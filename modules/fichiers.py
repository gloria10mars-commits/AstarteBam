#!/usr/bin/env python3
"""File explorer module - list, stats, delete, export directory structure."""

import os
import sys
import json
import shutil


def _safe_path(base, path):
    """Ensure path is within base directory to prevent path traversal."""
    real_base = os.path.realpath(base)
    real_path = os.path.realpath(path)
    if not real_path.startswith(real_base + os.sep) and real_path != real_base:
        return False
    return True


def handle(args, cwd, stdin_data=""):
    """File explorer: list cwd/file/dir stats, delete, export JSON."""
    args = args.strip()

    if not args:
        return _list_dir(cwd, cwd)
    elif args.startswith("delete "):
        target = args[7:].strip()
        return _delete_path(target, cwd)
    elif args.startswith("export "):
        target = args[7:].strip()
        return _export_dir(target, cwd)
    else:
        target = os.path.join(cwd, args) if not os.path.isabs(args) else args
        if os.path.isfile(target):
            return _file_stats(target)
        elif os.path.isdir(target):
            return _list_dir(target, cwd)
        else:
            return {"ok": False, "error": "Path not found: {}".format(args)}


def _list_dir(target, cwd):
    """List directory contents."""
    try:
        entries = sorted(os.listdir(target))
        lines = ["[DIR] {}".format(target), ""]
        for e in entries:
            fpath = os.path.join(target, e)
            if os.path.isdir(fpath):
                lines.append("[DIR]  {}".format(e))
            elif os.path.isfile(fpath):
                size = os.path.getsize(fpath)
                lines.append("[FILE] {}  ({} bytes)".format(e, size))
            else:
                lines.append("[OTHER] {}".format(e))
        if not entries:
            lines.append("(empty directory)")
        return {"ok": True, "msg": "\n".join(lines), "path": target, "count": len(entries)}
    except PermissionError:
        return {"ok": False, "error": "Permission denied: {}".format(target)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _file_stats(fpath):
    """Show file statistics."""
    try:
        st = os.stat(fpath)
        size = st.st_size
        mtime = os.path.getmtime(fpath)
        import time
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        atime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_atime))
        mode = oct(st.st_mode)[-3:]
        lines = [
            "File: {}".format(fpath),
            "Size: {} bytes ({:.2f} KB)".format(size, size / 1024.0),
            "Modified: {}".format(mtime_str),
            "Accessed: {}".format(atime_str),
            "Mode: {}".format(mode),
        ]
        return {"ok": True, "msg": "\n".join(lines), "size": size, "modified": mtime_str}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _delete_path(target, cwd):
    """Delete a file or directory (path traversal protected)."""
    if not target:
        return {"ok": False, "error": "Usage: delete <path>"}
    fpath = os.path.join(cwd, target) if not os.path.isabs(target) else target
    if not _safe_path(cwd, fpath):
        return {"ok": False, "error": "Path traversal detected. Deletion blocked."}
    if not os.path.exists(fpath):
        return {"ok": False, "error": "Path not found: {}".format(target)}
    try:
        if os.path.isfile(fpath) or os.path.islink(fpath):
            os.remove(fpath)
        elif os.path.isdir(fpath):
            shutil.rmtree(fpath)
        return {"ok": True, "msg": "Deleted: {}".format(target), "deleted": target}
    except Exception as e:
        return {"ok": False, "error": "Delete failed: {}".format(str(e))}


def _export_dir(target, cwd):
    """Export directory structure as JSON."""
    if not target:
        target = "."
    fpath = os.path.join(cwd, target) if not os.path.isabs(target) else target
    if not os.path.isdir(fpath):
        return {"ok": False, "error": "Directory not found: {}".format(target)}

    def _build_tree(path):
        result = {"name": os.path.basename(path) or path, "type": "directory", "children": []}
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            result["children"] = ["[permission denied]"]
            return result
        for e in entries:
            full = os.path.join(path, e)
            if os.path.isdir(full):
                result["children"].append(_build_tree(full))
            elif os.path.isfile(full):
                result["children"].append({"name": e, "type": "file", "size": os.path.getsize(full)})
            else:
                result["children"].append({"name": e, "type": "other"})
        return result

    try:
        tree = _build_tree(fpath)
        json_str = json.dumps(tree, indent=2, ensure_ascii=False)
        return {"ok": True, "msg": json_str, "json": tree}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", out))