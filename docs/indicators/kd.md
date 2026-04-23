# KD (Stochastic Oscillator) Specification

## Overview
- **Name**: KD (Stochastic Oscillator)
- **Category**: Momentum
- **Module**: `app/modules/indicators/kd.py`
- **Class**: `KDIndicator`

## Definition

The KD stochastic oscillator compares a stock's closing price to its price range over a given lookback period. It generates overbought/oversold signals and is widely used in Asian markets, particularly in Taiwan (commonly called KD 指標).

```
Raw %K = (Close - Lowest Low) / (Highest High - Lowest Low) * 100
%K     = SMA(Raw %K, k_smooth)
%D     = SMA(%K, d_smooth)
```

Developed by George Lane in the 1950s.

## Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| k_period | int | 9 | 5-21 | Lookback window for highest high / lowest low |
| k_smooth | int | 3 | 1-10 | Smoothing period for %K (SMA of Raw %K) |
| d_smooth | int | 3 | 1-10 | Smoothing period for %D (SMA of %K) |
| highs | list[float] | required | -- | High prices for each bar |
| lows | list[float] | required | -- | Low prices for each bar |

## Calculation Method

1. For each bar from index `k_period - 1` onward:
   - Find the highest high and lowest low within the trailing `k_period` window.
   - If highest high equals lowest low (flat range), set Raw %K = 50.
   - Otherwise: `Raw %K = (close - lowest_low) / (highest_high - lowest_low) * 100`.
2. **%K**: Compute a simple moving average of the last `k_smooth` Raw %K values.
3. **%D**: Compute a simple moving average of the last `d_smooth` %K values.
4. Values are `None` until enough data is available.

## Output

| Key | Type | Description |
|-----|------|-------------|
| K | list[float or None] | Smoothed %K values (0-100) |
| D | list[float or None] | Smoothed %D values (0-100) |

## Interpretation

- **K > 80**: Overbought zone -- the stock is trading near the top of its recent range.
- **K < 20**: Oversold zone -- the stock is trading near the bottom of its recent range.
- **Golden cross (K crosses above D)**: Bullish signal, especially when occurring below 20.
- **Death cross (K crosses below D)**: Bearish signal, especially when occurring above 80.
- **Divergence**: Price makes a new high but K does not -- bearish divergence warns of weakening momentum.

### TW Stock Context (台股備註)

KD is arguably the most popular technical indicator among Taiwan retail investors (散戶). The default (9, 3, 3) setting is standard on most TW brokerage platforms. Many TW traders use KD golden/death cross signals in the 20/80 zones as primary entry/exit triggers (KD 黃金交叉 / 死亡交叉). Be aware that in strong trending markets, KD can remain overbought or oversold for extended periods -- this is called "鈍化" (blunting).

## Use Cases

- Short-to-medium-term swing trading signals.
- Identifying reversal zones in range-bound or mean-reverting markets.
- Filtering entries: combine with trend indicators to avoid counter-trend KD signals.

### Complementary Indicators

- **Moving Average**: Use a long-term MA to determine the trend direction; only take KD buy signals when price is above the MA.
- **RSI**: Cross-validates overbought/oversold readings.
- **Volume**: Confirm KD crossover signals with volume expansion.

## Test Cases
| Input | Expected Output | Notes |
|-------|----------------|-------|
| Fewer than `k_period` bars | All K and D are `None` | Insufficient data |
| `len(highs) != len(closes)` | All K and D are `None` | Mismatched input lengths |
| Flat prices (high == low == close) | Raw %K = 50 for all valid bars | Division-by-zero guard |
| Monotonically rising closes within range | K near 100 | Close consistently near period high |
| Sharp drop after uptrend | K drops rapidly from high to low zone | Validates responsiveness |

## References

- Lane, George. "Lane's Stochastics," _Technical Analysis of Stocks & Commodities_, 1984.
- [Investopedia: Stochastic Oscillator](https://www.investopedia.com/terms/s/stochasticoscillator.asp)
