#!/usr/bin/env python3
"""Network information module - hostname, IPs, interfaces, gateway."""

import os
import sys
import subprocess
import socket


def handle(args, cwd, stdin_data=""):
    """Network info: hostname, local IP, public IP, all interfaces, gateway."""
    result = {"ok": True, "sections": {}}

    # --- Hostname ---
    hostname = socket.gethostname()
    result["sections"]["hostname"] = hostname

    # --- Local IP ---
    local_ip = "unknown"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    result["sections"]["local_ip"] = local_ip

    # --- Public IP ---
    public_ip = "unknown"
    public_info = {}
    try:
        import urllib.request
        url = "http://ip-api.com/json/?fields=status,message,query,city,region,country,countryCode,isp,lat,lon"
        req = urllib.request.Request(url, headers={"User-Agent": "AstarteBam/5.0"})
        resp = urllib.request.urlopen(req)
        data = resp.read().decode()
        import json
        info = json.loads(data)
        if info.get("status") == "success":
            public_ip = info.get("query", "unknown")
            public_info = {
                "ip": public_ip,
                "city": info.get("city", "?"),
                "region": info.get("region", "?"),
                "country": info.get("country", "?"),
                "country_code": info.get("countryCode", "?"),
                "isp": info.get("isp", "?"),
                "lat": info.get("lat", "?"),
                "lon": info.get("lon", "?"),
            }
    except Exception as e:
        public_info["error"] = str(e)
    result["sections"]["public_ip"] = public_ip
    result["sections"]["public_info"] = public_info

    # --- All interfaces ---
    ifaces = ""
    try:
        out = subprocess.check_output(["ip", "a"], stderr=subprocess.STDOUT).decode().strip()
        ifaces = out
    except Exception:
        try:
            out = subprocess.check_output(["ifconfig"], stderr=subprocess.STDOUT).decode().strip()
            ifaces = out
        except Exception:
            try:
                import psutil
                addrs = psutil.net_if_addrs()
                iface_lines = []
                for name, addr_list in addrs.items():
                    for addr in addr_list:
                        if addr.family == socket.AF_INET:
                            iface_lines.append("{}: {} (mask: {})".format(name, addr.address, addr.netmask))
                ifaces = "\n".join(iface_lines) if iface_lines else "No interfaces found"
            except Exception:
                ifaces = "No network tool available"
    result["sections"]["interfaces"] = ifaces

    # --- Gateway ---
    gateway = "unknown"
    try:
        out = subprocess.check_output(["ip", "route", "show", "default"], stderr=subprocess.STDOUT).decode().strip()
        gateway = out
    except Exception:
        try:
            out = subprocess.check_output(["route", "-n"], stderr=subprocess.STDOUT).decode().strip()
            gateway = out
        except Exception:
            gateway = "Could not determine gateway"
    result["sections"]["gateway"] = gateway

    # Build message
    lines = ["=== AstarteBam Network Info ===", ""]
    lines.append("[HOSTNAME] {}".format(hostname))
    lines.append("[LOCAL IP]  {}".format(local_ip))
    lines.append("[PUBLIC IP] {}".format(public_ip))
    if isinstance(public_info, dict) and "ip" in public_info:
        lines.append("  Location: {}, {}, {}".format(
            public_info.get("city", "?"), public_info.get("region", "?"), public_info.get("country", "?")))
        lines.append("  ISP: {}".format(public_info.get("isp", "?")))
        lines.append("  Geo: ({}, {})".format(public_info.get("lat", "?"), public_info.get("lon", "?")))
    lines.append("")
    lines.append("[INTERFACES]")
    lines.append("  " + ifaces.replace("\n", "\n  "))
    lines.append("")
    lines.append("[GATEWAY]")
    lines.append("  " + gateway.replace("\n", "\n  "))

    result["msg"] = "\n".join(lines)
    return result


if __name__ == "__main__":
    out = handle("", os.getcwd())
    print(out.get("msg", str(out)))