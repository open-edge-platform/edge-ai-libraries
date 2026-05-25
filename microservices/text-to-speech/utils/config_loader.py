import logging
import os
from types import SimpleNamespace

import yaml


logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PREFIX = "TEXT_TO_SPEECH__"
REQUIRED_CONFIG_PATHS = (
    ("models", "tts", "name"),
    ("models", "tts", "runtime"),
    ("models", "tts", "device"),
    ("models", "tts", "dtype"),
    ("models", "tts", "model_variant"),
    ("models", "tts", "default_speaker"),
    ("models", "tts", "default_language"),
    ("models", "tts", "models_base_path"),
    ("models", "tts", "use_local_cache"),
    ("audio", "output_format"),
    ("audio", "sample_width"),
    ("pipeline", "persist_outputs"),
)


def _load_yaml_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _merge_dicts(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_env_value(raw_value: str):
    lowered = raw_value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None

    try:
        return yaml.safe_load(raw_value)
    except yaml.YAMLError:
        return raw_value


def _apply_env_overrides(config_data: dict) -> dict:
    updated = dict(config_data)

    for env_name, env_value in os.environ.items():
        if not env_name.startswith(ENV_PREFIX):
            continue

        path = env_name[len(ENV_PREFIX):].split("__")
        cursor = updated
        for segment in path[:-1]:
            key = segment.lower()
            if key not in cursor or not isinstance(cursor[key], dict):
                cursor[key] = {}
            cursor = cursor[key]

        cursor[path[-1].lower()] = _coerce_env_value(env_value)

    return updated


def _dict_to_namespace(data):
    if isinstance(data, dict):
        return SimpleNamespace(**{key: _dict_to_namespace(value) for key, value in data.items()})
    return data


def _get_nested_value(data: dict, path: tuple[str, ...]):
    cursor = data
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            raise ValueError(f"Missing required configuration value: {'.'.join(path)}")
        cursor = cursor[key]
    return cursor


def _validate_config_data(data: dict) -> dict:
    for path in REQUIRED_CONFIG_PATHS:
        value = _get_nested_value(data, path)
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"Configuration value cannot be empty: {'.'.join(path)}")

    output_format = str(_get_nested_value(data, ("audio", "output_format"))).strip().lower()
    if output_format not in {"wav"}:
        raise ValueError("audio.output_format must be 'wav'")

    sample_width = _get_nested_value(data, ("audio", "sample_width"))
    if int(sample_width) != 16:
        raise ValueError("audio.sample_width must be 16")

    runtime = str(_get_nested_value(data, ("models", "tts", "runtime"))).strip().lower()
    if runtime not in {"openvino", "pytorch"}:
        raise ValueError("models.tts.runtime must be 'openvino' or 'pytorch'")

    return data


def load_config(path: str | None = None):
    config_path = path or os.getenv("TEXT_TO_SPEECH_CONFIG_PATH", "config.yaml")
    if not os.path.isabs(config_path):
        config_path = os.path.join(BASE_DIR, config_path)

    data = _load_yaml_file(config_path)

    override_paths = os.getenv("TEXT_TO_SPEECH_CONFIG_OVERRIDE_PATHS", "")
    for override_path in [entry.strip() for entry in override_paths.split(",") if entry.strip()]:
        if not os.path.isabs(override_path):
            override_path = os.path.join(BASE_DIR, override_path)
        data = _merge_dicts(data, _load_yaml_file(override_path))

    data = _validate_config_data(_apply_env_overrides(data))
    return _dict_to_namespace(data)


config = load_config()

logger.debug("\nCONFIGURATION START\n" + "-" * 40)
logger.debug(yaml.dump(vars(config), sort_keys=False))
logger.debug("\n" + "-" * 40 + "\nCONFIGURATION END\n")
