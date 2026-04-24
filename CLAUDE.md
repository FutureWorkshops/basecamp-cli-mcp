# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MCP (Model Context Protocol) server that wraps the `basecamp` CLI. Each non-shortcut CLI action (`projects list`, `todos create`, etc.) is exposed as one MCP tool. Ruby 4.0.x; stdio transport.

Requires the `basecamp` CLI on `PATH`, already authenticated via `basecamp setup`. Override the binary with `BASECAMP_BIN`.

## Commands

```sh
bundle install
bundle exec rake test                                  # all tests
bundle exec rake test TEST=test/runner_test.rb        # single file
bundle exec ruby -Ilib -Itest test/runner_test.rb -n /pattern/  # single test
bundle exec rake tools:generate                        # regenerate data/tools.json
bin/basecamp-mcp                                       # run the stdio MCP server
```

## Architecture

Two distinct phases — don't conflate them:

1. **Offline schema generation** (`lib/basecamp_mcp/generator.rb` + `help_parser.rb`, driven by `rake tools:generate`). Shells out to `basecamp commands --json`, then `basecamp <group> <action> --help` for each action, parses the help text, and writes `data/tools.json`. `Shortcuts` category is skipped — its actions (`todo`, `done`, `card`, `comment`) duplicate real actions already exposed.

2. **Runtime** (`lib/basecamp_mcp/server.rb` + `runner.rb`, entry `bin/basecamp-mcp`). Loads `data/tools.json` (does not re-introspect the CLI), registers one `MCP::Tool` per entry. Each invocation: `Runner#build_argv` assembles `basecamp <group> <action> <positional...> <flags...> --json`, shells out via `Open3`, parses the `{ok, data}` envelope, returns `data` (or raises `BasecampError` on `ok:false` / non-zero exit).

`data/tools.json` is the contract between the two phases — it is **committed**. After upgrading the `basecamp` CLI, regenerate it, review the diff, commit.

### Flag/arg conventions (in tool specs)

- Positional args: `{name, required, description}` — missing required raises `ArgumentError`.
- Flags: `{name, short, type, description}` where `type` ∈ `boolean` (bare `--flag` when truthy), `array` (repeated `--flag value`), `integer`, `string`.
- `HelpParser` maps CLI type hints: `stringArray` → array, `int` → integer, bare flag → boolean. `--help` is dropped.
