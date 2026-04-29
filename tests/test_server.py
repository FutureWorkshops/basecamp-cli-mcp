from basecamp_cli_mcp.server import filter_specs

SPECS = [
    {"name": "todos_create"},
    {"name": "todos_update"},
    {"name": "todos_complete"},
    {"name": "cards_create"},
    {"name": "cards_step_complete"},
    {"name": "cards_step_create"},
    {"name": "messages_create"},
]


def test_filter_include_glob() -> None:
    out = [s["name"] for s in filter_specs(SPECS, include=["cards_*"])]
    assert out == ["cards_create", "cards_step_complete", "cards_step_create"]


def test_filter_include_unions_multiple_patterns() -> None:
    out = [s["name"] for s in filter_specs(SPECS, include=["todos_*", "messages_*"])]
    assert out == ["todos_create", "todos_update", "todos_complete", "messages_create"]


def test_filter_exclude_subtracts_after_include() -> None:
    out = [
        s["name"]
        for s in filter_specs(SPECS, include=["cards_*"], exclude=["cards_step_*"])
    ]
    assert out == ["cards_create"]


def test_filter_exclude_only() -> None:
    out = [s["name"] for s in filter_specs(SPECS, exclude=["messages_*"])]
    assert "messages_create" not in out
    assert len(out) == 6


def test_filter_no_patterns_returns_all() -> None:
    assert filter_specs(SPECS) == SPECS
