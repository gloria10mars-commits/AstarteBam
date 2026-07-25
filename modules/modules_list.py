#!/usr/bin/env python3
"""Module listing - scan and display all available AstarteBam modules."""

import os
import sys


def handle(args, cwd, stdin_data=""):
    """List all modules in the modules directory with descriptions."""
    # Determine modules directory (same dir as this file)
    this_dir = os.path.dirname(os.path.abspath(__file__))
    if not this_dir:
        this_dir = cwd

    modules_dir = this_dir
    this_filename = os.path.basename(__file__)

    modules = []
    try:
        entries = sorted(os.listdir(modules_dir))
    except Exception as e:
        return {"ok": False, "error": "Cannot list modules directory: {}".format(str(e))}

    for entry in entries:
        if not entry.endswith(".py"):
            continue
        if entry in ("__init__.py", this_filename):
            continue

        fpath = os.path.join(modules_dir, entry)
        if not os.path.isfile(fpath):
            continue

        mod_name = os.path.splitext(entry)[0]
        description = ""

        # Try to read first line of docstring from source
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                source = f.read(2000)  # Read first 2KB for docstring

            # Find triple-quoted string at module level
            doc = _extract_docstring(source)
            if doc:
                # First line only
                first_line = doc.split("\n")[0].strip()
                if first_line:
                    description = first_line
        except Exception:
            pass

        if not description:
            description = "(no description)"

        modules.append({"name": mod_name, "file": entry, "description": description})

    # Filter by args if provided
    filter_term = args.strip().lower()
    if filter_term:
        modules = [m for m in modules if filter_term in m["name"].lower() or filter_term in m["description"].lower()]

    # Build message
    lines = [
        "=== AstarteBam Modules ({}) ===".format(len(modules)),
        "",
    ]
    for m in modules:
        lines.append("  {:<25s} {}".format(m["name"], m["description"]))
    lines.append("")
    lines.append("Total: {} modules".format(len(modules)))

    return {
        "ok": True,
        "msg": "\n".join(lines),
        "count": len(modules),
        "modules": modules,
    }


def _extract_docstring(source):
    """Extract module-level docstring from Python source."""
    # Look for triple-quoted string at the beginning
    stripped = source.lstrip()
    if stripped.startswith('"""'):
        end = stripped.find('"""', 3)
        if end >= 0:
            return stripped[3:end]
        # Multi-line: find closing
        end = stripped.find('"""', 3)
        if end > 0:
            return stripped[3:end]
    elif stripped.startswith("'''"):
        end = stripped.find("'''", 3)
        if end >= 0:
            return stripped[3:end]
        end = stripped.find("'''", 3)
        if end > 0:
            return stripped[3:end]
    return ""


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))