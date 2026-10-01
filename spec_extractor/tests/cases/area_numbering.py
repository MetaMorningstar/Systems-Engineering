"""
Paragraph numbers and headings: which lines start a new numbered paragraph or a section heading, and which
numbers are only list items, cross-references or values at the start of a wrapped line. The Section column
is checked where a heading must (or must not) become the section of the rows below it.
"""
from casekit import Case, items, para

AREA = "Paragraph numbers and headings"

_DOCS_STEM = "The following documents form a part of this specification to the extent specified herein and shall apply:"

CASES = [
    Case("NUM-01", "Numbered lists in sections 2 and 3, each followed by the next paragraph",
         "'2. APPLICABLE DOCUMENTS' with 2.1 and its list '1. MIL-STD-461G' / '2. MIL-STD-704F', then 2.2; '3. "
         "REQUIREMENTS' with 3.1, 3.2 and its list '1. Search mode.' to '3. Ground mapping mode.', then 3.3.",
         "The numbered items are list items, not section headings: rows 2.1 1, 2.1 2, 3.2 1 to 3.2 3. 2.2 and 3.3 "
         "keep their numbers and their sections (round 2: '3.2.5' after the list was taken as the list's own "
         "sub-paragraph, and the items became headings).",
         "Review round 2, finding contstem/a1 (opens section); real OCR page opens_section.",
         text="""
2. APPLICABLE DOCUMENTS

2.1 Government documents. The following documents form a part of
this specification to the extent specified herein and shall apply:

     1. MIL-STD-461G
     2. MIL-STD-704F

2.2 Order of precedence. In the event of a conflict, the text of
this specification shall take precedence.

3. REQUIREMENTS

3.1 Power. The unit shall operate from 28 VDC.

3.2 Modes. The radar shall provide the following modes:

     1. Search mode.
     2. Track mode.
     3. Ground mapping mode.

3.3 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_DOCS_STEM, "2.1 1 | 1. MIL-STD-461G", "2.1 2 | 2. MIL-STD-704F")
         + para("2.2 | In the event of a conflict, the text of this specification shall take precedence. "
                "[section: 2 APPLICABLE DOCUMENTS]",
                "3.1 | The unit shall operate from 28 VDC. [section: 3 REQUIREMENTS]")
         + items("The radar shall provide the following modes:", "3.2 1 | 1. Search mode.", "3.2 2 | 2. Track mode.",
                 "3.2 3 | 3. Ground mapping mode.")
         + para("3.3 | The radar shall weigh less than 45 kg. [section: 3 REQUIREMENTS]")),
    Case("NUM-02", "A title-case heading with a full stop after a list at the margin",
         "A list 'a. Search mode.' / 'b. Track mode.' at the left margin, a blank line, the heading '4. "
         "Verification.' (title case, with a full stop), then 4.1.",
         "'4. Verification.' is a heading, not the list's next item: no row for it, and 4.1 is in section '4 "
         "Verification' (round 3: it became a false requirement row '... following modes: 4. Verification.').",
         "Review round 3, finding F2; real OCR page r1b_margin_list_heading_period.",
         text="""
3.9 Modes. The radar shall provide the following modes:

a. Search mode.
b. Track mode.

4. Verification.

4.1 General. The contractor shall verify each requirement of
section 3 by test.
""",
         expect=items("The radar shall provide the following modes:", "3.9 a | a. Search mode.", "3.9 b | b. Track mode.")
         + para("4.1 | The contractor shall verify each requirement of section 3 by test. [section: 4 Verification]")),
    Case("NUM-03", "A heading with a full stop after a list of documents without full stops",
         "'a. MIL-STD-461G' / 'b. MIL-STD-704F' at the margin (no full stops), a blank line, then the heading '3. "
         "Requirements.' and paragraphs 3.1 and 3.2.",
         "The heading ends the list: item b is 'b. MIL-STD-704F' and 3.1 and 3.2 are in section '3 Requirements'.",
         "Review round 3, finding F2; real OCR page r1_heading_period.",
         text="""
2. APPLICABLE DOCUMENTS

2.1 Government documents. The following documents form a part of
this specification to the extent specified herein and shall apply:

a. MIL-STD-461G
b. MIL-STD-704F

3. Requirements.

3.1 Power. The unit shall operate from 28 VDC aircraft power.

3.2 Weight. The unit shall weigh less than 5 kg.
""",
         expect=items(_DOCS_STEM, "2.1 a | a. MIL-STD-461G", "2.1 b | b. MIL-STD-704F")
         + para("3.1 | The unit shall operate from 28 VDC aircraft power. [section: 3 Requirements]",
                "3.2 | The unit shall weigh less than 5 kg. [section: 3 Requirements]"),
         known="Almost every line of this page is followed by a blank line, so a blank line is taken as the "
               "page's normal line spacing; item b has no full stop, and the heading one blank line below it is "
               "read as its next line: the row is 'b. MIL-STD-704F 3. Requirements.' and 3.1 and 3.2 keep the "
               "section '2 APPLICABLE DOCUMENTS'."),
    Case("NUM-04", "Empty sections in a row ('5. Packaging.', '6. Notes.')",
         "4.3, then the headings '5. Packaging.' and '6. Notes.' each followed only by a blank line, then 6.1.",
         "Both are headings (no rows of their own) and 6.1 is in section '6 Notes' (round 3: a run of empty "
         "sections lost '6 Notes').",
         "Review round 3, finding F2; real OCR page r1_heading_period.",
         text="""
4.3 Inspection. The unit shall be inspected.

5. Packaging.

6. Notes.

6.1 Intended use. The unit shall be used in fighter aircraft.
""",
         expect=para("4.3 | The unit shall be inspected.",
                     "6.1 | The unit shall be used in fighter aircraft. [section: 6 Notes]")),
    Case("NUM-05", "Wrapped lines that start with a cross-reference or a quantity",
         "Paragraph 3.2.4 wraps after '... loads in paragraph' so the next line starts '3.2.5. The weight shall "
         "...'; 3.2.5 has a line starting '3.5 G in each axis ...'; 3.2.6 has one starting '4.2.1 Bonding Test) "
         "with ...' after '(see'.",
         "None of these numbers starts a new paragraph: 3.2.4 keeps both its sentences, and 3.2.5 and 3.2.6 are "
         "each one paragraph (round 1: 3.2.4 was split at '3.2.5.', which is exactly the number that comes next).",
         "Review round 1, finding numbering/F1; real OCR page r1_crossref.",
         text="""
3.2.4 Weight. The weight of the complete unit, including the mounting
tray and all interconnecting cables, shall not exceed the allocation
established for the installation and airframe loads in paragraph
3.2.5. The weight shall be verified by measurement with all fluids
drained and all covers fitted.

3.2.5 Structural loads. The mounting tray and its fasteners shall
withstand, without permanent deformation, a load factor equal to
3.5 G in each axis applied for not less than three seconds.

3.2.6 Bonding. The bonding resistance between the chassis and the
mounting structure shall not exceed 2.5 milliohms when measured (see
4.2.1 Bonding Test) with a calibrated four-wire milliohm meter.

3.2.7 Finish. The unit shall be painted gloss white.
""",
         expect=para("3.2.4 | The weight of the complete unit, including the mounting tray and all interconnecting "
                     "cables, shall not exceed the allocation established for the installation and airframe loads in "
                     "paragraph 3.2.5.",
                     "3.2.4 | The weight shall be verified by measurement with all fluids drained and all covers fitted.",
                     "3.2.5 | The mounting tray and its fasteners shall withstand, without permanent deformation, a load "
                     "factor equal to 3.5 G in each axis applied for not less than three seconds.",
                     "3.2.6 | The bonding resistance between the chassis and the mounting structure shall not exceed "
                     "2.5 milliohms when measured (see 4.2.1 Bonding Test) with a calibrated four-wire milliohm meter.",
                     "3.2.7 | The unit shall be painted gloss white.")),
    Case("NUM-06", "Paragraph numbers that skip after a list (3.2.4, then 3.2.8)",
         "Paragraphs with a first-line indent: 3.2.4 with a list on tab stops, then 3.2.8 and 3.2.9 (a skip of "
         "four - or a scan that misread 3.2.5).",
         "3.2.8 and 3.2.9 are paragraphs of their own, not more items of the 3.2.4 list (round 2: both were "
         "swallowed as extra items because 3.2.8 does not follow 3.2.4).",
         "Review round 2, finding numbering/F3; real OCR page r3_swallow.",
         text="""
     3.2.4 Environmental conditions. The equipment shall meet
each of the following:
@gap 0.6
    a.    Temperature:      -40 C to +71 C operating.
~
    b.    Humidity:         95 percent, non-condensing.
~
    c.    Altitude:         0 to 15,000 m.

     3.2.8 Weight. The equipment shall not exceed 45 kilograms.

     3.2.9 Finish. The equipment shall be painted gloss white.
""",
         expect=items("The equipment shall meet each of the following:",
                      "3.2.4 a | a. Temperature: -40 C to +71 C operating.",
                      "3.2.4 b | b. Humidity: 95 percent, non-condensing.", "3.2.4 c | c. Altitude: 0 to 15,000 m.")
         + para("3.2.8 | The equipment shall not exceed 45 kilograms.",
                "3.2.9 | The equipment shall be painted gloss white.")),
    Case("NUM-07", "A numbered list straight before '4. Verification' and 4.1",
         "'1. Search mode.' to '3. Ground mapping mode.' under 3.2.4, then the heading '4. Verification' (no full "
         "stop) and '4.1 General. ...'.",
         "Only '4. Verification' is a heading - the one followed by its own 4.1. Items 1 to 3 stay items (round 2: "
         "the whole run 1., 2., 3. and 4. was kept as headings).",
         "Review round 2, finding contstem/a1c.",
         text="""
3.2.4 Modes. The radar shall provide the following modes:

     1. Search mode.
     2. Track mode.
     3. Ground mapping mode.

4. Verification

4.1 General. The contractor shall verify each requirement of
section 3 by test.
""",
         expect=items("The radar shall provide the following modes:", "3.2.4 1 | 1. Search mode.",
                      "3.2.4 2 | 2. Track mode.", "3.2.4 3 | 3. Ground mapping mode.")
         + para("4.1 | The contractor shall verify each requirement of section 3 by test. [section: 4 Verification]")),
    Case("NUM-08", "A wrapped line that starts with the next paragraph's number",
         "'3.2.1 Power. The unit shall draw its power as defined in paragraph' / '3.2.2 Input Power of MIL-STD-704F "
         "and shall not exceed 150 W.' - the line after 'paragraph' starts with 3.2.2, the number that would come "
         "next.",
         "After 'paragraph' a number is a cross-reference: 3.2.1 is one paragraph, and there is no paragraph "
         "3.2.2.",
         "Review round 2 (layout, numbered_next).",
         text="""
3.2.1 Power. The unit shall draw its power as defined in paragraph
3.2.2 Input Power of MIL-STD-704F and shall not exceed 150 W.

3.2.3 Cooling. The unit shall be cooled by forced air.
""",
         expect=para("3.2.1 | The unit shall draw its power as defined in paragraph 3.2.2 Input Power of MIL-STD-704F "
                     "and shall not exceed 150 W.", "3.2.3 | The unit shall be cooled by forced air.")),
    Case("NUM-09", "Two numbered paragraphs with no blank line between them",
         "'3.2.2.1 Weight. ...' and '3.2.2.2 Input power. ...' on consecutive lines, as a scan that lost the "
         "blank line between them shows them.",
         "Two paragraphs, each with its own number and title - the second sentence is not filed under the first "
         "number.",
         "README (paragraph numbers found inside a block).",
         text="""
3.2.2.1 Weight. The unit shall not exceed 45 kg with its tray.
3.2.2.2 Input power. The unit shall draw less than 150 W.

3.2.2.3 Cooling. The unit shall be cooled by forced air.
""",
         expect=para("3.2.2.1 | The unit shall not exceed 45 kg with its tray.",
                     "3.2.2.2 | The unit shall draw less than 150 W.",
                     "3.2.2.3 | The unit shall be cooled by forced air.")),
    Case("NUM-10", "A numbered list of documents at the margin",
         "'2.1 ... The following documents shall apply:' then '1. MIL-STD-461G' and '2. MIL-STD-704F' at the left "
         "margin (all capitals), a blank line, then 2.2.",
         "The two lines are items of the list, not section headings '1' and '2' (round 3: all-capital lines in "
         "sequence were called headings and the list was lost).",
         "Review round 3, rule 2 (b12_doclist_margin).",
         text="""
2.1 Government documents. The following documents shall apply:
1. MIL-STD-461G
2. MIL-STD-704F

2.2 Order of precedence. The text of this specification shall take
precedence.
""",
         expect=items("The following documents shall apply:", "2.1 1 | 1. MIL-STD-461G", "2.1 2 | 2. MIL-STD-704F")
         + para("2.2 | The text of this specification shall take precedence.")),
    Case("NUM-11", "A title page with a document-control block",
         "A centred title, a block of 'Document:', 'Revision:', 'Date:', 'Prepared by:', 'Approved by:', "
         "'Distribution:' with their values on a tab stop, then '1. SCOPE' and paragraph 1.1.",
         "Only the requirement of 1.1 is a row; the control block is not a list or a requirement.",
         "Review round 1 (layout, title page); real OCR page title_mono.",
         text="""
             SYSTEM SPECIFICATION FOR THE
                 AIRBORNE RADAR UNIT
@gap 2
           Document:              SPEC-1234
~
           Revision:              C
~
           Date:                  12 March 1998
~
           Prepared by:           J. Smith
                                  Systems Engineering Department
~
           Approved by:           R. Jones
~
           Distribution:          3 copies to the program office,
                                  1 copy to the test site.
@gap 1
1. SCOPE

1.1 Scope. This specification establishes the requirements for
the airborne radar unit. The unit shall be designed for
installation in the aircraft nose bay.
""",
         expect=para("1.1 | The unit shall be designed for installation in the aircraft nose bay. [section: 1 SCOPE]")),
    Case("NUM-12", "A table of contents with dot leaders",
         "'TABLE OF CONTENTS', then numbers, titles with dot leaders and page numbers ('3.2.1  Performance "
         "..........  4').",
         "No requirement rows and no sections come from the contents list; it is given as one Table item.",
         "Review round 1 (layout, table of contents); real OCR page toc_mono.",
         text="""
                         TABLE OF CONTENTS

Paragraph                                                        Page

1.      SCOPE ........................................            1
~
1.1     Scope ........................................            1
~
1.2     Classification ...............................            1
~
2.      APPLICABLE DOCUMENTS .........................            2
~
2.1     Government documents .........................            2
~
3.      REQUIREMENTS .................................            3
~
3.1     Item definition ..............................            3
~
3.2     Characteristics ..............................            4
~
3.2.1   Performance ..................................            4
~
3.2.2   Physical characteristics .....................            6
~
4.      QUALITY ASSURANCE PROVISIONS .................            9
~
4.1     Responsibility for inspection ................            9
""",
         expect=[], tables=1, table_has=("QUALITY ASSURANCE PROVISIONS",)),
    Case("NUM-13", "A paragraph number run into its title ('4.2Extended verification.')",
         "'4.2Extended verification. The contractor shall ...' - the scan lost the space after the number.",
         "The number is still split off: Doc Ref '4.2'.",
         "README (a faint scan can lose the space after a paragraph number).",
         text="""
4.1 General. The contractor shall verify each requirement by test.

4.2Extended verification. The contractor shall repeat each test
at the highest and the lowest operating temperature.
""",
         expect=para("4.1 | The contractor shall verify each requirement by test.",
                     "4.2 | The contractor shall repeat each test at the highest and the lowest operating "
                     "temperature.")),
]
