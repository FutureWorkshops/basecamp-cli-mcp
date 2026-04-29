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


def test_summary_extracted(fixtures: Path) -> None:
    parsed = parse(fixtures, "projects_list")
    assert parsed["summary"]
