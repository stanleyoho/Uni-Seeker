# Dev image — must be built from monorepo root context (parent of Uni-Seeker)
# so that backtesting_core and prediction_engine path dependencies resolve
# correctly.
#
# Usage (via docker compose, which already sets context: ..):
#   docker compose up backend
#
# Manual build:
#   cd /path/to/stanley-project
#   docker build -f Uni-Seeker/backend/Dockerfile -t uni-seeker-backend .
FROM python:3.12-slim

# Mirror monorepo layout inside container so `[tool.uv.sources]` paths
# `../../adaptive-alpha-engine/packages/{backtesting_core,prediction_engine}`
# (relative to Uni-Seeker/backend/pyproject.toml) resolve the same way they
# do on host.
WORKDIR /workspace

RUN pip install --no-cache-dir uv

# Copy the sibling shared packages first so the path deps are satisfied.
# Both backtesting_core and prediction_engine are referenced by
# Uni-Seeker/backend/pyproject.toml's [tool.uv.sources].
COPY adaptive-alpha-engine/packages/backtesting_core /workspace/adaptive-alpha-engine/packages/backtesting_core
COPY adaptive-alpha-engine/packages/prediction_engine /workspace/adaptive-alpha-engine/packages/prediction_engine

# Copy Uni-Seeker backend.
COPY Uni-Seeker/backend /workspace/Uni-Seeker/backend

WORKDIR /workspace/Uni-Seeker/backend

# Editable install picks up backtesting_core + prediction_engine via
# [tool.uv.sources] paths.
RUN uv pip install --system -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
