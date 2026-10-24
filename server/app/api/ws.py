import asyncio
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.errors import DependencyUnavailable

router = APIRouter()


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str):
    services = websocket.app.state.services
    if websocket.headers.get("origin") not in services.settings.origins:
        await websocket.close(code=1008)
        return
    try:
        room_id = str(UUID(room_id))
        context = await services.auth.authenticate(websocket.cookies.get("bc_session"))
        room = await services.registry.get(context.user["id"], room_id)
    except (ValueError, HTTPException):
        await websocket.accept()
        await websocket.close(code=4401, reason="Please sign in.")
        return
    except DependencyUnavailable:
        await websocket.accept()
        await websocket.close(code=1013, reason="Service temporarily unavailable")
        return
    if room is None:
        await websocket.accept()
        await websocket.close(code=4404, reason="Room not found")
        return
    await websocket.accept()
    services.registry.sockets[context.session_id].add(websocket)
    queue = await room.subscribe()

    async def send_events():
        while True:
            event = await queue.get()
            if event is None:
                await websocket.close(code=1013, reason="Please reconnect for a current snapshot")
                return
            await asyncio.wait_for(websocket.send_json(event), timeout=5)

    async def receive_frames():
        while True:
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                return
            # Spectator transport has no application-level incoming messages.
            await websocket.close(code=1008, reason="This room is spectator only")
            return

    async def expire():
        await asyncio.sleep(max(0, context.expires_at - time.time()))
        await websocket.close(code=4401, reason="Session expired")

    tasks = [asyncio.create_task(coro) for coro in (send_events(), receive_frames(), expire())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, TimeoutError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await room.unsubscribe(queue)
        services.registry.sockets[context.session_id].discard(websocket)
        if not services.registry.sockets[context.session_id]:
            services.registry.sockets.pop(context.session_id, None)
