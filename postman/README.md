# Postman four-case test matrix

This collection tests all provider/service combinations without repeatedly editing `.env`.

## 1. Start both provider-specific servers

Open Terminal 1:

```bash
cd "/Users/tianyi/找工作/handson"
source .venv/bin/activate
env LLM_PROVIDER=openai uvicorn app.main:app --port 8001
```

Open Terminal 2:

```bash
cd "/Users/tianyi/找工作/handson"
source .venv/bin/activate
env LLM_PROVIDER=ollama uvicorn app.main:app --port 8002
```

Keep Ollama App running. The local model is `qwen3:4b`.

## 2. Import the collection

1. In Postman, click **Import**.
2. Choose **File**.
3. Select `postman/LLM_API_Homework.postman_collection.json`.
4. Open the imported **LLM API Homework - Provider Matrix** collection.

The collection already contains these variables:

```text
openai_base_url = http://127.0.0.1:8001
ollama_base_url = http://127.0.0.1:8002
```

Do not put the OpenAI API key in Postman. The port-8001 server reads it from the local `.env` file.

## 3. Run the four cases

You can open each request and click **Send**, or run the complete collection:

1. Click the collection's **...** menu.
2. Select **Run collection**.
3. Keep all four requests selected.
4. Click **Run LLM API Homework - Provider Matrix**.

Each request has seven automatic assertions:

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

## 4. Homework screenshots

For each request, capture method, URL, JSON body, SSE response, and the green test results. Never include `.env` or the OpenAI key in a screenshot.
