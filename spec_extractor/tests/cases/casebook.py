"""
casebook.py - writes CASEBOOK.pdf, the printed catalog of the test-case library (build_cases.py calls it).

For every case it shows the ID, the situation, what the tool must do (and what went wrong before), the page
itself - drawn again as vector text, exactly where the scan document has it - and the rows the tool must
produce, with their checks. A known limitation is marked. The appendices list every fast rule test
(tests/test_rules.py) and the regression documents, so all the tests can be looked up in one place.

The catalog records a fingerprint of the case definitions and of the rule-test list in its keywords; the fast
tests check it, so the catalog cannot silently fall behind the cases. It is drawn with ReportLab's built-in
PDF fonts (Courier for typewriter pages, Times for proportional ones): nothing is downloaded or embedded, and the
same definitions always give the same file.
"""
from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

import casekit

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent

GREY = colors.HexColor("#6b6b6b")
LIGHT = colors.HexColor("#eeeeee")
KNOWN_BG = colors.HexColor("#fff4d6")
KNOWN_LINE = colors.HexColor("#c98a00")

_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=11.5, spaceAfter=4)
_SMALL = ParagraphStyle("small", parent=_BODY, fontSize=7.8, leading=9.6, spaceAfter=0)
_CELL = ParagraphStyle("cell", parent=_BODY, fontSize=7.6, leading=9.2, spaceAfter=0)
_LABEL = ParagraphStyle("label", parent=_BODY, fontName="Helvetica-Bold", fontSize=8.5, spaceAfter=1, spaceBefore=3)
_H1 = ParagraphStyle("h1", parent=_BODY, fontName="Helvetica-Bold", fontSize=18, leading=22, spaceAfter=8)
_H2 = ParagraphStyle("h2", parent=_BODY, fontName="Helvetica-Bold", fontSize=13, leading=16, spaceAfter=4)
_CASE = ParagraphStyle("case", parent=_BODY, fontName="Helvetica-Bold", fontSize=12.5, leading=15, spaceAfter=1)


# =====================================================================================================================
# What the catalog lists besides the cases
# =====================================================================================================================
def regression_documents() -> list:
    """The file names tests/make_test_corpus.py writes (the regression documents), in the order it writes them."""
    src = (TESTS / "make_test_corpus.py").read_text(encoding="utf-8")
    return list(dict.fromkeys(re.findall(r'out / f?"(spec\w+?\.(?:pdf|tif))"', src)))


# =====================================================================================================================
# The page of a case, drawn again as vector text
# =====================================================================================================================
class PageDrawing(Flowable):
    """The case's page(s), drawn from what the Sheet recorded: every piece of text where the scan has it
    (Courier for the typewriter font, Times for the proportional one) and every ruled line. Each page is cut
    to the band that holds its text (the frame's top and bottom edges), at its full width, and the pages are
    stacked; the drawing is as large as the width allows, and scaled down only when it would be very tall."""
    GAP = 10                                              # points between two pages

    def __init__(self, sheets: list, width: float, max_height: float = 6.3 * inch):
        super().__init__()
        self.sheets = sheets
        self.bands = []                                   # (top, bottom) of each page's text, in inches
        for sh in sheets:
            ys = [y / sh.dpi for _x, y, *_ in sh.pieces] + [min(r[1], r[3]) / sh.dpi for r in sh.rules]
            ends = [y / sh.dpi + 1.3 * pt / 72 for _x, y, _t, _f, pt in sh.pieces] + \
                   [max(r[1], r[3]) / sh.dpi for r in sh.rules]
            self.bands.append((max(0.0, min(ys, default=1.0) - 0.3), min(11.0, max(ends, default=2.0) + 0.3)))
        tall = sum(b - a for a, b in self.bands) * 72
        self.scale = min(width / (8.5 * 72), (max_height - self.GAP * (len(sheets) - 1)) / tall)
        self.page_w = 8.5 * 72 * self.scale
        self.width = self.page_w
        self.height = tall * self.scale + self.GAP * (len(sheets) - 1)

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def draw(self):
        c = self.canv
        top = self.height
        for k, (sh, (b0, b1)) in enumerate(zip(self.sheets, self.bands)):
            h = (b1 - b0) * 72 * self.scale
            oy = top - h                                  # bottom of this page's band on the catalog
            c.setStrokeColor(colors.HexColor("#9a9a9a"))
            c.setLineWidth(0.6)
            c.rect(0, oy, self.page_w, h)
            c.setFont("Helvetica", 6)
            c.setFillColor(GREY)
            label = (f"page {k + 1}, " if len(self.sheets) > 1 else "") + f"{b0:.1f} to {b1:.1f} inches from the top"
            c.drawRightString(self.page_w - 3, oy + 3, label)
            px = self.scale * 72 / sh.dpi                 # catalog points per scan pixel
            c.setFillColor(colors.black)
            y_top = b0 * sh.dpi                           # the band's top, in scan pixels
            for x, y, text, font, pt in sh.pieces:
                size = pt * self.scale
                face, ascent = ("Courier", 0.83) if font.startswith("mono") else ("Times-Roman", 0.89)
                if font.endswith("-bold"):
                    face = "Courier-Bold" if face == "Courier" else "Times-Bold"
                c.setFont(face, size)
                c.drawString(x * px, top - ((y - y_top) * px + ascent * size), text)   # (y: top of the text)
            c.setStrokeColor(colors.black)
            for x0, y0, x1, y1, w in sh.rules:
                c.setLineWidth(max(0.3, w * px))
                c.line(x0 * px, top - (y0 - y_top) * px, x1 * px, top - (y1 - y_top) * px)
            top = oy - self.GAP


# =====================================================================================================================
# The catalog
# =====================================================================================================================
def _p(text: str, style=_BODY) -> Paragraph:
    return Paragraph(text, style)


def _known_box(text: str, width: float) -> Table:
    t = Table([[_p(f"<b>KNOWN LIMITATION</b> - the tool still gets this case wrong: {escape(text)}", _SMALL)]],
              colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), KNOWN_BG), ("BOX", (0, 0), (-1, -1), 0.8, KNOWN_LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _rows_table(case, width: float) -> list:
    """The expected rows of a case as a table: Doc Ref | Content (the lead-in in grey) | checks."""
    out = []
    if case.expect:
        data = [[_p("<b>Doc Ref</b>", _CELL), _p("<b>Content</b> (the lead-in in grey)", _CELL), _p("<b>Also checked</b>", _CELL)]]
        for r in case.expect:
            content = escape(r.content)
            if r.stem and r.content.startswith(r.stem):
                content = f'<font color="#7a7a7a">{escape(r.stem)}</font>{escape(r.content[len(r.stem):])}'
            data.append([_p(escape(r.doc_ref) or '<font color="#9a9a9a">(empty)</font>', _CELL), _p(content, _CELL),
                         _p(escape(r.label()), _CELL)])
        t = Table(data, colWidths=[0.85 * inch, width - 2.45 * inch, 1.6 * inch], repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b5b5b5")),
                               ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        out.append(t)
    else:
        out.append(_p("<i>No Requirement rows.</i>", _SMALL))
    extra = []
    if case.tables or not case.expect:
        extra.append(f"{case.tables} Table item(s)" + (f", containing {', '.join(repr(t) for t in case.table_has)}"
                                                       if case.table_has else ""))
    if case.captions is not None:
        extra.append("caption(s): " + (", ".join(case.captions) or "none"))
    if extra:
        out.append(Spacer(1, 3))
        out.append(_p("Also expected: " + escape("; ".join(extra)) + ".", _SMALL))
    # the headings of the Document Structure sheet and the documents of the Applicable Documents sheet, when checked
    for rows, title, heads, widths in (
            (case.outline, "The headings it must find (Document Structure sheet), in order",
             ("Level", "Number and title"), (0.6 * inch, width - 0.6 * inch)),
            (case.documents, "The documents it must list (Applicable Documents sheet), in order",
             ("Document", "Title", "Paragraphs"), (1.4 * inch, width - 2.6 * inch, 1.2 * inch))):
        if not rows:
            continue
        data = [[_p(f"<b>{h}</b>", _CELL) for h in heads]]
        for row in rows:
            cells = [c.strip() for c in row.split("|")] + [""] * len(heads)
            data.append([_p(escape(c) or '<font color="#9a9a9a">(empty)</font>', _CELL) for c in cells[:len(heads)]])
        t = Table(data, colWidths=list(widths), repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b5b5b5")),
                               ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        out += [Spacer(1, 6), _p(title, _LABEL), t]
    return out


def _case_flowables(case, width: float) -> list:
    sheets = case.sheets()
    fmt = [("typewriter" if case.font == "mono" else "proportional") + f" {case.pt:g} pt", f"{case.dpi} dpi"]
    if case.copy:
        fmt.append(case.copy + " (drawn here without the damage)")
    if len(sheets) > 1:
        fmt.append(f"{len(sheets)} pages")
    head = [_p(f"{escape(case.id)} &nbsp; {escape(case.title)}", _CASE),
            _p(f'<font color="#6b6b6b">{escape(case.area)} &nbsp;|&nbsp; document: documents/{escape(case.filename)} '
               f'&nbsp;|&nbsp; {escape(", ".join(fmt))}</font>', _SMALL), Spacer(1, 5)]
    words = [_p("Situation", _LABEL), _p(escape(case.situation), _SMALL),
             _p("What the tool must do", _LABEL), _p(escape(case.risk), _SMALL),
             _p("Source", _LABEL), _p(escape(case.source), _SMALL)]
    if case.known:
        words += [Spacer(1, 5), _known_box(case.known, width)]
    body = words + [Spacer(1, 6), _p("The page (as the scan document has it)", _LABEL), PageDrawing(sheets, width)]
    return [KeepTogether(head + body), Spacer(1, 8), _p("The rows the tool must produce", _LABEL)] \
        + _rows_table(case, width)


def write_casebook(cases: list, path: Path) -> None:
    """Write the catalog of these cases to `path` (a PDF)."""
    width = letter[0] - 1.3 * inch
    version = casekit.tool_version()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(0.65 * inch, 0.45 * inch, f"spec_extractor {version} - test-case library")
        canvas.drawRightString(letter[0] - 0.65 * inch, 0.45 * inch, f"page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=letter, leftMargin=0.65 * inch, rightMargin=0.65 * inch,
                          topMargin=0.6 * inch, bottomMargin=0.7 * inch, invariant=1,
                          title="spec_extractor test-case library", author="spec_extractor test cases",
                          subject=f"The test cases of spec_extractor {version}: one page per case",
                          keywords=f"casebook-fingerprint:{casekit.catalog_fingerprint()}")
    doc.addPageTemplates([PageTemplate(id="page", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width,
                                                                 doc.height, id="f", leftPadding=0, rightPadding=0,
                                                                 topPadding=0, bottomPadding=0)], onPage=footer)])
    story = _cover(cases, width, version) + _index(cases, width)
    for area in dict.fromkeys(c.area for c in cases):
        in_area = [c for c in cases if c.area == area]
        story += [PageBreak(), _p(escape(area), _H1),
                  _p(escape(_area_intro(in_area[0])), _BODY), Spacer(1, 6)]
        for k, c in enumerate(in_area):
            if k:
                story.append(PageBreak())
            story += _case_flowables(c, width)
    story += _appendices(width)
    doc.build(story)


def _area_intro(case) -> str:
    """The description at the top of the case's area file."""
    return casekit.AREA_DOCS.get(case.area, "")


def _cover(cases: list, width: float, version: str) -> list:
    areas = list(dict.fromkeys(c.area for c in cases))
    known = [c for c in cases if c.known]
    rows = [[_p("<b>Area</b>", _CELL), _p("<b>Cases</b>", _CELL), _p("<b>IDs</b>", _CELL), _p("<b>Known limitations</b>", _CELL)]]
    for a in areas:
        ids = [c.id for c in cases if c.area == a]
        rows.append([_p(escape(a), _CELL), _p(str(len(ids)), _CELL), _p(f"{ids[0]} to {ids[-1]}", _CELL),
                     _p(", ".join(c.id for c in cases if c.area == a and c.known) or "-", _CELL)])
    t = Table(rows, colWidths=[2.2 * inch, 0.6 * inch, 1.5 * inch, width - 4.3 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b5b5b5")),
                           ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    how = [
        "<b>What this is.</b> Every situation the tool has to get right - a common layout, or a detail that went "
        "wrong once - is a <b>case</b> with a fixed ID (TAB-01, LST-07 ...). Each case is one small page, saved as "
        "a scanned document of its own, together with the exact rows the tool must produce from it. Use the IDs to "
        "talk about a situation: in a bug report, a review or a commit message (\"LST-10 fails again\").",
        "<b>This catalog</b> shows each case on its own page: the situation, what the tool must do and why (and "
        "what went wrong before, where it did), the page itself - drawn again here as text, where the scan has it - "
        "and the rows expected, with their checks. A <b>known limitation</b> is a case the tool still gets wrong: "
        "it is kept, with what happens instead, so that it is tracked and so that a fix shows up at once.",
        "<b>The scanned documents</b> (image PDFs, as the tool sees them) are drawn on your computer by "
        "<font face='Courier'>python tests/cases/build_cases.py</font>, into "
        "<font face='Courier'>tests/cases/documents/</font> - one file per case, named by its ID, e.g. "
        "<font face='Courier'>TAB-01_letters_labels_and_two_line_values_on_wide_tab_stops.pdf</font>. Open one to "
        "see exactly what the tool reads, or run the tool on it yourself.",
        "<b>Running the cases.</b> <font face='Courier'>python tests/cases/run_cases.py</font> runs the tool on "
        "every document (offline; a few minutes) and checks each case: PASS, FAIL, KNOWN (a known limitation, still "
        "wrong) or KNOWN-PASSES (a known limitation that now passes - check it and remove the mark). It lists "
        "every case whose result changed since the last run, so the effect of an edit is seen at once. "
        "<font face='Courier'>--only TAB</font> runs one area, <font face='Courier'>--only TAB-07</font> one case. "
        "The full comparison is written to <font face='Courier'>tests/cases/_results/case_report.txt</font> and "
        "<font face='Courier'>case_results.xlsx</font>.",
        "<b>How a case is checked.</b> The Requirement rows of the Extracted Items sheet must match the expected "
        "rows one for one: the same number of rows, each Doc Ref exactly as expected and in order, and each "
        "Content at least 90 % similar to the expected text - both as a whole and after the lead-in, so an item "
        "that lost its value cannot pass on the strength of its lead-in. Checks written after a row (a review note, "
        "the Section, the Page(s)) and the number of tables and captions are checked too.",
        "<b>Adding a case.</b> Write the page as text in the right tests/cases/area_*.py file (the format is "
        "explained at the top of tests/cases/casekit.py), give it the next free ID of its area and the rows the "
        "tool must produce, then run <font face='Courier'>python tests/cases/build_cases.py</font> to draw its "
        "document and rewrite this catalog. Never reuse an ID for a different situation.",
    ]
    return ([_p("spec_extractor", _H2), _p("Test-case library", _H1),
             _p(f"Tool version {escape(version)} &nbsp;|&nbsp; {len(cases)} cases in {len(areas)} areas, "
                f"{len(known)} of them known limitations", _BODY), Spacer(1, 6)]
            + [_p(h) for h in how] + [Spacer(1, 6), t])


def _index(cases: list, width: float) -> list:
    rows = [[_p("<b>ID</b>", _CELL), _p("<b>Situation</b>", _CELL), _p("<b>Area</b>", _CELL), _p("<b>Known limitation</b>", _CELL)]]
    for c in cases:
        rows.append([_p(escape(c.id), _CELL), _p(escape(c.title), _CELL), _p(escape(c.area), _CELL),
                     _p("yes" if c.known else "", _CELL)])
    t = Table(rows, colWidths=[0.7 * inch, width - 3.3 * inch, 1.8 * inch, 0.8 * inch], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5c5c5")),
                           ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
                          + [("BACKGROUND", (3, k + 1), (3, k + 1), KNOWN_BG) for k, c in enumerate(cases) if c.known]))
    return [PageBreak(), _p("Index of the cases", _H1), t]


def _appendices(width: float) -> list:
    tests = casekit.rule_tests()
    rows = [[_p("<b>Rule test</b> (tests/test_rules.py) - and what it checks, where its description says more", _CELL)]]
    for name, first in tests:
        text = f"<b>{escape(name[5:].replace('_', ' '))}</b>"
        if first:
            text += f' <font color="#5a5a5a">- {escape(first)}</font>'
        rows.append([_p(text, _CELL)])
    t = Table(rows, colWidths=[width], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c5c5c5")),
                           ("BACKGROUND", (0, 0), (-1, 0), LIGHT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    docs = regression_documents()
    return [PageBreak(), _p("Appendix A - the fast rule tests", _H1),
            _p(f"<font face='Courier'>python tests/test_rules.py</font> runs these {len(tests)} checks in seconds, "
               "without the OCR: each builds OCR lines with realistic page geometry and runs them through the same "
               "steps as a scanned page. They test one rule at a time; the cases in this catalog test the whole tool "
               "on real scans of whole pages.", _BODY), Spacer(1, 4), t,
            CondPageBreak(3 * inch), Spacer(1, 10), _p("Appendix B - the regression documents", _H1),
            _p("<font face='Courier'>python tests/run_regression.py</font> builds these synthetic specifications "
               "with <font face='Courier'>tests/make_test_corpus.py</font>, ages them into office scans, photocopies "
               "and faxes, runs the whole tool and scores it against exact ground truth (README, section 6): "
               + escape(", ".join(docs)) + ".", _BODY)]
