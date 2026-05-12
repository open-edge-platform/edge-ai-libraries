import yaml
from types import SimpleNamespace
import os
import logging
import json

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PREFIX = "AUDIO_ANALYZER__"
CONFIG_PATH_ENV = "AUDIO_ANALYZER_CONFIG_PATH"
CONFIG_OVERRIDE_PATHS_ENV = "AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS"
ENV_FILE_ENV = "AUDIO_ANALYZER_ENV_FILE"


def _load_dotenv_file(path):
    if not os.path.isfile(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key or key in os.environ:
                continue

            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]

            os.environ[key] = value


def _load_default_dotenv_files():
    candidates = [
        os.environ.get(ENV_FILE_ENV),
        os.path.join(BASE_DIR, ".env"),
        os.path.join(os.path.dirname(BASE_DIR), ".env"),
    ]

    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        resolved = os.path.abspath(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        _load_dotenv_file(resolved)


def _parse_env_value(raw_value, existing_value):
    if isinstance(existing_value, bool):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

    if isinstance(existing_value, int) and not isinstance(existing_value, bool):
        return int(raw_value)

    if isinstance(existing_value, float):
        return float(raw_value)

    if isinstance(existing_value, list):
        stripped = raw_value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError("Expected a JSON array for list-valued config override")
            return parsed
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    if existing_value is None:
        stripped = raw_value.strip()
        if stripped.lower() in {"none", "null"}:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return raw_value

    return raw_value


def _set_nested_value(data, path, value):
    current = data
    for segment in path[:-1]:
        next_value = current.get(segment)
        if not isinstance(next_value, dict):
            next_value = {}
            current[segment] = next_value
        current = next_value
    current[path[-1]] = value


def _apply_env_overrides(data):
    for env_key, raw_value in os.environ.items():
        if not env_key.startswith(ENV_PREFIX):
            continue

        path = [segment.lower() for segment in env_key[len(ENV_PREFIX):].split("__") if segment]
        if not path:
            continue

        existing_value = data
        for segment in path:
            if isinstance(existing_value, dict) and segment in existing_value:
                existing_value = existing_value[segment]
            else:
                existing_value = None
                break

        parsed_value = _parse_env_value(raw_value, existing_value)
        _set_nested_value(data, path, parsed_value)

    return data


def _resolve_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


def _deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override

    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml_file(path):
    with open(path, "r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def _apply_yaml_overrides(data):
    raw_paths = os.environ.get(CONFIG_OVERRIDE_PATHS_ENV, "").strip()
    if not raw_paths:
        return data

    override_paths = [item.strip() for item in raw_paths.split(",") if item.strip()]
    for override_path in override_paths:
        resolved_path = _resolve_path(override_path)
        if not os.path.isfile(resolved_path):
            logger.warning("Config override file not found: %s", resolved_path)
            continue
        data = _deep_merge(data, _load_yaml_file(resolved_path))

    return data

def _dict_to_namespace(d):
    if isinstance(d, dict):
        return SimpleNamespace(**{k: _dict_to_namespace(v) for k, v in d.items()})
    return d

def load_config(path="config.yaml"):
    _load_default_dotenv_files()

    path = os.environ.get(CONFIG_PATH_ENV, path)
    path = _resolve_path(path)
    data = _load_yaml_file(path)
    data = _apply_yaml_overrides(data)
    data = _apply_env_overrides(data)
    return _dict_to_namespace(data)

# Load once and expose
config = load_config()

logger.debug("\n📦 CONFIGURATION START\n" + "-" * 40)
logger.debug(yaml.dump(vars(config), sort_keys=False))
logger.debug("\n" + "-" * 40 + "\n📦 CONFIGURATION END\n")
