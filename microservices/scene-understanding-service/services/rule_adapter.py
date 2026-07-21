# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Rule Engine Adapter — bridges the generic rule engine with LP-specific logic.

Responsibilities:
  - Translates RegionEvent + PersonSession → flat context dict
  - Calls RuleEngine.evaluate() (pure, no side effects)
  - Translates Action results → LP-specific Alert objects, BA triggers
  - Owns session state transitions, loiter dedup, poll loop, frame cleanup
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

import structlog
from vlm_metrics_logger import (
    user_log_start_time, 
    log_end_time
)

from models.events import EventType, RegionEvent
from models.alerts import Alert
from .config import ConfigService
from .session_manager import SessionManager
from rule_engine import RuleEngine, Action
from .alert_service_client import AlertServiceClient

logger = structlog.get_logger(__name__)


@runtime_checkable
class EscalationService(Protocol):
    """Protocol for services that can be invoked by the 'escalate' action type."""
    def start(self, object_id: str, region_id: str, scene_id: str) -> None: ...
    def stop(self, object_id: str, region_id: str, scene_id: str = "") -> None: ...
    def stop_all(self, object_id: str) -> None: ...


class RuleEngineAdapter:
    """LP-specific adapter that wires the Rule Engine Service to this service."""

    def __init__(
        self,
        engine: RuleEngine,
        config: ConfigService,
        session_manager: SessionManager,
        alert_service_client: AlertServiceClient | None = None,
        frame_manager=None,
        visit_tracker=None,
    ) -> None:
        self._engine = engine
        self.config = config
        self.session_mgr = session_manager
        self._alert_client = alert_service_client
        self._frame_mgr = frame_manager
        self._visit_tracker = visit_tracker

        rules_cfg = config.get_rules_config()
        self._loiter_threshold = float(rules_cfg.get("loiter_threshold_seconds", 20))

        # Config-driven session flags: {flag_name: {trigger, zone_type, ...}}
        self._session_flag_defs = config.get_session_flag_defs()

        # Precompute zone_type → list of flag names for fast lookup on zone entry
        self._zone_visited_flags: dict[str, list[str]] = {}
        for flag_name, flag_def in self._session_flag_defs.items():
            if flag_def.get("trigger") == "zone_visited":
                zt = flag_def.get("zone_type", "")
                self._zone_visited_flags.setdefault(zt, []).append(flag_name)

        # External flag definitions: {source_name: [{flag_name, field, match_value}]}
        self._external_flags: dict[str, list[dict]] = {}
        for flag_name, flag_def in self._session_flag_defs.items():
            if flag_def.get("trigger") == "external":
                source = flag_def.get("source", "")
                self._external_flags.setdefault(source, []).append({
                    "flag_name": flag_name,
                    "field": flag_def.get("field", "status"),
                    "match_value": flag_def.get("match_value"),
                })

        # Service registry: {service_name: EscalationService}
        self._service_registry: dict[str, EscalationService] = {}

        logger.info(
            "RuleEngineAdapter initialized",
            loiter_threshold=self._loiter_threshold,
            rules_loaded=len(engine.rules),
            session_flags=list(self._session_flag_defs.keys()),
            zone_visited_flags=self._zone_visited_flags,
        )

    def set_alert_client(self, client: AlertServiceClient) -> None:
        self._alert_client = client

    def register_service(self, name: str, handler: EscalationService) -> None:
        """Register a named escalation service (e.g. 'behavioral_analysis')."""
        self._service_registry[name] = handler
        logger.info("Escalation service registered", service=name)

    # ---- main entry point (same signature as old RuleEngine.on_event) ---------

    async def on_event(self, event: RegionEvent) -> None:
        """Process a region event: update state, evaluate rules, execute actions."""
        if event.event_type == EventType.PERSON_LOST:
            await self._on_person_lost(event)
            return

        session = self.session_mgr.get_session(event.object_id, event.scene_id)
        if not session:
            return

        # ---- Config-driven state transitions (replaces hardcoded if/elif) ----
        if event.event_type == EventType.ENTERED:
            zone_type_str = event.zone_type or ""
            flag_names = self._zone_visited_flags.get(zone_type_str, [])
            for flag_name in flag_names:
                if not session.flags.get(flag_name):
                    session.flags[flag_name] = True
                    logger.info(
                        "Session flag set",
                        flag=flag_name,
                        object_id=event.object_id,
                        region=event.region_name,
                        zone_type=zone_type_str,
                    )

        elif event.event_type == EventType.EXITED:
            # Stop any escalation services that were started for this zone
            for svc in self._service_registry.values():
                svc.stop(event.object_id, event.region_id, event.scene_id)
            self._maybe_cleanup_on_exit(event)

        elif event.event_type == EventType.LOITER:          
            if session.loiter_alerted.get(event.region_id):
                return

        # ---- Map event_type to rule trigger string ----
        trigger_map = {
            EventType.ENTERED: "zone_entry",
            EventType.EXITED: "zone_exit",
            EventType.LOITER: "zone_loiter",
        }
        trigger_event = trigger_map.get(event.event_type, "zone_exit")

        # ---- Build flat context dict (no LP dataclasses leak into engine) ----
        context = self._build_context(event, session)

        # ---- Evaluate rules (local rule engine) ----
        actions = self._engine.evaluate(trigger_event, event.zone_type or "", context)

        # ---- Execute actions (LP-specific side effects) ----
        await self._execute_actions(actions, event, session, context)

    # ---- context builder -----------------------------------------------------

    @staticmethod
    def _build_context(event: RegionEvent, session) -> dict:
        """Flatten event + session into a generic dict for the rule engine.

        The same dict is later consumed by the YAML-driven ``details:``
        block on each alert action. To keep YAML authors from having to
        edit Python every time they want to expose a new field, every
        public attribute on the ``RegionEvent`` and ``PersonSession``
        dataclasses is auto-merged into the context, on top of a few
        explicitly derived helpers (rounded dwell, BA result fields,
        per-region visit_count). Session ``flags`` are spread at the top
        level so YAML can write ``$ctx.visited_high_value`` directly.

        Naming collisions are resolved in this order (later wins):
          1. session attrs   2. event attrs   3. derived helpers
          4. session.flags
        """
        ctx: dict = {}

        def _spread(obj, skip: set[str]) -> None:
            for name in dir(obj):
                if name.startswith("_") or name in skip:
                    continue
                try:
                    value = getattr(obj, name)
                except Exception:
                    continue
                if callable(value):
                    continue
                ctx[name] = value

        # Hide internal / heavy / ambiguous fields. ``object_id`` and
        # ``scene_id`` are intentionally exposed via the event so YAML
        # can read them with familiar names.
        _spread(session, skip={
            "alert_dedup", "region_visits", "camera_history",
            "frame_buffer", "current_zones",
        })
        _spread(event, skip={"event_type"})

        # Normalize zone_type to a string (it should already be one).
        zt = ctx.get("zone_type")
        ctx["zone_type"] = zt if isinstance(zt, str) else (zt or "")

        # Derived helpers / overrides.
        ctx["dwell_seconds"] = (
            round(event.dwell_seconds, 1) if event.dwell_seconds else 0
        )
        ctx["visit_count"] = session.zone_visit_counts.get(event.region_id, 0)

        ba = getattr(session, "_pending_ba_result", None) or {}
        ctx["ba_confidence"] = ba.get("confidence")
        ctx["ba_message"] = ba.get("vlm_response") or ""
        ctx["ba_frames_analyzed"] = ba.get("frames_analyzed", 0)

        # Spread dynamic session flags last so they’re reachable as
        # bare names (e.g. ``$ctx.visited_high_value``).
        ctx.update(session.flags)
        return ctx

    # ---- action execution (LP-specific) --------------------------------------

    async def _execute_actions(
        self, actions: list[Action], event: RegionEvent, session, context: dict
    ) -> list[Alert]:
        """Execute each action; return the list of alerts actually fired.

        Callers that need to attach side effects to a fired alert (e.g.
        the BA result path copying evidence frames) can inspect the
        returned alerts. Other callers may safely ignore the return.
        """
        fired: list[Alert] = []
        for action in actions:
            if action.type == "alert":
                alert = await self._execute_alert(action, event, session, context)
                if alert is not None:
                    fired.append(alert)
            elif action.type == "escalate":
                service_name = action.params.get("service", "")
                handler = self._service_registry.get(service_name)
                if handler and self._engine.is_rule_enabled(action.rule_id):
                    handler.start(
                        event.object_id, event.region_id, event.scene_id
                    )
                elif not handler:
                    logger.warning(
                        "Escalate action references unknown service",
                        service=service_name,
                        rule_id=action.rule_id,
                    )
        return fired

    async def _execute_alert(
        self, action: Action, event: RegionEvent, session, context: dict
    ) -> Alert | None:
        """Build and fire an LP Alert from a generic Action.

        ``alert_type`` and ``severity`` are taken verbatim from rules.yaml,
        so adding a new rule with a new alert_type / severity does NOT
        require editing any Python source — just YAML.
        """
        alert_type = action.params["alert_type"]
        severity = action.params.get("severity", "WARNING")

        # Generic severity escalation, driven by rules.yaml. Two forms:
        #   severity_if: <flag_name>
        #     severity_when_true: CRITICAL
        # or the legacy shorthand kept for back-compat:
        #   severity_if_concealment: CRITICAL
        sev_flag = action.params.get("severity_if")
        sev_when_true = action.params.get("severity_when_true")
        if sev_flag and sev_when_true and session.flags.get(sev_flag):
            severity = sev_when_true
        elif (
            action.params.get("severity_if_concealment")
            and session.concealment_suspected
        ):
            severity = action.params["severity_if_concealment"]

        alert_level = severity

        # ---- Generic dedup, driven by rules.yaml ----------------------------
        # Each alert action may declare ``fire_once_per: zone | session | none``.
        # ``zone``    — one alert per (alert_type, region_id) per session.
        # ``session`` — one alert per alert_type for the whole session.
        # ``none`` (default) — every match fires an alert.
        dedup_key = self._dedup_key(action.params, event)
        alert_type_str = self._alert_type_str(alert_type)
        if dedup_key is not None and session.is_alerted(alert_type_str, dedup_key):
            logger.debug(
                "Alert already fired (dedup hit)",
                alert_type=alert_type_str,
                dedup_key=dedup_key,
                object_id=event.object_id,
            )
            return None

        details = self._build_details(action.params, context)

        alert = Alert(
            alert_type=alert_type,
            alert_level=alert_level,
            object_id=event.object_id,
            timestamp=event.timestamp,
            scene_id=event.scene_id,
            region_id=event.region_id,
            region_name=event.region_name,
            details=details,
        )
        logger.warning(
            "Rule fired",
            rule_id=action.rule_id,
            alert_type=alert_type,
            level=alert_level,
            object_id=event.object_id,
            region=event.region_name,
        )

        # Mark as fired for dedup BEFORE the await on _fire_alert. Otherwise
        # concurrent events (e.g. the scene_data LOITER stream firing one
        # per frame at ~5/s) all pass the dedup gate while the first alert
        # HTTP POST is in flight, and a flood of duplicates fires.
        if dedup_key is not None:
            session.mark_alerted(alert_type_str, dedup_key)

        await self._fire_alert(alert)
        return alert

    # ---- dedup helpers -------------------------------------------------------

    @staticmethod
    def _alert_type_str(alert_type) -> str:
        """Coerce a YAML-supplied alert_type to its canonical string key."""
        return getattr(alert_type, "value", str(alert_type))

    @staticmethod
    def _dedup_key(params: dict, event: RegionEvent):
        """Resolve the dedup scope key from an alert action's params.

        Returns ``None`` when no dedup is configured (every match alerts).
        """
        scope = params.get("fire_once_per", "none")
        if scope == "zone":
            return event.region_id or "*"
        if scope == "session":
            return "*"
        return None

    @staticmethod
    def _build_details(params: dict, ctx: dict) -> dict:
        """Build the alert ``details`` dict from a YAML-driven spec.

        ``params['details']`` is a mapping ``output_key -> value``. Each
        value is one of:

        * ``$ctx.<name>``   pulls the named field from the runtime context.
        * ``$param.<name>`` pulls the named field from the action params
          (so that ``threshold`` etc. set in YAML can be echoed back).
        * any other literal scalar/dict/list is emitted verbatim.

        Adding a new alert type now just means writing the rule + a
        ``details:`` map in YAML — no Python change required.
        """
        spec = params.get("details") or {}
        out: dict = {}
        for key, value in spec.items():
            if isinstance(value, str) and value.startswith("$ctx."):
                out[key] = ctx.get(value[5:])
            elif isinstance(value, str) and value.startswith("$param."):
                out[key] = params.get(value[7:])
            else:
                out[key] = value
        return out

    # ---- PERSON_LOST handler -------------------------------------------------

    async def _on_person_lost(self, event: RegionEvent) -> None:
        """Cancel active escalation tasks and clean up all resources for this person."""
        for svc in self._service_registry.values():
            svc.stop_all(event.object_id)

        # Clean up SeaweedFS frames and in-memory key tracking.
        if self._frame_mgr:
            try:
                self._frame_mgr.cleanup_person(event.object_id, scene_id=event.scene_id)
            except Exception:
                logger.exception(
                    "cleanup_person failed on PERSON_LOST",
                    object_id=event.object_id,
                )

        # Evict all visit-tracker entries for this person so alerted visits
        # don't leak memory indefinitely.
        if self._visit_tracker is not None:
            self._visit_tracker.forget_person(event.object_id)

        logger.info("Person lost — resources cleaned up", object_id=event.object_id)

    # ---- visit-tracker driven cleanup ---------------------------------------

    @staticmethod
    def _compact_entry_ts(entry_ts_iso: str) -> str:
        """Mirror BehavioralAnalysisOrchestrator._compact_ts so visit keys
        line up between the publish side and the result side.
        """
        if not entry_ts_iso:
            return ""
        return (
            entry_ts_iso.replace(":", "")
            .replace("-", "")
            .split("+")[0]
            .split(".")[0]
        )

    def _maybe_cleanup_on_exit(self, event: RegionEvent) -> None:
        """Mark visit as exited and run cleanup if request/result counts match."""
        if self._visit_tracker is None or self._frame_mgr is None:
            return
        entry_ts_iso = getattr(event, "entry_timestamp", "") or ""
        compact = self._compact_entry_ts(entry_ts_iso)
        if not compact:
            return
        visit_key = self._visit_tracker.make_key(
            event.scene_id, event.object_id, event.region_id, compact,
        )
        self._visit_tracker.mark_exited(visit_key)
        self._maybe_drain_visit(
            visit_key, event.scene_id, event.object_id, event.region_id, compact,
        )

    def _maybe_drain_visit(
        self, visit_key, scene_id: str, person_id: str,
        region_id: str, entry_timestamp: str,
    ) -> None:
        """If the visit is fully drained (exited, counts match, not alerted)
        clean its frames from the BA bucket and forget the counters.
        """
        if (
            self._visit_tracker is None
            or self._frame_mgr is None
            or visit_key is None
        ):
            return
        if not self._visit_tracker.is_drained(visit_key):
            return
        try:
            self._frame_mgr.cleanup_visit(
                object_id=person_id,
                region_id=region_id,
                entry_timestamp=entry_timestamp,
                scene_id=scene_id,
            )
        except Exception:
            logger.exception(
                "cleanup_visit failed",
                person_id=person_id,
                region_id=region_id,
                entry_timestamp=entry_timestamp,
            )
        finally:
            self._visit_tracker.forget(visit_key)

    async def on_ba_result(self, result: dict) -> None:
        """
        Handle a BA analysis result received from the MQTT ba/results topic.
        Routes the result through the rule engine (rule: concealment_detected).
        """
        person_id = result.get("person_id", "")
        region_id = result.get("region_id", "")
        status = result.get("status", "")
        scene_id = result.get("scene_id", "")
        entry_timestamp = result.get("entry_timestamp", "")

        # Notify the orchestrator that a result arrived so it can resume
        # sending new ba/requests for this visit (cooldown gate).
        ba_orch = self._service_registry.get("behavioral_analysis")
        if ba_orch and hasattr(ba_orch, "ack_result"):
            ba_orch.ack_result(person_id, region_id, scene_id)

        # Per-visit accounting: every ba/results bumps results_received.
        if self._visit_tracker is not None and entry_timestamp:
            visit_key = self._visit_tracker.make_key(
                scene_id, person_id, region_id, entry_timestamp,
            )
            self._visit_tracker.note_result(visit_key)
        else:
            visit_key = None

        session = self.session_mgr.get_session(person_id, scene_id=scene_id)
        if not session:
            logger.debug("BA result for unknown session", person_id=person_id)
            # Still attempt drain so we don't leak counters for an exited
            # session that we've already cleaned up elsewhere.
            self._maybe_drain_visit(visit_key, scene_id, person_id, region_id, entry_timestamp)
            return

        # Quick non-actionable statuses — no rule firing needed.
        if status in ("received", "no_match", "no_enough_data"):
            logger.debug(
                "BA queue: status update",
                person_id=person_id,
                region_id=region_id,
                status=status,
            )
            self._maybe_drain_visit(visit_key, scene_id, person_id, region_id, entry_timestamp)
            return

        # Log performance metric with last_frame_ts
        last_frame_ts = result.get("last_frame_ts", "")
        if last_frame_ts:
            ts_ms = int(datetime.fromisoformat(
                last_frame_ts.replace("Z", "+00:00")
            ).timestamp() * 1000)
            user_log_start_time(ts_ms, "USECASE_1","suspcious-activity")

        # No per-zone dedup here — the BA service emits one ba/results per
        # discrete concealment event it observes, and a single visit may
        # legitimately produce multiple suspicious verdicts (e.g. two thefts
        # at adjacent shelves in the same HV zone).

        # Resolve zone metadata for the synthetic event.
        zone_name = self.config.get_zone_name(region_id)
        zone_type = self.config.get_zone_type(region_id) or "HIGH_VALUE"

        synth_event = RegionEvent(
            event_type=EventType.ENTERED,  # placeholder; engine matches on "ba_result" string
            object_id=person_id,
            region_id=region_id,
            region_name=zone_name,
            zone_type=zone_type,
            timestamp=session.last_seen,
            dwell_seconds=0.0,
            scene_id=session.scene_id,
        )        

        # Stash raw BA result so _build_details(CONCEALMENT) can pick it up.
        session._pending_ba_result = result

        # Build context the rule conditions can read. Must happen AFTER the
        # _pending_ba_result stash so _build_context picks up ba_confidence /
        # ba_message / ba_frames_analyzed from the raw result.
        context = self._build_context(synth_event, session)
        context["ba_status"] = status

        # Apply external flag definitions from config
        for flag_def in self._external_flags.get("behavioral_analysis", []):
            field_name = flag_def["field"]
            match_val = flag_def["match_value"]
            if result.get(field_name) == match_val:
                session.flags[flag_def["flag_name"]] = True

        try:
            actions = self._engine.evaluate("ba_result", zone_type, context)
            fired = await self._execute_actions(
                actions, synth_event, session, context,
            )
        finally:
            session._pending_ba_result = None

        log_end_time("USECASE_1","suspcious-activity")
        # BA-specific evidence handling: for each alert that fired in
        # response to this BA result, copy the visit's frames (up to
        # last_frame_ts) into the per-alert prefix and mark the visit as
        # alerted so its frames are excluded from cleanup.
        for alert in fired:
            self._copy_ba_evidence(result, visit_key, alert)

    # ---- BA-specific evidence handling --------------------------------------

    def _copy_ba_evidence(
        self, result: dict, visit_key, alert: Alert,
    ) -> None:
        """Copy BA-bucket frames for ``result`` under the alert's prefix.

        Marks the visit as alerted (so cleanup leaves frames in place as
        evidence) and copies frames up to ``last_frame_ts`` into
        ``alerts/{person_id}/{alert_id}/frames/``. No-op if the result
        lacks the timestamps needed to bound the copy, or if the
        frame_manager is not configured.
        """
        if not self._frame_mgr:
            return
        last_frame_ts = result.get("last_frame_ts")
        entry_timestamp = result.get("entry_timestamp")
        if not (last_frame_ts and entry_timestamp):
            return

        if self._visit_tracker is not None and visit_key is not None:
            self._visit_tracker.mark_alerted(visit_key)

        # Offload synchronous S3 list + N copies to a background thread
        # to avoid blocking the event loop (~100-400ms per alert).
        import threading

        def _do_copy():
            try:
                copied = self._frame_mgr.copy_frames_to_alert(
                    scene_id=result.get("scene_id", alert.scene_id),
                    person_id=result.get("person_id", alert.object_id),
                    region_id=result.get("region_id", alert.region_id),
                    entry_timestamp=entry_timestamp,
                    last_frame_ts=last_frame_ts,
                    alert_id=alert.alert_id,
                )
                logger.info(
                    "BA frames copied to alert prefix",
                    alert_id=alert.alert_id,
                    copied=copied,
                )
            except Exception:
                logger.exception(
                    "copy_frames_to_alert failed",
                    alert_id=alert.alert_id,
                )

        threading.Thread(target=_do_copy, daemon=True).start()

    # ---- alert dispatch ------------------------------------------------------

    async def _fire_alert(self, alert: Alert) -> None:
        """Generic alert dispatch: send to alert-service and log.

        This path is intentionally type-agnostic. Per-alert-type side
        effects (e.g. copying BA evidence frames for CONCEALMENT) live
        with the producing flow, not here.
        """
        # Send to alert-service (handles MQTT delivery with dedup)
        if self._alert_client:
            try:
                await self._alert_client.publish_alert(alert)
            except Exception:
                logger.exception("AlertService publish error", alert_id=alert.alert_id)

        logger.warning(
            "ALERT",
            alert_id=alert.alert_id,
            type=getattr(alert.alert_type, "value", alert.alert_type),
            level=getattr(alert.alert_level, "value", alert.alert_level),
            object_id=alert.object_id,
            region=alert.region_name,
            details=alert.details,
        )
