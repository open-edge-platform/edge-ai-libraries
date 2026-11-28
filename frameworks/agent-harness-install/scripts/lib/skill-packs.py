#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Skill-pack helper for agent-harness-install.

A skill pack is a versioned directory (or .tar.gz/.tgz/.zip archive) that
bundles agent skills for one consumer (for example "vss"). This helper holds
the structural logic so the bash layer stays thin:

  * safe materialisation + validation of pack sources
  * installing/removing packs under the installer state directory
  * the pack registry (registry.json)
  * collision detection between packs and local skills
  * merging ``skills.external_dirs`` into the Hermes config.yaml
  * selectively retiring / restoring Hermes's bundled default skills

Only the Python standard library is required, except for the YAML config
merge: it uses PyYAML, or Hermes's own ``hermes_yaml`` when
HARNESS_HERMES_AGENT_DIR points at a Hermes checkout (OpenShell image build).

Machine-readable results go to stdout; human messages go to stderr.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

SCHEMA = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
SKILL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
AGENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
KNOWN_RUNTIMES = ("host", "openshell")
ALLOWED_SUBDIRS = ("references", "templates", "scripts", "assets", "examples")
MARKER_NAME = ".no-bundled-skills"
BUNDLED_MANIFEST = ".bundled_manifest"
MAX_MANIFEST_BYTES = 64 * 1024


class PackError(Exception):
    """A user-facing validation or safety failure."""


def say(msg: str) -> None:
    print("  " + msg, file=sys.stderr)


def warn(msg: str) -> None:
    print("  warning: " + msg, file=sys.stderr)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return default


def max_total_bytes() -> int:
    return _int_env("HARNESS_SKILLS_MAX_BYTES", 64 * 1024 * 1024)


def max_file_bytes() -> int:
    return _int_env("HARNESS_SKILLS_MAX_FILE_BYTES", 16 * 1024 * 1024)


def max_files() -> int:
    return _int_env("HARNESS_SKILLS_MAX_FILES", 5000)


def max_archive_bytes() -> int:
    return _int_env("HARNESS_SKILLS_MAX_ARCHIVE_BYTES", 128 * 1024 * 1024)


# --------------------------------------------------------------------------
# Generic filesystem helpers
# --------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Write ``data`` atomically; refuse to write through a symlink."""
    if path.is_symlink():
        raise PackError(f"refusing to write through symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _make_writable(path: str) -> None:
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass


def rmtree_writable(path: Path) -> None:
    """Remove a tree that may contain read-only files/dirs (installed packs)."""
    p = str(path)
    if os.path.islink(p):
        os.unlink(p)
        return
    if not os.path.lexists(p):
        return
    for dirpath, dirnames, _files in os.walk(p, topdown=True, followlinks=False):
        _make_writable(dirpath)
    if sys.version_info >= (3, 12):

        def _onexc(func, failed, _exc):  # type: ignore[no-untyped-def]
            _make_writable(failed)
            func(failed)

        shutil.rmtree(p, onexc=_onexc)
    else:

        def _onerror(func, failed, _info):  # type: ignore[no-untyped-def]
            _make_writable(failed)
            func(failed)

        shutil.rmtree(p, onerror=_onerror)


def make_readonly(root: Path) -> None:
    """Files 0444 (0555 when executable), directories 0555."""
    for dirpath, dirnames, filenames in os.walk(str(root), topdown=False, followlinks=False):
        for name in filenames:
            fpath = os.path.join(dirpath, name)
            if os.path.islink(fpath):
                continue
            exec_bit = os.stat(fpath).st_mode & 0o111
            os.chmod(fpath, 0o555 if exec_bit else 0o444)
        os.chmod(dirpath, 0o555)


def _is_exec(path: str) -> bool:
    return bool(os.lstat(path).st_mode & 0o111)


def _clean_rel(name: str) -> Optional[PurePosixPath]:
    """Normalise an archive member name; None means the archive root itself."""
    if "\x00" in name or "\\" in name or any(ord(c) < 32 for c in name):
        raise PackError(f"archive member has an unsafe name: {name!r}")
    p = PurePosixPath(name)
    if p.is_absolute():
        raise PackError(f"archive member has an absolute path: {name!r}")
    parts = [x for x in p.parts if x not in ("", ".")]
    if any(x == ".." for x in parts):
        raise PackError(f"archive member escapes the archive root: {name!r}")
    if not parts:
        return None
    return PurePosixPath(*parts)


class Budget:
    def __init__(self) -> None:
        self.total = 0
        self.files = 0

    def add_file(self, size: int, label: str) -> None:
        self.files += 1
        self.total += size
        if self.files > max_files():
            raise PackError(f"pack has more than {max_files()} files")
        if size > max_file_bytes():
            raise PackError(f"file {label!r} exceeds {max_file_bytes()} bytes")
        if self.total > max_total_bytes():
            raise PackError(f"pack exceeds {max_total_bytes()} bytes uncompressed")


def _stream_to(src: Any, dst: Path, budget: Budget, label: str, exec_bit: bool) -> None:
    written = 0
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(str(dst), flags, 0o700 if exec_bit else 0o600)
    with os.fdopen(fd, "wb") as out:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_file_bytes():
                raise PackError(f"file {label!r} exceeds {max_file_bytes()} bytes")
            budget.total += len(chunk)
            if budget.total > max_total_bytes():
                raise PackError(f"pack exceeds {max_total_bytes()} bytes uncompressed")
            out.write(chunk)
    budget.files += 1
    if budget.files > max_files():
        raise PackError(f"pack has more than {max_files()} files")


def _prepare_target(dest: Path, rel: PurePosixPath) -> Path:
    target = dest.joinpath(*rel.parts)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError):
        raise PackError(f"archive member conflicts with another entry: {rel}")
    return target


def extract_tar(archive: Path, dest: Path) -> None:
    budget = Budget()
    try:
        tf = tarfile.open(str(archive), "r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise PackError(f"cannot read tar archive: {exc}")
    with tf:
        for member in tf:
            rel = _clean_rel(member.name)
            if rel is None:
                if member.isdir():
                    continue
                raise PackError(f"archive member has an invalid name: {member.name!r}")
            if member.isdir():
                target = dest.joinpath(*rel.parts)
                try:
                    target.mkdir(parents=True, exist_ok=True)
                except (FileExistsError, NotADirectoryError):
                    raise PackError(f"archive member conflicts with another entry: {rel}")
                continue
            if not member.isreg():
                raise PackError(
                    f"archive member {member.name!r} is not a regular file or directory "
                    "(symlinks, hardlinks and devices are not allowed)"
                )
            if member.size > max_file_bytes():
                raise PackError(f"file {member.name!r} exceeds {max_file_bytes()} bytes")
            target = _prepare_target(dest, rel)
            if target.exists():
                raise PackError(f"archive has a duplicate entry: {rel}")
            src = tf.extractfile(member)
            if src is None:
                raise PackError(f"cannot read archive member {member.name!r}")
            with src:
                _stream_to(src, target, budget, member.name, bool(member.mode & 0o111))


def extract_zip(archive: Path, dest: Path) -> None:
    budget = Budget()
    try:
        zf = zipfile.ZipFile(str(archive))
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackError(f"cannot read zip archive: {exc}")
    with zf:
        for info in zf.infolist():
            rel = _clean_rel(info.filename)
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode) if mode else 0
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise PackError(
                    f"archive member {info.filename!r} is not a regular file or directory "
                    "(symlinks and devices are not allowed)"
                )
            if info.flag_bits & 0x1:
                raise PackError("encrypted zip archives are not supported")
            is_dir = info.filename.endswith("/") or kind == stat.S_IFDIR
            if rel is None:
                if is_dir:
                    continue
                raise PackError(f"archive member has an invalid name: {info.filename!r}")
            if is_dir:
                target = dest.joinpath(*rel.parts)
                try:
                    target.mkdir(parents=True, exist_ok=True)
                except (FileExistsError, NotADirectoryError):
                    raise PackError(f"archive member conflicts with another entry: {rel}")
                continue
            if info.file_size > max_file_bytes():
                raise PackError(f"file {info.filename!r} exceeds {max_file_bytes()} bytes")
            target = _prepare_target(dest, rel)
            if target.exists():
                raise PackError(f"archive has a duplicate entry: {rel}")
            with zf.open(info) as src:
                _stream_to(src, target, budget, info.filename, bool(mode & 0o111))


def sniff_archive(path: Path) -> str:
    with open(path, "rb") as handle:
        head = handle.read(4)
    if head[:2] == b"\x1f\x8b":
        return "tar"
    if head[:2] == b"PK":
        return "zip"
    raise PackError("source file is not a .tar.gz/.tgz or .zip archive")


# --------------------------------------------------------------------------
# Pack validation and normalisation
# --------------------------------------------------------------------------


def find_pack_root(base: Path) -> Path:
    if (base / "pack.json").exists():
        return base
    subdirs = [p for p in base.iterdir() if p.is_dir() and not p.is_symlink()]
    if len(subdirs) == 1 and (subdirs[0] / "pack.json").exists():
        return subdirs[0]
    raise PackError("pack.json not found at the pack root (or inside a single top-level directory)")


def _check_regular(path: Path, label: str) -> None:
    st = os.lstat(str(path))
    if stat.S_ISLNK(st.st_mode):
        raise PackError(f"{label} is a symlink, which is not allowed: {path}")
    if not stat.S_ISREG(st.st_mode) and not stat.S_ISDIR(st.st_mode):
        raise PackError(f"{label} is not a regular file or directory: {path}")


def _check_name(name: str, where: str) -> None:
    if not name or any(ord(c) < 32 for c in name) or "\\" in name:
        raise PackError(f"unsafe file name in {where}: {name!r}")


def load_manifest(path: Path) -> Dict[str, Any]:
    _check_regular(path, "pack.json")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise PackError("pack.json is too large")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PackError(f"pack.json is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise PackError("pack.json must contain a JSON object")
    if data.get("schema", SCHEMA) != SCHEMA:
        raise PackError(f"unsupported pack schema {data.get('schema')!r} (expected {SCHEMA})")
    pack_id = data.get("id")
    if not isinstance(pack_id, str) or not ID_RE.match(pack_id):
        raise PackError("pack.json 'id' must match ^[a-z0-9][a-z0-9-]{0,31}$")
    version = data.get("version", "")
    if not isinstance(version, str) or len(version) > 64 or any(ord(c) < 32 for c in version):
        raise PackError("pack.json 'version' must be a short string")
    description = data.get("description", "")
    if not isinstance(description, str) or len(description) > 500:
        raise PackError("pack.json 'description' must be a string of at most 500 characters")
    agents = data.get("agents", ["hermes"])
    if (
        not isinstance(agents, list)
        or not agents
        or not all(isinstance(a, str) and AGENT_RE.match(a) for a in agents)
    ):
        raise PackError("pack.json 'agents' must be a non-empty list of agent names")
    runtimes = data.get("runtimes", list(KNOWN_RUNTIMES))
    if (
        not isinstance(runtimes, list)
        or not runtimes
        or not all(isinstance(r, str) and r in KNOWN_RUNTIMES for r in runtimes)
    ):
        raise PackError("pack.json 'runtimes' must be a non-empty list drawn from: host, openshell")
    defaults = data.get("defaults", "keep")
    if defaults not in ("keep", "none"):
        raise PackError("pack.json 'defaults' must be 'keep' or 'none'")
    strict = data.get("strict_names", False)
    if not isinstance(strict, bool):
        raise PackError("pack.json 'strict_names' must be true or false")
    listed = data.get("skills")
    if listed is not None and (
        not isinstance(listed, list) or not all(isinstance(s, str) for s in listed)
    ):
        raise PackError("pack.json 'skills' must be a list of skill names")
    return {
        "schema": SCHEMA,
        "id": pack_id,
        "version": version,
        "description": description,
        "agents": sorted(set(agents)),
        "runtimes": [r for r in KNOWN_RUNTIMES if r in runtimes],
        "defaults": defaults,
        "strict_names": strict,
        "listed": listed,
    }


def read_frontmatter_name(md: Path) -> Optional[str]:
    try:
        with open(md, "rb") as handle:
            text = handle.read(16384).decode("utf-8-sig", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^name\s*:\s*(.+?)\s*$", line)
        if match:
            value = match.group(1).strip().strip("'\"").strip()
            return value or None
    return None


def _walk_files(root: Path) -> List[Tuple[str, Path]]:
    """All regular files under ``root`` as (posix-relative, path); rejects links."""
    found: List[Tuple[str, Path]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(str(current)) as it:
            entries = sorted(it, key=lambda e: e.name)
        for entry in entries:
            _check_name(entry.name, str(current))
            path = Path(entry.path)
            st = os.lstat(entry.path)
            if stat.S_ISLNK(st.st_mode):
                raise PackError(f"symlink not allowed in pack: {path}")
            if stat.S_ISDIR(st.st_mode):
                stack.append(path)
            elif stat.S_ISREG(st.st_mode):
                found.append((path.relative_to(root).as_posix(), path))
            else:
                raise PackError(f"special file not allowed in pack: {path}")
    found.sort(key=lambda item: item[0])
    return found


def content_hash(root: Path) -> str:
    """Deterministic sha256 over relative paths, contents and exec bits."""
    digest = hashlib.sha256()
    for rel, path in _walk_files(root):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(b"x" if _is_exec(str(path)) else b"-")
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(src), str(dst))
    os.chmod(str(dst), 0o755 if _is_exec(str(src)) else 0o644)


def copy_pack_tree(src: Path, dst: Path) -> None:
    """Copy a pack tree with owner-writable permissions, refusing links."""
    for rel, path in _walk_files(src):
        _copy_file(path, dst / rel)
    dst.mkdir(parents=True, exist_ok=True)


def discover_skills(skills_root: Path) -> List[Dict[str, Any]]:
    if not skills_root.is_dir() or skills_root.is_symlink():
        raise PackError("pack has no 'skills/' directory")
    budget = Budget()
    skills: List[Dict[str, Any]] = []
    with os.scandir(str(skills_root)) as it:
        entries = sorted(it, key=lambda e: e.name)
    for entry in entries:
        _check_name(entry.name, "skills/")
        st = os.lstat(entry.path)
        if stat.S_ISLNK(st.st_mode):
            raise PackError(f"symlink not allowed in pack: skills/{entry.name}")
        if not stat.S_ISDIR(st.st_mode):
            raise PackError(f"skills/ may only contain skill directories, found: {entry.name}")
        name = entry.name
        if not SKILL_RE.match(name) or ".." in name:
            raise PackError(
                f"invalid skill name {name!r}: use lowercase letters, digits, '.', '_' or '-' (max 64)"
            )
        sdir = Path(entry.path)
        md = sdir / "SKILL.md"
        if not md.is_file() or md.is_symlink():
            raise PackError(f"skill {name!r} has no SKILL.md")
        with os.scandir(entry.path) as sit:
            children = sorted(sit, key=lambda e: e.name)
        for child in children:
            _check_name(child.name, f"skills/{name}")
            cst = os.lstat(child.path)
            if stat.S_ISLNK(cst.st_mode):
                raise PackError(f"symlink not allowed in pack: skills/{name}/{child.name}")
            if stat.S_ISDIR(cst.st_mode) and child.name not in ALLOWED_SUBDIRS:
                raise PackError(
                    f"skills/{name}/{child.name}/ is not an allowed subdirectory "
                    f"(allowed: {', '.join(ALLOWED_SUBDIRS)})"
                )
        for rel, path in _walk_files(sdir):
            budget.add_file(path.stat().st_size, f"skills/{name}/{rel}")
        fm_name = read_frontmatter_name(md)
        if fm_name is not None and (len(fm_name) > 128 or any(ord(c) < 32 for c in fm_name)):
            raise PackError(f"skill {name!r} has an invalid name in SKILL.md frontmatter")
        skills.append({"dir": name, "name": fm_name or name})
    if not skills:
        raise PackError("pack contains no skills")
    return skills


def cmd_materialize(args: argparse.Namespace) -> int:
    src = Path(args.source)
    out = Path(args.out)
    if out.exists():
        raise PackError(f"output directory already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.sha256 and not SHA256_RE.match(args.sha256):
        raise PackError("--sha256 must be 64 lowercase hexadecimal characters")
    tmp_root: Optional[Path] = None
    try:
        if src.is_symlink():
            raise PackError(f"source is a symlink: {src}")
        if src.is_dir():
            if args.sha256:
                raise PackError("--sha256 applies to archive sources, not directories")
            base = src
        elif src.is_file():
            size = src.stat().st_size
            if size > max_archive_bytes():
                raise PackError(f"archive exceeds {max_archive_bytes()} bytes")
            if args.sha256:
                actual = sha256_file(src)
                if actual != args.sha256:
                    raise PackError(
                        f"sha256 mismatch for {src.name}: expected {args.sha256}, got {actual}"
                    )
            kind = sniff_archive(src)
            tmp_root = Path(tempfile.mkdtemp(prefix=".extract.", dir=str(out.parent)))
            os.chmod(str(tmp_root), 0o700)
            (extract_tar if kind == "tar" else extract_zip)(src, tmp_root)
            base = tmp_root
        else:
            raise PackError(f"source not found: {src}")

        pack_root = find_pack_root(base)
        manifest = load_manifest(pack_root / "pack.json")
        skills = discover_skills(pack_root / "skills")
        dir_names = sorted(s["dir"] for s in skills)
        if manifest["listed"] is not None and sorted(manifest["listed"]) != dir_names:
            raise PackError(
                "pack.json 'skills' does not match skills/ contents: "
                f"listed={sorted(manifest['listed'])} found={dir_names}"
            )

        strict = manifest["strict_names"] or os.environ.get("HARNESS_SKILLS_STRICT_NAMES") == "1"
        prefix = manifest["id"] + "-"
        warnings: List[str] = []
        for skill in skills:
            if not skill["dir"].startswith(prefix):
                msg = (
                    f"skill {skill['dir']!r} does not start with '{prefix}'; "
                    "prefixing pack skills avoids name collisions"
                )
                if strict:
                    raise PackError(msg)
                warnings.append(msg)
            if skill["name"] != skill["dir"]:
                warnings.append(
                    f"skill directory {skill['dir']!r} differs from its SKILL.md name {skill['name']!r}"
                )

        out.mkdir(parents=True)
        shutil.copyfile(str(pack_root / "pack.json"), str(out / "pack.json"))
        os.chmod(str(out / "pack.json"), 0o644)
        copy_pack_tree(pack_root / "skills", out / "skills")
        digest = content_hash(out)

        names = sorted({s["dir"] for s in skills} | {s["name"] for s in skills})
        meta = {
            "id": manifest["id"],
            "version": manifest["version"],
            "description": manifest["description"],
            "agents": manifest["agents"],
            "runtimes": manifest["runtimes"],
            "defaults": manifest["defaults"],
            "strict_names": manifest["strict_names"],
            "skills": dir_names,
            "names": names,
            "hash": digest,
            "warnings": warnings,
        }
        for item in warnings:
            warn(item)
        print(json.dumps(meta, sort_keys=True))
        return 0
    except BaseException:
        if out.exists():
            rmtree_writable(out)
        raise
    finally:
        if tmp_root is not None:
            rmtree_writable(tmp_root)


def load_meta(path: str) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackError(f"cannot read pack metadata {path}: {exc}")
    if not isinstance(data, dict):
        raise PackError(f"invalid pack metadata: {path}")
    return data


def cmd_meta_field(args: argparse.Namespace) -> int:
    value = load_meta(args.meta).get(args.field, "")
    if isinstance(value, list):
        print(",".join(str(v) for v in value))
    elif isinstance(value, bool):
        print("true" if value else "false")
    else:
        print(value)
    return 0


# --------------------------------------------------------------------------
# Install / remove pack directories
# --------------------------------------------------------------------------


def cmd_install(args: argparse.Namespace) -> int:
    staged, dest = Path(args.staged), Path(args.dest)
    if not staged.is_dir() or staged.is_symlink():
        raise PackError(f"staged pack not found: {staged}")
    if dest.is_symlink():
        raise PackError(f"refusing to replace a symlink: {dest}")
    if not ID_RE.match(dest.name):
        raise PackError(f"invalid pack directory name: {dest.name}")
    old: Optional[Path] = None
    if dest.exists():
        old = dest.with_name(f".{dest.name}.old.{os.getpid()}")
        os.replace(str(dest), str(old))
    try:
        os.replace(str(staged), str(dest))
    except BaseException:
        if old is not None:
            os.replace(str(old), str(dest))
        raise
    make_readonly(dest)
    if old is not None:
        rmtree_writable(old)
    return 0


def cmd_remove_dir(args: argparse.Namespace) -> int:
    path, within = Path(args.path), Path(args.within)
    if path.is_symlink():
        raise PackError(f"refusing to remove a symlink: {path}")
    if path.parent.resolve() != within.resolve():
        raise PackError(f"refusing to remove {path}: not directly inside {within}")
    rmtree_writable(path)
    return 0


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


def reg_load(path: str) -> Dict[str, Any]:
    p = Path(path)
    if p.is_symlink():
        raise PackError(f"registry is a symlink: {p}")
    if not p.exists():
        return {"version": 1, "defaults": {}, "packs": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackError(f"registry is unreadable ({p}): {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("packs", {}), dict):
        raise PackError(f"registry has an unexpected structure: {p}")
    data.setdefault("version", 1)
    data.setdefault("defaults", {})
    data.setdefault("packs", {})
    return data


def reg_save(path: str, data: Dict[str, Any]) -> None:
    atomic_write(Path(path), (json.dumps(data, indent=2) + "\n").encode("utf-8"))


def eligible(entry: Dict[str, Any], runtime: Optional[str]) -> bool:
    if "hermes" not in entry.get("agents", []):
        return False
    return runtime is None or runtime in entry.get("runtimes", [])


def effective_policy(reg: Dict[str, Any], override: str, runtime: Optional[str], extra_none: bool) -> str:
    if override in ("keep", "none"):
        return override
    if extra_none:
        return "none"
    for entry in reg["packs"].values():
        if eligible(entry, runtime) and entry.get("defaults") == "none":
            return "none"
    return "keep"


def cmd_registry_add(args: argparse.Namespace) -> int:
    meta = load_meta(args.meta)
    reg = reg_load(args.registry)
    entry = {
        "version": meta.get("version", ""),
        "description": meta.get("description", ""),
        "source": {
            "type": args.source_type,
            "ref": args.source_ref,
            "sha256": args.source_sha256 or "",
        },
        "hash": meta["hash"],
        "skills": meta.get("skills", []),
        "names": meta.get("names", []),
        "agents": meta.get("agents", []),
        "runtimes": meta.get("runtimes", []),
        "defaults": meta.get("defaults", "keep"),
        "dir": args.dir,
        "origin": args.origin,
        "added_at": now_iso(),
    }
    existing = reg["packs"].get(meta["id"])
    if existing and existing.get("added_at"):
        entry["added_at"] = existing["added_at"]
        entry["updated_at"] = now_iso()
    reg["packs"][meta["id"]] = entry
    reg_save(args.registry, reg)
    return 0


def cmd_registry_remove(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    if args.id not in reg["packs"]:
        raise PackError(f"skill pack {args.id!r} is not registered")
    del reg["packs"][args.id]
    reg_save(args.registry, reg)
    return 0


def cmd_registry_get(args: argparse.Namespace) -> int:
    """Print a field of the registry (dotted path); empty output when absent."""
    node: Any = reg_load(args.registry)
    for part in args.field.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return 0
    if isinstance(node, (dict, list)):
        print(json.dumps(node, sort_keys=True))
    elif isinstance(node, bool):
        print("true" if node else "false")
    else:
        print(node)
    return 0


def cmd_registry_set_defaults(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    try:
        updates = json.loads(args.json)
    except ValueError as exc:
        raise PackError(f"invalid JSON: {exc}")
    if not isinstance(updates, dict):
        raise PackError("--json must be an object")
    reg["defaults"].update(updates)
    reg_save(args.registry, reg)
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    print(effective_policy(reg, args.override, args.runtime, args.extra_none))
    return 0


def cmd_pack_dirs(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    for entry in reg["packs"].values():
        if eligible(entry, args.runtime):
            print(os.path.join(entry["dir"], "skills"))
    return 0


def pack_set_hash(reg: Dict[str, Any], runtime: str, policy: str) -> str:
    packs = [(pid, e) for pid, e in reg["packs"].items() if eligible(e, runtime)]
    if not packs and policy != "none":
        return ""
    digest = hashlib.sha256()
    digest.update(f"policy={policy}\n".encode("utf-8"))
    for pid, entry in packs:
        digest.update(f"{pid}={entry['hash']}\n".encode("utf-8"))
    return digest.hexdigest()


def cmd_pack_set_hash(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    policy = effective_policy(reg, args.override, args.runtime, False)
    print(pack_set_hash(reg, args.runtime, policy))
    return 0


def cmd_has_packs(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    print("true" if any(eligible(e, args.runtime) for e in reg["packs"].values()) else "false")
    return 0


# --------------------------------------------------------------------------
# Collisions
# --------------------------------------------------------------------------


def local_skill_names(skills_dir: Path) -> Dict[str, str]:
    """Map skill name -> relative directory for skills under ``skills_dir``."""
    names: Dict[str, str] = {}
    if not skills_dir.is_dir():
        return names
    for dirpath, dirnames, filenames in os.walk(str(skills_dir), followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if "SKILL.md" in filenames:
            sdir = Path(dirpath)
            rel = sdir.relative_to(skills_dir).as_posix()
            fm = read_frontmatter_name(sdir / "SKILL.md")
            for name in {sdir.name, fm or sdir.name}:
                names.setdefault(name, rel)
    return names


def cmd_collisions(args: argparse.Namespace) -> int:
    meta = load_meta(args.meta)
    reg = reg_load(args.registry)
    mine = set(meta.get("names", []))
    problems: List[str] = []
    for pid, entry in reg["packs"].items():
        if pid == meta["id"]:
            continue
        for name in sorted(mine & set(entry.get("names", []))):
            problems.append(f"skill {name!r} is also provided by skill pack {pid!r}")
    if args.local_skills_dir:
        local = local_skill_names(Path(args.local_skills_dir))
        retiring: Set[str] = set()
        if args.retiring_json:
            try:
                retiring = {str(r) for r in json.loads(args.retiring_json).get("moved", [])}
            except (ValueError, AttributeError):
                raise PackError("--retiring-json is not valid retire-defaults output")
        for name in sorted(mine & set(local)):
            if local[name] in retiring:
                continue
            problems.append(
                f"skill {name!r} already exists locally ({args.local_skills_dir}/{local[name]})"
            )
    if problems:
        raise PackError(
            f"skill pack {meta['id']!r} has conflicting skill names:\n    "
            + "\n    ".join(problems)
            + "\n  Rename the skills (a '<pack-id>-' prefix is recommended) or remove the conflicting skill."
        )
    return 0


# --------------------------------------------------------------------------
# Hermes config.yaml merge
# --------------------------------------------------------------------------


def load_yaml_module() -> Any:
    agent_dir = os.environ.get("HARNESS_HERMES_AGENT_DIR")
    if agent_dir:
        sys.path.insert(0, agent_dir)
        try:
            import hermes_bootstrap  # type: ignore  # noqa: F401
        except ImportError:
            pass
        import hermes_yaml as yaml  # type: ignore

        return yaml
    try:
        import yaml  # type: ignore
    except ImportError:
        raise PackError("PyYAML is required to edit the Hermes config (install python3-yaml)")
    return yaml


def _norm(path: str) -> str:
    return os.path.normpath(path)


def cmd_merge_config(args: argparse.Namespace) -> int:
    yaml = load_yaml_module()
    cfg = Path(args.config)
    if cfg.is_symlink():
        raise PackError(f"refusing to edit symlinked config: {cfg}")
    if cfg.exists():
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise PackError(f"{cfg} does not contain a YAML mapping")
    elif args.create:
        data = {}
    else:
        print(json.dumps({"missing": True, "changed": False}))
        return 3

    skills = data.get("skills")
    if skills is None:
        skills = {}
    if not isinstance(skills, dict):
        raise PackError("'skills' in the Hermes config is not a mapping; fix it manually")
    original = skills.get("external_dirs")
    if original is None:
        current: List[Any] = []
    elif isinstance(original, str):
        current = [original]
    elif isinstance(original, list):
        current = list(original)
    else:
        raise PackError("'skills.external_dirs' must be a list; fix it manually")

    remove = {_norm(d) for d in args.remove}
    merged = [e for e in current if not (isinstance(e, str) and _norm(e) in remove)]
    present = {_norm(e) for e in merged if isinstance(e, str)}
    added: List[str] = []
    for d in args.add:
        if _norm(d) not in present:
            merged.append(d)
            present.add(_norm(d))
            added.append(d)
    removed = len(current) - len([e for e in merged if e in current])

    if merged == current and (original is None or isinstance(original, list)):
        print(json.dumps({"changed": False, "added": [], "removed": 0}))
        return 0
    if not merged and original is None:
        print(json.dumps({"changed": False, "added": [], "removed": 0}))
        return 0

    if merged:
        skills["external_dirs"] = merged
        data["skills"] = skills
    else:
        skills.pop("external_dirs", None)
        if skills:
            data["skills"] = skills
        else:
            data.pop("skills", None)
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    backup = cfg.with_name(cfg.name + ".pre-skillpacks")
    if cfg.exists() and not backup.exists() and not args.no_backup:
        # The rewrite drops YAML comments and custom formatting.
        atomic_write(backup, cfg.read_bytes())
        say(f"saved the original Hermes config to {backup} (comments are not preserved when skill packs are wired in)")
    atomic_write(cfg, text.encode("utf-8"))
    print(json.dumps({"changed": True, "added": added, "removed": removed}))
    return 0


def config_external_dirs(config: Path) -> Optional[List[str]]:
    if not config.exists():
        return None
    yaml = load_yaml_module()
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    skills = data.get("skills") if isinstance(data, dict) else None
    ext = skills.get("external_dirs") if isinstance(skills, dict) else None
    if isinstance(ext, str):
        return [ext]
    if isinstance(ext, list):
        return [str(e) for e in ext]
    return []


# --------------------------------------------------------------------------
# Retire / restore Hermes default (bundled) skills
# --------------------------------------------------------------------------


def _is_runtime_cache(path: Path) -> bool:
    return (
        "__pycache__" in path.parts
        or path.suffix in (".pyc", ".pyo")
        or path.name == ".DS_Store"
    )


def hermes_dir_hash(directory: Path, include_runtime_cache: bool = False) -> str:
    """Mirror of Hermes's tools/skills_sync.py ``_dir_hash`` (md5, as used by its manifest)."""
    digest = hashlib.md5()  # noqa: S324 - format dictated by Hermes
    try:
        for fpath in sorted(directory.rglob("*")):
            if (include_runtime_cache or not _is_runtime_cache(fpath.relative_to(directory))) and fpath.is_file():
                digest.update(str(fpath.relative_to(directory)).encode("utf-8"))
                digest.update(fpath.read_bytes())
    except OSError:
        return ""
    return digest.hexdigest()


def read_bundled_manifest(skills_dir: Path) -> Dict[str, str]:
    path = skills_dir / BUNDLED_MANIFEST
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, digest = line.partition(":")
        out[name.strip()] = digest.strip()
    return out


def query_essential_skills(args: argparse.Namespace) -> Set[str]:
    if args.essential is not None:
        return {s for s in args.essential.split(",") if s}
    env = os.environ.get("HARNESS_HERMES_ESSENTIAL_SKILLS")
    if env is not None:
        return {s for s in env.split(",") if s}
    if not args.hermes_bin:
        raise PackError("cannot determine Hermes's essential skills (Hermes runtime not found)")
    home = args.hermes_home or os.path.join(os.path.expanduser("~"), ".hermes")
    env_vars = dict(os.environ, HERMES_HOME=home)
    try:
        proc = subprocess.run(
            [args.hermes_bin, "--print-runtime-command"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env_vars,
        )
        runtime = json.loads(proc.stdout.strip())
        python = runtime[0]
        code = (
            "import sys, json\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "try:\n"
            "    import hermes_bootstrap\n"
            "except ImportError:\n"
            "    pass\n"
            "from agent.skill_utils import ESSENTIAL_SKILLS\n"
            "print(json.dumps(sorted(ESSENTIAL_SKILLS)))\n"
        )
        agent_dir = args.hermes_agent_dir or os.path.join(home, "hermes-agent")
        proc = subprocess.run(
            [python, "-c", code, agent_dir],
            capture_output=True,
            text=True,
            timeout=120,
            env=env_vars,
        )
        values = json.loads(proc.stdout.strip().splitlines()[-1])
        if not isinstance(values, list):
            raise ValueError("unexpected output")
        return {str(v) for v in values}
    except (OSError, ValueError, IndexError, KeyError, subprocess.SubprocessError) as exc:
        raise PackError(f"cannot determine Hermes's essential skills: {exc}")


def index_local_skills(skills_dir: Path) -> List[Tuple[Path, Set[str]]]:
    found: List[Tuple[Path, Set[str]]] = []
    for dirpath, dirnames, filenames in os.walk(str(skills_dir), followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if "SKILL.md" in filenames:
            sdir = Path(dirpath)
            fm = read_frontmatter_name(sdir / "SKILL.md")
            found.append((sdir, {fm or sdir.name}))
            dirnames[:] = []
    return found


def _prune_empty_categories(skills_dir: Path, start: Path) -> None:
    current = start
    while current != skills_dir and skills_dir in current.parents:
        try:
            names = sorted(os.listdir(str(current)))
        except OSError:
            return
        if names and names != ["DESCRIPTION.md"]:
            return
        rmtree_writable(current)
        current = current.parent


def cmd_retire_defaults(args: argparse.Namespace) -> int:
    skills_dir = Path(args.skills_dir)
    if not skills_dir.is_dir() or skills_dir.is_symlink():
        print(json.dumps({"moved": [], "kept": [], "backup": ""}))
        return 0
    manifest = read_bundled_manifest(skills_dir)
    if not manifest:
        print(json.dumps({"moved": [], "kept": [], "backup": ""}))
        return 0
    essential = query_essential_skills(args)
    if not essential:
        raise PackError("cannot determine Hermes's essential skills (the list is empty)")

    plan: List[Path] = []
    kept: List[str] = []
    for sdir, names in index_local_skills(skills_dir):
        listed = [n for n in names if n in manifest]
        if not listed:
            continue
        name = listed[0]
        if name in essential:
            continue
        origin = manifest[name]
        pristine = bool(origin) and (
            hermes_dir_hash(sdir) == origin or hermes_dir_hash(sdir, include_runtime_cache=True) == origin
        )
        if pristine or args.purge:
            plan.append(sdir)
        else:
            kept.append(name)

    moved = [p.relative_to(skills_dir).as_posix() for p in plan]
    if args.dry_run or not plan:
        print(json.dumps({"moved": moved, "kept": sorted(kept), "backup": ""}))
        if kept and not args.dry_run:
            say(f"keeping {len(kept)} locally modified bundled skill(s): {', '.join(sorted(kept))}")
        return 0

    if not args.backup_root:
        raise PackError("--backup-root is required to retire default skills")
    backup_root = Path(args.backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    os.chmod(str(backup_root), 0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_root / stamp
    n = 0
    while backup.exists():
        n += 1
        backup = backup_root / f"{stamp}-{n}"
    shutil.copytree(str(skills_dir), str(backup / "skills"), symlinks=True)
    for rel in moved:
        if not (backup / "skills" / rel / "SKILL.md").is_file():
            raise PackError(f"backup verification failed for {rel}; nothing was removed")

    for sdir in plan:
        parent = sdir.parent
        rmtree_writable(sdir)
        _prune_empty_categories(skills_dir, parent)

    if args.registry:
        reg = reg_load(args.registry)
        backups = reg["defaults"].setdefault("backups", [])
        backups.append({"dir": str(backup), "moved": moved, "at": now_iso()})
        reg_save(args.registry, reg)

    say(f"retired {len(moved)} bundled default skill(s); backup: {backup}")
    if kept:
        say(f"keeping {len(kept)} locally modified bundled skill(s): {', '.join(sorted(kept))}")
    print(json.dumps({"moved": moved, "kept": sorted(kept), "backup": str(backup)}))
    return 0


def cmd_restore_defaults(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    defaults = reg["defaults"]
    skills_dir = Path(args.skills_dir)
    restored = 0
    for item in defaults.get("backups", []):
        backup = Path(item.get("dir", "")) / "skills"
        for rel in item.get("moved", []):
            if ".." in PurePosixPath(rel).parts or PurePosixPath(rel).is_absolute():
                continue
            src = backup / rel
            dst = skills_dir / rel
            if dst.exists():
                continue
            if not src.is_dir():
                warn(f"backup copy of {rel} is missing; skipping")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(src), str(dst), symlinks=True)
            desc = backup / PurePosixPath(rel).parent / "DESCRIPTION.md"
            target_desc = dst.parent / "DESCRIPTION.md"
            if PurePosixPath(rel).parent != PurePosixPath(".") and desc.is_file() and not target_desc.exists():
                shutil.copyfile(str(desc), str(target_desc))
            restored += 1
    marker = Path(args.hermes_home) / MARKER_NAME
    if defaults.get("marker_created") and marker.exists():
        marker.unlink()
        say("removed the bundled-skills opt-out marker")
    elif marker.exists():
        say(f"left {marker} in place (it was not created by this installer)")
    reg["defaults"] = {k: v for k, v in defaults.items() if k not in ("backups", "marker_created")}
    # Remember the choice so registered packs do not retire the defaults again.
    reg["defaults"]["operator"] = "keep"
    reg_save(args.registry, reg)
    say(f"restored {restored} bundled default skill(s)")
    return 0


# --------------------------------------------------------------------------
# Drop-ins
# --------------------------------------------------------------------------


def _check_owner_and_mode(path: Path, what: str) -> None:
    st = os.lstat(str(path))
    if stat.S_ISLNK(st.st_mode):
        raise PackError(f"{what} must not be a symlink: {path}")
    if hasattr(os, "getuid"):
        if st.st_uid != os.getuid():
            raise PackError(
                f"{what} must be owned by the current user (uid {os.getuid()}), but {path} is owned by uid {st.st_uid}."
                f" Fix it with: sudo chown {os.getuid()} '{path}' -- or remove it if it is not yours."
            )
        if st.st_mode & 0o022:
            raise PackError(
                f"{what} must not be group/world-writable: {path} (mode {st.st_mode & 0o777:03o})."
                f" Fix it with: chmod go-w '{path}'"
            )


def cmd_dropins(args: argparse.Namespace) -> int:
    base = Path(args.dir)
    if not os.path.lexists(str(base)):
        return 0
    _check_owner_and_mode(base, "drop-in directory")
    if not base.is_dir():
        raise PackError(f"drop-in path is not a directory: {base}")
    for path in sorted(base.glob("*.json")):
        _check_owner_and_mode(path, "drop-in file")
        if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            raise PackError(f"invalid drop-in file: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PackError(f"{path} is not valid JSON: {exc}")
        pack_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(pack_id, str) or not ID_RE.match(pack_id):
            raise PackError(f"{path}: 'id' must match ^[a-z0-9][a-z0-9-]{{0,31}}$")
        if path.stem != pack_id:
            raise PackError(f"{path}: file name must be <id>.json (id is {pack_id!r})")
        source = data.get("source")
        if not isinstance(source, dict):
            raise PackError(f"{path}: 'source' must be an object")
        stype = source.get("type")
        sha = ""
        if stype == "dir":
            ref = source.get("path")
            if not isinstance(ref, str) or not os.path.isabs(ref):
                raise PackError(f"{path}: source.path must be an absolute path")
        elif stype == "url":
            ref = source.get("url")
            sha = source.get("sha256")
            if not isinstance(ref, str) or not ref.startswith("https://"):
                raise PackError(f"{path}: source.url must be an https:// URL")
            if not isinstance(sha, str) or not SHA256_RE.match(sha.lower()):
                raise PackError(f"{path}: source.sha256 (64 hex characters) is required for URL sources")
            sha = sha.lower()
        else:
            raise PackError(f"{path}: source.type must be 'dir' or 'url'")
        if any(ord(c) < 32 for c in ref):
            raise PackError(f"{path}: source contains control characters")
        print("\t".join([pack_id, stype, ref, sha or "-", str(path)]))
    return 0


# --------------------------------------------------------------------------
# OpenShell build context
# --------------------------------------------------------------------------


def cmd_stage_context(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.name != "skill-packs":
        raise PackError(f"refusing to use {out} as a build-context staging directory")
    if out.is_symlink():
        raise PackError(f"refusing symlinked staging directory: {out}")
    reg = reg_load(args.registry)
    policy = effective_policy(reg, args.override, args.runtime, False)
    if out.exists():
        rmtree_writable(out)
    out.mkdir(parents=True)
    packs: List[Dict[str, str]] = []
    for pid, entry in reg["packs"].items():
        if not eligible(entry, args.runtime):
            continue
        src = Path(entry["dir"])
        if content_hash(src) != entry["hash"]:
            raise PackError(f"skill pack {pid!r} was modified after install; run './install.sh skills verify'")
        copy_pack_tree(src, out / pid)
        packs.append({"id": pid, "hash": entry["hash"], "skills_dir": f"{pid}/skills"})
    manifest = {"schema": SCHEMA, "defaults": policy, "packs": packs}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(pack_set_hash(reg, args.runtime, policy))
    return 0


# --------------------------------------------------------------------------
# list / verify
# --------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    packs = reg["packs"]
    if not packs:
        say("No skill packs registered.")
    else:
        say(f"Registered skill packs ({len(packs)}):")
        for pid, e in packs.items():
            src = e.get("source", {})
            say(
                f"{pid} {e.get('version', '')}  hash={e.get('hash', '')[:12]}  "
                f"{len(e.get('skills', []))} skill(s)  agents={','.join(e.get('agents', []))}  "
                f"runtimes={','.join(e.get('runtimes', []))}  defaults={e.get('defaults', 'keep')}"
            )
            say(f"    source: {src.get('type', '?')}:{src.get('ref', '')}  origin: {e.get('origin', '')}")
            say(f"    skills: {', '.join(e.get('skills', []))}")
    defaults = reg["defaults"]
    if args.hermes_home:
        marker = Path(args.hermes_home) / MARKER_NAME
        if marker.exists():
            say("Default Hermes skills: essential-only (opt-out marker present)")
        else:
            say("Default Hermes skills: kept")
        for item in defaults.get("backups", []):
            say(f"    backup of retired defaults: {item.get('dir')} ({len(item.get('moved', []))} skill(s))")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    reg = reg_load(args.registry)
    ids = [args.id] if args.id else list(reg["packs"])
    if args.id and args.id not in reg["packs"]:
        raise PackError(f"skill pack {args.id!r} is not registered")
    external: Optional[List[str]] = None
    if args.config:
        external = config_external_dirs(Path(args.config))
    failures = 0
    for pid in ids:
        entry = reg["packs"][pid]
        pdir = Path(entry["dir"])
        problems: List[str] = []
        if not pdir.is_dir():
            problems.append("pack directory is missing")
        else:
            try:
                if content_hash(pdir) != entry["hash"]:
                    problems.append("content hash differs from the registry (pack was modified)")
            except PackError as exc:
                problems.append(str(exc))
            for skill in entry.get("skills", []):
                if not (pdir / "skills" / skill / "SKILL.md").is_file():
                    problems.append(f"skill {skill!r} is missing")
        if external is not None and eligible(entry, "host"):
            wanted = _norm(os.path.join(entry["dir"], "skills"))
            if wanted not in {_norm(e) for e in external}:
                problems.append("skills.external_dirs in the Hermes config does not list this pack")
        if problems:
            failures += 1
            for item in problems:
                say(f"FAIL {pid}: {item}")
        else:
            say(f"ok   {pid} ({entry.get('hash', '')[:12]})")
    if args.hermes_home and Path(args.hermes_home).is_dir() and (not args.id):
        policy = effective_policy(reg, args.override, "host", False)
        marker = Path(args.hermes_home) / MARKER_NAME
        if policy == "none" and not marker.exists():
            failures += 1
            say("FAIL defaults: packs require essential-only default skills but the opt-out marker is missing")
    return 1 if failures else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill-packs.py")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func: Any) -> argparse.ArgumentParser:
        p = sub.add_parser(name)
        p.set_defaults(func=func)
        return p

    p = add("materialize", cmd_materialize)
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sha256", default="")

    p = add("meta-field", cmd_meta_field)
    p.add_argument("--meta", required=True)
    p.add_argument("--field", required=True)

    p = add("install", cmd_install)
    p.add_argument("--staged", required=True)
    p.add_argument("--dest", required=True)

    p = add("remove-dir", cmd_remove_dir)
    p.add_argument("--path", required=True)
    p.add_argument("--within", required=True)

    p = add("collisions", cmd_collisions)
    p.add_argument("--registry", required=True)
    p.add_argument("--meta", required=True)
    p.add_argument("--local-skills-dir", default="")
    p.add_argument("--retiring-json", default="")

    p = add("registry-add", cmd_registry_add)
    p.add_argument("--registry", required=True)
    p.add_argument("--meta", required=True)
    p.add_argument("--source-type", required=True, choices=("dir", "file", "url"))
    p.add_argument("--source-ref", required=True)
    p.add_argument("--source-sha256", default="")
    p.add_argument("--dir", required=True)
    p.add_argument("--origin", default="cli")

    p = add("registry-remove", cmd_registry_remove)
    p.add_argument("--registry", required=True)
    p.add_argument("--id", required=True)

    p = add("registry-get", cmd_registry_get)
    p.add_argument("--registry", required=True)
    p.add_argument("--field", required=True)

    p = add("registry-set-defaults", cmd_registry_set_defaults)
    p.add_argument("--registry", required=True)
    p.add_argument("--json", required=True)

    p = add("policy", cmd_policy)
    p.add_argument("--registry", required=True)
    p.add_argument("--override", default="auto", choices=("auto", "keep", "none"))
    p.add_argument("--runtime", default="host", choices=KNOWN_RUNTIMES)
    p.add_argument("--extra-none", action="store_true")

    p = add("pack-dirs", cmd_pack_dirs)
    p.add_argument("--registry", required=True)
    p.add_argument("--runtime", default="host", choices=KNOWN_RUNTIMES)

    p = add("pack-set-hash", cmd_pack_set_hash)
    p.add_argument("--registry", required=True)
    p.add_argument("--runtime", default="openshell", choices=KNOWN_RUNTIMES)
    p.add_argument("--override", default="auto", choices=("auto", "keep", "none"))

    p = add("has-packs", cmd_has_packs)
    p.add_argument("--registry", required=True)
    p.add_argument("--runtime", default="host", choices=KNOWN_RUNTIMES)

    p = add("merge-config", cmd_merge_config)
    p.add_argument("--config", required=True)
    p.add_argument("--add", nargs="*", default=[])
    p.add_argument("--remove", nargs="*", default=[])
    p.add_argument("--create", action="store_true")
    p.add_argument("--no-backup", action="store_true")

    p = add("retire-defaults", cmd_retire_defaults)
    p.add_argument("--skills-dir", required=True)
    p.add_argument("--backup-root", default="")
    p.add_argument("--registry", default="")
    p.add_argument("--purge", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--essential", default=None)
    p.add_argument("--hermes-bin", default="")
    p.add_argument("--hermes-home", default="")
    p.add_argument("--hermes-agent-dir", default="")

    p = add("restore-defaults", cmd_restore_defaults)
    p.add_argument("--registry", required=True)
    p.add_argument("--skills-dir", required=True)
    p.add_argument("--hermes-home", required=True)

    p = add("dropins", cmd_dropins)
    p.add_argument("--dir", required=True)

    p = add("stage-context", cmd_stage_context)
    p.add_argument("--registry", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--runtime", default="openshell", choices=KNOWN_RUNTIMES)
    p.add_argument("--override", default="auto", choices=("auto", "keep", "none"))

    p = add("list", cmd_list)
    p.add_argument("--registry", required=True)
    p.add_argument("--hermes-home", default="")

    p = add("verify", cmd_verify)
    p.add_argument("--registry", required=True)
    p.add_argument("--id", default="")
    p.add_argument("--config", default="")
    p.add_argument("--hermes-home", default="")
    p.add_argument("--override", default="auto", choices=("auto", "keep", "none"))

    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    # Machine-readable output is consumed by bash: never emit CRLF.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(newline="\n")
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
