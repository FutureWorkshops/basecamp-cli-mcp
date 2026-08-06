"""Tests for the `setup` command.

This is the only code in the package that writes outside the repo: it edits the
user's real `claude_desktop_config.json`. The merge and abort paths matter more
than the install plumbing, so they are what's covered here, with the config path
redirected into tmp_path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from basecamp_cli_mcp import setup_cmd


@pytest.fixture
def config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the Claude Desktop config to tmp_path and pretend we're on macOS."""
    path = tmp_path / "Claude" / "claude_desktop_config.json"
    monkeypatch.setattr(setup_cmd, "CLAUDE_DESKTOP_CONFIG_MACOS", path)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(setup_cmd, "_prompt", lambda question: False)
    return path


def choose(monkeypatch: pytest.MonkeyPatch, choice: str) -> None:
    monkeypatch.setattr(setup_cmd, "_prompt_claude_desktop_choice", lambda: choice)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def backups(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f"{path.stem}*.backup.*"))


# --- writing the entry -------------------------------------------------------


def test_full_choice_writes_unfiltered_entry(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    choose(monkeypatch, "full")
    monkeypatch.setattr(setup_cmd.shutil, "which", lambda name: "/opt/homebrew/bin/uvx")

    setup_cmd._maybe_configure_claude_desktop()

    assert read(config_path)["mcpServers"]["basecamp"] == {
        "command": "/opt/homebrew/bin/uvx",
        "args": ["basecamp-cli-mcp"],
    }


def test_minimal_choice_writes_include_flags_in_order(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    choose(monkeypatch, "minimal")
    monkeypatch.setattr(setup_cmd.shutil, "which", lambda name: "/usr/bin/uvx")

    setup_cmd._maybe_configure_claude_desktop()

    args = read(config_path)["mcpServers"]["basecamp"]["args"]
    expected = ["basecamp-cli-mcp"]
    for pattern in setup_cmd.MINIMAL_INCLUDES:
        expected += ["--include", pattern]
    assert args == expected


def test_minimal_set_covers_todos_cards_and_comments() -> None:
    """The minimal set is a product decision; pin it so edits are deliberate."""
    assert setup_cmd.MINIMAL_INCLUDES == [
        "todos_*",
        "cards_*",
        "projects_list",
        "assignments_due",
        "comments_create",
    ]


def test_falls_back_to_bare_uvx_when_not_on_path(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    choose(monkeypatch, "full")
    monkeypatch.setattr(setup_cmd.shutil, "which", lambda name: None)

    setup_cmd._maybe_configure_claude_desktop()

    assert read(config_path)["mcpServers"]["basecamp"]["command"] == "uvx"


def test_preserves_other_servers_and_backs_up(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path.parent.mkdir(parents=True)
    original = {
        "mcpServers": {"other": {"command": "node", "args": ["x.js"]}},
        "globalShortcut": "Cmd+Space",
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    choose(monkeypatch, "full")

    setup_cmd._maybe_configure_claude_desktop()

    after = read(config_path)
    assert after["mcpServers"]["other"] == {"command": "node", "args": ["x.js"]}
    assert after["globalShortcut"] == "Cmd+Space"
    assert "basecamp" in after["mcpServers"]
    assert [json.loads(b.read_text()) for b in backups(config_path)] == [original]


def test_replaces_an_existing_basecamp_entry(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"mcpServers": {"basecamp": {"command": "stale", "args": []}}}),
        encoding="utf-8",
    )
    choose(monkeypatch, "full")

    setup_cmd._maybe_configure_claude_desktop()

    assert read(config_path)["mcpServers"]["basecamp"]["command"] != "stale"


# --- paths that must not write ----------------------------------------------


def test_skip_choice_writes_nothing(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    choose(monkeypatch, "skip")
    setup_cmd._maybe_configure_claude_desktop()
    assert not config_path.exists()


def test_non_macos_is_a_noop(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    choose(monkeypatch, "full")
    setup_cmd._maybe_configure_claude_desktop()
    assert not config_path.exists()


def test_unparseable_config_aborts_and_leaves_file_untouched(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{ this is not json", encoding="utf-8")
    choose(monkeypatch, "full")

    setup_cmd._maybe_configure_claude_desktop()

    assert config_path.read_text(encoding="utf-8") == "{ this is not json"
    assert len(backups(config_path)) == 1


def test_non_object_top_level_aborts(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path.parent.mkdir(parents=True)
    config_path.write_text('["not", "an", "object"]', encoding="utf-8")
    choose(monkeypatch, "full")

    setup_cmd._maybe_configure_claude_desktop()

    assert read(config_path) == ["not", "an", "object"]


def test_non_object_mcpservers_aborts(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"mcpServers": []}), encoding="utf-8")
    choose(monkeypatch, "full")

    setup_cmd._maybe_configure_claude_desktop()

    assert read(config_path) == {"mcpServers": []}


# --- restart prompt ----------------------------------------------------------


def test_declining_restart_runs_nothing(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    choose(monkeypatch, "full")
    calls: list[list[str]] = []
    monkeypatch.setattr(setup_cmd.subprocess, "run", lambda argv, **kw: calls.append(argv))

    setup_cmd._maybe_configure_claude_desktop()

    assert calls == []


def test_accepting_restart_quits_and_reopens_claude(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    choose(monkeypatch, "full")
    monkeypatch.setattr(setup_cmd, "_prompt", lambda question: True)
    monkeypatch.setattr(setup_cmd.time, "sleep", lambda seconds: None)
    calls: list[list[str]] = []
    monkeypatch.setattr(setup_cmd.subprocess, "run", lambda argv, **kw: calls.append(argv))

    setup_cmd._maybe_configure_claude_desktop()

    assert calls[0][0] == "osascript"
    assert calls[-1] == ["open", "-a", "Claude"]


# --- prompt parsing ----------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("1", "minimal"), ("2", "full"), ("3", "skip"), ("", "skip"), ("garbage", "skip")],
)
def test_choice_prompt_mapping(
    monkeypatch: pytest.MonkeyPatch, typed: str, expected: str
) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt="": typed)
    assert setup_cmd._prompt_claude_desktop_choice() == expected


def test_choice_prompt_defaults_to_skip_on_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_eof(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert setup_cmd._prompt_claude_desktop_choice() == "skip"


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("y", True), ("Y", True), ("yes", True), ("n", False), ("", False), ("maybe", False)],
)
def test_yes_no_prompt(monkeypatch: pytest.MonkeyPatch, typed: str, expected: bool) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt="": typed)
    assert setup_cmd._prompt("Proceed?") is expected


# --- binary resolution -------------------------------------------------------


def test_resolve_binary_prefers_executable_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "basecamp"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("BASECAMP_BIN", str(fake))

    assert setup_cmd._resolve_binary() == str(fake)


def test_resolve_binary_ignores_non_executable_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dud = tmp_path / "basecamp"
    dud.write_text("not executable", encoding="utf-8")
    dud.chmod(0o644)
    monkeypatch.setenv("BASECAMP_BIN", str(dud))
    monkeypatch.setattr(setup_cmd.shutil, "which", lambda name: "/usr/local/bin/basecamp")

    assert setup_cmd._resolve_binary() == "/usr/local/bin/basecamp"


def test_resolve_binary_falls_back_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BASECAMP_BIN", raising=False)
    monkeypatch.setattr(setup_cmd.shutil, "which", lambda name: None)
    assert setup_cmd._resolve_binary() is None


# --- run() control flow ------------------------------------------------------


def test_run_propagates_basecamp_setup_failure_without_touching_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(setup_cmd, "_resolve_binary", lambda: "/usr/local/bin/basecamp")
    monkeypatch.setattr(
        setup_cmd.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 3),
    )
    configured = []
    monkeypatch.setattr(
        setup_cmd, "_maybe_configure_claude_desktop", lambda: configured.append(True)
    )

    assert setup_cmd.run() == 3
    assert configured == []


def test_run_configures_claude_desktop_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup_cmd, "_resolve_binary", lambda: "/usr/local/bin/basecamp")
    monkeypatch.setattr(
        setup_cmd.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0),
    )
    configured = []
    monkeypatch.setattr(
        setup_cmd, "_maybe_configure_claude_desktop", lambda: configured.append(True)
    )

    assert setup_cmd.run() == 0
    assert configured == [True]


def test_run_on_windows_without_binary_gives_manual_instructions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(setup_cmd, "_resolve_binary", lambda: None)

    assert setup_cmd.run() == 1
    assert setup_cmd.WINDOWS_INSTALL_CMD in capsys.readouterr().err


def test_run_aborts_when_installer_is_declined(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(setup_cmd, "_resolve_binary", lambda: None)
    monkeypatch.setattr(setup_cmd, "_prompt", lambda question: False)

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not run the installer after a declined prompt")

    monkeypatch.setattr(setup_cmd.subprocess, "run", fail)

    assert setup_cmd.run() == 1


# --- installer path ----------------------------------------------------------


def test_prompt_declines_on_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_eof(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert setup_cmd._prompt("Proceed?") is False


def test_installer_failure_returns_its_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(setup_cmd, "_resolve_binary", lambda: None)
    monkeypatch.setattr(setup_cmd, "_prompt", lambda question: True)
    monkeypatch.setattr(
        setup_cmd.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 4),
    )

    assert setup_cmd.run() == 4
    assert setup_cmd.INSTALL_DOCS_URL in capsys.readouterr().err


def test_installer_succeeding_without_a_binary_on_path_fails_clearly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Common case: the installer wrote to a dir the current shell hasn't picked up."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(setup_cmd, "_resolve_binary", lambda: None)
    monkeypatch.setattr(setup_cmd, "_prompt", lambda question: True)
    monkeypatch.setattr(
        setup_cmd.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0),
    )

    assert setup_cmd.run() == 1
    assert "restart your shell" in capsys.readouterr().err


def test_installer_success_continues_to_basecamp_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    resolved = iter([None, "/usr/local/bin/basecamp"])
    monkeypatch.setattr(setup_cmd, "_resolve_binary", lambda: next(resolved))
    monkeypatch.setattr(setup_cmd, "_prompt", lambda question: True)
    ran: list[list[str]] = []

    def fake_run(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(setup_cmd.subprocess, "run", fake_run)
    monkeypatch.setattr(setup_cmd, "_maybe_configure_claude_desktop", lambda: None)

    assert setup_cmd.run() == 0
    assert ran[0] == ["bash", "-c", setup_cmd.INSTALL_CMD]
    assert ran[1] == ["/usr/local/bin/basecamp", "setup"]
