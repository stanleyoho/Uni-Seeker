# Financial Health Scorer Specification

## Overview
- **Name**: Financial Health Scorer
- **Type**: Scoring
- **Module**: `app/modules/financial_analysis/scorer.py`
- **Function**: `calculate_health_score`
- **Dependencies**: `app/modules/financial_analysis/ratios.py` (provides `FinancialRatios`)

## Theory

The health scorer aggregates a company's financial ratios into a single composite score (0-100) across four equally weighted dimensions. It provides a quick, at-a-glance assessment of a company's financial condition without requiring deep fundamental analysis.

The approach is inspired by Piotroski's F-Score and similar multi-factor scoring systems, simplified for accessibility and adapted for the TW/US stock universe.

## Formula

The total score is the sum of four category scores, each scaled from 0 to 25:

```
Total Score = Profitability (0-25) + Efficiency (0-25) + Leverage (0-25) + Growth (0-25)
```

Total score is capped at 100.

Each sub-metric is scored using a linear interpolation function:

```
score_range(value, bad, good, max_score):
    if good > bad:  # higher is better
        score = (value - bad) / (good - bad) * max_score
    else:           # lower is better
        score = (bad - value) / (bad - good) * max_score
    clamped to [0, max_score]
```

If a ratio value is `None` (data unavailable), it receives 50% of the maximum sub-score (neutral default).

## Scoring Breakdown

### Profitability (0-25 points)

| Sub-metric | Weight | Bad | Good | Description |
|------------|--------|-----|------|-------------|
| Gross Margin | 8 pts | 0% | 40% | Revenue remaining after COGS |
| Operating Margin | 8 pts | -5% | 20% | Profit from core operations |
| ROE | 9 pts | 0% | 20% | Return on shareholders' equity |

### Efficiency (0-25 points)

| Sub-metric | Weight | Bad | Good | Description |
|------------|--------|-----|------|-------------|
| Inventory Turnover | 12 pts | 1x | 10x | How quickly inventory is sold |
| Receivable Turnover | 13 pts | 2x | 12x | How quickly receivables are collected |

### Leverage (0-25 points)

| Sub-metric | Weight | Bad | Good | Description |
|------------|--------|-----|------|-------------|
| Current Ratio | 10 pts | 0.5 | 2.0 | Short-term liquidity (higher is better) |
| Debt Ratio | 15 pts | 0.8 | 0.3 | Total liabilities / total assets (lower is better) |

### Growth (0-25 points)

| Sub-metric | Weight | Bad | Good | Description |
|------------|--------|-----|------|-------------|
| Revenue Growth (YoY) | 12 pts | -10% | 20% | Year-over-year revenue change |
| Net Income Growth (YoY) | 13 pts | -20% | 30% | Year-over-year net income change |

## Inputs
| Input | Source | Type | Required | Description |
|-------|--------|------|----------|-------------|
| ratios | `calculate_ratios()` | FinancialRatios | Yes | Pre-calculated financial ratios for a single period |

The `FinancialRatios` dataclass contains:
- `gross_margin`, `operating_margin`, `net_margin`, `roe`, `roa` (profitability)
- `inventory_turnover`, `receivable_turnover` (efficiency)
- `current_ratio`, `quick_ratio`, `debt_ratio` (leverage)
- `revenue_growth`, `net_income_growth` (growth)

## Outputs
| Output | Type | Range | Description |
|--------|------|-------|-------------|
| total_score | float | 0-100 | Composite health score |
| profitability_score | float | 0-25 | Profitability sub-score |
| efficiency_score | float | 0-25 | Efficiency sub-score |
| leverage_score | float | 0-25 | Leverage (solvency) sub-score |
| growth_score | float | 0-25 | Growth sub-score |
| details | dict[str, str] | -- | Explanatory text per category showing input ratio values |

## Score Interpretation

| Score Range | Rating | Interpretation |
|-------------|--------|----------------|
| 80-100 | Excellent | Strong fundamentals across all dimensions |
| 60-79 | Good | Solid overall with possible weakness in one area |
| 40-59 | Fair | Mixed signals; warrants deeper investigation |
| 20-39 | Weak | Multiple areas of concern |
| 0-19 | Critical | Significant financial distress indicators |

## Assumptions & Limitations

- **Equal weighting**: Each of the four categories contributes equally (25 points). In practice, the relative importance varies by industry -- leverage matters more for banks, growth matters more for tech.
- **Linear scoring**: The scoring function assumes a linear relationship between ratio values and quality. In reality, some ratios have diminishing returns (e.g., a current ratio of 5.0 is not necessarily better than 3.0; it might indicate idle capital).
- **Single-period snapshot**: The score reflects one period's ratios. A company might score well on growth after a one-time recovery but have poor long-term prospects.
- **Null handling**: Missing data receives a neutral 50% score rather than penalizing the company. This can inflate scores when data is sparse.
- **Industry-agnostic**: The same thresholds apply to all industries. A debt ratio of 0.7 is normal for a bank but alarming for a software company.

### TW Stock Context (台股備註)

- Financial ratios are computed from statements reported to the Taiwan Stock Exchange. Quarterly reports (季報) are required within 45 days of quarter-end; annual reports within 3 months of year-end.
- For TW financial companies (金融股), the standard efficiency ratios (inventory/receivable turnover) are not meaningful. The scorer will give neutral 50% scores for these, which is acceptable but not ideal.
- ROE > 15% is commonly used as a "good company" threshold among TW investors, aligning with the scorer's 0-20% range where 20% earns the full 9 points.

## Validation

- **Correlation check**: Plot total_score against subsequent 12-month stock returns. A well-calibrated scorer should show a positive (though imperfect) correlation.
- **Category balance**: For a diversified portfolio, the average score should be near 50. Extreme skew suggests threshold calibration issues.
- **Known-company sanity check**: Score well-known companies and verify the results match qualitative expectations. TSMC should score high; a company in financial distress should score low.
- **Comparison with Piotroski F-Score**: Cross-reference the health score against the Piotroski F-Score (0-9 scale) for the same stocks. Rankings should generally align.

## References

- Piotroski, Joseph D. "Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers," _Journal of Accounting Research_, 2000.
- [Investopedia: Piotroski Score](https://www.investopedia.com/terms/p/piotroski-score.asp)
- [Investopedia: Financial Ratios](https://www.investopedia.com/financial-ratios-4689817)
