import json

import pytest

from basecamp_cli_mcp.runner import TODOS_UPDATE_ISSUE_URL, BasecampError, Runner

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

UPDATE_SPEC = {
    "group": "todos",
    "action": "update",
    "positional": [],
    "flags": [],
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


VARIADIC_SPEC = {
    "group": "todos",
    "action": "complete",
    "positional": [
        {"name": "id", "required": True, "variadic": True, "description": "IDs"},
    ],
    "flags": [],
}


def test_build_argv_uses_argv_prefix(runner: Runner) -> None:
    spec = {
        "argv_prefix": ["cards", "step", "complete"],
        "positional": [{"name": "id", "required": True, "description": "ID"}],
        "flags": [],
    }
    argv = runner.build_argv(spec, {"id": "789"})
    assert argv == ["cards", "step", "complete", "789", "--json"]


def test_build_argv_variadic_positional_list(runner: Runner) -> None:
    argv = runner.build_argv(VARIADIC_SPEC, {"id": ["789", "012", "345"]})
    assert argv == ["todos", "complete", "789", "012", "345", "--json"]


def test_build_argv_variadic_positional_scalar(runner: Runner) -> None:
    argv = runner.build_argv(VARIADIC_SPEC, {"id": "789"})
    assert argv == ["todos", "complete", "789", "--json"]


def test_build_argv_variadic_required_raises_on_empty(runner: Runner) -> None:
    with pytest.raises(ValueError):
        runner.build_argv(VARIADIC_SPEC, {"id": []})


def test_parse_envelope_valid_json() -> None:
    assert Runner.parse_envelope('{"ok":true,"data":[1,2]}') == {"ok": True, "data": [1, 2]}


def test_parse_envelope_invalid_returns_none() -> None:
    assert Runner.parse_envelope("not json") is None


class FakeRunner(Runner):
    """Runner that records argv calls and returns scripted responses."""

    def __init__(self, responses: list) -> None:
        super().__init__(basecamp_bin="basecamp")
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def _invoke(self, argv):
        self.calls.append(argv)
        if not self.responses:
            raise AssertionError(f"No scripted response for {argv}")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


CURRENT_TODO = {
    "id": 7118897946,
    "content": "Get quote for roof terrace decking",
    "description": "<div>existing notes</div>",
    "due_on": "2026-04-01",
    "starts_on": None,
    "assignees": [{"id": 38087314, "name": "Matt Brooke-Smith"}],
    "completion_subscribers": [],
}


def test_todos_update_routes_through_api_put(capsys) -> None:
    updated = dict(CURRENT_TODO, due_on="2026-04-29")
    runner = FakeRunner([CURRENT_TODO, updated])

    result = runner.call(UPDATE_SPEC, {"id": 7118897946, "project": 31737525, "due": "2026-04-29"})

    assert result == updated
    assert runner.calls[0] == [
        "api", "get", "/buckets/31737525/todos/7118897946.json", "--json",
    ]
    put_call = runner.calls[1]
    assert put_call[:3] == ["api", "put", "/buckets/31737525/todos/7118897946.json"]
    assert put_call[3] == "-d"
    body = json.loads(put_call[4])
    assert body["due_on"] == "2026-04-29"
    # Existing fields preserved (otherwise the API would clear them).
    assert body["content"] == "Get quote for roof terrace decking"
    assert body["description"] == "<div>existing notes</div>"
    assert body["assignee_ids"] == [38087314]

    err = capsys.readouterr().err
    assert TODOS_UPDATE_ISSUE_URL in err
    assert "PUT /buckets/31737525/todos/7118897946.json" in err


def test_todos_update_clears_due_with_no_due(capsys) -> None:
    runner = FakeRunner([CURRENT_TODO, dict(CURRENT_TODO, due_on=None)])
    runner.call(UPDATE_SPEC, {"id": 1, "project": 2, "no-due": True})
    body = json.loads(runner.calls[1][4])
    assert body["due_on"] is None


def test_todos_update_overrides_title_and_assignees(capsys) -> None:
    runner = FakeRunner([CURRENT_TODO, CURRENT_TODO])
    runner.call(
        UPDATE_SPEC,
        {"id": 1, "project": 2, "title": "New title", "assignee": "100,200"},
    )
    body = json.loads(runner.calls[1][4])
    assert body["content"] == "New title"
    assert body["assignee_ids"] == [100, 200]


def test_todos_update_rejects_non_numeric_assignees() -> None:
    runner = FakeRunner([CURRENT_TODO])
    with pytest.raises(ValueError, match="numeric assignee IDs"):
        runner.call(UPDATE_SPEC, {"id": 1, "project": 2, "assignee": "Matt"})


def test_todos_update_requires_id_and_project() -> None:
    runner = FakeRunner([])
    with pytest.raises(ValueError, match="requires 'id' and 'project'"):
        runner.call(UPDATE_SPEC, {"due": "2026-04-29"})


def test_todos_update_propagates_get_error() -> None:
    runner = FakeRunner([BasecampError("not found")])
    with pytest.raises(BasecampError):
        runner.call(UPDATE_SPEC, {"id": 1, "project": 2, "due": "2026-04-29"})


# --- _merge_todo_body branches ----------------------------------------------
#
# The workaround sends a full PUT body, so every field it does *not* override
# has to be carried over from the current todo. A wrong branch here silently
# wipes a field on the real record.

CURRENT_FULL = {
    "content": "Original title",
    "description": "<div>Original description</div>",
    "due_on": "2026-08-20",
    "starts_on": "2026-08-01",
    "assignees": [{"id": 11}, {"id": 22}],
    "completion_subscribers": [{"id": 33}],
}


def test_merge_preserves_every_untouched_field() -> None:
    body = Runner._merge_todo_body(CURRENT_FULL, {})
    assert body == {
        "content": "Original title",
        "description": "<div>Original description</div>",
        "due_on": "2026-08-20",
        "starts_on": "2026-08-01",
        "assignee_ids": [11, 22],
        "completion_subscriber_ids": [33],
    }


def test_merge_sets_description() -> None:
    body = Runner._merge_todo_body(CURRENT_FULL, {"description": "<div>New</div>"})
    assert body["description"] == "<div>New</div>"


def test_merge_clears_description_with_no_description() -> None:
    body = Runner._merge_todo_body(CURRENT_FULL, {"no-description": True})
    assert body["description"] == ""


def test_merge_sets_and_clears_starts_on() -> None:
    assert Runner._merge_todo_body(CURRENT_FULL, {"starts-on": "2026-09-01"})[
        "starts_on"
    ] == "2026-09-01"
    assert Runner._merge_todo_body(CURRENT_FULL, {"no-starts-on": True})["starts_on"] is None


def test_merge_adds_notify_only_when_asked() -> None:
    assert "notify" not in Runner._merge_todo_body(CURRENT_FULL, {})
    assert Runner._merge_todo_body(CURRENT_FULL, {"notify": True})["notify"] is True


def test_merge_accepts_assignees_as_a_list_or_csv() -> None:
    assert Runner._merge_todo_body(CURRENT_FULL, {"assignee": [1, 2]})["assignee_ids"] == [1, 2]
    assert Runner._merge_todo_body(CURRENT_FULL, {"to": "3, 4"})["assignee_ids"] == [3, 4]


def test_merge_cannot_currently_unassign_everyone() -> None:
    """Known limitation, pinned so it's visible rather than surprising.

    The lookup is `params.get("assignee") or params.get("to")`, so an empty list
    is falsy and falls through to "not specified" — the current assignees are
    carried over instead of being cleared. There is no way to unassign everyone
    through this path today; it would need an explicit `no-assignee` flag.
    """
    assert Runner._merge_todo_body(CURRENT_FULL, {"assignee": []})["assignee_ids"] == [11, 22]


def test_merge_falls_back_to_title_when_content_is_absent() -> None:
    body = Runner._merge_todo_body({"title": "From title"}, {})
    assert body["content"] == "From title"


def test_merge_defaults_missing_fields() -> None:
    body = Runner._merge_todo_body({}, {})
    assert body == {
        "content": "",
        "description": "",
        "due_on": None,
        "starts_on": None,
        "assignee_ids": [],
        "completion_subscriber_ids": [],
    }


def test_merge_skips_assignees_without_ids() -> None:
    body = Runner._merge_todo_body({"assignees": [{"id": 5}, {"name": "no id"}]}, {})
    assert body["assignee_ids"] == [5]


def test_todos_update_rejects_a_non_dict_get_response() -> None:
    runner = FakeRunner(["not a dict"])
    with pytest.raises(BasecampError, match="Unexpected response fetching todo"):
        runner.call(UPDATE_SPEC, {"id": "1", "project": "2"})


def test_optional_positional_is_skipped_when_absent() -> None:
    spec = {
        "group": "cards",
        "action": "list",
        "positional": [
            {"name": "column", "required": False, "description": "Column"},
            {"name": "filter", "required": False, "description": "Filter"},
        ],
        "flags": [],
    }
    assert Runner().build_argv(spec, {"filter": "open"}) == [
        "cards",
        "list",
        "open",
        "--json",
    ]
