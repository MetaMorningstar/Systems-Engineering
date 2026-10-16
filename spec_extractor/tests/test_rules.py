#!/usr/bin/env python3
"""
test_rules.py - fast checks of the layout and requirement rules (no OCR, runs in seconds).

    python tests/test_rules.py                    all of them   (or:  python -m pytest tests/test_rules.py)
    python tests/test_rules.py underline table    only the tests with "underline" or "table" in their name
    python tests/test_rules.py --list             the name and first line of every test

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


def test_a_title_whose_capital_was_read_in_lower_case_keeps_its_number():
    """'3.2.7 output. The ...': the scan read the capital 'O' of the title as 'o' (letters such as c, o, s, v, w
    have the same shape in both cases). The paragraph keeps its number and its title (case TAB-44); a phrase
    after the number ('3.2.4 of MIL-STD-810') is not a title."""
    _, items = run({1: make_lines(["3.2.7 output. The power supply output shall be 28 VDC."])})
    row = find(items, "28 VDC")
    assert (row.doc_ref, row.title, row.text) == ("3.2.7", "Output", "The power supply output shall be 28 VDC."), \
        (row.doc_ref, row.title, row.text)
    for text in ("2.5 output. The unit shall be tested.", "3.2.4 of MIL-STD-810. The unit shall be tested.",
                 "3.2.4 ripple. The unit shall be tested."):
        _, items = run({1: make_lines([text])})
        assert find(items, "tested").doc_ref == "", text


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


def test_a_caption_under_the_last_row_is_given_back_not_read_into_it():
    """'TABLE I. Interface characteristics.' printed close under a table's last row, where the reader stretched
    that row down over it: it is the table's caption, not more text of the row's cell (case TBL-14)."""
    xs, ys = [300, 700, 1300, 1600], [400, 460, 520, 580, 700]           # the last row reaches over the caption
    rows = {r: [(xs[c], ys[r], xs[c + 1], ys[r + 1]) for c in range(3)] for r in range(4)}
    lines = _grid_lines({(0, 0): "Voltage:", (0, 1): "28 VDC nominal", (0, 2): "Test", (1, 0): "Current:",
                         (1, 1): "5 A maximum", (1, 2): "Test", (2, 0): "Impedance:", (2, 1): "50 ohm", (2, 2): "Analysis",
                         (3, 0): "Isolation:", (3, 1): "100 Mohm at 500 VDC", (3, 2): "Test"}, xs, ys)
    lines.append(make_line("TABLE I. Interface characteristics.", xs[1] - 80, ys[3] + 70, height=28))
    restore = _fake_img2table(rows, (xs[0], ys[0], xs[3], ys[4]))
    try:
        table, _tbox, _inside, caption_lines = se.detect_tables(blank_page().ocr_image, lines, DPI,
                                                                settings(detect_tables=True))[0]
    finally:
        restore()
    assert table.grid[-1] == ["Isolation:", "100 Mohm at 500 VDC", "Test"], table.grid
    assert [lines[i].text for i in caption_lines] == ["TABLE I. Interface characteristics."], caption_lines


def test_a_caption_close_under_an_aligned_table_is_not_a_wrapped_line_of_its_last_row():
    """A borderless table found from its aligned text, with 'TABLE I. Interface characteristics.' tight under its
    last row: the caption ends the table - it is not the last row's text wrapping on (case TBL-14)."""
    rows = [("Voltage:", "28 VDC nominal", "Test"), ("Current:", "5 A maximum", "Test"),
            ("Impedance:", "50 ohm", "Analysis"), ("Isolation:", "100 Mohm at 500 VDC", "Test")]
    lines = [make_line(t, LEFT + x, 400 + k * 50) for k, row in enumerate(rows) for x, t in zip((40, 480, 1100), row)]
    lines.append(make_line("TABLE I. Interface characteristics.", LEFT + 400, 400 + 3 * 50 + 50))
    found = se.detect_aligned_tables(lines, DPI, set())
    assert len(found) == 1, found
    table, _tbox, inside, _caps = found[0]
    assert table.grid[-1] == ["Isolation:", "100 Mohm at 500 VDC", "Test"], table.grid
    assert len(lines) - 1 not in inside


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


def test_a_page_with_little_text_has_its_orientation_checked_by_reading_it():
    """The orientation classifier can take a page with a few lines at its top and foot for an upside-down one, and
    the other way round (case PAGE-05). Such a page counts as sparse, so its orientation is checked by reading it
    both ways; when neither reading is better the page stays upright."""
    sparse = np.full((2420, 1870), 255, np.uint8)
    for y in (220, 1960, 2010, 2060):
        sparse[y:y + 30, 220:1500] = 0
    full = np.full((2420, 1870), 255, np.uint8)
    for y in range(220, 2200, 42):
        full[y:y + 30, 220:1650] = 0
    assert se.OrientationDetector._sparse(sparse) and not se.OrientationDetector._sparse(full)

    class ReadsNothing:
        def read(self, image, min_conf=0.3):
            return []
    assert se.OrientationDetector._ocr_vote(sparse, ReadsNothing(), (180, 0)) == 0


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
    stated = re.search(r"^>\s*##\s*Version\s+([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.+-]+)?)\s*$", readme, re.M)
    assert stated, "README.md must carry a '> ## Version X.Y.Z' heading at the top (or X.Y.Z-local.1 after a hand edit)"
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
# Lists on wide tab stops, list lead-ins, and the numbering sequence
# =====================================================================================================================
TAB_STEM = "3.2.4 Environmental conditions. The equipment shall meet each of the following:"
TAB_ITEMS = [("a.", "Acceleration:", ["5 g in each of the three orthogonal axes", "for 1 minute per axis."]),
             ("b.", "Vibration:", ["20 Hz to 2000 Hz random, 0.04 g2/Hz,", "3 hours per axis, 7.7 g rms overall."]),
             ("c.", "Shock:", ["40 g, 11 ms half-sine pulse,", "3 shocks in each direction."]),
             ("d.", "Temperature:", ["-40 C to +71 C operating."])]
TAB_AFTER = "3.2.5 Weight. The equipment shall not exceed 45 kilograms."


def _tabbed_page(items=TAB_ITEMS, stem=TAB_STEM, after=TAB_AFTER, x_mark=LEFT + 80, x_label=LEFT + 220,
                 x_value=LEFT + 560, y0=300, item_gap=0.4) -> list:
    """A lead-in and items laid out on wide tab stops. Marker, label and value are SEPARATE OCR lines,
    which is what the OCR returns when the gaps are wide (checked on rendered pages)."""
    lines, y = [make_line(stem, LEFT, y0)], y0 + PITCH
    for marker, label, values in items:
        y += int(item_gap * PITCH)
        parts = ([(x_mark, marker)] if marker else []) + ([(x_label, label)] if label else []) + [(x_value, values[0])]
        lines += [make_line(text, x, y) for x, text in parts]
        for more in values[1:]:
            y += PITCH
            lines.append(make_line(more, x_value, y))
        y += PITCH
    if after:
        lines.append(make_line(after, LEFT, y + PITCH))
    return lines


def _joined(values) -> str:
    return " ".join(values)


def test_a_list_on_wide_tab_stops_keeps_each_label_with_its_value():
    """The wide tab between 'Acceleration:' and its value is not the gutter between two columns:
    each row carries its marker, label and the whole multi-line value."""
    _doc, items = run({1: _tabbed_page()})
    rows = [(r.doc_ref, r.text) for r in requirements(items)]
    expected = [(f"3.2.4 {m[0]}", f"{TAB_STEM.split('. ', 1)[1]} {m} {label} {_joined(v)}") for m, label, v in TAB_ITEMS]
    assert rows[:4] == expected, rows
    assert rows[4] == ("3.2.5", "The equipment shall not exceed 45 kilograms."), rows


def test_numbered_items_on_tab_stops_are_items_not_headings():
    """'2. Vibration:  20 Hz ...' looks like a numbered heading ('2. SCOPE'), but a heading never
    holds a label and a value."""
    items_ = [(f"{k}.", label, v) for k, (_, label, v) in enumerate(TAB_ITEMS, 1)]
    doc, items = run({1: _tabbed_page(items_)})
    assert [b.kind for b in doc.blocks] == ["paragraph"] + ["list_item"] * 4 + ["paragraph"], \
        [(b.kind, b.text) for b in doc.blocks]
    assert [r.doc_ref for r in requirements(items)] == ["3.2.4 1", "3.2.4 2", "3.2.4 3", "3.2.4 4", "3.2.5"]
    assert not se._is_heading_text("2. Vibration: 20 Hz to 2000 Hz random,")
    assert se._is_heading_text("2. SCOPE")


def test_a_lead_in_without_a_colon_still_leads_into_its_list():
    """'... each of the following.' / 'within the following limits.' introduce a list as surely as a
    colon does; without one the items used to be attached to nothing."""
    for stem in ("3.2.4 Environmental conditions. The equipment shall meet each of the following.",
                 "3.2.4 Electrical conditions. The equipment shall operate within the following limits.",
                 "3.2.4 Timing. The unit shall meet the timing specified below.",
                 "3.2.4 Modes. The radar modes shall be as follows."):
        _doc, items = run({1: _tabbed_page(stem=stem)})
        refs = [r.doc_ref for r in requirements(items)]
        assert refs == ["3.2.4 a", "3.2.4 b", "3.2.4 c", "3.2.4 d", "3.2.5"], (stem, refs)
    for text in ("The equipment shall meet each of the following:", "It shall be as follows.",
                 "within the following limits.", "as specified below.", "the following test conditions apply."):
        assert se._introduces_list(text), text
    for text in ("The equipment shall follow the procedure.", "The unit shall operate below 40 C.",
                 "The following shall apply to all units."):
        assert not se._introduces_list(text), text


def test_a_lead_in_phrase_with_no_list_below_is_an_ordinary_requirement():
    """Without a colon, 'the following' followed by no list is just a sentence: no 'no list items'
    warning (a colon promised a list; the phrase alone did not)."""
    _doc, items = run({1: make_lines(["3.6 Test. The unit shall pass the tests in the following.", None,
                                      "3.7 Mass. The unit shall weigh 5 kg."])})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.6", "3.7"], [(r.doc_ref, r.text) for r in rows]
    assert not any("no list items" in r for r in rows[0].review_reasons), rows[0].review_reasons


def test_value_lines_that_start_with_numbers_stay_in_their_item():
    """A value line may end with a full stop and the next may start with a number - '2.5 G peak',
    '20 Hz', '1.5 V' - which used to be taken for a new section or a heading. A line that starts in
    the item's value column belongs to the item."""
    items_ = [("a.", "Forward:", ["9.0 G for 3 seconds.", "2.5 G sustained thereafter."]),
              ("b.", "Ripple:", ["1.5 V peak-to-peak maximum,", "10 Hz to 50 kHz."]),
              ("c.", "Vertical:", ["6.0 G down and 2.0 G up.", "3.2 G down sustained."])]
    doc, items = run({1: _tabbed_page(items_)})
    assert not any(b.kind == "heading" for b in doc.blocks), [(b.kind, b.text) for b in doc.blocks]
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c", "3.2.5"], [(r.doc_ref, r.text) for r in rows]
    assert rows[0].text.endswith("Forward: 9.0 G for 3 seconds. 2.5 G sustained thereafter."), rows[0].text
    assert not any("Stray period" in reason for r in rows for reason in r.review_reasons), \
        [r.review_reasons for r in rows]               # a full stop at a line end before a number is not a speck


def test_a_misread_list_marker_is_taken_from_the_sequence_and_reported():
    """'c.' read as 'C.' - the letters count a, b, ?, d, so it is c. The change is reported for
    review, because the tool, not the page, supplied the letter."""
    items_ = [TAB_ITEMS[0], TAB_ITEMS[1], ("C.", "Shock:", TAB_ITEMS[2][2]), TAB_ITEMS[3]]
    _doc, items = run({1: _tabbed_page(items_)})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c", "3.2.4 d", "3.2.5"], [(r.doc_ref, r.text) for r in rows]
    assert " c. Shock: " in rows[2].text, rows[2].text
    assert any("taken as 'c.' from the sequence" in reason for reason in rows[2].review_reasons), rows[2].review_reasons
    assert not any("from the sequence" in reason for r in rows[:2] + rows[3:] for reason in r.review_reasons)


def test_a_lost_list_marker_is_taken_from_the_sequence():
    """The photocopy lost 'a.' and 'c.' altogether: each of those rows starts with its label, in the
    label column. The item before and after say which letter it was."""
    items_ = [("", "Acceleration:", TAB_ITEMS[0][2]), TAB_ITEMS[1], ("", "Shock:", TAB_ITEMS[2][2]), TAB_ITEMS[3]]
    _doc, items = run({1: _tabbed_page(items_)})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c", "3.2.4 d", "3.2.5"], [(r.doc_ref, r.text) for r in rows]
    assert rows[2].text.endswith("c. Shock: 40 g, 11 ms half-sine pulse, 3 shocks in each direction."), rows[2].text


def test_a_list_that_really_skips_a_letter_keeps_its_letters():
    """a, b, d: a valid marker is only replaced when the NEXT item confirms the expected one, so a
    list that genuinely skips c is left as printed. A misread one between two agreeing neighbours
    (a, b, e, d) is corrected."""
    f = se.RequirementExtractor._sequence_markers
    tokens = lambda text: [(w, 1.0, "") for w in text.split()]
    kids = lambda markers: [(100, tokens(f"{m} Item {m}"), se.Block("list_item", 1, (0, 0, 1, 1))) for m in markers]
    assert [m for m, *_ in f(kids(["a.", "b.", "d."]), 10)] == ["a.", "b.", "d."]
    assert [m for m, *_ in f(kids(["a.", "b.", "e.", "d."]), 10)] == ["a.", "b.", "c.", "d."]
    assert [m for m, *_ in f(kids(["(1)", "(2)", "(4)"]), 10)] == ["(1)", "(2)", "(4)"]
    assert [m for m, *_ in f(kids(["i.", "ii.", "iii.", "iv."]), 10)] == ["i.", "ii.", "iii.", "iv."]
    assert se._next_marker("b.") == "c." and se._next_marker("(9)") == "(10)" and se._next_marker("iv)", roman=True) == "v)"
    assert se._previous_marker("b.") == "a." and se._previous_marker("1.") == ""


def test_section_numbers_must_follow_in_sequence():
    """Paragraph numbers count up: after 3.2.4 come 3.2.4.1, 3.2.5, 3.3 or 4 (a few may be skipped,
    since the scan can miss a heading). '1.5' or '20' after 3.2.4 is a value, not a section."""
    f = se.plausible_next_number
    for previous, candidate in (("3.2.4", "3.2.5"), ("3.2.4", "3.2.4.1"), ("3.2.4", "3.3"), ("3.2.4", "4"),
                                ("3.2.4", "3.3.1"), ("3.2.4", "3.2.7"), ("", "7.1"), ("6.3", "A.1"),
                                ("A.1", "A.2"), ("3.2.l.3", "3.2.1.4"), ("9.2", "10"), ("3", "3.1.1")):
        assert f(previous, candidate), (previous, candidate)
    for previous, candidate in (("3.2.4", "1.5"), ("3.2.4", "2.5"), ("3.2.4", "20"), ("3.2.5", "3.2.4"),
                                ("3.2.4", "3.2"), ("3.2.4", "3.9.1"), ("3.2.4", "3.3.7")):
        assert not f(previous, candidate), (previous, candidate)


def test_a_value_inside_a_paragraph_is_not_a_new_paragraph():
    """'... per axis. 2.5 G peak ...' inside paragraph 3.2.4: 2.5 does not follow 3.2.4, so it is a
    value and the paragraph is not split there (3.2.5 would have been)."""
    _doc, items = run({1: [make_line("3.2.4 Shock. The unit shall survive 40 G for 11 ms per axis. "
                                     "2.5 G Peak shall not be exceeded in the vertical axis.")]})
    rows = requirements(items)
    assert rows and all(r.doc_ref == "3.2.4" for r in rows), [(r.doc_ref, r.text) for r in rows]
    assert any("2.5 G Peak shall not be exceeded" in r.text for r in rows), [r.text for r in rows]


def test_the_next_paragraph_number_starts_a_new_paragraph_even_without_a_full_stop():
    """A speck turned '3.5 INTERFACE CONDITIONS' into '3.5 INTERFACE. CONDITIONS', which no longer looks
    like a heading; '3.5.1' on the next line is the number that should come next, so it still starts
    its own paragraph and its requirements carry 3.5.1."""
    _doc, items = run({1: make_lines(["3.5 INTERFACE. CONDITIONS",
                                      "3.5.1 Discrete signals. The discrete outputs shall be isolated."])})
    assert [r.doc_ref for r in requirements(items)] == ["3.5.1"], [(r.doc_ref, r.text) for r in requirements(items)]


def test_a_list_on_tab_stops_is_not_a_borderless_table():
    """Items on tab stops line up exactly like a table without ruling lines. A first column that
    counts a., b., c. (or holds only labels, when the bullets were not read) is a list."""
    f = se._first_column_counts_like_a_list
    assert f(["a. Acceleration:", "b. Vibration:", "c. Shock:"]) and f(["i.", "ii.", "iii.", "iv."])
    assert f(["1.", "2.", "3."]) and f(["POWER:", "FAULT:", "STANDBY:"]) and f(["a. Search", "b. Track", "C. Test"])
    assert not f(["CI-01", "CI-02", "CI-03"]) and not f(["MIL-STD-461G", "MIL-STD-704F", "MIL-STD-810H"])
    assert not f(["Parameter", "Voltage", "Current", "Power"]) and not f(["ENV-001", "ENV-002"])
    grid = [["a. Acceleration:", "5 g in each axis"], ["b. Vibration:", "20 Hz to 2000 Hz"], ["c. Shock:", "40 g, 11 ms"]]
    assert not se._plausible_borderless_table(grid, 6, 6)
    grid = [["Parameter", "Value", "Unit"], ["Voltage", "28", "VDC"], ["Current", "3.2", "A"], ["Power", "90", "W"]]
    assert se._plausible_borderless_table(grid, 12, 12)


def test_a_label_that_wraps_is_read_before_its_value():
    """'Storage' / 'temperature:' wraps in the label column beside a two-line value: the row reads
    'Storage temperature: -55 C to +85 C for up to 5 years', not the two columns interleaved."""
    items_ = [("a.", "Storage", ["-55 C to +85 C for", "up to 5 years."]), ("b.", "Altitude:", ["Up to 12,200 m."])]
    lines = _tabbed_page(items_, after=None)
    lines.append(make_line("temperature:", LEFT + 220, lines[3].box[1]))      # the label's 2nd line, beside value line 2
    _doc, items = run({1: lines})
    rows = requirements(items)
    assert rows[0].text.endswith("a. Storage temperature: -55 C to +85 C for up to 5 years."), rows[0].text
    assert rows[1].doc_ref == "3.2.4 b", [(r.doc_ref, r.text) for r in rows]


def test_a_long_value_line_is_not_taken_for_a_page_wide_line():
    """A value line can be long, but it starts far to the right; only a line that starts near the
    left edge (a running header, a title, a full line of a paragraph) divides the page before the
    column check. Here the lead-in's first line and the paragraph after the list are page-wide,
    and the first line of each value is nearly as long: taking those for page-wide lines left each
    label without its value, and the tabs were then cut as column gutters (seen on a photocopy)."""
    x_mark, x_label, x_value = LEFT + 80, LEFT + 200, LEFT + 470
    lines = [make_line("3.2.4 Environmental conditions. The equipment shall meet each of the", LEFT, 300),
             make_line("following:", LEFT, 300 + PITCH)]
    y = 300 + 2 * PITCH + 20
    for marker, label, first, more in (
            ("a.", "Acceleration:", "5 g in each of the three orthogonal axes of the unit,", "for 1 minute."),
            ("b.", "Vibration:", "20 Hz to 2000 Hz random at 0.04 g2/Hz in each axis,", "3 hours per axis."),
            ("c.", "Shock:", "40 g, 11 ms half-sine pulse, three shocks each way,", "in each axis.")):
        lines += [make_line(marker, x_mark, y), make_line(label, x_label, y), make_line(first, x_value, y),
                  make_line(more, x_value, y + PITCH)]
        y += 2 * PITCH + 20
    lines.append(make_line("3.2.5 Weight. The equipment shall not exceed forty-five kilograms.", LEFT, y + PITCH))
    _doc, items = run({1: lines})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c", "3.2.5"], [(r.doc_ref, r.text) for r in rows]
    assert rows[1].text.endswith("b. Vibration: 20 Hz to 2000 Hz random at 0.04 g2/Hz in each axis, 3 hours per axis."), \
        rows[1].text



# ---- what must NOT change: layouts that look like a list on tab stops but are not (from an adversarial review) ----
def test_a_short_list_in_one_column_of_a_two_column_page_is_not_read_across_the_page():
    """Left column: a lead-in and short items 'a. MIL-STD-461G'; right column: numbered prose on the same
    line grid. The gutter is a real column gutter, not a tab: nothing may be read across it."""
    left, right = LEFT, LEFT + 780
    lines = []
    left_rows = ["2.1 Documents. The following", "documents form a part of this", "specification:",
                 "a. MIL-STD-461G", "b. MIL-STD-704F", "c. MIL-STD-810H", "d. MIL-STD-1275E", "e. MIL-STD-1553B"]
    right_rows = ["3.1 Power. The unit shall operate", "from the 28 VDC aircraft bus and", "shall draw no more than 150 W in",
                  "any mode of operation. 3.2", "Cooling. The unit shall be cooled", "by the aircraft ECS and shall not",
                  "require any liquid coolant during", "ground running."]
    for k, (a, b) in enumerate(zip(left_rows, right_rows)):
        lines += [make_line(a, left + (40 if a[:2] in ("a.", "b.", "c.", "d.", "e.") else 0), 300 + k * PITCH),
                  make_line(b, right, 300 + k * PITCH)]
    doc, items = run({1: lines})
    assert not any("MIL-STD" in b.text and "shall" in b.text for b in doc.blocks), [b.text for b in doc.blocks]
    rows = requirements(items)
    assert any(r.doc_ref == "3.1" and r.text.startswith("The unit shall operate from the 28 VDC aircraft bus") for r in rows), \
        [(r.doc_ref, r.text) for r in rows]


def test_a_list_set_in_two_columns_gives_one_row_per_item():
    """a-c on the left, d-f on the right: a list set in columns, read column by column."""
    lines = [make_line("3.2.7 Documents. The unit shall comply with the following:", LEFT, 300)]
    for k, (a, b) in enumerate([("a. MIL-STD-461G", "d. MIL-STD-1275E"), ("b. MIL-STD-704F", "e. MIL-STD-1553B"),
                                ("c. MIL-STD-810H", "f. MIL-STD-883L")]):
        lines += [make_line(a, LEFT + 80, 300 + (k + 1) * PITCH), make_line(b, LEFT + 700, 300 + (k + 1) * PITCH)]
    _doc, items = run({1: lines})
    rows = requirements(items)
    assert sorted(r.doc_ref for r in rows) == [f"3.2.7 {c}" for c in "abcdef"], [(r.doc_ref, r.text) for r in rows]
    assert all(r.text.count("MIL-STD") == 1 for r in rows), [r.text for r in rows]


def test_paragraphs_after_a_list_are_not_pulled_into_its_last_item():
    """A blank line after a finished item ends the item, even when the next paragraph is indented to where
    the item's text starts; a numbered sub-paragraph after the list keeps its own number."""
    lines = make_lines(["3.2.4 Modes. The radar shall provide the following modes:", (40, "(a) Search mode."),
                        (40, "(b) Track mode."), None, (100, "The radar shall switch between modes in less than"),
                        "one second.", None, (100, "3.2.4.1 Mode memory. The radar shall retain the selected mode."), None,
                        "3.2.5 Weight. The radar shall weigh less than 450 kg."])
    _doc, items = run({1: lines})
    rows = [(r.doc_ref, r.text) for r in requirements(items)]
    assert ("3.2.4 b", "The radar shall provide the following modes: (b) Track mode.") in rows, rows
    assert any(t.startswith("The radar shall switch between modes") and "(b)" not in t for _, t in rows), rows
    assert ("3.2.4.1", "The radar shall retain the selected mode.") in rows, rows


def test_a_value_that_wraps_back_under_its_label_keeps_its_order():
    """Only a LABEL that wraps beside its value is read label-first. A value line that wraps back under the
    label column, with nothing beside it, stays after the value's first line."""
    items_ = [("a.", "Operating temperature:", ["-40 C to +71 C with the unit powered"]),
              ("b.", "Altitude:", ["Sea level to 15,000 m."])]
    lines = _tabbed_page(items_, after=None, x_value=LEFT + 600)
    lines.append(make_line("and cooling air at the rate given in Figure 3.", LEFT + 220, lines[3].box[1] + PITCH))
    lines = [ln if ln.box[1] < lines[3].box[1] + PITCH // 2 or ln.text.startswith("and cooling") else
             make_line(ln.text, ln.box[0], ln.box[1] + PITCH) for ln in lines]
    _doc, items = run({1: lines})
    rows = requirements(items)
    assert rows[0].text.endswith("a. Operating temperature: -40 C to +71 C with the unit powered and cooling air at the rate "
                                 "given in Figure 3."), rows[0].text


def test_a_real_table_with_label_like_first_cells_stays_a_table():
    """'Input voltage: | The unit shall ... | Test' is a table - its first cells end with ':' but a caption
    (above or below it), a header row or a real third column (Method: 'Test', 'Inspection') says so, even
    under a lead-in. Without those, labels under a lead-in or beside list markers are a list on tab stops."""
    assert not se._first_column_counts_like_a_list(["Parameter", "Input voltage:", "Power:", "Weight:"], 3)
    assert not se._first_column_counts_like_a_list(["Input voltage:", "Power:", "Weight:"], 3)
    assert se._first_column_counts_like_a_list(["POWER:", "FAULT:", "STANDBY:"], 2)
    assert not se._first_column_counts_like_a_list(["POWER:", "FAULT:", "STANDBY:"], 2, captioned=True)
    grid = [["Input voltage:", "The unit shall operate from 28 VDC."], ["Power:", "The unit shall draw 150 W."],
            ["Weight:", "The unit shall weigh 5 kg."]]
    with_method = [row + [m] for row, m in zip(grid, ("Test", "Test", "Inspection"))]
    tbox = (LEFT, 400, LEFT + 1200, 540)
    caption = [make_line("TABLE I. Characteristics.", LEFT + 300, 340)]
    caption_below = [make_line("TABLE I. Characteristics.", LEFT + 300, 570)]
    lead_in = [make_line("3.2 Limits. The unit shall meet each of the following:", LEFT, 340)]
    assert not se._tab_list_in_context(grid, tbox, caption, DPI)
    assert not se._tab_list_in_context(grid, tbox, lead_in + caption_below, DPI)
    assert se._tab_list_in_context(grid, tbox, lead_in, DPI)
    assert not se._tab_list_in_context(with_method, tbox, lead_in, DPI)
    markers = [make_line(f"{k}.", LEFT - 100, 400 + 48 * (k - 1)) for k in (1, 2, 3)]
    assert se._tab_list_in_context(grid, tbox, markers, DPI)


def test_notes_are_not_list_items():
    """'NOTE:  text' after a list, 'Note.' level with the items and a 'Note:' line inside an item are not
    items of the list: none of them gets a letter, and no letter is used twice."""
    assert not se._is_item_label("NOTE: The operator shall confirm.") and not se._is_item_label("WARNING: High voltage.")
    assert not se._is_item_label("SRS-101: The software shall log.") and se._is_item_label("Input voltage: 28 VDC")
    assert se.RE_MARKER_SHAPE.match("C. Shock:") and not se.RE_MARKER_SHAPE.match("Note. The unit shall be off.")
    lines = _tabbed_page([TAB_ITEMS[0], TAB_ITEMS[1]], after=None)
    y = max(ln.box[1] for ln in lines) + 2 * PITCH
    lines += [make_line("NOTE:", LEFT, y), make_line("The operator shall confirm each change.", LEFT + 560, y)]
    _doc, items = run({1: lines})
    rows = requirements(items)
    assert [r.doc_ref for r in rows][:2] == ["3.2.4 a", "3.2.4 b"], [(r.doc_ref, r.text) for r in rows]
    assert not any(r.doc_ref.startswith("3.2.4 c") for r in rows), [(r.doc_ref, r.text) for r in rows]
    note = [r for r in rows if "operator shall confirm" in r.text]
    assert note and TAB_STEM.split(". ", 1)[1] not in note[0].text, [(r.doc_ref, r.text) for r in rows]


def test_a_note_inside_an_item_stays_in_that_item():
    items_ = [("a.", "Acceleration:", ["5 g in each of the three axes."]), ("b.", "Vibration:", ["20 Hz to 2000 Hz random."]),
              ("c.", "Shock:", ["40 g, 11 ms half-sine."])]
    lines = _tabbed_page(items_, after=None)
    y_b = next(ln.box[1] for ln in lines if ln.text == "b.")
    moved = [make_line(ln.text, ln.box[0], ln.box[1] + PITCH) if ln.box[1] >= y_b else ln for ln in lines]
    moved.append(make_line("Note: The unit shall be powered during this test.", LEFT + 220, y_b))
    _doc, items = run({1: moved})
    rows = requirements(items)
    refs = [r.doc_ref for r in rows]
    assert refs == ["3.2.4 a", "3.2.4 b", "3.2.4 c"], [(r.doc_ref, r.text) for r in rows]
    assert "Note: The unit shall be powered during this test." in rows[0].text, rows[0].text


def test_the_following_day_is_not_a_lead_in_and_a_mid_paragraph_phrase_splits_nothing():
    """'... retested on the following day.' and '... as described below.' inside ordinary paragraphs:
    every sentence stays a whole requirement of its own."""
    _doc, items = run({1: make_lines([
        "3.4.1 Retest. A unit that fails shall be repaired and retested on the",
        "following day. The results of the retest shall be recorded in the test",
        "log and the log shall be signed by the quality inspector before the",
        "unit is returned to stock.", None,
        "3.6.2 Failures. Each failure shall be recorded and analysed as described below.",
        "The analysis shall identify the cause of the failure and the corrective action",
        "taken. The unit shall then be retested for a period of not less than 50 hours."])})
    texts_ = [r.text for r in requirements(items)]
    assert "The results of the retest shall be recorded in the test log and the log shall be signed by the quality " \
           "inspector before the unit is returned to stock." in texts_, texts_
    assert "The analysis shall identify the cause of the failure and the corrective action taken." in texts_, texts_
    assert not any(r.found_in.startswith("List") for r in requirements(items)), [r.found_in for r in requirements(items)]


def test_a_wrapped_cross_reference_does_not_split_a_paragraph():
    """'... established in paragraph' / '3.2.5. The weight shall ...' - the line above ran to the margin, so
    the number is a cross-reference in the sentence, not the start of paragraph 3.2.5."""
    _doc, items = run({1: make_lines([
        "3.2.4 Weight. The weight of the complete unit, including the mounting tray and all",
        "cables, shall not exceed the limit established for the installation in paragraph",
        "3.2.5. The weight shall be verified by measurement with all fluids drained."])})
    assert {r.doc_ref for r in requirements(items)} == {"3.2.4"}, [(r.doc_ref, r.text) for r in requirements(items)]


def test_a_titled_paragraph_ends_a_list_whatever_its_number():
    """'3.2.8 Weight. The ...' after a list: a skip, or 3.2.5 misread as 3.2.8 - a paragraph with a run-in
    title is a paragraph, not more of the list."""
    lines = _tabbed_page(TAB_ITEMS[:2], after="3.2.8 Weight. The equipment shall not exceed 45 kilograms.")
    _doc, items = run({1: lines})
    assert [r.doc_ref for r in requirements(items)] == ["3.2.4 a", "3.2.4 b", "3.2.8"], \
        [(r.doc_ref, r.text) for r in requirements(items)]


def test_a_titled_inner_paragraph_is_split_whatever_its_number():
    _doc, items = run({1: [make_line("3.2.4 Weight. The unit shall weigh less than 45 kg. "
                                     "3.2.8 Input power. The unit shall operate from 28 VDC.")]})
    assert [r.doc_ref for r in requirements(items)] == ["3.2.4", "3.2.8"], [(r.doc_ref, r.text) for r in requirements(items)]


def test_a_value_carried_onto_the_next_page_stays_with_its_item():
    """Item d's value goes on at the top of page 2 with '2.5 C per minute ...' - not a heading, not a new
    section; and the items after it are still found."""
    page1 = _tabbed_page([TAB_ITEMS[0], TAB_ITEMS[1], ("c.", "Temperature:", ["-40 C to +71 C operating,"])], after=None)
    page2 = [make_line("2.5 C per minute maximum rate of change.", LEFT + 560, 300),
             make_line("d.", LEFT + 80, 300 + 2 * PITCH), make_line("Humidity:", LEFT + 220, 300 + 2 * PITCH),
             make_line("95 percent for 10 days.", LEFT + 560, 300 + 2 * PITCH),
             make_line("3.2.5 Weight. The unit shall weigh 5 kg.", LEFT, 300 + 4 * PITCH)]
    _doc, items = run({1: page1, 2: page2})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c", "3.2.4 d", "3.2.5"], [(r.doc_ref, r.text) for r in rows]
    assert rows[2].text.endswith("c. Temperature: -40 C to +71 C operating, 2.5 C per minute maximum rate of change."), rows[2].text


def test_an_item_that_opens_a_sub_list_keeps_its_sub_items():
    """'a. Search mode, which shall include:' / 'a. Vibration:  as follows:' - the lines below are the
    item's sub-items (one row each, under the item), not more of its text and not new letters."""
    _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the following modes:",
                                      (40, "a. Search mode, which shall include:"), (100, "Long range scan"),
                                      (100, "Short range scan"), (40, "b. Track mode.")])})
    rows = [(r.doc_ref, r.text) for r in requirements(items)]
    assert sum(1 for ref, _ in rows if ref.startswith("3.2.4 a")) == 2, rows
    assert any(t.endswith("include: Long range scan") for _, t in rows) and any(t.endswith("include: Short range scan") for _, t in rows), rows
    x_mark, x_label, x_value = LEFT + 80, LEFT + 220, LEFT + 560
    lines = [make_line(TAB_STEM, LEFT, 300), make_line("a.", x_mark, 348), make_line("Vibration:", x_label, 348),
             make_line("as follows:", x_value, 348),
             make_line("Random:", x_label, 396), make_line("20 Hz to 2000 Hz, 0.04 g2/Hz.", x_value, 396),
             make_line("Sine:", x_label, 444), make_line("5 g peak, 5 Hz to 500 Hz.", x_value, 444),
             make_line("b.", x_mark, 510), make_line("Shock:", x_label, 510), make_line("40 g, 11 ms half-sine.", x_value, 510)]
    _doc, items = run({1: lines})
    refs = [r.doc_ref for r in requirements(items)]
    assert refs.count("3.2.4 b") == 1 and "3.2.4 c" not in refs, [(r.doc_ref, r.text) for r in requirements(items)]


def test_requirement_ids_under_a_lead_in_keep_their_ids():
    """'SRS-101:   The software shall ...' on tab stops under a lead-in: SRS-101 is the requirement's ID,
    not a list label."""
    lines = [make_line("3.1 Logging. The software shall meet the following:", LEFT, 300)]
    for k, (rid, text) in enumerate([("SRS-101:", "The software shall log each command."),
                                     ("SRS-102:", "The software shall log each fault.")]):
        lines += [make_line(rid, LEFT + 80, 348 + k * PITCH), make_line(text, LEFT + 300, 348 + k * PITCH)]
    _doc, items = run({1: lines})
    refs = [r.doc_ref for r in requirements(items)]
    assert "SRS-101" in " ".join(refs) and "SRS-102" in " ".join(refs), [(r.doc_ref, r.text) for r in requirements(items)]


def test_several_lost_markers_in_a_row_are_counted_forward():
    f = se.RequirementExtractor._sequence_markers
    tokens = lambda text: [(w, 1.0, "") for w in text.split()]
    kids = [(100, tokens(t), se.Block("list_item", 1, (0, 0, 1, 1))) for t in
            ("a. Search:", "Track: follows targets.", "Map: ground map.", "d. Test:")]
    assert [m for m, *_ in f(kids, 10)] == ["a.", "b.", "c.", "d."]



def test_a_note_between_items_keeps_its_own_row_and_the_letters_go_on_after_it():
    """a, b, NOTE, C. (misread), d: the NOTE is neither numbered nor glued to b, and 'C.' is still read as c
    - the letter is expected from the last item that has one."""
    f = se.RequirementExtractor._sequence_markers
    tokens = lambda text: [(w, 1.0, "") for w in text.split()]
    kids = [(100, tokens(t), se.Block("list_item", 1, (0, 0, 1, 1))) for t in
            ("a. Voltage: 28 VDC.", "b. Ripple: 1.5 V.", "NOTE: The limits apply at the connector.", "C. Power: 150 W.",
             "d. Current: 5 A.")]
    out = f(kids, 10)
    assert [m for m, *_ in out] == ["a.", "b.", "", "c.", "d."], out
    assert not any(merge for *_, merge in out), out
    assert "from the sequence" in out[3][2], out[3]


def test_a_misread_next_letter_starts_the_next_item_without_a_full_stop():
    """Items without final punctuation ('b. MIL-STD-704F') never end a sentence, so a misread 'C.' level
    with them used to be folded into the item above. The next letter of the list starts the next item."""
    _doc, items = run({1: make_lines(["3.2.7 Documents. The unit shall comply with the following:",
                                      (80, "a. MIL-STD-461G"), (80, "b. MIL-STD-704F"), (80, "C. MIL-STD-810H"),
                                      (80, "d. MIL-STD-1275E")])})
    rows = [(r.doc_ref, r.text) for r in requirements(items)]
    assert [ref for ref, _ in rows] == ["3.2.7 a", "3.2.7 b", "3.2.7 c", "3.2.7 d"], rows
    assert rows[1][1].endswith("b. MIL-STD-704F") and rows[2][1].endswith("c. MIL-STD-810H"), rows


def test_a_blank_line_after_a_finished_item_ends_it():
    """'c. Ground mapping mode.', a blank line, then an indented sentence: a paragraph of its own, not more
    of item c - even on a page whose paragraph spacing is wide."""
    _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the following modes:", (40, "a. Search mode."),
                                      (40, "b. Track mode."), (40, "c. Ground mapping mode."), None,
                                      (60, "The radar shall switch modes in less than one second.")])})
    rows = [(r.doc_ref, r.text) for r in requirements(items)]
    assert rows[2] == ("3.2.4 c", "The radar shall provide the following modes: c. Ground mapping mode."), rows
    assert any(t.endswith("The radar shall switch modes in less than one second.") and " c. " not in t for _, t in rows), rows


# ---- a second adversarial review: rules of the first round that were too strict, and more list shapes ----
def _tab_list(items, stem=TAB_STEM, after=TAB_AFTER, x_mark=LEFT + 80, x_label=LEFT + 220, x_value=LEFT + 560) -> list:
    """Like _tabbed_page, but a label may wrap over several rows (a list of lines) and a value may be empty."""
    lines, y = ([make_line(stem, LEFT, 300)] if stem else []), 300 + PITCH
    for marker, label, values in items:
        y += int(0.4 * PITCH)
        labels = label if isinstance(label, list) else ([label] if label else [])
        for k in range(max(len(labels), len(values), 1)):
            if k == 0 and marker:
                lines.append(make_line(marker, x_mark, y))
            if k < len(labels):
                lines.append(make_line(labels[k], x_label, y))
            if k < len(values):
                lines.append(make_line(values[k], x_value, y))
            y += PITCH
    if after:
        lines.append(make_line(after, LEFT, y + PITCH))
    return lines


def _refs_and_texts(items) -> list:
    return [(r.doc_ref, r.text.split(": ", 1)[1] if ": " in r.text else r.text) for r in requirements(items)]


def test_a_note_heading_or_long_label_near_a_tab_list_does_not_cut_it_into_columns():
    """Only the rows of the list itself are judged: a NOTE or a heading under the list, or the lead-in's last
    line above it, sits in the same band but is not part of it. A marker and a label may run to 8 words."""
    lines = _tabbed_page(after=None)
    y = max(ln.box[1] for ln in lines) + 2 * PITCH
    for extra in ("NOTE: Values apply at 25 C.", "3.2.5 Size, weight and finish."):
        _doc, items = run({1: lines + [make_line(extra, LEFT, y)]})
        rows = [r.text for r in requirements(items)]
        assert rows[0].endswith("a. Acceleration: 5 g in each of the three orthogonal axes for 1 minute per axis."), (extra, rows)
        assert rows[3].endswith("d. Temperature: -40 C to +71 C operating."), (extra, rows)
    long_label = [("a.", "Input voltage:", ["22 to 29 VDC."]), ("b.", "Peak inrush current (cold):", ["20 A for 10 ms."]),
                  ("c.", "Power:", ["150 W maximum."])]
    _doc, items = run({1: _tab_list(long_label, x_value=LEFT + 700)})
    assert [t for _, t in _refs_and_texts(items)][:3] == ["a. Input voltage: 22 to 29 VDC.",
                                                         "b. Peak inrush current (cold): 20 A for 10 ms.",
                                                         "c. Power: 150 W maximum."], _refs_and_texts(items)


def test_values_in_lower_case_without_a_full_stop_stay_with_their_labels():
    """'within 22 to 29 VDC' / 'less than 1 V peak to peak,' - values that start in lower case and do not end a
    sentence are not prose running from line to line: each line breaks where there was still room."""
    for values in (["within 22 to 29 VDC", "less than 1 V peak to peak", "not more than 150 W", "per MIL-STD-704F"],
                   ["within 22 to 29 VDC,", "less than 1 V peak to peak,", "not more than 150 W, and", "per MIL-STD-704F."]):
        items_ = [(f"{m}.", label, [v]) for m, label, v in zip("abcd", ("Voltage:", "Ripple:", "Power:", "Transients:"), values)]
        _doc, items = run({1: _tab_list(items_, stem="3.2.6 Input power. The unit shall meet the following:")})
        rows = _refs_and_texts(items)
        assert [ref for ref, _ in rows][:4] == ["3.2.6 a", "3.2.6 b", "3.2.6 c", "3.2.6 d"], rows
        assert rows[1][1] == f"b. Ripple: {values[1]}", rows


def test_a_quantity_at_the_start_of_a_value_is_not_a_titled_paragraph():
    """'5.0 V. Ripple shall ...', '1.5 V peak to peak. Measured ...', '2.5 G rms overall. Duration ...' start with a
    quantity and its unit; '3.1 Power. The unit ...' is a numbered paragraph with a run-in title."""
    for text in ("5.0 V. Ripple shall not exceed 50 mV.", "1.5 V peak to peak. Measured at the", "2.5 G rms overall. Duration",
                 "12.5 V. The auxiliary output shall be"):
        assert not se._is_titled_number(text), text
    for text in ("3.1 Power. The unit shall operate.", "4.5.3 Random vibration. Levels shall be measured."):
        assert se._is_titled_number(text), text
    items_ = [("a.", "Output voltage:", ["5.0 V. Ripple shall not exceed 50 mV."]),
              ("b.", "Output current:", ["2.5 A. The output shall be protected", "against short circuits."]),
              ("c.", "Efficiency:", ["85 percent minimum."])]
    _doc, items = run({1: _tab_list(items_, stem="3.2.9 Power supply. The power supply shall provide the following:")})
    rows = _refs_and_texts(items)
    assert rows[:3] == [("3.2.9 a", "a. Output voltage: 5.0 V. Ripple shall not exceed 50 mV."),
                        ("3.2.9 b", "b. Output current: 2.5 A. The output shall be protected against short circuits."),
                        ("3.2.9 c", "c. Efficiency: 85 percent minimum.")], rows


def test_a_sub_list_in_the_value_column_stays_under_its_own_item():
    """'a. Search mode:   (1) Range ...' / '(2) Azimuth ...' on the value tab stop: a sub-list that starts again
    under each item, not a second column of the list. Both sub-items are filed under their own parent."""
    items_ = [("a.", "Search mode:", ["(1) Range of 100 km.", "(2) Azimuth of 360 degrees."]),
              ("b.", "Track mode:", ["(1) Update rate of 1 Hz.", "(2) Up to 64 targets."]),
              ("c.", "Standby:", ["Transmitter off."])]
    _doc, items = run({1: _tab_list(items_, stem="3.2.8 Modes. The radar shall provide the following modes:")})
    rows = _refs_and_texts(items)
    assert rows[:5] == [("3.2.8 a.1", "a. Search mode: (1) Range of 100 km."), ("3.2.8 a.2", "a. Search mode: (2) Azimuth of 360 degrees."),
                        ("3.2.8 b.1", "b. Track mode: (1) Update rate of 1 Hz."), ("3.2.8 b.2", "b. Track mode: (2) Up to 64 targets."),
                        ("3.2.8 c", "c. Standby: Transmitter off.")], rows


def test_a_sub_list_printed_without_its_own_indent_is_nested_by_its_markers():
    """'b. Vibration:' then '(1) Random: ...', '(2) Sine: ...' at the same indent, then 'c. Shock:': the marker
    style changes after a line ending ':' and comes back, so (1) and (2) belong to b. The parent's next letter
    read as a capital ('C.' for 'c.', a common misread) still ends the sub-list (case TAB-30); a sub-list that
    is itself lettered in capitals keeps its own 'C.'."""
    sub = [("b.", "Vibration:", []), ("(1)", "Random:", ["20 Hz to 2000 Hz, 0.04 g2/Hz."]),
           ("(2)", "Sine:", ["5 Hz to 500 Hz, 2 g peak."])]
    _doc, items = run({1: _tab_list([TAB_ITEMS[0]] + sub + [TAB_ITEMS[2]])})
    rows = _refs_and_texts(items)
    assert [ref for ref, _ in rows][:4] == ["3.2.4 a", "3.2.4 b.1", "3.2.4 b.2", "3.2.4 c"], rows
    assert rows[1][1] == "b. Vibration: (1) Random: 20 Hz to 2000 Hz, 0.04 g2/Hz.", rows
    _doc, items = run({1: _tab_list([TAB_ITEMS[0]] + sub + [("C.",) + TAB_ITEMS[2][1:], TAB_ITEMS[3]])})
    rows = _refs_and_texts(items)
    assert [ref for ref, _ in rows][:5] == ["3.2.4 a", "3.2.4 b.1", "3.2.4 b.2", "3.2.4 c", "3.2.4 d"], rows
    assert rows[3][1].startswith("c. Shock: 40 g"), rows
    capitals = [("A.", "Random:", ["20 Hz to 2000 Hz."]), ("B.", "Sine:", ["5 Hz to 500 Hz."]),
                ("C.", "Shock:", ["40 g, 11 ms."])]
    _doc, items = run({1: _tab_list([TAB_ITEMS[0], ("b.", "Vibration:", [])] + capitals + [("c.",) + TAB_ITEMS[3][1:]])})
    rows = _refs_and_texts(items)
    assert [ref for ref, _ in rows][:5] == ["3.2.4 a", "3.2.4 b.A", "3.2.4 b.B", "3.2.4 b.C", "3.2.4 c"], rows


def test_a_label_that_wraps_is_read_before_its_value_even_when_the_value_is_shorter():
    """The label's last line may have no value beside it ('temperature:' under a one-line value), have 4 or
    more words, or follow a first line that ends in an abbreviation ('Max. oper.')."""
    for label, values, expected in (
            (["Operating", "temperature:"], ["-40 C to +71 C."], "a. Operating temperature: -40 C to +71 C."),
            (["Peak power", "consumption in any mode:"], ["150 W for not more than", "10 seconds."],
             "a. Peak power consumption in any mode: 150 W for not more than 10 seconds."),
            (["Max. oper.", "temperature:"], ["+71 C with the unit powered", "and cooled."],
             "a. Max. oper. temperature: +71 C with the unit powered and cooled.")):
        _doc, items = run({1: _tab_list([("a.", label, values), ("b.", "Humidity:", ["95 percent."])], x_value=LEFT + 640)})
        rows = _refs_and_texts(items)
        assert rows[0] == ("3.2.4 a", expected), rows
        assert rows[1] == ("3.2.4 b", "b. Humidity: 95 percent."), rows


def test_columns_under_a_lead_in_are_a_list_unless_a_title_or_heading_row_makes_them_a_table():
    """'Voltage: | 28 VDC nominal | Test' under '... the following characteristics:' is a list since 1.5.0 - one row
    per line with the lead-in in front, even with a short repeated Method column - because it has neither a title
    nor a heading row. The same columns with 'TABLE I. ...' printed under them, or under a heading row that names
    the columns, are a table."""
    lead = "3.2.1 Interface. The interface shall have the following characteristics:"
    rows_ = [("Voltage:", "28 VDC nominal", "Test"), ("Current:", "5 A maximum", "Test"),
             ("Impedance:", "50 ohm", "Analysis"), ("Isolation:", "100 Mohm at 500 VDC", "Test")]

    def page(extra_top=(), extra_bottom=()):
        top = [make_line(lead, LEFT, 300)] + [make_line(t, LEFT + x, 372) for x, t in zip((0, 420, 1000), extra_top)]
        y0 = 436 if extra_top else 372
        body = [make_line(t, LEFT + x, y0 + k * 64) for k, row in enumerate(rows_) for x, t in zip((0, 420, 1000), row)]
        bottom = [make_line(t, LEFT + 300, y0 + len(rows_) * 64) for t in extra_bottom]     # (straight under it)
        return top + body + bottom

    s = settings(detect_tables=True, borderless_tables=True)
    _doc, items = run({1: page()}, s)
    assert not [it for it in items if it.item_type == "Table"], [(it.item_type, it.text) for it in items]
    assert texts(items) == [f"The interface shall have the following characteristics: {a} {b} {c}" for a, b, c in rows_], \
        texts(items)
    for extra in ({"extra_bottom": ["TABLE I. Interface characteristics."]},
                  {"extra_top": ("Characteristic", "Requirement", "Method")}):
        _doc, items = run({1: page(**extra)}, s)
        tables = [it for it in items if it.item_type == "Table"]
        assert tables and "Impedance: | 50 ohm | Analysis" in tables[0].text, (extra, [(it.item_type, it.text) for it in items])
    assert se._has_real_extra_column([list(r) for r in rows_])
    # a label-only list whose value the OCR split at word gaps has ragged 'columns', not a real one
    assert not se._has_real_extra_column([["Power:", "150 W", "maximum."], ["Transients:", "as in", "MIL-STD-704F."],
                                          ["Hold-up:", "50 ms", "after loss of"]])


def test_a_label_list_with_one_colon_lost_stays_a_list_with_tables_on():
    """Labels on tab stops without markers, one of them without its colon ('Power  150 W maximum.'): with
    table detection on, still one list row per label under the lead-in."""
    items_ = [("", "Input voltage:", ["22 to 29 VDC."]), ("", "Ripple:", ["1 V peak to peak maximum."]),
              ("", "Power", ["150 W maximum."]), ("", "Transients:", ["as in MIL-STD-704F."]),
              ("", "Hold-up:", ["50 ms after loss of input."])]
    _doc, items = run({1: _tab_list(items_, stem="3.2.6 Input power. The unit shall meet the following:")},
                      settings(detect_tables=True, borderless_tables=True))
    texts_ = [t for _, t in _refs_and_texts(items)]
    assert not [it for it in items if it.item_type == "Table"], [(it.item_type, it.text) for it in items]
    assert texts_[:5] == ["Input voltage: 22 to 29 VDC.", "Ripple: 1 V peak to peak maximum.", "Power 150 W maximum.",
                          "Transients: as in MIL-STD-704F.", "Hold-up: 50 ms after loss of input."], texts_


def test_a_numbered_list_is_not_taken_for_section_headings_by_the_paragraph_after_it():
    """'1. Search mode.' ... '3. Ground mapping mode.' followed by '3.2.5 Weight. ...' (or a section-2 document list
    followed by '2.2 ...') are list items. Only a title-like last line followed by its own N.1 is a heading:
    '4. Verification' then '4.1 General. ...'."""
    _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the following modes:", (75, "1. Search mode."),
                                      (75, "2. Track mode."), (75, "3. Ground mapping mode."), None,
                                      "3.2.5 Weight. The radar shall weigh less than 45 kg."])})
    rows = [(r.doc_ref, r.section) for r in requirements(items)]
    assert [ref for ref, _ in rows] == ["3.2.4 1", "3.2.4 2", "3.2.4 3", "3.2.5"], rows
    assert not any("Ground mapping" in sec for _, sec in rows), rows
    doc, items = run({1: make_lines(["3.9 Modes. The radar shall provide the following modes:", "1. Search mode.",
                                     "2. Track mode.", "3. Ground mapping mode.", "4. Verification",
                                     "4.1 General. The contractor shall verify each requirement of section 3."])})
    assert [b.kind for b in doc.blocks if b.text.startswith(("3. ", "4. "))] == ["list_item", "heading"], \
        [(b.kind, b.text) for b in doc.blocks]
    assert [r.doc_ref for r in requirements(items)] == ["3.9 1", "3.9 2", "3.9 3", "4.1"]
    # all capitals at the margin, straight under a lead-in that ends with ':' (case NUM-10)
    _doc, items = run({1: make_lines(["2.1 Government documents. The following documents shall apply:",
                                      "1. MIL-STD-461G", "2. MIL-STD-704F", None,
                                      "2.2 Order of precedence. The text of this specification shall take precedence."])})
    assert _refs_and_texts(items) == [("2.1 1", "1. MIL-STD-461G"), ("2.1 2", "2. MIL-STD-704F"),
                                      ("2.2", "The text of this specification shall take precedence.")], _refs_and_texts(items)


def test_a_cross_reference_with_a_title_carries_a_value_onto_the_next_page():
    """'b. Vibration: 20 Hz to 2000 Hz random, as specified in' at the foot of page 1, then '4.5.3 Random
    vibration. Levels ...' at the top of page 2 in the value column: the number does not follow the section
    numbering and the value had not ended, so it is more of item b - and item c keeps its own row."""
    p1 = [make_line(TAB_STEM, LEFT, 2400), make_line("a.", LEFT + 80, 2460), make_line("Acceleration:", LEFT + 220, 2460),
          make_line("5 g in each of the three axes.", LEFT + 560, 2460), make_line("b.", LEFT + 80, 2530),
          make_line("Vibration:", LEFT + 220, 2530), make_line("20 Hz to 2000 Hz random, as specified in", LEFT + 560, 2530)]
    p2 = [make_line("4.5.3 Random vibration. Levels shall be measured at the mounting points.", LEFT + 560, 250),
          make_line("c.", LEFT + 80, 320), make_line("Shock:", LEFT + 220, 320), make_line("40 g, 11 ms half-sine.", LEFT + 560, 320),
          make_line(TAB_AFTER, LEFT, 420)]
    _doc, items = run({1: p1, 2: p2})
    rows = _refs_and_texts(items)
    assert [ref for ref, _ in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c", "3.2.5"], rows
    assert rows[1][1].endswith("as specified in 4.5.3 Random vibration. Levels shall be measured at the mounting points."), rows


def test_a_blank_line_under_a_long_item_still_ends_it():
    """'Right under an item' is measured with the item's own line spacing, so a blank line under an item of
    three lines ends it too: the paragraph after it, or the next item whose marker was lost, is not glued on."""
    long_c = [(75, "c. Ground mapping mode, with the antenna tilted down by"), (120, "the angle set by the operator and the"),
              (120, "range scale set to 10, 20 or 40 km.")]
    _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the following modes:", (75, "a. Search mode."),
                                      (75, "b. Track mode.")] + long_c + [None, (120, "The radar shall switch between any two modes."),
                                      None, "3.2.5 Weight. The radar shall weigh less than 45 kg."])})
    rows = _refs_and_texts(items)
    assert rows[2] == ("3.2.4 c", "c. Ground mapping mode, with the antenna tilted down by the angle set by the operator "
                                  "and the range scale set to 10, 20 or 40 km."), rows
    assert rows[3] == ("3.2.4", "The radar shall switch between any two modes."), rows
    long_a = [(75, "a. Search mode, covering the full surveillance volume at"), (120, "the maximum instrumented range and at"),
              (120, "every elevation angle up to 60 degrees.")]
    _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the following modes:"] + long_a +
                                     [None, (120, "Track mode, holding up to 20 targets."), None, (75, "c. Ground mapping mode.")])})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c"], [(r.doc_ref, r.text) for r in rows]
    assert rows[1].text.endswith("b. Track mode, holding up to 20 targets.") and "missing" in rows[1].review_reasons[0], \
        (rows[1].text, rows[1].review_reasons)


def test_an_unmarked_block_between_items_is_joined_only_when_it_is_a_piece_of_text():
    """An unmarked block whose would-be letter a later item carries is not that item. A requirement sentence
    of its own, or a second lead-in, keeps its own row; a plain piece of text is joined to the item at its
    own level above it (not to a sub-item), and a second list's 'a.' does not count as 'later'."""
    stem = "3.2.4 Modes. The radar shall provide the following modes:"
    _doc, items = run({1: make_lines([stem, (75, "a. Search mode, which shall include:"), (135, "(1) Long range scan."),
                                      (135, "(2) Short range scan."), None, (75, "The operator shall be able to select either scan."),
                                      None, (75, "b. Track mode."), (75, "c. Ground mapping mode.")])})
    rows = _refs_and_texts(items)
    assert rows[:5] == [("3.2.4 a.1", "a. Search mode, which shall include: (1) Long range scan."),
                        ("3.2.4 a.2", "a. Search mode, which shall include: (2) Short range scan."),
                        ("3.2.4", "The operator shall be able to select either scan."),
                        ("3.2.4 b", "b. Track mode."), ("3.2.4 c", "c. Ground mapping mode.")], rows
    _doc, items = run({1: make_lines(["3.2.6 Interfaces. The unit shall provide the following interfaces:",
                                      (75, "a. One MIL-STD-1553B bus."), (75, "b. Two RS-422 serial ports."), None,
                                      (75, "The unit shall also provide the following discrete signals:"),
                                      (75, "a. Weight on wheels."), (75, "b. Master arm."), (75, "c. Emergency jettison.")])})
    rows = _refs_and_texts(items)
    assert rows[1] == ("3.2.6 b", "b. Two RS-422 serial ports."), rows
    assert rows[2] == ("3.2.6", "The unit shall also provide the following discrete signals:"), rows
    f = se.RequirementExtractor._sequence_markers
    tokens = lambda text: [(w, 1.0, "") for w in text.split()]
    kids = [(100, tokens(t), se.Block("list_item", 1, (0, 0, 1, 1))) for t in
            ("a. Acceleration: 5 g.", "Applied for 1 minute per axis.", "b. Vibration: 20 Hz.")]
    assert [out[3] for out in f(kids, 10)] == [None, 0, None]           # the piece of text belongs to 'a.'


def test_labels_under_a_bare_label_item_are_its_sub_items():
    """'a. Operating:' with nothing after it, then 'Temperature: ...' and 'Humidity: ...' in its label column:
    they belong to a (no invented letters)."""
    rows_ = ["3.2.4 Environment. The unit shall meet the following conditions:",
             [(75, "a."), (135, "Operating:")], [(135, "Temperature:"), (375, "-40 C to +71 C.")],
             [(135, "Humidity:"), (375, "95 percent, non-condensing.")], [(75, "b."), (135, "Storage:")],
             [(135, "Temperature:"), (375, "-55 C to +85 C.")]]
    lines, y = [], 300
    for row in rows_:
        for x, t in ([(0, row)] if isinstance(row, str) else row):
            lines.append(make_line(t, LEFT + x, y))
        y += PITCH
    _doc, items = run({1: lines})
    rows = _refs_and_texts(items)
    assert rows == [("3.2.4 a", "a. Operating: Temperature: -40 C to +71 C."),
                    ("3.2.4 a", "a. Operating: Humidity: 95 percent, non-condensing."),
                    ("3.2.4 b", "b. Storage: Temperature: -55 C to +85 C.")], rows


def test_a_lead_in_without_a_colon_takes_a_run_of_short_plain_items():
    """'... shall show the following information.' followed by short indented lines without markers - a list
    whose lead-in lost its colon. One sentence after the lead-in is not a list, but a short indented line that
    is left out is flagged."""
    stem = "3.2.6 Displays. The display shall show the following information."
    plain = [(75, "Own ship position and heading."), None, (75, "Target range and bearing."), None,
             (75, "Time to go to the next waypoint.")]
    _doc, items = run({1: make_lines([stem, None] + plain + [None, "3.2.7 Mass. The display shall weigh 5 kg."])})
    rows = _refs_and_texts(items)
    assert [ref for ref, _ in rows] == ["3.2.6", "3.2.6", "3.2.6", "3.2.7"], rows
    assert rows[1][1] == "The display shall show the following information. Target range and bearing.", rows
    _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the operating modes listed below.",
                                      (75, "Search mode"), (75, "Track while scan mode"), (75, "Ground mapping mode")])})
    assert [t for _, t in _refs_and_texts(items)][-1].endswith("listed below. Ground mapping mode"), _refs_and_texts(items)
    _doc, items = run({1: make_lines([stem, None, (75, "Own ship position and heading."), None,
                                      "3.2.7 Mass. The display shall weigh 5 kg."])})
    assert any("no list items were taken" in r for r in requirements(items)[0].review_reasons), requirements(items)[0].review_reasons


def test_lost_markers_are_restored_from_the_neighbours():
    """'Track mode.' between 'a.' and 'c.' - in the markers' column or in the label column - is item b. Two lost
    markers at the start of a list are counted back from the first letter the scan kept, even when that letter
    was read as a capital ('C.'); a list lettered in capitals keeps its capitals."""
    for indent in (75, 120):
        _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the following modes:", None,
                                          (75, "a. Search mode."), None, (indent, "Track mode."), None, (75, "c. Ground mapping mode.")])})
        rows = requirements(items)
        assert [r.doc_ref for r in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c"], (indent, [(r.doc_ref, r.text) for r in rows])
        assert rows[1].review_reasons == ["List marker missing - taken as 'b.' from the sequence"], rows[1].review_reasons
    f = se.RequirementExtractor._sequence_markers
    tokens = lambda text: [(w, 1.0, "") for w in text.split()]
    kids = lambda texts: [(100, tokens(t), se.Block("list_item", 1, (0, 0, 1, 1))) for t in texts]
    assert [m for m, *_ in f(kids(["Acceleration: 5 g.", "Vibration: 20 Hz.", "C. Shock: 40 g.", "d. Humidity: 95 %."]), 10)] \
        == ["a.", "b.", "c.", "d."]
    assert [m for m, *_ in f(kids(["Flow rate: 5 l/min.", "B. Pressure: 2 bar.", "C. Temperature: 40 C."]), 10)] \
        == ["A.", "B.", "C."]
    assert [m for m, *_ in f(kids(["a. Search.", "b. Track.", "Map. Ground mapping.", "d. Test."]), 10)] == ["a.", "b.", "c.", "d."]


def test_an_item_after_a_figure_caption_inside_a_list_is_kept_when_its_marker_was_lost():
    """a., b., a caption, then 'Shock:  40 g ...' with its marker lost and 'd. Temperature:': the caption is
    exported and the list goes on after it."""
    lines = _tabbed_page(TAB_ITEMS[:2], after=None)
    y = max(ln.box[1] for ln in lines) + 2 * PITCH
    lines.append(make_line("Figure 3. Shock pulse shape.", LEFT + 400, y))
    # (the rest of the list starts after a blank line under the caption; its lead-in line is dropped)
    lines += _tabbed_page([("", "Shock:", ["40 g, 11 ms half-sine pulse."]), TAB_ITEMS[3]], y0=y + PITCH)[1:]
    _doc, items = run({1: lines})
    rows = [(r.doc_ref, r.item_type) for r in items if r.item_type in ("Requirement", "Figure Caption")]
    assert rows == [("3.2.4 a", "Requirement"), ("3.2.4 b", "Requirement"), ("3.2.4 c", "Requirement"),
                    ("3.2.4 d", "Requirement"), ("FIGURE 3", "Figure Caption"), ("3.2.5", "Requirement")], rows


def test_an_item_that_lost_its_marker_in_a_single_spaced_list_is_split_off_by_the_sequence():
    """'a.  Search mode.' / 'Track mode.' / 'c.  Ground mapping mode.' single-spaced: 'Track mode.' starts where a
    wrapped line of a would, but the markers skip b, so a is split where the new sentence starts in its text
    column, and the piece gets 'b.' from the sequence (reported). A gap that cannot be split is flagged."""
    for tab in (" " * 3, " " * 10):
        x_text = 75 + (len("a.") + len(tab)) * CHAR_W
        _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the following modes:", (75, f"a.{tab}Search mode."),
                                          (x_text, "Track mode."), (75, f"c.{tab}Ground mapping mode.")])})
        rows = requirements(items)
        assert [(r.doc_ref, r.text.split(": ", 1)[1]) for r in rows] == \
            [("3.2.4 a", "a. Search mode."), ("3.2.4 b", "b. Track mode."), ("3.2.4 c", "c. Ground mapping mode.")], \
            [(r.doc_ref, r.text) for r in rows]
        assert rows[1].review_reasons == ["List marker missing - taken as 'b.' from the sequence"], rows[1].review_reasons
    f = se.RequirementExtractor._sequence_markers
    tokens = lambda text: [(w, 1.0, "") for w in text.split()]
    kids = [(100, tokens(t), se.Block("list_item", 1, (0, 0, 1, 1))) for t in ("a. Search.", "b. Track.", "d. Test.")]
    out = f(kids, 10)
    assert [m for m, *_ in out] == ["a.", "b.", "d."] and "goes from 'b.' to 'd.'" in out[1][2], out


# ---- a third adversarial review of the fixes above ----
def _row_page(rows: list, y0: int = 300) -> list:
    """rows: text at the margin, [(indent_px, text), ...] pieces on one row, or None for a blank line."""
    lines, y = [], y0
    for row in rows:
        if row is not None:
            for x, t in ([(0, row)] if isinstance(row, str) else row):
                lines.append(make_line(t, LEFT + x, y))
        y += PITCH
    return lines


def test_a_label_list_stays_a_list_when_a_caption_or_table_sentence_follows_it():
    """Labels on tab stops under a lead-in, then a blank line and the NEXT table's caption, or a sentence that
    begins 'Table 4 ...': still one list row per label, not a table."""
    items_ = [("", "Input voltage:", ["22 to 29 VDC."]), ("", "Ripple:", ["1 V peak to peak maximum."]),
              ("", "Power:", ["150 W maximum."]), ("", "Transients:", ["as in MIL-STD-704F."])]
    assert not se._is_caption_text("Table 4 gives the limits for each mode.")
    assert se._is_caption_text("TABLE II. Connector J1 pin assignments.")
    for after in ("TABLE II. Connector J1 pin assignments.", "Table 4 gives the limits for each mode."):
        _doc, items = run({1: _tab_list(items_, stem="3.2.6 Input power. The unit shall meet the following:", after=after)},
                          settings(detect_tables=True, borderless_tables=True))
        rows = [r.text for r in requirements(items)]
        assert not [it for it in items if it.item_type == "Table" and "|" in it.text], (after, [(it.item_type, it.text) for it in items])
        assert rows[:2] == ["The unit shall meet the following: Input voltage: 22 to 29 VDC.",
                            "The unit shall meet the following: Ripple: 1 V peak to peak maximum."], (after, rows)


def test_a_short_list_beside_a_column_of_prose_is_not_read_across():
    """Two columns: a short list on the left, prose on the right - narrow (27 characters), ragged, with one
    numbered paragraph, or a second list of its own. Each column is read on its own."""
    docs = ["a. MIL-STD-461G", "b. MIL-STD-704F", "c. MIL-STD-810H", "d. MIL-STD-1275E", "e. MIL-STD-1553B"]
    narrow = ["The unit shall operate from", "the 28 VDC aircraft bus and", "shall draw no more than 150",
              "W in any mode of operation.", "The unit shall start within", "two seconds of the"]
    ragged = ["The unit shall operate from", "the 28 VDC aircraft bus and shall", "draw no more than 150 W in",
              "any mode of operation. The unit", "shall start within two seconds of", "the application of power."]
    titled = ["3.4 Cooling. The unit shall be", "cooled by forced air. Humidity", "shall not degrade cooling in any",
              "mode. The inlet air shall be at", "25 C at the unit inlet."]
    second = ["a. The radar shall search.", "b. The radar shall track.", "c. The radar shall map.",
              "d. The radar shall show weather.", "e. The radar shall answer."]
    for right, xr in ((narrow, 480), (ragged, 560), (titled, 560), (second, 700)):
        lines = [make_line(t, LEFT + 40, 300 + k * PITCH) for k, t in enumerate(docs)]
        lines += [make_line(t, LEFT + xr, 300 + k * PITCH) for k, t in enumerate(right)]
        _doc, items = run({1: lines})
        mixed = [r.text for r in requirements(items) if "MIL-STD" in r.text and "unit shall" in r.text + "radar shall"
                 and ("shall" in r.text)]
        assert not mixed, (right[0], [r.text for r in requirements(items)])


def test_a_lettered_paragraph_with_its_first_line_indented_is_read_whole():
    """'A. General: The contractor shall provide all labor, materials' with its next line back at the margin:
    the sentence wraps, it does not end the item."""
    _doc, items = run({1: _row_page(["3.1 Installation.", [(75, "A. General: The contractor shall provide all labor, materials")],
                                     "and equipment needed to install the system at each site.", None,
                                     [(75, "B. Cabling: The contractor shall route all cables through")],
                                     "the existing cable trays and shall label each cable at both ends."])})
    texts_ = [r.text for r in requirements(items)]
    assert any(t.endswith("materials and equipment needed to install the system at each site.") for t in texts_), texts_
    assert any(t.endswith("through the existing cable trays and shall label each cable at both ends.") for t in texts_), texts_


def test_an_item_broken_early_with_its_next_line_back_at_the_margin_is_read_whole():
    """'b. Track mode, holding up to twenty targets in' / 'track at the same time.' back at the margin, although
    the next word would have fitted on the line above (a typist's early break): a line that ends in the middle of
    a phrase ('in', 'at', 'the') carries on, and the list goes on to c. (case LST-16)."""
    _doc, items = run({1: _row_page(["3.2.3 Controls. The display shall have a brightness control and a",
                                     "contrast control on its front panel. Each control shall be",
                                     "illuminated for night use and shall be operable with gloved hands",
                                     "in all environmental conditions specified herein.", None,
                                     "3.2.4 Modes. The radar shall provide the following modes:",
                                     [(75, "a. Search mode, with a scan of 120 degrees in azimuth and")],
                                     "60 degrees in elevation at all ranges.",
                                     [(75, "b. Track mode, holding up to twenty targets in")],
                                     "track at the same time.",
                                     [(75, "c. Ground mapping mode.")], None,
                                     "3.2.5 Weight. The radar shall weigh less than 45 kg."])})
    rows = _refs_and_texts(items)
    assert rows[2:5] == [("3.2.4 a", "a. Search mode, with a scan of 120 degrees in azimuth and 60 degrees in "
                                     "elevation at all ranges."),
                         ("3.2.4 b", "b. Track mode, holding up to twenty targets in track at the same time."),
                         ("3.2.4 c", "c. Ground mapping mode.")], rows


def test_a_lost_marker_is_split_off_before_a_marker_read_as_a_capital():
    """'a.   Search mode.' / '     Track mode.' / 'C.   Ground mapping mode.' single-spaced: the scan lost 'b.' and
    read 'c.' as 'C.'. The markers still skip exactly one letter, so 'Track mode.' is split off as b (case LST-10)."""
    _doc, items = run({1: _row_page(["3.2.4 Modes. The radar shall provide the following modes:",
                                     [(75, "a.   Search mode.")], [(150, "Track mode.")],
                                     [(75, "C.   Ground mapping mode.")], None,
                                     "3.2.5 Weight. The radar shall weigh less than 45 kg."])})
    rows = requirements(items)
    stem = "The radar shall provide the following modes:"
    assert [(r.doc_ref, r.text) for r in rows[:3]] == [
        ("3.2.4 a", f"{stem} a. Search mode."), ("3.2.4 b", f"{stem} b. Track mode."),
        ("3.2.4 c", f"{stem} c. Ground mapping mode.")], [(r.doc_ref, r.text) for r in rows]
    assert any("missing" in n for n in rows[1].review_reasons), rows[1].review_reasons


def _recorded_lines(rows: list) -> list:
    """OCR lines recorded from a real scan: (text, (x0, y0, x1, y1)) in the OCR's pixels (220 dpi), with the
    words spread over the line as in a typewriter font."""
    out = []
    for text, (x0, y0, x1, y1) in rows:
        cw, words, pos = (x1 - x0) / len(text), [], 0
        for token in text.split(" "):
            if token:
                words.append(se.Word(token, 0.98, (round(x0 + pos * cw), y0, round(x0 + (pos + len(token)) * cw), y1)))
            pos += len(token) + 1
        out.append(se.Line(text, 0.98, (x0, y0, x1, y1), words))
    return out


def test_a_requirement_after_a_blank_line_does_not_hang_on_an_item_without_a_full_stop():
    """'b. Track mode' (no full stop), a blank line, then 'The operator shall select ...' in the item's text
    column: a requirement of its own, not more of item b. The lines are those the OCR read on case LST-25."""
    _doc, items = run({1: _recorded_lines([
        ("3.2.4 Modes. The radar shall provide the following modes:", (212, 214, 1375, 259)),
        ("a. Search mode", (313, 257, 610, 300)), ("b. Track mode", (315, 300, 590, 340)),
        ("The operator shall select the mode from the front panel.", (375, 382, 1513, 426)),
        ("3.2.5 Weight. The radar shall weigh less than 45 kg.", (212, 462, 1273, 514))])})
    assert _refs_and_texts(items) == [("3.2.4 a", "a. Search mode"), ("3.2.4 b", "b. Track mode"),
                                      ("3.2.4", "The operator shall select the mode from the front panel."),
                                      ("3.2.5", "The radar shall weigh less than 45 kg.")], _refs_and_texts(items)


def test_a_page_of_three_lines_separated_by_blank_lines_is_not_one_block():
    """The top of a page that carries a list on: a value line, a blank line, 'C.  Shock:  40 g ...' (the marker
    read as a capital), a blank line, '3.2.5 weight. The ...' (the title's capital read as a small letter). Two
    gaps cannot say how the page is spaced; they are taken as blank lines, so the three stay apart (case PAGE-01:
    they were one block, and item c and 3.2.5 were lost in the value of the item above)."""
    doc, _items = run({1: _recorded_lines([
        ("3 hours per axis, 7.7 g rms overall.", (779, 215, 1512, 259)), ("C.", (298, 328, 341, 358)),
        ("Shock:", (409, 320, 543, 361)), ("40 g, 11 ms half-sine pulse.", (778, 318, 1354, 366)),
        ("3.2.5 weight. The equipment shall not exceed 45 kilograms.", (213, 401, 1395, 448))])})
    texts = [b.text for b in doc.blocks]
    assert len(texts) == 3 and texts[2].startswith("3.2.5"), texts
    assert se._starts_new_item("3.2.5 weight. The equipment shall not exceed 45 kilograms.")
    assert not se._starts_new_item("3.2.5 of MIL-STD-704F. The unit shall be tested.")


def test_a_list_row_whose_marker_was_read_as_a_capital_starts_a_new_block():
    """The top of a page that carries a tab list on: its first line is the value of the item above, then
    'C.  Shock:  40 g ...' - a marker and a label, although the scan read 'c.' as 'C.' - then 3.2.5. The item row
    is not more of the value above it (case PAGE-01: item c was lost in item b)."""
    doc, _items = run({1: _recorded_lines([
        ("3 hours per axis, 7.7 g rms overall.", (778, 214, 1512, 260)), ("C.", (299, 287, 342, 316)),
        ("Shock:", (409, 278, 543, 320)), ("40 g, 11 ms half-sine pulse.", (778, 277, 1353, 325)),
        ("3.2.5 Weight. The equipment shall not exceed 45 kilograms.", (212, 359, 1396, 408))])})
    assert [b.text for b in doc.blocks] == ["3 hours per axis, 7.7 g rms overall.", "C. Shock: 40 g, 11 ms half-sine pulse.",
                                            "3.2.5 Weight. The equipment shall not exceed 45 kilograms."], \
        [b.text for b in doc.blocks]


def test_a_label_whose_capital_was_read_as_a_small_letter_still_starts_an_item():
    """Labels on tab stops under a lead-in: 'Voltage:', then 'current:' (the scan read 'C' as 'c'), 'Weight:',
    'Cooling:'. Each is an item of its own (case TBL-12: 'current:' was joined to the item above)."""
    _doc, items = run({1: _recorded_lines([
        ("3.2.1 Interface. The interface shall have the following properties:", (214, 215, 1574, 259)),
        ("Voltage:", (273, 287, 442, 332)), ("The unit shall operate from 28 VDC.", (698, 284, 1414, 331)),
        ("current:", (274, 339, 441, 383)), ("The unit shall draw less than 5 A.", (699, 342, 1393, 382)),
        ("Weight:", (273, 397, 424, 439)), ("The unit shall weigh less than 5 kg.", (696, 393, 1432, 441)),
        ("Cooling:", (272, 448, 442, 497)), ("The unit shall be cooled by forced air.", (698, 449, 1490, 492)),
        ("3.2.5 Weight. The equipment shall not exceed 45 kilograms.", (213, 532, 1395, 578))])})
    assert [t for _, t in _refs_and_texts(items)][:4] == [
        "Voltage: The unit shall operate from 28 VDC.", "current: The unit shall draw less than 5 A.",
        "Weight: The unit shall weigh less than 5 kg.", "Cooling: The unit shall be cooled by forced air."], \
        _refs_and_texts(items)


def test_a_value_that_wraps_back_under_its_label_is_not_read_as_the_label():
    """'a.  Vibration   20 Hz to 2000 Hz random, applied in' / 'each of three axes as follows:' under the label,
    then (1) and (2): the value stays in order and the sub-items stay under a."""
    _doc, items = run({1: _row_page(["3.2.4 Environmental conditions. The equipment shall meet each of the following:",
                                     [(80, "a."), (220, "Vibration"), (560, "20 Hz to 2000 Hz random, applied in")],
                                     [(220, "each of three axes as follows:")], [(300, "(1) Level: 0.04 g2/Hz.")],
                                     [(300, "(2) Duration: 3 hours per axis.")],
                                     [(80, "b."), (220, "Shock"), (560, "40 g, 11 ms half-sine pulse.")]])})
    rows = _refs_and_texts(items)
    assert rows[:2] == [("3.2.4 a.1", "a. Vibration 20 Hz to 2000 Hz random, applied in each of three axes as follows: "
                                      "(1) Level: 0.04 g2/Hz."),
                        ("3.2.4 a.2", "a. Vibration 20 Hz to 2000 Hz random, applied in each of three axes as follows: "
                                      "(2) Duration: 3 hours per axis.")], rows


def test_capital_letters_are_judged_per_list_level():
    """'A. Operating conditions:' with 'a. Temperature ...', 'b. Humidity ...' below it: the capitals are the
    list's own letters, not misreads - a sub-list in small letters does not change that."""
    c = CHAR_W
    _doc, items = run({1: _row_page(["3.2.4 Environment. The unit shall meet the following conditions:",
                                     [(5 * c, "A. Operating conditions:")], [(9 * c, "a. Temperature: -40 C to +71 C.")],
                                     [(9 * c, "b. Humidity: 95 percent.")], [(5 * c, "B. Storage conditions:")],
                                     [(9 * c, "a. Temperature: -55 C to +85 C.")]])})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 A.a", "3.2.4 A.b", "3.2.4 B.a"], [(r.doc_ref, r.text) for r in rows]
    assert not any(r.review_reasons for r in rows), [r.review_reasons for r in rows]


def test_a_numbered_heading_with_a_full_stop_still_opens_its_section():
    """'4. Verification.' followed by '4.1 General. ...' is a heading even after a list; '5. Packaging.' /
    '6. Notes.' / '6.1 Intended use. ...' are empty sections, not a list."""
    doc, items = run({1: make_lines(["3.9 Modes. The radar shall provide the following modes:", "a. Search mode.",
                                     "b. Track mode.", "4. Verification.",
                                     "4.1 General. The contractor shall verify each requirement."])})
    assert [r.doc_ref for r in requirements(items)] == ["3.9 a", "3.9 b", "4.1"], [(r.doc_ref, r.text) for r in requirements(items)]
    assert requirements(items)[-1].section.startswith("4 Verification"), requirements(items)[-1].section
    doc, items = run({1: make_lines(["4.3 Records. The contractor shall keep the test records.", None, "5. Packaging.",
                                     "6. Notes.", "6.1 Intended use. The unit is intended for use in aircraft."])})
    assert [b.kind for b in doc.blocks if b.text[:3] in ("5. ", "6. ")] == ["heading", "heading"], \
        [(b.kind, b.text) for b in doc.blocks]


def test_a_requirement_after_a_colon_less_list_keeps_its_own_row():
    """'... the following information.' with short plain items, then 'The display shall be readable in direct
    sunlight.' at the same indent: a requirement of its own, not one more item. The first item may share the
    lead-in's block (single-spaced)."""
    stem = "3.2.6 Displays. The display shall show the following information."
    _doc, items = run({1: make_lines([stem, None, (75, "Own ship position and heading."), None,
                                      (75, "Target range and bearing."), None,
                                      (75, "The display shall be readable in direct sunlight.")])})
    rows = [r.text for r in requirements(items)]
    assert not any(t.endswith("information. The display shall be readable in direct sunlight.") for t in rows), rows
    assert any(t.endswith("The display shall be readable in direct sunlight.") for t in rows), rows
    _doc, items = run({1: make_lines([stem, (75, "Own ship position and heading."), (75, "Target range and bearing."),
                                      (75, "Time of day."), (75, "Waypoint number."), None,
                                      "3.2.7 Mass. The display shall weigh less than 5 kg."])})
    taken = [r.text.split("information. ", 1)[1] for r in requirements(items) if r.doc_ref == "3.2.6"]
    assert taken == ["Own ship position and heading.", "Target range and bearing.", "Time of day.", "Waypoint number."], \
        [(r.doc_ref, r.text) for r in requirements(items)]


def test_a_list_that_counts_in_twos_or_repeats_a_misread_letter_is_not_split():
    """Tests numbered 1., 3., 5. skip on purpose: no item is invented and nothing is flagged. 'a.', 'c.', 'c.', 'd.'
    is a misread 'b.' - corrected, not split."""
    f = se.RequirementExtractor._sequence_markers
    tokens = lambda text: [(w, 1.0, "") for w in text.split()]
    kids = lambda texts: [(100, tokens(t), se.Block("list_item", 1, (0, 0, 1, 1))) for t in texts]
    out = f(kids(["1. Visual examination.", "3. Insulation resistance.", "5. Dielectric withstanding voltage."]), 10)
    assert [m for m, *_ in out] == ["1.", "3.", "5."] and not any(note for _, _, note, _ in out), out
    _doc, items = run({1: make_lines(["3.2.4 Modes. The radar shall provide the following modes:",
                                      (75, "a.   Search mode, with a scan of 120 degrees."), (150, "The scan rate shall be 60 degrees per second."),
                                      (75, "c.   Track mode."), (75, "c.   Ground mapping mode."), (75, "d.   Test mode.")])})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 a", "3.2.4 b", "3.2.4 c", "3.2.4 d"], [(r.doc_ref, r.text) for r in rows]
    assert rows[0].text.endswith("The scan rate shall be 60 degrees per second."), rows[0].text


def test_the_next_numbered_item_after_a_split_off_sentence_stays_in_the_list():
    """'2. Track mode, ...' whose second sentence starts on its own line, then '3. Ground mapping mode.': item 3 is
    the next item (its number follows 2), not a section heading that would swallow the rest of the page."""
    c = CHAR_W
    _doc, items = run({1: _row_page(["3.2.4 Modes. The radar shall provide the following modes:", [(5 * c, "1. Search mode.")],
                                     [(5 * c, "2. Track mode, with up to 20 targets in track.")],
                                     [(8 * c, "Tracks shall be updated once per second.")], [(5 * c, "3. Ground mapping mode.")],
                                     None, "3.2.5 Weight. The radar shall weigh less than 45 kg."])})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["3.2.4 1", "3.2.4 2", "3.2.4 3", "3.2.5"], [(r.doc_ref, r.text) for r in rows]
    assert rows[-1].section == "", rows[-1].section
    # a list of tests that counts in twos: '5.' after '3.' (and its second sentence) is still the next item
    _doc, items = run({1: _row_page(["4.3.2 Retest. The following tests shall be repeated after vibration:",
                                     [(5 * c, "1. Visual examination.")],
                                     [(5 * c, "3. Insulation resistance, measured at 500 VDC.")],
                                     [(8 * c, "Readings shall be recorded on the data sheet.")],
                                     [(5 * c, "5. Dielectric withstanding voltage.")], None,
                                     "4.3.3 Records. The contractor shall keep all test records."])})
    rows = requirements(items)
    assert [r.doc_ref for r in rows] == ["4.3.2 1", "4.3.2 3", "4.3.2 5", "4.3.3"], [(r.doc_ref, r.text) for r in rows]
    assert not any(r.review_reasons for r in rows), [r.review_reasons for r in rows]


def _line_at(text: str, box: tuple) -> se.Line:
    """An OCR line at a box measured on a real scan, its words spread over the box's width."""
    x0, y0, x1, y1 = box
    tokens = text.split()
    char_w = (x1 - x0) / max(1, len(text))
    words, x = [], x0
    for t in tokens:
        words.append(se.Word(t, 0.98, (x, y0, x + len(t) * char_w, y1)))
        x += (len(t) + 1) * char_w
    return se.Line(text, 0.98, box, words)


def test_short_values_on_a_real_scan_stay_with_their_labels():
    """Line boxes measured on two rendered, OCR'd pages (typewriter and serif). The values are short and all
    about as long as each other, so every value line looks 'full'; a few rows of the list cut off from the
    rest must not be judged again on less evidence than the whole list gave."""
    mono = [("3.2.6 Input power. The unit shall operate with an input:", (215, 217, 1328, 257)),
            ("a. Voltage:", (290, 279, 544, 321)), ("within 22 to 29 VDC,", (917, 279, 1318, 320)),
            ("b.", (291, 343, 383, 382)), ("Ripple:", (366, 340, 526, 385)), ("c. Power:", (288, 402, 505, 447)),
            ("d. Transients:", (289, 465, 604, 509)), ("less than 1 V peak to peak,", (919, 340, 1452, 383)),
            ("not more than 150 W, and", (918, 405, 1404, 445)), ("per MIL-STD-704F.", (917, 467, 1260, 509)),
            ("3.2.5 Weight. The equipment shall not exceed 45 kilograms.", (215, 551, 1367, 592))]
    serif = [("3.2.6 Input power. The unit shall operate with an input:", (212, 217, 952, 264)),
             ("a.", (291, 289, 325, 321)), ("Voltage:", (376, 279, 502, 327)), ("b.", (290, 344, 327, 384)),
             ("Ripple:", (377, 344, 489, 388)), ("C.", (291, 413, 325, 446)), ("Power:", (377, 407, 484, 446)),
             ("d.", (292, 472, 326, 506)), ("Transients:", (377, 469, 537, 510)),
             ("within 22 to 29 VDC,", (919, 280, 1211, 321)), ("less than 1 V peak to peak,", (917, 345, 1280, 385)),
             ("not more than 150 W, and", (919, 411, 1269, 444)), ("per MIL-STD-704F.", (917, 469, 1198, 512)),
             ("3.2.5 Weight. The equipment shall not exceed 45 kilograms.", (212, 551, 1019, 598))]
    for page in (mono, serif):
        _doc, items = run({1: [_line_at(t, b) for t, b in page]})
        rows = _refs_and_texts(items)
        assert rows[:4] == [("3.2.6 a", "a. Voltage: within 22 to 29 VDC,"), ("3.2.6 b", "b. Ripple: less than 1 V peak to peak,"),
                            ("3.2.6 c", "c. Power: not more than 150 W, and"), ("3.2.6 d", "d. Transients: per MIL-STD-704F.")], rows


def test_a_grid_of_wrapped_labels_beside_list_markers_is_a_list():
    """'Storage' / 'temperature:' in the first column of a borderless grid is one label wrapped over two rows;
    with the markers a., b., c. standing left of the grid it is a list on tab stops, not a table."""
    assert se._join_wrapped_labels(["Storage", "temperature:", "Operating", "temperature:", "Humidity:"]) == \
        ["Storage temperature:", "Operating temperature:", "Humidity:"]
    assert se._join_wrapped_labels(["Voltage", "Current"]) == ["Voltage", "Current"]
    grid = [["Storage", "-55 C to +85 C for"], ["temperature:", "up to 5 years."], ["Operating", "-40 C to +71 C."],
            ["temperature:", ""], ["Humidity:", "95 percent."]]
    tbox = (LEFT + 160, 400, LEFT + 1200, 400 + 5 * PITCH)
    markers = [make_line(m, LEFT + 80, 400 + k * 2 * PITCH) for k, m in enumerate(("a.", "b.", "c."))]
    assert se._tab_list_in_context(grid, tbox, markers, DPI)


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
# 1.5.0: how the text is printed, tables and lists, autocorrection, document structure, DOORS
# =====================================================================================================================
def _draw_formatted(rows: list, kind: str = "serif", dpi: int = 300, ruled_under: int = -1) -> tuple:
    """A page image with lines of text printed as asked, and their OCR lines with one box per word (the boxes an OCR
    engine gives: from the top of the capitals to the descenders). rows: [[(text, underlined, bold), ...], ...].
    ruled_under: the row under which a rule is drawn across the whole page, as a table draws one."""
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(HERE / "cases"))
    import casekit
    regular = ImageFont.truetype(casekit.FONT_FILES[kind], round(11 / 72 * dpi))
    heavy = ImageFont.truetype(casekit.BOLD_FILES[kind], round(11 / 72 * dpi))
    img = Image.new("L", (int(8.5 * dpi), int(11 * dpi)), 255)
    d = ImageDraw.Draw(img)
    lines, y = [], dpi
    for k, row in enumerate(rows):
        x, words = dpi, []
        for text, underlined, bold in row:
            f = heavy if bold else regular
            ascent, descent = f.getmetrics()
            start = x
            for word in text.split():
                d.text((x, y), word, font=f, fill=0)
                width = f.getlength(word)
                words.append(se.Word(word, 0.99, (int(x), int(y + 0.15 * ascent), int(x + width),
                                                  int(y + ascent + 0.6 * descent))))
                x += width + f.getlength(" ")
            if underlined:
                uy = y + ascent + max(2, round(0.12 * f.size))
                d.line((start, uy, x - f.getlength(" "), uy), fill=0, width=max(2, round(0.06 * f.size)))
            x += 0.4 * dpi
        if k == ruled_under:
            ry = y + regular.getmetrics()[0] + max(2, round(0.12 * regular.size))
            d.line((0.5 * dpi, ry, 8 * dpi, ry), fill=0, width=3)
        box = (min(w.box[0] for w in words), min(w.box[1] for w in words), max(w.box[2] for w in words),
               max(w.box[3] for w in words))
        lines.append(se.Line(" ".join(w.text for w in words), 0.99, box, words))
        y += round(0.3 * dpi)
    return np.array(img), lines


def test_underlined_words_and_bold_lines_are_measured_on_the_page():
    """An underline under a title is found word by word, in a serif and a typewriter font; a rule printed across
    the page under a line (a table's rule) is not an underline; a bold line is measured heavier than the page's
    ordinary text. Measured on the page image itself, as the tool does before its clean-up."""
    rows = [[("3.2.1", False, False), ("Power input", True, False), ("The equipment shall operate from 115 V.", False, False)],
            [("The quick brown fox jumps over the lazy dog, typing gyp jog quay.", False, False)],
            [("Bold words; equipment; typography; jumping quickly.", False, True)],
            [("Parameter values under a ruled line across the page.", False, False)],
            [("Normal words; equipment; typography; jumping quickly.", False, False)]]
    for kind in ("serif", "mono"):
        gray, lines = _draw_formatted(rows, kind, ruled_under=3)
        se.measure_text_format(gray, lines, 300)
        marked = [[w.text for w in ln.words if w.underline] for ln in lines]
        assert marked == [["Power", "input"], [], [], [], []], (kind, marked)
        assert lines[2].weight >= 1.2 and all(0.85 <= lines[k].weight <= 1.1 for k in (0, 1, 3, 4)), \
            (kind, [ln.weight for ln in lines])
        assert isinstance(lines[2].weight, float) and type(lines[0].words[1].underline) is bool   # (JSON cache)


def test_a_table_heading_row_is_one_only_when_printed_as_one():
    """A first row of short words is not a heading row by its words alone: it must be set apart in print
    (underlined, bold, capitals) or name the columns. A data row such as 'Voltage: | 28 VDC nominal | Test' is never
    taken for column names."""
    def words(row, underline=False, weight=1.0):
        return [(se.Word(t, 0.99, (0, 0, 10, 10), underline=underline), weight) for t in " ".join(row).split()]
    data = [["Input voltage", "22 to 29 VDC", "Test"], ["Ripple", "1.5 V", "Analysis"]]
    plain = [["Antenna", "Receiver", "Display"]] + data
    assert se._header_rows(plain, [], [words(r) for r in plain]) == (0, "")
    assert se._header_rows(plain, [], [words(plain[0], underline=True)] + [words(r) for r in data]) == (1, "underlined")
    assert se._header_rows(plain, [], [words(plain[0], weight=1.4)] + [words(r) for r in data]) == (1, "bold")
    named = [["Parameter", "Requirement", "Method"]] + data
    assert se._header_rows(named, [], [words(r) for r in named]) == (1, "column names")
    capitals = [["SIGNAL", "LEVEL", "SOURCE"]] + data
    assert se._header_rows(capitals, [], [words(r) for r in capitals]) == (1, "capitals")
    first_data = [["Voltage:", "28 VDC nominal", "Test"], ["Current:", "5 A maximum", "Test"]]
    assert not se._names_columns(first_data[0])
    assert se._header_rows(first_data, [], [words(r) for r in first_data]) == (0, "")


def test_a_table_without_heading_or_title_is_shown_as_a_list():
    """Columns with no heading row and no title are a list: each row one list entry, its cells kept apart and in
    order, and a row whose first cell is empty is the wrapped line of the entry above it."""
    lines = make_lines([(0, "MIL-STD-461G       Requirements for the Control of Electromagnetic"),
                        (0, "                   Interference Characteristics"),
                        (0, "MIL-STD-704F       Aircraft Electric Power Characteristics")], y0=600)
    grid = [["MIL-STD-461G", "Requirements for the Control of Electromagnetic"], ["", "Interference Characteristics"],
            ["MIL-STD-704F", "Aircraft Electric Power Characteristics"]]
    boxes = [[(LEFT, ln.box[1], LEFT + 250, ln.box[3]), (LEFT + 285, ln.box[1], LEFT + 1100, ln.box[3])] for ln in lines]
    table = se.TableData(grid=grid, conf=[[0.99, 0.99] for _ in grid], cell_boxes=boxes)
    block = se.Block("table", 1, (LEFT, lines[0].box[1], LEFT + 1100, lines[-1].box[3]), lines=lines, table=table)
    rows = se.table_rows_as_list(block, DPI)
    assert [b.kind for b in rows] == ["list_item", "list_item"], [b.kind for b in rows]
    assert rows[0].meta["cells"] == ["MIL-STD-461G", "Requirements for the Control of Electromagnetic Interference "
                                     "Characteristics"], rows[0].meta["cells"]
    assert rows[1].text == "MIL-STD-704F Aircraft Electric Power Characteristics" and rows[0].meta["from_table"]
    assert len(rows[0].lines) == 2 and rows[0].meta["cell_x"][0] == 0.0


def test_a_table_carried_onto_the_next_page_without_its_heading_row_is_joined():
    """A table that ends a page goes on at the top of the next page without repeating its heading row: the piece is
    joined to it, with its columns matched by position. A grid at the top of a page that continues nothing (the page
    before ended with text) is a list."""
    def table_block(page, grid, top, header_format=""):
        boxes = [[(LEFT + 400 * c, top + 60 * r, LEFT + 400 * c + 350, top + 60 * r + 40) for c in range(len(row))]
                 for r, row in enumerate(grid)]
        lines = [make_line("   ".join(row), LEFT, top + 60 * r) for r, row in enumerate(grid)]
        t = se.TableData(grid=grid, conf=[[0.99] * len(row) for row in grid], cell_boxes=boxes,
                         header_rows=1 if header_format else 0, header_format=header_format)
        b = se.Block("table", page, (LEFT, top, LEFT + 1150, top + 60 * len(grid)), lines=lines, table=t)
        if not header_format:
            b.meta["may_continue"] = True
        return b
    s = settings()
    doc = se.DocResult(source="t.pdf", engine="standard")
    for n in (1, 2):
        doc.pages.append(se.PageInfo(number=n, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI))
    doc.blocks = [table_block(1, [["Signal", "Level", "Source"], ["Power", "28 V", "J1"], ["Ground", "0 V", "J1"]],
                              1900, "underlined"),
                  table_block(2, [["Clock", "5 V", "J2"], ["Reset", "5 V", "J2"]], 250)]
    se.finalize_document(doc, s)
    tables = [b for b in doc.blocks if b.kind == "table"]
    assert len(tables) == 1 and tables[0].table.n_rows == 5, [(b.kind, b.text) for b in doc.blocks]
    assert tables[0].table.grid[3] == ["Clock", "5 V", "J2"] and tables[0].pages == [1, 2], tables[0].table.grid

    doc = se.DocResult(source="t.pdf", engine="standard")
    for n in (1, 2):
        doc.pages.append(se.PageInfo(number=n, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI))
    doc.blocks = se.analyze_page(1, blank_page(), make_lines(["3.1 General. The unit shall be painted."], y0=1900), s)
    doc.blocks.append(table_block(2, [["Clock", "5 V", "J2"], ["Reset", "5 V", "J2"]], 250))
    se.finalize_document(doc, s)
    assert not any(b.kind == "table" for b in doc.blocks), [(b.kind, b.text) for b in doc.blocks]
    assert [b.text for b in doc.blocks if b.kind == "list_item"] == ["Clock 5 V J2", "Reset 5 V J2"]


def test_look_alike_misreads_are_corrected_only_when_certain():
    """A letter or digit the scan misread for one of the same shape is put back when exactly one ordinary word comes
    out ('requ1red', 'c0ntrol', 'systern'), as is a same-shape capital ('sCope') and a number with a letter O or l
    ('1O0'). Acronyms ('UTC' is not 'UTE'), Roman numerals, identifiers, words the document repeats and real words
    are never changed. A word one letter away from a word the document writes elsewhere is corrected, but marked
    'twin': it stays a word to check."""
    from collections import Counter
    checker = se.WordChecker(Counter({"government": 3, "the": 20, "systen": 2}), settings())
    assert checker.correct("requ1red", "") == ("required", "word")
    assert checker.correct("c0ntrol.", "") == ("control.", "word")
    assert checker.correct("systern", "") == ("system", "word")
    assert checker.correct("sCope", "") == ("scope", "capital")
    assert checker.correct("1O0", "") == ("100", "number")
    assert checker.correct("governmient", "not in the English dictionary") == ("government", "twin")
    for left_alone in ("UTC", "UTC.", "VIII.", "iii", "MIL-STD-461G", "SW-001", "l/min", "shall", "Horn", "systen",
                       "TABLE", "0.65", "A", "I"):
        assert checker.correct(left_alone, checker.issue(left_alone, left_alone)) == ("", ""), left_alone
    off = se.WordChecker(Counter(), settings(spell_check_flags=False))
    assert off.correct("requ1red", "") == ("", "")          # (no dictionary: nothing is certain)


def test_corrected_words_are_listed_and_marked_and_a_guess_is_still_checked():
    """A correction changes the row's text, is listed in the OCR Corrections column (not in Review Reasons), and is
    highlighted in the Word report. A number the tool corrected, and a one-letter guess from the document's own
    words, still mark the row Needs Review."""
    lines = make_lines(["3.1 Power. The unit shall be requ1red to draw no more than 1O0 W.", None,
                        "3.2 Ownership. The government shall own the data.", None,
                        "3.3 Rights. The governmient shall approve the government data."])
    doc, items = run({1: lines})
    power = find(items, "draw no more")
    assert "required" in power.text and "100 W" in power.text, power.text
    assert "'requ1red' -> 'required'" in power.corrections and "'1O0' -> '100'" in power.corrections, power.corrections
    assert power.needs_review and any("Number corrected" in r for r in power.review_reasons), power.review_reasons
    assert not any("requ1red" in r for r in power.review_reasons), power.review_reasons
    guess = find(items, "approve")
    assert "The government shall approve" in guess.text and guess.needs_review, (guess.text, guess.review_reasons)
    with tempfile.TemporaryDirectory() as tmp:
        report = se.write_word_report(Path(tmp) / "r.docx", doc, items, settings(word_page_images=False))
        import docx
        green = [r.text.strip() for p in docx.Document(str(report)).paragraphs for r in p.runs
                 if r.font.highlight_color is not None and "GREEN" in str(r.font.highlight_color)]
        assert any("required" in t for t in green) and any("government" in t for t in green), green
    _, raw = run({1: lines}, settings(autocorrect=False))
    assert "requ1red" in find(raw, "draw no more").text and not find(raw, "draw no more").corrections


def test_sections_nest_by_their_numbers_and_run_in_titles_are_split():
    """Each numbered paragraph is a section at the level of its number (3 = 1, 3.1 = 2, 3.1.1.1 = 4) whatever its
    indent, a run-in title is split from its text - ended by a full stop, or by underlining when the number is
    indented by a tab - and the sections are typed by their titles."""
    lines = make_lines(["1. SCOPE", None, "1.1 Scope. This specification covers the radar.", None,
                        "3. REQUIREMENTS", None, (90, "3.1  Power input  The equipment shall operate from 115 V."),
                        None, "3.1.1 Inrush. The inrush current shall not exceed 20 A.", None,
                        (160, "3.1.1.1 The inrush shall be measured at turn on."), None,
                        "4. VERIFICATION", None, "4.1 Tests. The tests shall be done in the laboratory."])
    for w in lines[3].words[1:3]:                       # "Power input" printed underlined
        w.underline = True
    s = settings()
    doc, items = run({1: lines}, s)
    headings = se.build_outline(doc, se.RequirementExtractor(s))
    got = [(h["level"], h["number"], h["title"], h["type"]) for h in headings]
    assert got == [(1, "1", "SCOPE", "scope"), (2, "1.1", "Scope", "scope"), (1, "3", "REQUIREMENTS", "requirements"),
                   (2, "3.1", "Power input", "requirements"), (3, "3.1.1", "Inrush", "requirements"),
                   (4, "3.1.1.1", "", "requirements"), (1, "4", "VERIFICATION", "verification"),
                   (2, "4.1", "Tests", "verification")], got
    power = find(items, "115 V")
    assert (power.doc_ref, power.title, power.text) == ("3.1", "Power input", "The equipment shall operate from 115 V.")


def test_document_numbers_are_recognised_and_entries_parsed():
    """The numbers of military, federal and industry documents are recognised as the start of a document entry -
    paragraph numbers, requirement IDs and designators are not - and an entry gives its number, title and the
    paragraphs that call it up, in the tab-stop and the dash layouts."""
    for doc_id in ("MIL-STD-461G", "MIL-DTL-38999/26", "MIL-PRF-19500/543", "DOD-STD-1686", "FED-STD-595",
                   "QQ-A-250/4", "SAE AS50881", "ANSI/EIA-649", "IEEE Std 1394", "ISO 9001:2015", "JESD22-A114",
                   "MIL-HDBK-217F", "DI-IPSC-81433", "ASTM D3951", "RTCA DO-160G", "NASA-STD-8739.4"):
        assert se.RE_DOC_ID_START.match(doc_id + " Title of the document"), doc_id
    for not_a_document in ("3.2.1", "SW-001", "F-35", "3.3 V", "TABLE I", "CB12", "The radar"):
        assert not se.RE_DOC_ID_START.match(not_a_document + " shall"), not_a_document
    entry = se.parse_document_entry("MIL-STD-461G  Requirements for the Control of Electromagnetic Interference "
                                    "Characteristics  3.2.5, 4.3.2")
    assert entry == {"id": "MIL-STD-461G", "title": "Requirements for the Control of Electromagnetic Interference "
                     "Characteristics", "paragraphs": "3.2.5, 4.3.2"}, entry
    dash = se.parse_document_entry("MIL-STD-810H - Environmental Engineering Considerations and Laboratory Tests")
    assert dash["title"] == "Environmental Engineering Considerations and Laboratory Tests" and not dash["paragraphs"]
    assert se.parse_document_entry("The radar shall meet MIL-STD-461G.") is None


def test_the_documents_of_section_2_are_read_under_their_group_titles():
    """In section 2 each line of a document list is one document, filed under its group title ('SPECIFICATIONS')
    and the sub-title indented under it ('Military'); a section titled by its first sentence ('The following
    documents form a part of this specification') counts too."""
    rows = [["2. APPLICABLE DOCUMENTS"], None, ["2.1 Government documents."], None, [(300, "SPECIFICATIONS")], None,
            [(90, "Military")], None,
            [(0, "MIL-PRF-38534"), (300, "Hybrid Microcircuits, General Specification for"), (1100, "3.2.1")],
            [(0, "MIL-DTL-38999"), (300, "Connectors, Electrical, Circular"), (1100, "3.4")], None,
            [(300, "STANDARDS")], None, [(90, "Military")], None,
            [(0, "MIL-STD-461G"), (300, "Requirements for the Control of Electromagnetic"), (1100, "3.2.5")],
            [(300, "Interference Characteristics")], None,
            ["3. REQUIREMENTS"], None, ["3.1 General. The radar shall meet MIL-STD-461G."]]
    lines, y = [], 300
    for row in rows:                    # (the OCR returns the pieces of a line on tab stops as lines of their own)
        for piece in row or []:
            indent, text = piece if isinstance(piece, tuple) else (0, piece)
            lines.append(make_line(text, LEFT + indent, y))
        y += PITCH
    s = settings()
    doc, items = run({1: lines}, s)
    se.build_outline(doc, se.RequirementExtractor(s))
    entries = se.read_document_lists(doc)
    got = [(e["group"], e["subgroup"], e["id"], e["title"], e["paragraphs"]) for e in entries]
    assert got == [("SPECIFICATIONS", "Military", "MIL-PRF-38534", "Hybrid Microcircuits, General Specification for",
                    "3.2.1"),
                   ("SPECIFICATIONS", "Military", "MIL-DTL-38999", "Connectors, Electrical, Circular", "3.4"),
                   ("STANDARDS", "Military", "MIL-STD-461G", "Requirements for the Control of Electromagnetic "
                    "Interference Characteristics", "3.2.5")], got
    assert len(requirements(items)) == 1, texts(items)


def test_the_doors_document_follows_the_rules_doors_imports_by():
    """<name>_for_doors.docx: Heading 1-9 only for numbered sections, no level skipped (a parent the scan did not
    show is written as a placeholder), nothing else with an outline level, no empty paragraphs, tabs or line
    breaks, tables without merged cells and with borders on every cell, no tags or marks - and a heading that is only
    a number keeps it when heading numbers are removed."""
    import docx
    lines = make_lines(["SPEC-1234 Rev A", None, "3. REQUIREMENTS", None, "3.2.1 Range. The radar shall detect targets.",
                        None, "3.2.1.1 The radar shall detect a 1 m2 target at 100 km.", None,
                        "3.3 Cooling. The radar shall be cooled by forced air."])
    s = settings()
    doc, items = run({1: lines}, s)
    table = se.TableData(grid=[["Signal", "Level", "Level"], ["Power", "28 V", "J1"]], conf=[[1.0] * 3] * 2,
                         merges=[(0, 1, 0, 2)], header_rows=1, header_format="bold")
    doc.blocks.append(se.Block("table", 1, (LEFT, 2400, LEFT + 1000, 2500), table=table, uid=len(doc.blocks) + 1))
    se.build_outline(doc, se.RequirementExtractor(s))
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for numbers in ("keep", "remove"):
        style = Path(tempfile.mkdtemp()) / "style.ini"
        style.write_text(f"[doors]\nheading_numbers = {numbers}\n", encoding="utf-8")
        out = se.write_doors_document(style.parent / "d.docx", doc, items, settings(word_style_file=style))
        d = docx.Document(str(out))
        paras = [(p.style.name, p.text) for p in d.paragraphs]
        headings = [(name, text) for name, text in paras if name.startswith("Heading")]
        if numbers == "keep":
            assert headings == [("Heading 1", "3. REQUIREMENTS"), ("Heading 2", "3.2 [heading not found in the scan]"),
                                ("Heading 3", "3.2.1 Range"), ("Heading 4", "3.2.1.1"), ("Heading 2", "3.3 Cooling")], headings
        else:
            assert headings == [("Heading 1", "REQUIREMENTS"), ("Heading 2", "[heading not found in the scan]"),
                                ("Heading 3", "Range"), ("Heading 4", "3.2.1.1"), ("Heading 2", "Cooling")], headings
        assert ("Normal", "SPEC-1234 Rev A") in paras and paras[0][1] == "SPEC-1234 Rev A", paras[:3]
        assert all(text.strip() for _name, text in paras[:-1]), paras
        assert not any("[R-" in text for _name, text in paras), paras
        body = d.element.body
        assert not body.findall(f".//{W}tab") and not body.findall(f".//{W}br") and not body.findall(f".//{W}highlight")
        assert not body.findall(f".//{W}gridSpan") and not body.findall(f".//{W}vMerge")
        cells = body.findall(f".//{W}tc")
        assert len(cells) == 6 and all(tc.find(f"{W}tcPr/{W}tcBorders") is not None for tc in cells)
        for st in d.styles:                         # an outline level (own, or from the style it is based on)
            if st.type != se.WD_STYLE_TYPE.PARAGRAPH or st.name.startswith("Heading"):
                continue
            chain, level = st, None
            while chain is not None and level is None:
                found = chain.element.find(f"{W}pPr/{W}outlineLvl")
                level = found.get(f"{W}val") if found is not None else None
                chain = chain.base_style
            assert level in (None, "9"), (st.name, level)       # 9 = body text


def test_merged_cells_are_the_same_in_excel_and_word_and_heading_text_stays_readable():
    """Merged ranges that overlap or run out of the table are cut down once (_table_merges) and used by both files,
    so a merged heading cell can no longer be emptied in Word; heading text that would be the colour of its shading
    (white Table Heading text on a light row) is written in Word's automatic colour."""
    t = se.TableData(grid=[["Parameter", "Parameter", "Units"], ["Voltage", "Parameter", "V"], ["Current", "5", "A"]],
                     conf=[[1.0] * 3] * 3, merges=[(0, 0, 0, 1), (0, 1, 1, 1), (2, 2, 2, 5), (1, 0, 1, 0)],
                     header_rows=1, header_format="bold")
    assert se._table_merges(t) == [(0, 0, 0, 1)], se._table_merges(t)
    import docx
    tmp = Path(tempfile.mkdtemp())
    style = tmp / "style.ini"
    style.write_text("[table header row]\ncolor = FFFFFF\n", encoding="utf-8")
    doc = se.DocResult(source="t.pdf", engine="standard", pages=[se.PageInfo(1, PAGE_W, PAGE_H, DPI, DPI)],
                       blocks=[se.Block("table", 1, (100, 100, 900, 400), table=t, uid=1)])
    out = se.write_word_report(tmp / "r.docx", doc, [], settings(word_style_file=style, word_page_images=False))
    table = docx.Document(str(out)).tables[0]
    assert [c.text for c in table.rows[0].cells] == ["Parameter", "Parameter", "Units"]
    assert [c.text for c in table.rows[1].cells] == ["Voltage", "Parameter", "V"]
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    colours = {c.get(f"{W}val") for c in table._tbl.findall(f".//{W}tr")[0].findall(f".//{W}color")}
    assert colours == {"auto"}, colours


def test_the_excel_file_links_tables_and_holds_the_structure_and_the_documents():
    """A table's row in Extracted Items links to its sheet instead of holding the grid as text; the Document
    Structure and Applicable Documents sheets are written; the output folder carries the version."""
    import openpyxl
    lines = make_lines(["2. APPLICABLE DOCUMENTS", None, "MIL-STD-461G    Requirements for the Control of EMI    3.1",
                        None, "3. REQUIREMENTS", None, "3.1 General. The radar shall meet MIL-STD-461G."])
    s = settings()
    doc, items = run({1: lines}, s)
    t = se.TableData(grid=[["Signal", "Level"], ["Power", "28 V"]], conf=[[1.0] * 2] * 2, header_rows=1,
                     header_format="underlined")
    doc.blocks.append(se.Block("table", 1, (LEFT, 2400, LEFT + 1000, 2500), table=t, uid=len(doc.blocks) + 1,
                               meta={"caption": "TABLE I. Signals."}))
    items = se.RequirementExtractor(s).extract(doc)
    se.build_outline(doc, se.RequirementExtractor(s))
    se.read_document_lists(doc)
    out = se.write_workbook(Path(tempfile.mkdtemp()) / "x.xlsx", [(doc, items)], s)
    wb = openpyxl.load_workbook(out)
    assert {"Document Structure", "Applicable Documents"} <= set(wb.sheetnames), wb.sheetnames
    ws = wb["Extracted Items"]
    header = [c.value for c in ws[1]]
    row = next(r for r in ws.iter_rows(min_row=2) if r[header.index("Type")].value == "Table")
    content = row[header.index("Content")]
    assert content.hyperlink is not None and content.hyperlink.location.startswith("'T001'"), content.value
    docs = [[c.value for c in r] for r in wb["Applicable Documents"].iter_rows(min_row=2)]
    assert any("MIL-STD-461G" in [str(v) for v in r] for r in docs), docs
    assert se.OUTPUT_FOLDER == "extraction_output_" + se.__version__


def test_the_commit_is_read_from_the_git_folder_also_after_git_gc():
    """The commit shown beside the build is read from .git without running git: from the branch's own file, from
    packed-refs after 'git gc', or from a detached HEAD; nothing when the folder is not a checkout."""
    root = Path(tempfile.mkdtemp())
    assert se._git_commit(root) == ""
    git = root / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "packed-refs").write_text("# pack-refs with: peeled\n0123456789abcdef refs/heads/main\n", encoding="utf-8")
    assert se._git_commit(root) == "0123456"
    (git / "refs" / "heads" / "main").write_text("fedcba9876543210\n", encoding="utf-8")
    assert se._git_commit(root) == "fedcba9"
    (git / "HEAD").write_text("abcdef0123456789\n", encoding="utf-8")
    assert se._git_commit(root) == "abcdef0"


def test_the_code_guide_names_only_functions_that_exist():
    """CODE_GUIDE.md tells someone editing the tool which function does each step. A function renamed or removed
    must not leave the guide pointing at nothing: every `name()` it mentions must exist."""
    guide = (HERE.parent / "CODE_GUIDE.md").read_text(encoding="utf-8")
    missing = []
    for name in sorted(set(re.findall(r"`([A-Za-z_][A-Za-z0-9_.]*)\(\)`", guide))):
        if name in ("name", "Class.name", "Table.cell", "bool", "int", "float"):
            continue                                    # (the guide's own explanation, python-docx, built-ins)
        obj = se
        for part in name.split("."):
            obj = getattr(obj, part, None)
        if not callable(obj):
            missing.append(name)
    assert not missing, f"CODE_GUIDE.md names functions that do not exist: {missing}"


# =====================================================================================================================
# Tested configuration: supported Python versions and the pinned package versions (constraints.txt)
# =====================================================================================================================
def test_the_case_library_is_well_formed_and_its_catalog_is_up_to_date():
    """tests/cases: every case has its own ID shaped like 'TAB-01', a page, and the rows (or tables) the tool must
    produce; and CASEBOOK.pdf was written from the current cases and rule tests. After adding or changing a case,
    or a test in this file, run: python tests/cases/build_cases.py"""
    sys.path.insert(0, str(HERE / "cases"))
    import casekit
    import pypdfium2
    cases = casekit.load_cases()                     # (checks IDs, pages and expectations as it loads them)
    assert len(cases) >= 100, len(cases)
    for c in cases:
        assert c.title and c.situation and c.risk and c.source, c.id
        assert all(r.doc_ref is not None and r.content for r in c.expect), c.id
    catalog = HERE / "cases" / "CASEBOOK.pdf"
    assert catalog.exists(), "tests/cases/CASEBOOK.pdf is missing - run: python tests/cases/build_cases.py"
    pdf = pypdfium2.PdfDocument(str(catalog))
    try:
        keywords = pdf.get_metadata_dict().get("Keywords", "")
    finally:
        pdf.close()
    assert keywords == f"casebook-fingerprint:{casekit.catalog_fingerprint()}", \
        "tests/cases/CASEBOOK.pdf is out of date - run: python tests/cases/build_cases.py"


# ---- the look of the Word report: style file, template, starter template (section 11) -----------------------------
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _report_sample(s: se.Settings | None = None) -> tuple:
    """A one-page document with every part of the report: a heading, a requirement paragraph, a plain paragraph,
    a list under a stem, a caption, a table with a heading row and a low-confidence cell, and a running header."""
    s = s or settings()
    doc = se.DocResult(source="sample.pdf", engine="standard")
    doc.pages.append(se.PageInfo(number=1, width=PAGE_W, height=PAGE_H, source_dpi=DPI, dpi=DPI))
    lines = make_lines(["3.2 Electrical requirements", None,
                        "3.2.1 Output. The power supply shall deliver 28 V DC.", None,
                        "This paragraph explains the background of the design.", None,
                        "3.2.2 Modes. The radar shall provide the following modes:",
                        (60, "a. Search mode."), (60, "b. Track mode."), None,
                        "TABLE I. Power characteristics."], y0=300)
    doc.blocks.extend(se.analyze_page(1, blank_page(), lines, s))
    grid = [["Parameter", "Value"], ["Voltage", "28 V"], ["Ripple", "0.5 V"]]
    doc.blocks.append(se.Block("table", 1, (220, 1300, 1500, 1500),           # (its heading row is printed in bold)
                               table=se.TableData(grid=grid, conf=[[1.0, 1.0], [1.0, 1.0], [1.0, 0.4]],
                                                  header_format="bold")))
    doc.blocks.append(se.Block("page_header", 1, (220, 80, 900, 110), text="SPEC-1234 Rev A"))
    se.finalize_document(doc, s)
    items = se.RequirementExtractor(s).extract(doc)
    return doc, items, s


def _write_report(folder: Path, style_text: str | None = None, s: se.Settings | None = None, sample=None,
                  name: str = "report.docx"):
    """Write the sample's report with a style file holding `style_text` (None = the tool's own look, no file)."""
    import docx
    doc, items, s = sample or _report_sample(s)
    if style_text is None:
        s.word_style_file = None
    else:
        s.word_style_file = folder / f"{Path(name).stem}.ini"
        s.word_style_file.write_text(style_text, encoding="utf-8")
    path = se.write_word_report(folder / name, doc, items, s)
    return docx.Document(path), path


def _style_value(d, style_name: str, prop: str):
    """A style's own value or the one it inherits ('size', 'font', 'bold', 'italic', 'color', 'align', 'after',
    'line', 'left')."""
    from docx.oxml.ns import qn
    root = d.styles.element
    el = se._find_style_element(root, style_name)
    while el is not None:
        rpr, ppr = el.find(qn("w:rPr")), el.find(qn("w:pPr"))
        value = None
        if prop == "size" and rpr is not None and rpr.find(qn("w:sz")) is not None:
            value = int(rpr.find(qn("w:sz")).get(qn("w:val"))) / 2
        elif prop == "font" and rpr is not None and rpr.find(qn("w:rFonts")) is not None:
            fonts = rpr.find(qn("w:rFonts"))
            value = fonts.get(qn("w:asciiTheme")) and "theme" or fonts.get(qn("w:ascii"))
        elif prop in ("bold", "italic") and rpr is not None and rpr.find(qn("w:" + prop[0])) is not None:
            value = rpr.find(qn("w:" + prop[0])).get(qn("w:val")) not in ("0", "false")
        elif prop == "color" and rpr is not None and rpr.find(qn("w:color")) is not None:
            value = rpr.find(qn("w:color")).get(qn("w:val"))
        elif prop == "align" and ppr is not None and ppr.find(qn("w:jc")) is not None:
            value = ppr.find(qn("w:jc")).get(qn("w:val"))
        elif prop in ("after", "line") and ppr is not None and ppr.find(qn("w:spacing")) is not None:
            value = ppr.find(qn("w:spacing")).get(qn("w:" + prop))
        elif prop == "left" and ppr is not None and ppr.find(qn("w:ind")) is not None:
            value = ppr.find(qn("w:ind")).get(qn("w:left"))
        if value is not None:
            return value
        based = el.find(qn("w:basedOn"))
        el = next((s for s in root.findall(qn("w:style")) if based is not None
                   and s.get(qn("w:styleId")) == based.get(qn("w:val"))), None)
    return None


def _png(path: Path, width: int = 120, height: int = 40) -> Path:
    import cv2
    ok, data = cv2.imencode(".png", np.full((height, width), 128, np.uint8))
    path.write_bytes(data.tobytes())
    return path


def _word_template(folder: Path, name: str = "Company.docx", dotx: bool = False, numbered_headings: bool = False,
                   extra=None) -> Path:
    """A template made the way a company template usually is: Arial 11, Heading 1 18 pt, A4 landscape with 2 cm
    margins, a header with a marking, a logo and a link to the intranet, a footer with a page number and a field that
    fetches a picture from a web address, a link to an 'attached template' on a network share, an author, and some
    text of its own. Word writes only the styles a file uses, so Heading 3, Caption, List Paragraph and Table Grid
    are taken out."""
    import docx
    import zipfile
    from docx.enum.section import WD_ORIENT
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import parse_xml
    from docx.shared import Cm, Pt
    d = docx.Document()
    d.styles["Normal"].font.name = "Arial"
    d.styles["Normal"].font.size = Pt(11)
    d.styles["Heading 1"].font.size = Pt(18)
    for gone in ("Heading 3", "Caption", "List Paragraph", "Table Grid"):
        el = d.styles[gone].element
        el.getparent().remove(el)
    section = d.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Cm(29.7), Cm(21.0)
    section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Cm(2)
    header = section.header
    header.paragraphs[0].text = "UNCLASSIFIED"
    header.paragraphs[0].add_run().add_picture(str(_png(folder / "logo.png")))
    link_id = header.part.relate_to("http://intranet.example.com/policy", RT.HYPERLINK, is_external=True)
    header.paragraphs[0]._p.append(parse_xml(
        f'<w:hyperlink xmlns:w="{W_NS[1:-1]}" xmlns:r="{R_NS[1:-1]}" r:id="{link_id}"><w:r><w:t> intranet</w:t>'
        '</w:r></w:hyperlink>'))
    footer = section.footer.paragraphs[0]
    runs = [("t", "Page "), ("begin", ""), ("instr", " PAGE "), ("separate", ""), ("t", "1"), ("end", ""), ("t", "  "),
            ("begin", ""), ("instr", " INCL"), ("begin", ""), ("instr", " PAGE "), ("separate", ""), ("t", "1"),
            ("end", ""), ("instr", 'UDEPICTURE "http://198.51.100.9/beacon.png" '), ("separate", ""),
            ("t", "[logo placeholder]"), ("end", "")]
    for kind, text in runs:
        xml = {"t": f'<w:t xml:space="preserve">{text}</w:t>', "instr": f'<w:instrText xml:space="preserve">{text}</w:instrText>'
               }.get(kind, f'<w:fldChar w:fldCharType="{kind}"/>')
        footer._p.append(parse_xml(f'<w:r xmlns:w="{W_NS[1:-1]}">{xml}</w:r>'))
    settings_part = d.part._settings_part
    attached = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/attachedTemplate"
    template_id = settings_part.relate_to("file:///\\\\fileserver01\\templates\\Corporate.dotm", attached,
                                          is_external=True)
    settings_part.element.insert(2, parse_xml(f'<w:attachedTemplate xmlns:w="{W_NS[1:-1]}" xmlns:r="{R_NS[1:-1]}" '
                                              f'r:id="{template_id}"/>'))
    if numbered_headings:
        heading = d.styles["Heading 1"].element.get_or_add_pPr()
        heading.get_or_add_numPr().get_or_add_numId().val = 1
    d.add_paragraph("TEMPLATE BODY TEXT that must never reach a report.")
    d.core_properties.author = "Template Author"
    if extra:
        extra(d)
    path = folder / name
    d.save(path)
    if dotx:                                       # the same file as a Word template (.dotx)
        data = {}
        with zipfile.ZipFile(path) as z:
            for item in z.namelist():
                data[item] = z.read(item)
        data["[Content_Types].xml"] = data["[Content_Types].xml"].replace(
            b"wordprocessingml.document.main+xml", b"wordprocessingml.template.main+xml")
        path.unlink()
        path = path.with_suffix(".dotx")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for item, blob in data.items():
                z.writestr(item, blob)
    return path


def _package_text(path: Path) -> str:
    import zipfile
    with zipfile.ZipFile(path) as z:
        return "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith((".xml", ".rels")))


def test_the_word_report_has_the_tools_own_look_without_a_style_file_or_with_the_shipped_one():
    """Without a style file the report looks as it always did (Calibri 10, tables 8.5 pt with a shaded heading row,
    8 pt blue tags, Letter paper with 0.7/0.6 in margins); the shipped style file changes nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        d, path = _write_report(Path(tmp))
        assert (_style_value(d, "Normal", "font"), _style_value(d, "Normal", "size")) == ("Calibri", 10.0)
        assert _style_value(d, "Table Text", "size") == 8.5 and _style_value(d, "Table Heading", "bold") is True
        assert (_style_value(d, "Requirement Tag", "size"), _style_value(d, "Requirement Tag", "color"),
                _style_value(d, "Requirement Tag", "bold"), _style_value(d, "Requirement Tag", "italic")) == \
            (8.0, "1F4E9A", True, False)
        assert _style_value(d, "List Paragraph", "left") == "504"                     # 0.35 in
        assert (_style_value(d, "Caption", "italic"), _style_value(d, "Caption", "bold"),
                _style_value(d, "Caption", "align"), _style_value(d, "Caption", "size")) == (True, False, "center", 10.0)
        section = d.sections[0]
        assert (round(section.page_width.inches, 2), round(section.left_margin.inches, 2),
                round(section.top_margin.inches, 2)) == (8.5, 0.7, 0.6)
        heading_cell = d.tables[0].cell(0, 0)._tc
        assert heading_cell.find(f".//{W_NS}shd").get(f"{W_NS}fill") == "D9E2F3"
        shipped = se.Settings()                                    # the style file as it is shipped
        doc, items, _s = _report_sample()
        se.write_word_report(Path(tmp) / "shipped.docx", doc, items, shipped)
        import zipfile
        with zipfile.ZipFile(path) as a, zipfile.ZipFile(Path(tmp) / "shipped.docx") as b:
            assert a.read("word/styles.xml") == b.read("word/styles.xml")
            assert a.read("word/document.xml").count(b"<w:p>") + a.read("word/document.xml").count(b"<w:p ") == \
                b.read("word/document.xml").count(b"<w:p>") + b.read("word/document.xml").count(b"<w:p ")
        assert se.report_look(shipped).summary == "report_style.ini (nothing changed)"


def test_the_report_text_carries_no_formatting_of_its_own_so_a_template_decides_its_look():
    """Only the review marks (highlight, colour, bold of a likely misread) and a few labels are put on the words;
    sizes and fonts come from the styles, so a template or Word itself can change them."""
    with tempfile.TemporaryDirectory() as tmp:
        d, _path = _write_report(Path(tmp))
        for run in d.element.body.iter(f"{W_NS}r"):
            rpr = run.find(f"{W_NS}rPr")
            if rpr is None:
                continue
            own = {child.tag.replace(W_NS, "") for child in rpr}
            assert not own & {"sz", "szCs", "rFonts"}, own
            assert own <= {"rStyle", "highlight", "color", "b", "i"}, own


def test_the_shipped_style_file_lists_every_part_with_its_settings_and_the_tools_own_values():
    """report_style.ini names every part of the report, every setting in it is valid, every look value is empty
    (so a template decides), the switches hold the tool's own values, and the (bracketed) sizes match the code."""
    text = se.DEFAULT_WORD_STYLE_FILE.read_text(encoding="utf-8")
    values = se.read_style_file(se.DEFAULT_WORD_STYLE_FILE)
    assert set(values) <= set(se.BUILT_IN_SWITCHES), values
    assert all(se.BUILT_IN_SWITCHES[key] == value for key, value in values.items()), values
    sections = set(re.findall(r"^\[([^\]]+)\]", text, re.M))
    assert sections == set(se.OTHER_SECTIONS) | {p.section for p in se.REPORT_PARTS}, sections
    for part in se.REPORT_PARTS:
        block = re.split(r"^\[" + re.escape(part.section) + r"\]\s*$", text, flags=re.M)[1].split("\n[", 1)[0]
        assert part.kind == "table" or f"({part.style}:" in block, part.section
        size = dict(part.look).get("size")
        if isinstance(size, float):
            assert f"{size:g} pt" in block, (part.section, size)
    assert "(Calibri)" in text and "(Letter)" in text and "(0.6 in)" in text and "(0.7 in)" in text


def test_style_file_values_change_the_styles_not_the_text():
    """A size, colour, spacing or font from the style file goes into the style definition (so Word's Styles pane
    stays truthful), and a font replaces Word's theme fonts, which would otherwise win over it."""
    style = ("[document]\nfont = Arial\n[heading 1]\nsize = 20\ncolor = 00B050\n[table text]\nsize = 7\n"
             "[body]\nline_spacing = 1.5\nspace_after = 4\n[list items]\nindent_left = 1 cm\n"
             "[page]\npaper = A4\norientation = landscape\nmargin_left = 25 mm\n")
    with tempfile.TemporaryDirectory() as tmp:
        d, _path = _write_report(Path(tmp), style)
        assert (_style_value(d, "Heading 1", "size"), _style_value(d, "Heading 1", "color")) == (20.0, "00B050")
        assert _style_value(d, "Heading 1", "font") == "Arial" and _style_value(d, "Title", "font") == "Arial"
        assert _style_value(d, "Table Text", "size") == 7.0
        assert (_style_value(d, "Normal", "line"), _style_value(d, "Normal", "after")) == ("360", "80")
        assert _style_value(d, "List Paragraph", "left") == "567"
        section = d.sections[0]
        assert (round(section.page_width.mm), round(section.page_height.mm), round(section.left_margin.mm)) == \
            (297, 210, 25)
        assert not any(run.find(f"{W_NS}rPr/{W_NS}sz") is not None for run in d.element.body.iter(f"{W_NS}r"))


def test_a_template_gives_the_report_its_styles_page_headers_and_footers():
    """With a template the report has the template's fonts and sizes, page, header and footer (with its picture
    and page number), and the styles the template does not have are added to it; the template's text and its
    author never reach the report."""
    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp))
        d, path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        assert (_style_value(d, "Normal", "font"), _style_value(d, "Normal", "size")) == ("Arial", 11.0)
        assert _style_value(d, "Heading 1", "size") == 18.0
        assert _style_value(d, "Table Text", "font") == "Arial" and _style_value(d, "Table Text", "size") == 8.5
        assert se._find_style_element(d.styles.element, "Heading 3") is not None       # added: Word's own definition
        section = d.sections[0]
        assert (round(section.page_width.cm, 1), round(section.left_margin.cm, 1)) == (29.7, 2.0)
        assert section.header.paragraphs[0].text.startswith("UNCLASSIFIED")
        assert section.header.part.rels and any(r.reltype.endswith("/image") for r in section.header.part.rels.values())
        assert "Page 1" in section.footer.paragraphs[0].text
        package = _package_text(path)
        assert "TEMPLATE BODY TEXT" not in package and "Template Author" not in package
        assert d.core_properties.author == "" and d.core_properties.title == "Extraction Verification Report"
        heading_cell = d.tables[0].cell(0, 0)._tc                          # with a template its table style decides
        assert heading_cell.find(f".//{W_NS}shd") is None


def test_a_style_file_value_wins_over_the_template():
    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp))
        d, _path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n[heading 1]\nsize = 12\n"
                                            "[table header row]\nfill = D9D9D9\n")
        assert _style_value(d, "Heading 1", "size") == 12.0 and _style_value(d, "Normal", "size") == 11.0
        assert d.tables[0].cell(0, 0)._tc.find(f".//{W_NS}shd").get(f"{W_NS}fill") == "D9D9D9"


def test_nothing_in_a_template_that_points_outside_the_computer_reaches_the_report():
    """The attached template on a network share, the intranet link in the header and a field that fetches a picture
    from a web address (its name split over runs, with a page-number field inside it) are all left out: the link
    keeps its text, the field the text it showed, and the page number keeps working."""
    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp))
        look = se.read_word_template(template)
        notes = " | ".join(look.notes)
        assert "attached template" in notes and "fileserver01" in notes, notes
        assert "link(s) in the header became plain text" in notes and "INCLUDEPICTURE" in notes, notes
        d, path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        package = _package_text(path)
        for gone in ("fileserver01", "198.51.100.9", "intranet.example.com", "INCLUDEPICTURE", "attachedTemplate",
                     'TargetMode="External"'):
            assert gone not in package, gone
        footer = d.sections[0].footer.paragraphs[0]
        assert "[logo placeholder]" in footer.text and "intranet" in d.sections[0].header.paragraphs[0].text
        assert [se._field_name(c) for c in se._field_codes(footer._p)] == ["PAGE"]
        assert se.outside_references(path.read_bytes()) == []


def test_a_template_that_could_reach_outside_or_run_code_is_refused_with_what_to_do():
    import zipfile
    from docx.oxml import parse_xml
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    def refused(path: Path, *words) -> str:
        try:
            se.read_word_template(path)
        except se.ReportLookError as exc:
            assert all(w in str(exc) for w in words), (path.name, str(exc))
            return str(exc)
        raise AssertionError(f"{path.name} was accepted")

    def linked_logo(d):
        header = d.sections[0].header
        rid = header.part.relate_to("http://198.51.100.10/logo.png", RT.IMAGE, is_external=True)
        header.paragraphs[0]._p.append(parse_xml(
            f'<w:r xmlns:w="{W_NS[1:-1]}"><w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml" '
            f'style="width:20pt;height:10pt"><v:imagedata xmlns:r="{R_NS[1:-1]}" r:id="{rid}"/></v:shape>'
            '</w:pict></w:r>'))

    def embedded_object(d):
        d.sections[0].header.paragraphs[0]._p.append(parse_xml(
            f'<w:r xmlns:w="{W_NS[1:-1]}"><w:object/></w:r>'))

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        refused(_word_template(folder, "linked.docx", extra=linked_logo), "not stored in the template",
                "198.51.100.10", "Insert > Pictures > This Device")
        refused(_word_template(folder, "object.docx", extra=embedded_object), "embedded object")
        macro = _word_template(folder, "macro.docm")
        refused(macro, "macros", "Save As")
        hidden = folder / "hidden_macro.docx"                       # a macro project in a file named .docx
        with zipfile.ZipFile(macro) as z, zipfile.ZipFile(hidden, "w") as out:
            for item in z.namelist():
                blob = z.read(item)
                if item == "[Content_Types].xml":
                    blob = blob.replace(b"</Types>", b'<Default Extension="bin" ContentType="application/'
                                                     b'vnd.ms-office.vbaProject"/></Types>')
                out.writestr(item, blob)
            out.writestr("word/vbaProject.bin", b"\0" * 64)
        refused(hidden, "macros")
        activex = folder / "activex.docx"                           # ActiveX controls: Save As does not remove them
        with zipfile.ZipFile(macro) as z, zipfile.ZipFile(activex, "w") as out:
            for item in z.namelist():
                blob = z.read(item)
                if item == "[Content_Types].xml":
                    blob = blob.replace(b"</Types>", b'<Override PartName="/word/activeX/activeX1.xml" ContentType='
                                                     b'"application/vnd.ms-office.activeX+xml"/></Types>')
                out.writestr(item, blob)
            out.writestr("word/activeX/activeX1.xml", b"<ax/>")
        refused(activex, "ActiveX", "Design Mode")
        dtd = folder / "dtd.docx"
        with zipfile.ZipFile(_word_template(folder, "plain.docx")) as z, zipfile.ZipFile(dtd, "w") as out:
            for item in z.namelist():
                blob = z.read(item)
                if item == "word/styles.xml":
                    blob = blob.replace(b"?>", b'?><!DOCTYPE w:styles [<!ENTITY x SYSTEM "file:///etc/passwd">]>', 1)
                out.writestr(item, blob)
        refused(dtd, "document-type declaration")
        slip = folder / "slip.docx"
        with zipfile.ZipFile(folder / "plain.docx") as z, zipfile.ZipFile(slip, "w") as out:
            for item in z.namelist():
                out.writestr(item, z.read(item))
            out.writestr("../../outside.txt", b"x")
        refused(slip, "unsafe name")
        (folder / "protected.docx").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 512)
        refused(folder / "protected.docx", "password")
        (folder / "notword.dotx").write_bytes(b"not a zip")
        refused(folder / "notword.dotx", "not a Word")
        (folder / "old.dot").write_bytes(b"x")
        refused(folder / "old.dot", "Save As")


def test_a_dotx_template_gives_a_docx_report_that_word_opens():
    import zipfile
    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), dotx=True)
        assert template.suffix == ".dotx"
        d, path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        with zipfile.ZipFile(path) as z:
            assert b"wordprocessingml.document.main+xml" in z.read("[Content_Types].xml")
            assert b"template.main+xml" not in z.read("[Content_Types].xml")
        assert d.sections[0].header.paragraphs[0].text.startswith("UNCLASSIFIED")


def test_template_heading_numbering_is_switched_off_in_the_report():
    """A company heading style that numbers itself ("1.1") would print "1.1 3.2 Electrical requirements": the
    report's copy of the style has its numbering switched off."""
    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), numbered_headings=True)
        d, _path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        number = d.styles["Heading 1"].element.find(f"{W_NS}pPr/{W_NS}numPr/{W_NS}numId")
        assert number is not None and number.get(f"{W_NS}val") == "0"


def test_page_labels_are_in_the_page_header_and_the_page_holds_only_what_was_read():
    """Each scanned page starts a Word section of its own on a new page, labelled in that section's page header
    ("Page 1 of 1  -  text read by the tool"); no label, page break or blank paragraph is left in the text itself,
    and the document's own headings keep their levels (3.2 -> Heading 2)."""
    with tempfile.TemporaryDirectory() as tmp:
        d, _path = _write_report(Path(tmp))
        assert not any(p.text.startswith("Page 1") for p in d.paragraphs)
        labels = [p.text for p in d.sections[-1].header.paragraphs]
        assert labels == ["Page 1 of 1  -  text read by the tool"], labels
        assert d.sections[-1].header.paragraphs[0].style.name == "Page Label"
        assert not d.sections[-1].header.is_linked_to_previous and d.sections[-1].footer.is_linked_to_previous
        assert not d.element.body.findall(f".//{W_NS}br[@{W_NS}type='page']")
        assert next(p.style.name for p in d.paragraphs if p.text.startswith("3.2 Electrical")) == "Heading 2"
        breaks = [p for p in d.paragraphs if p._p.find(f"{W_NS}pPr/{W_NS}sectPr") is not None]
        assert breaks and all(p.text.strip() for p in breaks), [p.text for p in breaks]   # on a real paragraph


def test_page_images_fit_inside_the_page_a_template_sets():
    """The page image is sized from the report's real page (here A4 landscape with 2 cm margins and a header with a
    logo), not from US Letter."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        doc, items, s = _report_sample()
        _png(folder / "page1.png", 1870, 2420)
        doc.cache_dir, doc.pages[0].image_file = str(folder), "page1.png"
        template = _word_template(folder)
        d, _path = _write_report(folder, f"[document]\ntemplate = {template.name}\n", sample=(doc, items, s))
        section = d.sections[0]
        usable_w = section.page_width - section.left_margin - section.right_margin
        usable_h = section.page_height - section.top_margin - section.bottom_margin
        picture = d.inline_shapes[0]
        assert picture.width <= usable_w and picture.height <= usable_h, (picture.width, picture.height)
        d, _path = _write_report(folder, "[page]\npaper = A5\n", sample=(doc, items, s), name="a5.docx")
        section = d.sections[0]
        assert d.inline_shapes[0].height <= section.page_height - section.top_margin - section.bottom_margin


def test_requirement_tags_can_go_in_front_of_the_text():
    with tempfile.TemporaryDirectory() as tmp:
        d, _path = _write_report(Path(tmp), "[requirements]\ntag_position = start\n")
        requirement = next(p for p in d.paragraphs if "shall deliver 28 V" in p.text)
        assert re.match(r"\[R-\d{4}\]  The power supply", requirement.text), requirement.text
        before = d.paragraphs[[q._p for q in d.paragraphs].index(requirement._p) - 1]
        assert (before.text, before.style.name) == ("3.2.1 Output", "Heading 3")   # its run-in title, split off
        body = list(d.element.body)
        table = body.index(d.tables[0]._tbl)
        tag = body[table - 1]
        assert tag.tag == f"{W_NS}p" and "".join(t.text for t in tag.iter(f"{W_NS}t")).startswith("[T-"), table


def test_requirement_keywords_can_be_marked_and_keep_their_review_highlight():
    """mark_keywords = yes puts 'shall' in the Requirement Keyword style; a 'shall' the OCR was unsure of keeps its
    review highlight as well."""
    s = settings()
    doc, items, s = _report_sample(s)
    block = next(b for b in doc.blocks if "shall deliver" in b.text)
    for line in block.lines:
        for word in line.words:
            if word.text == "shall":
                word.conf = 0.2
    with tempfile.TemporaryDirectory() as tmp:
        d, _path = _write_report(Path(tmp), "[requirements]\nmark_keywords = yes\n", sample=(doc, items, s))
        keyword_id = d.styles["Requirement Keyword"].style_id
        marked = [r for r in d.element.body.iter(f"{W_NS}r")
                  if r.find(f"{W_NS}rPr/{W_NS}rStyle[@{W_NS}val='{keyword_id}']") is not None]
        texts = ["".join(t.text for t in r.iter(f"{W_NS}t")).strip() for r in marked]
        assert texts.count("shall") >= 2 and "shall" in texts, texts
        low = next(r for r in marked if "".join(t.text for t in r.iter(f"{W_NS}t")).strip() == "shall"
                   and r.find(f"{W_NS}rPr/{W_NS}highlight") is not None)
        assert low.find(f"{W_NS}rPr/{W_NS}highlight").get(f"{W_NS}val") == "yellow"
        assert _style_value(d, "Requirement Keyword", "bold") is True
        plain = next(p for p in d.paragraphs if "background of the design" in p.text)
        assert not any(r.style.name == "Requirement Keyword" for r in plain.runs)


def test_the_requirement_style_is_used_for_requirement_paragraphs_only():
    with tempfile.TemporaryDirectory() as tmp:
        d, _path = _write_report(Path(tmp), "[requirements]\nbold = yes\n")
        def style_of(text: str) -> str:
            return next(p.style.name for p in d.paragraphs if p.text.startswith(text))
        assert style_of("3.2.1 Output") == "Heading 3"                 # the run-in title is a heading of its own
        assert style_of("The power supply") == "Requirement Text"
        assert style_of("This paragraph explains") == "Normal"
        assert style_of("a. Search mode.") == "List Paragraph"
        assert _style_value(d, "Requirement Text", "bold") is True and _style_value(d, "Normal", "bold") in (None, False)


def test_table_heading_rows_repeat_on_each_page_and_cells_to_check_stay_shaded():
    with tempfile.TemporaryDirectory() as tmp:
        d, _path = _write_report(Path(tmp))
        rows = d.tables[0]._tbl.findall(f"{W_NS}tr")
        assert [r.find(f"{W_NS}trPr/{W_NS}tblHeader") is not None for r in rows] == [True, False, False]
        look = d.tables[0]._tbl.find(f"{W_NS}tblPr/{W_NS}tblLook")
        assert (look.get(f"{W_NS}firstRow"), look.get(f"{W_NS}firstColumn"), look.get(f"{W_NS}noHBand")) == ("1", "0", "1")
        assert d.tables[0].cell(2, 1)._tc.find(f".//{W_NS}shd").get(f"{W_NS}fill") == "FFF2CC"
        d, _path = _write_report(Path(tmp), "[table header row]\nrepeat_on_each_page = no\nfill = none\n"
                                            "[review marks]\ncell_fill = FFC7CE\n", name="b.docx")
        assert not d.tables[0]._tbl.findall(f".//{W_NS}tblHeader")
        assert d.tables[0].cell(0, 0)._tc.find(f".//{W_NS}shd") is None
        assert d.tables[0].cell(2, 1)._tc.find(f".//{W_NS}shd").get(f"{W_NS}fill") == "FFC7CE"


def _style_file_error(folder: Path, text, encoding: str = "utf-8") -> str:
    path = folder / "mistakes.ini"
    path.write_bytes(text if isinstance(text, bytes) else text.encode(encoding))
    try:
        se.read_style_file(path)
    except se.ReportLookError as exc:
        return str(exc)
    raise AssertionError("the mistakes were not reported")


def test_style_file_mistakes_are_all_reported_with_their_line_and_what_to_write():
    text = ("[body]\nline_spacing = 115%\n[table text]\nsise = 9\ncolor = navy blue\n[tabel header row]\nfill = D9E2F3\n"
            "[list items]\nindent_left = 1\n[requirement tag]\nspace_after = 6\n[heading 1]\nbold = maybe\n"
            "alignment = middle\n[page]\npaper = B5\n[tables]\nsize = 9\n")
    with tempfile.TemporaryDirectory() as tmp:
        message = _style_file_error(Path(tmp), text)
    for expected in ("has 10 mistakes", "Line 2: [body]  line_spacing = 115%", "single, 1.15, 1.5 or double",
                     "Line 4: [table text]  sise = 9", "Did you mean 'size'?", "'navy blue' is not a colour",
                     "Line 6: [tabel header row]", "Did you mean [table header row]?", "Line 9:", "needs a unit",
                     "changes words inside a line", "'maybe' should be yes or no", "left, center, right or justify",
                     "Letter, A4, Legal", "[tables] is the table itself"):
        assert expected in message, (expected, message)


def test_a_style_file_saved_by_notepad_is_read():
    """Notepad's byte-order mark and Windows line ends, an 'ANSI' (cp1252) file, a quoted file name, a % sign, a
    decimal comma, a section name in capitals and a setting written with a space are all read correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        path = folder / "notepad.ini"
        path.write_bytes(b"\xef\xbb\xbf; 100% of the look\r\n[Body]\r\nsize = 10,5\r\nline spacing = 1.15\r\n"
                         b'[document]\r\nfont = "Arial Narrow"\r\n[review marks]\r\ncheck_highlight = Bright Green\r\n')
        assert se.read_style_file(path) == {("body", "size"): 10.5, ("body", "line_spacing"): ("multiple", 1.15),
                                            ("document", "font"): "Arial Narrow",
                                            ("review marks", "check_highlight"): "bright green"}
        path.write_bytes("[document]\nfont = Fran\xe7ais Sans\n".encode("cp1252"))
        assert se.read_style_file(path) == {("document", "font"): "Fran\xe7ais Sans"}
        path.write_bytes("[body]\r\nsize = 11\r\n".encode("utf-16"))           # Notepad's "Unicode"
        assert se.read_style_file(path) == {("body", "size"): 11.0}
        path.write_text('[page]\npaper = A4; the paper we use\n[body]\nfont = Arial  # our font\n[document]\n'
                        'font = ""\n', encoding="utf-8")                    # comments straight after a value
        assert se.read_style_file(path) == {("page", "paper"): "a4", ("body", "font"): "Arial"}


def test_style_file_layout_mistakes_are_explained():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        assert "Start every setting at the left edge" in _style_file_error(folder, "[body]\nsize = 10\n  space_after = 6\n")
        assert "after a section name in square brackets" in _style_file_error(folder, "size = 10\n[body]\n")
        assert "set twice" in _style_file_error(folder, "[body]\nsize = 10\nsize = 11\n")
        assert "appears twice" in _style_file_error(folder, "[body]\nsize = 10\n[Body]\nspace_after = 6\n")
        assert "cannot be switched off" in _style_file_error(folder, "[review marks]\ncheck_highlight = none\n")
        assert "cannot be switched off" in _style_file_error(folder, "[review marks]\ncell_fill = none\n")
        assert "web or network address" in _style_file_error(folder, "[document]\ntemplate = https://example.com/t.dotx\n")
        assert "'Body Text' but give it a different size" in _style_file_error(
            folder, "[body]\nword_style = Body Text\nsize = 10\n[list items]\nword_style = Body Text\nsize = 9\n")
        message = _style_file_error(folder, "[body]\nsize = 11\nspace_after 6\n")
        assert "Line 3: space_after 6" in message and "not a setting: write name = value" in message, message
        assert "needs both brackets" in _style_file_error(folder, "[body\nsize = 11\n")
        message = _style_file_error(folder, "[body] ; ordinary text\nsize = ten\n[heading 1]\nsize = 12\n[Body]\n")
        assert "Line 2: [body]  size = ten" in message and "Line 5: [Body]" in message, message
        assert "1 to 200 points" in _style_file_error(folder, "[title]\nsize = 250\n")
        assert "cannot be read" in _style_file_error(folder, "[review marks]\nlikely_wrong_highlight = black\n"
                                                             "likely_wrong_color = black\n")
        s = se.Settings()                          # the same style named by its id ('Heading1' is 'Heading 1')
        s.word_style_file = folder / "ids.ini"
        s.word_style_file.write_text("[heading 1]\nsize = 14\n[heading 2]\nword_style = Heading1\nsize = 12\n",
                                     encoding="utf-8")
        try:
            se.report_look(s)
            raise AssertionError("two parts sharing a style by its id were accepted")
        except se.ReportLookError as exc:
            assert "both use the style 'Heading 1'" in str(exc) and "Line 5: [heading 2]  size" in str(exc), exc


def test_a_style_that_does_not_exist_or_is_of_the_wrong_kind_is_reported_before_any_page_is_read():
    import docx
    from docx.enum.style import WD_STYLE_TYPE

    def with_requirement_style(d):
        d.styles.add_style("Requirement Text Box", WD_STYLE_TYPE.PARAGRAPH)

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        template = _word_template(folder, extra=with_requirement_style)
        s = se.Settings()
        s.word_style_file = folder / "look.ini"
        s.word_style_file.write_text(f"[document]\ntemplate = {template.name}\n[requirements]\n"
                                     "word_style = Requirement Txt Box\n", encoding="utf-8")
        try:
            se.report_look(s)
            raise AssertionError("an unknown style was accepted")
        except se.ReportLookError as exc:
            assert "Line 4: [requirements]  word_style = Requirement Txt Box" in str(exc), exc
            assert "'Requirement Text Box'" in str(exc), exc
        s.word_style_file.write_text("[requirement tag]\nword_style = Heading 3\n", encoding="utf-8")
        try:
            se.report_look(s)
            raise AssertionError("a paragraph style was accepted for words inside a line")
        except se.ReportLookError as exc:
            assert "'Heading 3' is a paragraph style" in str(exc) and "character style" in str(exc), exc
        s.word_style_file.write_text("[body]\nword_style = body text\n[tables]\nword_style = light grid accent 1\n",
                                     encoding="utf-8")                           # (any case; Word's own styles)
        d, _path = _write_report(folder, s.word_style_file.read_text(encoding="utf-8"))
        assert any(p.style.name == "Body Text" for p in d.paragraphs)
        assert d.tables[0].style.name == "Light Grid Accent 1"


def test_the_template_is_looked_for_next_to_the_style_file():
    import os
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
        folder = Path(tmp) / "word_style"
        folder.mkdir()
        _word_template(folder, "Company.dotx", dotx=True)
        here = Path.cwd()
        try:
            os.chdir(elsewhere)
            s = se.Settings()
            s.word_style_file = folder / "report_style.ini"
            s.word_style_file.write_text("[document]\ntemplate = Company.dotx\n", encoding="utf-8")
            assert se.report_look(s).template.path == folder / "Company.dotx"
            s.word_style_file.write_text("[document]\ntemplate = Compnay.dotx\n", encoding="utf-8")
            try:
                se.report_look(s)
                raise AssertionError("a missing template was accepted")
            except se.ReportLookError as exc:
                assert "Line 2: [document]  template = Compnay.dotx" in str(exc) and "Company.dotx" in str(exc), exc
        finally:
            os.chdir(here)


def test_a_mistake_in_the_style_file_stops_the_run_before_any_page_is_read():
    """The run stops before any document is read, and the message is in the log file as well as on the screen."""
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.ini"
        bad.write_text("[body]\nsize = ten\n", encoding="utf-8")
        (Path(tmp) / "scan.pdf").write_bytes(b"%PDF-1.4 (never read)")
        reader = se.SpecExtractor.process_file

        def must_not_run(*_args, **_kwargs):
            raise AssertionError("a document was read although the style file is wrong")

        se.SpecExtractor.process_file = must_not_run
        import contextlib
        import io
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                assert se.main([str(Path(tmp) / "scan.pdf"), "--word-style", str(bad), "-o", tmp]) == 2
                assert se.main([str(Path(tmp) / "scan.pdf"), "--word-style", str(Path(tmp) / "missing.ini"),
                                "-o", tmp]) == 2
            assert "Line 2: [body]  size = ten" in printed.getvalue() and "does not exist" in printed.getvalue()
            log = (Path(tmp) / "spec_extractor_log.txt").read_text(encoding="utf-8")
            assert "Line 2: [body]  size = ten" in log and "does not exist" in log, log
        finally:
            se.SpecExtractor.process_file = reader
            for handler in logging.getLogger().handlers:
                handler.close()
            logging.getLogger().handlers.clear()
            logging.basicConfig(level=logging.ERROR)


def test_the_starter_template_has_every_report_style_and_works_as_a_template():
    """make_word_template.bat writes a .docx holding every style with a sample of each; it never overwrites a file,
    and used as the template it gives reports the same look."""
    import docx
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        look = se.report_look(se.Settings())
        first = se.write_starter_template(folder, look)
        second = se.write_starter_template(folder, look)
        assert (first.name, second.name) == ("report_template.docx", "report_template (2).docx")
        for target in (first, folder / "new.dotx"):
            try:
                se.write_starter_template(target, look)
                raise AssertionError(f"{target.name} was accepted")
            except se.ReportLookError:
                pass
        starter = docx.Document(first)
        names = {s.name for s in starter.styles}
        assert {p.style for p in se.REPORT_PARTS} <= names, {p.style for p in se.REPORT_PARTS} - names
        assert se.outside_references(first.read_bytes()) == []
        template = se.read_word_template(first)
        assert template.notes == ["its own text was left out (only its styles, page layout, headers and footers are "
                                  "used)"], template.notes
        built_in, _ = _write_report(folder, None, name="built_in.docx")
        restyled, _ = _write_report(folder, f"[document]\ntemplate = {first.name}\n", name="restyled.docx")
        for style in ("Normal", "Heading 1", "Table Text", "Table Heading", "Requirement Tag", "Caption", "List Paragraph"):
            for prop in ("size", "font", "bold", "italic", "color", "align", "left"):
                assert _style_value(built_in, style, prop) == _style_value(restyled, style, prop), (style, prop)


def test_the_starter_template_starts_from_the_template_in_the_style_file():
    import docx
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        template = _word_template(folder)
        s = se.Settings()
        s.word_style_file = folder / "look.ini"
        s.word_style_file.write_text(f"[document]\ntemplate = {template.name}\n", encoding="utf-8")
        starter = docx.Document(se.write_starter_template(folder, se.report_look(s)))
        assert starter.sections[0].header.paragraphs[0].text.startswith("UNCLASSIFIED")
        assert _style_value(starter, "Normal", "font") == "Arial"


def test_the_report_and_the_run_info_sheet_name_the_look_that_was_used():
    import openpyxl
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        template = _word_template(folder)
        doc, items, s = _report_sample()
        d, _path = _write_report(folder, f"[document]\ntemplate = {template.name}\n[heading 1]\nsize = 16\n",
                                 sample=(doc, items, s))
        summary = se.report_look(s).summary
        assert summary.startswith("template Company.docx (sha256 ") and summary.endswith("report.ini (1 value changed)"), summary
        assert any(f"Report look: {summary}" in p.text for p in d.paragraphs[:3])
        book = se.write_workbook(folder / "t.xlsx", [(doc, items)], s)
        info = {row[0].value: row[1].value for row in openpyxl.load_workbook(book)["Run Info"].iter_rows()}
        assert info["Word report look"] == summary, info


def test_a_report_that_would_point_outside_the_computer_is_never_saved():
    """The last check before saving: an outside link, a field that fetches something, or a linked picture anywhere in
    the file stops the save, whatever put it there."""
    import zipfile
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import parse_xml
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        d, styles = se._report_document(se.ReportLook())
        d.add_paragraph("clean")
        path = se._save_word_file(d, folder / "clean.docx")
        assert se.outside_references(path.read_bytes()) == []
        d.part.relate_to("http://example.com/x", RT.HYPERLINK, is_external=True)
        try:
            se._save_word_file(d, folder / "linked.docx")
            raise AssertionError("a report with an outside link was saved")
        except RuntimeError as exc:
            assert "points outside" in str(exc) and not (folder / "linked.docx").exists(), exc
        d, styles = se._report_document(se.ReportLook())
        d.add_paragraph()._p.append(parse_xml(f'<w:fldSimple xmlns:w="{W_NS[1:-1]}" w:instr=" INCLUDETEXT '
                                              f'&quot;\\\\\\\\server\\\\x.docx&quot; "/>'))
        problems = se.outside_references(_saved(d))
        assert any("INCLUDETEXT" in p for p in problems), problems
        with zipfile.ZipFile(path) as z, zipfile.ZipFile(folder / "vml.docx", "w") as out:
            for item in z.namelist():
                blob = z.read(item)
                if item == "word/document.xml":
                    blob = blob.replace(b"<w:t>clean</w:t>", b'<w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml">'
                                        b'<v:imagedata xmlns:o="urn:schemas-microsoft-com:office:office" '
                                        b'o:href="\\\\server\\share\\logo.png"/></v:shape></w:pict>')
                out.writestr(item, blob)
        problems = se.outside_references((folder / "vml.docx").read_bytes())
        assert any("linked to" in p for p in problems), problems


def _header_xml(d, inner: str) -> None:
    """Replace the template's default header with the given paragraph content (raw WordprocessingML)."""
    from docx.oxml import parse_xml
    header = d.sections[0].header
    header.is_linked_to_previous = False
    header.part._element = parse_xml(f'<w:hdr xmlns:w="{W_NS[1:-1]}" xmlns:r="{R_NS[1:-1]}" '
                                     f'xmlns:v="urn:schemas-microsoft-com:vml"><w:p>{inner}</w:p></w:hdr>')


def test_a_field_code_outside_any_field_never_reaches_the_report():
    """A field instruction with no field around it ('INCLUDEPICTURE http://...' in a plain run) does nothing in Word,
    but it is removed all the same, and the last check before saving would catch one."""
    def stray(d):
        _header_xml(d, '<w:r><w:instrText xml:space="preserve"> INCLUDEPICTURE "http://198.51.100.7/x.png" '
                       '</w:instrText></w:r><w:r><w:t>Company header</w:t></w:r>')
    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=stray)
        d, path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        assert "198.51.100.7" not in _package_text(path) and d.sections[0].header.paragraphs[0].text == "Company header"
        doc, _styles = se._report_document(se.ReportLook())
        doc.add_paragraph()._p.append(se._safe_xml(f'<w:r xmlns:w="{W_NS[1:-1]}"><w:instrText> DDEAUTO cmd '
                                                   '</w:instrText></w:r>'.encode(), "test"))
        assert any("DDEAUTO" in p for p in se.outside_references(_saved(doc)))


def test_tracked_changes_in_a_template_are_accepted_not_copied():
    """A marking changed from SECRET to UNCLASSIFIED with Track Changes on, and never accepted, must not put the
    struck-out SECRET (and the reviser's name) into every report; a page layout changed the same way gives the
    report the NEW layout, not the old one kept by the change."""
    def revised(d):
        _header_xml(d, '<w:del w:id="1" w:author="J. Smith" w:date="2026-01-05T10:00:00Z"><w:r><w:delText>SECRET'
                       '</w:delText></w:r></w:del><w:ins w:id="2" w:author="J. Smith" w:date="2026-01-05T10:00:00Z">'
                       '<w:r><w:t>UNCLASSIFIED</w:t></w:r></w:ins>')
        from docx.oxml import parse_xml
        sect = d.sections[0]._sectPr
        sect.append(parse_xml(f'<w:sectPrChange xmlns:w="{W_NS[1:-1]}" w:id="3" w:author="J. Smith"><w:sectPr>'
                              '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" '
                              'w:left="1417" w:header="709" w:footer="709" w:gutter="0"/></w:sectPr></w:sectPrChange>'))
    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=revised)
        notes = se.read_word_template(template).notes
        assert "tracked changes in the header were accepted" in notes and not any("sections" in n for n in notes), notes
        d, path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        package = _package_text(path)
        assert "SECRET" not in package and "J. Smith" not in package and "sectPrChange" not in package
        assert d.sections[0].header.paragraphs[0].text == "UNCLASSIFIED"
        assert round(d.sections[0].page_width.cm, 1) == 29.7                      # the current layout (landscape)


def test_styles_added_to_a_template_from_a_non_english_word_follow_its_own_normal_style():
    """German Word stores Normal under the id 'Standard'. The styles the report adds (List Paragraph, Caption ...)
    must be based on that style - not on a second, empty 'Normal' - and a style id the template already uses
    ('TableText') must not be used twice."""
    import docx
    from docx.enum.style import WD_STYLE_TYPE

    def german(d):
        root = d.styles.element
        renamed = {"Normal": "Standard", "DefaultParagraphFont": "Absatz-Standardschriftart",
                   "TableNormal": "NormaleTabelle"}
        for el in root.findall(f"{W_NS}style"):
            for tag in ("basedOn", "next", "link"):
                ref = el.find(f"{W_NS}{tag}")
                if ref is not None and ref.get(f"{W_NS}val") in renamed:
                    ref.set(f"{W_NS}val", renamed[ref.get(f"{W_NS}val")])
            if el.get(f"{W_NS}styleId") in renamed:
                el.set(f"{W_NS}styleId", renamed[el.get(f"{W_NS}styleId")])
        own = d.styles.add_style("TableText", WD_STYLE_TYPE.PARAGRAPH)      # a company style, id 'TableText'
        own.font.size = docx.shared.Pt(7)

    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=german)
        d, _path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n[table text]\nsize = 9\n")
        names = [s.name for s in d.styles]
        assert names.count("Normal") == 1 and names.count("Default Paragraph Font") == 1, names
        ids = [s.style_id for s in d.styles]
        assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
        for added in ("List Paragraph", "Caption"):
            assert _style_value(d, added, "font") == "Arial", added
        assert d.styles["Heading 3"].base_style.style_id == "Standard"         # (its font is the theme's)
        assert _style_value(d, "Table Text", "size") == 9.0
        cell_style = d.tables[0].cell(1, 0).paragraphs[0].style
        assert cell_style.name == "Table Text" and _style_value(d, "TableText", "size") == 7.0


def test_tags_and_keywords_keep_their_look_inside_italic_or_bold_paragraphs():
    """Bold and italic are 'toggles' in Word: a bold tag style inside a bold paragraph would print NOT bold, and the
    tag's 'not italic' could not undo an italic caption. The tags and keywords carry their style's bold and italic
    themselves."""
    with tempfile.TemporaryDirectory() as tmp:
        d, _path = _write_report(Path(tmp), "[requirements]\nbold = yes\nmark_keywords = yes\n")
        tag_id, keyword_id = d.styles["Requirement Tag"].style_id, d.styles["Requirement Keyword"].style_id
        for run in d.element.body.iter(f"{W_NS}r"):
            style = run.find(f"{W_NS}rPr/{W_NS}rStyle")
            if style is not None and style.get(f"{W_NS}val") in (tag_id, keyword_id):
                assert run.find(f"{W_NS}rPr/{W_NS}b") is not None, "".join(t.text for t in run.iter(f"{W_NS}t"))
                if style.get(f"{W_NS}val") == tag_id:
                    italic = run.find(f"{W_NS}rPr/{W_NS}i")
                    assert italic is not None and italic.get(f"{W_NS}val") in ("0", "false")


def test_an_empty_table_alignment_leaves_it_to_the_template_and_tables_fit_beside_a_gutter():
    from docx.oxml import parse_xml

    def left_tables_and_gutter(d):
        style = d.styles["Normal Table"].element
        style.find(f"{W_NS}tblPr").append(parse_xml(f'<w:jc xmlns:w="{W_NS[1:-1]}" w:val="left"/>'))
        d.sections[0].gutter = docx_cm(1)

    def docx_cm(n):
        from docx.shared import Cm
        return Cm(n)

    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=left_tables_and_gutter)
        d, _path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        assert d.tables[0]._tbl.find(f"{W_NS}tblPr/{W_NS}jc") is None
        section = d.sections[0]
        text_width = section.page_width - section.left_margin - section.right_margin - section.gutter
        grid = sum(int(c.get(f"{W_NS}w")) for c in d.tables[0]._tbl.find(f"{W_NS}tblGrid"))
        assert grid * 635 <= text_width + 635 * len(d.tables[0].columns), (grid * 635, text_width)
        d, _path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n[tables]\nalignment = right\n",
                                 name="right.docx")
        assert d.tables[0]._tbl.find(f"{W_NS}tblPr/{W_NS}jc").get(f"{W_NS}val") == "right"


def test_margins_too_wide_for_the_paper_stop_the_run_at_start_up():
    with tempfile.TemporaryDirectory() as tmp:
        s = se.Settings()
        s.word_style_file = Path(tmp) / "wide.ini"
        s.word_style_file.write_text("[page]\npaper = A5\nmargin_left = 3 in\nmargin_right = 3 in\n", encoding="utf-8")
        try:
            se.report_look(s)
            raise AssertionError("margins wider than the paper were accepted")
        except se.ReportLookError as exc:
            assert "margins are too wide" in str(exc) and "Line 3: [page]  margin_left" in str(exc), exc


def test_the_look_checked_at_start_up_is_used_for_the_whole_run():
    """Editing the style file while a batch runs must not make the remaining reports fail: main() keeps the look it
    checked at start-up in Settings.word_look."""
    with tempfile.TemporaryDirectory() as tmp:
        s = se.Settings()
        s.word_style_file = Path(tmp) / "look.ini"
        s.word_style_file.write_text("[heading 1]\nsize = 16\n", encoding="utf-8")
        s.word_look = se.report_look(s)
        s.word_style_file.write_text("[heading 1]\nsize = sixteen\n", encoding="utf-8")
        assert se.report_look(s) is s.word_look
        doc, items, _s = _report_sample()
        import docx
        d = docx.Document(se.write_word_report(Path(tmp) / "r.docx", doc, items, s))
        assert _style_value(d, "Heading 1", "size") == 16.0


def test_page_images_fit_under_the_page_label_and_tall_header_pictures():
    """The page image fits the text area of its page, under the page label in the page header, and a tall logo in
    the header - DrawingML or the older VML, in the default or the even-page header - takes room from it."""
    def vml_logo(d):
        _header_xml(d, '<w:r><w:pict><v:shape style="width:144pt;height:144pt"><v:imagedata/></v:shape></w:pict></w:r>')

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        plain, _ = se._report_document(se.ReportLook())
        width, height = se._usable_page(plain)
        assert (round(width, 2), round(height, 2)) == (7.1, 9.8)
        template = _word_template(folder, extra=vml_logo)
        look = se.ReportLook(template=se.read_word_template(template))
        d, _styles = se._report_document(look)
        section = d.sections[0]
        text_height = (section.page_height - section.top_margin - section.bottom_margin) / 914400
        assert se._usable_page(d)[1] <= text_height - 1.5, (se._usable_page(d), text_height)
        doc, items, s = _report_sample()
        _png(folder / "page1.png", 1870, 2420)
        doc.cache_dir, doc.pages[0].image_file = str(folder), "page1.png"
        d, _path = _write_report(folder, None, sample=(doc, items, s))
        usable = se._usable_page(d, d.sections[1])[1]                 # the page holding the scan, with its label
        assert usable < 9.8 and d.inline_shapes[0].height <= int(usable * 914400) + 9144, usable
        assert [p.text for p in d.sections[1].header.paragraphs] == ["Page 1 of 1  -  scanned page"]


def test_the_starter_template_keeps_the_heading_row_shading_when_used_as_the_template():
    import docx
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        starter = se.write_starter_template(folder, se.report_look(se.Settings()))
        grid = docx.Document(starter).styles["Table Grid"].element
        first_row = [el for el in grid.findall(f"{W_NS}tblStylePr") if el.get(f"{W_NS}type") == "firstRow"]
        assert first_row and first_row[0].find(f".//{W_NS}shd").get(f"{W_NS}fill") == "D9E2F3"
        d, _path = _write_report(folder, f"[document]\ntemplate = {starter.name}\n")
        look = d.tables[0]._tbl.find(f"{W_NS}tblPr/{W_NS}tblLook")
        assert look.get(f"{W_NS}firstRow") == "1" and d.styles["Table Grid"].element.find(f"{W_NS}tblStylePr") is not None


def test_a_damaged_template_gives_a_message_not_a_crash():
    from docx.oxml import parse_xml

    def odd_columns(d):
        d.sections[0]._sectPr.append(parse_xml(f'<w:cols xmlns:w="{W_NS[1:-1]}" w:num="two"/>'))

    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=odd_columns)
        assert any("columns were left out" in n for n in se.read_word_template(template).notes)
        import zipfile
        broken = Path(tmp) / "broken.docx"
        with zipfile.ZipFile(template) as z, zipfile.ZipFile(broken, "w") as out:
            for item in z.namelist():
                blob = z.read(item)
                if item == "word/_rels/document.xml.rels":
                    blob = blob.replace(b'Target="styles.xml"', b'Target="missing.xml"')
                out.writestr(item, blob)
        se.read_word_template(broken)                                    # (no styles: Word's standard ones)


def test_a_template_header_with_a_table_or_a_text_box_is_not_taken_for_a_tall_one():
    """A header laid out as a table (logo | title | marking) or holding a floating text box takes the room of its
    rows, not of every paragraph in it; the start-up check judges the margins only, and a damaged picture size in
    a header is ignored rather than stopping the run."""
    from docx.oxml import parse_xml
    cell = "<w:tc><w:p><w:r><w:t>x</w:t></w:r></w:p><w:p><w:r><w:t>y</w:t></w:r></w:p></w:tc>"
    rows = "".join(f"<w:tr>{cell * 4}</w:tr>" for _ in range(3))
    box = ('<w:r><w:drawing><wp:anchor xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
           + "".join("<w:p><w:r><w:t>side</w:t></w:r></w:p>" for _ in range(20)) + "</wp:anchor></w:drawing></w:r>")

    def busy_header(d):
        header = d.sections[0].header
        header.is_linked_to_previous = False
        header.part._element = parse_xml(
            f'<w:hdr xmlns:w="{W_NS[1:-1]}" xmlns:v="urn:schemas-microsoft-com:vml"><w:tbl>{rows}</w:tbl>'
            f'<w:p>{box}<w:r><w:pict><v:rect style="width:10pt;height:1.2.3pt"/></w:pict></w:r></w:p></w:hdr>')

    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=busy_header)
        look = se.ReportLook(template=se.read_word_template(template))
        d, _styles = se._report_document(look)
        height = se._story_height(d.sections[0].header._element)
        assert 3 * 2 * 228600 <= height <= 3 * 2 * 228600 + 228600, height / 914400     # 3 rows of 2 lines + 1 line
        d, _path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        assert d.paragraphs                                                       # (accepted, no crash)


def test_damaged_or_hostile_bits_of_a_template_are_cleaned_without_breaking_the_rest():
    """A stray field code sharing a run with a page number's field mark goes and the page number stays; a deleted
    field code (delInstrText) left outside its deletion goes; a deleted paragraph and a deleted table row go, as
    with Word's Accept All Changes; and a SECTION field is frozen like other fields."""
    def header(d):
        _header_xml(d, '<w:r><w:instrText>junk</w:instrText><w:fldChar w:fldCharType="begin"/></w:r>'
                       '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
                       '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
                       '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
                       '<w:r><w:delInstrText> INCLUDEPICTURE "http://198.51.100.8/x.png" </w:delInstrText></w:r>'
                       '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> SECTION </w:instrText></w:r>'
                       '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t> part 2</w:t></w:r>'
                       '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
                       '<w:p><w:pPr><w:rPr><w:del w:id="1" w:author="A"/></w:rPr></w:pPr><w:del w:id="2" w:author="A">'
                       '<w:r><w:delText>SECRET</w:delText></w:r></w:del></w:p>'
                       '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Doc 123</w:t></w:r></w:p></w:tc></w:tr>'
                       '<w:tr><w:trPr><w:del w:id="3" w:author="A"/></w:trPr><w:tc><w:p><w:r><w:t>NOFORN</w:t></w:r>'
                       '</w:p></w:tc></w:tr></w:tbl><w:p>')
    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=header)
        d, path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        story = d.sections[0].header._element
        assert [se._field_name(c) for c in se._field_codes(story)] == ["PAGE"], se._field_codes(story)
        assert d.sections[0].header.paragraphs[0].text == "1 part 2"
        package = _package_text(path)
        for gone in ("198.51.100.8", "SECRET", "NOFORN", "delInstrText", "junk"):
            assert gone not in package, gone
        assert len(d.sections[0].header.paragraphs) == 2 and len(d.sections[0].header.tables[0].rows) == 1
        doc, _styles = se._report_document(se.ReportLook())
        doc.add_paragraph()._p.append(se._safe_xml(f'<w:r xmlns:w="{W_NS[1:-1]}"><w:delInstrText> LINK x '
                                                   '</w:delInstrText></w:r>'.encode(), "test"))
        assert any("LINK" in p for p in se.outside_references(_saved(doc)))


def test_a_template_whose_normal_style_is_not_marked_as_the_default_still_has_one_normal():
    def not_default(d):
        d.styles["Normal"].element.attrib.pop(f"{W_NS}default", None)

    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=not_default)
        d, _path = _write_report(Path(tmp), f"[document]\ntemplate = {template.name}\n")
        names = [s.name for s in d.styles]
        assert names.count("Normal") == 1, names
        assert _style_value(d, "Caption", "font") == "Arial" and _style_value(d, "List Paragraph", "font") == "Arial"


def test_tables_are_centred_by_the_table_style_and_the_starter_keeps_it_with_its_shading():
    """The tool's own centring goes into the table style (Table Grid), like its heading-row shading in the starter
    template, so a template that lacks Table Grid gets centred tables and a report made from the unchanged starter
    looks like the starter; a centring or shading set in the style file is put on the table itself."""
    import docx
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        d, _path = _write_report(folder)
        assert d.tables[0]._tbl.find(f"{W_NS}tblPr/{W_NS}jc") is None
        assert d.styles["Table Grid"].element.find(f"{W_NS}tblPr/{W_NS}jc").get(f"{W_NS}val") == "center"
        template = _word_template(folder)                                  # (it has no Table Grid of its own)
        d, _path = _write_report(folder, f"[document]\ntemplate = {template.name}\n", name="t.docx")
        assert d.styles["Table Grid"].element.find(f"{W_NS}tblPr/{W_NS}jc").get(f"{W_NS}val") == "center"
        s = se.Settings()
        s.word_style_file = folder / "fill.ini"
        s.word_style_file.write_text("[table header row]\nfill = FFFF00\n", encoding="utf-8")
        starter = docx.Document(se.write_starter_template(folder, se.report_look(s)))
        assert starter.tables[0].cell(0, 0)._tc.find(f".//{W_NS}shd").get(f"{W_NS}fill") == "FFFF00"
        sample = next(p for p in starter.paragraphs if "Output voltage" in p.text)
        assert all(r.bold is None and r.italic is None for r in sample.runs)        # (styles only, for restyling)


def test_word_on_off_settings_written_as_off_are_off():
    from docx.oxml import parse_xml

    def gutter_off(d):
        from docx.shared import Cm
        d.sections[0].gutter = Cm(2)
        d.settings.element.append(parse_xml(f'<w:gutterAtTop xmlns:w="{W_NS[1:-1]}" w:val="0"/>'))

    with tempfile.TemporaryDirectory() as tmp:
        template = _word_template(Path(tmp), extra=gutter_off)
        d, _styles = se._report_document(se.ReportLook(template=se.read_word_template(template)))
        width, _height = se._usable_page(d)
        section = d.sections[0]
        assert abs(width - (section.page_width - section.left_margin - section.right_margin - section.gutter)
                   / 914400) < 0.01


def test_a_dark_highlight_for_misread_words_gets_white_text_and_a_damaged_style_file_a_message():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        path = folder / "dark.ini"
        path.write_text("[review marks]\nlikely_wrong_highlight = blue\nlikely_wrong_color = C00000\n", encoding="utf-8")
        assert se.likely_wrong_colour(se.read_style_file(path)) == "FFFFFF"
        path.write_bytes(b"\xff\xfe" + "[body]\r\nsize = 11\r\n".encode("utf-16-le") + b"\x00")
        assert "is damaged" in _style_file_error(folder, path.read_bytes())
        message = _style_file_error(folder, "[document]\ntemplate ..\\new templates\\report.dotx\n")
        assert "Line 2: template ..\\new templates\\report.dotx" in message, message


def _saved(d) -> bytes:
    import io
    buffer = io.BytesIO()
    d.save(buffer)
    return buffer.getvalue()


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
def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    if "--list" in args:
        for name, fn in tests:
            first = " ".join((fn.__doc__ or "").split()).split(". ")[0]
            print(f"{name}\n      {first}" if first else name)
        return 0
    words = [a.lower() for a in args if not a.startswith("-")]
    if words:
        tests = [(name, fn) for name, fn in tests if any(w in name.lower() for w in words)]
        if not tests:
            print(f"no test name contains {' or '.join(words)!r} (python tests/test_rules.py --list shows them all)")
            return 2
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
