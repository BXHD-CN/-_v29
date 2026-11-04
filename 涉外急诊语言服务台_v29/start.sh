#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python -m venv .venv
.venv/bin/python -m pip install --quiet -r requirements.txt
[ -f .env ] || cp .env.example .env
if [ ! -f data/app.db ]; then
  .venv/bin/python scripts/seed_public.py
  .venv/bin/python scripts/build_slices.py
  .venv/bin/python scripts/embed_chunks.py
fi
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
