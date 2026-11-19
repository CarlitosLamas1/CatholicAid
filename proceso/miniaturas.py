#!/usr/bin/env python3
"""CatholicAid · Poner la miniatura a los vídeos de YouTube que no la tienen (workflow «Poner miniaturas»).

YouTube rechazaba las miniaturas (403) hasta que Carlos verificó los canales por teléfono (15/11/2026). Aquí se
rehacen desde los registros y se suben a todos los vídeos sin miniatura, en los tres idiomas y con la MISMA imagen
en los tres: la del día de la escena donde está la frase clave del español (si no hay, la primera imagen del día
y, en último caso, el evangelista). La frase va en el idioma de cada canal.

Uso: python3 proceso/miniaturas.py [--simular] [--todas] [--solo=AAAA-MM-DD[-en|-pt],…] [--vertical]
     python3 proceso/miniaturas.py --tras-proceso   (cada hora, desde «Comentarios»: la portada de los Shorts)
"""
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def leer(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except Exception:
        return {}


def imagen_del_dia(fecha, es):
    """La imagen común a los tres idiomas para ese día (ver arriba). es: registro en español."""
    dias = RAIZ / "biblioteca" / "dias"

    def de_escena(n):
        return next((p for p in sorted(dias.glob(f"{fecha}_e{n}.*")) if p.suffix.lower() in (".jpg", ".png")), None)

    frase = ev.espacios(es.get("frase_clave", ""))
    escena = next((f.get("escena") for f in es.get("fragmentos") or []
                   if frase and frase in ev.espacios(ev.hablado(f.get("texto", "")))), None)
    if escena is not None and de_escena(escena):
        return de_escena(escena)
    for nombre in es.get("imagenes") or []:
        m = re.match(rf"dias/{fecha}_e(\d+)", str(nombre))
        if m and de_escena(m.group(1)):
            return de_escena(m.group(1))
    libro = (es.get("libro") or es.get("cita", "").split()[0] if es.get("cita") else "").lower()
    retrato = RAIZ / "personajes" / "evangelistas" / f"{libro}.jpg"
    return retrato if retrato.exists() else None


def pendientes(todas=False, solo=()):
    """[(nombre, idioma, registro)] de los vídeos subidos cuya miniatura no consta como puesta (o todos, con todas).
    solo: nombres de registro concretos (p. ej. 2026-11-18-en), aunque ya la tengan."""
    lista = []
    for ruta in sorted((RAIZ / "episodios").glob("*.json")):
        if solo and ruta.stem not in solo:
            continue
        if solo:
            todas = True
        reg = leer(ruta)
        yt = reg.get("youtube") or {}
        if yt.get("id") and (todas or yt.get("miniatura") != "ok") and reg.get("frase_clave"):
            lista.append((ruta.stem, reg.get("idioma") or "es", reg))
    return lista


DIAS_TRAS_PROCESO = 14   # vídeos de las dos últimas semanas (y los programados)
MAX_POR_PASADA = 8       # 50 unidades de cuota cada una


def pendientes_tras_proceso(hoy):
    """Vídeos subidos cuya miniatura aún no se ha puesto con el vídeo ya procesado (miniatura_shorts != "ok").
    YouTube solo aplica la miniatura a la portada del Short si se pone cuando ha terminado de procesarlo
    (documentación de thumbnails.set; comprobado en Studio por Carlos el 19/11/2026): la que se pone al subir
    se queda solo en la vista horizontal."""
    lista = []
    for ruta in sorted((RAIZ / "episodios").glob("*.json"), reverse=True):
        try:
            fecha = dt.date.fromisoformat(ruta.stem[:10])
        except ValueError:
            continue
        if fecha < hoy - dt.timedelta(days=DIAS_TRAS_PROCESO):
            continue
        reg = leer(ruta)
        yt = reg.get("youtube") or {}
        if yt.get("id") and yt.get("miniatura_shorts") != "ok" and reg.get("frase_clave") and reg.get("modo") == "diario":
            lista.append((ruta.stem, reg.get("idioma") or "es", reg))
    return lista


def procesado(tok, vid):
    d = ev.http(ev.YT + f"videos?part=processingDetails&id={vid}", headers={"Authorization": f"Bearer {tok}"})
    items = d.get("items") or []
    return bool(items) and items[0].get("processingDetails", {}).get("processingStatus") == "succeeded"


def main():
    simular = "--simular" in sys.argv
    tras_proceso = "--tras-proceso" in sys.argv
    tokens, tmp = {}, Path(tempfile.mkdtemp())
    puestas = 0
    solo = [x.split("=", 1)[1] for x in sys.argv if x.startswith("--solo=")]
    solo = [n for x in solo for n in x.split(",") if n]
    lista = (pendientes_tras_proceso(dt.datetime.now(ev.MADRID).date())[:MAX_POR_PASADA] if tras_proceso
             else pendientes("--todas" in sys.argv, solo))
    for nombre, idioma, reg in lista:
        fecha = nombre[:10]
        es = leer(RAIZ / "episodios" / f"{fecha}.json") or reg
        if es.get("modo") != "diario":
            es = reg
        img = imagen_del_dia(fecha, es) or imagen_del_dia(fecha, reg)
        if not img:
            print(f"{nombre}: sin imagen para la miniatura; se deja")
            continue
        dia = dt.date.fromisoformat(fecha)
        destino, vertical = tmp / f"{nombre}.jpg", tmp / f"{nombre}-v.jpg"
        ev.miniatura(img, reg["frase_clave"], vertical, (1080, 1920), ev.color_tiempo(dia), ev.etiqueta_tiempo(dia, idioma))
        ev.miniatura_short(vertical, destino)  # la vertical en el centro: en Shorts se ve entera
        if "--vertical" in sys.argv:  # prueba: la vertical tal cual (9:16), como la portada de un Short
            destino = vertical
        if simular:
            print(f"{nombre}: {img.name} · «{reg['frase_clave']}»")
            continue
        try:
            if idioma not in tokens:
                ev.aplicar_idioma(idioma)
                tokens[idioma] = ev.token_youtube(idioma)
            if tras_proceso and not procesado(tokens[idioma], reg["youtube"]["id"]):
                print(f"{nombre}: YouTube aún lo está procesando; en la próxima pasada")
                continue
            estado = ev.subir_miniatura(tokens[idioma], reg["youtube"]["id"], destino)
        except Exception as ex:
            estado = f"error: {ex}"[:200]
        print(f"{nombre}: {img.name} -> {estado[:80]}")
        if estado == "ok":
            reg["youtube"]["miniatura"] = "ok"
            if tras_proceso or solo:
                reg["youtube"]["miniatura_shorts"] = "ok"
            (RAIZ / "episodios" / f"{nombre}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2),
                                                               encoding="utf-8")
            puestas += 1
    print(f"Miniaturas puestas: {puestas}")


if __name__ == "__main__":
    main()
