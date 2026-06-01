FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /workspace

COPY shared ./shared
COPY background ./background

WORKDIR /workspace/background

RUN uv sync --no-dev

CMD ["uv", "run", "background-worker", "worker"]
