"""Graba cada pieza de rosario/guion_dolorosos.json en su propia petición (así Gemini no se salta ninguna).

Clave de pago (decidido para el rosario: céntimos, y el cupo gratis queda para el vídeo diario). Comprueba que la voz
dura lo razonable para el texto (Gemini a veces devuelve silencios enormes o se come frases) y repite si no.
"""
import base64
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
import wave

import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parents[1]  # carpeta rosario/ (este script vive en rosario/v2/)
GUION = json.loads((RAIZ.parent / os.environ.get("GUION", "rosario/v2/guion.json")).read_text(encoding="utf-8"))
SALIDA = RAIZ / "salida"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def pedir(cuerpo, clave):
    req = urllib.request.Request(URL.format(GUION["modelo"]), json.dumps(cuerpo).encode(),
                                 {"Content-Type": "application/json", "x-goog-api-key": clave})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def voz_util(ruta):
    """Segundos con voz (ventanas de 50 ms por encima de -40 dB)."""
    with wave.open(str(ruta)) as w:
        hz = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    v = int(hz * 0.05)
    rms = [np.sqrt(np.mean(x[i:i + v] ** 2)) for i in range(0, len(x) - v, v)]
    return sum(1 for r in rms if r > 0.01) * 0.05


def main():
    clave = os.environ.get("GEMINI_API_KEY_IMAGENES", "").strip()
    if not clave:
        sys.exit("Falta GEMINI_API_KEY_IMAGENES")
    SALIDA.mkdir(exist_ok=True)
    malas = []
    for p in GUION["piezas"]:
        destino = SALIDA / f"{p['id']}.wav"
        prompt = f"Lee en voz alta, con {p['estilo']}, este texto. Lee solo el texto:\n\n{p['texto']}"
        cuerpo = {"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                      "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": p["voz"]}}}}}
        ok = False
        for intento in range(6):
            try:
                dato = pedir(cuerpo, clave)["candidates"][0]["content"]["parts"][0]["inlineData"]
            except urllib.error.HTTPError as e:
                print(f"{p['id']}: Gemini {e.code} {e.read().decode(errors='replace')[:200]}")
                time.sleep(60 * (intento + 1))  # 429: límite por minuto
                continue
            except (KeyError, IndexError):
                print(f"{p['id']}: sin audio")
                time.sleep(5)
                continue
            bruto = base64.b64decode(dato["data"])
            m = re.search(r"rate=(\d+)", dato.get("mimeType", ""))
            with wave.open(str(destino), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(int(m.group(1)) if m else 24000)
                w.writeframes(bruto)
            with wave.open(str(destino)) as w:
                total = w.getnframes() / w.getframerate()
            util = voz_util(destino)
            ritmo = len(p["texto"]) / max(util, 0.1)
            print(f"{p['id']}: {total:.1f} s, {util:.1f} s de voz, {ritmo:.1f} letras/s", flush=True)
            if 9 <= ritmo <= 22 and total < util * 1.8 + 3:  # sin silencios enormes (las pausas naturales sí)
                ok = True
                break
            print(f"{p['id']}: ritmo raro, repito", flush=True)
            time.sleep(5)
        if not ok:
            malas.append(p["id"])
        time.sleep(10)
    print("Piezas dudosas:", malas or "ninguna")


if __name__ == "__main__":
    main()
