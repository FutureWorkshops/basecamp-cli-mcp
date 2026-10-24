from pathlib import Path

import pytest

from basecamp_cli_mcp import help_parser


def parse(fixtures: Path, name: str):
    return help_parser.parse((fixtures / f"{name}_help.txt").read_text(encoding="utf-8"))


def test_todos_create_required_positional(fixtures: Path) -> None:
    parsed = parse(fixtures, "todos_create")
    assert {"name": "content", "required": True, "description": "Content"} in parsed["positional"]


def test_todos_create_string_flag(fixtures: Path) -> None:
    parsed = parse(fixtures, "todos_create")
    due = next(f for f in parsed["flags"] if f["name"] == "due")
    assert due["type"] == "string"
    assert due["short"] == "d"


def test_todos_create_string_array_flag(fixtures: Path) -> None:
    parsed = parse(fixtures, "todos_create")
    attach = next(f for f in parsed["flags"] if f["name"] == "attach")
    assert attach["type"] == "array"


def test_todos_create_excludes_help_flag(fixtures: Path) -> None:
    parsed = parse(fixtures, "todos_create")
    assert not any(f["name"] == "help" for f in parsed["flags"])


def test_cards_create_optional_positional(fixtures: Path) -> None:
    parsed = parse(fixtures, "cards_create")
    title = next(p for p in parsed["positional"] if p["name"] == "title")
    body = next(p for p in parsed["positional"] if p["name"] == "body")
    assert title["required"]
    assert not body["required"]


def test_todos_complete_variadic_positional(fixtures: Path) -> None:
    parsed = parse(fixtures, "todos_complete")
    pos = parsed["positional"]
    assert len(pos) == 1
    assert pos[0]["name"] == "id"
    assert pos[0]["required"]
    assert pos[0].get("variadic") is True
    # "or URL" trimmed from description so agents don't think they need to pass URLs.
    assert "URL" not in pos[0]["description"]


def test_summary_extracted(fixtures: Path) -> None:
    parsed = parse(fixtures, "projects_list")
    assert parsed["summary"]


def test_inherited_project_flag_exposed(fixtures: Path) -> None:
    parsed = parse(fixtures, "todos_create")
    project = next(f for f in parsed["flags"] if f["name"] == "project")
    assert project["type"] == "string"
    assert project["short"] == "p"


def test_inherited_output_flags_excluded(fixtures: Path) -> None:
    # --json, --md, --quiet are owned by the runner; should never appear in the schema.
    parsed = parse(fixtures, "todos_create")
    names = {f["name"] for f in parsed["flags"]}
    assert "json" not in names
    assert "md" not in names
    assert "quiet" not in names


def test_summary_stops_at_first_blank_line(fixtures: Path) -> None:
    # todos_complete help has a short description, blank line, then a block of
    # shell-syntax examples. The summary should keep only the first paragraph.
    parsed = parse(fixtures, "todos_complete")
    assert parsed["summary"] == "Mark one or more todos as completed."


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        (None, "boolean"),
        ("bool", "boolean"),
        ("stringArray", "array"),
        ("int", "integer"),
        ("string", "string"),
        ("duration", "string"),
    ],
)
def test_type_hint_mapping(hint: str | None, expected: str) -> None:
    """A bare flag has no hint and is a switch; anything unrecognised is a string."""
    assert help_parser._map_type(hint) == expected


def test_summary_is_empty_when_help_opens_with_usage() -> None:
    """Some actions have no prose description, only a USAGE block."""
    assert help_parser.parse("USAGE\n  basecamp cards move <id>\n")["summary"] == ""


def test_summary_skips_leading_blank_lines() -> None:
    assert help_parser.parse("\n\n  Move a card.\n\nUSAGE\n")["summary"] == "Move a card."
