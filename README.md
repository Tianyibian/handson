# LLM API Integration Homework

这是一个使用 FastAPI、OpenAI 和 Ollama 的流式 LLM 服务：

- `POST /api/chat`：普通对话
- `POST /api/reason`：推理任务
- 两个接口都接收标准 `messages`，并以 Server-Sent Events（SSE）流式返回
- `LLM_PROVIDER=openai`：强制使用 OpenAI Responses API
- `LLM_PROVIDER=ollama`：强制使用本机 Ollama `/api/chat`，不需要 API key
- `LLM_PROVIDER=auto`：有真实 OpenAI key 时使用 OpenAI，否则 fallback 到 Ollama
- OOP `LLMServiceFactory` 根据 provider 和 service type 创建对应 adapter
- 已在 factory 中预留 `recommendation` service type

> `/api/reason` 返回的是经过推理后的最终答案和可公开解释，不是模型的隐藏 chain-of-thought。

## 1. 项目结构

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

调用关系：

```text
POST /api/chat or /api/reason
        -> LLMServiceFactory
        -> OpenAIResponsesService -> OpenAI Responses stream
        OR
        -> OllamaChatService -> local Ollama NDJSON stream
        -> FastAPI SSE stream
```

## 2. 创建虚拟环境并安装依赖

需要 Python 3.9 或更新版本。

macOS/Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 3. 配置 LLM provider

### 3.1 OpenAI

1. 登录 [OpenAI Platform](https://platform.openai.com/)。
2. 在 API keys 页面创建一个新 key。
3. 在项目根目录运行：

```bash
cp .env.example .env
```

4. 只在本机的 `.env` 中替换占位符：

```dotenv
OPENAI_API_KEY=your_real_key_here
```

安全规则：

- 不要把 key 写在 Python、README、curl 命令或截图里。
- `.env` 已加入 `.gitignore`；提交前仍应运行 `git status` 检查。
- 分享项目时分享 `.env.example`，绝不分享 `.env`。
- 如果 key 曾被公开，立即在 OpenAI Platform 撤销并创建新 key。
- API key 和 ChatGPT 订阅不是一回事；API 使用需要单独的 API 账户计费/额度。

确认 `.env` 会被 Git 忽略：

```bash
git check-ignore -v .env
```

并设置：

```dotenv
LLM_PROVIDER=openai
```

### 3.2 Ollama（本地、无需 API key）

安装并打开 Ollama 后，先下载模型：

```bash
ollama pull qwen3:4b
ollama list
```

在 `.env` 中设置：

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen3:4b
OLLAMA_REASON_MODEL=qwen3:4b
OLLAMA_RECOMMENDATION_MODEL=qwen3:4b
OLLAMA_CHAT_THINK=true
```

如果 Ollama App 没有运行，可以在另一个 Terminal 中运行：

```bash
ollama serve
```

对于默认的 Qwen 3，Chat、Reason 和 Recommendation 都让 Ollama 把 thinking 分离到专用字段；adapter 不会转发该字段，只流式返回最终答案。这样可避免 Qwen 在 `think=false` 时把思考标签混入普通内容。对于不支持 thinking 的其他模型，可以按模型行为把 `OLLAMA_CHAT_THINK` 改成 `false`。

## 4. 启动服务

```bash
uvicorn app.main:app --reload
```

打开：

- Swagger UI: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

## 5. 使用 curl 测试流

`-N` 会关闭 curl 的输出缓冲，便于看到 token/delta 逐步到达。

Chat：

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Explain FastAPI in two sentences."}]}'
```

Reason：

```bash
curl -N -X POST http://127.0.0.1:8000/api/reason \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"If a train travels 120 km in 1.5 hours, what is its average speed? Explain briefly."}]}'
```

返回格式示例：

```text
event: metadata
data: {"provider":"openai","model":"gpt-5.6-luna","service":"chat"}

event: delta
data: {"content":"FastAPI"}

event: done
data: "[DONE]"
```

使用 Ollama 时，metadata 会显示 `"provider":"ollama"` 和本地模型名。

## 6. 自动化测试（不会调用 OpenAI 或真实 Ollama）

测试使用 fake factory/service 替换真实 OpenAI adapter：

```bash
pytest -q
```

覆盖内容包括：两个 endpoints、SSE、request validation、OpenAI/Ollama factory、缺少 OpenAI key，以及 Ollama NDJSON 流解析。

## 7. 什么是 Postman？

Postman 是一个带图形界面的 API 测试工具。它让你选择 HTTP method、填写 URL、headers 和 JSON body，然后查看 status、headers 与 response；不需要自己写 curl。

测试本项目：

1. 安装并打开 Postman，选择 **New > HTTP Request**。
2. Method 选 `POST`，URL 填 `http://127.0.0.1:8000/api/chat`。
3. 在 **Headers** 添加 `Content-Type: application/json`。
4. 在 **Body > raw > JSON** 填：

```json
{
  "messages": [
    {"role": "user", "content": "Hello! Introduce yourself in one sentence."}
  ]
}
```

5. 点击 **Send**。截图时保留 method、URL、request body 和 response，但不要显示 `.env` 或 API key。

对于 streaming，curl 的 `-N` 通常最直观；Postman 可能根据版本把分块结果集中显示，但接口仍然是 SSE stream。

四种 provider/service 组合的可导入 Collection 与完整操作说明在 [`postman/`](postman/README.md)：

```text
OpenAI Chat    OpenAI Reason
Ollama Chat    Ollama Reason
```

## 8. 动态切换 OpenAI 与 Ollama

配置级 fallback（推荐的自动模式）：

```dotenv
LLM_PROVIDER=auto
```

Factory 在创建 service 时检查 `OPENAI_API_KEY`：key 缺失、为空或仍是模板占位符时选择 Ollama，否则选择 OpenAI。这个模式不会捕获 quota、billing、网络或生成过程中的错误后再切换 provider。

使用 OpenAI：

```dotenv
LLM_PROVIDER=openai
OPENAI_CHAT_MODEL=gpt-5.6-luna
OPENAI_REASON_MODEL=gpt-5.6-terra
OPENAI_REASONING_EFFORT=medium
```

使用本机 Ollama：

```dotenv
LLM_PROVIDER=ollama
OLLAMA_CHAT_MODEL=qwen3:4b
OLLAMA_REASON_MODEL=qwen3:4b
OLLAMA_CHAT_THINK=true
```

每次修改 `.env` 后重启 Uvicorn。两个 provider 共用相同 endpoints、request schema 和 SSE response contract；切换时 Postman 请求无需修改。这正是 factory/OOP 在这里的价值。
