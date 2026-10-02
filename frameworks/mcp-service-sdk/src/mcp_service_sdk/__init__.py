"""mcp-service-sdk — shared contract library for Central QSR Agent services.

Every service (real pipeline or simulator) presents the same contract to the
agent: emit an event -> durable log -> expose describe/subscribe/read/act.

The core is domain-agnostic. Services import it and add only their own event
schemas plus read/act tools.
"""

from .envelope import EventEnvelope, new_event
from .log import DurableLog, SQLiteLog, JSONLFileLog
from .delivery import Delivery, Sink, WebhookSink, EventHubSink, DisabledSink
from .policy import PolicyGate, PolicyDecision, ActionSpec, GateLevel
from .telemetry import Telemetry, NullTelemetry, MetricsBackend, Span
from .server import ServiceServer, ServiceConfig

__all__ = [
    "EventEnvelope",
    "new_event",
    "DurableLog",
    "SQLiteLog",
    "JSONLFileLog",
    "Delivery",
    "Sink",
    "WebhookSink",
    "EventHubSink",
    "DisabledSink",
    "PolicyGate",
    "PolicyDecision",
    "ActionSpec",
    "GateLevel",
    "Telemetry",
    "NullTelemetry",
    "MetricsBackend",
    "Span",
    "ServiceServer",
    "ServiceConfig",
]

__version__ = "0.2.0"
