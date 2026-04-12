"""
LangGraph debug pipeline — LLM-first architecture.

Execution flow:

    START
      │
      ▼
    ingest                Load dbt artifacts, find failed model
      │
      ├──────┐
      ▼      ▼            PARALLEL: these two are independent
  parse_sql  parse_error
      │      │
      └──┬───┘
         ▼
    build_lineage         Construct DAG
         │
         ▼
    llm_analyze           Single Claude call with structured evidence
         │
         ▼
        END

No more rule engine.  No more conditional "skip LLM" routing.
The LLM is the primary reasoner.  For complex cases the user can
opt into the multi-agent ReAct pipeline in app/graph/agent.py.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from app.graph.state import PipelineState
from app.graph.nodes import (
    node_ingest,
    node_parse_sql,
    node_parse_error,
    node_build_lineage,
    node_llm_analyze,
)


def build_graph() -> StateGraph:
    """Construct the LangGraph StateGraph (uncompiled)."""
    graph = StateGraph(PipelineState)

    graph.add_node("ingest", node_ingest)
    graph.add_node("parse_sql", node_parse_sql)
    graph.add_node("parse_error", node_parse_error)
    graph.add_node("build_lineage", node_build_lineage)
    graph.add_node("llm_analyze", node_llm_analyze)

    # START → ingest
    graph.add_edge(START, "ingest")

    # ingest → parse_sql AND parse_error (parallel fan-out)
    graph.add_edge("ingest", "parse_sql")
    graph.add_edge("ingest", "parse_error")

    # parse_sql + parse_error → build_lineage (fan-in: waits for both)
    graph.add_edge("parse_sql", "build_lineage")
    graph.add_edge("parse_error", "build_lineage")

    # build_lineage → llm_analyze → END
    graph.add_edge("build_lineage", "llm_analyze")
    graph.add_edge("llm_analyze", END)

    return graph


# ── Pre-compiled graph (singleton) ───────────────────────────────────────────

_compiled = build_graph().compile()


def run_graph(
    manifest_path: str,
    run_results_path: str = "",
    model_name: str | None = None,
    use_llm: bool = True,
) -> PipelineState:
    """Run the full debug pipeline via LangGraph.

    Args:
        manifest_path:    Path to target/manifest.json
        run_results_path: Path to target/run_results.json (optional)
        model_name:       Override model to debug (auto-detected if None)
        use_llm:          Set False to skip the LLM analysis entirely

    Returns:
        Final PipelineState dict with all fields populated by each node.
    """
    initial_state: PipelineState = {
        "manifest_path": manifest_path,
        "run_results_path": run_results_path,
        "model_name": model_name,
        "use_llm": use_llm,
        "errors": [],
    }

    final_state = _compiled.invoke(initial_state)
    return final_state


def get_compiled_graph():
    """Return the compiled graph for inspection or custom invocation."""
    return _compiled
