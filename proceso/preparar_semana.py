#!/usr/bin/env python3
"""Deja preparado en el repo lo que necesita el gestor semanal (que trabaja sin acceso a internet):
- biblia/citas.json: cita del Evangelio de los próximos 10 días (Vatican News).
- biblia/torres-amat/<libro>.json: texto original de Torres Amat de cada libro que aparezca.
"""
import datetime as dt
import json

from evangelio import MADRID, RAIZ, cargar_libro, log, obtener_evangelio

ruta = RAIZ / "biblia" / "citas.json"
citas = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
hoy = dt.datetime.now(MADRID).date()
for i in range(1, 11):
    fecha = hoy + dt.timedelta(days=i)
    try:
        ev = obtener_evangelio(fecha)
        citas[str(fecha)] = ev["cita"]
        cargar_libro(ev["cita"].split()[0])
        log(f"{fecha}: {ev['cita']}")
    except Exception as e:
        log(f"{fecha}: sin cita ({e})")
ruta.write_text(json.dumps(dict(sorted(citas.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
