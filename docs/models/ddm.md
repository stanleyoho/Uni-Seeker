# DDM (Dividend Discount Model) Specification

## Overview
- **Name**: DDM (Gordon Growth Model)
- **Type**: Valuation
- **Module**: `app/modules/price_estimator/ddm.py`
- **Function**: `estimate_by_ddm`

## Theory

The Dividend Discount Model values a stock as the present value of all future dividend payments. The Gordon Growth Model is a simplified form that assumes dividends grow at a constant rate indefinitely.

The core insight is that a stock's value equals the stream of future dividends discounted back to today. The model is most appropriate for mature, dividend-paying companies with stable payout ratios.

## Formula

**Gordon Growth Model**:

```
P = D / (r - g)
```

Where:
- **P** = estimated fair price per share
- **D** = annual dividend per share (current / most recent)
- **r** = required rate of return (discount rate)
- **g** = constant dividend growth rate (must be < r)

The model applies three different discount rates to generate a price range:

```
Expensive Price = D / (low_r - g)     (optimistic / lower discount rate)
Fair Price      = D / (mid_r - g)     (base case)
Cheap Price     = D / (high_r - g)    (conservative / higher discount rate)
```

A higher discount rate produces a lower price (more conservative), so the mapping is inverted relative to the rate names.

## Inputs
| Input | Source | Type | Required | Description |
|-------|--------|------|----------|-------------|
| annual_dividend | Financial statements | float | Yes | Most recent annual dividend per share (must be > 0) |
| growth_rate | Analyst estimate / historical | float | No | Expected constant dividend growth rate (default: 0.03 / 3%) |
| discount_rates | User / model config | tuple[float, float, float] | No | (low, mid, high) discount rates (default: 0.08, 0.10, 0.12) |

## Outputs
| Output | Type | Range | Description |
|--------|------|-------|-------------|
| cheap_price | float | >= 0 | Price at the highest discount rate (most conservative) |
| fair_price | float | >= 0 | Price at the mid discount rate |
| expensive_price | float | >= 0 | Price at the lowest discount rate (most optimistic) |
| confidence | float | 0.0-1.0 | Fixed at 0.6 when dividend > 0 |
| details.dividend | float | -- | Annual dividend used |
| details.growth_rate | float | -- | Growth rate assumption |
| details.discount_rates | dict | -- | The three discount rates |

## Assumptions & Limitations

- **Dividends required**: The model returns zero values for non-dividend-paying companies. This excludes a large portion of growth stocks.
- **Constant growth**: The model assumes dividends grow at a single constant rate forever. In practice, growth rates change as companies mature.
- **g < r constraint**: If the growth rate equals or exceeds the discount rate, the formula breaks down (division by zero or negative, producing infinite or negative prices). The implementation returns zero values in this case.
- **Sensitivity**: Small changes in `g` or `r` produce large price changes. A 1% change in growth rate can shift the fair price by 20-40%. This high sensitivity is a known weakness.
- **No retained earnings value**: The model only values the dividend stream. Companies that retain and reinvest earnings productively create value not captured by DDM.

### TW Stock Context (台股備註)

Many TW stocks have relatively high dividend yields compared to US markets, making DDM more applicable. However, TW companies often pay dividends annually (usually between June and September, 除息旺季), and some mix cash dividends (現金股利) with stock dividends (股票股利). For DDM purposes, use only the cash dividend component and convert stock dividends to equivalent cash value if needed.

Default discount rates of 8-12% may need adjustment for TW market conditions. Consider using:
- Taiwan 10-year government bond yield + equity risk premium as the base discount rate.
- A range of +/-2% around the base rate for the three-tier estimate.

## Confidence Score

The confidence is fixed at `0.6` when the annual dividend is positive. This relatively modest score reflects:
- The strong assumption of constant perpetual growth.
- Sensitivity to small parameter changes.
- The model ignoring non-dividend value creation.

When the dividend is zero or growth >= discount rate, confidence = 0.0.

## Validation

- **Dividend yield cross-check**: The fair price implies a dividend yield of `D / fair_price`. Compare this against the stock's historical dividend yield range. If the implied yield is outside the historical range, the growth or discount assumptions may be off.
- **Comparison with PE model**: For stable dividend payers, PE and DDM fair values should be in the same ballpark. Large discrepancies suggest misaligned assumptions.
- **Growth rate validation**: Compare the assumed growth rate against the company's 5-year historical dividend CAGR. Use `CAGR = (D_latest / D_5yr_ago)^(1/5) - 1`.

## References

- Gordon, M.J. _The Investment, Financing, and Valuation of the Corporation_, 1962.
- [Investopedia: Gordon Growth Model](https://www.investopedia.com/terms/g/gordongrowthmodel.asp)
- [Investopedia: Dividend Discount Model](https://www.investopedia.com/terms/d/ddm.asp)
