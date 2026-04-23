# Bollinger Bands Specification

## Overview
- **Name**: BB (Bollinger Bands)
- **Category**: Volatility
- **Module**: `app/modules/indicators/bollinger.py`
- **Class**: `BollingerBandsIndicator`

## Definition

Bollinger Bands consist of a middle band (SMA) with an upper and lower band placed a specified number of standard deviations above and below. They expand and contract based on price volatility. Created by John Bollinger in the 1980s.

```
Middle Band = SMA(close, period)
Upper Band  = Middle Band + (num_std * StdDev)
Lower Band  = Middle Band - (num_std * StdDev)
```

Where `StdDev` is the population standard deviation of the closing prices in the window:

```
StdDev = sqrt( (1/N) * sum( (x_i - SMA)^2 ) )
```

Note: The implementation uses population standard deviation (divides by N, not N-1), consistent with the original Bollinger definition.

## Parameters
| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| period | int | 20 | 5-100 | SMA lookback period |
| num_std | float | 2.0 | 0.5-4.0 | Number of standard deviations for band width |

## Calculation Method

1. For each bar from index `period - 1` onward:
   a. Extract the trailing window of `period` closes.
   b. Compute the SMA of the window (middle band).
   c. Compute the population standard deviation of the window.
   d. Upper band = SMA + `num_std` * StdDev.
   e. Lower band = SMA - `num_std` * StdDev.
2. Values at indices 0 through `period - 2` are `None`.

## Output

| Key | Type | Description |
|-----|------|-------------|
| upper | list[float or None] | Upper band values |
| middle | list[float or None] | Middle band (SMA) values |
| lower | list[float or None] | Lower band values |

## Interpretation

- **Price touching or exceeding the upper band**: The stock may be relatively overextended. Not necessarily a sell signal on its own -- in strong trends, prices can "ride" the upper band.
- **Price touching or falling below the lower band**: The stock may be relatively cheap. In strong downtrends, prices can ride the lower band.
- **Band squeeze (narrow bands)**: Low volatility period. Squeezes often precede significant price moves, though the direction is not predicted.
- **Band expansion (wide bands)**: High volatility. Often occurs at the start of a new trend or during sharp moves.
- **Bollinger Bounce**: In ranging markets, prices tend to bounce between the upper and lower bands. This mean-reversion behavior is the basis for range-trading strategies.
- **%B indicator**: `%B = (Price - Lower Band) / (Upper Band - Lower Band)`. Values above 1 indicate price above the upper band; below 0, price below the lower band.

### TW Stock Context (台股備註)

Bollinger Bands are commonly used by TW traders to spot 盤整突破 (consolidation breakouts). A squeeze followed by price closing above the upper band with expanding volume is a classic breakout signal. For lower-volatility large-cap TW stocks (e.g., TSMC / 2330), `num_std = 2.0` works well. For volatile small-cap OTC stocks, `num_std = 2.5` may reduce false signals.

## Use Cases

- Identifying volatility compression ("squeeze") setups that precede breakouts.
- Mean-reversion trading in range-bound markets (buy at lower band, sell at upper band).
- Setting dynamic stop-loss levels using the lower band as trailing support.
- Gauging relative price position: is the current price at the high or low end of its recent range?

### Complementary Indicators

- **RSI**: An RSI extreme (overbought/oversold) combined with a Bollinger Band touch strengthens the signal.
- **KD**: Similar approach -- KD oversold near the lower band adds conviction for a bounce.
- **Volume**: Volume confirmation on a band breakout distinguishes genuine breakouts from false ones.

## Test Cases
| Input | Expected Output | Notes |
|-------|----------------|-------|
| Fewer than `period` closes | All three arrays are `None` | Insufficient data |
| Constant prices | Upper = middle = lower (StdDev = 0) | Zero-volatility edge case |
| Linearly increasing prices | Bands are parallel with constant width | Constant variance in the window |
| Highly volatile prices | Wide bands | Confirms band expansion behavior |
| period=20, num_std=2.0, 25 closes | Non-None values from index 19 to 24 | Standard output range |

## References

- Bollinger, John. _Bollinger on Bollinger Bands_, 2001.
- [Investopedia: Bollinger Bands](https://www.investopedia.com/terms/b/bollingerbands.asp)
