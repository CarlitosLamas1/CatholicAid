"""Graba las voces de la muestra del Rosario (rosario/guion_muestra.json).

SOLO con la clave gratuita (GEMINI_API_KEY): si se acaba el cupo gratis, se para. Nunca usa la clave de pago.
Una petición por grabación (4 en total); cada una lee varios párrafos con una pausa larga entre ellos, que luego se
cortan en el montaje. Deja los WAV en rosario/salida/.
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

RAIZ = pathlib.Path(__file__).resolve().parent
GUION = json.loads((RAIZ / "guion_muestra.json").read_text(encoding="utf-8"))
SALIDA = RAIZ / "salida"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def pedir(modelo, cuerpo, clave):
    req = urllib.request.Request(URL.format(modelo), json.dumps(cuerpo).encode(),
                                 {"Content-Type": "application/json", "x-goog-api-key": clave})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main():
    clave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not clave:
        sys.exit("Falta GEMINI_API_KEY")
    SALIDA.mkdir(exist_ok=True)
    modelo = GUION["modelo"]
    for n, g in enumerate(GUION["grabaciones"]):
        textos = [t for _, t in g["partes"]]
        if g.get("repetir"):  # una oración varias veces, como en el rosario (sin esto el modelo se salta repeticiones)
            prompt = (f"Lee en voz alta, con {g['estilo']}, esta oración {g['repetir']} veces seguidas, como en el rezo "
                      "del rosario, con una pausa clara de dos segundos entre cada vez. Lee solo la oración:\n\n"
                      + textos[0])
        elif len(textos) == 1:
            prompt = f"Lee en voz alta, con {g['estilo']}, este texto:\n\n{textos[0]}"
        else:
            prompt = (f"Lee en voz alta, con {g['estilo']}, los siguientes párrafos, en este orden. Entre un párrafo y "
                      "el siguiente haz siempre una pausa clara de dos segundos. Lee solo el texto de los párrafos:\n\n"
                      + "\n\n".join(textos))
        cuerpo = {"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                      "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": g["voz"]}}}}}
        for intento in range(3):
            try:
                r = pedir(modelo, cuerpo, clave)
                dato = r["candidates"][0]["content"]["parts"][0]["inlineData"]
                break
            except urllib.error.HTTPError as e:
                print(f"{g['id']}: Gemini {e.code} {e.read().decode(errors='replace')[:300]}")
                if e.code == 429:
                    sys.exit("Cupo gratis agotado: paro (la muestra no usa la clave de pago).")
                if intento == 2 or e.code not in (500, 502, 503, 504):
                    raise
            except (KeyError, IndexError):
                print(f"{g['id']}: respuesta sin audio (intento {intento + 1})")
                if intento == 2:
                    raise
            time.sleep(20 * (intento + 1))
        bruto = base64.b64decode(dato["data"])
        destino = SALIDA / f"{g['id']}.wav"
        if bruto[:4] == b"RIFF":
            destino.write_bytes(bruto)
        else:
            m = re.search(r"rate=(\d+)", dato.get("mimeType", ""))
            with wave.open(str(destino), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(int(m.group(1)) if m else 24000)
                w.writeframes(bruto)
        with wave.open(str(destino)) as w:
            print(f"{g['id']}: {w.getnframes() / w.getframerate():.1f} s")
        if n + 1 < len(GUION["grabaciones"]):
            time.sleep(25)


if __name__ == "__main__":
    main()
