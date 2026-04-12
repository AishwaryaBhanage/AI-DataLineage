"""
Agentic Coordinator — LangGraph ReAct agent.

This is the AGENTIC version of the debug pipeline.  Instead of running
nodes in a fixed order, Claude receives a set of tools and decides:
  - which tools to call
  - in what order
  - whether to call them again
  - when it has enough evidence to produce a diagnosis

The loop:
    Thought → Tool Call → Observation → Thought → ... → Final Answer

The agent has access to:
  - ingest_dbt_artifacts    — load manifest + run results, find failures
  - analyze_sql             — parse SQL structure via sqlglot
  - analyze_error           — parse error message into typed sub-errors
  - get_lineage             — build DAG, get upstream/downstream
  - run_rule_engine         — deterministic root-cause analysis
  - get_model_sql           — inspect any model's SQL
  - fetch_dbt_cloud_artifacts — download artifacts from dbt Cloud API

Usage:
    from app.graph.agent import run_agent

    result = run_agent(
        manifest_path="dbt_demo/target/manifest.json",
        run_results_path="dbt_demo/target/run_results.json",
    )
    print(result["diagnosis"])    # agent's final analysis
    print(result["tool_calls"])   # what tools it used
"""

from __future__ import annotations

import json
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from app.core.config import (
    ANTHROPIC_API_KEY,
    LLM_TIMEOUT_SECONDS,
    AGENT_MAX_ITERATIONS,
)
from app.graph.tools import ALL_TOOLS


# ── System prompt ────────────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPT = """\
You are DataLineage AI — an expert dbt/SQL pipeline debugger.

You have tools that let you inspect dbt projects, parse SQL, analyze errors,
build lineage graphs, and check what columns are available in upstream models.
You are the reasoning engine — YOU decide what's wrong and how to fix it.

## Your debugging process

1. START by ingesting the dbt artifacts to understand what failed
2. ANALYZE the broken SQL structure
3. ANALYZE the error message to understand what the warehouse is complaining about
4. CHECK what columns are actually available in upstream models
5. COMPARE what the broken SQL uses vs what upstream provides
6. If the answer isn't obvious, INSPECT the upstream models' SQL directly
7. IDENTIFY the root cause and write the corrected SQL

## Important guidelines

- Always use the tools — never guess about SQL structure or column names
- Base your diagnosis ONLY on evidence from the tools — do not hallucinate columns
- When you inspect upstream models, focus on SELECT aliases — those are the
  "published" column names that downstream models see
- Preserve the original query's semantics (SELECT aliases, GROUP BY, Jinja refs)
- Provide your final answer as a structured diagnosis with:
  - root cause (one sentence)
  - explanation (2-4 sentences in plain English)
  - corrected SQL (if applicable)
  - confidence score (0.0-1.0) — be honest, not optimistic
  - validation steps the engineer should run

## Output format — CRITICAL

When you have enough evidence to finalize your diagnosis, your FINAL response
(the message with no more tool calls) must contain ONLY a single JSON object
matching the schema below.

Do NOT include:
  - Any preamble like "Now I have complete evidence" or "Here is my diagnosis"
  - Any markdown code fences (```json ... ```)
  - Any trailing commentary after the closing brace
  - Any text outside the JSON

The caller will parse the first balanced JSON object in your response. Every
character outside that object is wasted tokens.

Schema (strict):

{
  "root_cause": "<one sentence summary>",
  "explanation": "<2-4 sentence plain-English explanation>",
  "corrected_sql": "<full corrected SQL, or empty string if no fix needed>",
  "confidence_score": <float between 0.0 and 1.0>,
  "validation_steps": ["<step 1>", "<step 2>", "<step 3>"],
  "affected_columns": ["<column name>", ...],
  "hypotheses": [
    {"cause": "<label>", "description": "<why>", "confidence": <float>}
  ]
}

Start your final response with `{` and end with `}`. Nothing else.
"""


# ── Agent construction ───────────────────────────────────────────────────────

def _build_agent():
    """Build the ReAct agent with Claude and all tools."""
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_api_key_here":
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. "
            "Add your key to .env: ANTHROPIC_API_KEY=sk-ant-..."
        )

    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=ANTHROPIC_API_KEY,
        max_tokens=4096,
        temperature=0,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=2,
    )

    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=AGENT_SYSTEM_PROMPT,
        name="datalineage_agent",
    )

    return agent


def _enforce_max_iterations(messages: list, max_iters: int) -> bool:
    """Return True if the agent has exceeded the max tool-call budget.

    Why: a misbehaving agent could call tools in an infinite loop.
    Each tool call burns Anthropic tokens.  We cap iterations to bound
    cost per request.
    """
    from langchain_core.messages import AIMessage
    tool_call_count = sum(
        1 for m in messages
        if isinstance(m, AIMessage) and m.tool_calls
    )
    return tool_call_count >= max_iters


# ── Public API ───────────────────────────────────────────────────────────────

def run_agent(
    manifest_path: str,
    run_results_path: str = "",
    model_name: str | None = None,
    extra_context: str = "",
) -> dict[str, Any]:
    """Run the agentic debug pipeline.

    The agent will autonomously decide which tools to call and in what
    order to diagnose the failure.

    Args:
        manifest_path:    Path to target/manifest.json
        run_results_path: Path to target/run_results.json (optional)
        model_name:       Specific model to debug (auto-detected if None)
        extra_context:    Additional context from the user

    Returns:
        {
            "diagnosis": <agent's final JSON diagnosis>,
            "messages": <full message history>,
            "tool_calls": [list of tools the agent invoked],
        }
    """
    agent = _build_agent()

    # Build the initial user message
    parts = [f"Debug this dbt project."]
    parts.append(f"Manifest path: {manifest_path}")
    if run_results_path:
        parts.append(f"Run results path: {run_results_path}")
    if model_name:
        parts.append(f"Focus on model: {model_name}")
    if extra_context:
        parts.append(f"Additional context: {extra_context}")

    user_message = "\n".join(parts)

    # Run the agent
    result = agent.invoke({
        "messages": [HumanMessage(content=user_message)],
    })

    # Extract results
    messages = result.get("messages", [])
    tool_calls_used = _extract_tool_names(messages)
    diagnosis = _extract_diagnosis(messages)

    return {
        "diagnosis": diagnosis,
        "messages": messages,
        "tool_calls": tool_calls_used,
    }


def run_agent_stream(
    manifest_path: str,
    run_results_path: str = "",
    model_name: str | None = None,
    extra_context: str = "",
):
    """Stream the agent's execution step by step.

    Yields dicts with the current step info for real-time display.
    Each yield contains either a tool call or the agent's thinking.

    Usage:
        for step in run_agent_stream(manifest_path="..."):
            print(step["type"], step.get("tool"), step.get("content", "")[:100])
    """
    agent = _build_agent()

    parts = [f"Debug this dbt project."]
    parts.append(f"Manifest path: {manifest_path}")
    if run_results_path:
        parts.append(f"Run results path: {run_results_path}")
    if model_name:
        parts.append(f"Focus on model: {model_name}")
    if extra_context:
        parts.append(f"Additional context: {extra_context}")

    user_message = "\n".join(parts)

    for chunk in agent.stream({
        "messages": [HumanMessage(content=user_message)],
    }):
        # Each chunk is {node_name: {messages: [...]}}
        for node_name, node_output in chunk.items():
            msgs = node_output.get("messages", [])
            for msg in msgs:
                if isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            yield {
                                "type": "tool_call",
                                "tool": tc["name"],
                                "args": tc["args"],
                                "node": node_name,
                            }
                    elif msg.content:
                        yield {
                            "type": "agent_response",
                            "content": msg.content,
                            "node": node_name,
                        }
                elif isinstance(msg, ToolMessage):
                    yield {
                        "type": "tool_result",
                        "tool": msg.name,
                        "content": msg.content[:500] if msg.content else "",
                        "node": node_name,
                    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_tool_names(messages: list) -> list[str]:
    """Extract the list of tool names the agent called."""
    tools = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                tools.append(tc["name"])
    return tools


def _find_json_block(text: str) -> str | None:
    """Find the first balanced JSON object in a blob of text.

    Claude sometimes adds preamble like 'Now I have complete evidence...'
    before the JSON.  A simple regex can fail on nested braces, so we
    walk character-by-character tracking brace depth (while ignoring
    braces inside string literals).

    Returns the JSON substring, or None if no balanced block is found.
    """
    depth = 0
    start = None
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start : i + 1]
    return None


def _extract_diagnosis(messages: list) -> dict | str:
    """Extract the agent's final diagnosis from the last AI message.

    Handles several messy output formats:
      1. Pure JSON                               → parse directly
      2. JSON wrapped in ```json``` fences       → strip fences, parse
      3. Prose preamble + JSON                   → find balanced {...} block
      4. Nothing parseable                       → return raw text
    """
    import re

    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            content = msg.content.strip()

            # Attempt 1: strip markdown fences and try parsing
            clean = re.sub(r"^```(?:json)?\s*", "", content, flags=re.MULTILINE)
            clean = re.sub(r"\s*```$", "", clean.strip(), flags=re.MULTILINE)
            try:
                return json.loads(clean)
            except (json.JSONDecodeError, ValueError):
                pass

            # Attempt 2: find a balanced JSON block anywhere in the content
            # (handles prose preamble like "Here is my diagnosis: { ... }")
            json_block = _find_json_block(content)
            if json_block:
                try:
                    return json.loads(json_block)
                except (json.JSONDecodeError, ValueError):
                    pass

            # Give up — return the raw text so the UI can at least display it
            return content

    return "No diagnosis produced."
