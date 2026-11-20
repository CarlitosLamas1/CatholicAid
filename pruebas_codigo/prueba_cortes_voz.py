#!/usr/bin/env python3
"""Mejoras del 20/11/2026: signos sueltos al principio de un trozo («. Él respondió:»), cortes en el centro del silencio
de verdad, pausas según el momento, tono suspendido tras «dijo:» y evangelista en la línea de lectura. Sin red ni cupo."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proceso"))
import evangelio as ev  # noqa: E402


class Signos(unittest.TestCase):
    def test_punto_tras_la_cita_va_al_anterior(self):
        g = {"fragmentos": [
            {"personaje": "narrador", "texto": "Le preguntó:", "escena": 1},
            {"personaje": "jesus", "texto": "“¿Qué quieres que te haga?”", "escena": 1},
            {"personaje": "narrador", "texto": ". Él respondió:", "escena": 1}]}
        frs = ev.preparar_fragmentos(g, {"titulo": "Lectura del santo evangelio según san Lucas."})
        self.assertEqual(frs[2]["texto"], "“¿Qué quieres que te haga?”.")
        self.assertEqual(frs[3]["texto"], "Él respondió:")
        self.assertEqual(ev.normalizar("".join(f["texto"] for f in frs[1:-1])),
                         ev.normalizar("".join(f["texto"] for f in g["fragmentos"])))

    def test_registro_antiguo(self):
        frs = ev.signos_al_anterior([{"texto": "“Recobra la vista”"}, {"texto": ". Y al instante vio."}])
        self.assertEqual([f["texto"] for f in frs], ["“Recobra la vista”.", "Y al instante vio."])

    def test_sin_signos_no_cambia(self):
        frs = ev.signos_al_anterior([{"texto": "dijo:"}, {"texto": "“Venid”"}])
        self.assertEqual([f["texto"] for f in frs], ["dijo:", "“Venid”"])


class Cortes(unittest.TestCase):
    def test_corte_tardio_vuelve_al_silencio(self):
        # Silencio real 10,0–10,8; el corte caía en 10,95 (dentro de la frase siguiente)
        self.assertEqual(ev.ajustar_cortes([10.95], [(10.0, 10.8)]), [(10.0, 10.8)])

    def test_sin_silencio_cerca_no_es_fiable(self):
        self.assertIsNone(ev.ajustar_cortes([20.0], [(10.0, 10.8)]))

    def test_ignora_microsilencios(self):
        self.assertEqual(ev.ajustar_cortes([10.9], [(10.85, 10.95), (10.0, 10.6)]), [(10.0, 10.6)])

    def test_trozos_sin_la_pausa(self):
        partes = ev.partes_sin_pausa([(10.0, 11.0)], 20.0)
        self.assertEqual([tuple(round(x, 2) for x in p) for p in partes], [(0.0, 10.08), (10.95, 20.0)])

    def test_pausa_corta_no_se_cruza(self):
        a, b = ev.partes_sin_pausa([(5.0, 5.1)], 9.0)
        self.assertLessEqual(a[1], b[0])


class Pausas(unittest.TestCase):
    FRS = [{"personaje": "narrador", "texto": "Lectura del santo evangelio según san Lucas."},
           {"personaje": "narrador", "texto": "Le preguntó:"},
           {"personaje": "jesus", "texto": "“¿Qué quieres?”."},
           {"personaje": "narrador", "texto": "Y se fue."},
           {"personaje": "narrador", "texto": "Y volvió."},
           {"personaje": "narrador", "texto": "Palabra del Señor.", "palabra": True}]

    def test_segun_el_momento(self):
        p = [ev.pausa_tras(self.FRS, i) for i in range(5)]
        self.assertEqual(p, [0.5, 0.25, 0.45, 0.35, 0.8])


class Tono(unittest.TestCase):
    def test_solo_si_presenta_a_quien_habla(self):
        self.assertTrue(ev.con_tono("Lee", ["Y le dijo:"]).startswith(ev.txt("anuncia")))
        self.assertEqual(ev.con_tono("Lee", ["Y se fue."]), "Lee")


if __name__ == "__main__":
    unittest.main()
