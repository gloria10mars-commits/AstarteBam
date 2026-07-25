#!/usr/bin/env python3
"""Python code syntax checker using py_compile."""

import os
import sys
import py_compile


def handle(args, cwd, stdin_data=""):
    """Check Python file syntax. Args = file path (relative to cwd)."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: analyse_code <filepath>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    try:
        py_compile.compile(fpath, doraise=True)
        return {"ok": True, "msg": "Syntax OK: {}".format(filepath), "file": filepath}
    except py_compile.PyCompileError as e:
        return {"ok": False, "error": str(e), "file": filepath}
    except Exception as e:
        return {"ok": False, "error": "Compilation error: {}".format(str(e)), "file": filepath}


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", out.get("error", str(out))))