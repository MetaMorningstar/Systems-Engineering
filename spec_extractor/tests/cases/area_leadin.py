"""
Lead-ins: the sentence that introduces a list. It normally ends with ':', but the colon is often left out
('... shall show the following information.', '... listed below.'), and the same words can appear in running
text without any list ('... retested on the following day.'). These cases check which lines are taken as the
items of a lead-in, and that a sentence after the list is not swallowed as one more item.
"""
from casekit import Case, items, para

AREA = "Lead-ins"

_PRE = """
3.2.5 Controls. The display shall have a brightness control and a
contrast control on its front panel. Each control shall be
illuminated for night use and shall be operable with gloved hands
in all environmental conditions specified herein.
"""
_PRE_ROWS = para("3.2.5 | The display shall have a brightness control and a contrast control on its front panel.",
                 "3.2.5 | Each control shall be illuminated for night use and shall be operable with gloved hands in "
                 "all environmental conditions specified herein.")
_LEAD = "3.2.6 Displays. The display shall show the following information."
_STEM = "The display shall show the following information."
_SUN = "The display shall be readable in direct sunlight."
_MASS = """
3.2.7 Mass. The display shall weigh less than 5 kg. The mass shall
include the mounting tray and all cables supplied with the unit.
"""
_MASS_ROWS = para("3.2.7 | The display shall weigh less than 5 kg.",
                  "3.2.7 | The mass shall include the mounting tray and all cables supplied with the unit.")
_THREE = items(_STEM, "3.2.6 | Own ship position and heading.", "3.2.6 | Target range and bearing.",
               "3.2.6 | Time to go to the next waypoint.")

CASES = [
    Case("LEAD-01", "No colon; items separated by blank lines; then a requirement at the same indent",
         "A paragraph, then '3.2.6 ... the following information.' (no colon), three short indented lines each "
         "after a blank line, then - at the same indent - 'The display shall be readable in direct sunlight.'",
         "The three short lines are the items of the lead-in (each row: the lead-in + the item). The sentence "
         "after them states a requirement of its own and keeps its own row (round 3: it was taken as a fourth "
         "item).",
         "Review round 3, finding F3; real OCR page r2d_colonless_swallow_ctx_blanks.",
         text=_PRE + f"""
{_LEAD}

     Own ship position and heading.

     Target range and bearing.

     Time to go to the next waypoint.

     {_SUN}
""" + _MASS,
         expect=_PRE_ROWS + _THREE + para(f" | {_SUN}") + _MASS_ROWS),
    Case("LEAD-02", "No colon; four single-spaced items right under the lead-in",
         "A paragraph, then the lead-in without a colon and, right under it with no blank line, four short "
         "indented lines ('Own ship position and heading.', 'Target range and bearing.', 'Time of day.', "
         "'Waypoint number.').",
         "All four lines are items (round 3: the first line was put into the lead-in's block and silently "
         "dropped, so a list that looked complete was not).",
         "Review round 3, finding B2; real OCR page r7_colonless_single_spaced.",
         text=_PRE + f"""
{_LEAD}
     Own ship position and heading.
     Target range and bearing.
     Time of day.
     Waypoint number.
""" + _MASS,
         expect=_PRE_ROWS + items(_STEM, "3.2.6 | Own ship position and heading.", "3.2.6 | Target range and bearing.",
                                  "3.2.6 | Time of day.", "3.2.6 | Waypoint number.") + _MASS_ROWS),
    Case("LEAD-03", "No colon; three single-spaced items after a blank line; then a requirement",
         "A paragraph, the lead-in without a colon, a blank line, three short single-spaced indented lines (one "
         "block of 16 words), a blank line, then 'The display shall be readable in direct sunlight.' at the same "
         "indent.",
         "The three lines are items; the requirement after them keeps its own row.",
         "Review round 3, findings B2 and F3; real OCR page r2c_colonless_swallow_ctx.",
         text=_PRE + f"""
{_LEAD}

     Own ship position and heading.
     Target range and bearing.
     Time to go to the next waypoint.

     {_SUN}
""" + _MASS,
         expect=_PRE_ROWS + _THREE + para(f" | {_SUN}") + _MASS_ROWS),
    Case("LEAD-04", "'... listed below.' with plain one-line items",
         "'3.2.4 Modes. The radar shall provide the operating modes listed below.' then three indented lines "
         "without markers or full stops ('Search mode', 'Track while scan mode', 'Ground mapping mode').",
         "A lead-in without a colon may lead into plain items too: three rows, each with the lead-in in front "
         "(round 2: only marked or labelled items were taken after a colon-less lead-in).",
         "Review round 2, finding contstem/a3.",
         text="""
3.2.4 Modes. The radar shall provide the operating modes listed below.
     Search mode
     Track while scan mode
     Ground mapping mode

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items("The radar shall provide the operating modes listed below.", "3.2.4 | Search mode",
                      "3.2.4 | Track while scan mode", "3.2.4 | Ground mapping mode")
         + para("3.2.5 | The radar shall weigh less than 45 kg.")),
    Case("LEAD-05", "No colon, at the top of the page; three single-spaced items after a blank line",
         "LEAD-03 without the paragraph above it: the lead-in is the first line of the page.",
         "As LEAD-03: three items, then the requirement on its own row.",
         "Review round 3, finding B2; real OCR page r2_colonless_swallow.",
         text=f"""
{_LEAD}

     Own ship position and heading.
     Target range and bearing.
     Time to go to the next waypoint.

     {_SUN}

3.2.7 Mass. The display shall weigh less than 5 kg.
""",
         expect=_THREE + para(f" | {_SUN}", "3.2.7 | The display shall weigh less than 5 kg."),
         known="With nothing above the lead-in, the three short lines are neither taken as items nor flagged: "
               "only the lead-in and the requirement below them are rows (with a paragraph above the lead-in they "
               "are found - LEAD-03)."),
    Case("LEAD-06", "No colon, at the top of the page; items separated by blank lines",
         "LEAD-01 without the paragraph above it: the lead-in is the first line of the page.",
         "As LEAD-01: three items, then the requirement on its own row.",
         "Review round 3, finding F3; real OCR page r2b_colonless_swallow_blanks.",
         text=f"""
{_LEAD}

     Own ship position and heading.

     Target range and bearing.

     Time to go to the next waypoint.

     {_SUN}

3.2.7 Mass. The display shall weigh less than 5 kg.
""",
         expect=_THREE + para(f" | {_SUN}", "3.2.7 | The display shall weigh less than 5 kg."),
         known="With nothing above the lead-in, the three short lines are neither taken as items nor flagged: "
               "only the lead-in and the requirement below them are rows (with a paragraph above the lead-in they "
               "are found - LEAD-01)."),
    Case("LEAD-07", "Lead-in words in the middle of a paragraph",
         "'... shall be repaired and retested on the following day. The results ...' and '... shall be marked as "
         "specified below. The marking shall be legible ...' - the words of a lead-in, but inside running text "
         "with no list after them.",
         "No list: each sentence is a row of its own paragraph (round 1: 'on the following day.' was taken as a "
         "lead-in and the next sentence became its item).",
         "Review round 1, finding lists/F1; real OCR page r01_midblock.",
         text="""
3.4.1 Retest. A unit that fails shall be repaired and retested on the
following day. The results of the retest shall be recorded in the test
log and the log shall be signed by the quality inspector before the
unit is returned to stock.

3.4.2 Marking. Each unit shall be marked as specified below. The
marking shall be legible from a distance of one metre and shall
survive the cleaning fluids of 4.5.3 without loss of legibility.

3.4.3 Weight. The unit shall weigh 5 kg.
""",
         expect=para("3.4.1 | A unit that fails shall be repaired and retested on the following day.",
                     "3.4.1 | The results of the retest shall be recorded in the test log and the log shall be signed "
                     "by the quality inspector before the unit is returned to stock.",
                     "3.4.2 | Each unit shall be marked as specified below.",
                     "3.4.2 | The marking shall be legible from a distance of one metre and shall survive the cleaning "
                     "fluids of 4.5.3 without loss of legibility.",
                     "3.4.3 | The unit shall weigh 5 kg.")),
    Case("LEAD-08", "A colon with nothing below it",
         "'3.2.6 Displays. The display shall show the following:' followed straight away by the next numbered "
         "paragraph - the list is missing (lost on the scan, or on another page).",
         "The lead-in is a row of its own and Review Reasons says a list was promised but not found; 3.2.7 is not "
         "taken as its item.",
         "Written for the case library (the flag is described in the README).",
         text="""
3.2.6 Displays. The display shall show the following:

3.2.7 Mass. The display shall weigh less than 5 kg.
""",
         expect=para("3.2.6 | The display shall show the following: [note: Ends with ':' but no list items]",
                     "3.2.7 | The display shall weigh less than 5 kg.")),
    Case("LEAD-09", "Lead-in words, then the next numbered paragraph",
         "'3.2.6 ... as follows.' (no colon) followed by the next numbered paragraph '3.2.7 Mass. ...'.",
         "A sentence that just ends in a lead-in phrase and is followed by a new paragraph is not a list: two "
         "rows, and 3.2.7 keeps its number.",
         "Written for the case library (round 3 review of rule 7).",
         text="""
3.2.6 Displays. The display brightness shall be adjusted as follows.

3.2.7 Mass. The display shall weigh less than 5 kg.
""",
         expect=para("3.2.6 | The display brightness shall be adjusted as follows.",
                     "3.2.7 | The display shall weigh less than 5 kg.")),
]
