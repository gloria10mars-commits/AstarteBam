import sys, os
sys.path.insert(0, "/home/leon/Gemini-Chat-API")
from gemini_client import Chatbot, Model
print("Init...", flush=True)
bot = Chatbot(cookie_path="/home/leon/Gemini-Chat-API/cookies_fixed.json", model=Model.G_2_5_FLASH, timeout=90)
print("Ask...", flush=True)
res = bot.ask("Test direct.")
print(f"RESULT: {res}", flush=True)