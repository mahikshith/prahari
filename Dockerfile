# Prahari collector.
#
# This image is the security architecture, not packaging convenience. The customer
# runs it inside their own VPC: provider credentials stay under customer control.
# Configured notification channels receive alert metadata.
#
#   docker build -t prahari-collector .
#   docker run --rm -v "$PWD/prahari.yaml:/app/prahari.yaml:ro" \
#                   -v prahari-data:/data \
#                   --env-file .env -e PRAHARI_DUCKDB_PATH=/data/prahari.duckdb \
#                   --read-only --tmpfs /tmp \
#                   prahari-collector validate
#
# No secrets are baked in. Credentials arrive by environment or mounted file at run
# time, so the image itself is safe to store in a registry.

FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies before source: the layer cache then survives every code change,
# which matters because DuckDB and pandas are not small.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --extra gcp

COPY src/ ./src/
RUN uv sync --frozen --no-dev --extra gcp


FROM python:3.12-slim AS runtime

# Non-root. A container that can write its own code is one exploit away from
# persistence, and this one holds credentials for an entire AI estate.
RUN useradd --create-home --uid 10001 prahari \
    && mkdir -p /data \
    && chown -R prahari:prahari /data

WORKDIR /app

COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PRAHARI_DUCKDB_PATH=/data/prahari.duckdb

USER prahari

VOLUME ["/data"]

# This checks configuration and credential presence; collection freshness and
# notification delivery require separate operational checks.
HEALTHCHECK --interval=60s --timeout=15s --start-period=20s --retries=3 \
    CMD ["prahari", "validate", "-c", "/app/prahari.yaml"]

ENTRYPOINT ["prahari"]
CMD ["run", "-c", "/app/prahari.yaml"]
