"""Tests for the offline schema generator.

The generator only touches the outside world through `_list_commands`,
`_subcommands`, and `_help_text`, so a subclass that replays canned CLI output
exercises the whole tree walk: category skipping, nested-group discovery, alias
dedupe, name derivation, and schema assembly.

This is what should catch a structural regression after a basecamp CLI upgrade,
while the tools.json diff is still under review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from basecamp_cli_mcp.generator import Generator, _flag_schema


class FakeCLI(Generator):
    """Replays canned `commands --json`, `--agent --help`, and `--help` output."""

    def __init__(
        self,
        categories: list[dict[str, Any]],
        subcommands: dict[tuple[str, ...], list[dict[str, Any]]] | None = None,
        help_text: dict[tuple[str, ...], str] | None = None,
    ) -> None:
        super().__init__("basecamp")
        self._categories = categories
        self._subs = subcommands or {}
        self._help = help_text or {}

    def _list_commands(self) -> list[dict[str, Any]]:
        return self._categories

    def _subcommands(self, path: list[str]) -> list[dict[str, Any]]:
        return self._subs.get(tuple(path), [])

    def _help_text(self, path: list[str]) -> str:
        return self._help.get(tuple(path), "")


def category(name: str, *commands: str) -> dict[str, Any]:
    return {"name": name, "commands": [{"name": c} for c in commands]}


def sub(name: str, short: str = "") -> dict[str, Any]:
    return {"name": name, "short": short}


# --- walking the command tree ------------------------------------------------


def test_shortcuts_category_is_skipped() -> None:
    gen = FakeCLI(
        [category("Core", "projects"), category("Shortcuts", "todo")],
        {("projects",): [sub("list", "List projects")], ("todo",): [sub("add", "Add")]},
    )
    assert [t["name"] for t in gen.generate()] == ["projects_list"]


def test_bare_top_level_group_emits_nothing() -> None:
    """A group with no subcommands isn't a real action, just a namespace."""
    assert FakeCLI([category("Core", "projects")]).generate() == []


def test_nested_groups_are_walked() -> None:
    gen = FakeCLI(
        [category("Core", "cards")],
        {
            ("cards",): [sub("step", "Manage steps")],
            ("cards", "step"): [sub("create", "Create a step"), sub("complete", "Complete")],
        },
    )
    assert [t["name"] for t in gen.generate()] == ["cards_step_complete", "cards_step_create"]


def test_output_is_sorted_by_name() -> None:
    gen = FakeCLI(
        [category("Core", "todos")],
        {("todos",): [sub("update", "Update"), sub("create", "Create"), sub("list", "List")]},
    )
    names = [t["name"] for t in gen.generate()]
    assert names == sorted(names)


def test_recursion_stops_at_max_depth() -> None:
    """A CLI that reports itself as its own child must not spin forever."""
    subs = {
        ("g",): [sub("a", "A")],
        ("g", "a"): [sub("b", "B")],
        ("g", "a", "b"): [sub("c", "C")],
        ("g", "a", "b", "c"): [sub("d", "D")],
        ("g", "a", "b", "c", "d"): [sub("e", "E")],
        ("g", "a", "b", "c", "d", "e"): [sub("f", "F")],
    }
    tools = FakeCLI([category("Core", "g")], subs).generate()
    assert tools == []  # every leaf sits past _MAX_DEPTH


# --- alias dedupe ------------------------------------------------------------


def test_aliases_sharing_a_description_collapse_to_the_longer_name() -> None:
    gen = FakeCLI(
        [category("Core", "cards")],
        {("cards",): [sub("mv", "Move a card"), sub("move", "Move a card")]},
    )
    assert [t["name"] for t in gen.generate()] == ["cards_move"]


def test_distinct_descriptions_are_kept_apart() -> None:
    gen = FakeCLI(
        [category("Core", "cards")],
        {("cards",): [sub("move", "Move a card"), sub("copy", "Copy a card")]},
    )
    assert sorted(t["name"] for t in gen.generate()) == ["cards_copy", "cards_move"]


def test_subcommands_without_descriptions_collapse_together() -> None:
    """Sharp edge, pinned so a change is visible rather than silent.

    Dedupe keys on the short description, so siblings that carry none all share
    the "" key and only one survives. The survivor is the longest name, and ties
    keep whichever the CLI listed first, so here three real actions collapse to
    `create` (tied with `update` at 6 characters, listed earlier).
    """
    gen = FakeCLI(
        [category("Core", "cards")],
        {("cards",): [sub("create"), sub("update"), sub("trash")]},
    )
    assert [t["name"] for t in gen.generate()] == ["cards_create"]


# --- per-tool fields ---------------------------------------------------------


def test_name_argv_prefix_group_and_action_derivation() -> None:
    gen = FakeCLI(
        [category("Core", "cards")],
        {("cards",): [sub("step", "Steps")], ("cards", "step"): [sub("create", "Create")]},
    )
    tool = gen.generate()[0]
    assert tool["name"] == "cards_step_create"
    assert tool["argv_prefix"] == ["cards", "step", "create"]
    assert tool["group"] == "cards"
    assert tool["action"] == "step_create"


def test_description_falls_back_to_the_command_path() -> None:
    gen = FakeCLI(
        [category("Core", "cards")],
        {("cards",): [sub("create", "Create")]},
        help_text={("cards", "create"): ""},
    )
    assert gen.generate()[0]["description"] == "cards create"


def test_project_flag_is_injected_when_the_cli_omits_it() -> None:
    gen = FakeCLI([category("Core", "todos")], {("todos",): [sub("list", "List")]})
    tool = gen.generate()[0]
    project = [f for f in tool["flags"] if f["name"] == "project"]
    assert project == [
        {"name": "project", "short": "p", "type": "string", "description": "Project ID"}
    ]
    assert "project" in tool["input_schema"]["properties"]


def test_project_flag_is_not_duplicated(fixtures: Path) -> None:
    """`todos create --help` already declares --project; keep the CLI's own text."""
    gen = FakeCLI(
        [category("Core", "todos")],
        {("todos",): [sub("create", "Create")]},
        help_text={
            ("todos", "create"): (fixtures / "todos_create_help.txt").read_text(
                encoding="utf-8"
            )
        },
    )
    tool = gen.generate()[0]
    assert [f["name"] for f in tool["flags"]].count("project") == 1


def test_real_help_text_produces_a_usable_spec(fixtures: Path) -> None:
    gen = FakeCLI(
        [category("Core", "todos")],
        {("todos",): [sub("create", "Create a to-do")]},
        help_text={
            ("todos", "create"): (fixtures / "todos_create_help.txt").read_text(
                encoding="utf-8"
            )
        },
    )
    tool = gen.generate()[0]
    schema = tool["input_schema"]
    assert schema["type"] == "object"
    assert tool["description"]
    assert schema["properties"]
    # Whatever the CLI marks as a required positional must be required here too.
    for pos in tool["positional"]:
        if pos["required"]:
            assert pos["name"] in schema["required"]


# --- schema assembly ---------------------------------------------------------


def test_build_schema_maps_positionals_and_required() -> None:
    schema = Generator._build_schema(
        {
            "summary": "x",
            "positional": [
                {"name": "content", "required": True, "description": "Content"},
                {"name": "note", "required": False, "description": "Note"},
            ],
            "flags": [],
        }
    )
    assert schema["properties"]["content"] == {"type": "string", "description": "Content"}
    assert schema["required"] == ["content"]


def test_build_schema_maps_variadic_positional_to_array() -> None:
    schema = Generator._build_schema(
        {
            "summary": "x",
            "positional": [
                {"name": "id", "required": True, "description": "IDs", "variadic": True}
            ],
            "flags": [],
        }
    )
    assert schema["properties"]["id"] == {
        "type": "array",
        "items": {"type": "string"},
        "description": "IDs",
    }


def test_build_schema_omits_required_when_nothing_is_required() -> None:
    schema = Generator._build_schema({"summary": "x", "positional": [], "flags": []})
    assert "required" not in schema


@pytest.mark.parametrize(
    ("flag_type", "expected"),
    [
        ("array", {"type": "array", "items": {"type": "string"}, "description": "d"}),
        ("integer", {"type": "integer", "description": "d"}),
        ("boolean", {"type": "boolean", "description": "d"}),
        ("string", {"type": "string", "description": "d"}),
        (None, {"type": "string", "description": "d"}),
    ],
)
def test_flag_schema_by_type(flag_type: str | None, expected: dict[str, Any]) -> None:
    assert _flag_schema({"name": "f", "type": flag_type, "description": "d"}) == expected


# --- CLI failure handling ----------------------------------------------------


def test_list_commands_raises_with_stderr_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not logged in")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="not logged in"):
        Generator("basecamp")._list_commands()


def test_list_commands_unwraps_the_data_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    payload = {"ok": True, "data": [{"name": "Core", "commands": []}]}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert Generator("basecamp")._list_commands() == [{"name": "Core", "commands": []}]


def test_subcommands_returns_empty_on_non_json_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A group that doesn't support `--agent` is a leaf, not an error."""
    import subprocess

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="Usage: basecamp ...", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert Generator("basecamp")._subcommands(["cards"]) == []


def test_subcommands_filters_help_and_self_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    meta = {
        "subcommands": [
            {"name": "help"},
            {"name": "cards"},
            {"name": ""},
            {"name": "create", "short": "Create"},
        ]
    }

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(meta), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert Generator("basecamp")._subcommands(["cards"]) == [
        {"name": "create", "short": "Create"}
    ]


def test_help_text_shells_out_to_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="Usage: ...", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert Generator("bc")._help_text(["cards", "create"]) == "Usage: ..."
    assert seen == [["bc", "cards", "create", "--help"]]
