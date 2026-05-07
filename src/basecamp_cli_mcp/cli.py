from __future__ import annotations

import argparse
import asyncio
import json
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="basecamp-cli-mcp",
        description="MCP server that wraps the basecamp CLI.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        metavar="PATTERN",
        help=(
            "Only expose tools whose name matches PATTERN (fnmatch glob). "
            "Repeatable. Example: --include 'cards_*' --include 'todos_*'."
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="PATTERN",
        help="Hide tools whose name matches PATTERN. Repeatable. Applied after --include.",
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Regenerate data/tools.json from the basecamp CLI.")
    gen.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write tools.json (default: in-tree data/tools.json next to this package).",
    )

    sub.add_parser(
        "setup",
        help="Install the basecamp CLI (if missing) and run `basecamp setup` to authenticate.",
    )

    args = parser.parse_args(argv)

    if args.command == "generate":
        return _generate(args.output)

    if args.command == "setup":
        from .setup_cmd import run as run_setup

        return run_setup()

    from . import server

    asyncio.run(server.run(include=args.include, exclude=args.exclude))
    return 0


def _generate(output: Path | None) -> int:
    from .generator import Generator

    tools = Generator().generate()
    if output is None:
        output = Path(str(files("basecamp_cli_mcp") / "data" / "tools.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(tools, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(tools)} tools to {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
