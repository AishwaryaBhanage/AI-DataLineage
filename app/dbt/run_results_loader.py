"""
dbt Run Results Loader
Reads target/run_results.json and returns typed Python objects.

run_results.json is produced by `dbt run`, `dbt build`, or `dbt test`.
It contains one entry per node that was executed — with the outcome
(pass / error / skip / warn), error messages, compiled SQL, and
per-step timing breakdowns.

This module is PURE INGESTION — it reads and structures, it does not
analyse or debug.

Usage:
    results = load_run_results("path/to/target/run_results.json")
    for failure in results.failed():
        print(failure.model_name, failure.error_message)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# ── Dataclasses ──────────────────────────────────────────────────────────────

class Status:
    """Constants for the status values dbt writes to run_results.json.

    Models use:  success, error, skipped
    Tests use:   pass, fail, warn, error, skipped
    """
    SUCCESS = "success"
    ERROR   = "error"
    SKIPPED = "skipped"
    PASS    = "pass"     # tests only
    FAIL    = "fail"     # tests only
    WARN    = "warn"     # tests only


@dataclass(frozen=True)
class RunResultMetadata:
    """Top-level metadata about the dbt invocation that produced this file."""
    dbt_version: str
    generated_at: str
    command: str            # "run", "build", "test" — extracted from args.which
    elapsed_time: float     # total wall-clock seconds for the entire run

    def to_dict(self) -> dict:
        return {
            "dbt_version": self.dbt_version,
            "generated_at": self.generated_at,
            "command": self.command,
            "elapsed_time": round(self.elapsed_time, 3),
        }


@dataclass(frozen=True)
class TimingEntry:
    """One step in the timing breakdown (compile or execute)."""
    name: str               # "compile" or "execute"
    started_at: str         # ISO timestamp
    completed_at: str       # ISO timestamp
    duration_seconds: float # computed: completed - started

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 4),
        }


@dataclass(frozen=True)
class NodeResult:
    """The execution result for a single dbt node (model, test, snapshot, etc.).

    Key fields:
      status        — "success", "error", "skipped" (models);
                      "pass", "fail", "warn" (tests)
      error_message — full error text including the "Runtime Error in model ..."
                      prefix.  Empty string for passing nodes.
      compiled_sql  — the rendered SQL that was sent to the warehouse.
                      None if compilation itself failed.
      model_name    — short name extracted from unique_id
                      e.g. "customer_revenue" from "model.dbt_demo.customer_revenue"
      node_type     — "model", "test", "snapshot", "seed" — extracted from unique_id
    """
    unique_id: str
    model_name: str                 # extracted short name
    node_type: str                  # "model", "test", "snapshot", "seed"
    status: str
    error_message: str              # empty string if no error
    compiled_sql: str | None
    execution_time_seconds: float
    timing: list[TimingEntry]
    was_compiled: bool
    adapter_response: dict
    relation_name: str              # e.g. '"dev"."main"."raw_orders"'
    failures: int | None            # test-only: number of failing rows

    @property
    def is_error(self) -> bool:
        return self.status in (Status.ERROR, Status.FAIL)

    @property
    def is_success(self) -> bool:
        return self.status in (Status.SUCCESS, Status.PASS)

    @property
    def is_skipped(self) -> bool:
        return self.status == Status.SKIPPED

    @property
    def is_model(self) -> bool:
        return self.node_type == "model"

    @property
    def is_test(self) -> bool:
        return self.node_type == "test"

    @property
    def compile_time_seconds(self) -> float:
        """Duration of the compile step, or 0 if no timing data."""
        for t in self.timing:
            if t.name == "compile":
                return t.duration_seconds
        return 0.0

    @property
    def execute_time_seconds(self) -> float:
        """Duration of the execute step, or 0 if no timing data."""
        for t in self.timing:
            if t.name == "execute":
                return t.duration_seconds
        return 0.0

    def to_dict(self) -> dict:
        return {
            "unique_id": self.unique_id,
            "model_name": self.model_name,
            "node_type": self.node_type,
            "status": self.status,
            "error_message": self.error_message,
            "compiled_sql": self.compiled_sql,
            "execution_time_seconds": round(self.execution_time_seconds, 4),
            "compile_time_seconds": round(self.compile_time_seconds, 4),
            "execute_time_seconds": round(self.execute_time_seconds, 4),
            "was_compiled": self.was_compiled,
            "adapter_response": self.adapter_response,
            "relation_name": self.relation_name,
            "failures": self.failures,
        }


@dataclass
class RunResults:
    """The complete parsed run_results.json.

    Provides filtering helpers to quickly find failures, successes,
    and specific nodes.
    """
    metadata: RunResultMetadata
    results: list[NodeResult]

    def failed(self) -> list[NodeResult]:
        """All nodes that errored or failed."""
        return [r for r in self.results if r.is_error]

    def succeeded(self) -> list[NodeResult]:
        """All nodes that passed."""
        return [r for r in self.results if r.is_success]

    def skipped(self) -> list[NodeResult]:
        """All nodes that were skipped."""
        return [r for r in self.results if r.is_skipped]

    def get_by_name(self, model_name: str) -> NodeResult | None:
        """Look up a result by short model name."""
        for r in self.results:
            if r.model_name == model_name:
                return r
        return None

    def get_by_id(self, unique_id: str) -> NodeResult | None:
        """Look up a result by full unique_id."""
        for r in self.results:
            if r.unique_id == unique_id:
                return r
        return None

    def models_only(self) -> list[NodeResult]:
        """Filter to model results only (excludes tests, snapshots, seeds)."""
        return [r for r in self.results if r.is_model]

    def tests_only(self) -> list[NodeResult]:
        """Filter to test results only."""
        return [r for r in self.results if r.is_test]

    def summary(self) -> dict:
        """Aggregate counts by status.

        Example:
            {"total": 3, "success": 2, "error": 1, "skipped": 0, "warn": 0}
        """
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return {
            "total": len(self.results),
            **counts,
        }

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary(),
        }


# ── Parsing functions ────────────────────────────────────────────────────────

def _parse_timing(raw_timing: list[dict]) -> list[TimingEntry]:
    """Parse the timing array from a single result entry.

    Each entry has {name, started_at, completed_at}.
    We compute duration_seconds from the ISO timestamps.
    """
    entries: list[TimingEntry] = []
    for t in raw_timing:
        started = t.get("started_at", "")
        completed = t.get("completed_at", "")
        duration = _iso_diff_seconds(started, completed)
        entries.append(TimingEntry(
            name=t.get("name", ""),
            started_at=started,
            completed_at=completed,
            duration_seconds=duration,
        ))
    return entries


def _iso_diff_seconds(start_iso: str, end_iso: str) -> float:
    """Compute the difference in seconds between two ISO timestamps.
    Returns 0.0 if either timestamp is missing or unparseable."""
    if not start_iso or not end_iso:
        return 0.0
    try:
        from datetime import datetime, timezone
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
        start = datetime.strptime(start_iso, fmt).replace(tzinfo=timezone.utc)
        end = datetime.strptime(end_iso, fmt).replace(tzinfo=timezone.utc)
        return (end - start).total_seconds()
    except (ValueError, TypeError):
        return 0.0


def _extract_node_type(unique_id: str) -> str:
    """Extract node type from unique_id.

    Examples:
        "model.dbt_demo.stg_orders" -> "model"
        "test.dbt_demo.not_null_id"  -> "test"
        "snapshot.dbt_demo.orders"   -> "snapshot"
        "seed.dbt_demo.countries"    -> "seed"
    """
    return unique_id.split(".")[0] if "." in unique_id else "unknown"


def _extract_model_name(unique_id: str) -> str:
    """Extract the short name from a unique_id.

    Examples:
        "model.dbt_demo.stg_orders"                    -> "stg_orders"
        "test.dbt_demo.not_null_stg_orders_order_id"   -> "not_null_stg_orders_order_id"
    """
    parts = unique_id.split(".")
    return parts[-1] if parts else unique_id


def _parse_node_result(raw: dict) -> NodeResult:
    """Parse a single result entry from the results array."""
    unique_id = raw.get("unique_id", "")

    # Error message: dbt puts the full error in 'message' for failures.
    # For successes, 'message' is something like "OK" or "CREATE TABLE".
    status = raw.get("status", "")
    error_message = ""
    if status in (Status.ERROR, Status.FAIL):
        error_message = raw.get("message", "")

    return NodeResult(
        unique_id=unique_id,
        model_name=_extract_model_name(unique_id),
        node_type=_extract_node_type(unique_id),
        status=status,
        error_message=error_message,
        compiled_sql=raw.get("compiled_code"),
        execution_time_seconds=raw.get("execution_time", 0.0),
        timing=_parse_timing(raw.get("timing", [])),
        was_compiled=raw.get("compiled", False),
        adapter_response=raw.get("adapter_response", {}),
        relation_name=raw.get("relation_name", ""),
        failures=raw.get("failures"),
    )


# ── Public API ───────────────────────────────────────────────────────────────

def load_run_results(path: str | Path) -> RunResults:
    """Load and parse a dbt run_results.json file.

    Args:
        path: Path to target/run_results.json

    Returns:
        A fully parsed RunResults object with all node outcomes,
        timing, and error messages.

    Raises:
        FileNotFoundError: If run_results.json does not exist.
            This usually means the user ran `dbt compile` instead
            of `dbt run`.
        ValueError: If the file is not valid JSON.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"run_results.json not found at {path}\n"
            "This file is produced by `dbt run` or `dbt build`, "
            "not by `dbt compile`.\n"
            "Run `dbt run` inside your dbt project first."
        )

    with open(path) as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"run_results.json is not valid JSON: {e}")

    # ── Metadata ─────────────────────────────────────────────────────
    raw_meta = raw.get("metadata", {})
    command = raw.get("args", {}).get("which", "unknown")

    metadata = RunResultMetadata(
        dbt_version=raw_meta.get("dbt_version", "unknown"),
        generated_at=raw_meta.get("generated_at", ""),
        command=command,
        elapsed_time=raw.get("elapsed_time", 0.0),
    )

    # ── Results ──────────────────────────────────────────────────────
    results = [_parse_node_result(r) for r in raw.get("results", [])]

    return RunResults(metadata=metadata, results=results)
