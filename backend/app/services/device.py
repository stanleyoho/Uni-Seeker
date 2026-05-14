"""Device fingerprinting and registry helpers — Plan 4.5 T4+T8.

T4 (this commit) provides ``compute_fingerprint(request)`` — a simple
server-side fingerprint combining UA, Accept-Language, and a
network-prefix of the client IP (so a user moving within the same /24
or /64 keeps the same device identity).

T8 will add ``block_device(...)``; do not implement here.
"""
from __future__ import annotations

import hashlib
from typing import Protocol


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
