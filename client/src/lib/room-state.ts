import type { ArchiveStatus, ChatMessageEvent, RoomEvent, RoomStatus, SystemEvent } from "../types/chat";

export interface RoomState {
  messages: ChatMessageEvent[];
  systemEvents: SystemEvent[];
  count: number;
  maxMessages: number;
  status: RoomStatus;
  onlineIds: string[];
  typingIds: string[];
  lastSeq: number;
  archiveStatus: ArchiveStatus;
  hasHistory: boolean;
}

export type RoomAction = { type: "reset"; maxMessages: number; agentIds: string[] }
  | { type: "event"; event: RoomEvent }
  | { type: "disconnect" }
  | { type: "archive_saved" };

export function initialRoomState(maxMessages = 30, agentIds: string[] = []): RoomState {
  return {
    messages: [], systemEvents: [], count: 0, maxMessages, status: "running",
    onlineIds: agentIds, typingIds: [], lastSeq: -1, archiveStatus: null, hasHistory: false,
  };
}

function mergeEvents<T extends { id: string; seq: number }>(old: T[], incoming: T[]): T[] {
  const events = new Map(old.map((event) => [event.id, event]));
  for (const event of incoming) {
    const previous = events.get(event.id);
    if (!previous || event.seq >= previous.seq) events.set(event.id, event);
  }
  return [...events.values()].sort((a, b) => a.seq - b.seq);
}

export function roomReducer(state: RoomState, action: RoomAction): RoomState {
  if (action.type === "reset") return initialRoomState(action.maxMessages, action.agentIds);
  if (action.type === "disconnect") return { ...state, typingIds: [] };
  if (action.type === "archive_saved") return { ...state, archiveStatus: "saved" };
  const event = action.event;
  if (event.type === "history_sync") {
    const current = event.last_seq >= state.lastSeq;
    return {
      ...state,
      messages: mergeEvents(state.messages, event.messages),
      systemEvents: mergeEvents(state.systemEvents, event.system_events),
      count: Math.max(state.count, event.count),
      maxMessages: event.max_messages,
      status: current ? event.status : state.status,
      onlineIds: current ? event.online_agent_ids : state.onlineIds,
      typingIds: current ? (event.status === "running" ? event.typing_agent_ids : []) : state.typingIds,
      lastSeq: Math.max(state.lastSeq, event.last_seq),
      archiveStatus: current ? event.archive_status : state.archiveStatus,
      hasHistory: true,
    };
  }
  if (event.seq <= state.lastSeq) return state;
  const next = { ...state, lastSeq: event.seq };
  switch (event.type) {
    case "chat_message":
      return { ...next, messages: mergeEvents(state.messages, [event]), count: Math.max(state.count, event.count), maxMessages: event.max_messages };
    case "typing":
      return { ...next, typingIds: event.is_typing && state.status === "running" && state.onlineIds.includes(event.sender_id)
        ? [...new Set([...state.typingIds, event.sender_id])]
        : state.typingIds.filter((id) => id !== event.sender_id) };
    case "system_event":
      return {
        ...next,
        systemEvents: mergeEvents(state.systemEvents, [event]),
        status: event.reason === "max_reached" ? "completed" : event.reason === "room_error" ? "failed" : state.status,
        onlineIds: event.reason === "agent_left" ? state.onlineIds.filter((id) => id !== event.agent_id) : [],
        typingIds: event.reason === "agent_left" ? state.typingIds.filter((id) => id !== event.agent_id) : [],
      };
    case "archive_status": return { ...next, archiveStatus: event.status };
  }
}

export function missingMessageCount(messages: ChatMessageEvent[]): number {
  let count = 0;
  let previous = 0;
  for (const message of messages) {
    count += Math.max(0, message.count - previous - 1);
    previous = message.count;
  }
  return count;
}
