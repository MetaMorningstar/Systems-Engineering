"""
Tables and lists: a borderless table under a lead-in must stay a table (one Table item, its rows not made into
list items), and a list of labels on tab stops must stay a list, even with a table caption or a sentence about a
table right under it. Requirement tables ('Requirement' column) give one requirement row per cell.
"""
from casekit import Case, items, para

AREA = "Tables and lists"

_NO_LIST = "Ends with ':' but no list items"


def _p08_table(pg):
    """The borderless table of the earlier list suite's page p08, drawn exactly as it was."""
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


def _req_table(header: bool, colon: bool) -> str:
    """Paragraph 3.2, the caption 'TABLE I. Characteristics', a borderless Parameter / Requirement / Method table
    (with or without its header row, labels with or without colons), then 3.3."""
    c = ":" if colon else ""
    rows = [("Input voltage", ["The unit shall operate from 22 to", "29 VDC."], "Test"),
            ("Power", ["The unit shall draw less than 150 W."], "Test"),
            ("Weight", ["The unit shall weigh less than 5 kg."], "Inspection"),
            ("Cooling", ["The unit shall be cooled by forced", "air at 20 C inlet."], "Analysis")]
    out = ["3.2 Characteristics. The unit shall meet the requirements of Table I.", "@gap 0.5",
           " " * 21 + "TABLE I. Characteristics", "@gap 0.5"]
    if header:
        out += ["Parameter".ljust(21) + "Requirement".ljust(39) + "Method", "@gap 0.5"]
    for label, req, method in rows:
        out.append((label + c).ljust(21) + req[0].ljust(39) + method)
        out += [" " * 21 + t for t in req[1:]]
        out.append("@gap 0.5")
    return "\n".join(out + ["@gap 0.5", "3.3 Marking. Each unit shall carry a nameplate."])


_REQ_TABLE_ROWS = para("3.2 | The unit shall meet the requirements of Table I.",
                       " | The unit shall operate from 22 to 29 VDC.", " | The unit shall draw less than 150 W.",
                       " | The unit shall weigh less than 5 kg.", " | The unit shall be cooled by forced air at 20 C inlet.",
                       "3.3 | Each unit shall carry a nameplate.")
_LEAD = ["3.2.1 Interface. The interface shall have the following properties:"]
_LEAD_WRAPPED = ["3.2.1 Interface. The interface shall have the following", "characteristics:"]
_LEAD_ROW = para(f"3.2.1 | The interface shall have the following properties: [note: {_NO_LIST}]")
_AFTER = "3.2.5 Weight. The equipment shall not exceed 45 kilograms."
_AFTER_ROW = para("3.2.5 | The equipment shall not exceed 45 kilograms.")
_CHAR_ROWS = [("Voltage:", "28 VDC nominal", "Test"), ("Current:", "5 A maximum", "Test"),
              ("Impedance:", "50 ohm", "Analysis"), ("Isolation:", "100 Mohm at 500 VDC", "Test")]


def _grid(lead: list, rows: list, cols: tuple, header: tuple = None, caption: str = "", below: str = "",
          after: str = _AFTER) -> str:
    """A lead-in, then a borderless grid whose cells start at the given character columns (a caption above or
    below it), then the next paragraph - the layout of the round-2 table pages."""
    def line(cells):
        s = ""
        for x, t in zip(cols, cells):
            if t:
                s = s.ljust(x) + t
        return s
    out = list(lead) + ["@gap 0.7"]
    if caption:
        out += [" " * 20 + caption, "@gap 0.5"]
    if header:
        out += [line(header), "@gap 0.5"]
    for row in rows:
        out += [line(row), "@gap 0.3"]
    if below:
        out += ["@gap 0.3", " " * 20 + below, "@gap 0.5"]
    return "\n".join(out + ["@gap 0.7", after])


_DOCS = [("MIL-STD-461G", "Requirements for the Control of Electromagnetic"), ("", "Interference Characteristics"),
         ("MIL-STD-704F", "Aircraft Electric Power Characteristics"),
         ("MIL-STD-810H", "Environmental Engineering Considerations"),
         ("MIL-STD-1275E", "Characteristics of 28 Volt DC Input Power"),
         ("MIL-STD-1553B", "Digital Time Division Command/Response Bus")]
_DOCS_LEAD = ["2.1 Documents. The following documents form a part of this", "specification:"]
_PRECEDENCE = "2.2 Order of precedence. The text of this specification shall govern."
_PRECEDENCE_ROW = para("2.2 | The text of this specification shall govern.")

_LABELS = """
3.2.6 Input power. The unit shall meet the following:
@gap 0.4
       Input voltage:       22 to 29 VDC.
@gap 0.4
       Ripple:              1 V peak to peak maximum.
@gap 0.4
       Power:               150 W maximum.
@gap 0.4
       Transients:          as in MIL-STD-704F.
@gap 0.4
       Hold-up:             50 ms after loss of input.
"""
_LABEL_ROWS = items("The unit shall meet the following:", "3.2.6 | Input voltage: 22 to 29 VDC.",
                    "3.2.6 | Ripple: 1 V peak to peak maximum.", "3.2.6 | Power: 150 W maximum.",
                    "3.2.6 | Transients: as in MIL-STD-704F.", "3.2.6 | Hold-up: 50 ms after loss of input.")
_PIN_TABLE = """
@gap 1.4
                 TABLE II. Connector J1 pin assignments.
@gap 0.5
@box 0.5 5.5 4
@rule 0.5 5.5 1
@vrule 2.0 4
@gap 0.2
        Pin             Signal
        A               +28 VDC
        B               Return
        C               Chassis
"""

CASES = [
    Case("TBL-01", "A borderless table with real columns (control)",
         "Paragraph 3.8.3, the caption 'TABLE I. Serial interface characteristics.', a three-column table with no "
         "rulings (Parameter / Value / Unit and six rows, columns 1.4 to 2 inches apart), then 3.8.4.",
         "Two paragraph rows and ONE Table item: the table's rows are not list items or requirements.",
         "List suite p08 (control).",
         draw=_p08_table, tables=1, table_has=("Flow control",), captions=("TABLE I",),
         expect=para("3.8.3 | The serial interface shall have the characteristics listed in TABLE I.",
                     "3.8.4 | The serial interface connector shall be a 9-pin D-subminiature connector.")),
    Case("TBL-02", "A requirement table with a header row and labels with colons",
         "'3.2 ... the requirements of Table I.', the caption 'TABLE I. Characteristics', then a borderless table "
         "with the header 'Parameter / Requirement / Method' and four rows ('Input voltage:', 'Power:' ...) whose "
         "Requirement cells are sentences, some over two lines; then 3.3.",
         "One Table item with its caption, and one requirement row per Requirement cell (their Doc Ref is empty: "
         "the table has no ID column). The labels are not a list.",
         "Review round 1 (layout, requirement tables); real OCR page tbl_hdr_colon.",
         text=_req_table(header=True, colon=True), tables=1, table_has=("Inspection",), captions=("TABLE I",),
         expect=_REQ_TABLE_ROWS),
    Case("TBL-03", "A requirement table with a header row and labels without colons",
         "TBL-02 with the labels' colons left out.",
         "As TBL-02.",
         "Review round 1 (layout); real OCR page tbl_hdr_nocolon.",
         text=_req_table(header=True, colon=False), tables=1, table_has=("Inspection",), captions=("TABLE I",),
         expect=_REQ_TABLE_ROWS),
    Case("TBL-04", "A requirement table without a header row, labels with colons",
         "TBL-02 without its header row.",
         "As TBL-02: the table is recognised from its columns and caption even without a header.",
         "Review round 1 (layout); real OCR page tbl_nohdr_colon.",
         text=_req_table(header=False, colon=True), tables=1, table_has=("Inspection",), captions=("TABLE I",),
         expect=_REQ_TABLE_ROWS),
    Case("TBL-05", "A requirement table without a header row, labels without colons",
         "TBL-02 without its header row and without the labels' colons.",
         "As TBL-02.",
         "Review round 1 (layout); real OCR page tbl_nohdr_nocolon.",
         text=_req_table(header=False, colon=False), tables=1, table_has=("Inspection",), captions=("TABLE I",),
         expect=_REQ_TABLE_ROWS),
    Case("TBL-06", "A three-column table with a header under a lead-in",
         "'3.2.1 ... shall have the following properties:' then a borderless table 'Characteristic / "
         "Requirement / Method' with four rows ('Voltage:  28 VDC nominal  Test'), then 3.2.5.",
         "A Table item, not four list rows (round 2: the colons made the first column look like list labels); "
         "the Requirement cells give one requirement row each; the lead-in says no list items were found.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_colon_hdr.",
         text=_grid(_LEAD, _CHAR_ROWS, (3, 24, 55), header=("Characteristic", "Requirement", "Method")),
         tables=1, table_has=("Impedance:", "Analysis"),
         expect=_LEAD_ROW + para(" | 28 VDC nominal", " | 5 A maximum", " | 50 ohm", " | 100 Mohm at 500 VDC")
         + _AFTER_ROW),
    Case("TBL-07", "A three-column table without a header under a lead-in",
         "TBL-06 without its header row.",
         "A Table item, not four list rows (no Requirement column, so no requirement rows from it).",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_colon_nohdr.",
         text=_grid(_LEAD, _CHAR_ROWS, (3, 24, 55)), tables=1, table_has=("Impedance:", "Analysis"),
         expect=_LEAD_ROW + _AFTER_ROW),
    Case("TBL-08", "A three-column table with a header, labels without colons",
         "TBL-06 with the labels' colons left out.",
         "As TBL-06.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_plain_hdr.",
         text=_grid(_LEAD, [(a.rstrip(":"), b, c) for a, b, c in _CHAR_ROWS], (3, 24, 55),
                    header=("Characteristic", "Requirement", "Method")),
         tables=1, table_has=("Impedance", "Analysis"),
         expect=_LEAD_ROW + para(" | 28 VDC nominal", " | 5 A maximum", " | 50 ohm", " | 100 Mohm at 500 VDC")
         + _AFTER_ROW),
    Case("TBL-09", "A three-column table without a header, labels without colons",
         "TBL-07 with the labels' colons left out.",
         "As TBL-07.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_plain_nohdr.",
         text=_grid(_LEAD, [(a.rstrip(":"), b, c) for a, b, c in _CHAR_ROWS], (3, 24, 55)),
         tables=1, table_has=("Impedance", "Analysis"), expect=_LEAD_ROW + _AFTER_ROW),
    Case("TBL-10", "A table of documents under a lead-in",
         "'2.1 Documents. The following documents form a part of this specification:' then document numbers and "
         "titles in two columns (one title over two lines), then 2.2.",
         "One Table item; the documents are not list items; 2.2 keeps its number.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_docs.",
         text=_grid(_DOCS_LEAD, _DOCS, (3, 22), after=_PRECEDENCE), tables=1, table_has=("MIL-STD-810H",),
         expect=_PRECEDENCE_ROW),
    Case("TBL-11", "A table of documents with a header row",
         "TBL-10 with the header row 'Document / Title'.",
         "As TBL-10.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_docs_hdr.",
         text=_grid(_DOCS_LEAD, _DOCS, (3, 22), header=("Document", "Title"), after=_PRECEDENCE), tables=1,
         table_has=("MIL-STD-810H",), expect=_PRECEDENCE_ROW),
    Case("TBL-12", "Labels with a requirement sentence each, under a lead-in",
         "'3.2.1 ... the following properties:' then two columns: 'Voltage:' / 'The unit shall operate from 28 "
         "VDC.', 'Current:' / 'The unit shall draw less than 5 A.', and so on.",
         "A list: one row per label, with the lead-in in front ('... properties: Voltage: The unit shall "
         "operate from 28 VDC.'), not a table.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_reqs_2col.",
         text=_grid(_LEAD, [("Voltage:", "The unit shall operate from 28 VDC."),
                            ("Current:", "The unit shall draw less than 5 A."),
                            ("Weight:", "The unit shall weigh less than 5 kg."),
                            ("Cooling:", "The unit shall be cooled by forced air.")], (3, 24)),
         expect=items("The interface shall have the following properties:",
                      "3.2.1 | Voltage: The unit shall operate from 28 VDC.",
                      "3.2.1 | Current: The unit shall draw less than 5 A.",
                      "3.2.1 | Weight: The unit shall weigh less than 5 kg.",
                      "3.2.1 | Cooling: The unit shall be cooled by forced air.") + _AFTER_ROW),
    Case("TBL-13", "A table whose first column holds long labels",
         "'3.2.1 ... the following properties:' then 'Maximum steady state input current:  5 A  Test' and "
         "three more rows with labels of five to six words.",
         "A Table item, not a list.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_longlabel.",
         text=_grid(_LEAD, [("Maximum steady state input current:", "5 A", "Test"),
                            ("Minimum insulation resistance at 500 VDC:", "100 Mohm", "Test"),
                            ("Maximum inrush current at turn on:", "20 A", "Test"),
                            ("Maximum ripple voltage on the bus:", "1 V", "Analysis")], (3, 48, 60)),
         tables=1, table_has=("Maximum inrush current",), expect=_LEAD_ROW + _AFTER_ROW),
    Case("TBL-14", "A table under a lead-in with its caption BELOW it",
         "TBL-07's table with the caption 'TABLE I. Interface characteristics.' under it, then 3.2.5.",
         "A Table item linked to its caption; not a list.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_colon_caption_below.",
         text=_grid(_LEAD, _CHAR_ROWS, (3, 24, 55), below="TABLE I. Interface characteristics."), tables=1,
         table_has=("Impedance:",), captions=("TABLE I",), expect=_LEAD_ROW + _AFTER_ROW),
    Case("TBL-15", "A table whose labels are abbreviations with full stops ('Min.', 'Nom.', 'Max.')",
         "'3.2.3 ... within the following limits:' then 'Min.  22.0 VDC  Test', 'Nom.  28.0 VDC  Test', 'Max.  29.0 "
         "VDC  Test'.",
         "A Table item, not a list.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_minmax; known limitation.",
         text=_grid(["3.2.3 Input voltage. The input voltage shall be within the", "following limits:"],
                    [("Min.", "22.0 VDC", "Test"), ("Nom.", "28.0 VDC", "Test"), ("Max.", "29.0 VDC", "Test")],
                    (3, 24, 55)),
         tables=1, table_has=("29.0 VDC",),
         expect=para(f"3.2.3 | The input voltage shall be within the following limits: [note: {_NO_LIST}]")
         + _AFTER_ROW,
         known="The rows are taken as the lead-in's list, with the labels and the rest of each row apart: six rows "
               "('... following limits: Min.', 'Nom.', 'Max.', then '22.0 VDC Test' ...), and no Table item."),
    Case("TBL-16", "A table whose labels are abbreviations ('Temp.', 'Alt.', 'Vib.', 'Hum.')",
         "'3.2.1 ... the following properties:' then 'Temp.  -40 C to +71 C  Test' and three more such rows.",
         "A Table item, not a list.",
         "Review round 2 (tab-list attack on tables); real OCR page tbl_abbrev; known limitation.",
         text=_grid(_LEAD, [("Temp.", "-40 C to +71 C", "Test"), ("Alt.", "15,000 m", "Test"),
                            ("Vib.", "7.7 g rms", "Test"), ("Hum.", "95 percent", "Analysis")], (3, 24, 55)),
         tables=1, table_has=("15,000 m",), expect=_LEAD_ROW + _AFTER_ROW,
         known="The rows are taken as the lead-in's list: four rows such as '... properties: Temp. -40 C to "
               "+71 C Test', and no Table item."),
    Case("TBL-17", "Requirement IDs with a colon on a tab stop ('SRS-101:')",
         "'3.2 Performance. The radar shall meet the following requirements:' then 'SRS-101:' at the margin and "
         "its requirement on a tab stop (two lines), 'SRS-102:' and 'SRS-103:' likewise; then 3.3.",
         "Each requirement is a row whose Doc Ref is its own ID (SRS-101, SRS-102, SRS-103) - the ID is not a list "
         "label (round 3: 'SRS-101:' was accepted as a label and the table was lost).",
         "Review round 3 (idcolon); real OCR page idcolon_mono.",
         text="""
3.2 Performance. The radar shall meet the following requirements:
@gap 0.5
SRS-101:      The radar shall detect a 1 square meter target at
              a range of not less than 150 km.

SRS-102:      The radar shall track 200 targets.

SRS-103:      The radar shall operate from 115 VAC.

3.3 Cooling. The radar shall be cooled by forced air.
""",
         tables=1, table_has=("SRS-102",),
         expect=para(f"3.2 | The radar shall meet the following requirements: [note: {_NO_LIST}]",
                     "SRS-101 | The radar shall detect a 1 square meter target at a range of not less than 150 km.",
                     "SRS-102 | The radar shall track 200 targets.", "SRS-103 | The radar shall operate from 115 VAC.",
                     "3.3 | The radar shall be cooled by forced air."),
         known="The IDs are read as the first column of a table, and the requirement rows taken from it have an "
               "empty Doc Ref instead of SRS-101, SRS-102 and SRS-103."),
    Case("TBL-18", "A list of labels, then the next table's caption and a ruled table",
         "'3.2.6 ... shall meet the following:' with five labels on tab stops (no markers), one blank line, the "
         "caption 'TABLE II. Connector J1 pin assignments.' and a ruled table Pin / Signal.",
         "The labels stay a list (five rows with the lead-in), and TABLE II is a Table item with its caption "
         "(round 3: the caption below the labels turned the list into a borderless table).",
         "Review round 3, finding F1; real OCR page cap_list_mono.",
         text=_LABELS + _PIN_TABLE, tables=1, table_has=("Chassis",), captions=("TABLE II",), expect=_LABEL_ROWS),
    Case("TBL-19", "A list of labels, then the next table's caption and a ruled table, proportional font",
         "TBL-18 in a proportional (serif) font.",
         "As TBL-18.",
         "Review round 3, finding F1; real OCR page cap_list_serif.",
         text=_LABELS + _PIN_TABLE, font="serif", tables=1, table_has=("Chassis",), captions=("TABLE II",),
         expect=_LABEL_ROWS),
    Case("TBL-20", "A list of labels, then a sentence that starts 'Table 4 ...'",
         "The five labels of TBL-18, a blank line, then 'Table 4 gives the limits that apply in each mode of "
         "operation.'",
         "The labels stay a list; the sentence is not a caption (round 3: 'Table 4 gives ...' was taken as a caption "
         "and the list became a table).",
         "Review round 3, finding F1; real OCR page table_ref_after_list_mono.",
         text=_LABELS + "@gap 1.4\nTable 4 gives the limits that apply in each mode of operation.\n",
         expect=_LABEL_ROWS),
    Case("TBL-21", "A lead-in whose short last line sits right above a table's header",
         "TBL-06 with its lead-in wrapped: the second line 'characteristics:' is short and sits straight above the "
         "table's header row 'Characteristic  Requirement  Method'.",
         "The lead-in keeps its last line ('... have the following characteristics:'), and the table is one Table "
         "item that starts at its header row.",
         "Written for the case library (a variant of TBL-06).",
         text=_grid(_LEAD_WRAPPED, _CHAR_ROWS, (3, 24, 55), header=("Characteristic", "Requirement", "Method")),
         tables=1, table_has=("Impedance:", "Analysis"),
         expect=para(f"3.2.1 | The interface shall have the following characteristics: [note: {_NO_LIST}]",
                     " | 28 VDC nominal", " | 5 A maximum", " | 50 ohm", " | 100 Mohm at 500 VDC") + _AFTER_ROW,
         known="The lead-in's short last line is taken into the table as the start of its header row, so the "
               "lead-in's row stops at '... have the following' (and is flagged as possibly incomplete)."),
]
