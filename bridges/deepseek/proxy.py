#!/usr/bin/env python3
"""
Point d'entrée NEMAPI Bridge — lance le proxy OpenAI-compatible.

  python proxy.py
  # équivalent à: python proxy_openai.py

L'ancien protocole /ask + /result reste disponible sur le même serveur
(compat) ; l'API recommandée est POST /v1/chat/completions.
"""

from __future__ import annotations

import asyncio

from proxy_openai import main


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nArrêt demandé par Ctrl+C : proxy fermé proprement.")
    except OSError as exc:
        if getattr(exc, "errno", None) == 98:
            print("[NEMAPI] Port 8080 déjà utilisé : une instance du proxy est déjà active.")
            print("[NEMAPI] Utilisez ./stop_proxy.sh puis relancez ./start_proxy.sh.")
        else:
            raise
