#!/usr/bin/env python3
"""Shell execution module - run arbitrary shell commands."""

import os
import sys
import subprocess


def handle(args, cwd, stdin_data=""):
    """Execute a shell command from args. Returns stdout+stderr."""
    if not args or not args.strip():
        return {"ok": False, "error": "No command provided."}

    cmd = args.strip()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            input=stdin_data or None
        )
        stdout = proc.stdout.rstrip("\n")
        stderr = proc.stderr.rstrip("\n")
        combined = ""
        if stdout:
            combined += stdout
        if stderr:
            if combined:
                combined += "\n"
            combined += stderr

        return {
            "ok": proc.returncode == 0,
            "msg": combined or "(no output)",
            "stdout": stdout,
            "stderr": stderr,
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", out))