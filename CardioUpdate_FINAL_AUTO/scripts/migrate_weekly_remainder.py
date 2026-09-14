#!/usr/bin/env python3
"""Add a bibliography-style list of non-selected studies from the weekly candidate pool."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

s = s.replace("CardioUpdate-4.1-title-abstract-analysis", "CardioUpdate-4.2-weekly-remainder")

# Add a small bibliography-like style.
needle = ".empty{background:#fff;border:1px dashed #bdb5ac;padding:34px;text-align:center;color:#737b82}\n"
style = needle + ".remainderList{background:#fff;border-top:3px solid #17212b;padding:8px 26px 20px}.remainderList ol{margin:0;padding-left:28px}.remainderList li{padding:10px 4px;border-bottom:1px solid var(--line);font-family:Georgia,serif;font-size:16px;line-height:1.35}.remainderList li:last-child{border-bottom:0}.remainderList a{text-decoration:none}.remainderList a:hover{text-decoration:underline;color:#d51f32}\n"
if ".remainderList{" not in s:
    s = s.replace(needle, style)

# Candidate pool is intentionally separate from the selected weekly issue.
s = s.replace("let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={};", "let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={}, CANDIDATES=[];")

# Fetch candidates when available; older deployments remain compatible.
s = s.replace("fetch('data/meta.json').then(r=>r.json()).catch(()=>({}))", "fetch('data/meta.json').then(r=>r.json()).catch(()=>({})), fetch('data/candidates.json').then(r=>r.json()).catch(()=>([]))")
s = s.replace(".then(([s,g,a,meta])=>{", ".then(([s,g,a,meta,candidates])=>{")
s = s.replace("STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta;", "STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];")

# Render only studies from the current edition window that were NOT selected.
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
  box.innerHTML=items.length
    ? `<div class="ruleTitle"><h2>Resto de estudios publicados en la última semana</h2><span></span></div><div class="remainderList"><ol>${items.map(s=>`<li><a href="${esc(studySourceUrl(s))}" target="_blank" rel="noopener">${esc(s.title)}</a></li>`).join('')}</ol></div>`
    : '';
}
'''
if "function weeklyRemainder(){" not in s:
    s = s.replace(marker, marker + helper)

# Put it immediately after the Últimas incorporaciones container.
# The exact feed container is followed by its section closing tag in the current app.
if 'id="weeklyRemainder"' not in s:
    candidates = [
        '<div id="homeFeed" class="storyGrid"></div>',
        '<div id="latestFeed" class="storyGrid"></div>',
        '<div id="homeStories" class="storyGrid"></div>'
    ]
    for anchor in candidates:
        if anchor in s:
            s = s.replace(anchor, anchor + '<div id="weeklyRemainder"></div>', 1)
            break

# Render after home content has been populated.
for call in ["renderHome();", "renderLatest();"]:
    if call in s and "renderWeeklyRemainder();" not in s[s.find(call):s.find(call)+100]:
        s = s.replace(call, call + " renderWeeklyRemainder();", 1)
        break

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate: agregado resto bibliográfico de estudios semanales.")
else:
    print("CardioUpdate: resto bibliográfico ya estaba configurado.")
