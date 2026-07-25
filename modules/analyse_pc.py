#!/usr/bin/env python3
"""Full PC analysis module - platform, CPU, RAM, disks, network, uptime, ports, services."""

import os
import sys
import platform
import subprocess


def handle(args, cwd, stdin_data=""):
    """Full PC analysis: platform info, CPU, RAM, disks, network, uptime, open ports, services, firewall, SSH, users."""
    result = {"ok": True, "sections": {}}

    # --- Platform info ---
    plat = {
        "system": platform.system(),
        "node": platform.node(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
    }
    result["sections"]["platform"] = plat

    # --- CPU info (psutil if available) ---
    cpu_info = {}
    try:
        import psutil
        cpu_info["cpu_count_physical"] = psutil.cpu_count(logical=False)
        cpu_info["cpu_count_logical"] = psutil.cpu_count(logical=True)
        cpu_info["cpu_percent"] = psutil.cpu_percent(interval=1)
        cpu_info["cpu_freq"] = str(getattr(psutil.cpu_freq(), "current", "N/A"))
    except ImportError:
        cpu_info["note"] = "psutil not installed, limited CPU info"
        try:
            out = subprocess.check_output(["nproc"], stderr=subprocess.STDOUT).decode().strip()
            cpu_info["cpu_cores"] = out
        except Exception:
            cpu_info["cpu_cores"] = "unknown"
    except Exception as e:
        cpu_info["error"] = str(e)
    result["sections"]["cpu"] = cpu_info

    # --- RAM info ---
    ram_info = {}
    try:
        import psutil
        mem = psutil.virtual_memory()
        ram_info["total_mb"] = round(mem.total / (1024 * 1024), 2)
        ram_info["available_mb"] = round(mem.available / (1024 * 1024), 2)
        ram_info["used_mb"] = round(mem.used / (1024 * 1024), 2)
        ram_info["percent"] = mem.percent
        swap = psutil.swap_memory()
        ram_info["swap_total_mb"] = round(swap.total / (1024 * 1024), 2)
        ram_info["swap_used_mb"] = round(swap.used / (1024 * 1024), 2)
        ram_info["swap_percent"] = swap.percent
    except ImportError:
        ram_info["note"] = "psutil not installed"
        try:
            out = subprocess.check_output(["free", "-m"], stderr=subprocess.STDOUT).decode().strip()
            ram_info["free_output"] = out
        except Exception:
            ram_info["free_output"] = "unavailable"
    except Exception as e:
        ram_info["error"] = str(e)
    result["sections"]["ram"] = ram_info

    # --- Disk info ---
    disk_info = []
    try:
        import psutil
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_info.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent": usage.percent,
                })
            except Exception:
                disk_info.append({"device": part.device, "mountpoint": part.mountpoint, "note": "permission denied"})
    except ImportError:
        disk_info.append({"note": "psutil not installed"})
        try:
            out = subprocess.check_output(["df", "-h"], stderr=subprocess.STDOUT).decode().strip()
            disk_info.append({"df_output": out})
        except Exception:
            pass
    except Exception as e:
        disk_info.append({"error": str(e)})
    result["sections"]["disks"] = disk_info

    # --- Network interfaces ---
    net_info = {}
    try:
        import psutil
        addrs = psutil.net_if_addrs()
        net_info["interfaces"] = {}
        for iface, addr_list in addrs.items():
            entries = []
            for addr in addr_list:
                entries.append({
                    "family": str(addr.family),
                    "address": addr.address,
                    "netmask": addr.netmask,
                })
            net_info["interfaces"][iface] = entries
        net_stats = psutil.net_io_counters()
        net_info["bytes_sent"] = net_stats.bytes_sent
        net_info["bytes_recv"] = net_stats.bytes_recv
        net_info["packets_sent"] = net_stats.packets_sent
        net_info["packets_recv"] = net_stats.packets_recv
    except ImportError:
        net_info["note"] = "psutil not installed"
        try:
            out = subprocess.check_output(["ip", "a"], stderr=subprocess.STDOUT).decode().strip()
            net_info["ip_a_output"] = out[:2000]
        except Exception:
            try:
                out = subprocess.check_output(["ifconfig"], stderr=subprocess.STDOUT).decode().strip()
                net_info["ifconfig_output"] = out[:2000]
            except Exception:
                net_info["ip_output"] = "unavailable"
    except Exception as e:
        net_info["error"] = str(e)
    result["sections"]["network"] = net_info

    # --- Uptime ---
    uptime_info = {}
    try:
        out = subprocess.check_output(["uptime", "-p"], stderr=subprocess.STDOUT).decode().strip()
        uptime_info["uptime"] = out
    except Exception:
        try:
            with open("/proc/uptime", "r") as f:
                secs = float(f.read().split()[0])
                hours = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                uptime_info["uptime"] = "{}h {}m".format(hours, mins)
        except Exception:
            uptime_info["uptime"] = "unknown"
    result["sections"]["uptime"] = uptime_info

    # --- Open ports (ss -tlnp) ---
    ports_info = ""
    try:
        out = subprocess.check_output(["ss", "-tlnp"], stderr=subprocess.STDOUT).decode().strip()
        ports_info = out
    except Exception as e:
        ports_info = "Could not run ss: {}".format(str(e))
    result["sections"]["open_ports"] = ports_info

    # --- Running services ---
    services_info = ""
    try:
        out = subprocess.check_output(["systemctl", "list-units", "--type=service", "--state=running", "--no-pager"],
                                       stderr=subprocess.STDOUT).decode().strip()
        services_info = out
    except Exception as e:
        services_info = "Could not list services: {}".format(str(e))
    result["sections"]["running_services"] = services_info

    # --- Firewall status ---
    fw_info = ""
    try:
        out = subprocess.check_output(["ufw", "status"], stderr=subprocess.STDOUT).decode().strip()
        fw_info = out
    except Exception:
        try:
            out = subprocess.check_output(["firewall-cmd", "--state"], stderr=subprocess.STDOUT).decode().strip()
            fw_info = "firewall-cmd: " + out
        except Exception:
            fw_info = "No firewall tool detected (ufw/firewall-cmd)"
    result["sections"]["firewall"] = fw_info

    # --- SSH check ---
    ssh_info = {}
    ssh_config = "/etc/ssh/sshd_config"
    if os.path.exists(ssh_config):
        try:
            with open(ssh_config, "r") as f:
                lines = f.readlines()
            ssh_info["config_exists"] = True
            ssh_settings = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    if any(stripped.startswith(k) for k in ["Port ", "PermitRootLogin ", "PasswordAuthentication ",
                                                              "PubkeyAuthentication ", "PermitEmptyPasswords "]):
                        ssh_settings.append(stripped)
            ssh_info["key_settings"] = ssh_settings
        except Exception as e:
            ssh_info["error"] = str(e)
    else:
        ssh_info["config_exists"] = False
    # Check if sshd is running
    try:
        out = subprocess.check_output(["pgrep", "-c", "sshd"], stderr=subprocess.STDOUT).decode().strip()
        ssh_info["sshd_running"] = int(out) > 0
    except Exception:
        try:
            out = subprocess.check_output(["systemctl", "is-active", "sshd"], stderr=subprocess.STDOUT).decode().strip()
            ssh_info["sshd_running"] = out == "active"
        except Exception:
            ssh_info["sshd_running"] = "unknown"
    result["sections"]["ssh"] = ssh_info

    # --- Users with shell ---
    users_info = []
    try:
        with open("/etc/passwd", "r") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 7:
                    shell = parts[6]
                    if shell not in ["/bin/false", "/usr/sbin/nologin", "/bin/nologin", ""]:
                        users_info.append({"user": parts[0], "uid": parts[2], "shell": shell})
    except Exception as e:
        users_info = ["Error reading /etc/passwd: {}".format(str(e))]
    result["sections"]["users_with_shell"] = users_info

    # Build formatted message
    msg_lines = ["=== AstarteBam PC Analysis ===", ""]
    p = result["sections"]["platform"]
    msg_lines.append("[PLATFORM]")
    msg_lines.append("  OS: {} {} ({})".format(p["system"], p["release"], p["machine"]))
    msg_lines.append("  Hostname: {}".format(p["node"]))
    msg_lines.append("  Python: {}".format(p["python_version"]))
    msg_lines.append("")

    c = result["sections"]["cpu"]
    msg_lines.append("[CPU]")
    if "cpu_count_physical" in c:
        msg_lines.append("  Cores: {} physical / {} logical".format(c["cpu_count_physical"], c["cpu_count_logical"]))
        msg_lines.append("  Usage: {}%".format(c["cpu_percent"]))
    else:
        msg_lines.append("  {}".format(c.get("note", c.get("error", "N/A"))))
    msg_lines.append("")

    r = result["sections"]["ram"]
    msg_lines.append("[RAM]")
    if "total_mb" in r:
        msg_lines.append("  Total: {} MB | Used: {} MB ({:.1f}%) | Available: {} MB".format(
            r["total_mb"], r["used_mb"], r["percent"], r["available_mb"]))
    else:
        msg_lines.append("  {}".format(r.get("note", "N/A")))
    msg_lines.append("")

    msg_lines.append("[DISKS]")
    for d in result["sections"]["disks"]:
        if "device" in d:
            msg_lines.append("  {} on {} ({}) - {}GB / {}GB ({:.0f}%)".format(
                d.get("device", "?"), d.get("mountpoint", "?"), d.get("fstype", "?"),
                d.get("used_gb", 0), d.get("total_gb", 0), d.get("percent", 0)))
        else:
            msg_lines.append("  {}".format(d.get("note", d.get("df_output", ""))))
    msg_lines.append("")

    msg_lines.append("[NETWORK]")
    n = result["sections"]["network"]
    if "interfaces" in n:
        for iface, entries in n["interfaces"].items():
            for e in entries:
                if "address" in e and "." in e["address"]:
                    msg_lines.append("  {}: {}".format(iface, e["address"]))
    else:
        msg_lines.append("  {}".format(n.get("note", "N/A")))
    msg_lines.append("")

    msg_lines.append("[UPTIME] {}".format(result["sections"]["uptime"].get("uptime", "N/A")))
    msg_lines.append("")
    msg_lines.append("[OPEN PORTS]")
    msg_lines.append("  " + result["sections"]["open_ports"].replace("\n", "\n  "))
    msg_lines.append("")
    msg_lines.append("[FIREWALL] {}".format(result["sections"]["firewall"]))
    msg_lines.append("")
    msg_lines.append("[SSH]")
    s = result["sections"]["ssh"]
    msg_lines.append("  Running: {}".format(s.get("sshd_running", "unknown")))
    for setting in s.get("key_settings", []):
        msg_lines.append("  " + setting)
    msg_lines.append("")
    msg_lines.append("[USERS WITH SHELL]")
    for u in result["sections"]["users_with_shell"]:
        if isinstance(u, dict):
            msg_lines.append("  {} (uid={}, shell={})".format(u["user"], u["uid"], u["shell"]))
        else:
            msg_lines.append("  {}".format(u))

    result["msg"] = "\n".join(msg_lines)
    return result


if __name__ == "__main__":
    out = handle("", os.getcwd())
    print(out.get("msg", out))