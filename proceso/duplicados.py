#!/usr/bin/env python3
"""CatholicAid · Buscar vídeos de YouTube que no están en ningún registro (subidas duplicadas).

Uso: python3 proceso/duplicados.py                 (informa de los tres canales; no toca nada)
     python3 proceso/duplicados.py --borrar es ID  (borra ese vídeo, solo si NO está en ningún registro)

15/11/2026: «Publicar revisado» subió el vídeo del 17/11 y falló al guardar el registro; la pasada siguiente lo subió
otra vez. El primero quedó programado sin que nadie lo supiera. Aquí se comparan las últimas subidas de cada canal con
los registros (episodios/, resumenes/, estado/musica.json).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def conocidos():
    """Todos los identificadores de YouTube que aparecen en los registros del proyecto."""
    ids = set()

    def recoger(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("id", "prueba", "reemplaza", "reemplazado", "video") and isinstance(v, str):
                    ids.add(v)
                recoger(v)
        elif isinstance(x, list):
            for v in x:
                recoger(v)

    for carpeta in ("episodios", "resumenes"):
        for p in (RAIZ / carpeta).glob("*.json"):
            try:
                reg = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            recoger(reg.get("youtube") or {})
            ids.update(v for k in ("reemplaza", "reemplazado") if isinstance(v := reg.get(k), str))
    musica = RAIZ / "estado" / "musica.json"
    if musica.exists():
        recoger(json.loads(musica.read_text(encoding="utf-8")))
    return ids


def subidas(tok, cuantas=50):
    """Las últimas subidas del canal (también privadas y programadas): [{id, titulo, estado, publica}]."""
    cab = {"Authorization": f"Bearer {tok}"}
    canal = ev.http(ev.YT + "channels?part=contentDetails&mine=true", headers=cab)["items"][0]
    lista = canal["contentDetails"]["relatedPlaylists"]["uploads"]
    d = ev.http(ev.YT + f"playlistItems?part=contentDetails&maxResults={cuantas}&playlistId={lista}", headers=cab)
    ids = [i["contentDetails"]["videoId"] for i in d.get("items", [])]
    if not ids:
        return []
    v = ev.http(ev.YT + "videos?part=snippet,status&id=" + ",".join(ids), headers=cab)
    return [{"id": i["id"], "titulo": i["snippet"]["title"], "estado": i["status"]["privacyStatus"],
             "publica": i["status"].get("publishAt", ""), "subido": i["snippet"]["publishedAt"]}
            for i in v.get("items", [])]


def sobrantes(idioma, ids=None):
    """Vídeos del canal que no figuran en ningún registro."""
    ids = conocidos() if ids is None else ids
    ev.aplicar_idioma(idioma)
    return [v for v in subidas(ev.token_youtube(idioma)) if v["id"] not in ids]


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--borrar":
        idioma, vid = sys.argv[2], sys.argv[3]
        if vid in conocidos():
            sys.exit(f"{vid} está en un registro: no lo borro.")
        ev.aplicar_idioma(idioma)
        tok = ev.token_youtube(idioma)
        ev.http(ev.YT + f"videos?id={vid}", headers={"Authorization": f"Bearer {tok}"}, method="DELETE", raw=True)
        print(f"Borrado de YouTube ({idioma}): {vid}")
        return
    ids = conocidos()
    total = 0
    for idioma in ("es", "en", "pt"):
        try:
            lista = sobrantes(idioma, ids)
        except Exception as ex:
            print(f"[{idioma}] no se pudo comprobar ({ex})")
            continue
        total += len(lista)
        print(f"[{idioma}] {len(lista)} vídeo(s) sin registro")
        for v in lista:
            print(f"   SOBRA {v['id']} · {v['estado']} · publica {v['publica'] or '—'} · subido {v['subido']} · {v['titulo']}")
    print(f"TOTAL sin registro: {total}")


if __name__ == "__main__":
    main()
