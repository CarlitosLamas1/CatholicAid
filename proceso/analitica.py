#!/usr/bin/env python3
"""CatholicAid · Qué hace funcionar un vídeo (YouTube Analytics, permiso yt-analytics.readonly desde el 17/11/2026).

Para los vídeos diarios de los últimos N días (por defecto 28) de un canal: visitas, cuánto se ve de media (segundos
y %), suscriptores ganados, y lo que tenía cada vídeo (frase clave y sus palabras, duración, gancho, estilo de
imágenes, día de la semana). Además: de dónde llegan las visitas (Shorts, búsqueda, sugeridos…), países y edades.
Solo lee: no cambia nada. Resultado en estado/analitica-<idioma>.json y un resumen legible en el registro del run.
Uso: python3 proceso/analitica.py [es|en|pt] [días]"""
import datetime as dt
import json
import re
import statistics
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

RAIZ = ev.RAIZ
API = "https://youtubeanalytics.googleapis.com/v2/reports?"
SUF = {"es": "", "en": "-en", "pt": "-pt"}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def informe(tok, desde, hasta, metricas, dimensiones="", filtros="", orden="", maximo=None):
    q = {"ids": "channel==MINE", "startDate": str(desde), "endDate": str(hasta), "metrics": metricas}
    for k, v in (("dimensions", dimensiones), ("filters", filtros), ("sort", orden), ("maxResults", maximo)):
        if v:
            q[k] = v
    d = ev.http(API + urllib.parse.urlencode(q), headers={"Authorization": f"Bearer {tok}"})
    nombres = [c["name"] for c in d.get("columnHeaders", [])]
    return [dict(zip(nombres, fila)) for fila in d.get("rows") or []]


def registros(idioma, desde, hasta):
    """{id de YouTube: lo que tenía el vídeo} de los registros diarios publicados entre dos fechas."""
    out, dia = {}, desde
    while dia <= hasta:
        ruta = RAIZ / "episodios" / f"{dia}{SUF[idioma]}.json"
        reg = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
        vid = (reg.get("youtube") or {}).get("id")
        if vid and reg.get("modo") == "diario":
            frase = reg.get("frase_clave", "")
            out[vid] = {"fecha": str(dia), "dia": DIAS[dia.weekday()], "cita": reg.get("cita"), "frase": frase,
                        "palabras_frase": len(re.findall(r"\w+", frase)), "duracion_s": reg.get("duracion_s"),
                        "gancho_s": reg.get("gancho_segundos"), "estilo": reg.get("estilo_imagenes"),
                        "imagenes_dia": sum(1 for i in reg.get("imagenes", []) if str(i).startswith("dias/"))}
        dia += dt.timedelta(days=1)
    return out


def main():
    idioma = sys.argv[1] if len(sys.argv) > 1 else "es"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 28
    hasta = dt.datetime.now(ev.MADRID).date() - dt.timedelta(days=1)  # Analytics va con 1–2 días de retraso
    desde = hasta - dt.timedelta(days=n)
    tok = ev.token_youtube(idioma)
    regs = registros(idioma, desde, hasta)
    filas = informe(tok, desde, hasta, "views,averageViewDuration,averageViewPercentage,subscribersGained,likes",
                    "video", "video==" + ",".join(regs), "-views") if regs else []
    videos = [{**regs.get(f["video"], {}), "id": f["video"], "visitas": f["views"],
               "segundos_vistos": f["averageViewDuration"], "porcentaje_visto": round(f["averageViewPercentage"], 1),
               "suscriptores": f["subscribersGained"], "gustas": f["likes"]} for f in filas]
    fuentes = informe(tok, desde, hasta, "views", "insightTrafficSourceType", orden="-views")
    paises = informe(tok, desde, hasta, "views", "country", orden="-views", maximo=10)
    edades = informe(tok, desde, hasta, "viewerPercentage", "ageGroup")
    resultado = {"idioma": idioma, "desde": str(desde), "hasta": str(hasta), "videos": videos, "fuentes": fuentes,
                 "paises": paises, "edades": edades,
                 "generado": dt.datetime.now(ev.MADRID).isoformat(timespec="seconds")}
    (RAIZ / "estado" / f"analitica-{idioma}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2),
                                                              encoding="utf-8")
    print(f"Canal {idioma} · {desde} a {hasta} · {len(videos)} vídeos")
    for v in sorted(videos, key=lambda x: -x["visitas"]):
        print(f"{v.get('fecha')} {v.get('dia', ''):>9} · {v['visitas']:>6} visitas · {v['porcentaje_visto']:>5} % visto "
              f"({v['segundos_vistos']} de {v.get('duracion_s')} s) · +{v['suscriptores']} subs · "
              f"frase {v.get('palabras_frase')} pal. · gancho {v.get('gancho_s')} s · «{v.get('frase', '')[:50]}»")
    if len(videos) >= 6:
        print(f"Mediana de % visto: {statistics.median(v['porcentaje_visto'] for v in videos)}")
    print("Fuentes:", ", ".join(f"{x['insightTrafficSourceType']} {x['views']}" for x in fuentes))
    print("Países:", ", ".join(f"{x['country']} {x['views']}" for x in paises))
    print("Edades:", ", ".join(f"{x['ageGroup']} {x['viewerPercentage']:.0f} %" for x in edades))


if __name__ == "__main__":
    main()
