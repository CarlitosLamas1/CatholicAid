#!/usr/bin/env python3
"""Casting de voces: la misma frase con varias voces candidatas, en un solo MP3 por papel.
Salida: casting/<papel>.mp3 y casting/orden.txt (qué voz suena en cada posición)."""
import base64
import json
import os
import subprocess
import time
import urllib.request
import wave
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
CLAVE = (os.environ.get("GEMINI_API_KEY_IMAGENES") or os.environ["GEMINI_API_KEY"]).strip()
VELOCIDAD = float(os.environ.get("VELOCIDAD", "1.08"))
HOMBRES = ["Alnilam", "Charon", "Iapetus", "Achird", "Sadaltager", "Schedar", "Orus", "Algieba", "Umbriel",
           "Rasalgethi", "Enceladus", "Algenib"]
MUJERES = ["Sulafat", "Achernar", "Vindemiatrix", "Despina", "Aoede", "Kore", "Gacrux", "Leda"]
PAPELES = {
    "jesus": (HOMBRES, "voz de hombre adulto, cálida, armoniosa y tierna, llena de amor y de autoridad serena, "
                       "ritmo natural, acento de España",
              "Venid a mí todos los que estáis cansados y agobiados, y yo os aliviaré. "
              "Os doy un mandamiento nuevo: que os améis unos a otros como yo os he amado."),
    "narrador": (HOMBRES, "voz de narrador mayor, cálida y clara, que cuenta con cariño, ritmo natural y ágil, "
                          "acento de España",
                 "En aquel tiempo, se acercaban a Jesús los publicanos y los pecadores para escucharle, "
                 "y los fariseos murmuraban entre sí."),
    "maria": (MUJERES, "voz de mujer joven, dulce, humilde y luminosa, llena de paz, ritmo natural, acento de España",
              "He aquí la esclava del Señor; hágase en mí según tu palabra. "
              "Proclama mi alma la grandeza del Señor."),
}

salida = Path("casting")
salida.mkdir(exist_ok=True)
orden = []
for papel, (voces, estilo, frase) in PAPELES.items():
    trozos = []
    for n, voz in enumerate(voces, 1):
        cuerpo = {"contents": [{"parts": [{"text": f"Lee en voz alta, con {estilo}, este texto:\n\n{frase}"}]}],
                  "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                      "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
        req = urllib.request.Request(API, data=json.dumps(cuerpo).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": CLAVE})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                dato = json.loads(r.read())["candidates"][0]["content"]["parts"][0]["inlineData"]
        except Exception as e:
            print(f"{papel} {n} {voz}: falló ({e})")
            continue
        wav = salida / f"{papel}_{n:02d}_{voz}.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(base64.b64decode(dato["data"]))
        trozos.append(wav)
        orden.append(f"{papel} {n}: {voz}")
        print(orden[-1], flush=True)
        time.sleep(4)
    lista = salida / f"{papel}.txt"
    silencio = salida / "silencio.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", "1.5", str(silencio)], check=True)
    lista.write_text("".join(f"file '{p.name}'\nfile 'silencio.wav'\n" for p in trozos))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lista.name,
                    "-filter:a", f"atempo={VELOCIDAD}", "-b:a", "128k", f"{papel}.mp3"], check=True, cwd=salida)
(salida / "orden.txt").write_text("\n".join(orden) + "\n")
