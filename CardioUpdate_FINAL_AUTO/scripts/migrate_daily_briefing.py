#!/usr/bin/env python3
"""Idempotently place the daily briefing on the homepage and update its tutorial."""
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'index.html'
s=p.read_text(encoding='utf-8'); old=s
if 'id="briefingHome"' not in s:
    assert '<div id="weeklyRemainder"></div>' in s
    s=s.replace('<div id="weeklyRemainder"></div>', '<div id="briefingHome"></div>\n <div id="weeklyRemainder"></div>',1)
if 'BRIEFINGS=[]' not in s:
    assert 'META={}, CANDIDATES=[];' in s
    s=s.replace('META={}, CANDIDATES=[];', 'META={}, CANDIDATES=[], BRIEFINGS=[];',1)
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
if '.briefingDay{' not in s:
    assert '.mobileNav{display:none}' in s
    s=s.replace('.mobileNav{display:none}', '.briefingDay{background:#fff;padding:22px 25px;margin-bottom:18px}.briefItem{padding:17px 0;border-top:1px solid var(--line)}.briefItem h3{font-family:Georgia,serif;font-size:22px}.briefItem p{font-size:14px;line-height:1.55}.briefArchive{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:18px}.briefArchive button{padding:8px;border:1px solid var(--line);background:#fff}.briefArchive button.active{background:#17324a;color:#fff}.mobileNav{display:none}',1)
# Keep the tutorial synchronized with the actual homepage and six-button mobile navigation.
start=s.index('  <h1>Cómo usar CardioUpdate</h1>')
end=s.index('  <div class="manualNote">',start)
manual='''  <h1>Cómo usar CardioUpdate</h1><p class="manualSub">Guía de la actualización diaria y la revista semanal de cardiología</p>
  <p>CardioUpdate combina dos formatos complementarios: un <b>Briefing diario</b> para conocer novedades recientes y una <b>edición científica semanal</b> para revisar con mayor profundidad los estudios seleccionados. Son contenidos diferentes: el briefing puede renovarse cada mañana, mientras que la selección semanal se publica los viernes y permanece estable hasta la siguiente edición.</p>
  <h2>Portada: qué aparece y en qué orden</h2>
  <p>La portada comienza con el <b>trabajo principal de la semana</b> y la composición de la edición; continúa con la selección editorial, las especialidades y las últimas incorporaciones. A continuación aparece el <b>Briefing diario</b>, situado inmediatamente antes de <b>Resto de estudios publicados en la última semana</b>.</p>
  <h2>Briefing diario: cómo utilizarlo</h2>
  <p>Reúne hasta <b>cinco novedades</b> de cardiología, medicina e inteligencia artificial aplicada a la salud. Cada noticia está redactada en tercera persona y se organiza en <b>Qué ocurrió</b>, <b>Por qué es relevante</b> e <b>Implicación práctica</b>. El enlace <b>Fuente original ↗</b> permite consultar la publicación de origen.</p>
  <p>Los botones con fechas permiten consultar el <b>archivo de los últimos siete briefings disponibles</b>. La fecha de cada briefing indica a qué actualización corresponde; si la generación automática falla o no encuentra material verificable, puede mantenerse una edición anterior. El briefing informa novedades: <b>no reemplaza</b> la evaluación metodológica del artículo ni la selección semanal.</p>
  <h2>Menú inferior del teléfono</h2>
  <p>El menú conserva seis accesos. El briefing se lee directamente en <b>Portada</b>; no se agregó un séptimo botón.</p>
  <div class="manualMenu">
   <div><b>⌂ Portada</b>Trabajo principal, selección editorial, especialidades, últimas incorporaciones, briefing diario y bibliografía adicional.</div>
   <div><b>▤ Semana</b>Selección científica vigente, con filtros para recorrer los estudios de la edición.</div>
   <div><b>▦ Temas</b>Acceso por especialidad, incluida cardiología congénita (CONG).</div>
   <div><b>§ Guías</b>Biblioteca de guías y consensos, conservada independientemente del recambio semanal.</div>
   <div><b>★ Favoritos</b>La estrella guarda estudios en el navegador y dispositivo donde se marca; no implica sincronización entre equipos.</div>
   <div><b>⌕ Buscar</b>Búsqueda por enfermedad, intervención, fármaco, tema o revista; por ejemplo CAC, Lp(a), TAVI o mavacamten.</div>
  </div>
  <h2>Cómo leer un estudio de la edición semanal</h2>
  <p>Al abrir un trabajo se presenta el <b>título original en inglés</b>, seguido del <b>abstract original en inglés</b> cuando está disponible en la fuente, y del <b>análisis CardioUpdate en español</b>. Conviene comprobar los resultados, las cifras, el diseño y las limitaciones directamente en el artículo original.</p>
  <div class="manualSequence">Título original → Abstract original → Análisis CardioUpdate → Fuente</div>
  <h3>Abstract y análisis</h3><p>El abstract conserva el idioma original; no debe confundirse con la interpretación editorial. El análisis explica los aportes, la magnitud de los efectos, las limitaciones y las posibles implicaciones clínicas. Si la fuente no facilita el abstract, corresponde consultar el artículo original y no asumir que está completo.</p>
  <h2>Selección semanal y categorías</h2>
  <p>La edición reúne aproximadamente <b>20–30 trabajos</b> y se renueva los viernes. Las categorías <b>Practice Changer</b>, <b>Relevante</b> y <b>Seguimiento</b> ayudan a organizar la lectura; son criterios editoriales, no una sustitución de la evaluación crítica. Las barras de <b>Esta edición</b> indican la cantidad de trabajos en cada categoría y el número de guías/consensos disponibles.</p>
  <h2>Resto de estudios publicados en la última semana</h2><p>Esta sección, ubicada <b>debajo del briefing diario</b>, contiene bibliografía adicional detectada durante el período que no integra la selección principal. Los títulos enlazan a sus fuentes originales.</p>
  <h2>Actualización y solución de problemas</h2>
  <p>El botón <b>↻ Actualizar</b> recarga la base científica. Si no aparece una nueva edición, comprobá la fecha mostrada y volvé a cargar la página. La publicación depende de que finalicen correctamente la actualización automática y el despliegue del sitio; la instalación de la app no garantiza por sí sola que el contenido ya esté publicado.</p>
  <h2>Rutina sugerida</h2>
  <ol><li>Consultar el <b>Briefing diario</b> en Portada y abrir las fuentes de las novedades de interés.</li><li>Los viernes, revisar <b>Semana</b> y leer los estudios seleccionados.</li><li>Contrastar el abstract en inglés con el análisis en español y con la fuente original.</li><li>Guardar con ★ los trabajos que requieran una lectura posterior.</li><li>Explorar <b>Temas</b>, la biblioteca de <b>Guías</b> y el <b>Resto de estudios</b> según la necesidad clínica.</li></ol>
'''
s=s[:start]+manual+s[end:]
if s!=old:
    p.write_text(s,encoding='utf-8')
    print('Briefing diario y tutorial actualizado.')
else:
    print('Briefing diario y tutorial ya actualizados.')
