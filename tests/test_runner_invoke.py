"""Tests for `Runner._invoke`, the subprocess + envelope boundary.

The rest of the runner suite subclasses `Runner` and overrides `_invoke`, and
the server suite fakes the whole runner, so this is the seam neither covers:
argv actually reaching a process, and the `{ok, data}` / `{ok: false, error}`
envelope being turned into a return value or a `BasecampError`.

A stub executable stands in for the real `basecamp` CLI so the subprocess call,
stderr capture, and exit-code handling are all real. It is written once per
module and driven by environment variables: macOS scans each newly created
executable on first exec (~0.2s), so a per-test stub would cost more than the
rest of the suite combined.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

import pytest

from basecamp_cli_mcp.runner import BasecampError, Runner

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="stub relies on a shebang"
)

SPEC = {
    "group": "projects",
    "action": "list",
    "argv_prefix": ["projects", "list"],
    "positional": [],
    "flags": [{"name": "project", "type": "string", "description": "Project"}],
}


@pytest.fixture(scope="module")
def stub(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fake `basecamp` that replays $STUB_* output and logs its argv."""
    script = tmp_path_factory.mktemp("stub") / "basecamp"
    script.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" > "$STUB_ARGV"\n'
        'printf %s "$STUB_STDOUT"\n'
        'printf %s "$STUB_STDERR" >&2\n'
        'exit "$STUB_CODE"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


@pytest.fixture
def runner_for(
    stub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Runner]:
    """Build a Runner whose CLI returns the given stdout/stderr/exit code."""
    argv_log = tmp_path / "argv.txt"

    def build(stdout: str = "", stderr: str = "", code: int = 0) -> Runner:
        monkeypatch.setenv("STUB_STDOUT", stdout)
        monkeypatch.setenv("STUB_STDERR", stderr)
        monkeypatch.setenv("STUB_CODE", str(code))
        monkeypatch.setenv("STUB_ARGV", str(argv_log))
        return Runner(str(stub))

    build.argv_log = argv_log  # type: ignore[attr-defined]
    return build


def test_invoke_returns_envelope_data(runner_for: Callable[..., Runner]) -> None:
    runner = runner_for(stdout='{"ok":true,"data":[{"id":1}]}')
    assert runner.call(SPEC, {}) == [{"id": 1}]


def test_invoke_passes_built_argv_to_the_process(runner_for: Callable[..., Runner]) -> None:
    runner = runner_for(stdout='{"ok":true,"data":null}')
    runner.call(SPEC, {"project": "47723798"})
    argv = runner_for.argv_log.read_text(encoding="utf-8").splitlines()  # type: ignore[attr-defined]
    assert argv == ["projects", "list", "--project", "47723798", "--json"]


def test_invoke_returns_raw_stdout_when_not_json(runner_for: Callable[..., Runner]) -> None:
    """No envelope and a clean exit means the CLI printed something unstructured."""
    assert runner_for(stdout="plain text output").call(SPEC, {}) == "plain text output"


def test_invoke_raises_on_ok_false_despite_zero_exit(
    runner_for: Callable[..., Runner]
) -> None:
    """`ok: false` is an error even when the CLI exits 0."""
    runner = runner_for(stdout='{"ok":false,"error":{"message":"access denied"}}', code=0)
    with pytest.raises(BasecampError) as excinfo:
        runner.call(SPEC, {})
    assert str(excinfo.value) == "access denied"


def test_invoke_error_carries_stderr_and_payload(runner_for: Callable[..., Runner]) -> None:
    runner = runner_for(
        stdout='{"ok":false,"error":{"message":"nope"}}',
        stderr="401 Unauthorized",
        code=1,
    )
    with pytest.raises(BasecampError) as excinfo:
        runner.call(SPEC, {})
    assert excinfo.value.stderr == "401 Unauthorized"
    assert excinfo.value.data == {"ok": False, "error": {"message": "nope"}}


def test_invoke_error_dict_without_message_is_serialized(
    runner_for: Callable[..., Runner]
) -> None:
    runner = runner_for(stdout='{"ok":false,"error":{"code":422}}', code=1)
    with pytest.raises(BasecampError) as excinfo:
        runner.call(SPEC, {})
    assert json.loads(str(excinfo.value)) == {"code": 422}


def test_invoke_error_string_is_used_verbatim(runner_for: Callable[..., Runner]) -> None:
    runner = runner_for(stdout='{"ok":false,"error":"boom"}', code=1)
    with pytest.raises(BasecampError, match="^boom$"):
        runner.call(SPEC, {})


def test_invoke_falls_back_to_exit_status_without_envelope(
    runner_for: Callable[..., Runner]
) -> None:
    runner = runner_for(stdout="not json", stderr="segfault", code=2)
    with pytest.raises(BasecampError, match="exited with status 2"):
        runner.call(SPEC, {})


def test_bin_defaults_to_basecamp_bin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASECAMP_BIN", "/opt/custom/basecamp")
    assert Runner().basecamp_bin == "/opt/custom/basecamp"


def test_explicit_bin_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASECAMP_BIN", "/opt/custom/basecamp")
    assert Runner("/usr/local/bin/basecamp").basecamp_bin == "/usr/local/bin/basecamp"
