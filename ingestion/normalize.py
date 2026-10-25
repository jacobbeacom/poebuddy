"""Turn raw wikitext into normalized documents.

For each raw page we:
  - parse wikitext with mwparserfromhell
  - extract the infobox template fields (kept as structured dict)
  - strip navigation / templates / comments from prose
  - classify the document type from categories + infobox
  - flag obsolete / PoE1 content
  - detect a stated game version if present

Output: one JSON doc per page in data/normalized/.

Run:  python -m ingestion.normalize
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import mwparserfromhell as mw

from app.settings import SETTINGS

RAW_DIR = Path(SETTINGS["paths"]["raw_dir"])
NORM_DIR = Path(SETTINGS["paths"]["normalized_dir"])
DROP_KEYWORDS = [k.lower() for k in SETTINGS["wiki"]["drop_category_keywords"]]

# Map category / infobox hints -> document_type. First match wins.
TYPE_RULES: list[tuple[str, str]] = [
    ("unique", "unique_item"),
    ("skill gem", "skill"),
    ("active skill", "skill"),
    ("support gem", "support"),
    ("support skill", "support"),
    ("passive", "passive"),
    ("ascendancy", "ascendancy"),
    ("class", "class"),
    ("ailment", "ailment"),
    ("boss", "boss"),
    ("area", "area"),
    ("quest", "quest"),
    ("crafting", "crafting"),
    ("currency", "currency"),
    ("league", "league mechanic"),
    ("patch", "patch note"),
    ("guide", "guide"),
    ("disambiguation", "disambiguation"),
    ("mechanic", "damage mechanic"),
    ("item", "item"),
]

VERSION_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?)\b")


def classify(categories: list[str], infobox_name: str | None) -> str:
    hay = " ".join(categories).lower() + " " + (infobox_name or "").lower()
    for needle, dtype in TYPE_RULES:
        if needle in hay:
            return dtype
    return "guide"  # default bucket


def is_obsolete(categories: list[str]) -> bool:
    cats = " ".join(categories).lower()
    return any(k in cats for k in DROP_KEYWORDS)


def extract_infobox(wikicode) -> tuple[dict, str | None]:
    """Return (fields, template_name) for the first infobox-like template."""
    for tmpl in wikicode.filter_templates():
        name = str(tmpl.name).strip()
        if "infobox" in name.lower() or name.lower().endswith(" item"):
            fields = {}
            for param in tmpl.params:
                key = str(param.name).strip()
                val = str(param.value).strip()
                if key and val:
                    fields[key] = val
            return fields, name
    return {}, None


def to_plain_text(wikicode) -> str:
    """Strip templates/refs/comments, keep headings and readable prose."""
    # Remove HTML comments and reference tags.
    text = str(wikicode)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*/>", "", text)
    code = mw.parse(text)
    # strip_code keeps section headings as plain lines.
    plain = code.strip_code(normalize=True, collapse=True)
    # collapse >2 blank lines
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
    return plain


def detect_version(fields: dict, plain: str) -> str:
    for key in ("release_version", "version", "introduced"):
        if key in fields:
            m = VERSION_RE.search(fields[key])
            if m:
                return m.group(1)
    # fall back to configured current version (recorded as assumed, not stated)
    return SETTINGS["game"]["current_version"]


def normalize_one(rec: dict) -> dict:
    wikicode = mw.parse(rec.get("raw_wikitext", ""))
    infobox, infobox_name = extract_infobox(wikicode)
    plain = to_plain_text(wikicode)
    dtype = classify(rec.get("categories", []), infobox_name)
    return {
        "page_id": rec["page_id"],
        "title": rec["title"],
        "revision_id": rec["revision_id"],
        "namespace": rec["namespace"],
        "categories": rec.get("categories", []),
        "document_type": dtype,
        "obsolete": is_obsolete(rec.get("categories", [])),
        "source": rec.get("source", "wiki"),
        "source_path": rec.get("source_path", ""),
        "retrieved_at": rec.get("retrieved_at", ""),
        "game_version": detect_version(infobox, plain),
        "content_hash": rec.get("content_hash", ""),
        "infobox": infobox,
        "plain_text": plain,
    }


def run() -> None:
    NORM_DIR.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(RAW_DIR.glob("*.json"))
    print(f"Normalizing {len(raw_files)} raw pages...")
    n = 0
    for rf in raw_files:
        rec = json.loads(rf.read_text(encoding="utf-8"))
        doc = normalize_one(rec)
        (NORM_DIR / rf.name).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        n += 1
    print(f"Wrote {n} normalized docs to {NORM_DIR}")


if __name__ == "__main__":
    run()
