#!/usr/bin/env python3
"""Git status / public IP info module."""

import os
import sys
import subprocess


def handle(args, cwd, stdin_data=""):
    """If args empty or 'git': git status. Otherwise: public IP info from ip-api.com."""
    args = args.strip()

    if not args or args.lower() == "git":
        return _git_status(cwd)
    else:
        return _public_ip_info(args)


def _git_status(cwd):
    """Run git status in cwd."""
    try:
        result = subprocess.run(
            ["git", "status"],
            capture_output=True, text=True, cwd=cwd
        )
        output = result.stdout
        if result.stderr and result.returncode != 0:
            output += "\n" + result.stderr

        if result.returncode != 0 and "not a git repository" in output.lower():
            return {"ok": False, "error": "Not a git repository: {}".format(cwd)}

        # Also get branch info
        branch_info = ""
        try:
            br = subprocess.run(
                ["git", "branch", "-a"],
                capture_output=True, text=True, cwd=cwd
            )
            if br.returncode == 0 and br.stdout.strip():
                branch_info = "\n[BRANCHES]\n" + br.stdout.strip()
        except Exception:
            pass

        msg = "[GIT STATUS]\n{}\n{}".format(output.strip(), branch_info)
        return {"ok": True, "msg": msg, "status": output.strip()}
    except FileNotFoundError:
        return {"ok": False, "error": "git not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "git timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _public_ip_info(args):
    """Fetch public IP info from ip-api.com."""
    try:
        import urllib.request
        url = "http://ip-api.com/json/?fields=status,message,query,city,region,country,countryCode,isp,org,lat,lon,timezone,zip"
        req = urllib.request.Request(url, headers={"User-Agent": "AstarteBam/5.0"})
        resp = urllib.request.urlopen(req)
        data = resp.read().decode()
        import json
        info = json.loads(data)

        if info.get("status") != "success":
            return {"ok": False, "error": "ip-api error: {}".format(info.get("message", "unknown"))}

        lines = [
            "=== Public IP Info ===",
            "IP:       {}".format(info.get("query", "?")),
            "City:     {}".format(info.get("city", "?")),
            "Region:   {}".format(info.get("region", "?")),
            "Country:  {} ({})".format(info.get("country", "?"), info.get("countryCode", "?")),
            "ZIP:      {}".format(info.get("zip", "?")),
            "ISP:      {}".format(info.get("isp", "?")),
            "Org:      {}".format(info.get("org", "?")),
            "Timezone: {}".format(info.get("timezone", "?")),
            "Geo:      ({}, {})".format(info.get("lat", "?"), info.get("lon", "?")),
        ]

        return {"ok": True, "msg": "\n".join(lines), "data": info}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", str(out)))