from .router import IntelligentRouter
from .context_store import SharedContextStore
from .reporting import make_report
import json

class CollaborativeOrchestrator:
    def __init__(self, call_agent, parse_json, max_agents=3):
        self.call_agent, self.parse_json, self.max_agents = call_agent, parse_json, max_agents
        self.router, self.context = IntelligentRouter(), SharedContextStore()

    def run(self, task_id, prompt, task_history=""):
        feedback = task_history if task_history else "Début du projet."
        
        # On renforce le message pour DeepSeek
        msg = f"""TU ES L'ARCHITECTE. PROJET : {prompt}
        {feedback}
        
        RÈGLES INVIOLABLES :
        1. Tu DÉLÈGUES l'UI à Gemini : {{"type": "delegate", "args": "gemini", "content": "..."}}
        2. Tu ne codes que la LOGIQUE backend.
        3. Réponds en JSON v2 uniquement."""
        
        raw, provider, err = self.call_agent(msg, "architect", provider_force="nemapi")
        extracted = self.parse_json(raw)
        plan = extracted[0] if extracted else {"version": 2, "actions": []}

        # --- LE FILTRE DE FER ---
        # Si DeepSeek essaie de créer du HTML sans déléguer, on le punit et on le force à recommencer
        has_ui_code = any(".html" in str(a.get("args")) or "<!DOCTYPE" in str(a.get("content")) for a in plan.get("actions", []))
        has_delegate = any(a.get("type") == "delegate" for a in plan.get("actions", []))

        if has_ui_code and not has_delegate:
            print(f"[{task_id}] DeepSeek a tenté de tricher. Rejet du plan.")
            retry_msg = "ERREUR CRITIQUE : Tu as codé l'UI toi-même. C'est INTERDIT. Efface tes actions UI et utilise 'delegate' pour confier l'interface à Gemini."
            raw, _, _ = self.call_agent(retry_msg, "architect", provider_force="nemapi")
            extracted = self.parse_json(raw)
            plan = extracted[0] if extracted else {"version": 2, "actions": []}

        return plan, {"status": "success", "category": "dual_expert", "summary": "Pilotage DeepSeek validé."}
