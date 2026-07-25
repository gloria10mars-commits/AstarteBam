#!/usr/bin/env python3
"""
AstarteBam v6.0 — Serveur HTTP Complet
- File d'attente de prompts (POST /prompt, GET /next_prompt)
- 2 modes worker: API cle / Tampermonkey scraping
- 12 actions standardisees {type, args, content}
- Logs chaines avec long polling
- Boucle de feedback auto-correction
- Execution interactive (streaming, input utilisateur)
- Detection commandes dangereuses + confirmation
- Upload sur serveurs libres (URL retournee au LLM)
- Compatible Python 3.6+ / 32-bit / pure Python
"""
import json
import os
import re
import sys
import uuid
import time
import shutil
import base64
import hashlib
import threading
import importlib
import importlib.util
import subprocess
import select
import pty
import signal
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from core.orchestrator import CollaborativeOrchestrator
from core.providers import ProviderRegistry

# ═══════════════════════════════════════════════════
# CONFIGURATION via .env
# ═══════════════════════════════════════════════════
APP_NAME = "Astarte BAM"
APP_VERSION = "6.0.0"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.join(BASE_DIR, "workspace")
MODULES_DIR = os.path.join(BASE_DIR, "modules")
LOGS_DIR = os.path.join(WORKSPACE, "logs")

def log_activity(category, message, level="INFO"):
    log_path = os.path.join(LOGS_DIR, "activity.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] [{category}] {message}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)
    print(line.strip())


class ConfigError(ValueError):
    """Configuration locale invalide : le serveur ne doit pas démarrer."""

def load_env():
    """Charge un fichier .env simple, sans masquer les erreurs de lecture."""
    env_file = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_file):
        return False
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    raise ConfigError(".env ligne {} : format attendu CLE=VALEUR".format(number))
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if not key:
                    raise ConfigError(".env ligne {} : clé vide".format(number))
                # L'environnement du système garde la priorité sur le fichier.
                os.environ.setdefault(key, value)
    except OSError as exc:
        raise ConfigError("Impossible de lire .env : {}".format(exc))
    return True

def env_int(name, default, minimum, maximum):
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ConfigError("{} doit être un entier (valeur reçue : {!r})".format(name, raw))
    if not minimum <= value <= maximum:
        raise ConfigError("{} doit être entre {} et {} (valeur reçue : {})".format(name, minimum, maximum, value))
    return value

def is_local_host(host):
    host = host.strip().lower()
    return host == "localhost" or host == "::1" or host.startswith("127.")

try:
    ENV_FILE_FOUND = load_env()
    HOST = os.environ.get("HOST", "127.0.0.1").strip() or "127.0.0.1"
    ADMIN_HOST = os.environ.get("ADMIN_HOST", HOST).strip() or HOST
    PORT = env_int("PORT", 8765, 1, 65535)
    ADMIN_PORT = env_int("ADMIN_PORT", 8766, 1, 65535)
    if PORT == ADMIN_PORT:
        raise ConfigError("PORT et ADMIN_PORT doivent être différents")
    API_KEY = os.environ.get("API_KEY", "").strip()
    MAX_ACTIONS = env_int("MAX_ACTIONS", 20, 1, 100)
    MAX_CONTENT_SIZE = env_int("MAX_CONTENT_SIZE", 1048576, 1, 50 * 1024 * 1024)
    MAX_FEEDBACK_ATTEMPTS = 0  # 0 = illimité ; la boucle s’arrête uniquement avec actions: []
    WORKER_MODE = os.environ.get("WORKER_MODE", "api").strip().lower()
    if WORKER_MODE not in ("api", "tampermonkey"):
        raise ConfigError("WORKER_MODE doit être 'api' ou 'tampermonkey'")
    COMMAND_POLICY = os.environ.get("COMMAND_POLICY", "warn").strip().lower()
    if COMMAND_POLICY not in ("warn", "block", "allow"):
        raise ConfigError("COMMAND_POLICY doit être 'warn', 'block' ou 'allow'")
    ORCHESTRATION_MODE = os.environ.get("ASTARTE_MODE", os.environ.get("ORCHESTRATION_MODE", "individual")).strip().lower()
    if ORCHESTRATION_MODE not in ("individual", "collaborative"):
        raise ConfigError("ORCHESTRATION_MODE doit être 'individual' ou 'collaborative'")
    COLLAB_MAX_AGENTS = env_int("COLLAB_MAX_AGENTS", 3, 1, 5)
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "nvidia").strip().lower()
    AI_SLOT = os.environ.get("AI_SLOT", "1").strip()
    if AI_SLOT not in ("1", "2"):
        raise ConfigError("AI_SLOT doit être 1 ou 2")
    if AI_PROVIDER not in ("nvidia", "groq", "fireworks", "cohere", "gemini", "nemapi"):
        raise ConfigError("AI_PROVIDER doit être nvidia, groq, fireworks, cohere, gemini ou nemapi")
    NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
    NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "qwen/qwen3-next-80b-a3b-instruct").strip()
    NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b").strip()
    GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    NEMESIS_API_URL = os.environ.get("NEMESIS_API_URL", "http://127.0.0.1:5000").rstrip("/")
    NEMAPI_RESET_ON_NEW_TASK = os.environ.get("NEMAPI_RESET_ON_NEW_TASK", "true").strip().lower() in ("1", "true", "yes", "on")
except ConfigError as exc:
    print("[CONFIG] Erreur : {}".format(exc), file=sys.stderr)
    print("[CONFIG] Corrigez le fichier .env puis relancez le serveur.", file=sys.stderr)
    raise SystemExit(2)

os.makedirs(WORKSPACE, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(MODULES_DIR, exist_ok=True)
PROVIDER_REGISTRY = ProviderRegistry()
worker_thread_started = False
worker_start_lock = threading.Lock()

# ═══════════════════════════════════════════════════
# SECURITE
# ═══════════════════════════════════════════════════
DANGEROUS_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$", "Suppression recursive de /"),
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?\*", "Suppression massive avec *"),
    (r"\bmkfs\b", "Formatage de disque"),
    (r"\bdd\s+.*of=/dev/", "Ecriture directe sur device"),
    (r"\bchmod\s+777\s+/\s*$", "Permissions ouvertes sur /"),
    (r"\bshred\b", "Destruction securisee"),
    (r">\s*/dev/sd[a-z]", "Ecriture sur disque"),
    (r"\bkill\s+-9\s+1\b", "Kill init"),
    (r"\bshutdown\b", "Arret du systeme"),
    (r"\breboot\b", "Redemarrage"),
    (r"\binit\s+0\b", "Changement runlevel 0"),
]

def check_dangerous(command):
    """Verifie si une commande est dangereuse. Retourne (dangerous, reason)."""
    if not command:
        return False, ""
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, reason
    return False, ""

def resolve_path(user_path, base=None):
    """Résout un chemin. Mode système : les chemins absolus et ../ sont autorisés."""
    if not isinstance(user_path, str) or not user_path:
        return None
    if base is None:
        base = WORKSPACE
    return os.path.realpath(user_path if os.path.isabs(user_path) else os.path.join(base, user_path))

def resolve_path_exists(user_path, base=None):
    p = resolve_path(user_path, base)
    if p is None:
        return None, False
    return p, os.path.exists(p)

# ═══════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════
VALID_ACTION_TYPES = {
    "exec", "write_file", "write_file_b64", "read_file",
    "replace", "append", "delete_file", "copy", "list_dir",
    "module", "fix", "upload", "delegate"
}
ACTION_FIELDS = {"type", "args", "content", "interactive"}

# Alias souvent inventés par les LLM -> type canonique
ACTION_ALIASES = {
    "exec_command": "exec", "command": "exec", "shell": "exec", "run": "exec",
    "bash": "exec", "cmd": "exec", "execute": "exec",
    "write": "write_file", "create_file": "write_file", "writefile": "write_file",
    "write_b64": "write_file_b64",
    "read": "read_file", "readfile": "read_file", "cat": "read_file", "open": "read_file",
    "list": "list_dir", "ls": "list_dir", "listdir": "list_dir", "list_files": "list_dir",
    "dir": "list_dir",
    "delete": "delete_file", "remove": "delete_file", "rm": "delete_file",
    "move": "copy", "cp": "copy",
}


def normalize_action_type(value):
    if not isinstance(value, str):
        return value
    norm = value.strip().lower().replace("-", "_").replace(" ", "_")
    return ACTION_ALIASES.get(norm, norm)
CONTENT_REQUIRED = {"write_file", "write_file_b64", "replace", "append", "copy"}
ARGS_REQUIRED = VALID_ACTION_TYPES - {"list_dir", "delegate"}

def _valid_base64(value):
    try:
        base64.b64decode(value, validate=True)
        return True
    except (ValueError, TypeError):
        return False

def validate_request(data):
    """Valide complètement le contrat JSON v1 avant toute action système."""
    if not isinstance(data, dict):
        return False, "La requête doit être un objet JSON"
    if data.get("version") not in (1, 2):
        return False, "version doit être égale à 1 ou 2"
    allowed_request_fields = {"version", "thought", "stop_on_error", "cwd", "actions"}
    unexpected = set(data) - allowed_request_fields
    if unexpected:
        return False, "Champ(s) de requête non autorisé(s) : {}".format(", ".join(sorted(unexpected)))
    if "stop_on_error" in data and not isinstance(data["stop_on_error"], bool):
        return False, "stop_on_error doit être un booléen"
    if "cwd" in data and not isinstance(data["cwd"], str):
        return False, "cwd doit être une chaîne"
    actions = data.get("actions")
    if not isinstance(actions, list):
        return False, "actions doit être une liste"
    if len(actions) > MAX_ACTIONS:
        return False, "Trop d’actions (maximum : {})".format(MAX_ACTIONS)
    for index, action in enumerate(actions, 1):
        prefix = "Action {}".format(index)
        if not isinstance(action, dict):
            return False, prefix + " doit être un objet"
        unexpected = set(action) - ACTION_FIELDS
        if unexpected:
            return False, prefix + ": champ(s) non autorisé(s) : {}".format(", ".join(sorted(unexpected)))
        action_type = normalize_action_type(action.get("type"))
        if isinstance(action_type, str) and action_type != action.get("type"):
            action["type"] = action_type
        if action_type not in VALID_ACTION_TYPES:
            return False, prefix + ": type invalide {!r}".format(action.get("type"))
        args = action.get("args", "")
        content = action.get("content", "")
        if not isinstance(args, str) or not isinstance(content, str):
            return False, prefix + ": args et content doivent être des chaînes"
        if action_type in ARGS_REQUIRED and not args.strip():
            return False, prefix + ": args est obligatoire pour {}".format(action_type)
        if action_type in CONTENT_REQUIRED and not content:
            return False, prefix + ": content est obligatoire pour {}".format(action_type)
        if len(args) > MAX_CONTENT_SIZE or len(content) > MAX_CONTENT_SIZE:
            return False, prefix + ": args ou content dépasse MAX_CONTENT_SIZE"
        if "interactive" in action and (action_type != "exec" or not isinstance(action["interactive"], bool)):
            return False, prefix + ": interactive est un booléen réservé à exec"
        if action_type == "write_file_b64" and not _valid_base64(content):
            return False, prefix + ": content doit être du Base64 valide"
        if action_type == "replace" and ("<<<<<<< SEARCH" not in content or "=======" not in content or ">>>>>>> REPLACE" not in content):
            return False, prefix + ": replace exige les marqueurs SEARCH / REPLACE"
    return True, ""

# ═══════════════════════════════════════════════════
# LOGS CHAINES — Per-request log queues
# ═══════════════════════════════════════════════════
logs_store = {}
logs_lock = threading.Lock()

def add_log(request_id, log_entry):
    with logs_lock:
        if request_id not in logs_store:
            logs_store[request_id] = {"logs": [], "event": threading.Event(), "done": False}
        store = logs_store[request_id]
        log_entry["log_index"] = len(store["logs"])
        store["logs"].append(log_entry)
        store["event"].set()

def finish_logs(request_id):
    with logs_lock:
        if request_id in logs_store:
            logs_store[request_id]["done"] = True
            logs_store[request_id]["event"].set()

def get_logs(request_id, after_index=-1, timeout=None):
    with logs_lock:
        if request_id not in logs_store:
            return []
        store = logs_store[request_id]
    start = after_index + 1
    if start < len(store["logs"]):
        return store["logs"][start:]
    if store["done"]:
        return store["logs"][start:]
    store["event"].wait(timeout=timeout)
    store["event"].clear()
    with logs_lock:
        return store["logs"][start:]

# Plafonds de stockage/feedback par type d'action : pour delegation/lecture/
# listing, le contenu EST la donnee utile des agents (pas un simple statut).
_LOG_CAPS = {"delegate": 40000, "read_file": 40000, "list_dir": 12000}
_FEEDBACK_CAPS = {"DELEGATE": 20000, "READ_FILE": 20000, "LIST_DIR": 8000}


def result_to_output(action_type, result):
    """Synthetise une sortie texte lisible quand l'action n'a pas de champ output
    (list_dir, read_file, write_file, copy, delete_file...). Sans ca, les agents
    ne voient pas le resultat de leurs propres actions."""
    out = result.get("output")
    if out:
        return out
    if not result.get("ok"):
        return result.get("error", "")
    t = action_type
    if t == "list_dir":
        entries = result.get("entries", []) or []
        lines = ["Contenu de {} ({} elements) :".format(result.get("path", "?"), result.get("count", len(entries)))]
        for e in entries[:300]:
            mark = "/" if e.get("type") == "directory" else ""
            lines.append("  {}{}  ({} o, {})".format(e.get("name", "?"), mark, e.get("size", 0), e.get("modified", "?")))
        if len(entries) > 300:
            lines.append("  ... et {} autres".format(len(entries) - 300))
        return "\n".join(lines)
    if t == "read_file":
        return result.get("content", "")
    if t in ("write_file", "write_file_b64", "append"):
        return "Fichier ecrit : {} ({} octets)".format(result.get("path", "?"), result.get("size", result.get("new_size", "?")))
    if t == "delete_file":
        return "Supprime : {}".format(result.get("deleted", "?"))
    if t == "copy":
        return "Copie : {} -> {} ({})".format(result.get("source", "?"), result.get("destination", "?"), result.get("type", "?"))
    if t == "fix":
        return "Ligne {} de {} :\n{}".format(result.get("line", "?"), result.get("path", "?"), result.get("context", ""))
    if t == "upload":
        return "Televerse : {} ({} octets)".format(result.get("file", "?"), result.get("size", "?"))
    return ""


def make_log(action_type, action_args, status, message="", data=None, error=None, duration_ms=0, max_msg=4000):
    entry = {
        "action_type": action_type,
        "action_args": str(action_args)[:200],
        "status": status,
        "message": str(message)[:max_msg],
        "duration_ms": duration_ms,
        "timestamp": datetime.now().isoformat()
    }
    if data:
        entry["data"] = data
    if error:
        entry["error"] = error
    return entry

# ═══════════════════════════════════════════════════
# INTERACTIVE PROCESS MANAGER
# ═══════════════════════════════════════════════════
active_processes = {}
active_processes_lock = threading.Lock()
INPUT_PATTERNS = [
    "[sudo] password", "Password:", "Enter password",
    "Mot de passe", "passphrase", "Continue? [Y/n]",
    "Are you sure?", "Confirm?", "Enter passphrase",
    "Login:", "Username:", "mysql>", ">>> ",
]

def detect_input_required(text):
    text_lower = text.lower()
    for pattern in INPUT_PATTERNS:
        if pattern.lower() in text_lower:
            return True, pattern
    return False, ""

def should_mask(text):
    mask_words = ["password", "mot de passe", "passphrase"]
    text_lower = text.lower()
    for w in mask_words:
        if w in text_lower:
            return True
    return False

def stream_process(request_id, command, cwd, stdin_data=""):
    """Exécute la commande dans un pseudo-terminal et diffuse chaque sortie au CLI."""
    master_fd, slave_fd = pty.openpty()
    process = None
    output_chunks = []
    try:
        process = subprocess.Popen(
            command, shell=True, cwd=cwd,
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True, preexec_fn=os.setsid
        )
    finally:
        os.close(slave_fd)
    with active_processes_lock:
        active_processes[request_id] = {"process": process, "input_fd": master_fd}

    def read_output():
        try:
            while True:
                ready, _, _ = select.select([master_fd], [], [], 0.25)
                if ready:
                    try:
                        chunk = os.read(master_fd, 1024)
                    except OSError:
                        break
                    if not chunk:
                        break
                    text = chunk.decode("utf-8", errors="replace")
                    output_chunks.append(text)
                    input_req, input_prompt = detect_input_required(text)
                    log_data = {"text": text}
                    if input_req:
                        log_data.update({"input_required": True, "input_prompt": input_prompt, "mask": should_mask(text)})
                    # Les morceaux sans saut de ligne sont volontairement envoyés : sudo affiche son prompt ainsi.
                    add_log(request_id, make_log("exec", command, "running", text.rstrip("\r\n"), data=log_data))
                if process.poll() is not None and not ready:
                    break
        except Exception:
            pass

    reader_thread = threading.Thread(target=read_output, daemon=True)
    reader_thread.start()
    if stdin_data:
        try:
            os.write(master_fd, (stdin_data + "\n").encode("utf-8"))
        except OSError:
            pass
    process.wait()
    reader_thread.join()
    with active_processes_lock:
        active_processes.pop(request_id, None)
    try:
        os.close(master_fd)
    except OSError:
        pass
    return process.returncode, "".join(output_chunks)

# ═══════════════════════════════════════════════════
# CONFIRMATIONS UTILISATEUR — actions destructives ou sensibles
# ═══════════════════════════════════════════════════
pending_confirmations = {}
confirmations_lock = threading.Lock()
confirmation_waitable_requests = set()

def confirmation_reason(action, cwd):
    action_type, args, content = action.get("type", ""), action.get("args", ""), action.get("content", "")
    if action_type == "exec":
        dangerous, reason = check_dangerous(args)
        if dangerous and COMMAND_POLICY != "block":
            return "Commande shell sensible : {}".format(reason)
    elif action_type == "delete_file":
        return "Suppression du chemin {}".format(resolve_path(args, cwd))
    elif action_type in ("write_file", "write_file_b64"):
        target = resolve_path(args, cwd)
        if target and os.path.exists(target):
            return "Écrasement du fichier existant {}".format(target)
    elif action_type == "copy":
        target = resolve_path(content, cwd)
        if target and os.path.exists(target):
            return "Écrasement ou fusion vers la destination existante {}".format(target)
    return ""

def await_confirmation(request_id, action, cwd, reason):
    """Attend oui/non depuis le CLI. Les requêtes synchrones ne sont pas bloquées."""
    if request_id not in confirmation_waitable_requests:
        return False, "Confirmation requise : utilisez /execute_async ou le CLI pour cette action"
    event = threading.Event()
    details = {"action_type": action.get("type"), "args": action.get("args", ""), "reason": reason}
    with confirmations_lock:
        pending_confirmations[request_id] = {"event": event, "approved": None, "details": details}
    add_log(request_id, make_log("confirmation", action.get("args", ""), "confirmation", reason, data={"confirmation_required": True, "details": details}))
    event.wait()
    with confirmations_lock:
        decision = pending_confirmations.pop(request_id, {}).get("approved")
    if decision is True:
        add_log(request_id, make_log("confirmation", action.get("args", ""), "success", "Action confirmée par l’utilisateur."))
        return True, ""
    return False, "Action refusée par l’utilisateur"

def submit_confirmation(request_id, approved):
    with confirmations_lock:
        pending = pending_confirmations.get(request_id)
        if not pending:
            return False, "Aucune confirmation en attente pour cette requête"
        pending["approved"] = approved
        pending["event"].set()
    return True, "Confirmation enregistrée"

# ═══════════════════════════════════════════════════
# ACTION EXECUTOR — 12 actions
# ═══════════════════════════════════════════════════
def resolve_cwd(request):
    cwd_str = request.get("cwd", "")
    if cwd_str:
        p = resolve_path(cwd_str)
        if p and os.path.isdir(p):
            return p
    return WORKSPACE


def execute_action(action, cwd, request_id=None, log_index_offset=0):
    atype = action.get("type", "")
    args = action.get("args", "")
    content = action.get("content", "") or ""
    interactive = action.get("interactive", False)
    start = time.time()

    reason = confirmation_reason(action, cwd)
    if reason:
        approved, error = await_confirmation(request_id, action, cwd, reason)
        if not approved:
            return {"ok": False, "error": error, "confirmation_required": True, "confirmation_reason": reason}

    try:
        if atype == "delegate":
            target = args.lower()
            prompt = content
            add_log(request_id, make_log("system", "delegation", "running", f"Délégation de tâche à {target}..."))
            # Appel interne au provider cible
            res, slot, err = PROVIDER_REGISTRY.call([{"role": "user", "content": prompt}], preferred=target)
            if err:
                return {"ok": False, "error": f"Échec de la délégation à {target}: {err}"}
            return {"ok": True, "output": f"[RETOUR DE {target.upper()}] : {res}"}
        elif atype == "exec":
            return do_exec(args, cwd, content, request_id, interactive)
        elif atype == "write_file":
            return do_write_file(args, content, cwd)
        elif atype == "write_file_b64":
            return do_write_file_b64(args, content, cwd)
        elif atype == "read_file":
            return do_read_file(args, cwd)
        elif atype == "replace":
            return do_replace(args, content, cwd)
        elif atype == "append":
            return do_append(args, content, cwd)
        elif atype == "delete_file":
            return do_delete_file(args, cwd)
        elif atype == "copy":
            return do_copy(args, content, cwd)
        elif atype == "list_dir":
            return do_list_dir(args, cwd)
        elif atype == "module":
            return do_module(args, content, cwd)
        elif atype == "fix":
            return do_fix(args, cwd)
        elif atype == "upload":
            return do_upload(args, cwd)
        else:
            return {"ok": False, "error": "Unknown action type: {}".format(atype)}
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        return {"ok": False, "error": str(e), "duration_ms": duration}


def do_exec(command, cwd, stdin_data="", request_id=None, interactive=False):
    if not command or not isinstance(command, str):
        return {"ok": False, "error": "Missing or invalid command"}
    if len(command) > MAX_CONTENT_SIZE:
        return {"ok": False, "error": "Command too large"}
    dangerous, reason = check_dangerous(command)
    if dangerous and COMMAND_POLICY == "block":
        return {"ok": False, "error": "Commande bloquée par COMMAND_POLICY : {}".format(reason), "danger_reason": reason}
    warning = "Commande sensible détectée : {}".format(reason) if dangerous and COMMAND_POLICY == "warn" else ""

    if request_id:
        exit_code, output = stream_process(request_id, command, cwd, stdin_data)
        return {
            "ok": exit_code == 0,
            "output": output or "(no output)",
            "exit_code": exit_code,
            "interactive": True,
            "warning": warning
        }

    try:
        # Intentionally no execution timeout: a command may run until it exits.
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            cwd=cwd, input=stdin_data
        )
        output = (r.stdout + r.stderr).strip() or "(no output)"
        result = {"ok": r.returncode == 0, "output": output, "exit_code": r.returncode}
        if warning:
            result["warning"] = warning
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_write_file(path, content, cwd):
    if not path:
        return {"ok": False, "error": "Missing file path"}
    safe = resolve_path(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected or path outside workspace"}
    content = content if isinstance(content, str) else str(content)
    if len(content) > MAX_CONTENT_SIZE:
        return {"ok": False, "error": "Content too large"}
    try:
        parent = os.path.dirname(safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(safe, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": safe, "size": len(content)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_write_file_b64(path, b64_content, cwd):
    if not path:
        return {"ok": False, "error": "Missing file path"}
    if not b64_content:
        return {"ok": False, "error": "Missing base64 content"}
    safe = resolve_path(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    try:
        decoded = base64.b64decode(b64_content)
        if len(decoded) > MAX_CONTENT_SIZE:
            return {"ok": False, "error": "Decoded content too large"}
        parent = os.path.dirname(safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(safe, "wb") as f:
            f.write(decoded)
        return {"ok": True, "path": safe, "size": len(decoded)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_read_file(path, cwd):
    if not path:
        return {"ok": False, "error": "Missing file path"}
    safe, exists = resolve_path_exists(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    if not exists:
        return {"ok": False, "error": "File not found: {}".format(path)}
    if os.path.isdir(safe):
        return {"ok": False, "error": "C'est un dossier (pas un fichier). Utilise l'action list_dir sur ce chemin pour voir son contenu."}
    try:
        with open(safe, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"ok": True, "path": safe, "content": content, "size": len(content)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_replace(path, content, cwd):
    if not path:
        return {"ok": False, "error": "Missing file path"}
    if not content:
        return {"ok": False, "error": "Missing replace content"}
    safe, exists = resolve_path_exists(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    if not exists:
        return {"ok": False, "error": "File not found: {}".format(path)}
    try:
        with open(safe, "r", encoding="utf-8") as f:
            file_content = f.read()
        blocks = content.split("<<<<<<< SEARCH")
        replacements = 0
        for block in blocks[1:]:
            parts = block.split("=======", 1)
            if len(parts) < 2:
                continue
            search_text = parts[0].rstrip("\n\r")
            rest = parts[1]
            replace_parts = rest.split(">>>>>>> REPLACE", 1)
            if len(replace_parts) < 2:
                continue
            replace_text = replace_parts[0].rstrip("\n\r")
            if search_text in file_content:
                file_content = file_content.replace(search_text, replace_text, 1)
                replacements += 1
        with open(safe, "w", encoding="utf-8") as f:
            f.write(file_content)
        return {"ok": replacements > 0, "replacements": replacements, "path": safe}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_append(path, content, cwd):
    if not path:
        return {"ok": False, "error": "Missing file path"}
    safe = resolve_path(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    content = content if isinstance(content, str) else str(content)
    try:
        parent = os.path.dirname(safe)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(safe, "a", encoding="utf-8") as f:
            f.write(content)
        new_size = os.path.getsize(safe)
        return {"ok": True, "path": safe, "new_size": new_size}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_delete_file(path, cwd):
    if not path:
        return {"ok": False, "error": "Missing file path"}
    safe, exists = resolve_path_exists(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    if not exists:
        return {"ok": False, "error": "Not found: {}".format(path)}
    try:
        if os.path.isdir(safe):
            shutil.rmtree(safe)
        else:
            os.remove(safe)
        return {"ok": True, "deleted": safe}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_copy(args, dest, cwd):
    if not args:
        return {"ok": False, "error": "Missing source path"}
    if not dest:
        return {"ok": False, "error": "Missing destination path"}
    src_safe = resolve_path(args, cwd)
    dst_safe = resolve_path(dest, cwd)
    if src_safe is None or dst_safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    if not os.path.exists(src_safe):
        return {"ok": False, "error": "Source not found: {}".format(args)}
    try:
        if os.path.isdir(src_safe):
            shutil.copytree(src_safe, dst_safe, dirs_exist_ok=True)
            return {"ok": True, "source": src_safe, "destination": dst_safe, "type": "directory"}
        else:
            parent = os.path.dirname(dst_safe)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(src_safe, dst_safe)
            return {"ok": True, "source": src_safe, "destination": dst_safe, "type": "file"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_list_dir(path, cwd):
    if not path:
        path = "."
    safe, exists = resolve_path_exists(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    if not exists:
        return {"ok": False, "error": "Directory not found: {}".format(path)}
    if not os.path.isdir(safe):
        return {"ok": False, "error": "Not a directory: {}".format(path)}
    try:
        entries = []
        for name in sorted(os.listdir(safe)):
            full = os.path.join(safe, name)
            is_dir = os.path.isdir(full)
            try:
                stat_info = os.stat(full)
                size = stat_info.st_size if not is_dir else 0
                mtime = datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size = 0
                mtime = "?"
            entries.append({"name": name, "type": "directory" if is_dir else "file", "size": size, "modified": mtime})
        return {"ok": True, "path": safe, "entries": entries, "count": len(entries)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_fix(path_and_line, cwd):
    if not path_and_line:
        return {"ok": False, "error": "Missing args (expected: 'file.py line_number')"}
    parts = path_and_line.strip().rsplit(None, 1)
    if len(parts) < 2:
        return {"ok": False, "error": "Usage: 'file.py line_number'"}
    path, line_str = parts
    try:
        line_no = int(line_str)
    except ValueError:
        return {"ok": False, "error": "Line number must be an integer"}
    safe, exists = resolve_path_exists(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    if not exists:
        return {"ok": False, "error": "File not found: {}".format(path)}
    try:
        with open(safe, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        idx = line_no - 1
        start = max(0, idx - 3)
        end = min(len(lines), idx + 4)
        context = []
        for i in range(start, end):
            marker = ">> " if i == idx else "   "
            context.append("{}{:4d} | {}".format(marker, i + 1, lines[i].rstrip()))
        return {"ok": True, "path": safe, "line": line_no, "context": context, "total_lines": len(lines)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def do_upload(path, cwd):
    if not path:
        return {"ok": False, "error": "Missing file path"}
    safe, exists = resolve_path_exists(path, cwd)
    if safe is None:
        return {"ok": False, "error": "Path traversal detected"}
    if not exists:
        return {"ok": False, "error": "File not found: {}".format(path)}
    filename = os.path.basename(safe)
    try:
        with open(safe, "rb") as f:
            file_data = f.read()
        url = upload_to_tmpfiles(file_data, filename)
        if url:
            return {"ok": True, "url": url, "file": filename, "size": len(file_data)}
        return {"ok": False, "error": "Upload failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def upload_to_tmpfiles(file_data, filename):
    boundary = "----AstarteBam" + uuid.uuid4().hex[:8]
    body = (
        "--" + boundary + "\r\n"
        + 'Content-Disposition: form-data; name="file"; filename="'
        + filename + '"\r\n'
        + "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_data + ("\r\n--" + boundary + "--\r\n").encode()
    req = urllib.request.Request(
        "https://tmpfiles.org/api/v1/upload",
        data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary}
    )
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read().decode())
        page_url = result.get("data", {}).get("url", "")
        if page_url:
            direct_url = page_url.replace("https://tmpfiles.org/", "https://tmpfiles.org/dl/")
            return direct_url
    except Exception:
        pass
    try:
        req2 = urllib.request.Request(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data=urllib.parse.urlencode({
                "reqtype": "fileupload",
                "time": "72h",
                "fileToUpload": ""
            }).encode()
        )
        boundary2 = "----AstarteBam" + uuid.uuid4().hex[:8]
        body2 = (
            "--" + boundary2 + "\r\n"
            + 'Content-Disposition: form-data; name="reqtype"\r\n\r\nfileupload\r\n'
            + "--" + boundary2 + "\r\n"
            + 'Content-Disposition: form-data; name="time"\r\n\r\n72h\r\n'
            + "--" + boundary2 + "\r\n"
            + 'Content-Disposition: form-data; name="fileToUpload"; filename="'
            + filename + '"\r\n'
            + "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + file_data + ("\r\n--" + boundary2 + "--\r\n").encode()
        req2 = urllib.request.Request(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data=body2,
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary2}
        )
        resp2 = urllib.request.urlopen(req2)
        url = resp2.read().decode().strip()
        if url.startswith("http"):
            return url
    except Exception:
        pass
    return None

# ═══════════════════════════════════════════════════
# DYNAMIC MODULE LOADER (importlib)
# ═══════════════════════════════════════════════════
_modules_cache = {}
_modules_lock = threading.Lock()

def discover_modules():
    mods = {}
    if not os.path.isdir(MODULES_DIR):
        return mods
    for fname in os.listdir(MODULES_DIR):
        if fname.endswith(".py") and not fname.startswith("_"):
            mod_name = fname[:-3]
            mods[mod_name] = os.path.join(MODULES_DIR, fname)
    return mods

def load_module(name):
    with _modules_lock:
        if name in _modules_cache:
            return _modules_cache[name]
        module_map = discover_modules()
        filepath = module_map.get(name)
        if not filepath or not os.path.exists(filepath):
            return None
        try:
            spec = importlib.util.spec_from_file_location("astarte_mod_{}".format(name), filepath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "handle"):
                return None
            _modules_cache[name] = mod
            return mod
        except Exception:
            return None

def do_module(module_name, module_args, cwd):
    if not module_name:
        return {"ok": False, "error": "Missing module name"}
    name = module_name.lstrip("/").strip().lower()
    mod = load_module(name)
    if mod is None:
        available = sorted(discover_modules().keys())
        return {"ok": False, "error": "Module '{}' not found".format(module_name), "available_modules": available}
    try:
        args_str = module_args if isinstance(module_args, str) else str(module_args)
        result = mod.handle(args_str, cwd, "")
        if not isinstance(result, dict):
            result = {"ok": False, "error": "Module returned non-dict"}
        return result
    except Exception as e:
        return {"ok": False, "error": "Module error ({}): {}".format(name, str(e))}

def list_modules():
    module_map = discover_modules()
    result = []
    for name in sorted(module_map.keys()):
        mod = load_module(name)
        desc = ""
        if mod and hasattr(mod, "__doc__") and mod.__doc__:
            desc = mod.__doc__.strip().split("\n")[0]
        result.append({"name": name, "description": desc})
    return result

# ═══════════════════════════════════════════════════
# PROMPT INPUT AND WORKER AVAILABILITY
# ═══════════════════════════════════════════════════
def validate_prompt_request(data):
    if not isinstance(data, dict):
        return False, "La requête doit être un objet JSON"
    unexpected = set(data) - {"prompt", "system_prompt", "cwd"}
    if unexpected:
        return False, "Champ(s) non autorisé(s) : {}".format(", ".join(sorted(unexpected)))
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return False, "prompt doit être une chaîne non vide"
    if len(prompt) > MAX_CONTENT_SIZE:
        return False, "prompt dépasse MAX_CONTENT_SIZE"
    for field in ("system_prompt", "cwd"):
        if field in data and not isinstance(data[field], str):
            return False, "{} doit être une chaîne".format(field)
        if isinstance(data.get(field), str) and len(data[field]) > MAX_CONTENT_SIZE:
            return False, "{} dépasse MAX_CONTENT_SIZE".format(field)
    return True, ""

def worker_available():
    """Évite de mettre une demande en attente sans worker utilisable."""
    if WORKER_MODE == "api":
        available = PROVIDER_REGISTRY.public_status()
        return bool(available), "Aucun slot fournisseur configuré" if not available else ""
    try:
        request = urllib.request.Request(NEMESIS_API_URL + "/health")
        with urllib.request.urlopen(request) as response:
            if 200 <= response.status < 300:
                return True, ""
    except Exception as exc:
        return False, "NEMESIS indisponible : {}".format(exc)
    return False, "NEMESIS a renvoyé un statut non valide"

# ═══════════════════════════════════════════════════
# DIRECT JSON EXECUTION — synchronous compatibility + asynchronous jobs
# ═══════════════════════════════════════════════════
direct_results = {}
direct_results_lock = threading.Lock()

def execute_direct_request(data, request_id):
    """Exécute les actions JSON et alimente les logs du request_id."""
    started = time.time()
    cwd = resolve_cwd(data)
    stop = data.get("stop_on_error", True)
    results, all_ok = [], True
    with direct_results_lock:
        direct_results[request_id] = {"id": request_id, "status": "running", "created_at": started, "results": results}
    for action in data["actions"]:
        action_started = time.time()
        result = execute_action(action, cwd, request_id=request_id)
        result["action_type"] = action["type"]
        result["duration_ms"] = int((time.time() - action_started) * 1000)
        add_log(request_id, make_log(action["type"], action.get("args", ""), "success" if result.get("ok") else "error", result_to_output(action.get("type", "?"), result), duration_ms=result["duration_ms"], max_msg=_LOG_CAPS.get(action.get("type", ""), 4000)))
        results.append(result)
        if not result.get("ok"):
            all_ok = False
            if stop:
                break
    status = "success" if all_ok else "partial_error" if any(item.get("ok") for item in results) else "error"
    response = {"version": 1, "request_id": request_id, "status": status, "results": results, "duration_ms": int((time.time() - started) * 1000)}
    with direct_results_lock:
        direct_results[request_id].update(response)
    finish_logs(request_id)
    confirmation_waitable_requests.discard(request_id)
    return response

def start_direct_request(data):
    request_id = str(uuid.uuid4())[:8]

    log_activity("RECEIVE", f"Nouveau prompt reçu (ID: {request_id})")
    confirmation_waitable_requests.add(request_id)
    add_log(request_id, make_log("system", "execute_async", "running", "Exécution asynchrone en attente..."))
    thread = threading.Thread(target=execute_direct_request, args=(data, request_id), daemon=True)
    thread.start()
    return request_id

# ═══════════════════════════════════════════════════
# PROMPT QUEUE SYSTEM
# ═══════════════════════════════════════════════════
prompt_queue = []
prompt_queue_lock = threading.Lock()
prompt_results = {}
prompt_results_lock = threading.Lock()

def add_prompt(prompt_text, system_prompt="", cwd=""):
    prompt_id = str(uuid.uuid4())[:8]
    entry = {
        "id": prompt_id,
        "prompt": prompt_text,
        "system_prompt": system_prompt,
        "cwd": cwd,
        "status": "pending",
        "attempt": 0,
        "history": [],
        "created_at": time.time()
    }
    with prompt_queue_lock:
        prompt_queue.append(entry)
    with prompt_results_lock:
        prompt_results[prompt_id] = entry
    confirmation_waitable_requests.add(prompt_id)
    add_log(prompt_id, make_log("system", "queue", "running", "Prompt en attente de traitement..."))
    if AI_PROVIDER == "nemapi" and NEMAPI_RESET_ON_NEW_TASK:
        try:
            PROVIDER_REGISTRY.reset_nemapi_session()
            add_log(prompt_id, make_log("nemapi", "session", "success", "Session DeepSeek Bridge réinitialisée pour cette tâche."))
        except Exception as exc:
            add_log(prompt_id, make_log("nemapi", "session", "error", "Bridge indisponible : {}".format(exc)))
    return prompt_id

def get_next_prompt():
    with prompt_queue_lock:
        for entry in prompt_queue:
            if entry["status"] == "pending":
                entry["status"] = "scraping"
                return entry
    return None

def submit_llm_response(prompt_id, response_text):
    with prompt_results_lock:
        entry = prompt_results.get(prompt_id)
    if not entry:
        return False, "Prompt not found"
    entry["status"] = "processing"
    entry["llm_response_raw"] = response_text
    json_blocks = extract_json_blocks(response_text)
    if not json_blocks:
        entry["status"] = "error"
        entry["error"] = "No valid JSON found in LLM response"
        return False, "No valid JSON"
    return process_prompt_with_actions(entry, json_blocks[0])

def process_prompt_with_actions(entry, action_data):
    valid, err = validate_request(action_data)
    if not valid:
        entry["status"] = "error"
        entry["error"] = "Invalid JSON: {}".format(err)
        return False, err

    request_id = entry["id"]
    cwd = resolve_cwd(action_data)
    entry["status"] = "executing"

    stop = action_data.get("stop_on_error", True)
    actions = action_data.get("actions", [])
    if not actions:
        # LLM a envoyé un JSON vide : tout est terminé
        entry["status"] = "done"
        finish_logs(entry["id"])
        confirmation_waitable_requests.discard(entry["id"])
        return True, "done (no more actions)"
    results = []
    all_ok = True

    for i, action in enumerate(actions):
        start = time.time()
        result = execute_action(action, cwd, request_id=request_id)
        duration = int((time.time() - start) * 1000)
        result["action_type"] = action.get("type", "?")
        result["duration_ms"] = duration

        log_entry = make_log(
            action.get("type", "?"),
            action.get("args", ""),
            "success" if result.get("ok") else "error",
            result_to_output(action.get("type", "?"), result),
            data={"result": {k: v for k, v in result.items() if k != "action_type"}},
            duration_ms=duration,
            max_msg=_LOG_CAPS.get(action.get("type", ""), 4000)
        )
        add_log(request_id, log_entry)
        results.append(result)

        if not result.get("ok"):
            all_ok = False
            if stop:
                break

    entry["history"].append({
        "attempt": entry["attempt"] + 1,
        "results": results,
        "all_ok": all_ok
    })
    entry["attempt"] += 1

    # Boucle de feedback : le prochain tour reçoit le résultat et décide de continuer ou de corriger.
    entry["status"] = "pending"
    entry["retry_prompt"] = build_continue_prompt(entry) if all_ok else build_retry_prompt(entry)
    feedback_kind = "continue" if all_ok else "retry"
    add_log(request_id, make_log("feedback", feedback_kind, "running", "Étape {} terminée : nouveau tour IA préparé.".format(entry["attempt"])))
    return False, feedback_kind

def build_continue_prompt(entry):
    """Construit un prompt pour que le LLM continue apres succes."""
    results = entry.get("history", [])[-1].get("results", [])
    history_count = len(entry.get("history", []))
    lines = [
        "[ACTIONS REUSSIES - Etape {}]".format(history_count),
        "ATTENTION: Ne repete pas les memes actions. Passe a l'etape suivante.",
        "Si tu viens de lister des fichiers, maintenant LIS leur contenu avec cat.",
        "Si tu as deja lu les fichiers, reponds avec un JSON vide.",
        "",
    ]
    for i, r in enumerate(results):
        atype = r.get("action_type", "?")
        output = r.get("output", "") or r.get("msg", "") or r.get("path", "") or ""
        cap = _FEEDBACK_CAPS.get(atype.upper(), 1000)
        lines.append("{}/{} {} : {}".format(i + 1, len(results), atype, str(output)[:cap]))
    lines.extend([
        "",
        "[INSTRUCTION]",
        "AVANCE dans la tache. Ne liste pas, ne scanne pas, EXECUTE.",
        "Si tout est fait: {\"version\":1,\"actions\":[]}",
        "Sinon: actions PERTINENTES pour l'etape suivante."
    ])
    return "\n".join(lines)

def build_retry_prompt(entry):
    history = entry.get("history", [])
    last = history[-1] if history else {}
    results = last.get("results", [])
    lines = [
        "[CONTEXTE FEEDBACK - Etape {}]".format(entry["attempt"]),
        "Prompt original : {}".format(entry["prompt"]),
        "",
        "[RESULTATS DES ACTIONS]"
    ]
    for i, r in enumerate(results):
        atype = r.get("action_type", "?")
        ok = r.get("ok", False)
        flag = "SUCCES" if ok else "ECHEC"
        detail = ""
        if ok:
            detail = r.get("output") or r.get("path") or r.get("size") or ""
        else:
            detail = r.get("error") or ""
        cap = _FEEDBACK_CAPS.get(atype.upper(), 1000)
        lines.append("Action {}/{} : {} {} — {}".format(i + 1, len(results), atype, flag, str(detail)[:cap]))

    lines.extend([
        "",
        "[INSTRUCTION]",
        "Les actions ont echoue. Analyse les erreurs ci-dessus.",
        "Genere UNIQUEMENT les actions necessaires pour CORRIGER le probleme.",
        "Ne refais PAS les actions qui ont deja reussi.",
        "Utilise l'action 'replace' pour corriger un fichier ou 'write_file' pour reecrire."
    ])
    return "\n".join(lines)

# ═══════════════════════════════════════════════════
# AUTO-RELOAD — Surveille les fichiers et redemarre
# ═══════════════════════════════════════════════════
WATCHED_FILES = {}  # {path: mtime}

def file_watcher_loop():
    """Surveille les fichiers. Recharge les modules a chaud sans tuer le serveur."""
    global WATCHED_FILES
    watch_dirs = [BASE_DIR, os.path.join(BASE_DIR, "modules"), os.path.join(BASE_DIR, "config")]
    while True:
        try:
            for wdir in watch_dirs:
                if not os.path.isdir(wdir):
                    continue
                for fname in os.listdir(wdir):
                    fpath = os.path.join(wdir, fname)
                    if not fname.endswith(".py") and not fname.endswith(".txt") and not fname.endswith(".js") and fname != ".env":
                        continue
                    if not os.path.isfile(fpath):
                        continue
                    try:
                        mtime = os.stat(fpath).st_mtime
                    except OSError:
                        continue
                    if fpath in WATCHED_FILES:
                        if WATCHED_FILES[fpath] != mtime:
                            print("\n  [WATCHER] Fichier modifie: {}".format(fname))
                            if fname.endswith(".py") and "modules" in fpath:
                                modname = fname[:-3]
                                with _modules_lock:
                                    if modname in _modules_cache:
                                        del _modules_cache[modname]
                                        print("  [WATCHER] Module {} recharge a chaud.".format(modname))
                            elif fname == ".env":
                                load_env()
                                print("  [WATCHER] .env recharge.")
                            else:
                                print("  [WATCHER] Modification detectee (redemarrage manuel requis).")
                    WATCHED_FILES[fpath] = mtime
            time.sleep(1)
        except Exception as e:
            time.sleep(2)

# ═══════════════════════════════════════════════════
# CONFIG PERSISTENCE
# ═══════════════════════════════════════════════════
def _save_env(env_path):
    """Sauvegarde les variables d'environnement dans le fichier .env"""
    keys = ["HOST", "ADMIN_HOST", "PORT", "ADMIN_PORT", "API_KEY", "MAX_ACTIONS",
            "MAX_CONTENT_SIZE", "WORKER_MODE", "COMMAND_POLICY", "ORCHESTRATION_MODE", "COLLAB_MAX_AGENTS", "AI_PROVIDER", "NVIDIA_API_KEY", "NVIDIA_MODEL", "GROQ_API_KEY", "GROQ_MODEL", "GROQ_BASE_URL",
            "NVIDIA_BASE_URL", "NEMESIS_API_URL", "NEMESIS_MODEL"]
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("# AstarteBam v6.0 — Configuration\n")
        for k in keys:
            v = os.environ.get(k, "")
            f.write("{}={}\n".format(k, v))

# ═══════════════════════════════════════════════════
# NEMESIS API WORKER — Scraping via Tampermonkey
# ═══════════════════════════════════════════════════
def call_nemesis_api(prompt_text, retries=3):
    """Envoie un prompt a l'API NEMESIS qui scrape le LLM via navigateur."""
    url = NEMESIS_API_URL + "/v1/chat/completions"
    body = json.dumps({
        "model": os.environ.get("NEMESIS_MODEL", "deepseek"),
        "messages": [{"role": "user", "content": prompt_text}]
    }).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req)
            result = json.loads(resp.read().decode("utf-8"))
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return content, None
            return None, "Empty response from NEMESIS"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            return None, "NEMESIS error: {}".format(str(e))
    return None, "NEMESIS max retries reached"

# ═══════════════════════════════════════════════════
# API WORKER — Call LLM directly
# ═══════════════════════════════════════════════════


def call_llm_api(messages, retries=2, preferred_override=None):
    preferred = preferred_override if preferred_override else AI_PROVIDER
    log_activity("PROCESS", f"Appel IA ({preferred})...")
    
    # PROVIDER_REGISTRY.call renvoie (text, slot, error)
    text, slot, error = PROVIDER_REGISTRY.call(messages, preferred=preferred, preferred_slot=AI_SLOT if ORCHESTRATION_MODE == "individual" else None)
    
    if error:
        log_activity("IA-ERROR", f"Erreur IA: {error}")
        return None, error
    
    if text:
        log_activity("IA-SUCCESS", f"Réponse reçue ({len(text)} chars)")
    return text, None


def extract_json_blocks(text):
    if not text or not isinstance(text, str): return []
    import json, re

    def _scan(candidate):
        """Essaie d'extraire un JSON d'actions valide depuis `candidate`."""
        found = []
        # Stratégie 1 : blocs Markdown ```json ... ```
        for m in re.finditer(r'```(?:json)?\s*([\s\S]*?)```', candidate):
            try:
                p = json.loads(m.group(1).strip())
                if isinstance(p, dict) and 'actions' in p:
                    found.append(p)
            except Exception:
                pass
        # Stratégie 2 : première accolade -> dernière accolade
        if not found:
            try:
                s, e = candidate.find('{'), candidate.rfind('}')
                if s != -1 and e != -1 and e > s:
                    p = json.loads(candidate[s:e+1])
                    if isinstance(p, dict) and 'actions' in p:
                        found.append(p)
            except Exception:
                pass
        return found

    # Passe 1 : texte brut. CRUCIAL : ne JAMAIS retirer 'Copy'/'Download' ici,
    # sinon le contenu des fichiers écrits par le LLM est corrompu.
    results = _scan(text)
    if results:
        return results
    # Passe 2 (fallback pour les réponses scrappées via navigateur) :
    # on enlève alors les résidus d'UI collés au texte.
    ctext = text.replace('Copy\nDownload', '').replace('Copy', '').replace('Download', '')
    return _scan(ctext)

def worker_process_prompt(entry):
    system_prompt = entry.get("system_prompt", "")
    if not system_prompt:
        try:
            sp_path = os.path.join(BASE_DIR, "config", "system_prompt_collaboratif_v1.txt" if ORCHESTRATION_MODE == "collaborative" else "system_prompt_v2.txt")
            with open(sp_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()
        except Exception:
            system_prompt = "Respond with JSON: {\"version\":1,\"actions\":[...]}"

    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": entry["prompt"]})

    if "retry_prompt" in entry:
        messages[-1] = {"role": "user", "content": entry["retry_prompt"]}

    # Afficher le VRAI modèle du fournisseur actif (bug: qwen NVIDIA affiché pour nemapi/deepseek-web)
    _active_slots = PROVIDER_REGISTRY.ordered(AI_PROVIDER, AI_SLOT)
    active_model = _active_slots[0]["model"] if _active_slots else "(aucun slot disponible)"
    add_log(entry["id"], make_log("worker", "api_call", "running", "Appel {} / {}...".format(AI_PROVIDER, active_model)))

    NETWORK_ERRORS = ["Temporary failure", "timed out", "Service Unavailable", "ResourceExhausted", "rate limit"]
    
    max_api_retries = 5
    for api_attempt in range(max_api_retries):
        resp_text, err = call_llm_api(messages)
        if not err and resp_text:
            add_log(entry["id"], make_log("llm", "production", "success", resp_text))
        if err:
            is_network = any(e in err for e in NETWORK_ERRORS)
            add_log(entry["id"], make_log("worker", "api_call", "error" if not is_network else "retry", 
                "Tentative {}/{} - {}".format(api_attempt + 1, max_api_retries, err)))
            if is_network and api_attempt < max_api_retries - 1:
                wait = (api_attempt + 1) * 5
                add_log(entry["id"], make_log("worker", "retry", "running", "Nouvelle tentative dans {}s...".format(wait)))
                time.sleep(wait)
                continue
            entry["status"] = "error"
            entry["error"] = err
            finish_logs(entry["id"])
            return False, err
        break

    add_log(entry["id"], make_log("worker", "api_response", "success", "Réponse reçue ({} chars)".format(len(resp_text))))
    add_log(entry["id"], make_log("llm", "response", "success", resp_text[:500]))

    json_blocks = extract_json_blocks(resp_text)
    if not json_blocks:
        add_log(entry["id"], make_log("worker", "parse", "error", "No JSON found in response"))
        entry["status"] = "error"
        entry["error"] = "No JSON in LLM response"
        finish_logs(entry["id"])
        confirmation_waitable_requests.discard(entry["id"])
        return False, "No JSON"

    return process_prompt_with_actions(entry, json_blocks[0])

def worker_process_prompt_nemesis(entry):
    """Traite un prompt via l'API NEMESIS (Tampermonkey scraping)."""
    prompt_text = entry.get("retry_prompt", entry["prompt"])
    add_log(entry["id"], make_log("worker", "nemesis_call", "running", "Appel API NEMESIS..."))
    
    resp_text, err = call_nemesis_api(prompt_text)
    if err:
        add_log(entry["id"], make_log("worker", "nemesis_call", "error", err))
        entry["status"] = "error"
        entry["error"] = err
        finish_logs(entry["id"])
        return False, err
    
    add_log(entry["id"], make_log("worker", "nemesis_response", "success", "{} chars".format(len(resp_text))))
    add_log(entry["id"], make_log("llm", "response", "success", resp_text[:500]))
    
    json_blocks = extract_json_blocks(resp_text)
    if not json_blocks:
        add_log(entry["id"], make_log("worker", "parse", "error", "No JSON found"))
        entry["status"] = "error"
        entry["error"] = "No JSON in NEMESIS response"
        finish_logs(entry["id"])
        confirmation_waitable_requests.discard(entry["id"])
        return False, "No JSON"
    
    return process_prompt_with_actions(entry, json_blocks[0])

def worker_process_prompt_collaborative(entry):
    """Sous-agents parallèles : ils produisent des plans puis l'orchestrateur les exécute."""
    try:
        system_prompt = open(os.path.join(BASE_DIR, "config", "system_prompt_collaboratif_v1.txt"), encoding="utf-8").read()
    except Exception:
        system_prompt = "Réponds exclusivement avec un JSON v1 d'actions."

    def call_agent(role_prompt, role, provider_force=None):
        add_log(entry["id"], make_log("agent", role, "running", f"Sous-agent {role} en cours..."))
        pref = provider_force if provider_force else AI_PROVIDER
        raw, err = call_llm_api([{"role": "system", "content": system_prompt}, {"role": "user", "content": role_prompt}], preferred_override=pref)
        if raw is None: raw = ""
        add_log(entry["id"], make_log("llm", role, "success", raw))
        return raw, pref, err

    agent_limit = 1 if AI_PROVIDER == "nemapi" else COLLAB_MAX_AGENTS
    orchestrator = CollaborativeOrchestrator(call_agent, extract_json_blocks, agent_limit)

    # Construction du feedback (Rapport détaillé Tour par Tour)
    history_str = ""
    task_logs = logs_store.get(entry["id"], {}).get("logs", [])
    # Ne garder que les vraies actions d'exécution (délégation Gemini/DeepSeek comprise).
    # Sans ce filtre, les réponses LLM brutes et les logs système polluent le rapport.
    ACTION_LOG_TYPES = {"exec", "write_file", "write_file_b64", "read_file", "replace", "append",
                        "delete_file", "copy", "list_dir", "module", "fix", "upload", "delegate"}
    executed_actions = [l for l in task_logs
                        if l.get("status") in ("success", "error")
                        and l.get("action_type") in ACTION_LOG_TYPES]

    if executed_actions:
        tour = entry.get('attempt', 0)
        history_str = f"\n--- [RAPPORT D'EXECUTION - TOUR {tour}] ---\n"
        for i, l in enumerate(executed_actions, 1):
            status_label = "SUCCÈS ✅" if l.get("status") == "success" else "ÉCHEC ❌"
            atype = str(l.get('action_type', 'action')).upper()
            # make_log stocke la sortie dans 'message' (le bug lisait 'content' -> rapport vide)
            args_lbl = str(l.get('action_args', '')).strip()
            message = str(l.get('message', '')).strip()
            summary = (args_lbl + (" → " if args_lbl and message else "") + message)
            cap = _FEEDBACK_CAPS.get(atype, 1000)
            summary = (summary[:cap] + "...") if len(summary) > cap else summary
            history_str += f"[{i}/{len(executed_actions)}] {atype} | {status_label}\n   ➤ Sortie : {summary}\n"
        
        history_str += "\n[DIRECTIVES DE CONTINUATION]\n1. ANALYSE les résultats ci-dessus.\n2. NE REFAIS PAS les actions réussies.\n3. CORRIGE les erreurs (❌) en priorité.\n"

    log_activity("FEEDBACK", f"Historique compilé ({len(executed_actions)} actions) envoyé aux agents.")
    
    plan, report = orchestrator.run(entry["id"], entry.get("retry_prompt", entry["prompt"]), task_history=history_str)
    entry["collaboration_report"] = report
    add_log(entry["id"], make_log("orchestrator", report["category"], "success", report["summary"], data={"report": report}))
    
    valid, error = validate_request(plan)
    if not valid:
        entry["status"] = "error"
        entry["error"] = f"Plan collaboratif invalide : {error}"
        add_log(entry["id"], make_log("orchestrator", "plan_invalide", "error", entry["error"]))
        finish_logs(entry["id"])
        return False, error
        
    return process_prompt_with_actions(entry, plan)

def worker_loop():
    while True:
        try:
            time.sleep(0.5)
            with prompt_queue_lock:
                found = None
                for entry in prompt_queue:
                    if entry["status"] == "pending":
                        found = entry
                        entry["status"] = "processing"
                        break
            if not found:
                continue
            if WORKER_MODE == "tampermonkey":
                try:
                    worker_process_prompt_nemesis(found)
                except Exception as e:
                    found["status"] = "error"
                    found["error"] = str(e)
                    finish_logs(found["id"])
            elif WORKER_MODE == "api" and PROVIDER_REGISTRY.public_status():
                try:
                    if ORCHESTRATION_MODE == "collaborative":
                        worker_process_prompt_collaborative(found)
                    else:
                        worker_process_prompt(found)
                except Exception as e:
                    found["status"] = "error"
                    found["error"] = str(e)
                    finish_logs(found["id"])
        except Exception as e:
            import traceback
            traceback.print_exc()
            time.sleep(2)

# Démarre le worker API lorsqu’une clé est ajoutée à chaud par /config.
def ensure_api_worker():
    global worker_thread_started
    has_key = bool(PROVIDER_REGISTRY.public_status())
    if WORKER_MODE != "api" or not has_key:
        return False
    with worker_start_lock:
        if worker_thread_started:
            return False
        thread = threading.Thread(target=worker_loop, daemon=True)
        thread.start()
        worker_thread_started = True
        print("  Worker API thread démarré.")
        return True

# ═══════════════════════════════════════════════════
# HTTP SERVER
# ═══════════════════════════════════════════════════
try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

try:
    from socketserver import ThreadingMixIn
except ImportError:
    import SocketServer
    ThreadingMixIn = SocketServer.ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            print("[{}] {}".format(ts, fmt % args))
        except Exception:
            pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_CONTENT_SIZE * MAX_ACTIONS:
            return None, "Request too large"
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8")), None
        except (ValueError, json.JSONDecodeError) as e:
            return None, "Invalid JSON: {}".format(str(e))

    def _check_auth(self):
        if not API_KEY:
            return True
        key = self.headers.get("X-API-Key", "") or self.headers.get("Authorization", "").replace("Bearer ", "")
        expected_hash = hashlib.sha256(API_KEY.encode()).hexdigest()
        return key == API_KEY or key == expected_hash

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = self.path.split("?")[0]
        query = self.path.split("?")[1] if "?" in self.path else ""

        if parsed == "/ping":
            self._json(200, {
                "version": 1, "status": "ok",
                "message": "{} v{} operational".format(APP_NAME, APP_VERSION),
                "workspace": WORKSPACE,
                "modules_count": len(discover_modules()),
                "worker_mode": WORKER_MODE
            })

        elif parsed == "/modules":
            self._json(200, {"ok": True, "modules": list_modules()})

        elif parsed == "/health":
            import platform
            self._json(200, {
                "ok": True, "python": platform.python_version(),
                "platform": platform.system(), "arch": platform.machine()
            })

        elif parsed == "/next_prompt":
            if not self._check_auth():
                self._json(401, {"ok": False, "error": "Invalid API key"})
                return
            entry = get_next_prompt()
            if entry:
                entry["status"] = "scraping"
                resp = {"id": entry["id"], "prompt": entry["prompt"], "system_prompt": entry.get("system_prompt", ""), "cwd": entry.get("cwd", ""), "attempt": entry["attempt"]}
                if "retry_prompt" in entry:
                    resp["retry_prompt"] = entry["retry_prompt"]
                self._json(200, resp)
            else:
                self._json(200, {"prompt": None})

        elif parsed.startswith("/result/"):
            rid = parsed.split("/result/")[1]
            with direct_results_lock:
                direct = direct_results.get(rid)
            if direct:
                response = dict(direct)
                response["duration_ms"] = int((time.time() - direct["created_at"]) * 1000)
                self._json(200, response)
                return
            with prompt_results_lock:
                entry = prompt_results.get(rid)
            if not entry:
                self._json(404, {"error": "Not found"})
                return
            resp = {
                "id": entry["id"],
                "status": entry["status"],
                "attempt": entry["attempt"],
                "duration_ms": int((time.time() - entry.get("created_at", time.time())) * 1000)
            }
            if entry["status"] == "done" or entry["status"] == "partial_error":
                history = entry.get("history", [])
                if history and isinstance(history, list) and len(history) > 0:
                    last = history[-1]
                    if isinstance(last, dict):
                        resp["results"] = last.get("results", [])
            if entry.get("error"):
                resp["error"] = entry["error"]
            self._json(200, resp)

        elif parsed.startswith("/logs/"):
            rid = parsed.split("/logs/")[1].split("?")[0]
            params = {}
            if query:
                for pair in query.split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        params[k] = v
            after = int(params.get("after", "-1"))
            timeout_raw = int(params.get("timeout", "0"))
            timeout = None if timeout_raw <= 0 else timeout_raw
            new_logs = get_logs(rid, after, timeout)
            self._json(200, {"request_id": rid, "logs": new_logs, "more": not logs_store.get(rid, {}).get("done", True)})

        elif parsed.startswith("/queue"):
            with prompt_queue_lock:
                queue_info = []
                for e in prompt_queue:
                    queue_info.append({"id": e["id"], "status": e["status"], "prompt": e["prompt"][:100], "attempt": e["attempt"]})
            self._json(200, {"queue": queue_info})

        elif parsed == "/providers":
            self._json(200, {"ok": True, "mode": ORCHESTRATION_MODE, "providers": PROVIDER_REGISTRY.public_status()})

        elif parsed == "/config":
            self._json(200, {
                "HOST": HOST,
                "PORT": PORT,
                "ADMIN_HOST": ADMIN_HOST,
                "ADMIN_PORT": ADMIN_PORT,
                "WORKER_MODE": WORKER_MODE,
                "COMMAND_POLICY": COMMAND_POLICY,
                "ORCHESTRATION_MODE": ORCHESTRATION_MODE,
                "COLLAB_MAX_AGENTS": COLLAB_MAX_AGENTS,
                "AI_PROVIDER": AI_PROVIDER,
                "AI_SLOT": AI_SLOT,
                "NVIDIA_MODEL": NVIDIA_MODEL,
                "NVIDIA_BASE_URL": NVIDIA_BASE_URL,
                "GROQ_MODEL": GROQ_MODEL,
                "GROQ_BASE_URL": GROQ_BASE_URL,
                "MAX_ACTIONS": MAX_ACTIONS,
                "MAX_CONTENT_SIZE": MAX_CONTENT_SIZE,
                "MAX_FEEDBACK_ATTEMPTS": "unlimited",
                "API_KEY_SET": bool(API_KEY),
                "NVIDIA_API_KEY_SET": bool(NVIDIA_API_KEY),
                "GROQ_API_KEY_SET": bool(GROQ_API_KEY),
                "PROVIDERS": PROVIDER_REGISTRY.public_status()
            })

        else:
            self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        global API_KEY, WORKER_MODE, AI_PROVIDER, AI_SLOT, NVIDIA_API_KEY, NVIDIA_MODEL, NVIDIA_BASE_URL
        global GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL
        parsed = self.path.split("?")[0]

        if not self._check_auth():
            self._json(401, {"ok": False, "error": "Invalid API key"})
            return

        # POST /execute — compatibilité : réponse après la fin des actions
        # POST /execute_async — réponse immédiate, logs et résultat via request_id
        if parsed in ("/execute", "/execute_async"):
            data, err = self._read_body()
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            ok, err = validate_request(data)
            if not ok:
                self._json(400, {"ok": False, "error": err})
                return
            if parsed == "/execute_async":
                request_id = start_direct_request(data)
                self._json(202, {"version": 1, "ok": True, "request_id": request_id, "status": "queued"})
            else:
                request_id = str(uuid.uuid4())[:8]

                log_activity("RECEIVE", f"Nouveau prompt reçu (ID: {request_id})")
                self._json(200, execute_direct_request(data, request_id))
            return

        # POST /prompt — une demande langage naturel, traitée par un seul cycle IA
        if parsed == "/prompt":
            data, err = self._read_body()
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            valid, err = validate_prompt_request(data)
            if not valid:
                self._json(400, {"ok": False, "error": err})
                return
            available, reason = worker_available()
            if not available:
                self._json(503, {"ok": False, "error": "Aucun worker IA disponible : {}".format(reason)})
                return
            pid = add_prompt(data["prompt"].strip(), data.get("system_prompt", ""), data.get("cwd", ""))
            self._json(202, {"ok": True, "id": pid, "status": "queued", "worker": WORKER_MODE, "cycles_max": 1})
            return

        # POST /submit_response — Tampermonkey submits LLM response
        if parsed == "/submit_response":
            data, err = self._read_body()
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            pid = data.get("id", "")
            response_text = data.get("response", "")
            if not pid or not response_text:
                self._json(400, {"ok": False, "error": "Missing 'id' or 'response'"})
                return
            ok, msg = submit_llm_response(pid, response_text)
            self._json(200, {"ok": ok, "message": msg})
            return

        # POST /confirm/<id> — décision utilisateur reçue par le CLI
        if parsed.startswith("/confirm/"):
            rid = parsed.split("/confirm/")[1]
            data, err = self._read_body()
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            approved = data.get("approved") if isinstance(data, dict) else None
            if not isinstance(approved, bool):
                self._json(400, {"ok": False, "error": "approved doit être un booléen"})
                return
            ok, message = submit_confirmation(rid, approved)
            self._json(200 if ok else 404, {"ok": ok, "message": message})
            return

        # POST /input/<id> — send input to interactive process
        if parsed.startswith("/input/"):
            rid = parsed.split("/input/")[1]
            data, err = self._read_body()
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            input_text = data.get("input", "")
            with active_processes_lock:
                proc = active_processes.get(rid)
            if not proc or proc["process"].poll() is not None:
                self._json(400, {"ok": False, "error": "No active process for this request"})
                return
            try:
                os.write(proc["input_fd"], (input_text + "\n").encode("utf-8"))
                self._json(200, {"ok": True, "sent": True})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return

        # POST /signal/<id> — send signal to process
        if parsed.startswith("/signal/"):
            rid = parsed.split("/signal/")[1]
            data, err = self._read_body()
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            signal_name = data.get("signal", "SIGTERM")
            with active_processes_lock:
                proc = active_processes.get(rid)
            if not proc:
                self._json(400, {"ok": False, "error": "No active process"})
                return
            process = proc["process"]
            try:
                if signal_name == "SIGINT":
                    os.killpg(os.getpgid(process.pid), signal.SIGINT)
                elif signal_name == "EOF":
                    os.close(proc["input_fd"])
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                self._json(200, {"ok": True, "signal": signal_name})
            except OSError as exc:
                self._json(500, {"ok": False, "error": str(exc)})
            return

        # POST /config — update configuration
        if parsed == "/config":
            data, err = self._read_body()
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            changed = []
            env_path = os.path.join(BASE_DIR, ".env")
            allowed = ["AI_PROVIDER", "NVIDIA_API_KEY", "NVIDIA_MODEL", "NVIDIA_BASE_URL", "GROQ_API_KEY", "GROQ_MODEL", "GROQ_BASE_URL", "FIREWORKS_API_KEY_1", "FIREWORKS_API_KEY_2", "FIREWORKS_MODEL_1", "FIREWORKS_MODEL_2", "COHERE_API_KEY_1", "COHERE_API_KEY_2", "COHERE_MODEL_1", "COHERE_MODEL_2", "GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_MODEL_1", "GROQ_MODEL_2", "NVIDIA_API_KEY_1", "NVIDIA_API_KEY_2", "NVIDIA_MODEL_1", "NVIDIA_MODEL_2", "GEMINI_MODEL_1", "GEMINI_MODEL_2", "NEMAPI_ENABLED", "NEMAPI_MODEL", "AI_SLOT", "API_KEY", "WORKER_MODE", "MAX_FEEDBACK_ATTEMPTS"]
            removable = {"API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY", "GROQ_API_KEY_1", "GROQ_API_KEY_2", "NVIDIA_API_KEY_1", "NVIDIA_API_KEY_2", "FIREWORKS_API_KEY_1", "FIREWORKS_API_KEY_2", "COHERE_API_KEY_1", "COHERE_API_KEY_2"}
            remove_keys = data.get("remove_keys", [])
            if not isinstance(remove_keys, list) or any(key not in removable for key in remove_keys):
                self._json(400, {"ok": False, "error": "remove_keys contient une clé non autorisée"})
                return
            if remove_keys:
                for key in remove_keys:
                    os.environ.pop(key, None)
                    if key == "API_KEY": API_KEY = ""
                    elif key == "GROQ_API_KEY": GROQ_API_KEY = ""
                    elif key == "NVIDIA_API_KEY": NVIDIA_API_KEY = ""
                _save_env(env_path)
                self._json(200, {"ok": True, "removed": remove_keys})
                return
            if "AI_PROVIDER" in data and str(data["AI_PROVIDER"]).lower() not in ("nvidia", "groq", "fireworks", "cohere", "gemini", "nemapi"): 
                self._json(400, {"ok": False, "error": "AI_PROVIDER doit être nvidia, groq, fireworks, cohere, gemini ou nemapi"})
                return
            if "AI_SLOT" in data and str(data["AI_SLOT"]) not in ("1", "2"):
                self._json(400, {"ok": False, "error": "AI_SLOT doit être 1 ou 2"})
                return
            if "WORKER_MODE" in data and str(data["WORKER_MODE"]).lower() not in ("api", "tampermonkey"):
                self._json(400, {"ok": False, "error": "WORKER_MODE doit être api ou tampermonkey"})
                return
            for key in allowed:
                if key in data and data[key] != "":
                    value = str(data[key]).strip()
                    os.environ[key] = value
                    changed.append(key)
                    if key == "AI_PROVIDER": AI_PROVIDER = value.lower()
                    elif key == "AI_SLOT": AI_SLOT = value
                    elif key == "NVIDIA_API_KEY": NVIDIA_API_KEY = value
                    elif key == "NVIDIA_MODEL": NVIDIA_MODEL = value
                    elif key == "NVIDIA_BASE_URL": NVIDIA_BASE_URL = value.rstrip("/")
                    elif key == "GROQ_API_KEY": GROQ_API_KEY = value
                    elif key == "GROQ_MODEL": GROQ_MODEL = value
                    elif key == "GROQ_BASE_URL": GROQ_BASE_URL = value.rstrip("/")
                    elif key == "API_KEY": API_KEY = value
                    elif key == "WORKER_MODE": WORKER_MODE = value.lower()
            if changed:
                try:
                    _save_env(env_path)
                    ensure_api_worker()
                    print("  [CONFIG] Mise a jour: {}".format(", ".join(changed)))
                except Exception as e:
                    self._json(500, {"ok": False, "error": str(e)})
                    return
            self._json(200, {"ok": True, "changed": changed})
            return

        self._json(404, {"ok": False, "error": "Not found"})

# ═══════════════════════════════════════════════════
# ADMIN WEB UI
# ═══════════════════════════════════════════════════
ADMIN_HTML = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Astarte BAM — Console</title>
<style>
:root{--bg:#09111f;--surface:#101c30;--surface2:#152640;--line:#263c5f;--text:#e8f0ff;--muted:#91a4c4;--accent:#55a8ff;--good:#47d7a4;--bad:#ff7185;--warn:#ffcb66}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}.app{min-height:100vh;display:grid;grid-template-columns:250px 1fr}.side{background:#0c1729;border-right:1px solid var(--line);padding:22px 14px;display:flex;flex-direction:column;gap:20px}.brand{padding:0 9px;font-weight:800;letter-spacing:.06em}.brand span{color:var(--accent)}.subtitle{font-size:11px;color:var(--muted);margin-top:5px}.nav{display:grid;gap:5px}.nav button{background:transparent;color:var(--muted);border:0;border-radius:8px;padding:10px 12px;text-align:left;font:inherit;cursor:pointer}.nav button:hover,.nav button.active{color:#fff;background:var(--surface2)}.sidefooter{margin-top:auto;color:var(--muted);font-size:12px;padding:9px}.main{min-width:0;padding:28px;max-width:1450px;width:100%;margin:auto}.top{display:flex;justify-content:space-between;gap:18px;align-items:center;margin-bottom:26px}.top h1{font-size:23px;margin:0}.top p{margin:5px 0 0;color:var(--muted)}.status{border:1px solid var(--line);border-radius:999px;padding:7px 11px;color:var(--muted);font-size:12px}.status.online{color:var(--good);border-color:#277c65}.status.offline{color:var(--bad);border-color:#914454}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card,.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px}.card{padding:16px}.label{color:var(--muted);font-size:12px}.metric{font-size:22px;font-weight:750;margin-top:7px}.panel{margin-top:16px;padding:18px}.panelhead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}.panel h2{font-size:15px;margin:0}.hidden{display:none}.compose{display:grid;gap:10px}textarea,input{width:100%;background:#091526;border:1px solid var(--line);border-radius:9px;color:var(--text);font:inherit;padding:12px}textarea{min-height:130px;resize:vertical}.actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.actions .hint{color:var(--muted);font-size:12px;margin-right:auto}button{font:inherit}button.primary,button.secondary{border:0;border-radius:8px;padding:9px 13px;cursor:pointer;font-weight:650}button.primary{background:var(--accent);color:#07111f}button.secondary{background:var(--surface2);color:var(--text);border:1px solid var(--line)}button:hover{filter:brightness(1.1)}.log{background:#081322;border:1px solid var(--line);border-radius:9px;min-height:190px;max-height:410px;overflow:auto;padding:10px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;white-space:pre-wrap}.entry{padding:7px 4px;border-bottom:1px solid #1a2b45}.entry:last-child{border:0}.entry.ok{color:var(--good)}.entry.err{color:var(--bad)}.entry.info{color:#b8c8e8}.row{display:flex;gap:10px;align-items:center}.row input{flex:1}.module{padding:11px;border:1px solid var(--line);border-radius:9px;margin:8px 0}.module b{display:block}.module span{color:var(--muted);font-size:12px}@media(max-width:760px){.app{display:block}.side{padding:14px;gap:10px;border-bottom:1px solid var(--line)}.nav{display:flex;overflow:auto}.sidefooter{display:none}.main{padding:18px}.grid{grid-template-columns:repeat(2,1fr)}.top{align-items:flex-start;flex-direction:column}}
</style></head><body><div class="app"><aside class="side"><div class="brand">ASTARTE <span>BAM</span><div class="subtitle">Console de contrôle · v6</div></div><nav class="nav"><button class="active" data-page="dashboard">Tableau de bord</button><button data-page="modules">Modules</button><button data-page="queue">File d’attente</button><button data-page="settings">Connexion</button></nav><div class="sidefooter" id="foot">Initialisation…</div></aside><main class="main"><header class="top"><div><h1 id="title">Tableau de bord</h1><p id="description">Suivez le serveur et envoyez une demande à l’assistant.</p></div><div class="status" id="status">● Vérification…</div></header>
<section id="dashboard" class="page"><div class="grid"><div class="card"><div class="label">État serveur</div><div class="metric" id="serverState">—</div></div><div class="card"><div class="label">Modules disponibles</div><div class="metric" id="moduleCount">—</div></div><div class="card"><div class="label">Mode IA</div><div class="metric" id="workerMode">—</div></div><div class="card"><div class="label">API</div><div class="metric" id="apiAddress">—</div></div></div><div class="panel"><div class="panelhead"><h2>Nouvelle demande</h2><button class="secondary" id="clearPrompt">Effacer</button></div><div class="compose"><textarea id="prompt" placeholder="Décrivez la tâche à réaliser…"></textarea><div class="actions"><span class="hint">Entrée pour envoyer · Maj+Entrée pour une nouvelle ligne</span><button class="secondary" id="jsonMode">Exécuter du JSON</button><button class="primary" id="send">Envoyer la demande</button></div></div></div><div class="panel"><div class="panelhead"><h2>Activité</h2><button class="secondary" id="clearLog">Vider</button></div><div class="log" id="log" aria-live="polite"></div></div></section>
<section id="modules" class="page hidden"><div class="panel"><div class="panelhead"><h2>Modules chargés</h2><button class="secondary" id="refreshModules">Actualiser</button></div><div id="moduleList">Chargement…</div></div></section><section id="queue" class="page hidden"><div class="panel"><div class="panelhead"><h2>File d’attente</h2><button class="secondary" id="refreshQueue">Actualiser</button></div><div class="log" id="queueList">Chargement…</div></div></section><section id="settings" class="page hidden"><div class="panel"><div class="panelhead"><h2>Connexion à l’API</h2></div><p class="label">La clé est conservée uniquement dans le stockage local de votre navigateur.</p><div class="compose" style="margin-top:14px"><label>Adresse de l’API <input id="apiUrl" placeholder="http://127.0.0.1:8765"></label><label>Clé API (facultatif si le serveur est local sans clé) <input id="apiKey" type="password" placeholder="X-API-Key"></label><div class="actions"><button class="primary" id="saveSettings">Enregistrer et tester</button></div></div></div></section>
</main></div><script>
const state={api:localStorage.getItem('astarte.api')||'http://127.0.0.1:8765',key:localStorage.getItem('astarte.key')||'',current:''};const $=s=>document.querySelector(s);const titles={dashboard:['Tableau de bord','Suivez le serveur et envoyez une demande à l’assistant.'],modules:['Modules','Fonctions installées sur le serveur.'],queue:['File d’attente','Demandes actuellement traitées ou en attente.'],settings:['Connexion','Configurez l’accès à votre API Astarte BAM.']};
function headers(){let h={'Content-Type':'application/json'};if(state.key)h['X-API-Key']=state.key;return h}async function request(path,opt={}){let r=await fetch(state.api+path,{...opt,headers:{...headers(),...(opt.headers||{})}});let d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.error||('Erreur HTTP '+r.status));return d}function log(text,type='info'){let e=document.createElement('div');e.className='entry '+type;e.textContent='['+new Date().toLocaleTimeString()+'] '+text;$('#log').append(e);$('#log').scrollTop=$('#log').scrollHeight}function setOnline(on){let x=$('#status');x.textContent=on?'● Connecté':'● Hors ligne';x.className='status '+(on?'online':'offline');$('#serverState').textContent=on?'En ligne':'Hors ligne'}
async function ping(){try{let d=await request('/ping',{headers:{}});setOnline(true);$('#moduleCount').textContent=d.modules_count??'—';$('#workerMode').textContent=d.worker_mode||'—';$('#apiAddress').textContent=(new URL(state.api)).host;$('#foot').textContent='API · '+state.api;return d}catch(e){setOnline(false);$('#foot').textContent=e.message;return null}}
async function modules(){let d=await request('/modules',{headers:{}}), box=$('#moduleList');box.innerHTML='';(d.modules||[]).forEach(m=>{let x=document.createElement('div');x.className='module';x.innerHTML='<b></b><span></span>';x.querySelector('b').textContent=m.name;x.querySelector('span').textContent=m.description||'Aucune description';box.append(x)});if(!d.modules?.length)box.textContent='Aucun module trouvé.'}async function queue(){let d=await request('/queue',{headers:{}});$('#queueList').textContent=(d.queue||[]).length?d.queue.map(x=>'['+x.status+'] '+x.id+' — '+x.prompt).join('\n'):'Aucune demande en attente.'}
async function follow(id){let after=-1;log('Demande '+id+' envoyée.','info');while(true){try{let d=await request('/logs/'+id+'?after='+after+'&timeout=25',{headers:{}});for(const x of d.logs||[]){after=Math.max(after,x.log_index||-1);log('['+(x.action_type||'?')+'] '+(x.message||x.status||''),x.status==='success'?'ok':x.status==='error'?'err':'info')}if(d.more===false)break}catch(e){log(e.message,'err');break}}let r=await request('/result/'+id,{headers:{}}).catch(e=>({error:e.message}));log('Terminé : '+(r.status||r.error||'inconnu'),r.status==='done'?'ok':'info')}
async function send(json=false){let text=$('#prompt').value.trim();if(!text)return;try{let data;if(json){data=JSON.parse(text);let r=await request('/execute',{method:'POST',body:JSON.stringify(data)});log(JSON.stringify(r,null,2),r.status==='success'?'ok':'info')}else{let r=await request('/prompt',{method:'POST',body:JSON.stringify({prompt:text})});$('#prompt').value='';follow(r.id)}}catch(e){log(e.message,'err')}}
function page(name){document.querySelectorAll('.page').forEach(x=>x.classList.add('hidden'));$('#'+name).classList.remove('hidden');document.querySelectorAll('.nav button').forEach(x=>x.classList.toggle('active',x.dataset.page===name));$('#title').textContent=titles[name][0];$('#description').textContent=titles[name][1];if(name==='modules')modules().catch(e=>$('#moduleList').textContent=e.message);if(name==='queue')queue().catch(e=>$('#queueList').textContent=e.message)}
document.querySelectorAll('.nav button').forEach(x=>x.onclick=()=>page(x.dataset.page));$('#send').onclick=()=>send(false);$('#jsonMode').onclick=()=>send(true);$('#clearPrompt').onclick=()=>$('#prompt').value='';$('#clearLog').onclick=()=>$('#log').innerHTML='';$('#refreshModules').onclick=()=>modules();$('#refreshQueue').onclick=()=>queue();$('#saveSettings').onclick=()=>{state.api=$('#apiUrl').value.trim().replace(/\/$/,'')||state.api;state.key=$('#apiKey').value;localStorage.setItem('astarte.api',state.api);localStorage.setItem('astarte.key',state.key);ping()};$('#prompt').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(false)}});$('#apiUrl').value=state.api;$('#apiKey').value=state.key;ping();
</script></body></html>"""

class AdminHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    def do_GET(self):
        parsed = self.path.split("?")[0]
        if parsed in ("/", "/index.html"):
            body = ADMIN_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

# ═══════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════
def print_startup_summary():
    print("=" * 60)
    print("  {} v{} — Serveur API".format(APP_NAME, APP_VERSION))
    print("=" * 60)
    print("  API      : http://{}:{}".format(HOST, PORT))
    print("  Admin    : http://{}:{}".format(ADMIN_HOST, ADMIN_PORT))
    print("  Workspace: {}".format(WORKSPACE))
    print("  Modules  : {}".format(len(discover_modules())))
    print("  Worker   : {}".format(WORKER_MODE))
    print("  Commandes: politique {}".format(COMMAND_POLICY))
    print("  Mode IA  : {}".format(ORCHESTRATION_MODE))
    if WORKER_MODE == "api":
        print("  Modèle   : {} / slot {}".format(AI_PROVIDER, AI_SLOT))
    print("  Execution: sans limite de temps")
    print("  Feedback : illimité (fin avec actions: [])")
    print("  Python   : {}.{}".format(sys.version_info[0], sys.version_info[1]))
    print("  Auth     : {}".format("ON" if API_KEY else "OFF"))
    if not ENV_FILE_FOUND:
        print("  [CONFIG] Aucun .env : valeurs par défaut utilisées.")
    if not API_KEY:
        print("  [SECURITE] API_KEY est vide : les requêtes POST ne sont pas authentifiées.")
    if not is_local_host(HOST):
        print("  [SECURITE] API exposée sur {}. Définissez une API_KEY robuste.".format(HOST))
    if not is_local_host(ADMIN_HOST):
        print("  [SECURITE] Interface admin exposée sur {}.".format(ADMIN_HOST))
    print("=" * 60)

def run_api_server():
    try:
        server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    except OSError as exc:
        print("[DEMARRAGE] Impossible d’ouvrir l’API {}:{} : {}".format(HOST, PORT, exc), file=sys.stderr)
        raise SystemExit(1)
    print_startup_summary()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArret du serveur API.")
    finally:
        server.server_close()

def run_admin_server():
    try:
        server = ThreadingHTTPServer((ADMIN_HOST, ADMIN_PORT), AdminHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print("[DEMARRAGE] Interface admin indisponible sur {}:{} : {}".format(ADMIN_HOST, ADMIN_PORT, exc), file=sys.stderr)
    finally:
        try:
            server.server_close()
        except UnboundLocalError:
            pass

if __name__ == "__main__":
    mods = discover_modules()
    print("\n  Modules charges: {}".format(len(mods)))
    for name in sorted(mods.keys()):
        print("    - /{}".format(name))
    print()

    # Cleanup stale prompts
    with prompt_queue_lock:
        for entry in prompt_queue:
            if entry["status"] == "processing":
                entry["status"] = "pending"
                print("  Cleanup: prompt {} remis en pending.".format(entry["id"]))

    if WORKER_MODE == "api":
        ensure_api_worker()
    elif WORKER_MODE == "tampermonkey":
        print("\n  Pages disponibles (NEMESIS):")
        pages = ["chat_deepseek_com", "chat_qwen_ai", "www_kimi_com"]
        for i, p in enumerate(pages, 1):
            print("    {}. {}".format(i, p))
        try:
            choix = input("  Choix (1-{}) [defaut: 1]: ".format(len(pages))).strip()
            idx = int(choix) - 1 if choix.isdigit() and 1 <= int(choix) <= len(pages) else 0
            NEMESIS_MODEL = pages[idx]
        except (EOFError, KeyboardInterrupt):
            NEMESIS_MODEL = pages[0]
        print("  Page selectionnee: {}".format(NEMESIS_MODEL))
        os.environ["NEMESIS_MODEL"] = NEMESIS_MODEL
        worker_thread = threading.Thread(target=worker_loop, daemon=True)
        worker_thread.start()
        print("  Worker Tampermonkey thread demarre.")

    admin_thread = threading.Thread(target=run_admin_server, daemon=True)
    admin_thread.start()

    watcher_thread = threading.Thread(target=file_watcher_loop, daemon=True)
    watcher_thread.start()
    print("  Watcher: surveillance des fichiers active.")

    run_api_server()
