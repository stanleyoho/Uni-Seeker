# Plan 8 T10b — Cross-Repo Monitoring Stack (Design)

> 設計文件，**非實作**。對應 Plan 8 觀測棧 backlog 項目，將 Batch C 留下的「告警規則 + relay 程式碼」拼接成可實際 fire 的端到端鏈路。
> 讀者：未來的 Stanley（單人維護者）、後續 session 接手的 AI agent。

## 1. Status

**Backlog**。於 2026-05-19 自 Plan 8 T10 Batch C 切出。

- **觸發條件**：當 Stanley 想要 real 24/7 alerting — 也就是希望「停一個服務 → 手機收到 Telegram 通知」這條鏈路真正運作時。
- **目前狀態**：alert rules（`infra/prometheus/alerts.yml` × 3 repos）+ Alertmanager 設定（`infra/alertmanager/alertmanager.yml`）+ relay 程式碼（`scripts/alerts_tg_relay.py`）已存在於 filesystem，但沒有任何 Prometheus 程序在跑來執行這些規則。換言之：**規則是設計好的，但沒部署**。
- **預估啟動時機**：在 Plan 8 T11 follow-up（CI gate 加 metrics healthcheck）完成後，或當 Stanley 第一次因為服務故障沒收到通知而想補上監控時。

## 2. Problem Statement

Plan 8 T10 Batch C 在 `sports-prophet` repo 完成了以下交付：

- `sports-prophet/infra/alertmanager/alertmanager.yml` — Alertmanager 路由設定，所有 high-severity 走 webhook 到 relay
- `sports-prophet/scripts/alerts_tg_relay.py` — Webhook → Telegram Bot API 的轉發程式
- `sports-prophet/infra/prometheus/alerts.yml` — sports-prophet 的 2 條規則（ServiceDown / HighErrorRate）
- 對應 `Uni-Seeker/infra/prometheus/alerts.yml`（3 條規則）與 `smart_money/infra/prometheus/alerts.yml`（2 條規則）— 由 T10-A4 並行交付

但是端到端鏈路目前**無法 fire**，因為：

1. `sports-prophet/docker-compose.yml` 目前的 services 只有 `db / db-backup / datasette / sports-prophet / predict / dashboard` — **沒有 prometheus、沒有 alertmanager**。
2. 即使在 `sports-prophet/docker-compose.yml` 內加進 prometheus，它也**只能 scrape sports-prophet 自己**（port 9090）：
   - `smart_money`（port 9091）住在另一個 repo、另一個 docker-compose（或根本沒有 compose、直接 `uv run` 跑 APScheduler）
   - `Uni-Seeker`（port 8000）住在第三個 repo
3. 三個 repo = 三個獨立的 docker network island。`sports-prophet/docker-compose.yml` 裡的 `sp-internal` bridge network 無法 reach 其他兩個 repo 的 container DNS。
4. T10-A4 的 alert rules 是**跨 repo 的（job="uni-seeker" / job="sports-prophet" / job="smart-money"）**，必須有一個 Prometheus 同時 scrape 三個來源才能讓所有規則一起 evaluate。

Batch C 當時刻意不解這個問題，因為兩條路都很重：

- **路 A**（把 monitoring 塞進 sports-prophet）：只能監到 1/3，且耦合到單一業務 repo 的生命週期。
- **路 B**（跨 repo refactor 把三個 docker-compose 接到共用 network）：要動到三個 repo 的 networking，超出單一 session 的範圍。

因此延後到 T10b — 在獨立的 `monitoring/` 子資料夾完成這件事。

## 3. Proposed Architecture

### 3.1 Location

新增 top-level subfolder：

```
/Users/stanley/stanley-project/
├── Uni-Seeker/
├── sports-prophet/
├── smart_money/
├── adaptive-alpha-engine/
├── daily-task/
└── monitoring/         ← 新增，本 plan 的目標
    ├── docker-compose.yml
    ├── prometheus/
    │   └── prometheus.yml
    ├── alertmanager/
    │   └── alertmanager.yml   （或 symlink 到 sports-prophet 既有檔）
    ├── relay/
    │   └── alerts_tg_relay.py（或 symlink）
    ├── .env                    （TG token 與 chat_id；不 commit）
    └── README.md
```

`monitoring/` 是 standalone 的 — 自己的 docker-compose，**不掛在任何 service repo 下**。與 `Uni-Seeker / sports-prophet / smart_money` 平輩。

### 3.2 Components

| Component | 角色 | 來源 |
|---|---|---|
| `prometheus` | scrape 三個服務的 /metrics + 載入各 repo 的 alerts.yml + evaluate rules | 官方 image `prom/prometheus:latest` |
| `alertmanager` | 接收 Prometheus 觸發的 alert、做 routing、發 webhook | 官方 image `prom/alertmanager:latest`，設定檔來自 `sports-prophet/infra/alertmanager/alertmanager.yml`（symlink 或 copy） |
| `alerts-tg-relay` | 接收 alertmanager webhook → Telegram Bot API | `sports-prophet/scripts/alerts_tg_relay.py`（symlink 或 copy 一份） |
| `grafana`（phase 3，可選） | dashboard | 官方 image `grafana/grafana:latest` |

### 3.3 Why Standalone (not embedded in sports-prophet)

- **獨立生命週期**：monitoring stack 升 Prometheus 版本不應該需要重啟 sports-prophet 的 db / scheduler。反向亦然 — sports-prophet schema migration 不應該影響 monitoring。
- **不耦合到單一業務 repo**：如果哪天 sports-prophet 退役，monitoring 還能繼續監其他兩個。
- **可擴展到 N service repos**：之後若再加第四個服務（例如 AAE 變成 service），只要在 `monitoring/prometheus/prometheus.yml` 加一個 job，不用動其他 repo。
- **比較好 tear down**：monitoring 升級 / 重啟只影響 monitoring 容器自己。
- **權責清楚**：sports-prophet/docker-compose.yml 的角色是「跑 NBA 預測 pipeline」，不該背監控責任。

## 4. Network Topology

三個方案。先快速比較，最後給 phase 1 推薦。

### 4.1 Option A — Host networking

讓 prometheus container 直接用 host network，scrape `localhost:8000 / 9090 / 9091`。

- 優點：零設定。
- 缺點：
  - macOS / Windows Docker Desktop 不支援 `network_mode: host`（只 Linux 支援）。Stanley 本機 macOS，直接出局。
  - 與 host 上其他 process 共用 port，容易撞 port。
  - 失去 docker network 隔離。

→ **淘汰**。

### 4.2 Option B — Shared external docker network

宣告一個外部 docker network `stanley-monitoring`，三個 service repo 的 docker-compose 都加入：

```yaml
# 在 Uni-Seeker / sports-prophet / smart_money 各自的 docker-compose.yml 加：
networks:
  stanley-monitoring:
    external: true
```

且 service container 都接上這個 network。然後 `monitoring/docker-compose.yml` 的 prometheus 用 `service_name:port`（docker DNS）scrape。

- 優點：production-grade、隔離乾淨、scale 到雲端時行為一致。
- 缺點：
  - 要動三個 repo 的 docker-compose（破壞「不動 service repo」的 Batch C 約束）。
  - `smart_money` 目前可能根本沒有 docker-compose（用 `uv run` 跑 APScheduler）；要先 dockerize。
  - 維護成本高 — 每個 repo 都得記得這個 external network。

### 4.3 Option C — Localhost port forwarding via `host.docker.internal`

macOS / Windows 的 Docker Desktop 提供 `host.docker.internal` 這個 DNS 名稱，container 內可以解析到 host 的 IP。三個服務既然已經把 metrics port expose 到 host（dev 環境本來就有），prometheus 直接 scrape：

- `host.docker.internal:8000` → Uni-Seeker
- `host.docker.internal:9090` → sports-prophet
- `host.docker.internal:9091` → smart_money

- 優點：
  - **零變動到其他 repo** — 完全保留 Batch C 的「不動 service repo」原則。
  - 跨 docker-compose / 跨 repo / 跨「沒 docker」（smart_money APScheduler 直接 host 跑）一視同仁。
  - dev 友善 — 服務怎麼跑（docker、`uv run`、`launchctl`）都不影響。
- 缺點：
  - 不適合 Linux production（Linux 的 `host.docker.internal` 需要加 `extra_hosts: ["host.docker.internal:host-gateway"]` workaround）。
  - 失去 docker network 隔離；prometheus 看到的是 host 的 port，需要 host port 沒被別人佔走。

### Recommendation

- **Phase 1**：**Option C**。零侵入、最快上線、與既有「dev 用 host port 直連」習慣一致。Linux 部署時再評估。
- **Phase 3 / 上雲時**：升級到 **Option B**。屆時 service repo 已較穩定，refactor cost 可接受。

## 5. Scrape Config (Phase 1 sample)

`monitoring/prometheus/prometheus.yml` 預期形狀（不是完整檔，是讓讀者抓到形狀）：

```yaml
global:
  scrape_interval: 30s
  evaluation_interval: 30s

rule_files:
  - /etc/prometheus/rules/uni-seeker-alerts.yml
  - /etc/prometheus/rules/sports-prophet-alerts.yml
  - /etc/prometheus/rules/smart-money-alerts.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: uni-seeker
    metrics_path: /metrics
    static_configs:
      - targets: ["host.docker.internal:8000"]

  - job_name: sports-prophet
    metrics_path: /metrics
    static_configs:
      - targets: ["host.docker.internal:9090"]

  - job_name: smart-money
    metrics_path: /metrics
    static_configs:
      - targets: ["host.docker.internal:9091"]
```

對應的 volume mount 策略（`monitoring/docker-compose.yml` 的 prometheus service）：

```yaml
volumes:
  - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
  - ../Uni-Seeker/infra/prometheus/alerts.yml:/etc/prometheus/rules/uni-seeker-alerts.yml:ro
  - ../sports-prophet/infra/prometheus/alerts.yml:/etc/prometheus/rules/sports-prophet-alerts.yml:ro
  - ../smart_money/infra/prometheus/alerts.yml:/etc/prometheus/rules/smart-money-alerts.yml:ro
```

**關鍵 point**：規則檔以 `:ro` 直接 mount 進 prometheus container，**不複製檔案**。這樣 alert rule 的 source of truth 還是各自 repo（rule 屬於 service 本身的責任），monitoring stack 只是「載入並執行」。各 repo 修改 alerts.yml → 重啟 prometheus（或 hot reload `curl -X POST localhost:9090/-/reload`）即可。

對 alertmanager 配置與 relay 程式碼採取同樣策略 — symlink 或 readonly mount，避免 drift。

## 6. Rollout Plan

三 phase 漸進式，每 phase 都有獨立的 acceptance test。**不要試圖一次接三個服務**。

### Phase 1 — sports-prophet only（估時 ~1h）

1. 建立 `monitoring/` 目錄結構（docker-compose + prometheus.yml + README）
2. `monitoring/docker-compose.yml` 起 `prometheus + alertmanager + alerts-tg-relay` 三個服務
3. prometheus 只配一個 job：`sports-prophet` via `host.docker.internal:9090`
4. mount sports-prophet 的 alerts.yml 為唯一規則檔
5. Verify Targets page（`http://localhost:9090/targets`）顯示 sports-prophet `UP`
6. Verify Rules page 顯示 2 條 sports-prophet rules 都 loaded
7. **Acceptance**：手動 `docker stop sports-prophet` → 1 分鐘內 Telegram 收到 ServiceDown 通知（emoji + `[OPS]` prefix）

### Phase 2 — add smart_money（估時 ~30min）

1. 確認 smart_money 在 host 上跑（`uv run python -m smart_money.main`）且 `:9091/metrics` 從 host 可訪問
2. 在 `monitoring/prometheus/prometheus.yml` 加 `smart-money` job
3. 加 mount：`../smart_money/infra/prometheus/alerts.yml` → `/etc/prometheus/rules/smart-money-alerts.yml`
4. 重啟 prometheus 或 reload
5. **Acceptance**：手動停 smart_money（kill 該 process）→ TG 收到 smart-money ServiceDown alert

### Phase 3 — add Uni-Seeker（估時 ~30min）

1. 確認 Uni-Seeker FastAPI 在 host 跑（`uv run uvicorn app.main:app --port 8000`）
2. 加 `uni-seeker` job 到 prometheus.yml
3. 加 mount Uni-Seeker 的 alerts.yml
4. **Acceptance**：停 Uni-Seeker → TG 收到 uni-seeker ServiceDown alert
5. （可選）加 Grafana：mount prometheus 為 data source，import community NBA / FastAPI dashboard。**本 plan 不展開細節，列在 §7 open question。**

## 7. Open Questions (to decide at start of T10b)

開工前先問自己這 6 題：

1. **Storage**：prometheus TSDB 用 docker volume（managed by docker）還是 host bind mount（`./prometheus/data`）？影響 backup 策略 — bind mount 較好備份但要管權限。
2. **Retention**：prometheus 預設 15 天。要拉長到 30 天 / 90 天嗎？個人專案不太需要長期 trace，先 15 天即可，但要寫死還是參數化？
3. **Grafana**：phase 3 加 vs 永遠不加？Stanley 個人專案以 alert 為主，dashboard 是「看了爽」需求，不是運維必要。
4. **Auth**：prometheus / alertmanager web UI 預設無 auth。本機 dev 沒問題；若日後 expose 出 LAN / 公網，需 reverse proxy（caddy / nginx + basic auth）。Phase 1 假設 localhost-only。
5. **Repo strategy**：`monitoring/` 是自己一個 git repo 還是純子資料夾？子資料夾簡單但無 history isolation；獨立 repo 較正規但多一個維護負擔。建議子資料夾起手。
6. **Secrets**：relay 需要 Telegram bot token（`ALERTS_TG_BOT_TOKEN`）+ chat_id（`ALERTS_CHAT_ID`）。目前 token 住在 `sports-prophet/.env`。monitoring stack 怎麼讀？
   - 方案 a：`monitoring/.env` 獨立一份（手動同步 — 易 drift）
   - 方案 b：symlink `sports-prophet/.env` → `monitoring/.env`（耦合到 sports-prophet 存在）
   - 方案 c：建立 `~/.stanley-secrets/alerts.env`，兩邊都載（cleanest，但要建新路徑）
   - **建議**：phase 1 用方案 a 起手，phase 3 改方案 c。

## 8. Acceptance Criteria for T10b Done

整個 plan 完成的條件（不是 phase 1 的，是整個 T10b done 才打勾）：

- [ ] `/Users/stanley/stanley-project/monitoring/` 存在，包含 `docker-compose.yml` + `prometheus/prometheus.yml` + alertmanager 設定 + relay
- [ ] `docker compose up -d` 在 `monitoring/` 目錄能正常起 3 個（或 4 個含 grafana）container
- [ ] 三個 service repo 的 metrics 端點皆被 prometheus scrape 成功 — `http://localhost:9090/targets` 顯示 3 個 job 都是 `UP`
- [ ] 每個 repo 的 `infra/prometheus/alerts.yml` 都被 prometheus 載入 — `http://localhost:9090/rules` 顯示 7 條 rules（Uni-Seeker 3 + sports-prophet 2 + smart-money 2）皆為 `ok` 狀態
- [ ] 手動 `docker stop <service>` 或 kill process → 90 秒內 Telegram 收到 ServiceDown alert（含 service 名稱、severity、annotation）
- [ ] `Uni-Seeker/docs/superpowers/specs/2026-05-19-observability-verification.md` §6 從 "placeholder" 改寫為 "live"，列出 monitoring stack 的啟動 / 驗證 / troubleshooting 指令
- [ ] `monitoring/README.md` 完成 — 含啟動指令、healthcheck、新增 service 的 SOP

## 9. Related Files (existing artifacts to reuse)

Batch A/B（2026-05-19 完成，T10b 直接重用）：

- `/Users/stanley/stanley-project/Uni-Seeker/scripts/check_metrics_healthy.py`
- `/Users/stanley/stanley-project/sports-prophet/scripts/check_metrics_healthy.py`
- `/Users/stanley/stanley-project/smart_money/scripts/check_metrics_healthy.py`
- `/Users/stanley/stanley-project/Uni-Seeker/infra/prometheus/alerts.yml`
- `/Users/stanley/stanley-project/sports-prophet/infra/prometheus/alerts.yml`
- `/Users/stanley/stanley-project/smart_money/infra/prometheus/alerts.yml`

Batch C（如已完成；否則 T10b 第一步就是先完成 C 並把這兩個檔案落地到 sports-prophet）：

- `/Users/stanley/stanley-project/sports-prophet/infra/alertmanager/alertmanager.yml`
- `/Users/stanley/stanley-project/sports-prophet/scripts/alerts_tg_relay.py`

文件與決策來源：

- `/Users/stanley/stanley-project/Uni-Seeker/docs/superpowers/specs/2026-05-19-observability-verification.md`（跨 repo 驗證手冊；§6 待 T10b 更新）
- `/Users/stanley/stanley-project/daily-task/2026-05-19-DailyTask.md`（Q2/Q3/Q4 決議來源 + Batch C 切出 T10b 的紀錄）

新建將產生（T10b 落地時）：

- `/Users/stanley/stanley-project/monitoring/docker-compose.yml`
- `/Users/stanley/stanley-project/monitoring/prometheus/prometheus.yml`
- `/Users/stanley/stanley-project/monitoring/README.md`
- `/Users/stanley/stanley-project/monitoring/.env`（不 commit）

## 10. Estimated Effort

| Phase | 工作 | 估時 |
|---|---|---:|
| Phase 1 | monitoring/ skeleton + sports-prophet only + e2e TG verify | ~1h |
| Phase 2 | add smart_money job + verify | ~30min |
| Phase 3 | add Uni-Seeker job + verify + 可選 grafana | ~30min |
| 文件 | 更新 observability-verification.md §6 + monitoring/README.md | ~15min |
| **總計** | 單一 focused session 可完成 | **~2-2.5h** |

完成後 Plan 8 觀測棧整條鏈路（log → metric → alert → notification）才算真正 production-ready。
