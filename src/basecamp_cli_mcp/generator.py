"""Generate the static tool-schema file from the basecamp CLI.

Run via `basecamp-cli-mcp generate`. Not used at server startup.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from . import help_parser


class Generator:
    def __init__(self, basecamp_bin: str | None = None) -> None:
        self.basecamp_bin = basecamp_bin or os.environ.get("BASECAMP_BIN", "basecamp")

    _MAX_DEPTH = 5

    def generate(self) -> list[dict[str, Any]]:
        # `commands --json` lists canonical top-level groups and skips the
        # Shortcuts category. From each group we walk subcommands via
        # `--agent --help`, since that's the only place nested groups like
        # `cards step` and `cards column` are exposed.
        categories = self._list_commands()
        tools: list[dict[str, Any]] = []

        for category in categories:
            if category.get("name") == "Shortcuts":
                continue
            for cmd in category.get("commands") or []:
                tools.extend(self._tools_for_path([cmd["name"]]))

        tools.sort(key=lambda t: t["name"])
        return tools

    def _tools_for_path(self, path: list[str]) -> list[dict[str, Any]]:
        if len(path) > self._MAX_DEPTH:
            return []
        subs = self._subcommands(path)
        # Drop aliases — when two siblings share a short description, the CLI
        # is exposing the same action twice (e.g. `move`/`mv`). Keep the
        # longer name (or alphabetically last) so generated tool names match
        # what users would type.
        subs = self._dedupe_aliases(subs)
        if not subs:
            # Top-level groups with no subcommands aren't real (every group
            # has at least `help`); only emit a tool when path is deeper than
            # the seed.
            return [self._tool_for_path(path)] if len(path) >= 2 else []
        out: list[dict[str, Any]] = []
        for sub in subs:
            out.extend(self._tools_for_path([*path, sub["name"]]))
        return out

    @staticmethod
    def _dedupe_aliases(subs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_short: dict[str, dict[str, Any]] = {}
        for s in subs:
            short = s.get("short") or ""
            existing = by_short.get(short)
            if existing is None or len(s["name"]) > len(existing["name"]):
                by_short[short] = s
        return list(by_short.values())

    def _tool_for_path(self, path: list[str]) -> dict[str, Any]:
        parsed = help_parser.parse(self._help_text(path))
        flags = list(parsed["flags"])
        if not any(f["name"] == "project" for f in flags):
            flags.append({
                "name": "project",
                "short": "p",
                "type": "string",
                "description": "Project ID",
            })
        parsed_with_project: help_parser.Parsed = {
            "summary": parsed["summary"],
            "positional": parsed["positional"],
            "flags": flags,
        }
        summary = parsed["summary"] or " ".join(path)
        return {
            "name": "_".join(path),
            "argv_prefix": path,
            "group": path[0],
            "action": "_".join(path[1:]),
            "description": summary,
            "positional": parsed["positional"],
            "flags": flags,
            "input_schema": self._build_schema(parsed_with_project),
        }

    @staticmethod
    def _build_schema(parsed: help_parser.Parsed) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for pos in parsed["positional"]:
            if pos.get("variadic"):
                properties[pos["name"]] = {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": pos["description"],
                }
            else:
                properties[pos["name"]] = {"type": "string", "description": pos["description"]}
            if pos["required"]:
                required.append(pos["name"])

        for flag in parsed["flags"]:
            properties[flag["name"]] = _flag_schema(flag)

        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    def _list_commands(self) -> list[dict[str, Any]]:
        result = subprocess.run(
            [self.basecamp_bin, "commands", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(f"basecamp commands --json failed: {result.stderr}")
        envelope = json.loads(result.stdout)
        return envelope["data"]

    def _help_text(self, path: list[str]) -> str:
        result = subprocess.run(
            [self.basecamp_bin, *path, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout

    def _subcommands(self, path: list[str]) -> list[dict[str, Any]]:
        result = subprocess.run(
            [self.basecamp_bin, *path, "--agent", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        try:
            meta = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return []
        return [
            s
            for s in meta.get("subcommands") or []
            if s.get("name") and s["name"] != "help" and s["name"] not in path
        ]


def _flag_schema(flag: help_parser.Flag) -> dict[str, Any]:
    desc = flag.get("description", "")
    ftype = flag.get("type")
    if ftype == "array":
        return {"type": "array", "items": {"type": "string"}, "description": desc}
    if ftype == "integer":
        return {"type": "integer", "description": desc}
    if ftype == "boolean":
        return {"type": "boolean", "description": desc}
    return {"type": "string", "description": desc}
