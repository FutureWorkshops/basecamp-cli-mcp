"""Parse `basecamp <group> <action> --help` output into a structured schema.

Used only by the generator — not on the runtime hot path.
"""

from __future__ import annotations

import re
from typing import TypedDict


class Positional(TypedDict):
    name: str
    required: bool
    description: str


class Flag(TypedDict, total=False):
    name: str
    short: str | None
    type: str
    description: str


class Parsed(TypedDict):
    summary: str
    positional: list[Positional]
    flags: list[Flag]


_REQUIRED_POS = re.compile(r"\A\s+<(\w[\w-]*)>\s+(.*)")
_OPTIONAL_POS = re.compile(r"\A\s+\[(\w[\w-]*)]\s+(.*)")
_FLAG_LINE = re.compile(r"\A\s+(?:-(\w),\s+)?--([\w-]+)(?:\s+(\S+))?\s{2,}(.*)")
_HEADER = re.compile(r"\A[A-Z][A-Z ]+\Z")


def parse(help_text: str) -> Parsed:
    return {
        "summary": _summary(help_text),
        "positional": _positional(help_text),
        "flags": _flags(help_text),
    }


def _summary(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if line.strip() == "USAGE":
            break
        if line.strip():
            lines.append(line.strip())
    return " ".join(lines)


def _positional(text: str) -> list[Positional]:
    section = _section(text, "ARGUMENTS")
    if section is None:
        return []
    out: list[Positional] = []
    for line in section.splitlines(keepends=True):
        m = _REQUIRED_POS.match(line)
        if m:
            out.append({"name": m.group(1), "required": True, "description": m.group(2).strip()})
            continue
        m = _OPTIONAL_POS.match(line)
        if m:
            out.append({"name": m.group(1), "required": False, "description": m.group(2).strip()})
    return out


def _flags(text: str) -> list[Flag]:
    section = _section(text, "FLAGS")
    if section is None:
        return []
    out: list[Flag] = []
    for line in section.splitlines(keepends=True):
        m = _FLAG_LINE.match(line)
        if not m:
            continue
        short, name, type_hint, desc = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        if name == "help":
            continue
        flag: Flag = {"name": name, "type": _map_type(type_hint), "description": desc}
        if short:
            flag["short"] = short
        out.append(flag)
    return out


def _map_type(hint: str | None) -> str:
    if hint is None:
        return "boolean"
    if hint == "stringArray":
        return "array"
    if hint == "int":
        return "integer"
    if hint == "bool":
        return "boolean"
    return "string"


def _section(text: str, name: str) -> str | None:
    """Return body of a top-level section like FLAGS / ARGUMENTS, up to the next header."""
    in_section = False
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not in_section:
            if stripped == name:
                in_section = True
            continue
        # Next top-level header (all-caps line at col 0) ends the section.
        if _HEADER.match(stripped) and line[:1].isalpha() and line[:1].isupper() and line == line.lstrip():
            break
        out.append(line)
    return "".join(out) if in_section else None
