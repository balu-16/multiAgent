import asyncio
import logging
import random
import time
from collections import deque
from uuid import uuid4

from app.schemas.events import utcnow

logger = logging.getLogger(__name__)


class GroupChatRoom:
    def __init__(self, room_id, user_id, request, settings, groq, voice, store, on_complete=None, rng=None):
        self.id, self.user_id = room_id, user_id
        self.topic, self.max_messages, self.personas = request.topic, request.max_messages, request.personas
        self.settings, self.groq, self.voice, self.store = settings, groq, voice, store
        self.on_complete = on_complete
        self.rng = rng or random.Random()
        self.lock = asyncio.Lock()
        self.history = deque(maxlen=30)
        self.messages = []
        self.system_events = []
        self.total_messages = 0
        self.seq = 0
        self.status = "running"
        self.archive_status = None
        self.created_at, self.ended_at = utcnow(), None
        self.online_ids = {p.id for p in self.personas}
        self.typing_ids = set()
        self.departing_ids = set()
        self.last_activity = time.monotonic()
        self.actors = {}
        self.tasks = set()
        self.subscribers = set()
        self.finalizer = None
        self.finished_monotonic = None

    @property
    def is_active(self):
        return self.status == "running"

    def next_seq(self):
        self.seq += 1
        return self.seq

    def metadata(self):
        return {
            "id": self.id, "user_id": self.user_id, "topic": self.topic,
            "personas": [p.model_dump() for p in self.personas],
            "count": self.total_messages, "max_messages": self.max_messages,
            "status": self.status, "online_agent_ids": sorted(self.online_ids),
            "typing_agent_ids": sorted(self.typing_ids), "last_seq": self.seq,
            "archive_status": self.archive_status, "system_events": self.system_events,
            "created_at": self.created_at, "ended_at": self.ended_at,
        }

    def snapshot(self):
        meta = self.metadata()
        return {"type": "history_sync", "messages": list(self.history), **{
            key: meta[key] for key in (
                "system_events", "count", "max_messages", "status", "online_agent_ids",
                "typing_agent_ids", "last_seq", "archive_status",
            )
        }}

    def _broadcast(self, event):
        for queue in tuple(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Wake the consumer with a close sentinel; do not block actors.
                self.subscribers.discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)

    async def subscribe(self):
        queue = asyncio.Queue(maxsize=512)
        async with self.lock:
            queue.put_nowait(self.snapshot())
            self.subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue):
        async with self.lock:
            self.subscribers.discard(queue)

    async def start(self):
        from app.engine.actor import FriendActor
        await self.store.save_room(self.id, self.metadata())
        for persona in self.personas:
            actor = FriendActor(persona, self)
            self.actors[persona.id] = actor
        for actor in self.actors.values():
            self.spawn(actor.run(), f"friend:{self.id}:{actor.persona.id}")
        self.spawn(self.watchdog(), f"watchdog:{self.id}")
        first = max(self.actors.values(), key=lambda a: a.persona.talkativeness)
        first.inbox.put_nowait({"_nudge": True})

    def spawn(self, coroutine, name):
        task = asyncio.create_task(coroutine, name=name)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def set_typing(self, persona, value):
        async with self.lock:
            if value and (not self.is_active or persona.id not in self.online_ids):
                return
            if (persona.id in self.typing_ids) == value:
                return
            if value:
                self.typing_ids.add(persona.id)
                self.last_activity = time.monotonic()
            else:
                self.typing_ids.discard(persona.id)
            self._broadcast({"type": "typing", "sender_id": persona.id, "sender": persona.name,
                             "is_typing": value, "seq": self.next_seq()})

    def _clear_typing(self):
        events = []
        for persona in self.personas:
            if persona.id in self.typing_ids:
                events.append({"type": "typing", "sender_id": persona.id, "sender": persona.name,
                               "is_typing": False, "seq": self.next_seq()})
        self.typing_ids.clear()
        return events

    def _system(self, text, reason, agent_id=None):
        event = {"type": "system_event", "id": f"sys_{uuid4().hex}", "text": text,
                 "reason": reason, "agent_id": agent_id, "timestamp": utcnow(), "seq": self.next_seq()}
        self.system_events.append(event)
        return event

    def archive_payload(self):
        return {
            "id": self.id, "user_id": self.user_id, "topic": self.topic,
            "personas": [p.model_dump() for p in self.personas], "messages": list(self.messages),
            "system_events": list(self.system_events), "max_messages": self.max_messages,
            "message_count": self.total_messages, "created_at": self.created_at,
            "ended_at": self.ended_at, "reason": "max_reached",
        }

    async def commit_bubble(self, persona, text, reply_to=None):
        text = text.replace("|||", "").strip()
        if not text:
            return False
        terminal = False
        try:
            async with self.lock:
                if not self.is_active or self.total_messages >= self.max_messages or persona.id not in self.online_ids:
                    return False
                self.total_messages += 1
                event = {
                    "type": "chat_message", "id": f"msg_{self.total_messages}",
                    "sender_id": persona.id, "sender": persona.name, "color": persona.color,
                    "text": text, "reply_to": reply_to, "count": self.total_messages,
                    "max_messages": self.max_messages, "timestamp": utcnow(), "seq": self.next_seq(),
                }
                self.history.append(event)
                self.messages.append(event)
                self.last_activity = time.monotonic()
                ending_events = []
                archive = None
                if self.total_messages == self.max_messages:
                    terminal = True
                    self.status, self.archive_status, self.ended_at = "completed", "pending", utcnow()
                    self.finished_monotonic = time.monotonic()
                    ending_events.extend(self._clear_typing())
                    ending_events.append(self._system("Room reached the maximum message limit.", "max_reached"))
                    ending_events.append({"type": "archive_status", "status": "pending", "seq": self.next_seq()})
                    archive = self.archive_payload()
                # Only persistence is awaited here; LLM calls never hold the room lock.
                # The final bubble and full outbox payload are one idempotent Redis write.
                await self.store.save_room(self.id, self.metadata(), message=event, archive=archive)
                actor = self.actors.get(persona.id)
                if actor:
                    actor.fatigue += 0.14
                    actor.bubbles_sent += 1
                self._broadcast(event)
                for outgoing in ending_events:
                    self._broadcast(outgoing)
                if not terminal:
                    for actor in self.actors.values():
                        if actor.persona.id != persona.id and actor.is_online:
                            actor.inbox.put_nowait(event)
            if terminal:
                self._schedule_cleanup()
                if self.on_complete:
                    self.on_complete()
            return True
        except asyncio.CancelledError:
            raise
        except Exception:
            # State may have been advanced locally before an uncertain storage failure.
            # Never announce successful completion or continue spending in that case.
            await self.fail("Room stopped because message storage is unavailable.", force=True)
            return False

    async def reserve_departure(self, actor_id):
        async with self.lock:
            if actor_id in self.departing_ids:
                return True
            if not self.is_active or len(self.online_ids - self.departing_ids) <= 2:
                return False
            self.departing_ids.add(actor_id)
            return True

    async def finish_departure(self, actor):
        async with self.lock:
            if not self.is_active:
                return
            self.online_ids.discard(actor.persona.id)
            self.departing_ids.discard(actor.persona.id)
            actor.is_online = False
            event = self._system(f"{actor.persona.name} got tired and left the chat 👋", "agent_left", actor.persona.id)
            await self.store.save_room(self.id, self.metadata())
            self._broadcast(event)

    async def mark_archived(self):
        async with self.lock:
            if self.status != "completed" or self.archive_status == "saved":
                return
            self.archive_status = "saved"
            event = {"type": "archive_status", "status": "saved", "seq": self.next_seq()}
            await self.store.save_room(self.id, self.metadata())
            self._broadcast(event)

    async def fail(self, text="Room stopped because an AI service is unavailable.", force=False):
        async with self.lock:
            if not self.is_active and not force:
                return
            self.status, self.archive_status, self.ended_at = "failed", None, utcnow()
            self.finished_monotonic = time.monotonic()
            events = self._clear_typing()
            events.append(self._system(text, "room_error"))
            try:
                await self.store.save_room(self.id, self.metadata())
            except Exception:
                logger.warning("Failed room metadata could not be persisted; room=%s", self.id)
            for event in events:
                self._broadcast(event)
        self._schedule_cleanup()

    def _schedule_cleanup(self):
        if self.finalizer is None:
            self.finalizer = asyncio.create_task(self.stop_tasks(), name=f"finalize:{self.id}")

    async def stop_tasks(self):
        tasks = [task for task in self.tasks if task is not asyncio.current_task() and not task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def watchdog(self):
        while self.is_active:
            await asyncio.sleep(self.settings.watchdog_interval)
            if self.typing_ids or time.monotonic() - self.last_activity < self.settings.silence_seconds:
                continue
            eligible = [actor for actor in self.actors.values() if actor.is_online and not actor.busy]
            if len(self.online_ids) >= 2 and eligible:
                actor = min(eligible, key=lambda candidate: candidate.fatigue)
                self.last_activity = time.monotonic()
                actor.inbox.put_nowait({"_nudge": True})

    async def aclose(self):
        if self.is_active:
            await self.fail("Room stopped because the server is shutting down.")
        await self.stop_tasks()
        if self.finalizer and self.finalizer is not asyncio.current_task():
            await asyncio.gather(self.finalizer, return_exceptions=True)


class StoredRoom:
    """Read-only completed snapshots, or failed snapshots after process restart."""

    def __init__(self, metadata, messages):
        self.user_id = metadata["user_id"]
        self.id = metadata["id"]
        self.metadata = metadata
        self.messages = messages
        if metadata["status"] == "running":
            # Never resume billing automatically after a process restart.
            self.metadata["status"] = "failed"
        self.metadata["typing_agent_ids"] = []

    async def subscribe(self):
        queue = asyncio.Queue()
        queue.put_nowait({"type": "history_sync", "messages": self.messages, **{
            key: self.metadata[key] for key in (
                "system_events", "count", "max_messages", "status", "online_agent_ids",
                "typing_agent_ids", "last_seq", "archive_status",
            )
        }})
        return queue

    async def unsubscribe(self, queue):
        pass
