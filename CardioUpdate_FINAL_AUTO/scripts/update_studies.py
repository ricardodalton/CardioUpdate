#!/usr/bin/env python3
"""
CardioUpdate daily evidence updater.

Sources:
- Europe PMC REST API (publication metadata + indexed abstracts)
- Existing editorial database in data/studies.json

The updater:
1. Searches the last 3 calendar days to absorb indexing delays.
2. Scores cardiology relevance and source quality.
3. Deduplicates by DOI/PMID/title.
4. Translates indexed English abstracts to Spanish locally with MarianMT.
5. Adds a maximum of MAX_NEW_PER_RUN studies per run.
6. Never overwrites editorially reviewed entries.
"""

from __future__ import annotations
import json, os, re, sys, html, time
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
import requests

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "studies.json"
META = ROOT / "data" / "meta.json"
API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MAX_NEW_PER_RUN = int(os.environ.get("CARDIOUPDATE_MAX_NEW", "12"))
TRANSLATE = os.environ.get("CARDIOUPDATE_TRANSLATE", "1") != "0"

JOURNAL_WEIGHTS = {
    "new england journal of medicine": 7, "n engl j med": 7,
    "the lancet": 7, "lancet": 7,
    "jama": 6, "jama cardiology": 6,
    "circulation": 6, "european heart journal": 6,
    "journal of the american college of cardiology": 6, "j am coll cardiol": 6,
    "jacc heart failure": 5, "jacc cardiovascular interventions": 5,
    "jacc clinical electrophysiology": 5, "jacc cardiovascular imaging": 5,
    "heart": 4, "european journal of heart failure": 5,
    "hypertension": 5, "atherosclerosis": 4,
    "stroke": 5, "nature medicine": 6, "nature cardiovascular research": 5,
}

AREA_RULES = [
("Miocardiopatías", r"\b(hypertrophic cardiomyopathy|cardiac myosin|mavacamten|aficamten|amyloid|transthyretin|cardiomyopath)\b"),
("Insuficiencia cardíaca", r"\b(heart failure|hfpef|hfref|hfmrEF|ejection fraction|finerenone|sacubitril|sglt2)\b"),
("Arritmias y electrofisiología", r"\b(atrial fibrillation|ventricular arrhythm|ablation|electrophysiolog|pacemaker|defibrillator|anticoagulation)\b"),
("Valvulopatías", r"\b(aortic stenosis|mitral regurgitation|tricuspid regurgitation|tavi|tavr|transcatheter valve|valvular)\b"),
("Cardiopatía isquémica", r"\b(myocardial infarction|acute coronary|stemi|nstemi|coronary artery|revascularization|pci|antiplatelet)\b"),
("Lípidos y Lp(a)", r"\b(ldl|lipoprotein\(a\)|lp\(a\)|statin|pcsk9|inclisiran|bempedoic|cholesterol|dyslipid)\b"),
("Hipertensión", r"\b(hypertension|blood pressure|renal denervation)\b"),
("Prevención y aterosclerosis", r"\b(prevention|atherosclero|coronary calcium|cac\b|carotid plaque|cardiovascular risk|primary prevention)\b"),
("Patología aórtica", r"\b(aortic aneurysm|aortic dissection|aortopathy|acute aortic)\b"),
("Enfermedad vascular periférica", r"\b(peripheral artery|peripheral arterial|limb ischemia|carotid stenosis)\b"),
("Pericardiopatías", r"\b(pericarditis|pericardial|constrictive pericard)\b"),
]

CARDIO_TERMS = (
    "cardiovascular OR cardiac OR coronary OR myocardial OR heart failure OR "
    "\"atrial fibrillation\" OR hypertension OR atherosclerosis OR valvular OR "
    "cardiomyopathy OR \"peripheral artery\" OR pericarditis OR aortic"
)

def clean_markup(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<\s*(br|/p|/h\d)\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\r", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def classify_area(text: str) -> str:
    t = text.lower()
    for area, pat in AREA_RULES:
        if re.search(pat, t, flags=re.I):
            return area
    return "Prevención y aterosclerosis"

def journal_weight(journal: str) -> int:
    j = norm(journal)
    best = 0
    for k,w in JOURNAL_WEIGHTS.items():
        if k in j:
            best=max(best,w)
    return best

def type_text(item: dict) -> str:
    p = item.get("pubTypeList") or {}
    if isinstance(p, dict):
        vals = p.get("pubType") or []
    else:
        vals = []
    if isinstance(vals, str): vals=[vals]
    return "; ".join(vals)

def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('abstractText','')} {type_text(item)}".lower()
    s = journal_weight(item.get("journalTitle","")) * 3
    if re.search(r"randomized|randomised|clinical trial|controlled trial", text): s += 8
    if re.search(r"meta-analysis|systematic review", text): s += 5
    if re.search(r"guideline|consensus|scientific statement|position statement", text): s += 7
    if re.search(r"phase 3|phase iii", text): s += 4
    if re.search(r"mortality|death|myocardial infarction|stroke|hospitali", text): s += 2
    if item.get("abstractText"): s += 3
    return s

def level(item: dict) -> str:
    # Automated imports never assert "Practice Changer" before human review.
    return "Relevante" if score(item) >= 18 else "Seguimiento"

def split_sentences(text: str, max_chars=1150):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks=[]; cur=""
    for p in parts:
        if not p: continue
        if len(cur)+len(p)+1 <= max_chars:
            cur=(cur+" "+p).strip()
        else:
            if cur: chunks.append(cur)
            cur=p
    if cur: chunks.append(cur)
    return chunks

_TRANSLATOR=None
def translator():
    global _TRANSLATOR
    if _TRANSLATOR is None:
        from transformers import MarianMTModel, MarianTokenizer
        model_name="Helsinki-NLP/opus-mt-en-es"
        tok=MarianTokenizer.from_pretrained(model_name)
        mod=MarianMTModel.from_pretrained(model_name)
        _TRANSLATOR=(tok,mod)
    return _TRANSLATOR

def translate_es(text: str) -> str:
    if not text: return ""
    if not TRANSLATE: return text
    tok,mod=translator()
    out=[]
    for chunk in split_sentences(text):
        batch=tok([chunk], return_tensors="pt", padding=True, truncation=True, max_length=512)
        gen=mod.generate(**batch, max_length=640, num_beams=4)
        out.append(tok.batch_decode(gen, skip_special_tokens=True)[0])
    return " ".join(out).strip()

def structured_abstract_es(abstract: str):
    # Preserve common structured headings when present; otherwise one detailed block.
    a = clean_markup(abstract)
    heading_map = {
        "background":"Antecedentes","objective":"Objetivo","objectives":"Objetivos",
        "methods":"Métodos","method":"Métodos","results":"Resultados",
        "conclusion":"Conclusión","conclusions":"Conclusiones","importance":"Importancia",
        "design":"Diseño","setting":"Ámbito","participants":"Participantes",
        "interventions":"Intervenciones","main outcomes and measures":"Resultados principales"
    }
    # Try heading: text structures.
    pat = re.compile(r"(?im)^(background|objective|objectives|methods?|results|conclusions?|importance|design|setting|participants|interventions|main outcomes and measures)\s*:?\s*$")
    matches=list(pat.finditer(a))
    sections=[]
    if matches:
        for i,m in enumerate(matches):
            key=m.group(1).lower()
            body=a[m.end(): matches[i+1].start() if i+1<len(matches) else len(a)].strip()
            if body:
                sections.append([heading_map.get(key,key.title()), translate_es(body)])
    else:
        sections=[["Abstract", translate_es(a)]]
    return sections

def first_sentences_es(sections, n=2):
    text=" ".join(x[1] for x in sections)
    ss=re.split(r"(?<=[.!?])\s+", text)
    return " ".join(ss[:n]).strip()[:900]

def fetch_recent():
    today = date.today()
    start = today - timedelta(days=3)

    groups = [
        "cardiovascular OR cardiac OR coronary OR myocardial",
        '"heart failure" OR "atrial fibrillation" OR hypertension',
        "atherosclerosis OR valvular OR cardiomyopathy",
        '"peripheral artery" OR pericarditis OR aortic'
    ]

    results = {}

    for terms in groups:
        q = f'FIRST_PDATE:[{start.isoformat()} TO {today.isoformat()}] AND ({terms}) sort_date:y'
        params = {
            "query": q,
            "format": "json",
            "resultType": "core",
            "pageSize": "75"
        }

        for attempt in range(4):
            try:
                r = requests.get(
                    API,
                    params=params,
                    timeout=60,
                    headers={"User-Agent": "CardioUpdate/3.1 evidence updater"}
                )
                r.raise_for_status()

                items = (r.json().get("resultList") or {}).get("result") or []

                for item in items:
                    key = item.get("doi") or item.get("pmid") or item.get("pmcid") or item.get("title")
                    if key:
                        results[str(key).lower()] = item

                break

            except requests.RequestException as e:
                if attempt == 3:
                    print(f"Europe PMC: consulta omitida tras reintentos: {e}")
                else:
                    time.sleep(2 ** attempt)

        time.sleep(1)

     if not results:
        raise RuntimeError("Europe PMC no respondió después de los reintentos.")

    return list(results.values())


def make_id(item):
    base = item.get("doi") or item.get("pmid") or item.get("pmcid") or item.get("title") or "study"
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:110]

def original_url(item):
    if item.get("doi"): return "https://doi.org/"+item["doi"]
    if item.get("pmid"): return "https://pubmed.ncbi.nlm.nih.gov/"+item["pmid"]+"/"
    if item.get("pmcid"): return "https://europepmc.org/article/PMC/"+item["pmcid"]
    return "https://europepmc.org/"

def dedup_key(s):
    if s.get("doi"): return "doi:"+norm(s["doi"])
    if s.get("pmid"): return "pmid:"+norm(s["pmid"])
    return "title:"+norm(s.get("title",""))

def main():
    existing=json.loads(DB.read_text(encoding="utf-8"))
    keys={dedup_key(x) for x in existing}
    raw=fetch_recent()
    candidates=[]
    for x in raw:
        if not x.get("title") or not x.get("abstractText"): continue
        sc=score(x)
        if sc < 12: continue
        candidates.append((sc,x))
    candidates.sort(key=lambda z:z[0], reverse=True)
    added=[]
    for sc,x in candidates:
        if len(added)>=MAX_NEW_PER_RUN: break
        k = ("doi:"+norm(x.get("doi"))) if x.get("doi") else ("pmid:"+norm(x.get("pmid"))) if x.get("pmid") else "title:"+norm(x["title"])
        if k in keys: continue
        abstract_es=structured_abstract_es(x.get("abstractText",""))
        area=classify_area(f"{x.get('title','')} {x.get('abstractText','')}")
        ptypes=type_text(x)
        typ = "Ensayo clínico" if re.search(r"trial|randomized|randomised",ptypes,re.I) else ("Revisión / meta-análisis" if re.search(r"review|meta",ptypes,re.I) else "Artículo científico")
        s={
            "id":make_id(x),
            "title":clean_markup(x["title"]),
            "short":clean_markup(x["title"]),
            "area":area,
            "level":level(x),
            "type":typ,
            "journal":x.get("journalTitle") or x.get("journalInfo",{}).get("journal",{}).get("title",""),
            "date":x.get("firstPublicationDate") or x.get("journalInfo",{}).get("printPublicationDate",""),
            "summary":first_sentences_es(abstract_es),
            "why":f"Trabajo nuevo en {area.lower()} seleccionado automáticamente por fuente, diseño y relevancia temática. Revisión editorial pendiente.",
            "detail":"Consultar el abstract ampliado y el artículo original.",
            "url":original_url(x),
            "doi":x.get("doi",""),
            "pmid":x.get("pmid",""),
            "authors":x.get("authorString",""),
            "abstract_es":abstract_es,
            "limitations_es":"Importación automática. Antes de modificar conducta clínica, revisar el texto completo, metodología, población, endpoints, análisis estadístico y aplicabilidad.",
            "source_mode":"europe_pmc_daily",
            "review_status":"Revisión pendiente",
            "auto_score":sc,
            "imported_at":datetime.now(timezone.utc).isoformat()
        }
        existing.append(s); added.append(s); keys.add(k)

    # Keep all editorial items + last 365 days of automatic items.
    cutoff=date.today()-timedelta(days=365)
    cleaned=[]
    for s in existing:
        if s.get("source_mode")!="europe_pmc_daily":
            cleaned.append(s); continue
        try:
            d=date.fromisoformat((s.get("date") or "")[:10])
            if d>=cutoff: cleaned.append(s)
        except:
            cleaned.append(s)

    cleaned.sort(key=lambda s:(s.get("date") or ""), reverse=True)
    DB.write_text(json.dumps(cleaned,ensure_ascii=False,indent=2),encoding="utf-8")
    meta=json.loads(META.read_text(encoding="utf-8"))
    meta["updated_at"]=datetime.now(timezone.utc).isoformat()
    meta["last_run_added"]=len(added)
    meta["total_studies"]=len(cleaned)
    meta["source"]="Europe PMC REST API"
    META.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"CardioUpdate: {len(added)} nuevos trabajos; total {len(cleaned)}.")

if __name__=="__main__":
    main()
