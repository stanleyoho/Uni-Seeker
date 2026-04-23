# PE Valuation Model Specification

## Overview
- **Name**: PE (Price-to-Earnings) Valuation
- **Type**: Valuation
- **Module**: `app/modules/price_estimator/pe_model.py`
- **Function**: `estimate_by_pe`

## Theory

The Price-to-Earnings ratio is the most widely used valuation metric. It expresses how much investors are willing to pay per dollar of earnings. By applying a stock's historical PE range to its current earnings, we can estimate whether the stock is cheap, fairly valued, or expensive relative to its own history.

This is a **relative valuation** approach -- it does not calculate intrinsic value from cash flows but instead uses the market's historical pricing behavior for the specific stock.

## Formula

```
Estimated Price = EPS * PE Ratio
```

The model generates three price levels using percentiles of the historical PE distribution:

```
Cheap Price     = Current EPS * 25th percentile PE
Fair Price      = Current EPS * 50th percentile PE (median)
Expensive Price = Current EPS * 75th percentile PE
```

## Inputs
| Input | Source | Type | Required | Description |
|-------|--------|------|----------|-------------|
| current_eps | Financial statements | float | Yes | Current trailing twelve-month EPS (must be > 0) |
| historical_pe_ratios | TWSE / yfinance | list[float] | Yes | Historical PE ratios (daily/weekly observations) |
| current_price | Market data | float or None | No | Current market price (for reference, not used in calculation) |

## Outputs
| Output | Type | Range | Description |
|--------|------|-------|-------------|
| cheap_price | float | >= 0 | Price at the 25th percentile PE |
| fair_price | float | >= 0 | Price at the median (50th percentile) PE |
| expensive_price | float | >= 0 | Price at the 75th percentile PE |
| confidence | float | 0.0-1.0 | Based on data quantity |
| details.eps | float | -- | The EPS used |
| details.low_pe | float | -- | 25th percentile PE |
| details.mid_pe | float | -- | 50th percentile (median) PE |
| details.high_pe | float | -- | 75th percentile PE |

## Assumptions & Limitations

- **Positive EPS required**: The model returns zero values when EPS is zero or negative. PE-based valuation is meaningless for loss-making companies.
- **Mean-reversion assumption**: The model assumes the PE ratio will revert to its historical range. This breaks down when a company undergoes a fundamental transformation (sector pivot, major acquisition, regulatory change).
- **Earnings quality**: EPS can be distorted by one-time items, accounting choices, or stock buybacks. Use adjusted or normalized EPS when available.
- **Cyclical stocks**: Companies in cyclical industries (e.g., steel, shipping) can have low PE at earnings peaks and high PE at earnings troughs, inverting the usual interpretation.
- **Growth-stage companies**: High-growth companies may legitimately trade above historical PE ranges as the market prices in future earnings growth.

### TW Stock Context (台股備註)

TWSE provides daily PE data via the BWIBBU endpoint. For TW stocks, the PE ratio is based on trailing four-quarter EPS (近四季 EPS). Be aware that TWSE-reported PE may differ from yfinance PE due to different EPS calculation methods and reporting lag.

## Confidence Score

```
confidence = min(number_of_historical_observations / 20, 1.0)
```

- Fewer than 20 data points: confidence is proportionally reduced.
- 20 or more data points: confidence = 1.0 (capped).
- Zero or invalid EPS: confidence = 0.0, all prices = 0.

The 20-observation threshold is a heuristic: roughly one month of daily PE data.

## Validation

- **Sanity check**: The cheap price should be below the fair price, which should be below the expensive price. This is guaranteed by the percentile construction.
- **Historical comparison**: Compare the model's "fair" price against the stock's actual median trading price over the same period. They should be close if EPS was stable.
- **Cross-model check**: Compare PE-based fair value against DDM and DCF estimates. Large discrepancies warrant investigation.

## References

- Damodaran, Aswath. _Investment Valuation_, 3rd Edition, 2012.
- [Investopedia: Price-to-Earnings Ratio](https://www.investopedia.com/terms/p/price-earningsratio.asp)
- [TWSE BWIBBU API](https://openapi.twse.com.tw/)
