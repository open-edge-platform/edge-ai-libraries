# Agentic ChatQnA – LangGraph ReAct Agent

This document describes the agentic extension added to the ChatQnA sample application as part of GSoC project #36.

## What was added

The existing `/chat` endpoint uses a fixed retrieval-then-answer pipeline.
The new `/agent/chat` endpoint adds a **ReAct (Reason + Act) agent** that can dynamically decide *which tool to use* to answer a question.

## Architecture

```
User Question
      │
      ▼
  LangGraph ReAct Agent
      │
      ├── vector_search ──► PGVector knowledge base
      ├── web_search    ──► DuckDuckGo (no API key needed)
      └── calculator    ──► Safe in-process math evaluator
      │
      ▼
  Final Answer (streamed via SSE)
```

The agent runs a reasoning loop:
1. **Think** – decide if a tool is needed and which one
2. **Act** – call the chosen tool
3. **Observe** – read the result and decide if more tools are needed
4. **Answer** – write the final response

## New endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chatqna/agent/chat` | POST | Agentic chat (same request body as `/chat`) |
| `/v1/chatqna/agent/health` | GET | Lists available tools |

## Tools

### 1. `vector_search`
Queries the existing PGVector knowledge base using semantic similarity.
Use when the question is about topics in the uploaded documents.

### 2. `web_search`
Searches the web via DuckDuckGo (no API key, no rate-limit setup needed).
Use for current events or general knowledge outside the documents.

### 3. `calculator`
Evaluates math expressions safely (no `eval()` — uses Python's AST parser).
Supports `+`, `-`, `*`, `/`, `**`, `%`, and all `math` module functions.

```
sqrt(144)       → 12.0
2 ** 10         → 1024
(3 + 4) * 2.5  → 17.5
```

## Running the agent

The agent reuses the same LLM endpoint as the main ChatQnA pipeline:

```bash
# Install new deps
pip install langgraph duckduckgo-search

# Start the server (existing env vars apply)
uvicorn app.server:app --port 8080

# Check that tools are registered
curl http://localhost:8080/v1/chatqna/agent/health

# Ask a question via the agent
curl -X POST http://localhost:8080/v1/chatqna/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_messages": [{"role": "user", "content": "What is 256 * 256?"}],
    "max_tokens": 256
  }'
```

The streaming response will show `[agent]` prefixed lines for intermediate steps, followed by the plain answer tokens:

```
data: [agent] 🔧 Using tool: **calculator**('256 * 256')
data: [agent] ✅ calculator result: 256 * 256 = 65536...
data: The answer is 65,536.
```

## SSE response format

The UI can distinguish agent steps from the final answer by checking if a chunk starts with `[agent]`:

```js
if (chunk.startsWith("[agent]")) {
  // show in a collapsible "Agent Thinking" panel
} else {
  // append to the main answer bubble
}
```

## Running tests

```bash
# All existing tests
python -m pytest tests/unit_tests/ -v

# Only new agent tests
python -m pytest tests/unit_tests/test_agent.py -v
```
