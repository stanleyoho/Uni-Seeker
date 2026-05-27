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

# pyproject.toml's [tool.uv.sources] points backtesting_core +
# prediction-engine at git+ssh AAE URLs — that's what backend-ci /
# pg-integration / external-api-smoke / schema-gate workflows expect
# (they load AAE_DEPLOY_KEY via ssh-agent and let uv clone in-place).
# But inside the docker build context, there's no ssh-agent and no git
# binary, so git+ssh resolution fails (`Git executable not found`).
#
# We've already COPYed the AAE packages from the build context above,
# so rewrite the lookup to use those local paths instead. The patch
# only affects the image — Stanley's working-tree pyproject.toml is
# unchanged.
RUN sed -i -E \
    -e 's|backtesting_core = \{ git = "[^"]*", rev = "[^"]*", subdirectory = "packages/backtesting_core" \}|backtesting_core = { path = "../../adaptive-alpha-engine/packages/backtesting_core" }|' \
    -e 's|prediction-engine = \{ git = "[^"]*", rev = "[^"]*", subdirectory = "packages/prediction_engine" \}|prediction-engine = { path = "../../adaptive-alpha-engine/packages/prediction_engine" }|' \
    pyproject.toml \
 && grep -E "backtesting_core|prediction-engine" pyproject.toml

# Editable install picks up backtesting_core + prediction_engine via
# the rewritten [tool.uv.sources] paths.
RUN uv pip install --system -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
