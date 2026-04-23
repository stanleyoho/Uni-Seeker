# Technical Pattern Detection (技術型態偵測)

The `PatternIndicator` detects common technical analysis patterns and returns discrete signal values. It composes multiple built-in indicators (MA, KD, RSI, MACD) to identify actionable trading signals.

## Usage

```python
from app.modules.indicators.patterns import PatternIndicator

indicator = PatternIndicator()
result = indicator.calculate(closes, pattern_type="ma_alignment")
```

## Pattern Types

### 1. MA Alignment (多頭排列 / 空頭排列)

Detects whether moving averages (5, 10, 20, 60) are aligned in bullish or bearish order.

**Parameter:** `pattern_type="ma_alignment"`

| Signal | Meaning |
|--------|---------|
| `2`    | Strong bullish — MAs in ascending order AND price above MA5 (強勢多頭排列) |
| `1`    | Bullish — MAs in ascending order (多頭排列) |
| `0`    | Neutral — MAs not in any clear order |
| `-1`   | Bearish — MAs in descending order (空頭排列) |
| `-2`   | Strong bearish — MAs in descending order AND price below MA5 (強勢空頭排列) |

**TW Market Context:** MA alignment is one of the most commonly used signals among Taiwan retail investors. A 多頭排列 on the daily chart is often referenced in financial TV commentary as a bullish structural condition.

---

### 2. MA Crossover (黃金交叉 / 死亡交叉)

Detects when a short-period MA crosses above or below a long-period MA.

**Parameters:**
- `pattern_type="ma_crossover"`
- `short_period` (default: 5)
- `long_period` (default: 20)

| Signal | Meaning |
|--------|---------|
| `1`    | Golden cross — short MA crosses above long MA (黃金交叉) |
| `-1`   | Death cross — short MA crosses below long MA (死亡交叉) |
| `0`    | No crossover |

**TW Market Context:** The 5/20 MA crossover is the standard short-term signal. The 20/60 crossover is used for medium-term trend confirmation. Golden crosses on weekly charts are considered stronger signals.

---

### 3. KD Signal (KD 交叉信號)

Combines KD crossover detection with overbought/oversold zones for stronger signals.

**Parameters:**
- `pattern_type="kd_signal"`
- `highs` — list of high prices (required)
- `lows` — list of low prices (required)

| Signal | Meaning |
|--------|---------|
| `2`    | Oversold golden cross — K crosses above D below 20 (低檔黃金交叉，強力買進信號) |
| `1`    | Golden cross — K crosses above D (黃金交叉) |
| `0`    | Neutral |
| `-1`   | Death cross — K crosses below D (死亡交叉) |
| `-2`   | Overbought death cross — K crosses below D above 80 (高檔死亡交叉，強力賣出信號) |

**TW Market Context:** KD is the most popular oscillator among Taiwan investors. The 9-period KD with oversold (<20) golden crosses is a classic buy signal, especially when the stock has pulled back to a support level.

---

### 4. RSI Divergence (RSI 背離)

Detects divergence between price action and RSI momentum — a leading reversal signal.

**Parameters:**
- `pattern_type="rsi_divergence"`
- `period` (default: 14)
- `lookback` (default: 10) — window to compare against

| Signal | Meaning |
|--------|---------|
| `1`    | Bullish divergence — price makes new low, RSI does not (底背離，反轉向上信號) |
| `-1`   | Bearish divergence — price makes new high, RSI does not (頂背離，反轉向下信號) |
| `0`    | No divergence |

**TW Market Context:** RSI divergence is considered an advanced signal. Bullish divergence near support levels (e.g., quarterly MA or previous lows) is a high-confidence buy setup. Bearish divergence at resistance is used as a profit-taking trigger.

---

### 5. MACD Signal (MACD 柱狀圖信號)

Analyzes MACD histogram changes to detect momentum shifts.

**Parameter:** `pattern_type="macd_signal"`

| Signal | Meaning |
|--------|---------|
| `2`    | Histogram flips from negative to positive (柱狀圖翻正，強力買進) |
| `1`    | Histogram positive and growing (動能增加) |
| `0`    | Neutral |
| `-1`   | Histogram negative and falling (動能減弱) |
| `-2`   | Histogram flips from positive to negative (柱狀圖翻負，強力賣出) |

**TW Market Context:** MACD histogram flips are widely used as entry/exit timing signals. A histogram flip positive after a period of contraction (柱狀圖由縮腳轉翻紅) is considered a strong buy signal in Taiwan technical analysis practice.

## Output Format

All pattern types return an `IndicatorResult` with:
- `name`: `"PATTERN"`
- `values`: a dict with a single key matching the pattern type (e.g., `"ma_alignment"`, `"ma_crossover"`)
- The value is a list of the same length as the input `closes`, with `None` for indices where the pattern cannot be computed.
