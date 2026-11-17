#!/usr/bin/env python3
"""Vista previa de subtítulos y gancho SIN gastar voces ni imágenes: con el registro de un vídeo ya hecho, pinta
sobre una imagen del día unos fotogramas con los ajustes actuales («nuevo») y con los de antes del 17/11/2026
(«antes»: letra 60, trozos de 46, gancho del registro). Salida: vista/<modo>_<segundo>.jpg y vista/comparacion.jpg.
Uso: python3 proceso/vista_subtitulos.py AAAA-MM-DD"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402
from PIL import Image  # noqa: E402

fecha = dt.date.fromisoformat(sys.argv[1])
reg = json.loads((ev.RAIZ / "episodios" / f"{fecha}.json").read_text(encoding="utf-8"))
imagen = next(iter(sorted((ev.RAIZ / "biblioteca" / "dias").glob(f"{fecha}_e*.*"))), None)
salida = ev.RAIZ / "vista"
salida.mkdir(exist_ok=True)
cierre = float(ev.CFG.get("cierre_segundos", 2.5))
nuevos = (dict(ev.CFG.get("subtitulos") or {}), ev.CFG.get("caracteres_por_subtitulo"))
filas = []
for modo in ("antes", "nuevo"):
    if modo == "antes":
        ev.CFG.pop("subtitulos", None)
        ev.CFG["caracteres_por_subtitulo"] = 46
        g = float(reg["gancho_segundos"])
    else:
        ev.CFG["subtitulos"], ev.CFG["caracteres_por_subtitulo"] = nuevos
        g = ev.gancho_del_dia(fecha, reg["frase_clave"])
    desp = g - float(reg["gancho_segundos"])
    frs = [dict(f) for f in reg["fragmentos"]]
    for f in frs:
        f["inicio"] += desp
    total = float(reg["duracion_s"]) + desp
    for a, b in zip(frs, frs[1:]):
        a["fin"] = b["inicio"]
    frs[-1]["fin"] = total - cierre
    ass = salida / f"{modo}.ass"
    ev.subtitulos(frs, {"cita": reg["cita"]}, fecha, total, ass, reg["frase_clave"], g, cierre)
    largos = sorted(frs[1:-1], key=lambda f: -len(f["texto"]))[:2]  # dos fragmentos largos (Jesús, narrador…)
    momentos = [g / 2] + [f["inicio"] + 1.5 for f in largos]
    fotos = []
    for t in momentos:
        destino = salida / f"{modo}_{t:05.1f}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(imagen), "-t", f"{total:.1f}",
                        "-vf", f"scale=1080:1920,ass={ass.name}", "-ss", f"{t:.2f}", "-frames:v", "1", destino.name],
                       check=True, cwd=salida)
        fotos.append(Image.open(destino).resize((540, 960)))
    print(f"{modo}: gancho {g} s · fotogramas en {', '.join(f'{t:.1f}' for t in momentos)} s")
    filas.append(fotos)
hoja = Image.new("RGB", (540 * 3, 960 * 2), "black")
for y, fila in enumerate(filas):
    for x, im in enumerate(fila):
        hoja.paste(im, (540 * x, 960 * y))
hoja.save(salida / "comparacion.jpg", quality=85)
print("Arriba: antes · abajo: nuevo")
