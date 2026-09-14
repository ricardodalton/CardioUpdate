#!/usr/bin/env python3
"""Keep app stable and list ONLY prior-week non-selected studies."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

s = s.replace("CardioUpdate-4.3-weekly-remainder-fixed", "CardioUpdate-4.4-stable-weekly-remainder")
s = s.replace("CardioUpdate-4.2-weekly-remainder", "CardioUpdate-4.4-stable-weekly-remainder")

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

# Published edition: use exact weekly window when present. If legacy data does not contain
# that window, keep the app alive with the already-published leading records instead of crashing.
assign_patterns = [
    "ALL_STUDIES=Array.isArray(s)?s:[]; STUDIES=selectPublishedEdition(ALL_STUDIES); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];",
    "STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];"
]
replacement = "ALL_STUDIES=Array.isArray(s)?s:[]; const weekly=selectPublishedEdition(ALL_STUDIES); STUDIES=weekly.length?weekly:ALL_STUDIES.slice(0,30); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];"
for pat in assign_patterns:
    s = s.replace(pat, replacement)

new_func = r'''function weeklyRemainder(){
  const {start,end}=editionBounds();
  const keyOf=x=>String(x?.pmid||x?.doi||x?.url||x?.title||'').trim().toLowerCase();
  const dateValue=x=>x?.date||x?.firstPublicationDate||x?.firstIndexDate||'';
  const selectedKeys=new Set((STUDIES||[]).map(keyOf));
  const byKey=new Map();

  [...(ALL_STUDIES||[]), ...(CANDIDATES||[])].forEach(x=>{
    if(!x || !x.title) return;
    const key=keyOf(x);
    if(!key || selectedKeys.has(key)) return;
    const raw=String(dateValue(x)).slice(0,10);
    const d=new Date(raw+'T00:00:00');
    if(isNaN(d) || d<start || d>=end) return;
    const text=((x.type||'')+' '+(x.title||'')+' '+(x.short||'')+' '+((x.pubTypeList||{}).pubType||'')).toLowerCase();
    if(/guideline|guidelines|consensus|scientific statement|position statement|guía|guías|consenso/.test(text)) return;
    if(!(x.url||x.doi||x.pmid)) return;
    if(!byKey.has(key)) byKey.set(key,x);
  });

  return [...byKey.values()].sort((a,b)=>
    String(dateValue(b)).localeCompare(String(dateValue(a))) ||
    String(a.title||'').localeCompare(String(b.title||''))
  );
}
'''
s = re.sub(r"function weeklyRemainder\(\)\{.*?\n\}\nfunction studySourceUrl", new_func + "function studySourceUrl", s, count=1, flags=re.S)

if 'id="weeklyRemainder"' not in s:
    anchor='<div id="homeFeed" class="feed"></div>'
    s=s.replace(anchor, anchor+'\n <div id="weeklyRemainder"></div>',1)

# Render only after home elements exist.
s = s.replace(
    "document.getElementById('homeFeed').innerHTML=STUDIES.slice(4,10).map(feedItem).join('');\n}",
    "document.getElementById('homeFeed').innerHTML=STUDIES.slice(4,10).map(feedItem).join('');\n renderWeeklyRemainder();\n}"
)

# Avoid duplicated external render calls from older migrations.
s = s.replace("renderHome(); renderWeeklyRemainder();", "renderHome();")
s = s.replace("renderHome();renderWeeklyRemainder();renderWeek();", "renderHome();renderWeek();")
s = s.replace("if(id==='home'){renderHome();renderWeeklyRemainder();}", "if(id==='home')renderHome();")

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate: edición semanal estabilizada y bibliografía residual corregida.")
else:
    print("CardioUpdate: sin cambios pendientes.")
