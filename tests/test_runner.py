import pytest

from basecamp_cli_mcp.runner import Runner

SPEC = {
    "group": "todos",
    "action": "create",
    "positional": [
        {"name": "content", "required": True, "description": "Content"},
    ],
    "flags": [
        {"name": "project", "type": "string", "description": "Project"},
        {"name": "attach", "type": "array", "description": "Attach"},
        {"name": "verbose", "type": "boolean", "description": "Verbose"},
    ],
}


@pytest.fixture
def runner() -> Runner:
    return Runner()


def test_build_argv_positional_and_flags(runner: Runner) -> None:
    argv = runner.build_argv(
        SPEC,
        {
            "content": "Write docs",
            "project": "123",
            "attach": ["a.png", "b.png"],
            "verbose": True,
        },
    )
    assert argv == [
        "todos", "create", "Write docs",
        "--project", "123",
        "--attach", "a.png",
        "--attach", "b.png",
        "--verbose",
        "--json",
    ]


def test_build_argv_omits_nil_flags(runner: Runner) -> None:
    assert runner.build_argv(SPEC, {"content": "x"}) == ["todos", "create", "x", "--json"]


def test_build_argv_omits_false_boolean(runner: Runner) -> None:
    assert runner.build_argv(SPEC, {"content": "x", "verbose": False}) == [
        "todos", "create", "x", "--json",
    ]


def test_build_argv_raises_on_missing_required(runner: Runner) -> None:
    with pytest.raises(ValueError):
        runner.build_argv(SPEC, {})


def test_parse_envelope_valid_json() -> None:
    assert Runner.parse_envelope('{"ok":true,"data":[1,2]}') == {"ok": True, "data": [1, 2]}


def test_parse_envelope_invalid_returns_none() -> None:
    assert Runner.parse_envelope("not json") is None
