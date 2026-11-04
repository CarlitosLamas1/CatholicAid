#!/usr/bin/env python3
"""CatholicAid · Imágenes con Nano Banana (modelo de imágenes de Gemini) por la API.

Usa la clave GEMINI_API_KEY_IMAGENES (proyecto con facturación). Las imágenes de los
personajes (personajes/*.png) se envían como referencia para que los rostros sean siempre los mismos.

Uso de prueba: python3 proceso/imagenes.py "descripción de la escena" salida.png [--ref personajes/jesus.png]
"""
import argparse
import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
API = "https://generativelanguage.googleapis.com/v1beta/"
PREFERIDOS = ["gemini-3-pro-image-preview", "gemini-2.5-flash-image"]

ESTILO_OLEO = ("Devotional fine-art oil painting with visible, expressive brushstrokes, glowing warm golden divine "
               "light radiating softly, rich warm colors (gold, deep red, cream, soft blue), tender and intimate "
               "emotion full of love and kindness, sacred and peaceful atmosphere.")
ESTILO_ACUARELA = ("Delicate watercolor painting with soft washes, pastel sky with warm peach clouds, wildflower "
                   "meadows, gentle light, tender, hopeful and full of love and kindness.")
REGLAS = ("Vertical 9:16 composition filling the whole frame. Authentic 1st-century Galilee and Judea. "
          "No text, no letters, no signatures, no watermarks, no modern objects. Never violence or blood.")


def clave():
    k = os.environ.get("GEMINI_API_KEY_IMAGENES") or os.environ.get("GEMINI_API_KEY", "")
    return {"x-goog-api-key": k.strip()}


def _http(url, cuerpo=None, timeout=300):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json", **clave()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def modelo():
    """El mejor modelo de imagen disponible para la clave (preferidos primero)."""
    try:
        nombres = [m["name"].split("/")[-1] for m in _http(f"{API}models?pageSize=200").get("models", [])
                   if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception:
        return PREFERIDOS[-1]
    for p in PREFERIDOS:
        if p in nombres:
            return p
    otros = sorted((n for n in nombres if "image" in n and not n.startswith("imagen")), reverse=True)
    return otros[0] if otros else PREFERIDOS[-1]


def _referencia(ruta):
    """Reduce la imagen de referencia a ~1024 px (menos tokens) y la devuelve como parte inlineData."""
    datos = Path(ruta).read_bytes()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp) / "ref.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(ruta), "-vf",
                            "scale='min(1024,iw)':-2", "-q:v", "3", str(salida)], check=True)
            return {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(salida.read_bytes()).decode()}}
    except Exception:
        tipo = "image/png" if str(ruta).lower().endswith(".png") else "image/jpeg"
        return {"inlineData": {"mimeType": tipo, "data": base64.b64encode(datos).decode()}}


def generar(escena, destino, referencias=(), estilo="oleo", intentos=3):
    """Genera una imagen vertical para la escena. referencias: [(nombre, ruta)] p. ej. [("Jesus", "personajes/jesus.png")]."""
    partes = []
    for nombre, ruta in referencias:
        partes.append({"text": f"Reference image of {nombre}: keep exactly this face, hair and clothing."})
        partes.append(_referencia(ruta))
    estilo_txt = ESTILO_ACUARELA if estilo == "acuarela" else ESTILO_OLEO
    partes.append({"text": f"Create a new image. Scene: {escena}\nStyle: {estilo_txt}\n{REGLAS}"})
    cuerpo = {"contents": [{"parts": partes}],
              "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16"}}}
    m = modelo()
    for i in range(intentos):
        try:
            r = _http(f"{API}models/{m}:generateContent", cuerpo)
            for p in r.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in p:
                    Path(destino).write_bytes(base64.b64decode(p["inlineData"]["data"]))
                    return m
            raise RuntimeError(f"sin imagen en la respuesta: {str(r)[:300]}")
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 503) and i < intentos - 1:
                time.sleep(20 * (i + 1))
                continue
            raise RuntimeError(f"{m} -> {e.code}: {msg}")
    raise RuntimeError("no se pudo generar la imagen")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("escena")
    ap.add_argument("destino")
    ap.add_argument("--ref", action="append", default=[], help="ruta de imagen de referencia (nombre = archivo)")
    ap.add_argument("--estilo", default="oleo", choices=["oleo", "acuarela"])
    a = ap.parse_args()
    refs = [(Path(r).stem.capitalize(), r) for r in a.ref]
    print("Modelo:", generar(a.escena, a.destino, refs, a.estilo), "->", a.destino)
