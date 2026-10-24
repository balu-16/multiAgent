"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { AuthGate } from "@/components/AuthGate";
import { ArchivedRoom, LiveRoom } from "@/components/ChatStream";
import { Header } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { PersonaRoster } from "@/components/PersonaRoster";
import { SavedChats } from "@/components/SavedChats";
import { Steps } from "@/components/Steps";
import { TopicConfigForm } from "@/components/TopicConfigForm";
import { useSession } from "@/hooks/useSession";
import { api, errorMessage } from "@/lib/api";
import { personaSchema, type AgentPersona, type ArchivedChat, type TopicConfig, type User } from "@/types/chat";

const defaultConfig: TopicConfig = { topic: "", num_agents: 4, max_messages: 30 };
interface LiveRoomData { id: string; topic: string; maxMessages: number; personas: AgentPersona[] }
interface Workflow {
  stage: "CONFIG" | "ROSTER" | "LIVE";
  config: TopicConfig;
  personas: AgentPersona[];
  room: LiveRoomData | null;
  archive: ArchivedChat | null;
  busy: "generating" | "starting" | "archive" | null;
  openingId: string | null;
  error: string | null;
}
const initialWorkflow: Workflow = { stage: "CONFIG", config: defaultConfig, personas: [], room: null, archive: null, busy: null, openingId: null, error: null };
type Action =
  | { type: "config"; config: TopicConfig }
  | { type: "personas"; personas: AgentPersona[] }
  | { type: "busy"; busy: Workflow["busy"]; openingId?: string }
  | { type: "generated"; personas: AgentPersona[] }
  | { type: "started"; room: LiveRoomData }
  | { type: "archived"; chat: ArchivedChat }
  | { type: "error"; error: string }
  | { type: "back" }
  | { type: "session_end"; preserveDraft: boolean };
function workflowReducer(state: Workflow, action: Action): Workflow {
  switch (action.type) {
    case "config": return { ...state, config: action.config, error: null };
    case "personas": return { ...state, personas: action.personas, error: null };
    case "busy": return { ...state, busy: action.busy, openingId: action.openingId ?? null, error: null };
    case "generated": return { ...state, stage: "ROSTER", personas: action.personas, busy: null, error: null };
    case "started": return { ...state, stage: "LIVE", room: action.room, archive: null, busy: null, error: null };
    case "archived": return { ...state, stage: "LIVE", archive: action.chat, room: null, busy: null, openingId: null, error: null };
    case "error": return { ...state, error: action.error, busy: null, openingId: null };
    case "back": return { ...state, stage: "CONFIG", room: null, archive: null, busy: null, error: null };
    case "session_end": return { ...initialWorkflow, config: action.preserveDraft ? state.config : defaultConfig };
  }
}

export default function Home() {
  const session = useSession();
  const [workflow, dispatch] = useReducer(workflowReducer, initialWorkflow);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const requestVersion = useRef(0);
  const previousUserId = useRef<string | null>(null);
  const generation = session.generation;

  useEffect(() => {
    if (session.user) previousUserId.current = session.user.id;
    if (session.status !== "authenticated") {
      requestVersion.current += 1;
      request.current?.abort();
    }
    if (session.status === "signed_out") dispatch({ type: "session_end", preserveDraft: session.expired });
  }, [session.status, session.expired]);
  useEffect(() => () => request.current?.abort(), []);

  function begin(busy: Workflow["busy"], openingId?: string) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const version = ++requestVersion.current;
    const authVersion = generation.current;
    dispatch({ type: "busy", busy, openingId });
    return { signal: controller.signal, current: () => !controller.signal.aborted && version === requestVersion.current && authVersion === generation.current };
  }

  async function generate() {
    if (workflow.busy) return;
    const pending = begin("generating");
    try {
      const result = await api.generatePersonas(workflow.config.topic.trim(), workflow.config.num_agents, pending.signal);
      if (pending.current()) dispatch({ type: "generated", personas: result.personas });
    } catch (error) { if (pending.current()) dispatch({ type: "error", error: errorMessage(error) }); }
  }

  async function start() {
    if (workflow.busy) return;
    const personas = workflow.personas.map((persona) => ({ ...persona, name: persona.name.trim(), role_in_group: persona.role_in_group.trim(), stance_on_topic: persona.stance_on_topic.trim(), vibe_and_style: persona.vibe_and_style.trim(), expertise: persona.expertise.map((item) => item.trim()).filter(Boolean) }));
    if (personas.some((persona) => !personaSchema.safeParse(persona).success)) {
      dispatch({ type: "error", error: "Give every friend a name, role, point of view, and a little personality." });
      return;
    }
    const pending = begin("starting");
    try {
      const result = await api.startRoom(workflow.config.topic.trim(), workflow.config.max_messages, personas, pending.signal);
      if (pending.current()) dispatch({ type: "started", room: { id: result.room_id, topic: workflow.config.topic.trim(), personas, maxMessages: workflow.config.max_messages } });
    } catch (error) { if (pending.current()) dispatch({ type: "error", error: errorMessage(error) }); }
  }

  async function openArchive(id: string) {
    if (workflow.busy) return;
    const pending = begin("archive", id);
    try {
      const result = await api.getChat(id, pending.signal);
      if (pending.current()) dispatch({ type: "archived", chat: result.chat });
    } catch (error) { if (pending.current()) dispatch({ type: "error", error: errorMessage(error) }); }
  }

  async function logout() {
    if (loggingOut) return;
    setLoggingOut(true);
    setLogoutError(null);
    try { await session.logout(); dispatch({ type: "session_end", preserveDraft: false }); }
    catch (error) { setLogoutError(errorMessage(error)); }
    finally { setLoggingOut(false); }
  }

  function back() {
    requestVersion.current += 1;
    request.current?.abort();
    dispatch({ type: "back" });
  }

  function authenticated(user: User) {
    if (previousUserId.current && previousUserId.current !== user.id) dispatch({ type: "session_end", preserveDraft: false });
    previousUserId.current = user.id;
    session.acceptUser(user);
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <Header user={session.user} onLogout={() => void logout()} loggingOut={loggingOut} />
    {logoutError && <div className="page-alert error-note" role="alert">{logoutError}<button className="icon-button" aria-label="Dismiss sign out error" onClick={() => setLogoutError(null)}><Icon name="close" size={16} /></button></div>}
    <div id="main-content">
      {session.status === "restoring" ? <main className="service-state" role="status"><span className="large-spinner" /><h1>Pull up a chair.</h1><p>Finding your place in the conversation…</p></main>
        : session.status === "unavailable" ? <main className="service-state"><Icon name="chat" size={36} /><h1>We’ll be right with you.</h1><p role="alert">{session.error}</p><button className="button button-primary" onClick={session.restore}><Icon name="refresh" size={17} />Try again</button></main>
          : session.status === "signed_out" ? <AuthGate onAuthenticated={authenticated} sessionError={session.error} />
            : <main className="workspace" key={session.user.id}>
              <Steps stage={workflow.stage} />
              {workflow.stage === "CONFIG" && <><TopicConfigForm config={workflow.config} onChange={(config) => dispatch({ type: "config", config })} onGenerate={() => void generate()} busy={workflow.busy === "generating"} error={workflow.error} /><SavedChats key={session.user.id} onOpen={(id) => void openArchive(id)} openingId={workflow.openingId} /></>}
              {workflow.stage === "ROSTER" && <PersonaRoster personas={workflow.personas} topic={workflow.config.topic} onChange={(personas) => dispatch({ type: "personas", personas })} onBack={back} onStart={() => void start()} busy={workflow.busy === "starting"} error={workflow.error} />}
              {workflow.stage === "LIVE" && (workflow.archive ? <ArchivedRoom key={workflow.archive.id} chat={workflow.archive} onBack={back} /> : workflow.room && <LiveRoom key={workflow.room.id} roomId={workflow.room.id} topic={workflow.room.topic} personas={workflow.room.personas} maxMessages={workflow.room.maxMessages} onBack={back} />)}
            </main>}
    </div>
    <footer className="site-footer"><span>Made for the conversations you didn’t see coming.</span><span>BACKCHANNEL <span aria-hidden="true">✳</span> STAY CURIOUS</span></footer>
  </div>;
}
