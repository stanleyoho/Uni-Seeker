from typing import Protocol, runtime_checkable


@runtime_checkable
class NotificationChannel(Protocol):
    async def send(self, message: str, **kwargs: object) -> None: ...
