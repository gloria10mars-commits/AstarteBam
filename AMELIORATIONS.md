Source copiée le 2026-07-17. Le fichier .env et les environnements virtuels inclus ont été volontairement exclus.

## Interface admin modernisée
- Tableau de bord avec état du serveur, nombre de modules, mode IA et adresse API.
- Navigation distincte : tableau de bord, modules, file d’attente et connexion.
- Configuration de l’adresse API et de la clé API depuis l’interface (stockage local du navigateur).
- Journal d’activité horodaté et suivi des tâches asynchrones.
- Bouton d’envoi en langage naturel et bouton séparé pour l’exécution d’un JSON.
- Mise en page responsive pour ordinateur et mobile.

## Exécution sans timeout
- Les actions `exec` et le module `shell` attendent maintenant la fin naturelle de la commande, sans limite de temps configurée.
- Les timeouts réseau, de logs et des modules spécialisés restent inchangés.

## Flux de démarrage fiabilisé
- Configuration `.env` validée au démarrage : ports, limites et mode worker.
- Les erreurs de configuration sont affichées et empêchent un démarrage incohérent.
- `ADMIN_HOST` a été ajouté ; API et interface admin restent sur `127.0.0.1` par défaut.
- Avertissements visibles lorsque l’API n’a pas de clé ou qu’un service est exposé sur le réseau.
- Version unifiée dans le serveur et le lanceur : `6.0.0`.
- Lanceur Bash amélioré : vérification Python, création de `.env`, contrôle indicatif des ports, contrôle de la dépendance Rich du CLI et arrêt propre du serveur enfant.

## Flux JSON direct renforcé
- Validation stricte de toutes les actions JSON v1 (types, champs, tailles, Base64 et format `replace`).
- Ajout de `POST /execute_async`, avec suivi par `GET /logs/<request_id>` et `GET /result/<request_id>`.
- Mode système documenté : chemins absolus et `..` autorisés suivant les droits Linux du processus.
- `COMMAND_POLICY=warn|block|allow` pour le comportement face aux motifs de commande sensibles.
- Les messages de logs sont limités à 4 000 caractères pour éviter une croissance excessive par entrée.

## Flux langage naturel (IA)
- `POST /prompt` valide les champs et les tailles avant mise en file.
- Une demande est refusée avec HTTP 503 lorsqu’aucun worker IA utilisable n’est disponible.
- Un seul cycle IA → JSON → actions est exécuté ; aucun feedback automatique ne relance l’IA.
- Les erreurs inattendues du worker ferment maintenant les logs de la demande.

## Confirmation humaine des actions sensibles
- Confirmation demandée pour les commandes shell sensibles, suppressions, écrasements et copies vers une destination existante.
- Ajout de `POST /confirm/<request_id>` ; la décision est `{"approved": true|false}`.
- Le CLI détecte la demande dans les logs, affiche l’action et demande `oui/non`.
- Le JSON brut du CLI utilise désormais `/execute_async` afin que la confirmation soit possible sans bloquer la connexion HTTP.

## Terminal interactif et fournisseur Groq
- Les commandes associées à une requête sont maintenant lancées dans un pseudo-terminal ; leur sortie est diffusée au CLI en direct.
- Le CLI peut envoyer une saisie à un processus interactif, y compris un prompt `sudo`, sans afficher le mot de passe.
- Ajout du fournisseur OpenAI-compatible Groq : `AI_PROVIDER=groq`, `GROQ_API_KEY`, `GROQ_MODEL` et `GROQ_BASE_URL`.

## Raccourci de clés CLI
- `/cle`, `/cle groq`, `/cle nvidia` et `/cle api` demandent une clé avec saisie masquée.
- La configuration est appliquée immédiatement au serveur ; l’ajout d’une clé API démarre le worker sans redémarrage.

## Orchestration collaborative — fondation
- Ajout des composants `core/router.py`, `context_store.py`, `orchestrator.py` et `reporting.py`.
- Mode `ORCHESTRATION_MODE=individual|collaborative` et menu de démarrage correspondant.
- En collaboratif, des sous-agents spécialisés planifient en parallèle ; les plans sont dédupliqués, agrégés, journalisés puis exécutés par le flux existant.

## Pool fournisseurs
- Ajout de `core/providers.py` : slots 1/2, rotation, fallback et état public non sensible.
- Adaptateurs OpenAI compatibles Groq/NVIDIA/Fireworks, adaptateur Cohere v2 et adaptateur Gemini optionnel via sessions locales.
- Endpoint `GET /providers`.

## CLI — tableau de bord et agents
- Tableau de bord Rich au démarrage et avec `/dashboard` : API, orchestration, slots et file d’attente.
- Les logs collaboratifs affichent en direct le rôle de chaque agent et les messages de l’orchestrateur.

## Installation en une commande
- Ajout de `install_astartebam.sh` : environnement `.venv`, Rich, Gemini-Chat-API, `.env` local, `.secrets` et vérification Python.
- Test réel de l’installation réussi.

## Option NEMAPI / DeepSeek Bridge
- Ajout du fournisseur `nemapi`, activable par `NEMAPI_ENABLED=true`, sans clé API cloud.
- Il utilise le bridge local OpenAI-compatible sur `http://127.0.0.1:8080/v1` et apparaît dans `/providers`.

## Boucle de feedback restaurée
- Après chaque lot d’actions, le résultat est injecté au modèle sous forme de prompt de continuation ou de correction.
- La tâche reste `pending` jusqu’au JSON vide `actions: []` ou à la limite `MAX_FEEDBACK_ATTEMPTS`.
- Tests unitaire et intégration complète de deux tours IA réussis.

## Documentation et profils de modèles
- README entièrement réécrit : architecture, protocole, feedback, CLI, sécurité, fournisseurs et dépannage.
- Profils par défaut réorientés vers Qwen et DeepSeek plutôt que Llama ; Fireworks documente DeepSeek/Kimi/GLM/Qwen comme choix code.

## Limites supprimées
- Boucle de feedback illimitée : elle continue jusqu’au JSON `actions: []`.
- Les timeouts d’exécution des modules actifs ont été supprimés ; une opération attend sa fin naturelle.

## Module Gemini automatisé
- Ajout de `modules/gemini.py` : ouverture navigateur, extraction locale des cookies, stockage sécurisé par slot, état et test.
- Le fournisseur Gemini conserve désormais un `Chatbot` par slot pour garder la conversation durant les cycles de feedback et normalise les réponses `content` en liste.

## Prompt collaboratif corrigé
- Ajout de `config/system_prompt_collaboratif_v1.txt`.
- Le JSON n’utilise plus de champ `role` invalide ; les rôles passent par le contexte orchestrateur.
- Consignes alignées sur les confirmations, le feedback, le review contextuel et les chemins système justifiés.
- Le worker collaboratif charge désormais ce prompt dédié.

## Adaptation NEMAPI Bridge
- Réinitialisation automatique de la session DeepSeek à chaque nouvelle tâche NEMAPI.
- Nouveau module `/nemapi status|test|reset`.
- Le mode collaboratif limite NEMAPI à un agent afin de préserver son fil navigateur unique.

## Sélection individuelle de modèle
- Ajout de `AI_SLOT` et de la commande CLI `/model`.
- En individuel, le fournisseur et le slot choisis sont prioritaires, avec fallback vers les autres slots.
