#!/usr/bin/env python3
"""CatholicAid · Prueba del alineador de subtítulos sobre un vídeo ya hecho (sin gastar cupo de voces).
Uso: python3 proceso/probar_alineador.py <carpeta con guion.json y video.mp4>
Compara, fragmento a fragmento, dónde empezaba el subtítulo antes (reparto por longitud) y dónde se oye de verdad."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

carpeta = Path(sys.argv[1])
reg = json.loads((carpeta / "guion.json").read_text(encoding="utf-8"))
ev.aplicar_idioma(reg.get("idioma", "es"))
wav = carpeta / "voz.wav"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(carpeta / "video.mp4"), "-ac", "1", "-ar", "16000",
                str(wav)], check=True)
os.environ["DEPURAR_ALINEADOR"] = "1"
frs = [dict(f) for f in reg["fragmentos"]]
for a, b in zip(frs, frs[1:]):
    a["fin"] = b["inicio"]
frs[-1]["fin"] = reg["duracion_s"] - float(ev.CFG.get("cierre_segundos", 0))
antes = [(f["inicio"], f["fin"]) for f in frs]
estimadas = [ev.tiempos_palabras(dict(f), ev.espacios(f["texto"]).split()) for f in frs]
ok = ev.alinear_audio(frs, wav)
print("Alineación fiable:", ok)
peor = 0.0
for f, (a, _), est in zip(frs, antes, estimadas):
    reales = f.get("palabras_t") or []
    dif = max((abs(x[0] - y[0]) for x, y in zip(est, reales)), default=0.0)
    peor = max(peor, dif)
    print(f"{f['personaje']:>9} · antes {a:6.2f} s · oído {f['inicio']:6.2f} s · desfase máx. de palabra {dif:4.2f} s · "
          f"{f['texto'][:50]}")
    print("      " + " ".join(f"{w}@{t[0]:.2f}" for w, t in zip(ev.espacios(f["texto"]).split(), reales)))
print(f"DESFASE MÁXIMO ANTES: {peor:.2f} s")
