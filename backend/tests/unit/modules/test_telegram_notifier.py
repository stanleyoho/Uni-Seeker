from unittest.mock import AsyncMock, patch

from app.modules.notifier.base import NotificationChannel
from app.modules.notifier.telegram import TelegramNotifier


def test_telegram_is_notification_channel() -> None:
    notifier = TelegramNotifier(bot_token="fake", chat_id="123")
    assert isinstance(notifier, NotificationChannel)


async def test_send_message() -> None:
    with patch("app.modules.notifier.telegram.Bot") as mock_bot_cls:
        mock_bot = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        notifier = TelegramNotifier(bot_token="fake", chat_id="123")
        await notifier.send("Hello World")
        mock_bot.send_message.assert_awaited_once_with(
            chat_id="123", text="Hello World", parse_mode="HTML",
        )


async def test_send_with_custom_parse_mode() -> None:
    with patch("app.modules.notifier.telegram.Bot") as mock_bot_cls:
        mock_bot = AsyncMock()
        mock_bot_cls.return_value = mock_bot
        notifier = TelegramNotifier(bot_token="fake", chat_id="123")
        await notifier.send("**bold**", parse_mode="Markdown")
        mock_bot.send_message.assert_awaited_once_with(
            chat_id="123", text="**bold**", parse_mode="Markdown",
        )
