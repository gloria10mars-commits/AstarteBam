#!/usr/bin/env python3
"""Media file listing module (video and audio)."""

import os
import sys


MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".flac",
    ".mp4", ".avi", ".mkv", ".mov", ".webm", ".m4a",
}


def handle(args, cwd, stdin_data=""):
    """List media files in a directory. Args = directory path."""
    target = args.strip() if args and args.strip() else "."

    dirpath = os.path.join(cwd, target) if not os.path.isabs(target) else target

    if not os.path.isdir(dirpath):
        return {"ok": False, "error": "Directory not found: {}".format(target)}

    media_files = []
    try:
        for entry in sorted(os.listdir(dirpath)):
            fpath = os.path.join(dirpath, entry)
            if os.path.isfile(fpath):
                _, ext = os.path.splitext(entry)
                if ext.lower() in MEDIA_EXTENSIONS:
                    size = os.path.getsize(fpath)
                    media_files.append({"name": entry, "ext": ext.lower(), "size": size, "path": fpath})
    except PermissionError:
        return {"ok": False, "error": "Permission denied: {}".format(target)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if not media_files:
        return {"ok": True, "msg": "No media files found in: {}".format(target), "count": 0, "files": []}

    lines = ["Media files in: {}".format(target), "({} found)".format(len(media_files)), ""]
    total_size = 0
    for mf in media_files:
        total_size += mf["size"]
        lines.append("  [{}] {}  ({} bytes)".format(mf["ext"], mf["name"], mf["size"]))
    lines.append("")
    lines.append("Total: {} files, {} bytes ({:.2f} MB)".format(
        len(media_files), total_size, total_size / (1024 * 1024.0)))

    return {
        "ok": True,
        "msg": "\n".join(lines),
        "count": len(media_files),
        "total_size": total_size,
        "files": media_files,
    }


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))