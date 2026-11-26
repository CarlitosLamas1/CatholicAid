"""Letanías lauretanas en UNA grabación a dos voces (Gemini multi-speaker): él invoca, ella responde.

Lee rosario/v2/letanias.json. Comprueba con faster-whisper que se oye todo (si no, repite, hasta 3 veces) y guarda los
tiempos de cada línea (para el texto en pantalla). Salida: rosario/salida/letanias.wav y letanias_tiempos.json."""
import base64
import difflib
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request
import wave

import numpy as np
from faster_whisper import WhisperModel

RAIZ = pathlib.Path(__file__).resolve().parents[2]
L = json.loads((RAIZ / "rosario" / "v2" / "letanias.json").read_text(encoding="utf-8"))
SALIDA = RAIZ / "rosario" / "salida"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
CLAVE = os.environ["GEMINI_API_KEY_IMAGENES"].strip()
OIDO = WhisperModel("small", device="cpu", compute_type="int8")
norm = lambda t: re.sub(r"[^a-záéíóúüñ ]", " ", t.lower()).split()  # noqa: E731
G, R = L["guia"], L["respuesta"]


def grabar(destino):
    dialogo = "\n".join(f"{G['nombre']}: {x['a']}\n{R['nombre']}: {x['b']}" for x in L["lineas"])
    prompt = (f"Lee este diálogo: es el rezo de las letanías lauretanas en una parroquia, sin prisa pero con ritmo "
              f"natural, con una pausa breve entre cada invocación. {G['nombre']}: {G['estilo']}. "
              f"{R['nombre']}: {R['estilo']}. Lee todas las líneas, sin saltarte ninguna:\n\n{dialogo}")
    cuerpo = {"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"multiSpeakerVoiceConfig": {
                  "speakerVoiceConfigs": [
                      {"speaker": G["nombre"], "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": G["voz"]}}},
                      {"speaker": R["nombre"], "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": R["voz"]}}}]}}}}
    for intento in range(6):
        try:
            req = urllib.request.Request(URL.format(L["modelo"]), json.dumps(cuerpo).encode(),
                                         {"Content-Type": "application/json", "x-goog-api-key": CLAVE})
            with urllib.request.urlopen(req, timeout=300) as r:
                dato = json.load(r)["candidates"][0]["content"]["parts"][0]["inlineData"]
            bruto = base64.b64decode(dato["data"])
            if len(bruto) < 48000:
                raise ValueError("audio vacío")
            break
        except urllib.error.HTTPError as e:
            print(f"   Gemini {e.code}: {e.read().decode(errors='replace')[:200]}", flush=True)
            time.sleep(60 * (intento + 1))
        except (KeyError, IndexError, ValueError) as e:
            print(f"   sin audio ({e})", flush=True)
            time.sleep(10)
    else:
        raise RuntimeError("Gemini no devolvió audio")
    if bruto[:4] == b"RIFF":
        destino.write_bytes(bruto)
        return
    m = re.search(r"rate=(\d+)", dato.get("mimeType", ""))
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(m.group(1)) if m else 24000)
        w.writeframes(bruto)


def tiempos(ruta):
    """Empareja lo oído con el texto: (cubierto, [(inicio, fin) de cada invocación y de cada respuesta])."""
    with wave.open(str(ruta)) as w:
        hz = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    x = np.interp(np.arange(0, len(x), hz / 16000), np.arange(len(x)), x).astype(np.float32)
    oidas = [(t, w.start, w.end) for sg in OIDO.transcribe(x, language="es", word_timestamps=True)[0]
             for w in (sg.words or []) for t in norm(w.word)]
    objetivo, duena = [], []
    for i, ln in enumerate(L["lineas"]):
        for parte, texto in ((0, ln["a"]), (1, ln["b"])):
            for t in norm(texto):
                objetivo.append(t)
                duena.append((i, parte))
    sm = difflib.SequenceMatcher(None, objetivo, [o[0] for o in oidas], autojunk=False)
    por = {}
    casados = 0
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            por.setdefault(duena[a + k], []).append(b + k)
            casados += 1
    lineas = []
    for i in range(len(L["lineas"])):
        fila = []
        for parte in (0, 1):
            idx = por.get((i, parte))
            fila.append([oidas[min(idx)][1], oidas[max(idx)][2]] if idx else None)
        lineas.append(fila)
    return casados / len(objetivo), lineas


def main():
    SALIDA.mkdir(exist_ok=True)
    mejor = (-1, None, None)
    for intento in range(3):
        ruta = SALIDA / f"letanias_{intento}.wav"
        try:
            grabar(ruta)
        except Exception as e:
            print(f"intento {intento + 1}: falló ({e})", flush=True)
            continue
        cubierto, lineas = tiempos(ruta)
        faltan = sum(1 for f in lineas for t in f if t is None)
        with wave.open(str(ruta)) as w:
            dur = w.getnframes() / w.getframerate()
        print(f"intento {intento + 1}: {dur:.0f} s · se oye el {cubierto:.0%} del texto · {faltan} partes sin localizar",
              flush=True)
        if cubierto > mejor[0]:
            mejor = (cubierto, ruta, lineas)
        if cubierto >= 0.93:
            break
        time.sleep(20)
    cubierto, ruta, lineas = mejor
    ruta.replace(SALIDA / "letanias.wav")
    (SALIDA / "letanias_tiempos.json").write_text(json.dumps({"cubierto": cubierto, "lineas": lineas}, indent=1))
    print(f"Elegido: se oye el {cubierto:.0%}")


if __name__ == "__main__":
    main()
