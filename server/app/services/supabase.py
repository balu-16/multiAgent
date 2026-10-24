import base64
import json
from datetime import datetime
from uuid import UUID

import httpx

from app.errors import DependencyUnavailable, DuplicateEmail


def encode_cursor(row):
    return base64.urlsafe_b64encode(json.dumps([row["ended_at"], row["id"]]).encode()).decode().rstrip("=")


def decode_cursor(cursor):
    try:
        if len(cursor) > 512:
            raise ValueError
        ended_at, row_id = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        date = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError
        return date.isoformat(), str(UUID(row_id))
    except Exception:
        raise ValueError("Invalid archive cursor") from None


class SupabaseRepository:
    """Privileged Data API gateway. All public reads include an owner filter."""

    def __init__(self, settings, client=None):
        self.settings = settings
        key = settings.supabase_service_role_key.get_secret_value()
        self.configured = bool(settings.supabase_url and key)
        headers = {"apikey": key}
        if not key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {key}"
        self.client = client or httpx.AsyncClient(
            base_url=settings.supabase_url.rstrip("/") + "/rest/v1/" if settings.supabase_url else "https://unconfigured.invalid/",
            headers=headers, timeout=settings.storage_timeout,
        )

    async def _request(self, method, table, *, params=None, body=None, prefer=None, duplicate=False):
        if not self.configured:
            raise DependencyUnavailable("Database is not configured")
        try:
            response = await self.client.request(
                method, table, params=params, json=body,
                headers={"Prefer": prefer} if prefer else None,
            )
            if duplicate and response.status_code == 409:
                raise DuplicateEmail
            response.raise_for_status()
            return response.json() if response.content else None
        except DuplicateEmail:
            raise
        except Exception:
            raise DependencyUnavailable("Database request failed") from None

    async def create_user(self, email, password_hash):
        rows = await self._request("POST", "backchannel_users", body={"email": email, "password_hash": password_hash}, prefer="return=representation", duplicate=True)
        return rows[0]

    async def get_user_by_email(self, email):
        rows = await self._request("GET", "backchannel_users", params={"email": f"eq.{email}", "select": "id,email,password_hash", "limit": 1})
        return rows[0] if rows else None

    async def get_user(self, user_id):
        rows = await self._request("GET", "backchannel_users", params={"id": f"eq.{user_id}", "select": "id,email", "limit": 1})
        return rows[0] if rows else None

    async def create_session(self, session):
        await self._request("POST", "backchannel_sessions", body=session)

    async def get_session(self, session_id):
        rows = await self._request("GET", "backchannel_sessions", params={"id": f"eq.{session_id}", "select": "id,user_id,expires_at,revoked_at", "limit": 1})
        return rows[0] if rows else None

    async def revoke_session(self, session_id, revoked_at):
        await self._request("PATCH", "backchannel_sessions", params={"id": f"eq.{session_id}"}, body={"revoked_at": revoked_at})

    async def save_chat(self, payload):
        await self._request("POST", "backchannel_chats", params={"on_conflict": "id"}, body=payload, prefer="resolution=ignore-duplicates,return=minimal")

    async def list_chats(self, user_id, limit=20, cursor=None):
        params = {"user_id": f"eq.{user_id}", "select": "id,topic,message_count,max_messages,created_at,ended_at,reason", "order": "ended_at.desc,id.desc", "limit": limit + 1}
        if cursor:
            ended, row_id = decode_cursor(cursor)
            params["or"] = f"(ended_at.lt.{ended},and(ended_at.eq.{ended},id.lt.{row_id}))"
        rows = await self._request("GET", "backchannel_chats", params=params)
        return {"chats": rows[:limit], "next_cursor": encode_cursor(rows[limit - 1]) if len(rows) > limit else None}

    async def get_chat(self, user_id, room_id):
        rows = await self._request("GET", "backchannel_chats", params={"id": f"eq.{room_id}", "user_id": f"eq.{user_id}", "select": "id,topic,personas,messages,system_events,message_count,max_messages,created_at,ended_at,reason", "limit": 1})
        return rows[0] if rows else None

    async def aclose(self):
        await self.client.aclose()
