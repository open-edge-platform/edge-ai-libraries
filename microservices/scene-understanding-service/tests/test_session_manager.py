# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for SessionManager — region event handling and session lifecycle."""

import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from models.events import EventType
from services.session_manager import SessionManager


class FakeConfig:
    """Minimal ConfigService stub for testing."""

    def get_rules_config(self):
        return {"session_timeout_seconds": 5}

    def get_cameras(self):
        return []

    def get_zones(self):
        return {
            "region-electronics": {"name": "Electronics", "type": "HIGH_VALUE"},
            "region-checkout": {"name": "Checkout", "type": "CHECKOUT"},
            "region-exit": {"name": "Exit", "type": "EXIT"},
            "region-stockroom": {"name": "Stockroom", "type": "RESTRICTED"},
        }

    def get_zone_type(self, region_id):
        z = self.get_zones().get(region_id)
        return z["type"] if z else None

    def get_zone_name(self, region_id):
        z = self.get_zones().get(region_id)
        return z["name"] if z else None

    def get_scene_id(self):
        return None

    def get_accepted_scene_ids(self):
        return set()


@pytest.fixture
def config():
    return FakeConfig()


@pytest.fixture
def manager(config):
    return SessionManager(config)


@pytest.mark.asyncio
async def test_region_enter_fires_entered(manager):
    """A region event with 'entered' fires ENTERED event."""
    events = []

    async def collect(e):
        events.append(e)

    manager.register_event_handler(collect)

    data = {
        "entered": [{"id": "42", "visibility": ["cam1"]}],
        "exited": [],
    }
    await manager.on_region_event("scene1", "region-electronics", data)

    assert len(events) == 1
    assert events[0].event_type == EventType.ENTERED
    assert events[0].zone_type == "HIGH_VALUE"
    assert events[0].object_id == "42"


@pytest.mark.asyncio
async def test_region_exit_fires_exited(manager):
    """A region event with 'exited' fires EXITED event with dwell."""
    events = []

    async def collect(e):
        events.append(e)

    manager.register_event_handler(collect)

    # Enter first
    enter_data = {
        "entered": [{"id": "42", "visibility": ["cam1"]}],
        "exited": [],
    }
    await manager.on_region_event("scene1", "region-electronics", enter_data)

    # Exit
    exit_data = {
        "entered": [],
        "exited": [{"object": {"id": "42"}, "dwell": 5.2}],
    }
    await manager.on_region_event("scene1", "region-electronics", exit_data)

    assert len(events) == 2
    assert events[1].event_type == EventType.EXITED
    assert events[1].dwell_seconds == 5.2


@pytest.mark.asyncio
async def test_unknown_region_ignored(manager):
    """Regions not in zone_config produce no events."""
    events = []

    async def collect(e):
        events.append(e)

    manager.register_event_handler(collect)

    data = {
        "entered": [{"id": "99", "visibility": ["cam1"]}],
        "exited": [],
    }
    await manager.on_region_event("scene1", "unknown-region", data)

    # Session created but no event emitted (unknown zone)
    assert len(events) == 0


@pytest.mark.asyncio
async def test_session_tracks_current_zones(manager):
    """Entering a region updates current_zones on the session."""
    events = []

    async def collect(e):
        events.append(e)

    manager.register_event_handler(collect)

    data = {
        "entered": [{"id": "42", "visibility": ["cam1"]}],
        "exited": [],
    }
    await manager.on_region_event("scene1", "region-electronics", data)

    session = manager.get_session("42", scene_id="scene1")
    assert session is not None
    assert "region-electronics" in session.current_zones
    assert session.zone_visit_counts["region-electronics"] == 1
