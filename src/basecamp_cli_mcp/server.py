from __future__ import annotations

import fnmatch
import json
import sys
from importlib.resources import files
from typing import Any

import mcp.types as types
from mcp.server import Server, ServerRequestContext
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


def filter_specs(
    specs: list[dict[str, Any]],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter tool specs by fnmatch glob patterns against the tool name.

    `include` patterns are unioned (a tool matching any pattern is kept);
    if omitted, all tools start as candidates. `exclude` patterns are then
    subtracted.
    """
    out = specs
    if include:
        out = [s for s in out if any(fnmatch.fnmatch(s["name"], p) for p in include)]
    if exclude:
        out = [s for s in out if not any(fnmatch.fnmatch(s["name"], p) for p in exclude)]
    return out


def build_server(
    tool_specs: list[dict[str, Any]] | None = None,
    runner: Runner | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> Server:
    specs = tool_specs if tool_specs is not None else _load_tool_specs()
    if include or exclude:
        before = len(specs)
        specs = filter_specs(specs, include=include, exclude=exclude)
        print(
            f"[basecamp-cli-mcp] tool filter: {before} -> {len(specs)} "
            f"(include={include or []} exclude={exclude or []})",
            file=sys.stderr,
        )
    runner = runner or Runner()
    by_name = {s["name"]: s for s in specs}

    tools = [
        types.Tool(
            name=s["name"],
            description=s["description"],
            input_schema=s["input_schema"],
        )
        for s in specs
    ]

    async def on_list_tools(
        ctx: ServerRequestContext[object],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(
        ctx: ServerRequestContext[object],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        # A failing tool is reported as an error *result*, not a JSON-RPC error, so
        # the client can show the CLI's own message. This matches how the SDK's own
        # MCPServer handles tool exceptions.
        try:
            text = _call_spec(runner, by_name, params.name, params.arguments or {})
        except BasecampError as e:
            detail = f"\n{e.stderr}" if e.stderr else ""
            return _error_result(f"{e}{detail}")
        except Exception as e:  # noqa: BLE001 - surfaced to the client as tool output
            return _error_result(str(e))
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])

    return Server(
        name="basecamp",
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def _call_spec(
    runner: Runner,
    by_name: dict[str, dict[str, Any]],
    name: str,
    arguments: dict[str, Any],
) -> str:
    spec = by_name.get(name)
    if spec is None:
        raise ValueError(f"Unknown tool: {name}")
    data = runner.call(spec, arguments)
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return json.dumps(data, indent=2)


def _error_result(text: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        is_error=True,
    )


async def run(include: list[str] | None = None, exclude: list[str] | None = None) -> None:
    server = build_server(include=include, exclude=exclude)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
