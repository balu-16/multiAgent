import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class ArchiveWorker:
    def __init__(self, store, repo, settings, on_saved=None):
        self.store, self.repo, self.settings = store, repo, settings
        self.on_saved = on_saved
        self.wake = asyncio.Event()
        self.task = None
        self.failures = {}

    def start(self):
        self.task = asyncio.create_task(self.run(), name="archive-outbox")

    def notify(self):
        self.wake.set()

    async def process_once(self):
        pending = await self.store.pending_archives()
        for room_id in pending:
            attempt, retry_at = self.failures.get(room_id, (0, 0))
            if time.monotonic() < retry_at:
                continue
            try:
                payload = await self.store.get_archive(room_id)
                if payload is None:
                    await self.store.acknowledge_archive(room_id)
                    continue
                await self.repo.save_chat(payload)
                if self.on_saved:
                    await self.on_saved(room_id)
                await self.store.acknowledge_archive(room_id)
                self.failures.pop(room_id, None)
            except asyncio.CancelledError:
                raise
            except Exception:
                attempt += 1
                self.failures[room_id] = (attempt, time.monotonic() + min(60, 2 ** min(attempt - 1, 6)))
                logger.warning("Archive pending after storage failure; room=%s attempt=%d", room_id, attempt)

    async def run(self):
        while True:
            self.wake.clear()
            try:
                await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Archive outbox unavailable; will retry")
            delay = self.settings.archive_poll_seconds
            if self.failures:
                delay = min(delay, max(0.1, min(value[1] for value in self.failures.values()) - time.monotonic()))
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def aclose(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
