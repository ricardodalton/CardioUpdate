import json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
studies=json.loads((ROOT/"data/studies.json").read_text(encoding="utf-8"))
candidates=json.loads((ROOT/"data/candidates.json").read_text(encoding="utf-8"))
remainder=json.loads((ROOT/"data/weekly_remainder.json").read_text(encoding="utf-8"))
meta=json.loads((ROOT/"data/meta.json").read_text(encoding="utf-8"))
areas=json.loads((ROOT/"data/areas.json").read_text(encoding="utf-8"))
valid_areas={a[0] for a in areas}
assert isinstance(studies,list) and studies, "studies.json vacío"
assert isinstance(candidates,list) and candidates, "candidates.json vacío"
assert all(c.get("cardioupdate_detected_at") for c in candidates), "candidatos sin fecha de detección"
assert isinstance(remainder,list), "weekly_remainder.json inválido"
assert len(remainder)==meta.get("candidate_cycle_count"), "conteo del resto semanal inconsistente"
assert meta.get("candidate_cycle_start") and meta.get("candidate_cycle_end"), "meta sin ciclo de candidatos"
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
assert html.count("function cleanAbstractHtml(v){")==1, "helper cleanAbstractHtml duplicado"
assert html.count("function originalAbstractFor(s){")==1, "helper originalAbstractFor duplicado"
assert html.count("function currentCycleBounds(now=new Date()){")==1, "currentCycleBounds duplicado"
assert html.count("function renderBriefingHome(idx=0){")==1, "renderBriefingHome ausente o duplicado"
assert "cardioupdate_detected_at" in html, "Resto de estudios no usa fecha de detección"
assert "data/weekly_remainder.json" in html, "la interfaz no carga la bibliografía semanal liviana"
assert "data/candidates.json" not in html, "la interfaz no debe descargar el pool técnico completo"
print(f"OK: {len(studies)} estudios, {len(candidates)} candidatos y {len(remainder)} referencias del ciclo; esquema válido.")
