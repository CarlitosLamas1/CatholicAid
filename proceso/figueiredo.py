#!/usr/bin/env python3
"""CatholicAid · Texto base del canal en portugués: Bíblia Sagrada del Padre Antônio Pereira de Figueiredo
(1778–1790, traducción católica de la Vulgata, dominio público).

Fuente digital: OCR de la edición de 1950 publicado en github.com/ronaldomelofz/abibliasagrada (web/data/livros/).
El OCR tiene errores (palabras partidas, versículos pegados, trozos de notas), así que este archivo es solo la
REFERENCIA: el vídeo en portugués usa siempre la versión revisada y modernizada (biblia/figueiredo/revisada/,
criterio en guias/revision-portugues.md). Aquí solo se quitan las notas, se separan versículos pegados y se
actualiza la ortografía de 1945 (êste -> este, tôda -> toda…).

Uso: python3 proceso/figueiredo.py <carpeta web/data/livros>   -> biblia/figueiredo/{mateo,marcos,lucas,juan}.json
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LIBROS = {"mateus": "mateo", "marcos": "marcos", "lucas": "lucas", "joao": "juan"}

# Acentos diferenciales del Formulario de 1943 suprimidos en 1971 (Brasil) / 1945 (Portugal).
ACENTOS = {"ê": "e", "ô": "o", "Ê": "E", "Ô": "O"}
CONSERVAR = {"você", "vocês", "três", "português", "francês", "inglês", "mês", "fêz", "pôr", "pôde", "têm", "vêm",
             "crêem", "lêem", "dêem", "vêem", "ê", "avô", "avôs", "bisavô", "pôs", "compôs", "propôs", "dispôs", "supôs",
             "após", "nós", "vós", "pés", "fé", "sê", "lê", "vê", "dê", "crê", "Jesus", "José", "Moisés"}
OCR = [(r"£les?", lambda m: "E" + m.group(0)[1:]), (r"\bfle\b", lambda m: "Ele"), (r"\bête\b", lambda m: "este"),
       (r"\bEilo\b", lambda m: "Ei-lo"), (r"[«»|£]", lambda m: ""), (r"\s+([.,;:?!])", lambda m: m.group(1)),
       (r"([.,;:?!])\1+", lambda m: m.group(1)), (r"\s{2,}", lambda m: " ")]


def ortografia(t):
    def palabra(m):
        w = m.group(0)
        if w in CONSERVAR or w.lower() in CONSERVAR or w[-1] in "êôÊÔ" or (len(w) > 2 and w[-2:] in ("ês", "ôs")):
            return w  # oxítonas (você, avô, três) conservan el acento
        return "".join(ACENTOS.get(c, c) for c in w)
    t = re.sub(r"\w+", palabra, t)
    for patron, f in OCR:
        t = re.sub(patron, f, t)
    return t.strip(" -")


def separar(versiculos):
    """Versículos pegados por el OCR («… homens. ; 3 Havia…»): se separan cuando aparece el número que falta."""
    salida = {}
    numeros = {v["n"] for v in versiculos}
    for v in versiculos:
        texto, n = v["t"], v["n"]
        while True:
            m = re.search(rf"[\s|;:.,]+({n + 1})\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕ£])", texto)
            if not m or (n + 1) in numeros:
                break
            salida[str(n)] = texto[:m.start()]
            texto, n = texto[m.end():], n + 1
        salida[str(n)] = texto
    return salida


def main():
    origen = Path(sys.argv[1])
    destino = RAIZ / "biblia" / "figueiredo"
    destino.mkdir(parents=True, exist_ok=True)
    for archivo, libro in LIBROS.items():
        datos = json.loads((origen / f"{archivo}.json").read_text(encoding="utf-8"))
        libro_json = {}
        for cap in datos["capitulos"]:
            libro_json[str(cap["n"])] = {k: ortografia(t) for k, t in separar(cap["versiculos"]).items()}
        (destino / f"{libro}.json").write_text(json.dumps(libro_json, ensure_ascii=False, indent=1), encoding="utf-8")
        print(libro, sum(len(c) for c in libro_json.values()), "versículos")


if __name__ == "__main__":
    main()
