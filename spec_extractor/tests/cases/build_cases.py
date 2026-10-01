#!/usr/bin/env python3
"""
build_cases.py - write the test-case documents and the catalog.

    python tests/cases/build_cases.py              documents/<ID>_<name>.pdf for every case (only those that
                                                   changed) and CASEBOOK.pdf, the catalog of all cases
    python tests/cases/build_cases.py --force      draw every document again

The documents are synthetic scans (300 dpi images in a PDF), one per case: open any of them to see the page
the tool is given. They are drawn from the case definitions (area_*.py), so they are not kept in git; this
script (or run_cases.py, which calls it) makes them. CASEBOOK.pdf IS kept in git: it describes every case -
the situation, what the tool must do and why, the page, and the rows the tool must produce - so it can be
read without running anything. Everything is drawn on this computer; nothing is sent anywhere.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import casekit  # noqa: E402

DOCUMENTS = HERE / "documents"
CASEBOOK = HERE / "CASEBOOK.pdf"


def fingerprint(case: casekit.Case) -> str:
    """What the document of a case is drawn from: its page and drawing settings, and the drawing code. (A case
    drawn by a function also depends on its area file as a whole.)"""
    h = hashlib.sha256((HERE / "casekit.py").read_bytes())
    h.update(repr((case.text, case.font, case.pt, case.dpi, case.pitch, case.copy)).encode())
    if case.draw is not None:
        for name in casekit.AREAS:
            h.update((HERE / f"{name}.py").read_bytes())
    return h.hexdigest()[:16]


def build_documents(cases: list, force: bool = False) -> dict:
    """Write documents/<ID>_<name>.pdf for these cases (only the missing or changed ones) -> {case id: path}."""
    DOCUMENTS.mkdir(exist_ok=True)
    manifest_file = DOCUMENTS / "manifest.json"
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    paths, made = {}, 0
    for c in cases:
        path = DOCUMENTS / c.filename
        fp = fingerprint(c)
        if force or not path.exists() or manifest.get(c.id) != fp:
            for old in DOCUMENTS.glob(f"{c.id}_*.pdf"):             # a renamed case leaves no stale copy
                old.unlink()
            c.save_pdf(path)
            manifest[c.id] = fp
            made += 1
        paths[c.id] = path
    manifest_file.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    if made:
        print(f"drew {made} case document(s) in {DOCUMENTS}", flush=True)
    return paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the test-case documents and the casebook")
    ap.add_argument("--force", action="store_true", help="draw every document again")
    ap.add_argument("--no-casebook", action="store_true", help="only the documents")
    args = ap.parse_args(argv)
    cases = casekit.load_cases()
    build_documents(cases, force=args.force)
    if not args.no_casebook:
        import casebook
        casebook.write_casebook(cases, CASEBOOK)
        print(f"catalog of {len(cases)} cases: {CASEBOOK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
