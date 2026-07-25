"""
NEMAPI Bridge - Client interactif
Usage: python client.py
"""

import sys
import time
import urllib.request
import urllib.parse

PROXY = "http://127.0.0.1:8080"


def ask(question):
    params = urllib.parse.urlencode({"q": question})
    url = f"{PROXY}/ask?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.read().decode().strip()
    except Exception as e:
        print(f"Proxy inaccessible: {e}")
        return None


def poll(job_id, timeout=240):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{PROXY}/result?id={job_id}", timeout=5) as resp:
                result = resp.read().decode().strip()
        except Exception:
            time.sleep(2)
            continue
        
        if result == "STILL_WORKING":
            elapsed = int(time.time() - start)
            print(f"  ... {elapsed}s", end="\r")
            time.sleep(2)
        elif result == "ANNULÉ":
            print("\nAnnule.")
            return None
        elif result.startswith("Erreur"):
            print(f"\n{result}")
            return None
        else:
            print(f"\r  Recu en {int(time.time() - start)}s\n")
            print(result)
            return result
    
    print(f"\nTimeout ({timeout}s)")
    return None


def main():
    try:
        urllib.request.urlopen(f"{PROXY}/", timeout=3)
    except Exception:
        print("Proxy inaccessible. Lance: python proxy.py")
        sys.exit(1)
    
    print("NEMAPI Bridge - Tape /quit pour quitter\n")
    
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break
        
        if not question:
            continue
        if question.lower() == "/quit":
            print("Au revoir.")
            break
        
        job_id = ask(question)
        if not job_id:
            print("Erreur: job non cree. L'extension est connectee ?\n")
            continue
        
        poll(job_id)
        print()


if __name__ == "__main__":
    main()
