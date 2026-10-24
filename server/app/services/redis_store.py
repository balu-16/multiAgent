import json

import httpx

from app.errors import DependencyUnavailable


SAVE_LUA = """
local previous = redis.call('GET', KEYS[1])
local incoming = cjson.decode(ARGV[1])
local old = previous and cjson.decode(previous) or {count=0,last_seq=-1}
if incoming.last_seq < old.last_seq then return 0 end
if ARGV[2] ~= '' and incoming.count > old.count then
  redis.call('RPUSH', KEYS[2], ARGV[2])
  redis.call('LTRIM', KEYS[2], -30, -1)
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', 86400)
if redis.call('EXISTS', KEYS[2]) == 1 then redis.call('EXPIRE', KEYS[2], 86400) end
if ARGV[3] ~= '' then
  redis.call('SET', KEYS[3], ARGV[3])
  redis.call('SADD', KEYS[4], ARGV[4])
end
return 1
"""

ACK_LUA = """
local metadata = redis.call('GET', KEYS[1]) or ''
if metadata ~= ARGV[1] then return 0 end
if ARGV[2] ~= '' then
  redis.call('SET', KEYS[1], ARGV[2], 'EX', 86400)
end
redis.call('DEL', KEYS[2])
redis.call('SREM', KEYS[3], ARGV[3])
return 1
"""


class RedisStore:
    """One process-wide transport; actors never open Redis subscriptions."""

    def __init__(self, settings, client=None):
        self.settings = settings
        self.prefix = settings.redis_prefix
        self.scheme = settings.redis_scheme
        self.redis = None
        self.http = client
        if self.scheme == "https" and self.http is None:
            self.http = httpx.AsyncClient(
                base_url=settings.redis_url.get_secret_value().rstrip("/"),
                headers={"Authorization": "Bearer " + settings.redis_token.get_secret_value()},
                timeout=settings.storage_timeout,
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            )

    def keys(self, room_id):
        return (
            f"{self.prefix}:room:{room_id}:meta", f"{self.prefix}:room:{room_id}:history",
            f"{self.prefix}:outbox:{room_id}", f"{self.prefix}:outbox:pending",
        )

    async def execute(self, *command):
        try:
            if self.scheme == "https":
                if not self.settings.redis_token.get_secret_value():
                    raise DependencyUnavailable("REDIS_TOKEN is required for HTTPS Redis")
                response = await self.http.post("/", json=list(command))
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    raise DependencyUnavailable("Redis command failed")
                return data["result"]
            if self.scheme in {"redis", "rediss"}:
                if self.redis is None:
                    from redis.asyncio import Redis
                    self.redis = Redis.from_url(
                        self.settings.redis_url.get_secret_value(), decode_responses=True,
                        max_connections=8, socket_timeout=self.settings.storage_timeout,
                        socket_connect_timeout=self.settings.storage_timeout,
                    )
                return await self.redis.execute_command(*command)
            raise DependencyUnavailable("Redis URL must use https, redis or rediss")
        except DependencyUnavailable:
            raise
        except Exception:
            raise DependencyUnavailable("Redis request failed") from None

    async def ping(self):
        return await self.execute("PING")

    async def save_room(self, room_id, metadata, message=None, archive=None):
        await self.execute(
            "EVAL", SAVE_LUA, 4, *self.keys(room_id),
            json.dumps(metadata, separators=(",", ":")),
            json.dumps(message, separators=(",", ":")) if message else "",
            json.dumps(archive, separators=(",", ":")) if archive else "", room_id,
        )

    async def load_room(self, room_id):
        meta_key, history_key, _, _ = self.keys(room_id)
        metadata = await self.execute("GET", meta_key)
        if not metadata:
            return None
        history = await self.execute("LRANGE", history_key, 0, -1)
        return json.loads(metadata), [json.loads(message) for message in history]

    async def pending_archives(self):
        return await self.execute("SMEMBERS", f"{self.prefix}:outbox:pending")

    async def get_archive(self, room_id):
        raw = await self.execute("GET", f"{self.prefix}:outbox:{room_id}")
        return json.loads(raw) if raw else None

    async def acknowledge_archive(self, room_id):
        meta, _, outbox, pending = self.keys(room_id)
        for _ in range(3):
            previous = await self.execute("GET", meta)
            updated = ""
            if previous:
                metadata = json.loads(previous)
                metadata["archive_status"] = "saved"
                updated = json.dumps(metadata, separators=(",", ":"))
            # Lua never decodes/re-encodes JSON: empty Python arrays stay arrays.
            if await self.execute("EVAL", ACK_LUA, 3, meta, outbox, pending,
                                  previous or "", updated, room_id):
                return
        raise DependencyUnavailable("Room metadata changed during archive acknowledgment")

    async def aclose(self):
        if self.http:
            await self.http.aclose()
        if self.redis:
            await self.redis.aclose()
