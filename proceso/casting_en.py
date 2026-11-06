#!/usr/bin/env python3
"""Casting de voces en INGLÉS (canal CatolicAid English). Separado del casting en español (proceso/casting.py).

Para cada papel, la misma frase de la World English Bible con la voz que ya tiene en español (posición 1) y unas
pocas alternativas. Estilos de config («en»), con el acento de config (en.acento; por defecto americano neutro).

Solo la clave GRATUITA (GEMINI_API_KEY), salvo PAGO=si. El cupo gratuito de voces es de 10 peticiones al día: si se
agota, se para sin error y lo ya grabado se guarda en casting_en/ (el workflow lo conserva en la caché de GitHub),
así una nueva tirada solo graba lo que falta.
Salida: casting_en/<papel>.mp3 y casting_en/orden.txt (qué voz suena en cada posición).
"""
import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CFG = json.loads((RAIZ / "config" / "personajes.json").read_text(encoding="utf-8"))
EN = CFG["en"]
ACENTO = os.environ.get("ACENTO", "").strip() or EN.get("acento", "clear neutral American accent")
MODELO = CFG["modelo_voz"]
API = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent"
VELOCIDAD = float(os.environ.get("VELOCIDAD", "") or CFG.get("velocidad_voz", 1.15))
PAUSA = int(CFG.get("pausa_tts_segundos", 21))


def estilo(e):
    return e.replace("{acento}", ACENTO)


# Frases literales de la World English Bible (Catholic), sin comillas.
JESUS = ("Come to me, all you who labor and are heavily burdened, and I will give you rest. "
         "Peace I leave with you. My peace I give to you; not as the world gives, I give to you.")
MARIA = ("Behold, the servant of the Lord; let it be done to me according to your word. "
         "My soul magnifies the Lord. My spirit has rejoiced in God my Savior.")
NARRA = ("Now all the tax collectors and sinners were coming close to him to hear him. "
         "The Pharisees and the scribes murmured, saying, This man welcomes sinners, and eats with them.")

PJ, NAR = CFG["personajes"], CFG["narradores"]
PAPELES = {  # papel: [(voz, estilo)], frase. La primera voz es la que ya tiene en español.
    "jesus": ([(v, EN["personajes"]["jesus"]["estilo"]) for v in [PJ["jesus"]["voz_gemini"], "Sadaltager", "Rasalgethi"]],
              JESUS),
    "maria": ([(v, EN["personajes"]["maria"]["estilo"]) for v in [PJ["maria"]["voz_gemini"], "Sulafat", "Vindemiatrix"]],
              MARIA),
    "narradores": ([(NAR[k]["voz_gemini"], EN["narradores"][k]["estilo"]) for k in ("Mateo", "Marcos", "Lucas", "Juan")]
                   + [(v, EN["narradores"]["Lucas"]["estilo"]) for v in ("Rasalgethi", "Sadaltager")], NARRA),
}
NOMBRES = {"narradores": ["Mateo", "Marcos", "Lucas", "Juan", "alternativa", "alternativa"]}


def clave():
    gratis = os.environ.get("GEMINI_API_KEY", "").strip()
    pago = os.environ.get("GEMINI_API_KEY_IMAGENES", "").strip()
    return gratis, (pago if os.environ.get("PAGO", "").strip().lower() in ("si", "sí", "true", "1") else "")


def grabar(voz, est, frase, destino):
    cuerpo = {"contents": [{"parts": [{"text": f"Read aloud, with {estilo(est)}, the following text:\n\n{frase}"}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                  "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
    gratis, pago = clave()
    for k in [gratis] + ([pago] if pago else []):
        req = urllib.request.Request(API, data=json.dumps(cuerpo).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": k})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                dato = json.loads(r.read())["candidates"][0]["content"]["parts"][0]["inlineData"]
            break
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            print(f"   429: cupo {'gratuito' if k == gratis else 'de pago'} agotado", flush=True)
    else:
        raise RuntimeError("cupo")
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(base64.b64decode(dato["data"]))


def main():
    salida = RAIZ / "casting_en"
    salida.mkdir(exist_ok=True)
    print(f"Acento: {ACENTO} · velocidad {VELOCIDAD} · modelo {MODELO}", flush=True)
    orden, sin_cupo, peticiones = [], False, 0
    silencio = salida / "silencio.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", "1.5", str(silencio)], check=True)
    for papel, (voces, frase) in PAPELES.items():
        trozos = []
        for n, (voz, est) in enumerate(voces, 1):
            quien = NOMBRES.get(papel, [""] * 9)[n - 1]
            wav = salida / f"{papel}_{n:02d}_{voz}_{hashlib.sha1((ACENTO + est + frase).encode()).hexdigest()[:6]}.wav"
            etiqueta = f"{papel} {n}: {voz}" + (f" ({quien})" if quien else "") + (" · la de español" if n == 1 or (
                papel == "narradores" and n <= 4) else " · alternativa")
            if not wav.exists() and not sin_cupo:
                try:
                    if peticiones:
                        time.sleep(PAUSA)
                    peticiones += 1
                    grabar(voz, est, frase, wav)
                except Exception as e:
                    print(f"{etiqueta}: no grabada ({e})", flush=True)
                    sin_cupo = sin_cupo or "cupo" in str(e)
                    continue
            if wav.exists():
                trozos.append(wav)
                orden.append(etiqueta)
                print(etiqueta, flush=True)
        if trozos:
            lista = salida / f"{papel}.txt"
            lista.write_text("".join(f"file '{p.name}'\nfile 'silencio.wav'\n" for p in trozos))
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lista.name,
                            "-filter:a", f"atempo={VELOCIDAD}", "-b:a", "128k", f"{papel}.mp3"], check=True, cwd=salida)
    total = sum(len(v) for v, _ in PAPELES.values())
    nota = (f"\nFaltan {total - len(orden)} de {total} muestras: se acabó el cupo gratuito de voces (10 al día). "
            "Vuelve a lanzar el casting mañana y grabará solo las que faltan.\n" if len(orden) < total else "")
    (salida / "orden.txt").write_text(f"Acento: {ACENTO}\n" + "\n".join(orden) + "\n" + nota)
    print(nota or "Casting completo.", flush=True)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Casting en inglés\n\n" + "\n".join(f"- {x}" for x in orden) + "\n" + nota)


if __name__ == "__main__":
    main()
