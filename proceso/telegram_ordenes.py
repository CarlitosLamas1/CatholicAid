#!/usr/bin/env python3
"""CatholicAid · Órdenes de Carlos por Telegram (botones y comandos).

Lo lanza «Telegram: órdenes» cada 5 minutos. Lee los mensajes nuevos del bot (getUpdates), los confirma
uno a uno ANTES de actuar (así nada se ejecuta dos veces) y solo obedece al chat de Carlos.

Botones del aviso ✅ (dato «acción|AAAA-MM-DD»):
  ok   -> nada que hacer, sale a su hora          no   -> no publicar ese día
  img  -> rehacer con imágenes nuevas             voz  -> rehacer la lectura (voces y guion)
Comandos: /estado · /reintentar · /pausa N · /seguir · /ver D · /ayuda
"""
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avisos  # noqa: E402
from avisos import MADRID, RAIZ, e, enviar, episodio, fecha_txt, log  # noqa: E402

ESTADO = RAIZ / "estado" / "telegram.json"
AYUDA = ("🤖 <b>Lo que puedes pedirme</b>\n"
         "/estado: qué hay preparado y cómo fue el último vídeo\n"
         "/reintentar: vuelve a generar el vídeo de mañana\n"
         "/pausa 3: no publica durante 3 días (desde mañana)\n"
         "/seguir: quita la pausa\n"
         "/ver 12: te mando el vídeo del día 12 (o /ver mañana)\n"
         "/imagen Jesús calmando la tempestad: la pinto y, si te gusta, va a la biblioteca\n"
         "/retocar: cambiar frase, reflexión, música o estilo del vídeo de mañana\n"
         "💬 También puedes escribirme normal o mandarme una nota de voz («no publiques el domingo»).\n"
         "📷 Mándame una foto con el nombre del personaje (p. ej. «Jesús») y la pongo como su nuevo modelo.\n"
         "En el aviso ✅ tienes botones para publicar, no publicar o rehacerlo.\n"
         "⏱️ Leo tus mensajes cada 5–15 minutos.")


def hoy():
    return dt.datetime.now(MADRID).date()


def sh(*args, check=True):
    return subprocess.run(list(args), capture_output=True, text=True, timeout=300, check=check).stdout


def guardar_git(mensaje, *rutas):
    sh("git", "config", "user.name", "gestor-catholicaid")
    sh("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    sh("git", "add", "-A", *rutas, "estado/")
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    sh("git", "commit", "-q", "-m", mensaje)
    for _ in range(3):
        if subprocess.run(["git", "pull", "-q", "--rebase"]).returncode == 0 and \
           subprocess.run(["git", "push", "-q"]).returncode == 0:
            return
    raise RuntimeError("no pude guardar el cambio en GitHub")


def leer_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def escribir_estado(d):
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def guardar_episodio(fecha, reg):
    (RAIZ / "episodios" / f"{fecha}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def quitar_tiktok(fecha):
    return subprocess.run(["gh", "release", "delete", f"tiktok-{fecha}", "--yes", "--cleanup-tag"],
                          capture_output=True).returncode == 0


def desprogramar_youtube(vid):
    """Deja el vídeo en privado sin fecha de publicación. Devuelve True si YouTube lo aceptó."""
    try:
        tok = avisos.token_youtube()
        cuerpo = json.dumps({"id": vid, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                                                   "containsSyntheticMedia": True}}).encode()
        req = urllib.request.Request("https://www.googleapis.com/youtube/v3/videos?part=status", data=cuerpo,
                                     method="PUT", headers={"Authorization": f"Bearer {tok}",
                                                            "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).close()
        return True
    except Exception as ex:
        log(f"YouTube no deja desprogramar {vid} ({ex})")
        return False


def nota_youtube(ok, vid):
    if ok:
        return "En YouTube lo he dejado en privado, sin programar."
    return ("En YouTube no tengo permiso para quitar la programación (mientras no aprueben la auditoría "
            f"se queda privado igualmente). Si quieres, bórralo en Studio: https://studio.youtube.com/video/{vid}/edit")


# ---------- Acciones ----------

def no_publicar(fecha, motivo="Carlos pidió no publicarlo"):
    reg = episodio(fecha)
    tk = quitar_tiktok(fecha)
    partes = [f"⛔ <b>{e(fecha_txt(fecha))}</b>: no se publica."]
    partes.append("TikTok: cancelado." if tk else "TikTok: no había nada preparado.")
    if reg.get("youtube", {}).get("id"):
        partes.append(nota_youtube(desprogramar_youtube(reg["youtube"]["id"]), reg["youtube"]["id"]))
    if reg:
        reg["no_publicar"] = motivo
        guardar_episodio(fecha, reg)
    return "\n".join(partes)


def rehacer(fecha, imagenes):
    if dt.date.fromisoformat(str(fecha)) <= hoy():
        return f"Ese vídeo ({e(fecha_txt(fecha))}) ya está publicado o publicándose; no lo rehago."
    reg = episodio(fecha)
    extra = ""
    if reg.get("youtube", {}).get("id"):
        vid = reg["youtube"]["id"]
        ok = desprogramar_youtube(vid)
        if not ok:
            extra = (f"\nEl anterior se queda privado en YouTube (https://youtu.be/{vid}); "
                     "si lo publicas a mano, publica solo el nuevo.")
        reg.setdefault("descartados", []).append({**reg.pop("youtube"), "motivo": "otras imágenes" if imagenes else "otra lectura"})
        reg.pop("no_publicar", None)
        guardar_episodio(fecha, reg)
    quitar_tiktok(fecha)
    rutas = ["episodios/"]
    if imagenes:
        for p in (RAIZ / "biblioteca" / "dias").glob(f"{fecha}_e*.png"):
            p.unlink()
        rutas.append("biblioteca/dias/")
    guardar_git(f"Telegram: rehacer el {fecha}", *rutas)
    sh("gh", "workflow", "run", "evangelio-diario.yml", "-f", f"fecha={fecha}", "-f", "modo=diario")
    que = "con imágenes nuevas" if imagenes else "con otra lectura"
    return (f"🔁 Rehaciendo el vídeo del {e(fecha_txt(fecha))} {que}. "
            f"Te aviso cuando esté (unos 15 minutos).{e(extra)}")


def pausa(dias):
    hasta = hoy() + dt.timedelta(days=dias)
    est = leer_estado()
    est["pausa_hasta"] = str(hasta)
    escribir_estado(est)
    notas = []
    for i in range(1, dias + 1):
        f = hoy() + dt.timedelta(days=i)
        if episodio(f).get("youtube") or subprocess.run(["gh", "release", "view", f"tiktok-{f}"],
                                                         capture_output=True).returncode == 0:
            notas.append(no_publicar(f, "pausa"))
    guardar_git("Telegram: pausa", "estado/", "episodios/")
    texto = f"⏸️ En pausa hasta el {e(fecha_txt(hasta))} incluido: no se genera ni se publica nada. /seguir para quitarla."
    return "\n\n".join([texto, *notas])


def seguir():
    est = leer_estado()
    est.pop("pausa_hasta", None)
    escribir_estado(est)
    guardar_git("Telegram: fin de la pausa", "estado/")
    return "▶️ Pausa quitada. El vídeo de mañana se genera esta tarde como siempre (o usa /reintentar)."


def estado():
    lineas = [avisos.proximos_dias(hoy())]
    try:
        r = json.loads(sh("gh", "run", "list", "-w", "evangelio-diario.yml", "-L", "1", "--json",
                          "status,conclusion,createdAt,url"))[0]
        txt = {"success": "✅ bien", "failure": "❌ falló", "cancelled": "⚪ cancelado"}.get(
            r["conclusion"], "⏳ en marcha" if r["status"] != "completed" else r["conclusion"])
        cuando = dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")).astimezone(MADRID)
        lineas.append(f"\n🛠️ Último proceso: {txt} ({cuando:%d/%m %H:%M})")
    except Exception as ex:
        log(f"sin estado de procesos ({ex})")
    if avisos.pausa_hasta() >= str(hoy()):
        lineas.append(f"⏸️ En pausa hasta el {e(fecha_txt(avisos.pausa_hasta()))}.")
    return "\n".join(lineas)


def reintentar():
    f = hoy() + dt.timedelta(days=1)
    if avisos.pausa_hasta() >= str(f):
        return "Mañana está en pausa. Usa /seguir primero."
    if episodio(f).get("youtube"):
        return rehacer(f, imagenes=False)
    sh("gh", "workflow", "run", "evangelio-diario.yml", "-f", f"fecha={f}", "-f", "modo=diario")
    return f"🔁 Generando el vídeo del {e(fecha_txt(f))}. Te aviso cuando esté (unos 15 minutos)."


def interpretar_dia(txt):
    txt = txt.strip().lower()
    if txt in ("", "hoy"):
        return hoy()
    if txt in ("mañana", "manana"):
        return hoy() + dt.timedelta(days=1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt):
        return dt.date.fromisoformat(txt)
    m = re.fullmatch(r"(\d{1,2})(?:[/-](\d{1,2}))?", txt)
    if not m:
        return None
    d, mes = int(m.group(1)), int(m.group(2) or hoy().month)
    f = dt.date(hoy().year, mes, d)
    if f < hoy() - dt.timedelta(days=200):
        f = f.replace(year=f.year + 1)
    return f


def ver(arg):
    f = interpretar_dia(arg)
    if not f:
        return "No entiendo el día. Prueba /ver 12, /ver 12/11 o /ver mañana."
    reg = episodio(f)
    carpeta = Path(tempfile.mkdtemp())
    if subprocess.run(["gh", "release", "download", f"tiktok-{f}", "-D", str(carpeta), "-p", "video.mp4"],
                      capture_output=True).returncode == 0:
        try:
            avisos._api("sendVideo", {"chat_id": avisos.chat_id(), "caption": f"🎬 {fecha_txt(f)} · {reg.get('cita', '')}",
                                      "supports_streaming": "true"}, ("video", carpeta / "video.mp4"))
            return None
        except Exception as ex:
            log(f"no pude mandar el vídeo ({ex})")
    if reg.get("youtube", {}).get("url"):
        return (f"🎬 {e(fecha_txt(f))} · {e(reg.get('cita', ''))}\n▶️ {e(reg['youtube']['url'])}"
                "\n(Si es privado, ábrelo con la sesión de YouTube del canal.)")
    return f"No hay vídeo del {e(fecha_txt(f))} todavía."


# ---------- Fotos (retratos de personajes) ----------

def _sin_acentos(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def personajes():
    return avisos.config().get("personajes", {})


def personaje_en(texto):
    """Busca en el pie de foto el nombre de un personaje («nuevo Jesús» -> jesus)."""
    t = _sin_acentos(texto or "")
    candidatos = []
    for clave, d in personajes().items():
        for nombre in {clave, d.get("nombre", "")}:
            if nombre:
                candidatos.append((_sin_acentos(nombre), clave))
    for nombre, clave in sorted(candidatos, key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(nombre)}\b", t):
            return clave
    return None


def descargar_foto(file_id, destino):
    ruta = avisos._api("getFile", {"file_id": file_id})["file_path"]
    token = avisos.os.environ["TELEGRAM_BOT_TOKEN"].strip()
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{ruta}", timeout=120) as r:
        Path(destino).write_bytes(r.read())
    return destino


def a_png(origen, destino, lado=1536):
    try:
        from PIL import Image
    except ImportError:  # solo se instala cuando llega una foto
        carpeta = Path(tempfile.gettempdir()) / "py-pillow"
        base = [sys.executable, "-m", "pip", "install", "-q", "--target", str(carpeta), "pillow"]
        if subprocess.run(base + ["--break-system-packages"], capture_output=True, timeout=240).returncode != 0:
            subprocess.run(base, check=True, capture_output=True, timeout=240)
        sys.path.insert(0, str(carpeta))
        from PIL import Image
    im = Image.open(origen).convert("RGB")
    im.thumbnail((lado, lado))
    im.save(destino, "PNG", optimize=True)
    return im.size


def aplicar_foto(file_id, clave):
    tmp = Path(tempfile.mkdtemp()) / "foto"
    descargar_foto(file_id, tmp)
    if clave == "guardar":
        destino = RAIZ / "entrada" / "telegram" / f"{dt.datetime.now(MADRID):%Y-%m-%d_%H%M%S}.jpg"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(tmp.read_bytes())
        guardar_git("Telegram: foto recibida", "entrada/")
        return (f"📁 Foto guardada en <code>{e(destino.relative_to(RAIZ))}</code>. "
                "Dile al gestor qué quieres hacer con ella.")
    nombre = personajes().get(clave, {}).get("nombre", clave)
    destino = RAIZ / "personajes" / f"{clave}.png"
    aviso = ""
    if destino.exists():
        copia = RAIZ / "personajes" / "anteriores" / f"{clave}_{dt.datetime.now(MADRID):%Y-%m-%d_%H%M}.png"
        copia.parent.mkdir(parents=True, exist_ok=True)
        destino.replace(copia)
        aviso = f"\nEl anterior queda guardado en <code>{e(copia.relative_to(RAIZ))}</code> por si quieres volver a él."
    ancho, alto = a_png(tmp, destino)
    guardar_git(f"Telegram: nuevo retrato de {nombre}", "personajes/")
    pequeno = "\n⚠️ Es bastante pequeña; si tienes una más grande, mándala como archivo." if max(ancho, alto) < 700 else ""
    return (f"🖼️ <b>Nuevo modelo de {e(nombre)}</b> guardado ({ancho}×{alto}).\n"
            "Desde el próximo vídeo las imágenes nuevas lo usarán como referencia "
            f"(las ya pintadas no cambian).{aviso}{pequeno}")


def recibir_foto(msg):
    if msg.get("photo"):
        file_id = msg["photo"][-1]["file_id"]  # la de más resolución
    else:
        file_id = msg["document"]["file_id"]
    clave = personaje_en(msg.get("caption", ""))
    if clave:
        return aplicar_foto(file_id, clave)
    est = leer_estado()
    est["foto_pendiente"] = {"file_id": file_id, "recibida": dt.datetime.now(MADRID).isoformat(timespec="seconds")}
    escribir_estado(est)
    guardar_git("Telegram: foto pendiente", "estado/")
    claves = list(personajes())
    filas = [[(personajes()[k].get("nombre", k), f"pj|{k}") for k in claves[i:i + 3]] for i in range(0, len(claves), 3)]
    filas.append([("📁 Solo guardarla", "pj|guardar"), ("✖️ Nada", "pj|cancelar")])
    enviar("📷 Foto recibida. ¿De quién es el nuevo modelo?", botones=filas)
    return None


def elegir_personaje(clave):
    est = leer_estado()
    pendiente = est.pop("foto_pendiente", None)
    escribir_estado(est)
    guardar_git("Telegram: foto atendida", "estado/")
    if clave == "cancelar":
        return "👌 No hago nada con la foto."
    if not pendiente:
        return "No tengo ninguna foto pendiente: mándamela otra vez."
    return aplicar_foto(pendiente["file_id"], clave)


# ---------- Gemini (texto, gratis) ----------

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/"


def gemini_json(partes, esquema, temperatura=0.2):
    clave = avisos.os.environ.get("GEMINI_API_KEY", "").strip()
    if not clave:
        raise RuntimeError("falta GEMINI_API_KEY")
    ultimo = None
    preferidos = avisos.config().get("modelos_texto", ["gemini-2.5-flash"])
    try:  # como el proceso principal: los preferidos que existan + otros «flash» disponibles
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                     headers={"x-goog-api-key": clave})
        with urllib.request.urlopen(req, timeout=30) as r:
            nombres = [m["name"].split("/")[-1] for m in json.loads(r.read()).get("models", [])
                       if "generateContent" in m.get("supportedGenerationMethods", [])]
        extra = sorted((n for n in nombres if "flash" in n and n not in preferidos
                        and not re.search(r"tts|image|live|audio|embed|exp", n)), reverse=True)
        modelos = [m for m in preferidos if m in nombres] + extra[:3]
    except Exception:
        modelos = preferidos
    for modelo in [m for m in modelos for _ in (0, 1)]:  # cada modelo, dos intentos
        cuerpo = json.dumps({"contents": [{"parts": partes}],
                             "generationConfig": {"responseMimeType": "application/json", "responseSchema": esquema,
                                                  "temperature": temperatura}}).encode()
        req = urllib.request.Request(f"{GEMINI}{modelo}:generateContent", data=cuerpo,
                                     headers={"Content-Type": "application/json", "x-goog-api-key": clave})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.loads(r.read())
            texto = next(p["text"] for p in reversed(res["candidates"][0]["content"]["parts"]) if "text" in p)
            return json.loads(texto)
        except Exception as ex:
            ultimo = ex
            log(f"Gemini {modelo} no respondió ({ex})")
            if "404" in str(ex):
                continue
            __import__("time").sleep(8)
    raise RuntimeError(f"Gemini no disponible ({ultimo})")


# ---------- Retoques ----------

def ruta_retoque(fecha):
    return RAIZ / "retoques" / f"{fecha}.json"


def leer_retoque(fecha):
    try:
        return json.loads(ruta_retoque(fecha).read_text(encoding="utf-8"))
    except Exception:
        return {}


def escribir_retoque(fecha, d):
    ruta_retoque(fecha).parent.mkdir(exist_ok=True)
    ruta_retoque(fecha).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pistas():
    return [m.replace(" ", "_") for m in avisos.config().get("musica", [])]


def nombre_pista(nombre):
    for clave, txt in (("Satie", "Gymnopédie (Satie)"), ("Debussy", "Claro de luna (Debussy)"),
                       ("Bach", "Preludio en do (Bach)")):
        if clave in nombre:
            return txt
    return nombre.rsplit(".", 1)[0].replace("_", " ")[:28]


def _plano(t):
    """Texto en minúsculas, sin acentos ni signos, con el mapa de posiciones al original."""
    import unicodedata
    salida, mapa = [], []
    for i, c in enumerate(t):
        base = "".join(x for x in unicodedata.normalize("NFD", c.lower()) if unicodedata.category(x) != "Mn")
        if base.isalnum():
            salida.append(base)
            mapa.append(i)
        elif salida and salida[-1] != " ":
            salida.append(" ")
            mapa.append(i)
    return "".join(salida), mapa


def frase_literal(frase, fecha):
    """Busca la frase de Carlos en el Evangelio de ese día (sin importar tildes ni signos) y devuelve el texto
    tal cual aparece. None si no está. Si aún no hay vídeo, la deja como está (el proceso la valida)."""
    reg = episodio(fecha)
    textos = [f["texto"] for f in reg.get("fragmentos", []) if f["texto"] != reg.get("reflexion")]
    if not textos:
        return frase.strip()
    buscada = _plano(frase)[0].strip()
    if len(buscada.split()) < 2:
        return None
    for t in textos:
        plano, mapa = _plano(t)
        i = plano.find(buscada)
        if i >= 0:
            literal = t[mapa[i]:mapa[i + len(buscada) - 1] + 1]
            return literal.strip(" “”‘’\"'«»,;:")
    return None


def menu_retoque(fecha):
    r = leer_retoque(fecha)
    reg = episodio(fecha)
    actual = [f"💬 Frase: «{e(r.get('frase_clave') or reg.get('frase_clave') or '—')}»",
              f"🕊️ Reflexión: {e(r.get('reflexion') or reg.get('reflexion') or '—')}"]
    if r.get("musica"):
        actual.append(f"🎵 Música: {e(nombre_pista(r['musica']))}")
    if r.get("estilo"):
        actual.append(f"🖌️ Estilo: {e(r['estilo'])}")
    filas = [[("💬 Cambiar frase", f"rf|{fecha}"), ("🕊️ Cambiar reflexión", f"rr|{fecha}")],
             [(f"🎵 {nombre_pista(m)}", f"rm|{fecha}|{i}") for i, m in enumerate(pistas())],
             [("🖼️ Todo en óleo", f"re|{fecha}|oleo"), ("🎨 Todo en acuarela", f"re|{fecha}|acuarela")],
             [("✅ Rehacer ya con los cambios", f"rh|{fecha}"), ("✖️ Nada", "rx|")]]
    enviar(f"✏️ <b>Retocar el vídeo del {e(fecha_txt(fecha))}</b>\n" + "\n".join(actual)
           + "\n\nEl texto del Evangelio no se toca nunca.", botones=filas)
    return None


def esperar_texto(tipo, fecha):
    est = leer_estado()
    est["esperando"] = {"tipo": tipo, "fecha": str(fecha)}
    escribir_estado(est)
    guardar_git("Telegram: esperando texto", "estado/")
    if tipo == "frase":
        return ("💬 Escríbeme la frase del gancho. Tiene que estar <b>tal cual</b> en el Evangelio de ese día "
                "(da igual tildes o mayúsculas).")
    return "🕊️ Escríbeme la reflexión final (1 o 2 frases; la leerá el narrador)."


def guardar_retoque(fecha, campo, valor):
    fecha = str(fecha)
    if campo == "frase_clave":
        literal = frase_literal(valor, fecha)
        if not literal:
            return (f"❌ «{e(valor)}» no está tal cual en el Evangelio del {e(fecha_txt(fecha))}. "
                    "Cópiala del texto y mándamela otra vez.")
        valor = literal
    if campo == "reflexion" and len(valor.split()) > 60:
        return "❌ La reflexión es muy larga: déjala en 1 o 2 frases (máximo unas 60 palabras)."
    r = leer_retoque(fecha)
    r[campo] = valor
    if campo == "estilo":
        r["_imagenes_nuevas"] = True
    escribir_retoque(fecha, r)
    guardar_git(f"Telegram: retoque del {fecha} ({campo})", "retoques/")
    nombres = {"frase_clave": f"💬 Frase: «{e(valor)}»", "reflexion": f"🕊️ Reflexión: {e(valor)}",
               "musica": f"🎵 Música: {e(nombre_pista(valor))}", "estilo": f"🖌️ Estilo: {e(valor)}"}
    texto = f"✍️ Guardado para el {e(fecha_txt(fecha))}.\n{nombres[campo]}"
    if episodio(fecha).get("youtube") and dt.date.fromisoformat(fecha) > hoy():
        enviar(texto + "\n\nEl vídeo ya está hecho. ¿Lo rehago ya con este cambio?",
               botones=[[("✅ Rehacer ya", f"rh|{fecha}"), ("✏️ Otro retoque", f"ret|{fecha}")]])
        return None
    return texto + "\nSe aplicará cuando se genere el vídeo."


def rehacer_con_retoques(fecha):
    r = leer_retoque(fecha)
    nuevas = bool(r.pop("_imagenes_nuevas", False))
    if nuevas:
        escribir_retoque(fecha, r)
    return rehacer(fecha, imagenes=nuevas)


# ---------- Imágenes a petición (Nano Banana, de pago) ----------

def a_jpg(origen, destino):
    a_png(origen, destino.with_suffix(".tmp.png"), lado=2048)
    from PIL import Image
    Image.open(destino.with_suffix(".tmp.png")).convert("RGB").save(destino, "JPEG", quality=90)
    destino.with_suffix(".tmp.png").unlink()


def plan_imagen(peticion):
    cat = json.loads((RAIZ / "biblioteca" / "catalogo.json").read_text(encoding="utf-8"))
    con_retrato = [k for k in personajes() if (RAIZ / "personajes" / f"{k}.png").exists()]
    prompt = f"""Carlos, del canal católico CatolicAid (Evangelio del día), pide una imagen: «{peticion}».
Prepara la petición para el modelo de imágenes:
- "escena": descripción visual en INGLÉS, concreta y rica (personajes, acción, lugar, luz, composición vertical),
  fiel al Evangelio y a la tradición católica, respetuosa y devocional. Sin texto en la imagen.
  Si aparece Jesús, descríbelo así: {cat.get('jesus', '')}
- "estilo": "oleo" o "acuarela" (si Carlos no lo dice: oleo para interior, noche o recogimiento; acuarela para exterior luminoso).
- "personajes": claves de los que aparecen y tienen retrato de referencia, de entre: {', '.join(con_retrato)}.
- "titulo": título corto en español. "descripcion": en español, para qué escenas sirve (para elegirla después).
Si la petición no es apropiada para un canal católico, pon "escena" vacía y explica el motivo en "titulo"."""
    esquema = {"type": "OBJECT", "properties": {
        "escena": {"type": "STRING"}, "estilo": {"type": "STRING", "enum": ["oleo", "acuarela"]},
        "personajes": {"type": "ARRAY", "items": {"type": "STRING"}},
        "titulo": {"type": "STRING"}, "descripcion": {"type": "STRING"}},
        "required": ["escena", "estilo", "personajes", "titulo", "descripcion"]}
    plan = gemini_json([{"text": prompt}], esquema, 0.6)
    plan["personajes"] = [k for k in plan.get("personajes", []) if k in con_retrato]
    plan["peticion"] = peticion
    return plan


def pedir_imagen(peticion):
    if limite_imagenes():
        return limite_imagenes()
    plan = plan_imagen(peticion)
    if not plan.get("escena"):
        return f"🙏 No voy a pintar eso: {e(plan.get('titulo', ''))}"
    return generar_y_mandar(plan)


def limite_imagenes():
    limite = avisos.config().get("imagenes_ia", {}).get("max_telegram_dia", 10)
    if leer_estado().get("imagenes_hoy", {}).get(str(hoy()), 0) >= limite:
        return f"🛑 Hoy ya he pintado {limite} imágenes por Telegram (cuestan saldo). Mañana más."
    return None


def generar_y_mandar(plan):
    if limite_imagenes():
        return limite_imagenes()
    sys.path.insert(0, str(RAIZ / "proceso"))
    import imagenes
    modelo = avisos.config().get("imagenes_ia", {}).get("modelo")
    if modelo:
        imagenes.PREFERIDOS = [modelo]
    ident = dt.datetime.now(MADRID).strftime("%m%d%H%M%S")
    tmp = Path(tempfile.mkdtemp()) / "imagen"
    refs = [(k.capitalize(), RAIZ / "personajes" / f"{k}.png") for k in plan["personajes"]]
    imagenes.generar(plan["escena"], tmp, refs, plan["estilo"])
    destino = RAIZ / "entrada" / "imagenes" / f"{ident}.jpg"
    destino.parent.mkdir(parents=True, exist_ok=True)
    a_jpg(tmp, destino)
    est = leer_estado()
    est.setdefault("imagenes", {})[ident] = plan
    cuenta = est.setdefault("imagenes_hoy", {})
    est["imagenes_hoy"] = {str(hoy()): cuenta.get(str(hoy()), 0) + 1}
    escribir_estado(est)
    guardar_git("Telegram: imagen pedida por Carlos", "entrada/", "estado/")
    avisos._api("sendPhoto", {"chat_id": avisos.chat_id(), "parse_mode": "HTML",
                              "caption": f"🎨 <b>{e(plan['titulo'])}</b> ({e(plan['estilo'])})",
                              "reply_markup": avisos.teclado([[("📚 A la biblioteca", f"ib|{ident}"),
                                                               ("🔁 Otra versión", f"io|{ident}")],
                                                              [("✖️ Descartar", f"ix|{ident}")]])},
                ("photo", destino))
    return None


def imagen_a_biblioteca(ident):
    est = leer_estado()
    plan = est.get("imagenes", {}).pop(ident, None)
    origen = RAIZ / "entrada" / "imagenes" / f"{ident}.jpg"
    if not plan or not origen.exists():
        return "Esa imagen ya no está pendiente."
    ruta_cat = RAIZ / "biblioteca" / "catalogo.json"
    cat = json.loads(ruta_cat.read_text(encoding="utf-8"))
    nums = [int(k[1:]) for k in cat["clips"] if re.fullmatch(r"T\d+", k)]
    clave = f"T{(max(nums) + 1) if nums else 1:02d}"
    origen.replace(RAIZ / "biblioteca" / "clips" / f"{clave}.jpg")
    cat["clips"][clave] = {"titulo": plan["titulo"], "descripcion": plan["descripcion"], "estilo": plan["estilo"],
                           "personajes": plan["personajes"], "prompt_imagen": plan["escena"],
                           "origen": f"Telegram: «{plan.get('peticion', '')}»"}
    ruta_cat.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    escribir_estado(est)
    guardar_git(f"Telegram: imagen {clave} a la biblioteca", "biblioteca/", "entrada/", "estado/")
    return (f"📚 Añadida a la biblioteca como <b>{clave}</b>: «{e(plan['titulo'])}». "
            "Se usará en los vídeos cuya escena encaje.")


def descartar_imagen(ident):
    est = leer_estado()
    est.get("imagenes", {}).pop(ident, None)
    escribir_estado(est)
    (RAIZ / "entrada" / "imagenes" / f"{ident}.jpg").unlink(missing_ok=True)
    guardar_git("Telegram: imagen descartada", "entrada/", "estado/")
    return "🗑️ Descartada."


def otra_version(ident):
    plan = leer_estado().get("imagenes", {}).get(ident)
    if not plan:
        return "Esa imagen ya no está pendiente."
    return generar_y_mandar(plan)


# ---------- Lenguaje natural y notas de voz ----------

ACCIONES = ["estado", "reintentar", "pausa", "seguir", "ver", "no_publicar", "rehacer_imagenes", "rehacer_lectura",
            "frase", "reflexion", "musica", "estilo", "retocar", "imagen", "ayuda", "conversar"]
CONFIRMAR = {"reintentar", "pausa", "no_publicar", "rehacer_imagenes", "rehacer_lectura"}


def interpretar(texto=None, audio=None):
    manana = hoy() + dt.timedelta(days=1)
    prompt = f"""Eres el asistente del canal católico CatolicAid (un vídeo diario con el Evangelio del día, que se genera
la tarde anterior y se publica a las 7:00 en YouTube y TikTok). Hoy es {fecha_txt(hoy())} ({hoy()}); mañana es {manana}.
Convierte el mensaje de Carlos, el dueño, en UNA acción:
- estado: qué hay preparado / cómo va. - reintentar: volver a generar el vídeo de mañana.
- pausa: no publicar durante "dias" días. - seguir: quitar la pausa. - ver: mandarle el vídeo de "fecha".
- no_publicar: no publicar el vídeo de "fecha". - rehacer_imagenes / rehacer_lectura: rehacer el vídeo de "fecha"
  con otras imágenes / con otras voces.
- frase: poner como frase del gancho inicial "texto" (debe ser una frase del Evangelio de ese día; copia lo que dice Carlos).
- reflexion: poner como reflexión final "texto" (si Carlos solo da una idea, redáctala en 1–2 frases cálidas, de tú).
- musica: elegir la "pista" (una de: {', '.join(nombre_pista(m) for m in pistas())}). - estilo: "estilo" oleo o acuarela.
- retocar: quiere retocar el vídeo de "fecha" sin decir qué. - imagen: quiere que pintes una imagen; "texto" = lo que quiere ver.
- ayuda: pregunta qué puedes hacer. - conversar: saluda o pregunta algo general; contesta en "respuesta" (breve, cálida, sin inventar datos).
Reglas: "fecha" en formato AAAA-MM-DD; si se refiere a un vídeo y no dice día, usa mañana ({manana}). El texto del
Evangelio NO se puede cambiar nunca: si lo pide, usa conversar y explícalo. Si es un audio, pon en "transcripcion" lo que dice."""
    partes = [{"text": prompt}]
    if audio:
        partes.append({"inlineData": {"mimeType": audio[1], "data": __import__("base64").b64encode(audio[0]).decode()}})
    else:
        partes.append({"text": f"MENSAJE DE CARLOS: {texto}"})
    esquema = {"type": "OBJECT", "properties": {
        "accion": {"type": "STRING", "enum": ACCIONES}, "fecha": {"type": "STRING"}, "dias": {"type": "INTEGER"},
        "texto": {"type": "STRING"}, "pista": {"type": "STRING"}, "estilo": {"type": "STRING"},
        "respuesta": {"type": "STRING"}, "transcripcion": {"type": "STRING"}}, "required": ["accion"]}
    return gemini_json(partes, esquema)


def describir(a):
    f = a.get("fecha") or str(hoy() + dt.timedelta(days=1))
    return {"reintentar": "volver a generar el vídeo de mañana",
            "pausa": f"no publicar nada durante {a.get('dias') or 1} día(s)",
            "no_publicar": f"no publicar el vídeo del {fecha_txt(f)}",
            "rehacer_imagenes": f"rehacer el vídeo del {fecha_txt(f)} con imágenes nuevas",
            "rehacer_lectura": f"rehacer el vídeo del {fecha_txt(f)} con otra lectura"}.get(a["accion"], a["accion"])


def ejecutar(a):
    acc = a.get("accion", "ayuda")
    f = a.get("fecha") or str(hoy() + dt.timedelta(days=1))
    try:
        dt.date.fromisoformat(f)
    except ValueError:
        f = str(hoy() + dt.timedelta(days=1))
    if acc == "estado":
        return estado()
    if acc == "reintentar":
        return reintentar()
    if acc == "pausa":
        return pausa(max(1, min(int(a.get("dias") or 1), 30)))
    if acc == "seguir":
        return seguir()
    if acc == "ver":
        return ver(f)
    if acc == "no_publicar":
        r = no_publicar(f)
        guardar_git(f"Telegram: no publicar el {f}", "episodios/")
        return r
    if acc in ("rehacer_imagenes", "rehacer_lectura"):
        return rehacer(f, imagenes=acc == "rehacer_imagenes")
    if acc == "frase":
        return guardar_retoque(f, "frase_clave", a.get("texto", "")) if a.get("texto") else esperar_texto("frase", f)
    if acc == "reflexion":
        return guardar_retoque(f, "reflexion", a.get("texto", "")) if a.get("texto") else esperar_texto("reflexion", f)
    if acc == "musica":
        elegida = next((m for m in pistas() if a.get("pista") and (a["pista"].lower() in nombre_pista(m).lower()
                                                                    or nombre_pista(m).lower() in a["pista"].lower())), None)
        return guardar_retoque(f, "musica", elegida) if elegida else menu_retoque(f)
    if acc == "estilo" and a.get("estilo") in ("oleo", "acuarela"):
        return guardar_retoque(f, "estilo", a["estilo"])
    if acc in ("retocar", "estilo", "musica"):
        return menu_retoque(f)
    if acc == "imagen":
        return pedir_imagen(a.get("texto") or "una imagen devocional de Jesús")
    if acc == "conversar" and a.get("respuesta"):
        return e(a["respuesta"])
    return AYUDA


def lenguaje_natural(texto=None, audio=None):
    try:
        a = interpretar(texto, audio)
    except Exception as ex:
        log(f"no entendí el mensaje ({ex})")
        return ("No he podido entenderte ahora mismo (Gemini no responde). Prueba con una orden:\n\n" + AYUDA)
    log(f"interpretado: {a}")
    eco = f"🎙️ «{e(a['transcripcion'])}»\n\n" if audio and a.get("transcripcion") else ""
    if a.get("accion") in CONFIRMAR:
        est = leer_estado()
        est["confirmar"] = a
        escribir_estado(est)
        guardar_git("Telegram: pendiente de confirmar", "estado/")
        enviar(f"{eco}¿Quieres que vaya a <b>{e(describir(a))}</b>?", botones=[[("✅ Sí", "cf|si"), ("✖️ No", "cf|no")]])
        return None
    r = ejecutar(a)
    if r:
        return eco + r
    if eco:
        enviar(eco.strip())
    return None


def confirmar(respuesta):
    est = leer_estado()
    a = est.pop("confirmar", None)
    escribir_estado(est)
    guardar_git("Telegram: confirmación atendida", "estado/")
    if respuesta != "si" or not a:
        return "👌 No hago nada."
    return ejecutar(a)


# ---------- Bucle ----------

def responder_boton(cb):
    dato = cb.get("data", "")
    try:
        avisos._api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "Recibido"})
    except Exception:
        pass  # si han pasado unos minutos, Telegram ya no lo acepta; no importa
    accion, _, resto = dato.partition("|")
    msg = cb.get("message", {})
    if accion != "io":  # «otra versión» deja la imagen anterior con sus botones
        try:
            avisos._api("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                                   "reply_markup": json.dumps({"inline_keyboard": []})})
        except Exception:
            pass
    fecha, _, extra = resto.partition("|")
    if accion == "pj":
        return elegir_personaje(fecha)
    if accion == "prueba":
        return f"✅ Botón «{e(fecha)}» recibido: los botones funcionan. (Era una prueba: no he cambiado nada.)"
    if accion == "ok":
        return f"👍 Perfecto: el vídeo del {e(fecha_txt(fecha))} sale a las 7:00."
    if accion == "no":
        return ejecutar({"accion": "no_publicar", "fecha": fecha})
    if accion in ("img", "voz"):
        return rehacer(fecha, imagenes=accion == "img")
    if accion == "ret":
        return menu_retoque(fecha)
    if accion == "rf":
        return esperar_texto("frase", fecha)
    if accion == "rr":
        return esperar_texto("reflexion", fecha)
    if accion == "rm":
        return guardar_retoque(fecha, "musica", pistas()[int(extra)])
    if accion == "re":
        return guardar_retoque(fecha, "estilo", extra)
    if accion == "rh":
        return rehacer_con_retoques(fecha)
    if accion == "rx":
        return "👌 Sin cambios."
    if accion == "ib":
        return imagen_a_biblioteca(fecha)
    if accion == "io":
        return otra_version(fecha)
    if accion == "ix":
        return descartar_imagen(fecha)
    if accion == "cf":
        return confirmar(fecha)
    return "No reconozco ese botón."


def responder_texto(texto):
    texto = texto.strip()
    est = leer_estado()
    espera = est.pop("esperando", None)
    if espera:
        escribir_estado(est)
        if not texto.startswith("/"):
            campo = "frase_clave" if espera["tipo"] == "frase" else "reflexion"
            return guardar_retoque(espera["fecha"], campo, texto)
        guardar_git("Telegram: espera cancelada", "estado/")
    if not texto.startswith("/"):
        return lenguaje_natural(texto=texto)
    orden, _, arg = texto.partition(" ")
    orden = orden.lower().split("@")[0]
    if orden == "/estado":
        return estado()
    if orden == "/reintentar":
        return reintentar()
    if orden == "/pausa":
        n = int(arg) if arg.strip().isdigit() else 1
        return pausa(max(1, min(n, 30)))
    if orden in ("/seguir", "/reanudar"):
        return seguir()
    if orden == "/ver":
        return ver(arg)
    if orden == "/imagen":
        return pedir_imagen(arg) if arg.strip() else "Dime qué quieres ver: /imagen Jesús calmando la tempestad"
    if orden == "/retocar":
        return menu_retoque(interpretar_dia(arg) or hoy() + dt.timedelta(days=1)) if arg.strip() \
            else menu_retoque(hoy() + dt.timedelta(days=1))
    return AYUDA


def actualizar_repo():
    """Trae lo último del repo (registros, estado). Devuelve True si ha cambiado el código del bot."""
    antes = sh("git", "rev-parse", "HEAD").strip()
    subprocess.run(["git", "pull", "-q", "--rebase"], capture_output=True, timeout=120)
    cambios = sh("git", "diff", "--name-only", antes, "HEAD", check=False)
    return any(x in cambios for x in ("proceso/telegram_ordenes.py", "proceso/avisos.py"))


def atender(updates):
    yo = avisos.chat_id()
    for u in updates:
        avisos._api("getUpdates", {"offset": u["update_id"] + 1, "timeout": 0})  # confirmar antes de actuar
        cb, msg = u.get("callback_query"), u.get("message")
        chat = str((cb or {}).get("message", {}).get("chat", {}).get("id") or (msg or {}).get("chat", {}).get("id"))
        if chat != yo:
            log(f"ignoro un mensaje de otro chat ({chat})")
            continue
        msg = msg or {}
        entrada = cb.get("data") if cb else msg.get("text", "")
        es_foto = bool(msg.get("photo") or str(msg.get("document", {}).get("mime_type", "")).startswith("image/"))
        audio = msg.get("voice") or msg.get("audio")
        if es_foto:
            entrada = "foto " + msg.get("caption", "")
        elif audio:
            entrada = "nota de voz"
        log(f"orden: {entrada}")
        try:
            if cb:
                r = responder_boton(cb)
            elif es_foto:
                r = recibir_foto(msg)
            elif audio:
                tmp = Path(tempfile.mkdtemp()) / "audio"
                descargar_foto(audio["file_id"], tmp)
                r = lenguaje_natural(audio=(tmp.read_bytes(), audio.get("mime_type", "audio/ogg")))
            else:
                r = responder_texto(entrada or "")
        except Exception as ex:
            log(f"falló «{entrada}»: {ex}")
            r = f"⚠️ No he podido hacer «{e(entrada)}»: {e(str(ex)[:200])}. El gestor lo revisará."
        if r:
            enviar(r)


def main(minutos=0):
    """minutos=0: atiende lo pendiente y termina. minutos>0: se queda escuchando (respuesta en segundos) hasta
    agotar el tiempo o hasta que cambie el código del bot; luego el workflow lanza el relevo."""
    fin = __import__("time").time() + minutos * 60
    tipos = json.dumps(["message", "callback_query"])
    while True:
        espera = 50 if minutos else 0
        try:
            updates = avisos._api("getUpdates", {"timeout": espera, "allowed_updates": tipos}, espera=espera)
        except Exception as ex:
            log(f"Telegram no responde ({ex})")
            updates = []
            __import__("time").sleep(20 if minutos else 0)
        if updates:
            if minutos:
                actualizar_repo()
            atender(updates)
        if not minutos:
            if not updates:
                log("sin mensajes nuevos")
            return
        if __import__("time").time() > fin:
            log("tiempo agotado: paso el relevo")
            return
        if not updates and int(__import__("time").time()) % 600 < 55 and actualizar_repo():
            log("ha cambiado el código del bot: paso el relevo para usar la versión nueva")
            return


if __name__ == "__main__":
    try:
        main(int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--escuchar" else 0)
    except Exception as ex:  # nunca bloquear nada
        log(f"órdenes no procesadas ({type(ex).__name__}: {ex})")
