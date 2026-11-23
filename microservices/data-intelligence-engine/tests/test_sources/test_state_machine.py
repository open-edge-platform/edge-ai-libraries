# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The planner alone: snapshots in, transitions out."""

from assetlib.sources.binding import DEGRADE, PREPARING, SERVING
from assetlib.sources.state_machine import BindingView, on_attach, on_enabled, on_sync_result


def _states(transitions):
    return [(t.source_id, t.state) for t in transitions]


def test_a_new_binding_prepares_until_it_has_caught_up():
    views = {"new": BindingView(state=SERVING, caught_up=False)}
    assert _states(on_attach(views, newly_attached=["new"])) == [("new", PREPARING)]


def test_a_new_binding_that_already_holds_the_pool_serves_at_once():
    views = {"new": BindingView(state=SERVING, caught_up=True)}
    assert _states(on_attach(views, newly_attached=["new"])) == [("new", SERVING)]


def test_catching_up_promotes_and_finishes_the_replacement():
    views = {
        "old": BindingView(state=SERVING, caught_up=True),
        "new": BindingView(state=PREPARING, caught_up=True, replaces="old"),
    }
    transitions = on_sync_result(views)
    assert ("new", SERVING) in _states(transitions)
    assert ("old", DEGRADE) in _states(transitions)
    assert any(t.source_id == "new" and t.clear_replaces for t in transitions)


def test_nothing_moves_while_the_replacement_is_still_behind():
    views = {
        "old": BindingView(state=SERVING, caught_up=False),
        "new": BindingView(state=PREPARING, caught_up=False, replaces="old"),
    }
    assert on_sync_result(views) == []


def test_a_serving_binding_that_falls_behind_keeps_serving():
    """New assets make every source pending; that is not a reason to stop serving."""
    views = {"s": BindingView(state=SERVING, caught_up=False)}
    assert on_sync_result(views) == []


def test_a_frozen_binding_is_never_promoted():
    views = {"s": BindingView(state=PREPARING, caught_up=True, frozen=True)}
    assert on_sync_result(views) == []


def test_redeclaring_a_deprecated_source_brings_it_back_through_preparing():
    views = {
        "f16": BindingView(state=SERVING, caught_up=True),
        "f8": BindingView(state=DEGRADE, caught_up=False, replaces="f16"),
    }
    assert _states(on_attach(views, newly_attached=[], redeclared=["f8"])) == [
        ("f8", PREPARING)
    ]


def test_re_enabling_a_binding_that_fell_behind_makes_it_catch_up_first():
    views = {"s": BindingView(state=SERVING, caught_up=False)}
    assert _states(on_enabled(views, "s")) == [("s", PREPARING)]


def test_re_enabling_a_binding_that_missed_nothing_keeps_it_serving():
    views = {"s": BindingView(state=SERVING, caught_up=True)}
    assert on_enabled(views, "s") == []
