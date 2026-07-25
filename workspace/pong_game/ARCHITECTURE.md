# 🏓 Pong Game - Architecture

## Projet 100% Frontend
Le jeu Pong fonctionne entièrement côté client (HTML/CSS/JS).

## Spécifications UI (délégué à Gemini)

### Composants
| Composant | Description |
|-----------|-------------|
| Canvas | Zone de jeu rectangulaire |
| Raquette gauche | Contrôlée par Joueur 1 (Z/S ou W/S) |
| Raquette droite | Contrôlée par Joueur 2 (Flèches HAUT/BAS) |
| Balle | Rebondit sur les murs et les raquettes |
| Score | Affichage J1 vs J2 |
| Ligne médiane | Pointillés au centre du terrain |
| Message de victoire | Quand un joueur atteint 11 points |

### Gameplay
- Raquette gauche : touches Z (haut) et S (bas)
- Raquette droite : touches Flèche HAUT et Flèche BAS
- Balle accélère légèrement à chaque rebond sur raquette
- Point marqué quand la balle dépasse un côté
- Premier à 11 points gagne
- Bouton Rejouer pour recommencer

### Design
- Fond sombre élégant (noir profond)
- Raquettes blanches avec effet lumineux
- Balle blanche brillante
- Ligne médiane en pointillés subtils
- Scores en grand format
- Animations fluides (requestAnimationFrame)

### Fichier unique
- `pong_game/index.html` — Tout le code HTML+CSS+JS

## Pas de backend requis
