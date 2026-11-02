# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Provider probes — internal helpers (no public API).

A **probe** is a per-provider background task that, on a fixed interval, GETs a
configured endpoint, extracts numeric fields with regex/JSON, aggregates each
field over a sliding window, and publishes each one — keyed by its parsed field
name under a probe prefix — to a sink (provider metadata, a file, or both).

There is no per-backend probe code: one generic
:class:`~src.providers.probes.probe.ProviderProbe` is parameterised entirely by
a :class:`~src.providers.probes.spec.ProbeSpec` parsed from ``config.yaml``.
"""
from __future__ import annotations

import logging
from typing import Any, List

from src.providers.probes.host import ProbeHost
from src.providers.probes.probe import ProviderProbe
from src.providers.probes.spec import ProbeConfigError, ProbeSpec


logger = logging.getLogger(__name__)


def build_probes(spec_list: List[dict[str, Any]], host: "ProbeHost") -> List[ProviderProbe]:
    """Parse raw ``settings.probes`` entries into enabled :class:`ProviderProbe`s.

    Only probes with ``enabled: true`` are returned (lifecycle = the enabled
    flag). A malformed individual spec is logged and skipped rather than sinking
    the whole provider.
    """
    probes: List[ProviderProbe] = []
    for raw in spec_list or []:
        try:
            spec = ProbeSpec.from_mapping(raw)
        except ProbeConfigError as exc:
            logger.error(
                "skipping invalid probe on provider %r: %s", host.name, exc
            )
            continue
        if not spec.enabled:
            continue
        probes.append(ProviderProbe(spec, host))
    return probes


__all__ = ["ProbeHost", "ProviderProbe", "ProbeSpec", "build_probes"]
