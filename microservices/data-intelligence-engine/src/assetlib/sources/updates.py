# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""What a caller may change about a source and its bindings, and the checks.

A source is immutable in everything that decides its vectors. Its name, labels
and `enabled` switch may change; anything else is a new source. A binding's
state is never set by a caller -- the one thing they may say about it is which
source it replaces, at attach time.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from assetlib.sources import binding

#: Fields `PATCH /sources/{id}` accepts.
PATCHABLE = frozenset({"name", "enabled", "labels"})


class SourceRuleError(ValueError):
    """A request the multi-source rules refuse -- reported as 422, not 400."""


def check_patch(fields: Mapping[str, Any]) -> Dict[str, Any]:
    """The patch, if every field in it may be changed."""
    refused = sorted(set(fields) - PATCHABLE)
    if refused:
        raise SourceRuleError(
            "Only name, enabled and labels can be changed on a source; "
            f"{', '.join(refused)} cannot. A source's model and parameters are "
            "fixed: create a new source and attach it with `replaces` instead."
        )
    return dict(fields)


def split_replaces(
    configurations: Sequence[Mapping[str, Any]],
) -> Tuple[List[Mapping[str, Any]], Dict[str, str]]:
    """Separate the `replaces` intents from source configurations.

    Returns the configurations without the key, and `{source_id: replaces}` for
    the entries that named one. Only an entry that refers to an existing source
    by id can declare a replacement.
    """
    cleaned: List[Mapping[str, Any]] = []
    replaces: Dict[str, str] = {}
    for configuration in configurations:
        configuration = dict(configuration)
        old = configuration.pop("replaces", None)
        if old:
            source_id = configuration.get("source_id")
            if not source_id:
                raise SourceRuleError("`replaces` needs the entry to name a source_id")
            replaces[str(source_id)] = str(old)
        cleaned.append(configuration)
    return cleaned, replaces


def resolve_ref(ref: str, sources: Mapping[str, Any]) -> str:
    """A source id from an id or a unique name."""
    if ref in sources:
        return ref
    named = [source_id for source_id, source in sources.items() if source.name == ref]
    if len(named) == 1:
        return named[0]
    if named:
        raise SourceRuleError(f"Source name {ref!r} is ambiguous; use its id")
    raise SourceRuleError(f"Source {ref!r} not found")


def check_replacements(
    pool,
    attached_ids: Sequence[str],
    replaces: Mapping[str, str],
    sources: Mapping[str, Any],
) -> None:
    """Refuse a replacement the state machine could not carry out safely."""
    claimed: Dict[str, str] = {
        old: source_id
        for source_id, status in pool.source_statuses.items()
        for old in [binding.pending_replacement(status)]
        if old and source_id not in replaces
    }
    attached = set(attached_ids)
    for new, old in replaces.items():
        if new == old:
            raise SourceRuleError(f"Source {new!r} cannot replace itself")
        status = pool.source_statuses.get(old)
        if status is None:
            raise SourceRuleError(
                f"Source {old!r} is not attached to pool {pool.asset_pool_id!r}, "
                "so there is nothing to replace"
            )
        if old not in attached:
            # The source list is replaced wholesale: leaving the old source out
            # would detach it now, and the pool would serve nothing from it while
            # the new one prepares.
            raise SourceRuleError(
                f"Source {old!r} is being replaced and must stay in the pool's "
                "source list until the replacement has caught up"
            )
        if status.serving_state == binding.DEPRECATED:
            raise SourceRuleError(f"Source {old!r} is already deprecated in this pool")
        if claimed.get(old) not in (None, new):
            raise SourceRuleError(
                f"Source {old!r} is already being replaced by {claimed[old]!r}"
            )
        new_source, old_source = sources.get(new), sources.get(old)
        if (
            new_source is not None
            and old_source is not None
            and new_source.source_type != old_source.source_type
        ):
            raise SourceRuleError(
                f"A {new_source.source_type!r} source cannot replace a "
                f"{old_source.source_type!r} source"
            )
        claimed[old] = new


def drop_stale_replaces(pool, attached_ids: Sequence[str]) -> None:
    """Forget a pending replacement whose target was detached."""
    attached = set(attached_ids)
    for status in pool.source_statuses.values():
        if status.replaces and status.replaces not in attached:
            status.replaces = None


__all__ = [
    "PATCHABLE",
    "SourceRuleError",
    "check_patch",
    "check_replacements",
    "drop_stale_replaces",
    "resolve_ref",
    "split_replaces",
]
