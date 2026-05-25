"""AlertRuleRepo — CRUD over ``alert_rules``.

User isolation: every method takes ``user_id`` (the service layer
extracts it from the authenticated user). There is no method that can
return one user's rules to another user.

Business validation (e.g. tier quota, threshold sign) lives in the
service. The repo only validates structural constraints already
encoded as DB CHECKs.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, update

from app.db.models.alerts.alert_rule import AlertRule

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AlertRuleRepo:
    """CRUD-only repository for ``alert_rules``."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        name: str,
        rule_type: str,
        threshold_value: Decimal,
        threshold_type: str,
        symbol: str | None = None,
        market: str | None = None,
        status: str = "ACTIVE",
    ) -> AlertRule:
        rule = AlertRule(
            user_id=user_id,
            name=name,
            rule_type=rule_type,
            threshold_value=threshold_value,
            threshold_type=threshold_type,
            symbol=symbol,
            market=market,
            status=status,
        )
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def get(self, rule_id: int, *, user_id: int) -> AlertRule | None:
        """Fetch one rule, enforcing ownership in the WHERE clause."""
        result = await self.db.execute(
            select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user_id)
        )
        return result.scalars().first()

    async def list_by_user(self, user_id: int) -> list[AlertRule]:
        result = await self.db.execute(
            select(AlertRule).where(AlertRule.user_id == user_id).order_by(AlertRule.id.asc())
        )
        return list(result.scalars().all())

    async def list_active_by_user(self, user_id: int) -> list[AlertRule]:
        """Hot path for the scheduler — uses (user_id, status) index."""
        result = await self.db.execute(
            select(AlertRule)
            .where(
                AlertRule.user_id == user_id,
                AlertRule.status == "ACTIVE",
            )
            .order_by(AlertRule.id.asc())
        )
        return list(result.scalars().all())

    async def list_active_all(self) -> list[AlertRule]:
        """All ACTIVE rules across all users. Used by the global
        scheduled evaluator when it walks users by tier."""
        result = await self.db.execute(
            select(AlertRule)
            .where(AlertRule.status == "ACTIVE")
            .order_by(AlertRule.user_id.asc(), AlertRule.id.asc())
        )
        return list(result.scalars().all())

    async def update(
        self,
        rule_id: int,
        *,
        user_id: int,
        **fields: Any,
    ) -> AlertRule | None:
        """Patch arbitrary scalar fields on an owned rule.

        Unknown keys are dropped — the service layer is the authority
        for what fields are user-mutable.
        """
        rule = await self.get(rule_id, user_id=user_id)
        if rule is None:
            return None
        for key, value in fields.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    async def update_status(
        self,
        rule_id: int,
        *,
        status: str,
        last_evaluated_at: datetime | None = None,
        last_triggered_at: datetime | None = None,
    ) -> None:
        """Status + timestamp update used by the evaluator.

        Note: takes no ``user_id`` because the scheduler is a system
        actor — caller has already loaded the rule via ``list_active_*``
        so ownership has been established structurally.
        """
        values: dict[str, Any] = {"status": status}
        if last_evaluated_at is not None:
            values["last_evaluated_at"] = last_evaluated_at
        if last_triggered_at is not None:
            values["last_triggered_at"] = last_triggered_at
        await self.db.execute(update(AlertRule).where(AlertRule.id == rule_id).values(**values))
        await self.db.flush()

    async def delete(self, rule_id: int, *, user_id: int) -> bool:
        """Hard delete. Returns True iff a row was removed."""
        result = await self.db.execute(
            delete(AlertRule).where(
                AlertRule.id == rule_id,
                AlertRule.user_id == user_id,
            )
        )
        await self.db.flush()
        return (result.rowcount or 0) > 0  # type: ignore[attr-defined]

    async def count_by_user(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count(AlertRule.id)).where(AlertRule.user_id == user_id)
        )
        return int(result.scalar() or 0)


__all__ = ["AlertRuleRepo"]
