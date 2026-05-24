"""Unit tests for telegram_sender.send_telegram_message.

We test the boundary contract — given a stubbed HTTPX response, the
function returns the right boolean and logs the right way. No real
network calls are made; we substitute a transport-level mock so the
full ``httpx.AsyncClient`` codepath (URL formation, JSON payload,
status parsing) is exercised end-to-end.
"""

from __future__ import annotations

import httpx

from app.modules.notifications.telegram_sender import send_telegram_message


def _mock_transport(handler):
    """Wrap a callable into an ``httpx.MockTransport`` for the test."""
    return httpx.MockTransport(handler)


async def test_send_message_returns_true_on_200_ok() -> None:
    """Happy path: 200 + ``{"ok": true}`` returns True."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        ok = await send_telegram_message(
            "tok-abc",
            "chat-123",
            "hello",
            client=client,
        )
    assert ok is True
    assert captured["url"] == "https://api.telegram.org/bottok-abc/sendMessage"
    assert "chat-123" in captured["body"]  # type: ignore[operator]
    assert "hello" in captured["body"]  # type: ignore[operator]


async def test_send_message_returns_false_on_429_rate_limit() -> None:
    """Telegram rate limit responses return False without raising."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests: retry after 30",
            },
        )

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        ok = await send_telegram_message("tok", "chat", "hi", client=client)
    assert ok is False


async def test_send_message_returns_false_on_invalid_token_401() -> None:
    """401 (invalid token) returns False; no exception leaks."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"ok": False, "error_code": 401, "description": "Unauthorized"}
        )

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        ok = await send_telegram_message("bad-token", "chat", "hi", client=client)
    assert ok is False


async def test_send_message_passes_html_parse_mode_by_default() -> None:
    """Parse mode HTML must hit the request payload as the field value."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.read().decode()))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        await send_telegram_message("tok", "chat", "<b>x</b>", client=client)
    assert seen.get("parse_mode") == "HTML"
    assert seen.get("disable_notification") is False
    assert seen.get("chat_id") == "chat"
    assert seen.get("text") == "<b>x</b>"


async def test_empty_token_returns_false_without_calling_telegram() -> None:
    """An empty bot_token short-circuits to False (no HTTP call)."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        ok = await send_telegram_message("", "chat", "hi", client=client)
    assert ok is False
    assert calls == 0


async def test_empty_chat_id_returns_false_without_calling_telegram() -> None:
    """Empty chat_id short-circuits (defensive — avoids a 400 round trip)."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        ok = await send_telegram_message("tok", "", "hi", client=client)
    assert ok is False
    assert calls == 0


async def test_send_message_returns_false_on_transport_error() -> None:
    """Connection / DNS / timeout failures return False (logged warning)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS resolution failed", request=request)

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        ok = await send_telegram_message("tok", "chat", "hi", client=client)
    assert ok is False


async def test_send_message_returns_false_on_ok_false_at_200() -> None:
    """200 + ``{"ok": false}`` (chat not found / parse error) returns False."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": False, "error_code": 400, "description": "chat not found"},
        )

    async with httpx.AsyncClient(transport=_mock_transport(handler)) as client:
        ok = await send_telegram_message("tok", "chat-bad", "hi", client=client)
    assert ok is False
