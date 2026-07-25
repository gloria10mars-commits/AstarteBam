#!/usr/bin/env python3
"""Autopep8 formatting module."""

import os
import sys
import subprocess


def handle(args, cwd, stdin_data=""):
    """Format Python file with autopep8. Args = file path."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: autopep8_mod <filepath>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    try:
        result = subprocess.run(
            ["autopep8", "--in-place", fpath],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return {
                "ok": True,
                "msg": "Formatted with autopep8: {}".format(fpath),
                "file": fpath,
                "stderr": result.stderr.strip(),
            }
        else:
            return {
                "ok": False,
                "error": "autopep8 failed (code {}): {}".format(result.returncode, result.stderr.strip()),
                "file": fpath,
            }
    except FileNotFoundError:
        return {"ok": False, "error": "autopep8 not found in PATH. Install with: pip install autopep8"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "autopep8 timed out (30s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", out.get("error", str(out))))