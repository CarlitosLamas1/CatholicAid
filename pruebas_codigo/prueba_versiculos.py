#!/usr/bin/env python3
"""La cita manda: un pasaje nunca pierde versículos porque una Biblia (OCR) tenga el capítulo cortado.

24/11/2026: el Figueiredo original acaba Lucas 21 en el v. 9 («IO» por «10») y el vídeo en portugués de
Lucas 21,5-11 salió con 5-9; el revisor lo rechazó dos veces y no se publicó."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "proceso"))
import evangelio as ev  # noqa: E402


class Versiculos(unittest.TestCase):
    def test_capitulo_cortado_en_el_original(self):
        datos = {"21": {str(v): "x" for v in range(1, 10)}}
        self.assertEqual(ev.versiculos("Lucas 21, 5-11", datos), [(21, v) for v in range(5, 12)])

    def test_cruza_capitulo_con_la_revisada(self):
        datos = {"26": {str(v): "x" for v in range(1, 70)}, "27": {"1": "x", "2": "x"}}
        rev = {"26": {"75": "x"}}
        vs = ev.versiculos("Mateo 26, 74-27, 2", datos, rev)
        self.assertEqual(vs, [(26, 74), (26, 75), (27, 1), (27, 2)])

    def test_tramos(self):
        self.assertEqual(ev.versiculos("Juan 20, 1-2. 11-13", {"20": {}}),
                         [(20, 1), (20, 2), (20, 11), (20, 12), (20, 13)])

    def test_lucas_21_portugues_entero(self):
        texto, _ = ev.texto_figueiredo("Lucas 21, 5-11")
        self.assertIn("Uma nação se levantará contra outra nação", texto)
        self.assertIn("grandes sinais no céu", texto)


if __name__ == "__main__":
    unittest.main()
