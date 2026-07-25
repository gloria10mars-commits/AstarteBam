"""
NEMESIS Client v1.5.2
- SDK Python style OpenAI (Nemesis.chat.completions.create)
- CLI preserve: python client.py <page_id|model> <prompt>
- Async: Nemesis.tasks.create / .get / .result / .cancel
- Compat v1: Nemesis().ask(prompt, page_id) toujours dispo
- Auto-start: si le serveur est down, le client le lance en arriere-plan
- Compatible 32-bit (i386, armhf) et 64-bit (amd64, arm64)
"""

import requests
import time
import sys
import json
import uuid
import os
import subprocess
import socket
from typing import Optional, List, Dict, Any


BACKEND_URL = "http://localhost:5000"
SERVER_PORT = 5000


# ---------------------------------------------------------------------------
# Auto-start du serveur si besoin
# ---------------------------------------------------------------------------
def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Check rapide si le port repond"""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _ensure_server_running(verbose: bool = True):
    """Lance le serveur en arriere-plan s'il n'est pas deja demarre.
    Timeout adapte pour hardware ancien (Pentium M, Celeron M, etc.): 45s max."""
    if _is_port_open(SERVER_PORT):
        return True

    # Trouver server.py dans le meme dossier que client.py
    client_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(client_dir, "server.py")
    if not os.path.exists(server_path):
        if verbose:
            print(f"[!] server.py introuvable: {server_path}")
        return False

    # Detecter le venv local s'il existe (PEP 668 friendly)
    venv_python = os.path.join(client_dir, "venv", "bin", "python")
    if os.path.exists(venv_python):
        python_bin = venv_python
    else:
        python_bin = sys.executable

    # Lancer en subprocess detache
    if verbose:
        print(f"[i] Serveur non demarre - lancement automatique...")
        print(f"    Python: {python_bin}")
        print(f"    (Patiente, sur hardware ancien le demarrage peut prendre 10-20s)")
    log_path = os.path.join(client_dir, "logs", "nemesis.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_f = open(log_path, "a")

    # Detache completement du parent
    proc = subprocess.Popen(
        [python_bin, server_path],
        cwd=client_dir,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True  # detached
    )

    # Attendre que le port reponde (max 45s - hardware ancien)
    for i in range(90):
        time.sleep(0.5)
        if _is_port_open(SERVER_PORT):
            if verbose:
                print(f"[OK] Serveur demarre (PID {proc.pid}) sur :{SERVER_PORT} en {i*0.5:.1f}s")
            return True
        # Afficher des points pour montrer qu'on attend
        if verbose and i > 0 and i % 4 == 0:
            print(f"    ... toujours en cours ({i*0.5:.0f}s)")

    if verbose:
        print(f"[!] Le serveur n'a pas repondu dans les 45s - verifie {log_path}")
    return False


# ---------------------------------------------------------------------------
# Ressources facon OpenAI
# ---------------------------------------------------------------------------
class Completions:
    """Resource /v1/chat/completions"""

    def __init__(self, client: "Nemesis"):
        self.client = client

    def create(
        self,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
        timeout: int = 60,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Drop-in OpenAI. Retourne le dict JSON complet.

        Exemple:
            r = client.chat.completions.create(
                model="deepseek",
                messages=[{"role":"user","content":"Salut"}]
            )
            print(r["choices"][0]["message"]["content"])
        """
        payload = {"model": model, "messages": messages, "stream": stream}
        try:
            resp = requests.post(
                f"{self.client.base_url}/v1/chat/completions",
                json=payload, timeout=timeout
            )
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Serveur NEMESIS injoignable sur {self.client.base_url}\n"
                f"  -> Lance-le manuellement:  python server.py\n"
                f"  -> Ou verifie que le port 5000 est libre"
            )
        if resp.status_code != 200:
            try:
                err = resp.json()
            except Exception:
                err = {"error": resp.text}
            raise RuntimeError(f"Nemesis error {resp.status_code}: {err}")
        return resp.json()


class Chat:
    def __init__(self, client: "Nemesis"):
        self.completions = Completions(client)


class Tasks:
    """Resource /v1/tasks - mode asynchrone"""

    def __init__(self, client: "Nemesis"):
        self.client = client

    def create(self, model: str, prompt: str) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.client.base_url}/v1/tasks",
            json={"model": model, "prompt": prompt},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get(self, task_id: str) -> Dict[str, Any]:
        resp = requests.get(f"{self.client.base_url}/v1/tasks/{task_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def result(self, task_id: str, timeout: int = 30) -> Dict[str, Any]:
        """Bloquant: attend le resultat max `timeout` secondes"""
        resp = requests.get(
            f"{self.client.base_url}/v1/tasks/{task_id}/result",
            timeout=timeout + 5
        )
        if resp.status_code == 504:
            return {"success": False, "error": "timeout"}
        resp.raise_for_status()
        return resp.json()

    def cancel(self, task_id: str) -> Dict[str, Any]:
        resp = requests.delete(f"{self.client.base_url}/v1/tasks/{task_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()


class Models:
    """Resource /v1/models"""

    def __init__(self, client: "Nemesis"):
        self.client = client

    def list(self) -> List[Dict[str, Any]]:
        resp = requests.get(f"{self.client.base_url}/v1/models", timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])


# ---------------------------------------------------------------------------
# Client principal
# ---------------------------------------------------------------------------
class Nemesis:
    """
    Client NEMESIS API v1.5

    Usage sync (OpenAI drop-in):
        from client import Nemesis
        n = Nemesis()
        r = n.chat.completions.create(
            model="deepseek",
            messages=[{"role":"user","content":"Salut"}]
        )
        print(r["choices"][0]["message"]["content"])

    Usage async:
        task = n.tasks.create(model="deepseek", prompt="Salut")
        result = n.tasks.result(task["task_id"], timeout=60)

    Compat v1:
        result = n.ask("Salut", page_id="chat_deepseek_com")
    """

    def __init__(
        self,
        base_url: str = BACKEND_URL,
        api_key: Optional[str] = None,
        auto_start_server: bool = True,
        verbose: bool = True
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.verbose = verbose
        # Auto-start le serveur si besoin (localhost uniquement)
        if auto_start_server and ("localhost" in self.base_url or "127.0.0.1" in self.base_url):
            _ensure_server_running(verbose=verbose)
        self.chat = Chat(self)
        self.tasks = Tasks(self)
        self.models = Models(self)

    # ---- Compat v1 ----
    def list_pages(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/pages").json()

    def ask(
        self,
        prompt: str,
        page_id: Optional[str] = None,
        config: Optional[Dict] = None,
        wait: bool = True,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """Envoie un prompt et attend la reponse (compat v1)"""
        payload = {"prompt": prompt, "task_id": f"task_{uuid.uuid4().hex[:12]}"}
        if page_id:
            payload["page_id"] = page_id
        if config:
            payload["config"] = config

        resp = requests.post(f"{self.base_url}/send_prompt", json=payload)
        if resp.status_code != 200:
            return {"error": f"Erreur serveur: {resp.text}"}

        data = resp.json()
        if not wait:
            return data

        task_id = data.get("task_id")
        start = time.time()
        while time.time() - start < timeout:
            r = requests.get(f"{self.base_url}/get_result/{task_id}")
            result = r.json()
            if "success" in result or "error" in result and result.get("error") != "pending":
                if result.get("status") == "pending":
                    time.sleep(0.5)
                    continue
                return result
            time.sleep(0.5)
        return {"error": "Timeout"}

    def ask_batch(
        self,
        prompts: List[str],
        page_id: Optional[str] = None,
        config: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Envoie plusieurs prompts en sequence"""
        results = []
        for i, prompt in enumerate(prompts):
            print(f"[{i+1}/{len(prompts)}] Envoi: {prompt[:50]}...")
            result = self.ask(prompt, page_id, config)
            results.append(result)
            if result.get("error"):
                print(f"  X Erreur: {result['error']}")
            else:
                txt = result.get("result", "")
                print(f"  OK: {txt[:100]}...")
        return results

    # ---- Admin ----
    def health(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/health").json()

    def metrics(self) -> Dict[str, Any]:
        return requests.get(f"{self.base_url}/v1/metrics").json()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
USAGE = """
NEMESIS Client v1.5.2 (compatible 32-bit et 64-bit)

Usage:
  python client.py <page_id|model> <prompt>
  python client.py <page_id|model> --batch <fichier_prompts.json>
  python client.py --list
  python client.py --health
  python client.py --metrics

Modeles/pages supportes (apres calibration):
  deepseek   -> chat_deepseek_com
  kimi       -> kimi_moonshot_cn
  qwen       -> chat_qwenlm_ai
  gemini     -> gemini_google_com

Exemple:
  python client.py deepseek "Salut, raconte une blague"
  python client.py deepseek --batch prompts.json
"""


def main():
    # Commandes qui ne necessitent pas le serveur
    if len(sys.argv) >= 2 and sys.argv[1] in ("--help", "-h"):
        print(USAGE)
        sys.exit(0)

    try:
        client = Nemesis()
    except Exception as e:
        print(f"[!] Impossible de demarrer le client: {e}", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(0)

    # Commandes speciales
    if sys.argv[1] == "--list":
        try:
            pages = client.list_pages()
            print("Pages calibrees:")
            for pid, cfg in pages.get("saved_configs", {}).items():
                print(f"  - {pid}: input={cfg.get('input_click')} send={cfg.get('send_click')} copy={cfg.get('copy_zone')}")
            if not pages.get("saved_configs"):
                print("  (aucune - ouvre un site dans le navigateur et calle 3 points)")
        except requests.exceptions.ConnectionError:
            print("[!] Serveur NEMESIS injoignable. Lance: python server.py")
        return

    if sys.argv[1] == "--health":
        try:
            h = client.health()
            print(json.dumps(h, indent=2, ensure_ascii=False))
        except requests.exceptions.ConnectionError:
            print("[!] Serveur NEMESIS injoignable. Lance: python server.py")
        return

    if sys.argv[1] == "--metrics":
        try:
            m = client.metrics()
            print(json.dumps(m, indent=2, ensure_ascii=False))
        except requests.exceptions.ConnectionError:
            print("[!] Serveur NEMESIS injoignable. Lance: python server.py")
        return

    # Modele/page
    target = sys.argv[1]

    if len(sys.argv) < 3:
        print(USAGE)
        sys.exit(1)

    if sys.argv[2] == "--batch" and len(sys.argv) > 3:
        with open(sys.argv[3]) as f:
            prompts = json.load(f)
        results = client.ask_batch(prompts, target)
        print("\n" + "=" * 50)
        print(f"Termine: {len(results)} reponses")
        for i, r in enumerate(results):
            print(f"\n[{i}] {r.get('result', r.get('error', '?'))[:200]}")
    else:
        prompt = " ".join(sys.argv[2:])
        print(f"Envoi a {target}: {prompt[:50]}...")
        try:
            r = client.chat.completions.create(
                model=target,
                messages=[{"role": "user", "content": prompt}],
                timeout=60
            )
            print(f"\nReponse:\n{r['choices'][0]['message']['content']}")
        except RuntimeError as e:
            print(f"\n[!] {e}", file=sys.stderr)
            # Fallback v1
            try:
                result = client.ask(prompt, page_id=target)
                if result.get("success"):
                    print(f"\nReponse:\n{result['result']}")
                else:
                    print(f"\nErreur: {result.get('error')}", file=sys.stderr)
            except requests.exceptions.ConnectionError:
                print("[!] Serveur NEMESIS toujours injoignable.", file=sys.stderr)
        except requests.exceptions.ConnectionError:
            print(f"\n[!] Serveur NEMESIS injoignable sur {client.base_url}", file=sys.stderr)
            print(f"    Lance-le manuellement:  python server.py", file=sys.stderr)


if __name__ == "__main__":
    main()
