"""Pone la lista «Santo Rosario» como sección de la portada del canal español (una vez; si ya está, no hace nada)."""
import json
import pathlib
import sys
import urllib.error

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "proceso"))
import evangelio as ev  # noqa: E402

tok = ev.token_youtube("es")
h = {"Authorization": f"Bearer {tok}"}
listas = ev.http(ev.YT + "playlists?part=snippet&mine=true&maxResults=50", headers=h).get("items", [])
lista = next(p["id"] for p in listas if p["snippet"]["title"] == "Santo Rosario")
print("Lista Santo Rosario:", lista)
secciones = ev.http(ev.YT + "channelSections?part=snippet,contentDetails&mine=true", headers=h).get("items", [])
for s in secciones:
    print("Sección:", s["snippet"].get("type"), s["snippet"].get("position"), s["snippet"].get("title", ""),
          (s.get("contentDetails") or {}).get("playlists", []))
if any(lista in (s.get("contentDetails") or {}).get("playlists", []) for s in secciones):
    print("Ya está en la portada: no hago nada")
    sys.exit()
try:
    r = ev.http(ev.YT + "channelSections?part=snippet,contentDetails",
                {"snippet": {"type": "singlePlaylist", "position": 1 if secciones else 0},
                 "contentDetails": {"playlists": [lista]}}, h, method="POST")
    print("Sección añadida:", json.dumps(r.get("snippet"), ensure_ascii=False))
except urllib.error.HTTPError as e:
    print("No se pudo añadir la sección:", e.code, e.read().decode(errors="replace")[:500])
