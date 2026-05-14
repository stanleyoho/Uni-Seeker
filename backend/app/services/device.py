"""Device fingerprinting and registry helpers — Plan 4.5 T4+T8.

T4 provides ``compute_fingerprint(request)`` — a simple server-side
fingerprint combining UA, Accept-Language, and a network-prefix of the
client IP (so a user moving within the same /24 or /64 keeps the same
device identity).

T8 adds ``block_device(...)`` — soft-blocks a UserDevice row and writes
a ``device_blocked`` audit entry.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_device import UserDevice
from app.services.audit import log_audit_event


class _RequestLike(Protocol):
    """Minimal protocol so unit tests can pass SimpleNamespace."""
    headers: dict[str, str] | object  # FastAPI uses Headers (case-insensitive Mapping)
    client: object


def _ip_prefix(ip: str) -> str:
    """Reduce an IP address to a network prefix.

    - IPv4 → first 3 octets (``"1.2.3.4"`` → ``"1.2.3"``).
    - IPv6 → first 4 hexlets (``"2001:db8:85a3:0:..."`` → ``"2001:db8:85a3:0"``).
    - Anything else (empty / "localhost") → returned as-is.
    """
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:4])
    if "." in ip:
        return ip.rsplit(".", 1)[0]
    return ip


def compute_fingerprint(request: _RequestLike) -> str:
    """Hash UA + Accept-Language + IP prefix into a 64-char sha256 hex.

    The hash is intentionally coarse so that:
    - A user roaming on the same network keeps the same fingerprint.
    - Switching browser / language / network creates a new fingerprint
      → triggers the 3-device-limit guard implemented in T7.
    """
    headers = request.headers
    ua = headers.get("user-agent", "") if headers else ""
    al = headers.get("accept-language", "") if headers else ""
    client = getattr(request, "client", None)
    ip = client.host if client is not None and getattr(client, "host", None) else ""
    raw = f"{ua}|{al}|{_ip_prefix(ip)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def block_device(
    db: AsyncSession,
    device_id: uuid.UUID,
    *,
    reason: str,
    actor_type: str = "system",
) -> UserDevice | None:
    """Soft-block a device. Subsequent logins matching this row return 403
    ``device_blocked`` (see T7 login flow).

    Args:
        db:         Active AsyncSession.
        device_id:  UUID of the UserDevice to block.
        reason:     Short reason string for audit trail.
        actor_type: Who triggered the block — ``"system"`` (auto-rule, default),
                    ``"admin"`` (manual ops), or ``"user"`` (self-revoke).

    Returns:
        The updated UserDevice on success, or None if device_id was unknown
        (caller decides whether unknown id is an error or no-op).

    Notes:
        - Idempotent on already-blocked rows (re-stamps blocked_at, still
          writes an audit entry so the operator's intent is traceable).
        - Caller does NOT need to commit; this helper commits.
        - Auto-rules (e.g. 5 distinct logins in 1h) are intentionally NOT
          implemented here; they require rate-limit infrastructure and are
          on the Plan 4.5 backlog.
    """
    row = await db.scalar(select(UserDevice).where(UserDevice.id == device_id))
    if row is None:
        return None

    row.blocked_at = datetime.now(timezone.utc)
    await log_audit_event(
        db,
        action="device_blocked",
        actor_type=actor_type,
        user_id=row.user_id,
        resource_type="user_device",
        resource_id=str(device_id),
        metadata={"reason": reason, "fingerprint": row.fingerprint_hash[:16] + "..."},
    )
    await db.commit()
    await db.refresh(row)
    return row
