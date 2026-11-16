#!/usr/bin/env python3
"""CatholicAid · Revisión mecánica de reserva (workflow «Revisión de reserva», lo lanza el Reloj).

El vídeo solo se publica con el visto bueno del revisor (la rutina de Claude de cada hora). Si esa rutina no responde,
el vídeo se quedaría sin publicar. Cuando a un vídeo de HOY o de MAÑANA le quedan pocas horas para su hora de
publicación, lleva tiempo hecho y sigue sin veredicto, aquí se comprueba lo que se puede comprobar sin criterio
humano y se escribe el veredicto en revisiones/ («por»: «reserva»):
- el texto leído es idéntico al del Evangelio (fragmentos unidos = texto_evangelio);
- la frase clave es literal y de Jesús (o del texto, si Jesús no habla);
- hay reflexión y no es larga; duración y volumen dentro de lo normal; ningún audio anómalo; subtítulos en sincronía.
No mira las imágenes ni si el reparto de voces o la reflexión tienen sentido: por eso es solo la red de seguridad y
lo dice en los avisos. Si el revisor responde después, su veredicto sustituye a este (mismo archivo).

Uso: python3 proceso/revision_reserva.py            (revisa lo que cumpla las condiciones)
     python3 proceso/revision_reserva.py --ver NOMBRE  (solo muestra el veredicto que daría, p. ej. 2026-11-17-en)
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
MADRID = ZoneInfo("Europe/Madrid")
SUF = {"es": "", "en": "-en", "pt": "-pt"}
HORAS_ANTES = 4      # se actúa cuando faltan menos de estas horas para publicar…
HORAS_ESPERA = 3     # …y el vídeo lleva al menos estas horas hecho sin que el revisor diga nada


def leer(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except Exception:
        return {}


def plano(t):
    """Sin espacios ni comillas: así compara el revisor el texto leído con el del Evangelio."""
    return re.sub(r"[\s“”‘’\"«»]", "", t or "")


def comprobar(reg):
    """(ok, motivos, avisos, puntos) con las comprobaciones mecánicas de un registro."""
    motivos, avisos, puntos = [], [], {}
    frs = reg.get("fragmentos") or []
    lectura = [f for f in frs if not f.get("reflexion")][1:-1]  # sin el título ni «Palabra del Señor»
    if lectura and plano("".join(f["texto"] for f in lectura)) == plano(reg.get("texto_evangelio")):
        puntos["fidelidad"] = "✅ texto idéntico al del Evangelio (comprobado por programa)"
    else:
        motivos.append("El texto leído no coincide con el del Evangelio.")
        puntos["fidelidad"] = "❌ no coincide"
    frase = plano(reg.get("frase_clave"))
    de_jesus = [plano(f["texto"]) for f in lectura if f.get("personaje") == "jesus"]
    donde = de_jesus or [plano(reg.get("texto_evangelio"))]
    if not frase:
        avisos.append("No hay frase clave.")
        puntos["frase_clave"] = "⚠️ vacía"
    elif any(frase.strip(".,;:") in x for x in donde):
        puntos["frase_clave"] = "✅ literal"
    else:
        motivos.append("La frase clave no es literal o no es de Jesús.")
        puntos["frase_clave"] = "❌ no literal"
    reflexion = reg.get("reflexion") or ""
    if not reflexion or len(reflexion.split()) > 45:
        avisos.append("La reflexión falta o es larga.")
    puntos["reflexion"] = f"{len(reflexion.split())} palabras (no se ha valorado su sentido)"
    dur, lufs = float(reg.get("duracion_s") or 0), reg.get("lufs")
    if not dur or dur > 180:
        motivos.append(f"Duración fuera de límite ({dur:.0f} s).")
    if lufs is None or not -15.5 <= float(lufs) <= -12.5:
        avisos.append(f"Volumen fuera de lo habitual ({lufs} LUFS).")
    puntos["tecnica"] = f"{dur:.0f} s, {lufs} LUFS"
    raros = []
    for i, f in enumerate(frs):
        fin = frs[i + 1]["inicio"] if i + 1 < len(frs) else dur
        d = fin - f["inicio"]
        v = len(f["texto"]) / d if d > 0 else 0
        lento = d > 8 and v < 6 and not f.get("reflexion")  # la reflexión incluye el cierre musical: no cuenta
        if lento or (d > 3 and v > 30) or d <= 0:
            raros.append(f"fragmento {i + 1}: {v:.1f} car/s en {d:.1f} s")
    if raros:
        motivos.append("Audio anómalo: " + "; ".join(raros[:3]))
    puntos["audio"] = "❌ " + "; ".join(raros[:3]) if raros else "✅ velocidades normales"
    sinc = reg.get("sincronia")
    if sinc and not sinc.get("ok"):
        avisos.append("Los subtítulos podrían no ir sincronizados.")
    puntos["voces"] = puntos["imagenes"] = "— no comprobado (revisión automática)"
    avisos.insert(0, "Revisión automática de reserva: el revisor no respondió a tiempo. Comprobados texto, frase, "
                     "duración y audio; NO se han mirado las imágenes ni el reparto de voces.")
    return not motivos, motivos, avisos, puntos


def toca(reg, rev, ahora, hora_pub):
    """¿Hay que revisar de reserva este vídeo ahora?"""
    if reg.get("modo") != "diario" or reg.get("revision") != "pendiente" or reg.get("no_publicar"):
        return False
    if rev and (not rev.get("generado") or rev.get("generado") == reg.get("generado")):
        return False  # ya tiene veredicto de esta versión
    try:
        hecho = dt.datetime.fromisoformat(reg["generado"])
        publica = dt.datetime.combine(dt.date.fromisoformat(reg["fecha"]), hora_pub, MADRID)
    except (KeyError, TypeError, ValueError):
        return False
    falta = publica - ahora
    return (dt.timedelta(hours=-12) < falta < dt.timedelta(hours=HORAS_ANTES)
            and ahora - hecho >= dt.timedelta(hours=HORAS_ESPERA))


def hora_publicacion(cfg, idioma):
    v = cfg.get("hora_publicacion" + ("" if idioma == "es" else f"_{idioma}"), cfg.get("hora_publicacion", "07:30"))
    return dt.time(*map(int, v.split(":")[:2])) if isinstance(v, str) else dt.time(int(v))


def veredicto(reg, ahora):
    ok, motivos, avisos, puntos = comprobar(reg)
    rev = {"fecha": reg["fecha"], "ok": ok, "por": "reserva", "generado": reg.get("generado"),
           "revisado": ahora.isoformat(timespec="seconds"), "motivos": motivos, "avisos": avisos, "puntos": puntos}
    if reg.get("idioma"):
        rev["idioma"] = reg["idioma"]
    return rev


def pendientes(ahora, cfg=None):
    cfg = cfg or leer(RAIZ / "config" / "personajes.json")
    lista = []
    for dia in (ahora.date(), ahora.date() + dt.timedelta(days=1)):
        for idioma, suf in SUF.items():
            nombre = f"{dia}{suf}"
            reg = leer(RAIZ / "episodios" / f"{nombre}.json")
            if reg and toca(reg, leer(RAIZ / "revisiones" / f"{nombre}.json"), ahora, hora_publicacion(cfg, idioma)):
                lista.append((nombre, reg))
    return lista


def main():
    ahora = dt.datetime.now(MADRID)
    if len(sys.argv) == 3 and sys.argv[1] == "--ver":
        print(json.dumps(veredicto(leer(RAIZ / "episodios" / f"{sys.argv[2]}.json"), ahora), ensure_ascii=False, indent=2))
        return
    for nombre, reg in pendientes(ahora):
        rev = veredicto(reg, ahora)
        (RAIZ / "revisiones" / f"{nombre}.json").write_text(json.dumps(rev, ensure_ascii=False, indent=2),
                                                            encoding="utf-8")
        print(f"Revisión de reserva: {nombre} {'OK' if rev['ok'] else 'no OK: ' + '; '.join(rev['motivos'])}")


if __name__ == "__main__":
    main()
