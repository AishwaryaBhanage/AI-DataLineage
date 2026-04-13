# DataLineage AI — Complete Project Report

**Author**: Aishwarya Bhanage (116556145)
**Course**: LLM Course — Stony Brook University
**Date**: April 2026
**Repository**: https://github.com/AishwaryaBhanage/AI-DataLineage
**Live URL**: http://datali-Publi-qsZNW7jcIFUB-1558367737.us-east-1.elb.amazonaws.com

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Solution Overview](#3-solution-overview)
4. [System Architecture](#4-system-architecture)
5. [How It Works — End to End](#5-how-it-works--end-to-end)
6. [LLM Integration — Core Design](#6-llm-integration--core-design)
7. [Technology Stack](#7-technology-stack)
8. [Backend Implementation](#8-backend-implementation)
9. [Frontend Implementation](#9-frontend-implementation)
10. [Database Layer](#10-database-layer)
11. [dbt Artifact Ingestion](#11-dbt-artifact-ingestion)
12. [dbt Cloud Integration](#12-dbt-cloud-integration)
13. [Security & Authentication](#13-security--authentication)
14. [Deployment Pipeline](#14-deployment-pipeline)
15. [CI/CD with GitHub Actions](#15-cicd-with-github-actions)
16. [Monitoring & Observability](#16-monitoring--observability)
17. [Testing Strategy](#17-testing-strategy)
18. [Demo Scenarios](#18-demo-scenarios)
19. [Cost Analysis](#19-cost-analysis)
20. [Design Decisions & Trade-offs](#20-design-decisions--trade-offs)
21. [Limitations](#21-limitations)
22. [Future Work](#22-future-work)
23. [Project Timeline](#23-project-timeline)
24. [File Structure](#24-file-structure)
25. [How to Run](#25-how-to-run)
26. [References](#26-references)

---

## 1. Executive Summary

DataLineage AI is an LLM-powered debugging tool for broken dbt (data build tool)
data pipelines. When a dbt model fails — typically due to column renames,
missing references, or schema drift across upstream models — data engineers
spend 30-60 minutes manually tracing lineage to find the root cause.

This project automates that process. Given a dbt project's `manifest.json`
and `run_results.json`, the system:

1. Parses the broken SQL and error message using deterministic tools (sqlglot, regex)
2. Reconstructs the full pipeline lineage graph (networkx)
3. Extracts upstream column schemas to build a structured evidence packet
4. Sends ONE Claude API call with the evidence and receives a structured diagnosis
5. Returns the root cause, corrected SQL, confidence score, and validation steps

The entire analysis completes in **~4 seconds** at a cost of **~$0.013 per run**.

For complex cases, an optional **agentic mode** spins up a multi-step ReAct
agent that autonomously decides which tools to call, taking ~25 seconds at
~$0.15 per run.

The system is deployed as a production-grade service on **AWS ECS Fargate**
with a React frontend, FastAPI backend, bearer token authentication, rate
limiting, structured logging, per-user usage tracking, and CI/CD via
GitHub Actions.

---

## 2. Problem Statement

### The pain point

Data engineers and analytics engineers work with dbt (data build tool) to
transform raw warehouse data into clean, analysis-ready models. A typical
dbt project has 50-500 SQL models organized in layers:

```
Raw sources → Staging → Intermediate → Marts → BI dashboards
```

When a model fails, the warehouse returns a single error like:

```
Binder Error: Referenced column "amount" not found in FROM clause!
Candidate bindings: "amount_total", "status", "order_date"
```

The engineer must then:
1. Open the failing model's SQL
2. Identify which column is missing
3. Trace upstream through 3-10 dependency layers
4. Find where the column was renamed, dropped, or never existed
5. Fix the reference
6. Re-run and hope the next error isn't a different root cause

**This process takes 30-60 minutes per failure**, and production dbt projects
can have multiple failures daily. The warehouse only reports ONE error at a
time, so fixing one reveals the next, creating a frustrating iterative cycle.

### Why existing tools don't solve this

| Tool | What it does | Why it's not enough |
|------|-------------|-------------------|
| dbt CLI errors | Shows the warehouse error | Only one error at a time, no root cause analysis |
| dbt docs | Shows lineage graph | Visual only, no reasoning about column-level issues |
| ChatGPT / Claude.ai | Can analyze SQL if you paste it | No access to your manifest, lineage, or upstream schemas |
| Datafold / Elementary | Data observability | Focus on data quality, not SQL debugging |
| SQLFluff | SQL linting | Catches style issues, not semantic column errors |

### The gap

No existing tool combines **lineage awareness** (knowing what upstream models
produce) with **LLM reasoning** (understanding why a column is missing and
how to fix it). This project fills that gap.

---

## 3. Solution Overview

### What the user does

1. Upload their dbt project's `manifest.json` and `run_results.json` (or paste a dbt Cloud URL)
2. Click "Analyze"
3. Receive a complete diagnosis in 4 seconds

### What the system produces

```json
{
  "root_cause": "Column 'amount' was renamed to 'amount_total' in stg_orders",
  "explanation": "The customer_revenue model references 'amount', but the upstream
    stg_orders model publishes this column as 'amount_total'. The rename happened
    in the staging layer where 'price' was aliased to 'amount_total'.",
  "confidence_score": 0.98,
  "corrected_sql": "SELECT customer_id, SUM(amount_total) AS total_revenue ...",
  "affected_columns": ["amount", "amount_total"],
  "validation_steps": [
    "Run dbt compile --select customer_revenue",
    "Run dbt run --select customer_revenue",
    "Verify total_revenue values against raw source data"
  ],
  "hypotheses": [
    {"cause": "column_renamed_upstream", "confidence": 0.98},
    {"cause": "typo_in_reference", "confidence": 0.30}
  ]
}
```

### Two analysis modes

| Mode | How it works | Speed | Cost | When to use |
|------|-------------|-------|------|-------------|
| **Analyze (fast)** | Pre-built evidence → ONE Claude call | ~4 seconds | ~$0.013 | 90% of cases |
| **Deep analysis (agentic)** | Claude autonomously calls 5-10 tools | ~25 seconds | ~$0.15 | Complex multi-layer failures |

---

## 4. System Architecture

### High-level architecture

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                   React Frontend (Vite + Tailwind)              │
  │                                                                  │
  │   Pages: Debug · Jobs · Usage · Models · Settings                │
  │   State: Zustand (settings persisted, results in-memory)         │
  │   DAG: React Flow + dagre auto-layout                            │
  │   HTTP: Axios + TanStack Query + bearer token auth               │
  └──────────────────────┬───────────────────────────────────────────┘
                         │ HTTPS + Authorization: Bearer <key>
                         ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                     FastAPI Backend                              │
  │                                                                  │
  │   Endpoints:                                                     │
  │     POST /api/v1/debug         main analysis (fast + agentic)    │
  │     POST /api/v1/upload        file drag-and-drop upload         │
  │     POST /api/v1/debug/cloud   dbt Cloud integration             │
  │     GET  /api/v1/jobs/{id}     poll async agentic jobs           │
  │     GET  /api/v1/jobs          list job history                  │
  │     GET  /api/v1/usage         per-key usage stats               │
  │     GET  /api/v1/models        list models in a manifest         │
  │     GET  /api/v1/health        health check (public)             │
  │                                                                  │
  │   Middleware:                                                    │
  │     • Bearer token auth (per-key)                                │
  │     • Rate limiting (slowapi — 10/min fast, 3/min agentic)       │
  │     • Structured logging (structlog → JSON)                      │
  │     • Request size limits (50 MB max)                            │
  │     • CORS lockdown                                              │
  │     • Request ID tracking                                        │
  │     • Global exception handler                                   │
  └──────────────────────┬───────────────────────────────────────────┘
                         │
        ┌────────────────┼─────────────────┐
        ▼                ▼                 ▼
  ┌──────────┐    ┌──────────────┐   ┌──────────────┐
  │ LangGraph│    │ SQLite +     │   │ Claude API   │
  │ pipeline │    │ SQLAlchemy   │   │ (Sonnet 4)   │
  │          │    │ async        │   │              │
  │ 5 nodes: │    │              │   │ Fast mode:   │
  │ ingest → │    │ Tables:      │   │  1 call      │
  │ parse  → │    │ • jobs       │   │              │
  │ lineage→ │    │ • usage_log  │   │ Agentic:     │
  │ analyze  │    │ • cache      │   │  5-10 calls  │
  └──────────┘    └──────────────┘   └──────────────┘
```

### Fast mode pipeline (LangGraph)

```
POST /api/v1/debug (mode=fast)
       │
       ▼
  node_ingest ──── load manifest.json + run_results.json
       │           find the failed model
       │           extract upstream column schemas
       │
       ├────────┬────── parallel fan-out
       ▼        ▼
  node_parse_sql   node_parse_error
  (sqlglot)        (regex patterns)
       │        │
       └────┬───┘
            ▼
  node_build_lineage ── networkx DAG from parent_map
            │
            ▼
  node_llm_analyze ──── ONE Claude call with structured evidence
            │           returns: root_cause, corrected_sql,
            │                    confidence, validation_steps
            ▼
           END → cached in DB → returned to client
```

### Agentic mode pipeline (LangGraph ReAct)

```
POST /api/v1/debug (mode=agentic)
       │
       ▼
  Returns 202 + job_id immediately (async)
       │
       ▼ (background task)
  ┌─────────────────────────────────────────────┐
  │  Claude as ReAct coordinator                │
  │                                              │
  │  Available tools:                            │
  │    1. ingest_dbt_artifacts                   │
  │    2. analyze_sql                            │
  │    3. analyze_error                          │
  │    4. get_lineage                            │
  │    5. check_columns_available                │
  │    6. get_model_sql                          │
  │    7. fetch_dbt_cloud_artifacts              │
  │                                              │
  │  Loop:                                       │
  │    Thought → pick a tool → call it           │
  │    → read observation → think again          │
  │    → repeat until diagnosis is ready         │
  └──────────────────┬──────────────────────────┘
                     │
                     ▼
  Client polls GET /api/v1/jobs/{id} every 2 seconds
                     │
                     ▼
  Returns: diagnosis + tool timeline + corrected SQL
```

---

## 5. How It Works — End to End

### Step 1: User uploads artifacts

The user provides two files from their dbt project:
- `target/manifest.json` — the complete project snapshot (all models, SQL,
  dependencies, columns, materializations)
- `target/run_results.json` — the execution report (which models passed,
  which failed, error messages, timing)

These are generated by running `dbt run` or `dbt build`.

### Step 2: Ingestion and failure detection

The `node_ingest` function:
1. Parses `manifest.json` into typed Python objects (`ModelNode`, `SourceNode`)
2. Parses `run_results.json` into `NodeResult` objects with status, error, timing
3. Joins them via `model_resolver` to build a `FailureContext`:
   - The failing model's raw SQL and compiled SQL
   - The error message from the warehouse
   - Every upstream model with its published columns
   - The full lineage chain

### Step 3: Parallel parsing

Two nodes run in parallel (LangGraph fan-out):

**`node_parse_sql`** uses sqlglot to extract:
- Tables referenced
- Columns used
- Aggregation functions (SUM, COUNT, AVG, etc.)
- CTEs (Common Table Expressions)
- dbt refs ({{ ref('model_name') }})
- Column aliases
- GROUP BY clauses

**`node_parse_error`** uses regex patterns to classify the error:
- `missing_column` — column not found
- `missing_relation` — table/view not found
- `ambiguous_column` — column exists in multiple joined tables
- `type_mismatch` — incompatible data types
- `syntax_error` — SQL syntax issue
- `missing_group_by` — aggregation without GROUP BY
- And more (10 patterns covering DuckDB, Postgres, Snowflake, BigQuery)

### Step 4: Lineage construction

`node_build_lineage` builds a networkx DAG from the manifest's pre-computed
`parent_map` and `child_map`. Each node carries metadata (materialization,
schema, file path, run status). The DAG is used for:
- Upstream traversal (which models feed into the broken one)
- Downstream impact analysis (what breaks if this model is broken)
- Path finding (all paths from source to the broken model)

### Step 5: LLM analysis

`node_llm_analyze` assembles all gathered evidence into a structured prompt
and makes ONE Claude API call:

**System prompt** instructs Claude to:
- Read the evidence carefully
- Think step-by-step about the cause
- Check columns against upstream schemas
- Identify renames, drops, and phantom references
- Write corrected SQL preserving the original semantics
- Assess confidence honestly (0.0 to 1.0)

**User prompt** contains:
- The broken model's raw SQL
- The warehouse error message
- For each upstream model: name, file path, published columns, first 800
  chars of SQL
- The lineage path (e.g., raw_orders → stg_orders → customer_revenue)
- Parsed entities (tables, columns, aggregations, refs)

**Response** is structured JSON:
```json
{
  "root_cause": "...",
  "explanation": "...",
  "confidence_score": 0.98,
  "corrected_sql": "...",
  "validation_steps": ["...", "..."],
  "affected_columns": ["...", "..."],
  "hypotheses": [{"cause": "...", "description": "...", "confidence": 0.98}]
}
```

### Step 6: Caching and response

The result is:
1. Cached in the database (keyed by hash of manifest_path + run_results_path
   + model_name + mode) with a 1-hour TTL
2. Logged as a `Job` row (for the Jobs page and usage tracking)
3. Returned to the client as JSON
4. Rendered in the React frontend with DAG visualization, stat cards,
   hypothesis cards, SQL diff, and validation checklist

---

## 6. LLM Integration — Core Design

### Design philosophy: context engineering, not tool-calling

The naive approach to LLM-powered debugging is to give Claude all the tools
and let it discover everything through tool calls (the agentic approach).
This works but is slow (~25 seconds) and expensive (~$0.15 per run).

The design insight: **most of the "investigation" is deterministic**. Parsing
SQL, reading the manifest, comparing columns — these don't require an LLM.
What requires an LLM is the **reasoning**: "given these facts, what went
wrong and how do I fix it?"

So the architecture pre-builds a structured evidence packet using cheap
deterministic code, then asks Claude to reason over it in a single call.
This is **context engineering** — the art of assembling the right context
so the LLM can produce a high-quality answer in one pass.

### What gets sent to Claude (per request)

| Component | Source | Tokens |
|-----------|--------|--------|
| System prompt (reasoning instructions + few-shot example) | Static | ~800 |
| Broken model SQL | manifest.json `raw_code` | ~200-500 |
| Error message | run_results.json `message` | ~100-200 |
| Upstream models (columns + SQL snippet per model) | Parsed from manifest | ~500-1000 |
| Parsed entities (tables, columns, aggregations) | sqlglot output | ~100-200 |
| Lineage path | networkx traversal | ~50 |
| **Total input** | | **~1,700-2,900** |
| **Total output** | Claude's JSON response | **~400-1,200** |

### Cost per analysis

```
Input:  2,900 tokens × $3.00 / 1M tokens  = $0.0087
Output: 1,100 tokens × $15.00 / 1M tokens = $0.0165
Total per run:                               ~$0.025

With caching (50% hit rate):                 ~$0.013 effective
```

### LLM techniques demonstrated

| Technique | Where | How |
|-----------|-------|-----|
| **Context engineering** | `llm_analyzer.py` | Pre-build structured evidence, send as one prompt |
| **Chain-of-thought** | System prompt | "Think step-by-step about what caused the error" |
| **Structured output (JSON)** | System prompt | Strict JSON schema with type constraints |
| **Few-shot prompting** | System prompt | One complete example diagnosis included |
| **Grounded reasoning** | Evidence packet | LLM answers constrained by real manifest data |
| **Confidence calibration** | System prompt | Rules for 0.95+, 0.80-0.94, 0.65-0.79, <0.65 |
| **Tool use / function calling** | `agent.py` | 7 tools for the ReAct agentic mode |
| **ReAct pattern** | `agent.py` | Thought → Action → Observation loop |
| **Multi-agent orchestration** | `pipeline.py` | LangGraph StateGraph with parallel fan-out |

### Why NOT a rule engine

An earlier version of this project used a hand-written rule engine with
hard-coded confidence values (e.g., `column_renamed_upstream = 0.95`).
This was replaced for three reasons:

1. **Doesn't scale**: every new error pattern requires a new hand-written rule
2. **Fake confidence**: hard-coded numbers aren't real probabilities
3. **Can't explain**: rules produce labels ("column_renamed_upstream"),
   not explanations ("stg_orders renamed 'price' to 'amount_total' during
   staging, but the downstream model still references the old name")

The LLM-first approach handles novel errors, produces natural language
explanations, and assesses its own confidence — all without any hand-written
patterns.

---

## 7. Technology Stack

### Backend

| Component | Tool | Version | Purpose |
|-----------|------|---------|---------|
| Web framework | FastAPI | 0.115.0 | Async HTTP API with Pydantic validation |
| LLM orchestration | LangGraph | 1.1.6 | StateGraph with parallel nodes, conditional edges |
| LLM client | LangChain Anthropic | 1.4.0 | ChatAnthropic wrapper for Claude |
| LLM API | Anthropic SDK | 0.94+ | Direct Claude API calls with timeout/retry |
| SQL parsing | sqlglot | 25.24.0 | AST extraction: tables, columns, joins, aliases |
| Graph library | networkx | 3.3 | DAG construction, traversal, path finding |
| ORM | SQLAlchemy | 2.0+ | Async database access with aiosqlite |
| Rate limiting | slowapi | 0.1.9 | Per-key request throttling |
| Logging | structlog | 25.0+ | Structured JSON logging for CloudWatch |
| HTTP client | httpx | 0.27+ | dbt Cloud API client |
| Validation | Pydantic | 2.9.2 | Request/response schema enforcement |
| dbt | dbt-core | 1.8.7 | Bundled demo project with dbt-duckdb adapter |

### Frontend

| Component | Tool | Version | Purpose |
|-----------|------|---------|---------|
| Framework | React | 18.3 | Component-based UI |
| Language | TypeScript | 5.6 | Type safety across the frontend |
| Build tool | Vite | 5.4 | Dev server with proxy, fast HMR |
| Styling | Tailwind CSS | 3.4 | Utility-first CSS with custom brand theme |
| State | Zustand | 5.0 | Global store with localStorage persistence |
| Server state | TanStack Query | 5.59 | Polling, caching, refetching |
| HTTP client | Axios | 1.7 | Bearer token interceptor, error normalization |
| DAG visualization | React Flow | 11.11 | Interactive lineage graph |
| Graph layout | dagre | 0.8.5 | Automatic left-to-right DAG positioning |
| Icons | Lucide React | 0.454 | Consistent icon set |
| Toasts | Sonner | 1.7 | Non-blocking notifications |
| Routing | React Router | 6.28 | Client-side page navigation |

### Infrastructure

| Component | Tool | Purpose |
|-----------|------|---------|
| Container | Docker | Multi-stage build (Node + Python + runtime) |
| Container runtime | AWS ECS Fargate | Serverless container execution |
| Load balancer | AWS ALB | HTTP routing + health checks |
| Image registry | AWS ECR | Private Docker image storage |
| Secrets | AWS SSM Parameter Store | Anthropic key + API keys |
| Networking | AWS VPC | Private subnets + public ALB |
| Logging | AWS CloudWatch | Centralized log aggregation |
| Deployment tool | AWS Copilot CLI | ECS infrastructure management |
| CI/CD | GitHub Actions | Automated test + build + deploy |
| Version control | GitHub | Source code + issue tracking |

---

## 8. Backend Implementation

### API design

The API follows RESTful conventions with versioning (`/api/v1/`). All
authenticated endpoints require a `Authorization: Bearer <key>` header.

**Endpoint summary:**

| Method | Path | Auth | Rate limit | Purpose |
|--------|------|------|-----------|---------|
| GET | /api/v1/health | Public | None | Health + dependency checks |
| POST | /api/v1/debug | Bearer | 10/min | Main analysis endpoint |
| POST | /api/v1/upload | Bearer | 10/min | File upload (multipart) |
| POST | /api/v1/debug/cloud | Bearer | 10/min | dbt Cloud integration |
| GET | /api/v1/jobs/{id} | Bearer | None | Poll async job status |
| GET | /api/v1/jobs | Bearer | 30/min | List job history |
| GET | /api/v1/usage | Bearer | 30/min | Per-key usage stats |
| GET | /api/v1/models | Bearer | 30/min | List models in manifest |

### Middleware stack (order matters)

```
Request → Size limit check (50MB)
        → Request ID generation (UUID)
        → Request logging (structlog)
        → CORS validation
        → Rate limiting (slowapi)
        → Bearer token auth
        → Route handler
        → Usage logging (to DB)
        → Response with X-Request-ID header
```

### Async job pattern

Agentic mode uses fire-and-poll:

1. `POST /api/v1/debug` creates a `Job` row (status=queued), schedules
   a `BackgroundTasks` coroutine, returns `202 Accepted` with `job_id`
2. Background task runs the agent, updates the job row as it progresses
   (queued → running → completed/failed)
3. Client polls `GET /api/v1/jobs/{id}` every 2 seconds until
   status is `completed` or `failed`

This prevents long-running agentic requests from blocking the server.

### Caching

Results are cached by a SHA-256 hash of `(manifest_path, run_results_path,
model_name, mode)` with a 1-hour TTL. Cache hits return instantly ($0 cost,
~50ms latency) and don't create new job rows.

---

## 9. Frontend Implementation

### Pages

| Page | Route | Purpose |
|------|-------|---------|
| Debug | `/` | Main analysis — mode selector, source selector, file upload, results |
| Jobs | `/jobs` | Job history with auto-refresh (5s interval) |
| Usage | `/usage` | Per-key stats: debug runs, fast/agentic split, cache hits |
| Models | `/models` | Browse all models in a manifest with upstream/downstream |
| Settings | `/settings` | API key + base URL configuration |

### State management

**Zustand with selective persistence:**
- `useSettings` → persisted to localStorage (API key, paths survive refresh)
- `useDebugState` → in-memory only (results survive navigation but clear on refresh)

### Key components

| Component | What it renders |
|-----------|----------------|
| `AnalyzerResultPanel` | Root cause card (gradient banner), explanation, affected columns, hypotheses with confidence bars, validation checklist |
| `AgenticResultPanel` | Tool call timeline with numbered steps, diagnosis card, SQL diff |
| `LineageGraph` | React Flow DAG with dagre layout, custom model nodes with status icons |
| `FileDropZone` | Drag-and-drop file upload with size validation and status feedback |
| `SqlDiff` | Side-by-side original vs corrected SQL with copy/download buttons |
| `ParsedSqlPanel` | Extracted entities (tables, columns, aggregations) with highlighted missing column |
| `ParsedErrorPanel` | Structured error type, column, candidates from warehouse |

### Design system

- Light theme with brand gradient: `#5ba479` (sage green) → `#2f6379` (teal)
- Font: Inter (UI) + JetBrains Mono (code)
- Component library: custom primitives (Button, Card, Badge, Input, Select)
- Responsive layout with sidebar navigation

---

## 10. Database Layer

### Schema (SQLAlchemy async + SQLite / Postgres-compatible)

**Jobs table** — one row per analysis:
```
jobs:
  id              VARCHAR(32) PK    "job_abc123def456"
  api_key_prefix  VARCHAR(32)       "dl_385c5e..."
  mode            ENUM              fast | agentic
  status          ENUM              queued | running | completed | failed
  request         JSON              full request body
  result          JSON              full analysis result
  broken_model    VARCHAR(255)      "customer_revenue"
  cache_key       VARCHAR(64)       SHA-256 hash
  created_at      DATETIME
  started_at      DATETIME
  completed_at    DATETIME
  duration_ms     INTEGER
```

**Usage log** — one row per HTTP request:
```
usage_log:
  id              INTEGER PK
  api_key_prefix  VARCHAR(32)
  endpoint        VARCHAR(255)
  method          VARCHAR(10)
  status_code     INTEGER
  duration_ms     INTEGER
  timestamp       DATETIME
  job_id          VARCHAR(32)       nullable FK
```

**Cache entries** — one row per cached result:
```
cache_entries:
  cache_key       VARCHAR(64) PK    SHA-256 hash
  mode            ENUM
  result          JSON
  created_at      DATETIME
  hit_count       INTEGER
```

### Migration path

SQLite for development and beta. Upgrading to Postgres requires ONE config
change:

```
# .env
DATABASE_URL=sqlite+aiosqlite:///./datalineage.db       # dev
DATABASE_URL=postgresql+asyncpg://user:pass@host/db      # prod
```

Same SQLAlchemy models, same queries. Zero code changes.

---

## 11. dbt Artifact Ingestion

### Modules

| Module | File | Input | Output |
|--------|------|-------|--------|
| Manifest Loader | `app/dbt/manifest_loader.py` | `manifest.json` | `Manifest` with `ModelNode`, `SourceNode`, dependency maps |
| Run Results Loader | `app/dbt/run_results_loader.py` | `run_results.json` | `RunResults` with `NodeResult` per model (status, error, timing) |
| Model Resolver | `app/dbt/model_resolver.py` | Manifest + RunResults | `FailureContext` — complete debug context per failed model |
| Lineage Builder | `app/dbt/lineage_builder.py` | Manifest | `LineageGraph` — networkx DAG with traversal helpers |

### Column extraction strategy

dbt's `manifest.json` has a `columns` field on each model, but it's almost
always empty (only populated when the user writes explicit column docs in
`schema.yml`). So the system extracts columns by **parsing the raw SQL**:

```
stg_orders.sql:
  SELECT order_id, price AS amount_total FROM {{ ref('raw_orders') }}
         ────────  ─────    ────────────
         column    source    alias (published name)

Extraction:
  Published columns = [amount_total, order_id]
  (aliases win over sources because downstream sees the alias)
```

This is done via sqlglot AST analysis in `_extract_columns_from_sql()`.

---

## 12. dbt Cloud Integration

### How it works

Users can paste a dbt Cloud URL instead of uploading files:

```
https://cloud.getdbt.com/deploy/12345/projects/67890/jobs/111
```

The frontend's `parseDbtCloudUrl()` extracts:
- Account ID: `12345`
- Project ID: `67890`
- Job ID: `111`

The backend's `DbtCloudClient` then:
1. Calls `GET /api/v2/accounts/{acct}/runs/?job_definition_id={job}` to
   find the latest completed run
2. Downloads `manifest.json` and `run_results.json` from that run
3. Saves them to a temp directory
4. Passes the paths to the normal analysis pipeline

### Mock server for testing

`scripts/mock_dbt_cloud.py` is a local FastAPI app that mimics dbt Cloud's
API, serving the bundled `dbt_demo/target/` files. This enables full
integration testing without a real dbt Cloud account.

---

## 13. Security & Authentication

### Authentication flow

```
Client → Authorization: Bearer dl_385c5eacd16657ddd2b944b7
                                       │
Backend reads API_KEYS env var ────────┘
         │
         ▼
  If key is in the allowed list → proceed
  If key is missing → 401 Unauthorized
  If key is invalid → 401 Unauthorized
```

### Per-key isolation

- Jobs endpoint: `WHERE api_key_prefix = <caller's prefix>`
- Usage endpoint: same filter
- One user CANNOT see another user's jobs or usage

### Rate limiting

- slowapi with per-key tracking (not per-IP)
- Fast mode: 10 requests/minute
- Agentic mode: 3 requests/minute
- On exceed: HTTP 429 with Retry-After header

### Data privacy

- Only the failing model's SQL + direct upstream columns are sent to Claude
- The full manifest is read server-side only — never sent to the LLM
- No SQL content is logged — only metadata (timing, status, key prefix)
- Self-hosting option: run the Docker image in your own VPC with your own
  Anthropic key

---

## 14. Deployment Pipeline

### Docker image (multi-stage build)

```dockerfile
Stage 1: frontend-builder (Node 20)
  → npm ci
  → npm run build
  → Output: /frontend/dist/

Stage 2: python-builder (Python 3.13)
  → pip install -r requirements.txt
  → Output: /install/

Stage 3: runtime (Python 3.13 slim)
  → Copy Python packages from Stage 2
  → Copy app code
  → Copy frontend/dist from Stage 1
  → Non-root user (datalineage, uid 1000)
  → HEALTHCHECK on /api/v1/health
  → CMD: uvicorn with 1 worker
```

Image size: ~855 MB

### AWS infrastructure

```
Internet
    │
    ▼
AWS Application Load Balancer (HTTP, health checks)
    │
    ▼
AWS ECS Fargate (1 vCPU, 2 GB RAM)
    │
    ├── Container: datalineage-ai:latest
    │     ├── FastAPI + React (port 8000)
    │     ├── SQLite (ephemeral per container)
    │     └── Reads secrets from SSM Parameter Store
    │
    ├── ECR: 095453158391.dkr.ecr.us-east-1.amazonaws.com/datalineage-ai
    │
    └── CloudWatch: /copilot/datalineage-prod-api (structured JSON logs)
```

### Deployment managed by AWS Copilot

```
copilot app init datalineage     → registers the application
copilot env init --name prod     → creates VPC, subnets, ALB, ECS cluster
copilot svc init --name api      → defines the service from Dockerfile
copilot svc deploy               → builds, pushes, deploys
```

---

## 15. CI/CD with GitHub Actions

### Test workflow (`.github/workflows/test.yml`)

Triggered on: every push to `main` and every pull request.

```
Steps:
  1. Checkout code
  2. Set up Python 3.13
  3. Install dependencies
  4. Compile dbt demo project
  5. Run pytest (26 tests)
  6. Start the API server, hit /health to verify startup
```

### Deploy workflow (`.github/workflows/deploy.yml`)

Triggered on: every push to `main`.

```
Steps:
  1. Checkout code
  2. Configure AWS credentials (from GitHub secrets)
  3. Login to ECR
  4. Build Docker image (tagged with commit SHA + latest)
  5. Push to ECR
  6. Force ECS to pull the new image
  7. Wait for service to stabilize
  8. Health check against the live URL
```

### GitHub secrets

| Secret | Purpose |
|--------|---------|
| `AWS_ACCESS_KEY_ID` | IAM user access key for ECR + ECS |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key |

---

## 16. Monitoring & Observability

### Three levels of monitoring

**Level 1: Application metrics (in-app)**
- `/api/v1/usage` — per-key debug runs, fast/agentic split, cache hits,
  avg duration, status code breakdown
- `/api/v1/jobs` — per-key job history with timing

**Level 2: Infrastructure metrics (CloudWatch)**
- ALB: RequestCount, TargetResponseTime, HTTPCode_Target_2XX/4XX/5XX
- ECS: CPUUtilization, MemoryUtilization
- Health check status

**Level 3: Structured logs (CloudWatch Logs)**
Every request is logged as JSON:
```json
{
  "event": "request_end",
  "request_id": "abc12345",
  "method": "POST",
  "path": "/api/v1/debug",
  "status": 200,
  "duration_ms": 4200,
  "api_key": "dl_385c5e...",
  "timestamp": "2026-04-12T22:10:00Z"
}
```

Searchable by: request_id, api_key, path, status, duration.

---

## 17. Testing Strategy

### Test coverage

| Test file | Tests | What it covers |
|-----------|-------|---------------|
| `test_sql_parser.py` | 7 | sqlglot entity extraction, dbt ref handling, CTE detection, alias mapping |
| `test_manifest_and_lineage.py` | 19 | Manifest parsing, model lookup, upstream/downstream traversal, DAG construction, path finding |
| **Total** | **26** | Core deterministic logic |

### What's NOT unit-tested (and why)

- **LLM analyzer**: each call costs $0.013 and produces non-deterministic
  output. Tested via integration tests against the bundled demo.
- **API endpoints**: tested via curl/httpx during development and CI
  health check. Full API test suite is future work.
- **Frontend**: no automated browser tests. Tested manually across all
  5 pages. Playwright/Cypress is future work.

### Integration test (bundled demo)

The `dbt_demo/` project serves as a living integration test:
- 6 models (raw_orders, stg_orders, raw_customers, stg_customers,
  customer_revenue, customer_lifetime_metrics)
- 2 intentionally broken models with known errors
- `customer_lifetime_metrics` has 6 distinct errors spanning CTEs,
  window functions, and multiple upstream layers
- Every deployment includes a health check + manifest/models endpoint
  verification

---

## 18. Demo Scenarios

### Bundled demo project

```
raw_orders ──► stg_orders ──┐
                            ├──► customer_revenue          ❌ 1 error
                            │   (simple column rename)
                            │
                            └──► customer_lifetime_metrics ❌ 6 errors
                                 (CTEs + window functions)
                                 ▲
raw_customers ──► stg_customers ─┘
  (phone_number,    (drops phone for PII,
   loyalty_tier)     renames customer_name→full_name)
```

### The 6 errors in customer_lifetime_metrics

| # | Error | Category | Root cause |
|---|-------|----------|-----------|
| 1 | `amount` → `amount_total` | Column renamed in staging | stg_orders |
| 2 | `price` → (dropped) | Column removed during staging | stg_orders |
| 3 | `customer_name` → `full_name` | Column renamed in staging | stg_customers |
| 4 | `email_address` → (never existed) | Typo / phantom reference | nowhere |
| 5 | `phone_number` → (dropped for PII) | Intentional data governance | stg_customers |
| 6 | `membership_level` → `loyalty_tier` | Typo / wrong name | stg_customers |

### Beta test scenarios

5 test folders prepared for 5 beta testers, each testing a different feature:

| Scenario | Tester | Focus |
|----------|--------|-------|
| Simple 1-error analysis | Friend 1 | Fast mode basic flow |
| Complex 6-error analysis | Friend 2 | LLM multi-error detection |
| Agentic deep analysis | Friend 3 | ReAct agent with tool timeline |
| Valid query detection | Friend 4 | Green "query is valid" banner |
| Full app tour | Friend 5 | Upload, Cloud URL, Jobs, Usage, navigation |

---

## 19. Cost Analysis

### Per-request costs

| Mode | Input tokens | Output tokens | Claude cost | Total with infra |
|------|-------------|--------------|-------------|-----------------|
| Fast (simple model) | ~1,700 | ~500 | $0.013 | $0.013 |
| Fast (complex model) | ~2,900 | ~1,100 | $0.025 | $0.025 |
| Fast (cached) | 0 | 0 | $0.000 | $0.000 |
| Agentic | ~15,000 | ~3,000 | $0.090 | $0.150 |

### Monthly projections

| Usage level | Fast runs | Agentic runs | Claude cost | AWS cost | Total |
|------------|-----------|-------------|-------------|----------|-------|
| Beta (5 users, light) | 100 | 10 | $2.80 | $10 | ~$13 |
| Small team (20 users) | 500 | 50 | $17 | $15 | ~$32 |
| Growth (100 users) | 2,000 | 200 | $80 | $25 | ~$105 |

### AWS infrastructure costs

| Service | Free tier | Monthly cost |
|---------|-----------|-------------|
| ECS Fargate (1 vCPU, 2GB) | None | ~$10-15 |
| ECR (image storage) | 500 MB free | ~$0.10 |
| ALB | Free for first 12 months | ~$5 after |
| CloudWatch Logs | 5 GB free | ~$0.50 |
| SSM Parameter Store | Free tier | $0 |
| **Total infrastructure** | | **~$10-20/month** |

---

## 20. Design Decisions & Trade-offs

### LLM-first vs rule engine

| Aspect | Rule engine (rejected) | LLM-first (chosen) |
|--------|----------------------|-------------------|
| Novel errors | Cannot handle | Handles naturally |
| Explanations | Labels only | Natural language |
| Confidence | Hard-coded (fake) | Self-assessed (real) |
| Maintenance | New rule per pattern | Zero maintenance |
| Cost | Free | ~$0.013/run |
| Determinism | Yes | No (but cached) |

**Decision**: the ~1 cent per run is worth the 10x better quality.

### Context engineering vs full tool-calling

| Aspect | Context engineering (fast mode) | Tool-calling (agentic mode) |
|--------|-------------------------------|---------------------------|
| Latency | ~4 seconds | ~25 seconds |
| Cost | ~$0.013 | ~$0.15 |
| LLM calls | 1 | 5-10 |
| Handles 90% of cases | Yes | Yes |
| Handles edge cases | Sometimes | Yes |
| User experience | Instant | "Agent is investigating..." |

**Decision**: offer both. Default to fast, opt-in to agentic for complex cases.

### SQLite vs Postgres

| Aspect | SQLite (chosen for beta) | Postgres (future) |
|--------|------------------------|--------------------|
| Setup | Zero config | Need RDS instance |
| Cost | $0 | ~$15/month |
| Data survives restart | No (ephemeral in ECS) | Yes |
| Multi-worker safe | No (single writer) | Yes |
| Migration effort | — | One config line change |

**Decision**: SQLite for beta (acceptable to lose data on restart), Postgres
when paying users need persistent history.

### Streamlit vs React

| Aspect | Streamlit (rejected) | React (chosen) |
|--------|---------------------|----------------|
| Dev speed | Faster for prototyping | Slower initial build |
| Production quality | Limited (no auth, shared state) | Full control |
| Customization | Limited theming | Complete design system |
| Performance | Re-renders entire page | Virtual DOM, efficient updates |
| Deployment | Separate service needed | Bundles into the same container |

**Decision**: React for production quality, Streamlit was useful during
prototyping but replaced for the final product.

---

## 21. Limitations

### Current limitations

1. **No user signup/login** — API keys are pre-issued manually. No
   self-service registration.

2. **SQLite data is ephemeral** — job history and usage stats are lost when
   the ECS container restarts (on every deployment). Postgres migration
   would fix this.

3. **No streaming in agentic mode** — the frontend polls every 2 seconds
   instead of receiving a real-time stream of the agent's actions.

4. **English-only prompts** — the LLM system prompt and few-shot examples
   are in English. The system could theoretically work in other languages
   but hasn't been tested.

5. **No local LLM support** — currently requires an Anthropic API key.
   Supporting Ollama or AWS Bedrock would enable fully private deployments.

6. **No custom domain** — uses the default AWS ALB URL. A custom domain
   (e.g., datalineage-ai.com) requires Route 53 + ACM certificate setup.

7. **Single warehouse dialect** — error parsing patterns cover DuckDB,
   Postgres, Snowflake, and BigQuery, but haven't been tested extensively
   on Redshift, Databricks, or Spark SQL.

8. **No historical comparison** — the system analyzes one snapshot at a
   time. It can't show "this column was renamed in commit X by developer Y."

---

## 22. Future Work

### Short-term (next 2-4 weeks)

- **Self-service signup** — email-based registration with automatic key
  provisioning. Removes the manual key generation bottleneck.

- **Job history export** — download analysis reports as JSON/PDF from the
  Jobs page. Enables audit trails and team sharing.

- **Postgres migration** — persistent storage that survives deployments.
  One config line change, but needs an RDS instance.

- **"Try demo" button** — one-click pre-filled analysis using the bundled
  demo data. Makes the app shareable with non-dbt visitors.

### Medium-term (1-3 months)

- **Streaming agentic mode** — replace polling with WebSocket/SSE streaming
  so users see the agent's reasoning in real-time.

- **Multi-model batch analysis** — analyze all failures in a run at once,
  not just one model at a time.

- **Git integration** — "who renamed this column and when?" by cross-
  referencing the manifest with git blame.

- **Warehouse introspection** — connect to the actual database (Snowflake,
  BigQuery, etc.) to get runtime column types, row counts, and sample data.

- **Local LLM support** — Ollama integration for fully offline, privacy-
  preserving deployments.

### Long-term (3-6 months)

- **CI/CD integration** — run DataLineage AI as a step in dbt CI pipelines.
  On failure, automatically diagnose and post the root cause as a PR comment.

- **Slack/Teams bot** — receive debug results in a channel notification
  when a scheduled dbt job fails.

- **Multi-tenant SaaS** — proper user accounts, team management, billing
  with usage-based pricing.

- **Custom domain + SSL** — professional URL (datalineage-ai.com) with
  HTTPS via AWS Certificate Manager.

- **SOC2 compliance** — data processing agreement, security audit, for
  enterprise customers who need compliance certification.

---

## 23. Project Timeline

| Phase | Duration | What was built |
|-------|----------|---------------|
| **Phase 1: Core modules** | Days 1-2 | manifest_loader, run_results_loader, sql_parser, error_parser, lineage_builder, model_resolver |
| **Phase 2: LangGraph pipeline** | Days 2-3 | StateGraph with 5 nodes, parallel fan-out, agentic ReAct agent with 7 tools |
| **Phase 3: LLM-first pivot** | Day 3 | Deleted rule engine, built llm_analyzer.py with single Claude call, structured prompting |
| **Phase 4: FastAPI v1 API** | Days 3-4 | Auth, rate limiting, async jobs, caching, file upload, dbt Cloud integration |
| **Phase 5: React frontend** | Days 4-5 | 5 pages, DAG visualization, file drag-drop, dbt Cloud URL parser, light theme |
| **Phase 6: Production ops** | Days 5-6 | SQLite persistence, structured logging, Dockerfile, health checks |
| **Phase 7: AWS deployment** | Day 6 | ECR, ECS Fargate (via Copilot), SSM secrets, ALB, CloudWatch |
| **Phase 8: CI/CD** | Day 6 | GitHub Actions (test on PR, deploy on merge) |
| **Phase 9: Beta prep** | Day 7 | Complex demo (6-error model), test scenarios, README rewrite, screenshots |

---

## 24. File Structure

```
.
├── app/
│   ├── api/                       # FastAPI routes + middleware
│   │   ├── main.py                # App entry, middleware stack, static serving
│   │   ├── v1.py                  # All /api/v1/* endpoints
│   │   ├── auth.py                # Bearer token verification
│   │   ├── rate_limit.py          # slowapi per-key limits
│   │   ├── jobs.py                # Background task runners
│   │   └── schemas.py             # Pydantic request/response models
│   │
│   ├── core/                      # Configuration + logging
│   │   ├── config.py              # All env vars (40+ settings)
│   │   └── logging.py             # structlog JSON/console setup
│   │
│   ├── dbt/                       # dbt artifact ingestion
│   │   ├── manifest_loader.py     # Parse manifest.json → typed objects
│   │   ├── run_results_loader.py  # Parse run_results.json
│   │   ├── model_resolver.py      # Join manifest + results → FailureContext
│   │   ├── lineage_builder.py     # networkx DAG with React Flow output
│   │   └── cloud_client.py        # dbt Cloud API client (httpx)
│   │
│   ├── services/                  # Deterministic helpers
│   │   ├── sql_parser.py          # sqlglot AST extraction
│   │   ├── error_parser.py        # 10 regex error patterns
│   │   └── llm_analyzer.py        # THE core: single Claude call
│   │
│   ├── graph/                     # LangGraph orchestration
│   │   ├── state.py               # PipelineState TypedDict
│   │   ├── nodes.py               # 5 node functions
│   │   ├── pipeline.py            # Fast-mode StateGraph
│   │   ├── agent.py               # Agentic ReAct agent
│   │   └── tools.py               # 7 tools for the agent
│   │
│   └── db/                        # SQLAlchemy async
│       ├── base.py                # Engine + session factory
│       ├── models.py              # Job, UsageLog, CacheEntry
│       └── repository.py          # All DB CRUD functions
│
├── frontend/                      # React + TypeScript + Tailwind
│   ├── src/
│   │   ├── lib/                   # api.ts, store.ts, types.ts, utils.ts
│   │   ├── components/            # 15 components (UI primitives + features)
│   │   └── pages/                 # 5 pages (Debug, Jobs, Usage, Models, Settings)
│   ├── vite.config.ts             # Dev proxy /api → localhost:8000
│   └── tailwind.config.js         # Brand gradient theme
│
├── dbt_demo/                      # Bundled demo dbt project (6 models)
├── test_scenarios/                # 5 beta tester folders with instructions
├── scripts/                       # mock_dbt_cloud.py
├── tests/                         # 26 pytest tests
├── .github/workflows/             # CI/CD (test.yml + deploy.yml)
├── copilot/                       # AWS Copilot environment config
│
├── Dockerfile                     # Multi-stage (Node + Python + runtime)
├── .dockerignore
├── .env.example                   # Template with all 20+ env vars
├── .gitignore
├── LICENSE                        # All rights reserved
├── API.md                         # API reference documentation
├── DEPLOY.md                      # AWS deployment step-by-step guide
├── PROJECT_REPORT.md              # This document
├── README.md                      # GitHub landing page
└── requirements.txt               # 25 Python dependencies
```

---

## 25. How to Run

### Local development (Vite + uvicorn)

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your ANTHROPIC_API_KEY
cd dbt_demo && dbt run --profiles-dir . && cd ..
API_KEYS=dl_dev REQUIRE_API_KEY=true uvicorn app.api.main:app --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev

# Open http://localhost:5173 → Settings → paste dl_dev → Debug → Analyze
```

### Docker (single container)

```bash
docker build -t datalineage-ai:latest .
docker run --rm -p 9000:8000 \
  -e API_KEYS=dl_dev \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  datalineage-ai:latest

# Open http://localhost:9000
```

### Production (AWS ECS via Copilot)

See [DEPLOY.md](DEPLOY.md) for the complete step-by-step guide.

---

## 26. References

### Tools and frameworks

- **dbt (data build tool)**: https://www.getdbt.com/
- **Claude API (Anthropic)**: https://docs.anthropic.com/
- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **FastAPI**: https://fastapi.tiangolo.com/
- **React Flow**: https://reactflow.dev/
- **sqlglot**: https://sqlglot.com/
- **networkx**: https://networkx.org/
- **AWS Copilot**: https://aws.github.io/copilot-cli/

### Concepts

- **ReAct pattern**: Yao et al., "ReAct: Synergizing Reasoning and Acting
  in Language Models" (2022)
- **Context engineering**: building structured prompts that ground LLM
  reasoning in factual evidence
- **Chain-of-thought prompting**: Wei et al., "Chain-of-Thought Prompting
  Elicits Reasoning in Large Language Models" (2022)
- **Structured output**: constraining LLM responses to a strict JSON
  schema for reliable parsing

---

*This document was prepared as part of the LLM course final project at
Stony Brook University, April 2026.*
