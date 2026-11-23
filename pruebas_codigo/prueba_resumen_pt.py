import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proceso"))
import resumen_semanal as r  # noqa: E402


class ResumenPt(unittest.TestCase):
    def test_textos_pt(self):
        t = r.textos("pt", dt.date(2026, 11, 16), dt.date(2026, 11, 22))
        self.assertTrue(t["titulo"].startswith("Evangelho da semana"))
        self.assertLessEqual(len(t["titulo"]), 100)
        self.assertEqual(r.nombre_dia(dt.date(2026, 11, 16), "pt"), "Segunda 16")


if __name__ == "__main__":
    unittest.main()
