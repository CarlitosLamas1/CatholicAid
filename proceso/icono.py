#!/usr/bin/env python3
"""CatolicAid · Propuesta de icono del canal: Gemini (texto) propone el concepto y Nano Banana lo pinta.

Uso: python3 proceso/icono.py salida_dir [--idea "texto"]   (deja propuesta.png y propuesta.json en salida_dir)
Texto con GEMINI_API_KEY (gratis); imagen con GEMINI_API_KEY_IMAGENES (de pago, céntimos).
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imagenes  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CFG = json.loads((RAIZ / "config" / "personajes.json").read_text(encoding="utf-8"))

ENCARGO = """You are a brand designer for «CatolicAid», a non-profit Catholic project that publishes one short vertical
video every morning with the Gospel of the day, read aloud by several voices over devotional paintings and soft
classical music, in Spanish, English and Portuguese (YouTube, TikTok, Instagram). Many viewers are older Latin American
and US Hispanic Catholics.

Propose ONE profile icon (avatar) for all the accounts. Requirements:
- Inspiring, symbolic and reverent. It must NOT be a face or portrait of Jesus or of any person.
- Must stay recognisable at 32x32 px and when cropped to a circle: few shapes, strong contrast, one focal symbol.
- Warm and hopeful, not gloomy; a sense of daily light and the Word. Palette may use gold (#F5C542) and deep blue/night.
- No text, no letters, no watermark. Square composition, symbol centred with generous margin (circle crop safe).
Answer ONLY as JSON with these keys: "nombre" (short name of the concept, in Spanish), "idea" (2-3 sentences in
Spanish explaining the symbolism and why it works small), "prompt_imagen" (a detailed English prompt for an image
model to paint exactly that icon: style, composition, colours, what must be avoided)."""


def pedir_concepto(idea_extra=""):
    ult = None
    for modelo in CFG.get("modelos_texto", ["gemini-3.7-flash"]):
        try:
            cuerpo = {"contents": [{"parts": [{"text": ENCARGO + (f"\nExtra guidance from the owner: {idea_extra}" if idea_extra else "")}]}],
                      "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}}
            req = urllib.request.Request(
                f"{imagenes.API}models/{modelo}:generateContent", data=json.dumps(cuerpo).encode(),
                headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()})
            with urllib.request.urlopen(req, timeout=120) as r:
                texto = json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"]
            d = json.loads(re.sub(r"^```(?:json)?|```$", "", texto.strip()).strip())
            if d.get("prompt_imagen"):
                d["modelo_texto"] = modelo
                return d
        except Exception as e:  # prueba el siguiente modelo
            ult = e
            print(f"[{modelo}] {e}", flush=True)
    raise SystemExit(f"Gemini no propone icono: {ult}")


def pintar(prompt, destino):
    cuerpo = {"contents": [{"parts": [{"text": prompt + "\nSquare 1:1 app icon. No text, no letters, no watermark."}]}],
              "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}}}
    m = imagenes.modelo()
    r = imagenes._http(f"{imagenes.API}models/{m}:generateContent", cuerpo)
    for p in r.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in p:
            imagenes.guardar(base64.b64decode(p["inlineData"]["data"]), destino)
            return m
    raise SystemExit(f"sin imagen: {str(r)[:300]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("salida")
    ap.add_argument("--idea", default="")
    a = ap.parse_args()
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    d = pedir_concepto(a.idea)
    print(json.dumps(d, ensure_ascii=False, indent=2), flush=True)
    d["modelo_imagen"] = pintar(d["prompt_imagen"], out / "propuesta.png")
    (out / "propuesta.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
