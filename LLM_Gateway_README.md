# LLM Gateway

**A production-style, provider-agnostic gateway for large-language-model APIs — streaming, stateful, and persistence-backed.**

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-async%20ORM-d71f00)](https://www.sqlalchemy.org/)
[![Alembic](https://img.shields.io/badge/Alembic-migrations-6BA81E)](https://alembic.sqlalchemy.org/)
[![Tests](https://img.shields.io/badge/tests-pytest%20%2B%20postman-0A9EDC)](#testing)
[![License](https://img.shields.io/badge/license-MIT-black)](LICENSE)

LLM Gateway puts a single, stable HTTP contract in front of multiple inference
backends. Clients always speak the same `messages` format and receive the same
Server-Sent Event stream, whether the tokens come from the **OpenAI API** or a
**self-hosted Ollama** model. Conversations are durable: every completed turn is
written to a relational database, so a client can resume a thread by ID instead
of replaying history on every request.

---

## Highlights

| | |
|---|---|
| **Streaming by default** | Both endpoints emit Server-Sent Events (`metadata` → `delta` → `done`), so tokens render as they are generated. |
| **Provider-agnostic** | `LLMServiceFactory` returns an adapter chosen from configuration. Swapping OpenAI ⇄ Ollama requires no client or endpoint changes. |
| **Stateful conversations** | Server-side history: send only the new user turn and the service prepends stored context. |
| **Durable & transactional** | Async SQLAlchemy persistence; a turn is committed atomically, and a conversation auto-created by a failed first stream is cleaned up rather than left orphaned. |
| **Versioned schema** | Alembic migrations are tracked independently of application startup — no implicit schema mutation on boot. |
| **Ownership enforced** | Conversation reads and mutations are scoped to a `user_id`; another user's thread is indistinguishable from a missing one (404). |
| **Tested two ways** | Deterministic `pytest` suite (no API credits, no Ollama required) plus a Postman collection that asserts against *live* providers. |

---

## Architecture

```
                    ┌──────────────────────────────┐
   POST /api/chat   │        FastAPI  layer        │
   POST /api/reason │  routes · Pydantic schemas   │
        ──────────► │        SSE  response         │
                    └───────────────┬──────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │     ConversationService      │   load history
                    │  (async SQLAlchemy · Alembic)│ ◄─────────────►  DB
                    └───────────────┬──────────────┘   persist turn
                                    │
                    ┌───────────────▼──────────────┐
                    │      LLMServiceFactory       │
                    │   provider × service type    │
                    └───────┬──────────────┬───────┘
                            │              │
                   ┌────────▼───────┐ ┌────▼───────────┐
                   │ OpenAIService  │ │ OllamaService  │
                   │ Responses API  │ │ local /api/chat│
                   └────────────────┘ └────────────────┘
```

**Request flow:** `POST /api/chat` → load stored history → merge with incoming
messages → factory selects an adapter → provider stream → completed turn saved
atomically → `[DONE]`.

The factory keys on *provider* **and** *service type* (`chat`, `reason`, and a
reserved `recommendation` slot), so new capabilities plug in without touching
routing code — an application of the factory + adapter patterns.

---

## API

### Inference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Stateful multi-turn conversation. Returns a `conversation_id`; reuse it and send only the new turn. |
| `POST` | `/api/reason` | Stateless reasoning-oriented response — a reasoned final answer plus a concise explanation (not hidden chain of thought). |

### Conversation management

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/conversations` | Create a thread explicitly |
| `PATCH` | `/api/conversations/{id}` | Rename (`{"user_id": "...", "title": "..."}`) |
| `DELETE` | `/api/conversations/{id}?user_id=` | Delete (cascades messages, `204`) |
| `GET` | `/api/users/{user_id}/conversations` | List a user's threads |
| `GET` | `/api/conversations/{id}/messages?user_id=` | Read stored turns in order |

### Streamed response format

```
event: metadata
data: {"provider":"openai","model":"...","service":"chat","conversation_id":"..."}

event: delta
data: {"content":"FastAPI"}

event: done
data: "[DONE]"
```

Interactive docs are served at `/docs`; liveness at `/health`.

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

cp .env.example .env          # then set LLM_PROVIDER (and a key, if using OpenAI)
alembic upgrade head          # create / update the schema
uvicorn app.main:app --reload
```

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"demo-user","messages":[{"role":"user","content":"Explain FastAPI in two sentences."}]}'
```

`-N` disables curl buffering so deltas appear as they stream.

---

## Configuration

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `openai` · `ollama` · `auto` (uses OpenAI when a valid key is present, otherwise Ollama) |
| `OPENAI_API_KEY` | Required only for the OpenAI path |
| `OPENAI_CHAT_MODEL` / `OPENAI_REASON_MODEL` | Model per service type |
| `OLLAMA_BASE_URL` / `OLLAMA_CHAT_MODEL` / `OLLAMA_REASON_MODEL` | Local inference, no key required |
| `DATABASE_URL` | Defaults to `sqlite+aiosqlite`; swap in an async PostgreSQL URL with no service-layer changes |

Both providers share one request schema and one SSE contract, so switching is a
configuration change — clients and tests stay identical. Restart Uvicorn after
editing `.env`.

**Secrets:** `.env` is git-ignored and only `.env.example` is committed; keys
never appear in source, docs, or requests. Verify with `git check-ignore -v .env`.

---

## Testing

```bash
pytest -q
```

The `pytest` suite runs against temporary SQLite databases with the provider
replaced by a deterministic fake, covering routing, request validation, factory
selection, SSE formatting, ownership rules, atomic turn persistence,
failed-first-turn cleanup, cascading deletes, history ordering, and Alembic
upgrade/downgrade. It consumes no API credits and needs no local model.

The Postman collection (`postman/`) is deliberately **not** mocked: it drives a
running Uvicorn process against real providers and asserts status, SSE content
type, the expected provider and service type, streamed output, `[DONE]`, and the
absence of an error event — including a seven-request stateful conversation flow.

Passing unit tests proves the application logic; the Postman run proves the
integration.

---

## Project layout

```
app/
├── api/routes.py                 # LLM endpoints + SSE
├── api/conversation_routes.py    # conversation CRUD
├── core/config.py                # environment configuration
├── db/models.py                  # Conversation / Message tables
├── db/session.py                 # async engine & session factory
├── models/schemas.py             # Pydantic request & response schemas
├── services/base.py              # abstract service + service types
├── services/factory.py           # provider × service-type factory
├── services/openai_service.py    # OpenAI adapter
├── services/ollama_service.py    # Ollama streaming adapter
├── services/conversation_service.py
└── main.py
migrations/                       # Alembic revisions
tests/                            # deterministic provider + temp SQLite
postman/                          # live end-to-end collection
```

---

## Notes & limits

- `user_id` is a demonstration ownership boundary, not authentication. A real
  deployment should derive identity from a verified token (e.g. JWT) rather than
  trusting client input.
- `LLM_PROVIDER=auto` resolves at service-construction time; it does not fail
  over mid-request after quota, billing, or network errors.
- `/api/reason` returns a reasoned answer and a short explanation by design — it
  does not expose a model's internal reasoning trace.

## License

MIT
