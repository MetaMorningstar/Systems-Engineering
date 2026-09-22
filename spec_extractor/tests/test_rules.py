#!/usr/bin/env python3
"""
test_rules.py - fast checks of the layout and requirement rules (no OCR, runs in seconds).

    python tests/test_rules.py          (or:  python -m pytest tests/test_rules.py)

Each test builds OCR "lines" with realistic page geometry, runs them through the same steps as a
real document (layout -> document clean-up -> requirement extraction) and checks the rows.
The cases come from an independent review of the tool: every one of them used to lose, split,
merge or mislabel a requirement. Run this after ANY change to the rules; run
tests/run_regression.py as well after changes to OCR, image clean-up or table detection.
"""
from __future__ import annotations

import logging
import re
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import spec_extractor as se  # noqa: E402

logging.basicConfig(level=logging.ERROR)

# ---- page geometry: US letter at 220 dpi, 10-12 pt typewriter text ------------------------------------------------
DPI = 220
PAGE_W, PAGE_H = int(8.5 * DPI), int(11 * DPI)
CHAR_W, TEXT_H, PITCH = 15, 30, 48      # character width, text height, line pitch (pixels)
LEFT = 220                              # 1 inch margin


def make_line(text: str, x0: int = LEFT, y0: int = 300, conf: float = 0.98, height: int = TEXT_H) -> se.Line:
    """One OCR line with one box per word (monospaced geometry)."""
    words, x = [], x0
    for token in text.split(" "):
        if not token:
            x += CHAR_W
            continue
        w = len(token) * CHAR_W
        words.append(se.Word(token, conf, (x, y0, x + w, y0 + height)))
        x += w + CHAR_W
    return se.Line(text, conf, (x0, y0, words[-1].box[2], y0 + height), words)


def make_lines(rows: list, y0: int = 300, x0: int = LEFT) -> list:
    """rows: text, (indent_px, text), or None for a blank line."""
    out, y = [], y0
    for row in rows:
        if row is not None:
            indent, text = row if isinstance(row, tuple) else (0, row)
            out.append(make_line(text, x0 + indent, y))
        y += PITCH
    return out


def settings(**changes) -> se.Settings:
    s = se.Settings()
    s.detect_tables = False            # these tests give the layout step text only
    s.borderless_tables = False
    for key, value in changes.items():
        setattr(s, key, value)
    se.configure_keywords(s.keywords)
    return s


def blank_page() -> se.PreparedPage:
    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    return se.PreparedPage(img, img.copy(), float(DPI))


def run(pages: dict, s: se.Settings | None = None) -> tuple:
    """{page number: [Line]} -> (DocResult, [ExtractedItem]) through the real pipeline steps."""
    s = s or settings()
    doc = se.DocResult(source="test.pdf", engine="standard")
    for number, lines in pages.items():
        doc.pages.append(se.PageInfo(number=number, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI))
        doc.blocks.extend(se.analyze_page(number, blank_page(), lines, s))
    se.finalize_document(doc, s)
    items = se.RequirementExtractor(s).extract(doc)
    return doc, items


def requirements(items: list) -> list:
    return [it for it in items if it.item_type == "Requirement"]


def texts(items: list) -> list:
    return [it.text for it in requirements(items)]


def find(items: list, fragment: str) -> se.ExtractedItem:
    hits = [it for it in requirements(items) if fragment in it.text]
    assert len(hits) == 1, f"expected one requirement containing {fragment!r}, got {texts(items)}"
    return hits[0]


# =====================================================================================================================
# Text layout and requirement rows
# =====================================================================================================================
def test_paragraph_continued_on_next_page_keeps_its_order():
    page1 = make_lines(["3.4 Transmitter.", None, "3.4.1 Warm-up. The transmitter shall reach full rated",
                        "output power within a period that shall not"], y0=1990)
    page2 = make_lines(["exceed 30 minutes after application of primary power.", None,
                        "3.5 Cooling. The unit shall be air cooled."], y0=250)
    _, items = run({1: page1, 2: page2})
    row = find(items, "full rated")
    assert row.text == ("The transmitter shall reach full rated output power within a period that shall not exceed "
                        "30 minutes after application of primary power."), row.text
    assert row.doc_ref == "3.4.1" and row.pages == "1-2", (row.doc_ref, row.pages)
    assert any("across pages" in r for r in row.review_reasons)


def test_page_break_after_complete_word_does_not_join_paragraphs():
    # "... sensor" ends a line at the page bottom, but the next page starts a new paragraph
    page1 = make_lines(["3.1 Sensor. The unit shall contain one temperature sensor"], y0=2090)
    page2 = make_lines(["3.2 Cooling. The unit shall be air cooled."], y0=250)
    _, items = run({1: page1, 2: page2})
    assert texts(items) == ["The unit shall contain one temperature sensor", "The unit shall be air cooled."], texts(items)


def test_numbered_sentence_is_not_a_heading():
    _, items = run({1: make_lines(["3.2.1 The primary and secondary radar display units",
                                   "shall operate from 28 VDC aircraft power.", None,
                                   "3.2.2 Weight. The unit shall weigh less than 5 kg."])})
    row = find(items, "display units")
    assert row.text == "The primary and secondary radar display units shall operate from 28 VDC aircraft power."
    assert row.doc_ref == "3.2.1" and row.section == "", (row.doc_ref, row.section)


def test_number_at_start_of_wrapped_line_does_not_split_paragraph():
    _, items = run({1: make_lines(["3.3.1 Channels. The receiver shall provide channels equal to",
                                   "12. The receiver shall acquire all channels within 45 s."])})
    assert texts(items) == ["The receiver shall provide channels equal to 12.",
                            "The receiver shall acquire all channels within 45 s."], texts(items)
    assert [it.doc_ref for it in requirements(items)] == ["3.3.1", "3.3.1"]


def test_designator_at_start_of_wrapped_line_stays_in_text():
    _, items = run({1: make_lines(["3.3.2 Interface. The flight computer shall exchange data with",
                                   "F-35 mission systems through the 1553B data bus."])})
    assert texts(items) == ["The flight computer shall exchange data with F-35 mission systems through the 1553B data bus."]


def test_unit_abbreviation_ends_a_sentence():
    _, items = run({1: make_lines(["3.3.3 Timing. The system shall respond within 100 ms. The",
                                   "display shall update at 10 Hz. Class A power shall be used."])})
    assert texts(items) == ["The system shall respond within 100 ms.", "The display shall update at 10 Hz.",
                            "Class A power shall be used."], texts(items)


def test_real_abbreviations_do_not_end_a_sentence():
    spans = se.split_sentences("See Fig. 3 and para. 4. The unit shall comply, e.g. The Standard applies. Done.")
    parts = [("See Fig. 3 and para. 4. The unit shall comply, e.g. The Standard applies. Done.")[a:b] for a, b in spans]
    assert parts == ["See Fig. 3 and para. 4.", "The unit shall comply, e.g. The Standard applies.", "Done."], parts
    text = "The receiver shall lock within 45 s. The display shall show a. The first item. Weigh 20 g. The end."
    parts = [text[a:b] for a, b in se.split_sentences(text)]
    assert parts == ["The receiver shall lock within 45 s.", "The display shall show a. The first item.", "Weigh 20 g.",
                     "The end."], parts


def test_stray_period_before_an_abbreviation_does_not_cut_the_requirement():
    _, items = run({1: make_lines(["3.3.2 Maintainability. The mean time to repair. (MTTR) shall not exceed",
                                   "30 minutes. The unit shall be tested. (a) The display shall be checked."])})
    assert texts(items) == ["The mean time to repair. (MTTR) shall not exceed 30 minutes.", "The unit shall be tested.",
                            "(a) The display shall be checked."], texts(items)
    assert any("Stray period" in r for r in requirements(items)[0].review_reasons), requirements(items)[0].review_reasons


def test_quantity_is_not_a_paragraph_number():
    _, items = run({1: make_lines(["3.3 V shall be supplied to the logic card."])})
    row = find(items, "logic card")
    assert row.text == "3.3 V shall be supplied to the logic card." and row.doc_ref == "", (row.text, row.doc_ref)


def test_designators_are_not_requirement_ids():
    _, items = run({1: make_lines(["MK-54 torpedo tubes shall be inspected before loading.", None,
                                   "The harness shall mate with connector (J3) and breaker (CB12)."])})
    assert texts(items) == ["MK-54 torpedo tubes shall be inspected before loading.",
                            "The harness shall mate with connector (J3) and breaker (CB12)."], texts(items)
    assert all(it.doc_ref == "" for it in requirements(items))


def test_bracketed_and_repeated_ids_are_recognised():
    _, items = run({1: make_lines(["[SRS-101] The GCS shall log all operator commands.", None,
                                   "SRS-102: The GCS shall display telemetry within 250 ms.", None,
                                   "SRS-103 The GCS shall alert the operator within 2 seconds."])})
    assert [it.doc_ref for it in requirements(items)] == ["SRS-101", "SRS-102", "SRS-103"], \
        [(it.doc_ref, it.text) for it in requirements(items)]
    assert texts(items)[2] == "The GCS shall alert the operator within 2 seconds."


def test_ocr_garbled_keyword_is_repaired_and_flagged():
    _, items = run({1: make_lines(["3.3.4 Mass. The unit sha11 weigh less than 5 lb."])})
    row = find(items, "weigh")
    assert row.text == "The unit shall weigh less than 5 lb." and row.keyword == "shall"
    assert any("repaired" in r for r in row.review_reasons)


def test_all_caps_list_items_are_not_headings():
    _, items = run({1: make_lines(["3.3.5 Modes. The radar shall provide these modes:",
                                   (60, "(1) SEARCH MODE."), (60, "(2) TRACK MODE."), None,
                                   "3.3.6 Power. The radar shall use 28 VDC."])})
    assert texts(items)[:2] == ["The radar shall provide these modes: (1) SEARCH MODE.",
                                "The radar shall provide these modes: (2) TRACK MODE."], texts(items)
    assert find(items, "28 VDC").section == ""          # no fake "SEARCH MODE" section


def test_unmarked_list_under_a_stem():
    _, items = run({1: make_lines(["3.7.1 Recording. The recorder shall record these parameters:",
                                   (80, "Barometric altitude."), (80, "True airspeed."), (80, "Magnetic heading."), None,
                                   "3.7.2 Storage. The recorder shall store 25 hours of data."])})
    assert texts(items) == ["The recorder shall record these parameters: Barometric altitude.",
                            "The recorder shall record these parameters: True airspeed.",
                            "The recorder shall record these parameters: Magnetic heading.",
                            "The recorder shall store 25 hours of data."], texts(items)


def test_list_item_in_footer_zone_is_not_page_furniture():
    page1 = make_lines(["3.6.1 Power. The unit shall accept the following inputs:",
                        (60, "a. 115 VAC, 400 Hz, three phase.")], y0=300) + make_lines([(60, "b. 28 VDC.")], y0=2226)
    page1 += [make_line("1", 930, 2330)]
    page2 = make_lines(["3.6.2 Grounding. The chassis shall be grounded."], y0=300) + [make_line("2", 930, 2330)]
    doc, items = run({1: page1, 2: page2})
    assert "The unit shall accept the following inputs: b. 28 VDC." in texts(items), texts(items)
    assert [b.text for b in doc.blocks if b.kind == "page_footer"] == ["1", "2"]


def test_repeated_header_is_page_furniture():
    pages = {n: [make_line("SPEC-RDR-0042 REV C", 1300, 60)] + make_lines([f"3.{n} Item. The unit shall pass test {n}."])
             for n in (1, 2, 3)}
    doc, items = run(pages)
    assert len(texts(items)) == 3 and all("SPEC-RDR" not in t for t in texts(items))
    assert sum(1 for b in doc.blocks if b.kind == "page_header") == 3


def test_designator_in_parentheses_at_start_of_wrapped_line_stays_in_sentence():
    _, items = run({1: make_lines(["3.1.6 Harness. The harness shall mate with connector (J3) and breaker",
                                   "(CB12). The connector shall be keyed.", None,
                                   "[SRS-101] The GCS shall log all operator commands."])})
    assert texts(items) == ["The harness shall mate with connector (J3) and breaker (CB12).", "The connector shall be keyed.",
                            "The GCS shall log all operator commands."], texts(items)


FULL = ("The contractor shall provide all labor, materials and test equipment needed to perform the")   # 93 characters


def test_heading_without_period_before_a_sentence_is_split():
    doc, items = run({1: make_lines([FULL, "tests described in this section.", None,
                                     "3.4 Security Requirements", "User passwords shall contain at least 12 characters.", None,
                                     "3.5 Installation", "The GCS will be installed on government workstations."])})
    assert [b.text for b in doc.blocks if b.kind == "heading"] == ["3.4 Security Requirements", "3.5 Installation"], \
        [(b.kind, b.text) for b in doc.blocks]
    assert texts(items)[1:] == ["User passwords shall contain at least 12 characters.",
                                "The GCS will be installed on government workstations."], texts(items)


def test_full_width_title_like_line_is_a_wrapped_sentence():
    line = "3.2.4 Radar Cross Section Measurement Accuracy Over The Entire Operating Frequency"   # ends near the margin
    _, items = run({1: make_lines([FULL, "tests described in this section.", None, line, "Range shall be within 1 dB."])})
    assert texts(items)[1:] == ["Radar Cross Section Measurement Accuracy Over The Entire Operating Frequency Range shall "
                                "be within 1 dB."], texts(items)


def test_keywords_in_heading_rule_follow_settings():
    settings(keywords={"shall": "Mandatory", "is to": "Custom keyword"})
    try:
        assert not se._is_heading_text("3.9 Fault log is to be kept")
        assert not se._is_heading_text("3.9 Units sha11 be metric")          # OCR-garbled keyword
        assert se._is_heading_text("3.9 Fault log")
    finally:
        settings()                                                        # back to the default keywords
    assert se._is_heading_text("3.9 Fault log is to be kept")


def test_short_text_in_footer_zone_is_not_page_furniture():
    page1 = make_lines(["3.6.3 Rating. The supply shall be rated as follows."], y0=300) + [make_line("Rated power: 140 W", 220, 2240)]
    page1 += [make_line("1", 930, 2330)]
    page2 = make_lines(["3.6.4 Grounding. The chassis shall be grounded."], y0=300) + [make_line("2", 930, 2330)]
    doc, _ = run({1: page1, 2: page2})
    assert [b.kind for b in doc.blocks if b.text == "Rated power: 140 W"] == ["paragraph"], [(b.kind, b.text) for b in doc.blocks]


def test_keyword_notice_repeated_in_every_footer_is_reported_once():
    notice = "Recipients shall protect this page from disclosure."
    pages = {n: make_lines([f"3.{n} Item. The unit shall pass test {n}."]) + [make_line(notice, 220, 2250),
                                                                               make_line(str(n), 930, 2330)] for n in (1, 2, 3)}
    doc, items = run(pages)
    rows = [it for it in requirements(items) if it.text == notice]
    assert len(rows) == 1 and rows[0].pages == "1-3" and rows[0].needs_review, [(it.text, it.pages) for it in requirements(items)]
    assert len(requirements(items)) == 4
    with tempfile.TemporaryDirectory() as tmp:                         # the notice carries its [R-] tag in the Word report
        import docx
        path = se.write_word_report(Path(tmp) / "t.docx", doc, items, settings())
        footers = [p.text for p in docx.Document(path).paragraphs if p.text.startswith("[footer] Recipients")]
        assert len(footers) == 3 and all(rows[0].item_id in t for t in footers), footers


def test_keyword_notice_with_page_number_or_ocr_noise_is_reported_once():
    notices = {1: "Recipients shall protect this page from disclosure. 1", 2: "Recipients shall protect this page from disclosure. 2",
               3: "Recipients shaIl protect this page frorn disclosure. 3"}
    pages = {n: make_lines([f"3.{n} Item. The unit shall pass test {n}."]) + [make_line(t, 220, 2250)] for n, t in notices.items()}
    _, items = run(pages)
    rows = [it for it in requirements(items) if "disclosure" in it.text]
    assert [(it.pages, it.text) for it in rows] == [("1-3", "Recipients shall protect this page from disclosure.")], \
        [(it.pages, it.text) for it in rows]
    assert not any("Stray period" in r for r in rows[0].review_reasons), rows[0].review_reasons


def test_running_header_with_ocr_noise_is_page_furniture():
    headers = {1: "SPEC-RDR-0042 REV C", 2: "SPEC-RDR-OO42 REV C", 3: "SPEC-RDR-0042 REV C", 4: "SPEC-RDR-0042 REV C."}
    pages = {n: [make_line(h, 1300, 60)] + make_lines([f"3.{n} Item. The unit shall pass test {n}."]) for n, h in headers.items()}
    doc, items = run(pages)
    assert sum(1 for b in doc.blocks if b.kind == "page_header") == 4, [(b.kind, b.text) for b in doc.blocks]
    assert len(texts(items)) == 4


def test_two_column_page_keeps_wrapped_sentences_together():
    left = make_lines(["3.1.6 Harness. The harness shall mate with", "(CB12) and J3 before the first power-up.", None,
                       "3.2.4 Radar Cross Section Measurement Error", "Budget shall not exceed 1.5 dB at any angle."], x0=150)
    right = make_lines(["3.3 Cooling. The unit shall be air cooled by", "the aircraft ECS and shall not require any",
                        "liquid coolant during ground operation.", None, "3.4 Mass. The unit shall weigh less than 5 kg",
                        "including the mounting tray and connectors."], x0=900)
    footer = [make_line("Use or disclosure of this data shall be subject to the restriction on the title page. 1", 150, 2300)]
    _, items = run({1: left + right + footer})                   # the footer runs across both columns
    assert texts(items)[:2] == ["The harness shall mate with (CB12) and J3 before the first power-up.",
                                "Radar Cross Section Measurement Error Budget shall not exceed 1.5 dB at any angle."], texts(items)
    assert texts(items)[2:4] == ["The unit shall be air cooled by the aircraft ECS and shall not require any liquid coolant "
                                 "during ground operation.", "The unit shall weigh less than 5 kg including the mounting "
                                 "tray and connectors."], texts(items)
    assert [it.section for it in requirements(items)] == [""] * len(requirements(items))


def test_double_spaced_paragraph_next_to_single_spaced_notes():
    pitch2 = 2 * PITCH                                            # double-spaced paragraph lines
    para = [make_line(t, LEFT, 300 + k * pitch2) for k, t in enumerate(
        ["3.2.1 Detection range. The radar shall detect a target with a radar cross",
         "section of 1 square meter at a range of not less than 150 km with a",
         "probability of detection of 0.9 in clear weather conditions."])]
    notes = [make_line("NOTES:", LEFT + 100, 700)] + [make_line(f"{n}. Note text line number {n} for the table of values.",
                                                               LEFT + 100, 700 + n * 38) for n in range(1, 9)]
    para2 = [make_line(t, LEFT, 1150 + k * pitch2) for k, t in enumerate(
        ["3.2.2 Track capacity. The radar shall maintain tracks on not less than",
         "200 targets simultaneously while continuing to search."])]
    _, items = run({1: para + notes + para2})
    assert texts(items) == [
        "The radar shall detect a target with a radar cross section of 1 square meter at a range of not less than 150 km "
        "with a probability of detection of 0.9 in clear weather conditions.",
        "The radar shall maintain tracks on not less than 200 targets simultaneously while continuing to search."], texts(items)
    assert [it.section for it in requirements(items)] == ["", ""]                 # the notes are not headings


def test_id_led_requirement_after_full_line_without_period():
    _, items = run({1: make_lines(["[SRS-100] The ground control station shall display the moving map with the current mission route",
                                   "[SRS-101] The GCS shall log all operator commands."])})
    assert [(it.doc_ref, it.text) for it in requirements(items)] == [
        ("SRS-100", "The ground control station shall display the moving map with the current mission route"),
        ("SRS-101", "The GCS shall log all operator commands.")], [(it.doc_ref, it.text) for it in requirements(items)]


def test_continuation_on_next_page_starting_with_a_number_is_joined():
    page1 = make_lines(["3.4.1 Warm-up. The transmitter shall reach full rated output power within a period", "that shall not exceed"],
                       y0=2040)
    page2 = make_lines(["30 minutes after application of primary power.", None, "3.5 Cooling. The unit shall be air cooled."], y0=250)
    _, items = run({1: page1, 2: page2})
    assert texts(items) == ["The transmitter shall reach full rated output power within a period that shall not exceed 30 minutes "
                            "after application of primary power.", "The unit shall be air cooled."], texts(items)


def test_numbered_caps_items_under_a_stem_are_list_items():
    doc, items = run({1: make_lines(["3.3.5 Modes. The radar shall provide these modes:", (60, "1. SEARCH MODE."),
                                     (60, "2. TRACK MODE."), None, "3.3.6 Power. The radar shall use 28 VDC.", None,
                                     "4. VERIFICATION", None, "4.1 Tests. Tests shall be witnessed."])})
    assert texts(items)[:2] == ["The radar shall provide these modes: 1. SEARCH MODE.",
                                "The radar shall provide these modes: 2. TRACK MODE."], texts(items)
    assert [it.section for it in requirements(items)] == ["", "", "", "4 VERIFICATION"], [it.section for it in requirements(items)]
    doc, items = run({1: make_lines(["NOTES:", "1. VALUES ARE NOMINAL.", None, "3.4 Mass. The unit shall weigh 5 kg."])})
    assert [b.kind for b in doc.blocks] == ["paragraph", "list_item", "paragraph"], [(b.kind, b.text) for b in doc.blocks]
    assert requirements(items)[0].section == ""


def test_last_line_without_final_period_does_not_swallow_next_paragraph():
    for next_paragraph, expected_ref in (("3.2.5 Weight. The radar shall weigh less than 45 kg.", "3.2.5"),
                                         ("The radar shall weigh less than 45 kg.", "")):
        _, items = run({1: make_lines(["3.2.4 Display. The contractor shall provide all labor, materials and test equipment needed to",
                                       "perform the tests described in this section and in the verification cross reference matrix",
                                       None, next_paragraph])})
        assert [(it.doc_ref, it.text) for it in requirements(items)] == [
            ("3.2.4", "The contractor shall provide all labor, materials and test equipment needed to perform the tests described "
                      "in this section and in the verification cross reference matrix"),
            (expected_ref, "The radar shall weigh less than 45 kg.")], [(it.doc_ref, it.text) for it in requirements(items)]


def test_section_headings_after_a_list_or_an_empty_section_stay_headings():
    doc, items = run({1: make_lines(["3.6 Power. The unit shall accept the following inputs:", "a. 115 VAC, 400 Hz.", "b. 28 VDC.", None,
                                     "4. VERIFICATION", None, "4.1 Tests. Tests shall be witnessed by the government."])})
    assert [it.section for it in requirements(items)] == ["", "", "4 VERIFICATION"], [(it.section, it.text) for it in requirements(items)]
    doc, items = run({1: make_lines(["1. SCOPE", None, "1.1 Scope. This specification covers the radar.", None,
                                     "3. REQUIREMENTS", "4. VERIFICATION", None, "4.1 Tests. Tests shall be witnessed."])})
    assert [b.kind for b in doc.blocks if b.text[:2] in ("1.", "3.", "4.")][:1] + \
        [b.kind for b in doc.blocks if b.text in ("3. REQUIREMENTS", "4. VERIFICATION")] == ["heading", "heading", "heading"]


def test_bracketed_citation_at_start_of_wrapped_line_stays_in_sentence():
    _, items = run({1: make_lines(["5.2.1 Protocol. The interface shall comply with the telecommand protocol defined in",
                                   "[RD-3] and shall use a data rate of 115200 bit/s on both redundant channels."])})
    assert [(it.doc_ref, it.text) for it in requirements(items)] == [
        ("5.2.1", "The interface shall comply with the telecommand protocol defined in [RD-3] and shall use a data rate of "
                  "115200 bit/s on both redundant channels.")], [(it.doc_ref, it.text) for it in requirements(items)]


def test_heading_without_period_on_a_list_heavy_page_and_next_to_id_columns():
    rows = (["3.3 Displays. The console shall provide these indicators:"] + [(60, f"{c}. Indicator {c} lamp") for c in "abcdefghijk"]
            + [None, "3.4 Security Requirements", None, FULL, "tests described in this section."])
    doc, _ = run({1: make_lines(rows)})
    assert "3.4 Security Requirements" in [b.text for b in doc.blocks if b.kind == "heading"], [(b.kind, b.text) for b in doc.blocks]
    page = [make_line("SPEC-0042 REV C", 1350, 60), make_line("12", 930, 2330)]
    page += make_lines(["3.4 Software requirements", FULL, "tests described in this section.", None,
                        "[SRS-FUNC-0001]", None, "[SRS-FUNC-0002]"], y0=300)
    page += make_lines(["The GCS shall log all operator commands.", None, "The GCS shall display telemetry data."], y0=300 + 4 * 48, x0=660)
    doc, items = run({1: page})
    assert [(it.doc_ref, it.section) for it in requirements(items)][:3] == [
        ("", "3.4 Software requirements"), ("SRS-FUNC-0001", "3.4 Software requirements"), ("SRS-FUNC-0002", "3.4 Software requirements")], \
        [(it.doc_ref, it.section, it.text) for it in requirements(items)]


def test_heading_before_a_short_sentence_on_a_single_column_page():
    rows = ["3.3 Displays. The console shall provide these indicators:"] + [(60, f"{c}. Indicator {c} lamp") for c in "abcdef"]
    rows += [None, FULL, "tests described in this section.", None, "3.4 Security Requirements", "Passwords shall be encrypted.",
             None, FULL, "tests described in this section."]
    doc, items = run({1: make_lines(rows)})
    assert "3.4 Security Requirements" in [b.text for b in doc.blocks if b.kind == "heading"], [(b.kind, b.text) for b in doc.blocks]
    assert "Passwords shall be encrypted." in texts(items), texts(items)


def test_different_requirements_in_footer_zone_are_not_grouped():
    pages = {p: make_lines([f"3.{p} Item. The unit shall pass test {p}."]) +
             [make_line(f"The operator shall record the measured reading in Table 4-{p} before power-down.", 220, 2240),
              make_line(str(p), 930, 2330)] for p in (1, 2, 3)}
    _, items = run(pages)
    rows = [it for it in requirements(items) if "operator" in it.text]
    assert [it.text for it in rows] == [f"The operator shall record the measured reading in Table 4-{p} before power-down." for p in (1, 2, 3)]
    assert [(it.found_in, it.needs_review) for it in rows] == [("Paragraph", False)] * 3, [(it.found_in, it.review_reasons) for it in rows]


def test_custom_keywords_protect_short_requirements():
    s = settings(keywords={"shall": "Mandatory", "is to": "Custom keyword"})
    _, items = run({1: make_lines(["3.9 Fault log is to be kept."])}, s)
    assert texts(items) == ["Fault log is to be kept."] and requirements(items)[0].keyword == "is to", \
        [(it.text, it.keyword) for it in requirements(items)]


def test_heading_rules_still_find_real_headings():
    doc, items = run({1: make_lines(["3.2 Characteristics.", None, "3.2.1 Detection range. The radar shall detect "
                                     "targets at 150 km.", None, "4. VERIFICATION", None,
                                     "4.1 Tests. Tests shall be witnessed."])})
    headings = [b.text for b in doc.blocks if b.kind == "heading"]
    assert headings == ["3.2 Characteristics.", "4. VERIFICATION"], headings
    assert [it.section for it in requirements(items)] == ["3.2 Characteristics", "4 VERIFICATION"], \
        [it.section for it in requirements(items)]


# =====================================================================================================================
# Tables and captions
# =====================================================================================================================
def _fake_img2table(rows: dict, bbox: tuple):
    """Replace img2table's Image class so detect_tables() receives exactly this cell grid.

    The cells carry geometry only (`value` is None): this mock stands in for the grid img2table
    finds, while the text is filled in from our own OCR lines afterwards. The check for rows that
    have swallowed several rows of text reads img2table's own cell text, so with this mock it sees
    nothing and stays switched off - which is what these tests want, as they are about the grid."""
    import img2table.document as i2t_document

    def box(x1, y1, x2, y2):
        return types.SimpleNamespace(x1=x1, y1=y1, x2=x2, y2=y2)

    table = types.SimpleNamespace(content={r: [types.SimpleNamespace(bbox=box(*c), value=None) for c in cells]
                                           for r, cells in rows.items()},
                                  bbox=box(*bbox))

    class FakeImage:
        def __init__(self, *args, **kwargs):
            pass

        def extract_tables(self, borderless_tables=False, **kwargs):
            return [] if borderless_tables else [table]

    original = i2t_document.Image
    i2t_document.Image = FakeImage
    return lambda: setattr(i2t_document, "Image", original)


def _grid_lines(texts_at: dict, xs: list, ys: list) -> list:
    return [make_line(t, xs[c] + 10, ys[r] + 15, height=28) for (r, c), t in texts_at.items()]


def test_caption_row_inside_table_is_given_back_and_merges_shift():
    xs, ys = [300, 800, 1200, 1600], [400, 460, 520, 580, 640, 700]

    def cell(r0, c0, r1=None, c1=None):
        return (xs[c0], ys[r0], xs[(c1 if c1 is not None else c0) + 1], ys[(r1 if r1 is not None else r0) + 1])

    caption, note = cell(0, 0, 0, 2), cell(2, 2, 3, 2)            # merged caption row; "Notes" merged over 2 rows
    rows = {0: [caption] * 3, 1: [cell(1, 0), cell(1, 1), cell(1, 2)], 2: [cell(2, 0), cell(2, 1), note],
            3: [cell(3, 0), cell(3, 1), note], 4: [cell(4, 0), cell(4, 1), cell(4, 2)]}
    lines = _grid_lines({(0, 0): "TABLE I. Supply data", (1, 0): "Parameter", (1, 1): "Value", (1, 2): "Notes",
                         (2, 0): "Voltage", (2, 1): "28 VDC", (2, 2): "See note 1", (3, 0): "Current", (3, 1): "5 A",
                         (4, 0): "Power", (4, 1): "140 W", (4, 2): "Nominal rating"}, xs, ys)
    restore = _fake_img2table(rows, (xs[0], ys[0], xs[3], ys[5]))
    try:
        s = settings(detect_tables=True)
        table, tbox, inside, caption_lines = se.detect_tables(blank_page().ocr_image, lines, DPI, s)[0]
        assert table.grid[0] == ["Parameter", "Value", "Notes"] and table.n_rows == 4, table.grid
        assert table.merges == [(1, 2, 2, 2)], table.merges
        assert tbox[1] >= ys[1] - 1, tbox                                  # table box no longer covers the caption
        assert len(caption_lines) == 1
        doc, items = run({1: lines}, s)
    finally:
        restore()
    tables = [it for it in items if it.item_type == "Table"]
    captions = [it for it in items if it.item_type == "Table Caption"]
    assert len(tables) == 1 and len(captions) == 1, [(it.item_type, it.text) for it in items]
    assert tables[0].title == "TABLE I. Supply data", tables[0].title
    with tempfile.TemporaryDirectory() as tmp:                             # merged cells in the Excel table sheet
        import openpyxl
        path = se.write_workbook(Path(tmp) / "t.xlsx", [(doc, items)], s)
        sheet = openpyxl.load_workbook(path)[tables[0].table_sheet]
        merged = [str(r) for r in sheet.merged_cells.ranges]
        values = [[c.value for c in row][:3] for row in sheet.iter_rows(min_row=5, max_row=8)]
        assert merged == ["C6:C7"], merged
        assert values[3] == ["Power", "140 W", "Nominal rating"], values


def test_caption_split_over_cells_is_given_back():
    xs, ys = [300, 700, 1300], [400, 460, 520, 580, 640]
    rows = {r: [(xs[0], ys[r], xs[1], ys[r + 1]), (xs[1], ys[r], xs[2], ys[r + 1])] for r in range(4)}
    lines = _grid_lines({(0, 0): "TABLE II.", (0, 1): "Interface signals", (1, 0): "Signal", (1, 1): "Level",
                         (2, 0): "READY", (2, 1): "5 V", (3, 0): "FAULT", (3, 1): "28 V"}, xs, ys)
    restore = _fake_img2table(rows, (xs[0], ys[0], xs[2], ys[4]))
    try:
        table, _, _, caption_lines = se.detect_tables(blank_page().ocr_image, lines, DPI, settings(detect_tables=True))[0]
    finally:
        restore()
    assert table.grid == [["Signal", "Level"], ["READY", "5 V"], ["FAULT", "28 V"]], table.grid
    assert len(caption_lines) == 2


def test_list_of_tables_keeps_its_rows():
    xs, ys = [300, 700, 1300], [400, 460, 520, 580, 640]
    rows = {r: [(xs[0], ys[r], xs[1], ys[r + 1]), (xs[1], ys[r], xs[2], ys[r + 1])] for r in range(4)}
    lines = _grid_lines({(0, 0): "Table", (0, 1): "Page", (1, 0): "TABLE 1. Pins", (1, 1): "4",
                         (2, 0): "TABLE 2. Levels", (2, 1): "7", (3, 0): "TABLE 3. Limits", (3, 1): "9"}, xs, ys)
    restore = _fake_img2table(rows, (xs[0], ys[0], xs[2], ys[4]))
    try:
        table, _, _, caption_lines = se.detect_tables(blank_page().ocr_image, lines, DPI, settings(detect_tables=True))[0]
    finally:
        restore()
    assert table.n_rows == 4 and not caption_lines, table.grid


def test_two_line_caption_row_is_given_back_whole():
    xs, ys = [300, 800, 1200, 1600], [400, 530, 590, 650, 710]
    rows = {0: [(xs[0], ys[0], xs[3], ys[1])] * 3}
    rows.update({r: [(xs[c], ys[r], xs[c + 1], ys[r + 1]) for c in range(3)] for r in (1, 2, 3)})
    lines = [make_line("TABLE III. Environmental test conditions for", 310, 410, height=28),
             make_line("equipment in uncontrolled areas", 310, 490, height=28)]             # double-spaced caption lines
    lines += _grid_lines({(1, 0): "Parameter", (1, 1): "Value", (1, 2): "Notes", (2, 0): "Voltage", (2, 1): "28 VDC",
                          (2, 2): "Nominal", (3, 0): "Current", (3, 1): "5 A", (3, 2): "Maximum"}, xs, ys)
    restore = _fake_img2table(rows, (xs[0], ys[0], xs[3], ys[4]))
    try:
        _, items = run({1: lines}, settings(detect_tables=True))
    finally:
        restore()
    table = [it for it in items if it.item_type == "Table"][0]
    assert table.title == "TABLE III. Environmental test conditions for equipment in uncontrolled areas", table.title
    assert table.table.grid[0] == ["Parameter", "Value", "Notes"]


def test_requirement_table_with_requirement_id_header():
    s = settings()
    grid = [["Requirement ID", "Requirement Type", "Requirement Text", "Verification Method"],
            ["SRS-001", "Functional", "The software shall start within 10 s.", "T"],
            ["SRS-002", "Functional", "The softwere shall log faults.", "A"]]
    doc = se.DocResult(source="t.pdf", engine="standard",
                       pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)],
                       blocks=[se.Block("table", 1, (300, 400, 1500, 600),
                                        table=se.TableData(grid=grid, conf=[[1.0] * 4 for _ in grid]))])
    se.finalize_document(doc, s)
    rows = requirements(se.RequirementExtractor(s).extract(doc))
    assert [(r.doc_ref, r.text, r.verification) for r in rows] == [
        ("SRS-001", "The software shall start within 10 s.", "Test"), ("SRS-002", "The softwere shall log faults.", "Analysis")], \
        [(r.doc_ref, r.text, r.verification) for r in rows]
    assert rows[1].needs_review and not rows[0].needs_review


def test_word_report_handles_large_tables_quickly():
    import time
    import docx
    s = settings()
    grid = [[f"H{c}" for c in range(8)]] + [[f"r{r}c{c}" for c in range(8)] for r in range(1, 400)]
    table = se.TableData(grid=grid, conf=[[1.0] * 8 for _ in grid], merges=[(r, 7, r + 1, 7) for r in range(1, 399, 10)])
    doc = se.DocResult(source="t.pdf", engine="standard",
                       pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)],
                       blocks=[se.Block("table", 1, (200, 200, 1700, 2200), table=table)])
    se.finalize_document(doc, s)
    items = se.RequirementExtractor(s).extract(doc)
    with tempfile.TemporaryDirectory() as tmp:
        start = time.time()
        path = se.write_word_report(Path(tmp) / "t.docx", doc, items, s)
        seconds = time.time() - start
        cells = docx.Document(path).tables[0]
        assert cells.cell(398, 3).text == "r398c3" and cells.cell(1, 7)._tc is cells.cell(2, 7)._tc
    assert seconds < 15, f"Word report took {seconds:.1f} s for a 400-row table"


def test_framed_figure_above_a_table_stays_a_figure():
    import cv2
    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    x0, x1 = 444, 1459
    cv2.rectangle(img, (x0, 1300), (x1, 1700), 0, 4)                  # a framed block diagram ...
    for bx in (520, 860, 1200):
        cv2.rectangle(img, (bx, 1450), (bx + 200, 1600), 0, 3)
    cv2.line(img, (720, 1525), (860, 1525), 0, 3)
    lines = [make_line("FIGURE 3. Receiver block diagram", 560, 1330), make_line("Antenna", 550, 1510),
             make_line("Receiver", 890, 1510), make_line("Processor", 1225, 1510)]
    xs, ys = [x0, 900, x1], [1720, 1780, 1840, 1900]                   # ... directly above a table of the same width
    rows = {r: [(xs[c], ys[r], xs[c + 1], ys[r + 1]) for c in range(2)] for r in range(3)}
    lines += _grid_lines({(0, 0): "Signal", (0, 1): "Level", (1, 0): "RF IN", (1, 1): "-90 dBm", (2, 0): "IF OUT", (2, 1): "0 dBm"}, xs, ys)
    for bx0, by0, bx1, by1 in [cb for row in rows.values() for cb in row]:
        cv2.rectangle(img, (bx0, by0), (bx1, by1), 0, 2)
    restore = _fake_img2table(rows, (x0, ys[0], x1, ys[3]))
    try:
        s = settings(detect_tables=True)
        prep = se.PreparedPage(img, img.copy(), float(DPI))
        blocks = se.analyze_page(1, prep, lines, s)
        assert [b.kind for b in blocks if b.kind in ("figure", "table")] == ["figure", "table"], [(b.kind, b.text) for b in blocks]
        small = img.copy()                                              # a short frame with a TABLE-like title and a drawing
        small[1300:1720] = 255
        cv2.rectangle(small, (x0, 1560), (x1, 1712), 0, 4)
        cv2.rectangle(small, (900, 1640), (1100, 1700), 0, 3)
        lines2 = [make_line("TABLE 3. Signal levels", 470, 1580)] + lines[4:]
        blocks = se.analyze_page(1, se.PreparedPage(small, small.copy(), float(DPI)), lines2, s)
        assert [b.kind for b in blocks if b.kind in ("figure", "table")] == ["figure", "table"], [(b.kind, b.text) for b in blocks]
    finally:
        restore()


def test_framed_caption_cell_above_a_table_is_the_caption():
    import cv2
    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    x0, x1 = 444, 1459
    cv2.rectangle(img, (x0, 1560), (x1, 1712), 0, 4)                  # the caption cell of the table frame (text only)
    lines = [make_line("TABLE III. Environmental test conditions for", 470, 1585),
             make_line("equipment in uncontrolled areas", 470, 1660)]
    xs, ys = [x0, 900, x1], [1720, 1780, 1840, 1900]
    rows = {r: [(xs[c], ys[r], xs[c + 1], ys[r + 1]) for c in range(2)] for r in range(3)}
    lines += _grid_lines({(0, 0): "Parameter", (0, 1): "Value", (1, 0): "Voltage", (1, 1): "28 VDC", (2, 0): "Current", (2, 1): "5 A"}, xs, ys)
    for bx0, by0, bx1, by1 in [cb for row in rows.values() for cb in row]:
        cv2.rectangle(img, (bx0, by0), (bx1, by1), 0, 2)
    restore = _fake_img2table(rows, (x0, ys[0], x1, ys[3]))
    try:
        s = settings(detect_tables=True)
        doc = se.DocResult(source="t.pdf", engine="standard",
                           pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)])
        doc.blocks = se.analyze_page(1, se.PreparedPage(img, img.copy(), float(DPI)), lines, s)
        se.finalize_document(doc, s)
        items = se.RequirementExtractor(s).extract(doc)
    finally:
        restore()
    assert [b.kind for b in doc.blocks] == ["caption", "table"], [(b.kind, b.text) for b in doc.blocks]
    table = [it for it in items if it.item_type == "Table"][0]
    assert table.title == "TABLE III. Environmental test conditions for equipment in uncontrolled areas", table.title


def test_requirement_table_with_title_and_description_columns():
    s = settings()
    grid = [["Req ID", "Requirement Title", "Description", "Method"],
            ["RDR-001", "Detection range at sea level", "The radar shall detect a 1 m2 target at 150 km.", "T"],
            ["RDR-002", "Track capacity in search mode", "The radar shall track 200 targets.", "D"]]
    doc = se.DocResult(source="t.pdf", engine="standard",
                       pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)],
                       blocks=[se.Block("table", 1, (300, 400, 1500, 600), table=se.TableData(grid=grid, conf=[[1.0] * 4 for _ in grid]))])
    se.finalize_document(doc, s)
    rows = requirements(se.RequirementExtractor(s).extract(doc))
    assert [(r.doc_ref, r.text, r.verification) for r in rows] == [
        ("RDR-001", "The radar shall detect a 1 m2 target at 150 km.", "Test"), ("RDR-002", "The radar shall track 200 targets.", "Demonstration")], \
        [(r.doc_ref, r.text, r.verification) for r in rows]


def test_merges_without_row():
    assert se._merges_without_row([(0, 0, 0, 2), (1, 2, 3, 2), (2, 0, 2, 1)], 0) == [(0, 2, 2, 2), (1, 0, 1, 1)]
    assert se._merges_without_row([(3, 1, 4, 1), (4, 0, 4, 2), (1, 0, 2, 0)], 4) == [(1, 0, 2, 0)]


def _object_block(kind: str, page: int, box: tuple) -> se.Block:
    table = se.TableData(grid=[["A", "B"], ["1", "2"]], conf=[[1.0, 1.0], [1.0, 1.0]]) if kind == "table" else None
    return se.Block(kind, page, box, table=table)


def _caption_block(text: str, page: int, box: tuple) -> se.Block:
    return se.Block("caption", page, box, text=text, meta=se.caption_meta(text, "table"))


def _link(blocks: list) -> dict:
    doc = se.DocResult(source="t.pdf", engine="standard",
                       pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)], blocks=blocks)
    for i, b in enumerate(doc.blocks, 1):
        b.uid = i
    se._link_captions(doc)
    return {b.text: b.meta.get("caption_of") for b in doc.blocks if b.kind == "caption"}


def test_captions_below_tables_link_to_their_own_table():
    # table, caption (below it, but a little closer to the next table), table, caption, table, caption
    links = _link([_object_block("table", 1, (400, 500, 1400, 800)), _caption_block("TABLE IV. Pins.", 1, (600, 830, 1200, 860)),
                   _object_block("table", 1, (400, 882, 1400, 1100)), _caption_block("TABLE V. Levels.", 1, (600, 1130, 1200, 1160)),
                   _object_block("table", 1, (400, 1182, 1400, 1400)), _caption_block("TABLE VI. Data.", 1, (600, 1430, 1200, 1460))])
    assert links == {"TABLE IV. Pins.": 1, "TABLE V. Levels.": 3, "TABLE VI. Data.": 5}, links


def test_captions_above_tables_link_to_the_table_below():
    links = _link([_caption_block("TABLE I. Items.", 1, (600, 400, 1200, 430)), _object_block("table", 1, (400, 450, 1400, 800)),
                   _caption_block("TABLE II. Limits.", 1, (600, 830, 1200, 860)), _object_block("table", 1, (400, 880, 1400, 1100))])
    assert links == {"TABLE I. Items.": 2, "TABLE II. Limits.": 4}, links


def test_caption_inside_table_frame_and_captions_below_on_one_page():
    # like test document D: two tables with captions below, then a table whose caption row was taken out of its frame
    frame_caption = _caption_block("TABLE VI. Supply data.", 1, (452, 1682, 862, 1720))
    frame_caption.meta["caption_for_box"] = [444, 1730, 1459, 1970]
    links = _link([_object_block("table", 1, (598, 1035, 1304, 1276)), _caption_block("TABLE IV. Pins.", 1, (551, 1308, 1345, 1350)),
                   _object_block("table", 1, (598, 1370, 1305, 1550)), _caption_block("TABLE V. Levels.", 1, (623, 1584, 1275, 1625)),
                   frame_caption, _object_block("table", 1, (444, 1730, 1459, 1970))])
    assert links == {"TABLE IV. Pins.": 1, "TABLE V. Levels.": 3, "TABLE VI. Supply data.": 6}, links


def test_min_cost_assignment():
    assert se._min_cost_assignment([[4, 1, 3], [2, 0, 5], [3, 2, 2]]) == [1, 0, 2]
    assert se._min_cost_assignment([[10, 1, 99], [2, 50, 99]]) == [1, 0]


def test_sequential_ids_are_not_flagged_as_misreads():
    ctx = se.build_text_context([se.Block("paragraph", 1, (0, 0, 10, 10), lines=[make_line(
        "SW-001 SW-002 SW-003 per MIL-STD-810H and MIL-STD-810B via the uplink")])], settings())
    check = ctx.checker
    assert check.issue("SW-002", "SW-002") == ""
    assert "differs by one character" in check.issue("MIL-STD-810B", "MIL-STD-810B")
    ctx = se.build_text_context([se.Block("paragraph", 1, (0, 0, 10, 10), lines=[make_line(
        "ICD-1204A ICD-1205A ENV-005 ENV-006 SPEC-1234-A SPEC-1284-A")])], settings())
    assert ctx.checker.issue("ICD-1205A", "ICD-1205A") == ""                               # running number + revision
    assert ctx.checker.issue("ENV-006", "ENV-006") == ""
    assert "differs by one character" in ctx.checker.issue("SPEC-1284-A", "SPEC-1284-A")   # not the running number
    assert check.issue("uplink", "uplink") == ""                   # engineering word, not a misread


def test_header_row_may_name_a_keyword():
    assert se._looks_like_header(["Req ID", "Shall Statement", "V&V"])
    assert not se._looks_like_header(["SW-001", "The software shall start within 10 s.", "T"])


def test_table_cells_with_suspect_text_are_flagged():
    s = settings()
    table = se.TableData(grid=[["Parameter", "Limit"], ["Operating tempreature", "1O0 VAC"], ["Humidity", "95 %"]],
                         conf=[[0.99, 0.99], [0.99, 0.99], [0.99, 0.99]])
    doc = se.DocResult(source="t.pdf", engine="standard",
                       pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)])
    doc.blocks = [se.Block("paragraph", 1, (220, 300, 1500, 330), lines=[make_line("The operating temperature and the "
                                                                                    "humidity shall be recorded.")],
                           text="The operating temperature and the humidity shall be recorded."),
                  se.Block("table", 1, (300, 400, 1500, 600), table=table)]
    se.finalize_document(doc, s)
    items = se.RequirementExtractor(s).extract(doc)
    row = [it for it in items if it.item_type == "Table"][0]
    joined = " ".join(row.review_reasons)
    assert "1O0" in joined, row.review_reasons
    assert "tempreature" in joined, row.review_reasons


def test_verification_column_and_references():
    s = settings()
    table = se.TableData(grid=[["Req ID", "Shall Statement", "V&V"], ["SW-001", "The software shall start within 10 s.", "T"],
                               ["SW-002", "The software shall comply with MIL-STD-461G and Section 10.2.", "A, T"]],
                         conf=[[1.0] * 3] * 3)
    doc = se.DocResult(source="t.pdf", engine="standard",
                       pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)],
                       blocks=[se.Block("table", 1, (300, 400, 1500, 600), table=table)])
    se.finalize_document(doc, s)
    rows = requirements(se.RequirementExtractor(s).extract(doc))
    assert [(r.doc_ref, r.verification) for r in rows] == [("SW-001", "Test"), ("SW-002", "Analysis, Test")], \
        [(r.doc_ref, r.verification, r.text) for r in rows]
    assert rows[1].references == "MIL-STD-461G; Section 10.2", rows[1].references


# =====================================================================================================================
# Table structure: rows without ruling lines, sideways headers, verification matrices
#
# These cases come from a review on real Systems Engineering scans, where the tool scored well on
# running text but lost whole tables. Unlike the tests above, they draw a REAL page image and let
# the real detector look at it, because the failures were in how the ruling lines (or the absence
# of them) are read - not in the grid handling that happens afterwards.
# =====================================================================================================================
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _draw_words(img, text: str, x: int, y_top: int, scale: float = 1.0, thickness: int = 2) -> list:
    """Print `text` on the page one word at a time and return OCR Words whose boxes match the ink."""
    words, cx = [], x
    for token in text.split():
        (w, h), base = cv2.getTextSize(token, FONT, scale, thickness)
        cv2.putText(img, token, (cx, y_top + h), FONT, scale, 0, thickness, cv2.LINE_AA)
        words.append(se.Word(token, 0.97, (cx, y_top, cx + w, y_top + h + base)))
        cx += w + int(10 * scale) + 4
    return words


def _draw_table(cells: dict, xs: list, ys: list, *, h_lines: bool = True, v_lines: bool = True,
                frame: bool = True, scale: float = 1.0) -> tuple:
    """Draw a table on a blank page and return (page image, OCR lines).

    `cells` is {(row, column): text}; `xs`/`ys` are the column and row boundaries in pixels.
    h_lines=False draws the very common layout of a verification matrix: column rules and an outer
    frame, but nothing between the rows."""
    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    if frame:
        cv2.rectangle(img, (xs[0], ys[0]), (xs[-1], ys[-1]), 0, 2)
    for x in (xs[1:-1] if v_lines else []):
        cv2.line(img, (x, ys[0]), (x, ys[-1]), 0, 2)
    for y in (ys[1:-1] if h_lines else []):
        cv2.line(img, (xs[0], y), (xs[-1], y), 0, 2)
    lines = []
    for (r, c), text in sorted(cells.items()):
        words = _draw_words(img, text, xs[c] + 12, ys[r] + 14, scale=scale)
        lines.append(se.Line(text, 0.97, se.box_union(w.box for w in words), words))
    return img, lines


# rows of a small verification cross reference matrix: (paragraph, title, which method is marked)
VCRM_ROWS = [("3.2.1.1", "Detection range", 3), ("3.2.1.2", "Range accuracy", 1),
             ("3.2.1.3", "Operating modes", 2), ("3.2.1.4", "Track capacity", 3),
             ("3.2.2.1", "Weight", 0), ("3.2.2.2", "Input power", 3)]


def _vcrm_cells(headers=("Paragraph", "Title", "I", "A", "D", "T")) -> dict:
    cells = {(0, c): h for c, h in enumerate(headers)}
    for r, (para, title, mark) in enumerate(VCRM_ROWS, start=1):
        cells[(r, 0)], cells[(r, 1)], cells[(r, 2 + mark)] = para, title, "X"
    return cells


def test_table_with_column_rules_but_no_row_lines_is_found():
    """The layout that broke the tool on real specifications: an outer frame and column rules, but
    no line between the rows. A table needs two horizontal lines before it has a row, so without
    help this table is not found at all - not merely mis-split."""
    xs = [300, 720, 1180, 1320, 1460, 1600, 1740]
    ys = [400 + 58 * i for i in range(8)]
    img, lines = _draw_table(_vcrm_cells(), xs, ys, h_lines=False)
    found = se.detect_tables(img, lines, DPI, settings(detect_tables=True))
    assert found, "a table with column rules but no lines between the rows was not detected at all"
    table = found[0][0]
    assert (table.n_rows, table.n_cols) == (7, 6), (table.n_rows, table.n_cols, table.grid)
    assert table.grid[0] == ["Paragraph", "Title", "I", "A", "D", "T"], table.grid[0]
    assert [r[0] for r in table.grid[1:]] == [row[0] for row in VCRM_ROWS], [r[0] for r in table.grid]
    assert [r[1] for r in table.grid[1:]] == [row[1] for row in VCRM_ROWS], [r[1] for r in table.grid]


def test_fully_ruled_table_is_unchanged_by_the_row_inference():
    """Inferring the missing row lines must never disturb a table that draws all of them."""
    xs = [300, 720, 1180, 1320, 1460, 1600, 1740]
    ys = [400 + 58 * i for i in range(8)]
    img, lines = _draw_table(_vcrm_cells(), xs, ys, h_lines=True)
    table = se.detect_tables(img, lines, DPI, settings(detect_tables=True))[0][0]
    assert (table.n_rows, table.n_cols) == (7, 6), (table.n_rows, table.n_cols, table.grid)
    assert [r[0] for r in table.grid[1:]] == [row[0] for row in VCRM_ROWS], table.grid


def test_row_inference_does_not_split_a_cell_that_wraps_over_two_lines():
    """A cell whose text wraps must stay one row: the row pitch, not every line of text, decides."""
    xs, ys = [300, 900, 1500], [400, 520, 640, 760]
    cells = {(0, 0): "Parameter", (0, 1): "Value",
             (1, 0): "Operating temperature", (1, 1): "-40 C to +71 C",
             (2, 0): "Input power", (2, 1): "115 VAC"}
    img, lines = _draw_table(cells, xs, ys, h_lines=False)
    # a second, wrapped line inside the first data cell
    extra = _draw_words(img, "at sea level", xs[0] + 12, ys[1] + 58)
    lines.append(se.Line("at sea level", 0.97, se.box_union(w.box for w in extra), extra))
    found = se.detect_tables(img, lines, DPI, settings(detect_tables=True))
    assert found, "table not detected"
    table = found[0][0]
    assert table.n_rows == 3, (table.n_rows, table.grid)
    assert "Operating temperature" in table.grid[1][0] and "sea level" in table.grid[1][0], table.grid


def test_sparse_verification_matrix_is_not_rejected_as_too_empty():
    """A verification cross reference matrix is mostly empty by design - one or two marks per row.
    The 'is this really a table?' check must not throw it away for being sparse."""
    header = ["Paragraph", "Title", "I", "A", "D", "T", "S", "E"]
    grid = [header]
    for i, mark_col in enumerate([2, 5, 3, 7, 4, 6]):
        row = [""] * len(header)
        row[0], row[1] = f"3.2.{i + 1}", f"Characteristic {i + 1}"
        row[mark_col] = "X"
        grid.append(row)
    n_unique = len(grid) * len(header)
    n_filled = sum(1 for row in grid for cell in row if cell)
    assert n_filled < 0.5 * n_unique, "this fixture has to be sparse for the test to mean anything"
    assert se._is_mark_matrix(grid), grid
    assert se._plausible_borderless_table(grid, n_unique, n_filled), grid


def test_ordinary_sparse_grid_is_still_rejected():
    """The exemption above must not open the door to any mostly empty grid (forms, drawings)."""
    grid = [["Item", "Value", "Notes", "Date"], ["Pump", "", "", ""], ["", "", "see sheet 2", ""],
            ["Valve", "", "", ""], ["", "", "", "12 May"]]
    n_unique = len(grid) * 4
    n_filled = sum(1 for row in grid for cell in row if cell)
    assert not se._is_mark_matrix(grid), grid
    assert not se._plausible_borderless_table(grid, n_unique, n_filled), grid


def _matrix_doc(header: list, legend: str = "") -> se.DocResult:
    """A one page document holding a verification matrix, optionally preceded by its legend."""
    grid = [header]
    for para, mark in [("3.2.1.1", 3), ("3.2.1.2", 1), ("3.2.2.1", 0)]:
        row = [""] * len(header)
        row[0] = para
        row[2 + mark] = "X"
        grid.append(row)
    blocks = []
    if legend:
        blocks.append(se.Block("paragraph", 1, (300, 300, 1700, 340), lines=make_lines([legend]), text=legend))
    table = se.TableData(grid=grid, conf=[[1.0] * len(header) for _ in grid], header_rows=1)
    blocks.append(se.Block("table", 1, (300, 400, 1700, 700), table=table))
    return se.DocResult(source="t.pdf", engine="standard",
                        pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)],
                        blocks=blocks)


def test_verification_matrix_read_from_its_headers():
    doc = _matrix_doc(["Paragraph", "Title", "I", "A", "D", "T"])
    matrix = se.RequirementExtractor._verification_matrix(doc)
    assert matrix["3.2.1.1"].methods == "Test" and not matrix["3.2.1.1"].from_legend, matrix
    assert matrix["3.2.1.2"].methods == "Analysis", matrix
    assert matrix["3.2.2.1"].methods == "Inspection", matrix


def test_verification_matrix_works_when_the_sideways_headers_could_not_be_read():
    """Sideways headers often come back from OCR as nothing at all. The matrix is then recognised
    from its content (columns holding nothing but X marks) and the columns are named from the
    legend sentence that documents nearly always print above the matrix."""
    legend = ("Verification of each requirement shall be accomplished by inspection (I), analysis (A), "
              "demonstration (D), or test (T), as specified in TABLE III.")
    doc = _matrix_doc(["Paragraph", "Title", "", "", "", ""], legend=legend)
    matrix = se.RequirementExtractor._verification_matrix(doc)
    assert matrix["3.2.1.1"].methods == "Test" and matrix["3.2.1.1"].from_legend, matrix
    assert matrix["3.2.1.2"].methods == "Analysis", matrix
    assert matrix["3.2.2.1"].methods == "Inspection", matrix


def test_verification_matrix_without_headers_or_legend_is_not_guessed():
    """With neither readable headers nor a legend the methods are unknown: say so, never invent."""
    doc = _matrix_doc(["Paragraph", "Title", "", "", "", ""])
    assert se.RequirementExtractor._verification_matrix(doc) == {}


def test_verification_matrix_taken_from_the_legend_is_flagged_for_review():
    """A method read from a column order rather than from a header is a deduction, so the row says so."""
    legend = ("Verification shall be by inspection (I), analysis (A), demonstration (D), or test (T).")
    doc = _matrix_doc(["Paragraph", "Title", "", "", "", ""], legend=legend)
    doc.blocks.append(se.Block("paragraph", 1, (300, 800, 1700, 900),
                               lines=make_lines(["3.2.1.1 Detection range. The radar shall detect targets at 100 nmi."],
                                                y0=800)))
    se.finalize_document(doc, settings())
    rows = requirements(se.RequirementExtractor(settings()).extract(doc))
    row = find(rows, "detect targets")
    assert row.verification.startswith("Test"), row.verification
    assert "legend" in row.verification, row.verification
    assert any("verification matrix" in r.lower() for r in row.review_reasons), row.review_reasons


def test_verification_matrix_reads_a_two_row_header():
    """Matrices often group the method columns under a merged 'VERIFICATION METHOD' banner."""
    grid = [["Paragraph", "Title", "VERIFICATION METHOD", "VERIFICATION METHOD", "VERIFICATION METHOD", "VERIFICATION METHOD"],
            ["", "", "I", "A", "D", "T"],
            ["3.2.1.1", "Detection range", "", "", "", "X"],
            ["3.2.1.2", "Range accuracy", "", "X", "", ""]]
    table = se.TableData(grid=grid, conf=[[1.0] * 6 for _ in grid], header_rows=2,
                         merges=[(0, 2, 0, 5)])
    doc = se.DocResult(source="t.pdf", engine="standard",
                       pages=[se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI)],
                       blocks=[se.Block("table", 1, (300, 400, 1700, 700), table=table)])
    matrix = se.RequirementExtractor._verification_matrix(doc)
    assert matrix["3.2.1.1"].methods == "Test", matrix
    assert matrix["3.2.1.2"].methods == "Analysis", matrix


def test_header_rows_counts_a_merged_banner_above_the_real_headers():
    xs, ys = [300, 700, 1100, 1500], [400, 460, 520, 580, 640]
    def cell(r0, c0, r1=None, c1=None):
        return (xs[c0], ys[r0], xs[(c1 if c1 is not None else c0) + 1], ys[(r1 if r1 is not None else r0) + 1])
    banner = cell(0, 1, 0, 2)
    rows = {0: [cell(0, 0), banner, banner], 1: [cell(1, 0), cell(1, 1), cell(1, 2)],
            2: [cell(2, 0), cell(2, 1), cell(2, 2)], 3: [cell(3, 0), cell(3, 1), cell(3, 2)]}
    lines = _grid_lines({(0, 0): "Para", (0, 1): "METHOD", (1, 0): "No.", (1, 1): "I", (1, 2): "T",
                         (2, 0): "3.1.1", (2, 1): "X", (3, 0): "3.1.2", (3, 2): "X"}, xs, ys)
    restore = _fake_img2table(rows, (xs[0], ys[0], xs[3], ys[4]))
    try:
        table = se.detect_tables(blank_page().ocr_image, lines, DPI, settings(detect_tables=True))[0][0]
    finally:
        restore()
    assert table.header_rows == 2, (table.header_rows, table.grid)


# an SRS-style borderless table: an ID column beside whole requirement sentences that wrap
BORDERLESS_REQ_ROWS = [
    ("SRS-101", "The radar shall detect a one square metre target at a range of 100 nautical",
     "miles in clear air and in light precipitation without any operator action"),
    ("SRS-102", "The radar shall acquire and simultaneously track up to 200 separate targets",
     "while continuing to search the whole of the assigned surveillance volume"),
    ("SRS-103", "The equipment shall operate over the full ambient temperature range that is",
     "specified in TABLE II of this specification without degradation of performance"),
    ("SRS-104", "The system shall complete its built in test and report the result within 30",
     "seconds of the application of primary power at any ambient temperature"),
]


def _borderless_requirement_lines(id_header: str, text_header: str) -> list:
    """The table above as OCR lines: rows 64 px apart, the two lines of a wrapped cell 26 px apart."""
    lines = [make_line(id_header, 200, 400, height=21), make_line(text_header, 520, 400, height=21)]
    for r, (req_id, first, second) in enumerate(BORDERLESS_REQ_ROWS):
        y = 455 + 64 * r
        lines += [make_line(req_id, 200, y, height=21), make_line(first, 520, y, height=21),
                  make_line(second, 520, y + 26, height=21)]
    return lines


def test_borderless_requirement_table_with_long_sentences_is_kept():
    """An ID column beside a column of whole requirement sentences is a table, not prose. Such a
    table holds many words per cell, which is normally the sign of running text, so it used to be
    thrown away - even though its header row says plainly what the wide column holds."""
    found = se.detect_aligned_tables(_borderless_requirement_lines("Requirement ID", "Requirement Text"),
                                     DPI, set())
    assert found, "a borderless requirement table with real sentences was dropped"
    grid = found[0][0].grid
    words_per_cell = (sum(se.word_count(c) for row in grid for c in row)
                      / max(sum(1 for row in grid for c in row if c), 1))
    assert words_per_cell > 10, f"fixture must be wordy enough to exercise the limit ({words_per_cell:.1f})"
    assert len(grid) == 5 and len(grid[0]) == 2, grid
    assert [r[0] for r in grid[1:]] == ["SRS-101", "SRS-102", "SRS-103", "SRS-104"], grid
    assert "light precipitation" in grid[1][1], grid[1][1]      # the wrapped line joined its own row


def test_wordy_columns_without_a_requirement_header_are_still_prose():
    """The relaxed limit is earned by the header row alone. The very same wordy layout under
    headers that promise nothing stays what it looks like: running text, not a table."""
    assert not se.detect_aligned_tables(_borderless_requirement_lines("Ref", "Notes"), DPI, set())


def _i2t_rows(rows: list):
    """A stand-in for one table as img2table returns it: cell values with the lines that share a
    cell joined by newlines, which is how a row that swallowed several rows of text shows up."""
    return types.SimpleNamespace(content={r: [types.SimpleNamespace(value=v) for v in row]
                                          for r, row in enumerate(rows)})


def test_a_table_whose_rows_were_never_ruled_is_recognised():
    """Every column of the one data row holds several lines at once: the rows were never ruled."""
    et = _i2t_rows([["Paragraph", "Title", "I", "A", "D", "T"],
                    ["3.2.1.1\n3.2.1.2\n3.2.2.1", "Detection range\nRange accuracy\nWeight",
                     "x", "", "", "x\nx"]])
    assert se._rows_are_under_split(et), "a table with no row separators was not recognised"


def test_a_sparse_matrix_whose_rows_were_never_ruled_is_recognised():
    """A verification matrix is mostly ticks, so only its left-hand column shows the crowding.
    One column holding more lines than the table has rows, beside columns of nothing but marks,
    is the giveaway."""
    et = _i2t_rows([["Paragraph", "I", "A", "D", "T", "S", "E"],
                    ["3.4.1.1\n3.4.1.2\n3.4.2.1\n3.4.2.2\n3.4.3.1\n3.4.3.2", "x", "x", "", "x", "x", ""]])
    assert se._rows_are_under_split(et), "a sparse matrix with no row separators was not recognised"


def test_a_ruled_table_whose_cells_wrap_is_left_alone():
    """The case that must NOT be touched: a properly ruled requirement table whose wide column
    wraps over two or three lines. Treating that as a missing separator would turn every wrapped
    line into a requirement of its own."""
    et = _i2t_rows([["Req ID", "Parameter", "Requirement", "Method"],
                    ["ENV-001", "Operating\ntemperature",
                     "The radar shall operate within\nspecification from -40 C to +71 C.", "T"],
                    ["ENV-005", "Salt fog",
                     "The radar shall withstand exposure to\nsalt fog per MIL-STD-810H,\nMethod 509.7.", "T"],
                    ["ENV-007", "Rain", "The radar should operate in rainfall\nrates up to 50 mm/hr.", "D"]])
    assert not se._rows_are_under_split(et), "a ruled table whose cells wrap must be left alone"


def test_a_checklist_with_tick_columns_and_a_deep_cell_is_left_alone():
    """A deeply wrapped cell beside tick columns is still an ordinary table while the table has
    more rows than any one cell has lines."""
    et = _i2t_rows([["Step", "Description", "Done", "N/A"],
                    ["1", "Check the\nconnector\nfor damage", "x", ""],
                    ["2", "Measure the\ninsulation", "x", ""],
                    ["3", "Record the\nserial number", "", "x"],
                    ["4", "Refit the cover", "x", ""]])
    assert not se._rows_are_under_split(et), "an ordinary checklist must be left alone"


def test_rows_are_recut_from_the_text_when_the_rules_do_not_describe_them():
    """The last resort: cut the rows ourselves, half-way down the white gap between the lines of
    text, keeping the columns exactly as the printed rules give them."""
    xs, ys = [300, 800, 1200], (400, 700)
    cell_boxes = [[(xs[0], ys[0], xs[1], ys[1]), (xs[1], ys[0], xs[2], ys[1])]]
    lines = []
    for r, (left, right) in enumerate([("3.2.1.1", "Detection range"), ("3.2.1.2", "Range accuracy"),
                                       ("3.2.2.1", "Weight")]):
        y = 420 + 90 * r
        lines += [make_line(left, xs[0] + 10, y, height=30), make_line(right, xs[1] + 10, y, height=30)]
    recut = se._resplit_rows(cell_boxes, lines)
    assert recut is not None and len(recut) == 3, recut
    assert [cb[0][0] for cb in recut] == [xs[0]] * 3, recut      # columns untouched
    assert recut[0][0][1] == ys[0] and recut[-1][0][3] == ys[1], recut   # the band is fully covered
    tops = [cb[0][1] for cb in recut]
    assert tops == sorted(tops) and len(set(tops)) == 3, tops    # three separate, ordered bands
    assert se._resplit_rows(cell_boxes, lines[:2]) is None       # one row of text: nothing to cut


def test_a_header_band_split_by_the_row_inference_is_put_back_together():
    """A sideways header needs a tall band, and the fragments read in it ("DEM" above "ON") can
    look like two rows of text. The slices must be rejoined before the band is read again,
    otherwise the real header row is mistaken for the table's first row of data."""
    grid = [["", "", "", "", "DEM", ""],
            ["Paragraph", "Title", "INS OON", "ANS T IS", "ON", "TEST"],
            ["3.2.1.1", "Detection range", "", "", "", "X"],
            ["3.2.2.1", "Weight", "X", "", "", ""]]
    conf = [[0.4] * 6, [0.9] * 6, [0.99] * 6, [0.99] * 6]
    words = [[[] for _ in range(6)] for _ in grid]
    heights = [(300, 372), (372, 552), (552, 619), (619, 686)]     # a sliver above a tall band
    boxes = [[(100 + 80 * c, y0, 180 + 80 * c, y1) for c in range(6)] for y0, y1 in heights]
    merges = se._collapse_header_band(grid, conf, boxes, words, [(2, 0, 3, 0)])
    assert len(grid) == 3, grid
    assert grid[0] == ["Paragraph", "Title", "INS OON", "ANS T IS", "DEM ON", "TEST"], grid[0]
    assert boxes[0][4] == (420, 300, 500, 552), boxes[0][4]        # the crop covers both slices
    assert conf[0][0] == 0.4 and merges == [(1, 0, 2, 0)], (conf[0][0], merges)


def test_evenly_sized_rows_are_never_collapsed():
    """The rejoining above must only ever touch a genuinely tall band, not an ordinary table whose
    first row happens to have a single filled cell."""
    grid = [["Notes", "", "", ""], ["Pin", "Signal", "Level", "Use"], ["1", "+28V", "28 V", "Power"],
            ["2", "RTN", "0 V", "Return"]]
    conf = [[1.0] * 4 for _ in grid]
    boxes = [[(100 + 80 * c, 300 + 60 * r, 180 + 80 * c, 360 + 60 * r) for c in range(4)]
             for r in range(4)]
    assert se._collapse_header_band(grid, conf, boxes, [[[] for _ in range(4)] for _ in grid], []) == []
    assert len(grid) == 4 and grid[0][0] == "Notes", grid


def test_unrotate_box_maps_sideways_text_back_to_the_page():
    """The inverse of a 90 degree rotation, used to put a sideways header back on its own column.
    Getting the direction wrong would silently put every header on the wrong column."""
    h, w = 200, 80                                   # a tall, narrow header strip
    # a box in the image produced by turning the strip 90 deg clockwise (that image is w x h)
    assert se._unrotate_box((10, 5, 60, 25), 90, (h, w)) == (5, 140, 25, 190)
    assert se._unrotate_box((10, 5, 60, 25), 270, (h, w)) == (55, 10, 75, 60)
    # a full width box maps back to the full height of the strip, whichever way it was turned
    for rot in (90, 270):
        x0, y0, x1, y1 = se._unrotate_box((0, 0, h, w), rot, (h, w))
        assert (x0, y0, x1, y1) == (0, 0, w, h), (rot, (x0, y0, x1, y1))


def test_sideways_column_headers_are_read_and_land_on_their_own_columns():
    """The point of the sideways pass: "INSPECTION" printed vertically above the third column has
    to become the THIRD column's header, not the second's or the fourth's. The fake recogniser
    below returns each name where the real one would find it after the band is turned upright,
    so what is under test is the mapping back onto the columns, not the recognition."""
    xs = [300, 720, 1180, 1320, 1460, 1600, 1740]
    header_box = (xs[0], 300, xs[-1], 560)               # the tall band above the data rows
    band_w, band_h = header_box[2] - header_box[0], header_box[3] - header_box[1]
    names = {2: "INSPECTION", 3: "ANALYSIS", 4: "DEMONSTRATION", 5: "TEST"}

    class FakeOcr:
        def read(self, image, min_conf=None):
            lines = []
            for col, name in names.items():
                # forward 90 deg anticlockwise turn of the band: strip (x, y) -> (y, band_w - x),
                # so a column's x range becomes a y range in the upright image
                sx0, sx1 = xs[col] - header_box[0], xs[col + 1] - header_box[0]
                box = (20, band_w - sx1, band_h - 20, band_w - sx0)
                lines.append(se.Line(name, 0.95, box, [se.Word(name, 0.95, box)]))
            return lines

    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    cv2.rectangle(img, (header_box[0], header_box[1]), (header_box[2], header_box[3]), 0, 2)
    bands = [(xs[c], xs[c + 1]) for c in range(6)]
    assert se.read_sideways_headers(img, header_box, bands, FakeOcr(), rotation=270) == names


def test_sideways_headers_are_only_read_where_the_headers_are_missing():
    """A header band that OCR already read normally must be left exactly as it is."""
    xs = [300, 720, 1180, 1320, 1460, 1600, 1740]
    ys = [400 + 58 * i for i in range(8)]
    img, lines = _draw_table(_vcrm_cells(), xs, ys, h_lines=False)

    class ExplodingOcr:
        def read(self, image, min_conf=None):
            raise AssertionError("the sideways pass must not run when the headers were read normally")

    table = se.detect_tables(img, lines, DPI, settings(detect_tables=True), ocr=ExplodingOcr())[0][0]
    assert table.grid[0] == ["Paragraph", "Title", "I", "A", "D", "T"], table.grid[0]


# =====================================================================================================================
# Records: telling a row of a table from the lines its cells wrap onto
#
# Where a table's row separators were never printed, the rows have to be worked out from the text,
# and the first thing that goes wrong is putting every LINE on a row of its own. These cases come
# from pages supplied after a run against real Systems Engineering material.
# =====================================================================================================================
def test_gap_threshold_splits_a_tables_two_spacings():
    """Wrapped lines sit tight together, records are set apart; the dividing line is measured from
    the table itself because the leading differs from one document to the next."""
    gaps = [18, 1, 3, 23, -2, -2, 24, 22, -1, 0]          # measured off a supplied page
    cut = se._gap_threshold(gaps, 36)
    assert cut is not None and 3 < cut < 18, cut
    assert [g > cut for g in gaps] == [True, False, False, True, False, False, True, True, False, False]


def test_evenly_spaced_lines_have_no_threshold():
    """A matrix of one-line entries has one spacing only: there is nothing to split, and saying so
    is what keeps every one of its rows a record of its own."""
    assert se._gap_threshold([20, 21, 19, 20, 22], 36) is None
    assert se._gap_threshold([18, 1], 36) is None                      # too few gaps to judge


def test_record_breaks_follow_the_key_column():
    """The strongest signal: a value in the left-hand column starts a record, and a line without
    one continues the record above, however many such lines there are."""
    ink = [(0, 30), (40, 70), (72, 100), (102, 130), (160, 190), (192, 220)]
    cols = [{0, 1, 2}, {0, 1, 2}, {1}, {1}, {0, 1, 2}, {1}]
    assert se._record_breaks(ink, cols, 30) == [0, 1, 4]


def test_record_breaks_fall_back_to_the_leading():
    """With no key column to go by - every row fills every column - the spacing decides."""
    ink = [(0, 30), (34, 64), (66, 96), (130, 160), (162, 192)]
    cols = [{0, 1}] * 5
    assert se._record_breaks(ink, cols, 30) == [0, 3]


def test_record_breaks_keep_every_row_when_nothing_distinguishes_them():
    ink = [(0, 30), (50, 80), (100, 130), (150, 180)]
    assert se._record_breaks(ink, [{0, 1}] * 4, 30) == [0, 1, 2, 3]


def test_continuation_rows_are_merged_back_into_their_record():
    """One row per line of text goes in, one row per record comes out, and the merged cell boxes
    cover the whole record so its text is gathered from all of its lines."""
    xs = [100, 400, 900]
    ys = [(0, 30), (34, 64), (66, 96), (130, 160)]          # record, wrap, wrap, record
    cell_boxes = [[(xs[0], y0, xs[1], y1), (xs[1], y0, xs[2], y1)] for y0, y1 in ys]
    lines = [make_line("SYS-101", xs[0] + 5, 0, height=30), make_line("The radar shall detect", xs[1] + 5, 0, height=30),
             make_line("a target at a range of", xs[1] + 5, 34, height=30),
             make_line("not less than 150 km.", xs[1] + 5, 66, height=30),
             make_line("SYS-102", xs[0] + 5, 130, height=30), make_line("The radar shall track", xs[1] + 5, 130, height=30)]
    merged = se._merge_continuation_rows(cell_boxes, lines)
    assert len(merged) == 2, merged
    assert merged[0][1] == (xs[1], 0, xs[2], 96), merged[0][1]         # the record's whole height
    assert merged[1][0] == (xs[0], 130, xs[1], 160), merged[1][0]


def test_a_grid_of_real_rows_is_left_alone_by_the_merge():
    """A matrix whose entries are one line each must come through untouched."""
    xs, ys = [100, 400, 900], [(0, 30), (50, 80), (100, 130)]
    cell_boxes = [[(xs[0], y0, xs[1], y1), (xs[1], y0, xs[2], y1)] for y0, y1 in ys]
    lines = []
    for r, (para, title) in enumerate([("3.2.1.1", "Detection range"), ("3.2.1.2", "Range accuracy"),
                                       ("3.2.2.1", "Weight")]):
        y = ys[r][0]
        lines += [make_line(para, xs[0] + 5, y, height=30), make_line(title, xs[1] + 5, y, height=30)]
    assert se._merge_continuation_rows(cell_boxes, lines) == cell_boxes


def test_a_candidate_that_starts_inside_a_record_is_rejected():
    """Aligned-text detection can lock on to the lower half of a table, taking its wrapped lines
    for rows and missing the header and first record above them."""
    lines = [make_line("READY Set when the power-on self test has", 200, 100, height=30),
             make_line("completed without a fault.", 400, 132, height=30),
             make_line("FAULT Set when any line replaceable unit", 200, 190, height=30)]
    assert se._cut_out_of_a_record((200, 130, 1200, 230), lines)       # begins a third of a line below
    assert not se._cut_out_of_a_record((200, 90, 1200, 230), lines)    # begins at the top of the table


def test_a_cell_wrapping_over_two_lines_does_not_end_a_borderless_table():
    """The bug behind a whole table being lost: the run stopped at the first cell that wrapped
    over two lines, because it demanded that the very next row have cells again."""
    lines = [make_line("Req ID", 200, 400, height=21), make_line("Requirement", 520, 400, height=21),
             make_line("Method", 1500, 400, height=21)]
    rows = [("SYS-101", ["The radar shall detect a target having a radar", "cross section of 1 square meter at a range",
                         "of not less than 150 km."], "T"),
            ("SYS-102", ["The radar shall maintain not less than 200", "simultaneous tracks while continuing to",
                         "search the full surveillance volume."], "A, T"),
            ("SYS-103", ["The radar shall operate from 115 VAC."], "T"),
            ("SYS-104", ["The operator console shall display all tracks,", "alerts and status within one second."], "D")]
    y = 455
    for req_id, wrapped, method in rows:
        lines.append(make_line(req_id, 200, y, height=21))
        lines.append(make_line(method, 1500, y, height=21))
        for n, part in enumerate(wrapped):
            lines.append(make_line(part, 520, y + 26 * n, height=21))
        y += 26 * len(wrapped) + 38
    found = se.detect_aligned_tables(lines, DPI, set())
    assert found, "a borderless table whose cells wrap over three lines was lost"
    grid = found[0][0].grid
    assert len(grid) == 5 and len(grid[0]) == 3, grid
    assert [r[0] for r in grid[1:]] == ["SYS-101", "SYS-102", "SYS-103", "SYS-104"], grid
    assert "150 km." in grid[1][1] and "surveillance volume." in grid[2][1], grid
    assert [r[2] for r in grid[1:]] == ["T", "A, T", "T", "D"], grid


def test_two_borderless_tables_on_one_page_are_both_found():
    """Also a guard on the scan itself: the loop that walks the page must move on after each
    table. A version of this code reused its counter inside the table it had just built, so the
    scan restarted for ever and no page with two borderless tables ever finished."""
    lines = []
    for table, top in ((("Signal", "Description", "Remarks"), 300), (("ID", "Requirement", "Method"), 900)):
        lines += [make_line(table[0], 200, top, height=21), make_line(table[1], 520, top, height=21),
                  make_line(table[2], 1400, top, height=21)]
        for n in range(3):
            y = top + 60 + 64 * n
            lines += [make_line(f"ITEM-{n}", 200, y, height=21),
                      make_line("Set when the power-on self test has", 520, y, height=21),
                      make_line("completed without a fault.", 520, y + 26, height=21),
                      make_line("None.", 1400, y, height=21)]
    found = se.detect_aligned_tables(lines, DPI, set())
    assert len(found) == 2, [(t.n_rows, t.n_cols) for t, _, _, _ in found]
    for table, _tbox, _used, _c in found:
        assert (table.n_rows, table.n_cols) == (4, 3), table.grid


def test_boxed_table_with_only_a_header_rule_gives_one_row_per_record():
    """The layout the supplied pages showed most often: a box and a line under the headers, with
    nothing between the rows, and requirement cells that wrap over three lines."""
    xs = [300, 700, 1500, 1750]
    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    cv2.rectangle(img, (xs[0], 380), (xs[-1], 1180), 0, 2)
    for x in xs[1:-1]:
        cv2.line(img, (x, 380), (x, 1180), 0, 2)
    cv2.line(img, (xs[0], 440), (xs[-1], 440), 0, 2)                   # under the headers only
    lines = []

    def put(text, x, y):
        words = _draw_words(img, text, x, y, scale=0.7)
        lines.append(se.Line(text, 0.97, se.box_union(w.box for w in words), words))

    for text, x in (("ID", xs[0]), ("Requirement", xs[1]), ("Verification", xs[2])):
        put(text, x + 12, 396)
    y = 460
    for n, (req_id, wrapped, method) in enumerate([
            ("IFC-101", ["The radar shall detect a target having", "a radar cross section of 1 square meter",
                         "at a range of not less than 150 km."], "T"),
            ("IFC-102", ["The radar shall maintain not less than", "200 simultaneous tracks while it",
                         "searches the full surveillance volume."], "A, T"),
            ("IFC-103", ["The radar shall operate from 115 VAC."], "T")]):
        put(req_id, xs[0] + 12, y)
        put(method, xs[2] + 12, y)
        for i, part in enumerate(wrapped):
            put(part, xs[1] + 12, y + 34 * i)
        y += 34 * len(wrapped) + 40
    found = se.detect_tables(img, lines, DPI, settings(detect_tables=True))
    assert found, "a table boxed with only a header rule was not detected"
    grid = found[0][0].grid
    assert len(grid) == 4, grid                                        # header + three records, not per line
    assert [r[0] for r in grid[1:]] == ["IFC-101", "IFC-102", "IFC-103"], grid
    assert "150 km." in grid[1][1], grid[1][1]
    assert [r[2] for r in grid[1:]] == ["T", "A, T", "T"], grid


def test_a_page_saved_at_screen_size_is_enlarged_enough_to_read():
    """A page exported at screen size is about a third of the resolution the recogniser wants.
    Assuming the usual 300 dpi and then shrinking toward 220 made such a page worse, not better;
    the resolution estimated from the text has to be believed, and the enlargement allowed to go
    past doubling. Run on one of the supplied pages, which is exactly that kind of image."""
    page = HERE / "pages" / "specG_page1.png"
    if not page.exists():                       # the supplied pages are optional
        return
    gray = cv2.imread(str(page), cv2.IMREAD_GRAYSCALE)
    estimated = se.estimate_dpi_from_text(gray)
    assert estimated is not None and estimated < 100, estimated        # a screen-sized page, not a scan
    s = settings(auto_rotate=False, deskew=False, clean_background=False, denoise=False)
    raw = se.RawPage(1, gray, float(s.fallback_dpi), False)             # no resolution recorded
    prep = se.prepare_page(raw, s, None, None)
    assert prep.ocr_image.shape[1] > 2.5 * gray.shape[1], (gray.shape, prep.ocr_image.shape)
    assert 150 <= prep.dpi <= 300, prep.dpi                             # brought near the target
    assert prep.ocr_image.size / 1e6 <= s.max_page_megapixels


# =====================================================================================================================
# Version and build identity
# =====================================================================================================================
def test_readme_states_the_same_version_as_the_code():
    """The version at the top of the README is what a user compares against the line a run prints,
    so the two must never drift apart. Raise both in the same commit."""
    readme = (HERE.parent / "README.md").read_text(encoding="utf-8")
    stated = re.search(r"^>\s*##\s*Version\s+([0-9]+\.[0-9]+\.[0-9]+)\s*$", readme, re.M)
    assert stated, "README.md must carry a '> ## Version X.Y.Z' heading at the top"
    assert stated.group(1) == se.__version__, (stated.group(1), se.__version__)


def test_build_id_fingerprints_the_code_that_is_running():
    """The build id has to follow the FILE, not the version number, so that a folder carrying a
    half-applied patch or an unreleased edit cannot claim to be a released version."""
    import hashlib
    expected = hashlib.sha1(Path(se.__file__).read_bytes()).hexdigest()[:7]
    assert se.build_id().startswith(expected), (se.build_id(), expected)
    assert se.version_line() == f"spec_extractor {se.__version__} (build {se.build_id()})"
    assert se.version_line().startswith(f"spec_extractor {se.__version__} (build {expected}")


# =====================================================================================================================
# Lists: spacing is trusted over the marker character
#
# A marker is one or two characters, which is exactly what OCR drops or mistakes, while a list's
# indentation is printed identically for every item. These cases all come from real reports of a
# list's LAST entry being glued onto the entry above it, or dropped out of the list altogether.
# =====================================================================================================================
LIST_STEM = "The radar shall provide the following modes:"
LIST_ITEMS = ["Long range search mode.", "Track-while-scan mode.", "Built-in test mode."]


def _list_rows(markers, items=None, indent=36, stem=LIST_STEM):
    """The stem followed by one line per item, each line "<marker> <text>" at `indent`."""
    items = items or LIST_ITEMS
    return [stem] + [(indent, f"{m} {t}".strip()) for m, t in zip(markers, items)]


def _list_requirements(rows):
    _doc, items = run({1: make_lines(rows)})
    return [it.text for it in requirements(items)]


def test_every_ordinary_list_format_yields_one_row_per_item():
    """The formats a specification actually uses, each of which must give one row per item."""
    for name, markers in (("letters", ["a.", "b.", "c."]),
                          ("letters in brackets", ["(a)", "(b)", "(c)"]),
                          ("digits with a period", ["1.", "2.", "3."]),
                          ("digits in brackets", ["(1)", "(2)", "(3)"]),
                          ("digits with a bracket", ["1)", "2)", "3)"]),
                          ("roman numerals", ["i.", "ii.", "iii."]),
                          ("dashes", ["-", "-", "-"]),
                          ("bullets", ["•", "•", "•"])):
        rows = _list_requirements(_list_rows(markers))
        assert len(rows) == 3, (name, rows)
        assert all(LIST_STEM in r for r in rows), (name, rows)
        assert rows[-1].endswith(LIST_ITEMS[-1]), (name, rows)


def test_list_spacing_variations_all_yield_one_row_per_item():
    """The same list set with different spacing: tight, a blank line between items, a wide tab
    between the marker and its text, and an item indented differently from its siblings."""
    tight = _list_requirements(_list_rows(["a.", "b.", "c."]))
    spaced = _list_requirements([LIST_STEM, (36, "a. Long range search mode."), None,
                                 (36, "b. Track-while-scan mode."), None, (36, "c. Built-in test mode.")])
    tabbed = _list_requirements(_list_rows(["a." + " " * 8, "b." + " " * 8, "c." + " " * 8]))
    ragged = _list_requirements([LIST_STEM, (36, "a. Long range search mode."),
                                 (36, "b. Track-while-scan mode."), (96, "c. Built-in test mode.")])
    for name, rows in (("tight", tight), ("blank line between", spaced),
                       ("wide tab after the marker", tabbed), ("last item indented further", ragged)):
        assert len(rows) == 3, (name, rows)
        assert rows[-1].endswith(LIST_ITEMS[-1]), (name, rows)


def test_a_misread_marker_does_not_end_the_list():
    """The heart of it: the last marker comes back as the wrong letter, the wrong case, a digit
    where letters were used, or glued to its text. None of those may end the list, because the
    indentation still says the line is an item."""
    for name, last in (("wrong letter", "e."), ("a letter shaped like another", "o."),
                       ("upper case", "C."), ("a digit among letters", "3."),
                       ("a bracket instead of a period", "c)"), ("run together with the text", "c.Built-in")):
        markers = ["a.", "b.", last]
        items = LIST_ITEMS[:2] + (["test mode."] if last == "c.Built-in" else [LIST_ITEMS[2]])
        rows = _list_requirements(_list_rows(markers, items))
        assert len(rows) == 3, (name, rows)
        assert "test mode." in rows[-1], (name, rows)
        assert LIST_STEM in rows[-1], (name, rows)


def test_a_marker_lost_altogether_does_not_end_the_list():
    """The marker is gone, not merely wrong. The line still sits level with the items above it and
    the item above finished its sentence, so it is the next item."""
    rows = _list_requirements([LIST_STEM, (36, "a. Long range search mode."),
                               (36, "b. Track-while-scan mode."), (36, "Built-in test mode.")])
    assert len(rows) == 3, rows
    assert rows[-1].endswith("Built-in test mode."), rows


def test_a_misread_digit_does_not_end_a_numbered_list():
    for last in ("8.", "5.", "l."):
        rows = _list_requirements(_list_rows(["1.", "2.", last]))
        assert len(rows) == 3, (last, rows)
        assert rows[-1].endswith(LIST_ITEMS[-1]), (last, rows)


def test_a_wrapped_item_is_still_one_item():
    """The guard on all of the above: a line that merely continues the sentence of the item above
    must NOT become an item of its own, however it is indented."""
    rows = _list_requirements([LIST_STEM, (36, "a. Long range search mode."),
                               (36, "b. Track-while-scan mode."),
                               (36, "c. Built-in test mode which shall run at power"),
                               (36, "on and at the operator's request.")])
    assert len(rows) == 3, rows
    assert "operator's request." in rows[-1], rows


def test_a_heading_after_a_list_is_still_a_heading():
    """The counter-case to treating a numbered line level with a list as the next item: a section
    heading in capitals after a list stays a heading and does not join the list."""
    doc, items = run({1: make_lines([LIST_STEM, (36, "a. Long range search mode."),
                                     (36, "b. Track-while-scan mode."), (36, "c. Built-in test mode."),
                                     (36, "4. VERIFICATION"),
                                     "4.1 Tests. Tests shall be witnessed by the procuring activity."])})
    headings = [b.text for b in doc.blocks if b.kind == "heading"]
    assert "4. VERIFICATION" in headings, [b.kind + ":" + b.text for b in doc.blocks]
    assert len(requirements(items)) == 4, texts(items)


def test_a_wide_tab_list_that_also_loses_a_marker_is_a_known_limitation():
    """Documented, not fixed. With a WIDE TAB the marker is its own OCR box, so an item whose
    marker is also lost leaves only its text, sitting exactly where a wrapped line would sit and
    following a finished sentence. Nothing in the geometry separates the two, so the text joins the
    item above. Pinned here so a future change to the list rules shows up as a change in THIS
    behaviour rather than passing unnoticed."""
    lines = [make_line(LIST_STEM, LEFT, 300)]
    y = 300 + PITCH
    for marker, text in (("a.", LIST_ITEMS[0]), ("b.", LIST_ITEMS[1]), (None, LIST_ITEMS[2])):
        if marker:
            lines.append(make_line(marker, LEFT + 36, y))
        lines.append(make_line(text, LEFT + 300, y))
        y += PITCH
    _doc, items = run({1: lines})
    rows = [it.text for it in requirements(items)]
    assert len(rows) == 2, rows                      # the third item is not recovered
    assert rows[-1].endswith(LIST_ITEMS[2]), rows    # its text is kept, on the item above


# =====================================================================================================================
# Verification matrices with a legend band
#
# The shape reported from real material: a LEGEND across the top, then a header row whose own label
# wraps, then many narrow mark columns, with the columns ruled and nothing between the rows. It came
# out as one row holding every requirement, with the X marks bundled into it.
# =====================================================================================================================
def test_the_split_is_taken_at_the_lowest_clear_step():
    """Measured off such a matrix. The gaps inside a record are alike, but the gaps BETWEEN records
    are not: the header band sits 20 px above the first record while the records sit 46-49 px
    apart. Cutting at the BIGGEST step lands between those two kinds of record gap and swallows the
    first record into the header; cutting at the lowest clear step keeps them apart."""
    gaps = [2, 64, 1, 20, 49, 49, 48, 46, 47, 47]
    cut = se._gap_threshold(gaps, 40)
    assert cut is not None and 2 < cut < 20, cut
    assert [g > cut for g in gaps] == [False, True, False, True, True, True, True, True, True, True]


def test_the_lowest_step_rule_still_groups_a_wrapped_requirement_table():
    """The same rule on the gaps of a requirement table whose cells wrap over three lines."""
    gaps = [18, 1, 3, 23, -2, -2, 24, 22, -1, 0]
    cut = se._gap_threshold(gaps, 36)
    assert cut is not None and 3 < cut < 18, cut
    assert [g > cut for g in gaps] == [True, False, False, True, False, False, True, True, False, False]


def test_a_matrix_cell_holding_a_column_number_and_a_tick_is_not_a_heading():
    """"1 X" - a column header run together with the tick below it - used to read as the heading
    "1. X", so the whole matrix was dismissed as running text and the broken reading kept."""
    matrix = [["Requirement reference", "1 X", "2", "3 X", "4"],
              ["3.2.1.2", "", "X", "", ""],
              ["3.2.1.3", "X", "", "", "X"],
              ["3.2.2.1", "", "", "X", ""]]
    assert not se._reads_like_prose(matrix), matrix
    # a real numbered heading inside a grid is still caught
    assert se._reads_like_prose([["4. VERIFICATION", ""], ["4. VERIFICATION", ""],
                                 ["Each requirement shall be", "verified as specified"]])


def test_row_keys_tell_a_record_from_a_wrapped_header():
    """A legend band of two lines, then a header whose label wraps onto a second line, then the
    records. Only the records carry a key in the left-hand column, and the bands above the first
    key are separated from each other by their spacing."""
    ink = [(0, 30), (32, 62), (107, 137), (134, 164), (178, 208), (208, 238),
           (239, 269), (300, 330), (330, 360), (360, 390), (389, 419)]
    keys = ["LEGEND: 1 = First article", "Dimensional C = Functional", "Requirement", "reference",
            "3.4.1.1", "", "3.4.1.2", "3.4.2.1", "3.4.2.2", "", "3.4.3.1"]
    cols = [set(range(11))] * 2 + [{0, 1}, set(range(11))] + [set(range(7)), {0}, set(range(5)),
                                                              set(range(7)), set(range(5)), {0}, set(range(7))]
    starts = se._record_breaks(ink, cols, 32.5, keys)
    assert starts == [0, 2, 4, 6, 7, 8, 10], starts     # legend, header, then one per requirement


def test_what_counts_as_a_row_key():
    """A paragraph number or an identifier names a record; a word, a band of legend text, a tick or
    an empty cell does not. "2.5" counts, because paragraph 2.5 is a perfectly ordinary key - it
    reads as an AQL percentage only in the AQL column, and this is asked of the LEFT-HAND column."""
    for key in ("3.2.1.4", "3.4.1.1", "SRS-101", "IFC-010", "A.1.2", "2.5"):
        assert se._looks_like_row_key(key), key
    for not_key in ("Requirement", "reference", "LEGEND: 1 = First article", "", "Visual", "X",
                    "Inspection method", "Visual and functional"):
        assert not se._looks_like_row_key(not_key), not_key


def test_a_legend_matrix_with_a_wrapped_header_keeps_one_row_per_requirement():
    """End to end on a drawn page: legend band, a header whose label wraps, eleven columns, column
    rules and no line between the rows. Every requirement must keep its own row and its own marks."""
    xs = [260, 700, 810, 920, 1030, 1140, 1250, 1360, 1470, 1620, 1810]
    img = np.full((PAGE_H, PAGE_W), 255, np.uint8)
    top, head_top, first = 360, 470, 600
    rows = [("3.2.1.1", [0, 2], [0, 2], "2.5"), ("3.2.1.2", [1], [1], "1.0"),
            ("3.2.1.3", [0, 3], [0, 3], "0.65"), ("3.2.2.1", [2], [2], "4.0")]
    bottom = first + 64 * len(rows)
    cv2.rectangle(img, (xs[0], top), (xs[-1], bottom), 0, 2)
    for x in xs[1:-1]:
        cv2.line(img, (x, head_top), (x, bottom), 0, 2)          # column rules below the legend
    cv2.line(img, (xs[0], head_top), (xs[-1], head_top), 0, 2)   # under the legend
    cv2.line(img, (xs[0], first - 16), (xs[-1], first - 16), 0, 2)   # under the headers
    lines = []

    def put(text, x, y, scale=0.62):
        words = _draw_words(img, text, x, y, scale=scale)
        lines.append(se.Line(text, 0.97, se.box_union(w.box for w in words), words))

    put("LEGEND: 1 = First article  2 = Periodic  3 = Lot sample  4 = Continuous", xs[0] + 10, top + 14)
    put("A = Visual  B = Dimensional  C = Functional  D = Environmental", xs[0] + 10, top + 46)
    put("Requirement", xs[0] + 10, head_top + 12)                # the label WRAPS onto a second line
    put("reference", xs[0] + 10, head_top + 44)
    for c, label in enumerate(["1", "2", "3", "4", "A", "B", "C", "D"]):
        put(label, xs[c + 1] + 12, head_top + 44)
    put("AQL", xs[9] + 12, head_top + 44)
    for r, (ref, nums, letters, aql) in enumerate(rows):
        y = first + 64 * r
        put(ref, xs[0] + 10, y)
        for c in nums:
            put("X", xs[c + 1] + 12, y)
        for c in letters:
            put("X", xs[c + 5] + 12, y)
        put(aql, xs[9] + 12, y)
    found = se.detect_tables(img, lines, DPI, settings(detect_tables=True))
    assert found, "a matrix with a legend band and a wrapped header was not detected"
    grid = found[0][0].grid
    assert len(grid) == 2 + len(rows), [r[0] for r in grid]      # legend, header, one per requirement
    assert "LEGEND" in grid[0][0], grid[0]
    assert grid[1][0].replace(" ", "").startswith("Requirement"), grid[1]
    assert [r[0] for r in grid[2:]] == [r[0] for r in rows], [r[0] for r in grid]
    for r, (ref, nums, letters, aql) in enumerate(rows):
        marked = [c for c in range(1, 9) if grid[2 + r][c].strip()]
        assert marked == sorted([n + 1 for n in nums] + [l + 5 for l in letters]), (ref, marked, grid[2 + r])


def test_a_lost_space_after_a_paragraph_number_is_repaired():
    """A photocopy loses the space after a paragraph number, or reads it as a speck of dirt.
    Both are repaired, while list markers, part numbers and file names are left untouched."""
    assert se.remove_ocr_specks("4.2Extended verification.") == "4.2 Extended verification."
    assert se.remove_ocr_specks("3.2.2.2.Input power.") == "3.2.2.2. Input power."
    assert se.remove_ocr_specks("3.1Purpose.") == "3.1 Purpose."
    # a real full stop in front of the capital survives, so a cross-reference still reads as one
    assert se.remove_ocr_specks("per 3.2.1.The unit") == "per 3.2.1. The unit"
    for unchanged in ("MIL-STD-1553B bus", "MIL-STD-461G.Method", "1.Built-in test", "10.The unit",
                      "514.8Requires", "config.xml", "3.2.2.1"):
        assert se.remove_ocr_specks(unchanged) == unchanged, unchanged


def test_two_numbered_paragraphs_in_one_block_keep_their_own_numbers():
    """A faint scan can lose the blank line between two numbered paragraphs, leaving both in one
    block. Each requirement must still carry the number of the paragraph it was written under."""
    lines = make_lines(["3.2.2.1 Weight. The equipment shall not exceed 45 kilograms.",
                        "3.2.2.2 Input power. The equipment shall operate from 115 VAC."])
    _doc, items = run({1: lines})          # no blank line between them: the layout sees ONE block
    rows = requirements(items)
    assert len(rows) == 2, texts(items)
    assert [r.doc_ref for r in rows] == ["3.2.2.1", "3.2.2.2"], [r.doc_ref for r in rows]
    assert "45 kilograms" in rows[0].text and "3.2.2.2" not in rows[0].text, rows[0].text
    assert rows[1].text.startswith("The equipment shall operate"), rows[1].text
    assert rows[1].title == "Input power", rows[1].title


def test_a_second_numbered_paragraph_without_a_title_is_not_lost():
    """Both paragraphs on ONE line, so they are one block. With no title after the second number,
    '... 45 kilograms. 3.2.2.2 The equipment shall ...' is a single sentence (a full stop before a
    digit does not end one); the second requirement must still become its own row, not vanish."""
    for text in ("3.2.2.1 Weight. The equipment shall not exceed 45 kilograms. "
                 "3.2.2.2 Input power. The equipment shall operate from 115 VAC.",
                 "3.2.2.1 Weight. The equipment shall not exceed 45 kilograms. "
                 "3.2.2.2 The equipment shall operate from 115 VAC."):
        _doc, items = run({1: [make_line(text)]})
        rows = requirements(items)
        assert [(r.doc_ref, r.text) for r in rows] == [
            ("3.2.2.1", "The equipment shall not exceed 45 kilograms."),
            ("3.2.2.2", "The equipment shall operate from 115 VAC.")], [(r.doc_ref, r.text) for r in rows]


def test_a_list_under_the_second_numbered_paragraph_of_a_block_carries_that_number():
    """A stem in the second of two merged numbered paragraphs: its list items belong to THAT
    paragraph, so they must not be filed under the first paragraph's number."""
    lines = [make_line("3.4.1 Power. The unit shall draw less than 40 W. 3.4.2 Modes. The unit shall provide:")]
    lines += make_lines([(80, "a. Standby mode."), (80, "b. Operate mode.")], y0=300 + PITCH)
    _doc, items = run({1: lines})
    rows = requirements(items)
    refs = [r.doc_ref for r in rows]
    assert refs[0] == "3.4.1", [(r.doc_ref, r.text) for r in rows]
    assert refs[1:] == ["3.4.2 a", "3.4.2 b"], [(r.doc_ref, r.text) for r in rows]


def test_a_cross_reference_is_not_mistaken_for_a_new_paragraph():
    """'... as defined in 3.2.1. Testing shall ...' is one paragraph: the number is a reference in
    running text, not a heading, so the second sentence keeps the block's own number."""
    lines = make_lines(["3.4.1 Test method. The unit shall be tested as defined in 3.2.1.",
                        "Testing shall be witnessed by the procuring activity."])
    _doc, items = run({1: lines})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.4.1"] * len(rows), [(r.doc_ref, r.text) for r in rows]


def test_a_quantity_inside_a_paragraph_is_not_a_new_paragraph():
    """'3.3 V shall' after a full stop is a voltage, not paragraph 3.3."""
    lines = make_lines(["3.5.1 Supply. The rail shall be regulated. 3.3 V shall be held to 2 percent."])
    _doc, items = run({1: lines})
    rows = requirements(items)
    assert rows and all(r.doc_ref == "3.5.1" for r in rows), [(r.doc_ref, r.text) for r in rows]


def _checker(words: list) -> "se.WordChecker":
    from collections import Counter
    counts = Counter(w.lower() for w in words)
    return se.WordChecker(counts, settings(), Counter())


def test_an_ocr_misread_repeated_on_every_page_is_still_flagged():
    """The OCR repeats its mistakes, so 'repeated in the document' cannot mean 'a real term' on its
    own. 'systen' printed beside 'system' is reported; a project term of its own is not."""
    ck = _checker(["system", "systen", "systen", "systen", "the", "status"])
    assert "system" in ck.issue("systen", "systen"), ck.issue("systen", "systen")
    ck = _checker(["monopulse", "monopulse", "monopulse", "boresight", "boresight", "radar"])
    assert ck.issue("monopulse", "monopulse") == "", ck.issue("monopulse", "monopulse")
    assert ck.issue("boresight", "boresight") == "", ck.issue("boresight", "boresight")


def test_a_project_term_is_not_flagged_just_because_english_has_a_near_word():
    """A term of the program's own ('hardpoint') is one edit from nothing the document uses, so
    there is no evidence of a misread and it is left alone however often it appears. The tool also
    carries its own engineering dictionary, so 'boresight' and 'monopulse' are known words."""
    ck = _checker(["hardpoint"] * 4 + ["radar", "antenna", "mounted"])
    assert ck.issue("hardpoint", "hardpoint") == "", ck.issue("hardpoint", "hardpoint")
    for term in ("boresight", "monopulse", "pitot", "waveguide"):
        assert _checker([term]).issue(term, term) == "", term


# =====================================================================================================================
# Command line and file handling
# =====================================================================================================================
def test_page_selection():
    assert se.parse_page_selection("1–3, 7", 10) == [1, 2, 3, 7]         # en dash typed by Word/Outlook
    assert se.parse_page_selection("5-3", 10) == [3, 4, 5]
    assert se.parse_page_selection("8-", 10) == [8, 9, 10]
    assert se.parse_page_selection("", 3) == [1, 2, 3]
    assert se.parse_page_selection("2-40", 4) == [2, 3, 4]
    assert se.parse_page_selection("3-", 2) == []                           # past the end: nothing, not page 2
    for bad in ("1..3", "abc", "-"):
        try:
            se.parse_page_selection(bad, 10)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should be rejected")


def test_keyword_option_accepts_semicolons():
    args = se.build_arg_parser().parse_args(["x.pdf", "--keywords", "shall; must|is required to", "--no-will"])
    s = se.settings_from_args(args)
    assert s.keywords == {"shall": "Mandatory", "must": "Mandatory", "is required to": "Mandatory"}, s.keywords


def test_output_names_never_collide():
    files = [Path("A/spec.pdf"), Path("B/spec.pdf"), Path("B/spec.tif"), Path("C/other.pdf"), Path("D/Spec.pdf")]
    names = se.unique_output_stems(files)
    assert len({v.lower() for v in names.values()}) == len(files), names
    assert names[Path("C/other.pdf")] == "other" and names[Path("B/spec.tif")] == "spec_tif", names


def test_cache_key_changes_with_keywords_and_layout_code():
    a, b = se.Settings(), se.Settings()
    b.keywords = {"shall": "Mandatory", "is to": "Custom keyword"}
    assert a.ocr_fingerprint() != b.ocr_fingerprint()
    assert se._cached_code_hash() != ""
    source = Path(se.__file__).read_text(encoding="utf-8")
    for name in ("RE_UNIT = ", "OCR_KEYWORD_REPAIRS = "):          # patterns the layout rules use are fingerprinted
        position = source.index(name)
        assert source.index("# 6. OCR AND PAGE LAYOUT") < position < source.index("# 7. DOCUMENT-LEVEL CLEAN-UP"), name


def test_image_file_that_cannot_be_written_is_not_fatal():
    with tempfile.TemporaryDirectory() as tmp:
        blocked = Path(tmp) / "page_0001.jpg"
        blocked.mkdir()                                                   # a folder where the file should go
        assert se._imwrite(blocked, np.full((20, 20), 255, np.uint8)) is False


def test_unreadable_image_page_does_not_stop_the_file():
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "three_pages.tif"
        frames = [Image.new("L", (400, 500), 255) for _ in range(3)]
        frames[0].save(path, save_all=True, append_images=frames[1:], dpi=(200, 200))

        def broken(im, number, s):
            if number == 2:
                raise OSError("decoder error -2")
            return real(im, number, s)

        real = se._read_image_frame
        se._read_image_frame = broken
        try:
            pages = list(se._iter_image_pages(path, settings()))
        finally:
            se._read_image_frame = real
    assert [(p.number, bool(p.error)) for p in pages] == [(1, False), (2, True), (3, False)], pages
    assert "decoder error" in pages[1].error


# =====================================================================================================================
# Tested configuration: supported Python versions and the pinned package versions (constraints.txt)
# =====================================================================================================================
def test_python_version_check():
    ok = dict(is_64bit=True, free_threaded=False)
    for version in [(3, 10, 21), (3, 11, 16), (3, 12, 3), (3, 13, 15), (3, 14, 6), (3, 14, 99)]:
        assert se.python_support_problem(version, **ok) == "", version
    for version in [(3, 9, 18), (3, 15, 0), (4, 0, 0)]:
        assert "not a tested version" in se.python_support_problem(version, **ok), version
    assert "32-bit" in se.python_support_problem((3, 12, 3), is_64bit=False, free_threaded=False)
    assert "free-threaded" in se.python_support_problem((3, 14, 6), is_64bit=True, free_threaded=True)
    # setup_windows.bat must accept exactly the same versions (its check and its "py -3.x" search list)
    bat = (HERE.parent / "setup_windows.bat").read_text(encoding="ascii")
    (low_major, low), (high_major, high) = se.SUPPORTED_PYTHON
    assert f"({low_major}, {low}) <= sys.version_info[:2] <= ({high_major}, {high})" in bat
    assert "Py_GIL_DISABLED" in bat and "sys.maxsize > 2**32" in bat
    searched = re.search(r"for %%V in \(([^)]*)\)", bat).group(1).split()
    assert sorted(searched, key=lambda v: tuple(map(int, v.split(".")))) == [f"3.{m}" for m in range(low, high + 1)], searched


def test_constraints_file_pins_every_package_for_every_tested_python():
    from packaging.requirements import Requirement
    requirements = []
    for name in ("requirements.txt", "requirements-dev.txt"):
        for line in (HERE.parent / name).read_text(encoding="utf-8").splitlines():
            entry = line.split("#", 1)[0].strip()
            if entry and not entry.startswith("-r"):
                requirements.append(Requirement(entry))
    (_, low), (_, high) = se.SUPPORTED_PYTHON
    for minor in range(low, high + 1):
        for platform in ("win32", "linux"):
            pinned = se.tested_versions(python=(3, minor), platform=platform)
            for req in requirements:
                name = se.canonical_package_name(req.name)
                needed = not req.marker or se._conditions_hold(str(req.marker), (3, minor), platform)
                assert (name in pinned) == needed, (minor, platform, name)
                if needed:          # the pinned version must also satisfy requirements.txt
                    assert req.specifier.contains(pinned[name], prereleases=True), (minor, name, pinned[name])
            for name in se.RESULT_PACKAGES:      # every package the run report checks has a tested version
                expected = name != "rapid-orientation" or minor < 13
                assert (name in pinned) == expected, (minor, platform, name)
    assert se.tested_versions(python=(3, 10), platform="linux")["numpy"] == "2.2.6"
    assert se.tested_versions(python=(3, 11), platform="linux")["numpy"] == "2.4.6"
    assert se.tested_versions(python=(3, 14), platform="win32")["numpy"] == "2.5.3"
    assert "colorama" in se.tested_versions(python=(3, 12), platform="win32")
    assert "colorama" not in se.tested_versions(python=(3, 12), platform="linux")
    # Python versions compare as numbers ("3.9" is older than "3.10"), conditions can be combined
    assert se._conditions_hold('python_version < "3.10"', (3, 9), "linux")
    assert not se._conditions_hold('sys_platform == "win32" and python_version < "3.11"', (3, 12), "win32")
    with tempfile.TemporaryDirectory() as tmp:
        odd = Path(tmp) / "constraints.txt"
        odd.write_text('numpy==2.5.3; platform_machine == "AMD64"\n', encoding="utf-8")
        try:
            se.tested_versions(odd)
            raise AssertionError("an unsupported condition must be reported, not ignored")
        except ValueError as exc:
            assert "unsupported condition" in str(exc), exc
        assert se.tested_versions(Path(tmp) / "missing.txt") == {}


def test_configuration_report_names_every_difference():
    tested = {"numpy": "2.5.3", "rapidocr": "3.9.2"}
    assert se.configuration_differences({"numpy": "2.5.3", "rapidocr": "3.9.2"}, tested) == []
    # the classifier is neither tested nor installed on Python 3.13+: that is the tested setup, not a difference
    assert se.configuration_differences({"numpy": "2.5.3", "rapid-orientation": None}, tested) == []
    differences = se.configuration_differences({"numpy": "2.6.0", "rapidocr": None, "rapid-orientation": "0.0.11"}, tested)
    assert differences == ["numpy 2.6.0 is installed (tested with 2.5.3)",
                           "rapidocr is not installed (tested with 3.9.2)",
                           "rapid-orientation 0.0.11 is installed, but it is not part of the tested set for this Python"], differences
    differences = se.configuration_differences({}, {}, python_problem="Python 3.15.0 is not a tested version")
    assert differences[0].startswith("Python 3.15.0") and "constraints.txt was not found" in differences[1], differences
    assert se.configuration_status(docling_used=True)[1][-1] == se.DOCLING_NOTE
    # every checked package is found under its pip name (the classifier is absent on Python 3.13+ by design)
    missing = [name for name, version in se.installed_versions().items() if version is None and name != "rapid-orientation"]
    assert not missing, f"version lookup did not find: {missing}"


# =====================================================================================================================
def main() -> int:
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    _software, differences = se.configuration_status()
    print("Tested configuration: yes" if not differences else
          "NOTE - not the tested configuration:\n  - " + "\n  - ".join(differences))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
