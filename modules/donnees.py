#!/usr/bin/env python3
"""Data reader module - parse JSON and CSV files."""

import os
import sys
import json
import csv


def handle(args, cwd, stdin_data=""):
    """Read JSON or CSV files. Args: 'json filepath' or 'csv filepath'."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: donnees json <filepath> | donnees csv <filepath>"}

    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return {"ok": False, "error": "Usage: donnees json <filepath> | donnees csv <filepath>"}

    fmt = parts[0].lower()
    filepath = parts[1]
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    if fmt == "json":
        return _read_json(fpath)
    elif fmt == "csv":
        return _read_csv(fpath)
    else:
        # Auto-detect by extension
        ext = os.path.splitext(fpath)[1].lower()
        if ext == ".json":
            return _read_json(fpath)
        elif ext == ".csv":
            return _read_csv(fpath)
        else:
            return {"ok": False, "error": "Unknown format '{}'. Use 'json' or 'csv'.".format(fmt)}


def _read_json(fpath):
    """Parse JSON file."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        pretty = json.dumps(data, indent=2, ensure_ascii=False)

        # Basic stats
        if isinstance(data, list):
            stats = "Array with {} items".format(len(data))
        elif isinstance(data, dict):
            stats = "Object with {} keys: {}".format(len(data), ", ".join(list(data.keys())[:10]))
        else:
            stats = "Type: {}".format(type(data).__name__)

        msg = "=== JSON Data ===\nFile: {}\n{}\n\n{}".format(fpath, stats, pretty)
        return {"ok": True, "msg": msg, "data": data, "stats": stats}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": "Invalid JSON: {}".format(str(e))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _read_csv(fpath):
    """Parse CSV file."""
    try:
        with open(fpath, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return {"ok": True, "msg": "CSV file is empty: {}".format(fpath), "rows": 0, "data": []}

        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        # Format preview
        lines = ["=== CSV Data ===", "File: {}".format(fpath), ""]
        lines.append("Columns ({}): {}".format(len(headers), ", ".join(headers)))
        lines.append("Data rows: {}".format(len(data_rows)))
        lines.append("")

        # Show preview table
        col_widths = []
        for i in range(len(headers)):
            max_w = len(headers[i])
            for row in data_rows[:20]:
                if i < len(row):
                    max_w = max(max_w, len(row[i]))
            col_widths.append(min(max_w, 40))

        # Header row
        header_strs = []
        for i, h in enumerate(headers):
            w = col_widths[i] if i < len(col_widths) else 20
            header_strs.append(h[:w].ljust(w))
        lines.append("  " + " | ".join(header_strs))
        lines.append("  " + "-+-".join("-" * (col_widths[i] if i < len(col_widths) else 20) for i in range(len(headers))))

        for row in data_rows[:20]:
            row_strs = []
            for i, cell in enumerate(row):
                w = col_widths[i] if i < len(col_widths) else 20
                row_strs.append(cell[:w].ljust(w))
            lines.append("  " + " | ".join(row_strs))

        if len(data_rows) > 20:
            lines.append("  ... and {} more rows".format(len(data_rows) - 20))

        return {
            "ok": True,
            "msg": "\n".join(lines),
            "headers": headers,
            "row_count": len(data_rows),
            "data": data_rows,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))