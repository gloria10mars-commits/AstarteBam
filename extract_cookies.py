import json, os, sys
from pathlib import Path

# Add Gemini-Chat-API to path
sys.path.insert(0, "/home/leon/Gemini-Chat-API")
from gemini_client.cookie_manager import CookieExtractor

try:
    extractor = CookieExtractor()
    cookies = extractor.extract_cookies(save_to_disk=False)
    
    # We need __Secure-1PSID and __Secure-1PSIDTS
    psid = cookies.get("__Secure-1PSID") or cookies.get("SECURE_1PSID")
    psidts = cookies.get("__Secure-1PSIDTS") or cookies.get("SECURE_1PSIDTS")
    
    if psid:
        print(f"OK: Found cookies")
        # Save to cookies_fixed.json in the format expected by Chatbot
        payload = [{"name": "__Secure-1PSID", "value": psid}]
        if psidts:
            payload.append({"name": "__Secure-1PSIDTS", "value": psidts})
        
        with open("/home/leon/Gemini-Chat-API/cookies_fixed.json", "w") as f:
            json.dump(payload, f, indent=2)
        print("Saved to /home/leon/Gemini-Chat-API/cookies_fixed.json")
    else:
        print("Error: __Secure-1PSID not found in browser cookies")
except Exception as e:
    print(f"Extraction failed: {e}")
