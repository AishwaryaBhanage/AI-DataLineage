# DataLineage AI — API Reference

AI-powered debugger for broken dbt/SQL pipelines.

**Base URL (beta):** `https://your-app.us-east-1.awsapprunner.com`

---

## Authentication

All endpoints under `/api/v1/*` require a bearer token, except `/api/v1/health`.

```
Authorization: Bearer dl_xxxxxxxxxxxxxxxx
```

If you don't have a key yet, ask Aishwarya.

**Wrong or missing key:**
```json
{ "detail": "Missing Authorization header. Send: Authorization: Bearer <api_key>" }
```

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /api/v1/debug` (fast mode) | 10 requests/minute |
| `POST /api/v1/debug` (agentic mode) | 3 requests/minute |
| `GET /api/v1/models` | 30 requests/minute |
| `GET /api/v1/health` | unlimited |

When you exceed the limit, you get HTTP `429` with a `Retry-After: 60` header.

---

## Endpoints

### `GET /api/v1/health`

Public — no auth required. Returns service status and dependency checks.

```bash
curl https://your-app.../api/v1/health
```

**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "modes": ["fast", "agentic"],
  "checks": {
    "anthropic_key_configured": true,
    "filesystem_writable": true,
    "core_modules_loaded": true
  }
}
```

---

### `POST /api/v1/debug`

The main endpoint. Analyzes a broken dbt model and returns a diagnosis.

**Two modes:**
- `fast` — runs inline, returns full result synchronously. ~1-3 seconds.
  Cached by input hash for 1 hour.
- `agentic` — runs asynchronously. Returns 202 + `job_id` immediately.
  Poll `GET /api/v1/jobs/{job_id}` for the result. Typical completion: 15-30s.

**Caching:** fast mode responses include a `cached: true/false` field.
Identical requests (same manifest/run_results/model/mode) within 1 hour
return the cached result instantly.

**Two artifact sources:**
- `local` — files on the server (good for the bundled `dbt_demo` or your own paths)
- `cloud` — fetch from dbt Cloud API using your job's run ID

#### Example 1 — Fast mode, local artifacts

```bash
curl -X POST https://your-app.../api/v1/debug \
  -H "Authorization: Bearer dl_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "local",
    "manifest_path": "dbt_demo/target/manifest.json",
    "run_results_path": "dbt_demo/target/run_results.json",
    "mode": "fast",
    "use_llm": false
  }'
```

**Response (truncated):**
```json
{
  "mode": "fast",
  "broken_model": "customer_revenue",
  "parsed_sql": { "tables": ["stg_orders"], "columns": [...], "aggregations": [...] },
  "parsed_error": { "error_type": "missing_column", "column": "amount", "candidates": ["amount_total"] },
  "lineage": { "nodes": [...], "edges": [...] },
  "rule_hits": [
    {
      "cause": "column_renamed_upstream",
      "title": "Column 'amount' was renamed in upstream model 'stg_orders'",
      "confidence": 0.95,
      "fix_hint": "Replace 'amount' with 'amount_total'"
    }
  ],
  "query_is_valid": false,
  "corrected_sql": "select customer_id, sum(amount_total) ...",
  "errors": []
}
```

#### Example 2 — Agentic mode (LLM-driven)

```bash
curl -X POST https://your-app.../api/v1/debug \
  -H "Authorization: Bearer dl_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "local",
    "manifest_path": "dbt_demo/target/manifest.json",
    "run_results_path": "dbt_demo/target/run_results.json",
    "mode": "agentic"
  }'
```

**Response:**
```json
{
  "mode": "agentic",
  "diagnosis": {
    "root_cause": "Column 'amount' was renamed to 'amount_total' upstream",
    "explanation": "The customer_revenue model references a column 'amount' that no longer exists in stg_orders...",
    "corrected_sql": "select customer_id, sum(amount_total) ...",
    "confidence_score": 0.95,
    "validation_steps": [
      "Run dbt compile --select customer_revenue",
      "Run dbt run --select customer_revenue"
    ]
  },
  "tools_used": [
    "ingest_dbt_artifacts",
    "analyze_error",
    "get_model_sql",
    "run_rule_engine"
  ]
}
```

#### Example 3 — From dbt Cloud

```bash
curl -X POST https://your-app.../api/v1/debug \
  -H "Authorization: Bearer dl_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "cloud",
    "dbt_cloud_token": "dbt_cloud_...",
    "dbt_cloud_account_id": "12345",
    "dbt_cloud_run_id": "67890",
    "mode": "fast"
  }'
```

#### Request schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | enum | yes | `"local"` or `"cloud"` |
| `manifest_path` | string | for local | Path to `target/manifest.json` |
| `run_results_path` | string | for local | Path to `target/run_results.json` |
| `dbt_cloud_token` | string | for cloud | dbt Cloud API token |
| `dbt_cloud_account_id` | string | for cloud | dbt Cloud account ID |
| `dbt_cloud_run_id` | string | for cloud | Specific run ID |
| `dbt_cloud_job_id` | string | for cloud | Or job ID (uses latest run) |
| `model_name` | string | no | Specific model to debug. Auto-detected from failures if omitted |
| `mode` | enum | no | `"fast"` (default) or `"agentic"` |
| `use_llm` | bool | no | In fast mode, call Claude after rules. Default `true` |

---

### `GET /api/v1/jobs/{job_id}`

Poll the status of a job. Used after submitting an agentic debug request.

```bash
curl -H "Authorization: Bearer dl_xxx" \
  https://your-app.../api/v1/jobs/job_abc123def456
```

**Response (while running):**
```json
{
  "id": "job_abc123def456",
  "status": "running",
  "mode": "agentic",
  "broken_model": null,
  "result": null,
  "error": null,
  "created_at": "2026-04-11T03:09:41.418085",
  "started_at": "2026-04-11T03:09:41.523000",
  "completed_at": null,
  "duration_ms": null
}
```

**Response (completed):**
```json
{
  "id": "job_abc123def456",
  "status": "completed",
  "mode": "agentic",
  "broken_model": "customer_revenue",
  "result": {
    "mode": "agentic",
    "diagnosis": { "root_cause": "...", "corrected_sql": "...", ... },
    "tools_used": ["ingest_dbt_artifacts", "run_rule_engine", ...]
  },
  "created_at": "2026-04-11T03:09:41.418085",
  "started_at": "2026-04-11T03:09:41.523000",
  "completed_at": "2026-04-11T03:10:04.647901",
  "duration_ms": 23228
}
```

**Status values:** `queued` → `running` → `completed` / `failed` / `cancelled`

Poll every 2-3 seconds until status is `completed` or `failed`.

---

### `GET /api/v1/jobs`

List recent jobs for your API key. Newest first.

```bash
curl -H "Authorization: Bearer dl_xxx" \
  "https://your-app.../api/v1/jobs?limit=20"
```

**Response:**
```json
{
  "count": 2,
  "jobs": [
    { "id": "job_abc...", "status": "completed", "mode": "fast", ... },
    { "id": "job_def...", "status": "running", "mode": "agentic", ... }
  ]
}
```

---

### `GET /api/v1/usage`

Get your API key's usage statistics.

```bash
curl -H "Authorization: Bearer dl_xxx" \
  "https://your-app.../api/v1/usage?days=7"
```

**Response:**
```json
{
  "api_key_prefix": "dl_test_ab...",
  "period_days": 7,
  "total_requests": 42,
  "avg_duration_ms": 234,
  "by_endpoint": {
    "/api/v1/debug": 28,
    "/api/v1/jobs": 12,
    "/api/v1/usage": 2
  },
  "by_status_code": {
    "200": 40,
    "429": 2
  },
  "daily_quota": 0,
  "requests_today": 15
}
```

---

### `GET /api/v1/models`

List all models in a manifest.

```bash
curl -H "Authorization: Bearer dl_xxx" \
  "https://your-app.../api/v1/models?manifest_path=dbt_demo/target/manifest.json"
```

**Response:**
```json
{
  "project": "dbt_demo",
  "adapter": "duckdb",
  "total_models": 3,
  "models": [
    {
      "name": "customer_revenue",
      "file_path": "models/customer_revenue.sql",
      "materialized": "table",
      "upstream": ["stg_orders"],
      "downstream": []
    }
  ]
}
```

---

## Error responses

All errors return JSON with this shape:

```json
{
  "error": "rate_limit_exceeded",
  "detail": "Too many requests. Limit: 10/minute. Try again shortly."
}
```

| Status | Meaning |
|--------|---------|
| `400` | Bad request (missing required field, invalid path) |
| `401` | Missing or invalid API key |
| `413` | Request body too large (>5MB) |
| `429` | Rate limit exceeded |
| `500` | Unexpected server error (check `request_id` header for support) |
| `502` | dbt Cloud API error |
| `503` | Service misconfigured |

Every response includes an `X-Request-ID` header you can quote when reporting bugs.

---

## Interactive docs

When the server runs in `development` mode, interactive Swagger docs are available at:

- **Swagger UI:** `https://your-app.../docs`
- **ReDoc:** `https://your-app.../redoc`

(These are disabled in production for security.)

---

## Quick start with Python

```python
import requests

API_URL = "https://your-app.us-east-1.awsapprunner.com"
API_KEY = "dl_xxxxxxxxxxxxxxxx"

response = requests.post(
    f"{API_URL}/api/v1/debug",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "source": "local",
        "manifest_path": "dbt_demo/target/manifest.json",
        "run_results_path": "dbt_demo/target/run_results.json",
        "mode": "fast",
    },
)

result = response.json()
print(f"Broken model: {result['broken_model']}")
print(f"Top fix: {result['rule_hits'][0]['fix_hint']}")
print(f"Corrected SQL:\n{result['corrected_sql']}")
```

---

## Feedback

This is a beta. Your feedback shapes the next version. Please report:

- **Bugs** — what broke, what request you sent, the `X-Request-ID` from the response
- **Slow requests** — anything over 30s in fast mode or 60s in agentic
- **Wrong diagnoses** — describe the actual root cause and we'll add a rule
- **Wishes** — what would you want it to do?

Reach out: [your contact info]
