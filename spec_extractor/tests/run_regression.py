#!/usr/bin/env python3
"""
run_regression.py - one command to confirm the extractor still works after ANY change.

    python -m pip install -r requirements-dev.txt      (once)
    python tests/run_regression.py                     (about 3-6 minutes on a laptop)
    python tests/run_regression.py --reuse             (re-use OCR results: seconds, for rule changes)

Steps: 1) build the synthetic degraded test documents (only if missing),
       2) run spec_extractor.py on all of them, 3) score against the exact ground truth,
       4) print PASS or FAIL. Exit code 0 = pass, 1 = accuracy dropped, 2 = the run crashed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CORPUS = HERE / "corpus"
RESULTS = HERE / "_results"
FILES = ["specA_clean.pdf", "specA_scan.pdf", "specA_photocopy.tif", "specB_scan.pdf", "specB_photocopy.tif", "specC_fax.tif",
         "specD_scan.pdf", "specE_scan.pdf", "specE_photocopy.tif", "specG_pages.tif", "specH_scan.pdf",
         "specH_photocopy.tif"]

# Minimum acceptable scores. "ref_errors" = requirement rows with a wrong paragraph number / ID;
# "caption_link_errors" = tables that carry another table's caption (or none).
# "clean_scan_flags" = items of any type (tables, captions ...) marked Needs Review in the undamaged scan,
# where the OCR is perfect: it keeps the review checks from crying wolf (e.g. on sequential IDs).
THRESHOLDS = {"requirement_recall": 0.98, "requirement_precision": 0.98, "captions_missed": 0,
              "tables_missed": 0, "error_rows_flagged_share": 0.75, "false_flags": 2,
              "ref_errors": 1, "caption_link_errors": 0, "clean_scan_flags": 0}
LOWER_IS_BETTER = ("captions_missed", "tables_missed", "false_flags", "ref_errors", "caption_link_errors", "clean_scan_flags")
CLEAN_FILES = ("specA_clean.pdf",)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reuse", action="store_true", help="re-use cached OCR results from the last run")
    args = ap.parse_args()

    if not all((CORPUS / f).exists() for f in FILES):
        print("Building the synthetic test documents ...")
        if subprocess.call([sys.executable, str(HERE / "make_test_corpus.py"), "--out", str(CORPUS)]) != 0:
            return 2

    cmd = [sys.executable, str(ROOT / "spec_extractor.py"), *[str(CORPUS / f) for f in FILES], "-o", str(RESULTS),
           "--no-combined", "--no-page-images"]
    if not args.reuse:
        cmd.append("--no-cache")
    print("Running:", " ".join(cmd[1:3]), f"... ({len(FILES)} documents)")
    if subprocess.call(cmd) != 0:
        print("FAIL: spec_extractor.py reported an error")
        return 2

    sys.path.insert(0, str(HERE))
    import evaluate  # noqa: E402  (tests/evaluate.py)

    totals = {k: 0 for k in ("req_total", "req_found", "req_extracted", "cap_total", "cap_found", "tab_total",
                             "tab_found", "rows_with_errors", "errors_flagged", "flags_on_correct", "ref_errors",
                             "caption_link_errors")}
    clean_scan_flags = 0
    print(f"\n{'document':22s} {'recall':>7s} {'precision':>9s} {'exact text':>10s} {'captions':>9s} {'tables':>7s}")
    for f in FILES:
        xlsx = RESULTS / f"{Path(f).stem}_extracted.xlsx"
        gt = json.loads((CORPUS / f"{f.split('_')[0]}_groundtruth.json").read_text())
        r = evaluate.evaluate(xlsx, gt, details=False)
        for k in totals:
            totals[k] += r[k]
        if f in CLEAN_FILES:
            items, _tables = evaluate.read_items(xlsx)
            clean_scan_flags += sum(1 for it in items if evaluate.ocr_flagged(it))
        print(f"{Path(f).stem:22s} {r['req_recall']:7.1%} {r['req_precision']:9.1%} {r['req_exact']:10.1%} "
              f"{r['cap_found']:>4d}/{r['cap_total']:<4d} {r['tab_found']:>3d}/{r['tab_total']:<3d}")

    scores = {
        "requirement_recall": totals["req_found"] / max(totals["req_total"], 1),
        "requirement_precision": totals["req_found"] / max(totals["req_extracted"], 1),
        "captions_missed": totals["cap_total"] - totals["cap_found"],
        "tables_missed": totals["tab_total"] - totals["tab_found"],
        "error_rows_flagged_share": totals["errors_flagged"] / max(totals["rows_with_errors"], 1),
        "false_flags": totals["flags_on_correct"],
        "ref_errors": totals["ref_errors"],
        "caption_link_errors": totals["caption_link_errors"],
        "clean_scan_flags": clean_scan_flags,
    }
    failed = []
    for key, limit in THRESHOLDS.items():
        value = scores[key]
        ok = value <= limit if key in LOWER_IS_BETTER else value >= limit
        print(f"  {key:26s} {value:8.3f}  (limit {limit})  {'ok' if ok else 'FAILED'}")
        if not ok:
            failed.append(key)
    print("\nPASS" if not failed else f"\nFAIL: {', '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
