---
name: estado
description: Parte rápido de cómo va CatholicAid ahora mismo (vídeos de hoy, mañana y pasado en español, inglés y portugués; revisor; YouTube, TikTok e Instagram; fallos recientes). Úsalo cuando Carlos pregunte «¿cómo va?», «¿está todo bien?», «¿se publicó?» o escriba /estado.
---
Prepara un parte corto para Carlos, en español sencillo y sin tecnicismos. Solo lee: no lances workflows ni cambies nada.

1. Trae lo último: `git pull --ff-only -q`.
2. Parte del día (el mismo que llega por Telegram a las 21:00, pero sin enviarlo):
   ```bash
   python3 -c "import sys; sys.path.insert(0,'proceso'); import parte, datetime as dt; print(parte.componer(dt.datetime.now(parte.MADRID)))" 2>/dev/null
   ```
   Las visitas de YouTube no salen en local (faltan los secretos): es normal, no lo menciones.
3. Fallos recientes en GitHub (últimas 12 h):
   ```bash
   gh run list -L 40 --json name,conclusion,createdAt,url --jq '.[] | select(.conclusion=="failure")'
   ```
   Para cada fallo, mira si ya se arregló solo: si después hay un run del mismo workflow con `success`, no es un problema. Si sigue fallando, mira el motivo con `gh run view <id> --log-failed | tail -30`.
4. Responde así, en pocas líneas:
   - Semáforo (🟢 todo bien / 🟡 algo se arregla solo / 🟠 te necesito).
   - Lo que le toca a Carlos, si hay algo (de una en una, con el enlace).
   - Hoy, mañana y pasado mañana, una línea por idioma (🇪🇸 🇬🇧 🇧🇷).
   - Fallos que sigan sin arreglarse y qué vas a hacer (si hace falta arreglar código, propón usar el ayudante «productor»).
   Convierte el HTML del parte (<b>, <a>…) a texto normal con enlaces.
