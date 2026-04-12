"""
dbt Model Resolver
Joins manifest + run_results to build a complete failure context.

This is the JOIN LAYER between:
  - Manifest (structure: SQL, dependencies, columns)
  - RunResults (outcomes: pass/fail, error messages, timing)

For each failed model it assembles everything the debugger needs:
  - the broken SQL (raw + compiled)
  - the error message from the warehouse
  - every upstream model and what columns it produces
  - every downstream model that is impacted

This module does NOT analyse or determine root causes.
It assembles the evidence packet.

Usage:
    manifest = load_manifest("target/manifest.json")
    results  = load_run_results("target/run_results.json")

    # all failures at once
    failures = resolve_failures(manifest, results)

    # one specific model
    ctx = resolve_model(manifest, results, "customer_revenue")
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.dbt.manifest_loader import Manifest, ModelNode
from app.dbt.run_results_loader import RunResults, NodeResult
from app.services.sql_parser import parse_sql


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class UpstreamModel:
    """Everything we know about one upstream dependency of the failed model.

    columns_from_docs  — columns documented in schema.yml (often empty)
    columns_from_sql   — columns extracted by parsing the model's raw SQL
                         via sqlglot.  These are the SELECT aliases, which
                         are the "published" names downstream models see.
    """
    name: str
    unique_id: str
    file_path: str
    materialized: str
    status: str                         # from run_results, or "unknown"
    columns_from_docs: dict[str, str]   # {col_name: description}
    columns_from_sql: list[str]         # parsed from raw SQL

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "unique_id": self.unique_id,
            "file_path": self.file_path,
            "materialized": self.materialized,
            "status": self.status,
            "columns_from_docs": self.columns_from_docs,
            "columns_from_sql": self.columns_from_sql,
        }


@dataclass(frozen=True)
class FailureContext:
    """Complete context for debugging one failed model.

    This is the evidence packet that the rule engine and LLM consume.

    Key fields:
      upstream_models    — direct parents with their column info
      available_columns  — flat {model_name: [col, ...]} for quick lookup
      all_upstream_names — full ancestor chain (recursive), closest first
      downstream_models  — models impacted by this failure (blast radius)
    """
    failed_model: str
    unique_id: str
    file_path: str
    raw_sql: str
    compiled_sql: str | None
    error_message: str
    materialized: str
    schema: str
    upstream_models: list[UpstreamModel]
    available_columns: dict[str, list[str]]
    downstream_models: list[str]
    all_upstream_names: list[str]

    def to_dict(self) -> dict:
        return {
            "failed_model": self.failed_model,
            "unique_id": self.unique_id,
            "file_path": self.file_path,
            "raw_sql": self.raw_sql,
            "compiled_sql": self.compiled_sql,
            "error_message": self.error_message,
            "materialized": self.materialized,
            "schema": self.schema,
            "upstream_models": [u.to_dict() for u in self.upstream_models],
            "available_columns": self.available_columns,
            "downstream_models": self.downstream_models,
            "all_upstream_names": self.all_upstream_names,
        }


# ── Column extraction ────────────────────────────────────────────────────────

def _extract_columns_from_sql(raw_sql: str) -> list[str]:
    """Parse a model's raw SQL and return the output column names.

    The "output columns" of a dbt model are the SELECT-level aliases.
    For example:
        SELECT order_id, price AS amount_total FROM raw_orders
    produces: ["order_id", "amount_total"]

    Why aliases take priority:
        When a model does `SELECT price AS amount_total`, downstream
        models see "amount_total" — not "price".  So the alias is the
        published column name.

    Returns an empty list if parsing fails (e.g. complex Jinja that
    sqlglot can't handle after stripping).
    """
    if not raw_sql.strip():
        return []
    try:
        parsed = parse_sql(raw_sql)
    except (ValueError, Exception):
        return []

    # aliases = {"amount_total": "price"} — these are the published names
    # columns = ["order_id", "price", ...] — these are the raw references
    #
    # Strategy: start with alias names (the published outputs),
    # then add any columns that aren't already covered by an alias's
    # source expression.  This avoids duplicates like showing both
    # "price" and "amount_total" when they're the same column.
    alias_names = list(parsed.aliases.keys())
    alias_sources = set(parsed.aliases.values())

    other_columns = [
        col for col in parsed.columns
        if col not in alias_sources and col not in alias_names
    ]

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for col in alias_names + other_columns:
        if col not in seen:
            seen.add(col)
            result.append(col)

    return result


def _build_upstream_model(
    model_node: ModelNode,
    run_results: RunResults,
) -> UpstreamModel:
    """Build an UpstreamModel for one direct upstream dependency."""
    # Get run status from results (may not exist if model wasn't in this run)
    result = run_results.get_by_id(model_node.unique_id)
    status = result.status if result else "unknown"

    # Documented columns from schema.yml (often empty)
    columns_from_docs = {
        name: info.description
        for name, info in model_node.columns.items()
    }

    # Parsed columns from raw SQL (the reliable source)
    columns_from_sql = _extract_columns_from_sql(model_node.raw_sql)

    return UpstreamModel(
        name=model_node.name,
        unique_id=model_node.unique_id,
        file_path=model_node.file_path,
        materialized=model_node.materialized,
        status=status,
        columns_from_docs=columns_from_docs,
        columns_from_sql=columns_from_sql,
    )


# ── Public API ───────────────────────────────────────────────────────────────

def resolve_model(
    manifest: Manifest,
    run_results: RunResults,
    model_name: str,
) -> FailureContext | None:
    """Build a complete FailureContext for a specific model.

    Works for any model — it doesn't have to be a failed one.
    This is useful when the user manually selects which model to debug.

    Args:
        manifest:    Parsed manifest (from load_manifest)
        run_results: Parsed run results (from load_run_results)
        model_name:  Short model name (e.g. "customer_revenue")

    Returns:
        FailureContext with all upstream info, or None if the model
        doesn't exist in the manifest.
    """
    model_node = manifest.get_model(model_name)
    if not model_node:
        return None

    # Get error message from run results (empty string if model passed)
    result = run_results.get_by_name(model_name)
    error_message = result.error_message if result else ""

    # Prefer compiled SQL from run_results (it's the actual SQL that was
    # sent to the warehouse).  Fall back to manifest's compiled_sql.
    compiled_sql = None
    if result and result.compiled_sql:
        compiled_sql = result.compiled_sql
    elif model_node.compiled_sql:
        compiled_sql = model_node.compiled_sql

    # Build upstream models — direct parents only.
    # We resolve these because they hold the column information
    # the debugger needs to check for renames, missing columns, etc.
    direct_upstream_names = manifest.get_upstream(model_name)
    upstream_models: list[UpstreamModel] = []

    for up_name in direct_upstream_names:
        up_node = manifest.get_model(up_name)
        if up_node:
            upstream_models.append(
                _build_upstream_model(up_node, run_results)
            )

    # Flat column map for quick lookup: {model_name: [col1, col2, ...]}
    available_columns: dict[str, list[str]] = {
        um.name: um.columns_from_sql for um in upstream_models
    }

    # Full ancestor chain (recursive) — for blast-radius and deep lineage
    all_upstream_names = manifest.get_all_upstream(model_name)

    # Downstream models impacted by this failure
    downstream_models = manifest.get_all_downstream(model_name)

    return FailureContext(
        failed_model=model_name,
        unique_id=model_node.unique_id,
        file_path=model_node.file_path,
        raw_sql=model_node.raw_sql,
        compiled_sql=compiled_sql,
        error_message=error_message,
        materialized=model_node.materialized,
        schema=model_node.schema,
        upstream_models=upstream_models,
        available_columns=available_columns,
        downstream_models=downstream_models,
        all_upstream_names=all_upstream_names,
    )


def resolve_failures(
    manifest: Manifest,
    run_results: RunResults,
) -> list[FailureContext]:
    """Build a FailureContext for every failed model in the run.

    Skipped models are NOT included — they failed only because an
    upstream model failed, not because of their own bug.

    Returns:
        List of FailureContext objects, one per failed model.
        Empty list if all models passed.
    """
    contexts: list[FailureContext] = []

    for failure in run_results.failed():
        if not failure.is_model:
            continue  # skip failed tests/snapshots/seeds for now

        ctx = resolve_model(manifest, run_results, failure.model_name)
        if ctx:
            contexts.append(ctx)

    return contexts
