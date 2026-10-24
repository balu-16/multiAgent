import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.api.ws import router as ws_router
from app.config import Settings
from app.engine.registry import RoomRegistry
from app.errors import DependencyUnavailable, ProviderError
from app.services.archive import ArchiveWorker
from app.services.auth import AuthService, RateLimiter
from app.services.llm_gemini import GeminiVoice
from app.services.llm_groq import GroqBrain
from app.services.redis_store import RedisStore
from app.services.supabase import SupabaseRepository


def create_app(*, settings=None, groq=None, voice=None, store=None, repo=None):
    """Dependency injection is Python-only; clients cannot select fake providers."""
    settings = settings or Settings()
    groq = groq if groq is not None else GroqBrain(settings)
    voice = voice if voice is not None else GeminiVoice(settings)
    store = store if store is not None else RedisStore(settings)
    repo = repo if repo is not None else SupabaseRepository(settings)
    registry = RoomRegistry(settings, groq, voice, store)
    archive = ArchiveWorker(store, repo, settings, registry.archived)
    registry.archive = archive
    services = SimpleNamespace(settings=settings, groq=groq, voice=voice, store=store, repo=repo,
                               auth=AuthService(settings, repo), registry=registry, archive=archive,
                               limiter=RateLimiter(settings.rate_limit_enabled))

    @asynccontextmanager
    async def lifespan(app):
        archive.start()
        try:
            yield
        finally:
            await registry.aclose()
            await archive.aclose()
            for dependency in (groq, voice, store, repo):
                close = getattr(dependency, "aclose", None)
                if close:
                    await close()

    app = FastAPI(title="Backchannel", version="1.0.0", lifespan=lifespan)
    app.state.services = services

    @app.middleware("http")
    async def browser_security(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("origin") not in settings.origins:
                return JSONResponse({"detail": "Origin is not allowed."}, status_code=403, headers={"Cache-Control": "no-store"})
            has_body = request.headers.get("content-length", "0") != "0" or "transfer-encoding" in request.headers
            if (has_body or request.url.path != "/api/auth/logout") and request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                return JSONResponse({"detail": "Content-Type must be application/json."}, status_code=415, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])

    @app.exception_handler(DependencyUnavailable)
    async def dependency_error(request, exc):
        return JSONResponse({"detail": "A storage service is temporarily unavailable."}, status_code=503, headers={"Cache-Control": "no-store"})

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse({"detail": "The AI service is temporarily unavailable."}, status_code=502, headers={"Cache-Control": "no-store"})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic includes rejected inputs by default, including password fields.
        errors = [{key: value for key, value in error.items() if key in {"type", "loc", "msg"}}
                  for error in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422, headers={"Cache-Control": "no-store"})

    @app.get("/health")
    async def health():
        return {"status": "ok", "active_rooms": sum(room.is_active for room in registry.rooms.values())}

    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
