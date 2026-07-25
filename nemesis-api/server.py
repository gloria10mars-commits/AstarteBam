"""
NEMESIS API v1.5.4 - Serveur local de gestion des xdotool par page
Communication avec Tampermonkey via polling HTTP

Ameliorations v1.5:
- P0: wrapper xdotool (plus de crash), worker unique par page (FIFO),
     restauration du presse-papier
- P1: polling bing 500ms (latence reelle), cache geometry fenetre
- P2: endpoints OpenAI-compatible (/v1/chat/completions), cancel,
     metrics, health
- Persistance: configs.json sur disque (survit aux redemarrages)
- Auto-registration: Tampermonkey re-POST la config sauvee au chargement

v1.5.2:
- Compatibilite explicite 32-bit (i386, armhf) et 64-bit (amd64, arm64)
- Detection architecture dans /health et au demarrage

v1.5.3:
- PEP 668: venv local automatique + wrappers run-*.sh
- auto_test.sh et client.py utilisent le venv local

v1.5.4 (HP Pavilion dv1000 / Pentium M):
- Timeout auto-start 15s -> 45s (hardware ancien lent)
- Rotation logs reduite: 1MB x 2 (au lieu de 5MB x 5)
- /health retourne aussi get_memory_info()
- install.sh detecte hardware ancien et installe MarkupSafe en Python pur
  (les wheels C Pentium M sans SSE3 peuvent rater)
- Messages d'avertissement patient pour demarrage lent
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import subprocess
import threading
import time
import queue
import json
import os
import uuid
import platform
import struct
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("nemesis")
logger.setLevel(logging.INFO)
# Rotation reduite (1MB x 2) pour economiser disque sur hardware ancien
_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "nemesis.log"),
    maxBytes=1 * 1024 * 1024, backupCount=2
)
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"
))
logger.addHandler(_handler)
# aussi stdout
logger.addHandler(logging.StreamHandler())

# ---------------------------------------------------------------------------
# Etat global
# ---------------------------------------------------------------------------
CONFIGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs.json")

# File d'attente par page_id (FIFO)
page_queues: dict[str, queue.Queue] = {}
# Worker vivant par page_id
page_workers: dict[str, threading.Thread] = {}
# Resultats par task_id
page_results: dict[str, dict] = {}
# Configurations sauvegardees par page_id (persistantes)
saved_configs: dict[str, dict] = {}
# Lock global
lock = threading.Lock()
# Tasks annulees
cancelled_tasks: set[str] = set()
# Metriques
metrics = {
    "total_requests": 0,
    "total_success": 0,
    "total_errors": 0,
    "per_page": {},  # page_id -> {requests, success, errors, total_ms}
    "started_at": datetime.now(timezone.utc).isoformat(),
}

WINDOW_ID = None  # ID de la fenetre navigateur ciblee
_geometry_cache = {"window_id": None, "ts": 0, "value": None}


# ---------------------------------------------------------------------------
# Persistance des configs
# ---------------------------------------------------------------------------
def save_configs_to_disk():
    """Sauvegarde saved_configs vers configs.json"""
    try:
        with open(CONFIGS_FILE, "w", encoding="utf-8") as f:
            json.dump(saved_configs, f, ensure_ascii=False, indent=2)
        logger.info(f"[save_configs] {len(saved_configs)} configs sauvegardees")
    except Exception as e:
        logger.error(f"[save_configs] erreur: {e}")


def load_configs_from_disk():
    """Charge configs.json vers saved_configs au demarrage"""
    global saved_configs
    if os.path.exists(CONFIGS_FILE):
        try:
            with open(CONFIGS_FILE, "r", encoding="utf-8") as f:
                saved_configs = json.load(f)
            logger.info(f"[load_configs] {len(saved_configs)} configs chargees: {list(saved_configs.keys())}")
        except Exception as e:
            logger.error(f"[load_configs] erreur: {e}")
            saved_configs = {}


load_configs_from_disk()


# ---------------------------------------------------------------------------
# Detection architecture (compatibilite 32-bit / 64-bit)
# ---------------------------------------------------------------------------
def get_arch_info() -> dict:
    """Retourne les infos d'architecture pour diagnostic"""
    bits = struct.calcsize("P") * 8  # 32 ou 64
    return {
        "machine": platform.machine(),
        "processor": platform.processor() or "inconnu",
        "python_bits": bits,
        "python_version": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "is_32bit": bits == 32,
        "is_64bit": bits == 64,
    }


def get_memory_info() -> dict:
    """Retourne les infos memoire (utile pour hardware ancien)"""
    info = {"total_mb": 0, "available_mb": 0, "used_percent": 0}
    try:
        # Lecture de /proc/meminfo (Linux)
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = int(parts[1].strip().split()[0])
                    mem[key] = val
            total_kb = mem.get("MemTotal", 0)
            avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
            info["total_mb"] = total_kb // 1024
            info["available_mb"] = avail_kb // 1024
            if total_kb > 0:
                info["used_percent"] = round(100 * (1 - avail_kb / total_kb), 1)
    except Exception:
        pass
    return info


def get_arch_label() -> str:
    info = get_arch_info()
    return f"{info['machine']} ({info['python_bits']}-bit, Python {info['python_version']})"


# ---------------------------------------------------------------------------
# Wrapper xdotool / xclip robuste (P0d)
# ---------------------------------------------------------------------------
def _run(cmd: list[str], timeout: int = 5, input_data: bytes = None) -> subprocess.CompletedProcess | None:
    """Wrapper robuste pour subprocess.run - retourne None au lieu de crasher"""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=False,
            timeout=timeout, input=input_data
        )
    except FileNotFoundError:
        logger.warning(f"[subprocess] binaire absent: {cmd[0]}")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"[subprocess] timeout: {cmd}")
        return None
    except Exception as e:
        logger.warning(f"[subprocess] erreur {cmd}: {e}")
        return None


def xdotool(*args, timeout=5):
    """Appel xdotool robuste. Retourne CompletedProcess ou None."""
    return _run(["xdotool"] + list(args), timeout=timeout)


def xclip_copy(text: str) -> bool:
    """Copie du texte dans le presse-papier X CLIPBOARD via fichier temporaire"""
    import tempfile
    try:
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        tmp.write(text)
        tmp.close()
        r = _run(["xclip", "-selection", "c", "-i", tmp.name], timeout=5)
        os.unlink(tmp.name)
        return r is not None and r.returncode == 0
    except Exception as e:
        logger.error(f"[xclip_copy] Erreur: {e}")
        return False


def xclip_paste() -> str:
    """Recupere le contenu du presse-papier X CLIPBOARD"""
    r = _run(["xclip", "-selection", "c", "-o"], timeout=5)
    if r is None or r.returncode != 0:
        return ""
    try:
        return r.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Helpers navigateur
# ---------------------------------------------------------------------------
def get_window_id():
    """Recupere l'ID de la fenetre active du navigateur (cherche Firefox, Chrome, Brave, Chromium)"""
    global WINDOW_ID
    if WINDOW_ID:
        check = xdotool("getwindowname", str(WINDOW_ID), timeout=3)
        if check and check.returncode == 0 and check.stdout.strip():
            return WINDOW_ID
        else:
            WINDOW_ID = None

    browsers = ["firefox", "chrome", "brave", "chromium", "Google-chrome", "Brave-browser"]
    for browser in browsers:
        result = xdotool("search", "--onlyvisible", "--class", browser, timeout=3)
        if not result:
            continue
        ids = result.stdout.decode(errors="replace").strip().split('\n') if result.stdout else []
        if ids and ids[0]:
            WINDOW_ID = ids[0]
            name_r = xdotool("getwindowname", str(WINDOW_ID), timeout=3)
            name = name_r.stdout.decode(errors="replace").strip() if name_r and name_r.stdout else ""
            logger.info(f"[window] Fenetre trouvee: {name[:60]} (ID: {WINDOW_ID})")
            return WINDOW_ID

    logger.warning("[window] Aucune fenetre de navigateur trouvee!")
    return None


def get_window_geometry(window_id):
    """Recupere la position + taille de la fenetre (avec cache 30s) (P1c)"""
    now = time.time()
    if (_geometry_cache["window_id"] == window_id
            and _geometry_cache["value"]
            and now - _geometry_cache["ts"] < 30):
        return _geometry_cache["value"]

    result = xdotool("getwindowgeometry", str(window_id), timeout=3)
    if not result or result.returncode != 0:
        return None
    stdout = result.stdout.decode(errors="replace")
    lines = stdout.strip().split('\n')
    try:
        pos_line = [l for l in lines if 'Position' in l][0]
        geo_line = [l for l in lines if 'Geometry' in l][0]
        pos_part = pos_line.split(':')[1].strip().split(' ')[0]
        x = int(pos_part.split(',')[0])
        y = int(pos_part.split(',')[1])
        geo_part = geo_line.split(':')[1].strip()
        w = int(geo_part.split('x')[0])
        h = int(geo_part.split('x')[1])
        geo = (x, y, w, h)
        _geometry_cache["window_id"] = window_id
        _geometry_cache["ts"] = now
        _geometry_cache["value"] = geo
        return geo
    except (IndexError, ValueError) as e:
        logger.warning(f"[geometry] parse erreur: {e}")
        return None


def xdotool_click(window_id, rel_x, rel_y, y_offset=100):
    """Clique a une position relative"""
    geo = get_window_geometry(window_id)
    if not geo:
        logger.warning("[click] geometry indisponible")
        return False
    abs_x, abs_y, w, h = geo
    abs_click_x = abs_x + rel_x
    abs_click_y = abs_y + rel_y + y_offset
    logger.info(f"[click] Absolu: {abs_click_x},{abs_click_y}")
    r = xdotool("mousemove", "--clearmodifiers", str(abs_click_x), str(abs_click_y),
                "click", "1", timeout=3)
    time.sleep(0.1)
    return r is not None and r.returncode == 0


def xdotool_type(window_id, text):
    """Colle du texte via Ctrl+V direct. Le prompt doit etre dans le presse-papier."""
    logger.info(f"[type] Collage: {text[:50]}...")
    wa = xdotool("windowactivate", "--sync", str(window_id), timeout=3)
    time.sleep(0.1)
    xdotool("key", "--window", str(window_id), "ctrl+v", timeout=5)
    logger.info("[type] Collage OK")
    return True


def xdotool_copy(window_id):
    """Ctrl+C dans la fenetre + lecture xclip"""
    xdotool("windowactivate", "--sync", str(window_id), timeout=3)
    time.sleep(0.15)
    xdotool("key", "--window", str(window_id), "ctrl+c", timeout=5)
    time.sleep(0.3)
    return xclip_paste()


# ---------------------------------------------------------------------------
# Metriques
# ---------------------------------------------------------------------------
def record_metric(page_id: str, success: bool, latency_ms: float):
    with lock:
        metrics["total_requests"] += 1
        if success:
            metrics["total_success"] += 1
        else:
            metrics["total_errors"] += 1
        if page_id not in metrics["per_page"]:
            metrics["per_page"][page_id] = {
                "requests": 0, "success": 0, "errors": 0, "total_ms": 0
            }
        m = metrics["per_page"][page_id]
        m["requests"] += 1
        m["success"] += int(success)
        m["errors"] += int(not success)
        m["total_ms"] += latency_ms


# ---------------------------------------------------------------------------
# Execution d'une action
# ---------------------------------------------------------------------------
def execute_action(page_id, action_config, prompt, task_id):
    """
    Execute une sequence d'actions sur une page.
    Verifie l'annulation entre chaque etape (P2j).
    Verifie en priorite si un bing est arrive (P1a).
    """
    def is_cancelled():
        with lock:
            return task_id in cancelled_tasks

    def check_bing():
        """Retourne le resultat bing s'il est deja arrive, sinon None"""
        with lock:
            if task_id in page_results:
                return page_results.pop(task_id)
        return None

    start_time = time.time()
    logger.info(f"[execute] page={page_id} task={task_id} prompt={prompt[:50]!r}")

    # Annulation avant meme de commencer
    if is_cancelled():
        return {"success": False, "error": "cancelled"}

    window_id = get_window_id()
    if not window_id:
        record_metric(page_id, False, 0)
        return {"success": False, "error": "Fenetre navigateur non trouvee"}

    logger.info(f"[execute] Fenetre ID: {window_id}")

    try:
        # Etape 1: clic zone saisie
        if "input_click" in action_config and not is_cancelled():
            x, y = action_config["input_click"]
            logger.info(f"[execute] Clic saisie: {x},{y}")
            xdotool_click(window_id, x, y)
            time.sleep(0.5)

        # Etape 2: mettre le prompt dans le presse-papier puis Ctrl+V
        if prompt and not is_cancelled():
            logger.info(f"[execute] Collage prompt")
            # Ecrire dans fichier temporaire puis xclip (methode fiable)
            import tempfile
            tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
            tmp.write(prompt)
            tmp.close()
            _run(["xclip", "-selection", "c", "-i", tmp.name], timeout=5)
            os.unlink(tmp.name)
            time.sleep(0.1)
            if not xdotool_type(window_id, prompt):
                record_metric(page_id, False, (time.time() - start_time) * 1000)
                return {"success": False, "error": "Echec collage prompt"}
            time.sleep(0.3)

            # Verifier bing (Tampermonkey peut avoir detecte la saisie)
            bing = check_bing()
            if bing:
                record_metric(page_id, bing.get("success", True), (time.time() - start_time) * 1000)
                return bing

        # Etape 3: clic bouton envoyer
        if "send_click" in action_config and not is_cancelled():
            x, y = action_config["send_click"]
            logger.info(f"[execute] Clic send: {x},{y}")
            xdotool_click(window_id, x, y)
            time.sleep(0.5)

        # Etape 4: attendre reponse
        # Polling 500ms pendant max 30s, en priorite sur bing (P1a)
        # Fallback xdotool_copy tous les 5 essais (2.5s)
        if "copy_zone" in action_config:
            x, y = action_config["copy_zone"]
            max_loops = 240  # 120s max (pas de timeout)
            result_text = ""

            for i in range(max_loops):
                if is_cancelled():
                    record_metric(page_id, False, (time.time() - start_time) * 1000)
                    return {"success": False, "error": "cancelled"}

                # 1. Verifier bing d'abord (instantane)
                bing = check_bing()
                if bing is not None:
                    latency = (time.time() - start_time) * 1000
                    record_metric(page_id, bing.get("success", True), latency)
                    logger.info(f"[execute] bing recu apres {latency:.0f}ms")
                    return bing

                # 2. Fallback xdotool copy tous les 5 loops (~2.5s)
                if i > 0 and i % 5 == 0:
                    logger.info(f"[execute] Tentative copy {i // 5}/12...")
                    xdotool_click(window_id, x, y)
                    time.sleep(0.3)
                    result_text = xdotool_copy(window_id)
                    if result_text and result_text != prompt and len(result_text) > 2:
                        latency = (time.time() - start_time) * 1000
                        record_metric(page_id, True, latency)
                        logger.info(f"[execute] Reponse (xdotool) apres {latency:.0f}ms")
                        return {"success": True, "result": result_text}

                time.sleep(0.5)

            latency = (time.time() - start_time) * 1000
            record_metric(page_id, False, latency)
            return {"success": False, "error": "Timeout - pas de reponse apres 30s"}

        # Si pas de copy_zone definie, on attend juste un bing
        for i in range(60):
            if is_cancelled():
                record_metric(page_id, False, (time.time() - start_time) * 1000)
                return {"success": False, "error": "cancelled"}
            bing = check_bing()
            if bing is not None:
                latency = (time.time() - start_time) * 1000
                record_metric(page_id, bing.get("success", True), latency)
                return bing
            time.sleep(0.5)

        latency = (time.time() - start_time) * 1000
        record_metric(page_id, False, latency)
        return {"success": False, "error": "Timeout - pas de bing recu"}

    except Exception as e:
        logger.exception(f"[execute] EXCEPTION task={task_id}")
        record_metric(page_id, False, (time.time() - start_time) * 1000)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Worker persistant par page (P0e)
# ---------------------------------------------------------------------------
def page_worker_loop(page_id: str):
    """Boucle de consommation de la file pour une page. Un seul worker par page."""
    logger.info(f"[worker] Demarrage pour {page_id}")
    while True:
        try:
            task = page_queues[page_id].get(timeout=1.0)
        except queue.Empty:
            # Verifier si on doit s'arreter (plus de travail, on garde quand meme le worker vivant)
            continue
        except KeyError:
            # La queue a ete supprimee
            logger.info(f"[worker] Queue supprimee pour {page_id}, arret")
            return

        if task is None:
            # Signal d'arret
            logger.info(f"[worker] Signal d'arret pour {page_id}")
            return

        prompt = task["prompt"]
        action_config = task["config"]
        task_id = task["id"]

        logger.info(f"[worker] Execution tache {task_id} sur {page_id}")
        result = execute_action(page_id, action_config, prompt, task_id)

        # Stocker le resultat (sauf si deja consomme via bing)
        with lock:
            if task_id not in page_results and task_id not in cancelled_tasks:
                page_results[task_id] = result
            elif task_id in cancelled_tasks:
                logger.info(f"[worker] task {task_id} annulee, resultat ignore")

        # Marquer la tache comme faite dans la queue
        page_queues[page_id].task_done()


def ensure_worker(page_id: str):
    """Cree le worker pour une page s'il n'existe pas deja"""
    with lock:
        if page_id not in page_queues:
            page_queues[page_id] = queue.Queue()
        existing = page_workers.get(page_id)
        if existing is None or not existing.is_alive():
            t = threading.Thread(target=page_worker_loop, args=(page_id,), daemon=True)
            page_workers[page_id] = t
            t.start()
            logger.info(f"[ensure_worker] Worker cree pour {page_id}")


# ---------------------------------------------------------------------------
# Helpers conversion model -> page_id (P2h)
# ---------------------------------------------------------------------------
MODEL_TO_PAGE = {
    "deepseek": "chat_deepseek_com",
    "kimi": "kimi_moonshot_cn",
    "qwen": "chat_qwenlm_ai",
    "gemini": "gemini_google_com",
    # alias
    "chat_deepseek_com": "chat_deepseek_com",
    "kimi_moonshot_cn": "kimi_moonshot_cn",
    "chat_qwenlm_ai": "chat_qwenlm_ai",
    "gemini_google_com": "gemini_google_com",
}


def resolve_page_id(model_or_page: str | None, autodetect: bool = True) -> str | None:
    """Resout un model/page_id en verifiant qu'une config existe"""
    if model_or_page:
        pid = MODEL_TO_PAGE.get(model_or_page, model_or_page)
        if pid in saved_configs:
            return pid
        # pas de config sauvegardee mais page_id explicite -> OK quand meme
        # (Tampermonkey re-enregistrera au prochain chargement)
        return pid

    if not autodetect:
        return None

    # Auto-detection par titre de fenetre
    window_id = get_window_id()
    if not window_id:
        return None
    name_r = xdotool("getwindowname", str(window_id), timeout=3)
    name = name_r.stdout.decode(errors="replace").strip() if name_r and name_r.stdout else ""
    with lock:
        for pid in saved_configs:
            domain_part = pid.replace('_', '.').replace('www.', '')
            keywords = [kw for kw in domain_part.split('.') if len(kw) > 2]
            if any(kw.lower() in name.lower() for kw in keywords):
                logger.info(f"[resolve] Auto-detect: {pid} depuis '{name[:60]}'")
                return pid
    return None


# ---------------------------------------------------------------------------
# Endpoints v1 (compatibilite ascendante)
# ---------------------------------------------------------------------------
@app.route('/register_page', methods=['POST'])
def register_page():
    """Tampermonkey enregistre une page avec sa config"""
    data = request.json or {}
    page_id = data.get("page_id")
    config = data.get("config", {})

    if not page_id:
        return jsonify({"error": "page_id requis"}), 400

    with lock:
        if page_id not in page_queues:
            page_queues[page_id] = queue.Queue()
        if config and config.get("input_click"):
            saved_configs[page_id] = config
            logger.info(f"[register_page] Config sauvegardee pour {page_id}: {config}")
            save_configs_to_disk()

    return jsonify({
        "status": "ok",
        "page_id": page_id,
        "saved": page_id in saved_configs,
        "config": saved_configs.get(page_id)
    })


@app.route('/send_prompt', methods=['POST'])
def send_prompt():
    """Recoit un prompt - detecte auto le site si page_id non fourni (compat v1)"""
    data = request.json or {}
    page_id = data.get("page_id")
    prompt = data.get("prompt")
    config = data.get("config", {})
    task_id = data.get("task_id", f"task_{uuid.uuid4().hex[:12]}")

    if not prompt:
        return jsonify({"error": "prompt requis"}), 400

    if not page_id:
        page_id = resolve_page_id(None, autodetect=True)
        if not page_id:
            return jsonify({
                "error": "Aucun navigateur ou site non reconnu",
                "saved_pages": list(saved_configs.keys())
            }), 404

    if not config or not config.get("input_click"):
        with lock:
            if page_id in saved_configs:
                config = saved_configs[page_id]
            else:
                return jsonify({
                    "error": f"Aucune config pour {page_id}",
                    "saved_pages": list(saved_configs.keys())
                }), 400

    ensure_worker(page_id)

    with lock:
        if page_id not in page_queues:
            page_queues[page_id] = queue.Queue()
        task = {"id": task_id, "prompt": prompt, "config": config}
        page_queues[page_id].put(task)

    return jsonify({
        "status": "queued",
        "task_id": task_id,
        "page_id": page_id,
        "auto_detected": not data.get("page_id")
    })


@app.route('/get_result/<task_id>', methods=['GET'])
def get_result(task_id):
    """Recupere le resultat d'une tache (compat v1)"""
    with lock:
        if task_id in page_results:
            return jsonify(page_results.pop(task_id))
    return jsonify({"status": "pending"})


@app.route('/pages', methods=['GET'])
def list_pages():
    """Liste les pages enregistrees avec leurs configs"""
    with lock:
        return jsonify({
            "saved_configs": dict(saved_configs),
            "window_id": WINDOW_ID,
            "active_workers": list(page_workers.keys())
        })


@app.route('/current_page', methods=['GET'])
def current_page():
    """Detecte la page actuellement ouverte dans le navigateur"""
    window_id = get_window_id()
    if not window_id:
        return jsonify({"error": "Aucun navigateur trouve"}), 404

    name_r = xdotool("getwindowname", str(window_id), timeout=3)
    name = name_r.stdout.decode(errors="replace").strip() if name_r and name_r.stdout else ""

    detected = None
    with lock:
        for pid in saved_configs:
            domain_part = pid.replace('_', '.').replace('www.', '')
            if any(word.lower() in name.lower() for word in domain_part.split('.')):
                detected = pid
                break

    return jsonify({
        "window_name": name,
        "window_id": window_id,
        "detected_page": detected,
        "has_config": detected in saved_configs if detected else False
    })


@app.route('/bing/<page_id>', methods=['POST'])
def bing_notification(page_id):
    """Recoit une notification 'bing' de Tampermonkey (donnees copiees)"""
    data = request.json or {}
    content = data.get("content", "")
    task_id = data.get("task_id", "")
    success = data.get("success", True)

    if not task_id:
        return jsonify({"error": "task_id requis"}), 400

    with lock:
        page_results[task_id] = {
            "success": success,
            "result": content,
            "bing": True,
            "page_id": page_id
        }
    logger.info(f"[bing] task={task_id} page={page_id} len={len(content)}")

    # Son
    try:
        os.system("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || printf '\\a'")
    except Exception:
        pass

    return jsonify({"status": "bing_received", "task_id": task_id})


# ---------------------------------------------------------------------------
# Endpoints v2 (OpenAI-compatible + admin) - P2
# ---------------------------------------------------------------------------
@app.route('/v1/chat/completions', methods=['POST'])
def v1_chat_completions():
    """Endpoint compatible OpenAI Chat Completions"""
    data = request.json or {}
    model = data.get("model", "deepseek")
    messages = data.get("messages", [])
    stream = data.get("stream", False)

    if not messages:
        return jsonify({"error": {"message": "messages requis", "type": "invalid_request"}}), 400

    # Construire le prompt depuis les messages
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"[SYSTEM]: {content}")
        elif role == "user":
            parts.append(content)
        elif role == "assistant":
            parts.append(f"[ASSISTANT]: {content}")
    prompt = "\n\n".join(parts)

    page_id = resolve_page_id(model, autodetect=False)
    if not page_id:
        return jsonify({
            "error": {
                "message": f"Model/page '{model}' inconnu. Pages disponibles: {list(saved_configs.keys())}",
                "type": "invalid_request"
            }
        }), 400

    with lock:
        if page_id not in saved_configs:
            return jsonify({
                "error": {
                    "message": f"Page '{page_id}' non calibree. Ouvre-la dans le navigateur et calle 3 points.",
                    "type": "invalid_request"
                }
            }), 400
        config = saved_configs[page_id]

    task_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    ensure_worker(page_id)

    with lock:
        if page_id not in page_queues:
            page_queues[page_id] = queue.Queue()
        page_queues[page_id].put({"id": task_id, "prompt": prompt, "config": config})

    # Attendre le resultat (bloquant, max 60s)
    start = time.time()
    timeout = 60
    while time.time() - start < timeout:
        with lock:
            if task_id in page_results:
                result = page_results.pop(task_id)
                break
            if task_id in cancelled_tasks:
                cancelled_tasks.discard(task_id)
                return jsonify({"error": {"message": "cancelled", "type": "cancelled"}}), 499
        time.sleep(0.3)
    else:
        return jsonify({"error": {"message": "Timeout", "type": "timeout"}}), 504

    if not result.get("success"):
        return jsonify({
            "error": {"message": result.get("error", "unknown"), "type": "internal_error"}
        }), 502

    content = result.get("result", "")
    response = {
        "id": task_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }
    return jsonify(response)


@app.route('/v1/models', methods=['GET'])
def v1_models():
    """Liste les modeles disponibles (config sauvegardee = disponible)"""
    with lock:
        models = []
        for pid in saved_configs:
            # Recupere le nom court
            short = next((k for k, v in MODEL_TO_PAGE.items() if v == pid), pid)
            models.append({
                "id": short,
                "object": "model",
                "created": 0,
                "owned_by": "nemesis"
            })
    return jsonify({"object": "list", "data": models})


@app.route('/v1/tasks', methods=['POST'])
def v1_create_task():
    """Cree une tache asynchrone"""
    data = request.json or {}
    model = data.get("model", "deepseek")
    prompt = data.get("prompt")
    if not prompt:
        return jsonify({"error": "prompt requis"}), 400

    page_id = resolve_page_id(model, autodetect=False)
    if not page_id or page_id not in saved_configs:
        return jsonify({
            "error": f"Page '{model}' non calibree. Pages: {list(saved_configs.keys())}"
        }), 400

    with lock:
        config = saved_configs[page_id]

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    ensure_worker(page_id)
    with lock:
        page_queues.setdefault(page_id, queue.Queue()).put(
            {"id": task_id, "prompt": prompt, "config": config}
        )

    return jsonify({"task_id": task_id, "page_id": page_id, "status": "queued"})


@app.route('/v1/tasks/<task_id>', methods=['GET'])
def v1_get_task(task_id):
    """Statut d'une tache"""
    with lock:
        if task_id in page_results:
            return jsonify({"status": "done", "result": page_results.get(task_id)})
        if task_id in cancelled_tasks:
            return jsonify({"status": "cancelled"})
    return jsonify({"status": "pending"})


@app.route('/v1/tasks/<task_id>/result', methods=['GET'])
def v1_get_task_result(task_id):
    """Recupere le resultat (bloquant 30s max)"""
    start = time.time()
    while time.time() - start < 30:
        with lock:
            if task_id in page_results:
                return jsonify(page_results.pop(task_id))
            if task_id in cancelled_tasks:
                cancelled_tasks.discard(task_id)
                return jsonify({"success": False, "error": "cancelled"}), 499
        time.sleep(0.3)
    return jsonify({"status": "pending", "error": "timeout"}), 504


@app.route('/v1/tasks/<task_id>', methods=['DELETE'])
def v1_cancel_task(task_id):
    """Annule une tache (P2j)"""
    with lock:
        cancelled_tasks.add(task_id)
    logger.info(f"[cancel] task={task_id}")
    return jsonify({"status": "cancelled", "task_id": task_id})


@app.route('/v1/metrics', methods=['GET'])
def v1_metrics():
    """Metriques (P2k)"""
    with lock:
        per_page = {}
        for pid, m in metrics["per_page"].items():
            avg = m["total_ms"] / m["requests"] if m["requests"] else 0
            per_page[pid] = {
                "requests": m["requests"],
                "success": m["success"],
                "errors": m["errors"],
                "avg_latency_ms": round(avg, 1),
                "success_rate": m["success"] / m["requests"] if m["requests"] else 0
            }
        active = sum(1 for q in page_queues.values() if q.qsize() > 0)
        return jsonify({
            "total_requests": metrics["total_requests"],
            "total_success": metrics["total_success"],
            "total_errors": metrics["total_errors"],
            "success_rate": (metrics["total_success"] / metrics["total_requests"]
                             if metrics["total_requests"] else 0),
            "per_page": per_page,
            "active_tasks": active,
            "started_at": metrics["started_at"],
            "uptime_seconds": int(time.time() - datetime.fromisoformat(metrics["started_at"]).timestamp())
        })


@app.route('/health', methods=['GET'])
def health():
    """Health check (P2l) - avec info architecture 32/64-bit"""
    xdotool_ok = xdotool("--version", timeout=2) is not None
    xclip_ok = _run(["xclip", "-version"], timeout=2) is not None
    display = os.environ.get("DISPLAY", "")
    window_id = get_window_id()
    browser_name = ""
    if window_id:
        r = xdotool("getwindowname", str(window_id), timeout=2)
        if r and r.stdout:
            browser_name = r.stdout.decode(errors="replace").strip()

    return jsonify({
        "status": "ok" if (xdotool_ok and xclip_ok and display) else "degraded",
        "xdotool": xdotool_ok,
        "xclip": xclip_ok,
        "display": display,
        "connected_pages": list(saved_configs.keys()),
        "active_workers": list(page_workers.keys()),
        "browser_window_id": window_id,
        "browser_window_name": browser_name,
        "architecture": get_arch_info(),
        "memory": get_memory_info()
    })


@app.route('/', methods=['GET'])
def root():
    """Page d'accueil avec liens endpoints"""
    return jsonify({
        "name": "NEMESIS API",
        "version": "1.5",
        "endpoints": {
            "v1_compat": ["/register_page", "/send_prompt", "/get_result/<id>",
                          "/pages", "/current_page", "/bing/<page_id>"],
            "v2_openai": ["/v1/chat/completions", "/v1/models", "/v1/tasks",
                          "/v1/tasks/<id>", "/v1/tasks/<id>/result"],
            "admin": ["/health", "/v1/metrics"]
        },
        "saved_pages": list(saved_configs.keys())
    })


if __name__ == '__main__':
    print("=" * 60)
    print("  NEMESIS API v1.5.4")
    print("  http://localhost:5000")
    print("=" * 60)
    print(f"  Architecture: {get_arch_label()}")
    mem = get_memory_info()
    print(f"  Memoire: {mem['available_mb']} MB dispo / {mem['total_mb']} MB total")
    print(f"  Pages calibrees: {list(saved_configs.keys())}")
    print(f"  Logs: {os.path.join(LOG_DIR, 'nemesis.log')}")
    print(f"  Configs: {CONFIGS_FILE}")
    print("=" * 60)
    logger.info(f"NEMESIS demarre sur {get_arch_label()} (mem: {mem['available_mb']}/{mem['total_mb']} MB)")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
