#!/usr/bin/env python3
"""El capítulo 1 de los Evangelios no se pierde y el rosario del día es el que toca.

24/11/2026: Wikisource escribe «CAPÍTULO PRIMERO» en letra y solo se leían los romanos: faltaba el capítulo 1 de
los cuatro Evangelios (8/12 y 17-25/12: Lucas 1, Mateo 1, Juan 1)."""
import datetime as dt
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "proceso"))
import evangelio as ev  # noqa: E402


class Capitulos(unittest.TestCase):
    def test_numero_en_letra_y_romano(self):
        self.assertEqual(ev.numero_capitulo("CAPÍTULO PRIMERO."), 1)
        self.assertEqual(ev.numero_capitulo("CAPITULO XXIV."), 24)
        self.assertEqual(ev.numero_capitulo("CAPÍTULO IX"), 9)
        self.assertIsNone(ev.numero_capitulo("El capítulo siguiente"))

    def test_lee_el_primer_capitulo(self):
        texto = ("EL SANTO EVANGELIO\n1 Prólogo que no es versículo\nCAPÍTULO PRIMERO.\nResumen\n"
                 "1 En el principio era el Verbo,\ny el Verbo estaba en Dios.\n2 Él estaba en el principio.\n"
                 "CAPÍTULO II.\n1 Tres días después.")
        d = ev.leer_torres_amat(texto)
        self.assertEqual(d["1"]["1"], "En el principio era el Verbo, y el Verbo estaba en Dios.")
        self.assertEqual(d["1"]["2"], "Él estaba en el principio.")
        self.assertEqual(d["2"]["1"], "Tres días después.")

    def test_solo_anade_lo_que_falta(self):
        guardado = {"2": {"1": "texto revisado a mano"}}
        descargado = {"1": {"1": "nuevo"}, "2": {"1": "otro texto"}}
        junto, nuevos = ev.completar_capitulos(guardado, descargado)
        self.assertEqual(nuevos, ["1"])
        self.assertEqual(junto["2"]["1"], "texto revisado a mano")
        self.assertEqual(junto["1"]["1"], "nuevo")


class Rosario(unittest.TestCase):
    def test_misterios_por_dia(self):
        f = dt.date(2026, 11, 23)  # lunes
        nombres = [ev.rosario_del_dia(f + dt.timedelta(days=i)) for i in range(6)]
        self.assertEqual(nombres, ["gozosos", "dolorosos", "gloriosos", "luminosos", "dolorosos", "gozosos"])

    def test_domingos_segun_el_tiempo(self):
        self.assertEqual(ev.rosario_del_dia(dt.date(2026, 11, 22)), "gloriosos")  # ordinario
        self.assertEqual(ev.rosario_del_dia(dt.date(2026, 12, 6)), "gozosos")  # Adviento
        self.assertEqual(ev.rosario_del_dia(dt.date(2027, 2, 21)), "dolorosos")  # Cuaresma

    def test_frase_sin_enlace(self):
        linea = ev.linea_rosario(dt.date(2026, 11, 26))
        self.assertIn("misterios luminosos", linea)
        self.assertNotIn("http", linea)


if __name__ == "__main__":
    unittest.main()
