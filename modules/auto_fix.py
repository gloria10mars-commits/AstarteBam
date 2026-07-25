#!/usr/bin/env python3
"""Auto-fix module - try autopep8 formatting then check syntax."""

import os
import sys
import subprocess
import py_compile


def handle(args, cwd, stdin_data=""):
    """Try to fix Python file: autopep8 formatting then syntax check. Args = file path."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: auto_fix <filepath>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    # Step 1: Try autopep8
    autopep8_ok = False
    autopep8_msg = ""
    try:
        result = subprocess.run(
            ["autopep8", "--in-place", "--aggressive", fpath],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            autopep8_ok = True
            autopep8_msg = "autopep8 formatting applied successfully."
        else:
            autopep8_msg = "autopep8 returned code {}: {}".format(result.returncode, result.stderr.strip())
    except FileNotFoundError:
        autopep8_msg = "autopep8 not found in PATH. Skipping formatting."
    except subprocess.TimeoutExpired:
        autopep8_msg = "autopep8 timed out."
    except Exception as e:
        autopep8_msg = "autopep8 error: {}".format(str(e))

    # Step 2: Check syntax
    syntax_ok = False
    syntax_msg = ""
    try:
        py_compile.compile(fpath, doraise=True)
        syntax_ok = True
        syntax_msg = "Syntax OK."
    except py_compile.PyCompileError as e:
        syntax_msg = "Syntax error: {}".format(str(e))
    except Exception as e:
        syntax_msg = "Compile error: {}".format(str(e))

    lines = [
        "=== Auto-Fix Report ===",
        "File: {}".format(fpath),
        "",
        "[1] autopep8: {}".format("OK" if autopep8_ok else "SKIPPED"),
        "  {}".format(autopep8_msg),
        "",
        "[2] Syntax: {}".format("PASS" if syntax_ok else "FAIL"),
        "  {}".format(syntax_msg),
        "",
        "Result: {}".format("SUCCESS" if (syntax_ok) else "NEEDS ATTENTION"),
    ]

    return {
        "ok": syntax_ok,
        "msg": "\n".join(lines),
        "file": fpath,
        "autopep8_ok": autopep8_ok,
        "syntax_ok": syntax_ok,
    }


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", out.get("error", str(out))))