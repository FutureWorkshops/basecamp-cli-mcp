# basecamp-cli-mcp

A Model Context Protocol (MCP) server that wraps the [`basecamp`](https://github.com/basecamp/cli)
CLI. Every non-shortcut CLI action (`projects list`, `todos create`, `cards update`, etc.) is
exposed as an MCP tool, so MCP-compatible clients (Claude Code, Claude Desktop, etc.) can
drive Basecamp directly.

## Requirements

- Ruby 4.0.x (see `.ruby-version`)
- The `basecamp` CLI on `PATH`, already authenticated (`basecamp setup`)

## Install

```sh
bundle install
```

## Run

```sh
bin/basecamp-mcp
```

This starts a stdio MCP server that reads JSON-RPC on stdin and writes on stdout.

### Add to Claude Code

```sh
claude mcp add basecamp -- /absolute/path/to/basecamp-cli-mcp/bin/basecamp-mcp
```

### Add to Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "basecamp": {
      "command": "/absolute/path/to/basecamp-cli-mcp/bin/basecamp-mcp"
    }
  }
}
```

## How it works

Tool schemas are pre-generated and committed to `data/tools.json`. At runtime the server
loads that file and registers one MCP tool per entry. Each tool:

1. Builds `argv` from positional arguments and flags defined in the schema.
2. Shells out: `basecamp <group> <action> <args...> --json`.
3. Returns the parsed `data` field from the CLI's `{ok, data}` envelope to the MCP client.

Shortcut commands (`todo`, `done`, `card`, `comment`, etc.) are intentionally excluded — their
underlying actions (`todos_create`, `cards_create`, …) are already exposed.

## Regenerating tool schemas

After upgrading the `basecamp` CLI, regenerate `data/tools.json`:

```sh
bundle exec rake tools:generate
```

Review the diff and commit. The generator reads `basecamp commands --json` and parses
`basecamp <group> <action> --help` for each action.

## Development

```sh
bundle exec rake test        # run tests
bundle exec rake             # default task (tests)
```

Layout:

- `lib/basecamp_mcp/server.rb` — wires up `MCP::Server` from `data/tools.json`
- `lib/basecamp_mcp/runner.rb` — builds argv and shells out
- `lib/basecamp_mcp/generator.rb` — regenerates `data/tools.json`
- `lib/basecamp_mcp/help_parser.rb` — parses `--help` text into a schema
- `data/tools.json` — generated tool schemas (committed)
