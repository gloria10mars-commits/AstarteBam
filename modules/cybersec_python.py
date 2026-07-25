#!/usr/bin/env python3
"""Advanced cybersecurity Python environment scanner."""

import os
import sys


def handle(args, cwd, stdin_data=""):
    """Advanced cybersecurity scan: YARA, PyShark, CryptoDome, security score."""
    results = {}
    score = 0
    max_score = 0
    findings = []

    # --- Check YARA ---
    yara_info = {"installed": False}
    try:
        import yara
        yara_info["installed"] = True
        yara_info["version"] = getattr(yara, "__version__", "unknown")
        score += 10
        findings.append({"tool": "YARA", "status": "INSTALLED", "detail": "Version: {}".format(yara_info["version"])})
    except ImportError:
        yara_info["detail"] = "Not installed. Install: pip install yara-python"
        findings.append({"tool": "YARA", "status": "MISSING", "detail": yara_info["detail"]})
    max_score += 10
    results["yara"] = yara_info

    # --- Check PyShark ---
    pyshark_info = {"installed": False}
    try:
        import pyshark
        pyshark_info["installed"] = True
        pyshark_info["version"] = getattr(pyshark, "__version__", "unknown")
        score += 10
        findings.append({"tool": "PyShark", "status": "INSTALLED", "detail": "Version: {}".format(pyshark_info["version"])})
    except ImportError:
        pyshark_info["detail"] = "Not installed. Install: pip install pyshark"
        findings.append({"tool": "PyShark", "status": "MISSING", "detail": pyshark_info["detail"]})
    max_score += 10
    results["pyshark"] = pyshark_info

    # --- Check CryptoDome / pycryptodome ---
    crypto_info = {"installed": False}
    try:
        from Crypto.Cipher import AES
        crypto_info["installed"] = True
        crypto_info["backend"] = "pycryptodome"
        try:
            from Crypto import __version__ as cv
            crypto_info["version"] = cv
        except Exception:
            crypto_info["version"] = "unknown"
        score += 10
        findings.append({"tool": "CryptoDome", "status": "INSTALLED", "detail": "Version: {}".format(crypto_info.get("version", "unknown"))})
    except ImportError:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher
            crypto_info["installed"] = True
            crypto_info["backend"] = "cryptography"
            try:
                import cryptography
                crypto_info["version"] = cryptography.__version__
            except Exception:
                crypto_info["version"] = "unknown"
            score += 8
            findings.append({"tool": "cryptography", "status": "INSTALLED", "detail": "Version: {}".format(crypto_info.get("version", "unknown"))})
        except ImportError:
            crypto_info["detail"] = "Neither pycryptodome nor cryptography installed"
            findings.append({"tool": "Crypto", "status": "MISSING", "detail": crypto_info["detail"]})
    max_score += 10
    results["crypto"] = crypto_info

    # --- Check Scapy ---
    scapy_info = {"installed": False}
    try:
        import scapy
        scapy_info["installed"] = True
        scapy_info["version"] = getattr(scapy, "__version__", "unknown")
        score += 10
        findings.append({"tool": "Scapy", "status": "INSTALLED", "detail": "Version: {}".format(scapy_info["version"])})
    except ImportError:
        scapy_info["detail"] = "Not installed. Install: pip install scapy"
        findings.append({"tool": "Scapy", "status": "MISSING", "detail": scapy_info["detail"]})
    max_score += 10
    results["scapy"] = scapy_info

    # --- Check Requests (common for security tools) ---
    requests_info = {"installed": False}
    try:
        import requests
        requests_info["installed"] = True
        requests_info["version"] = requests.__version__
        score += 5
        findings.append({"tool": "requests", "status": "INSTALLED", "detail": "Version: {}".format(requests_info["version"])})
    except ImportError:
        requests_info["detail"] = "Not installed"
        findings.append({"tool": "requests", "status": "MISSING", "detail": "Not installed"})
    max_score += 5
    results["requests"] = requests_info

    # --- Check psutil ---
    psutil_info = {"installed": False}
    try:
        import psutil
        psutil_info["installed"] = True
        psutil_info["version"] = psutil.__version__
        score += 5
        findings.append({"tool": "psutil", "status": "INSTALLED", "detail": "Version: {}".format(psutil_info["version"])})
    except ImportError:
        psutil_info["detail"] = "Not installed"
        findings.append({"tool": "psutil", "status": "MISSING", "detail": "Not installed"})
    max_score += 5
    results["psutil"] = psutil_info

    # --- Calculate security score ---
    pct = int((score / max_score * 100)) if max_score > 0 else 0

    if pct >= 80:
        grade = "A - Well equipped"
    elif pct >= 60:
        grade = "B - Good setup"
    elif pct >= 40:
        grade = "C - Basic tools"
    elif pct >= 20:
        grade = "D - Minimal"
    else:
        grade = "F - Needs improvement"

    # Build message
    lines = [
        "=== AstarteBam CyberSec Python Scan ===",
        "",
        "[SECURITY TOOL CHECK]",
    ]
    for f in findings:
        status = f["status"]
        icon = "[+]" if status == "INSTALLED" else "[-]"
        lines.append("  {} {}: {}".format(icon, f["tool"], f["detail"]))

    lines.append("")
    lines.append("[SECURITY SCORE]")
    lines.append("  Score: {}/{} ({}%)".format(score, max_score, pct))
    lines.append("  Grade: {}".format(grade))
    lines.append("")
    lines.append("[RECOMMENDATIONS]")
    if not results["yara"]["installed"]:
        lines.append("  - Install YARA for malware pattern matching: pip install yara-python")
    if not results["pyshark"]["installed"]:
        lines.append("  - Install PyShark for packet analysis: pip install pyshark")
    if not results["crypto"]["installed"]:
        lines.append("  - Install pycryptodome for crypto operations: pip install pycryptodome")
    if not results["scapy"]["installed"]:
        lines.append("  - Install Scapy for network crafting: pip install scapy")

    return {
        "ok": True,
        "msg": "\n".join(lines),
        "score": score,
        "max_score": max_score,
        "percentage": pct,
        "grade": grade,
        "tools": results,
        "findings": findings,
    }


if __name__ == "__main__":
    out = handle("", os.getcwd())
    print(out.get("msg", str(out)))