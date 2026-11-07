# Texto del canal en inglés: World English Bible (Catholic)

- **Edición exacta**: «World English Bible (Catholic)» — abreviatura WEBC, identificador `eng-web-c` (también `ENGWEBC`),
  «The World English Bible with Catholic Book Order», texto estable de 2020. Incluye los libros deuterocanónicos
  (Tobías, Judit, Sabiduría, Sirácida, Baruc, 1–2 Macabeos y las partes griegas de Ester y Daniel).
- **Ficha de la edición**: https://ebible.org/find/details.php?id=eng-web-c (consultada el 07/11/2026).
- **Archivo que descarga el proceso** (`proceso/evangelio.py`, función `cargar_web`): https://eBible.org/Scriptures/eng-web-c_vpl.zip
  (un versículo por línea). Se guardan solo los cuatro evangelios en `biblia/web/{mateo,marcos,lucas,juan}.json`.
- **Dominio público** (texto literal de la ficha de eBible.org): «The World English Bible is in the Public Domain.
  That means that it is not copyrighted.» Aviso de la misma ficha: «World English Bible» es marca registrada de
  eBible.org; por eso en las descripciones se cita como «World English Bible, Catholic Edition (public domain)»
  y nunca se presenta un texto cambiado como si fuera la WEB oficial (la revisión se declara: «revised by CatolicAid»).
- **Versión revisada**: `biblia/web/revisada/<libro>.json`, igual que `biblia/revisada/` en español: solo las
  introducciones litúrgicas (`_inicios`) y, cuando la lectura empieza en mitad de un discurso, sin la conjunción
  inicial («For», «But»). Las comillas “ ” y ‘ ’ se equilibran solas (`equilibrar_comillas`: la WEB reabre “ en cada
  párrafo de un discurso largo). Versículos que la WEB no trae por variante textual (p. ej. Lucas 17,36) se saltan.
- **Pendiente de revisar**: la WEB añade al final de Mateo 25,13 «in which the Son of Man is coming» (variante que
  el leccionario católico no lee). Se ha dejado tal cual (fiel a la fuente).
