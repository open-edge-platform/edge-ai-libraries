"""Reference service: Order Accuracy (walkthrough §7.1).

This is what a REAL service instance looks like. It writes only its own domain
code — event schema + read tools + act tools — and inherits the log, delivery,
 policy gate, and telemetry from mcp-service-sdk.

Signals : mismatch events, per-order accuracy score, remake rate by station.
Behaviour: read order vs prepared -> request_remake / notify_expo -> record.
Guardrails: request_remake is rate-limited; comps/refunds are human-approved.

Run as an MCP server (needs the mcp extra):
    python -m order_accuracy.service
"""

from __future__ import annotations

from mcp_service_sdk import GateLevel, ServiceServer

STORE_ID = "store-001"

svc = ServiceServer(service="order_accuracy", store_id=STORE_ID)

# -- 1. declare the event types (feeds `describe`) ------------------------
svc.register_event_type(
    "order_mismatch",
    schema={
        "order_id": "str",
        "station": "str",
        "missing_items": "list[str]",
        "extra_items": "list[str]",
        "accuracy_score": "float (0..1)",
    },
)

# -- 2. read tools (exposed broadly) --------------------------------------


@svc.read_tool(
    "rework_rate",
    description="Rework rate for a daypart, optionally filtered by station.",
    schema={"daypart": "str", "station": "str|None"},
)
def rework_rate(daypart: str, station: str | None = None) -> dict:
    events = svc.log.read(event_type="order_mismatch", limit=10_000)
    if station:
        events = [e for e in events if e.payload.get("station") == station]
    total = len(events) or 1
    remakes = sum(1 for e in events if e.payload.get("missing_items"))
    return {
        "daypart": daypart,
        "station": station or "all",
        "orders_seen": len(events),
        "rework_rate": round(remakes / total, 3),
    }


@svc.read_tool(
    "order_history",
    description="Recent mismatch events, newest last.",
    schema={"limit": "int"},
)
def order_history(limit: int = 50) -> list[dict]:
    events = svc.log.read(event_type="order_mismatch", limit=limit)
    return [{"order_id": e.payload.get("order_id"), **e.payload} for e in events]


# -- 3. act tools (narrow, gated) -----------------------------------------


@svc.act_tool(
    "request_remake",
    level=GateLevel.AUTOMATIC,
    description="Ask the line to remake an order flagged inaccurate.",
    schema={"order_id": "str", "reason": "str"},
    max_calls=5,          # rate-limited guardrail
    per_seconds=60.0,
)
def request_remake(order_id: str, reason: str) -> dict:
    return {"remake_requested": order_id, "reason": reason}


@svc.act_tool(
    "notify_expo",
    level=GateLevel.AUTOMATIC,
    description="Notify the expo station of an accuracy issue.",
    schema={"order_id": "str", "message": "str"},
)
def notify_expo(order_id: str, message: str) -> dict:
    return {"notified": "expo", "order_id": order_id, "message": message}


@svc.act_tool(
    "issue_comp",
    level=GateLevel.NEEDS_APPROVAL,  # comps/refunds always human-approved
    description="Issue a comp/refund for an order. Requires human approval.",
    schema={"order_id": "str", "amount": "float"},
)
def issue_comp(order_id: str, amount: float) -> dict:
    return {"comp_issued": order_id, "amount": amount}


def main() -> None:
    svc.run()


if __name__ == "__main__":
    main()
