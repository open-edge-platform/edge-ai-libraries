# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Manual pool-local stop/resume, independent of CLI replacements."""

import asyncio
from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from api import asset_library as source_api
from assetlib.sources.binding import DEGRADE, PREPARING, SERVING
from assetlib.sources.updates import SourceRuleError
from schemas import SourceServingStateUpdate
from tests.test_sources.fakes import Library, add_source, ingest, serving_ids, state


@pytest.fixture
def library():
    library = Library()
    for source_id in ("old", "other"):
        add_source(library, source_id)
    for pool_id in ("A", "B"):
        library.create_asset_pool(pool_id, pool_id, source_configurations=[
            {"source_id": "old"}, {"source_id": "other"},
        ])
        ingest(library, pool_id, "a")
        library.sync_asset_pool(pool_id)
    return library


def test_deprecating_keeps_data_binding_and_other_pools(library):
    pool = library.asset_pools["A"]
    before = deepcopy(library.store)
    source_record = deepcopy(library.sources["old"].to_record())
    progress = deepcopy(pool.source_statuses["old"].indexed_asset_ids)

    assert library.set_source_serving_state("A", "old", DEGRADE) == []

    assert state(library, "A", "old") == DEGRADE
    assert state(library, "B", "old") == SERVING
    assert serving_ids(library, "A") == ["other"]
    assert set(serving_ids(library, "B")) == {"old", "other"}
    assert "old" in pool.frozen_sources
    assert all(p.source.source_id != "old" for p in pool.projections)
    assert pool.source_statuses["old"].indexed_asset_ids == progress
    assert pool.source_statuses["old"].serving_history[-1]["reason"] == "manually deprecated"
    assert library.sources["old"].to_record() == source_record
    assert library.store == before


def test_resuming_ready_binding_serves_without_replacing_anyone(library):
    library.set_source_serving_state("A", "old", DEGRADE)
    builds = len(library.builds)

    assert library.set_source_serving_state("A", "old", SERVING) == []

    assert len(library.builds) == builds + 1
    assert state(library, "A", "old") == SERVING
    assert set(serving_ids(library, "A")) == {"old", "other"}
    assert not library.asset_pools["A"].frozen_sources
    assert all(status.replaces is None for status in library.asset_pools["A"].source_statuses.values())


def test_resuming_behind_binding_prepares_then_serves_alongside_other_sources(library):
    library.set_source_serving_state("A", "old", DEGRADE)
    ingest(library, "A", "new")
    library.sync_asset_pool("A")
    assert library.store["c_old"] == {"a"}

    assert library.set_source_serving_state("A", "old", SERVING) == ["A"]
    assert state(library, "A", "old") == PREPARING
    assert serving_ids(library, "A") == ["other"]
    library.sync_asset_pool("A")

    assert state(library, "A", "old") == SERVING
    assert set(serving_ids(library, "A")) == {"old", "other"}
    assert library.store["c_old"] == {"a", "new"}
    assert state(library, "B", "old") == SERVING


def test_a_failed_resume_leaves_the_binding_untouched(library, monkeypatch):
    library.set_source_serving_state("A", "old", DEGRADE)
    before = deepcopy(library.to_record())
    pool = library.asset_pools["A"]
    projections = pool.projections
    monkeypatch.setattr(library, "build_projection", Mock(side_effect=RuntimeError("model missing")))

    with pytest.raises(RuntimeError, match="model missing"):
        library.set_source_serving_state("A", "old", SERVING)

    assert library.to_record() == before
    assert pool.projections == projections
    assert serving_ids(library, "A") == ["other"]
    assert "old" in pool.frozen_sources


@pytest.mark.parametrize("requested", [SERVING, DEGRADE])
def test_setting_the_current_state_is_idempotent(library, monkeypatch, requested):
    library.set_source_serving_state("A", "old", requested)
    before = deepcopy(library.to_record())
    build = Mock(side_effect=AssertionError("no rebuild"))
    monkeypatch.setattr(library, "build_projection", build)

    assert library.set_source_serving_state("A", "old", requested) == []
    assert library.to_record() == before
    build.assert_not_called()


def test_all_bindings_may_be_deprecated_without_detaching_or_deleting_data(library):
    for source_id in ("old", "other"):
        library.set_source_serving_state("A", source_id, DEGRADE)

    assert serving_ids(library, "A") == []
    assert set(library.asset_pools["A"].source_statuses) == {"old", "other"}
    assert library.store == {"c_old": {"a"}, "c_other": {"a"}}


def test_manual_deprecation_survives_restore_without_loading_that_binding(library):
    library.set_source_serving_state("A", "old", DEGRADE)
    # Remove the other pool so its same source cannot mask a model load.
    library.remove_asset_pool("B")
    restored = Library(store=library.store)

    restored.restore(library.to_record())

    assert restored.builds == ["other"]
    assert state(restored, "A", "old") == DEGRADE
    assert serving_ids(restored, "A") == ["other"]


@pytest.mark.parametrize("source_id", ["old", "new"])
def test_pending_cli_replacement_is_not_implicitly_modified(library, source_id):
    add_source(library, "new")
    library.set_asset_pool_sources("A", [
        {"source_id": "old"}, {"source_id": "other"}, {"source_id": "new", "replaces": "old"},
    ])
    before = deepcopy(library.to_record())

    with pytest.raises(SourceRuleError, match="pending replacement"):
        library.set_source_serving_state("A", source_id, DEGRADE)

    assert library.to_record() == before


def test_a_disabled_source_cannot_be_resumed_by_one_pool(library):
    library.set_source_serving_state("A", "old", DEGRADE)
    library.update_source("old", enabled=False)

    with pytest.raises(SourceRuleError, match="Enable"):
        library.set_source_serving_state("A", "old", SERVING)

    assert state(library, "A", "old") == DEGRADE
    assert not library.sources["old"].enabled


def test_preparing_is_computed_not_a_user_target(library):
    with pytest.raises(SourceRuleError, match="Choose SERVING or DEGRADE"):
        library.set_source_serving_state("A", "old", PREPARING)


def test_resuming_a_failed_binding_queues_catchup_and_preserves_progress(library):
    library.set_source_serving_state("A", "old", DEGRADE)
    ingest(library, "A", "new")
    status = library.asset_pools["A"].source_statuses["old"]
    status.mark_failed("previous write failed")
    progress = list(status.indexed_asset_ids)

    assert library.set_source_serving_state("A", "old", SERVING) == ["A"]

    assert status.serving_state == PREPARING
    assert status.status == "pending"  # UI polls while the background retry runs.
    assert status.indexed_asset_ids == progress
    assert status.error == "previous write failed"
    library.sync_asset_pool("A")
    assert status.serving_state == SERVING
    assert status.status == "ready"
    assert status.error is None


def test_deprecation_during_a_sync_is_not_promoted_back_to_serving(library):
    pool = library.asset_pools["A"]
    projection = next(p for p in pool.projections if p.source.source_id == "old")
    add = projection.add

    def deprecate_mid_add(assets):
        library.set_source_serving_state("A", "old", DEGRADE)
        return add(assets)

    projection.add = deprecate_mid_add
    ingest(library, "A", "new")
    library.sync_asset_pool("A")

    assert state(library, "A", "old") == DEGRADE
    assert serving_ids(library, "A") == ["other"]


@pytest.fixture
def http_library(library, monkeypatch):
    registry = Mock()
    registry.get.side_effect = lambda name: library if name == "library" else None
    monkeypatch.setattr(source_api, "registry", registry)
    app = FastAPI()
    app.include_router(source_api.router)
    with TestClient(app) as client:
        yield client, registry


URL = "/v1/libraries/library/asset_pools/A/sources/old"


def test_http_stop_resume_changes_only_the_named_binding(library, http_library):
    client, registry = http_library
    response = client.patch(URL, json={"serving_state": DEGRADE})
    assert response.status_code == 200, response.text
    status = next(item for item in response.json()["source_statuses"] if item["source_id"] == "old")
    assert status["serving_state"] == status["effective_state"] == DEGRADE
    ingest(library, "A", "new")

    response = client.patch(URL, json={"serving_state": SERVING})
    assert response.status_code == 200, response.text
    status = next(item for item in response.json()["source_statuses"] if item["source_id"] == "old")
    assert status["serving_state"] == PREPARING  # before background catch-up
    assert state(library, "A", "old") == SERVING  # TestClient runs background tasks
    assert state(library, "A", "other") == SERVING
    assert state(library, "B", "old") == SERVING
    assert registry.save.call_count >= 2


@pytest.mark.parametrize("payload", [{"serving_state": PREPARING}, {"serving_state": "DISABLED"},
    {"serving_state": "garbage"}, {"serving_state": SERVING, "replaces": "other"}, {}])
def test_http_state_target_validation_is_atomic(library, http_library, payload):
    client, registry = http_library
    before = deepcopy(library.to_record())

    response = client.patch(URL, json=payload)

    assert response.status_code == 422, response.text
    assert library.to_record() == before
    registry.save.assert_not_called()


@pytest.mark.parametrize("url", [URL.replace("/A/", "/missing/"), URL + "-missing",
    URL.replace("/library/", "/missing/")])
def test_http_missing_binding_is_404(http_library, url):
    client, registry = http_library
    assert client.patch(url, json={"serving_state": DEGRADE}).status_code == 404
    registry.save.assert_not_called()


def test_http_resume_failure_is_503_and_retains_deprecated_binding(library, http_library, monkeypatch):
    client, registry = http_library
    library.set_source_serving_state("A", "old", DEGRADE)
    before = deepcopy(library.to_record())
    monkeypatch.setattr(library, "build_projection", Mock(side_effect=RuntimeError("model missing")))

    response = client.patch(URL, json={"serving_state": SERVING})

    assert response.status_code == 503
    assert "model missing" in response.json()["detail"]
    assert library.to_record() == before
    registry.save.assert_not_called()


def test_api_resuming_behind_binding_schedules_catchup(library, monkeypatch):
    registry = Mock()
    registry.get.return_value = library
    monkeypatch.setattr(source_api, "registry", registry)
    library.set_source_serving_state("A", "old", DEGRADE)
    ingest(library, "A", "new")
    tasks = BackgroundTasks()

    asyncio.run(source_api.set_source_serving_state(
        "library", "A", "old", SourceServingStateUpdate(serving_state=SERVING), tasks,
    ))

    assert state(library, "A", "old") == PREPARING
    assert len(tasks.tasks) == 1