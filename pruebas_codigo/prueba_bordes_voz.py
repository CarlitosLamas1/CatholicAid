#!/usr/bin/env python3
"""Ninguna palabra se pierde al cortar la grabación de un personaje (28/11/2026).

Español del 28/11 (Lucas 21,34-36): whisper no reconoció «porque vendrá» al principio del segundo trozo de Jesús y
se cortó en la pausa más larga hasta la primera palabra reconocida, ya dentro de la frase siguiente: «porque vendrá»
desapareció y «Velad, pues» se oyó «pues». Además el arranque suave de «No permitas» y «Palabra» se recortaba."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proceso"))
import evangelio as ev  # noqa: E402


class Corte(unittest.TestCase):
    # «…como un lazo;» acaba en 12,0 · pausa 12,0–12,5 · «porque vendrá» 12,5–13,2 · pausa 13,2–13,9 (respiración
    # larga) · «sobre todos…» desde 13,9
    SIL = [(12.0, 12.5), (13.2, 13.9)]

    def test_primera_pausa_si_no_se_oyo_el_principio(self):
        corte = ev.elegir_corte(self.SIL, fin_prev=12.0, ini_sig=13.9, ultima_oida=True, primera_oida=False)
        self.assertTrue(12.0 <= corte <= 12.5, corte)

    def test_ultima_pausa_si_no_se_oyo_el_final(self):
        corte = ev.elegir_corte([(5.0, 5.3), (6.0, 6.4)], fin_prev=4.0, ini_sig=6.5, ultima_oida=False,
                                primera_oida=True)
        self.assertTrue(6.0 <= corte <= 6.4, corte)

    def test_sin_bordes_oidos_no_es_fiable(self):
        self.assertIsNone(ev.elegir_corte(self.SIL, 12.0, 13.9, False, False))

    def test_con_ambos_bordes_como_antes(self):
        self.assertAlmostEqual(ev.elegir_corte([(12.0, 12.6)], 12.1, 12.5, True, True), 12.3)

    def test_arranque_con_margen(self):
        partes = ev.partes_sin_pausa([(10.0, 11.0)], 20.0)
        self.assertAlmostEqual(partes[1][0], 10.82)  # 0,18 s antes de que vuelva la voz


class Bordes(unittest.TestCase):
    def test_se_oye_entero(self):
        self.assertTrue(ev.bordes_se_oyen(["no", "permitas", "que", "mirada"], ["no", "permitas", "que", "mirada"]))

    def test_falta_el_principio(self):
        self.assertFalse(ev.bordes_se_oyen(["porque", "vendra", "sobre", "todos", "tierra"],
                                           ["sobre", "todos", "los", "que", "habitan", "tierra"]))

    def test_sobra_el_principio_del_siguiente(self):
        self.assertFalse(ev.bordes_se_oyen(["os", "sorprenda", "como", "un", "lazo"],
                                           ["os", "sorprenda", "como", "un", "lazo", "porque", "vendra", "sobre", "todos"]))

    def test_tolera_una_letra_mal_oida(self):
        self.assertTrue(ev.bordes_se_oyen(["velad", "pues", "hombre"], ["velad", "pues", "hombres"]))


if __name__ == "__main__":
    unittest.main()
