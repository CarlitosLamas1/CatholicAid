#!/usr/bin/env python3
"""CatholicAid · Probar música nueva antes de usarla (workflow «Probar música»).

Por cada pieza de musica_candidatas (config) que aún no se ha probado: la descarga de Wikimedia Commons (solo con
licencia libre), monta un vídeo de 90 s con fondo negro y esa música (el principio, que es lo que suena en los
vídeos) y lo sube en PRIVADO al canal en español. Queda anotado en estado/musica.json («pruebas»).
Unas horas después, proceso/youtube_tareas.py mira si YouTube (Content ID) lo ha bloqueado: si no, la pieza pasa a
«aprobadas» y entra en la rotación; si sí, se veta. El vídeo de prueba se borra en los dos casos.
Uso: python3 proceso/probar_musica.py
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402


def log(*a):
    print(*a, flush=True)


def pendientes():
    est = ev.musica_estado()
    hechas = set(est.get("vetadas", {})) | set(est.get("aprobadas", {})) | set(est.get("pruebas", {}))
    return [x.replace(" ", "_") for x in ev.CFG.get("musica_candidatas", []) if x.replace(" ", "_") not in hechas]


def main():
    lista = pendientes()
    if not lista:
        log("No hay música nueva que probar.")
        return
    tok = ev.token_youtube("es")
    tmp = Path(tempfile.mkdtemp())
    est = ev.musica_estado()
    for nombre in lista:
        try:
            ruta = ev.descargar_musica(nombre)
            if not ruta:
                continue
            video = tmp / "prueba.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30",
                            "-i", str(ruta), "-t", "90", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                            "-b:a", "192k", "-shortest", str(video)], check=True)
            meta = {"snippet": {"title": f"Prueba de música (privado) · {nombre[:60]}", "categoryId": "22",
                                "description": "Prueba interna de derechos de la música. Se borra sola."},
                    "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}
            r, _ = ev.http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                           meta, {"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                                  "X-Upload-Content-Length": str(video.stat().st_size)}, method="POST", raw=True)
            req = urllib.request.Request(r.headers["Location"], data=video.read_bytes(), method="PUT",
                                         headers={"Content-Type": "video/mp4", "User-Agent": ev.UA})
            with urllib.request.urlopen(req, timeout=600) as r2:
                vid = json.loads(r2.read())["id"]
            est.setdefault("pruebas", {})[nombre] = {"video": vid,
                                                     "subido": dt.datetime.now(ev.MADRID).isoformat(timespec="seconds")}
            log(f"Prueba subida: {nombre} -> {vid}")
        except Exception as e:
            log(f"{nombre}: no se pudo probar ({type(e).__name__}: {e})")
    ev.MUSICA_VETADA.parent.mkdir(exist_ok=True)
    ev.MUSICA_VETADA.write_text(json.dumps(est, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
