"""Shared fixtures for context/ tests.

Inputs are built in code (no data files):
  - conversation_history : a 24-msg agent conversation with 10 completed tool calls
  - tavily_payload       : a Tavily-shaped web_search result (untrusted-content
                           wrappers, Markdown images/links, nav boilerplate, URLs)
"""
from __future__ import annotations

import json

import pytest

_SENTENCES = (
    "Hot composting keeps the pile between 55 and 65 degrees Celsius for at least 3 days.",
    "A carbon to nitrogen ratio of roughly 30 to 1 is the usual starting point.",
    "Turning the pile every 7 to 10 days adds oxygen and prevents odors.",
    "A worm bin with 0.5 kg of worms can process about 0.25 kg of scraps per day.",
)


def _wrap(text: str, tag_id: str) -> str:
    return (f'\n<<<EXTERNAL_UNTRUSTED_CONTENT id="{tag_id}">>>\nSource: Web Search\n---\n'
            f'{text}\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="{tag_id}">>>')


def _noisy_snippet(i: int) -> str:
    nav = " ".join(f"[{item}](https://www.example.org/{item.lower()})"
                   for item in ("Home", "Guides", "Shop", "Blog", "About", "Contact"))
    lines = [f"Skip to main content](https://www.example.org/#). {nav}. Cookie Settings."]
    for j, sentence in enumerate(_SENTENCES):
        lines += [
            sentence,
            f"![figure {j}](https://cdn.example.net/img/compost-{i}-{j}.jpg)",
            f"* [Related guide {j}](https://www.example.org/guides/{i}/{j})",
            f"Read more: https://news.example.net/articles/{i}/{j}",
        ]
    return "\n".join(lines)


def build_tavily_payload(query: str = "home composting methods") -> dict:
    return {
        "query": query, "provider": "tavily", "count": 3, "tookMs": 1200,
        "externalContent": {"untrusted": True, "source": "web_search",
                            "provider": "tavily", "wrapped": True},
        "results": [
            {"title": _wrap(f"Composting guide part {i}", f"t{i}"),
             "url": f"https://www.example.org/composting/{i}",
             "snippet": _wrap(_noisy_snippet(i), f"s{i}"),
             "score": 0.9 - 0.1 * i}
            for i in range(3)
        ],
    }


def build_conversation() -> list[dict]:
    """system + user, 10 tool call/result pairs, final assistant + user."""
    report = "\n".join(f"<p>Section {i}: {' '.join(_SENTENCES)}</p>" for i in range(20))
    calls = [
        ("exec", {"command": "bash /workspace/collect_notes.sh"},
         "Command still running (session s1, pid 100). Use process (list/poll/log) for follow-up."),
        ("process", {"action": "poll", "sessionId": "s1"}, "(no new output)\n\nProcess still running."),
        ("process", {"action": "poll", "sessionId": "s1"}, " ".join(_SENTENCES) + "\n\nProcess exited with code 0."),
        ("web_fetch", {"url": "https://www.example.org/guide"},
         '{"status": "error", "tool": "web_fetch", "error": "fetch failed"}'),
        ("web_search", {"query": "compost methods"}, json.dumps(build_tavily_payload("compost methods"))),
        ("web_search", {"query": "compost ratio"}, json.dumps(build_tavily_payload("compost ratio"))),
        ("web_search", {"query": "worm bin setup"}, json.dumps(build_tavily_payload("worm bin setup"))),
        ("exec", {"command": "bash /workspace/extract_trial_data.sh"}, "Method: hot pile\nDays: 42"),
        ("write", {"path": "/workspace/report.html", "content": f"<html><body>\n{report}\n</body></html>"},
         "Successfully wrote the report to /workspace/report.html"),
        ("exec", {"command": "weasyprint /workspace/report.html /workspace/report.pdf"}, "(no output)"),
    ]
    messages = [
        {"role": "system", "content": "You are an assistant with read/write/exec/process/web tools."},
        {"role": "user", "content": "Write an HTML and PDF report on home composting methods."},
    ]
    for i, (name, args, result) in enumerate(calls):
        call_id = f"call_{i}"
        messages.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": call_id, "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}]})
        messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
    messages += [
        {"role": "assistant", "content": "Done. The report is saved as /workspace/report.pdf."},
        {"role": "user", "content": "Thanks."},
    ]
    return messages


@pytest.fixture
def conversation_history() -> list[dict]:
    return build_conversation()


@pytest.fixture
def tavily_payload() -> dict:
    return build_tavily_payload()


@pytest.fixture
def tavily_content(tavily_payload) -> str:
    """The Tavily payload serialized as a tool message `content` string."""
    return json.dumps(tavily_payload, ensure_ascii=False)
