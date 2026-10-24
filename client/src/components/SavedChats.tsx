"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { ChatSummary } from "@/types/chat";
import { Icon } from "./Icon";

export function SavedChats({ onOpen, openingId }: { onOpen: (id: string) => void; openingId: string | null }) {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(async (nextCursor?: string) => {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setLoading(true);
    setError(null);
    try {
      const result = await api.listChats(nextCursor, request.signal);
      if (request.signal.aborted) return;
      setChats((current) => nextCursor
        ? [...new Map([...current, ...result.chats].map((chat) => [chat.id, chat])).values()]
        : result.chats);
      setCursor(result.next_cursor);
      setLoaded(true);
    } catch (cause) { if (!request.signal.aborted) setError(errorMessage(cause)); }
    finally { if (!request.signal.aborted) setLoading(false); }
  }, []);

  useEffect(() => { void load(); return () => controller.current?.abort(); }, [load]);

  return <section className="saved-chats" aria-labelledby="saved-chats-title">
    <div className="saved-heading"><div><span className="eyebrow">YOUR PRIVATE COLLECTION</span><h2 id="saved-chats-title">Good conversations <em>keep.</em></h2></div><button className="text-button" onClick={() => void load()} disabled={loading}><Icon name="refresh" size={15} />Refresh</button></div>
    {error && <div className="error-note" role="alert">{error}<button className="inline-button" onClick={() => void load()}>Try again</button></div>}
    {!loaded && loading && <div className="archive-skeleton" aria-label="Loading saved conversations" role="status"><span /><span /><span /></div>}
    {loaded && !chats.length && <div className="archive-empty"><Icon name="archive" size={26} /><div><h3>Nothing on the shelf. Yet.</h3><p>Your completed conversations will be saved here, ready for a second read.</p></div></div>}
    {chats.length > 0 && <div className="archive-grid">{chats.map((chat) => <button key={chat.id} className="archive-card" onClick={() => onOpen(chat.id)} disabled={openingId !== null}><div className="archive-card-top"><span className="archive-icon"><Icon name="chat" size={18} /></span><span className="quiet-label">{new Date(chat.ended_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span></div><h3>{chat.topic}</h3><div className="archive-card-bottom"><span>{chat.message_count} messages · Saved for you</span>{openingId === chat.id ? <span className="spinner" /> : <Icon name="arrow" size={18} />}</div></button>)}</div>}
    {cursor && <button className="button button-secondary load-more" onClick={() => void load(cursor)} disabled={loading}>{loading ? "Loading…" : "More conversations"}</button>}
  </section>;
}
