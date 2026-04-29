from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

# Workaround for https://github.com/basecamp/basecamp-cli/issues/412 —
# `basecamp todos update --due ...` returns 200 but the CLI silently drops
# fields from the PUT payload, so the server never sees them. Until that ships,
# route todo updates through `basecamp api put` with a merged body.
TODOS_UPDATE_ISSUE_URL = "https://github.com/basecamp/basecamp-cli/issues/412"


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
        params = params or {}
        if tool_spec.get("group") == "todos" and tool_spec.get("action") == "update":
            return self._todos_update_via_api(params)
        argv = self.build_argv(tool_spec, params)
        return self._invoke(argv)

    def _invoke(self, argv: list[str]) -> Any:
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

    def _todos_update_via_api(self, params: dict[str, Any]) -> Any:
        todo_id = params.get("id") or params.get("todo_id")
        project_id = params.get("project") or params.get("in")
        if not todo_id or not project_id:
            raise ValueError(
                "todos.update workaround requires 'id' and 'project' params "
                f"(see {TODOS_UPDATE_ISSUE_URL})"
            )

        print(
            f"[basecamp-cli-mcp] todos.update for todo={todo_id} project={project_id} "
            f"-> routing via `basecamp api put` (workaround for {TODOS_UPDATE_ISSUE_URL})",
            file=sys.stderr,
        )

        path = f"/buckets/{project_id}/todos/{todo_id}.json"
        current = self._invoke(["api", "get", path, "--json"])
        if not isinstance(current, dict):
            raise BasecampError(f"Unexpected response fetching todo {todo_id}: {current!r}")

        body = self._merge_todo_body(current, params)

        print(
            f"[basecamp-cli-mcp] PUT {path} body={json.dumps(body, sort_keys=True)}",
            file=sys.stderr,
        )
        return self._invoke(["api", "put", path, "-d", json.dumps(body), "--json"])

    @staticmethod
    def _merge_todo_body(current: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "content": current.get("content") or current.get("title") or "",
            "description": current.get("description") or "",
            "due_on": current.get("due_on"),
            "starts_on": current.get("starts_on"),
            "assignee_ids": [a["id"] for a in current.get("assignees") or [] if "id" in a],
            "completion_subscriber_ids": [
                p["id"] for p in current.get("completion_subscribers") or [] if "id" in p
            ],
        }

        title = params.get("title")
        if isinstance(title, str) and title:
            body["content"] = title

        if "description" in params and params["description"] is not None:
            body["description"] = params["description"]
        if params.get("no-description"):
            body["description"] = ""

        if params.get("due"):
            body["due_on"] = params["due"]
        if params.get("no-due"):
            body["due_on"] = None

        if params.get("starts-on"):
            body["starts_on"] = params["starts-on"]
        if params.get("no-starts-on"):
            body["starts_on"] = None

        assignees = params.get("assignee") or params.get("to")
        if assignees is not None:
            body["assignee_ids"] = _parse_id_list(assignees)

        if params.get("notify"):
            body["notify"] = True

        return body

    def build_argv(self, tool_spec: dict[str, Any], params: dict[str, Any]) -> list[str]:
        argv: list[str] = [tool_spec["group"], tool_spec["action"]]

        for pos in tool_spec.get("positional") or []:
            value = params.get(pos["name"])
            if value is None or (not isinstance(value, list) and str(value) == ""):
                if pos.get("required"):
                    raise ValueError(f"Missing required argument: {pos['name']}")
                continue
            if pos.get("variadic"):
                values = value if isinstance(value, list) else [value]
                if not values and pos.get("required"):
                    raise ValueError(f"Missing required argument: {pos['name']}")
                for v in values:
                    argv.append(str(v))
            else:
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


def _parse_id_list(value: Any) -> list[int]:
    if isinstance(value, list):
        items = value
    else:
        items = [v.strip() for v in str(value).split(",") if v.strip()]
    out: list[int] = []
    for item in items:
        try:
            out.append(int(item))
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"todos.update workaround requires numeric assignee IDs, got {item!r}"
            ) from e
    return out
