#!/usr/bin/env python3
"""Detailed Python syntax checker with line numbers and error types."""

import os
import sys
import py_compile
import re


def handle(args, cwd, stdin_data=""):
    """Check Python file syntax with detailed error info. Args = file path."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: check_syntax <filepath>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    # Read file info
    try:
        with open(fpath, "r") as f:
            source = f.read()
        total_lines = source.count("\n") + 1
    except Exception as e:
        return {"ok": False, "error": "Cannot read file: {}".format(str(e))}

    # Try to compile
    try:
        py_compile.compile(fpath, doraise=True)
        msg_lines = [
            "Syntax Check: PASSED",
            "File: {}".format(fpath),
            "Lines: {}".format(total_lines),
            "Size: {} bytes".format(len(source)),
        ]
        return {
            "ok": True,
            "msg": "\n".join(msg_lines),
            "file": fpath,
            "lines": total_lines,
            "size": len(source),
            "syntax_ok": True,
        }
    except py_compile.PyCompileError as e:
        error_str = str(e)
        # Extract line number and error type
        line_num = "?"
        error_type = "SyntaxError"
        error_detail = ""

        # Pattern: File "path", line N
        m = re.search(r'line\s+(\d+)', error_str)
        if m:
            line_num = int(m.group(1))

        # Try to extract error type (e.g., SyntaxError, IndentationError)
        m2 = re.search(r'(\w+Error)', error_str)
        if m2:
            error_type = m2.group(1)

        # Get the specific line content
        line_content = ""
        if line_num != "?" and isinstance(line_num, int):
            try:
                lines = source.split("\n")
                if 1 <= line_num <= len(lines):
                    line_content = lines[line_num - 1]
            except Exception:
                pass

        msg_lines = [
            "Syntax Check: FAILED",
            "File: {}".format(fpath),
            "Error Type: {}".format(error_type),
            "Line: {}".format(line_num),
            "",
        ]
        if line_content:
            msg_lines.append("Code at line {}:".format(line_num))
            msg_lines.append("  {}".format(line_content))
            msg_lines.append("")
        msg_lines.append("Detail:")
        msg_lines.append("  {}".format(error_str))

        return {
            "ok": False,
            "msg": "\n".join(msg_lines),
            "file": fpath,
            "lines": total_lines,
            "error_type": error_type,
            "line": line_num,
            "line_content": line_content,
            "detail": error_str,
            "syntax_ok": False,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": "Unexpected error: {}".format(str(e)),
            "file": fpath,
            "syntax_ok": False,
        }


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", out.get("error", str(out))))