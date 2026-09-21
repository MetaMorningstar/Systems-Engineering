# Spec Extractor

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

* **Verification method** comes from the requirement table's Method column. Otherwise it is looked up in the document's verification cross-reference matrix, an I/A/D/T table.
* **References** lists the standards, tables, figures and sections a requirement cites, e.g. `MIL-STD-704F; TABLE II`.

Requirements are recognised in all the usual layouts:

* **Numbered paragraphs**, e.g. `3.2.1.4 Operating temperature. The radar shall …`. Paragraph number and title go into their own columns, and each "shall" sentence becomes its own row.
* **Stem + list**, e.g. `The radar shall provide the following modes: a. Search. b. Track.` This gives one row per item ("stem + item"), including nested lists and widely spaced lists. `--keep-list-stems` gives one row per block instead.
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

All five supported versions passed both test levels (section 9) with the exact package versions in `constraints.txt`. Every run states whether it used this **tested configuration**: in the first lines of the run log, in the *Tested configuration* row of the Excel **Run Info** sheet (the installed versions are listed below it) and in the header of the Word report. If it says **NO**, the accuracy figures in section 6 do not apply to that run; see section 7.

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
2. **Clean the image (OpenCV).** Pages are resized to about 220 dpi, turned upright (orientation classifier, confirmed by OCR), straightened with projection-profile deskew (accurate to about 0.05°), and cleared of binder punch holes. Stains, shadows and yellowing are flattened and specks removed with a light median filter. This combination measured best; hard black/white binarization made the deep-learning OCR worse.
3. **OCR.** PaddleOCR **PP-OCRv6** text detection and recognition, run by **RapidOCR** on ONNX Runtime, gives word boxes and confidences.
4. **Layout.** **img2table** finds ruled tables, and borderless tables are found from text alignment. OCR words are placed into cells; a caption printed inside a table's frame (even over several lines) is taken out again. Figures are found as non-text graphics, reading order comes from a recursive XY-cut (which handles columns), and lines are grouped into headings, paragraphs and list items. A line only ends a block when there is evidence: final punctuation, a larger gap, a list marker, or a line that stops short of its column's edge although the next word would have fitted. So a number, unit or designator at the start of a wrapped line ("12. The…", "3.3 V…", "F-35…", "(CB12)") stays in its sentence, on one- and two-column pages and with any line spacing. Numbered lines that follow "NOTES:" or a stem, or that follow each other as sentences ("1. Note text…", "2. …"), are list items rather than headings; "3. REQUIREMENTS" stays a heading.
5. **Document clean-up.** Running headers/footers and page numbers are removed. Paragraphs and tables that continue on the next page are joined (in page order), words hyphenated at line ends are re-joined, and captions are linked to their table or figure. Caption linking learns whether the document puts captions above or below, then matches all captions on a page at once, so a caption cannot take the neighbouring table.
6. **Requirement extraction.** Deterministic, auditable rules (details below).
7. **Export** to Excel (openpyxl) and Word (python-docx).

### Requirement rules (section 9 of the script)

* A **sentence containing a keyword** is a requirement. The class follows MIL-STD-961E usage: *shall/must* = Mandatory, *should* = Goal, *will* = Statement of intent. A following sentence that starts with "This/These/It/Such…" is kept with it.
* The **paragraph number** (`3.2.1.4`, including OCR-damaged `3.2.i.4`), the **inline title** and **explicit IDs** (`[SRS-101]`, `PRF-201:`, `(SRS-103)`) are split off into their own columns. Standards such as MIL-STD-461G are never mistaken for requirement IDs.
* A keyword sentence **ending in ":"** is a stem, and each list item below it becomes a row. A stamp or figure between list items does not break the list.
* A **table** is a requirement table when a column header names the requirement text (*Requirement*, *Requirement Text*, *Shall Statement* – not *Requirement ID/Type/Title*; then every row counts), or when most cells of a column contain a keyword. The ID column is found by header (*Req ID, Requirement No., Para* …) or by content, and a *Method/Verification* column fills the verification method.
* Garbled keywords are repaired only for exact OCR patterns (`sha11`, `shaII`, `rnust`, `wi11`). Real words such as *shell*, *small* or *most* never match, and every repair is listed in *Review Reasons*.

---

## 6. Accuracy measured on the test documents

The `tests` folder builds realistic synthetic specifications with **exact ground truth**. Real controlled documents cannot be used for automated testing, and public scans have no ground truth. The documents are:

* A MIL-STD-490-style system specification in typewriter font, with numbered paragraphs, stem + list, three tables and a figure.
* A software requirements specification with bracketed IDs, bullets, a borderless table, figures and an upside-down page.
* A fax-quality interface control document with a sideways landscape table page.
* A "hard layout" specification made of the problems found in two independent reviews of the tool: a paragraph continued on the next page; a number, a unit and a designator at the start of wrapped lines ("12. The…", "3.3 V…", "F-35…", "(CB12)"); a unit abbreviation ending a sentence ("100 ms. The…"); all-caps, numbered and unmarked list items; a list item printed in the footer area; a figure between two list items; captions below tables; a two-line caption drawn inside a table frame above a merged cell; requirement tables headed "Shall Statement" and "Requirement ID / Requirement Type / Requirement Text"; a handling notice with a "shall" in every page footer; and a two-column page with double-spaced paragraphs next to single-spaced notes.

Each was then "aged" into:

| Version | Damage applied |
|---|---|
| Office scan | 300 dpi, skew, noise, JPEG |
| Photocopy | 200 dpi, faded ink, speckle, punch holes, dark copier edges |
| Fax | Bilevel G4, 204×98 dpi |

Results of the final version (27 pages in 7 files, `python tests/run_regression.py`):

| | Clean / office scan | Heavy photocopy | Fax |
|---|---|---|---|
| Requirements found (recall) | 100 % | 100 % | 100 % |
| Extracted rows that are real requirements (precision) | 100 % | 100 % | 100 % |
| Paragraph number / requirement ID correct | 100 % | 100 % | 100 % |
| Requirement text exactly right | 100 % | 78–81 % | 43 % (1.9 % character errors) |
| Captions and tables found, each table linked to its own caption | all | all | all |

Of the 13 requirement rows that still contained an OCR character error, 12 were flagged *Needs Review*, and no correct row was flagged. The one unflagged error was "95%" misread as "958".

The same test was run on Python **3.10, 3.11, 3.12, 3.13 and 3.14**. All five pass, and their results are identical: every cell of every Excel sheet matches (apart from the run information), so the figures above apply to every supported Python version. On 3.13 and 3.14 the OCR-based orientation check costs a few seconds per page - about 13 s per page against 7.6 s on 3.12 on the single-core test machine.

Page orientation was right in 32 of 32 tests (every quarter turn of 8 different pages). Processing took 5–9 s per page (6.4 s on average) on a 2-core virtual machine; typical laptops with more cores are faster. After the OCR, a synthetic 300-page document with a 40-row table on every page needed about one minute for document clean-up, extraction, Excel and Word output.

The requirement text errors that remain are OCR misreads of damaged print (for example "fro" for "from", "958" for "95%"). They are left as read, never silently "corrected", which is why the review flags matter.

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
| A list became normal paragraphs, or a table was missed | Check the Word report for how the page was grouped. Very faint ruling lines can make a ruled table fall back to text; the text and requirements are still extracted |
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
* **After any change**, run the two test levels (install once: `python -m pip install -r requirements-dev.txt -c constraints.txt`):
  * `python tests/test_rules.py` takes seconds and needs no OCR. It feeds realistic page geometry through the layout, clean-up and extraction rules: text across a page break, numbers/units/designators at the start of wrapped lines, headings without a period, unmarked lists, footer-zone items, captions inside table frames and below tables, merged cells, page selection, output names, a damaged page, and more. It also checks that `constraints.txt`, the `requirements*.txt` files and `setup_windows.bat` agree on the supported Python versions and packages, and it ends by saying whether it ran on the tested configuration. Add a test here for every new rule or bug.
  * `python tests/run_regression.py` takes a few minutes. It builds the synthetic scanned documents, runs the whole tool, scores it against exact ground truth (requirement recall/precision, paragraph numbers, captions, caption-to-table links, tables, review flags) and prints PASS/FAIL. `--reuse` skips the OCR.
* **Tested configurations.** Release 1.0.1 passed both test levels on 64-bit Python 3.10.21, 3.11.16, 3.12.3, 3.13.15 and 3.14.6 with the package versions in `constraints.txt` (the tests ran on Linux; Windows installs the same package versions). To add a Python version or change a package version: update `SUPPORTED_PYTHON` in `spec_extractor.py`, the search list and `PY_CHECK` in `setup_windows.bat`, `constraints.txt` and this README; install; run both test levels on **every** supported version; hand the folder out only when all of them pass.
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
