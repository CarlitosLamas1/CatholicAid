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
_LISTA = [json.loads((RAIZ / x.strip()).read_text(encoding="utf-8"))
          for x in os.environ.get("LOTES", "rosario/v2/lotes.json").split(",") if x.strip()]
LOTES = dict(_LISTA[0], lotes=[l for d in _LISTA for l in d["lotes"]])  # varias tandas en una tirada (mismo modelo)
IDIOMA = LOTES.get("idioma", "es")
PROMPT = {
    "es": ("Lee en voz alta, con {}, los siguientes párrafos, en este orden. Entre un párrafo y el siguiente haz siempre "
           "una pausa clara de dos segundos. Lee solo el texto de los párrafos, todos y cada uno, sin saltarte ninguno:"),
    "en": ("Read aloud, with {}, the following paragraphs, in this order. Between one paragraph and the next always make "
           "a clear two-second pause. Read only the text of the paragraphs, every single one, without skipping any:"),
    "pt": ("Leia em voz alta, com {}, os parágrafos seguintes, nesta ordem. Entre um parágrafo e o seguinte faça sempre "
           "uma pausa clara de dois segundos. Leia só o texto dos parágrafos, todos e cada um, sem pular nenhum:")}[IDIOMA]
REFS = RAIZ / "rosario" / "referencias"  # tiradas aprobadas (para parecerse a ellas)
SALIDA = RAIZ / "rosario" / "salida"
FF = imageio_ffmpeg.get_ffmpeg_exe()
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
CLAVE = os.environ["GEMINI_API_KEY_IMAGENES"].strip()
OIDO = WhisperModel("small", device="cpu", compute_type="int8")
norm = lambda t: re.sub(r"[^a-záéíóúüñàâãêôõç' ]", " ", t.lower().replace("’", "'")).split()  # noqa: E731


def grabar(lote, destino):
    prompt = PROMPT.format(lote["estilo"]) + "\n\n" + "\n\n".join(x["texto"] for x in lote["lineas"])
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
    bruto = base64.b64decode(dato["data"])
    if len(bruto) < 48000:
        raise ValueError("audio vacío")
    if bruto[:4] == b"RIFF":
        destino.write_bytes(bruto)
        return
    m = re.search(r"rate=(\d+)", dato.get("mimeType", ""))
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(m.group(1)) if m else 24000)
        w.writeframes(bruto)


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
    return " ".join(s.text for s in OIDO.transcribe(x, language=IDIOMA)[0]).strip()


def palabras(ruta):
    with wave.open(str(ruta)) as w:
        hz = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    x = np.interp(np.arange(0, len(x), hz / 16000), np.arange(len(x)), x).astype(np.float32)
    segs, _ = OIDO.transcribe(x, language=IDIOMA, word_timestamps=True)
    salida = []
    for sg in segs:
        for w in sg.words or []:
            for t in norm(w.word):
                salida.append((t, w.start, w.end))
    return salida


def cortar_y_comprobar(lote, bruto, carpeta):
    """Empareja lo que se oye con el texto: cada línea va desde su primera palabra oída hasta la última, y el corte cae
    en el silencio que hay entre dos líneas. Una línea vale si se oye al menos el 75 % de sus palabras (40 % si es
    muy corta)."""
    lineas = lote["lineas"]
    d = duracion(bruto)
    oidas = palabras(bruto)
    objetivo, duena = [], []
    for i, x in enumerate(lineas):
        for t in norm(x["texto"]):
            objetivo.append(t)
            duena.append(i)
    sm = difflib.SequenceMatcher(None, objetivo, [o[0] for o in oidas], autojunk=False)
    por_linea = {i: [] for i in range(len(lineas))}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            por_linea[duena[a + k]].append(b + k)
    sil = silencios(bruto)
    notas, buenas, tramos = [], 0, []
    for i, x in enumerate(lineas):
        idx = por_linea[i]
        total = len(norm(x["texto"]))
        cubierto = len(idx) / max(total, 1)
        if not idx:
            tramos.append(None)
            notas.append(f"MAL 0.00 {x['id']}: no se oye")
            continue
        tramos.append([oidas[min(idx)][1], oidas[max(idx)][2]])
        minimo = 0.75 if total > 4 else 0.4
        ok = cubierto >= minimo
        buenas += ok
        notas.append(f"{'OK ' if ok else 'MAL'} {cubierto:.2f} {x['id']}")
    # cortes en el silencio entre una línea y la siguiente (o en el punto medio si no hay)
    for i in range(len(tramos) - 1):
        a, b = tramos[i], tramos[i + 1]
        if not a or not b:
            continue
        hueco = [(s0, s1) for s0, s1 in sil if s1 > a[1] - 0.15 and s0 < b[0] + 0.15]
        if hueco:
            s0, s1 = max(hueco, key=lambda h: h[1] - h[0])
            a[1], b[0] = max(a[1], s0 + 0.05), min(b[0], s1 - 0.05)
        else:
            m = (a[1] + b[0]) / 2
            a[1], b[0] = m, m
    for x, t in zip(lineas, tramos):
        if not t:
            continue
        ini, fin = max(0.0, t[0] - 0.12), min(d, t[1] + 0.25)
        subprocess.run([FF, "-y", "-loglevel", "error", "-ss", f"{ini:.3f}", "-to", f"{fin:.3f}", "-i", str(bruto),
                        "-ar", "48000", "-ac", "1", "-sample_fmt", "s16", str(carpeta / f"{x['id']}.wav")], check=True)
    return buenas, notas


def huella(ruta, letras=None):
    """(tono, brillo, sequedad, letras por segundo) de una grabación, para elegir la tirada más parecida a la aprobada.
    sequedad: parte del tiempo en silencio limpio (< -50 dB). Las tiradas con eco de iglesia casi no tienen
    silencios limpios (26/11/2026: Carlos oyó reverberación en las tiradas largas)."""
    import librosa
    y, hz = librosa.load(str(ruta), sr=16000)
    f0, sonoro, _ = librosa.pyin(y, fmin=60, fmax=400, sr=hz)
    tono = float(np.nanmedian(f0[sonoro])) if np.any(sonoro) else 0.0
    brillo = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=hz)))
    rms = librosa.feature.rms(y=y, frame_length=800, hop_length=400)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-9))
    sequedad = float(np.mean(db < -50))
    voz = float(np.mean(db > -35)) * len(y) / hz
    ritmo = (letras / voz) if letras and voz else 0.0
    return tono, brillo, sequedad, ritmo


def distancia(a, b):
    d = abs(a[0] - b[0]) / max(b[0], 1) + abs(a[1] - b[1]) / max(b[1], 1) + 2 * abs(a[2] - b[2])
    if a[3] and b[3]:
        d += abs(a[3] - b[3]) / max(b[3], 1)
    return d


def main():
    SALIDA.mkdir(exist_ok=True)
    informe = []
    for lote in LOTES["lotes"]:
        mejor = (-1, None, None)
        ref = REFS / lote["referencia"] if lote.get("referencia") else None
        huella_ref = huella(ref, lote.get("letras_referencia")) if ref and ref.exists() else None
        if huella_ref:
            print(f"{lote['id']}: referencia tono {huella_ref[0]:.0f} Hz · brillo {huella_ref[1]:.0f} Hz · "
                  f"silencio limpio {huella_ref[2]:.0%} · {huella_ref[3]:.1f} letras/s", flush=True)
        candidatas = []
        for intento in range(LOTES.get("intentos", 3)):
            carpeta = SALIDA / f"_{lote['id']}_{intento}"
            carpeta.mkdir(exist_ok=True)
            bruto = carpeta / "bruto.wav"
            try:
                grabar(lote, bruto)
                buenas, notas = cortar_y_comprobar(lote, bruto, carpeta)
            except Exception as e:
                print(f"{lote['id']} intento {intento + 1}: falló ({e})", flush=True)
                time.sleep(20)
                continue
            print(f"{lote['id']} intento {intento + 1}: {buenas}/{len(lote['lineas'])} bien · {duracion(bruto):.0f} s",
                  flush=True)
            if huella_ref:
                h = huella(bruto, sum(len(x["texto"]) for x in lote["lineas"]))
                dist = distancia(h, huella_ref)
                print(f"   tono {h[0]:.0f} Hz · brillo {h[1]:.0f} Hz · silencio limpio {h[2]:.0%} · {h[3]:.1f} letras/s · "
                      f"diferencia con la aprobada {dist:.3f}", flush=True)
                candidatas.append((buenas, -dist, carpeta, notas))
            elif buenas > mejor[0]:
                mejor = (buenas, carpeta, notas)
            if not huella_ref and buenas == len(lote["lineas"]):
                break
            time.sleep(15)
        if candidatas:  # entre las que se oyen enteras (o las mejores), la que más se parece a la aprobada
            tope = max(c[0] for c in candidatas)
            b, d, c, n = max((c for c in candidatas if c[0] >= tope - 1), key=lambda c: (c[1], c[0]))
            mejor = (b, c, n)
            print(f"{lote['id']}: elegida {c.name} ({b}/{len(lote['lineas'])}, diferencia {-d:.3f})", flush=True)
        buenas, carpeta, notas = mejor
        if carpeta is None:
            informe.append(f"== {lote['id']}: SIN GRABAR")
            continue
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
