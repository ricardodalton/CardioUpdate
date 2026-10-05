#!/usr/bin/env python3
"""CardioUpdate weekly evidence pipeline.

Daily behavior (Saturday-Thursday):
- Search recent cardiology literature in Europe PMC.
- Accumulate/deduplicate candidates in data/candidates.json.
- Do NOT change the published weekly edition (data/studies.json).

Friday behavior:
- Search once more to absorb indexing delays.
- Select up to 30 high-priority, cardiovascular-relevant papers published from the previous Saturday
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
REMAINDER = ROOT / "data" / "weekly_remainder.json"
META = ROOT / "data" / "meta.json"
EPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CROSSREF_API = "https://api.crossref.org/works/"

MAX_WEEKLY = int(os.environ.get("CARDIOUPDATE_MAX_WEEKLY", "30"))
MAX_RELATED = int(os.environ.get("CARDIOUPDATE_MAX_RELATED", "6"))
TRANSLATE = os.environ.get("CARDIOUPDATE_TRANSLATE", "1") != "0"
FORCE_PUBLISH = os.environ.get("CARDIOUPDATE_FORCE_PUBLISH", "0") == "1"
DISCOVERY_LOOKBACK_DAYS = max(1, int(os.environ.get("CARDIOUPDATE_DISCOVERY_LOOKBACK_DAYS", "7")))
CANDIDATE_RETENTION_DAYS = max(14, int(os.environ.get("CARDIOUPDATE_CANDIDATE_RETENTION_DAYS", "35")))
DETECTED_AT = "cardioupdate_detected_at"
LAST_SEEN_AT = "cardioupdate_last_seen_at"

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
    return "No clasificado"


CARDIOVASCULAR_RELEVANCE_PATTERNS = [
    r"\\b(cardiovascular|cardiac|coronary|myocardial|heart failure|hfpef|hfref|atrial fibrillation|ventricular arrhythm|cardiomyopath|pericard|valvular|aortic stenosis|mitral regurgitation|tricuspid regurgitation|tavi|tavr|revasculari[sz]ation|pci|acute coronary|stemi|nstemi|myocardial infarction)\\b",
    r"\\b(hypertension|blood pressure|atherosclero|coronary calcium|coronary artery calcium|carotid plaque|peripheral arter|lipoprotein\\(a\\)|lp\\(a\\)|ldl cholesterol|apolipoprotein b|pcsk9|inclisiran|statin|dyslipid|cardiac rehabilitation)\\b",
    r"\\b(cardiovascular mortality|cardiovascular death|major adverse cardiovascular|mace\\b|heart failure hospitalization|hospitalization for heart failure|stroke|ischemic stroke|sudden cardiac death)\\b",
]


def cardiovascular_relevance(item: dict) -> bool:
    """Mandatory gate for the highlighted weekly issue.

    Admit clinical cardiology research and research from another specialty only
    when title/abstract states a direct, clinically meaningful cardiovascular
    disease, intervention, phenotype, or cardiovascular outcome.
    """
    title = clean_markup(item.get("title", "")).lower()
    abstract = clean_markup(item.get("abstractText", "")).lower()
    if not title or not abstract:
        return False
    text = f"{title} {abstract}"
    return any(re.search(pattern, text, flags=re.I) for pattern in CARDIOVASCULAR_RELEVANCE_PATTERNS)


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


def editorial_score(item: dict) -> tuple[int, dict]:
    """Rank already-eligible weekly papers for the single lead story.

    This is intentionally separate from the inclusion score. It favors evidence
    that a cardiologist should know if only one paper from the week were read.
    """
    text = f"{item.get('title','')} {item.get('abstractText','')} {type_text(item)}".lower()
    title = clean_markup(item.get("title", "")).lower()
    components = {"practice": 0, "novelty": 0, "methodology": 0, "clinical_effect": 0, "publication": 0}

    # Potential to change clinical practice (0-30).
    if re.search(r"randomized|randomised|phase 3|phase iii|clinical trial|controlled trial", text):
        components["practice"] += 16
    if re.search(r"mortality|cardiovascular death|myocardial infarction|stroke|hospitali[sz]ation|heart failure hospitalization", text):
        components["practice"] += 8
    if re.search(r"superior|superiority|reduced|reduction|lower risk|improved|benefit|effective|efficacy", text):
        components["practice"] += 6
    components["practice"] = min(30, components["practice"])

    # Novelty (0-20): explicit first/new evidence or a contemporary intervention.
    if re.search(r"first|novel|new|previously unknown|first-in-class", text):
        components["novelty"] += 10
    if re.search(r"mavacamten|aficamten|inclisiran|pcsk9|transcatheter|tavi|tavr|renal denervation|gene therapy|rna|sirna", text):
        components["novelty"] += 6
    if re.search(r"randomized|randomised|phase 3|phase iii", title):
        components["novelty"] += 4
    components["novelty"] = min(20, components["novelty"])

    # Methodological robustness (0-20).
    if re.search(r"randomized|randomised|controlled trial", text):
        components["methodology"] = 20
    elif re.search(r"meta-analysis|systematic review", text):
        components["methodology"] = 15
    elif re.search(r"prospective|cohort", text):
        components["methodology"] = 9
    else:
        components["methodology"] = 5

    # Clinical magnitude/relevance of the measured effect (0-20).
    if re.search(r"mortality|death", text):
        components["clinical_effect"] += 9
    if re.search(r"myocardial infarction|stroke|hospitali[sz]ation|mace\b|major adverse cardiovascular", text):
        components["clinical_effect"] += 7
    if re.search(r"hazard ratio|relative risk|risk ratio|odds ratio|confidence interval|number needed to treat", text):
        components["clinical_effect"] += 4
    components["clinical_effect"] = min(20, components["clinical_effect"])

    # Publication/source quality (0-10), deliberately capped so prestige alone
    # cannot determine the lead story.
    components["publication"] = min(10, round(journal_weight(item.get("journalTitle", "")) * 10 / 7))

    total = sum(components.values())
    return total, components


def lead_reason(item: dict, components: dict) -> str:
    text = f"{item.get('title','')} {item.get('abstractText','')} {type_text(item)}".lower()
    reasons = []
    if components.get("practice", 0) >= 20:
        reasons.append("alto potencial de impacto en la práctica clínica")
    if re.search(r"randomized|randomised|controlled trial|phase 3|phase iii", text):
        reasons.append("diseño experimental robusto")
    elif re.search(r"meta-analysis|systematic review", text):
        reasons.append("síntesis de evidencia de alto nivel")
    if re.search(r"mortality|cardiovascular death|myocardial infarction|stroke|hospitali[sz]ation|mace\b", text):
        reasons.append("evaluación de desenlaces cardiovasculares clínicamente relevantes")
    if components.get("novelty", 0) >= 10:
        reasons.append("aporte novedoso")
    if components.get("publication", 0) >= 8:
        reasons.append("publicación en una fuente de alta jerarquía")
    reasons = reasons[:3] or ["mayor puntuación editorial global entre los trabajos elegibles de la semana"]
    return "Seleccionado como principal por " + ", ".join(reasons) + "."


def choose_lead(selected: list[dict]) -> tuple[dict, int, dict]:
    ranked = [(editorial_score(x)[0], editorial_score(x)[1], x) for x in selected]
    ranked.sort(key=lambda z: (z[0], score(z[2]), (paper_date(z[2]) or date.min).isoformat()), reverse=True)
    total, components, item = ranked[0]
    return item, total, components


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


def pipeline_today() -> date:
    """Return the pipeline date, with an override for deterministic tests/recovery runs."""
    override = os.environ.get("CARDIOUPDATE_TODAY", "").strip()
    if override:
        return date.fromisoformat(override)
    return datetime.now(timezone.utc).date()


def fetch_recent(today: date | None = None):
    today = today or pipeline_today()
    published_start = today - timedelta(days=3)
    indexed_start = today - timedelta(days=DISCOVERY_LOOKBACK_DAYS)
    groups = ["cardiovascular OR cardiac OR coronary OR myocardial", '"heart failure" OR "atrial fibrillation" OR hypertension', "atherosclerosis OR valvular OR cardiomyopathy", '"peripheral artery" OR pericarditis OR aortic', '"congenital heart" OR fontan OR "tetralogy of fallot" OR coarctation OR "adult congenital"']
    results = {}
    for terms in groups:
        # FIRST_PDATE finds genuinely recent publications. CREATION_DATE also
        # catches citations that Europe PMC indexed today with an older journal
        # date; those were the records silently missed by the former pipeline.
        queries = (
            (f'FIRST_PDATE:[{published_start.isoformat()} TO {today.isoformat()}] AND ({terms}) sort_date:y', 100),
            (f'CREATION_DATE:[{indexed_start.isoformat()} TO {today.isoformat()}] AND ({terms}) sort_date:y', 250),
        )
        for query, page_size in queries:
            for item in epmc_search(query, page_size):
                key = candidate_key(item)
                if key: results[key] = item
            time.sleep(.5)
    if not results:
        print("Europe PMC: no se detectaron registros nuevos en la ventana consultada.")
    return list(results.values())


def candidate_key(item: dict) -> str:
    if item.get("pmid"): return "pmid:" + norm(item["pmid"])
    if item.get("doi"): return "doi:" + norm(item["doi"])
    title = norm(item.get("title", "")); return "title:" + title if title else ""


def paper_date(item: dict):
    raw = (item.get("firstPublicationDate") or item.get("date") or (item.get("journalInfo") or {}).get("printPublicationDate") or "")[:10]
    try: return date.fromisoformat(raw)
    except Exception: return None


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        # A damaged candidates file must stop the run. Treating it as [] would
        # overwrite the last valid pool and make "Resto de estudios" disappear.
        raise RuntimeError(f"No se pudo leer {path.name}; se conserva el archivo previo: {exc}") from exc


def save_json(path: Path, value):
    """Write JSON atomically so an interrupted action cannot leave an empty file."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def source_tracking_date(item: dict):
    for key in (DETECTED_AT, "firstIndexDate", "dateOfCreation", "firstPublicationDate", "date"):
        raw = str(item.get(key) or "")[:10]
        try:
            return date.fromisoformat(raw)
        except ValueError:
            continue
    return None


def compact_candidate(item: dict):
    """Keep only fields used by ranking and Friday issue generation."""
    fields = (
        "id", "source", "pmid", "pmcid", "doi", "title", "authorString",
        "journalTitle", "journalInfo", "pubTypeList", "abstractText",
        "firstPublicationDate", "firstIndexDate", "electronicPublicationDate",
        "pubYear", "publicationStatus", "citedByCount", "url", "date",
        DETECTED_AT, LAST_SEEN_AT,
    )
    return {key: item[key] for key in fields if item.get(key) not in (None, "", [], {})}


def merge_candidate_pool(pool: list[dict], recent: list[dict], today: date | None = None):
    today = today or pipeline_today()
    today_iso = today.isoformat()
    merged: dict[str, dict] = {}
    for item in pool:
        key = candidate_key(item)
        if not key:
            continue
        stored = dict(item)
        detected = source_tracking_date(stored)
        if detected:
            stored[DETECTED_AT] = detected.isoformat()
            stored.setdefault(LAST_SEEN_AT, detected.isoformat())
        merged[key] = compact_candidate(stored)
    for x in recent:
        key = candidate_key(x)
        if not x.get("title") or not key:
            continue
        previous = merged.get(key)
        stored = {**(previous or {}), **x}
        if previous:
            detected = source_tracking_date(previous) or today
        else:
            # This is CardioUpdate's first observation, regardless of an older
            # publisher/index date. It belongs to the active Saturday-Friday cycle.
            detected = today
        stored[DETECTED_AT] = detected.isoformat()
        stored[LAST_SEEN_AT] = today_iso
        merged[key] = compact_candidate(stored)
    cutoff = today - timedelta(days=CANDIDATE_RETENTION_DAYS); kept = []
    for x in merged.values():
        raw = str(x.get(LAST_SEEN_AT) or x.get(DETECTED_AT) or "")[:10]
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            d = paper_date(x)
        if d is None or d >= cutoff: kept.append(x)
    kept.sort(key=lambda x: (str(x.get(DETECTED_AT) or ""), (paper_date(x) or date.min).isoformat(), score(x)), reverse=True); return kept


def edition_window(day: date):
    friday = day
    if friday.weekday() != 4: friday = day - timedelta(days=(day.weekday() - 4) % 7)
    return friday - timedelta(days=6), friday


def collection_window(day: date):
    """Active collection cycle: Saturday through the following Friday."""
    saturday = day - timedelta(days=(day.weekday() - 5) % 7)
    return saturday, saturday + timedelta(days=6)


def build_weekly_remainder(pool: list[dict], day: date):
    start, _ = collection_window(day)
    items = []
    for item in pool:
        detected = source_tracking_date(item)
        if detected is None or not (start <= detected <= day):
            continue
        if not item.get("title") or is_guideline_like(item):
            continue
        if not (item.get("url") or item.get("doi") or item.get("pmid") or item.get("pmcid")):
            continue
        items.append({
            "title": clean_markup(item.get("title", "")),
            "doi": item.get("doi", ""),
            "pmid": item.get("pmid", ""),
            "pmcid": item.get("pmcid", ""),
            "url": original_url(item),
            "firstPublicationDate": item.get("firstPublicationDate", ""),
            "firstIndexDate": item.get("firstIndexDate", ""),
            DETECTED_AT: detected.isoformat(),
            "pubTypeList": item.get("pubTypeList") or {},
        })
    items.sort(key=lambda x: (x[DETECTED_AT], x.get("firstPublicationDate", ""), x["title"]), reverse=True)
    return items


def select_weekly(pool: list[dict], start: date, end: date):
    """Select up to 30 highlights; cardiovascular relevance is mandatory."""
    eligible = []
    for x in pool:
        d = paper_date(x)
        if d is None or not (start <= d <= end):
            continue
        if not x.get("title") or not x.get("abstractText") or is_guideline_like(x):
            continue
        if not cardiovascular_relevance(x):
            continue
        eligible.append((score(x), x))
    eligible.sort(key=lambda z: (z[0], (paper_date(z[1]) or date.min).isoformat()), reverse=True)
    # Quality and relevance prevail over quota: never add weaker papers merely
    # to reach 20. A weekly issue may legitimately contain fewer than 20.
    return [x for sc, x in eligible if sc >= 12][:MAX_WEEKLY]


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
    today=pipeline_today();existing=load_json(DB,[]);pool=load_json(CANDIDATES,[])
    if not isinstance(pool,list):raise RuntimeError("candidates.json debe contener una lista; se conserva el archivo previo.")
    previous_keys={candidate_key(x) for x in pool if candidate_key(x)}
    recent=fetch_recent(today)
    if not recent and not pool:raise RuntimeError("Las fuentes no devolvieron candidatos y no existe un pool previo; no se escribe candidates.json.")
    pool=merge_candidate_pool(pool,recent,today)
    if not pool:raise RuntimeError("La fusión produjo un pool vacío; no se reemplaza candidates.json.")
    save_json(CANDIDATES,pool)
    new_candidates=len({candidate_key(x) for x in recent if candidate_key(x)}-previous_keys)
    cycle_start,cycle_end=collection_window(today)
    remainder=build_weekly_remainder(pool,today);save_json(REMAINDER,remainder)
    cycle_candidates=len(remainder)
    meta=load_json(META,{})
    meta.update({"candidate_updated_at":datetime.now(timezone.utc).isoformat(),"candidate_pool":len(pool),"new_candidates":new_candidates,"candidate_cycle_start":cycle_start.isoformat(),"candidate_cycle_end":cycle_end.isoformat(),"candidate_cycle_count":cycle_candidates})
    publish=FORCE_PUBLISH or today.weekday()==4
    if not publish:
        save_json(META,meta)
        print(f"CardioUpdate: {len(pool)} candidatos acumulados; {new_candidates} nuevos y {cycle_candidates} del ciclo {cycle_start} a {cycle_end}. Edición publicada sin cambios hasta el viernes.");return
    start,end=edition_window(today);selected=select_weekly(pool,start,end);existing_map={candidate_key(x):x for x in existing if candidate_key(x)};issue=[]
    if not selected:raise RuntimeError(f"No hay estudios elegibles para la edición {start} a {end}; se conserva studies.json.")
    lead_item,lead_total,lead_components=choose_lead(selected)
    lead_key=candidate_key(lead_item)
    for x in selected:
        k=candidate_key(x);old=existing_map.get(k)
        if old and old.get("review_status")!="Revisión pendiente":
            # Backfill the original English abstract even when a reviewed record is reused.
            old["abstract_en"] = clean_markup(x.get("abstractText", "")) or old.get("abstract_en", "")
            issue.append(old)
        else:issue.append(build_study(x,score(x)))
    for study in issue:
        study["is_weekly_lead"] = candidate_key(study) == lead_key
        if study["is_weekly_lead"]:
            study["editorial_score"] = lead_total
            study["editorial_components"] = lead_components
            study["lead_reason"] = lead_reason(lead_item, lead_components)
    issue.sort(key=lambda st:(1 if st.get("is_weekly_lead") else 0,(st.get("auto_score") or 0),st.get("date") or ""),reverse=True);save_json(DB,issue)
    meta.update({"updated_at":datetime.now(timezone.utc).isoformat(),"edition_start":start.isoformat(),"edition_end":end.isoformat(),"total_studies":len(issue),"candidate_pool":len(pool),"publication_mode":"weekly_friday","source":"Europe PMC + Crossref","related_evidence_enabled":True,"related_evidence_max_sources":MAX_RELATED});save_json(META,meta)
    print(f"CardioUpdate: edición {start} a {end} publicada con {len(issue)} trabajos; {len(pool)} candidatos acumulados.")


if __name__=="__main__":main()
