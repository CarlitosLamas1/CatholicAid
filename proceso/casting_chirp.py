#!/usr/bin/env python3
"""Casting de respaldo: cada personaje lee la misma frase con su voz de hoy (Gemini TTS) y, justo después,
con la voz del mismo nombre de Google Cloud «Chirp 3 HD» (servicio estable, no «preview").
Solo prueba: no toca la producción. ~2.000 letras en total (Chirp: ~30 $ por millón de letras).
Salida: casting_chirp/comparacion.mp3 (por personaje: Gemini, pausa, Chirp) y casting_chirp/orden.txt."""
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

CFG = json.loads(Path("config/personajes.json").read_text())
MODELO = CFG.get("modelo_voz", "gemini-2.5-flash-preview-tts")
GEMINI = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent"
CHIRP = "https://texttospeech.googleapis.com/v1/text:synthesize"
CLAVES = [c.strip() for c in (os.environ.get("GEMINI_API_KEY_IMAGENES"), os.environ.get("GEMINI_API_KEY")) if c]
IDIOMA = os.environ.get("IDIOMA_CHIRP", "es-ES")

N = CFG["narradores"]
PAPELES = [
    ("Jesús", "Enceladus", "voz de hombre adulto, cálida, armoniosa y tierna, llena de amor y de autoridad serena, "
                           "ritmo natural, acento de España",
     "Venid a mí todos los que estáis cansados y agobiados, y yo os aliviaré."),
    ("María", "Gacrux", "voz de mujer joven, dulce, humilde y luminosa, llena de paz, ritmo natural, acento de España",
     "He aquí la esclava del Señor; hágase en mí según tu palabra."),
] + [(f"Narrador {e}", N[e]["voz_gemini"], N[e]["estilo"],
      "En aquel tiempo, se acercaban a Jesús los publicanos y los pecadores para escucharle.")
     for e in ("Mateo", "Marcos", "Lucas", "Juan")]


def pedir(url, cuerpo, clave):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": clave})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def con_claves(url, cuerpo):
    ultimo = None
    for n, clave in enumerate(CLAVES):
        try:
            return pedir(url, cuerpo, clave)
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code} con la clave {'de pago' if n == 0 and len(CLAVES) > 1 else 'gratis'}: " \
                     f"{e.read().decode(errors='replace')[:600]}"
            print(ultimo, flush=True)
    raise RuntimeError(ultimo)


def guardar_pcm(pcm, ruta, hz=24000):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(pcm)


salida = Path("casting_chirp")
salida.mkdir(exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                "-t", "1.2", str(salida / "pausa.wav")], check=True)
trozos, orden, fallos = [], [], []
for n, (papel, voz, estilo, frase) in enumerate(PAPELES, 1):
    # 1) Gemini (lo de hoy)
    try:
        d = con_claves(GEMINI, {"contents": [{"parts": [{"text": f"Lee en voz alta, con {estilo}, este texto:\n\n{frase}"}]}],
                                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}})
        g = salida / f"{n}_{voz}_gemini.wav"
        guardar_pcm(base64.b64decode(d["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]), g)
    except Exception as e:
        fallos.append(f"{papel} Gemini: {e}")
        g = None
    # 2) Chirp 3 HD, misma voz por nombre
    nombre = f"{IDIOMA}-Chirp3-HD-{voz}"
    try:
        d = con_claves(CHIRP, {"input": {"text": frase}, "voice": {"languageCode": IDIOMA, "name": nombre},
                               "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000}})
        c = salida / f"{n}_{voz}_chirp.wav"
        c.write_bytes(base64.b64decode(d["audioContent"]))   # LINEAR16 ya viene con cabecera WAV
    except Exception as e:
        fallos.append(f"{papel} Chirp ({nombre}): {e}")
        c = None
    for etiqueta, ruta in (("1.º Gemini (hoy)", g), ("2.º Chirp 3 HD", c)):
        if ruta:
            trozos += [ruta.name, "pausa.wav"]
            orden.append(f"{papel} · {voz} · {etiqueta}")
    trozos.append("pausa.wav")
    print(papel, "hecho", flush=True)
    time.sleep(3)

(salida / "orden.txt").write_text("\n".join(orden) + ("\n\nFALLOS:\n" + "\n".join(fallos) if fallos else "") + "\n")
print((salida / "orden.txt").read_text())
if trozos:
    (salida / "lista.txt").write_text("".join(f"file '{t}'\n" for t in trozos))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "lista.txt",
                    "-ar", "24000", "-ac", "1", "-b:a", "128k", "comparacion.mp3"], check=True, cwd=salida)
if any("Chirp" in f for f in fallos):
    raise SystemExit(1)
