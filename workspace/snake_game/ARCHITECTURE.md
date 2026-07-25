# 🐍 Snake Game - Architecture

## Projet 100% Frontend
Le jeu Snake fonctionne entièrement côté client (HTML/CSS/JS).

## Spécifications UI (délégué à Gemini)

### Composants
| Composant | Description |
|-----------|-------------|
| Canvas | Zone de jeu où le serpent se déplace |
| Serpent | Segments colorés, tête distincte |
| Pomme | Apparaît aléatoirement, mangée = +1 segment |
| Score | Affichage du score en temps réel |
| Game Over | Écran de fin avec score final |
| Bouton Rejouer | Redémarre la partie |

### Gameplay
- Serpent se déplace dans 4 directions (flèches clavier)
- Manger une pomme → score +1, serpent s'allonge
- Collision avec les murs → Game Over
- Collision avec soi-même → Game Over
- Vitesse constante (intervalle 100-150ms)
- Empêcher le demi-tour (ex: gauche → droite)

### Design
- Fond sombre élégant
- Serpent vert néon avec tête plus claire
- Pomme rouge avec effet lumineux
- Canvas avec bordure arrondie
- Animations fluides

### Fichier unique
- `snake_game/index.html` — Tout le code HTML+CSS+JS

## Pas de backend requis
