#!/usr/bin/env python3
"""
AstarteBam v6.0 — Client CLI avec Rich
"""
import json
import os
import sys
import time
import select
import threading
import stat
import urllib.request

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.theme import Theme
from rich.text import Text
from rich.table import Table
from rich.layout import Layout
from rich.align import Align

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_URL = os.environ.get("ASTARTE_URL", "http://127.0.0.1:8765")

RUNNING = True
LOCK_MSG = threading.Lock()
REFRESH_NEEDED = True

custom_theme = Theme({
    "user": "bold bright_cyan",
    "log_ok": "bold green",
    "log_ko": "bold red",
    "warn": "bold yellow",
    "info": "dim white",
    "system": "bold magenta",
    "retry": "italic yellow",
})

console = Console(theme=custom_theme)

def load_env():
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass

load_env()
SERVER_URL = os.environ.get("ASTARTE_URL", SERVER_URL)

def http_get(path, timeout=None):
    try:
        req = urllib.request.Request(SERVER_URL + path)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}

def http_post(path, data, timeout=None):
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(SERVER_URL + path, data=body, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def format_time(ms):
    if ms > 1000:
        return "{:.1f}s".format(ms / 1000)
    return "{}ms".format(ms)

def poll_logs(request_id):
    """Poll les logs et les affiche en temps reel avec Rich."""
    after = -1
    while RUNNING:
        try:
            result = http_get("/logs/{}?after={}".format(request_id, after), timeout=None)
            if "logs" in result:
                for log_entry in result["logs"]:
                    idx = log_entry.get("log_index", 0)
                    if idx > after:
                        after = idx
                        atype = log_entry.get("action_type", "?")
                        status = log_entry.get("status", "?")
                        msg = log_entry.get("message", "")[:150]
                        duration = log_entry.get("duration_ms", 0)
                        time_str = format_time(duration)
                        
                        if atype == "agent":
                            icon = "⚙" if status == "running" else "✓" if status == "success" else "✗"
                            color = "yellow" if status == "running" else "green" if status == "success" else "red"
                            console.print(f"  [{color}]{icon} AGENT {log_entry.get('action_args', '?').upper()}[/ {color}] [info]{msg}[/info]".replace("[/ ", "[/"))
                        elif atype == "orchestrator":
                            console.print(f"  [bold magenta]◈ ORCHESTRATEUR[/bold magenta] [info]{msg}[/info]")
                        elif atype == "llm" and status == "success":
                            console.print(f"  [bold blue]🤖 Réponse LLM :[/bold blue]")
                            console.print(f"  [dim blue]{msg}[/dim blue]")
                        elif status == "success":
                            console.print(f"  [log_ok]✅ [{atype}][/log_ok] [info]{msg}[/info] [dim]({time_str})[/dim]")
                        elif status == "retry":
                            console.print(f"  [retry]🔄 [{atype}] {msg} ({time_str})[/retry]")
                        elif status == "error" or status == "KO":
                            console.print(f"  [log_ko]❌ [{atype}] {msg} ({time_str})[/log_ko]")
                        elif status == "running":
                            console.print(f"  [system]⏳ [{atype}] {msg}[/system]")
                        else:
                            console.print(f"  [info]  [{atype}] {msg} ({time_str})[/info]")
                    if log_entry.get("data", {}).get("confirmation_required"):
                        details = log_entry["data"].get("details", {})
                        console.print(f"  [warn]⚠️  CONFIRMATION REQUISE : {details.get('reason', msg)}[/warn]")
                        console.print(f"  [dim]Action : {details.get('action_type', '?')} {details.get('args', '')}[/dim]")
                        choice = Prompt.ask("  Autoriser cette action ?", choices=["oui", "non"], default="non")
                        confirmation = http_post("/confirm/{}".format(request_id), {"approved": choice == "oui"})
                        if not confirmation.get("ok"):
                            console.print(f"  [log_ko]❌ Confirmation non envoyée : {confirmation.get('message', confirmation.get('error', 'inconnue'))}[/log_ko]")
                    if log_entry.get("data", {}).get("input_required"):
                        prompt_text = log_entry["data"].get("input_prompt", "")
                        mask = log_entry["data"].get("mask", False)
                        console.print(f"  [warn]⚠️  INPUT REQUIS : {prompt_text}[/warn]")
                        user_input = Prompt.ask("  [bold yellow]→[/bold yellow]", password=mask)
                        http_post("/input/{}".format(request_id), {"input": user_input})
            if result.get("more") is False:
                break
            # Verifier si c'est termine
            check = http_get("/result/{}".format(request_id))
            if check.get("status") in ("done", "error", "partial_error"):
                break
        except Exception:
            time.sleep(1)

def send_prompt(text):
    """Envoie un prompt et suit l'execution en direct."""
    console.print(f"\n[user]⬆ {text}[/user]")
    resp = http_post("/prompt", {"prompt": text})
    if not resp.get("ok"):
        console.print(f"[log_ko]❌ Erreur: {resp.get('error', 'inconnu')}[/log_ko]")
        return
    
    pid = resp.get("id", "")
    worker = resp.get("worker", "?")
    
    console.print(f"[system]⏳ AstarteBam réfléchit...[/system]")
    poll_logs(pid)
    
    # Résultat final
    final = http_get("/result/{}".format(pid))
    status = final.get("status", "?")
    total_duration = final.get("duration_ms", 0)
    
    if status == "done":
        console.print(f"\n[log_ok]✅ TERMINE : {status} (total {format_time(total_duration)})[/log_ok]")
    elif status == "error":
        console.print(f"\n[log_ko]❌ TERMINE : {status}[/log_ko]")
    else:
        console.print(f"\n[warn]⚠️  TERMINE : {status}[/warn]")
    
    if final.get("error"):
        console.print(f"[log_ko]   Erreur: {final['error']}[/log_ko]")
    
    if final.get("results"):
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim")
        table.add_column("Type")
        table.add_column("Statut")
        table.add_column("Détail")
        for i, r in enumerate(final["results"], 1):
            ok = r.get("ok", False)
            flag = "✅" if ok else "❌"
            detail = r.get("output") or r.get("error") or r.get("path") or r.get("msg") or ""
            table.add_row(str(i), r.get("action_type", "?"), flag, str(detail)[:80])
        console.print(table)

def show_dashboard():
    """Vue de contrôle : serveur, orchestration et slots fournisseurs sans secrets."""
    ping = http_get("/ping")
    config = http_get("/config")
    providers = http_get("/providers").get("providers", [])
    queue = http_get("/queue").get("queue", [])
    state = "[log_ok]● EN LIGNE[/log_ok]" if ping.get("status") == "ok" else "[log_ko]● HORS LIGNE[/log_ko]"
    summary = Table.grid(expand=True, padding=(0, 2))
    summary.add_column(); summary.add_column(); summary.add_column()
    summary.add_row(
        Panel(Align.center(state + "\n[dim]" + SERVER_URL + "[/dim]"), title="Serveur", border_style="cyan"),
        Panel(Align.center("[bold]{}[/bold]\n[dim]{}[/dim]".format(config.get("ORCHESTRATION_MODE", "individual"), config.get("WORKER_MODE", "?"))), title="Orchestration", border_style="magenta"),
        Panel(Align.center("[bold]{}[/bold]\n[dim]{} module(s)[/dim]".format(len(providers), ping.get("modules_count", "?"))), title="Fournisseurs", border_style="green")
    )
    table = Table(title="Slots fournisseurs", show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Fournisseur"); table.add_column("Slot", justify="center"); table.add_column("Modèle"); table.add_column("État")
    if providers:
        for item in providers:
            state = item.get("state", "configuré")
            color = "green" if state in ("ok", "configuré") else "red"
            table.add_row(item.get("provider", "?"), str(item.get("slot", "?")), item.get("model", "?"), "[{}]{}[/{}]".format(color, state, color))
    else:
        table.add_row("[dim]Aucun slot configuré[/dim]", "", "", "")
    tasks = Table.grid(expand=True); tasks.add_column()
    tasks.add_row("[bold]File d’attente :[/bold] {} tâche(s)".format(len(queue)))
    for task in queue[:4]: tasks.add_row("  [dim]{}[/dim] {} — {}".format(task.get("id","?"), task.get("status","?"), task.get("prompt","")[:90]))
    console.print(Panel(summary, title="ASTARTE BAM — TABLEAU DE BORD", border_style="bright_cyan"))
    console.print(table)
    console.print(Panel(tasks, border_style="blue"))

def show_help():
    console.print(Panel(
        "[system]ASTARTE BAM v6.0 — AIDE[/system]\n\n"
        "[bold]/help[/bold]     → cette aide\n"
        "[bold]/ping[/bold]     → tester connexion\n"
        "[bold]/dashboard[/bold]→ afficher le tableau de bord\n"
        "[bold]/clear[/bold]    → vider l'écran\n"
        "[bold]/quit[/bold]     → quitter\n"
        "[bold]/modules[/bold]  → lister les modules\n"
        "[bold]/queue[/bold]    → voir la file d'attente\n"
        "[bold]/config[/bold]   → voir/modifier la config\n"
        "[bold]/cle[/bold]      → changer une clé Groq, NVIDIA ou API\n"
        "[bold]/model[/bold]    → sélectionner fournisseur, slot et modèle individuel\n"
        "[bold]/supprimer-cle[/bold] → retirer une clé enregistrée\n"
        "[bold]/gemini-cookie[/bold] → enregistrer une session Gemini locale (slot 1 ou 2)\n\n"
        "[dim]Tape du texte naturel → envoi au LLM[/dim]\n"
        "[dim]Ou du JSON brut → execution directe[/dim]",
        border_style="cyan", expand=False
    ))

def main():

    console.print("[bold cyan]DeepSeek API System:[/bold cyan] Bridge local activé.")
    # Vérification Gemini
    if os.path.exists(".secrets/gemini_slot_1.json"):
        console.print("[bold green]Gemini API System:[/bold green] Cookies détectés (Slot 1) - Modèle 3.1 Pro actif.")
    else:
        console.print("[bold red]Gemini API Status:[/bold red] Cookies manquants dans .secrets/")

    console.print("[dim]Note: L'agent gère automatiquement le lancement du bridge sur le port 8080.[/dim]")

    global RUNNING
    
    console.clear()
    console.print(Panel(
        "[system]ASTARTE BAM v6.0[/system]\n"
        f"[dim]Serveur : {SERVER_URL}[/dim]",
        border_style="bright_cyan", expand=False
    ))
    
    show_dashboard()
    p = http_get("/ping")
    if p.get("status") == "ok":
        console.print(f"[log_ok]✔ Connecté ! Modules: {p.get('modules_count', '?')}, Worker: {p.get('worker_mode', '?')}[/log_ok]")
    else:
        console.print("[warn]⚠️  Serveur injoignable[/warn]")
    
    while RUNNING:
        try:
            user_input = Prompt.ask("\n[bold cyan]▸[/bold cyan]")
            msg = user_input.strip()
            
            if not msg:
                continue
            if msg in ("/quit", "/q"):
                RUNNING = False
                break
            if msg == "/clear":
                console.clear()
                continue
            if msg == "/help":
                show_help()
                continue
            if msg in ("/dashboard", "/dash"):
                show_dashboard()
                continue
            if msg == "/ping":
                r = http_get("/ping")
                console.print(json.dumps(r, indent=2))
                continue
            if msg == "/modules":
                r = http_get("/modules")
                if r.get("ok"):
                    for m in r["modules"]:
                        console.print(f"  [bold]/{m['name']}[/bold] — [dim]{m.get('description', '')}[/dim]")
                continue
            if msg == "/queue":
                r = http_get("/queue")
                if "queue" in r:
                    if not r["queue"]:
                        console.print("[info]File vide.[/info]")
                    else:
                        for e in r["queue"]:
                            color = "green" if e["status"] == "done" else "yellow" if e["status"] == "processing" else "red" if e["status"] == "error" else "dim"
                            console.print(f"  [{color}][{e['status']}][/{color}] {e['id']} — {e['prompt'][:80]}")
                continue
            if msg == "/config":
                r = http_get("/config")
                if r:
                    for k, v in r.items():
                        if k.endswith("_SET"):
                            console.print(f"  [bold]{k}[/bold]: [dim]{'***' if v else '(non défini)'}[/dim]")
                        else:
                            console.print(f"  [bold]{k}[/bold]: {v}")
                    console.print("\n[dim]Pour modifier : /config CLE VALEUR[/dim]")
                continue
            if msg == "/site":
                pages = {"deepseek": "chat_deepseek_com", "qwen": "chat_qwen_ai", "kimi": "www_kimi_com"}
                current = os.environ.get("NEMESIS_MODEL", "deepseek")
                console.print(f"[info]Site actuel: {current} → {pages.get(current, '?')}[/info]")
                console.print("[dim]Sites dispos: deepseek, qwen, kimi[/dim]")
                console.print("[dim]Pour changer: /site deepseek[/dim]")
                continue
            if msg.startswith("/site "):
                parts = msg.split()
                if len(parts) >= 2:
                    site = parts[1].lower()
                    if site in ("deepseek", "qwen", "kimi"):
                        os.environ["NEMESIS_MODEL"] = site
                        r = http_post("/config", {"NEMESIS_MODEL": site})
                        console.print(f"[log_ok]✔ Site changé: {site}[/log_ok]")
                    else:
                        console.print(f"[log_ko]❌ Site inconnu: {site}. Choisis: deepseek, qwen, kimi[/log_ko]")
                continue
            if msg == "/model" or msg.startswith("/model "):
                parts = msg.split(None, 3)
                provider = parts[1].lower() if len(parts) > 1 else Prompt.ask("Fournisseur", choices=["groq", "nvidia", "fireworks", "cohere", "gemini", "nemapi"], default="groq")
                if provider not in ("groq", "nvidia", "fireworks", "cohere", "gemini", "nemapi"):
                    console.print("[log_ko]❌ Fournisseur inconnu.[/log_ko]"); continue
                slot = parts[2] if len(parts) > 2 else Prompt.ask("Slot", choices=["1", "2"], default="1")
                if slot not in ("1", "2"): console.print("[log_ko]❌ Slot invalide.[/log_ko]"); continue
                model = parts[3] if len(parts) > 3 else Prompt.ask("Identifiant exact du modèle", default="")
                payload={"AI_PROVIDER":provider,"AI_SLOT":slot,"WORKER_MODE":"api"}
                prefix={"groq":"GROQ","nvidia":"NVIDIA","fireworks":"FIREWORKS","cohere":"COHERE","gemini":"GEMINI","nemapi":"NEMAPI"}[provider]
                if model.strip() and provider != "nemapi": payload[prefix+"_MODEL_"+slot]=model.strip()
                if provider == "nemapi": payload["NEMAPI_ENABLED"]="true"
                r=http_post("/config",payload)
                if r.get("ok"): console.print("[log_ok]✔ Mode individuel : {} slot {} sélectionné.[/log_ok]".format(provider,slot))
                else: console.print("[log_ko]❌ {}[/log_ko]".format(r.get("error","Sélection impossible")))
                continue

            if msg == "/supprimer-cle" or msg.startswith("/supprimer-cle "):
                parts = msg.split()
                provider = parts[1].lower() if len(parts) > 1 else Prompt.ask("Fournisseur", choices=["groq", "nvidia", "fireworks", "cohere", "api"], default="groq")
                if provider not in ("groq", "nvidia", "fireworks", "cohere", "api"):
                    console.print("[log_ko]❌ Fournisseur inconnu.[/log_ko]"); continue
                slot = "1" if provider == "api" else (parts[2] if len(parts) > 2 else Prompt.ask("Slot", choices=["1", "2"], default="1"))
                if slot not in ("1", "2"):
                    console.print("[log_ko]❌ Slot invalide.[/log_ko]"); continue
                key = {"groq":"GROQ_API_KEY_"+slot,"nvidia":"NVIDIA_API_KEY_"+slot,"fireworks":"FIREWORKS_API_KEY_"+slot,"cohere":"COHERE_API_KEY_"+slot,"api":"API_KEY"}[provider]
                if Prompt.ask("Retirer {} ?".format(key), choices=["oui", "non"], default="non") != "oui":
                    console.print("[warn]Suppression annulée.[/warn]"); continue
                r = http_post("/config", {"remove_keys":[key]})
                console.print("[log_ok]✔ {} retirée.[/log_ok]".format(key) if r.get("ok") else "[log_ko]❌ {}[/log_ko]".format(r.get("error", "Suppression impossible")))
                continue

            if msg.startswith("/gemini-cookie"):
                parts = msg.split()
                slot = parts[1] if len(parts) > 1 else Prompt.ask("Emplacement Gemini", choices=["1", "2"], default="1")
                if slot not in ("1", "2"):
                    console.print("[log_ko]❌ Emplacement invalide : choisissez 1 ou 2.[/log_ko]")
                    continue
                console.print("[warn]Ne partagez jamais ces cookies dans le chat ou un dépôt Git.[/warn]")
                psid = Prompt.ask("__Secure-1PSID", password=True).strip()
                psidts = Prompt.ask("__Secure-1PSIDTS", password=True).strip()
                if not psid or not psidts:
                    console.print("[log_ko]❌ Les deux valeurs sont nécessaires ; rien n’a été enregistré.[/log_ko]")
                    continue
                secrets_dir = os.path.join(BASE_DIR, ".secrets")
                os.makedirs(secrets_dir, mode=0o700, exist_ok=True)
                try:
                    os.chmod(secrets_dir, 0o700)
                except OSError:
                    pass
                cookie_file = os.path.join(secrets_dir, "gemini_slot_{}.json".format(slot))
                payload = [
                    {"name": "__Secure-1PSID", "value": psid},
                    {"name": "__Secure-1PSIDTS", "value": psidts}
                ]
                try:
                    fd = os.open(cookie_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(payload, f)
                    os.chmod(cookie_file, stat.S_IRUSR | stat.S_IWUSR)
                    console.print("[log_ok]✔ Session Gemini enregistrée localement dans le slot {}.[/log_ok]".format(slot))
                except OSError as e:
                    console.print("[log_ko]❌ Impossible d’enregistrer la session : {}[/log_ko]".format(e))
                continue

            if msg == "/cle" or msg.startswith("/cle "):
                parts = msg.split(None, 1)
                provider = parts[1].strip().lower() if len(parts) > 1 else Prompt.ask("Type de clé", choices=["groq", "nvidia", "fireworks", "cohere", "api"], default="groq")
                if provider not in ("groq", "nvidia", "fireworks", "cohere", "api"):
                    console.print("[log_ko]❌ Choisis : groq, nvidia, fireworks, cohere ou api.[/log_ko]")
                    continue
                slot = "1" if provider == "api" else Prompt.ask("Slot", choices=["1", "2"], default="1")
                label = {"groq": "GROQ_API_KEY_" + slot, "nvidia": "NVIDIA_API_KEY_" + slot, "fireworks": "FIREWORKS_API_KEY_" + slot, "cohere": "COHERE_API_KEY_" + slot, "api": "API_KEY"}[provider]
                key = Prompt.ask("Nouvelle {}".format(label), password=True)
                if not key.strip():
                    console.print("[warn]Clé inchangée.[/warn]")
                    continue
                payload = {label: key.strip()}
                if provider in ("groq", "nvidia", "fireworks", "cohere"):
                    payload["AI_PROVIDER"] = provider
                    payload["WORKER_MODE"] = "api"
                r = http_post("/config", payload)
                if r.get("ok"):
                    console.print("[log_ok]✔ {} mise à jour. La valeur n’est pas affichée.[/log_ok]".format(label))
                else:
                    console.print("[log_ko]❌ {}[/log_ko]".format(r.get("error", "Mise à jour impossible")))
                continue

            if msg.startswith("/config "):
                parts = msg.split(None, 2)
                if len(parts) >= 3:
                    key, val = parts[1], parts[2]
                    r = http_post("/config", {key: val})
                    if r.get("ok"):
                        console.print(f"[log_ok]✔ {key} = {val}[/log_ok]")
                    else:
                        console.print(f"[log_ko]❌ {r.get('error', '')}[/log_ko]")
                continue
            if msg.startswith("/"):
                parts = msg.split(None, 1)
                mod_name = parts[0][1:]
                mod_args = parts[1] if len(parts) > 1 else ""
                r = http_post("/execute", {"version": 1, "stop_on_error": True, "actions": [{"type": "module", "args": mod_name, "content": mod_args}]})
                if r.get("results"):
                    res = r["results"][0]
                    flag = "✅" if res.get("ok") else "❌"
                    detail = res.get("output") or res.get("msg") or res.get("error") or ""
                    console.print(f"  {flag} {detail[:300]}")
                continue
            
            # Essayer JSON brut
            try:
                parsed = json.loads(msg)
                if "version" in parsed and "actions" in parsed:
                    console.print(f"[user]⬆ [JSON brut][/user]")
                    r = http_post("/execute_async", parsed)
                    if not r.get("ok"):
                        console.print(f"[log_ko]❌ Erreur: {r.get('error', 'inconnue')}[/log_ko]")
                    else:
                        request_id = r["request_id"]
                        poll_logs(request_id)
                        final = http_get("/result/{}".format(request_id))
                        for res in final.get("results", []):
                            flag = "✅" if res.get("ok") else "❌"
                            detail = res.get("output") or res.get("error") or ""
                            console.print(f"  {flag} [{res.get('action_type', '?')}] {detail[:200]}")
                        console.print(f"[info]Status: {final.get('status', '?')} ({final.get('duration_ms', 0)}ms)[/info]")
                else:
                    send_prompt(msg)
            except (json.JSONDecodeError, ValueError):
                send_prompt(msg)
                
        except KeyboardInterrupt:
            console.print("\n[system]👋 Au revoir ![/system]")
            break
        except Exception:
            pass

if __name__ == "__main__":
    main()
