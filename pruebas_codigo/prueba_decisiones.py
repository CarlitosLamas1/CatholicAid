#!/usr/bin/env python3
"""Decisiones que no deben romperse: cuándo graban inglés y portugués, cuándo se rehacen, qué se limpia y cómo
queda el título de YouTube. No usan red ni gastan cupo."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proceso"))
import evangelio as ev  # noqa: E402
import mantenimiento  # noqa: E402
import publicar  # noqa: E402
import reloj  # noqa: E402


class EsperaAlEspanol(unittest.TestCase):
    def test_sin_espanol_espera(self):
        self.assertTrue(reloj.espera_al_espanol({}, True, 12))

    def test_espanol_sin_revisar_espera(self):
        self.assertTrue(reloj.espera_al_espanol({"modo": "diario", "revision": "pendiente"}, True, 15))
        self.assertTrue(reloj.espera_al_espanol({"modo": "diario", "revision": "pendiente"}, False, 22))

    def test_espanol_aprobado_graba(self):
        self.assertEqual(reloj.espera_al_espanol({"modo": "diario", "revision": "ok"}, False, 10), "")
        self.assertEqual(reloj.espera_al_espanol({"modo": "diario", "youtube": {"id": "x"}}, True, 10), "")

    def test_de_noche_no_se_pierde_el_dia(self):
        self.assertEqual(reloj.espera_al_espanol({"modo": "diario", "revision": "pendiente"}, True, 21), "")
        self.assertEqual(reloj.espera_al_espanol({}, True, 23), "")
        self.assertTrue(reloj.espera_al_espanol({}, False, 23))  # pasado mañana: hay un día de margen

    def test_una_prueba_no_cuenta(self):
        self.assertTrue(reloj.espera_al_espanol({"modo": "prueba", "revision": "ok"}, True, 12))


class Desfasado(unittest.TestCase):
    ES = {"frase_clave": "Tu fe te ha salvado", "reflexion": "R", "generado": "2026-11-15T02:46:28+01:00"}

    def test_coincide(self):
        otro = {"frase_es": "Tu fe te ha salvado", "reflexion_es": "R", "generado": "2026-11-15T03:10:00+01:00"}
        self.assertEqual(publicar.desfasado(self.ES, otro), "")

    def test_frase_cambiada(self):
        otro = {"frase_es": "Zaqueo, baja", "reflexion_es": "R", "generado": "2026-11-15T01:01:00+01:00"}
        self.assertIn("frase", publicar.desfasado(self.ES, otro))

    def test_reflexion_cambiada(self):
        otro = {"frase_es": "Tu fe te ha salvado", "reflexion_es": "otra", "generado": "2026-11-15T03:10:00+01:00"}
        self.assertIn("reflexión", publicar.desfasado(self.ES, otro))

    def test_imagenes_repintadas_despues(self):
        es = {**self.ES, "repintados": 1}
        antes = {"frase_es": "Tu fe te ha salvado", "reflexion_es": "R", "generado": "2026-11-15T01:01:00+01:00"}
        despues = {**antes, "generado": "2026-11-15T03:10:00+01:00"}
        self.assertIn("repintó", publicar.desfasado(es, antes))
        self.assertEqual(publicar.desfasado(es, despues), "")

    def test_registro_antiguo(self):
        es = {**self.ES, "rehechos": 1}
        self.assertTrue(publicar.desfasado(es, {"generado": "2026-11-15T01:01:00+01:00"}))
        self.assertEqual(publicar.desfasado(self.ES, {"generado": "2026-11-15T01:01:00+01:00"}), "")


class Mantenimiento(unittest.TestCase):
    HOY = dt.date(2026, 11, 15)

    def test_releases(self):
        etiquetas = ["tiktok-2026-11-17", "tiktok-2026-11-13", "en-2026-11-07", "pt-2026-11-12",
                     "archivo-2026-09", "version-estable-2026-11-07"]
        self.assertEqual(mantenimiento.releases_viejas(etiquetas, self.HOY), ["en-2026-11-07", "pt-2026-11-12"])

    def test_imagenes(self):
        nombres = ["2026-09-01_e1.jpg", "2026-09-15_e2.png", "2026-10-30_e1.jpg", "LEEME.txt"]
        self.assertEqual(mantenimiento.imagenes_viejas(nombres, self.HOY), {"2026-09": nombres[:2]})


class FraseClave(unittest.TestCase):
    def test_se_entienden_solas(self):
        for f in ("Recobra la vista; tu fe te ha salvado", "Hoy ha sido día de salvación para esta casa",
                  "Receive your sight. Your faith has healed you.", "Acordaos de la mujer de Lot."):
            self.assertTrue(ev.frase_valida(f), f)

    def test_dependen_de_lo_anterior(self):
        for f in ("De la misma manera, el que había recibido dos ganó otros dos.",
                  "he also who got the two gained another two.",
                  "Do mesmo modo, o que tinha recebido dois ganhou outros dois."):
            self.assertFalse(ev.frase_valida(f), f)

    def test_longitud(self):
        self.assertFalse(ev.frase_valida("Venid a mí"))
        self.assertFalse(ev.frase_valida("palabra " * 13))

    def test_el_revisor_pide_otra(self):
        self.assertTrue(publicar.FRASE_FLOJA.search("La frase clave («Do mesmo modo…») es floja: no se entiende sola."))
        self.assertFalse(publicar.FRASE_FLOJA.search("La frase clave es corta pero literal y se entiende; aceptable."))

    def test_la_reserva_no_repite_la_descartada(self):
        frs = [{"personaje": "jesus", "texto": "Pedid y se os dará. Buscad y hallaréis lo que buscáis."}]
        primera = ev.frase_de_reserva(frs)
        self.assertTrue(primera)
        self.assertNotEqual(ev.frase_de_reserva(frs, "", (primera,)), primera)


class Titulo(unittest.TestCase):
    def test_cabe_en_100_y_lleva_cita(self):
        for idioma, cita in (("es", "Lucas 19, 1-10"), ("en", "Luke 19:1-10"), ("pt", "Lucas 19,1-10")):
            for frase in ("Tu fe te ha salvado", "palabra " * 30):
                t = ev.titulo_youtube({"frase_clave": frase, "cita": cita}, dt.date(2026, 11, 17), idioma)
                self.assertLessEqual(len(t), 100, t)
                self.assertIn(cita, t)

    def test_empieza_en_mayuscula(self):
        t = ev.titulo_youtube({"frase_clave": "recobra la vista", "cita": "Lucas 18, 35-43"}, dt.date(2026, 11, 16))
        self.assertTrue(t.startswith("“Recobra la vista”"), t)


if __name__ == "__main__":
    unittest.main()
