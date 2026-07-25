# NEMAPI Bridge v2.3 — OpenAI + send (delta)

Proxy local : **chat.deepseek.com** → API OpenAI.  
**Sans xdotool, sans regenerate** — automatisation DOM pure.

## Flux (simple)

1. Le proxy packe **uniquement le delta** (dernier message user / résultats d’outils ; system une fois par session). **Pas** tout l’historique OpenAI.
2. L’extension colle ce texte dans la **barre de texte** DeepSeek et clique Envoyer.
3. Elle attend la **réponse assistant** dans le DOM et la renvoie au proxy.
4. Le **contexte multi-tour** est déjà sur les serveurs DeepSeek (même fil d’onglet).

| Élément | Comportement |
|---------|----------------|
| Mode job | Toujours `send` |
| Historique CLI | Non renvoyé en entier (`manages_context` + `pack_delta`) |
| Regenerate / Edit | **Abandonné** (limite DeepSeek ~7) |

## Démarrage

```bash
source venv/bin/activate
python proxy.py   # ou python proxy_openai.py
```

1. Recharger l’extension **v2.3** (`about:debugging` → Reload)
2. Onglet **DeepSeek** (un fil de conversation)
3. Panneau → **Capturer** → **Connecter**
4. **Tester DOM** : `input=true`, `send=true`

## NEMESIS

```yaml
provider: bridge
providers:
  bridge:
    base_url: http://127.0.0.1:8080/v1
    model: deepseek-web
    timeout: 600
```

`/clear` reset la session proxy. Ouvrir aussi un **Nouveau chat** DeepSeek si vous voulez un fil vide côté web.

## API

- `POST /v1/chat/completions` — pack delta → job `send` → réponse
- `GET /v1/session` · `POST /v1/sessions/reset`
- `GET/POST /job` (extension)

## Dépannage

| Symptôme | Action |
|----------|--------|
| `input=false` | Page DeepSeek pas prête — F5, recapturer |
| Timeout réponse | L’IA n’a pas fini / sélecteurs DOM changés |
| Contexte « oublié » | Vous n’êtes plus sur le même fil DeepSeek — rester sur le même chat |
| Nouveau fil logique | `/clear` + Nouveau chat DeepSeek + reset session panneau |


---

## 13. Configuration Gemini 3 (reverse web)

AstarteBam utilise désormais les modèles Gemini 3 du client web local :

```env
AI_PROVIDER=gemini
AI_SLOT=1
GEMINI_MODEL_1=gemini-3.0-flash
GEMINI_MODEL_2=gemini-3.0-pro
```

Les modèles reconnus sont `gemini-3.0-flash`, `gemini-3.0-pro` et
`gemini-3.0-flash-thinking`. Le client applique automatiquement les en-têtes
web associés à chaque modèle. Cette intégration utilise la session Gemini du
navigateur, pas une clé Google AI Studio. Les cookies sont stockés uniquement
dans `.secrets/gemini_slot_1.json` ou `.secrets/gemini_slot_2.json`.

Commandes CLI :

```text
/gemini status
/gemini actualiser 1
/gemini test 1
/gemini ouvrir
```

Si Gemini renvoie une erreur d'authentification, ouvrez Gemini dans Firefox,
reconnectez le compte, puis relancez `/gemini actualiser 1`. Les réponses
streamées du protocole web sont entièrement parcourues et le fragment le plus
complet est conservé afin d'éviter les réponses tronquées.

## 14. Streaming des fournisseurs avec clé API

Les fournisseurs OpenAI-compatibles suivants utilisent maintenant le streaming
SSE (`stream: true`) : Groq, NVIDIA et Fireworks. AstarteBam lit les lignes
`data:`, agrège les fragments `choices[0].delta.content` et les publie dans les
logs en direct avant de terminer le parsing JSON des actions.

Exemple de configuration :

```env
AI_PROVIDER=nvidia
AI_SLOT=1
NVIDIA_API_KEY_1=votre_cle
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL_1=qwen/qwen3-next-80b-a3b-instruct
```

ou :

```env
AI_PROVIDER=groq
GROQ_API_KEY_1=votre_cle
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL_1=qwen/qwen3.6-27b
```

Le streaming est visible via `GET /logs/<request_id>?after=-1&timeout=25`.
Exemple de cycle :

```bash
id=$(curl -s http://127.0.0.1:8765/prompt \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Analyse ce projet"}' | jq -r .id)
curl -N "http://127.0.0.1:8765/logs/$id?after=-1&timeout=25"
curl -s "http://127.0.0.1:8765/result/$id"
```

Les logs `action_type: llm`, `action_args: stream`, `status: running`
contiennent les derniers fragments reçus. Le texte final reste utilisé pour
extraire le JSON d'actions : le streaming ne change donc pas le protocole
Astarte et ne casse pas les confirmations de sécurité.

Cohere, Gemini web et NEMAPI restent compatibles avec le même registre, mais
leur transport spécifique n'est pas un flux OpenAI SSE : ils renvoient leur
résultat selon leur protocole natif, après assemblage.

## 15. Utilisation des providers

```text
/provider status              afficher les slots configurés
/model gemini 1               sélectionner Gemini 3 Flash
/model nvidia 1               sélectionner NVIDIA avec clé API
/model groq 1                 sélectionner Groq avec clé API
/model fireworks 1            sélectionner Fireworks avec clé API
/model nemapi 1               sélectionner DeepSeek web local
/nemapi status                vérifier Firefox et le bridge
/nemapi test                  envoyer un test DeepSeek
/nemapi reset                 réinitialiser le fil DeepSeek
```

Pour une nouvelle tâche, le worker choisit le provider indiqué par
`AI_PROVIDER`, le slot indiqué par `AI_SLOT`, puis applique le fallback prévu
par le registre si le slot échoue. Ne mettez jamais une clé API dans le README,
les logs ou un dépôt Git.


## 16. Explications et protocole d'exécution interactif

Chaque JSON d'actions doit contenir `explanation`. Ce champ est enregistré dans
les logs avant l'exécution et doit expliquer :

```json
"explanation": {
  "summary": "Ce qui va être fait",
  "why": "Pourquoi c'est nécessaire",
  "steps": ["Étape 1", "Étape 2"],
  "risks": ["Risque éventuel"],
  "requires_user": true
}
```

L'explication décrit le plan ; elle ne remplace pas les confirmations de
sécurité. Une action sensible reste soumise à `/confirm/<request_id>`.

## 17. Exécution sans timeout et saisie utilisateur

Les commandes sont exécutées dans un pseudo-terminal avec stdout et stderr
transmis au fil de l'eau. Il n'y a pas de timeout automatique de commande.
L'utilisateur peut intervenir sans transmettre son mot de passe au modèle.

Pour une commande qui peut demander une saisie :

```json
{
  "type": "exec",
  "args": "sudo apt install python3-venv",
  "interactive": true,
  "stream": true
}
```

La forme courte suivante est aussi acceptée :

```json
{
  "type": "exec_interactive",
  "args": {
    "command": "sudo apt install python3-venv",
    "cwd": "/home/leon",
    "stdin": ""
  }
}
```

Dès qu'une action comporte `interactive:true`, `stream:true` ou le type
`exec_interactive`, Astarte force automatiquement le mode asynchrone et
retourne immédiatement un `request_id`, même avec `/execute`.

Suivre les sorties :

```bash
curl -N "http://127.0.0.1:8765/logs/REQUEST_ID?after=-1&timeout=25"
```

Répondre à une demande de saisie :

```bash
curl -X POST http://127.0.0.1:8765/input/REQUEST_ID \
  -H 'Content-Type: application/json' \
  -d '{"input":"la_saisie_de_l_utilisateur"}'
```

La saisie n'est jamais ajoutée au prompt de l'IA. Les messages détectés comme
mot de passe, passphrase ou password sont masqués dans les logs.

Interrompre une commande :

```bash
curl -X POST http://127.0.0.1:8765/signal/REQUEST_ID \
  -H 'Content-Type: application/json' \
  -d '{"signal":"SIGINT"}'
```

Signaux acceptés : `SIGINT`, `SIGTERM` et `EOF`. Le serveur ne tue pas une
commande simplement parce qu'elle est longue ou silencieuse.


## Arrêt propre du proxy

`start_proxy.sh` s'exécute au premier plan : Ctrl+C arrête le proxy, supprime `logs/proxy.pid` et conserve l'événement dans `logs/proxy.log`. Le script détecte aussi un port 8080 déjà utilisé.

```bash
./stop_proxy.sh
./start_proxy.sh
```
