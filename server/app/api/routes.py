from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.errors import DuplicateEmail
from app.schemas.persona import Credentials, GeneratePersonasRequest, StartRoomRequest

router = APIRouter(prefix="/api")


async def current_user(request: Request):
    return await request.app.state.services.auth.authenticate(request.cookies.get("bc_session"))


def set_session(response, token, settings):
    response.set_cookie("bc_session", token, max_age=settings.session_hours * 3600,
                        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")


@router.post("/auth/register", status_code=201)
async def register(body: Credentials, request: Request, response: Response):
    services = request.app.state.services
    services.limiter.check(("register", request.client.host if request.client else "local"), 5)
    password_hash = await services.auth.hash_password(body.password)
    try:
        user = await services.repo.create_user(str(body.email), password_hash)
    except DuplicateEmail:
        raise HTTPException(409, "An account with this email already exists.") from None
    token = await services.auth.issue_session(user)
    set_session(response, token, services.settings)
    return {"user": {"id": str(user["id"]), "email": user["email"]}}


@router.post("/auth/login")
async def login(body: Credentials, request: Request, response: Response):
    services = request.app.state.services
    services.limiter.check(("login", request.client.host if request.client else "local"), 10)
    user = await services.repo.get_user_by_email(str(body.email))
    matches = await services.auth.check_password(body.password, user["password_hash"] if user else None)
    if not user or not matches:
        raise HTTPException(401, "Invalid email or password.")
    token = await services.auth.issue_session(user)
    set_session(response, token, services.settings)
    return {"user": {"id": str(user["id"]), "email": user["email"]}}


@router.get("/auth/me")
async def me(context=Depends(current_user)):
    return {"user": context.user}


@router.post("/auth/logout", status_code=204)
async def logout(request: Request):
    services = request.app.state.services
    try:
        context = await services.auth.authenticate(request.cookies.get("bc_session"))
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
    else:
        await services.auth.revoke(context)
        await services.registry.close_session_sockets(context.session_id)
    response = Response(status_code=204)
    response.delete_cookie("bc_session", path="/", httponly=True,
                           secure=services.settings.cookie_secure, samesite="lax")
    return response


@router.post("/generate-personas")
async def generate_personas(body: GeneratePersonasRequest, request: Request, context=Depends(current_user)):
    services = request.app.state.services
    services.limiter.check(("generate", context.user["id"]), 10)
    personas = await services.groq.generate_personas(body.topic, body.num_agents)
    return {"personas": [persona.model_dump() for persona in personas]}


@router.post("/rooms/start")
async def start_room(body: StartRoomRequest, request: Request, context=Depends(current_user)):
    services = request.app.state.services
    services.limiter.check(("start", context.user["id"]), 5)
    room = await services.registry.start(context.user["id"], body)
    return {"room_id": room.id, "status": "started"}


@router.get("/chats")
async def list_chats(request: Request, limit: Annotated[int, Query(ge=1, le=50)] = 20,
                     cursor: str | None = None, context=Depends(current_user)):
    try:
        return await request.app.state.services.repo.list_chats(context.user["id"], limit, cursor)
    except ValueError:
        raise HTTPException(400, "Invalid archive cursor.") from None


@router.get("/chats/{room_id}")
async def get_chat(room_id: UUID, request: Request, context=Depends(current_user)):
    chat = await request.app.state.services.repo.get_chat(context.user["id"], str(room_id))
    if not chat:
        raise HTTPException(404, "Chat not found.")
    return {"chat": chat}
