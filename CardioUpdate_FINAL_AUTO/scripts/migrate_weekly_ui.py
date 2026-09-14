#!/usr/bin/env python3
"""Idempotent UI migration for CardioUpdate weekly-journal behavior and help manual."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

s = s.replace("CardioUpdate-3.5-guides-permanent-outside-weekly20", "CardioUpdate-4.7-manual-edition-counts")
s = s.replace("CardioUpdate-4.0-frozen-weekly-edition", "CardioUpdate-4.7-manual-edition-counts")
s = s.replace("CardioUpdate-4.6-mobile-remainder-title", "CardioUpdate-4.7-manual-edition-counts")
s = s.replace(".meterRow{display:grid;grid-template-columns:1fr;gap:12px;align-items:center;font-size:12px}",
              ".meterRow{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;font-size:12px}")

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

# Restore the numerical identity of each bar in "Esta edición".
repls = {
'Practice Changers<div class="bar"><span style="--w:${Math.max(8,STUDIES.filter(x=>x.level===\'Practice Changer\').length/STUDIES.length*100)}%;--c:#d51f32"></span></div></div></div>':
'Practice Changers<div class="bar"><span style="--w:${Math.max(8,STUDIES.filter(x=>x.level===\'Practice Changer\').length/STUDIES.length*100)}%;--c:#d51f32"></span></div></div><b>${STUDIES.filter(x=>x.level===\'Practice Changer\').length}</b></div>',
'Clínicamente relevantes<div class="bar"><span style="--w:${Math.max(8,STUDIES.filter(x=>x.level===\'Relevante\').length/STUDIES.length*100)}%;--c:#e58b1e"></span></div></div></div>':
'Clínicamente relevantes<div class="bar"><span style="--w:${Math.max(8,STUDIES.filter(x=>x.level===\'Relevante\').length/STUDIES.length*100)}%;--c:#e58b1e"></span></div></div><b>${STUDIES.filter(x=>x.level===\'Relevante\').length}</b></div>',
'Para seguimiento<div class="bar"><span style="--w:${Math.max(8,STUDIES.filter(x=>x.level===\'Seguimiento\').length/STUDIES.length*100)}%;--c:#3375d1"></span></div></div></div>':
'Para seguimiento<div class="bar"><span style="--w:${Math.max(8,STUDIES.filter(x=>x.level===\'Seguimiento\').length/STUDIES.length*100)}%;--c:#3375d1"></span></div></div><b>${STUDIES.filter(x=>x.level===\'Seguimiento\').length}</b></div>',
'Guías / consensos<div class="bar"><span style="--w:${Math.max(8,GUIDES.length/Math.max(1,STUDIES.length)*100)}%;--c:#0f96a8"></span></div></div></div>':
'Guías / consensos<div class="bar"><span style="--w:${Math.max(8,GUIDES.length/Math.max(1,STUDIES.length)*100)}%;--c:#0f96a8"></span></div></div><b>${GUIDES.length}</b></div>'
}
for old,new in repls.items():
    if old in s and new not in s:
        s=s.replace(old,new)

s = re.sub(r"function weeklyStudies\(\)\{.*?\n\}\nfunction filtered\(\)\{",
           "function weeklyStudies(){ return STUDIES; }\nfunction filtered(){",
           s, count=1, flags=re.S)

s = s.replace("El artículo y su abstract fueron incorporados por la búsqueda diaria.",
              "El artículo y su abstract fueron incorporados por la selección semanal.")

# In-app manual: compact ? button in the top bar, no extra bottom-nav item.
help_css = r'''
.helpBtn{width:38px;height:38px;border:1px solid #cfc7bd;background:#17324a;color:#fff;border-radius:50%;font-weight:900;font-size:18px;cursor:pointer;display:grid;place-items:center;flex:0 0 auto}.helpBtn:hover{background:#d51f32}.manualOverlay{display:none;position:fixed;inset:0;background:rgba(15,28,40,.62);z-index:200;padding:22px;overflow:auto}.manualOverlay.open{display:block}.manualCard{max-width:860px;margin:20px auto;background:#f6f1ea;border-top:10px solid #17324a;box-shadow:0 18px 60px rgba(0,0,0,.3);padding:28px 32px 36px;position:relative}.manualClose{position:sticky;float:right;top:8px;width:38px;height:38px;border:0;background:#17324a;color:#fff;border-radius:50%;font-size:22px;cursor:pointer}.manualCard h1{font-family:Georgia,serif;font-size:38px;margin:0 48px 5px 0;color:#17324a}.manualCard .manualSub{color:#6f7881;margin:0 0 22px}.manualCard h2{font-family:Georgia,serif;font-size:24px;color:#17324a;border-bottom:1px solid #d9d2c9;padding-bottom:6px;margin:27px 0 10px}.manualCard h3{font-size:15px;color:#d51f32;margin:18px 0 5px}.manualCard p,.manualCard li{font-size:14px;line-height:1.58;color:#45535e}.manualCard ol{padding-left:22px}.manualSequence{background:#fff;border-left:6px solid #d51f32;padding:13px 16px;font-weight:800}.manualNote{background:#fff;border:1px solid #d9d2c9;padding:15px 17px;margin-top:24px}.manualMenu{display:grid;grid-template-columns:1fr 1fr;gap:10px}.manualMenu>div{background:#fff;border:1px solid #e0d9d0;padding:12px}.manualMenu b{display:block;color:#17324a;margin-bottom:4px}@media(max-width:760px){.helpBtn{width:34px;height:34px;font-size:16px}.manualOverlay{padding:0}.manualCard{margin:0;min-height:100vh;padding:20px 17px 90px;border-top-width:7px}.manualCard h1{font-size:31px}.manualMenu{grid-template-columns:1fr}.manualCard h2{font-size:22px}.manualCard p,.manualCard li{font-size:14px}.mastActions{gap:7px}.mastActions .favCount{padding:9px 8px;font-size:11px}}
'''
if ".manualOverlay{" not in s:
    s=s.replace("</style>", help_css+"\n</style>",1)

help_button='<button class="helpBtn" onclick="document.getElementById(\'manualOverlay\').classList.add(\'open\')" title="Cómo usar CardioUpdate" aria-label="Cómo usar CardioUpdate">?</button>'
if "manualOverlay').classList.add" not in s:
    s=s.replace('<div class="mastActions">','<div class="mastActions">'+help_button,1)

manual_html=r'''
<div id="manualOverlay" class="manualOverlay" onclick="if(event.target===this)this.classList.remove('open')">
 <article class="manualCard">
  <button class="manualClose" onclick="document.getElementById('manualOverlay').classList.remove('open')" aria-label="Cerrar">×</button>
  <h1>Cómo usar CardioUpdate</h1><p class="manualSub">Guía breve para la actualización semanal en cardiología</p>
  <p>CardioUpdate está diseñada para facilitar la revisión de literatura cardiológica reciente. Funciona como una <b>revista cardiológica semanal</b>: durante la semana reúne nueva evidencia y cada viernes publica una selección de aproximadamente <b>20–30 trabajos de mayor relevancia</b>, que permanece estable hasta la edición siguiente.</p>
  <h2>Menú inferior</h2>
  <div class="manualMenu">
   <div><b>⌂ Portada</b>Entrada principal. Muestra el trabajo destacado, la composición de la edición, últimas incorporaciones y el resto de estudios publicados en la semana.</div>
   <div><b>▣ Semana</b>Permite recorrer ordenadamente los trabajos seleccionados para la edición vigente y filtrarlos por relevancia, tipo o revista.</div>
   <div><b>▦ Temas</b>Organiza la selección por áreas de cardiología para concentrarse en las subespecialidades de interés.</div>
   <div><b>▤ Guías</b>Reúne guías, consensos y documentos de referencia. Se mantienen como biblioteca y no dependen del recambio semanal.</div>
   <div><b>★ Favoritos</b>La estrella junto a cada publicación permite guardarla. Los favoritos quedan almacenados localmente en ese dispositivo y navegador.</div>
   <div><b>⌕ Buscar</b>Localiza estudios por enfermedad, intervención, fármaco, tema o revista: por ejemplo CAC, Lp(a), TAVI, HFpEF o mavacamten.</div>
  </div>
  <h2>Cómo leer un trabajo</h2>
  <p>Al tocar el título se abre la ficha del estudio. CardioUpdate conserva como referencia principal el <b>título original en inglés</b>.</p>
  <div class="manualSequence">Título original → Abstract → Análisis CardioUpdate</div>
  <h3>Abstract</h3><p>Permite revisar el contenido científico esencial del trabajo: objetivos, metodología, resultados y conclusiones cuando están disponibles.</p>
  <h3>Análisis CardioUpdate</h3><p>Interpreta qué aporta el estudio, la magnitud del efecto, sus limitaciones, relevancia clínica y potencial para modificar la conducta.</p>
  <h2>Practice Changers</h2><p>Identifica trabajos que merecen especial atención por su posible impacto sobre la práctica. Es una señal de prioridad y no sustituye la lectura crítica del artículo original.</p>
  <h2>Esta edición</h2><p>Las barras muestran la composición de la edición semanal. El número junto a cada barra indica cuántos trabajos fueron clasificados como <b>Practice Changers</b>, <b>Clínicamente relevantes</b>, <b>Para seguimiento</b> y cuántas <b>Guías/consensos</b> están disponibles.</p>
  <h2>Resto de estudios publicados en la última semana</h2><p>Incluye publicaciones detectadas en el mismo período que no integraron la selección principal. Se presentan como bibliografía simple con el título original enlazado a la fuente.</p>
  <h2>Rutina sugerida</h2>
  <ol><li>Abrir <b>Semana</b> una vez por semana y recorrer la selección.</li><li>Revisar Abstract + Análisis CardioUpdate de los trabajos relevantes.</li><li>Guardar con ★ los estudios para una lectura posterior.</li><li>Usar <b>Temas</b> para las áreas de interés personal.</li><li>Recorrer el <b>Resto de estudios</b> para detectar publicaciones adicionales.</li><li>Consultar <b>Guías</b> y utilizar <b>Buscar</b> cuando se necesite un tema concreto.</li></ol>
  <div class="manualNote"><b>Importante.</b> CardioUpdate es una herramienta de selección, organización y apoyo a la actualización profesional. No sustituye la lectura crítica de las publicaciones originales, las bases bibliográficas ni las recomendaciones de las guías de práctica clínica.</div>
 </article>
</div>
'''
if 'id="manualOverlay"' not in s:
    s=s.replace("</body>",manual_html+"\n</body>",1)

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate UI: edición semanal, manual y contadores aplicados.")
else:
    print("CardioUpdate UI ya estaba migrada.")

# This file is intentionally kept as an idempotent migration so future deploys remain consistent.
