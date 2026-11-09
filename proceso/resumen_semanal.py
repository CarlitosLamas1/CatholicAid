#!/usr/bin/env python3
"""CatholicAid · Resumen semanal: los Evangelios de la semana en un solo vídeo horizontal (no Short).

Cada domingo por la tarde junta los vídeos diarios (lunes a domingo) ya aprobados por el revisor y publicados, los
pone en horizontal 1920×1080 (el vídeo vertical en el centro y, detrás, el mismo vídeo ampliado, desenfocado y
oscurecido), quita el cierre «Síguenos…» de cada día salvo del último y lo sube a YouTube con capítulos (uno por
día), subtítulos y la lista «Evangelio de la semana». Programado a resumen_semanal.hora (Madrid) del domingo.
No vuelve a revisar nada: solo usa días con el OK del revisor. No avisa por Telegram (decisión de Carlos).

Los vídeos salen de la release del día (si sigue) o de la copia de 30 días del run que los hizo.
Registro: resumenes/AAAA-MM-DD.json (domingo; -en para el inglés).
Uso: python3 proceso/resumen_semanal.py [--domingo AAAA-MM-DD] [--idioma es|en|todos] [--no-subir]
"""
import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

RAIZ = ev.RAIZ
DIAS_EN = ev.DAYS


def log(*a):
    print(*a, flush=True)


def cfg():
    return {"activo": True, "hora": 20, "minimo_dias": 5, **ev.CFG.get("resumen_semanal", {})}


def leer(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except Exception:
        return {}


def sh(*args, check=True):
    return subprocess.run(list(map(str, args)), check=check, capture_output=True, text=True)


def ffprobe_duracion(ruta):
    r = sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta)
    return float(r.stdout.strip())


def buscar_en(carpeta, nombre, generado):
    """video.mp4 de salida/<nombre>/ dentro de una copia descargada, si es la misma versión (mismo «generado»)."""
    for g in Path(carpeta).rglob("guion.json"):
        if g.parent.name != nombre:
            continue
        if generado and leer(g).get("generado") != generado:
            continue
        v = g.parent / "video.mp4"
        if v.exists():
            return v
    return None


def conseguir_video(nombre, reg, idioma, tmp):
    """Vídeo publicado de ese día: release, run anotado en el registro o los runs recientes del workflow diario."""
    fecha = reg["fecha"]
    destino = tmp / nombre
    destino.mkdir(parents=True, exist_ok=True)
    release = f"tiktok-{fecha}" if idioma == "es" else f"en-{fecha}"
    if reg.get("youtube") and sh("gh", "release", "download", release, "-D", destino, "-p", "video.mp4",
                                 check=False).returncode == 0 and (destino / "video.mp4").exists():
        # la release se rehace con cada versión: solo vale si es la del registro (lo garantiza el flujo de publicación)
        return destino / "video.mp4"
    runs = [reg["run"]] if reg.get("run") else []
    flujo = "evangelio-diario.yml" if idioma == "es" else "evangelio-ingles.yml"
    r = sh("gh", "run", "list", "-w", flujo, "-s", "success", "-L", "60", "--json", "databaseId,createdAt", check=False)
    dia = dt.date.fromisoformat(fecha)
    for x in json.loads(r.stdout or "[]"):
        creado = dt.date.fromisoformat(x["createdAt"][:10])
        if dia - dt.timedelta(days=3) <= creado <= dia and str(x["databaseId"]) not in runs:
            runs.append(str(x["databaseId"]))
    for run in runs:
        carpeta = tmp / f"run-{run}"
        if not carpeta.exists():
            sh("gh", "run", "download", run, "-D", carpeta, check=False)
        v = buscar_en(carpeta, nombre, reg.get("generado"))
        if v:
            log(f"   {nombre}: copia del run {run}")
            return v
    return None


def horizontal(video, destino, recortar):
    """Vertical 1080×1920 -> horizontal 1920×1080 con fondo desenfocado. recortar: segundos a quitar del final."""
    dur = ffprobe_duracion(video) - recortar
    filtro = ("[0:v]split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
              "gblur=sigma=40,eq=brightness=-0.22:saturation=0.8[fondo];[b]scale=-2:1080[delante];"
              "[fondo][delante]overlay=(W-w)/2:0,fps=30,format=yuv420p[v];"
              f"[0:a]aresample=48000,aformat=channel_layouts=stereo,afade=t=out:st={max(0.0, dur - 0.6):.2f}:d=0.6[a]")
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", video, "-t", f"{dur:.2f}", "-filter_complex", filtro,
       "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", 30,
       "-c:a", "aac", "-b:a", "192k", "-ar", 48000, destino)
    return ffprobe_duracion(destino)


def marca_capitulo(s):
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def desplazar_srt(srt, desde):
    def mover(m):
        h, mi, se, ms = map(int, m.groups())
        t = h * 3600000 + mi * 60000 + se * 1000 + ms + int(round(desde * 1000))
        return f"{t // 3600000:02d}:{t // 60000 % 60:02d}:{t // 1000 % 60:02d},{t % 1000:03d}"
    return re.sub(r"(\d\d):(\d\d):(\d\d),(\d\d\d)", mover, srt)


def unir_srt(partes):
    bloques = []
    for srt, desde in partes:
        for b in desplazar_srt(srt, desde).strip().split("\n\n"):
            lineas = b.split("\n")
            if len(lineas) >= 3:
                bloques.append("\n".join(lineas[1:]))
    return "".join(f"{n}\n{b}\n\n" for n, b in enumerate(bloques, 1))


def textos(idioma, lunes, domingo):
    if idioma == "en":
        if lunes.month == domingo.month:
            rango = f"{ev.MONTHS[lunes.month - 1]} {lunes.day}–{domingo.day}, {domingo.year}"
        else:
            rango = f"{ev.MONTHS[lunes.month - 1]} {lunes.day} – {ev.MONTHS[domingo.month - 1]} {domingo.day}, {domingo.year}"
        return {"titulo": f"Gospel of the week · {rango} | The daily Gospels read with several voices",
                "intro": f"This week’s Gospels ({rango}), one after another, read with several voices. "
                         "To listen calmly, pray or meditate.",
                "capitulos": "📖 Chapters:", "cortos": "🎬 Every day, the Gospel in a short video:",
                "lista": ("Gospel of the week", "Each week’s daily Gospels in one video, read with several voices. #GospelOfTheDay"),
                "miniatura": "Gospel of the week",
                "pie": "📖 Text: World English Bible (Catholic). Liturgical calendar: Vatican News.\n"
                       "🎨 Images: scenes generated with AI and classic paintings (public domain).\n"
                       "🎙️ Voices generated with artificial intelligence.",
                "musica": "🎵 Music:",
                "hashtags": "#GospelOfTheDay #DailyGospel #Gospel #Catholic #WordOfGod #Bible",
                "etiquetas": ["gospel of the week", "gospel of the day", "daily gospel", "catholic", "bible"]}
    if lunes.month == domingo.month:
        rango = f"del {lunes.day} al {domingo.day} de {ev.MESES[domingo.month - 1]} de {domingo.year}"
    else:
        rango = (f"del {lunes.day} de {ev.MESES[lunes.month - 1]} al {domingo.day} de {ev.MESES[domingo.month - 1]} "
                 f"de {domingo.year}")
    return {"titulo": f"Evangelio de la semana · {rango} | Las lecturas del día con varias voces",
            "intro": f"Los Evangelios de esta semana ({rango}), uno tras otro y leídos con varias voces. "
                     "Para escucharlos con calma, rezar o meditar.",
            "capitulos": "📖 Capítulos:", "cortos": "🎬 Cada día, el Evangelio en un vídeo corto:",
            "lista": ("Evangelio de la semana", "Los Evangelios del día de cada semana en un solo vídeo, leídos con "
                                                "varias voces. #EvangelioDelDia"),
            "miniatura": "El Evangelio de la semana",
            "pie": "📖 Texto: Torres Amat (1836), versión revisada por CatholicAid. Calendario litúrgico: Vatican News.\n"
                   "🎨 Imágenes: escenas generadas con IA y pinturas clásicas (dominio público).\n"
                   "🎙️ Voces generadas con inteligencia artificial.",
            "musica": "🎵 Música:",
            "hashtags": "#EvangelioDelDia #Evangelio #PalabraDeDios #Catolico #Biblia",
            "etiquetas": ["evangelio de la semana", "evangelio del día", "evangelio", "católico", "palabra de Dios"]}


def nombre_dia(fecha, idioma):
    if idioma == "en":
        return f"{DIAS_EN[fecha.weekday()]} {fecha.day}"
    return f"{ev.DIAS[fecha.weekday()].capitalize()} {fecha.day}"


def resumen(domingo, idioma, subir=True):
    suf = ev.SUFIJO[idioma]
    ruta_reg = RAIZ / "resumenes" / f"{domingo}{suf}.json"
    if leer(ruta_reg).get("youtube", {}).get("id"):
        log(f"Resumen {domingo}{suf}: ya está subido.")
        return
    ev.aplicar_idioma(idioma)
    c = cfg()
    lunes = domingo - dt.timedelta(days=6)
    tmp = Path(tempfile.mkdtemp())
    dias = []
    for i in range(7):
        f = lunes + dt.timedelta(days=i)
        nombre = f"{f}{suf}"
        reg = leer(RAIZ / "episodios" / f"{nombre}.json")
        rev = leer(RAIZ / "revisiones" / f"{nombre}.json")
        if not (reg.get("modo") == "diario" and reg.get("youtube", {}).get("id") and rev.get("ok")
                and not reg.get("no_publicar") and not reg.get("musica_bloqueada", {}).get("video") == reg["youtube"]["id"]):
            log(f"   {nombre}: sin vídeo aprobado y publicado; no entra")
            continue
        video = conseguir_video(nombre, reg, idioma, tmp)
        if not video:
            log(f"   {nombre}: no encuentro el vídeo (ni release ni copia); no entra")
            continue
        dias.append((f, reg, video))
    if len(dias) < int(c["minimo_dias"]):
        log(f"Resumen {domingo}{suf}: solo {len(dias)} días disponibles (mínimo {c['minimo_dias']}); no se hace.")
        ruta_reg.parent.mkdir(exist_ok=True)
        ruta_reg.write_text(json.dumps({"domingo": str(domingo), "estado": "omitido", "dias": len(dias)},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.rmtree(tmp, ignore_errors=True)
        return
    cierre = float(ev.CFG.get("cierre_segundos", 0) or 0)
    salida = RAIZ / "salida" / f"semana-{domingo}{suf}"
    shutil.rmtree(salida, ignore_errors=True)
    salida.mkdir(parents=True)
    t, capitulos, partes_srt, lista = 0.0, [], [], []
    for n, (f, reg, video) in enumerate(dias):
        trozo = salida / f"dia{n}.mp4"
        dur = horizontal(video, trozo, 0.0 if n == len(dias) - 1 else cierre)
        frase = (reg.get("frase_clave") or "").strip(" .,;:")
        capitulos.append(f"{marca_capitulo(t)} {nombre_dia(f, idioma)} · {reg['cita']}" + (f" · “{frase}”" if frase else ""))
        partes_srt.append((ev.srt_del_registro(reg), t))
        lista.append(f"{nombre_dia(f, idioma)}: {reg['youtube']['url']}")
        log(f"   {nombre_dia(f, idioma)} · {reg['cita']} · {dur:.1f} s desde {t:.1f} s")
        t += dur
    (salida / "partes.txt").write_text("".join(f"file 'dia{n}.mp4'\n" for n in range(len(dias))))
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", 0, "-i", salida / "partes.txt", "-c", "copy",
       "-movflags", "+faststart", salida / "video.mp4")
    video = salida / "video.mp4"
    log(f"Vídeo de la semana: {t / 60:.1f} min · {video.stat().st_size / 1e6:.0f} MB")
    srt = unir_srt(partes_srt)
    (salida / "subtitulos.srt").write_text(srt, encoding="utf-8")

    tx = textos(idioma, lunes, domingo)
    creditos = []
    for _, reg, _ in dias:
        cr = ev.credito_musica({"musica": reg.get("musica", "")})
        if cr and cr not in creditos:
            creditos.append(cr)
    descripcion = (f"{tx['intro']}\n\n{tx['capitulos']}\n" + "\n".join(capitulos) + "\n\n"
                   f"{tx['cortos']}\n" + "\n".join(lista) + "\n\n" + tx["pie"] + "\n"
                   + (f"{tx['musica']} " + " · ".join(creditos) + "\n" if creditos else "") + "\n" + tx["hashtags"])
    estado = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    hora = dt.datetime.combine(domingo, dt.time(int(c["hora"])), ev.MADRID)
    if hora > dt.datetime.now(ev.MADRID) + dt.timedelta(minutes=30):
        estado["publishAt"] = hora.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        estado["privacyStatus"] = "public"
    meta = {"snippet": {"title": tx["titulo"][:100], "description": descripcion[:4900], "categoryId": "22",
                        "tags": tx["etiquetas"], "defaultLanguage": idioma, "defaultAudioLanguage": idioma},
            "status": estado}
    (salida / "metadatos.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    mini = None
    try:  # miniatura: la primera imagen pintada del domingo (o del último día) con «El Evangelio de la semana»
        img = next((p for f, _, _ in reversed(dias) for p in sorted((RAIZ / "biblioteca" / "dias").glob(f"{f}_e*.jpg"))), None)
        if img:
            mini = ev.miniatura(img, tx["miniatura"], salida / "miniatura.jpg")
    except Exception as e:
        log(f"Miniatura no creada ({e})")
    registro = {"domingo": str(domingo), "idioma": idioma, "dias": [str(f) for f, _, _ in dias],
                "duracion_s": round(t, 1), "titulo": meta["snippet"]["title"], "capitulos": capitulos}
    if not subir:
        log("No se sube (--no-subir). Metadatos en " + str(salida / "metadatos.json"))
        log(descripcion)
        return
    tok = ev.token_youtube(idioma)
    r, _ = ev.http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                   meta, {"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                          "X-Upload-Content-Length": str(video.stat().st_size)}, method="POST", raw=True)
    import urllib.request
    req = urllib.request.Request(r.headers["Location"], data=video.read_bytes(), method="PUT",
                                 headers={"Content-Type": "video/mp4", "User-Agent": ev.UA})
    with urllib.request.urlopen(req, timeout=1800) as r2:
        vid = json.loads(r2.read())["id"]
    registro["youtube"] = {"id": vid, "url": f"https://youtu.be/{vid}", **estado}
    ruta_reg.parent.mkdir(exist_ok=True)
    ruta_reg.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Subido: https://youtu.be/{vid} ({estado['privacyStatus']}{', ' + estado['publishAt'] if 'publishAt' in estado else ''})")
    yt = registro["youtube"]
    try:
        yt["lista"] = ev.anadir_a_lista(tok, tx["lista"][0], tx["lista"][1], vid, idioma)
        yt["miniatura"] = ev.subir_miniatura(tok, vid, mini) if mini else "sin miniatura"
        yt["subtitulos"] = ev.subir_subtitulos(tok, vid, {}, idioma, srt=srt)
    except Exception as e:
        log(f"Extras no completados ({e})")
    ruta_reg.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domingo", default="")
    ap.add_argument("--idioma", default="todos")
    ap.add_argument("--no-subir", action="store_true")
    a = ap.parse_args()
    if not cfg().get("activo"):
        log("Resumen semanal desactivado (resumen_semanal.activo en config).")
        return
    hoy = dt.datetime.now(ev.MADRID).date()
    domingo = dt.date.fromisoformat(a.domingo) if a.domingo.strip() else hoy - dt.timedelta(days=(hoy.weekday() + 1) % 7)
    idiomas = ["es", "en"] if a.idioma in ("", "todos") else [a.idioma]
    for idioma in idiomas:
        if idioma != "es" and not ev.CFG.get(idioma, {}).get("activo"):
            continue
        log(f"== Evangelio de la semana · domingo {domingo} · {idioma} ==")
        try:
            resumen(domingo, idioma, not a.no_subir)
        except Exception as e:  # un idioma nunca impide el otro
            log(f"Resumen {idioma} falló: {type(e).__name__}: {e}")
            if len(idiomas) == 1:
                raise


if __name__ == "__main__":
    main()
