# LLM Gateway API

This project implements a streaming LLM service with FastAPI, OpenAI, and Ollama:

- `POST /api/chat` provides standard conversational responses.
- `POST /api/reason` handles reasoning-oriented tasks.
- Both endpoints accept the standard `messages` format and stream Server-Sent
  Events (SSE).
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
├── api/routes.py              # FastAPI endpoints + SSE
├── core/config.py             # .env configuration
├── models/schemas.py          # standard messages schema
├── services/base.py           # abstract service + service types
├── services/factory.py        # OOP factory
├── services/openai_service.py # OpenAI Responses adapter
├── services/ollama_service.py # native Ollama streaming adapter
└── main.py                    # FastAPI app
tests/                         # mocked tests; no API cost or model required
```

Request flow:

```text
POST /api/chat or /api/reason
        -> LLMServiceFactory
        -> OpenAIResponsesService -> OpenAI Responses stream
        OR
        -> OllamaChatService -> local Ollama NDJSON stream
        -> FastAPI SSE stream
```

## 2. Set up the environment

Python 3.9 or later is required.

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

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
uvicorn app.main:app --reload
```

Open:

- Swagger UI: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

## 5. Live integration test with curl

These requests go through the running FastAPI server and call the configured real
OpenAI or Ollama provider. `-N` disables curl output buffering so streamed deltas
are visible as they arrive.

Chat:

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Explain FastAPI in two sentences."}]}'
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
data: {"provider":"openai","model":"gpt-5.6-luna","service":"chat"}

event: delta
data: {"content":"FastAPI"}

event: done
data: "[DONE]"
```

When Ollama is selected, metadata displays `"provider":"ollama"` and the local
model name.

## 6. Unit tests with pytest (mocked providers)

These tests validate routing, validation, factory selection, SSE formatting, and
provider response parsing without spending API credits or requiring Ollama. The
API endpoint tests replace the provider with a deterministic fake service only
inside the pytest process.

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

The four live cases are:

```text
OpenAI Chat    OpenAI Reason
Ollama Chat    Ollama Reason
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
