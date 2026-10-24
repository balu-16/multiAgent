"""Real Redis rolling history and recoverable outbox integration check."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.config import Settings
from app.services.archive import ArchiveWorker
from app.services.redis_store import RedisStore


class RecoveringArchive:
    def __init__(self):
        self.available = False
        self.rows = {}

    async def save_chat(self, payload):
        if not self.available:
            raise RuntimeError("Simulated archive outage")
        self.rows.setdefault(payload["id"], payload)


async def main():
    checks = []

    def check(name, passed, **details):
        checks.append({"name": name, "passed": bool(passed), **details})
        print(json.dumps(checks[-1]), flush=True)

    settings = Settings(redis_prefix="backchannel-qa-" + uuid4().hex, archive_poll_seconds=0.1)
    room_id = str(uuid4())
    store = RedisStore(settings)
    stamp = datetime.now(timezone.utc).isoformat()
    messages = []
    metadata = {"id": room_id, "user_id": str(uuid4()), "topic": "Storage integration", "personas": [], "count": 0, "max_messages": 35, "status": "running", "online_agent_ids": [], "typing_agent_ids": [], "last_seq": 0, "archive_status": None, "system_events": [], "created_at": stamp, "ended_at": None}
    try:
        await store.save_room(room_id, metadata)
        for count in range(1, 36):
            message = {"type": "chat_message", "id": f"msg_{count}", "sender_id": "agent_1", "sender": "Aarav", "color": "#4A6B5D", "text": f"Message {count}", "reply_to": None, "count": count, "max_messages": 35, "timestamp": stamp, "seq": count}
            messages.append(message)
            metadata = {**metadata, "count": count, "last_seq": count}
            await store.save_room(room_id, metadata, message=message)
        loaded, history = await store.load_room(room_id)
        check("real_redis_rolling_window", [message["count"] for message in history] == list(range(6, 36)))
        check("authoritative_count_after_trimming", loaded["count"] == 35)
        await store.save_room(room_id, {**metadata, "count": 1, "last_seq": 1}, message=messages[0])
        loaded, history = await store.load_room(room_id)
        check("stale_write_cannot_duplicate_history", loaded["count"] == 35 and len(history) == 30)
        archive = {"id": room_id, "user_id": metadata["user_id"], "topic": metadata["topic"], "personas": [], "messages": messages, "system_events": [], "max_messages": 35, "message_count": 35, "created_at": stamp, "ended_at": stamp, "reason": "max_reached"}
        metadata = {**metadata, "status": "completed", "last_seq": 36, "archive_status": "pending", "ended_at": stamp}
        await store.save_room(room_id, metadata, archive=archive)
        await store.aclose()

        # A new store/worker instance models process recovery using the durable outbox.
        store = RedisStore(settings)
        pending = await store.pending_archives()
        check("outbox_survives_store_restart", room_id in pending and len((await store.get_archive(room_id))["messages"]) == 35)
        repo = RecoveringArchive()
        failing_worker = ArchiveWorker(store, repo, settings)
        await failing_worker.process_once()
        check("outage_preserves_pending_transcript", room_id in await store.pending_archives() and await store.get_archive(room_id) is not None)
        repo.available = True
        restarted_worker = ArchiveWorker(store, repo, settings)
        await restarted_worker.process_once()
        await restarted_worker.process_once()
        check("recovery_archives_once", len(repo.rows) == 1 and len(repo.rows[room_id]["messages"]) == 35)
        check("acknowledged_outbox_removed", room_id not in await store.pending_archives() and await store.get_archive(room_id) is None)
        loaded, _ = await store.load_room(room_id)
        check("saved_metadata_preserves_empty_arrays", loaded["archive_status"] == "saved" and loaded["typing_agent_ids"] == [] and loaded["online_agent_ids"] == [] and loaded["system_events"] == [])
    except Exception as error:
        check("storage_pipeline_completed", False, error_type=type(error).__name__)
    finally:
        try:
            await store.execute("DEL", *store.keys(room_id))
        finally:
            await store.aclose()
    passed = all(item["passed"] for item in checks)
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts" / "storage.json").write_text(json.dumps({"kind": "real_redis_deterministic_archive", "passed": passed, "checks": checks}, indent=2) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
