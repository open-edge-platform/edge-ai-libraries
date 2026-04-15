"""OpenAPI and Swagger loading plus normalization into MCP-friendly operations."""

from __future__ import annotations

from collections import OrderedDict
import json
import re
from typing import Any
from urllib.parse import urljoin

import httpx
import yaml

from .config import Settings
from .models import ApiCatalog, OperationSpec, ParameterSpec, RequestBodySpec


HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
RESERVED_FIELD_NAMES = {
    "ctx",
    "response_format",
    "include_binary_content",
    "json_body",
    "form_data",
    "files",
    "text_body",
    "binary_body_base64",
}


def load_api_catalog(settings: Settings) -> ApiCatalog:
    """Load the configured OpenAPI or Swagger document into a normalized catalog."""

    document, source = _load_document(settings)
    spec_kind = _detect_spec_kind(document)
    base_url = _resolve_base_url(document, settings, source_url=settings.spec_url)
    operations = tuple(_build_operations(document, spec_kind))

    if not operations:
        raise ValueError("The loaded API specification does not contain any supported operations.")

    info = document.get("info") if isinstance(document.get("info"), dict) else {}
    return ApiCatalog(
        title=str(info.get("title", "API Proxy")).strip() or "API Proxy",
        version=str(info.get("version", "unknown")).strip() or "unknown",
        base_url=base_url,
        source=source,
        spec_kind=spec_kind,
        operations=operations,
    )


def _load_document(settings: Settings) -> tuple[dict[str, Any], str]:
    """Load the OpenAPI/Swagger document from the configured URL."""

    with httpx.Client(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
        response = client.get(settings.spec_url)
        response.raise_for_status()
    return _parse_document_text(response.text), settings.spec_url


def _parse_document_text(raw_text: str) -> dict[str, Any]:
    """Parse a JSON or YAML OpenAPI/Swagger document."""

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = yaml.safe_load(raw_text)

    if not isinstance(parsed, dict):
        raise ValueError("The loaded API specification must be a JSON or YAML object.")

    return parsed


def _detect_spec_kind(document: dict[str, Any]) -> str:
    """Return 'openapi' or 'swagger2' depending on the document shape."""

    openapi_version = str(document.get("openapi", "")).strip()
    swagger_version = str(document.get("swagger", "")).strip()

    if openapi_version:
        return "openapi"
    if swagger_version.startswith("2."):
        return "swagger2"

    raise ValueError("Only OpenAPI 3.x and Swagger 2.0 documents are supported.")


def _resolve_base_url(
    document: dict[str, Any],
    settings: Settings,
    *,
    source_url: str | None,
) -> str:
    """Resolve the target API base URL from settings or the loaded spec."""

    if settings.target_base_url:
        return settings.target_base_url

    spec_kind = _detect_spec_kind(document)
    if spec_kind == "openapi":
        resolved = _resolve_openapi_base_url(document, source_url=source_url)
    else:
        resolved = _resolve_swagger2_base_url(document)

    if resolved is not None:
        return resolved

    raise ValueError(
        "TARGET_BASE_URL must be set when the spec does not declare a usable server URL."
    )


def _resolve_openapi_base_url(document: dict[str, Any], *, source_url: str | None) -> str | None:
    """Return the first usable OpenAPI 3 server URL, if any."""

    servers = document.get("servers") if isinstance(document.get("servers"), list) else []
    for server in servers:
        if not isinstance(server, dict):
            continue
        candidate = str(server.get("url", "")).strip()
        if not candidate:
            continue
        resolved = urljoin(source_url, candidate) if source_url else candidate
        return resolved.rstrip("/")
    return None


def _resolve_swagger2_base_url(document: dict[str, Any]) -> str | None:
    """Return the Swagger 2 base URL, if the document declares one."""

    host = str(document.get("host", "")).strip()
    if not host:
        return None

    schemes = document.get("schemes") if isinstance(document.get("schemes"), list) else []
    scheme = str(schemes[0]).strip() if schemes else "https"
    base_path = str(document.get("basePath", "")).strip()
    return f"{scheme}://{host}{base_path}".rstrip("/")


def _build_operations(document: dict[str, Any], spec_kind: str) -> list[OperationSpec]:
    """Build normalized operation specs from the raw document."""

    raw_paths = document.get("paths")
    if not isinstance(raw_paths, dict):
        raise ValueError("The loaded API specification does not contain a valid 'paths' object.")

    operations: list[OperationSpec] = []
    for path, method, operation, path_parameters in _iter_operation_entries(raw_paths):
        operations.append(
            _build_operation_spec(
                document=document,
                path=path,
                method=method,
                operation=operation,
                path_parameters=path_parameters,
                spec_kind=spec_kind,
            )
        )

    operations.sort(key=lambda operation: (operation.path, operation.method))
    return operations


def _iter_operation_entries(
    raw_paths: dict[str, Any],
) -> list[tuple[str, str, dict[str, Any], list[Any]]]:
    """Yield normalized path/method/operation entries from the raw spec."""

    entries: list[tuple[str, str, dict[str, Any], list[Any]]] = []
    for path, path_item in raw_paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue

        path_parameters = (
            path_item.get("parameters") if isinstance(path_item.get("parameters"), list) else []
        )
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            entries.append((path, method.upper(), operation, path_parameters))
    return entries


def _build_operation_spec(
    *,
    document: dict[str, Any],
    path: str,
    method: str,
    operation: dict[str, Any],
    path_parameters: list[Any],
    spec_kind: str,
) -> OperationSpec:
    """Build one normalized operation from a raw path item entry."""

    operation_parameters = (
        operation.get("parameters") if isinstance(operation.get("parameters"), list) else []
    )
    merged_parameters = _merge_parameters(document, path_parameters, operation_parameters)
    return OperationSpec(
        method=method,
        path=path,
        slug=_operation_slug(method=method, path=path, operation_id=operation.get("operationId")),
        operation_id=_optional_text(operation.get("operationId")),
        summary=_optional_text(operation.get("summary")),
        description=_optional_text(operation.get("description")),
        tags=tuple(str(tag) for tag in operation.get("tags", []) if isinstance(tag, str)),
        parameters=_parse_parameter_specs(document, path, merged_parameters),
        request_body=_parse_request_body(document, operation, merged_parameters, spec_kind),
        response_content_types=_parse_response_content_types(document, operation, spec_kind),
    )


def _merge_parameters(
    document: dict[str, Any],
    path_parameters: list[Any],
    operation_parameters: list[Any],
) -> list[dict[str, Any]]:
    """Merge path-level and operation-level parameters with operation overrides."""

    merged: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
    for candidate in path_parameters + operation_parameters:
        resolved = _resolve_ref(document, candidate)
        if not isinstance(resolved, dict):
            continue
        name = str(resolved.get("name", "")).strip()
        location = str(resolved.get("in", "")).strip()
        if not name or not location:
            continue
        merged[(name, location)] = resolved
    return list(merged.values())


def _parse_parameter_specs(
    document: dict[str, Any],
    path: str,
    merged_parameters: list[dict[str, Any]],
) -> tuple[ParameterSpec, ...]:
    """Convert raw OpenAPI parameters into normalized parameter specs."""

    parameter_specs: list[ParameterSpec] = []
    used_names: set[str] = set(RESERVED_FIELD_NAMES)
    for parameter in merged_parameters:
        resolved = _resolve_ref(document, parameter)
        if not isinstance(resolved, dict):
            continue

        location = str(resolved.get("in", "")).strip()
        if location in {"body", "formData"}:
            continue
        if location not in {"path", "query", "header", "cookie"}:
            continue

        name = str(resolved.get("name", "")).strip()
        if not name:
            continue

        field_name = _unique_field_name(name, location, used_names)
        used_names.add(field_name)
        schema = resolved.get("schema") if isinstance(resolved.get("schema"), dict) else {}
        schema_type = _optional_text(schema.get("type")) or _optional_text(resolved.get("type"))
        parameter_specs.append(
            ParameterSpec(
                name=name,
                field_name=field_name,
                location=location,
                required=bool(resolved.get("required", location == "path")),
                description=_optional_text(resolved.get("description")),
                schema_type=schema_type,
            )
        )

    declared_path_parameter_names = {parameter.name for parameter in parameter_specs if parameter.location == "path"}
    for raw_name in re.findall(r"{([^{}]+)}", path):
        if raw_name in declared_path_parameter_names:
            continue

        field_name = _unique_field_name(raw_name, "path", used_names)
        used_names.add(field_name)
        parameter_specs.append(
            ParameterSpec(
                name=raw_name,
                field_name=field_name,
                location="path",
                required=True,
                description=f"Inferred path parameter {raw_name!r} from the URI template.",
                schema_type="string",
            )
        )

    return tuple(parameter_specs)


def _parse_request_body(
    document: dict[str, Any],
    operation: dict[str, Any],
    merged_parameters: list[dict[str, Any]],
    spec_kind: str,
) -> RequestBodySpec | None:
    """Normalize request body metadata for the operation."""

    if spec_kind == "openapi":
        raw_request_body = operation.get("requestBody")
        if raw_request_body is None:
            return None
        request_body = _resolve_ref(document, raw_request_body)
        if not isinstance(request_body, dict):
            return None
        raw_content = request_body.get("content")
        content_types = tuple(
            content_type
            for content_type, value in raw_content.items()
            if isinstance(content_type, str) and isinstance(value, dict)
        ) if isinstance(raw_content, dict) else ()
        return RequestBodySpec(
            required=bool(request_body.get("required", False)),
            description=_optional_text(request_body.get("description")),
            content_types=content_types,
        )

    body_parameter = next(
        (
            parameter
            for parameter in merged_parameters
            if str(parameter.get("in", "")).strip() == "body"
        ),
        None,
    )
    form_parameters = [
        parameter
        for parameter in merged_parameters
        if str(parameter.get("in", "")).strip() == "formData"
    ]
    consumes = operation.get("consumes")
    raw_content_types = consumes if isinstance(consumes, list) else document.get("consumes")
    content_types = tuple(
        str(content_type)
        for content_type in raw_content_types
        if isinstance(content_type, str)
    ) if isinstance(raw_content_types, list) else ()

    if body_parameter is not None:
        return RequestBodySpec(
            required=bool(body_parameter.get("required", False)),
            description=_optional_text(body_parameter.get("description")),
            content_types=content_types or ("application/json",),
        )
    if form_parameters:
        return RequestBodySpec(
            required=any(bool(parameter.get("required", False)) for parameter in form_parameters),
            description="Form fields defined in the Swagger 2.0 spec.",
            content_types=content_types or ("multipart/form-data",),
        )
    return None


def _parse_response_content_types(
    document: dict[str, Any],
    operation: dict[str, Any],
    spec_kind: str,
) -> tuple[str, ...]:
    """Collect advertised response content types for the operation."""

    if spec_kind == "openapi":
        content_types = _parse_openapi_response_content_types(document, operation)
    else:
        content_types = _parse_swagger_response_content_types(document, operation)
    return tuple(dict.fromkeys(content_types))


def _parse_openapi_response_content_types(
    document: dict[str, Any],
    operation: dict[str, Any],
) -> list[str]:
    """Collect 2xx/default response content types from an OpenAPI 3 operation."""

    responses = operation.get("responses") if isinstance(operation.get("responses"), dict) else {}
    content_types: list[str] = []
    for status_code, response in responses.items():
        if status_code != "default" and not str(status_code).startswith("2"):
            continue
        resolved = _resolve_ref(document, response)
        if not isinstance(resolved, dict):
            continue
        raw_content = resolved.get("content")
        if not isinstance(raw_content, dict):
            continue
        content_types.extend(
            content_type
            for content_type, value in raw_content.items()
            if isinstance(content_type, str) and isinstance(value, dict)
        )
    return content_types


def _parse_swagger_response_content_types(
    document: dict[str, Any],
    operation: dict[str, Any],
) -> list[str]:
    """Collect declared response content types from a Swagger 2 operation."""

    produces = operation.get("produces")
    raw_content_types = produces if isinstance(produces, list) else document.get("produces")
    if not isinstance(raw_content_types, list):
        return []
    return [str(content_type) for content_type in raw_content_types if isinstance(content_type, str)]


def _resolve_ref(document: dict[str, Any], value: Any) -> Any:
    """Resolve a local JSON pointer reference if present."""

    if not isinstance(value, dict) or "$ref" not in value:
        return value

    ref = value.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError(f"Only local JSON pointer refs are supported, got: {ref!r}")

    current: Any = document
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"Reference could not be resolved: {ref}")
        current = current[part]
    return current


def _operation_slug(method: str, path: str, operation_id: Any) -> str:
    """Create a stable slug for tool naming."""

    if isinstance(operation_id, str) and operation_id.strip():
        return _snake_case(operation_id)

    parts = [_snake_case(method)]
    for segment in path.strip("/").split("/"):
        if not segment:
            continue
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("by")
            parts.append(_snake_case(segment[1:-1]))
        else:
            parts.append(_snake_case(segment))
    return "_".join(part for part in parts if part)


def _unique_field_name(name: str, location: str, used_names: set[str]) -> str:
    """Create a valid, unique Python identifier for a parameter."""

    prefix = ""
    if location == "header":
        prefix = "header_"
    elif location == "cookie":
        prefix = "cookie_"

    base = f"{prefix}{_snake_case(name)}".strip("_") or "value"
    if base[0].isdigit():
        base = f"param_{base}"

    candidate = base
    counter = 2
    while candidate in used_names:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _snake_case(value: Any) -> str:
    """Convert an arbitrary value into a snake_case identifier fragment."""

    text = str(value).strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_").lower()


def _optional_text(value: Any) -> str | None:
    """Return a stripped string value or None."""

    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
