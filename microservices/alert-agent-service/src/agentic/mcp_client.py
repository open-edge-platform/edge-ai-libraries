# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import aiohttp

from src.config import settings

logger = logging.getLogger(__name__)


_JSON_SCHEMA_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}

_servers: Dict[str, "MCPServer"] = {}
_tools: Dict[str, "MCPTool"] = {}


@dataclass
class MCPTool:
    """An MCP tool with its schema."""
    name: str
    server: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    default_arguments: dict = field(default_factory=dict)

    def to_schema(self) -> dict:
        """Convert to OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"[MCP:{self.server}] {self.description}",
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }


@dataclass
class ServerConfig:
    """MCP server configuration."""
    name: str
    transport: str = "http"  # stdio | http | sse
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout: float = 30.0
    description: str = ""
    tool_defaults: Dict[str, dict] = field(default_factory=dict)


class MCPServer:
    """Connection to a single MCP server."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.name = config.name
        self._session: Optional[aiohttp.ClientSession] = None
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._mcp_session_id: Optional[str] = None

    async def connect(self) -> bool:
        """Establish connection. Returns True on success."""
        try:
            if self.config.transport == "stdio":
                return self._connect_stdio()
            else:
                return await self._connect_http()
        except Exception as e:
            logger.error(f"[{self.name}] Connection failed: {e}")
            return False

    def _connect_stdio(self) -> bool:
        if not self.config.command:
            logger.error(f"[{self.name}] stdio requires 'command'")
            return False

        env = {**os.environ, **self.config.env}
        self._process = subprocess.Popen(
            [self.config.command, *self.config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        logger.info(f"[{self.name}] Connected (stdio)")
        return True

    async def _connect_http(self) -> bool:
        if not self.config.url:
            logger.error(f"[{self.name}] HTTP/SSE requires 'url'")
            return False

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )

        try:
            await self._initialize()
            logger.info(f"[{self.name}] Connected ({self.config.transport}) -> {self.config.url}")
            return True
        except Exception as e:
            logger.error(f"[{self.name}] Initialize failed: {e}")
            await self._session.close()
            self._session = None
            return False

    async def _initialize(self):
        """Send MCP initialize handshake and capture session ID."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                # ── Only change from live-video-alert-agent version ──
                "clientInfo": {"name": "alert-agent-service", "version": "1.0.0"},
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        async with self._session.post(self.config.url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}: {await resp.text()}")

            self._mcp_session_id = resp.headers.get("mcp-session-id")
            logger.debug(f"[{self.name}] Session ID: {self._mcp_session_id}")

            content_type = resp.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                async for line in resp.content:
                    line = line.decode().strip()
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "error" in data:
                            raise RuntimeError(data["error"])
                        logger.debug(f"[{self.name}] Initialized: {data.get('result', {}).get('serverInfo', {})}")
                        break
            else:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(data["error"])
                logger.debug(f"[{self.name}] Initialized: {data.get('result', {}).get('serverInfo', {})}")

        await self._send_initialized_notification()

    async def _send_initialized_notification(self):
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._mcp_session_id:
            headers["mcp-session-id"] = self._mcp_session_id

        async with self._session.post(self.config.url, json=payload, headers=headers) as resp:
            if resp.status not in (200, 202, 204):
                logger.warning(
                    f"[{self.name}] notifications/initialized returned HTTP {resp.status}"
                )
            else:
                logger.debug(f"[{self.name}] notifications/initialized sent successfully")

    async def disconnect(self):
        if self._session:
            await self._session.close()
            self._session = None
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None
        logger.info(f"[{self.name}] Disconnected")

    async def list_tools(self) -> List[MCPTool]:
        try:
            result = await self._request("tools/list", {})
            tools = []
            for t in result.get("tools", []):
                name = t.get("name", "")
                if name:
                    tool = MCPTool(
                        name=f"mcp_{self.name}_{name}",
                        server=self.name,
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                    )
                    tools.append(tool)
            logger.info(f"[{self.name}] Found {len(tools)} tools")
            return tools
        except Exception as e:
            logger.error(f"[{self.name}] Tool discovery failed: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        prefix = f"mcp_{self.name}_"
        original = tool_name[len(prefix):] if tool_name.startswith(prefix) else tool_name

        try:
            result = await self._request("tools/call", {"name": original, "arguments": arguments})
            content = result.get("content", [])
            if isinstance(content, list):
                text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
                return {"status": "success", "result": text or str(content)}
            return {"status": "success", "result": str(result)}
        except Exception as e:
            logger.error(f"[{self.name}] Tool call failed: {e}")
            return {"status": "error", "error": str(e)}

    async def _request(self, method: str, params: dict) -> dict:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params}

        if self.config.transport == "stdio":
            return await self._stdio_request(payload)
        return await self._http_request(payload)

    async def _stdio_request(self, payload: dict) -> dict:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("Process not running")

        self._process.stdin.write((json.dumps(payload) + "\n").encode())
        self._process.stdin.flush()

        try:
            line = await asyncio.wait_for(
                asyncio.to_thread(self._process.stdout.readline),
                timeout=self.config.timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"[{self.name}] stdio request timed out after {self.config.timeout}s"
            )
        resp = json.loads(line.decode())
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp.get("result", {})

    async def _http_request(self, payload: dict) -> dict:
        if not self._session or not self.config.url:
            raise RuntimeError("HTTP session not ready")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._mcp_session_id:
            headers["mcp-session-id"] = self._mcp_session_id

        async with self._session.post(self.config.url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}: {await resp.text()}")

            content_type = resp.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                async for line in resp.content:
                    line = line.decode().strip()
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "error" in data:
                            raise RuntimeError(data["error"])
                        return data.get("result", {})
                raise RuntimeError("No data in SSE response")

            data = await resp.json()
            if "error" in data:
                raise RuntimeError(data["error"])
            return data.get("result", {})


def load_config(path: Optional[str] = None) -> List[ServerConfig]:
    config_path = Path(path or settings.MCP_CONFIG_FILE)
    if not config_path.exists():
        logger.info(f"MCP config not found: {config_path}")
        return []

    try:
        data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load MCP config: {e}")
        return []

    configs = []
    for s in data.get("servers", []):
        if s.get("name"):
            raw_defaults = s.get("tool_defaults", {})
            tool_defaults = {
                k: v for k, v in raw_defaults.items()
                if isinstance(v, dict) and not k.startswith("_")
            }
            configs.append(ServerConfig(
                name=s["name"],
                transport=s.get("transport", "http"),
                url=s.get("url"),
                command=s.get("command"),
                args=s.get("args", []),
                env=s.get("env", {}),
                enabled=s.get("enabled", True),
                timeout=s.get("timeout", 30.0),
                description=s.get("description", ""),
                tool_defaults=tool_defaults,
            ))
    logger.info(f"Loaded {len(configs)} MCP server config(s)")
    return configs


async def initialize_mcp_servers() -> Tuple[Dict[str, Callable], List[dict]]:
    """Connect to all enabled MCP servers and discover tools."""
    global _servers, _tools

    configs = [c for c in load_config() if c.enabled]
    if not configs:
        logger.info("No MCP servers enabled")
        return {}, []

    tool_map: Dict[str, Callable] = {}
    schemas: List[dict] = []

    for cfg in configs:
        server = MCPServer(cfg)
        if not await server.connect():
            logger.warning(
                f"[{cfg.name}] Failed to connect — tools from this server will be "
                f"unavailable. Check server config (transport={cfg.transport}, "
                f"url={cfg.url or 'stdio'})"
            )
            continue

        _servers[cfg.name] = server
        for tool in await server.list_tools():
            original_name = tool.name.removeprefix(f"mcp_{cfg.name}_")
            tool.default_arguments = cfg.tool_defaults.get(original_name, {})
            _tools[tool.name] = tool
            schemas.append(tool.to_schema())
            tool_map[tool.name] = _make_caller(server, tool)

    logger.info(f"MCP ready: {len(_servers)} server(s), {len(tool_map)} tool(s)")
    return tool_map, schemas


def _make_caller(server: MCPServer, tool: MCPTool) -> Callable:
    allowed_args = set(tool.input_schema.get("properties", {}).keys()) if tool.input_schema else set()
    defaults = dict(tool.default_arguments)

    async def call(**kwargs) -> dict:
        merged = {**defaults, **kwargs}
        arguments = {k: v for k, v in merged.items() if k in allowed_args}
        return await server.call_tool(tool.name, arguments)

    call.__name__ = tool.name
    call.__doc__ = tool.description or f"Invoke MCP tool {tool.name}"
    return call


async def shutdown_mcp_servers():
    for server in _servers.values():
        await server.disconnect()
    _servers.clear()
    _tools.clear()
    logger.info("MCP shutdown complete")


def get_mcp_tools() -> Dict[str, MCPTool]:
    return _tools.copy()


def get_mcp_servers() -> Dict[str, MCPServer]:
    return _servers


def get_mcp_server_status() -> List[dict]:
    return [
        {
            "name": s.name,
            "connected": s._session is not None or s._process is not None,
            "transport": s.config.transport,
            "url": s.config.url,
        }
        for s in _servers.values()
    ]


def get_tool_defaults(tool_name: str) -> dict:
    tool = _tools.get(tool_name)
    return dict(tool.default_arguments) if tool else {}
