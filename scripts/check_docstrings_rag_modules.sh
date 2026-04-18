#!/usr/bin/env bash
# Enforce docstring coverage on RAG pipeline modules introduced / maintained as a unit.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec python3 -m interrogate \
  backend/services/compression.py \
  backend/services/contextual.py \
  backend/services/grounding.py \
  backend/services/hybrid.py \
  backend/services/mmr.py \
  backend/services/query_transform.py \
  backend/services/reranker.py \
  backend/services/retrieval_pipeline.py \
  backend/services/structured_extract.py \
  backend/services/tracing.py \
  -I \
  -s \
  -n \
  -f 80 \
  "$@"
