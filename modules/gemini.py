#!/usr/bin/env python3
"""Connexion locale Gemini : ouvrir, actualiser les cookies, état et test."""
import json
import os
import stat
import webbrowser


def _root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _slot_file(slot):
    return os.path.join(_root(), ".secrets", "gemini_slot_{}.json".format(slot))


def _save(slot, values):
    required = ("__Secure-1PSID", "__Secure-1PSIDTS")
    missing = [key for key in required if not values.get(key)]
    if missing:
        return {"ok": False, "error": "Cookies Gemini manquants : {}".format(", ".join(missing))}
    folder = os.path.join(_root(), ".secrets")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    path = _slot_file(slot)
    payload = [{"name": key, "value": values[key]} for key in required]
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return {"ok": True, "msg": "Session Gemini locale actualisée (slot {}).".format(slot), "path": path}


def handle(args, cwd, stdin_data=""):
    """Usage: /gemini ouvrir | actualiser [1|2] | connecter [1|2] | status | test [1|2]."""
    parts = (args or "status").strip().split()
    command = parts[0].lower() if parts else "status"
    slot = parts[1] if len(parts) > 1 else "1"
    if slot not in ("1", "2"):
        return {"ok": False, "error": "Slot Gemini invalide : choisissez 1 ou 2."}
    if command in ("ouvrir", "open", "browser"):
        webbrowser.open("https://gemini.google.com/app", new=2)
        return {"ok": True, "msg": "Navigateur ouvert sur Gemini. Connectez-vous puis lancez /gemini actualiser {}.".format(slot)}
    if command in ("actualiser", "refresh", "connecter", "connect"):
        if command in ("connecter", "connect"):
            webbrowser.open("https://gemini.google.com/app", new=2)
        try:
            from gemini_client.cookie_manager import CookieExtractor
            values = CookieExtractor().extract_cookies(save_to_disk=False)
        except Exception as exc:
            return {"ok": False, "error": "Cookies non détectés. Ouvrez Gemini, connectez-vous dans votre navigateur, puis relancez /gemini actualiser {}. Détail : {}".format(slot, exc)}
        return _save(slot, values)
    if command in ("status", "etat"):
        rows = []
        for number in ("1", "2"):
            path = _slot_file(number)
            rows.append({"slot": number, "configured": os.path.isfile(path), "path": path})
        return {"ok": True, "msg": "État des sessions Gemini locales.", "slots": rows}
    if command == "test":
        path = _slot_file(slot)
        if not os.path.isfile(path):
            return {"ok": False, "error": "Aucune session dans le slot {}. Utilisez /gemini actualiser {}.".format(slot, slot)}
        try:
            from gemini_client import Chatbot, Model
            model = Model.G_2_5_PRO
            bot = Chatbot(cookie_path=path, model=model, timeout=None)
            response = bot.ask("Réponds uniquement par OK.")
            content = response.get("content", "") if isinstance(response, dict) else ""
            text = "".join(content) if isinstance(content, list) else str(content)
            if isinstance(response, dict) and response.get("error"):
                return {"ok": False, "error": "Gemini a renvoyé une erreur : {}".format(text)}
            return {"ok": True, "msg": "Test Gemini réussi.", "response_preview": text[:200]}
        except Exception as exc:
            return {"ok": False, "error": "Test Gemini impossible : {}".format(exc)}
    return {"ok": False, "error": "Commande inconnue. Utilisez ouvrir, actualiser, connecter, status ou test."}
