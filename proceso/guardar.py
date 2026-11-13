#!/usr/bin/env python3
"""Guarda en main los cambios de un workflow sin chocar con otros que escriben a la vez.

Uso: python3 proceso/guardar.py "mensaje" carpeta1/ carpeta2/ ...

Antes se hacía «git pull --rebase»: si TikTok e Instagram añadían a la vez su dato al mismo registro
(episodios/AAAA-MM-DD.json), el rebase chocaba, no se guardaba lo publicado y la siguiente pasada
volvía a publicar (14/11/2026: Reels duplicados). Aquí, en los JSON solo se aplican las claves que
este workflow cambió, encima de la versión más reciente de main; los demás archivos se copian tal cual.
"""
import json
import subprocess
import sys
import time
from pathlib import Path


def git(*args, check=True):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check).stdout


def anterior(ruta):
    r = subprocess.run(["git", "show", f"HEAD:{ruta}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def main():
    mensaje, carpetas = sys.argv[1], sys.argv[2:]
    rutas = set(git("diff", "--name-only", "HEAD", "--", *carpetas).split())
    rutas |= set(git("ls-files", "--others", "--exclude-standard", "--", *carpetas).split())
    if not rutas:
        print("Nada que guardar.")
        return
    cambios = {}
    for r in sorted(rutas):
        p = Path(r)
        nuevo = p.read_bytes() if p.exists() else None
        viejo = anterior(r)
        if r.endswith(".json") and nuevo is not None:
            try:
                n = json.loads(nuevo)
                v = json.loads(viejo) if viejo else {}
                if isinstance(n, dict) and isinstance(v, dict):
                    cambios[r] = ("claves", {k: n[k] for k in n if v.get(k, object()) != n[k]},
                                  [k for k in v if k not in n])
                    continue
            except ValueError:
                pass
        cambios[r] = ("entero", nuevo, None)
    for intento in range(6):
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        for r, (tipo, datos, borrar) in cambios.items():
            p = Path(r)
            if tipo == "claves":
                d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
                d.update(datos)
                for k in borrar:
                    d.pop(k, None)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            elif datos is None:
                p.unlink(missing_ok=True)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(datos)
        git("add", "-A", "--", *cambios.keys())
        if not git("diff", "--cached", "--name-only"):
            print("Ya estaba guardado.")
            return
        git("commit", "-q", "-m", mensaje)
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"]).returncode == 0:
            print("Guardado:", ", ".join(sorted(cambios)))
            return
        time.sleep(3 + 4 * intento)
    sys.exit("No se pudo guardar en main tras varios intentos.")


if __name__ == "__main__":
    main()
