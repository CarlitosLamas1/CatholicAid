#!/usr/bin/env python3
"""CatholicAid · Avisos por Telegram a Carlos. Solo tres cosas:

  1. 🎬 Vídeo listo: te manda el vídeo para que lo veas, y cuándo y dónde se publicará.
  2. ✅/⛔ Revisión: si se sube a YouTube o no (lo manda proceso/publicar.py).
  3. 📺/🎵 Publicado: cuando ya es público en YouTube y cuando se publica en TikTok.
  4. ❌ Fallo: si falla la creación del vídeo, y cuándo se vuelve a intentar.

Regla de oro: un aviso NUNCA rompe la producción. Todo error se captura y el programa sale con 0.

Uso:
  python3 proceso/avisos.py listo              -> 🎬 vídeo listo (lee salida/*/ y episodios/)
  python3 proceso/avisos.py youtube            -> 📺 si el vídeo de hoy ya es público (una sola vez)
  python3 proceso/avisos.py tiktok <fecha>     -> 🎵 publicado en TikTok
  python3 proceso/avisos.py instagram <fecha>  -> 📸 publicado en Instagram
  python3 proceso/avisos.py fallo [fecha] [url] -> ❌ falló la creación del vídeo y cuándo se reintenta
  python3 proceso/avisos.py prueba             -> mensaje de prueba (falla si Telegram no responde)

Necesita TELEGRAM_BOT_TOKEN (secreto) y TELEGRAM_CHAT_ID (variable del repo).
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
MADRID = ZoneInfo("Europe/Madrid")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
TIKTOK_PERFIL = "https://www.tiktok.com/@catolicaid"
IDIOMAS = {"es": "🇪🇸 español", "en": "🇬🇧 inglés"}  # cada aviso dice de qué canal es


def idioma_de(nombre):
    """«2026-11-08-en» -> («2026-11-08», «en»); «2026-11-08» -> («2026-11-08», «es»)."""
    nombre = str(nombre)
    return (nombre[:-3], "en") if nombre.endswith("-en") else (nombre, "es")


def etiqueta(idioma):
    return IDIOMAS.get(idioma, idioma)


def log(*a):
    print("[avisos]", *a, flush=True)


def e(t):
    return html.escape(str(t), quote=False)


def fecha_txt(f):
    f = dt.date.fromisoformat(str(f))
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month - 1]}"


# ---------- Telegram ----------

def _api(metodo, datos=None, archivo=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("falta TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    if archivo:
        limite = "----" + uuid.uuid4().hex
        cuerpo = b""
        for k, v in (datos or {}).items():
            cuerpo += f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        campo, ruta = archivo
        tipo = "video/mp4" if str(ruta).endswith(".mp4") else "image/jpeg"
        cuerpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{campo}\"; filename=\"{Path(ruta).name}\"\r\n"
                   f"Content-Type: {tipo}\r\n\r\n").encode() + Path(ruta).read_bytes() + f"\r\n--{limite}--\r\n".encode()
        req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(datos or {}).encode())
    with urllib.request.urlopen(req, timeout=180 if archivo else 30) as r:
        res = json.loads(r.read())
    if not res.get("ok"):
        raise RuntimeError(res.get("description", "Telegram no aceptó el mensaje"))
    return res.get("result")


def chat_id():
    c = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not c:
        raise RuntimeError("falta TELEGRAM_CHAT_ID (lanza el workflow «Configurar Telegram»)")
    return c


def copia_ligera(video):
    """Telegram no acepta vídeos de más de 50 MB enviados por un bot: copia a 720p solo para Carlos."""
    import subprocess
    import tempfile
    destino = Path(tempfile.gettempdir()) / "video_telegram.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", "scale=720:-2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", str(destino)], check=True, timeout=600)
    if destino.stat().st_size > 49_000_000:
        raise RuntimeError("ni la copia ligera baja de 50 MB")
    return destino


def enviar(texto, video=None):
    """Envía un mensaje (HTML), con el vídeo si se da. Nunca lanza excepciones: devuelve True/False."""
    try:
        base = {"chat_id": chat_id(), "parse_mode": "HTML"}
        if video and Path(video).exists():
            try:
                if Path(video).stat().st_size > 49_000_000:
                    video = copia_ligera(video)
                _api("sendVideo", {**base, "caption": texto[:1024], "supports_streaming": "true"}, ("video", video))
                log("enviado (con vídeo)")
                return True
            except Exception as ex:
                log(f"el vídeo no se pudo enviar ({ex}); mando solo el texto")
        _api("sendMessage", {**base, "text": texto[:4000], "disable_web_page_preview": "true"})
        log("enviado")
        return True
    except Exception as ex:
        log(f"Telegram no disponible ({ex}); se sigue sin avisar")
        return False


# ---------- Datos ----------

def episodio(fecha):
    ruta = RAIZ / "episodios" / f"{fecha}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def guardar_episodio(fecha, reg):
    (RAIZ / "episodios" / f"{fecha}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def config():
    try:
        return json.loads((RAIZ / "config" / "personajes.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def hora_publicacion(idioma="es"):
    cfg = config()
    return int(cfg.get("hora_publicacion" if idioma == "es" else f"hora_publicacion_{idioma}", cfg.get("hora_publicacion", 7)))


# ---------- Avisos ----------

def aviso_listo():
    """🎬 El vídeo recién generado, para que Carlos lo vea, con cuándo y dónde se publicará."""
    carpetas = sorted(p for p in (RAIZ / "salida").glob("*/") if (p / "video.mp4").exists())
    if not carpetas:
        log("no hay vídeo nuevo; nada que avisar")
        return
    carpeta = carpetas[-1]
    idioma = idioma_de(carpeta.name)[1]
    reg = episodio(carpeta.name) or json.loads((carpeta / "guion.json").read_text(encoding="utf-8"))
    dur = reg.get("duracion_s", 0)
    lineas = [f"🎬 <b>Vídeo listo</b> · {etiqueta(idioma)} · {e(fecha_txt(reg['fecha']))}",
              f"📖 {e(reg.get('cita', ''))} · ⏱️ {int(dur // 60)}:{int(dur % 60):02d}"]
    if reg.get("modo") == "diario" and idioma == "en":
        if config().get("en", {}).get("publicar_programado"):
            lineas.append(f"📅 Se publicará el {e(fecha_txt(reg['fecha']))} a las {hora_publicacion('en')}:00 en "
                          "<b>YouTube (CatolicAid English)</b>, si el revisor automático lo aprueba.")
        else:
            lineas.append("🔒 Estreno: si el revisor lo aprueba, se sube a <b>CatolicAid English</b> en PRIVADO "
                          "(no se publica hasta que tú lo digas).")
        lineas.append(f"🔗 También aquí: https://github.com/CarlitosLamas1/CatholicAid/releases/tag/en-{reg['fecha']}")
    elif reg.get("modo") == "diario":
        lineas.append(f"📅 Se publicará el {e(fecha_txt(reg['fecha']))} a las {hora_publicacion()}:00 en "
                      "<b>YouTube</b>, <b>TikTok</b> e <b>Instagram</b>, si el revisor automático lo aprueba.")
        lineas.append(f"🔗 También aquí: https://github.com/CarlitosLamas1/CatholicAid/releases/tag/tiktok-{reg['fecha']}")
    else:
        lineas.append("🧪 Es una prueba: no se publica.")
    enviar("\n".join(lineas), carpeta / "video.mp4")


def aviso_youtube():
    """📺 Cuando el vídeo de hoy ya es público en YouTube (una sola vez por canal; «telegram_youtube» en el registro)."""
    for idioma in ("es", "en"):
        try:
            aviso_youtube_idioma(idioma)
        except Exception as ex:  # un canal nunca impide el aviso del otro
            log(f"aviso de YouTube ({idioma}) no enviado ({type(ex).__name__}: {ex})")


def aviso_youtube_idioma(idioma):
    hoy = dt.datetime.now(MADRID).date()
    nombre = f"{hoy}" + ("" if idioma == "es" else f"-{idioma}")
    reg = episodio(nombre)
    yt = reg.get("youtube", {})
    if not yt.get("id") or reg.get("telegram_youtube"):
        log(f"nada que avisar de YouTube ({idioma})")
        return
    if idioma == "es":
        refresh = os.environ["YT_REFRESH_TOKEN"].strip()
    else:  # el canal en inglés solo con su propio permiso
        import sys as _s
        _s.path.insert(0, str(RAIZ / "proceso"))
        import youtube_conectar
        refresh = youtube_conectar.guardado(idioma)
        if not refresh:
            log("sin permiso del canal en inglés")
            return
    datos = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(), "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=datos), timeout=30) as r:
        tok = json.loads(r.read())["access_token"]
    req = urllib.request.Request(f"https://www.googleapis.com/youtube/v3/videos?part=status&id={yt['id']}",
                                 headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.loads(r.read()).get("items", [])
    if not items or items[0]["status"].get("privacyStatus") != "public":
        log(f"el vídeo de hoy aún no es público ({idioma})")
        return
    if enviar(f"📺 <b>Publicado en YouTube</b> · {etiqueta(idioma)} · {e(fecha_txt(hoy))}\n📖 {e(reg.get('cita', ''))}"
              f"\n🔗 {e(yt['url'])}"):
        reg["telegram_youtube"] = True
        guardar_episodio(nombre, reg)


def aviso_tiktok(nombre):
    """nombre = AAAA-MM-DD (español, @catolicaid) o AAAA-MM-DD-en (inglés, @catolicaid_en)."""
    fecha, idioma = idioma_de(nombre)
    reg = episodio(nombre)
    priv = reg.get("tiktok", {}).get("privacidad", "")
    nota = " (visible solo para ti hasta que TikTok apruebe la app)" if priv == "SELF_ONLY" else ""
    perfil = TIKTOK_PERFIL if idioma == "es" else TIKTOK_PERFIL + "_" + idioma
    enviar(f"🎵 <b>Publicado en TikTok</b> · {etiqueta(idioma)} · {e(fecha_txt(fecha))}{nota}\n"
           f"📖 {e(reg.get('cita', ''))}\n🔗 {perfil}")


def aviso_instagram(nombre):
    """nombre = AAAA-MM-DD (español) o AAAA-MM-DD-en (inglés)."""
    reg = episodio(nombre)
    enlace = reg.get("instagram", {}).get("enlace") or "https://www.instagram.com/"
    cuenta = " (English)" if nombre.endswith("-en") else ""
    enviar(f"📸 <b>Publicado en Instagram{cuenta}</b> · {e(fecha_txt(nombre[:10]))}\n📖 {e(reg.get('cita', ''))}\n🔗 {e(enlace)}")


REINTENTOS_UTC = [15, 17, 19, 20, 21]  # horas de «Evangelio diario» (.github/workflows/evangelio-diario.yml)
REINTENTOS_EN_UTC = [17, 19, 21, 22]  # «Evangelio diario (inglés)», a y media (.github/workflows/evangelio-ingles.yml)


def aviso_fallo(fecha="", enlace=""):
    ahora = dt.datetime.now(dt.timezone.utc)
    idioma = os.environ.get("IDIOMA", "es").strip() or "es"
    fecha = fecha or str(dt.datetime.now(MADRID).date() + dt.timedelta(days=1))
    horas, minuto = (REINTENTOS_EN_UTC, 30) if idioma == "en" else (REINTENTOS_UTC, 0)
    siguiente = next((h for h in horas if h > ahora.hour), None)
    if siguiente is not None:
        hora = ahora.replace(hour=siguiente, minute=minuto).astimezone(MADRID).strftime("%H:%M")
        cuando = f"🔁 Se vuelve a intentar solo a las {hora}."
    else:
        cuando = "⚠️ Hoy ya no quedan intentos automáticos: el gestor lo revisará."
    motivo = ""
    reg = episodio(f"{fecha}-en") if idioma == "en" else {}
    if reg.get("cupo_agotado"):
        motivo = "\n⏳ Motivo: no queda cupo gratuito de Gemini hoy (el español va primero)."
    enviar(f"❌ <b>No se ha podido crear el vídeo</b> · {etiqueta(idioma)} · {e(fecha_txt(fecha))}.{motivo}\n{cuando}"
           + (f"\n🔗 {e(enlace)}" if enlace else ""))


def main():
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if orden == "prueba":  # el único que sí falla si Telegram no responde (para «Configurar Telegram»)
            try:
                _api("deleteMyCommands")  # sin menú de órdenes: el bot solo avisa
            except Exception:
                pass
            sys.exit(0 if enviar("👋 <b>¡Hola, Carlos!</b> Desde ahora solo te escribiré para tres cosas:\n"
                                 "🎬 el vídeo cuando esté listo, con cuándo y dónde se publicará,\n"
                                 "✅ si el revisor lo aprueba (o no),\n"
                                 "📺🎵 y cuando ya esté publicado en YouTube y en TikTok.") else 1)
        elif orden == "listo":
            aviso_listo()
        elif orden == "youtube":
            aviso_youtube()
        elif orden == "fallo":
            aviso_fallo(*sys.argv[2:4])
        elif orden == "tiktok":
            aviso_tiktok(sys.argv[2])
        elif orden == "instagram":
            aviso_instagram(sys.argv[2])
        else:
            print(__doc__)
    except SystemExit:
        raise
    except Exception as ex:  # nunca bloquear
        log(f"aviso no enviado ({type(ex).__name__}: {ex})")


if __name__ == "__main__":
    main()
