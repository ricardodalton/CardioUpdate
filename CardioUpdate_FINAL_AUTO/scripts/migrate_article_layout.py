#!/usr/bin/env python3
"""Idempotent UI migration: original title -> abstract -> CardioUpdate analysis."""
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "index.html"
s = p.read_text(encoding="utf-8")
original = s

# Version marker.
s = s.replace("CardioUpdate-4.0-frozen-weekly-edition", "CardioUpdate-4.1-title-abstract-analysis")

# Always show the original indexed English title instead of abbreviated/edited short titles.
s = s.replace("${esc(lead.short)}", "${esc(lead.title)}")
s = s.replace("${esc(s.short)}", "${esc(s.title)}")

# Weekly lead: remove the explanatory sentence under the main title and the area/type-like label.
s = s.replace('<p class="dek">${esc(lead.why||lead.summary)}</p>', '')
s = s.replace('<span style="color:${a[1]};font-weight:900">${esc(a[3])}</span>', '')

# Cards/listings: do not show potentially truncated auto-generated summaries under titles.
s = s.replace('<p>${esc(s.summary)}</p>', '')

# Article header: title only, without the generated summary immediately below it.
s = s.replace('<p class="summary">${esc(s.summary)}</p>', '')

# Article body: remove the separate "Resumen CardioUpdate" block so the sequence is
# original title -> abstract -> CardioUpdate analysis.
summary_block = '<section class="articleBlock impact" style="--c:${a[1]}"><h2>Resumen CardioUpdate</h2><p>${esc(s.why||s.summary||\'Relevancia clínica pendiente de síntesis editorial.\')}</p></section>'
s = s.replace(summary_block, '')

if s != original:
    p.write_text(s, encoding="utf-8")
    print("CardioUpdate: aplicado orden título original -> abstract -> análisis.")
else:
    print("CardioUpdate: layout de artículos ya actualizado.")
