#!/usr/bin/env python3
"""Idempotently place the daily briefing immediately before weekly remainder."""
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'index.html'
s=p.read_text(encoding='utf-8'); old=s
# The daily briefing belongs on the homepage, immediately before the remainder.
if 'id="briefingHome"' not in s:
    assert '<div id="weeklyRemainder"></div>' in s
    s=s.replace('<div id="weeklyRemainder"></div>', '<div id="briefingHome"></div>\n <div id="weeklyRemainder"></div>',1)
# Do not add a seventh mobile navigation button or a separate page.
if 'BRIEFINGS=[]' not in s:
    assert 'META={}, CANDIDATES=[];' in s
    s=s.replace('META={}, CANDIDATES=[];', 'META={}, CANDIDATES=[], BRIEFINGS=[];',1)
# Fix prior migration's broken Promise.all: six destructured results but only five fetches.
fetch="fetch('data/briefings.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():([])).catch(()=>([]))"
if fetch not in s:
    needle="fetch('data/candidates.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():([])).catch(()=>([]))"
    assert needle in s
    s=s.replace(needle,needle+',\n    '+fetch,1)
if 'const [s,g,a,meta,candidates,briefings]' not in s:
    assert 'const [s,g,a,meta,candidates]' in s
    s=s.replace('const [s,g,a,meta,candidates]','const [s,g,a,meta,candidates,briefings]',1)
if 'BRIEFINGS=Array.isArray(briefings)?briefings:[];' not in s:
    assert 'CANDIDATES=Array.isArray(candidates)?candidates:[];' in s
    s=s.replace('CANDIDATES=Array.isArray(candidates)?candidates:[];', 'CANDIDATES=Array.isArray(candidates)?candidates:[];BRIEFINGS=Array.isArray(briefings)?briefings:[];',1)
# Always render before the bibliography in the same homepage.
if 'renderBriefingHome();' not in s:
    assert ' renderWeeklyRemainder();' in s
    s=s.replace(' renderWeeklyRemainder();',' renderBriefingHome();\n renderWeeklyRemainder();',1)
if 'function renderBriefingHome(' not in s:
    anchor='function renderWeeklyRemainder(){'
    assert anchor in s
    fn='''function renderBriefingHome(idx=0){
 const box=document.getElementById('briefingHome');if(!box)return;
 const valid=(BRIEFINGS||[]).filter(x=>Array.isArray(x.items)&&x.items.length);
 if(!valid.length){box.innerHTML=`<div class="ruleTitle"><h2>Briefing diario</h2><span></span><small>Actualización diaria</small></div><div class="empty">El briefing de hoy aún no está disponible.</div>`;return;}
 const b=valid[idx]||valid[0];
 box.innerHTML=`<div class="ruleTitle"><h2>Briefing diario</h2><span></span><small>Cardiología · Medicina · IA</small></div><div class="briefArchive">${valid.map((x,i)=>`<button class="${x===b?'active':''}" onclick="renderBriefingHome(${i})">${esc(x.date)}</button>`).join('')}</div><div class="briefingDay"><h2>${esc(b.date)}</h2>${b.items.map((x,i)=>`<article class="briefItem"><h3>${i+1}. ${esc(x.title)}</h3><p><strong>Qué ocurrió.</strong> ${esc(x.what_happened)}</p><p><strong>Por qué es relevante.</strong> ${esc(x.why_relevant)}</p><p><strong>Implicación práctica.</strong> ${esc(x.practical_implication)}</p><a href="${esc(x.url)}" target="_blank" rel="noopener">Fuente original ↗</a></article>`).join('')}</div>`;
}
'''
    s=s.replace(anchor,fn+anchor,1)
# A prior version added CSS but did not insert the section; retain its styling.
if '.briefingDay{' not in s:
    assert '.mobileNav{display:none}' in s
    s=s.replace('.mobileNav{display:none}', '.briefingDay{background:#fff;padding:22px 25px;margin-bottom:18px}.briefItem{padding:17px 0;border-top:1px solid var(--line)}.briefItem h3{font-family:Georgia,serif;font-size:22px}.briefItem p{font-size:14px;line-height:1.55}.briefArchive{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:18px}.briefArchive button{padding:8px;border:1px solid var(--line);background:#fff}.briefArchive button.active{background:#17324a;color:#fff}.mobileNav{display:none}',1)
if s!=old:p.write_text(s,encoding='utf-8');print('Briefing diario: homepage placement and data fetch repaired.')
else:print('Briefing diario: migration already applied.')
