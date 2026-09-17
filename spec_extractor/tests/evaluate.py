#!/usr/bin/env python3
"""
evaluate.py - score spec_extractor.py output against the synthetic ground truth.

    python tests/evaluate.py RESULTS_FOLDER [--corpus tests/corpus] [--details]

For every <name>_extracted.xlsx in RESULTS_FOLDER whose name starts with specA/specB/specC/specD,
the matching <doc>_groundtruth.json is loaded and these numbers are printed:

  requirements  recall     share of true requirements that were found (text similarity >= 0.90)
                precision  share of extracted requirement rows that are true requirements
                exact      share of found requirements whose text matches character-for-character
                CER        character error rate of the found requirement texts (0 = perfect)
                keyword    share of found requirements with the right keyword
                doc ref    share of found requirements with the right paragraph number / ID
  captions      recall / precision
  tables        found (caption match or best overlap), cell accuracy, and whether the table
                row carries its own caption (not a neighbouring table's)
  review flags  "false flags" = correct rows marked Needs Review. A row whose only reason is a
                deliberate structural check (text joined across a page break, a notice repeated in
                every page footer) is not counted.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import openpyxl
from rapidfuzz.distance import Levenshtein

BULLETS = "•·◦*"
STRUCTURAL_REASONS = ("continues across pages", "Repeated in the page")   # deliberate checks, not OCR suspicions


def norm(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    t = "".join(ch for ch in t if ch not in BULLETS)
    return re.sub(r"\s+", " ", t).strip()


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a and not b:
        return 1.0
    return 1.0 - Levenshtein.distance(a, b) / max(len(a), len(b), 1)


def ref_ok(truth_id: str, found_ref: str) -> bool:
    """'3.2.1.3' matches '3.2.1.3 a'; '(1)' matches '1'; an empty truth id matches anything."""
    t = re.sub(r"[()\[\]:]", "", truth_id or "").strip().lower()
    f = re.sub(r"[()\[\]:]", "", found_ref or "").strip().lower()
    return not t or f == t or f.startswith(t + " ")


def ocr_flagged(row: dict) -> bool:
    reasons = [r.strip() for r in re.split(r"[\n;]", str(row.get("Review Reasons") or "")) if r.strip()]
    return row.get("Needs Review") == "Yes" and any(not any(k in r for k in STRUCTURAL_REASONS) for r in reasons or ["?"])


def cer(truth: str, found: str) -> float:
    t, f = norm(truth), norm(found)
    return Levenshtein.distance(t, f) / max(len(t), 1)


def read_items(xlsx: Path) -> list:
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb["Extracted Items"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    items = [dict(zip(header, r)) for r in rows[1:] if any(v is not None for v in r)]
    tables = {}
    for name in wb.sheetnames:
        if name in ("Extracted Items", "Full Text", "Page Quality", "Run Info"):
            continue
        sh = wb[name]
        grid = [list(r) for r in sh.iter_rows(min_row=5, values_only=True)]
        grid = [["" if v is None else str(v) for v in r] for r in grid if any(v not in (None, "") for v in r)]
        grid = [r for r in grid if not r[0].startswith("Yellow cells")]
        tables[name] = grid
    return items, tables


def greedy_match(truths: list, founds: list, key_t, key_f, threshold: float) -> list:
    pairs = []
    for ti, t in enumerate(truths):
        for fi, f in enumerate(founds):
            s = similarity(key_t(t), key_f(f))
            if s >= threshold:
                pairs.append((s, ti, fi))
    pairs.sort(reverse=True)
    used_t, used_f, matches = set(), set(), []
    for s, ti, fi in pairs:
        if ti not in used_t and fi not in used_f:
            used_t.add(ti)
            used_f.add(fi)
            matches.append((ti, fi, s))
    return matches


def evaluate(xlsx: Path, gt: dict, details: bool) -> dict:
    items, tables = read_items(xlsx)
    reqs = [i for i in items if i.get("Type") == "Requirement"]
    caps = [i for i in items if i.get("Type") in ("Table Caption", "Figure Caption")]
    tabs = [i for i in items if i.get("Type") == "Table"]
    gt_reqs = gt["requirements"]
    m = greedy_match(gt_reqs, reqs, lambda t: t["text"], lambda f: f.get("Content") or "", 0.90)
    matched_t = {ti for ti, _, _ in m}
    matched_f = {fi for _, fi, _ in m}
    exact = sum(1 for ti, fi, _ in m if norm(gt_reqs[ti]["text"]) == norm(reqs[fi]["Content"]))
    cers = [cer(gt_reqs[ti]["text"], reqs[fi]["Content"]) for ti, fi, _ in m]
    kw_ok = sum(1 for ti, fi, _ in m if (reqs[fi].get("Keyword") or "").lower() == gt_reqs[ti]["keyword"])
    ref_errors = [(ti, fi) for ti, fi, _ in m if not ref_ok(gt_reqs[ti].get("doc_id", ""), reqs[fi].get("Doc Ref") or "")]
    mandatory = [i for i, r in enumerate(gt_reqs) if r["category"] == "mandatory"]
    res = {
        "req_total": len(gt_reqs), "req_found": len(m), "req_extracted": len(reqs),
        "req_recall": len(m) / max(len(gt_reqs), 1), "req_precision": len(m) / max(len(reqs), 1),
        "req_exact": exact / max(len(m), 1), "req_cer": sum(cers) / max(len(cers), 1),
        "keyword_acc": kw_ok / max(len(m), 1), "ref_errors": len(ref_errors),
        "mandatory_recall": sum(1 for i in mandatory if i in matched_t) / max(len(mandatory), 1),
        "flagged": sum(1 for r in reqs if r.get("Needs Review") == "Yes"),
    }
    # review-flag quality: does "Needs Review" point at the rows whose text is actually wrong?
    wrong = [(ti, fi) for ti, fi, _ in m if norm(gt_reqs[ti]["text"]) != norm(reqs[fi]["Content"])]
    res["rows_with_errors"] = len(wrong)
    res["errors_flagged"] = sum(1 for ti, fi in wrong if reqs[fi].get("Needs Review") == "Yes")
    res["flags_on_correct"] = sum(1 for ti, fi, _ in m if norm(gt_reqs[ti]["text"]) == norm(reqs[fi]["Content"])
                                  and ocr_flagged(reqs[fi]))
    cm = greedy_match(gt["captions"], caps, lambda t: t["text"], lambda f: f.get("Content") or "", 0.85)
    res.update({"cap_total": len(gt["captions"]), "cap_found": len(cm), "cap_extracted": len(caps)})
    # tables: match on caption similarity, else by best cell overlap
    gt_tabs = [t for t in gt["tables"] if not t.get("optional")]
    tab_scores = []
    caption_link_errors = []
    used = set()
    for t in gt_tabs:
        best, best_score = None, 0.0
        for k, f in enumerate(tabs):
            if k in used:
                continue
            grid = tables.get(f.get("Table Sheet") or "", [])
            truth_cells = [norm(c) for r in t["rows"] for c in r if c]
            found_cells = [norm(c) for r in grid for c in r if c]
            if not truth_cells:
                continue
            hits = 0
            pool = list(found_cells)
            for c in truth_cells:
                if c in pool:
                    pool.remove(c)
                    hits += 1
            score = hits / len(truth_cells)
            if t.get("caption") and f.get("Title") and similarity(t["caption"], f["Title"]) > 0.85:
                score += 0.01
            if score > best_score:
                best, best_score = k, score
        if best is not None and best_score >= 0.3:
            used.add(best)
            tab_scores.append(min(best_score, 1.0))
            title = tabs[best].get("Title") or ""
            if t.get("caption") and similarity(t["caption"], title) < 0.85:
                caption_link_errors.append((t["caption"], title))
        else:
            tab_scores.append(0.0)
    res.update({"tab_total": len(gt_tabs), "tab_found": sum(1 for s in tab_scores if s > 0),
                "tab_cell_acc": sum(tab_scores) / max(len(tab_scores), 1), "tab_extracted": len(tabs),
                "caption_link_errors": len(caption_link_errors)})
    if details:
        print(f"\n--- {xlsx.name}: missed requirements ---")
        for i, r in enumerate(gt_reqs):
            if i not in matched_t:
                best = max(reqs, key=lambda f: similarity(r["text"], f.get("Content") or ""), default=None)
                bs = similarity(r["text"], best.get("Content") or "") if best else 0
                print(f"  MISS [{r['keyword']}/{r['source']}] {r['text']}\n       closest ({bs:.2f}): {best.get('Content') if best else None}")
        print(f"--- {xlsx.name}: extra (not in ground truth) ---")
        for k, f in enumerate(reqs):
            if k not in matched_f:
                print(f"  EXTRA [{f.get('Found In')}] {f.get('Content')}")
        print(f"--- {xlsx.name}: imperfect matches ---")
        for ti, fi, s in m:
            if norm(gt_reqs[ti]["text"]) != norm(reqs[fi]["Content"]):
                print(f"  ({s:.3f}) truth: {gt_reqs[ti]['text']}\n          found: {reqs[fi]['Content']}")
        for ti, fi in ref_errors:
            print(f"  DOC REF: truth {gt_reqs[ti].get('doc_id')!r}  found {reqs[fi].get('Doc Ref')!r}  ({gt_reqs[ti]['text'][:60]})")
        for caption, title in caption_link_errors:
            print(f"  TABLE CAPTION: truth {caption!r}  found {title!r}")
        cm_f = {fi for _, fi, _ in cm}
        cm_t = {ti for ti, _, _ in cm}
        for i, c in enumerate(gt["captions"]):
            if i not in cm_t:
                print(f"  CAPTION MISS: {c['text']}")
        for k, c in enumerate(caps):
            if k not in cm_f:
                print(f"  CAPTION EXTRA: {c.get('Content')}")
        print(f"  table cell accuracy per table: {[round(s, 2) for s in tab_scores]}")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="+", help="folder(s) containing *_extracted.xlsx files")
    ap.add_argument("--corpus", default=str(Path(__file__).parent / "corpus"))
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()
    corpus = Path(args.corpus)
    rows = []
    for folder in args.results:
        for xlsx in sorted(Path(folder).glob("*_extracted*.xlsx")):
            doc = xlsx.name.split("_")[0]
            gt_file = corpus / f"{doc}_groundtruth.json"
            if not gt_file.exists():
                continue
            res = evaluate(xlsx, json.loads(gt_file.read_text()), args.details)
            rows.append((xlsx.name.replace("_extracted.xlsx", ""), res))
    if not rows:
        print("no results found")
        return 1
    print(f"\n{'file':24s} {'req rec':>7s} {'prec':>6s} {'mand':>6s} {'exact':>6s} {'CER':>6s} {'kw':>5s} {'ref err':>7s} "
          f"{'caps':>7s} {'tables':>7s} {'cells':>6s} {'cap link':>8s} | {'err rows':>8s} {'flagged':>7s} {'false flags':>11s}")
    for name, r in rows:
        print(f"{name:24s} {r['req_recall']:7.1%} {r['req_precision']:6.1%} {r['mandatory_recall']:6.1%} {r['req_exact']:6.1%} "
              f"{r['req_cer']:6.3f} {r['keyword_acc']:5.0%} {r['ref_errors']:7d} {r['cap_found']:>3d}/{r['cap_total']:<3d} "
              f"{r['tab_found']:>3d}/{r['tab_total']:<3d} {r['tab_cell_acc']:6.1%} {r['caption_link_errors']:8d} | {r['rows_with_errors']:8d} "
              f"{r['errors_flagged']:7d} {r['flags_on_correct']:11d}")
    err = sum(r["rows_with_errors"] for _, r in rows)
    print(f"\nREVIEW FLAGS: {sum(r['errors_flagged'] for _, r in rows)} of {err} requirement rows with OCR errors are flagged; "
          f"{sum(r['flags_on_correct'] for _, r in rows)} correct rows are flagged too")
    tot = {k: sum(r[k] for _, r in rows) for k in ("req_total", "req_found", "req_extracted", "cap_total", "cap_found")}
    print(f"\nOVERALL requirements: recall {tot['req_found'] / tot['req_total']:.1%}  precision "
          f"{tot['req_found'] / max(tot['req_extracted'], 1):.1%}   captions {tot['cap_found']}/{tot['cap_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
