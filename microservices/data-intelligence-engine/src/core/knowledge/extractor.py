# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The external extractor: a REST service that turns documents into OKF bundles.

A graph source whose `operator_options.asset_types` includes ``document`` takes
documents as well as OKF bundles. The engine does not distil concepts itself; it
sends documents to an extractor service and builds the graph from the bundles
that come back. The source carries the service's access parameters:

    "operator_options": {
      "asset_types": ["okf", "document"],
      "external_extractor": {
        "url": "http://okf-extractor:8080",   # required, http(s)
        "api_key": "...",                     # optional, sent as a bearer token
        "timeout": 3600,                      # optional, seconds per request
        "options": {"language": "zh"}         # optional, passed to the service
      }
    }

"""

import hashlib
import json
import logging
import math
import mimetypes
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

#: `operator_options` key holding the extractor's access parameters.
EXTERNAL_EXTRACTOR = "external_extractor"
#: Access parameters never echoed back over the API (see `redact_operator_options`).
SECRET_KEYS = frozenset({"api_key"})
#: Seconds to wait for the extractor's (synchronous) answer: it reviews and then
#: extracts the pool's whole corpus with an LLM, which takes minutes per document.
DEFAULT_TIMEOUT = 3600.0
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_BUNDLE_FILES = 10000
MAX_ERROR_BYTES = 16384
MAX_RESULT_BYTES = 65536
TASK_DIRECTORY = "okf-extractor"
_MASK = "***"
#: When a graph source extracts its pool's documents: `auto` once document
#: changes settle, `schedule` on a cron, `manual` only when asked
#: (`POST .../extractions`).
TRIGGERS = ("auto", "schedule", "manual")
#: How long `auto` waits after the last document change, so a bulk upload is
#: one extraction rather than one per file.
DEFAULT_DEBOUNCE = 15.0
MAX_DEBOUNCE = 24 * 3600.0


@dataclass(frozen=True)
class ExtractionTrigger:
    mode: str = "auto"
    debounce_seconds: float = DEFAULT_DEBOUNCE      # auto
    cron: str = ""                                  # schedule
    timezone: str = "UTC"                           # schedule

    def schedule(self):
        """The parsed cron expression of a `schedule` trigger."""
        from core import cron

        return cron.parse(self.cron)

    def to_out(self) -> Dict[str, Any]:
        if self.mode == "auto":
            return {"mode": "auto", "debounce_seconds": self.debounce_seconds}
        if self.mode == "schedule":
            return {"mode": "schedule", "cron": self.cron, "timezone": self.timezone}
        return {"mode": self.mode}


@dataclass(frozen=True)
class ExternalExtractorConfig:
    """How to reach the extractor service."""

    url: str
    api_key: str = ""
    timeout: float = DEFAULT_TIMEOUT
    options: Dict[str, Any] = field(default_factory=dict)
    trigger: ExtractionTrigger = field(default_factory=ExtractionTrigger)

    @classmethod
    def from_options(cls, raw: Any) -> "ExternalExtractorConfig":
        """Validate `operator_options.external_extractor`; raise ValueError if unusable."""
        if not isinstance(raw, Mapping):
            raise ValueError(
                f"{EXTERNAL_EXTRACTOR} must be an object with at least a 'url' "
                "(the extractor service that turns documents into OKF bundles)"
            )
        unknown = set(raw) - {"url", "api_key", "timeout", "options", "trigger"}
        if unknown:
            raise ValueError(f"Unknown {EXTERNAL_EXTRACTOR} field(s): {', '.join(sorted(unknown))}")
        url = str(raw.get("url") or "").strip()
        try:
            parsed = urlparse(url)
            valid_url = (
                parsed.scheme in ("http", "https") and bool(parsed.hostname)
                and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment
                and parsed.port != 0
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ValueError(f"{EXTERNAL_EXTRACTOR}.url must be an http(s) URL, got {url!r}")
        try:
            timeout = float(raw.get("timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            raise ValueError(f"{EXTERNAL_EXTRACTOR}.timeout must be a number of seconds") from None
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(f"{EXTERNAL_EXTRACTOR}.timeout must be finite and positive")
        options = raw.get("options") or {}
        if not isinstance(options, Mapping):
            raise ValueError(f"{EXTERNAL_EXTRACTOR}.options must be an object")
        return cls(url=url.rstrip("/"), api_key=str(raw.get("api_key") or ""),
                   timeout=timeout, options=dict(options),
                   trigger=_trigger(raw.get("trigger", "auto")))


def _trigger(raw: Any) -> ExtractionTrigger:
    """`"auto"` / `"manual"`, or an object:
    ``{"mode": "auto", "debounce_seconds": 60}``,
    ``{"mode": "schedule", "cron": "0 2 * * *", "timezone": "Asia/Shanghai"}``."""
    name = f"{EXTERNAL_EXTRACTOR}.trigger"
    fields = dict(raw) if isinstance(raw, Mapping) else {"mode": raw}
    mode = fields.get("mode")
    if mode not in TRIGGERS:
        raise ValueError(f"{name} must be one of {', '.join(TRIGGERS)}, got {mode!r}")
    allowed = {"auto": {"debounce_seconds"}, "schedule": {"cron", "timezone"}, "manual": set()}[mode]
    unknown = set(fields) - allowed - {"mode"}
    if unknown:
        raise ValueError(f"Unknown {name} field(s) for {mode!r}: {', '.join(sorted(unknown))}")
    if mode == "auto":
        try:
            debounce = float(fields.get("debounce_seconds", DEFAULT_DEBOUNCE))
        except (TypeError, ValueError):
            raise ValueError(f"{name}.debounce_seconds must be a number of seconds") from None
        if not math.isfinite(debounce) or not 0 <= debounce <= MAX_DEBOUNCE:
            raise ValueError(f"{name}.debounce_seconds must be between 0 and {MAX_DEBOUNCE:.0f}")
        return ExtractionTrigger("auto", debounce_seconds=debounce)
    if mode == "schedule":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        trigger = ExtractionTrigger(
            "schedule", cron=str(fields.get("cron") or ""),
            timezone=str(fields.get("timezone") or "UTC"),
        )
        try:
            trigger.schedule()
        except ValueError as error:
            raise ValueError(f"{name}.cron: {error}") from None
        try:
            ZoneInfo(trigger.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"{name}.timezone is not a known time zone: {trigger.timezone!r}") from None
        return trigger
    return ExtractionTrigger("manual")


class ExternalExtractor:
    """Submit metadata over HTTP and exchange files through ENGINE_UPLOAD_DIR."""

    def __init__(self, config: ExternalExtractorConfig):
        self.config = config

    def extract(self, assets: Sequence[Any], output_dir: Optional[Path] = None) -> List[Path]:
        """Stage inputs under the shared upload root and POST relative paths.

        The response is JSON naming the completed bundle in the same shared
        folder; no file bytes or archives are transferred over HTTP. A caller
        supplying `output_dir` receives a validated, atomically published cache
        directory. Otherwise the bundle remains under the shared task folder.
        """
        if not assets:
            return []
        import config

        if len({str(getattr(asset, "asset_id", "")) for asset in assets}) != len(assets):
            raise ValueError("An extraction task cannot contain duplicate asset IDs")
        shared_dir = Path(config.UPLOAD_DIR).resolve()
        task_id = uuid4().hex
        task_dir = _shared_path(shared_dir, f"{TASK_DIRECTORY}/{task_id}")
        task_dir.mkdir(parents=True)
        submitted = False
        completed = False
        try:
            items = [_stage_item(asset, shared_dir, task_dir) for asset in assets]
            task = {"task_id": task_id, "items": items, "options": self.config.options}
            headers = {"Accept": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            logger.info(
                "Submitting OKF task %s to %s: %d document(s), %s bytes; waiting up to %.0fs",
                task_id, self.config.url, len(items),
                sum((shared_dir / item["file_path"]).stat().st_size for item in items),
                self.config.timeout,
            )
            with httpx.Client(timeout=self.config.timeout, trust_env=False) as client:
                submitted = True
                with _timeout_explained(task_id, self.config.timeout), client.stream(
                    "POST", f"{self.config.url}/v1/tasks", json=task, headers=headers,
                ) as response:
                    if not response.is_success:
                        detail = _service_error_detail(response)
                        if self.config.api_key:
                            detail = detail.replace(self.config.api_key, _MASK)
                        message = f"OKF task {task_id} failed (HTTP {response.status_code}): {detail}"
                        logger.error("%s", message)
                        raise httpx.HTTPStatusError(
                            message, request=response.request, response=response,
                        )
                    if response.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                        raise ValueError("Extractor service must return JSON with a shared bundle_path")
                    payload = bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        payload.extend(chunk)
                        if len(payload) > MAX_RESULT_BYTES:
                            raise ValueError("Extractor result exceeds the metadata size limit")
                    try:
                        result = json.loads(payload)
                    except ValueError:
                        raise ValueError("Extractor returned invalid JSON result metadata") from None
            expected = f"{TASK_DIRECTORY}/{task_id}/bundle"
            if not isinstance(result, dict) or result.get("task_id") != task_id or result.get("bundle_path") != expected:
                raise ValueError("Extractor returned an unexpected task ID or shared bundle_path")
            bundle = _shared_path(shared_dir, expected)
            _validate_bundle(bundle)
            # Keep the submitted source->asset mapping authoritative locally.
            (bundle / "task.json").write_text(json.dumps({
                "task_id": task_id,
                "sources": [{"path": item["path"], "asset_id": item["asset_id"]} for item in items],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            destination = bundle
            if output_dir is not None:
                base = Path(output_dir).resolve()
                if base == task_dir or task_dir in base.parents:
                    raise ValueError("output_dir cannot be inside the shared extraction task directory")
                base.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix=".okf-cache-", dir=base) as temporary:
                    candidate = Path(temporary) / "bundle"
                    # A local move (or filesystem copy across mounts), never an
                    # HTTP download. Publish the cache folder only when complete.
                    shutil.move(str(bundle), candidate)
                    destination = base / f"{task_id}.okf"
                    candidate.rename(destination)
            completed = True
            logger.info("Extracted %d document(s) into shared OKF bundle %s", len(assets), destination)
            return [destination]
        finally:
            if not submitted or (completed and output_dir is not None):
                shutil.rmtree(task_dir, ignore_errors=True)
            elif completed:
                shutil.rmtree(task_dir / "sources", ignore_errors=True)
            # After timeouts the remote process may still be reading these
            # files. Failed/interrupted task inputs are retained for diagnosis
            # and must not be removed until the service is no longer running.


@contextmanager
def _timeout_explained(task_id: str, timeout: float):
    """A read timeout means the extractor is still working, not that it failed."""
    try:
        yield
    except httpx.ReadTimeout:
        raise TimeoutError(
            f"OKF task {task_id} did not finish within {timeout:.0f}s "
            f"({EXTERNAL_EXTRACTOR}.timeout). The extractor may still be working on it; "
            "raise the timeout for a corpus this size."
        ) from None


def _service_error_detail(response: httpx.Response) -> str:
    """Read bounded streamed errors, retaining reasons but not validation inputs.

    `raise_for_status()` alone loses the service's JSON detail; calling `.json()`
    before reading a streaming response raises ResponseNotRead. FastAPI schema
    errors can echo entire source documents under `input`, so select only their
    locations and messages instead of dumping the response object into logs.
    """
    payload = bytearray()
    for chunk in response.iter_bytes(chunk_size=4096):
        payload.extend(chunk[:MAX_ERROR_BYTES - len(payload)])
        if len(payload) >= MAX_ERROR_BYTES:
            break
    text = payload.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        detail = parsed.get("detail", parsed.get("error"))
        if isinstance(detail, list):
            messages = []
            for item in detail[:10]:
                if not isinstance(item, dict):
                    continue
                location = item.get("loc")
                path = ".".join(map(str, location)) if isinstance(location, (list, tuple)) else "task"
                messages.append(f"{path}: {item.get('msg', 'validation failed')}")
            text = "; ".join(messages) or "Task validation failed"
        elif isinstance(detail, str):
            text = detail
        elif isinstance(detail, dict) and isinstance(detail.get("message"), str):
            text = detail["message"]
        else:
            text = "The extractor returned an error without a recognized detail"
    return " ".join(text.split())[:4000] or response.reason_phrase


def _stage_item(asset: Any, shared_dir: Path, task_dir: Path) -> Dict[str, Any]:
    """Prefer persisted ContentStreams; an origin URI is provenance, not content."""
    asset_id = str(getattr(asset, "asset_id", "") or "")
    if not asset_id:
        raise ValueError("Extraction needs an asset_id for every document")
    origin = str(getattr(asset, "origin", "") or "")
    name = str(getattr(asset, "file_name", "") or Path(unquote(urlparse(origin).path)).name)
    name = re.sub(r'[\\/:\x00-\x1f]', "-", name).lstrip(".") or "document.txt"
    name = name.encode("utf-8")[:240].decode("utf-8", errors="ignore")
    if name == "__files__":
        name = "document.txt"
    identity = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:24]
    # Name a shared upload by where it is stored (`<library-id>/02_theft.md`) so
    # extractor logs and OKF `source_files` are recognizable; anything else gets
    # an asset-derived folder, which keeps duplicate basenames distinct.
    source = _upload_name(origin, shared_dir) or f"{identity}/{name}"
    item: Dict[str, Any] = {
        "path": source, "asset_id": asset_id,
        "media_type": str(getattr(asset, "media_type", "") or mimetypes.guess_type(name)[0] or ""),
    }
    directory = task_dir / "sources" / identity
    directory.mkdir(parents=True)
    stored = directory / ("source" + Path(name).suffix)
    text = None
    has_content = hasattr(type(asset), "content") or "content" in getattr(asset, "__dict__", {})
    if has_content:
        content = asset.content
        if isinstance(content, str):
            text = content
        elif isinstance(content, bytes):
            stored.write_bytes(content)
        elif callable(getattr(content, "ordered", None)):
            text = "\n\n".join(
                str(block.text or block.caption) for block in content.ordered()
                if block.text or block.caption
            )
        else:
            raise ValueError(f"Asset {asset_id!r} has unsupported extraction content")
    else:
        # Existing shared uploads are referenced in place. File-only assets
        # outside that root are copied into the per-task staging directory.
        parsed = urlparse(origin)
        if parsed.scheme not in ("", "file") or parsed.netloc not in ("", "localhost"):
            raise ValueError(f"Asset {asset_id!r} has no extractable content")
        path = Path(unquote(parsed.path))
        if not path.is_file():
            raise ValueError(f"Asset {asset_id!r} has no extractable content")
        if path.is_absolute() and path.is_relative_to(shared_dir):
            stored = _shared_path(shared_dir, path.relative_to(shared_dir).as_posix())
        else:
            shutil.copyfile(path, stored)
    if text is not None:
        if not text.strip():
            raise ValueError(f"Asset {asset_id!r} has no textual content for OKF extraction")
        stored = directory / "content.txt"
        stored.write_text(text, encoding="utf-8")
        item["media_type"] = "text/plain"
    item["file_path"] = stored.relative_to(shared_dir).as_posix()
    return item


def _upload_name(origin: str, shared_dir: Path) -> Optional[str]:
    """The upload-relative path of a `file:` origin, if the extractor accepts it."""
    parsed = urlparse(origin)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    path = Path(unquote(parsed.path))
    if not path.is_absolute() or not path.is_relative_to(shared_dir):
        return None
    relative = path.relative_to(shared_dir).as_posix()
    parts = PurePosixPath(relative).parts
    if (
        not parts or parts[0] == TASK_DIRECTORY or len(relative) > 1024
        or any(part.startswith(".") or part == "__files__" or len(part.encode("utf-8")) > 255
               for part in parts)
        or "\\" in relative or ":" in relative or any(ord(char) < 32 for char in relative)
    ):
        return None
    return relative


def _shared_path(root: Path, relative: str) -> Path:
    """Resolve service-controlled names only inside the configured upload root."""
    path = PurePosixPath(relative)
    if (
        not path.parts or path.is_absolute() or path.as_posix() != relative
        or any(part.startswith(".") for part in path.parts)
        or "\\" in relative or ":" in relative or any(ord(char) < 32 for char in relative)
    ):
        raise ValueError("Extractor returned an unsafe shared path")
    target = root
    for part in path.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError("Symlinks are not allowed in shared extraction paths")
    return target


def _validate_bundle(bundle: Path) -> None:
    """Validate directory contents before publishing them into the engine cache."""
    if not bundle.is_dir():
        raise ValueError("Extractor bundle is missing from the shared upload directory; check the shared mount")
    total = 0
    count = 0
    concepts = 0
    pending = [bundle]
    while pending:
        for path in pending.pop().iterdir():
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                total += info.st_size
                if path.suffix == ".md" and path.name != "index.md":
                    concepts += 1
            else:
                raise ValueError("Extractor bundle contains a symlink, hard link or non-regular file")
            count += 1
            if count > MAX_BUNDLE_FILES or total > MAX_BUNDLE_BYTES:
                raise ValueError("Extractor bundle exceeds the size/file limit")
    if not (bundle / "index.md").is_file() or not concepts:
        raise ValueError("Extractor returned no OKF concept files or bundle index")


def redact_operator_options(options: Mapping[str, Any]) -> Dict[str, Any]:
    """A source's options as reported: extractor credentials masked."""
    redacted = dict(options)
    extractor = redacted.get(EXTERNAL_EXTRACTOR)
    if isinstance(extractor, Mapping):
        redacted[EXTERNAL_EXTRACTOR] = {
            key: (_MASK if key in SECRET_KEYS and value else value)
            for key, value in extractor.items()
        }
    return redacted


__all__ = [
    "EXTERNAL_EXTRACTOR",
    "ExternalExtractor",
    "ExternalExtractorConfig",
    "redact_operator_options",
]
