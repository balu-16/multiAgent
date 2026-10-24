import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash

from app.errors import DependencyUnavailable
from app.schemas.events import utcnow


@dataclass
class AuthContext:
    user: dict
    session_id: str
    expires_at: float


class RateLimiter:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.windows = defaultdict(deque)

    def check(self, key, limit, seconds=60):
        if not self.enabled:
            return
        now = time.monotonic()
        if len(self.windows) > 10000:
            self.windows = defaultdict(deque, {k: v for k, v in self.windows.items() if v and now - v[-1] < 3600})
        window = self.windows[key]
        while window and now - window[0] >= seconds:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(429, "Too many requests. Please try again later.", headers={"Retry-After": str(seconds)})
        window.append(now)


class AuthService:
    def __init__(self, settings, repo):
        self.settings = settings
        self.repo = repo
        self.passwords = PasswordHash.recommended()
        # A fixed valid hash keeps nonexistent-user verification on the same path.
        self.dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$yA6L8qip2bS7NLIzBqIecQ$WUqF5MPYsSEVHiMtefGqFRV3B3fBZyflAUq0KDJbJ+Y"

    async def hash_password(self, password):
        return await asyncio.to_thread(self.passwords.hash, password)

    async def check_password(self, password, encoded):
        try:
            return await asyncio.to_thread(self.passwords.verify, password, encoded or self.dummy_hash)
        except Exception:
            return False

    async def issue_session(self, user):
        secret = self.settings.jwt_secret.get_secret_value()
        if len(secret.encode()) < 32:
            raise DependencyUnavailable("JWT signing is not configured")
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=self.settings.session_hours)
        session_id = str(uuid4())
        await self.repo.create_session({"id": session_id, "user_id": user["id"], "expires_at": expiry.isoformat(), "revoked_at": None})
        token = jwt.encode({
            "sub": str(user["id"]), "jti": session_id,
            "iat": int(now.timestamp()), "exp": int(expiry.timestamp()),
            "iss": "backchannel", "aud": "backchannel-web",
        }, secret, algorithm="HS256")
        return token

    async def authenticate(self, token):
        secret = self.settings.jwt_secret.get_secret_value()
        if not secret:
            raise DependencyUnavailable("JWT signing is not configured")
        try:
            claims = jwt.decode(
                token or "", secret, algorithms=["HS256"], issuer="backchannel", audience="backchannel-web",
                options={"require": ["sub", "jti", "iat", "exp", "iss", "aud"]},
            )
            user_id, session_id = str(UUID(claims["sub"])), str(UUID(claims["jti"]))
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise HTTPException(401, "Please sign in.") from None
        session = await self.repo.get_session(session_id)
        if not session or session.get("revoked_at") or str(session["user_id"]) != user_id:
            raise HTTPException(401, "Please sign in.")
        expiry = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00")).timestamp()
        if expiry <= time.time():
            raise HTTPException(401, "Please sign in.")
        user = await self.repo.get_user(user_id)
        if not user:
            raise HTTPException(401, "Please sign in.")
        return AuthContext({"id": user_id, "email": user["email"]}, session_id, min(expiry, claims["exp"]))

    async def revoke(self, context):
        await self.repo.revoke_session(context.session_id, utcnow())
