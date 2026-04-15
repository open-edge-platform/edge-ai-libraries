"""Shared models for the spec-driven MCP REST proxy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Normalized OpenAPI parameter metadata."""

    name: str
    field_name: str
    location: str
    required: bool
    description: str | None
    schema_type: str | None


@dataclass(frozen=True, slots=True)
class RequestBodySpec:
    """Normalized request body metadata."""

    required: bool
    description: str | None
    content_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """A normalized API operation used for tool and resource generation."""

    method: str
    path: str
    slug: str
    operation_id: str | None
    summary: str | None
    description: str | None
    tags: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    request_body: RequestBodySpec | None
    response_content_types: tuple[str, ...]

    @property
    def path_parameters(self) -> tuple[ParameterSpec, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.location == "path")

    @property
    def query_parameters(self) -> tuple[ParameterSpec, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.location == "query")

    @property
    def read_only(self) -> bool:
        return self.method in {"GET", "HEAD", "OPTIONS"}

    @property
    def supports_json_body(self) -> bool:
        return self.request_body is not None and any(
            content_type.endswith("/json") or "+json" in content_type
            for content_type in self.request_body.content_types
        )

    @property
    def supports_form_body(self) -> bool:
        if self.request_body is None:
            return False
        return any(
            content_type == "application/x-www-form-urlencoded"
            for content_type in self.request_body.content_types
        )

    @property
    def supports_multipart_body(self) -> bool:
        if self.request_body is None:
            return False
        return any(
            content_type == "multipart/form-data" for content_type in self.request_body.content_types
        )

    @property
    def supports_text_body(self) -> bool:
        if self.request_body is None:
            return False
        return any(content_type.startswith("text/") for content_type in self.request_body.content_types)

    @property
    def supports_binary_body(self) -> bool:
        if self.request_body is None:
            return False
        return not (
            self.supports_json_body
            or self.supports_form_body
            or self.supports_multipart_body
            or self.supports_text_body
        )

    @property
    def resource_parameters(self) -> tuple[ParameterSpec, ...]:
        required_query_parameters = tuple(
            parameter for parameter in self.query_parameters if parameter.required
        )
        return self.path_parameters + required_query_parameters

    def resource_uri_template(self, scheme: str) -> str:
        """Build a resource URI template for this operation."""

        resource_path = self.path or "/"
        for parameter in self.path_parameters:
            resource_path = resource_path.replace(
                f"{{{parameter.name}}}",
                f"{{{parameter.field_name}}}",
            )

        normalized_path = resource_path.lstrip("/") or "root"
        uri = f"{scheme}://{normalized_path}"
        required_query_parameters = [
            parameter for parameter in self.query_parameters if parameter.required
        ]
        if required_query_parameters:
            query_string = "&".join(
                f"{parameter.field_name}={{{parameter.field_name}}}"
                for parameter in required_query_parameters
            )
            uri = f"{uri}?{query_string}"
        return uri


@dataclass(frozen=True, slots=True)
class ApiCatalog:
    """The normalized API catalog loaded from an OpenAPI/Swagger spec."""

    title: str
    version: str
    base_url: str
    source: str
    spec_kind: str
    operations: tuple[OperationSpec, ...]


class FileUpload(BaseModel):
    """A single multipart file upload passed to a generated tool."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, description="Original filename sent to the REST API.")
    content_base64: str = Field(
        min_length=1,
        description="Base64-encoded file content for this multipart field.",
    )
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME type sent with the multipart file part.",
    )


class ProxyOperationResult(BaseModel):
    """Structured content returned for every generated MCP tool call."""

    model_config = ConfigDict(extra="forbid")

    operation: str = Field(description="Generated MCP tool name for the proxied operation.")
    operation_id: str | None = Field(
        default=None,
        description="Original OpenAPI operationId when available.",
    )
    endpoint: str = Field(description="Resolved target API path that was called.")
    url: str = Field(description="Resolved absolute URL that was called.")
    method: str = Field(description="HTTP method used for the target API request.")
    status_code: int = Field(description="HTTP status returned by the target API.")
    ok: bool = Field(description="True when the target API returned a 2xx status code.")
    content_type: str | None = Field(
        default=None,
        description="Response content type returned by the target API.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Response headers returned by the target API.",
    )
    content_size_bytes: int = Field(description="Response body size in bytes.")
    data: Any = Field(
        default=None,
        description="Parsed JSON payload when the target API responded with JSON.",
    )
    text: str | None = Field(
        default=None,
        description="Decoded text payload for text-like target API responses.",
    )
    content_base64: str | None = Field(
        default=None,
        description="Base64-encoded binary response content when requested.",
    )
    note: str | None = Field(
        default=None,
        description="Additional context such as omitted binary payload warnings.",
    )
