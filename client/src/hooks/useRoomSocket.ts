"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError, errorMessage, SESSION_EXPIRED_EVENT, WS_URL } from "@/lib/api";
import { initialRoomState, roomReducer } from "@/lib/room-state";
import { roomEventSchema, type ConnectionStatus } from "@/types/chat";

export function useRoomSocket(roomId: string, maxMessages: number, agentIds: string[]) {
  const [state, dispatch] = useReducer(roomReducer, undefined, () => initialRoomState(maxMessages, agentIds));
  const [connection, setConnection] = useState<ConnectionStatus>("connecting");
  const [socketError, setSocketError] = useState<string | null>(null);
  const [retryVersion, setRetryVersion] = useState(0);
  const terminal = useRef(false);
  const agentKey = agentIds.join("|");
  const retry = useCallback(() => setRetryVersion((value) => value + 1), []);

  useEffect(() => {
    dispatch({ type: "reset", maxMessages, agentIds: agentKey.split("|").filter(Boolean) });
  }, [roomId, maxMessages, agentKey]);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    let probed = false;
    const controller = new AbortController();
    terminal.current = false;
    setConnection("connecting");
    setSocketError(null);

    function scheduleReconnect() {
      if (disposed || terminal.current) return;
      if (attempts >= 8) {
        setConnection("disconnected");
        setSocketError("We could not reconnect to this room. Your received messages are still here.");
        return;
      }
      setConnection("reconnecting");
      const delay = Math.min(10_000, 600 * 2 ** attempts) + Math.random() * 400;
      attempts += 1;
      retryTimer = setTimeout(connect, delay);
    }

    async function closed(event: CloseEvent) {
      if (disposed) return;
      dispatch({ type: "disconnect" });
      if (event.code === 4401) {
        setConnection("disconnected");
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
        return;
      }
      if (terminal.current) {
        setConnection("finished");
        return;
      }
      if (event.code === 4403 || event.code === 4404) {
        setConnection("disconnected");
        setSocketError("This room is no longer available.");
        return;
      }
      if (!probed) {
        probed = true;
        try {
          await api.me(controller.signal);
        } catch (error) {
          if (disposed) return;
          if (error instanceof ApiError && error.status === 401) {
            window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
            return;
          }
          setSocketError(errorMessage(error));
        }
      }
      if (!disposed) scheduleReconnect();
    }

    function connect() {
      if (disposed || terminal.current) return;
      try {
        socket = new WebSocket(`${WS_URL}/ws/rooms/${encodeURIComponent(roomId)}`);
      } catch {
        setSocketError("Could not open the live connection.");
        scheduleReconnect();
        return;
      }
      const instance = socket;
      instance.onopen = () => {
        if (disposed || socket !== instance) return;
        attempts = 0;
        probed = false;
        setConnection("connected");
        setSocketError(null);
      };
      instance.onmessage = (event: MessageEvent<string>) => {
        if (disposed || socket !== instance) return;
        try {
          const value: unknown = JSON.parse(event.data);
          if (typeof value === "object" && value !== null && "type" in value
            && !["history_sync", "chat_message", "typing", "system_event", "archive_status"].includes(String(value.type))) return;
          const parsed = roomEventSchema.safeParse(value);
          if (!parsed.success) throw new Error("Invalid update");
          dispatch({ type: "event", event: parsed.data });
          if ((parsed.data.type === "history_sync" && parsed.data.status !== "running")
            || (parsed.data.type === "system_event" && parsed.data.reason !== "agent_left")) {
            terminal.current = true;
            setConnection("finished");
          }
        } catch {
          setSocketError("An update was interrupted. Reconnecting to recover the conversation…");
          instance.close(4002, "Invalid room event");
        }
      };
      instance.onerror = () => {
        // The close handler checks the session; browsers hide handshake details.
        if (!disposed) setConnection("reconnecting");
      };
      instance.onclose = (event) => { void closed(event); };
    }

    connect();
    return () => {
      disposed = true;
      controller.abort();
      if (retryTimer) clearTimeout(retryTimer);
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        if (socket.readyState === WebSocket.OPEN) socket.close(1000, "Leaving spectator view");
        else if (socket.readyState === WebSocket.CONNECTING) socket.addEventListener("open", () => socket?.close(1000), { once: true });
      }
    };
  }, [roomId, maxMessages, agentKey, retryVersion]);

  useEffect(() => {
    if (state.status !== "completed" || state.archiveStatus !== "pending") return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    const controller = new AbortController();
    async function checkSaved() {
      try {
        await api.getChat(roomId, controller.signal);
        if (!disposed) dispatch({ type: "archive_saved" });
      } catch (error) {
        if (disposed || (error instanceof ApiError && error.status === 401)) return;
        timer = setTimeout(checkSaved, Math.min(15_000, 2_000 * 2 ** attempt++));
      }
    }
    timer = setTimeout(checkSaved, 2_000);
    return () => { disposed = true; controller.abort(); if (timer) clearTimeout(timer); };
  }, [roomId, state.status, state.archiveStatus]);

  return { state, connection, socketError, retry };
}
