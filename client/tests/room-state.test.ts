import assert from "node:assert/strict";
import test from "node:test";
import { initialRoomState, missingMessageCount, roomReducer } from "../src/lib/room-state";
import type { ChatMessageEvent, HistorySync, RoomEvent } from "../src/types/chat";
import { roomEventSchema } from "../src/types/chat";

function message(count: number, seq = count): ChatMessageEvent {
  return { type: "chat_message", id: `message-${count}`, sender_id: "agent_1", sender: "Aarav", color: "#4A6B5D", text: `Message ${count}`, reply_to: null, count, max_messages: 80, timestamp: "2026-10-16T10:00:00Z", seq };
}
function snapshot(messages: ChatMessageEvent[], overrides: Partial<HistorySync> = {}): HistorySync {
  return { type: "history_sync", messages, system_events: [], count: messages.at(-1)?.count ?? 0, max_messages: 80, status: "running", online_agent_ids: ["agent_1", "agent_2"], typing_agent_ids: [], last_seq: messages.at(-1)?.seq ?? 0, archive_status: null, ...overrides };
}
function event(state: ReturnType<typeof initialRoomState>, value: RoomEvent) { return roomReducer(state, { type: "event", event: value }); }

test("history/live overlap is idempotent and retains messages older than rolling history", () => {
  let state = event(initialRoomState(), snapshot(Array.from({ length: 20 }, (_, index) => message(index + 1))));
  state = event(state, message(21));
  const overlap = snapshot(Array.from({ length: 30 }, (_, index) => message(index + 11)));
  state = event(state, overlap);
  state = event(state, overlap);
  state = event(state, message(40));
  assert.deepEqual(state.messages.map((item) => item.count), Array.from({ length: 40 }, (_, index) => index + 1));
  assert.equal(state.count, 40);
  assert.equal(state.lastSeq, 40);
});

test("counters use authoritative snapshot count rather than retained length", () => {
  const state = event(initialRoomState(), snapshot(Array.from({ length: 30 }, (_, index) => message(index + 31))));
  assert.equal(state.messages.length, 30);
  assert.equal(state.count, 60);
  assert.equal(missingMessageCount(state.messages), 30);
});

test("stale snapshot can recover messages but cannot undo terminal lifecycle", () => {
  let state = event(initialRoomState(), message(2, 5));
  state = event(state, { type: "system_event", id: "end", text: "Done", reason: "max_reached", agent_id: null, timestamp: "2026-10-16T10:00:01Z", seq: 6 });
  state = event(state, snapshot([message(1, 1)], { last_seq: 1, typing_agent_ids: ["agent_1"] }));
  assert.equal(state.status, "completed");
  assert.equal(state.count, 2);
  assert.deepEqual(state.typingIds, []);
  assert.deepEqual(state.messages.map((item) => item.count), [1, 2]);
});

test("multiple typing indicators are independent and departures clear only that agent", () => {
  let state = event(initialRoomState(), snapshot([]));
  state = event(state, { type: "typing", sender_id: "agent_1", sender: "Aarav", is_typing: true, seq: 1 });
  state = event(state, { type: "typing", sender_id: "agent_2", sender: "Meera", is_typing: true, seq: 2 });
  assert.deepEqual(state.typingIds, ["agent_1", "agent_2"]);
  state = event(state, { type: "system_event", id: "left", text: "Aarav left", reason: "agent_left", agent_id: "agent_1", timestamp: "2026-10-16T10:00:01Z", seq: 3 });
  assert.deepEqual(state.typingIds, ["agent_2"]);
  assert.deepEqual(state.onlineIds, ["agent_2"]);
  state = event(state, { type: "typing", sender_id: "agent_1", sender: "Aarav", is_typing: true, seq: 4 });
  assert.deepEqual(state.typingIds, ["agent_2"]);
  state = roomReducer(state, { type: "disconnect" });
  assert.deepEqual(state.typingIds, []);
});

test("completion/failure clear typing and obsolete events cannot regress archive state", () => {
  let state = event(initialRoomState(), snapshot([], { typing_agent_ids: ["agent_1"] }));
  state = event(state, { type: "system_event", id: "failed", text: "Provider unavailable", reason: "room_error", agent_id: null, timestamp: "2026-10-16T10:00:01Z", seq: 10 });
  assert.equal(state.status, "failed");
  assert.deepEqual(state.typingIds, []);
  state = event(state, { type: "archive_status", status: "saved", seq: 12 });
  state = event(state, { type: "archive_status", status: "pending", seq: 11 });
  assert.equal(state.archiveStatus, "saved");
});

test("untrusted socket payloads are validated before reaching state", () => {
  assert.equal(roomEventSchema.safeParse({ type: "history_sync", messages: [] }).success, false);
  assert.equal(roomEventSchema.safeParse({ ...message(1), color: "url(javascript:invalid)" }).success, false);
  assert.equal(roomEventSchema.safeParse(message(1)).success, true);
});
