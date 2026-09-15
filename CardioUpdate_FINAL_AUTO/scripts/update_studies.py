#!/usr/bin/env python3
"""CardioUpdate weekly evidence pipeline.

Daily behavior (Saturday-Thursday):
- Search recent cardiology literature in Europe PMC.
- Accumulate/deduplicate candidates in data/candidates.json.
- Do NOT change the published weekly edition (data/studies.json).

Friday behavior:
- Search once more to absorb indexing delays.
- Select the 20-30 highest-priority papers published from the previous Saturday
  through Friday.
- Replace data/studies.json with that weekly issue.
- Keep that issue unchanged until the next Friday.

Guidelines/consensus documents are excluded from the study issue because they
have their own permanent section (data/guides.json).
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from ai_analysis import build_ai_analysis

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "studies.json"
CANDIDATES = ROOT / "data" / "candidates.json"
META = ROOT / "data" / "meta.json"
EPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CROSSREF_API = "https://api.crossref.org/works/"

MIN_WEEKLY = int(os.environ.get("CARDIOUPDATE_MIN_WEEKLY", "20"))
MAX_WEEKLY = int(os.environ.get("CARDIOUPDATE_MAX_WEEKLY", "30"))
MAX_RELATED = int(os.environ.get("CARDIOUPDATE_MAX_RELATED", "6"))
TRANSLATE = os.environ.get("CARDIOUPDATE_TRANSLATE", "1") != "0"
FORCE_PUBLISH = os.environ.get("CARDIOUPDATE_FORCE_PUBLISH", "0") == "1"

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
    ("Cardiopatías congénitas", r"\b(congenital heart|adult congenital|achd\b|fontan|tetralogy of fallot|transposition of the great arteries|coarctation|atrial septal defect|ventricular septal defect|single ventricle|ebstein)\b"),
    ("Miocardiopatías", r"\b(hypertrophic cardiomyopathy|cardiac myosin|mavacamten|aficamten|amyloid|transthyretin|cardiomyopath)\b"),
    ("Insuficiencia cardíaca", r"\b(heart failure|hfpef|hfref|hfmref|ejection fraction|finerenone|sacubitril|sglt2)\b"),
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

STOPWORDS = {
    "the","and","for","with","from","into","among","after","before","during","versus","vs",
    "study","trial","patients","patient","clinical","randomized","randomised","effect","effects",
    "outcomes","outcome","cardiovascular","cardiac","heart","disease","treatment","therapy","risk",
    "of","in","on","to","a","an","is","are","by","as","or","at","using","use","new"
}


def clean_markup(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<\s*(br|/p|/h\d)\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\r", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def classify_area(text: str) -> str:
    for area, pattern in AREA_RULES:
        if re.search(pattern, text or "", flags=re.I):
            return area
    return "Prevención y aterosclerosis"


def journal_weight(journal: str) -> int:
    j = norm(journal)
    return max([w for k, w in JOURNAL_WEIGHTS.items() if k in j] or [0])


def type_text(item: dict) -> str:
    p = item.get("pubTypeList") or {}
    vals = p.get("pubType") or [] if isinstance(p, dict) else []
    if isinstance(vals, str): vals = [vals]
    return "; ".join(vals)


def is_guideline_like(item: dict) -> bool:
    text = f"{item.get('title','')} {type_text(item)}".lower()
    return bool(re.search(r"guideline|consensus|scientific statement|position statement", text))


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('abstractText','')} {type_text(item)}".lower()
    s = journal_weight(item.get("journalTitle", "")) * 3
    if re.search(r"randomized|randomised|clinical trial|controlled trial", text): s += 8
    if re.search(r"meta-analysis|systematic review", text): s += 5
    if re.search(r"phase 3|phase iii", text): s += 4
    if re.search(r"mortality|death|myocardial infarction|stroke|hospitali", text): s += 2
    if item.get("abstractText"): s += 3
    return s


def level(item: dict) -> str:
    return "Relevante" if score(item) >= 18 else "Seguimiento"


def split_sentences(text: str, max_chars=700):
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    chunks, cur = [], ""
    for p in parts:
        if not p: continue
        if len(cur) + len(p) + 1 <= max_chars: cur = (cur + " " + p).strip()
        else:
            if cur: chunks.append(cur)
            cur = p
    if cur: chunks.append(cur)
    return chunks


_TRANSLATOR = None
def translator():
    global _TRANSLATOR
    if _TRANSLATOR is None:
        from transformers import MarianMTModel, MarianTokenizer
        name = "Helsinki-NLP/opus-mt-en-es"
        _TRANSLATOR = (MarianTokenizer.from_pretrained(name), MarianMTModel.from_pretrained(name))
    return _TRANSLATOR


def translate_es(text: str) -> str:
    if not text or not TRANSLATE: return text or ""
    try:
        tok, mod = translator(); out = []
        for chunk in split_sentences(text):
            try:
                batch = tok([chunk], return_tensors="pt", padding=True, truncation=True, max_length=400)
                gen = mod.generate(**batch, max_new_tokens=400, num_beams=2)
                out.append(tok.batch_decode(gen, skip_special_tokens=True)[0])
            except Exception as exc:
                print(f"Traducción omitida para un fragmento: {exc}"); out.append(chunk)
        return " ".join(out).strip()
    except Exception as exc:
        print(f"Traducción completa omitida: {exc}"); return text


def structured_abstract_es(abstract: str):
    a = clean_markup(abstract)
    return [["Abstract", translate_es(a)]]


def first_sentences_es(sections, n=2):
    text = " ".join(x[1] for x in sections)
    return " ".join(re.split(r"(?<=[.!?])\s+", text)[:n]).strip()[:900]


def epmc_search(query: str, page_size: int = 40):
    params = {"query": query, "format": "json", "resultType": "core", "pageSize": str(page_size)}
    for attempt in range(4):
        try:
            r = requests.get(EPMC_API, params=params, timeout=60, headers={"User-Agent": "CardioUpdate/5.0 weekly evidence"})
            r.raise_for_status(); return (r.json().get("resultList") or {}).get("result") or []
        except requests.RequestException as exc:
            if attempt == 3:
                print(f"Europe PMC: consulta omitida tras reintentos: {exc}"); return []
            time.sleep(2 ** attempt)
    return []


def fetch_recent():
    today = date.today(); start = today - timedelta(days=3)
    groups = ["cardiovascular OR cardiac OR coronary OR myocardial", '"heart failure" OR "atrial fibrillation" OR hypertension', "atherosclerosis OR valvular OR cardiomyopathy", '"peripheral artery" OR pericarditis OR aortic', '"congenital heart" OR fontan OR "tetralogy of fallot" OR coarctation OR "adult congenital"']
    results = {}
    for terms in groups:
        q = f'FIRST_PDATE:[{start.isoformat()} TO {today.isoformat()}] AND ({terms}) sort_date:y'
        for item in epmc_search(q, 100):
            key = candidate_key(item)
            if key: results[key] = item
        time.sleep(.5)
    if not results: raise RuntimeError("Europe PMC no respondió después de los reintentos.")
    return list(results.values())


def candidate_key(item: dict) -> str:
    if item.get("doi"): return "doi:" + norm(item["doi"])
    if item.get("pmid"): return "pmid:" + norm(item["pmid"])
    title = norm(item.get("title", "")); return "title:" + title if title else ""


def paper_date(item: dict):
    raw = (item.get("firstPublicationDate") or item.get("date") or (item.get("journalInfo") or {}).get("printPublicationDate") or "")[:10]
    try: return date.fromisoformat(raw)
    except Exception: return None


def load_json(path: Path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default


def save_json(path: Path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_candidate_pool(pool: list[dict], recent: list[dict]):
    merged = {candidate_key(x): x for x in pool if candidate_key(x)}
    for x in recent:
        if x.get("title") and candidate_key(x): merged[candidate_key(x)] = x
    cutoff = date.today() - timedelta(days=21); kept = []
    for x in merged.values():
        d = paper_date(x)
        if d is None or d >= cutoff: kept.append(x)
    kept.sort(key=lambda x: ((paper_date(x) or date.min).isoformat(), score(x)), reverse=True); return kept


def edition_window(day: date):
    friday = day
    if friday.weekday() != 4: friday = day - timedelta(days=(day.weekday() - 4) % 7)
    return friday - timedelta(days=6), friday


def select_weekly(pool: list[dict], start: date, end: date):
    eligible = []
    for x in pool:
        d = paper_date(x)
        if d is None or not (start <= d <= end) or not x.get("title") or not x.get("abstractText") or is_guideline_like(x): continue
        eligible.append((score(x), x))
    eligible.sort(key=lambda z: (z[0], (paper_date(z[1]) or date.min).isoformat()), reverse=True)
    chosen = [x for sc, x in eligible if sc >= 12][:MAX_WEEKLY]
    if len(chosen) < MIN_WEEKLY:
        chosen_keys = {candidate_key(x) for x in chosen}
        for sc, x in eligible:
            if candidate_key(x) in chosen_keys or sc < 8: continue
            chosen.append(x); chosen_keys.add(candidate_key(x))
            if len(chosen) >= MIN_WEEKLY or len(chosen) >= MAX_WEEKLY: break
    return chosen[:MAX_WEEKLY]


def title_keywords(title: str, max_terms=7):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9()-]{2,}", title.lower())
    out=[]
    for w in words:
        if w not in STOPWORDS and w not in out: out.append(w)
    return out[:max_terms]


def crossref_verify(doi: str):
    if not doi: return None
    try:
        r=requests.get(CROSSREF_API+quote(doi,safe=""),timeout=25,headers={"User-Agent":"CardioUpdate/5.0"})
        if not r.ok:return None
        msg=(r.json() or {}).get("message") or {}
        return {"title":clean_markup((msg.get("title") or [""])[0]),"journal":clean_markup((msg.get("container-title") or [""])[0]),"year":((msg.get("issued") or {}).get("date-parts") or [[None]])[0][0]}
    except requests.RequestException:return None


def related_score(item: dict, main: dict, keywords: list[str]) -> int:
    text=f"{item.get('title','')} {item.get('abstractText','')} {type_text(item)}".lower(); s=journal_weight(item.get("journalTitle",""))*2
    for k in keywords:
        if k.lower() in text:s+=3
    if re.search(r"meta-analysis|systematic review",text):s+=8
    if re.search(r"guideline|consensus|scientific statement|position statement",text):s+=8
    if re.search(r"randomized|randomised|clinical trial|controlled trial",text):s+=6
    if item.get("abstractText"):s+=2
    return s


def original_url(item):
    if item.get("doi"):return "https://doi.org/"+item["doi"]
    if item.get("pmid"):return "https://pubmed.ncbi.nlm.nih.gov/"+item["pmid"]+"/"
    if item.get("pmcid"):return "https://europepmc.org/article/PMC/"+item["pmcid"]
    return "https://europepmc.org/"


def find_related_evidence(main: dict):
    keywords=title_keywords(main.get("title",""))
    if len(keywords)<2:return []
    q=f'({" OR ".join(keywords[:6])}) AND HAS_ABSTRACT:Y sort_cited:y'; pool=epmc_search(q,50); mk=candidate_key(main); ranked=[];seen=set()
    for item in pool:
        k=candidate_key(item)
        if not k or k==mk or k in seen:continue
        seen.add(k);ranked.append((related_score(item,main,keywords),item))
    ranked.sort(key=lambda z:z[0],reverse=True);related=[]
    for _,item in ranked[:MAX_RELATED]:
        doi=item.get("doi","");verified=crossref_verify(doi) if doi else None;title=clean_markup(item.get("title",""));journal=item.get("journalTitle","") or (item.get("journalInfo") or {}).get("journal",{}).get("title","");year=(item.get("firstPublicationDate") or "")[:4]
        if verified:title=verified.get("title") or title;journal=verified.get("journal") or journal;year=verified.get("year") or year
        abstract=clean_markup(item.get("abstractText",""))
        related.append({"title":title,"journal":journal,"year":year,"date":item.get("firstPublicationDate",""),"doi":doi,"pmid":item.get("pmid",""),"type":type_text(item),"url":original_url(item),"abstract_context_es":translate_es(" ".join(re.split(r"(?<=[.!?])\s+",abstract)[:2])) if abstract else "","verified_by_crossref":bool(verified) if doi else False,"source":"Europe PMC"+(" + Crossref" if verified else "")})
    return related


def build_context_analysis(area: str, summary: str, related: list[dict]) -> str:
    if not related:return "Trabajo incorporado a la edición semanal; contextualización bibliográfica adicional pendiente."
    refs="; ".join(f"{r.get('title','')} ({r.get('journal','')}, {r.get('year','')})" for r in related[:3])
    return f"Este trabajo se sitúa dentro de {area.lower()}. Hallazgo principal según el abstract: {summary} CardioUpdate recuperó {len(related)} fuentes relacionadas. Referencias prioritarias: {refs}. La síntesis automática no sustituye la lectura crítica del artículo completo ni una decisión clínica individual."


def make_id(item):
    base=item.get("doi") or item.get("pmid") or item.get("pmcid") or item.get("title") or "study"
    return re.sub(r"[^a-z0-9]+","-",base.lower()).strip("-")[:110]


def build_study(x: dict, sc: int):
    # Persist the source abstract itself in every weekly study. The UI therefore
    # never depends on candidates.json to display the lead paper abstract.
    abstract_en = clean_markup(x.get("abstractText", ""))
    abstract_es = structured_abstract_es(x.get("abstractText", ""))
    area=classify_area(f"{x.get('title','')} {x.get('abstractText','')}");ptypes=type_text(x)
    typ="Ensayo clínico" if re.search(r"trial|randomized|randomised",ptypes,re.I) else ("Revisión / meta-análisis" if re.search(r"review|meta",ptypes,re.I) else "Artículo científico")
    summary=first_sentences_es(abstract_es);related=find_related_evidence(x)
    study={"id":make_id(x),"title":clean_markup(x["title"]),"short":clean_markup(x["title"]),"area":area,"level":level(x),"type":typ,"journal":x.get("journalTitle") or (x.get("journalInfo") or {}).get("journal",{}).get("title",""),"date":x.get("firstPublicationDate") or (x.get("journalInfo") or {}).get("printPublicationDate",""),"summary":summary,"why":f"Seleccionado para la edición semanal por relevancia clínica, diseño y calidad de fuente en {area.lower()}.","detail":"Consultar el abstract original, el análisis contextual y las fuentes relacionadas.","url":original_url(x),"doi":x.get("doi",""),"pmid":x.get("pmid",""),"authors":x.get("authorString",""),"abstract_en":abstract_en,"abstract_es":abstract_es,"analysis_es":build_context_analysis(area,summary,related),"analysis_mode":"contexto_bibliografico_automatico","related_evidence":related,"source_mode":"europe_pmc_weekly","review_status":"Revisión pendiente","auto_score":sc,"imported_at":datetime.now(timezone.utc).isoformat()}
    ai_analysis=build_ai_analysis(study,related)
    if ai_analysis:
        study["ai_analysis"]=ai_analysis;study["analysis_es"]="\n\n".join([ai_analysis.get("main_finding",""),ai_analysis.get("magnitude_and_results",""),ai_analysis.get("prior_evidence",""),ai_analysis.get("novelty",""),ai_analysis.get("clinical_implications",""),ai_analysis.get("uncertainties","")]).strip();study["analysis_mode"]="ai_grounded_verified_sources";study["analysis_status"]=ai_analysis.get("analysis_status","AUTO")
    else:study["analysis_status"]="AUTO · Contexto bibliográfico"
    return study


def main():
    today=date.today();existing=load_json(DB,[]);pool=load_json(CANDIDATES,[]);recent=fetch_recent();pool=merge_candidate_pool(pool,recent);save_json(CANDIDATES,pool)
    publish=FORCE_PUBLISH or today.weekday()==4
    if not publish:
        print(f"CardioUpdate: {len(pool)} candidatos acumulados. Edición publicada sin cambios hasta el viernes.");return
    start,end=edition_window(today);selected=select_weekly(pool,start,end);existing_map={candidate_key(x):x for x in existing if candidate_key(x)};issue=[]
    for x in selected:
        k=candidate_key(x);old=existing_map.get(k)
        if old and old.get("review_status")!="Revisión pendiente":
            # Backfill the original English abstract even when a reviewed record is reused.
            old["abstract_en"] = clean_markup(x.get("abstractText", "")) or old.get("abstract_en", "")
            issue.append(old)
        else:issue.append(build_study(x,score(x)))
    issue.sort(key=lambda s:((s.get("auto_score") or 0),s.get("date") or ""),reverse=True);save_json(DB,issue)
    meta=load_json(META,{});meta.update({"updated_at":datetime.now(timezone.utc).isoformat(),"edition_start":start.isoformat(),"edition_end":end.isoformat(),"total_studies":len(issue),"candidate_pool":len(pool),"publication_mode":"weekly_friday","source":"Europe PMC + Crossref","related_evidence_enabled":True,"related_evidence_max_sources":MAX_RELATED});save_json(META,meta)
    print(f"CardioUpdate: edición {start} a {end} publicada con {len(issue)} trabajos; {len(pool)} candidatos acumulados.")


if __name__=="__main__":main()
