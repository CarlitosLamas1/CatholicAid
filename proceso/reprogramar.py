#!/usr/bin/env python3
"""CatholicAid · Reprograma en YouTube los vídeos ya subidos (privados y programados) a la hora_publicacion actual.

Para cuando cambia la hora de publicación (16/11/2026: de 00:05 a 07:30): los vídeos que ya estaban programados
con la hora anterior pasan a la nueva. Solo toca vídeos privados con publicación futura; los ya públicos no.
Mantiene los demás ajustes del estado (para niños, contenido sintético, licencia…) y anota el cambio en el registro.
Uso: python3 proceso/reprogramar.py AAAA-MM-DD [AAAA-MM-DD …]   (los tres idiomas)
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SUF = {"es": "", "en": "-en", "pt": "-pt"}
MUTABLES = ("privacyStatus", "publishAt", "license", "embeddable", "publicStatsViewable",
            "selfDeclaredMadeForKids", "containsSyntheticMedia")


def nueva_hora(fecha, idioma):
    local = dt.datetime.combine(dt.date.fromisoformat(fecha), ev.hora_pub(idioma), ev.MADRID)
    return local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reprogramar(fecha, idioma, tok):
    ruta = RAIZ / "episodios" / f"{fecha}{SUF[idioma]}.json"
    if not ruta.exists():
        print(f"[{idioma}] {fecha}: sin registro")
        return
    reg = json.loads(ruta.read_text(encoding="utf-8"))
    yt = reg.get("youtube") or {}
    if not yt.get("id"):
        print(f"[{idioma}] {fecha}: aún no está en YouTube (se subirá ya con la hora nueva)")
        return
    h = {"Authorization": f"Bearer {tok}"}
    items = ev.http(ev.YT + f"videos?part=status&id={yt['id']}", headers=h).get("items", [])
    if not items:
        print(f"[{idioma}] {fecha}: YouTube no encuentra {yt['id']}")
        return
    estado = items[0]["status"]
    nueva = nueva_hora(fecha, idioma)
    ahora = dt.datetime.now(dt.timezone.utc)
    if estado.get("privacyStatus") != "private" or not estado.get("publishAt"):
        print(f"[{idioma}] {fecha}: no está programado ({estado.get('privacyStatus')}); no lo toco")
        return
    if dt.datetime.fromisoformat(estado["publishAt"].replace("Z", "+00:00")) <= ahora:
        print(f"[{idioma}] {fecha}: su hora ya pasó; no lo toco")
        return
    if estado["publishAt"].replace(".000", "") == nueva:
        print(f"[{idioma}] {fecha}: ya está a la hora nueva")
        return
    cuerpo = {"id": yt["id"], "status": {k: estado[k] for k in MUTABLES if k in estado}}
    cuerpo["status"]["publishAt"] = nueva
    r = ev.http(ev.YT + "videos?part=status", data=cuerpo, headers=h, method="PUT")
    print(f"[{idioma}] {fecha}: {estado['publishAt']} -> {r.get('status', {}).get('publishAt')}")
    yt["publishAt"] = nueva
    reg["youtube"] = yt
    ruta.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    for idioma in ("es", "en", "pt"):
        try:
            ev.aplicar_idioma(idioma)
            tok = ev.token_youtube(idioma)
        except Exception as ex:
            print(f"[{idioma}] sin acceso ({ex})")
            continue
        for fecha in sys.argv[1:]:
            try:
                reprogramar(fecha, idioma, tok)
            except Exception as ex:
                print(f"[{idioma}] {fecha}: error {ex}")


if __name__ == "__main__":
    main()
