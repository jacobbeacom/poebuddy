"""Heading-aware chunking.

Rules (from the design doc):
  - split on headings, not fixed character counts
  - repeat page title + heading path in every chunk
  - aim ~300-800 tokens, overlap prose ~50-100 tokens
  - keep lists/tables together where possible
  - never mix game versions in a chunk (single page = single version here)
  - store infobox as a separate structured record (handled in index.py)

Output: data/normalized/chunks.jsonl  (one chunk per line)

Run:  python -m ingestion.chunk
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.settings import SETTINGS

NORM_DIR = Path(SETTINGS["paths"]["normalized_dir"])
CHUNKS_PATH = NORM_DIR / "chunks.jsonl"

CFG = SETTINGS["chunking"]
CPT = CFG["chars_per_token"]
TARGET = CFG["target_tokens"] * CPT
MIN_CHARS = CFG["min_tokens"] * CPT
OVERLAP = CFG["overlap_tokens"] * CPT

# strip_code renders headings as their bare text on their own line.
# We re-detect section boundaries heuristically: short Title-Case lines
# followed by a blank line are treated as headings.
HEADING_RE = re.compile(r"^(?P<h>[A-Z][^\n]{0,60})$")


def split_sections(plain: str) -> list[tuple[list[str], str]]:
    """Return list of (heading_path, body_text).

    Because strip_code flattens heading levels, we keep a single-level
    heading path. Good enough for retrieval context; the wikitext parser
    can be swapped in later for true level tracking.
    """
    lines = plain.split("\n")
    sections: list[tuple[list[str], list[str]]] = [(["(intro)"], [])]
    for i, line in enumerate(lines):
        stripped = line.strip()
        nxt_blank = (i + 1 >= len(lines)) or (lines[i + 1].strip() == "")
        prev_blank = (i == 0) or (lines[i - 1].strip() == "")
        looks_heading = (
            stripped
            and len(stripped) <= 60
            and prev_blank and nxt_blank
            and HEADING_RE.match(stripped)
            and not stripped.endswith((".", ",", ":", ";"))
        )
        if looks_heading:
            sections.append(([stripped], []))
        else:
            sections[-1][1].append(line)
    return [(hp, "\n".join(body).strip()) for hp, body in sections
            if "\n".join(body).strip()]


def pack(text: str) -> list[str]:
    """Greedily pack paragraphs up to TARGET chars, overlapping neighbours."""
    paras = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    step = max(1, TARGET - int(OVERLAP))
    for para in paras:
        if len(para) > TARGET:
            # No internal blank-line break to pack around (e.g. a big table
            # or list flattened to plain text) -- hard-slice it so no chunk
            # ever exceeds TARGET and blows the embedding model's context.
            if buf:
                chunks.append(buf)
                buf = ""
            for start in range(0, len(para), step):
                chunks.append(para[start:start + TARGET])
            continue
        if len(buf) + len(para) + 2 <= TARGET or not buf:
            buf = f"{buf}\n\n{para}".strip()
        else:
            chunks.append(buf)
            tail = buf[-int(OVERLAP):]
            buf = f"{tail}\n\n{para}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def chunk_doc(doc: dict) -> list[dict]:
    out: list[dict] = []
    title = doc["title"]
    for heading_path, body in split_sections(doc["plain_text"]):
        for j, piece in enumerate(pack(body)):
            if len(piece) < MIN_CHARS and len(out) > 0:
                # merge tiny trailing fragments into previous chunk
                out[-1]["text"] += "\n\n" + piece
                continue
            header = f"{title} > {' > '.join(heading_path)}"
            out.append({
                "chunk_id": f"page-{doc['page_id']}-"
                            f"{re.sub(r'[^a-z0-9]+', '-', heading_path[0].lower())}-{j:02d}",
                "title": title,
                "heading_path": heading_path,
                "document_type": doc["document_type"],
                "text": f"{header}\n\n{piece}",
                "revision_id": doc["revision_id"],
                "game_version": doc["game_version"],
                "source_path": doc["source_path"],
                "obsolete": doc["obsolete"],
            })
    return out


def run() -> None:
    docs = sorted(p for p in NORM_DIR.glob("*.json"))
    total = 0
    with open(CHUNKS_PATH, "w", encoding="utf-8") as out:
        for df in docs:
            doc = json.loads(df.read_text(encoding="utf-8"))
            if "plain_text" not in doc:
                continue
            for ch in chunk_doc(doc):
                out.write(json.dumps(ch, ensure_ascii=False) + "\n")
                total += 1
    print(f"Wrote {total} chunks to {CHUNKS_PATH}")


if __name__ == "__main__":
    run()
