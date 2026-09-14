#!/usr/bin/env python3
"""Keep CardioUpdate stable and list ONLY prior-week non-selected studies."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

for old in [
    "CardioUpdate-4.2-weekly-remainder",
    "CardioUpdate-4.3-weekly-remainder-fixed",
    "CardioUpdate-4.4-stable-weekly-remainder",
]:
    s = s.replace(old, "CardioUpdate-4.5-stable-remainder-functions")

# Ensure full source pool exists.
s = s.replace(
    "let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={}, CANDIDATES=[];",
    "let STUDIES=[], ALL_STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={}, CANDIDATES=[];"
)

# Candidate loading is optional and must never break the app.
s = s.replace("const [s,g,a,meta]=await Promise.all([", "const [s,g,a,meta,candidates]=await Promise.all([")
meta_line = "    fetch('data/meta.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():({}))\n"
if meta_line in s and "fetch('data/candidates.json'+bust" not in s:
    s = s.replace(meta_line, "    fetch('data/meta.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():({})),\n    fetch('data/candidates.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():[]).catch(()=>[])\n")

assign_patterns = [
    "ALL_STUDIES=Array.isArray(s)?s:[]; STUDIES=selectPublishedEdition(ALL_STUDIES); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];",
    "STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];"
]
replacement = "ALL_STUDIES=Array.isArray(s)?s:[]; const weekly=selectPublishedEdition(ALL_STUDIES); STUDIES=weekly.length?weekly:ALL_STUDIES.slice(0,30); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];"
for pat in assign_patterns:
    s = s.replace(pat, replacement)

helper = r'''function weeklyRemainder(){
  const {start,end}=editionBounds();
  const keyOf=x=>String((x&&x.pmid)||(x&&x.doi)||(x&&x.url)||(x&&x.title)||'').trim().toLowerCase();
  const dateValue=x=>(x&&x.date)||(x&&x.firstPublicationDate)||(x&&x.firstIndexDate)||'';
  const selectedKeys=new Set((STUDIES||[]).map(keyOf));
  const byKey=new Map();

  [...(ALL_STUDIES||[]), ...(CANDIDATES||[])].forEach(x=>{
    if(!x || !x.title) return;
    const key=keyOf(x);
    if(!key || selectedKeys.has(key)) return;
    const raw=String(dateValue(x)).slice(0,10);
    const d=new Date(raw+'T00:00:00');
    if(isNaN(d) || d<start || d>=end) return;
    const pubTypes=Array.isArray(x.pubTypeList?.pubType) ? x.pubTypeList.pubType.join(' ') : (x.pubTypeList?.pubType||'');
    const text=((x.type||'')+' '+(x.title||'')+' '+(x.short||'')+' '+pubTypes).toLowerCase();
    if(/guideline|guidelines|consensus|scientific statement|position statement|guía|guías|consenso/.test(text)) return;
    if(!(x.url||x.doi||x.pmid)) return;
    if(!byKey.has(key)) byKey.set(key,x);
  });

  return [...byKey.values()].sort((a,b)=>
    String(dateValue(b)).localeCompare(String(dateValue(a))) ||
    String(a.title||'').localeCompare(String(b.title||''))
  );
}
function studySourceUrl(x){
  if(x.url) return x.url;
  if(x.doi) return 'https://doi.org/'+String(x.doi).replace(/^https?:\/\/(dx\.)?doi\.org\//i,'');
  if(x.pmid) return 'https://pubmed.ncbi.nlm.nih.gov/'+x.pmid+'/';
  return '#';
}
function renderWeeklyRemainder(){
  const box=document.getElementById('weeklyRemainder');
  if(!box) return;
  const items=weeklyRemainder();
  box.innerHTML=items.length
    ? `<div class="ruleTitle"><h2>Resto de estudios publicados en la última semana</h2><span></span></div><div class="remainderList"><ol>${items.map(x=>`<li><a href="${esc(studySourceUrl(x))}" target="_blank" rel="noopener">${esc(x.title)}</a></li>`).join('')}</ol></div>`
    : '';
}
'''

# Replace an existing helper block when present; otherwise insert it after weeklyStudies().
pattern = r"function weeklyRemainder\(\)\{.*?\n\}\nfunction studySourceUrl\(.*?\n\}\nfunction renderWeeklyRemainder\(\)\{.*?\n\}\n"
if re.search(pattern, s, flags=re.S):
    s = re.sub(pattern, helper, s, count=1, flags=re.S)
elif "function weeklyRemainder(){" not in s:
    marker = "function weeklyStudies(){ return STUDIES; }\n"
    if marker in s:
        s = s.replace(marker, marker + helper, 1)

# Ensure visual container exists.
if 'id="weeklyRemainder"' not in s:
    anchor='<div id="homeFeed" class="feed"></div>'
    s=s.replace(anchor, anchor+'\n <div id="weeklyRemainder"></div>',1)

# Render only after home elements exist.
if "renderWeeklyRemainder();" not in s[s.find("function renderHome(){"):s.find("function weeklyStudies(){")]:
    s = s.replace(
        "document.getElementById('homeFeed').innerHTML=STUDIES.slice(4,10).map(feedItem).join('');\n}",
        "document.getElementById('homeFeed').innerHTML=STUDIES.slice(4,10).map(feedItem).join('');\n renderWeeklyRemainder();\n}"
    )

# Remove duplicated external render calls from older migrations.
s = s.replace("renderHome(); renderWeeklyRemainder();", "renderHome();")
s = s.replace("renderHome();renderWeeklyRemainder();renderWeek();", "renderHome();renderWeek();")
s = s.replace("if(id==='home'){renderHome();renderWeeklyRemainder();}", "if(id==='home')renderHome();")

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate: funciones de bibliografía semanal restauradas y estabilizadas.")
else:
    print("CardioUpdate: sin cambios pendientes.")
