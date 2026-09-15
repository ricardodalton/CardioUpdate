#!/usr/bin/env python3
"""Generate CardioUpdate's rolling 7-day daily briefing from fresh indexed evidence."""
from __future__ import annotations
import json, os, re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'briefings.json'
EPMC='https://www.ebi.ac.uk/europepmc/webservices/rest/search'
MODEL=os.getenv('CARDIOUPDATE_AI_MODEL','gpt-5.6-terra')

QUERIES=[
 'cardiovascular OR cardiac OR coronary OR myocardial OR "heart failure" OR "atrial fibrillation" OR hypertension OR atherosclerosis OR cardiomyopathy OR valvular',
 '"artificial intelligence" AND (cardiology OR cardiovascular OR medicine OR clinical)',
]

def search(q):
    start=(date.today()-timedelta(days=2)).isoformat(); end=date.today().isoformat()
    r=requests.get(EPMC,params={'query':f'FIRST_PDATE:[{start} TO {end}] AND ({q}) sort_date:y','format':'json','resultType':'core','pageSize':'75'},timeout=60,headers={'User-Agent':'CardioUpdate daily briefing'})
    r.raise_for_status(); return (r.json().get('resultList') or {}).get('result') or []

def key(x): return (x.get('doi') or x.get('pmid') or x.get('title') or '').lower().strip()
def url(x):
    if x.get('doi'): return 'https://doi.org/'+x['doi']
    if x.get('pmid'): return 'https://pubmed.ncbi.nlm.nih.gov/'+x['pmid']+'/'
    return 'https://europepmc.org/'
def score(x):
    t=(x.get('title','')+' '+x.get('abstractText','')).lower(); s=3 if x.get('abstractText') else 0
    for term,w in [('randomized',6),('trial',4),('guideline',6),('consensus',5),('meta-analysis',4),('mortality',3),('artificial intelligence',3),('cardiovascular',2)]:
        if term in t:s+=w
    return s

def ai_items(pool):
    from openai import OpenAI
    client=OpenAI()
    evidence=[]
    for i,x in enumerate(pool[:18]):
        evidence.append({'n':i,'title':re.sub('<[^>]+>','',x.get('title','')),'journal':x.get('journalTitle',''),'date':x.get('firstPublicationDate',''),'abstract':re.sub('<[^>]+>',' ',x.get('abstractText',''))[:3500]})
    prompt='''Actúa como editor científico de CardioUpdate. Selecciona exactamente 5 novedades de mayor interés para un cardiólogo clínico. Prioriza cardiología clínica y prevención, estudios/guías, nuevos tratamientos e IA aplicada a medicina. Redacta TODO en español y EN TERCERA PERSONA, nunca dirigiéndote al lector. Para cada noticia devuelve title, what_happened, why_relevant, practical_implication y source_n. No inventes datos, cifras ni conclusiones ausentes. Devuelve JSON puro con clave items.'''
    resp=client.responses.create(model=MODEL,input=prompt+'\nEVIDENCIA:\n'+json.dumps(evidence,ensure_ascii=False),text={'format':{'type':'json_object'}})
    data=json.loads(resp.output_text); out=[]
    for z in data.get('items',[])[:5]:
        try:x=pool[int(z.get('source_n'))]
        except:continue
        out.append({'title':z.get('title',''),'what_happened':z.get('what_happened',''),'why_relevant':z.get('why_relevant',''),'practical_implication':z.get('practical_implication',''),'source_title':re.sub('<[^>]+>','',x.get('title','')),'journal':x.get('journalTitle',''),'url':url(x)})
    return out

def main():
    found={}
    for q in QUERIES:
        for x in search(q):
            if key(x):found[key(x)]=x
    pool=sorted(found.values(),key=score,reverse=True)
    items=ai_items(pool) if os.getenv('OPENAI_API_KEY') and pool else []
    try:hist=json.loads(OUT.read_text(encoding='utf-8'))
    except:hist=[]
    today=date.today().isoformat(); hist=[x for x in hist if x.get('date')!=today]
    hist.insert(0,{'date':today,'generated_at':datetime.now(timezone.utc).isoformat(),'items':items})
    OUT.write_text(json.dumps(hist[:7],ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'CardioUpdate briefing {today}: {len(items)} noticias; archivo conserva {min(len(hist),7)} días.')
if __name__=='__main__':main()
