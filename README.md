# Astarte BAM v6 — Guide de fonctionnement complet

Astarte BAM est un orchestrateur local d’agents IA capable de transformer une demande humaine en **plan JSON**, d’exécuter les actions prévues sur une machine Linux, de lire les résultats, puis de redonner ces résultats au modèle afin qu’il continue ou corrige son travail.

> **Attention** — les actions générées ne sont pas une simulation. Elles peuvent créer, modifier, supprimer des fichiers et exécuter des commandes. Gardez le serveur local et vérifiez les confirmations affichées dans le CLI.

---

## 1. Installation

```bash
unzip AstarteBam_ameliore.zip
cd AstarteBam_ameliore
./install_astartebam.sh
```

Le script crée `.venv`, installe les dépendances Rich et Gemini-Chat-API, prépare `.env` et `.secrets/`, puis vérifie le code.

Démarrer :

```bash
./astarte
```

Le lanceur demande le mode d’orchestration :

```text
1) Individuel    — un fournisseur/modèle actif
2) Collaboratif  — plusieurs sous-agents planifient en parallèle
```

---

## 2. Architecture

```text
Utilisateur / CLI / Admin web
             │
             ▼
       API Astarte BAM
             │
      ┌──────┴─────────────────────────┐
      │                                │
      ▼                                ▼
JSON direct                       Prompt langage naturel
POST /execute[_async]             POST /prompt
      │                                │
      ▼                                ▼
Exécuteur d’actions        Routeur / fournisseur IA
      │                                │
      └─────────── logs + résultats ───┘
                                       │
                                       ▼
                         feedback IA → actions suivantes
```

Composants :

```text
server.py                 API, actions, logs, confirmations, worker
cli.py                    tableau de bord Rich et terminal interactif
core/providers.py         fournisseurs, slots, rotation et fallback
core/router.py            classification des demandes
core/orchestrator.py      sous-agents collaboratifs et agrégation
core/context_store.py     contexte partagé de tâche
core/reporting.py         rapport collaboratif
config/system_prompt_v2.txt  protocole IA → JSON d’actions (individuel)
config/system_prompt_collaboratif_v1.txt  protocole rôles et JSON (collaboratif)
modules/                  capacités spécialisées
workspace/                espace de travail et fichiers produits
```

---

## 3. Protocole IA et boucle de feedback

Le modèle reçoit le prompt système et doit répondre exclusivement avec un bloc JSON v1 :

```json
{
  "version": 1,
  "stop_on_error": false,
  "cwd": "projet",
  "actions": [
    {"type": "write_file", "args": "hello.py", "content": "print('Bonjour')"},
    {"type": "exec", "args": "python3 hello.py"}
  ]
}
```

Cycle complet :

```text
1. Le modèle propose un lot d’actions.
2. Astarte BAM les valide et les exécute.
3. Les sorties, erreurs et fichiers concernés sont journalisés.
4. Le serveur construit un prompt de continuation ou de correction.
5. Le modèle reçoit ce feedback et propose le lot suivant.
6. La tâche se termine lorsque le modèle renvoie : {"version":1,"actions":[]}.
```

La boucle de feedback est illimitée. Elle s’arrête uniquement lorsque le modèle renvoie `actions: []`. Les commandes et modules Astarte BAM ne possèdent pas de limite d’exécution artificielle.

---

## 4. Actions disponibles

| Action | Utilité |
|---|---|
| `exec` | Lance une commande shell dans le répertoire de travail. |
| `write_file` | Crée ou écrase un fichier texte. |
| `write_file_b64` | Écrit un fichier binaire encodé en Base64. |
| `read_file` | Lit un fichier texte. |
| `replace` | Remplace un bloc `SEARCH / REPLACE` dans un fichier. |
| `append` | Ajoute du contenu à un fichier. |
| `delete_file` | Supprime un fichier ou dossier. |
| `copy` | Copie un fichier ou dossier. |
| `list_dir` | Liste un dossier. |
| `fix` | Affiche le contexte autour d’une ligne. |
| `module` | Appelle un module Astarte BAM. |
| `upload` | Envoie un fichier vers un service externe. |

Les actions sensibles demandent confirmation dans le CLI :

- commande shell reconnue comme dangereuse ;
- suppression ;
- écrasement de fichier ;
- copie vers une destination existante.

---

## 5. Terminal interactif

Les actions `exec` asynchrones utilisent un pseudo-terminal. La sortie apparaît progressivement dans le CLI, comme dans un terminal classique.

Si une commande affiche un prompt connu — `sudo`, `Password:`, `Mot de passe`, `passphrase`, `Continue? [Y/n]` — le CLI vous demande la saisie et la transmet au processus actif.

Les mots de passe saisis dans le CLI sont masqués.

---

## 6. Modes individuel et collaboratif

### Individuel

Un seul fournisseur est privilégié pour la demande. C’est le mode recommandé avec NEMAPI/DeepSeek Bridge ou lors de tests.

```env
ORCHESTRATION_MODE=individual
AI_PROVIDER=groq
```

### Collaboratif

Le routeur classe la demande puis lance des rôles spécialisés :

```text
planner · code · system · document · research · vision · review
```

Les plans sont agrégés, les actions strictement identiques sont dédupliquées, puis le résultat est exécuté avec les mêmes confirmations humaines.

```env
ORCHESTRATION_MODE=collaborative
COLLAB_MAX_AGENTS=3
```

Utilisez NEMAPI de préférence en mode individuel : son bridge navigateur conserve un seul fil DeepSeek et ne doit pas recevoir plusieurs demandes parallèles.

---

## 7. Fournisseurs, slots et modèles

Chaque fournisseur accepte au plus deux slots. Les clés restent locales dans `.env` ; les cookies Gemini restent dans `.secrets/`.

```text
Groq       : slot 1, slot 2
NVIDIA     : slot 1, slot 2
Fireworks  : slot 1, slot 2
Cohere     : slot 1, slot 2
Gemini     : session 1, session 2
NEMAPI     : bridge local unique
```

### Profils privilégiés pour le code

Astarte BAM privilégie les familles orientées code, raisonnement technique ou agent :

| Fournisseur | Profil conseillé | Rôle conseillé |
|---|---|---|
| Groq | `qwen/qwen3.6-27b` | code rapide, planification légère |
| NVIDIA | `qwen/qwen3-next-80b-a3b-instruct` | code et raisonnement |
| Fireworks | DeepSeek V4 Pro / Flash, Kimi K2.6, GLM 5.1, Qwen 3.6 | sous-agents code, système, review |
| Cohere | Command A / Command R+ | recherche, RAG, vérification documentaire |
| Gemini | Gemini 2.5 Pro | analyse longue, multimodal, code |
| NEMAPI | DeepSeek Web | agent général dans le navigateur |

Les catalogues de fournisseurs changent. Vérifiez toujours le nom exact exposé par votre compte avant de l’enregistrer dans `.env` ou dans le CLI.

Un modèle Llama peut être réservé uniquement au rôle final d’explication collective si vous le configurez volontairement ; il ne constitue pas le profil code par défaut.

### Configuration

```env
# Groq
GROQ_API_KEY_1=
GROQ_MODEL_1=qwen/qwen3.6-27b
GROQ_API_KEY_2=
GROQ_MODEL_2=qwen/qwen3.6-27b

# NVIDIA
NVIDIA_API_KEY_1=
NVIDIA_MODEL_1=qwen/qwen3-next-80b-a3b-instruct
NVIDIA_API_KEY_2=
NVIDIA_MODEL_2=qwen/qwen3-next-80b-a3b-instruct

# Fireworks : utilisez l’identifiant exact disponible dans votre compte
FIREWORKS_API_KEY_1=
FIREWORKS_MODEL_1=
FIREWORKS_API_KEY_2=
FIREWORKS_MODEL_2=

# Cohere : surtout destiné à recherche et vérification
COHERE_API_KEY_1=
COHERE_MODEL_1=command-a-03-2025
COHERE_API_KEY_2=
COHERE_MODEL_2=command-a-03-2025

# NEMAPI / DeepSeek Bridge local
NEMAPI_ENABLED=false
NEMAPI_BASE_URL=http://127.0.0.1:8080/v1
NEMAPI_MODEL=deepseek-web
```

Le pool sélectionne les slots disponibles et passe au suivant lorsqu’un fournisseur échoue.

---

## 8. CLI

Lancer le client :

```bash
./astarte
```

Commandes principales :

```text
/dashboard                    tableau de bord
/providers                    état des fournisseurs (via API)
/model                         sélectionner fournisseur, slot et modèle en individuel
/model fireworks 1 accounts/fireworks/models/deepseek-v4-pro
/cle groq                     enregistrer ou changer une clé Groq
/cle fireworks                enregistrer une clé Fireworks
/cle cohere                   enregistrer une clé Cohere
/cle nvidia                   enregistrer une clé NVIDIA
/supprimer-cle groq 1         supprimer une clé locale
/gemini ouvrir                 ouvre Gemini dans le navigateur
/gemini actualiser 1           extrait et stocke les cookies locaux du slot 1
/gemini connecter 1            ouvre Gemini puis tente l’extraction automatique
/gemini status                 état des deux sessions
/gemini test 1                 vérifie une session Gemini locale
/gemini-cookie 1              saisie manuelle alternative
/help                         aide
/quit                         quitter
```

N’envoyez jamais de clé API ou de cookie Gemini dans un chat, un dépôt Git ou une archive partagée.

---

## 9. NEMAPI / DeepSeek Bridge

NEMAPI ne nécessite pas de clé API cloud. Il utilise un proxy local et une session DeepSeek ouverte dans Firefox.

```env
NEMAPI_ENABLED=true
NEMAPI_BASE_URL=http://127.0.0.1:8080/v1
NEMAPI_MODEL=deepseek-web
NEMAPI_RESET_ON_NEW_TASK=true
AI_PROVIDER=nemapi
ORCHESTRATION_MODE=individual
```

Le bridge doit écouter seulement sur la machine locale :

```env
NEMAPI_HOST=127.0.0.1
```

Ne l’exposez pas sur `0.0.0.0` sans authentification.

Commandes de bridge dans le CLI :

```text
/nemapi status
/nemapi test
/nemapi reset
```

Astarte BAM réinitialise la session NEMAPI au début d’une nouvelle tâche lorsque `NEMAPI_RESET_ON_NEW_TASK=true`. En mode collaboratif avec `AI_PROVIDER=nemapi`, Astarte limite le bridge à un agent pour éviter de mélanger les messages dans le même fil DeepSeek.

---

## 10. API HTTP

| Route | Fonction |
|---|---|
| `GET /ping` | Vérifie le serveur. |
| `GET /health` | État machine minimal. |
| `GET /modules` | Liste les modules. |
| `GET /providers` | Liste les slots sans exposer les clés. |
| `GET /config` | Configuration non sensible. |
| `POST /prompt` | Démarre une demande IA. |
| `POST /execute` | Exécution JSON synchrone. |
| `POST /execute_async` | Exécution JSON asynchrone. |
| `GET /logs/<id>` | Logs en direct. |
| `GET /result/<id>` | Résultat final. |
| `POST /confirm/<id>` | Accepte ou refuse une action sensible. |
| `POST /input/<id>` | Envoie une saisie à un terminal interactif. |
| `POST /signal/<id>` | Envoie SIGINT, SIGTERM ou EOF. |

---

## 11. Tests

```bash
./install_astartebam.sh
./astarte
```

Tests déjà réalisés sur cette version :

```text
- installation locale et compilation Python ;
- API, slots, collaboration, logs et confirmations ;
- boucle complète de feedback à deux tours ;
- terminal interactif ;
- Groq réel avec réponse JSON ;
- adaptateurs Fireworks et Cohere simulés ;
- registre Gemini sans cookie ;
- création HTML de bout en bout.
```

---

## 12. Sécurité

- Gardez `HOST` et `ADMIN_HOST` sur `127.0.0.1` par défaut.
- Configurez une `API_KEY` si le serveur est accessible depuis un réseau.
- Vérifiez les confirmations avant de lancer une commande sensible.
- Les sorties et résultats peuvent contenir des informations machine : ne partagez pas les logs sans les relire.
- `.env` et `.secrets/` sont privés et doivent rester exclus de Git.
