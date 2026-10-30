# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The one generic probe runner.

Every probe — for every backend — runs this identical loop:

    tick → GET(endpoint) → extract fields → aggregate each field → publish

The only thing that varies between probes is the :class:`ProbeSpec` (config),
never the code.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List

from src.providers.probes.aggregator import MetricAggregator
from src.providers.probes.extract import FieldExtractor
from src.providers.probes.publish import Sink, build_sink
from src.providers.probes.spec import ProbeSpec


if TYPE_CHECKING:
    from src.providers.probes.host import ProbeHost


logger = logging.getLogger(__name__)


class ProviderProbe:
    """A single provider probe: an asyncio task running the generic pipeline.

    ``host`` is the provider that owns this probe; the probe asks it for an
    authenticated HTTP client (``probe_client()``) and borrows its ``endpoint``
    when the spec omits one. Everything else — what to parse, how to aggregate,
    where to publish — is declared by ``spec``.
    """

    def __init__(self, spec: ProbeSpec, host: "ProbeHost"):
        self.spec = spec
        self.host = host
        self._extractors: List[FieldExtractor] = [
            FieldExtractor(rule) for rule in spec.extract
        ]
        self._aggregator = MetricAggregator(
            window=spec.aggregate.window,
            method=spec.aggregate.method,
            max_series=spec.max_series,
        )
        self._sinks: List[Sink] = [build_sink(p) for p in spec.publish]
        self._task: asyncio.Task | None = None
        # Liveness/health counters — surfaced by ``snapshot()``. A failed request
        # has no body to parse, so success/failure lives here, not in extraction.
        self._success = 0
        self._fail = 0
        self._miss = 0

    # ---- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Launch the tick loop as a background task (idempotent)."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(
            self._run(), name=f"probe:{self.host.name}:{self.spec.name}"
        )

    def cancel(self) -> None:
        """Request cancellation of the tick loop. Safe to call from sync code.

        Cancelling an ``asyncio.Task`` is synchronous; the loop observes
        ``CancelledError`` on its next scheduling and runs its own cleanup
        (closing the HTTP client), so shutdown needn't await.
        """
        if self._task is not None:
            self._task.cancel()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ---- the identical pipeline --------------------------------------------

    async def _run(self) -> None:
        """Tick forever: build a client once, then GET/extract/aggregate/publish."""
        endpoint = self.spec.endpoint or getattr(self.host, "endpoint", None)
        if not endpoint:
            logger.warning(
                "probe %r on provider %r has no endpoint (spec or provider); not running",
                self.spec.name, self.host.name,
            )
            return

        client = await self.host.probe_client()
        try:
            while True:
                try:
                    await self._tick(client, endpoint)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - a probe must never die on a bad tick
                    logger.warning(
                        "probe %r on provider %r tick error: %s",
                        self.spec.name, self.host.name, exc,
                    )
                await asyncio.sleep(self.spec.interval)
        except asyncio.CancelledError:
            pass
        finally:
            await client.aclose()

    async def _tick(self, client, endpoint: str) -> None:
        """One iteration of the pipeline."""
        try:
            response = await client.request(
                self.spec.method, endpoint, timeout=self.spec.timeout
            )
        except Exception as exc:  # transport error — nothing to parse this tick
            self._fail += 1
            logger.debug(
                "probe %r GET %s failed: %s", self.spec.name, endpoint, exc
            )
            return

        self._success += 1
        fields = self._extract(response.text)
        if not fields:
            # No matches this tick — record a miss; windows keep prior samples.
            self._miss += 1

        self._aggregator.add(fields)
        aggregates = self._aggregator.values()
        for sink in self._sinks:
            try:
                sink.emit(self, aggregates)
            except Exception as exc:  # noqa: BLE001 - one bad sink must not kill the tick
                logger.warning(
                    "probe %r sink error: %s", self.spec.name, exc
                )

    def _extract(self, text: str) -> Dict[str, float]:
        """Merge every extract rule's ``{name: value}`` pairs for this tick."""
        merged: Dict[str, float] = {}
        for extractor in self._extractors:
            merged.update(extractor.apply(text))
        return merged

    # ---- read path ----------------------------------------------------------

    def snapshot(self) -> dict:
        """Live programmatic view of this probe — aggregates + counters.

        Surfaced by :meth:`ProbeHost.probe_snapshot`. The durable read path for
        probe values is the file sink; this in-memory view is for tests and
        programmatic inspection.
        """
        return {
            "running": self.running,
            "window": self.spec.aggregate.window,
            "method": self.spec.aggregate.method,
            "aggregates": self._aggregator.values(),
            "counters": {
                "success": self._success,
                "fail": self._fail,
                "miss": self._miss,
            },
        }
