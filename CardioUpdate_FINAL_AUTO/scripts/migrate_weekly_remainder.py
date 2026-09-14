#!/usr/bin/env python3
"""Ensure bibliography lists ONLY last-week studies not selected into the weekly issue."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

s = s.replace("CardioUpdate-4.2-weekly-remainder", "CardioUpdate-4.3-weekly-remainder-fixed")

needle = ".empty{background:#fff;border:1px dashed #bdb5ac;padding:34px;text-align:center;color:#737b82}\n"
style = needle + ".remainderList{background:#fff;border-top:3px solid #17212b;padding:8px 26px 20px}.remainderList ol{margin:0;padding-left:28px}.remainderList li{padding:10px 4px;border-bottom:1px solid var(--line);font-family:Georgia,serif;font-size:16px;line-height:1.35}.remainderList li:last-child{border-bottom:0}.remainderList a{text-decoration:none}.remainderList a:hover{text-decoration:underline;color:#d51f32}\n"
if ".remainderList{" not in s:
    s = s.replace(needle, style)

# Keep the complete published database as a source pool. The weekly issue itself is STUDIES.
s = s.replace(
    "let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={}, CANDIDATES=[];",
    "let STUDIES=[], ALL_STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={}, CANDIDATES=[];"
)

# Load candidates as an auxiliary source, but never depend exclusively on it.
s = s.replace("const [s,g,a,meta]=await Promise.all([", "const [s,g,a,meta,candidates]=await Promise.all([")
meta_line = "    fetch('data/meta.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():({}))\n"
if meta_line in s and "fetch('data/candidates.json'+bust" not in s:
    s = s.replace(meta_line, "    fetch('data/meta.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():({})),\n    fetch('data/candidates.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():([])).catch(()=>([]))\n")

s = s.replace(
    "STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];",
    "ALL_STUDIES=Array.isArray(s)?s:[]; STUDIES=selectPublishedEdition(ALL_STUDIES); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];"
)

# Replace the function entirely so older broken variants are removed.
new_func = r'''function weeklyRemainder(){
  const {start,end}=editionBounds();
  const keyOf=x=>String(x.pmid||x.doi||x.url||x.title||'').trim().toLowerCase();
  const dateOf=x=>new Date((x.date||x.firstPublicationDate||'')+'T00:00:00');
  const selectedKeys=new Set(STUDIES.map(keyOf));
  const byKey=new Map();

  // First source: the full studies database, which contains the studies already accumulated
  // before the weekly-selection logic was introduced. Second source: new raw candidates.
  [...(ALL_STUDIES||[]), ...(CANDIDATES||[])].forEach(x=>{
    if(!x || !x.title) return;
    const key=keyOf(x);
    if(!key || selectedKeys.has(key)) return;
    const d=dateOf(x);
    if(isNaN(d) || d<start || d>=end) return;
    const text=((x.type||'')+' '+(x.title||'')+' '+(x.short||'')).toLowerCase();
    if(/guideline|guidelines|consensus|scientific statement|position statement|guía|guías|consenso/.test(text)) return;
    if(!(x.url||x.doi||x.pmid)) return;
    if(!byKey.has(key)) byKey.set(key,x);
  });

  return [...byKey.values()].sort((a,b)=>
    String(b.date||b.firstPublicationDate||'').localeCompare(String(a.date||a.firstPublicationDate||'')) ||
    String(a.title||'').localeCompare(String(b.title||''))
  );
}
'''
s = re.sub(r"function weeklyRemainder\(\)\{.*?\n\}\nfunction studySourceUrl", new_func + "function studySourceUrl", s, count=1, flags=re.S)

# Insert the visual container directly after Últimas incorporaciones.
if 'id="weeklyRemainder"' not in s:
    anchor = '<div id="homeFeed" class="feed"></div>'
    if anchor in s:
        s = s.replace(anchor, anchor + '\n <div id="weeklyRemainder"></div>', 1)

# Always render after the home feed is prepared.
s = s.replace(
    "document.getElementById('homeFeed').innerHTML=STUDIES.slice(4,10).map(feedItem).join('');\n}",
    "document.getElementById('homeFeed').innerHTML=STUDIES.slice(4,10).map(feedItem).join('');\n renderWeeklyRemainder();\n}"
)

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate: listado bibliográfico reconstruido desde la base completa + candidatos.")
else:
    print("CardioUpdate: listado bibliográfico ya estaba corregido.")
