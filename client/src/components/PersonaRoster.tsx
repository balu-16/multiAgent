"use client";

import type { FormEvent } from "react";
import type { AgentPersona } from "@/types/chat";
import { Avatar } from "./Avatar";
import { Icon } from "./Icon";

const palette = ["#4A6B5D", "#B57C3C", "#A84A3B", "#6E536B", "#4A6274", "#8C5A3C"];

export function PersonaRoster({ personas, topic, onChange, onBack, onStart, busy, error }: {
  personas: AgentPersona[]; topic: string; onChange: (personas: AgentPersona[]) => void; onBack: () => void; onStart: () => void; busy: boolean; error: string | null;
}) {
  function update(id: string, patch: Partial<AgentPersona>) { onChange(personas.map((persona) => persona.id === id ? { ...persona, ...patch } : persona)); }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!busy) onStart(); }
  return <section className="roster-section page-enter">
    <div className="section-title-row"><div><div className="eyebrow">A FEW DIFFERENT POINTS OF VIEW</div><h1>Meet your <em>kind of people.</em></h1><p className="muted">A cast with opinions. Fine-tune any detail, or let them be themselves.</p></div><button className="text-button" onClick={onBack} disabled={busy}><Icon name="back" size={17} /> Change the topic</button></div>
    <div className="topic-ribbon"><span className="quiet-label">ON THE TABLE</span><p>{topic}</p></div>
    <form onSubmit={submit}>
      <div className="persona-grid">{personas.map((persona, index) => <article className="persona-card" key={persona.id} style={{ "--persona-accent": persona.color } as React.CSSProperties}>
        <div className="persona-card-top"><Avatar name={persona.name} color={persona.color} size={62} /><span className="persona-number">FRIEND {String(index + 1).padStart(2, "0")}</span><span className="persona-accent-dot" /></div>
        <label className="sr-only" htmlFor={`${persona.id}-name`}>Friend {index + 1} name</label><input id={`${persona.id}-name`} className="persona-name" value={persona.name} maxLength={80} required disabled={busy} onChange={(event) => update(persona.id, { name: event.target.value })} />
        <label className="sr-only" htmlFor={`${persona.id}-role`}>{persona.name} role</label><input id={`${persona.id}-role`} className="persona-role" value={persona.role_in_group} maxLength={200} required disabled={busy} onChange={(event) => update(persona.id, { role_in_group: event.target.value })} />
        <label className="card-field-label" htmlFor={`${persona.id}-stance`}>THEIR TAKE</label><textarea id={`${persona.id}-stance`} rows={3} value={persona.stance_on_topic} maxLength={2000} required disabled={busy} onChange={(event) => update(persona.id, { stance_on_topic: event.target.value })} />
        <label className="card-field-label" htmlFor={`${persona.id}-vibe`}>HOW THEY TALK</label><textarea id={`${persona.id}-vibe`} rows={3} value={persona.vibe_and_style} maxLength={2000} required disabled={busy} onChange={(event) => update(persona.id, { vibe_and_style: event.target.value })} />
        <label className="card-field-label" htmlFor={`${persona.id}-expertise`}>KNOWS A THING OR TWO ABOUT</label><input id={`${persona.id}-expertise`} value={persona.expertise.join(", ")} maxLength={1000} disabled={busy} onChange={(event) => update(persona.id, { expertise: event.target.value.split(",").map((item) => item.trimStart()) })} />
        <div className="label-row talkativeness-label"><label className="card-field-label" htmlFor={`${persona.id}-talkativeness`}>SOCIAL BATTERY</label><span className="field-hint">{Math.round(persona.talkativeness * 100)}%</span></div><input id={`${persona.id}-talkativeness`} type="range" min={0} max={1} step={0.05} value={persona.talkativeness} disabled={busy} onChange={(event) => update(persona.id, { talkativeness: Number(event.target.value) })} />
        <div className="range-labels"><span>Listens, then lands a point</span><span>Has a lot to say</span></div>
        <div className="persona-colors" role="group" aria-label={`${persona.name} accent color`}>{palette.map((color, colorIndex) => <button type="button" key={color} className={persona.color.toLowerCase() === color.toLowerCase() ? "selected" : ""} style={{ backgroundColor: color }} onClick={() => update(persona.id, { color })} disabled={busy} aria-label={`Accent color ${colorIndex + 1} for ${persona.name}`} aria-pressed={persona.color.toLowerCase() === color.toLowerCase()} />)}</div>
      </article>)}</div>
      {error && <p className="error-note" role="alert">{error}</p>}
      <div className="roster-footer"><p><Icon name="eye" size={18} /> Your only job now? Enjoy the conversation.</p><button className="button button-primary" disabled={busy} type="submit">{busy ? <><span className="spinner" />Getting everyone together…</> : <>Start Live Group Chat <span aria-hidden="true">▶</span></>}</button></div>
    </form>
  </section>;
}
