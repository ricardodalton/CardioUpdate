#!/usr/bin/env python3
"""
CardioUpdate daily evidence updater.

Sources:
- Europe PMC REST API (new publications, metadata, indexed abstracts)
- Crossref REST API (DOI metadata verification for related evidence)
- Existing editorial database in data/studies.json

The updater:
1. Searches the last 3 calendar days to absorb indexing delays.
2. Scores cardiology relevance and source quality.
3. Deduplicates by DOI/PMID/title.
4. Translates indexed English abstracts to Spanish locally with MarianMT.
5. For every new study, retrieves 3-6 related publications to provide evidence context.
6. Verifies DOI metadata through Crossref whenever a DOI is available.
7. Adds a conservative automated contextual synthesis based only on retrieved sources.
8. Never overwrites editorially reviewed entries.
"""

from __future__ import annotations
import json, os, re, html, time
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
import requests
from ai_analysis import build_ai_analysis
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "studies.json"
META = ROOT / "data" / "meta.json"
EPMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
CROSSREF_API = "https://api.crossref.org/works/"
MAX_NEW_PER_RUN = int(os.environ.get("CARDIOUPDATE_MAX_NEW", "12"))
MAX_RELATED = int(os.environ.get("CARDIOUPDATE_MAX_RELATED", "6"))
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
    for k, w in JOURNAL_WEIGHTS.items():
        if k in j:
            best = max(best, w)
    return best


def type_text(item: dict) -> str:
    p = item.get("pubTypeList") or {}
    vals = p.get("pubType") or [] if isinstance(p, dict) else []
    if isinstance(vals, str):
        vals = [vals]
    return "; ".join(vals)


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('abstractText','')} {type_text(item)}".lower()
    s = journal_weight(item.get("journalTitle", "")) * 3
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
    chunks, cur = [], ""
    for p in parts:
        if not p:
            continue
        if len(cur) + len(p) + 1 <= max_chars:
            cur = (cur + " " + p).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


_TRANSLATOR = None

def translator():
    global _TRANSLATOR
    if _TRANSLATOR is None:
        from transformers import MarianMTModel, MarianTokenizer
        model_name = "Helsinki-NLP/opus-mt-en-es"
        tok = MarianTokenizer.from_pretrained(model_name)
        mod = MarianMTModel.from_pretrained(model_name)
        _TRANSLATOR = (tok, mod)
    return _TRANSLATOR


def translate_es(text: str) -> str:
    if not text:
        return ""

    if not TRANSLATE:
        return text

    try:
        tok, mod = translator()
        out = []

        for chunk in split_sentences(text, max_chars=700):
            try:
                batch = tok(
                    [chunk],
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=400
                )

                gen = mod.generate(
                    **batch,
                    max_new_tokens=400,
                    num_beams=2
                )

                translated = tok.batch_decode(
                    gen,
                    skip_special_tokens=True
                )[0]

                out.append(translated)

            except Exception as e:
                print(f"Traducción omitida para un fragmento: {e}")
                out.append(chunk)

        return " ".join(out).strip()

    except Exception as e:
        print(f"Traducción completa omitida: {e}")
        return text


def structured_abstract_es(abstract: str):
    a = clean_markup(abstract)
    heading_map = {
        "background":"Antecedentes","objective":"Objetivo","objectives":"Objetivos",
        "methods":"Métodos","method":"Métodos","results":"Resultados",
        "conclusion":"Conclusión","conclusions":"Conclusiones","importance":"Importancia",
        "design":"Diseño","setting":"Ámbito","participants":"Participantes",
        "interventions":"Intervenciones","main outcomes and measures":"Resultados principales"
    }
    pat = re.compile(r"(?im)^(background|objective|objectives|methods?|results|conclusions?|importance|design|setting|participants|interventions|main outcomes and measures)\s*:?\s*$")
    matches = list(pat.finditer(a))
    sections = []
    if matches:
        for i, m in enumerate(matches):
            key = m.group(1).lower()
            body = a[m.end(): matches[i+1].start() if i+1 < len(matches) else len(a)].strip()
            if body:
                sections.append([heading_map.get(key, key.title()), translate_es(body)])
    else:
        sections = [["Abstract", translate_es(a)]]
    return sections


def first_sentences_es(sections, n=2):
    text = " ".join(x[1] for x in sections)
    ss = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(ss[:n]).strip()[:900]


def epmc_search(query: str, page_size: int = 40):
    params = {"query": query, "format": "json", "resultType": "core", "pageSize": str(page_size)}
    for attempt in range(4):
        try:
            r = requests.get(EPMC_API, params=params, timeout=60,
                             headers={"User-Agent": "CardioUpdate/4.0 evidence-context updater"})
            r.raise_for_status()
            return (r.json().get("resultList") or {}).get("result") or []
        except requests.RequestException as e:
            if attempt == 3:
                print(f"Europe PMC: consulta omitida tras reintentos: {e}")
                return []
            time.sleep(2 ** attempt)
    return []


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
        for item in epmc_search(q, 75):
            key = item.get("doi") or item.get("pmid") or item.get("pmcid") or item.get("title")
            if key:
                results[str(key).lower()] = item
        time.sleep(.7)
    if not results:
        raise RuntimeError("Europe PMC no respondió después de los reintentos.")
    return list(results.values())


def title_keywords(title: str, max_terms: int = 7):
    words = re.findall(r"[A-Za-z][A-Za-z0-9()\-]{3,}", title or "")
    out = []
    for w in words:
        lw = w.lower().strip("-()")
        if lw in STOPWORDS or lw.isdigit():
            continue
        if lw not in [x.lower() for x in out]:
            out.append(w)
        if len(out) >= max_terms:
            break
    return out


def crossref_verify(doi: str):
    if not doi:
        return None
    try:
        r = requests.get(CROSSREF_API + quote(doi, safe=""), timeout=25,
                         headers={"User-Agent": "CardioUpdate/4.0 (mailto:cardioupdate@example.invalid)"})
        if not r.ok:
            return None
        msg = (r.json() or {}).get("message") or {}
        title = (msg.get("title") or [""])[0]
        journal = (msg.get("container-title") or [""])[0]
        issued = msg.get("issued", {}).get("date-parts", [[None]])
        year = issued[0][0] if issued and issued[0] else None
        return {"title": clean_markup(title), "journal": clean_markup(journal), "year": year}
    except requests.RequestException:
        return None


def related_score(item: dict, main: dict, keywords: list[str]) -> int:
    text = f"{item.get('title','')} {item.get('abstractText','')} {type_text(item)}".lower()
    s = journal_weight(item.get("journalTitle", "")) * 2
    for k in keywords:
        if k.lower() in text:
            s += 3
    if re.search(r"meta-analysis|systematic review", text): s += 8
    if re.search(r"guideline|consensus|scientific statement|position statement", text): s += 8
    if re.search(r"randomized|randomised|clinical trial|controlled trial", text): s += 6
    if item.get("abstractText"): s += 2
    # Prefer evidence published before the index study when dates are known.
    md = (main.get("firstPublicationDate") or "")[:10]
    rd = (item.get("firstPublicationDate") or "")[:10]
    if md and rd and rd <= md:
        s += 2
    return s


def find_related_evidence(main: dict):
    keywords = title_keywords(main.get("title", ""))
    if len(keywords) < 2:
        return []
    phrase = " AND ".join(f'\"{k}\"' if " " in k else k for k in keywords[:5])
    # Relaxed OR fallback makes the search resilient when a title is very specific.
    q1 = f'({phrase}) AND HAS_ABSTRACT:Y sort_cited:y'
    q2 = f'({" OR ".join(keywords[:6])}) AND HAS_ABSTRACT:Y sort_cited:y'
    pool = epmc_search(q1, 40)
    if len(pool) < 8:
        pool += epmc_search(q2, 50)

    main_doi = norm(main.get("doi", ""))
    main_pmid = norm(main.get("pmid", ""))
    main_title = norm(main.get("title", ""))
    seen, ranked = set(), []
    for item in pool:
        doi = norm(item.get("doi", ""))
        pmid = norm(item.get("pmid", ""))
        title = norm(item.get("title", ""))
        if (doi and doi == main_doi) or (pmid and pmid == main_pmid) or title == main_title:
            continue
        key = doi or pmid or title
        if not key or key in seen:
            continue
        seen.add(key)
        ranked.append((related_score(item, main, keywords), item))
    ranked.sort(key=lambda x: x[0], reverse=True)

    related = []
    for _, item in ranked[:MAX_RELATED * 2]:
        if len(related) >= MAX_RELATED:
            break
        doi = item.get("doi", "")
        verified = crossref_verify(doi) if doi else None
        title = clean_markup(item.get("title", ""))
        journal = item.get("journalTitle", "") or item.get("journalInfo", {}).get("journal", {}).get("title", "")
        year = (item.get("firstPublicationDate") or item.get("journalInfo", {}).get("printPublicationDate", ""))[:4]
        if verified:
            # Crossref is used as a verification layer, but Europe PMC remains the source of abstract/PMID data.
            title = verified.get("title") or title
            journal = verified.get("journal") or journal
            year = verified.get("year") or year
        abstract = clean_markup(item.get("abstractText", ""))
        abstract_es = translate_es(" ".join(re.split(r"(?<=[.!?])\s+", abstract)[:2])) if abstract else ""
        related.append({
            "title": title,
            "journal": journal,
            "year": year,
            "date": item.get("firstPublicationDate", ""),
            "doi": doi,
            "pmid": item.get("pmid", ""),
            "type": type_text(item),
            "url": original_url(item),
            "abstract_context_es": abstract_es,
            "verified_by_crossref": bool(verified) if doi else False,
            "source": "Europe PMC" + (" + Crossref" if verified else "")
        })
        time.sleep(.15)
    return related


def build_context_analysis(area: str, summary: str, related: list[dict]) -> str:
    """Conservative synthesis using only retrieved bibliographic material.

    It intentionally avoids claiming concordance/discordance unless that relationship has
    been explicitly established by a later generative editorial layer.
    """
    if not related:
        return "El trabajo fue incorporado automáticamente, pero todavía no se recuperó evidencia relacionada suficiente para contextualizarlo de forma segura."
    kinds = []
    for r in related:
        t = (r.get("type") or "").lower()
        if "meta" in t or "review" in t:
            kinds.append("revisiones o metaanálisis")
        elif "guideline" in t or "consensus" in t:
            kinds.append("guías o consensos")
        elif "trial" in t or "random" in t:
            kinds.append("ensayos clínicos")
    kinds_txt = ", ".join(dict.fromkeys(kinds)) if kinds else "estudios clínicos relacionados"
    refs = "; ".join(f"{r.get('title','')} ({r.get('journal','')}, {r.get('year','')})" for r in related[:3])
    return (
        f"Este trabajo se sitúa dentro de {area.lower()}. Según el abstract indexado, el hallazgo principal puede resumirse así: {summary} "
        f"Para contextualizarlo, CardioUpdate recuperó {len(related)} fuentes previas o relacionadas, incluyendo {kinds_txt}. "
        f"Entre las referencias de mayor prioridad se encuentran: {refs}. "
        "Esta síntesis automática describe el contexto bibliográfico recuperado y no sustituye la lectura crítica del artículo completo. "
        "La comparación causal entre estudios, la valoración de heterogeneidad y cualquier cambio de conducta deben quedar sujetos a revisión editorial."
    )


def make_id(item):
    base = item.get("doi") or item.get("pmid") or item.get("pmcid") or item.get("title") or "study"
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:110]


def original_url(item):
    if item.get("doi"): return "https://doi.org/" + item["doi"]
    if item.get("pmid"): return "https://pubmed.ncbi.nlm.nih.gov/" + item["pmid"] + "/"
    if item.get("pmcid"): return "https://europepmc.org/article/PMC/" + item["pmcid"]
    return "https://europepmc.org/"


def dedup_key(s):
    if s.get("doi"): return "doi:" + norm(s["doi"])
    if s.get("pmid"): return "pmid:" + norm(s["pmid"])
    return "title:" + norm(s.get("title", ""))


def main():
    existing = json.loads(DB.read_text(encoding="utf-8"))
    keys = {dedup_key(x) for x in existing}
    raw = fetch_recent()
    candidates = []
    for x in raw:
        if not x.get("title") or not x.get("abstractText"):
            continue
        sc = score(x)
        if sc < 12:
            continue
        candidates.append((sc, x))
    candidates.sort(key=lambda z: z[0], reverse=True)

    added = []
    for sc, x in candidates:
        if len(added) >= MAX_NEW_PER_RUN:
            break
        k = ("doi:" + norm(x.get("doi"))) if x.get("doi") else ("pmid:" + norm(x.get("pmid"))) if x.get("pmid") else "title:" + norm(x["title"])
        if k in keys:
            continue
        abstract_es = structured_abstract_es(x.get("abstractText", ""))
        area = classify_area(f"{x.get('title','')} {x.get('abstractText','')}")
        ptypes = type_text(x)
        typ = "Ensayo clínico" if re.search(r"trial|randomized|randomised", ptypes, re.I) else ("Revisión / meta-análisis" if re.search(r"review|meta", ptypes, re.I) else "Artículo científico")
        summary = first_sentences_es(abstract_es)
        related = find_related_evidence(x)
        analysis_es = build_context_analysis(area, summary, related)
        ai_analysis = None
        s = {
            "id": make_id(x),
            "title": clean_markup(x["title"]),
            "short": clean_markup(x["title"]),
            "area": area,
            "level": level(x),
            "type": typ,
            "journal": x.get("journalTitle") or x.get("journalInfo", {}).get("journal", {}).get("title", ""),
            "date": x.get("firstPublicationDate") or x.get("journalInfo", {}).get("printPublicationDate", ""),
            "summary": summary,
            "why": f"Trabajo nuevo en {area.lower()} seleccionado automáticamente por fuente, diseño y relevancia temática. Revisión editorial pendiente.",
            "detail": "Consultar el abstract ampliado, el análisis contextual y las fuentes relacionadas.",
            "url": original_url(x),
            "doi": x.get("doi", ""),
            "pmid": x.get("pmid", ""),
            "authors": x.get("authorString", ""),
            "abstract_es": abstract_es,
            "analysis_es": analysis_es,
            "analysis_mode": "contexto_bibliografico_automatico",
            "related_evidence": related,
            "source_mode": "europe_pmc_daily",
            "review_status": "Revisión pendiente",
            "auto_score": sc,
            "imported_at": datetime.now(timezone.utc).isoformat()
        }
        ai_analysis = build_ai_analysis(s, related)

        if ai_analysis:
            s["ai_analysis"] = ai_analysis
            s["analysis_es"] = (
                f"{ai_analysis['main_finding']}\n\n"
                f"{ai_analysis['magnitude_and_results']}\n\n"
                f"{ai_analysis['prior_evidence']}\n\n"
                f"{ai_analysis['novelty']}\n\n"
                f"{ai_analysis['clinical_implications']}\n\n"
                f"{ai_analysis['uncertainties']}"
            )
            s["analysis_mode"] = "ai_grounded_verified_sources"
            s["analysis_status"] = ai_analysis["analysis_status"]
        else:
            s["analysis_status"] = "AUTO · Contexto bibliográfico"
        existing.append(s)
        added.append(s)
        keys.add(k)

    cutoff = date.today() - timedelta(days=365)
    cleaned = []
    for s in existing:
        if s.get("source_mode") != "europe_pmc_daily":
            cleaned.append(s)
            continue
        try:
            d = date.fromisoformat((s.get("date") or "")[:10])
            if d >= cutoff:
                cleaned.append(s)
        except Exception:
            cleaned.append(s)

    cleaned.sort(key=lambda s: (s.get("date") or ""), reverse=True)
    DB.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = json.loads(META.read_text(encoding="utf-8"))
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    meta["last_run_added"] = len(added)
    meta["total_studies"] = len(cleaned)
    meta["source"] = "Europe PMC + Crossref"
    meta["related_evidence_enabled"] = True
    meta["related_evidence_max_sources"] = MAX_RELATED
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"CardioUpdate: {len(added)} nuevos trabajos; total {len(cleaned)}. Evidencia relacionada activada.")


if __name__ == "__main__":
    main()
