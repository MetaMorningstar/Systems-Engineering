# Spec Extractor

> ## Version 1.3.0
>
> Every run prints this version together with a **build** fingerprint of the code that is actually running:
>
> ```
> spec_extractor 1.3.0 (build a1b2c3d commit 4e5f6a7)
> ```
>
> (the two short codes are examples - yours will differ)
>
> The **build** is a fingerprint of `spec_extractor.py` itself, so it changes whenever any line of the tool changes - a merge, a hand edit, a patch that only half applied. The **commit** is shown as well when the folder is a git checkout, which is what identifies a merge. To check a folder is up to date, compare the line a run prints with the version above and with the commit you expect; `python spec_extractor.py --version` prints it without processing anything. The same line is written into the Excel **Run Info** sheet and the header of the Word report, so any result can be traced back to the code that produced it.
>
> Maintainers: raise `__version__` in `spec_extractor.py` **and** this heading in the same commit - `tests/test_rules.py` fails if they disagree.

Pulls **Systems Engineering requirements, tables and figure/table captions** out of **scanned PDF and TIFF documents** (typewritten, photocopied, faxed, skewed, upside-down…). It produces an Excel dataset where **every row is one complete requirement, one caption or one complete table**, and a Word verification report for checking the result against the scan.

Everything runs **locally on a normal CPU**. After installation it needs no internet connection: the OCR model files are inside the pip package, and no document content ever leaves the computer. The tool also switches off the usage telemetry that ONNX Runtime (the engine that runs the OCR models) would otherwise try to send to Microsoft; a full run was measured to make no outbound connections.

---

## 1. What you get

For each input document, in the output folder:

| File | What it is |
|---|---|
| `<name>_extracted.xlsx` | **Extracted Items** sheet: one row per requirement / table / caption. Columns include page, section, paragraph number or requirement ID, keyword, class (mandatory/goal/intent), **verification method** and **references** (see below the table), plus confidence and review flags. One extra sheet per table (`T001`, `T002`, …) holding the full cell grid. **Full Text** has every text block in reading order. **Page Quality** has per-page scan quality. **Run Info** has the settings, the column help and the *Tested configuration* check ([Python versions](#python-versions)). |
| `<name>_verification.docx` | Page by page: the cleaned scan image, then the text the tool read (headings, paragraphs, lists, real Word tables, captions, figures). Words that need a look are **highlighted**, and blue tags such as **[R-0012]** show which Excel row a sentence became. |
| `ALL_DOCUMENTS_<date>.xlsx` | All documents in one workbook (only when several files are processed). |
| `spec_extractor_log.txt` | The run log. |
| `_cache\` | Saved OCR results. Re-runs of unchanged files skip the slow OCR step. Safe to delete. |

About the **verification method** and **references** columns:

* **Verification method** comes from the requirement table's Method column. Otherwise it is looked up in the document's verification cross-reference matrix, an I/A/D/T table. Such a matrix is read even when it is drawn with column rules but no line between the rows, and when its column headers are printed sideways. If those headers cannot be read at all, the columns are named from the legend sentence the document prints above the matrix ("... by inspection (I), analysis (A), demonstration (D), or test (T)"); the method then says *columns named from the legend* and the row is flagged for review, because it was deduced from the column order rather than read off the page.
* **References** lists the standards, tables, figures and sections a requirement cites, e.g. `MIL-STD-704F; TABLE II`.

Requirements are recognised in all the usual layouts:

* **Numbered paragraphs**, e.g. `3.2.1.4 Operating temperature. The radar shall …`. Paragraph number and title go into their own columns, and each "shall" sentence becomes its own row.
* **Stem + list**, e.g. `The radar shall provide the following modes: a. Search. b. Track.` This gives one row per item ("stem + item"), including nested lists, lists whose markers sit a wide tab away from their text, and lists whose markers the scan misread or lost (see [Requirement rules](#requirement-rules-section-9-of-the-script)). `--keep-list-stems` gives one row per block instead.
* **Lists on wide tab stops**, where each item is a marker, a label and a value that may run over several lines:

  ```
  3.2.4 Environmental conditions. The equipment shall meet each of the following:
      a.      Acceleration:      5 g in each of the three orthogonal axes
                                 for 1 minute per axis.
      b.      Vibration:         20 Hz to 2000 Hz random, 0.04 g2/Hz,
                                 3 hours per axis, 7.7 g rms overall.
  ```

  Each item becomes one row - `3.2.4 a` / *The equipment shall meet each of the following: a. Acceleration: 5 g in each of the three orthogonal axes for 1 minute per axis.* - with the label and the whole value, even when a value line starts with a number ("2.5 C per minute", "1.5 V peak-to-peak", "5.0 V. Ripple shall …"), starts in lower case or has no final full stop ("within 22 to 29 VDC"). Markers may be `a.` `a)` `(a)` `A.` `1.` `1)` `(1)` `i.` `(i)` or bullets, labels may wrap onto a second line (even when the value beside them is shorter), and the lead-in may end with a colon or with a phrase such as *the following*, *as follows* or *as specified below*. A sub-list inside a value (`a. Search mode:   (1) Range …` with `(2) Azimuth …` under it) is filed under its own item (`3.2.8 a.1`, `3.2.8 a.2`), and so is a sub-list printed without an indent of its own (`b. Vibration:` then `(1) …`, `(2) …`, then `c. …`).
* **Requirement tables**, with columns like *Req ID / Requirement / Verification* or *Requirement ID / Requirement Type / Requirement Text / Verification Method*. Each row becomes a requirement, and the other columns are kept (e.g. `Requirement Type: Interface`).
* **Inline IDs** such as `[SRS-101] The software shall …` or `SRS-103: …`.

---

## 2. Quick start (Windows)

1. Install a 64-bit **Python 3.11 or 3.12** from python.org (3.10, 3.13 and 3.14 also work, see [Python versions](#python-versions)). With the python.org installer, tick **"Add python.exe to PATH"**. With the newer **Python install manager**, open a terminal and run `py install 3.12`.
2. Put this folder somewhere (e.g. `C:\Tools\spec_extractor`).
3. Double-click **`setup_windows.bat`**. This is a one-time step of a few minutes that creates a private `.venv` environment with **exactly the package versions the tool was tested with** (`constraints.txt`). It picks a tested Python by itself, and says what to install if there is none.
4. Double-click **`run_extractor.bat`** and pick PDF/TIFF files. If you press *Cancel*, you get a folder picker instead. You can also **drag and drop** files or folders onto `run_extractor.bat` (Windows cannot pass a name containing `&` this way: rename the file, or use the picker). The folder may be on a network share.
5. Open the `extraction_output` folder next to your documents.

From a terminal (any OS):

```bat
python -m pip install -r requirements.txt -c constraints.txt
python spec_extractor.py "C:\Scans\SPEC-1234.pdf"
python spec_extractor.py "C:\Scans" -r -o "C:\Results"          (a whole folder tree)
python spec_extractor.py spec.tif --pages 1-10                   (try a few pages first)
python spec_extractor.py --help                                  (all options)
```

### Installing on a computer without internet access

On a computer **with** internet, the **same Windows version and the same Python version**, run this inside this folder:

```bat
python -m pip wheel -r requirements.txt -c constraints.txt -w wheels
```

Copy the whole folder, including the new `wheels` subfolder, to the offline computer and double-click `setup_windows.bat`. It installs from `wheels` automatically. On a company PyPI mirror (e.g. Artifactory), the normal `pip install -r requirements.txt -c constraints.txt` works as long as pip is configured for the mirror and the mirror carries the pinned versions.

### Python versions

| Python (64-bit, standard build) | Status |
|---|---|
| **3.11, 3.12** | Recommended. Fastest, because only Python 3.12 and older can install the page-orientation classifier. |
| **3.13, 3.14** | Supported, same accuracy. The classifier's package does not support these versions, so pages are turned upright with a slower OCR-based check (a few seconds more per page). The classifier is deliberately not forced onto them. |
| **3.10** | Supported, same accuracy. Uses older numpy and ONNX Runtime releases, pinned in `constraints.txt`. Python 3.10 reaches end of life in October 2026. |
| 3.15 and newer, 32-bit Python, the free-threaded build (`python3.14t`) | Not supported: the OCR and table packages cannot be installed there, or were not tested there. `setup_windows.bat` skips them. |

Release 1.2.0 was re-run on Python 3.10, 3.11, 3.12 and 3.13 with the exact package versions in `constraints.txt`; **Python 3.14 has not been re-run since release 1.0.1** (see section 9). Every run states whether it used this **tested configuration**: in the first lines of the run log, in the *Tested configuration* row of the Excel **Run Info** sheet (the installed versions are listed below it) and in the header of the Word report. If it says **NO**, the accuracy figures in section 6 do not apply to that run; see section 7.

---

## 3. Command-line options

| Option | Meaning |
|---|---|
| `-o FOLDER` | Output folder (default: `extraction_output` next to the input) |
| `-r` | Also process sub-folders |
| `--pages 1-5,9` | Only these pages |
| `--keywords "shall,must"` | Words/phrases that mark a requirement, separated by commas or semicolons. Default: `shall, must, is required to, are required to, should, will` |
| `--no-will`, `--no-should` | Do not report "will" (statement of intent) or "should" (goal) sentences |
| `--keep-list-stems` | One row per stem with all its list items, instead of one row per item |
| `--review-threshold 0.7` | Numbers read with OCR confidence below this are flagged |
| `--dpi 220` | Working resolution for OCR (220 was best in testing) |
| `--no-rotate`, `--no-deskew`, `--no-clean` | Switch off automatic page turning, straightening, background clean-up |
| `--remove-color-marks` | Fade colored stamps, pen marks and highlighter before OCR |
| `--no-borderless-tables` | Only detect tables drawn with ruling lines |
| `--no-inferred-rows` | Do not work out a table's missing row separators from the text. Tables whose columns are ruled but whose rows are not will then be missed |
| `--no-sideways-headers` | Do not turn a table's header band upright to read column headers printed sideways |
| `--no-word`, `--no-page-images`, `--no-combined` | Skip outputs, or make the Word report smaller |
| `--no-cache` | Always redo the OCR |
| `--engine docling` | Optional AI layout/table engine (section 8) |
| `--debug-images` | Save the cleaned page images in `_cache` |

Everything else, such as keyword classes, table header names and thresholds, is in the **`Settings`** class near the top of `spec_extractor.py`, with an explanation next to each value.

---

## 4. Recommended review routine

1. In `<name>_extracted.xlsx`, **filter "Needs Review" = Yes** first. The *Review Reasons* column says exactly what to check and on which page. Typical reasons:
   * A word not in the English dictionary.
   * Accent marks removed from a word.
   * A stray period or apostrophe.
   * A number read with low confidence, or a number containing a letter (`1O0`).
   * An ID that differs by one character from another ID in the document (`MIL-STD-810H` / `MIL-STD-810B`, `SPEC-1234-A` / `SPEC-1284-A`). A different digit in the running number at the end is ordinary numbering and is not flagged (`SW-001` / `SW-002`, `ICD-1204A` / `ICD-1205A`), so a misread in that last number (`1553B` read as `1558B`) is only caught by the confidence check.
   * A keyword that had to be repaired (`sha11` → `shall`).
   * Text joined across a page break.
   * A list stem with no items below it.
   * A verification method that came from a matrix whose column headers could not be read, so the methods follow the order given in the legend.
   * A sentence with a keyword that is printed in the header or footer of many pages (for example a handling notice). It is reported once, with the pages it appears on.
2. Open `<name>_verification.docx` and compare each page image with the text under it. Every requirement sentence should carry an `[R-…]` tag, and every table should match cell by cell.
3. Check the **Page Quality** sheet. Pages graded *Poor* deserve a full read. A page graded **FAILED** could not be read at all (for example a damaged TIFF page); the rest of the document is still processed, and the run log says which pages failed.
4. *Quality Notes* are not OCR problems. They are INCOSE-style writing checks on the requirement itself: TBD/TBR, vague terms, escape clauses ("as appropriate"), open-ended lists, and/or, and compound requirements.
5. Check that **Run Info** says *Tested configuration: Yes*. *NO* means the Python or package versions differ from the tested set (each difference is listed in that cell), so the accuracy figures in section 6 do not apply to the run.

> Words of your own program that the dictionary does not know (part names, acronyms written in lower case) can be added to `extra_dictionary_words` in `Settings`, so they are not flagged. Common engineering words (uplink, checksum, boresight, …) are already accepted.

> Why not just trust the OCR confidence? Testing showed that most real misreads on degraded scans still scored above 0.95. For example, "telémetry", "fro" (for "from") and "16.AWG" were all "confident". The review flags therefore combine confidence with independent checks: dictionary, accent marks, punctuation, number and ID consistency. Treat the flags as a strong filter, not a guarantee. On important documents, still read the requirement rows against the scan.

---

## 5. How it works (pipeline)

1. **Load pages.** PDFs are rendered with pypdfium2 at the scan's own resolution; TIFF/PNG/JPG are read with Pillow. Multi-page TIFF, 1-bit fax and non-square fax pixels (204×98 dpi) are handled.
2. **Clean the image (OpenCV).** Pages are resized to about 220 dpi (a page with no resolution recorded, or one recorded as a screen resolution, has its resolution estimated from the height of its printed characters; a page exported at screen size is enlarged up to four times to bring it near 220 dpi, within the memory limit), turned upright (orientation classifier, confirmed by OCR), straightened with projection-profile deskew (accurate to about 0.05°), and cleared of binder punch holes. Stains, shadows and yellowing are flattened and specks removed with a light median filter. This combination measured best; hard black/white binarization made the deep-learning OCR worse.
3. **OCR.** PaddleOCR **PP-OCRv6** text detection and recognition, run by **RapidOCR** on ONNX Runtime, gives word boxes and confidences.
4. **Layout.** **img2table** finds ruled tables, and borderless tables are found from text alignment. Where a table rules its columns but prints no line between its rows - the usual layout of a verification matrix, and one that is otherwise missed completely, because a row needs two horizontal lines before it exists - the missing separators are worked out from where the text sits. That reading is used only where the printed ruling lines cannot describe the table (nothing was found, or its rows have each swallowed several rows of text); a table that draws all of its lines keeps exactly the grid it had, and if the worked-out reading turns out not to look like a table, the printed one is used after all. Column headers printed sideways, as narrow method columns nearly always are, are read by turning that band upright and reading it again, and each header is put back on the column its ink was printed over. Rows worked out this way are then grouped into **records**: a row of the table plus the lines its cells wrap onto. A cell that wraps must not become a row of its own, so the grouping follows the table's key column where it has one (a value in the left-hand column starts a record; a line without one continues the record above) and otherwise the table's own leading - the lines inside a record sit closer together than the records do, and both spacings are constant through a table, so the dividing line is measured from that table rather than fixed in advance. A **legend band** across the top of a matrix ("LEGEND: 1 = First article  2 = Periodic  A = Visual …", printed above the column headers and spanning the whole width) is recognised as its own row, so the headers below it are still read as headers and the wrapped label of a narrow first column (*Requirement / reference*) does not swallow the first requirement. OCR words are placed into cells; a caption printed inside a table's frame (even over several lines) is taken out again. A **list laid out on tab stops** lines up exactly like a table without ruling lines, and its wide tabs look like the gutter between two text columns; neither is taken as such when the left-hand pieces are list markers or short labels ("a.", "Acceleration:") sitting on the same lines as the text to their right, or when a would-be table's first column counts a., b., c. (or holds only labels, when the bullets were too faint for the OCR). A table with a real third column of short repeated entries (a Method column: *Test*, *Analysis*), a header row or its caption right above it (or directly under it) stays a table, even under a lead-in. Two text columns are kept apart when the right-hand one reads as running text (lines that carry a sentence on from one line to the next), holds numbered paragraphs, or holds a list of its own. Once a band of whitespace is found to be a list's tab stops, it is not judged again for a few rows of the same list on their own. Each item then keeps its label and value together, and a line that starts in the item's label or value column stays with the item whatever it begins with. A label that wraps onto a second line is read before the value beside it. Figures are found as non-text graphics, reading order comes from a recursive XY-cut (which handles columns), and lines are grouped into headings, paragraphs and list items. A line only ends a block when there is evidence: final punctuation, a larger gap, a list marker, or a line that stops short of its column's edge although the next word would have fitted. So a number, unit or designator at the start of a wrapped line ("12. The…", "3.3 V…", "F-35…", "(CB12)") stays in its sentence, on one- and two-column pages and with any line spacing. Numbered lines that follow "NOTES:" or a stem, or that follow each other as sentences ("1. Note text…", "2. …"), are list items rather than headings; "3. REQUIREMENTS" stays a heading.
5. **Document clean-up.** Running headers/footers and page numbers are removed. Paragraphs and tables that continue on the next page are joined (in page order), words hyphenated at line ends are re-joined, and captions are linked to their table or figure. Caption linking learns whether the document puts captions above or below, then matches all captions on a page at once, so a caption cannot take the neighbouring table.
6. **Requirement extraction.** Deterministic, auditable rules (details below).
7. **Export** to Excel (openpyxl) and Word (python-docx).

### Requirement rules (section 9 of the script)

* A **sentence containing a keyword** is a requirement. The class follows MIL-STD-961E usage: *shall/must* = Mandatory, *should* = Goal, *will* = Statement of intent. A following sentence that starts with "This/These/It/Such…" is kept with it.
* The **paragraph number** (`3.2.1.4`, including OCR-damaged `3.2.i.4`), the **inline title** and **explicit IDs** (`[SRS-101]`, `PRF-201:`, `(SRS-103)`) are split off into their own columns. Standards such as MIL-STD-461G are never mistaken for requirement IDs.
* A faint scan can lose the space after a paragraph number, or read it as a speck of dirt (`4.2Extended verification.`, `3.2.2.2.Input power.`). Both are repaired, while list markers (`1.Built-in test`), part numbers (`MIL-STD-1553B`) and file names are left exactly as read.
* A faint scan can also lose the **blank line between two numbered paragraphs**, leaving both in one block. Each number found inside a block starts a new paragraph, so every requirement keeps the number and title it was written under instead of inheriting the one above. A cross-reference in running text ("… as defined in 3.2.1. Testing shall …") and a quantity ("3.3 V shall …") are not mistaken for one.
* A keyword sentence that **leads into a list** is a stem, and each list item below it becomes a row. It usually ends in ":", but the colon is often left out, or lost on the scan, so a sentence ending with a lead-in phrase counts too: *… each of the following.*, *… within the following limits.*, *… as follows.*, *… as specified below.* Without a colon, the items must look like items: a marker, a label, or a run of two or more short lines indented level with each other that state no requirement of their own ("Own ship position and heading." / "Target range and bearing."); a single sentence after *… on the following day.* is not a list. (A lead-in phrase with nothing under it is simply a requirement. A colon with nothing under it is flagged, and so is a lead-in phrase followed by one short indented line that was not taken as an item.) A stamp or figure between list items does not break the list. Because a marker can be misread (`e.` for `c.`, `3.` for `8.`) or lost altogether, **indentation outranks the marker character**: an item that keeps the list's indentation stays in the list even when its letter or number makes no sense, and a numbered line at a list's indentation is an item rather than a heading. In a list with labels, an item whose marker was lost starts with its label in the label column, which is enough to recognise it. An item that loses its marker in a list **without** labels starts exactly where a wrapped line of the item above would; when the markers either side show the gap (`a.` then `c.`, in a list that otherwise counts up one at a time), the item above is split where the new sentence starts and the lost item gets its letter back from the sequence (reported). A list that counts in twos (tests 1, 3, 5) is left as printed. *Known limitation:* the last item of a list has no marker after it to show the gap, so if it loses its marker it stays joined to the item above.
* **Numbers must follow in sequence.** Paragraph numbers count up: after 3.2.4 may come 3.2.4.1, 3.2.5, 3.3 or 4, and up to three may be skipped, because a scan can miss a heading. A number that fits none of these - 1.5 or 20 after 3.2.4 - is a value that happens to start a line ("1.5 V peak-to-peak", "20 Hz to 2000 Hz"): it does not start a new section, end a list, or split a paragraph. The other way round, a line that starts with exactly the number that should come next (3.5.1 under 3.5) starts a new paragraph even when a speck made the line above look unfinished. **List markers count up the same way** (a, b, c / 1, 2, 3 / i, ii, iii / (a), (b)): a marker the scan misread ("C." for "c.") or lost is taken from its neighbours, and *Review Reasons* says so ("List marker read as 'C.' - taken as 'c.' from the sequence"), because the letter came from the tool rather than the page. The same misread - a capital read as the small letter of the same shape (c, o, s, v, w, x, z) - is allowed for in a paragraph title (`3.2.7 output. The …` keeps its number) and in a label (`current:` still starts its own item). A list that really skips a letter keeps its letters: a valid marker is only replaced when the next item confirms the expected one. A notice between or after the items ("NOTE:", "WARNING:", "CAUTION:") is never numbered and keeps a row of its own, and a requirement ID on tab stops ("SRS-101:   The software shall …") stays the requirement's ID rather than becoming a list label. Each level of a nested list is judged on its own (`A.`, `B.` with `a.`, `b.` below them keep their capitals). Several lost markers are counted from the nearest letter the scan kept, also at the start of a list (`Acceleration: …`, `Vibration: …`, `c. Shock: …` gives a., b., c.). A block between two items that cannot be an item - the letter it would get belongs to a later item - is joined to the item above it at its own level when it is only a piece of text, and keeps its own row, unnumbered, when it states a requirement of its own or leads into a list of its own. A numbered list is never mistaken for section headings by the paragraph after it: `1.` `2.` `3.` followed by `3.2.5 Weight. …` are list items; only a title-like last line followed by its own first sub-paragraph (`4. Verification` then `4.1 General. …`) is a heading. A blank line under an item that has finished its sentence ends the item: a paragraph after it is a requirement of its own, and a value only goes on past a blank line in its value column.
* A **table** is a requirement table when a column header names the requirement text (*Requirement*, *Requirement Text*, *Shall Statement* – not *Requirement ID/Type/Title*; then every row counts), or when most cells of a column contain a keyword. Headers are read from every header row, so a banner merged across the top (*VERIFICATION METHOD* above *I / A / D / T*) does not hide the real column names. The ID column is found by header (*Req ID, Requirement No., Para* …) or by content, and a *Method/Verification* column fills the verification method.
* Garbled keywords are repaired only for exact OCR patterns (`sha11`, `shaII`, `rnust`, `wi11`). Real words such as *shell*, *small* or *most* never match, and every repair is listed in *Review Reasons*.
* A word the document repeats is normally a term of the program's own, not a misread, so it is not flagged. But OCR repeats *its* mistakes too - the same word read the same wrong way on every page - and those are the errors most easily missed. So a repeated word that is in no dictionary is still flagged when the document **also writes the ordinary English word one edit away from it** (`systen` printed beside `system`). A term of the program's own has no such twin in its own document and stays unflagged.

---

## 6. Accuracy measured on the test documents

The `tests` folder builds realistic synthetic specifications with **exact ground truth**. Real controlled documents cannot be used for automated testing, and public scans have no ground truth. The documents are:

* A MIL-STD-490-style system specification in typewriter font, with numbered paragraphs, stem + list, three tables and a figure.
* A software requirements specification with bracketed IDs, bullets, a borderless table, figures and an upside-down page.
* A fax-quality interface control document with a sideways landscape table page.
* A "hard layout" specification made of the problems found in two independent reviews of the tool: a paragraph continued on the next page; a number, a unit and a designator at the start of wrapped lines ("12. The…", "3.3 V…", "F-35…", "(CB12)"); a unit abbreviation ending a sentence ("100 ms. The…"); all-caps, numbered and unmarked list items; a list item printed in the footer area; a figure between two list items; captions below tables; a two-line caption drawn inside a table frame above a merged cell; requirement tables headed "Shall Statement" and "Requirement ID / Requirement Type / Requirement Text"; a handling notice with a "shall" in every page footer; and a two-column page with double-spaced paragraphs next to single-spaced notes.
* A **tabbed-list** specification (two pages): lists whose marker, label and value are separated by wide tab stops, with values that run over several lines and start with numbers ("2.5 C per minute", "3.5 Seconds"), lead-ins with and without a colon, `a.` `1.` and `(1)` markers, and a heading and paragraphs after each list. It is scored with the item letter in the paragraph number (`3.2 a`), so a wrong or missing marker counts as an error.
* A **table-structure** specification, built from the failures found when the tool was run against real Systems Engineering material: a verification cross-reference matrix whose **columns are ruled but whose rows are not**, and whose method headers are **printed sideways**; a wide, very sparse qualification matrix (six method columns, one tick per row); a requirement table whose two right-hand columns sit under one merged *VERIFICATION* banner, so it has two header rows; and a **quality conformance matrix in the shape users reported as broken** - a legend band across the top ("1 = First article … A = Visual …"), then a header row of eleven columns (*Requirement reference, 1, 2, 3, 4, A, B, C, D, AQL or percent, Inspection method*), column rules drawn and **no line between the requirements**, with the first column narrow enough that its label wraps onto a second line.

* Two **supplied page images**, kept exactly as they were given, at their own resolution - a specification exported at screen size rather than scanned (about 64 dpi). They carry five table shapes in one place: a verification matrix with column rules and no line between the rows; a requirement table with no ruling lines at all; one boxed with a line under the headers only; a borderless table whose second and third columns wrap at the same time; and a fully ruled table as the control. They live in `tests/pages/` and are the one test whose input was not generated here.

Each rendered document was then "aged" into:

| Version | Damage applied |
|---|---|
| Office scan | 300 dpi, skew, noise, JPEG |
| Photocopy | 200 dpi, faded ink, speckle, punch holes, dark copier edges |
| Fax | Bilevel G4, 204×98 dpi |

Results of the current version (38 pages in 10 files, `python tests/run_regression.py`):

| | Clean / office scan | Heavy photocopy | Fax | Supplied pages (≈64 dpi) |
|---|---|---|---|---|
| Requirements found (recall) | 100 % | 100 % | 100 % | 100 % |
| Extracted rows that are real requirements (precision) | 100 % | 100 % | 100 % | 100 % |
| Paragraph number / requirement ID correct | 100 % | 100 % | 100 % | 100 % |
| Requirement text exactly right | 100 % | 67–81 % | 43 % | 50 % |
| Character errors in the requirement text | 0 % | 0.3–1.0 % | 1.9 % | 0.6 % |
| Captions and tables found, each table linked to its own caption | all | all | all | all |

Of the 24 requirement rows that still contained an OCR character error, **21 were flagged** *Needs Review* (88 %), and one correct row was flagged (a "115" that the OCR itself read at 0.51 confidence - the cautious direction). The three unflagged errors are a "95%" read as "958", a "150 km" read as "150 kn" and a "45 kilograms" read as "45.kilograms": in each the misread token carries a digit, which no dictionary can check.

Table **cells** are 100 % right on the clean and office scans of the ordinary documents and 97 % on the table-structure document, where the sideways headers are read from a quarter-turned crop and lose a character or two. On the heavy photocopies cell accuracy is 82–100 %, on the supplied low-resolution pages 90 % and on the fax 71 %; those are OCR misreads inside cells that were correctly found and correctly divided into rows and columns, and they are flagged for review.

The same test was re-run for 1.2.0 on Python **3.10, 3.11, 3.12 and 3.13**. All four pass, and their results are identical: every cell of every Excel sheet matches (apart from the run information), so the figures above apply to each of them. **Python 3.14 has not been re-run since release 1.0.1**, where it also passed (see section 9). On 3.13 and 3.14 the OCR-based orientation check costs a few seconds per page - about 13 s per page against 7.6 s on 3.12 on the single-core test machine.

Page orientation was right in 32 of 32 tests (every quarter turn of 8 different pages, among them a title page and pages with only a few lines at their top or foot), with the orientation classifier (Python 3.11) and without it (3.13). Processing took 5–9 s per page (6.4 s on average) on a 2-core virtual machine; typical laptops with more cores are faster. After the OCR, a synthetic 300-page document with a 40-row table on every page needed about one minute for document clean-up, extraction, Excel and Word output.

The requirement text errors that remain are OCR misreads of damaged print (for example "fro" for "from", "958" for "95%"). They are left as read, never silently "corrected", which is why the review flags matter.

**The test-case library.** Besides these documents, `tests/cases` holds 149 small scans, each showing one situation the tool must get right or once got wrong - a list on wide tab stops, a marker the scan lost, a lead-in without a colon, a heading after a list, a list beside a column of prose, a table under a lead-in, a list that carries on over a page break - with the exact rows it must produce. Each has a fixed ID such as `TAB-01`, and `tests/cases/CASEBOOK.pdf` shows them all, one page per case. 136 of them pass; the 13 marked there as *known limitations* are what the tool still gets wrong, each with a description of what happens instead (see section 9).

**Real documents will differ.** Before relying on the tool for a program, run a pilot of 20–30 pages of your own documents and compare against a manual extraction.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `Missing Python packages` | Run `setup_windows.bat` again, or `python -m pip install -r requirements.txt -c constraints.txt`. If the message also says the Python version is not a tested one, install the 64-bit Python 3.12 first |
| `setup_windows.bat` says *No supported Python was found* | Install the 64-bit Python 3.12 from python.org (python.org installer: tick *Add python.exe to PATH*; Python install manager: run `py install 3.12`), then run the setup again. Python 3.15 and newer, 32-bit Python and the free-threaded build are not supported |
| The run log or *Run Info* says **NOT the tested configuration** | The Python version or a package version differs from `constraints.txt`; the message lists each difference. Delete the `.venv` folder and run `setup_windows.bat` again (other systems: `python -m pip install -r requirements.txt -c constraints.txt`). The results are still written, but the accuracy in section 6 was not measured for that setup. A Docling run is always reported this way, because the Docling engine's accuracy has not been measured |
| pip cannot reach the internet | Configure pip for the company proxy or mirror, or use the offline `wheels` method (section 2) |
| `ImportError` mentioning `cv2` | The OCR and table libraries each install an OpenCV build into the same folder, and one of them was damaged. Run `python -m pip install --force-reinstall --no-deps -c constraints.txt opencv-contrib-python` (the most complete build, in its tested version) |
| "the PDF is password-protected" | Save an unprotected copy (with permission) and run again |
| A page is text but nothing was found | Look at *Page Quality* and the Word report. Try `--dpi 300` for very small print, or `--remove-color-marks` for colored stamps |
| Every line of a table cell became its own table row | Fixed in 1.1.1. If it reappears, the table's records are not being told from its wrapped lines: check the Word report to see how the page was grouped, and try `--no-inferred-rows` to see whether the row inference is responsible |
| A verification matrix came out as **one huge row**, with every X bundled together | Fixed in 1.2.0 for the usual shape: a legend band across the top, a header row, column rules and no line between the requirements. If it reappears, the rows are not being found from the text: check the Word report to see how the page was grouped, and send the page to the maintainer - a fixture of that exact shape is the way these get fixed |
| A list item has only its label ("a. Acceleration:") and its value appears elsewhere, or later items are missing | Fixed in 1.3.0: wide tab stops between marker, label and value are no longer taken for text columns or for a borderless table. If it reappears, check the Word report: if the values sit in paragraphs of their own, the layout step split the items - send the page to the maintainer. Test cases TAB-01 to TAB-54 cover these layouts |
| A list entry was joined to the one before it | The scan lost that entry's letter or number, so its line looks like a wrapped line of the item above. When the letters either side show the gap (`a.` then `c.`), the item is split where the new sentence starts and the entry gets its letter back, marked *List marker missing - taken as 'b.' from the sequence*; when the split point is not clear, the item before the gap is flagged (*The list goes from 'a.' to 'c.' …*). An entry that lost its marker at the END of a list has no letter after it to show the gap - correct it in the Excel file Test cases LST-03 to LST-12; a lost marker on the LAST item of a list is not found yet (LST-24) |
| List items lost their values right above a two-column section | *Known limitation* (test case COL-13): when a list on wide tab stops is followed directly by text set in two columns, with no full-width line between them, the list's tab and the column gutter merge into one band and are read as columns. The values are still in the Word report and the *Full Text* sheet; add them to the rows by hand |
| A table under "… the following characteristics:" came out as list rows, or a list came out as a table | A borderless grid under a lead-in is read as a list when its first column holds labels ("Voltage:") or list markers. It stays a **table** when it has a real third column of short repeated entries (a Method column: *Test*, *Analysis*), a header row, or its caption ("TABLE I. …") right above it or directly under it. (A caption after a blank line under a list usually belongs to the next table, so it does not count.) Check the Word report; the text is kept either way Test cases TBL-01 to TBL-21; labels that are abbreviations with a full stop ('Min.', 'Temp.') still make a table read as a list (TBL-15, TBL-16) |
| A page image looks fine but the text is read badly | Check *Scan dpi* and *OCR dpi* in the **Page Quality** sheet. A page exported at screen size (roughly 60-100 dpi) is enlarged automatically, but a photograph of a page, or a page cropped to part of a sheet, can still be too coarse to read: re-export or re-scan it at 200-300 dpi |
| A list became normal paragraphs, or a table was missed | Check the Word report for how the page was grouped. Very faint ruling lines can make a ruled table fall back to text; the text and requirements are still extracted |
| A result looks wrong for a particular layout | Look the layout up in `tests/cases/CASEBOOK.pdf`: each test case shows one situation, the rows the tool must give for it, and - for the ones marked *known limitation* - what the tool does instead. Quote the case ID (for example LST-20) when reporting a problem, or send a page of the same shape |
| Excel file "is open in another program" | The tool saves a copy with the time added to the name |
| Dragging a file onto `run_extractor.bat` does nothing or shows an error | The file or folder name probably contains `&`. Rename it, or double-click the .bat and use the file picker |
| A page is graded **FAILED** in *Page Quality* | That page could not be read (usually damaged in the file). The other pages were processed. Results with a failed page are not cached, so simply running again retries it; if it fails again, open the page in an image viewer, and if it opens, save/print it to a new PDF and run that |
| Slow on large batches | Normal on CPU. Unchanged files re-use `_cache`. `--threads N` sets CPU threads |
| Python 3.13 or 3.14 | Works, with the same accuracy; page orientation is checked with a slower OCR-based method (a few seconds more per page). Python 3.11/3.12 is faster. Do not force-install the orientation classifier on 3.13/3.14: it was not tested there, and runs would be reported as *not the tested configuration* |

---

## 8. Optional Docling engine (more advanced layout/table AI)

`--engine docling` uses **IBM Docling** (MIT license): the Heron layout model and TableFormer, which handles complex table structure with merged cells. It runs on top of the same cleaned pages and the same PP-OCRv6 OCR. Try it if your documents have complex multi-column layouts or tables without ruling lines.

```bat
python -m pip install -r requirements-docling.txt -c constraints.txt   (large: includes PyTorch)
python spec_extractor.py spec.pdf --engine docling
```

* Docling downloads its models (a few hundred MB) from **Hugging Face** on first use. **Offline or blocked networks:** on a computer with access, run `docling-tools models download -o docling_models`, copy the folder over, and pass `--docling-models path\to\docling_models`.
* If Docling or its models are unavailable, the tool says so and **automatically continues with the standard engine**.
* With an NVIDIA GPU and a CUDA build of PyTorch, Docling can use the GPU (`--device cuda`).
* Status in this release: the Docling integration is tested (setup, fallback, and mapping of real Docling output into the Excel/Word exports). Its accuracy on the aged test documents could **not** be measured in the development environment, because Hugging Face was blocked there. Compare both engines on a pilot set. Until then, Docling runs are reported as *not the tested configuration*.
* `constraints.txt` keeps the standard engine's packages at their tested versions; pip resolves them together with Docling 2.128 without conflicts. Docling's own packages are not pinned.

---

## 9. For maintainers

* `spec_extractor.py` is one file in 12 numbered sections, listed at the top of the file. All tunable values are in `Settings`.
* **After any change**, run the three test levels (install once: `python -m pip install -r requirements-dev.txt -c constraints.txt`):
  * `python tests/test_rules.py` takes seconds and needs no OCR. It feeds realistic page geometry through the layout, clean-up and extraction rules: text across a page break, numbers/units/designators at the start of wrapped lines, headings without a period, unmarked lists, footer-zone items, captions inside table frames and below tables, merged cells, page selection, output names, a damaged page, and more. The table-structure tests draw a **real page image** and run the real detector on it, because those failures are in how the ruling lines (or the absence of them) are read: a table with column rules and no row lines, a fully ruled table that must be left alone, a cell that wraps and must not be split, sparse verification matrices, sideways headers and the arithmetic that maps them back onto their columns. It also checks that `constraints.txt`, the `requirements*.txt` files and `setup_windows.bat` agree on the supported Python versions and packages, and it ends by saying whether it ran on the tested configuration. Add a test here for every new rule or bug.
  * `python tests/run_regression.py` takes a few minutes. It builds the synthetic scanned documents, runs the whole tool, scores it against exact ground truth (requirement recall/precision, paragraph numbers, captions, caption-to-table links, tables, review flags) and prints PASS/FAIL. `--reuse` skips the OCR.
  * `python tests/cases/run_cases.py` takes ten to twenty minutes. It runs the whole tool, with the real OCR, on the **test-case library**: 149 small scanned documents, each showing **one situation** the tool must get right - lists on wide tab stops, list markers the scan lost or misread, lead-ins with and without a colon, paragraph numbers and headings, paragraphs after a list, two-column pages, tables beside lists, page breaks - together with the exact rows it must produce. Every case has a fixed ID (`TAB-01`, `LST-07`, `PAGE-02` ...): use it to refer to a situation in a report, a review or a commit. **`tests/cases/CASEBOOK.pdf`** is the catalog - one page per case with the situation, what the tool must do and why, the page itself and the rows expected - and `python tests/cases/build_cases.py` draws the scanned documents into `tests/cases/documents/` (one PDF per case, named by its ID) so that any case can be opened and looked at, or run through the tool on its own. A case marked **known limitation** is one the tool still gets wrong; it is kept, with what happens instead, and does not fail the run. Every other case must pass. Each run lists the cases whose result changed since the previous run, and writes the full comparison to `tests/cases/_results/case_report.txt`; `--only TAB` runs one area, `--only TAB-07` one case. **To add a case**, write its page and rows in the right `tests/cases/area_*.py` file (the format is explained at the top of `tests/cases/casekit.py`) under the next free ID, then run `build_cases.py` to draw it and rewrite the catalog; `test_rules.py` fails until the catalog is up to date.
* **Table detection** lives in section 6c and turns on three questions, each in its own function, so a misbehaving document can be traced to one of them: `_rows_are_under_split` (did the printed ruling lines really describe this table, or has each row swallowed several rows of text?), `_plausible_borderless_table` / `_reads_like_prose` (is this a table at all, or tidy-looking running text?) and `_is_mark_matrix` (is it a verification matrix, which is mostly empty on purpose and must not be judged on how many of its cells are filled?).
* Rows that had to be worked out from the text are grouped into records by `_record_breaks` (the key column, else `_gap_threshold` on the table's own leading) and joined by `_merge_continuation_rows`; the same grouping drives the borderless detector, so both read a wrapped cell the same way.
* Each area of a page is read up to three ways, and `_better_row_split` puts them in the order to try: as the printed ruling lines describe it; with the missing separators inferred by img2table; and, when that inference gives up - it does on badly degraded scans, where the ink is too broken for it to measure a row pitch - with the rows cut from the text by `_resplit_rows`. A reading that the checks above then reject falls back to the next one, so a table is never lost by trying to improve it. Both behaviours can be switched off, with `--no-inferred-rows` and `--no-sideways-headers`; that is the quickest way to tell whether one of them is behind a surprising result.
* **Tested configurations.** Release **1.3.0** passed the rule tests and the regression on 64-bit Python 3.10.20, 3.11.15, 3.12.3 and 3.13.12 with the package versions in `constraints.txt` (the tests ran on Linux; Windows installs the same package versions), with identical scores on every one of them, and the test-case library (`tests/cases/run_cases.py`) on 3.11 and 3.13: 136 cases pass, and the other 13 are the known limitations, still wrong as the catalog describes. **Python 3.14 was not available where 1.3.0 was built, so it has not been re-run since release 1.0.1: run both test levels on 3.14 before handing this version out.** Release 1.0.1 passed on 64-bit Python 3.10.21, 3.11.16, 3.12.3, 3.13.15 and 3.14.6. To add a Python version or change a package version: update `SUPPORTED_PYTHON` in `spec_extractor.py`, the search list and `PY_CHECK` in `setup_windows.bat`, `constraints.txt` and this README; install; run both test levels on **every** supported version; hand the folder out only when all of them pass.
* The OCR cache (`_cache`) holds the page layout too. It is keyed on the file, the OCR settings, the requirement keywords (the layout rules protect keyword sentences) a fingerprint of the code sections that produce it (3–6 and 8) and the tool version (so a new release reads documents again once). Editing that code therefore re-reads documents automatically, while changes to the requirement rules and exports (sections 7, 9–12) re-use the cache. Documents with a page that could not be read or saved are not cached.
* `tests/make_test_corpus.py` shows how to add new document styles with ground truth, and `tests/evaluate.py --details` lists every miss, extra, wrong paragraph number and wrong caption link.

### Technology and licenses

| Component | Role | License |
|---|---|---|
| RapidOCR 3.9 + PaddleOCR PP-OCRv6 models | OCR | Apache-2.0 |
| ONNX Runtime | Inference | MIT |
| img2table | Table grid detection | MIT |
| OpenCV | Image processing | Apache-2.0 |
| pypdfium2 | PDF rendering | Apache-2.0 / BSD-3 |
| Pillow | Image reading | MIT-CMU |
| openpyxl | Excel output | MIT |
| python-docx | Word output | MIT |
| pyspellchecker | English word list (frequencies from OpenSubtitles) | MIT |
| rapid_orientation | Page orientation | Apache-2.0 |
| Docling (optional) | Layout/table AI | MIT; models Apache-2.0 / CDLA-Permissive-2.0 |

These were deliberately **not** used:

* PyMuPDF and MinerU: AGPL or revenue-limited licenses.
* Marker/Surya/Chandra model weights: free only below a revenue threshold.
* Some newer vision-language OCR models: license terms exclude commercial or military use.
* Generative vision-language OCR in general, as the main transcriber: it reads bad scans well but can silently invent or "correct" words and numbers, which is not acceptable for requirements.

Check dependency licenses and the handling of controlled technical data with your own IT/export-control office before use.
