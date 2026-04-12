"""
Tools for the agentic coordinator.

Each tool wraps an existing deterministic module so the LLM agent can
call it by name.  Tools use @tool from langchain_core which gives
them a name, description, and JSON schema that Claude can invoke.

The agent sees these tools and decides:
  - which to call
  - in what order
  - whether to call them again with different parameters
  - when it has enough evidence to stop

Tool design rules:
  - Tools take simple JSON-serialisable inputs (strings, dicts)
  - Tools return plain strings (the agent reads text, not objects)
  - Tools never crash — they return error strings the agent can react to
  - Tools are stateless — all context is passed in via arguments
"""

from __future__ import annotations

import json
from langchain_core.tools import tool

# ── dbt ingestion layer ──────────────────────────────────────────────────────
from app.dbt.manifest_loader import load_manifest
from app.dbt.run_results_loader import load_run_results
from app.dbt.model_resolver import resolve_failures, resolve_model
from app.dbt.lineage_builder import LineageGraph

# ── existing services ────────────────────────────────────────────────────────
from app.services.sql_parser import parse_sql
from app.services.error_parser import parse_error, parse_all_errors


@tool
def ingest_dbt_artifacts(
    manifest_path: str,
    run_results_path: str = "",
) -> str:
    """Load dbt manifest.json and run_results.json, find all failed models,
    and return their names, error messages, file paths, and upstream dependencies.

    Use this as your FIRST tool call to understand what failed and why.

    Args:
        manifest_path: Path to target/manifest.json
        run_results_path: Path to target/run_results.json (optional — if omitted, no failure detection)
    """
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as e:
        return f"ERROR loading manifest: {e}"

    result = {
        "project": manifest.metadata.to_dict(),
        "total_models": len(manifest.models),
        "all_models": manifest.all_model_names(),
    }

    if run_results_path:
        try:
            rr = load_run_results(run_results_path)
            result["run_summary"] = rr.summary()

            failures = resolve_failures(manifest, rr)
            result["failed_models"] = []
            for ctx in failures:
                result["failed_models"].append({
                    "name": ctx.failed_model,
                    "file_path": ctx.file_path,
                    "error_message": ctx.error_message[:500],
                    "upstream_models": [u.name for u in ctx.upstream_models],
                    "available_columns": ctx.available_columns,
                    "downstream_impacted": ctx.downstream_models,
                })
        except (FileNotFoundError, ValueError) as e:
            result["run_results_error"] = str(e)

    return json.dumps(result, indent=2)


@tool
def analyze_sql(sql: str) -> str:
    """Parse a SQL query using sqlglot and extract its structure:
    tables, columns, joins, filters, CTEs, aggregations, dbt refs, and aliases.

    Use this to understand what a broken SQL model is trying to do.

    Args:
        sql: The raw SQL or dbt model SQL (may contain {{ ref() }} syntax)
    """
    try:
        parsed = parse_sql(sql)
        return json.dumps(parsed.to_dict(), indent=2)
    except ValueError as e:
        return f"ERROR parsing SQL: {e}"


@tool
def analyze_error(error_message: str) -> str:
    """Parse a dbt/warehouse error message into structured sub-errors.
    Identifies the error type (missing_column, missing_relation, type_mismatch, etc.),
    extracts the offending column/table name, and finds candidate corrections.

    Args:
        error_message: The raw error text from dbt or the warehouse
    """
    primary = parse_error(error_message)
    all_errors = parse_all_errors(error_message)

    return json.dumps({
        "primary_error": primary.to_dict(),
        "all_errors": [e.to_dict() for e in all_errors],
        "total_sub_errors": len(all_errors),
    }, indent=2)


@tool
def get_lineage(manifest_path: str, target_model: str = "") -> str:
    """Build the DAG lineage graph from manifest.json.
    If target_model is given, returns the scoped lineage (upstream + downstream).
    If target_model is empty, returns the full project lineage.

    Returns nodes, edges, upstream chain, downstream chain, and paths to root.

    Args:
        manifest_path: Path to target/manifest.json
        target_model: Optional model to scope the lineage to
    """
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as e:
        return f"ERROR: {e}"

    graph = LineageGraph(manifest)

    if target_model:
        lineage = graph.to_dict_simple(target_model)
        full = graph.get_full_lineage(target_model)
        ascii_tree = graph.ascii(target_model)
    else:
        lineage = graph.to_dict_simple()
        full = {}
        ascii_tree = graph.ascii()

    return json.dumps({
        "lineage": lineage,
        "full_context": full,
        "ascii": ascii_tree,
    }, indent=2)


@tool
def check_columns_available(manifest_path: str, target_model: str) -> str:
    """Check which columns are available in the upstream models of the target model.
    Returns a dict mapping each upstream model name to its published columns
    (SELECT aliases from the model's SQL).

    Use this to verify whether a column referenced in the broken model actually
    exists in one of its upstream dependencies.

    Args:
        manifest_path: Path to target/manifest.json
        target_model: The name of the model to check (e.g. 'customer_revenue')
    """
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as e:
        return f"ERROR: {e}"

    model = manifest.get_model(target_model)
    if not model:
        return f"ERROR: Model '{target_model}' not found"

    upstream_names = manifest.get_upstream(target_model)
    result = {}
    for up in upstream_names:
        up_model = manifest.get_model(up)
        if not up_model:
            continue
        try:
            parsed = parse_sql(up_model.raw_sql)
            alias_names = list(parsed.aliases.keys())
            alias_sources = set(parsed.aliases.values())
            other_columns = [
                c for c in parsed.columns
                if c not in alias_sources and c not in alias_names
            ]
            seen = set()
            cols = []
            for c in alias_names + other_columns:
                if c not in seen:
                    seen.add(c)
                    cols.append(c)
            result[up] = cols
        except Exception:
            result[up] = []

    return json.dumps({
        "model": target_model,
        "upstream_models": upstream_names,
        "columns_per_upstream": result,
    }, indent=2)


@tool
def get_model_sql(manifest_path: str, target_model: str) -> str:
    """Retrieve the raw SQL and compiled SQL for a specific model from the manifest.
    Useful for inspecting upstream model SQL to understand column definitions.

    Args:
        manifest_path: Path to target/manifest.json
        target_model: The model name (e.g. 'stg_orders')
    """
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as e:
        return f"ERROR: {e}"

    model = manifest.get_model(target_model)
    if not model:
        return f"ERROR: Model '{target_model}' not found. Available: {manifest.all_model_names()}"

    return json.dumps({
        "name": model.name,
        "file_path": model.file_path,
        "materialized": model.materialized,
        "raw_sql": model.raw_sql,
        "compiled_sql": model.compiled_sql,
        "refs": model.refs,
        "depends_on_models": model.depends_on_models,
    }, indent=2)


@tool
def fetch_dbt_cloud_artifacts(
    api_token: str,
    account_id: str,
    run_id: str = "",
    job_id: str = "",
    base_url: str = "https://cloud.getdbt.com",
) -> str:
    """Fetch manifest.json and run_results.json from dbt Cloud API.
    Provide either run_id (specific run) or job_id (latest run of that job).

    Returns local file paths where the artifacts were downloaded.

    Args:
        api_token: dbt Cloud API token (Bearer token)
        account_id: dbt Cloud account ID
        run_id: Specific run ID to fetch artifacts from
        job_id: Job ID — will fetch the latest completed run's artifacts
        base_url: dbt Cloud API base URL (default: https://cloud.getdbt.com)
    """
    from app.dbt.cloud_client import DbtCloudClient

    try:
        client = DbtCloudClient(
            api_token=api_token,
            account_id=account_id,
            base_url=base_url,
        )
    except ValueError as e:
        return f"ERROR: {e}"

    try:
        if run_id:
            paths = client.fetch_artifacts(run_id=run_id)
        elif job_id:
            paths = client.fetch_latest_artifacts(job_id=job_id)
        else:
            return "ERROR: Provide either run_id or job_id"

        return json.dumps({
            "status": "downloaded",
            **paths.to_dict(),
        }, indent=2)
    except Exception as e:
        return f"ERROR fetching from dbt Cloud: {e}"
    finally:
        client.close()


# ── Tool registry ────────────────────────────────────────────────────────────

ALL_TOOLS = [
    ingest_dbt_artifacts,
    analyze_sql,
    analyze_error,
    get_lineage,
    check_columns_available,
    get_model_sql,
    fetch_dbt_cloud_artifacts,
]
