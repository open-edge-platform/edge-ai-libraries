"""Dynamic registration helpers used by MCP tools and resources."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import CallToolResult, TextContent

from .client import ProxyApiClient, ProxyServiceError
from .config import Settings
from .filters import ProxyFilterConfig, operation_is_enabled, resource_is_enabled
from .formatting import build_tool_result, render_resource_payload
from .lifecycle import AppContext
from .models import ApiCatalog, FileUpload, OperationSpec, ParameterSpec


@dataclass(slots=True)
class RegistryContext:
    """Reusable helpers for MCP tool and resource registration."""

    settings: Settings
    catalog: ApiCatalog
    filter_config: ProxyFilterConfig
    shared_client: ProxyApiClient

    def enabled_operations(self) -> tuple[OperationSpec, ...]:
        """Return operations allowed by the JSON filter."""

        return tuple(
            operation
            for operation in self.catalog.operations
            if operation_is_enabled(self.filter_config, operation)
        )

    def tool_name(self, operation: OperationSpec) -> str:
        """Return the generated MCP tool name for an operation."""

        return f"{self.filter_config.tool_prefix}_{operation.slug}"

    def resource_name(self, operation: OperationSpec) -> str:
        """Return the generated MCP resource name for an operation."""

        return f"{self.tool_name(operation)}_resource"

    def resource_uri(self, operation: OperationSpec) -> str:
        """Return the generated resource URI template for an operation."""

        return operation.resource_uri_template(self.filter_config.resource_scheme)

    def tool_annotations(self, operation: OperationSpec) -> dict[str, bool]:
        """Create consistent annotation hints for generated tools."""

        return {
            "readOnlyHint": operation.read_only,
            "destructiveHint": operation.method in {"DELETE", "PATCH"},
            "idempotentHint": operation.method in {"GET", "HEAD", "OPTIONS", "PUT"},
            "openWorldHint": True,
        }

    def client(self, ctx: Context[ServerSession, AppContext]):
        """Return the shared proxy API client from the typed MCP context."""

        return ctx.request_context.lifespan_context.client

    @staticmethod
    def error_result(message: str) -> CallToolResult:
        """Return a structured MCP tool error."""

        payload = {"ok": False, "detail": message}
        return CallToolResult(
            content=[TextContent(type="text", text=message)],
            structuredContent=payload,
            isError=True,
        )

    async def execute_tool(
        self,
        ctx: Context[ServerSession, AppContext],
        *,
        operation: OperationSpec,
        invocation_arguments: dict[str, Any],
        response_format: str,
        json_body: dict[str, Any] | list[Any] | None = None,
        form_data: dict[str, str] | None = None,
        files: dict[str, FileUpload] | None = None,
        text_body: str | None = None,
        binary_body_base64: str | None = None,
        include_binary_content: bool = False,
    ) -> CallToolResult:
        """Execute a proxied request and convert it into an MCP tool result."""

        path_params, query_params, headers = _split_operation_arguments(
            operation=operation,
            invocation_arguments=invocation_arguments,
        )

        try:
            response = await self.client(ctx).request(
                operation=self.tool_name(operation),
                operation_id=operation.operation_id,
                method=operation.method,
                path_template=operation.path,
                path_params=path_params,
                query_params=query_params,
                headers=headers,
                json_body=json_body,
                form_data=form_data,
                files=files,
                text_body=text_body,
                binary_body_base64=binary_body_base64,
                include_binary_content=include_binary_content,
            )
        except ProxyServiceError as exc:
            await ctx.error(exc.detail)
            return self.error_result(exc.detail)

        return build_tool_result(response, response_format=response_format)

    async def execute_resource(
        self,
        *,
        operation: OperationSpec,
        invocation_arguments: dict[str, Any],
    ) -> str:
        """Load a read-only backend payload and render it for an MCP resource."""

        path_params, query_params, headers = _split_operation_arguments(
            operation=operation,
            invocation_arguments=invocation_arguments,
        )

        try:
            response = await self.shared_client.request(
                operation=self.resource_name(operation),
                operation_id=operation.operation_id,
                method=operation.method,
                path_template=operation.path,
                path_params=path_params,
                query_params=query_params,
                headers=headers,
            )
        except ProxyServiceError as exc:
            raise RuntimeError(exc.detail) from exc

        if not response.ok:
            raise RuntimeError(
                f"Target API returned HTTP {response.status_code} while loading {self.resource_name(operation)}."
            )

        return render_resource_payload(response)

    def catalog_resource_payload(self, operations: tuple[OperationSpec, ...]) -> str:
        """Render the currently enabled operation catalog as JSON."""

        payload = {
            "title": self.catalog.title,
            "version": self.catalog.version,
            "base_url": self.catalog.base_url,
            "source": self.catalog.source,
            "spec_kind": self.catalog.spec_kind,
            "server_name": self.filter_config.server_name,
            "tool_prefix": self.filter_config.tool_prefix,
            "resource_scheme": self.filter_config.resource_scheme,
            "operations": [
                {
                    "tool_name": self.tool_name(operation),
                    "resource_uri": (
                        self.resource_uri(operation)
                        if resource_is_enabled(self.filter_config, operation)
                        else None
                    ),
                    "method": operation.method,
                    "path": operation.path,
                    "operation_id": operation.operation_id,
                    "summary": operation.summary,
                    "tags": list(operation.tags),
                    "request_body_content_types": list(
                        operation.request_body.content_types if operation.request_body else ()
                    ),
                    "response_content_types": list(operation.response_content_types),
                }
                for operation in operations
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    def filter_resource_payload(self) -> str:
        """Render the loaded filter config as JSON."""

        return json.dumps(self.filter_config.model_dump(mode="json"), indent=2, sort_keys=True)

    def guidance_resource_payload(self) -> str:
        """Render optional operator guidance for this MCP surface."""

        return self.filter_config.guidance_markdown or ""


def build_server_instructions(
    registry: RegistryContext,
    operations: tuple[OperationSpec, ...],
) -> str:
    """Build high-level MCP server instructions for clients."""

    resource_count = sum(
        1 for operation in operations if resource_is_enabled(registry.filter_config, operation)
    )
    lines = [
        f"This MCP server proxies the filtered subset of the {registry.catalog.title} REST API.",
        (
            f"It loaded an {registry.catalog.spec_kind} document from {registry.catalog.source} "
            f"and exposes {len(operations)} tool(s) plus {resource_count} read-only resource(s)."
        ),
        "Only operations matching the JSON filter config are available.",
        (
            f"Use the {registry.filter_config.resource_scheme}://__meta/catalog resource to inspect "
            "the currently exposed operations."
        ),
        (
            "Use generated tools for full request control and generated resources for read-only "
            "GET endpoints with URI-templated path and required query arguments."
        ),
    ]
    if registry.filter_config.guidance_markdown:
        lines.append(
            f"Additional usage guidance is available at "
            f"{registry.filter_config.resource_scheme}://__meta/guidance."
        )
    return " ".join(lines)


def register_resources(
    mcp: FastMCP,
    registry: RegistryContext,
    operations: tuple[OperationSpec, ...],
) -> None:
    """Register static metadata resources and generated read-only endpoint resources."""

    scheme = registry.filter_config.resource_scheme
    _register_static_resource(
        mcp,
        uri=f"{scheme}://__meta/catalog",
        name=f"{registry.filter_config.tool_prefix}_catalog_resource",
        title="Enabled proxy operation catalog",
        description="List the filtered API operations currently exposed by this MCP server.",
        mime_type="application/json",
        payload_factory=lambda: registry.catalog_resource_payload(operations),
    )
    _register_static_resource(
        mcp,
        uri=f"{scheme}://__meta/filter",
        name=f"{registry.filter_config.tool_prefix}_filter_resource",
        title="Loaded proxy filter configuration",
        description="Inspect the JSON filter configuration used to enable and disable proxy endpoints.",
        mime_type="application/json",
        payload_factory=registry.filter_resource_payload,
    )

    if registry.filter_config.guidance_markdown:
        _register_static_resource(
            mcp,
            uri=f"{scheme}://__meta/guidance",
            name=f"{registry.filter_config.tool_prefix}_guidance_resource",
            title="Operator guidance for this MCP surface",
            description="Read special usage guidance and intentional exclusions for this MCP server.",
            mime_type="text/markdown",
            payload_factory=registry.guidance_resource_payload,
        )

    for operation in operations:
        if not resource_is_enabled(registry.filter_config, operation):
            continue

        handler = _build_resource_handler(registry, operation)
        mcp.resource(
            registry.resource_uri(operation),
            name=registry.resource_name(operation),
            title=f"{operation.method} {operation.path}",
            description=_build_resource_description(operation),
            mime_type="application/json",
        )(handler)


def register_tools(
    mcp: FastMCP,
    registry: RegistryContext,
    operations: tuple[OperationSpec, ...],
) -> None:
    """Register generated MCP tools for the filtered operations."""

    for operation in operations:
        handler = _build_tool_handler(registry, operation)
        mcp.add_tool(
            handler,
            name=registry.tool_name(operation),
            description=_build_tool_description(operation),
            annotations=registry.tool_annotations(operation),
            structured_output=True,
        )


def _register_static_resource(
    mcp: FastMCP,
    *,
    uri: str,
    name: str,
    title: str,
    description: str,
    mime_type: str,
    payload_factory,
) -> None:
    """Register a fixed metadata resource that returns a precomputed payload."""

    @mcp.resource(
        uri,
        name=name,
        title=title,
        description=description,
        mime_type=mime_type,
    )
    def resource() -> str:
        return payload_factory()


def _build_tool_handler(registry: RegistryContext, operation: OperationSpec):
    """Create a generated tool handler for a specific operation."""

    async def runner(**kwargs: Any) -> CallToolResult:
        ctx = kwargs.pop("ctx")
        response_format = kwargs.pop("response_format", "markdown")
        include_binary_content = kwargs.pop("include_binary_content", False)
        json_body = kwargs.pop("json_body", None)
        form_data = kwargs.pop("form_data", None)
        files = kwargs.pop("files", None)
        text_body = kwargs.pop("text_body", None)
        binary_body_base64 = kwargs.pop("binary_body_base64", None)
        return await registry.execute_tool(
            ctx,
            operation=operation,
            invocation_arguments=kwargs,
            response_format=response_format,
            json_body=json_body,
            form_data=form_data,
            files=files,
            text_body=text_body,
            binary_body_base64=binary_body_base64,
            include_binary_content=include_binary_content,
        )

    return _make_generated_function(
        function_name=registry.tool_name(operation),
        description=_build_tool_description(operation),
        runner=runner,
        operation=operation,
        include_context=True,
        include_tool_extras=True,
        return_type_expression="CallToolResult",
    )


def _build_resource_handler(registry: RegistryContext, operation: OperationSpec):
    """Create a generated resource handler for a specific operation."""

    async def runner(**kwargs: Any) -> str:
        return await registry.execute_resource(
            operation=operation,
            invocation_arguments=kwargs,
        )

    return _make_generated_function(
        function_name=registry.resource_name(operation),
        description=_build_resource_description(operation),
        runner=runner,
        operation=operation,
        include_context=False,
        include_tool_extras=False,
        return_type_expression="str",
    )


def _make_generated_function(
    *,
    function_name: str,
    description: str,
    runner,
    operation: OperationSpec,
    include_context: bool,
    include_tool_extras: bool,
    return_type_expression: str,
):
    """Create a real Python function with an explicit signature for FastMCP introspection."""

    declarations, forwarded_names = _generated_function_parts(
        operation=operation,
        include_context=include_context,
        include_tool_extras=include_tool_extras,
    )
    signature = _generated_function_signature(
        function_name=function_name,
        declarations=declarations,
        return_type_expression=return_type_expression,
    )
    body = _generated_function_body(forwarded_names)

    namespace = {
        "__runner": runner,
        "AppContext": AppContext,
        "CallToolResult": CallToolResult,
        "Context": Context,
        "FileUpload": FileUpload,
        "ServerSession": ServerSession,
    }
    exec("\n".join([signature, body]), namespace)
    generated = namespace[function_name]
    generated.__doc__ = description
    return generated


def _parameter_declaration(parameter: ParameterSpec) -> str:
    """Return a Python source fragment for an operation parameter."""

    type_expression = _type_expression(parameter.schema_type)
    if parameter.required:
        return f"{parameter.field_name}: {type_expression}"
    return f"{parameter.field_name}: {type_expression} | None = None"


def _type_expression(schema_type: str | None) -> str:
    """Map normalized schema types to Python type expressions."""

    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    return "str"


def _generated_function_parts(
    *,
    operation: OperationSpec,
    include_context: bool,
    include_tool_extras: bool,
) -> tuple[list[str], list[str]]:
    """Return source declarations and forwarded names for a generated handler."""

    declarations: list[str] = []
    forwarded_names: list[str] = []

    if include_context:
        declarations.append("ctx: Context[ServerSession, AppContext]")
        forwarded_names.append("ctx")

    source_parameters = operation.parameters if include_tool_extras else operation.resource_parameters
    for parameter in source_parameters:
        declarations.append(_parameter_declaration(parameter))
        forwarded_names.append(parameter.field_name)

    if include_tool_extras:
        declarations.extend(_tool_extra_declarations(operation))
        forwarded_names.extend(_tool_extra_forwarded_names(operation))

    return declarations, forwarded_names


def _tool_extra_declarations(operation: OperationSpec) -> list[str]:
    """Return generated tool-only parameter declarations."""

    declarations: list[str] = []
    if operation.request_body is not None:
        if operation.supports_json_body:
            declarations.append("json_body: object | None = None")
        if operation.supports_form_body or operation.supports_multipart_body:
            declarations.append("form_data: dict[str, str] | None = None")
        if operation.supports_multipart_body:
            declarations.append("files: dict[str, FileUpload] | None = None")
        if operation.supports_text_body:
            declarations.append("text_body: str | None = None")
        if operation.supports_binary_body:
            declarations.append("binary_body_base64: str | None = None")

    declarations.extend(
        [
            "include_binary_content: bool = False",
            "response_format: str = 'markdown'",
        ]
    )
    return declarations


def _tool_extra_forwarded_names(operation: OperationSpec) -> list[str]:
    """Return generated tool-only argument names forwarded to the runner."""

    names: list[str] = []
    if operation.request_body is not None:
        if operation.supports_json_body:
            names.append("json_body")
        if operation.supports_form_body or operation.supports_multipart_body:
            names.append("form_data")
        if operation.supports_multipart_body:
            names.append("files")
        if operation.supports_text_body:
            names.append("text_body")
        if operation.supports_binary_body:
            names.append("binary_body_base64")

    names.extend(["include_binary_content", "response_format"])
    return names


def _generated_function_signature(
    *,
    function_name: str,
    declarations: list[str],
    return_type_expression: str,
) -> str:
    """Build the generated async function signature source."""

    argument_list = ", ".join(declarations)
    if not argument_list:
        return f"async def {function_name}() -> {return_type_expression}:"
    return f"async def {function_name}({argument_list}) -> {return_type_expression}:"


def _generated_function_body(forwarded_names: list[str]) -> str:
    """Build the generated function body source."""

    if not forwarded_names:
        return "    return await __runner()"
    forwarded_kwargs = ", ".join(f"{name}={name}" for name in forwarded_names)
    return f"    return await __runner({forwarded_kwargs})"


def _split_operation_arguments(
    *,
    operation: OperationSpec,
    invocation_arguments: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str] | None]:
    """Split generated tool/resource args into path, query, and header maps."""

    path_params: dict[str, Any] = {}
    query_params: dict[str, Any] = {}
    header_params: dict[str, str] = {}
    cookies: list[tuple[str, str]] = []

    for parameter in operation.parameters:
        if parameter.field_name not in invocation_arguments:
            continue
        value = invocation_arguments[parameter.field_name]
        if value is None:
            continue

        if parameter.location == "path":
            path_params[parameter.name] = value
        elif parameter.location == "query":
            query_params[parameter.name] = value
        elif parameter.location == "header":
            header_params[parameter.name] = str(value)
        elif parameter.location == "cookie":
            cookies.append((parameter.name, str(value)))

    if cookies:
        cookie_header = "; ".join(f"{name}={value}" for name, value in cookies)
        existing_cookie = header_params.get("Cookie")
        header_params["Cookie"] = (
            f"{existing_cookie}; {cookie_header}" if existing_cookie else cookie_header
        )

    return path_params, query_params, header_params or None


def _build_tool_description(operation: OperationSpec) -> str:
    """Create a readable description for a generated tool."""

    lines = [f"Proxy {operation.method} {operation.path} from the loaded API spec."]
    if operation.summary:
        lines.append(f"Summary: {operation.summary}")
    if operation.description:
        lines.append(f"Description: {operation.description}")
    if operation.tags:
        lines.append(f"Tags: {', '.join(operation.tags)}")
    if operation.parameters:
        lines.append(
            "Parameters: "
            + ", ".join(
                f"{parameter.location}:{parameter.name}{' (required)' if parameter.required else ''}"
                for parameter in operation.parameters
            )
        )
    if operation.request_body is not None:
        lines.append(
            "Request body content types: "
            + ", ".join(operation.request_body.content_types or ("unspecified",))
        )
    if operation.response_content_types:
        lines.append(
            "Response content types: " + ", ".join(operation.response_content_types)
        )
    return "\n".join(lines)


def _build_resource_description(operation: OperationSpec) -> str:
    """Create a readable description for a generated resource."""

    lines = [f"Read-only resource proxy for {operation.method} {operation.path}."]
    if operation.summary:
        lines.append(f"Summary: {operation.summary}")
    if operation.query_parameters and any(
        not parameter.required for parameter in operation.query_parameters
    ):
        lines.append(
            "Only required query parameters are modeled in the resource URI template; "
            "use the corresponding tool for optional query parameters."
        )
    return "\n".join(lines)
