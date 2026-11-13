"""Prueba exhaustiva de los modelos de voz de Gemini con la clave GRATUITA para el portugués.
Para cada modelo de voz: 1) graba un texto real con la instrucción de estilo del canal y lo transcribe (¿lee la
instrucción?, ¿lee el texto entero?); 2) en los modelos que NO usan el español ni el inglés, mide el cupo gratis
diario pidiendo frases cortas hasta el 429 (máx. 40)."""
import base64, json, os, re, time, urllib.error, urllib.request
import numpy as np

G = "https://generativelanguage.googleapis.com/v1beta/models"
H = {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()}
USADOS = {"gemini-2.5-flash-preview-tts": "español", "gemini-3.1-flash-tts-preview": "inglés"}
ESTILO = ("the voice of an adult man, warm, harmonious and tender, full of love and serene authority, natural pace, "
          "natural Brazilian Portuguese accent (from São Paulo), clear and warm")
TEXTO = ("Como aconteceu nos dias de Noé, assim também acontecerá nos dias do Filho do Homem. Comiam e bebiam, "
         "casavam-se e davam-se em casamento, até o dia em que Noé entrou na arca. Lembrem-se da mulher de Ló.")
PROMPTS = {"con instrucción (como el canal)": f"Leia em voz alta, com {ESTILO}, o seguinte texto:\n\n{TEXTO}",
           "solo el texto": TEXTO}


def pedir(modelo, texto, voz="Enceladus"):
    cuerpo = {"contents": [{"parts": [{"text": texto}]}], "generationConfig": {"responseModalities": ["AUDIO"],
              "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
    req = urllib.request.Request(f"{G}/{modelo}:generateContent", json.dumps(cuerpo).encode(), H)
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    dato = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    bruto = base64.b64decode(dato["data"])
    if bruto[:4] == b"RIFF":
        bruto = bruto[44:]
    rate = int((re.search(r"rate=(\d+)", dato.get("mimeType", "")) or [0, 24000])[1])
    return np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0, rate


def error429(e):
    t = e.read().decode(errors="replace")
    return t, re.findall(r'"quotaId":\s*"([^"]+)".*?"quotaValue":\s*"?(\d+)', t, re.S) or re.findall(r"limit: (\d+)", t)


from faster_whisper import WhisperModel
w = WhisperModel("small", compute_type="int8")


def oir(audio, rate):
    if rate != 16000:
        x = np.linspace(0, len(audio), int(len(audio) * 16000 / rate), endpoint=False)
        audio = np.interp(x, np.arange(len(audio)), audio).astype(np.float32)
    segs, _ = w.transcribe(audio, language="pt")
    return " ".join(s.text.strip() for s in segs), len(audio) / 16000


with urllib.request.urlopen(urllib.request.Request(G + "?pageSize=300", headers=H), timeout=60) as r:
    todos = json.loads(r.read())["models"]
voz = [m["name"].split("/")[-1] for m in todos
       if re.search(r"tts|audio|speech|voice", m["name"]) and "generateContent" in m.get("supportedGenerationMethods", [])]
otros = [m["name"].split("/")[-1] + " (" + ",".join(m.get("supportedGenerationMethods", [])) + ")" for m in todos
         if re.search(r"tts|audio|speech|voice|live", m["name"]) and "generateContent" not in m.get("supportedGenerationMethods", [])]
print("MODELOS DE VOZ (generateContent):", ", ".join(voz))
print("OTROS DE AUDIO (no sirven para grabar un texto):", ", ".join(otros) or "ninguno")
print()
for modelo in voz:
    print(f"=== {modelo}" + (f" (lo usa el {USADOS[modelo]}: solo 1 prueba)" if modelo in USADOS else ""))
    for nombre, p in PROMPTS.items():
        if modelo in USADOS and nombre != "con instrucción (como el canal)":
            continue
        try:
            audio, rate = pedir(modelo, p)
            oido, seg = oir(audio, rate)
            lee_instr = bool(re.search(r"leia|voz alta|voice|accent|sotaque|warm|serene", oido, re.I))
            print(f"  [{nombre}] {seg:.1f} s · lee la instrucción: {'SÍ ❌' if lee_instr else 'no ✅'}")
            print(f"     oído: {oido[:260]}")
        except urllib.error.HTTPError as e:
            t, lim = error429(e) if e.code == 429 else (e.read().decode(errors='replace'), [])
            print(f"  [{nombre}] ERROR {e.code} {lim or t[:200]}")
        except Exception as e:
            print(f"  [{nombre}] ERROR {type(e).__name__}: {e}")
        time.sleep(7)
    if modelo in USADOS:
        continue
    n = 0
    for i in range(40):
        try:
            pedir(modelo, "Amém.")
            n += 1
        except urllib.error.HTTPError as e:
            if e.code == 429:
                t, lim = error429(e)
                if re.search(r"PerMinute", t) and not re.search(r"PerDay", t):
                    print(f"  (límite por minuto tras {n}; espero 65 s) {lim}")
                    time.sleep(65)
                    continue
                print(f"  CUPO: se agota tras {n} peticiones más hoy · límite informado: {lim or t[:300]}")
                break
            print(f"  cupo: error {e.code} tras {n}")
            break
        except Exception as e:
            print(f"  cupo: {type(e).__name__} tras {n}")
            break
        time.sleep(7)
    else:
        print(f"  CUPO: {n} peticiones más sin agotarse (da para un vídeo)")
    print()
