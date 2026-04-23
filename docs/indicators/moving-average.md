# Moving Average Specification

## Overview
- **Name**: MA (Moving Average)
- **Category**: Trend
- **Module**: `app/modules/indicators/moving_average.py`
- **Class**: `MovingAverageIndicator`

## Definition

A moving average smooths price data by calculating the average closing price over a specified number of periods. This indicator supports two types:

**Simple Moving Average (SMA)**:
```
SMA = (P_1 + P_2 + ... + P_n) / n
```

**Exponential Moving Average (EMA)**:
```
Multiplier = 2 / (period + 1)
EMA[i] = (Close[i] - EMA[i-1]) * Multiplier + EMA[i-1]
```
The EMA is seeded with the SMA of the first `period` closes.

## Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| period | int | 20 | 2-500 | Number of bars in the averaging window |
| ma_type | str | "SMA" | "SMA" or "EMA" | Type of moving average |

## Calculation Method

### SMA
1. Compute the sum of the first `period` closes.
2. At index `period - 1`, set `MA = sum / period`.
3. For each subsequent bar, use a sliding window: add the new close, subtract the oldest close, divide by `period`.

### EMA
1. Compute the SMA of the first `period` closes as the seed value at index `period - 1`.
2. Calculate the multiplier: `2 / (period + 1)`.
3. For each subsequent bar: `EMA[i] = (close[i] - EMA[i-1]) * multiplier + EMA[i-1]`.
4. Values at indices 0 through `period - 2` are `None`.

## Output

| Key | Type | Description |
|-----|------|-------------|
| MA | list[float or None] | Moving average value for each bar |

## Interpretation

- **Price above MA**: Bullish -- the stock is trading above its average, suggesting upward momentum.
- **Price below MA**: Bearish -- the stock is trading below its average, suggesting downward momentum.
- **MA slope**: A rising MA confirms an uptrend; a flattening or declining MA signals a weakening or reversing trend.
- **MA crossover**: When a short-period MA crosses above a long-period MA ("golden cross"), it is a bullish signal. The reverse ("death cross") is bearish.

### Common Period Selections

| Period | Typical Use |
|--------|-------------|
| 5 | Weekly average -- very short-term trading (週線) |
| 10 | Bi-weekly average |
| 20 | Monthly average -- standard short-term trend (月線) |
| 60 | Quarterly average -- medium-term trend (季線) |
| 120 | Half-year average (半年線) |
| 240 | Annual average -- long-term trend (年線) |

### TW Stock Context (台股備註)

Taiwan traders commonly reference the 5 / 10 / 20 / 60 / 120 / 240 day moving averages. The "年線" (240-day MA) is considered a major support/resistance level and is widely watched by institutional and retail investors. When a stock breaks below the 年線, it is often interpreted as a significant bearish event.

## Use Cases

- Determining the primary trend direction.
- Identifying dynamic support and resistance levels.
- Building crossover-based trading strategies (e.g., 5-day MA crossing above 20-day MA).
- Serving as a building block for other indicators (Bollinger Bands use SMA as the middle band; MACD uses EMA).

### Complementary Indicators

- **Bollinger Bands**: Add standard deviation bands around the MA to gauge volatility.
- **MACD**: A derived indicator using two EMAs -- use alongside raw MA for multi-timeframe analysis.
- **RSI / KD**: Combine with MA to filter momentum signals by trend direction.

## Test Cases
| Input | Expected Output | Notes |
|-------|----------------|-------|
| Fewer than `period` closes | All `None` | Insufficient data |
| 20 identical closes, SMA, period=20 | MA = that constant value at index 19 | Trivial average |
| Linearly increasing closes, SMA | MA lags behind the current price | Confirms lag behavior |
| Same data, SMA vs EMA | EMA responds faster to recent changes | EMA assigns more weight to recent prices |

## References

- [Investopedia: Moving Average](https://www.investopedia.com/terms/m/movingaverage.asp)
- [Investopedia: Exponential Moving Average](https://www.investopedia.com/terms/e/ema.asp)
