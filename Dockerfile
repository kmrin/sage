ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.11

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# Builder
FROM python:${PYTHON_VERSION}-slim-trixie AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# Runtime
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

ARG SAGE_UID=10001
ARG SAGE_GID=10001

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SAGE_HOME=/var/lib/sage

RUN apt update \
    && apt install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid "${SAGE_GID}" sage \
    && useradd --system --uid "${SAGE_UID}" --gid sage \
        --home-dir /var/lib/sage --no-create-home --shell /usr/sbin/nologin sage \
    && install -d -o sage -g sage -m 0750 /var/lib/sage

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY src ./src

RUN chmod 0755 /app/src/scripts/entrypoint.sh

USER sage
WORKDIR /app/src
VOLUME ["/var/lib/sage"]
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD ["python", "-m", "scripts.healthcheck"]

ENTRYPOINT [ "/app/src/scripts/entrypoint.sh" ]