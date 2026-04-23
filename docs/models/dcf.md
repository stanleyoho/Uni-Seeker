# DCF (Discounted Cash Flow) Model Specification

## Overview
- **Name**: DCF (Discounted Cash Flow)
- **Type**: Valuation
- **Module**: `app/modules/price_estimator/dcf.py`
- **Function**: `estimate_by_dcf`

## Theory

The DCF model estimates a company's intrinsic value by projecting its future free cash flows and discounting them back to present value. It is considered the gold standard of intrinsic valuation because it values the company based on cash generation rather than market multiples.

The total enterprise value equals the sum of:
1. Present value of projected free cash flows during the explicit forecast period.
2. Present value of the terminal value (representing all cash flows beyond the forecast period).

## Formula

**Projected FCF** for each year:

```
FCF_t = FCF_0 * (1 + g) ^ t
```

**Present Value of projected FCFs**:

```
PV_FCF = sum( FCF_t / (1 + r)^t )  for t = 1 to N
```

**Terminal Value** (using the perpetuity growth method):

```
Terminal_FCF  = FCF_N * (1 + g_terminal)
Terminal_Value = Terminal_FCF / (r - g_terminal)
PV_Terminal    = Terminal_Value / (1 + r)^N
```

**Total Value and Price**:

```
Total Value    = PV_FCF + PV_Terminal
Fair Price     = Total Value / Shares Outstanding
Cheap Price    = Fair Price * 0.70   (30% margin of safety)
Expensive Price = Fair Price * 1.30   (30% premium)
```

Where:
- **FCF_0** = current free cash flow
- **g** = growth rate during the projection period
- **g_terminal** = long-term perpetual growth rate
- **r** = discount rate (WACC)
- **N** = number of projection years

## Inputs
| Input | Source | Type | Required | Description |
|-------|--------|------|----------|-------------|
| free_cash_flow | Cash flow statement | float | Yes | Current annual FCF (must be > 0) |
| growth_rate | Analyst estimate | float | No | Annual FCF growth rate (default: 0.05 / 5%) |
| terminal_growth | Macro assumption | float | No | Perpetual growth rate (default: 0.02 / 2%) |
| discount_rate | WACC estimate | float | No | Discount rate (default: 0.10 / 10%) |
| shares_outstanding | Company filings | float | No | Number of shares (default: 1.0) |
| projection_years | Model config | int | No | Explicit forecast period (default: 5) |

## Outputs
| Output | Type | Range | Description |
|--------|------|-------|-------------|
| cheap_price | float | >= 0 | Fair price * 0.70 (margin of safety) |
| fair_price | float | >= 0 | DCF-derived intrinsic value per share |
| expensive_price | float | >= 0 | Fair price * 1.30 |
| confidence | float | 0.0-1.0 | Fixed at 0.5 |
| details.fcf | float | -- | Input FCF |
| details.growth_rate | float | -- | Growth rate used |
| details.terminal_growth | float | -- | Terminal growth rate |
| details.discount_rate | float | -- | Discount rate used |
| details.pv_fcf | float | -- | Present value of projected FCFs |
| details.pv_terminal | float | -- | Present value of terminal value |

## Assumptions & Limitations

- **Positive FCF required**: Companies with negative free cash flow cannot be valued with this simplified model. Returns zero values in this case.
- **Discount rate > terminal growth**: If `r <= g_terminal`, the terminal value formula breaks down. The implementation returns zero values.
- **Terminal value dominance**: In a typical 5-year DCF, the terminal value represents 60-80% of total value. This means the result is highly sensitive to `g_terminal` and `r`, which are the most uncertain inputs.
- **Single growth rate**: The model uses a single growth rate for all projection years. A two-stage or three-stage model with different growth phases would be more accurate for high-growth companies transitioning to maturity.
- **No explicit WACC calculation**: The discount rate is a single input, not computed from the company's capital structure. For a proper WACC: `WACC = E/(E+D) * r_e + D/(E+D) * r_d * (1 - tax_rate)`.
- **Fixed margin of safety**: The 30% margin is a heuristic. More sophisticated approaches would calculate scenario-based ranges.

### TW Stock Context (台股備註)

- Use free cash flow from the cash flow statement (自由現金流 = 營業現金流 - 資本支出).
- For the discount rate, consider Taiwan's lower interest rate environment. A WACC of 7-10% is common for TW blue chips. High-growth tech companies (like IC design houses) may warrant 10-14%.
- Terminal growth rate should not exceed Taiwan's long-term nominal GDP growth rate (approximately 2-4%).
- Shares outstanding for TW stocks should account for treasury shares (庫藏股) if applicable.

## Confidence Score

The confidence is fixed at `0.5`, reflecting:
- Heavy reliance on assumptions (growth rate, discount rate, terminal growth).
- High sensitivity to small parameter changes.
- Terminal value dominance amplifies estimation error.

When FCF <= 0 or shares_outstanding <= 0 or discount_rate <= terminal_growth, confidence = 0.0.

## Validation

- **Reverse DCF**: Given the current market price, solve for the implied growth rate. If the implied rate is unrealistic (e.g., 30% perpetual growth), the stock may be overvalued.
- **Terminal value check**: Terminal value should typically be 50-75% of total enterprise value. If it exceeds 85%, the explicit forecast period may be too short or the terminal growth rate too high.
- **Sensitivity table**: Vary growth_rate (+/-2%) and discount_rate (+/-2%) in a matrix. If the fair price range is extremely wide, the model is not providing actionable insight for the given stock.
- **Cross-model check**: Compare DCF fair value against PE and DDM estimates. The composite model (`composite.py`) handles this automatically using confidence-weighted averaging.

## References

- Damodaran, Aswath. _Investment Valuation_, 3rd Edition, 2012.
- Damodaran, Aswath. _The Little Book of Valuation_, 2011.
- [Investopedia: Discounted Cash Flow](https://www.investopedia.com/terms/d/dcf.asp)
