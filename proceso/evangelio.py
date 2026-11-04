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
    extra = sorted((n for n in nombres if "flash" in n and n not in preferidos
                    and not re.search(r"tts|image|live|audio|embed|exp", n)), reverse=True)
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


# ---------- 2. Guion ----------

def guion_gemini(texto):
    lista = "\n".join(f"- {k}: {v['descripcion']}" for k, v in PJ.items())
    prompt = f"""Prepara una lectura dramatizada del Evangelio con varias voces.

PERSONAJES (usa solo estas claves):
{lista}

REGLAS:
1. Divide el texto en fragmentos consecutivos. Copia cada fragmento EXACTAMENTE igual que en el original: no añadas, quites ni cambies ninguna palabra ni signo. Unidos en orden, los fragmentos deben reproducir el texto completo.
2. Las palabras en estilo directo (entre comillas “ ”) van en un fragmento propio, asignado a quien las dice. Si alguien cita a otro dentro de su discurso (comillas ‘ ’), sigue hablando el mismo personaje. Todo lo demás es del narrador.
3. Si habla un personaje secundario que no está en la lista, usa hombre, mujer o multitud.
4. Agrupa el relato en 2 a 4 escenas visuales. En cada fragmento indica su escena (1, 2, ...). Para cada escena da "busqueda": 1 a 3 palabras en inglés para encontrar un cuadro de James Tissot de esa escena (ej.: "good shepherd", "Pharisees", "Jesus teaching", "Peter").

TEXTO:
{texto}"""
    esquema = {"type": "OBJECT", "properties": {
        "fragmentos": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "personaje": {"type": "STRING", "enum": list(PJ)},
            "texto": {"type": "STRING"},
            "escena": {"type": "INTEGER"}}, "required": ["personaje", "texto", "escena"]}},
        "escenas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "numero": {"type": "INTEGER"}, "busqueda": {"type": "STRING"}},
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
            i = narracion.rfind(a)
            if i > pos:
                mejor, pos = k, i
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

def a_wav_estandar(origen, destino):
    ffmpeg("-i", origen, "-ar", HZ, "-ac", 1, "-sample_fmt", "s16", destino)


def lotes_gemini(frs):
    """Agrupa fragmentos consecutivos de como mucho 2 personajes: 1 petición de voz por grupo."""
    maximo = CFG.get("max_caracteres_lote", 2500)
    lotes, actual, voces, largo = [], [], set(), 0
    for i, f in enumerate(frs):
        n = len(hablado(f["texto"]))
        if actual and (len(voces | {f["personaje"]}) > 2 or largo + n > maximo):
            lotes.append(actual)
            actual, voces, largo = [], set(), 0
        actual.append(i)
        voces.add(f["personaje"])
        largo += n
    if actual:
        lotes.append(actual)
    return lotes


def tts_gemini(frs, lote, destino):
    voces = list(dict.fromkeys(frs[i]["personaje"] for i in lote))
    if len(voces) == 1:
        p = PJ[voces[0]]
        texto = f"{p['estilo']}: " + " ".join(hablado(frs[i]["texto"]) for i in lote)
        habla = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": p["voz_gemini"]}}}
    else:
        guia = " ".join(f"Voz de {k.capitalize()}: {PJ[k]['estilo']}." for k in voces)
        lineas = "\n".join(f"{frs[i]['personaje'].capitalize()}: {hablado(frs[i]['texto'])}" for i in lote)
        texto = f"Lee en voz alta esta lectura del Evangelio a dos voces. {guia}\n\n{lineas}"
        habla = {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
            {"speaker": k.capitalize(), "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": PJ[k]["voz_gemini"]}}}
            for k in voces]}}
    cuerpo = {"contents": [{"parts": [{"text": texto}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": habla}}
    r = gemini(CFG["modelo_voz"], cuerpo)
    dato = r["candidates"][0]["content"]["parts"][0]["inlineData"]
    m = re.search(r"rate=(\d+)", dato.get("mimeType", ""))
    tasa = int(m.group(1)) if m else HZ
    crudo = destino.with_suffix(".raw.wav")
    with wave.open(str(crudo), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tasa)
        w.writeframes(base64.b64decode(dato["data"]))
    a_wav_estandar(crudo, destino)


def tts_edge(f, destino):
    p = PJ[f["personaje"]]
    mp3 = destino.with_suffix(".mp3")
    subprocess.run(["edge-tts", f"--voice={p['voz_edge']}", f"--rate={p.get('velocidad_edge', '-5%')}",
                    "--text", hablado(f["texto"]), "--write-media", str(mp3)], check=True)
    a_wav_estandar(mp3, destino)


def generar_audio(frs, carpeta):
    motores = ["gemini", "edge"] if CFG.get("motor_voz") == "gemini" else ["edge"]
    for motor in motores:
        lotes = lotes_gemini(frs) if motor == "gemini" else [[i] for i in range(len(frs))]
        try:
            pistas = []
            for j, lote in enumerate(lotes):
                destino = carpeta / f"voz_{motor}_{j:02d}.wav"
                quienes = " + ".join(dict.fromkeys(frs[i]["personaje"] for i in lote))
                log(f"   [{motor}] petición {j + 1}/{len(lotes)}: {quienes}")
                if motor == "gemini":
                    if j:
                        time.sleep(CFG.get("pausa_tts_segundos", 21))
                    tts_gemini(frs, lote, destino)
                else:
                    tts_edge(frs[lote[0]], destino)
                pistas.append({"archivo": destino.name, "fragmentos": lote})
            return motor, pistas
        except Exception as e:
            log(f"   El motor de voz {motor} falló: {e}")
    raise RuntimeError("Ningún motor de voz funcionó")


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
    gen = CFG["busquedas_genericas"]
    for q in ([busqueda] if busqueda else []) + random.sample(gen, len(gen)):
        r = http("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "format": "json", "list": "search", "srnamespace": 6, "srlimit": 20,
            "srsearch": f'intitle:"James Tissot" {q} filetype:bitmap'}))
        titulos = [x["title"] for x in r.get("query", {}).get("search", []) if x["title"] not in usados]
        if titulos:
            t = titulos[0] if q == busqueda else random.choice(titulos[:10])
            usados.add(t)
            return t
    raise RuntimeError("No encuentro cuadros en Wikimedia Commons")


def elegir_cuadros(escenas, busquedas, carpeta):
    usados, cuadros = set(), {}
    for n in escenas:
        titulo = buscar_cuadro(busquedas.get(n, ""), usados)
        nombre = titulo.split(":", 1)[1].replace(" ", "_")
        url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(nombre) + "?width=1400"
        destino = carpeta / f"cuadro_{n}.img"
        destino.write_bytes(http(url, raw=True)[1])
        cuadros[n] = {"archivo": destino, "titulo": titulo}
        log(f"   Escena {n}: {titulo}")
    return cuadros


# ---------- 5. Vídeo ----------

def bloques(frs, total):
    b = []
    for f in frs:
        if not b or b[-1]["escena"] != f["escena"]:
            b.append({"escena": f["escena"], "inicio": f["inicio"]})
    b[0]["inicio"] = 0.0
    for i, x in enumerate(b):
        fin = b[i + 1]["inicio"] if i + 1 < len(b) else total
        x["frames"] = max(1, round(fin * FPS) - round(x["inicio"] * FPS))
    return b


def clip_escena(img, frames, n, carpeta):
    marco = carpeta / f"marco_{n}.png"
    ffmpeg("-i", img, "-filter_complex",
           f"[0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:3,"
           f"eq=brightness=-0.30[bg];[0]scale=1000:860:force_original_aspect_ratio=decrease[fg];"
           f"[bg][fg]overlay=(W-w)/2:290+(860-h)/2", "-frames:v", 1, marco)
    dur = frames / FPS
    z = f"1+0.10*on/{frames}" if n % 2 == 0 else f"1.10-0.10*on/{frames}"
    salida = carpeta / f"clip_{n:02d}.mp4"
    ffmpeg("-loop", 1, "-framerate", FPS, "-i", marco, "-vf",
           f"scale={int(W * 1.5)}:{int(H * 1.5)},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
           f":d=1:s={W}x{H}:fps={FPS},fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.0, dur - 0.4):.2f}:d=0.4",
           "-frames:v", frames, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", salida)
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


def subtitulos(frs, ev, fecha, total, ruta):
    eventos = [("Cabecera", 0, total,
                "{\\fs38}Evangelio del día · " + f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"
                + "\\N{\\fs56}" + ev["cita"])]
    for f in frs:
        p = PJ[f["personaje"]]
        limpio = hablado(f["texto"]).replace("{", "(").replace("}", ")")
        trozos = trocear(limpio, CFG.get("caracteres_por_subtitulo", 46))
        largo = sum(len(x) for x in trozos)
        t, dur = f["inicio"], f["fin"] - f["inicio"]
        nombre = ""
        if p.get("nombre"):
            nombre = "{\\fs40\\c" + color_ass(p["color"]) + "}" + p["nombre"].upper() + "\\N"
        for tr in trozos:
            d = dur * len(tr) / largo
            eventos.append(("Texto", t, t + d,
                            nombre + "{\\fs60\\c" + color_ass(p.get("color_texto", "FFFFFF")) + "}" + tr))
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
        "60,60,120,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    cuerpo = "".join(f"Dialogue: 0,{ts(a)},{ts(b)},{s},,0,0,0,,{x}\n" for s, a, b, x in eventos)
    ruta.write_text(cabecera + cuerpo, encoding="utf-8")


# ---------- 6. YouTube ----------

def subir_youtube(video, ev, fecha, modo):
    tok = http("https://oauth2.googleapis.com/token", urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(),
        "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"}).encode())["access_token"]
    fecha_txt = f"{fecha.day} de {MESES[fecha.month - 1]}"
    titulo = f"Evangelio del día · {fecha_txt} · {ev['cita']}"
    if len(titulo) <= 90:
        titulo += " #shorts"
    descripcion = (f"{ev['titulo']}\n{ev['cita']}\n\n"
                   f"Evangelio del {DIAS[fecha.weekday()]} {fecha_txt} de {fecha.year}, leído con varias voces.\n\n"
                   f"📖 Texto: Vatican News · {ev['url']}\n"
                   "🎨 Imágenes: James Tissot, Brooklyn Museum (dominio público, Wikimedia Commons)\n"
                   "🎙️ Voces generadas con inteligencia artificial.\n\n"
                   "#EvangelioDelDia #Evangelio #PalabraDeDios #Catolico")
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
    a = ap.parse_args()
    fecha = (dt.date.fromisoformat(a.fecha.strip()) if a.fecha.strip()
             else dt.datetime.now(MADRID).date() + dt.timedelta(days=1))
    carpeta = RAIZ / "salida" / fecha.isoformat()
    shutil.rmtree(carpeta, ignore_errors=True)
    carpeta.mkdir(parents=True)
    log(f"== Evangelio del {fecha} (modo {a.modo}) ==")

    log("1/6 Evangelio")
    ev = obtener_evangelio(fecha)
    log(f"   {ev['cita']} · {len(ev['texto'])} caracteres")

    log("2/6 Guion")
    g = guion_gemini(ev["texto"])
    if not g:
        log("   Gemini no disponible o no fiel: uso reglas por comillas")
        g = guion_reglas(ev["texto"])
    frs = preparar_fragmentos(g, ev)
    busquedas = {int(e["numero"]): e["busqueda"] for e in g.get("escenas", [])}
    for f in frs:
        log(f"   [{f['escena']}] {f['personaje']}: {f['texto'][:80]}")

    log("3/6 Voces")
    motor, pistas = generar_audio(frs, carpeta)
    total = montar_audio(frs, pistas, carpeta)
    log(f"   Motor: {motor} · duración {total:.1f} s" + ("  (más de 3 min: no será Short)" if total > 180 else ""))

    log("4/6 Cuadros")
    bl = bloques(frs, total)
    cuadros = elegir_cuadros(sorted({b["escena"] for b in bl}), busquedas, carpeta)

    log("5/6 Vídeo")
    clips = [clip_escena(cuadros[b["escena"]]["archivo"], b["frames"], i, carpeta) for i, b in enumerate(bl)]
    (carpeta / "clips.txt").write_text("".join(f"file '{c.name}'\n" for c in clips))
    subtitulos(frs, ev, fecha, total, carpeta / "subtitulos.ass")
    ffmpeg("-f", "concat", "-safe", "0", "-i", "clips.txt", "-i", "audio.wav", "-vf", "ass=subtitulos.ass",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", "video.mp4", cwd=carpeta)
    video = carpeta / "video.mp4"
    log(f"   video.mp4 · {video.stat().st_size / 1e6:.1f} MB")

    registro = {"fecha": str(fecha), "modo": a.modo, "cita": ev["cita"], "fuente": ev["url"],
                "guion": g.get("origen"), "voces": motor, "peticiones_voz": len(pistas), "duracion_s": round(total, 1),
                "cuadros": {str(k): v["titulo"] for k, v in cuadros.items()},
                "fragmentos": [{"personaje": f["personaje"], "escena": f["escena"],
                                "inicio": round(f["inicio"], 2), "texto": f["texto"]} for f in frs],
                "generado": dt.datetime.now(MADRID).isoformat(timespec="seconds")}

    if a.no_subir:
        log("6/6 YouTube: omitido (--no-subir)")
    else:
        log("6/6 YouTube")
        try:
            vid, estado = subir_youtube(video, ev, fecha, a.modo)
        except urllib.error.HTTPError as e:
            log(f"   Error de YouTube {e.code}: {e.read().decode(errors='replace')[:600]}")
            raise
        registro["youtube"] = {"id": vid, "url": f"https://youtu.be/{vid}", **estado}
        log(f"   Subido: https://youtu.be/{vid} ({estado['privacyStatus']})")

    texto = json.dumps(registro, ensure_ascii=False, indent=2)
    (carpeta / "guion.json").write_text(texto, encoding="utf-8")
    (RAIZ / "episodios").mkdir(exist_ok=True)
    (RAIZ / "episodios" / f"{fecha}.json").write_text(texto, encoding="utf-8")
    resumen(registro)
    log("LISTO")


if __name__ == "__main__":
    main()
