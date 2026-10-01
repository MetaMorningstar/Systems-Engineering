"""
Lists on wide tab stops: a marker, a large tab, a label ("Acceleration:"), another large tab, then a value
that may run over several lines, its continuation lines aligned under the value column.

TAB-01 to TAB-20 are the pages of the earlier 'list suite', kept exactly as they were drawn (their Doc Ref
and Content convention is the tool's: '<paragraph number> <marker>' and '<lead-in> <marker> <label> <value>').
The later cases come from the adversarial reviews of the tab-list rules.
"""
from casekit import Case, gap, items, line, para, paragraph, tab_list, tab_text

AREA = "Lists on tab stops"

_OCR_C = ("The OCR tends to read the lone marker 'c.' as 'C.'; the Doc Ref must still be '<para> c', because "
          "the a, b, ?, d sequence says it is c.")
_OCR_BULLET = ("The OCR returns no glyph at all for a bullet that stands alone, so these items have no visible "
               "marker and must be found from their label column under the lead-in.")


def _suite(id_, title, situation, risk, source, tl, **kw):
    draw, rows = tl
    return Case(id_, title, situation, risk, source, expect=rows, draw=draw, **kw)


_ENV = [dict(m="a.", label=["Acceleration:"], value=["5 g in each of the three orthogonal axes", "for 1 minute per axis."]),
        dict(m="b.", label=["Vibration:"], value=["20 Hz to 2000 Hz random, 0.04 g2/Hz,", "3 hours per axis, 7.7 g rms overall."]),
        dict(m="c.", label=["Shock:"], value=["40 g, 11 ms half-sine pulse,", "3 shocks in each direction."]),
        dict(m="d.", label=["Temperature:"], value=["-40 C to +71 C operating,", "2.5 C per minute maximum rate of change."])]
_ELEC = [dict(m="1.", label=["Input voltage:"], value=["24 to 32 VDC, 28 VDC nominal."]),
         dict(m="2.", label=["Ripple:"], value=["1.5 V peak-to-peak maximum,", "10 Hz to 50 kHz."]),
         dict(m="3.", label=["Current:"], value=["3.2 A continuous, 4.0 A peak."]),
         dict(m="4.", label=["Power:"], value=["150 W maximum at 28 VDC."])]
_ENV_LIST = ("3.2.4 Environmental conditions. The equipment shall meet each of the following:",
             "The equipment shall meet each of the following:", "3.2.4", _ENV, (0.4, 0.9, 2.6))
_ELEC_LIST = ("3.2.5 Electrical conditions. The equipment shall operate within the following limits.",
              "The equipment shall operate within the following limits.", "3.2.5", _ELEC, (0.4, 0.9, 2.6))
_ELEC_AFTER = dict(after=[gap(0.6), paragraph("3.2.6 Weight. The equipment shall not exceed 45 kilograms.")],
                   after_rows=para("3.2.6 | The equipment shall not exceed 45 kilograms."))

# ---- shared pages for the text-layout cases ----------------------------------------------------------------------
_STEM = ["3.2.4 Environmental conditions. The equipment shall meet", "each of the following:"]
_STEM_S = "The equipment shall meet each of the following:"
_AFTER = "3.2.5 Weight. The equipment shall not exceed 45 kilograms."
_BASE = [("a.", "Acceleration:", ["5 g in each of the three orthogonal axes", "for 1 minute per axis."]),
         ("b.", "Vibration:", ["20 Hz to 2000 Hz random, 0.04 g2/Hz,", "3 hours per axis, 7.7 g rms overall."]),
         ("c.", "Shock:", ["40 g, 11 ms half-sine pulse,", "3 shocks in each direction."]),
         ("d.", "Temperature:", ["-40 C to +71 C operating."])]
_BASE_NARROW = [("a.", "Acceleration:", ["5 g in each of the three orthogonal", "axes for 1 minute per axis."])] + _BASE[1:]
_BASE_SPECS = ["3.2.4 a | a. Acceleration: 5 g in each of the three orthogonal axes for 1 minute per axis.",
               "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random, 0.04 g2/Hz, 3 hours per axis, 7.7 g rms overall.",
               "3.2.4 c | c. Shock: 40 g, 11 ms half-sine pulse, 3 shocks in each direction.",
               "3.2.4 d | d. Temperature: -40 C to +71 C operating."]
_BASE_ROWS = items(_STEM_S, *_BASE_SPECS)
_WEIGHT = para("3.2.5 | The equipment shall not exceed 45 kilograms.")
_LOWER = [("a.", "Input voltage:", ["within 22 to 29 VDC"]), ("b.", "Ripple:", ["less than 1 V peak to peak"]),
          ("c.", "Power:", ["not more than 150 W"]), ("d.", "Transients:", ["per MIL-STD-704F"])]
_COMMA = [("a.", "Voltage:", ["within 22 to 29 VDC,"]), ("b.", "Ripple:", ["less than 1 V peak to peak,"]),
          ("c.", "Power:", ["not more than 150 W, and"]), ("d.", "Transients:", ["per MIL-STD-704F."])]
_COMMA_ROWS = items("The unit shall operate with an input:", "3.2.6 a | a. Voltage: within 22 to 29 VDC,",
                    "3.2.6 b | b. Ripple: less than 1 V peak to peak,", "3.2.6 c | c. Power: not more than 150 W, and",
                    "3.2.6 d | d. Transients: per MIL-STD-704F.") + para("3.2.7 | The unit shall weigh less than 5 kg.")
_WRAPPED = [("a.", ["Storage", "temperature:"], ["-55 C to +85 C for", "up to 5 years."]),
            ("b.", ["Operating", "temperature:"], ["-40 C to +71 C."]),
            ("c.", "Humidity:", ["95 percent non-condensing."]), ("d.", "Altitude:", ["sea level to 15,000 m."])]
_WRAPPED_ROWS = items(_STEM_S, "3.2.4 a | a. Storage temperature: -55 C to +85 C for up to 5 years.",
                      "3.2.4 b | b. Operating temperature: -40 C to +71 C.",
                      "3.2.4 c | c. Humidity: 95 percent non-condensing.",
                      "3.2.4 d | d. Altitude: sea level to 15,000 m.") + _WEIGHT
_WRAP_BACK = """
3.2.4 Environment. The equipment shall meet each of the following:
~
    a.   Operating temperature:   -40 C to +71 C with the unit powered
         and cooling air supplied at the rate given in Figure 3.
~
    b.   Storage temperature:     -55 C to +85 C for up to 5 years in
         the original shipping container.
~
    c.   Altitude:                Sea level to 15 000 m.

3.2.5 Weight. The equipment shall not exceed 45 kilograms.
"""
_WRAP_BACK_ROWS = items(_STEM_S, "3.2.4 a | a. Operating temperature: -40 C to +71 C with the unit powered and cooling "
                                 "air supplied at the rate given in Figure 3.",
                        "3.2.4 b | b. Storage temperature: -55 C to +85 C for up to 5 years in the original shipping "
                        "container.",
                        "3.2.4 c | c. Altitude: Sea level to 15 000 m.") + _WEIGHT
_NOTE_INSIDE = """
3.2.4 Environmental conditions. The equipment shall meet
each of the following:
~
    a.    Acceleration:     5 g in each of the three axes.
          Note: The unit shall be powered during this test.
~
    b.    Vibration:        20 Hz to 2000 Hz random.
~
    c.    Shock:            40 g, 11 ms half-sine.

3.2.5 Weight. The equipment shall not exceed 45 kilograms.
"""
_NOTE_INSIDE_ROWS = items(_STEM_S, "3.2.4 a | a. Acceleration: 5 g in each of the three axes. Note: The unit shall be "
                                   "powered during this test.",
                          "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random.",
                          "3.2.4 c | c. Shock: 40 g, 11 ms half-sine.") + _WEIGHT
_DOUBLE_SPACED = """
3.2.3 Power. The unit shall operate from 28 VDC and shall draw

no more than 150 W in any mode. The input shall meet each of

the following:

    a.     Acceleration:    5 g in each of the three orthogonal axes

                            for 1 minute per axis.

    b.     Vibration:       20 Hz to 2000 Hz random, 0.04 g2/Hz,

                            3 hours per axis, 7.7 g rms overall.

    c.     Shock:           40 g, 11 ms half-sine pulse,

                            3 shocks in each direction.

    d.     Temperature:     -40 C to +71 C operating.

The unit shall return to normal operation within 50 ms after any

transient.


3.2.5 Weight. The equipment shall not exceed 45 kilograms.
"""


CASES = [
    _suite("TAB-01", "Letters, labels and two-line values on wide tab stops",
           "a. / b. / c. / d. at 0.4 in, a label ('Acceleration:') at 0.9 in and a value at 2.6 in - tabs of about "
           "0.4 and 1 inch. Every value has two lines that start with numbers ('5 g', '20 Hz', '40 g', '-40 C', "
           "'2.5 C per minute'); the lead-in ends 'each of the following:'; half a line between items.",
           "Each item is ONE row with its marker, its label and its whole value, joined to the lead-in. The wide "
           "tabs are not the gutter between two text columns, the list is not a table, and a value line that "
           "starts with a number is not a new paragraph. " + _OCR_C,
           "The user's report (the layout that started the tab-list work); list suite p01.",
           tab_list(*_ENV_LIST, gap=0.5)),
    _suite("TAB-02", "Numbered list under a lead-in without a colon, then the next paragraph",
           "1. to 4. on tab stops; the lead-in ends '... within the following limits.' (no colon); value lines "
           "start with '24 to', '1.5 V peak-to-peak', '3.2 A continuous', '150 W'; paragraph 3.2.6 follows.",
           "A lead-in phrase ('the following limits.') leads into the list even without a colon; the values that "
           "start with '1.5' or '3.2' do not start new sections; 3.2.6 is a paragraph of its own.",
           "List suite p01.", tab_list(*_ELEC_LIST, gap=0.5, **_ELEC_AFTER)),
    _suite("TAB-03", "(a)-(d), labels without colons, very large tab, blank lines between items",
           "(a)-(d) at 0.4 in, labels WITHOUT ':' at 1.0 in, values at 3.2 in (a tab of 1.4-2 inches); lead-in "
           "'as follows:'; a full blank line between items; values start with '9.3 GHz', '25 kW', '0.5 us', "
           "'0.1 percent'.",
           "Each item one row; the blank lines between items do not end the list.",
           "List suite p02.",
           tab_list("3.3.1 Transmitter. The transmitter output shall be as follows:",
                    "The transmitter output shall be as follows:", "3.3.1",
                    [dict(m="(a)", label=["Frequency"], value=["9.3 GHz to 9.5 GHz, tunable", "in 10 MHz steps."]),
                     dict(m="(b)", label=["Peak power"], value=["25 kW minimum."]),
                     dict(m="(c)", label=["Pulse width"], value=["0.5 us, 1.0 us or 2.0 us,", "selectable by the operator."]),
                     dict(m="(d)", label=["Duty cycle"], value=["0.1 percent maximum."])], (0.4, 1.0, 3.2), gap=1.0)),
    _suite("TAB-04", "(1)-(4) with small tabs and no gap between items",
           "(1)-(4) at 0.4 in, labels at 0.8 in (a small tab after the marker), values at 2.3 in (only 2-4 "
           "characters after the longest label); lead-in 'as specified below.' (no colon); no gap between items.",
           "Each item one row even though the tabs are small and the items are single-spaced.",
           "List suite p02.",
           tab_list("3.3.2 Receiver. The receiver shall have the characteristics as specified below.",
                    "The receiver shall have the characteristics as specified below.", "3.3.2",
                    [dict(m="(1)", label=["Noise figure:"], value=["3.5 dB maximum."]),
                     dict(m="(2)", label=["Sensitivity:"], value=["-110 dBm minimum for 10 dB", "signal-to-noise ratio."]),
                     dict(m="(3)", label=["Bandwidth:"], value=["1.2 MHz between 3 dB points."]),
                     dict(m="(4)", label=["Dynamic range:"], value=["70 dB minimum."])], (0.4, 0.8, 2.3), gap=0.0)),
    _suite("TAB-05", "1) to 4) markers, lead-in ending 'the following.'",
           "1)-4) at 0.4 in, labels at 0.9 in, values at 2.6 in; lead-in ends 'the following.' (no colon); value "
           "lines start with '32 dBi', '2.5 degrees', '-25 dB', '1.5:1'; paragraph 3.3.4 follows.",
           "Each item one row; 3.3.4 is a paragraph of its own.",
           "List suite p02.",
           tab_list("3.3.3 Antenna. The antenna shall conform to the following.",
                    "The antenna shall conform to the following.", "3.3.3",
                    [dict(m="1)", label=["Gain:"], value=["32 dBi minimum at 9.4 GHz."]),
                     dict(m="2)", label=["Beamwidth:"], value=["2.5 degrees maximum in both", "azimuth and elevation."]),
                     dict(m="3)", label=["Sidelobes:"], value=["-25 dB maximum relative to", "the main beam peak."]),
                     dict(m="4)", label=["VSWR:"], value=["1.5:1 maximum over the band."])], (0.4, 0.9, 2.6), gap=0.5,
                    after=[gap(0.6), paragraph("3.3.4 Radome. The radome shall not reduce antenna gain by more than 1 dB.")],
                    after_rows=para("3.3.4 | The radome shall not reduce antenna gain by more than 1 dB."))),
    _suite("TAB-06", "Roman numerals i. to iv.",
           "i./ii./iii./iv. at 0.4 in, labels at 1.0 in, values at 2.8 in; lead-in 'the following.' (no colon); "
           "two-line values.",
           "Roman markers count i, ii, iii, iv - 'i.' is not the ninth letter here.",
           "List suite p03.",
           tab_list("3.4.1 Built-in test. The BIT function shall perform the following.",
                    "The BIT function shall perform the following.", "3.4.1",
                    [dict(m="i.", label=["Power-up:"], value=["Full test at power-on, completed", "within 30 seconds."]),
                     dict(m="ii.", label=["Periodic:"], value=["Non-interfering test every", "60 seconds in operation."]),
                     dict(m="iii.", label=["Initiated:"], value=["Full test started by the operator."]),
                     dict(m="iv.", label=["Isolation:"], value=["To one LRU with 95 percent",
                                                                 "probability of correct isolation."])],
                    (0.4, 1.0, 2.8), gap=0.5)),
    _suite("TAB-07", "Roman numerals in brackets (i) to (iii)",
           "(i)/(ii)/(iii) at 0.4 in, labels at 1.0 in, values at 2.6 in; the lead-in ends ':'.",
           "Each item one row, Doc Refs '3.4.2 i', '3.4.2 ii', '3.4.2 iii'.",
           "List suite p03.",
           tab_list("3.4.2 Status reporting. The equipment shall report the following status data:",
                    "The equipment shall report the following status data:", "3.4.2",
                    [dict(m="(i)", label=["Mode:"], value=["Current operating mode."]),
                     dict(m="(ii)", label=["Faults:"], value=["Active faults with time tags", "to the nearest 1 second."]),
                     dict(m="(iii)", label=["Hours:"], value=["Elapsed operating hours."])], (0.4, 1.0, 2.6), gap=0.5)),
    _suite("TAB-08", "Capital letters A. to D., then a sub-paragraph 3.4.3.1",
           "A./B./C./D. at 0.4 in, labels at 1.0 in, values at 3.0 in; the lead-in 'within the following limits:' "
           "wraps over two lines; values start with '2.5 kg/min', '15 C', '1.2 kPa', '5 to 95'; the child "
           "paragraph 3.4.3.1 follows.",
           "A list lettered in capitals keeps its capitals ('3.4.3 A' ... '3.4.3 D'); 3.4.3.1 (a valid next number "
           "after 3.4.3) is a paragraph of its own.",
           "List suite p03.",
           tab_list("3.4.3 Cooling. The cooling air supplied to the equipment shall be within the following limits:",
                    "The cooling air supplied to the equipment shall be within the following limits:", "3.4.3",
                    [dict(m="A.", label=["Flow rate:"], value=["2.5 kg/min minimum."]),
                     dict(m="B.", label=["Inlet temperature:"], value=["15 C to 35 C."]),
                     dict(m="C.", label=["Pressure drop:"], value=["1.2 kPa maximum at", "the rated flow."]),
                     dict(m="D.", label=["Humidity:"], value=["5 to 95 percent, non-condensing."])], (0.4, 1.0, 3.0),
                    gap=0.5, after=[gap(0.6), paragraph("3.4.3.1 Coolant. The coolant shall be dry, filtered air.")],
                    after_rows=para("3.4.3.1 | The coolant shall be dry, filtered air."))),
    _suite("TAB-09", "Bullets with upper-case labels",
           "Bullets at 0.4 in, upper-case labels ('POWER:') at 0.8 in, values at 2.4 in; the lead-in ends ':'.",
           "Bullet items have no marker reference: every row has Doc Ref '3.5.1'. " + _OCR_BULLET,
           "List suite p04.",
           tab_list("3.5.1 Indicators. The front panel shall provide the following indicators:",
                    "The front panel shall provide the following indicators:", "3.5.1",
                    [dict(m="•", label=["POWER:"], value=["Green, lit when primary", "power is applied."]),
                     dict(m="•", label=["FAULT:"], value=["Red, lit when BIT detects a fault."]),
                     dict(m="•", label=["STANDBY:"], value=["Amber, lit in standby mode."])], (0.4, 0.8, 2.4), gap=0.5)),
    _suite("TAB-10", "No label column: markers and values of one to four lines",
           "a.-d. at 0.4 in, no label, values at 1.2 in (a large tab); values of 2, 1, 4 and 2 lines; continuation "
           "lines start with '10 Mbit/s' and 'system time.'; item c holds a second 'shall' sentence.",
           "Each item one row with its whole value, whatever its continuation lines start with.",
           "List suite p04.",
           tab_list("3.5.2 Data recording. The recorder shall meet each of the following:",
                    "The recorder shall meet each of the following:", "3.5.2",
                    [dict(m="a.", value=["Record all bus traffic at data rates up to", "10 Mbit/s without loss of data."]),
                     dict(m="b.", value=["Store not less than 8 hours of data."]),
                     dict(m="c.", value=["Time-tag each message to within 1 ms of", "system time. Time tags shall be derived",
                                         "from the GPS time source when available", "and from the internal clock otherwise."]),
                     dict(m="d.", value=["Retain recorded data for 30 days", "without external power."])],
                    (0.4, None, 1.2), gap=0.5)),
    _suite("TAB-11", "A label that wraps onto a second line beside its value",
           "a.-c. at 0.4 in; the label at 0.9 in wraps ('Storage' / 'temperature:') beside a two-line value at "
           "2.6 in; paragraph 3.5.4 follows.",
           "The label is read first, then the value: 'a. Storage temperature: -55 C to +85 C for up to 5 years.' - "
           "not 'Storage -55 C to +85 C for temperature: up to 5 years.'",
           "List suite p04.",
           tab_list("3.5.3 Storage. The equipment shall not be damaged by storage in the following conditions:",
                    "The equipment shall not be damaged by storage in the following conditions:", "3.5.3",
                    [dict(m="a.", label=["Storage", "temperature:"], value=["-55 C to +85 C for", "up to 5 years."]),
                     dict(m="b.", label=["Relative", "humidity:"], value=["Up to 100 percent,", "including condensation."]),
                     dict(m="c.", label=["Altitude:"], value=["Up to 12,200 m (40,000 ft)."])], (0.4, 0.9, 2.6), gap=0.5,
                    after=[gap(0.6), paragraph("3.5.4 Transport. The packaged equipment shall withstand transport by "
                                               "road, rail, sea and air.")],
                    after_rows=para("3.5.4 | The packaged equipment shall withstand transport by road, rail, sea and air."))),
    _suite("TAB-12", "A nested (1)/(2) list under an item that has no value",
           "a./b./c. on tab stops; item b. 'Random:' has no value of its own and a nested (1)/(2) list under its "
           "label (markers 0.9 in, labels 1.4 in, values 3.0 in).",
           "The sub-items are filed under b: '3.6.1 b.1' and '3.6.1 b.2', each with 'b. Random:' in front.",
           "List suite p05.",
           tab_list("3.6.1 Vibration. The equipment shall withstand the following vibration environments:",
                    "The equipment shall withstand the following vibration environments:", "3.6.1",
                    [dict(m="a.", label=["Sinusoidal:"], value=["5 Hz to 500 Hz, 2 g peak,", "1 octave per minute."]),
                     dict(m="b.", label=["Random:"], sub_xs=(0.9, 1.4, 3.0), sub_gap=0.5,
                          sub=[dict(m="(1)", label=["Functional:"], value=["20 Hz to 2000 Hz, 0.04 g2/Hz,", "1 hour per axis."]),
                               dict(m="(2)", label=["Endurance:"], value=["20 Hz to 2000 Hz, 0.1 g2/Hz,", "3 hours per axis."])]),
                     dict(m="c.", label=["Transport:"], value=["As specified in MIL-STD-810H,", "Method 514.8, Procedure II."])],
                    (0.4, 0.9, 2.6), gap=0.5)),
    _suite("TAB-13", "Decimal values that look like paragraph numbers, then an all-capitals heading 4.",
           "1./2./3. on tab stops, no gap between items; every value line starts with a decimal and a capital unit "
           "('9.0 G', '2.5 G', '3.2 G'); the first value line ends with '.' and the next starts with a number; then "
           "the heading '4. QUALITY ASSURANCE PROVISIONS' (4 would continue 1, 2, 3!) and paragraph 4.1.",
           "'2.5 G sustained thereafter.' stays in its item (it is not paragraph 2.5); '4. QUALITY ASSURANCE "
           "PROVISIONS' is a heading, not item 4; 4.1 is a paragraph.",
           "List suite p05.",
           tab_list("3.6.2 Crash safety. The equipment shall remain attached to its mounting under the following loads:",
                    "The equipment shall remain attached to its mounting under the following loads:", "3.6.2",
                    [dict(m="1.", label=["Forward:"], value=["9.0 G for 3 seconds.", "2.5 G sustained thereafter."]),
                     dict(m="2.", label=["Lateral:"], value=["3.0 G in either direction.", "1.5 G sustained thereafter."]),
                     dict(m="3.", label=["Vertical:"], value=["6.0 G down and 2.0 G up.", "3.2 G down sustained."])],
                    (0.4, 0.9, 2.6), gap=0.0,
                    after=[gap(1.2), line(0, "4. QUALITY ASSURANCE PROVISIONS"), gap(0.6),
                           paragraph("4.1 Responsibility for inspection. The contractor shall be responsible for the "
                                     "performance of all inspection requirements.")],
                    after_rows=para("4.1 | The contractor shall be responsible for the performance of all inspection "
                                    "requirements."))),
    _suite("TAB-14", "Proportional font, markers at the margin, three-line value",
           "Serif, 200 dpi. a.-d. at the LEFT MARGIN, labels at 0.5 in, values at 2.2 in; the lead-in ':' wraps over "
           "two lines; item a. has a three-line value whose lines start '-40 C', '-55 C', '5 C per minute'.",
           "Each item one row with its whole value. " + _OCR_C,
           "List suite p06.",
           tab_list("3.7.1 Environmental conditions. The equipment shall meet all performance requirements when "
                    "exposed to each of the following environments:",
                    "The equipment shall meet all performance requirements when exposed to each of the following "
                    "environments:", "3.7.1",
                    [dict(m="a.", label=["Temperature:"], value=["-40 C to +71 C operating,", "-55 C to +85 C non-operating,",
                                                                  "5 C per minute maximum rate of change."]),
                     dict(m="b.", label=["Altitude:"], value=["Sea level to 15,000 m."]),
                     dict(m="c.", label=["Humidity:"], value=["95 percent relative humidity for 10 days,",
                                                               "including condensation."]),
                     dict(m="d.", label=["Salt fog:"], value=["48 hours exposure, 5 percent solution."])],
                    (0.0, 0.5, 2.2), gap=0.5),
           font="serif", pt=12, dpi=200),
    _suite("TAB-15", "Proportional font, numbered list, wrapped lead-in without a colon",
           "Serif, 200 dpi. 1.-4. at 0.3 in, labels at 0.7 in, values at 2.2 in; the lead-in '... within the "
           "following limits.' wraps over two lines; a value line ending '.' is followed by one starting '4.5 A'; "
           "paragraph 3.7.3 follows.",
           "Each item one row; '4.5 A peak' is not paragraph 4.5. The OCR does not return the lone marker '4.' of "
           "'Inrush' at all: the Doc Ref '3.7.2 4' can only come from the 1, 2, 3 sequence and the label column.",
           "List suite p06.",
           tab_list("3.7.2 Electrical interface. The equipment shall accept primary power from the aircraft bus "
                    "within the following limits.",
                    "The equipment shall accept primary power from the aircraft bus within the following limits.", "3.7.2",
                    [dict(m="1.", label=["Voltage:"], value=["22 VDC to 29 VDC,", "28 VDC nominal."]),
                     dict(m="2.", label=["Ripple:"], value=["1.5 V peak-to-peak maximum."]),
                     dict(m="3.", label=["Current:"], value=["3.2 A continuous.", "4.5 A peak for 100 ms."]),
                     dict(m="4.", label=["Inrush:"], value=["12 A for 10 ms maximum."])], (0.3, 0.7, 2.2), gap=0.5,
                    after=[gap(0.6), paragraph("3.7.3 Grounding. The equipment case shall be bonded to structure with a "
                                               "resistance not exceeding 2.5 milliohms.")],
                    after_rows=para("3.7.3 | The equipment case shall be bonded to structure with a resistance not "
                                    "exceeding 2.5 milliohms.")),
           font="serif", pt=12, dpi=200),
    _suite("TAB-16", "Proportional font, (a)-(c), a four-line value with numbers inside",
           "Serif, 200 dpi. (a)-(c) on tab stops; lead-in 'within the following limits.' (no colon); item (b) has a "
           "four-line value whose second line ends with '.' and whose third and fourth lines start '3.0 kg/min' "
           "and '3,000 m'.",
           "(b) is one row with all four value lines.",
           "List suite p07.",
           tab_list("3.7.4 Cooling air. The equipment shall operate with cooling air within the following limits.",
                    "The equipment shall operate with cooling air within the following limits.", "3.7.4",
                    [dict(m="(a)", label=["Temperature:"], value=["15 C to 35 C at the inlet."]),
                     dict(m="(b)", label=["Flow:"], value=["2.5 kg/min minimum per kW of", "dissipated power at sea level.",
                                                            "3.0 kg/min per kW above", "3,000 m altitude."]),
                     dict(m="(c)", label=["Pressure:"], value=["1.2 kPa maximum drop across", "the equipment at rated flow."])],
                    (0.4, 0.9, 2.4), gap=0.5),
           font="serif", pt=12, dpi=200),
    _suite("TAB-17", "Proportional font, every label wraps onto two lines",
           "Serif, 200 dpi. a.-c.; two-line labels ('Maximum' / 'weight:') at 0.9 in beside two-line values at "
           "2.4 in; the lead-in ends ':'.",
           "Each item reads label first, then value: 'a. Maximum weight: 12.5 kg including the mounting tray.'",
           "List suite p07.",
           tab_list("3.7.5 Mechanical. The equipment shall meet the following:",
                    "The equipment shall meet the following:", "3.7.5",
                    [dict(m="a.", label=["Maximum", "weight:"], value=["12.5 kg including the", "mounting tray."]),
                     dict(m="b.", label=["Envelope", "dimensions:"], value=["300 mm x 200 mm x 150 mm",
                                                                             "maximum, excluding connectors."]),
                     dict(m="c.", label=["Center of", "gravity:"], value=["Within 25 mm of the", "geometric center."])],
                    (0.4, 0.9, 2.4), gap=0.5),
           font="serif", pt=12, dpi=200),
    _suite("TAB-18", "Proportional font, bullets, then the next paragraph",
           "Serif, 200 dpi. Bullets at 0.4 in, labels at 0.7 in, values at 2.2 in; the lead-in ends ':'; "
           "paragraph 3.7.7 follows.",
           "Bullet items: every row has Doc Ref '3.7.6'. " + _OCR_BULLET,
           "List suite p07.",
           tab_list("3.7.6 Connectors. The equipment shall use the following connectors:",
                    "The equipment shall use the following connectors:", "3.7.6",
                    [dict(m="•", label=["Power (J1):"], value=["MIL-DTL-38999 Series III, size 13."]),
                     dict(m="•", label=["Data (J2):"], value=["MIL-DTL-38999 Series III, size 15."]),
                     dict(m="•", label=["RF (J3):"], value=["TNC, 50 ohm."])], (0.4, 0.7, 2.2), gap=0.5,
                    after=[gap(0.6), paragraph("3.7.7 Bonding. Each connector shall be bonded to the equipment case.")],
                    after_rows=para("3.7.7 | Each connector shall be bonded to the equipment case.")),
           font="serif", pt=12, dpi=200),
    _suite("TAB-19", "TAB-01 on a photocopy",
           "The page of TAB-01 run through photocopier-style damage: faded ink, speckle, a 1.3 degree skew, punch "
           "holes.",
           "The same rows as TAB-01.",
           "List suite p10.", tab_list(*_ENV_LIST, gap=0.5), copy="photocopy"),
    _suite("TAB-20", "TAB-02 on a photocopy",
           "The page of TAB-02 run through photocopier-style damage: faded ink, speckle, a 1.3 degree skew, punch "
           "holes.",
           "The same rows as TAB-02.",
           "List suite p10.", tab_list(*_ELEC_LIST, gap=0.5, **_ELEC_AFTER), copy="photocopy"),

    # ---- from the adversarial reviews of the tab-list rules (rounds 1 to 3) -----------------------------------------
    Case("TAB-21", "A NOTE right under the list",
         "The list of TAB-01's shape (values on tab stops), then, after a blank line, 'NOTE: Values apply at 25 C.' at "
         "the margin, then paragraph 3.2.5.",
         "The NOTE sits in the same band of the page as the list, but it is not part of the list: it must not make "
         "the tab look like the gutter between two text columns (round 2: the values were lost, or all given to "
         "the last item). The NOTE has no 'shall', so it is not a row.",
         "Review round 2, finding layout/F1.",
         text=tab_text(_STEM, _BASE, ["", "NOTE: Values apply at 25 C.", "", _AFTER]),
         expect=_BASE_ROWS + _WEIGHT),
    Case("TAB-22", "A heading right under the list",
         "The list, then the heading '3.2.5 Size, weight and finish.' and its first paragraph 3.2.5.1.",
         "The heading does not cut the list into columns and does not become an item; 3.2.5.1 is a paragraph.",
         "Review round 2, finding layout/F1.",
         text=tab_text(_STEM, _BASE_NARROW, ["", "3.2.5 Size, weight and finish.", "",
                                             "3.2.5.1 Weight. The equipment shall not exceed 45 kilograms in any",
                                             "configuration."], value=32),
         expect=_BASE_ROWS + para("3.2.5.1 | The equipment shall not exceed 45 kilograms in any configuration.")),
    Case("TAB-23", "The lead-in's last line sits beside the markers and labels",
         "A two-line lead-in whose second line, 'to meet each of the following:' (six words), ends just before the "
         "value column, so it sits in the same band as the markers and labels of the list below it.",
         "The lead-in's tail is part of the lead-in, not a label of the list, and it must not make the list look like "
         "two columns of text.",
         "Review round 2, finding layout/F1.",
         text=tab_text(["3.2.4 Environmental conditions. The equipment shall be designed",
                        "to meet each of the following:"], _BASE_NARROW, ["", _AFTER], value=32),
         expect=items("The equipment shall be designed to meet each of the following:", *_BASE_SPECS)
         + _WEIGHT),
    Case("TAB-24", "One label of five words in a six-item list",
         "Six items; one label is 'Peak inrush current (cold):' (five words with the marker).",
         "A long label is still a label: the list is not cut into columns (round 2: the five-word row made the "
         "whole band look like running text, and every value was given to the last item).",
         "Review round 2, finding layout/F1.",
         text=tab_text("3.2.6 Input power. The unit shall meet the following:",
                       [("a.", "Input voltage:", ["22 to 29 VDC."]), ("b.", "Ripple:", ["1 V peak to peak maximum."]),
                        ("c.", "Peak inrush current (cold):", ["20 A for 10 ms maximum."]),
                        ("d.", "Power:", ["150 W maximum."]), ("e.", "Transients:", ["as in MIL-STD-704F."]),
                        ("f.", "Hold-up:", ["50 ms after loss of input."])],
                       ["", "3.2.7 Weight. The unit shall weigh less than 5 kg."], value=40),
         expect=items("The unit shall meet the following:", "3.2.6 a | a. Input voltage: 22 to 29 VDC.",
                      "3.2.6 b | b. Ripple: 1 V peak to peak maximum.",
                      "3.2.6 c | c. Peak inrush current (cold): 20 A for 10 ms maximum.",
                      "3.2.6 d | d. Power: 150 W maximum.", "3.2.6 e | e. Transients: as in MIL-STD-704F.",
                      "3.2.6 f | f. Hold-up: 50 ms after loss of input.")
         + para("3.2.7 | The unit shall weigh less than 5 kg.")),
    Case("TAB-25", "Values in lower case without a full stop",
         "Values such as 'within 22 to 29 VDC', 'less than 1 V peak to peak', 'not more than 150 W', 'per "
         "MIL-STD-704F' - lower case, no final full stop.",
         "Values that start in lower case are not a column of prose running on from line to line: each stays with "
         "its label (round 2: every value went into the last item).",
         "Review round 2, finding layout/F2.",
         text=tab_text("3.2.6 Input power. The unit shall meet the following:", _LOWER,
                       ["", "3.2.7 Weight. The unit shall weigh less than 5 kg."]),
         expect=items("The unit shall meet the following:", "3.2.6 a | a. Input voltage: within 22 to 29 VDC",
                      "3.2.6 b | b. Ripple: less than 1 V peak to peak", "3.2.6 c | c. Power: not more than 150 W",
                      "3.2.6 d | d. Transients: per MIL-STD-704F")
         + para("3.2.7 | The unit shall weigh less than 5 kg.")),
    Case("TAB-26", "Values that end with commas, one sentence over all items",
         "'within 22 to 29 VDC,' / 'less than 1 V peak to peak,' / 'not more than 150 W, and' / 'per MIL-STD-704F.' - "
         "the items read as one sentence; the values are short and all about as long as each other.",
         "Each value stays with its label. Short values of equal length look like 'full' lines of a narrow text "
         "column, so the column test must not be fooled (round 3: on the scan the list was cut into two columns).",
         "Review round 2, finding layout/F2; real-scan failure found in round 3.",
         text=tab_text("3.2.6 Input power. The unit shall operate with an input:", _COMMA,
                       ["", "3.2.7 Weight. The unit shall weigh less than 5 kg."]),
         expect=_COMMA_ROWS),
    Case("TAB-27", "Values that end with commas, proportional font",
         "TAB-26 in a proportional (serif) font, where the OCR also tends to read the marker 'c.' as 'C.'.",
         "As TAB-26: four rows, each with its own value.",
         "Review round 2, finding layout/F2; real-scan failure found in round 3.",
         text=tab_text("3.2.6 Input power. The unit shall operate with an input:", _COMMA,
                       ["", "3.2.7 Weight. The unit shall weigh less than 5 kg."]),
         font="serif", expect=_COMMA_ROWS),
    Case("TAB-28", "A value that starts with a quantity and a sentence ('5.0 V. Ripple shall ...')",
         "'a. Output voltage:  5.0 V. Ripple shall not exceed 50 mV.' and 'b. Output current:  2.5 A. The output "
         "shall be protected' / 'against short circuits.'",
         "'5.0 V.' is a quantity, not the start of a numbered paragraph 5.0 with the title 'V': no paragraphs '5.0' "
         "or '2.5' are invented, and the values stay in their items (round 2).",
         "Review round 2, finding layout/F3.",
         text=tab_text("3.2.9 Power supply. The power supply shall provide the following:",
                       [("a.", "Output voltage:", ["5.0 V. Ripple shall not exceed 50 mV."]),
                        ("b.", "Output current:", ["2.5 A. The output shall be protected", "against short circuits."]),
                        ("c.", "Efficiency:", ["85 percent minimum."])],
                       ["", "3.2.10 Weight. The power supply shall weigh less than 5 kg."]),
         font="serif",
         expect=items("The power supply shall provide the following:",
                      "3.2.9 a | a. Output voltage: 5.0 V. Ripple shall not exceed 50 mV.",
                      "3.2.9 b | b. Output current: 2.5 A. The output shall be protected against short circuits.",
                      "3.2.9 c | c. Efficiency: 85 percent minimum.")
         + para("3.2.10 | The power supply shall weigh less than 5 kg.")),
    Case("TAB-29", "A sub-list (1), (2) inside the value column",
         "'a. Search mode:  (1) Range of 100 km.' with '(2) Azimuth of 360 degrees.' under it in the value column; "
         "b. has its own (1), (2); c. has a plain value.",
         "The sub-items are filed under their own item: 3.2.8 a.1, a.2, b.1, b.2 - not a second column of the list "
         "(round 2: all sub-items were given to c), and the (2) rows keep their parent.",
         "Review round 2, finding layout/F4; the (2) rows lost their parent until round 3.",
         text=tab_text("3.2.8 Modes. The radar shall provide the following modes:",
                       [("a.", "Search mode:", ["(1) Range of 100 km.", "(2) Azimuth of 360 degrees."]),
                        ("b.", "Track mode:", ["(1) Update rate of 1 Hz.", "(2) Up to 64 targets."]),
                        ("c.", "Standby:", ["Transmitter off."])],
                       ["", "3.2.9 Weight. The radar shall weigh less than 45 kg."]),
         expect=items("The radar shall provide the following modes:",
                      "3.2.8 a.1 | a. Search mode: (1) Range of 100 km.",
                      "3.2.8 a.2 | a. Search mode: (2) Azimuth of 360 degrees.",
                      "3.2.8 b.1 | b. Track mode: (1) Update rate of 1 Hz.",
                      "3.2.8 b.2 | b. Track mode: (2) Up to 64 targets.",
                      "3.2.8 c | c. Standby: Transmitter off.")
         + para("3.2.9 | The radar shall weigh less than 45 kg.")),
    Case("TAB-30", "A sub-list printed without its own indent",
         "'b. Vibration:' with no value, then '(1) Random: ...' and '(2) Sine: ...' at the SAME indent as a. and b., "
         "then 'c. Shock: ...'.",
         "The change of marker style after a line ending ':' (and back again at c.) shows that (1) and (2) belong to "
         "b: rows 3.2.4 b.1 and b.2.",
         "Review round 3 (found while checking the round-2 fixes).",
         text=tab_text(_STEM, [_BASE[0], ("b.", "Vibration:", []), ("(1)", "Random:", ["20 Hz to 2000 Hz, 0.04 g2/Hz."]),
                               ("(2)", "Sine:", ["5 Hz to 500 Hz, 2 g peak."]), _BASE[2], _BASE[3]], ["", _AFTER]),
         expect=items(_STEM_S, _BASE_SPECS[0], "3.2.4 b.1 | b. Vibration: (1) Random: 20 Hz to 2000 Hz, 0.04 g2/Hz.",
                      "3.2.4 b.2 | b. Vibration: (2) Sine: 5 Hz to 500 Hz, 2 g peak.", *_BASE_SPECS[2:])
         + _WEIGHT),
    Case("TAB-31", "A label that wraps and is longer than its value",
         "'b. Operating' / 'temperature:' - a two-line label beside a ONE-line value, so the label's second line "
         "has nothing beside it.",
         "The label is read first, then the value: 'b. Operating temperature: -40 C to +71 C.' (round 2: 'b. "
         "Operating -40 C to +71 C. temperature:').",
         "Review round 2, finding layout/F5.",
         text=tab_text(_STEM, _WRAPPED, ["", _AFTER]), expect=_WRAPPED_ROWS),
    Case("TAB-32", "A label that wraps and is longer than its value, proportional font",
         "TAB-31 in a proportional (serif) font.",
         "As TAB-31. On this scan the first cells of the would-be table are the halves of wrapped labels "
         "('Storage' / 'temperature:'), which must be read as one label each, not as a table (round 3).",
         "Review round 2, finding layout/F5; real-scan failure found in round 3.",
         text=tab_text(_STEM, _WRAPPED, ["", _AFTER]), font="serif", expect=_WRAPPED_ROWS),
    Case("TAB-33", "A wrapped label whose second line has four words",
         "'a. Peak power' / 'consumption in any mode:' beside '150 W for not more than' / '10 seconds.'; serif font.",
         "'a. Peak power consumption in any mode: 150 W for not more than 10 seconds.' - a long second label line "
         "does not stop the label from being read first.",
         "Review round 2, finding layout/F5.",
         text=tab_text("3.2.6 Power. The unit shall meet the following:",
                       [("a.", ["Peak power", "consumption in any mode:"], ["150 W for not more than", "10 seconds."]),
                        ("b.", "Average power:", ["90 W."]), ("c.", "Standby power:", ["10 W."])],
                       ["", "3.2.7 Weight. The unit shall weigh less than 5 kg."], value=38),
         font="serif",
         expect=items("The unit shall meet the following:",
                      "3.2.6 a | a. Peak power consumption in any mode: 150 W for not more than 10 seconds.",
                      "3.2.6 b | b. Average power: 90 W.", "3.2.6 c | c. Standby power: 10 W.")
         + para("3.2.7 | The unit shall weigh less than 5 kg.")),
    Case("TAB-34", "A wrapped label whose first line ends with an abbreviation",
         "'a. Max. oper.' / 'temperature:' beside '+71 C with the unit powered' / 'and cooled.'",
         "The full stop of 'oper.' does not end the label: 'a. Max. oper. temperature: +71 C with the unit powered "
         "and cooled.' (a review note about the full stops is fine).",
         "Review round 2, finding layout/F5.",
         text=tab_text(_STEM, [("a.", ["Max. oper.", "temperature:"], ["+71 C with the unit powered", "and cooled."]),
                               ("b.", ["Min. oper.", "temperature:"], ["-40 C after a 2 hour", "cold soak."]),
                               ("c.", "Humidity:", ["95 percent non-condensing."])], ["", _AFTER]),
         expect=items(_STEM_S, "3.2.4 a | a. Max. oper. temperature: +71 C with the unit powered and cooled.",
                      "3.2.4 b | b. Min. oper. temperature: -40 C after a 2 hour cold soak.",
                      "3.2.4 c | c. Humidity: 95 percent non-condensing.") + _WEIGHT),
    Case("TAB-35", "Values that run on in lower case, each ending 'and'",
         "'a. Search:  the radar shall detect targets of 1 m2' / 'at 100 km range and', 'b. Track:  maintain track "
         "on up to 64 targets with' / 'an update rate of 1 Hz and', 'c. Identify:  interrogate ...'.",
         "Each item keeps its own value although the values read like one running sentence.",
         "Review round 2 (tab-list attack).",
         text=tab_text("3.2.6 Modes. In each mode the radar shall operate as follows:",
                       [("a.", "Search:", ["the radar shall detect targets of 1 m2", "at 100 km range and"]),
                        ("b.", "Track:", ["maintain track on up to 64 targets with", "an update rate of 1 Hz and"]),
                        ("c.", "Identify:", ["interrogate each target in track using", "Mode 5 IFF."])],
                       ["", "3.2.7 Weight. The radar shall weigh less than 45 kg."]),
         expect=items("In each mode the radar shall operate as follows:",
                      "3.2.6 a | a. Search: the radar shall detect targets of 1 m2 at 100 km range and",
                      "3.2.6 b | b. Track: maintain track on up to 64 targets with an update rate of 1 Hz and",
                      "3.2.6 c | c. Identify: interrogate each target in track using Mode 5 IFF.")
         + para("3.2.7 | The radar shall weigh less than 45 kg.")),
    Case("TAB-36", "Long labels ('Mean time between failures:')",
         "Four items whose labels have three to four words ('Mean time between failures:', 'Built-in test "
         "coverage:').",
         "Long labels are labels: one row per item.",
         "Review round 2 (tab-list attack).",
         text=tab_text("3.2.7 Reliability. The unit shall meet each of the following:",
                       [("a.", "Mean time between failures:", ["not less than 5000 hours."]),
                        ("b.", "Mean time to repair:", ["not more than 30 minutes."]),
                        ("c.", "Built-in test coverage:", ["95 percent of all failures."]),
                        ("d.", "False alarm rate:", ["1 percent maximum."])],
                       ["", "3.2.8 Weight. The unit shall weigh less than 5 kg."], value=40),
         expect=items("The unit shall meet each of the following:",
                      "3.2.7 a | a. Mean time between failures: not less than 5000 hours.",
                      "3.2.7 b | b. Mean time to repair: not more than 30 minutes.",
                      "3.2.7 c | c. Built-in test coverage: 95 percent of all failures.",
                      "3.2.7 d | d. False alarm rate: 1 percent maximum.")
         + para("3.2.8 | The unit shall weigh less than 5 kg.")),
    Case("TAB-37", "A value that wraps back under the label column",
         "'a. Operating temperature:  -40 C to +71 C with the unit powered' and the next line starting under the "
         "LABEL: 'and cooling air supplied at the rate given in Figure 3.'",
         "The value is read in order: 'a. Operating temperature: -40 C to +71 C with the unit powered and cooling air "
         "supplied at the rate given in Figure 3.' (round 1: the second value line was placed first).",
         "Review round 1, finding layout/F4.",
         text=_WRAP_BACK, expect=_WRAP_BACK_ROWS),
    Case("TAB-38", "A value that wraps back under the label column, proportional font",
         "TAB-37 in a proportional (serif) font.",
         "As TAB-37: three items, each with its whole value.",
         "Review round 1, finding layout/F4.",
         text=_WRAP_BACK, font="serif", expect=_WRAP_BACK_ROWS,
         known="In the proportional font the labels and values of items b and c (from 'Storage temperature:' down) "
               "are taken as a two-column table: item b's row keeps only its marker, without its letter in the Doc "
               "Ref ('3.2.4 | ... b.'), and item c has no row. The mono page (TAB-37) is read correctly."),
    Case("TAB-39", "A sentence under the label column after a two-line value",
         "Item a: 'Acceleration:' with a two-line value, then a sentence starting under the LABEL: 'The unit shall be "
         "powered and operating during the test.'",
         "The sentence stays in item a, after its value, in reading order (round 1: the rows were reordered).",
         "Review round 1, finding lists/F3.",
         text="""
3.2.4 Environmental conditions. The equipment shall meet
each of the following:
@gap 0.6
    a.    Acceleration:     5 g in each of the three orthogonal axes
                            for 1 minute per axis.
          The unit shall be powered and operating during the test.
~
    b.    Vibration:        20 Hz to 2000 Hz random.
~
    c.    Shock:            40 g, 11 ms half-sine pulse.
@gap 0.6
3.2.5 Weight. The equipment shall not exceed 45 kilograms.
""",
         expect=items(_STEM_S, "3.2.4 a | a. Acceleration: 5 g in each of the three orthogonal axes for 1 minute per "
                               "axis. The unit shall be powered and operating during the test.",
                      "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random.",
                      "3.2.4 c | c. Shock: 40 g, 11 ms half-sine pulse.") + _WEIGHT),
    Case("TAB-40", "A 'Note:' line inside a tabbed item",
         "Item a: 'Acceleration:  5 g in each of the three axes.', then under the label 'Note: The unit shall be "
         "powered during this test.', then items b and c.",
         "The note stays in item a; it is not given a marker of its own, and b and c keep their values (round 1: "
         "the note was split off and two rows got Doc Ref '3.2.4 b').",
         "Review round 1, finding layout/F11.",
         text=_NOTE_INSIDE, expect=_NOTE_INSIDE_ROWS),
    Case("TAB-41", "A 'Note:' line inside a tabbed item, proportional font",
         "TAB-40 in a proportional (serif) font.",
         "As TAB-40.",
         "Review round 1, finding layout/F11.",
         text=_NOTE_INSIDE, font="serif", expect=_NOTE_INSIDE_ROWS),
    Case("TAB-42", "Sub-labels without markers under 'a. Vibration: as follows:'",
         "'a. Vibration:  as follows:' then, in the label column with no marker, 'Random:  20 Hz ...' and "
         "'Sine:  5 g peak ...', then b. and c.",
         "The sub-labels belong to a (two rows '3.2.4 a'); they are not given made-up letters of their own (round 1: "
         "duplicate refs, parent lost).",
         "Review round 1, finding lists/F4.",
         text="""
3.2.4 Environmental conditions. The equipment shall meet
each of the following:
@gap 0.6
    a.    Vibration:        as follows:
          Random:           20 Hz to 2000 Hz, 0.04 g2/Hz.
          Sine:             5 g peak, 5 Hz to 500 Hz.
~
    b.    Shock:            40 g, 11 ms half-sine pulse.
~
    c.    Temperature:      -40 C to +71 C operating.
@gap 0.6
3.2.5 Weight. The equipment shall not exceed 45 kilograms.
""",
         expect=items(_STEM_S, "3.2.4 a | a. Vibration: as follows: Random: 20 Hz to 2000 Hz, 0.04 g2/Hz.",
                      "3.2.4 a | a. Vibration: as follows: Sine: 5 g peak, 5 Hz to 500 Hz.",
                      "3.2.4 b | b. Shock: 40 g, 11 ms half-sine pulse.",
                      "3.2.4 c | c. Temperature: -40 C to +71 C operating.") + _WEIGHT),
    Case("TAB-43", "A value that wraps back under a label without a colon, then a sub-list",
         "'a.  Vibration  20 Hz to 2000 Hz random, applied in', then under the label 'each of three axes as "
         "follows:', then '(1) Level: ...' and '(2) Duration: ...', then 'b.  Shock  40 g ...'.",
         "The value stays in order ('... applied in each of three axes as follows:') and the sub-items are filed "
         "under a: 3.2.4 a.1 and a.2 (round 3: the value line was taken for the end of a wrapped label, the text "
         "was reordered and the sub-items lost their parent).",
         "Review round 3, finding layout/F7.",
         text="""
3.2.4 Environmental conditions. The equipment shall meet
each of the following:
    a.     Vibration        20 Hz to 2000 Hz random, applied in
           each of three axes as follows:
               (1) Level: 0.04 g2/Hz.
               (2) Duration: 3 hours per axis.
    b.     Shock            40 g, 11 ms half-sine pulse.

3.2.5 Weight. The equipment shall not exceed 45 kilograms.
""",
         expect=items(_STEM_S, "3.2.4 a.1 | a. Vibration 20 Hz to 2000 Hz random, applied in each of three axes as "
                               "follows: (1) Level: 0.04 g2/Hz.",
                      "3.2.4 a.2 | a. Vibration 20 Hz to 2000 Hz random, applied in each of three axes as follows: "
                      "(2) Duration: 3 hours per axis.",
                      "3.2.4 b | b. Shock 40 g, 11 ms half-sine pulse.") + _WEIGHT),
    Case("TAB-44", "A value '1.5 V peak to peak. Measured at the' ...",
         "'b. Ripple:  1.5 V peak to peak. Measured at the' / 'output terminals.' between two one-line items.",
         "'1.5 V ...' is a quantity: it does not start paragraph 1.5, cut the list into columns or end the list "
         "(round 2: the values were attached to the wrong items and 3.2.7 c appeared twice).",
         "Review round 2, finding extraction/F2.",
         text=tab_text("3.2.7 Output. The power supply output shall be as follows:",
                       [("a.", "Voltage:", ["28 V dc nominal."]),
                        ("b.", "Ripple:", ["1.5 V peak to peak. Measured at the", "output terminals."]),
                        ("c.", "Power:", ["150 W maximum."])],
                       ["", "3.2.8 Weight. The power supply shall weigh less than 5 kg."]),
         expect=items("The power supply output shall be as follows:", "3.2.7 a | a. Voltage: 28 V dc nominal.",
                      "3.2.7 b | b. Ripple: 1.5 V peak to peak. Measured at the output terminals.",
                      "3.2.7 c | c. Power: 150 W maximum.")
         + para("3.2.8 | The power supply shall weigh less than 5 kg.")),
    Case("TAB-45", "A value line '2.5 G rms overall. Duration 3 hours per axis.'",
         "Item b's value has a second line that starts with a decimal quantity and a capital unit: '2.5 G rms "
         "overall. Duration 3 hours per axis.'",
         "The line stays in item b; '2.5 G' is not paragraph 2.5.",
         "Review round 2, finding extraction/F2.",
         text=tab_text("3.2.4 Environment. The unit shall meet each of the following:",
                       [("a.", "Acceleration:", ["5 g in each of the three axes."]),
                        ("b.", "Vibration:", ["20 Hz to 2000 Hz random.", "2.5 G rms overall. Duration 3 hours",
                                                              "per axis."]),
                        ("c.", "Shock:", ["40 g, 11 ms half-sine."]), ("d.", "Humidity:", ["95 percent, non-condensing."])],
                       ["", "3.2.5 Weight. The unit shall weigh less than 5 kg."]),
         expect=items("The unit shall meet each of the following:", "3.2.4 a | a. Acceleration: 5 g in each of the three axes.",
                      "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random. 2.5 G rms overall. Duration 3 hours per axis.",
                      "3.2.4 c | c. Shock: 40 g, 11 ms half-sine.", "3.2.4 d | d. Humidity: 95 percent, non-condensing.")
         + para("3.2.5 | The unit shall weigh less than 5 kg.")),
    Case("TAB-46", "A nested (1)/(2) list inside a value that ends with ':'",
         "'a. Search:  The search mode shall provide:' then '(1) Long range search to 150 km.' and '(2) Short range "
         "search to 50 km.' a little right of the value column.",
         "The value's own lead-in ('The search mode shall provide:') leads into the sub-items: rows 3.2.4 a.1 and a.2.",
         "Review round 1 (layout attack, control page).",
         text="""
3.2.4 Modes. The radar shall provide each of the following modes:
~
    a.   Search:        The search mode shall provide:
                           (1) Long range search to 150 km.
                           (2) Short range search to 50 km.
~
    b.   Track:         Track while scan of 200 targets.
~
    c.   Map:           Real beam ground mapping to
                        80 km range.

3.2.5 Weight. The radar shall not exceed 45 kilograms.
""",
         expect=items("The radar shall provide each of the following modes:",
                      "3.2.4 a.1 | a. Search: The search mode shall provide: (1) Long range search to 150 km.",
                      "3.2.4 a.2 | a. Search: The search mode shall provide: (2) Short range search to 50 km.",
                      "3.2.4 b | b. Track: Track while scan of 200 targets.",
                      "3.2.4 c | c. Map: Real beam ground mapping to 80 km range.")
         + para("3.2.5 | The radar shall not exceed 45 kilograms.")),
    Case("TAB-47", "Each label on its own line, its text on the lines below",
         "'a.  Operator display:' with nothing beside it, then the item's two-line text below, starting under the "
         "label.",
         "The text belongs to its label's item: '3.2.10 a | ... a. Operator display: The display shall present ...'.",
         "Review round 2 (tab-list attack).",
         text="""
3.2.10 Displays. The system shall provide the following displays:
~
    a.     Operator display:
           The display shall present the current mode, the
           range scale and all tracks in the selected sector.
~
    b.     Maintainer display:
           The display shall present the current mode, the
           range scale and all tracks in the selected sector.

3.2.11 Weight. The system shall weigh less than 45 kg.
""",
         expect=items("The system shall provide the following displays:",
                      "3.2.10 a | a. Operator display: The display shall present the current mode, the range scale "
                      "and all tracks in the selected sector.",
                      "3.2.10 b | b. Maintainer display: The display shall present the current mode, the range scale "
                      "and all tracks in the selected sector.")
         + para("3.2.11 | The system shall weigh less than 45 kg.")),
    Case("TAB-48", "A whole page typed double-spaced",
         "A double-spaced typewritten page: the lead-in, a list whose values wrap (a blank line between every "
         "line), a paragraph, then 3.2.5.",
         "Double spacing is the page's normal spacing, not a blank line after every item: the values stay whole, "
         "and the paragraph after the list is a row of its own.",
         "Review round 2 (tab-list attack).",
         text=_DOUBLE_SPACED,
         expect=para("3.2.3 | The unit shall operate from 28 VDC and shall draw no more than 150 W in any mode.")
         + items("The input shall meet each of the following:", *[s.replace("3.2.4", "3.2.3", 1) for s in _BASE_SPECS])
         + para(" | The unit shall return to normal operation within 50 ms after any transient.") + _WEIGHT),
    Case("TAB-49", "A second paragraph of a value, after a blank line, in the value column",
         "Each item: its value, a blank line, then a second sentence in the VALUE column ('The unit shall operate "
         "during the test.').",
         "A paragraph in the value column after a blank line is still part of that item's value.",
         "Review round 2 (tab-list attack).",
         text="""
3.2.4 Environmental conditions. The equipment shall meet
each of the following:
~
    a.     Acceleration:    5 g in each of the three axes.

                            The unit shall operate during the test.
~
    b.     Vibration:       20 Hz to 2000 Hz random.

                            The unit shall operate during the test.
~
    c.     Shock:           40 g, 11 ms half-sine.

                            The unit shall not be operated.

3.2.5 Weight. The equipment shall not exceed 45 kilograms.
""",
         expect=items(_STEM_S, "3.2.4 a | a. Acceleration: 5 g in each of the three axes. The unit shall operate during "
                               "the test.",
                      "3.2.4 b | b. Vibration: 20 Hz to 2000 Hz random. The unit shall operate during the test.",
                      "3.2.4 c | c. Shock: 40 g, 11 ms half-sine. The unit shall not be operated.") + _WEIGHT),
    Case("TAB-50", "A value that ends with a colon of its own",
         "'a. Output voltage:  The output voltage shall be:' / '28 VDC +/- 2 V at the connector.'",
         "A colon at the end of a value line does not turn the item into the lead-in of a sub-list; the next value "
         "line is more of the same value.",
         "Review round 2 (tab-list attack).",
         text=tab_text("3.2.9 Power supply. The power supply shall provide the following:",
                       [("a.", "Output voltage:", ["The output voltage shall be:", "28 VDC +/- 2 V at the connector."]),
                        ("b.", "Output current:", ["5 A maximum."]), ("c.", "Efficiency:", ["85 percent minimum."])],
                       ["", "3.2.10 Weight. The power supply shall weigh less than 5 kg."]),
         expect=items("The power supply shall provide the following:",
                      "3.2.9 a | a. Output voltage: The output voltage shall be: 28 VDC +/- 2 V at the connector.",
                      "3.2.9 b | b. Output current: 5 A maximum.", "3.2.9 c | c. Efficiency: 85 percent minimum.")
         + para("3.2.10 | The power supply shall weigh less than 5 kg.")),
    Case("TAB-51", "Contents of a report: 'Title:', 'Procedure:', 'Remarks:', 'Signature:'",
         "'4.3 Test report. Each test report shall contain the following:' then a. Title:, b. Procedure:, c. "
         "Remarks:, d. Signature: with lower-case values.",
         "Four items. Words such as 'Remarks:' are labels of this list, not notes.",
         "Review round 2 (tab-list attack).",
         text=tab_text("4.3 Test report. Each test report shall contain the following:",
                       [("a.", "Title:", ["the title of the test."]), ("b.", "Procedure:", ["the procedure used."]),
                        ("c.", "Remarks:", ["any deviation from the procedure."]),
                        ("d.", "Signature:", ["the signature of the inspector."])],
                       ["", "4.4 Records. The contractor shall keep test reports for five years."]),
         expect=items("Each test report shall contain the following:", "4.3 a | a. Title: the title of the test.",
                      "4.3 b | b. Procedure: the procedure used.", "4.3 c | c. Remarks: any deviation from the procedure.",
                      "4.3 d | d. Signature: the signature of the inspector.")
         + para("4.4 | The contractor shall keep test reports for five years.")),
    Case("TAB-52", "An item whose value is empty",
         "'b. Vibration:' with nothing beside it and nothing under it, between complete items.",
         "b is still an item of its own ('b. Vibration:'); c and d keep their values.",
         "Review round 2 (tab-list attack).",
         text=tab_text(_STEM, [_BASE[0], ("b.", "Vibration:", []), _BASE[2], _BASE[3]], ["", _AFTER]),
         expect=items(_STEM_S, _BASE_SPECS[0], "3.2.4 b | b. Vibration:", *_BASE_SPECS[2:]) + _WEIGHT),
    Case("TAB-53", "Labels without colons",
         "The list of TAB-01's shape with every label's colon left out ('Acceleration', 'Vibration').",
         "Still one row per item with its label and value.",
         "Review round 2 (tab-list attack).",
         text=tab_text(_STEM, [(m, l.rstrip(":"), v) for m, l, v in _BASE], ["", _AFTER]),
         expect=items(_STEM_S, "3.2.4 a | a. Acceleration 5 g in each of the three orthogonal axes for 1 minute per axis.",
                      "3.2.4 b | b. Vibration 20 Hz to 2000 Hz random, 0.04 g2/Hz, 3 hours per axis, 7.7 g rms overall.",
                      "3.2.4 c | c. Shock 40 g, 11 ms half-sine pulse, 3 shocks in each direction.",
                      "3.2.4 d | d. Temperature -40 C to +71 C operating.") + _WEIGHT),
    Case("TAB-54", "A value line '12.5 V. The auxiliary output shall be' after a finished value line",
         "'a. Main output:  The output shall be 28 VDC nominal.' then '12.5 V. The auxiliary output shall be' / "
         "'regulated to 1 percent.' in the value column; item b's value wraps back under its label.",
         "'12.5 V.' is a quantity, not paragraph 12.5: it stays in item a.",
         "Review round 2 (tab-list attack).",
         text="""
3.2.9 Power supply. The power supply shall provide the following:
~
    a.     Main output:     The output shall be 28 VDC nominal.
                            12.5 V. The auxiliary output shall be
                            regulated to 1 percent.
~
    b.     Efficiency:      85 percent minimum at full load with
           the cooling air at the temperature given in Table II.

3.2.10 Weight. The power supply shall weigh less than 5 kg.
""",
         expect=items("The power supply shall provide the following:",
                      "3.2.9 a | a. Main output: The output shall be 28 VDC nominal. 12.5 V. The auxiliary output shall "
                      "be regulated to 1 percent.",
                      "3.2.9 b | b. Efficiency: 85 percent minimum at full load with the cooling air at the "
                      "temperature given in Table II.")
         + para("3.2.10 | The power supply shall weigh less than 5 kg.")),
]
