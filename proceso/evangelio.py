#!/usr/bin/env python3
"""CatholicAid · Evangelio del día en vídeo.

Pasos: 1) Evangelio (Vatican News) -> 2) guion por personajes (Gemini, validando que el
texto quede idéntico; si no, reglas por comillas) -> 3) voces (Gemini TTS; si falla, Edge TTS)
-> 4) cuadros de James Tissot (Wikimedia Commons) -> 5) vídeo vertical 1080x1920 (FFmpeg)
-> 6) subida a YouTube.

Uso: python3 proceso/evangelio.py [--fecha AAAA-MM-DD] [--modo prueba|diario] [--no-subir]
"""
import argparse
import base64
import datetime as dt
import html
import json
import os
import random
import re
import shutil
import subprocess
import time
import urllib.error
import unicodedata
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
CFG = json.loads((RAIZ / "config" / "personajes.json").read_text(encoding="utf-8"))
PJ = CFG["personajes"]
MADRID = ZoneInfo("Europe/Madrid")
GEMINI = "https://generativelanguage.googleapis.com/v1beta/"
UA = "CatholicAid/1.0 (+https://github.com/CarlitosLamas1/CatholicAid)"
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
W, H, FPS, HZ = 1080, 1920, 30, 24000
COMILLAS = "“”‘’\"«»"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DIAS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
            "novembro", "dezembro"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]

# Idioma del vídeo: «es» (canal CatolicAid, por defecto) o «en» (canal CatolicAid English). Todo lo del inglés
# se aplica solo con --idioma en; con «es» el proceso es el de siempre.
IDIOMA = "es"
TXT = {
    "es": {"leer": "Lee en voz alta, con {estilo}, este texto:\n\n{texto}",
           "leer_varios": "Lee en voz alta, con {estilo}, los siguientes párrafos, en este orden. Entre un párrafo "
                          "y el siguiente haz siempre una pausa clara de un segundo:\n\n",
           "palabra": "Palabra del Señor.",
           "cierre": "Síguenos para escuchar\\Nel Evangelio cada día"},
    "en": {"leer": "Read aloud, with {estilo}, the following text:\n\n{texto}",
           "leer_varios": "Read aloud, with {estilo}, the following paragraphs, in this order. Between one paragraph "
                          "and the next always make a clear one-second pause:\n\n",
           "palabra": "The Gospel of the Lord.",
           "cierre": "Follow us to hear\\Nthe Gospel every day"},
    # Portugués (preparado, aún sin canal: guias/portugues.md). No se usa hasta activar config «pt».
    "pt": {"leer": "Leia em voz alta, com {estilo}, o seguinte texto:\n\n{texto}",
           "leer_varios": "Leia em voz alta, com {estilo}, os parágrafos seguintes, nesta ordem. Entre um parágrafo "
                          "e o seguinte faça sempre uma pausa clara de um segundo:\n\n",
           "palabra": "Palavra da Salvação.",
           "cierre": "Siga-nos para ouvir\\No Evangelho todos os dias"},
}
SUFIJO = {"es": "", "en": "-en", "pt": "-pt"}  # episodios/AAAA-MM-DD-en.json, revisiones/AAAA-MM-DD-en.json, salida/AAAA-MM-DD-en/


def txt(clave):
    return TXT[IDIOMA][clave]


def aplicar_idioma(idioma):
    """Ajustes del idioma (config «en»: nombres, estilos de voz, voces de prueba). Las voces de Gemini por personaje
    son las mismas salvo que la config diga otra cosa."""
    global IDIOMA
    IDIOMA = idioma
    if idioma == "es":
        return
    o = CFG.get(idioma, {})
    acento = o.get("acento", "clear neutral American accent")
    for k, v in o.get("personajes", {}).items():
        if k in PJ:
            PJ[k] = {**PJ[k], **v}
    for k, v in o.get("narradores", {}).items():
        CFG["narradores"][k] = {**CFG["narradores"].get(k, {}), **v}
    for d in list(PJ.values()) + list(CFG["narradores"].values()):
        if "estilo" in d:
            d["estilo"] = d["estilo"].replace("{acento}", acento)
    CFG["hora_publicacion"] = CFG.get(f"hora_publicacion_{idioma}", CFG.get("hora_publicacion", 7))


def a_hora(v):
    """hora_publicacion de config: «00:05» (o un número de hora, como antes) -> dt.time."""
    if isinstance(v, str) and ":" in v:
        h, m = v.split(":")[:2]
        return dt.time(int(h), int(m))
    return dt.time(int(v))


def hora_pub(idioma="es"):
    return a_hora(CFG.get("hora_publicacion" if idioma == "es" else f"hora_publicacion_{idioma}",
                          CFG.get("hora_publicacion", 7)))


def fecha_larga(fecha):
    if IDIOMA == "en":
        return f"{DAYS[fecha.weekday()]}, {MONTHS[fecha.month - 1]} {fecha.day}"
    if IDIOMA == "pt":
        return f"{DIAS_PT[fecha.weekday()]}, {fecha.day} de {MESES_PT[fecha.month - 1]}"
    return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"


def log(*a):
    print(*a, flush=True)


def http(url, data=None, headers=None, method=None, timeout=120, raw=False):
    headers = {"User-Agent": UA, **(headers or {})}
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        cuerpo = r.read()
        return (r, cuerpo) if raw else json.loads(cuerpo)


def ffmpeg(*args, cwd=None):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True, cwd=cwd)


def hablado(t):
    t = re.sub(r"(?<=\w)’(?=\w)", "\0", t)  # apóstrofo inglés (don’t, Father’s): no es una comilla
    return "".join(c for c in t if c not in COMILLAS).replace("\0", "’").strip()


def normalizar(t):
    return "".join(c for c in t if not c.isspace() and c not in COMILLAS)


# ---------- Gemini ----------

CUPO_AGOTADO = set()  # modelos de Gemini que han dado 429 (cupo gratuito agotado) en esta tirada
MODELOS_VOZ_USADOS = set()
CACHE = None  # carpeta de caché (--cache): guion, frase/reflexión y voces ya hechas no se vuelven a pedir


def cache_leer(nombre):
    if CACHE and (CACHE / nombre).exists():
        log(f"   (caché) {nombre}")
        return json.loads((CACHE / nombre).read_text(encoding="utf-8"))
    return None


def cache_guardar(nombre, datos):
    if CACHE:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / nombre).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def huella(*partes):
    import hashlib
    return hashlib.sha1("\n".join(map(str, partes)).encode()).hexdigest()[:16]


def clave_gemini():
    return {"x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()}


def gemini(modelo, cuerpo, intentos=3, clave=None):
    for i in range(intentos):
        try:
            cab = {"x-goog-api-key": clave} if clave else clave_gemini()
            return http(f"{GEMINI}models/{modelo}:generateContent", cuerpo, cab, timeout=300)
        except urllib.error.HTTPError as e:
            log(f"   Gemini {modelo} -> {e.code}: {e.read().decode(errors='replace')[:500]}")
            if e.code == 429:
                CUPO_AGOTADO.add(modelo)
            if e.code in (500, 502, 503, 504) and i < intentos - 1:
                time.sleep(15 * (i + 1))
                continue
            raise


def modelos_texto():
    preferidos = CFG["modelos_texto"]
    try:
        d = http(f"{GEMINI}models?pageSize=200", headers=clave_gemini())
        nombres = [m["name"].split("/")[-1] for m in d.get("models", [])
                   if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception as e:
        log(f"   No pude listar modelos: {e}")
        return preferidos
    extra = sorted((n for n in nombres if "flash" in n and n not in preferidos  # omni/pro: sin cuota gratuita
                    and not re.search(r"tts|image|live|audio|embed|exp|omni|pro|lite", n)), reverse=True)
    return [m for m in preferidos if m in nombres] + extra[:3]


# ---------- 1. Evangelio ----------

def limpiar(t):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def obtener_evangelio(fecha):
    url = f"https://www.vaticannews.va/es/evangelio-de-hoy/{fecha:%Y/%m/%d}.html"
    pagina = http(url, raw=True)[1].decode("utf-8", "replace")
    seccion = next((s for s in re.findall(r"<section[^>]*section--evidence[\s\S]*?</section>", pagina)
                    if "Evangelio del D" in s), None)
    if not seccion:
        raise RuntimeError(f"No encuentro el Evangelio en {url}")
    parrafos = [p for p in (limpiar(x) for x in re.findall(r"<p[^>]*>([\s\S]*?)</p>", seccion)) if p]
    titulo = next((p for p in parrafos
                   if re.match(r"(Lectura|Comienzo|Conclusión|Final) del santo evangelio", p, re.I)), "")
    cita = next((p for p in parrafos
                 if len(p) < 60 and re.match(r"^[1-3]?\s?[A-ZÁÉÍÓÚ][a-záéíóú]+\s+\d+\s*,", p)), "")
    cuerpo = [p for p in parrafos if p not in (titulo, cita)]
    if not cuerpo or not cita:
        raise RuntimeError(f"Formato inesperado en {url}: {parrafos[:3]}")
    titulo = (titulo or "Lectura del santo evangelio").rstrip(". ") + "."
    return {"url": url, "titulo": titulo, "cita": cita, "texto": "\n".join(cuerpo)}


# ---------- 1b. Texto de Torres Amat (dominio público) ----------

NOMBRES = {"Jesús", "Jesus", "Pedro", "Simón", "Juan", "María", "Dios", "Jerusalén", "Galilea", "Herodes", "Pilato"}
ORTOGRAFIA = {
    "Jesus": "Jesús", "muger": "mujer", "mugeres": "mujeres", "entónces": "entonces", "Entónces": "Entonces",
    "despues": "después", "Despues": "Después", "todavia": "todavía", "léjos": "lejos", "oidos": "oídos",
    "habia": "había", "habian": "habían", "tenia": "tenía", "tenian": "tenían", "decia": "decía", "Decia": "Decía",
    "dia": "día", "dias": "días", "fé": "fe", "tambien": "también", "Jerusalem": "Jerusalén", "ácia": "hacia",
    "extrangero": "extranjero", "ageno": "ajeno", "comun": "común", "habeis": "habéis", "sabeis": "sabéis",
    "podeis": "podéis", "seais": "seáis", "mia": "mía", "tí": "ti", "Regocijáos": "Regocijaos",
    "Alegráos": "Alegraos", "drachma": "dracma", "mostráos": "mostraos", "querais": "queráis", "vayais": "vayáis",
    "compreis": "compréis", "administracion": "administración", "obligacion": "obligación",
    "poblacion": "población", "Ningun": "Ningún", "vendeis": "vendéis", "vendian": "vendían"}


def ortografia(t):
    """Actualiza la ortografía de 1836: á/ó/é/ú sueltas y palabras frecuentes."""
    t = re.sub(r"\s+([.,;:?!])", r"\1", t)
    t = re.sub(r"(?<!\w)([áóéú])(?!\w)", lambda m: "aoeu"["áóéú".index(m.group(1))], t)
    return re.sub(r"\w+", lambda m: ORTOGRAFIA.get(m.group(0), m.group(0)), t)


def cargar_libro(libro):
    """Evangelio de Torres Amat (1836) desde Wikisource; se guarda en biblia/torres-amat/."""
    ruta = RAIZ / "biblia" / "torres-amat" / f"{libro.lower()}.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    log(f"   Descargando {libro} (Torres Amat, 1836) de Wikisource")
    url = ("https://es.wikisource.org/w/api.php?action=parse&format=json&formatversion=2&prop=text&page="
           + urllib.parse.quote(f"La Sagrada Biblia (XIII)/{libro}"))
    h = http(url)["parse"]["text"]
    h = re.sub(r'<sup[^>]*class="reference"[\s\S]*?</sup>', "", h)
    h = re.sub(r'<ol class="references"[\s\S]*?</ol>', "", h)
    h = re.sub(r"<br\s*/?>|</p>|</div>|</dd>|</li>", "\n", h)
    texto = html.unescape(re.sub(r"<[^>]+>", "", h)).replace("\xa0", " ")
    romanos = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    datos, cap, ver = {}, 0, None
    for linea in texto.split("\n"):
        linea = linea.strip()
        if not linea:
            continue
        m = re.match(r"CAP[IÍ]TULO\s+([IVXLC]+)", linea)
        if m:
            d = [romanos[c] for c in m.group(1)]
            cap = sum(-x if i + 1 < len(d) and x < d[i + 1] else x for i, x in enumerate(d))
            datos[str(cap)], ver = {}, None
            continue
        m = re.match(r"^[^\w¿¡]*(\d+)\s+(.+)", linea)
        if cap and m:
            ver = m.group(1)
            datos[str(cap)][ver] = m.group(2).strip()
        elif cap and ver:
            datos[str(cap)][ver] += " " + linea
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return datos


# ---------- 1c. World English Bible, edición católica (dominio público) · canal en inglés ----------

WEB_URL = "https://eBible.org/Scriptures/eng-web-c_vpl.zip"  # «World English Bible (Catholic)», eBible.org
LIBROS_WEB = {"Mateo": "MAT|MATT?", "Marcos": "MRK|MAR|MARK?", "Lucas": "LUK|LUKE?", "Juan": "JHN|JOH|JOHN?"}  # códigos posibles
LIBROS_EN = {"Mateo": "Matthew", "Marcos": "Mark", "Lucas": "Luke", "Juan": "John"}


def cargar_web(libro):
    """Evangelio de la World English Bible (Catholic) desde eBible.org; se guarda en biblia/web/<libro>.json."""
    ruta = RAIZ / "biblia" / "web" / f"{libro.lower()}.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    import io
    import zipfile
    log(f"   Descargando la World English Bible (Catholic) de {WEB_URL}")
    z = zipfile.ZipFile(io.BytesIO(http(WEB_URL, raw=True, timeout=300)[1]))
    lineas = "\n".join(z.read(n).decode("utf-8-sig", "replace") for n in z.namelist() if n.lower().endswith(".txt"))
    for nombre, codigo in LIBROS_WEB.items():
        datos = {}
        for m in re.finditer(rf"^(?:{codigo})\.? (\d+):(\d+) (.*)$", lineas, re.M | re.I):
            texto = re.sub(r"\s+", " ", m.group(3).replace("¶", " ")).strip()
            datos.setdefault(m.group(1), {})[m.group(2)] = texto
        if datos:
            destino = RAIZ / "biblia" / "web" / f"{nombre.lower()}.json"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    if not ruta.exists():
        codigos = sorted(set(re.findall(r"^([1-3]?[A-Za-z]{2,4})\.? \d+:\d+ ", lineas, re.M)))
        raise RuntimeError(f"No encuentro {libro} en la World English Bible (libros: {' '.join(codigos)[:300]})")
    return json.loads(ruta.read_text(encoding="utf-8"))


def cita_en(cita):
    """'Lucas 16, 1-8' -> 'Luke 16:1-8' · 'Juan 20, 1-2. 11-18' -> 'John 20:1-2, 11-18'"""
    libro, resto = cita.split(None, 1)
    resto = re.sub(r"(\d+),\s*(\d)", r"\1:\2", resto)
    resto = re.sub(r"\.\s*", ", ", resto).strip(", ")
    return f"{LIBROS_EN.get(libro, libro)} {resto}"


def versiculos(cita, datos):
    """'Lucas 15, 1-10' / 'Juan 20, 1-2. 11-18' / 'Mateo 26, 14-27, 66' -> [(cap, ver), ...]"""
    resto = re.sub(r"^\s*[1-3]?\s?\w+\s+", "", cita).replace("—", "-").replace("–", "-")
    lista, cap = [], None
    for parte in re.split(r"[.;]\s*", resto):
        parte = re.sub(r"(\d)[a-d]\b", r"\1", parte.strip())
        if not parte:
            continue
        if re.match(r"^\d+\s*,", parte):
            c, parte = parte.split(",", 1)
            cap, parte = int(c), parte.strip()
        a, _, b = parte.partition("-")
        if not b:
            lista.append((cap, int(a)))
            continue
        c2, v2 = (int(x) for x in b.split(",")) if "," in b else (cap, int(b))
        c, v = cap, int(a)
        while (c, v) <= (c2, v2):
            lista.append((c, v))
            ultimo = max((int(k) for k in datos.get(str(c), {})), default=0)
            c, v = (c + 1, 1) if v >= ultimo else (c, v + 1)
        cap = c2
    return lista


NOMBRES_EN = {"Jesus", "Peter", "Simon", "John", "Mary", "God", "Jerusalem", "Galilee", "Herod", "Pilate", "I",
              "Martha", "Thomas", "Philip", "Andrew", "James", "Judas", "Zacchaeus", "Lazarus", "Elizabeth"}


def texto_torres_amat(cita):
    return texto_biblia(cita, cargar_libro, RAIZ / "biblia" / "revisada", ortografia, "En aquel tiempo,", NOMBRES,
                        "Torres Amat (1836)")


def texto_web(cita):
    """Canal en inglés: la misma cita (en español) con el texto de la World English Bible (Catholic)."""
    texto, fuente = texto_biblia(cita, cargar_web, RAIZ / "biblia" / "web" / "revisada", lambda t: t,
                                 "At that time,", NOMBRES_EN, "World English Bible, Catholic Edition (public domain)",
                                 saltar_ausentes=True, comillas=equilibrar_comillas)
    return texto, fuente.replace("versión revisada por CatholicAid", "revised by CatolicAid").replace(
        "revisión parcial", "partly revised").replace("ortografía actualizada", "original text")


NOMBRES_PT = {"Jesus", "Pedro", "Simão", "João", "Maria", "Deus", "Jerusalém", "Galileia", "Herodes", "Pilatos", "Zaqueu",
              "Marta", "Tomé", "Filipe", "André", "Tiago", "Judas", "Lázaro", "Isabel"}


def cargar_figueiredo(libro):
    """Canal en portugués: Figueiredo (dominio público) ya extraído en biblia/figueiredo/ (proceso/figueiredo.py)."""
    return json.loads((RAIZ / "biblia" / "figueiredo" / f"{libro.lower()}.json").read_text(encoding="utf-8"))


def texto_figueiredo(cita):
    """Portugués: SOLO con la versión revisada y modernizada completa (el OCR original tiene errores)."""
    texto, fuente = texto_biblia(cita, cargar_figueiredo, RAIZ / "biblia" / "figueiredo" / "revisada", lambda t: t,
                                 "Naquele tempo,", NOMBRES_PT, "Bíblia do Pe. Antônio Pereira de Figueiredo (domínio público)")
    if "versión revisada" not in fuente:
        raise ValueError(f"{cita}: falta la revisión en portugués (biblia/figueiredo/revisada/)")
    return texto, "Bíblia do Pe. Antônio Pereira de Figueiredo (domínio público), revisada e atualizada por CatolicAid"


def equilibrar_comillas(texto):
    """Solo signos, nunca palabras: la WEB abre “ en cada párrafo de un discurso largo sin cerrarlo antes, y un pasaje
    puede empezar o acabar en mitad de un discurso. Se quitan las “ repetidas y se abre/cierra la que falte."""
    salida, abierta, falta_abrir = [], False, False
    for c in texto:
        if c == "“":
            if abierta:
                continue
            abierta = True
        elif c == "”":
            if not abierta:
                if any(x in "“”" for x in salida):
                    continue  # cierre suelto en mitad: sobra
                falta_abrir = True
            abierta = False
        salida.append(c)
    t = "".join(salida)
    if falta_abrir:
        t = "“" + t
    if abierta:
        t = t.rstrip() + "”"
    return t


def texto_biblia(cita, cargar, carpeta_rev, arreglar, inicio_defecto, nombres, nombre, saltar_ausentes=False,
                 comillas=None):
    libro = cita.split()[0]
    datos = cargar(libro)
    ruta_rev = carpeta_rev / f"{libro.lower()}.json"
    rev = json.loads(ruta_rev.read_text(encoding="utf-8")) if ruta_rev.exists() else {}
    vs = versiculos(cita, datos)
    partes, faltan, revisados = [], [], 0
    for c, v in vs:
        r = rev.get(str(c), {}).get(str(v))
        o = datos.get(str(c), {}).get(str(v))
        if r:
            partes.append(r)
            revisados += 1
        elif o:
            partes.append(arreglar(o))
        elif saltar_ausentes and any(int(k) > v for k in datos.get(str(c), {})):
            log(f"   {c},{v}: no está en esta Biblia (variante textual omitida); se salta")
        else:
            faltan.append(f"{c},{v}")
    if not vs or faltan:
        raise ValueError(f"faltan versículos: {faltan or cita}")
    texto = " ".join(partes)
    if comillas:
        texto = comillas(texto)
    inicio = rev.get("_inicios", {}).get(f"{vs[0][0]}:{vs[0][1]}")
    if inicio is None:
        inicio = "" if vs[0] == (1, 1) else inicio_defecto
    if inicio:
        primera = texto.split()[0].strip("¿¡“«")
        if inicio.endswith(",") and primera not in nombres:
            texto = texto[0].lower() + texto[1:]
        texto = f"{inicio} {texto}"
    if revisados == len(vs):
        fuente = f"{nombre}, versión revisada por CatholicAid"
    elif revisados:
        fuente = f"{nombre}, revisión parcial"
    else:
        fuente = f"{nombre}, ortografía actualizada"
    return texto, fuente


# ---------- 2. Guion ----------

def guion_gemini(texto, clips, escenas_fijas=""):
    """escenas_fijas (canal en inglés): las escenas del vídeo en español, para reutilizar sus imágenes."""
    clave = f"guion_{huella(texto, escenas_fijas, sorted(clips))}.json"
    previo = cache_leer(clave)
    if previo:
        return previo
    lista = "\n".join(f"- {k}: {v['descripcion']}" for k, v in PJ.items())
    biblioteca = ""
    if clips:
        biblioteca = ("\n5. Para cada escena elige en \"clip\" el vídeo de la biblioteca que mejor muestre lo que se narra"
                      " (o \"ninguno\" si ninguno encaja):\n" + "\n".join(f"- {k}: {v}" for k, v in clips.items()))
    prompt = f"""Prepara una lectura dramatizada del Evangelio con varias voces.

PERSONAJES (usa solo estas claves):
{lista}

REGLAS:
1. Divide el texto en fragmentos consecutivos. Copia cada fragmento EXACTAMENTE igual que en el original: no añadas, quites ni cambies ninguna palabra ni signo. Unidos en orden, los fragmentos deben reproducir el texto completo.
2. Las palabras en estilo directo (entre comillas “ ”) van en un fragmento propio, asignado a quien las dice. Si alguien cita a otro dentro de su discurso (comillas ‘ ’), sigue hablando el mismo personaje. Todo lo demás es del narrador.
3. Si habla un personaje secundario que no está en la lista, usa hombre, mujer o multitud.
4. Agrupa el relato en 3 a 5 escenas visuales (cambia de escena cuando cambie lo que se ve). En cada fragmento indica su escena (1, 2, ...). Para cada escena da:
   - "busqueda": 1 a 3 palabras en inglés para encontrar un cuadro clásico de esa escena (ej.: "good shepherd", "Pharisees").
   - "descripcion": en inglés, 1 o 2 frases que describan la imagen a pintar: quién aparece, qué hace, dónde y con qué emoción. Debe mostrar lo que narra el Evangelio en ese momento, de forma bella, tierna e íntima (nunca violenta). Muestra exactamente a los personajes y la acción de esa escena: si Jesús cuenta una parábola, pinta la escena de la parábola con sus personajes (p. ej. el administrador ante los deudores, el sembrador en el campo), nunca a alguien ajeno al relato ni a una persona leyendo.
   - "personajes": claves de los personajes que se ven en la imagen (por ejemplo ["jesus"]).
   - "estilo": "oleo" para escenas de interior, noche o recogimiento; "acuarela" para escenas al aire libre y luminosas.{biblioteca}{escenas_fijas}

TEXTO:
{texto}"""
    esquema = {"type": "OBJECT", "properties": {
        "fragmentos": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "personaje": {"type": "STRING", "enum": list(PJ)},
            "texto": {"type": "STRING"},
            "escena": {"type": "INTEGER"}}, "required": ["personaje", "texto", "escena"]}},
        "escenas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "numero": {"type": "INTEGER"}, "busqueda": {"type": "STRING"},
            "descripcion": {"type": "STRING"},
            "personajes": {"type": "ARRAY", "items": {"type": "STRING", "enum": list(PJ)}},
            "estilo": {"type": "STRING", "enum": ["oleo", "acuarela"]},
            "clip": {"type": "STRING", "enum": list(clips) + ["ninguno"]}},
            "required": ["numero", "busqueda"]}}},
        "required": ["fragmentos", "escenas"]}
    for modelo in modelos_texto():
        try:
            r = gemini(modelo, {"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"responseMimeType": "application/json",
                                                     "responseSchema": esquema, "temperature": 0}})
            partes = r["candidates"][0]["content"]["parts"]
            g = json.loads(next(p["text"] for p in reversed(partes) if "text" in p))
            if normalizar("".join(f["texto"] for f in g["fragmentos"])) == normalizar(texto):
                g["origen"] = modelo
                log(f"   Guion de {modelo}: texto idéntico al original")
                cache_guardar(clave, g)
                return g
            log(f"   {modelo}: el guion no coincide con el texto original; se descarta")
        except Exception as e:
            log(f"   {modelo}: falló ({e})")
    return None


def hablante(narracion):
    mejor, pos = "jesus", -1
    for k, v in PJ.items():
        for a in v.get("alias", []):
            for m in re.finditer(re.escape(a), narracion):
                antes = narracion[:m.start()].rstrip().lower()
                if re.search(r"\b(a|al|a los|a las|a sus|a su|con|de|to|to the|to his|with|of)$", antes):
                    continue  # es a quien se habla, no quien habla
                if m.start() > pos:
                    mejor, pos = k, m.start()
    return mejor


def guion_reglas(texto):
    frs, previo = [], ""
    for trozo in re.split(r"(“[^”]*”)", texto):
        if not trozo.strip():
            continue
        if trozo.startswith("“"):
            frs.append({"personaje": hablante(previo), "texto": trozo})
        else:
            frs.append({"personaje": "narrador", "texto": trozo})
            previo = trozo
    n = min(3, max(1, len(frs) // 3))
    for i, f in enumerate(frs):
        f["escena"] = 1 + i * n // len(frs)
    gen = CFG["busquedas_genericas"]
    return {"fragmentos": frs, "origen": "reglas",
            "escenas": [{"numero": i + 1, "busqueda": gen[i % len(gen)]} for i in range(n)]}


def espacios(t):
    return " ".join(t.split())


INICIOS_DEBILES = {"no", "sí", "si", "pero", "mas", "y", "e", "o", "porque", "pues", "entonces", "así", "ahora", "ay", "oh",
                   "yes", "but", "and", "or", "for", "so", "then", "now", "nay", "truly"}


def frase_valida(frase, pregunta=True):
    """Frase clave que se entiende sola: 4–12 palabras, sin «…», sin empezar con una muletilla corta («No, por cierto»)."""
    ws = re.findall(r"\w+", frase)
    if not 4 <= len(ws) <= 12 or "…" in frase:
        return False
    if ws[0].lower() in INICIOS_DEBILES and len(ws) < 7:
        return False
    return pregunta or not frase.rstrip().endswith("?")


CITA = r"‘(.*?)’(?!\w)"  # cita dentro del discurso (’ seguido de letra es un apóstrofo inglés, no un cierre)
ENSENANZA = re.compile(r"\b(os digo|te digo|en verdad|bienaventurad\w*|así también vosotros|amad|velad|vigilad|"
                       r"decid|venid|seguidme|no temáis|creed|perdonad|pedid|buscad|llamad|i tell you|most certainly|"
                       r"blessed|even so you|watch|love|come|follow|believe|forgive|ask|seek|knock|don’t be afraid)\b",
                       re.I)
NARRACION = re.compile(r"^(había|hubo|un hombre|una mujer|cierto|entonces|mientras|cuando|mas|five|ten|then|while|when|"
                       r"there was|a certain|now|afterward)\b", re.I)
MANDA_DECIR = re.compile(r"(decid|di|diréis|dirás|say|tell them|you shall say)\s*[:,]?\s*$", re.I)


def frase_de_reserva(frs, texto=""):
    """Si Gemini falla: una frase de Jesús que se entienda sola, NUNCA vacía ni cortada (copiada tal cual).
    Prefiere enseñanzas y mandatos («os digo», imperativos, «así también vosotros…», y lo que Jesús manda decir a los
    oyentes: «Somos siervos inútiles») frente a la narración de una parábola. Por escalones: cláusula de 4–12 palabras
    (3 si es lo que Jesús manda decir) → 3 palabras → la frase completa de Jesús más corta."""
    piezas = []  # (texto, es_lo_que_manda_decir)
    for f in frs:
        if f["personaje"] != "jesus":
            continue
        for m in re.finditer(CITA, f["texto"]):
            if MANDA_DECIR.search(f["texto"][:m.start()]):
                piezas.append((m.group(1), True))
        piezas.append((re.sub(CITA, " … ", f["texto"]), False))
    if not piezas and texto:
        piezas = [(texto, False)]
    candidatas = []
    for pieza, mandada in piezas:
        trozos = re.split(r"((?<=[.?!;:])\s+|\s*…\s*)", pieza)  # «…» = cita quitada: corta ahí
        for k, x in enumerate(trozos[::2]):
            sep = trozos[2 * k + 1] if 2 * k + 1 < len(trozos) else ""
            anuncia = x.rstrip().endswith(":") or "…" in sep  # introduce una cita («…, saying,»): se queda a medias
            x = espacios(hablado(x)).strip(" ,;:")
            ws = x.split() if re.search(r"\w", x) else []  # palabras reales (don’t cuenta como una)
            if not ws or "…" in x or anuncia:
                continue
            nota = 3 * bool(mandada or ENSENANZA.search(x)) - 3 * bool(NARRACION.search(x)) + (k == 0 and mandada)
            nota -= x[0].islower() + 2 * x.endswith("?")
            candidatas.append((x, len(ws), nota, mandada))

    def mejor(lista):
        return max(lista, key=lambda c: (c[2], -abs(c[1] - 8)))[0] if lista else ""

    debiles = INICIOS_DEBILES
    escalon1 = [c for c in candidatas if (3 if c[3] else 4) <= c[1] <= 12 and not c[0].endswith("?")
                and not (c[0].split()[0].lower().strip(",") in debiles and c[1] < 7)]
    escalon2 = [c for c in candidatas if c[1] == 3 and not c[0].endswith("?")
                and c[0].split()[0].lower().strip(",") not in debiles]
    largas = [c for c in candidatas if 13 <= c[1] <= 20 and c[2] > 0 and not c[0].endswith("?")]
    buenas = [c for c in escalon1 if c[2] >= 0]
    frase = mejor(buenas) or mejor(largas) or mejor(escalon1) or mejor(escalon2)  # enseñanza larga antes que narración
    if frase:
        return frase
    completas = [espacios(hablado(x)).strip(" ,;:") for p, _ in piezas for x in re.split(r"(?<=[.?!])\s+", p)
                 if "…" not in x and re.search(r"\w", x)]
    return min(completas, key=len) if completas else ""


def gancho_y_reflexion(frs, ev, fiable=True):
    """Gemini elige la frase clave (literal, de las palabras de Jesús) y escribe una reflexión breve.
    La frase se valida: tiene que estar tal cual en el texto. El Evangelio no se toca.
    fiable=False (reparto por reglas): no se sabe con certeza quién habla, así que sin Gemini no hay gancho."""
    jesus = [hablado(f["texto"]) for f in frs if f["personaje"] == "jesus"]
    fuente = jesus or [hablado(ev["texto"])]
    propias = [espacios(hablado(re.sub(CITA, " … ", f["texto"]))) for f in frs if f["personaje"] == "jesus"]
    if sum(len(re.findall(r"\w+", x)) for x in propias) >= 8:
        fuente = propias  # lo que dice Jesús con su voz, no los personajes de sus parábolas
    quien = "las palabras de Jesús" if jesus else "el texto"
    prompt = f"""Eres un sacerdote católico que prepara un vídeo breve con el Evangelio del día ({ev['cita']}).

1. "frase_clave": elige de {quien} (abajo) la frase más significativa y fácil de recordar para mostrarla en grande al
   principio del vídeo. Cópiala LITERALMENTE, palabra por palabra y con los mismos signos, sin comillas: puede ser una
   frase entera o una parte con sentido completo que se entienda sola (con su verbo), de 4 a 12 palabras. Prefiere una enseñanza o promesa de Jesús
   (no una pregunta suelta, ni una frase de transición, ni una frase que solo describe un detalle del relato o de la
   parábola y no se entiende fuera de él) y no cojas nada que contenga «…». MUY IMPORTANTE: tiene que entenderse
   sola, sin ningún contexto, por alguien que no ha oído la lectura.
2. "reflexion": 1 o 2 frases breves (máximo 35 palabras en total) para meditar después de la lectura; puede terminar
   con una pregunta. Tono cálido y cercano, de tú, en español de España. Fiel a la doctrina de la Iglesia católica y
   al sentido de esta lectura. No cites ni inventes palabras de Jesús, no uses comillas ni emojis, no hables de
   política ni de temas polémicos.

{quien.upper()}:
{chr(10).join(fuente)}

LECTURA COMPLETA (contexto):
{hablado(ev['texto'])}"""
    if IDIOMA == "en":
        quien = "the words of Jesus" if jesus else "the text"
        prompt = f"""You are a Catholic priest preparing a short video with the Gospel of the day ({ev['cita']}).

1. "frase_clave": choose from {quien} (below) the most meaningful and memorable sentence, to show it large at the
   beginning of the video. Copy it LITERALLY, word for word and with the same punctuation, without quotation marks:
   it can be a whole sentence or a part with complete meaning that stands on its own (with its verb), 4 to 12 words. Prefer a teaching or promise of Jesus
   (not a lone question, nor a transition phrase, nor a sentence that only describes a detail of the story or parable
   and makes no sense out of context) and do not take anything containing «…». VERY IMPORTANT: it must make sense
   on its own, with no context at all, to someone who has not heard the reading.
2. "reflexion": 1 or 2 short sentences (35 words at most in total) to meditate on after the reading; it may end
   with a question. Warm and close tone, addressing the viewer as "you", in clear American English. Faithful to the
   teaching of the Catholic Church and to the meaning of this reading. Do not quote or invent words of Jesus, do not
   use quotation marks or emojis, do not talk about politics or controversial topics.

{quien.upper()}:
{chr(10).join(fuente)}

FULL READING (context):
{hablado(ev['texto'])}"""
    if IDIOMA == "pt":
        quien = "as palavras de Jesus" if jesus else "o texto"
        prompt = f"""Você é um sacerdote católico que prepara um vídeo curto com o Evangelho do dia ({ev['cita']}).

1. "frase_clave": escolha d{quien} (abaixo) a frase mais significativa e fácil de lembrar, para mostrá-la em grande no
   início do vídeo. Copie-a LITERALMENTE, palavra por palavra e com a mesma pontuação, sem aspas: pode ser uma frase
   inteira ou uma parte com sentido completo que se entenda sozinha (com o seu verbo), de 4 a 12 palavras. Prefira um
   ensinamento ou promessa de Jesus (não uma pergunta solta, nem uma frase de transição, nem uma frase que só descreve
   um detalhe do relato ou da parábola) e não use nada que contenha «…». MUITO IMPORTANTE: tem de se entender
   sozinha, sem nenhum contexto, por alguém que não ouviu a leitura.
2. "reflexion": 1 ou 2 frases breves (no máximo 35 palavras no total) para meditar depois da leitura; pode terminar
   com uma pergunta. Tom caloroso e próximo, tratando o espectador por «você», em português do Brasil. Fiel à
   doutrina da Igreja Católica e ao sentido desta leitura. Não cite nem invente palavras de Jesus, não use aspas nem
   emojis, não fale de política nem de temas polêmicos.

{quien.upper()}:
{chr(10).join(fuente)}

LEITURA COMPLETA (contexto):
{hablado(ev['texto'])}"""
    if IDIOMA != "es" and ev.get("frase_es"):
        # Coherencia entre canales: la misma frase (en esta traducción) y la misma reflexión que el vídeo en español.
        lengua = {"en": "American English", "pt": "Brazilian Portuguese"}.get(IDIOMA, IDIOMA)
        prompt += (f"\n\nIMPORTANT — consistency with the Spanish video of the same day, which uses:\n"
                   f"- frase_clave: «{ev['frase_es']}»\n"
                   + (f"- reflexion: «{ev['reflexion_es']}»\n" if ev.get("reflexion_es") else "") +
                   f"For \"frase_clave\", choose the SAME passage (the same words of the same verse) as it appears in the "
                   f"text above, copied LITERALLY from it (same length and cut as far as possible). For \"reflexion\", "
                   f"translate the Spanish reflection faithfully and naturally into {lengua} (same meaning, same question).")
    clave = f"gancho_{huella(prompt)}.json"
    previo = cache_leer(clave)
    if previo:
        return tuple(previo)
    esquema = {"type": "OBJECT", "properties": {"frase_clave": {"type": "STRING"}, "reflexion": {"type": "STRING"}},
               "required": ["frase_clave", "reflexion"]}
    base = [espacios(s) for s in fuente]
    frase_ok, reflexion_ok = "", ""
    reserva = [m for m in CFG.get("comentarios", {}).get("modelos", [])]  # lite: último recurso para no quedarse sin reflexión
    modelos = modelos_texto()
    for modelo in modelos + [m for m in reserva if m not in modelos]:
        if frase_ok and reflexion_ok:
            break
        try:
            r = gemini(modelo, {"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"responseMimeType": "application/json",
                                                     "responseSchema": esquema, "temperature": 0.4}})
            partes = r["candidates"][0]["content"]["parts"]
            d = json.loads(next(p["text"] for p in reversed(partes) if "text" in p))
            frase = espacios(hablado(d.get("frase_clave", ""))).strip(" ,;:")
            reflexion = espacios(hablado(d.get("reflexion", "")))
            anuncia = any(re.search(re.escape(frase) + r"\s*:", s) for s in base)  # «…, decid:» se queda a medias
            if not frase_ok and frase and frase_valida(frase) and not anuncia and any(frase in s for s in base):
                frase_ok = frase
            elif not frase_ok:
                log(f"   {modelo}: la frase clave no es literal o no se entiende sola ({frase[:60]}); se descarta")
            if not reflexion_ok and reflexion and len(reflexion.split()) <= 45:
                reflexion_ok = reflexion
            elif not reflexion_ok:
                log(f"   {modelo}: reflexión vacía o demasiado larga; se descarta")
        except Exception as e:
            log(f"   {modelo}: gancho/reflexión falló ({e})")
    if frase_ok and reflexion_ok:
        cache_guardar(clave, [frase_ok, reflexion_ok])
    if not frase_ok and fiable:
        frase_ok = frase_de_reserva(frs, hablado(ev["texto"]))
    return frase_ok, reflexion_ok


def preparar_fragmentos(g, ev):
    frs = []
    for f in g["fragmentos"]:
        t = f["texto"].strip()
        if not t:
            continue
        if not re.search(r"\w", t):
            if frs:
                frs[-1]["texto"] += t
            continue
        p = f["personaje"] if f["personaje"] in PJ else "hombre"
        e = int(f.get("escena") or 1)
        if frs and frs[-1]["personaje"] == p and frs[-1]["escena"] == e:
            frs[-1]["texto"] += " " + t
            continue
        frs.append({"personaje": p, "texto": t, "escena": e})
    frs.insert(0, {"personaje": "narrador", "texto": ev["titulo"], "escena": frs[0]["escena"]})
    frs.append({"personaje": "narrador", "texto": txt("palabra"), "escena": frs[-1]["escena"], "palabra": True})
    return frs


# ---------- 3. Voces ----------

def a_wav_estandar(origen, destino, tempo=1.0):
    filtro = ["-filter:a", f"atempo={tempo}"] if abs(tempo - 1.0) > 0.001 else []
    ffmpeg("-i", origen, *filtro, "-ar", HZ, "-ac", 1, "-sample_fmt", "s16", destino)


def lotes_gemini(frs):
    """Una petición por personaje: fragmentos seguidos del mismo personaje van juntos, nunca dos voces a la vez."""
    lotes = []
    for i, f in enumerate(frs):
        if lotes and frs[lotes[-1][-1]]["personaje"] == f["personaje"]:
            lotes[-1].append(i)
        else:
            lotes.append([i])
    return lotes


def voz_gemini(p, texto, destino):
    """Graba un texto con la voz fija del personaje p. Clave gratuita; si se agota el cupo, la de pago (misma voz)."""
    cuerpo = {"contents": [{"parts": [{"text": texto}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                  "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": p["voz_gemini"]}}}}}
    # Español: modelo_voz (como siempre). Inglés: sus propios modelos de voz (config en.modelos_voz), cada uno con su
    # cupo gratuito, para no gastar nunca el cupo de voz del español; si uno se agota, el siguiente (misma voz).
    modelos = CFG.get(IDIOMA, {}).get("modelos_voz") if IDIOMA != "es" else None
    modelos = [m for m in (modelos or [CFG["modelo_voz"]]) if m not in CUPO_AGOTADO] or [CFG["modelo_voz"]]
    r = None
    pago = os.environ.get("GEMINI_API_KEY_IMAGENES", "").strip()
    if IDIOMA != "es" and CFG.get(IDIOMA, {}).get("voz_de_pago"):
        # Portugués (decisión de Carlos, 13/11/2026): voces SIEMPRE con la clave de pago (proyecto de pago, cupo propio),
        # para no tocar nunca el cupo gratuito de voz del español ni del inglés. Sin clave de pago, no se graba.
        if not pago:
            raise RuntimeError("Falta GEMINI_API_KEY_IMAGENES: las voces de este idioma son de pago")
        modelo = modelos[0]
        r = gemini(modelo, cuerpo, clave=pago)
        MODELOS_VOZ_USADOS.add(modelo + " (pago)")
        modelos = []
    for k, modelo in enumerate(modelos):
        try:
            r = gemini(modelo, cuerpo)
            MODELOS_VOZ_USADOS.add(modelo)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and k + 1 < len(modelos):
                log(f"   Cupo de voz agotado en {modelo}: sigo con {modelos[k + 1]} (misma voz)")
                continue
            pago = os.environ.get("GEMINI_API_KEY_IMAGENES", "").strip()
            if e.code != 429 or not pago:
                raise
            log("   Cupo gratuito agotado: sigo con la clave de pago (misma voz)")
            os.environ["GEMINI_API_KEY"] = pago
            r = gemini(modelo, cuerpo)
            MODELOS_VOZ_USADOS.add(modelo)
            break
    dato = r["candidates"][0]["content"]["parts"][0]["inlineData"]
    m = re.search(r"rate=(\d+)", dato.get("mimeType", ""))
    crudo = destino.with_suffix(".raw.wav")
    bruto = base64.b64decode(dato["data"])
    if bruto[:4] == b"RIFF":  # algunos modelos (gemini-3.8-flash-tts) devuelven un WAV completo, no PCM suelto
        crudo.write_bytes(bruto)
    else:
        with wave.open(str(crudo), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(m.group(1)) if m else HZ)
            w.writeframes(bruto)
    a_wav_estandar(crudo, destino, CFG.get("velocidad_voz", 1.0))


LIMPIAR = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
           "silenceremove=start_periods=1:start_threshold=-45dB,areverse,loudnorm=I=-18:TP=-2:LRA=11")


def silencios(ruta):
    """[(inicio, fin)] de los silencios de un wav."""
    r = subprocess.run(["ffmpeg", "-i", str(ruta), "-af", "silencedetect=noise=-40dB:d=0.2", "-f", "null", "-"],
                       capture_output=True, text=True)
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    fin = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(ini, fin))


def duracion(ruta):
    with wave.open(str(ruta)) as w:
        return w.getnframes() / w.getframerate()


def voz_comprobada(p, prompt, destino, letras, intentos=3):
    """Graba y comprueba que la duración es razonable para el texto (≈15 letras por segundo). A veces Gemini
    devuelve un audio anómalo (silencios enormes, texto repetido o leído a medias): entonces se graba otra vez."""
    esperado = letras / 15.0
    guardada = CACHE / f"voz_{huella(p['voz_gemini'], prompt, CFG['modelo_voz'], CFG.get('velocidad_voz', 1.0))}.wav" \
        if CACHE else None
    if guardada and guardada.exists():
        log(f"   (caché) voz ya grabada: {guardada.name}")
        shutil.copy(guardada, destino)
        return
    for intento in range(intentos):
        try:
            voz_gemini(p, prompt, destino)
        except (KeyError, IndexError) as e:  # a veces Gemini responde sin audio (sin «content»): se pide otra vez
            if intento == intentos - 1:
                raise
            log(f"   Gemini respondió sin audio ({e}); grabo otra vez")
            time.sleep(CFG.get("pausa_tts_segundos", 21))
            continue
        dur = duracion(destino)
        if esperado * 0.55 - 1 <= dur <= esperado * 1.6 + 3:
            if guardada:
                guardada.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(destino, guardada)
            return
        log(f"   Audio anómalo: {dur:.1f} s para {letras} letras (esperado ~{esperado:.0f} s); grabo otra vez")
        time.sleep(CFG.get("pausa_tts_segundos", 21))
    raise RuntimeError(f"Gemini devuelve audios anómalos ({dur:.0f} s para ~{esperado:.0f} s); no se publica así")


def por_separado(p, quien, indices, textos, carpeta):
    """Graba cada fragmento de un personaje aparte (misma voz). Devuelve {índice de fragmento: wav}."""
    salida = {}
    for n, (i, texto) in enumerate(zip(indices, textos)):
        bruto = carpeta / f"voz_{quien}_{n:02d}_b.wav"
        voz_comprobada(p, txt("leer").format(estilo=p['estilo'], texto=texto), bruto, len(texto))
        trozo = carpeta / f"voz_{quien}_{n:02d}.wav"
        ffmpeg("-i", bruto, "-af", LIMPIAR, "-ar", HZ, "-ac", 1, "-sample_fmt", "s16", trozo)
        salida[i] = trozo
        time.sleep(CFG.get("pausa_tts_segundos", 21))
    return salida


def grabar_personaje(frs, indices, carpeta):
    """TODO lo que dice un personaje en UNA sola grabación (mismo tono de principio a fin), cortada en sus fragmentos.
    Devuelve {índice de fragmento: wav}."""
    quien = frs[indices[0]]["personaje"]
    p = PJ[quien]
    textos = [hablado(frs[i]["texto"]) for i in indices]
    completo = carpeta / f"voz_{quien}.wav"
    if len(indices) == 1:
        voz_comprobada(p, txt("leer").format(estilo=p['estilo'], texto=textos[0]), completo, len(textos[0]))
        partes = [(0.0, duracion(completo))]
    else:
        try:
            voz_comprobada(p, txt("leer_varios").format(estilo=p['estilo']) + "\n\n".join(textos), completo,
                           sum(len(x) for x in textos) + 15 * (len(textos) - 1), intentos=2)
        except (KeyError, IndexError):
            # 14/11/2026: con textos muy largos (la parábola de los talentos, ~1700 letras de Jesús) el modelo de voz
            # responde varias veces sin audio. Entonces se graba cada fragmento aparte, con la misma voz.
            log(f"   {quien}: la grabación entera no sale (texto largo); grabo sus fragmentos por separado")
            return por_separado(p, quien, indices, textos, carpeta)
        dur = duracion(completo)
        try:
            oidos = cortes_oidos(completo, textos)
        except Exception as e:
            log(f"   {quien}: no pude escuchar la grabación para cortarla ({type(e).__name__}: {e})")
            oidos = None
        if oidos:
            log(f"   {quien}: cortes por lo que se oye en " + ", ".join(f"{c:.2f}" for c in oidos) + " s")
        elif CFG.get("karaoke", {}).get("alineador") == "whisper":
            CORTES_SIN_OIR.append(quien)  # cortado por estimación: puede caer en la pausa equivocada
        letras = [len(x) for x in textos]
        candidatos = [((a + b) / 2, b - a) for a, b in silencios(completo) if 0.1 < a and b < dur - 0.1]
        cortes, previo = (list(oidos), None) if oidos else ([], 0.0)
        for k in (range(1, len(indices)) if not oidos else []):
            esperado = dur * sum(letras[:k]) / sum(letras)
            margen = max(3.0, dur * 0.12)
            validos = [(m, d) for m, d in candidatos if m > previo + 0.5 and abs(m - esperado) <= margen]
            if not validos:
                cortes = None
                break
            m = max(validos, key=lambda c: c[1] - abs(c[0] - esperado) * 0.15)[0]
            cortes.append(m)
            previo = m
        if cortes is None:
            # Muy raro: no se distinguen las pausas. Se graba cada fragmento aparte, con la misma voz.
            log(f"   {quien}: no distingo las pausas; grabo sus fragmentos por separado")
            return por_separado(p, quien, indices, textos, carpeta)
        bordes = [0.0] + cortes + [dur]
        partes = list(zip(bordes[:-1], bordes[1:]))
    salida = {}
    for n, (i, (a, b)) in enumerate(zip(indices, partes)):
        trozo = carpeta / f"voz_{quien}_{n:02d}.wav"
        ffmpeg("-i", completo, "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-af", LIMPIAR,
               "-ar", HZ, "-ac", 1, "-sample_fmt", "s16", trozo)
        salida[i] = trozo
    return salida


def tts_edge(f, destino):
    p = PJ[f["personaje"]]
    mp3 = destino.with_suffix(".mp3")
    subprocess.run(["edge-tts", f"--voice={p['voz_edge']}", f"--rate={p.get('velocidad_edge', '-5%')}",
                    "--text", hablado(f["texto"]), "--write-media", str(mp3)], check=True)
    a_wav_estandar(mp3, destino)


def generar_audio(frs, carpeta):
    motor_voz = os.environ.get("MOTOR_VOZ", "").strip() or CFG.get("motor_voz")  # MOTOR_VOZ=edge: solo para pruebas
    motores = ["gemini"] + (["edge"] if CFG.get("respaldo_edge") else []) if motor_voz == "gemini" else ["edge"]
    for motor in motores:
        if motor == "gemini":
            try:
                archivos = {}
                orden = list(dict.fromkeys(f["personaje"] for f in frs))
                for j, quien in enumerate(orden):
                    indices = [i for i, f in enumerate(frs) if f["personaje"] == quien]
                    log(f"   [gemini] grabación {j + 1}/{len(orden)}: {quien} ({len(indices)} fragmentos)")
                    if j:
                        time.sleep(CFG.get("pausa_tts_segundos", 21))
                    archivos.update(grabar_personaje(frs, indices, carpeta))
                return motor, [{"archivo": archivos[i].name, "fragmentos": [i]} for i in range(len(frs))]
            except Exception as e:
                log(f"   El motor de voz gemini falló: {e}")
                continue
        lotes = [[i] for i in range(len(frs))]
        try:
            pistas = []
            for j, lote in enumerate(lotes):
                destino = carpeta / f"voz_{motor}_{j:02d}.wav"
                quienes = " + ".join(dict.fromkeys(frs[i]["personaje"] for i in lote))
                log(f"   [{motor}] petición {j + 1}/{len(lotes)}: {quienes}")
                tts_edge(frs[lote[0]], destino)
                pistas.append({"archivo": destino.name, "fragmentos": lote})
            return motor, pistas
        except Exception as e:
            log(f"   El motor de voz {motor} falló: {e}")
    raise RuntimeError("No se pudieron generar las voces (¿cupo de Gemini agotado?). No se publica para no cambiar las voces de los personajes: vuelve a lanzarlo más tarde.")


def montar_audio(frs, pistas, carpeta):
    """Une las pistas con pausas y reparte el tiempo de cada pista entre sus fragmentos (por letras)."""
    pausa = int(HZ * CFG.get("pausa_entre_voces", 0.35))
    inicio = int(HZ * 0.6)
    t = inicio / HZ
    with wave.open(str(carpeta / "audio.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(HZ)
        out.writeframes(b"\0\0" * inicio)
        for pista in pistas:
            if any(frs[i].get("reflexion") for i in pista["fragmentos"]):  # respiro antes de la reflexión
                extra = int(HZ * 0.9)
                out.writeframes(b"\0\0" * extra)
                t += extra / HZ
            with wave.open(str(carpeta / pista["archivo"])) as w:
                n = w.getnframes()
                out.writeframes(w.readframes(n))
            dur = n / HZ
            largos = [max(1, len(hablado(frs[i]["texto"]))) for i in pista["fragmentos"]]
            s = t
            for i, largo in zip(pista["fragmentos"], largos):
                d = dur * largo / sum(largos)
                frs[i]["inicio"], frs[i]["fin"] = s, s + d
                if len(pista["fragmentos"]) == 1:
                    frs[i]["audio"] = str(carpeta / pista["archivo"])  # para el alineador de palabras (karaoke)
                s += d
            out.writeframes(b"\0\0" * pausa)
            t += dur + pausa / HZ
        out.writeframes(b"\0\0" * HZ)
    return t + 1.0


# ---------- 4. Cuadros ----------

def buscar_cuadro(busqueda, usados):
    """Busca cuadros de dominio público (pintores de config) y prefiere los verticales."""
    gen = CFG["busquedas_genericas"]
    pintores = CFG.get("pintores", ["James Tissot"])
    for q in ([busqueda] if busqueda else []) + random.sample(gen, len(gen)):
        candidatos = []
        for pintor in pintores:
            r = http("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
                "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 15,
                "gsrsearch": f'intitle:"{pintor}" {q} filetype:bitmap', "prop": "imageinfo", "iiprop": "size"}))
            paginas = sorted(r.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
            for p in paginas:
                ii = (p.get("imageinfo") or [{}])[0]
                if p["title"] not in usados and ii.get("width"):
                    candidatos.append((ii["height"] < ii["width"], p["title"]))
            time.sleep(1)
        if candidatos:
            verticales = [x for horizontal, x in candidatos if not horizontal]
            lista = verticales or [x for _, x in candidatos]
            elegido = lista[0] if q == busqueda else random.choice(lista[:8])
            usados.add(elegido)
            return elegido
    raise RuntimeError("No encuentro cuadros en Wikimedia Commons")


def elegir_cuadros(escenas, busquedas, carpeta, usados=None):
    usados, cuadros = (set() if usados is None else usados), {}
    for n in escenas:
        titulo = buscar_cuadro(busquedas.get(n, ""), usados)
        nombre = titulo.split(":", 1)[1].replace(" ", "_")
        url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(nombre) + "?width=2200"
        destino = carpeta / f"cuadro_{n}.img"
        destino.write_bytes(http(url, raw=True)[1])
        cuadros[n] = {"archivo": destino, "titulo": titulo}
        log(f"   Escena {n}: {titulo}")
    return cuadros


def archivo_clip(nombre, carpeta="clips"):
    for ext in (".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp"):
        p = RAIZ / "biblioteca" / carpeta / f"{nombre}{ext}"
        if p.exists() and p.stat().st_size > 10_000:  # ignora archivos vacíos o rotos
            return p
    return None


def clips_disponibles():
    ruta = RAIZ / "biblioteca" / "catalogo.json"
    if not ruta.exists():
        return {}
    cat = json.loads(ruta.read_text(encoding="utf-8"))["clips"]
    return {k: v["descripcion"] for k, v in cat.items() if archivo_clip(k) and not k.startswith("R")}  # R: solo reflexión


def es_video(p):
    return Path(p).suffix.lower() in (".mp4", ".mov", ".webm")


CORTES_SIN_OIR = []  # personajes cuya grabación se cortó sin poder escucharla (riesgo de desfase entre frases)
AVISOS = []  # cosas que requieren a Carlos (se mandan por Telegram con el aviso de «vídeo listo»)


def generar_imagenes_dia(info, escenas, fecha, correcciones=None):
    """Pinta con Nano Banana (API de pago) una imagen por escena y la guarda en biblioteca/dias/.
    Si ya existe (o falla), no hace nada: el proceso sigue con la biblioteca.
    correcciones: {escena: texto} que pidió el revisor al mandar repintar (publicar.py borra la imagen mala)."""
    correcciones = {int(k): v for k, v in (correcciones or {}).items()}
    opciones = CFG.get("imagenes_ia", {})
    if not opciones.get("activo") or not os.environ.get("GEMINI_API_KEY_IMAGENES", "").strip():
        return
    import imagenes
    if opciones.get("modelo"):
        imagenes.PREFERIDOS = [opciones["modelo"]]
    datos = {int(e["numero"]): e for e in info}
    hechas = 0
    for n in escenas:
        e = datos.get(n, {})
        if archivo_clip(f"{fecha}_e{n}", "dias") or not e.get("descripcion"):
            continue
        if hechas >= opciones.get("max_por_video", 5):
            break
        refs = [(k.capitalize(), RAIZ / "personajes" / f"{k}.png") for k in e.get("personajes", [])
                if (RAIZ / "personajes" / f"{k}.png").exists()]
        destino = RAIZ / "biblioteca" / "dias" / f"{fecha}_e{n}.jpg"
        escena = e["descripcion"]
        if e.get("personajes") and "jesus" not in e["personajes"]:  # p. ej. una parábola: Jesús la cuenta, pero no sale en ella
            escena += "\nJesus does NOT appear in this scene."
        if correcciones.get(n):
            escena += f"\nIMPORTANT CORRECTION (a previous version was wrong): {correcciones[n]}"
            log(f"   Escena {n}: se repinta con la corrección del revisor: {correcciones[n]}")
        try:
            modelo = imagenes.generar(escena, destino, refs, e.get("estilo", "oleo"))
            hechas += 1
            log(f"   Imagen IA escena {n} ({modelo}): {e['descripcion'][:90]}")
        except Exception as ex:
            log(f"   Imagen IA escena {n} falló ({ex}); se usa la biblioteca")
            txt = str(ex)
            if any(k in txt for k in ("429", "402", "RESOURCE_EXHAUSTED", "billing", "credit", "prepay", "quota")):
                AVISOS.append("Las imágenes de pago fallan por saldo o cuota: recarga el prepago de la API de imágenes.")
                break


def elegir_visuales(tramos, info, fecha, carpeta, retrato=None, presentes=None):
    """Por tramo: clip del día > clip elegido por Gemini > imagen devocional (D..) > cuadro clásico.
    presentes: personajes del pasaje. De la biblioteca solo valen imágenes sin personas, con Jesús o con personajes
    que salen en el pasaje (nunca la Virgen mientras habla Jesús si María no aparece)."""
    datos = {int(e["numero"]): e for e in info}
    ruta_cat = RAIZ / "biblioteca" / "catalogo.json"
    cat = json.loads(ruta_cat.read_text(encoding="utf-8"))["clips"] if ruta_cat.exists() else {}
    validos = set(presentes or PJ) | {"jesus"}

    otros = validos - {"jesus", "narrador"}

    def encaja(k):
        """«persona» en el catálogo = alguien junto a Jesús (p. ej. D06, Jesús abraza a alguien que llora): solo vale
        si en el pasaje hay otro personaje que no sea Jesús ni el narrador."""
        pj = set(cat.get(k, {}).get("personajes", []))
        if "persona" in pj and not otros:
            return False
        return pj - {"persona"} <= validos

    rellenos = [k for k in cat if k.startswith("D") and archivo_clip(k) and encaja(k)]
    random.shuffle(rellenos)
    usados, visuales = set(), []
    for b in tramos:
        n, e = b["escena"], datos.get(b["escena"], {})
        tipo = b.get("tipo", "escena")
        if tipo in ("evangelista", "cierre") and retrato:  # el evangelista del día, pintado una vez
            visuales.append({"archivo": retrato, "titulo": f"evangelistas/{retrato.name}"})
            log(f"   Tramo {tipo}: {visuales[-1]['titulo']}")
            continue
        if tipo == "reflexion":  # fondo SIN personas (no atribuir la reflexión a nadie), rotando por días
            fondos = [k for k in CFG.get("fondos_reflexion", []) if archivo_clip(k)]
            if fondos:
                k = fondos[dt.date.fromisoformat(str(fecha)).toordinal() % len(fondos)]
                visuales.append({"archivo": archivo_clip(k), "titulo": f"biblioteca/{k}"})
                log(f"   Tramo reflexión: biblioteca/{k} (sin personas, oscurecida)")
                continue
        if tipo in ("reflexion", "cierre") and visuales:  # la última escena, oscurecida
            previa = next((v for v in reversed(visuales) if not v["titulo"].startswith("evangelistas/")), visuales[-1])
            visuales.append(dict(previa))
            log(f"   Tramo {tipo}: {previa['titulo']} (oscurecida)")
            continue
        propio = archivo_clip(f"{fecha}_e{n}", "dias") if b["parte"] == 0 else None
        clip = e.get("clip", "ninguno")
        if propio:
            v = {"archivo": propio, "titulo": f"dias/{propio.name}"}
        elif clip != "ninguno" and clip not in usados and archivo_clip(clip) and encaja(clip):
            usados.add(clip)
            v = {"archivo": archivo_clip(clip), "titulo": f"biblioteca/{clip}"}
        elif any(r not in usados for r in rellenos):
            r = next(r for r in rellenos if r not in usados)
            usados.add(r)
            v = {"archivo": archivo_clip(r), "titulo": f"biblioteca/{r}"}
        else:
            clave = f"{n}_{b['parte']}"
            v = elegir_cuadros([clave], {clave: e.get("busqueda", "")}, carpeta, usados)[clave]
        log(f"   Tramo escena {n}.{b['parte']}: {v['titulo']}")
        visuales.append(v)
    return visuales


# ---------- 5. Vídeo ----------

def bloques(frs, total, gancho=0.0, cierre=0.0, evangelista=False):
    """Tramos de imagen: uno por escena, partidos para que ninguna imagen dure más de max_segundos_imagen."""
    maximo = CFG.get("max_segundos_imagen", 16)
    b = []
    for i, f in enumerate(frs):
        # Tramos especiales: el evangelista mientras anuncia la lectura (primer fragmento) y la reflexión,
        # que va sobre la última escena oscurecida para separarla del Evangelio.
        # «Palabra del Señor» también sobre el evangelista (lo dice el narrador; no sobre un retrato de Jesús).
        tipo = "reflexion" if f.get("reflexion") else (
            "evangelista" if (i == 0 or f.get("palabra")) and evangelista else "escena")
        if not b or b[-1]["escena"] != f["escena"] or b[-1]["tipo"] != tipo:
            b.append({"escena": f["escena"], "inicio": f["inicio"], "tipo": tipo})
    if b[0]["tipo"] == "evangelista" and gancho:  # el gancho, sobre la primera escena; luego el evangelista
        b[0]["inicio"] = gancho
        b.insert(0, {"escena": frs[0]["escena"], "inicio": 0.0, "tipo": "escena"})
    b[0]["inicio"] = 0.0
    if cierre:
        b.append({"escena": frs[-1]["escena"], "inicio": total - cierre, "tipo": "cierre"})
    tramos = []
    for i, x in enumerate(b):
        fin = b[i + 1]["inicio"] if i + 1 < len(b) else total
        partes = max(1, int(-(-(fin - x["inicio"]) // maximo)))
        paso = (fin - x["inicio"]) / partes
        for k in range(partes):
            ini = x["inicio"] + k * paso
            tramos.append({"escena": x["escena"], "parte": k, "inicio": ini, "tipo": x["tipo"],
                           "frames": max(1, round((ini + paso) * FPS) - round(ini * FPS))})
    return tramos


FILTROS = {"reflexion": "eq=brightness=-0.14:saturation=0.55,gblur=sigma=6,",  # oscurecida y desenfocada
           "cierre": "eq=brightness=-0.08:saturation=0.9,"}  # apenas oscurecida, para leer el texto


def clip_escena(img, frames, n, carpeta, tipo="escena"):
    """Zoom lento y suave (acercar o alejar, alternando). Cada fotograma se calcula con precisión subpíxel
    (Pillow), así la imagen no «tiembla» como con zoompan, que redondea a píxeles enteros."""
    from PIL import Image
    zoom = CFG.get("zoom_imagen", 0.08)
    mw, mh = round(W * (1 + zoom)), round(H * (1 + zoom))
    marco = carpeta / f"marco_{n}.png"
    ffmpeg("-i", img, "-vf",
           f"scale={mw}:{mh}:force_original_aspect_ratio=increase:flags=lanczos,crop={mw}:{mh},"
           + FILTROS.get(tipo, "") + "eq=saturation=1.08:brightness=0.02,vignette=PI/5", "-frames:v", 1, marco)
    base = Image.open(marco).convert("RGB")
    dur = frames / FPS
    salida = carpeta / f"clip_{n:02d}.mp4"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-vf",
         f"fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.0, dur - 0.3):.2f}:d=0.3",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(salida)],
        stdin=subprocess.PIPE)
    for k in range(frames):
        avance = k / max(1, frames - 1)
        avance = avance * avance * (3 - 2 * avance) * 0.5 + avance * 0.5  # arranque y final suaves
        if n % 2:
            avance = 1 - avance
        escala = (1 + zoom) / (1 + zoom * avance)  # píxeles de origen por píxel de salida
        a = escala
        c = mw / 2 - a * W / 2
        f = mh / 2 - a * H / 2
        cuadro = base.transform((W, H), Image.AFFINE, (a, 0, c, 0, a, f), resample=Image.BICUBIC)
        proc.stdin.write(cuadro.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError(f"FFmpeg falló al montar la escena {n}")
    return salida


def clip_video(origen, frames, n, carpeta, tipo="escena"):
    """Clip de la biblioteca: cámara lenta, ida y vuelta (sin cortes) y relleno vertical 9:16."""
    dur = frames / FPS
    base = carpeta / f"base_{n:02d}.mp4"
    ffmpeg("-i", origen, "-an", "-filter_complex",
           f"[0:v]setpts=1.5*PTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
           f"crop={W}:{H}," + FILTROS.get(tipo, "") + "eq=saturation=1.05,vignette=PI/5,split[f][r0];[r0]reverse[r];[f][r]concat=n=2:v=1:a=0,format=yuv420p[v]",
           "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", base)
    salida = carpeta / f"clip_{n:02d}.mp4"
    ffmpeg("-stream_loop", -1, "-i", base, "-vf",
           f"fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.0, dur - 0.3):.2f}:d=0.3",
           "-frames:v", frames, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", salida)
    return salida


def ts(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def color_ass(rgb):
    return f"&H00{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&"


def trocear(texto, maximo):
    trozos, actual = [], ""
    for p in texto.split():
        if actual and (len(actual) + 1 + len(p) > maximo or (actual[-1] in ".;:?!" and len(actual) > maximo * 0.45)):
            trozos.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    if actual:
        trozos.append(actual)
    return trozos


def trocear_equilibrado(texto, maximo):
    """Trozos de subtítulo equilibrados (como mucho «maximo» letras), cortando a ser posible tras un signo
    (. ; : , ? !) y nunca dejando una palabra suelta («mesa?», «entregándote»)."""
    ws = texto.split()
    if not ws:
        return []
    n = max(1, -(-len(texto) // maximo))
    objetivo = len(texto) / n
    largo = lambda i, j: len(" ".join(ws[i:j]))  # noqa: E731
    mejor = {0: (0.0, [])}
    for j in range(1, len(ws) + 1):
        opciones = []
        for i in range(max(0, j - 40), j):
            if i not in mejor or largo(i, j) > maximo and j - i > 1:
                continue
            coste = (largo(i, j) - objetivo) ** 2
            if j - i < 3 and len(ws) >= 3:
                coste += 4000  # nada de una o dos palabras solas
            if j < len(ws) and not re.search(r"[.;:,?!]$", ws[j - 1]):
                coste += 120  # mejor cortar tras un signo
            opciones.append((mejor[i][0] + coste, mejor[i][1] + [(i, j)]))
        if opciones:
            mejor[j] = min(opciones)
    return [" ".join(ws[i:j]) for i, j in mejor[len(ws)][1]]


def cortes_de_linea(palabras, maximo=26):
    """Dónde partir el subtítulo en líneas equilibradas (índices de palabra), para que libass no parta solo y deje una
    palabra sola en la última línea. Vale para todos los textos, también la reflexión."""
    total = len(" ".join(palabras))
    if total <= maximo or len(palabras) < 2:
        return []
    n = 2 if total <= 2 * maximo or len(palabras) < 3 else 3
    largo = lambda i, j: len(" ".join(palabras[i:j]))  # noqa: E731
    if n == 2:
        return [min(range(1, len(palabras)), key=lambda i: max(largo(0, i), largo(i, len(palabras))))]
    pares = [(i, j) for i in range(1, len(palabras) - 1) for j in range(i + 1, len(palabras))]
    i, j = min(pares, key=lambda c: max(largo(0, c[0]), largo(c[0], c[1]), largo(c[1], len(palabras))))
    return [i, j]


def tiempos_palabras(f, palabras):
    """Inicio y fin de cada palabra de un fragmento (subtítulos karaoke). Cada fragmento es su propia grabación
    (f["audio"]), colocada en el vídeo en [inicio, fin]: su principio y su final son exactos. Dentro:
    1) alineador (karaoke.alineador = whisper): se escucha la grabación del fragmento y cada palabra va donde suena;
    2) si no está o no es fiable: la duración se reparte por longitud SOLO entre los tramos con voz (las pausas
       de las comas y los puntos no hacen avanzar el resaltado)."""
    if CFG.get("karaoke", {}).get("alineador") == "whisper" and f.get("audio"):
        try:
            t = alinear_whisper(f, palabras)
            if t:
                f["sinc"] = "oido"
                return t
        except Exception as e:
            log(f"   Alineador no disponible ({type(e).__name__}: {e}); reparto por pausas")
    f["sinc"] = "pausas"
    return reparto_con_pausas(f, palabras)


def tramos_de_voz(f):
    """[(a, b)] en segundos de vídeo donde se oye voz dentro del fragmento (sin silencios de 0,2 s o más)."""
    ini, fin = f["inicio"], f["fin"]
    if not f.get("audio") or not Path(f["audio"]).exists():
        return [(ini, fin)]
    try:
        dur = duracion(f["audio"])
        escala = (fin - ini) / max(0.1, dur)
        voz, t = [], 0.0
        for a, b in silencios(f["audio"]) + [(dur, dur)]:
            if a - t > 0.05:
                voz.append((ini + t * escala, ini + min(a, dur) * escala))
            t = max(t, b)
        return voz or [(ini, fin)]
    except Exception:
        return [(ini, fin)]


def reparto_con_pausas(f, palabras):
    voz = tramos_de_voz(f)
    total = sum(b - a for a, b in voz)
    pesos = [len(x) + 1 for x in palabras]
    suma = sum(pesos)

    def en_tiempo(frac):  # fracción del habla -> segundo del vídeo (saltando las pausas)
        objetivo = frac * total
        for a, b in voz:
            if objetivo <= b - a + 1e-9:
                return a + objetivo
            objetivo -= b - a
        return voz[-1][1]

    tiempos, acum = [], 0
    for w in pesos:
        a = en_tiempo(acum / suma)
        acum += w
        tiempos.append((a, en_tiempo(acum / suma)))
    # Si una palabra empieza justo al final de un tramo, que espere al siguiente (tras la pausa)
    return [(a, max(b, a + 0.05)) for a, b in tiempos]


_WHISPER = None


def oir(ruta):
    """[(inicio, fin, palabra)] de lo que se oye en un wav (faster-whisper en CPU, audio leído con FFmpeg)."""
    global _WHISPER
    import numpy as np
    from faster_whisper import WhisperModel
    if _WHISPER is None:
        _WHISPER = WhisperModel(CFG.get("karaoke", {}).get("modelo_whisper", "small"), device="cpu", compute_type="int8")
    crudo = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(ruta), "-f", "f32le", "-ac", "1",
                            "-ar", "16000", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(crudo, dtype=np.float32)
    segs, _ = _WHISPER.transcribe(audio, language=IDIOMA, word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False)
    return [(w.start, w.end, w.word) for sg in segs for w in (sg.words or [])], len(audio) / 16000


def emparejar(palabras, oidas):
    """Para cada palabra del texto, (inicio, fin) donde se oye o None. Solo anclas seguras: 2+ palabras seguidas o una
    palabra de 4+ letras."""
    import difflib
    a = [_normal_palabra(w) for w in palabras]
    b = [_normal_palabra(w) for _, _, w in oidas]
    rel = [None] * len(palabras)
    for bloque in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        if bloque.size < 2 and not (bloque.size == 1 and len(a[bloque.a]) >= 4):
            continue
        for d in range(bloque.size):
            rel[bloque.a + d] = oidas[bloque.b + d][:2]
    return rel


def cortes_oidos(ruta, textos):
    """Grabación con varios fragmentos seguidos (un personaje): dónde cortar, escuchándola. Para cada frontera, el
    silencio más largo entre la última palabra oída de un fragmento y la primera del siguiente. None si no es fiable."""
    if CFG.get("karaoke", {}).get("alineador") != "whisper":
        return None
    oidas, dur = oir(ruta)
    palabras, de = [], []
    for k, t in enumerate(textos):
        for w in espacios(t).split():
            palabras.append(w)
            de.append(k)
    rel = emparejar(palabras, oidas)
    if sum(1 for x in rel if x) / max(1, len(rel)) < CFG.get("karaoke", {}).get("minimo_alineado", 0.6):
        return None
    sil = silencios(ruta)
    cortes = []
    for k in range(1, len(textos)):
        fin_prev = max((rel[j][1] for j in range(len(rel)) if de[j] == k - 1 and rel[j]), default=None)
        ini_sig = min((rel[j][0] for j in range(len(rel)) if de[j] == k and rel[j]), default=None)
        if fin_prev is None or ini_sig is None or ini_sig <= fin_prev:
            return None
        huecos = [(a, b) for a, b in sil if b > fin_prev - 0.05 and a < ini_sig + 0.05]
        if huecos:
            a, b = max(huecos, key=lambda x: x[1] - x[0])
            cortes.append((max(a, fin_prev) + min(b, ini_sig)) / 2)
        else:
            cortes.append((fin_prev + ini_sig) / 2)
    if any(y <= x for x, y in zip(cortes, cortes[1:])):
        return None
    return cortes


def alinear_whisper(f, palabras):
    """Escucha SOLO la grabación del fragmento (voz limpia, unos segundos) con faster-whisper y empareja lo oído con el
    texto, que conocemos exacto. Lo no reconocido se coloca entre lo reconocido. None si no es fiable."""
    opciones = CFG.get("karaoke", {})
    oidas, segundos = oir(f["audio"])
    rel = emparejar(palabras, oidas)
    cuota = sum(1 for x in rel if x) / max(1, len(rel))
    if cuota < opciones.get("minimo_alineado", 0.6):
        log(f"   Alineador: {cuota:.0%} reconocido en «{f['texto'][:30]}…»; reparto por pausas")
        return None
    escala = (f["fin"] - f["inicio"]) / max(0.1, segundos)
    abs_ = [((x[0] * escala + f["inicio"]), (x[1] * escala + f["inicio"])) if x else None for x in rel]
    # Huecos (palabras no reconocidas): por pausas entre las anclas vecinas
    pausas = reparto_con_pausas(f, palabras)
    anclas = [k for k, x in enumerate(abs_) if x]
    for k in range(len(abs_)):
        if abs_[k]:
            continue
        prev = max((x for x in anclas if x < k), default=None)
        nxt = min((x for x in anclas if x > k), default=None)
        lo = abs_[prev][1] if prev is not None else f["inicio"]
        hi = abs_[nxt][0] if nxt is not None else f["fin"]
        # posición relativa según el reparto por pausas, encajada entre las anclas
        p_lo = pausas[prev][1] if prev is not None else f["inicio"]
        p_hi = pausas[nxt][0] if nxt is not None else f["fin"]
        def mapa(t):
            return lo + (t - p_lo) * (hi - lo) / max(1e-3, p_hi - p_lo)
        abs_[k] = (mapa(pausas[k][0]), mapa(pausas[k][1]))
    # Orden y límites del fragmento
    salida, previo = [], f["inicio"]
    for x, y in abs_:
        x = min(max(x, previo, f["inicio"]), f["fin"])
        y = min(max(y, x + 0.05), f["fin"])
        salida.append((x, y))
        previo = x
    return salida


def _normal_palabra(w):
    w = unicodedata.normalize("NFKD", w.lower())
    return "".join(c for c in w if c.isalnum())


def subtitulos(frs, ev, fecha, total, ruta, frase="", gancho=0.0, cierre=0.0):
    titulo = {"en": "Gospel of the day · ", "pt": "Evangelho do dia · "}.get(IDIOMA, "Evangelio del día · ")
    fin_cabecera = next((f["inicio"] for f in frs if f.get("reflexion")), total - cierre)  # no durante la reflexión
    eventos = [("Cabecera", gancho, fin_cabecera,
                "{\\fs38}" + titulo + fecha_larga(fecha) + "\\N{\\fs56}" + ev["cita"])]
    if frase and gancho:
        # Gancho minimalista: velo oscuro muy suave sobre la imagen y la frase en serif fina, centrada.
        eventos.append(("Velo", 0, gancho, "{\\an7\\pos(0,0)\\p1\\fad(0,350)}"
                        f"m 0 0 l {W} 0 {W} {H} 0 {H}" + "{\\p0}"))
        limpio = frase.replace("{", "(").replace("}", ")")
        eventos.append(("Gancho", 0, gancho, "{\\fad(250,350)\\blur3}“" + limpio + "”"))
    if cierre:
        # Cierre minimalista sobre el evangelista (o la escena oscurecida), arriba, en la pared despejada.
        eventos.append(("Gancho", total - cierre, total, "{\\an8\\pos(540,430)\\fad(300,400)\\blur2\\fs64}" + txt("cierre")
                        + "\\N{\\fs40\\i0\\c" + color_ass("F5C542") + "}CatolicAid"))
    for n_f, f in enumerate(frs):
        p = PJ[f["personaje"]]
        kar = CFG.get("karaoke", {})
        # Karaoke: se ven las comillas “ ” y ‘ ’ (citas dentro del discurso); sin karaoke, como siempre.
        limpio = (espacios(f["texto"]) if kar.get("activo") else hablado(f["texto"])).replace("{", "(").replace("}", ")")
        trozos = (trocear_equilibrado if kar.get("activo") else trocear)(limpio, CFG.get("caracteres_por_subtitulo", 46))
        largo = sum(len(x) for x in trozos)
        t, dur = f["inicio"], f["fin"] - f["inicio"]
        nombre = ""
        if p.get("nombre"):
            nombre = "{\\fs40\\c" + color_ass(p["color"]) + "}" + p["nombre"].upper() + "\\N"
        estilo = "{\\fs60\\c" + color_ass(p.get("color_texto", "FFFFFF")) + "}"
        base = p.get("color_texto", "FFFFFF")
        if f.get("reflexion"):
            nombre, estilo, base = "", "{\\fs56\\i1\\c" + color_ass("F3E6C4") + "}", "F3E6C4"
        if not kar.get("activo"):
            for tr in trozos:
                d = dur * len(tr) / largo
                eventos.append(("Texto", t, t + d, nombre + estilo + tr))
                t += d
            continue
        # Karaoke: la palabra que se lee, resaltada (Jesús en su dorado; los demás, un tono suave).
        resalte = kar.get("resalte", {}).get(f["personaje"], kar.get("resalte_otros", "FFE6A6"))
        if f.get("reflexion"):
            resalte = kar.get("resalte_reflexion", "FFFFFF")
        palabras = [w for tr in trozos for w in tr.split()]
        tiempos = tiempos_palabras(f, palabras)
        siguiente = frs[n_f + 1]["inicio"] if n_f + 1 < len(frs) else total - cierre  # sin huecos sin texto
        k = 0
        for n_tr, tr in enumerate(trozos):
            ws = tr.split()
            cortes = cortes_de_linea(ws, 24 if f.get("reflexion") else 26)
            for j in range(len(ws)):
                a = tiempos[k + j][0] if j else (tiempos[k][0] if n_tr else f["inicio"])
                b = tiempos[k + j + 1][0] if j + 1 < len(ws) else tiempos[k + j][1]
                if j + 1 == len(ws) and n_tr + 1 == len(trozos):
                    b = max(b, siguiente - 0.02)
                marcadas = ws[:j] + ["{\\c" + color_ass(resalte) + "}" + ws[j] + "{\\c" + color_ass(base) + "}"] + ws[j + 1:]
                bordes = [0] + cortes + [len(marcadas)]
                linea = "\\N".join(" ".join(marcadas[x:y]) for x, y in zip(bordes, bordes[1:]))
                eventos.append(("Texto", a, b, nombre + estilo + linea))
            k += len(ws)
    cabecera = (
        "[Script Info]\nScriptType: v4.00+\n" f"PlayResX: {W}\nPlayResY: {H}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Texto,DejaVu Sans,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,3,8,"
        "110,110,1185,1\n"
        "Style: Cabecera,DejaVu Sans,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,4,2,8,"
        "60,60,120,1\n"
        "Style: Gancho,DejaVu Serif,86,&H00FFFFFF,&H00FFFFFF,&H60000000,&HA0000000,0,1,0,0,100,100,1,0,1,1.5,0,5,"
        "130,130,0,1\n"
        "Style: Velo,DejaVu Sans,10,&H9A000000,&H9A000000,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,7,"
        "0,0,0,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    cuerpo = "".join(f"Dialogue: 0,{ts(a)},{ts(b)},{s},,0,0,0,,{x}\n" for s, a, b, x in eventos)
    ruta.write_text(cabecera + cuerpo, encoding="utf-8")


MUSICA_VETADA = RAIZ / "estado" / "musica.json"
LICENCIAS_LIBRES = re.compile(r"public domain|dominio p|\bpd\b|cc0|cc[ -]by(?![ -]?(nc|nd))", re.I)


def musica_vetada():
    """Grabaciones que YouTube (Content ID) ha reclamado o bloqueado: no se vuelven a usar nunca."""
    try:
        return json.loads(MUSICA_VETADA.read_text(encoding="utf-8")).get("vetadas", {})
    except Exception:
        return {}


def vetar_musica(nombre, motivo):
    datos = musica_estado()
    datos.setdefault("vetadas", {})
    datos.get("aprobadas", {}).pop(nombre.replace(" ", "_"), None)
    datos["vetadas"][nombre.replace(" ", "_")] = {"motivo": motivo, "fecha": dt.datetime.now(MADRID).isoformat(timespec="seconds")}
    MUSICA_VETADA.parent.mkdir(exist_ok=True)
    MUSICA_VETADA.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def licencia_commons(nombre):
    """Licencia que declara Wikimedia Commons para el archivo («» si no se puede saber)."""
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=extmetadata&titles="
           + urllib.parse.quote("File:" + nombre))
    paginas = http(url, timeout=60).get("query", {}).get("pages", {})
    meta = next(iter(paginas.values()), {}).get("imageinfo", [{}])[0].get("extmetadata", {})
    return " ".join(meta.get(k, {}).get("value", "") for k in ("LicenseShortName", "License"))


def musica_estado():
    try:
        return json.loads(MUSICA_VETADA.read_text(encoding="utf-8"))
    except Exception:
        return {}


def musica_aprobada():
    """Candidatas (musica_candidatas de config) que ya pasaron la prueba privada en YouTube sin reclamaciones."""
    return set(musica_estado().get("aprobadas", {}))


def descargar_musica(nombre):
    """Pista de Wikimedia Commons en musica/ (si no está ya), solo con licencia libre. Devuelve la ruta o None."""
    nombre = nombre.replace(" ", "_")
    ruta = RAIZ / "musica" / nombre
    if ruta.exists():
        return ruta
    lic = licencia_commons(nombre)
    if not LICENCIAS_LIBRES.search(lic):
        log(f"   Música {nombre}: licencia no libre o desconocida en Commons ({lic[:80] or '?'}); la salto")
        return None
    url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(nombre)
    datos = http(url, raw=True, timeout=180)[1]
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_bytes(datos)
    return ruta


def musica_del_dia(fecha):
    """Música clásica de dominio público (Wikimedia Commons), rotando por días; se guarda en musica/.
    Solo valen: las pistas de «musica» (ya publicadas sin problemas) y las candidatas que pasaron la prueba privada en
    YouTube (proceso/youtube_tareas.py); siempre con crédito en creditos_musica, licencia libre en Commons y nunca
    vetadas (estado/musica.json). Si la del día no vale, se usa la siguiente."""
    vetadas = musica_vetada()
    creditos = {k.replace(" ", "_") for k in CFG.get("creditos_musica", {})}
    aprobadas = musica_aprobada()
    pistas = [x.replace(" ", "_") for x in CFG.get("musica", [])]
    pistas += [x.replace(" ", "_") for x in CFG.get("musica_candidatas", []) if x.replace(" ", "_") in aprobadas]
    pistas = [x for x in dict.fromkeys(pistas) if x not in vetadas and x in creditos]
    if not pistas:
        log("   Sin música: ninguna pista comprobada disponible")
        return None
    inicio = fecha.toordinal() % len(pistas)
    for nombre in pistas[inicio:] + pistas[:inicio]:
        try:
            ruta = descargar_musica(nombre)
            if ruta:
                return ruta
        except Exception as e:
            log(f"   Música {nombre} no disponible ({e})")
    return None


def medir(ruta, extra=""):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(ruta), "-af",
                        f"loudnorm=I=-14:TP=-2:LRA=11{extra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])


def normalizar_volumen(origen, destino):
    """Audio final a -14 LUFS (estándar de YouTube/TikTok), en dos pasadas y con pico real máximo de -1,5 dB."""
    m = medir(origen)
    medidas = ":".join(f"measured_{k}={m['input_' + k]}" for k in ("i", "tp", "lra", "thresh"))
    # TP=-2 (no -1,5): margen para que, tras comprimir a AAC, el pico real quede por debajo de -1,5 dBTP
    ffmpeg("-i", origen, "-af", f"loudnorm=I=-14:TP=-2:LRA=11:{medidas}:offset={m['target_offset']}:linear=true,"
           "aresample=48000", "-ar", 48000, "-ac", 2, "-c:a", "pcm_s16le", destino)
    final = float(medir(destino)["input_i"])
    log(f"   Volumen: {float(m['input_i']):.1f} → {final:.1f} LUFS")
    return round(final, 1)


# ---------- 6. YouTube ----------

YT = "https://www.googleapis.com/youtube/v3/"
CANAL_ES = "UCeQ2e1rojxsa9UyrHWcVEVA"
CANAL_EN = "UCNedsWPz5j3H9WXOADjzjkg"
LISTAS = {"Mateo": "Evangelio según san Mateo", "Marcos": "Evangelio según san Marcos",
          "Lucas": "Evangelio según san Lucas", "Juan": "Evangelio según san Juan"}
LISTAS_EN = {"Mateo": "Gospel according to St. Matthew", "Marcos": "Gospel according to St. Mark",
             "Lucas": "Gospel according to St. Luke", "Juan": "Gospel according to St. John"}
TIEMPOS = {"adviento": ("Evangelio del día · Adviento", "Daily Gospel · Advent"),
           "navidad": ("Evangelio del día · Navidad", "Daily Gospel · Christmas"),
           "cuaresma": ("Evangelio del día · Cuaresma", "Daily Gospel · Lent"),
           "pascua": ("Evangelio del día · Pascua", "Daily Gospel · Easter"),
           "ordinario": ("Evangelio del día · Tiempo Ordinario", "Daily Gospel · Ordinary Time")}


TIEMPOS_PT = {"adviento": "Evangelho do dia · Advento", "navidad": "Evangelho do dia · Natal",
              "cuaresma": "Evangelho do dia · Quaresma", "pascua": "Evangelho do dia · Páscoa",
              "ordinario": "Evangelho do dia · Tempo Comum"}


def pascua(anio):
    """Domingo de Pascua (calendario gregoriano, algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    mes = (h + l - 7 * m + 90) // 25
    return dt.date(anio, mes, (h + l - 7 * m + 33 * mes + 19) % 32)


def tiempo_liturgico(fecha):
    """adviento / navidad / cuaresma / pascua / ordinario (rito romano, Epifanía el 6 de enero)."""
    navidad = dt.date(fecha.year, 12, 25)
    adviento = navidad - dt.timedelta(days=(navidad.isoweekday() % 7 or 7) + 21)  # 4.º domingo antes de Navidad
    if adviento <= fecha < navidad:
        return "adviento"
    if fecha >= navidad:
        return "navidad"
    epifania = dt.date(fecha.year, 1, 6)
    bautismo = epifania + dt.timedelta(days=7 - epifania.isoweekday() % 7)  # domingo siguiente al 6 de enero
    if fecha <= bautismo:
        return "navidad"
    p = pascua(fecha.year)
    if p - dt.timedelta(days=46) <= fecha < p:
        return "cuaresma"
    if p <= fecha <= p + dt.timedelta(days=49):  # hasta Pentecostés
        return "pascua"
    return "ordinario"


def refresh_youtube(idioma="es"):
    """Español: el permiso reconectado (secretos/youtube.enc) o, si no, el secreto de siempre.
    Inglés: SOLO su permiso (secretos/youtube-en.enc); nunca el del español."""
    import youtube_conectar
    if idioma != "es":
        r = youtube_conectar.guardado(idioma)
        if not r:
            raise RuntimeError(f"No hay permiso de YouTube para el canal «{idioma}» (secretos/youtube-{idioma}.enc)")
        return r
    return youtube_conectar.guardado() or os.environ["YT_REFRESH_TOKEN"].strip()


def token_youtube(idioma="es"):
    r = http("https://oauth2.googleapis.com/token", urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(),
        "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": refresh_youtube(idioma),
        "grant_type": "refresh_token"}).encode())
    log(f"   Permisos de YouTube: {r.get('scope', '?')}")
    if idioma != "es":  # seguridad: el vídeo en inglés nunca puede ir al canal en español
        d = http(YT + "channels?part=snippet&mine=true", headers={"Authorization": f"Bearer {r['access_token']}"})
        canal = (d.get("items") or [{}])[0]
        log(f"   Canal: {canal.get('snippet', {}).get('title', '?')} ({canal.get('id', '?')})")
        if not canal.get("id") or canal["id"] == CANAL_ES or (idioma != "en" and canal["id"] == CANAL_EN):
            raise RuntimeError(f"El permiso del canal «{idioma}» apunta a otro canal: no subo nada")
    return r["access_token"]


def anadir_a_lista(tok, titulo, descripcion, vid, idioma="es"):
    """Añade el vídeo a la lista (la crea si no existe). Si falla, no impide la publicación."""
    h = {"Authorization": f"Bearer {tok}"}
    try:
        lista, pagina = None, ""
        while lista is None:
            d = http(YT + "playlists?part=snippet&mine=true&maxResults=50" + (f"&pageToken={pagina}" if pagina else ""),
                     headers=h)
            lista = next((p["id"] for p in d.get("items", []) if p["snippet"]["title"] == titulo), None)
            pagina = d.get("nextPageToken")
            if not pagina:
                break
        if not lista:
            lista = http(YT + "playlists?part=snippet,status", {
                "snippet": {"title": titulo, "defaultLanguage": idioma, "description": descripcion},
                "status": {"privacyStatus": "public"}}, h, method="POST")["id"]
            log(f"   Lista creada: {titulo}")
        http(YT + "playlistItems?part=snippet", {"snippet": {
            "playlistId": lista, "resourceId": {"kind": "youtube#video", "videoId": vid}}}, h, method="POST")
        log(f"   Añadido a la lista «{titulo}»")
        return {"id": lista, "titulo": titulo, "url": f"https://www.youtube.com/playlist?list={lista}"}
    except urllib.error.HTTPError as e:
        motivo = e.read().decode(errors="replace")[:400]
        falta = e.code == 403 and "insufficient" in motivo.lower()
        log(f"   Lista «{titulo}»: " + ("FALTA EL PERMISO de YouTube para gestionar listas" if falta
                                       else f"error {e.code}: {motivo}"))
        return {"titulo": titulo, "error": "falta permiso" if falta else f"{e.code}"}


def lista_evangelista(tok, libro, vid, idioma="es"):
    titulo = (LISTAS_EN if idioma == "en" else CFG.get("pt", {}).get("listas", {}) if idioma == "pt" else LISTAS).get(libro)
    if not titulo:
        return None
    if idioma == "pt":
        desc = (f"O Evangelho do dia segundo São {LIBROS_PT[libro]}, lido com várias vozes. "
                "Um vídeo novo todos os dias. #EvangelhoDoDia")
    elif idioma == "en":
        desc = (f"The Gospel of the day according to St. {LIBROS_EN[libro]}, read with several voices. "
                "A new video every day. #GospelOfTheDay")
    else:
        desc = (f"El Evangelio del día según san {libro}, leído con varias voces. "
                "Un vídeo nuevo cada mañana. #EvangelioDelDia")
    return anadir_a_lista(tok, titulo, desc, vid, idioma)


def lista_liturgica(tok, fecha, vid, idioma="es"):
    tiempo = tiempo_liturgico(fecha)
    es, en = TIEMPOS[tiempo]
    if idioma == "pt":
        pt = TIEMPOS_PT[tiempo]
        return anadir_a_lista(tok, pt, f"{pt.split(' · ')[1]}: o Evangelho de cada dia, lido com várias vozes. "
                              "#EvangelhoDoDia", vid, idioma)
    if idioma == "en":
        return anadir_a_lista(tok, en, f"{en.split(' · ')[1]}: the Gospel of each day, read with several voices. "
                              "#GospelOfTheDay", vid, idioma)
    return anadir_a_lista(tok, es, f"{es.split(' · ')[1]}: el Evangelio de cada día, leído con varias voces. "
                          "#EvangelioDelDia", vid, idioma)


def subir_miniatura(tok, vid, ruta):
    """Miniatura propia (thumbnails.set). Si YouTube no la acepta (canal sin verificar por teléfono, permisos...),
    se anota y se sigue: nunca impide la publicación."""
    if not ruta or not Path(ruta).exists():
        return "sin miniatura"
    try:
        http(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}", Path(ruta).read_bytes(),
             {"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"}, method="POST")
        log("   Miniatura subida")
        return "ok"
    except urllib.error.HTTPError as e:
        motivo = e.read().decode(errors="replace")[:300]
        log(f"   Miniatura no aceptada ({e.code}): {motivo}")
        return f"error {e.code}: " + re.sub(r"\s+", " ", motivo)[:200]
    except Exception as e:
        log(f"   Miniatura no subida ({e})")
        return f"error: {e}"[:200]


def credito_musica(ev):
    """Crédito de la grabación usada (obligatorio en las CC BY). ev["musica"]: nombre del archivo (con _ o espacios)."""
    nombre = (ev.get("musica") or "").replace("_", " ")
    return next((v for k, v in CFG.get("creditos_musica", {}).items() if k.replace("_", " ") == nombre), "")


def titulo_youtube(ev, fecha, idioma="es"):
    frase = (ev.get("frase_clave") or "").strip(" .,;:")
    if idioma == "pt":
        mes = MESES_PT[fecha.month - 1]
        base = f"Evangelho do dia · {fecha.day} de {mes} · {ev['cita']}"
        opciones = [f" | Evangelho do dia {fecha.day} de {mes} ({ev['cita']})",
                    f" | Evangelho do dia {fecha.day}/{fecha.month} ({ev['cita']})",
                    f" | Evangelho {fecha.day}/{fecha.month} · {ev['cita']}"]
    elif idioma == "en":
        mes = MONTHS[fecha.month - 1][:3]
        base = f"Gospel of the day · {MONTHS[fecha.month - 1]} {fecha.day} · {ev['cita']}"
        opciones = [f" | Gospel of the day, {MONTHS[fecha.month - 1]} {fecha.day} ({ev['cita']})",
                    f" | Gospel of the day, {mes} {fecha.day} ({ev['cita']})", f" | Gospel {mes} {fecha.day} · {ev['cita']}"]
    else:
        fecha_txt = f"{fecha.day} de {MESES[fecha.month - 1]}"
        base = f"Evangelio del día · {fecha_txt} · {ev['cita']}"
        corto = f"{fecha.day} {MESES[fecha.month - 1][:3]}"
        opciones = [f" | Evangelio del día {fecha_txt} ({ev['cita']})", f" | Evangelio del día {corto} ({ev['cita']})",
                    f" | Evangelio {corto} · {ev['cita']}"]
    if not frase:
        return base + (" #shorts" if len(base) <= 90 else "")
    # «“Frase” | Evangelio del día 6 de noviembre (Lucas 16, 1-8)». Si no cabe: primero la fecha corta (la fecha y la
    # cita siempre se quedan); después se acorta la frase, a ser posible en una pausa (coma, punto y coma) y sin «…».
    frase = frase[0].upper() + frase[1:]
    resto = next((r for r in opciones if len(frase) + 2 + len(r) <= 100), opciones[-1])
    hueco = 100 - len(resto) - 2
    if len(frase) > hueco:
        pausas = [m.start() for m in re.finditer(r"[,;:]", frase[:hueco]) if len(frase[:m.start()].split()) >= 4]
        frase = frase[:pausas[-1]] if pausas else frase[:hueco - 1].rsplit(" ", 1)[0] + "…"
    return f"“{frase}”{resto}"


def metadatos_youtube(ev, fecha, modo, idioma="es"):
    """Título, descripción, etiquetas y estado (privado, contenido sintético, programación) del vídeo."""
    titulo = titulo_youtube(ev, fecha, idioma)
    if idioma == "pt":
        descripcion = (f"{ev['titulo']}\n{ev['cita']}\n\n"
                       f"Evangelho de {DIAS_PT[fecha.weekday()]}, {fecha.day} de {MESES_PT[fecha.month - 1]} de "
                       f"{fecha.year}, lido com várias vozes.\n\n"
                       + (f"🕊️ Para meditar: {ev['reflexion']}\n\n" if ev.get("reflexion") else "") +
                       f"📖 Texto: {ev.get('fuente_texto', 'Bíblia do Pe. Antônio Pereira de Figueiredo')}. "
                       "Calendário litúrgico: Vatican News.\n"
                       "🎨 Imagens: cenas geradas com IA e pinturas clássicas (domínio público).\n"
                       "🎙️ Vozes geradas com inteligência artificial.\n"
                       + (f"🎵 Música: {credito_musica(ev)}\n" if credito_musica(ev) else "") + "\n"
                       + CFG.get("pt", {}).get("hashtags", "#Shorts #EvangelhoDoDia #Evangelho #PalavraDeDeus #Catolico"))
        etiquetas = ["evangelho do dia", "evangelho", "católico", "palavra de Deus", "bíblia", LIBROS_PT.get(
            ev["cita"].split()[0], ev["cita"].split()[0])]
    elif idioma == "en":
        descripcion = (f"{ev['titulo']}\n{ev['cita']}\n\n"
                       f"Gospel of {DAYS[fecha.weekday()]}, {MONTHS[fecha.month - 1]} {fecha.day}, {fecha.year}, "
                       "read with several voices.\n\n"
                       + (f"🕊️ To meditate: {ev['reflexion']}\n\n" if ev.get("reflexion") else "") +
                       f"📖 Text: {ev.get('fuente_texto', 'World English Bible')}. Liturgical calendar: Vatican News.\n"
                       "🎨 Images: scenes generated with AI and classic paintings (public domain).\n"
                       "🎙️ Voices generated with artificial intelligence.\n"
                       + (f"🎵 Music: {credito_musica(ev)}\n" if credito_musica(ev) else "") + "\n"
                       "#Shorts #GospelOfTheDay #DailyGospel #Gospel #Catholic #WordOfGod")
        etiquetas = ["gospel of the day", "daily gospel", "gospel", "catholic", "word of God", "bible",
                     ev["cita"].split()[0]]
    else:
        fecha_txt = f"{fecha.day} de {MESES[fecha.month - 1]}"
        descripcion = (f"{ev['titulo']}\n{ev['cita']}\n\n"
                       f"Evangelio del {DIAS[fecha.weekday()]} {fecha_txt} de {fecha.year}, leído con varias voces.\n\n"
                       + (f"🕊️ Para meditar: {ev['reflexion']}\n\n" if ev.get("reflexion") else "") +
                       f"📖 Texto: {ev.get('fuente_texto', 'Vatican News')}. Calendario litúrgico: Vatican News.\n"
                       "🎨 Imágenes: escenas generadas con IA y pinturas clásicas (dominio público)\n"
                       "🎙️ Voces generadas con inteligencia artificial.\n"
                       + (f"🎵 Música: {credito_musica(ev)}\n" if credito_musica(ev) else "") + "\n"
                       "#Shorts #EvangelioDelDia #Evangelio #PalabraDeDios #Catolico")
        etiquetas = ["evangelio del día", "evangelio", "católico", "palabra de Dios", ev["cita"].split()[0]]
    estado = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    programar = idioma == "es" or CFG.get(idioma, {}).get("publicar_programado")  # inglés: estreno solo en privado
    if modo == "diario" and programar:
        hora = dt.datetime.combine(fecha, hora_pub(idioma), MADRID)
        if hora > dt.datetime.now(MADRID) + dt.timedelta(minutes=30):
            estado["publishAt"] = hora.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif fecha >= dt.datetime.now(MADRID).date():
            estado["privacyStatus"] = "public"  # llega tarde (su hora ya pasó, mismo día; p. ej. rehecho): se publica ya
    return {"snippet": {"title": titulo[:100], "description": descripcion[:4900], "categoryId": "22",
                        "tags": etiquetas, "defaultLanguage": idioma, "defaultAudioLanguage": idioma},
            "status": estado}


def subir_youtube(video, ev, fecha, modo, tok, idioma="es"):
    meta = metadatos_youtube(ev, fecha, modo, idioma)
    estado = meta["status"]
    r, _ = http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                meta, {"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                       "X-Upload-Content-Length": str(video.stat().st_size)}, method="POST", raw=True)
    req = urllib.request.Request(r.headers["Location"], data=video.read_bytes(), method="PUT",
                                 headers={"Content-Type": "video/mp4", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=900) as r2:
        res = json.loads(r2.read())
    return res["id"], estado


def publicar_extras(tok, vid, reg, fecha, miniatura, idioma="es"):
    """Tras subir: listas (evangelista y tiempo litúrgico) y miniatura. Nada de esto bloquea."""
    yt = reg["youtube"]
    libro = reg.get("libro") or reg["cita"].split()[0]
    for intento in range(3):  # YouTube a veces da 409 SERVICE_UNAVAILABLE justo tras subir o crear la lista
        if not yt.get("lista", {}).get("id"):
            lista = lista_evangelista(tok, libro, vid, idioma)
            if lista:
                yt["lista"] = lista
        if not yt.get("lista_liturgica", {}).get("id"):
            yt["lista_liturgica"] = lista_liturgica(tok, fecha, vid, idioma)
        if yt.get("lista", {}).get("id") and yt.get("lista_liturgica", {}).get("id"):
            break
        time.sleep(20)
    if yt.get("miniatura") != "ok" and miniatura:
        yt["miniatura"] = subir_miniatura(tok, vid, miniatura)
    if yt.get("subtitulos") != "ok":
        yt["subtitulos"] = subir_subtitulos(tok, vid, reg, idioma)


# ---------- 5a. Subtítulos como archivo (YouTube los indexa para las búsquedas y los traduce solo) ----------

def srt_del_registro(reg):
    """SRT con lo que se oye (y la frase del gancho), a partir del registro. Cada fragmento dura hasta el siguiente;
    el último, hasta que empieza el cierre (solo música). Trozos de dos líneas como mucho."""
    frs = reg.get("fragmentos") or []
    if not frs:
        return ""
    total = float(reg.get("duracion_s") or frs[-1]["inicio"] + 5)
    fin_voz = total - float(CFG.get("cierre_segundos", 0) or 0)
    tramos = []
    gancho = float(reg.get("gancho_segundos") or 0)
    if gancho and reg.get("frase_clave"):
        tramos.append((0.0, gancho, f"“{espacios(reg['frase_clave'])}”"))
    for i, f in enumerate(frs):
        a = float(f["inicio"])
        b = float(frs[i + 1]["inicio"]) if i + 1 < len(frs) else max(a + 1.0, fin_voz)
        trozos = trocear_equilibrado(espacios(f["texto"]), 84) or [espacios(f["texto"])]
        largo = sum(len(t) for t in trozos) or 1
        t = a
        for tr in trozos:
            d = (b - a) * len(tr) / largo
            tramos.append((t, t + d - 0.05, tr))
            t += d

    def marca(s):
        ms = int(round(max(0.0, s) * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    def dos_lineas(tr):
        ws = tr.split()
        if len(tr) <= 42 or len(ws) < 2:
            return tr
        c = cortes_de_linea(ws, 42)
        bordes = [0] + c + [len(ws)]
        return "\n".join(" ".join(ws[x:y]) for x, y in zip(bordes, bordes[1:]))

    return "".join(f"{n}\n{marca(a)} --> {marca(b)}\n{dos_lineas(tx)}\n\n" for n, (a, b, tx) in enumerate(tramos, 1))


def subir_subtitulos(tok, vid, reg, idioma="es", srt=None):
    """Sube los subtítulos (captions.insert, permiso youtube.force-ssl). Nunca impide la publicación.
    srt: uno ya hecho (p. ej. el del resumen semanal); si no, se hace con el registro."""
    srt = srt if srt is not None else srt_del_registro(reg)
    if not srt:
        return "sin texto"
    meta = {"snippet": {"videoId": vid, "language": idioma, "isDraft": False,
                        "name": {"en": "English", "pt": "Português"}.get(idioma, "Español")}}
    frontera = "catolicaid" + huella(vid, srt)[:12]
    cuerpo = (f"--{frontera}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
              f"--{frontera}\r\nContent-Type: application/x-subrip; charset=UTF-8\r\n\r\n{srt}\r\n--{frontera}--\r\n")
    try:
        http("https://www.googleapis.com/upload/youtube/v3/captions?part=snippet&uploadType=multipart",
             cuerpo.encode("utf-8"), {"Authorization": f"Bearer {tok}",
                                      "Content-Type": f"multipart/related; boundary={frontera}"}, method="POST")
        log("   Subtítulos subidos")
        return "ok"
    except urllib.error.HTTPError as e:
        motivo = e.read().decode(errors="replace")[:300]
        log(f"   Subtítulos no aceptados ({e.code}): {motivo}")
        return f"error {e.code}: " + re.sub(r"\s+", " ", motivo)[:200]
    except Exception as e:
        log(f"   Subtítulos no subidos ({e})")
        return f"error: {e}"[:200]


# ---------- 5b. Miniatura ----------

def fuente_serif(tam):
    from PIL import ImageFont
    for ruta in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/Library/Fonts/Georgia.ttf",
                 "/System/Library/Fonts/Supplemental/Georgia.ttf", "/System/Library/Fonts/Supplemental/Times New Roman.ttf"):
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default(tam)


def miniatura(img, frase, destino, tam=(1280, 720)):
    """JPG con la imagen del día, la frase clave en serif fina con velo suave y «CatolicAid» en pequeño."""
    from PIL import Image, ImageDraw, ImageFilter
    w, h = tam
    base = Image.open(img).convert("RGB")
    mx, my = int(base.width * 0.06), int(base.height * 0.06)  # sin bordes: ahí suelen salir firmas o garabatos
    base = base.crop((mx, my, base.width - mx, base.height - my))
    escala = max(w / base.width, h / base.height)
    base = base.resize((round(base.width * escala), round(base.height * escala)), Image.LANCZOS)
    x = (base.width - w) // 2
    y = max(0, min(base.height - h, int((base.height - h) * 0.3)))  # algo por encima del centro (caras)
    base = base.crop((x, y, x + w, y + h))
    velo = Image.new("L", (w, h))
    dv = ImageDraw.Draw(velo)
    for fila in range(h):  # velo suave: más oscuro abajo, donde va el texto
        dv.line([(0, fila), (w, fila)], fill=int(70 + 110 * (fila / h) ** 1.6))
    base = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), base, velo.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(base)
    ancho = w * 0.84
    tam_letra = int(h * (0.105 if w > h else 0.05))
    frase = f"“{frase.strip()}”" if frase else ""
    while True:
        f = fuente_serif(tam_letra)
        lineas, actual = [], ""
        for p in frase.split():
            prueba = f"{actual} {p}".strip()
            if actual and d.textlength(prueba, font=f) > ancho:
                lineas.append(actual)
                actual = p
            else:
                actual = prueba
        if actual:
            lineas.append(actual)
        if len(lineas) <= (2 if w > h else 5) or tam_letra < 24:
            break
        tam_letra = int(tam_letra * 0.9)
    if len(lineas) == 2:  # dos líneas equilibradas (nunca una palabra sola abajo)
        ws = frase.split()
        i = min(range(1, len(ws)), key=lambda k: max(d.textlength(" ".join(ws[:k]), font=f),
                                                     d.textlength(" ".join(ws[k:]), font=f)))
        lineas = [" ".join(ws[:i]), " ".join(ws[i:])]
    alto = tam_letra * 1.25
    # Horizontal: la frase abajo (las caras suelen estar en el centro y arriba); vertical: algo por debajo del centro.
    y0 = (h * 0.93 - alto * len(lineas)) if w > h else h * 0.58 - alto * len(lineas) / 2
    for k, linea in enumerate(lineas):
        lw = d.textlength(linea, font=f)
        d.text(((w - lw) / 2, y0 + k * alto), linea, font=f, fill=(255, 255, 255),
               stroke_width=max(1, tam_letra // 40), stroke_fill=(0, 0, 0))
    marca = fuente_serif(int(tam_letra * 0.45))
    mw = d.textlength("CatolicAid", font=marca)
    pos = (w - mw - h * 0.04, h * 0.04) if w > h else ((w - mw) / 2, h - tam_letra * 2.2)  # horizontal: esquina superior
    d.text(pos, "CatolicAid", font=marca, fill=(245, 197, 66), stroke_width=1, stroke_fill=(0, 0, 0))
    base.save(destino, "JPEG", quality=90)
    return destino


def imagen_miniatura(frs, frase, visuales, bl):
    """La imagen del día de la escena donde está la frase clave; si no, la primera imagen del día."""
    escena = next((f["escena"] for f in frs if frase and frase in espacios(hablado(f["texto"]))), None)
    candidatas = [(b["escena"], v) for b, v in zip(bl, visuales)
                  if b.get("tipo", "escena") == "escena" and not es_video(v["archivo"])]
    for n, v in candidatas:
        if n == escena and v["titulo"].startswith("dias/"):
            return v["archivo"]
    for n, v in candidatas:
        if v["titulo"].startswith("dias/"):
            return v["archivo"]
    return candidatas[0][1]["archivo"] if candidatas else None


# ---------- Principal ----------

def resumen(r):
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if not ruta:
        return
    yt = r.get("youtube", {})
    lineas = [f"## Evangelio del {r['fecha']} · {r['cita']}", "",
              f"- Duración: {r['duracion_s']} s · Guion: {r['guion']} · Voces: {r['voces']}",
              f"- YouTube: {yt.get('url', 'no subido')} ({yt.get('privacyStatus', '-')})", "",
              "| Personaje | Texto |", "|---|---|"]
    lineas += [f"| {f['personaje']} | {f['texto'][:90].replace('|', '/')} |" for f in r["fragmentos"]]
    with open(ruta, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")


def evangelio_ingles(fecha):
    """Canal en inglés: la MISMA cita que el español (registro del día > biblia/citas.json > Vatican News),
    con el texto de la World English Bible (Catholic). Si falta algún versículo, falla (nunca otro texto)."""
    es = RAIZ / "episodios" / f"{fecha}.json"
    reg_es = json.loads(es.read_text(encoding="utf-8")) if es.exists() else {}
    ruta = RAIZ / "biblia" / "citas.json"
    citas = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    cita = (reg_es.get("cita") if reg_es.get("modo") == "diario" else None) or citas.get(str(fecha))
    if not cita:
        cita = obtener_evangelio(fecha)["cita"]
    elif citas.get(str(fecha)) and reg_es.get("cita") and citas[str(fecha)] != reg_es["cita"]:
        log(f"   Aviso: citas.json dice {citas[str(fecha)]} y el vídeo en español {reg_es['cita']}; sigo al español")
    texto, fuente = texto_web(cita)
    libro = cita.split()[0]
    return {"url": f"https://www.vaticannews.va/es/evangelio-de-hoy/{fecha:%Y/%m/%d}.html",
            "titulo": f"A reading from the holy Gospel according to {LIBROS_EN.get(libro, libro)}.",
            "cita": cita_en(cita), "cita_es": cita, "libro": libro, "texto": texto, "fuente_texto": fuente}


LIBROS_PT = {"Mateo": "Mateus", "Marcos": "Marcos", "Lucas": "Lucas", "Juan": "João"}


def cita_pt(cita):
    """'Lucas 17, 26-37' -> 'Lucas 17,26-37' · 'Juan 20, 1-2. 11-18' -> 'João 20,1-2.11-18'"""
    libro, resto = cita.split(None, 1)
    resto = re.sub(r"([,.])\s+", r"\1", resto)
    return f"{LIBROS_PT.get(libro, libro)} {resto}"


def evangelio_portugues(fecha):
    """Canal en portugués: la MISMA cita que el español, con el Figueiredo revisado (solo la versión revisada)."""
    es = RAIZ / "episodios" / f"{fecha}.json"
    reg_es = json.loads(es.read_text(encoding="utf-8")) if es.exists() else {}
    ruta = RAIZ / "biblia" / "citas.json"
    citas = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    cita = (reg_es.get("cita") if reg_es.get("modo") == "diario" else None) or citas.get(str(fecha))
    if not cita:
        cita = obtener_evangelio(fecha)["cita"]
    texto, fuente = texto_figueiredo(cita)
    libro = cita.split()[0]
    plantilla = CFG.get("pt", {}).get("titulo_lectura", "Proclamação do Evangelho de Jesus Cristo segundo {evangelista}.")
    return {"url": CFG.get("pt", {}).get("evangelio_del_dia", "").replace("{AAAA}", f"{fecha:%Y}").replace(
                "{MM}", f"{fecha:%m}").replace("{DD}", f"{fecha:%d}"),
            "titulo": plantilla.replace("{evangelista}", f"São {LIBROS_PT.get(libro, libro)}"),
            "cita": cita_pt(cita), "cita_es": cita, "libro": libro, "texto": texto, "fuente_texto": fuente}


def escenas_del_espanol(fecha):
    """Las escenas del vídeo en español del mismo día, para que el inglés use sus imágenes (no se pinta nada)."""
    es = RAIZ / "episodios" / f"{fecha}.json"
    reg = json.loads(es.read_text(encoding="utf-8")) if es.exists() else {}
    escenas = reg.get("escenas") or []
    hechas = sorted(int(m.group(1)) for p in (RAIZ / "biblioteca" / "dias").glob(f"{fecha}_e*.*")
                    if (m := re.search(r"_e(\d+)\.", p.name)))
    if not escenas and not hechas:
        return ""
    if escenas:
        lista = "\n".join(f"   {e['numero']}: {e.get('descripcion') or e.get('busqueda', '')}" for e in escenas)
        return (f"\n6. IMPORTANTE: usa EXACTAMENTE estas {len(escenas)} escenas, numeradas igual y en este orden, "
                f"y asigna cada fragmento a la escena que muestra lo que narra:\n{lista}")
    return (f"\n6. IMPORTANTE: agrupa el relato en EXACTAMENTE {max(hechas)} escenas, numeradas 1 a {max(hechas)} "
            "en el orden del relato.")


def aviso_sin_cupo(fecha, idioma, modo, error):
    """Inglés: si no se ha podido hacer por falta de cupo de Gemini, se deja constancia en el registro."""
    ruta = RAIZ / "episodios" / f"{fecha}{SUFIJO[idioma]}.json"
    previo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if previo.get("revision") or previo.get("youtube"):
        return  # nunca se pisa un vídeo hecho
    previo.update({"fecha": str(fecha), "idioma": idioma, "modo": modo, "estado": "fallido",
                   "error": str(error)[:300], "cupo_agotado": sorted(CUPO_AGOTADO),
                   "intento": dt.datetime.now(MADRID).isoformat(timespec="seconds")})
    if CUPO_AGOTADO:
        previo["avisos"] = sorted(set(previo.get("avisos", []) + [
            "Falta cupo gratuito de Gemini (" + ", ".join(sorted(CUPO_AGOTADO)) + "): se reintenta más tarde."]))
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(previo, ensure_ascii=False, indent=2), encoding="utf-8")


def gancho_del_dia(fecha):
    """Prueba A/B del gancho: días pares e impares con distinta duración (config gancho_ab)."""
    ab = CFG.get("gancho_ab")
    if ab:
        return float(ab["par"] if fecha.day % 2 == 0 else ab["impar"])
    return float(CFG.get("gancho_segundos", 2.0))


def main():
    global CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", default="")
    ap.add_argument("--modo", choices=["prueba", "diario"], default="prueba")
    ap.add_argument("--idioma", choices=["es", "en", "pt"], default="es")
    ap.add_argument("--no-subir", action="store_true")
    ap.add_argument("--si-falta", action="store_true", help="no hace nada si ese día ya está subido (reintentos)")
    ap.add_argument("--cache", default="", help="carpeta de caché (guion, frase y voces ya hechas no se repiten)")
    ap.add_argument("--reutilizar", default="", help="registro del que copiar frase clave y reflexión (rehacer un vídeo "
                                                      "sin volver a pedirlas: con la caché, las voces tampoco se graban)")
    a = ap.parse_args()
    idioma = a.idioma
    aplicar_idioma(idioma)
    suf = SUFIJO[idioma]
    if a.cache:
        CACHE = Path(a.cache)
    if idioma != "es" and not CFG.get(idioma, {}).get("pago_voz") and not CFG.get(idioma, {}).get("voz_de_pago"):
        os.environ.pop("GEMINI_API_KEY_IMAGENES", None)  # inglés: solo la clave gratuita (ni voces ni imágenes de pago)
    if os.environ.get("SIN_PAGO", "").strip().lower() in ("1", "true", "si", "sí"):
        os.environ.pop("GEMINI_API_KEY_IMAGENES", None)  # pruebas: nada de pago
    fecha = (dt.date.fromisoformat(a.fecha.strip()) if a.fecha.strip()
             else dt.datetime.now(MADRID).date() + dt.timedelta(days=1))
    previo = RAIZ / "episodios" / f"{fecha}{suf}.json"
    hecho = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    if a.si_falta and hecho.get("modo") == "diario" and (
            "youtube" in hecho or hecho.get("revision") in ("pendiente", "ok") or hecho.get("no_publicar")):
        log(f"El vídeo del {fecha}{suf} ya está hecho ({hecho.get('revision') or 'subido'}); nada que hacer.")
        return
    if idioma != "es" and a.si_falta and a.modo == "diario" and dt.datetime.now(dt.timezone.utc).hour < 8:
        # 14/11/2026: los cron de GitHub llegaron con horas de retraso, de madrugada, y el inglés y el portugués del
        # día siguiente se grabaron con el cupo gratis que quedaba del día anterior (se renueva a las 08:00 UTC):
        # sin voces en inglés y sin frase clave coherente. Hay tiempo de sobra: se espera al cupo nuevo.
        log(f"Son menos de las 08:00 UTC: el vídeo del {fecha}{suf} espera al cupo gratis nuevo del día.")
        return
    if idioma != "es" and a.si_falta and a.modo == "diario":
        # El inglés va DESPUÉS del español (usa sus imágenes y el cupo que sobre). Si el español aún no está, espera
        # sin fallar; solo en la última tirada (22 UTC o más) sigue sin él, con las imágenes de la biblioteca.
        # El portugués va además DESPUÉS del inglés: usa el mismo modelo de voz y así nunca le quita cupo.
        es = RAIZ / "episodios" / f"{fecha}{'-en' if idioma == 'pt' else ''}.json"
        reg_es = json.loads(es.read_text(encoding="utf-8")) if es.exists() else {}
        listo = reg_es.get("modo") == "diario" and (reg_es.get("youtube") or reg_es.get("revision") in ("pendiente", "ok")
                                                   or reg_es.get("revision") == "rechazada" or reg_es.get("no_publicar"))
        if idioma == "pt":  # el inglés ya APROBADO (no volverá a grabar voces hoy) o descartado: solo entonces el portugués
            listo = reg_es.get("modo") == "diario" and (reg_es.get("youtube") or reg_es.get("revision") == "ok"
                                                       or reg_es.get("no_publicar") or reg_es.get("estado") == "fallido")
        if not listo and dt.datetime.now(dt.timezone.utc).hour < 22:
            log(f"El vídeo en español del {fecha} aún no está hecho: el inglés espera a la próxima tirada.")
            return
    if CACHE:
        CACHE = CACHE / f"{fecha}{suf}"
    carpeta = RAIZ / "salida" / f"{fecha.isoformat()}{suf}"
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    log(f"== Evangelio del {fecha} (modo {a.modo}, idioma {idioma}) ==")
    try:
        producir(a, fecha, idioma, suf, carpeta, hecho)
    except Exception as e:
        if idioma != "es":
            aviso_sin_cupo(fecha, idioma, a.modo, e)
        raise


def producir(a, fecha, idioma, suf, carpeta, hecho):
    log("1/6 Evangelio")
    if idioma == "en":
        ev = evangelio_ingles(fecha)
        libro = ev["libro"]
    elif idioma == "pt":
        ev = evangelio_portugues(fecha)
        libro = ev["libro"]
    else:
        ev = obtener_evangelio(fecha)
        if CFG.get("texto") == "torres-amat":
            try:
                ev["texto"], ev["fuente_texto"] = texto_torres_amat(ev["cita"])
            except Exception as e:
                log(f"   Torres Amat no disponible ({e}); uso el texto de Vatican News")
        ev.setdefault("fuente_texto", "Vatican News")
        libro = ev["cita"].split()[0]
    log(f"   {ev['cita']} · {ev['fuente_texto']} · {len(ev['texto'])} caracteres")
    if libro in CFG.get("narradores", {}):
        PJ["narrador"] = {**PJ["narrador"], **CFG["narradores"][libro]}
        log(f"   Narrador: san {libro} (voz {PJ['narrador']['voz_gemini']})")

    log("2/6 Guion")
    biblioteca = clips_disponibles()
    log(f"   Biblioteca: {len(biblioteca)} clips disponibles")
    g = guion_gemini(ev["texto"], biblioteca, escenas_del_espanol(fecha) if idioma != "es" else "")
    if not g and a.modo == "diario" and dt.datetime.now(dt.timezone.utc).hour < 21:
        raise RuntimeError("Gemini no ha podido repartir las voces: no publico con un reparto dudoso. "
                           "Se reintenta en la próxima tirada (el último intento, a las 21 UTC, usa reglas).")
    if not g:
        log("   Gemini no disponible o no fiel: uso reglas por comillas")
        g = guion_reglas(ev["texto"])
    frs = preparar_fragmentos(g, ev)
    previo_reg = json.loads((RAIZ / a.reutilizar).read_text(encoding="utf-8")) if a.reutilizar else {}
    if previo_reg.get("frase_clave") and previo_reg.get("reflexion"):
        frase, reflexion = previo_reg["frase_clave"], previo_reg["reflexion"]
        log(f"   Frase y reflexión reutilizadas de {a.reutilizar}")
    else:
        if idioma != "es":  # misma frase y reflexión que el español del día (coherencia entre canales)
            es_reg = RAIZ / "episodios" / f"{fecha}.json"
            es_d = json.loads(es_reg.read_text(encoding="utf-8")) if es_reg.exists() else {}
            if es_d.get("modo") == "diario" and es_d.get("frase_clave"):
                ev["frase_es"], ev["reflexion_es"] = es_d["frase_clave"], es_d.get("reflexion", "")
        frase, reflexion = gancho_y_reflexion(frs, ev, g.get("origen") != "reglas")
    if not reflexion:  # nunca un vídeo sin reflexión: como el reparto, se reintenta salvo en el último intento
        if a.modo == "diario" and dt.datetime.now(dt.timezone.utc).hour < (22 if idioma != "es" else 21):
            raise RuntimeError("Gemini no ha podido escribir la reflexión: no publico sin ella. Se reintenta en la próxima tirada.")
        reflexion = CFG.get("reflexion_reserva", {}).get(idioma, "")
        log("   Reflexión de reserva (Gemini no respondió)")
    log(f"   Frase clave: {frase or '(ninguna)'}")
    log(f"   Reflexión: {reflexion or '(ninguna)'}")
    if reflexion:
        ev["reflexion"] = reflexion
        frs.append({"personaje": "narrador", "texto": reflexion, "escena": frs[-1]["escena"], "reflexion": True})
    ev["frase_clave"] = frase
    for f in frs:
        log(f"   [{f['escena']}] {f['personaje']}: {f['texto'][:80]}")

    log("3/6 Voces")
    motor, pistas = generar_audio(frs, carpeta)
    total = montar_audio(frs, pistas, carpeta)
    gancho = gancho_del_dia(fecha) if frase else 0.0
    cierre = float(CFG.get("cierre_segundos", 0))
    limite = CFG.get("duracion_maxima", 170) - gancho - cierre
    if total > limite:  # Shorts: 3 minutos como máximo. Se acelera lo justo (sin cambiar el tono).
        factor = min(1.3, total / limite)
        ffmpeg("-i", carpeta / "audio.wav", "-filter:a", f"atempo={factor:.4f}", "-ar", HZ, "-ac", 1,
               carpeta / "audio_rapido.wav")
        (carpeta / "audio_rapido.wav").replace(carpeta / "audio.wav")
        for f in frs:
            f["inicio"], f["fin"] = f["inicio"] / factor, f["fin"] / factor
        total /= factor
        log(f"   Acelerado x{factor:.2f} para que quepa en un Short ({total:.0f} s)")
    if gancho:  # la lectura empieza cuando termina el gancho
        with wave.open(str(carpeta / "audio.wav")) as w:
            datos = w.readframes(w.getnframes())
        with wave.open(str(carpeta / "audio.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(HZ)
            w.writeframes(b"\0\0" * int(HZ * gancho) + datos)
        for f in frs:
            f["inicio"], f["fin"] = f["inicio"] + gancho, f["fin"] + gancho
        total += gancho
    if cierre:  # unos segundos más al final, solo con música, para el cierre
        with wave.open(str(carpeta / "audio.wav")) as w:
            datos = w.readframes(w.getnframes())
        with wave.open(str(carpeta / "audio.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(HZ)
            w.writeframes(datos + b"\0\0" * int(HZ * cierre))
        total += cierre
    log(f"   Motor: {motor} · duración {total:.1f} s" + ("  (más de 3 min: no será Short)" if total > 180 else ""))

    log("4/6 Cuadros")
    retrato = RAIZ / "personajes" / "evangelistas" / f"{libro.lower()}.jpg"
    retrato = retrato if retrato.exists() else None
    bl = bloques(frs, total, gancho, cierre, bool(retrato))
    if idioma == "es":  # el inglés reutiliza las imágenes del día del español: no se pinta nada
        correcciones = {str(x.get("escena")): x.get("corregir", "") for x in hecho.get("repintar") or [] if x.get("escena")}
        generar_imagenes_dia(g.get("escenas", []), sorted({b["escena"] for b in bl}), fecha, correcciones)
    presentes = {f["personaje"] for f in frs} | {k for e in g.get("escenas", []) for k in (e.get("personajes") or [])}
    visuales = elegir_visuales(bl, g.get("escenas", []), fecha, carpeta, retrato, presentes)

    log("5/6 Vídeo")
    clips = [(clip_video if es_video(v["archivo"]) else clip_escena)(v["archivo"], b["frames"], i, carpeta, b.get("tipo", "escena"))
             for i, (b, v) in enumerate(zip(bl, visuales))]
    (carpeta / "clips.txt").write_text("".join(f"file '{c.name}'\n" for c in clips))
    subtitulos(frs, ev, fecha, total, carpeta / "subtitulos.ass", frase, gancho, cierre)
    musica = musica_del_dia(fecha)
    entradas = ["-i", "audio.wav"]
    voz = "[0:a]aresample=48000,aformat=channel_layouts=stereo"
    if musica:
        log(f"   Música: {musica.name}")
        vol = CFG.get("volumen_musica", 0.10)
        filtro = (f"{voz}[v];[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol},"
                  f"atrim=0:{total:.2f},afade=t=in:st=0:d=2,afade=t=out:st={max(0.0, total - 3):.2f}:d=3[m];"
                  "[v][m]amix=inputs=2:duration=first:normalize=0[a]")
        entradas += ["-i", musica]
    else:
        filtro = f"{voz}[a]"
    ffmpeg(*entradas, "-filter_complex", filtro, "-map", "[a]", "-c:a", "pcm_s16le", "mezcla.wav", cwd=carpeta)
    lufs = normalizar_volumen(carpeta / "mezcla.wav", carpeta / "final.wav")
    ffmpeg("-f", "concat", "-safe", "0", "-i", "clips.txt", "-i", "final.wav",
           "-filter_complex", "[0:v]ass=subtitulos.ass[vid]", "-map", "[vid]", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", "video.mp4", cwd=carpeta)
    video = carpeta / "video.mp4"
    log(f"   video.mp4 · {video.stat().st_size / 1e6:.1f} MB")
    mini = None
    try:  # miniatura (YouTube 1280×720) y versión vertical (TikTok 1080×1920); si falla, se sigue sin ella
        img = imagen_miniatura(frs, frase, visuales, bl)
        if img:
            mini = miniatura(img, frase, carpeta / "miniatura.jpg")
            miniatura(img, frase, carpeta / "miniatura_vertical.jpg", (1080, 1920))
            log(f"   Miniatura: {Path(img).name}")
    except Exception as e:
        log(f"   Miniatura no creada ({e})")

    registro = {"fecha": str(fecha), "modo": a.modo, "cita": ev["cita"], "fuente": ev["url"], "texto_fuente": ev["fuente_texto"],
                "guion": g.get("origen"), "voces": motor, "peticiones_voz": len(pistas), "musica": musica.name if musica else None, "duracion_s": round(total, 1),
                "imagenes": [v["titulo"] for v in visuales],
                "frase_clave": frase, "reflexion": reflexion, "lufs": lufs,
                "gancho_segundos": gancho, "subtitulos_karaoke": bool(CFG.get("karaoke", {}).get("activo")),
                "miniatura": Path(mini).name if mini else None,
                "escenas": [{k: e.get(k) for k in ("numero", "descripcion", "busqueda", "personajes")}
                            for e in g.get("escenas", [])],
                "titulo": ev["titulo"], "texto_evangelio": ev["texto"],
                "fragmentos": [{"personaje": f["personaje"], "escena": f["escena"],
                                "inicio": round(f["inicio"], 2), "texto": f["texto"],
                                **({"reflexion": True} if f.get("reflexion") else {})} for f in frs],
                "generado": dt.datetime.now(MADRID).isoformat(timespec="seconds")}
    if os.environ.get("GITHUB_RUN_ID"):  # para encontrar después la copia del vídeo (resumen semanal)
        registro["run"] = os.environ["GITHUB_RUN_ID"]
    if idioma != "es":
        registro.update({"idioma": idioma, "libro": libro, "cita_es": ev["cita_es"]})
    if CUPO_AGOTADO:
        registro["cupo_agotado"] = sorted(CUPO_AGOTADO)
    if MODELOS_VOZ_USADOS:
        registro["modelos_voz"] = sorted(MODELOS_VOZ_USADOS)
    if CFG.get("karaoke", {}).get("alineador") == "whisper":
        oidas = [f for f in frs if f.get("sinc") == "oido"]
        por_pausas = [f["texto"][:60] for f in frs if f.get("sinc") == "pausas"]
        registro["sincronia"] = {"frases_oidas": len(oidas), "frases_por_pausas": por_pausas,
                                 "cortes_sin_oir": sorted(set(CORTES_SIN_OIR)),
                                 "ok": not CORTES_SIN_OIR and len(por_pausas) <= 1}
        log(f"   Sincronía de subtítulos: {len(oidas)} frases por lo que se oye, {len(por_pausas)} por pausas"
            + (f"; cortes sin oír: {', '.join(sorted(set(CORTES_SIN_OIR)))}" if CORTES_SIN_OIR else ""))
    if AVISOS:
        registro["avisos"] = sorted(set(AVISOS))
    if a.modo == "diario" and hecho.get("modo") == "diario" and hecho.get("youtube", {}).get("id"):
        # Se rehace un vídeo ya subido (p. ej. para mejorarlo): al subir el nuevo, «Publicar revisado» borra el viejo
        registro["reemplaza"] = hecho["youtube"]["id"]
    for k in ("rehechos", "descartados", "repintar", "repintados", "musica_bloqueada"):  # historial de versiones anteriores del mismo día
        if k in hecho:
            registro[k] = hecho[k]

    if a.modo == "diario":
        # Publicación condicionada: el revisor (rutina en la nube) revisa el episodio y, si da el OK,
        # «Publicar revisado» lo sube a YouTube programado y TikTok lo publica a la hora_publicacion (config).
        registro["revision"] = "pendiente"
        log("6/6 YouTube: pendiente de la revisión (se sube cuando el revisor dé el OK)")
    elif a.no_subir:
        log("6/6 YouTube: omitido (--no-subir)")
    else:
        log("6/6 YouTube")
        try:
            tok = token_youtube(idioma)
            vid, estado = subir_youtube(video, ev, fecha, a.modo, tok, idioma)
        except urllib.error.HTTPError as e:
            log(f"   Error de YouTube {e.code}: {e.read().decode(errors='replace')[:600]}")
            raise
        registro["youtube"] = {"id": vid, "url": f"https://youtu.be/{vid}", **estado}
        log(f"   Subido: https://youtu.be/{vid} ({estado['privacyStatus']})")
        publicar_extras(tok, vid, registro, fecha, mini, idioma)

    if idioma == "es":
        # TikTok no permite programar: se deja el texto preparado y el vídeo se publica a la hora_publicacion (tiktok-publicar.yml / Reloj).
        fecha_txt = f"{fecha.day} de {MESES[fecha.month - 1]}"
        (carpeta / "tiktok.txt").write_text(
            f"Evangelio del día · {fecha_txt} · {ev['cita']} 🙏\n\n" + (f"«{frase}»\n\n" if frase else "") + f"{ev['titulo']}\n"
            "Escúchalo con el corazón y compártelo con quien lo necesite. ✝️\n\n"
            "#EvangelioDelDia #Evangelio #PalabraDeDios #Catolico #Fe #Jesus #Dios #Oracion", encoding="utf-8")
    elif idioma == "pt":
        (carpeta / "tiktok.txt").write_text(
            f"Evangelho do dia · {fecha.day} de {MESES_PT[fecha.month - 1]} · {ev['cita']} 🙏\n\n"
            + (f"«{frase}»\n\n" if frase else "") + f"{ev['titulo']}\n"
            "Ouça com o coração e compartilhe com quem precisa. ✝️\n\n"
            "#EvangelhoDoDia #Evangelho #PalavraDeDeus #Catolico #Fe #Jesus #Deus #Oracao", encoding="utf-8")
    else:  # TikTok en inglés: fuera de alcance; la nota solo sirve de descripción de la release
        (carpeta / "tiktok.txt").write_text(f"Gospel of the day · {ev['cita']} (CatolicAid English)\n", encoding="utf-8")

    ev["musica"] = musica.name if musica else ""
    # Metadatos de YouTube tal como se subirían (para revisarlos también en las pruebas, sin subir nada)
    try:
        (carpeta / "metadatos.json").write_text(json.dumps(metadatos_youtube(ev, fecha, a.modo, idioma),
                                                           ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"   Metadatos no generados ({e})")
    texto = json.dumps(registro, ensure_ascii=False, indent=2)
    (carpeta / "guion.json").write_text(texto, encoding="utf-8")
    (RAIZ / "episodios").mkdir(exist_ok=True)
    if a.modo != "diario" and hecho.get("modo") == "diario" and (hecho.get("youtube") or hecho.get("revision")):
        log("   Prueba: no piso el registro del vídeo diario ya hecho (queda solo en salida/)")
    else:
        (RAIZ / "episodios" / f"{fecha}{suf}.json").write_text(texto, encoding="utf-8")
    resumen(registro)
    log("LISTO")


if __name__ == "__main__":
    main()
