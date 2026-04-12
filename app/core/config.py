from dotenv import load_dotenv
import os

load_dotenv()

# ── LLM ──────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ── dbt local project ───────────────────────────────────────────────────────
DBT_PROJECT_PATH = os.getenv("DBT_PROJECT_PATH", "./dbt_demo")
MANIFEST_PATH = os.getenv("MANIFEST_PATH", "./dbt_demo/target/manifest.json")

# ── dbt Cloud ───────────────────────────────────────────────────────────────
DBT_CLOUD_API_TOKEN = os.getenv("DBT_CLOUD_API_TOKEN", "")
DBT_CLOUD_ACCOUNT_ID = os.getenv("DBT_CLOUD_ACCOUNT_ID", "")
DBT_CLOUD_BASE_URL = os.getenv("DBT_CLOUD_BASE_URL", "https://cloud.getdbt.com")

# ── API auth ────────────────────────────────────────────────────────────────
# Comma-separated list of valid API keys for the public API.
# Each beta tester gets one key.  Format: "dl_<user>_<random>"
# Set in production via AWS Secrets Manager or env var.
API_KEYS = [
    k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()
]

# When True, the API requires Authorization: Bearer <key> header.
# Set to False only for local development.
REQUIRE_API_KEY = os.getenv("REQUIRE_API_KEY", "true").lower() == "true"

# ── CORS ────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins for the API.
# In dev: "*" or "http://localhost:8501"
# In prod: "https://yourdomain.com"
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
]

# ── Rate limits ─────────────────────────────────────────────────────────────
RATE_LIMIT_FAST = os.getenv("RATE_LIMIT_FAST", "10/minute")
RATE_LIMIT_AGENTIC = os.getenv("RATE_LIMIT_AGENTIC", "3/minute")

# ── Timeouts ────────────────────────────────────────────────────────────────
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "15"))

# ── Request limits ──────────────────────────────────────────────────────────
# 50MB default covers most real dbt manifests (large projects can hit 20-30MB).
# For enterprise projects with thousands of models, bump this higher.
MAX_REQUEST_SIZE_MB = int(os.getenv("MAX_REQUEST_SIZE_MB", "50"))

# ── Environment ─────────────────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development | staging | production
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Database ────────────────────────────────────────────────────────────────
# SQLite for dev, Postgres for prod.  Driver must be async:
#   sqlite+aiosqlite:///./datalineage.db
#   postgresql+asyncpg://user:pass@host:5432/datalineage
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./datalineage.db")

# ── Cache settings ──────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 hour

# ── Daily quota per API key (0 = disabled) ──────────────────────────────────
DAILY_QUOTA_PER_KEY = int(os.getenv("DAILY_QUOTA_PER_KEY", "0"))
