# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MCP (Model Context Protocol) server that wraps the `basecamp` CLI. Each non-shortcut CLI action (`projects list`, `todos create`, etc.) is exposed as one MCP tool. Python ≥ 3.11; stdio transport. Distributed as a PyPI package; recommended invocation is `uvx basecamp-cli-mcp` so MCP clients (Claude Desktop in particular) don't need any environment setup.

Requires the `basecamp` CLI on `PATH`, already authenticated via `basecamp setup`. Override the binary with `BASECAMP_BIN`.

## Commands

```sh
uv sync                                # install deps into .venv
uv run pytest                          # all tests
uv run pytest tests/test_runner.py     # single file
uv run pytest -k pattern               # filter
uv run basecamp-cli-mcp generate       # regenerate src/basecamp_cli_mcp/data/tools.json
uv run basecamp-cli-mcp                # run the stdio MCP server
uv build                               # wheel + sdist into dist/
```

## Architecture

Two distinct phases — don't conflate them:

1. **Offline schema generation** (`src/basecamp_cli_mcp/generator.py` + `help_parser.py`, driven by `basecamp-cli-mcp generate`). Shells out to `basecamp commands --json`, then `basecamp <group> <action> --help` for each action, parses the help text, and writes `data/tools.json`. `Shortcuts` category is skipped — its actions (`todo`, `done`, `card`, `comment`) duplicate real actions already exposed.

2. **Runtime** (`src/basecamp_cli_mcp/server.py` + `runner.py`, entry `src/basecamp_cli_mcp/cli.py`). Loads `data/tools.json` via `importlib.resources` (does not re-introspect the CLI), registers one MCP tool per entry. Each invocation: `Runner.build_argv` assembles `basecamp <group> <action> <positional...> <flags...> --json`, shells out via `subprocess.run`, parses the `{ok, data}` envelope, returns `data` (or raises `BasecampError` on `ok:false` / non-zero exit).

`data/tools.json` is the contract between the two phases — it is **committed** and shipped as package data inside the wheel. After upgrading the `basecamp` CLI, regenerate it, review the diff, commit.

### Flag/arg conventions (in tool specs)

- Positional args: `{name, required, description}` — missing required raises `ValueError`.
- Flags: `{name, short, type, description}` where `type` ∈ `boolean` (bare `--flag` when truthy), `array` (repeated `--flag value`), `integer`, `string`.
- `help_parser` maps CLI type hints: `stringArray` → array, `int` → integer, bare flag → boolean. `--help` is dropped.
