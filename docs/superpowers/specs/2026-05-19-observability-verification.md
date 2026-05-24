# Observability Verification Handbook (Plan 8)

> Stanley 自用 + AI handoff 文件。任何後續 session 接手 Plan 8 觀測棧驗證工作時，
> 從本檔可端到端重現所有檢查，無需先翻 commit history。
> 對應交付批次：T9-B（Plan 8 / 2026-05-19）。

## 1. Purpose & Scope

本手冊定義 Stanley 個人專案生態鏈中 3 個 service repo 的 Prometheus 觀測端點與告警規則的驗證流程，目標是讓未來自己或 AI agent 能在不依賴口傳脈絡的情況下，逐步確認「/metrics 健康、alerts.yml 語法正確、metric 名稱沒漂移」。

涵蓋範圍：

- `Uni-Seeker` — FastAPI 服務，`/metrics` 由 `prometheus_fastapi_instrumentator` 與 `backend/app/obs/metrics.py` 共同暴露於 `:8000`
- `sports-prophet` — APScheduler 驅動的 NBA 預測 pipeline，`prometheus_client.start_http_server` 暴露於 `:9090`
- `smart_money` — Smart Money 資料 pipeline，`prometheus_client.start_http_server` 暴露於 `:9091`

明確不在範圍：

- `adaptive-alpha-engine`（AAE）：是 library 而非 service，無 entry point，Plan 8 T8 留在 backlog
- 任何 frontend / Streamlit dashboard 觀測（屬 Plan 9 之後）
- Loki / Tempo（log + trace 後端）— 目前只有 Sentry，本批不涉及

## 2. Architecture Snapshot

| Repo | Metrics endpoint | Default port | Runtime | Metrics module | Healthcheck script |
|---|---|---:|---|---|---|
| Uni-Seeker | `http://localhost:8000/metrics` | 8000 | FastAPI (uvicorn) | `backend/app/obs/metrics.py` | `scripts/check_metrics_healthy.py` |
| sports-prophet | `http://localhost:9090/metrics` | 9090 | APScheduler (long-running CLI) | `src/sports_prophet/obs/metrics.py` | `scripts/check_metrics_healthy.py` |
| smart_money | `http://localhost:9091/metrics` | 9091 | APScheduler / cron-style jobs | `obs/metrics.py` | `scripts/check_metrics_healthy.py` |

來源 commit（Plan 8 baseline）：

- Uni-Seeker T5 — `8edd331`（Prometheus 業務指標 + `/metrics`）
- sports-prophet T6 — `36dbb48`（Prometheus + APScheduler listener）
- smart_money T7 — `704cdf0`（Prometheus + `start_http_server`）

本批新增（2026-05-19，T9-A + T10-A 並行批）：

- 3 × `scripts/check_metrics_healthy.py`
- 3 × `infra/prometheus/alerts.yml`

## 3. Decisions (this session — 2026-05-19)

本 session 對 Plan 8 open questions 的拍板紀錄。完整版見 `daily-task/2026-05-19-DailyTask.md` 的「需求脈絡」段。

- **Q2 = (c) 24/7 全 severity 都 page** — 生態鏈 cron 夜間跑（smart_money APScheduler / sports-prophet daily pipeline），不適合 office-hours silencing。alert rules 因此**沒有** `office_hours` label，也不接 Alertmanager time-based mute。
- **Q3 = (c) 用 Telegram bot DM 替代 PagerDuty** — Stanley 是個人開發者，無 on-call 排班需求；Telegram push notification 已足夠吵醒。
- **Q4 = (b) 獨立 alerts bot** — 與 sports-prophet 既有 prediction bot **不共用 token**，避免 prediction message 被 ops alert 淹沒。新 token 由 `@BotFather` 另開，對齊 Q3。

仍未決（**不在本批 scope**，列此處避免 AI agent 自行猜測）：

- **Q1** Sentry self-host vs SaaS（影響 T3 DSN policy + alert routing）
- **Q5** observability-core 抽 package 時機（目前 4 repos 各複製 `obs/`）
- **Q6** release version 來源（git SHA / pyproject version / CI env）

## 4. Verifying `/metrics` Locally (per repo)

通用前置：所有 healthcheck script 使用 stdlib `urllib`，**不需要安裝任何套件**。腳本走標準 `python` 解譯器即可。

macOS dev shell 慣例用 `python3`（系統 / Homebrew Python），CI venv 或 `uv run` 環境用 `python` 即可。

### 4.1 Uni-Seeker

啟動服務（參考 `Uni-Seeker/backend/README.md` 與 `backend/app/main.py`）：

```bash
cd /Users/stanley/stanley-project/Uni-Seeker/backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

跑 healthcheck：

```bash
cd /Users/stanley/stanley-project/Uni-Seeker
python3 scripts/check_metrics_healthy.py
```

成功輸出範例：

```
✓ /metrics healthy: <N> metric series detected (sample: uni_tier_upgrade_total, uni_tier_downgrade_total, uni_subscription_active)
```

預期至少能命中的 metric（取自 `backend/app/obs/metrics.py`）：

- `uni_tier_upgrade_total` — tier 升級轉換漏斗 Counter
- `uni_tier_downgrade_total` — 降級 / 取消 Counter
- `uni_subscription_active` — 各 tier 當前活躍訂閱 Gauge
- `uni_audit_event_total` — `audit_logs` insert Counter
- `uni_stripe_webhook_total` — Stripe webhook 結果 Counter

覆寫 target：

```bash
METRICS_URL=http://staging.example:8000/metrics python3 scripts/check_metrics_healthy.py
```

### 4.2 sports-prophet

啟動 scheduler（會在背景啟動 `start_http_server(9090)`）：

```bash
cd /Users/stanley/stanley-project/sports-prophet
uv run python scripts/run_daily.py
# 或單純跑 scheduler entrypoint（視 src/sports_prophet/scheduler/jobs.py 配置）
```

跑 healthcheck：

```bash
cd /Users/stanley/stanley-project/sports-prophet
python3 scripts/check_metrics_healthy.py
```

成功輸出範例：

```
✓ /metrics healthy: <N> metric series detected (sample: sp_collector_rows_total, sp_collector_last_success_timestamp, sp_job_duration_seconds)
```

預期至少能命中的 metric（取自 `src/sports_prophet/obs/metrics.py`）：

- `sp_collector_rows_total` — collector 抓取列數 Counter，labels `(collector, outcome)`
- `sp_collector_last_success_timestamp` — 最後一次成功 collector 的 unix ts Gauge
- `sp_job_duration_seconds` — APScheduler job 執行時長 Histogram
- `sp_job_total` — APScheduler job 結果 Counter，labels `(job_name, outcome)`
- `sp_model_ic` / `sp_calibration_brier_score` — 模型品質 Gauge

覆寫 target：

```bash
METRICS_URL=http://localhost:9090/metrics python3 scripts/check_metrics_healthy.py
```

### 4.3 smart_money

啟動 pipeline（會 `start_http_server(9091)`）：

```bash
cd /Users/stanley/stanley-project/smart_money
uv run python -m smart_money.main
# 或對應的 collector / aggregator entrypoint
```

跑 healthcheck：

```bash
cd /Users/stanley/stanley-project/smart_money
python3 scripts/check_metrics_healthy.py
```

成功輸出範例：

```
✓ /metrics healthy: <N> metric series detected (sample: sm_collector_events_total, sm_collector_last_run_timestamp, sm_aggregator_duration_seconds)
```

預期至少能命中的 metric（取自 `smart_money/obs/metrics.py`）：

- `sm_collector_events_total` — `SmartMoneyEvent` 列數 Counter，labels `(collector, source_market, outcome)`
- `sm_collector_last_run_timestamp` — 最後成功 collector 的 unix ts Gauge
- `sm_aggregator_duration_seconds` — slow / fast aggregator 執行時長 Histogram
- `sm_archive_oldest_event_age_days` — 最舊 live row 年齡 Gauge
- `sm_weight_trainer_ic_score` — Ridge weight trainer 最新 IC Gauge

覆寫 target：

```bash
METRICS_URL=http://localhost:9091/metrics python3 scripts/check_metrics_healthy.py
```

### 4.4 Healthcheck script 退出碼合約

所有 3 個 script 共用：

| Exit code | 條件 |
|---:|---|
| `0` | HTTP 200 且 body 含至少 1 個 `EXPECTED_METRICS` 內的名稱 |
| `1` | 連線失敗 / timeout（5s） / 非 200 status / body 無預期 metric |

CI 接法：直接 `python scripts/check_metrics_healthy.py`，非 0 退出 = fail。

## 5. Validating Alert Rules

### 5.1 安裝 promtool

本機目前**沒有**安裝 `promtool`、`amtool`、`docker`。macOS 安裝：

```bash
brew install prometheus
# 同時提供 promtool 與 prometheus binary
which promtool
# /opt/homebrew/bin/promtool（Apple Silicon）或 /usr/local/bin/promtool（Intel）
```

### 5.2 跑 syntax + semantic check

每個 repo：

```bash
cd /Users/stanley/stanley-project/Uni-Seeker
promtool check rules infra/prometheus/alerts.yml

cd /Users/stanley/stanley-project/sports-prophet
promtool check rules infra/prometheus/alerts.yml

cd /Users/stanley/stanley-project/smart_money
promtool check rules infra/prometheus/alerts.yml
```

預期輸出：

```
Checking infra/prometheus/alerts.yml
  SUCCESS: 1 rules found
```

（Uni-Seeker 為 3 條規則，sports-prophet / smart_money 為 2 條規則。）

### 5.3 Per-repo alert inventory

#### Uni-Seeker (`infra/prometheus/alerts.yml`, group `uni-seeker-alerts`)

| Alert | Expr | Severity | Metric source |
|---|---|---|---|
| `ServiceDown` | `up{job="uni-seeker"} == 0` for 1m | critical | Prometheus scrape liveness |
| `HighErrorRate` | `sum(rate(http_requests_total{job="uni-seeker",status=~"5.."}[5m])) > 0.1` for 5m | critical | `prometheus_fastapi_instrumentator` 自動暴露 |
| `AuditBurst` | `sum(rate(uni_audit_event_total[1m])) > 50` for 2m | warning | `backend/app/obs/metrics.py` AUDIT_EVENT_TOTAL |

#### sports-prophet (`infra/prometheus/alerts.yml`, group `sports-prophet-alerts`)

| Alert | Expr | Severity | Metric source |
|---|---|---|---|
| `ServiceDown` | `up{job="sports-prophet"} == 0` for 1m | critical | Prometheus scrape liveness |
| `HighErrorRate` | `sum(rate(sp_job_total{outcome="fail"}[5m])) > 0.1` for 5m | critical | APScheduler listener (`sp_job_total`) |

#### smart_money (`infra/prometheus/alerts.yml`, group `smart-money-alerts`)

| Alert | Expr | Severity | Metric source |
|---|---|---|---|
| `ServiceDown` | `up{job="smart-money"} == 0` for 1m | critical | Prometheus scrape liveness |
| `HighErrorRate` | `sum(rate(sm_collector_events_total{outcome="error"}[5m])) > 0.1` for 5m | critical | `smart_money/obs/metrics.py` COLLECTOR_EVENTS_TOTAL |

### 5.4 已知 caveat — outcome label 用詞未鎖死

- `sports-prophet` 的 APScheduler listener 寫死 `outcome="ok"` / `outcome="fail"`（見 `src/sports_prophet/obs/metrics.py:73`）。alert 使用 `outcome="fail"`，**一致**。
- `smart_money` 的 `sm_collector_events_total` 在 `obs/metrics.py` **僅宣告 label 名稱**（`collector / source_market / outcome`）但未於 module 內固定 value vocabulary。alert 使用 `outcome="error"`。
- **wiring 時必須核對**：當 collector 真實 call site 落地時，要決定用 `"error"` 還是 `"fail"` 並更新 alert expr。若決定改用 `"fail"`，需同步修改 `smart_money/infra/prometheus/alerts.yml` 第 22 行。
- 建議：commit call site 同時跑 `promtool check rules` + 對著實機 `/metrics` `grep outcome=` 確認。

## 6. End-to-End Alert Test

告警鏈路（Batch C 落地後）：

```
Prometheus (eval infra/prometheus/alerts.yml)
  └── fires alert (severity=critical|warning, labels: service, team)
        └── Alertmanager (route by severity, infra/alertmanager/alertmanager.yml)
              └── webhook POST /alertmanager/webhook
                    └── scripts/alerts_tg_relay.py (Starlette app on :8888)
                          └── TelegramBot.send_message() — 復用 sports-prophet 現有 bot
                                └── Telegram chat (ALERTS_CHAT_ID 或 TELEGRAM_CHAT_ID)
```

### 6.1 檔案索引（sports-prophet）

- `/Users/stanley/stanley-project/sports-prophet/scripts/alerts_tg_relay.py` — webhook receiver，~120 lines
- `/Users/stanley/stanley-project/sports-prophet/infra/alertmanager/alertmanager.yml` — routing + inhibit rules
- `/Users/stanley/stanley-project/sports-prophet/src/sports_prophet/output/telegram_bot.py` — 既有 `TelegramBot.send_message`，本批僅 import 重用，**未改動**

### 6.2 環境變數

| Var | 必填 | 說明 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | 是 | @BotFather token（Q4 = 獨立 alerts bot） |
| `ALERTS_CHAT_ID` | 否 | 專用 alerts chat；未設則 fallback `TELEGRAM_CHAT_ID` |
| `TELEGRAM_CHAT_ID` | 條件 | 至少 `ALERTS_CHAT_ID` 與本變數其一必填 |
| `RELAY_PORT` | 否 | 預設 8888（避開 sports-prophet app 用的 8000） |

### 6.3 本機驗證流程

```bash
# 1) 啟動 relay
cd /Users/stanley/stanley-project/sports-prophet
uv run python scripts/alerts_tg_relay.py
# → 監聽 0.0.0.0:8888，GET / 回 {"status":"ok"}

# 2) 驗證 alertmanager.yml（需先 brew install prometheus 取得 amtool）
amtool check-config infra/alertmanager/alertmanager.yml

# 3) 注入測試告警
amtool alert add alertname=ServiceDown severity=critical service=sports-prophet \
  --annotation=summary="manual test" --annotation=description="e2e relay check"

# 4) 觀察 Telegram chat 是否收到「🔴 [OPS] CRITICAL: ServiceDown」訊息
```

### 6.4 跨 repo 監控棧（deferred）

本批僅交付 sports-prophet 內的 relay + alertmanager.yml。實際把 Prometheus / Alertmanager / relay 串成 docker-compose 服務、同時監控 3 個 repo，延到 **Plan 8 T10b**：

- `Uni-Seeker/docs/superpowers/plans/2026-05-19-plan-8-t10b-monitoring-stack.md`（另一 agent 撰寫中）

## 7. CI Integration (recommendation)

Plan 8 T11 已在每個 repo 加 `.github/workflows/obs-gate.yml`（ruff T20 + Sentry DSN policy 檢查）。建議下一輪 obs-gate.yml 加：

1. **啟動服務的 background step** — 用 `uv run uvicorn ... &` 或對應 entrypoint
2. **`sleep 3`** 等 `/metrics` 起來
3. **`python scripts/check_metrics_healthy.py`** — 非 0 即 fail CI
4. **`promtool check rules infra/prometheus/alerts.yml`** — alert syntax gate

此項目尚未實作，標記為 **backlog**（不在本批 scope）。對應追蹤項：未來 `Plan 8 T11 follow-up`。

CI 環境變數參考：

```yaml
- name: Healthcheck /metrics
  env:
    METRICS_URL: http://localhost:8000/metrics
  run: python scripts/check_metrics_healthy.py
```

## 8. Troubleshooting Cheat Sheet

| 症狀 | 訊息 / 觀察 | 一句話排查 |
|---|---|---|
| Connection refused | `✗ Could not reach http://localhost:PORT/metrics: [Errno 61]` | 服務沒起 — 檢查 uvicorn / scheduler process 是否還活著 |
| Timeout | `✗ /metrics timed out after 5.0s` | 服務起了但卡 startup — 查 app log 是否還在 import / migrate |
| HTTP 4xx / 5xx | `✗ /metrics returned HTTP <code>` | 大概率是 reverse proxy 把 `/metrics` 路由錯了，或 FastAPI 加了 auth 把 `/metrics` 也擋掉 |
| No expected metric found | `✗ /metrics responded 200 but no expected uni_* metrics found` | metrics module rename 了 — 更新 script 內 `EXPECTED_METRICS` list 與本手冊 §4.x 同步 |
| `ServiceDown` 一直 firing | alert 持續 active 但服務明明在跑 | 檢查 prometheus.yml 的 `scrape_configs.job_name` 是否真的等於 alert expr 裡的 `job="<name>"`（Uni-Seeker = `uni-seeker`、sports-prophet = `sports-prophet`、smart_money = `smart-money`） |
| `HighErrorRate` 永遠 0 | alert 從未觸發 | sports-prophet / smart_money 的 outcome label 拼字不一致；參考 §5.4，對著 live `/metrics` `grep outcome=` 核對 |
| `AuditBurst` 一啟動就 fire | `uni_audit_event_total` rate 異常高 | 多半是 import 階段 backfill 或 test fixture 沒清；確認 production AUDIT 寫入頻率 |
| promtool 找不到 | `command not found: promtool` | macOS：`brew install prometheus`；CI：用 `prom/prometheus` docker image 跑 |

## 9. Related Files Index

本批（2026-05-19）新增：

- `/Users/stanley/stanley-project/Uni-Seeker/scripts/check_metrics_healthy.py`
- `/Users/stanley/stanley-project/sports-prophet/scripts/check_metrics_healthy.py`
- `/Users/stanley/stanley-project/smart_money/scripts/check_metrics_healthy.py`
- `/Users/stanley/stanley-project/Uni-Seeker/infra/prometheus/alerts.yml`
- `/Users/stanley/stanley-project/sports-prophet/infra/prometheus/alerts.yml`
- `/Users/stanley/stanley-project/smart_money/infra/prometheus/alerts.yml`

Plan 8 T5–T7 既有 metrics 模組（本手冊引用）：

- `/Users/stanley/stanley-project/Uni-Seeker/backend/app/obs/metrics.py`
- `/Users/stanley/stanley-project/sports-prophet/src/sports_prophet/obs/metrics.py`
- `/Users/stanley/stanley-project/smart_money/obs/metrics.py`

Session handoff / 決策來源：

- `/Users/stanley/stanley-project/daily-task/2026-05-19-DailyTask.md`（「需求脈絡」段含 Q2/Q3/Q4 完整決議）

待補（Batch C ship 後回來更新本檔 §6）：

- `/Users/stanley/stanley-project/sports-prophet/infra/alertmanager/alertmanager.yml`
- `/Users/stanley/stanley-project/sports-prophet/scripts/alerts_tg_relay.py`
