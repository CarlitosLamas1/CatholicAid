#!/usr/bin/env python3
"""Publicar revisado: si no se puede anotar en main lo que frena un rehacer, NO se relanza el vídeo (bucle del 16/11/2026)."""
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "proceso"))
import publicar  # noqa: E402


class Freno(unittest.TestCase):
    def test_ayudante(self):
        orig_g, orig_l = publicar.guardar_en_main, publicar.log
        try:
            publicar.log = lambda *a: None
            publicar.guardar_en_main = lambda *a, **k: False
            self.assertFalse(publicar.anotar_para_rehacer("x"))
            publicar.guardar_en_main = lambda *a, **k: True
            self.assertTrue(publicar.anotar_para_rehacer("x"))
        finally:
            publicar.guardar_en_main, publicar.log = orig_g, orig_l

    def test_ningun_guardado_ignorado(self):
        """Todo guardar_en_main se usa dentro de un «if»: ninguna llamada suelta que ignore el fallo."""
        fuente = (RAIZ / "proceso" / "publicar.py").read_text(encoding="utf-8")
        sueltas = re.findall(r"^\s+guardar_en_main\(", fuente, re.M)
        self.assertEqual(sueltas, [], "guardar_en_main sin comprobar el resultado")

    def test_los_tres_rehacer_comprueban(self):
        fuente = (RAIZ / "proceso" / "publicar.py").read_text(encoding="utf-8")
        self.assertEqual(fuente.count("if not anotar_para_rehacer("), 3)


if __name__ == "__main__":
    unittest.main()
