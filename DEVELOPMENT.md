# Development guide

Everything needed to open this in VS Code and start iterating immediately.

## First time (about 3 minutes)

1. **Install VS Code** — https://code.visualstudio.com
2. **Install Ollama** — `brew install --cask ollama` (or https://ollama.com),
   then open the app once so its local server starts.
3. **Open this folder in VS Code:** `File > Open Folder…` → select
   `poebuddy`.
4. VS Code will pop up *"This workspace has extension recommendations"* →
   click **Install All** (Python, Pylance, debugpy, Ruff, YAML).
5. Open a terminal in VS Code (`` Ctrl+` ``) and run:

   ```bash
   ./setup.sh
   ```

   This creates `.venv`, installs everything from `requirements.txt`, and
   copies `.env.example` → `.env`. It also tells you whether Ollama is running.

6. **Select the interpreter** (usually automatic): `Cmd+Shift+P` →
   *Python: Select Interpreter* → choose `./.venv/bin/python`.
   `settings.json` already points here, so new terminals auto-activate it.

7. **Pull the models** (confirm names in `ollama list` first):

   ```bash
   ollama pull llama3.1:8b-instruct-q4_K_M
   ollama pull nomic-embed-text
   ```

You're ready.

## Running things

Two equivalent ways — pick whichever you like.

### Run and Debug panel (breakpoints work)

Open the **Run and Debug** panel (the ▶🐞 icon) and pick a config from the
dropdown, then press F5:

| Config | What it does |
|---|---|
| **Streamlit: UI** | Launches the build-report UI with the debugger attached |
| **Build index: smoke (--limit 40)** | Fetch ~40 pages → normalize → chunk → index |
| **Build index: full** | Full ingestion (slow; embeds every chunk locally) |
| **Init DuckDB** | Creates the structured tables |
| **Python: current file** | Debug whatever file is focused |

### Command Palette → Run Task (no debugger, just runs)

`Cmd+Shift+P` → *Tasks: Run Task* → choose Setup / Build / Run UI / Refresh
prices. `Setup` is the default build task (`Cmd+Shift+B`).

## Where to set breakpoints while tuning

- **Retrieval quality** — `app/retrieval.py`, in `search()`. Break after
  `reciprocal_rank_fusion` and after `rerank` to inspect what the LLM is about
  to receive. This is where most answer-quality issues live.
- **Wrong document classification** — `ingestion/normalize.py`, `classify()`.
  Watch `TYPE_RULES` against the real category names in your fetched pages.
- **Infobox → structured fields** — `ingestion/index.py`, `build_structured()`.
  Break here and inspect a `doc["infobox"]` dict to map real field names.
- **Build analysis rules** — `app/analysis.py`. Each check is a small
  function returning `Finding`s; benchmark thresholds live in
  `config/settings.yaml` under `analysis:`.
- **PoB import** — `app/pob_import.py`, `parse_pob_xml()`. Break here to
  inspect the raw XML fields against what lands on the `Build` model.
- **Archetype / role detection** — `app/archetype.py`, `detect_archetype()`.
  Break here when a build is misclassified (DoT vs hit, support vs carry).
- **Report assembly** — `app/report.py`, `generate_report()`. Break before
  `llm.chat` to see the findings JSON + wiki excerpts the coach notes use.

## Fast iteration tips

- You don't need to re-fetch to re-tune retrieval or chunking. Re-run just the
  later stages: `python build_index.py --skip-fetch` reuses `data/raw/`.
- `app/analysis.py` checks run on a plain `Build` object — no wiki data or
  Ollama needed, good for TDD on the deterministic parts.
- Ruff formats on save. To lint the whole tree: `ruff check .`
- Everything binds to `localhost`. The only outbound calls are the wiki fetch
  (ingestion), pasted pobb.in links, and cached poe.ninja prices.

## Using Claude Code alongside VS Code (optional)

If you want an AI pair-programmer that can edit files *and* run your commands
in this repo, install Claude Code and launch it from the VS Code terminal:

```bash
npm install -g @anthropic-ai/claude-code   # one time
claude                                       # from the project root
```

It sees the real Ollama errors and can close the edit → run → fix loop locally,
which the desktop app can't do from its sandbox.

## Troubleshooting

- **`streamlit: command not found`** — the venv isn't active. Run
  `source .venv/bin/activate` or reopen the VS Code terminal.
- **Connection refused to `:11434`** — Ollama isn't running. Open the app.
- **`model 'x' not found`** — the name in `.env` doesn't match `ollama list`.
- **Qdrant / import errors on first index** — make sure `setup.sh` finished and
  the interpreter is `./.venv/bin/python` (bottom-left status bar in VS Code).
- **Embedding dimension mismatch** — if you changed the embedding model, set
  `embedding.dim` in `config/settings.yaml` to that model's output size, then
  rebuild the index.
```
