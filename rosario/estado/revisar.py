"""Borra los cuatro rosarios viejos (con «Clair de lune»), pedido por Carlos el 24/11/2026.
Solo borra si siguen privados y sin fecha de publicación (los retiró la resubida); si no, no toca nada."""
import pathlib
import sys
import urllib.error

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "proceso"))
import evangelio as ev  # noqa: E402

VIEJOS = {"gloriosos": "4MMpgbrHyXQ", "luminosos": "NfolBIYIP5g", "dolorosos": "0ksMZv7vrQA", "gozosos": "xHQyQhxatCw"}
NUEVOS = {"gloriosos": "4g5SfhRa0VY", "luminosos": "DmSKbPaNVBg", "dolorosos": "ZZqUO3F8NTo", "gozosos": "D5Cyt1T6H3c"}
tok = ev.token_youtube("es")
h = {"Authorization": f"Bearer {tok}"}
d = ev.http(ev.YT + "videos?part=status,snippet&id=" + ",".join(list(VIEJOS.values()) + list(NUEVOS.values())),
            headers=h)
por_id = {i["id"]: i for i in d.get("items", [])}
for clave, vid in VIEJOS.items():
    nuevo = por_id.get(NUEVOS[clave], {}).get("status", {})
    if not nuevo.get("publishAt"):
        print(f"{clave}: el nuevo ({NUEVOS[clave]}) no está programado; NO borro el viejo")
        continue
    st = por_id.get(vid, {}).get("status")
    if not st:
        print(f"{clave}: {vid} ya no existe")
        continue
    if st.get("privacyStatus") != "private" or st.get("publishAt"):
        print(f"{clave}: {vid} no está privado sin fecha ({st}); no lo borro")
        continue
    try:
        ev.http(ev.YT + f"videos?id={vid}", None, h, method="DELETE", raw=True)
        print(f"{clave}: borrado {vid} · queda el nuevo {NUEVOS[clave]} ({nuevo['publishAt']})")
    except urllib.error.HTTPError as e:
        print(f"{clave}: no pude borrar {vid}: {e.code} {e.read().decode(errors='replace')[:200]}")
