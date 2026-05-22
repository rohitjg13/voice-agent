# Voice Agent Platform

A cold-calling AI agent where **industries are swappable YAML configs**, not code.
Vapi handles the audio; all conversational intelligence lives in a FastAPI backend
exposing an OpenAI-compatible Custom LLM endpoint.

| | |
|---|---|
| Live API | `https://voice-agent-rohitjg.fly.dev` |
| Tests | 154 passing |
| Adversarial personas | 12 (CI evals run in seconds, no audio) |
| Industries | `dental_saas`, `b2b_recruitment` (drop in YAML to add a third) |

---

## Architecture

```
   Caller's phone
        │
        ▼
   ┌───────────────────── Vapi ─────────────────────┐
   │  Twilio (telephony)                            │
   │  Deepgram (STT) ──► transcript                 │
   │  ElevenLabs (TTS) ◄── text                     │
   │  Voice UX: VAD, turn-taking, barge-in,         │
   │            voicemail detect, end-call detect   │
   │                                                │
   │  Custom LLM: forwards OpenAI-shaped JSON to    │
   │  → POST /vapi/llm/chat/completions             │
   │                                                │
   │  End-of-call report:                           │
   │  → POST /vapi/server                           │
   └────────────────────┬───────────────────────────┘
                        │
                        ▼
   ┌──────────── FastAPI orchestrator (Fly.io) ─────────────┐
   │                                                        │
   │  POST /vapi/llm/chat/completions (per turn)            │
   │  ─────────────────────────────────────────             │
   │   1. DNC pre-flight check                              │
   │   2. Load IndustryPack (YAML → Pydantic, cached)       │
   │   3. Fetch CallState from Redis (or initialise)        │
   │   4. Classify intent via Haiku (one line)              │
   │      → (Intent, objection_id)                          │
   │   5. FSM transition: OPENER → PERMISSION → DISCOVERY   │
   │                     → PITCH ⇄ OBJECTION → CLOSE        │
   │                     → SCHEDULE → END                   │
   │   6. If OBJECTION: pack lookup + RAG retrieval         │
   │   7. If SCHEDULE: extract email/name from user turn    │
   │   8. Compose system prompt:                            │
   │      [base from pack] + [runtime context: today,       │
   │      working-day calendar] + [stage instruction]       │
   │      + [compliance directive]                          │
   │   9. Stream Claude Sonnet 4.6 (OpenAI SSE format)      │
   │  10. Post-stream: audit response, persist state        │
   │                                                        │
   │  POST /vapi/server (call ended)                        │
   │  ─────────────────────────────                         │
   │   • Haiku extracts {booked, time, email, name}         │
   │   • UPSERT into appointments table                     │
   │                                                        │
   └────┬───────────────────────────────┬───────────────────┘
        │                               │
        ▼                               ▼
  Upstash Redis                    Supabase Postgres
  (per-call state,                 • pgvector RAG chunks
   4-hour TTL)                     • appointments table
```

---

## Stack

| Layer | Choice |
|---|---|
| Voice | Vapi (Twilio + Deepgram + ElevenLabs bundled) |
| Generation LLM | Claude Sonnet 4.6 (`claude-sonnet-4-6`) |
| Classifier / extractor LLM | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Backend | FastAPI, Python 3.11, asyncpg |
| State | Upstash Redis (REST) |
| Vector + relational | Supabase Postgres + pgvector |
| Templating | Jinja2 (system prompt composition) |
| Deploy | Fly.io (`ord`) |
| CI | GitHub Actions (ruff + mypy + pytest) |

---

## What's in the box

| Subsystem | Where | Notes |
|---|---|---|
| Industry pack schema + loader | `packs/_schema/pack.py`, `packs/pack_loader.py` | Pydantic, `extra="forbid"`, in-process cache |
| Two real packs | `packs/dental_saas/`, `packs/b2b_recruitment/` | YAML + knowledge docs each |
| Per-call FSM | `orchestrator/services/state_machine.py` | Pure function, 21 unit tests |
| Intent classifier | `orchestrator/services/intent_classifier.py` | Single Haiku call, `intent:objection_id` format |
| Objection handler | `orchestrator/services/objection_handler.py` | Taxonomy lookup → pattern fallback → escalating response → RAG-augmented |
| RAG | `orchestrator/services/rag.py`, `ingest.py` | Chunk → embed (OpenAI) → pgvector cosine search |
| Compliance | `orchestrator/services/compliance.py` | DNC, banned-word audit, disclosure tracking |
| Appointment capture | `orchestrator/services/appointment_extractor.py` | Post-call Haiku extraction → Supabase row |
| Speech-email sanitiser | same | Handles "at"/"dot"/spaces from STT |
| Adversarial simulator | `simulator/` | 12 personas, in-process httpx, no audio |

---

## Setup

### Prerequisites

- Python 3.11
- Supabase project (free tier OK)
- Upstash Redis (free tier OK)
- Anthropic API key
- OpenAI API key (embeddings only)
- Vapi account + Fly.io account for live calls

### Local dev

```bash
git clone <repo>
cd voice-agent-platform

python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, OPENAI_API_KEY, DATABASE_URL,
#         UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN

# One-time: run migrations in Supabase SQL editor
#   infra/migrations/001_knowledge_chunks.sql
#   infra/migrations/002_appointments.sql

# One-time: ingest the dental pack's knowledge into pgvector
.venv/bin/python -m orchestrator.services.ingest dental_saas

# Start the server
.venv/bin/uvicorn orchestrator.main:app --port 8001 --reload

# In another terminal:
curl http://localhost:8001/health
```

### Test the LLM endpoint via curl

```bash
curl -sN -X POST http://localhost:8001/vapi/llm \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "stream": true,
    "messages": [{"role": "user", "content": "Hi, who is this?"}],
    "call": {"id": "dev-test-1"}
  }'
```

You'll see OpenAI-format SSE chunks streaming back from Claude.

### Run the adversarial simulator

The simulator drives a full conversation against the live `/vapi/llm` endpoint
**in-process** via `httpx.ASGITransport` — no audio, no Vapi, no network. Costs
about $0.01 per persona (both sides use Haiku).

```bash
# All 12 personas
.venv/bin/python -m simulator.cli --all

# Single persona with full transcript
.venv/bin/python -m simulator.cli --persona compliance_tester --verbose
```

Output:
```
═══ Simulator Report ═══
Personas run:        12
Demos booked:        7 (58%)
Avg turns per call:  9.3
Compliance issues:   0

Per-persona breakdown:
  eager_adopter                        ✓ booked     turns=4
  skeptical_office_manager             ✓ booked     turns=11
  hostile                              ✗ no book    turns=4
  ...
```

### Run unit tests

```bash
.venv/bin/pytest tests/ -v
# 154 passed
```

---

## Deploy

```bash
# Fly.io
flyctl apps create voice-agent-<yourname>
flyctl secrets set \
  ANTHROPIC_API_KEY="..." OPENAI_API_KEY="..." \
  DATABASE_URL="postgresql://..." \
  UPSTASH_REDIS_REST_URL="..." UPSTASH_REDIS_REST_TOKEN="..." \
  ACTIVE_PACK="dental_saas" \
  --app voice-agent-<yourname>
flyctl deploy --app voice-agent-<yourname>

# Vapi (dashboard)
#   • Custom LLM URL: https://voice-agent-<yourname>.fly.dev/vapi/llm
#     Custom LLM API Key: <same as VAPI_LLM_SECRET on Fly>
#   • Server URL:     https://voice-agent-<yourname>.fly.dev/vapi/server
#     Server Secret:    <same as VAPI_SERVER_SECRET on Fly>
#   • End Call Phrases: "Thanks again, talk soon — goodbye"
#   • Transcriber: Deepgram nova-2
#   • Voice: ElevenLabs (any warm voice)
#   • First Message: hardcode the pack's opener
```

CI/CD (`.github/workflows/`) runs ruff + mypy + pytest on every PR and
auto-deploys to Fly.io on push to `main` (needs `FLY_API_TOKEN` repo secret).

---

## Adding a new industry — the extensibility proof

Zero Python changes needed. Three steps:

1. Create `packs/<industry>/pack.yaml` matching the schema in `packs/_schema/pack.py`
2. Drop knowledge docs into `packs/<industry>/knowledge/*.md`
3. Run `python -m orchestrator.services.ingest <industry>`

Set `ACTIVE_PACK=<industry>` in the environment and restart. The FSM, classifier,
objection handler, RAG, and compliance all work unchanged.

See `packs/b2b_recruitment/` for a full second-industry example.

---

## Folder layout

```
voice-agent-platform/
├── orchestrator/                    FastAPI app
│   ├── main.py                      app factory + lifespan
│   ├── config.py                    pydantic-settings
│   ├── db.py                        asyncpg pool
│   ├── routers/vapi.py              /vapi/llm + /vapi/server
│   ├── models/                      CallState, VapiRequest, Appointment, …
│   └── services/                    one file per subsystem
│       ├── state_machine.py         pure FSM
│       ├── intent_classifier.py     Haiku → (Intent, objection_id)
│       ├── objection_handler.py     taxonomy + strikes + RAG
│       ├── prompt_composer.py       Jinja2 + stage + runtime context
│       ├── compliance.py            DNC, audit, disclosure
│       ├── rag.py                   chunk + embed + retrieve
│       ├── ingest.py                CLI for loading knowledge
│       ├── call_state_store.py      Redis CRUD (mem fallback)
│       ├── schedule_extractor.py    pull email/name from a turn
│       ├── appointment_extractor.py post-call structured extraction
│       ├── appointment_store.py     Supabase UPSERT
│       └── auth.py                  Vapi shared-secret verifiers
│
├── packs/
│   ├── _schema/pack.py              Pydantic IndustryPack
│   ├── pack_loader.py               YAML → IndustryPack (cached)
│   ├── dental_saas/                 pack.yaml + knowledge/*.md
│   └── b2b_recruitment/             pack.yaml + knowledge/*.md
│
├── simulator/                       adversarial test harness
├── infra/                           Dockerfile + SQL migrations
├── tests/                           164 tests, mocks for all external APIs
└── .github/workflows/               ci.yml, deploy.yml
```

---

## Known limitations / next steps

- **No real calendar invite is sent.** The appointment is captured into a Supabase
  row; integrating Cal.com / Google Calendar is a 1-hour follow-up.
- **Webhook auth is shared-secret only.** Set `VAPI_LLM_SECRET` and
  `VAPI_SERVER_SECRET`; the backend rejects requests without
  `Authorization: Bearer <secret>` (Custom LLM) and
  `x-vapi-secret: <secret>` (server webhook), using constant-time comparison.
  Production might want signed JWTs or mTLS instead.
- **DNC list is hardcoded.** Real deployment should integrate the FTC DNC registry
  or an internal suppression list.
- **No call recording transcription pipeline.** Vapi stores recordings; we don't
  pull them into our own warehouse for analytics yet.
- **Latency: ~150ms DB round trip** because Supabase is in Tokyo and Fly is in
  Chicago. Moving them to the same region would help if we wanted < 1s response
  budgets.
- **Voicemail handling** is enabled in Vapi but we don't have a distinct
  voicemail-script branch in the FSM.

---

## Architecture Decision Records

### ADR-001 — Industry knowledge as YAML, not code

**Decision:** Each industry is a single YAML file plus markdown knowledge docs.
The schema lives in one Pydantic model.

**Why:**
- Non-engineers can ship a new industry (sales team owns the YAML)
- One file diff to review when changing the pitch / objection responses
- Forces the schema to be the contract, prevents per-industry custom code
- Bad packs fail loudly at load time (`extra="forbid"`)

**Trade-off:** YAML can express persona + scripts + objections + compliance, but
not arbitrary per-industry logic (e.g. industry-specific tools). When that
becomes necessary, a pack-scoped plugin hook is the next step.

### ADR-002 — Hand-rolled FSM instead of LangGraph

**Decision:** Conversation state transitions are a 90-line pure function with a
`match` statement, not a graph framework.

**Why:**
- The FSM has 8 states and ~15 transitions. LangGraph's tracing / persistence
  features don't earn the dependency weight at this size.
- Tests are trivial: pass a `CallState`, assert the next state. No mocking.
- Onboarding cost for someone reading the code: ~5 minutes.

**Trade-off:** If transitions grow beyond ~30 or need branch-and-merge semantics,
LangGraph's graph compiler pays off. We're not there.

### ADR-003 — Vapi Custom LLM mode (not Vapi's built-in model routing)

**Decision:** Vapi knows nothing about packs, state, or RAG. It treats our
backend as an OpenAI-compatible LLM endpoint.

**Why:**
- All intelligence stays in one process — easy to test end-to-end without audio
- Provider-agnostic: swap Claude → GPT-4 → local model without touching Vapi
- The simulator (step 12) runs the same code path Vapi uses, in-process
- Per-call state can live in our DB instead of being smuggled through Vapi's
  metadata fields

**Trade-off:** We have to handle SSE formatting and OpenAI-shaped payloads
ourselves. Worth it.

### ADR-004 — Split LLMs: Haiku for classification, Sonnet for generation

**Decision:** Intent / objection-id / schedule extraction use Haiku 4.5. The
spoken response uses Sonnet 4.6.

**Why:**
- Classification is one-line structured output — Haiku is reliable and ~$0.001/call
- Generation needs strict multi-step instruction-following (collect email, then
  name, then confirm); early tests with Haiku showed it skipping steps
- ~12× cost difference, but Sonnet calls run ~1/call vs Haiku's ~2/call
- Total LLM cost per conversation: ~$0.02

**Trade-off:** Two models means two prompts to maintain. Acceptable given the
clarity gain.

### ADR-005 — Post-call extraction for appointments (not mid-call tool use)

**Decision:** When Vapi sends the end-of-call webhook, we run one Haiku call
over the full transcript to extract `{booked, name, email, time}` and UPSERT
to Supabase.

**Why:**
- Mid-call tool use over SSE is fiddly (function-call deltas, partial JSON)
- The full transcript gives strictly more context than per-turn extraction
- Idempotent: a row keyed by `call_id` is easy to re-run if extraction failed
- Failures don't degrade the live call

**Trade-off:** No real-time booking signal to Vapi mid-call (e.g. couldn't push
a calendar event before the user hangs up). If we needed that, we'd add a
`book_appointment` tool definition at the SCHEDULE state.

### ADR-006 — FSM gates SCHEDULE exit on collected_email AND collected_name

**Decision:** The state machine **refuses** to transition `SCHEDULE → END`
until both fields are set in `CallState`. Each turn in SCHEDULE shows a
single-question prompt (ask email, then ask name, then confirm).

**Why:**
- Earlier versions relied on the LLM following multi-step prompt instructions.
  Sonnet would skip steps "to be conversational" — booking a meeting without
  ever asking for the name.
- Making it a state invariant means the bot literally cannot end the call until
  the data is captured.
- The per-turn extractor is one cheap Haiku call.

**Trade-off:** Adds one LLM call per SCHEDULE turn. Worth it for reliability.

### ADR-007 — Shared-secret webhook auth between Vapi and the backend

**Decision:** Two FastAPI dependencies (`verify_llm_auth`, `verify_server_auth`)
check headers using `hmac.compare_digest`. Secrets live in env vars
(`VAPI_LLM_SECRET`, `VAPI_SERVER_SECRET`); when empty, auth is skipped for dev.

**Why:**
- The Custom LLM URL and server webhook are publicly reachable. Without auth,
  anyone who finds them can drive Claude calls on your dime or spoof end-of-call
  reports to write fake appointments.
- Vapi natively supports both headers in its assistant config — no custom
  middleware needed on their side.
- Constant-time comparison avoids timing side-channels against the secret.

**Trade-off:** Static secrets are weaker than signed JWTs or mTLS. Acceptable
because Vapi's outbound auth options are limited and the threat is opportunistic
scanning, not a determined attacker.

### ADR-008 — Adversarial simulator over real-audio CI

**Decision:** Tests against the agent's conversational behaviour use in-process
HTTP calls to `/vapi/llm/` plus an LLM-driven persona. No audio, no Vapi, no
Twilio.

**Why:**
- A full Vapi audio round-trip costs ~$0.09/min and takes minutes; the
  simulator runs 12 personas in ~30 seconds for ~$0.09 total
- All conversational regressions surface before CI hits the cloud
- Vapi's voice UX (VAD, barge-in) is Vapi's concern, not ours

