# Volume Indicators Specification

## Overview
- **Name**: VOL (Volume Indicators)
- **Category**: Volume
- **Module**: `app/modules/indicators/volume.py`
- **Class**: `VolumeIndicator`

This module provides two volume-based indicators selected via the `indicator_type` parameter:
1. **OBV** -- On-Balance Volume
2. **VMA** -- Volume Moving Average

---

## On-Balance Volume (OBV)

### Definition

OBV is a cumulative volume indicator that adds volume on up days and subtracts volume on down days. It was introduced by Joseph Granville in 1963 as a way to detect institutional money flow.

```
If Close[i] > Close[i-1]:  OBV[i] = OBV[i-1] + Volume[i]
If Close[i] < Close[i-1]:  OBV[i] = OBV[i-1] - Volume[i]
If Close[i] == Close[i-1]: OBV[i] = OBV[i-1]
```

OBV[0] is initialized to Volume[0].

### Parameters (OBV)
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| indicator_type | str | "OBV" | -- | Must be "OBV" |
| volumes | list[int] | required | -- | Volume for each bar (must match closes length) |

### Output (OBV)

| Key | Type | Description |
|-----|------|-------------|
| OBV | list[int or None] | Cumulative on-balance volume |

### Interpretation (OBV)

- **Rising OBV with rising price**: Confirms the uptrend -- volume is flowing into the stock.
- **Falling OBV with falling price**: Confirms the downtrend.
- **Rising OBV with flat or falling price**: Bullish divergence -- accumulation may be occurring before a price move up.
- **Falling OBV with flat or rising price**: Bearish divergence -- distribution may be occurring before a price decline.
- **OBV breakout**: When OBV breaks to a new high before price does, it can foreshadow a price breakout.

---

## Volume Moving Average (VMA)

### Definition

The Volume Moving Average is a simple moving average of volume values, used to identify whether current volume is above or below its recent average.

```
VMA[i] = (Volume[i - period + 1] + ... + Volume[i]) / period
```

### Parameters (VMA)
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| indicator_type | str | -- | Must be anything other than "OBV" | Selects VMA calculation |
| volumes | list[int] | required | -- | Volume for each bar |
| period | int | 5 | 2-60 | SMA lookback period for volume |

### Output (VMA)

| Key | Type | Description |
|-----|------|-------------|
| VMA | list[float or None] | Volume moving average |

### Interpretation (VMA)

- **Current volume > VMA**: Above-average activity -- the current move has conviction.
- **Current volume < VMA**: Below-average activity -- the current move may lack conviction and could reverse.
- **Volume spike (2x+ VMA)**: Significant event -- could mark a climactic top/bottom, earnings reaction, or institutional block trade.

---

## General Volume Interpretation

### TW Stock Context (台股備註)

- Taiwan market volume is reported in "lots" (張), where 1 lot = 1,000 shares. When comparing volume across stocks, normalize by shares outstanding or free float.
- Institutional investors (三大法人: 外資, 投信, 自營商) publish daily buy/sell data on TWSE. Combining OBV with 法人買賣超 data gives a more complete picture of money flow.
- Volume tends to spike on futures/options settlement days (每月第三個星期三, "結算日").

## Use Cases

- **OBV**: Detect accumulation or distribution phases before price movements. Useful for confirming breakouts.
- **VMA**: Quick check of whether current trading activity is normal or elevated. Useful as a filter: only take breakout signals when volume exceeds the VMA.

### Complementary Indicators

- **Moving Average**: Confirm price trend direction alongside volume trend.
- **Bollinger Bands**: A band breakout on high volume (above VMA) is more reliable than one on low volume.
- **RSI / KD**: An oversold reading with rising OBV suggests accumulation; an overbought reading with falling OBV suggests distribution.

## Test Cases
| Input | Expected Output | Notes |
|-------|----------------|-------|
| Empty closes and volumes | All `None` | Empty data guard |
| `len(volumes) != len(closes)` | All `None` for OBV | Mismatched length guard |
| Monotonically rising prices | OBV = cumulative sum of all volumes | Every day adds volume |
| Flat prices | OBV stays constant after index 0 | No volume added or subtracted |
| VMA with fewer than `period` volumes | All `None` | Insufficient data |
| VMA with constant volume | VMA equals that constant value from index `period - 1` onward | Trivial average |

## References

- Granville, Joseph. _New Key to Stock Market Profits_, 1963.
- [Investopedia: On-Balance Volume](https://www.investopedia.com/terms/o/onbalancevolume.asp)
- [Investopedia: Volume Moving Average](https://www.investopedia.com/terms/a/averagedailytradingvolume.asp)
