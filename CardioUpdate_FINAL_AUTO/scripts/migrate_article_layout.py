#!/usr/bin/env python3
"""Idempotent UI migration: original English title -> original English abstract -> Spanish CardioUpdate analysis."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

# Version marker.
s = s.replace("CardioUpdate-4.0-frozen-weekly-edition", "CardioUpdate-4.1-title-abstract-analysis")
s = s.replace("CardioUpdate-4.1-title-abstract-analysis", "CardioUpdate-4.8-english-abstract-spanish-analysis")
s = s.replace("CardioUpdate-4.7-manual-edition-counts", "CardioUpdate-4.8-english-abstract-spanish-analysis")

# Always show the original indexed English title instead of abbreviated/edited short titles.
s = s.replace("${esc(lead.short)}", "${esc(lead.title)}")
s = s.replace("${esc(s.short)}", "${esc(s.title)}")

# Weekly lead: remove the explanatory sentence under the main title and the area/type-like label.
s = s.replace('<p class="dek">${esc(lead.why||lead.summary)}</p>', '')
s = s.replace('<span style="color:${a[1]};font-weight:900">${esc(a[3])}</span>', '')

# Cards/listings: do not show potentially truncated auto-generated summaries under titles.
s = s.replace('<p>${esc(s.summary)}</p>', '')

# Article header: title only, without the generated summary immediately below it.
s = s.replace('<p class="summary">${esc(s.summary)}</p>', '')

# Remove obsolete separate summary block.
summary_block = '<section class="articleBlock impact" style="--c:${a[1]}"><h2>Resumen CardioUpdate</h2><p>${esc(s.why||s.summary||\'Relevancia clínica pendiente de síntesis editorial.\')}</p></section>'
s = s.replace(summary_block, '')

# Detail view: never display the automatic-import warning and never show a machine-translated abstract.
# The original indexed English abstract is recovered from candidates.json (or abstract_en when present).
new_open = r'''function cleanAbstractHtml(v){
  const d=document.createElement('div'); d.innerHTML=String(v||'');
  return (d.textContent||d.innerText||'').replace(/\s+/g,' ').trim();
}
function originalAbstractFor(s){
  if(s.abstract_en){
    if(Array.isArray(s.abstract_en)) return s.abstract_en.map(x=>Array.isArray(x)?x[1]:x).filter(Boolean).join(' ');
    return String(s.abstract_en);
  }
  const same=(a,b)=>String(a||'').trim().toLowerCase()===String(b||'').trim().toLowerCase();
  const c=(CANDIDATES||[]).find(x=>(s.pmid&&x.pmid&&same(s.pmid,x.pmid))||(s.doi&&x.doi&&same(s.doi,x.doi))||(!s.pmid&&!s.doi&&x.title&&same(s.title,x.title)));
  return cleanAbstractHtml(c&&c.abstractText ? c.abstractText : '');
}
function openStudy(id){let s=STUDIES.find(x=>x.id===id);if(!s)return;previous=document.querySelector('.page.active')?.id||'week';let a=areaOf(s.area);let abs=originalAbstractFor(s);document.getElementById('detailBody').innerHTML=`<div class="detailWrap"><button class="back" onclick="go('${previous==='detail'?'week':previous}')">← Volver</button><article class="articleHead" style="--c:${a[1]}"><div class="issueTag" style="background:${a[1]}">${esc(a[3])} · ${esc(s.level)}</div><h1>${esc(s.title)}</h1><div class="articleByline">${esc(s.type)} · ${esc(s.journal)} · ${esc(s.date)}</div><div class="sourceBar"><a href="${s.url}" target="_blank" rel="noopener">Artículo original ↗</a><a class="alt" href="#" onclick="event.preventDefault();toggleFav('${s.id}');openStudy('${s.id}')">${isFav(s.id)?'★ Guardado':'☆ Guardar'}</a></div></article><div class="articleGrid">${abs?`<section class="abstractFull" style="--c:${a[1]}"><h2>Abstract</h2><p class="abstractNote">Original English abstract from the indexed scientific source.</p><section class="abstractSection"><p>${esc(abs)}</p></section></section>`:''}${s.analysis_es?`<section class="articleBlock impact" style="--c:${a[1]}"><h2>Análisis CardioUpdate</h2><p>${esc(s.analysis_es)}</p></section>`:''}</div></div>`;go('detail')}'''
s = re.sub(r"function openStudy\(id\)\{.*?\}\nfunction runSearch", lambda m: new_open + "\nfunction runSearch", s, count=1, flags=re.S)

# Keep the embedded manual consistent with the new language policy.
s = s.replace("<h3>Abstract</h3><p>Permite revisar el contenido científico esencial del trabajo: objetivos, metodología, resultados y conclusiones cuando están disponibles.</p>",
              "<h3>Abstract</h3><p>Se presenta en su <b>idioma original en inglés</b>, sin traducción automática, para preservar con máxima fidelidad objetivos, metodología, resultados, cifras y conclusiones.</p>")
s = s.replace("Revisar Abstract + Análisis CardioUpdate de los trabajos relevantes.",
              "Revisar el Abstract original en inglés + el Análisis CardioUpdate en español de los trabajos relevantes.")

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate: abstract original en inglés y análisis CardioUpdate en español.")
else:
    print("CardioUpdate: política de idioma de artículos ya aplicada.")
