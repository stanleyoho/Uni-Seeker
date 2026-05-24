# Generated API Types

Auto-generated TypeScript types from the backend's OpenAPI 3.1 spec
(`FastAPI` -> `/api/openapi.json`).

The committed `schema.d.ts` is the authoritative typed contract for HTTP
requests/responses. Regenerate after every backend schema change.

## Regenerate

Backend must be running locally:

```bash
cd backend
uv run uvicorn app.main:app --port 8000
```

Then, from `frontend/`:

```bash
npm run gen:api-types
```

To target a non-local backend:

```bash
API_URL=http://staging.example.com npm run gen:api-types
```

## Usage

```ts
import type { paths, components } from "@/lib/api/generated/schema";

// 1) Endpoint response body (200 application/json)
type FilersList =
  paths["/api/v1/institutional/filers"]["get"]["responses"]["200"]["content"]["application/json"];

// 2) Reusable component schema
type F13Filer = components["schemas"]["F13FilerResponse"];

// 3) Request body
type LoginBody =
  paths["/api/v1/auth/login"]["post"]["requestBody"]["content"]["application/json"];

// 4) Path / query parameters
type StockParams =
  paths["/api/v1/stocks/{ticker}"]["get"]["parameters"]["path"];
```

The existing `apiFetch<T>` wrapper in `src/lib/api-client.ts` remains the
runtime fetch helper. Pass a generated type as the type parameter to get
end-to-end type-safety without changing call sites:

```ts
import { apiFetch } from "@/lib/api-client";
import type { paths } from "@/lib/api/generated/schema";

type FilersList =
  paths["/api/v1/institutional/filers"]["get"]["responses"]["200"]["content"]["application/json"];

const data = await apiFetch<FilersList>("/api/v1/institutional/filers");
```

## Migration Strategy

`src/lib/api-client.ts` keeps its hand-written interfaces and remains the
authoritative type source for now. Generated types are additive:

- New endpoints / new screens -> use generated types directly.
- After a backend schema change -> regenerate, then reconcile any manual
  interfaces that diverged.
- Phase 7+ goal -> remove the hand-written interfaces and rely solely on the
  generated `components["schemas"][...]` aliases.

## Limitations

- `openapi-typescript` emits **types only**; no runtime fetch wrapper.
  Continue using `apiFetch<T>` from `api-client.ts`.
- Decimal-as-string fields appear as `string` (correct; pass through
  `Number()` before arithmetic per `CLAUDE.md`).
- File-download endpoints (CSV exports) are typed as
  `application/octet-stream` -- handle the response as a `Blob` manually.
- The first generated build replaces this stub file; do not hand-edit
  `schema.d.ts`.
