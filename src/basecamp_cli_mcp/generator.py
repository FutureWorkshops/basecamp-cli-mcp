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

    def generate(self) -> list[dict[str, Any]]:
        categories = self._list_commands()
        tools: list[dict[str, Any]] = []

        for category in categories:
            if category.get("name") == "Shortcuts":
                continue
            for cmd in category.get("commands") or []:
                group = cmd["name"]
                for action in cmd.get("actions") or []:
                    tools.append(self._tool_for(group, action))

        tools.sort(key=lambda t: t["name"])
        return tools

    def _tool_for(self, group: str, action: str) -> dict[str, Any]:
        parsed = help_parser.parse(self._help_text(group, action))
        summary = parsed["summary"] or f"{action} {group}"
        return {
            "name": f"{group}_{action}",
            "group": group,
            "action": action,
            "description": summary,
            "positional": parsed["positional"],
            "flags": parsed["flags"],
            "input_schema": self._build_schema(parsed),
        }

    @staticmethod
    def _build_schema(parsed: help_parser.Parsed) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for pos in parsed["positional"]:
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

    def _help_text(self, group: str, action: str) -> str:
        result = subprocess.run(
            [self.basecamp_bin, group, action, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout


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
