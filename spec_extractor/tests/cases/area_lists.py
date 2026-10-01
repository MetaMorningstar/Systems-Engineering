"""
List markers and list structure: markers that the scan lost or misread, lists that skip on purpose, nested lists,
items that wrap back to the margin, sentences and notes between items, and a second lead-in inside a paragraph.

LST-01 and LST-02 are the ordinary tight lists of the earlier 'list suite' (controls that must not change). The
later cases are the real-OCR pages of the review rounds, one situation per document.
"""
from casekit import Case, items, para, tab_list, tab_text

AREA = "List markers and list structure"

# the paragraph the round-3 pages put above their list, so the list is not alone on the page
_PRE = """
3.2.{n} Controls. The display shall have a brightness control and a
contrast control on its front panel. Each control shall be
illuminated for night use and shall be operable with gloved hands
in all environmental conditions specified herein.
"""
_PRE_ROWS = lambda n: para(  # noqa: E731
    f"3.2.{n} | The display shall have a brightness control and a contrast control on its front panel.",
    f"3.2.{n} | Each control shall be illuminated for night use and shall be operable with gloved hands in all "
    "environmental conditions specified herein.")
_MODES = "The radar shall provide the following modes:"
_MODES_LEAD = "3.2.4 Modes. The radar shall provide the following modes:"
_RADAR_WEIGHT = "3.2.5 Weight. The radar shall weigh 45 kg."
_LOST = "List marker missing"

# ---- a marker lost on an item that has no label: 'Map. Ground mapping ...' between b. and d. -----------------
_MAP_LIST = """
3.2.4 Modes. The radar shall provide the following modes:

     a. Search. Detection of targets out to 100 nmi.

     b. Track. Tracking of up to 20 targets.

{map}Map. Ground mapping at 10 m resolution.

     d. Test. Built-in test of all modules.
"""
_MAP_ROWS = items(_MODES, "3.2.4 a | a. Search. Detection of targets out to 100 nmi.",
                  "3.2.4 b | b. Track. Tracking of up to 20 targets.",
                  f"3.2.4 c | c. Map. Ground mapping at 10 m resolution. [note: {_LOST}]",
                  "3.2.4 d | d. Test. Built-in test of all modules.")
_LONG_BEFORE = """
3.2.3 Power. The radar shall operate from a 28 VDC supply as defined
in MIL-STD-704F and shall meet all of its performance requirements
over the full range of normal and abnormal steady state voltage
limits without degradation of any function.
"""
_LONG_AFTER = """
3.2.5 Weight. The radar shall weigh 45 kg and its centre of gravity
shall lie within the envelope shown in the interface control
drawing for all configurations of the equipment.
"""
_LONG_ROWS_BEFORE = para("3.2.3 | The radar shall operate from a 28 VDC supply as defined in MIL-STD-704F and shall "
                         "meet all of its performance requirements over the full range of normal and abnormal steady "
                         "state voltage limits without degradation of any function.")
_LONG_ROWS_AFTER = para("3.2.5 | The radar shall weigh 45 kg and its centre of gravity shall lie within the envelope "
                        "shown in the interface control drawing for all configurations of the equipment.")

# ---- the list of TAB-01's shape with the first two markers lost ------------------------------------------------
_ENV_LEAD = ["3.2.4 Environmental conditions. The equipment shall meet", "each of the following:"]
_ENV_STEM = "The equipment shall meet each of the following:"
_TWO_LOST = tab_text(_ENV_LEAD, [("", "Acceleration:", ["5 g in each of the three orthogonal axes", "for 1 minute per axis."]),
                                 ("", "Vibration:", ["20 Hz to 2000 Hz random, 0.04 g2/Hz,",
                                                     "3 hours per axis, 7.7 g rms overall."]),
                                 ("c.", "Shock:", ["40 g, 11 ms half-sine pulse,", "3 shocks in each direction."])],
                     ["", "3.2.5 Weight. The equipment shall not exceed 45 kilograms."], label=10)
_TWO_LOST_ROWS = items(_ENV_STEM,
                       f"3.2.4 a | a. Acceleration: 5 g in each of the three orthogonal axes for 1 minute per axis. [note: {_LOST}]",
                       f"3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random, 0.04 g2/Hz, 3 hours per axis, 7.7 g rms "
                       f"overall. [note: {_LOST}]",
                       "3.2.4 c | c. Shock: 40 g, 11 ms half-sine pulse, 3 shocks in each direction.") \
    + para("3.2.5 | The equipment shall not exceed 45 kilograms.")


def _suite(id_, title, situation, risk, source, tl, **kw):
    """A page of the earlier list suite, drawn exactly as it was (tab_list gives the drawing and the rows)."""
    draw, rows = tl
    return Case(id_, title, situation, risk, source, expect=rows, draw=draw, **kw)


CASES = [
    _suite("LST-01", "An ordinary tight lettered list (control)",
           "'a. Search mode.' / 'b. Track mode.' / 'c. Built-in test mode.' - a marker and one space, no tabs, no "
           "gap between items.",
           "The plainest list there is: one row per item under its lead-in. The tab-list rules must not change it.",
           "List suite p08 (control).",
           tab_list("3.8.1 Operating modes. The radar shall provide the following operating modes:",
                    "The radar shall provide the following operating modes:", "3.8.1",
                    [dict(m="a.", value=["Search mode."]), dict(m="b.", value=["Track mode."]),
                     dict(m="c.", value=["Built-in test mode."])], (0.4, None, 0.7), gap=0.0)),
    _suite("LST-02", "An ordinary tight numbered list whose last item wraps (control)",
           "'1.' to '4.' with one space after the marker, no gap between items; item 4 wraps onto a second line "
           "aligned with its text.",
           "One row per item; the wrapped line stays in item 4. The tab-list rules must not change it.",
           "List suite p08 (control).",
           tab_list("3.8.2 Display data. The display shall show the following data:",
                    "The display shall show the following data:", "3.8.2",
                    [dict(m="1.", value=["Target range to the nearest 0.1 nmi."]),
                     dict(m="2.", value=["Target bearing to the nearest 1 degree."]),
                     dict(m="3.", value=["Own-ship heading."]),
                     dict(m="4.", value=["Track quality, shown as a number from 1 to 7 for",
                                         "each track held by the radar."])], (0.4, None, 0.7), gap=0.0)),

    # ---- lost and misread markers -------------------------------------------------------------------------------
    Case("LST-03", "A lost marker: the item starts in the marker column",
         "Items a., b., d. have their markers; the third item 'Map. Ground mapping at 10 m resolution.' has lost its "
         "'c.' and starts where the markers are. A blank line between items.",
         "The neighbours b. and d. confirm the missing letter: the row is '3.2.4 c' with 'c.' put back, and Review "
         "Reasons says the marker was taken from the sequence (the letter came from the tool, not the page).",
         "Review round 2 (lists), real OCR page f8_marker_col.",
         text=_MAP_LIST.format(map="     ") + "\n" + _RADAR_WEIGHT, expect=_MAP_ROWS + para("3.2.5 | The radar shall weigh 45 kg.")),
    Case("LST-04", "A lost marker: the item starts in the text column",
         "As LST-03, but 'Map. Ground mapping ...' starts where the TEXT of the items starts (under 'Search.').",
         "As LST-03: '3.2.4 c' with a review note. The item is not joined to b. as a second line.",
         "Review round 2 (lists), real OCR page f11_text_col.",
         text=_MAP_LIST.format(map="        ") + "\n" + _RADAR_WEIGHT, expect=_MAP_ROWS + para("3.2.5 | The radar shall weigh 45 kg.")),
    Case("LST-05", "A lost marker in the marker column, between long paragraphs",
         "LST-03 with a four-line paragraph 3.2.3 above the list and a three-line paragraph 3.2.5 below it.",
         "As LST-03. The long lines around the list must not change how the list is read.",
         "Review round 2 (lists), real OCR page f8b_marker_col.",
         text=_LONG_BEFORE + "\n" + _MAP_LIST.format(map="     ").strip("\n") + "\n" + _LONG_AFTER,
         expect=_LONG_ROWS_BEFORE + _MAP_ROWS + _LONG_ROWS_AFTER),
    Case("LST-06", "A lost marker in the text column, between long paragraphs",
         "LST-04 with a four-line paragraph 3.2.3 above the list and a three-line paragraph 3.2.5 below it.",
         "As LST-04.",
         "Review round 2 (lists), real OCR page f11b_text_col.",
         text=_LONG_BEFORE + "\n" + _MAP_LIST.format(map="        ").strip("\n") + "\n" + _LONG_AFTER,
         expect=_LONG_ROWS_BEFORE + _MAP_ROWS + _LONG_ROWS_AFTER),
    Case("LST-07", "The first two markers lost in a tab list",
         "A list on tab stops whose first two items have lost their markers ('Acceleration: ...', 'Vibration: ...'); "
         "the third keeps 'c.'.",
         "The markers are counted back from 'c.': rows a and b, each with a review note, then c.",
         "Review round 2 (lists), real OCR page f10_twolost.",
         text=_TWO_LOST, expect=_TWO_LOST_ROWS),
    Case("LST-08", "The first two markers lost in a tab list, proportional font",
         "LST-07 in a proportional (serif) font.",
         "As LST-07.",
         "Review round 2 (lists), real OCR page f10_twolost_serif.",
         text=_TWO_LOST, font="serif", expect=_TWO_LOST_ROWS),
    Case("LST-09", "A figure caption between two items, and the next item's marker lost",
         "Items a. and b. on tab stops, then a figure caption 'Figure 3. Shock pulse shape.' in the middle of the "
         "list, then 'Shock: ...' without its marker, then d.",
         "The caption is a Figure Caption item of its own and does not end the list; the item after it is '3.2.4 c' "
         "(marker taken from the sequence, with a review note), and d. follows.",
         "Review round 2 (lists), real OCR page f9_caption.",
         text="""
3.2.4 Environmental conditions. The equipment shall meet
each of the following:
@gap 0.6
    a.    Acceleration:     5 g in each of the three orthogonal axes
                            for 1 minute per axis.
~
    b.    Vibration:        20 Hz to 2000 Hz random, 0.04 g2/Hz,
                            3 hours per axis, 7.7 g rms overall.

                      Figure 3. Shock pulse shape.

          Shock:            40 g, 11 ms half-sine pulse,
                            3 shocks in each direction.
~
    d.    Temperature:      -40 C to +71 C operating.

3.2.5 Weight. The equipment shall not exceed 45 kilograms.
""",
         expect=items(_ENV_STEM, "3.2.4 a | a. Acceleration: 5 g in each of the three orthogonal axes for 1 minute per axis.",
                      "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random, 0.04 g2/Hz, 3 hours per axis, 7.7 g rms overall.",
                      f"3.2.4 c | c. Shock: 40 g, 11 ms half-sine pulse, 3 shocks in each direction. [note: {_LOST}]",
                      "3.2.4 d | d. Temperature: -40 C to +71 C operating.")
         + para("3.2.5 | The equipment shall not exceed 45 kilograms."),
         captions=("FIGURE 3",)),
    Case("LST-10", "A lost marker in a single-spaced list",
         "'a.   Search mode.' / '     Track mode.' / 'c.   Ground mapping mode.' with no gap between items: the "
         "second item has lost its 'b.' and starts where a wrapped line of 'a.' would.",
         "The markers skip exactly one letter (a. then c.) and one line in a's text column starts a new sentence "
         "after a finished one: it is split off as item b, with a review note.",
         "Review round 3 (lists).",
         text=f"""
{_MODES_LEAD}
   a.   Search mode.
        Track mode.
   c.   Ground mapping mode.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_MODES, "3.2.4 a | a. Search mode.", f"3.2.4 b | b. Track mode. [note: {_LOST}]",
                      "3.2.4 c | c. Ground mapping mode.") + para("3.2.5 | The radar shall weigh less than 45 kg.")),
    Case("LST-11", "A lost marker after an item of three lines",
         "Item a. wraps onto three lines; after a blank line 'Target range and bearing.' starts in a's text column "
         "(its 'b.' lost); then c.",
         "The blank line ends item a (its sentence is finished): the next paragraph is item b with its marker "
         "taken from the sequence - not a fourth line of a (round 2: a's line spacing made the blank line look "
         "like an ordinary line gap).",
         "Review round 2, finding contstem/a4b; real OCR page para_after_long_item.",
         text="""
3.2.6 Displays. The display shall show the following items:

     a. Own ship position, heading and ground speed, updated
        at least once per second and shown in the upper left
        corner of the tactical display.

        Target range and bearing.

     c. Time to go to the next waypoint.

3.2.7 Mass. The display shall weigh less than 5 kg.
""",
         expect=items("The display shall show the following items:",
                      "3.2.6 a | a. Own ship position, heading and ground speed, updated at least once per second and "
                      "shown in the upper left corner of the tactical display.",
                      f"3.2.6 b | b. Target range and bearing. [note: {_LOST}]",
                      "3.2.6 c | c. Time to go to the next waypoint.")
         + para("3.2.7 | The display shall weigh less than 5 kg.")),
    Case("LST-12", "A marker misread as the next one ('c.', 'c.')",
         "'a. Search mode, ...' with a second sentence on its own line, then 'c. Track mode.', 'c. Ground mapping "
         "mode.', 'd. Test mode.' - the scan read 'b.' as 'c.'.",
         "Two 'c.' in a row, with d. after them: the first is a misread 'b.' (not a lost item): rows a, b (with a "
         "review note), c, d; item a keeps its second sentence.",
         "Review round 3, finding V2 (misread split); real OCR page r5_v2_misread_split.",
         text=f"""
{_MODES_LEAD}

     a. Search mode, with a scan of 120 degrees in azimuth.
        The scan rate shall be 60 degrees per second.
     c. Track mode.
     c. Ground mapping mode.
     d. Test mode.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_MODES, "3.2.4 a | a. Search mode, with a scan of 120 degrees in azimuth. The scan rate shall be "
                              "60 degrees per second.",
                      "3.2.4 b | b. Track mode. [note: List marker read as 'c.']",
                      "3.2.4 c | c. Ground mapping mode.", "3.2.4 d | d. Test mode.")
         + para("3.2.5 | The radar shall weigh less than 45 kg.")),
    Case("LST-13", "A numbered item whose second sentence starts on its own line",
         "'1. Search mode.' / '2. Track mode, holding up to twenty targets in track.' / 'Tracks shall be updated "
         "once per second.' (on its own line, in the text column) / '3. Ground mapping mode.'",
         "Item 2 keeps its second sentence and item 3 stays an item (round 3: item 3 became a section heading, was "
         "dropped from the list and became the Section of every later row). 3.2.5 has no Section.",
         "Review round 3, finding B1; real OCR page r3_numbered_second_sentence.",
         text=f"""
{_MODES_LEAD}

     1. Search mode.
     2. Track mode, holding up to twenty targets in track.
        Tracks shall be updated once per second.
     3. Ground mapping mode.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_MODES, "3.2.4 1 | 1. Search mode.",
                      "3.2.4 2 | 2. Track mode, holding up to twenty targets in track. Tracks shall be updated once "
                      "per second.", "3.2.4 3 | 3. Ground mapping mode.")
         + para("3.2.5 | The radar shall weigh less than 45 kg. [section: ]")),
    Case("LST-14", "A numbered list that skips on purpose (1, 3, 5)",
         "'The following tests of TABLE I shall be repeated after vibration:' then '1. Visual examination.', '3. "
         "Insulation resistance, ...' (three lines, the last a sentence of its own), '5. Dielectric withstanding "
         "voltage.' - the test numbers of a table.",
         "A list that counts in twos has no lost items: rows 1, 3 and 5 with their own numbers and no review note "
         "about markers; item 3 keeps all its lines.",
         "Review round 3, finding V2 (skip split); real OCR page r4_v2_skip_split.",
         text="""
4.3.2 Retest. The following tests of TABLE I shall be repeated after
vibration:

     1. Visual examination.
     3. Insulation resistance, measured at 500 VDC between each pin
        and the case.
        Readings shall be recorded on the data sheet.
     5. Dielectric withstanding voltage.

4.3.3 Records. The contractor shall keep all test records.
""",
         expect=items("The following tests of TABLE I shall be repeated after vibration:",
                      "4.3.2 1 | 1. Visual examination. [no marker note]",
                      "4.3.2 3 | 3. Insulation resistance, measured at 500 VDC between each pin and the case. Readings "
                      "shall be recorded on the data sheet. [no marker note]",
                      "4.3.2 5 | 5. Dielectric withstanding voltage. [no marker note]")
         + para("4.3.3 | The contractor shall keep all test records.")),
    Case("LST-15", "Capital letters with a small-letter list under each",
         "'A. Operating conditions:' with 'a. Temperature: ...' and 'b. Humidity: ...' indented under it, then 'B. "
         "Storage conditions:' with its own a. and b.",
         "Each level is judged on its own: A. and B. keep their capitals (they are not misread 'a.'), and the rows "
         "are 3.2.4 A.a, A.b, B.a, B.b (round 3: the capitals were lower-cased).",
         "Review round 3, finding F1; real OCR page r6_caps_with_sublists.",
         text="""
3.2.4 Environment. The unit shall meet the following conditions:

     A. Operating conditions:
         a. Temperature: -40 C to +71 C.
         b. Humidity: 95 percent, non-condensing.
     B. Storage conditions:
         a. Temperature: -55 C to +85 C.
         b. Humidity: 100 percent, condensing.

3.2.5 Weight. The unit shall weigh less than 5 kg.
""",
         expect=items("The unit shall meet the following conditions:",
                      "3.2.4 A.a | A. Operating conditions: a. Temperature: -40 C to +71 C.",
                      "3.2.4 A.b | A. Operating conditions: b. Humidity: 95 percent, non-condensing.",
                      "3.2.4 B.a | B. Storage conditions: a. Temperature: -55 C to +85 C.",
                      "3.2.4 B.b | B. Storage conditions: b. Humidity: 100 percent, condensing.")
         + para("3.2.5 | The unit shall weigh less than 5 kg.")),
    Case("LST-16", "Lettered items that wrap back to the left margin",
         "A paragraph, then a list whose items are indented but wrap back to the LEFT MARGIN ('a. Search mode, "
         "with a scan ...' / '60 degrees in elevation at all ranges.').",
         "The lines at the margin are more of their item, not new paragraphs: three whole items (round 3: the list "
         "stopped at the first line that came back to the margin and the rest was lost).",
         "Review round 3, finding F4; real OCR page r9_flushleft_lettered.",
         text=_PRE.format(n=3) + f"""
{_MODES_LEAD}
     a. Search mode, with a scan of 120 degrees in azimuth and
60 degrees in elevation at all ranges.
     b. Track mode, holding up to twenty targets in track at
the same time.
     c. Ground mapping mode.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=_PRE_ROWS(3)
         + items(_MODES, "3.2.4 a | a. Search mode, with a scan of 120 degrees in azimuth and 60 degrees in elevation "
                         "at all ranges.",
                 "3.2.4 b | b. Track mode, holding up to twenty targets in track at the same time.",
                 "3.2.4 c | c. Ground mapping mode.")
         + para("3.2.5 | The radar shall weigh less than 45 kg.")),
    Case("LST-17", "Capital-lettered items on tab stops whose value wraps back to the margin",
         "A paragraph, then 'A.  Temperature:  -40 C to +71 C when mounted in the' / 'aircraft equipment bay with "
         "forced air cooling.' (back at the margin), then B. and C.",
         "Item A keeps its whole value; B. and C. follow; the capitals are kept.",
         "Review round 3, finding F4; real OCR page r10_flushleft_caps_label.",
         text=_PRE.format(n=3) + """
3.2.4 Environment. The unit shall meet the following:
     A.  Temperature:    -40 C to +71 C when mounted in the
aircraft equipment bay with forced air cooling.
     B.  Humidity:       95 percent, non-condensing.
     C.  Altitude:       0 to 50,000 feet.

3.2.5 Weight. The unit shall weigh less than 5 kg.
""",
         expect=_PRE_ROWS(3)
         + items("The unit shall meet the following:",
                 "3.2.4 A | A. Temperature: -40 C to +71 C when mounted in the aircraft equipment bay with forced air "
                 "cooling.", "3.2.4 B | B. Humidity: 95 percent, non-condensing.",
                 "3.2.4 C | C. Altitude: 0 to 50,000 feet.")
         + para("3.2.5 | The unit shall weigh less than 5 kg.")),
    Case("LST-18", "Sub-items without markers under 'a. ... which shall include:'",
         "'a. Search mode, which shall include:' then three short lines without markers, indented a little further "
         "('Long range scan', 'Short range scan', 'Sector scan'), then b. and c.",
         "The unmarked lines are sub-items of a: three rows '3.2.4 a', each with 'a. Search mode, which shall "
         "include:' in front - not joined into one line, and not items of their own (round 1: they were run into "
         "a's text).",
         "Review round 1, finding lists/F9; review round 2, finding contstem/a18; real OCR page r09_subitems.",
         text=f"""
{_MODES_LEAD}
     a. Search mode, which shall include:
         Long range scan
         Short range scan
         Sector scan
     b. Track mode.
     c. Test mode.

{_RADAR_WEIGHT}
""",
         expect=items(_MODES, "3.2.4 a | a. Search mode, which shall include: Long range scan",
                      "3.2.4 a | a. Search mode, which shall include: Short range scan",
                      "3.2.4 a | a. Search mode, which shall include: Sector scan",
                      "3.2.4 b | b. Track mode.", "3.2.4 c | c. Test mode.")
         + para("3.2.5 | The radar shall weigh 45 kg.")),
    Case("LST-19", "A requirement sentence between items, after a sub-list",
         "'a. Search mode, which shall include:' with (1) and (2) under it, a blank line, the sentence 'The operator "
         "shall be able to select either scan at any time.' in the markers' column, a blank line, then b. and c.",
         "The sentence states a requirement of its own: it keeps its own row (with the lead-in, no letter), it is "
         "not glued to item (2), and b. and c. are still items (round 2: the sequence rule merged it into the "
         "wrong item).",
         "Review round 2, finding contstem/a6 (merge rule); real OCR page merge_rule.",
         text=f"""
{_MODES_LEAD}
     a. Search mode, which shall include:
         (1) Long range scan.
         (2) Short range scan.

     The operator shall be able to select either scan at any time.

     b. Track mode.
     c. Ground mapping mode.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_MODES, "3.2.4 a.1 | a. Search mode, which shall include: (1) Long range scan.",
                      "3.2.4 a.2 | a. Search mode, which shall include: (2) Short range scan.",
                      "3.2.4 | The operator shall be able to select either scan at any time.",
                      "3.2.4 b | b. Track mode.", "3.2.4 c | c. Ground mapping mode.")
         + para("3.2.5 | The radar shall weigh less than 45 kg.")),
    Case("LST-20", "A second lead-in inside the same paragraph",
         "'3.2.5 ... shall provide the following interfaces:' with a. and b., a blank line, then 'The unit shall "
         "also provide the following discrete signals:' with a new a., b., c.",
         "The second list belongs to its own lead-in: its rows read 'The unit shall also provide the following "
         "discrete signals: a. Weight on wheels.' and so on.",
         "Review round 2, finding contstem/a6 (merge rule); real OCR page merge_rule.",
         text="""
3.2.5 Interfaces. The unit shall provide the following interfaces:
     a. One MIL-STD-1553B bus.
     b. Two RS-422 serial ports.

     The unit shall also provide the following discrete signals:
     a. Weight on wheels.
     b. Master arm.
     c. Emergency jettison.

3.2.6 Weight. The unit shall weigh less than 5 kg.
""",
         expect=items("The unit shall provide the following interfaces:", "3.2.5 a | a. One MIL-STD-1553B bus.",
                      "3.2.5 b | b. Two RS-422 serial ports.")
         + items("The unit shall also provide the following discrete signals:", "3.2.5 a | a. Weight on wheels.",
                 "3.2.5 b | b. Master arm.", "3.2.5 c | c. Emergency jettison.")
         + para("3.2.6 | The unit shall weigh less than 5 kg."),
         known="The second lead-in is not used for the items below it: it becomes a row of its own under the first "
               "lead-in ('... the following interfaces: The unit shall also provide the following discrete "
               "signals:'), and 'Weight on wheels', 'Master arm' and 'Emergency jettison' get the first lead-in "
               "('The unit shall provide the following interfaces:') in front of them."),
    Case("LST-21", "Two requirement sentences between a. and b.",
         "'a. Search mode.', then two sentences each after a blank line, in the markers' column ('Search mode "
         "shall be selected at power-up.', 'Search mode shall cover 360 degrees in azimuth.'), then b. and c.",
         "Both sentences keep rows of their own (with the lead-in, no letter) and neither is given the letter 'b.' "
         "that the next item really carries (round 2: the first was merged into a., the second became an orphan "
         "row).",
         "Review round 2, finding contstem/a16 (merge chain); real OCR page misc1.",
         text=f"""
{_MODES_LEAD}
     a. Search mode.

     Search mode shall be selected at power-up.

     Search mode shall cover 360 degrees in azimuth.

     b. Track mode.
     c. Ground mapping mode.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_MODES, "3.2.4 a | a. Search mode.", "3.2.4 | Search mode shall be selected at power-up.",
                      "3.2.4 | Search mode shall cover 360 degrees in azimuth.", "3.2.4 b | b. Track mode.",
                      "3.2.4 c | c. Ground mapping mode.")
         + para("3.2.5 | The radar shall weigh less than 45 kg.")),
    Case("LST-22", "A NOTE between two items of a tab list",
         "'a. Voltage: ...', 'b. Ripple: ...', then 'NOTE: The limits apply at the equipment connector.' in the "
         "markers' column, then 'c. Power: ...'.",
         "The NOTE is never given a letter: it keeps a row of its own (with the lead-in), and the next item is "
         "still '3.2.10 c' (round 2: the NOTE was made item c and the real c. got a duplicate letter).",
         "Review round 2, finding numbering/F3; real OCR page r3_swallow.",
         text="""
3.2.10 Power. The equipment shall operate within the
following limits:
@gap 0.6
    a.    Voltage:          24 to 32 VDC, 28 VDC nominal.
~
    b.    Ripple:           1.5 V peak-to-peak maximum.
~
    NOTE: The limits apply at the equipment connector.
~
    c.    Power:            150 W maximum at 28 VDC.

3.3 Design and construction. The equipment shall be modular.
""",
         expect=items("The equipment shall operate within the following limits:",
                      "3.2.10 a | a. Voltage: 24 to 32 VDC, 28 VDC nominal.",
                      "3.2.10 b | b. Ripple: 1.5 V peak-to-peak maximum.",
                      "3.2.10 | NOTE: The limits apply at the equipment connector.",
                      "3.2.10 c | c. Power: 150 W maximum at 28 VDC.")
         + para("3.3 | The equipment shall be modular.")),
    Case("LST-23", "A capital 'C.' printed in a small-letter list",
         "'a. MIL-STD-461G', 'b. MIL-STD-704F', 'C. MIL-STD-810H', 'd. MIL-STD-1275E' - the page itself has 'C.' "
         "(the same thing the scan often does to a lone 'c.').",
         "The a, b, ?, d sequence says it is c: the row is '3.2.7 c' and Review Reasons says the marker was read as "
         "'C.'.",
         "Review round 2 (layout, f2_upperC).",
         text="""
3.2.7 Documents. The unit shall comply with each of the following:
        a. MIL-STD-461G
        b. MIL-STD-704F
        C. MIL-STD-810H
        d. MIL-STD-1275E

3.2.8 Weight. The unit shall not exceed 45 kilograms.
""",
         expect=items("The unit shall comply with each of the following:", "3.2.7 a | a. MIL-STD-461G",
                      "3.2.7 b | b. MIL-STD-704F", "3.2.7 c | c. MIL-STD-810H [note: List marker read as 'C.']",
                      "3.2.7 d | d. MIL-STD-1275E")
         + para("3.2.8 | The unit shall not exceed 45 kilograms.")),
    Case("LST-24", "The last item's marker lost in a single-spaced list",
         "'a.   Search mode.' / 'b.   Track mode.' / '     Ground mapping mode.' - the last item has lost its "
         "'c.' and starts where a wrapped line of b. would; nothing follows it in the list.",
         "Ideally item c, with a review note - or at least a review note on b.",
         "Review round 3 (lists), known limitation.",
         text=f"""
{_MODES_LEAD}
   a.   Search mode.
   b.   Track mode.
        Ground mapping mode.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_MODES, "3.2.4 a | a. Search mode.", "3.2.4 b | b. Track mode.",
                      f"3.2.4 c | c. Ground mapping mode. [note: {_LOST}]")
         + para("3.2.5 | The radar shall weigh less than 45 kg."),
         known="No marker after the gap confirms the sequence, so the line is read as the second line of item b "
               "('b. Track mode. Ground mapping mode.'), and nothing is flagged. A lost marker in the middle of a "
               "list is found (LST-10)."),
    Case("LST-25", "Lettered items without full stops, then a paragraph",
         "'a. Search mode' / 'b. Track mode' (no full stops), a blank line, then 'The operator shall select the "
         "mode from the front panel.' in the items' text column.",
         "The paragraph is a requirement of its own (with the lead-in, no letter), not more of item b.",
         "Review round 3, finding B3; still wrong when the case library was written, fixed with it.",
         text=f"""
{_MODES_LEAD}
     a. Search mode
     b. Track mode

        The operator shall select the mode from the front panel.

3.2.5 Weight. The radar shall weigh less than 45 kg.
""",
         expect=items(_MODES, "3.2.4 a | a. Search mode", "3.2.4 b | b. Track mode",
                      "3.2.4 | The operator shall select the mode from the front panel.")
         + para("3.2.5 | The radar shall weigh less than 45 kg.")),
]
