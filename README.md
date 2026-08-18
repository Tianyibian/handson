# LLM Gateway API

This project implements a database-backed streaming LLM gateway with FastAPI,
OpenAI, and Ollama:

- `POST /api/chat` provides server-side stateful multi-turn conversations.
- `POST /api/reason` provides stateless reasoning-oriented responses.
- Both endpoints accept the standard `messages` format and stream Server-Sent
  Events (SSE).
- Async SQLAlchemy persists conversations and complete user/assistant turns.
- Conversation endpoints create threads, list a user's threads, and read stored
  messages.
- `LLM_PROVIDER=openai` forces the OpenAI Responses API.
- `LLM_PROVIDER=ollama` forces the local Ollama `/api/chat` API and requires no
  API key.
- `LLM_PROVIDER=auto` selects OpenAI when a valid key is present and otherwise
  falls back to Ollama.
- The object-oriented `LLMServiceFactory` creates an adapter based on provider
  and service type.
- The factory includes a reserved `recommendation` service type for future use.

> `/api/reason` returns a reasoned final answer and a concise user-facing
> explanation, not the model's hidden chain of thought.

## 1. Project structure

```text
app/
├── api/conversation_routes.py # conversation CRUD endpoints
├── api/routes.py              # LLM endpoints + SSE
├── core/config.py             # .env configuration
├── db/models.py               # SQLAlchemy Conversation and Message tables
├── db/session.py              # async engine and session factory
├── models/schemas.py          # Pydantic request and response schemas
├── services/base.py           # abstract service + service types
├── services/conversation_service.py # conversation persistence logic
├── services/factory.py        # OOP factory
├── services/openai_service.py # OpenAI Responses adapter
├── services/ollama_service.py # native Ollama streaming adapter
└── main.py                    # FastAPI app
migrations/                      # versioned Alembic schema changes
tests/                         # temporary SQLite + deterministic fake LLM tests
```

Request flow:

```text
POST /api/chat
        -> ConversationService -> load database history
        -> history + current messages
        -> LLMServiceFactory
        -> OpenAI or Ollama stream
        -> ConversationService -> atomically save the completed turn
        -> FastAPI SSE [DONE]
```

## 2. Set up the environment

Python 3.9 or later is required.

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The default database is local SQLite:

```dotenv
DATABASE_URL=sqlite+aiosqlite:///./llm_gateway.db
DATABASE_ECHO=false
```

The database file is ignored by Git. Initialize or upgrade the schema before
starting the application:

```bash
alembic upgrade head
```

A deployment can replace `DATABASE_URL` with an async PostgreSQL URL without
changing the conversation service contract.

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 3. Configure the LLM provider

### 3.1 OpenAI

1. Sign in to the [OpenAI Platform](https://platform.openai.com/).
2. Create a new key on the API keys page.
3. From the project root, run:

```bash
cp .env.example .env
```

4. Replace the placeholder only in your local `.env` file:

```dotenv
OPENAI_API_KEY=your_real_key_here
```

Security rules:

- Never place a key in Python source, the README, curl commands, or screenshots.
- `.env` is listed in `.gitignore`; still verify with `git status` before every
  commit.
- Share `.env.example`, never `.env`.
- If a key is exposed, revoke it immediately on the OpenAI Platform and create a
  replacement.
- API usage and ChatGPT subscriptions are separate; API access requires its own
  account billing or credits.

Confirm that Git ignores `.env`:

```bash
git check-ignore -v .env
```

Then configure:

```dotenv
LLM_PROVIDER=openai
```

### 3.2 Ollama (local, no API key required)

After installing and opening Ollama, download the model:

```bash
ollama pull qwen3:4b
ollama list
```

Configure `.env`:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen3:4b
OLLAMA_REASON_MODEL=qwen3:4b
OLLAMA_RECOMMENDATION_MODEL=qwen3:4b
OLLAMA_CHAT_THINK=true
```

If the Ollama app is not running, start it in another terminal:

```bash
ollama serve
```

For the default Qwen 3 model, Chat, Reason, and Recommendation ask Ollama to
separate thinking into its dedicated field. The adapter omits that field and
streams only the final answer. This prevents Qwen from mixing thinking tags into
normal content when `think=false`. For other models that do not support thinking,
set `OLLAMA_CHAT_THINK=false` as appropriate for the model's behavior.

## 4. Run the server

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Open:

- Swagger UI: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

Alembic tracks the database schema version independently from application
startup. Useful commands:

```bash
alembic current
alembic history
alembic revision --autogenerate -m "describe the schema change"
alembic upgrade head
alembic downgrade -1
```

Always review an autogenerated revision before applying it. Application startup
does not run migrations automatically.

## 5. Live integration test with curl

These requests go through the running FastAPI server and call the configured real
OpenAI or Ollama provider. `-N` disables curl output buffering so streamed deltas
are visible as they arrive.

Chat:

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"demo-user","messages":[{"role":"user","content":"Explain FastAPI in two sentences."}]}'
```

Reason:

```bash
curl -N -X POST http://127.0.0.1:8000/api/reason \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"If a train travels 120 km in 1.5 hours, what is its average speed? Explain briefly."}]}'
```

Example response format:

```text
event: metadata
data: {"provider":"openai","model":"gpt-5.6-luna","service":"chat","conversation_id":"..."}

event: delta
data: {"content":"FastAPI"}

event: done
data: "[DONE]"
```

When Ollama is selected, metadata displays `"provider":"ollama"` and the local
model name. Reuse the returned `conversation_id` in the next `/api/chat` request;
send only the new user turn and the server will prepend stored history.

Conversation management endpoints:

```text
POST /api/conversations
GET  /api/users/{user_id}/conversations
GET  /api/conversations/{conversation_id}/messages?user_id={user_id}
```

`user_id` is a demonstration ownership boundary, not authentication. A production
deployment should derive it from an authenticated identity such as a verified
JWT rather than trusting arbitrary client input.

## 6. Unit tests with pytest (mocked providers)

These tests validate routing, validation, factory selection, SSE formatting,
conversation ownership, atomic turn persistence, history ordering, Alembic
upgrade/downgrade behavior, and provider response parsing. They use real
temporary SQLite databases but replace the LLM provider with a deterministic
fake service, so they spend no API credits and do not require Ollama.

```bash
pytest -q
```

Passing these tests proves the application logic behaves correctly; it does not
prove that external model credentials, network access, or a local Ollama process
are working.

## 7. Live end-to-end tests with Postman (real providers)

The Postman collection is not mocked. It sends HTTP requests to separately
running Uvicorn processes, which instantiate the application's normal
`LLMServiceFactory` and call the configured OpenAI API or local Ollama API. Code
under `tests/` is not imported by Uvicorn, so pytest's fake dependency override
cannot affect these requests.

The collection includes the four provider/service checks plus a five-request
stateful conversation flow:

```text
OpenAI Chat    OpenAI Reason
Ollama Chat    Ollama Reason

Create Conversation
First Turn
Second Turn Recalls History
Verify Persisted Messages
Verify User Conversation List
```

Each request verifies HTTP 200, SSE content type, the expected real provider,
the expected service type, streamed output, `[DONE]`, and absence of an SSE error
event. If a fake provider were returned, the collection assertion would fail.

Import `postman/LLM_API.postman_collection.json` and follow the concise
run instructions in [`postman/README.md`](postman/README.md). Do not store an
OpenAI key in Postman; the OpenAI Uvicorn process reads it from the ignored local
`.env` file.

## 8. Switch dynamically between OpenAI and Ollama

Recommended configuration-level fallback:

```dotenv
LLM_PROVIDER=auto
```

When creating a service, the factory checks `OPENAI_API_KEY`. It selects Ollama
when the key is missing, empty, or still a template placeholder; otherwise, it
selects OpenAI. This configuration mode does not switch providers after quota,
billing, network, or generation-time failures.

Use OpenAI:

```dotenv
LLM_PROVIDER=openai
OPENAI_CHAT_MODEL=gpt-5.6-luna
OPENAI_REASON_MODEL=gpt-5.6-terra
OPENAI_REASONING_EFFORT=medium
```

Use local Ollama:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_CHAT_MODEL=qwen3:4b
OLLAMA_REASON_MODEL=qwen3:4b
OLLAMA_CHAT_THINK=true
```

Restart Uvicorn after every `.env` change. Both providers share the same
endpoints, request schema, and SSE response contract, so Postman requests do not
need to change when switching providers. This interchangeable behavior is the
main benefit of the factory and adapter design.
