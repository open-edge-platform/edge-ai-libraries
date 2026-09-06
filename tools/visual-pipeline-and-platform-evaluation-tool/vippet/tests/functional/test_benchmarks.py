"""Functional tests for the /benchmarks endpoints."""

import logging
from typing import Any

import pytest
import requests

from helpers.config import BASE_URL

logger = logging.getLogger(__name__)

type JsonDict = dict[str, Any]


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
