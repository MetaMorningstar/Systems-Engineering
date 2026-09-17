#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 SPEC EXTRACTOR  -  requirements, tables and captions from scanned documents
===============================================================================

WHAT IT DOES
  1. Reads scanned PDF and TIFF files (PNG / JPG / BMP also work), page by page.
  2. Cleans every page image: fixes sideways or upside-down pages, straightens
     skew, flattens stains/shadows/yellowed paper, normalizes resolution.
  3. Reads the text with a modern deep-learning OCR model (PaddleOCR PP-OCRv6,
     run through RapidOCR + ONNX Runtime). It runs on an ordinary CPU and needs
     NO internet connection - the model files ship inside the pip package, and
     ONNX Runtime's usage telemetry is switched off (see section 1).
  4. Rebuilds the page layout: headings, paragraphs, lists, tables (cell by
     cell), figures, captions, page headers/footers, in reading order.
  5. Finds Systems Engineering requirements written as paragraphs ("shall"
     statements), list items under a stem ("The system shall: a. ... b. ..."),
     and rows of requirement tables. Also collects every table and caption.
  6. Writes, for each input document:
       <name>_extracted.xlsx     one row per requirement, caption and table
                                 (each table also gets its own worksheet)
       <name>_verification.docx  the document rebuilt page by page next to
                                 the scanned image, with words worth checking
                                 highlighted, to check nothing was missed
     plus ALL_DOCUMENTS_<date>.xlsx when more than one document is processed.

QUICK START
  1. Install Python 3.11 or 3.12 (3.10 and 3.13 also work) from python.org.
     Tick "Add python.exe to PATH".
  2. Open a terminal in this folder and run:
         python -m pip install -r requirements.txt
  3. Run one of:
         python spec_extractor.py "C:\\Scans\\MySpec.pdf"      (one file)
         python spec_extractor.py "C:\\Scans"                  (every file in a folder)
         python spec_extractor.py                             (opens a file picker)
     Results appear in an "extraction_output" folder next to the input.

USEFUL OPTIONS  (run  python spec_extractor.py --help  for the full list)
  -o / --output FOLDER      put results somewhere else
  --pages 1-5,9             only process some pages (handy for a first test)
  --keywords "shall;must"   words that mark a requirement, separated by commas or
                            semicolons (default: shall, must, is/are required to,
                            should, will)
  --no-will                 do not treat "will" statements as requirements
  --keep-list-stems         one row per stem+list block instead of per item
  --review-threshold 0.70   flag numbers read below this OCR confidence (default 0.70)
  --engine docling          optional: IBM Docling AI layout + table models
                            (needs extra install + one-time model download)
  --no-word                 skip the Word verification report
  --debug-images            also save the cleaned page images

HOW TO CHECK THE RESULTS (recommended routine)
  * Open <name>_verification.docx. Each page shows the scan, then the text the
    tool read. Yellow highlight = a word worth checking against the scan (it
    failed a spelling / punctuation / look-alike check, or is a number the OCR
    was unsure of); red = very unsure. Blue tags like [R-0012] show which
    Excel row a sentence became.
  * In <name>_extracted.xlsx filter "Needs Review" = Yes first. The
    "Review Reasons" column says why (suspect word or number, keyword that had
    to be repaired, text that continued across a page, list stem without items).
  * "Page Quality" sheet: pages graded Poor deserve a closer look; a page graded
    FAILED could not be read at all (the other pages still were).

DESIGN NOTES (for maintainers)
  * Heavy lifting is done by proven, permissively licensed libraries:
      RapidOCR (Apache-2.0) running PaddleOCR PP-OCRv6 models (Apache-2.0)
      img2table (MIT)       - OpenCV ruled / borderless table detection
      OpenCV (Apache-2.0), pypdfium2 (Apache-2.0/BSD), Pillow (MIT-CMU)
      openpyxl (MIT), python-docx (MIT); optional Docling (MIT)
    AGPL/GPL and revenue-restricted model licenses (e.g. PyMuPDF, MinerU,
    Marker/Surya weights) were deliberately avoided.
  * Generative "vision-language" OCR models were NOT used for transcription:
    they read degraded text well but can silently invent or "correct" words
    and numbers, which is unacceptable for requirements. PP-OCRv6 gives a
    confidence score for every word, so uncertain text can be flagged.
  * Requirement detection is rule-based (deterministic and auditable):
    modal verbs per MIL-STD-961 / INCOSE usage, paragraph numbering, list
    stems, requirement-table column detection. All rules are in section 9.
  * OCR results are cached per file, so re-running with different requirement
    settings is fast. Delete the "_cache" folder (or use --no-cache) to force
    a fresh OCR. Editing the OCR/layout code (sections 3-6, 8) invalidates the
    cache automatically.
  * Tests: tests/test_rules.py (seconds, layout + requirement rules) and
    tests/run_regression.py (minutes, whole tool on synthetic aged scans with
    exact ground truth). Run both after any change.

FILE LAYOUT OF THIS SCRIPT
   1. Imports and dependency check          7. Document-level clean-up
   2. Settings (defaults you can change)    8. Optional Docling engine
   3. Data model                            9. Requirement / caption / table extraction
   4. Loading pages from PDF / TIFF        10. Excel export
   5. Image clean-up (preprocessing)       11. Word verification report
   6. OCR + page layout analysis           12. Batch runner, caching, command line
"""
from __future__ import annotations

# =============================================================================
# 1. IMPORTS AND DEPENDENCY CHECK
# =============================================================================
import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import logging
import math
import os
import re
import statistics
import sys
import time
import traceback
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

__version__ = "1.0.0"

# Keep all traffic on this computer. ONNX Runtime (which runs the OCR models) otherwise sends usage
# telemetry to Microsoft - measured: 4 connection attempts per run, no document content - and the
# Hugging Face libraries used by the optional Docling engine report downloads. These switches must be
# set before those libraries load. (An administrator can still override them in the environment.)
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")

_MISSING = []
try:
    import numpy as np
except ImportError:  # pragma: no cover - only hit on a broken install
    _MISSING.append("numpy")
try:
    import cv2
except ImportError:  # pragma: no cover
    _MISSING.append("opencv-contrib-python (installed automatically with img2table)")
try:
    from PIL import Image
except ImportError:  # pragma: no cover
    _MISSING.append("pillow")
try:
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c
except ImportError:  # pragma: no cover
    _MISSING.append("pypdfium2")
try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table as XlTable, TableStyleInfo
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.worksheet.hyperlink import Hyperlink
except ImportError:  # pragma: no cover
    _MISSING.append("openpyxl")
try:
    import docx  # python-docx
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
    from docx.shared import Inches, Pt, RGBColor
except ImportError:  # pragma: no cover
    _MISSING.append("python-docx")

if _MISSING:  # pragma: no cover
    sys.stderr.write(
        "\nMissing Python packages: " + ", ".join(_MISSING) +
        "\nInstall everything with:\n    python -m pip install -r requirements.txt\n\n")
    sys.exit(2)

# Scanned engineering drawings can be very large; these are trusted local files.
Image.MAX_IMAGE_PIXELS = 400_000_000

LOG = logging.getLogger("spec_extractor")


# =============================================================================
# 2. SETTINGS  -  every tunable value lives here, with an explanation.
#    Command-line options override these defaults (see section 12).
# =============================================================================
@dataclass
class Settings:
    # ---- Input / output -----------------------------------------------------
    recursive: bool = False             # also look inside sub-folders
    output_dir: Optional[Path] = None   # default: <input folder>/extraction_output
    page_selection: str = ""            # e.g. "1-3,7"; empty = all pages
    use_cache: bool = True              # reuse OCR results for unchanged files

    # ---- Page images ----------------------------------------------------------
    # OCR works best around 200-220 dpi for PP-OCR (tested on degraded scans:
    # 300 dpi was no more accurate and took twice as long). Pages are resized
    # toward this resolution; very low-resolution scans are gently upscaled.
    target_dpi: int = 220
    fallback_dpi: int = 300             # assumed when a file has no resolution info
    max_page_megapixels: float = 60.0   # huge drawings are scaled down to this
    auto_rotate: bool = True            # fix pages scanned sideways / upside-down
    deskew: bool = True                 # straighten slightly rotated scans
    max_skew_degrees: float = 8.0       # largest skew the deskew step searches for
    clean_background: bool = True       # flatten stains, shadows, yellowed paper
    denoise: bool = True                # light median filter against speckle
    remove_color_marks: bool = False    # fade colored stamps/highlighter (keeps black text)

    # ---- OCR --------------------------------------------------------------------
    engine: str = "standard"            # "standard" (pip-only) or "docling" (optional)
    ocr_model_size: str = "small"       # PP-OCRv6 "small" ships with RapidOCR (no download)
    min_text_confidence: float = 0.30   # text below this is treated as noise and dropped
    # Tested on degraded scans: most real misreads still score > 0.95, so confidence alone is a
    # weak signal. Words are ALSO flagged by independent checks (dictionary, accent marks,
    # punctuation inside words, numbers with letters) - see WordChecker in section 7.
    review_confidence: float = 0.70     # words below this OCR confidence are flagged "Needs Review"
    very_low_confidence: float = 0.50   # shown in red in the Word report
    english_text: bool = True           # documents are English: remove accent marks OCR adds (telémetry)
    spell_check_flags: bool = True      # flag words missing from an English dictionary (never auto-corrects)
    # your program's own words that the dictionary check should accept, e.g. {"xr7", "radome"}
    extra_dictionary_words: set = field(default_factory=set)
    ocr_threads: int = 0                # 0 = let ONNX Runtime decide

    # ---- Tables -------------------------------------------------------------------
    detect_tables: bool = True
    borderless_tables: bool = True      # also look for tables without ruling lines
    merge_continued_tables: bool = True # join a table that continues on the next page

    # ---- Requirements -------------------------------------------------------------
    # keyword -> requirement class. Matching ignores case. Multi-word phrases are fine.
    keywords: dict = field(default_factory=lambda: {
        "shall": "Mandatory",
        "must": "Mandatory",
        "is required to": "Mandatory",
        "are required to": "Mandatory",
        "should": "Goal / recommended",
        "will": "Statement of intent",
    })
    split_list_items: bool = True       # one row per list item ("stem + item")
    fix_ocr_keywords: bool = True       # repair OCR-garbled keywords (e.g. "sha11" -> "shall")
    quality_checks: bool = True         # INCOSE-style notes (TBD, vague terms, and/or ...)
    # a table column with one of these headers holds requirements (every row becomes a requirement)
    requirement_table_headers: tuple = ("requirement", "requirements", "req text", "req. text",
                                        "shall statement", "requirement statement")
    id_column_headers: tuple = ("req id", "req. id", "requirement id", "req no", "req. no", "req. no.",
                                "req #", "id", "no.", "no", "number", "paragraph", "para", "para.",
                                "ref", "ref.", "reference", "item", "req")

    # ---- Outputs ----------------------------------------------------------------------
    make_excel: bool = True
    make_word_report: bool = True
    word_page_images: bool = True       # put the scanned page image in the Word report
    word_image_dpi: int = 110           # resolution of those images (file size vs. clarity)
    combined_workbook: bool = True      # ALL_DOCUMENTS_<date>.xlsx when >1 document
    save_debug_images: bool = False

    # ---- Optional Docling engine -----------------------------------------------------
    docling_models_dir: Optional[Path] = None  # offline model folder (docling-tools models download)
    docling_device: str = "auto"               # auto / cpu / cuda / mps

    def ocr_fingerprint(self) -> str:
        """Settings that change OCR/layout results (used for the cache key)."""
        keys = ["target_dpi", "fallback_dpi", "max_page_megapixels", "auto_rotate", "deskew",
                "max_skew_degrees", "clean_background", "denoise", "remove_color_marks", "engine",
                "ocr_model_size", "min_text_confidence", "detect_tables", "borderless_tables"]
        values = {k: getattr(self, k) for k in keys}
        values["keywords"] = sorted(self.keywords)      # the layout rules protect keyword sentences
        blob = json.dumps(values, sort_keys=True, default=str)
        return hashlib.sha1((blob + CACHE_FORMAT + __version__ + _cached_code_hash()).encode()).hexdigest()[:10]


CACHE_FORMAT = "spec-extractor-cache-v1"


def _cached_code_hash() -> str:
    """Fingerprint of the code whose results are cached (data model, page loading, image clean-up, OCR,
    page layout, Docling mapping: sections 3-6 and 8). Editing that code makes old caches unused
    automatically; changes to the requirement rules and exports (sections 7, 9-12) reuse the OCR cache."""
    try:
        src = Path(__file__).read_text(encoding="utf-8")

        def banner(title):                # position of a section title line (not this function's text)
            return re.search(r"^# " + re.escape(title), src, re.M).start()

        cached = src[banner("3. DATA MODEL"):banner("7. DOCUMENT-LEVEL CLEAN-UP")]
        cached += src[banner("8. OPTIONAL ENGINE: DOCLING"):banner("9. REQUIREMENT / CAPTION / TABLE EXTRACTION")]
        return hashlib.sha1(cached.encode("utf-8")).hexdigest()[:8]
    except (OSError, AttributeError):
        return ""
SUPPORTED_EXTENSIONS = {".pdf", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}


# =============================================================================
# 3. DATA MODEL
#    Everything the engines produce is stored in these small classes, so the
#    requirement extraction and the exports do not care which engine ran.
#    Boxes are (x0, y0, x1, y1) in pixels of the cleaned page image, origin top-left.
# =============================================================================
Box = tuple  # (x0, y0, x1, y1)


def box_union(boxes: Iterable[Box]) -> Box:
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def box_area(b: Box) -> float:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def box_intersection(a: Box, b: Box) -> float:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def box_center_inside(inner: Box, outer: Box, pad: float = 0) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] - pad <= cx <= outer[2] + pad and outer[1] - pad <= cy <= outer[3] + pad


@dataclass
class Word:
    text: str
    conf: float
    box: Box


@dataclass
class Line:
    """One OCR text line (a horizontal run of words)."""
    text: str
    conf: float
    box: Box
    words: list = field(default_factory=list)   # list[Word]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    @property
    def min_word_conf(self) -> float:
        return min((w.conf for w in self.words), default=self.conf)


@dataclass
class TableData:
    """A table as a rectangular grid. Merged cells repeat their text in every
    grid position they cover and are listed in `merges` (r0, c0, r1, c1)."""
    grid: list                                  # list[list[str]]
    conf: list                                  # list[list[float]] min word confidence per cell (1.0 if empty)
    merges: list = field(default_factory=list)  # list[(r0, c0, r1, c1)]
    header_rows: int = 1
    cell_boxes: list = field(default_factory=list)  # list[list[Box]] (may be empty)
    continued_pages: list = field(default_factory=list)  # extra pages merged into this table
    cell_words: list = field(default_factory=list)  # list[list[list[[word, confidence]]]] (may be empty)

    @property
    def n_rows(self) -> int:
        return len(self.grid)

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.grid), default=0)

    def as_text(self, sep: str = " | ") -> str:
        """Plain-text rendering used in the one-row-per-table Excel column."""
        out = []
        for i, row in enumerate(self.grid):
            out.append(sep.join((c or "").replace("\n", " ").strip() for c in row))
            if i == self.header_rows - 1 and self.n_rows > 1:
                out.append(sep.join("---" for _ in row))
        return "\n".join(out)


@dataclass
class Block:
    """A layout element in reading order.
    kind: heading | paragraph | list_item | caption | table | figure | page_header | page_footer"""
    kind: str
    page: int
    box: Box
    lines: list = field(default_factory=list)       # list[Line]
    text: str = ""
    table: Optional[TableData] = None
    meta: dict = field(default_factory=dict)       # marker, caption kind/number, image file, ...
    uid: int = 0                                   # unique number within the document
    pages: list = field(default_factory=list)      # all pages this block spans (after merging)

    @property
    def conf(self) -> float:
        confs = [ln.conf for ln in self.lines]
        if self.table is not None:
            confs += [c for row in self.table.conf for c in row]
        return float(statistics.fmean(confs)) if confs else 1.0

    @property
    def min_conf(self) -> float:
        confs = [ln.min_word_conf for ln in self.lines]
        if self.table is not None:
            confs += [c for row in self.table.conf for c in row]
        return float(min(confs)) if confs else 1.0

    def page_label(self) -> str:
        pages = sorted(set(self.pages or [self.page]))
        return str(pages[0]) if len(pages) == 1 else f"{pages[0]}-{pages[-1]}"


@dataclass
class PageInfo:
    number: int
    width: int
    height: int
    source_dpi: float
    dpi: float                    # resolution of the cleaned image the OCR saw
    rotation: int = 0             # degrees clockwise that were applied to make the page upright
    skew: float = 0.0             # degrees of skew correction applied
    n_lines: int = 0
    mean_conf: float = 1.0
    low_conf_lines: int = 0
    image_file: str = ""          # downscaled page image for the Word report (in cache folder)
    notes: list = field(default_factory=list)


@dataclass
class DocResult:
    source: str
    engine: str
    pages: list = field(default_factory=list)    # list[PageInfo]
    blocks: list = field(default_factory=list)   # list[Block] in reading order
    warnings: list = field(default_factory=list)
    seconds: float = 0.0
    cache_dir: str = ""

    # ---- JSON round trip (for the OCR cache) --------------------------------------
    def to_json(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_json(d: dict) -> "DocResult":
        def line(ld):
            return Line(ld["text"], ld["conf"], tuple(ld["box"]), [Word(w["text"], w["conf"], tuple(w["box"])) for w in ld["words"]])

        blocks = []
        for b in d["blocks"]:
            t = b.get("table")
            table = None
            if t:
                table = TableData(grid=t["grid"], conf=t["conf"], merges=[tuple(m) for m in t["merges"]],
                                  header_rows=t["header_rows"], cell_boxes=t.get("cell_boxes", []),
                                  continued_pages=t.get("continued_pages", []), cell_words=t.get("cell_words", []))
            blocks.append(Block(kind=b["kind"], page=b["page"], box=tuple(b["box"]),
                                lines=[line(ld) for ld in b["lines"]], text=b["text"], table=table,
                                meta=b["meta"], uid=b["uid"], pages=b.get("pages", [])))
        pages = [PageInfo(**p) for p in d["pages"]]
        return DocResult(source=d["source"], engine=d["engine"], pages=pages, blocks=blocks,
                         warnings=d.get("warnings", []), seconds=d.get("seconds", 0.0), cache_dir=d.get("cache_dir", ""))


@dataclass
class ExtractedItem:
    """One row of the final Excel sheet."""
    item_type: str            # Requirement | Table | Table Caption | Figure Caption
    source_file: str
    pages: str
    section: str = ""
    doc_ref: str = ""         # paragraph number, requirement ID, or table/figure number
    title: str = ""           # inline paragraph title, e.g. "Detection range"
    text: str = ""
    keyword: str = ""
    req_class: str = ""
    found_in: str = ""        # Paragraph | List item | Table row | Table cell | ...
    context: str = ""         # list stem, table caption, or surrounding sentence(s)
    attributes: str = ""      # other table columns, e.g. "Method: T"
    verification: str = ""    # verification method(s): from the requirement table or the VCRM
    references: str = ""      # standards / tables / figures / sections the requirement cites
    ocr_conf: Optional[float] = None
    review_reasons: list = field(default_factory=list)
    quality_notes: list = field(default_factory=list)
    table: Optional[TableData] = None
    block_uids: list = field(default_factory=list)
    item_id: str = ""
    table_sheet: str = ""

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)


# =============================================================================
# 4. LOADING PAGES FROM PDF / TIFF / IMAGE FILES
# =============================================================================
@dataclass
class RawPage:
    number: int            # 1-based page number inside the file
    image: "np.ndarray"    # uint8, grayscale (H, W) or RGB (H, W, 3), square pixels
    dpi: float             # resolution of `image`
    dpi_known: bool        # False when the file had no trustworthy resolution
    notes: list = field(default_factory=list)
    error: str = ""        # set when this page could not be read (the other pages still are)


def parse_page_selection(spec: str, n_pages: int) -> list:
    """Turn '1-3,7' into [1, 2, 3, 7] (1-based, limited to the pages that exist). Accepts en/em dashes
    and reversed ranges ('5-3'); raises ValueError with a readable message for anything else."""
    if not spec or not spec.strip():
        return list(range(1, n_pages + 1))
    pages = set()
    for part in re.sub(r"[\u2012\u2013\u2014\u2212]", "-", spec).replace(" ", "").split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)-(\d*)|(\d+)", part)
        if not m or part == "-":
            raise ValueError(f"page selection '{part}' is not understood - use for example 1-5,9")
        if m.group(3):
            pages.add(int(m.group(3)))
        else:
            first = int(m.group(1)) if m.group(1) else 1
            last = int(m.group(2)) if m.group(2) else n_pages
            if m.group(1) and m.group(2):
                first, last = min(first, last), max(first, last)     # "5-3" means pages 3 to 5
            pages.update(range(first, min(last, n_pages) + 1))
    return [p for p in sorted(pages) if 1 <= p <= n_pages]


def count_pages(path: Path) -> int:
    if path.suffix.lower() == ".pdf":
        pdf = pdfium.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()
    with Image.open(path) as im:
        return int(getattr(im, "n_frames", 1))


def iter_raw_pages(path: Path, settings: Settings) -> Iterator[RawPage]:
    """Yield the selected pages of a document one at a time (keeps memory low)."""
    if path.suffix.lower() == ".pdf":
        yield from _iter_pdf_pages(path, settings)
    else:
        yield from _iter_image_pages(path, settings)


def _pdf_scan_dpi(page) -> Optional[float]:
    """Resolution of the scanned picture that fills a PDF page, or None when the
    page is not a scan (born-digital text, vector drawing, ...)."""
    try:
        page_w, page_h = page.get_size()
        best = None
        for obj in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,), max_depth=3):
            left, bottom, right, top = obj.get_bounds()
            if (right - left) * (top - bottom) < 0.4 * page_w * page_h:
                continue  # a logo or signature, not the page scan
            px_w, px_h = obj.get_px_size()
            # the image may be placed rotated; use the larger of the two estimates
            dpi = max(px_w, px_h) / max(max(right - left, top - bottom) / 72.0, 1e-6)
            best = max(best or 0.0, dpi)
        return best
    except Exception:  # never let an odd PDF object stop the run
        return None


def _iter_pdf_pages(path: Path, settings: Settings) -> Iterator[RawPage]:
    pdf = pdfium.PdfDocument(str(path))
    try:
        for number in parse_page_selection(settings.page_selection, len(pdf)):
            try:
                page = pdf[number - 1]
            except Exception as exc:
                yield RawPage(number, None, 0.0, False, [], error=f"page could not be opened ({exc})")
                continue
            try:
                notes = []
                page_w, page_h = page.get_size()                       # PDF points (1/72 inch)
                scan_dpi = _pdf_scan_dpi(page)
                dpi_known = scan_dpi is not None and 70 <= scan_dpi <= 1600
                # Render at the scan's own resolution (no needless resampling), within 150-400 dpi.
                render_dpi = float(np.clip(scan_dpi if dpi_known else settings.fallback_dpi, 150, 400))
                megapixels = (page_w / 72 * render_dpi) * (page_h / 72 * render_dpi) / 1e6
                if megapixels > settings.max_page_megapixels:
                    render_dpi *= math.sqrt(settings.max_page_megapixels / megapixels)
                    notes.append(f"very large page rendered at {render_dpi:.0f} dpi")
                try:
                    if page.get_textpage().count_chars() > 50:
                        notes.append("PDF already has a text layer (ignored - the page image is OCR'd)")
                except Exception:
                    pass
                bitmap = page.render(scale=render_dpi / 72.0, grayscale=not settings.remove_color_marks)
                pil = bitmap.to_pil()
                img = np.array(pil.convert("RGB" if settings.remove_color_marks else "L"))
            except Exception as exc:
                page.close()
                yield RawPage(number, None, 0.0, False, [], error=f"page could not be rendered ({exc})")
                continue
            page.close()
            yield RawPage(number, img, render_dpi, dpi_known, notes)
    finally:
        pdf.close()


def _pil_to_uint8(frame: "Image.Image", keep_color: bool) -> "np.ndarray":
    """Convert any Pillow image mode (1-bit fax, 16-bit, palette, CMYK, alpha) to uint8."""
    mode = frame.mode
    if mode in ("I;16", "I;16B", "I;16L", "I", "F"):
        arr = np.asarray(frame, dtype=np.float32)
        lo, hi = np.percentile(arr, (0.5, 99.5))
        return np.clip((arr - lo) * 255.0 / max(hi - lo, 1.0), 0, 255).astype(np.uint8)
    if mode in ("RGBA", "LA") or (mode == "P" and "transparency" in frame.info):
        rgba = frame.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        frame = Image.alpha_composite(white, rgba)
    return np.array(frame.convert("RGB" if keep_color else "L"))


def _iter_image_pages(path: Path, settings: Settings) -> Iterator[RawPage]:
    with Image.open(path) as im:
        n_frames = int(getattr(im, "n_frames", 1))
        for number in parse_page_selection(settings.page_selection, n_frames):
            try:
                raw = _read_image_frame(im, number, settings)
            except Exception as exc:
                raw = RawPage(number, None, 0.0, False, [], error=f"page could not be decoded ({exc})")
            yield raw


def _read_image_frame(im: "Image.Image", number: int, settings: Settings) -> RawPage:
    """Read one frame of a (possibly multi-page) image file, with its scan resolution."""
    im.seek(number - 1)
    notes = []
    # Pillow reports TIFF resolution as IFDRational objects -> convert to float.
    raw_dpi = im.info.get("dpi")
    try:
        x_dpi, y_dpi = (float(v) for v in raw_dpi) if raw_dpi else (0.0, 0.0)
    except (TypeError, ValueError):
        x_dpi, y_dpi = 0.0, 0.0
    if im.info.get("resolution_unit") == 3 or im.info.get("unit") == "cm":  # dots per cm
        x_dpi, y_dpi = x_dpi * 2.54, y_dpi * 2.54
    img = _pil_to_uint8(im, keep_color=settings.remove_color_marks)
    # Fax "normal" mode stores 204 x 98 dpi: stretch to square pixels first.
    if x_dpi > 0 and y_dpi > 0 and abs(x_dpi - y_dpi) / max(x_dpi, y_dpi) > 0.05:
        new_h = int(round(img.shape[0] * x_dpi / y_dpi))
        img = cv2.resize(img, (img.shape[1], new_h), interpolation=cv2.INTER_CUBIC)
        notes.append(f"non-square pixels ({x_dpi:.0f}x{y_dpi:.0f} dpi) resampled")
    dpi = max(x_dpi, y_dpi)
    # 72/96 dpi are software defaults, not real scan resolutions.
    dpi_known = 100 <= dpi <= 1600 and round(dpi) not in (72, 96)
    megapixels = img.shape[0] * img.shape[1] / 1e6
    if megapixels > settings.max_page_megapixels:
        f = math.sqrt(settings.max_page_megapixels / megapixels)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        dpi *= f
        notes.append("very large image scaled down")
    return RawPage(number, img, dpi if dpi_known else float(settings.fallback_dpi), dpi_known, notes)


# =============================================================================
# 5. IMAGE CLEAN-UP (PREPROCESSING)
#    Tested on degraded scans (photocopy, office scan, fax): deskew + background
#    flattening + a 3x3 median filter gave the best OCR word accuracy. Hard
#    black/white binarization was worse for the deep-learning OCR, so the OCR
#    sees a cleaned grayscale image.
# =============================================================================
@dataclass
class PreparedPage:
    ocr_image: "np.ndarray"    # cleaned grayscale image used for OCR and table detection
    view_image: "np.ndarray"   # same geometry, not flattened (figures, Word report)
    dpi: float
    rotation: int = 0          # degrees clockwise applied to make the page upright
    skew: float = 0.0          # degrees of rotation applied to remove skew
    notes: list = field(default_factory=list)


def _odd(n: float) -> int:
    n = max(1, int(round(n)))
    return n if n % 2 else n + 1


def to_grayscale(img: "np.ndarray", remove_color_marks: bool) -> "np.ndarray":
    if img.ndim == 2:
        return img
    if remove_color_marks:
        # Colored ink (red stamps, blue pen, highlighter) is bright in at least one color
        # channel while black print is dark in all of them: the brightest channel keeps
        # the black text and fades the colored marks.
        return img.max(axis=2).astype(np.uint8)
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def estimate_dpi_from_text(gray: "np.ndarray") -> Optional[float]:
    """Guess the scan resolution from the typical height of printed characters
    (used only when the file has no usable dpi information)."""
    scale = min(1.0, 1600.0 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    heights = [h for x, y, w, h, a in stats[1:] if 3 <= h <= 120 and w <= 3 * h and a >= 6]
    if len(heights) < 50:
        return None
    median_h = statistics.median(heights) / scale
    return float(np.clip(median_h / 0.085, 100, 800))  # ~0.085 in = typical glyph height at 10-12 pt


def rotate_bound(gray: "np.ndarray", angle: float, border: int) -> "np.ndarray":
    """Rotate by `angle` degrees (counter-clockwise) without cutting off the corners."""
    h, w = gray.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += new_w / 2 - w / 2
    m[1, 2] += new_h / 2 - h / 2
    return cv2.warpAffine(gray, m, (new_w, new_h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=int(border))


def _binary_thumbnail(gray: "np.ndarray", max_side: int = 1200) -> "np.ndarray":
    scale = max_side / max(gray.shape)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # ignore dark scanner/photocopier borders, they carry no text-line information
    m = max(2, int(0.03 * min(bw.shape)))
    bw[:m, :], bw[-m:, :], bw[:, :m], bw[:, -m:] = 0, 0, 0, 0
    return bw


def _profile_energy(bw: "np.ndarray", angle: float, axis: int = 1) -> float:
    """How 'striped' the image is along one axis after rotating by `angle`.
    Text lines produce sharp alternations between ink rows and blank rows."""
    if angle:
        m = cv2.getRotationMatrix2D((bw.shape[1] / 2, bw.shape[0] / 2), angle, 1.0)
        bw = cv2.warpAffine(bw, m, (bw.shape[1], bw.shape[0]), flags=cv2.INTER_NEAREST)
    profile = bw.sum(axis=axis, dtype=np.float64)
    return float(np.sum(np.diff(profile) ** 2))


def estimate_skew(gray: "np.ndarray", max_angle: float) -> float:
    """Projection-profile deskew: try angles coarse-to-fine and keep the one that makes
    text lines most horizontal. Accurate to ~0.05 degree; takes ~0.1 s per page."""
    bw = _binary_thumbnail(gray)
    if bw.sum() == 0:
        return 0.0
    coarse = np.arange(-max_angle, max_angle + 1e-6, 0.5)
    best = max(coarse, key=lambda a: _profile_energy(bw, a))
    fine = np.arange(best - 0.5, best + 0.5 + 1e-6, 0.05)
    best = max(fine, key=lambda a: _profile_energy(bw, a))
    return round(float(best), 2)


class OrientationDetector:
    """Decide whether a page must be turned 0/90/180/270 degrees clockwise.
    Uses the small RapidOrientation classifier when installed (Python <= 3.12);
    otherwise compares OCR confidence of the page read in both directions."""

    def __init__(self):
        self._model = None
        try:
            from rapid_orientation import RapidOrientation  # optional dependency
            _quiet_third_party_loggers()
            self._model = RapidOrientation()
        except Exception:
            self._model = None

    def detect(self, gray: "np.ndarray", ocr: "RapidOcrEngine") -> int:
        if self._model is not None:
            try:
                scale = min(1.0, 1024 / max(gray.shape))
                small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                label, _elapsed = self._model(cv2.cvtColor(small, cv2.COLOR_GRAY2RGB))[:2]
                # The classifier reports how far the page content is rotated CLOCKWISE
                # (verified: content turned 90 deg clockwise -> label "90"), so the
                # correction is the remaining angle to a full turn.
                rotation = (360 - int(label)) % 360
                if rotation:
                    # Rotated pages are rare and the classifier can confuse opposite directions on
                    # sparse pages (title pages): confirm against the opposite turn with OCR.
                    rotation = self._ocr_vote(gray, ocr, (rotation, (rotation + 180) % 360))
                return rotation
            except Exception:
                pass
        # Fallback without the classifier: find the reading direction, then let OCR decide.
        return self._ocr_vote(gray, ocr, (90, 270) if self._text_runs_vertically(gray, ocr) else (0, 180))

    @staticmethod
    def _text_runs_vertically(gray: "np.ndarray", ocr: "RapidOcrEngine") -> bool:
        """The OCR text detector draws wide boxes around horizontal text lines and tall boxes
        around lines of a page lying on its side."""
        scale = min(1.0, 1200 / max(gray.shape))
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        sizes = ocr.detect_boxes(small)
        wide = sum(1 for w, h in sizes if w > 1.8 * h)
        tall = sum(1 for w, h in sizes if h > 1.8 * w)
        return tall > 1.5 * max(wide, 1)

    @staticmethod
    def _ocr_vote(gray: "np.ndarray", ocr: "RapidOcrEngine", candidates: tuple) -> int:
        """Read a band of the page in each candidate direction; upright text reads confidently."""
        scale = min(1.0, 1400 / max(gray.shape))
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        best, best_score = candidates[0], -1.0
        for rot in candidates:
            img = rotate_right_angle(small, rot)
            h = img.shape[0]
            band = img[int(0.2 * h):int(0.65 * h), :]
            lines = ocr.read(band, min_conf=0.3)
            score = sum(ln.conf * len(ln.text) for ln in lines if ln.conf >= 0.6)
            if score > best_score:
                best, best_score = rot, score
        return best


def rotate_right_angle(img: "np.ndarray", clockwise_degrees: int) -> "np.ndarray":
    code = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(clockwise_degrees % 360)
    return img if code is None else cv2.rotate(img, code)


def remove_punch_holes(gray: "np.ndarray", dpi: float) -> tuple:
    """Paint over binder punch holes (round dark blobs near the page edges). OCR otherwise
    reads them as a large letter 'O' that gets glued to the text line next to it."""
    h, w = gray.shape[:2]
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # ignore the outermost strip, where photocopiers leave dark borders touching the holes
    border = max(2, int(0.02 * min(h, w)))
    bw[:border, :], bw[-border:, :], bw[:, :border], bw[:, -border:] = 0, 0, 0, 0
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = [cv2.boundingRect(c) for c in contours]
    paper = int(np.percentile(gray, 90))
    edge_zone = 0.9 * dpi
    removed = 0
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        diameter = (cw + ch) / 2.0
        if not (0.15 * dpi <= diameter <= 0.5 * dpi) or abs(cw - ch) > 0.25 * max(cw, ch):
            continue
        cx, cy = x + cw / 2.0, y + ch / 2.0
        if min(cx, w - cx, cy, h - cy) > edge_zone:
            continue                                          # not near an edge: could be a real symbol
        perimeter = cv2.arcLength(c, True)
        circularity = 4 * math.pi * cv2.contourArea(c) / max(perimeter * perimeter, 1.0)
        if circularity < 0.7:
            continue
        # isolated: no character-sized ink on the same line within 0.3 inch (a letter 'O' inside
        # a word has neighbours; specks and the tall dark photocopier edge are ignored)
        neighbour = False
        for ox, oy, ow, oh in rects:
            if (ox, oy, ow, oh) == (x, y, cw, ch) or not (0.25 * diameter <= oh <= 1.5 * diameter) or ow > 3 * diameter:
                continue
            if abs((oy + oh / 2.0) - cy) < diameter and min(abs(ox - (x + cw)), abs(x - (ox + ow))) < 0.3 * dpi:
                neighbour = True
                break
        if neighbour:
            continue
        radius = int(diameter / 2 + 0.03 * dpi)
        ring_mask = np.zeros(gray.shape, np.uint8)
        cv2.circle(ring_mask, (int(cx), int(cy)), radius + int(0.08 * dpi), 255, -1)
        cv2.circle(ring_mask, (int(cx), int(cy)), radius, 0, -1)
        local = gray[(ring_mask > 0) & (bw == 0)]
        fill = int(np.median(local)) if local.size > 20 else paper
        cv2.circle(gray, (int(cx), int(cy)), radius, fill, -1)
        removed += 1
    return gray, removed


def flatten_background(gray: "np.ndarray", dpi: float) -> "np.ndarray":
    """Remove stains, shadows, yellowing and uneven lighting: estimate the paper
    brightness around every pixel (ink removed by a max-filter) and divide it out."""
    k = _odd(max(7, dpi * 0.035))                  # wider than a pen stroke (~0.035 in)
    background = cv2.dilate(gray, np.ones((k, k), np.uint8))
    background = cv2.medianBlur(background, _odd(max(21, dpi * 0.1)))
    flat = cv2.divide(gray, background, scale=255)
    # stretch contrast so the darkest ink is close to black again
    lo = float(np.percentile(flat, 0.5))
    if lo < 245:
        flat = np.clip((flat.astype(np.float32) - lo) * (255.0 / (255.0 - lo)), 0, 255).astype(np.uint8)
    return flat


def prepare_page(raw: RawPage, settings: Settings, orientation: OrientationDetector,
                 ocr: "RapidOcrEngine") -> PreparedPage:
    notes = list(raw.notes)
    gray = to_grayscale(raw.image, settings.remove_color_marks)
    dpi = raw.dpi
    if not raw.dpi_known:
        guess = estimate_dpi_from_text(gray)
        if guess:
            dpi = guess
            notes.append(f"resolution unknown - estimated {dpi:.0f} dpi from text size")

    # 1) resolution normalization (the OCR model is most accurate/fast around target_dpi)
    scale = float(np.clip(settings.target_dpi / max(dpi, 1.0), 0.35, 2.0))
    if abs(scale - 1.0) > 0.12:
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interp)
        dpi *= scale

    paper = int(np.percentile(gray, 90))
    # 2) page orientation (sideways / upside-down scans)
    rotation = 0
    if settings.auto_rotate:
        rotation = orientation.detect(gray, ocr)
        if rotation:
            gray = rotate_right_angle(gray, rotation)
            notes.append(f"page turned {rotation} degrees clockwise")

    # 3) deskew
    skew = 0.0
    if settings.deskew:
        skew = estimate_skew(gray, settings.max_skew_degrees)
        if abs(skew) >= 0.1:
            gray = rotate_bound(gray, skew, paper)
        else:
            skew = 0.0

    # 4) binder punch holes
    gray, holes = remove_punch_holes(gray, dpi)
    if holes:
        notes.append(f"{holes} punch hole(s) removed")

    view = gray
    # 5) background flattening + light denoise
    ocr_img = flatten_background(gray, dpi) if settings.clean_background else gray.copy()
    if settings.denoise:
        ocr_img = cv2.medianBlur(ocr_img, 3)
    return PreparedPage(ocr_img, view, dpi, rotation, skew, notes)


# =============================================================================
# 6. OCR AND PAGE LAYOUT ANALYSIS  (the "standard" engine)
# =============================================================================

# ---- 6a. Text patterns shared by layout analysis and requirement extraction ----
# Paragraph / heading numbers: "3", "3.2", "3.2.1.4", "A.1.2" (optionally followed by a period)
RE_PARA_NUM = re.compile(r"^(?P<num>(?:\d{1,2}(?:\.(?:\d{1,3}|[lIi|](?=[.\s'`·]))){0,7}|[A-Z](?:\.\d{1,3}){1,7}))(?P<dot>\.?)(?:\s+|['`´’·,]\s*(?=[A-Z]))(?P<rest>\S.*)$", re.S)
# List markers: a.  a)  (a)  (1)  1)  iv)  (iv)  bullets.  "1." is handled separately.
RE_LIST_MARKER = re.compile(
    r"^(?P<marker>\([a-z]\)|[a-z][.)]|\(\d{1,2}\)|\d{1,2}\)|\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)\)"
    r"|(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)[.)]|[•●▪■‣⁃∙·◦]"
    r"|[–—*\-o](?=\s+[A-Z0-9]))"          # dash / 'o' bullets only before a capital or digit
    r"(?:\s+|(?<=\))(?=[A-Z]))(?P<rest>\S.*)$", re.S)
RE_BARE_MARKER = re.compile(r"^\s*(?:\(?[a-z]\)|[a-z]\.|\(?\d{1,2}[.)]|\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\)|[•·◦*\-o])\s*$")
RE_NUMBERED_ITEM = re.compile(r"^(?P<marker>\d{1,2}\.)\s+(?P<rest>\S.*)$", re.S)
# Captions: "TABLE II. Title", "Figure 3-1: Title", "FIG. 4 Title", "Exhibit A - Title"
RE_CAPTION = re.compile(
    r"^(?P<kind>TABLE|Table|FIGURE|Figure|FIG\.?|Fig\.?|EXHIBIT|Exhibit|CHART|Chart|DRAWING|Drawing|PLATE|Plate)"
    r"\s*(?P<num>(?:[A-Z]-)?\d{1,3}(?:[.\-]\d{1,3})*[A-Za-z]?|[IVXLCl1|]{1,8}(?=[\s.:\-–—]))"
    r"(?P<delim>\s*[.:\-–—]+)?\s*(?P<title>.*)$", re.S)
RE_CONTINUED = re.compile(r"\(?\s*(?:continued|cont'?d\.?|concluded)\s*\)?\s*\.?$", re.I)
# Explicit requirement identifiers: [SRS-101], SRS-103:, PRF-201, SYS_PWR_012 ...
_ID_STOP = (r"(?:MIL|DOD|DI|NPR|NPD|NASA|ISO|IEC|IEEE|SAE|ASTM|ANSI|RTCA|STANAG|FED|JSSG|ECSS|AES|SHA|RS|DO|AS|MS|"
            r"NAS|ARINC|TIA|EIA|UL|NFPA|CFR|FAR|DFARS|IPC|ASME|AWG|UTC|GMT|CAGE|NSN|DTL|PRF-\d{5,}|TB[DRSC])")
RE_REQ_ID = r"(?!" + _ID_STOP + r"[-_ ])[A-Z][A-Z0-9]{0,9}(?:[-_.][A-Z0-9]{1,9}){0,3}[-_.]?\d{1,6}[a-z]?"
RE_LEADING_ID = re.compile(r"^\s*[\[(]?(?P<id>" + RE_REQ_ID + r")[\])]?\s*(?:[:.\-–—]\s*|\s+)(?P<rest>\S.*)$", re.S)
RE_TRAILING_ID = re.compile(r"\s*[\[(](?P<id>" + RE_REQ_ID + r")[\])]\s*\.?$")
RE_ID_CELL = re.compile(r"^\s*[\[(]?(?:" + RE_REQ_ID + r"|(?:\d{1,2}(?:\.\d{1,3}){1,7}\.?)|[A-Z]{1,4}-?\d{1,4}[a-z]?)[\])]?\s*$")
RE_PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?[-–—]?\s*(?:\d{1,4}|[ivxlcdm]{1,7})\s*[-–—]?\s*(?:of\s*\d{1,4})?\s*$", re.I)
RE_TERMINAL = re.compile(r"[.:;!?][\"')\]]*\s*$")
OCR_KEYWORD_REPAIRS = [
    # (correct word, pattern of OCR-garbled spellings). Whole tokens only; real English
    # words such as "shell", "small", "wall", "most" do NOT match.
    ("shall", re.compile(r"(?<![A-Za-z0-9])[sS5$][hbn][aA@][l1I|!]{2}(?![A-Za-z0-9])")),
    ("should", re.compile(r"(?<![A-Za-z0-9])[sS5][hb][o0]u[l1I|!][dc](?![A-Za-z0-9])")),
    ("must", re.compile(r"(?<![A-Za-z0-9])(?:m|rn|nn)[uv][s5]t(?![A-Za-z0-9])")),
    ("will", re.compile(r"(?<![A-Za-z0-9])(?:[wW]|vv)[i1l|!][l1I|!]{2}(?![A-Za-z0-9])")),
]
RE_UNIT = re.compile(r"(?:[kMGmu\u00b5]?(?:A|V|W|Hz|VA|VAC|VDC|Vdc|Vac|s|ms|g|m|Pa|N|J|F|H|dB|dBm|dBi|bps|B|b)|"
                     r"mm|cm|km|nmi|kg|lb|lbs|oz|in|ft|psi|psig|psia|rpm|\u00b0[CFK]?|%|ohms?|\u03a9|kts|knots|AWG|min|hr|hrs)")

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
             "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "‐": "-", "‑": "-"}


def clean_para_number(num: str) -> str:
    """'3.2.i.4' -> '3.2.1.4' (a letter l/I/i/| inside a paragraph number is a misread 1)."""
    return re.sub(r"(?<=\.)[lIi|](?=\.|$)", "1", num)


def normalize_ocr_text(text: str) -> str:
    """Tidy raw OCR output without changing its meaning (no NFKC: that would turn m² into m2)."""
    text = unicodedata.normalize("NFC", text or "")
    for bad, good in LIGATURES.items():
        text = text.replace(bad, good)
    text = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch)[0] != "C")
    return re.sub(r"[ \t]+", " ", text).strip()


_FILE_EXTENSIONS = {"xml", "txt", "csv", "pdf", "doc", "docx", "xls", "xlsx", "exe", "dll", "cfg", "ini", "log", "dat",
                    "bin", "htm", "html", "com", "org", "net", "gov", "mil", "edu", "json", "yaml", "yml", "py"}


def strip_accents(text: str) -> str:
    """'telémetry' -> 'telemetry'. Only Latin letters lose accents; symbols such as °, ±, µ, ² stay."""
    out = []
    for ch in text:
        if ord(ch) > 127 and unicodedata.category(ch).startswith("L") and "LATIN" in unicodedata.name(ch, ""):
            base = unicodedata.normalize("NFD", ch)[0]
            out.append(base if base.isascii() else ch)
        else:
            out.append(ch)
    return "".join(out)


def remove_ocr_specks(text: str) -> str:
    """Remove dots/apostrophes that are paper specks read as punctuation on photocopies and
    faxes ("The.power", "radar' shall", "finished'in", ".interface"). Numbers, decimals,
    abbreviations (e.g.), possessives (operator's) and file names (config.xml) are left alone."""
    # speck read as a middle dot next to a word ("be·as", ".·The"); "N·m" (units) is kept
    text = re.sub(r"(?:(?<=[a-z]{2})|(?<=[.,;:]))·(?=[A-Za-z])", " ", text)
    # dot glued between two ordinary lowercase words: "steady-state.voltages" -> "steady-state voltages"
    text = re.sub(r"(?<![\w.])([A-Za-z][a-z]{2,})\.([a-z]{2,})(?!\w|\.\w)",
                  lambda m: m.group(0) if m.group(2) in _FILE_EXTENSIONS or m.group(1).lower() == "www"
                  else f"{m.group(1)} {m.group(2)}", text)
    # dot stuck to the front of a word: "The .interface" -> "The interface"
    text = re.sub(r"(?:(?<=\s)|^)\.(?=[a-z]{3,}\b)", "", text)
    # apostrophe speck after a word (not a plural possessive): "radar' shall" -> "radar shall"
    text = re.sub(r"(?<=[A-Za-rt-z])['’`](?=\s|[.,;:]|$)", "", text)
    # colon/dot/quote specks between a word and a number or unit: "of:1" "450:kg" "16.AWG" 'Aircraft"Electric'
    text = re.sub(r"(?<=[a-z]):(?=\d)|(?<=\d):(?=[a-z]{2})|(?<=\d)\.(?=[A-Z]{2,}\b)|(?<=[a-z])\"(?=[A-Z])", " ", text)
    # ",." speck after a word: "(I),.analysis" -> "(I), analysis"  (".," is kept: "i.e., etc.,")
    text = re.sub(r"(?<=[A-Za-z)\]]),\.(?=\s*[a-z])", ", ", text)
    # doubled period after a word ("II..") and a speck apostrophe in front of a lowercase word ("'mode")
    text = re.sub(r"(?<=[A-Za-z)\]])\.\.(?!\.)", ".", text)
    text = re.sub(r"(?:(?<=\s)|^)['`](?=[a-z]{2,}\b)(?![a-z]*['`])", "", text)
    # apostrophe speck between words: "finished'in" -> "finished in" (contractions are kept)
    text = re.sub(r"(?<=[A-Za-z0-9][a-z0-9])['’`](?!(?:s|t|ll|re|ve|d|m)\b)(?=[a-z]{2,})", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def word_count(text: str) -> int:
    return len(text.split())


def _quiet_third_party_loggers():
    for name in ("RapidOCR", "rapidocr", "rapid_orientation", "img2table", "onnxruntime", "docling"):
        logging.getLogger(name).setLevel(logging.ERROR)


# ---- 6b. OCR engine -------------------------------------------------------------
class RapidOcrEngine:
    """PaddleOCR PP-OCRv6 text detection + recognition through RapidOCR / ONNX Runtime.
    The PP-OCRv6 'small' models are bundled inside the rapidocr pip package."""

    def __init__(self, settings: Settings):
        try:
            from rapidocr import ModelType, RapidOCR
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("RapidOCR is not installed. Run: python -m pip install -r requirements.txt") from exc
        params = {
            "Global.log_level": "error",
            "Global.use_cls": False,          # page orientation is already fixed; faster and safer
            "Global.max_side_len": 4096,      # never shrink a normal page before OCR (hurts accuracy)
            "Det.limit_type": "max",
            "Det.limit_side_len": 2600,       # cap detection resolution for very large drawings
        }
        size = (settings.ocr_model_size or "small").lower()
        if size in ("tiny", "medium"):        # these sizes download once from ModelScope
            model_type = ModelType.TINY if size == "tiny" else ModelType.MEDIUM
            params.update({"Det.model_type": model_type, "Rec.model_type": model_type})
        if settings.ocr_threads > 0:
            params["EngineConfig.onnxruntime.intra_op_num_threads"] = int(settings.ocr_threads)
        _quiet_third_party_loggers()
        self.engine = RapidOCR(params=params)
        _quiet_third_party_loggers()
        self.settings = settings

    def detect_boxes(self, gray: "np.ndarray") -> list:
        """Text-line detection only (no recognition): [(width, height)] of each line box."""
        rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB) if gray.ndim == 2 else gray
        res = self.engine(rgb, use_det=True, use_cls=False, use_rec=False, box_thresh=0.5, unclip_ratio=1.6)
        boxes = getattr(res, "boxes", None)
        if boxes is None:
            return []
        return [(float(np.ptp(np.asarray(b)[:, 0])), float(np.ptp(np.asarray(b)[:, 1]))) for b in boxes]

    def read(self, gray: "np.ndarray", min_conf: Optional[float] = None) -> list:
        """OCR one image -> list of Line (each with word boxes and confidences)."""
        rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB) if gray.ndim == 2 else gray
        min_conf = self.settings.min_text_confidence if min_conf is None else min_conf
        # NOTE: RapidOCR resets text_score/box_thresh/unclip_ratio on every call, so pass all three.
        res = self.engine(rgb, use_det=True, use_cls=False, use_rec=True, text_score=min_conf,
                          box_thresh=0.5, unclip_ratio=1.6, return_word_box=True)
        if res is None or res.boxes is None or res.txts is None:
            return []
        word_results = getattr(res, "word_results", None) or ()
        lines = []
        for i, (quad, raw_text, score) in enumerate(zip(res.boxes, res.txts, res.scores)):
            text = normalize_ocr_text(raw_text)
            if not text:
                continue
            q = np.asarray(quad, dtype=float)
            box = (int(q[:, 0].min()), int(q[:, 1].min()), int(math.ceil(q[:, 0].max())), int(math.ceil(q[:, 1].max())))
            words = []
            if i < len(word_results) and word_results[i]:
                for entry in word_results[i]:
                    try:
                        w_text, w_score, w_quad = normalize_ocr_text(entry[0]), float(entry[1]), np.asarray(entry[2], dtype=float)
                    except (TypeError, ValueError, IndexError):
                        words = []
                        break
                    if w_text:
                        words.append(Word(w_text, w_score, (int(w_quad[:, 0].min()), int(w_quad[:, 1].min()),
                                                            int(math.ceil(w_quad[:, 0].max())), int(math.ceil(w_quad[:, 1].max())))))
            # word boxes must spell the same text as the line, otherwise estimate them
            if not words or "".join(w.text for w in words).replace(" ", "") != text.replace(" ", ""):
                words = _estimate_word_boxes(text, box, float(score))
            lines.append(Line(text, float(score), box, words))
        return lines


def _estimate_word_boxes(text: str, box: Box, conf: float) -> list:
    """Split a line box into word boxes proportionally to character counts."""
    x0, y0, x1, y1 = box
    n = max(len(text), 1)
    words = []
    for m in re.finditer(r"\S+", text):
        wx0 = x0 + (x1 - x0) * m.start() / n
        wx1 = x0 + (x1 - x0) * m.end() / n
        words.append(Word(m.group(), conf, (int(wx0), y0, int(math.ceil(wx1)), y1)))
    return words


# ---- 6c. Tables (img2table finds the grid; our OCR words fill the cells) --------------
def detect_tables(gray: "np.ndarray", lines: list, dpi: float, settings: Settings) -> list:
    """Return [(TableData, table_box, set_of_line_indexes_inside, caption_lines)] for one page.
    img2table finds the table grid (ruling lines, or aligned text for borderless tables);
    the words we already OCR'd are then placed into the cells."""
    try:
        from img2table.document import Image as I2TImage
        from img2table.ocr._types import OCRData, OCRInstance
    except Exception as exc:  # pragma: no cover
        LOG.warning("Table detection unavailable (img2table could not be imported: %s)", exc)
        return []

    records = []
    for li, ln in enumerate(lines):
        for wi, wd in enumerate(ln.words):
            records.append({"id": f"w{li}_{wi}", "parent": f"l{li}", "value": wd.text,
                            "confidence": max(1, int(round(wd.conf * 100))),
                            "x1": int(wd.box[0]), "y1": int(wd.box[1]), "x2": int(wd.box[2]), "y2": int(wd.box[3])})

    class _PrecomputedOCR(OCRInstance):
        """Hands img2table the words we already read, so each page is OCR'd only once."""

        def of(self, document):
            return OCRData(records={0: records}) if records else None

    ok, png = cv2.imencode(".png", gray)

    def run_img2table(borderless: bool) -> list:
        try:
            return I2TImage(src=png.tobytes(), detect_rotation=False).extract_tables(
                ocr=_PrecomputedOCR() if records else None, implicit_rows=False, implicit_columns=False,
                borderless_tables=borderless, min_confidence=1)
        except Exception as exc:
            LOG.warning("Table detection failed on a page (%s) - continuing without tables", exc)
            return []

    # Pass 1: ruled tables (reliable). Pass 2: borderless candidates, which must pass
    # stricter checks because aligned lists and indented text can look like tables.
    candidates = [(et, False) for et in run_img2table(False)]
    if settings.borderless_tables:
        ruled_boxes = [(et.bbox.x1, et.bbox.y1, et.bbox.x2, et.bbox.y2) for et, _ in candidates]
        for et in run_img2table(True):
            eb = (et.bbox.x1, et.bbox.y1, et.bbox.x2, et.bbox.y2)
            if not any(box_intersection(eb, rb) > 0.3 * min(box_area(eb), box_area(rb)) for rb in ruled_boxes):
                candidates.append((et, True))

    page_area = gray.shape[0] * gray.shape[1]
    results = []
    claimed = set()
    for et, borderless in candidates:
        rows = list(et.content.values())
        if len(rows) < 2 or max((len(r) for r in rows), default=0) < 2:
            continue
        n_cols = max(len(r) for r in rows)
        cell_boxes = [[(int(c.bbox.x1), int(c.bbox.y1), int(c.bbox.x2), int(c.bbox.y2)) for c in r]
                      + [None] * (n_cols - len(r)) for r in rows]
        tbox = (int(et.bbox.x1), int(et.bbox.y1), int(et.bbox.x2), int(et.bbox.y2))
        pad = 0.02 * dpi
        inside = {i for i, ln in enumerate(lines) if box_center_inside(ln.box, tbox, pad) and i not in claimed}
        inside_order = sorted(inside)
        grid, conf, merges, n_unique, n_filled, words_in_cells, words_grid, row_lines = _fill_cells(
            cell_boxes, [lines[i] for i in inside_order])

        # A caption that img2table swallowed as the first/last row is given back. It may fill one merged
        # cell or be split over a few cells ("TABLE II." | "Interface signals"), so the row's joined text
        # is tested. A "list of tables" (many rows starting "Table n") is left alone.
        caption_lines = []
        for edge in (0, -1):
            if len(grid) < 3:
                break
            distinct = list(dict.fromkeys(c for c in grid[edge] if c))   # a merged cell repeats its text
            joined = " ".join(distinct)
            other_caption_rows = sum(1 for row in grid if row is not grid[edge] and row and RE_CAPTION.match(row[0] or ""))
            if not (distinct and len(distinct) <= 3 and word_count(joined) <= 40
                    and RE_CAPTION.match(joined) and other_caption_rows == 0):
                continue
            row_index = edge % len(grid)
            # every line whose words were placed in that row (a caption can wrap over several lines)
            elsewhere = set().union(*(row_lines[r] for r in range(len(row_lines)) if r != row_index))
            given_back = sorted(row_lines[row_index] - elsewhere)
            if not given_back:
                continue                                # its lines also fill other rows: leave the table as it is
            caption_lines.extend(inside_order[li] for li in given_back)
            del grid[edge], conf[edge], cell_boxes[edge], words_grid[edge], row_lines[edge]
            merges = _merges_without_row(merges, row_index)
        if caption_lines:
            inside -= set(caption_lines)
            # the table now starts/ends at its first/last real row (so the caption sits next to it)
            remaining = [cb for row in cell_boxes for cb in row if cb]
            if remaining:
                tbox = (tbox[0], min(cb[1] for cb in remaining), tbox[2], max(cb[3] for cb in remaining))

        if n_filled < max(2, 0.25 * n_unique):
            continue                                    # mostly empty grid: a drawing or form, not a table
        if box_area(tbox) > 0.6 * page_area and words_in_cells / max(n_filled, 1) > 25:
            continue                                    # a page border drawn around ordinary paragraphs
        if borderless and not _plausible_borderless_table(grid, n_unique, n_filled):
            continue
        claimed |= inside
        table = TableData(grid=grid, conf=conf, merges=merges, cell_boxes=cell_boxes, cell_words=words_grid,
                          header_rows=1 if _looks_like_header(grid[0]) else 0)
        results.append((table, tbox, inside, caption_lines))
    if settings.borderless_tables:
        results += detect_aligned_tables(lines, dpi, claimed)
    return results


def detect_aligned_tables(lines: list, dpi: float, claimed: set) -> list:
    """Borderless tables recognised from text alignment alone (the idea behind Camelot's
    'stream' mode): consecutive rows that break into the same columns. Works on noisy
    photocopies where image-based detection fails, because it only needs the OCR boxes."""
    free = [i for i in range(len(lines)) if i not in claimed]
    if len(free) < 6:
        return []
    char_h = statistics.median(lines[i].height for i in free)
    # rows of OCR line boxes; separate boxes on one row are candidate cells
    rows = []
    for row in _rows_of([lines[i] for i in free]):
        ids = [next(i for i in free if lines[i] is ln) for ln in row]
        segs = []
        for i in ids:                      # also split a box at very wide word gaps
            words = sorted(lines[i].words, key=lambda w: w.box[0])
            current = [words[0]] if words else []
            for w in words[1:]:
                if w.box[0] - current[-1].box[2] > 2.0 * char_h:
                    segs.append((i, current))
                    current = [w]
                else:
                    current.append(w)
            if current:
                segs.append((i, current))
        box = box_union(lines[i].box for i in ids)
        rows.append({"ids": ids, "segs": segs, "box": box})

    results = []
    k = 0
    while k < len(rows):
        if len(rows[k]["segs"]) < 2:
            k += 1
            continue
        run = [k]
        m = k + 1
        while m < len(rows):
            gap = rows[m]["box"][1] - rows[run[-1]]["box"][3]
            if gap > 2.2 * char_h:
                break
            if len(rows[m]["segs"]) >= 2:
                run.append(m)
            elif m + 1 < len(rows) and len(rows[m + 1]["segs"]) >= 2 and rows[m + 1]["box"][1] - rows[m]["box"][3] <= 2.2 * char_h:
                run.append(m)             # a wrapped cell line between two table rows
            else:
                break
            m += 1
        # a wrapped cell line directly below the last row ("... Considerations and" / "Laboratory Tests")
        if (m < len(rows) and len(rows[m]["segs"]) == 1 and len(rows[run[-1]]["segs"]) >= 2
                and rows[m]["box"][1] - rows[run[-1]]["box"][3] <= 0.8 * char_h
                and rows[m]["box"][0] > min(w.box[0] for _, ws in rows[run[-1]]["segs"] for w in ws) + 2 * char_h):
            run.append(m)
            m += 1
        k = m
        multi = [r for r in run if len(rows[r]["segs"]) >= 2]
        if len(multi) < 3:
            continue
        # column bands = merged horizontal extents of the cells of all multi-cell rows
        bands = _merge_intervals([(min(w.box[0] for w in ws), max(w.box[2] for w in ws))
                                  for r in multi for _, ws in rows[r]["segs"]], 0.6 * char_h)
        if len(bands) < 2:
            continue
        grid, conf, words_grid, used = [], [], [], set()
        for r in run:
            cells = [[] for _ in bands]
            for i, ws in rows[r]["segs"]:
                for w in ws:
                    cx = (w.box[0] + w.box[2]) / 2
                    col = min(range(len(bands)), key=lambda b: 0 if bands[b][0] <= cx <= bands[b][1]
                              else min(abs(cx - bands[b][0]), abs(cx - bands[b][1])))
                    cells[col].append(w)
                used.add(i)
            texts = [_join_words_in_reading_order(c) for c in cells]
            confs = [min((w.conf for w in c), default=1.0) for c in cells]
            if len(rows[r]["segs"]) < 2 and grid:          # wrapped line: add to the row above
                for c, t in enumerate(texts):
                    if t:
                        grid[-1][c] = (grid[-1][c] + " " + t).strip()
                        conf[-1][c] = min(conf[-1][c], confs[c])
                        words_grid[-1][c] += [[w.text, round(w.conf, 4)] for w in cells[c]]
                continue
            grid.append(texts)
            conf.append(confs)
            words_grid.append([[[w.text, round(w.conf, 4)] for w in c] for c in cells])
        n_cells = len(grid) * len(bands)
        filled = sum(1 for row in grid for c in row if c)
        words_per_cell = sum(word_count(c) for row in grid for c in row) / max(filled, 1)
        if filled < 0.6 * n_cells or words_per_cell > 10 or not _plausible_borderless_table(grid, n_cells, filled):
            continue
        tbox = box_union(lines[i].box for i in used)
        table = TableData(grid=grid, conf=conf, cell_words=words_grid, header_rows=1 if _looks_like_header(grid[0]) else 0)
        results.append((table, tbox, used, []))
        claimed |= used
    return results


def _fill_cells(cell_boxes: list, table_lines: list) -> tuple:
    """Assign each OCR word to the grid cell it overlaps most; merged cells share one box."""
    unique = {}
    for r, row in enumerate(cell_boxes):
        for c, cb in enumerate(row):
            if cb is not None:
                unique.setdefault(cb, []).append((r, c))
    cells = list(unique.keys())
    cell_words = defaultdict(list)
    cell_lines = defaultdict(set)                         # cell -> indexes of the table_lines its words came from
    words = [wd for ln in table_lines for wd in ln.words]
    word_line = [li for li, ln in enumerate(table_lines) for _ in ln.words]
    if cells and words:
        C = np.asarray(cells, dtype=np.float64)
        centers = np.stack([(C[:, 0] + C[:, 2]) / 2, (C[:, 1] + C[:, 3]) / 2], axis=1)
        for start in range(0, len(words), 400):          # chunks keep memory small on huge tables
            chunk = words[start:start + 400]
            W = np.asarray([w.box for w in chunk], dtype=np.float64)
            ix = np.clip(np.minimum(W[:, None, 2], C[None, :, 2]) - np.maximum(W[:, None, 0], C[None, :, 0]), 0, None)
            iy = np.clip(np.minimum(W[:, None, 3], C[None, :, 3]) - np.maximum(W[:, None, 1], C[None, :, 1]), 0, None)
            area = np.maximum((W[:, 2] - W[:, 0]) * (W[:, 3] - W[:, 1]), 1.0)
            ratio = ix * iy / area[:, None]
            best = ratio.argmax(axis=1)
            wc = np.stack([(W[:, 0] + W[:, 2]) / 2, (W[:, 1] + W[:, 3]) / 2], axis=1)
            nearest = np.abs(wc[:, None, :] - centers[None, :, :]).sum(axis=2).argmin(axis=1)
            for k, wd in enumerate(chunk):
                # a word sitting on a ruling line (little overlap with any cell) goes to the nearest cell
                idx = best[k] if ratio[k, best[k]] >= 0.3 else nearest[k]
                cell_words[cells[int(idx)]].append(wd)
                cell_lines[cells[int(idx)]].add(word_line[start + k])
    n_rows, n_cols = len(cell_boxes), max((len(r) for r in cell_boxes), default=0)
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    conf = [[1.0 for _ in range(n_cols)] for _ in range(n_rows)]
    words_grid = [[[] for _ in range(n_cols)] for _ in range(n_rows)]
    row_lines = [set() for _ in range(n_rows)]           # grid row -> indexes of the lines placed in it
    merges = []
    for cb, positions in unique.items():
        for r, _c in positions:
            row_lines[r] |= cell_lines.get(cb, set())
        words = cell_words.get(cb, [])
        text = _join_words_in_reading_order(words)
        cmin = min((w.conf for w in words), default=1.0)
        for r, c in positions:
            grid[r][c], conf[r][c] = text, cmin
            words_grid[r][c] = [[w.text, round(w.conf, 4)] for w in words]
        if len(positions) > 1:
            rs, cs = [p[0] for p in positions], [p[1] for p in positions]
            merges.append((min(rs), min(cs), max(rs), max(cs)))
    n_filled = sum(1 for cb in unique if cell_words.get(cb))
    return grid, conf, merges, len(unique), n_filled, sum(len(v) for v in cell_words.values()), words_grid, row_lines


def _pages_text(pages: list) -> str:
    """[1, 2, 3, 7] -> '1-3, 7' (shortened after a few ranges)."""
    ranges = []
    for p in sorted(set(pages)):
        if ranges and p == ranges[-1][1] + 1:
            ranges[-1][1] = p
        else:
            ranges.append([p, p])
    parts = [str(a) if a == b else f"{a}-{b}" for a, b in ranges]
    return ", ".join(parts[:6]) + (" ..." if len(parts) > 6 else "")


def _merges_without_row(merges: list, row: int) -> list:
    """Merged-cell ranges (r0, c0, r1, c1) after grid row `row` was deleted: later rows move up one,
    a range that covered the deleted row shrinks, and a range left with a single cell is dropped."""
    out = []
    for r0, c0, r1, c1 in merges:
        if r0 > row:
            r0, r1 = r0 - 1, r1 - 1
        elif r1 >= row:
            r1 -= 1
        if r1 >= r0 and (r1 > r0 or c1 > c0):
            out.append((r0, c0, r1, c1))
    return out


def _plausible_borderless_table(grid: list, n_unique: int, n_filled: int) -> bool:
    """Borderless candidates must look like real tables, not lists, headings or prose that happens
    to line up (monospaced typewriter text lines up very well)."""
    n_rows, n_cols = len(grid), max(len(r) for r in grid)
    if n_rows < 3 or n_cols < 2 or n_cols > 15 or n_filled < 0.5 * n_unique:
        return False
    first_col = [r[0] for r in grid if r and r[0]]
    if first_col and sum(1 for c in first_col if RE_BARE_MARKER.match(c)) >= 0.5 * len(first_col):
        return False                                   # "a. | Search mode." -> that is a list
    prose_rows = 0
    for row in grid:
        cells = [c for c in row if c]
        for cell in cells:
            m = RE_PARA_NUM.match(cell)
            if m and "." in m.group("num") + m.group("dot") and m.group("rest")[:1].isalpha():
                return False                           # "4.1 Verification ..." : a numbered paragraph or heading
            if _is_heading_text(cell) and word_count(cell) >= 2 and RE_PARA_NUM.match(cell):
                return False                           # "4. VERIFICATION"
        # one sentence running across cells: "manufactured and" | "finished" | "in accordance with"
        if any(re.search(r"[a-z,]$", a) and re.match(r"[a-z]", b) and word_count(a) + word_count(b) >= 3
               for a, b in zip(cells, cells[1:])):
            prose_rows += 1
    if prose_rows >= max(1, 0.3 * n_rows):
        return False
    well_filled = sum(1 for c in range(n_cols) if sum(1 for r in grid if c < len(r) and r[c]) >= 0.6 * n_rows)
    return well_filled >= 2


def _join_words_in_reading_order(words: list) -> str:
    """Order words by visual rows (top to bottom), then left to right."""
    if not words:
        return ""
    words = sorted(words, key=lambda w: (w.box[1] + w.box[3]) / 2)
    med_h = statistics.median(w.box[3] - w.box[1] for w in words)
    rows, current, current_y = [], [], None
    for w in words:
        cy = (w.box[1] + w.box[3]) / 2
        if current and abs(cy - current_y) > 0.5 * med_h:
            rows.append(current)
            current = []
        current.append(w)
        current_y = statistics.fmean((x.box[1] + x.box[3]) / 2 for x in current)
    rows.append(current)
    parts = []
    for row in rows:
        row_text = " ".join(w.text for w in sorted(row, key=lambda w: w.box[0]))
        if parts and parts[-1].endswith("-") and row_text[:1].islower():
            parts[-1] = parts[-1] + row_text       # word hyphenated across lines inside a cell
        else:
            parts.append(row_text)
    return " ".join(parts).strip()


def _looks_like_header(row: list) -> bool:
    cells = [c for c in row if c and c.strip()]
    if not cells:
        return False
    short = all(word_count(c) <= 6 for c in cells)
    numeric = sum(1 for c in cells if re.fullmatch(r"[\d.,%\-+ ]+", c)) / len(cells)
    # "Shall Statement" is a header label; "The unit shall ..." is a requirement sentence
    return short and numeric < 0.5 and not any(word_count(c) > 3 and _modal_re().search(c) for c in cells)


# ---- 6d. Figures (drawings, photos, diagrams) -----------------------------------------
def detect_figures(prep: PreparedPage, lines: list, table_boxes: list) -> list:
    """Find non-text graphics: ink that remains after masking text lines and tables."""
    dpi = prep.dpi
    view = prep.view_image
    h, w = view.shape
    _, bw = cv2.threshold(prep.ocr_image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    bw = cv2.bitwise_or(bw, (view < 140).astype(np.uint8) * 255)     # keep mid-gray photos too
    for ln in lines:                                                   # remove text
        p = int(0.25 * ln.height)
        cv2.rectangle(bw, (ln.box[0] - p, ln.box[1] - p), (ln.box[2] + p, ln.box[3] + p), 0, -1)
    tpad = int(0.04 * dpi)
    for tb in table_boxes:                                             # remove tables (incl. their border lines)
        cv2.rectangle(bw, (tb[0] - tpad, tb[1] - tpad), (tb[2] + tpad, tb[3] + tpad), 0, -1)
    edge = int(0.035 * min(h, w))                                      # scanner edges / punch holes margin
    bw[:edge, :], bw[-edge:, :], bw[:, :edge], bw[:, -edge:] = 0, 0, 0, 0
    k = _odd(dpi * 0.03)
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    parts = []
    for x, y, cw, ch, area in stats[1:]:
        if max(cw, ch) < 0.3 * dpi or min(cw, ch) < 0.05 * dpi:
            continue                                                   # specks, rules, underlines
        if cw * ch < 0.12 * dpi * dpi and area > 0.6 * cw * ch:
            continue                                                   # small solid blobs (punch holes)
        parts.append((x, y, x + cw, y + ch))
    # merge parts that are close to each other into whole figures
    gap = 0.25 * dpi
    merged = True
    while merged and len(parts) > 1:
        merged = False
        out = []
        while parts:
            a = parts.pop()
            for i, b in enumerate(out):
                if a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]:
                    out[i] = box_union([a, b])
                    merged = True
                    break
            else:
                out.append(a)
        parts = out
    figures = []
    for fb in parts:
        fw, fh = fb[2] - fb[0], fb[3] - fb[1]
        if fw < 0.75 * dpi or fh < 0.4 * dpi or fw * fh < 0.01 * h * w:
            continue
        if any(box_intersection(fb, tb) > 0.3 * box_area(fb) for tb in table_boxes):
            continue                                                   # leftovers of a table's frame
        figures.append(tuple(int(v) for v in fb))
    return figures


def _frame_is_caption_cell(fbox: Box, lines_inside: list, gray: "np.ndarray", dpi: float, text: str) -> bool:
    """A box drawn around a table's caption (the caption row of the table frame), not a figure: the text is
    a TABLE caption, the box is only a few text lines tall, and apart from that text and the frame itself
    there is no drawing inside it."""
    cap = RE_CAPTION.match(text)
    if not cap or not cap.group("kind").lower().startswith("tab") or not lines_inside:
        return False
    line_h = statistics.median(ln.height for ln in lines_inside)
    x0, y0, x1, y1 = (int(v) for v in fbox)
    if y1 - y0 > 5 * line_h + 0.15 * dpi:
        return False
    margin = max(3, int(0.04 * dpi))                    # the frame lines themselves
    ink = gray[y0 + margin:y1 - margin, x0 + margin:x1 - margin] < 128
    if ink.size == 0:
        return True
    pad = max(2, int(0.02 * dpi))
    for ln in lines_inside:                             # remove the text
        a0, b0 = max(0, int(ln.box[1]) - y0 - margin - pad), max(0, int(ln.box[0]) - x0 - margin - pad)
        a1, b1 = int(ln.box[3]) - y0 - margin + pad, int(ln.box[2]) - x0 - margin + pad
        ink[a0:max(a0, a1), b0:max(b0, b1)] = False
    return float(ink.mean()) < 0.002


def _figure_is_really_text(fig_box: Box, lines_inside: list) -> bool:
    """Guard against losing text: a 'figure' that is mostly text (e.g. a table whose ruling
    lines were not recognised) or that contains requirement sentences stays as text."""
    if not lines_inside:
        return False
    text_area = sum(box_area(ln.box) for ln in lines_inside)
    long_lines = sum(1 for ln in lines_inside if word_count(ln.text) >= 8)
    has_modal = any(_modal_re().search(ln.text) for ln in lines_inside)
    return text_area > 0.35 * box_area(fig_box) or long_lines >= 3 or has_modal


# ---- 6e. Reading order: recursive XY-cut ----------------------------------------------
def _merge_intervals(intervals: list, tolerance: float) -> list:
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1] + tolerance:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _column_cut(items: list, region_w: float, min_vgap: float):
    """The widest vertical whitespace band with real text on both sides -> (gap, left, right) or None."""
    x_spans = _merge_intervals([(it[0][0], it[0][2]) for it in items], 0)
    best = None
    for (a0, a1), (b0, b1) in zip(x_spans, x_spans[1:]):
        gap = b0 - a1
        if gap < min_vgap:
            continue
        left = [it for it in items if it[0][2] <= a1]
        right = [it for it in items if it[0][0] >= b0]
        lw = max(it[0][2] for it in left) - min(it[0][0] for it in left)
        rw = max(it[0][2] for it in right) - min(it[0][0] for it in right)
        if lw >= 0.2 * region_w and rw >= 0.2 * region_w and len(left) >= 2 and len(right) >= 2:
            if best is None or gap > best[0]:
                best = (gap, left, right)
    return best


def xy_cut(items: list, min_hgap: float, min_vgap: float, depth: int = 0) -> list:
    """items = [(box, payload)]. Returns leaves (lists of items) in reading order.
    Columns are split first (a vertical whitespace band crossing the whole region, with
    real text on both sides); otherwise the region is split at horizontal gaps."""
    if len(items) <= 1 or depth > 60:
        return [sorted(items, key=lambda it: (it[0][1], it[0][0]))] if items else []
    x_min, x_max = min(it[0][0] for it in items), max(it[0][2] for it in items)
    region_w = max(x_max - x_min, 1)
    # --- vertical cut (columns)
    best = _column_cut(items, region_w, min_vgap)
    if best:
        return xy_cut(best[1], min_hgap, min_vgap, depth + 1) + xy_cut(best[2], min_hgap, min_vgap, depth + 1)
    # --- a line across the whole width (running header/footer, page-wide heading or table) hides the
    #     column gutter: cut the region above and below such lines first, then look for columns again.
    #     (Cutting at every horizontal gap would slice two columns into rows and mix their lines.)
    wide = {id(it) for it in items if it[0][2] - it[0][0] >= 0.6 * region_w}
    narrow = [it for it in items if id(it) not in wide]
    if wide and len(narrow) >= 4 and _column_cut(narrow, region_w, min_vgap):
        bands, current = [], []
        for it in sorted(items, key=lambda it: (it[0][1], it[0][0])):
            if id(it) in wide:
                if current:
                    bands.append(current)
                bands.append([it])
                current = []
            else:
                current.append(it)
        if current:
            bands.append(current)
        if len(bands) > 1:
            return [leaf for band in bands for leaf in xy_cut(band, min_hgap, min_vgap, depth + 1)]
    # --- horizontal cuts
    y_spans = _merge_intervals([(it[0][1], it[0][3]) for it in items], min_hgap)
    if len(y_spans) > 1:
        leaves = []
        for y0, y1 in y_spans:
            group = [it for it in items if y0 <= (it[0][1] + it[0][3]) / 2 <= y1]
            leaves.extend(xy_cut(group, min_hgap, min_vgap, depth + 1))
        return leaves
    return [sorted(items, key=lambda it: (it[0][1], it[0][0]))]


# ---- 6f. Grouping lines into headings / paragraphs / list items ---------------------------
_MODAL_RE = None
_MODAL_WORDS = ("shall", "must", "should", "will", "is required to", "are required to")
_SENTENCE_STARTERS = {"The", "A", "An", "This", "These", "Each", "All", "Any", "Every", "It", "When", "While", "If", "Where"}


def configure_keywords(keywords: Iterable) -> None:
    """Layout rules (headings, captions, figure labels) must never swallow a requirement: they use
    the same keywords as the extractor, plus the OCR-garbled spellings the extractor repairs."""
    global _MODAL_WORDS, _MODAL_RE
    _MODAL_WORDS = tuple(sorted({" ".join(str(k).lower().split()) for k in keywords if str(k).strip()}
                                | {"shall", "must", "should", "will"}, key=len, reverse=True))
    _MODAL_RE = None


def _modal_re():
    """Regex matching any requirement keyword (as configured) or an OCR-garbled shall/must/should/will."""
    global _MODAL_RE
    if _MODAL_RE is None:
        words = "|".join(r"\s+".join(re.escape(p) for p in w.split()) for w in _MODAL_WORDS)
        garbled = "|".join(f"(?:{pattern.pattern})" for _, pattern in OCR_KEYWORD_REPAIRS)
        _MODAL_RE = re.compile(r"(?<![A-Za-z])(?:" + words + r")(?![A-Za-z])|" + garbled, re.I)
    return _MODAL_RE
_ENDS_MID_PHRASE = re.compile(r"\b(?:of|in|the|and|or|to|for|with|a|an|by|on|at|from|as|that|which|section|per|than)\s*$", re.I)


def _ends_sentence(text: str) -> bool:
    return bool(RE_TERMINAL.search(text))


def _is_heading_text(text: str) -> bool:
    """Short title-like line: '3.2 Characteristics.', '1. SCOPE', 'REQUIREMENTS'."""
    t = text.strip()
    if not t or word_count(t) > 12 or _modal_re().search(t) or RE_LIST_MARKER.match(t):
        return False                               # "(1) SEARCH MODE." is a list item, not a heading
    m = RE_PARA_NUM.match(t)
    if m:
        rest = m.group("rest").strip()
        if RE_CAPTION.match(rest) or _starts_with_unit(rest):
            return False                           # "3.3 V shall ..." / "28 VDC" are quantities
        # a heading title has no sentence after it ("Detection range. The radar ..." is a paragraph),
        # does not stop in the middle of a phrase ("... requirement in section") and does not start
        # like a sentence ("3.2.1 The primary display units")
        first = rest.split()[0] if rest.split() else ""
        return (word_count(rest) <= 10 and not re.search(r"[.:;]+['`\u00b7]?\s*[A-Z(]", rest)
                and rest[:1].isupper() and not _ENDS_MID_PHRASE.search(rest) and first not in _SENTENCE_STARTERS)
    m = RE_NUMBERED_ITEM.match(t)
    if m and m.group("rest").isupper():
        return True
    letters = [c for c in t if c.isalpha()]
    return (len(letters) >= 4 and all(c.isupper() for c in letters) and word_count(t) <= 10
            and not RE_PAGE_NUMBER.match(t) and not _ENDS_MID_PHRASE.search(t)
            and not t.endswith(":"))                   # "NOTES:" introduces a list; it is not a section title


_QUANTITY_FOLLOWERS = {"to", "and", "or", "max", "min", "maximum", "minimum", "nominal", "dc", "ac", "rms", "peak",
                       "\u00b1", "+/-", "input", "output", "bus", "power", "supply", "nom"}


def _starts_with_unit(text: str) -> bool:
    """'V shall ...' / 'VDC input' after a number is a quantity ('3.3 V shall'), not a paragraph title.
    A single letter only counts as a unit when a keyword, number or 'to/max/...' follows ('3.1 A radar' is fine)."""
    toks = text.split()
    if not toks:
        return False
    first = toks[0].rstrip(".,;:")
    if not RE_UNIT.fullmatch(first):
        return False
    if len(first) >= 2 and first not in ("in", "min", "hr", "ft", "lb", "oz"):
        return True
    second = toks[1].lower().strip(".,;:") if len(toks) > 1 else ""
    return second in _QUANTITY_FOLLOWERS or bool(_modal_re().fullmatch(second)) or second[:1].isdigit()


def _id_prefix(rid: str) -> str:
    m = re.match(r"[A-Za-z][A-Za-z0-9]*?(?=[-_.]|\d|$)", rid or "")
    return m.group(0).upper() if m else ""


def _starts_with_delimited_id(text: str) -> bool:
    """'[SRS-101] ...', '(SRS-101) ...' or 'SRS-103: ...' - an ID that is clearly marked as one."""
    return bool(re.match(r"^\s*[\[(](?:" + RE_REQ_ID + r")[\])]|^\s*(?:" + RE_REQ_ID + r")\s*:", text))


def _starts_new_item(text: str) -> bool:
    t = text.strip()
    if RE_LIST_MARKER.match(t) or RE_CAPTION.match(t):
        return True
    m = RE_PARA_NUM.match(t)
    if m and "." in m.group("num") and m.group("rest")[:1].isupper() and not _starts_with_unit(m.group("rest")):
        return True
    m = RE_NUMBERED_ITEM.match(t)
    if m and m.group("rest")[:1].isupper():
        return True
    return _starts_with_delimited_id(t)


def _rows_of(lines: list) -> list:
    """Group line fragments that sit on the same visual row (left to right)."""
    rows = []
    for ln in sorted(lines, key=lambda l: (l.box[1], l.box[0])):
        if rows:
            last = rows[-1]
            ry0, ry1 = min(l.box[1] for l in last), max(l.box[3] for l in last)
            overlap = min(ry1, ln.box[3]) - max(ry0, ln.box[1])
            if overlap >= 0.5 * min(ln.height, ry1 - ry0):
                last.append(ln)
                continue
        rows.append([ln])
    return [sorted(r, key=lambda l: l.box[0]) for r in rows]


def caption_meta(text: str, default_kind: str) -> dict:
    """Caption kind and label ('TABLE 3-1') for a text already known to be a caption."""
    cap = RE_CAPTION.match(text.strip())
    if not cap:
        return {"caption_kind": default_kind, "caption_label": "", "continued": False}
    kind = "table" if cap.group("kind").lower().startswith("tab") else "figure"
    return {"caption_kind": kind, "caption_label": f"{cap.group('kind').upper().rstrip('.')} {cap.group('num')}",
            "continued": bool(RE_CONTINUED.search(cap.group("title") or ""))}


def classify_text_block(text: str, n_rows: int) -> tuple:
    """-> (kind, meta) for a block of text lines."""
    t = text.strip()
    meta = {}
    cap = RE_CAPTION.match(t)
    if cap and word_count(t) <= 40 and not _modal_re().search(t):
        kind = "table" if cap.group("kind").lower().startswith("tab") else "figure"
        title = (cap.group("title") or "").strip()
        # "Table 3 lists the ..." is a sentence, not a caption: require a delimiter or a title-like start
        if cap.group("delim") or not title or title[:1].isupper() or RE_CONTINUED.search(title):
            meta.update({"caption_kind": kind, "caption_label": f"{cap.group('kind').upper().rstrip('.')} {cap.group('num')}",
                         "continued": bool(RE_CONTINUED.search(title))})
            return "caption", meta
    if n_rows <= 2 and _is_heading_text(t):
        m = RE_PARA_NUM.match(t)
        if m:
            meta["number"] = clean_para_number(m.group("num"))
            meta["title"] = m.group("rest").strip().rstrip(".")
            meta["level"] = m.group("num").count(".") + 1
        else:
            meta["level"] = 1
            meta["title"] = t.rstrip(".")
        return "heading", meta
    m = RE_LIST_MARKER.match(t) or RE_NUMBERED_ITEM.match(t)
    if m:
        meta["marker"] = m.group("marker")
        return "list_item", meta
    return "paragraph", meta


@dataclass
class _PageStats:
    line_h: float
    line_gap: float
    para_gap: float


def _page_stats(rows: list) -> _PageStats:
    heights = [max(l.box[3] for l in r) - min(l.box[1] for l in r) for r in rows] or [30.0]
    line_h = float(statistics.median(heights))
    gaps = []
    for a, b in zip(rows, rows[1:]):
        ab, bb = box_union(l.box for l in a), box_union(l.box for l in b)
        overlap_x = min(ab[2], bb[2]) - max(ab[0], bb[0])
        gap = bb[1] - ab[3]
        if overlap_x > 0 and 0 <= gap < 2 * line_h:
            gaps.append(gap)
    line_gap = float(np.percentile(gaps, 30)) if gaps else 0.35 * line_h
    para_gap = float(np.clip(line_gap + 0.5 * line_h, 0.6 * line_h, 1.5 * line_h))
    return _PageStats(line_h, line_gap, para_gap)


def analyze_page(page_no: int, prep: PreparedPage, lines: list, settings: Settings) -> list:
    """Turn the OCR lines of one page into ordered Blocks."""
    dpi = prep.dpi
    blocks = []
    page_h, page_w = prep.ocr_image.shape[:2]
    # tiny OCR 'lines' in the outer side margins (specks, binder holes, revision bars) are noise
    lines = [ln for ln in lines if not (len(ln.text.strip()) <= 2 and not ln.text.strip().isdigit()
                                        and (ln.box[2] < 0.09 * page_w or ln.box[0] > 0.91 * page_w))]
    free = list(lines)

    # tables first: their words are removed from the running text
    table_captions = []       # (table box, caption lines taken out of that table's grid)
    if settings.detect_tables and lines:
        used = set()
        for table, tbox, inside, caption_lines in detect_tables(prep.ocr_image, lines, dpi, settings):
            blocks.append(Block("table", page_no, tbox, lines=[lines[i] for i in sorted(inside)], table=table))
            used |= inside
            if caption_lines:
                table_captions.append((tbox, {id(lines[i]) for i in caption_lines}))
        free = [ln for i, ln in enumerate(lines) if i not in used]

    # figures: graphics that are not text; labels inside a figure belong to the figure
    for fbox in detect_figures(prep, free, [b.box for b in blocks if b.kind == "table"]):
        inside = [ln for ln in free if box_center_inside(ln.box, fbox)]
        if _figure_is_really_text(fbox, inside):
            continue
        framed_caption = " ".join(ln.text for ln in sorted(inside, key=lambda l: (l.box[1], l.box[0]))).strip()
        table_below_or_above = next((tb for tb in blocks if tb.kind == "table"
                                     and abs(fbox[0] - tb.box[0]) < 0.1 * dpi and abs(fbox[2] - tb.box[2]) < 0.1 * dpi
                                     and (abs(tb.box[1] - fbox[3]) < 0.15 * dpi or abs(fbox[1] - tb.box[3]) < 0.15 * dpi)), None)
        if (inside and table_below_or_above is not None
                and _frame_is_caption_cell(fbox, inside, prep.ocr_image, dpi, framed_caption)):
            # the frame around a caption printed as the table's first (or last) row: keep it as text
            table_captions.append((table_below_or_above.box, {id(ln) for ln in inside}))
            continue
        blocks.append(Block("figure", page_no, fbox, lines=inside))
        inside_ids = {id(ln) for ln in inside}
        free = [ln for ln in free if id(ln) not in inside_ids]

    # reading order for text lines + tables + figures together
    items = [(ln.box, ln) for ln in free] + [(b.box, b) for b in blocks]
    line_h = statistics.median([ln.height for ln in free]) if free else 0.12 * dpi
    leaves = xy_cut(items, min_hgap=0.45 * line_h, min_vgap=max(1.2 * line_h, 0.12 * dpi))

    ordered_rows = []   # (leaf_index, row) where row is list[Line]  OR  (leaf_index, Block)
    for li, leaf in enumerate(leaves):
        leaf_lines = [p for _, p in leaf if isinstance(p, Line)]
        leaf_blocks = [p for _, p in leaf if isinstance(p, Block)]
        entries = [(r[0].box[1], "row", r) for r in _rows_of(leaf_lines)] + [(b.box[1], "block", b) for b in leaf_blocks]
        for _, what, obj in sorted(entries, key=lambda e: e[0]):
            ordered_rows.append((li, what, obj))

    stats = _page_stats([obj for _, what, obj in ordered_rows if what == "row"])
    row_boxes = [box_union(ln.box for ln in obj) for _, what, obj in ordered_rows if what == "row"]
    text_x0 = min((b[0] for b in row_boxes), default=0)
    text_w = max(1.0, max((b[2] for b in row_boxes), default=page_w) - text_x0)
    narrow_rows = [(b, None) for b in row_boxes if b[2] - b[0] < 0.6 * text_w]
    has_columns = len(narrow_rows) >= 4 and bool(_column_cut(narrow_rows, text_w, max(1.2 * stats.line_h, 0.12 * dpi)))

    def column_right_edge(x0: float, x1: float, in_columns: bool) -> float:
        """Right edge of the text column holding x0..x1: taken from the rows of this page that overlap it
        horizontally, so each column of a two-column page has its own edge. A line that stops well short
        of it, although the next line's first word would have fitted, was ended on purpose (a heading, a
        list item, the end of a paragraph) - it is not a wrapped sentence."""
        overlapping = [b for b in row_boxes if min(b[2], x1) - max(b[0], x0) > 0.5 * max(1.0, min(b[2] - b[0], x1 - x0))]
        if in_columns:                   # a line across both columns (page footer, page-wide title) is not this column
            overlapping = [b for b in overlapping if b[2] - b[0] < 0.6 * text_w] or overlapping
        same = [b[2] for b in overlapping]
        return float(np.percentile(same, 90)) if len(same) >= 3 else float(max(same, default=x1))

    out = []
    current = []          # rows of the block being built
    current_leaf = None
    current_right = None  # right edge of the column of the block being built

    def flush():
        nonlocal current, current_right
        current_right = None
        if not current:
            return
        all_lines = [ln for row in current for ln in row]
        text = " ".join(" ".join(ln.text for ln in row) for row in current)
        kind, meta = classify_text_block(text, len(current))
        out.append(Block(kind, page_no, box_union(ln.box for ln in all_lines), lines=all_lines, text=text, meta=meta))
        current = []

    for leaf_idx, what, obj in ordered_rows:
        if what == "block":
            flush()
            out.append(obj)
            current_leaf = None
            continue
        row = obj
        row_box = box_union(ln.box for ln in row)
        row_text = " ".join(ln.text for ln in row)
        if current:
            prev = current[-1]
            prev_box = box_union(ln.box for ln in prev)
            prev_text = " ".join(ln.text for ln in prev)
            block_box = box_union(ln.box for r in current for ln in r)
            first_box = box_union(ln.box for ln in current[0])
            first_text = " ".join(ln.text for ln in current[0])
            gap = row_box[1] - prev_box[3]
            sentence_ended = _ends_sentence(prev_text)
            if current_right is None:
                # on a page with columns, a block whose lines are all narrow sits in one of the columns
                in_columns = has_columns and max(block_box[2] - block_box[0], row_box[2] - row_box[0]) < 0.6 * text_w
                current_right = column_right_edge(first_box[0], max(first_box[2], prev_box[2]), in_columns)
            first_word = row[0].words[0].box if row[0].words else None
            word_w = (first_word[2] - first_word[0]) if first_word else 0.5 * stats.line_h * len(row_text.split()[0])
            next_word_fits = current_right - prev_box[2] > word_w + 1.0 * stats.line_h
            # The previous line ran to the margin in mid-sentence, so the text simply wrapped. That holds for
            # any line spacing: a double-spaced paragraph on a page with single-spaced notes is not split.
            wrapped = not sentence_ended and not next_word_fits
            # ... but a larger gap before the bottom / after the top 8.5% of the page is the page footer / header
            furniture_edge = (row_box[1] > 0.915 * page_h >= prev_box[1]) or (prev_box[3] < 0.085 * page_h <= row_box[3])
            wrapped = wrapped and not (furniture_edge and gap > stats.para_gap)
            # A larger gap after a wrapped line is ordinary spacing only when the next line continues the
            # sentence: it starts in lower case / with a number, or the block already has this spacing. A last
            # line that lost its final period (faint print) must not swallow "3.2.5 Weight. ..." or "The ...".
            if len(current) >= 2:
                before_box = box_union(ln.box for ln in current[-2])
                same_spacing = gap <= 1.3 * (prev_box[1] - before_box[3]) + 0.1 * stats.line_h
            else:
                same_spacing = False
            continues = (wrapped and gap < 3 * stats.line_h and not _starts_new_item(row_text) and not RE_LIST_MARKER.match(row_text)
                         and (row_text[:1].islower() or row_text[:1].isdigit() or same_spacing))
            wider_gap = gap > stats.line_gap + 0.25 * stats.line_h and not wrapped
            # A new bullet / list marker at the same indent as the block's first line is a sibling item, even
            # when the previous item has no final punctuation. So is "[SRS-101] ..." or "SRS-103: ...".
            # "(CB12)" at the start of a line needs evidence that the line before really ended: it is often
            # a designator in the middle of a wrapped sentence.
            strong_id = bool(re.match(r"^\s*(?:\[(?:" + RE_REQ_ID + r")\]|(?:" + RE_REQ_ID + r")\s*:)\s*[A-Z\"(\[]", row_text))
            row_is_item = bool(RE_LIST_MARKER.match(row_text) or strong_id
                               or (_starts_with_delimited_id(row_text) and (sentence_ended or next_word_fits or wider_gap)))
            sibling_item = row_is_item and row_box[0] <= first_box[0] + 0.6 * stats.line_h
            outdented = (bool(RE_LIST_MARKER.match(first_text) or RE_NUMBERED_ITEM.match(first_text))
                         and row_box[0] < first_box[0] - 0.6 * stats.line_h)
            x_overlap = min(row_box[2], block_box[2]) - max(row_box[0], block_box[0])
            narrow = max(1, min(row_box[2] - row_box[0], block_box[2] - block_box[0]))
            prev_h, row_h = prev_box[3] - prev_box[1], row_box[3] - row_box[1]
            new_block = (
                gap < -0.3 * stats.line_h                                        # jumped back up (new column)
                or (leaf_idx != current_leaf and x_overlap < 0.3 * narrow)          # different column
                or (gap > stats.para_gap and not continues)                        # paragraph spacing
                or sibling_item or outdented                                       # next list item / end of list
                or (_is_heading_text(prev_text) and len(current) == 1 and not row_text[:1].islower()
                    and (prev_text.rstrip().endswith((".", ":")) or prev_text.isupper() or _starts_new_item(row_text)
                         or _is_heading_text(row_text) or wider_gap or next_word_fits))
                or (prev_text.rstrip().endswith(":") and row_box[0] > first_box[0] + 0.6 * stats.line_h)  # list starts
                or ((_starts_new_item(row_text) or _is_heading_text(row_text)) and (sentence_ended or wider_gap))
                or (sentence_ended and prev_box[2] < block_box[2] - 0.25 * (block_box[2] - block_box[0])
                    and len(current) > 1)                                           # short last line of a paragraph
                or (max(prev_h, row_h) > 1.45 * max(1, min(prev_h, row_h)))         # font size change
            )
            if new_block:
                flush()
        current.append(row)
        current_leaf = leaf_idx
    flush()

    # "1. SEARCH MODE." / "1. Note text ..." look like headings on their own. They are list items when
    # they follow a line ending in ":" ("NOTES:", "... the following modes:"), when they sit level with a
    # list item, or when several of them follow each other with consecutive numbers (1., 2., 3.).
    def numbered_heading(blk):
        return RE_NUMBERED_ITEM.match(blk.text or "") if blk.kind == "heading" else None

    k = 0
    while k < len(out):
        if not numbered_heading(out[k]):
            k += 1
            continue
        run = [k]
        while (run[-1] + 1 < len(out) and numbered_heading(out[run[-1] + 1]) and out[run[-1] + 1].page == out[k].page
               and abs(out[run[-1] + 1].box[0] - out[run[-1]].box[0]) <= 0.6 * stats.line_h):
            run.append(run[-1] + 1)
        numbers = [int(numbered_heading(out[x]).group("marker").rstrip(".")) for x in run]
        before = out[k - 1] if k > 0 else None
        after_stem = (before is not None and before.page == out[k].page and before.text.rstrip().endswith(":")
                      and (before.kind == "heading" or word_count(before.text) <= 3             # "NOTES:"
                           or out[k].box[0] > before.box[0] + 0.3 * stats.line_h))              # indented under a stem
        # "1. Note text ...", "2. Note text ..." - but not "3. REQUIREMENTS" / "4. VERIFICATION" (empty section)
        consecutive = (len(run) >= 2 and all(y == x + 1 for x, y in zip(numbers, numbers[1:]))
                       and not all(RE_NUMBERED_ITEM.match(out[x].text).group("rest").isupper() for x in run))
        if after_stem or consecutive:
            for x in run:
                out[x].kind, out[x].meta = "list_item", {"marker": numbered_heading(out[x]).group("marker")}
        k = run[-1] + 1

    # a caption that was printed inside a table's frame belongs to that table
    for tbox, caption_line_ids in table_captions:
        for b in out:
            if b.kind == "caption" and any(id(ln) in caption_line_ids for ln in b.lines):
                b.meta["caption_for_box"] = [int(v) for v in tbox]
    return out


# =============================================================================
# 7. DOCUMENT-LEVEL CLEAN-UP
#    Runs after every page is read: page headers/footers, words hyphenated across
#    lines, paragraphs and tables that continue on the next page, caption links.
# =============================================================================
def _similar(a: str, b: str, at_least: float = 0.0) -> float:
    """Similarity 0..1 of two strings. With `at_least`, clearly different strings return 0 early
    (the cheap upper bounds are checked first - the full comparison is slow on long text)."""
    import difflib
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if at_least and (m.real_quick_ratio() < at_least or m.quick_ratio() < at_least):
        return 0.0
    return m.ratio()


# Engineering words missing from the general English dictionary (so they are not flagged as misreads).
# Program-specific terms can be added to Settings.extra_dictionary_words.
ENGINEERING_WORDS = set("""
antitamper backplane backplanes baseband beamformer beamforming beamwidth bitrate bitrates bootloader bootloaders
bootup boresight boresighting checksum checksums circulators config configs connectorization connectorized crypto
cryptos cybersecurity databus datagram datagrams datalink datalinks deconfliction deserializer diplexer downlink
downlinks duplexer duplexers dwg dwgs failover failsafe geofence geofencing geolocation georeference georeferenced
geospatial gimbaled hardcopy hypervisor interoperate interoperates interoperating keyloader lidar lifecycle loopback
mainlobe metadata microamp microamps microservice microservices middleware milliamp milliamps milliwatt milliwatts
monopulse multimode multipath narrowband offboard onboard overcurrent overtemperature overvoltage packetized
passthrough picosecond pinout pinouts postflight powerdown powerup pulsewidth pushbuttons qty readback realtime req
reqs runtime scanline serializer sidelobe sidelobes singlemode softcopy subassemblies subcomponent subcomponents
subtier teleoperated teleoperation testset testsets timestamp timestamped timestamps undervoltage uninterruptible
uplink uplinks verif virtualization waypoint waypoints webserver wideband workaround writeback zeroization zeroize
zeroized""".split())


class WordChecker:
    """Spots OCR misreads the OCR engine itself is confident about. Tested on the degraded test
    scans: most real misreads ('telémetry', 'fro', 'governmient', '16.AWG') scored above 0.95,
    so these independent checks are what makes the 'Needs Review' flag useful:
      * accent marks in English text (removed, and flagged)
      * a word that is not in an English dictionary (pyspellchecker, MIT) and occurs only once
      * a rare word one letter away from a common word of the same document ('fro' vs 'from')
      * punctuation inside a word ('Rev'A')
    Nothing is ever auto-corrected except the accent marks."""

    def __init__(self, counts: Counter, settings: "Settings", ids: Counter = None):
        self.counts = counts
        self.ids = ids or Counter()
        self.settings = settings
        self._memo = {}
        self._id_index = defaultdict(set)         # "MIL-STD-810?" -> {"MIL-STD-810H", "MIL-STD-810B"}
        for token in self.ids:
            for i in range(len(token)):
                self._id_index[token[:i] + "\0" + token[i + 1:]].add(token)
        self.spell = None
        if settings.spell_check_flags:
            try:
                from spellchecker import SpellChecker
                self.spell = SpellChecker(language="en", distance=1)
                self.spell.word_frequency.load_words(ENGINEERING_WORDS | settings.extra_dictionary_words)
            except Exception:
                self.spell = None

    def _id_twin(self, token: str) -> str:
        """Identifiers such as MIL-STD-810H / MIL-STD-810B or SPEC-1234-A / SPEC-I234-A that differ in one
        character. A different digit in the running number at the end (SW-001 / SW-002, ICD-1204A /
        ICD-1205A) is ordinary numbering and is not reported: sequential IDs would all be flagged."""
        if self.ids.get(token, 0) >= 2:
            return ""
        last_number = re.search(r"(\d+)[A-Za-z]{0,2}$", token)      # the running number (+ revision letter)
        for i in range(len(token)):
            for other in self._id_index.get(token[:i] + "\0" + token[i + 1:], ()):
                if other == token:
                    continue
                if (last_number and last_number.start(1) <= i < last_number.end(1)
                        and token[i].isdigit() and other[i].isdigit()):
                    continue                     # SW-001 / SW-002, ICD-1204A / ICD-1205A: ordinary numbering
                return other
        return ""

    def clean(self, raw: str) -> str:
        return remove_ocr_specks(strip_accents(raw) if self.settings.english_text else raw)

    def issue(self, raw: str, clean: str) -> str:
        key = (raw, clean)
        if key not in self._memo:
            self._memo[key] = self._issue(raw, clean)
        return self._memo[key]

    def _issue(self, raw: str, clean: str) -> str:
        core = clean.strip(".,;:()[]{}\"'!?")
        if self.settings.english_text and strip_accents(raw) != raw:
            parts = [x.lower() for x in re.findall(r"[A-Za-z]{2,}", core)]
            if not parts or any(self.spell is not None and x not in self.spell and self.counts.get(x, 0) < 2 for x in parts):
                return f"accent marks removed from '{raw}'"
        if re.fullmatch(r"\d[\d.,]*['\u2019`]", core + ("'" if clean.endswith("'") else "")) or re.search(r"\d['\u2019`]$", clean):
            return "stray mark after a number (or a feet symbol)"
        for part in core.split():
            part = part.strip(".,;:()[]{}\"'!?")
            if re.search(r"\d", part) and re.search(r"[A-Za-z]", part) and len(part) >= 5:
                twin = self._id_twin(part)
                if twin:
                    return f"differs by one character from '{twin}' elsewhere in the document"
        if (re.search(r"(?<=[A-Za-z])[;'\"`](?=[A-Za-z0-9])|(?<=[a-z])[.:](?=[a-z])|(?<=\d)[;'\"`](?=[A-Za-z])", core)
                and not re.fullmatch(r"(?:[A-Za-z]\.){2,}[A-Za-z]?|[A-Za-z]+'(?:s|t|ll|re|ve|d|m)|[\w.-]+\.(?:" + "|".join(_FILE_EXTENSIONS) + r")", core)):
            return "punctuation inside a word"
        if re.search(r"[a-z]{3,}[A-Z]{3,}|[A-Za-z]{3,}[01][A-Za-z]{2,}", core) and not re.fullmatch(r"(?:[A-Z]{2,}\d+[A-Z]*|\w+\.\w+)", core):
            return "letters and digits mixed inside a word (overlapping stamp or misread)"
        if self.spell is None:
            return ""
        for part in re.split(r"[-/]", core):
            if not re.fullmatch(r"[A-Za-z][a-z]{2,}", part):
                continue                       # acronyms, IDs, numbers and short words are not checked
            w = part.lower()
            if self.counts.get(w, 0) >= 2:
                continue                       # repeated in the document: a real term (or a consistent one)
            if w not in self.spell:
                return "not in the English dictionary"
            freq = self.spell.word_usage_frequency(w)
            if freq < 1e-6:
                for cand in self.spell.edit_distance_1(w):
                    if self.counts.get(cand, 0) >= 3 and self.spell.word_usage_frequency(cand) > max(1e-4, 1000 * freq):
                        return f"possible misread of '{cand}'"
        return ""


@dataclass
class TextContext:
    vocab: set
    counts: Counter
    checker: WordChecker


def build_text_context(blocks: list, settings: "Settings") -> TextContext:
    counts, ids = Counter(), Counter()
    for b in blocks:
        for ln in b.lines:
            for w in ln.words:
                plain = remove_ocr_specks(strip_accents(w.text))
                for tok in re.findall(r"[A-Za-z]+(?![A-Za-z-])", plain):
                    counts[tok.lower()] += 1
                for part in plain.split():
                    core = part.strip(".,;:()[]{}\"'!?")
                    if len(core) >= 5 and re.search(r"\d", core) and re.search(r"[A-Za-z]", core):
                        ids[core] += 1
    return TextContext(set(counts), counts, WordChecker(counts, settings, ids))


def document_text_context(doc: "DocResult", settings: "Settings") -> TextContext:
    """The word statistics of a document are computed once and re-used by extraction and exports."""
    ctx = getattr(doc, "_text_ctx", None)
    if ctx is None:
        ctx = build_text_context(doc.blocks, settings)
        doc._text_ctx = ctx
    return ctx


def token_attention(token: tuple, settings: "Settings") -> str:
    """'' (fine), 'check' or 'likely_wrong' for one (text, confidence, issue) token.
    Same rules for the Excel 'Needs Review' flag and the Word highlighting: numbers with low
    OCR confidence, words that failed a WordChecker check, and any word read very poorly."""
    text, conf = token[0], token[1]
    issue = token[2] if len(token) > 2 else ""
    has_digit = bool(re.search(r"\d", text))
    if (has_digit and conf < settings.very_low_confidence) or (conf < 0.35 and re.search(r"[A-Za-z]{2}", text)):
        return "likely_wrong"
    if issue or (has_digit and conf < settings.review_confidence):
        return "check"
    return ""


def word_tokens(words: Iterable, ctx: TextContext) -> list:
    """[(clean text, confidence, issue)] for a sequence of OCR words."""
    out = []
    for w in words:
        clean = ctx.checker.clean(w.text)
        if not clean:
            continue
        if out and re.fullmatch(r"[.,;:]", clean):
            prev = out[-1]
            out[-1] = (prev[0] + clean, min(prev[1], w.conf), prev[2])   # "mode ." -> "mode."
            continue
        issue = ctx.checker.issue(w.text, clean)
        out.extend((part, w.conf, issue) for part in clean.split(" "))
    return out


def block_token_rows(block: Block, ctx: TextContext) -> list:
    """Tokens [(text, confidence, issue)] of a text block, one list per visual row (same order as
    _block_rows). A word split by a line-end hyphen is re-joined when the joined word appears
    elsewhere in the document ("require-" + "ment" -> "requirement"), otherwise the hyphen is kept
    ("track-while-" + "scan"). Paper specks read as punctuation are removed; suspicious words get an
    'issue' text."""
    raw_rows = []                                       # [[(raw text, conf)]] per row
    last = None                                         # (row index, token index) of the last token
    for row in _block_rows(block):
        current = []
        raw_rows.append(current)
        for k, w in enumerate(w for ln in row for w in ln.words):
            if k == 0 and last is not None:
                prev_text, prev_conf = raw_rows[last[0]][last[1]]
                if prev_text.endswith("-") and w.text[:1].islower():
                    head = re.search(r"([A-Za-z]+)-$", prev_text)
                    tail = re.match(r"[A-Za-z]+", w.text)
                    joined = prev_text[:-1] + w.text if head and tail and (head.group(1) + tail.group(0)).lower() in ctx.vocab \
                        else prev_text + w.text
                    raw_rows[last[0]][last[1]] = (joined, min(prev_conf, w.conf))
                    continue
            current.append((w.text, w.conf))
            last = (len(raw_rows) - 1, len(current) - 1)
    return [word_tokens((Word(t, c, (0, 0, 0, 0)) for t, c in r), ctx) for r in raw_rows]


def block_tokens(block: Block, ctx: TextContext) -> list:
    """All tokens of a text block in reading order (see block_token_rows)."""
    return [tok for row in block_token_rows(block, ctx) for tok in row]


def _block_rows(block: Block) -> list:
    """Rows of a block in reading order. A paragraph joined across a page break keeps its pages
    in order (sorting all lines by height alone would put page 2 before page 1)."""
    bounds = list(block.meta.get("segments") or [0]) + [len(block.lines)]
    rows = []
    for a, z in zip(bounds, bounds[1:]):
        rows.extend(_rows_of(block.lines[a:z]))
    return rows


def tokens_text(tokens: list) -> tuple:
    """-> (text, [(start, end) char span of each token])"""
    spans, parts, pos = [], [], 0
    for t, *_ in tokens:
        spans.append((pos, pos + len(t)))
        parts.append(t)
        pos += len(t) + 1
    return " ".join(parts), spans


def finalize_document(doc: DocResult, settings: Settings) -> None:
    for i, b in enumerate(doc.blocks, 1):
        b.uid = i
        b.pages = b.pages or [b.page]
    ctx = build_text_context(doc.blocks, settings)
    doc._text_ctx = ctx                         # re-used by extraction and the exports
    for b in doc.blocks:
        if b.kind not in ("table", "figure") and b.lines:
            b.text = tokens_text(block_tokens(b, ctx))[0]
        if b.kind == "table" and b.table is not None:
            b.table.grid = [[ctx.checker.clean(c) if c else c for c in row] for row in b.table.grid]
    _mark_page_furniture(doc)
    _merge_across_pages(doc)
    if settings.merge_continued_tables:
        _merge_continued_tables(doc)
    for i, b in enumerate(doc.blocks, 1):      # renumber BEFORE linking captions (merges removed blocks)
        b.uid = i
    _link_captions(doc)
    # page statistics for the "Page Quality" sheet
    for p in doc.pages:
        page_lines = [ln for b in doc.blocks if b.page == p.number for ln in b.lines]
        p.n_lines = len(page_lines)
        p.mean_conf = round(float(statistics.fmean(ln.conf for ln in page_lines)), 4) if page_lines else 1.0
        p.low_conf_lines = sum(1 for ln in page_lines if ln.min_word_conf < settings.review_confidence)


def _mark_page_furniture(doc: DocResult) -> None:
    """Running headers/footers repeat on many pages near the top/bottom edge; page numbers too."""
    heights = {p.number: p.height for p in doc.pages}
    n_pages = len(doc.pages)
    candidates = []
    for b in doc.blocks:
        h = heights.get(b.page)
        if not h or b.kind in ("table", "figure") or not b.text:
            continue
        if b.box[3] < 0.085 * h:
            candidates.append((b, "page_header"))
        elif b.box[1] > 0.915 * h:
            candidates.append((b, "page_footer"))

    def norm(t):
        return re.sub(r"\d+", "#", re.sub(r"\s+", "", t.lower()))

    def notice_key(t):
        """Keyword text compared word for word, without a page number printed on the same line."""
        t = re.sub(r"^\s*(?:page\s*)?\d{1,4}(?:\s*of\s*\d{1,4})?\s+|\s+(?:page\s*)?\d{1,4}(?:\s*of\s*\d{1,4})?\s*$", " ", t, flags=re.I)
        return " ".join(t.lower().split())

    pages_by_key = defaultdict(set)             # (kind, normalized text) -> pages it appears on
    pages_by_notice = defaultdict(set)          # (kind, keyword text without page number) -> pages
    for b, kind in candidates:
        pages_by_key[(kind, norm(b.text))].add(b.page)
        pages_by_notice[(kind, notice_key(b.text))].add(b.page)
    notice_keys = list(pages_by_notice)
    keys = list(pages_by_key)
    threshold = max(1, 0.3 * (n_pages - 1))
    for b, kind in candidates:
        if RE_LIST_MARKER.match(b.text):
            continue                             # a list item is never page furniture
        if _modal_re().search(b.text):
            # Text with a requirement keyword is furniture only when the same words repeat on other pages
            # (a handling notice in every footer; OCR may garble a letter or two of a long notice). The
            # extractor still reports it once.
            key = notice_key(b.text)
            other = set(pages_by_notice[(kind, key)]) - {b.page}
            if len(other) < threshold and word_count(key) >= 6 and len(notice_keys) <= 400:
                for k2 in notice_keys:
                    if (k2[0] == kind and k2[1] != key and re.findall(r"\d+", k2[1]) == re.findall(r"\d+", key)
                            and _similar(k2[1], key, at_least=0.9) >= 0.9):
                        other |= pages_by_notice[k2] - {b.page}
            if n_pages >= 2 and len(other) >= threshold:
                b.kind = kind
                b.meta["repeated_keyword_text"] = True
                b.meta["notice_key"] = key
            continue
        key = norm(b.text)
        other_pages = set(pages_by_key[(kind, key)]) - {b.page}
        if len(other_pages) < threshold and len(key) <= 150 and len(keys) <= 400:
            # OCR noise: allow near-identical text (running headers/footers are short lines)
            for k2 in keys:
                if k2[0] == kind and k2[1] != key and _similar(k2[1], key, at_least=0.8) >= 0.8:
                    other_pages |= pages_by_key[k2] - {b.page}
        if (n_pages >= 2 and len(other_pages) >= threshold) or RE_PAGE_NUMBER.match(b.text):
            b.kind = kind


_ENDS_MID_SENTENCE = re.compile(r"(?:-|,|\b(?:and|or|the|of|to|a|an|in|for|with|by|shall|must|will|should|be|not|than|"
                                r"from|at|on|as|per|that|which))$", re.I)


def _merge_across_pages(doc: DocResult) -> None:
    """Join a paragraph that is cut by a page break ('...shall not' | next page 'exceed 30 minutes')."""
    body = [b for b in doc.blocks if b.kind not in ("page_header", "page_footer")]
    removed = set()
    for a, nxt in zip(body, body[1:]):
        if id(a) in removed or nxt.page != max(a.pages) + 1:
            continue
        if a.kind not in ("paragraph", "list_item") or nxt.kind != "paragraph" or not a.text or not nxt.text:
            continue
        para = RE_PARA_NUM.match(nxt.text)
        if (_ends_sentence(a.text) or _starts_with_delimited_id(nxt.text)
                or (para and ("." in para.group("num") or para.group("dot")) and para.group("rest")[:1].isupper()
                    and not _starts_with_unit(para.group("rest")))):
            continue                                     # the next page starts a new paragraph / requirement
        if not (nxt.text[:1].islower() or nxt.text[:1].isdigit() or _ENDS_MID_SENTENCE.search(a.text)):
            continue
        a.meta["segments"] = list(a.meta.get("segments") or [0]) + [len(a.lines)]
        a.lines = a.lines + nxt.lines
        a.pages = sorted(set(a.pages) | set(nxt.pages))
        a.meta["continued_across_pages"] = True
        joiner = "" if a.text.endswith("-") and nxt.text[:1].islower() else " "
        a.text = a.text + joiner + nxt.text
        removed.add(id(nxt))
    doc.blocks = [b for b in doc.blocks if id(b) not in removed]


def _merge_continued_tables(doc: DocResult) -> None:
    """A table that runs onto the next page usually repeats its header row (MIL-STD-961
    also repeats the title with '- Continued'). Merge those pieces into one table."""
    body = [b for b in doc.blocks if b.kind not in ("page_header", "page_footer")]
    removed = set()
    i = 0
    while i < len(body) - 1:
        a = body[i]
        if a.kind != "table" or id(a) in removed:
            i += 1
            continue
        j = i + 1
        continued_caption = None
        if j < len(body) and body[j].kind == "caption" and body[j].page == max(a.pages) + 1:
            cap = body[j]
            if cap.meta.get("continued") or (a.meta.get("caption_label") and cap.meta.get("caption_label") == a.meta.get("caption_label")):
                continued_caption = cap
                j += 1
        if j >= len(body):
            break
        b = body[j]
        if b.kind == "table" and b.page == max(a.pages) + 1 and b.table.n_cols == a.table.n_cols:
            same_header = (a.table.header_rows and b.table.header_rows and
                           _similar(" ".join(a.table.grid[0]).lower(), " ".join(b.table.grid[0]).lower(), at_least=0.85) >= 0.85)
            if same_header or continued_caption is not None:
                skip = b.table.header_rows if same_header else 0
                if a.table.cell_words and b.table.cell_words:
                    a.table.cell_words += b.table.cell_words[skip:]
                else:
                    a.table.cell_words = []
                a.table.grid += b.table.grid[skip:]
                a.table.conf += b.table.conf[skip:]
                offset = len(a.table.grid) - len(b.table.grid[skip:])
                a.table.merges += [(r0 - skip + offset, c0, r1 - skip + offset, c1) for r0, c0, r1, c1 in b.table.merges if r0 >= skip]
                a.table.cell_boxes = []
                a.table.continued_pages.append(b.page)
                a.lines = a.lines + b.lines
                a.pages = sorted(set(a.pages) | {b.page})
                removed.add(id(b))
                hidden = set()
                if continued_caption is not None:
                    continued_caption.meta["duplicate_of_table"] = True
                    hidden.add(id(continued_caption))   # keep it in the document, but out of the way here
                # stay on this table: it might continue on a third page
                body = [x for x in body if id(x) not in removed and id(x) not in hidden]
                continue
        i += 1
    doc.blocks = [b for b in doc.blocks if id(b) not in removed]


def _min_cost_assignment(cost: list) -> list:
    """Hungarian algorithm: for a cost matrix with rows <= columns, the column chosen for each row so
    that the total cost is as small as possible (each column used at most once)."""
    n, m = len(cost), len(cost[0]) if cost else 0
    inf = float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [inf] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    result = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            result[p[j] - 1] = j - 1
    return result


def _link_captions(doc: DocResult) -> None:
    """Attach each caption to its table or figure.
    1. Known links first: a caption row taken out of a table's frame, or Docling's caption order.
    2. The side is learned: MIL-STD-961 puts table titles above tables and figure titles below figures,
       but a document is consistent with itself, so captions that have only one possible object
       decide the side used for captions sitting between two objects (the norm when unclear).
    3. On each page all remaining captions are matched to objects at once (smallest total distance),
       so one caption cannot take the table that clearly belongs to the next caption."""
    dpi_of = {p.number: p.dpi for p in doc.pages}
    taken = set()

    def link(c, target):
        c.meta["caption_of"] = target.uid
        target.meta["caption"] = c.text
        target.meta["caption_label"] = c.meta.get("caption_label", "")
        taken.add(target.uid)

    objects = defaultdict(list)                          # (page, kind) -> tables / figures on that page
    by_box = {}
    for t in doc.blocks:
        if t.kind in ("table", "figure"):
            objects[(t.page, t.kind)].append(t)
            by_box[(t.page, tuple(int(x) for x in t.box))] = t
    votes = {"table": Counter(), "figure": Counter()}
    for idx, c in enumerate(doc.blocks):
        if c.kind != "caption":
            continue
        attach = c.meta.get("attach")
        target = (doc.blocks[idx + 1] if attach == "next" and idx + 1 < len(doc.blocks) else
                  doc.blocks[idx - 1] if attach == "prev" and idx > 0 else
                  by_box.get((c.page, tuple(c.meta["caption_for_box"]))) if c.meta.get("caption_for_box") else None)
        if (target is not None and target.kind in ("table", "figure") and target.uid not in taken
                and not c.meta.get("duplicate_of_table")):    # a "(continued)" caption whose table piece was merged
            link(c, target)
            if attach in ("next", "prev") and target.kind in votes:
                votes[target.kind]["below" if attach == "next" else "above"] += 1

    def candidates(c):
        """-> {'above': (gap, block) or None, 'below': ...}: the nearest free object on each side."""
        max_gap = 1.2 * dpi_of.get(c.page, 200)          # within ~1.2 inch
        found = {"above": None, "below": None}
        for t in objects[(c.page, c.meta["caption_kind"])]:
            if t.uid in taken:
                continue
            side = "below" if t.box[1] >= c.box[1] else "above"
            gap = t.box[1] - c.box[3] if side == "below" else c.box[1] - t.box[3]
            if -0.2 * max_gap <= gap <= max_gap and (found[side] is None or gap < found[side][0]):
                found[side] = (gap, t)
        return found

    pending = [b for b in doc.blocks if b.kind == "caption" and "caption_of" not in b.meta
               and not b.meta.get("duplicate_of_table") and b.meta.get("caption_kind") in ("table", "figure")]
    for c in pending:
        found = candidates(c)
        if (found["above"] is None) != (found["below"] is None):
            votes[c.meta["caption_kind"]]["above" if found["above"] else "below"] += 1
    preferred, penalty = {}, {}
    for kind, norm in (("table", "below"), ("figure", "above")):      # side where the OBJECT sits
        total = sum(votes[kind].values())
        if total and votes[kind].most_common(1)[0][1] >= 0.75 * total:
            preferred[kind], penalty[kind] = votes[kind].most_common(1)[0][0], 2.0    # the document's own habit
        else:
            preferred[kind], penalty[kind] = norm, 1.25

    groups = defaultdict(list)
    for c in pending:
        groups[(c.page, c.meta["caption_kind"])].append(c)
    for (page, kind), caps in groups.items():
        objs = [t for t in objects[(page, kind)] if t.uid not in taken]
        if not objs:
            continue
        max_gap = 1.2 * dpi_of.get(page, 200)
        unmatched = 3.0 * max_gap                        # leaving a caption without its object is costly
        cost = []
        for c in caps:
            row = []
            for t in objs:
                side = "below" if t.box[1] >= c.box[1] else "above"
                gap = t.box[1] - c.box[3] if side == "below" else c.box[1] - t.box[3]
                if not -0.2 * max_gap <= gap <= max_gap:
                    row.append(1e9)                      # too far away: never
                else:
                    row.append(gap * (1.0 if side == preferred[kind] else penalty[kind]) if gap > 0 else gap)
            row += [unmatched] * len(caps)               # one "no object" choice per caption
            cost.append(row)
        for i, j in enumerate(_min_cost_assignment(cost)):
            if 0 <= j < len(objs) and cost[i][j] < 1e9:
                link(caps[i], objs[j])


# =============================================================================
# 8. OPTIONAL ENGINE: DOCLING  (IBM, MIT license)
#    Adds a trained layout model (Heron) and TableFormer table-structure model on
#    top of the same PP-OCRv6 OCR. Needs:  python -m pip install "docling[rapidocr]"
#    and a one-time model download from Hugging Face (or an offline copy, see README).
# =============================================================================
class EngineUnavailable(RuntimeError):
    pass


class DoclingEngine:
    def __init__(self, settings: Settings):
        models_dir = settings.docling_models_dir or os.environ.get("DOCLING_ARTIFACTS_PATH")
        if models_dir:
            # an offline model folder was given: never try to reach Hugging Face (read before docling loads)
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        try:
            from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (OcrMode, PdfPipelineOptions, RapidOcrOptions,
                                                            TableFormerMode, TableStructureOptions)
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise EngineUnavailable('Docling is not installed. Install it with:  python -m pip install "docling[rapidocr]"'
                                    "  - or run with the standard engine.") from exc
        self.settings = settings
        ocr_kwargs = {"mode": OcrMode.FULL_PAGE, "backend": "onnxruntime", "text_score": settings.min_text_confidence,
                      "rapidocr_params": {"Global.log_level": "error"}}
        try:  # reuse the PP-OCRv6 models that ship inside the rapidocr package (no extra download)
            import rapidocr
            models = Path(rapidocr.__file__).parent / "models"
            det, rec = models / "PP-OCRv6_det_small.onnx", models / "PP-OCRv6_rec_small.onnx"
            cls = models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
            if det.exists() and rec.exists():
                ocr_kwargs.update({"det_model_path": str(det), "rec_model_path": str(rec)})
                if cls.exists():
                    ocr_kwargs["cls_model_path"] = str(cls)
        except ImportError:
            pass
        device = {"cpu": AcceleratorDevice.CPU, "cuda": AcceleratorDevice.CUDA, "mps": AcceleratorDevice.MPS}.get(
            settings.docling_device.lower(), AcceleratorDevice.AUTO)
        options = PdfPipelineOptions(
            do_ocr=True, do_table_structure=True, ocr_options=RapidOcrOptions(**ocr_kwargs),
            table_structure_options=TableStructureOptions(do_cell_matching=False, mode=TableFormerMode.ACCURATE),
            accelerator_options=AcceleratorOptions(device=device))
        if models_dir:
            options.artifacts_path = str(models_dir)
        self._converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})

    def convert(self, prepared_pages: list, work_dir: Path) -> tuple:
        """prepared_pages = [(page_number, PreparedPage)]. The cleaned page images are packed
        into a temporary PDF so Docling benefits from our deskew/rotation/cleanup too.
        Returns (blocks, {page_number: ocr_score})."""
        pdf_path = work_dir / "_docling_input.pdf"
        pdf = pdfium.PdfDocument.new()            # page by page, JPEGs are embedded without decoding (low memory)
        try:
            for _number, dpi, height, width, image_file in prepared_pages:
                w_pt, h_pt = width * 72.0 / dpi, height * 72.0 / dpi
                page = pdf.new_page(w_pt, h_pt)
                image = pdfium.PdfImage.new(pdf)
                image.load_jpeg(str(image_file), inline=False)
                image.set_matrix(pdfium.PdfMatrix().scale(w_pt, h_pt))
                page.insert_obj(image)
                page.gen_content()
                page.close()
            pdf.save(str(pdf_path))
        finally:
            pdf.close()
        try:
            result = self._converter.convert(str(pdf_path), raises_on_error=True)
        except Exception as exc:
            msg = str(exc)
            if any(k in msg.lower() for k in ("huggingface", "hf.co", "connection", "403", "offline", "artifacts")):
                raise EngineUnavailable(
                    "Docling could not load its layout/table models (" + msg[:200] + "). Download them once on a "
                    "machine with internet access (docling-tools models download), copy the folder, and pass "
                    "--docling-models FOLDER; or use the standard engine.") from exc
            raise
        scores = {}
        for idx, (page_number, *_rest) in enumerate(prepared_pages, 1):
            score = None
            for key in (idx, idx - 1):          # Docling numbers pages from 1 (older versions from 0)
                try:
                    score = float(result.confidence.pages[key].ocr_score)
                    break
                except Exception:
                    continue
            scores[page_number] = score if score is not None and score == score else 1.0   # NaN -> 1.0
        return self.blocks_from_document(result.document, prepared_pages, scores), scores

    @staticmethod
    def blocks_from_document(doc, prepared_pages: list, scores: dict) -> list:
        """Map a DoclingDocument onto our Block model (reading order is Docling's).
        prepared_pages = [(page_number, dpi, height_px, width_px, ...)]"""
        from docling_core.types.doc import ContentLayer, PictureItem, TableItem
        blocks = []
        seen_captions = set()
        layers = {ContentLayer.BODY, ContentLayer.FURNITURE}
        for item, _level in doc.iterate_items(included_content_layers=layers):
            prov = item.prov[0] if getattr(item, "prov", None) else None
            if prov is None or not (1 <= prov.page_no <= len(prepared_pages)):
                continue
            page_number, page_dpi, page_h_px = prepared_pages[prov.page_no - 1][:3]
            page_h_pt = page_h_px * 72.0 / page_dpi
            bb = prov.bbox.to_top_left_origin(page_height=page_h_pt)
            k = page_dpi / 72.0
            box = (int(bb.l * k), int(bb.t * k), int(math.ceil(bb.r * k)), int(math.ceil(bb.b * k)))
            conf = scores.get(page_number, 1.0)
            label = getattr(item.label, "value", str(item.label))
            if isinstance(item, TableItem):
                grid = [[(cell.text or "").strip() for cell in row] for row in item.data.grid]
                merges = sorted({(c.start_row_offset_idx, c.start_col_offset_idx, c.end_row_offset_idx - 1, c.end_col_offset_idx - 1)
                                 for c in item.data.table_cells if c.row_span > 1 or c.col_span > 1})
                header_rows = sum(1 for row in item.data.grid if row and all(c.column_header for c in row)) or (1 if grid and _looks_like_header(grid[0]) else 0)
                table = TableData(grid=grid, conf=[[conf] * len(r) for r in grid], merges=list(merges), header_rows=min(header_rows, 3))
                blk = Block("table", page_number, box, table=table,
                            lines=[Line(" ".join(" ".join(r) for r in grid), conf, box, _estimate_word_boxes(" ".join(" ".join(r) for r in grid), box, conf))])
                cap = item.caption_text(doc) if hasattr(item, "caption_text") else ""
                if cap:
                    blk.meta["caption"] = cap
                    for ref in item.captions:
                        seen_captions.add(ref.cref)
                blocks.append(blk)
                if cap:   # emit the caption as its own block too (Excel caption row + Word report)
                    meta = dict(caption_meta(cap, "table"), attach="next")
                    blk.meta["caption_label"] = meta["caption_label"]
                    blocks.insert(len(blocks) - 1, Block("caption", page_number, box, text=cap, meta=meta,
                                                         lines=[Line(cap, conf, box, _estimate_word_boxes(cap, box, conf))]))
                continue
            if isinstance(item, PictureItem):
                blk = Block("figure", page_number, box)
                cap = item.caption_text(doc) if hasattr(item, "caption_text") else ""
                blocks.append(blk)
                if cap:
                    for ref in item.captions:
                        seen_captions.add(ref.cref)
                    meta = dict(caption_meta(cap, "figure"), attach="prev")
                    blk.meta.update({"caption": cap, "caption_label": meta["caption_label"]})
                    blocks.append(Block("caption", page_number, box, text=cap, meta=meta,
                                        lines=[Line(cap, conf, box, _estimate_word_boxes(cap, box, conf))]))
                continue
            text = normalize_ocr_text(getattr(item, "text", "") or "")
            if not text or getattr(item, "self_ref", None) in seen_captions:
                continue
            meta = {}
            if label in ("section_header", "title"):
                kind = "heading"
                m = RE_PARA_NUM.match(text)
                meta = {"level": (m.group("num").count(".") + 1) if m else 1, "title": text}
                if m:
                    meta["number"] = m.group("num")
            elif label == "list_item":
                kind = "list_item"
                marker = (getattr(item, "marker", "") or "").strip()
                if marker and not text.startswith(marker):
                    text = f"{marker} {text}"
                meta = {"marker": marker}
            elif label == "caption":
                kind, meta = "caption", caption_meta(text, "figure")
            elif label == "page_header":
                kind = "page_header"
            elif label == "page_footer":
                kind = "page_footer"
            else:
                kind, meta = classify_text_block(text, 3)
                if kind == "heading":
                    kind, meta = "paragraph", {}
            blocks.append(Block(kind, page_number, box, text=text, meta=meta,
                                lines=[Line(text, conf, box, _estimate_word_boxes(text, box, conf))]))
        return blocks


# =============================================================================
# 9. REQUIREMENT / CAPTION / TABLE EXTRACTION
#    Deterministic rules, in this order:
#      a. text is split into sentences; a sentence with a requirement keyword is a
#         requirement (MIL-STD-961: "shall" = binding, "will" = intent, "should" = goal)
#      b. a keyword sentence ending in ":" is a STEM; each list item below it becomes
#         "<stem> <marker> <item>" (one row per item, nested lists are supported)
#      c. a table with a requirement column (by header name, or a column where most
#         cells contain a keyword) gives one requirement per row, other columns are
#         kept as attributes (e.g. "Method: T")
#      d. every table becomes one row (text grid) + its own worksheet; every caption one row
# =============================================================================
# numbers where a letter probably replaced a digit (1O0, 2l.5): flagged, never changed
RE_SUSPECT_NUMBER = re.compile(r"(?<![A-Za-z])(?:\d+[OoIil|]+\d+[A-Za-z]?|\d+[OoIil|]+(?=[.,]\d)|[OoIl|]\d+(?![A-Za-z]))(?:[.,]\d+)?")
# Words that end with a period but do NOT end a sentence. Units (ms, min, ft, lbs ...) are deliberately
# absent: "... within 100 ms. The display shall ..." is two requirements.
ABBREVIATIONS = {"e.g", "i.e", "fig", "figs", "no", "nos", "para", "paras", "ref", "refs", "rev", "sec", "vol",
                 "approx", "dept", "govt", "mr", "mrs", "dr", "vs", "cf", "al", "ch", "art", "appx", "app", "eq",
                 "eqs", "incl", "resp", "mfr", "spec", "specs", "tab", "u.s", "u.s.a", "p", "pp", "op", "cit", "viz",
                 "nom", "st", "mt", "jr", "sr", "inc", "corp", "co", "ltd"}
CONTINUATION_START = re.compile(r"^(?:This|These|That|Those|It|Its|Such|The above|Said|Where|Except|Unless|Including|"
                                r"In addition|Additionally|Also|However|Otherwise|For example|E\.g\.|I\.e\.)\b")
WEAK_REQUIREMENT_HEADERS = ("description", "text", "statement", "specification", "spec")
# verification methods (MIL-STD-961: analysis, demonstration, examination, test; NASA/SRS: inspection)
METHOD_NAMES = {"i": "Inspection", "a": "Analysis", "d": "Demonstration", "t": "Test", "e": "Examination",
                "s": "Similarity", "inspection": "Inspection", "analysis": "Analysis", "demonstration": "Demonstration",
                "demo": "Demonstration", "test": "Test", "examination": "Examination", "exam": "Examination",
                "similarity": "Similarity", "insp": "Inspection"}
VERIFICATION_HEADERS = ("method", "verification", "verif", "ver method", "vm", "v v", "qualification method", "test method")
RE_REFERENCES = re.compile(
    r"\b(?:MIL|DOD|DoD|FED|NASA|JSSG)-(?:STD|DTL|PRF|HDBK|SPEC)-\d+[A-Z]?\b"
    r"|\bMIL-[A-Z]-\d+[A-Z]?\b"
    r"|\b(?:ISO|IEC|ISO/IEC|ISO/IEC/IEEE)\s+\d+(?:-\d+)*(?::\d{4})?"
    r"|\bIEEE(?:\s+Std)?\s+\d+(?:\.\d+)?(?:-\d{4})?"
    r"|\b(?:SAE\s+)?(?:AS|ARP|AMS)\d{3,}[A-Z]?\b|\bRTCA\s+DO-\d+[A-Z]?\b|\bDO-\d{3}[A-Z]?\b"
    r"|\bSTANAG\s+\d{4}\b|\bNASM\s?\d+\b|\bASTM\s+[A-Z]\d+\b|\bANSI[/ ][\w./-]+\d"
    r"|\b(?:TABLE|Table)\s+(?:[A-Z]-)?(?:\d+(?:[-.]\d+)*|[IVXL]+\b)"
    r"|\b(?:FIGURE|Figure|FIG\.|Fig\.)\s+(?:[A-Z]-)?\d+(?:[-.]\d+)*"
    r"|\b(?:paragraph|para\.|section|Section|SECTION|appendix|Appendix|APPENDIX)\s+(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)\b")


def find_references(text: str) -> str:
    seen = []
    for m in RE_REFERENCES.finditer(text or ""):
        ref = re.sub(r"\s+", " ", m.group(0)).rstrip(".")
        if ref not in seen:
            seen.append(ref)
    return "; ".join(seen)


def method_name(value: str) -> str:
    """'T' -> 'Test'; 'A, T' -> 'Analysis, Test'; unknown text is kept as written."""
    parts = [p for p in re.split(r"[\s,/&+;]+", (value or "").strip().rstrip(".")) if p]
    names = [METHOD_NAMES.get(p.lower().rstrip(".")) for p in parts]
    return ", ".join(names) if parts and all(names) else (value or "").strip()
QUALITY_RULES = [
    ("Placeholder TBD/TBR/TBS", re.compile(r"\bTB[DRSC]\b|\bto be (?:determined|resolved|supplied|specified|confirmed|defined)\b", re.I)),
    ("Escape clause", re.compile(r"\b(?:as appropriate|as applicable|as required|if possible|where possible|if practical|"
                                 r"if practicable|to the extent (?:possible|practical|practicable)|as necessary|if necessary|"
                                 r"when required|if required|so far as is possible)\b", re.I)),
    ("Vague term", re.compile(r"\b(?:adequate|appropriate|sufficient|reasonable|user[- ]friendly|easy|easily|quickly|fast|"
                              r"robust|flexible|efficient|effective|minimi[sz]e|maximi[sz]e|optimi[sz]e|approximately|several|"
                              r"various|significant|state[- ]of[- ]the[- ]art|as soon as possible|timely)\b", re.I)),
    ("Open-ended list", re.compile(r"\b(?:etc\.?|and so on|including but not limited to|but not limited to)(?=\W|$)", re.I)),
    ("Ambiguous and/or", re.compile(r"\band/or\b", re.I)),
]


def split_sentences(text: str) -> list:
    """Split into sentences, respecting abbreviations, decimals, section numbers and IDs.
    Returns [(start, end)] character spans."""
    spans, start = [], 0
    for m in re.finditer(r"[.!?][\"')\]]*\s+", text):
        end = m.end()
        before = text[start:m.start() + 1]
        last_token = re.findall(r"[\w.]+\.?$", before)
        token = last_token[0].rstrip(".").lower() if last_token else ""
        nxt = text[end:end + 1]
        if not nxt or nxt.islower() or nxt.isdigit() or nxt in ",;:)":
            continue                                   # "... para. 3" / "i.e. the" -> same sentence
        if re.match(r"\([A-Za-z0-9&/-]{1,12}\)[,;:]?\s+[a-z]", text[end:]):
            continue                                   # "repair. (MTTR) shall ..." - a stray OCR period
        if token in ABBREVIATIONS or (last_token and re.fullmatch(r"[a-z]", last_token[0].rstrip("."))
                                      and not re.search(r"\d\s*[a-z]\.$", before)):
            continue                                   # "Fig. 3", "e.g. The", inline list marker "a. Search"
        spans.append((start, m.start() + 1 + len(m.group(0).rstrip()) - 1))
        start = end
    if start < len(text) and text[start:].strip():
        spans.append((start, len(text.rstrip())))
    return [(s, e) for s, e in spans if text[s:e].strip()]


class RequirementExtractor:
    def __init__(self, settings: Settings):
        self.settings = settings
        keys = sorted(settings.keywords.keys(), key=len, reverse=True)
        alternation = "|".join(r"\s+".join(re.escape(part) for part in k.split()) for k in keys)
        self.re_keyword = re.compile(r"(?<![A-Za-z])(" + alternation + r")(?![A-Za-z])", re.I)
        self.classes = {" ".join(k.lower().split()): v for k, v in settings.keywords.items()}

    # ---- helpers --------------------------------------------------------------------
    def keyword_in(self, text: str) -> Optional[str]:
        m = self.re_keyword.search(text or "")
        if not m:
            return None
        kw = " ".join(m.group(1).lower().split())
        # "May 1987" / "Will Smith": a capitalized modal right after a sentence start is fine,
        # but skip "will" used as a noun ("the will of"): rare - accepted.
        return kw

    def repair_keywords(self, text: str) -> tuple:
        """Fix OCR-garbled keywords; returns (text, [notes])."""
        notes = []
        if not self.settings.fix_ocr_keywords:
            return text, notes
        for word, pattern in OCR_KEYWORD_REPAIRS:
            if word not in self.classes and not any(word in k for k in self.classes):
                continue

            def fix(m, word=word):
                tok = m.group(0)
                if tok.lower() == word:
                    return tok
                fixed = word.capitalize() if tok[:1].isupper() else word
                notes.append(f"OCR keyword repaired: '{tok}' -> '{fixed}'")
                return fixed
            text = pattern.sub(fix, text)
        return text, notes

    def quality_notes(self, text: str) -> list:
        if not self.settings.quality_checks:
            return []
        notes = []
        for name, pattern in QUALITY_RULES:
            found = sorted({m.group(0).strip() for m in pattern.finditer(text)}, key=str.lower)
            if found:
                notes.append(f"{name}: {', '.join(found[:4])}")
        n_modal = len(self.re_keyword.findall(text))
        if n_modal > 1:
            notes.append(f"Possible compound requirement ({n_modal} keywords)")
        return notes

    def review_for_tokens(self, tokens: list, text: str, extra: list = ()) -> tuple:
        """-> (min_confidence, [review reasons]) for the OCR tokens that make up an item."""
        reasons = list(extra)
        confs = [t[1] for t in tokens]
        min_conf = min(confs) if confs else None
        # Low confidence is flagged for numbers (a misread digit changes the requirement and no
        # dictionary can catch it). For words, the dictionary/format checks are far more reliable:
        # on the test scans, low-confidence words were usually read correctly.
        low = [(t[0], t[1]) for t in tokens if token_attention((t[0], t[1], ""), self.settings)]
        if low:
            shown = ", ".join(f"'{t}' ({c:.2f})" for t, c in sorted(low, key=lambda x: x[1])[:6])
            reasons.append(f"Low OCR confidence: {shown}")
        stray = []
        for a, b, c in zip(tokens, tokens[1:], tokens[2:] + [("", 1.0, "")]):
            if (re.search(r"[A-Za-z0-9]\.$", a[0]) and not re.fullmatch(r"(?:[A-Za-z]\.){1,3}", a[0])
                    and a[0][:-1].lower() not in ABBREVIATIONS
                    and (b[0][:1].islower() or b[0][:1].isdigit()
                         or (re.fullmatch(r"\d+\.", a[0]) and RE_UNIT.fullmatch(b[0].rstrip(".,;:")))
                         or (re.fullmatch(r"\([A-Za-z0-9&/-]{1,12}\)[,;:]?", b[0]) and c[0][:1].islower()))):
                stray.append(f"{a[0]} {b[0]}")
        if stray:
            reasons.append("Stray period? " + "; ".join(f"'{x}'" for x in stray[:5]))
        suspicious = []
        for t in tokens:
            if len(t) > 2 and t[2] and (t[0], t[2]) not in suspicious:
                suspicious.append((t[0], t[2]))
        if suspicious:
            reasons.append("Check word(s): " + "; ".join(f"'{w}' ({why})" for w, why in suspicious[:6]))
        suspects = sorted(set(RE_SUSPECT_NUMBER.findall(text)))
        if suspects:
            reasons.append("Number may contain a misread letter: " + ", ".join(suspects[:5]))
        return min_conf, reasons

    # ---- main entry ------------------------------------------------------------------
    def extract(self, doc: DocResult) -> list:
        items = []
        source = Path(doc.source).name
        vocab = document_text_context(doc, self.settings)
        self.ctx = vocab
        dpi_of = {p.number: p.dpi for p in doc.pages}
        blocks = [b for b in doc.blocks if b.kind not in ("page_header", "page_footer")]
        self.id_prefixes = self._learn_id_prefixes(blocks)
        section = ""
        i = 0
        while i < len(blocks):
            b = blocks[i]
            if b.kind == "heading" and self.keyword_in(self.repair_keywords(b.text)[0]):
                b.kind = "paragraph"             # a 'heading' that states a requirement is a paragraph
            if b.kind == "heading":
                num, title = b.meta.get("number", ""), b.meta.get("title", b.text)
                section = f"{num} {title}".strip() if num else title
                i += 1
                continue
            if b.kind == "caption":
                if not b.meta.get("duplicate_of_table"):
                    items.append(self._caption_item(b, source, section))
                i += 1
                continue
            if b.kind == "table" and b.table is not None:
                items.extend(self._table_items(b, source, section))
                i += 1
                continue
            if b.kind == "figure":
                items.extend(self._figure_items(b, source, section))
                i += 1
                continue
            if b.kind in ("paragraph", "list_item"):
                consumed = self._text_block_items(blocks, i, source, section, vocab, dpi_of, items)
                i += consumed
                continue
            i += 1
        items.extend(self._repeated_furniture_items(doc, source))
        # verification methods and references
        matrix = self._verification_matrix(doc)
        for it in items:
            if it.item_type != "Requirement":
                continue
            it.references = find_references(it.text)
            if not it.verification and it.doc_ref:
                key = clean_para_number(it.doc_ref.split()[0].rstrip("."))
                if key in matrix:
                    it.verification = matrix[key] + " (from verification matrix)"
        # item numbers
        counters = Counter()
        prefix = {"Requirement": "R", "Table": "T", "Table Caption": "TC", "Figure Caption": "FC"}
        for it in items:
            counters[it.item_type] += 1
            width = 4 if it.item_type == "Requirement" else 3
            it.item_id = f"{prefix.get(it.item_type, 'X')}-{counters[it.item_type]:0{width}d}"
        return items

    @staticmethod
    def _learn_id_prefixes(blocks: list) -> Counter:
        """Prefixes of the requirement IDs this document really uses ('SRS' in [SRS-101], 'ENV' in a
        table ID column). A bare 'MK-54 torpedo ...' is only read as an ID if MK is such a prefix."""
        prefixes = Counter()
        for b in blocks:
            if b.kind in ("paragraph", "list_item", "heading") and b.text:
                m = RE_LEADING_ID.match(b.text)
                if m and _starts_with_delimited_id(b.text):
                    prefixes[_id_prefix(m.group("id"))] += 1
                for tm in re.finditer(r"[\[(](" + RE_REQ_ID + r")[\])]", b.text):
                    if "-" in tm.group(1) or "_" in tm.group(1):
                        prefixes[_id_prefix(tm.group(1))] += 1
            elif b.kind == "table" and b.table is not None:
                for row in b.table.grid[b.table.header_rows:]:
                    if row and row[0] and re.fullmatch(r"\s*(?:" + RE_REQ_ID + r")\s*", row[0]) and re.search(r"[-_]", row[0]):
                        prefixes[_id_prefix(row[0].strip())] += 1
        return prefixes

    def _repeated_furniture_items(self, doc: DocResult, source: str) -> list:
        """Keyword text printed in the header/footer of many pages (e.g. a handling notice) is reported
        once, flagged, instead of once per page or not at all."""
        groups = []                               # [(kind, notice text, [blocks])], near-identical notices together
        for b in doc.blocks:
            if b.kind in ("page_header", "page_footer") and b.meta.get("repeated_keyword_text"):
                key = b.meta.get("notice_key") or " ".join(b.text.lower().split())
                for kind, gkey, members in groups:
                    if kind == b.kind and (gkey == key or (re.findall(r"\d+", gkey) == re.findall(r"\d+", key)
                                                          and _similar(gkey, key, at_least=0.9) >= 0.9)):
                        members.append(b)
                        break
                else:
                    groups.append((b.kind, key, [b]))
        out = []
        for kind, _key, group in groups:
            first = max(group, key=lambda x: x.conf)      # the best-read copy
            clean = re.sub(r"^\s*(?:page\s*)?\d{1,4}(?:\s*of\s*\d{1,4})?\s+|\s+(?:page\s*)?\d{1,4}(?:\s*of\s*\d{1,4})?\s*$",
                           " ", first.text, flags=re.I)
            text, notes = self.repair_keywords(" ".join(clean.split()))
            kw = self.keyword_in(text)
            if not kw:
                continue
            pages = sorted({p for b in group for p in (b.pages or [b.page])})
            where = "header" if kind == "page_header" else "footer"
            tokens = word_tokens((w for ln in first.lines for w in ln.words), self.ctx)
            if clean.strip() != first.text.strip():          # leave out the page number printed on the same line
                while tokens and re.fullmatch(r"\d{1,4}", tokens[-1][0]) and not text.rstrip().endswith(tokens[-1][0]):
                    tokens = tokens[:-1]
                while tokens and re.fullmatch(r"\d{1,4}", tokens[0][0]) and not text.lstrip().startswith(tokens[0][0]):
                    tokens = tokens[1:]
            conf, reasons = self.review_for_tokens(
                tokens, text, [f"Repeated in the page {where} on {len(pages)} pages - check whether it is a requirement"] + notes)
            out.append(ExtractedItem("Requirement", source, _pages_text(pages), "", text=text, keyword=kw,
                                     req_class=self.classes.get(kw, ""), found_in=f"Page {where} (repeated)",
                                     ocr_conf=conf, review_reasons=reasons, quality_notes=self.quality_notes(text),
                                     block_uids=[b.uid for b in group]))
        return out

    def _figure_items(self, b: Block, source: str, section: str) -> list:
        label_text = " ".join(ln.text for ln in b.lines)
        kw = self.keyword_in(self.repair_keywords(label_text)[0])
        if not kw:
            return []
        tokens = word_tokens((w for ln in b.lines for w in ln.words), self.ctx)
        conf, reasons = self.review_for_tokens(tokens, label_text, ["Keyword found inside a figure - check manually"])
        return [ExtractedItem("Requirement", source, b.page_label(), section, text=label_text, keyword=kw,
                              req_class=self.classes.get(kw, ""), found_in="Figure text", ocr_conf=conf,
                              review_reasons=reasons, block_uids=[b.uid])]

    @staticmethod
    def _verification_matrix(doc: DocResult) -> dict:
        """Read verification cross-reference matrices: a column of paragraph numbers and two or
        more method columns (I / A / D / T ...) marked with X. Returns {paragraph: 'Analysis, Test'}."""
        matrix = {}
        for b in doc.blocks:
            t = b.table
            if b.kind != "table" or t is None or not t.header_rows or t.n_rows < 2:
                continue
            header = [(h or "").strip().lower().rstrip(".") for h in t.grid[0]]
            method_cols = {c: METHOD_NAMES[h] for c, h in enumerate(header) if h in METHOD_NAMES}
            if len(method_cols) < 2:
                continue
            data = t.grid[t.header_rows:]
            para_col = None
            def para(v):                      # OCR tolerance: "3,2.1.1.." -> "3.2.1.1"
                return clean_para_number(re.sub(r"(?<=\d),(?=\d)", ".", (v or "").strip()).rstrip("."))

            for c in range(t.n_cols):
                vals = [para(r[c]) for r in data if c < len(r) and r[c].strip()]
                if c not in method_cols and vals and sum(1 for v in vals if re.fullmatch(r"(?:\d{1,2}|[A-Z])(?:\.[\dlIi|]{1,3}){1,7}\.?", v)) >= 0.6 * len(vals):
                    para_col = c
                    break
            if para_col is None:
                continue
            for r in data:
                num = para(r[para_col]) if para_col < len(r) else ""
                marks = [name for c, name in method_cols.items()
                         if c < len(r) and re.fullmatch(r"\s*(?:[xX\u2713\u2714\u2022*+]|yes|Yes|YES)\s*", r[c] or "")]
                if num and marks:
                    matrix[num] = ", ".join(dict.fromkeys(marks))
        return matrix

    # ---- captions and tables --------------------------------------------------------------
    def _caption_item(self, b: Block, source: str, section: str) -> ExtractedItem:
        kind = b.meta.get("caption_kind", "figure")
        tokens = word_tokens((w for ln in b.lines for w in ln.words), self.ctx)
        conf, reasons = self.review_for_tokens(tokens, b.text)
        return ExtractedItem("Table Caption" if kind == "table" else "Figure Caption", source, b.page_label(), section,
                             doc_ref=b.meta.get("caption_label", ""), text=b.text, found_in="Caption",
                             ocr_conf=conf, review_reasons=reasons, block_uids=[b.uid])

    def _table_items(self, b: Block, source: str, section: str) -> list:
        t = b.table
        caption = b.meta.get("caption", "")
        label = b.meta.get("caption_label", "")
        min_conf = min((c for row in t.conf for c in row), default=1.0)
        reasons = []
        flagged = [t.grid[r][c] for r in range(t.n_rows) for c in range(len(t.grid[r]))
                   if t.grid[r][c] and _cell_attention(t, r, c, self.ctx, self.settings)]
        if flagged:
            reasons.append(f"{len(flagged)} table cell(s) to check against the scan, e.g. " +
                           "; ".join(f"'{x[:40]}'" for x in flagged[:3]))
        suspects = sorted({m for row in t.grid for cell in row for m in RE_SUSPECT_NUMBER.findall(cell or "")})
        if suspects:
            reasons.append("Number may contain a misread letter: " + ", ".join(suspects[:5]))
        if t.continued_pages:
            reasons.append("Table continues across pages - check the joined rows")
        notes = [] if caption else ["No caption found near this table"]
        out = [ExtractedItem("Table", source, b.page_label(), section, doc_ref=label, title=caption,
                             text=t.as_text(), found_in=f"Table ({t.n_rows} rows x {t.n_cols} columns)",
                             ocr_conf=min_conf, review_reasons=reasons, quality_notes=notes, table=t, block_uids=[b.uid])]
        out.extend(self._requirement_rows_from_table(b, source, section, caption or label))
        return out

    def _requirement_rows_from_table(self, b: Block, source: str, section: str, caption: str) -> list:
        t = b.table
        s = self.settings
        if t.n_rows < 2 or t.n_cols < 1:
            return []
        header = [(c or "").strip() for c in t.grid[0]] if t.header_rows else []
        data_start = t.header_rows
        data = t.grid[data_start:]
        if not data:
            return []
        n_cols = t.n_cols

        def norm_header(h):
            return " ".join(re.sub(r"[^a-z# ]+", " ", h.lower()).split())

        id_headers = {norm_header(x) for x in s.id_column_headers}

        def is_id_header(hn):
            """'Req ID', 'Requirement No.', 'Requirement Number', 'Para #' ... name an ID column."""
            return hn in id_headers or bool(re.search(r"(?:^|\s)(?:id|ids|no|nos|nr|num|number|#|ident|identifier|ref)$", hn))

        def is_attribute_header(hn):
            """'Requirement Title / Type / Status / Owner ...' describe the requirement - they are not its text."""
            return bool(re.search(r"(?:^|\s)(?:title|name|type|category|class|status|owner|source|priority|rationale|"
                                  r"level|phase|allocation|trace|parent|method)$", hn))

        modal_share = [sum(1 for r in data if c < len(r) and self.keyword_in(r[c])) / len(data) for c in range(n_cols)]
        mean_words = [statistics.fmean(word_count(r[c]) if c < len(r) else 0 for r in data) for c in range(n_cols)]
        text_col, header_says = None, False
        named = []           # columns whose header says "Requirement ..." (not "Requirement ID")
        for c, h in enumerate(header):
            hn = norm_header(h)
            if not hn or word_count(hn) > 3 or is_id_header(hn) or is_attribute_header(hn):
                continue
            if any(hn == k or hn.startswith(k) for k in s.requirement_table_headers):
                named.append((hn in s.requirement_table_headers or hn.endswith(("text", "statement")), modal_share[c], mean_words[c], -c))
            elif any(hn == k or hn.startswith(k) for k in WEAK_REQUIREMENT_HEADERS) and modal_share[c] >= 0.3:
                text_col = c                             # "Description" column that contains shall-statements
        if named:
            best = max(named)                            # exact "Requirement" / "... Text" first, then most shall-cells
            modal_elsewhere = max((share for c, share in enumerate(modal_share) if c != -best[3]), default=0.0)
            if (best[1] > 0 or best[2] >= 3) and not (best[1] == 0 and modal_elsewhere >= 0.5):
                text_col, header_says = -best[3], True   # every row of that column is a requirement
            elif modal_elsewhere >= 0.5:
                text_col = None                          # the shall-statements are in another column (found below)
        if text_col is None and modal_share and max(modal_share) >= 0.5:
            text_col = int(np.argmax(modal_share))
        rows_out = []
        if text_col is None:
            # not a requirement table: still catch any cell that states a requirement
            for r_off, row in enumerate(data):
                for c, cell in enumerate(row):
                    kw = self.keyword_in(cell)
                    if kw and word_count(cell) >= 4:
                        attrs = "; ".join(f"{header[k] if k < len(header) and header[k] else f'Column {k + 1}'}: {v}"
                                          for k, v in enumerate(row) if k != c and v)
                        rows_out.append(self._table_requirement(b, source, section, caption, cell, kw, "", attrs,
                                                                t.conf[data_start + r_off][c], "Table cell",
                                                                _cell_words(t, data_start + r_off, c)))
            return rows_out
        id_col = None
        for c, h in enumerate(header):
            if c != text_col and norm_header(h) and is_id_header(norm_header(h)):
                id_col = c
                break
        if id_col is None:
            for c in range(n_cols):
                if c != text_col:
                    vals = [r[c] for r in data if c < len(r) and r[c]]
                    if vals and sum(1 for v in vals if RE_ID_CELL.match(v)) >= 0.6 * len(vals):
                        id_col = c
                        break
        seen = set()
        for r_off, row in enumerate(data):
            text = (row[text_col] if text_col < len(row) else "").strip()
            if not text or (text, r_off) in seen:
                continue
            seen.add((text, r_off))
            kw = self.keyword_in(text)
            if not kw and not header_says:
                continue
            attrs = "; ".join(f"{header[c] if c < len(header) and header[c] else f'Column {c + 1}'}: {row[c]}"
                              for c in range(min(n_cols, len(row))) if c not in (text_col, id_col) and row[c])
            ref = row[id_col].strip().strip(".,;:'`[]()") if id_col is not None and id_col < len(row) else ""
            item = self._table_requirement(b, source, section, caption, text, kw or "", ref, attrs,
                                           t.conf[data_start + r_off][text_col], "Table row",
                                           _cell_words(t, data_start + r_off, text_col))
            for c, h in enumerate(header):
                if c < len(row) and row[c] and c not in (text_col, id_col) and norm_header(h).startswith(VERIFICATION_HEADERS):
                    item.verification = method_name(row[c])
            rows_out.append(item)
        return rows_out

    def _table_requirement(self, b, source, section, caption, text, kw, ref, attrs, cell_conf, found_in, cell_words=None) -> ExtractedItem:
        text, repair_notes = self.repair_keywords(text)
        kw = kw or self.keyword_in(text) or ""
        words = cell_words or [[w, cell_conf] for w in text.split()]
        tokens = word_tokens((Word(w, c, (0, 0, 0, 0)) for w, c in words), self.ctx)
        min_conf, reasons = self.review_for_tokens(tokens, text, repair_notes)
        cell_conf = min_conf if min_conf is not None else cell_conf
        return ExtractedItem("Requirement", source, b.page_label(), section, doc_ref=ref, text=text, keyword=kw,
                             req_class=self.classes.get(kw, "Listed in requirement table" if not kw else ""),
                             found_in=found_in, context=caption, attributes=attrs, ocr_conf=cell_conf,
                             review_reasons=reasons, quality_notes=self.quality_notes(text), block_uids=[b.uid])

    # ---- paragraphs and lists ----------------------------------------------------------------
    def parse_head(self, text: str) -> tuple:
        """Split '3.2.1.1 Detection range. The radar shall ...' -> ('3.2.1.1', 'Detection range', body, offset)
        and '[SRS-101] The GCS shall ...' -> ('SRS-101', '', body, offset).
        'MK-54 torpedo ...' and '3.3 V shall ...' are left alone (a designator and a quantity)."""
        ref, title, body = "", "", text
        prefixes = getattr(self, "id_prefixes", Counter())
        m = RE_LEADING_ID.match(body)
        if m and (("-" in m.group("id") or "_" in m.group("id")) and
                  (_starts_with_delimited_id(body) or prefixes.get(_id_prefix(m.group("id")), 0) >= 2)):
            ref, body = m.group("id"), m.group("rest")
        else:
            m = RE_PARA_NUM.match(body)
            if (m and ("." in m.group("num") or m.group("dot")) and m.group("rest")[:1].isupper()
                    and not _starts_with_unit(m.group("rest"))):
                ref, body = clean_para_number(m.group("num")), m.group("rest")
        if ref:
            t = re.match(r"^(?P<title>[A-Z][^.:;!?\[\]]{0,80}?)[.:]{1,3}['`·,]?(?:\s+|(?=[A-Z]))(?P<body>[A-Z\[(\"].*)$", body, re.S)
            if (t and word_count(t.group("title")) <= 8 and not _modal_re().search(t.group("title"))
                    and not re.search(r"\s(?:The|A|An|This|These|Each|All|Any)\s", t.group("title"))):
                title, body = t.group("title").strip(), t.group("body")
        offset = len(text) - len(body)
        return ref, title, body, offset

    def _text_block_items(self, blocks: list, i: int, source: str, section: str, vocab: set, dpi_of: dict, items: list) -> int:
        """Handle a paragraph/list item (and, for a stem, the list below it). Returns blocks consumed."""
        b = blocks[i]
        tokens = block_tokens(b, vocab) if b.lines else [(w, 1.0, "") for w in b.text.split()]
        text, spans = tokens_text(tokens)
        marker = ""
        lead = RE_LIST_MARKER.match(text) or RE_NUMBERED_ITEM.match(text) if b.kind == "list_item" else None
        if lead:
            marker = lead.group("marker")
        body_start = len(text) - len(lead.group("rest")) if lead else 0
        ref, title, body, off = self.parse_head(text[body_start:])
        body_start += off
        if marker and not ref:
            ref = marker
        extra_reasons = ["Text continues across pages - check the join"] if b.meta.get("continued_across_pages") else []

        # sentences with requirement keywords (and the non-keyword sentences that explain them)
        units = []
        for s0, e0 in split_sentences(text[body_start:]):
            s, e = s0 + body_start, e0 + body_start
            sent = text[s:e].strip()
            kw = self.keyword_in(self.repair_keywords(sent)[0])
            if kw:
                units.append([s, e, kw])
            elif units and CONTINUATION_START.match(sent) and not sent.endswith(":"):
                units[-1][1] = e
        if not units:
            return 1

        dpi = dpi_of.get(b.page, 200)
        # a stem inside the block ("... shall provide:" with the first items on the next rows of the same block)
        inline_items = []
        stem_unit = None
        for u in units:
            if text[u[0]:u[1]].strip().endswith(":") and u[1] < len(text.rstrip()) - 1:
                row_entries = self._row_entries(b, vocab, text, spans, start_char=u[1])
                if row_entries:
                    stem_unit, inline_items = u, row_entries
                    break
        if stem_unit is None and text[units[-1][0]:units[-1][1]].strip().endswith(":"):
            stem_unit = units[-1]
        last = stem_unit
        if last is not None:
            # ---- a stem: collect the list items that follow
            children = list(inline_items)
            skipped = []
            j = i + 1
            while j < len(blocks):
                nb = blocks[j]
                if nb.kind in ("figure", "caption") and children and j + 1 < len(blocks):
                    after = next((x for x in blocks[j + 1:] if x.kind not in ("figure", "caption")), None)
                    prev_x0 = children[-1][0]
                    if after is not None and after.kind == "list_item" and abs(after.box[0] - prev_x0) <= 0.1 * dpi:
                        skipped.append(nb)       # a stamp/signature/figure sitting between two list items
                        j += 1
                        continue
                if b.kind == "list_item" and nb.box[0] <= b.box[0] + 0.1 * dpi:
                    break                        # a sibling item, not a child ("(2) ... format:" then "(3) ...")
                if nb.kind == "list_item":
                    children.extend(self._child_entries(nb, vocab))
                    j += 1
                    continue
                if (nb.kind == "paragraph" and nb.box[0] > b.box[0] + 0.15 * dpi and not RE_PARA_NUM.match(nb.text)
                        and not _starts_with_delimited_id(nb.text) and word_count(nb.text) <= 60):
                    children.extend(self._child_entries(nb, vocab))   # indented items without visible bullets
                    j += 1
                    continue
                break
            # requirements stated before the stem in the same block
            for s, e, kw in [u for u in units if u[1] <= last[0]]:
                items.append(self._req_item(b, source, section, ref, title, text, tokens, spans, s, e, kw, "Paragraph", "", extra_reasons))
            if not children:
                items.append(self._req_item(b, source, section, ref, title, text, tokens, spans, last[0], last[1], last[2],
                                            "Paragraph", "", extra_reasons + ["Ends with ':' but no list items were found below"]))
                return 1
            self._list_items(b, children, source, section, ref, title, text, tokens, spans, last, vocab, items, extra_reasons, dpi)
            for sb in skipped:                   # captions / figures that sat inside the list are exported too
                if sb.kind == "caption" and not sb.meta.get("duplicate_of_table"):
                    items.append(self._caption_item(sb, source, section))
                elif sb.kind == "figure":
                    items.extend(self._figure_items(sb, source, section))
            return j - i

        found_in = "List item" if b.kind == "list_item" else "Paragraph"
        for s, e, kw in units:
            items.append(self._req_item(b, source, section, ref, title, text, tokens, spans, s, e, kw, found_in, "", extra_reasons))
        return 1

    def _row_entries(self, b: Block, ctx, text: str, spans: list, start_char: int) -> list:
        """List items written on the rows after an inline stem inside the same block."""
        entries, n_before = [], 0
        rows = _block_rows(b)
        for row_lines, row_tokens in zip(rows, block_token_rows(b, ctx)):
            first = n_before
            n_before += len(row_tokens)
            if not row_tokens or first >= len(spans) or spans[first][0] < start_char:
                continue
            entries.append((min(ln.box[0] for ln in row_lines), row_tokens, b))
        return entries

    def _child_entries(self, child: Block, ctx) -> list:
        """(x0, tokens, block) items of one child block. An unmarked block whose rows each start like a
        new item ('Search mode' / 'Track mode') is split into one item per row."""
        if not child.lines:
            return [(child.box[0], [(w, 1.0, "") for w in child.text.split()], child)]
        rows = _block_rows(child)
        token_rows = block_token_rows(child, ctx)
        all_tokens = [t for r in token_rows for t in r]
        text = tokens_text(all_tokens)[0]
        if (len(rows) > 1 and not (RE_LIST_MARKER.match(text) or RE_NUMBERED_ITEM.match(text))
                and all(r and word_count(" ".join(t[0] for t in r)) <= 10 and (r[0][0][:1].isupper() or r[0][0][:1].isdigit())
                        for r in token_rows)):
            return [(min(ln.box[0] for ln in rl), tr, child) for rl, tr in zip(rows, token_rows) if tr]
        return [(child.box[0], all_tokens, child)]

    def _list_items(self, stem_block, children, source, section, ref, title, text, tokens, spans, stem_unit, vocab, items, extra, dpi=200.0):
        """children = [(x0, tokens, block)] in reading order."""
        stem_s, stem_e, stem_kw = stem_unit
        tol = 0.08 * dpi                     # items within ~0.08 inch of each other are at the same level
        stem_text, stem_notes = self.repair_keywords(text[stem_s:stem_e].strip())
        stem_tokens = [tok for tok, (a, z) in zip(tokens, spans) if a < stem_e and z > stem_s]
        stack = []          # nested stems: (x0, marker, text, tokens)
        rows = []           # (block, marker_path, tokens)
        for k, (x0, c_tokens, child) in enumerate(children):
            c_text = tokens_text(c_tokens)[0]
            m = RE_LIST_MARKER.match(c_text) or RE_NUMBERED_ITEM.match(c_text)
            c_marker, c_body = (m.group("marker"), m.group("rest")) if m else ("", c_text)
            while stack and x0 <= stack[-1][0] + tol:
                stack.pop()
            nxt = children[k + 1] if k + 1 < len(children) else None
            if c_body.rstrip().endswith(":") and nxt is not None and nxt[0] > x0 + tol:
                stack.append((x0, c_marker, c_body.strip(), c_tokens))
                continue
            path = [(mk, bd) for _, mk, bd, _ in stack] + [(c_marker, c_body.strip())]
            path_tokens = [t for *_, tk in stack for t in tk] + c_tokens
            rows.append((child, path, path_tokens))
        if not self.settings.split_list_items:
            joined = stem_text + " " + " ".join(" ".join(f"{mk} {bd}".strip() for mk, bd in path) for _, path, _ in rows)
            all_tokens = stem_tokens + [t for _, _, tk in rows for t in tk]
            conf, reasons = self.review_for_tokens(all_tokens, joined, extra + stem_notes)
            pages = sorted({p for blk in [stem_block] + [r[0] for r in rows] for p in blk.pages})
            items.append(ExtractedItem("Requirement", source, _page_label(pages), section, doc_ref=ref, title=title,
                                       text=joined.strip(), keyword=stem_kw, req_class=self.classes.get(stem_kw, ""),
                                       found_in="List (stem + all items)", ocr_conf=conf, review_reasons=reasons,
                                       quality_notes=self.quality_notes(joined),
                                       block_uids=list(dict.fromkeys([stem_block.uid] + [r[0].uid for r in rows]))))
            return
        for child, path, path_tokens in rows:
            item_text = " ".join(f"{mk} {bd}".strip() for mk, bd in path)
            full, notes = self.repair_keywords(f"{stem_text} {item_text}")
            conf, reasons = self.review_for_tokens(stem_tokens + path_tokens, full, extra + stem_notes + notes)
            pages = sorted(set(stem_block.pages) | set(child.pages))
            marker_ref = ".".join(mk.strip("().") for mk, _ in path if mk and mk not in "•·*-o◦")
            items.append(ExtractedItem("Requirement", source, _page_label(pages), section,
                                       doc_ref=(f"{ref} {marker_ref}".strip() if marker_ref else ref), title=title,
                                       text=full, keyword=stem_kw, req_class=self.classes.get(stem_kw, ""),
                                       found_in="List item under stem", context=stem_text, ocr_conf=conf,
                                       review_reasons=reasons, quality_notes=self.quality_notes(full),
                                       block_uids=list(dict.fromkeys([stem_block.uid, child.uid]))))

    def _req_item(self, b, source, section, ref, title, text, tokens, spans, s, e, kw, found_in, context, extra) -> ExtractedItem:
        sentence = text[s:e].strip()
        trailing = RE_TRAILING_ID.search(sentence)
        if trailing and ("-" in trailing.group("id") or "_" in trailing.group("id")) \
                and getattr(self, "id_prefixes", Counter()).get(_id_prefix(trailing.group("id")), 0) >= 2:
            trailing = trailing                       # a known requirement-ID prefix
        else:
            trailing = None                           # "(J3)" / "(CB12)" are designators: keep them in the text
        if trailing and not ref:                      # "... within 2 seconds (SRS-103)."
            ref = trailing.group("id")
            ended = sentence.endswith(".")
            sentence = sentence[:trailing.start()].rstrip()
            if ended and not sentence.endswith("."):
                sentence += "."
        fixed, notes = self.repair_keywords(sentence)
        unit_tokens = [tok for tok, (a, z) in zip(tokens, spans) if a < e and z > s]
        reasons = list(extra) + notes
        if found_in == "Paragraph" and not RE_TERMINAL.search(fixed):
            reasons.append("Sentence has no final punctuation - it may be incomplete")
        conf, reasons = self.review_for_tokens(unit_tokens, fixed, reasons)
        return ExtractedItem("Requirement", source, b.page_label(), section, doc_ref=ref, title=title, text=fixed,
                             keyword=kw, req_class=self.classes.get(kw, ""), found_in=found_in, context=context,
                             ocr_conf=conf, review_reasons=reasons, quality_notes=self.quality_notes(fixed),
                             block_uids=[b.uid])


def _cell_words(t: TableData, r: int, c: int) -> list:
    try:
        return t.cell_words[r][c]
    except (IndexError, TypeError):
        return []


def _page_label(pages: list) -> str:
    pages = sorted(set(pages))
    return str(pages[0]) if len(pages) == 1 else f"{pages[0]}-{pages[-1]}"


# =============================================================================
# 10. EXCEL EXPORT
#     Sheet "Extracted Items": one row per requirement, caption and table.
#     One sheet per table (T001, T002, ...), plus "Full Text", "Page Quality", "Run Info".
# =============================================================================
MASTER_COLUMNS = [  # (header, width, description used in the Run Info sheet)
    ("Item #", 10, "Unique ID: R- requirement, T- table, TC- table caption, FC- figure caption"),
    ("Type", 14, "Requirement / Table / Table Caption / Figure Caption"),
    ("Source File", 22, "Input document"),
    ("Page(s)", 8, "Page number(s) in the source document"),
    ("Section", 28, "Nearest heading above the item"),
    ("Doc Ref", 13, "Paragraph number, requirement ID or table/figure number printed in the document"),
    ("Title", 20, "Paragraph title (e.g. 'Detection range') or table caption"),
    ("Content", 72, "The complete requirement text, caption text, or the table as text"),
    ("Keyword", 10, "Requirement keyword found (shall, must, should, will ...)"),
    ("Class", 18, "Mandatory / Goal / Statement of intent (from the keyword)"),
    ("Found In", 20, "Paragraph, list item under a stem, table row ..."),
    ("Parent / Context", 36, "List stem or table caption the requirement belongs to"),
    ("Other Columns", 30, "Other columns of a requirement table row (e.g. parameter, priority)"),
    ("Verification", 16, "Verification method: from the requirement table, or looked up in the document's verification cross-reference matrix (I/A/D/T)"),
    ("References", 26, "Standards, tables, figures and sections cited by the requirement (e.g. MIL-STD-704F; TABLE II)"),
    ("OCR Confidence", 11, "Lowest OCR confidence of the words in this item (0-1). A high value does NOT prove the text is right"),
    ("Needs Review", 9, "Yes when something below deserves a human check"),
    ("Review Reasons", 42, "Why the item needs a check"),
    ("Quality Notes", 36, "INCOSE-style writing checks: TBD, vague terms, escape clauses, and/or ..."),
    ("Table Sheet", 11, "Link to the worksheet holding the full table"),
]
_COL = {name: i for i, (name, _w, _d) in enumerate(MASTER_COLUMNS, 1)}
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill("solid", fgColor="1F3864")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_REVIEW_FILL = PatternFill("solid", fgColor="FCE4D6")
_LOWCONF_FILL = PatternFill("solid", fgColor="FFF2CC")
_WRAP_TOP = Alignment(wrap_text=True, vertical="top")


def _xl(value):
    """Make a value safe for Excel: strip characters Excel rejects, respect the 32,767
    character cell limit."""
    if value is None or isinstance(value, (int, float)):
        return value
    text = ILLEGAL_CHARACTERS_RE.sub("", str(value))
    if len(text) > 32000:
        text = text[:32000] + " ...[truncated - see the table sheet / Word report]"
    return text


def _put(ws, row: int, col: int, value, bold=False, fill=None, wrap=True, number_format=None):
    cell = ws.cell(row=row, column=col)
    v = _xl(value)
    cell.value = v
    if isinstance(v, str) and v.startswith("="):
        cell.data_type = "s"            # text such as "=5 V" must never become a formula
    if bold:
        cell.font = Font(bold=True)
    if fill is not None:
        cell.fill = fill
    if wrap:
        cell.alignment = _WRAP_TOP
    if number_format:
        cell.number_format = number_format
    return cell


def _safe_sheet_title(title: str, existing: set) -> str:
    title = re.sub(r"[\[\]:*?/\\']", "_", title)[:31] or "Sheet"
    base, n = title, 2
    while title.lower() in {e.lower() for e in existing}:
        suffix = f"_{n}"
        title = base[:31 - len(suffix)] + suffix
        n += 1
    return title


def write_workbook(path: Path, runs: list, settings: Settings, multi_doc: bool = False) -> Path:
    """runs = [(DocResult, [ExtractedItem])]. Returns the path actually written."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extracted Items"
    for c, (name, width, _desc) in enumerate(MASTER_COLUMNS, 1):
        cell = _put(ws, 1, c, name, wrap=True)
        cell.font, cell.fill, cell.border = _HEADER_FONT, _HEADER_FILL, _BORDER
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "B2"
    ws.row_dimensions[1].height = 30

    sheet_names = {"Extracted Items", "Full Text", "Page Quality", "Run Info"}
    table_sheets = []           # (sheet title, item, doc)
    row = 2
    for d_index, (doc, items) in enumerate(runs, 1):
        for it in items:
            if it.item_type == "Table" and it.table is not None:
                name = _safe_sheet_title((f"D{d_index}-" if multi_doc else "") + it.item_id.replace("-", ""), sheet_names)
                sheet_names.add(name)
                it.table_sheet = name
                table_sheets.append((name, it, doc))
            values = [it.item_id if not multi_doc else f"D{d_index}-{it.item_id}", it.item_type, it.source_file, it.pages,
                      it.section, it.doc_ref, it.title, it.text, it.keyword, it.req_class, it.found_in, it.context,
                      it.attributes, it.verification, it.references, round(it.ocr_conf, 3) if it.ocr_conf is not None else None,
                      "Yes" if it.needs_review else "No", "\n".join(it.review_reasons), "\n".join(it.quality_notes),
                      it.table_sheet or None]
            for c, v in enumerate(values, 1):
                cell = _put(ws, row, c, v, number_format="0.00" if c == _COL["OCR Confidence"] else None)
                cell.border = _BORDER
            if it.table_sheet:
                link = ws.cell(row=row, column=len(MASTER_COLUMNS))
                link.hyperlink = Hyperlink(ref=link.coordinate, location=f"'{it.table_sheet}'!A1", display=it.table_sheet)
                link.style = "Hyperlink"
                link.alignment = _WRAP_TOP
            row += 1
    if row == 2:
        _put(ws, 2, 1, "-")
        _put(ws, 2, 8, "No requirements, tables or captions were found. Check the Full Text sheet and the Word report.")
        row = 3
    last = row - 1
    ref = f"A1:{get_column_letter(len(MASTER_COLUMNS))}{last}"
    xl_table = XlTable(displayName="ExtractedItems", ref=ref)
    xl_table.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(xl_table)
    review_col = get_column_letter(_COL["Needs Review"])
    ws.conditional_formatting.add(f"A2:{get_column_letter(len(MASTER_COLUMNS))}{last}",
                                  FormulaRule(formula=[f'${review_col}2="Yes"'], fill=_REVIEW_FILL))

    # ---- one sheet per table ----------------------------------------------------------
    for name, it, doc in table_sheets:
        ts = wb.create_sheet(name)
        t = it.table
        ctx = document_text_context(doc, settings)
        _put(ts, 1, 1, it.title or it.doc_ref or "Table (no caption found)", bold=True, wrap=False).font = Font(bold=True, size=12)
        _put(ts, 2, 1, f"{it.item_id}  |  {it.source_file}  |  page(s) {it.pages}  |  {t.n_rows} rows x {t.n_cols} columns", wrap=False)
        back = _put(ts, 3, 1, "<< Back to Extracted Items", wrap=False)
        back.hyperlink = Hyperlink(ref=back.coordinate, location="'Extracted Items'!A1", display="Extracted Items")
        back.style = "Hyperlink"
        top = 5
        widths = [8] * t.n_cols
        merged_hidden = set()
        for r0, c0, r1, c1 in t.merges:
            for rr in range(r0, r1 + 1):
                for cc in range(c0, c1 + 1):
                    if (rr, cc) != (r0, c0):
                        merged_hidden.add((rr, cc))
        for r, grid_row in enumerate(t.grid):
            for c in range(t.n_cols):
                value = grid_row[c] if c < len(grid_row) else ""
                cell = _put(ts, top + r, c + 1, None if (r, c) in merged_hidden else (value or None))
                cell.border = _BORDER
                if r < t.header_rows:
                    cell.font, cell.fill = _HEADER_FONT, _HEADER_FILL
                elif _cell_attention(t, r, c, ctx, settings):
                    cell.fill = _LOWCONF_FILL
                widths[c] = max(widths[c], min(60, max((len(x) for x in str(value).split("\n")), default=0) + 2))
        for r0, c0, r1, c1 in t.merges:
            if r1 < t.n_rows and c1 < t.n_cols and (r1 > r0 or c1 > c0):
                ts.merge_cells(start_row=top + r0, start_column=c0 + 1, end_row=top + r1, end_column=c1 + 1)
        for c, wdt in enumerate(widths, 1):
            ts.column_dimensions[get_column_letter(c)].width = wdt
        if any(_cell_attention(t, r, c, ctx, settings) for r in range(t.header_rows, t.n_rows) for c in range(t.n_cols)):
            _put(ts, top + t.n_rows + 1, 1, "Yellow cells: check against the scan (suspicious word or low-confidence number).", wrap=False)

    # ---- Full Text -----------------------------------------------------------------------
    ft = wb.create_sheet("Full Text", 1)
    headers = [("Source File", 22), ("Page", 7), ("Block #", 8), ("Type", 12), ("Text", 90), ("Mean OCR Conf.", 10),
               ("Min OCR Conf.", 10), ("Words To Check", 36), ("Became Item(s)", 16)]
    for c, (h, wdt) in enumerate(headers, 1):
        cell = _put(ft, 1, c, h)
        cell.font, cell.fill = _HEADER_FONT, _HEADER_FILL
        ft.column_dimensions[get_column_letter(c)].width = wdt
    ft.freeze_panes = "A2"
    r = 2
    for d_index, (doc, items) in enumerate(runs, 1):
        by_block = defaultdict(list)
        for it in items:
            for uid in it.block_uids:
                by_block[uid].append(it.item_id if not multi_doc else f"D{d_index}-{it.item_id}")
        for b in doc.blocks:
            if b.kind == "table" and b.table is not None:
                text = b.table.as_text()
            elif b.kind == "figure":
                text = "[figure] " + " / ".join(ln.text for ln in b.lines)
            else:
                text = b.text
            toks = word_tokens((w for ln in b.lines for w in ln.words), document_text_context(doc, settings))
            low = sorted({tok[0] for tok in toks if token_attention(tok, settings)})
            vals = [Path(doc.source).name, b.page_label(), b.uid, b.kind.replace("_", " "), text, round(b.conf, 3),
                    round(b.min_conf, 3), ", ".join(low[:15]), ", ".join(by_block.get(b.uid, []))]
            for c, v in enumerate(vals, 1):
                _put(ft, r, c, v, fill=_LOWCONF_FILL if (c == 5 and low) else None)
            r += 1
    ft.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(r - 1, 1)}"

    # ---- Page Quality ------------------------------------------------------------------------
    pq = wb.create_sheet("Page Quality", 2)
    headers = [("Source File", 22), ("Page", 7), ("Scan dpi", 9), ("OCR dpi", 9), ("Turned (deg)", 10), ("Skew fixed (deg)", 11),
               ("Text Lines", 9), ("Mean OCR Conf.", 11), ("Lines Needing Review", 12), ("Quality", 10), ("Notes", 60)]
    for c, (h, wdt) in enumerate(headers, 1):
        cell = _put(pq, 1, c, h)
        cell.font, cell.fill = _HEADER_FONT, _HEADER_FILL
        pq.column_dimensions[get_column_letter(c)].width = wdt
    r = 2
    for doc, _items in runs:
        for p in doc.pages:
            share_low = p.low_conf_lines / max(p.n_lines, 1)
            grade = "Good" if p.mean_conf >= 0.95 and share_low <= 0.05 else ("Fair" if p.mean_conf >= 0.88 and share_low <= 0.2 else "Poor")
            failed = any(str(n).startswith("FAILED") for n in p.notes)
            if failed:
                grade = "FAILED"                  # the page could not be read: check it by hand
            elif p.n_lines == 0:
                grade = "No text"
            vals = [Path(doc.source).name, p.number, p.source_dpi or None, p.dpi or None, p.rotation, p.skew, p.n_lines,
                    None if failed else p.mean_conf, p.low_conf_lines, grade, "; ".join(p.notes)]
            for c, v in enumerate(vals, 1):
                _put(pq, r, c, v, fill=_REVIEW_FILL if (c == 10 and grade in ("Poor", "No text", "FAILED")) else None)
            r += 1

    # ---- Run Info -------------------------------------------------------------------------
    ri = wb.create_sheet("Run Info")
    ri.column_dimensions["A"].width = 30
    ri.column_dimensions["B"].width = 110
    n_req = sum(1 for _, items in runs for it in items if it.item_type == "Requirement")
    info = [
        ("Created", _dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Tool", f"spec_extractor.py {__version__}"),
        ("Engine", runs[0][0].engine if runs else settings.engine),
        ("Documents", "\n".join(f"{Path(d.source).name}  ({len(d.pages)} pages, {d.seconds:.0f} s)" for d, _ in runs)),
        ("Requirements", n_req),
        ("Tables", sum(1 for _, items in runs for it in items if it.item_type == "Table")),
        ("Captions", sum(1 for _, items in runs for it in items if "Caption" in it.item_type)),
        ("Items needing review", sum(1 for _, items in runs for it in items if it.needs_review)),
        ("Requirement keywords", ", ".join(f"{k} = {v}" for k, v in settings.keywords.items())),
        ("List handling", "one row per list item (stem + item)" if settings.split_list_items else "one row per stem with all items"),
        ("Review threshold", f"OCR confidence below {settings.review_confidence:.2f}"),
        ("Warnings", "\n".join(w for d, _ in runs for w in d.warnings) or "none"),
        ("", ""),
        ("HOW TO USE THIS WORKBOOK", "1) Filter 'Needs Review' = Yes on 'Extracted Items' and compare those rows with the scan "
                                     "(page numbers are given).\n2) Use the Word verification report to check whole pages quickly.\n"
                                     "3) 'Full Text' lists every text block the OCR found, in reading order, and which item it became.\n"
                                     "4) 'Page Quality' shows pages with poor scan quality."),
    ] + [(f"Column: {name}", desc) for name, _w, desc in MASTER_COLUMNS]
    for r, (k, v) in enumerate(info, 1):
        _put(ri, r, 1, k, bold=True)
        _put(ri, r, 2, v)
    return _save_workbook(wb, path)


def _save_workbook(wb, path: Path) -> Path:
    try:
        wb.save(path)
        return path
    except PermissionError:
        alt = path.with_name(f"{path.stem}_{_dt.datetime.now():%H%M%S}{path.suffix}")
        LOG.warning("%s is open in another program - saved as %s instead", path.name, alt.name)
        wb.save(alt)
        return alt


# =============================================================================
# 11. WORD VERIFICATION REPORT
#     Page by page: the scanned page image, then everything the tool read, with
#     low-confidence words highlighted and [R-0001] tags linking to Excel rows.
# =============================================================================
def _docx_text(text: str) -> str:
    return ILLEGAL_CHARACTERS_RE.sub("", text or "")


def _shade_cell(cell, hex_fill: str):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _add_confidence_runs(paragraph, tokens: list, settings: Settings, size: float = 10.0):
    """Write words, highlighting the ones the OCR was not sure about."""
    group, group_class = [], None

    def emit():
        if not group:
            return
        run = paragraph.add_run(_docx_text(" ".join(group)) + " ")
        run.font.size = Pt(size)
        if group_class == "low":
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        elif group_class == "very_low":
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
            run.bold = True

    for token in tokens:
        text = token[0]
        level = token_attention(token, settings)
        cls = "very_low" if level == "likely_wrong" else ("low" if level == "check" else "ok")
        if cls != group_class:
            emit()
            group, group_class = [], cls
        group.append(text)
    emit()


def _cell_attention(t: "TableData", r: int, c: int, ctx: "TextContext", settings: Settings) -> bool:
    words = _cell_words(t, r, c)
    if not words:
        text = t.grid[r][c] if r < len(t.grid) and c < len(t.grid[r]) else ""
        conf = t.conf[r][c] if r < len(t.conf) and c < len(t.conf[r]) else 1.0
        words = [[w, conf] for w in text.split()]
    tokens = word_tokens((Word(w, cf, (0, 0, 0, 0)) for w, cf in words), ctx)
    return any(token_attention(tok, settings) for tok in tokens)


def write_word_report(path: Path, doc: DocResult, items: list, settings: Settings) -> Path:
    d = docx.Document()
    sec = d.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.7)
    sec.top_margin = sec.bottom_margin = Inches(0.6)
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10)
    usable_w, usable_h = 8.5 - 1.4, 11 - 1.2 - 0.6

    tags = defaultdict(list)
    for it in items:
        for uid in it.block_uids:
            tags[uid].append(it.item_id)
    vocab = document_text_context(doc, settings)

    d.add_heading("Extraction Verification Report", 0)
    p = d.add_paragraph()
    p.add_run("Source: ").bold = True
    p.add_run(_docx_text(Path(doc.source).name))
    p.add_run(f"\nPages: {len(doc.pages)}    Engine: {doc.engine}    Created: {_dt.datetime.now():%Y-%m-%d %H:%M}")
    n_req = sum(1 for it in items if it.item_type == "Requirement")
    p.add_run(f"\nRequirements: {n_req}    Tables: {sum(1 for it in items if it.item_type == 'Table')}    "
              f"Captions: {sum(1 for it in items if 'Caption' in it.item_type)}    "
              f"Items needing review: {sum(1 for it in items if it.needs_review)}")
    d.add_heading("How to read this report", 2)
    legend = d.add_paragraph()
    r = legend.add_run("highlighted words")
    r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    legend.add_run(" = check against the scan: the word failed a check (not in the dictionary, accent marks, "
                   f"stray punctuation, a near-duplicate ID) or is a number read with OCR confidence below "
                   f"{settings.review_confidence:.2f};  ")
    r = legend.add_run("red bold words")
    r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    r.font.color.rgb = RGBColor(0xC0, 0, 0)
    r.bold = True
    legend.add_run(" = very low OCR confidence (likely misread);  ")
    r = legend.add_run("[R-0001]")
    r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x9A)
    r.bold = True
    legend.add_run(" = the row ID in the Excel workbook that this text became;  grey italic text = page header/footer.")
    d.add_paragraph("Suggested check: compare each page image with the text below it. Every sentence with a "
                    "requirement keyword should carry an [R-...] tag; tables should match cell by cell.")

    blocks_by_page = defaultdict(list)
    for b in doc.blocks:
        blocks_by_page[b.page].append(b)
    furniture_rank = {"page_header": 0, "page_footer": 2}      # running header first, footer last on each page
    for page_blocks in blocks_by_page.values():
        page_blocks.sort(key=lambda blk: furniture_rank.get(blk.kind, 1))     # (stable: reading order is kept)
    cache_dir = Path(doc.cache_dir) if doc.cache_dir else None

    for page in doc.pages:
        d.add_page_break()
        d.add_heading(f"Page {page.number}", 1)
        if page.notes:
            note = d.add_paragraph()
            run = note.add_run("Notes: " + "; ".join(page.notes))
            run.italic, run.font.size = True, Pt(8.5)
        if page.notes and any(n.startswith("FAILED") for n in page.notes):
            d.add_paragraph("This page could not be read - check the scan manually.")
        if settings.word_page_images and page.image_file and cache_dir and (cache_dir / page.image_file).exists():
            aspect = page.height / max(page.width, 1)
            width = min(usable_w, (usable_h - 0.6) / aspect)
            d.add_picture(str(cache_dir / page.image_file), width=Inches(width))
            d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            d.add_page_break()
            d.add_heading(f"Page {page.number} - text read by the tool", 2)
        for b in blocks_by_page.get(page.number, []):
            tag_text = ("  [" + ", ".join(tags[b.uid]) + "]") if tags.get(b.uid) else ""
            if b.kind == "heading":
                level = min(4, 1 + int(b.meta.get("level", 1)))
                d.add_heading(_docx_text(b.text), level)
            elif b.kind in ("page_header", "page_footer"):
                para = d.add_paragraph()
                run = para.add_run(("[header] " if b.kind == "page_header" else "[footer] ") + _docx_text(b.text))
                run.italic, run.font.size = True, Pt(8)
                run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
                if tag_text:                      # a repeated notice that was reported as a requirement
                    tr = para.add_run(tag_text)
                    tr.bold, tr.font.size = True, Pt(8)
                    tr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x9A)
            elif b.kind == "table" and b.table is not None:
                t = b.table
                if b.meta.get("caption") and not any(x.kind == "caption" and x.meta.get("caption_of") == b.uid for x in blocks_by_page[page.number]):
                    cap = d.add_paragraph()
                    cr = cap.add_run(_docx_text(b.meta["caption"]))
                    cr.italic = True
                tbl = d.add_table(rows=t.n_rows, cols=t.n_cols)
                tbl.style = "Table Grid"
                tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                hidden = set()
                table_rows = list(tbl.rows)       # (Table.cell() re-reads the whole table on every call: slow)
                for r0, c0, r1, c1 in t.merges:
                    if r1 < t.n_rows and c1 < t.n_cols and (r1 > r0 or c1 > c0):
                        try:
                            table_rows[r0].cells[c0].merge(table_rows[r1].cells[c1])
                        except Exception:
                            continue
                        hidden |= {(rr, cc) for rr in range(r0, r1 + 1) for cc in range(c0, c1 + 1)} - {(r0, c0)}
                grid_cells = tbl._cells           # one cell object per grid position, read once
                for r_i, row in enumerate(t.grid):
                    for c_i in range(t.n_cols):
                        if (r_i, c_i) in hidden:
                            continue
                        cell = grid_cells[r_i * t.n_cols + c_i]
                        cell.text = ""
                        run = cell.paragraphs[0].add_run(_docx_text(row[c_i] if c_i < len(row) else ""))
                        run.font.size = Pt(8.5)
                        if r_i < t.header_rows:
                            run.bold = True
                            _shade_cell(cell, "D9E2F3")
                        elif _cell_attention(t, r_i, c_i, vocab, settings):
                            _shade_cell(cell, "FFF2CC")
                if tag_text:
                    tp = d.add_paragraph()
                    tr = tp.add_run(tag_text.strip())
                    tr.bold, tr.font.size = True, Pt(8)
                    tr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x9A)
            elif b.kind == "figure":
                img_file = b.meta.get("image_file")
                if img_file and cache_dir and (cache_dir / img_file).exists():
                    fw = max(1, b.box[2] - b.box[0]) / max(page.dpi, 1)
                    d.add_picture(str(cache_dir / img_file), width=Inches(min(usable_w, max(1.5, fw))))
                    d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    d.add_paragraph("[figure]")
                if b.lines:
                    fp = d.add_paragraph()
                    run = fp.add_run("Text inside figure: ")
                    run.italic, run.font.size = True, Pt(8.5)
                    _add_confidence_runs(fp, word_tokens((w for ln in b.lines for w in ln.words), vocab), settings, 8.5)
            else:
                para = d.add_paragraph()
                if b.kind == "list_item":
                    para.paragraph_format.left_indent = Inches(0.35)
                if b.kind == "caption":
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                tokens = block_tokens(b, vocab) if b.lines else [(w, 1.0, "") for w in b.text.split()]
                _add_confidence_runs(para, tokens, settings)
                if b.kind == "caption":
                    for run in para.runs:
                        run.italic = True
                if b.meta.get("continued_across_pages"):
                    cr = para.add_run(" [continues across pages]")
                    cr.italic, cr.font.size = True, Pt(8)
                if tag_text:
                    tr = para.add_run(tag_text)
                    tr.bold, tr.font.size = True, Pt(8)
                    tr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x9A)
    try:
        d.save(path)
        return path
    except PermissionError:
        alt = path.with_name(f"{path.stem}_{_dt.datetime.now():%H%M%S}{path.suffix}")
        LOG.warning("%s is open in another program - saved as %s instead", path.name, alt.name)
        d.save(alt)
        return alt


# =============================================================================
# 12. BATCH RUNNER, CACHING AND COMMAND LINE
# =============================================================================
def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _imwrite(path: Path, img: "np.ndarray", params: Optional[list] = None) -> bool:
    """cv2.imwrite cannot write to non-ASCII paths on Windows; encode in memory, then write the bytes.
    Returns False (with a warning) instead of stopping when the file cannot be written."""
    try:
        ok, buf = cv2.imencode(Path(path).suffix or ".png", img, params or [])
        if ok:
            buf.tofile(str(path))
        return bool(ok)
    except (OSError, cv2.error) as exc:
        LOG.warning("  could not write %s (%s)", Path(path).name, exc)
        return False


def _imread_gray(path: Path) -> "np.ndarray":
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)


def _save_jpeg(gray: "np.ndarray", path: Path, scale: float, quality: int = 70) -> bool:
    img = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    return _imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, quality])


class SpecExtractor:
    """Runs the whole pipeline for one file at a time; OCR models are loaded once."""

    def __init__(self, settings: Settings):
        self.settings = settings
        configure_keywords(settings.keywords)
        self._ocr = None
        self._orientation = None
        self._docling = None

    @property
    def ocr(self) -> RapidOcrEngine:
        if self._ocr is None:
            LOG.info("Loading OCR model (PP-OCRv6 via RapidOCR)...")
            self._ocr = RapidOcrEngine(self.settings)
        return self._ocr

    @property
    def orientation(self) -> OrientationDetector:
        if self._orientation is None:
            self._orientation = OrientationDetector()
        return self._orientation

    def process_file(self, path: Path, out_dir: Path, output_stem: str) -> tuple:
        s = self.settings
        start = time.time()
        page_key = hashlib.sha1(s.page_selection.encode()).hexdigest()[:6] if s.page_selection else "all"
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem)[:40]
        cache_dir = out_dir / "_cache" / f"{safe_stem}_{_file_sha256(path)[:12]}_{s.ocr_fingerprint()}_{page_key}"
        result_file = cache_dir / "result.json"
        doc = None
        if s.use_cache and result_file.exists():
            try:
                doc = DocResult.from_json(json.loads(result_file.read_text(encoding="utf-8")))
                doc.cache_dir = str(cache_dir)
                doc.source = str(path)            # the same file may have been moved, renamed or copied
                LOG.info("  using cached OCR results (delete the _cache folder or use --no-cache to re-read)")
            except Exception as exc:
                LOG.warning("  cache unreadable (%s) - reading the document again", exc)
                doc = None
        if doc is None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            doc = self._read_document(path, cache_dir)
            failed = [p.number for p in doc.pages if any(str(n).startswith("FAILED") for n in p.notes)
                      or (p.width and not p.image_file)]            # a page or its report image could not be saved
            if failed:
                LOG.info("  results not cached because page(s) %s were not completely read or saved - the next run "
                         "tries again", _pages_text(failed))
            elif doc.engine == s.engine or not doc.engine.startswith("standard ("):
                try:                                 # (a Docling fallback run is not cached as a Docling result)
                    tmp = result_file.with_suffix(".tmp")
                    tmp.write_text(json.dumps(doc.to_json(), ensure_ascii=False), encoding="utf-8")
                    os.replace(tmp, result_file)
                except OSError as exc:
                    LOG.warning("  could not save the OCR cache (%s) - the results are still written", exc)
        finalize_document(doc, s)
        items = RequirementExtractor(s).extract(doc)
        outputs = {}
        if s.make_excel:
            outputs["excel"] = write_workbook(out_dir / f"{output_stem}_extracted.xlsx", [(doc, items)], s)
        if s.make_word_report:
            outputs["word"] = write_word_report(out_dir / f"{output_stem}_verification.docx", doc, items, s)
        failed_pages = [p.number for p in doc.pages if any(str(n).startswith("FAILED") for n in p.notes)]
        LOG.info("  done in %.0f s: %d requirements, %d tables, %d captions, %d items flagged for review%s",
                 time.time() - start, sum(1 for i in items if i.item_type == "Requirement"),
                 sum(1 for i in items if i.item_type == "Table"), sum(1 for i in items if "Caption" in i.item_type),
                 sum(1 for i in items if i.needs_review),
                 f" - {len(failed_pages)} page(s) could NOT be read: {_pages_text(failed_pages)} (see Page Quality)"
                 if failed_pages else "")
        return doc, items, outputs

    def _read_document(self, path: Path, cache_dir: Path) -> DocResult:
        s = self.settings
        doc = DocResult(source=str(path), engine=s.engine, cache_dir=str(cache_dir))
        t0 = time.time()
        total = len(parse_page_selection(s.page_selection, count_pages(path)))
        if total == 0:
            doc.warnings.append(f"{path.name}: no pages selected")
            LOG.warning("  no pages selected (--pages %s, the file has %d page(s))", s.page_selection, count_pages(path))
            return doc
        docling_pages = []     # (page number, dpi, height, width, cleaned image file) - images stay on disk
        for n, raw in enumerate(iter_raw_pages(path, s), 1):
            page_start = time.time()
            if raw.error:
                self._page_failed(doc, raw.number, raw.error)
                continue
            try:
                prep = prepare_page(raw, s, self.orientation, self.ocr)
                h, w = prep.ocr_image.shape[:2]
                info = PageInfo(number=raw.number, width=int(w), height=int(h), source_dpi=round(float(raw.dpi), 1),
                                dpi=round(float(prep.dpi), 1), rotation=prep.rotation, skew=prep.skew, notes=list(prep.notes))
                # page image for the Word report (always cached, so later runs can include it)
                info.image_file = f"page_{raw.number:04d}.jpg"
                if not _save_jpeg(prep.view_image, cache_dir / info.image_file, min(1.0, s.word_image_dpi / max(prep.dpi, 1))):
                    info.image_file = ""
                if s.save_debug_images:
                    _imwrite(cache_dir / f"page_{raw.number:04d}_cleaned.png", prep.ocr_image)
                if s.engine == "docling":
                    ocr_file = cache_dir / f"page_{raw.number:04d}_docling.jpg"
                    if not _imwrite(ocr_file, prep.ocr_image, [cv2.IMWRITE_JPEG_QUALITY, 92]):
                        raise OSError(f"could not write the temporary page image {ocr_file.name}")
                    docling_pages.append((raw.number, float(prep.dpi), int(h), int(w), ocr_file))
                    doc.pages.append(info)
                    continue
                lines = self.ocr.read(prep.ocr_image)
                blocks = analyze_page(raw.number, prep, lines, s)
                self._save_figure_images(blocks, prep.view_image, prep.dpi, cache_dir)
            except Exception as exc:
                LOG.debug(traceback.format_exc())
                self._page_failed(doc, raw.number, f"{type(exc).__name__}: {exc}")
                continue
            doc.pages.append(info)
            doc.blocks.extend(blocks)
            eta = (time.time() - t0) / n * (total - n)
            LOG.info("  page %d (%d of %d): %d text lines, %d tables, %d figures  [%.1f s; about %s left]",
                     raw.number, n, total, len(lines), sum(1 for b in blocks if b.kind == "table"),
                     sum(1 for b in blocks if b.kind == "figure"), time.time() - page_start, _human_time(eta))
        if s.engine == "docling" and docling_pages:
            try:
                if self._docling is None:
                    LOG.info("Loading Docling models (first use downloads them - this can take a while)...")
                    self._docling = DoclingEngine(s)
                blocks, _scores = self._docling.convert(docling_pages, cache_dir)
                for number, dpi, _h, _w, image_file in docling_pages:
                    img = _imread_gray(image_file)
                    self._save_figure_images([b for b in blocks if b.page == number], img, dpi, cache_dir)
                doc.blocks = blocks
            except Exception as exc:              # missing models, no network, or any Docling error
                LOG.debug(traceback.format_exc())
                msg = f"Docling engine could not run - used the standard engine instead. {exc}"
                LOG.warning("  %s", msg)
                doc.warnings.append(msg)
                doc.engine = "standard (Docling unavailable)"
                s.engine = "standard"           # do not retry Docling for the remaining files
                for number, dpi, _h, _w, image_file in docling_pages:
                    try:
                        img = _imread_gray(image_file)
                        prep = PreparedPage(img, img, dpi)
                        lines = self.ocr.read(img)
                        blocks = analyze_page(number, prep, lines, s)
                        self._save_figure_images(blocks, img, dpi, cache_dir)
                        doc.blocks.extend(blocks)
                        LOG.info("  page %d: %d text lines (standard engine)", number, len(lines))
                    except Exception as page_exc:
                        self._page_failed(doc, number, f"{type(page_exc).__name__}: {page_exc}", keep_info=True)
        doc.seconds = round(time.time() - t0, 1)
        return doc

    @staticmethod
    def _page_failed(doc: DocResult, number: int, reason: str, keep_info: bool = False):
        msg = f"page {number} FAILED and was skipped: {reason}"
        LOG.error("  %s", msg)
        doc.warnings.append(msg)
        existing = next((p for p in doc.pages if p.number == number), None) if keep_info else None
        if existing is not None:
            existing.notes.append(f"FAILED: {reason}")
        else:
            doc.pages.append(PageInfo(number=number, width=0, height=0, source_dpi=0.0, dpi=0.0,
                                      notes=[f"FAILED: {reason}"]))

    @staticmethod
    def _save_figure_images(blocks: list, image: "np.ndarray", dpi: float, cache_dir: Path):
        for k, b in enumerate(b for b in blocks if b.kind == "figure"):
            x0, y0, x1, y1 = b.box
            pad = int(0.05 * dpi)
            h, w = image.shape[:2]
            crop = image[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)]
            if crop.size:
                name = f"figure_p{b.page:04d}_{k + 1}.png"
                if _imwrite(cache_dir / name, crop):
                    b.meta["image_file"] = name


def _human_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {(seconds % 3600) // 60} min"


def collect_input_files(inputs: list, recursive: bool) -> list:
    files = []
    for item in inputs:
        p = Path(item).expanduser()
        if p.is_dir():
            pattern = "**/*" if recursive else "*"
            files += sorted(f for f in p.glob(pattern) if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
                            and "_cache" not in f.parts and not f.name.startswith("~$"))
        elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(p)
        elif p.exists():
            LOG.warning("Skipping %s (supported types: %s)", p.name, ", ".join(sorted(SUPPORTED_EXTENSIONS)))
        else:
            LOG.warning("Not found: %s", p)
    unique, seen = [], set()
    for f in files:
        key = str(f.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def unique_output_stems(files: list) -> dict:
    """File -> name used for its outputs (<name>_extracted.xlsx). Names never collide, so one run cannot
    overwrite its own results: 'spec.pdf' + 'spec.tif' -> spec_pdf / spec_tif, and the same name in two
    folders gets the folder name in front (B_spec_pdf), then a counter if that is still not unique."""
    stems = Counter(f.stem.lower() for f in files)
    output_stems, used = {}, set()
    for f in files:
        stem = f.stem if stems[f.stem.lower()] == 1 else f"{f.stem}_{f.suffix.lstrip('.').lower()}"
        candidate = stem if stem.lower() not in used else f"{f.parent.name}_{stem}"
        k = 2
        while candidate.lower() in used:
            candidate = f"{stem}_{k}"
            k += 1
        used.add(candidate.lower())
        output_stems[f] = candidate
    return output_stems


def _pick_inputs_with_dialog() -> list:
    """File picker for people who double-click the script instead of using a terminal."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        files = filedialog.askopenfilenames(
            title="Choose scanned PDF/TIFF files  (press Cancel to choose a whole folder instead)",
            filetypes=[("Scanned documents", "*.pdf *.tif *.tiff *.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if files:
            root.destroy()
            return [Path(f) for f in files]
        folder = filedialog.askdirectory(title="Choose a folder of scanned documents")
        root.destroy()
        return [Path(folder)] if folder else []
    except Exception:
        return []


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spec_extractor.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Extract requirements, tables and captions from scanned PDF/TIFF documents into Excel, "
                    "with a Word report for checking the OCR.",
        epilog="examples:\n"
               "  python spec_extractor.py C:\\Scans\\spec.pdf\n"
               "  python spec_extractor.py C:\\Scans -r -o C:\\Results\n"
               "  python spec_extractor.py spec.tif --pages 1-10 --keywords shall,must\n"
               "  python spec_extractor.py spec.pdf --engine docling --docling-models D:\\docling_models\n")
    p.add_argument("inputs", nargs="*", help="PDF/TIFF/PNG/JPG files and/or folders (omit to open a file picker)")
    g = p.add_argument_group("input / output")
    g.add_argument("-o", "--output", help="output folder (default: 'extraction_output' next to the input)")
    g.add_argument("-r", "--recursive", action="store_true", help="also process files in sub-folders")
    g.add_argument("--pages", default="", help="pages to process, e.g. 1-5,9 (default: all)")
    g.add_argument("--no-word", action="store_true", help="do not write the Word verification report")
    g.add_argument("--no-page-images", action="store_true", help="leave page images out of the Word report (smaller file)")
    g.add_argument("--no-combined", action="store_true", help="no ALL_DOCUMENTS workbook for multi-file runs")
    g.add_argument("--no-cache", action="store_true", help="always re-run OCR (ignore cached results)")
    g.add_argument("--debug-images", action="store_true", help="save the cleaned page images in the _cache folder")
    g = p.add_argument_group("requirements")
    g.add_argument("--keywords", help="comma-separated requirement keywords (default: shall,must,is required to,"
                                      "are required to,should,will)")
    g.add_argument("--no-will", action="store_true", help='do not report "will" statements')
    g.add_argument("--no-should", action="store_true", help='do not report "should" statements')
    g.add_argument("--keep-list-stems", action="store_true", help="one row per stem with all its list items")
    g.add_argument("--no-keyword-repair", action="store_true", help="do not repair OCR-garbled keywords such as 'sha11'")
    g.add_argument("--no-quality-notes", action="store_true", help="skip INCOSE-style writing checks")
    g = p.add_argument_group("OCR and image clean-up")
    g.add_argument("--engine", choices=["standard", "docling"], default="standard",
                   help="standard = pip-only (default); docling = adds IBM Docling layout/table AI models")
    g.add_argument("--dpi", type=int, help="working resolution for OCR (default 220)")
    g.add_argument("--review-threshold", type=float, help="flag numbers read below this OCR confidence (default 0.70)")
    g.add_argument("--min-confidence", type=float, help="drop OCR text below this confidence as noise (default 0.30)")
    g.add_argument("--no-rotate", action="store_true", help="do not auto-rotate sideways/upside-down pages")
    g.add_argument("--no-deskew", action="store_true", help="do not straighten skewed scans")
    g.add_argument("--no-clean", action="store_true", help="no background flattening / denoising")
    g.add_argument("--remove-color-marks", action="store_true", help="fade colored stamps, pen marks and highlighter")
    g.add_argument("--no-borderless-tables", action="store_true", help="only detect tables that have ruling lines")
    g.add_argument("--threads", type=int, default=0, help="CPU threads for OCR (default: automatic)")
    g.add_argument("--docling-models", help="folder with pre-downloaded Docling models (offline use)")
    g.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], default="auto", help="device for the Docling engine")
    p.add_argument("-v", "--verbose", action="store_true", help="more detailed log")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


KEYWORD_CLASSES = {"shall": "Mandatory", "must": "Mandatory", "is required to": "Mandatory", "are required to": "Mandatory",
                   "required": "Mandatory", "should": "Goal / recommended", "will": "Statement of intent",
                   "may": "Permissive / optional", "can": "Permissive / optional"}


def settings_from_args(args) -> Settings:
    s = Settings()
    if args.output:
        s.output_dir = Path(args.output)
    s.recursive = args.recursive
    s.page_selection = args.pages or ""
    s.make_word_report = not args.no_word
    s.word_page_images = not args.no_page_images
    s.combined_workbook = not args.no_combined
    s.use_cache = not args.no_cache
    s.save_debug_images = args.debug_images
    if args.keywords:
        words = [" ".join(k.strip().lower().split()) for k in re.split(r"[,;|]", args.keywords) if k.strip()]
        s.keywords = {k: KEYWORD_CLASSES.get(k, "Custom keyword") for k in words}
    if args.no_will:
        s.keywords.pop("will", None)
    if args.no_should:
        s.keywords.pop("should", None)
    if not s.keywords:
        raise SystemExit("No requirement keywords left - check --keywords / --no-will / --no-should.")
    s.split_list_items = not args.keep_list_stems
    s.fix_ocr_keywords = not args.no_keyword_repair
    s.quality_checks = not args.no_quality_notes
    s.engine = args.engine
    if args.dpi:
        s.target_dpi = int(np.clip(args.dpi, 120, 400))
    if args.review_threshold is not None:
        s.review_confidence = float(np.clip(args.review_threshold, 0.0, 1.0))
    if args.min_confidence is not None:
        s.min_text_confidence = float(np.clip(args.min_confidence, 0.0, 0.95))
    s.auto_rotate = not args.no_rotate
    s.deskew = not args.no_deskew
    s.clean_background = s.denoise = not args.no_clean
    s.remove_color_marks = args.remove_color_marks
    s.borderless_tables = not args.no_borderless_tables
    s.ocr_threads = max(0, args.threads or 0)
    if args.docling_models:
        s.docling_models_dir = Path(args.docling_models)
    s.docling_device = args.device
    return s


def _setup_logging(out_dir: Optional[Path], verbose: bool):
    # Windows consoles/pipes may not be able to print every character of a file name: never crash on it
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(console)
    if out_dir is not None:
        fh = logging.FileHandler(out_dir / "spec_extractor_log.txt", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root.addHandler(fh)
    _quiet_third_party_loggers()


def main(argv: Optional[list] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    used_dialog = False
    inputs = args.inputs
    if not inputs:
        inputs = _pick_inputs_with_dialog()
        used_dialog = bool(inputs)
        if not inputs:
            build_arg_parser().print_help()
            return 1
    settings = settings_from_args(args)
    _setup_logging(None, args.verbose)
    try:
        parse_page_selection(settings.page_selection, 10 ** 6)
    except ValueError as exc:
        LOG.error("--pages: %s", exc)
        return 2
    configure_keywords(settings.keywords)
    files = collect_input_files(inputs, settings.recursive)
    if not files:
        LOG.error("No PDF/TIFF/image files found in: %s", ", ".join(map(str, inputs)))
        return 1
    first = Path(inputs[0]).expanduser()
    out_dir = settings.output_dir or ((first if first.is_dir() else first.parent) / "extraction_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(out_dir, args.verbose)
    LOG.info("spec_extractor %s - %d file(s) - engine: %s - output: %s", __version__, len(files), settings.engine, out_dir)

    output_stems = unique_output_stems(files)
    extractor = SpecExtractor(settings)
    runs, failures = [], []
    for n, f in enumerate(files, 1):
        stem = output_stems[f]
        LOG.info("")
        LOG.info("[%d/%d] %s", n, len(files), f.name if stem == f.stem else f"{f.name}   (from {f.parent} -> {stem}_...)")
        try:
            doc, items, outputs = extractor.process_file(f, out_dir, stem)
            runs.append((doc, items))
            for kind, pth in outputs.items():
                LOG.info("  %-5s -> %s", kind, pth)
        except EngineUnavailable as exc:
            LOG.error("  %s", exc)
            return 3
        except KeyboardInterrupt:
            LOG.error("Stopped by user.")
            return 130
        except Exception as exc:
            reason = str(exc)
            if "password" in reason.lower():
                reason = "the PDF is password-protected - save an unprotected copy and run again"
            elif "format error" in reason.lower() or "cannot identify image file" in reason.lower():
                reason = "the file is damaged or is not really a PDF/TIFF/image"
            LOG.error("  FAILED: %s (details in spec_extractor_log.txt)", reason)
            LOG.debug(traceback.format_exc())
            failures.append((f.name, reason))

    if settings.combined_workbook and len(runs) > 1 and settings.make_excel:
        combined = write_workbook(out_dir / f"ALL_DOCUMENTS_{_dt.datetime.now():%Y%m%d_%H%M}.xlsx", runs, settings, multi_doc=True)
        LOG.info("")
        LOG.info("Combined workbook -> %s", combined)
    LOG.info("")
    LOG.info("Finished: %d document(s) processed, %d failed.", len(runs), len(failures))
    for name, err in failures:
        LOG.info("  failed: %s - %s", name, err)
    if used_dialog and sys.stdin and sys.stdin.isatty() and not os.environ.get("SPEC_EXTRACTOR_LAUNCHER"):
        try:
            input("\nPress Enter to close this window...")
        except EOFError:
            pass
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
