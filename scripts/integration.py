"""Real-service Phase 4 checks. Run with both servers up: npm run verify:live.

Uses temporary application accounts and real provider requests. Reports contain
no passwords/tokens. Deterministic engine/browser checks are separate.
"""
import asyncio
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sys
import time

import httpx
import websockets

from preflight import read_env

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:3000"
API = "http://localhost:8000"


class PersonaCheckComplete(Exception):
    pass


async def cleanup_temporary_accounts():
    """Remove only accounts with the exact random email pattern used by this script."""
    env = read_env()
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SECRET_KEY")
    async with httpx.AsyncClient(base_url=env["SUPABASE_URL"].rstrip("/") + "/rest/v1/", headers={"apikey": key, "Authorization": "Bearer " + key}, timeout=15) as client:
        response = await client.get("backchannel_users", params={"select": "id,email", "email": "like.backchannel-qa-%@example.com"})
        response.raise_for_status()
        rows = [row for row in response.json() if re.fullmatch(r"backchannel-qa-[0-9a-f]{12}-[01]@example\.com", row["email"])]
        for row in rows:
            response = await client.delete("backchannel_users", params={"id": "eq." + row["id"]})
            response.raise_for_status()
    print(json.dumps({"temporary_accounts_removed": len(rows)}), flush=True)
    return 0


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=API)
    parser.add_argument("--personas-only", action="store_true")
    parser.add_argument("--cleanup-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.cleanup_only:
        return await cleanup_temporary_accounts()
    api_url = arguments.api_url.rstrip("/")
    ws_url = api_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    checks = []
    users = []
    room_id = None
    completed = False
    stopped = False
    env = read_env()
    suffix = secrets.token_hex(6)
    password = secrets.token_urlsafe(24)

    def check(name, passed, **details):
        item = {"name": name, "passed": bool(passed), **details}
        checks.append(item)
        print(json.dumps(item), flush=True)
        return bool(passed)

    async with httpx.AsyncClient(base_url=api_url, headers={"Origin": ORIGIN}, timeout=30) as client, httpx.AsyncClient(base_url=api_url, headers={"Origin": ORIGIN}, timeout=30) as other:
        try:
            response = await client.get("/health")
            check("health", response.status_code == 200)
            response = await client.get("/api/auth/me")
            check("unauthenticated_request_rejected", response.status_code == 401)
            preflight = await client.options("/api/rooms/start", headers={"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
            check("credentialed_cors", preflight.status_code == 200 and preflight.headers.get("access-control-allow-origin") == ORIGIN and preflight.headers.get("access-control-allow-credentials") == "true")
            for index, current in enumerate([client] if arguments.personas_only else [client, other]):
                email = f"backchannel-qa-{suffix}-{index}@example.com"
                response = await current.post("/api/auth/register", json={"email": email, "password": password})
                if not check(f"register_user_{index + 1}", response.status_code == 201, http_status=response.status_code):
                    raise RuntimeError("registration_failed")
                users.append(response.json()["user"]["id"])
                cookie = response.headers.get("set-cookie", "").lower()
                check(f"private_cookie_{index + 1}", "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie)
            response = await client.post("/api/auth/login", json={"email": f"backchannel-qa-{suffix}-0@example.com", "password": "incorrect-password"})
            check("invalid_password_rejected", response.status_code == 401)
            response = await client.post("/api/auth/login", json={"email": f"backchannel-qa-{suffix}-0@example.com", "password": password})
            check("login", response.status_code == 200)
            response = await client.get("/api/auth/me")
            check("session_restoration", response.status_code == 200 and response.json().get("user", {}).get("id") == users[0])
            async with httpx.AsyncClient(base_url=api_url, timeout=15) as untrusted:
                response = await untrusted.post("/api/auth/login", json={"email": "nobody@example.com", "password": password})
                check("missing_origin_rejected", response.status_code == 403)
                response = await untrusted.get("/api/auth/me", cookies={"bc_session": "tampered.invalid.jwt"})
                check("tampered_jwt_rejected", response.status_code == 401)

            started = time.perf_counter()
            response = await client.post("/api/generate-personas", json={"topic": "Should friends build a small software business or join a large company?", "num_agents": 3})
            latency = time.perf_counter() - started
            if not check("real_groq_persona_generation", response.status_code == 200, http_status=response.status_code, seconds=round(latency, 3)):
                raise RuntimeError("real_persona_generation_failed")
            personas = response.json().get("personas", [])
            required = {"id", "name", "role_in_group", "vibe_and_style", "expertise", "stance_on_topic", "talkativeness", "color"}
            valid = len(personas) == 3 and len({p.get("id") for p in personas}) == 3 and all(required <= p.keys() and isinstance(p["expertise"], list) and 0 <= p["talkativeness"] <= 1 and re.fullmatch(r"#[0-9A-Fa-f]{6}", p["color"]) for p in personas)
            check("persona_contract", valid)
            check("persona_under_two_seconds", latency < 2, seconds=round(latency, 3))
            if arguments.personas_only:
                raise PersonaCheckComplete
            response = await client.post("/api/rooms/start", json={"topic": "Should friends build a small software business or join a large company?", "max_messages": 8, "personas": personas})
            if not check("start_eight_message_room", response.status_code == 200 and response.json().get("status") == "started", http_status=response.status_code):
                raise RuntimeError("room_start_failed")
            room_id = response.json()["room_id"]
            private = ROOT / "artifacts" / "private"
            private.mkdir(parents=True, exist_ok=True)
            probe = private / "last-room.json"
            probe.write_text(json.dumps({"room_id": room_id, "topic": "Should friends build a small software business or join a large company?", "personas": personas}, indent=2))
            probe.chmod(0o600)
            messages = {}
            system_events = {}
            typing_on = set()
            typing_off = set()
            snapshot_seen = False
            sequences = []
            token = client.cookies.get("bc_session")
            async with websockets.connect(f"{ws_url}/ws/rooms/{room_id}", origin=ORIGIN, additional_headers={"Cookie": f"bc_session={token}"}, open_timeout=15) as socket:
                deadline = time.monotonic() + 150
                while time.monotonic() < deadline:
                    event = json.loads(await asyncio.wait_for(socket.recv(), timeout=max(0.1, deadline - time.monotonic())))
                    kind = event.get("type")
                    if not snapshot_seen:
                        check("websocket_snapshot_first", kind == "history_sync")
                    if kind == "history_sync":
                        snapshot_seen = True
                        messages.update({message["id"]: message for message in event["messages"]})
                        system_events.update({item["id"]: item for item in event.get("system_events", [])})
                        completed = event.get("status") == "completed"
                        stopped = event.get("status") in ("completed", "failed")
                        if event.get("status") == "failed":
                            check("room_has_no_provider_error", False, reason="Room was already failed in its connection snapshot")
                            break
                    else:
                        if "seq" in event:
                            sequences.append(event["seq"])
                        if kind == "chat_message":
                            messages[event["id"]] = event
                        elif kind == "typing":
                            (typing_on if event["is_typing"] else typing_off).add(event["sender_id"])
                        elif kind == "system_event":
                            system_events[event["id"]] = event
                            if event["reason"] == "max_reached":
                                completed = True
                                stopped = True
                            elif event["reason"] == "room_error":
                                stopped = True
                                check("room_has_no_provider_error", False, reason=event["text"])
                                break
                    if completed:
                        break
            ordered = sorted(messages.values(), key=lambda item: item["count"])
            check("exact_message_cap", completed and [m["count"] for m in ordered] == list(range(1, 9)), count=len(ordered))
            check("clean_bubble_delimiters", bool(ordered) and all("|||" not in m["text"] and m["text"].strip() for m in ordered))
            check("typing_transitions", bool(typing_on) and typing_on <= typing_off)
            check("ordered_live_events", sequences == sorted(set(sequences)))
            check("one_terminal_event", sum(e["reason"] == "max_reached" for e in system_events.values()) == 1)
            async with websockets.connect(f"{ws_url}/ws/rooms/{room_id}", origin=ORIGIN, additional_headers={"Cookie": f"bc_session={token}"}) as socket:
                snapshot = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
                check("completed_room_reconnect", snapshot.get("type") == "history_sync" and snapshot.get("status") == "completed" and snapshot.get("count") == 8 and snapshot.get("typing_agent_ids") == [])

            if env["REDIS_URL"].startswith("https://"):
                async with httpx.AsyncClient(base_url=env["REDIS_URL"].rstrip("/"), headers={"Authorization": "Bearer " + env["REDIS_TOKEN"]}, timeout=15) as redis:
                    key = env.get("REDIS_PREFIX", "backchannel") + f":room:{room_id}:history"
                    stored = (await redis.post("/", json=["LRANGE", key, "0", "-1"])).json().get("result", [])
                    stored_messages = [json.loads(message) for message in stored]
                    check("real_redis_message_storage", [m["count"] for m in stored_messages] == list(range(1, 9)))

            archive = None
            for _ in range(30 if completed else 0):
                response = await client.get(f"/api/chats/{room_id}")
                if response.status_code == 200:
                    archive = response.json()["chat"]
                    break
                await asyncio.sleep(0.5)
            check("supabase_full_archive", archive is not None and len(archive.get("messages", [])) == 8)
            response = await client.get("/api/chats")
            check("private_archive_listing", response.status_code == 200 and room_id in [chat["id"] for chat in response.json().get("chats", [])])
            response = await other.get(f"/api/chats/{room_id}")
            check("cross_user_archive_denied", response.status_code == 404)
            try:
                async with websockets.connect(f"{ws_url}/ws/rooms/{room_id}", origin=ORIGIN, additional_headers={"Cookie": f"bc_session={other.cookies.get('bc_session')}"}, open_timeout=10) as socket:
                    try:
                        await asyncio.wait_for(socket.recv(), timeout=2)
                        denied = False
                    except websockets.exceptions.ConnectionClosed:
                        denied = True
            except websockets.exceptions.InvalidStatus as error:
                denied = error.response.status_code in (403, 404)
            check("cross_user_socket_denied", denied)
            response = await client.post("/api/auth/logout")
            check("logout", response.status_code == 204)
            response = await client.get("/api/auth/me")
            check("logout_revokes_session", response.status_code == 401)
        except PersonaCheckComplete:
            pass
        except Exception as error:
            check("pipeline_completed", False, error_type=type(error).__name__)
        finally:
            # Remove only the accounts generated above, whose UUIDs came from signup.
            if users and (room_id is None or stopped):
                service = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SECRET_KEY")
                async with httpx.AsyncClient(base_url=env["SUPABASE_URL"], headers={"apikey": service, "Authorization": "Bearer " + service}, timeout=15) as db:
                    response = await db.delete("/rest/v1/backchannel_users", params={"id": "in.(" + ",".join(users) + ")"})
                    check("temporary_accounts_cleaned", response.status_code in (200, 204))
                if room_id and env["REDIS_URL"].startswith("https://"):
                    prefix = env.get("REDIS_PREFIX", "backchannel")
                    async with httpx.AsyncClient(base_url=env["REDIS_URL"].rstrip("/"), headers={"Authorization": "Bearer " + env["REDIS_TOKEN"]}, timeout=15) as redis:
                        await redis.post("/multi-exec", json=[["DEL", f"{prefix}:room:{room_id}:history", f"{prefix}:room:{room_id}:meta", f"{prefix}:outbox:{room_id}"], ["SREM", f"{prefix}:outbox:pending", room_id]])

    passed = all(item["passed"] for item in checks)
    report = {"kind": "real_personas" if arguments.personas_only else "real_services", "timestamp": datetime.now(timezone.utc).isoformat(), "passed": passed, "functional_passed": all(item["passed"] for item in checks if item["name"] != "persona_under_two_seconds"), "checks": checks}
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / ("persona-performance.json" if arguments.personas_only else "integration.json")).write_text(json.dumps(report, indent=2) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
