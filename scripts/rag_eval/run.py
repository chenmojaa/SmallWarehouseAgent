# -*- coding: utf-8 -*-
"""RAG Eval runner.

Reads scripts/rag_eval/golden.jsonl and scores hybrid_search against it.
Reports Recall@K, MRR, and (for smalltalk) the false-citation rate.

Usage:
  cd D:\\one_agent\\backend
  .\\.venv\\Scripts\\python.exe D:\\one_agent\scripts\rag_eval\run.py
  .\\.venv\\Scripts\\python.exe D:\\one_agent\scripts\rag_eval\run.py --top-k 5 --out report.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def load_golden(path: Path) -> list[dict]:
  out = []
  with open(path, "r", encoding="utf-8") as f:
    for line in f:
      line = line.strip()
      if line:
        out.append(json.loads(line))
  return out


def recall_at_k(actual: list[str], expected: list[str]) -> float:
  if not expected:
    return 1.0  # no expectation -> nothing to recall, count as pass
  hit = any(n in expected for n in actual)
  return 1.0 if hit else 0.0


def mrr(actual: list[str], expected: list[str]) -> float:
  if not expected:
    return 1.0
  for i, n in enumerate(actual, 1):
    if n in expected:
      return 1.0 / i
  return 0.0


def has_citations(actual: list[str]) -> bool:
  return len(actual) > 0


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--golden", default=str(Path(__file__).parent / "golden.jsonl"))
  ap.add_argument("--top-k", type=int, default=5)
  ap.add_argument("--out", default=None, help="Markdown report path")
  args = ap.parse_args()

  from app.storage.hybrid import hybrid_search

  cases = load_golden(Path(args.golden))
  if not cases:
    print("golden set is empty; nothing to evaluate")
    return 1

  rows = []
  cat_totals: dict[str, list[float]] = {}
  start = time.perf_counter()
  for c in cases:
    q = c["query"]
    expected = c.get("expect_note_ids") or []
    cat = c.get("category", "uncategorized")
    try:
      hits = hybrid_search(q, top_k=args.top_k)
      actual_note_ids = [str(h.get("note_id")) for h in hits]
      rec = recall_at_k(actual_note_ids, expected)
      m = mrr(actual_note_ids, expected)
      cite = has_citations(actual_note_ids)
    except Exception as e:
      actual_note_ids = []
      rec = m = 0.0
      cite = False
      print(f"[WARN] {q!r} -> {e}")
    rows.append({
      "query": q, "category": cat, "expected": expected,
      "actual": actual_note_ids, "recall_at_k": rec, "mrr": m,
      "cited": cite, "fail": cat == "smalltalk_should_no_cite" and cite,
    })
    cat_totals.setdefault(cat, []).append(rec)
    cat_totals.setdefault(cat + "_mrr", []).append(m)
  elapsed = time.perf_counter() - start

  overall_recall = sum(r["recall_at_k"] for r in rows) / len(rows)
  overall_mrr = sum(r["mrr"] for r in rows) / len(rows)
  smalltalk_rows = [r for r in rows if r["category"] == "smalltalk_should_no_cite"]
  false_cite_rate = (sum(1 for r in smalltalk_rows if r["fail"]) / len(smalltalk_rows)) if smalltalk_rows else 0.0

  # Per-category table
  cat_summary = {}
  for k, vs in cat_totals.items():
    if k.endswith("_mrr"):
      continue
    cat_summary[k] = {
      "count": len(vs),
      "recall_at_k": sum(vs) / len(vs),
      "mrr": sum(cat_totals.get(k + "_mrr", [0])) / len(vs),
    }

  # Build markdown
  lines = ["# RAG Eval Report", ""]
  lines.append("- golden set: %s (%d cases)" % (args.golden, len(cases)))
  lines.append("- top_k: %d" % args.top_k)
  lines.append("- elapsed: %.2fs" % elapsed)
  lines.append("")
  lines.append("## Overall")
  lines.append("")
  lines.append("| metric | value |")
  lines.append("|---|---|")
  lines.append("| Recall@%d | %.3f |" % (args.top_k, overall_recall))
  lines.append("| MRR       | %.3f |" % overall_mrr)
  lines.append("| smalltalk false-citation rate | %.3f |" % false_cite_rate)
  lines.append("")
  lines.append("## By category")
  lines.append("")
  lines.append("| category | count | Recall@%d | MRR |" % args.top_k)
  lines.append("|---|---|---|---|")
  for cat, s in sorted(cat_summary.items()):
    lines.append("| %s | %d | %.3f | %.3f |" % (cat, s["count"], s["recall_at_k"], s["mrr"]))
  lines.append("")
  lines.append("## Per-case")
  lines.append("")
  lines.append("| query | category | expected | actual | R@K | MRR |")
  lines.append("|---|---|---|---|---|---|")
  for r in rows:
    exp = ",".join(r["expected"]) or "-"
    act = ",".join(r["actual"][:3]) + ("..." if len(r["actual"]) > 3 else "")
    lines.append("| %s | %s | %s | %s | %.0f | %.2f |" % (
      r["query"][:40], r["category"], exp, act, r["recall_at_k"], r["mrr"]))
  lines.append("")

  report = "\n".join(lines)
  print(report)
  if args.out:
    Path(args.out).write_text(report, encoding="utf-8")
    print("\n[report] saved to %s" % args.out)
  return 0


if __name__ == "__main__":
  sys.exit(main())