# Master Execution Plan: "Backchannel" — Asynchronous Multi-Agent Group Chat System

## 0. Role & Orchestration Directive (READ FIRST)
You are a **Principal Distributed AI Systems Engineer (10+ years experience)** acting as the **Lead Orchestrator Agent**. 
Your objective is to build, wire, and thoroughly test **Backchannel**, a real-time, asynchronous multi-agent group chat application where AI personas behave like real friends in a group chat (double/triple/5x texting, interrupting, lurking, roasting, and organically getting tired and leaving the chat) while the human user watches in **Spectator Mode**.

### Multi-Agent Execution Strategy (Sub-Agent Delegation)
Do **NOT** build this entire monorepo sequentially in a single context. You must orchestrate this build using **two specialized Sub-Agents** and act as the **Lead Integrator & QA Engineer**:

1. **Phase 1 (Contract Lock & Scaffolding):** Create the root directory structure (`/server` and `/client`) and environment templates.
2. **Phase 2 (Spawn Sub-Agent 1 — `backend-subagent`):** Delegate the complete creation of the `/server` directory (FastAPI, `asyncio` Actor Engine, Groq `openai/gpt-oss-20b` Reflex Brain, Gemini `gemini-2.5-flash` Streaming Voice Engine, Upstash Redis state manager, and WebSockets).
3. **Phase 3 (Spawn Sub-Agent 2 — `frontend-subagent`):** Delegate the complete creation of the `/client` directory (Next.js App Router, TypeScript, Tailwind CSS Warm Beige Theme, 3-Step Spectator Workflow, Editable Persona Roster, Grouped Message Bubbles, and WebSocket client).
4. **Phase 4 (Main Agent Integration & End-to-End Testing):** Once both sub-agents complete their work, YOU (the Main Agent) must verify the REST/WebSocket contracts, boot both servers, run automated integration tests (REST + WebSocket handshake + simulated room run), fix any CORS/type/hydration mismatches, and verify zero runtime errors.

---

## 1. Monorepo Architecture & Modularity Rules
The codebase must be strictly modular so new features (e.g., Spectator "Plot Twist" injections, voice notes, web search tools, reactions) can be added via plug-and-play modules without touching core actor loops.

```text
root/
├── plan.md
├── .env.example
├── server/                         # Owned by Sub-Agent 1 (Backend)
│   ├── requirements.txt
│   ├── .env                        # GROQ_API_KEY, GEMINI_API_KEY, REDIS_URL
│   └── app/
│       ├── main.py                 # FastAPI entrypoint & CORS config
│       ├── config.py               # Env settings & constants
│       ├── schemas/
│       │   ├── persona.py          # Pydantic models for AgentPersona & Requests
│       │   └── events.py           # WebSocket & Event Bus payload schemas
│       ├── services/
│       │   ├── llm_groq.py         # Tier-1 Reflex Brain & Persona Generator (gpt-oss-20b)
│       │   ├── llm_gemini.py       # Tier-2 Uncapped Streaming Voice Model (gemini-2.5-flash)
│       │   └── redis_store.py      # Upstash Redis single-connection history/state manager
│       ├── engine/
│       │   ├── actor.py            # FriendActor class (Urge math, Fatigue, Stamina, Burst stream)
│       │   ├── room.py             # GroupChatRoom class (In-memory fan-out + WS broadcast)
│       │   └── registry.py         # Active rooms manager
│       └── api/
│           ├── routes.py           # POST /api/generate-personas, POST /api/rooms/start
│           └── ws.py               # WS /ws/rooms/{room_id}
└── client/                         # Owned by Sub-Agent 2 (Frontend)
    ├── package.json
    ├── .env.local                  # NEXT_PUBLIC_API_URL, NEXT_PUBLIC_WS_URL
    └── src/
        ├── types/chat.ts           # Shared TypeScript interfaces matching server/schemas
        ├── hooks/useRoomSocket.ts  # Custom resilient WebSocket + state hook
        ├── lib/api.ts              # Typed REST client
        ├── components/
        │   ├── Header.tsx          # Warm Beige top bar + Live room counter badge
        │   ├── TopicConfigForm.tsx # Step 1: Topic, N Agents slider, Max Messages cap
        │   ├── PersonaRoster.tsx   # Step 2: Editable cards for AI-generated personas
        │   ├── ChatStream.tsx      # Step 3: Spectator chat viewport with bubble grouping
        │   ├── MessageBubble.tsx   # WhatsApp/Discord style consecutive burst grouping
        │   └── TypingIndicator.tsx # "Aarav and Meera are typing..." animated footer
        └── app/
            ├── globals.css         # Warm Beige theme CSS variables
            ├── layout.tsx
            └── page.tsx            # State machine controller (CONFIG -> ROSTER -> LIVE)
```

---

## 2. Shared Data Contracts (Single Source of Truth)
Both sub-agents MUST adhere strictly to these JSON schemas so `/client` and `/server` integrate seamlessly on the first try.

### 2.1 `AgentPersona` Schema
```json
{
  "id": "agent_1",
  "name": "Aarav",
  "role_in_group": "The Pragmatic Systems Nerd",
  "vibe_and_style": "lowercase only, blunt, uses skull emojis sparingly, roasts hype",
  "expertise": ["backend systems", "unit economics", "distributed databases"],
  "stance_on_topic": "Skeptical and demands concrete architecture proof",
  "talkativeness": 0.75,
  "color": "#4A6B5D"
}
```

### 2.2 REST Endpoints
1. `POST /api/generate-personas`
   - **Request:** `{"topic": string, "num_agents": number}`
   - **Response:** `{"personas": AgentPersona[]}`
2. `POST /api/rooms/start`
   - **Request:** `{"topic": string, "max_messages": number, "personas": AgentPersona[]}`
   - **Response:** `{"room_id": string, "status": "started"}`

### 2.3 WebSocket Endpoint (`WS /ws/rooms/{room_id}`)
Server streams JSON events to Spectator clients:
- **History Sync (on connect):** `{"type": "history_sync", "messages": ChatMessageEvent[]}`
- **Chat Message Bubble:**
  ```json
  {
    "type": "chat_message",
    "id": "msg_14",
    "sender": "Aarav",
    "color": "#4A6B5D",
    "text": "wait hold on, have you actually calculated the latency on that?",
    "reply_to": "msg_12",
    "count": 14,
    "max_messages": 35,
    "timestamp": "2026-10-16T13:10:00Z"
  }
  ```
- **Typing Status:** `{"type": "typing", "sender": "Meera", "is_typing": true}`
- **System Event (Agent Exit / Room End):** `{"type": "system_event", "text": "Aarav got tired and left the chat 👋", "reason": "agent_left" | "max_reached"}`

---

## 3. Sub-Agent 1 Specification: `/server` (Backend Architecture)

### 3.1 Tech Stack & API Keys
- **Framework:** FastAPI + Uvicorn + `asyncio` + `redis.asyncio` + `groq` + `google-genai`.
- **Environment Variables (`.env`):**
  - `GROQ_API_KEY`
  - `GEMINI_API_KEY`
  - `REDIS_URL` (Upstash Redis `rediss://...` or `redis://...` connection string)

### 3.2 Critical Model Configurations (Zero Slowdown Rules)
1. **Tier-1 Reflex Brain & Persona Spawner (`openai/gpt-oss-20b` on Groq):**
   - MUST set `reasoning_effort="low"` on every call so thinking overhead is near zero (~120ms latency, ~950+ tokens/sec).
   - MUST use `response_format={"type": "json_schema", "json_schema": {"name": "...", "strict": True, "schema": ...}}` for guaranteed valid JSON.
2. **Tier-2 Uncapped Voice Model (`gemini-2.5-flash` via `google-genai` SDK):**
   - MUST disable thinking latency by passing:
     ```python
     config=types.GenerateContentConfig(
         system_instruction=sys_prompt,
         temperature=0.88,
         max_output_tokens=350,
         thinking_config=types.ThinkingConfig(thinking_budget=0)
     )
     ```
   - MUST use `gemini_client.aio.models.generate_content_stream(...)` for asynchronous token streaming.

### 3.3 Core Behavioral Mechanics to Implement in `/server/app/engine/`
1. **Upstash Free-Tier Optimization (Single Multiplexer Pattern):**
   - Do NOT open per-agent Redis Pub/Sub connections (which exhausts Upstash command/connection quotas).
   - Instead, use in-memory `asyncio.Queue` per `FriendActor` for sub-millisecond message fan-out inside the `GroupChatRoom`, and use a **single shared `redis.asyncio` pool** strictly to persist the rolling window of the last 30 messages (`RPUSH` + `LTRIM`) and room metadata.
2. **Uncapped Context-Driven Multi-Message Bursts (`|||` Stream Splitter):**
   - Agents do NOT have a hardcoded 2-message limit.
   - When `evaluate_reflex()` runs on `openai/gpt-oss-20b`, it classifies the social trigger into one of 4 modes:
     - `CASUAL_CHIME` (1 bubble)
     - `BANTER` (2–3 bubbles)
     - `DEEP_DIVE` (Triggered when directly asked a question OR topic matches `persona.expertise`: agent sends **3 to 6+ rapid-fire bubbles** breaking down their explanation).
     - `DEFENSIVE_ROAST` (Triggered when roasted, called out by name, or strongly disagreed with: agent sends **3 to 6+ rapid-fire bubbles** defending themselves and roasting back).
     - `SIGN_OFF` (Triggered when the agent's personal stamina hits 0).
   - As `gemini-2.5-flash` streams tokens, split on `|||` in real time. **Immediately broadcast Bubble #1 as soon as the first `|||` arrives** while the LLM is still streaming Bubbles #2–#6. Pace consecutive bubbles with a realistic typing delay (`min(1.1, max(0.35, len(bubble) * 0.014))` seconds).
3. **Cooldown Penalty (`fatigue`) with Direct-Trigger Override:**
   - Every bubble an agent sends increases `self.fatigue += 0.14`.
   - Every bubble sent by *another* agent decreases `self.fatigue = max(0.0, self.fatigue - 0.15)`.
   - **Override Rule:** If `trigger` is `ROASTED_OR_CALLED_OUT` or `DIRECT_QUESTION`, multiply `self.fatigue` by `0.2` and add `+0.45` to `raw_urge` so an agent NEVER ignores a direct question or roast just because they recently spoke!
4. **Organic Agent Fatigue ("Getting Tired & Leaving") + Hard Room Limit:**
   - Each agent initializes with `self.stamina_limit = random.randint(7, 14)` bubbles (scaled to `max_messages`).
   - When `self.bubbles_sent >= self.stamina_limit` (and at least 2 other agents are still online), the agent's next triggered turn enters `SIGN_OFF` mode: they send 1–2 casual messages making a realistic excuse (e.g., class, food delivery, sleep, debugging) and set `self.is_online = False`, emitting a `system_event` (`"{name} left the chat 👋"`).
   - **Hard Billing Cap:** `GroupChatRoom` enforces `total_messages <= max_messages` using an `asyncio.Lock()`. Once `total_messages == max_messages`, `room.is_active = False`, all actor tasks cancel cleanly, and `{"type": "system_event", "text": "Room reached the maximum message limit.", "reason": "max_reached"}` is broadcast.
5. **Deadlock Prevention (Silence Breaker):**
   - Add a background watchdog task in `GroupChatRoom`. If the room is still active (`total_messages < max_messages`), at least 2 agents are online, and no agent has spoken or typed for `4.5 seconds` (because all random urge scores happened to fall below `0.58`), automatically nudge the online agent with the lowest current `fatigue` to keep the conversation flowing naturally.

---

## 4. Sub-Agent 2 Specification: `/client` (Warm Beige Frontend)

### 4.1 Design System: Warm Beige Theme
Use Tailwind CSS to craft a cozy, high-craft Warm Beige aesthetic:
- **Primary Background (Warm Alabaster):** `#F7F3EB`
- **Elevated Surface / Panels (Toasted Sand):** `#EFE9DC`
- **Card / Chat Bubble Surface (Soft Parchment):** `#FDFBF7`
- **Borders & Hairlines:** `#E2D9C8`
- **Primary Accent / Buttons (Terracotta Clay):** `#C86D51` (Hover: `#B55E43`)
- **Primary Text (Deep Espresso):** `#2C2523`
- **Secondary Text (Muted Taupe):** `#7D7268`
- **Dynamic Agent Name Accents:** `["#4A6B5D", "#B57C3C", "#A84A3B", "#6E536B", "#4A6274", "#8C5A3C"]`

### 4.2 3-Stage User Flow (Spectator Mode)
1. **Stage 1 (`TopicConfigForm.tsx`):**
   - Textarea for the Discussion Topic.
   - Slider for Number of Agents (`2` to `6`, default `4`).
   - Number input for Total Message Cap (`10` to `80`, default `30`).
   - Button: **"Generate Friend Group →"** (shows a subtle skeleton loader while calling `POST /api/generate-personas`).
2. **Stage 2 (`PersonaRoster.tsx` — User Override Screen):**
   - Renders a responsive grid of Warm Beige persona cards returned by `gpt-oss-20b`.
   - Each card displays a keyless DiceBear illustrated avatar (`https://api.dicebear.com/9.x/notionists/svg?seed=${encodeURIComponent(persona.name)}&backgroundColor=efe9dc`).
   - **Editable Overrides:** Every field on every card (`name`, `role_in_group`, `stance_on_topic`, `vibe_and_style`, `talkativeness`) is an inline-editable input so the user can customize any agent or click **"Start Live Group Chat ▶"** immediately.
3. **Stage 3 (`ChatStream.tsx` — Live Spectator Viewport):**
   - Connects immediately to `WS /ws/rooms/{room_id}`.
   - **Sidebar / Top Bar:** Shows active/offline status dots next to each agent's avatar and a live badge: `Messages: 14 / 30`.
   - **Consecutive Burst Grouping (`MessageBubble.tsx`):**
     - If an agent sends 5 messages in a row, only Bubble #1 shows their DiceBear avatar and colored name header. Bubbles #2–#5 align cleanly underneath with tight spacing (`mt-1` vs `mt-4`) and a subtle reply-to pill if `reply_to` references an older message ID.
   - **Live Multi-Agent Typing Footer (`TypingIndicator.tsx`):**
     - Dynamically renders animated bouncing dots and `"Aarav is typing..."` or `"Aarav, Meera are typing..."`.

---

## 5. Phase 4: Main Agent Integration & Verification Checklist
After Sub-Agent 1 and Sub-Agent 2 complete their respective folders, the **Main Agent** must execute the following verification pipeline before reporting completion:

1. **Environment Wiring:**
   - Ensure `/server/.env` is populated with `GROQ_API_KEY`, `GEMINI_API_KEY`, and `REDIS_URL`.
   - Ensure `/client/.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000` and `NEXT_PUBLIC_WS_URL=ws://localhost:8000`.
2. **Backend Smoke & Contract Test:**
   - Start FastAPI (`uvicorn app.main:app --port 8000`).
   - Run a test script against `POST /api/generate-personas` with `num_agents=3` and verify valid JSON schema output from `openai/gpt-oss-20b` in under 2 seconds.
   - Run a WebSocket test client against `POST /api/rooms/start` + `WS /ws/rooms/{room_id}` with `max_messages=8` and verify:
     - Streaming bubbles arrive separated by `|||`.
     - Typing indicators toggle `true`/`false` properly.
     - Upstash Redis stores the rolling message list without errors.
     - The room cleanly halts at `max_messages=8`.
3. **Frontend Build & Type Check:**
   - Run `npm run build` (or `npx tsc --noEmit`) inside `/client` to confirm zero TypeScript or Next.js compilation errors.