#!/usr/bin/env python3
"""Maintain the weekly remainder and group its articles by publication date."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / 'index.html'
s = p.read_text(encoding='utf-8')
original = s

css = '''
#weeklyRemainder .remainderDay{margin:12px 0;border:1px solid rgba(125,145,160,.25);border-radius:10px;overflow:hidden}
#weeklyRemainder .remainderDay summary{cursor:pointer;padding:12px 16px;font-weight:700;list-style:revert}
#weeklyRemainder .remainderDay summary:focus-visible{outline:2px solid currentColor;outline-offset:-3px}
#weeklyRemainder .remainderDay ol{margin:0;padding:4px 22px 14px 42px}
#weeklyRemainder .remainderDay li{margin:8px 0;line-height:1.4;overflow-wrap:anywhere}
@media(max-width:760px){#weeklyRemainder .ruleTitle{align-items:flex-start;gap:8px}#weeklyRemainder .ruleTitle h2{white-space:normal;overflow-wrap:anywhere;word-break:normal;font-size:25px;line-height:1.08;max-width:100%;flex:1}#weeklyRemainder .ruleTitle span{display:none}.remainderList{padding:0 10px}#weeklyRemainder .remainderDay summary{padding:12px}#weeklyRemainder .remainderDay ol{padding-left:32px;padding-right:12px}}
'''
if '#weeklyRemainder .remainderDay{' not in s:
    s = s.replace('</style>', css + '</style>', 1)

s = s.replace('let STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={}, CANDIDATES=[];', 'let STUDIES=[], ALL_STUDIES=[], GUIDES=[], AREAS=[], AM={}, META={}, CANDIDATES=[];')
s = s.replace('const [s,g,a,meta]=await Promise.all([', 'const [s,g,a,meta,candidates]=await Promise.all([')
meta_line = "    fetch('data/meta.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():({}))\n"
if meta_line in s and "fetch('data/candidates.json'+bust" not in s:
    s = s.replace(meta_line, "    fetch('data/meta.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():({})),\n    fetch('data/candidates.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():[]).catch(()=>[])\n")
replacement = 'ALL_STUDIES=Array.isArray(s)?s:[]; const weekly=selectPublishedEdition(ALL_STUDIES); STUDIES=weekly.length?weekly:ALL_STUDIES.slice(0,30); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];'
for old in ['ALL_STUDIES=Array.isArray(s)?s:[]; STUDIES=selectPublishedEdition(ALL_STUDIES); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];', 'STUDIES=selectPublishedEdition(s); GUIDES=g; AREAS=a; META=meta; CANDIDATES=Array.isArray(candidates)?candidates:[];']:
    s = s.replace(old, replacement)

helper = r'''function currentCycleBounds(now=new Date()){
  const d=new Date(now); d.setHours(0,0,0,0);
  const daysSinceSaturday=(d.getDay()+1)%7;
  const start=new Date(d); start.setDate(d.getDate()-daysSinceSaturday);
  const end=new Date(d); end.setDate(d.getDate()+1);
  return {start,end};
}
function weeklyRemainder(){
  const {start,end}=currentCycleBounds();
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
  return [...byKey.values()].sort((a,b)=>String(dateValue(b)).localeCompare(String(dateValue(a))) || String(a.title||'').localeCompare(String(b.title||'')));
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
  const byDay=new Map();
  items.forEach(x=>{
    const day=String(x.date||x.firstPublicationDate||x.firstIndexDate||'').slice(0,10);
    if(!byDay.has(day)) byDay.set(day,[]);
    byDay.get(day).push(x);
  });
  const dayLabel=day=>{
    const [year,month,date]=day.split('-').map(Number);
    return new Intl.DateTimeFormat('es-AR',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(Date.UTC(year,month-1,date)));
  };
  const sections=[...byDay].map(([day,studies],index)=>`<details class="remainderDay" ${index===0?'open':''}><summary>${esc(dayLabel(day))} — ${studies.length} ${studies.length===1?'estudio':'estudios'}</summary><ol>${studies.map(x=>`<li><a href="${esc(studySourceUrl(x))}" target="_blank" rel="noopener">${esc(x.title)}</a></li>`).join('')}</ol></details>`).join('');
  box.innerHTML=items.length
    ? `<div class="ruleTitle"><h2>Resto de estudios publicados en la última semana</h2><span></span></div><div class="remainderList">${sections}</div>`
    : '';
}
'''
pattern = r'function weeklyRemainder\(\)\{.*?\n\}\nfunction studySourceUrl\(.*?\n\}\nfunction renderWeeklyRemainder\(\)\{.*?\n\}\n'
if re.search(pattern,s,flags=re.S):
    s = re.sub(pattern,lambda _:helper,s,count=1,flags=re.S)
elif 'function weeklyRemainder(){' not in s:
    s = s.replace('function weeklyStudies(){ return STUDIES; }\n','function weeklyStudies(){ return STUDIES; }\n'+helper,1)
if 'id="weeklyRemainder"' not in s:
    s=s.replace('<div id="homeFeed" class="feed"></div>','<div id="homeFeed" class="feed"></div>\n <div id="weeklyRemainder"></div>',1)
if 'renderWeeklyRemainder();' not in s[s.find('function renderHome(){'):s.find('function weeklyStudies(){')]:
    s=s.replace("document.getElementById('homeFeed').innerHTML=STUDIES.slice(4,10).map(feedItem).join('');\n}","document.getElementById('homeFeed').innerHTML=STUDIES.slice(4,10).map(feedItem).join('');\n renderWeeklyRemainder();\n}")
s=s.replace('renderHome(); renderWeeklyRemainder();','renderHome();').replace('renderHome();renderWeeklyRemainder();renderWeek();','renderHome();renderWeek();').replace("if(id==='home'){renderHome();renderWeeklyRemainder();}","if(id==='home')renderHome();")
if s!=original:
    p.write_text(s,encoding='utf-8')
    print('CardioUpdate: estudios complementarios agrupados por fecha de publicación.')
else:
    print('CardioUpdate: sin cambios pendientes.')
