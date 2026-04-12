"""
LLM Analyzer — the primary analysis engine.

Architecture pivot note:
  This module replaces the hand-written rule_engine.py approach.
  Instead of hard-coded confidence values ("column_renamed_upstream =
  0.95"), the LLM reasons over structured evidence and produces
  its own assessment.

Flow (fast mode):
  1. Deterministic tools gather facts (SQL parser, manifest loader,
     error parser, lineage builder) — this is the cheap, fast part.
  2. We assemble those facts into a structured "evidence packet".
  3. ONE Claude call reads the packet and returns a diagnosis with
     root cause, explanation, confidence, corrected SQL, and
     validation steps.

Why a single call instead of a multi-step agent:
  - 10x faster (~4s vs 30s)
  - 25x cheaper (~$0.013 vs $0.30 per run)
  - More reliable structured output with one schema
  - Still handles novel errors — Claude is the reasoner

For truly complex or ambiguous cases, users can opt into the
multi-agent ReAct pipeline in app/graph/agent.py ("Deep analysis").

Course-relevant techniques used here:
  - Structured prompting (explicit evidence sections)
  - Chain-of-thought reasoning (system prompt asks for step-by-step)
  - Structured JSON output (strict schema)
  - Context engineering (grounding LLM in real manifest data)
  - Few-shot example in the system prompt
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import anthropic

from app.core.config import ANTHROPIC_API_KEY, LLM_TIMEOUT_SECONDS
from app.core.logging import get_logger
from app.dbt.manifest_loader import Manifest
from app.dbt.model_resolver import FailureContext
from app.services.sql_parser import ParsedSQL, parse_sql
from app.services.error_parser import ParsedError

log = get_logger(__name__)


# ── Response dataclass ───────────────────────────────────────────────────────

@dataclass
class AnalyzerResult:
    """Structured diagnosis from the LLM analyzer."""
    root_cause: str
    explanation: str
    confidence_score: float       # Claude's own self-assessment, 0.0-1.0
    corrected_sql: str            # empty string if no fix needed
    validation_steps: list[str] = field(default_factory=list)
    affected_columns: list[str] = field(default_factory=list)
    query_is_valid: bool = False  # True if the LLM thinks the SQL is actually fine
    hypotheses: list[dict] = field(default_factory=list)  # alternative causes
    tokens_used: dict = field(default_factory=dict)
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "root_cause": self.root_cause,
            "explanation": self.explanation,
            "confidence_score": self.confidence_score,
            "corrected_sql": self.corrected_sql,
            "validation_steps": self.validation_steps,
            "affected_columns": self.affected_columns,
            "query_is_valid": self.query_is_valid,
            "hypotheses": self.hypotheses,
            "tokens_used": self.tokens_used,
        }


# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert dbt pipeline debugger. You analyze broken dbt models \
and produce precise diagnoses grounded in the actual project structure.

You will receive a structured evidence packet containing:
  - The broken model's SQL (raw and compiled)
  - The error message from the warehouse
  - Every upstream model with its SQL and published columns
  - The dbt lineage path
  - Parsed entities from the broken SQL (tables, columns, aggregations)

Your reasoning process (think step-by-step internally):
  1. Identify what the broken SQL is trying to do
  2. Identify what the warehouse error is complaining about
  3. Check if the columns used in the broken SQL actually exist in the upstream models
  4. If a column is missing, check if a similar column exists (rename detection)
  5. Determine the root cause
  6. Write the corrected SQL
  7. Assess your confidence based on how directly the evidence supports your conclusion

Rules for confidence_score:
  - 0.95 or higher: direct evidence, only one reasonable interpretation
  - 0.80 to 0.94: strong evidence with minor ambiguity
  - 0.65 to 0.79: multiple plausible causes, you picked the most likely
  - Below 0.65: weak evidence, you're guessing
  Be honest. If you're guessing, say so.

Rules for query_is_valid:
  - Set to true ONLY if you believe the SQL is actually correct AND the error must be stale (e.g. from a previous run)
  - Set to false in all other cases

Important constraints:
  - Base your diagnosis ONLY on the evidence provided. Do not hallucinate columns or models that aren't in the packet.
  - Use the EXACT column names from the upstream models in your corrected SQL.
  - Preserve the original query's semantics (SELECT aliases, GROUP BY, etc.)
  - If the broken SQL uses Jinja like {{ ref('model') }}, keep that syntax in the corrected version.

Output format:
  Respond with ONLY valid JSON matching this schema — no markdown fences, no prose outside the JSON:

{
  "root_cause": "<one-sentence summary>",
  "explanation": "<2-4 sentence plain-English explanation>",
  "confidence_score": <float 0.0-1.0>,
  "query_is_valid": <boolean>,
  "corrected_sql": "<full corrected SQL, or empty string if query is already valid>",
  "validation_steps": ["<step 1>", "<step 2>", ...],
  "affected_columns": ["<column name>", ...],
  "hypotheses": [
    {"cause": "<short label>", "description": "<why this might be it>", "confidence": <float>}
  ]
}

Example few-shot:

Evidence: A dbt model customer_revenue uses `sum(amount)` from stg_orders. \
stg_orders publishes columns [order_id, customer_id, amount_total, status]. \
Error: "column 'amount' not found".

Good response:
{
  "root_cause": "Column 'amount' was renamed to 'amount_total' in the upstream stg_orders model.",
  "explanation": "The customer_revenue model references 'amount', but looking at stg_orders the column is actually published as 'amount_total' (likely renamed from 'price' during staging). Downstream models need to use the new name.",
  "confidence_score": 0.96,
  "query_is_valid": false,
  "corrected_sql": "select customer_id, sum(amount_total) as total_revenue from {{ ref('stg_orders') }} group by customer_id",
  "validation_steps": [
    "Run `dbt compile --select customer_revenue` to verify the SQL compiles",
    "Run `dbt run --select customer_revenue` to confirm it executes",
    "Spot-check total_revenue values for a known customer against raw source data"
  ],
  "affected_columns": ["amount", "amount_total"],
  "hypotheses": [
    {"cause": "column_renamed_upstream", "description": "stg_orders aliases price to amount_total", "confidence": 0.96},
    {"cause": "typo", "description": "Developer typed 'amount' instead of 'amount_total'", "confidence": 0.30}
  ]
}
"""


def _build_user_prompt(
    failure: FailureContext,
    parsed_sql: ParsedSQL,
    parsed_error: ParsedError,
    upstream_details: list[dict],
) -> str:
    """Assemble the structured evidence packet as a formatted user prompt."""
    upstream_block = "\n\n".join(
        f"### {u['name']} ({u['file_path']})\n"
        f"Published columns: {u['columns']}\n"
        f"Materialized: {u['materialized']}\n"
        f"Status: {u['status']}\n"
        f"SQL:\n```sql\n{u['raw_sql'][:800]}\n```"
        for u in upstream_details
    ) if upstream_details else "(none — this is a root model with no upstream)"

    lineage_chain = " → ".join(failure.all_upstream_names[::-1] + [failure.failed_model]) \
        if failure.all_upstream_names else failure.failed_model

    error_block = (
        f"Type: {parsed_error.error_type.value}\n"
        f"Column: {parsed_error.column or 'N/A'}\n"
        f"Relation: {parsed_error.relation or 'N/A'}\n"
        f"Line: {parsed_error.line_number or 'N/A'}\n"
        f"Warehouse candidates: {parsed_error.candidates or 'none'}\n"
        f"Raw message:\n{parsed_error.raw_text[:600]}"
    ) if parsed_error and parsed_error.raw_text else f"Raw message:\n{failure.error_message[:600]}"

    parsed_block = (
        f"Tables referenced: {parsed_sql.tables}\n"
        f"Columns used: {parsed_sql.columns}\n"
        f"Aggregations: {parsed_sql.aggregations}\n"
        f"dbt refs: {parsed_sql.dbt_refs}\n"
        f"CTEs: {parsed_sql.ctes}\n"
        f"Column aliases: {parsed_sql.aliases}\n"
        f"GROUP BY: {parsed_sql.group_by}"
    ) if parsed_sql else "(SQL could not be parsed)"

    return f"""\
## Broken model
Name: {failure.failed_model}
File: {failure.file_path}
Materialization: {failure.materialized}
Schema: {failure.schema}

## Broken SQL
```sql
{failure.raw_sql}
```

## Warehouse error
{error_block}

## Lineage path
{lineage_chain}

## Upstream models
{upstream_block}

## Parsed entities from the broken SQL
{parsed_block}

---

Now analyze this failure step by step and respond with the JSON diagnosis.
"""


# ── Main API ─────────────────────────────────────────────────────────────────

def analyze(
    failure: FailureContext,
    parsed_sql: ParsedSQL | None,
    parsed_error: ParsedError | None,
    manifest: Manifest,
    model_name: str = "claude-sonnet-4-20250514",
) -> AnalyzerResult:
    """Run a single Claude call to diagnose a dbt failure.

    Args:
        failure: Context from resolve_failures / resolve_model
        parsed_sql: Pre-parsed SQL entities (optional)
        parsed_error: Pre-parsed error message (optional)
        manifest: The loaded dbt manifest (for upstream column lookup)
        model_name: Claude model ID

    Returns:
        AnalyzerResult with structured diagnosis

    Raises:
        ValueError: if ANTHROPIC_API_KEY is missing or response is malformed
    """
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_api_key_here":
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. "
            "Add your key to .env: ANTHROPIC_API_KEY=sk-ant-..."
        )

    # ── Gather upstream details ──────────────────────────────────────
    # For each upstream model in the failure context, look up its full
    # ModelNode in the manifest to get richer info than failure_context
    # provides by default.
    upstream_details: list[dict] = []
    for um in failure.upstream_models:
        upstream_details.append({
            "name": um.name,
            "file_path": um.file_path,
            "materialized": um.materialized,
            "status": um.status,
            "columns": um.columns_from_sql,
            "raw_sql": manifest.get_raw_sql(um.name),
        })

    # ── Build the prompt ─────────────────────────────────────────────
    user_prompt = _build_user_prompt(
        failure=failure,
        parsed_sql=parsed_sql,
        parsed_error=parsed_error,
        upstream_details=upstream_details,
    )

    # ── Call Claude ──────────────────────────────────────────────────
    client = anthropic.Anthropic(
        api_key=ANTHROPIC_API_KEY,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=2,
    )

    log.info(
        "llm_analyzer_call",
        model=failure.failed_model,
        upstream_count=len(upstream_details),
        prompt_chars=len(user_prompt),
    )

    message = client.messages.create(
        model=model_name,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text
    tokens_used = {
        "input_tokens": getattr(message.usage, "input_tokens", 0),
        "output_tokens": getattr(message.usage, "output_tokens", 0),
    }

    return _parse_response(raw, failure.raw_sql, tokens_used)


def _parse_response(
    raw: str, original_sql: str, tokens_used: dict
) -> AnalyzerResult:
    """Parse Claude's JSON response into an AnalyzerResult.

    Falls back gracefully if the response is malformed: returns a result
    with the raw text as the explanation and confidence=0.
    """
    # Strip accidental markdown fences if Claude adds them despite the prompt
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    clean = re.sub(r"\s*```$", "", clean.strip(), flags=re.MULTILINE)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        log.warning("llm_response_not_json", error=str(e), preview=raw[:200])
        return AnalyzerResult(
            root_cause="LLM response could not be parsed as JSON",
            explanation=raw[:500],
            confidence_score=0.0,
            corrected_sql=original_sql,
            query_is_valid=False,
            tokens_used=tokens_used,
            raw_response=raw,
        )

    return AnalyzerResult(
        root_cause=data.get("root_cause", ""),
        explanation=data.get("explanation", ""),
        confidence_score=float(data.get("confidence_score", 0.0)),
        corrected_sql=data.get("corrected_sql", "") or "",
        validation_steps=data.get("validation_steps", []) or [],
        affected_columns=data.get("affected_columns", []) or [],
        query_is_valid=bool(data.get("query_is_valid", False)),
        hypotheses=data.get("hypotheses", []) or [],
        tokens_used=tokens_used,
        raw_response=raw,
    )
