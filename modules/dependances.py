#!/usr/bin/env python3
"""Dependencies module - list installed pip packages."""

import os
import sys
import subprocess


def handle(args, cwd, stdin_data=""):
    """List installed pip packages. Optional args: package name to filter."""
    try:
        result = subprocess.run(
            ["pip3", "list"],
            capture_output=True, text=True
        )
        output = result.stdout
        if result.returncode != 0:
            # Fallback to pip
            result2 = subprocess.run(
                ["pip", "list"],
                capture_output=True, text=True
            )
            if result2.returncode == 0:
                output = result2.stdout
            else:
                return {"ok": False, "error": "pip3/pip list failed: {}".format(result.stderr.strip())}
    except FileNotFoundError:
        return {"ok": False, "error": "pip3 not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "pip list timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    lines = output.strip().split("\n")
    # Parse into list of dicts
    packages = []
    header_found = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("---"):
            header_found = True
            continue
        if header_found or (not header_found and lines[0].startswith("Package")):
            parts = stripped.split(None, 2)
            if len(parts) >= 2:
                packages.append({"name": parts[0], "version": parts[1]})

    # Filter if args provided
    filter_term = args.strip().lower()
    if filter_term:
        packages = [p for p in packages if filter_term in p["name"].lower()]

    count = len(packages)
    msg_lines = ["=== Installed Packages ({}) ===".format(count), ""]
    for p in packages:
        msg_lines.append("  {} ({})".format(p["name"], p["version"]))

    return {"ok": True, "msg": "\n".join(msg_lines), "count": count, "packages": packages}


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))