#!/usr/bin/env python3
"""SVG to JPG converter using cairosvg."""

import os
import sys


def handle(args, cwd, stdin_data=""):
    """Convert SVG to JPG using cairosvg. Args = SVG file path."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: svg_jpg <filepath.svg>"}

    filepath = args.strip()
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(filepath)}

    if not fpath.lower().endswith(".svg"):
        return {"ok": False, "error": "File is not an SVG: {}".format(filepath)}

    # Try cairosvg
    try:
        import cairosvg
    except ImportError:
        return {"ok": False, "error": "cairosvg not installed. Install: pip install cairosvg"}

    out_path = os.path.splitext(fpath)[0] + ".jpg"

    try:
        cairosvg.svg2jpg(url=fpath, write_to=out_path)
        out_size = os.path.getsize(out_path)
        return {
            "ok": True,
            "msg": "Converted SVG to JPG: {}".format(out_path),
            "input": fpath,
            "output": out_path,
            "output_size": out_size,
        }
    except Exception as e:
        return {"ok": False, "error": "Conversion failed: {}".format(str(e))}


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", out.get("error", str(out))))