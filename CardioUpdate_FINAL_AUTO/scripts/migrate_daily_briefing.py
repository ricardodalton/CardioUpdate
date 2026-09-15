#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'index.html';s=p.read_text(encoding='utf-8');o=s
# CSS
if '.briefingDay{' not in s:
 s=s.replace('.mobileNav{display:none}', '.briefingDay{background:#fff;border-top:4px solid #17324a;padding:22px 25px;margin-bottom:18px}.briefingDay h2{font-family:Georgia,serif;font-size:28px;margin:0 0 18px}.briefItem{padding:17px 0;border-top:1px solid var(--line)}.briefItem h3{font-family:Georgia,serif;font-size:22px;line-height:1.15;margin:0 0 9px}.briefItem p{font-size:14px;line-height:1.55;color:#53616c;margin:6px 0}.briefItem strong{color:#17212b}.briefItem a{display:inline-block;margin-top:5px;color:#d51f32;font-weight:900;text-decoration:none;font-size:12px}.briefArchive{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 18px}.briefArchive button{border:1px solid #bdb5ac;background:#fff;padding:8px 10px;font-weight:800;cursor:pointer}.briefArchive button.active{background:#17324a;color:#fff}.mobileNav{display:none}')
# Add sidebar button after Portada if identifiable
needle='<button data-page="home"'
if 'data-page="briefing"' not in s and needle in s:
 pos=s.find('</button>',s.find(needle))+9
 s=s[:pos]+'<button data-page="briefing" onclick="go(\'briefing\')"><i>◉</i> Briefing diario</button>'+s[pos:]
# Add page before detail page
if 'id="briefing"' not in s:
 marker='<section class="page" id="detail">'
 page='''<section class="page" id="briefing"><div class="sectionHeader"><div><h1>Briefing diario</h1><p>5 novedades · cardiología, medicina e IA · narrado en tercera persona</p></div></div><div id="briefArchive" class="briefArchive"></div><div id="briefBody"></div></section>'''
 s=s.replace(marker,page+marker)
# State
s=s.replace('let STUDIES=[],GUIDES=[],AREAS=[],META={},CANDIDATES=[];', 'let STUDIES=[],GUIDES=[],AREAS=[],META={},CANDIDATES=[],BRIEFINGS=[];')
# Fetch alongside candidates: robust replacements for common current loader
s=s.replace("fetch('data/candidates.json?ts='+Date.now()).then(r=>r.ok?r.json():[]).catch(()=>[])", "fetch('data/candidates.json?ts='+Date.now()).then(r=>r.ok?r.json():[]).catch(()=>[]),fetch('data/briefings.json?ts='+Date.now()).then(r=>r.ok?r.json():[]).catch(()=>[])")
s=s.replace('const [s,g,a,meta,candidates]=await Promise.all([', 'const [s,g,a,meta,candidates,briefings]=await Promise.all([')
s=s.replace('CANDIDATES=Array.isArray(candidates)?candidates:[];', 'CANDIDATES=Array.isArray(candidates)?candidates:[];BRIEFINGS=Array.isArray(briefings)?briefings:[];')
# Render functions before runSearch
if 'function renderBriefing(' not in s:
 fn='''function renderBriefing(idx=0){let b=BRIEFINGS[idx];let tabs=document.getElementById('briefArchive'),box=document.getElementById('briefBody');if(!tabs||!box)return;if(!BRIEFINGS.length){tabs.innerHTML='';box.innerHTML='<div class="empty">El briefing diario se generará en la próxima actualización automática.</div>';return}tabs.innerHTML=BRIEFINGS.map((x,i)=>`<button class="${i===idx?'active':''}" onclick="renderBriefing(${i})">${esc(x.date)}</button>`).join('');box.innerHTML=`<div class="briefingDay"><h2>${esc(b.date)}</h2>${(b.items||[]).map((x,i)=>`<article class="briefItem"><h3>${i+1}. ${esc(x.title)}</h3><p><strong>Qué ocurrió.</strong> ${esc(x.what_happened)}</p><p><strong>Por qué es relevante.</strong> ${esc(x.why_relevant)}</p><p><strong>Implicación práctica.</strong> ${esc(x.practical_implication)}</p><a href="${x.url}" target="_blank" rel="noopener">Fuente original ↗</a></article>`).join('')}</div>`}'''
 s=s.replace('function runSearch',fn+'\nfunction runSearch')
# go renderer
s=s.replace("if(id==='home')renderHome();", "if(id==='home')renderHome();if(id==='briefing')renderBriefing();")
# Manual mention
s=s.replace('<h3>⌂ Portada</h3>', '<h3>◉ Briefing diario</h3><p>Presenta cada mañana cinco novedades de cardiología, medicina e inteligencia artificial aplicada a la salud, redactadas en tercera persona. Conserva los últimos siete briefings.</p><h3>⌂ Portada</h3>')
if s!=o:p.write_text(s,encoding='utf-8');print('CardioUpdate: sección Briefing diario aplicada.')
else:print('CardioUpdate: Briefing diario ya aplicado.')
