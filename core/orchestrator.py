from .router import IntelligentRouter
from .context_store import SharedContextStore
from .reporting import make_report

UI_EXTENSIONS = (".html", ".htm", ".css", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte")
UI_WRITE_TYPES = {"write_file", "write_file_b64", "append", "replace"}

def is_ui_write(action):
    if not isinstance(action, dict):
        return False
    if action.get("type") not in UI_WRITE_TYPES:
        return False
    target = str(action.get("path") or action.get("args") or "").strip().lower()
    return target.endswith(UI_EXTENSIONS)

class CollaborativeOrchestrator:
    def __init__(self, call_agent, parse_json, max_agents=3):
        self.call_agent = call_agent
        self.parse_json = parse_json
        self.max_agents = max_agents
        self.router = IntelligentRouter()
        self.context = SharedContextStore()

    def run(self, task_id, prompt, task_history=""):
        decision = self.router.route(prompt)
        feedback = task_history if task_history else "Début de la tâche."
        if decision.category == "dual_expert":
            return self._run_dual_expert(task_id, prompt, feedback)
        return self._run_standard(task_id, prompt, feedback, decision)

    def _run_standard(self, task_id, prompt, feedback, decision):
        role = decision.roles[0] if decision.roles else "planner"
        msg = f"""DEMANDE : {prompt}
{feedback}
Réponds en JSON d'actions. Si la demande est terminée, renvoie {{"version":1,"actions":[]}}.
Tu peux déléguer l'UI à Gemini : {{"type":"delegate","args":"gemini","content":"...","path":"fichier.html"}}."""
        raw, provider, err = self.call_agent(msg, role)
        if err or not raw:
            plan = {"version": 1, "actions": []}
            return plan, {
                "status": "provider_error",
                "category": decision.category,
                "summary": f"Appel IA en échec : {err}",
                "provider": provider,
            }
        extracted = self.parse_json(raw)
        plan = extracted[0] if extracted else {"version": 1, "actions": []}
        return plan, {
            "status": "success",
            "category": decision.category,
            "summary": decision.explanation or "Plan standard validé.",
            "provider": provider,
        }

    @staticmethod
    def _plan_cheats(plan):
        actions = plan.get("actions", [])
        has_ui_code = any(is_ui_write(a) for a in actions)
        has_delegate = any(
            a.get("type") == "delegate" and str(a.get("args", "")).lower() == "gemini"
            for a in actions
        )
        return has_ui_code and not has_delegate

    def _run_dual_expert(self, task_id, prompt, feedback):
        msg = f"""TU ES LE CHEF DE PROJET / DÉVELOPPEUR BACKEND (DeepSeek).
Projet en cours : {prompt}

--- ÉTAT ACTUEL DU PROJET ---
{feedback}

--- NOTRE MÉTHODE DE TRAVAIL (DUAL-EXPERT) ---
Tu travailles en binôme avec notre Développeur Frontend (Gemini). Vous vous complétez pour livrer le meilleur projet possible.

🎯 TES MISSIONS (Ce que tu fais) :
- Penser l'architecture globale du projet.
- Créer l'arborescence, les fichiers de configuration, les bases de données.
- Coder la logique Backend (Python, Node.js, bash, etc.) avec les actions 'write_file' ou 'exec'.
- Orchestrer le projet étape par étape.

🤝 LA DÉLÉGATION À GEMINI (Ce que tu ne fais surtout pas) :
Tu n'écris JAMAIS le code de l'interface utilisateur (.html, .css, .js, .jsx, .vue, etc.). C'est le domaine exclusif de Gemini.
⚠️ TRÈS IMPORTANT : 
1. Gemini est isolé. Il ne connaît RIEN du projet. Tu dois OBLIGATOIREMENT lui écrire un bref contexte.
2. Ne le bride pas sur le visuel. Donne-lui les specs techniques mais laisse-lui CARTE BLANCHE sur le design, c'est lui le génie de l'UI !
3. 🚫 RÈGLE ABSOLUE : Tu n'as le droit qu'à **UNE SEULE ACTION 'delegate' PAR PLAN JSON**. Ne lui demande jamais de créer index.html, style.css et script.js séparément dans 3 actions distinctes. Demande-lui TOUJOURS de tout coder en un seul fichier (ex: index.html avec le CSS et le JS intégrés à l'intérieur).
Exemple de délégation parfaite :
{{"type": "delegate", "args": "gemini", "content": "Crée une interface web pour un jeu Zuma. Prévois un canvas et ces boutons. Fais un code tout-en-un (HTML/CSS/JS dans le même fichier). Pour le design, je te laisse carte blanche, sois créatif !", "path": "index.html"}}
AstarteBam ira le voir, récupérera son code, et le sauvegardera directement dans le fichier 'path'.

💡 RÈGLES DE BON SENS :
- Vérifie toujours le feedback : si l'action est déjà marquée "SUCCÈS", ne la répète pas.
- Le code de Gemini est bon, ne le réécris pas avec un write_file par-dessus ! S'il te manque des infos sur ce qu'il a fait, lis le fichier avec 'read_file'.
- Une fois que ton backend tourne et que tu as délégué l'interface à Gemini, la tâche est terminée !
- Termine alors en douceur : {{"version":2,"thought":"Le projet est assemblé et terminé","actions":[]}}

Tu dois répondre UNIQUEMENT avec ton plan d'action au format JSON v2, comme un vrai orchestrateur informatique."""
        raw, provider, err = self.call_agent(msg, "architect", provider_force="nemapi")
        if err or not raw:
            raw2, provider2, err2 = self.call_agent(
                msg + "\n\n[NOTE: bridge DeepSeek indisponible — continue en architecte.]",
                "architect",
            )
            if err2 or not raw2:
                return {"version": 2, "actions": []}, {
                    "status": "provider_error",
                    "category": "dual_expert",
                    "summary": f"Architecte indisponible (nemapi: {err} | fallback: {err2})",
                    "provider": provider2,
                }
            raw, provider, err = raw2, provider2, None
        extracted = self.parse_json(raw)
        plan = extracted[0] if extracted else {"version": 2, "actions": []}
        if self._plan_cheats(plan):
            print(f"[{task_id}] Note : UI codée directement par l'architecte — plan accepté (recommandation delegate).")
            return plan, {
                "status": "success",
                "category": "dual_expert",
                "summary": "Plan accepté (UI sans délégation Gemini — sous-optimal).",
                "provider": provider,
                "ui_cheated": True,
            }
        return plan, {
            "status": "success",
            "category": "dual_expert",
            "summary": "Pilotage dual-expert DeepSeek→Gemini validé.",
            "provider": provider,
        }
