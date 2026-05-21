import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.websocket_manager import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect(manager):
    ws = AsyncMock()
    await manager.connect(ws, "test")
    assert manager.connection_count == 1


@pytest.mark.asyncio
async def test_disconnect(manager):
    ws = AsyncMock()
    await manager.connect(ws, "test")
    manager.disconnect(ws, "test")
    assert manager.connection_count == 0


@pytest.mark.asyncio
async def test_broadcast(manager):
    ws = AsyncMock()
    await manager.connect(ws, "test")
    await manager.broadcast("test", {"msg": "hello"})
    ws.send_text.assert_called_once()


@pytest.mark.asyncio
async def test_broadcast_removes_dead(manager):
    ws = AsyncMock()
    ws.send_text.side_effect = Exception("dead")
    await manager.connect(ws, "test")
    await manager.broadcast("test", {"msg": "hello"})
    assert manager.connection_count == 0
