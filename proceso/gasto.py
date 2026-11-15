#!/usr/bin/env python3
"""CatholicAid · Gasto estimado de la clave de pago de Gemini (imágenes, voces de pago y reserva de pago).

Google no da el saldo de prepago por API, así que es una ESTIMACIÓN a partir de los registros de los vídeos
(episodios/*.json) y de los precios aproximados de config «gasto.precios»:
- imágenes: las pintadas ese día (solo el español pinta) más las repintadas;
- voz: los segundos de vídeo grabados con la clave de pago (portugués siempre; español e inglés solo con la reserva);
- texto: un fijo pequeño si el reparto o la reflexión tiraron de la reserva de pago.
Si Carlos apunta un saldo conocido (config «gasto.saldo»: euros y fecha), también se estima lo que queda.
"""
import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
MADRID = ZoneInfo("Europe/Madrid")
PRECIOS = {"imagen": 0.04, "voz_segundo": 0.0003, "texto": 0.01}


def config():
    try:
        return json.loads((RAIZ / "config" / "personajes.json").read_text(encoding="utf-8")).get("gasto", {})
    except Exception:
        return {}


def gasto_registro(reg, precios=None):
    """Euros estimados que costó hacer el vídeo de este registro."""
    p = {**PRECIOS, **(precios or {})}
    total = 0.0
    if not reg.get("idioma"):  # español: es el único que pinta
        del_dia = {x for x in reg.get("imagenes") or [] if re.match(rf"dias/{reg.get('fecha', '')}_e\d+", str(x))}
        total += (len(del_dia) + int(reg.get("repintados") or 0)) * p["imagen"]
    reserva = [str(m) for m in reg.get("reserva_pago") or []]
    voz_pago = any("(pago)" in str(m) for m in reg.get("modelos_voz") or []) or any("tts" in m for m in reserva)
    if voz_pago:
        total += float(reg.get("duracion_s") or 0) * p["voz_segundo"]
    if any("tts" not in m for m in reserva):
        total += p["texto"]
    return round(total, 4)


def _momento(texto):
    """Fecha («2026-11-15») o fecha y hora ISO -> datetime con zona (Madrid si no la trae); None si no vale."""
    try:
        t = dt.datetime.fromisoformat(texto)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=MADRID)


def resumen(hoy, registros=None, cfg=None):
    """{"hoy": €, "mes": €, "queda": € o None}. registros: lista de registros (por defecto, todos los episodios)."""
    cfg = config() if cfg is None else cfg
    if registros is None:
        registros = []
        for ruta in (RAIZ / "episodios").glob("*.json"):
            try:
                registros.append(json.loads(ruta.read_text(encoding="utf-8")))
            except ValueError:
                pass
    precios = cfg.get("precios")
    de_hoy = de_mes = desde_saldo = 0.0
    saldo = cfg.get("saldo") or {}
    fecha_saldo = _momento(saldo.get("fecha"))  # solo cuenta lo grabado DESPUÉS de mirar el saldo
    for reg in registros:
        hecho = _momento(reg.get("generado"))
        if not hecho:
            continue
        dia = hecho.astimezone(MADRID).date()
        coste = gasto_registro(reg, precios)
        de_hoy += coste if dia == hoy else 0
        de_mes += coste if (dia.year, dia.month) == (hoy.year, hoy.month) else 0
        desde_saldo += coste if fecha_saldo and hecho > fecha_saldo else 0
    queda = round(float(saldo["euros"]) - desde_saldo, 2) if fecha_saldo and "euros" in saldo else None
    return {"hoy": round(de_hoy, 2), "mes": round(de_mes, 2), "queda": queda}


if __name__ == "__main__":
    print(resumen(dt.date.today()))
