"""
casekit.py - the machinery behind the test-case library in this folder.

A CASE is one small specification situation - "a list on tab stops whose values start with numbers",
"a NOTE between two list items", "a short list beside a column of prose" - drawn as a page of its own and
saved as a PDF document (a synthetic scan), together with the rows the tool must produce for it. Every case
has a fixed ID ("TAB-01", "LST-07") so a situation can be named in a discussion, a bug report or a commit.

    area_*.py        the cases themselves, one file per area (tab lists, list markers, lead-ins, ...)
    casekit.py       this file: how a case is written, drawn and turned into a document
    build_cases.py   writes the documents (documents/<ID>_<name>.pdf) and the catalog (CASEBOOK.pdf)
    run_cases.py     runs spec_extractor.py on every document and checks its output against each case

HOW A PAGE IS WRITTEN. Most cases give the page as plain text, typed the way it looks:

    3.2.4 Environmental conditions. The equipment shall meet each of the following:

         a.     Acceleration:      5 g in each of the three orthogonal axes
                                   for 1 minute per axis.

  * Every line is one printed line (1 inch margins, 11 pt, 0.19 inch line pitch).
  * Text is split where two or more spaces follow each other: each piece is drawn at the column where it
    starts in the text (one column = the width of one typewriter character, 0.092 inch). So the wide tabs of
    a list are written as runs of spaces, exactly where they are on the page. Single spaces are ordinary
    word spaces.
  * An empty line is a blank line.
  * <u>...</u> underlines text and <b>...</b> prints it in bold, as a typewriter or word processor would:
        3.2.1  <u>Power input.</u>  The equipment shall operate from 115 V ac.
    The tags take up no room: columns are counted on the text without them.
Lines that start with '@' are drawing instructions, not text:
    @gap 0.5                    a gap of half a line (any number of lines; '~' alone is short for @gap 0.5)
    @y 9.4                      continue 9.4 inches from the top of the page (to reach the foot of a page)
    @wrap 0: text ...           a paragraph, wrapped to the right margin, starting at column 0
    @wrap 5/0: text ...         the same with its first line indented to column 5 and the rest at column 0
    @wrap 0 to 38: text ...     the same, wrapped at column 38 (the right edge of a left-hand column)
    @mark top  /  @goto top     remember the current height / go back to it (to write a second column)
    @rule 0.5 5.5               a ruled line across the page from 0.5 to 5.5 inches, at the current height
                                (@rule 0.5 5.5 1: one line further down), for tables with rulings
    @vrule 2.0 4                a vertical rule at 2.0 inches, from the current height 4 lines down
    @box 0.5 5.5 4              a ruled box from 0.5 to 5.5 inches, from the current height 4 lines down
    @page                       start a new page ('=== page ===' works too)
'@wrap' is what makes proportional (serif) text realistic: lines are broken where the next word no longer
fits, as a typesetter would, instead of where they were broken in the source.

Cases can instead draw their page with a function (draw=...), using the same Sheet methods - the lists
from the earlier 'list suite' are kept that way, exactly as they were drawn before.

WHAT THE TOOL MUST PRODUCE is given with para(...) and items(...):
    para("3.2.5 | The equipment shall not exceed 45 kilograms.")
    items("The equipment shall meet each of the following:",
          "3.2.4 a | a. Acceleration: 5 g in each of the three orthogonal axes for 1 minute per axis.")
One string per 'Requirement' row of the Extracted Items sheet: '<Doc Ref> | <Content>'. items() puts its
stem (the lead-in sentence) in front of each item, as the tool does. A row may end with checks in brackets:
    [note: List marker missing]   its Review Reasons must contain this text
    [no marker note]              its Review Reasons must say nothing about list markers
    [section: 4 Verification]     its Section column must be exactly this ('' = empty)
    [pages: 1-2]                  its Page(s) column must be exactly this
    [title: Power input]          its Title column (the paragraph's run-in title) must be exactly this
    [corrected: requ1red]         its OCR Corrections column must contain this text
    [quality: section 6]          its Quality Notes column must contain this text
A case can also check the document's structure and its list of documents (see Case):
    outline=("1 | 3 REQUIREMENTS", "2 | 3.1 General", ...)     the headings of the Document Structure sheet, in
                                                                order: level, then paragraph number and title
    documents=("MIL-STD-461G | Requirements for ... | 3.2.5", ...)   the Applicable Documents sheet, in order:
                                                                document, title, referencing paragraphs

YOUR OWN SCANS AS CASES (kept on this computer only): put a scan in tests/cases/my_cases/ and run
    python tests/cases/run_cases.py --record tests/cases/my_cases/<file>
which writes <file>.expected.txt with what the tool produces now. Correct that file to what it SHOULD produce;
from then on the scan is checked with every run (--only MY runs only your own). See tests/README.md.
Nothing on this page reaches the network: documents are drawn with PIL and saved on this computer.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Liberation fonts (Linux) or their metric-compatible Windows equivalents. Cases are compared by the text the
# tool reads, not pixel by pixel, so either font gives the same expected rows.
_FONT_CHOICES = {"mono": ["/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", "C:/Windows/Fonts/cour.ttf"],
                 "serif": ["/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf", "C:/Windows/Fonts/times.ttf"]}
FONT_FILES = {k: next((p for p in v if Path(p).exists()), v[0]) for k, v in _FONT_CHOICES.items()}
_BOLD_CHOICES = {"mono": ["/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf", "C:/Windows/Fonts/courbd.ttf"],
                 "serif": ["/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", "C:/Windows/Fonts/timesbd.ttf"]}
BOLD_FILES = {k: next((p for p in v if Path(p).exists()), v[0]) for k, v in _BOLD_CHOICES.items()}
_TAG = re.compile(r"</?[bu]>")


def _formatted(text: str, state: tuple = (False, False)) -> tuple:
    """'<u>Power input.</u> The' -> ([('Power input.', False, True), (' The', False, False)], state at the end):
    runs of (text, bold, underline). `state` is (bold, underline) at the start - a tag may stay open over a line."""
    bold, underline = state
    runs, pos = [], 0
    for m in _TAG.finditer(text):
        if m.start() > pos:
            runs.append((text[pos:m.start()], bold, underline))
        tag = m.group(0)
        if tag in ("<b>", "</b>"):
            bold = tag == "<b>"
        else:
            underline = tag == "<u>"
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], bold, underline))
    return runs, (bold, underline)


def plain(text: str) -> str:
    """The text without its <b>/<u> tags."""
    return _TAG.sub("", text)


def _pieces(line: str) -> list:
    """[(column, tagged text)] - a typed line split where two or more spaces follow each other, each piece at the
    column where it starts on the line WITHOUT its tags, with the tags that apply to it."""
    chars, state = [], (False, False)
    for text, bold, underline in _formatted(line)[0]:
        chars += [(ch, bold, underline) for ch in text]
    visible = "".join(ch for ch, _b, _u in chars)
    out = []
    for m in re.finditer(r"\S+(?: \S+)*", visible):
        tagged, cur = "", (False, False)
        for ch, bold, underline in chars[m.start():m.end()]:
            if (bold, underline) != cur:
                tagged += ("</b>" if cur[0] and not bold else "") + ("</u>" if cur[1] and not underline else "")
                tagged += ("<b>" if bold and not cur[0] else "") + ("<u>" if underline and not cur[1] else "")
                cur = (bold, underline)
            tagged += ch
        tagged += ("</b>" if cur[0] else "") + ("</u>" if cur[1] else "")
        out.append((m.start(), tagged))
    return out


def _balanced(lines: list) -> list:
    """Wrapped lines of tagged text, each closing the tags it opened and reopening those still open from above."""
    out, state = [], (False, False)
    for x, text in lines:
        opening = ("<b>" if state[0] else "") + ("<u>" if state[1] else "")
        _runs, state = _formatted(text, state)
        out.append((x, opening + text + ("</b>" if state[0] else "") + ("</u>" if state[1] else "")))
    return out
BULLETS = set("•●▪■‣⁃∙·◦*-o–—")
AREAS = ["area_tab", "area_lists", "area_leadin", "area_numbering", "area_paragraphs", "area_columns",
         "area_tables", "area_pages", "area_structure"]
AREA_DOCS = {}          # area name -> the description at the top of its file (filled in by load_cases)


# =====================================================================================================================
# Drawing a page
# =====================================================================================================================
class Sheet:
    """One page being drawn. Positions are in inches from the top-left corner of the text area (1 inch margins).
    Everything drawn is also recorded - text in `pieces` (x, y in pixels, text, font, size), ruled lines in
    `rules` (x0, y0, x1, y1, width in pixels) - which the catalog uses to draw the page again in vector form."""

    def __init__(self, font: str = "mono", pt: float = 11, dpi: int = 300, pitch: float = 0.19,
                 margin: float = 1.0, top: float = 1.0):
        from PIL import Image, ImageDraw, ImageFont
        self.dpi, self.font_name, self.pt = dpi, font, pt
        self.W, self.H = int(8.5 * dpi), int(11 * dpi)
        self.font = ImageFont.truetype(FONT_FILES[font], round(pt / 72 * dpi))
        self.bold_font = ImageFont.truetype(BOLD_FILES[font], round(pt / 72 * dpi))
        self.lh = round(pitch * dpi)
        self.L = round(margin * dpi)
        self.R = self.W - self.L
        self.img = Image.new("L", (self.W, self.H), 255)
        self.d = ImageDraw.Draw(self.img)
        self.y = round(top * dpi)
        self.col = (0.0, (self.R - self.L) / dpi)          # current column: (x offset, width) in inches
        self.col_in = 0.6 * pt / 72                        # one typewriter character, for the text layouts
        self.pieces = []
        self.rules = []

    def x(self, inch: float) -> int:
        return self.L + round((self.col[0] + inch) * self.dpi)

    def width(self, s: str) -> float:
        """Printed width of a text in pixels (<b>/<u> tags take no room; bold text is a little wider)."""
        return sum((self.bold_font if bold else self.font).getlength(t) for t, bold, _u in _formatted(s)[0])

    def text(self, x_in: float, s: str):
        x = self.x(x_in)
        right = self.L + round((self.col[0] + self.col[1]) * self.dpi)
        if x + self.width(s) > right + 2:
            raise ValueError(f"text runs past the column edge by {x + self.width(s) - right:.0f} px: {s!r}")
        if self.y + self.lh > self.H - round(0.7 * self.dpi):
            raise ValueError(f"page overflow at {s!r}")
        for run, bold, underline in _formatted(s)[0]:
            font = self.bold_font if bold else self.font
            self.d.text((x, self.y), run, font=font, fill=0)
            self.pieces.append((x, self.y, run, self.font_name + ("-bold" if bold else ""), self.pt))
            w = font.getlength(run)
            if underline and run.strip():
                ascent = font.getmetrics()[0]          # an underline just below the baseline, as Word draws it
                uy = self.y + ascent + max(2, round(0.10 * font.size))
                self.line_px(round(x), uy, round(x + w), uy, max(2, round(0.06 * font.size)))
            x += w

    def newline(self, n: float = 1.0):
        self.y += round(n * self.lh)

    def line_px(self, x0: int, y0: int, x1: int, y1: int, width: int = 3):
        self.d.line((x0, y0, x1, y1), fill=0, width=width)
        self.rules.append((x0, y0, x1, y1, width))

    def rule(self, x0_in: float, x1_in: float, dy: float = 0.0, width: int = 3):
        """A ruled line from x0 to x1 inches, `dy` lines below the current height (the rulings of a table)."""
        y = self.y + round(dy * self.lh)
        self.line_px(self.x(x0_in), y, self.x(x1_in), y, width)

    def vrule(self, x_in: float, rows: float, width: int = 3):
        """A vertical rule at x inches, from the current height `rows` lines down."""
        self.line_px(self.x(x_in), self.y, self.x(x_in), self.y + round(rows * self.lh), width)

    def box(self, x0_in: float, x1_in: float, rows: float, width: int = 3):
        """A ruled box from x0 to x1 inches, from the current height `rows` lines down."""
        y1 = self.y + round(rows * self.lh)
        for a, b, c, d in ((x0_in, 0, x1_in, 0), (x0_in, rows, x1_in, rows), (x0_in, 0, x0_in, rows), (x1_in, 0, x1_in, rows)):
            self.line_px(self.x(a), self.y + round(b * self.lh), self.x(c), self.y + round(d * self.lh), width)

    def wrap(self, text: str, x_in: float = 0.0, width_in: float = None) -> list:
        avail = (width_in if width_in is not None else self.col[1] - x_in) * self.dpi
        lines, cur = [], ""
        for w in text.split():
            trial = f"{cur} {w}".strip()
            if cur and self.width(trial) > avail:
                lines.append(cur)
                cur = w
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return [ln for _x, ln in _balanced([(0, ln) for ln in lines])]

    def para(self, text: str, x_in: float = 0.0):
        for ln in self.wrap(text, x_in):
            self.text(x_in, ln)
            self.newline()


def draw_layout(text: str, new_sheet) -> list:
    """Draw a page layout written as text (see the top of this file) -> list of Sheets (one per page)."""
    sheets = [new_sheet()]
    marks = {}
    for raw in text.strip("\n").split("\n"):
        pg = sheets[-1]
        line = raw.rstrip()
        stripped = line.strip()
        if stripped == "~":
            pg.newline(0.5)
            continue
        if stripped == "@page" or re.fullmatch(r"=+\s*page\s*\d*\s*=+", stripped, re.I):
            sheets.append(new_sheet())
            continue
        if stripped.startswith("@"):
            cmd, _, arg = stripped[1:].partition(" ")
            arg = arg.strip()
            if cmd == "gap":
                pg.newline(float(arg))
            elif cmd == "y":
                pg.y = round(float(arg) * pg.dpi)
            elif cmd == "mark":
                marks[arg] = pg.y
            elif cmd == "goto":
                pg.y = marks[arg]
            elif cmd in ("rule", "vrule", "box"):
                nums = [float(v) for v in arg.split()]
                getattr(pg, cmd)(*nums)
            elif cmd.startswith("wrap"):
                spec, _, body = (cmd[4:] + " " + arg).strip().partition(":")
                m = re.fullmatch(r"\s*(\d+)(?:/(\d+))?(?:\s+to\s+(\d+))?\s*", spec)
                if not m:
                    raise ValueError(f"bad @wrap instruction: {raw!r}")
                first, rest = int(m.group(1)), int(m.group(2) if m.group(2) is not None else m.group(1))
                right = int(m.group(3)) * pg.col_in if m.group(3) else pg.col[1]
                words, x0, lines = body.split(), first * pg.col_in, []
                cur = ""
                for w in words:
                    trial = f"{cur} {w}".strip()
                    x = first * pg.col_in if not lines else rest * pg.col_in
                    if cur and pg.width(trial) > (right - x) * pg.dpi:
                        lines.append((x, cur))
                        cur = w
                    else:
                        cur = trial
                if cur:
                    lines.append((first * pg.col_in if not lines else rest * pg.col_in, cur))
                for x, ln in _balanced(lines):
                    pg.text(x, ln)
                    pg.newline()
            else:
                raise ValueError(f"unknown instruction: {raw!r}")
            continue
        if not stripped:
            pg.newline()
            continue
        for column, piece in _pieces(line):                   # pieces: split at two or more spaces
            pg.text(column * pg.col_in, piece)
        pg.newline()
    return sheets


# ---- photocopy damage (the tests/make_test_corpus.py profile, a little lighter so the words stay readable) --------
def _low_freq(shape, rng, sigma_px: float):
    import cv2
    import numpy as np
    h, w = shape
    small = rng.random((max(4, h // 16), max(4, w // 16))).astype(np.float32)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, sigma_px / 16))
    big = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    return (big - big.min()) / (np.ptp(big) + 1e-6)


def degrade(gray, p: dict, rng):
    import cv2
    import numpy as np
    ink = 255.0 - gray.astype(np.float32)
    if p.get("bleed"):
        ink = cv2.dilate(ink, np.ones((p["bleed"], p["bleed"]), np.uint8))
    if p.get("fade"):
        ink *= p["fade"] + (1 - p["fade"]) * 0.6 * _low_freq(gray.shape, rng, 300)
    paper = float(p.get("paper", 255))
    img = paper - ink * (paper / 255.0)
    if p.get("paper_noise"):
        img += (_low_freq(gray.shape, rng, 120) - 0.5) * p["paper_noise"]
    if p.get("illum"):
        h, w = img.shape
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        img *= 1.0 - p["illum"] * (0.6 * xx / w + 0.4 * yy / h)
    if p.get("skew"):
        h, w = img.shape
        m = cv2.getRotationMatrix2D((w / 2, h / 2), p["skew"], 1.0)
        img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=paper)
    if p.get("blur"):
        img = cv2.GaussianBlur(img, (0, 0), p["blur"])
    if p.get("noise"):
        img += rng.normal(0, p["noise"], img.shape).astype(np.float32)
    if p.get("speckle"):
        mask = (rng.random(img.shape) < p["speckle"]).astype(np.uint8) * 255
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
        img[mask > 0] = rng.uniform(30, 110)
    if p.get("dark_edges"):
        h, w = img.shape
        e = max(2, int(p["dark_edges"] * w))
        img[:, :e] = 25 + rng.normal(0, 8, (h, e))
        img[:, w - e // 2:] = 35 + rng.normal(0, 8, (h, e // 2))
    if p.get("punch_holes"):
        h, w = img.shape
        for fy in (0.18, 0.5, 0.82):
            cv2.circle(img, (int(0.045 * w), int(fy * h)), int(0.013 * w), 15, -1)
    img = np.clip(img, 0, 255).astype(np.uint8)
    if p.get("jpeg"):
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(p["jpeg"])])
        img = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return img


PHOTOCOPY = {"paper": 238, "paper_noise": 18, "bleed": 2, "fade": 0.6, "skew": -1.3, "blur": 0.9, "noise": 10,
             "speckle": 0.0004, "dark_edges": 0.015, "punch_holes": True, "illum": 0.10, "jpeg": 50}


# =====================================================================================================================
# What the tool must produce
# =====================================================================================================================
@dataclass
class Row:
    """One expected 'Requirement' row of the Extracted Items sheet."""
    doc_ref: str
    content: str
    stem: str = ""                    # the lead-in part of `content` (the item after it is checked on its own too)
    note: str = ""                    # text its Review Reasons must contain
    no_marker_note: bool = False      # its Review Reasons must not mention list markers
    section: str = None               # exact Section column, when given
    pages: str = None                 # exact Page(s) column, when given
    title: str = None                 # exact Title column (run-in title), when given
    corrected: str = ""               # text its OCR Corrections must contain
    quality: str = ""                 # text its Quality Notes must contain

    def label(self) -> str:
        checks = []
        if self.title is not None:
            checks.append(f"Title: {self.title or '(empty)'}")
        if self.corrected:
            checks.append(f"corrected: {self.corrected}")
        if self.quality:
            checks.append(f"quality note: {self.quality}")
        if self.note:
            checks.append(f"review note: {self.note}")
        if self.no_marker_note:
            checks.append("no list-marker note")
        if self.section is not None:
            checks.append(f"Section: {self.section or '(empty)'}")
        if self.pages is not None:
            checks.append(f"Page(s): {self.pages}")
        return "; ".join(checks)


_CHECK = re.compile(r"\s*\[(note|no marker note|section|pages|title|corrected|quality)(?::\s*([^\]]*))?\]\s*$", re.I)


def _row(spec: str, stem: str = "") -> Row:
    note, no_note, section, pages = "", False, None, None
    extra = {}
    while True:
        m = _CHECK.search(spec)
        if not m:
            break
        kind, value = m.group(1).lower(), (m.group(2) or "").strip()
        if kind == "note":
            note = value
        elif kind == "no marker note":
            no_note = True
        elif kind == "section":
            section = value
        elif kind == "pages":
            pages = value
        else:
            extra[kind] = value
        spec = spec[:m.start()]
    ref, sep, text = spec.partition("|")
    if not sep:
        raise ValueError(f"an expected row needs '<Doc Ref> | <Content>': {spec!r}")
    text = " ".join(text.split())
    content = f"{stem} {text}" if stem else text
    return Row(" ".join(ref.split()), content, stem, note, no_note, section, pages, extra.get("title"),
               extra.get("corrected", ""), extra.get("quality", ""))


def para(*specs: str) -> list:
    """Expected rows given in full: para('3.2.5 | The equipment shall not exceed 45 kilograms.')"""
    return [_row(s) for s in specs]


def items(stem: str, *specs: str) -> list:
    """Expected list-item rows: the stem (lead-in sentence) is put in front of each one, as the tool does."""
    stem = " ".join(stem.split())
    return [_row(s, stem) for s in specs]


# ---- lists drawn from their parts (the form the earlier 'list suite' used; its pages are kept exactly) -------------
def _draw_items(pg: Sheet, its: list, xs: tuple, gap: float):
    """Draw 'marker <tab> label <tab> value' items; label and value columns may each run over several rows."""
    xm, xl, xv = xs
    for n, it in enumerate(its):
        if n:
            pg.newline(gap)
        labels, values = it.get("label", []), it.get("value", [])
        for k in range(max(1, len(labels), len(values))):
            if k == 0:
                pg.text(xm, it["m"])
            if k < len(labels):
                pg.text(xl, labels[k])
            if k < len(values):
                pg.text(xv, values[k])
            pg.newline()
        if it.get("sub"):
            pg.newline(it.get("sub_gap", gap))
            _draw_items(pg, it["sub"], it["sub_xs"], it.get("sub_gap", gap))


def _item_rows(ref: str, stem: str, its: list, path: tuple = ()) -> list:
    rows = []
    for it in its:
        part = " ".join(x for x in (it["m"], " ".join(it.get("label", [])), " ".join(it.get("value", []))) if x)
        p = path + ((it["m"], part),)
        if it.get("sub"):
            rows += _item_rows(ref, stem, it["sub"], p)
            continue
        marks = [m.strip("().") for m, _ in p if m and m not in BULLETS]
        doc_ref = f"{ref} {'.'.join(marks)}" if marks else ref
        rows.append(Row(doc_ref, f"{stem} {' '.join(pt for _, pt in p)}", stem))
    return rows


def tab_list(lead: str, stem: str, ref: str, its: list, xs: tuple, gap: float = 0.5, lead_gap: float = 0.6,
             after: tuple = (), after_rows: tuple = ()) -> tuple:
    """A lead-in paragraph, then a list whose marker, label and value sit on tab stops at xs = (marker x,
    label x or None, value x) inches, then whatever `after` draws -> (draw function, expected rows).
    items: dict(m="a.", label=["Acceleration:"], value=["5 g in each ...", "for 1 minute per axis."]),
    optionally sub=[...], sub_xs=(...) for a nested list. The expected rows are worked out from the same items,
    so the drawing and the expectation cannot drift apart."""
    def draw(pg: Sheet):
        pg.para(lead)
        pg.newline(lead_gap)
        _draw_items(pg, its, xs, gap)
        for fn in after:
            fn(pg)
    return draw, _item_rows(ref, stem, its) + list(after_rows)


def tab_text(lead, its, after=(), marker: int = 4, label: int = 11, value: int = 28, between: str = "~") -> str:
    """The page text of a lead-in and a list on tab stops, for the text layouts: every item is
    (marker, label or [label lines], [value lines]) and is written with its marker at column `marker`, its
    label at column `label` and its value at column `value`; `between` goes before every item ('~' = half a
    blank line, '' = none). lead and after are lines of text (a string is one line)."""
    out = [lead] if isinstance(lead, str) else list(lead)
    for m, lab, values in its:
        if between:
            out.append(between)
        labels = lab if isinstance(lab, list) else ([lab] if lab else [])
        for k in range(max(1, len(labels), len(values))):
            row = ""
            for col, piece in ((marker, m if k == 0 else ""), (label, labels[k] if k < len(labels) else ""),
                               (value, values[k] if k < len(values) else "")):
                if piece:
                    if row and len(row) > col - 2:        # two spaces at least, or it would be one piece
                        raise ValueError(f"{piece!r} does not fit at column {col}: {row!r}")
                    row = row.ljust(col) + piece
            out.append(row)
    return "\n".join(out + (list(after) if not isinstance(after, str) else [after]))


def gap(n: float):
    return lambda pg: pg.newline(n)


def line(x: float, s: str):
    def f(pg):
        pg.text(x, s)
        pg.newline()
    return f


def paragraph(text: str):
    return lambda pg: pg.para(text)


# =====================================================================================================================
# A case
# =====================================================================================================================
@dataclass
class Case:
    id: str                           # "TAB-01" - never reuse an ID for a different situation
    title: str                        # one line
    situation: str                    # what the page shows, in words
    risk: str                         # what the tool must do, and what went wrong before (if it did)
    source: str                       # where the case came from (user report, review round, list suite ...)
    expect: list                      # the Requirement rows, in order (para(...) + items(...))
    text: str = ""                    # the page(s), written as text (see the top of this file) ...
    draw: object = None               # ... or a function that draws on a Sheet
    font: str = "mono"                # "mono" (typewriter) or "serif" (proportional)
    pt: float = 11
    dpi: int = 300
    pitch: float = 0.19
    copy: str = ""                    # "photocopy" = run the page through photocopier-style damage
    tables: int = 0                   # number of Table items expected
    table_has: tuple = ()             # text each expected table must contain ('Impedance: | 50 ohm | Analysis')
    captions: tuple = None            # caption labels expected ('TABLE I', 'FIGURE 3'), when checked
    known: str = ""                   # a KNOWN LIMITATION: why the tool still gets this wrong (it may fail)
    # the headings of the Document Structure sheet, in order, as "level | number and title" ("2 | 3.1 General")
    outline: tuple = None
    # the Applicable Documents sheet, in order, as "document | title | paragraphs" ("MIL-STD-461G | Requirements ... |
    # 3.2.5"); the title is compared like a requirement's text, the rest exactly
    documents: tuple = None
    scan: str = ""                    # your own scan (my_cases): its file, used as it is instead of a drawn page
    area: str = ""                    # filled in from the area file

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "_", self.title.lower()).strip("_")[:60]

    @property
    def filename(self) -> str:
        return f"{self.id}_{self.slug}.pdf"

    def sheets(self) -> list:
        """Draw the case -> list of Sheets (pages)."""
        new = lambda: Sheet(self.font, self.pt, self.dpi, self.pitch)
        if self.draw is not None:
            pg = new()
            self.draw(pg)
            return [pg]
        return draw_layout(self.text, new)

    def images(self) -> list:
        """The pages as the scanner would give them (PIL images), with photocopy damage when asked for."""
        import numpy as np
        from PIL import Image
        pages = [pg.img for pg in self.sheets()]
        if self.copy == "photocopy":
            rng = np.random.default_rng(zlib.crc32(self.id.encode()))
            pages = [Image.fromarray(degrade(np.array(p), PHOTOCOPY, rng)) for p in pages]
        elif self.copy:
            raise ValueError(f"{self.id}: unknown copy={self.copy!r}")
        return pages

    def save_pdf(self, path: Path) -> None:
        pages = self.images()
        pages[0].save(path, "PDF", resolution=self.dpi, save_all=True, append_images=pages[1:],
                      title=f"{self.id} {self.title}", subject=self.situation[:250], author="spec_extractor test cases")


LOCAL_FOLDER = HERE / "my_cases"     # your own scans and what the tool must produce for them (never in git)
SCAN_TYPES = (".pdf", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp")


def read_expected(path: Path, scan: Path) -> "Case":
    """A case from your own scan and its .expected.txt (written by run_cases.py --record, then corrected by hand).
    One expectation per line; # starts a comment:
        requirement: 3.2.1 | The equipment shall operate from 115 V ac.  [title: Power input]
        tables: 1                     table has: Flow control              caption: TABLE I
        heading: 2 | 3.1 General      document: MIL-STD-461G | Requirements for ... | 3.2.5"""
    rows, tables, table_has, captions, outline, documents = [], 0, [], [], [], []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("  #", 1)[0].strip() if not raw.lstrip().startswith("#") else ""
        if not line:
            continue
        kind, sep, value = line.partition(":")
        kind, value = kind.strip().lower(), value.strip()
        if not sep:
            raise ValueError(f"{path.name} line {n}: write 'requirement: ...', 'tables: 1', 'heading: ...' and so on")
        if kind == "requirement":
            rows.append(_row(value))
        elif kind == "tables":
            tables = int(value)
        elif kind == "table has":
            table_has.append(value)
        elif kind == "caption":
            captions.append(value)
        elif kind == "heading":
            outline.append(value)
        elif kind == "document":
            documents.append(value)
        else:
            raise ValueError(f"{path.name} line {n}: unknown kind of expectation {kind!r}")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", scan.stem).strip("-").upper()[:40] or "SCAN"
    return Case(f"MY-{slug}", scan.name, "Your own scan (tests/cases/my_cases), kept on this computer.",
                "What the tool must produce for it, as written in " + path.name + ".", "my_cases", expect=rows,
                tables=tables, table_has=tuple(table_has), captions=tuple(captions) if captions else None,
                outline=tuple(outline) if outline else None, documents=tuple(documents) if documents else None,
                scan=str(scan), area="Your own scans")


def load_local_cases(folder: Path = LOCAL_FOLDER) -> list:
    """Your own scans in tests/cases/my_cases that have an <file>.expected.txt beside them."""
    if not folder.is_dir():
        return []
    cases = []
    for expected in sorted(folder.glob("*.expected.txt")):          # "page12.pdf.expected.txt" beside "page12.pdf"
        scan = folder / expected.name[:-len(".expected.txt")]
        if scan.is_file() and scan.suffix.lower() in SCAN_TYPES:
            cases.append(read_expected(expected, scan))
    return cases


def load_cases(folder: Path = HERE) -> list:
    """All cases of the library, area by area, with their IDs checked (unique, and shaped like 'TAB-01')."""
    cases, seen = [], {}
    for name in AREAS:
        path = folder / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"spec_cases_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        AREA_DOCS[mod.AREA] = " ".join((mod.__doc__ or "").split())
        for c in mod.CASES:
            c.area = mod.AREA
            if not re.fullmatch(r"[A-Z]{2,4}-\d{2}[A-Z]?", c.id):
                raise ValueError(f"{path.name}: case ID {c.id!r} is not shaped like 'TAB-01'")
            if c.id in seen:
                raise ValueError(f"case ID {c.id} is used twice ({seen[c.id]} and {path.name})")
            if not c.expect and not c.tables and not c.outline and not c.documents:
                raise ValueError(f"{c.id}: a case must expect at least one row, table, heading or document")
            if bool(c.text) == (c.draw is not None):
                raise ValueError(f"{c.id}: give the page as text=... or draw=..., not both / neither")
            seen[c.id] = path.name
            cases.append(c)
    return cases


def library_hash(folder: Path = HERE) -> str:
    """A fingerprint of every case definition and of this file: when it changes, the documents and the
    catalog must be built again."""
    h = hashlib.sha256()
    for name in ["casekit"] + AREAS:
        h.update((folder / f"{name}.py").read_bytes())
    return h.hexdigest()[:16]


def rule_tests(folder: Path = HERE) -> list:
    """[(test name, first sentence of its description)] of tests/test_rules.py, in file order - the list the
    catalog prints in its appendix."""
    import ast
    tree = ast.parse((folder.parent / "test_rules.py").read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            out.append((node.name, _first_sentence(" ".join((ast.get_docstring(node) or "").split()))))
    return out


def _first_sentence(text: str, limit: int = 240) -> str:
    """The first sentence of a description - not cut inside a quoted example ('a. Search mode.'): a quote mark
    between two letters is an apostrophe, any other one opens or closes a quotation."""
    quoted = False
    for k, ch in enumerate(text):
        if ch == "'" and not (0 < k < len(text) - 1 and text[k - 1].isalpha() and text[k + 1].isalpha()):
            quoted = not quoted
        elif ch in ".:" and not quoted and text[k + 1:k + 3][:1] == " " and text[k + 2:k + 3].isupper():
            return text[:k + 1]
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


def tool_version(folder: Path = HERE) -> str:
    """The version of spec_extractor.py in this project."""
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', (folder.parent.parent / "spec_extractor.py").read_text(encoding="utf-8"),
                  re.M)
    return m.group(1) if m else "?"


def catalog_fingerprint(folder: Path = HERE) -> str:
    """What CASEBOOK.pdf is made from: the case definitions, the list of rule tests and the tool version it names.
    It is written into the catalog's keywords; tests/test_rules.py checks that it still matches, so the catalog is
    rebuilt (python tests/cases/build_cases.py) whenever a case or a rule test is added or changed."""
    h = hashlib.sha256(library_hash(folder).encode())
    h.update(repr(rule_tests(folder)).encode())
    h.update(tool_version(folder).encode())
    return h.hexdigest()[:16]
