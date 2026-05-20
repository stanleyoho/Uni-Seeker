"""PortfolioAccountService — account CRUD orchestration.

Spec §5.2 / §9. Owns the transaction boundary for account create /
update / delete, enforces tier quota AND feature flag at the service
layer (second line of defense per spec §9 双保险), and writes audit
log rows for every mutation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.config import settings
from app.models.enums import Market
from app.modules.billing.tier_limits import get_limit, has_feature
from app.repositories.portfolio import PortfolioAccountRepo
from app.services.audit import log_audit_event
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
    TierLimitExceeded,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.account import PortfolioAccount
    from app.models.user import User


class PortfolioAccountService:
    """Account lifecycle service.

    All public coroutines accept the same `(self, ...)` invariants:
    - The injected `AsyncSession` is the transaction boundary; callers
      commit (or roll back) after the call returns.
    - The injected `User` is the requesting principal — every read /
      write is scoped to `user.id` via the underlying repo's WHERE.

    NEVER bypass tier checks by calling repo directly from the API
    layer — that would defeat spec §9's second-line guarantee.
    """

    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user
        self._repo = PortfolioAccountRepo(db)

    # ── tier guards (spec §9 service-level second line) ─────────────────

    async def _assert_account_quota(self) -> None:
        """Raise `TierLimitExceeded` if creating one more account would
        push the user over `max_accounts` for their tier.

        Bypassed when `enable_monetization=False` (dev/test parity with
        `tier_limits.tier_guard`).
        """
        if not settings.enable_monetization:
            return
        limit = get_limit(self._user.tier, "max_accounts")
        if limit is None:
            return  # PRO / unlimited
        current = await self._repo.count_by_user(self._user.id)
        if current >= limit:
            raise TierLimitExceeded(
                limit_key="max_accounts", current=current, limit=limit
            )

    async def _assert_multi_account_feature(self) -> None:
        """For non-first accounts the user must have the
        `multi_account` feature flag (FREE = false).

        Bypassed when monetization toggle is off.
        """
        if not settings.enable_monetization:
            return
        # First account is always allowed (the flag gates the *second* one
        # onwards). Count first so we don't tax PRO users with a feature
        # check they trivially pass.
        existing = await self._repo.count_by_user(self._user.id)
        if existing == 0:
            return
        if not has_feature(self._user.tier, "multi_account"):
            raise TierFeatureUnavailable(feature="multi_account")

    # ── public API ──────────────────────────────────────────────────────

    async def create_account(
        self,
        name: str,
        market: Market,
        broker: str | None = None,
        currency: str = "TWD",
        description: str | None = None,
    ) -> PortfolioAccount:
        """Create a new portfolio account for the requesting user.

        Order of checks per spec §9:
        1. multi_account feature flag (if not first account)
        2. max_accounts numeric quota
        3. INSERT + audit log

        Raises:
            TierFeatureUnavailable: multi_account gated.
            TierLimitExceeded:      max_accounts reached.
        """
        await self._assert_multi_account_feature()
        await self._assert_account_quota()

        account = await self._repo.create(
            user_id=self._user.id,
            name=name,
            market=market,
            broker=broker,
            currency=currency,
            description=description,
        )
        await log_audit_event(
            self._db,
            action="portfolio_account_created",
            user_id=self._user.id,
            resource_type="portfolio_account",
            resource_id=str(account.id),
            after_state={
                "name": name,
                "market": market.value,
                "broker": broker,
                "currency": currency,
            },
        )
        return account

    async def list_accounts(self) -> list[PortfolioAccount]:
        """All accounts owned by the requesting user (oldest first)."""
        return await self._repo.list_by_user(self._user.id)

    async def get_account(self, account_id: int) -> PortfolioAccount:
        """Fetch one owned account or raise `PortfolioAccountNotFound`."""
        account = await self._repo.get_by_id(account_id, user_id=self._user.id)
        if account is None:
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )
        return account

    async def update_account(
        self, account_id: int, **fields: Any
    ) -> PortfolioAccount:
        """Patch allowed fields on an owned account.

        Raises:
            PortfolioAccountNotFound: row missing or not owned.
        """
        # Capture before-state for audit log (best-effort — repo update
        # is atomic regardless).
        existing = await self.get_account(account_id)
        before = {
            "name": existing.name,
            "broker": existing.broker,
            "description": existing.description,
            "currency": existing.currency,
        }
        updated = await self._repo.update(
            account_id, user_id=self._user.id, **fields
        )
        if updated is None:
            # Race: deleted between fetch and update.
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )
        await log_audit_event(
            self._db,
            action="portfolio_account_updated",
            user_id=self._user.id,
            resource_type="portfolio_account",
            resource_id=str(account_id),
            before_state=before,
            after_state={
                "name": updated.name,
                "broker": updated.broker,
                "description": updated.description,
                "currency": updated.currency,
            },
        )
        return updated

    async def delete_account(self, account_id: int) -> None:
        """Delete an owned account; cascade removes trades / lots /
        positions via FK ON DELETE CASCADE.

        Raises:
            PortfolioAccountNotFound: row missing or not owned.
        """
        # Confirm ownership first so we can audit-log the right row id.
        await self.get_account(account_id)
        deleted = await self._repo.delete(account_id, user_id=self._user.id)
        if not deleted:
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )
        await log_audit_event(
            self._db,
            action="portfolio_account_deleted",
            user_id=self._user.id,
            resource_type="portfolio_account",
            resource_id=str(account_id),
        )
