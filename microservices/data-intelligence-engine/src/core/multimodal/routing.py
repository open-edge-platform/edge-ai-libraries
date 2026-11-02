# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asset scope and representation policy, independent of model loading.

Selectors retain their precision (``mp4`` is not widened to all video). Only
model selection uses their coarse asset family. Effective filters are frozen
in the source profile, not recomputed when a source is restored.
"""

import mimetypes
from typing import Any, Mapping

from core.content import (
    AUDIO, IMAGE, VIDEO, MM_ROLES, ROLE_to_KIND,
    ROLE_IMAGE, ROLE_AUDIO, ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO,
    ROLE_L1_SEGMENT, ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI,
)

MEDIA_TYPES = frozenset({IMAGE, VIDEO, AUDIO})
DEFAULT_ROLES = {
    IMAGE: frozenset({ROLE_IMAGE}),
    VIDEO: frozenset({ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO, ROLE_L1_SEGMENT}),
    AUDIO: frozenset({ROLE_L2_TRANSCRIPT}),
}
ASSET_ROLES = {
    IMAGE: DEFAULT_ROLES[IMAGE] | {ROLE_L2_CAPTION, ROLE_L3_WIKI},
    VIDEO: DEFAULT_ROLES[VIDEO] | {ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI},
    AUDIO: DEFAULT_ROLES[AUDIO] | {ROLE_AUDIO, ROLE_L2_CAPTION, ROLE_L3_WIKI},
}


def string_list(options: Mapping[str, Any], key: str) -> list[str]:
    raw = options.get(key)
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)) or any(
        not isinstance(value, str) or not value.strip().lstrip('.') for value in raw
    ):
        raise ValueError(f"{key} must be an array of nonempty strings")
    return sorted({value.strip().lower().lstrip('.') for value in raw})


def asset_family(selector: str) -> str:
    selector = selector.strip().lower().lstrip('.')
    if selector in MEDIA_TYPES:
        return selector
    mime = selector if '/' in selector else mimetypes.guess_type(f"asset.{selector}")[0]
    family = (mime or '').split('/')[0]
    return family if family in MEDIA_TYPES else "document"


def asset_families(options: Mapping[str, Any]) -> set[str]:
    return {asset_family(value) for value in string_list(options, 'asset_types')}


def require_asset_types(options: Mapping[str, Any]) -> set[str]:
    families = asset_families(options)
    if not families or not families <= MEDIA_TYPES:
        raise ValueError(
            'A multimodal source requires nonempty asset_types containing only '
            'supported media selectors (image, video, audio); recreate/replace '
            'the source with asset_types. block_kinds is not a model selector.'
        )
    return families


def representation(options: Mapping[str, Any]) -> tuple[dict, set[str]]:
    """Effective routing and roles used to choose a model at source creation.

    Explicit roles select a representation *before* selecting its encoder. An
    empty role filter keeps the asset's default model choice but imposes no role
    restriction. Empty kind filters likewise remain explicit overrides.
    """
    families = require_asset_types(options)
    roles = set(string_list(options, 'block_roles'))
    unknown = roles - MM_ROLES
    if unknown:
        raise ValueError(f"Unknown block_roles {', '.join(sorted(unknown))}")
    available = set().union(*(ASSET_ROLES[kind] for kind in families))
    if roles - available:
        raise ValueError(
            f"block_roles {sorted(roles - available)} do not belong to asset_types "
            f"{sorted(families)}"
        )
    selected = roles or set().union(*(DEFAULT_ROLES[kind] for kind in families))
    kinds = string_list(options, 'block_kinds')
    if kinds:
        possible = {
            role for role in selected
            if ROLE_to_KIND[role] in kinds
            or (role == ROLE_L2_TRANSCRIPT and AUDIO in kinds)
        }
        if not possible:
            raise ValueError('block_kinds excludes the selected asset representation')
        # A kind filter cannot silently discard an explicitly requested role.
        if roles and possible != selected:
            raise ValueError('block_kinds conflicts with the selected block_roles')
        selected = possible
    effective = {'asset_types': string_list(options, 'asset_types')}
    effective['block_roles'] = (
        string_list(options, 'block_roles') if 'block_roles' in options else sorted(selected)
    )
    effective['block_kinds'] = (
        kinds if 'block_kinds' in options
        else sorted({ROLE_to_KIND[role] for role in selected})
    )
    return effective, selected


def effective_configuration(source: Any) -> dict:
    """User options plus frozen defaults, without consulting today's defaults."""
    return {
        **dict(getattr(source, 'configuration', {}) or {}),
        **dict((getattr(source, 'profile', {}) or {}).get('params') or {}),
    }


def validate_model_options(options: Mapping[str, Any]) -> None:
    """Public model selection is an ID, not a path or weight override.

    Call on persisted source options, never the private projection configuration
    whose model path is injected from a frozen profile.
    """
    for key in ('embedding_model_path', 'precision'):
        if key in options:
            raise ValueError(
                f'Invalid operator_options.{key}; select a prepared model with '
                'embedding_model under ENGINE_MODEL_ROOT_PATH'
            )


def validate_source(source: Any) -> None:
    """Validate a frozen source's routing without resolving a model/default.

    In particular, a legacy media profile cannot supply a missing user asset
    declaration. Reconciliation must keep that record, but refuse to execute it.
    """
    raw = dict(source.configuration or {})
    options = effective_configuration(source)
    validate_model_options(raw)
    validate_model_options(options)
    profile = source.profile or {}
    if profile.get('encoder_kind') == 'multimodal':
        require_asset_types(raw)
        representation(options)
        return
    validate_options(options)


def validate_options(options: Mapping[str, Any]) -> None:
    """Reject unscoped media declarations, retaining document/figure defaults."""
    validate_model_options(options)
    for key in ('asset_types', 'block_kinds', 'block_roles'):
        string_list(options, key)
    kinds = set(string_list(options, 'block_kinds'))
    roles = set(string_list(options, 'block_roles'))
    # A document source can legitimately select prose and PDF figures. Pure
    # media/derived representations must not bypass the required media scope.
    if not asset_families(options) and (
        kinds & {AUDIO, VIDEO}
        or (IMAGE in kinds and 'text' not in kinds)
        or roles & {ROLE_AUDIO, ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO, ROLE_L1_SEGMENT,
                    ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI}
    ):
        require_asset_types(options)