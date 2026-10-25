"""PoEBuddy: paste a Path of Building build, get an improvement report.

Run:  streamlit run app/report_ui.py
"""
from __future__ import annotations

import json

import streamlit as st

from app import ui_theme
from app.build_parser import parse_build
from app.pob_import import import_pob
from app.report import PHASES, generate_report
from app.settings import SETTINGS

st.set_page_config(page_title="PoEBuddy", page_icon="🎯", layout="wide")
st.markdown(ui_theme.CSS, unsafe_allow_html=True)

if "report" not in st.session_state:
    st.session_state.report = None
if "build" not in st.session_state:
    st.session_state.build = None


def _fmt_num(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 10_000:
        return f"{v / 1_000:.0f}k"
    return f"{v:,.0f}"


def _metric(analysis: dict, finding_id_prefix: str, key: str) -> float | None:
    for f in analysis["findings"]:
        if f["id"].startswith(finding_id_prefix):
            return f["metrics"].get(key)
    return None


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Import build")
    st.caption(
        "Paste a pobb.in link or a raw Path of Building export code. "
        "pobb.in links are fetched over the network; export codes are "
        "decoded locally."
    )
    pob_text = st.text_area(
        "PoB link or export code", key="pob_text", height=110,
        placeholder="https://pobb.in/xxxxxxxxxxxx  or  the raw export code",
    )
    role_choice = st.selectbox(
        "Build role",
        ["Auto-detect", "DPS carry", "Group support"],
        help="Group-support builds (aura/curse bots) are graded on party "
             "contribution and staying alive, not personal DPS.",
    )
    role = {"Auto-detect": "auto", "DPS carry": "dps",
            "Group support": "support"}[role_choice]
    include_notes = st.toggle(
        "Coach's notes (local LLM)",
        value=SETTINGS["report"]["coach_notes"],
        help="A short narrative grounded in wiki citations. Requires "
             "Ollama running; everything else works without it.",
    )
    include_prices = st.toggle(
        "Live prices (poe.ninja)",
        value=SETTINGS["ninja"]["enabled"],
        help="Attaches market costs to recommendations. Cached for "
             f"{SETTINGS['ninja']['cache_hours']}h; the report works "
             "fully without it.",
    )
    analyze_clicked = st.button("Analyze build", type="primary",
                                use_container_width=True)

    with st.expander("Advanced: build JSON"):
        st.caption("Inspect or hand-edit the canonical build, then re-run.")
        build_json = st.text_area(
            "Build JSON", height=200,
            value=json.dumps(st.session_state.build, indent=2)
            if st.session_state.build else "",
        )
        if st.button("Analyze JSON"):
            try:
                st.session_state.build = (
                    parse_build(build_json).model_dump(by_alias=True))
                with st.spinner("Analyzing build..."):
                    st.session_state.report = generate_report(
                        st.session_state.build, include_notes=include_notes,
                        role=role, include_prices=include_prices)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not analyze JSON: {exc}")

if analyze_clicked:
    try:
        with st.spinner("Importing from Path of Building..."):
            build = import_pob(pob_text)
        st.session_state.build = build.model_dump(by_alias=True)
        with st.spinner("Analyzing build against PoE2 benchmarks..."):
            st.session_state.report = generate_report(
                build, include_notes=include_notes, role=role,
                include_prices=include_prices)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not import/analyze the build: {exc}")

# ------------------------------------------------------------------ main
st.title("PoEBuddy")

if st.session_state.report is None:
    st.markdown(ui_theme.hero(SETTINGS["game"]["current_version"]),
                unsafe_allow_html=True)
else:
    rep = st.session_state.report
    a = rep["analysis"]

    who = " · ".join(x for x in (a["ascendancy"] or a["class"],
                                 f"level {a['level']}",
                                 a["main_skill"]) if x)
    st.markdown(ui_theme.who_line(who or "imported build"),
                unsafe_allow_html=True)
    st.markdown(
        ui_theme.archetype_pill(
            a["archetype"]["summary"]
            + (" · role set manually"
               if a["archetype"].get("role_forced") else "")),
        unsafe_allow_html=True)

    cells = [
        ui_theme.grade_badge("Survivability", a["grades"]["survivability"]),
        ui_theme.grade_badge(a["offense_label"], a["grades"]["offense"]),
    ]
    dps = _metric(a, "dps_tier", "dps")
    if dps:
        cells.append(ui_theme.stat_tile(
            "Main skill DPS", _fmt_num(dps),
            a["archetype"]["basis"] + "-based"))
    pool = _metric(a, "pool_", "pool")
    if pool:
        cells.append(ui_theme.stat_tile("Life + ES pool", _fmt_num(pool)))
    counts = a["issue_count"]
    cells.append(ui_theme.stat_tile(
        "Issues", f"{counts['critical'] + counts['major']}",
        f"{counts['critical']} critical · {counts['major']} major"))
    st.markdown(ui_theme.stat_row(cells), unsafe_allow_html=True)

    if not a["stats_available"]:
        st.warning(
            "No PoB-computed stats found in this import — only structural "
            "checks ran. Export directly from Path of Building so the "
            "stat sheet is included."
        )

    issues = [f for f in a["findings"]
              if f["severity"] in ("critical", "major", "minor")]
    goods = [f for f in a["findings"] if f["severity"] == "good"]
    infos = [f for f in a["findings"] if f["severity"] == "info"]

    st.subheader("Upgrade roadmap")
    roadmap = rep["roadmap"]
    sheet = rep.get("prices")
    if sheet:
        r = sheet.get("rates", {})
        rates = " · ".join(x for x in (
            f"1 div ≈ {r['exalted']:,.0f} ex" if r.get("exalted") else "",
            f"≈ {r['chaos']:,.1f} chaos" if r.get("chaos") else "") if x)
        st.caption(f"Live prices: poe.ninja · {sheet['league']} · {rates} · "
                   f"fetched {sheet['fetched_at_text']}")
    if any(roadmap.values()):
        blocks = []
        for key, label, icon in PHASES:
            steps = roadmap[key]
            if not steps:
                continue
            blocks.append(ui_theme.phase_header(
                icon, label,
                f"{len(steps)} step{'s' if len(steps) != 1 else ''}"))
            blocks.extend(
                ui_theme.action_item(i, f["title"], f["recommendation"],
                                     f.get("cost"))
                for i, f in enumerate(steps, 1))
        st.markdown("".join(blocks), unsafe_allow_html=True)
    else:
        st.success("Nothing urgent — the build's fundamentals are in order.")

    st.subheader("Findings")
    st.markdown("".join(ui_theme.finding_card(f) for f in issues + infos),
                unsafe_allow_html=True)

    if goods:
        with st.expander("What's already working", expanded=False):
            st.markdown(
                "".join(ui_theme.finding_card(f) for f in goods),
                unsafe_allow_html=True)

    if rep["notes"]:
        st.subheader("Coach's notes")
        st.markdown(
            f'<div class="pb-card pb-finding-detail" style="font-size:14px">'
            f'{ui_theme.html.escape(rep["notes"])}</div>',
            unsafe_allow_html=True)

    with st.expander("Sources & assumptions"):
        for e in rep["evidence"]:
            st.markdown(f"- **{e['title']}** — `{e['source_path']}`")
        for s in a["assumptions"]:
            st.markdown(f"- {s}")

    st.download_button(
        "⬇️ Download report (Markdown)",
        data=rep["markdown"],
        file_name="poebuddy_report.md",
        mime="text/markdown",
    )
