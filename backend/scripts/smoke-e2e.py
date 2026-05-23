#!/usr/bin/env python3
"""End-to-end real-user smoke against a live backend.

Exercises the full user journey through real uvicorn (NOT pytest TestClient):
register → login → /auth/me → create account → create trade → positions →
summary KPI → subscribe Berkshire filer → list filers.

Catches P0 bugs that mocked tests miss — pytest TestClient bypasses the
ASGI lifespan, middleware-after-startup checks, CORS preflight, real DB
transaction boundaries, and JWT verification end-to-end.

Usage:
    # default targets http://localhost:8000
    python backend/scripts/smoke-e2e.py

    # against staging
    API_URL=https://staging.example.com python backend/scripts/smoke-e2e.py

Exit 0 if all checks pass, 1 otherwise.
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get("API_URL", "http://localhost:8000").rstrip("/") + "/api/v1"
EMAIL = f"smoke+{int(time.time())}@uni-seeker.test"
PASSWORD = "Smoke-Test-2026!"
USERNAME = f"smoke{int(time.time())}"

token: str | None = None
results: list[tuple[str, bool, str]] = []


def req(method: str, path: str, body: dict | None = None, auth: bool = False) -> tuple[int, dict | str]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if auth and token:
        headers["Authorization"] = f"Bearer {token}"
    req_obj = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req_obj, timeout=10) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:
        return 0, f"ERR {type(e).__name__}: {e}"


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}{(' — ' + detail) if detail else ''}")


# 1. Register
status, body = req("POST", "/auth/register", {
    "email": EMAIL, "password": PASSWORD, "username": USERNAME,
})
check("register", status in (200, 201), f"status={status}")

# 2. Login
status, body = req("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})
token = body.get("access_token") if isinstance(body, dict) else None
check("login", status == 200 and bool(token), f"status={status} has_token={bool(token)}")

# 3. /auth/me
status, body = req("GET", "/auth/me", auth=True)
me_email = body.get("email") if isinstance(body, dict) else None
check("auth/me", status == 200 and me_email == EMAIL, f"status={status} email={me_email}")

# 4. Add account
status, body = req("POST", "/holdings/accounts", {
    "name": "永豐 Test",
    "market": "TW_TWSE",
    "broker": "SinoPac",
    "currency": "TWD",
}, auth=True)
account_id = body.get("id") if isinstance(body, dict) else None
check("create account", status in (200, 201) and account_id, f"status={status} id={account_id}")

# 5. Add trade (BUY 2330 @ 580 × 1000)
status, body = req("POST", "/holdings/trades", {
    "account_id": account_id,
    "action": "BUY",
    "symbol": "2330",
    "market": "TW_TWSE",
    "qty": "1000",
    "price": "580",
    "trade_date": "2026-05-24",
}, auth=True)
trade_id = body.get("id") if isinstance(body, dict) else None
check("create trade", status in (200, 201) and trade_id, f"status={status} id={trade_id}")

# 6. KPI: GET /holdings/positions
status, body = req("GET", "/holdings/positions", auth=True)
positions = body if isinstance(body, list) else (body.get("positions", []) if isinstance(body, dict) else [])
found_2330 = any(p.get("symbol") == "2330" for p in positions) if positions else False
check("positions has 2330", status == 200 and found_2330, f"status={status} count={len(positions)} found={found_2330}")

# 7. KPI: GET /holdings/summary
status, body = req("GET", "/holdings/summary", auth=True)
total_cost = body.get("total_cost") if isinstance(body, dict) else None
check("summary has total_cost", status == 200 and total_cost, f"status={status} total_cost={total_cost}")

# 8. Subscribe Berkshire filer (CIK 0001067983)
#    `name` is REQUIRED for unknown CIKs — see F13SubscribeRequest.name docstring.
#    UI flow always supplies `name` from EDGAR search; smoke mimics that contract.
status, body = req("POST", "/institutional/filers", {
    "cik": "0001067983",
    "name": "BERKSHIRE HATHAWAY INC",
}, auth=True)
filer_id = body.get("filer", {}).get("id") if isinstance(body, dict) else None
check("subscribe filer", status in (200, 201) and filer_id, f"status={status} filer_id={filer_id}")

# 9. GET /institutional/filers (verify subscription persisted)
status, body = req("GET", "/institutional/filers", auth=True)
subs = body if isinstance(body, list) else []
found_berk = any(f.get("cik") == "0001067983" for f in subs) if subs else False
check("filers list has Berkshire", status == 200 and found_berk, f"status={status} count={len(subs)}")

# Summary
print("---")
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"{passed}/{total} pass")
sys.exit(0 if passed == total else 1)
