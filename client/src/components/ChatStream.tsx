"use client";

import { useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import { useRoomSocket } from "@/hooks/useRoomSocket";
import type { RoomState } from "@/lib/room-state";
import type { AgentPersona, ArchivedChat, ConnectionStatus } from "@/types/chat";
import { Avatar } from "./Avatar";
import { Icon } from "./Icon";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

interface ChatStreamProps {
  topic: string;
  personas: AgentPersona[];
  state: RoomState;
  archived?: boolean;
  connection: ConnectionStatus;
  error?: string | null;
  onRetry?: () => void;
  onBack: () => void;
}

export function LiveRoom({ roomId, topic, personas, maxMessages, onBack }: {
  roomId: string; topic: string; personas: AgentPersona[]; maxMessages: number; onBack: () => void;
}) {
  const { state, connection, socketError, retry } = useRoomSocket(roomId, maxMessages, personas.map((persona) => persona.id));
  return <ChatStream topic={topic} personas={personas} state={state} connection={connection} error={socketError} onRetry={retry} onBack={onBack} />;
}

export function ArchivedRoom({ chat, onBack }: { chat: ArchivedChat; onBack: () => void }) {
  const state: RoomState = {
    messages: chat.messages, systemEvents: chat.system_events, count: chat.message_count,
    maxMessages: chat.max_messages, status: "completed", onlineIds: [], typingIds: [],
    lastSeq: Math.max(0, ...chat.messages.map((message) => message.seq), ...chat.system_events.map((event) => event.seq)),
    archiveStatus: "saved", hasHistory: true,
  };
  return <ChatStream topic={chat.topic} personas={chat.personas} state={state} connection="finished" archived onBack={onBack} />;
}

export function ChatStream({ topic, personas, state, archived = false, connection, error, onRetry, onBack }: ChatStreamProps) {
  const viewport = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const previousLength = useRef(0);
  const [unread, setUnread] = useState(0);
  const timeline = useMemo(() => [...state.messages, ...state.systemEvents].sort((a, b) => a.seq - b.seq), [state.messages, state.systemEvents]);
  const messageMap = useMemo(() => new Map(state.messages.map((message) => [message.id, message])), [state.messages]);
  const active = state.status === "running";
  const connected = connection === "connected";
  const typingIds = active && connected ? state.typingIds : [];

  useEffect(() => {
    if (nearBottom.current && viewport.current) {
      viewport.current.scrollTop = viewport.current.scrollHeight;
      setUnread(0);
    } else {
      setUnread((value) => value + Math.max(0, timeline.length - previousLength.current));
    }
    previousLength.current = timeline.length;
  }, [timeline.length]);

  function scrolled(event: UIEvent<HTMLDivElement>) {
    const element = event.currentTarget;
    nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 100;
    if (nearBottom.current) setUnread(0);
  }
  function jumpToLatest() {
    nearBottom.current = true;
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    setUnread(0);
  }

  let previousMessageCount = 0;
  return <section className="live-section page-enter">
    <div className="section-title-row chat-title-row"><div><div className="eyebrow">{archived ? "ONE FOR THE ARCHIVES" : "YOU HAVE THE BEST SEAT IN THE HOUSE"}</div><h1>{archived ? <>A conversation <em>worth keeping.</em></> : <>The group chat <em>is open.</em></>}</h1></div><button className="text-button" onClick={onBack}><Icon name="back" size={17} />{active ? "Back to setup" : "Start another conversation"}</button></div>
    <div className="chat-shell">
      <aside className="chat-sidebar">
        <div className="sidebar-top"><span className="sidebar-icon"><Icon name={archived ? "archive" : "chat"} size={23} /></span><h2>The friend group</h2><p>{personas.length} personalities. One conversation.</p></div>
        <div className="sidebar-section-label quiet-label">THE PEOPLE IN THE ROOM</div>
        <ul className="participant-list">{personas.map((persona) => {
          const online = active && state.onlineIds.includes(persona.id);
          const typing = typingIds.includes(persona.id);
          return <li key={persona.id} className={online ? "" : "participant-offline"}><div className="participant-avatar"><Avatar name={persona.name} color={persona.color} size={41} /><span className={`presence-dot ${online ? "online" : ""}`} /></div><div><span className="participant-name">{persona.name}</span><span className="participant-role">{typing ? "Typing…" : archived || !active ? "Conversation ended" : online ? persona.role_in_group : "Left the chat"}</span></div></li>;
        })}</ul>
        <div className="spectator-card"><Icon name="eye" size={20} /><strong>You’re just listening in.</strong><p>Real personalities. Unexpected tangents. Let the conversation do its thing.</p></div>
        <div className="sidebar-footer"><span className="tiny-star">✳</span><span>A little beautifully unpredictable.</span></div>
      </aside>
      <div className="chat-main">
        <header className="room-header"><div className="room-topic"><div className="room-status-row"><span className={`room-status ${active && connected ? "live" : ""}`}><i />{archived ? "SAVED CONVERSATION" : !active ? state.status === "failed" ? "CONVERSATION PAUSED" : "THAT’S A WRAP" : connected ? "LIVE CONVERSATION" : connection === "connecting" ? "GATHERING THE GROUP" : "RECONNECTING"}</span><span className="spectator-pill"><Icon name="eye" size={12} />Spectator</span></div><h2>{topic}</h2></div><div className="message-counter" aria-label={`${state.count} of ${state.maxMessages} messages`}><span>MESSAGES</span><strong>{state.count}<i> / {state.maxMessages}</i></strong></div></header>
        {error && <div className="connection-note" role="status"><span>{error}</span>{onRetry && connection === "disconnected" && active && <button onClick={onRetry} className="text-button"><Icon name="refresh" size={15} />Reconnect</button>}</div>}
        {active && connection === "reconnecting" && !error && <div className="connection-note" role="status">The connection took a breather. Reconnecting…</div>}
        <div className="message-viewport" ref={viewport} onScroll={scrolled} role="log" aria-label="Group conversation" aria-live="polite" aria-relevant="additions" tabIndex={0}>
          <div className="conversation-start"><span>THE CONVERSATION STARTS HERE</span><p>{archived ? "A saved little slice of the group chat." : "Friends with opinions, making themselves comfortable."}</p></div>
          {!timeline.length && <div className="chat-empty"><div className="empty-avatar-stack">{personas.map((persona) => <Avatar key={persona.id} name={persona.name} color={persona.color} size={50} />)}</div><h3>{connected ? "Someone’s about to have a take." : "Pulling up a few chairs…"}</h3><p>The first message is on its way.</p></div>}
          {timeline.map((event, index) => {
            if (event.type === "system_event") return <div className={`system-message ${event.reason === "room_error" ? "system-error" : ""}`} key={event.id}><span>{event.text}</span></div>;
            const missing = Math.max(0, event.count - previousMessageCount - 1);
            previousMessageCount = event.count;
            const previous = timeline[index - 1];
            const grouped = !missing && previous?.type === "chat_message" && previous.sender_id === event.sender_id;
            return <div key={event.id}>{missing > 0 && <div className="history-gap">{missing} earlier {missing === 1 ? "message was" : "messages were"} outside the live history window.</div>}<MessageBubble message={event} grouped={grouped} reply={event.reply_to ? messageMap.get(event.reply_to) : undefined} /></div>;
          })}
          {!active && <div className="conversation-end"><span className="end-icon"><Icon name={state.status === "failed" ? "chat" : "check"} size={21} /></span><h3>{state.status === "failed" ? "The conversation hit a snag." : "Good company. Good conversation."}</h3><p>{state.status === "failed" ? "You can still read the messages above or start a new room." : state.archiveStatus === "saved" ? "Saved to your private collection. Come back anytime." : "Saving this conversation to your private collection…"}</p></div>}
        </div>
        {unread > 0 && <button className="new-messages-button" onClick={jumpToLatest}>{unread} new {unread === 1 ? "message" : "messages"} <span aria-hidden="true">↓</span></button>}
        <footer className="chat-footer">{active ? <TypingIndicator personas={personas} typingIds={typingIds} /> : <div className="typing-footer"><Icon name={state.archiveStatus === "saved" ? "lock" : "archive"} size={14} /><span>{state.status === "failed" ? "The room has stopped." : state.archiveStatus === "saved" ? "Saved. Just for you." : "Saving your conversation…"}</span></div>}<span className="footer-spectator">SPECTATOR MODE</span></footer>
      </div>
    </div>
  </section>;
}
