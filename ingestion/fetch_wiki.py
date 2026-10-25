"""Responsible MediaWiki fetcher for the PoE2 wiki.

Uses the MediaWiki action API (list=allpages + revisions) instead of
scraping rendered HTML. Caches raw wikitext to data/raw/ keyed by page
id, and skips pages whose content hash is unchanged.

Run:
    python -m ingestion.fetch_wiki            # all main-namespace pages
    python -m ingestion.fetch_wiki --limit 50 # smoke test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Iterator

import requests

from app.settings import SETTINGS

WIKI = SETTINGS["wiki"]
RAW_DIR = Path(SETTINGS["paths"]["raw_dir"])


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": WIKI["user_agent"]})
    return s


def _get(session: requests.Session, params: dict) -> dict:
    params = {**params, "format": "json"}
    last_err: Exception | None = None
    for attempt in range(WIKI["max_retries"]):
        try:
            resp = session.get(WIKI["api_url"], params=params, timeout=(10, 60))
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 15.0 * (2 ** attempt)
                print(f"  rate-limited (429); backing off {delay:.0f}s "
                      f"(attempt {attempt + 1}/{WIKI['max_retries']})")
                time.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(WIKI["request_delay_seconds"] * (attempt + 1))
    raise RuntimeError(
        f"API request failed after {WIKI['max_retries']} retries "
        f"(last error: {last_err}). If this was a 429, the wiki's "
        "anti-bot protection likely needs longer to cool down than a "
        "single run can wait out -- pause for several minutes and rerun; "
        "already-fetched pages are cached to data/raw/ and won't be "
        "re-downloaded once their content is unchanged."
    )


def list_page_titles(session: requests.Session,
                     limit: int | None = None) -> Iterator[dict]:
    """Yield {'pageid', 'title', 'ns'} for every page in configured namespaces."""
    count = 0
    for ns in WIKI["namespaces"]:
        apcontinue = None
        while True:
            params = {
                "action": "query",
                "list": "allpages",
                "apnamespace": ns,
                "aplimit": "max",
            }
            if apcontinue:
                params["apcontinue"] = apcontinue
            data = _get(session, params)
            for page in data.get("query", {}).get("allpages", []):
                yield {"pageid": page["pageid"], "title": page["title"], "ns": ns}
                count += 1
                if limit and count >= limit:
                    return
            cont = data.get("continue", {})
            apcontinue = cont.get("apcontinue")
            if not apcontinue:
                break
            time.sleep(WIKI["request_delay_seconds"])


def fetch_revisions(session: requests.Session, page_ids: list[int]) -> dict[int, dict]:
    """Fetch latest revision wikitext + metadata for a batch of page ids."""
    params = {
        "action": "query",
        "prop": "revisions|categories",
        "pageids": "|".join(str(p) for p in page_ids),
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "cllimit": "max",
    }
    data = _get(session, params)
    out: dict[int, dict] = {}
    for pid, page in data.get("query", {}).get("pages", {}).items():
        revs = page.get("revisions", [])
        if not revs:
            continue
        slot = revs[0].get("slots", {}).get("main", {})
        cats = [c["title"] for c in page.get("categories", [])]
        out[int(pid)] = {
            "page_id": page["pageid"],
            "title": page["title"],
            "namespace": page["ns"],
            "revision_id": revs[0]["revid"],
            "timestamp": revs[0]["timestamp"],
            "categories": cats,
            "raw_wikitext": slot.get("*", ""),
        }
    return out


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _raw_path(page_id: int) -> Path:
    return RAW_DIR / f"{page_id}.json"


def _unchanged(page_id: int, new_hash: str) -> bool:
    p = _raw_path(page_id)
    if not p.exists():
        return False
    try:
        existing = json.loads(p.read_text(encoding="utf-8"))
        return existing.get("content_hash") == new_hash
    except Exception:  # noqa: BLE001
        return False


def run(limit: int | None = None) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = _session()
    titles = list(list_page_titles(session, limit=limit))
    print(f"Discovered {len(titles)} pages. Fetching revisions...")

    batch = WIKI["batch_size"]
    fetched = skipped = 0
    for i in range(0, len(titles), batch):
        ids = [t["pageid"] for t in titles[i:i + batch]]
        revs = fetch_revisions(session, ids)
        for pid, rec in revs.items():
            h = _content_hash(rec["raw_wikitext"])
            if _unchanged(pid, h):
                skipped += 1
                continue
            rec["content_hash"] = h
            rec["source"] = "wiki"
            rec["source_path"] = "/wiki/" + rec["title"].replace(" ", "_")
            rec["retrieved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _raw_path(pid).write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            fetched += 1
        print(f"  {i + len(ids)}/{len(titles)} processed "
              f"(new/updated={fetched}, unchanged={skipped})")
        time.sleep(WIKI["request_delay_seconds"])

    print(f"Done. {fetched} written, {skipped} unchanged. Raw dir: {RAW_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="cap number of pages (smoke test)")
    args = ap.parse_args()
    run(limit=args.limit)
