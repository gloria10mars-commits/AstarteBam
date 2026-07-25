import sys, json, re
sys.path.insert(0, "/home/leon/Gemini-Chat-API")
from curl_cffi.requests import Session

# Load extracted cookies
with open("/home/leon/Gemini-Chat-API/cookies_fixed.json", "r") as f:
    cookies_list = json.load(f)
cookies = {c["name"]: c["value"] for c in cookies_list}

s = Session(impersonate="chrome120")
r = s.get("https://gemini.google.com/app", cookies=cookies, timeout=30)
print(f"Status: {r.status_code}")
print(f"URL: {r.url}")
print(f"Body length: {len(r.text)}")

if "SNlM0e" in r.text:
    print("OK: SNlM0e found in body!")
    m = re.search(r'"SNlM0e":"(.*?)"', r.text)
    if m:
        print(f"SNlM0e value: {m.group(1)[:20]}...")
else:
    print("ERROR: SNlM0e NOT found")
    if "Sign in" in r.text or "accounts.google.com" in r.url:
        print("Reason: Redirected to Login (Cookies invalid?)")
    else:
        print("Reason: Unknown (Page structure changed?)")
        print("Body snippet:", r.text[:1000])
