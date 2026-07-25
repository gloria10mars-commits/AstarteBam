#!/usr/bin/env python3
"""Text file summary module."""

import os
import sys


def handle(args, cwd, stdin_data=""):
    """Summarize text file: word count, line count, char count, preview. Args = file path."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: resume_texte <filepath>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    try:
        with open(fpath, "r", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return {"ok": False, "error": "Cannot read file: {}".format(str(e))}

    char_count = len(content)
    lines = content.split("\n")
    line_count = len(lines)
    word_count = len(content.split())
    non_empty_lines = sum(1 for l in lines if l.strip())

    # First 500 chars
    first_500 = content[:500]
    if len(content) > 500:
        first_500 += "\n... (truncated)"

    # Last 500 chars
    last_500 = ""
    if len(content) > 500:
        last_500 = content[-500:]
        last_500 = "\n... (truncated)\n" + last_500
    else:
        last_500 = "(file too short for last 500 chars preview)"

    msg_lines = [
        "=== Text Summary ===",
        "File: {}".format(fpath),
        "",
        "[STATISTICS]",
        "  Characters:      {}".format(char_count),
        "  Words:           {}".format(word_count),
        "  Lines:           {}".format(line_count),
        "  Non-empty lines: {}".format(non_empty_lines),
        "",
        "[FIRST 500 CHARS]",
        first_500,
        "",
        "[LAST 500 CHARS]",
        last_500,
    ]

    return {
        "ok": True,
        "msg": "\n".join(msg_lines),
        "file": fpath,
        "char_count": char_count,
        "word_count": word_count,
        "line_count": line_count,
        "non_empty_lines": non_empty_lines,
    }


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))