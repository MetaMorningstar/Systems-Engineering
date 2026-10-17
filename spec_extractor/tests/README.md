# Testing spec_extractor

There are four ways to test the tool. Every command below is typed in a terminal (Command Prompt) **in the
`spec_extractor` folder** - the folder that holds `spec_extractor.py`. On Windows, start each command with
`.venv\Scripts\python` instead of `python` to use the tool's own Python environment (the one
`setup_windows.bat` made).

| Test | What it checks | How long | Command |
|---|---|---|---|
| **Rule tests** | the layout, table, list, heading and export rules, on made-up page geometry (no OCR) | seconds | `python tests/test_rules.py` |
| **Regression** | the whole tool, with the real OCR, on 12 scanned files (42 pages) of 7 synthetic specifications with exact answers | 4-6 minutes | `python tests/run_regression.py` |
| **Case library** | the whole tool on 162 small scanned pages, each one situation (a list on tab stops, a table without a heading row ...) | 15-20 minutes | `python tests/cases/run_cases.py` |
| **Your own scans** | the whole tool on pages of your own documents, checked against what you wrote down | a minute a page | `python tests/cases/run_cases.py --only MY` |

The test tools need a few extra packages, once:

```bat
python -m pip install -r requirements-dev.txt -c constraints.txt
```

Nothing here uses the network: the test documents are drawn on this computer, and the tool runs offline.

---

## 1. Rule tests (`tests/test_rules.py`)

```bat
python tests/test_rules.py                      all of them (about 350), in a minute or two
python tests/test_rules.py underline            only the tests with "underline" in their name
python tests/test_rules.py underline doors      ... with "underline" or "doors" in their name
python tests/test_rules.py --list               the name and first line of every test
```

Each test prints `ok` or `FAIL` (with the line that failed), and the run ends with the number passed and failed.
The last line says whether the Python and package versions are the tested ones.

**Adding a rule test.** A test is a function whose name starts with `test_`; it is found by its name, so it only
has to be written. It builds OCR "lines" with the geometry of a real page (220 dpi, a typewriter font), runs
them through the tool's real steps and checks the rows. The helpers at the top of the file do the work:

```python
def test_a_heading_without_a_full_stop_keeps_its_requirement():
    """'3.2.1 Power input' on a line of its own, then the requirement - one row with the number."""
    lines = make_lines(["3.2.1 Power input",                        # one printed line each,
                        "The equipment shall operate from 115 V ac.",
                        None,                                       # None = a blank line
                        (60, "a. indented by 60 pixels")])          # (indent, text)
    doc, items = run({1: lines})                                    # {page number: lines}
    row = find(items, "115 V ac")                                   # the one requirement with this text
    assert row.doc_ref == "3.2.1", row.doc_ref
```

* `make_lines` / `make_line` - text to OCR lines; `run` - lines to `(document, Excel rows)` through layout,
  clean-up and extraction; `requirements`, `texts`, `find` - pick rows out of the result.
* Tests of tables and underlining draw a real page image, because those rules look at the ink: `_draw_words()`
  and `_draw_table()` draw text and ruled tables, `_draw_formatted()` underlined and bold text. `_report_sample()`
  is a small document with every part of the Word report, for tests of the report.
* Put the new test next to the tests of the same rule, and give it a docstring that says what must happen:
  the first sentence is shown in the case catalog's appendix.

---

## 2. Regression (`tests/run_regression.py`)

```bat
python tests/run_regression.py            build the test documents (only when missing), run the tool, score it
python tests/run_regression.py --reuse    keep the OCR results of the last run: seconds, for changes to the rules
python tests/evaluate.py tests/_results --details     every missed or extra row, every wrong number or caption
```

The test documents (`tests/corpus/`, made by `tests/make_test_corpus.py`) are specifications in several styles,
each "aged" into an office scan, a photocopy or a fax, with the exact rows they must give. The run prints a table
per document and ends with **PASS** or **FAIL**: requirement recall and precision, captions, tables, wrong
paragraph numbers, and how many rows with an OCR error are flagged for review. The limits are in `THRESHOLDS` at the
top of `run_regression.py`. Results go to `tests/_results/`.

`--reuse` re-runs only the steps after the OCR, which are most of the rules. Changes to sections 3-6 or 8 of
`spec_extractor.py` (data model, loading, image clean-up, OCR and page layout, Docling) make the tool read the
documents again by itself.

---

## 3. The case library (`tests/cases/`)

Each **case** is one small page - one situation the tool must get right, or once got wrong - with the exact rows
it must produce. Every case has a fixed ID (`TAB-01`, `LST-07`, `STR-05` ...). **`tests/cases/CASEBOOK.pdf`** shows
them all, one page per case: the situation, what must happen and why, the page itself and the expected rows.

### Running cases

```bat
python tests/cases/run_cases.py                      all cases (15-20 minutes)
python tests/cases/run_cases.py --only STR           one area (STR = document structure)
python tests/cases/run_cases.py --only STR-05        one case
python tests/cases/run_cases.py --only STR-05,TBL    several, separated by commas
python tests/cases/run_cases.py --only "page break"  the cases whose title has these words
python tests/cases/run_cases.py --only STR-05 -v     ... with the expected and actual rows of a failing case
python tests/cases/run_cases.py --reuse              check the last run's results again without running the tool
python tests/cases/run_cases.py --jobs 4             run 4 copies of the tool at once (default: half the cores)
python tests/cases/run_cases.py other\spec_extractor.py    test another copy of the tool (e.g. an edited one)
```

The areas are: `TAB` lists on tab stops, `LST` list markers, `LEAD` lead-ins, `NUM` numbered lists and paragraph
numbers, `PARA` paragraphs, `COL` two-column pages, `TBL` tables beside lists, `PAGE` page breaks, `STR` document
structure (underlined titles, nesting, applicable documents, tables and lists, autocorrection).

Each case ends as **PASS**, **FAIL**, **KNOWN** (a known limitation, still wrong as its page in the catalog
describes - it does not fail the run) or **KNOWN-PASSES** (the limitation seems fixed: check it, and remove its
`known=` mark). The run then lists the cases whose result changed since the previous run - the quickest way to see
what an edit improved or broke - and writes:

* `tests/cases/_results/case_report.txt` - every case, expected against actual, row by row;
* `tests/cases/_results/case_results.xlsx` - one line per case;
* `tests/cases/_results/run*/` - the tool's own Excel files for each case, to open and look at.

(Your own scans, section 4, are run into `tests/cases/my_cases/_results/` instead, with reports of their own.)

To look at a case's page, open `tests/cases/documents/<ID>_<name>.pdf`, or run the tool on that one file:

```bat
python spec_extractor.py tests\cases\documents\STR-05_a_list_of_documents_under_a_title_and_a_tab_indented_sub_tit.pdf
```

To run the cases with another Python, set `SPEC_PYTHON` to it first (`set SPEC_PYTHON=C:\Python314\python.exe`).

### Adding a case of your own design

1. **Pick the area file** - `tests/cases/area_tables.py`, `area_structure.py` ... - and the next free ID in it.
2. **Write the case** at the end of its `CASES` list. The page is typed as it looks: every line is a printed
   line; two or more spaces mean "the next piece starts at this column" (so tab stops are written as spaces);
   `<u>...</u>` underlines and `<b>...</b>` prints in bold; lines starting with `@` are drawing instructions
   (`@gap 0.5`, `@page`, `@rule`, `@wrap` - all explained at the top of `casekit.py`).

   ```python
   Case("STR-14", "An underlined title with its text on the same line",        # ID and title
        "'3.2.1' at the margin, the underlined title 'Power input', then the requirement on the same line.",
        "A heading '3.2.1 Power input' and one requirement row with the title split off.",   # what must happen
        "Why the case exists: who asked, or which bug it caught.",                            # where it came from
        text="""
   3.2 Electrical.

        3.2.1  <u>Power input</u>  The equipment shall operate from 115 V ac.
   """,
        expect=para("3.2.1 | The equipment shall operate from 115 V ac. [title: Power input]"),
        outline=("2 | 3.2 Electrical", "3 | 3.2.1 Power input")),     # optional: Document Structure headings
                                                                      # (level = parts of the number: 3.2.1 is 3)
   ```

   * `expect=para(...)`: one string per **Requirement** row of the Extracted Items sheet, `"<Doc Ref> | <Content>"`.
     `items(lead_in, ...)` writes rows of a list, with the lead-in in front of each, as the tool does.
   * Checks in brackets at the end of a row: `[note: ...]` (Review Reasons), `[no marker note]`, `[section: ...]`,
     `[pages: 1-2]`, `[title: ...]`, `[corrected: requ1red]` (OCR Corrections), `[quality: ...]`.
   * `tables=1` and `table_has=("text",)` check Table items; `captions=("TABLE I",)` their captions;
     `outline=(...)` the Document Structure headings (`"level | number title"`); `documents=(...)` the Applicable
     Documents sheet (`"number | title | paragraphs"`); `font="serif"` prints the page in a proportional font.
   * A case the tool still gets wrong can be kept with `known="what happens instead"`.
3. **Draw it and update the catalog**: `python tests/cases/build_cases.py` (only new and changed cases are drawn).
   `test_rules.py` fails until the catalog has been rebuilt, so a case cannot be added without its page.
4. **Run it**: `python tests/cases/run_cases.py --only STR-14 -v`.

A case that fails at once is a bug report with its reproduction attached: commit it with `known=` if it is not
fixed in the same change.

---

## 4. Adding your own example (`tests/cases/my_cases/`)

A page of a real document that the tool got wrong is the best test there is. It can be kept as a case **on this
computer only**: nothing in `tests/cases/my_cases/` goes into git (that folder's `.gitignore` keeps everything
out but its two help files), and nothing is sent anywhere.

1. Copy the scan - a whole document or a few pages saved as their own PDF or TIFF - into `tests/cases/my_cases/`,
   for example `tests/cases/my_cases/page12.pdf`.
2. Record what the tool produces now:

   ```bat
   python tests/cases/run_cases.py --record tests/cases/my_cases/page12.pdf
   ```

   This writes `tests/cases/my_cases/page12.pdf.expected.txt` beside the scan (an existing one is never
   overwritten).
3. Open the `.expected.txt` file in Notepad and **correct it to what the tool should produce**. One expectation per
   line; anything after `#` is a comment:

   ```text
   requirement: 3.2.1 | The equipment shall operate from 115 V ac.  [title: Power input]
   requirement: 3.2.2 a | The unit shall provide the following: a. Search mode.
   tables: 1
   table has: Flow control
   caption: TABLE I
   heading: 3 | 3.2.1 Power input
   document: MIL-STD-461G | Requirements for the Control of Electromagnetic Interference Characteristics | 3.2.5
   ```

   Delete the lines that are wrong and write the right ones; leave out what you do not want checked (the
   `heading:` and `document:` lines can all be removed, for example). The checks in brackets are the ones of
   section 3.
4. Check it from now on with every run, or on its own:

   ```bat
   python tests/cases/run_cases.py --only MY
   ```

   Your cases are named `MY-<file name>` (`--only MY-PAGE12` runs one of them) and take part in every plain
   `run_cases.py` run too.

Remember that these files hold your document's text. Everything the runs write for your scans stays inside
`tests/cases/my_cases/`: the tool's workbooks, the page images and text it keeps in `_cache`, and the case reports
(which quote the requirement text) go to `tests/cases/my_cases/_results/`, never to `tests/cases/_results/`, and
`--record` refuses a scan that is not in `my_cases` (and deletes the tool's output once the `.expected.txt` is
written). Keep the folder where such data may be kept, and when a scan is no longer needed delete it, its
`.expected.txt` and the `_results` folder.

---

## 5. Before handing out a new version

1. `python tests/test_rules.py` - all pass (it also checks that the version in `spec_extractor.py` matches the
   heading of `README.md`, and that the case catalog is up to date).
2. `python tests/run_regression.py` - PASS.
3. `python tests/cases/run_cases.py` - no FAIL (KNOWN cases are allowed; KNOWN-PASSES ones should be cleared).
4. Repeat 1-3 on every supported Python version (README, *Python versions*), with `SPEC_PYTHON` for step 3.
5. Open a verification report and a `_for_doors.docx` in Word, and one made with your organisation's template.
