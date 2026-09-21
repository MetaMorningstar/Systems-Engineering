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
    """Replace img2table's Image class so detect_tables() receives exactly this cell grid."""
    import img2table.document as i2t_document

    def box(x1, y1, x2, y2):
        return types.SimpleNamespace(x1=x1, y1=y1, x2=x2, y2=y2)

    table = types.SimpleNamespace(content={r: [types.SimpleNamespace(bbox=box(*c)) for c in cells] for r, cells in rows.items()},
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
