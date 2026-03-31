"""
Isolated test script for the agent tools (calculator + web_search).
Runs without needing PGVector, psycopg, or a live LLM endpoint.
"""
import sys
import os

# Make the app package importable from the project root
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_HERE, "..", "..")   # …/chat-question-and-answer/
sys.path.insert(0, os.path.abspath(_PROJECT_ROOT))

# Patch out the chain module before import to avoid DB connections
from unittest.mock import patch, MagicMock

# Stub heavy deps not available in dev
for mod in [
    "sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio",
    "langchain_postgres", "langchain_postgres.vectorstores",
    "psycopg", "asyncpg",
    "opentelemetry", "opentelemetry.sdk", "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export", "opentelemetry.exporter",
    "opentelemetry.exporter.otlp", "opentelemetry.exporter.otlp.proto",
    "opentelemetry.exporter.otlp.proto.http",
    "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    "opentelemetry.instrumentation", "opentelemetry.instrumentation.fastapi",
    "openlit",
]:
    sys.modules.setdefault(mod, MagicMock())


# ----------------------------------------------------------------
# Import only the parts we want to test
# ----------------------------------------------------------------
from app.agent import calculator, web_search, TOOLS   # noqa: E402

PASS = "✅ PASS"
FAIL = "❌ FAIL"

results = []

def check(name, cond):
    status = PASS if cond else FAIL
    results.append((name, status))
    print(f"  {status}  {name}")

# ---- calculator tests ----
print("\n── calculator ──────────────────────────────")
check("2 + 3 = 5",          "5" in calculator.invoke({"expression": "2 + 3"}))
check("6 * 7 = 42",         "42" in calculator.invoke({"expression": "6 * 7"}))
check("2 ** 10 = 1024",     "1024" in calculator.invoke({"expression": "2 ** 10"}))
check("10 / 4 = 2.5",       "2.5" in calculator.invoke({"expression": "10 / 4"}))
check("sqrt(144) = 12",     "12" in calculator.invoke({"expression": "sqrt(144)"}))
check("floor(3.9) = 3",     "3" in calculator.invoke({"expression": "floor(3.9)"}))
check("div by zero handled", "zero" in calculator.invoke({"expression": "1/0"}).lower())
check("bad input handled",   "error" in calculator.invoke({"expression": "import os"}).lower()
                             or "Could not" in calculator.invoke({"expression": "import os"}))
check("(3+4)*2.5 = 17.5",   "17.5" in calculator.invoke({"expression": "(3+4)*2.5"}))

# ---- web_search tests ----
print("\n── web_search ──────────────────────────────")
from unittest.mock import patch

with patch("app.agent.DDGS") as MockDDGS:
    MockDDGS.return_value.__enter__.return_value.text.return_value = [
        {"title": "GraphRAG", "body": "Combines graphs with RAG.", "href": "https://example.com"},
    ]
    r = web_search.invoke({"query": "GraphRAG"})
    check("returns mocked result",   "GraphRAG" in r)
    check("includes link",           "example.com" in r)

with patch("app.agent.DDGS") as MockDDGS:
    MockDDGS.return_value.__enter__.return_value.text.return_value = []
    r = web_search.invoke({"query": "xyznothing"})
    check("empty results handled",   "No web results" in r)

with patch("app.agent.DDGS") as MockDDGS:
    MockDDGS.return_value.__enter__.return_value.text.side_effect = Exception("net error")
    r = web_search.invoke({"query": "test"})
    check("exception handled",       isinstance(r, str) and len(r) > 0)

# ---- TOOLS list ----
print("\n── TOOLS registry ──────────────────────────")
check("3 tools registered",          len(TOOLS) == 3)
check("tool names correct",          {t.name for t in TOOLS} == {"vector_search", "web_search", "calculator"})
check("all tools have descriptions", all(len(t.description) > 10 for t in TOOLS))

# ---- Summary ----
failed = [n for n, s in results if s == FAIL]
print(f"\n{'='*50}")
print(f"  Total: {len(results)}  Passed: {len(results)-len(failed)}  Failed: {len(failed)}")
if failed:
    print("  Failed tests:", ", ".join(failed))
    sys.exit(1)
else:
    print("  All tests passed 🎉")
