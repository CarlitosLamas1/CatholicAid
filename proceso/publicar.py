#!/usr/bin/env python3
"""CatholicAid · Publicar revisado.

Uso: python3 proceso/publicar.py AAAA-MM-DD       (canal en español)
     python3 proceso/publicar.py AAAA-MM-DD-pt    (canal en portugués: igual que el inglés, release pt-AAAA-MM-DD)
     python3 proceso/publicar.py AAAA-MM-DD-en    (canal en inglés: episodios/…-en.json, revisiones/…-en.json,
                                                  release en-AAAA-MM-DD, permiso secretos/youtube-en.enc, sin TikTok;
                                                  en el estreno se sube en PRIVADO sin programar)

Lee la revisión del día (revisiones/AAAA-MM-DD.json, la escribe la rutina «Revisor diario» o Carlos con 👍):
- OK  -> sube a YouTube el vídeo de la release tiktok-AAAA-MM-DD, programado a la hora_publicacion (Madrid, config), y lo añade
         a la lista del evangelista. TikTok lo publica a esa hora (tiktok-publicar.yml / Reloj) porque hay OK.
- No OK -> la primera vez rehace el vídeo (evangelio-diario) para que el revisor lo vuelva a mirar;
           la segunda, no se publica (no_publicar en el registro, se borra la release) y se avisa a Carlos.
Si el registro tiene «no_publicar» (⛔ o /pausa), no se publica nada aunque haya OK.
Si el revisor pide «repintar» escenas (imágenes mejorables), se borran, se rehace el vídeo una vez y se revisa de nuevo.
Nunca cambia el texto del Evangelio.
"""
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avisos  # noqa: E402
import evangelio as ev_mod  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
MAX_REHECHOS = 1


def log(*a):
    print(*a, flush=True)


def leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def guardar(ruta, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def sh(*args, check=True):
    return subprocess.run(list(map(str, args)), check=check, capture_output=True, text=True)


def guardar_en_main(mensaje, ruta_reg=None, reg=None):
    """Sube ya el registro (y las imágenes borradas) a main con el guardado seguro (proceso/guardar.py): justo después
    de subir a YouTube (15/11/2026: el guardado del final chocó, no quedó anotado y la pasada siguiente subió el vídeo
    otra vez) y antes de relanzar un vídeo (la nueva tirada lee el registro de main).
    Después, «reg» se vuelve a leer del disco: guardar.py lo deja con lo último de main más nuestros cambios."""
    r = sh(sys.executable, RAIZ / "proceso" / "guardar.py", mensaje, "episodios/", "biblioteca/dias/", "estado/",
           check=False)
    log((r.stdout or r.stderr).strip()[-300:])
    if ruta_reg is not None and reg is not None and ruta_reg.exists():
        nuevo = leer(ruta_reg)
        reg.clear()
        reg.update(nuevo)
    return r.returncode == 0


IMAGEN = re.compile(r"\b(imagen|im[aá]genes|plano|cuadro|pintura)\b", re.I)
ESCENA = re.compile(r"\b(?:escena\s*|e)(\d)\b", re.I)
SIN_ARREGLO = re.compile(r"\bPNG\b|biblioteca/|evangelistas/|reutiliza", re.I)


def repintar_de_avisos(rev, fecha):
    """Avisos del revisor sobre una imagen pintada del día («La imagen de la escena 2 muestra a Jesús…», «firma en la
    esquina de e1») -> [{"escena": n, "corregir": aviso}]. Solo escenas cuya imagen del día existe."""
    pedidas = {}
    for aviso in rev.get("avisos") or []:
        if not IMAGEN.search(aviso) or SIN_ARREGLO.search(aviso):
            continue
        for n in {int(m) for m in ESCENA.findall(aviso)}:
            if any((RAIZ / "biblioteca" / "dias" / f"{fecha}_e{n}.{ext}").exists() for ext in ("jpg", "png")):
                pedidas.setdefault(n, []).append(aviso)
    return [{"escena": n, "corregir": "Fix the problem the reviewer found in the previous version (in Spanish): "
             + " ".join(t)} for n, t in sorted(pedidas.items())]


FRASE_FLOJA = re.compile(r"frase clave.*\b(floja|no se entiende|se entiende a medias|depende del contexto)", re.I)


def da_tiempo(fecha, idioma="es", horas=3):
    """Quedan más de «horas» para la hora de publicación de ese día: da tiempo a rehacer y revisar otra vez."""
    publica = dt.datetime.combine(dt.date.fromisoformat(fecha), ev_mod.hora_pub(idioma), ev_mod.MADRID)
    return dt.datetime.now(ev_mod.MADRID) <= publica - dt.timedelta(hours=horas)


def pedir_otra_frase(fecha, idioma, reg, rev):
    """El revisor ve que la frase clave no se entiende sola ("cambiar_frase": true, o lo dice en sus avisos): se
    apunta como descartada y la nueva tirada elige otra. Una sola vez por día y solo en español (el inglés y el
    portugués copian la del español y se rehacen detrás). Devuelve True si hay que rehacer."""
    textos = [t for t in (rev.get("avisos") or []) + (rev.get("motivos") or []) if isinstance(t, str)]
    pide = bool(rev.get("cambiar_frase")) or any(FRASE_FLOJA.search(t) for t in textos)
    if idioma != "es" or not pide or not reg.get("frase_clave") or reg.get("frases_descartadas"):
        return False
    if not da_tiempo(fecha):
        log("Cambiar la frase clave: ya no da tiempo antes de publicar; se deja como está.")
        return False
    reg["frases_descartadas"] = [reg["frase_clave"]]
    log(f"Frase clave descartada («{reg['frase_clave']}»): el vídeo se rehace con otra.")
    return True


def pedir_repintar(fecha, idioma, reg, rev):
    """El revisor pide repintar escenas (rev["repintar"] = [{"escena": n, "corregir": "..."}]): se borran esas imágenes
    del día y la nueva tirada las pinta otra vez con la corrección. Una sola vez por día, solo en español (el inglés
    reutiliza las imágenes) y solo si da tiempo a revisarlo antes de publicar. Devuelve True si hay que rehacer."""
    pedidas = [x for x in rev.get("repintar") or [] if isinstance(x, dict) and str(x.get("escena", "")).isdigit()]
    if not pedidas:  # el revisor no lo pide de forma explícita: se sacan de sus avisos sobre imágenes del día
        pedidas = repintar_de_avisos(rev, fecha)
    if idioma != "es" or not pedidas or reg.get("repintados", 0) >= 1:
        return False
    if not da_tiempo(fecha):
        log("Repintar: ya no da tiempo antes de publicar; se deja como está.")
        return False
    borradas = []
    for x in pedidas:
        for ext in ("jpg", "png"):
            ruta = RAIZ / "biblioteca" / "dias" / f"{fecha}_e{int(x['escena'])}.{ext}"
            if ruta.exists():
                ruta.unlink()
                borradas.append(ruta.name)
    if not borradas:
        return False
    reg["repintar"] = [{"escena": int(x["escena"]), "corregir": str(x.get("corregir", ""))[:400]} for x in pedidas]
    reg["repintados"] = reg.get("repintados", 0) + 1
    log(f"Repintar: borradas {', '.join(borradas)}; el vídeo se rehace con las imágenes corregidas.")
    return True


def _momento(t):
    try:
        return dt.datetime.fromisoformat(t)
    except (TypeError, ValueError):
        return None


def desfasado(es, otro):
    """¿El vídeo en inglés/portugués se hizo con una versión del español que ya no es la buena? Devuelve el motivo
    o "". El español manda: misma frase clave, misma reflexión y mismas imágenes en los tres canales."""
    if not es.get("frase_clave") or not otro.get("generado"):
        return ""
    t_es, t_otro = _momento(es.get("generado")), _momento(otro.get("generado"))
    posterior = bool(t_es and t_otro and t_es > t_otro)  # el español se rehízo después de hacer este vídeo
    if "frase_es" in otro:
        if otro["frase_es"] != es["frase_clave"]:
            return "la frase clave del español ha cambiado"
        if otro.get("reflexion_es", "") != es.get("reflexion", ""):
            return "la reflexión del español ha cambiado"
    elif posterior and es.get("rehechos"):  # registros anteriores al 15/11/2026: no guardaban qué copiaron
        return "el español se rehízo después"
    if posterior and es.get("repintados"):
        return "el español repintó imágenes después"
    return ""


def arrastrar_idiomas(fecha, es):
    """El español ya tiene el OK definitivo: si el inglés o el portugués de ese día se hicieron con una versión
    anterior (17/11/2026: el español se rehízo y quedaron con otra frase y la imagen vieja), se rehacen una vez,
    si quedan más de 3 h para publicar. Nunca bloquea."""
    flujos = {"en": "evangelio-ingles.yml", "pt": "evangelio-portugues.yml"}
    for idioma, flujo in flujos.items():
        try:
            if not ev_mod.CFG.get(idioma, {}).get("activo"):
                continue
            ruta = RAIZ / "episodios" / f"{fecha}-{idioma}.json"
            otro = leer(ruta)
            if (otro.get("modo") != "diario" or otro.get("no_publicar") or otro.get("rehecho_por_es")
                    or otro.get("revision") not in ("pendiente", "ok")):
                continue
            motivo = desfasado(es, otro)
            if not motivo:
                continue
            if not da_tiempo(fecha, idioma):
                log(f"{idioma} {fecha}: {motivo}, pero ya no da tiempo a rehacerlo; se deja como está.")
                continue
            otro["rehecho_por_es"] = 1
            otro["revision"] = "rechazada"
            guardar(ruta, otro)
            guardar_en_main(f"Rehacer {fecha}-{idioma}: {motivo}")
            sh("gh", "release", "delete", f"{idioma}-{fecha}", "--yes", "--cleanup-tag", check=False)
            sh("gh", "workflow", "run", flujo, "-f", f"fecha={fecha}", "-f", "modo=diario")
            log(f"{idioma} {fecha}: {motivo}; lo rehago para que coincida con el español.")
        except Exception as ex:
            log(f"{idioma} {fecha}: no se pudo comprobar si coincide con el español ({ex})")


def main():
    nombre = sys.argv[1].strip()
    fecha, idioma = avisos.idioma_de(nombre)
    ev_mod.aplicar_idioma(idioma)
    lengua = avisos.etiqueta(idioma)
    release = f"tiktok-{fecha}" if idioma == "es" else f"{idioma}-{fecha}"
    flujo = {"es": "evangelio-diario.yml", "en": "evangelio-ingles.yml", "pt": "evangelio-portugues.yml"}[idioma]
    ruta_reg = RAIZ / "episodios" / f"{nombre}.json"
    reg, rev = leer(ruta_reg), leer(RAIZ / "revisiones" / f"{nombre}.json")
    if not reg:
        log(f"No hay registro del {fecha}; nada que publicar.")
        return
    if reg.get("no_publicar"):
        log(f"El {fecha} está marcado para no publicar ({reg['no_publicar']}).")
        return
    if not rev:
        log(f"El {fecha} aún no está revisado.")
        return
    if rev.get("generado") and reg.get("generado") and rev["generado"] != reg["generado"]:
        log(f"La revisión es de otra versión del vídeo ({rev['generado']} ≠ {reg['generado']}); espero a la nueva.")
        return
    cuando = avisos.fecha_txt(fecha)
    motivos = rev.get("motivos") or []

    sinc = reg.get("sincronia") or {}
    if rev.get("ok") and sinc and not sinc.get("ok") and reg.get("rehechos", 0) < MAX_REHECHOS:
        # Subtítulos que pueden ir desfasados (grabación cortada sin poder escucharla, o varias frases sin reconocer):
        # se rehace una vez aunque el revisor diera el OK.
        rev = {**rev, "ok": False, "motivos": (rev.get("motivos") or []) + [
            "Los subtítulos podrían no ir sincronizados con la voz; lo rehago para dejarlos perfectos."]}
    if rev.get("ok") and reg.get("revision") == "rechazada" and reg.get("repintar"):
        log(f"El {nombre} se está rehaciendo con imágenes repintadas; espero a la nueva versión.")
        return
    mejorable = rev.get("ok") or reg.get("rehechos", 0) < MAX_REHECHOS
    repintar = mejorable and pedir_repintar(fecha, idioma, reg, rev)
    otra_frase = mejorable and pedir_otra_frase(fecha, idioma, reg, rev)
    if rev.get("ok") and (repintar or otra_frase):  # aprobado, pero mejorable: se arregla y se revisa otra vez
        reg["revision"] = "rechazada"
        guardar(ruta_reg, reg)
        guardar_en_main(("Repintar imágenes" if repintar else "Cambiar la frase clave") + f": {nombre}", ruta_reg, reg)
        sh("gh", "release", "delete", release, "--yes", "--cleanup-tag", check=False)
        sh("gh", "workflow", "run", flujo, "-f", f"fecha={fecha}", "-f", "modo=diario")
        log(f"Revisión OK con imágenes o frase mejorables: rehago el vídeo del {nombre}.")
        return

    if not rev.get("ok"):
        n = reg.get("rehechos", 0)
        if n < MAX_REHECHOS:
            reg["rehechos"] = n + 1
            reg["revision"] = "rechazada"
            guardar(ruta_reg, reg)
            guardar_en_main(f"Revisión no OK: rehacer {nombre}", ruta_reg, reg)
            sh("gh", "release", "delete", release, "--yes", "--cleanup-tag", check=False)
            sh("gh", "workflow", "run", flujo, "-f", f"fecha={fecha}", "-f", "modo=diario")
            log(f"Revisión no OK: rehago el vídeo del {nombre}.")
            avisos.enviar(f"🔎 {lengua} · El revisor no ha aprobado el vídeo del <b>{avisos.e(cuando)}</b>:\n"
                          + "\n".join(f"• {avisos.e(m)}" for m in motivos)
                          + "\n\n🔁 Lo rehago solo y el revisor lo vuelve a mirar. No tienes que hacer nada.")
        else:
            reg["revision"] = "rechazada"
            reg["no_publicar"] = "revisor: " + "; ".join(motivos)[:300]
            guardar(ruta_reg, reg)
            sh("gh", "release", "delete", release, "--yes", "--cleanup-tag", check=False)
            log(f"Revisión no OK por segunda vez: el {nombre} no se publica.")
            avisos.enviar(f"⛔ {lengua} · El vídeo del <b>{avisos.e(cuando)}</b> <b>no se publica</b>: el revisor no lo ha aprobado "
                          "ni después de rehacerlo.\n" + "\n".join(f"• {avisos.e(m)}" for m in motivos)
                          + "\n\nEl gestor lo revisará.")
        return

    reg["revision"] = "ok"
    tmp = Path(tempfile.mkdtemp())
    sh("gh", "release", "download", release, "-D", tmp, "-p", "miniatura.jpg", check=False)
    miniatura = tmp / "miniatura.jpg" if (tmp / "miniatura.jpg").exists() else None
    if reg.get("youtube", {}).get("id"):
        log(f"El {nombre} ya está subido a YouTube ({reg['youtube']['url']}).")
        try:  # completa listas y miniatura si faltaron (p. ej. sin permiso entonces); nunca bloquea
            ev_mod.publicar_extras(ev_mod.token_youtube(idioma), reg["youtube"]["id"], reg,
                                   dt.date.fromisoformat(fecha), miniatura, idioma)
        except Exception as ex:
            log(f"Extras no completados ({ex})")
        guardar(ruta_reg, reg)
        if idioma == "es":
            arrastrar_idiomas(fecha, reg)
        return
    sh("gh", "release", "download", release, "-D", tmp, "-p", "video.mp4")
    video = tmp / "video.mp4"
    ev = {"cita": reg["cita"], "titulo": reg.get("titulo") or reg["fragmentos"][0]["texto"],
          "fuente_texto": reg.get("texto_fuente", "Vatican News"), "reflexion": reg.get("reflexion", ""),
          "frase_clave": reg.get("frase_clave", ""), "musica": reg.get("musica", "")}
    tok = ev_mod.token_youtube(idioma)
    vid, estado = ev_mod.subir_youtube(video, ev, dt.date.fromisoformat(fecha), "diario", tok, idioma)
    reg["youtube"] = {"id": vid, "url": f"https://youtu.be/{vid}", **estado}
    guardar(ruta_reg, reg)
    # Lo subido queda anotado en main YA, pase lo que pase después: sin esto, un fallo al guardar al final hacía
    # que la pasada siguiente subiera el vídeo otra vez.
    if not guardar_en_main(f"Publicar revisado: {nombre} subido a YouTube", ruta_reg, reg):
        log("AVISO: no se pudo anotar en main el vídeo recién subido; lo reintenta el paso «Guardar registro».")
    viejo = reg.get("reemplaza")
    if viejo and viejo != vid:  # versión anterior ya subida (vídeo rehecho): se borra para que no salgan dos
        try:
            ev_mod.http(ev_mod.YT + f"videos?id={viejo}", headers={"Authorization": f"Bearer {tok}"},
                        method="DELETE", raw=True)
            log(f"Borrada de YouTube la versión anterior ({viejo})")
            reg["reemplazado"] = reg.pop("reemplaza")
        except Exception as ex:
            log(f"No se pudo borrar la versión anterior {viejo} ({ex})")
        guardar(ruta_reg, reg)
    try:
        ev_mod.publicar_extras(tok, vid, reg, dt.date.fromisoformat(fecha), miniatura, idioma)
    except Exception as ex:
        log(f"Listas/miniatura no completadas ({ex})")
    guardar(ruta_reg, reg)
    log(f"Subido: https://youtu.be/{vid} ({estado['privacyStatus']})")
    if idioma == "es":
        arrastrar_idiomas(fecha, reg)
    hora = ev_mod.hora_pub(idioma).strftime("%H:%M")
    cuando_yt = f"programado a las {hora}" if estado.get("publishAt") else f"queda {estado['privacyStatus']}"
    nota = "" if rev.get("por") == "Carlos" else "\n🔎 Revisado por el revisor: todo correcto."
    if idioma == "es":
        avisos.enviar(f"✅ {lengua} · Vídeo del <b>{avisos.e(cuando)}</b> aprobado y subido a YouTube ({cuando_yt}): "
                      f"{avisos.e(reg['youtube']['url'])}\n🎵📸 TikTok e Instagram se publican a las {hora}.{nota}")
    else:
        estreno = "" if estado.get("publishAt") else "\n🔒 Estreno: queda en privado; tú decides cuándo se publica."
        avisos.enviar(f"✅ {lengua} · Vídeo del <b>{avisos.e(cuando)}</b> aprobado y subido a {avisos.CANALES[idioma]} "
                      f"({cuando_yt}): {avisos.e(reg['youtube']['url'])}{estreno}{nota}")


if __name__ == "__main__":
    main()
