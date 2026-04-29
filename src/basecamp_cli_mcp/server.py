from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from . import __version__
from .runner import BasecampError, Runner

INSTRUCTIONS = (
    "Wraps the `basecamp` CLI. Each tool corresponds to a CLI action; all tools "
    "return the parsed JSON payload from the CLI."
)


def _load_tool_specs() -> list[dict[str, Any]]:
    path = files("basecamp_cli_mcp") / "data" / "tools.json"
    return json.loads(path.read_text(encoding="utf-8"))


def build_server(tool_specs: list[dict[str, Any]] | None = None, runner: Runner | None = None) -> Server:
    specs = tool_specs if tool_specs is not None else _load_tool_specs()
    runner = runner or Runner()
    by_name = {s["name"]: s for s in specs}

    server: Server = Server(name="basecamp", version=__version__, instructions=INSTRUCTIONS)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=s["name"],
                description=s["description"],
                inputSchema=s["input_schema"],
            )
            for s in specs
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        spec = by_name.get(name)
        if spec is None:
            raise ValueError(f"Unknown tool: {name}")
        try:
            data = runner.call(spec, arguments or {})
        except BasecampError as e:
            detail = f"\n{e.stderr}" if e.stderr else ""
            raise RuntimeError(f"{e}{detail}") from e

        if data is None:
            text = ""
        elif isinstance(data, str):
            text = data
        else:
            text = json.dumps(data, indent=2)
        return [types.TextContent(type="text", text=text)]

    return server


async def run() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
