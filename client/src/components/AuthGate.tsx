"use client";

import { useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/types/chat";
import { Avatar } from "./Avatar";
import { Icon } from "./Icon";

export function AuthGate({ onAuthenticated, sessionError }: { onAuthenticated: (user: User) => void; sessionError?: string | null }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api[mode](email.trim().toLowerCase(), password);
      setPassword("");
      onAuthenticated(result.user);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  return <main className="auth-layout page-enter">
    <section className="auth-story">
      <div className="eyebrow"><span className="tiny-star">✳</span> A FRONT ROW SEAT TO THE GROUP CHAT</div>
      <h1><span className="auth-heading-line">Good friends.</span>{" "}<span className="auth-heading-line">Strong opinions.</span>{" "}<em className="auth-heading-line">Zero small talk.</em></h1>
      <p className="intro-copy">Drop a topic. Meet a group of AI friends. Watch the conversation find a life of its own.</p>
      <div className="preview-conversation" aria-label="An example of a fictional group conversation">
        <div className="preview-note quiet-label">A LITTLE TASTE OF THE CONVERSATION</div>
        <div className="preview-message"><Avatar name="Meera" color="#6E536B" /><div><span className="sender-label" style={{ color: "#6E536B" }}>Meera <span>the idealist</span></span><p>okay but hear me out…</p></div></div>
        <div className="preview-message second"><Avatar name="Aarav" color="#4A6B5D" /><div><span className="sender-label" style={{ color: "#4A6B5D" }}>Aarav <span>the friendly skeptic</span></span><p>those are historically dangerous words</p></div></div>
        <div className="preview-caption"><span className="typing-dots"><i /><i /><i /></span> And just like that, it gets interesting.</div>
      </div>
    </section>
    <section className="auth-panel panel">
      <div className="eyebrow">YOUR SEAT IS WAITING</div>
      <h2>{mode === "login" ? "Welcome back." : "Come on in."}</h2>
      <p className="muted">{mode === "login" ? "Sign in to start a conversation worth watching." : "Create an account for your own corner of the conversation."}</p>
      <div className="auth-tabs" role="group" aria-label="Account action">
        <button type="button" className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(null); }} disabled={busy}>Sign in</button>
        <button type="button" className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(null); }} disabled={busy}>Sign up</button>
      </div>
      <form onSubmit={submit} className="auth-form">
        <label className="field-label" htmlFor="auth-email">Email address</label>
        <input id="auth-email" name="email" type="email" autoComplete="email" placeholder="you@example.com" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy} />
        <div className="label-row"><label className="field-label" htmlFor="auth-password">Password</label>{mode === "register" && <span className="field-hint">At least 8 characters</span>}</div>
        <input id="auth-password" name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={8} maxLength={128} required placeholder={mode === "login" ? "Your password" : "Make it a good one"} value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} />
        {(error || sessionError) && <p className="error-note" role="alert">{error ?? sessionError}</p>}
        <button className="button button-primary auth-submit" disabled={busy} type="submit">{busy ? <><span className="spinner" />{mode === "login" ? "Signing in…" : "Making room…"}</> : <>{mode === "login" ? "Take a seat" : "Create your account"}<Icon name="arrow" size={18} /></>}</button>
      </form>
      <p className="privacy-note"><Icon name="lock" size={14} /> Your conversations are saved just for you.</p>
    </section>
    <div className="auth-bottom-note"><Icon name="eye" size={16} /><span>You set the scene. They take it from there.</span></div>
  </main>;
}
