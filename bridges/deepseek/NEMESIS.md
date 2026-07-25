NEMESIS Project - NEMAPI Bridge (Extension Firefox)
Documentation generee par NEMESIS le 30 mai 2026.

Objectif
Transformer un navigateur Firefox en passerelle API pour applications d'IA web (ChatGPT, DeepSeek, Claude, Gemini, etc.) en simulant des clics humains via une extension Firefox. Le projet reprend le concept de NEMAPI Bridge Android en l'adaptant au contexte PC/navigateur.

Pourquoi
De nombreuses IA puissantes disposent d'applications web gratuites mais n'offrent pas d'API accessible gratuitement. NEMAPI Bridge utilise une extension Firefox pour simuler des interactions humaines (clics, copier-coller) et exposer ces capacites via un serveur HTTP local.

Fonctionnement global
1. Un proxy HTTP local (Python) expose une API REST sur le port 8080
2. L'extension Firefox (Manifest v3) poll le proxy toutes les 2 secondes
3. Quand une requete arrive, l'extension execute le cycle d'automatisation
4. Les clics sont effectues via xdotool (evenements X11 natifs, isTrusted=true)
5. La reponse est detectee par surveillance du presse-papier
6. Le resultat est renvoye au proxy puis au client

Architecture technique
- proxy.py : Serveur HTTP asynchrone (asyncio), jobs manager, interface web, endpoints API REST
- extension/background.js : Service Worker, polling HTTP, communication proxy<->content script, gestion debugger
- extension/content.js : Content Script injecte dans l'onglet IA, fonctions de clic, paste, scroll, calibration, boucle d'automatisation
- extension/floating.html + floating.js : Fenetre flottante persistante (controles, profils, statut)
- client.py : Client interactif en terminal
- install.sh : Script d'installation (verification dependances, creation venv)

Technologies
- Python 3 (asyncio, json, urllib, uuid) - standard library uniquement
- JavaScript (Firefox WebExtensions API, Manifest v3)
- xdotool (clic souris natif X11 avec isTrusted=true)
- Firefox 109+

Cycle d'automatisation
1. Copier la question dans le presse-papier (navigator.clipboard.writeText)
2. Clic zone texte (clickAt -> element.click + MouseEvent)
3. Coller le texte (execCommand paste)
4. Clic bouton Envoyer
5. Boucle toutes les 2 secondes :
   - scrollDown (window.scrollBy + conteneurs scrollables)
   - clic bouton Copier (clickAtCopyButton -> xdotool via proxy)
   - lectures multiples du presse-papier (execCommand paste)
   - detection : contenu different de la question ET different du precedent

Calibration
Overlay semi-transparent injecte dans l'onglet IA. L'utilisateur clique successivement sur :
1. La zone de saisie de texte
2. Le bouton Envoyer
3. Le bouton Copier du dernier message
Les coordonnees sont sauvegardees dans browser.storage.local par profil (ex: ChatGPT, DeepSeek).

Problemes resolus
- Clic programmatique non fonctionnel sur bouton Copier (isTrusted=false ignore par React/Vue)
  Solution : xdotool pour generer de vrais clics X11 natifs
- Detection de fin de generation : lecture multiple du presse-papier apres clic Copier
- Coordonnees ecran vs viewport : conversion via window.mozInnerScreenX/Y et devicePixelRatio
- Fonctionnement multi-onglets : l'extension cible un tabId specifique, peut tourner en arriere-plan
- Interface utilisateur : fenetre flottante persistante avec controles et statut

Etat d'avancement (30 mai 2026)
- Extension Firefox : operationnelle (calibration, automatisation, fenetre flottante)
- Proxy HTTP : operationnel (endpoints API, interface web, polling)
- Client interactif : operationnel
- Clics xdotool : operationnels (souris physique, coordonnees absolues)
- Interface web : operationnelle (chat, accessible depuis le reseau local)
- Proxy OpenAI : en pause (problemes de parsing HTTP/keep-alive)
- Upload de fichiers : non implemente (abandonne apres tests)
- Fonctionnement arriere-plan sans bouger la souris : non resolu (ydotool instable, python-xlib inefficace)

Etat proxy OpenAI (juillet 2026) — v2.3 send + delta
- proxy_openai.py : OpenAI + BrowserSession (toujours send via composer)
- Pack **delta** uniquement (pas d'historique empilé ; contexte = serveurs DeepSeek)
- Jobs : mode send uniquement (regenerate abandonné — limite plateforme ~7)
- POST /v1/sessions/reset · GET /v1/session
- Extension v2.3 : DOM DeepSeek (composer bas → send → wait assistant)
- Pas de xdotool / calibration / edit SVG
- NEMESIS CLI : BridgeProvider.reset_browser_session() sur /clear
- Stateful CLI : system une fois côté batch ; proxy re-seed system après reset

Prochaines etapes
- Mode streaming SSE (optionnel)
- Ajouter la gestion du DISPLAY pour environnement VNC/headless
- Support multi-fenetres Firefox
- Emballage en extension Firefox signee (signing AMO)

Structure du depot
nemapi-extension/
  proxy.py              Serveur HTTP + interface web
  client.py             Client interactif terminal
  install.sh            Script d'installation
  requirements.txt      Dependances Python
  README.md             Documentation utilisateur
  NEMESIS.md            Documentation technique (ce fichier)
  extension/
    manifest.json       Configuration Firefox
    background.js       Service Worker (polling, debugger)
    content.js          Content Script (automatisation, calibration)
    floating.html       Fenetre flottante
    floating.js         Script fenetre flottante
    icons/logo.png      Icone
