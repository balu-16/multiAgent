import asyncio
import unittest
from uuid import uuid4

from app.engine.actor import FriendActor
from app.engine.registry import RoomRegistry
from app.engine.room import GroupChatRoom
from app.schemas.persona import StartRoomRequest
from app.services.archive import ArchiveWorker
from app.services.llm_gemini import split_bubbles
from tests.fakes import FakeBrain, FakeVoice, MemoryRepository, MemoryStore, personas, settings


def make_room(cap=8, count=4, **kwargs):
    store = kwargs.pop("store", MemoryStore())
    cfg = kwargs.pop("config", settings())
    return GroupChatRoom(str(uuid4()), str(uuid4()), StartRoomRequest(topic="How systems fail", max_messages=cap, personas=personas(count)),
                         cfg, kwargs.pop("brain", FakeBrain()), kwargs.pop("voice", FakeVoice()), store, **kwargs)


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_bubble_precedes_stream_completion_and_cross_chunk_delimiters(self):
        gate = asyncio.Event()
        async def chunks():
            yield "first|"
            yield "|"
            yield "|second"
            await gate.wait()
            yield "|||third||"
        bubbles = split_bubbles(chunks())
        self.assertEqual(await asyncio.wait_for(anext(bubbles), 0.1), "first")
        gate.set()
        self.assertEqual([bubble async for bubble in bubbles], ["second", "third"])

    async def test_simultaneous_commits_never_exceed_cap_or_emit_duplicate_terminal(self):
        room = make_room()
        queue = await room.subscribe()
        results = await asyncio.gather(*(room.commit_bubble(room.personas[i % 4], f"bubble {i}") for i in range(50)))
        self.assertEqual(sum(results), 8)
        self.assertEqual([message["count"] for message in room.messages], list(range(1, 9)))
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        live = events[1:]
        self.assertEqual([event["seq"] for event in live], sorted({event["seq"] for event in live}))
        self.assertEqual(sum(event.get("reason") == "max_reached" for event in live), 1)
        self.assertEqual(room.status, "completed")
        self.assertEqual(room.archive_status, "pending")
        self.assertEqual(len(room.store.outbox[room.id]["messages"]), 8)
        await room.aclose()

    async def test_rolling_history_is_thirty_and_archive_is_full(self):
        room = make_room(cap=35)
        for i in range(35):
            await room.commit_bubble(room.personas[i % 4], f"message {i}")
        self.assertEqual([m["count"] for m in room.store.histories[room.id]], list(range(6, 36)))
        self.assertEqual(len(room.store.outbox[room.id]["messages"]), 35)
        await room.aclose()

    async def test_real_actor_engine_streams_more_than_two_and_cleans_up(self):
        room = make_room(cap=12, count=2)
        await room.start()
        async with asyncio.timeout(2):
            while room.is_active:
                await asyncio.sleep(0.005)
        await room.aclose()
        self.assertEqual(len(room.messages), 12)
        self.assertFalse(room.typing_ids)
        self.assertTrue(all(task.done() for task in room.tasks))
        self.assertTrue(any(sum(m["sender_id"] == p.id for m in room.messages) >= 3 for p in room.personas))
        self.assertFalse(any("|||" in m["text"] for m in room.messages))

    async def test_departure_reservations_leave_two_online(self):
        room = make_room(count=6)
        reservations = await asyncio.gather(*(room.reserve_departure(p.id) for p in room.personas))
        self.assertEqual(sum(reservations), 4)
        for persona in room.personas:
            if persona.id in room.departing_ids:
                await room.finish_departure(FriendActor(persona, room))
        self.assertEqual(len(room.online_ids), 2)
        await room.aclose()

    async def test_direct_trigger_bypasses_fatigue_threshold(self):
        room = make_room(cap=1, count=2)
        actor = FriendActor(room.personas[0], room)
        room.actors[actor.persona.id] = actor
        actor.fatigue = 1000
        await actor.consider({})
        await asyncio.wait_for(actor.turn, 1)
        self.assertEqual(room.total_messages, 1)
        await room.aclose()

    async def test_provider_failure_clears_typing_and_stops_every_actor(self):
        class BrokenVoice:
            async def stream(self, *args):
                raise RuntimeError("simulated provider failure")
                yield ""
        room = make_room(voice=BrokenVoice())
        await room.start()
        async with asyncio.timeout(1):
            while room.is_active:
                await asyncio.sleep(0.005)
        await room.aclose()
        self.assertEqual(room.status, "failed")
        self.assertFalse(room.typing_ids)
        self.assertTrue(all(task.done() for task in room.tasks))

    async def test_silence_watchdog_nudges_least_fatigued_actor(self):
        room = make_room()
        room.actors = {persona.id: FriendActor(persona, room) for persona in room.personas}
        for index, actor in enumerate(room.actors.values()):
            actor.fatigue = float(index)
        room.last_activity -= 1
        task = asyncio.create_task(room.watchdog())
        await asyncio.sleep(0.015)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(room.actors[room.personas[0].id].inbox.get_nowait()["_nudge"])
        await room.aclose()

    async def test_archive_failure_is_durable_retry_is_idempotent(self):
        room = make_room(cap=2)
        for i in range(2):
            await room.commit_bubble(room.personas[0], f"bubble {i}")
        repo = MemoryRepository()
        repo.archive_fail = True
        worker = ArchiveWorker(room.store, repo, settings(), lambda room_id: room.mark_archived())
        await worker.process_once()
        self.assertIn(room.id, room.store.outbox)
        self.assertEqual(room.archive_status, "pending")
        repo.archive_fail = False
        worker.failures.clear()
        await worker.process_once()
        await worker.process_once()
        self.assertEqual(len(repo.chats), 1)
        self.assertEqual(room.archive_status, "saved")
        self.assertNotIn(room.id, room.store.outbox)
        await room.aclose()

    async def test_reconnect_snapshot_is_ordered_and_restarted_room_never_runs(self):
        room = make_room()
        await room.commit_bubble(room.personas[0], "first")
        queue = await room.subscribe()
        await room.commit_bubble(room.personas[1], "second")
        snapshot, live = queue.get_nowait(), queue.get_nowait()
        self.assertEqual(snapshot["count"], 1)
        self.assertGreater(live["seq"], snapshot["last_seq"])
        registry = RoomRegistry(room.settings, FakeBrain(), FakeVoice(), room.store)
        recovered = await registry.get(room.user_id, room.id)
        recovered_snapshot = (await recovered.subscribe()).get_nowait()
        self.assertEqual(recovered_snapshot["status"], "failed")
        self.assertFalse(registry.rooms)
        self.assertIsNone(await registry.get(str(uuid4()), room.id))
        await room.aclose()

    async def test_slow_subscriber_cannot_block_message_commit(self):
        room = make_room()
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait({"busy": True})
        room.subscribers.add(queue)
        self.assertTrue(await asyncio.wait_for(room.commit_bubble(room.personas[0], "hello"), 0.1))
        self.assertIsNone(queue.get_nowait())
        await room.aclose()
