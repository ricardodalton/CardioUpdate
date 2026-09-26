#!/usr/bin/env python3
"""Generate a prevention-first seven-edition briefing using PubMed and Europe PMC."""
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

# Search each prevention domain independently so broad cardiology/AI cannot crowd it out.
QUERIES=[
 'coronary artery calcium OR CAC score OR coronary calcification OR subclinical atherosclerosis',
 'carotid plaque OR femoral plaque OR carotid ultrasound OR femoral ultrasound OR atherosclerosis burden',
 'LDL cholesterol OR cumulative LDL exposure OR apoB OR apolipoprotein B OR lipoprotein(a) OR Lp(a) OR dyslipidemia',
 'hypertension OR blood pressure OR coronary prevention OR cardiovascular prevention',
 'randomized cardiovascular prevention trial OR cardiovascular prevention guideline OR lipid lowering therapy',
 'artificial intelligence AND (cardiovascular prevention OR cardiovascular imaging OR clinical medicine)',
]
PREVENTION_TERMS=[
 ('coronary artery calcium',12),('cac score',12),('coronary calcification',10),
 ('carotid plaque',12),('femoral plaque',12),('carotid ultrasound',10),('femoral ultrasound',10),
 ('atherosclerosis burden',12),('subclinical atherosclerosis',11),('cumulative ldl',12),
 ('ldl cholesterol',9),('lipoprotein(a)',12),('lp(a)',12),('apolipoprotein b',10),
 ('apob',10),('dyslipidemia',8),('hypertension',9),('blood pressure',7),
 ('coronary prevention',11),('cardiovascular prevention',10),('primary prevention',10),
 ('secondary prevention',9),('lipid lowering',8),('atherosclerosis',6),
]

def clean(value):
    return re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',str(value or ''))).strip()

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
        if pmid and title:out.append({'pmid':pmid,'doi':doi,'title':title,'abstractText':abstract,
            'journalTitle':journal,'firstPublicationDate':publication,'source_database':'PubMed'})
    return out

def key(x):
    return (clean(x.get('doi')) or clean(x.get('pmid')) or clean(x.get('title'))).lower()

def url(x):
    if x.get('doi'):return 'https://doi.org/'+str(x['doi'])
    if x.get('pmid'):return 'https://pubmed.ncbi.nlm.nih.gov/'+str(x['pmid'])+'/'
    if x.get('id') and x.get('source'):
        return 'https://europepmc.org/article/'+str(x['source'])+'/'+str(x['id'])
    return ''

def score(x):
    text=(clean(x.get('title'))+' '+clean(x.get('abstractText'))).lower()
    title=clean(x.get('title')).lower()
    s=3 if x.get('abstractText') else 0
    for term,weight in PREVENTION_TERMS:
        if term in text:s+=weight+(weight//2 if term in title else 0)
    for term,weight in [('randomized',6),('trial',4),('guideline',6),('consensus',5),
                        ('meta-analysis',4),('mortality',3),('clinical outcomes',4)]:
        if term in text:s+=weight
    if x.get('source_database')=='PubMed':s+=2
    return s

def ai_items(pool):
    from openai import OpenAI
    client=OpenAI(); evidence=[]
    for i,x in enumerate(pool[:35]):
        evidence.append({'n':i,'title':clean(x.get('title')),'journal':x.get('journalTitle',''),
            'date':x.get('firstPublicationDate',''),'database':x.get('source_database','Europe PMC'),
            'abstract':clean(x.get('abstractText'))[:3500]})
    prompt='''Actúa como editor científico de CardioUpdate para cardiólogos. Selecciona hasta 5 novedades científicas verificables y clínicamente importantes, dando prioridad explícita a PREVENCIÓN CARDIOVASCULAR: carga aterosclerótica por CAC e imágenes carotídeas/femorales, LDL y exposición acumulada, apoB, Lp(a), dislipidemias, hipertensión y prevención coronaria primaria/secundaria. Prioriza ensayos clínicos, metaanálisis rigurosos, guías y resultados clínicos frente a hipótesis y biomarcadores. IA médica y cardiología general solo si aportan un avance excepcional; no rellenes con noticias irrelevantes. No confundas fecha de indexación con publicación ni presentes revisiones antiguas como novedades. Redacta TODO en español y EN TERCERA PERSONA. Para cada noticia devuelve title, what_happened, why_relevant, practical_implication y source_n. Distingue evidencia observacional de causal y resultados sustitutos de eventos clínicos. No inventes datos, cifras, conclusiones ni fuentes ausentes. No repitas artículos. Devuelve JSON puro con clave items.'''
    resp=client.responses.create(model=MODEL,input=prompt+'\nEVIDENCIA:\n'+json.dumps(evidence,ensure_ascii=False),
        text={'format':{'type':'json_object'}})
    data=json.loads(resp.output_text);out=[];seen=set()
    for z in data.get('items',[]):
        try:i=int(z.get('source_n'));x=pool[i]
        except (TypeError,ValueError,IndexError):continue
        link=url(x)
        if not link or key(x) in seen:continue
        seen.add(key(x))
        out.append({'title':z.get('title',''),'what_happened':z.get('what_happened',''),
            'why_relevant':z.get('why_relevant',''),'practical_implication':z.get('practical_implication',''),
            'source_title':clean(x.get('title')),'journal':x.get('journalTitle',''),
            'source_database':x.get('source_database','Europe PMC'),'url':link})
        if len(out)==5:break
    return out

def main():
    found={}; failures=[]
    for q in QUERIES:
        for name,fn in [('PubMed',pubmed_search),('Europe PMC',epmc_search)]:
            try:results=fn(q)
            except (requests.RequestException,ValueError,ET.ParseError) as exc:
                failures.append(f'{name}: {type(exc).__name__}');continue
            for x in results:
                if not key(x):continue
                x.setdefault('source_database',name)
                k=key(x)
                if k not in found or (not found[k].get('abstractText') and x.get('abstractText')):
                    found[k]=x
    if not found:raise RuntimeError('No se pudo recuperar evidencia de PubMed ni Europe PMC: '+', '.join(failures))
    pool=sorted(found.values(),key=score,reverse=True)
    if not os.getenv('OPENAI_API_KEY'):raise RuntimeError('Falta OPENAI_API_KEY: se conserva el briefing anterior.')
    items=ai_items(pool)
    if not items:raise RuntimeError('No se generaron noticias válidas: se conserva el briefing anterior.')
    try:hist=json.loads(OUT.read_text(encoding='utf-8'))
    except (OSError,ValueError):hist=[]
    today_obj=date.today(); today=today_obj.isoformat()
    # Briefing cycle follows the journal week: Saturday through Friday.
    # On Saturday, prior-week briefings disappear and the new cycle starts at one day.
    days_since_saturday=(today_obj.weekday()-5)%7
    week_start=today_obj-timedelta(days=days_since_saturday)
    hist=[x for x in hist if x.get('date')!=today and x.get('date','')>=week_start.isoformat() and x.get('date','')<=today]
    hist.insert(0,{'date':today,'generated_at':datetime.now(timezone.utc).isoformat(),'items':items})
    hist.sort(key=lambda x:x.get('date',''),reverse=True)
    OUT.write_text(json.dumps(hist,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'CardioUpdate briefing {today}: {len(items)} noticias; {len(found)} referencias; PubMed y Europe PMC; {len(failures)} fallos de búsqueda.')
if __name__=='__main__':main()
