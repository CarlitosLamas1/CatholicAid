#!/usr/bin/env python3
"""CatholicAid · Comprobar los textos de los próximos días (sin red, sin cupo, sin grabar nada).

Para cada cita de biblia/citas.json de hoy a +7 días monta el texto en los tres idiomas con LAS MISMAS funciones
que usa el vídeo (evangelio.py) y comprueba que:
  · no falta ningún versículo (en portugués y en español, de la versión revisada);
  · el último versículo montado es el último de la cita (24/11/2026: Lucas 21,5-11 salió 5-9 en portugués).
Resultado en estado/textos.json ({"fecha", "problemas": [{"fecha", "idioma", "cita", "motivo"}]}); lo leen el
parte diario y la rutina «Revisor diario» (PASO 4d/4e), que completa lo que falte. Lo lanza el mantenimiento diario.
Uso: python3 proceso/comprobar_textos.py [días]
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evangelio as ev  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
MADRID = ev.MADRID


def fin_de_cita(cita, vs):
    """(capítulo, versículo) con el que acaba la cita según su propio texto ('Lucas 21, 5-11' -> (21, 11))."""
    m = re.search(r"(?:(\d+)\s*,\s*)?(\d+)[a-d]?\s*$", cita.strip())
    if not m:
        return None
    return (int(m.group(1)) if m.group(1) else vs[-1][0]), int(m.group(2))


def comprobar(cita, idioma):
    """'' si el texto de esa cita está completo en ese idioma; si no, el motivo."""
    libro = cita.split()[0]
    if idioma == "es":
        texto, fuente = ev.texto_torres_amat(cita)
        if not ev.texto_revisado(fuente):
            return "falta la versión revisada de algún versículo (se usaría el Torres Amat de 1836 tal cual)"
        datos, carpeta = ev.cargar_libro(libro), RAIZ / "biblia" / "revisada"
    elif idioma == "en":
        texto, _ = ev.texto_web(cita)
        datos, carpeta = ev.cargar_web(libro), RAIZ / "biblia" / "web" / "revisada"
    else:
        texto, _ = ev.texto_figueiredo(cita)
        datos, carpeta = ev.cargar_figueiredo(libro), RAIZ / "biblia" / "figueiredo" / "revisada"
    ruta = carpeta / f"{libro.lower()}.json"
    rev = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    vs = ev.versiculos(cita, datos, rev)
    fin = fin_de_cita(cita, vs)
    if fin and vs[-1] != fin:
        return f"el texto acaba en {vs[-1][0]},{vs[-1][1]} y la cita en {fin[0]},{fin[1]}"
    if not texto.strip():
        return "texto vacío"
    return ""


def main():
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    hoy = dt.datetime.now(MADRID).date()
    citas = json.loads((RAIZ / "biblia" / "citas.json").read_text(encoding="utf-8"))
    cfg = json.loads((RAIZ / "config" / "personajes.json").read_text(encoding="utf-8"))
    idiomas = ["es"] + [x for x in ("en", "pt") if cfg.get(x, {}).get("activo")]
    problemas, revisadas = [], 0
    for n in range(dias + 1):
        fecha = str(hoy + dt.timedelta(days=n))
        cita = citas.get(fecha)
        if not cita:
            continue
        for idioma in idiomas:
            try:
                motivo = comprobar(cita, idioma)
            except Exception as ex:
                motivo = str(ex)[:200]
            revisadas += 1
            if motivo:
                problemas.append({"fecha": fecha, "idioma": idioma, "cita": cita, "motivo": motivo})
                print(f"✗ {fecha} {idioma} {cita}: {motivo}")
    print(f"Textos comprobados: {revisadas}; con problemas: {len(problemas)}")
    salida = RAIZ / "estado" / "textos.json"
    salida.write_text(json.dumps({"fecha": str(hoy), "problemas": problemas}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return problemas


if __name__ == "__main__":
    main()
