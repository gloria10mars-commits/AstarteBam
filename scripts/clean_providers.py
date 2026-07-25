import re
from pathlib import Path

path = Path("/home/leon/AstarteBam/core/providers.py")
text = path.read_text(encoding="utf-8")

# On va redéfinir proprement le bloc nemapi dans call()
# Le but est d'avoir un seul bloc propre.

pattern = re.compile(r"elif s\['provider'\]=='nemapi':.*?elif s\['provider'\]", re.DOTALL)
replacement = """elif s['provider']=='nemapi':
            key = self.env.get('NEMAPI_KEY', 'sk-deepseek-local')
            # Pré-check bridge
            try:
                health_url = s['url'].rsplit('/v1', 1)[0] + '/health'
                req_h = urllib.request.Request(health_url, headers={'User-Agent':'AstarteBam/6.0', 'Authorization': 'Bearer ' + key})
                urllib.request.urlopen(req_h, timeout=3)
            except Exception as e:
                raise RuntimeError(f"NEMAPI bridge inaccessible ({health_url}): {e}")
            
            body = {'model': s['model'], 'messages': messages, 'temperature': 0.7, 'max_tokens': 4096}
            headers = {'Content-Type': 'application/json', 'User-Agent': 'AstarteBam/6.0', 'Authorization': 'Bearer ' + key}
        elif s['provider']"""

text = pattern.sub(replacement, text)

# On patche aussi nemapi_request pour inclure la clé
text = text.replace(
    "req = urllib.request.Request(url, method=method, headers={\"User-Agent\":\"AstarteBam/6.0\"})",
    "key = self.env.get('NEMAPI_KEY', 'sk-deepseek-local')\n        req = urllib.request.Request(url, method=method, headers={\"User-Agent\":\"AstarteBam/6.0\", \"Authorization\": \"Bearer \" + key})"
)

path.write_text(text, encoding="utf-8")
print("providers.py unifié et sécurisé.")
