"""
LangGraph node functions — LLM-first architecture.

Each function:
  - Takes the full PipelineState as input
  - Returns a dict with ONLY the keys it wants to update
  - Never mutates the input state directly
  - Catches its own exceptions and writes to state["errors"]
    rather than crashing the graph

Pipeline flow (fast mode):
  ingest → [parse_sql, parse_error] (parallel) → build_lineage → llm_analyze → END

Deprecated nodes (removed in this pivot):
  - node_run_rules      → replaced by node_llm_analyze
  - node_call_llm       → merged into node_llm_analyze
"""

from __future__ import annotations

from app.graph.state import PipelineState

# ── dbt ingestion layer ──────────────────────────────────────────────────────
from app.dbt.manifest_loader import load_manifest
from app.dbt.run_results_loader import load_run_results
from app.dbt.model_resolver import resolve_failures, resolve_model
from app.dbt.lineage_builder import LineageGraph

# ── services layer ──────────────────────────────────────────────────────────
from app.services.sql_parser import parse_sql
from app.services.error_parser import (
    parse_error,
    parse_all_errors,
    ParsedError,
    ErrorType,
)
from app.services.llm_analyzer import analyze as llm_analyze


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1: ingest
# ─────────────────────────────────────────────────────────────────────────────

def node_ingest(state: PipelineState) -> dict:
    """Load dbt artifacts and resolve the failed model.

    Reads:  manifest_path, run_results_path, model_name
    Writes: manifest, run_results, failure_context, broken_model,
            upstream_columns
    """
    manifest_path = state["manifest_path"]
    run_results_path = state.get("run_results_path", "")
    requested_model = state.get("model_name")

    manifest = load_manifest(manifest_path)

    run_results = None
    errors: list[str] = []
    if run_results_path:
        try:
            run_results = load_run_results(run_results_path)
        except FileNotFoundError:
            errors.append(
                f"run_results.json not found at {run_results_path}. "
                "Continuing without execution results."
            )

    failure_context = None
    broken_model = requested_model or ""

    if requested_model:
        if run_results:
            failure_context = resolve_model(manifest, run_results, requested_model)
    elif run_results:
        failures = resolve_failures(manifest, run_results)
        if failures:
            failure_context = failures[0]

    if failure_context:
        broken_model = failure_context.failed_model

    if not broken_model:
        errors.append("Could not determine which model to debug.")

    upstream_columns: dict[str, list[str]] = {}
    if failure_context:
        upstream_columns = failure_context.available_columns

    return {
        "manifest": manifest,
        "run_results": run_results,
        "failure_context": failure_context,
        "broken_model": broken_model,
        "upstream_columns": upstream_columns,
        "errors": errors,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2: parse_sql
# ─────────────────────────────────────────────────────────────────────────────

def node_parse_sql(state: PipelineState) -> dict:
    """Parse the broken model's SQL using sqlglot."""
    ctx = state.get("failure_context")
    if not ctx:
        return {"errors": ["parse_sql: no failure_context available."]}

    sql = ctx.raw_sql
    if not sql.strip():
        return {"errors": ["parse_sql: empty SQL in failure_context."]}

    try:
        parsed = parse_sql(sql)
    except ValueError as e:
        return {"errors": [f"parse_sql: {e}"]}

    return {"parsed_sql": parsed}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3: parse_error
# ─────────────────────────────────────────────────────────────────────────────

def node_parse_error(state: PipelineState) -> dict:
    """Parse the error message into typed sub-errors."""
    ctx = state.get("failure_context")
    if not ctx:
        return {"errors": ["parse_error: no failure_context available."]}

    error_text = ctx.error_message
    if not error_text.strip():
        return {
            "parsed_error": ParsedError(
                raw_text="", error_type=ErrorType.UNKNOWN
            ),
            "all_errors": [],
        }

    parsed = parse_error(error_text)
    all_errs = parse_all_errors(error_text)

    return {
        "parsed_error": parsed,
        "all_errors": all_errs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4: build_lineage
# ─────────────────────────────────────────────────────────────────────────────

def node_build_lineage(state: PipelineState) -> dict:
    """Build the DAG and compute lineage for the broken model."""
    manifest = state.get("manifest")
    if not manifest:
        return {"errors": ["build_lineage: no manifest loaded."]}

    broken_model = state.get("broken_model", "")
    run_results = state.get("run_results")

    graph = LineageGraph(manifest, run_results)
    lineage = graph.to_dict_simple(broken_model or None)
    lineage_ascii = graph.ascii(broken_model or None)

    return {
        "lineage": lineage,
        "lineage_ascii": lineage_ascii,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5: llm_analyze (NEW — replaces rule engine + legacy llm call)
# ─────────────────────────────────────────────────────────────────────────────

def node_llm_analyze(state: PipelineState) -> dict:
    """Run a single Claude call with structured evidence.

    This is the core of the LLM-first pipeline.  The LLM receives the
    full evidence packet (broken SQL, parsed entities, error details,
    upstream columns, lineage) and produces a diagnosis.

    Reads:  failure_context, parsed_sql, parsed_error, manifest
    Writes: analyzer_result, query_is_valid, corrected_sql
    """
    ctx = state.get("failure_context")
    parsed_sql = state.get("parsed_sql")
    parsed_error = state.get("parsed_error")
    manifest = state.get("manifest")

    if not ctx:
        return {"errors": ["llm_analyze: no failure_context available."]}
    if not manifest:
        return {"errors": ["llm_analyze: no manifest available."]}

    # Skip the LLM entirely if the user opted out
    if not state.get("use_llm", True):
        return {
            "errors": ["llm_analyze: skipped (use_llm=false)"],
            "query_is_valid": False,
        }

    try:
        result = llm_analyze(
            failure=ctx,
            parsed_sql=parsed_sql,
            parsed_error=parsed_error,
            manifest=manifest,
        )
    except ValueError as e:
        return {"errors": [f"llm_analyze: {e}"]}
    except Exception as e:
        return {"errors": [f"llm_analyze: unexpected error: {e}"]}

    return {
        "analyzer_result": result,
        "query_is_valid": result.query_is_valid,
        "corrected_sql": result.corrected_sql or None,
    }
