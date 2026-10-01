"""
Page breaks: an item or a paragraph that carries on at the top of the next page must be joined back into one
row (its Page(s) column then reads '1-2'), and what starts the next page must not be taken for a new section
just because it starts with a number.
"""
from casekit import Case, items, para

AREA = "Page breaks"

_STEM = "The equipment shall meet each of the following:"
_TOP = """
3.2.3 Power. The unit shall operate from 28 VDC aircraft power.
@y 8.9
3.2.4 Environmental conditions. The equipment shall meet
each of the following:
~
    a.    Acceleration:     5 g in each of the three orthogonal axes
                            for 1 minute per axis.
~
"""
_BOTTOM = """~
    c.    Shock:            40 g, 11 ms half-sine pulse.

3.2.5 Weight. The equipment shall not exceed 45 kilograms.
"""
_A = "3.2.4 a | a. Acceleration: 5 g in each of the three orthogonal axes for 1 minute per axis. [pages: 1]"
_C = "3.2.4 c | c. Shock: 40 g, 11 ms half-sine pulse. [pages: 1-2]"   # (its row holds the lead-in, from page 1)
_ENDS = para("3.2.5 | The equipment shall not exceed 45 kilograms.")
_POWER = para("3.2.3 | The unit shall operate from 28 VDC aircraft power.")

CASES = [
    Case("PAGE-01", "A tab-list value that carries on at the top of the next page",
         "Item b's value starts at the foot of page 1 ('20 Hz to 2000 Hz random, 0.04 g2/Hz,') and carries on at the "
         "top of page 2 in the value column ('3 hours per axis, 7.7 g rms overall.'); c. and 3.2.5 follow on page 2.",
         "Item b is one row with its whole value, pages '1-2'; c is still item c.",
         "Review round 2, finding contstem/a8 (written as a two-page document for the case library).",
         text=_TOP + """    b.    Vibration:        20 Hz to 2000 Hz random, 0.04 g2/Hz,
@page
                            3 hours per axis, 7.7 g rms overall.
""" + _BOTTOM,
         expect=_POWER + items(_STEM, _A, "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random, 0.04 g2/Hz, 3 hours per axis, "
                                          "7.7 g rms overall. [pages: 1-2]", _C) + _ENDS),
    Case("PAGE-02", "A value carried onto the next page that starts with a decimal quantity",
         "As PAGE-01, but the line at the top of page 2 is '2.5 G rms overall. The unit shall be powered during' / "
         "'the test.' - it starts like a paragraph numbered 2.5 with the title 'G rms overall'.",
         "The line carries item b's value on (pages '1-2'); there is no section 2.5 (round 2: it became section "
         "'2.5' and item c was filed under it).",
         "Review round 2, finding contstem/a10.",
         text=_TOP + """    b.    Vibration:        20 Hz to 2000 Hz random, 0.04 g2/Hz,
@page
                            2.5 G rms overall. The unit shall be
                            powered during the test.
""" + _BOTTOM,
         expect=_POWER + items(_STEM, _A, "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random, 0.04 g2/Hz, 2.5 G rms overall. "
                                          "The unit shall be powered during the test. [pages: 1-2]", _C) + _ENDS),
    Case("PAGE-03", "A value carried onto the next page that starts with a cross-referenced paragraph",
         "Item b's value ends at the foot of page 1 with '... as specified in'; page 2 starts, in the value column, "
         "with '4.5.3 Random vibration. Levels shall be measured at the' / 'mounting points.'",
         "The cross-reference carries item b's value on (pages '1-2'): 4.5.3 does not follow 3.2.4 and the value "
         "had not ended, so it is not a new section, and c is still item c.",
         "Review round 2, finding contstem/a12.",
         text=_TOP + """    b.    Vibration:        20 Hz to 2000 Hz random, as specified in
@page
                            4.5.3 Random vibration. Levels shall
                            be measured at the mounting points.
""" + _BOTTOM,
         expect=_POWER + items(_STEM, _A, "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random, as specified in 4.5.3 Random "
                                          "vibration. Levels shall be measured at the mounting points. [pages: 1-2]",
                               _C) + _ENDS),
    Case("PAGE-04", "A paragraph that carries on at the top of the next page",
         "Paragraph 3.2.6 ends page 1 in mid-sentence ('... forced air from the'); page 2 starts with the rest "
         "('aircraft environmental control system at an inlet temperature of' / '20 C.'), then 3.2.7.",
         "One row for 3.2.6 with the whole sentence, pages '1-2', and a review note that the text was joined across "
         "the page break.",
         "Written for the case library (README: text that continues across pages).",
         text="""
3.2.5 Power. The unit shall operate from 28 VDC aircraft power.
@y 9.3
3.2.6 Cooling. The unit shall be cooled by forced air from the
@page
aircraft environmental control system at an inlet temperature of
20 C.

3.2.7 Weight. The unit shall weigh less than 5 kg.
""",
         expect=para("3.2.5 | The unit shall operate from 28 VDC aircraft power.",
                     "3.2.6 | The unit shall be cooled by forced air from the aircraft environmental control system at "
                     "an inlet temperature of 20 C. [pages: 1-2] [note: Text continues across pages]",
                     "3.2.7 | The unit shall weigh less than 5 kg.")),
    Case("PAGE-05", "A list that carries on at the top of the next page",
         "The lead-in and items a. and b. at the foot of page 1; items c. and d. at the top of page 2, then 3.2.5.",
         "All four items under the same lead-in and paragraph number. The rows of c and d give pages '1-2': each "
         "holds the lead-in, which is on page 1.",
         "Written for the case library.",
         text="""
3.2.3 Power. The unit shall operate from 28 VDC aircraft power.
@y 8.9
3.2.4 Modes. The radar shall provide the following modes:
     a. Search mode, with a scan of 120 degrees in azimuth.
     b. Track mode, holding up to twenty targets in track.
@page
     c. Ground mapping mode.
     d. Test mode.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=_POWER + items("The radar shall provide the following modes:",
                               "3.2.4 a | a. Search mode, with a scan of 120 degrees in azimuth. [pages: 1]",
                               "3.2.4 b | b. Track mode, holding up to twenty targets in track. [pages: 1]",
                               "3.2.4 c | c. Ground mapping mode. [pages: 1-2]", "3.2.4 d | d. Test mode. [pages: 1-2]")
         + para("3.2.5 | The radar shall weigh less than 45 kg.")),
]
