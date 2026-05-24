#!/bin/bash
# Generate TypeScript types from backend OpenAPI spec.
#
# Prerequisite: backend must be running and serving /api/openapi.json.
#   cd backend && uv run uvicorn app.main:app --port 8000
#
# Usage:
#   ./scripts/gen-api-types.sh                              (default: http://localhost:8000)
#   API_URL=http://staging.example.com ./scripts/gen-api-types.sh
#
# Output: src/lib/api/generated/schema.d.ts

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
OUTPUT="src/lib/api/generated/schema.d.ts"

# Resolve to frontend root regardless of where script is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$FRONTEND_ROOT"

mkdir -p "$(dirname "$OUTPUT")"

echo "Fetching OpenAPI spec from $API_URL/api/openapi.json ..."
npx --no-install openapi-typescript "$API_URL/api/openapi.json" --output "$OUTPUT"

echo "Generated: $FRONTEND_ROOT/$OUTPUT"
