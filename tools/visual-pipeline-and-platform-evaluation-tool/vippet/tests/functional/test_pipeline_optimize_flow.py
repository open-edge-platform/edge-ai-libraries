"""Functional test covering pipeline optimization flows."""

import logging
import re

import pytest
import requests

from helpers.api_helpers import (
    JsonDict,
    fetch_devices,
    start_optimization_job,
    wait_for_job_completion,
)
from helpers.config import BASE_URL
from helpers.pipeline_case_helpers import (
    SUPPORTED_DEVICE_FAMILIES,
    skip_if_pipeline_models_missing,
)

logger = logging.getLogger(__name__)


PIPELINE_ID = "smart-parking"

# Functional cases cover a device-named variant ("cpu" -> optimizer search
# restricted to CPU) and a non-device variant ("gpu_npu" -> optimizer keeps
# default scope). The optimizer runs on DL Streamer Pipeline Server.
OPTIMIZATION_CASES = [
    (
        "optimize-cpu-variant",
        "cpu",
        {
            "type": "optimize",
            "parameters": {"search_duration": 10, "sample_duration": 3},
        },
    ),
    (
        "optimize-non-device-variant",
        "gpu-npu",
        {
            "type": "optimize",
            "parameters": {"search_duration": 10, "sample_duration": 3},
        },
    ),
]


def _required_families_for_variant(variant_id: str) -> set[str]:
    """Return device families a variant id encodes (e.g. ``gpu-npu`` -> {GPU, NPU}).

    Variant identifiers may use either ``_`` or ``-`` as separators
    (e.g. ``gpu_npu`` or ``gpu-npu``); both are accepted.

    Only families listed in :data:`SUPPORTED_DEVICE_FAMILIES` are
    returned; unknown tokens are ignored so the function never asks for
    something the host could not advertise.
    """
    tokens = {part.upper() for part in re.split(r"[-_]", variant_id) if part}
    return tokens & SUPPORTED_DEVICE_FAMILIES


@pytest.mark.full
@pytest.mark.parametrize(
    "case_id,variant_id,payload",
    OPTIMIZATION_CASES,
    ids=[c[0] for c in OPTIMIZATION_CASES],
)
def test_pipeline_optimize_flow(
    http_client: requests.Session,
    case_id: str,
    variant_id: str,
    payload: JsonDict,
) -> None:
    required = _required_families_for_variant(variant_id)
    if required:
        available: set[str] = {
            (device.get("device_family") or "").upper()
            for device in fetch_devices(http_client)
        } & SUPPORTED_DEVICE_FAMILIES
        missing = required - available
        if missing:
            pytest.skip(
                f"Variant '{variant_id}' requires device families {sorted(required)} "
                f"but the host only advertises {sorted(available)}; "
                f"missing: {sorted(missing)}"
            )

    # Also skip if the pipeline references models that are not installed.
    skip_if_pipeline_models_missing(http_client, PIPELINE_ID)

    logger.info(
        "Running pipeline optimize flow case '%s' on variant '%s'",
        case_id,
        variant_id,
    )
    job_id = start_optimization_job(http_client, PIPELINE_ID, variant_id, payload)
    status_url = f"{BASE_URL}/jobs/optimization/{job_id}/status"
    final_status = wait_for_job_completion(
        http_client,
        status_url,
        assert_initial_running=False,
    )

    assert final_status.get("state") == "COMPLETED", (
        f"Job {job_id} finished in unexpected state {final_status.get('state')}"
    )
    assert final_status.get("error_message") is None, (
        f"Job {job_id} returned error message: {final_status.get('error_message')}"
    )


@pytest.mark.smoke
def test_preprocess_optimization_type_is_rejected(
    http_client: requests.Session,
) -> None:
    """The deprecated preprocess type is rejected with 400 and creates no job."""
    response = http_client.post(
        f"{BASE_URL}/pipelines/{PIPELINE_ID}/variants/cpu/optimize",
        json={"type": "preprocess", "parameters": None},
        timeout=30,
    )

    assert response.status_code == 400, (
        f"Expected 400 for preprocess optimization, "
        f"got {response.status_code}, body={response.text}"
    )
    assert "preprocess" in response.json().get("message", ""), response.text
