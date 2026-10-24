import asyncio
import time
from collections import defaultdict
from uuid import uuid4

from fastapi import HTTPException

from app.engine.room import GroupChatRoom, StoredRoom


class RoomRegistry:
    def __init__(self, settings, groq, voice, store):
        self.settings, self.groq, self.voice, self.store = settings, groq, voice, store
        self.rooms = {}
        self.lock = asyncio.Lock()
        self.archive = None
        self.sockets = defaultdict(set)

    async def start(self, user_id, request):
        async with self.lock:
            for room_id, room in list(self.rooms.items()):
                if room.finished_monotonic and time.monotonic() - room.finished_monotonic > self.settings.room_retention_seconds and not room.subscribers:
                    self.rooms.pop(room_id)
            if sum(room.is_active and room.user_id == user_id for room in self.rooms.values()) >= self.settings.max_active_rooms_per_user:
                raise HTTPException(429, "Finish your active rooms before starting another.")
            room_id = str(uuid4())
            room = GroupChatRoom(room_id, user_id, request, self.settings, self.groq, self.voice, self.store,
                                 on_complete=self.archive.notify if self.archive else None)
            await room.start()
            self.rooms[room_id] = room
            return room

    async def get(self, user_id, room_id):
        if room_id in self.rooms:
            room = self.rooms[room_id]
            return room if room.user_id == user_id else None
        stored = await self.store.load_room(room_id)
        if not stored or stored[0]["user_id"] != user_id:
            return None
        return StoredRoom(*stored)

    async def archived(self, room_id):
        room = self.rooms.get(room_id)
        if room:
            await room.mark_archived()

    async def close_session_sockets(self, session_id):
        sockets = list(self.sockets.pop(session_id, set()))
        await asyncio.gather(*(socket.close(code=4401, reason="Session ended") for socket in sockets), return_exceptions=True)

    async def aclose(self):
        await asyncio.gather(*(room.aclose() for room in list(self.rooms.values())), return_exceptions=True)
        for session_id in list(self.sockets):
            await self.close_session_sockets(session_id)
