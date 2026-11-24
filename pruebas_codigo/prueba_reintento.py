#!/usr/bin/env python3
"""Un vídeo rechazado dos veces no se da por perdido si quedan días (24/11/2026), y los textos de los próximos días
se comprueban con las mismas funciones que el vídeo."""
import datetime as dt
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "proceso"))
import comprobar_textos  # noqa: E402
import evangelio as ev  # noqa: E402
import publicar  # noqa: E402
import reloj  # noqa: E402

M = ev.MADRID


class Reintento(unittest.TestCase):
    def test_con_dos_dias_de_margen_se_reintenta_manana(self):
        reg = {"rehechos": 1}
        ahora = dt.datetime(2026, 11, 22, 12, 33, tzinfo=M)
        self.assertTrue(publicar.reintentar_otro_dia("2026-11-24", "pt", reg, ahora))
        self.assertEqual(reg["reintentar_desde"], "2026-11-23")
        self.assertEqual(reg["reintentos"], 1)
        self.assertNotIn("no_publicar", reg)

    def test_sin_margen_no_se_reintenta(self):
        ahora = dt.datetime(2026, 11, 23, 12, 0, tzinfo=M)  # el vídeo del 24 sale a las 07:30: faltan < 24 h
        self.assertFalse(publicar.reintentar_otro_dia("2026-11-24", "pt", {}, ahora))

    def test_tope_de_reintentos(self):
        ahora = dt.datetime(2026, 11, 20, 12, 0, tzinfo=M)
        reg = {"reintentos": publicar.MAX_REINTENTOS}
        self.assertFalse(publicar.reintentar_otro_dia("2026-11-24", "es", reg, ahora))

    def test_reloj_espera_al_dia_del_reintento(self):
        reg = {"modo": "diario", "revision": "rechazada", "reintentar_desde": "2026-11-23"}
        self.assertTrue(reloj.hecho_reg(reg, dt.date(2026, 11, 22)))   # aún no toca: no se graba
        self.assertFalse(reloj.hecho_reg(reg, dt.date(2026, 11, 23)))  # ya toca: se graba otra vez
        self.assertTrue(reloj.hecho_reg({**reg, "no_publicar": "x"}, dt.date(2026, 11, 23)))

    def test_el_reintento_no_se_arrastra_al_registro_nuevo(self):
        fuente = (RAIZ / "proceso" / "evangelio.py").read_text(encoding="utf-8")
        bloque = fuente[fuente.index('for k in ("rehechos"'):][:300]
        self.assertIn('"reintentos"', bloque)
        self.assertNotIn("reintentar_desde", bloque)


class ComprobarTextos(unittest.TestCase):
    def test_fin_de_cita(self):
        self.assertEqual(comprobar_textos.fin_de_cita("Lucas 21, 5-11", [(21, 5)]), (21, 11))
        self.assertEqual(comprobar_textos.fin_de_cita("Mateo 26, 14-27, 66", [(26, 14)]), (27, 66))
        self.assertEqual(comprobar_textos.fin_de_cita("Juan 20, 1-2. 11-18", [(20, 1)]), (20, 18))

    def test_detecta_un_pasaje_cortado(self):
        original = ev.versiculos
        ev.versiculos = lambda cita, datos, *o: [(21, v) for v in range(5, 10)]  # como salía antes del arreglo
        try:
            self.assertIn("acaba en 21,9", comprobar_textos.comprobar("Lucas 21, 5-11", "pt"))
        finally:
            ev.versiculos = original

    def test_lucas_21_completo_en_los_tres_idiomas(self):
        for idioma in ("es", "en", "pt"):
            self.assertEqual(comprobar_textos.comprobar("Lucas 21, 5-11", idioma), "", idioma)


if __name__ == "__main__":
    unittest.main()
