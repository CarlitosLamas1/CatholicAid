#!/usr/bin/env python3
"""CatholicAid · Visitas por vídeo y hora de publicación (solo lectura, no guarda nada).

Escribe en el registro del run una tabla por idioma: fecha del Evangelio, hora de publicación (Madrid), horas desde
entonces, visitas, «me gusta» y comentarios. Sirve para comparar las horas de publicación probadas. Uso:
  python3 proceso/visitas_videos.py
"""
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
MADRID = ZoneInfo("Europe/Madrid")
SUF = {"es": "", "en": "-en", "pt": "-pt"}


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import evangelio as ev
    ahora = dt.datetime.now(dt.timezone.utc)
    for idioma in ("es", "en", "pt"):
        try:
            ev.aplicar_idioma(idioma)
            tok = ev.token_youtube(idioma)
        except Exception as ex:
            print(f"[{idioma}] sin acceso ({ex})")
            continue
        filas = []
        for f in sorted((RAIZ / "episodios").glob(f"2026-*{SUF[idioma]}.json")):
            if idioma == "es" and f.stem.endswith(("-en", "-pt")):
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            y = d.get("youtube") or {}
            if y.get("id") and d.get("modo") == "diario":
                filas.append((d["fecha"], y["id"], y.get("publishAt"), d.get("duracion_s")))
        if not filas:
            continue
        datos = {}
        for i in range(0, len(filas), 40):
            r = ev.http(ev.YT + "videos?part=statistics,status&id=" + ",".join(x[1] for x in filas[i:i + 40]),
                        headers={"Authorization": f"Bearer {tok}"})
            for it in r.get("items", []):
                datos[it["id"]] = it
        print(f"== {idioma}: fecha | publicado (Madrid) | horas | visitas | gustas | coment. | duración s")
        for fecha, vid, pub, dur in filas:
            it = datos.get(vid, {})
            s = it.get("statistics", {})
            ini = pub or (it.get("status") or {}).get("publishAt")
            if ini:
                t = dt.datetime.fromisoformat(ini.replace("Z", "+00:00"))
                horas = round((ahora - t).total_seconds() / 3600)
                local = t.astimezone(MADRID).strftime("%d/%m %H:%M")
            else:
                horas, local = "?", "?"
            print(f"{fecha} | {local} | {horas} | {s.get('viewCount', '?')} | {s.get('likeCount', '?')} | "
                  f"{s.get('commentCount', '?')} | {dur}")


if __name__ == "__main__":
    main()
