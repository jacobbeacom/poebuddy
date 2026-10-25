"""One-shot pipeline: fetch -> normalize -> chunk -> index.

Run the whole ingestion in order. Use --limit for a quick smoke test that
only pulls a handful of pages.

    python build_index.py --limit 40     # smoke test
    python build_index.py                # full build
"""
from __future__ import annotations

import argparse

from ingestion import fetch_wiki, normalize, chunk, index


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="cap pages fetched (smoke test)")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="reuse existing data/raw/ instead of re-fetching")
    args = ap.parse_args()

    if not args.skip_fetch:
        print("== 1/4 fetch ==")
        fetch_wiki.run(limit=args.limit)
    print("== 2/4 normalize ==")
    normalize.run()
    print("== 3/4 chunk ==")
    chunk.run()
    print("== 4/4 index (embeddings need Ollama running) ==")
    index.run()
    print("\nDone. Launch the UI with:  streamlit run app/report_ui.py")


if __name__ == "__main__":
    main()
