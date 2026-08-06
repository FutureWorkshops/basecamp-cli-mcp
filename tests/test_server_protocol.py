"""End-to-end protocol tests over in-memory streams.

These exercise the real MCP handshake against `build_server`, which is what the
mcp 1.x -> 2.x migration broke: the old decorator API failed at server
construction, so a unit test of `filter_specs` alone would not have caught it.
"""

from __future__ import annotations

import json
from functools import partial
from typing import Any

import anyio
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from basecamp_cli_mcp.runner import BasecampError
from basecamp_cli_mcp.server import build_server

pytestmark = pytest.mark.anyio

SPECS: list[dict[str, Any]] = [
    {
        "name": "projects_list",
        "argv_prefix": ["projects", "list"],
        "group": "projects",
        "action": "list",
        "description": "List all projects.",
        "positional": [],
        "flags": [],
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "todos_create",
        "argv_prefix": ["todos", "create"],
        "group": "todos",
        "action": "create",
        "description": "Create a to-do.",
        "positional": [{"name": "content", "required": True, "description": "Content"}],
        "flags": [],
        "input_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    },
]


class FakeRunner:
    """Stands in for `Runner`, recording calls instead of shelling out."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool_spec: dict[str, Any], params: dict[str, Any] | None) -> Any:
        self.calls.append((tool_spec["name"], params or {}))
        if self.error is not None:
            raise self.error
        return self.result


async def _session(runner: FakeRunner, **kwargs: Any):
    """Yield an initialized ClientSession wired to a server over memory streams."""
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        server = build_server(tool_specs=SPECS, runner=runner, **kwargs)
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                partial(
                    server.run,
                    server_streams[0],
                    server_streams[1],
                    server.create_initialization_options(),
                    raise_exceptions=True,
                )
            )
            async with ClientSession(client_streams[0], client_streams[1]) as session:
                await session.initialize()
                yield session
            tg.cancel_scope.cancel()


async def test_initialize_and_list_tools() -> None:
    async for session in _session(FakeRunner()):
        result = await session.list_tools()
        assert [t.name for t in result.tools] == ["projects_list", "todos_create"]
        todos = result.tools[1]
        assert todos.description == "Create a to-do."
        assert todos.input_schema["required"] == ["content"]


async def test_list_tools_honours_filters() -> None:
    async for session in _session(FakeRunner(), include=["todos_*"]):
        result = await session.list_tools()
        assert [t.name for t in result.tools] == ["todos_create"]


async def test_call_tool_returns_json_payload() -> None:
    runner = FakeRunner(result=[{"id": 1, "name": "Acme"}])
    async for session in _session(runner):
        result = await session.call_tool("projects_list", {})
        assert result.is_error in (None, False)
        assert json.loads(result.content[0].text) == [{"id": 1, "name": "Acme"}]
        assert runner.calls == [("projects_list", {})]


async def test_call_tool_passes_arguments_through() -> None:
    runner = FakeRunner(result={"id": 7})
    async for session in _session(runner):
        await session.call_tool("todos_create", {"content": "Ship it"})
        assert runner.calls == [("todos_create", {"content": "Ship it"})]


async def test_call_tool_returns_empty_text_for_null_payload() -> None:
    async for session in _session(FakeRunner(result=None)):
        result = await session.call_tool("projects_list", {})
        assert result.content[0].text == ""


async def test_basecamp_error_becomes_error_result_with_stderr() -> None:
    error = BasecampError("access denied", stderr="401 Unauthorized")
    async for session in _session(FakeRunner(error=error)):
        result = await session.call_tool("projects_list", {})
        assert result.is_error is True
        assert result.content[0].text == "access denied\n401 Unauthorized"


async def test_unknown_tool_becomes_error_result() -> None:
    async for session in _session(FakeRunner()):
        result = await session.call_tool("nope_missing", {})
        assert result.is_error is True
        assert "Unknown tool: nope_missing" in result.content[0].text
