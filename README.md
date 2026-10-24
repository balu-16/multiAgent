# Backchannel

A spectator group chat where AI friends debate a topic, send message bursts,
interrupt, and eventually sign off. Built with FastAPI, asyncio actors, Groq,
Gemini, Redis, and a warm beige Next.js interface.

Email/password accounts use application JWT cookies. Supabase stores password
hashes, revocable sessions, and each user's private completed conversations.
Authentication is implemented in FastAPI; the app does not use Supabase Auth.

## Local setup

Requires Node.js 22+, Python 3.11+, and [uv](https://docs.astral.sh/uv/).

1. Fill the root `.env` using `.env.example` as a reference. An existing `.env`
   is preserved. HTTPS Upstash URLs use `REDIS_TOKEN`; Redis TCP URLs may use
   `redis://` or `rediss://` with credentials in the connection string.
2. Prepare the environment and dependencies:

   ```bash
   python3 scripts/setup_env.py
   npm run setup:server
   npm ci
   npm --prefix client ci
   ```

3. Apply `supabase/migrations/202610160001_backchannel.sql` to your Supabase
   project once, using the Supabase CLI or connected MCP migration tool. This
   workspace's connected project has already received that migration.
4. Start the backend in one terminal from the project root:

   ```bash
   cd server
   source .venv/bin/activate
   python main.py
   ```

   Start the frontend in another terminal from the project root:

   ```bash
   cd client
   npm run dev
   ```

   The root shortcuts `npm run dev:server` and `npm run dev` also start the
   backend and frontend respectively.

Open [localhost:3000](http://localhost:3000), sign up, choose a topic, edit the
generated friend group, and start watching. Completed chats appear in your
private collection. The backend runs at [localhost:8000](http://localhost:8000)
with its OpenAPI documentation at `/docs`.

Use `localhost` consistently for both services so cookie authentication reaches
the WebSocket endpoint. The environment setup links `server/.env` to the root
file, generates a separate random JWT signing key only when absent, and writes
only public API/WebSocket URLs into `client/.env.local`.

Python dependencies are managed in `server/pyproject.toml` and `server/uv.lock`.
`npm run setup:server` runs `uv sync`, which creates the managed environment
automatically. The backend runs with `python main.py` after activation, and the
root Python helper commands use `uv run`.
Add dependencies with `uv add --project server <package>`.

## Verification

Deterministic backend tests, frontend state/contract tests, and production build:

```bash
npm run test:server
npm --prefix client test
npm --prefix client run typecheck
npm run build
```

With the real backend running and credentials configured:

```bash
npm run check:services
npm run verify:live
npm run test:storage
```

`verify:live` creates temporary accounts, measures real three-persona generation,
runs an eight-message room with real Groq/Gemini calls, checks WebSockets,
authentication, ownership, Redis, and Supabase archives, then cleans up its test
records. This command uses provider quota. `test:storage` verifies a 35-message
rolling window and archive-outage recovery against isolated real Redis keys.

For browser checks, stop the real backend and run the dedicated deterministic
fixture backend on port 8000. Keep the frontend running on port 3000:

```bash
npm run test:fixture-server
```

Then, in another terminal:

```bash
npm run setup:browser
npm run test:browser
```

The browser harness refuses to run against the production backend. It exercises
signup, cookie restoration, editable personas, live HTTP/WebSocket transport,
reconnection, message caps, private archives, logout, and mobile layouts without
provider requests. Browser binaries are kept under `/tmp/backchannel-playwright`.

Reports are written to `artifacts/integration.json`, `artifacts/storage.json`,
and `artifacts/browser.json`; browser screenshots are in `artifacts/screenshots/`.
Real-service results and deterministic results are reported separately.
`artifacts/verification.json` summarizes the implementation verification, and
`artifacts/persona-performance.json` records the focused latency follow-up.
The real-service report keeps performance misses even when `functional_passed`
is true; provider response times can vary around the two-second target.

## Architecture and operation

- `plan.md` contains the product and actor behavior specification;
  `contracts.md` locks authentication, events, archive APIs, and storage fields.
- `server/app` separates schemas, provider/storage services, actor engine, and
  REST/WebSocket endpoints. Run **one Uvicorn worker**, because live rooms and
  fan-out queues belong to one process.
- Redis uses one shared transport and no per-agent Pub/Sub connections. It stores
  the last 30 live messages and metadata; completed transcripts remain in a
  durable outbox until Supabase acknowledges an idempotent save.
- Live actor tasks do not resume after a process restart. Pending archive saves
  are recovered automatically; saved conversations remain available in Supabase.
- JWT cookies expire after 24 hours. Logout revokes the current session and
  closes its sockets. Provider and Supabase service keys stay in the backend.
- Set `COOKIE_SECURE=true` when serving over HTTPS and set `ALLOWED_ORIGINS`
  to the exact frontend origin. The supplied localhost defaults are for local use.
- Provider IDs are the exact models in `plan.md`: `openai/gpt-oss-20b` and
  `gemini-2.5-flash`. Provider failures are surfaced; the application does not
  silently replace models or select fixture providers.
