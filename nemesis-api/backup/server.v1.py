"""
NEMESIS API - Serveur local de gestion des xdotool par page
Communication avec Tampermonkey via polling HTTP
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import threading
import time
import queue
import json
import os

app = Flask(__name__)
CORS(app)

# File d'attente par page_id
page_queues = {}
# Résultats par page_id
page_results = {}
# Configurations enregistrées par page_id
saved_configs = {}
# Lock pour éviter les conflits
lock = threading.Lock()

WINDOW_ID = None  # ID de la fenêtre navigateur ciblée


def get_window_id():
    """Récupère l'ID de la fenêtre active du navigateur (cherche Firefox, Chrome, Brave, Chromium)"""
    global WINDOW_ID
    if WINDOW_ID:
        check = subprocess.run(
            ["xdotool", "getwindowname", WINDOW_ID],
            capture_output=True, text=True
        )
        if check.returncode == 0 and check.stdout.strip():
            return WINDOW_ID
        else:
            WINDOW_ID = None

    browsers = ["firefox", "chrome", "brave", "chromium", "Google-chrome", "Brave-browser"]
    for browser in browsers:
        try:
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--class", browser],
                capture_output=True, text=True, timeout=3
            )
            ids = result.stdout.strip().split('\n')
            if ids and ids[0]:
                WINDOW_ID = ids[0]
                name = subprocess.run(["xdotool", "getwindowname", WINDOW_ID],
                                      capture_output=True, text=True).stdout.strip()
                print(f"Fenetre trouvee: {name[:60]} (ID: {WINDOW_ID})")
                return WINDOW_ID
        except Exception as e:
            continue

    print("Aucune fenetre de navigateur trouvee!")
    return None


def focus_window(window_id):
    """Donne le focus à la fenêtre sans la faire surgir"""
    subprocess.run(["xdotool", "windowfocus", "--sync", window_id])


def get_window_geometry(window_id):
    """Récupère la position et taille de la fenêtre"""
    result = subprocess.run(
        ["xdotool", "getwindowgeometry", window_id],
        capture_output=True, text=True
    )
    lines = result.stdout.strip().split('\n')
    pos_line = [l for l in lines if 'Position' in l][0]
    geo_line = [l for l in lines if 'Geometry' in l][0]
    # Format: "  Position: 0,0 (screen: 0)"
    pos_part = pos_line.split(':')[1].strip().split(' ')[0]  # "0,0"
    x = int(pos_part.split(',')[0])
    y = int(pos_part.split(',')[1])
    # Format: "  Geometry: 1280x735"
    geo_part = geo_line.split(':')[1].strip()
    w = int(geo_part.split('x')[0])
    h = int(geo_part.split('x')[1])
    return x, y, w, h


def xdotool_click(window_id, rel_x, rel_y, y_offset=100):
    """Clique à une position relative (le focus est géré par xdotool_type)"""
    abs_x, abs_y, w, h = get_window_geometry(window_id)
    
    abs_click_x = abs_x + rel_x
    abs_click_y = abs_y + rel_y + y_offset
    
    print(f"[xdotool_click] Absolu: {abs_click_x},{abs_click_y}")
    subprocess.run([
        "xdotool", "mousemove", "--clearmodifiers", str(abs_click_x), str(abs_click_y),
        "click", "1"
    ], timeout=3)
    time.sleep(0.1)


def xdotool_type(window_id, text):
    """Tape du texte - Ctrl+V"""
    print(f"[xdotool_type] Collage: {text[:50]}...")
    try:
        subprocess.run(["xdotool", "windowactivate", "--sync", str(window_id)], timeout=3)
        time.sleep(0.1)
        subprocess.run(["xclip", "-selection", "c"], input=text.encode('utf-8'), capture_output=True, timeout=5)
        time.sleep(0.1)
        subprocess.run(["xdotool", "key", "--window", str(window_id), "ctrl+v"], timeout=5)
        print(f"[xdotool_type] Collage OK")
    except Exception as e:
        print(f"[xdotool_type] Erreur: {e}")


def xdotool_copy(window_id):
    """Copie le texte sans focus"""
    subprocess.run(["xdotool", "key", "--window", str(window_id), "ctrl+c"], timeout=5)
    time.sleep(0.3)
    result = subprocess.run(["xclip", "-selection", "c", "-o"], capture_output=True, text=True, timeout=5)
    return result.stdout.strip()


def execute_action(page_id, action_config, prompt):
    """
    Exécute une séquence d'actions sur une page
    action_config: dict avec les coordonnées des éléments
    """
    print(f"[execute_action] Demarrage pour page={page_id}, prompt={prompt[:50]}...")
    print(f"[execute_action] Config: {action_config}")

    window_id = get_window_id()
    if not window_id:
        print("[execute_action] ERREUR: Fenetre navigateur non trouvee")
        return {"error": "Fenetre navigateur non trouvee"}

    print(f"[execute_action] Fenetre ID: {window_id}")

    try:
        result_text = ""

        # Étape 1: Cliquer sur la zone de saisie
        if "input_click" in action_config:
            x, y = action_config["input_click"]
            print(f"[execute_action] Clic zone saisie: {x},{y}")
            xdotool_click(window_id, x, y)
            time.sleep(0.5)

        # Étape 2: Coller le prompt (après le clic, le focus est déjà bon)
        if prompt:
            print(f"[execute_action] Collage du prompt: {prompt[:50]}...")
            # Écrire dans un fichier temporaire puis xclip
            tmpfile = "/tmp/nemesis_prompt.txt"
            with open(tmpfile, "w", encoding="utf-8") as f:
                f.write(prompt)
            subprocess.run(f"cat {tmpfile} | xclip -selection c", shell=True, timeout=5)
            time.sleep(0.2)
            # Ctrl+V
            subprocess.run(["xdotool", "key", "ctrl+v"], timeout=5)
            time.sleep(0.3)
            print(f"[execute_action] Collage OK")

        # Étape 3: Cliquer sur le bouton envoyer
        if "send_click" in action_config:
            x, y = action_config["send_click"]
            print(f"[execute_action] Clic bouton envoyer: {x},{y}")
            xdotool_click(window_id, x, y)
            time.sleep(0.5)

        # Étape 4: Attendre et copier la réponse (clic+copie toutes les 8s, max 8 essais)
        if "copy_zone" in action_config:
            x, y = action_config["copy_zone"]
            max_attempts = 8
            result_text = ""

            for attempt in range(max_attempts):
                print(f"[execute_action] Tentative copie {attempt+1}/{max_attempts}...")
                time.sleep(8)

                # Clic zone réponse + Ctrl+C
                xdotool_click(window_id, x, y)
                time.sleep(0.3)
                result_text = xdotool_copy(window_id)

                if result_text and result_text != prompt and len(result_text) > 2:
                    print(f"[execute_action] Reponse detectee: {result_text[:100]}...")
                    break
                else:
                    print(f"[execute_action] Pas encore de reponse (obtenu: {result_text[:50] if result_text else 'vide'}), reessai...")

            if not result_text:
                return {"success": False, "error": "Aucune reponse apres 64 secondes"}

        print(f"[execute_action] Resultat final: {result_text[:100]}...")
        return {"success": True, "result": result_text}

    except Exception as e:
        print(f"[execute_action] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def process_queue(page_id):
    """Traite la file d'attente pour une page donnée"""
    print(f"[process_queue] Demarrage pour page_id={page_id}")
    with lock:
        if page_id not in page_queues:
            print(f"[process_queue] page_id {page_id} pas dans page_queues")
            return

    while True:
        with lock:
            if page_id not in page_queues or page_queues[page_id].empty():
                print(f"[process_queue] File vide pour {page_id}, fin")
                break
            try:
                task = page_queues[page_id].get_nowait()
                print(f"[process_queue] Tache recuperee: {task['id']}")
            except queue.Empty:
                break

        prompt = task["prompt"]
        action_config = task["config"]
        task_id = task["id"]

        print(f"[process_queue] Execution de la tache {task_id}...")
        result = execute_action(page_id, action_config, prompt)

        with lock:
            page_results[task_id] = result
            print(f"[process_queue] Resultat stocke pour {task_id}: {str(result)[:100]}")


@app.route('/register_page', methods=['POST'])
def register_page():
    """Tampermonkey enregistre une page avec sa config"""
    data = request.json
    page_id = data.get("page_id")
    config = data.get("config", {})

    with lock:
        if page_id not in page_queues:
            page_queues[page_id] = queue.Queue()
        if config and config.get("input_click"):
            saved_configs[page_id] = config
            print(f"[register_page] Config sauvegardee pour {page_id}: {config}")

    return jsonify({"status": "ok", "page_id": page_id, "saved": page_id in saved_configs})


@app.route('/send_prompt', methods=['POST'])
def send_prompt():
    """Reçoit un prompt - détecte auto le site si page_id non fourni"""
    data = request.json
    page_id = data.get("page_id")
    prompt = data.get("prompt")
    config = data.get("config", {})
    task_id = data.get("task_id", str(time.time()))

    if not prompt:
        return jsonify({"error": "prompt requis"}), 400

    # Si pas de page_id, détecter automatiquement
    if not page_id:
        window_id = get_window_id()
        if not window_id:
            return jsonify({"error": "Aucun navigateur trouvé"}), 404
        
        name = subprocess.run(["xdotool", "getwindowname", str(window_id)],
                              capture_output=True, text=True).stdout.strip()
        
        with lock:
            for pid, pconfig in saved_configs.items():
                domain_part = pid.replace('_', '.').replace('www.', '')
                keywords = domain_part.split('.')
                if any(kw.lower() in name.lower() for kw in keywords if len(kw) > 2):
                    page_id = pid
                    config = pconfig
                    print(f"[send_prompt] Auto-détection: {pid} depuis '{name}'")
                    break
        
        if not page_id:
            return jsonify({"error": f"Site non reconnu: {name}. Pages enregistrées: {list(saved_configs.keys())}"}), 404

    # Si pas de config fournie, utiliser la config sauvegardée
    if not config or not config.get("input_click"):
        with lock:
            if page_id in saved_configs:
                config = saved_configs[page_id]
                print(f"[send_prompt] Utilisation config sauvegardee pour {page_id}")
            else:
                return jsonify({"error": f"Aucune config pour {page_id}"}), 400

    with lock:
        if page_id not in page_queues:
            page_queues[page_id] = queue.Queue()

        task = {
            "id": task_id,
            "prompt": prompt,
            "config": config
        }
        page_queues[page_id].put(task)

        t = threading.Thread(target=process_queue, args=(page_id,), daemon=True)
        t.start()

    return jsonify({
        "status": "queued",
        "task_id": task_id,
        "page_id": page_id,
        "auto_detected": True
    })


@app.route('/get_result/<task_id>', methods=['GET'])
def get_result(task_id):
    """Récupère le résultat d'une tâche"""
    with lock:
        if task_id in page_results:
            result = page_results.pop(task_id)
            return jsonify(result)
    return jsonify({"status": "pending"})


@app.route('/pages', methods=['GET'])
def list_pages():
    """Liste les pages enregistrées avec leurs configs"""
    with lock:
        return jsonify({
            "saved_configs": {k: v for k, v in saved_configs.items()},
            "window_id": WINDOW_ID
        })

@app.route('/current_page', methods=['GET'])
def current_page():
    """Détecte la page actuellement ouverte dans le navigateur"""
    window_id = get_window_id()
    if not window_id:
        return jsonify({"error": "Aucun navigateur trouvé"}), 404
    
    name = subprocess.run(["xdotool", "getwindowname", str(window_id)],
                          capture_output=True, text=True).stdout.strip()
    
    # Chercher quelle page sauvegardée correspond
    detected = None
    with lock:
        for pid in saved_configs:
            # Convertir page_id en morceau d'URL (chat_deepseek_com -> deepseek)
            domain_part = pid.replace('_', '.').replace('www.', '')
            if any(word.lower() in name.lower() for word in domain_part.split('.')):
                detected = pid
                break
    
    return jsonify({
        "window_name": name,
        "detected_page": detected,
        "has_config": detected in saved_configs if detected else False
    })

@app.route('/bing/<page_id>', methods=['POST'])
def bing_notification(page_id):
    """Reçoit une notification 'bing' de Tampermonkey (données copiées)"""
    data = request.json
    content = data.get("content", "")
    task_id = data.get("task_id", "")

    with lock:
        page_results[task_id] = {"success": True, "result": content, "bing": True}

    # Joue un son
    os.system("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || echo -e '\a'")

    return jsonify({"status": "bing_received"})


if __name__ == '__main__':
    print("🚀 NEMESIS API démarrée sur http://localhost:5000")
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
