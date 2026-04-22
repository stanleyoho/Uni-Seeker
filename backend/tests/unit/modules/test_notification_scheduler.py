from unittest.mock import AsyncMock, patch
from app.modules.notifier.scheduler import NotificationScheduler


async def test_schedule_post_market_tw() -> None:
    mock_channel = AsyncMock()
    scheduler = NotificationScheduler(channel=mock_channel)
    with patch.object(scheduler, "_build_post_market_message", return_value="test message"):
        await scheduler.send_post_market_summary(market="TW")
        mock_channel.send.assert_awaited_once_with("test message")


async def test_schedule_pre_market_tw() -> None:
    mock_channel = AsyncMock()
    scheduler = NotificationScheduler(channel=mock_channel)
    with patch.object(scheduler, "_build_pre_market_message", return_value="pre-market msg"):
        await scheduler.send_pre_market_summary(market="TW")
        mock_channel.send.assert_awaited_once_with("pre-market msg")


def test_dedup_same_day() -> None:
    scheduler = NotificationScheduler(channel=AsyncMock())
    key = ("price_alert", "2330.TW", "2026-04-22")
    assert scheduler.should_send(key) is True
    scheduler.mark_sent(key)
    assert scheduler.should_send(key) is False


def test_dedup_different_day() -> None:
    scheduler = NotificationScheduler(channel=AsyncMock())
    key1 = ("price_alert", "2330.TW", "2026-04-22")
    key2 = ("price_alert", "2330.TW", "2026-04-23")
    scheduler.mark_sent(key1)
    assert scheduler.should_send(key2) is True
