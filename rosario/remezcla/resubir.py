"""Sube los rosarios remezclados (nuevo-<clave>.mp4) y retira los anteriores (privados sin fecha y fuera de la lista).

Orden seguro: primero sube el nuevo programado; solo si sale bien retira el viejo. Nunca borra vídeos."""
import json
import pathlib
import sys
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "proceso"))
sys.path.insert(0, str(RAIZ / "rosario" / "subir"))
import evangelio as ev  # noqa: E402
import subir  # noqa: E402

subir.MUSICA = ["Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg", "Chopin_-_Nocturne-op-55-no-1.ogg",
                "Schubert_-_Piano_Sonata_No._13_in_A_major,_D664_-_II._Andante_(Paul_Pitman).flac",
                "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._55.ogg",
                "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._62.ogg"]
VIEJOS = {"gloriosos": "4MMpgbrHyXQ", "luminosos": "NfolBIYIP5g", "dolorosos": "0ksMZv7vrQA", "gozosos": "xHQyQhxatCw"}
MUTABLES = ("privacyStatus", "license", "embeddable", "publicStatsViewable", "selfDeclaredMadeForKids",
            "containsSyntheticMedia")
ARCH = RAIZ / "rosario" / "subir" / "archivos"
tok = ev.token_youtube("es")
h = {"Authorization": f"Bearer {tok}"}


def lista_rosario():
    d = ev.http(ev.YT + "playlists?part=snippet&mine=true&maxResults=50", headers=h)
    return next(p["id"] for p in d["items"] if p["snippet"]["title"] == "Santo Rosario")


def retirar(vid, lista):
    item = ev.http(ev.YT + f"videos?part=status&id={vid}", headers=h)["items"][0]
    estado = {k: v for k, v in item["status"].items() if k in MUTABLES}
    estado["privacyStatus"] = "private"  # sin publishAt: ya no se publica solo
    ev.http(ev.YT + "videos?part=status", {"id": vid, "status": estado}, h, method="PUT")
    items = ev.http(ev.YT + f"playlistItems?part=snippet&maxResults=50&playlistId={lista}", headers=h)["items"]
    for it in items:
        if it["snippet"]["resourceId"]["videoId"] == vid:
            ev.http(ev.YT + f"playlistItems?id={it['id']}", None, h, method="DELETE", raw=True)  # 204 sin cuerpo
    print(f"   retirado {vid}: privado sin fecha y fuera de la lista", flush=True)


lista = lista_rosario()
hechos = {t: v for t, v in subir.ya_subidos(tok).items() if v not in VIEJOS.values()}
resultado = []
for r in subir.PLAN["rosarios"]:
    meta = subir.metadatos(r)
    titulo = meta["snippet"]["title"]
    if titulo in hechos:
        print(f"{r['clave']}: ya hay uno nuevo (https://youtu.be/{hechos[titulo]}); no lo repito")
        continue
    video = ARCH / f"nuevo-{r['clave']}.mp4"
    resp, _ = ev.http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                      meta, {"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                             "X-Upload-Content-Length": str(video.stat().st_size)}, method="POST", raw=True)
    req = urllib.request.Request(resp.headers["Location"], data=video.read_bytes(), method="PUT",
                                 headers={"Content-Type": "video/mp4", "User-Agent": ev.UA})
    with urllib.request.urlopen(req, timeout=3600) as r2:
        vid = json.loads(r2.read())["id"]
    print(f"{r['clave']}: subido https://youtu.be/{vid} · {meta['status'].get('publishAt', meta['status']['privacyStatus'])}",
          flush=True)
    reg = {"clave": r["clave"], "id": vid, **meta["status"]}
    reg["lista"] = ev.anadir_a_lista(tok, subir.LISTA[0], subir.LISTA[1], vid, "es")
    reg["miniatura"] = ev.subir_miniatura(tok, vid, ARCH / f"miniatura_{r['clave']}.jpg")
    try:
        retirar(VIEJOS[r["clave"]], lista)
    except Exception as e:  # el nuevo ya está: que se vea el fallo para retirar el viejo a mano
        print(f"   ¡OJO! No pude retirar {VIEJOS[r['clave']]}: {e}", flush=True)
        reg["retirar_falla"] = str(e)
    resultado.append(reg)
print(json.dumps(resultado, ensure_ascii=False, indent=1))
if any("retirar_falla" in r for r in resultado):
    sys.exit(1)
