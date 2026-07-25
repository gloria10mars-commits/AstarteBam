import sys, os
sys.path.insert(0, "/home/leon/AstarteBam")
from core.providers import ProviderRegistry
reg = ProviderRegistry()
try:
    res = reg.call([{"role": "user", "content": "Dis OK."}], preferred="gemini")
    print(f"RESULT: {res}")
except Exception as e:
    print(f"ERROR: {e}")