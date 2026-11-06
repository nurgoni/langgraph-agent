# syntax=docker/dockerfile:1
# Satu Dockerfile, dua target: `service` (FastAPI) dan `ui` (Streamlit).
#   docker build -f docker/Dockerfile --target service -t agent-service .
#   docker build -f docker/Dockerfile --target ui -t agent-service-ui .

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS base
# Versi uv sama dengan yang menulis uv.lock (lihat CI).
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1
WORKDIR /app

# Dependency dulu, supaya layer ini tetap ter-cache selama uv.lock tidak berubah.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown app:app /data
USER app

FROM base AS service
ENV HOST=0.0.0.0 \
    PORT=8080 \
    SQLITE_DB_PATH=/data/checkpoints.db
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=10 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=2)"]
CMD ["python", "-m", "agent_service.run_service"]

FROM base AS ui
ENV AGENT_URL=http://agent-service:8080 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8501
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=10 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=2)"]
CMD ["streamlit", "run", "src/agent_service/ui/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
