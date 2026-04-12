"""
dbt Cloud Client
Fetches artifacts (manifest.json, run_results.json) from the dbt Cloud
Admin API and saves them locally so the rest of the pipeline can consume
them as normal files.

dbt Cloud API docs:
  GET /api/v2/accounts/{account_id}/runs/{run_id}/artifacts/{path}
  GET /api/v2/accounts/{account_id}/runs/  (list runs for a job)

Authentication:
  Header: Authorization: Bearer <dbt_cloud_api_token>
  Tokens: Service Account tokens or Personal Access Tokens from
          dbt Cloud → Account Settings → API Access.

Usage:
    client = DbtCloudClient(api_token="dbt_...", account_id="12345")

    # Fetch from a specific run
    paths = client.fetch_artifacts(run_id="67890")
    # paths.manifest_path  → "/tmp/dbt_cloud_67890/manifest.json"
    # paths.run_results_path → "/tmp/dbt_cloud_67890/run_results.json"

    # Fetch from the latest run of a job
    paths = client.fetch_latest_artifacts(job_id="111")

    # List recent runs for a job
    runs = client.list_runs(job_id="111", limit=5)
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ArtifactPaths:
    """Local file paths where downloaded artifacts were saved."""
    manifest_path: str
    run_results_path: str
    run_id: str

    def to_dict(self) -> dict:
        return {
            "manifest_path": self.manifest_path,
            "run_results_path": self.run_results_path,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class RunInfo:
    """Summary of a single dbt Cloud run."""
    run_id: int
    job_id: int
    status: int             # 10=success, 20=error, 30=cancelled
    status_label: str       # human-readable
    finished_at: str
    duration_seconds: int
    git_sha: str

    @property
    def is_success(self) -> bool:
        return self.status == 10

    @property
    def is_error(self) -> bool:
        return self.status == 20

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "status": self.status,
            "status_label": self.status_label,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "git_sha": self.git_sha,
        }


# Status code mapping from dbt Cloud API
_STATUS_LABELS = {
    1: "queued",
    2: "starting",
    3: "running",
    10: "success",
    20: "error",
    30: "cancelled",
}


# ── Client ───────────────────────────────────────────────────────────────────

class DbtCloudClient:
    """HTTP client for the dbt Cloud Admin API v2.

    All methods are synchronous (blocking) for simplicity.
    Timeouts are generous (30s) since artifact downloads can be large.
    """

    def __init__(
        self,
        api_token: str,
        account_id: str,
        base_url: str = "https://cloud.getdbt.com",
    ):
        if not api_token:
            raise ValueError(
                "dbt Cloud API token is required. "
                "Set DBT_CLOUD_API_TOKEN in your .env file. "
                "Generate one at: dbt Cloud → Account Settings → API Access"
            )
        if not account_id:
            raise ValueError(
                "dbt Cloud account ID is required. "
                "Set DBT_CLOUD_ACCOUNT_ID in your .env file. "
                "Find it in your dbt Cloud URL: cloud.getdbt.com/deploy/{account_id}"
            )

        self._account_id = account_id
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    # ── Public API ───────────────────────────────────────────────────────

    def fetch_artifacts(
        self,
        run_id: str,
        output_dir: str | None = None,
    ) -> ArtifactPaths:
        """Download manifest.json and run_results.json from a specific run.

        Args:
            run_id:     The dbt Cloud run ID
            output_dir: Where to save files (default: temp directory)

        Returns:
            ArtifactPaths with local file paths

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx status
            ValueError: If artifacts are not available (run still in progress)
        """
        if not output_dir:
            output_dir = tempfile.mkdtemp(prefix=f"dbt_cloud_{run_id}_")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        manifest_path = str(out / "manifest.json")
        run_results_path = str(out / "run_results.json")

        self._download_artifact(run_id, "manifest.json", manifest_path)
        self._download_artifact(run_id, "run_results.json", run_results_path)

        return ArtifactPaths(
            manifest_path=manifest_path,
            run_results_path=run_results_path,
            run_id=run_id,
        )

    def fetch_latest_artifacts(
        self,
        job_id: str,
        output_dir: str | None = None,
    ) -> ArtifactPaths:
        """Find the most recent completed run of a job, then download its artifacts.

        Args:
            job_id:     The dbt Cloud job ID
            output_dir: Where to save files (default: temp directory)

        Returns:
            ArtifactPaths with local file paths

        Raises:
            ValueError: If no completed run is found for this job
        """
        runs = self.list_runs(job_id=job_id, limit=10)

        # Find the most recent completed (success or error) run
        completed = [r for r in runs if r.status in (10, 20)]
        if not completed:
            raise ValueError(
                f"No completed runs found for job {job_id}. "
                "The job may still be running or has never been executed."
            )

        latest = completed[0]  # already sorted by recency
        return self.fetch_artifacts(
            run_id=str(latest.run_id),
            output_dir=output_dir,
        )

    def list_runs(
        self,
        job_id: str | None = None,
        limit: int = 10,
    ) -> list[RunInfo]:
        """List recent runs, optionally filtered by job ID.

        Returns runs sorted by most recent first.
        """
        url = f"{self._base}/api/v2/accounts/{self._account_id}/runs/"
        params: dict = {
            "limit": limit,
            "order_by": "-finished_at",
        }
        if job_id:
            params["job_definition_id"] = job_id

        resp = self._client.get(url, params=params)
        resp.raise_for_status()

        data = resp.json().get("data", [])
        runs: list[RunInfo] = []
        for r in data:
            status_code = r.get("status", 0)
            runs.append(RunInfo(
                run_id=r["id"],
                job_id=r.get("job_definition_id", 0),
                status=status_code,
                status_label=_STATUS_LABELS.get(status_code, "unknown"),
                finished_at=r.get("finished_at", ""),
                duration_seconds=int(r.get("duration", "0") or 0),
                git_sha=r.get("git_sha", ""),
            ))

        return runs

    def get_run_status(self, run_id: str) -> RunInfo:
        """Get the status of a specific run."""
        url = f"{self._base}/api/v2/accounts/{self._account_id}/runs/{run_id}/"
        resp = self._client.get(url)
        resp.raise_for_status()

        r = resp.json().get("data", {})
        status_code = r.get("status", 0)
        return RunInfo(
            run_id=r["id"],
            job_id=r.get("job_definition_id", 0),
            status=status_code,
            status_label=_STATUS_LABELS.get(status_code, "unknown"),
            finished_at=r.get("finished_at", ""),
            duration_seconds=int(r.get("duration", "0") or 0),
            git_sha=r.get("git_sha", ""),
        )

    # ── Private helpers ──────────────────────────────────────────────────

    def _download_artifact(
        self, run_id: str, artifact_name: str, save_path: str
    ) -> None:
        """Download a single artifact file from a run."""
        url = (
            f"{self._base}/api/v2/accounts/{self._account_id}"
            f"/runs/{run_id}/artifacts/{artifact_name}"
        )
        resp = self._client.get(url)

        if resp.status_code == 404:
            raise ValueError(
                f"Artifact '{artifact_name}' not found for run {run_id}. "
                "The run may still be in progress, or this artifact "
                "was not generated (e.g. run failed before compilation)."
            )

        resp.raise_for_status()

        with open(save_path, "w") as f:
            # Response is raw JSON — write it directly
            json.dump(resp.json(), f, indent=2)

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
