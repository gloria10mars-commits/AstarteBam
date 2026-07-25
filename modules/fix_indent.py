#!/usr/bin/env python3
"""Fix indentation with autopep8 --in-place."""

import os
import sys
import subprocess


def handle(args, cwd, stdin_data=""):
    """Fix indentation using autopep8 --in-place. Args = file path."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: fix_indent <filepath>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    try:
        result = subprocess.run(
            ["autopep8", "--in-place", "--select=E1,W1,W3,W5,W6", fpath],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return {
                "ok": True,
                "msg": "Indentation fixed: {}".format(fpath),
                "file": fpath,
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