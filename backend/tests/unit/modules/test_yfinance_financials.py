from unittest.mock import MagicMock, patch
import pytest
import pandas as pd
from app.modules.financial_analysis.base import FinancialProvider
from app.modules.financial_analysis.yfinance_financials import YFinanceFinancialProvider


def _mock_income_stmt() -> pd.DataFrame:
    return pd.DataFrame(
        {"2024-12-31": [1000000, 600000, 200000, 150000],
         "2024-09-30": [950000, 580000, 180000, 140000]},
        index=["Total Revenue", "Cost Of Revenue", "Operating Income", "Net Income"],
    )


def _mock_balance_sheet() -> pd.DataFrame:
    return pd.DataFrame(
        {"2024-12-31": [5000000, 2000000, 1500000, 3000000, 500000, 800000],
         "2024-09-30": [4800000, 1900000, 1400000, 2900000, 480000, 750000]},
        index=["Total Assets", "Current Assets", "Current Liabilities",
               "Stockholders Equity", "Inventory", "Net Receivables"],
    )


def _mock_cashflow() -> pd.DataFrame:
    return pd.DataFrame(
        {"2024-12-31": [200000, -50000, -30000],
         "2024-09-30": [180000, -45000, -25000]},
        index=["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"],
    )


def test_provider_is_financial_provider() -> None:
    assert isinstance(YFinanceFinancialProvider(), FinancialProvider)


@pytest.mark.asyncio
async def test_fetch_financials() -> None:
    mock_ticker = MagicMock()
    mock_ticker.info = {"currency": "USD"}
    mock_ticker.quarterly_income_stmt = _mock_income_stmt()
    mock_ticker.quarterly_balance_sheet = _mock_balance_sheet()
    mock_ticker.quarterly_cashflow = _mock_cashflow()
    mock_ticker.income_stmt = pd.DataFrame()
    mock_ticker.balance_sheet = pd.DataFrame()
    mock_ticker.cashflow = pd.DataFrame()

    with patch("app.modules.financial_analysis.yfinance_financials.yf.Ticker", return_value=mock_ticker):
        provider = YFinanceFinancialProvider()
        data = await provider.fetch_financials("AAPL")

    assert data.symbol == "AAPL"
    assert data.currency == "USD"
    assert len(data.income_statements) == 2
    assert data.income_statements[0].data["Total Revenue"] == 1000000


@pytest.mark.asyncio
async def test_empty_financials() -> None:
    mock_ticker = MagicMock()
    mock_ticker.info = {"currency": "USD"}
    mock_ticker.quarterly_income_stmt = pd.DataFrame()
    mock_ticker.quarterly_balance_sheet = pd.DataFrame()
    mock_ticker.quarterly_cashflow = pd.DataFrame()
    mock_ticker.income_stmt = pd.DataFrame()
    mock_ticker.balance_sheet = pd.DataFrame()
    mock_ticker.cashflow = pd.DataFrame()

    with patch("app.modules.financial_analysis.yfinance_financials.yf.Ticker", return_value=mock_ticker):
        provider = YFinanceFinancialProvider()
        data = await provider.fetch_financials("INVALID")

    assert data.income_statements == []
