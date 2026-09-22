#!/usr/bin/env python3
"""
make_suite.py - render the tabbed-list acceptance pages and write expectations.json.

    python tests/list_suite/make_suite.py     (writes images/*.png and expectations.json next to this file;
                                               runner.py does this by itself when they are missing)

Every page is a synthetic scan of a specification page rendered with PIL:
  * 300 dpi, Liberation Mono 11 pt (typewriter) - pages p01-p05, p08
  * 200 dpi, Liberation Serif 12 pt (proportional) - pages p06, p07, p09
  * p10 is p01 run through a photocopier-style degradation (faded ink, speckle, skew, punch holes)

The list items are drawn the way the user describes them: a marker (a. / 1. / (a) / ...) then a LARGE
tab, a label ("Acceleration:"), another large tab, then a value that may run over several lines, the
continuation lines aligned under the value column. The expected Excel rows are generated from the same
case definitions that draw the page, so drawing and expectation cannot drift apart.

Expected-row convention (the one the tool already uses for an ordinary list, see
RequirementExtractor._list_items):
  Doc Ref  = '<paragraph number> <marker without ().>'   e.g. '3.2.4 a', '3.2.5 1', '3.6.1 b.1'
             a bullet item has no marker reference: Doc Ref = '<paragraph number>'
  Content  = '<stem sentence> <marker> <label> <value text>'   (label lines and value lines each joined by
             one space; for a nested item the parent's '<marker> <label>' comes before the child's part)
A stem with list items is NOT reported as a row of its own; only its items are.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
IMAGES = HERE / "images"
# Liberation fonts (Linux) or their metric-compatible Windows equivalents. The pages are compared by the
# text the tool reads, not pixel by pixel, so either font gives the same expected rows.
_FONT_CHOICES = {"mono": ["/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", "C:/Windows/Fonts/cour.ttf"],
                 "serif": ["/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf", "C:/Windows/Fonts/times.ttf"]}
FONT_FILES = {k: next((p for p in v if Path(p).exists()), v[0]) for k, v in _FONT_CHOICES.items()}
BULLETS = set("•●▪■‣⁃∙·◦*-o–—")


# =====================================================================================================================
# Page drawing
# =====================================================================================================================
class Page:
    def __init__(self, dpi: int, font: str, pt: float, pitch_in: float, margin_in: float = 1.0, top_in: float = 1.0):
        self.dpi, self.font_name = dpi, font
        self.W, self.H = int(8.5 * dpi), int(11 * dpi)
        self.font = ImageFont.truetype(FONT_FILES[font], round(pt / 72 * dpi))
        self.lh = round(pitch_in * dpi)
        self.L = round(margin_in * dpi)
        self.R = self.W - self.L
        self.img = Image.new("L", (self.W, self.H), 255)
        self.d = ImageDraw.Draw(self.img)
        self.y = round(top_in * dpi)
        self.col = (0.0, (self.R - self.L) / dpi)          # current column: (x offset, width) in inches

    def x(self, inch: float) -> int:
        return self.L + round((self.col[0] + inch) * self.dpi)

    def width(self, s: str) -> float:
        return self.font.getlength(s)

    def text(self, x_in: float, s: str):
        x = self.x(x_in)
        right = self.L + round((self.col[0] + self.col[1]) * self.dpi)
        if x + self.width(s) > right + 2:
            raise ValueError(f"text runs past the column edge by {x + self.width(s) - right:.0f} px: {s!r}")
        if self.y + self.lh > self.H - round(0.7 * self.dpi):
            raise ValueError(f"page overflow at {s!r}")
        self.d.text((x, self.y), s, font=self.font, fill=0)

    def newline(self, n: float = 1.0):
        self.y += round(n * self.lh)

    def wrap(self, text: str, x_in: float = 0.0) -> list:
        avail = self.col[1] * self.dpi - round(x_in * self.dpi)
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
        return lines

    def para(self, text: str, x_in: float = 0.0):
        for ln in self.wrap(text, x_in):
            self.text(x_in, ln)
            self.newline()

    def save(self, path: Path):
        self.img.save(path, dpi=(self.dpi, self.dpi))


def draw_items(pg: Page, items: list, xs: tuple, gap: float):
    """Draw 'marker <tab> label <tab> value' items; label and value columns may each run over several rows."""
    xm, xl, xv = xs
    for n, it in enumerate(items):
        if n:
            pg.newline(gap)
        labels, values = it.get("label", []), it.get("value", [])
        rows = max(1, len(labels), len(values))
        for k in range(rows):
            if k == 0:
                pg.text(xm, it["m"])
            if k < len(labels):
                pg.text(xl, labels[k])
            if k < len(values):
                pg.text(xv, values[k])
            pg.newline()
        if it.get("sub"):
            pg.newline(it.get("sub_gap", gap))
            draw_items(pg, it["sub"], it["sub_xs"], it.get("sub_gap", gap))


def expected_item_rows(para: str, stem: str, items: list, path: tuple = ()) -> list:
    rows = []
    for it in items:
        part = " ".join(x for x in (it["m"], " ".join(it.get("label", [])), " ".join(it.get("value", []))) if x)
        p = path + ((it["m"], part),)
        if it.get("sub"):
            rows += expected_item_rows(para, stem, it["sub"], p)
            continue
        marks = [m.strip("().") for m, _ in p if m and m not in BULLETS]
        ref = f"{para} {'.'.join(marks)}" if marks else para
        rows.append({"doc_ref": ref, "content": f"{stem} {' '.join(pt for _, pt in p)}", "stem": stem})
    return rows


def para_row(ref: str, sentence: str) -> dict:
    return {"doc_ref": ref, "content": sentence, "stem": ""}


# =====================================================================================================================
# Case drawing: lead-in paragraph + tabbed list + whatever follows
# =====================================================================================================================
def list_case(pg: Page, c: dict) -> dict:
    """c: name, format, lead (full paragraph text), para, stem, items, xs, gap, lead_gap, after (callables), after_rows"""
    pg.para(c["lead"])
    pg.newline(c.get("lead_gap", 0.6))
    draw_items(pg, c["items"], c["xs"], c.get("gap", 0.5))
    rows = expected_item_rows(c["para"], c["stem"], c["items"])
    for fn in c.get("after", []):
        fn(pg)
    rows += c.get("after_rows", [])
    pg.newline(c.get("case_gap", 1.2))
    return case_record(c, rows)


OCR_NOTES = {  # what PP-OCR (snapshot build) actually returns for these pages - see oracle.py
    "c.": "OCR reads the lone marker 'c.' as 'C.'; the Doc Ref must still be '<para> c' (the a, b, ?, d sequence "
          "says it is c).",
    "•": "OCR returns NO glyph for a bullet that stands alone (tested: bullet, -, *, en dash, middle dot, black "
         "circle), so these items have no visible marker and must be found from their label column under the stem.",
}


def case_record(c: dict, rows: list) -> dict:
    xs = c.get("xs", (0, None, 0))
    lone = ((xs[1] if xs[1] is not None else xs[2]) - xs[0]) >= 0.4      # marker set apart by a tab: its own OCR box
    marks = {it["m"] for it in c.get("items", [])} if lone else set()
    extra = [note for m, note in OCR_NOTES.items() if m in marks and note not in c.get("notes", "")]
    if extra:
        c = dict(c, notes=" ".join([c.get("notes", "")] + extra).strip())
    refs = sorted({r["doc_ref"].split()[0] for r in rows} | set(c.get("extra_refs", [])))
    rec = {"name": c["name"], "format": c["format"], "refs": refs, "expected_rows": rows}
    if "tables" in c:
        rec["tables"] = c["tables"]
    if c.get("notes"):
        rec["notes"] = c["notes"]
    return rec


def gap(n: float):
    return lambda pg: pg.newline(n)


def line(x: float, s: str):
    def f(pg):
        pg.text(x, s)
        pg.newline()
    return f


def paragraph(text: str):
    return lambda pg: pg.para(text)


def mono300() -> Page:
    return Page(300, "mono", 11, 0.19)


def serif200() -> Page:
    return Page(200, "serif", 12, 0.19)


# =====================================================================================================================
# The pages
# =====================================================================================================================
def page01(pg: Page) -> list:
    """The user's case: letters then numbers, marker / large tab / label / large tab / value."""
    cases = [list_case(pg, dict(
        name="p01_letters_tab_label", para="3.2.4",
        format="a./b./c./d. at 0.4in, label 'Xxx:' at 0.9in, value at 2.6in (tabs of ~0.4in and ~1in), "
               "values of 2 lines that start with numbers ('5 g', '20 Hz', '40 g', '-40 C', '2.5 C per minute'); "
               "lead-in ends 'each of the following:' and wraps onto a 2nd line; half-line gap between items; "
               "'c.' is the letter PP-OCR tends to read as 'C.'",
        lead="3.2.4 Environmental conditions. The equipment shall meet each of the following:",
        stem="The equipment shall meet each of the following:",
        xs=(0.4, 0.9, 2.6), gap=0.5,
        items=[dict(m="a.", label=["Acceleration:"], value=["5 g in each of the three orthogonal axes",
                                                             "for 1 minute per axis."]),
               dict(m="b.", label=["Vibration:"], value=["20 Hz to 2000 Hz random, 0.04 g2/Hz,",
                                                          "3 hours per axis, 7.7 g rms overall."]),
               dict(m="c.", label=["Shock:"], value=["40 g, 11 ms half-sine pulse,", "3 shocks in each direction."]),
               dict(m="d.", label=["Temperature:"], value=["-40 C to +71 C operating,",
                                                            "2.5 C per minute maximum rate of change."])],
        notes="")),
        list_case(pg, dict(
            name="p01_numbered_within_limits", para="3.2.5",
            format="1./2./3./4. at 0.4in, label at 0.9in, value at 2.6in; lead-in WITHOUT colon "
                   "'... within the following limits.'; value lines start with '24 to', '1.5 V peak-to-peak', "
                   "'3.2 A continuous', '150 W'; list followed by the next numbered paragraph 3.2.6",
            lead="3.2.5 Electrical conditions. The equipment shall operate within the following limits.",
            stem="The equipment shall operate within the following limits.",
            xs=(0.4, 0.9, 2.6), gap=0.5,
            items=[dict(m="1.", label=["Input voltage:"], value=["24 to 32 VDC, 28 VDC nominal."]),
                   dict(m="2.", label=["Ripple:"], value=["1.5 V peak-to-peak maximum,", "10 Hz to 50 kHz."]),
                   dict(m="3.", label=["Current:"], value=["3.2 A continuous, 4.0 A peak."]),
                   dict(m="4.", label=["Power:"], value=["150 W maximum at 28 VDC."])],
            after=[gap(0.6), paragraph("3.2.6 Weight. The equipment shall not exceed 45 kilograms.")],
            after_rows=[para_row("3.2.6", "The equipment shall not exceed 45 kilograms.")]))]
    return cases


def page02(pg: Page) -> list:
    return [list_case(pg, dict(
        name="p02_paren_letters_no_colon_labels_very_large_tab", para="3.3.1",
        format="(a)-(d) at 0.4in, labels WITHOUT ':' at 1.0in, value at 3.2in (very large tab ~1.4-2in); "
               "lead-in 'as follows:'; a full blank line between items; values start with '9.3 GHz', '25 kW', "
               "'0.5 us', '0.1 percent'",
        lead="3.3.1 Transmitter. The transmitter output shall be as follows:",
        stem="The transmitter output shall be as follows:",
        xs=(0.4, 1.0, 3.2), gap=1.0,
        items=[dict(m="(a)", label=["Frequency"], value=["9.3 GHz to 9.5 GHz, tunable", "in 10 MHz steps."]),
               dict(m="(b)", label=["Peak power"], value=["25 kW minimum."]),
               dict(m="(c)", label=["Pulse width"], value=["0.5 us, 1.0 us or 2.0 us,", "selectable by the operator."]),
               dict(m="(d)", label=["Duty cycle"], value=["0.1 percent maximum."])])),
        list_case(pg, dict(
            name="p02_paren_numbers_small_tabs_tight", para="3.3.2",
            format="(1)-(4) at 0.4in, label at 0.8in (small tab after the marker), value tab at 2.3in (only "
                   "~2-4 characters after the longest label); lead-in 'as specified below.' (no colon); "
                   "no gap between items",
            lead="3.3.2 Receiver. The receiver shall have the characteristics as specified below.",
            stem="The receiver shall have the characteristics as specified below.",
            xs=(0.4, 0.8, 2.3), gap=0.0,
            items=[dict(m="(1)", label=["Noise figure:"], value=["3.5 dB maximum."]),
                   dict(m="(2)", label=["Sensitivity:"], value=["-110 dBm minimum for 10 dB",
                                                                 "signal-to-noise ratio."]),
                   dict(m="(3)", label=["Bandwidth:"], value=["1.2 MHz between 3 dB points."]),
                   dict(m="(4)", label=["Dynamic range:"], value=["70 dB minimum."])])),
        list_case(pg, dict(
            name="p02_close_paren_numbers", para="3.3.3",
            format="1)-4) at 0.4in, label at 0.9in, value at 2.6in; lead-in ends 'the following.' (no colon); "
                   "value lines start with '32 dBi', '2.5 degrees', '-25 dB', '1.5:1'",
            lead="3.3.3 Antenna. The antenna shall conform to the following.",
            stem="The antenna shall conform to the following.",
            xs=(0.4, 0.9, 2.6), gap=0.5,
            items=[dict(m="1)", label=["Gain:"], value=["32 dBi minimum at 9.4 GHz."]),
                   dict(m="2)", label=["Beamwidth:"], value=["2.5 degrees maximum in both",
                                                              "azimuth and elevation."]),
                   dict(m="3)", label=["Sidelobes:"], value=["-25 dB maximum relative to",
                                                              "the main beam peak."]),
                   dict(m="4)", label=["VSWR:"], value=["1.5:1 maximum over the band."])],
            after=[gap(0.6), paragraph("3.3.4 Radome. The radome shall not reduce antenna gain by more than 1 dB.")],
            after_rows=[para_row("3.3.4", "The radome shall not reduce antenna gain by more than 1 dB.")]))]


def page03(pg: Page) -> list:
    return [list_case(pg, dict(
        name="p03_roman_dot", para="3.4.1",
        format="i./ii./iii./iv. at 0.4in, label at 1.0in, value at 2.8in; lead-in 'the following.' (no colon); "
               "2-line values",
        lead="3.4.1 Built-in test. The BIT function shall perform the following.",
        stem="The BIT function shall perform the following.",
        xs=(0.4, 1.0, 2.8), gap=0.5,
        items=[dict(m="i.", label=["Power-up:"], value=["Full test at power-on, completed", "within 30 seconds."]),
               dict(m="ii.", label=["Periodic:"], value=["Non-interfering test every", "60 seconds in operation."]),
               dict(m="iii.", label=["Initiated:"], value=["Full test started by the operator."]),
               dict(m="iv.", label=["Isolation:"], value=["To one LRU with 95 percent",
                                                           "probability of correct isolation."])])),
        list_case(pg, dict(
            name="p03_paren_roman", para="3.4.2",
            format="(i)/(ii)/(iii) at 0.4in, label at 1.0in, value at 2.6in; lead-in ends ':'",
            lead="3.4.2 Status reporting. The equipment shall report the following status data:",
            stem="The equipment shall report the following status data:",
            xs=(0.4, 1.0, 2.6), gap=0.5,
            items=[dict(m="(i)", label=["Mode:"], value=["Current operating mode."]),
                   dict(m="(ii)", label=["Faults:"], value=["Active faults with time tags",
                                                             "to the nearest 1 second."]),
                   dict(m="(iii)", label=["Hours:"], value=["Elapsed operating hours."])])),
        list_case(pg, dict(
            name="p03_capital_letters", para="3.4.3",
            format="A./B./C./D. (capital letters) at 0.4in, label at 1.0in, value at 3.0in; lead-in "
                   "'within the following limits:' wrapped over 2 lines; values start with '2.5 kg/min', "
                   "'15 C', '1.2 kPa', '5 to 95'; followed by sub-paragraph 3.4.3.1",
            lead="3.4.3 Cooling. The cooling air supplied to the equipment shall be within the following limits:",
            stem="The cooling air supplied to the equipment shall be within the following limits:",
            xs=(0.4, 1.0, 3.0), gap=0.5,
            items=[dict(m="A.", label=["Flow rate:"], value=["2.5 kg/min minimum."]),
                   dict(m="B.", label=["Inlet temperature:"], value=["15 C to 35 C."]),
                   dict(m="C.", label=["Pressure drop:"], value=["1.2 kPa maximum at", "the rated flow."]),
                   dict(m="D.", label=["Humidity:"], value=["5 to 95 percent, non-condensing."])],
            after=[gap(0.6), paragraph("3.4.3.1 Coolant. The coolant shall be dry, filtered air.")],
            after_rows=[para_row("3.4.3.1", "The coolant shall be dry, filtered air.")],
            notes="Capital-letter markers are not list markers for the snapshot; the convention gives '3.4.3 A'. "
                  "The list is followed by the CHILD paragraph 3.4.3.1 (a valid next number after 3.4.3)."))]


def page04(pg: Page) -> list:
    return [list_case(pg, dict(
        name="p04_bullets_label", para="3.5.1",
        format="bullets at 0.4in, upper-case label at 0.8in, value at 2.4in; lead-in ':'",
        lead="3.5.1 Indicators. The front panel shall provide the following indicators:",
        stem="The front panel shall provide the following indicators:",
        xs=(0.4, 0.8, 2.4), gap=0.5,
        items=[dict(m="•", label=["POWER:"], value=["Green, lit when primary", "power is applied."]),
               dict(m="•", label=["FAULT:"], value=["Red, lit when BIT detects a fault."]),
               dict(m="•", label=["STANDBY:"], value=["Amber, lit in standby mode."])],
        notes="Bullet items carry no marker reference: every row has Doc Ref '3.5.1' (snapshot convention).")),
        list_case(pg, dict(
            name="p04_no_label_1_to_4_lines", para="3.5.2",
            format="a.-d. at 0.4in, NO label column, value at 1.2in (large tab); values of 2, 1, 4 and 2 lines; "
                   "continuation lines start with '10 Mbit/s' and 'system time.'; item c contains a second "
                   "'shall' sentence",
            lead="3.5.2 Data recording. The recorder shall meet each of the following:",
            stem="The recorder shall meet each of the following:",
            xs=(0.4, None, 1.2), gap=0.5,
            items=[dict(m="a.", value=["Record all bus traffic at data rates up to",
                                       "10 Mbit/s without loss of data."]),
                   dict(m="b.", value=["Store not less than 8 hours of data."]),
                   dict(m="c.", value=["Time-tag each message to within 1 ms of",
                                       "system time. Time tags shall be derived",
                                       "from the GPS time source when available",
                                       "and from the internal clock otherwise."]),
                   dict(m="d.", value=["Retain recorded data for 30 days",
                                       "without external power."])])),
        list_case(pg, dict(
            name="p04_label_wraps_two_lines", para="3.5.3",
            format="a.-c. at 0.4in, label at 0.9in that WRAPS onto a 2nd line ('Storage' / 'temperature:'), "
                   "value at 2.6in over 2 lines beside it; expected text reads the label column first, then "
                   "the value column",
            lead="3.5.3 Storage. The equipment shall not be damaged by storage in the following conditions:",
            stem="The equipment shall not be damaged by storage in the following conditions:",
            xs=(0.4, 0.9, 2.6), gap=0.5,
            items=[dict(m="a.", label=["Storage", "temperature:"], value=["-55 C to +85 C for", "up to 5 years."]),
                   dict(m="b.", label=["Relative", "humidity:"], value=["Up to 100 percent,",
                                                                         "including condensation."]),
                   dict(m="c.", label=["Altitude:"], value=["Up to 12,200 m (40,000 ft)."])],
            after=[gap(0.6), paragraph("3.5.4 Transport. The packaged equipment shall withstand transport by "
                                       "road, rail, sea and air.")],
            after_rows=[para_row("3.5.4", "The packaged equipment shall withstand transport by road, rail, "
                                          "sea and air.")]))]


def page05(pg: Page) -> list:
    return [list_case(pg, dict(
        name="p05_nested_sublist", para="3.6.1",
        format="a./b./c. at 0.4in, label at 0.9in, value at 2.6in; item b. 'Random:' has no value and a nested "
               "(1)/(2) sub-list under the label column (marker 0.9in, label 1.4in, value 3.0in)",
        lead="3.6.1 Vibration. The equipment shall withstand the following vibration environments:",
        stem="The equipment shall withstand the following vibration environments:",
        xs=(0.4, 0.9, 2.6), gap=0.5,
        items=[dict(m="a.", label=["Sinusoidal:"], value=["5 Hz to 500 Hz, 2 g peak,", "1 octave per minute."]),
               dict(m="b.", label=["Random:"], sub_xs=(0.9, 1.4, 3.0), sub_gap=0.5,
                    sub=[dict(m="(1)", label=["Functional:"], value=["20 Hz to 2000 Hz, 0.04 g2/Hz,",
                                                                      "1 hour per axis."]),
                         dict(m="(2)", label=["Endurance:"], value=["20 Hz to 2000 Hz, 0.1 g2/Hz,",
                                                                     "3 hours per axis."])]),
               dict(m="c.", label=["Transport:"], value=["As specified in MIL-STD-810H,",
                                                          "Method 514.8, Procedure II."])])),
        list_case(pg, dict(
            name="p05_decimal_values_then_caps_heading", para="3.6.2",
            format="1./2./3. at 0.4in, label at 0.9in, value at 2.6in, NO gap between items (tight); every value "
                   "line starts with a dotted decimal and a capital unit ('9.0 G', '2.5 G', '3.2 G'); the 1st "
                   "value line ENDS with '.' and the next starts with a number; the list is followed by the "
                   "all-caps heading '4. QUALITY ASSURANCE PROVISIONS' (4 would continue 1, 2, 3!) and 4.1",
            lead="3.6.2 Crash safety. The equipment shall remain attached to its mounting under the following "
                 "loads:",
            stem="The equipment shall remain attached to its mounting under the following loads:",
            xs=(0.4, 0.9, 2.6), gap=0.0,
            items=[dict(m="1.", label=["Forward:"], value=["9.0 G for 3 seconds.", "2.5 G sustained thereafter."]),
                   dict(m="2.", label=["Lateral:"], value=["3.0 G in either direction.",
                                                            "1.5 G sustained thereafter."]),
                   dict(m="3.", label=["Vertical:"], value=["6.0 G down and 2.0 G up.", "3.2 G down sustained."])],
            after=[gap(1.2), line(0, "4. QUALITY ASSURANCE PROVISIONS"), gap(0.6),
                   paragraph("4.1 Responsibility for inspection. The contractor shall be responsible for the "
                             "performance of all inspection requirements.")],
            after_rows=[para_row("4.1", "The contractor shall be responsible for the performance of all "
                                        "inspection requirements.")]))]


def page06(pg: Page) -> list:
    return [list_case(pg, dict(
        name="p06_serif_letters_marker_at_margin", para="3.7.1",
        format="SERIF 200dpi. a.-d. at the LEFT MARGIN, label at 0.5in, value at 2.2in; lead-in ':' wrapped "
               "over 2 lines; item a. has a 3-line value whose lines start '-40 C', '-55 C', '5 C per minute'; "
               "other values start with 'Sea level', '95 percent', '48 hours'",
        lead="3.7.1 Environmental conditions. The equipment shall meet all performance requirements when "
             "exposed to each of the following environments:",
        stem="The equipment shall meet all performance requirements when exposed to each of the following "
             "environments:",
        xs=(0.0, 0.5, 2.2), gap=0.5,
        items=[dict(m="a.", label=["Temperature:"], value=["-40 C to +71 C operating,",
                                                            "-55 C to +85 C non-operating,",
                                                            "5 C per minute maximum rate of change."]),
               dict(m="b.", label=["Altitude:"], value=["Sea level to 15,000 m."]),
               dict(m="c.", label=["Humidity:"], value=["95 percent relative humidity for 10 days,",
                                                         "including condensation."]),
               dict(m="d.", label=["Salt fog:"], value=["48 hours exposure, 5 percent solution."])])),
        list_case(pg, dict(
            name="p06_serif_numbered_wrapped_leadin_no_colon", para="3.7.2",
            format="SERIF 200dpi. 1.-4. at 0.3in, label at 0.7in, value at 2.2in; lead-in WITHOUT colon "
                   "'... within the following limits.' wrapped over 2 lines; value line ending '.' followed by "
                   "a line starting '4.5 A'; followed by the next numbered paragraph 3.7.3",
            lead="3.7.2 Electrical interface. The equipment shall accept primary power from the aircraft bus "
                 "within the following limits.",
            stem="The equipment shall accept primary power from the aircraft bus within the following limits.",
            xs=(0.3, 0.7, 2.2), gap=0.5,
            items=[dict(m="1.", label=["Voltage:"], value=["22 VDC to 29 VDC,", "28 VDC nominal."]),
                   dict(m="2.", label=["Ripple:"], value=["1.5 V peak-to-peak maximum."]),
                   dict(m="3.", label=["Current:"], value=["3.2 A continuous.", "4.5 A peak for 100 ms."]),
                   dict(m="4.", label=["Inrush:"], value=["12 A for 10 ms maximum."])],
            after=[gap(0.6), paragraph("3.7.3 Grounding. The equipment case shall be bonded to structure with a "
                                       "resistance not exceeding 2.5 milliohms.")],
            notes="OCR (serif, 200 dpi) does not return the lone marker '4.' of 'Inrush' at all: the Doc Ref "
                  "'3.7.2 4' can only come from the 1, 2, 3 sequence and the label column (the Content may lack "
                  "'4.' and still pass).",
            after_rows=[para_row("3.7.3", "The equipment case shall be bonded to structure with a resistance not "
                                          "exceeding 2.5 milliohms.")]))]


def page07(pg: Page) -> list:
    return [list_case(pg, dict(
        name="p07_serif_paren_letters_within_limits", para="3.7.4",
        format="SERIF 200dpi. (a)-(c) at 0.4in, label at 0.9in, value at 2.4in; lead-in WITHOUT colon "
               "'within the following limits.'; values start with '15 C', '2.5 kg/min', '1.2 kPa'; (b) has a "
               "4-line value whose 2nd line ENDS with '.' and whose 3rd and 4th lines start '3.0 kg/min', '3,000 m'",
        lead="3.7.4 Cooling air. The equipment shall operate with cooling air within the following limits.",
        stem="The equipment shall operate with cooling air within the following limits.",
        xs=(0.4, 0.9, 2.4), gap=0.5,
        items=[dict(m="(a)", label=["Temperature:"], value=["15 C to 35 C at the inlet."]),
               dict(m="(b)", label=["Flow:"], value=["2.5 kg/min minimum per kW of",
                                                      "dissipated power at sea level.",
                                                      "3.0 kg/min per kW above",
                                                      "3,000 m altitude."]),
               dict(m="(c)", label=["Pressure:"], value=["1.2 kPa maximum drop across", "the equipment at rated flow."])])),
        list_case(pg, dict(
            name="p07_serif_label_wraps", para="3.7.5",
            format="SERIF 200dpi. a.-c. at 0.4in, 2-line labels at 0.9in ('Maximum' / 'weight:'), value at 2.4in; "
                   "lead-in ':'",
            lead="3.7.5 Mechanical. The equipment shall meet the following:",
            stem="The equipment shall meet the following:",
            xs=(0.4, 0.9, 2.4), gap=0.5,
            items=[dict(m="a.", label=["Maximum", "weight:"], value=["12.5 kg including the", "mounting tray."]),
                   dict(m="b.", label=["Envelope", "dimensions:"], value=["300 mm x 200 mm x 150 mm",
                                                                           "maximum, excluding connectors."]),
                   dict(m="c.", label=["Center of", "gravity:"], value=["Within 25 mm of the",
                                                                         "geometric center."])])),
        list_case(pg, dict(
            name="p07_serif_bullets", para="3.7.6",
            format="SERIF 200dpi. bullets at 0.4in, label at 0.7in, value at 2.2in; lead-in ':'; followed by "
                   "the next numbered paragraph 3.7.7",
            lead="3.7.6 Connectors. The equipment shall use the following connectors:",
            stem="The equipment shall use the following connectors:",
            xs=(0.4, 0.7, 2.2), gap=0.5,
            items=[dict(m="•", label=["Power (J1):"], value=["MIL-DTL-38999 Series III, size 13."]),
                   dict(m="•", label=["Data (J2):"], value=["MIL-DTL-38999 Series III, size 15."]),
                   dict(m="•", label=["RF (J3):"], value=["TNC, 50 ohm."])],
            after=[gap(0.6), paragraph("3.7.7 Bonding. Each connector shall be bonded to the equipment case.")],
            notes=OCR_NOTES["•"],
            after_rows=[para_row("3.7.7", "Each connector shall be bonded to the equipment case.")]))]


def page08(pg: Page) -> list:
    """CONTROLS: ordinary tight lists and a borderless table with real columns."""
    cases = [list_case(pg, dict(
        name="p08_control_tight_letters", para="3.8.1",
        format="CONTROL. ordinary tight list 'a. Search mode.' (marker + one space, no tabs, no gap)",
        lead="3.8.1 Operating modes. The radar shall provide the following operating modes:",
        stem="The radar shall provide the following operating modes:",
        xs=(0.4, None, 0.7), gap=0.0,
        items=[dict(m="a.", value=["Search mode."]), dict(m="b.", value=["Track mode."]),
               dict(m="c.", value=["Built-in test mode."])])),
        list_case(pg, dict(
            name="p08_control_tight_numbered_wrapping", para="3.8.2",
            format="CONTROL. ordinary tight numbered list, item 4 wraps onto a 2nd line aligned with its text",
            lead="3.8.2 Display data. The display shall show the following data:",
            stem="The display shall show the following data:",
            xs=(0.4, None, 0.7), gap=0.0,
            items=[dict(m="1.", value=["Target range to the nearest 0.1 nmi."]),
                   dict(m="2.", value=["Target bearing to the nearest 1 degree."]),
                   dict(m="3.", value=["Own-ship heading."]),
                   dict(m="4.", value=["Track quality, shown as a number from 1 to 7 for",
                                       "each track held by the radar."])]))]
    # borderless table with real columns
    pg.para("3.8.3 Serial interface. The serial interface shall have the characteristics listed in TABLE I.")
    pg.newline(0.8)
    pg.text(1.8, "TABLE I. Serial interface characteristics.")
    pg.newline(2.0)
    table = [("Parameter", "Value", "Unit"), ("Data rate", "9600", "bit/s"), ("Data bits", "8", "bits"),
             ("Stop bits", "1", "bits"), ("Parity", "even", "n/a"), ("Flow control", "none", "n/a"),
             ("Voltage level", "RS-422", "n/a")]
    for r, row in enumerate(table):
        for x, cell in zip((0.8, 2.8, 4.2), row):
            pg.text(x, cell)
        pg.newline(1.4 if r == 0 else 1.2)
    pg.newline(0.8)
    pg.para("3.8.4 Connector. The serial interface connector shall be a 9-pin D-subminiature connector.")
    cases.append(case_record(dict(
        name="p08_control_borderless_table",
        format="CONTROL. paragraph, caption 'TABLE I.', borderless 3-column table (header Parameter/Value/Unit + "
               "6 rows, columns 1.4-2in apart, no ruling at all), then paragraph 3.8.4",
        tables=1,
        notes="Right result: two paragraph requirements and ONE Table item (Type 'Table'); the table rows must "
              "not become list items or requirements."),
        [para_row("3.8.3", "The serial interface shall have the characteristics listed in TABLE I."),
         para_row("3.8.4", "The serial interface connector shall be a 9-pin D-subminiature connector.")]))
    return cases


def page09(pg: Page) -> list:
    """CONTROL: two-column prose page (serif 200 dpi) with a tight list in the left column."""
    pg.text(0, "3.9 Construction.")
    pg.newline(1.5)
    top = pg.y
    gutter, colw = 0.4, (pg.R - pg.L) / pg.dpi / 2 - 0.2
    pg.col = (0.0, colw)
    pg.para("3.9.1 Materials. Materials shall be free of defects which would adversely affect the performance "
            "or maintainability of the equipment.")
    pg.newline(0.8)
    pg.para("3.9.2 Marking. Each unit shall be marked with the following information:")
    pg.newline(0.4)
    for m, t in (("a.", "Part number."), ("b.", "Serial number."), ("c.", "Manufacturer's CAGE code.")):
        pg.text(0.25, m)
        pg.text(0.5, t)
        pg.newline()
    pg.newline(0.8)
    pg.para("3.9.3 Workmanship. The equipment shall be fabricated and finished so that it is free of burrs, "
            "sharp edges and loose parts.")
    pg.y = top
    pg.col = (colw + gutter, colw)
    pg.para("3.9.4 Interchangeability. All parts having the same part number shall be directly and completely "
            "interchangeable with each other.")
    pg.newline(0.8)
    pg.para("3.9.5 Finish. External surfaces shall be painted in accordance with the approved finish "
            "specification for the equipment.")
    pg.newline(0.8)
    pg.para("3.9.6 Fasteners. Threaded fasteners shall be secured against loosening by an approved locking "
            "method.")
    stem = "Each unit shall be marked with the following information:"
    rows = [para_row("3.9.1", "Materials shall be free of defects which would adversely affect the performance or "
                              "maintainability of the equipment."),
            {"doc_ref": "3.9.2 a", "content": f"{stem} a. Part number.", "stem": stem},
            {"doc_ref": "3.9.2 b", "content": f"{stem} b. Serial number.", "stem": stem},
            {"doc_ref": "3.9.2 c", "content": f"{stem} c. Manufacturer's CAGE code.", "stem": stem},
            para_row("3.9.3", "The equipment shall be fabricated and finished so that it is free of burrs, sharp "
                              "edges and loose parts."),
            para_row("3.9.4", "All parts having the same part number shall be directly and completely "
                              "interchangeable with each other."),
            para_row("3.9.5", "External surfaces shall be painted in accordance with the approved finish "
                              "specification for the equipment."),
            para_row("3.9.6", "Threaded fasteners shall be secured against loosening by an approved locking method.")]
    return [case_record(dict(
        name="p09_control_two_column_prose",
        format="CONTROL. SERIF 200dpi two-column page (0.4in gutter): left column 3.9.1-3.9.3 with a tight "
               "a./b./c. list, right column 3.9.4-3.9.6; reading order = whole left column, then right column",
        notes="Right result: 8 rows in column order; nothing from the right column is joined to the left."), rows)]


# ---- photocopy damage (same as tests/make_test_corpus.py degrade(), copied so this script stands alone) -------------
def _low_freq(shape, rng, sigma_px: float) -> np.ndarray:
    h, w = shape
    small = rng.random((max(4, h // 16), max(4, w // 16))).astype(np.float32)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, sigma_px / 16))
    big = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    return (big - big.min()) / (np.ptp(big) + 1e-6)


def degrade(gray: np.ndarray, p: dict, rng: np.random.Generator) -> np.ndarray:
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


# the tests/make_test_corpus.py "photocopy" profile, a little lighter so the words stay readable: this page tests
# the list layout under photocopy damage, not the recogniser
PHOTOCOPY = {"paper": 238, "paper_noise": 18, "bleed": 2, "fade": 0.6, "skew": -1.3, "blur": 0.9, "noise": 10,
             "speckle": 0.0004, "dark_edges": 0.015, "punch_holes": True, "illum": 0.10, "jpeg": 50}

PAGES = [
    ("p01_main_mono300.png", mono300, page01),
    ("p02_markers_mono300.png", mono300, page02),
    ("p03_markers_mono300.png", mono300, page03),
    ("p04_layout_mono300.png", mono300, page04),
    ("p05_nested_mono300.png", mono300, page05),
    ("p06_serif200.png", serif200, page06),
    ("p07_serif200.png", serif200, page07),
    ("p08_controls_mono300.png", mono300, page08),
    ("p09_twocol_serif200.png", serif200, page09),
]


def main():
    IMAGES.mkdir(parents=True, exist_ok=True)
    out = {"about": __doc__.strip(), "pages": []}
    for fname, make_page, fill in PAGES:
        pg = make_page()
        cases = fill(pg)
        pg.save(IMAGES / fname)
        out["pages"].append({"image": f"images/{fname}", "dpi": pg.dpi, "font": pg.font_name, "cases": cases})
        if fname.startswith("p01_"):
            rng = np.random.default_rng(20260922)
            bad = degrade(np.array(pg.img), PHOTOCOPY, rng)
            Image.fromarray(bad).save(IMAGES / "p10_main_photocopy300.png", dpi=(300, 300))
            copy = json.loads(json.dumps(cases))
            for c in copy:
                c["name"] = c["name"].replace("p01_", "p10_photocopy_")
                c["format"] = "PHOTOCOPY-degraded copy of p01 (faded ink, speckle, -1.3 deg skew, punch holes). " + c["format"]
            photocopy = {"image": "images/p10_main_photocopy300.png", "dpi": 300, "font": "mono", "cases": copy}
    out["pages"].append(photocopy)
    (HERE / "expectations.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    n = sum(len(p["cases"]) for p in out["pages"])
    print(f"{len(out['pages'])} pages, {n} cases -> {HERE / 'expectations.json'}")


if __name__ == "__main__":
    main()
