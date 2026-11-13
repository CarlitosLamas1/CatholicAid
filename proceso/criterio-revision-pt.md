# Revisión del vídeo en PORTUGUÉS (canal CatolicAid Português)

Mismo criterio que el inglés (`proceso/criterio-revision-en.md`), con estas diferencias. El revisor escribe
`revisiones/AAAA-MM-DD-pt.json` (ese push lanza «Publicar revisado» con `AAAA-MM-DD-pt`). Sin OK no se publica el
portugués; el español y el inglés no se ven afectados. Revisa siempre DESPUÉS del español y del inglés.

## Qué leer
- Registro: `episodios/AAAA-MM-DD-pt.json` (`idioma: "pt"`, `libro`, `cita_es`).
- Vídeo: release `pt-AAAA-MM-DD`. No hay TikTok ni Instagram en portugués (aún).
- Si el registro tiene `"estado": "fallido"`, NO hay vídeo: no escribas revisión.

## Puntos
1. **fidelidad**: `texto_evangelio` = texto de `biblia/figueiredo/revisada/<libro>.json` (Figueiredo revisado y
   actualizado, criterio en `guias/revision-portugues.md`), versículos de `cita_es`. Solo puede variar la
   introducción (`_inicios`, por defecto «Naquele tempo,») y la primera letra en minúscula tras ella. La unión de
   los fragmentos debe ser idéntica al texto (sin comillas ni espacios).
2. **voces**: palabras de Jesús en `jesus`, narración en `narrador`, etc. Comillas ‘ ’ dentro de un discurso:
   sigue el mismo personaje.
3. **frase_clave**: literal, de Jesús, en portugués, 3–12 palabras, que se entienda sola.
4. **reflexion**: en portugués de Brasil, 1–2 frases (≤ 45 palabras) o una pregunta, tratando de «você», fiel a la
   doctrina, sin comillas, sin política. No es parte del Evangelio.
5. **tecnica**: duración ≤ 180 s, `lufs` entre -15.5 y -12.5 (⚠️ si fuera). Audio: lo normal son 9–19 caracteres por segundo en
   fragmentos largos; ❌ solo si uno de más de 8 s va a menos de 6 c/s o uno de más de 3 s a más de 30 c/s.
6. **imagenes**: las del día del español o de la biblioteca; nunca pidas "repintar".
7. **metadatos**: título «“Frase” | Evangelho do dia 13 de novembro (Lucas 17,26-37)» (≤ 100 caracteres), cita en
   formato brasileño (Lucas 17,26-37; João 20,1-2.11-18), todo en portugués, `subtitulos_karaoke: true`.

## JSON (igual que en inglés, con `"idioma": "pt"`; motivos y avisos en español para Carlos)
