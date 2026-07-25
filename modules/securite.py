#!/usr/bin/env python3
"""Security scanner module - firewall, file permissions, hashing, SSH keys, random tokens."""

import os
import sys
import hashlib
import subprocess
import stat
import secrets
import string


def handle(args, cwd, stdin_data=""):
    """Security scanner with subcommands: scan (default), hash filepath, random."""
    args = args.strip()
    parts = args.split(None, 1)
    cmd = parts[0] if parts else "scan"
    sub_arg = parts[1] if len(parts) > 1 else ""

    if cmd == "hash":
        return _handle_hash(sub_arg, cwd)
    elif cmd == "random":
        return _handle_random(sub_arg)
    else:
        return _handle_scan(cwd)


def _handle_scan(cwd):
    """Run security scan."""
    result = {"ok": True, "findings": []}
    findings = result["findings"]

    # --- Firewall status ---
    fw_status = "unknown"
    try:
        out = subprocess.check_output(["ufw", "status"], stderr=subprocess.STDOUT).decode().strip()
        fw_status = out
        if "active" not in out.lower():
            findings.append({"level": "WARN", "item": "Firewall", "detail": "UFW is not active"})
        else:
            findings.append({"level": "OK", "item": "Firewall", "detail": "UFW is active"})
    except Exception:
        try:
            out = subprocess.check_output(["firewall-cmd", "--state"], stderr=subprocess.STDOUT).decode().strip()
            fw_status = "firewall-cmd: " + out
            if out.strip() == "running":
                findings.append({"level": "OK", "item": "Firewall", "detail": "firewalld is running"})
            else:
                findings.append({"level": "WARN", "item": "Firewall", "detail": "firewalld state: " + out.strip()})
        except Exception:
            fw_status = "No firewall tool detected"
            findings.append({"level": "WARN", "item": "Firewall", "detail": "No ufw or firewall-cmd found"})
    result["firewall"] = fw_status

    # --- Sensitive file permissions ---
    sensitive_files = ["/etc/shadow", "/etc/sudoers", "/etc/ssh/sshd_config", "/etc/passwd"]
    perm_checks = []
    for fpath in sensitive_files:
        check = {"path": fpath}
        if not os.path.exists(fpath):
            check["status"] = "MISSING"
            check["detail"] = "File not found"
            perm_checks.append(check)
            continue
        try:
            st = os.stat(fpath)
            mode = oct(st.st_mode)[-3:]
            check["mode"] = mode
            check["owner"] = st.st_uid
            if fpath == "/etc/shadow":
                if mode in ["640", "600", "400"]:
                    check["status"] = "OK"
                    check["detail"] = "Permissions are restrictive ({})".format(mode)
                else:
                    check["status"] = "CRITICAL"
                    check["detail"] = "Permissions too open: {} (should be 640 or 600)".format(mode)
                    findings.append({"level": "CRITICAL", "item": fpath, "detail": check["detail"]})
            elif fpath == "/etc/sudoers":
                if mode == "440":
                    check["status"] = "OK"
                    check["detail"] = "Permissions correct (440)"
                else:
                    check["status"] = "WARN"
                    check["detail"] = "Permissions: {} (expected 440)".format(mode)
                    findings.append({"level": "WARN", "item": fpath, "detail": check["detail"]})
            else:
                check["status"] = "INFO"
                check["detail"] = "Permissions: {}".format(mode)
        except Exception as e:
            check["status"] = "ERROR"
            check["detail"] = str(e)
        perm_checks.append(check)
    result["file_permissions"] = perm_checks

    # --- SSH key check ---
    ssh_dir = os.path.join(os.path.expanduser("~"), ".ssh")
    ssh_info = {"dir_exists": os.path.isdir(ssh_dir), "keys": []}
    if ssh_dir and os.path.isdir(ssh_dir):
        for fname in os.listdir(ssh_dir):
            fpath = os.path.join(ssh_dir, fname)
            if os.path.isfile(fpath) and fname not in [".", "..", "known_hosts", "known_hosts.old", "authorized_keys"]:
                if "pub" not in fname:
                    try:
                        st = os.stat(fpath)
                        mode = oct(st.st_mode)[-3:]
                        if mode not in ["600", "400"]:
                            findings.append({"level": "WARN", "item": "SSH key",
                                             "detail": "{} has mode {} (should be 600)".format(fname, mode)})
                        ssh_info["keys"].append({"file": fname, "mode": mode, "size": st.st_size})
                    except Exception:
                        ssh_info["keys"].append({"file": fname, "error": "cannot stat"})
    result["ssh_keys"] = ssh_info

    # --- File hashing of sensitive files ---
    hashes = {}
    for fpath in ["/etc/passwd", "/etc/shadow"]:
        if os.path.exists(fpath):
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
                hashes[fpath] = {
                    "md5": hashlib.md5(data).hexdigest(),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            except Exception as e:
                hashes[fpath] = {"error": str(e)}
    result["file_hashes"] = hashes

    # --- Build message ---
    lines = ["=== AstarteBam Security Scan ===", ""]
    lines.append("[FIREWALL] {}".format(fw_status))
    lines.append("")
    lines.append("[FILE PERMISSIONS]")
    for pc in perm_checks:
        status = pc.get("status", "?")
        lines.append("  [{}] {} - {} ({})".format(status, pc["path"], pc.get("mode", ""), pc.get("detail", "")))
    lines.append("")
    lines.append("[SSH KEYS] dir={}".format(ssh_info["dir_exists"]))
    for k in ssh_info.get("keys", []):
        lines.append("  {} - mode={} size={}".format(k.get("file", "?"), k.get("mode", "?"), k.get("size", "?")))
    lines.append("")
    lines.append("[FILE HASHES]")
    for fpath, h in hashes.items():
        if "md5" in h:
            lines.append("  {}:".format(fpath))
            lines.append("    MD5:    {}".format(h["md5"]))
            lines.append("    SHA256: {}".format(h["sha256"]))
        else:
            lines.append("  {}: {}".format(fpath, h.get("error", "")))
    lines.append("")
    lines.append("[FINDINGS] ({} items)".format(len(findings)))
    for f in findings:
        lines.append("  [{}] {}: {}".format(f["level"], f["item"], f["detail"]))

    result["msg"] = "\n".join(lines)
    return result


def _handle_hash(filepath, cwd):
    """Hash a file with MD5 and SHA256."""
    if not filepath:
        return {"ok": False, "error": "Usage: hash <filepath>"}
    fpath = os.path.join(cwd, filepath) if not os.path.isabs(filepath) else filepath
    if not os.path.isfile(fpath):
        return {"ok": False, "error": "File not found: {}".format(fpath)}
    try:
        with open(fpath, "rb") as f:
            data = f.read()
        md5 = hashlib.md5(data).hexdigest()
        sha256 = hashlib.sha256(data).hexdigest()
        size = len(data)
        msg = "File: {}\nSize: {} bytes\nMD5:    {}\nSHA256: {}".format(fpath, size, md5, sha256)
        return {"ok": True, "msg": msg, "md5": md5, "sha256": sha256, "size": size}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _handle_random(sub_arg):
    """Generate a random token. Optional arg: length (default 32)."""
    try:
        length = int(sub_arg) if sub_arg else 32
        if length < 1 or length > 1024:
            length = 32
    except ValueError:
        length = 32
    alphabet = string.ascii_letters + string.digits + string.punctuation
    token = "".join(secrets.choice(alphabet) for _ in range(length))
    msg = "Random token ({} chars):\n{}".format(length, token)
    return {"ok": True, "msg": msg, "token": token, "length": length}


if __name__ == "__main__":
    import json
    out = handle(" ".join(sys.argv[1:]), os.getcwd())
    print(out.get("msg", json.dumps(out, indent=2)))