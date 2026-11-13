# CardioUpdate FINAL AUTO

Esta versión separa completamente la interfaz de la evidencia.

## Cómo funciona
- `index.html`: interfaz fija.
- `data/studies.json`: base de estudios.
- `data/candidates.json`: pool técnico de candidatos para la selección del viernes.
- `data/weekly_remainder.json`: bibliografía liviana del ciclo sábado–viernes que consume la interfaz.
- `data/guides.json`: guías.
- `data/areas.json`: áreas.
- `scripts/update_studies.py`: búsqueda diaria en Europe PMC.
- `.github/workflows/daily-update.yml`: ejecución automática todos los días a las 06:35 (America/Argentina/Buenos_Aires).
- La traducción del abstract al español se realiza en el proceso automático con `Helsinki-NLP/opus-mt-en-es`.
- Los trabajos automáticos quedan marcados `Revisión pendiente`; no se les asigna automáticamente la categoría Practice Changer.

## Despliegue automático definitivo
Para que Netlify se actualice solo sin volver a subir ZIP:
1. Cree/usar un repositorio GitHub y copie allí TODO el contenido de esta carpeta.
2. En Netlify, conecte el sitio a ese repositorio (Deploy from Git).
3. Publicación: raíz del repositorio; no necesita comando de build.
4. GitHub Actions actualizará `data/studies.json` cada mañana; el commit disparará automáticamente un nuevo deploy de Netlify.

La búsqueda y la traducción de abstracts no requieren OpenAI. El briefing diario sí utiliza `OPENAI_API_KEY`; no se reactiva el análisis individual de los estudios.

## Briefing diario de cardiología clínica
- Objetivo: diez novedades por día; menos si no hay suficientes fuentes nuevas y pertinentes, sin completar el cupo con material débil.
- Búsquedas independientes de los últimos siete días en PubMed y Europe PMC para prevención/aterosclerosis, lípidos, hipertensión, insuficiencia cardíaca, arritmias, coronaria, valvulopatías, miocardiopatías, aorta/vascular, circulación pulmonar/pericardio, congénitas del adulto/deporte, cardiooncología e IA cardiovascular clínica.
- Se conservan los tipos de publicación. La preselección usa las mismas reglas de diseño y desenlaces para todas las áreas; no suma puntos por palabras de prevención ni por base de datos. Es un filtro bibliográfico, no un score validado de calidad metodológica.
- Hasta tres candidatos por área tienen acceso a la preselección; los demás lugares se completan por puntuación global hasta un máximo de 60 referencias. Esto protege la cobertura de la búsqueda y no impone cupos a las noticias publicadas.
- La IA selecciona y ordena de mayor a menor relevancia clínica: potencial de cambiar diagnóstico/tratamiento/pronóstico, diseño y limitaciones verificables, desenlaces para pacientes, magnitud/precisión y novedad documentada. Con mérito similar se favorece diversidad; ninguna especialidad tiene prioridad automática.
- Solo se aceptan referencias incluidas en la evidencia enviada a la IA. Se verifican índices, campos y duplicados; no se reciclan enlaces ya publicados en el ciclo sábado–viernes.
- La interfaz conserva el orden editorial y muestra área, revista, fecha y fuente original. La vigilancia de respaldo sin IA se identifica explícitamente y no se presenta como valoración clínica completa.

## Actualización manual de prueba
`python scripts/update_studies.py`
Luego `python tests/test_database.py`.

## Seguridad editorial
La importación diaria es automática y sirve para vigilancia científica. La etiqueta “Practice Changer” queda reservada a entradas revisadas editorialmente. Las traducciones automáticas deben contrastarse con el original antes de decisiones clínicas.

