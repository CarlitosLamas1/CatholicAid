#!/usr/bin/env python3
"""Hora de publicación: la misma en los tres idiomas y los cron de respaldo de TikTok e Instagram (que publican
al llegar, sin esperar) caen SIEMPRE después de ella, en invierno y en verano."""
import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "proceso"))
import evangelio as ev  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
CFG = json.loads((RAIZ / "config" / "personajes.json").read_text(encoding="utf-8"))


def crons(workflow):
    texto = (RAIZ / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    return [tuple(map(int, m)) for m in re.findall(r'cron:\s*"(\d+)\s+(\d+)\s+\*\s+\*\s+\*"', texto)]


class Horas(unittest.TestCase):
    def test_misma_hora_en_los_tres_idiomas(self):
        horas = {ev.a_hora(CFG[k]) for k in ("hora_publicacion", "hora_publicacion_en", "hora_publicacion_pt")}
        self.assertEqual(len(horas), 1)

    def test_respaldos_despues_de_la_hora(self):
        hora = ev.a_hora(CFG["hora_publicacion"])
        for wf in ("tiktok-publicar.yml", "instagram-publicar.yml"):
            lista = crons(wf)
            self.assertTrue(lista, wf)
            for dia in (dt.date(2026, 12, 15), dt.date(2027, 7, 15)):  # invierno y verano
                publica = dt.datetime.combine(dia, hora, MADRID)
                for minuto, h in lista:
                    cron = dt.datetime(dia.year, dia.month, dia.day, h, minuto, tzinfo=dt.timezone.utc)
                    self.assertGreater(cron, publica, f"{wf} {h:02d}:{minuto:02d} UTC el {dia}")
                    self.assertLess(cron - publica, dt.timedelta(hours=4), f"{wf} demasiado tarde el {dia}")


if __name__ == "__main__":
    unittest.main()
