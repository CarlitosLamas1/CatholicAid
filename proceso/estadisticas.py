#!/usr/bin/env python3
"""CatholicAid · Números de la semana (lo lanza «Mantenimiento» los domingos; resultado en estado/estadisticas.json,
que el parte diario del domingo resume).

Con el permiso de YouTube que ya hay (visitas, «me gusta» y comentarios de cada vídeo; la retención exacta pediría
otro permiso) compara los vídeos de los últimos 14 días:
- por canal: cuántos vídeos, visitas totales y el más visto;
- prueba A/B del gancho (solo español, el canal con más visitas): mediana de visitas de los días de gancho corto y
  de gancho largo. Si el mismo gana con claridad (≥ 20 % y al menos 3 vídeos por lado) dos semanas seguidas, se fija
  en config (gancho_segundos) y se quita la prueba (gancho_ab).
"""
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
MADRID = ZoneInfo("Europe/Madrid")
SUF = {"es": "", "en": "-en", "pt": "-pt"}
VENTAJA, MINIMO = 1.2, 3


def log(*a):
    print(*a, flush=True)


def leer(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except Exception:
        return {}


def videos(idioma, desde, hasta):
    """Registros diarios publicados entre dos fechas: [{fecha, id, frase, gancho, duracion}]."""
    lista = []
    dia = desde
    while dia <= hasta:
        reg = leer(RAIZ / "episodios" / f"{dia}{SUF[idioma]}.json")
        vid = (reg.get("youtube") or {}).get("id")
        if vid and reg.get("modo") == "diario":
            lista.append({"fecha": str(dia), "id": vid, "frase": reg.get("frase_clave", ""),
                          "gancho": reg.get("gancho_segundos"), "duracion": reg.get("duracion_s")})
        dia += dt.timedelta(days=1)
    return lista


def con_visitas(lista, tok):
    import evangelio as ev
    if not lista:
        return lista
    d = ev.http(ev.YT + "videos?part=statistics&id=" + ",".join(v["id"] for v in lista),
                headers={"Authorization": f"Bearer {tok}"})
    datos = {i["id"]: i.get("statistics", {}) for i in d.get("items", [])}
    for v in lista:
        s = datos.get(v["id"], {})
        v.update({"visitas": int(s.get("viewCount", 0)), "gustas": int(s.get("likeCount", 0)),
                  "comentarios": int(s.get("commentCount", 0))})
    return lista


def comparar_gancho(lista):
    """{"lados": {"1.5": {"n", "mediana"}, …}, "ganador": "2.8" o None} con los vídeos dados."""
    lados = {}
    for v in lista:
        if v.get("gancho") is not None and "visitas" in v:
            lados.setdefault(str(v["gancho"]), []).append(v["visitas"])
    res = {k: {"n": len(x), "mediana": round(statistics.median(x))} for k, x in sorted(lados.items())}
    ganador = None
    if len(res) == 2 and all(r["n"] >= MINIMO for r in res.values()):
        (a, ra), (b, rb) = sorted(res.items(), key=lambda kv: kv[1]["mediana"])
        if rb["mediana"] >= VENTAJA * max(ra["mediana"], 1):
            ganador = b
    return {"lados": res, "ganador": ganador}


def decidir(historial, ganador, semana):
    """Apunta el ganador de esta semana ({"semana": "2026-W46", "ganador": "2.8"}; una sola entrada por semana,
    aunque el cálculo se repita) y dice si hay que fijarlo: el mismo ganador dos semanas DISTINTAS seguidas."""
    historial = [h for h in historial if isinstance(h, dict) and h.get("semana") != semana]
    historial = (historial + [{"semana": semana, "ganador": ganador}])[-6:]
    fijar = ganador if ganador and len(historial) >= 2 and historial[-2]["ganador"] == ganador else None
    return historial, fijar


def fijar_gancho(segundos):
    ruta = RAIZ / "config" / "personajes.json"
    cfg = json.loads(ruta.read_text(encoding="utf-8"))
    if "gancho_ab" not in cfg:
        return False
    cfg["gancho_segundos"] = float(segundos)
    cfg["_gancho_ab"] = (f"Prueba A/B terminada el {dt.datetime.now(MADRID).date()}: gana el gancho de {segundos} s "
                         "(más visitas dos semanas seguidas; proceso/estadisticas.py).")
    cfg["gancho_ab_anterior"] = cfg.pop("gancho_ab")
    ruta.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import evangelio as ev
    hoy = dt.datetime.now(MADRID).date()
    previo = leer(RAIZ / "estado" / "estadisticas.json")
    estado = {"fecha": str(hoy), "idiomas": {}}
    for idioma in ("es", "en", "pt"):
        try:
            ev.aplicar_idioma(idioma)
            lista = con_visitas(videos(idioma, hoy - dt.timedelta(days=14), hoy - dt.timedelta(days=1)),
                                ev.token_youtube(idioma))
        except Exception as ex:
            log(f"[{idioma}] sin números ({ex})")
            continue
        semana = [v for v in lista if v["fecha"] >= str(hoy - dt.timedelta(days=7))]
        mejor = max(semana, key=lambda v: v.get("visitas", 0), default=None)
        estado["idiomas"][idioma] = {
            "videos": len(semana), "visitas": sum(v.get("visitas", 0) for v in semana),
            "gustas": sum(v.get("gustas", 0) for v in semana),
            "comentarios": sum(v.get("comentarios", 0) for v in semana),
            "mejor": {k: mejor[k] for k in ("fecha", "frase", "visitas")} if mejor else None}
        if idioma == "es":
            estado["gancho"] = comparar_gancho(lista)
            semana = "{}-W{:02d}".format(*hoy.isocalendar()[:2])
            estado["gancho_historial"], fijar = decidir(previo.get("gancho_historial") or [],
                                                         estado["gancho"]["ganador"], semana)
            if fijar and fijar_gancho(fijar):
                estado["gancho_fijado"] = fijar
                log(f"Gancho fijado en {fijar} s")
        log(f"[{idioma}] {estado['idiomas'][idioma]}")
    (RAIZ / "estado" / "estadisticas.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2),
                                                        encoding="utf-8")


if __name__ == "__main__":
    main()
