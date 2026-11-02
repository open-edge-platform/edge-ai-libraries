"""Functional tests for the /benchmarks endpoints."""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import requests
from helpers.api_helpers import start_benchmark_suite_run, wait_for_job_completion
from helpers.config import BASE_URL, BENCHMARK_SUITE_POLL_TIMEOUT_SECONDS, PROJECT_ROOT

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]

# Local sqlite file backing the running backend (see compose.yml's
# `./shared/db:/db` mount). Used only to trim test-case counts for the
# run-list tests below; the shared YAML catalog is never touched.
_BENCHMARK_DB_PATH = PROJECT_ROOT / "shared" / "db" / "app.db"
# Backup preserves trimmed test cases even if a test run is interrupted.
_BENCHMARK_DB_BACKUP_PATH = PROJECT_ROOT / "shared" / "db" / "app_test.db"
_FULL_RUN_STREAM_COUNTS = (1, 4)


@contextmanager
def _shrink_suite_to_streams(
    suite_slug: str, streams: tuple[int, ...] = _FULL_RUN_STREAM_COUNTS
) -> Iterator[None]:
    """Temporarily keep one CPU workload at *streams* for *suite_slug*.

    Keeps run-list tests fast without depending on every hardware variant.
    The backend reads this same sqlite file, so the delete must be committed
    for it to take effect; removed rows are restored from the backup on exit
    without discarding benchmark runs created during the test.
    """
    if not _BENCHMARK_DB_PATH.is_file():
        logger.warning(
            "Benchmark DB not found at %s; running suite %s with its full "
            "seeded stream matrix",
            _BENCHMARK_DB_PATH,
            suite_slug,
        )
        yield
        return

    if _BENCHMARK_DB_BACKUP_PATH.exists():
        pytest.skip(
            f"Found leftover benchmark DB backup at {_BENCHMARK_DB_BACKUP_PATH}; "
            "a previous test run likely crashed before restoring it. Restore "
            "the deleted benchmark_test_cases rows from that backup manually, "
            "then remove the backup file before re-running."
        )

    placeholders = ",".join("?" for _ in streams)
    with sqlite3.connect(_BENCHMARK_DB_PATH) as conn:
        workload = conn.execute(
            f"""
            SELECT btc.workload_id
            FROM benchmark_test_cases btc
            JOIN benchmark_workloads bw ON bw.id = btc.workload_id
            JOIN benchmark_suites bs ON bs.id = bw.suite_id
            WHERE bs.slug = ? AND btc.variant_id = 'cpu'
              AND btc.streams IN ({placeholders})
            GROUP BY btc.workload_id
            HAVING COUNT(DISTINCT btc.streams) = ?
            ORDER BY btc.workload_id
            LIMIT 1
            """,
            (suite_slug, *streams, len(streams)),
        ).fetchone()
        assert workload is not None, (
            f"Suite {suite_slug!r} has no CPU workload with streams={streams}"
        )
        workload_id = workload[0]
        with sqlite3.connect(_BENCHMARK_DB_BACKUP_PATH) as backup:
            conn.backup(backup)
    try:
        with sqlite3.connect(_BENCHMARK_DB_PATH) as conn:
            conn.execute(
                f"""
                DELETE FROM benchmark_test_cases
                WHERE NOT (workload_id = ? AND variant_id = 'cpu'
                           AND streams IN ({placeholders}))
                  AND workload_id IN (
                      SELECT bw.id FROM benchmark_workloads bw
                      JOIN benchmark_suites bs ON bs.id = bw.suite_id
                      WHERE bs.slug = ?
                  )
                """,
                (workload_id, *streams, suite_slug),
            )
            conn.commit()
        logger.info(
            "Shrunk suite %s to CPU workload %s streams=%s (backed up to %s)",
            suite_slug,
            workload_id,
            streams,
            _BENCHMARK_DB_BACKUP_PATH,
        )

        yield
    finally:
        with sqlite3.connect(_BENCHMARK_DB_BACKUP_PATH) as backup:
            rows = backup.execute(
                f"""
                SELECT id, workload_id, variant_id, streams
                FROM benchmark_test_cases
                                WHERE NOT (workload_id = ? AND variant_id = 'cpu'
                                                     AND streams IN ({placeholders}))
                  AND workload_id IN (
                      SELECT bw.id FROM benchmark_workloads bw
                      JOIN benchmark_suites bs ON bs.id = bw.suite_id
                      WHERE bs.slug = ?
                  )
                """,
                (workload_id, *streams, suite_slug),
            ).fetchall()
        with sqlite3.connect(_BENCHMARK_DB_PATH) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO benchmark_test_cases "
                "(id, workload_id, variant_id, streams) VALUES (?, ?, ?, ?)",
                rows,
            )
        _BENCHMARK_DB_BACKUP_PATH.unlink()
        logger.info("Restored benchmark DB for suite %s from backup", suite_slug)


def test_shrink_suite_restores_cases_without_erasing_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    monkeypatch.setattr("test_benchmarks._BENCHMARK_DB_PATH", db_path)
    monkeypatch.setattr(
        "test_benchmarks._BENCHMARK_DB_BACKUP_PATH", tmp_path / "app_test.db"
    )
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE benchmark_suites (id INTEGER PRIMARY KEY, slug TEXT);
            CREATE TABLE benchmark_workloads (id INTEGER PRIMARY KEY, suite_id INTEGER);
            CREATE TABLE benchmark_test_cases (
                id INTEGER PRIMARY KEY, workload_id INTEGER, variant_id TEXT, streams INTEGER
            );
            CREATE TABLE benchmark_suite_runs (id INTEGER PRIMARY KEY, job_id TEXT);
            INSERT INTO benchmark_suites VALUES (1, 'suite');
            INSERT INTO benchmark_workloads VALUES (1, 1);
            INSERT INTO benchmark_workloads VALUES (2, 1);
            INSERT INTO benchmark_test_cases VALUES
                (1, 1, 'cpu', 1), (2, 1, 'cpu', 4), (3, 1, 'cpu', 8),
                (4, 1, 'gpu', 1), (5, 2, 'cpu', 1);
            """
        )

    with _shrink_suite_to_streams("suite"):
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT id FROM benchmark_test_cases").fetchall() == [
                (1,),
                (2,),
            ]
            conn.execute("INSERT INTO benchmark_suite_runs VALUES (1, 'new-job')")

    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT id FROM benchmark_test_cases ORDER BY id"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,)]
        assert conn.execute("SELECT job_id FROM benchmark_suite_runs").fetchall() == [
            ("new-job",)
        ]


def _fetch_benchmark_suites(session: requests.Session) -> list[JsonDict]:
    """Return benchmark suites from GET /benchmarks."""
    response = session.get(f"{BASE_URL}/benchmarks", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /benchmarks, got {response.status_code}, "
        f"body={response.text}"
    )
    payload = response.json()
    assert isinstance(payload, list), "Benchmark suites response must be a list"
    return payload


def _find_any_benchmark_suite(session: requests.Session) -> JsonDict:
    suites = _fetch_benchmark_suites(session)
    assert suites, "Benchmark suites endpoint returned an empty list"
    suite = suites[0]
    assert isinstance(suite.get("slug"), str) and suite["slug"], (
        "Benchmark suite must include a non-empty slug"
    )
    return suite


@pytest.mark.smoke
def test_get_benchmarks_returns_seeded_suites(
    http_client: requests.Session,
) -> None:
    """Calls GET /benchmarks and asserts seeded benchmark suites are returned."""
    suites = _fetch_benchmark_suites(http_client)

    assert suites, "Benchmark suites endpoint returned an empty list"
    for suite in suites:
        assert isinstance(suite, dict), "Each benchmark suite must be an object"
        assert isinstance(suite.get("slug"), str) and suite["slug"], (
            "Benchmark suite has missing or empty slug"
        )
        assert isinstance(suite.get("name"), str) and suite["name"], (
            "Benchmark suite has missing or empty name"
        )
        assert isinstance(suite.get("workloads"), list), (
            "Benchmark suite workloads must be a list"
        )

    logger.info("Benchmarks endpoint returned %d suite(s)", len(suites))


@pytest.mark.smoke
def test_get_all_benchmark_runs_returns_list(
    http_client: requests.Session,
) -> None:
    """Calls GET /benchmarks/runs and asserts the response is a list."""
    response = http_client.get(f"{BASE_URL}/benchmarks/runs", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /benchmarks/runs, got {response.status_code}, "
        f"body={response.text}"
    )
    assert isinstance(response.json(), list), "Benchmark runs response must be a list"


@pytest.mark.smoke
def test_get_benchmark_suite_by_slug_returns_suite(
    http_client: requests.Session,
) -> None:
    """Fetches a seeded suite by slug and asserts the returned slug matches."""
    suite = _find_any_benchmark_suite(http_client)
    suite_slug = suite["slug"]

    response = http_client.get(f"{BASE_URL}/benchmarks/{suite_slug}", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 for GET /benchmarks/{suite_slug}, "
        f"got {response.status_code}, body={response.text}"
    )
    payload = response.json()
    assert payload.get("slug") == suite_slug, (
        f"Returned benchmark suite slug does not match requested slug={suite_slug!r}"
    )
    assert isinstance(payload.get("workloads"), list), (
        "Benchmark suite detail workloads must be a list"
    )


@pytest.mark.smoke
def test_run_benchmark_suite_for_nonexistent_slug_returns_400(
    http_client: requests.Session,
) -> None:
    """Calls POST /benchmarks/{suite_slug}/run with a non-existent suite slug."""
    suite_slug = "does-not-exist"

    response = http_client.post(f"{BASE_URL}/benchmarks/{suite_slug}/run", timeout=30)

    assert response.status_code == 400, (
        f"Expected 400 for unknown benchmark suite slug={suite_slug!r}, "
        f"got {response.status_code}, body={response.text}"
    )
    assert "message" in response.json(), "Error response must contain 'message'"


@pytest.mark.smoke
def test_get_benchmark_suite_runs_returns_list(
    http_client: requests.Session,
) -> None:
    """Calls GET /benchmarks/{suite_slug}/runs and asserts the response is a list."""
    suite = _find_any_benchmark_suite(http_client)
    suite_slug = suite["slug"]

    response = http_client.get(f"{BASE_URL}/benchmarks/{suite_slug}/runs", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 for GET /benchmarks/{suite_slug}/runs, "
        f"got {response.status_code}, body={response.text}"
    )
    assert isinstance(response.json(), list), (
        "Benchmark suite runs response must be a list"
    )


@pytest.mark.smoke
def test_benchmark_run_detail_endpoints_return_404_for_missing_run(
    http_client: requests.Session,
) -> None:
    """Calls benchmark run detail endpoints with a missing run id.

    These endpoints require historical benchmark execution data for a 200 path.
    The seeded suite plus a guaranteed-missing run id exercises the route and
    validates the stable not-found contract without starting a benchmark job.
    """
    suite = _find_any_benchmark_suite(http_client)
    suite_slug = suite["slug"]
    missing_run_id = 0
    missing_test_run_id = 0

    detail_response = http_client.get(
        f"{BASE_URL}/benchmarks/{suite_slug}/run/{missing_run_id}", timeout=30
    )
    assert detail_response.status_code == 404, (
        f"Expected 404 for missing benchmark run id={missing_run_id}, "
        f"got {detail_response.status_code}, body={detail_response.text}"
    )

    csv_response = http_client.get(
        f"{BASE_URL}/benchmarks/{suite_slug}/run/{missing_run_id}/csv", timeout=30
    )
    assert csv_response.status_code == 404, (
        f"Expected 404 for missing benchmark run CSV id={missing_run_id}, "
        f"got {csv_response.status_code}, body={csv_response.text}"
    )

    test_run_response = http_client.get(
        f"{BASE_URL}/benchmarks/{suite_slug}/run/"
        f"{missing_run_id}/test/{missing_test_run_id}",
        timeout=30,
    )
    assert test_run_response.status_code == 404, (
        f"Expected 404 for missing benchmark test run id={missing_test_run_id}, "
        f"got {test_run_response.status_code}, body={test_run_response.text}"
    )


@pytest.mark.full
def test_get_benchmark_suite_runs_returns_populated_list_after_run(
    http_client: requests.Session,
) -> None:
    """After running a suite, GET /benchmarks/{suite_slug}/runs returns a populated list."""
    suite = _find_any_benchmark_suite(http_client)
    suite_slug = suite["slug"]

    with _shrink_suite_to_streams(suite_slug):
        job_id = start_benchmark_suite_run(http_client, suite_slug)
        status_url = f"{BASE_URL}/jobs/tests/benchmark/{job_id}/status"
        final_status = wait_for_job_completion(
            http_client,
            status_url,
            assert_initial_running=False,
            timeout_seconds=BENCHMARK_SUITE_POLL_TIMEOUT_SECONDS,
        )

    assert final_status.get("state") == "COMPLETED", (
        f"Benchmark job {job_id} finished in unexpected state "
        f"{final_status.get('state')}: {final_status.get('error_message')}"
    )

    response = http_client.get(f"{BASE_URL}/benchmarks/{suite_slug}/runs", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 for GET /benchmarks/{suite_slug}/runs, "
        f"got {response.status_code}, body={response.text}"
    )
    runs = response.json()
    assert isinstance(runs, list), "Benchmark suite runs response must be a list"
    assert runs, "Expected at least one run after starting a benchmark suite job"

    matching_runs = [run for run in runs if run.get("job_id") == job_id]
    assert matching_runs, (
        f"Expected a run with job_id={job_id!r} in {[r.get('job_id') for r in runs]}"
    )
    run = matching_runs[0]
    assert run.get("suite_slug") == suite_slug, (
        f"Expected run suite_slug={suite_slug!r}, got {run.get('suite_slug')!r}"
    )
    assert (
        isinstance(run.get("total_test_cases"), int) and run["total_test_cases"] > 0
    ), "Populated benchmark run must report a positive total_test_cases"


@pytest.mark.full
def test_get_all_benchmark_runs_returns_populated_list_after_run(
    http_client: requests.Session,
) -> None:
    """After running a suite, GET /benchmarks/runs includes the new run."""
    suite = _find_any_benchmark_suite(http_client)
    suite_slug = suite["slug"]

    with _shrink_suite_to_streams(suite_slug):
        job_id = start_benchmark_suite_run(http_client, suite_slug)
        status_url = f"{BASE_URL}/jobs/tests/benchmark/{job_id}/status"
        final_status = wait_for_job_completion(
            http_client,
            status_url,
            assert_initial_running=False,
            timeout_seconds=BENCHMARK_SUITE_POLL_TIMEOUT_SECONDS,
        )

    assert final_status.get("state") == "COMPLETED", (
        f"Benchmark job {job_id} finished in unexpected state "
        f"{final_status.get('state')}: {final_status.get('error_message')}"
    )

    response = http_client.get(f"{BASE_URL}/benchmarks/runs", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /benchmarks/runs, got {response.status_code}, "
        f"body={response.text}"
    )
    runs = response.json()
    assert isinstance(runs, list), "Benchmark runs response must be a list"
    assert runs, "Expected /benchmarks/runs to be populated after starting a job"

    job_ids = [run.get("job_id") for run in runs]
    assert job_id in job_ids, (
        f"Expected job_id={job_id!r} in all-suite runs list: {job_ids}"
    )
