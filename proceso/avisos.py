#!/usr/bin/env python3
"""CatholicAid · Avisos por Telegram a Carlos.

Regla de oro: un aviso NUNCA rompe la producción. Todo error se captura y el programa sale con 0.

Uso (en los workflows):
  python3 proceso/avisos.py prueba                 -> mensaje de prueba
  python3 proceso/avisos.py listo                  -> ✅ vídeo listo (lee salida/*/ y episodios/)
  python3 proceso/avisos.py tiktok <fecha>         -> 🎵 publicado en TikTok
  python3 proceso/avisos.py manana                 -> 📺 YouTube de hoy + 📅 próximos 3 días + 🔔 pendientes
  python3 proceso/avisos.py informe <ruta.md>      -> 📊 informe semanal
  python3 proceso/avisos.py fallo                  -> ❌ fallo del run actual, con la causa y el reintento
  python3 proceso/avisos.py accion "<texto>"       -> 🔔 algo que requiere a Carlos

Necesita TELEGRAM_BOT_TOKEN (secreto) y TELEGRAM_CHAT_ID (variable del repo).
"""
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
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
STUDIO = "https://studio.youtube.com/channel/UCeQ2e1rojxsa9UyrHWcVEVA/videos/short"


def log(*a):
    print("[avisos]", *a, flush=True)


def e(t):
    return html.escape(str(t), quote=False)


def fecha_txt(f):
    f = dt.date.fromisoformat(str(f))
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month - 1]}"


# ---------- Telegram ----------

def _api(metodo, datos=None, archivo=None, espera=0):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("falta TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    if archivo:
        limite = "----" + uuid.uuid4().hex
        cuerpo = b""
        for k, v in (datos or {}).items():
            cuerpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
        campo, ruta = archivo
        cuerpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{campo}\"; filename=\"{Path(ruta).name}\"\r\n"
                   f"Content-Type: {'video/mp4' if str(ruta).endswith('.mp4') else 'image/jpeg'}\r\n\r\n").encode() + Path(ruta).read_bytes() + f"\r\n--{limite}--\r\n".encode()
        req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(datos or {}).encode())
    with urllib.request.urlopen(req, timeout=180 if archivo else 30 + espera) as r:
        res = json.loads(r.read())
    if not res.get("ok"):
        raise RuntimeError(res.get("description", "Telegram no aceptó el mensaje"))
    return res.get("result")


def chat_id():
    c = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not c:
        raise RuntimeError("falta TELEGRAM_CHAT_ID (lanza el workflow «Configurar Telegram»)")
    return c


def teclado(botones):
    """botones: filas de (texto, dato) -> reply_markup de Telegram."""
    return json.dumps({"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in fila] for fila in botones]})


def enviar(texto, foto=None, botones=None):
    """Envía un mensaje (HTML). Nunca lanza excepciones: devuelve True/False."""
    try:
        base = {"chat_id": chat_id(), "parse_mode": "HTML"}
        if botones:
            base["reply_markup"] = teclado(botones)
        if foto and Path(foto).exists() and len(texto) <= 1024:
            try:
                _api("sendPhoto", {**base, "caption": texto}, ("photo", foto))
                log("enviado (con imagen)")
                return True
            except Exception as ex:
                log(f"la imagen no se pudo enviar ({ex}); mando solo el texto")
        trozos = trocear(texto, 4000)
        for i, trozo in enumerate(trozos):
            datos = {**base, "text": trozo, "disable_web_page_preview": "true"}
            if i < len(trozos) - 1:
                datos.pop("reply_markup", None)
            _api("sendMessage", datos)
        log("enviado")
        return True
    except Exception as ex:
        log(f"Telegram no disponible ({ex}); se sigue sin avisar")
        return False


def trocear(texto, maximo):
    trozos, actual = [], ""
    for linea in texto.split("\n"):
        while len(linea) > maximo:
            trozos.append(linea[:maximo])
            linea = linea[maximo:]
        if len(actual) + len(linea) + 1 > maximo:
            trozos.append(actual)
            actual = ""
        actual += linea + "\n"
    if actual.strip():
        trozos.append(actual)
    return trozos


# ---------- Datos ----------

def episodio(fecha):
    ruta = RAIZ / "episodios" / f"{fecha}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def config():
    return json.loads((RAIZ / "config" / "personajes.json").read_text(encoding="utf-8"))


def nombres_voces(reg):
    cfg = config()
    pj = cfg.get("personajes", {})
    libro = reg.get("cita", "").split()[0] if reg.get("cita") else ""
    vistos = []
    for f in reg.get("fragmentos", []):
        p = f.get("personaje")
        if p and p not in vistos:
            vistos.append(p)
    nombres = []
    for p in vistos:
        if p == "narrador":
            nombres.append(f"Narrador (san {libro})" if libro in cfg.get("narradores", {}) else "Narrador")
        else:
            nombres.append(pj.get(p, {}).get("nombre", p.capitalize()))
    return ", ".join(nombres)


def fotograma(video, segundo, destino):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{segundo:.1f}", "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "3", str(destino)], check=True, timeout=60)
    return destino


def token_youtube():
    datos = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(),
        "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=datos), timeout=30) as r:
        return json.loads(r.read())["access_token"]


def estado_youtube(vid, tok):
    req = urllib.request.Request(f"https://www.googleapis.com/youtube/v3/videos?part=status&id={vid}",
                                 headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.loads(r.read()).get("items", [])
    return items[0]["status"] if items else None


# ---------- Mensajes ----------

def aviso_listo():
    carpetas = sorted(p for p in (RAIZ / "salida").glob("*/") if (p / "video.mp4").exists())
    if not carpetas:
        log("no hay vídeo nuevo; nada que avisar")
        return
    carpeta = carpetas[-1]
    reg = episodio(carpeta.name)
    if not reg:
        reg = json.loads((carpeta / "guion.json").read_text(encoding="utf-8"))
    yt = reg.get("youtube", {})
    dur = reg.get("duracion_s", 0)
    lineas = [f"✅ <b>Vídeo listo</b> · {e(fecha_txt(reg['fecha']))}",
              f"📖 {e(reg.get('cita', ''))}",
              f"⏱️ {int(dur // 60)}:{int(dur % 60):02d} · 🎙️ {e(nombres_voces(reg))}"]
    if reg.get("frase_clave"):
        lineas.append(f"💬 «{e(reg['frase_clave'])}»")
    if yt.get("url"):
        cuando = "se publica a las 07:00" if yt.get("publishAt") else f"queda {yt.get('privacyStatus', 'privado')}"
        lineas.append(f"▶️ {e(yt['url'])} ({cuando})")
    else:
        lineas.append("▶️ No se ha subido a YouTube (prueba sin subir)")
    if reg.get("modo") == "prueba":
        lineas.append("🧪 Es una prueba: no se programa ni va a TikTok.")
    ia = [i for i in reg.get("imagenes", []) if i.startswith("dias/")]
    if config().get("imagenes_ia", {}).get("activo") and not ia:
        lineas.append("")
        lineas.append("🔔 <b>Hoy no se ha pintado ninguna imagen nueva</b>: puede que se haya acabado el saldo "
                      "de imágenes. Mira la API de Gemini (prepago) y recarga si hace falta.")
    for a in reg.get("avisos", []):
        lineas.append(f"🔔 {e(a)}")
    foto = None
    try:
        foto = fotograma(carpeta / "video.mp4", min(max(dur * 0.35, 3), max(dur - 1, 0)),
                         Path(tempfile.gettempdir()) / "fotograma.jpg")
    except Exception as ex:
        log(f"sin fotograma ({ex})")
    botones = None
    hoy = dt.datetime.now(MADRID).date()
    if reg.get("modo") == "diario" and yt.get("id") and dt.date.fromisoformat(reg["fecha"]) > hoy:
        f = reg["fecha"]
        botones = [[("👍 Publicar", f"ok|{f}"), ("⛔ No publicar", f"no|{f}")],
                   [("🎨 Otras imágenes", f"img|{f}"), ("🎙️ Otra lectura", f"voz|{f}")],
                   [("✏️ Retocar (frase, reflexión, música, estilo)", f"ret|{f}")]]
    enviar("\n".join(lineas), foto, botones)


def aviso_video(fecha, ruta):
    """📲 El vídeo del día en el móvil de Carlos, listo para reenviar (una sola vez por día)."""
    reg = episodio(fecha)
    if reg.get("telegram_video"):
        log("el vídeo de hoy ya se mandó")
        return
    ruta = Path(ruta)
    texto = f"📖 <b>Evangelio del día</b> · {e(fecha_txt(fecha))}\n{e(reg.get('cita', ''))} 🙏"
    if reg.get("reflexion"):
        texto += f"\n\n🕊️ {e(reg['reflexion'])}"
    try:
        if ruta.stat().st_size > 49_000_000:
            raise RuntimeError("pesa más de 50 MB (límite de Telegram)")
        _api("sendVideo", {"chat_id": chat_id(), "caption": texto, "parse_mode": "HTML",
                           "supports_streaming": "true"}, ("video", ruta))
        log("vídeo enviado")
    except Exception as ex:
        log(f"no pude mandar el vídeo ({ex})")
        enviar(texto + f"\n\n(No he podido mandarte el vídeo: {e(ex)})")
    if reg:
        reg["telegram_video"] = True
        (RAIZ / "episodios" / f"{fecha}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def aviso_tiktok(fecha):
    reg = episodio(fecha)
    tk = reg.get("tiktok", {})
    priv = tk.get("privacidad", "")
    visible = {"SELF_ONLY": "solo tú (Sandbox, hasta que TikTok apruebe la app)",
               "PUBLIC_TO_EVERYONE": "público"}.get(priv, priv or "?")
    enviar(f"🎵 <b>Publicado en TikTok</b> · {e(fecha_txt(fecha))}\n📖 {e(reg.get('cita', ''))}\n"
           f"👁️ Visible para: {e(visible)}\n🔗 {TIKTOK_PERFIL}")


def aviso_manana():
    hoy = dt.datetime.now(MADRID).date()
    # 📺 YouTube de hoy
    reg = episodio(hoy)
    yt = reg.get("youtube", {})
    acciones = []
    if reg.get("no_publicar") or str(hoy) <= pausa_hasta():
        pass  # Carlos pidió no publicarlo
    elif yt.get("id"):
        try:
            st = estado_youtube(yt["id"], token_youtube())
            if st and st.get("privacyStatus") == "public":
                enviar(f"📺 <b>Publicado en YouTube</b> · {e(fecha_txt(hoy))}\n📖 {e(reg.get('cita', ''))}\n"
                       f"🔗 {e(yt['url'])}")
            elif st:
                acciones.append(f"El vídeo de hoy sigue <b>privado</b> en YouTube (falta la auditoría). "
                                f"Publícalo a mano en Studio: {STUDIO}")
            else:
                acciones.append(f"El vídeo de hoy ({e(yt['url'])}) no aparece en YouTube.")
        except urllib.error.HTTPError as ex:
            if ex.code in (400, 401):
                acciones.append("El permiso de YouTube ha caducado: díselo al gestor para renovarlo.")
            else:
                log(f"no pude consultar YouTube ({ex})")
        except Exception as ex:
            log(f"no pude consultar YouTube ({ex})")
    else:
        acciones.append(f"No hay vídeo de hoy ({e(fecha_txt(hoy))}) en YouTube.")

    enviar(proximos_dias(hoy))

    # 🔔 Pendientes (los lunes se recuerdan las respuestas que se esperan)
    if hoy.weekday() == 0:
        for p in config().get("avisos", {}).get("pendientes", []):
            acciones.append(e(p))
    for a in acciones:
        enviar(f"🔔 {a}")


def pausa_hasta():
    try:
        return json.loads((RAIZ / "estado" / "telegram.json").read_text(encoding="utf-8")).get("pausa_hasta", "")
    except Exception:
        return ""


def proximos_dias(hoy):
    citas = {}
    try:
        citas = json.loads((RAIZ / "biblia" / "citas.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    lineas = ["📅 <b>Próximos días</b>"]
    for i in range(1, 4):
        f = hoy + dt.timedelta(days=i)
        r = episodio(f)
        cita = r.get("cita") or citas.get(str(f), "")
        cita = f" · {e(cita)}" if cita else ""
        if str(f) <= pausa_hasta():
            marca = "⏸️ en pausa"
        elif r.get("no_publicar"):
            marca = "⛔ no se publica"
        elif r.get("youtube") and r.get("modo") == "diario":
            marca = "✅ preparado"
        elif i == 1:
            marca = "⏳ falta · se genera esta tarde"
        else:
            marca = "⏳ falta · se genera la víspera"
        lineas.append(f"• {e(fecha_txt(f))}{cita}: {marca}")
    return "\n".join(lineas)


def aviso_informe(ruta):
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    # Markdown sencillo -> HTML de Telegram
    t = e(texto)
    t = re.sub(r"^#+\s*(.+)$", r"<b>\1</b>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"^\s*[-*]\s+", "• ", t, flags=re.M)
    enviar(f"📊 <b>Informe semanal del gestor</b> ({e(ruta.stem)})\n\n{t}")


# Causas conocidas: (patrón en el log, frase para Carlos, requiere acción de Carlos)
CAUSAS = [
    (r"no publico con un reparto dudoso", "Gemini está saturado y no ha podido repartir las voces; "
                                          "no se publica para no equivocarse con quién habla.", False),
    (r"invalid_grant", "El permiso de YouTube ha caducado o se ha revocado.", True),
    (r"quotaExceeded|uploadLimitExceeded|dailyLimitExceeded", "YouTube no deja subir más hoy (límite de cuota).", False),
    (r"TikTok no da acceso", "El permiso de TikTok ha caducado: hay que reconectarlo una vez.", True),
    (r"TikTok rechazó|spam_risk|unaudited_client", "TikTok ha rechazado la publicación.", False),
    (r"RESOURCE_EXHAUSTED|\b429\b", "Gemini ha agotado la cuota gratuita (texto o voces) por ahora.", False),
    (r"API_KEY_INVALID|API key not valid|PERMISSION_DENIED", "La clave de Gemini no es válida o ha caducado.", True),
    (r"vaticannews", "No se pudo leer la cita del día en Vatican News.", False),
    (r"falta (el secreto )?TELEGRAM", "Falta configurar Telegram.", True),
    (r"CalledProcessError.*ffmpeg|ffmpeg.*returned non-zero", "Falló el montaje del vídeo (FFmpeg).", False),
    (r"timed out|TimeoutError|timeout-minutes|has exceeded the maximum execution time", "Un servicio tardó demasiado en responder.", False),
    (r"\b50[0234]\b|Service Unavailable|Internal Server Error", "Un servicio externo dio un error temporal.", False),
    (r"rejected.*fetch first|failed to push", "No se pudo guardar el registro en GitHub (choque al guardar).", False),
]

# Reintentos por workflow (horas UTC). Si no queda ninguno hoy, se dice.
REINTENTOS = {
    "Evangelio diario": ([15, 17, 19, 20, 21], "Se vuelve a intentar a las {h} (hora de España)"),
    "Publicar en TikTok": ([6, 8], "Se vuelve a intentar a las {h} (hora de España)"),
}


def log_del_fallo():
    """Devuelve el final del log del job que ha fallado en este run (vía la API de GitHub con gh)."""
    run = os.environ.get("FALLO_RUN_ID") or os.environ.get("GITHUB_RUN_ID")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not run or not repo:
        return ""
    jobs = json.loads(subprocess.run(["gh", "api", f"repos/{repo}/actions/runs/{run}/jobs"],
                                     capture_output=True, text=True, timeout=60, check=True).stdout)["jobs"]
    malos = [j for j in jobs if j.get("conclusion") in ("failure", "timed_out", "cancelled")]
    if not malos:
        return ""
    lineas = [re.sub(r"^\S+Z\s", "", l) for l in descargar_log(repo, malos[0]["id"]).splitlines()]
    lineas = [re.sub(r"\x1b\[[0-9;]*m", "", l) for l in lineas if "\x1b[36;1m" not in l]  # sin el código del paso
    return "\n".join(lineas[-80:])


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def descargar_log(repo, job):
    """La API responde con una redirección a un enlace temporal; se sigue sin enviar el token."""
    token = os.environ.get("GH_TOKEN", "").strip()
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/jobs/{job}/logs",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.build_opener(_SinRedireccion).open(req, timeout=60) as r:
            return r.read().decode(errors="replace")
    except urllib.error.HTTPError as ex:
        if ex.code not in (301, 302, 303, 307, 308):
            raise
        destino = ex.headers["Location"]
    with urllib.request.urlopen(destino, timeout=60) as r:
        return r.read().decode(errors="replace")


def causa(texto):
    # Solo se mira lo anterior al primer «Process completed with exit code» (el paso que falló)
    corte = texto.find("##[error]Process completed")
    texto = texto[:corte] if corte > 0 else texto
    lineas = [l.strip() for l in texto.splitlines() if l.strip() and not l.startswith("##[")]
    final = "\n".join(lineas[-40:])
    for patron, frase, accion in CAUSAS:
        if re.search(patron, final, re.I):
            return frase, accion
    errores = [l for l in lineas[-15:] if re.search(r"Error|SystemExit|falló|Exception|No encuentro|No hay", l)]
    ultima = (errores or lineas[-1:] or [""])[-1]
    if ultima:
        return ultima[:200], False
    return "No he podido identificar la causa (mira el enlace).", False


def proximo_reintento(nombre, ahora=None):
    horas, plantilla = REINTENTOS.get(nombre, ([], ""))
    if not horas:  # los reintentos son tiradas programadas: ocurren aunque el fallo fuera de un lanzamiento manual
        return ""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    for h in sorted(horas):
        if h > ahora.hour:
            local = ahora.replace(hour=h, minute=0).astimezone(MADRID)
            return plantilla.format(h=local.strftime("%H:%M")) + "."
    return "No quedan reintentos hoy: hace falta revisarlo."


def aviso_fallo():
    nombre = os.environ.get("FALLO_WORKFLOW") or os.environ.get("GITHUB_WORKFLOW", "Un proceso")
    run = os.environ.get("FALLO_RUN_ID") or os.environ.get("GITHUB_RUN_ID", "")
    url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}" \
          f"/actions/runs/{run}"
    try:
        texto = log_del_fallo()
    except Exception as ex:
        log(f"no pude leer el log ({ex})")
        texto = ""
    frase, accion = causa(texto)
    reintento = proximo_reintento(nombre)
    lineas = [f"❌ <b>Falló «{e(nombre)}»</b>", f"Causa: {e(frase)}"]
    if reintento:
        lineas.append(f"🔁 {e(reintento)}")
    lineas.append(f"🔗 {e(url)}")
    enviar("\n".join(lineas))
    if accion:
        enviar(f"🔔 <b>Necesito tu ayuda</b>: {e(frase)} Díselo al gestor y te guiará en un solo paso.")


def main():
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if orden == "comandos":  # menú «/» del bot
            _api("setMyCommands", {"commands": json.dumps([
                {"command": "estado", "description": "Qué hay preparado"},
                {"command": "reintentar", "description": "Rehacer el vídeo de mañana"},
                {"command": "pausa", "description": "No publicar N días (/pausa 3)"},
                {"command": "seguir", "description": "Quitar la pausa"},
                {"command": "ver", "description": "Ver el vídeo de un día (/ver 12)"},
                {"command": "imagen", "description": "Pintar una imagen (/imagen Jesús en el lago)"},
                {"command": "retocar", "description": "Frase, reflexión, música o estilo de mañana"},
                {"command": "ayuda", "description": "Qué puedo hacer"}])})
            log("menú de comandos puesto")
        elif orden == "prueba":  # el único que sí falla si Telegram no responde (para «Configurar Telegram»)
            sys.exit(0 if enviar("👋 <b>¡Hola, Carlos!</b> Soy el gestor de CatolicAid. A partir de ahora te avisaré aquí "
                   "de los vídeos, las publicaciones, los fallos y lo que necesite de ti. 🙏") else 1)
        elif orden == "listo":
            aviso_listo()
        elif orden == "video":
            aviso_video(sys.argv[2], sys.argv[3])
        elif orden == "tiktok":
            aviso_tiktok(sys.argv[2])
        elif orden == "manana":
            aviso_manana()
        elif orden == "informe":
            aviso_informe(sys.argv[2])
        elif orden == "fallo":
            aviso_fallo()
        elif orden == "accion":
            enviar(f"🔔 {e(sys.argv[2])}")
        else:
            print(__doc__)
    except Exception as ex:  # nunca bloquear
        log(f"aviso no enviado ({type(ex).__name__}: {ex})")


if __name__ == "__main__":
    main()
