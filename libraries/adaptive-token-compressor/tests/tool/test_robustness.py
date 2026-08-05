"""Robustness — malformed / oversized inputs to ToolCompressor (ATC-UNIT-010).

Hermetic: an injected in-memory predictor means nothing here touches the
network. Contract under test: ``compress()`` never raises on shape-broken tool
schemas / messages or very large tool lists — it returns a ``CompressorResult``.

Empty tool lists and malformed *predictor responses* are already covered
(test_compressor.py / test_predictor.py); this file adds malformed *tool/message
input shapes* and oversized tool lists.
"""
from __future__ import annotations

from adaptive_token_compressor.core.base import CompressionContext, CompressorResult
from adaptive_token_compressor.tool.compressor import ToolCompressor
from adaptive_token_compressor.tool.predictor import ToolCandidate


URL = "http://localhost:8088/v1/chat/completions"


class FixedPredictor:
    """Predictor returning a fixed candidate set; never touches the network."""

    name = "fixed_predictor"

    def __init__(self, candidates=None):
        self._candidates = candidates or []

    def predict(self, task, *, system_prompt):
        return list(self._candidates), {}

    def health_check(self, *, timeout=5.0):
        from adaptive_token_compressor.core.health import HealthStatus

        return HealthStatus.healthy("fixed_predictor")


def _tool(name: str, description: str = "") -> dict:
    return {"type": "function", "function": {"name": name, "description": description}}


class TestMalformed:
    def _compressor(self, candidates=None) -> ToolCompressor:
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FixedPredictor(candidates=candidates or [])
        return comp

    def test_malformed_tool_entries_do_not_crash(self):
        comp = self._compressor(candidates=[ToolCandidate(name="get_weather", score=5)])
        tools = [
            _tool("get_weather", "ok"),
            {"type": "function"},                  # missing "function" body
            {"type": "function", "function": {}},  # function w/o name
            {"function": {"name": "no_type"}},     # missing "type"
            {"type": "not_a_function", "function": {"name": "x"}},
        ]
        ctx = CompressionContext(
            messages=[{"role": "user", "content": "weather in SF?"}], tools=tools
        )
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert isinstance(result.tools, list)

    def test_malformed_messages_with_tools_do_not_crash(self):
        comp = self._compressor(candidates=[ToolCandidate(name="get_weather", score=5)])
        ctx = CompressionContext(
            messages=[
                {"role": "user", "content": None},
                {"role": "user", "content": {"weird": "shape"}},
            ],
            tools=[_tool("get_weather", "ok")],
        )
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)


class TestOversized:
    def test_oversized_tool_list_and_descriptions(self):
        comp = ToolCompressor(predictor_url=URL)
        comp._predictor = FixedPredictor(candidates=[ToolCandidate(name="tool_0", score=5)])
        tools = [_tool(f"tool_{i}", "d" * 5_000) for i in range(1_000)]
        ctx = CompressionContext(
            messages=[{"role": "user", "content": "use tool_0 please"}], tools=tools
        )
        result = comp.compress(ctx)
        assert isinstance(result, CompressorResult)
        assert isinstance(result.tools, list)