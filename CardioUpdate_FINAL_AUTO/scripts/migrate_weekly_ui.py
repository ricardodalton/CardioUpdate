#!/usr/bin/env python3
"""Idempotent UI migration for CardioUpdate weekly-journal behavior."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

s = s.replace("CardioUpdate-3.5-guides-permanent-outside-weekly20", "CardioUpdate-4.0-frozen-weekly-edition")
s = s.replace(".meterRow{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;font-size:12px}",
              ".meterRow{display:grid;grid-template-columns:1fr;gap:12px;align-items:center;font-size:12px}")

anchor = "let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={};\n"
weekly_helpers = r'''let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={};
function editionBounds(now=new Date()){
  const d=new Date(now); d.setHours(0,0,0,0);
  const daysSinceFriday=(d.getDay()+2)%7;
  const friday=new Date(d); friday.setDate(d.getDate()-daysSinceFriday);
  const start=new Date(friday); start.setDate(friday.getDate()-6);
  const end=new Date(friday); end.setDate(friday.getDate()+1);
  return {start,end};
}
function selectPublishedEdition(items){
  const {start,end}=editionBounds();
  const selected=(items||[]).filter(s=>{
    const d=new Date((s.date||'')+'T00:00:00');
    const text=((s.type||'')+' '+(s.title||'')+' '+(s.short||'')).toLowerCase();
    const isGuide=/guideline|guidelines|consensus|scientific statement|position statement|guía|guías|consenso/.test(text);
    return !isGuide && !isNaN(d) && d>=start && d<end;
  }).sort((a,b)=>(b.auto_score||0)-(a.auto_score||0)||String(b.date||'').localeCompare(String(a.date||'')));
  return selected.slice(0,30);
}
'''
if "function editionBounds(" not in s:
    s = s.replace(anchor, weekly_helpers)

s = s.replace("STUDIES=s; GUIDES=g; AREAS=a; META=meta;", "STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta;")

s = s.replace('<div class="number">${STUDIES.length}</div><div class="caption">trabajos seleccionados</div>', '')
s = s.replace("<b>${STUDIES.filter(x=>x.level==='Practice Changer').length}</b>", "")
s = s.replace("<b>${STUDIES.filter(x=>x.level==='Relevante').length}</b>", "")
s = s.replace("<b>${STUDIES.filter(x=>x.level==='Seguimiento').length}</b>", "")
s = s.replace("<b>${GUIDES.length}</b>", "")

s = re.sub(r"function weeklyStudies\(\)\{.*?\n\}\nfunction filtered\(\)\{",
           "function weeklyStudies(){ return STUDIES; }\nfunction filtered(){",
           s, count=1, flags=re.S)

s = s.replace("El artículo y su abstract fueron incorporados por la búsqueda diaria.",
              "El artículo y su abstract fueron incorporados por la selección semanal.")

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate UI migrada a edición semanal congelada.")
else:
    print("CardioUpdate UI ya estaba migrada.")
