# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from audio_assets import AudioAssetsManager, SAFE_FILENAME_PATTERN
from utils import load_thumbnail_as_base64, slugify_text

AUDIO_PIPELINES_DIR = Path(__file__).resolve().parent.parent / "pipelines" / "audio"
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
SPEECH_VOICES = {"Ryan", "Miles", "Aaron", "Nora", "Elena", "Kabir", "Angus"}
PIPELINE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class AudioPipelineOperation(str, Enum):
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"


SUPPORTED_DEVICES = {
    AudioPipelineOperation.SPEECH_TO_TEXT: {"CPU", "GPU", "NPU"},
    AudioPipelineOperation.TEXT_TO_SPEECH: {"CPU", "GPU"},
}


@dataclass(frozen=True)
class AudioPipelineVariant:
    id: str
    name: str
    device: str


@dataclass(frozen=True)
class AudioPipelineDefaults:
    audio: str | None = None
    language: str | None = None
    text: str | None = None
    voice: str | None = None


@dataclass(frozen=True)
class AudioPipeline:
    id: str
    name: str
    description: str
    type: str
    operation: AudioPipelineOperation
    tags: list[str]
    thumbnail: str | None
    required_models: list[str]
    variants: list[AudioPipelineVariant]
    defaults: AudioPipelineDefaults
    available: bool
    unavailable_reason: str | None = None


class AudioPipelineManager:
    def __init__(
        self,
        pipeline_dir: Path = AUDIO_PIPELINES_DIR,
        assets: AudioAssetsManager | None = None,
    ) -> None:
        self._assets = assets or AudioAssetsManager()
        self._pipelines = self._load_pipelines(pipeline_dir)

    def _load_pipelines(self, pipeline_dir: Path) -> dict[str, AudioPipeline]:
        if not pipeline_dir.is_dir():
            raise RuntimeError(f"Audio pipeline directory not found: {pipeline_dir}")
        pipelines: dict[str, AudioPipeline] = {}
        for config_path in sorted(pipeline_dir.glob("*.yaml")):
            pipeline = self._load_pipeline(config_path)
            if pipeline.id in pipelines:
                raise ValueError(f"Duplicate Audio pipeline id '{pipeline.id}'")
            pipelines[pipeline.id] = pipeline
        return pipelines

    def _load_pipeline(self, config_path: Path) -> AudioPipeline:
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(
                f"Unable to load Audio pipeline '{config_path.name}'"
            ) from exc
        if not isinstance(config, dict):
            raise ValueError(f"Audio pipeline '{config_path.name}' must be a mapping")
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
        if config.get("type") != "audio":
            raise ValueError(f"Audio pipeline '{pipeline_id}' type must be 'audio'")
        try:
            operation = AudioPipelineOperation(config.get("operation"))
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
            base_path=str(config_path.parent.parent),
        )
        required_models = self._load_required_models(pipeline_id, config)
        variants = self._load_variants(pipeline_id, operation, config)
        defaults_config = config.get("defaults")
        if not isinstance(defaults_config, dict):
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' defaults must be a mapping"
            )
        defaults = self._load_defaults(pipeline_id, operation, defaults_config)

        available = True
        unavailable_reason = None
        if operation is AudioPipelineOperation.SPEECH_TO_TEXT:
            available = self._assets.get_path(defaults.audio or "") is not None
            if not available:
                unavailable_reason = "Default audio input is unavailable."
        return AudioPipeline(
            id=pipeline_id,
            name=name,
            description=description.strip(),
            type="audio",
            operation=operation,
            tags=[tag.strip() for tag in tags],
            thumbnail=thumbnail,
            required_models=required_models,
            variants=variants,
            defaults=defaults,
            available=available,
            unavailable_reason=unavailable_reason,
        )

    def _load_defaults(
        self,
        pipeline_id: str,
        operation: AudioPipelineOperation,
        defaults: dict[str, Any],
    ) -> AudioPipelineDefaults:
        if operation is AudioPipelineOperation.SPEECH_TO_TEXT:
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
            return AudioPipelineDefaults(
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
        if voice not in SPEECH_VOICES:
            raise ValueError(f"Audio pipeline '{pipeline_id}' has unsupported voice")
        return AudioPipelineDefaults(text=text.strip(), voice=voice)

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
        operation: AudioPipelineOperation,
        config: dict[str, Any],
    ) -> list[AudioPipelineVariant]:
        variants_config = config.get("variants")
        if not isinstance(variants_config, list) or not variants_config:
            raise ValueError(
                f"Audio pipeline '{pipeline_id}' must define at least one variant"
            )
        variants: list[AudioPipelineVariant] = []
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
                AudioPipelineVariant(
                    id=variant_id,
                    name=name.strip(),
                    device=device,
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

    def list_pipelines(self) -> list[AudioPipeline]:
        return list(self._pipelines.values())

    def get_pipeline(self, pipeline_id: str) -> AudioPipeline | None:
        return self._pipelines.get(pipeline_id)

    def get_variant(
        self, pipeline_id: str, variant_id: str
    ) -> AudioPipelineVariant | None:
        pipeline = self.get_pipeline(pipeline_id)
        if pipeline is None:
            return None
        return next(
            (variant for variant in pipeline.variants if variant.id == variant_id),
            None,
        )


_default_manager: AudioPipelineManager | None = None


def get_audio_pipeline_manager() -> AudioPipelineManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = AudioPipelineManager()
    return _default_manager
