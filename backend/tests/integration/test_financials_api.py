from unittest.mock import patch, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.modules.financial_analysis.base import FinancialData, FinancialStatement


def _mock_financial_data() -> FinancialData:
    return FinancialData(
        symbol="AAPL", currency="USD",
        income_statements=[
            FinancialStatement(period="2024-12-31", period_type="quarterly", data={
                "Total Revenue": 1000000, "Cost Of Revenue": 600000,
                "Operating Income": 200000, "Net Income": 150000,
            }),
        ],
        balance_sheets=[
            FinancialStatement(period="2024-12-31", period_type="quarterly", data={
                "Total Assets": 5000000, "Current Assets": 2000000,
                "Current Liabilities": 1500000, "Stockholders Equity": 3000000,
                "Total Liabilities Net Minority Interest": 2000000,
                "Inventory": 500000, "Net Receivables": 800000,
            }),
        ],
        cash_flows=[
            FinancialStatement(period="2024-12-31", period_type="quarterly", data={
                "Operating Cash Flow": 200000, "Capital Expenditure": -50000,
            }),
        ],
    )


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_get_full_analysis(app) -> None:
    with patch(
        "app.api.v1.financials.YFinanceFinancialProvider.fetch_financials",
        new_callable=AsyncMock,
        return_value=_mock_financial_data(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/financials/AAPL")
            assert resp.status_code == 200
            data = resp.json()
            assert data["financials"]["symbol"] == "AAPL"
            assert len(data["ratios"]) == 1
            assert data["ratios"][0]["gross_margin"] == 0.4
            assert len(data["health_scores"]) == 1
            assert data["health_scores"][0]["total_score"] > 0


@pytest.mark.asyncio
async def test_get_ratios(app) -> None:
    with patch(
        "app.api.v1.financials.YFinanceFinancialProvider.fetch_financials",
        new_callable=AsyncMock,
        return_value=_mock_financial_data(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/financials/AAPL/ratios")
            assert resp.status_code == 200
            ratios = resp.json()
            assert len(ratios) == 1
            assert ratios[0]["net_margin"] == 0.15


@pytest.mark.asyncio
async def test_no_data_returns_404(app) -> None:
    empty = FinancialData(symbol="X", currency="USD")
    with patch(
        "app.api.v1.financials.YFinanceFinancialProvider.fetch_financials",
        new_callable=AsyncMock,
        return_value=empty,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/financials/INVALID")
            assert resp.status_code == 404
