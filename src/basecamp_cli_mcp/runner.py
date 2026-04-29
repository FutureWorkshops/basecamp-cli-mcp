from __future__ import annotations

import json
import os
import subprocess
from typing import Any


class BasecampError(Exception):
    def __init__(self, message: str, *, stderr: str | None = None, data: Any = None) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.data = data


class Runner:
    """Builds argv for a basecamp CLI invocation and runs it."""

    def __init__(self, basecamp_bin: str | None = None) -> None:
        self.basecamp_bin = basecamp_bin or os.environ.get("BASECAMP_BIN", "basecamp")

    def call(self, tool_spec: dict[str, Any], params: dict[str, Any] | None) -> Any:
        argv = self.build_argv(tool_spec, params or {})
        result = subprocess.run(
            [self.basecamp_bin, *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        payload = self.parse_envelope(result.stdout)

        if result.returncode == 0 and (payload is None or payload.get("ok") is not False):
            return payload["data"] if payload else result.stdout

        if payload and payload.get("error") is not None:
            err = payload["error"]
            if isinstance(err, dict):
                message = err.get("message") or json.dumps(err)
            else:
                message = str(err)
        else:
            message = f"basecamp CLI exited with status {result.returncode}"
        raise BasecampError(message, stderr=result.stderr, data=payload)

    def build_argv(self, tool_spec: dict[str, Any], params: dict[str, Any]) -> list[str]:
        argv: list[str] = [tool_spec["group"], tool_spec["action"]]

        for pos in tool_spec.get("positional") or []:
            value = params.get(pos["name"])
            if value is None or str(value) == "":
                if pos.get("required"):
                    raise ValueError(f"Missing required argument: {pos['name']}")
                continue
            argv.append(str(value))

        for flag in tool_spec.get("flags") or []:
            value = params.get(flag["name"])
            if value is None:
                continue
            ftype = flag.get("type")
            if ftype == "boolean":
                if value:
                    argv.append(f"--{flag['name']}")
            elif ftype == "array":
                values = value if isinstance(value, list) else [value]
                for v in values:
                    argv.extend([f"--{flag['name']}", str(v)])
            else:
                argv.extend([f"--{flag['name']}", str(value)])

        argv.append("--json")
        return argv

    @staticmethod
    def parse_envelope(stdout: str) -> Any:
        try:
            return json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return None
