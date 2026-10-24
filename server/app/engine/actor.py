import asyncio
from contextlib import aclosing

from app.services.llm_gemini import split_bubbles


class FriendActor:
    def __init__(self, persona, room):
        self.persona, self.room = persona, room
        self.inbox = asyncio.Queue()
        self.fatigue = 0.0
        self.bubbles_sent = 0
        self.stamina_limit = max(2, round(room.rng.randint(7, 14) * room.max_messages / 30))
        self.is_online = True
        self.turn = None
        self.pending = None
        self.evaluating = False

    @property
    def busy(self):
        return self.evaluating or (self.turn is not None and not self.turn.done())

    async def run(self):
        try:
            while self.is_online and self.room.is_active:
                event = await self.inbox.get()
                if event.get("type") == "chat_message":
                    self.fatigue = max(0.0, self.fatigue - 0.15)
                if self.turn is not None and not self.turn.done():
                    # Preserve a direct mention instead of replacing it with later banter.
                    if self.pending is None or self.persona.name.casefold() not in self.pending.get("text", "").casefold():
                        self.pending = event
                    continue
                if event.get("_resume"):
                    event, self.pending = self.pending, None
                    if event is None:
                        continue
                self.evaluating = True
                try:
                    await self.consider(event)
                finally:
                    self.evaluating = False
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.room.fail()

    async def consider(self, event):
        if not self.room.is_active:
            return
        async with self.room.lock:
            history = list(self.room.history)
        async with asyncio.timeout(self.room.settings.provider_timeout):
            decision = await self.room.groq.evaluate_reflex(self.persona, self.room.topic, history)
        if not self.room.is_active:
            return
        direct = decision.trigger in {"DIRECT_QUESTION", "ROASTED_OR_CALLED_OUT"}
        raw = 0.5 * self.persona.talkativeness + 0.5 * decision.relevance + self.room.rng.uniform(-0.15, 0.15)
        if direct:
            self.fatigue *= 0.2
            raw += 0.45
        if not (direct or event.get("_nudge") or raw - self.fatigue >= 0.58):
            return
        mode = decision.mode
        if direct:
            mode = "DEEP_DIVE" if decision.trigger == "DIRECT_QUESTION" else "DEFENSIVE_ROAST"
        elif mode == "SIGN_OFF":
            mode = "CASUAL_CHIME"
        if self.bubbles_sent >= self.stamina_limit and await self.room.reserve_departure(self.persona.id):
            mode = "SIGN_OFF"
        valid_ids = {message["id"] for message in self.room.messages}
        reply_to = decision.reply_to if decision.reply_to in valid_ids else None
        self.turn = self.room.spawn(self.speak(mode, reply_to), f"voice:{self.room.id}:{self.persona.id}")
        self.turn.add_done_callback(self._turn_finished)

    def _turn_finished(self, task):
        if self.pending is not None and self.is_online and self.room.is_active:
            self.inbox.put_nowait({"_resume": True})

    async def speak(self, mode, reply_to):
        completed = False
        sent = 0
        await self.room.set_typing(self.persona, True)
        try:
            async with self.room.lock:
                history = list(self.room.history)
            async with asyncio.timeout(self.room.settings.provider_timeout):
                async with aclosing(self.room.voice.stream(self.persona, self.room.topic, history, mode)) as chunks:
                    async with aclosing(split_bubbles(chunks)) as bubbles:
                        async for bubble in bubbles:
                            if not self.room.is_active:
                                break
                            if sent:
                                delay = min(1.1, max(0.35, len(bubble) * 0.014))
                                await asyncio.sleep(delay * self.room.settings.bubble_delay_scale)
                            if not await self.room.commit_bubble(self.persona, bubble, reply_to):
                                break
                            sent += 1
                            if not self.room.is_active or (mode == "SIGN_OFF" and sent >= 2):
                                break
            completed = True
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.room.fail()
        finally:
            await self.room.set_typing(self.persona, False)
            if completed and mode == "SIGN_OFF" and sent and self.room.is_active:
                try:
                    await self.room.finish_departure(self)
                except Exception:
                    await self.room.fail("Room stopped because message storage is unavailable.")
