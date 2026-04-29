# n8n Multi-Agent Orchestrator

A six-workflow [n8n](https://n8n.io) hub that turns a single Telegram bot into a routed multi-agent assistant. One inbound message is captured, classified by an LLM, and dispatched to a specialised sub-agent (Action / Media / Commands / Qualifier) — no monolithic prompt.

> Production-tested pattern for splitting agent responsibilities across small, debuggable workflows instead of one mega-prompt.

---

## Architecture

```
                ┌────────────────────┐
   Telegram ───►│  01 Capture        │  ingests text/URL, fetches metadata,
                │  (entry point)     │  saves raw inbox row in Supabase
                └─────────┬──────────┘
                          │ executeWorkflow
                          ▼
                ┌────────────────────┐
                │  02 AI Classifier  │  LangChain agent + structured output
                │  (router)          │  → routes to one of 4 sub-workflows
                └─────────┬──────────┘
                          │
        ┌─────────────────┼──────────────────┬────────────────┐
        ▼                 ▼                  ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ 03 Action    │  │ 04 Media     │  │ 05 Commands  │  │ 06 Qualifier │
│ task / write │  │ photo/video/ │  │ /help, /list │  │ lead BANT,   │
│ → 6 sub-WFs  │  │ link assets  │  │ slash-cmds   │  │ structured   │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

**Why split:** each workflow owns one concern (10-30 nodes), can be re-deployed independently, and routes are just `executeWorkflow` calls — easy to extend with a new department without touching the router.

---

## Workflows

| File | Nodes | What it does |
|---|---|---|
| `workflows/01_capture.json` | 8 | Receives the message, extracts URL/metadata, persists to `inbox` table, replies to user |
| `workflows/02_ai_classifier.json` | 14 | LLM agent (OpenAI) with structured-output parser; decides which sub-workflow handles the message |
| `workflows/03_action.json` | 19 | Dispatcher to six action sub-workflows (e.g. copywriting, research, longform) via `executeWorkflow` |
| `workflows/04_media.json` | 9 | Photo / video / link asset routing into Supabase storage paths |
| `workflows/05_commands.json` | 7 | Slash-command handler (`/help`, listing, etc.) |
| `workflows/06_qualifier.json` | 26 | Standalone lead-qualifier agent with BANT scoring and Telegram chat-memory pattern |

All workflows use `executeWorkflowTrigger` so they can be called from a parent or chained.

---

## Stack

- **n8n** ≥ 1.30 (uses `@n8n/n8n-nodes-langchain` for the agent + structured output parser)
- **OpenAI** chat model (swap to Anthropic/Mistral/etc. by changing the `lmChat*` node)
- **Supabase** (Postgres) — `inbox`, classification audit log, lead records
- **Telegram Bot API** — surface

---

## Patterns worth stealing

1. **Router as its own workflow.** Classification has its own audit table and prompt — easy to A/B without touching downstream agents.
2. **Structured output, not free text.** Every routing decision uses `outputParserStructured` so the next workflow gets a typed payload.
3. **`executeWorkflow` over webhook chains.** Keeps invocations transactional, no inter-WF HTTP timeouts, callable from CLI.
4. **Sticky-notes as inline docs.** The qualifier WF uses `stickyNote` nodes to document BANT logic next to the prompts (see `06_qualifier.json`).
5. **One Supabase row per inbound = audit trail.** Capture → classifier → action all stamp the same inbox row, so you can debug an end-to-end run from a single SQL query.

---

## Importing into your n8n

1. **Credentials first.** All workflows reference credentials by *type* (`telegramApi`, `supabaseApi`, `openAiApi`) but the IDs are placeholders. Create your own credentials in n8n and re-link them in the imported nodes.
2. **Import order:** start with `04_media`, `05_commands` (leaves), then `03_action`, then `02_ai_classifier`, then `01_capture`. The classifier and action workflows reference the others by id.
3. **Update `executeWorkflow` references.** After import, n8n assigns new workflow IDs — update the `workflowId` field in classifier/action nodes to match.
4. **Webhook UUIDs** in the JSON are placeholders (`<uuid>`). n8n regenerates them on import; no action needed.
5. **Database schema** is intentionally not included — set up a Supabase table that fits your inbox shape and adjust the `supabase` node fields. A minimal schema:
   ```sql
   create table inbox (
     id            bigint generated always as identity primary key,
     tg_user_id    text,
     tg_chat_id    text,
     raw_text      text,
     url           text,
     classification text,
     created_at    timestamptz default now()
   );
   ```

---

## What this repo is **not**

- Not a one-click installer. n8n imports require manual credential setup and downstream-WF id remapping.
- Not a production-ready bot — system prompts and routing labels are minimal examples, swap them for your domain.
- Not coupled to any specific business — all references to internal users, projects, and chat IDs have been replaced with placeholders.

---

## License

MIT — see `LICENSE`. No warranty; you wire it up to your stack.
