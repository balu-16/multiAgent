from datetime import datetime, timezone
from typing import Literal, TypedDict


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ChatMessageEvent(TypedDict):
    type: Literal["chat_message"]
    id: str
    sender_id: str
    sender: str
    color: str
    text: str
    reply_to: str | None
    count: int
    max_messages: int
    timestamp: str
    seq: int


class SystemEvent(TypedDict):
    type: Literal["system_event"]
    id: str
    text: str
    reason: Literal["agent_left", "max_reached", "room_error"]
    agent_id: str | None
    timestamp: str
    seq: int
