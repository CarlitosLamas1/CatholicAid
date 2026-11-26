"""Rosario v2: sube un rosario montado (artefacto del montaje), público, a la lista «Santo Rosario» con su miniatura,
y borra de YouTube el vídeo viejo de ese rosario (pedido por Carlos el 26/11/2026).
Orden seguro: primero sube el nuevo; solo si sale bien borra el viejo. No repite un título ya subido."""
import json
import pathlib
import sys
import urllib.error
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "proceso"))
import evangelio as ev  # noqa: E402

PLAN = json.loads((RAIZ / "rosario" / "v2" / "subir.json").read_text(encoding="utf-8"))
GUION = json.loads((RAIZ / "rosario" / "v2" / "guion.json").read_text(encoding="utf-8"))
ARCH = pathlib.Path("/tmp/montado")
MUSICA = ["Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg", "Chopin_-_Nocturne-op-55-no-1.ogg",
          "Schubert_-_Piano_Sonata_No._13_in_A_major,_D664_-_II._Andante_(Paul_Pitman).flac",
          "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._55.ogg",
          "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._62.ogg"]
DIAS = {"gozosos": "los lunes y los sábados", "dolorosos": "los martes y los viernes",
        "gloriosos": "los miércoles y los domingos", "luminosos": "los jueves"}
LISTA = ("Santo Rosario", "El Santo Rosario completo y guiado a dos voces, con una lectura breve del Evangelio en "
         "cada misterio: gozosos (lunes y sábado), dolorosos (martes y viernes), gloriosos (miércoles y domingo) y "
         "luminosos (jueves). #SantoRosario #RosarioDeHoy")


def metadatos(clave):
    r = GUION["rosarios"][clave]
    titulo = f"Santo Rosario de hoy · {r['titulo']} ({r['dias']}) · Rosario completo"[:100]
    caps = (ARCH / f"rosario-{clave}.capitulos.txt").read_text(encoding="utf-8").strip()
    lect = " · ".join(m["cita"] for m in r["misterios"])
    creditos = "; ".join(c for c in (ev.credito_musica({"musica": m}) for m in MUSICA) if c)
    desc = (f"Reza con nosotros el Santo Rosario: {r['titulo'].lower()}, que se rezan {DIAS[clave]}. "
            f"Rosario completo y guiado a dos voces; san {r['evangelista']} lee en cada misterio un pasaje breve del "
            "Evangelio. Para rezar en casa, en familia o de camino.\n\n"
            f"Capítulos:\n{caps}\n\n"
            f"📖 Lecturas: {lect} (Biblia de Torres Amat, 1836, con la ortografía actual).\n"
            "📿 Los cuatro rosarios, en la lista «Santo Rosario» del canal.\n"
            "✝️ Cada mañana, el Evangelio del día en un vídeo corto: suscríbete para no perderlo.\n\n"
            "🎨 Imágenes generadas con IA.\n🎙️ Voces generadas con inteligencia artificial.\n"
            f"🎵 Música: {creditos}\n\n"
            f"#SantoRosario #RosarioDeHoy #{r['titulo'].title().replace(' ', '')} #Rosario #Catolico")
    etiquetas = ["santo rosario", "rosario de hoy", "rosario completo", r["titulo"].lower(), "rosario católico",
                 "rosario en español", "virgen maría", "oración"]
    return {"snippet": {"title": titulo, "description": desc[:4900], "categoryId": "22", "tags": etiquetas,
                        "defaultLanguage": "es", "defaultAudioLanguage": "es"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}


def main():
    clave, viejo = PLAN["rosario"], PLAN.get("borrar")
    tok = ev.token_youtube("es")
    h = {"Authorization": f"Bearer {tok}"}
    canal = ev.http(ev.YT + "channels?part=contentDetails&mine=true", headers=h)["items"][0]
    subidas = canal["contentDetails"]["relatedPlaylists"]["uploads"]
    hechos = {i["snippet"]["title"]: i["snippet"]["resourceId"]["videoId"] for i in ev.http(
        ev.YT + f"playlistItems?part=snippet&maxResults=50&playlistId={subidas}", headers=h).get("items", [])
        if i["snippet"]["resourceId"]["videoId"] != viejo}
    meta = metadatos(clave)
    if meta["snippet"]["title"] in hechos:
        vid = hechos[meta["snippet"]["title"]]
        print(f"{clave}: ya está subido el nuevo (https://youtu.be/{vid}); no lo repito")
    else:
        video = ARCH / f"rosario-{clave}.mp4"
        resp, _ = ev.http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                          meta, {"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                                 "X-Upload-Content-Length": str(video.stat().st_size)}, method="POST", raw=True)
        req = urllib.request.Request(resp.headers["Location"], data=video.read_bytes(), method="PUT",
                                     headers={"Content-Type": "video/mp4", "User-Agent": ev.UA})
        with urllib.request.urlopen(req, timeout=3600) as r2:
            vid = json.loads(r2.read())["id"]
        print(f"{clave}: subido https://youtu.be/{vid} (público)", flush=True)
        ev.anadir_a_lista(tok, LISTA[0], LISTA[1], vid, "es")
        print("   miniatura:", ev.subir_miniatura(tok, vid, RAIZ / "rosario" / "v2" / "miniaturas" / f"miniatura_{clave}.jpg"))
    if viejo:
        try:
            ev.http(ev.YT + f"videos?id={viejo}", None, h, method="DELETE", raw=True)
            print(f"   borrado el viejo {viejo}")
        except urllib.error.HTTPError as e:
            print(f"   no pude borrar {viejo}: {e.code} {e.read().decode(errors='replace')[:200]}")
    print(f"RESULTADO {clave} {vid}")


if __name__ == "__main__":
    main()
