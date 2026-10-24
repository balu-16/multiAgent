# Backchannel server

From this directory, install with uv, activate the environment, and start the backend:

```sh
uv sync --locked
source .venv/bin/activate
python main.py
```

uv creates and manages `.venv` automatically. Dependencies live in
`pyproject.toml`, and `uv.lock` pins their resolved versions. Add a dependency
with `uv add <package>`; use `uv lock` after manually editing the project file.
`requirements.txt` is a generated compatibility export, not the installation
source. Refresh it with `uv export --locked --no-hashes --no-emit-project --output-file requirements.txt`.

The root `npm run setup:server` installs with uv, and `npm run dev:server` invokes
this same `main.py` entrypoint through `uv run`. To run the existing backend tests
when needed:

```sh
uv run --locked python -m unittest discover -s tests -v
```

Use one Uvicorn worker. `.env` links to the canonical root environment. Missing
external service settings are reported when the corresponding API is used;
`GET /health` never calls a model or database. Browser mutations require the
configured Origin, JSON and the HttpOnly session cookie.

`create_app(settings=..., groq=..., voice=..., store=..., repo=...)` injects test
dependencies. Services are available under `app.state.services`. Test providers
cannot be selected through configuration or public API requests.

Redis supports HTTPS plus `REDIS_TOKEN`, and redis/rediss TCP URLs. It uses one
shared transport, in-memory actor queues, last-30 message lists, and a durable
completion outbox containing the full transcript. Pending archives have no TTL;
the archive worker resumes them at startup and only acknowledges them after the
idempotent Supabase insert succeeds. Actor work never resumes after a restart.
