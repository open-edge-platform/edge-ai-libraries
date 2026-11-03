# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""What a source is *for* in one pool: preparing, serving, or deprecated.

A pool-source binding carries two independent facts, kept in the same
`SourceSyncStatus` record:

- `status` -- how far the source has got with the pool's assets
  (pending / indexing / ready / failed). It already existed and is unchanged.
- `serving_state` -- whether this source answers the pool's retrievals.

They are separate because they move separately: a serving source goes back to
`pending` every time an asset is added, and must keep serving while it catches
up; a source that has just been attached is `ready` for nothing yet, and must
not serve until its first full pass is done.

`DISABLED` is never stored. It is what a binding *is* while its source has
`enabled=False`, laid over whatever `serving_state` says, so turning the source
back on restores each binding to where it was.
"""

from datetime import datetime, timezone
from typing import Any, Optional

PREPARING = "PREPARING"
SERVING = "SERVING"
DEPRECATED = "DEPRECATED"
DISABLED = "DISABLED"

#: The states a binding can be stored in.
SERVING_STATES = (PREPARING, SERVING, DEPRECATED)
#: Effective states in which a binding holds no projection and takes no writes.
FROZEN_STATES = frozenset({DEPRECATED, DISABLED})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def effective_state(source: Any, status: Any) -> str:
    """The state that decides behaviour: `DISABLED` overrides the stored one."""
    if source is not None and not getattr(source, "enabled", True):
        return DISABLED
    return getattr(status, "serving_state", SERVING) if status is not None else PREPARING


def is_frozen(source: Any, status: Any) -> bool:
    return effective_state(source, status) in FROZEN_STATES


def transition(status: Any, state: str, reason: str) -> bool:
    """Move a binding to `state`, recording why. False if it was already there."""
    if state not in SERVING_STATES:
        raise ValueError(f"Unknown serving state {state!r}")
    if status.serving_state == state:
        return False
    status.serving_state = state
    status.serving_history.append(
        {"serving_state": state, "at": _now(), "reason": reason}
    )
    return True


def is_caught_up(status: Any, revision: int) -> bool:
    """Whether a binding holds everything the pool did at `revision`."""
    return status.status == "ready" and status.indexed_revision >= revision


def pending_replacement(status: Any) -> Optional[str]:
    """The source this binding is waiting to replace, if it is still preparing."""
    if status.serving_state == PREPARING:
        return status.replaces
    return None


__all__ = [
    "DEPRECATED",
    "DISABLED",
    "FROZEN_STATES",
    "PREPARING",
    "SERVING",
    "SERVING_STATES",
    "effective_state",
    "is_caught_up",
    "is_frozen",
    "pending_replacement",
    "transition",
]
