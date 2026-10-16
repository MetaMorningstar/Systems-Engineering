"""
Sections, titles and document lists: every numbered paragraph is a section at the level its number gives it, whatever
its indent or the space around it; a title printed underlined ends where the underline ends, also when the text
follows on the same line; a table needs a heading row printed as one, or a title, and is otherwise a list; the
documents listed in section 2 are read with their number, title and referencing paragraphs; misreads that can be
undone with confidence are corrected, and the correction is listed.
"""
from casekit import Case, items, para

AREA = "Sections, titles and document lists"

_DOCS_490 = """
2.  APPLICABLE DOCUMENTS

2.1  <u>Government documents.</u>  The following documents form a part
of this specification to the extent specified herein.

SPECIFICATIONS

      <u>Military</u>

MIL-E-5400T    Electronic Equipment, Aerospace,      3.2.1, 3.4.5
               General Specification for
MIL-C-5015G    Connectors, Electrical, Circular      3.3.2

STANDARDS

      <u>Military</u>

MIL-STD-461G   Requirements for the Control of EMI   3.2.5
MIL-STD-810H   Environmental Engineering             3.2.6

3.  REQUIREMENTS

3.1  <u>General.</u>  The radar shall meet the requirements of this
section.
"""
_DOCS_490_LIST = ("MIL-E-5400T | Electronic Equipment, Aerospace, General Specification for | 3.2.1, 3.4.5",
                  "MIL-C-5015G | Connectors, Electrical, Circular | 3.3.2",
                  "MIL-STD-461G | Requirements for the Control of EMI | 3.2.5",
                  "MIL-STD-810H | Environmental Engineering | 3.2.6")

CASES = [
    Case("STR-01", "A tab-indented subsection with an underlined title and its text on the same line",
         "'3.2 Electrical requirements.' then, indented by a tab, '3.2.1  Power input  The equipment shall operate "
         "...' with 'Power input' underlined and no full stop after it, and '3.2.2  Power consumption  ...' the same.",
         "Each subsection is a section of its own at level 3 under 3.2 - its underlined words are its title, the "
         "rest its text: the Title column says 'Power input' and the text starts 'The equipment ...'. In the Word "
         "documents the title is a Heading 3 and the text a paragraph under it. (The page starts inside section 3, so "
         "the Document Structure sheet first has '3 [heading not found in the scan]', as the DOORS file does.)",
         "User request (1.5.0): a subsection indented by a tab, its underlined title and body on one line.",
         text="""
3.2  Electrical requirements.  The equipment shall meet the
requirements of this section.

      3.2.1  <u>Power input</u>  The equipment shall operate from
      115 V ac, 400 Hz, single phase.

      3.2.2  <u>Power consumption</u>  The equipment shall draw no
      more than 500 W.
""",
         expect=para("3.2 | The equipment shall meet the requirements of this section. [title: Electrical requirements]",
                     "3.2.1 | The equipment shall operate from 115 V ac, 400 Hz, single phase. [title: Power input]",
                     "3.2.2 | The equipment shall draw no more than 500 W. [title: Power consumption]"),
         outline=("1 | 3 [heading not found in the scan]", "2 | 3.2 Electrical requirements", "3 | 3.2.1 Power input",
                  "3 | 3.2.2 Power consumption")),
    Case("STR-02", "An underlined run-in title with a full stop, proportional font",
         "STR-01 printed in a proportional (serif) font, the underlined titles ending in a full stop "
         "('Power input.').",
         "As STR-01: the full stop belongs to the title, not to the text.",
         "User request (1.5.0); a variant of STR-01.",
         text="""
3.2  Electrical requirements.  The equipment shall meet the
requirements of this section.

      3.2.1  <u>Power input.</u>  The equipment shall operate from
      115 V ac, 400 Hz, single phase.

      3.2.2  <u>Power consumption.</u>  The equipment shall draw no
      more than 500 W.
""", font="serif",
         expect=para("3.2 | The equipment shall meet the requirements of this section. [title: Electrical requirements]",
                     "3.2.1 | The equipment shall operate from 115 V ac, 400 Hz, single phase. [title: Power input]",
                     "3.2.2 | The equipment shall draw no more than 500 W. [title: Power consumption]"),
         outline=("1 | 3 [heading not found in the scan]", "2 | 3.2 Electrical requirements", "3 | 3.2.1 Power input",
                  "3 | 3.2.2 Power consumption")),
    Case("STR-03", "An underlined title on a line of its own, without a number",
         "'3.4 Environmental conditions' (underlined), a paragraph, then 'Temperature' underlined on a line of its "
         "own and a paragraph under it.",
         "Both underlined lines are titles, not text: 3.4 is a level-2 section; 'Temperature' has no number, so it is "
         "a sub-title inside 3.4 and leaves the numbered levels alone (it is not a heading in the outline). Section 3 "
         "itself is not on the page: its row says '3 [heading not found in the scan]'.",
         "User request (1.5.0): underlined text is a section title.",
         text="""
3.4  <u>Environmental conditions</u>

The equipment shall operate in the environments of this section.

<u>Temperature</u>

The equipment shall operate from -40 C to +71 C.
""",
         expect=para(" | The equipment shall operate in the environments of this section. "
                     "[section: 3.4 Environmental conditions]",
                     " | The equipment shall operate from -40 C to +71 C. [section: Temperature]"),
         outline=("1 | 3 [heading not found in the scan]", "2 | 3.4 Environmental conditions",)),
    Case("STR-04", "Numbered paragraphs nest by their numbers, not by their indent or spacing",
         "3 REQUIREMENTS, then 3.1, 3.1.1, 3.1.1.1, 3.1.1.2 and 3.2 printed at different indents, some with a blank "
         "line before them and some without.",
         "Each paragraph is a section at the level its number gives it: 3.1.1.1 and 3.1.1.2 under 3.1.1, 3.2 back at "
         "level 2 - the indent and the spacing do not change that.",
         "User request (1.5.0): numbered text nests under the number before it.",
         text="""
3.  REQUIREMENTS

    3.1  General.  The system shall meet the requirements of this
    section.
3.1.1  Performance.  The system shall detect a target at 150 km.
              3.1.1.1  The system shall track 200 targets.

3.1.1.2  The system shall operate continuously.
        3.2  Interfaces.  The system shall provide two data buses.
""",
         expect=para("3.1 | The system shall meet the requirements of this section.",
                     "3.1.1 | The system shall detect a target at 150 km.",
                     "3.1.1.1 | The system shall track 200 targets.",
                     "3.1.1.2 | The system shall operate continuously.",
                     "3.2 | The system shall provide two data buses."),
         outline=("1 | 3 REQUIREMENTS", "2 | 3.1 General", "3 | 3.1.1 Performance", "4 | 3.1.1.1", "4 | 3.1.1.2",
                  "2 | 3.2 Interfaces")),
    Case("STR-05", "A list of documents under a title and a tab-indented sub-title (MIL-STD-490 layout)",
         "Section 2: 'SPECIFICATIONS', a blank line, 'Military' indented by a tab and underlined, then lines of a "
         "document number, its title (one title wraps onto a second line) and the paragraphs that call it up; the "
         "same again under 'STANDARDS'.",
         "Each line is one document with its number, title and referencing paragraphs - in the Applicable Documents "
         "sheet with its group and sub-group - not a table, and not a column of numbers and a column of titles.",
         "User request (1.5.0): the applicable-documents listing with a list title and a tab-indented sub-title.",
         text=_DOCS_490,
         expect=para("3.1 | The radar shall meet the requirements of this section. [title: General]"),
         documents=_DOCS_490_LIST),
    Case("STR-06", "The same list of documents, proportional font",
         "STR-05 printed in a proportional (serif) font.",
         "As STR-05.",
         "User request (1.5.0); a variant of STR-05.",
         text=_DOCS_490, font="serif",
         expect=para("3.1 | The radar shall meet the requirements of this section. [title: General]"),
         documents=_DOCS_490_LIST),
    Case("STR-07", "A list of documents in the MIL-STD-961E layout",
         "'2.2.1 Specifications, standards, and handbooks.', the group title 'DEPARTMENT OF DEFENSE STANDARDS', and "
         "entries 'MIL-STD-461G  - Requirements for the Control of ...' (a dash before the title, which wraps), then "
         "the note '(Copies of these documents are available ...)'.",
         "Two documents with their titles (the dash is not part of the title, the wrapped line is), and no "
         "referencing paragraphs; the note is not a document.",
         "MIL-STD-961E 5.7 (research for 1.5.0).",
         text="""
2.  APPLICABLE DOCUMENTS

2.2.1  Specifications, standards, and handbooks.  The following
specifications, standards, and handbooks form a part of this document.

DEPARTMENT OF DEFENSE STANDARDS

  MIL-STD-461G  - Requirements for the Control of Electromagnetic
                  Interference Characteristics
  MIL-STD-704F  - Aircraft Electric Power Characteristics

(Copies of these documents are available from the Defense
Logistics Agency.)

3.  REQUIREMENTS

3.1  General.  The radar shall meet the requirements of this section.
""",
         expect=para("3.1 | The radar shall meet the requirements of this section."),
         documents=("MIL-STD-461G | Requirements for the Control of Electromagnetic Interference Characteristics | ",
                    "MIL-STD-704F | Aircraft Electric Power Characteristics | ")),
    Case("STR-08", "Columns with no heading row and no title are a list",
         "'3.2.4 Interface. The interface shall have the following properties:' then three lines in three columns "
         "('Connector  D38999/26WB35PN  Shell size 11' ...), with no heading row and no 'TABLE ...' title.",
         "No Table item: a table needs a heading row printed as one, or a title. The lines are the lead-in's list, "
         "one row each with the lead-in in front.",
         "User request (1.5.0): only a table when there is a table header or title.",
         text="""
3.2.4  Interface.  The interface shall have the following properties:

    Connector      D38999/26WB35PN      Shell size 11
    Contacts       Crimp, size 22D      Gold plated
    Backshell      M85049/38-11W        Straight

3.2.5  Weight.  The equipment shall not exceed 45 kilograms.
""",
         expect=items("The interface shall have the following properties:",
                      "3.2.4 | Connector D38999/26WB35PN Shell size 11",
                      "3.2.4 | Contacts Crimp, size 22D Gold plated",
                      "3.2.4 | Backshell M85049/38-11W Straight")
         + para("3.2.5 | The equipment shall not exceed 45 kilograms."), tables=0),
    Case("STR-09", "A table with an underlined heading row and no title",
         "'The test equipment is listed below.' then a table whose heading row 'Item  Model  Quantity' is "
         "underlined, three rows, then 4.2.",
         "One Table item: the underlined row is its heading row, which is enough for a table without a title.",
         "User request (1.5.0): underlined text as table headers.",
         text="""
4.1  Test equipment.  The test equipment is listed below.

     <u>Item</u>             <u>Model</u>             <u>Quantity</u>
     Oscilloscope     DSO-X 3034T       2
     Power supply     E36313A           1
     Load bank        LB-2000           1

4.2  Test conditions.  Each test shall be run at room temperature.
""",
         expect=para("4.2 | Each test shall be run at room temperature."), tables=1, table_has=("Oscilloscope",)),
    Case("STR-10", "A table with a bold heading row and no title",
         "STR-09 with the heading row printed in bold instead of underlined.",
         "As STR-09: a bold row over plain rows is a heading row.",
         "User request (1.5.0): a header only if the text format is different.",
         text="""
4.1  Test equipment.  The test equipment is listed below.

     <b>Item</b>             <b>Model</b>             <b>Quantity</b>
     Oscilloscope     DSO-X 3034T       2
     Power supply     E36313A           1
     Load bank        LB-2000           1

4.2  Test conditions.  Each test shall be run at room temperature.
""",
         expect=para("4.2 | Each test shall be run at room temperature."), tables=1, table_has=("Oscilloscope",)),
    Case("STR-11", "A table carried onto the next page without its heading row",
         "'TABLE I. Discrete signals.' and a table with a bold heading row at the foot of page 1; its last three rows "
         "at the top of page 2, with no heading row and no title; then a paragraph.",
         "One Table item holding the rows of both pages: the piece at the top of page 2 carries on the table above "
         "it, so it needs no heading row or title of its own.",
         "User request (1.5.0): a table may continue on a new page without a new header.",
         text="""
3.5  Discrete signals.  The discrete signals shall be as listed in
TABLE I.
@y 8.2
                 TABLE I. Discrete signals.

     <b>Signal</b>           <b>Level</b>             <b>Remarks</b>
     READY            0 V / 5 V         Set after self test
     FAULT            0 V / 5 V         Latched
@page
     RESET            0 V / 5 V         Pulse, 10 ms
     STANDBY          0 V / 5 V         Held low in standby
     TEST             0 V / 5 V         Built-in test request

3.6  Grounding.  The signal return shall be isolated from chassis.
""",
         expect=para("3.5 | The discrete signals shall be as listed in TABLE I.",
                     "3.6 | The signal return shall be isolated from chassis."),
         tables=1, table_has=("READY", "STANDBY", "TEST"), captions=("TABLE I",)),
    Case("STR-12", "Look-alike misreads are corrected and listed",
         "'3.6 Weight. The equipment shall be requ1red to weigh no more than 1O0 kg.' - a digit 1 printed inside "
         "'required' and a letter O inside '100' (as a misread would give them).",
         "The text reads 'required' and '100'; the OCR Corrections column lists the corrected word. (The recogniser "
         "itself already reads the printed '1O0' as '100'; a corrected number - flagged for a check, because a value "
         "decides what the requirement says - is tested in tests/test_rules.py.)",
         "User request (1.5.0): autocorrect look-alike letters and digits, visibly.",
         text="""
3.6  Weight.  The equipment shall be requ1red to weigh no more
than 1O0 kg.
""",
         expect=para("3.6 | The equipment shall be required to weigh no more than 100 kg. [corrected: requ1red]")),
    Case("STR-13", "A requirement in section 6 (Notes)",
         "'6. NOTES' then '6.1 Intended use. The equipment shall be used on fixed-wing aircraft.'",
         "The requirement row is kept, with a quality note that section 6 is not contractually binding "
         "(MIL-STD-961E 5.11).",
         "MIL-STD-961E 5.11 (research for 1.5.0).",
         text="""
6.  NOTES

6.1  Intended use.  The equipment shall be used on fixed-wing
aircraft.
""",
         expect=para("6.1 | The equipment shall be used on fixed-wing aircraft. [quality: not contractually binding]"),
         outline=("1 | 6 NOTES", "2 | 6.1 Intended use")),
]
