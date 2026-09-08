# CardioUpdate FINAL AUTO

Esta versión separa completamente la interfaz de la evidencia.

## Cómo funciona
- `index.html`: interfaz fija.
- `data/studies.json`: base de estudios.
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

No requiere clave de OpenAI ni servicio de traducción pago.

## Actualización manual de prueba
`python scripts/update_studies.py`
Luego `python tests/test_database.py`.

## Seguridad editorial
La importación diaria es automática y sirve para vigilancia científica. La etiqueta “Practice Changer” queda reservada a entradas revisadas editorialmente. Las traducciones automáticas deben contrastarse con el original antes de decisiones clínicas.
