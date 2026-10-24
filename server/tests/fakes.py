import asyncio
import copy
from uuid import uuid4

from app.config import Settings
from app.errors import DependencyUnavailable, DuplicateEmail
from app.schemas.persona import AgentPersona, ReflexDecision
from app.services.supabase import decode_cursor, encode_cursor


def settings(**kwargs):
    options = {
        "_env_file": None, "jwt_secret": "test-signing-key-with-more-than-thirty-two-bytes",
        "allowed_origins": "http://localhost:3000", "rate_limit_enabled": False,
        "bubble_delay_scale": 0, "silence_seconds": 0.02, "watchdog_interval": 0.005,
        "archive_poll_seconds": 0.02,
    }
    options.update(kwargs)
    return Settings(**options)


def personas(n=3):
    return [AgentPersona(id=f"agent_{i}", name=f"Friend {i}", role_in_group="The curious friend",
                         vibe_and_style="casual and concise", expertise=["systems"],
                         stance_on_topic="Wants practical details", talkativeness=0.8,
                         color="#4A6B5D") for i in range(1, n + 1)]


class FakeBrain:
    async def generate_personas(self, topic, num_agents):
        return personas(num_agents)

    async def evaluate_reflex(self, persona, topic, messages):
        await asyncio.sleep(0)
        return ReflexDecision(trigger="DIRECT_QUESTION", mode="DEEP_DIVE", relevance=1,
                              reply_to=messages[-1]["id"] if messages else None)


class FakeVoice:
    def __init__(self, bubbles=7):
        self.bubbles = bubbles
        self.cancelled = 0

    async def stream(self, persona, topic, messages, mode):
        try:
            for index in range(2 if mode == "SIGN_OFF" else self.bubbles):
                yield f"{persona.name} bubble {index}|"
                await asyncio.sleep(0)
                yield "||"
        finally:
            self.cancelled += 1


class MemoryStore:
    def __init__(self):
        self.rooms = {}
        self.histories = {}
        self.outbox = {}
        self.fail = False

    async def save_room(self, room_id, metadata, message=None, archive=None):
        if self.fail:
            raise DependencyUnavailable("Simulated Redis outage")
        previous = self.rooms.get(room_id, {})
        if message and metadata["count"] > previous.get("count", 0):
            self.histories.setdefault(room_id, []).append(copy.deepcopy(message))
            self.histories[room_id] = self.histories[room_id][-30:]
        self.rooms[room_id] = copy.deepcopy(metadata)
        if archive:
            self.outbox[room_id] = copy.deepcopy(archive)

    async def load_room(self, room_id):
        if room_id not in self.rooms:
            return None
        return copy.deepcopy(self.rooms[room_id]), copy.deepcopy(self.histories.get(room_id, []))

    async def pending_archives(self):
        return list(self.outbox)

    async def get_archive(self, room_id):
        return copy.deepcopy(self.outbox.get(room_id))

    async def acknowledge_archive(self, room_id):
        self.outbox.pop(room_id, None)
        if room_id in self.rooms:
            self.rooms[room_id]["archive_status"] = "saved"


class MemoryRepository:
    def __init__(self):
        self.users, self.sessions, self.chats = {}, {}, {}
        self.fail = False
        self.archive_fail = False

    def available(self):
        if self.fail:
            raise DependencyUnavailable("Simulated database outage")

    async def create_user(self, email, password_hash):
        self.available()
        if any(user["email"] == email for user in self.users.values()):
            raise DuplicateEmail
        user = {"id": str(uuid4()), "email": email, "password_hash": password_hash}
        self.users[user["id"]] = user
        return user

    async def get_user_by_email(self, email):
        self.available()
        return next((user for user in self.users.values() if user["email"] == email), None)

    async def get_user(self, user_id):
        self.available()
        return self.users.get(user_id)

    async def create_session(self, session):
        self.available()
        self.sessions[session["id"]] = dict(session)

    async def get_session(self, session_id):
        self.available()
        return self.sessions.get(session_id)

    async def revoke_session(self, session_id, revoked_at):
        self.available()
        self.sessions[session_id]["revoked_at"] = revoked_at

    async def save_chat(self, payload):
        self.available()
        if self.archive_fail:
            raise DependencyUnavailable("Simulated archive outage")
        self.chats.setdefault(payload["id"], copy.deepcopy(payload))

    async def list_chats(self, user_id, limit=20, cursor=None):
        self.available()
        rows = sorted([chat for chat in self.chats.values() if chat["user_id"] == user_id], key=lambda row: (row["ended_at"], row["id"]), reverse=True)
        if cursor:
            ended, row_id = decode_cursor(cursor)
            rows = [row for row in rows if (row["ended_at"], row["id"]) < (ended, row_id)]
        fields = ("id", "topic", "message_count", "max_messages", "created_at", "ended_at", "reason")
        return {"chats": [{key: row[key] for key in fields} for row in rows[:limit]],
                "next_cursor": encode_cursor(rows[limit - 1]) if len(rows) > limit else None}

    async def get_chat(self, user_id, room_id):
        self.available()
        chat = self.chats.get(room_id)
        return {key: value for key, value in chat.items() if key != "user_id"} if chat and chat["user_id"] == user_id else None
