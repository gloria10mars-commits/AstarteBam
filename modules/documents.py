#!/usr/bin/env python3
"""Document/code analysis - count lines, functions, classes in Python files."""

import os
import sys
import ast
import re


def handle(args, cwd, stdin_data=""):
    """Analyze Python file: count lines, functions, classes. Args = file path."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: documents <filepath>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    try:
        with open(fpath, "r") as f:
            source = f.read()
    except Exception as e:
        return {"ok": False, "error": "Cannot read file: {}".format(str(e))}

    total_lines = len(source.split("\n"))
    non_empty_lines = sum(1 for line in source.split("\n") if line.strip())
    comment_lines = sum(1 for line in source.split("\n") if line.strip().startswith("#"))
    file_size = len(source)
    ext = os.path.splitext(fpath)[1].lower()

    # Python-specific analysis
    functions = []
    classes = []
    if ext == ".py":
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": len(node.args.args),
                    })
                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": sum(1 for n in node.body if isinstance(n, ast.FunctionDef)),
                    })
        except SyntaxError:
            # Fallback: regex
            functions = _regex_functions(source)
            classes = _regex_classes(source)

    # Imports
    imports = []
    if ext == ".py":
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                imports.append(stripped)

    lines = [
        "=== Document Analysis ===",
        "File: {}".format(fpath),
        "Type: {}".format(ext or "unknown"),
        "",
        "[STATISTICS]",
        "  Total lines:      {}".format(total_lines),
        "  Non-empty lines:  {}".format(non_empty_lines),
        "  Comment lines:    {}".format(comment_lines),
        "  File size:        {} bytes".format(file_size),
        "",
    ]

    if ext == ".py":
        lines.append("[FUNCTIONS] ({} found)".format(len(functions)))
        for fn in functions:
            lines.append("  {}() at line {} ({} args)".format(
                fn.get("name", fn), fn.get("line", "?"), fn.get("args", "?")))
        lines.append("")
        lines.append("[CLASSES] ({} found)".format(len(classes)))
        for cls in classes:
            lines.append("  {} at line {} ({} methods)".format(
                cls.get("name", cls), cls.get("line", "?"), cls.get("methods", 0)))
        lines.append("")
        lines.append("[IMPORTS] ({} found)".format(len(imports)))
        for imp in imports[:20]:
            lines.append("  {}".format(imp))
        if len(imports) > 20:
            lines.append("  ... and {} more".format(len(imports) - 20))

    return {
        "ok": True,
        "msg": "\n".join(lines),
        "file": fpath,
        "total_lines": total_lines,
        "non_empty_lines": non_empty_lines,
        "comment_lines": comment_lines,
        "functions": functions,
        "classes": classes,
        "imports": imports,
    }


def _regex_functions(source):
    """Fallback function extraction via regex."""
    results = []
    for i, line in enumerate(source.split("\n"), 1):
        m = re.match(r'^(\s*)def\s+(\w+)\s*\(', line)
        if m:
            results.append({"name": m.group(2), "line": i, "args": "?"})
    return results


def _regex_classes(source):
    """Fallback class extraction via regex."""
    results = []
    for i, line in enumerate(source.split("\n"), 1):
        m = re.match(r'^(\s*)class\s+(\w+)', line)
        if m:
            results.append({"name": m.group(2), "line": i, "methods": "?"})
    return results


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))