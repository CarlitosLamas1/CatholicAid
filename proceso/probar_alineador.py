#!/usr/bin/env python3
"""CatholicAid · Prueba del alineador de subtítulos sobre un vídeo ya hecho (sin gastar cupo de voces).
Uso: python3 proceso/probar_alineador.py <carpeta con guion.json y video.mp4>
Corta el audio de cada fragmento del vídeo y compara el resaltado antiguo (reparto por longitud), el nuevo sin
alineador (reparto por pausas) y el alineador (lo que se oye)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

carpeta = Path(sys.argv[1])
reg = json.loads((carpeta / "guion.json").read_text(encoding="utf-8"))
ev.aplicar_idioma(reg.get("idioma", "es"))
frs = [dict(f) for f in reg["fragmentos"]]
for a, b in zip(frs, frs[1:]):
    a["fin"] = b["inicio"]
frs[-1]["fin"] = reg["duracion_s"] - float(ev.CFG.get("cierre_segundos", 0))
peor_antiguo = peor_pausas = 0.0
for n, f in enumerate(frs):
    wav = carpeta / f"frag{n:02d}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(carpeta / "video.mp4"), "-ss", f"{f['inicio']:.3f}",
                    "-to", f"{f['fin']:.3f}", "-ac", "1", "-ar", "24000", "-sample_fmt", "s16", str(wav)], check=True)
    f["audio"] = str(wav)
    palabras = ev.espacios(f["texto"]).split()
    pesos = [len(x) + 1 for x in palabras]
    antiguo, t = [], f["inicio"]
    for w in pesos:
        d = (f["fin"] - f["inicio"]) * w / sum(pesos)
        antiguo.append((t, t + d))
        t += d
    pausas = ev.reparto_con_pausas(f, palabras)
    oido = ev.alinear_whisper(f, palabras)
    if not oido:
        print(f"{f['personaje']:>9} · alineador no fiable: {f['texto'][:60]}")
        continue
    d1 = max(abs(x[0] - y[0]) for x, y in zip(antiguo, oido))
    d2 = max(abs(x[0] - y[0]) for x, y in zip(pausas, oido))
    peor_antiguo, peor_pausas = max(peor_antiguo, d1), max(peor_pausas, d2)
    print(f"{f['personaje']:>9} · desfase máx. antiguo {d1:4.2f} s · por pausas {d2:4.2f} s · {f['texto'][:50]}")
    print("      " + " ".join(f"{w}@{t[0]:.2f}" for w, t in zip(palabras, oido)))
print(f"DESFASE MÁXIMO · antiguo {peor_antiguo:.2f} s · por pausas (sin alineador) {peor_pausas:.2f} s")
