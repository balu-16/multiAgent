# Backchannel integration contract

This document supplements plan.md with the agreed authentication, archive, and
reconnection contract. The original persona fields and REST request shapes apply.
All JSON uses snake_case. Run one backend worker. No Supabase Auth is used.

## Environment

Root `.env` is canonical. `server/.env` links to `../.env`. Only these public
variables go in client/.env.local:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

Backend settings: GROQ_API_KEY, GEMINI_API_KEY, REDIS_URL, optional REDIS_TOKEN
(required for HTTPS), SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, JWT_SECRET,
ALLOWED_ORIGINS (comma-separated, localhost:3000 default), COOKIE_SECURE (false
locally). SUPABASE_SECRET_KEY can be supported as an alias. Never log credentials.

## Authentication

Use pwdlib Argon2id (hash/verify off the asyncio loop) and PyJWT HS256. Generate a
separate random JWT_SECRET of at least 32 bytes once. Require sub=user UUID,
jti=session UUID, iat, exp, iss=backchannel, aud=backchannel-web. Session lifetime
is 24 hours. Validate session row, user ID, expiry, and revocation on every
protected REST request and WebSocket handshake. Database outages are 503, not 401.

Cookie: bc_session, HttpOnly, Path=/, SameSite=Lax, host-only (no Domain), Secure
when configured. No token JSON, localStorage tokens, refresh endpoints, or
Supabase Auth. Auth/private responses use Cache-Control:no-store.

Every mutation and WebSocket handshake requires an exact configured Origin;
reject absent/null origins. Browser fetches use credentials:include. JSON mutation
bodies only (logout may have no body). CORS allows credentials and exact origins.

* POST /api/auth/register {email,password}: 201 {user:{id,email}}, sets cookie.
* POST /api/auth/login {email,password}: 200 {user:{id,email}}, sets cookie.
* GET /api/auth/me: 200 {user:{id,email}}, or 401.
* POST /api/auth/logout: 204, revokes current session, clears cookie, closes its sockets.

Email is trimmed/lowercased, validated, unique. Password is not trimmed; length
8..128. Login errors are generic. Use 409 for duplicate registration, 429 for
throttling. Return 404 for another user's room/chat. Close accepted sockets at
expiry with 4401; socket handlers use only the current session's ownership.

## Original REST APIs

Both require authentication:
* POST /api/generate-personas {topic,num_agents}: {personas:AgentPersona[]}.
* POST /api/rooms/start {topic,max_messages,personas}: {room_id,status:"started"}.

num_agents/personas length 2..6, API max_messages 1..80 (8 is used in integration
tests); UI cap remains 10..80, default30. Persona IDs must remain stable. Validate
talkativeness 0..1, colors, nonempty text, and unique persona IDs. Errors follow
FastAPI's {detail:...} convention. GET /health is unauthenticated and unbilled.

## WebSocket /ws/rooms/{room_id}

Client uses the session cookie; browser auto-attaches it. Server verifies owner
and Origin. A subscriber queue is registered and its snapshot enqueued under the
room lock before live events. Spectators cannot send chat messages.

Live events have strictly increasing integer seq per room; timestamps are UTC
ISO8601. Event IDs and sender IDs are stable. Chat counts start at1.

```
chat_message = {
  type:"chat_message", id:string, sender_id:string, sender:string, color:string,
  text:string, reply_to:string|null, count:number, max_messages:number,
  timestamp:string, seq:number
}
typing = {type:"typing",sender_id:string,sender:string,is_typing:boolean,seq:number}
system_event = {
  type:"system_event",id:string,text:string,
  reason:"agent_left"|"max_reached"|"room_error",agent_id:string|null,
  timestamp:string,seq:number
}
archive_status = {type:"archive_status",status:"pending"|"saved",seq:number}
history_sync = {
  type:"history_sync",messages:chat_message[],system_events:system_event[],
  count:number,max_messages:number,status:"running"|"completed"|"failed",
  online_agent_ids:string[],typing_agent_ids:string[],last_seq:number,
  archive_status:null|"pending"|"saved"
}
```

Snapshot messages contain last30, system_events contain the durable room system
timeline. Merge by ID and sort seq; retain already received older messages.
Counter is authoritative count, not retained list length. Clear typing on
completion/disconnect, stop terminal reconnects. Never expose literal ||| in a
bubble. Archive status does not restart a completed room.

## Supabase schema (lead integrator owns migration)

Tables are public.backchannel_users, backchannel_sessions, backchannel_chats.
RLS enabled; revoke anon/authenticated access and explicitly grant service_role.
Do not pass custom app JWTs to Supabase. FastAPI enforces owner filters.

* users: id UUID PK default gen_random_uuid(), email TEXT UNIQUE normalized,
  password_hash TEXT, created_at TIMESTAMPTZ default now().
* sessions: id UUID PK (=jti), user_id UUID FK users ON DELETE CASCADE,
  expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ nullable,
  created_at TIMESTAMPTZ default now().
* chats: id UUID PK (=room_id), user_id UUID FK users ON DELETE CASCADE,
  topic TEXT, personas JSONB, messages JSONB, system_events JSONB,
  max_messages INT, message_count INT, created_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ, reason TEXT (max_reached).
  Index(user_id,ended_at DESC,id DESC). All chat fields nonnull.

Use a shared async httpx Data API gateway with service-role headers; do not block
the loop with a synchronous Supabase SDK. Use parameterized/encoded filter params.

At normal room completion atomically persist the complete immutable archive
payload in Redis outbox plus pending identifier before terminal broadcast.
Archive worker idempotently upserts chats on id; retries with backoff and startup
recovery. Pending outbox has no TTL until acknowledged. Redis live state keeps
last30 plus room metadata. Preserve owner ID in all stored records. An archive
failure remains pending and cannot restart actors or report success.

GET /api/chats?cursor=<opaque>&limit=20 (limit 1..50):
{chats:[{id,topic,message_count,max_messages,created_at,ended_at,reason}],next_cursor:string|null}.
Newest ended_at then id first; cursor is an opaque encoded ended_at/id pair.

GET /api/chats/{room_id}:
{chat:{id,topic,personas,messages,system_events,message_count,max_messages,created_at,ended_at,reason}}.
Exclude user_id from responses. Archive view has no WebSocket or LLM calls.

## Behavioral decisions

Keep all mechanics/constants in plan.md. Normal urge: raw = 0.5*talkativeness +
0.5*relevance + uniform(-0.15,0.15); urge=raw-fatigue, threshold0.58. Direct
questions/callouts apply the specified fatigue*=0.2/raw+=0.45 AND bypass threshold.
Scale stamina max(2,round(randint(7,14)*max_messages/30)). Reserve departures under
lock so two remain. Do not wait on providers under the room lock. Every bubble
commit checks remaining capacity; completion is exactly once and actor cleanup
cannot await itself. Provider calls have bounded deadlines, typing is cleared in
finally, slow spectator queues cannot block actors, and clients cannot select
mock providers in production. Tests inject providers/stores through app factory.

