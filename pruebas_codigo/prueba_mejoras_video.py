#!/usr/bin/env python3
"""Mejoras del vídeo del 17/11/2026: frase clave literal aunque cambie una coma, gancho de 3–5 s según la frase,
personajes secundarios con el mismo aspecto y hoja de fotogramas para el revisor. Sin red ni cupo."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proceso"))
import evangelio as ev  # noqa: E402
import mantenimiento  # noqa: E402


class FraseLiteral(unittest.TestCase):
    TEXTO = ["Yo os digo que a todo el que tiene, se le dará; pero al que no tiene, aun lo que tiene se le quitará."]

    def test_coma_distinta_se_recupera_la_del_texto(self):
        self.assertEqual(ev.literal_en("a todo el que tiene se le dará", self.TEXTO), "a todo el que tiene, se le dará")

    def test_palabra_distinta_no_vale(self):
        self.assertEqual(ev.literal_en("a todo el que tenga se le dará", self.TEXTO), "")

    def test_no_corta_palabras(self):
        self.assertEqual(ev.literal_en("tiene se le", ["mantiene se le"]), "")


class DuracionGancho(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(ev.CFG)
        ev.CFG.pop("gancho_ab", None)
        ev.CFG["gancho"] = {"base": 1.5, "por_palabra": 0.3, "minimo": 3.0, "maximo": 5.0}

    def tearDown(self):
        ev.CFG.clear()
        ev.CFG.update(self.cfg)

    def test_entre_3_y_5(self):
        f = dt.date(2026, 11, 18)
        self.assertEqual(ev.gancho_del_dia(f, "Venid a mí todos"), 3.0)
        self.assertEqual(ev.gancho_del_dia(f, "Hoy ha sido día de salvación para esta casa"), 4.2)
        self.assertEqual(ev.gancho_del_dia(f, "palabra " * 20), 5.0)

    def test_config_real_sin_ab(self):
        self.assertNotIn("gancho_ab", self.cfg)
        self.assertIn("gancho", self.cfg)


class ReparteVisual(unittest.TestCase):
    def test_en_escena(self):
        self.assertTrue(ev.en_escena("Zacchaeus", "Zacchaeus climbs a sycamore tree"))
        self.assertTrue(ev.en_escena("The rich master", "The master gives coins to his servants"))
        self.assertFalse(ev.en_escena("Zacchaeus", "Jesus walks through Jericho"))


class HojaFotogramas(unittest.TestCase):
    def test_momentos(self):
        m = ev.momentos_hoja(100.0, 4.0, 2.5)
        self.assertEqual(len(m), 8)
        self.assertEqual(m[0], 2.0)  # mitad del gancho
        self.assertTrue(all(4.0 < x < 97.5 for x in m[1:]))

    def test_mantenimiento_borra_viejas(self):
        hoy = dt.date(2026, 11, 20)
        viejos = mantenimiento.fotogramas_viejos(["2026-11-10.jpg", "2026-11-10-en.jpg", "2026-11-19-pt.jpg", "x.jpg"], hoy)
        self.assertEqual(viejos, ["2026-11-10-en.jpg", "2026-11-10.jpg"])


if __name__ == "__main__":
    unittest.main()
