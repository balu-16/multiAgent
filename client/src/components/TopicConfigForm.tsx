"use client";

import type { FormEvent } from "react";
import type { TopicConfig } from "@/types/chat";
import { Icon } from "./Icon";

const suggestions = ["Is AI making us more creative?", "The four-day workweek", "Is the internet still fun?"];

export function TopicConfigForm({ config, onChange, onGenerate, busy, error }: {
  config: TopicConfig; onChange: (config: TopicConfig) => void; onGenerate: () => void; busy: boolean; error: string | null;
}) {
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!busy && config.topic.trim()) onGenerate(); }
  return <section className="setup-layout page-enter">
    <div className="setup-story">
      <div className="eyebrow"><span className="tiny-star">✳</span> THE BEST TAKES HAPPEN IN THE GROUP CHAT</div>
      <h1>A little topic.<br />A little tension.<br /><em>A good conversation.</em></h1>
      <p className="intro-copy">Bring something worth talking about. We’ll bring the friends who have something to say.</p>
      <div className="how-it-works"><div><span>01</span><p>Pick the conversation starter.</p></div><div><span>02</span><p>Make the friend group your own.</p></div><div><span>03</span><p>Sit back. See where it goes.</p></div></div>
      <p className="spectator-note"><Icon name="eye" size={18} /> Spectator mode. All the conversation, no pressure to reply.</p>
    </div>
    <form className="config-panel panel" onSubmit={submit}>
      <div className="panel-heading"><span className="eyebrow">LET’S GET THEM TALKING</span><Icon name="spark" size={21} /></div>
      <label className="field-label topic-label" htmlFor="discussion-topic">What’s on your mind?</label>
      <textarea id="discussion-topic" name="topic" rows={4} maxLength={2000} required placeholder="e.g. Would you trust an AI to run your startup?" value={config.topic} onChange={(event) => onChange({ ...config, topic: event.target.value })} disabled={busy} />
      <div className="suggestion-label">OR BORROW A CONVERSATION STARTER</div>
      <div className="topic-suggestions">{suggestions.map((topic) => <button type="button" key={topic} disabled={busy} onClick={() => onChange({ ...config, topic })}>{topic} <span>↗</span></button>)}</div>
      <div className="config-divider" />
      <div className="label-row"><label className="field-label" htmlFor="agent-count">Friends in the chat</label><output className="value-chip" htmlFor="agent-count">{config.num_agents}</output></div>
      <input id="agent-count" name="num_agents" type="range" min={2} max={6} step={1} value={config.num_agents} disabled={busy} onChange={(event) => onChange({ ...config, num_agents: Number(event.target.value) })} />
      <div className="range-labels"><span>A close-knit catch-up</span><span>A lively group</span></div>
      <div className="message-cap-row"><div><label className="field-label" htmlFor="message-cap">Room for how many messages?</label><p className="field-hint">Every good conversation has a curtain call.</p></div><input id="message-cap" name="max_messages" type="number" min={10} max={80} step={1} required value={config.max_messages || ""} disabled={busy} onChange={(event) => onChange({ ...config, max_messages: Number(event.target.value) })} /></div>
      {error && <p className="error-note" role="alert">{error}</p>}
      <button className="button button-primary generate-button" disabled={busy || !config.topic.trim()} type="submit">{busy ? <><span className="spinner" />Finding your people…</> : <>Generate Friend Group <Icon name="arrow" size={19} /></>}</button>
      <p className="form-footnote">A few personalities. Plenty of possibilities.</p>
      {busy && <div className="generation-skeleton" role="status" aria-label="Generating your friend group">{Array.from({ length: config.num_agents }, (_, index) => <span key={index} />)}</div>}
    </form>
  </section>;
}
