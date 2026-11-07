FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

ARG HUBSHELL_RELEASE_ID
ENV GAMECLUB_SERVER_RELEASE_ID=${HUBSHELL_RELEASE_ID}

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.19

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8100 51051
