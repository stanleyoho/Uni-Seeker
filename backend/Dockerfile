# Dev image — must be built from monorepo root context (parent of Uni-Seeker)
# so that backtesting_core's editable path dependency resolves correctly.
#
# Usage (via docker compose, which already sets context: ..):
#   docker compose up backend
#
# Manual build:
#   cd /path/to/stanley-project
#   docker build -f Uni-Seeker/backend/Dockerfile -t uni-seeker-backend .
FROM python:3.12-slim

# Mirror monorepo layout inside container so `[tool.uv.sources]` path
# `../../adaptive-alpha-engine/packages/backtesting_core` (relative to
# Uni-Seeker/backend/pyproject.toml) resolves the same way it does on host.
WORKDIR /workspace

RUN pip install --no-cache-dir uv

# Copy the sibling shared package first so the path dep is satisfied.
COPY adaptive-alpha-engine/packages/backtesting_core /workspace/adaptive-alpha-engine/packages/backtesting_core

# Copy Uni-Seeker backend.
COPY Uni-Seeker/backend /workspace/Uni-Seeker/backend

WORKDIR /workspace/Uni-Seeker/backend

# Editable install picks up backtesting_core via tool.uv.sources path.
RUN uv pip install --system -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
