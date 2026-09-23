#!/usr/bin/env python3
"""
runner.py - acceptance suite for tabbed 'marker <tab> label <tab> value' lists (real OCR path).

    python tests/list_suite/runner.py                          (tests ../../spec_extractor.py, about 1-2 minutes)
    python tests/list_suite/runner.py [spec_extractor.py] [outdir] [--reuse] [--only TEXT] [--jobs N] [-v]

The page images and expectations.json are built by make_suite.py the first time (they are not stored in git).

Runs spec_extractor.py on every page image in images/ (one run, --no-combined --no-cache --no-word), reads the
'Extracted Items' sheet of each <stem>_extracted.xlsx and compares, case by case, the requirement rows with
expectations.json (written by make_suite.py). Prints one PASS/FAIL line per case and the totals; the full
expected-vs-actual listing of every case goes to <outdir>/suite_report.txt (and to the screen with -v).

A case passes when
  * its number of Requirement rows is exactly the expected number,
  * every row's Doc Ref is exactly the expected one (whitespace normalised), in the expected order,
  * every row's Content is similar to the expected text (difflib ratio >= 0.9, whitespace normalised) - both the
    whole Content AND the part after the stem sentence, so a list item that lost its value line cannot pass on
    the strength of a long shared stem,
  * its number of Table items is the expected one (0 unless the case says otherwise: a tabbed list is not a table).

Rows are given to cases by the paragraph number that starts their Doc Ref ('3.2.4 a' -> the case owning 3.2.4).
A row whose Doc Ref belongs to no case (e.g. '1.5' taken from a value '1.5 V ...', or no Doc Ref at all) goes to
the case whose expected text it resembles most, so a stray row counts against the case it came from. Table items
go to the case of the row before them.

Options: --reuse      do not run the tool again when <outdir> already holds the workbooks (re-check only)
         --only TEXT  only the cases (or page images) whose name contains TEXT
         --jobs N     run the tool as N parallel processes (pages split between them)
         -v           print the expected/actual rows of failing cases
Exit status: 0 when every selected case passes, 1 otherwise.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # the spec_extractor folder
VENV_PY = os.path.join(_ROOT, ".venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join(_ROOT, ".venv", "bin", "python")
try:
    import openpyxl  # noqa: F401
except ImportError:                                   # started with a Python without openpyxl: use the tool's venv
    if os.path.exists(VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(VENV_PY):
        os.execv(VENV_PY, [VENV_PY] + sys.argv)
    raise

import argparse
import difflib
import json
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
THRESHOLD = 0.9


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def tail_after_stem(actual: str, expected: str, stem_len: int) -> str:
    """The part of `actual` that corresponds to expected[stem_len:] (the list item after the stem)."""
    if stem_len <= 0:
        return actual
    pos = 0
    for a, b, size in difflib.SequenceMatcher(None, expected, actual, autojunk=False).get_matching_blocks():
        if a > stem_len or size == 0:
            break
        pos = b + min(stem_len - a, size)
    return actual[pos:].strip()


def run_tool(spec: Path, images: list, outdir: Path, jobs: int) -> None:
    py = os.environ.get("SPEC_PYTHON") or (VENV_PY if os.path.exists(VENV_PY) else sys.executable)
    jobs = max(1, min(jobs, len(images)))
    groups = [images[k::jobs] for k in range(jobs)]
    procs = []
    for k, group in enumerate(groups):
        target = outdir if jobs == 1 else outdir / f"run{k + 1}"
        target.mkdir(parents=True, exist_ok=True)
        cmd = [py, str(spec), *map(str, group), "-o", str(target), "--no-combined", "--no-cache", "--no-word"]
        log = open(target / "runner_tool_output.txt", "w", encoding="utf-8")
        procs.append((subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log, target))
    for p, log, target in procs:
        rc = p.wait()
        log.close()
        if rc != 0:
            print(f"WARNING: spec_extractor exited with status {rc} (see {target / 'runner_tool_output.txt'})",
                  file=sys.stderr)


def find_workbook(outdir: Path, image: Path):
    hits = sorted(outdir.rglob(f"{image.stem}_extracted.xlsx"))
    return hits[0] if hits else None


def read_items(xlsx: Path) -> list:
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb["Extracted Items"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    col = {name: k for k, name in enumerate(rows[0]) if name}
    out = []
    for r in rows[1:]:
        kind = r[col["Type"]]
        if kind not in ("Requirement", "Table"):
            continue
        out.append({"type": kind, "doc_ref": norm(r[col["Doc Ref"]]), "content": norm(r[col["Content"]]),
                    "item": r[col["Item #"]], "found_in": r[col.get("Found In", col["Type"])]})
    return out


def assign(rows: list, cases: list) -> list:
    owner = {ref: ci for ci, c in enumerate(cases) for ref in c["refs"]}
    out = [[] for _ in cases]
    current = 0
    for r in rows:
        key = r["doc_ref"].split()[0] if r["doc_ref"] else ""
        if r["type"] == "Requirement" and key in owner:
            current = owner[key]
        elif r["type"] == "Requirement":
            best, best_ci = 0.0, current
            for ci, c in enumerate(cases):
                for e in c["expected_rows"]:
                    s = difflib.SequenceMatcher(None, r["content"], norm(e["content"]), autojunk=False).quick_ratio()
                    if s > best:
                        best, best_ci = s, ci
            current = best_ci if best >= 0.4 else current
        out[current].append(r)
    return out


def align(exp: list, got: list) -> list:
    """Pair expected and actual rows by Doc Ref order -> [(expected or None, actual or None)]."""
    a, b = [norm(e["doc_ref"]) for e in exp], [r["doc_ref"] for r in got]
    pairs = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        n = max(i2 - i1, j2 - j1)
        for k in range(n):
            pairs.append((exp[i1 + k] if i1 + k < i2 else None, got[j1 + k] if j1 + k < j2 else None))
    return pairs


def compare_row(e: dict, a: dict) -> list:
    e_ref, e_text = norm(e["doc_ref"]), norm(e["content"])
    stem_len = len(norm(e.get("stem", ""))) + (1 if e.get("stem") else 0)
    full = ratio(a["content"], e_text)
    tail = ratio(tail_after_stem(a["content"], e_text, stem_len), e_text[stem_len:].strip())
    bad = []
    if a["doc_ref"] != e_ref:
        bad.append(f"Doc Ref {a['doc_ref']!r} != {e_ref!r}")
    if full < THRESHOLD or tail < THRESHOLD:
        bad.append(f"text similarity {full:.2f} (item part {tail:.2f})")
    return bad


def evaluate(case: dict, rows: list) -> tuple:
    """-> (passed, one-line reason, detail lines)"""
    exp = case["expected_rows"]
    reqs = [r for r in rows if r["type"] == "Requirement"]
    n_tables = sum(1 for r in rows if r["type"] == "Table")
    problems, detail = [], []
    if len(reqs) != len(exp):
        want, got = Counter(norm(e["doc_ref"]) for e in exp), Counter(r["doc_ref"] for r in reqs)
        missing, extra = list((want - got).elements()), list((got - want).elements())
        msg = f"{len(reqs)} rows, expected {len(exp)}"
        if missing:
            msg += "; missing " + ", ".join(repr(m) for m in missing)
        if extra:
            msg += "; unexpected " + ", ".join(repr(x) for x in extra)
        problems.append(msg)
    # the pass test pairs rows in order; the listing aligns them by Doc Ref so a lost row does not shift the rest
    if len(reqs) == len(exp):
        for k, (e, a) in enumerate(zip(exp, reqs), 1):
            bad = compare_row(e, a)
            if bad:
                problems.append(f"row {k}: " + ", ".join(bad))
    for k, (e, a) in enumerate(align(exp, reqs), 1):
        bad = compare_row(e, a) if e and a else []
        mark = "!!" if bad or not (e and a) else "  "
        detail.append(f"   {mark} expected  " + (f"[{norm(e['doc_ref'])}] {norm(e['content'])}" if e else "(none)"))
        detail.append(f"   {mark} actual    " + (f"[{a['doc_ref']}] {a['content']}" if a else "(none)")
                      + (f"   <- {'; '.join(bad)}" if bad else ""))
    want_tables = case.get("tables", 0)
    if n_tables != want_tables:
        problems.append(f"{n_tables} Table item(s), expected {want_tables}")
    for r in rows:
        if r["type"] == "Table":
            detail.append(f"   {'  ' if n_tables == want_tables else '!!'} TABLE item {r['item']}: {r['content'][:150]}")
    return (not problems), "; ".join(problems[:3]) + (" ..." if len(problems) > 3 else ""), detail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tabbed-list acceptance suite for spec_extractor.py")
    ap.add_argument("spec", nargs="?", default=str(HERE.parent.parent / "spec_extractor.py"),
                    help="path of the spec_extractor.py to test (default: the one in this project)")
    ap.add_argument("outdir", nargs="?", default=str(HERE / "_results"),
                    help="folder for the tool's output and the suite report (default: tests/list_suite/_results)")
    ap.add_argument("--reuse", action="store_true", help="re-check existing workbooks in outdir without re-running")
    ap.add_argument("--only", default="", help="only cases / page images whose name contains this text")
    ap.add_argument("--jobs", type=int, default=1, help="parallel tool processes (default 1)")
    ap.add_argument("-v", "--verbose", action="store_true", help="print expected/actual rows of failing cases")
    args = ap.parse_args(argv)

    spec, outdir = Path(args.spec).resolve(), Path(args.outdir).resolve()
    if not spec.is_file():
        ap.error(f"no such file: {spec}")
    outdir.mkdir(parents=True, exist_ok=True)
    if not (HERE / "expectations.json").exists() or not (HERE / "images").is_dir():
        print("Building the list-format test pages ...", flush=True)
        if subprocess.call([sys.executable, str(HERE / "make_suite.py")]) != 0:
            return 2
    expectations = json.loads((HERE / "expectations.json").read_text(encoding="utf-8"))
    pages = []
    for p in expectations["pages"]:
        cases = [c for c in p["cases"] if not args.only or args.only in c["name"] or args.only in p["image"]]
        if cases:
            pages.append((HERE / p["image"], p["cases"], {c["name"] for c in cases}))

    t0 = time.time()
    todo = [img for img, _, _ in pages if not (args.reuse and find_workbook(outdir, img))]
    if todo:
        print(f"running {spec.name} on {len(todo)} page image(s) -> {outdir}", flush=True)
        for img in todo:                              # never compare against a stale workbook
            for old in outdir.rglob(f"{img.stem}_extracted.xlsx"):
                old.unlink()
        run_tool(spec, todo, outdir, args.jobs)

    report, n_pass, n_all = [], 0, 0
    for img, cases, selected in pages:
        xlsx = find_workbook(outdir, img)
        rows = read_items(xlsx) if xlsx else None
        report.append(f"=== {img.name}  ({xlsx if xlsx else 'NO WORKBOOK'})")
        per_case = assign(rows, cases) if rows is not None else [[] for _ in cases]
        for case, got in zip(cases, per_case):
            if case["name"] not in selected:
                continue
            n_all += 1
            if rows is None:
                ok, why, detail = False, "no Excel output for this page (did the tool fail?)", []
            else:
                ok, why, detail = evaluate(case, got)
            n_pass += ok
            line = f"{'PASS' if ok else 'FAIL'}  {case['name']}" + ("" if ok else f"  - {why}")
            print(line, flush=True)
            report.append(line)
            report.append(f"   format: {case['format']}")
            if case.get("notes"):
                report.append(f"   notes:  {case['notes']}")
            report.extend(detail)
            if args.verbose and not ok:
                print("\n".join(detail))
        report.append("")
    total = f"TOTAL: {n_pass}/{n_all} passed, {n_all - n_pass} failed  ({time.time() - t0:.0f} s)"
    print(total)
    report.append(total)
    (outdir / "suite_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"details: {outdir / 'suite_report.txt'}")
    return 0 if n_pass == n_all else 1


if __name__ == "__main__":
    sys.exit(main())
