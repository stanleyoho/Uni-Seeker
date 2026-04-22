from telegram import Bot


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id

    async def send(self, message: str, **kwargs: object) -> None:
        parse_mode = str(kwargs.get("parse_mode", "HTML"))
        await self._bot.send_message(chat_id=self._chat_id, text=message, parse_mode=parse_mode)
