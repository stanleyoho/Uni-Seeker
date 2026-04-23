# RSI (Relative Strength Index) Specification

## Overview
- **Name**: RSI
- **Category**: Momentum
- **Module**: `app/modules/indicators/rsi.py`
- **Class**: `RSIIndicator`

## Definition

The Relative Strength Index measures the speed and magnitude of recent price changes to evaluate whether a stock is overbought or oversold. Developed by J. Welles Wilder Jr. in 1978.

```
RS  = Average Gain over N periods / Average Loss over N periods
RSI = 100 - (100 / (1 + RS))
```

The implementation uses Wilder's smoothing method (exponential moving average) for the running averages after the initial SMA seed.

## Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| period | int | 14 | 2-100 | Number of periods for the lookback window |

## Calculation Method

1. Compute price changes: `change[i] = close[i] - close[i-1]` for each bar.
2. Separate gains (positive changes) and losses (absolute value of negative changes).
3. **Initial values** (index = `period`): Calculate the simple average of the first `period` gains and losses.
4. **Subsequent values** (index > `period`): Apply Wilder's smoothing:
   ```
   avg_gain = (prev_avg_gain * (period - 1) + current_gain) / period
   avg_loss = (prev_avg_loss * (period - 1) + current_loss) / period
   ```
5. Compute RS and RSI. If `avg_loss == 0`, RSI = 100. If `avg_gain == 0`, RSI = 0.
6. Values at indices 0 through `period - 1` are `None` (insufficient data).

## Output

| Key | Type | Description |
|-----|------|-------------|
| RSI | list[float or None] | RSI value for each bar, `None` where insufficient data |

## Interpretation

- **RSI > 70**: The stock may be overbought -- price has risen aggressively and could be due for a pullback or consolidation.
- **RSI < 30**: The stock may be oversold -- price has fallen sharply and could be due for a bounce.
- **RSI crossing 50**: A cross above 50 suggests bullish momentum is strengthening; below 50 suggests bearish momentum.
- **Divergence**: If price makes a new high but RSI does not, this bearish divergence can signal weakening momentum (and vice versa for bullish divergence).

### TW Stock Context (台股備註)

In the Taiwan market, many retail-heavy stocks (e.g., small-cap OTC / 櫃買股) tend to show more extreme RSI readings. Some traders use 80/20 thresholds instead of 70/30 for highly volatile names.

## Use Cases

- Identifying potential reversal points in range-bound markets.
- Confirming trend strength alongside a trend-following indicator like MACD or Moving Average.
- Setting entry/exit alerts when RSI crosses overbought/oversold thresholds.

### Complementary Indicators

- **MACD**: Confirm momentum direction alongside RSI overbought/oversold signals.
- **Bollinger Bands**: An RSI extreme near a Bollinger Band touch strengthens the reversal signal.
- **Volume (OBV)**: Validate whether the price move is supported by volume.

## Test Cases
| Input | Expected Output | Notes |
|-------|----------------|-------|
| Fewer than `period + 1` closes | All `None` values | Insufficient data guard |
| Monotonically increasing prices | RSI = 100 | All gains, zero losses |
| Monotonically decreasing prices | RSI = 0 | All losses, zero gains |
| Flat prices (no change) | RSI at index `period` depends on 0/0 guard | Edge case: avg_gain and avg_loss both 0 |
| 15 closes with mixed movement, period=14 | Single non-None RSI at index 14 | Minimum viable output |

## References

- Wilder, J. Welles Jr. _New Concepts in Technical Trading Systems_, 1978.
- [Investopedia: Relative Strength Index](https://www.investopedia.com/terms/r/rsi.asp)
