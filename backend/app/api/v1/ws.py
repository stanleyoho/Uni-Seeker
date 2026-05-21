from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    channel = ws.query_params.get("channel", "general")
    await ws_manager.connect(ws, channel)
    try:
        while True:
            data = await ws.receive_text()
            # Echo or handle client messages
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, channel)


@router.websocket("/ws/notifications")
async def notification_ws(ws: WebSocket) -> None:
    await ws_manager.connect(ws, "notifications")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws, "notifications")
