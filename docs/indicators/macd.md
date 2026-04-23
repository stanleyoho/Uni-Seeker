# MACD (Moving Average Convergence Divergence) Specification

## Overview
- **Name**: MACD
- **Category**: Momentum / Trend
- **Module**: `app/modules/indicators/macd.py`
- **Class**: `MACDIndicator`

## Definition

MACD measures the relationship between two exponential moving averages (EMAs) of closing prices. It reveals changes in a trend's strength, direction, momentum, and duration. Developed by Gerald Appel in the late 1970s.

```
MACD Line  = EMA(fast) - EMA(slow)
Signal Line = EMA(MACD Line, signal_period)
Histogram   = MACD Line - Signal Line
```

## Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| fast | int | 12 | 2-50 | Period for the fast EMA |
| slow | int | 26 | 10-200 | Period for the slow EMA |
| signal | int | 9 | 2-50 | Period for the signal line EMA |

## Calculation Method

1. **EMA helper** (`_ema`): Seeds with an SMA of the first `period` values, then applies the standard EMA formula:
   ```
   multiplier = 2 / (period + 1)
   EMA[i] = (close[i] - EMA[i-1]) * multiplier + EMA[i-1]
   ```
2. Compute `fast_ema = EMA(closes, fast)` and `slow_ema = EMA(closes, slow)`.
3. **MACD Line**: For each bar where both fast and slow EMA are available, `MACD[i] = fast_ema[i] - slow_ema[i]`.
4. **Signal Line**: Apply `_ema` to the non-None MACD values using `signal_period`.
5. **Histogram**: `histogram[i] = MACD[i] - signal[i]` where both are available.
6. Values are `None` until enough data is present (first valid MACD appears at index `slow - 1`).

## Output

| Key | Type | Description |
|-----|------|-------------|
| MACD | list[float or None] | MACD line values |
| signal | list[float or None] | Signal line values |
| histogram | list[float or None] | MACD minus signal |

## Interpretation

- **MACD crosses above signal line**: Bullish signal -- consider buying or closing short positions.
- **MACD crosses below signal line**: Bearish signal -- consider selling or closing long positions.
- **Histogram growing**: Momentum is increasing in the direction of the MACD line.
- **Histogram shrinking**: Momentum is fading -- potential trend change ahead.
- **MACD above zero**: The fast EMA is above the slow EMA, indicating an uptrend.
- **MACD below zero**: The fast EMA is below the slow EMA, indicating a downtrend.
- **Divergence**: Price making new highs while MACD makes lower highs (bearish divergence) signals potential reversal.

### TW Stock Context (台股備註)

For shorter-term TW stock day trading, some traders use faster settings like (5, 13, 6) or (8, 17, 9) to capture intraday momentum during the compressed 09:00-13:30 trading session.

## Use Cases

- Identifying trend direction and momentum shifts.
- Generating crossover-based buy/sell signals for systematic strategies.
- Spotting divergences between price and momentum as early reversal warnings.

### Complementary Indicators

- **RSI**: Use RSI to filter MACD crossover signals -- only act on bullish crossovers when RSI is not already overbought.
- **Moving Average**: A 200-period MA can confirm the macro trend; only take MACD buy signals when price is above the long-term MA.
- **Volume**: Volume expansion on a MACD crossover adds conviction.

## Test Cases
| Input | Expected Output | Notes |
|-------|----------------|-------|
| Fewer than `slow` closes | All three arrays are `None` | Insufficient data guard |
| Exactly `slow` closes | MACD has one value at index `slow - 1`, signal/histogram still `None` | Signal needs `signal_period` MACD points |
| 50 closes, default params | Non-None MACD from index 25, signal from ~index 33 | Verify histogram = MACD - signal |
| Constant prices | MACD = 0, signal = 0, histogram = 0 | No divergence between fast and slow EMA |

## References

- Appel, Gerald. _Technical Analysis: Power Tools for Active Investors_, 2005.
- [Investopedia: MACD](https://www.investopedia.com/terms/m/macd.asp)
