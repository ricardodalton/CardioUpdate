#!/usr/bin/env python3
"""Idempotently place the daily briefing on the homepage and update its tutorial."""
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'index.html'
s=p.read_text(encoding='utf-8'); old=s
audio_script='<script src="briefing-audio.js?v=1"></script>'
if audio_script not in s:
    s=s.replace('</head>',audio_script+'\n</head>',1)
audio_style='''<style id="briefingAudioStyles">
.briefAudio{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 20px;padding:14px;background:#f6f1ea;border:1px solid var(--line)}.briefAudio button{font:inherit;font-size:14px;font-weight:700;cursor:pointer;border:1px solid #17324a;border-radius:4px;padding:10px 12px;background:#fff;color:#17324a}.briefAudio button:first-child{background:#17324a;color:#fff}.briefAudio button:disabled{opacity:.45;cursor:default}.briefAudio button:focus-visible{outline:3px solid #d51f32;outline-offset:2px}.briefAudio p{flex-basis:100%;margin:2px 0 0!important;font-size:12px!important;color:#59656e}
</style>'''
if 'id="briefingAudioStyles"' not in s:
    s=s.replace('</head>',audio_style+'\n</head>',1)
go_audio="function go(id){if(id!=='home')window.CardioUpdateBriefingAudio?.stop();"
if go_audio not in s:
    s=s.replace('function go(id){',go_audio,1)
if 'id="briefingHome"' not in s:
    assert '<div id="weeklyRemainder"></div>' in s
    s=s.replace('<div id="weeklyRemainder"></div>', '<div id="briefingHome"></div>\n <div id="weeklyRemainder"></div>',1)
if 'BRIEFINGS=[]' not in s:
    assert 'META={}, CANDIDATES=[];' in s
    s=s.replace('META={}, CANDIDATES=[];', 'META={}, CANDIDATES=[], BRIEFINGS=[];',1)
fetch="fetch('data/briefings.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():([])).catch(()=>([]))"
if fetch not in s:
    needle="fetch('data/weekly_remainder.json'+bust,{cache:'no-store'}).then(r=>r.ok?r.json():([])).catch(()=>([]))"
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
anchor='function renderWeeklyRemainder(){'
fn='''function renderBriefingHome(idx=0){
 const box=document.getElementById('briefingHome');if(!box)return;
 const valid=(BRIEFINGS||[]).filter(x=>Array.isArray(x.items)&&x.items.length);
 if(!valid.length){window.CardioUpdateBriefingAudio?.stop();box.innerHTML=`<div class="ruleTitle"><h2>Briefing diario</h2><span></span><small>Actualización diaria</small></div><div class="empty">El briefing de hoy aún no está disponible.</div>`;return;}
 const b=valid[idx]||valid[0];
 const orderNote=b.selection_policy==='clinical-cardiology-v1' ? (b.selection_mode==='ai' ? '<p>Ordenadas de mayor a menor relevancia clínica, sin cupos fijos por especialidad.</p>' : '<p>Vigilancia bibliográfica automática: orden orientativo, pendiente de valoración clínica.</p>') : '';
 box.innerHTML=`<div class="ruleTitle"><h2>Briefing diario</h2><span></span><small>Cardiología clínica · Hasta 10 novedades</small></div><div class="briefArchive">${valid.map((x,i)=>`<button class="${x===b?'active':''}" onclick="renderBriefingHome(${i})">${esc(x.date)}</button>`).join('')}</div><div class="briefingDay"><h2>${esc(b.date)}</h2><div id="briefingAudio" class="briefAudio" role="group" aria-label="Escuchar el briefing"></div>${orderNote}${b.items.map((x,i)=>`<article class="briefItem"><h3>${i+1}. ${esc(x.title)}</h3><p class="briefingMeta">${[x.specialty,x.journal,x.publication_date].filter(Boolean).map(esc).join(' · ')}</p><p><strong>Hallazgo principal.</strong> ${esc(x.what_happened)}</p><p><strong>Por qué es relevante.</strong> ${esc(x.why_relevant)}</p><p><strong>Implicación práctica.</strong> ${esc(x.practical_implication)}</p><a href="${esc(x.url)}" target="_blank" rel="noopener">Fuente original ↗</a></article>`).join('')}</div>`;
 window.CardioUpdateBriefingAudio?.mount(b);
}
'''
assert anchor in s
if 'function renderBriefingHome(' not in s:
    s=s.replace(anchor,fn+anchor,1)
else:
    start=s.index('function renderBriefingHome(')
    end=s.index(anchor,start)
    s=s[:start]+fn+s[end:]
if '.briefingDay{' not in s:
    assert '.mobileNav{display:none}' in s
    s=s.replace('.mobileNav{display:none}', '.briefingDay{background:#fff;padding:22px 25px;margin-bottom:18px}.briefItem{padding:17px 0;border-top:1px solid var(--line)}.briefItem h3{font-family:Georgia,serif;font-size:22px}.briefItem p{font-size:14px;line-height:1.55}.briefArchive{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:18px}.briefArchive button{padding:8px;border:1px solid var(--line);background:#fff}.briefArchive button.active{background:#17324a;color:#fff}.mobileNav{display:none}',1)
# Keep the tutorial synchronized with the actual homepage and six-button mobile navigation.
start=s.index('  <h1>Cómo usar CardioUpdate</h1>')
end=s.index('  <div class="manualNote">',start)
manual='''  <h1>Cómo usar CardioUpdate</h1><p class="manualSub">Guía de la actualización diaria y la revista semanal de cardiología</p>
  <p>CardioUpdate combina dos formatos complementarios: un <b>Briefing diario</b> para conocer novedades recientes y una <b>edición científica semanal</b> para revisar los abstracts y las fuentes de los estudios seleccionados. Son contenidos diferentes: el briefing puede renovarse cada mañana, mientras que la selección semanal corresponde al ciclo sábado–viernes y se publica al cerrarse el ciclo, a partir del sábado.</p>
  <h2>Portada: qué aparece y en qué orden</h2>
  <p>La portada comienza con el <b>trabajo principal de la semana</b> y la composición de la edición; continúa con la selección editorial, las especialidades y las últimas incorporaciones. A continuación aparece el <b>Briefing diario</b>, situado inmediatamente antes del <b>Resto de estudios detectados en el ciclo sábado–viernes</b>.</p>
  <h2>Briefing diario: cómo utilizarlo</h2>
  <p>El objetivo es reunir <b>diez novedades diarias</b> de las distintas áreas de cardiología: prevención y aterosclerosis, dislipidemias, hipertensión, insuficiencia cardíaca, arritmias, enfermedad coronaria, valvulopatías, miocardiopatías, aorta y enfermedad vascular, circulación pulmonar, pericardio, cardiopatías congénitas del adulto, deporte y cardiooncología. La inteligencia artificial se incluye cuando aporta evidencia cardiovascular clínica pertinente.</p>
  <p>Se buscan publicaciones de los <b>últimos siete días en PubMed y Europe PMC</b>. La preselección automática contempla todas las áreas y la edición con IA las ordena de <b>mayor a menor relevancia clínica</b>, considerando posibles cambios en diagnóstico, tratamiento o pronóstico, diseño y limitaciones, desenlaces importantes para pacientes, magnitud de los resultados y novedad. <b>No hay cupos fijos ni prioridad automática por especialidad</b>. Se publican menos de diez si no hay suficientes novedades pertinentes y se evitan repeticiones dentro del ciclo sábado–viernes. La preselección es orientativa y no equivale a una evaluación metodológica formal.</p>
  <p>Cada noticia muestra su área, revista y fecha cuando están disponibles, y se organiza en <b>Hallazgo principal</b>, <b>Por qué es relevante</b> e <b>Implicación práctica</b>. El enlace <b>Fuente original ↗</b> permite consultar la publicación. Si no se obtiene una edición válida con IA, se identifica como <b>vigilancia bibliográfica automática</b>, pendiente de valoración clínica.</p>
  <p>El botón <b>Escuchar briefing</b> lee la edición seleccionada en español, en el mismo orden que aparece en pantalla. <b>Pausar</b>, <b>Continuar</b> y <b>Detener</b> permiten controlar la lectura. Al cambiar de fecha o salir de Portada se detiene el audio. Se utiliza una voz disponible en el dispositivo; su disponibilidad y funcionamiento en segundo plano dependen del navegador.</p>
  <p>Los botones con fechas permiten consultar el <b>archivo de los últimos siete briefings disponibles</b>. La fecha de cada briefing indica a qué actualización corresponde; si la generación automática falla o no encuentra material verificable, puede mantenerse una edición anterior. El briefing informa novedades: <b>no reemplaza</b> la evaluación metodológica del artículo ni la selección semanal.</p>
  <h2>Menú inferior del teléfono</h2>
  <p>El menú conserva seis accesos. El briefing se lee directamente en <b>Portada</b>; no se agregó un séptimo botón.</p>
  <div class="manualMenu">
   <div><b>⌂ Portada</b>Trabajo principal, selección editorial, especialidades, últimas incorporaciones, briefing diario y bibliografía adicional.</div>
   <div><b>▤ Semana</b>Selección científica vigente, con filtros para recorrer los estudios de la edición.</div>
   <div><b>▦ Temas</b>Acceso por el nombre completo de cada especialidad, incluida cardiología congénita.</div>
   <div><b>§ Guías</b>Biblioteca de guías y consensos, conservada independientemente del recambio semanal.</div>
   <div><b>★ Favoritos</b>La estrella guarda estudios en el navegador y dispositivo donde se marca; no implica sincronización entre equipos.</div>
   <div><b>⌕ Buscar</b>Búsqueda por enfermedad, intervención, fármaco, tema o revista; por ejemplo CAC, Lp(a), TAVI o mavacamten.</div>
  </div>
  <h2>Cómo leer un estudio de la edición semanal</h2>
  <p>Al abrir un trabajo se presenta el <b>título original en inglés</b>, seguido del <b>abstract original en inglés</b> cuando está disponible y del enlace al <b>artículo original</b>. Los artículos no generan ni muestran un análisis individual con IA; la IA queda reservada al briefing diario. Conviene comprobar los resultados, las cifras, el diseño y las limitaciones directamente en el artículo original.</p>
  <div class="manualSequence">Título original → Abstract original → Fuente</div>
  <h3>Abstract y fuente original</h3><p>El abstract conserva el idioma de la fuente. Si no está disponible, corresponde abrir el artículo original. Las traducciones locales de los abstracts no utilizan OpenAI y no son un análisis del estudio.</p>
  <h2>Selección semanal y categorías</h2>
  <p>La edición reúne hasta <b>30 trabajos</b> del ciclo sábado–viernes y se renueva a partir del sábado. Las categorías <b>Practice Changer</b>, <b>Relevante</b> y <b>Seguimiento</b> ayudan a organizar la lectura; son criterios editoriales, no una sustitución de la evaluación crítica. Las barras de <b>Esta edición</b> indican la cantidad de trabajos en cada categoría y el número de guías/consensos disponibles.</p>
  <h2>Resto de estudios detectados en el ciclo sábado–viernes</h2><p>Esta sección, ubicada <b>debajo del briefing diario</b>, contiene bibliografía adicional detectada durante el período que no integra la selección principal. Los títulos enlazan a sus fuentes originales.</p>
  <h2>Actualización y solución de problemas</h2>
  <p>El botón <b>↻ Actualizar</b> recarga la base científica. Si no aparece una nueva edición, comprobá la fecha mostrada y volvé a cargar la página. La publicación depende de que finalicen correctamente la actualización automática y el despliegue del sitio; la instalación de la app no garantiza por sí sola que el contenido ya esté publicado.</p>
  <h2>Rutina sugerida</h2>
  <ol><li>Consultar el <b>Briefing diario</b> en Portada y abrir las fuentes de las novedades de interés.</li><li>Al renovarse la edición, revisar <b>Semana</b> y leer los estudios seleccionados.</li><li>Contrastar el abstract con el artículo original.</li><li>Guardar con ★ los trabajos que requieran una lectura posterior.</li><li>Explorar <b>Temas</b>, la biblioteca de <b>Guías</b> y el <b>Resto de estudios</b> según la necesidad clínica.</li></ol>
'''
s=s[:start]+manual+s[end:]
if s!=old:
    p.write_text(s,encoding='utf-8')
    print('Briefing diario y tutorial actualizado.')
else:
    print('Briefing diario y tutorial ya actualizados.')


