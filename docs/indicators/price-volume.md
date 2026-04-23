# Price-Volume Derived Indicators Specification

## Overview
- **Name**: PV (Price-Volume Indicators)
- **Category**: Price-Volume Derived
- **Module**: `app/modules/indicators/price_volume.py`
- **Class**: `PriceVolumeIndicator`

This module provides five price-volume derived indicators selected via the `indicator_type` parameter:
1. **Volume Ratio** -- Today's volume relative to N-day average
2. **Volume Surge** -- Detect abnormal volume spikes
3. **Amplitude** -- Daily price range as percentage of previous close
4. **New High/Low** -- N-day new high or low detection
5. **Multi-Period Price Change** -- Price change % across multiple timeframes

---

## Volume Ratio

### Definition

Volume Ratio measures the current day's volume relative to its recent average, indicating whether trading activity is above or below normal.

```
Volume_Ratio[i] = Volume[i] / SMA(Volume, period)[i-1..i-period]
```

Where `SMA(Volume, period)` is the simple moving average of volume over the preceding `period` days (not including the current day).

### Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| indicator_type | str | "volume_ratio" | -- | Must be "volume_ratio" |
| volumes | list[int] | required | -- | Volume for each bar |
| period | int | 5 | 2-60 | Lookback period for average volume |

### Output

| Key | Type | Description |
|-----|------|-------------|
| volume_ratio | list[float or None] | Ratio of current volume to N-day average |

### Interpretation

- **Ratio > 1.5**: Significantly above-average volume; strong conviction in the current move.
- **Ratio ~ 1.0**: Normal trading activity.
- **Ratio < 0.5**: Very low volume; the current move may lack conviction.
- Useful as a filter for confirming breakouts or breakdowns.

---

## Volume Surge

### Definition

Volume Surge detects days where volume significantly exceeds its recent average, expressed as a multiple of the average.

```
Surge[i] = Volume[i] / SMA(Volume, period)[i-1..i-period]
```

Functionally identical to Volume Ratio but typically used with a longer lookback period and a threshold to flag surges.

### Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| indicator_type | str | -- | -- | Must be "volume_surge" |
| volumes | list[int] | required | -- | Volume for each bar |
| period | int | 20 | 5-120 | Lookback period for average volume |
| threshold | float | 2.0 | 1.5-10.0 | Multiple above which a surge is flagged |

### Output

| Key | Type | Description |
|-----|------|-------------|
| volume_surge | list[float or None] | Multiple of current volume vs. N-day average |

### Interpretation

- **Surge >= 2.0**: Volume spike; may indicate institutional activity, news reaction, or climactic reversal.
- **Surge >= 3.0**: Extreme volume; watch for potential exhaustion tops or capitulation bottoms.
- Combine with price direction: a surge on an up day is bullish; a surge on a down day may signal panic selling.

---

## Amplitude

### Definition

Daily amplitude measures the intraday price range as a percentage of the previous close. It captures volatility on a per-bar basis.

```
Amplitude[i] = (High[i] - Low[i]) / Close[i-1] * 100
```

### Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| indicator_type | str | -- | -- | Must be "amplitude" |
| highs | list[float] | required | -- | High price for each bar (must match closes length) |
| lows | list[float] | required | -- | Low price for each bar (must match closes length) |

### Output

| Key | Type | Description |
|-----|------|-------------|
| amplitude | list[float or None] | Daily amplitude as percentage |

### Interpretation

- **Amplitude > 5%**: High volatility day; common around earnings or macro events.
- **Amplitude < 1%**: Very low volatility; potential for an imminent breakout.
- Rising average amplitude often accompanies trend transitions.
- Compare to historical average amplitude to gauge whether current volatility is normal.

---

## New High/Low

### Definition

Detects whether the current close is a new N-day high or low, useful for momentum and breakout strategies.

```
If Close[i] > max(Close[i-period..i-1]): signal = 1  (new high)
If Close[i] < min(Close[i-period..i-1]): signal = -1 (new low)
Otherwise:                                signal = 0
```

### Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| indicator_type | str | -- | -- | Must be "new_high_low" |
| period | int | 20 | 5-240 | Lookback period for high/low detection |

### Output

| Key | Type | Description |
|-----|------|-------------|
| new_high_low | list[int or None] | 1 = new high, -1 = new low, 0 = neither |

### Interpretation

- **Signal = 1**: Price is breaking out above recent resistance; bullish momentum.
- **Signal = -1**: Price is breaking down below recent support; bearish momentum.
- **Signal = 0**: Price is consolidating within the recent range.
- Common period choices: 20 (1 month), 60 (1 quarter), 240 (1 year).
- Combine with volume indicators: a new high on above-average volume is more significant.

---

## Multi-Period Price Change

### Definition

Calculates the percentage price change over multiple standard periods (5, 20, 60, 120, 240 days), providing a multi-timeframe momentum view.

```
Change_Nd[i] = (Close[i] - Close[i-N]) / Close[i-N] * 100
```

Where N is one of: 5, 20, 60, 120, 240.

### Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| indicator_type | str | -- | -- | Must be "price_change" |

No additional parameters; all five periods are computed automatically.

### Output

| Key | Type | Description |
|-----|------|-------------|
| change_5d | list[float or None] | 5-day price change % |
| change_20d | list[float or None] | 20-day price change % |
| change_60d | list[float or None] | 60-day (quarterly) price change % |
| change_120d | list[float or None] | 120-day (half-year) price change % |
| change_240d | list[float or None] | 240-day (annual) price change % |

### Interpretation

- Provides a quick snapshot of momentum across timeframes.
- **Positive across all periods**: Strong sustained uptrend.
- **Short-term negative, long-term positive**: Possible pullback in an uptrend (buy-the-dip candidate).
- **Short-term positive, long-term negative**: Bear market rally; proceed with caution.
- Useful for screening and ranking stocks by momentum.

---

## TW Stock Context

- Volume is reported in lots on TWSE/TPEX. Volume ratio and surge calculations work the same regardless of unit, as they are relative measures.
- Amplitude tends to be higher for smaller-cap OTC stocks and lower for large-cap TWSE50 constituents.
- The 240-day price change approximates annual return, useful for comparing against the TAIEX benchmark.
- Combine new high/low signals with institutional net buy/sell data for higher-confidence signals.

## Use Cases

- **Volume Ratio / Surge**: Confirm breakouts; filter out low-conviction moves.
- **Amplitude**: Gauge volatility regime; set stop-loss distances; identify quiet-before-the-storm setups.
- **New High/Low**: Momentum screening; Donchian-channel-style breakout strategies.
- **Multi-Period Change**: Momentum factor ranking for portfolio construction; sector rotation analysis.

### Complementary Indicators

- **Moving Average**: Confirm trend direction alongside momentum signals.
- **RSI / KD**: Combine overbought/oversold readings with new high/low for divergence detection.
- **Bollinger Bands**: Amplitude expanding beyond bands suggests strong directional move.
- **Volume (OBV/VMA)**: Cross-validate volume ratio/surge with OBV trend.

## Test Cases
| Input | Expected Output | Notes |
|-------|----------------|-------|
| Volume ratio with 5 constant + 5 doubled volumes | ratio[5] = 2.0 | Basic ratio calculation |
| Volume surge with 20 constant + spike | surge[20] = 5.0 | Spike detection |
| Amplitude with known highs/lows/closes | amp[1] = 11.0 | (108-97)/100*100 |
| Steadily rising prices, period=20 | signal[20] = 1 | New high detection |
| Steadily falling prices, period=20 | signal[20] = -1 | New low detection |
| 250 linearly rising closes | change_5d[5] = 5.0 | Multi-period change |
| Insufficient data (n < period) | All None | Edge case guard |

## References

- [Investopedia: Volume Ratio](https://www.investopedia.com/terms/v/volume-rate-of-change.asp)
- [Investopedia: Average True Range (related to Amplitude)](https://www.investopedia.com/terms/a/atr.asp)
- [Investopedia: 52-Week High/Low](https://www.investopedia.com/terms/1/52weekhighlow.asp)
- [Investopedia: Rate of Change](https://www.investopedia.com/terms/r/rateofchange.asp)
