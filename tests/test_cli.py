"""Tests for the `basecamp-cli-mcp` entry point.

Mostly about wiring: that flags reach `server.run`, that `generate` writes where
it's told, and that `setup` dispatches. The subcommand bodies are stubbed — the
real generator shells out to the basecamp CLI, and `setup` installs software.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from basecamp_cli_mcp import cli


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture the kwargs the stdio server would have been started with."""
    calls: list[dict[str, Any]] = []

    async def fake_run(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr("basecamp_cli_mcp.server.run", fake_run)
    return calls


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    from basecamp_cli_mcp import __version__

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])

    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_arguments_serves_every_tool(served: list[dict[str, Any]]) -> None:
    assert cli.main([]) == 0
    assert served == [{"include": None, "exclude": None}]


def test_include_flags_accumulate(served: list[dict[str, Any]]) -> None:
    cli.main(["--include", "cards_*", "--include", "todos_*"])
    assert served[0]["include"] == ["cards_*", "todos_*"]


def test_exclude_flags_accumulate(served: list[dict[str, Any]]) -> None:
    cli.main(["--exclude", "api_*", "--exclude", "webhooks_*"])
    assert served[0]["exclude"] == ["api_*", "webhooks_*"]


def test_include_and_exclude_combine(served: list[dict[str, Any]]) -> None:
    cli.main(["--include", "todos_*", "--exclude", "todos_trash"])
    assert served[0] == {"include": ["todos_*"], "exclude": ["todos_trash"]}


# --- generate ----------------------------------------------------------------


class FakeGenerator:
    TOOLS = [{"name": "todos_create", "group": "todos", "action": "create"}]

    def generate(self) -> list[dict[str, Any]]:
        return self.TOOLS


def test_generate_writes_to_explicit_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("basecamp_cli_mcp.generator.Generator", FakeGenerator)
    out = tmp_path / "nested" / "tools.json"

    assert cli.main(["generate", "--output", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == FakeGenerator.TOOLS
    assert "Wrote 1 tools" in capsys.readouterr().err


def test_generate_defaults_to_the_in_tree_data_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --output it targets the packaged data dir, not the cwd."""
    monkeypatch.setattr("basecamp_cli_mcp.generator.Generator", FakeGenerator)
    monkeypatch.setattr(cli, "files", lambda package: tmp_path)

    assert cli.main(["generate"]) == 0
    assert json.loads((tmp_path / "data" / "tools.json").read_text()) == FakeGenerator.TOOLS


def test_generated_file_ends_with_a_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keeps the committed contract diff-clean."""
    monkeypatch.setattr("basecamp_cli_mcp.generator.Generator", FakeGenerator)
    out = tmp_path / "tools.json"

    cli.main(["generate", "--output", str(out)])

    assert out.read_text(encoding="utf-8").endswith("}\n]\n")


# --- setup -------------------------------------------------------------------


def test_setup_dispatches_and_returns_its_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("basecamp_cli_mcp.setup_cmd.run", lambda: 7)
    assert cli.main(["setup"]) == 7
