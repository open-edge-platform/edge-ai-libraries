"""API route coverage check for the VIPPET functional test suite.

This module verifies that every HTTP endpoint declared in the live OpenAPI spec
has been called at least once during the current pytest session.  Because it
relies on calls accumulated by the shared ``http_client`` fixture (see
``conftest.py``), it **must execute after all other test files** – the ``z_``
prefix in the filename guarantees that when pytest collects tests in
alphabetical order.

When to run
-----------
Run it as part of the full test suite::

    make test-full

Excluded routes
---------------
Routes listed in ``_COVERAGE_EXCLUDED_ROUTES`` are known to require special
hardware or a specific runtime environment that is not available in the
standard test setup (e.g. a physical camera for ONVIF profile discovery).
They are deliberately skipped by this check.  **Any new exclusion must include
an inline comment explaining why it cannot be covered by an automated test.**
"""

import logging
import re

import pytest
import requests

from helpers.config import BASE_URL

logger = logging.getLogger(__name__)

# Routes intentionally excluded from the coverage check.
# Only add entries here when a route genuinely cannot be exercised without
# special hardware / environment that is not present in the standard CI setup.
_COVERAGE_EXCLUDED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        # Example: ("POST", "/cameras/{camera_id}/profiles"),  # Requires a physical network camera.
    }
)


def _openapi_path_to_regex(openapi_path: str) -> str:
    """Convert an OpenAPI path template to a regex that matches concrete URLs.

    ``{param}`` placeholders are replaced with ``[^/]+`` so that a single path
    segment is matched.  The result is anchored at both ends.

    Examples::

        "/cameras/{camera_id}"  →  "^/cameras/[^/]+$"
        "/health"               →  "^/health$"
    """
    pattern = re.sub(r"\{[^}]+\}", "[^/]+", openapi_path)
    return f"^{pattern}$"


def _collect_http_routes(spec: dict) -> list[tuple[str, str]]:
    """Return ``(METHOD, path)`` pairs for all standard HTTP endpoints in *spec*."""
    http_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    routes: list[tuple[str, str]] = []
    for path, methods in spec.get("paths", {}).items():
        for method in methods:
            if method.upper() in http_methods:
                routes.append((method.upper(), path))
    return routes


def _route_was_called(
    method: str,
    openapi_path: str,
    recorded_calls: set[tuple[str, str]],
    api_base: str,
) -> bool:
    """Return True if the route was called at least once in *recorded_calls*.

    Matching strategy:
    1. Strip *api_base* (e.g. ``http://localhost/api/v1``) from each recorded URL.
    2. Compare the resulting path against the regex derived from *openapi_path*.
    """
    pattern = re.compile(_openapi_path_to_regex(openapi_path))
    for rec_method, rec_url in recorded_calls:
        if rec_method != method:
            continue
        if not rec_url.startswith(api_base):
            continue
        recorded_path = rec_url[len(api_base) :]
        if pattern.match(recorded_path):
            return True
    return False


def test_all_api_endpoints_called_at_least_once(
    http_client: requests.Session,
    recorded_api_calls: set[tuple[str, str]],
) -> None:
    """Assert that every HTTP endpoint in the OpenAPI spec was called at least once.

    The check is intentionally broad: it does not care *which* test called the
    endpoint or whether the call was a happy-path or error scenario.  The sole
    goal is to act as a safety net so that newly added or renamed routes do not
    silently fall through the functional test suite without any coverage.

    Routes listed in ``_COVERAGE_EXCLUDED_ROUTES`` are skipped.

    Failure message
    ---------------
    When the test fails it prints the full list of uncovered ``METHOD /path``
    pairs, making it straightforward to identify which endpoints need attention.
    """
    response = http_client.get(f"{BASE_URL}/openapi.json", timeout=30)
    assert response.status_code == 200, (
        f"Could not fetch OpenAPI spec from {BASE_URL}/openapi.json: "
        f"HTTP {response.status_code} – {response.text}"
    )
    spec = response.json()

    all_routes = _collect_http_routes(spec)
    api_base = BASE_URL.rstrip("/")

    uncovered: list[tuple[str, str]] = []
    for method, path in all_routes:
        if (method, path) in _COVERAGE_EXCLUDED_ROUTES:
            logger.debug("Skipping excluded route: %s %s", method, path)
            continue
        if not _route_was_called(method, path, recorded_api_calls, api_base):
            uncovered.append((method, path))

    if uncovered:
        lines = "\n".join(f"  {m} {p}" for m, p in sorted(uncovered))
        pytest.fail(
            f"{len(uncovered)} API endpoint(s) were never called during this test run:\n"
            f"{lines}\n\n"
            "Add functional test coverage for the missing endpoint(s), or—if the "
            "endpoint cannot be exercised in the standard CI environment—add it to "
            "_COVERAGE_EXCLUDED_ROUTES in test_z_api_coverage.py with a comment "
            "explaining why."
        )
    else:
        logger.info(
            "API coverage check passed: all %d route(s) were called at least once "
            "(%d route(s) intentionally excluded).",
            len(all_routes) - len(_COVERAGE_EXCLUDED_ROUTES),
            len(_COVERAGE_EXCLUDED_ROUTES),
        )
