# 2026-05-27 DailyTask

## 主任務 (Parent Ticket)

**E2E-4** — External API smoke nightly cron（FinMind / yfinance / Stripe sig）

## 需求脈絡 (Requirement Context)

### Q1: Why

後端整合 FinMind / Stripe / yfinance 三個外部資料源，現行 unit/integration 測試都用 `unittest.mock` 把它們擋掉。若上游悄悄改 schema（rename 欄位、改回傳結構），unit test 不會壞，prod 才會吐 500 — 沒有早期警報。

### Q2: Definition of Success

- 新增獨立 nightly GitHub Actions workflow，cron `0 3 * * *`（11am Taipei）+ workflow_dispatch
- 三支 smoke test 各打真實上游（FinMind public dataset、yfinance AAPL、Stripe 簽章驗證）
- 失敗時 Telegram 告警（secret 缺則靜默 skip alert，CI 仍紅）
- 一般 pytest 不收集這批，避免拖慢 backend-ci

### Q3: Scope-out

- 不打 Stripe live API（不會扣款、不會改 Stanley 帳號狀態），只驗本地簽章碼
- 不引新依賴（已有 requests/httpx）
- 不做監控 dashboard / Sentry hookup（本輪只要 nightly CI + TG）
- 不改現有 mocked unit test

## 團隊單 (Team Subtasks)

### #1 [E2E-4][subtask] Nightly external smoke workflow

- 狀態: `todo`
- DoD:
  - [ ] `.github/workflows/external-api-smoke.yml` 存在、cron 設定正確、TG 告警 step gracefully skip on missing secret
  - [ ] `backend/tests/external_smoke/` 三支 test + `__init__.py` + `conftest.py`
  - [ ] `backend/pyproject.toml` 把 `external_smoke` 從預設 collection 排除
  - [ ] 一般 `pytest --collect-only` 不撈到 external_smoke
  - [ ] PR 開好回傳 URL

## 內部步驟 (Internal WBS)

### Batch A — Smoke test 檔案（可平行寫）

- **T1.1** `tests/external_smoke/__init__.py`（空檔）— 狀態: `todo`
- **T1.2** `tests/external_smoke/conftest.py`（60s timeout fixture）— 狀態: `todo`
- **T1.3** `tests/external_smoke/test_finmind_smoke.py` — 狀態: `todo`
- **T1.4** `tests/external_smoke/test_yfinance_smoke.py` — 狀態: `todo`
- **T1.5** `tests/external_smoke/test_stripe_smoke.py` — 狀態: `todo`

### Batch B — Config & workflow（依賴 A 命名）

- **T2.1** `backend/pyproject.toml` 加 `--ignore=tests/external_smoke` — 狀態: `todo`
- **T2.2** `.github/workflows/external-api-smoke.yml` — 狀態: `todo`

### Batch C — Verify & PR

- **T3.1** `pytest --collect-only` 確認排除生效 — 狀態: `todo`
- **T3.2** local FinMind smoke run（best effort）— 狀態: `todo`
- **T3.3** yaml lint via `python -c "import yaml; yaml.safe_load(...)"` — 狀態: `todo`
- **T3.4** self-review skill 6 dim → commit → PR — 狀態: `todo`

## Layer Mapping

| 團隊單 | 內部步驟 |
|--------|----------|
| #1 | T1.1-T1.5, T2.1-T2.2, T3.1-T3.4 |

## 已完成 (Completed)

(none)

## Blockers

(none)

## Decisions

- Stripe smoke 不打 live API — 只驗本地簽章邏輯對上 Stripe 官方 doc 的 reference payload（避免改 Stanley 帳號狀態）
- yfinance 不穩 → 用 `pytest.xfail` 包，避免上游空回應就 CI 紅
- TG 告警 step 用 `if: failure() && env.TG_TOKEN != ''` 模式，secret 缺就靜默
