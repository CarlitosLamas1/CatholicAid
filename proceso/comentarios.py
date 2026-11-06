#!/usr/bin/env python3
"""CatholicAid · Respuestas a comentarios de YouTube, con ritmo humano.

Lo ejecuta el «Reloj» cada hora. En cada pasada:
1. Lee los comentarios recientes del canal (últimos 3 días). Los nuevos quedan en comentarios/pendientes.json y
   CLAUDE (la rutina horaria del revisor) decide y redacta en comentarios/decisiones.json; si en 3 h no lo ha
   hecho, decide Gemini lite (reserva). Tipos:
   responder (positivo o pregunta sencilla) · delicado (duelo, enfermedad, crisis, petición de oración concreta,
   duda de fe seria, crítica) · ignorar (spam, insultos, solo emojis, sin contenido).
2. Los delicados se mandan a Carlos por Telegram para que responda él. Nunca se contestan solos.
3. Como mucho UNA respuesta por pasada, y solo si ya toca: entre respuesta y respuesta pasa un rato al azar
   (min_minutos_entre–max_minutos_entre), cada comentario espera al menos unas horas, hay un máximo diario
   y solo en horas de vela (Madrid). Además espera unos minutos al azar para no responder siempre a la misma hora.
Las respuestas hablan como «el canal»: cálidas y concretas, sin fingir ser una persona ni inventar vivencias.
Si falta el permiso de YouTube para comentar, funciona en modo simulación (escribe lo que respondería).
Estado en estado/comentarios.json.  Uso: python3 proceso/comentarios.py [--simular]
"""
import datetime as dt
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avisos  # noqa: E402
import evangelio as ev  # noqa: E402

RAIZ = ev.RAIZ
CANAL = "UCeQ2e1rojxsa9UyrHWcVEVA"
ESTADO = RAIZ / "estado" / "comentarios.json"
YT = "https://www.googleapis.com/youtube/v3/"
PROHIBIDO = re.compile(r"rez(o|ar[eé]|aremos|amos)\b|orar[eé]|oramos por|yo tambi[eé]n|me pas[oó]|en (la )?misa|"
                       r"como sacerdote|\bsoy (un|una|el|la)\b|mi (familia|mujer|marido|hijo|madre|padre)|https?://|www\.",
                       re.I)


def log(*a):
    print(*a, flush=True)


def cfg():
    return {"activo": True, "max_dia": 6, "min_minutos_entre": 75, "max_minutos_entre": 200,
            "espera_min_minutos": 60, "espera_max_minutos": 300, "desde_hora": 9, "hasta_hora": 2,
            "modelos": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"],
            **ev.CFG.get("comentarios", {})}


def ahora():
    return dt.datetime.now(ev.MADRID)


def leer_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {"vistos": {}, "respondidos": [], "recientes": []}


def guardar_estado(est):
    # Solo se guarda lo de los últimos 10 días para que no crezca sin fin.
    limite = (ahora() - dt.timedelta(days=10)).isoformat()
    est["vistos"] = {k: v for k, v in est["vistos"].items() if v.get("publicado", "") >= limite}
    est["respondidos"] = est["respondidos"][-300:]
    est["recientes"] = est["recientes"][-30:]
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(est, ensure_ascii=False, indent=2), encoding="utf-8")


def gemini_json(prompt, esquema, modelos, temperatura):
    for m in modelos:
        try:
            r = ev.gemini(m, {"contents": [{"parts": [{"text": prompt}]}],
                              "generationConfig": {"responseMimeType": "application/json", "responseSchema": esquema,
                                                   "temperature": temperatura}}, intentos=2)
            partes = r["candidates"][0]["content"]["parts"]
            return json.loads(next(p["text"] for p in reversed(partes) if "text" in p))
        except Exception as e:
            log(f"   {m}: falló ({e})")
    return None


def leer_comentarios(tok):
    h = {"Authorization": f"Bearer {tok}"}
    d = ev.http(YT + "commentThreads?" + urllib.parse.urlencode({
        "part": "snippet,replies", "allThreadsRelatedToChannelId": CANAL, "maxResults": 50, "order": "time",
        "textFormat": "plainText"}), headers=h)
    limite = ahora() - dt.timedelta(days=3)
    salida = []
    for t in d.get("items", []):
        c = t["snippet"]["topLevelComment"]["snippet"]
        publicado = dt.datetime.fromisoformat(c["publishedAt"].replace("Z", "+00:00"))
        autor = c.get("authorChannelId", {}).get("value")
        ya = any(r["snippet"].get("authorChannelId", {}).get("value") == CANAL for r in t.get("replies", {}).get("comments", []))
        if publicado < limite or autor == CANAL or ya:
            continue
        salida.append({"id": t["id"], "video": c.get("videoId", ""), "autor": c.get("authorDisplayName", ""),
                       "texto": c.get("textOriginal") or c.get("textDisplay", ""), "publicado": publicado.isoformat()})
    return salida


def contexto_video(video):
    for ruta in sorted((RAIZ / "episodios").glob("*.json"), reverse=True)[:30]:
        try:
            r = json.loads(ruta.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("youtube", {}).get("id") == video:
            return f"Evangelio del {r['fecha']} ({r['cita']}). Frase clave: {r.get('frase_clave', '')}. Reflexión: {r.get('reflexion', '')}"
    return "Evangelio del día leído con varias voces."


def clasificar(nuevos, c):
    lista = "\n".join(f'- id {x["id"]}: «{x["texto"][:400]}»' for x in nuevos)
    prompt = f"""Eres el responsable de la comunidad de un canal católico de YouTube que publica cada día el Evangelio.
Clasifica cada comentario:
- "responder": positivo, agradecido, de fe, o una pregunta sencilla que se puede contestar con cariño y en general.
- "delicado": duelo, enfermedad, crisis personal, alguien que sufre o pide oración por algo concreto, dudas de fe
  serias, temas morales complejos, críticas o quejas. Esos los contesta una persona del canal.
- "ignorar": spam, enlaces, insultos, publicidad, solo emojis, una sola palabra sin más («Amén», «🙏»), o nada que aportar.
COMENTARIOS:
{lista}"""
    esquema = {"type": "OBJECT", "properties": {"comentarios": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "id": {"type": "STRING"}, "tipo": {"type": "STRING", "enum": ["responder", "delicado", "ignorar"]},
        "motivo": {"type": "STRING"}}, "required": ["id", "tipo"]}}}, "required": ["comentarios"]}
    r = gemini_json(prompt, esquema, c["modelos"], 0)
    return {x["id"]: x for x in (r or {}).get("comentarios", [])}


def redactar(com, est, c):
    prompt = f"""Responde, en nombre del canal católico de YouTube «CatolicAid», a este comentario de {com['autor']} en el vídeo:
{contexto_video(com['video'])}

COMENTARIO: «{com['texto'][:600]}»

Reglas:
- Una o dos frases cortas (máximo 200 caracteres), cálidas y naturales, en español; si el comentario es de
  Hispanoamérica, sin «vosotros». Recoge algo concreto de lo que dice; nada de frases de plantilla.
- Hablas como el canal, nunca como una persona concreta: no digas que rezas, que oras, que vas a misa, que eres
  sacerdote, que te pasó algo o que tienes familia. Puedes desear bendiciones o invitar a seguir el Evangelio cada día.
- Fiel a la doctrina católica; si es una pregunta, respuesta sencilla y prudente.
- Sin enlaces, sin hashtags, como mucho un emoji (o ninguno). No empieces con «¡Hola!» ni con el nombre siempre.
- No repitas ninguna de estas respuestas recientes del canal: {json.dumps(est['recientes'][-10:], ensure_ascii=False)}"""
    esquema = {"type": "OBJECT", "properties": {"respuesta": {"type": "STRING"}}, "required": ["respuesta"]}
    for _ in range(2):
        r = gemini_json(prompt, esquema, c["modelos"], 0.9)
        texto = ev.espacios((r or {}).get("respuesta", "")).strip(' "«»')
        if 10 <= len(texto) <= 220 and not PROHIBIDO.search(texto) and texto not in est["recientes"]:
            return texto
        log(f"   Respuesta descartada: {texto[:120]}")
    return None


PENDIENTES = RAIZ / "comentarios" / "pendientes.json"  # lo escribe este script (GitHub)
DECISIONES = RAIZ / "comentarios" / "decisiones.json"  # lo escribe Claude (rutina horaria)


def leer_json(ruta, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return defecto


def avisar_delicado(x, motivo):
    enlace = f"https://www.youtube.com/watch?v={x['video']}&lc={x['id']}"
    avisos.enviar(f"💬 <b>Comentario para que respondas tú</b> ({avisos.e(motivo)}):\n"
                  f"«{avisos.e(x['texto'][:500])}» — {avisos.e(x['autor'])}\n🔗 {avisos.e(enlace)}")


def ver_respuestas():
    """Comprueba en YouTube las respuestas del canal a los comentarios respondidos (visibles o retenidas)."""
    est = leer_estado()
    h = {"Authorization": f"Bearer {ev.token_youtube()}"}
    for cid in est["respondidos"][-10:]:
        d = ev.http(YT + "comments?" + urllib.parse.urlencode({"part": "snippet", "parentId": cid, "maxResults": 50}), headers=h)
        mias = [x["snippet"] for x in d.get("items", []) if x["snippet"].get("authorChannelId", {}).get("value") == CANAL]
        hilo = ev.http(YT + "commentThreads?" + urllib.parse.urlencode({"part": "snippet", "id": cid}), headers=h)
        video = (hilo.get("items") or [{}])[0].get("snippet", {}).get("videoId", "?")
        for m in mias:
            log(f"{cid} · vídeo {video} · {m.get('moderationStatus', 'publicado')} · {m.get('publishedAt')} · «{m.get('textOriginal')}»")
        if not mias:
            log(f"{cid} · vídeo {video} · ¡no aparece la respuesta del canal!")


def main():
    if "--ver" in sys.argv:
        return ver_respuestas()
    simular = "--simular" in sys.argv
    c = cfg()
    if not c["activo"]:
        log("Respuestas a comentarios desactivadas.")
        return
    est = leer_estado()
    momento = ahora()
    tok = ev.token_youtube()
    try:
        comentarios = leer_comentarios(tok)
    except urllib.error.HTTPError as e:
        log(f"No puedo leer comentarios: {e.code} {e.read().decode(errors='replace')[:200]}")
        return
    vivos = {x["id"]: x for x in comentarios}

    # 1. Comentarios nuevos: quedan pendientes de que Claude decida (rutina horaria).
    for x in comentarios:
        if x["id"] not in est["vistos"]:
            espera = random.randint(c["espera_min_minutos"], c["espera_max_minutos"])
            est["vistos"][x["id"]] = {"tipo": "pendiente", "publicado": x["publicado"], "desde": momento.isoformat(),
                                     "listo": (dt.datetime.fromisoformat(x["publicado"]) + dt.timedelta(minutes=espera)).isoformat()}
            log(f"   [nuevo] {x['autor']}: {x['texto'][:80]}")

    # 2. Decisiones de Claude; si Claude no ha decidido en 3 h, decide Gemini (reserva).
    decisiones = leer_json(DECISIONES, {})
    sin_decidir = []
    for cid, v in est["vistos"].items():
        if v["tipo"] != "pendiente":
            continue
        d = decisiones.get(cid)
        if d and d.get("tipo") in ("responder", "delicado", "ignorar"):
            v.update({"tipo": d["tipo"], "motivo": d.get("motivo", ""), "respuesta": d.get("respuesta", ""), "por": "claude"})
        elif cid in vivos and v["desde"] <= (momento - dt.timedelta(hours=3)).isoformat():
            sin_decidir.append(vivos[cid])
    if sin_decidir:
        log(f"Claude no ha decidido {len(sin_decidir)} comentario(s) en 3 h: decide Gemini")
        for cid, t in clasificar(sin_decidir, c).items():
            if cid in est["vistos"]:
                est["vistos"][cid].update({"tipo": t["tipo"], "motivo": t.get("motivo", ""), "por": "gemini"})
    for cid, v in est["vistos"].items():
        if v["tipo"] != "pendiente":
            log(f"   [{v['tipo']} · {v.get('por', '-')}] {vivos.get(cid, {}).get('texto', cid)[:70]}")
        if v["tipo"] == "delicado" and not v.get("avisado") and cid in vivos and not simular:
            avisar_delicado(vivos[cid], v.get("motivo", ""))
            v["avisado"] = True

    # Lo que sigue pendiente, con todo lo que Claude necesita para decidir.
    pendientes = [{**vivos[cid], "contexto": contexto_video(vivos[cid]["video"])}
                  for cid, v in est["vistos"].items() if v["tipo"] == "pendiente" and cid in vivos]
    if not simular:
        PENDIENTES.parent.mkdir(exist_ok=True)
        PENDIENTES.write_text(json.dumps({"actualizado": momento.isoformat(), "comentarios": pendientes,
                                          "recientes": est["recientes"][-10:]}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    log(f"Comentarios recientes: {len(comentarios)} · pendientes de Claude: {len(pendientes)}")

    # 3. ¿Toca responder ahora? Como mucho una respuesta por pasada.
    hoy = str(momento.date())
    if est.get("dia") != hoy:
        est["dia"], est["hoy"] = hoy, 0
    h = momento.hour
    despierto = h >= c["desde_hora"] or h < c["hasta_hora"]
    proxima = est.get("proxima")
    if not despierto or est["hoy"] >= c["max_dia"] or (proxima and momento.isoformat() < proxima):
        log(f"No toca responder ahora (hora {h}, hoy {est['hoy']}/{c['max_dia']}, próxima {proxima or '-'}).")
        guardar_estado(est)
        return
    candidatos = sorted((x for x in comentarios if est["vistos"].get(x["id"], {}).get("tipo") == "responder"
                         and est["vistos"][x["id"]]["listo"] <= momento.isoformat()
                         and x["id"] not in est["respondidos"]), key=lambda x: x["publicado"])
    if not candidatos:
        log("Nada que responder ahora.")
        guardar_estado(est)
        return
    com = candidatos[0]
    texto = ev.espacios(est["vistos"][com["id"]].get("respuesta", "")).strip(' "«»')
    if not (10 <= len(texto) <= 240) or PROHIBIDO.search(texto) or texto in est["recientes"]:
        texto = redactar(com, est, c)  # sin borrador válido de Claude: lo redacta Gemini
    if not texto:
        guardar_estado(est)
        return
    if simular:
        log(f"(simulación) Respondería a {com['autor']} «{com['texto'][:80]}» -> «{texto}»")
        guardar_estado(est)
        return
    time.sleep(random.randint(0, 20 * 60))  # que no sea siempre a la misma hora
    try:
        ev.http(YT + "comments?part=snippet", {"snippet": {"parentId": com["id"], "textOriginal": texto}},
                {"Authorization": f"Bearer {ev.token_youtube()}"}, method="POST")
    except urllib.error.HTTPError as e:
        log(f"YouTube no dejó responder: {e.code} {e.read().decode(errors='replace')[:300]}")
        est["proxima"] = (ahora() + dt.timedelta(minutes=c["min_minutos_entre"])).isoformat()
        guardar_estado(est)
        return
    est["respondidos"].append(com["id"])
    est["recientes"].append(texto)
    est["hoy"] += 1
    est["ultima"] = ahora().isoformat()
    est["proxima"] = (ahora() + dt.timedelta(minutes=random.randint(c["min_minutos_entre"], c["max_minutos_entre"]))).isoformat()
    log(f"Respondido a {com['autor']}: «{texto}»")
    guardar_estado(est)


if __name__ == "__main__":
    main()
