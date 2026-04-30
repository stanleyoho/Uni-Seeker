from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections. Fully independent module."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}  # channel -> connections

    async def connect(self, ws: WebSocket, channel: str = "general") -> None:
        await ws.accept()
        self._connections.setdefault(channel, set()).add(ws)
        logger.info(
            "ws_connected",
            extra={
                "channel": channel,
                "total": len(self._connections.get(channel, set())),
            },
        )

    def disconnect(self, ws: WebSocket, channel: str = "general") -> None:
        if channel in self._connections:
            self._connections[channel].discard(ws)

    async def broadcast(self, channel: str, data: dict) -> None:
        """Broadcast message to all connections in a channel."""
        if channel not in self._connections:
            return
        message = json.dumps(data, default=str)
        dead: list[WebSocket] = []
        for ws in self._connections[channel]:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[channel].discard(ws)

    @property
    def connection_count(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


# Singleton instance
ws_manager = ConnectionManager()
