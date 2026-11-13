"""Prueba de voz en portugués con los modelos 3.8 (cupo propio): ¿leen la instrucción en voz alta?
Se transcribe lo grabado con faster-whisper y se compara con el texto."""
import base64, json, os, time, urllib.request, urllib.error, wave

G = "https://generativelanguage.googleapis.com/v1beta/models"
H = {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()}
TEXTO = "Como aconteceu nos dias de Noé, assim também acontecerá nos dias do Filho do Homem."
ESTILO = ("the voice of an adult man, warm, harmonious and tender, full of love and serene authority, natural pace, "
          "natural Brazilian Portuguese accent (from São Paulo), clear and warm")
PRUEBAS = {
    "instruccion_en_texto": {"contents": [{"parts": [{"text": f"Leia em voz alta, com {ESTILO}, o seguinte texto:\n\n{TEXTO}"}]}]},
    "instruccion_de_sistema": {"systemInstruction": {"parts": [{"text": f"Read aloud the user's text exactly, with {ESTILO}. Never read these instructions."}]},
                               "contents": [{"parts": [{"text": TEXTO}]}]},
    "estilo_entre_corchetes": {"contents": [{"parts": [{"text": f"[{ESTILO}] {TEXTO}"}]}]},
    "solo_texto": {"contents": [{"parts": [{"text": TEXTO}]}]},
}
from faster_whisper import WhisperModel
w = WhisperModel("small", compute_type="int8")
for modelo in ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]:
    for nombre, cuerpo in PRUEBAS.items():
        cuerpo = {**cuerpo, "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Enceladus"}}}}}
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{G}/{modelo}:generateContent", json.dumps(cuerpo).encode(), H), timeout=180) as r:
                d = json.loads(r.read())
            dato = d["candidates"][0]["content"]["parts"][0]["inlineData"]
            bruto = base64.b64decode(dato["data"])
            f = f"/tmp/{modelo}_{nombre}.wav"
            if bruto[:4] == b"RIFF":
                open(f, "wb").write(bruto)
            else:
                with wave.open(f, "wb") as x:
                    x.setnchannels(1); x.setsampwidth(2); x.setframerate(24000); x.writeframes(bruto)
            segs, _ = w.transcribe(f, language="pt")
            oido = " ".join(s.text.strip() for s in segs)
            print(f"{modelo} · {nombre}: OÍDO = {oido}", flush=True)
        except urllib.error.HTTPError as e:
            print(f"{modelo} · {nombre}: ERROR {e.code} {e.read().decode(errors='replace')[:200]}", flush=True)
        except Exception as e:
            print(f"{modelo} · {nombre}: ERROR {type(e).__name__} {e}", flush=True)
        time.sleep(8)
