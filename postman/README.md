# Postman live integration test matrix

This collection makes real model requests for every provider/service combination.
It does not use the fake services from the pytest suite.

## 1. Start both provider-specific servers

From the project root, open Terminal 1:

```bash
source .venv/bin/activate
env LLM_PROVIDER=openai uvicorn app.main:app --port 8001
```

From the project root, open Terminal 2:

```bash
source .venv/bin/activate
env LLM_PROVIDER=ollama uvicorn app.main:app --port 8002
```

Keep Ollama App running. The local model is `qwen3:4b`.

## 2. Import the collection

1. In Postman, click **Import**.
2. Choose **File**.
3. Select `postman/LLM_API.postman_collection.json`.
4. Open the imported **LLM API - Provider Matrix** collection.

The collection already contains these variables:

```text
openai_base_url = http://127.0.0.1:8001
ollama_base_url = http://127.0.0.1:8002
conversation_base_url = http://127.0.0.1:8001
conversation_user_id = postman-user
conversation_id = (set automatically)
```

Do not put the OpenAI API key in Postman. The port-8001 server reads it from the local `.env` file.

## 3. Run the provider matrix

You can open each request and click **Send**, or run the complete collection:

1. Click the collection's **...** menu.
2. Select **Run collection**.
3. Select the four requests under **OpenAI** and **Ollama**.
4. Click **Run LLM API - Provider Matrix**.

Each request reaches the real provider through FastAPI and has seven automatic
assertions:

- HTTP status is 200
- response Content-Type is SSE
- expected provider is present
- expected service type is present
- at least one delta was streamed
- the stream ended with `[DONE]`
- no SSE error event was returned

Expected matrix:

| Case | URL | Expected metadata |
| --- | --- | --- |
| OpenAI Chat | `http://127.0.0.1:8001/api/chat` | `openai` + `chat` |
| OpenAI Reason | `http://127.0.0.1:8001/api/reason` | `openai` + `reason` |
| Ollama Chat | `http://127.0.0.1:8002/api/chat` | `ollama` + `chat` |
| Ollama Reason | `http://127.0.0.1:8002/api/reason` | `ollama` + `reason` |

## 4. Run the stateful multi-turn flow

Run the five requests under **Stateful Conversation** in their numbered order:

1. **Create Conversation** creates a database record and stores its ID in the
   `conversation_id` collection variable.
2. **First Turn** tells the real model that the user's preferred backend
   framework is FastAPI. The completed user and assistant messages are saved.
3. **Second Turn Recalls History** sends only a new question. Its assertion
   reconstructs the SSE deltas and verifies that the answer recalls FastAPI.
4. **Verify Persisted Messages** checks that the database contains exactly two
   complete turns ordered as user, assistant, user, assistant.
5. **Verify User Conversation List** checks that the new conversation appears in
   the user's conversation list.

The default `conversation_base_url` uses the OpenAI server on port 8001. Set it
to `http://127.0.0.1:8002` to run the same stateful flow through Ollama. Creating
a new conversation at the beginning makes repeated collection runs independent.
