#!/usr/bin/env python3
"""
fetch_meteo.py — One-shot : récupère les données APDL, consolide, écrit live.json.

Utilisé par GitHub Actions (.github/workflows/fetch_meteo.yml) toutes les 15 min.
En cas d'échec APDL, conserve le dernier live.json valide et le marque "stale":true
afin de ne jamais publier un fichier cassé.

Usage : python3 fetch_meteo.py [chemin_sortie]   (défaut: public/live.json)
"""

import json
import os
import sys
from datetime import datetime, timezone

import meteo_core


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "public/live.json"
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    try:
        raw = meteo_core.fetch_all()
        data = meteo_core.consolidate(raw)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"OK  -> {out_path}  updated_at={data['updated_at']}  "
              f"vento={data['wind']['speed_kn']}kn  agua={data['sea']['water_temp_c']}C")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FETCH FAILED: {exc}", file=sys.stderr)
        # Marque l'ancien fichier comme périmé s'il existe, sinon échoue.
        if os.path.exists(out_path):
            try:
                with open(out_path, "r", encoding="utf-8") as fh:
                    old = json.load(fh)
                old["stale"] = True
                old["stale_since"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                with open(out_path, "w", encoding="utf-8") as fh:
                    json.dump(old, fh, ensure_ascii=False, separators=(",", ":"))
                print("Kept previous live.json, marked stale=true", file=sys.stderr)
                return 0
            except Exception as exc2:  # noqa: BLE001
                print(f"Could not preserve previous file: {exc2}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
