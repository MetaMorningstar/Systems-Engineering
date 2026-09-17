#!/usr/bin/env python3
"""
make_test_corpus.py - Build synthetic "old scanned specification" test documents
with exact ground truth, so spec_extractor.py can be validated with real numbers.

WHY SYNTHETIC?
    Real controlled documents cannot leave their network, and public scans have no
    ground truth. Here every requirement, caption and table cell is known exactly,
    so we can measure recall, precision and character error rate after extraction.

HOW IT WORKS
    1. Each test document is described below as a list of elements (headings,
       numbered paragraphs, stem+list requirements, tables, figures).
    2. ReportLab lays the document out as a normal PDF.
    3. pypdfium2 rasterizes every page (like a scanner would).
    4. OpenCV/numpy "age" the page images: skew, fading, ink bleed, speckle,
       blur, JPEG artifacts, uneven lighting, photocopier edges, punch holes,
       fax binarization, rotated pages.
    5. The damaged images are saved as image-only PDFs and multi-page TIFFs,
       alongside a <doc>_groundtruth.json file.

USAGE
    python tests/make_test_corpus.py            # writes to tests/corpus/
    python tests/make_test_corpus.py --out DIR
"""
from __future__ import annotations

import argparse
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, FrameBreak, Image as RLImage, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

# --------------------------------------------------------------------------------------
# Fonts: a real typewriter face for the "1980s spec", serif/sans for the SRS, mono for fax
# --------------------------------------------------------------------------------------
FONT_DIRS = [Path("/usr/share/fonts/truetype/liberation"), Path("C:/Windows/Fonts")]


def _register_fonts() -> dict:
    """Register fonts; fall back to ReportLab built-ins if a font file is missing."""
    names = {"type": "Courier", "type_bold": "Courier-Bold", "serif": "Times-Roman",
             "sans_bold": "Helvetica-Bold", "mono": "Courier"}
    # Courier 10 Pitch (Bitstream) looks like an IBM Selectric typewriter.
    afm, pfb = Path("/usr/share/fonts/X11/Type1/c0419bt_.afm"), Path("/usr/share/fonts/X11/Type1/c0419bt_.pfb")
    if afm.exists() and pfb.exists():
        face = pdfmetrics.EmbeddedType1Face(str(afm), str(pfb))
        pdfmetrics.registerTypeFace(face)
        pdfmetrics.registerFont(pdfmetrics.Font("Courier10Pitch", face.name, "WinAnsiEncoding"))
        names["type"] = "Courier10Pitch"
    for key, fname in [("serif", "LiberationSerif-Regular.ttf"), ("sans_bold", "LiberationSans-Bold.ttf"),
                       ("mono", "LiberationMono-Regular.ttf"), ("type_bold", "LiberationMono-Bold.ttf")]:
        for d in FONT_DIRS:
            if (d / fname).exists():
                pdfmetrics.registerFont(TTFont(fname[:-4], str(d / fname)))
                names[key] = fname[:-4]
                break
    # Paragraph() needs a family mapping (normal/bold/italic) for every custom font.
    for font_name in set(names.values()):
        if font_name not in ("Courier", "Courier-Bold", "Times-Roman", "Helvetica-Bold"):
            for bold in (0, 1):
                for italic in (0, 1):
                    addMapping(font_name, bold, italic, font_name)
    return names


FONTS = _register_fonts()


# --------------------------------------------------------------------------------------
# Ground-truth records
# --------------------------------------------------------------------------------------
@dataclass
class GTReq:
    text: str                 # the complete requirement as it should appear in the output row
    keyword: str              # shall / must / should / will
    source: str               # paragraph | list | table
    doc_id: str = ""          # paragraph number or explicit ID printed in the document

    @property
    def category(self) -> str:
        return {"shall": "mandatory", "must": "mandatory", "should": "goal", "will": "intent"}[self.keyword]


@dataclass
class GroundTruth:
    doc: str
    requirements: list = field(default_factory=list)
    captions: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    all_text: list = field(default_factory=list)

    def to_json(self) -> dict:
        d = asdict(self)
        d["requirements"] = [dict(asdict(r), category=r.category) for r in self.requirements]
        return d


class Builder:
    """Collects ReportLab flowables and the matching ground truth at the same time."""

    def __init__(self, doc_name: str, body: ParagraphStyle, heading: ParagraphStyle, small: ParagraphStyle):
        self.story: list = []
        self.gt = GroundTruth(doc=doc_name)
        self.body, self.heading_style, self.small = body, heading, small

    # plain text helpers -------------------------------------------------------------
    def _p(self, text: str, style: ParagraphStyle, **kw) -> Paragraph:
        st = ParagraphStyle(f"x{len(self.story)}", parent=style, **kw) if kw else style
        return Paragraph(escape(text), st)

    def spacer(self, h: float):
        self.story.append(Spacer(1, h))

    def page_break(self):
        self.story.append(PageBreak())

    def title_block(self, lines: list[str]):
        st = ParagraphStyle("title", parent=self.heading_style, alignment=TA_CENTER, fontSize=14, leading=22)
        self.spacer(2.2 * inch)
        for ln in lines:
            if ln:
                self.story.append(self._p(ln, st))
                self.gt.all_text.append(ln)
            else:
                self.spacer(18)

    def heading(self, text: str):
        self.story.append(self._p(text, self.heading_style, spaceBefore=10, spaceAfter=6))
        self.gt.all_text.append(text)

    def para(self, num: str, title: str, sentences: list[tuple[str, str | None]], **style_kw):
        """Numbered paragraph. sentences = [(sentence, keyword-or-None), ...]."""
        text = " ".join(x for x in [num, title, " ".join(s for s, _ in sentences)] if x)
        self.story.append(self._p(text, self.body, spaceAfter=8, **style_kw))
        self.gt.all_text.append(text)
        for s, kw in sentences:
            if kw:
                self.gt.requirements.append(GTReq(s, kw, "paragraph", num))

    def broken_para(self, lines: list[str], requirements: list[tuple[str, str]], doc_id: str = ""):
        """A paragraph whose line breaks are fixed (like a typed page), so a test can put a number,
        a unit or a designator at the start of a wrapped line. requirements = [(sentence, keyword)]."""
        markup = "<br/>".join(escape(ln) for ln in lines)
        self.story.append(Paragraph(markup, ParagraphStyle(f"x{len(self.story)}", parent=self.body, spaceAfter=8)))
        self.gt.all_text.append(" ".join(lines))
        for sentence, kw in requirements:
            self.gt.requirements.append(GTReq(sentence, kw, "paragraph", doc_id))

    def fill_page(self, leave_lines: float):
        """Push the next element down so that only `leave_lines` text lines fit before the page ends."""
        self.story.append(FillPage(leave_lines * self.body.leading))

    def list_item(self, stem: str, keyword: str, marker: str, item: str, doc_id: str, indent: float = 36,
                  item_gap: float = 6):
        """One list item of a stem (stem printed separately): expected row = "<stem> <marker> <item>"."""
        line = f"{marker} {item}".strip()
        self.story.append(self._p(line, self.body, leftIndent=indent, spaceBefore=item_gap))
        self.gt.all_text.append(line)
        self.gt.requirements.append(GTReq(" ".join(x for x in (stem, marker, item) if x), keyword, "list", doc_id))

    def plain(self, text: str, keyword: str | None = None, doc_id: str = "", req_text: str | None = None):
        self.story.append(self._p(text, self.body, spaceAfter=8))
        self.gt.all_text.append(text)
        if keyword:
            self.gt.requirements.append(GTReq(req_text or text, keyword, "paragraph", doc_id))

    def stem_list(self, lead: str, stem: str, keyword: str, items: list[tuple[str, str]], doc_id: str,
                  item_gap: float = 6, indent: float = 36):
        """A stem sentence ending in ':' followed by list items.
        Expected output: one requirement row per item = "<stem> <marker> <item>"."""
        text = f"{lead} {stem}".strip()
        self.story.append(self._p(text, self.body, spaceAfter=4))
        self.gt.all_text.append(text)
        for marker, item in items:
            self.list_item(stem, keyword, marker, item, doc_id, indent=indent, item_gap=item_gap)
        self.spacer(6)

    def table(self, caption: str | None, rows: list[list[str]], col_widths: list[float], *,
              req_col: int | None = None, id_col: int | None = None, keyword_of=None,
              ruled: bool = True, caption_above: bool = True, font: str | None = None, font_size: float = 9,
              optional: bool = False, spans: list | None = None, caption_row: bool = False,
              caption_space: tuple[float, float] = (6, 6), space_after: float = 8):
        """rows[0] is the header row. spans = ReportLab SPAN commands [((col0, row0), (col1, row1)), ...].
        caption_row=True draws the caption INSIDE the table frame as a merged first row (some documents
        do this); the expected table then excludes that row. Merged cells: give their text once and
        leave the covered positions empty."""
        cell_style = ParagraphStyle(f"cell{len(self.story)}", parent=self.body, fontName=font or self.body.fontName,
                                    fontSize=font_size, leading=font_size * 1.25, spaceAfter=0, spaceBefore=0)
        grid_rows = ([[caption] + [""] * (len(rows[0]) - 1)] + rows) if caption_row else rows
        data = [[Paragraph(escape(c), cell_style) for c in r] for r in grid_rows]
        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                 ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        if ruled:
            style.append(("GRID", (0, 0), (-1, -1), 0.9, colors.black))
        else:
            style.append(("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.black))
        shift = 1 if caption_row else 0
        if caption_row:
            style.append(("SPAN", (0, 0), (-1, 0)))
        for (c0, r0), (c1, r1) in spans or []:
            style.append(("SPAN", (c0, r0 + shift), (c1, r1 + shift)))
        tbl.setStyle(TableStyle(style))
        cap_para = (self._p(caption, self.body, alignment=TA_CENTER, spaceBefore=caption_space[0], spaceAfter=caption_space[1])
                    if caption and not caption_row else None)
        parts = ([cap_para, tbl] if caption_above else [tbl, cap_para]) if cap_para else [tbl]
        self.story.append(KeepTogether(parts) if len(rows) < 12 else parts[0])
        if len(rows) >= 12:
            self.story.extend(parts[1:])
        if space_after:
            self.spacer(space_after)
        if caption:
            kind = "table"
            self.gt.captions.append({"kind": kind, "text": caption})
            self.gt.all_text.append(caption)
        self.gt.tables.append({"caption": caption, "rows": rows, "optional": optional})
        for r in rows:
            self.gt.all_text.extend(c for c in r if c)
        if req_col is not None:
            for r in rows[1:]:
                kw = keyword_of(r[req_col])
                if kw:
                    self.gt.requirements.append(GTReq(r[req_col], kw, "table", r[id_col] if id_col is not None else ""))

    def figure(self, flowable, caption: str, figure_words: list[str]):
        cap = self._p(caption, self.body, alignment=TA_CENTER, spaceBefore=6, spaceAfter=10)
        self.story.append(KeepTogether([Spacer(1, 6), flowable, cap]))
        self.gt.captions.append({"kind": "figure", "text": caption})
        self.gt.all_text.append(caption)
        self.gt.all_text.extend(figure_words)


class FillPage(Flowable):
    """Takes all the space left on the page except `leave` points, so the next paragraph starts
    near the bottom (used to force a paragraph across a page break, or text into the footer zone)."""

    def __init__(self, leave: float):
        super().__init__()
        self.leave = leave

    def wrap(self, avail_width, avail_height):
        self.height = max(0.0, avail_height - self.leave)
        return avail_width, self.height

    def draw(self):
        pass


def keyword_of(text: str) -> str | None:
    t = f" {text.lower()} "
    for kw in ("shall", "must", "should", "will"):
        if f" {kw} " in t:
            return kw
    return None


# --------------------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------------------
def block_diagram(labels: list[str], font: str, width=5.8 * inch, height=2.2 * inch) -> tuple[Drawing, list[str]]:
    """Simple boxes-and-arrows functional block diagram."""
    d = Drawing(width, height)
    n = len(labels)
    bw, bh, gap = (width - (n - 1) * 18) / n, 0.6 * inch, 18
    y = height / 2 - bh / 2
    for i, lab in enumerate(labels):
        x = i * (bw + gap)
        d.add(Rect(x, y, bw, bh, strokeColor=colors.black, fillColor=None, strokeWidth=1.4))
        d.add(String(x + bw / 2, y + bh / 2 - 3, lab, fontName=font, fontSize=7.5, textAnchor="middle"))
        if i < n - 1:
            x2 = x + bw
            d.add(Line(x2, y + bh / 2, x2 + gap - 4, y + bh / 2, strokeWidth=1.2))
            d.add(Polygon([x2 + gap - 5, y + bh / 2 + 3, x2 + gap, y + bh / 2, x2 + gap - 5, y + bh / 2 - 3],
                          fillColor=colors.black, strokeColor=colors.black))
    # a feedback loop drawn under the boxes
    d.add(Line(bw / 2, y, bw / 2, y - 0.45 * inch, strokeWidth=1.2))
    d.add(Line(bw / 2, y - 0.45 * inch, width - bw / 2, y - 0.45 * inch, strokeWidth=1.2))
    d.add(Line(width - bw / 2, y - 0.45 * inch, width - bw / 2, y, strokeWidth=1.2))
    return d, labels


def photo_like(seed: int, w_in=4.0, h_in=2.6) -> RLImage:
    """A smooth grayscale 'photograph' with a few shapes (tests picture detection)."""
    rng = np.random.default_rng(seed)
    w, h = int(w_in * 150), int(h_in * 150)
    img = cv2.GaussianBlur(rng.random((h, w)).astype(np.float32), (0, 0), 25)
    img = (img - img.min()) / (np.ptp(img) + 1e-6) * 140 + 60
    cv2.rectangle(img, (w // 5, h // 3), (w // 2, h - 30), 35, -1)          # a "console"
    cv2.circle(img, (int(w * 0.72), int(h * 0.45)), h // 5, 210, -1)        # a "monitor glare"
    buf = io.BytesIO()
    Image.fromarray(img.astype(np.uint8)).save(buf, format="PNG")
    buf.seek(0)
    return RLImage(buf, width=w_in * inch, height=h_in * inch)


# --------------------------------------------------------------------------------------
# Document A: MIL-STD-490/961 style system specification, typewriter font
# --------------------------------------------------------------------------------------
def build_spec_a() -> tuple[bytes, GroundTruth]:
    body = ParagraphStyle("A", fontName=FONTS["type"], fontSize=11, leading=14.5)
    head = ParagraphStyle("AH", parent=body, fontName=FONTS["type"])
    b = Builder("specA", body, head, body)
    b.title_block(["SPEC-RDR-0042 REV C", "15 MARCH 1987", "", "SYSTEM SPECIFICATION", "FOR THE",
                   "XR-7 SURVEILLANCE RADAR", "", "SAMPLE TEST DOCUMENT - ALL CONTENT IS FICTITIOUS"])
    b.page_break()
    b.heading("1. SCOPE")
    b.para("1.1", "Scope.", [("This specification establishes the performance, design, development, and verification "
                              "requirements for the XR-7 Surveillance Radar, hereinafter referred to as the radar.", None)])
    b.para("1.2", "Classification.", [("The radar will be furnished in fixed-site and transportable configurations.", "will")])
    b.heading("2. APPLICABLE DOCUMENTS")
    b.para("2.1", "General.", [("The documents listed below form a part of this specification to the extent specified herein.", None)])
    b.table(None, [["MIL-STD-461G", "Requirements for the Control of Electromagnetic Interference Characteristics"],
                   ["MIL-STD-704F", "Aircraft Electric Power Characteristics"],
                   ["MIL-STD-810H", "Environmental Engineering Considerations and Laboratory Tests"]],
            [1.5 * inch, 4.6 * inch], ruled=False, font_size=10.5, optional=True)
    b.heading("3. REQUIREMENTS")
    b.para("3.1", "Item definition.", [("The radar shall consist of the configuration items listed in TABLE I.", "shall")])
    b.table("TABLE I. Radar configuration items.",
            [["CI No.", "Nomenclature", "Quantity"], ["CI-01", "Antenna Assembly", "1"], ["CI-02", "Transmitter Unit", "1"],
             ["CI-03", "Receiver/Exciter", "2"], ["CI-04", "Signal Processor", "1"], ["CI-05", "Operator Console", "2"]],
            [1.2 * inch, 3.0 * inch, 1.2 * inch], font_size=10)
    b.heading("3.2 Characteristics.")
    b.heading("3.2.1 Performance characteristics.")
    b.para("3.2.1.1", "Detection range.", [(
        "The radar shall detect a target having a radar cross section of 1 m\u00b2 at a range of not less than 150 km "
        "with a probability of detection of 0.9.", "shall")])
    b.para("3.2.1.2", "Range accuracy.", [("The range accuracy shall be within \u00b115 m (1 sigma).", "shall"),
                                          ("The range resolution should be 25 m or better.", "should")])
    b.stem_list("3.2.1.3 Operating modes.", "The radar shall provide the following operating modes:", "shall",
                [("a.", "Search mode."), ("b.", "Track-while-scan mode."), ("c.", "Standby mode."),
                 ("d.", "Built-in test (BIT) mode.")], doc_id="3.2.1.3", item_gap=16)
    b.para("3.2.1.4", "Track capacity.", [("The radar shall maintain not less than 200 simultaneous tracks.", "shall"),
                                          ("The track update rate shall be not less than 1 Hz.", "shall")])
    b.heading("3.2.2 Physical characteristics.")
    b.para("3.2.2.1", "Weight.", [("The weight of the antenna assembly shall not exceed 450 kg.", "shall")])
    b.para("3.2.2.2", "Input power.", [("The radar shall operate from 115 VAC, 400 Hz, three-phase power in accordance "
                                        "with MIL-STD-704F.", "shall"),
                                       ("Total power consumption shall not exceed TBD kW.", "shall")])
    diag, words = block_diagram(["ANTENNA", "TRANSMITTER", "RECEIVER", "PROCESSOR", "CONSOLE"], FONTS["mono"])
    b.figure(diag, "FIGURE 1. Radar functional block diagram.", words)
    b.para("3.2.3", "Environmental conditions.", [("The radar shall meet the environmental requirements specified in "
                                                   "TABLE II.", "shall")])
    b.table("TABLE II. Environmental requirements.",
            [["Req ID", "Parameter", "Requirement", "Method"],
             ["ENV-001", "Operating temperature", "The radar shall operate within specification from -40 \u00b0C to +71 \u00b0C.", "T"],
             ["ENV-002", "Storage temperature", "The radar shall withstand storage temperatures from -57 \u00b0C to +85 \u00b0C.", "T"],
             ["ENV-003", "Humidity", "The radar shall operate at up to 95% relative humidity, non-condensing.", "T"],
             ["ENV-004", "Altitude", "The radar shall operate at altitudes up to 4,600 m above sea level.", "A"],
             ["ENV-005", "Salt fog", "The radar shall withstand exposure to salt fog per MIL-STD-810H, Method 509.7.", "T"],
             ["ENV-006", "Vibration", "The radar shall survive transportation vibration per MIL-STD-810H, Method 514.8.", "T"],
             ["ENV-007", "Rain", "The radar should operate in rainfall rates up to 50 mm/hr.", "D"]],
            [0.9 * inch, 1.35 * inch, 3.25 * inch, 0.7 * inch], req_col=2, id_col=0, keyword_of=keyword_of, font_size=9.5)
    b.heading("3.3 Design and construction.")
    b.para("3.3.1", "Materials.", [("Materials shall be selected to minimize weight as appropriate.", "shall")])
    b.para("3.3.2", "Maintainability.", [(
        "The mean time to repair (MTTR) shall not exceed 30 minutes at the organizational level, excluding time for "
        "fault isolation of intermittent failures, logistics delay time, and administrative delay time, when performed "
        "by personnel of the skill levels identified in the maintenance plan using only the standard tool kit and the "
        "technical manuals furnished with the radar.", "shall")])
    b.para("3.3.3", "Workmanship.", [("The contractor will ensure that all equipment is manufactured and finished in "
                                      "accordance with best commercial practice.", "will")])
    b.heading("4. VERIFICATION")
    b.para("4.1", "Verification methods.", [(
        "Verification of each requirement in section 3 shall be accomplished by inspection (I), analysis (A), "
        "demonstration (D), or test (T), as specified in TABLE III.", "shall")])
    b.table("TABLE III. Verification cross reference matrix.",
            [["Paragraph", "Title", "I", "A", "D", "T"],
             ["3.2.1.1", "Detection range", "", "", "", "X"], ["3.2.1.2", "Range accuracy", "", "X", "", "X"],
             ["3.2.1.3", "Operating modes", "", "", "X", ""], ["3.2.1.4", "Track capacity", "", "", "", "X"],
             ["3.2.2.1", "Weight", "X", "", "", ""], ["3.2.2.2", "Input power", "", "", "", "X"]],
            [1.1 * inch, 2.4 * inch, 0.55 * inch, 0.55 * inch, 0.55 * inch, 0.55 * inch], font_size=10)
    b.para("4.2", "Test reports.", [("Test reports must be delivered within 30 days after completion of each test.", "must")])
    b.heading("6. NOTES")
    b.para("6.1", "Intended use.", [("The radar is intended for ground-based air surveillance.", None)])

    def on_page(canvas, doc):
        if doc.page == 1:
            return
        canvas.setFont(FONTS["type"], 10)
        canvas.drawRightString(letter[0] - 0.9 * inch, letter[1] - 0.6 * inch, "SPEC-RDR-0042C")
        canvas.drawCentredString(letter[0] / 2, 0.55 * inch, str(doc.page))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                      topMargin=0.95 * inch, bottomMargin=0.9 * inch).build(b.story, onFirstPage=on_page, onLaterPages=on_page)
    b.gt.all_text += ["SPEC-RDR-0042C"]
    return buf.getvalue(), b.gt


# --------------------------------------------------------------------------------------
# Document B: Software Requirements Specification with bracketed IDs, borderless table
# --------------------------------------------------------------------------------------
def build_spec_b() -> tuple[bytes, GroundTruth]:
    body = ParagraphStyle("B", fontName=FONTS["serif"], fontSize=11.5, leading=15)
    head = ParagraphStyle("BH", parent=body, fontName=FONTS["sans_bold"], fontSize=12.5, leading=16)
    b = Builder("specB", body, head, body)
    b.heading("SOFTWARE REQUIREMENTS SPECIFICATION")
    b.heading("Ground Control Software (GCS)")
    b.heading("1 INTRODUCTION")
    b.heading("1.1 Purpose")
    b.plain("This Software Requirements Specification (SRS) defines the requirements for the Ground Control Software "
            "(GCS). Each requirement is identified by a unique identifier.")
    b.heading("3 REQUIREMENTS")
    b.heading("3.1 Functional Requirements")
    b.plain("[SRS-101] The GCS shall log all operator commands with a UTC time stamp.", "shall", "SRS-101",
            "The GCS shall log all operator commands with a UTC time stamp.")
    b.plain("[SRS-102] The GCS shall display vehicle telemetry within 250 ms of receipt.", "shall", "SRS-102",
            "The GCS shall display vehicle telemetry within 250 ms of receipt.")
    b.plain("SRS-103: When a telemetry link loss is detected, the GCS shall alert the operator within 2 seconds.",
            "shall", "SRS-103", "When a telemetry link loss is detected, the GCS shall alert the operator within 2 seconds.")
    b.stem_list("SRS-104:", "The GCS shall display the following status information:", "shall",
                [("\u2022", "Vehicle position"), ("\u2022", "Battery state of charge"), ("\u2022", "Data link quality")],
                doc_id="SRS-104", item_gap=3, indent=28)
    b.plain("SRS-105: While the GCS is in maintenance mode, the GCS shall inhibit all flight commands.", "shall",
            "SRS-105", "While the GCS is in maintenance mode, the GCS shall inhibit all flight commands.")
    diag, words = block_diagram(["OPERATOR", "GCS", "DATA LINK", "AIR VEHICLE"], FONTS["mono"], width=5.2 * inch)
    b.figure(diag, "Figure 3-1: GCS context diagram", words)
    b.heading("3.2 Performance Requirements")
    b.table("Table 3-1: Performance requirements",
            [["ID", "Requirement", "Priority"],
             ["PRF-201", "The GCS must process at least 100 telemetry messages per second.", "High"],
             ["PRF-202", "The GCS shall complete start-up in less than 60 seconds.", "Medium"],
             ["PRF-203", "The GCS should support up to 4 simultaneous vehicles.", "Low"]],
            [0.9 * inch, 4.4 * inch, 0.9 * inch], req_col=1, id_col=0, keyword_of=keyword_of, ruled=False, font_size=10.5)
    b.page_break()
    b.heading("3.3 Interface Requirements")
    for n, s in [("(1)", "The GCS shall communicate with the air vehicle using the STANAG 4586 message set."),
                 ("(2)", "The GCS shall export mission logs in comma-separated values (CSV) format."),
                 ("(3)", "The command data link shall be encrypted using AES-256.")]:
        b.story.append(b._p(f"{n} {s}", body, leftIndent=30, firstLineIndent=-30, spaceBefore=22))
        b.gt.all_text.append(f"{n} {s}")
        b.gt.requirements.append(GTReq(s, "shall", "list", n))
    b.spacer(10)
    b.heading("3.4 Security Requirements")
    b.plain("User passwords shall contain at least 12 characters and/or special characters. The GCS shall lock a user "
            "account after 5 consecutive failed login attempts, if possible.")
    b.gt.requirements += [GTReq("User passwords shall contain at least 12 characters and/or special characters.", "shall", "paragraph"),
                          GTReq("The GCS shall lock a user account after 5 consecutive failed login attempts, if possible.", "shall", "paragraph")]
    b.heading("3.5 Installation")
    b.plain("The GCS will be installed on government-furnished workstations.", "will")
    b.figure(photo_like(7), "Figure 3-2: Operator workstation", [])

    def on_page(canvas, doc):
        canvas.setFont(FONTS["serif"], 9.5)
        canvas.drawString(0.9 * inch, letter[1] - 0.55 * inch, "SRS-GCS-110 Rev A")
        canvas.drawRightString(letter[0] - 0.9 * inch, 0.5 * inch, f"Page {doc.page}")

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                      topMargin=0.9 * inch, bottomMargin=0.85 * inch).build(b.story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue(), b.gt


# --------------------------------------------------------------------------------------
# Document C: short interface control document; page 2 is a landscape table
# --------------------------------------------------------------------------------------
def build_spec_c() -> tuple[list[bytes], GroundTruth]:
    body = ParagraphStyle("C", fontName=FONTS["mono"], fontSize=10.5, leading=14)
    head = ParagraphStyle("CH", parent=body, fontName=FONTS["type_bold"])
    b = Builder("specC", body, head, body)
    b.heading("ICD-PWR-007 INTERFACE CONTROL DOCUMENT - POWER INTERFACE")
    b.heading("3. INTERFACE REQUIREMENTS")
    b.para("3.1", "Connector.", [("The power connector shall be a MIL-DTL-38999 Series III receptacle.", "shall")])
    b.para("3.2", "Pin assignments.", [("Pin assignments shall be as specified in Table 1.", "shall")])
    b.table("Table 1. Connector J1 pin assignments.",
            [["Pin", "Signal", "Wire Gauge"], ["A", "+28 VDC", "16 AWG"], ["B", "28 VDC RETURN", "16 AWG"],
             ["C", "CHASSIS GROUND", "18 AWG"], ["D", "SPARE", "-"]],
            [0.8 * inch, 2.6 * inch, 1.4 * inch], font_size=10.5)
    b.para("3.3", "Voltage limits.", [("The interface shall tolerate steady-state voltages from 22 VDC to 29 VDC.", "shall")])
    b.para("3.4", "Transients.", [("The equipment shall withstand voltage transients of 50 VDC for 12.5 ms.", "shall")])
    buf1 = io.BytesIO()
    SimpleDocTemplate(buf1, pagesize=letter, leftMargin=1 * inch, rightMargin=1 * inch).build(b.story)

    # landscape page (will be scanned sideways)
    b.story = []
    b.table("Table 2. Power quality requirements.",
            [["Req. No.", "Requirement", "Verification"],
             ["PQ-1", "Ripple voltage on the 28 VDC bus shall not exceed 1.5 V peak-to-peak.", "Test"],
             ["PQ-2", "Inrush current shall not exceed 20 A for more than 10 ms.", "Test"],
             ["PQ-3", "The equipment shall draw no more than 350 W in any operating mode.", "Analysis"]],
            [1.1 * inch, 5.8 * inch, 1.3 * inch], req_col=1, id_col=0, keyword_of=keyword_of, font_size=11)
    buf2 = io.BytesIO()
    SimpleDocTemplate(buf2, pagesize=landscape(letter)).build(b.story)
    return [buf1.getvalue(), buf2.getvalue()], b.gt


# --------------------------------------------------------------------------------------
# Document D: hard layout cases found in review (all must come out complete and in order)
# --------------------------------------------------------------------------------------
def build_spec_d() -> tuple[list[bytes], GroundTruth]:
    body = ParagraphStyle("D", fontName=FONTS["type"], fontSize=11, leading=14.5)
    head = ParagraphStyle("DH", parent=body, fontName=FONTS["type"])
    b = Builder("specD", body, head, body)
    b.heading("3. REQUIREMENTS")
    b.heading("3.1 Electrical and interfaces.")
    # a paragraph number followed by a sentence (not a heading), split over two lines
    b.broken_para(["3.1.1 The primary and secondary radar display units",
                   "shall operate from 28 VDC aircraft power."],
                  [("The primary and secondary radar display units shall operate from 28 VDC aircraft power.", "shall")], "3.1.1")
    # a quantity, a number and a designator at the start of wrapped lines
    b.broken_para(["3.1.2 Logic power. The regulated output voltage of",
                   "3.3 V shall be supplied to the logic card."],
                  [("The regulated output voltage of 3.3 V shall be supplied to the logic card.", "shall")], "3.1.2")
    b.broken_para(["3.1.3 Channels. The receiver shall provide a quantity of",
                   "12. The receiver shall acquire all channels within 45 s."],
                  [("The receiver shall provide a quantity of 12.", "shall"),
                   ("The receiver shall acquire all channels within 45 s.", "shall")], "3.1.3")
    b.broken_para(["3.1.4 Interface. The flight computer shall exchange data with",
                   "F-35 mission systems through the 1553B data bus."],
                  [("The flight computer shall exchange data with F-35 mission systems through the 1553B data bus.", "shall")], "3.1.4")
    # a unit abbreviation ending a sentence must not glue two requirements together
    b.broken_para(["3.1.5 Timing. The system shall respond within 100 ms. The",
                   "display shall update at 10 Hz."],
                  [("The system shall respond within 100 ms.", "shall"), ("The display shall update at 10 Hz.", "shall")], "3.1.5")
    b.plain("MK-54 torpedo tubes shall be inspected before loading.", "shall")
    b.para("3.1.6", "Harness.", [("The harness shall mate with connector (J3) and breaker (CB12).", "shall")])
    b.stem_list("3.1.7 Modes.", "The radar shall provide these modes:", "shall",
                [("(1)", "SEARCH MODE."), ("(2)", "TRACK MODE.")], doc_id="3.1.7")
    b.stem_list("3.1.8 Recording.", "The recorder shall record these parameters:", "shall",
                [("", "Barometric altitude."), ("", "True airspeed."), ("", "Magnetic heading.")], doc_id="3.1.8")
    # a paragraph that continues on the next page
    b.fill_page(2.6)
    b.para("3.1.9", "Warm-up.", [("The transmitter shall reach full rated output power within a period that shall not "
                                  "exceed 30 minutes after application of primary power, including the time required "
                                  "for the built-in test sequence to complete.", "shall")])
    b.heading("3.2 Power.")
    stem = "The unit shall accept the following inputs:"
    b.plain(f"3.2.1 Power. {stem}")
    b.list_item(stem, "shall", "a.", "115 VAC, 400 Hz, three phase, per MIL-STD-704F.", "3.2.1")
    b.fill_page(1.6)                                   # item b lands in the footer zone of the page
    b.list_item(stem, "shall", "b.", "28 VDC.", "3.2.1")
    b.page_break()
    b.heading("3.3 Displays.")
    stem = "The console shall provide the following:"
    b.plain(f"3.3.1 Displays. {stem}")
    b.list_item(stem, "shall", "a.", "Plan position indicator.", "3.3.1")
    diag, words = block_diagram(["DISPLAY", "KEYBOARD", "TRACKBALL"], FONTS["mono"], width=4.6 * inch, height=1.7 * inch)
    b.figure(diag, "FIGURE 2. Console layout.", words)
    b.list_item(stem, "shall", "b.", "Range height indicator.", "3.3.1")
    b.spacer(10)
    b.heading("3.4 Connectors.")
    # two tables with their captions BELOW, the first caption closer to the next table than usual
    b.table("TABLE IV. Connector J2 pin assignments.", [["Pin", "Signal"], ["1", "+28 VDC"], ["2", "RETURN"], ["3", "CHASSIS"]],
            [1.0 * inch, 2.2 * inch], caption_above=False, font_size=10, caption_space=(10, 7), space_after=0)
    b.table("TABLE V. Discrete signal levels.", [["Signal", "Low", "High"], ["READY", "0 V", "5 V"], ["FAULT", "0 V", "28 V"]],
            [1.2 * inch, 1.0 * inch, 1.0 * inch], caption_above=False, font_size=10, caption_space=(10, 7))
    # caption drawn inside the table frame + a cell merged over two rows
    # caption drawn inside the table frame, long enough to wrap onto a second line
    b.table("TABLE VI. Supply data for the equipment power interface at the aircraft connector.",
            [["Parameter", "Value", "Notes"], ["Voltage", "28 VDC", "See note 1."], ["Current", "5 A", ""],
             ["Power", "140 W", "Nominal rating."]],
            [1.4 * inch, 1.2 * inch, 2.0 * inch], caption_row=True, spans=[((2, 1), (2, 2))], font_size=10)
    b.page_break()
    b.heading("3.5 Software.")
    b.table("TABLE VII. Software requirements.",
            [["Req ID", "Shall Statement", "V&V"], ["SW-001", "The software shall start within 10 s.", "T"],
             ["SW-002", "The software shall log faults to non-volatile memory.", "I"]],
            [0.9 * inch, 4.2 * inch, 0.7 * inch], req_col=1, id_col=0, keyword_of=keyword_of, font_size=10)
    # a requirement table whose ID column is headed "Requirement ID" and that has a "Requirement Type" column
    b.table("TABLE VIII. Interface requirements.",
            [["Requirement ID", "Requirement Type", "Requirement Text", "Verification Method"],
             ["IRS-010", "Interface", "The unit shall accept MIL-STD-1553B bus commands.", "Test"],
             ["IRS-011", "Interface", "The unit shall report its status every 50 ms.", "Test"]],
            [1.1 * inch, 1.1 * inch, 2.6 * inch, 1.25 * inch], req_col=2, id_col=0, keyword_of=keyword_of, font_size=9)
    b.para("3.6", "Verification.", [("Compliance shall be verified as described in Section 10.2.", "shall")])

    # a handling notice printed in the footer of every page, with the page number on the same line
    notice = "Use or disclosure of this data shall be subject to the restriction on the title page."
    b.gt.requirements.append(GTReq(notice, "shall", "paragraph", ""))
    b.gt.all_text += ["SPEC-D-0099", notice]

    def on_page(canvas, doc, page_number=None):
        canvas.setFont(FONTS["type"], 10)
        canvas.drawRightString(letter[0] - 0.9 * inch, letter[1] - 0.5 * inch, "SPEC-D-0099")
        canvas.setFont(FONTS["type"], 9)
        canvas.drawString(1.0 * inch, 0.25 * inch, notice)
        canvas.drawRightString(letter[0] - 0.9 * inch, 0.25 * inch, str(page_number or doc.page))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                      topMargin=0.8 * inch, bottomMargin=0.55 * inch).build(b.story, onFirstPage=on_page, onLaterPages=on_page)

    # ---- a two-column page: wrapped designators, a full-width title-like line, numbered all-caps list items,
    #      double-spaced paragraphs next to single-spaced NOTES
    small = ParagraphStyle("D2", fontName=FONTS["type"], fontSize=10, leading=13)
    double = ParagraphStyle("D2dbl", parent=small, leading=26)
    b.body = small
    b.story = []
    b.heading("3.7 Installation.")
    b.broken_para(["3.7.1 Harness. The harness shall mate", "with connector J3 and circuit breaker",
                   "(CB12) before the first power-up."],
                  [("The harness shall mate with connector J3 and circuit breaker (CB12) before the first power-up.", "shall")],
                  "3.7.1")
    b.broken_para(["3.7.2 Radar Cross Section Measurement", "Error shall not exceed 1.5 dB at any", "aspect angle."],
                  [("Radar Cross Section Measurement Error shall not exceed 1.5 dB at any aspect angle.", "shall")], "3.7.2")
    b.stem_list("3.7.3 Modes.", "The radar shall provide these modes:", "shall",
                [("1.", "SEARCH MODE."), ("2.", "TRACK MODE.")], doc_id="3.7.3", indent=24)
    b.story.append(FrameBreak())                        # continue in the right-hand column
    b.body = double
    b.para("3.8", "Detection.", [("The radar shall detect a target with a radar cross section of 1 square meter at a "
                                  "range of not less than 150 km.", "shall")])
    b.body = small
    b.plain("NOTES:")
    for note in ("1. Values are nominal.", "2. Range is slant range.", "3. See TABLE VI for supply data.",
                 "4. Tolerances apply at 25 C."):
        b.plain(note)
    b.body = double
    b.para("3.9", "Tracking.", [("The radar shall maintain not less than 200 tracks while it continues to search the "
                                 "full volume.", "shall")])
    buf2 = io.BytesIO()
    margin, gutter = 0.75 * inch, 0.35 * inch
    col_w = (letter[0] - 2 * margin - gutter) / 2
    frames = [Frame(margin, 0.6 * inch, col_w, letter[1] - 1.4 * inch, id="left"),
              Frame(margin + col_w + gutter, 0.6 * inch, col_w, letter[1] - 1.4 * inch, id="right")]
    pages_before = len(pdfium.PdfDocument(buf.getvalue()))
    template = PageTemplate(id="two_columns", frames=frames,
                            onPage=lambda canvas, doc: on_page(canvas, doc, page_number=pages_before + doc.page))
    BaseDocTemplate(buf2, pagesize=letter, pageTemplates=[template]).build(b.story)
    return [buf.getvalue(), buf2.getvalue()], b.gt


# --------------------------------------------------------------------------------------
# Rasterize + degrade ("scan") the pages
# --------------------------------------------------------------------------------------
def rasterize(pdf_bytes: bytes, dpi: int) -> list[np.ndarray]:
    pdf = pdfium.PdfDocument(pdf_bytes)
    pages = [np.array(pdf[i].render(scale=dpi / 72, grayscale=True).to_pil().convert("L")) for i in range(len(pdf))]
    pdf.close()
    return pages


def _low_freq(shape, rng, sigma_px: float) -> np.ndarray:
    """Smooth random field in [0,1] (computed small then upscaled for speed)."""
    h, w = shape
    small = rng.random((max(4, h // 16), max(4, w // 16))).astype(np.float32)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, sigma_px / 16))
    big = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    return (big - big.min()) / (np.ptp(big) + 1e-6)


def degrade(gray: np.ndarray, p: dict, rng: np.random.Generator) -> np.ndarray:
    """Apply scanner/photocopier/fax style damage to a clean grayscale page (0=ink, 255=paper)."""
    ink = 255.0 - gray.astype(np.float32)
    if p.get("bleed"):                                  # ink spread -> thicker strokes
        ink = cv2.dilate(ink, np.ones((p["bleed"], p["bleed"]), np.uint8))
    if p.get("thin"):                                   # worn ribbon -> thinner strokes
        ink = cv2.erode(ink, np.ones((p["thin"], p["thin"]), np.uint8))
    if p.get("fade"):                                   # patchy fading of the ink
        ink *= p["fade"] + (1 - p["fade"]) * 0.6 * _low_freq(gray.shape, rng, 300)
    paper = float(p.get("paper", 255))
    img = paper - ink * (paper / 255.0)
    if p.get("paper_noise"):                            # paper texture / yellowing blotches
        img += (_low_freq(gray.shape, rng, 120) - 0.5) * p["paper_noise"]
    if p.get("illum"):                                  # uneven lighting (darker toward one corner)
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
    if p.get("dark_edges"):                             # photocopier lid shadow on the left/right edges
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


PROFILES = {
    "clean":     {},
    "scan":      {"paper": 244, "paper_noise": 10, "skew": 0.8, "blur": 0.7, "noise": 6, "jpeg": 55, "illum": 0.05},
    "photocopy": {"paper": 236, "paper_noise": 22, "bleed": 2, "fade": 0.55, "skew": -1.6, "blur": 1.0, "noise": 12,
                  "speckle": 0.0004, "dark_edges": 0.02, "punch_holes": True, "illum": 0.12, "jpeg": 45},
    "fax":       {"thin": 0, "skew": 1.1, "blur": 0.6, "noise": 18, "speckle": 0.0006},
}


def save_pdf(pages: list[np.ndarray], path: Path, dpi: int):
    ims = [Image.fromarray(p) for p in pages]
    ims[0].save(path, "PDF", resolution=dpi, save_all=True, append_images=ims[1:])


def save_tiff(pages: list[np.ndarray], path: Path, dpi: tuple[int, int], bilevel: bool = False):
    ims = []
    for p in pages:
        im = Image.fromarray(p)
        ims.append(im.point(lambda v: 255 if v > 150 else 0, mode="1") if bilevel else im)
    kw = {"compression": "group4"} if bilevel else {"compression": "tiff_lzw"}
    ims[0].save(path, save_all=True, append_images=ims[1:], dpi=dpi, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path(__file__).parent / "corpus"))
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    # ---- Document A -----------------------------------------------------------------
    pdf_a, gt_a = build_spec_a()
    (out / "specA_source_digital.pdf").write_bytes(pdf_a)          # the born-digital original, for reference
    pages300 = rasterize(pdf_a, 300)
    save_pdf(pages300, out / "specA_clean.pdf", 300)
    save_pdf([degrade(p, PROFILES["scan"], rng) for p in pages300], out / "specA_scan.pdf", 300)
    pages200 = rasterize(pdf_a, 200)
    save_tiff([degrade(p, PROFILES["photocopy"], rng) for p in pages200], out / "specA_photocopy.tif", (200, 200))
    (out / "specA_groundtruth.json").write_text(json.dumps(gt_a.to_json(), indent=2))

    # ---- Document B (page 2 scanned upside-down) -------------------------------------
    pdf_b, gt_b = build_spec_b()
    pages = [degrade(p, PROFILES["scan"], rng) for p in rasterize(pdf_b, 250)]
    if len(pages) > 1:
        pages[1] = np.rot90(pages[1], 2).copy()
    save_pdf(pages, out / "specB_scan.pdf", 250)
    pages = [degrade(p, PROFILES["photocopy"], rng) for p in rasterize(pdf_b, 200)]
    save_tiff(pages, out / "specB_photocopy.tif", (200, 200))
    (out / "specB_groundtruth.json").write_text(json.dumps(gt_b.to_json(), indent=2))

    # ---- Document C: bilevel G4 fax, 204x98 dpi, landscape page rotated 90 degrees ----
    (pdf_c1, pdf_c2), gt_c = build_spec_c()
    p1 = degrade(rasterize(pdf_c1, 204)[0], PROFILES["fax"], rng)
    p2 = np.rot90(degrade(rasterize(pdf_c2, 204)[0], PROFILES["fax"], rng), 1).copy()
    squash = lambda im: cv2.resize(im, (im.shape[1], int(round(im.shape[0] * 98 / 204))), interpolation=cv2.INTER_AREA)
    save_tiff([squash(p1), squash(p2)], out / "specC_fax.tif", (204, 98), bilevel=True)
    (out / "specC_groundtruth.json").write_text(json.dumps(gt_c.to_json(), indent=2))

    # ---- Document D: hard layout cases, office scan -------------------------------------
    pdfs_d, gt_d = build_spec_d()
    (out / "specD_source_digital.pdf").write_bytes(pdfs_d[0])
    pages_d = [page for pdf in pdfs_d for page in rasterize(pdf, 300)]
    save_pdf([degrade(p, PROFILES["scan"], rng) for p in pages_d], out / "specD_scan.pdf", 300)
    (out / "specD_groundtruth.json").write_text(json.dumps(gt_d.to_json(), indent=2))

    for f in sorted(out.iterdir()):
        print(f"{f.stat().st_size / 1e6:7.2f} MB  {f.name}")
    for gt in (gt_a, gt_b, gt_c, gt_d):
        print(f"{gt.doc}: {len(gt.requirements)} requirements, {len(gt.captions)} captions, {len(gt.tables)} tables")


if __name__ == "__main__":
    main()
