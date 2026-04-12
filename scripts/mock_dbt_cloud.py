"""
Mock dbt Cloud API server — for local testing of the dbt Cloud integration.

Mimics the dbt Cloud Admin API v2 endpoints that our DbtCloudClient uses.
Returns the local dbt_demo/target/*.json files regardless of which
account/job/run ID is requested.  Accepts any Bearer token.

Why this exists:
  Signing up for dbt Cloud and configuring a warehouse takes 20+ minutes.
  This mock lets you test the integration end-to-end in 5 seconds with
  zero external dependencies.

─────────────────────────────────────────────────────────────────────────────
USAGE
─────────────────────────────────────────────────────────────────────────────

1. Start the mock server (in one terminal):

     python scripts/mock_dbt_cloud.py

   It listens on http://localhost:9090

2. Start your backend pointing at the mock (in another terminal):

     DBT_CLOUD_BASE_URL=http://localhost:9090 \\
     API_KEYS=dl_dev_local_key \\
     REQUIRE_API_KEY=true \\
     CORS_ORIGINS=http://localhost:5173 \\
     .venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8000

3. Open http://localhost:5173 → Debug page → select "dbt Cloud" source

4. Paste this fake URL:
     http://localhost:9090/deploy/12345/projects/67890/jobs/111

5. Paste any string as the API token (mock doesn't check)

6. Click "Analyze" — should work exactly like real dbt Cloud.

─────────────────────────────────────────────────────────────────────────────
ENDPOINTS
─────────────────────────────────────────────────────────────────────────────

GET /                                                         status info
GET /api/v2/accounts/{account_id}/runs/                        list runs
GET /api/v2/accounts/{account_id}/runs/{run_id}/               run status
GET /api/v2/accounts/{account_id}/runs/{run_id}/artifacts/manifest.json
GET /api/v2/accounts/{account_id}/runs/{run_id}/artifacts/run_results.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse

# Resolve the path to the real dbt_demo artifacts regardless of where
# this script is run from
REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "dbt_demo" / "target" / "manifest.json"
RUN_RESULTS_PATH = REPO_ROOT / "dbt_demo" / "target" / "run_results.json"


app = FastAPI(
    title="Mock dbt Cloud API",
    description=(
        "Fake dbt Cloud server for local testing. "
        "Returns local dbt_demo artifacts for any account/run/job ID."
    ),
    version="1.0.0",
)


# ── Root / info ──────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "Mock dbt Cloud API",
        "version": "1.0.0",
        "real_files_served": {
            "manifest.json": str(MANIFEST_PATH),
            "run_results.json": str(RUN_RESULTS_PATH),
        },
        "try_this_url_in_the_app": (
            "http://localhost:9090/deploy/12345/projects/67890/jobs/111"
        ),
        "endpoints": [
            "GET /api/v2/accounts/{id}/runs/",
            "GET /api/v2/accounts/{id}/runs/{run}/",
            "GET /api/v2/accounts/{id}/runs/{run}/artifacts/manifest.json",
            "GET /api/v2/accounts/{id}/runs/{run}/artifacts/run_results.json",
        ],
    }


# ── Artifacts ───────────────────────────────────────────────────────────────

def _check_file(path: Path) -> None:
    if not path.exists():
        raise HTTPException(
            status_code=500,
            detail=(
                f"Mock source file not found: {path}\n"
                "Run `dbt run --profiles-dir .` inside dbt_demo/ first."
            ),
        )


@app.get(
    "/api/v2/accounts/{account_id}/runs/{run_id}/artifacts/manifest.json"
)
def get_manifest(account_id: str, run_id: str):
    """Return the local manifest.json regardless of account/run IDs."""
    _check_file(MANIFEST_PATH)
    with open(MANIFEST_PATH) as f:
        data = json.load(f)
    return JSONResponse(data)


@app.get(
    "/api/v2/accounts/{account_id}/runs/{run_id}/artifacts/run_results.json"
)
def get_run_results(account_id: str, run_id: str):
    """Return the local run_results.json regardless of account/run IDs."""
    _check_file(RUN_RESULTS_PATH)
    with open(RUN_RESULTS_PATH) as f:
        data = json.load(f)
    return JSONResponse(data)


# ── Runs list / status (used by fetch_latest_artifacts) ────────────────────

@app.get("/api/v2/accounts/{account_id}/runs/")
def list_runs(
    account_id: str,
    limit: int = 10,
    job_definition_id: str | None = None,
    order_by: str = "-finished_at",
):
    """Return a fake list with a single "completed" run.

    The DbtCloudClient.fetch_latest_artifacts() flow calls this endpoint
    first, then calls get_manifest with the returned run ID.
    """
    fake_run_id = 999001
    return {
        "data": [
            {
                "id": fake_run_id,
                "job_definition_id": int(job_definition_id) if job_definition_id else 789,
                "status": 10,  # 10 = success
                "status_humanized": "Success",
                "finished_at": "2024-04-11T12:00:00.000Z",
                "started_at": "2024-04-11T11:59:15.000Z",
                "duration": "45",
                "duration_humanized": "45 seconds",
                "git_sha": "abc123def456",
                "git_branch": "main",
            }
        ],
        "status": {
            "code": 200,
            "is_success": True,
            "user_message": "Success!",
        },
    }


@app.get("/api/v2/accounts/{account_id}/runs/{run_id}/")
def get_run_status(account_id: str, run_id: str):
    """Return fake status for a specific run."""
    return {
        "data": {
            "id": int(run_id) if run_id.isdigit() else 999001,
            "job_definition_id": 789,
            "status": 10,
            "status_humanized": "Success",
            "finished_at": "2024-04-11T12:00:00.000Z",
            "duration": "45",
            "git_sha": "abc123def456",
        }
    }


# ── Entry point ─────────────────────────────────────────────────────────────

def main():
    import uvicorn

    # Pre-flight check: warn if artifacts aren't where we expect them
    if not MANIFEST_PATH.exists():
        print(f"⚠  manifest.json NOT FOUND at {MANIFEST_PATH}")
        print(f"   Run `dbt run --profiles-dir .` inside dbt_demo/ first.")
        print()
    if not RUN_RESULTS_PATH.exists():
        print(f"⚠  run_results.json NOT FOUND at {RUN_RESULTS_PATH}")
        print()

    print("═══════════════════════════════════════════════════════════════")
    print("  Mock dbt Cloud API — serving local dbt_demo artifacts")
    print("═══════════════════════════════════════════════════════════════")
    print()
    print(f"  manifest.json    -> {MANIFEST_PATH}")
    print(f"  run_results.json -> {RUN_RESULTS_PATH}")
    print()
    print("  Test URL to paste into the app's Debug page (dbt Cloud source):")
    print("    http://localhost:9090/deploy/12345/projects/67890/jobs/111")
    print()
    print("  Don't forget to start the backend with:")
    print("    DBT_CLOUD_BASE_URL=http://localhost:9090 uvicorn ...")
    print()
    print("  Starting on http://localhost:9090 ...")
    print("═══════════════════════════════════════════════════════════════")
    print()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9090,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
