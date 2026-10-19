# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Human-readable explanations for failed performance jobs.

Each message says what happened, why, and what to change ("To fix: ...").
Kept free of the functional-test ``helpers`` imports so it can be unit
tested on its own.
"""

from collections.abc import Iterable, Mapping
from typing import Any

_MAX_DETAIL_CHARS = 300


def job_status_url(base_url: str, job_id: str) -> str:
    return f"{base_url.rstrip('/')}/jobs/tests/performance/{job_id}/status"


def _logs_hint(base_url: str, job_id: str) -> str:
    if not job_id:
        return "the ViPPET logs"
    return (
        f"the ViPPET logs for job {job_id} (status: {job_status_url(base_url, job_id)})"
    )


def describe_job_failure(
    label: str, status: Mapping[str, Any], attempts: int, base_url: str
) -> str:
    """Explain why a job did not reach ``COMPLETED`` after all attempts."""
    state = status.get("state") or "UNKNOWN"
    job_id = str(status.get("job_id") or "")
    detail = status.get("error_message") or "ViPPET returned no error message"
    job = f" (job_id={job_id})" if job_id else ""
    what = (
        f"{label} did not complete: attempt {attempts} of {attempts} ended in "
        f"state {state}{job}: {detail}."
    )
    if state == "TIMEOUT":
        why = (
            "The job was still running when the job timeout expired, so it "
            "was stopped. To fix: allow more time with --max-job-duration / "
            "VIPPET_JOB_TIMEOUT_SECONDS, or shorten each run with "
            "--max-runtime."
        )
    elif state == "CONFLICT":
        why = (
            "ViPPET runs one job at a time and was still busy with another "
            "job. To fix: wait for the other job to finish (or stop it), then "
            "rerun; --retry-delay gives ViPPET more time between attempts."
        )
    else:
        why = (
            "ViPPET reported that the pipeline itself failed, for example "
            "because an input, model or device was not available. To fix: "
            f"check {_logs_hint(base_url, job_id)}."
        )
    return f"{what} {why}"


def describe_zero_fps(label: str, status: Mapping[str, Any], base_url: str) -> str:
    """Explain a ``COMPLETED`` job that reported no throughput."""
    job_id = str(status.get("job_id") or "")
    return (
        f"{label} completed but reported total_fps={status.get('total_fps')!r} "
        f"and per_stream_fps={status.get('per_stream_fps')!r}, so the pipeline "
        "processed no frames. To fix: check that the pipeline's input source "
        f"produces frames and look at {_logs_hint(base_url, job_id)}."
    )


def describe_rejected_submission(label: str, status_code: int, body: str) -> str:
    """Explain a non-409 HTTP error returned when submitting a job."""
    detail = " ".join(body.split())[:_MAX_DETAIL_CHARS] or "(empty response)"
    if status_code >= 500:
        why = (
            "ViPPET failed while accepting the job. To fix: check the ViPPET "
            "logs (for example 'docker compose logs vippet') and rerun."
        )
    else:
        why = (
            "ViPPET did not accept the request, for example because the "
            "pipeline or variant no longer exists or an execution setting is "
            "out of range. To fix: rerun with --dry-run to check the matrix, "
            "and review --output-mode / --max-runtime."
        )
    return (
        f"ViPPET rejected the performance job for {label} with HTTP "
        f"{status_code}: {detail}. {why}"
    )


def describe_connection_lost(label: str, base_url: str, exc: BaseException) -> str:
    """Explain a network error while submitting or polling a job."""
    return (
        f"Lost contact with ViPPET at {base_url} while running {label} "
        f"({type(exc).__name__}: {exc}). ViPPET may have stopped or restarted "
        "during the run. To fix: check 'docker compose ps' and "
        "'docker compose logs vippet', then rerun."
    )


def describe_missing_hw_samples(
    results: Iterable[Mapping[str, Any]], metrics_url: str
) -> str | None:
    """Warn when tests ran but no hardware metrics were sampled for them."""
    ran = [r for r in results if r.get("status") != "skipped"]
    empty = [r for r in ran if not (r.get("hw_metrics") or {}).get("sample_count")]
    if not empty:
        return None
    return (
        f"No hardware metrics were sampled from {metrics_url} for "
        f"{len(empty)} of {len(ran)} test(s), so the report has no "
        "utilisation or power charts for them. To fix: check that "
        "metrics-manager is running, or set --metrics-url / "
        "VIPPET_METRICS_URL to its address."
    )
