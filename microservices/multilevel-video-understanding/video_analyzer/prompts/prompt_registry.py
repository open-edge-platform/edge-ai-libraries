# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""In-memory + on-disk registry of dynamic video summary tasks.

Responsibilities
----------------
1. Parse a Python-module-style `content` string into four named prompt sections.
2. Apply smart auto-fill scaffolding when users omit required placeholders.
3. Hard-validate task name, render-smoke-test, and structural invariants.
4. Persist each task as `{cache_dir}/tasks/{name}.json` with atomic writes.
5. Expose a thread-safe CRUD surface to the REST handlers.

The registry is a module-level singleton; see `get_registry()`.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import tempfile
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from video_analyzer.prompts.prompt_base import BasePrompt
from video_analyzer.prompts.prompt_dynamic import DynamicPrompt
from video_analyzer.core.settings import settings
from video_analyzer.schemas.summarization import TASKNAME

logger = logging.getLogger(__name__)


# ----- anchor + placeholder spec -----
# Order matters: determines the order sections are reconstituted in `content`.
ANCHOR_NAMES = (
    "GLOBAL_PROMPT",
    "MACRO_CHUNK_PROMPT",
    "LOCAL_PROMPT",
    "T_MINUS_1_PROMPT",
)
ANCHOR_TO_KEY = {
    "GLOBAL_PROMPT":    "global",
    "MACRO_CHUNK_PROMPT": "macro",
    "LOCAL_PROMPT":     "local",
    "T_MINUS_1_PROMPT": "t_minus",
}
KEY_TO_ANCHOR = {v: k for k, v in ANCHOR_TO_KEY.items()}

REQUIRED_PLACEHOLDERS = {
    "global":  set(),
    "macro":   {"st_tm", "end_tm"},
    "local":   {"st_tm", "end_tm"},
    "t_minus": {"dur", "st_tm", "end_tm", "past_summary"},
}

# ----- reference template returned with every parse error -----
REFERENCE_TEMPLATE = """\
GLOBAL_PROMPT = '''
...
'''

MACRO_CHUNK_PROMPT = '''
...
'''

LOCAL_PROMPT = '''
...
'''

T_MINUS_1_PROMPT = '''
...
'''
"""

# ----- URL fetch safeguards -----
MAX_URL_BYTES = 256 * 1024
URL_TIMEOUT_S = 10
_PRIVATE_NETS = [
    ipaddress.ip_network(n) for n in (
        "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10",
    )
]


# ======================================================================
# Errors
# ======================================================================
class RegistryError(Exception):
    """Base error carrying (http_status, error_code, detail dict)."""
    def __init__(self, http_status: int, code: str, **detail):
        self.http_status = http_status
        self.code = code
        self.detail = detail
        super().__init__(f"{http_status} {code}: {detail}")


def _raise_parse(detail: str) -> "RegistryError":
    raise RegistryError(
        400, "parse_error",
        detail=detail, reference_template=REFERENCE_TEMPLATE,
    )


def _raise_missing(missing: List[str]) -> "RegistryError":
    raise RegistryError(
        422, "missing_anchors",
        missing=missing, reference_template=REFERENCE_TEMPLATE,
    )


# ======================================================================
# Anchor parser: content string -> {GLOBAL_PROMPT: "...", ...}
# ======================================================================
# Python-style string literal: triple-quoted OR single-line, either quote style.
# Anchored to start-of-line for the NAME = ; the literal itself matches until
# its closing delimiter. re.DOTALL lets triple bodies span lines.
_STRING_LITERAL_RE = (
    r"(?:"
    r"'''(?P<tq_single>.*?)'''"
    r"|\"\"\"(?P<tq_double>.*?)\"\"\""
    r"|'(?P<sq_single>[^'\n]*)'"
    r"|\"(?P<sq_double>[^\"\n]*)\""
    r")"
)
_ANCHOR_RE = re.compile(
    rf"^[ \t]*(?P<name>{'|'.join(ANCHOR_NAMES)})[ \t]*=[ \t]*{_STRING_LITERAL_RE}[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def parse_full_content(text: str) -> Dict[str, str]:
    """Extract the four named sections. Raises RegistryError on any problem."""
    if not text or not text.strip():
        _raise_parse("content is empty")

    found: Dict[str, str] = {}
    for m in _ANCHOR_RE.finditer(text):
        name = m.group("name")
        body = None
        for grp in ("tq_single", "tq_double", "sq_single", "sq_double"):
            if m.group(grp) is not None:
                body = m.group(grp)
                break
        if body is None:
            _raise_parse(f"malformed string literal for {name}")
        if name in found:
            raise RegistryError(
                400, "duplicate_anchor",
                anchor=name, reference_template=REFERENCE_TEMPLATE,
            )
        found[name] = body

    missing = [n for n in ANCHOR_NAMES if n not in found or not found[n].strip()]
    if missing:
        _raise_missing(missing)

    return {ANCHOR_TO_KEY[n]: found[n] for n in ANCHOR_NAMES}


# ======================================================================
# Smart field auto-fill
# ======================================================================
# Appended to MACRO / LOCAL when st_tm/end_tm are missing.
_TIME_SCAFFOLD = "\n开始时间: {st_tm} 秒\n结束时间: {end_tm} 秒\n"

# T-minus envelope: wraps the user's body so required placeholders all appear.
_TMINUS_ENVELOPE = (
    "##上下文:\n"
    "前 {dur} 秒的视频总结放在方括号 [] 中。\n"
    "{user_body}\n"
    "[\n"
    "开始时间: {st_tm} 秒\n"
    "结束时间: {end_tm} 秒\n"
    "{past_summary}\n"
    "]\n"
)


def _placeholders_in(text: str) -> set:
    """Names of {foo} placeholders present in `text`, via BasePrompt._get_template_fields."""
    return BasePrompt._get_template_fields(text)


def smart_autofill(sections: Dict[str, str]) -> Dict[str, str]:
    """Return a copy with canonical scaffolding appended where required
    placeholders are missing. Does not mutate input."""
    out = dict(sections)

    # MACRO / LOCAL: append time-range lines if they lack st_tm/end_tm.
    for key in ("macro", "local"):
        present = _placeholders_in(out[key])
        needed = REQUIRED_PLACEHOLDERS[key] - present
        if needed:
            # Only append when at least one of st_tm/end_tm is missing;
            # the scaffold line provides both together.
            out[key] = out[key].rstrip() + _TIME_SCAFFOLD

    # T-minus: if it's missing any required placeholder, wrap into the envelope.
    present_t = _placeholders_in(out["t_minus"])
    if REQUIRED_PLACEHOLDERS["t_minus"] - present_t:
        out["t_minus"] = _TMINUS_ENVELOPE.format_map({
            "user_body": out["t_minus"].strip(),
            # Keep the literal placeholders unresolved — they must survive for the final .format() at runtime.
            "dur": "{dur}",
            "st_tm": "{st_tm}",
            "end_tm": "{end_tm}",
            "past_summary": "{past_summary}",
        })

    return out


# ======================================================================
# Hard validation
# ======================================================================
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_BANNED_TOKENS = ("```", "<<<")


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise RegistryError(
            400, "invalid_name",
            detail=f"task_name must match {_NAME_RE.pattern}", task_name=name,
        )
    if name in {t.value for t in TASKNAME}:
        raise RegistryError(
            409, "builtin_conflict",
            detail=f"task_name '{name}' conflicts with a built-in task",
            task_name=name,
        )


def _validate_sections(sections: Dict[str, str]) -> None:
    """Check banned tokens, required placeholders, and run a render smoke test."""
    for key, txt in sections.items():
        for tok in _BANNED_TOKENS:
            if tok in txt:
                raise RegistryError(
                    400, "banned_token",
                    section=key, token=tok,
                    detail=f"section '{key}' contains reserved token {tok!r}",
                )
        need = REQUIRED_PLACEHOLDERS[key]
        have = _placeholders_in(txt)
        missing = need - have
        if missing:
            raise RegistryError(
                422, "missing_placeholders",
                section=key, missing=sorted(missing),
                reference_template=REFERENCE_TEMPLATE,
            )

    # Render smoke test: build a DynamicPrompt and call each assign_* with
    # canonical kwargs. Any KeyError / ValueError here means the template is
    # unsafe to ship.
    probe = DynamicPrompt(
        task_name="__probe__",
        global_prompt=sections["global"],
        macro_prompt=sections["macro"],
        local_prompt=sections["local"],
        t_minus_prompt=sections["t_minus"],
    )
    smoke_kwargs_common = {
        "question": "probe",
        "st_tm": 0, "end_tm": 10,
        "dur": 10, "past_summary": "probe",
    }
    try:
        probe.assign_global_prompt(**smoke_kwargs_common)
        probe.assign_macro_prompt(**smoke_kwargs_common)
        probe.assign_local_prompt(**smoke_kwargs_common)
        probe.assign_t_minus_prompt(**smoke_kwargs_common)
    except Exception as e:
        raise RegistryError(
            422, "render_smoke_failed",
            detail=str(e),
        )


# ======================================================================
# URL fetching (SSRF-safe)
# ======================================================================
def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unknown → treat as private
    return any(addr in net for net in _PRIVATE_NETS)


def fetch_prompt_url(url: str) -> str:
    """Download an https URL with size cap + SSRF protection. Returns text."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise RegistryError(400, "invalid_url", detail="only https:// URLs are accepted")
    host = parsed.hostname or ""
    if not host or host in ("localhost",):
        raise RegistryError(400, "invalid_url", detail="host not allowed")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise RegistryError(400, "invalid_url", detail=f"DNS failed: {e}")
    for info in infos:
        ip = info[4][0]
        if _is_private_ip(ip):
            raise RegistryError(
                400, "invalid_url",
                detail=f"host resolves to private address {ip}",
            )

    req = urllib.request.Request(url, headers={"User-Agent": "video-summary-service/prompt-studio"})
    try:
        with urllib.request.urlopen(req, timeout=URL_TIMEOUT_S) as resp:
            cl = resp.headers.get("Content-Length")
            if cl and int(cl) > MAX_URL_BYTES:
                raise RegistryError(
                    400, "url_too_large",
                    detail=f"Content-Length {cl} exceeds {MAX_URL_BYTES}",
                )
            data = resp.read(MAX_URL_BYTES + 1)
    except RegistryError:
        raise
    except Exception as e:
        raise RegistryError(400, "fetch_failed", detail=str(e))
    if len(data) > MAX_URL_BYTES:
        raise RegistryError(
            400, "url_too_large",
            detail=f"response exceeded {MAX_URL_BYTES} bytes",
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise RegistryError(400, "fetch_failed", detail="response is not utf-8 text")


# ======================================================================
# Content <-> sections round-trip
# ======================================================================
def reconstitute_content(sections: Dict[str, str]) -> str:
    """Rebuild an anchor-style content string from the four sections.

    Lossless round-trip: `parse_full_content(reconstitute_content(s)) == s`
    when the bodies don't themselves contain the closing delimiter `'''`.
    """
    parts = []
    for anchor in ANCHOR_NAMES:
        key = ANCHOR_TO_KEY[anchor]
        body = sections[key]
        # Preserve the body verbatim — the open delimiter uses '\n' immediately,
        # so the body's leading/trailing whitespace is retained.
        parts.append(f"{anchor} = '''{body}'''")
    return "\n\n".join(parts) + "\n"


# ======================================================================
# Registry
# ======================================================================
@dataclass
class DynamicTaskRecord:
    name: str
    description: Optional[str]
    sections: Dict[str, str]              # keys: global/macro/local/t_minus
    created_at: str
    updated_at: str

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "global_prompt": self.sections["global"],
            "macro_prompt": self.sections["macro"],
            "local_prompt": self.sections["local"],
            "t_minus_prompt": self.sections["t_minus"],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source": "dynamic",
        }

    @classmethod
    def from_json(cls, data: dict) -> "DynamicTaskRecord":
        return cls(
            name=data["name"],
            description=data.get("description"),
            sections={
                "global":  data["global_prompt"],
                "macro":   data["macro_prompt"],
                "local":   data["local_prompt"],
                "t_minus": data["t_minus_prompt"],
            },
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


class PromptRegistry:
    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir
        self._tasks_dir = cache_dir / "tasks"
        self._lock = threading.RLock()
        self._records: Dict[str, DynamicTaskRecord] = {}

    # ----- lifecycle -----
    def load(self) -> None:
        """Scan cache dir at startup; corrupt files get renamed .broken."""
        try:
            self._tasks_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("PromptRegistry: could not create %s: %s", self._tasks_dir, e)
            return

        with self._lock:
            self._records.clear()
            for path in sorted(self._tasks_dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    rec = DynamicTaskRecord.from_json(data)
                except Exception as e:
                    broken = path.with_suffix(".json.broken")
                    try:
                        path.rename(broken)
                    except OSError:
                        pass
                    logger.warning("PromptRegistry: bad file %s -> %s: %s", path, broken, e)
                    continue
                try:
                    _validate_sections(rec.sections)
                except RegistryError as e:
                    logger.warning("PromptRegistry: invalid task %s: %s", rec.name, e)
                    continue
                self._records[rec.name] = rec

        logger.info(
            "PromptRegistry: loaded %d dynamic tasks from %s",
            len(self._records), self._tasks_dir,
        )
        # Human-readable dump of every task currently available to the service
        # (built-in + dynamic). Helps users confirm what /v1/summary can route
        # to right after startup / reload.
        for row in self.list_all():
            desc = row.get("description") or "(no description)"
            logger.info(
                "PromptRegistry: available task  %-30s  source=%-7s  %s",
                row["name"], row["source"], desc,
            )

    # ----- queries -----
    @staticmethod
    def is_builtin(name: str) -> bool:
        return name in {t.value for t in TASKNAME}

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._records.keys())

    def list_all(self) -> List[dict]:
        """Built-in + dynamic, each tagged. Pulls each builtin's one-line
        DESCRIPTION class attribute so users can tell what each task does."""
        # Lazy import to avoid a prompt_builder → prompt_registry cycle at
        # module import time. `get_prompt_instance` is cheap — each builtin
        # class is stateless and construction is basically free.
        from video_analyzer.prompts.prompt_builder import get_prompt_instance

        out: List[dict] = []
        for t in TASKNAME:
            desc: Optional[str] = None
            try:
                inst = get_prompt_instance(t.value)
                raw = getattr(inst, "DESCRIPTION", "")
                if isinstance(raw, str) and raw.strip():
                    desc = raw.strip()
            except Exception:
                # Never let a broken builtin break the registry listing.
                desc = None
            out.append({"name": t.value, "source": "builtin", "description": desc})
        with self._lock:
            for rec in self._records.values():
                out.append(
                    {"name": rec.name, "source": "dynamic", "description": rec.description}
                )
        return out

    def get(self, name: str) -> Optional[BasePrompt]:
        """Return a DynamicPrompt for `name` if registered, else None."""
        with self._lock:
            rec = self._records.get(name)
        if rec is None:
            return None
        return DynamicPrompt(
            task_name=rec.name,
            global_prompt=rec.sections["global"],
            macro_prompt=rec.sections["macro"],
            local_prompt=rec.sections["local"],
            t_minus_prompt=rec.sections["t_minus"],
        )

    def get_record(self, name: str) -> Optional[DynamicTaskRecord]:
        with self._lock:
            return self._records.get(name)

    # ----- mutations -----
    def add(
        self,
        name: str,
        sections: Dict[str, str],
        description: Optional[str],
    ) -> DynamicTaskRecord:
        _validate_name(name)
        with self._lock:
            if name in self._records:
                raise RegistryError(
                    409, "already_registered",
                    detail=f"dynamic task '{name}' already exists",
                    task_name=name,
                )
            filled = smart_autofill(sections)
            _validate_sections(filled)
            now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            rec = DynamicTaskRecord(
                name=name, description=description,
                sections=filled, created_at=now, updated_at=now,
            )
            self._persist(rec)
            self._records[name] = rec
            return rec

    def rename(self, old: str, new: str) -> DynamicTaskRecord:
        _validate_name(new)
        with self._lock:
            if old not in self._records:
                raise RegistryError(404, "not_found", task_name=old)
            if new == old:
                return self._records[old]
            if new in self._records:
                raise RegistryError(
                    409, "already_registered", task_name=new,
                )
            rec = self._records.pop(old)
            rec.name = new
            rec.updated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            self._persist(rec)
            self._records[new] = rec
            self._delete_file(old)
            return rec

    def replace(
        self,
        name: str,
        sections: Dict[str, str],
        description: Optional[str],
    ) -> DynamicTaskRecord:
        """Overwrite all four sections + optionally description."""
        with self._lock:
            if name not in self._records:
                raise RegistryError(404, "not_found", task_name=name)
            filled = smart_autofill(sections)
            _validate_sections(filled)
            rec = self._records[name]
            rec.sections = filled
            if description is not None:
                rec.description = description
            rec.updated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            self._persist(rec)
            return rec

    def update_description(self, name: str, description: str) -> DynamicTaskRecord:
        with self._lock:
            if name not in self._records:
                raise RegistryError(404, "not_found", task_name=name)
            rec = self._records[name]
            rec.description = description
            rec.updated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            self._persist(rec)
            return rec

    def delete(self, name: str) -> None:
        if self.is_builtin(name):
            raise RegistryError(
                403, "builtin_immutable",
                detail=f"built-in task '{name}' cannot be deleted", task_name=name,
            )
        with self._lock:
            if name not in self._records:
                raise RegistryError(404, "not_found", task_name=name)
            self._delete_file(name)
            del self._records[name]

    # ----- persistence helpers -----
    def _persist(self, rec: DynamicTaskRecord) -> None:
        """Atomic write: tmp file in same dir, then os.replace."""
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        final = self._tasks_dir / f"{rec.name}.json"
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{rec.name}.", suffix=".json.tmp", dir=str(self._tasks_dir),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rec.to_json(), f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, final)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _delete_file(self, name: str) -> None:
        path = self._tasks_dir / f"{name}.json"
        try:
            path.unlink()
        except FileNotFoundError:
            pass


# ======================================================================
# Module singleton
# ======================================================================
_registry: Optional[PromptRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> PromptRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            cache_dir = Path(settings.VIDEO_SUMMARY_CACHE).expanduser()
            _registry = PromptRegistry(cache_dir)
            _registry.load()
    return _registry


# ======================================================================
# High-level content -> sections helper (used by REST handlers)
# ======================================================================
def resolve_content_to_sections(
    content_text: Optional[str],
    content_url: Optional[str],
) -> Tuple[Dict[str, str], str]:
    """Convert a PromptContent (text or url) into the four sections.

    Returns (sections_dict, raw_content_text_used).
    """
    if content_text is not None and content_url is not None:
        raise RegistryError(
            400, "ambiguous_content",
            detail="provide exactly one of content.text or content.url",
        )
    if content_url is not None:
        raw = fetch_prompt_url(content_url)
    elif content_text is not None:
        raw = content_text
    else:
        raise RegistryError(
            400, "missing_content",
            detail="content is required for mode=full",
        )
    sections = parse_full_content(raw)
    return sections, raw
