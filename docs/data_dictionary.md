# Uni-Seeker 財務資料字典 (Financial Data Dictionary)

本文件定義了 Uni-Seeker 平台中財務相關資料的欄位定義、類型、來源及計算公式。

## 1. 財務報表 (Financial Statements)
儲存來自資料源（如 FinMind）的原始與標準化財務報表數據。

| 欄位名稱 (Field Name) | 類型 (Type) | 說明 (Description) | 來源/公式 (Source/Formula) | 單位 (Unit) |
| :--- | :--- | :--- | :--- | :--- |
| `stock_id` | Integer | 股票在系統中的內部 ID | 關聯至 `stocks.id` | N/A |
| `period` | String | 財報週期 (例: "2024-Q1") | 原始資料 | N/A |
| `statement_type` | String | 報表類型 (income, balance, cashflow) | 分類標記 | N/A |
| `fiscal_year` | Integer | 財政年度 | 原始資料 | 年 |
| `fiscal_quarter` | Integer | 財政季度 (1-4) | 原始資料 | 季 |
| `data` | JSONB | 報表具體數據，包含各項會計科目 | FinMind API | 多樣 |
| `is_cumulative` | Boolean | 是否為累計數值 | 原始資料 | N/A |

---

## 2. 財務指標與比率 (Financial Metrics & Ratios)
經過計算後的財務比率，用於分析公司的獲利能力、營運效率及償債能力。

| 欄位名稱 (Field Name) | 類型 (Type) | 說明 (Description) | 來源/公式 (Source/Formula) | 單位 (Unit) |
| :--- | :--- | :--- | :--- | :--- |
| `gross_margin` | Float | 毛利率 | (營業收入 - 營業成本) / 營業收入 | % |
| `operating_margin` | Float | 營業利益率 | 營業利益 / 營業收入 | % |
| `net_margin` | Float | 稅後淨利率 | 稅後淨利 / 營業收入 | % |
| `roe` | Float | 股東權益報酬率 | 稅後淨利 / 股東權益 | % |
| `roa` | Float | 資產報酬率 | 稅後淨利 / 總資產 | % |
| `eps` | Float | 每股盈餘 | 稅後淨利 / 加權平均流通在外股數 | 元 |
| `current_ratio` | Float | 流動比率 | 流動資產 / 流動負債 | % |
| `quick_ratio` | Float | 速動比率 | (流動資產 - 存貨 - 預付款項) / 流動負債 | % |
| `debt_to_equity` | Float | 負債權益比 | 總負債 / 股東權益 | % |
| `revenue_growth_yoy` | Float | 營收年增率 | (本期營收 - 去年同期營收) / 去年同期營收 | % |
| `fcf` | Float | 自由現金流量 | 營業現金流量 - 資本支出 | 金額 |

---

## 3. 每月營收 (Monthly Revenue)
追蹤公司每個月公佈的營收狀況與增長趨勢。

| 欄位名稱 (Field Name) | 類型 (Type) | 說明 (Description) | 來源/公式 (Source/Formula) | 單位 (Unit) |
| :--- | :--- | :--- | :--- | :--- |
| `period` | String | 營收月份 (例: "2024-03") | 原始資料 | N/A |
| `revenue` | Numeric | 當月營業收入 | 原始資料 | 金額 (TWD) |
| `mom_growth` | Numeric | 營收月增率 (MoM) | (本月營收 - 上月營收) / 上月營收 | % |
| `yoy_growth` | Numeric | 營收年增率 (YoY) | (本月營收 - 去年同月營收) / 去年同月營收 | % |
| `currency` | String | 幣別 | 原始資料 | N/A |

---

## 4. 信用交易 (Margin Trading)
反映市場籌碼面狀況，包括融資融券的使用情形。

| 欄位名稱 (Field Name) | 類型 (Type) | 說明 (Description) | 來源/公式 (Source/Formula) | 單位 (Unit) |
| :--- | :--- | :--- | :--- | :--- |
| `date` | Date | 交易日期 | 原始資料 | N/A |
| `margin_buy` | BigInteger | 融資買進張數 | 原始資料 | 張 |
| `margin_sell` | BigInteger | 融資賣出張數 | 原始資料 | 張 |
| `margin_balance` | BigInteger | 融資餘額 | 原始資料 | 張 |
| `margin_limit` | BigInteger | 融資限額 | 原始資料 | 張 |
| `short_buy` | BigInteger | 融券買進張數 | 原始資料 | 張 |
| `short_sell` | BigInteger | 融券賣出張數 | 原始資料 | 張 |
| `short_balance` | BigInteger | 融券餘額 | 原始資料 | 張 |
| `short_usage_pct` | Float | 融券使用率 | 融券餘額 / 融券限額 | % |
| `margin_short_ratio` | Float | 券資比 | 融券餘額 / 融資餘額 | % |

---

## 5. 估值與價格預測 (Valuation & Price Estimates)
包含基於不同模型計算出的股價估值建議。

| 欄位名稱 (Field Name) | 類型 (Type) | 說明 (Description) | 來源/公式 (Source/Formula) | 單位 (Unit) |
| :--- | :--- | :--- | :--- | :--- |
| `pe_ratio` | Numeric | 本益比 (P/E Ratio) | 市價 / 每股盈餘 | 倍 |
| `pb_ratio` | Numeric | 股價淨值比 (P/B Ratio) | 市價 / 每股淨值 | 倍 |
| `dividend_yield` | Numeric | 現金殖利率 | 股利 / 市價 | % |
| `model_type` | String | 估值模型類型 | dcf, ddm, pe_band, pb_band, composite | N/A |
| `cheap_price` | Numeric | 便宜價 (底標) | 基於模型計算 | 元 |
| `fair_price` | Numeric | 合理價 (中標) | 基於模型計算 | 元 |
| `expensive_price` | Numeric | 昂貴價 (高標) | 基於模型計算 | 元 |
| `confidence` | Numeric | 置信度 / 信心指數 | 模型評估指標 (0.0 - 1.0) | N/A |
| `details` | JSONB | 模型具體參數 (如折現率、成長率等) | 模型內部計算邏輯 | N/A |
