"""Build the search index from chunks.jsonl.

Creates three artifacts:
  1. Embedded Qdrant collection (dense vectors + payload metadata)
  2. A BM25 keyword index (pickled tokenized corpus)
  3. Structured DuckDB records for infobox-derived facts

Embeddings come from the local Ollama embedding model, so nothing leaves
your machine.

Run:  python -m ingestion.index
"""
from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.settings import SETTINGS
from app.llm import embed_texts
from app import db

NORM_DIR = Path(SETTINGS["paths"]["normalized_dir"])
CHUNKS_PATH = NORM_DIR / "chunks.jsonl"
BM25_PATH = Path(SETTINGS["paths"]["qdrant_path"]).parent / "bm25.pkl"

QCFG = SETTINGS["qdrant"]
ECFG = SETTINGS["embedding"]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def load_chunks() -> list[dict]:
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(
            f"{CHUNKS_PATH} missing. Run ingestion.chunk first."
        )
    with open(CHUNKS_PATH, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_qdrant(chunks: list[dict]) -> None:
    client = QdrantClient(path=SETTINGS["paths"]["qdrant_path"])  # embedded
    client.recreate_collection(
        collection_name=QCFG["collection"],
        vectors_config=VectorParams(
            size=ECFG["dim"], distance=Distance[QCFG["distance"].upper()]
        ),
    )
    batch = ECFG["batch_size"]
    points: list[PointStruct] = []
    for i in range(0, len(chunks), batch):
        window = chunks[i:i + batch]
        vecs = embed_texts([c["text"] for c in window])
        for j, (c, v) in enumerate(zip(window, vecs)):
            points.append(PointStruct(
                id=i + j,
                vector=v,
                payload={
                    "chunk_id": c["chunk_id"],
                    "title": c["title"],
                    "heading_path": c["heading_path"],
                    "document_type": c["document_type"],
                    "text": c["text"],
                    "revision_id": c["revision_id"],
                    "game_version": c["game_version"],
                    "source_path": c["source_path"],
                    "obsolete": c["obsolete"],
                },
            ))
        client.upsert(collection_name=QCFG["collection"], points=points)
        points = []
        print(f"  embedded {min(i + batch, len(chunks))}/{len(chunks)}")
    print(f"Qdrant collection '{QCFG['collection']}' built (embedded).")


def build_bm25(chunks: list[dict]) -> None:
    corpus = [_tokenize(c["text"]) for c in chunks]
    payload = [{k: c[k] for k in (
        "chunk_id", "title", "heading_path", "document_type",
        "text", "revision_id", "game_version", "source_path", "obsolete")}
        for c in chunks]
    BM25_PATH.write_bytes(pickle.dumps({"corpus": corpus, "payload": payload}))
    print(f"BM25 corpus written to {BM25_PATH} ({len(corpus)} docs).")


def build_structured() -> None:
    """Load infobox fields into DuckDB tables (best-effort mapping)."""
    db.init_db()
    con = db.connect()
    try:
        skills, mods, items, passives, pages = [], [], [], [], []
        for df in sorted(NORM_DIR.glob("*.json")):
            if df.name == "chunks.jsonl":
                continue
            doc = json.loads(df.read_text(encoding="utf-8"))
            ib = doc.get("infobox", {})
            gv, sp, rev = doc["game_version"], doc["source_path"], doc["revision_id"]
            pages.append((doc["page_id"], doc["title"], rev, doc["namespace"],
                          doc["document_type"], json.dumps(doc["categories"]),
                          doc["source"], sp, doc["retrieved_at"], gv,
                          doc["content_hash"], doc["obsolete"]))
            dt = doc["document_type"]
            if dt in ("skill", "support"):
                skills.append((doc["title"], doc["title"],
                               _int(ib.get("level")), json.dumps(_tags(ib)),
                               _int(ib.get("required_level")),
                               _float(ib.get("damage_effectiveness")),
                               _float(ib.get("mana_cost")), gv, rev, sp))
            elif dt in ("item", "unique_item"):
                items.append((doc["title"], doc["title"], ib.get("class", ""),
                              dt == "unique_item", _int(ib.get("required_level")),
                              _int(ib.get("required_strength")),
                              _int(ib.get("required_dexterity")),
                              _int(ib.get("required_intelligence")),
                              json.dumps(ib.get("implicits", "")),
                              json.dumps(ib.get("explicits", "")), gv, sp))
            elif dt == "passive":
                passives.append((doc["title"], doc["title"],
                                 ib.get("node_type", "normal"),
                                 json.dumps(ib), gv, sp))
        con.executemany("INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", pages)
        con.executemany("INSERT INTO skills VALUES (?,?,?,?,?,?,?,?,?,?)", skills)
        con.executemany("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", items)
        con.executemany("INSERT INTO passives VALUES (?,?,?,?,?,?)", passives)
        print(f"DuckDB loaded: {len(pages)} pages, {len(skills)} skills, "
              f"{len(items)} items, {len(passives)} passives.")
    finally:
        con.close()


def _tags(ib: dict) -> list[str]:
    raw = ib.get("tags") or ib.get("gem_tags") or ""
    return [t.strip() for t in re.split(r"[,;]", raw) if t.strip()]


def _int(v):
    try:
        return int(re.sub(r"[^0-9-]", "", str(v)))
    except Exception:  # noqa: BLE001
        return None


def _float(v):
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v)))
    except Exception:  # noqa: BLE001
        return None


def run() -> None:
    chunks = load_chunks()
    print(f"Indexing {len(chunks)} chunks...")
    build_qdrant(chunks)
    build_bm25(chunks)
    build_structured()
    print("Index build complete.")


if __name__ == "__main__":
    run()
