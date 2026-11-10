# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Binding state machine (PREPARING -> SERVING -> DEGRADE): which source serves a pool."""

from dataclasses import dataclass
from typing import Collection, Dict, List, Mapping, Optional

from assetlib.sources import binding
from assetlib.sources.binding import DEGRADE, PREPARING, SERVING


@dataclass(frozen=True)
class BindingView:
    """What the planner needs to know about one binding."""

    state: str
    caught_up: bool
    replaces: Optional[str] = None
    # Disabled or deprecated: takes no writes, so it can never catch up.
    frozen: bool = False


@dataclass(frozen=True)
class Transition:
    source_id: str
    state: str
    reason: str
    # Set on the binding whose pending `replaces` has just been carried out.
    clear_replaces: bool = False


def views(pool, sources: Mapping[str, object]) -> Dict[str, BindingView]:
    """A snapshot of every binding in `pool`, frozen ones included."""
    return {
        source_id: BindingView(
            state=status.serving_state,
            caught_up=binding.is_caught_up(status, pool.revision),
            replaces=status.replaces,
            frozen=binding.is_frozen(sources.get(source_id), status),
        )
        for source_id, status in pool.source_statuses.items()
    }


def on_attach(
    current: Mapping[str, BindingView],
    newly_attached: Collection[str],
    redeclared: Collection[str] = (),
) -> List[Transition]:
    """Transitions after the pool's source list changed; `redeclared` were re-named with `replaces`."""
    transitions: List[Transition] = []
    states = {source_id: view.state for source_id, view in current.items()}
    for source_id in newly_attached:
        view = current[source_id]
        if view.caught_up and not view.frozen:
            state, reason = SERVING, "attached; already holds the pool's assets"
        else:
            state, reason = PREPARING, "attached"
        transitions.append(Transition(source_id, state, reason))
        states[source_id] = state
    for source_id in redeclared:
        if states.get(source_id) == DEGRADE:
            transitions.append(
                Transition(source_id, PREPARING, "re-attached to replace a source")
            )
            states[source_id] = PREPARING
    transitions.extend(_settle(current, states))
    return transitions


def on_sync_result(current: Mapping[str, BindingView]) -> List[Transition]:
    """Transitions after a sync pass: promotions, and the replacements they finish."""
    return _settle(current, {source_id: view.state for source_id, view in current.items()})


def on_enabled(current: Mapping[str, BindingView], source_id: str) -> List[Transition]:
    """A source was switched back on: a binding that fell behind must catch up first."""
    states = {sid: view.state for sid, view in current.items()}
    transitions: List[Transition] = []
    view = current.get(source_id)
    if view is not None and view.state == SERVING and not view.caught_up:
        transitions.append(
            Transition(source_id, PREPARING, "re-enabled; catching up before serving")
        )
        states[source_id] = PREPARING
    transitions.extend(_settle(current, states))
    return transitions


def _settle(
    current: Mapping[str, BindingView], states: Dict[str, str]
) -> List[Transition]:
    """Promote whatever has caught up, then carry out the replacements it unlocks."""
    transitions: List[Transition] = []
    for source_id, view in current.items():
        if states[source_id] == PREPARING and view.caught_up and not view.frozen:
            transitions.append(Transition(source_id, SERVING, "caught up"))
            states[source_id] = SERVING
    for source_id, view in current.items():
        old = view.replaces
        if states[source_id] != SERVING or view.frozen or not old:
            continue
        if old in states and states[old] != DEGRADE:
            transitions.append(Transition(old, DEGRADE, f"replaced_by:{source_id}"))
            states[old] = DEGRADE
        transitions.append(
            Transition(source_id, SERVING, f"replaced:{old}", clear_replaces=True)
        )
    return transitions


def apply(pool, transitions: List[Transition], sources: Mapping[str, object]) -> List[str]:
    """Write `transitions` into `pool`, freezing bindings as needed; returns newly frozen source ids."""
    frozen: List[str] = []
    for item in transitions:
        status = pool.source_statuses.get(item.source_id)
        if status is None:
            continue
        binding.transition(status, item.state, item.reason)
        if item.clear_replaces:
            status.replaces = None
        if binding.is_frozen(sources.get(item.source_id), status):
            if pool.freeze(item.source_id, sources.get(item.source_id)):
                frozen.append(item.source_id)
    pool.refresh_serving()
    return frozen


__all__ = [
    "BindingView",
    "Transition",
    "apply",
    "on_attach",
    "on_enabled",
    "on_sync_result",
    "views",
]
