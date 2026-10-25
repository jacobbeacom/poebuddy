"""Visual theme + HTML components for the report UI.

Design notes:
- Dark warm surface with an antique-gold accent (headings only); body text
  and values stay in neutral ink tokens.
- Severity colors are a fixed status palette (contrast-checked >= 3:1 on
  the dark surface) and never appear without a text label chip, so color
  never carries meaning alone.
- Cinzel (display serif) is for headings/grades only; all values, labels
  and body copy use Inter with tabular numerals where columns align.
"""
from __future__ import annotations

import html

SEVERITY = {
    "critical": {"color": "#d03b3b", "label": "Critical"},
    "major":    {"color": "#ec835a", "label": "Major"},
    "minor":    {"color": "#fab219", "label": "Minor"},
    "info":     {"color": "#9db2c7", "label": "Note"},
    "good":     {"color": "#0ca30c", "label": "Good"},
}

GRADE_COLORS = {
    "A": "#0ca30c", "B": "#199e70", "C": "#fab219",
    "D": "#ec835a", "F": "#d03b3b", "?": "#8a857a",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Inter:wght@400;500;600;700&display=swap');

:root {
  --pb-gold: #c9a961;
  --pb-gold-soft: rgba(201,169,97,.16);
  --pb-border: rgba(201,169,97,.22);
  --pb-hairline: rgba(255,255,255,.08);
  --pb-surface: #191510;
  --pb-surface-2: #211b13;
  --pb-ink: #e8e4da;
  --pb-ink-2: #b5ae9f;
  --pb-muted: #8a857a;
}

html, body, [class*="css"], .stMarkdown, p, li {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

h1, h2, h3 {
  font-family: 'Cinzel', 'Georgia', serif !important;
  letter-spacing: .02em;
}
h1 {
  color: var(--pb-gold) !important;
  text-shadow: 0 0 24px rgba(201,169,97,.25);
}
h2, h3 { color: var(--pb-ink) !important; }

[data-testid="stSidebar"] {
  background: #14110c;
  border-right: 1px solid var(--pb-hairline);
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: var(--pb-gold) !important; }

.stButton > button, .stDownloadButton > button {
  border: 1px solid var(--pb-border);
  border-radius: 8px;
  font-weight: 600;
  letter-spacing: .02em;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(180deg, #d8b96f 0%, #b3924e 100%);
  color: #1a1408;
  border: none;
  text-shadow: none;
}
.stButton > button[kind="primary"]:hover {
  background: linear-gradient(180deg, #e3c67e 0%, #c09d55 100%);
  color: #1a1408;
}

hr { border-color: var(--pb-hairline) !important; }

/* ---- cards & chips ---- */
.pb-card {
  background: var(--pb-surface);
  border: 1px solid var(--pb-hairline);
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 12px;
}
.pb-chip {
  display: inline-block;
  font: 600 11px/1 'Inter', sans-serif;
  letter-spacing: .08em;
  text-transform: uppercase;
  padding: 4px 9px;
  border-radius: 999px;
  vertical-align: middle;
}

/* ---- grade badges & stat tiles ---- */
.pb-statrow {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  margin: 6px 0 20px 0;
}
.pb-badgebox {
  background: var(--pb-surface);
  border: 1px solid var(--pb-hairline);
  border-radius: 12px;
  padding: 14px 12px 12px 12px;
  text-align: center;
}
.pb-grade {
  font: 700 40px/1 'Cinzel', serif;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 68px; height: 68px;
  border-radius: 50%;
  margin-bottom: 8px;
}
.pb-tile {
  background: var(--pb-surface);
  border: 1px solid var(--pb-hairline);
  border-radius: 12px;
  padding: 14px 16px;
}
.pb-tile-label, .pb-badge-label {
  font: 600 11px/1.3 'Inter', sans-serif;
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--pb-muted);
}
.pb-tile-value {
  font: 600 28px/1.25 'Inter', sans-serif;
  font-variant-numeric: tabular-nums;
  color: var(--pb-ink);
  margin-top: 6px;
}
.pb-tile-sub { font: 400 12px/1.4 'Inter', sans-serif; color: var(--pb-ink-2); margin-top: 2px; }

/* ---- findings ---- */
.pb-finding {
  background: var(--pb-surface);
  border: 1px solid var(--pb-hairline);
  border-left-width: 3px;
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 10px;
}
.pb-finding-title {
  font: 600 15px/1.4 'Inter', sans-serif;
  color: var(--pb-ink);
  margin: 8px 0 4px 0;
}
.pb-finding-detail { font: 400 13.5px/1.55 'Inter', sans-serif; color: var(--pb-ink-2); }
.pb-fix {
  margin-top: 10px;
  padding: 9px 12px;
  background: var(--pb-gold-soft);
  border-left: 2px solid var(--pb-gold);
  border-radius: 6px;
  font: 400 13.5px/1.5 'Inter', sans-serif;
  color: var(--pb-ink);
}
.pb-fix b { color: var(--pb-gold); letter-spacing: .05em; }

/* ---- priority actions ---- */
.pb-action {
  display: flex; gap: 14px; align-items: flex-start;
  background: var(--pb-surface);
  border: 1px solid var(--pb-hairline);
  border-radius: 10px;
  padding: 13px 16px;
  margin-bottom: 8px;
}
.pb-action-n {
  flex: 0 0 30px;
  width: 30px; height: 30px;
  border-radius: 50%;
  border: 1.5px solid var(--pb-gold);
  color: var(--pb-gold);
  font: 700 15px/27px 'Cinzel', serif;
  text-align: center;
}
.pb-action-title { font: 600 14px/1.4 'Inter', sans-serif; color: var(--pb-ink); }
.pb-action-rec { font: 400 13px/1.5 'Inter', sans-serif; color: var(--pb-ink-2); margin-top: 2px; }

/* ---- hero (empty state) ---- */
.pb-hero { text-align: center; padding: 34px 0 10px 0; }
.pb-hero-sub {
  font: 400 15px/1.6 'Inter', sans-serif;
  color: var(--pb-ink-2);
  max-width: 560px; margin: 10px auto 0 auto;
}
.pb-features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-top: 26px;
}
.pb-feature {
  background: var(--pb-surface);
  border: 1px solid var(--pb-hairline);
  border-radius: 12px;
  padding: 18px;
  text-align: left;
}
.pb-feature-icon { font-size: 22px; }
.pb-feature h4 {
  font: 700 14px/1.3 'Cinzel', serif;
  color: var(--pb-gold);
  margin: 8px 0 6px 0;
  letter-spacing: .03em;
}
.pb-feature p { font: 400 13px/1.55 'Inter', sans-serif; color: var(--pb-ink-2); margin: 0; }

.pb-archetype {
  display: inline-block;
  font: 500 12.5px/1 'Inter', sans-serif;
  color: var(--pb-gold);
  background: var(--pb-gold-soft);
  border: 1px solid var(--pb-border);
  border-radius: 999px;
  padding: 6px 12px;
  margin: 2px 0 14px 0;
}
.pb-who { font: 500 14px/1.4 'Inter', sans-serif; color: var(--pb-ink-2); margin-bottom: 6px; }
</style>
"""


def _alpha(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def chip(severity: str) -> str:
    s = SEVERITY[severity]
    return (f'<span class="pb-chip" style="color:{s["color"]};'
            f'background:{_alpha(s["color"], 0.14)};'
            f'border:1px solid {_alpha(s["color"], 0.45)}">{s["label"]}</span>')


def grade_badge(label: str, grade: str) -> str:
    color = GRADE_COLORS.get(grade, GRADE_COLORS["?"])
    return (
        '<div class="pb-badgebox">'
        f'<div class="pb-grade" style="color:{color};'
        f'border:2px solid {color};background:{_alpha(color, 0.10)};'
        f'box-shadow:0 0 20px {_alpha(color, 0.22)}">{html.escape(grade)}</div>'
        f'<div class="pb-badge-label">{html.escape(label)}</div></div>'
    )


def stat_tile(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="pb-tile-sub">{html.escape(sub)}</div>' if sub else ""
    return ('<div class="pb-tile">'
            f'<div class="pb-tile-label">{html.escape(label)}</div>'
            f'<div class="pb-tile-value">{html.escape(value)}</div>'
            f'{sub_html}</div>')


def stat_row(cells: list[str]) -> str:
    return f'<div class="pb-statrow">{"".join(cells)}</div>'


def finding_card(f: dict) -> str:
    color = SEVERITY[f["severity"]]["color"]
    fix = (f'<div class="pb-fix"><b>FIX&nbsp;→</b>&nbsp; '
           f'{html.escape(f["recommendation"])}</div>'
           if f.get("recommendation") else "")
    refs = (f'<div class="pb-tile-sub" style="margin-top:8px">Mechanics: '
            f'{html.escape(", ".join(f["wiki_refs"]))} (wiki)</div>'
            if f.get("wiki_refs") else "")
    return (f'<div class="pb-finding" style="border-left-color:{color}">'
            f'{chip(f["severity"])}'
            f'<div class="pb-finding-title">{html.escape(f["title"])}</div>'
            f'<div class="pb-finding-detail">{html.escape(f["detail"])}</div>'
            f'{fix}{refs}</div>')


def action_item(i: int, title: str, rec: str, cost: str | None = None) -> str:
    cost_html = (f'<span class="pb-chip" style="color:var(--pb-gold);'
                 f'background:var(--pb-gold-soft);border:1px solid '
                 f'var(--pb-border);margin-left:8px">{html.escape(cost)}</span>'
                 if cost else "")
    return ('<div class="pb-action">'
            f'<div class="pb-action-n">{i}</div><div>'
            f'<div class="pb-action-title">{html.escape(title)}{cost_html}</div>'
            f'<div class="pb-action-rec">{html.escape(rec)}</div>'
            '</div></div>')


def phase_header(icon: str, label: str, sub: str = "") -> str:
    sub_html = (f'<span style="font:400 12.5px Inter,sans-serif;'
                f'color:var(--pb-muted);margin-left:10px">{html.escape(sub)}'
                '</span>' if sub else "")
    return (f'<div style="font:700 16px Cinzel,serif;color:var(--pb-gold);'
            f'margin:18px 0 10px 0">{icon} {html.escape(label)}{sub_html}</div>')


def archetype_pill(text: str) -> str:
    return f'<div class="pb-archetype">⚔️ {html.escape(text)}</div>'


def who_line(text: str) -> str:
    return f'<div class="pb-who">{html.escape(text)}</div>'


def hero(version: str) -> str:
    features = [
        ("🛡️", "Survivability",
         "Resistance caps and overcap, chaos res, life/ES pool, largest "
         "survivable hit, mitigation layers, recovery, unused spirit."),
        ("⚔️", "Damage",
         "DPS benchmarks matched to what your build scales — hits, DoT or "
         "minions — plus support sockets, gem levels and accuracy."),
        ("🤝", "Group play",
         "Aura/curse supports are detected and graded on party contribution: "
         "buff coverage, enemy debuffs, curse limits."),
        ("📜", "Grounded, not generated",
         "Every number is deterministic, benchmarked against the current "
         f"patch ({version}) wiki. The optional coach's notes only narrate "
         "the findings, with citations."),
    ]
    cards = "".join(
        f'<div class="pb-feature"><div class="pb-feature-icon">{icon}</div>'
        f'<h4>{title}</h4><p>{text}</p></div>'
        for icon, title, text in features)
    return (
        '<div class="pb-hero">'
        '<div class="pb-hero-sub">Paste your <b>Path of Building</b> export '
        'in the sidebar and get a prioritized, wiki-grounded improvement '
        'report for your Path of Exile 2 character.</div>'
        f'<div class="pb-features">{cards}</div></div>'
    )
