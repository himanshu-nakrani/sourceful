"""Golden-set retrieval evaluation harness.

Runs under `pytest -m eval`. The harness:
  1. Ingests each golden document as a real user (via the API),
  2. Processes the job with deterministic fake embeddings so results are
     reproducible across machines and CI providers,
  3. Queries the retrieval pipeline for each golden question,
  4. Computes recall@K on expected excerpts,
  5. Writes a JSON report to `docs/eval/last_run.json` and prints a
     summary so trends can be diffed against `docs/eval/baseline.json`.

The fake embedding is a bag-of-tokens TF vector projected into a
fixed-length space. This is intentionally simple: it's stable and gives
the dense lane a real signal to retrieve against, while keeping the
harness fully hermetic (no external API calls).

Optional RAGAS integration (task 1.14):
  When the `ragas` package is installed, `test_ragas_metrics_on_golden_set`
  computes faithfulness, answer_relevancy, and context_precision alongside
  our deterministic recall@K. The test auto-skips when `ragas` is absent
  so no deployment breaks.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.jobs import claim_next_job, process_job

GOLDEN_PATH = Path(__file__).parent / "golden.json"
GOLDEN_V2_PATH = Path(__file__).parent / "golden_v2.json"
REPORT_DIR = Path(__file__).resolve().parents[3] / "docs" / "eval"
REPORT_PATH = REPORT_DIR / "last_run.json"
REPORT_V2_PATH = REPORT_DIR / "last_run_v2.json"
REPORT_RAGAS_PATH = REPORT_DIR / "last_run_ragas.json"

HEADERS = {"X-Client-Session": "eval-session"}
PROVIDER_HEADERS = {**HEADERS, "X-Provider-Api-Key": "eval-provider-key"}

EMBED_DIM = 64


def _token_vector(text: str) -> list[float]:
    vec = [0.0] * EMBED_DIM
    for token in text.lower().split():
        # Deterministic bucket via sha1 so the same token always lands in
        # the same dimension regardless of Python's hash seed.
        bucket = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16) % EMBED_DIM
        vec[bucket] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _login(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert response.status_code == 200


def _ingest_and_process(client, sections: list[str], filename: str) -> str:
    body = "\n\n".join(sections).encode("utf-8")
    response = client.post(
        "/api/ingest",
        data={"provider": "openai"},
        files={"file": (filename, body, "text/plain")},
        headers=PROVIDER_HEADERS,
    )
    assert response.status_code == 202, response.text
    payload = response.json()

    async def fake_embed_texts(provider, api_key, model, texts):
        return [_token_vector(t) for t in texts]

    with patch("backend.services.jobs.embed_texts", new=AsyncMock(side_effect=fake_embed_texts)):
        # The same file contents are deduplicated across items, so a job
        # may already have been processed for this checksum. Only process
        # when there's actually a queued job waiting.
        job = asyncio.run(claim_next_job())
        if job is not None:
            asyncio.run(process_job(job))
    return payload["document_id"]


def _run_recall_eval(
    client, items: list[dict], *, top_k: int = 3
) -> tuple[list[dict], int]:
    """Shared recall evaluation logic used by both v1 and v2 golden-set tests.

    Returns (results_list, hits_count).
    """
    async def fake_embed_query(provider, api_key, model, text):
        return _token_vector(text)

    results: list[dict] = []
    hits = 0

    with patch(
        "backend.routers.chat.embed_query",
        new=AsyncMock(side_effect=fake_embed_query),
    ), patch(
        "backend.routers.chat.create_openai_text",
        new=AsyncMock(return_value="(stubbed answer)"),
    ):
        for item in items:
            # v2 items have document info as { "document": "<key>" }, while
            # v1 items have inline { "document": { "sections": [...], "filename": ... } }.
            doc_info = item.get("document")
            if isinstance(doc_info, dict):
                doc_id = _ingest_and_process(
                    client,
                    doc_info["sections"],
                    doc_info["filename"],
                )
            else:
                # For v2 format, the caller should pre-resolve sections.
                # This path only hits for v1 data.
                raise ValueError("Cannot resolve document info from golden item")

            chat_response = client.post(
                "/api/chat",
                headers=PROVIDER_HEADERS,
                json={
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "question": item["question"],
                    "document_id": doc_id,
                    "top_k": top_k,
                },
            )
            assert chat_response.status_code == 200, chat_response.text
            body = chat_response.json()
            sources = body.get("sources", [])
            expected = item["expected_substring"].lower()
            hit = any(expected in (s.get("excerpt") or "").lower() for s in sources)
            result_item = {
                "id": item["id"],
                "question": item["question"],
                "expected_substring": item["expected_substring"],
                "hit": hit,
                "top_excerpts": [s.get("excerpt", "")[:120] for s in sources],
                "answer": body.get("content", ""),
            }
            if item.get("category"):
                result_item["category"] = item["category"]
            results.append(result_item)
            if hit:
                hits += 1

    return results, hits


@pytest.mark.eval
def test_retrieval_recall_on_golden_set(client):
    if os.environ.get("SKIP_EVAL") == "1":
        pytest.skip("SKIP_EVAL=1 set")

    _login(client)
    data = json.loads(GOLDEN_PATH.read_text())
    items = data["items"]
    started = time.perf_counter()

    results, hits = _run_recall_eval(client, items)

    recall = hits / max(1, len(items))
    elapsed = time.perf_counter() - started

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "recall_at_k": recall,
        "hits": hits,
        "total": len(items),
        "elapsed_seconds": round(elapsed, 3),
        "items": results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\n[eval] recall@3 = {recall:.2f} ({hits}/{len(items)}) in {elapsed:.2f}s")
    print(f"[eval] report written to {REPORT_PATH}")

    # Phase 0 baseline bar — intentionally loose; tightened in later phases.
    assert recall >= 0.66, f"Retrieval recall@3 regressed: {recall:.2f} < 0.66"


@pytest.mark.eval
def test_retrieval_recall_on_golden_v2(client):
    """Expanded golden-set eval (31 items across policy/technical/numeric/multi-hop)."""
    if os.environ.get("SKIP_EVAL") == "1":
        pytest.skip("SKIP_EVAL=1 set")
    if not GOLDEN_V2_PATH.exists():
        pytest.skip("golden_v2.json not found")

    _login(client)
    data = json.loads(GOLDEN_V2_PATH.read_text())
    documents = data["documents"]
    golden_items = data["items"]

    # Resolve v2 document references into the inline format our helper expects.
    items: list[dict] = []
    for raw_item in golden_items:
        doc_key = raw_item["document"]
        doc_def = documents[doc_key]
        items.append({
            **raw_item,
            "document": {
                "sections": doc_def["sections"],
                "filename": doc_def["filename"],
            },
        })

    started = time.perf_counter()
    results, hits = _run_recall_eval(client, items, top_k=5)
    recall = hits / max(1, len(items))
    elapsed = time.perf_counter() - started

    # Category breakdown
    categories: dict[str, dict] = {}
    for r in results:
        cat = r.get("category", "uncategorized")
        entry = categories.setdefault(cat, {"hits": 0, "total": 0})
        entry["total"] += 1
        if r["hit"]:
            entry["hits"] += 1

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "recall_at_k": recall,
        "hits": hits,
        "total": len(items),
        "elapsed_seconds": round(elapsed, 3),
        "categories": {
            cat: {**entry, "recall": entry["hits"] / max(1, entry["total"])}
            for cat, entry in categories.items()
        },
        "items": results,
    }
    REPORT_V2_PATH.write_text(json.dumps(report, indent=2))
    print(f"\n[eval-v2] recall@5 = {recall:.2f} ({hits}/{len(items)}) in {elapsed:.2f}s")
    for cat, entry in sorted(categories.items()):
        cat_recall = entry["hits"] / max(1, entry["total"])
        print(f"  [{cat}] recall={cat_recall:.2f} ({entry['hits']}/{entry['total']})")
    print(f"[eval-v2] report written to {REPORT_V2_PATH}")

    # Phase 1 bar on expanded set — loose until acceptance criteria are met.
    assert recall >= 0.50, f"Retrieval recall@5 (v2) regressed: {recall:.2f} < 0.50"


# ---- Task 1.14: RAGAS integration (optional) ---------------------------

@pytest.mark.eval
def test_ragas_metrics_on_golden_set(client):
    """Compute RAGAS faithfulness, answer_relevancy, and context_precision.

    Auto-skips when the `ragas` package is not installed. Uses the v2
    expanded golden set to produce a meaningful evaluation. The LLM
    answer is stubbed (same as the recall tests), so RAGAS scores here
    measure retrieval quality + prompt faithfulness, not real LLM output.
    To get meaningful faithfulness scores, set RAGAS_LLM_PROVIDER env var
    and run with a real API key.
    """
    if os.environ.get("SKIP_EVAL") == "1":
        pytest.skip("SKIP_EVAL=1 set")

    try:
        from ragas import evaluate  # type: ignore
        from ragas.metrics import (  # type: ignore
            answer_relevancy,
            context_precision,
            faithfulness,
        )
        from datasets import Dataset  # type: ignore
    except ImportError:
        pytest.skip(
            "ragas and/or datasets not installed — "
            "install with `pip install ragas datasets` to enable"
        )

    golden_path = GOLDEN_V2_PATH if GOLDEN_V2_PATH.exists() else GOLDEN_PATH
    _login(client)
    data = json.loads(golden_path.read_text())

    # Build items list (handle both v1 and v2 formats)
    if "documents" in data:
        documents = data["documents"]
        golden_items = data["items"]
        items = []
        for raw_item in golden_items:
            doc_key = raw_item["document"]
            doc_def = documents[doc_key]
            items.append({
                **raw_item,
                "document": {
                    "sections": doc_def["sections"],
                    "filename": doc_def["filename"],
                },
            })
    else:
        items = data["items"]

    started = time.perf_counter()
    results, _hits = _run_recall_eval(client, items, top_k=5)
    elapsed = time.perf_counter() - started

    # Build the RAGAS-compatible dataset.
    # Each row needs: question, answer, contexts, ground_truth
    ragas_rows: list[dict] = []
    for item, result in zip(items, results):
        question = item["question"]
        answer = result.get("answer", "(stubbed answer)")
        # Contexts are the top retrieved excerpts
        contexts = result.get("top_excerpts", [])
        # Ground truth is the expected substring/section from which it came
        ground_truth = item["expected_substring"]
        ragas_rows.append({
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": ground_truth,
        })

    dataset = Dataset.from_list(ragas_rows)

    metrics = [faithfulness, answer_relevancy, context_precision]
    try:
        ragas_result = evaluate(dataset, metrics=metrics)
    except Exception as exc:
        # RAGAS may need a configured LLM to compute some metrics. If no
        # LLM is available, surface the error as a skip rather than a fail.
        pytest.skip(f"RAGAS evaluation failed (likely missing LLM config): {exc}")

    # Convert to a plain dict for JSON serialization.
    scores: dict[str, float | None] = {}
    for metric in metrics:
        name = metric.name if hasattr(metric, "name") else str(metric)
        val = ragas_result.get(name)
        scores[name] = round(float(val), 4) if val is not None else None

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ragas_report = {
        "elapsed_seconds": round(elapsed, 2),
        "total_items": len(ragas_rows),
        "scores": scores,
    }
    REPORT_RAGAS_PATH.write_text(json.dumps(ragas_report, indent=2))
    print(f"\n[ragas] scores: {scores}")
    print(f"[ragas] report written to {REPORT_RAGAS_PATH}")

    # Soft assertion — don't block CI on RAGAS scores yet. Log only.
    # Phase 1 acceptance criteria: faithfulness >= 0.85. We'll enforce
    # this once we have real LLM answers running through the eval.
    f_score = scores.get("faithfulness")
    if f_score is not None:
        print(f"[ragas] faithfulness = {f_score:.2f} (target >= 0.85)")
    ar_score = scores.get("answer_relevancy")
    if ar_score is not None:
        print(f"[ragas] answer_relevancy = {ar_score:.2f}")
    cp_score = scores.get("context_precision")
    if cp_score is not None:
        print(f"[ragas] context_precision = {cp_score:.2f}")
