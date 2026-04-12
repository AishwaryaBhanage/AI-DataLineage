"""
Shared state schema for the LangGraph debug pipeline.

Every node in the graph reads from and writes to this single TypedDict.
LangGraph merges each node's return dict into the state automatically —
a node only needs to return the keys it wants to update.

Design rules:
  - All fields are Optional so nodes can run in any order during development.
  - Fields use plain types (dicts, lists, strings) rather than dataclass
    instances, because LangGraph serializes state for checkpointing.
  - The `errors` list accumulates non-fatal warnings from any node.
    A node appends to it rather than crashing the pipeline.
"""

from __future__ import annotations

from typing import TypedDict, Annotated
import operator

from app.dbt.manifest_loader import Manifest
from app.dbt.run_results_loader import RunResults
from app.dbt.model_resolver import FailureContext
from app.services.sql_parser import ParsedSQL
from app.services.error_parser import ParsedError
from app.services.llm_analyzer import AnalyzerResult


class PipelineState(TypedDict, total=False):
    """Shared state flowing through the LangGraph debug pipeline."""

    # ── Inputs (provided at invocation) ──────────────────────────────
    manifest_path: str
    run_results_path: str
    model_name: str | None      # optional: override auto-detection
    use_llm: bool               # default True

    # ── Produced by: ingest ──────────────────────────────────────────
    manifest: Manifest | None
    run_results: RunResults | None
    failure_context: FailureContext | None
    broken_model: str

    # ── Produced by: parse_sql ───────────────────────────────────────
    parsed_sql: ParsedSQL | None

    # ── Produced by: parse_error ─────────────────────────────────────
    parsed_error: ParsedError | None
    all_errors: list[ParsedError]

    # ── Produced by: build_lineage ───────────────────────────────────
    lineage: dict
    lineage_ascii: str

    # ── Produced by: llm_analyze (replaces old rule_engine node) ────
    analyzer_result: AnalyzerResult | None
    query_is_valid: bool
    corrected_sql: str | None
    upstream_columns: dict[str, list[str]]

    # ── Accumulator: non-fatal warnings from any node ────────────────
    errors: Annotated[list[str], operator.add]
