# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for agent-service utility modules."""

import os
import tempfile
import json
import pytest


# ── config_loader ─────────────────────────────────────────────────────────────

def test_load_config():
    from src.utility.config_loader import load_config, get_use_case_id
    cfg = {"use_case_id": "test-case", "analysis": {"min_confidence": 0.6}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        import yaml
        yaml.dump(cfg, f)
        tmp_path = f.name
    try:
        loaded = load_config(tmp_path)
        assert loaded["use_case_id"] == "test-case"
        assert get_use_case_id(loaded) == "test-case"
    finally:
        os.unlink(tmp_path)


# ── prompt_loader ─────────────────────────────────────────────────────────────

SAMPLE_PROMPT = """\
[SYSTEM]
You are an AI assistant for pipeline inspection.
Defect classes: Rupture, Deformation, Disconnect.

[POLICY]
Generate a policy based on the detection summary.

[ANALYSIS]
Provide a detailed analysis report.

[EVIDENCE]
Build a compliance audit trail.
"""


def test_get_section():
    from src.utility.prompt_loader import get_section
    text = get_section("test", "SYSTEM", prompt_text=SAMPLE_PROMPT)
    assert "pipeline inspection" in text


def test_get_section_policy():
    from src.utility.prompt_loader import get_section
    text = get_section("test", "POLICY", prompt_text=SAMPLE_PROMPT)
    assert "policy" in text.lower()


def test_get_section_missing():
    from src.utility.prompt_loader import get_section
    with pytest.raises(KeyError):
        get_section("test", "NONEXISTENT", prompt_text=SAMPLE_PROMPT)


def test_load_prompt_file(tmp_path):
    from src.utility.prompt_loader import load_prompt_file
    pf = tmp_path / "my-case.txt"
    pf.write_text(SAMPLE_PROMPT)
    text = load_prompt_file("my-case", str(tmp_path))
    assert "[SYSTEM]" in text


# ── policy_agent (fallback mode) ──────────────────────────────────────────────

def _make_fallback_file(tmp_path, data: dict) -> str:
    p = tmp_path / "policy_fallback.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_policy_agent_fallback(monkeypatch, tmp_path):
    fallback_data = {
        "thresholds": {
            "Rupture": {"alert_above": 0.7},
            "Deformation": {"alert_above": 0.8},
        }
    }
    fallback_path = _make_fallback_file(tmp_path, fallback_data)
    monkeypatch.setenv("LLM_MODE", "fallback")
    monkeypatch.setenv("FALLBACK_POLICY_PATH", fallback_path)

    summary = {
        "by_class": [
            {"label": "Rupture", "count": 5, "avg_confidence": 0.85},
            {"label": "Deformation", "count": 2, "avg_confidence": 0.6},
        ]
    }

    import importlib
    import src.utility.llm_client as lc
    importlib.reload(lc)

    import src.agents.policy_agent as pa
    monkeypatch.setattr(pa.storage_client, "get_summary", lambda: summary)
    monkeypatch.setattr(pa, "llm_client", lc)

    result = pa.run("test-case", {})
    assert result["mode"] == "fallback"
    assert any(v["label"] == "Rupture" for v in result["violations"])
    assert not any(v["label"] == "Deformation" for v in result["violations"])


# ── analysis_agent (fallback mode) ────────────────────────────────────────────

def test_analysis_agent_fallback(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "fallback")

    detections = [
        {"frame_id": 1, "label": "Rupture",    "confidence": 0.9},
        {"frame_id": 2, "label": "Rupture",    "confidence": 0.85},
        {"frame_id": 3, "label": "Disconnect", "confidence": 0.5},
    ]

    import importlib
    import src.utility.llm_client as lc
    importlib.reload(lc)

    import src.agents.analysis_agent as aa
    monkeypatch.setattr(aa, "llm_client", lc)
    monkeypatch.setattr(aa.storage_client, "get_detections", lambda **kw: detections)

    result = aa.run("test-case", {})
    assert result["mode"] == "fallback"
    assert result["total_detections"] == 3


# ── evidence_agent (fallback mode) ────────────────────────────────────────────

def test_evidence_agent_fallback(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "fallback")

    detections = [
        {"frame_id": 1, "label": "Rupture",    "confidence": 0.9},
        {"frame_id": 2, "label": "Disconnect", "confidence": 0.6},
    ]

    import importlib
    import src.utility.llm_client as lc
    importlib.reload(lc)

    import src.agents.evidence_agent as ea
    monkeypatch.setattr(ea, "llm_client", lc)
    monkeypatch.setattr(ea.storage_client, "get_detections", lambda **kw: detections)

    result = ea.run("test-case", {})
    assert result["mode"] == "fallback"
    assert 1 in result["frame_ids"]


# ── ticketing_agent (fallback mode) ───────────────────────────────────────────

def test_ticketing_agent_fallback(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "fallback")

    import importlib
    import src.utility.llm_client as lc
    importlib.reload(lc)

    import src.agents.ticketing_agent as ta
    monkeypatch.setattr(ta, "llm_client", lc)

    policy = {"violations": [{"label": "Rupture", "avg_confidence": 0.9}], "recommendation": "Halt pipeline"}
    analysis = {"total_detections": 15, "mode": "fallback"}

    result = ta.run("test-case", {}, policy, analysis)
    assert result["mode"] == "fallback"
    assert result["priority"] == "HIGH"
    assert "TICKET-" in result["ticket_id"]
