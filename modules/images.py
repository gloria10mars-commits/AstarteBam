#!/usr/bin/env python3
"""Image file listing module."""

import os
import sys


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".ico"}


def handle(args, cwd, stdin_data=""):
    """List image files in a directory. Args = directory path."""
    target = args.strip() if args and args.strip() else "."

    dirpath = os.path.join(cwd, target) if not os.path.isabs(target) else target

    if not os.path.isdir(dirpath):
        return {"ok": False, "error": "Directory not found: {}".format(target)}

    images = []
    try:
        for entry in sorted(os.listdir(dirpath)):
            fpath = os.path.join(dirpath, entry)
            if os.path.isfile(fpath):
                _, ext = os.path.splitext(entry)
                if ext.lower() in IMAGE_EXTENSIONS:
                    size = os.path.getsize(fpath)
                    images.append({"name": entry, "size": size, "path": fpath})
    except PermissionError:
        return {"ok": False, "error": "Permission denied: {}".format(target)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if not images:
        return {"ok": True, "msg": "No image files found in: {}".format(target), "count": 0, "images": []}

    lines = ["Images in: {}".format(target), "({} found)".format(len(images)), ""]
    total_size = 0
    for img in images:
        total_size += img["size"]
        lines.append("  {}  ({} bytes)".format(img["name"], img["size"]))
    lines.append("")
    lines.append("Total: {} files, {} bytes ({:.2f} KB)".format(
        len(images), total_size, total_size / 1024.0))

    return {
        "ok": True,
        "msg": "\n".join(lines),
        "count": len(images),
        "total_size": total_size,
        "images": images,
    }


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))