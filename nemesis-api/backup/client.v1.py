"""
NEMESIS Client - Envoie des prompts au système et récupère les réponses
"""

import requests
import time
import sys
import json

BACKEND_URL = "http://localhost:5000"


class NemesisClient:
    def __init__(self, page_id=None):
        self.page_id = page_id
        self.base_url = BACKEND_URL

    def list_pages(self):
        """Scanner les pages disponibles (à implémenter côté serveur)"""
        resp = requests.get(f"{self.base_url}/pages")
        return resp.json()

    def ask(self, prompt, page_id=None, config=None, wait=True, timeout=60):
        """
        Envoie un prompt à une page IA et attend la réponse

        Args:
            prompt: Le texte à envoyer
            page_id: ID de la page cible (ex: 'chat_openai_com')
            config: Configuration optionnelle (coordonnées des clics)
            wait: Si True, attend la réponse
            timeout: Temps max d'attente en secondes

        Returns:
            dict avec la réponse ou l'erreur
        """
        pid = page_id or self.page_id
        if not pid:
            return {"error": "page_id requis"}

        task_id = f"task_{int(time.time() * 1000)}"

        payload = {
            "page_id": pid,
            "prompt": prompt,
            "task_id": task_id
        }
        if config:
            payload["config"] = config

        # Envoyer le prompt
        resp = requests.post(f"{self.base_url}/send_prompt", json=payload)
        if resp.status_code != 200:
            return {"error": f"Erreur serveur: {resp.text}"}

        data = resp.json()
        if not wait:
            return data

        # Attendre le résultat
        start = time.time()
        while time.time() - start < timeout:
            result_resp = requests.get(f"{self.base_url}/get_result/{task_id}")
            result = result_resp.json()

            if "success" in result:
                return result

            if result.get("status") != "pending":
                time.sleep(0.5)
                continue

            time.sleep(1)

        return {"error": "Timeout - pas de réponse reçue"}

    def ask_batch(self, prompts, page_id=None, config=None):
        """
        Envoie plusieurs prompts en séquence

        Args:
            prompts: liste de textes à envoyer
            page_id: ID de la page cible
            config: Configuration optionnelle

        Returns:
            liste des résultats
        """
        results = []
        for i, prompt in enumerate(prompts):
            print(f"[{i+1}/{len(prompts)}] Envoi: {prompt[:50]}...")
            result = self.ask(prompt, page_id, config)
            results.append(result)
            if result.get("error"):
                print(f"  ❌ Erreur: {result['error']}")
            else:
                print(f"  ✅ Réponse: {result.get('result', '')[:100]}...")
        return results


# Interface CLI simple
if __name__ == "__main__":
    client = NemesisClient()

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python client.py <page_id> <prompt>")
        print("  python client.py <page_id> --batch <fichier_prompts.json>")
        print()
        print("Pages disponibles (IDs):")
        print("  kimi_moonshot_cn, chat_deepseek_com, chat_qwenlm_ai, gemini_google_com")
        sys.exit(1)

    page_id = sys.argv[1]

    if sys.argv[2] == "--batch" and len(sys.argv) > 3:
        with open(sys.argv[3]) as f:
            prompts = json.load(f)
        results = client.ask_batch(prompts, page_id)
        print("\n" + "="*50)
        print(f"Terminé: {len(results)} réponses")
        for i, r in enumerate(results):
            print(f"\n[{i}] {r.get('result', r.get('error', '?'))[:200]}")
    else:
        prompt = " ".join(sys.argv[2:])
        print(f"📤 Envoi à {page_id}: {prompt[:50]}...")
        result = client.ask(prompt, page_id)
        if result.get("success"):
            print(f"📥 Réponse:\n{result['result']}")
        else:
            print(f"❌ Erreur: {result.get('error')}")
