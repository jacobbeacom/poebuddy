"""Hybrid retrieval: dense (Qdrant) + BM25, fused with RRF, then reranked.

Public entry point:  search(question, filters, ...) -> list[chunk dict]
"""
from __future__ import annotations

import pickle
import re
from functools import lru_cache
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from rank_bm25 import BM25Okapi

from app.settings import SETTINGS
from app.llm import embed_one

RCFG = SETTINGS["retrieval"]
QCFG = SETTINGS["qdrant"]
BM25_PATH = Path(SETTINGS["paths"]["qdrant_path"]).parent / "bm25.pkl"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


@lru_cache(maxsize=1)
def _qdrant() -> QdrantClient:
    return QdrantClient(path=SETTINGS["paths"]["qdrant_path"])


@lru_cache(maxsize=1)
def _bm25():
    data = pickle.loads(BM25_PATH.read_bytes())
    return BM25Okapi(data["corpus"]), data["payload"]


@lru_cache(maxsize=1)
def _reranker():
    # imported lazily; heavy dependency
    from sentence_transformers import CrossEncoder
    return CrossEncoder(RCFG["reranker_model"])


def _qdrant_filter(filters: dict | None) -> Filter | None:
    if not filters:
        return None
    must = []
    for key, val in filters.items():
        if val is None:
            continue
        must.append(FieldCondition(key=key, match=MatchValue(value=val)))
    return Filter(must=must) if must else None


def dense_search(question: str, filters: dict | None, limit: int) -> list[dict]:
    vec = embed_one(question)
    hits = _qdrant().query_points(
        collection_name=QCFG["collection"],
        query=vec,
        query_filter=_qdrant_filter(filters),
        limit=limit,
        with_payload=True,
    ).points
    return [dict(h.payload, _score=h.score) for h in hits]


def keyword_search(question: str, filters: dict | None, limit: int) -> list[dict]:
    bm25, payload = _bm25()
    scores = bm25.get_scores(_tokenize(question))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    out: list[dict] = []
    for i in ranked:
        p = payload[i]
        if filters and not _passes(p, filters):
            continue
        out.append(dict(p, _score=float(scores[i])))
        if len(out) >= limit:
            break
    return out


def _passes(payload: dict, filters: dict) -> bool:
    for k, v in filters.items():
        if v is None:
            continue
        if payload.get(k) != v:
            return False
    return True


def reciprocal_rank_fusion(*rankings: list[dict]) -> list[dict]:
    k = RCFG["rrf_k"]
    scores: dict[str, float] = {}
    lookup: dict[str, dict] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            cid = item["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            lookup[cid] = item
    fused = sorted(lookup.values(), key=lambda it: scores[it["chunk_id"]], reverse=True)
    for it in fused:
        it["_rrf"] = scores[it["chunk_id"]]
    return fused


def rerank(question: str, candidates: list[dict], top_n: int) -> list[dict]:
    if not candidates:
        return []
    try:
        model = _reranker()
    except Exception:  # noqa: BLE001 -- reranker optional; fall back to RRF order
        return candidates[:top_n]
    pairs = [(question, c["text"]) for c in candidates]
    scores = model.predict(pairs)
    for c, s in zip(candidates, scores):
        c["_rerank"] = float(s)
    return sorted(candidates, key=lambda c: c["_rerank"], reverse=True)[:top_n]


def search(question: str, filters: dict | None = None) -> list[dict]:
    """Full hybrid pipeline -> final_top_k chunks for the LLM."""
    # Default: exclude obsolete unless caller explicitly overrides.
    filters = {"obsolete": False, **(filters or {})}
    dense = dense_search(question, filters, RCFG["dense_top_k"])
    lexical = keyword_search(question, filters, RCFG["bm25_top_k"])
    fused = reciprocal_rank_fusion(dense, lexical)
    reranked = rerank(question, fused[:RCFG["rerank_top_n"]], RCFG["rerank_top_n"])
    min_score = RCFG.get("min_rerank_score")
    if min_score is not None:
        # Candidates without a "_rerank" score (reranker unavailable) are kept
        # as-is; we can't judge relevance without a score to filter on.
        reranked = [c for c in reranked if c.get("_rerank", min_score) >= min_score]
    return reranked[:RCFG["final_top_k"]]
