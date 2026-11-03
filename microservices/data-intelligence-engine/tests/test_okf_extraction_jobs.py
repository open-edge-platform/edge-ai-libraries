# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Extraction runs as a job beside syncing: triggers, coalescing, precedence."""
import threading

import pytest
from fastapi.testclient import TestClient

from core.knowledge.extraction_jobs import ExtractionJobs
from core.knowledge.extractor import ExternalExtractorConfig
from core.knowledge.okf import OKFNode
from core.file_asset_library import FileAssetLibrary

from .test_asset_identity import _ingest, _library_with_pool
from .test_graph_indexer import _indexer
from .test_okf_task_ingestion import TaskVector, _generated, exchange, inline_extraction_jobs  # noqa: F401


def _pool(trigger="auto"):
    library, pool, _ = _library_with_pool()
    vector = TaskVector()
    graph, adapter = _indexer({
        "asset_types": ["okf", "document"],
        "external_extractor": {"url": "http://extractor", "trigger": trigger},
    })
    library.add_source(graph.source)
    pool.set_projections([vector, graph])
    return library, pool, vector, graph, adapter


@pytest.mark.parametrize("raw,expected", [
    (None, "auto"), ("auto", "auto"), ("manual", "manual"), ({"mode": "manual"}, "manual"),
])
def test_trigger_defaults_to_auto_and_accepts_a_mode_object(raw, expected):
    options = {"url": "http://extractor"} | ({} if raw is None else {"trigger": raw})
    assert ExternalExtractorConfig.from_options(options).trigger.mode == expected


@pytest.mark.parametrize("raw,message", [
    ("hourly", "must be one of"),
    ({"mode": "auto", "cron": "x"}, "Unknown"),
    ({"mode": "manual", "debounce_seconds": 5}, "Unknown"),
    ({"mode": "auto", "debounce_seconds": -1}, "between 0"),
    ({"mode": "auto", "debounce_seconds": "soon"}, "number of seconds"),
    ("schedule", "5 fields"),
    ({"mode": "schedule", "cron": "0 25 * * *"}, "hour field"),
    ({"mode": "schedule", "cron": "0 2 * * *", "timezone": "Mars/Base"}, "time zone"),
])
def test_unsupported_triggers_are_rejected(raw, message):
    with pytest.raises(ValueError, match=message):
        ExternalExtractorConfig.from_options({"url": "http://extractor", "trigger": raw})


def test_a_sync_never_extracts_for_a_manual_source(exchange):
    library, pool, vector, graph, _ = _pool("manual")
    _ingest(library, "/host/a.pdf", "Source.")

    library.sync_asset_pool("pool")

    status = pool.source_statuses[graph.source.source_id]
    assert status.status == "ready" and status.extraction_outdated
    assert exchange.instances == [] and library.extraction_jobs.list() == []
    out = library.extraction_out(pool, status)
    assert out["trigger"] == "manual" and out["state"] == "idle" and out["outdated"]


def test_manual_extraction_runs_once_per_change_unless_forced(exchange):
    library, pool, vector, graph, adapter = _pool("manual")
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")

    job, created = library.request_extraction("pool")
    assert created and job.state == "succeeded" and job.result["outcome"] == "extracted"
    status = pool.source_statuses[graph.source.source_id]
    assert not status.extraction_outdated
    assert {vertex["id"] for vertex in adapter.vertices} == {"topic/corpus"}
    generated, _ = _generated(library, pool)
    assert job.result["bundle_asset_id"] == generated.asset_id

    again, _ = library.request_extraction("pool")
    assert again.result["outcome"] == "up_to_date" and len(exchange.instances) == 1
    forced, _ = library.request_extraction("pool", force=True)
    assert forced.result["outcome"] == "extracted" and len(exchange.instances) == 2

    _ingest(library, "/host/a.pdf", "Changed source.")
    library.sync_asset_pool("pool")
    assert pool.source_statuses[graph.source.source_id].extraction_outdated
    assert len(exchange.instances) == 2, "a manual source waits to be asked"


def test_a_request_names_the_graph_source_when_the_pool_is_ambiguous():
    library, pool, *_ = _pool()
    with pytest.raises(ValueError, match="is not a graph source extracting"):
        library.request_extraction("pool", "missing")
    pool.set_projections([TaskVector()])
    with pytest.raises(ValueError, match="has 0 graph sources"):
        library.request_extraction("pool")


def test_requests_during_a_run_coalesce_into_one_more_run(monkeypatch):
    monkeypatch.setattr(ExtractionJobs, "inline", False)
    started, release, runs = threading.Event(), threading.Event(), []

    def run(job):
        runs.append(job.extraction_id)
        started.set()
        release.wait(5)
        return {"outcome": "extracted"}

    jobs = ExtractionJobs(run)
    first, created = jobs.request("lib", "pool", "g", "manual")
    assert created and started.wait(5)
    second, created_again = jobs.request("lib", "pool", "g", "auto")
    third, _ = jobs.request("lib", "pool", "g", "auto")
    assert second is first and third is first and not created_again
    with pytest.raises(ValueError, match="cannot be cancelled"):
        jobs.cancel(first.extraction_id)
    release.set()
    for _ in range(100):
        if len(runs) == 2 and jobs.active("lib", "pool", "g") is None:
            break
        threading.Event().wait(0.05)
    assert len(runs) == 2, "one follow-up run for every request made mid-run"
    assert [job.state for job in jobs.list()] == ["succeeded", "succeeded"]


def test_a_queued_job_can_be_cancelled(monkeypatch):
    jobs = ExtractionJobs(lambda job: {})
    monkeypatch.setattr(jobs, "_submit", lambda job: None)   # never picked up
    job, _ = jobs.request("lib", "pool", "g", "manual")
    assert jobs.cancel(job.extraction_id).state == "cancelled"
    assert jobs.active("lib", "pool", "g") is None


def test_uploaded_concepts_take_precedence_over_generated_ones():
    uploaded = OKFNode(ctype="Topic", title="Corpus", body="Curated.", source_chunk_ids=["c1"],
                       links=[("person/ada", "about")])
    generated = OKFNode(ctype="Topic", title="Corpus", body="Extracted.", source_chunk_ids=["c1", "c2"],
                        links=[("person/ada", "about"), ("event/launch", "covers")])
    only_generated = OKFNode(ctype="Event", title="Launch")

    layered = FileAssetLibrary._layer_concepts(
        {"generated": [generated, only_generated], "upload": [uploaded]}, ["generated"],
    )

    corpus = layered["generated"][0]
    assert layered["upload"][0] is corpus, "every bundle writes the same vertex"
    assert corpus.body == "Curated."
    assert corpus.links == [("person/ada", "about"), ("event/launch", "covers")]
    assert corpus.source_chunk_ids == ["c1", "c2"]
    assert layered["generated"][1] is only_generated
    assert uploaded.links == [("person/ada", "about")], "parsed nodes are not mutated"


def test_an_uploaded_bundle_overrides_the_generated_concept_in_the_graph(exchange, tmp_path):
    library, pool, vector, graph, adapter = _pool()
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")
    bundle = tmp_path / "curated"
    bundle.mkdir()
    (bundle / "corpus.md").write_text("---\ntype: Topic\ntitle: Corpus\n---\nCurated summary.\n", encoding="utf-8")
    upload = library.create_okf_asset(bundle.as_uri())
    library.register_assets([upload])
    library.add_assets_to_pool("pool", [upload.asset_id])

    library.sync_asset_pool("pool")

    assert len(exchange.instances) == 1, "an uploaded bundle never triggers extraction"
    corpus = next(node for node in vector.concept_batches[-1] if node.cid == "topic/corpus")
    assert "Curated summary." in corpus.body
    assert corpus.source_chunk_ids, "the generated citations are kept"
    assert library.concept_origins("pool") == {"topic/corpus": "both"}

    # Without the upload, the generated version is rebuilt.
    library.delete_assets([upload.asset_id])
    assert pool.source_statuses[graph.source.source_id].status == "pending"
    library.sync_asset_pool("pool")
    corpus = next(node for node in vector.concept_batches[-1] if node.cid == "topic/corpus")
    assert "Curated summary." not in corpus.body
    assert library.concept_origins("pool") == {"topic/corpus": "generated"}


def test_extraction_api_queues_reports_and_reuses_jobs(monkeypatch):
    from api import asset_library as api_module
    from main import app

    library, pool, *_ = _pool("manual")
    monkeypatch.setattr(api_module, "_require", lambda name: library)
    monkeypatch.setattr(library.extraction_jobs, "_submit", lambda job: None)   # stays queued
    with TestClient(app) as client:
        base = f"/v1/libraries/{library.name}/asset_pools/pool/extractions"
        created = client.post(base, json={})
        assert created.status_code == 202 and created.json()["state"] == "queued"
        repeated = client.post(base, json={"force": True})
        assert repeated.status_code == 200
        assert repeated.json()["extraction_id"] == created.json()["extraction_id"]
        assert repeated.json()["force"] is True
        job_id = created.json()["extraction_id"]
        assert client.get(f"{base}/{job_id}").json()["state"] == "queued"
        assert [job["extraction_id"] for job in client.get(base).json()] == [job_id]
        assert client.post(base, json={"source_id": "nope"}).status_code == 400
        assert client.delete(f"{base}/{job_id}").json()["state"] == "cancelled"
        assert client.get(f"{base}/missing").status_code == 404
    graph_status = next(st for st in pool.source_statuses.values() if library.extraction_out(pool, st))
    extraction = library.extraction_out(pool, graph_status)
    assert extraction["trigger"] == "manual" and extraction["last"]["state"] == "cancelled"


def test_a_graph_source_is_created_with_the_base_classes_options():
    """`enabled` and `labels` (main's source lifecycle) pass through the
    knowledge-checking override; the API sends them for every new source."""
    from . import dbhub

    library = FileAssetLibrary("library", databasehub=dbhub.with_graph(dbhub.object_hub()))
    source = library.create_source(
        "graph", dbhub.GRAPH_DATABASE, "space",
        {"asset_types": ["okf", "document"], "external_extractor": {"url": "http://x", "trigger": "manual"}},
        enabled=False, labels={"team": "a"},
    )
    assert source.enabled is False and source.labels == {"team": "a"}
    with pytest.raises(ValueError, match="cron"):
        library.create_source("bad", dbhub.GRAPH_DATABASE, "space2", {
            "asset_types": ["okf", "document"],
            "external_extractor": {"url": "http://x", "trigger": {"mode": "schedule", "cron": "nightly"}},
        })


def test_source_api_rejects_flat_extractor_options_instead_of_silently_disabling_auto(monkeypatch):
    from fastapi import FastAPI
    from api import asset_library as api_module
    from . import dbhub

    library = FileAssetLibrary("library", databasehub=dbhub.with_graph(dbhub.object_hub()))
    monkeypatch.setattr(api_module, "_require", lambda name: library)
    app = FastAPI()
    app.include_router(api_module.router)
    with TestClient(app) as client:
        response = client.post("/v1/libraries/library/sources", json={
            "name": "graph", "database_id": dbhub.GRAPH_DATABASE, "collection_name": "space",
            "operator_options": {"url": "http://extractor", "api_key": "private-key", "timeout": 3600},
        })

    assert response.status_code == 400
    assert "operator_options.external_extractor" in response.json()["detail"]
    assert "private-key" not in response.text
    assert not library.sources


# --- step 3: debounce and schedule ----------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from core import cron  # noqa: E402
from core.knowledge import extraction_jobs as jobs_module  # noqa: E402
from core.knowledge.extraction_jobs import ExtractionScheduler  # noqa: E402


@pytest.mark.parametrize("expression,moment,expected", [
    ("0 2 * * *", datetime(2026, 1, 5, 2, 0), True),
    ("0 2 * * *", datetime(2026, 1, 5, 2, 1), False),
    ("*/15 9-17 * * 1-5", datetime(2026, 1, 5, 9, 45), True),      # a Monday
    ("*/15 9-17 * * 1-5", datetime(2026, 1, 4, 9, 45), False),     # a Sunday
    ("0 0 1 * 0", datetime(2026, 2, 1, 0, 0), True),                # the 1st...
    ("0 0 1 * 0", datetime(2026, 1, 4, 0, 0), True),                # ...or a Sunday
    ("0 0 * * 7", datetime(2026, 1, 4, 0, 0), True),                # 7 is Sunday too
    ("5,35 * * * *", datetime(2026, 1, 4, 3, 35), True),
])
def test_cron_matches_like_cron(expression, moment, expected):
    assert cron.parse(expression).matches(moment) is expected


def test_cron_next_run_and_invalid_expressions():
    tz = ZoneInfo("Asia/Shanghai")
    assert cron.parse("30 2 * * *").next_after(datetime(2026, 1, 5, 2, 30, tzinfo=tz)) == \
        datetime(2026, 1, 6, 2, 30, tzinfo=tz)
    assert cron.parse("0 0 31 2 *").next_after(datetime(2026, 1, 1)) is None
    for bad in ("* * * *", "60 * * * *", "*/0 * * * *", "a * * * *", "5-1 * * * *"):
        with pytest.raises(ValueError):
            cron.parse(bad)


def _wait_for(condition, seconds=5.0):
    for _ in range(int(seconds / 0.02)):
        if condition():
            return True
        threading.Event().wait(0.02)
    return condition()


def test_auto_requests_wait_for_quiet_then_run_once(monkeypatch):
    monkeypatch.setattr(ExtractionJobs, "inline", False)
    runs = []
    jobs = ExtractionJobs(lambda job: runs.append(job.trigger) or {"outcome": "extracted"})

    first, created = jobs.request("lib", "pool", "g", "auto", delay=0.3)
    assert created and first.not_before is not None
    for _ in range(3):                       # a bulk upload: each sync asks again
        threading.Event().wait(0.15)
        again, created = jobs.request("lib", "pool", "g", "auto", delay=0.3)
        assert again is first and not created
    assert runs == [], "still inside the quiet period"
    assert _wait_for(lambda: runs == ["auto"] and first.state == "succeeded")
    threading.Event().wait(0.4)
    assert runs == ["auto"], "one extraction for the whole burst"


def test_a_manual_request_ends_the_quiet_period(monkeypatch):
    monkeypatch.setattr(ExtractionJobs, "inline", False)
    runs = []
    jobs = ExtractionJobs(lambda job: runs.append(job.extraction_id) or {})
    waiting, _ = jobs.request("lib", "pool", "g", "auto", delay=60)
    now, created = jobs.request("lib", "pool", "g", "manual")
    assert now is waiting and not created and now.not_before is None
    assert _wait_for(lambda: runs == [waiting.extraction_id])


@pytest.fixture
def extraction_clock(monkeypatch):
    """Control deadlines without real 15/60-second waits or live timer threads."""
    clock = {"now": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    monkeypatch.setattr(ExtractionJobs, "inline", False)
    monkeypatch.setattr(jobs_module, "_later", lambda seconds: (
        clock["now"] + timedelta(seconds=seconds)
    ).isoformat())
    monkeypatch.setattr(jobs_module, "_seconds_until", lambda moment: (
        datetime.fromisoformat(moment) - clock["now"]
    ).total_seconds())
    monkeypatch.setattr(ExtractionJobs, "_arm", lambda self, job: None)
    monkeypatch.setattr(ExtractionJobs, "_submit", lambda self, job: None)
    return clock


@pytest.mark.parametrize("delay", [15, 60])
def test_unchanged_pool_syncs_do_not_restart_the_auto_quiet_period(extraction_clock, delay):
    library, pool, _, graph, _ = _pool({"mode": "auto", "debounce_seconds": delay})
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")
    first = library.extraction_jobs.list()[0]
    deadline = first.not_before
    assert datetime.fromisoformat(deadline) == extraction_clock["now"] + timedelta(seconds=delay)
    changes = pool.source_statuses[graph.source.source_id].extraction_changes

    for _ in range(3):
        extraction_clock["now"] += timedelta(seconds=5)
        library.sync_asset_pool("pool")
        assert first.not_before == deadline, "an unchanged corpus must not postpone extraction"
        assert pool.source_statuses[graph.source.source_id].extraction_changes == changes

    assert library.extraction_jobs.list() == [first]


def test_real_document_changes_extend_the_existing_auto_job(extraction_clock):
    library, _, _, _, _ = _pool({"mode": "auto", "debounce_seconds": 15})
    _ingest(library, "/host/a.pdf", "Original.")
    library.sync_asset_pool("pool")
    first = library.extraction_jobs.list()[0]
    old_deadline = first.not_before
    extraction_clock["now"] += timedelta(seconds=10)
    _ingest(library, "/host/a.pdf", "Changed.")
    library.sync_asset_pool("pool")

    assert library.extraction_jobs.list() == [first]
    assert first.not_before != old_deadline
    assert datetime.fromisoformat(first.not_before) == extraction_clock["now"] + timedelta(seconds=15)


def test_an_uploaded_okf_bundle_does_not_extend_the_document_debounce(extraction_clock, tmp_path):
    library, pool, _, graph, _ = _pool({"mode": "auto", "debounce_seconds": 15})
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")
    first = library.extraction_jobs.list()[0]
    deadline = first.not_before
    changes = pool.source_statuses[graph.source.source_id].extraction_changes
    bundle = tmp_path / "uploaded"
    bundle.mkdir()
    (bundle / "concept.md").write_text("---\ntype: Topic\ntitle: Manual\n---\nCurated concept.\n", encoding="utf-8")
    asset = library.create_okf_asset(bundle.as_uri())
    library.register_assets([asset])
    extraction_clock["now"] += timedelta(seconds=10)
    library.add_assets_to_pool("pool", [asset.asset_id])
    library.sync_asset_pool("pool")

    assert first.not_before == deadline
    assert pool.source_statuses[graph.source.source_id].extraction_changes == changes


def test_unchanged_sync_during_extraction_does_not_queue_another_auto_run(extraction_clock, monkeypatch):
    library, _, _, _, _ = _pool({"mode": "auto", "debounce_seconds": 15})
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")
    first = library.extraction_jobs.list()[0]
    extraction_clock["now"] += timedelta(seconds=15)
    library.extraction_jobs._due(first)
    monkeypatch.setattr(library.extraction_jobs, "_run", lambda job: library.sync_asset_pool("pool") or {})

    library.extraction_jobs._work(first)

    assert first.state == "succeeded"
    assert library.extraction_jobs.list() == [first], "outdated does not itself mean a newer change"


def test_failed_auto_job_can_be_retried_by_a_later_sync_without_a_new_upload(extraction_clock, monkeypatch):
    library, _, _, graph, _ = _pool({"mode": "auto", "debounce_seconds": 15})
    _ingest(library, "/host/a.pdf", "Original.")
    library.sync_asset_pool("pool")
    first = library.extraction_jobs.list()[0]
    extraction_clock["now"] += timedelta(seconds=15)
    library.extraction_jobs._due(first)

    def fail(job):
        raise TimeoutError("extractor still busy")

    monkeypatch.setattr(library.extraction_jobs, "_run", fail)
    library.extraction_jobs._work(first)
    library.sync_asset_pool("pool")
    assert first.state == "failed" and len(library.extraction_jobs.list()) == 2
    retry = library.extraction_jobs.active(library.idx, "pool", graph.source.source_id)
    assert retry is not first and retry.state == "queued"

    extraction_clock["now"] += timedelta(seconds=5)
    _ingest(library, "/host/a.pdf", "Changed.")
    library.sync_asset_pool("pool")
    assert len(library.extraction_jobs.list()) == 2
    assert library.extraction_jobs.active(library.idx, "pool", graph.source.source_id) is retry
    assert jobs_module._seconds_until(retry.not_before) == 15


@pytest.mark.parametrize("elapsed_after_change,remaining", [(5, 10), (30, 0)])
def test_follow_up_waits_only_for_the_remaining_quiet_period(extraction_clock, elapsed_after_change, remaining):
    def run(job):
        extraction_clock["now"] += timedelta(seconds=5)
        jobs.request("lib", "pool", "graph", "auto", delay=15)
        extraction_clock["now"] += timedelta(seconds=elapsed_after_change)
        return {}

    jobs = ExtractionJobs(run)
    first, _ = jobs.request("lib", "pool", "graph", "auto")
    jobs._work(first)
    follow_up = jobs.active("lib", "pool", "graph")

    assert follow_up is not None and follow_up is not first
    if remaining:
        assert jobs_module._seconds_until(follow_up.not_before) == remaining
    else:
        assert follow_up.not_before is None, "do not add another full delay after a long running job"


def test_extraction_api_exposes_the_queued_deadline(monkeypatch, extraction_clock):
    from fastapi import FastAPI
    from api import asset_library as api_module

    app = FastAPI()
    app.include_router(api_module.router)
    library, _, _, graph, _ = _pool("manual")
    monkeypatch.setattr(api_module, "_require", lambda name: library)
    job, _ = library.extraction_jobs.request(library.idx, "pool", graph.source.source_id, "auto", delay=15)
    with TestClient(app) as client:
        response = client.get(f"/v1/libraries/{library.name}/asset_pools/pool/extractions/{job.extraction_id}")

    assert response.status_code == 200
    assert response.json()["not_before"] == job.not_before


def test_deleting_a_source_cancels_its_queued_extraction_and_removes_bindings(extraction_clock):
    library, pool, _, graph, _ = _pool({"mode": "auto", "debounce_seconds": 15})
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")
    job = library.extraction_jobs.list()[0]
    source_id = graph.source.source_id

    assert library.detach_source(source_id)
    assert job.state == "cancelled"
    assert source_id not in pool.source_statuses and source_id not in library.sources
    library.extraction_jobs._due(job)
    assert job.state == "cancelled"
    library.sync_asset_pool("pool")


def test_deleting_a_source_with_running_extraction_reports_an_actionable_error(extraction_clock):
    library, pool, _, graph, _ = _pool({"mode": "auto", "debounce_seconds": 15})
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")
    job = library.extraction_jobs.list()[0]
    job.state = "running"

    with pytest.raises(ValueError, match="running OKF extraction"):
        library.detach_source(graph.source.source_id)
    assert graph.source.source_id in library.sources
    assert graph.source.source_id in pool.source_statuses


def test_schedule_fires_once_per_matching_minute_and_only_when_outdated(exchange):
    library, pool, vector, graph, adapter = _pool({"mode": "schedule", "cron": "0 2 * * *", "timezone": "Asia/Shanghai"})
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")
    assert exchange.instances == [], "a scheduled source does not extract on sync"
    out = library.extraction_out(pool, pool.source_statuses[graph.source.source_id])
    assert out["trigger"] == "schedule" and out["next_run"].endswith("+08:00")
    assert datetime.fromisoformat(out["next_run"]).hour == 2

    two_am = datetime(2026, 1, 5, 2, 0, 20, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)
    assert library.run_scheduled_extractions(two_am.replace(minute=1)) == []
    fired = library.run_scheduled_extractions(two_am)
    assert [job.trigger for job in fired] == ["schedule"] and fired[0].state == "succeeded"
    assert len(exchange.instances) == 1
    assert library.run_scheduled_extractions(two_am.replace(second=40)) == [], "once per minute"
    next_day = two_am.replace(day=6)
    assert library.run_scheduled_extractions(next_day) == [], "nothing changed since"


def test_the_scheduler_asks_every_library_and_survives_failures():
    asked = []

    class Broken:
        name = "broken"

        def run_scheduled_extractions(self, now):
            raise RuntimeError("boom")

    class Fine:
        def run_scheduled_extractions(self, now):
            asked.append(now)

    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ExtractionScheduler(lambda: [Broken(), object(), Fine()]).tick(moment)
    assert asked == [moment]


def test_a_scheduled_minute_during_a_running_job_queues_nothing(exchange, monkeypatch):
    library, pool, *_ = _pool({"mode": "schedule", "cron": "* * * * *"})
    _ingest(library, "/host/a.pdf", "Source.")
    library.sync_asset_pool("pool")
    monkeypatch.setattr(library.extraction_jobs, "_submit", lambda job: None)   # stays queued
    minute = datetime(2026, 1, 5, 2, 0, tzinfo=timezone.utc)
    first = library.run_scheduled_extractions(minute)
    assert len(first) == 1
    assert library.run_scheduled_extractions(minute.replace(minute=1)) == []
    assert library.extraction_jobs.list() == first


def _failing_jobs_with_follow_up(monkeypatch, follow_up_trigger):
    monkeypatch.setattr(ExtractionJobs, "inline", False)
    started, release, runs = threading.Event(), threading.Event(), []

    def run(job):
        runs.append(job.trigger)
        if len(runs) == 1:
            started.set()
            release.wait(5)
            raise TimeoutError("extractor too slow")
        return {"outcome": "extracted"}

    jobs = ExtractionJobs(run)
    jobs.request("lib", "pool", "g", "auto")
    assert started.wait(5)
    jobs.request("lib", "pool", "g", follow_up_trigger)
    release.set()
    _wait_for(lambda: jobs.active("lib", "pool", "g") is None and len(jobs.list()) >= 1, 3)
    threading.Event().wait(0.3)
    return jobs, runs


def test_a_failed_job_does_not_start_its_automatic_follow_up(monkeypatch):
    jobs, runs = _failing_jobs_with_follow_up(monkeypatch, "auto")
    assert runs == ["auto"] and [job.state for job in jobs.list()] == ["failed"]


def test_a_failed_job_still_runs_a_requested_follow_up(monkeypatch):
    jobs, runs = _failing_jobs_with_follow_up(monkeypatch, "manual")
    assert _wait_for(lambda: runs == ["auto", "manual"])


def test_an_uploaded_copy_of_an_engine_bundle_is_the_users_and_keeps_its_concepts(exchange, tmp_path):
    """A generated bundle downloaded and uploaded into another pool still has
    its task.json, naming documents of the pool it was extracted from. It is
    an uploaded bundle: concepts stay, provenance resolves by file name."""
    import json
    import shutil

    source_library, source_pool, *_ = _pool("auto")
    _ingest(source_library, "/elsewhere/02_theft.md", "Original pool's copy.")
    source_library.sync_asset_pool("pool")
    _, generated_folder = _generated(source_library, source_pool)
    copy = tmp_path / "intel-graph_extract-ac32a13d"
    shutil.copytree(generated_folder, copy)
    assert json.loads((copy / "task.json").read_text())["sources"][0]["asset_id"] not in ("",)

    library, pool, vector, graph, adapter = _pool("manual")
    document = _ingest(library, "/host/02_theft.md", "This pool's copy.")
    upload = library.create_okf_asset(copy.as_uri())
    library.register_assets([upload])
    library.add_assets_to_pool("pool", [upload.asset_id])
    library.sync_asset_pool("pool")

    status = pool.source_statuses[graph.source.source_id]
    assert status.status == "ready", status.error
    assert not library._is_generated_bundle(upload)
    assert library.concept_origins("pool") == {"topic/corpus": "uploaded"}
    corpus = next(node for node in vector.concept_batches[-1] if node.cid == "topic/corpus")
    assert corpus.source_chunk_ids == [f"chunk-{document.asset_id}"]


def test_a_sync_whose_bundles_resolve_to_no_concepts_skips_the_concept_index():
    """E.g. a generated bundle whose every concept cited deleted documents:
    there is nothing to index, and checking an index for no concepts would
    wrongly report it missing."""
    library, pool, vector, graph, adapter = _pool("manual")
    graph.set_okf_context({"bundle": []})
    vector.load_concept_index = lambda ids: (_ for _ in ()).throw(AssertionError("checked an empty index"))

    library._finish_projection_add(pool, graph, [])

    assert vector.concept_batches == [] and graph.okf_context is None


def _bundle(root, title):
    root.mkdir()
    (root / "index.md").write_text("# Bundle\n", encoding="utf-8")
    (root / f"{title.lower()}.md").write_text(f"---\ntype: Topic\ntitle: {title}\n---\n{title}.\n", encoding="utf-8")
    return root


def test_pools_sharing_a_graph_source_each_see_their_own_concepts(tmp_path):
    from core.retrievers import pool_concept_graph

    library, pool, vector, graph, adapter = _pool("manual")
    other = library.create_asset_pool("other", "other")
    other.set_projections([vector, graph])
    for pool_id, title in (("pool", "Mine"), ("other", "Theirs")):
        bundle = library.create_okf_asset(_bundle(tmp_path / title, title).as_uri())
        library.register_assets([bundle])
        library.add_assets_to_pool(pool_id, [bundle.asset_id])

    assert library.pool_concept_scope("pool") == {"topic/mine"}
    assert library.pool_concept_scope("other") == {"topic/theirs"}

    # The view filters the shared space down to the pool's concepts.
    class Space:
        def concept_ids(self): return {"topic/mine", "topic/theirs"}
        def neighbors(self, ids): return {cid: [] for cid in ids}
        def concept_details(self, ids): return {cid: {"label": "Topic", "title": cid} for cid in ids}

    import dataclasses
    import core.graph_search as graph_search
    from databasehub.models import GraphCollection
    graph.source = dataclasses.replace(graph.source, location=GraphCollection("space"))
    graph._adapter.existing_store = lambda space: None
    original = graph_search.NebulaConceptGraphBackend
    graph_search.NebulaConceptGraphBackend = lambda store: Space()
    try:
        view = pool_concept_graph(pool, 100, library.pool_concept_scope("pool"))
    finally:
        graph_search.NebulaConceptGraphBackend = original
    assert [node["id"] for node in view["nodes"]] == ["topic/mine"] and view["total"] == 1


def test_a_pool_with_its_own_graph_source_is_not_restricted():
    library, *_ = _pool("manual")
    assert library.pool_concept_scope("pool") is None
