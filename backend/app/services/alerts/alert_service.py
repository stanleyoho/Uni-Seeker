"""AlertService — user-defined alert rule orchestration.

Owns:
  * Input validation for create/update (rule_type vocabulary,
    threshold sign, symbol/market presence per rule_type).
  * Tier quota enforcement (max_alert_rules).
  * Building an EvaluationContext from positions + portfolio summary.
  * Iterating active rules through the pure evaluator and dispatching
    TG notifications on triggers.
  * Persisting status transitions (ACTIVE → TRIGGERED) so the rule
    pauses itself after firing once.

No DB queries live here; we route every read/write through
``AlertRuleRepo`` + the existing portfolio repos / services. No Telegram
HTTP lives here either — we reuse ``send_telegram_message`` from the Y7
infrastructure.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from decimal import Decimal
from typing import TYPE_CHECKING

from app.config import settings
from app.db.models.alerts.alert_rule import (
    ALERT_RULE_TYPES,
    ALERT_STATUSES,
    ALERT_THRESHOLD_TYPES,
    AlertRule,
)
from app.modules.alerts.evaluator import (
    EvaluationContext,
    PositionSnapshot,
    RuleType,
    ThresholdType,
    evaluate_rule,
)
from app.modules.billing.tier_limits import get_limit
from app.modules.notifications.dispatcher import dispatch_notification
from app.obs.logging import get_logger
from app.repositories.alerts.alert_repo import AlertRuleRepo
from app.services.audit import log_audit_event
from app.services.portfolio.exceptions import (
    PortfolioServiceError,
    TierLimitExceeded,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User
    from app.modules.portfolio.live_price_fetcher import LivePriceFetcher


logger = get_logger(component="alert_service")


class AlertRuleNotFound(PortfolioServiceError):
    """Rule id not present OR not owned by the requesting user."""


class InvalidAlertRule(PortfolioServiceError):
    """User-supplied input fails domain validation.

    ``code`` is a short snake_case identifier the API layer surfaces
    verbatim in the ``detail`` field (so the frontend can map it to a
    localised message).
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_POSITION_RULES = {
    "POSITION_PRICE_DROP",
    "POSITION_PRICE_RISE",
    "POSITION_PNL_PCT_ABOVE",
    "POSITION_PNL_PCT_BELOW",
}
_PORTFOLIO_RULES = {
    "PORTFOLIO_VALUE_ABOVE",
    "PORTFOLIO_VALUE_BELOW",
}
_PNL_RULES = {"POSITION_PNL_PCT_ABOVE", "POSITION_PNL_PCT_BELOW"}


class AlertService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user
        self._repo = AlertRuleRepo(db)

    # ── CRUD ───────────────────────────────────────────────────────────

    async def create_rule(
        self,
        *,
        name: str,
        rule_type: str,
        threshold_value: Decimal,
        threshold_type: str,
        symbol: str | None = None,
        market: str | None = None,
    ) -> AlertRule:
        """Create a rule for the current user.

        Tier-quota second line — the API dependency layer already runs
        ``tier_guard(limit_key="max_alert_rules")`` but a programmer who
        forgets the dependency would still bypass the quota. We re-check
        here so the data layer is the final authority.
        """
        self._validate_inputs(
            name=name,
            rule_type=rule_type,
            threshold_value=threshold_value,
            threshold_type=threshold_type,
            symbol=symbol,
            market=market,
        )

        if settings.enable_monetization:
            limit = get_limit(self._user.tier, "max_alert_rules")
            if limit is not None:
                current = await self._repo.count_by_user(self._user.id)
                if current >= limit:
                    raise TierLimitExceeded(
                        limit_key="max_alert_rules",
                        current=current,
                        limit=limit,
                    )

        rule = await self._repo.create(
            user_id=self._user.id,
            name=name,
            rule_type=rule_type,
            threshold_value=threshold_value,
            threshold_type=threshold_type,
            symbol=symbol,
            market=market,
        )
        await log_audit_event(
            self._db,
            action="alert_rule_created",
            user_id=self._user.id,
            resource_type="alert_rule",
            resource_id=str(rule.id),
            after_state={
                "rule_type": rule_type,
                "threshold_value": str(threshold_value),
                "threshold_type": threshold_type,
                "symbol": symbol,
                "market": market,
            },
        )
        return rule

    async def list_rules(self) -> list[AlertRule]:
        return await self._repo.list_by_user(self._user.id)

    async def get_rule(self, rule_id: int) -> AlertRule:
        rule = await self._repo.get(rule_id, user_id=self._user.id)
        if rule is None:
            raise AlertRuleNotFound(f"rule {rule_id}")
        return rule

    async def update_rule(
        self,
        rule_id: int,
        **fields: object,
    ) -> AlertRule:
        """Patch a rule. Whitelisted set: name, status, threshold_value,
        threshold_type. rule_type / symbol / market are immutable once
        created — if the user wants a different scope they delete and
        recreate (keeps the lifecycle clean)."""
        # Reject unknown / non-mutable keys explicitly so a typo doesn't
        # silently no-op.
        allowed = {"name", "status", "threshold_value", "threshold_type"}
        patch = {k: v for k, v in fields.items() if k in allowed and v is not None}

        if "status" in patch and patch["status"] not in ALERT_STATUSES:
            raise InvalidAlertRule("invalid_status")
        if "threshold_type" in patch and patch["threshold_type"] not in ALERT_THRESHOLD_TYPES:
            raise InvalidAlertRule("invalid_threshold_type")
        if "name" in patch:
            name_val = str(patch["name"]).strip()
            if not name_val or len(name_val) > 100:
                raise InvalidAlertRule("invalid_name")
            patch["name"] = name_val

        updated = await self._repo.update(rule_id, user_id=self._user.id, **patch)
        if updated is None:
            raise AlertRuleNotFound(f"rule {rule_id}")
        return updated

    async def delete_rule(self, rule_id: int) -> None:
        removed = await self._repo.delete(rule_id, user_id=self._user.id)
        if not removed:
            raise AlertRuleNotFound(f"rule {rule_id}")
        await log_audit_event(
            self._db,
            action="alert_rule_deleted",
            user_id=self._user.id,
            resource_type="alert_rule",
            resource_id=str(rule_id),
        )

    # ── evaluation ─────────────────────────────────────────────────────

    async def evaluate_user_rules(
        self,
        fetcher: LivePriceFetcher,
    ) -> dict[str, int]:
        """Evaluate every ACTIVE rule for the current user.

        Algorithm:
          1. Load active rules.
          2. Build an EvaluationContext from the user's positions +
             summary (one quote batch per evaluation pass).
          3. For each rule: evaluate; on trigger send TG + persist
             status=TRIGGERED + last_triggered_at.
          4. Always update last_evaluated_at — even on misses — so the
             UI can show "last checked 3 minutes ago".

        Returns a counter dict suitable for logging / audit:
            {"evaluated": N, "triggered": M, "notified": K, "errors": E}
        """
        rules = await self._repo.list_active_by_user(self._user.id)
        counts = {"evaluated": 0, "triggered": 0, "notified": 0, "errors": 0}
        if not rules:
            return counts

        context = await self._build_context(fetcher, rules)
        now = datetime.now(UTC)

        for rule in rules:
            counts["evaluated"] += 1
            try:
                result = evaluate_rule(
                    rule_type=rule.rule_type,
                    threshold=Decimal(str(rule.threshold_value)),
                    threshold_type=rule.threshold_type,
                    symbol=rule.symbol,
                    market=rule.market,
                    context=context,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "alert_evaluation_failed",
                    rule_id=rule.id,
                    error=str(exc),
                )
                counts["errors"] += 1
                continue

            if result.triggered:
                counts["triggered"] += 1
                # Round 14: route through the dispatcher so TG + email
                # both fire when the user opted into each. The dispatcher
                # checks per-channel eligibility itself — no double guard
                # needed here.
                tg_text = self._format_trigger_message(rule, result.message)
                title = f"Alert triggered: {rule.name}"
                app_url = settings.app_url.rstrip("/")
                deep_link = f"{app_url}/settings/alerts"
                dispatched = await dispatch_notification(
                    self._user,
                    title=title,
                    body_text=result.message,
                    tg_text=tg_text,
                    deep_link=deep_link,
                )
                if int(dispatched["channels_succeeded"]) > 0:
                    counts["notified"] += 1
                attempted = int(dispatched["channels_attempted"])
                succeeded = int(dispatched["channels_succeeded"])
                if attempted > 0 and succeeded < attempted:
                    counts["errors"] += 1
                # Pause after firing so the user isn't spammed.
                await self._repo.update_status(
                    rule.id,
                    status="TRIGGERED",
                    last_evaluated_at=now,
                    last_triggered_at=now,
                )
            else:
                await self._repo.update_status(
                    rule.id,
                    status="ACTIVE",  # keep current state
                    last_evaluated_at=now,
                )

        return counts

    async def evaluate_one(
        self,
        rule_id: int,
        fetcher: LivePriceFetcher,
    ) -> dict[str, object]:
        """Manual single-rule evaluation (Pro feature: "evaluate now").

        Returns a small dict the API layer can serialise — keeps the
        endpoint contract decoupled from the internal EvaluationResult
        dataclass.
        """
        rule = await self.get_rule(rule_id)
        context = await self._build_context(fetcher, [rule])
        result = evaluate_rule(
            rule_type=rule.rule_type,
            threshold=Decimal(str(rule.threshold_value)),
            threshold_type=rule.threshold_type,
            symbol=rule.symbol,
            market=rule.market,
            context=context,
        )
        now = datetime.now(UTC)
        if result.triggered:
            # Round 14: dispatcher handles TG + email per user opt-in.
            tg_text = self._format_trigger_message(rule, result.message)
            title = f"Alert triggered: {rule.name}"
            app_url = settings.app_url.rstrip("/")
            deep_link = f"{app_url}/settings/alerts"
            await dispatch_notification(
                self._user,
                title=title,
                body_text=result.message,
                tg_text=tg_text,
                deep_link=deep_link,
            )
            await self._repo.update_status(
                rule.id,
                status="TRIGGERED",
                last_evaluated_at=now,
                last_triggered_at=now,
            )
        else:
            await self._repo.update_status(
                rule.id,
                status=rule.status,
                last_evaluated_at=now,
            )
        return {
            "triggered": result.triggered,
            "actual_value": str(result.actual_value),
            "threshold": str(result.threshold),
            "message": result.message,
        }

    # ── internals ──────────────────────────────────────────────────────

    @staticmethod
    def _validate_inputs(
        *,
        name: str,
        rule_type: str,
        threshold_value: Decimal,
        threshold_type: str,
        symbol: str | None,
        market: str | None,
    ) -> None:
        if not name or len(name) > 100:
            raise InvalidAlertRule("invalid_name")
        if rule_type not in ALERT_RULE_TYPES:
            raise InvalidAlertRule("invalid_rule_type")
        if threshold_type not in ALERT_THRESHOLD_TYPES:
            raise InvalidAlertRule("invalid_threshold_type")

        # Scope consistency: matches the DB CHECK constraint.
        if rule_type in _POSITION_RULES:
            if not symbol or not market:
                raise InvalidAlertRule("missing_symbol_market")
        elif rule_type in _PORTFOLIO_RULES:
            if symbol is not None or market is not None:
                raise InvalidAlertRule("symbol_not_allowed_for_portfolio_rule")
            if threshold_type != "ABSOLUTE":
                raise InvalidAlertRule("portfolio_rule_requires_absolute")

        # PNL rules: PCT only (DB CHECK doesn't know this).
        if rule_type in _PNL_RULES and threshold_type != "PCT":
            raise InvalidAlertRule("pnl_rule_requires_pct")

        # Sign rules — PRICE_DROP / PRICE_RISE / VALUE_* must be positive.
        # PNL_PCT_BELOW accepts negatives (stop-loss style).
        if rule_type == "POSITION_PNL_PCT_BELOW":
            pass
        else:
            if threshold_value <= 0:
                raise InvalidAlertRule("threshold_must_be_positive")

    async def _build_context(
        self,
        fetcher: LivePriceFetcher,
        rules: list[AlertRule],
    ) -> EvaluationContext:
        """Materialise a per-evaluation EvaluationContext.

        We import the portfolio services lazily to avoid a hard circular
        dependency (services.alerts → services.portfolio →
        services.alerts via the audit module would be a cycle in some
        future build configurations).
        """
        from app.services.portfolio.position_service import (
            PortfolioPositionService,
        )
        from app.services.portfolio.summary_service import (
            PortfolioSummaryService,
        )

        positions: dict[tuple[str, str], PositionSnapshot] = {}
        portfolio_value = Decimal("0")

        # Position-scoped rules need their own snapshot — fetch all the
        # user's positions in one pass (cheap once cached by the fetcher).
        position_service = PortfolioPositionService(self._db, self._user, fetcher)
        enriched = await position_service.list_positions()
        for p in enriched:
            key = (
                p.symbol,
                p.market.value if hasattr(p.market, "value") else str(p.market),
            )
            # `unrealized_pnl_pct` is already expressed as a decimal
            # (0.10 == 10%). Multiply by 100 so the rule threshold
            # comparison is in percent units (matches the user's
            # "PNL above 10%" phrasing).
            unr_pct: Decimal | None = None
            if p.unrealized_pnl is not None:
                unr_pct = Decimal(str(p.unrealized_pnl.unrealized_pnl_pct)) * Decimal("100")
            positions[key] = PositionSnapshot(
                last_price=p.last_price,
                prev_close=p.prev_close,
                quantity=p.quantity,
                avg_cost=p.avg_cost,
                unrealized_pnl_pct=unr_pct,
            )

        # Only compute the portfolio total when at least one rule
        # actually needs it — skips a quote roundtrip for users who
        # only have POSITION_* rules.
        needs_portfolio = any(r.rule_type in _PORTFOLIO_RULES for r in rules)
        if needs_portfolio:
            summary_service = PortfolioSummaryService(self._db, self._user, fetcher)
            summary = await summary_service.get_user_summary()
            portfolio_value = Decimal(str(summary.total_value))

        return EvaluationContext(
            portfolio_value=portfolio_value,
            positions=positions,
        )

    @staticmethod
    def _format_trigger_message(rule: AlertRule, body: str) -> str:
        """Build the Telegram body. Mirror 13F notifier formatting —
        STRATOS users already see this voice elsewhere."""
        app_url = settings.app_url.rstrip("/")
        link = f"{app_url}/settings/alerts"
        # No HTML escape needed — body is generated by the evaluator
        # from numeric snapshots, not user-attacker-controlled strings.
        return f"<b>Alert triggered</b>: {rule.name}\n{body}\n\n管理規則: {link}"


__all__ = [
    "AlertRuleNotFound",
    "AlertService",
    "InvalidAlertRule",
]
