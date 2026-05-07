# basecamp-cli-mcp

A Model Context Protocol (MCP) server that wraps the [`basecamp`](https://github.com/basecamp/cli)
CLI. Every non-shortcut CLI action (`projects list`, `todos create`, `cards update`, etc.) is
exposed as an MCP tool, so MCP-compatible clients (Claude Code, Claude Desktop, etc.) can
drive Basecamp directly.

## Requirements

- Python ≥ 3.11
- The `basecamp` CLI on `PATH`, already authenticated (`basecamp setup`) — see [First-time setup](#first-time-setup) below to do both in one command
- [`uv`](https://docs.astral.sh/uv/) for the recommended install

## First-time setup

If you don't have the `basecamp` CLI installed yet:

```sh
uvx basecamp-cli-mcp setup
```

This checks for the `basecamp` binary, runs the official installer (`curl -fsSL https://basecamp.com/install-cli | bash`) after a y/N prompt if it's missing, then runs `basecamp setup` to walk you through OAuth.

On macOS, after auth completes it offers to:

1. Add `basecamp` to your `claude_desktop_config.json` (with a timestamped backup of any existing file).
2. Restart Claude Desktop.

Both steps prompt y/N. macOS and Linux only for the install/auth — on Windows the command prints the PowerShell installer and exits. The Claude Desktop step is macOS-only.

## Run

The fastest way — no install step at all:

```sh
uvx basecamp-cli-mcp
```

`uvx` resolves the package, runs it in an ephemeral isolated env, and exec's it on stdin/stdout.

To install permanently:

```sh
uv tool install basecamp-cli-mcp
basecamp-cli-mcp
```

### Add to Claude Code

```sh
claude mcp add basecamp -- uvx basecamp-cli-mcp
```

### Add to Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "basecamp": {
      "command": "uvx",
      "args": ["basecamp-cli-mcp"]
    }
  }
}
```

If `uvx` isn't on Desktop's `PATH` (it strips most of your shell `PATH`), use the absolute path — `which uvx` from your shell.

### Filtering tools

By default the server exposes all 250+ tools. Most agents only need a handful, and a smaller
catalog speeds up tool selection. Filter with `--include` / `--exclude` (fnmatch globs against
tool names; both flags repeatable):

```sh
basecamp-cli-mcp --include 'cards_*' --include 'todos_*'
basecamp-cli-mcp --include '*' --exclude 'webhooks_*' --exclude 'templates_*'
```

Register multiple profiles in `claude_desktop_config.json` and turn them on per task:

```json
{
  "mcpServers": {
    "basecamp-cards": {
      "command": "uvx",
      "args": ["basecamp-cli-mcp", "--include", "cards_*", "--include", "projects_list"]
    },
    "basecamp-todos": {
      "command": "uvx",
      "args": ["basecamp-cli-mcp", "--include", "todos_*", "--include", "projects_list"]
    },
    "basecamp-full": {
      "command": "uvx",
      "args": ["basecamp-cli-mcp"]
    }
  }
}
```

### `BASECAMP_BIN`

If the `basecamp` CLI isn't on the spawned process's `PATH` (a real risk under Claude Desktop), set:

```json
"env": { "BASECAMP_BIN": "/absolute/path/to/basecamp" }
```

## How it works

Tool schemas are pre-generated and committed to `src/basecamp_cli_mcp/data/tools.json` (shipped
inside the wheel as package data). At runtime the server loads that file and registers one MCP
tool per entry. Each tool:

1. Builds `argv` from positional arguments and flags defined in the schema.
2. Shells out: `basecamp <group> <action> <args...> --json`.
3. Returns the parsed `data` field from the CLI's `{ok, data}` envelope to the MCP client.

Shortcut commands (`todo`, `done`, `card`, `comment`, etc.) are intentionally excluded — their
underlying actions (`todos_create`, `cards_create`, …) are already exposed.

## Regenerating tool schemas

After upgrading the `basecamp` CLI:

```sh
uv run basecamp-cli-mcp generate
```

Review the diff in `src/basecamp_cli_mcp/data/tools.json` and commit. The generator reads
`basecamp commands --json` and parses `basecamp <group> <action> --help` for each action.

## Development

```sh
uv sync
uv run pytest
uv build                       # wheel + sdist into dist/
```

Layout:

- `src/basecamp_cli_mcp/server.py` — wires up the MCP server from `data/tools.json`
- `src/basecamp_cli_mcp/runner.py` — builds argv and shells out
- `src/basecamp_cli_mcp/generator.py` — regenerates `data/tools.json`
- `src/basecamp_cli_mcp/help_parser.py` — parses `--help` text into a schema
- `src/basecamp_cli_mcp/cli.py` — entrypoint (`basecamp-cli-mcp`)
- `src/basecamp_cli_mcp/data/tools.json` — generated tool schemas (committed)
