# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import re
from pathlib import Path
from typing import Any, cast

import yaml

from audio_assets import SAFE_FILENAME_PATTERN
from internal_types import (
    InternalAudioDevice,
    InternalAudioPipeline,
    InternalAudioPipelineDefaults,
    InternalAudioPipelineOperation,
    InternalAudioPipelineVariant,
    InternalPipelineType,
    InternalSpeechVoice,
)
from utils import load_thumbnail_as_base64, slugify_text

AUDIO_PIPELINES_DIR = Path(__file__).resolve().parent.parent / "pipelines"
PIPELINE_FIELDS = {
    "name",
    "definition",
    "type",
    "operation",
    "tags",
    "thumbnail",
    "required_models",
    "variants",
    "defaults",
}
PIPELINE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


SUPPORTED_DEVICES = {
    InternalAudioPipelineOperation.SPEECH_TO_TEXT: {"CPU", "GPU", "NPU"},
    InternalAudioPipelineOperation.TEXT_TO_SPEECH: {"CPU", "GPU"},
}


class AudioPipelineManager:
    def __init__(self, pipeline_dir: Path = AUDIO_PIPELINES_DIR) -> None:
        self._pipelines = self._load_pipelines(pipeline_dir)

    def _load_pipelines(self, pipeline_dir: Path) -> dict[str, InternalAudioPipeline]:
        if not pipeline_dir.is_dir():
            raise RuntimeError(f"Audio pipeline directory not found: {pipeline_dir}")
        pipelines: dict[str, InternalAudioPipeline] = {}
        for config_path in sorted(pipeline_dir.glob("*.yaml")):
            pipeline = self._load_pipeline(config_path)
            if pipeline is None:
                continue
            if pipeline.id in pipelines:
                raise ValueError(f"Duplicate Audio pipeline id '{pipeline.id}'")
            pipelines[pipeline.id] = pipeline
        return pipelines

    def _load_pipeline(self, config_path: Path) -> InternalAudioPipeline | None:
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(
                f"Unable to load Audio pipeline '{config_path.name}'"
            ) from exc
        if not isinstance(config, dict):
            raise ValueError(f"Audio pipeline '{config_path.name}' must be a mapping")
        if config.get("type") != InternalPipelineType.AUDIO.value:
            return None
        unknown_fields = set(config) - PIPELINE_FIELDS
        if unknown_fields:
            raise ValueError(
                f"Audio pipeline '{config_path.name}' has unknown fields: "
                f"{', '.join(sorted(unknown_fields))}"
            )

        pipeline_id = config_path.stem
        if PIPELINE_ID_PATTERN.fullmatch(pipeline_id) is None:
            raise ValueError(f"Audio pipeline id '{pipeline_id}' is invalid")
        name = self._required_string(config, "name", config_path)
        description = config.get("definition", "")
        if not isinstance(description, str):
            raise ValueError(f"Audio pipeline '{pipeline_id}' definition must be text")
        try:
            operation = InternalAudioPipelineOperation(config.get("operation"))
        except ValueError as exc:
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' has unsupported operation"
            ) from exc
        tags = config.get("tags", [])
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            raise ValueError(f"Audio pipeline '{pipeline_id}' tags must be text")
        thumbnail_path = config.get("thumbnail", "")
        if not isinstance(thumbnail_path, str):
            raise ValueError(f"Audio pipeline '{pipeline_id}' thumbnail must be text")
        thumbnail = load_thumbnail_as_base64(
            thumbnail_path,
            name,
            base_path=str(config_path.parent),
        )
        required_models = self._load_required_models(pipeline_id, config)
        variants = self._load_variants(pipeline_id, operation, config)
        defaults_config = config.get("defaults")
        if not isinstance(defaults_config, dict):
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' defaults must be a mapping"
            )
        defaults = self._load_defaults(pipeline_id, operation, defaults_config)

        return InternalAudioPipeline(
            id=pipeline_id,
            name=name,
            description=description.strip(),
            type=InternalPipelineType.AUDIO.value,
            operation=operation,
            tags=[tag.strip() for tag in tags],
            thumbnail=thumbnail,
            required_models=required_models,
            variants=variants,
            defaults=defaults,
        )

    def _load_defaults(
        self,
        pipeline_id: str,
        operation: InternalAudioPipelineOperation,
        defaults: dict[str, Any],
    ) -> InternalAudioPipelineDefaults:
        if operation is InternalAudioPipelineOperation.SPEECH_TO_TEXT:
            allowed = {"audio", "language"}
            self._reject_unknown_defaults(pipeline_id, defaults, allowed)
            audio = defaults.get("audio")
            if (
                not isinstance(audio, str)
                or SAFE_FILENAME_PATTERN.fullmatch(audio) is None
                or Path(audio).name != audio
            ):
                raise ValueError(
                    f"Audio pipeline '{pipeline_id}' default audio must be a safe WAV filename"
                )
            language = defaults.get("language", "en")
            if (
                not isinstance(language, str)
                or re.fullmatch(r"[a-z]{2}", language) is None
            ):
                raise ValueError(
                    f"Audio pipeline '{pipeline_id}' language must be a two-letter code"
                )
            return InternalAudioPipelineDefaults(
                audio=audio,
                language=language,
            )

        allowed = {"text", "voice"}
        self._reject_unknown_defaults(pipeline_id, defaults, allowed)
        text = defaults.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 200:
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' default text must be between 1 and 200 characters"
            )
        voice = defaults.get("voice")
        if not isinstance(voice, str):
            raise ValueError(f"Audio pipeline '{pipeline_id}' has unsupported voice")
        try:
            speech_voice = InternalSpeechVoice(voice)
        except ValueError as exc:
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' has unsupported voice"
            ) from exc
        return InternalAudioPipelineDefaults(text=text.strip(), voice=speech_voice)

    def _load_required_models(
        self,
        pipeline_id: str,
        config: dict[str, Any],
    ) -> list[str]:
        required_models = config.get("required_models")
        if not isinstance(required_models, list) or not required_models:
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' required models must be a non-empty list"
            )
        normalized = [
            model.strip() if isinstance(model, str) else "" for model in required_models
        ]
        if not all(normalized) or len(set(normalized)) != len(normalized):
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' required models must be unique text"
            )
        return normalized

    def _load_variants(
        self,
        pipeline_id: str,
        operation: InternalAudioPipelineOperation,
        config: dict[str, Any],
    ) -> list[InternalAudioPipelineVariant]:
        variants_config = config.get("variants")
        if not isinstance(variants_config, list) or not variants_config:
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' must define at least one variant"
            )
        variants: list[InternalAudioPipelineVariant] = []
        variant_ids: set[str] = set()
        for variant_config in variants_config:
            if not isinstance(variant_config, dict) or set(variant_config) != {
                "name",
                "device",
            }:
                raise ValueError(
                    f"Audio pipeline '{pipeline_id}' variant must contain name and device"
                )
            name = variant_config.get("name")
            device = variant_config.get("device")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    f"Audio pipeline '{pipeline_id}' variant name must be text"
                )
            if device not in SUPPORTED_DEVICES[operation]:
                raise ValueError(
                    f"Audio pipeline '{pipeline_id}' variant has unsupported device"
                )
            variant_id = slugify_text(name.strip())
            if (
                PIPELINE_ID_PATTERN.fullmatch(variant_id) is None
                or variant_id in variant_ids
            ):
                raise ValueError(
                    f"Audio pipeline '{pipeline_id}' has duplicate variant id '{variant_id}'"
                )
            variant_ids.add(variant_id)
            variants.append(
                InternalAudioPipelineVariant(
                    id=variant_id,
                    name=name.strip(),
                    device=cast(InternalAudioDevice, device),
                )
            )
        return variants

    @staticmethod
    def _required_string(config: dict[str, Any], field: str, path: Path) -> str:
        value = config.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Audio pipeline '{path.name}' field '{field}' must be non-empty text"
            )
        return value.strip()

    @staticmethod
    def _reject_unknown_defaults(
        pipeline_id: str,
        defaults: dict[str, Any],
        allowed: set[str],
    ) -> None:
        unknown = set(defaults) - allowed
        if unknown:
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' defaults have unknown fields: "
                f"{', '.join(sorted(unknown))}"
            )

    def list_pipelines(self) -> list[InternalAudioPipeline]:
        return list(self._pipelines.values())

    def get_pipeline(self, pipeline_id: str) -> InternalAudioPipeline | None:
        return self._pipelines.get(pipeline_id)


_default_manager: AudioPipelineManager | None = None


def get_audio_pipeline_manager() -> AudioPipelineManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = AudioPipelineManager()
    return _default_manager
