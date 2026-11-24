"""Solo lectura: estado en YouTube (subida, bloqueos por derechos, restricciones) de unos vídeos del canal español."""
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "proceso"))
import evangelio as ev  # noqa: E402

IDS = {"resumen 16-22 nov": "sfstbew1_Wo", "resumen 9-15 nov": "D-h0xUelEBc",
       "short 16": "Bq1h1BkXrM4", "short 17": "-7djYYrQd78", "short 18": "7rQ7Qf3wWHE", "short 19": "kKQvKgj4PoU",
       "short 20": "I5q56XF2Epk", "short 21": "T1xhKthKTMU", "short 22": "ZL0ewkzHC7g",
       "rosario gloriosos": "4MMpgbrHyXQ", "rosario luminosos": "NfolBIYIP5g",
       "rosario dolorosos": "0ksMZv7vrQA", "rosario gozosos": "xHQyQhxatCw"}
tok = ev.token_youtube("es")
d = ev.http(ev.YT + "videos?part=status,contentDetails,snippet,processingDetails&id=" + ",".join(IDS.values()),
            headers={"Authorization": f"Bearer {tok}"})
por_id = {i["id"]: i for i in d.get("items", [])}
for nombre, vid in IDS.items():
    i = por_id.get(vid)
    if not i:
        print(f"{nombre} ({vid}): NO APARECE (borrado o retirado)")
        continue
    st, cd = i["status"], i["contentDetails"]
    print(f"{nombre} ({vid}): {st.get('privacyStatus')} · subida {st.get('uploadStatus')}"
          + (f" · RECHAZO {st.get('rejectionReason')}" if st.get("rejectionReason") else "")
          + (f" · FALLO {st.get('failureReason')}" if st.get("failureReason") else "")
          + (f" · publica {st.get('publishAt')}" if st.get("publishAt") else "")
          + f" · restricciones {json.dumps(cd.get('regionRestriction') or {})}"
          + f" · licencia {cd.get('licensedContent')} · proceso {i.get('processingDetails', {}).get('processingStatus')}")
