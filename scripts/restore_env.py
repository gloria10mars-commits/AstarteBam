from pathlib import Path

p = Path("/home/leon/AstarteBam/.env")
text = p.read_text(encoding="utf-8")

nemapi_config = """
# DeepSeek / NEMAPI Configuration
NEMAPI_ENABLED=true
NEMAPI_KEY=sk-deepseek-local
NEMAPI_BASE_URL=http://127.0.0.1:8080/v1
NEMAPI_MODEL=deepseek-web
NEMAPI_RESET_ON_NEW_TASK=true
"""

if "NEMAPI_ENABLED" not in text:
    # Ajouter à la fin du fichier
    text += "\n" + nemapi_config
    p.write_text(text, encoding="utf-8")
    print("Configuration NEMAPI restaurée dans .env.")
else:
    print("Configuration NEMAPI déjà présente.")
