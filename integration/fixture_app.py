"""Deterministic backend for full browser transport tests, with no provider calls.

Run from the root with the test:fixture-server script. Production app.main does
not import this module and exposes no switch for selecting these dependencies.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4
import asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.config import Settings
from app.errors import DuplicateEmail
from app.main import create_app
from app.schemas.persona import AgentPersona, ReflexDecision


class FixtureRepository:
    def __init__(self):
        self.users = {}
        self.sessions = {}
        self.chats = {}

    async def create_user(self, email, password_hash):
        if any(user["email"] == email for user in self.users.values()):
            raise DuplicateEmail()
        user = {"id": str(uuid4()), "email": email, "password_hash": password_hash}
        self.users[user["id"]] = user
        return deepcopy(user)

    async def get_user_by_email(self, email):
        return next((deepcopy(user) for user in self.users.values() if user["email"] == email), None)

    async def get_user(self, user_id):
        return deepcopy(self.users.get(user_id))

    async def create_session(self, session):
        self.sessions[session["id"]] = deepcopy(session)

    async def get_session(self, session_id):
        return deepcopy(self.sessions.get(session_id))

    async def revoke_session(self, session_id, revoked_at):
        self.sessions[session_id]["revoked_at"] = revoked_at

    async def save_chat(self, payload):
        self.chats.setdefault(payload["id"], deepcopy(payload))

    async def list_chats(self, user_id, limit=20, cursor=None):
        from app.services.supabase import decode_cursor, encode_cursor
        chats = sorted((deepcopy(row) for row in self.chats.values() if row["user_id"] == user_id), key=lambda row: (row["ended_at"], row["id"]), reverse=True)
        if cursor:
            cutoff = decode_cursor(cursor)
            chats = [row for row in chats if (row["ended_at"], row["id"]) < cutoff]
        fields = ["id", "topic", "message_count", "max_messages", "created_at", "ended_at", "reason"]
        return {"chats": [{field: row[field] for field in fields} for row in chats[:limit]], "next_cursor": encode_cursor(chats[limit - 1]) if len(chats) > limit else None}

    async def get_chat(self, user_id, room_id):
        chat = self.chats.get(room_id)
        if not chat or chat["user_id"] != user_id:
            return None
        return {key: deepcopy(value) for key, value in chat.items() if key != "user_id"}

    async def aclose(self):
        pass


class FixtureStore:
    def __init__(self):
        self.rooms = {}
        self.outbox = {}

    async def ping(self):
        return "PONG"

    async def save_room(self, room_id, metadata, message=None, archive=None):
        previous = self.rooms.get(room_id)
        if previous and previous[0]["last_seq"] > metadata["last_seq"]:
            return
        messages = deepcopy(previous[1]) if previous else []
        if message and (not previous or metadata["count"] > previous[0]["count"]):
            messages.append(deepcopy(message))
        self.rooms[room_id] = deepcopy(metadata), messages[-30:]
        if archive:
            self.outbox[room_id] = deepcopy(archive)

    async def load_room(self, room_id):
        return deepcopy(self.rooms.get(room_id))

    async def pending_archives(self):
        return list(self.outbox)

    async def get_archive(self, room_id):
        return deepcopy(self.outbox.get(room_id))

    async def acknowledge_archive(self, room_id):
        self.outbox.pop(room_id, None)
        if room_id in self.rooms:
            self.rooms[room_id][0]["archive_status"] = "saved"

    async def aclose(self):
        pass


class FixtureBrain:
    async def generate_personas(self, topic, num_agents):
        names = ["Aarav", "Meera", "Kabir", "Isha", "Riya", "Dev"]
        colors = ["#4A6B5D", "#B57C3C", "#A84A3B", "#6E536B", "#4A6274", "#8C5A3C"]
        return [AgentPersona(id=f"agent_{i + 1}", name=names[i], role_in_group="The thoughtful friend", vibe_and_style="short, playful, curious", expertise=["software", "business"], stance_on_topic="Curious and ready to debate", talkativeness=0.9, color=colors[i]) for i in range(num_agents)]

    async def evaluate_reflex(self, persona, topic, messages):
        return ReflexDecision(trigger="EXPERTISE", mode="DEEP_DIVE", relevance=1, reply_to=messages[-1]["id"] if messages else None)

    async def aclose(self):
        pass


class FixtureVoice:
    async def stream(self, persona, topic, messages, mode):
        bubbles = (["food is here, i need to run", "catch you later"] if mode == "SIGN_OFF" else [
            "okay, hear me out",
            "start with something small enough to finish",
            "a working prototype beats another group spreadsheet",
            "but someone has to actually talk to customers",
            "yes, that includes you",
            "we can build the first version this weekend",
            "and then argue about the name for a week",
        ])
        for index, bubble in enumerate(bubbles):
            await asyncio.sleep(0.05)
            # Deliberately split the separator across provider chunks.
            yield bubble + ("||" if index < len(bubbles) - 1 else "")
            if index < len(bubbles) - 1:
                yield "|"

    async def aclose(self):
        pass


app = create_app(
    settings=Settings(_env_file=None, jwt_secret="integration-only-signing-key-at-least-32-bytes",
                      silence_seconds=0.08, watchdog_interval=0.02,
                      bubble_delay_scale=0.5, archive_poll_seconds=0.1,
                      rate_limit_enabled=False),
    groq=FixtureBrain(), voice=FixtureVoice(), store=FixtureStore(), repo=FixtureRepository(),
)


@app.get("/__integration")
async def integration_marker():
    return {"fixture": True}
