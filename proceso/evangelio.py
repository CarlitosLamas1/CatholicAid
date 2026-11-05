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
    return "".join(c for c in t if c not in COMILLAS).strip()


def normalizar(t):
    return "".join(c for c in t if not c.isspace() and c not in COMILLAS)


# ---------- Gemini ----------

def clave_gemini():
    return {"x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()}


def gemini(modelo, cuerpo, intentos=3):
    for i in range(intentos):
        try:
            return http(f"{GEMINI}models/{modelo}:generateContent", cuerpo, clave_gemini(), timeout=300)
        except urllib.error.HTTPError as e:
            log(f"   Gemini {modelo} -> {e.code}: {e.read().decode(errors='replace')[:500]}")
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


def texto_torres_amat(cita):
    libro = cita.split()[0]
    datos = cargar_libro(libro)
    ruta_rev = RAIZ / "biblia" / "revisada" / f"{libro.lower()}.json"
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
            partes.append(ortografia(o))
        else:
            faltan.append(f"{c},{v}")
    if not vs or faltan:
        raise ValueError(f"faltan versículos: {faltan or cita}")
    texto = " ".join(partes)
    inicio = rev.get("_inicios", {}).get(f"{vs[0][0]}:{vs[0][1]}")
    if inicio is None:
        inicio = "" if vs[0] == (1, 1) else "En aquel tiempo,"
    if inicio:
        primera = texto.split()[0].strip("¿¡“«")
        if inicio.endswith(",") and primera not in NOMBRES:
            texto = texto[0].lower() + texto[1:]
        texto = f"{inicio} {texto}"
    if revisados == len(vs):
        fuente = "Torres Amat (1836), versión revisada por CatholicAid"
    elif revisados:
        fuente = "Torres Amat (1836), revisión parcial"
    else:
        fuente = "Torres Amat (1836), ortografía actualizada"
    return texto, fuente


# ---------- 2. Guion ----------

def guion_gemini(texto, clips):
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
   - "estilo": "oleo" para escenas de interior, noche o recogimiento; "acuarela" para escenas al aire libre y luminosas.{biblioteca}

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
                if re.search(r"\b(a|al|a los|a las|a sus|a su|con|de)$", antes):
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


def frase_de_reserva(fuente):
    """Si Gemini falla: la frase más corta (3–12 palabras) de las palabras de Jesús, copiada tal cual."""
    frases = [espacios(x).strip(" ,;:") for s in fuente for x in re.split(r"(?<=[.?!])\s+", s)]
    buenas = [x for x in frases if 3 <= len(x.split()) <= 12 and "…" not in x]
    return min(buenas, key=len) if buenas else ""


def gancho_y_reflexion(frs, ev, fiable=True):
    """Gemini elige la frase clave (literal, de las palabras de Jesús) y escribe una reflexión breve.
    La frase se valida: tiene que estar tal cual en el texto. El Evangelio no se toca.
    fiable=False (reparto por reglas): no se sabe con certeza quién habla, así que sin Gemini no hay gancho."""
    jesus = [hablado(f["texto"]) for f in frs if f["personaje"] == "jesus"]
    fuente = jesus or [hablado(ev["texto"])]
    propias = [espacios(hablado(re.sub(r"‘[^’]*’", " … ", f["texto"]))) for f in frs if f["personaje"] == "jesus"]
    if sum(len(re.findall(r"\w+", x)) for x in propias) >= 8:
        fuente = propias  # lo que dice Jesús con su voz, no los personajes de sus parábolas
    quien = "las palabras de Jesús" if jesus else "el texto"
    prompt = f"""Eres un sacerdote católico que prepara un vídeo breve con el Evangelio del día ({ev['cita']}).

1. "frase_clave": elige de {quien} (abajo) la frase más significativa y fácil de recordar para mostrarla en grande al
   principio del vídeo. Cópiala LITERALMENTE, palabra por palabra y con los mismos signos, sin comillas: puede ser una
   frase entera o una parte con sentido completo, de 3 a 12 palabras. Prefiere una enseñanza o promesa de Jesús
   (no una pregunta suelta ni una frase de transición) y no cojas nada que contenga «…».
2. "reflexion": 1 o 2 frases breves (máximo 35 palabras en total) para meditar después de la lectura; puede terminar
   con una pregunta. Tono cálido y cercano, de tú, en español de España. Fiel a la doctrina de la Iglesia católica y
   al sentido de esta lectura. No cites ni inventes palabras de Jesús, no uses comillas ni emojis, no hables de
   política ni de temas polémicos.

{quien.upper()}:
{chr(10).join(fuente)}

LECTURA COMPLETA (contexto):
{hablado(ev['texto'])}"""
    esquema = {"type": "OBJECT", "properties": {"frase_clave": {"type": "STRING"}, "reflexion": {"type": "STRING"}},
               "required": ["frase_clave", "reflexion"]}
    base = [espacios(s) for s in fuente]
    for modelo in modelos_texto():
        try:
            r = gemini(modelo, {"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"responseMimeType": "application/json",
                                                     "responseSchema": esquema, "temperature": 0.4}})
            partes = r["candidates"][0]["content"]["parts"]
            d = json.loads(next(p["text"] for p in reversed(partes) if "text" in p))
            frase = espacios(hablado(d.get("frase_clave", ""))).strip(" ,;:")
            reflexion = espacios(hablado(d.get("reflexion", "")))
            if not (frase and "…" not in frase and 2 <= len(frase.split()) <= 14 and any(frase in s for s in base)):
                log(f"   {modelo}: la frase clave no es literal ({frase[:60]}); se descarta")
                continue
            if not reflexion or len(reflexion.split()) > 45:
                log(f"   {modelo}: reflexión vacía o demasiado larga; se descarta")
                continue
            return frase, reflexion
        except Exception as e:
            log(f"   {modelo}: gancho/reflexión falló ({e})")
    return (frase_de_reserva(fuente) if fiable else ""), ""


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
    frs.append({"personaje": "narrador", "texto": "Palabra del Señor.", "escena": frs[-1]["escena"]})
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
    try:
        r = gemini(CFG["modelo_voz"], cuerpo)
    except urllib.error.HTTPError as e:
        pago = os.environ.get("GEMINI_API_KEY_IMAGENES", "").strip()
        if e.code != 429 or not pago:
            raise
        log("   Cupo gratuito agotado: sigo con la clave de pago (misma voz)")
        os.environ["GEMINI_API_KEY"] = pago
        r = gemini(CFG["modelo_voz"], cuerpo)
    dato = r["candidates"][0]["content"]["parts"][0]["inlineData"]
    m = re.search(r"rate=(\d+)", dato.get("mimeType", ""))
    crudo = destino.with_suffix(".raw.wav")
    with wave.open(str(crudo), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(m.group(1)) if m else HZ)
        w.writeframes(base64.b64decode(dato["data"]))
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


def voz_comprobada(p, prompt, destino, letras):
    """Graba y comprueba que la duración es razonable para el texto (≈15 letras por segundo). A veces Gemini
    devuelve un audio anómalo (silencios enormes, texto repetido o leído a medias): entonces se graba otra vez."""
    esperado = letras / 15.0
    for intento in range(3):
        voz_gemini(p, prompt, destino)
        dur = duracion(destino)
        if esperado * 0.55 - 1 <= dur <= esperado * 1.6 + 3:
            return
        log(f"   Audio anómalo: {dur:.1f} s para {letras} letras (esperado ~{esperado:.0f} s); grabo otra vez")
        time.sleep(CFG.get("pausa_tts_segundos", 21))
    raise RuntimeError(f"Gemini devuelve audios anómalos ({dur:.0f} s para ~{esperado:.0f} s); no se publica así")


def grabar_personaje(frs, indices, carpeta):
    """TODO lo que dice un personaje en UNA sola grabación (mismo tono de principio a fin), cortada en sus fragmentos.
    Devuelve {índice de fragmento: wav}."""
    quien = frs[indices[0]]["personaje"]
    p = PJ[quien]
    textos = [hablado(frs[i]["texto"]) for i in indices]
    completo = carpeta / f"voz_{quien}.wav"
    if len(indices) == 1:
        voz_comprobada(p, f"Lee en voz alta, con {p['estilo']}, este texto:\n\n{textos[0]}", completo, len(textos[0]))
        partes = [(0.0, duracion(completo))]
    else:
        voz_comprobada(p, f"Lee en voz alta, con {p['estilo']}, los siguientes párrafos, en este orden. Entre un párrafo "
                          f"y el siguiente haz siempre una pausa clara de un segundo:\n\n" + "\n\n".join(textos), completo,
                       sum(len(x) for x in textos) + 15 * (len(textos) - 1))
        dur = duracion(completo)
        letras = [len(x) for x in textos]
        candidatos = [((a + b) / 2, b - a) for a, b in silencios(completo) if 0.1 < a and b < dur - 0.1]
        cortes, previo = [], 0.0
        for k in range(1, len(indices)):
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
            salida = {}
            for n, (i, texto) in enumerate(zip(indices, textos)):
                bruto = carpeta / f"voz_{quien}_{n:02d}_b.wav"
                voz_comprobada(p, f"Lee en voz alta, con {p['estilo']}, este texto:\n\n{texto}", bruto, len(texto))
                trozo = carpeta / f"voz_{quien}_{n:02d}.wav"
                ffmpeg("-i", bruto, "-af", LIMPIAR, "-ar", HZ, "-ac", 1, "-sample_fmt", "s16", trozo)
                salida[i] = trozo
                time.sleep(CFG.get("pausa_tts_segundos", 21))
            return salida
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
    motores = ["gemini"] + (["edge"] if CFG.get("respaldo_edge") else []) if CFG.get("motor_voz") == "gemini" else ["edge"]
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
    return {k: v["descripcion"] for k, v in cat.items() if archivo_clip(k)}


def es_video(p):
    return Path(p).suffix.lower() in (".mp4", ".mov", ".webm")


AVISOS = []  # cosas que requieren a Carlos (se mandan por Telegram con el aviso de «vídeo listo»)


def generar_imagenes_dia(info, escenas, fecha):
    """Pinta con Nano Banana (API de pago) una imagen por escena y la guarda en biblioteca/dias/.
    Si ya existe (o falla), no hace nada: el proceso sigue con la biblioteca."""
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
        try:
            modelo = imagenes.generar(e["descripcion"], destino, refs, e.get("estilo", "oleo"))
            hechas += 1
            log(f"   Imagen IA escena {n} ({modelo}): {e['descripcion'][:90]}")
        except Exception as ex:
            log(f"   Imagen IA escena {n} falló ({ex}); se usa la biblioteca")
            txt = str(ex)
            if any(k in txt for k in ("429", "402", "RESOURCE_EXHAUSTED", "billing", "credit", "prepay", "quota")):
                AVISOS.append("Las imágenes de pago fallan por saldo o cuota: recarga el prepago de la API de imágenes.")
                break


def elegir_visuales(tramos, info, fecha, carpeta):
    """Por tramo: clip del día > clip elegido por Gemini > imagen devocional (D..) > cuadro clásico."""
    datos = {int(e["numero"]): e for e in info}
    ruta_cat = RAIZ / "biblioteca" / "catalogo.json"
    cat = json.loads(ruta_cat.read_text(encoding="utf-8"))["clips"] if ruta_cat.exists() else {}
    rellenos = [k for k in cat if k.startswith("D") and archivo_clip(k)]
    random.shuffle(rellenos)
    usados, visuales = set(), []
    for b in tramos:
        n, e = b["escena"], datos.get(b["escena"], {})
        if b.get("oscuro") and visuales:  # reflexión: la última imagen, oscurecida
            visuales.append(dict(visuales[-1]))
            log(f"   Tramo reflexión: {visuales[-1]['titulo']} (oscurecida)")
            continue
        propio = archivo_clip(f"{fecha}_e{n}", "dias") if b["parte"] == 0 else None
        clip = e.get("clip", "ninguno")
        if propio:
            v = {"archivo": propio, "titulo": f"dias/{propio.name}"}
        elif clip != "ninguno" and clip not in usados and archivo_clip(clip):
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

def bloques(frs, total):
    """Tramos de imagen: uno por escena, partidos para que ninguna imagen dure más de max_segundos_imagen."""
    maximo = CFG.get("max_segundos_imagen", 16)
    b = []
    for f in frs:
        oscuro = bool(f.get("reflexion"))  # la reflexión (y el cierre) van sobre la imagen oscurecida
        if not b or b[-1]["escena"] != f["escena"] or b[-1]["oscuro"] != oscuro:
            b.append({"escena": f["escena"], "inicio": f["inicio"], "oscuro": oscuro})
    b[0]["inicio"] = 0.0
    tramos = []
    for i, x in enumerate(b):
        fin = b[i + 1]["inicio"] if i + 1 < len(b) else total
        partes = max(1, int(-(-(fin - x["inicio"]) // maximo)))
        paso = (fin - x["inicio"]) / partes
        for k in range(partes):
            ini = x["inicio"] + k * paso
            tramos.append({"escena": x["escena"], "parte": k, "inicio": ini, "oscuro": x["oscuro"],
                           "frames": max(1, round((ini + paso) * FPS) - round(ini * FPS))})
    return tramos


OSCURO = "eq=brightness=-0.14:saturation=0.55,gblur=sigma=6,"


def clip_escena(img, frames, n, carpeta, oscuro=False):
    """Zoom lento y suave (acercar o alejar, alternando). Cada fotograma se calcula con precisión subpíxel
    (Pillow), así la imagen no «tiembla» como con zoompan, que redondea a píxeles enteros."""
    from PIL import Image
    zoom = CFG.get("zoom_imagen", 0.08)
    mw, mh = round(W * (1 + zoom)), round(H * (1 + zoom))
    marco = carpeta / f"marco_{n}.png"
    ffmpeg("-i", img, "-vf",
           f"scale={mw}:{mh}:force_original_aspect_ratio=increase:flags=lanczos,crop={mw}:{mh},"
           + (OSCURO if oscuro else "") + "eq=saturation=1.08:brightness=0.02,vignette=PI/5", "-frames:v", 1, marco)
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


def clip_video(origen, frames, n, carpeta, oscuro=False):
    """Clip de la biblioteca: cámara lenta, ida y vuelta (sin cortes) y relleno vertical 9:16."""
    dur = frames / FPS
    base = carpeta / f"base_{n:02d}.mp4"
    ffmpeg("-i", origen, "-an", "-filter_complex",
           f"[0:v]setpts=1.5*PTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
           f"crop={W}:{H}," + (OSCURO if oscuro else "") + "eq=saturation=1.05,vignette=PI/5,split[f][r0];[r0]reverse[r];[f][r]concat=n=2:v=1:a=0,format=yuv420p[v]",
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


def subtitulos(frs, ev, fecha, total, ruta, frase="", gancho=0.0, cierre=0.0):
    eventos = [("Cabecera", gancho, total - cierre,
                "{\\fs38}Evangelio del día · " + f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"
                + "\\N{\\fs56}" + ev["cita"])]
    if frase and gancho:
        # Gancho minimalista: velo oscuro muy suave sobre la imagen y la frase en serif fina, centrada.
        eventos.append(("Velo", 0, gancho, "{\\an7\\pos(0,0)\\p1\\fad(0,350)}"
                        f"m 0 0 l {W} 0 {W} {H} 0 {H}" + "{\\p0}"))
        limpio = frase.replace("{", "(").replace("}", ")")
        eventos.append(("Gancho", 0, gancho, "{\\fad(250,350)\\blur3}“" + limpio + "”"))
    if cierre:
        # Cierre minimalista sobre la imagen oscurecida: invitación a seguir el canal.
        eventos.append(("Gancho", total - cierre, total, "{\\fad(300,400)\\blur2\\fs64}Síguenos para escuchar\\N"
                        "el Evangelio cada día\\N{\\fs40\\i0\\c" + color_ass("F5C542") + "}CatolicAid"))
    for f in frs:
        p = PJ[f["personaje"]]
        limpio = hablado(f["texto"]).replace("{", "(").replace("}", ")")
        trozos = trocear(limpio, CFG.get("caracteres_por_subtitulo", 46))
        largo = sum(len(x) for x in trozos)
        t, dur = f["inicio"], f["fin"] - f["inicio"]
        nombre = ""
        if p.get("nombre"):
            nombre = "{\\fs40\\c" + color_ass(p["color"]) + "}" + p["nombre"].upper() + "\\N"
        estilo = "{\\fs60\\c" + color_ass(p.get("color_texto", "FFFFFF")) + "}"
        if f.get("reflexion"):
            nombre, estilo = "", "{\\fs56\\i1\\c" + color_ass("F3E6C4") + "}"
        for tr in trozos:
            d = dur * len(tr) / largo
            eventos.append(("Texto", t, t + d, nombre + estilo + tr))
            t += d
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


def musica_del_dia(fecha):
    """Música clásica de dominio público (Wikimedia Commons), rotando por días; se guarda en musica/."""
    pistas = CFG.get("musica", [])
    if not pistas:
        return None
    nombre = pistas[fecha.toordinal() % len(pistas)].replace(" ", "_")
    ruta = RAIZ / "musica" / nombre
    if not ruta.exists():
        try:
            url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(nombre)
            datos = http(url, raw=True, timeout=180)[1]
            ruta.parent.mkdir(exist_ok=True)
            ruta.write_bytes(datos)
        except Exception as e:
            log(f"   Sin música ({e})")
            return None
    return ruta


def medir(ruta, extra=""):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(ruta), "-af",
                        f"loudnorm=I=-14:TP=-1.5:LRA=11{extra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])


def normalizar_volumen(origen, destino):
    """Audio final a -14 LUFS (estándar de YouTube/TikTok), en dos pasadas y con pico real máximo de -1,5 dB."""
    m = medir(origen)
    medidas = ":".join(f"measured_{k}={m['input_' + k]}" for k in ("i", "tp", "lra", "thresh"))
    ffmpeg("-i", origen, "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11:{medidas}:offset={m['target_offset']}:linear=true,"
           "aresample=48000", "-ar", 48000, "-ac", 2, "-c:a", "pcm_s16le", destino)
    final = float(medir(destino)["input_i"])
    log(f"   Volumen: {float(m['input_i']):.1f} → {final:.1f} LUFS")
    return round(final, 1)


# ---------- 6. YouTube ----------

YT = "https://www.googleapis.com/youtube/v3/"
LISTAS = {"Mateo": "Evangelio según san Mateo", "Marcos": "Evangelio según san Marcos",
          "Lucas": "Evangelio según san Lucas", "Juan": "Evangelio según san Juan"}


def token_youtube():
    r = http("https://oauth2.googleapis.com/token", urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(),
        "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"}).encode())
    log(f"   Permisos de YouTube: {r.get('scope', '?')}")
    return r["access_token"]


def lista_evangelista(tok, libro, vid):
    """Añade el vídeo a la lista del evangelista (la crea si no existe). Si falla, no impide la publicación."""
    titulo = LISTAS.get(libro)
    if not titulo:
        return None
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
                "snippet": {"title": titulo, "defaultLanguage": "es",
                            "description": f"El Evangelio del día según san {libro}, leído con varias voces. "
                                           "Un vídeo nuevo cada mañana. #EvangelioDelDia"},
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


def subir_youtube(video, ev, fecha, modo, tok):
    fecha_txt = f"{fecha.day} de {MESES[fecha.month - 1]}"
    titulo = f"Evangelio del día · {fecha_txt} · {ev['cita']}"
    frase = (ev.get("frase_clave") or "").strip(" .,;:")
    if frase:  # «“Frase” | Evangelio del día 6 de noviembre (Lucas 16, 1-8)», recortando la frase si no cabe
        frase = frase[0].upper() + frase[1:]
        corto = f"{fecha.day} {MESES[fecha.month - 1][:3]}"
        opciones = [f" | Evangelio del día {fecha_txt} ({ev['cita']})", f" | Evangelio {corto} · {ev['cita']}",
                    f" | Evangelio · {ev['cita']}"]
        resto = next((r for r in opciones if len(frase) + 2 + len(r) <= 100), opciones[-1])
        hueco = 100 - len(resto) - 2
        if len(frase) > hueco:
            frase = frase[:hueco - 1].rsplit(" ", 1)[0] + "…"
        titulo = f"“{frase}”{resto}"
    elif len(titulo) <= 90:
        titulo += " #shorts"
    descripcion = (f"{ev['titulo']}\n{ev['cita']}\n\n"
                   f"Evangelio del {DIAS[fecha.weekday()]} {fecha_txt} de {fecha.year}, leído con varias voces.\n\n"
                   + (f"🕊️ Para meditar: {ev['reflexion']}\n\n" if ev.get("reflexion") else "") +
                   f"📖 Texto: {ev.get('fuente_texto', 'Vatican News')}. Calendario litúrgico: Vatican News.\n"
                   "🎨 Imágenes: escenas generadas con IA y cuadros de James Tissot (dominio público)\n"
                   "🎙️ Voces generadas con inteligencia artificial.\n\n"
                   "#Shorts #EvangelioDelDia #Evangelio #PalabraDeDios #Catolico")
    estado = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if modo == "diario":
        hora = dt.datetime.combine(fecha, dt.time(CFG.get("hora_publicacion", 7)), MADRID)
        if hora > dt.datetime.now(MADRID) + dt.timedelta(minutes=30):
            estado["publishAt"] = hora.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {"snippet": {"title": titulo[:100], "description": descripcion[:4900], "categoryId": "22",
                        "tags": ["evangelio del día", "evangelio", "católico", "palabra de Dios",
                                 ev["cita"].split()[0]],
                        "defaultLanguage": "es", "defaultAudioLanguage": "es"}, "status": estado}
    r, _ = http("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                meta, {"Authorization": f"Bearer {tok}", "X-Upload-Content-Type": "video/mp4",
                       "X-Upload-Content-Length": str(video.stat().st_size)}, method="POST", raw=True)
    req = urllib.request.Request(r.headers["Location"], data=video.read_bytes(), method="PUT",
                                 headers={"Content-Type": "video/mp4", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=900) as r2:
        res = json.loads(r2.read())
    return res["id"], estado


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", default="")
    ap.add_argument("--modo", choices=["prueba", "diario"], default="prueba")
    ap.add_argument("--no-subir", action="store_true")
    ap.add_argument("--si-falta", action="store_true", help="no hace nada si ese día ya está subido (reintentos)")
    a = ap.parse_args()
    fecha = (dt.date.fromisoformat(a.fecha.strip()) if a.fecha.strip()
             else dt.datetime.now(MADRID).date() + dt.timedelta(days=1))
    previo = RAIZ / "episodios" / f"{fecha}.json"
    hecho = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {}
    if a.si_falta and hecho.get("modo") == "diario" and (
            "youtube" in hecho or hecho.get("revision") in ("pendiente", "ok") or hecho.get("no_publicar")):
        log(f"El vídeo del {fecha} ya está hecho ({hecho.get('revision') or 'subido'}); nada que hacer.")
        return
    carpeta = RAIZ / "salida" / fecha.isoformat()
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    log(f"== Evangelio del {fecha} (modo {a.modo}) ==")

    log("1/6 Evangelio")
    ev = obtener_evangelio(fecha)
    if CFG.get("texto") == "torres-amat":
        try:
            ev["texto"], ev["fuente_texto"] = texto_torres_amat(ev["cita"])
        except Exception as e:
            log(f"   Torres Amat no disponible ({e}); uso el texto de Vatican News")
    ev.setdefault("fuente_texto", "Vatican News")
    log(f"   {ev['cita']} · {ev['fuente_texto']} · {len(ev['texto'])} caracteres")
    libro = ev["cita"].split()[0]
    if libro in CFG.get("narradores", {}):
        PJ["narrador"] = {**PJ["narrador"], **CFG["narradores"][libro]}
        log(f"   Narrador: san {libro} (voz {PJ['narrador']['voz_gemini']})")

    log("2/6 Guion")
    biblioteca = clips_disponibles()
    log(f"   Biblioteca: {len(biblioteca)} clips disponibles")
    g = guion_gemini(ev["texto"], biblioteca)
    if not g and a.modo == "diario" and dt.datetime.now(dt.timezone.utc).hour < 21:
        raise RuntimeError("Gemini no ha podido repartir las voces: no publico con un reparto dudoso. "
                           "Se reintenta en la próxima tirada (el último intento, a las 21 UTC, usa reglas).")
    if not g:
        log("   Gemini no disponible o no fiel: uso reglas por comillas")
        g = guion_reglas(ev["texto"])
    frs = preparar_fragmentos(g, ev)
    busquedas = {int(e["numero"]): e["busqueda"] for e in g.get("escenas", [])}
    frase, reflexion = gancho_y_reflexion(frs, ev, g.get("origen") != "reglas")
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
    gancho = float(CFG.get("gancho_segundos", 2.0)) if frase else 0.0
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
    bl = bloques(frs, total)
    generar_imagenes_dia(g.get("escenas", []), sorted({b["escena"] for b in bl}), fecha)
    visuales = elegir_visuales(bl, g.get("escenas", []), fecha, carpeta)

    log("5/6 Vídeo")
    clips = [(clip_video if es_video(v["archivo"]) else clip_escena)(v["archivo"], b["frames"], i, carpeta, b.get("oscuro", False))
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

    registro = {"fecha": str(fecha), "modo": a.modo, "cita": ev["cita"], "fuente": ev["url"], "texto_fuente": ev["fuente_texto"],
                "guion": g.get("origen"), "voces": motor, "peticiones_voz": len(pistas), "musica": musica.name if musica else None, "duracion_s": round(total, 1),
                "imagenes": [v["titulo"] for v in visuales],
                "frase_clave": frase, "reflexion": reflexion, "lufs": lufs,
                "titulo": ev["titulo"], "texto_evangelio": ev["texto"],
                "fragmentos": [{"personaje": f["personaje"], "escena": f["escena"],
                                "inicio": round(f["inicio"], 2), "texto": f["texto"],
                                **({"reflexion": True} if f.get("reflexion") else {})} for f in frs],
                "generado": dt.datetime.now(MADRID).isoformat(timespec="seconds")}
    if AVISOS:
        registro["avisos"] = sorted(set(AVISOS))
    for k in ("rehechos", "descartados"):  # historial de versiones anteriores del mismo día
        if k in hecho:
            registro[k] = hecho[k]

    if a.modo == "diario":
        # Publicación condicionada: el revisor (rutina en la nube) revisa el episodio y, si da el OK,
        # «Publicar revisado» lo sube a YouTube programado y TikTok lo publica a las 7:00.
        registro["revision"] = "pendiente"
        log("6/6 YouTube: pendiente de la revisión (se sube cuando el revisor dé el OK)")
    elif a.no_subir:
        log("6/6 YouTube: omitido (--no-subir)")
    else:
        log("6/6 YouTube")
        try:
            tok = token_youtube()
            vid, estado = subir_youtube(video, ev, fecha, a.modo, tok)
        except urllib.error.HTTPError as e:
            log(f"   Error de YouTube {e.code}: {e.read().decode(errors='replace')[:600]}")
            raise
        registro["youtube"] = {"id": vid, "url": f"https://youtu.be/{vid}", **estado}
        log(f"   Subido: https://youtu.be/{vid} ({estado['privacyStatus']})")
        lista = lista_evangelista(tok, libro, vid)
        if lista:
            registro["youtube"]["lista"] = lista

    # TikTok no permite programar: se deja el texto preparado y el vídeo se publica a las 7:00 (tiktok-publicar.yml).
    fecha_txt = f"{fecha.day} de {MESES[fecha.month - 1]}"
    (carpeta / "tiktok.txt").write_text(
        f"Evangelio del día · {fecha_txt} · {ev['cita']} 🙏\n\n" + (f"«{frase}»\n\n" if frase else "") + f"{ev['titulo']}\n"
        "Escúchalo con el corazón y compártelo con quien lo necesite. ✝️\n\n"
        "#EvangelioDelDia #Evangelio #PalabraDeDios #Catolico #Fe #Jesus #Dios #Oracion", encoding="utf-8")

    texto = json.dumps(registro, ensure_ascii=False, indent=2)
    (carpeta / "guion.json").write_text(texto, encoding="utf-8")
    (RAIZ / "episodios").mkdir(exist_ok=True)
    (RAIZ / "episodios" / f"{fecha}.json").write_text(texto, encoding="utf-8")
    resumen(registro)
    log("LISTO")


if __name__ == "__main__":
    main()
