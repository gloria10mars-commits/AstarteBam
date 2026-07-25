import sys, os, time
sys.path.insert(0, "/home/leon/Gemini-Chat-API")
from gemini_client import Chatbot, Model

print(f"[{time.ctime()}] Start Init...")
try:
    bot = Chatbot(cookie_path="/home/leon/Gemini-Chat-API/cookies_fixed.json", model=Model.G_3_1_PRO, timeout=30)
    print(f"[{time.ctime()}] Init Done. Asking...")
    res = bot.ask("Dis TEST_DEBUG")
    print(f"[{time.ctime()}] Response: {res}")
except Exception as e:
    print(f"[{time.ctime()}] ERROR: {e}")
