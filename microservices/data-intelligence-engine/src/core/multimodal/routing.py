# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asset scope and representation policy for sources, independent of model loading."""

import mimetypes
from typing import Any, Mapping

from core.content import (
    AUDIO, DOCUMENT, IMAGE, VIDEO, MM_ROLES, ROLE_to_KIND, asset_family,
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


def asset_families(options: Mapping[str, Any]) -> set[str]:
    return {asset_family(value) for value in string_list(options, 'asset_types')}


def validate_asset_types(options: Mapping[str, Any]) -> None:
    """Refuse a vector source's `asset_types` entry that no asset can match."""
    from core.extractor import is_supported  # noqa: PLC0415

    unknown = []
    for value in string_list(options, 'asset_types'):
        if value == 'okf':
            raise ValueError('asset_types "okf" is for a graph source; a vector source never takes OKF bundles')
        extensions = mimetypes.guess_all_extensions(value) if '/' in value else [f".{value}"]
        if value not in MEDIA_TYPES | {DOCUMENT} and not any(
            is_supported(f"asset{extension}") for extension in extensions
        ):
            unknown.append(value)
    if unknown:
        raise ValueError(
            f"Unknown asset_types {', '.join(unknown)}: use document, image, video, "
            "audio, or the extension or MIME type of a supported file"
        )


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
    """Effective routing and roles used to choose a model at source creation."""
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
    """User options plus frozen profile params; an unscoped text vector source takes documents."""
    options = {
        **dict(getattr(source, 'configuration', {}) or {}),
        **dict((getattr(source, 'profile', {}) or {}).get('params') or {}),
    }
    if (
        getattr(source, 'source_type', None) == 'vector'
        and (getattr(source, 'profile', None) or {}).get('encoder_kind') != 'multimodal'
        and not options.get('asset_types')
    ):
        options['asset_types'] = [DOCUMENT]
    return options


def validate_model_options(options: Mapping[str, Any]) -> None:
    """Reject path/precision overrides in persisted source options; models are selected by ID."""
    for key in ('embedding_model_path', 'precision'):
        if key in options:
            raise ValueError(
                f'Invalid operator_options.{key}; select a prepared model with '
                'embedding_model under ENGINE_MODEL_ROOT_PATH'
            )


def validate_source(source: Any) -> None:
    """Validate a frozen source's routing without resolving a model/default."""
    raw = dict(source.configuration or {})
    options = effective_configuration(source)
    validate_model_options(raw)
    validate_model_options(options)
    profile = source.profile or {}
    if profile.get('encoder_kind') == 'multimodal':
        from core.multimodal.registry import model_for_record

        model_for_record(profile.get('multimodal_model') or {})
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
    # Media/derived selections without asset_types require a media scope.
    if not asset_families(options) and (
        kinds & {AUDIO, VIDEO}
        or (IMAGE in kinds and 'text' not in kinds)
        or roles & {ROLE_AUDIO, ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO, ROLE_L1_SEGMENT,
                    ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI}
    ):
        require_asset_types(options)