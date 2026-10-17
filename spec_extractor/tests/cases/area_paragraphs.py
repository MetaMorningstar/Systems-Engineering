"""
Paragraphs around lists: what comes after the last item - an ordinary paragraph with its first line indented, a
sub-paragraph, a sentence in the items' text column, a NOTE - must not be swallowed by the last item, and the
last item must keep all of its own lines. Also paragraphs that are numbered or lettered in a hanging indent.
"""
from casekit import Case, items, para

AREA = "Paragraphs around lists"

_MODES = "The radar shall provide the following modes:"
_MODES_LEAD = "3.2.4 Modes. The radar shall provide the following modes:"
_ABC = ["3.2.4 a | a. Search mode.", "3.2.4 b | b. Track mode.", "3.2.4 c | c. Ground mapping mode."]
_WEIGHT_45 = "3.2.5 Weight. The radar shall not exceed 45 kilograms."
_WEIGHT_45_ROW = para("3.2.5 | The radar shall not exceed 45 kilograms.")
_PRE = """
3.2.5 Controls. The display shall have a brightness control and a
contrast control on its front panel. Each control shall be
illuminated for night use and shall be operable with gloved hands
in all environmental conditions specified herein.
"""
_PRE_ROWS = para("3.2.5 | The display shall have a brightness control and a contrast control on its front panel.",
                 "3.2.5 | Each control shall be illuminated for night use and shall be operable with gloved hands in "
                 "all environmental conditions specified herein.")

CASES = [
    Case("PARA-01", "Paragraphs with a first-line indent after a list at the margin",
         "'(a) Search mode.' to '(c) Ground mapping mode.' at the margin, then two ordinary paragraphs whose first "
         "line is indented and whose second line is back at the margin, then 3.2.5.",
         "The paragraphs are not more of item (c): each is a row of its own (they have no number of their own, so "
         "their Doc Ref is empty).",
         "Review round 1 (layout, hanging indents); real OCR page hang_paren.",
         text=f"""
{_MODES_LEAD}
(a) Search mode.
(b) Track mode.
(c) Ground mapping mode.

     The radar shall switch between any two modes in less than
one second.

     The radar shall retain the selected mode after a power
interruption of less than 50 ms.

{_WEIGHT_45}
""",
         expect=items(_MODES, "3.2.4 a | (a) Search mode.", "3.2.4 b | (b) Track mode.",
                      "3.2.4 c | (c) Ground mapping mode.")
         + para(" | The radar shall switch between any two modes in less than one second.",
                " | The radar shall retain the selected mode after a power interruption of less than 50 ms.")
         + _WEIGHT_45_ROW),
    Case("PARA-02", "A numbered sub-paragraph indented under a list",
         "'a. Search mode.' / 'b. Track mode.', a blank line, then '3.2.4.1 Mode switching. The radar shall "
         "switch ...' indented to the items' text column, then 3.2.5.",
         "3.2.4.1 is a paragraph of its own with its own number - not more of item b.",
         "Review round 1 (layout, hanging indents); real OCR page hang_numbered.",
         text=f"""
{_MODES_LEAD}
     a. Search mode.
     b. Track mode.

        3.2.4.1 Mode switching. The radar shall switch between
        modes in less than one second.

{_WEIGHT_45}
""",
         expect=items(_MODES, *_ABC[:2])
         + para("3.2.4.1 | The radar shall switch between modes in less than one second.") + _WEIGHT_45_ROW),
    Case("PARA-03", "A one-line indented paragraph after a list at the margin",
         "'a.', 'b.', 'c.' at the margin, a blank line, then one sentence indented eight characters, then 3.2.5.",
         "The sentence is a requirement of its own, not more of item c. It sits between the list and the next "
         "numbered paragraph, so it keeps the list's lead-in and paragraph number (Doc Ref '3.2.4', no letter).",
         "Review round 1, finding lists/F3; real OCR page indented_para.",
         text=f"""
{_MODES_LEAD}
a. Search mode.
b. Track mode.
c. Ground mapping mode.

        The radar shall switch modes in less than one second.

{_WEIGHT_45}
""",
         expect=items(_MODES, *_ABC, "3.2.4 | The radar shall switch modes in less than one second.")
         + _WEIGHT_45_ROW),
    Case("PARA-04", "A paragraph after a last item of three lines",
         "Item c. wraps onto three lines; after a blank line, a two-line sentence in the items' text column; then "
         "3.2.5.",
         "The blank line ends item c: the sentence keeps its own row (with the lead-in, no letter) and item c keeps "
         "its three lines (round 2: the three-line item's line spacing spanned the blank line and the sentence "
         "was joined to it).",
         "Review round 2, finding contstem/a5; real OCR page para_after_long_item.",
         text=f"""
{_MODES_LEAD}
     a. Search mode.
     b. Track mode.
     c. Ground mapping mode, with the antenna tilted down by
        the angle set by the operator and the range scale set
        to 10, 20 or 40 km.

        The radar shall switch between any two modes in less
        than one second.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_MODES, *_ABC[:2],
                      "3.2.4 c | c. Ground mapping mode, with the antenna tilted down by the angle set by the operator "
                      "and the range scale set to 10, 20 or 40 km.",
                      "3.2.4 | The radar shall switch between any two modes in less than one second.")
         + para("3.2.5 | The radar shall weigh less than 45 kg.")),
    Case("PARA-05", "A NOTE on tab stops after a list",
         "The list, a blank line, then 'NOTE:' at the margin with its text on a tab stop over two lines, then "
         "3.2.5.",
         "The NOTE is a row of its own, whole, and is not joined to item c (round 1: the note's text went into the "
         "list).",
         "Review round 1 (layout, notes); real OCR page note_after_list.",
         text=f"""
{_MODES_LEAD}
     a. Search mode.
     b. Track mode.
     c. Ground mapping mode.

NOTE:   The operator shall confirm each mode change on the
        control panel before it takes effect.

{_WEIGHT_45}
""",
         expect=items(_MODES, *_ABC)
         + para(" | NOTE: The operator shall confirm each mode change on the control panel before it takes effect.")
         + _WEIGHT_45_ROW),
    Case("PARA-06", "'Note.' level with the list's markers",
         "'a.', 'b.', 'c.' at the margin and straight under them, with no blank line, 'Note. The operator shall "
         "confirm each mode change.'",
         "The note is not item c's continuation and is not given a letter: a row of its own ('Note' is taken as "
         "its title).",
         "Review round 1 (layout, notes); real OCR page note_level.",
         text=f"""
{_MODES_LEAD}
a. Search mode.
b. Track mode.
c. Ground mapping mode.
Note. The operator shall confirm each mode change.

{_WEIGHT_45}
""",
         expect=items(_MODES, *_ABC) + para(" | The operator shall confirm each mode change.") + _WEIGHT_45_ROW),
    Case("PARA-07", "Numbered items without full stops, then a paragraph",
         "A paragraph, then '1. Search mode' / '2. Track mode' (no full stops), a blank line, then 'The operator "
         "shall select the mode from the front panel.' in the items' text column.",
         "The sentence is a requirement of its own (with the lead-in, no number), not more of item 2 (round 3: an "
         "item without a full stop looked unfinished and the sentence was glued to it). Lettered items: LST-25.",
         "Review round 3, finding B3; real OCR page r8_numbered_noperiod_para.",
         text=_PRE + """
3.2.6 Modes. The radar shall provide the following modes:
     1. Search mode
     2. Track mode

        The operator shall select the mode from the front panel.

3.2.7 Mass. The radar shall weigh less than 45 kg. The mass shall
include the mounting tray and all cables supplied with the unit.
""",
         expect=_PRE_ROWS
         + items(_MODES, "3.2.6 1 | 1. Search mode", "3.2.6 2 | 2. Track mode",
                 "3.2.6 | The operator shall select the mode from the front panel.")
         + para("3.2.7 | The radar shall weigh less than 45 kg.",
                "3.2.7 | The mass shall include the mounting tray and all cables supplied with the unit.")),
    Case("PARA-08", "Paragraph numbers set apart from their text (hanging indent)",
         "'3.2.1' at the margin and its text ('Power. The unit shall ...') on a tab stop an inch further in, for "
         "3.2.1 to 3.2.3; then the heading '3.3 Interfaces' and two ordinary paragraphs.",
         "Each numbered paragraph is one row with its number as the Doc Ref and its title split off ('The unit "
         "shall operate from ...'); no table; the two paragraphs are in section '3.3 Interfaces'.",
         "Review round 1 (layout); real OCR page hanging_numbers. A known limitation until 1.5.0 (an extra Table "
         "item, titles left in the text).",
         text="""
3.2.1     Power. The unit shall operate from the 28 VDC
          aircraft bus and shall draw no more than 150 W.

3.2.2     Cooling. The unit shall be cooled by forced air
          from the aircraft ECS at 20 C maximum inlet.

3.2.3     Mass. The unit shall weigh less than 5 kg.

3.3 Interfaces

     The unit shall provide an RS-422 interface to the
mission computer as defined in the ICD.

     The unit shall provide a MIL-STD-1553B remote terminal.
""",
         expect=para("3.2.1 | The unit shall operate from the 28 VDC aircraft bus and shall draw no more than 150 W.",
                     "3.2.2 | The unit shall be cooled by forced air from the aircraft ECS at 20 C maximum inlet.",
                     "3.2.3 | The unit shall weigh less than 5 kg.",
                     " | The unit shall provide an RS-422 interface to the mission computer as defined in the ICD. "
                     "[section: 3.3 Interfaces]",
                     " | The unit shall provide a MIL-STD-1553B remote terminal. [section: 3.3 Interfaces]")),
    Case("PARA-09", "Lettered paragraphs 'A. General:' under a heading",
         "The heading '3.1 Installation.', then 'A. General: The contractor shall provide all labor, materials' "
         "with its next line back at the margin, and 'B. Cabling: ...' the same way; then 3.2.",
         "Each lettered paragraph is one whole row (round 3: the sentence was cut after 'materials' and the rest "
         "dropped). Its letter is kept: Doc Ref '3.1 A' / '3.1 B', as for the items of a list.",
         "Review round 3, finding F6; real OCR page lettered_para.",
         text="""
3.1 Installation.

     A. General: The contractor shall provide all labor, materials
and equipment needed to install the system at each site.

     B. Cabling: The contractor shall route all cables through the
existing cable trays and shall label each cable at both ends.

3.2 Testing. The contractor shall test each installed system.
""",
         expect=para("3.1 A | A. General: The contractor shall provide all labor, materials and equipment needed to "
                     "install the system at each site.",
                     "3.1 B | B. Cabling: The contractor shall route all cables through the existing cable trays and "
                     "shall label each cable at both ends.",
                     "3.2 | The contractor shall test each installed system."),
         known="The letters are lost: both rows have an empty Doc Ref and their text starts at the label ('General: "
               "The contractor shall ...'). The text itself is complete."),
]
