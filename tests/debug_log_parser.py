import re

with open("/home/leon/AstarteBam/workspace/logs/activity.log", "r", encoding="utf-8") as f:
    content = f.read()

# Find all occurrences of IA-SUCCESS and the text after it
matches = re.findall(r'\[IA-SUCCESS\] Réponse reçue \((\d+) chars\)(.*?)(?=\[\d{4}-\d{2}-\d{2}|$)', content, re.DOTALL)

for i, (size, text) in enumerate(matches):
    print(f"--- Match {i} (Size: {size}) ---")
    print(text.strip()[:300] + "...")
