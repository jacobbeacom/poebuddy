"""Build-improvement report: deterministic findings + grounded narrative.

generate_report(build) is the single entry point. The findings and every
number come from analysis.py; the optional "coach's notes" section is the
only LLM output, and it is constrained to narrate the findings using
retrieved wiki text (cited by page title). If Ollama is down the report
still renders fully, just without notes.
"""
from __future__ import annotations

import time

from app import llm, ninja, retrieval
from app.analysis import analyze_build
from app.build_parser import Build, parse_build
from app.settings import SETTINGS

RCFG = SETTINGS["report"]

PHASES = [
    ("survive", "Phase 1 — Survive", "🛡️"),
    ("damage", "Phase 2 — Damage", "⚔️"),
    ("efficiency", "Phase 3 — Divines per hour", "💰"),
]

# finding id -> (poe.ninja item name, qty or metric-driven qty fn)
def _cost_source(f: dict) -> tuple[str, int] | None:
    if f["id"] == "supports_missing":
        orb = {2: "Lesser Jeweller's Orb", 3: "Greater Jeweller's Orb",
               4: "Perfect Jeweller's Orb"}.get(f["metrics"].get("supports"))
        return (orb, 1) if orb else None
    if f["id"] == "gem_quality_zero":
        return ("Gemcutter's Prism", 4)  # 4 x 5% = the 20% quality cap
    return None


def _annotate_costs(analysis: dict, sheet: dict | None) -> None:
    for f in analysis["findings"]:
        f["cost"] = None
        if sheet:
            src = _cost_source(f)
            if src:
                f["cost"] = ninja.price_text(sheet, src[0], src[1])


def build_roadmap(analysis: dict) -> dict[str, list[dict]]:
    """Actionable issues grouped into staged phases, cheap wins first
    within the same severity."""
    sev_rank = {"critical": 0, "major": 1, "minor": 2}
    roadmap: dict[str, list[dict]] = {k: [] for k, _, _ in PHASES}
    for f in analysis["findings"]:
        if f["severity"] in sev_rank and f["recommendation"]:
            roadmap[f["phase"]].append(f)
    for phase in roadmap.values():
        phase.sort(key=lambda f: (sev_rank[f["severity"]],
                                  0 if f.get("cost") else 1))
    return roadmap

SEVERITY_BADGE = {"critical": "🟥 CRITICAL", "major": "🟧 MAJOR",
                  "minor": "🟨 MINOR", "info": "ℹ️ NOTE", "good": "✅ GOOD"}

COACH_PROMPT = """You are a Path of Exile 2 build coach writing the closing
notes of a build report. You are given the deterministic findings (JSON)
and excerpts from the PoE2 wiki.

Rules:
- Do not invent numbers, thresholds, item names, or mechanics. Every number
  you mention must already appear in the findings.
- Ground mechanic explanations in the wiki excerpts and cite page titles
  in parentheses, e.g. (Resistance).
- 150-250 words, plain prose, second person, no headings or lists.
- Focus on the 2-3 highest-impact changes and the order to do them in.
- If the findings are mostly good, say so briefly and suggest the next
  milestone instead of manufacturing problems."""


def _gather_evidence(analysis: dict) -> list[dict]:
    """Retrieve wiki chunks for the mechanics behind the top findings."""
    titles_wanted: list[str] = []
    for f in analysis["findings"]:
        if f["severity"] in ("critical", "major"):
            titles_wanted.extend(f["wiki_refs"])
    if analysis.get("main_skill"):
        titles_wanted.append(analysis["main_skill"])
    seen: set[str] = set()
    evidence: list[dict] = []
    for title in titles_wanted:
        if title in seen or len(evidence) >= RCFG["evidence_chunks"]:
            continue
        seen.add(title)
        try:
            hits = retrieval.search(title, {"obsolete": False})
        except Exception:  # noqa: BLE001 -- index may be missing/locked
            return evidence
        if hits:
            exact = next((h for h in hits
                          if h["title"].lower() == title.lower()), None)
            evidence.append(exact or hits[0])
    return evidence


def _coach_notes(analysis: dict, evidence: list[dict]) -> str | None:
    import json
    findings = [f for f in analysis["findings"] if f["severity"] != "good"]
    excerpts = "\n\n".join(
        f"[{e['title']}] {e['text'][:800]}" for e in evidence)
    role_line = ("This is a GROUP-SUPPORT build: frame advice around "
                 "enabling the party's carry, not personal damage."
                 if analysis["role"] == "support" else "")
    user = (f"BUILD ARCHETYPE: {analysis['archetype']['summary']}. {role_line}\n\n"
            f"FINDINGS:\n{json.dumps(findings[:10], indent=1)}\n\n"
            f"WIKI EXCERPTS:\n{excerpts or '(none retrieved)'}")
    try:
        return llm.chat(
            [{"role": "system", "content": COACH_PROMPT},
             {"role": "user", "content": user}],
            temperature=0.3,
        ).strip()
    except Exception:  # noqa: BLE001 -- notes are optional
        return None


def _fmt_finding(f: dict) -> str:
    lines = [f"### {SEVERITY_BADGE[f['severity']]} — {f['title']}",
             "", f["detail"]]
    if f["recommendation"]:
        lines += ["", f"**Fix:** {f['recommendation']}"]
    if f["wiki_refs"]:
        lines += ["", f"*Mechanics: {', '.join(f['wiki_refs'])} (wiki)*"]
    return "\n".join(lines)


def _rates_line(sheet: dict | None) -> str:
    if not sheet:
        return ""
    r = sheet.get("rates", {})
    parts = [f"1 div ≈ {r['exalted']:,.0f} ex" if r.get("exalted") else "",
             f"≈ {r['chaos']:,.1f} chaos" if r.get("chaos") else ""]
    rates = " ".join(p for p in parts if p)
    return (f"Live prices: poe.ninja · league **{sheet['league']}** · "
            f"{rates} · fetched {sheet['fetched_at_text']}")


def render_markdown(analysis: dict, notes: str | None,
                    evidence: list[dict], sheet: dict | None = None) -> str:
    a = analysis
    who = " ".join(x for x in (a["ascendancy"] or a["class"],
                               f"level {a['level']}") if x)
    supports = ", ".join(a["main_supports"]) or "none"
    issues = [f for f in a["findings"]
              if f["severity"] in ("critical", "major", "minor")]
    goods = [f for f in a["findings"] if f["severity"] == "good"]
    notes_block = (f"\n## Coach's notes\n\n{notes}\n" if notes else "")
    sources = ("\n".join(f"- {e['title']} — `{e['source_path']}`"
                         for e in evidence) or "- (none retrieved)")
    counts = a["issue_count"]

    md = f"""# PoEBuddy build report

**{who}** · main skill **{a['main_skill'] or 'unknown'}** (supports: {supports})

*Detected: {a['archetype']['summary']}*

| | |
|---|---|
| **Survivability** | **{a['grades']['survivability']}** |
| **{a['offense_label']}** | **{a['grades']['offense']}** |
| Issues found | {counts['critical']} critical · {counts['major']} major · {counts['minor']} minor |

{"⚠️ *No PoB-computed stats were found in this import; only structural checks ran. Import a full PoB export for the complete analysis.*" if not a['stats_available'] else ""}

## Upgrade roadmap

"""
    roadmap = build_roadmap(a)
    any_action = False
    for key, label, icon in PHASES:
        steps = roadmap[key]
        if not steps:
            continue
        any_action = True
        md += f"\n### {icon} {label}\n\n"
        for i, f in enumerate(steps, 1):
            cost = f" *({f['cost']})*" if f.get("cost") else ""
            md += f"{i}. **{f['title']}**{cost} — {f['recommendation']}\n"
    if not any_action:
        md += "Nothing urgent — the build's fundamentals are in order.\n"
    rates = _rates_line(sheet)
    if rates:
        md += f"\n{rates}\n"

    md += "\n## Detailed findings\n\n"
    md += "\n\n".join(_fmt_finding(f) for f in issues) or "_No issues._"
    if goods:
        md += "\n\n## What's already working\n\n"
        md += "\n".join(f"- ✅ {f['title']}: {f['detail']}" for f in goods)
    md += notes_block
    md += f"""
## Sources & assumptions

Wiki pages consulted:
{sources}

"""
    md += "\n".join(f"- {s}" for s in a["assumptions"])
    md += (f"\n\n*Generated by PoEBuddy · patch "
           f"{SETTINGS['game']['current_version']} wiki snapshot · "
           f"{time.strftime('%Y-%m-%d %H:%M')}*\n")
    return md


def generate_report(build: dict | Build, include_notes: bool = True,
                    role: str = "auto", include_prices: bool = True) -> dict:
    b = build if isinstance(build, Build) else parse_build(build)
    analysis = analyze_build(b, role=role)
    sheet = ninja.get_prices() if include_prices else None
    _annotate_costs(analysis, sheet)
    evidence = _gather_evidence(analysis)
    notes = _coach_notes(analysis, evidence) if include_notes else None
    markdown = render_markdown(analysis, notes, evidence, sheet)
    return {"analysis": analysis, "evidence": evidence, "notes": notes,
            "markdown": markdown, "roadmap": build_roadmap(analysis),
            "prices": sheet}
