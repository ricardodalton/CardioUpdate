#!/usr/bin/env python3
"""Generate up to ten clinically ranked cardiology news items per day."""
from __future__ import annotations
import json, os, re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'briefings.json'
EPMC='https://www.ebi.ac.uk/europepmc/webservices/rest/search'
EUTILS='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
MODEL=os.getenv('CARDIOUPDATE_AI_MODEL','gpt-5.6-terra')
HEADERS={'User-Agent':'CardioUpdate/1.0 (academic cardiovascular literature briefing)'}

TARGET_ITEMS=10
MAX_AI_CANDIDATES=60
SELECTION_POLICY='clinical-cardiology-v1'
# Independent searches give every area access to the editorial shortlist.
# These are retrieval lanes, not publication quotas or specialty bonuses.
SEARCH_DOMAINS=[
 ('Prevención cardiovascular y aterosclerosis',
  'coronary artery calcium OR CAC score OR carotid plaque OR femoral plaque OR atherosclerosis burden OR subclinical atherosclerosis OR cardiovascular prevention'),
 ('Dislipidemias',
  'LDL cholesterol OR cumulative LDL exposure OR apoB OR apolipoprotein B OR lipoprotein(a) OR Lp(a) OR lipid lowering therapy'),
 ('Hipertensión arterial', 'hypertension OR blood pressure treatment OR blood pressure monitoring'),
 ('Insuficiencia cardíaca', 'heart failure OR HFpEF OR HFrEF OR cardiogenic shock'),
 ('Arritmias y electrofisiología',
  'atrial fibrillation OR ventricular arrhythmia OR cardiac ablation OR pacemaker OR implantable cardioverter defibrillator'),
 ('Enfermedad coronaria',
  'acute coronary syndrome OR myocardial infarction OR coronary revascularization OR percutaneous coronary intervention OR coronary artery bypass'),
 ('Valvulopatías',
  'aortic stenosis OR mitral regurgitation OR tricuspid regurgitation OR transcatheter valve OR heart valve disease'),
 ('Miocardiopatías y miocarditis',
  'hypertrophic cardiomyopathy OR dilated cardiomyopathy OR cardiac amyloidosis OR myocarditis'),
 ('Aorta y enfermedad vascular periférica',
  'aortic aneurysm OR aortic dissection OR peripheral artery disease OR peripheral arterial disease'),
 ('Circulación pulmonar y pericardio',
  'pulmonary hypertension OR pulmonary embolism OR pericarditis OR pericardial disease'),
 ('Cardiopatías congénitas del adulto y cardiología del deporte',
  'adult congenital heart disease OR sports cardiology OR athlete sudden cardiac death'),
 ('Cardiooncología', 'cardio-oncology OR cancer therapy cardiotoxicity'),
 ('Inteligencia artificial en cardiología',
  'artificial intelligence AND (cardiology OR cardiovascular imaging OR cardiovascular outcomes)'),
]
QUERIES=[query for _,query in SEARCH_DOMAINS]
SPECIALTIES={name for name,_ in SEARCH_DOMAINS}
CARDIO_PATTERN=re.compile(
 r'cardia|cardio|coronary|heart|atrial|ventric|arrhyth|hypertens|blood pressure|'
 r'atherosclero|carotid|femoral|cholesterol|lipid|lipoprotein|apob|apolipoprotein|'
 r'lp\(a\)|valv|aortic|aorta|mitral|tricuspid|pacemaker|pericardi|'
 r'pulmonary embol|pulmonary hypertens|peripheral arter|hfpef|hfref', re.I)

def clean(value):
    return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',str(value or ''))).strip()

def journal_name(x):
    # Europe PMC core records nest the journal under journalInfo.journal;
    # PubMed records normalized below already expose journalTitle.
    journal=(x.get('journalInfo') or {}).get('journal') or {}
    return clean(x.get('journalTitle') or journal.get('title') or journal.get('isoAbbreviation'))

def epmc_search(q):
    start=(date.today()-timedelta(days=6)).isoformat(); end=date.today().isoformat()
    r=requests.get(EPMC,params={'query':f'FIRST_PDATE:[{start} TO {end}] AND ({q}) sort_date:y',
        'format':'json','resultType':'core','pageSize':'35'},timeout=60,headers=HEADERS)
    r.raise_for_status()
    return (r.json().get('resultList') or {}).get('result') or []

def pubmed_search(q):
    # Independent NCBI E-utilities retrieval, not a PubMed link generated from Europe PMC.
    term=f'({q}) AND ("last 7 days"[dp])'
    params={'db':'pubmed','term':term,'retmax':'35','retmode':'json','sort':'pub date'}
    if os.getenv('NCBI_API_KEY'):params['api_key']=os.environ['NCBI_API_KEY']
    r=requests.get(EUTILS+'esearch.fcgi',params=params,timeout=45,headers=HEADERS)
    r.raise_for_status(); ids=r.json().get('esearchresult',{}).get('idlist',[])
    if not ids:return []
    params={'db':'pubmed','id':','.join(ids),'retmode':'xml'}
    if os.getenv('NCBI_API_KEY'):params['api_key']=os.environ['NCBI_API_KEY']
    r=requests.get(EUTILS+'efetch.fcgi',params=params,timeout=60,headers=HEADERS)
    r.raise_for_status(); root=ET.fromstring(r.content); out=[]
    for article in root.findall('.//PubmedArticle'):
        pmid=clean(''.join(article.findtext('./MedlineCitation/PMID') or ''))
        title=clean(''.join(article.find('./MedlineCitation/Article/ArticleTitle').itertext())) if article.find('./MedlineCitation/Article/ArticleTitle') is not None else ''
        abstract=' '.join(clean(''.join(node.itertext())) for node in article.findall('./MedlineCitation/Article/Abstract/AbstractText'))
        journal=clean(article.findtext('./MedlineCitation/Article/Journal/Title'))
        doi=''
        for identifier in article.findall('./PubmedData/ArticleIdList/ArticleId'):
            if identifier.get('IdType')=='doi':doi=clean(identifier.text);break
        pubdate=article.find('./MedlineCitation/Article/ArticleDate')
        if pubdate is None:pubdate=article.find('./MedlineCitation/Article/Journal/JournalIssue/PubDate')
        year=pubdate.findtext('Year') if pubdate is not None else None
        month=pubdate.findtext('Month') if pubdate is not None else None
        day=pubdate.findtext('Day') if pubdate is not None else None
        publication='-'.join([year,month.zfill(2),day.zfill(2)]) if year and month and day and month.isdigit() else (year or '')
        pubtypes=[clean(node.text) for node in article.findall('./MedlineCitation/Article/PublicationTypeList/PublicationType')]
        if pmid and title:out.append({'pmid':pmid,'doi':doi,'title':title,'abstractText':abstract,
            'journalTitle':journal,'firstPublicationDate':publication,'source_database':'PubMed',
            'pubTypeList':{'pubType':pubtypes}})
    return out

def key(x):
    return (clean(x.get('doi')) or clean(x.get('pmid')) or clean(x.get('title'))).lower()

def url(x):
    if x.get('doi'):return 'https://doi.org/'+str(x['doi'])
    if x.get('pmid'):return 'https://pubmed.ncbi.nlm.nih.gov/'+str(x['pmid'])+'/'
    if x.get('id') and x.get('source'):
        return 'https://europepmc.org/article/'+str(x['source'])+'/'+str(x['id'])
    return ''

def publication_types(x):
    values=(x.get('pubTypeList') or {}).get('pubType') or []
    if isinstance(values,str):values=[values]
    return ' '.join(clean(value) for value in values).lower()

def eligible_source(x):
    title=clean(x.get('title')); text=title+' '+clean(x.get('abstractText'))
    if not title or not url(x) or not CARDIO_PATTERN.search(text):return False
    if re.search(r'case reports?|editorial|comment',publication_types(x)):return False
    # Do not fill the clinical briefing with pediatric or preclinical studies.
    if re.search(r'\b(mice|mouse|rats?|murine|porcine|in vitro|pediatric|paediatric|children|neonatal|infants?)\b',title,re.I) and not re.search(r'\badults?\b',title,re.I):
        return False
    publication=clean(x.get('firstPublicationDate'))[:10]
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',publication):
        try:published=date.fromisoformat(publication)
        except ValueError:return False
        if not date.today()-timedelta(days=6)<=published<=date.today():return False
    return True

def score(x):
    """Screening heuristic, not a validated methodological quality score.

    Publication types and title-level design signals outrank topic frequency.
    Every cardiology specialty uses exactly the same scoring rules.
    """
    title=clean(x.get('title')).lower()
    design=publication_types(x)+' '+title
    text=title+' '+clean(x.get('abstractText')).lower()
    if re.search(r'guideline|practice guideline',design):s=40
    elif re.search(r'meta.analysis|systematic review',design):s=35
    elif ('randomized controlled trial' in publication_types(x) or
          (not re.search(r'non.?randomi[sz]ed',title) and re.search(r'randomi[sz]ed.*trial',title))):s=45
    elif re.search(r'clinical trial|controlled clinical trial',design):s=30
    elif re.search(r'prospective|cohort|registry|registries',design):s=20
    elif re.search(r'retrospective|observational',design):s=12
    elif re.search(r'consensus|scientific statement',design):s=10
    elif re.search(r'\breview\b',design):s=2
    else:s=5
    if re.search(r'mortality|hospitali[sz]ation|clinical outcomes|cardiovascular events|major adverse|quality of life|functional capacity',text):s+=10
    if x.get('abstractText'):s+=4
    return s

def shortlist(pool,limit=MAX_AI_CANDIDATES):
    """Let each area compete before filling remaining places by global rank."""
    ranked=sorted(pool,key=lambda x:(score(x),clean(x.get('firstPublicationDate'))),reverse=True)
    chosen={}
    for specialty,_ in SEARCH_DOMAINS:
        matches=[x for x in ranked if specialty in x.get('search_domains',[])]
        for x in matches[:3]:chosen.setdefault(key(x),x)
    # The per-area allowance protects retrieval coverage, not the final ten.
    for x in ranked:
        if len(chosen)>=limit:break
        chosen.setdefault(key(x),x)
    return sorted(chosen.values(),key=lambda x:(score(x),clean(x.get('firstPublicationDate'))),reverse=True)[:limit]

def source_specialty(x, suggested=''):
    if suggested in SPECIALTIES:return suggested
    return next((s for s in x.get('search_domains',[]) if s in SPECIALTIES),'Cardiología clínica')

def parsed_ai_items(data, pool):
    if not isinstance(data,dict) or not isinstance(data.get('items'),list):return []
    out=[];seen=set()
    for z in data.get('items',[]):
        if not isinstance(z,dict):continue
        try:
            source_n=z.get('source_n')
            if isinstance(source_n,bool) or not re.fullmatch(r'\d+',str(source_n)):continue
            i=int(source_n)
            if i<0:continue
            x=pool[i]
        except (TypeError,ValueError,IndexError):continue
        link=url(x)
        if not link or key(x) in seen:continue
        fields=('title','what_happened','why_relevant','practical_implication')
        if not all(clean(z.get(field)) for field in fields):continue
        seen.add(key(x))
        out.append({'title':clean(z.get('title')),'what_happened':clean(z.get('what_happened')),
            'why_relevant':clean(z.get('why_relevant')),'practical_implication':clean(z.get('practical_implication')),
            'source_title':clean(x.get('title')),'journal':journal_name(x),
            'source_database':x.get('source_database','Europe PMC'),'url':link,
            'specialty':source_specialty(x,clean(z.get('specialty'))),
            'publication_date':clean(x.get('firstPublicationDate'))})
        if len(out)==TARGET_ITEMS:break
    return out

def ai_items(pool):
    from openai import OpenAI
    client=OpenAI(); evidence=[]
    candidates=pool[:MAX_AI_CANDIDATES]
    for i,x in enumerate(candidates):
        evidence.append({'n':i,'title':clean(x.get('title')),'journal':journal_name(x),
            'date':x.get('firstPublicationDate',''),'database':x.get('source_database','Europe PMC'),
            'specialties':x.get('search_domains',[]),'publication_types':publication_types(x),
            'abstract':clean(x.get('abstractText'))[:3500]})
    prompt=f'''Actúa como editor científico de CardioUpdate para cardiólogos clínicos de adultos.
Selecciona {TARGET_ITEMS} novedades científicas verificables cuando haya suficientes publicaciones pertinentes. Devuelve menos si no las hay; nunca rellenes con material débil, repetido o ajeno a la práctica cardiovascular.
Cubre TODAS las áreas de cardiología disponibles en EVIDENCIA: prevención y aterosclerosis, lípidos, hipertensión, insuficiencia cardíaca, arritmias, coronaria, valvulopatías, miocardiopatías, aorta y enfermedad vascular, circulación pulmonar, pericardio, congénitas del adulto, deporte y cardiooncología. IA solo cuando tenga relevancia cardiovascular clínica demostrable.
ORDENA de mayor a menor RELEVANCIA CLÍNICA: primero potencial de modificar diagnóstico, tratamiento o pronóstico; después solidez del diseño y limitaciones que realmente puedan verificarse en el resumen, desenlaces relevantes para pacientes (mortalidad, hospitalización, síntomas o calidad de vida), magnitud y precisión de los efectos, y novedad respecto al conocimiento previo cuando esté documentada. No inventes comparaciones con estudios ausentes.
Ninguna especialidad tiene bonificación automática: prevención NO debe desplazar a un estudio más relevante de otra área. No hay cupos fijos por especialidad; con mérito similar, favorece diversidad temática. No uses la frecuencia de palabras clave, el orden de EVIDENCIA ni el prestigio de la revista como sustitutos de la valoración crítica. Un ensayo aleatorizado no es automáticamente superior a cualquier estudio de otro diseño.
No presentes biomarcadores o resultados sustitutos como beneficio clínico demostrado, asociaciones como causalidad, ni significación estadística como relevancia clínica. Explica en why_relevant qué justifica la prioridad y qué limita la interpretación. Excluye casos aislados, estudios puramente animales, pediátricos o sin relación cardiovascular directa. No confundas indexación con publicación ni repitas el mismo ensayo mediante publicaciones secundarias sin un hallazgo independiente importante.
Redacta TODO en español y EN TERCERA PERSONA. Para cada noticia devuelve title, what_happened, why_relevant, practical_implication, specialty y source_n. specialty debe ser uno de estos nombres completos: {json.dumps([name for name,_ in SEARCH_DOMAINS],ensure_ascii=False)}.
source_n debe ser exactamente uno de los enteros provistos en EVIDENCIA. Usa exclusivamente los títulos, resúmenes y metadatos proporcionados; explicita cuando el resumen no permite evaluar un aspecto. No inventes datos, cifras, conclusiones ni fuentes. No repitas artículos. Devuelve JSON puro con clave items, ya ordenados por relevancia.'''
    for attempt in range(2):
        retry='\nReparación: la respuesta anterior no produjo noticias válidas. Devuelve items completos con source_n válido, hasta diez sin rellenar el cupo.' if attempt else ''
        try:
            resp=client.responses.create(model=MODEL,input=prompt+retry+'\nEVIDENCIA:\n'+json.dumps(evidence,ensure_ascii=False),
                text={'format':{'type':'json_object'}})
            out=parsed_ai_items(json.loads(resp.output_text),candidates)
        except Exception as exc:
            print(f'Intento de edición por IA {attempt+1} falló: {type(exc).__name__}')
            out=[]
        if out:return out
    return out

def fallback_items(pool, limit=TARGET_ITEMS):
    """Publish a conservative metadata-only watchlist if AI output is unusable."""
    out=[];seen=set()
    for x in pool:
        link=url(x)
        if not link or key(x) in seen:continue
        title=clean(x.get('title'))
        journal=journal_name(x) or 'la fuente indexada'
        if not title:continue
        seen.add(key(x))
        out.append({
            'title':title,
            'what_happened':f'Se detectó una publicación reciente en {journal} durante la vigilancia bibliográfica diaria de CardioUpdate.',
            'why_relevant':'El trabajo coincide con las áreas cardiológicas priorizadas. Esta incorporación automática confirma su disponibilidad, pero no sustituye la evaluación del diseño, los resultados ni las limitaciones.',
            'practical_implication':'Conviene revisar la fuente original antes de modificar conductas clínicas. Se presenta como señal bibliográfica para lectura y no como recomendación terapéutica.',
            'source_title':title,'journal':journal_name(x),
            'source_database':x.get('source_database','Europe PMC'),'url':link,
            'specialty':source_specialty(x),'publication_date':clean(x.get('firstPublicationDate'))})
        if len(out)>=limit:break
    return out

def main():
    found={}; failures=[]
    for specialty,q in SEARCH_DOMAINS:
        for name,fn in [('PubMed',pubmed_search),('Europe PMC',epmc_search)]:
            try:results=fn(q)
            except (requests.RequestException,ValueError,ET.ParseError) as exc:
                failures.append(f'{name}: {type(exc).__name__}');continue
            for x in results:
                if not key(x):continue
                x.setdefault('source_database',name)
                k=key(x); previous=found.get(k)
                domains=list(dict.fromkeys((previous or {}).get('search_domains',[])+[specialty]))
                if previous is None or (not previous.get('abstractText') and x.get('abstractText')):
                    found[k]=x
                found[k]['search_domains']=domains
    if not found:
        print('No se pudo recuperar evidencia de PubMed ni Europe PMC; se conserva el briefing anterior. '
              + ', '.join(failures))
        return
    try:hist=json.loads(OUT.read_text(encoding='utf-8'))
    except (OSError,ValueError):hist=[]
    today_obj=date.today(); today=today_obj.isoformat()
    # Do not recycle sources already shown in the active Saturday-Friday cycle.
    days_since_saturday=(today_obj.weekday()-5)%7
    week_start=today_obj-timedelta(days=days_since_saturday)
    hist=[x for x in hist if x.get('date')!=today and x.get('date','')>=week_start.isoformat() and x.get('date','')<=today]
    used_urls={clean(item.get('url')) for edition in hist for item in edition.get('items',[]) if item.get('url')}
    pool=shortlist([x for x in found.values() if eligible_source(x) and url(x) not in used_urls])
    if not pool:
        print('No existen fuentes cardiológicas nuevas y elegibles: se conserva el briefing anterior.')
        return
    items=ai_items(pool) if os.getenv('OPENAI_API_KEY') else []
    selection_mode='ai'
    if not items:
        items=fallback_items(pool)
        selection_mode='bibliographic_fallback'
        print(f'La IA no generó noticias válidas; se publica una vigilancia bibliográfica conservadora de {len(items)} fuentes.')
    if not items:
        print('No existen fuentes nuevas con enlace válido: se conserva el briefing anterior.')
        return
    hist.insert(0,{'date':today,'generated_at':datetime.now(timezone.utc).isoformat(),'items':items,
        'target_items':TARGET_ITEMS,'selection_policy':SELECTION_POLICY,'selection_mode':selection_mode})
    hist.sort(key=lambda x:x.get('date',''),reverse=True)
    OUT.write_text(json.dumps(hist,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'CardioUpdate briefing {today}: {len(items)} noticias; {len(found)} referencias; PubMed y Europe PMC; {len(failures)} fallos de búsqueda.')
if __name__=='__main__':main()

