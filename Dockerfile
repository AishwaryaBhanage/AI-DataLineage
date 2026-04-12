# ─────────────────────────────────────────────────────────────────────────────
# DataLineage AI — Production Dockerfile
#
# Multi-stage build:
#   1. frontend-builder  — compiles React app to static files
#   2. python-builder    — installs Python dependencies
#   3. runtime           — slim image with only what's needed at execution
#
# FastAPI serves both the API AND the frontend from a single container,
# so beta testers get one URL (e.g. https://xxx.awsapprunner.com) where
# the React UI is at / and the API is at /api/v1/*
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: frontend-builder (Node) ────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

# Copy only package files first so Docker caches the npm install layer
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install

# Now copy source and build
COPY frontend/ ./
RUN npm run build

# Output is at /frontend/dist


# ── Stage 2: python-builder ─────────────────────────────────────────────────
FROM python:3.13-slim AS python-builder

# Build tools needed to compile some Python deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install into /install so we can copy the result into the runtime image
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 3: runtime ────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# Runtime-only system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd --create-home --uid 1000 datalineage

# Copy installed Python packages from the python-builder stage
COPY --from=python-builder /install /usr/local

WORKDIR /app

# Copy application code with proper ownership
COPY --chown=datalineage:datalineage app/ ./app/
COPY --chown=datalineage:datalineage dbt_demo/ ./dbt_demo/
COPY --chown=datalineage:datalineage data/ ./data/

# Copy the built frontend from the frontend-builder stage
# Placed at /app/frontend/dist so FastAPI can serve it as static files
COPY --from=frontend-builder --chown=datalineage:datalineage /frontend/dist ./frontend/dist

# Make /app itself writable for the datalineage user so the app can
# create runtime files (SQLite DB, temp upload dirs, etc.)
RUN chown datalineage:datalineage /app

# Switch to non-root
USER datalineage

# Production defaults — override at runtime via -e flags
ENV ENVIRONMENT=production \
    LOG_LEVEL=INFO \
    REQUIRE_API_KEY=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Healthcheck — App Runner uses /api/v1/health to decide container health
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/api/v1/health || exit 1

EXPOSE 8000

# Single worker per container.  SQLite is single-writer so multi-worker
# creates startup races.  For scale, App Runner spins up multiple container
# instances horizontally — that's where the real parallelism comes from.
# When migrating to Postgres later, you can bump --workers to 2 or 4.
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
