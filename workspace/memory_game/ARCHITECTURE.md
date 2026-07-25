# 🧠 Memory Game - Architecture

## Projet 100% Frontend
Le jeu de memory fonctionne entièrement côté client (HTML/CSS/JS).

## Spécifications UI (délégué à Gemini)

### Composants
| Composant | Description |
|-----------|-------------|
| Grille de cartes | 4x4 (16 cartes, 8 paires) |
| Cartes | Face cachée au départ, se retournent au clic |
| Score | Compteur de coups et paires trouvées |
| Message de victoire | Félicitations quand toutes les paires sont trouvées |
| Bouton Rejouer | Nouvelle partie avec cartes mélangées |

### Design
- Palette moderne et ludique (dégradés, ombres)
- Animations de retournement fluides (CSS transform)
- Émojis comme symboles sur les cartes
- Responsive (adapté mobile)

### Logique JS
- Mélange aléatoire des cartes (Fisher-Yates)
- Retourner 2 cartes max à la fois
- Vérifier si les 2 cartes sont identiques
- Si paire trouvée → rester face visible
- Si pas paire → retourner après 1 seconde
- Détection de victoire (toutes paires trouvées)

### Fichier unique
- `memory_game/index.html` — Tout le code HTML+CSS+JS

## Pas de backend requis
