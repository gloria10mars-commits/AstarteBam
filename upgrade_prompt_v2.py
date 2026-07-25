from pathlib import Path
path = Path("/home/leon/AstarteBam/config/system_prompt_collaboratif_v1.txt")
text = path.read_text(encoding="utf-8")

# 1. Mise à jour du format autorisé
old_format = """Format autorisé :

```json
{
  "version": 1,
  "stop_on_error": false,
  "cwd": "",
  "actions": [
    {"type": "exec", "args": "commande shell", "content": "stdin optionnel"},
    {"type": "write_file", "args": "fichier.txt", "content": "contenu"}
  ]
}
```"""

new_format = """Format autorisé (Protocole v2) :

```json
{
  "version": 2,
  "thought": "Ta réflexion stratégique ici (Chain of Thought). Analyse la demande, identifie les risques et planifie tes étapes.",
  "stop_on_error": false,
  "cwd": "",
  "actions": [
    {"type": "exec", "args": "commande shell", "content": "stdin"},
    {"type": "write_file", "args": "fichier.txt", "content": "contenu"}
  ]
}
```"""

text = text.replace(old_format, new_format)

# 2. Modifier les règles de validation des champs
text = text.replace('- Les seuls champs autorisés au niveau principal sont version, stop_on_error, cwd,\n  actions.', 
                    '- Les champs autorisés au niveau principal sont version, thought, stop_on_error, cwd, actions.')
text = text.replace('- NE METS PAS "role", "plan", "comment", "reasoning", "message" ou un autre\n  champ au niveau principal',
                    '- NE METS PAS "role", "plan" ou "message" au niveau principal')

path.write_text(text, encoding="utf-8")
print("System Prompt mis à jour vers le Protocole v2 (Réflexion activée).")
