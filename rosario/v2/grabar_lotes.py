"""Rosario v2: cada voz graba todas sus piezas de UNA vez (misma voz y tono), se corta por las pausas y se comprueba.

Lee rosario/v2/lotes.json. Por lote: una petición a Gemini (clave de pago) con los párrafos en orden y pausas de 2 s;
se corta por las N-1 pausas más largas y cada trozo se escucha con faster-whisper. Si algo no cuadra (se saltó una
línea, un corte cae mal), se repite el lote entero (hasta 3 veces) y se queda el mejor intento.
Salida: rosario/salida/<id>.wav (48 kHz, mono) y rosario/salida/informe.txt.
"""
import base64
import difflib
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.request
import wave

import imageio_ffmpeg
import numpy as np
from faster_whisper import WhisperModel

RAIZ = pathlib.Path(__file__).resolve().parents[2]
LOTES = json.loads((RAIZ / "rosario" / "v2" / "lotes.json").read_text(encoding="utf-8"))
SALIDA = RAIZ / "rosario" / "salida"
FF = imageio_ffmpeg.get_ffmpeg_exe()
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
CLAVE = os.environ["GEMINI_API_KEY_IMAGENES"].strip()
OIDO = WhisperModel("small", device="cpu", compute_type="int8")
norm = lambda t: re.sub(r"[^a-záéíóúüñ ]", " ", t.lower()).split()  # noqa: E731


def grabar(lote, destino):
    prompt = (f"Lee en voz alta, con {lote['estilo']}, los siguientes párrafos, en este orden. Entre un párrafo y el "
              "siguiente haz siempre una pausa clara de dos segundos. Lee solo el texto de los párrafos, todos y cada "
              "uno, sin saltarte ninguno:\n\n" + "\n\n".join(x["texto"] for x in lote["lineas"]))
    cuerpo = {"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                  "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": lote["voz"]}}}}}
    for intento in range(6):
        try:
            req = urllib.request.Request(URL.format(LOTES["modelo"]), json.dumps(cuerpo).encode(),
                                         {"Content-Type": "application/json", "x-goog-api-key": CLAVE})
            with urllib.request.urlopen(req, timeout=300) as r:
                dato = json.load(r)["candidates"][0]["content"]["parts"][0]["inlineData"]
            break
        except urllib.error.HTTPError as e:
            print(f"   Gemini {e.code}: {e.read().decode(errors='replace')[:150]}", flush=True)
            time.sleep(60 * (intento + 1))
        except (KeyError, IndexError):
            print("   respuesta sin audio", flush=True)
            time.sleep(10)
    else:
        raise RuntimeError("Gemini no devolvió audio")
    m = re.search(r"rate=(\d+)", dato.get("mimeType", ""))
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(m.group(1)) if m else 24000)
        w.writeframes(base64.b64decode(dato["data"]))


def silencios(ruta):
    r = subprocess.run([FF, "-i", str(ruta), "-af", "silencedetect=noise=-40dB:d=0.5", "-f", "null", "-"],
                       capture_output=True, text=True)
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    fin = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(ini, fin))


def duracion(ruta):
    with wave.open(str(ruta)) as w:
        return w.getnframes() / w.getframerate()


def escuchar(ruta):
    with wave.open(str(ruta)) as w:
        hz = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    x = np.interp(np.arange(0, len(x), hz / 16000), np.arange(len(x)), x).astype(np.float32)
    return " ".join(s.text for s in OIDO.transcribe(x, language="es")[0]).strip()


def cortar_y_comprobar(lote, bruto, carpeta):
    lineas = lote["lineas"]
    d = duracion(bruto)
    sil = [(a, b) for a, b in silencios(bruto) if a > 0.2 and b < d - 0.2]
    cortes = sorted(sorted(sil, key=lambda s: s[1] - s[0], reverse=True)[:len(lineas) - 1])
    if len(cortes) != len(lineas) - 1:
        return 0, [f"solo {len(cortes) + 1} trozos para {len(lineas)} líneas"]
    bordes = [0.0] + [x for c in cortes for x in c] + [d]
    notas, buenas = [], 0
    for i, x in enumerate(lineas):
        a, b = bordes[2 * i], bordes[2 * i + 1]
        destino = carpeta / f"{x['id']}.wav"
        subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(bruto),
                        "-ar", "48000", "-ac", "1", "-sample_fmt", "s16", str(destino)], check=True)
        oido = escuchar(destino)
        r = difflib.SequenceMatcher(None, norm(x["texto"]), norm(oido)).ratio()
        minimo = 0.75 if len(norm(x["texto"])) > 4 else 0.4  # frases muy cortas: whisper las oye peor
        ok = r >= minimo
        buenas += ok
        notas.append(f"{'OK ' if ok else 'MAL'} {r:.2f} {x['id']}: {oido}")
    return buenas, notas


def main():
    SALIDA.mkdir(exist_ok=True)
    informe = []
    for lote in LOTES["lotes"]:
        mejor = (-1, None, None)
        for intento in range(3):
            carpeta = SALIDA / f"_{lote['id']}_{intento}"
            carpeta.mkdir(exist_ok=True)
            bruto = carpeta / "bruto.wav"
            grabar(lote, bruto)
            buenas, notas = cortar_y_comprobar(lote, bruto, carpeta)
            print(f"{lote['id']} intento {intento + 1}: {buenas}/{len(lote['lineas'])} bien · {duracion(bruto):.0f} s",
                  flush=True)
            if buenas > mejor[0]:
                mejor = (buenas, carpeta, notas)
            if buenas == len(lote["lineas"]):
                break
            time.sleep(15)
        buenas, carpeta, notas = mejor
        for x in lote["lineas"]:
            f = carpeta / f"{x['id']}.wav"
            if f.exists():
                f.replace(SALIDA / f"{x['id']}.wav")
        (SALIDA / f"bruto_{lote['id']}.wav").write_bytes((carpeta / "bruto.wav").read_bytes())
        informe += [f"== {lote['id']}: {buenas}/{len(lote['lineas'])}"] + notas
        time.sleep(15)
    (SALIDA / "informe.txt").write_text("\n".join(informe), encoding="utf-8")
    print("\n".join(informe))


if __name__ == "__main__":
    main()
