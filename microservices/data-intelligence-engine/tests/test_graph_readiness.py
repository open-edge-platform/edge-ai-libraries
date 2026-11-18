# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Display readiness includes graph extraction without mutating sync state."""

import pytest

from schemas import AssetPoolOut, SourceSyncStatusOut


def _status(status="ready", extraction=None):
    return SourceSyncStatusOut(
        source_id="graph", status=status, indexed_revision=1,
        updated_at="2026-10-26T00:00:00+00:00", extraction=extraction,
    )


@pytest.mark.parametrize("extraction,expected", [
    (None, "ready"),
    ({"state": "queued", "outdated": True, "active": {"not_before": "2026-10-26T00:00:15+00:00"}}, "extraction_waiting"),
    ({"state": "queued", "outdated": True, "active": {}}, "extraction_queued"),
    ({"state": "running", "outdated": True}, "extracting"),
    ({"state": "idle", "outdated": True, "trigger": "manual"}, "extraction_pending"),
    ({"state": "idle", "outdated": True, "last": {"state": "failed"}}, "extraction_failed"),
    ({"state": "idle", "outdated": False, "bundle_asset_id": "bundle"}, "ready"),
])
def test_source_and_pool_do_not_show_ready_before_graph_is_current(extraction, expected):
    source = _status(extraction=extraction)
    pool = AssetPoolOut(id="pool", name="Pool", source_statuses=[source])

    assert source.status == "ready", "keep internal materialization state separate"
    assert source.model_dump()["display_status"] == expected
    assert pool.model_dump()["display_status"] == expected


def test_sync_failure_takes_precedence_over_a_running_extraction():
    status = _status("failed", {"state": "running", "outdated": True})
    assert status.display_status == "failed"


def test_pool_with_ready_vector_still_waits_for_graph():
    vector = _status()
    vector.source_id = "vector"
    graph = _status(extraction={"state": "running", "outdated": True})
    pool = AssetPoolOut(id="pool", name="Pool", source_statuses=[vector, graph])
    assert pool.display_status == "extracting"
    graph.extraction = {"state": "idle", "outdated": False}
    assert pool.display_status == "ready"