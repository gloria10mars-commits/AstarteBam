"""Contrôle du NEMAPI DeepSeek Bridge local : état, test et reset de session."""
import os, sys
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.providers import ProviderRegistry

def handle(args, cwd, stdin_data=""):
    cmd=(args or "status").strip().lower()
    reg=ProviderRegistry()
    try:
        if cmd in ("status", "etat"):
            info=reg.nemapi_status()
            return {"ok":True,"msg":"Bridge NEMAPI connecté.","data":info}
        if cmd in ("reset", "clear"):
            return {"ok":True,"msg":"Session DeepSeek Bridge réinitialisée.","data":reg.reset_nemapi_session()}
        if cmd == "test":
            raw,slot,error=reg.call([{"role":"user","content":"Réponds uniquement par OK."}],preferred="nemapi")
            return {"ok":not bool(error),"msg":raw if not error else error,"provider":slot}
        return {"ok":False,"error":"Usage : /nemapi status | test | reset"}
    except Exception as exc:
        return {"ok":False,"error":"NEMAPI indisponible : {}".format(exc)}
