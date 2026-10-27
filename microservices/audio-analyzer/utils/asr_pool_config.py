"""Single source of truth for per-pool ASR model configuration.

The service runs two ASR model pools (see the ``_models`` docstring in
``components/asr_component.py``):

* ``final``   — persisted commits and the file-based endpoint.
* ``preview`` — non-destructive realtime snapshots, which may optionally be
  routed to a different model/device via ``models.asr.preview``.

Every key under ``models.asr.preview`` is optional and falls back to the main
``models.asr`` value, so a deployment can override just ``device:`` without
also having to restate ``name:``/``provider:``. Resolving that fallback in one
place keeps the pipeline, the model pre-export step and the model-path lookup
from drifting apart — and from assuming keys the user never set.
"""

from __future__ import annotations

from dataclasses import dataclass

from utils.config_loader import config

POOL_FINAL = "final"
POOL_PREVIEW = "preview"
POOLS = (POOL_FINAL, POOL_PREVIEW)


@dataclass(frozen=True)
class AsrPoolConfig:
    """Fully resolved ASR settings for one pool."""

    pool: str
    provider: str
    name: str
    device: str
    weight_format: str | None

    @property
    def is_preview(self) -> bool:
        return self.pool == POOL_PREVIEW


def get_preview_override():
    """Return the raw ``models.asr.preview`` config node, or ``None``."""
    return getattr(config.models.asr, "preview", None)


def resolve_pool_config(pool: str, device_override: str | None = None) -> AsrPoolConfig:
    """Resolve the model settings a pool actually runs with.

    Args:
        pool: ``POOL_FINAL`` or ``POOL_PREVIEW``.
        device_override: Per-request device, honoured for the final pool only.
            The preview pool is an internal latency optimisation, not a
            caller-selectable path.

    Returns:
        The resolved :class:`AsrPoolConfig`.

    Raises:
        ValueError: If ``pool`` is not a known pool name.
    """
    if pool not in POOLS:
        raise ValueError(f"Unsupported ASR pool: {pool!r}; expected one of {POOLS}")

    asr = config.models.asr
    main_weight_format = getattr(asr, "weight_format", None)

    override = get_preview_override() if pool == POOL_PREVIEW else None
    if override is None:
        return AsrPoolConfig(
            pool=pool,
            provider=asr.provider,
            name=asr.name,
            device=device_override or asr.device,
            weight_format=main_weight_format,
        )

    # Every key is optional — fall back to the main ASR config for any the
    # deployment did not set, including `device`, so a host without the
    # overridden device never fails to load the preview model.
    return AsrPoolConfig(
        pool=pool,
        provider=getattr(override, "provider", None) or asr.provider,
        name=getattr(override, "name", None) or asr.name,
        device=getattr(override, "device", None) or asr.device,
        weight_format=getattr(override, "weight_format", None) or main_weight_format,
    )


def preview_differs_from_final() -> bool:
    """True when the preview pool resolves to a different model than the final pool.

    Used to skip redundant work (a second identical model export, a second
    cache entry) when ``models.asr.preview`` only overrides the device.
    """
    if get_preview_override() is None:
        return False
    preview = resolve_pool_config(POOL_PREVIEW)
    final = resolve_pool_config(POOL_FINAL)
    return (preview.provider, preview.name, preview.weight_format) != (
        final.provider,
        final.name,
        final.weight_format,
    )
