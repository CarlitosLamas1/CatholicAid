"""Pinta las escenas de rosario/escenas_dolorosos.json con el modelo barato (gemini-2.5-flash-image, ~0,04 € cada una).
Cada escena se pinta viendo la anterior del mismo misterio, para que los personajes no cambien."""
import json
import os
import pathlib
import sys
import time

os.environ["MODELO_IMAGEN"] = "gemini-2.5-flash-image"  # nunca el Pro
RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "proceso"))
import imagenes  # noqa: E402

imagenes.PREFERIDOS = ["gemini-2.5-flash-image"]
salida = RAIZ / "rosario" / "pinturas"
salida.mkdir(exist_ok=True)
escenas = json.loads((RAIZ / "rosario" / "escenas_dolorosos.json").read_text(encoding="utf-8"))["escenas"]
hechas = 0
for e in escenas:
    destino = salida / f"dolorosos_{e['id']}.jpg"
    anterior = salida / f"dolorosos_{e['id'][0]}a.jpg" if not e["id"].endswith("a") else None
    refs = [(n.capitalize() if n != "jesus" else "Jesus", RAIZ / "personajes" / f"{n}.png") for n in e["refs"]]
    try:
        m = imagenes.generar(e["escena"], destino, refs, "oleo", anterior=anterior)
        hechas += 1
        print(f"{e['id']}: ok ({m})", flush=True)
    except Exception as ex:
        print(f"{e['id']}: FALLO {ex}", flush=True)
    time.sleep(6)
print(f"Pintadas {hechas} de {len(escenas)} (~{hechas * 0.04:.2f} €)")
