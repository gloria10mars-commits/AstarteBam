#!/usr/bin/env python3
"""Web tools module - fetch URL, extract title and links."""

import os
import sys
import re


def handle(args, cwd, stdin_data=""):
    """Fetch a URL and extract title, link count, links list. Args = URL."""
    if not args or not args.strip():
        return {"ok": False, "error": "Usage: web_tools <url>"}

    url = args.strip()

    # Validate URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        from urllib.request import urlopen, Request
        from urllib.error import URLError
        req = Request(url, headers={"User-Agent": "AstarteBam/5.0"})
        resp = urlopen(req)
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read(500000)  # Read up to 500KB
        # Try to decode
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            html = raw.decode("latin-1")
    except Exception as e:
        return {"ok": False, "error": "Failed to fetch URL: {}".format(str(e))}

    # Extract title
    title = "N/A"
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if m:
        title = m.group(1).strip()

    # Extract meta description
    description = ""
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html, re.IGNORECASE)
    if m:
        description = m.group(1).strip()
    if not description:
        m = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', html, re.IGNORECASE)
        if m:
            description = m.group(1).strip()

    # Extract links
    links = []
    seen = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = m.group(1).strip()
        if href and href not in seen and not href.startswith(("#", "javascript:", "mailto:")):
            seen.add(href)
            links.append(href)

    # Stats
    html_size = len(html)
    tag_count = len(re.findall(r'<[a-zA-Z/]', html))

    lines = [
        "=== Web Analysis ===",
        "URL: {}".format(url),
        "Content-Type: {}".format(content_type),
        "",
        "[META]",
        "  Title: {}".format(title),
    ]
    if description:
        lines.append("  Description: {}".format(description[:200]))
    lines.append("")
    lines.append("[STATS]")
    lines.append("  HTML size: {} chars".format(html_size))
    lines.append("  Tags found: ~{}".format(tag_count))
    lines.append("  Links found: {}".format(len(links)))
    lines.append("")
    lines.append("[LINKS] (showing first 30)")
    for link in links[:30]:
        lines.append("  {}".format(link))
    if len(links) > 30:
        lines.append("  ... and {} more".format(len(links) - 30))

    return {
        "ok": True,
        "msg": "\n".join(lines),
        "url": url,
        "title": title,
        "description": description,
        "link_count": len(links),
        "links": links,
        "html_size": html_size,
    }


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))