# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""What this deployment can do, read once at startup."""

from __future__ import annotations

from dataclasses import dataclass

from .clients import VssClient


@dataclass(frozen=True, slots=True)
class Features:
    """The VSS capabilities this server builds a tool surface for."""

    summary: bool
    search: bool
    #: Whether a frame-embedding search index is deployed (dual/search-only
    #: mode), as opposed to a caption-embedding-only index (unified mode).
    #: Mirrors ``FeaturesService.isImageSearchEnabled()`` in the backend, the
    #: only reliable signal for telling dual and unified mode apart, since
    #: both report identical ``summary``/``search`` flags.
    image_search_enabled: bool = False

    def describe(self) -> str:
        """Return the enabled features as a phrase, e.g. ``summary, search``."""

        names = [
            name
            for name, on in (("summary", self.summary), ("search", self.search))
            if on
        ]
        return ", ".join(names) or "none"


#: Every feature on, for callers that build the surface directly (tests).
ALL_FEATURES = Features(summary=True, search=True, image_search_enabled=True)


async def detect_features(client: VssClient) -> Features:
    """Read which features this deployment has.

    Anything but exactly ``FEATURE_ON`` counts as off, matching
    ``features.service.ts``.

    Raises:
        VssError: If the deployment cannot be reached.
    """

    raw = await client.get_features()
    return Features(
        summary=raw.get("summary") == "FEATURE_ON",
        search=raw.get("search") == "FEATURE_ON",
        image_search_enabled=bool(raw.get("imageSearchEnabled", False)),
    )
