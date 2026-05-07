from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

INSTALL_CMD = "curl -fsSL https://basecamp.com/install-cli | bash"
WINDOWS_INSTALL_CMD = (
    "irm https://raw.githubusercontent.com/basecamp/basecamp-cli/main/scripts/install.ps1 | iex"
)
INSTALL_DOCS_URL = "https://github.com/basecamp/basecamp-cli#installation"

CLAUDE_DESKTOP_CONFIG_MACOS = (
    Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
)


def _prompt(question: str) -> bool:
    try:
        answer = input(f"{question} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def _resolve_binary() -> str | None:
    override = os.environ.get("BASECAMP_BIN")
    if override:
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override
        # Fall through: an invalid BASECAMP_BIN is treated as "not installed".
    return shutil.which("basecamp")


def run() -> int:
    bin_path = _resolve_binary()

    if bin_path is None:
        if sys.platform == "win32":
            print("basecamp CLI not found.", file=sys.stderr)
            print("On Windows, install it with PowerShell:", file=sys.stderr)
            print(f"  {WINDOWS_INSTALL_CMD}", file=sys.stderr)
            print(f"Then re-run: basecamp-cli-mcp setup", file=sys.stderr)
            return 1

        print("basecamp CLI not found.")
        print(f"About to run: {INSTALL_CMD}")
        if not _prompt("Proceed?"):
            print("Aborted.", file=sys.stderr)
            return 1

        result = subprocess.run(["bash", "-c", INSTALL_CMD], check=False)
        if result.returncode != 0:
            print(
                f"Installer exited with status {result.returncode}. "
                f"See {INSTALL_DOCS_URL} for manual instructions.",
                file=sys.stderr,
            )
            return result.returncode

        bin_path = _resolve_binary()
        if bin_path is None:
            print(
                "Installer finished but `basecamp` is not on PATH — "
                "you may need to restart your shell, then re-run "
                "`basecamp-cli-mcp setup`.",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"Found basecamp at {bin_path}")

    # Run `basecamp setup` as a subprocess (inherits stdio) so OAuth works
    # and we can continue with Claude Desktop config afterwards.
    result = subprocess.run([bin_path, "setup"], check=False)
    if result.returncode != 0:
        return result.returncode

    _maybe_configure_claude_desktop()
    return 0


def _maybe_configure_claude_desktop() -> None:
    if sys.platform != "darwin":
        return

    print()
    if not _prompt("Configure Claude Desktop to use basecamp-cli-mcp?"):
        return

    config_path = CLAUDE_DESKTOP_CONFIG_MACOS
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        backup = config_path.with_suffix(
            config_path.suffix + f".backup.{int(time.time())}"
        )
        shutil.copy2(config_path, backup)
        print(f"Backed up existing config to {backup}")
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("top-level JSON is not an object")
        except (json.JSONDecodeError, ValueError) as e:
            print(
                f"Could not parse existing config ({e}). Aborting Claude Desktop setup; "
                f"your file is untouched (backup at {backup}).",
                file=sys.stderr,
            )
            return
    else:
        config = {}

    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        print(
            "Existing `mcpServers` entry is not an object — aborting Claude Desktop setup.",
            file=sys.stderr,
        )
        return

    # Claude Desktop strips most of the user's PATH, so resolve uvx absolutely
    # if we can. Fall back to bare "uvx" if it's not on our PATH.
    uvx = shutil.which("uvx") or "uvx"
    servers["basecamp"] = {"command": uvx, "args": ["basecamp-cli-mcp"]}

    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {config_path}")

    if _prompt("Restart Claude Desktop now?"):
        subprocess.run(
            ["osascript", "-e", 'tell application "Claude" to quit'],
            check=False,
        )
        # Give it a moment to actually exit before relaunching.
        time.sleep(1)
        subprocess.run(["open", "-a", "Claude"], check=False)
        print("Claude Desktop relaunching.")
