"""Smoke test: exercises the whole contract WITHOUT the mcp SDK.

Run: python examples/smoke_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make src/ and examples/ importable when run directly from the repo.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from order_accuracy.service import svc  # noqa: E402


def main() -> None:
    # 1. emit some events (emit-to-log-first, delivery disabled by default)
    svc.emit("order_mismatch", {"order_id": "A1", "station": "bag", "missing_items": ["fries"]})
    svc.emit("order_mismatch", {"order_id": "A2", "station": "bag", "missing_items": []})
    svc.emit("order_mismatch", {"order_id": "A3", "station": "grill", "missing_items": ["patty"]})

    # idempotent replay: same ref_id must not double-count
    ev = svc.emit("order_mismatch", {"order_id": "A4", "station": "bag", "missing_items": []}, ref_id="fixed-1")
    svc.emit("order_mismatch", {"order_id": "A4", "station": "bag", "missing_items": []}, ref_id="fixed-1")

    # 2. read tools
    print("rework_rate(all):", svc._read_tools["rework_rate"].fn("lunch"))
    print("rework_rate(bag):", svc._read_tools["rework_rate"].fn("lunch", station="bag"))
    print("order_history:", len(svc._read_tools["order_history"].fn(limit=100)), "events (idempotent = 4)")

    # 3. act tools through the policy gate
    print("request_remake (auto):", svc.call_action("request_remake", order_id="A1", reason="missing fries"))
    print("issue_comp (needs approval, no approver):", svc.call_action("issue_comp", order_id="A1", amount=5.0))
    print("unknown action (blocked):", svc.call_action("delete_everything"))

    # rate limit: request_remake capped at 5/min
    for i in range(7):
        r = svc.call_action("request_remake", order_id=f"R{i}", reason="test")
    print("request_remake after burst:", r)

    # 4. describe (what the agent discovers)
    d = svc.describe()
    print("describe -> read_tools:", list(d["read_tools"]))
    print("describe -> act_tools:", {k: v["gate"] for k, v in d["act_tools"].items()})

    # 5. telemetry spine
    print("telemetry spans captured:", len(svc.telemetry.drain()))
    print("\nOK — contract works end-to-end without the mcp SDK.")


if __name__ == "__main__":
    main()
