#!/usr/bin/env bash
# One-shot dev setup for macOS (Apple Silicon).
# Creates the venv, installs dependencies, and seeds .env.
# Safe to re-run.
set -euo pipefail

cd "$(dirname "$0")"

# --- pick a Python 3.11+ interpreter -----------------------------------------
PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  for cand in python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
if [[ -z "$PY" ]]; then
  echo "No Python found. Install with: brew install python@3.11" >&2
  exit 1
fi
echo "Using interpreter: $("$PY" --version) ($PY)"

# --- venv --------------------------------------------------------------------
if [[ ! -d .venv ]]; then
  echo "Creating virtual environment in .venv ..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# --- deps --------------------------------------------------------------------
python -m pip install --upgrade pip
pip install -r requirements.txt

# --- env file ----------------------------------------------------------------
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example (edit model names to match 'ollama list')."
fi

# --- friendly checks ---------------------------------------------------------
echo
echo "Checking for Ollama ..."
if command -v ollama >/dev/null 2>&1; then
  echo "  ollama found: $(ollama --version 2>/dev/null | head -1)"
  if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "  Ollama server is running."
  else
    echo "  Ollama installed but server not responding — open the Ollama app once."
  fi
else
  echo "  Ollama NOT found. Install: brew install --cask ollama  (or https://ollama.com)"
fi

cat <<'DONE'

Setup complete. Next steps:
  1. Pull models (confirm names in 'ollama list' first):
       ollama pull llama3.1:8b-instruct-q4_K_M
       ollama pull nomic-embed-text
  2. Smoke-build the index (fetches ~40 wiki pages):
       python build_index.py --limit 40
  3. Launch the UI:
       streamlit run app/report_ui.py

In VS Code you can also use Run and Debug (the launch configs) or
Terminal > Run Task... for any of the above.
DONE
