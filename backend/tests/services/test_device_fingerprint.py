"""Plan 4.5 T4 — compute_fingerprint unit tests."""

from types import SimpleNamespace

import pytest

from app.services.device import compute_fingerprint


def _req(ua: str = "Mozilla/5.0", al: str = "zh-TW", ip: str = "1.2.3.4"):
    """Build a minimal FastAPI-like Request stub for hashing."""
    return SimpleNamespace(
        headers={"user-agent": ua, "accept-language": al},
        client=SimpleNamespace(host=ip),
    )


def test_returns_sha256_hex():
    fp = compute_fingerprint(_req())
    assert isinstance(fp, str)
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


def test_ipv4_same_24_block_same_fp():
    fp1 = compute_fingerprint(_req(ip="1.2.3.4"))
    fp2 = compute_fingerprint(_req(ip="1.2.3.99"))
    assert fp1 == fp2  # /24 prefix collapses last octet


def test_ipv4_different_24_block_differs():
    fp1 = compute_fingerprint(_req(ip="1.2.3.4"))
    fp2 = compute_fingerprint(_req(ip="1.2.4.4"))
    assert fp1 != fp2


def test_ipv6_collapses_to_4_hexlets():
    fp1 = compute_fingerprint(_req(ip="2001:0db8:85a3:0000:0000:0000:0000:0001"))
    fp2 = compute_fingerprint(_req(ip="2001:0db8:85a3:0000:ffff:ffff:ffff:ffff"))
    assert fp1 == fp2


def test_ipv6_different_prefix_differs():
    fp1 = compute_fingerprint(_req(ip="2001:0db8:85a3:0000::1"))
    fp2 = compute_fingerprint(_req(ip="2001:0db8:85a3:1111::1"))
    assert fp1 != fp2


def test_different_user_agent_differs():
    fp1 = compute_fingerprint(_req(ua="Mozilla/5.0"))
    fp2 = compute_fingerprint(_req(ua="Chrome/123"))
    assert fp1 != fp2


def test_different_accept_language_differs():
    fp1 = compute_fingerprint(_req(al="zh-TW"))
    fp2 = compute_fingerprint(_req(al="en-US"))
    assert fp1 != fp2


def test_no_client_yields_stable_hash():
    req = SimpleNamespace(
        headers={"user-agent": "UA", "accept-language": "zh-TW"},
        client=None,
    )
    fp = compute_fingerprint(req)
    assert len(fp) == 64
    # Calling again with same headers + no client should be identical
    fp2 = compute_fingerprint(req)
    assert fp == fp2


def test_missing_headers_handled():
    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"))
    fp = compute_fingerprint(req)
    assert len(fp) == 64
