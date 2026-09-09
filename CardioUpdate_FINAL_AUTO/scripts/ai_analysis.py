import json
import os
from datetime import datetime, timezone

AI_MODEL = os.environ.get("CARDIOUPDATE_AI_MODEL", "gpt-5.6-terra")


def build_ai_analysis(main_study: dict, related: list[dict]):
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key or not related:
        return None

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    sources = []

    for i, r in enumerate(related, 1):
        sources.append({
            "source_id": i,
            "title": r.get("title", ""),
            "journal": r.get("journal", ""),
            "year": r.get("year", ""),
            "doi": r.get("doi", ""),
            "pmid": r.get("pmid", ""),
            "type": r.get("type", ""),
            "abstract_context_es": r.get("abstract_context_es", "")
        })

    evidence_packet = {
        "index_study": {
            "title": main_study.get("title", ""),
            "journal": main_study.get("journal", ""),
            "date": main_study.get("date", ""),
            "doi": main_study.get("doi", ""),
            "pmid": main_study.get("pmid", ""),
            "area": main_study.get("area", ""),
            "type": main_study.get("type", ""),
            "abstract_es": main_study.get("abstract_es", [])
        },
        "verified_related_sources": sources
    }

    instructions = """
Eres el editor científico de CardioUpdate, una aplicación profesional
dirigida a cardiólogos.

Analiza EXCLUSIVAMENTE el paquete de evidencia proporcionado.

No inventes datos, referencias, DOI, PMID, tamaños muestrales,
endpoints ni resultados.

Devuelve exclusivamente JSON válido con estas claves:

main_finding
magnitude_and_results
prior_evidence
novelty
clinical_implications
uncertainties
source_ids_used

Reglas:

- Español académico y preciso.
- Distingue asociación de causalidad.
- Si un dato no está disponible, indícalo.
- No extrapoles más allá de la población estudiada.
- Compara con evidencia previa solamente cuando las fuentes lo permitan.
- Toda afirmación sobre evidencia previa debe corresponder a source_id.
- source_ids_used solo puede contener IDs de las fuentes proporcionadas.
- Nunca clasifiques automáticamente un estudio como Practice Changer.
- Explica la potencial relevancia clínica sin indicar tratamiento individual.
"""

    response = client.responses.create(
        model=AI_MODEL,
        reasoning={"effort": "medium"},
        instructions=instructions,
        input=json.dumps(evidence_packet, ensure_ascii=False)
    )

    text = response.output_text.strip()

    if text.startswith("```"):
        text = text.strip("`")

        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return None

    allowed = {x["source_id"] for x in sources}
    used = result.get("source_ids_used") or []

    if not isinstance(used, list):
        return None

    if any(x not in allowed for x in used):
        return None

    required = [
        "main_finding",
        "magnitude_and_results",
        "prior_evidence",
        "novelty",
        "clinical_implications",
        "uncertainties"
    ]

    if any(not isinstance(result.get(k), str) for k in required):
        return None

    result["analysis_status"] = "AUTO · Síntesis generada por IA"
    result["analysis_model"] = AI_MODEL
    result["analysis_generated_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    return result
