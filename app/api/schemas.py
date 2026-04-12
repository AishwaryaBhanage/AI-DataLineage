"""
API request/response schemas for the v1 debug API.

Pydantic models that define the contract between the API and its consumers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────────────────

class DebugMode(str, Enum):
    FAST = "fast"           # deterministic pipeline, no LLM in the loop
    AGENTIC = "agentic"     # Claude-driven tool-calling agent


class ArtifactSource(str, Enum):
    LOCAL = "local"         # files on disk
    CLOUD = "cloud"         # dbt Cloud API


# ── Request schemas ──────────────────────────────────────────────────────────

class DebugRequest(BaseModel):
    """Request to debug a dbt model failure."""
    model_config = {"protected_namespaces": ()}

    # Artifact source — where to find manifest/run_results
    source: ArtifactSource = ArtifactSource.LOCAL

    # Local file paths (required when source=local)
    manifest_path: Optional[str] = None
    run_results_path: Optional[str] = None

    # dbt Cloud parameters (required when source=cloud)
    dbt_cloud_token: Optional[str] = None
    dbt_cloud_account_id: Optional[str] = None
    dbt_cloud_run_id: Optional[str] = None
    dbt_cloud_job_id: Optional[str] = None

    # Debugging options
    model_name: Optional[str] = Field(
        default=None,
        description="Specific model to debug. Auto-detected from run_results if omitted."
    )
    mode: DebugMode = Field(
        default=DebugMode.FAST,
        description="'fast' = deterministic pipeline (no LLM). 'agentic' = Claude-driven agent."
    )
    use_llm: bool = Field(
        default=True,
        description="In fast mode: whether to call Claude for explanation after rules. "
                    "Ignored in agentic mode (always uses LLM)."
    )

    # Optional: manually provide SQL/error (skips auto-detection from artifacts)
    sql: Optional[str] = None
    error_message: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    environment: str = "development"
    modes: list[str] = ["fast", "agentic"]
    checks: dict = {}


# ── Response schemas ─────────────────────────────────────────────────────────

class AnalyzerHypothesis(BaseModel):
    cause: str
    description: str
    confidence: float


class AnalyzerResultResponse(BaseModel):
    """The LLM-produced diagnosis — the primary result of a fast analysis."""
    root_cause: str
    explanation: str
    confidence_score: float
    corrected_sql: str
    validation_steps: list[str] = []
    affected_columns: list[str] = []
    query_is_valid: bool = False
    hypotheses: list[AnalyzerHypothesis] = []
    tokens_used: dict = {}


class ParsedSQLResponse(BaseModel):
    tables: list[str]
    columns: list[str]
    joins: list
    filters: list[str]
    ctes: list[str]
    aggregations: list[str]
    dbt_refs: list[str]
    aliases: dict[str, str]
    group_by: list[str]


class ParsedErrorResponse(BaseModel):
    raw_text: str
    error_type: str
    column: Optional[str] = None
    relation: Optional[str] = None
    model: Optional[str] = None
    line_number: Optional[int] = None
    hint: Optional[str] = None
    candidates: list[str] = []


class LLMResultResponse(BaseModel):
    root_cause: str
    explanation: str
    corrected_sql: str
    confidence_score: float
    validation_steps: list[str] = []
    ranked_causes: list[dict] = []


class FastDebugResponse(BaseModel):
    """Response from the LLM-powered debug analysis (default mode).

    This is the "single LLM call with structured evidence" response.
    The rule_hits field is kept empty for backward compat with old clients
    but will be removed in a future version — use analyzer_result instead.
    """
    mode: str = "fast"
    broken_model: str
    file_path: str = ""
    raw_sql: str = ""
    compiled_sql: Optional[str] = None
    parsed_sql: Optional[ParsedSQLResponse] = None
    parsed_error: Optional[ParsedErrorResponse] = None
    lineage: dict = {}
    lineage_ascii: str = ""
    upstream_columns: dict[str, list[str]] = {}
    query_is_valid: bool = False
    corrected_sql: Optional[str] = None
    analyzer_result: Optional[AnalyzerResultResponse] = None
    errors: list[str] = []


class AgenticDebugResponse(BaseModel):
    """Response from the agentic (Claude-driven) debug mode."""
    mode: str = "agentic"
    diagnosis: dict | str
    tools_used: list[str] = []
    errors: list[str] = []


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
