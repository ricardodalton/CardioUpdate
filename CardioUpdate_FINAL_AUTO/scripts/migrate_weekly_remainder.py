#!/usr/bin/env python3
"""Add/fix bibliography-style list of non-selected weekly studies."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

s = s.replace("CardioUpdate-4.1-title-abstract-analysis", "CardioUpdate-4.2-weekly-remainder")

needle = ".empty{background:#fff;border:1px dashed #bdb5ac;padding:34px;text-align:center;color:#737b82}\n"
style = needle + ".remainderList{background:#fff;border-top:3px solid #17212b;padding:8px 26px 20px}.remainderList ol{margin:0;padding-left:28px}.remainderList li{padding:10px 4px;border-bottom:1px solid var(--line);font-family:Georgia,serif;font-size:16px;line-height:1.35}.remainderList li:last-child{border-bottom:0}.remainderList a{text-decoration:none}.remainderList a:hover{text-decoration:underline;color:#d51f32}\n"
if ".remainderList{" not in s:
    s = s.replace(needle, style)

if "CANDIDATES=[]" not in s:
    s = s.replace("let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={};", "let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={}, CANDIDATES=[];")

# Repair loadDatabase regardless of which prior migration version is present.
s = s.replace("const [s,g,a,meta]=await Promise.all([", "const [s,g,a,meta,candidates]=await Promise.all([")
meta_line = "    fetch('data/meta.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():({}))\n"
if meta_line in s and "fetch('data/candidates.json'+bust" not in s:
    s = s.replace(meta_line, "    fetch('data/meta.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():({})),\n    fetch('data/candidates.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():([])).catch(()=>([]))\n")

s = s.replace("STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];", "STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];")

marker = "function weeklyStudies(){ return STUDIES; }\n"
helper = r'''function weeklyRemainder(){
  const {start,end}=editionBounds();
  const selectedKeys=new Set(STUDIES.map(x=>String(x.pmid||x.doi||x.url||x.title||'').toLowerCase()));
  return (CANDIDATES||[]).filter(s=>{
    const d=new Date((s.date||'')+'T00:00:00');
    const key=String(s.pmid||s.doi||s.url||s.title||'').toLowerCase();
    const text=((s.type||'')+' '+(s.title||'')+' '+(s.short||'')).toLowerCase();
    const isGuide=/guideline|guidelines|consensus|scientific statement|position statement|guía|guías|consenso/.test(text);
    return !isGuide && !selectedKeys.has(key) && !isNaN(d) && d>=start && d<end && s.title && (s.url||s.doi||s.pmid);
  }).sort((a,b)=>String(b.date||'').localeCompare(String(a.date||''))||String(a.title||'').localeCompare(String(b.title||'')));
}
function studySourceUrl(s){
  if(s.url) return s.url;
  if(s.doi) return 'https://doi.org/'+String(s.doi).replace(/^https?:\/\/(dx\.)?doi\.org\//i,'');
  if(s.pmid) return 'https://pubmed.ncbi.nlm.nih.gov/'+s.pmid+'/';
  return '#';
}
function renderWeeklyRemainder(){
  const box=document.getElementById('weeklyRemainder');
  if(!box) return;
  const items=weeklyRemainder();
  box.innerHTML=items.length ? `<div class="ruleTitle"><h2>Resto de estudios publicados en la última semana</h2><span></span></div><div class="remainderList"><ol>${items.map(s=>`<li><a href="${esc(studySourceUrl(s))}" target="_blank" rel="noopener">${esc(s.title)}</a></li>`).join('')}</ol></div>` : '';
}
'''
if "function weeklyRemainder(){" not in s:
    s = s.replace(marker, marker + helper)

if 'id="weeklyRemainder"' not in s:
    for anchor in ['<div id="homeFeed" class="storyGrid"></div>','<div id="latestFeed" class="storyGrid"></div>','<div id="homeStories" class="storyGrid"></div>']:
        if anchor in s:
            s = s.replace(anchor, anchor + '<div id="weeklyRemainder"></div>', 1)
            break

# Render remainder whenever home is rendered.
s = s.replace("if(id==='home')renderHome();if(id==='week')", "if(id==='home'){renderHome();renderWeeklyRemainder();}if(id==='week')")

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate: carga de candidatos y listado semanal corregidos.")
else:
    print("CardioUpdate: corrección ya aplicada.")
