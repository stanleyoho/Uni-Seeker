"""Integration tests for AlertService — CRUD + evaluation + TG fan-out."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserTier
from app.models.user import User
from app.modules.portfolio.live_price_fetcher import PriceQuote
from app.services.alerts.alert_service import (
    AlertRuleNotFoundError,
    AlertService,
    InvalidAlertRuleError,
)
from app.services.portfolio.exceptions import TierLimitExceeded


class _MockFetcher:
    def __init__(self, quotes: dict[str, tuple[Decimal, Decimal]]) -> None:
        self._quotes = quotes

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
        out: dict[str, PriceQuote] = {}
        for sid in stock_ids:
            if sid in self._quotes:
                last, prev = self._quotes[sid]
                out[sid] = PriceQuote(
                    stock_id=sid,
                    last_price=last,
                    prev_close=prev,
                    as_of=datetime(2026, 5, 19, tzinfo=UTC),
                )
        return out


async def _mk_user(
    db: AsyncSession,
    email: str,
    tier: UserTier = UserTier.PRO,
    chat_id: str | None = None,
) -> User:
    u = User(
        email=email,
        hashed_password="x" * 60,
        username=email.split("@")[0],
    )
    u.tier = tier
    if chat_id is not None:
        u.telegram_chat_id = chat_id
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_create_rule_valid(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "s1@test.com")
    service = AlertService(db_session, user)
    rule = await service.create_rule(
        name="NVDA",
        rule_type="POSITION_PRICE_DROP",
        threshold_value=Decimal("10"),
        threshold_type="PCT",
        symbol="NVDA",
        market="US_NASDAQ",
    )
    await db_session.commit()
    assert rule.id is not None
    assert rule.status == "ACTIVE"


@pytest.mark.asyncio
async def test_create_rule_rejects_position_without_symbol(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "s2@test.com")
    service = AlertService(db_session, user)
    with pytest.raises(InvalidAlertRuleError) as exc:
        await service.create_rule(
            name="bad",
            rule_type="POSITION_PRICE_DROP",
            threshold_value=Decimal("10"),
            threshold_type="PCT",
            symbol=None,
            market=None,
        )
    assert exc.value.code == "missing_symbol_market"


@pytest.mark.asyncio
async def test_create_rule_rejects_portfolio_with_pct(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "s3@test.com")
    service = AlertService(db_session, user)
    with pytest.raises(InvalidAlertRuleError) as exc:
        await service.create_rule(
            name="bad",
            rule_type="PORTFOLIO_VALUE_ABOVE",
            threshold_value=Decimal("10"),
            threshold_type="PCT",
        )
    assert exc.value.code in {
        "portfolio_rule_requires_absolute",
    }


@pytest.mark.asyncio
async def test_create_rule_rejects_negative_threshold_for_price_drop(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "s4@test.com")
    service = AlertService(db_session, user)
    with pytest.raises(InvalidAlertRuleError):
        await service.create_rule(
            name="bad",
            rule_type="POSITION_PRICE_DROP",
            threshold_value=Decimal("-5"),
            threshold_type="PCT",
            symbol="NVDA",
            market="US_NASDAQ",
        )


@pytest.mark.asyncio
async def test_quota_enforced_when_monetization_on(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "quota@test.com", tier=UserTier.BASIC)

    with patch("app.services.alerts.alert_service.settings") as mock_settings:
        mock_settings.enable_monetization = True
        mock_settings.uni_telegram_bot_token = ""
        mock_settings.app_url = "http://localhost:3000"
        service = AlertService(db_session, user)
        # BASIC has max_alert_rules=5; create 5 then fail on the 6th.
        for i in range(5):
            await service.create_rule(
                name=f"r{i}",
                rule_type="PORTFOLIO_VALUE_ABOVE",
                threshold_value=Decimal("100"),
                threshold_type="ABSOLUTE",
            )
        await db_session.commit()
        with pytest.raises(TierLimitExceeded) as exc:
            await service.create_rule(
                name="over",
                rule_type="PORTFOLIO_VALUE_ABOVE",
                threshold_value=Decimal("200"),
                threshold_type="ABSOLUTE",
            )
        assert exc.value.limit_key == "max_alert_rules"


@pytest.mark.asyncio
async def test_update_rule_whitelist_only(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "u1@test.com")
    service = AlertService(db_session, user)
    rule = await service.create_rule(
        name="orig",
        rule_type="PORTFOLIO_VALUE_ABOVE",
        threshold_value=Decimal("100"),
        threshold_type="ABSOLUTE",
    )
    await db_session.commit()
    updated = await service.update_rule(
        rule.id, name="renamed", status="PAUSED", rule_type="ignored"
    )
    assert updated.name == "renamed"
    assert updated.status == "PAUSED"
    # rule_type is immutable — original kept.
    assert updated.rule_type == "PORTFOLIO_VALUE_ABOVE"


@pytest.mark.asyncio
async def test_delete_rule_not_found_raises(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "d1@test.com")
    service = AlertService(db_session, user)
    with pytest.raises(AlertRuleNotFoundError):
        await service.delete_rule(999999)


@pytest.mark.asyncio
async def test_evaluate_portfolio_value_no_positions(
    db_session: AsyncSession,
) -> None:
    """No positions → portfolio value 0; rule with threshold > 0 should
    not fire (above) and rule with threshold > 0 below threshold WILL fire."""
    user = await _mk_user(db_session, "e1@test.com")
    service = AlertService(db_session, user)
    await service.create_rule(
        name="r1",
        rule_type="PORTFOLIO_VALUE_ABOVE",
        threshold_value=Decimal("1000"),
        threshold_type="ABSOLUTE",
    )
    await db_session.commit()
    fetcher = _MockFetcher({})
    counts = await service.evaluate_user_rules(fetcher)
    assert counts["evaluated"] == 1
    assert counts["triggered"] == 0


@pytest.mark.asyncio
async def test_evaluate_one_returns_serialisable_dict(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "e2@test.com")
    service = AlertService(db_session, user)
    rule = await service.create_rule(
        name="r",
        rule_type="PORTFOLIO_VALUE_BELOW",
        threshold_value=Decimal("999999999"),
        threshold_type="ABSOLUTE",
    )
    await db_session.commit()
    fetcher = _MockFetcher({})
    result = await service.evaluate_one(rule.id, fetcher)
    assert "triggered" in result
    assert "actual_value" in result
    assert "threshold" in result
    assert "message" in result


@pytest.mark.asyncio
async def test_evaluate_triggers_pauses_rule(
    db_session: AsyncSession,
) -> None:
    user = await _mk_user(db_session, "trig@test.com")
    service = AlertService(db_session, user)
    rule = await service.create_rule(
        name="trip-me",
        rule_type="PORTFOLIO_VALUE_BELOW",
        threshold_value=Decimal("999999999"),
        threshold_type="ABSOLUTE",
    )
    await db_session.commit()
    fetcher = _MockFetcher({})
    # No TG configured → notify skipped but rule still marked TRIGGERED.
    counts = await service.evaluate_user_rules(fetcher)
    assert counts["triggered"] == 1
    await db_session.refresh(rule)
    assert rule.status == "TRIGGERED"
    assert rule.last_triggered_at is not None
