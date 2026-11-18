# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections import defaultdict

from .concept import Concept, norm_title
from .llmclient import parse_json
from .prompts import render_canonicalize

MergedKey = tuple[str, str]   # (type, norm_title)


def merge_same_title(concepts: list[Concept]) -> dict[MergedKey, Concept]:
    """Fold concepts with the same (type, norm_title(title)); the first-seen title is the surface form."""
    out: dict[MergedKey, Concept] = {}
    for c in concepts:
        title = (c.title or "").strip()
        ctype = (c.type or "").strip()
        if not title or not ctype:
            continue
        k = (ctype, norm_title(title))
        m = out.get(k)
        if m is None:
            m = out[k] = Concept(type=ctype, title=title)
        for sf in c.source_files:
            if sf not in m.source_files:
                m.source_files.append(sf)
        for summ, rp in c.summaries:
            if summ:
                m.summaries.append((summ, rp))
        for pair in c.links:
            if pair not in m.links:
                m.links.append(pair)
    return out


def _evidence_card(rid: int, c: Concept, max_roles: int, max_role_len: int) -> str:
    roles: list[str] = []
    seen: set[str] = set()
    for s, _rp in c.summaries:
        s = " ".join(s.split())
        if not s or s in seen:
            continue
        seen.add(s)
        roles.append(s[:max_role_len] + ("…" if len(s) > max_role_len else ""))
        if len(roles) >= max_roles:
            break
    lines = [f"[{rid}] title: {c.title}"]
    if roles:
        lines.append(f"  roles: {'; '.join(roles)}")
    lines.append(f"  sources: {len(c.source_files)} file(s)")
    return "\n".join(lines)


def _valid_groups(groups, n: int) -> list[dict]:
    """Keep well-formed groups: members are in-range ints, deduped, >=2."""
    out: list[dict] = []
    if not isinstance(groups, list):
        return out
    for g in groups:
        if not isinstance(g, dict):
            continue
        members = g.get("members", [])
        if not isinstance(members, list):
            continue
        rids: list[int] = []
        for r in members:
            if isinstance(r, bool):
                continue
            if isinstance(r, int) and 0 <= r < n and r not in rids:
                rids.append(r)
        if len(rids) >= 2:
            out.append({"members": rids, "reason": str(g.get("reason", ""))})
    return out


def propose_clusters(cfg, client, merged: dict[MergedKey, Concept], ui=None,
                     instructions: dict | None = None) -> list[dict]:
    """Ask the LLM for a merge plan: groups of {type, canonical_title, members (titles), reason}."""
    from .ui import UI
    ui = ui or UI(enabled=False)
    max_roles = int(cfg.merge.get("max_roles", 4))
    max_gloss = int(cfg.merge.get("max_gloss", 60))
    # Per-run `instructions` override config.yaml.
    instructions = instructions if instructions is not None else cfg.instructions
    canon_template = cfg.prompt_path("canonicalize")

    by_type: dict[str, list[MergedKey]] = defaultdict(list)
    for k in merged:
        by_type[k[0]].append(k)

    plan: list[dict] = []
    for ctype, keys in by_type.items():
        keys = sorted(keys)                       # stable order == row-id order
        cs = [merged[k] for k in keys]
        if len(cs) < 2:
            continue

        cards = [_evidence_card(i, c, max_roles, max_gloss) for i, c in enumerate(cs)]
        prompt = render_canonicalize(
            ctype, "\n".join(cards), instructions, template_path=canon_template
        )
        groups: list[dict] = []
        try:
            with ui.spinner(f"canonicalize {ctype} ({len(cs)} concepts)"):
                raw = client.chat(
                    [{"role": "user", "content": prompt}], max_tokens=2048
                )["message"]["content"]
            groups = _valid_groups(parse_json(raw).get("groups", []), len(cs))
        except Exception as e:  # noqa: BLE001
            ui.warn(f"canonicalize [{ctype}] failed, merging nothing: {type(e).__name__}: {e}")

        # each row joins at most one group (first wins)
        member_of: set[int] = set()
        for g in groups:
            rids = [r for r in g["members"] if r not in member_of]
            if len(rids) < 2:
                continue
            member_of.update(rids)
            members = [cs[r] for r in rids]
            plan.append({
                "type": ctype,
                "canonical_title": _pick_canonical(members).title,
                "members": [m.title for m in members],
                "reason": str(g.get("reason", "")),
            })
    return plan


def apply_clusters(merged: dict[MergedKey, Concept],
                   plan: list[dict]) -> dict[MergedKey, Concept]:
    """Fold concepts per a (possibly human-edited) merge plan; a non-empty `canonical_title` wins."""
    # Any-type lookup: a human may group across types.
    by_norm_key: dict[str, MergedKey] = {}
    for k in merged:
        by_norm_key.setdefault(norm_title(k[1]), k)

    result: dict[MergedKey, Concept] = {}
    consumed: set[MergedKey] = set()
    for g in plan:
        resolved: list[MergedKey] = []
        for title in g.get("members", []):
            k = by_norm_key.get(norm_title(title))
            if k is None or k in consumed or k in resolved:
                continue                          # stale/typo/dupe -> skip defensively
            resolved.append(k)
        if len(resolved) < 2:
            continue                              # nothing to merge -> leave as singletons
        members = [merged[k] for k in resolved]
        canon = (g.get("canonical_title") or "").strip() or _pick_canonical(members).title
        ctype = members[0].type
        folded = Concept(type=ctype, title=canon)
        for m in members:
            for sf in m.source_files:
                if sf not in folded.source_files:
                    folded.source_files.append(sf)
            folded.summaries.extend(m.summaries)
            for pair in m.links:
                if pair not in folded.links:
                    folded.links.append(pair)
        result[(ctype, norm_title(folded.title))] = folded
        consumed.update(resolved)

    # Pass through unfolded concepts; first write wins on a canonical collision.
    for k, c in merged.items():
        if k not in consumed:
            result.setdefault(k, c)
    return result


def canonicalize(cfg, client, merged: dict[MergedKey, Concept], ui=None,
                 instructions: dict | None = None) -> dict[MergedKey, Concept]:
    """Propose then apply a merge plan with no human review."""
    plan = propose_clusters(cfg, client, merged, ui=ui, instructions=instructions)
    return apply_clusters(merged, plan)


def _pick_canonical(members: list[Concept]) -> Concept:
    """Canonical = most source_files, then longest title, then title."""
    return max(members, key=lambda c: (len(c.source_files), len(c.title), c.title))


def redirect_links(merged: dict[MergedKey, Concept]) -> dict:
    """Remap link targets in place to surviving titles, dropping self/unresolved/duplicate links; returns stats."""
    # Any-type match (relations cross types).
    by_norm: dict[str, str] = {}
    for c in merged.values():
        by_norm.setdefault(norm_title(c.title), c.title)

    stats = {"kept": 0, "unresolved": 0, "examples": []}
    for c in merged.values():
        seen: set[tuple[str, str]] = set()
        fixed: list[tuple[str, str]] = []
        for to_title, rel in c.links:
            resolved = by_norm.get(norm_title(to_title))
            if not resolved:
                stats["unresolved"] += 1
                if len(stats["examples"]) < 5:
                    stats["examples"].append(f"{c.title} -> {to_title}")
                continue                                   # target didn't survive -> drop
            if norm_title(resolved) == norm_title(c.title):
                continue                                   # self-link -> drop
            key = (norm_title(resolved), rel)
            if key in seen:
                continue                                   # dupe -> drop
            seen.add(key)
            fixed.append((resolved, rel))
        c.links = fixed
        stats["kept"] += len(fixed)
    return stats
