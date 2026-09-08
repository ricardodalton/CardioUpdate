import json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
studies=json.loads((ROOT/"data/studies.json").read_text(encoding="utf-8"))
areas=json.loads((ROOT/"data/areas.json").read_text(encoding="utf-8"))
valid_areas={a[0] for a in areas}
assert isinstance(studies,list) and studies, "studies.json vacío"
ids=set()
for s in studies:
    for key in ["id","title","area","level","journal","date","summary","url"]:
        assert key in s, f"{s.get('id')}: falta {key}"
    assert s["id"] not in ids, f"ID duplicado {s['id']}"
    ids.add(s["id"])
    assert s["area"] in valid_areas, f"Área inválida {s['area']}"
    assert s["level"] in {"Practice Changer","Relevante","Seguimiento"}, f"Nivel inválido {s['level']}"
    assert s["url"].startswith("http"), f"URL inválida {s['url']}"
    if s.get("abstract_es"):
        assert isinstance(s["abstract_es"],list), "abstract_es debe ser lista"
        for sec in s["abstract_es"]:
            assert isinstance(sec,list) and len(sec)==2 and all(isinstance(x,str) for x in sec)
html=(ROOT/"index.html").read_text(encoding="utf-8")
assert "data/studies.json" in html
assert ">DOI<" not in html
assert "<h2>Dato principal</h2>" not in html
assert "<h2>Datos clave</h2>" not in html
assert "loadDatabase()" in html
print(f"OK: {len(studies)} estudios, esquema válido, interfaz conectada a base externa.")
