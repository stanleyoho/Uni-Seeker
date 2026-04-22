from app.modules.notifier.base import NotificationChannel


class NotificationScheduler:
    def __init__(self, channel: NotificationChannel) -> None:
        self._channel = channel
        self._sent: set[tuple[str, ...]] = set()

    def should_send(self, key: tuple[str, ...]) -> bool:
        return key not in self._sent

    def mark_sent(self, key: tuple[str, ...]) -> None:
        self._sent.add(key)

    async def send_post_market_summary(self, market: str) -> None:
        message = self._build_post_market_message(market)
        await self._channel.send(message)

    async def send_pre_market_summary(self, market: str) -> None:
        message = self._build_pre_market_message(market)
        await self._channel.send(message)

    def _build_post_market_message(self, market: str) -> str:
        return f"[盤後總結] {market}"

    def _build_pre_market_message(self, market: str) -> str:
        return f"[盤前摘要] {market}"
