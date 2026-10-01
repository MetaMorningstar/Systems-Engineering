"""
Two-column pages: each column must be read on its own, top to bottom, and a narrow column of prose or a short
list beside it must not be taken for the wide tab stops of a list (or the other way round). Several pages are
set in a 10 pt typewriter face, as two-column typed pages usually are.
"""
from casekit import Case, items, para, tab_text

AREA = "Two-column pages"

_LIST7 = ["a. MIL-STD-461G", "b. MIL-STD-704F", "c. MIL-STD-810H", "d. MIL-STD-1275E", "e. MIL-STD-1553B",
          "f. MIL-STD-883L", "g. MIL-STD-1472H"]
_TEXT_ROWS = para(" | The unit shall operate from the 28 VDC aircraft bus and shall draw no more than 150 W in any mode "
                  "of operation.",
                  " | The unit shall start within two seconds of the application of power and shall not reset when the "
                  "bus voltage drops to 18 VDC for up to 50 ms.",
                  " | The unit shall be cooled by the aircraft environmental control system and shall not require any "
                  "liquid coolant during ground running.")


def _two_columns(left: list, right: list, x_right: int, x_left: int = 0) -> str:
    """Page text of two columns side by side: the left column's lines at column x_left, the right column's at
    column x_right (None = a blank line in that column)."""
    out = ["@mark top"]
    out += [(" " * x_left + t) if t else "" for t in left]
    out += ["@goto top"]
    out += [(" " * x_right + t) if t else "" for t in right]
    return "\n".join(out)


def _p09(pg):
    """The two-column page of the earlier list suite, drawn exactly as it was."""
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


_DOCS_LEFT = ["2.1 Government documents. The", "following documents form a part", "of this specification:",
              "a. MIL-STD-461G", "b. MIL-STD-704F", "c. MIL-STD-810H", "d. MIL-STD-1275E", "e. MIL-STD-1553B",
              "f. MIL-STD-883L", "g. MIL-HDBK-217F", "h. MIL-PRF-38534", "i. MIL-DTL-38999", "j. MIL-C-17"]
_DOCS_RIGHT = ["3.1 Power. The unit shall operate", "from the 28 VDC aircraft bus", "defined in MIL-STD-704F and shall",
               "draw no more than 150 W in any", "operating mode, including warm-up.", None,
               "3.2 Cooling. The unit shall be", "cooled by forced air from the", "aircraft ECS and shall not require",
               "any liquid coolant during ground", "running or flight at any altitude.", None,
               "3.3 Mass. The unit shall weigh", "less than 5 kg including its tray."]
_DOCS_ROWS = para("3.1 | The unit shall operate from the 28 VDC aircraft bus defined in MIL-STD-704F and shall draw no "
                  "more than 150 W in any operating mode, including warm-up.",
                  "3.2 | The unit shall be cooled by forced air from the aircraft ECS and shall not require any liquid "
                  "coolant during ground running or flight at any altitude.",
                  "3.3 | The unit shall weigh less than 5 kg including its tray.")
_COLMAJOR = """
3.2.7 Documents. The unit shall comply with each of the following:
@gap 0.5
    a. MIL-STD-461G                    d. MIL-STD-1275E
    b. MIL-STD-704F                    e. MIL-STD-1553B
    c. MIL-STD-810H                    f. MIL-STD-883L
@gap 1
3.2.8 Weight. The unit shall not exceed 45 kilograms.
"""
_COLMAJOR_ROWS = items("The unit shall comply with each of the following:", "3.2.7 a | a. MIL-STD-461G",
                       "3.2.7 b | b. MIL-STD-704F", "3.2.7 c | c. MIL-STD-810H", "3.2.7 d | d. MIL-STD-1275E",
                       "3.2.7 e | e. MIL-STD-1553B", "3.2.7 f | f. MIL-STD-883L") \
    + para("3.2.8 | The unit shall not exceed 45 kilograms.")

CASES = [
    Case("COL-01", "Two columns of prose with a tight list in the left column (control)",
         "Proportional font, 200 dpi. '3.9 Construction.' across the page, then a left column 3.9.1 to 3.9.3 (with "
         "the list a. to c. under 3.9.2) and a right column 3.9.4 to 3.9.6, 0.4 inch apart.",
         "Eight rows in column order: the whole left column, then the right column. Nothing from the right column "
         "is joined to the left.",
         "List suite p09 (control).",
         draw=_p09, font="serif", pt=12, dpi=200,
         expect=para("3.9.1 | Materials shall be free of defects which would adversely affect the performance or "
                     "maintainability of the equipment.")
         + items("Each unit shall be marked with the following information:", "3.9.2 a | a. Part number.",
                 "3.9.2 b | b. Serial number.", "3.9.2 c | c. Manufacturer's CAGE code.")
         + para("3.9.3 | The equipment shall be fabricated and finished so that it is free of burrs, sharp edges and "
                "loose parts.",
                "3.9.4 | All parts having the same part number shall be directly and completely interchangeable with "
                "each other.",
                "3.9.5 | External surfaces shall be painted in accordance with the approved finish specification for "
                "the equipment.",
                "3.9.6 | Threaded fasteners shall be secured against loosening by an approved locking method.")),
    Case("COL-02", "A list of documents in the left column, prose in the right",
         "10 pt typewriter. Left column: '2.1 Government documents. The following documents form a part of this "
         "specification:' and ten documents a. to j.; right column: paragraphs 3.1 to 3.3.",
         "The right column's paragraphs are whole and in order; nothing from the list is mixed into them (round 1: "
         "the gutter was taken for the tab stops of a list and the columns were read across).",
         "Review round 1 (layout, list-heavy two-column pages); real OCR page twocol_docs_mono.",
         text=_two_columns(_DOCS_LEFT, _DOCS_RIGHT, 42), pt=10, pitch=0.17, expect=_DOCS_ROWS),
    Case("COL-03", "A list of documents in the left column, prose in the right, proportional font",
         "COL-02 in an 11 pt proportional (serif) font.",
         "As COL-02.",
         "Review round 1 (layout); real OCR page twocol_docs_serif.",
         text=_two_columns(_DOCS_LEFT, _DOCS_RIGHT, 37), font="serif", pitch=0.18, expect=_DOCS_ROWS),
    Case("COL-04", "A lead-in and short labelled items in the left column, prose in the right",
         "10 pt typewriter. Left: '3.4 Modes. The radar shall provide the following operating modes:' and seven "
         "items 'a. Search:' to 'g. Off:'; right: paragraphs 3.5 and 3.6.",
         "Seven list rows under 3.4, then 3.5 and 3.6 whole.",
         "Review round 1 (layout); real OCR page twocol_modes_mono.",
         text=_two_columns(["3.4 Modes. The radar shall provide", "the following operating modes:", "a. Search:",
                            "b. Track:", "c. Map:", "d. Standby:", "e. Test:", "f. Maintenance:", "g. Off:"],
                           ["3.5 Power. The unit shall operate", "from the 28 VDC aircraft bus",
                            "defined in MIL-STD-704F and shall", "draw no more than 150 W in any",
                            "operating mode, including warm-up.", None, "3.6 Cooling. The unit shall be",
                            "cooled by forced air from the", "aircraft ECS."], 42),
         pt=10, pitch=0.17,
         expect=items("The radar shall provide the following operating modes:", "3.4 a | a. Search:", "3.4 b | b. Track:",
                      "3.4 c | c. Map:", "3.4 d | d. Standby:", "3.4 e | e. Test:", "3.4 f | f. Maintenance:",
                      "3.4 g | g. Off:")
         + para("3.5 | The unit shall operate from the 28 VDC aircraft bus defined in MIL-STD-704F and shall draw no "
                "more than 150 W in any operating mode, including warm-up.",
                "3.6 | The unit shall be cooled by forced air from the aircraft ECS.")),
    Case("COL-05", "A list set in two columns (a-c left, d-f right)",
         "A page-wide lead-in, then the items a. to c. in a left column and d. to f. in a right column, then 3.2.8.",
         "The six items in order a to f (column by column), each with the lead-in; 3.2.8 after them.",
         "Review round 2 (layout, column-major list); real OCR page colmajor_mono.",
         text=_COLMAJOR, expect=_COLMAJOR_ROWS),
    Case("COL-06", "A list set in two columns, proportional font",
         "COL-05 in a proportional (serif) font.",
         "As COL-05.",
         "Review round 2 (layout); real OCR page colmajor_serif.",
         text=_COLMAJOR, font="serif", expect=_COLMAJOR_ROWS),
    Case("COL-07", "A short list beside a narrow column of prose",
         "10 pt typewriter. Left: a list of seven documents (no lead-in); right: a column of prose 29 characters "
         "wide.",
         "The three sentences of the prose, whole; the list is not read across into them (round 3: the narrow "
         "prose looked like the value column of a list).",
         "Review round 3, finding F2; real OCR page twocol_narrow_mono.",
         text=_two_columns(_LIST7, ["The unit shall operate from", "the 28 VDC aircraft bus and",
                                    "shall draw no more than 150 W", "in any mode of operation. The",
                                    "unit shall start within two", "seconds of the application of",
                                    "power and shall not reset", "when the bus voltage drops to",
                                    "18 VDC for up to 50 ms. The", "unit shall be cooled by the",
                                    "aircraft environmental", "control system and shall not",
                                    "require any liquid coolant", "during ground running."], 40, x_left=3),
         pt=10, expect=_TEXT_ROWS),
    Case("COL-08", "A short list beside a ragged column of typed prose",
         "As COL-07, but the prose is typed with a ragged right edge (lines of 27 to 35 characters).",
         "As COL-07 (round 3: lines that stopped short were taken as finished rows of a list).",
         "Review round 3, finding F3; real OCR page twocol_ragged_mono.",
         text=_two_columns(_LIST7, ["The unit shall operate from", "the 28 VDC aircraft bus and shall",
                                    "draw no more than 150 W in", "any mode of operation. The unit",
                                    "shall start within two seconds of", "the application of power and",
                                    "shall not reset when the", "bus voltage drops to 18 VDC for up",
                                    "to 50 ms. The unit shall be", "cooled by the aircraft",
                                    "environmental control system", "and shall not require any",
                                    "liquid coolant during ground", "running."], 36, x_left=3),
         pt=10, expect=_TEXT_ROWS),
    Case("COL-09", "Two lists side by side",
         "10 pt typewriter. Left: five documents a. to e.; right: 'a. The radar shall search.' to 'e. The radar "
         "shall answer.'",
         "The right list's five requirements, each on its own row with its own marker; the left list is not mixed "
         "in (round 3: the two lists were read across).",
         "Review round 3, finding F5; real OCR page twocol_two_lists_mono.",
         text=_two_columns(_LIST7[:5], ["a. The radar shall search.", "b. The radar shall track.",
                                        "c. The radar shall map.", "d. The radar shall show weather.",
                                        "e. The radar shall answer."], 40, x_left=3),
         pt=10,
         expect=para("a. | The radar shall search.", "b. | The radar shall track.", "c. | The radar shall map.",
                     "d. | The radar shall show weather.", "e. | The radar shall answer.")),
    Case("COL-10", "A list beside prose that has a small list of its own",
         "10 pt typewriter. Left: seven documents; right: '3.4 Modes. The radar shall have the following operating "
         "modes:' with 'a. search mode,' to 'd. weather mode.' and a closing sentence.",
         "The right column's list under 3.4 (a to d) and its closing sentence; the left list is not mixed in.",
         "Review round 3 (layout); real OCR page twocol_sublist_mono.",
         text=_two_columns(_LIST7, ["3.4 Modes. The radar shall have", "the following operating modes:",
                                    "a. search mode,", "b. track while scan mode,", "c. ground mapping mode, and",
                                    "d. weather mode.", "The radar shall switch between",
                                    "modes in less than one second."], 36, x_left=3),
         pt=10,
         expect=items("The radar shall have the following operating modes:", "3.4 a | a. search mode,",
                      "3.4 b | b. track while scan mode,", "3.4 c | c. ground mapping mode, and",
                      "3.4 d | d. weather mode.")
         + para(" | The radar shall switch between modes in less than one second.")),
    Case("COL-11", "A short right column beside a list and prose",
         "10 pt typewriter. Left: five documents, a blank line, then six lines of prose; right: only six lines of "
         "prose, level with the list, ending mid-sentence.",
         "Left column first (three sentences), then the right column; the right column's unfinished last sentence "
         "is flagged for review.",
         "Review round 3 (layout); real OCR page twocol_short_right_mono.",
         text=_two_columns(_LIST7[:5] + [None, "The contractor shall supply each", "of the documents listed above to",
                                          "the procuring activity on request.", "Copies shall be legible and shall",
                                          "include every revision issued.", "The contractor shall keep a log."],
                           ["The unit shall operate from", "the 28 VDC aircraft bus and",
                            "shall draw no more than 150 W", "in any mode of operation. The",
                            "unit shall start within two", "seconds of the application of"], 40),
         pt=10,
         expect=para(" | The contractor shall supply each of the documents listed above to the procuring activity on "
                     "request.", " | Copies shall be legible and shall include every revision issued.",
                     " | The contractor shall keep a log.",
                     " | The unit shall operate from the 28 VDC aircraft bus and shall draw no more than 150 W in any "
                     "mode of operation.",
                     " | The unit shall start within two seconds of the application of [note: no final punctuation]")),
    Case("COL-12", "A short list beside prose with one numbered paragraph",
         "10 pt typewriter. Left: seven documents; right: '3.4 Cooling. The unit shall be ...' - one numbered "
         "paragraph whose lines often start with capitals ('MIL-STD-810H', 'Method 507.6', 'Result').",
         "The paragraph's four sentences, all under 3.4, in order (round 3: a single titled paragraph made the "
         "right column look like the second column of a table).",
         "Review round 3, finding F4; real OCR page twocol_one_titled_mono.",
         text=_two_columns(_LIST7, ["3.4 Cooling. The unit shall be", "cooled by forced air. MIL-STD-810H",
                                    "Method 507.6 humidity shall not", "degrade cooling. The unit shall",
                                    "MIL-STD-704F transients shall not", "Result in any loss of cooling.",
                                    "The inlet air shall be at 25 C."], 36, x_left=3),
         pt=10,
         expect=para("3.4 | The unit shall be cooled by forced air.",
                     "3.4 | MIL-STD-810H Method 507.6 humidity shall not degrade cooling.",
                     "3.4 | The unit shall MIL-STD-704F transients shall not Result in any loss of cooling.",
                     "3.4 | The inlet air shall be at 25 C.")),
    Case("COL-13", "A list on tab stops straight above a two-column section",
         "10 pt typewriter. A lead-in and a list a. to d. whose values sit on a tab stop at 3.3 inches, then, one "
         "blank line below, two columns of prose whose right column starts at the same 3.3 inches.",
         "The list's four items with their values, then 3.3 to 3.6 in column order.",
         "Review round 3, finding B1; known limitation.",
         text=tab_text(["3.2.4 Environmental conditions. The equipment shall meet each of the", "following:"],
                       [("a.", "Acceleration:", ["5 g in each of the three axes."]),
                        ("b.", "Vibration:", ["20 Hz to 2000 Hz random."]),
                        ("c.", "Shock:", ["40 g, 11 ms half-sine pulse."]),
                        ("d.", "Temperature:", ["-40 C to +71 C operating."])],
                       ["@gap 1.4", "@mark top", "3.3 Power. The unit shall operate", "from the 28 VDC aircraft bus and",
                        "shall draw no more than 150 W in", "any mode of operation or test.",
                        "3.4 Mass. The unit shall weigh", "less than 5 kg with its tray.", "@goto top"]
                       + [" " * 40 + t for t in ["3.5 Cooling. The unit shall be", "cooled by forced air from the",
                                                 "aircraft ECS and shall not need", "any liquid coolant during ground",
                                                 "running. 3.6 Finish. The unit", "shall be painted gray."]],
                       marker=4, label=10, value=40, between="@gap 0.4"),
         pt=10,
         expect=items("The equipment shall meet each of the following:",
                      "3.2.4 a | a. Acceleration: 5 g in each of the three axes.",
                      "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random.",
                      "3.2.4 c | c. Shock: 40 g, 11 ms half-sine pulse.",
                      "3.2.4 d | d. Temperature: -40 C to +71 C operating.")
         + para("3.3 | The unit shall operate from the 28 VDC aircraft bus and shall draw no more than 150 W in any mode "
                "of operation or test.", "3.4 | The unit shall weigh less than 5 kg with its tray.",
                "3.5 | The unit shall be cooled by forced air from the aircraft ECS and shall not need any liquid "
                "coolant during ground running.", "3.6 | The unit shall be painted gray."),
         known="The two-column section's gutter lines up with the list's value tab stop, so the page is cut into "
               "two columns from the top: the values leave their items (the rows keep only 'a. Acceleration:') "
               "and come out as a separate Table item."),
]
