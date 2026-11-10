#!/usr/bin/env python3
"""Espera hasta la hora de publicación (hora_publicacion de config, Madrid) del día dado, como mucho 3 h.
Lo usan «Publicar en TikTok» e «Publicar en Instagram» cuando el Reloj los lanza antes de hora (esperar=true):
así se publica puntual aunque los horarios de GitHub lleguen tarde.  Uso: python3 proceso/esperar.py AAAA-MM-DD"""
import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "personajes.json").read_text(encoding="utf-8"))
objetivo = dt.datetime.combine(dt.date.fromisoformat(sys.argv[1]), dt.time(int(cfg.get("hora_publicacion", 7))), MADRID)
falta = (objetivo - dt.datetime.now(MADRID)).total_seconds()
if 0 < falta <= 3 * 3600:
    print(f"Espero {falta / 60:.0f} min hasta las {objetivo:%H:%M} del {objetivo:%d/%m} (Madrid)", flush=True)
    time.sleep(falta + 5)
else:
    print("No hay que esperar.")
