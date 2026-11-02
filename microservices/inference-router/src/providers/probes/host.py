# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""``ProbeHost`` — the provider-side mixin that owns probes.

Both provider families (``LitellmProvider`` and ``PassthroughProvider``) mix this
in. The provider does not decide *what* a probe parses (that is config); its job
shrinks to **owning** the probes and giving them the one thing only it knows: an
authenticated HTTP client. ``probe_client()`` is the only per-provider seam.

A host must set two attributes in its ``__init__`` (both providers already carry
the auth ones):

- ``probe_specs``: the raw ``settings.probes`` list (default ``[]``)
- ``name``, ``endpoint``, ``api_key``, ``auth_scheme``, ``custom_headers``
"""
from __future__ import annotations

import logging
from typing import Dict, List

import httpx


logger = logging.getLogger(__name__)


class ProbeHost:
    """Concrete, shared probe lifecycle mixed into providers."""

    # The single member the host owns. Declared here for clarity; populated by
    # ``start_probes`` (guarded reads use ``getattr`` so an un-started host is
    # safe to snapshot/stop).
    _probes: "Dict[str, object]"

    async def start_probes(self) -> None:
        """Build and launch every ``enabled`` probe from ``probe_specs``.

        Called from the orchestrator's ``initialize()`` (boot) and on every
        provider rebuild (a config edit tears down the old provider and builds a
        new one). Disabled probes are simply never launched.
        """
        # Imported here to avoid a circular import at module load time
        # (probes package -> providers.base -> providers.__init__).
        from src.providers.probes import build_probes

        self._probes = {}
        specs = getattr(self, "probe_specs", None) or []
        try:
            probes = build_probes(specs, host=self)
        except Exception as exc:  # noqa: BLE001 - a bad probe spec must not sink the provider
            logger.error(
                "failed to build probes for provider %r: %s", self.name, exc
            )
            return

        for probe in probes:
            probe.start()
            self._probes[probe.spec.name] = probe
        if self._probes:
            logger.info(
                "provider %r started %d probe(s): %s",
                self.name, len(self._probes), ", ".join(self._probes),
            )

    def stop_probes(self) -> None:
        """Cancel every probe task and clear the set.

        Synchronous by design so it composes with the orchestrator's synchronous
        ``shutdown()``: cancelling a task needs no await, and each probe closes
        its HTTP client in its own ``finally``.
        """
        for probe in getattr(self, "_probes", {}).values():
            probe.cancel()
        self._probes = {}

    def probe_snapshot(self) -> Dict[str, dict]:
        """Per-probe live view (aggregates + counters) for programmatic reads."""
        return {
            name: probe.snapshot()
            for name, probe in getattr(self, "_probes", {}).items()
        }

    async def probe_client(self) -> httpx.AsyncClient:
        """Return an authenticated HTTP client for probe requests.

        The only per-provider seam. Default builds auth headers from the same
        ``api_key`` / ``auth_scheme`` / ``custom_headers`` the provider already
        uses for chat/forwarding. Override to customise (e.g. mTLS).
        """
        headers: Dict[str, str] = {}
        api_key = getattr(self, "api_key", None)
        scheme = getattr(self, "auth_scheme", "bearer")
        if api_key and scheme in ("bearer", "api_key"):
            if scheme == "bearer":
                headers["Authorization"] = f"Bearer {api_key}"
            else:
                headers["api-key"] = api_key
        custom = getattr(self, "custom_headers", None)
        if custom:
            headers.update(custom)
        return httpx.AsyncClient(headers=headers)
