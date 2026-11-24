"""Sube los cuatro rosarios al canal en español, programados, a la lista «Santo Rosario» y con su miniatura.

Los vídeos y miniaturas vienen de la release `rosario-videos` (descargados a rosario/subir/archivos/).
Antes de subir, mira los últimos vídeos del canal: si ya hay uno con el mismo título, no lo vuelve a subir.
"""
import datetime as dt
import json
import pathlib
import sys
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "proceso"))
import evangelio as ev  # noqa: E402

AQUI = pathlib.Path(__file__).resolve().parent
ARCH = AQUI / "archivos"
PLAN = json.loads((AQUI / "plan.json").read_text(encoding="utf-8"))
DOL = json.loads((RAIZ / "rosario" / "guion_dolorosos.json").read_text(encoding="utf-8"))
TRES = json.loads((RAIZ / "rosario" / "tres" / "guion.json").read_text(encoding="utf-8"))
MUSICA = ["Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg", "Chopin_-_Nocturne-op-55-no-1.ogg",
          "Schubert_-_Piano_Sonata_No._13_in_A_major,_D664_-_II._Andante_(Paul_Pitman).flac",
          "Clair_de_lune_(Claude_Debussy)_Suite_bergamasque.ogg",
          "Frederic_Chopin_-_nocturne_no._2_in_e_flat_major,_op._62.ogg"]
LISTA = ("Santo Rosario", "El Santo Rosario completo y guiado a dos voces, con una lectura breve del Evangelio en "
         "cada misterio: gozosos (lunes y sábado), dolorosos (martes y viernes), gloriosos (miércoles y domingo) y "
         "luminosos (jueves). #SantoRosario #RosarioDeHoy")


def misterios(clave):
    return DOL["misterios"] if clave == "dolorosos" else TRES["rosarios"][clave]["misterios"]


def metadatos(r):
    clave = r["clave"]
    titulo = f"Santo Rosario de hoy · {r['titulo']} ({r['dias']}) · Rosario completo"[:100]
    caps = (AQUI / f"capitulos_{clave}.txt").read_text(encoding="utf-8").strip()
    lect = " · ".join(m["cita"] for m in misterios(clave))
    creditos = "; ".join(c for c in (ev.credito_musica({"musica": m}) for m in MUSICA) if c)
    desc = (f"Reza con nosotros el Santo Rosario: {r['titulo'].lower()}, que se rezan {r['dias_frase']}. "
            "Rosario completo y guiado a dos voces, con una lectura breve del Evangelio en cada misterio, para "
            "rezar en casa, en familia o de camino.\n\n"
            f"Capítulos:\n{caps}\n\n"
            f"📖 Lecturas: {lect} (Biblia de Torres Amat, 1836, con la ortografía actual).\n"
            "📿 Los cuatro rosarios, en la lista «Santo Rosario» del canal.\n"
            "✝️ Cada mañana, el Evangelio del día en un vídeo corto: suscríbete para no perderlo.\n\n"
            "🎨 Imágenes generadas con IA.\n🎙️ Voces generadas con inteligencia artificial.\n"
            f"🎵 Música: {creditos}\n\n"
            f"#SantoRosario #RosarioDeHoy #{r['titulo'].title().replace(' ', '')} #Rosario #Catolico")
    hora = dt.datetime.fromisoformat(r["publicar"]).replace(tzinfo=ev.MADRID)
    estado = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if hora > dt.datetime.now(ev.MADRID) + dt.timedelta(minutes=30):
        estado["publishAt"] = hora.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        estado["privacyStatus"] = "public"
    etiquetas = ["santo rosario", "rosario de hoy", "rosario completo", r["titulo"].lower(), "rosario católico",
                 "rosario en español", "virgen maría", "oración"]
    return {"snippet": {"title": titulo, "description": desc[:4900], "categoryId": "22", "tags": etiquetas,
                        "defaultLanguage": "es", "defaultAudioLanguage": "es"}, "status": estado}


def ya_subidos(tok):
    h = {"Authorization": f"Bearer {tok}"}
    canal = ev.http(ev.YT + "channels?part=contentDetails&mine=true", headers=h)["items"][0]
    subidas = canal["contentDetails"]["relatedPlaylists"]["uploads"]
    d = ev.http(ev.YT + f"playlistItems?part=snippet&maxResults=50&playlistId={subidas}", headers=h)
    return {i["snippet"]["title"]: i["snippet"]["resourceId"]["videoId"] for i in d.get("items", [])}


def main():
    tok = ev.token_youtube("es")
    hechos = ya_subidos(tok)
    salida = []
    for r in PLAN["rosarios"]:
        meta = metadatos(r)
        titulo = meta["snippet"]["title"]
        if titulo in hechos:
            print(f"{r['clave']}: ya está subido (https://youtu.be/{hechos[titulo]}), no lo repito")
            salida.append({"clave": r["clave"], "id": hechos[titulo], "repetido": True})
            continue
        video = ARCH / f"rosario-{r['clave']}.mp4"
        resp, _ = ev.http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                          meta, {"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                                 "X-Upload-Content-Length": str(video.stat().st_size)}, method="POST", raw=True)
        req = urllib.request.Request(resp.headers["Location"], data=video.read_bytes(), method="PUT",
                                     headers={"Content-Type": "video/mp4", "User-Agent": ev.UA})
        with urllib.request.urlopen(req, timeout=3600) as r2:
            vid = json.loads(r2.read())["id"]
        print(f"{r['clave']}: subido https://youtu.be/{vid} · {meta['status'].get('publishAt', meta['status']['privacyStatus'])}",
              flush=True)
        reg = {"clave": r["clave"], "id": vid, "url": f"https://youtu.be/{vid}", "titulo": titulo, **meta["status"]}
        reg["lista"] = ev.anadir_a_lista(tok, LISTA[0], LISTA[1], vid, "es")
        reg["miniatura"] = ev.subir_miniatura(tok, vid, ARCH / f"miniatura_{r['clave']}.jpg")
        salida.append(reg)
        (AQUI / "resultado.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    (AQUI / "resultado.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(salida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
