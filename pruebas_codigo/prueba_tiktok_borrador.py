#!/usr/bin/env python3
"""TikTok: subir como borrador usa el punto de bandeja (inbox), sin texto ni privacidad, y trocea bien."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proceso"))
import tiktok  # noqa: E402


class Borrador(unittest.TestCase):
    def test_trozos(self):
        self.assertEqual(tiktok._trozos(5_000_000), (5_000_000, 1))
        self.assertEqual(tiktok._trozos(25_000_000), (25_000_000, 1))
        self.assertEqual(tiktok._trozos(95_000_000), (10_000_000, 9))

    def test_borrador_usa_inbox_sin_texto(self):
        llamadas = []

        def api(ruta, token, cuerpo=None):
            llamadas.append((ruta, cuerpo))
            if ruta.endswith("inbox/video/init/"):
                return {"publish_id": "v_inbox_file~1", "upload_url": "https://subida/x"}
            return {"status": "SEND_TO_USER_INBOX"}

        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(b"0" * 1000)
            f.flush()
            with mock.patch.object(tiktok, "acceso", return_value="tok"), \
                    mock.patch.object(tiktok, "_api", side_effect=api), \
                    mock.patch.object(tiktok, "_enviar") as enviar, \
                    mock.patch.object(tiktok.time, "sleep"):
                r = tiktok.subir_borrador(f.name)
        self.assertEqual(r, ("v_inbox_file~1", "SEND_TO_USER_INBOX"))
        self.assertEqual(llamadas[0][0], "post/publish/inbox/video/init/")
        self.assertNotIn("post_info", llamadas[0][1])
        self.assertEqual(llamadas[0][1]["source_info"]["video_size"], 1000)
        enviar.assert_called_once()
        self.assertFalse(any("creator_info" in c[0] for c in llamadas))


if __name__ == "__main__":
    unittest.main()
