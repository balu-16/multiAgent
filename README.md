# Backchannel

Backchannel is a spectator-only AI group chat. Give it a topic, review the
generated group of AI personas, and watch them debate in real time. Personas
can interrupt one another, send short message bursts, show typing activity,
get tired and leave, and stop when the room reaches its message limit.

Completed conversations are saved to a private archive so users can return to
them later.

## What it includes

- **Three-step web experience:** choose a topic, customize the generated
  personas, then watch the live conversation.
- **Multi-agent actor engine:** each persona runs as an independent asyncio
  actor with fatigue, stamina, reaction triggers, and a silence watchdog.
- **Streaming conversations:** Groq decides whether a persona should react;
  Gemini streams the response, which can become multiple chat bubbles.
- **Reliable live updates:** FastAPI WebSockets provide ordered message,
  typing, system, history, and archive-status events.
- **Durable storage:** Redis holds live room state and a rolling message
  window; Supabase stores complete private transcripts.
- **Application authentication:** Argon2id password hashing, revocable
  HttpOnly JWT cookies, origin checks, rate limits, and ownership checks.
- **Reconnect-safe UI:** the client merges snapshots and live events without
  duplicating messages or regressing terminal room state.

## Architecture

```text
Next.js client
    │ REST + WebSocket
    ▼
FastAPI application
    ├── Auth and archive REST APIs
    ├── Room registry
    ├── Asyncio actor engine
    ├── Groq decision provider
    └── Gemini streaming provider
         │
         ├── Redis: live state, last 30 messages, archive outbox
         └── Supabase: users, sessions, complete archived chats
```

The backend is intentionally run with **one Uvicorn worker**. Active rooms and
their in-memory fan-out queues belong to one process. Redis is used for
persistence and recovery, not for one Pub/Sub connection per agent.

### Conversation lifecycle

1. The user authenticates with the FastAPI backend.
2. Groq generates 2–6 structured personas.
3. The user edits the persona roster and starts a room.
4. Each actor evaluates incoming messages and decides whether to speak.
5. Gemini streams one or more bubbles; the room commits each bubble under a
   lock so the message cap cannot be exceeded.
6. Actors may sign off after reaching their stamina limit, while at least two
   agents remain online.
7. At completion, the full transcript is written to a Redis outbox.
8. A retrying archive worker saves it idempotently to Supabase.

## Repository layout

```text
client/       Next.js App Router frontend and browser-facing state management
server/       FastAPI API, WebSocket endpoint, providers, and actor engine
supabase/     Database migration for users, sessions, and archived chats
scripts/      Environment setup and live, browser, and storage verification
artifacts/    Verification reports and screenshots
contracts.md  Authentication, API, event, and storage contracts
plan.md       Product behavior and implementation specification
```

## Requirements

- Node.js 22+
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Redis or Upstash Redis
- Supabase project
- Groq API key
- Gemini API key

## Configuration

Copy `.env.example` to `.env` and fill in the backend values:

```dotenv
GROQ_API_KEY=...
GEMINI_API_KEY=...
REDIS_URL=redis://localhost:6379
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
JWT_SECRET=at-least-32-random-bytes
ALLOWED_ORIGINS=http://localhost:3000
COOKIE_SECURE=false
```

Run the migration in
`supabase/migrations/202610160001_backchannel.sql` against the Supabase
project. The setup script creates `server/.env` as a link to the root
environment and writes only public API URLs to `client/.env.local`.

Never expose provider keys, the JWT secret, or the Supabase service-role key
to the client.

## Run locally

Install dependencies from the repository root:

```bash
python3 scripts/setup_env.py
npm run setup:server
npm ci
npm --prefix client ci
```

Start the backend:

```bash
cd server
source .venv/bin/activate
python main.py
```

In another terminal, start the frontend:

```bash
cd client
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Use `localhost` for both
services so browser cookies are available to the WebSocket handshake.
The backend is available at [http://localhost:8000](http://localhost:8000);
its OpenAPI documentation is at `/docs`.

Root shortcuts are also available:

```bash
npm run dev          # frontend
npm run dev:server   # backend
```

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health and active-room status |
| `POST` | `/api/auth/register` | Create an account and session |
| `POST` | `/api/auth/login` | Sign in |
| `GET` | `/api/auth/me` | Restore the current session |
| `POST` | `/api/auth/logout` | Revoke the session and close its sockets |
| `POST` | `/api/generate-personas` | Generate a structured persona roster |
| `POST` | `/api/rooms/start` | Start a spectator room |
| `GET` | `/api/chats` | List the current user's saved chats |
| `GET` | `/api/chats/{room_id}` | Read one saved chat |
| `WS` | `/ws/rooms/{room_id}` | Receive live room events |

The WebSocket is spectator-only: clients receive events but do not send chat
messages. Every event has an increasing sequence number so reconnecting
clients can merge snapshots and live updates safely.

## Testing and verification

Run the deterministic checks:

```bash
npm run test:server
npm --prefix client test
npm --prefix client run typecheck
npm run build
```

With real services configured and the backend running:

```bash
npm run check:services
npm run verify:live
npm run test:storage
```

`verify:live` uses provider quota and checks authentication, persona
generation, an eight-message live room, WebSockets, Redis, Supabase archives,
and ownership isolation. `test:storage` checks rolling-window behavior,
durable archive retries, and outage recovery.

For deterministic browser testing, use the fixture backend instead of the real
provider-backed server:

```bash
npm run test:fixture-server
npm run setup:browser
npm run test:browser
```

Reports are written to `artifacts/`, including integration, storage, browser,
verification, and persona-performance results.

## Operational notes

- Live actor tasks do not resume after a process restart; pending archives do.
- Redis retains the last 30 live messages, but completed archives contain the
  full transcript.
- Archive writes are retried and are idempotent by room ID.
- Set `COOKIE_SECURE=true` behind HTTPS and configure exact frontend origins.
- The production providers are fixed to `openai/gpt-oss-20b` and
  `gemini-2.5-flash`; clients cannot select fixture providers.

The detailed contracts live in [`contracts.md`](contracts.md), and the
behavioral specification is in [`plan.md`](plan.md).
