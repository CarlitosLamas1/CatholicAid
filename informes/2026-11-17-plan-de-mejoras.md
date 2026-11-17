# Plan de mejoras de CatolicAid · 17/11/2026

Revisión completa del proyecto (código, workflows, datos, costes, audiencia, plataformas, documentación) y propuesta de mejoras ordenadas por temática, con dificultad, riesgo y el modelo con el que las haría.

## 1. Foto de hoy

**Lo que hay**
- 3 canales (es, en, pt) × 3 plataformas (YouTube, TikTok, Instagram; Facebook solo Reels de Instagram). Un vídeo al día por idioma, con dos días de margen.
- 7.180 líneas de Python; **`evangelio.py` tiene 2.655 (el 37 %)**. 33 workflows. 7 archivos de pruebas, 50 pruebas, 546 líneas (casi nada sobre `evangelio.py`).
- Repositorio público (necesario para GitHub Pages gratis), 203 MB, 60 MB de música dentro de git. 47 cachés de Actions, 1,7 GB.
- Cada vídeo tarda unos 20 min en generarse (7–36; un caso de 106).
- Saldo de la clave de pago: **8,39 €** (17/11, 09:51). Bajó 2,13 € en ~42 h, con un bucle de rehacer y mis pruebas de iconos incluidos.

**Lo que funciona bien (no tocar)**
- Producción: «Evangelio diario» 15 ejecuciones, 0 fallos; «Comentarios» 66/0; «Reloj» 78/0 (16 canceladas por la cola, es normal); mantenimiento, parte y copia semanal sin fallos.
- El margen de dos días se recuperó solo hoy: el 18 y el 19 están subidos en los tres idiomas.
- Primer dato de la hora 07:30: el español del 17 llegó a **1.329 visitas en 7 horas**, el mejor arranque de todos (n=1, no es concluyente).

**Lo que se rompió esta semana** (y por qué importa)
| Cuándo | Qué | Causa de fondo | Estado |
|---|---|---|---|
| 15/11 | Publicó dos veces | Guardado con `git pull --rebase` que chocaba | Arreglado (`guardar.py`) |
| 16/11 | «Publicar revisado» fallando cada hora y vídeo rehecho en bucle (~10 veces) | `guardar.py` leía JPG como texto + se relanzaba sin guardar antes las marcas | Arreglado y con freno (`anotar_para_rehacer`) |
| 16–17/11 | El inglés y el portugués del 18 no se hicieron a tiempo | La rama `reloj` llevaba un `reloj.yml` antiguo (una pasada por hora, no cuatro) | Arreglado (script único `reloj_tirada.sh`) |
| 17/11 06:30 | TikTok en inglés falló en la subida y se recuperó a los 3 min | Una petición de subida sin reintentos; el aviso ⚠️ llegó a Carlos | **Pendiente (A1)** |

**Patrón común:** casi todos los fallos son de *estado y coordinación* (guardar, relanzar, quién decide cuándo), no de generación de vídeo. Ahí está el riesgo real.

## 1b. Segunda revisión (con Opus, 17/11/2026)

He repasado la primera versión del plan comprobando sus datos. Esto cambia:

**Correcciones**
- **El gasto de imágenes diario ya está bien medido.** El vídeo diario usa `gemini-2.5-flash-image` (lo fija `imagenes_ia.modelo` en la configuración), y su precio (~0,04 €) es el que está apuntado. El modelo caro (`gemini-3-pro-image-preview`, unos 0,13 $ por imagen según [fuentes de terceros](https://yingtu.ai/blog/nano-banana-pro-api-pricing-per-image), sin confirmar en Google) **solo lo usaron mis pruebas de iconos** (`proceso/icono.py` no fija modelo). Con ~8 imágenes, eso explica cerca de 1 € de los 2,13 €. B2 pasa a ser: «el generador de iconos usa el modelo barato salvo que se pida otro».
- **La estimación del parte falla menos de lo que dije**: parte de la diferencia eran mis pruebas, que el programa no ve. B1 (libro de cuentas) sigue valiendo, pero baja de urgencia.

**Nuevo: lo que se me escapó**

| # | Mejora | Por qué | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| H5 | **Tu correo personal está en el historial público**: 49 commits firmados con él y versiones antiguas de `CLAUDE.md`; además 193 commits con el nombre de tu Mac. No hay ninguna clave filtrada (lo he buscado en todo el historial). Arreglo seguro: que los commits nuevos usen el correo anónimo de GitHub. Reescribir el historial es posible, pero rompe copias y enlaces | Repositorio público | Baja (lo nuevo) · Alta (el historial) | Bajo · Alto | Haiku (lo nuevo) · Opus (historial) · 👤 |
| A8 | **Las voces dependen de modelos «preview»** (`gemini-2.5-flash-preview-tts` en español; `gemini-3.1-flash-tts-preview` en inglés y portugués) y no hay respaldo (`respaldo_edge: false`, decisión tuya). Si Google retira uno, se para la producción de ese idioma. Propuesta: inventario de modelos preview, aviso cuando Google anuncie la retirada y un sustituto probado con las mismas voces | Producción entera depende de ellos | Media | Medio | Opus |
| C7 | **Pruebas del revisor** (la rutina en la nube y su guía de 15 KB): un juego de episodios de ejemplo con el veredicto esperado, para que cambiar la guía no rompa el criterio sin darnos cuenta | El revisor decide qué se publica y nadie comprueba que su criterio no cambie | Media | Bajo | Opus |

**Lo que se mantiene igual** (lo he comprobado): el fallo de subida de TikTok de esta mañana (A1), la falta de pruebas en `reloj.py` y `publicar.py`, las dependencias sin versión fija, el aviso de Node 20 y el peso del repositorio.

**Orden ajustado:** H5 (lo nuevo) entra en la Ola 0; A8 en la Ola 1 (antes que B1); C7 en la Ola 2.

## 2. Cómo leer el plan

- **Dificultad:** Baja (horas, sin riesgo) · Media (un día, con pruebas) · Alta (varios días o toca el centro de la producción).
- **Modelo:** el que usaría para que salga bien, no el más barato.
  - **Opus 5.5:** lógica de estado, orquestación, dinero, publicación, diseño de criterios de revisión, refactors grandes y cualquier cosa que no se pueda probar del todo antes de ponerla en producción.
  - **Sonnet 5.5:** implementación con criterios claros y pruebas posibles (web, scripts, workflows, estadísticas, documentación técnica).
  - **Haiku 5.5:** tareas mecánicas sin decisiones (borrar ramas, subir versiones, renombrar, comprobar listas).
- **Necesita a Carlos:** marcado con 👤 cuando hace falta una decisión, un permiso o una acción en una cuenta tuya.

---

## A. Fiabilidad y operación

| # | Mejora | Por qué (evidencia) | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| A1 | **Reintentos con espera en las subidas a TikTok e Instagram** (inicio, trozos y estado) y que el aviso ⚠️ solo salte si fallan los reintentos | 17/11 06:30: una petición de subida falló, se avisó y a los 3 min iba bien | Baja | Bajo | Sonnet |
| A2 | **Freno general de bucles**: máximo N rehacer por vídeo y día contado desde GitHub (no solo desde el registro), y parar si el gasto del día supera un tope | El bucle del 16/11 se salvó por un arreglo concreto; falta una red que no dependa de que el guardado funcione | Media | Medio (toca el flujo de rehacer) | Opus |
| A3 | **Aviso tras 3 fallos seguidos del mismo workflow** (un solo mensaje, como el ⚠️ actual) | «Publicar revisado» falló 6 veces seguidas y te enteraste por correos de GitHub | Baja | Bajo | Sonnet · 👤 hace falta tu OK: es un aviso nuevo y prometimos no añadir |
| A4 | **Ventana de grabación para el vídeo de mañana**: hoy no se graba entre las 22:00 y las 08:00 UTC; con publicación a las 06:30 UTC, un vídeo que falte a las 22:00 ya llega tarde | Se cambió la hora y la ventana no se revisó. Hay 14 h de reintentos antes, así que el riesgo es bajo, pero existe | Alta | Alto (toca `ultimo_intento`, el corte de las 08:00 del inglés/portugués y la clave de pago) | Opus |
| A5 | **Segundo latido independiente del Reloj** (hoy depende de una sola rutina en la nube; los cron de GitHub se retrasan horas) | Si la rutina falla, el Reloj solo corre cuando GitHub quiere | Media | Medio | Opus · 👤 requiere un servicio externo gratis con una clave tuya |
| A6 | **Reloj: extraer las decisiones a funciones puras y probarlas** (qué lanzar según hora, registros y ejecuciones) | `reloj.py` (311 líneas) decide todo y no tiene ni una prueba; el fallo de las 21:32 se vio a posteriori | Media | Bajo | Sonnet |
| A7 | **Registro de eventos por vídeo** (lista con hora y causa: generado, revisado, rehecho, subido…) en lugar de varias marcas sueltas | Hoy hay `rehechos`, `repintados`, `frases_descartadas`, `rehecho_por_es`… y para entender el 16/11 hubo que leer varios commits | Media | Medio | Opus |

## B. Costes

| # | Mejora | Por qué | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| B1 | **Libro de cuentas de gasto**: anotar el coste en el momento de cada petición de pago, en un archivo propio | La estimación desde los registros dio 0,37 € frente a 2,13 € reales: los rehechos sobrescriben lo anterior | Media | Bajo | Opus (toca el centro de voces e imágenes) |
| B2 | **El generador de iconos usa el modelo barato** salvo que se pida el Pro (ver 1b: el diario ya usa el barato y el precio apuntado es correcto) | Mis pruebas de iconos usaron el Pro sin quererlo | Baja | Bajo | Sonnet |
| B3 | **Tope diario y mensual** con cambio a «solo gratis» al llegar (y aviso en el parte) | Hoy solo avisa por debajo de 3 € | Media | Medio | Opus |
| B4 | **Medir un día limpio** (saldo de mañana a las 10:00) y fijar el gasto normal | Los 2,13 € no son representativos | Baja | Ninguno | 👤 solo tu cifra · Haiku para apuntarla |

## C. Calidad del vídeo y del contenido

| # | Mejora | Por qué | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| C1 | **El revisor ve fotogramas**: una hoja de contacto con ~8 fotogramas por vídeo en el repositorio mientras se revisa | Hoy juzga imágenes por la descripción: el 16/11 pidió repintar por un aviso, no porque lo viera | Media | Bajo | Opus (criterios y prompt) |
| C2 | **Comprobaciones automáticas con ffprobe**: silencios, picos, fotogramas negros, zona segura de subtítulos | El revisor «no puede oír»; hoy se estima por caracteres por segundo | Media | Bajo | Sonnet |
| C3 | **Prueba de velocidad de la voz** (1,15 hoy frente a 1,0) | El 47 % del público español tiene más de 65 años; es una hipótesis barata de probar | Baja | Bajo | Sonnet |
| C4 | **Límite de longitud de la frase clave** (≈14 palabras) | El 18 acabó con una de ~25 palabras tras descartar una de 18 | Baja | Bajo | Sonnet |
| C5 | **Subtítulos y gancho adaptados al público mayor** (tamaño, contraste, ritmo) y a la tele (8 % en inglés) | Mismos datos de edad | Media | Bajo | Sonnet |
| C6 | **Texto en español latinoamericano** («ustedes» en lugar de «vosotros») | México+EE. UU. = 57 % de las visitas; España, 1,7 % | Alta | Alto (es el texto del Evangelio) | Opus · 👤 decisión tuya, y revisión humana |

## D. Crecimiento y audiencia

| # | Mejora | Por qué | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| D1 | **Permiso de YouTube Analytics** (retención, fuentes de tráfico, países) | Hoy solo vemos visitas y «me gusta»; sin retención no sabemos qué corregir | Baja | Bajo | Sonnet · 👤 reconectar YouTube una vez |
| D2 | **Cuadro semanal ampliado**: suscriptores, visitas por hora de publicación, primer día, mejor y peor, y enlace con frase/duración/gancho | Entre vídeos de la misma hora hay de 92 a 1.833 visitas: manda el contenido y hay que medirlo | Media | Bajo | Sonnet |
| D3 | **Estudio de qué hace funcionar un vídeo** (frase, duración, gancho, imágenes) con los datos que ya tenemos | 13/11 (1.833) frente a 12/11 (92) | Media | Bajo | Opus |
| D4 | **Hora propia por idioma** una vez haya 2 semanas de datos (el portugués sale a las 03:30 de Brasil) | PT sube 26–78 visitas por vídeo; la hora puede pesar más allí | Baja | Bajo | Sonnet |
| D5 | **Páginas diarias en la web** (texto, vídeo, reflexión, botón de WhatsApp) | «Evangelio de hoy» es una búsqueda muy frecuente; además ayuda a la revisión de TikTok | Media | Bajo | Sonnet |
| D6 | **Canal público de Telegram y botón de compartir por WhatsApp** | Público mayor y latinoamericano: WhatsApp es el canal natural | Baja | Bajo | Sonnet · 👤 decisión tuya (prometimos no ampliar el bot) |
| D7 | **Instagram Insights** (permiso nuevo) | Hoy no medimos Instagram | Media | Bajo | Sonnet · 👤 volver a autorizar en Meta |

## E. Plataformas

| # | Mejora | Por qué | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| E1 | **TikTok: seguir con la revisión de la app y decidir sobre la auditoría** cuando responda | Revisión reenviada el 16/11. Aprobar la app no basta para publicar en público | Baja | Bajo | Opus (lectura de normas) · 👤 |
| E2 | **TikTok Studio desde tu Chrome**, solo con tu permiso y supervisión | Es la única vía que quita el trabajo manual sin gastar; zona gris de las condiciones | Media | Medio (cuentas) | Opus · 👤 |
| E3 | **TikTok es tan grande como YouTube** (~650 espectadores/día en español; el inglés, ~3 veces su YouTube): medirlo cada semana | Datos del 9–14/11; el trabajo diario compensa | Baja | Bajo | Sonnet · 👤 exportar el CSV |
| E4 | **Instagram: portada y primer comentario** con hashtags | La API no deja borrar Reels; se hace bien desde el principio | Baja | Bajo | Sonnet |

## F. Código y pruebas

| # | Mejora | Por qué | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| F1 | **Partir `evangelio.py`** en módulos (texto, guion, voces, imágenes, vídeo, subida) con pruebas de caracterización antes de moverlo | 2.655 líneas y pocas pruebas: cada cambio asusta | Alta | Alto | Opus (con revisión por un segundo pase) |
| F2 | **Modo simulacro**: ejecutar todo el montaje con voces e imágenes de ejemplo, sin llamar a las APIs, en CI | Hoy los fallos del montaje se ven en producción | Alta | Medio | Opus |
| F3 | **Pruebas de `publicar.py`, `tiktok.py` e `instagram.py`** con respuestas simuladas | Cero pruebas en el camino que publica | Media | Bajo | Sonnet |
| F4 | **Fijar versiones** (`requirements.txt`, Python) | `pip install faster-whisper` sin versión sobre Python 3.14 del runner: se puede romper un día sin avisar | Baja | Bajo | Sonnet |
| F5 | **Validación de la configuración** (47 claves, 24 KB) con un esquema en CI | Una errata en una clave no da error, da otro comportamiento | Media | Bajo | Sonnet |
| F6 | **Acción compuesta común** para ffmpeg, caché, pip y fuentes | Se repite en 6+ workflows | Media | Medio | Sonnet |
| F7 | **Subir las acciones** (`checkout@v4` avisa de Node 20 obsoleto) y borrar ramas viejas (`claude/*`, `mejoras-ingles`) | Avisos hoy; ramas sin uso | Baja | Bajo | Haiku |
| F8 | **Ordenar los workflows de un solo uso** (casting, pruebas, iconos, reprogramar, borrador de TikTok) | 33 workflows; los de prueba se mezclan con los de producción | Baja | Bajo | Haiku |

## G. Documentación y conocimiento

| # | Mejora | Por qué | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| G1 | **Partir `CLAUDE.md`** (173 líneas, 44 KB) en un resumen corto + guías: arquitectura, qué hacer si…, historial | Se carga entero en cada sesión y mezcla estado actual con historia; varias frases ya son viejas (horas, Reloj, iconos) | Media | Medio (no perder datos) | Opus |
| G2 | **Guía «qué hacer si…»** (se atasca un vídeo, caduca un permiso, falla TikTok, se acaba el saldo) | Hoy el conocimiento está en la historia de los commits | Media | Bajo | Sonnet |
| G3 | **Revisión mensual automática** (modelos de Gemini retirados, versiones, cuotas, caducidad de tokens) que deje un informe | Hoy se descubre cuando algo falla | Media | Bajo | Sonnet |

## H. Seguridad y datos

| # | Mejora | Por qué | Dif. | Riesgo | Modelo |
|---|---|---|---|---|---|
| H1 | **Probar una restauración desde la copia semanal** | Existe la copia (1,5 MB por Telegram), pero nunca se ha restaurado | Baja | Bajo | Sonnet |
| H2 | **Revisión de permisos de los workflows** (`contents: write` en muchos) y de los secretos | Repositorio público: lo que se escribe se ve | Media | Medio | Opus |
| H3 | **Sacar la música de git** a una release | 60 MB en git; pesa en cada clon | Media | Medio | Sonnet |
| H4 | **Rotación de claves** (Gemini, Meta, YouTube, TikTok) con calendario | Los `.enc` viven en un repositorio público; si una clave se filtra, el historial queda legible | Media | Medio | Opus · 👤 |

---

## 3. Orden propuesto

**Ola 0 · esta semana (barato y evita sustos)**
A1, A3 (con tu OK), B2, B4, F4, F7, C4, H5 (solo lo nuevo), D1 (tu reconexión).

**Ola 1 · las dos siguientes semanas (refuerzan lo que se rompió)**
A2, A6, A8, B1, B3, F3, G1, D2.

**Ola 2 · calidad y crecimiento**
C1, C2, C3, C7, D3, D4, D5, E3, E4.

**Ola 3 · estructura (solo si el resto va estable)**
A4, A7, F1, F2, F5, F6, H2, H3, H4.

**Decisiones tuyas, sin prisa:** C6 («ustedes»), D6 (Telegram/WhatsApp), E2 (TikTok Studio), A5 (latido externo), A3 (aviso nuevo).

## 4. Qué no haría

- **No tocaría la producción de vídeo** (voces, montaje, música) mientras no haya pruebas que la cubran: funciona y es lo más caro de romper.
- **No ampliaría la ventana de grabación (A4) ahora**: el riesgo es bajo y el cambio toca demasiadas piezas sin poder probarlo de verdad.
- **No pasaría el repositorio a privado**: perderíamos la web gratuita que TikTok y Google usan en sus revisiones.
