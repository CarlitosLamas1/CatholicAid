#!/usr/bin/env python3
"""CatholicAid · Escuchar un vídeo ya hecho (solo lectura): transcribe el audio del vídeo final con whisper y lo
compara con lo que debía decir (gancho, texto del Evangelio, «Palabra del Señor» y reflexión del registro).

Señala palabras que faltan o sobran, silencios largos dentro de la voz y tramos donde el habla va anormalmente rápida
o lenta. Lo lanza el workflow «Escuchar vídeo» con los runs de los vídeos (copia de 30 días).
Uso: python3 proceso/escuchar.py <carpeta_con_copias> <registro.json> [...]
"""
import difflib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

IDIOMA_WHISPER = {"es": "es", "en": "en", "pt": "pt"}


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9']+", t.replace("’", "'"))


def silencios(video):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "silencedetect=n=-38dB:d=0.9", "-f", "null",
                        "-"], capture_output=True, text=True)
    ini, sal = None, []
    for linea in r.stderr.splitlines():
        if "silence_start" in linea:
            ini = float(linea.split("silence_start:")[1])
        elif "silence_end" in linea and ini is not None:
            fin = float(linea.split("silence_end:")[1].split("|")[0])
            sal.append((ini, fin))
    return sal


def escuchar(video, reg, modelo):
    idioma = reg.get("idioma", "es")
    print(f"\n══════ {reg['fecha']} {idioma} · {reg.get('cita')} · {video.name}", flush=True)
    segs, _ = modelo.transcribe(str(video), language=IDIOMA_WHISPER[idioma], word_timestamps=True, beam_size=5,
                                vad_filter=False, condition_on_previous_text=False)
    palabras = [w for s in segs for w in (s.words or [])]
    print("TRANSCRIPCIÓN (segundo: texto):")
    linea, t0 = [], None
    for w in palabras:
        if t0 is None:
            t0 = w.start
        linea.append(w.word.strip())
        if w.word.strip()[-1:] in ".?!:;" or len(linea) > 14:
            print(f"  {t0:6.2f}: {' '.join(linea)}")
            linea, t0 = [], None
    if linea:
        print(f"  {t0:6.2f}: {' '.join(linea)}")
    # Huecos y prisas dentro de la voz
    print("HUECOS > 1,2 s entre palabras:")
    for a, b in zip(palabras, palabras[1:]):
        if b.start - a.end > 1.2:
            print(f"  {a.end:6.2f}–{b.start:6.2f} ({b.start - a.end:.1f} s) tras «{a.word.strip()}» antes de «{b.word.strip()}»")
    print("PALABRAS MUY LARGAS (> 1,3 s, posible sílaba arrastrada o ruido):")
    for w in palabras:
        if w.end - w.start > 1.3:
            print(f"  {w.start:6.2f} «{w.word.strip()}» {w.end - w.start:.1f} s")
    print("SILENCIOS (ffmpeg, < -38 dB, > 0,9 s):", ", ".join(f"{a:.1f}–{b:.1f}" for a, b in silencios(video)) or "ninguno")
    # Comparación con lo esperado
    esperado = " ".join(x for x in (reg.get("frase_clave", ""), reg.get("texto_evangelio", ""), reg.get("reflexion", ""))
                        if x)
    e, o = norm(esperado), norm(" ".join(w.word for w in palabras))
    print("DIFERENCIAS con el texto esperado (gancho + Evangelio + reflexión; fórmulas como «Palabra del Señor» aparte):")
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, e, o, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        print(f"  {op:8s} esperado «{' '.join(e[i1:i2])}» · oído «{' '.join(o[j1:j2])}»")


def main():
    from faster_whisper import WhisperModel
    carpeta = Path(sys.argv[1])
    modelo = WhisperModel("small", device="cpu", compute_type="int8")
    for ruta in sys.argv[2:]:
        reg = json.loads(Path(ruta).read_text(encoding="utf-8"))
        candidatos = [p for p in carpeta.rglob("*.mp4") if str(reg.get("run")) in str(p)]
        candidatos = [p for p in candidatos if "miniatura" not in p.name] or candidatos
        if not candidatos:
            print(f"\n{ruta}: no encuentro el vídeo del run {reg.get('run')}")
            continue
        video = max(candidatos, key=lambda p: p.stat().st_size)
        escuchar(video, reg, modelo)


if __name__ == "__main__":
    main()
