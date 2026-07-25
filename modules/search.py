#!/usr/bin/env python3
"""
Module search — Recherche rapide d'expression dans les fichiers
Supporte la recherche recursive dans un dossier.
Compatible Python 3.6+ / pure Python
"""
import os
import re


def handle(args, cwd, stdin_data):
    """
    args: "expression [chemin_dossier]"
    Recherche une expression dans tous les fichiers d'un dossier.
    Si aucun chemin n'est donne, cherche dans le cwd.
    """
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: search <expression> [path]"}

    parts = args.strip().split(None, 1)
    expression = parts[0]
    search_path = parts[1] if len(parts) > 1 else "."

    target = os.path.join(cwd, search_path) if not os.path.isabs(search_path) else search_path

    if not os.path.isdir(target):
        return {"ok": False, "error": "Not a directory: {}".format(search_path)}

    try:
        pattern = re.compile(expression, re.IGNORECASE)
    except re.error as e:
        return {"ok": False, "error": "Invalid regex: {}".format(str(e))}

    results = []
    max_results = 100
    max_file_size = 1048576  # 1MB max par fichier

    try:
        for root, dirs, files in os.walk(target):
            for fname in files:
                if len(results) >= max_results:
                    break
                fpath = os.path.join(root, fname)
                try:
                    fsize = os.path.getsize(fpath)
                    if fsize > max_file_size:
                        continue
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern.search(line):
                                rel = os.path.relpath(fpath, target)
                                results.append({
                                    "file": rel,
                                    "line": line_num,
                                    "match": line.strip()[:200]
                                })
                                if len(results) >= max_results:
                                    break
                except (OSError, IOError):
                    continue
            if len(results) >= max_results:
                break
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "expression": expression,
        "path": search_path,
        "matches": len(results),
        "max_reached": len(results) >= max_results,
        "results": results
    }