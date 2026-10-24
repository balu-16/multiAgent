import time
import unittest
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeBrain, FakeVoice, MemoryRepository, MemoryStore, settings

ORIGIN = {"Origin": "http://localhost:3000"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.config = settings()
        self.store, self.repo = MemoryStore(), MemoryRepository()
        self.app = create_app(settings=self.config, groq=FakeBrain(), voice=FakeVoice(), store=self.store, repo=self.repo)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def register(self, email="person@example.com"):
        result = self.client.post("/api/auth/register", headers=ORIGIN,
                                  json={"email": email, "password": "a secure password"})
        self.assertEqual(result.status_code, 201, result.text)
        return result

    def test_signup_login_cookie_normalization_logout_and_revocation(self):
        result = self.register("  PERSON@example.com  ")
        self.assertEqual(result.json()["user"]["email"], "person@example.com")
        self.assertNotIn("password", result.text)
        cookie = result.headers["set-cookie"]
        for field in ("HttpOnly", "Path=/", "SameSite=lax", "Max-Age=86400"):
            self.assertIn(field, cookie)
        self.assertNotIn("Domain", cookie)
        self.assertEqual(result.headers["cache-control"], "no-store")
        token = self.client.cookies.get("bc_session")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=ORIGIN).status_code, 204)
        self.client.cookies.set("bc_session", token)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        result = self.client.post("/api/auth/login", headers=ORIGIN, json={"email": "person@example.com", "password": "a secure password"})
        self.assertEqual(result.status_code, 200)

    def test_duplicate_registration_generic_login_and_validation(self):
        self.register()
        duplicate = self.client.post("/api/auth/register", headers=ORIGIN, json={"email": "PERSON@example.com", "password": "a secure password"})
        self.assertEqual(duplicate.status_code, 409)
        errors = []
        for email in ("person@example.com", "unknown@example.com"):
            result = self.client.post("/api/auth/login", headers=ORIGIN, json={"email": email, "password": "wrong password"})
            self.assertEqual(result.status_code, 401)
            errors.append(result.json())
        self.assertEqual(errors[0], errors[1])
        bad = self.client.post("/api/auth/register", headers=ORIGIN, json={"email": "not-an-email", "password": "123"})
        self.assertEqual(bad.status_code, 422)
        self.assertNotIn('"input"', bad.text)

    def test_origin_json_cors_and_no_auth_bypass(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/api/chats").status_code, 401)
        payload = {"email": "person@example.com", "password": "a secure password"}
        self.assertEqual(self.client.post("/api/auth/register", json=payload).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/register", headers={"Origin": "https://evil.example"}, json=payload).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/register", headers=ORIGIN, data=payload).status_code, 415)
        preflight = self.client.options("/api/rooms/start", headers={**ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(preflight.headers["access-control-allow-origin"], ORIGIN["Origin"])
        self.assertEqual(preflight.headers["access-control-allow-credentials"], "true")

    def test_tampered_expired_or_mismatched_session_is_rejected(self):
        self.register()
        token = self.client.cookies.get("bc_session")
        claims = jwt.decode(token, options={"verify_signature": False})
        for updated in ({**claims, "exp": int(time.time()) - 1}, {**claims, "sub": str(uuid4())}, {**claims, "aud": "wrong"}):
            self.client.cookies.clear()
            self.client.cookies.set("bc_session", jwt.encode(updated, self.config.jwt_secret.get_secret_value(), algorithm="HS256"))
            self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.client.cookies.clear()
        self.client.cookies.set("bc_session", token[:-5] + "abcde")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_database_outage_fails_closed_with_503(self):
        self.register()
        self.repo.fail = True
        self.assertEqual(self.client.get("/api/auth/me").status_code, 503)
        self.assertEqual(self.client.get("/api/chats").status_code, 503)

    def test_authenticated_eight_message_room_websocket_archive_and_ownership(self):
        user = self.register().json()["user"]
        roster = self.client.post("/api/generate-personas", headers=ORIGIN, json={"topic": "systems", "num_agents": 3}).json()["personas"]
        started = self.client.post("/api/rooms/start", headers=ORIGIN, json={"topic": "systems", "max_messages": 8, "personas": roster})
        self.assertEqual(started.status_code, 200, started.text)
        room_id = started.json()["room_id"]
        with self.client.websocket_connect(f"/ws/rooms/{room_id}", headers=ORIGIN) as socket:
            event = socket.receive_json()
            self.assertEqual(event["type"], "history_sync")
            count, status = event["count"], event["status"]
            seq = event["last_seq"]
            while status == "running":
                event = socket.receive_json()
                self.assertGreater(event["seq"], seq)
                seq = event["seq"]
                if event["type"] == "chat_message":
                    self.assertNotIn("|||", event["text"])
                    count = event["count"]
                if event.get("reason") == "max_reached":
                    status = "completed"
            self.assertEqual(count, 8)
        deadline = time.monotonic() + 2
        while room_id not in self.repo.chats and time.monotonic() < deadline:
            time.sleep(0.01)
        archive = self.client.get(f"/api/chats/{room_id}")
        self.assertEqual(archive.status_code, 200, archive.text)
        self.assertEqual(len(archive.json()["chat"]["messages"]), 8)
        self.assertNotIn("user_id", archive.json()["chat"])
        self.assertEqual(self.repo.chats[room_id]["user_id"], user["id"])
        self.assertEqual(len(self.client.get("/api/chats").json()["chats"]), 1)
        with self.client.websocket_connect(f"/ws/rooms/{room_id}", headers=ORIGIN) as socket:
            snapshot = socket.receive_json()
            self.assertEqual(snapshot["status"], "completed")
            self.assertEqual(snapshot["typing_agent_ids"], [])
        self.register("other@example.com")
        self.assertEqual(self.client.get(f"/api/chats/{room_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/chats").json()["chats"], [])
        with self.assertRaises(Exception) as caught:
            with self.client.websocket_connect(f"/ws/rooms/{room_id}", headers=ORIGIN) as socket:
                socket.receive_json()
        self.assertEqual(getattr(caught.exception, "code", None), 4404)

    def test_logout_closes_only_that_sessions_socket(self):
        self.register()
        roster = self.client.post("/api/generate-personas", headers=ORIGIN, json={"topic": "systems", "num_agents": 2}).json()["personas"]
        room_id = self.client.post("/api/rooms/start", headers=ORIGIN, json={"topic": "systems", "max_messages": 1, "personas": roster}).json()["room_id"]
        with self.client.websocket_connect(f"/ws/rooms/{room_id}", headers=ORIGIN) as socket:
            socket.receive_json()
            self.client.post("/api/auth/logout", headers=ORIGIN)
            from starlette.websockets import WebSocketDisconnect
            with self.assertRaises(WebSocketDisconnect) as caught:
                while True:
                    socket.receive_json()
            self.assertEqual(caught.exception.code, 4401)

    def test_invalid_cap_persona_ids_and_cursor_are_rejected(self):
        self.register()
        roster = self.client.post("/api/generate-personas", headers=ORIGIN, json={"topic": "systems", "num_agents": 2}).json()["personas"]
        for cap in (0, 81, 2.5):
            self.assertEqual(self.client.post("/api/rooms/start", headers=ORIGIN, json={"topic": "systems", "max_messages": cap, "personas": roster}).status_code, 422)
        roster[1]["id"] = roster[0]["id"]
        self.assertEqual(self.client.post("/api/rooms/start", headers=ORIGIN, json={"topic": "systems", "max_messages": 8, "personas": roster}).status_code, 422)
        self.assertEqual(self.client.get("/api/chats?cursor=invalid").status_code, 400)
        self.assertEqual(self.client.get("/api/chats?limit=51").status_code, 422)

    def test_rate_limits_authentication_attempts(self):
        self.app.state.services.limiter.enabled = True
        for _ in range(10):
            self.client.post("/api/auth/login", headers=ORIGIN, json={"email": "absent@example.com", "password": "incorrect password"})
        self.assertEqual(self.client.post("/api/auth/login", headers=ORIGIN, json={"email": "absent@example.com", "password": "incorrect password"}).status_code, 429)
