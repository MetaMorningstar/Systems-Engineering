# Spec Extractor

> ## Version 1.5.0
>
> Every run prints this version together with a **build** fingerprint of the code that is actually running:
>
> ```
> spec_extractor 1.5.0 (build a1b2c3d commit 4e5f6a7)
> ```
>
> (the two short codes are examples - yours will differ)
>
> The **build** is a fingerprint of `spec_extractor.py` itself, so it changes whenever any line of the tool changes - a merge, a hand edit, a patch that only half applied. The **commit** is shown as well when the folder is a git checkout, which is what identifies a merge. To check a folder is up to date, compare the line a run prints with the version above and with the commit you expect; `python spec_extractor.py --version` prints it without processing anything. The same line is written into the Excel **Run Info** sheet and the header of the Word report, so any result can be traced back to the code that produced it. The version also names the output folder: `extraction_output_1.5.0`.
>
> See [Changing the version number by hand](#changing-the-version-number-by-hand) (section 10) after editing the tool yourself.

Pulls **Systems Engineering requirements, tables and figure/table captions** out of **scanned PDF and TIFF documents** (typewritten, photocopied, faxed, skewed, upside-down…). It produces an Excel dataset where **every row is one complete requirement, one caption or one complete table**, and a Word verification report for checking the result against the scan.

Everything runs **locally on a normal CPU**. After installation it needs no internet connection: the OCR model files are inside the pip package, and no document content ever leaves the computer. The tool also switches off the usage telemetry that ONNX Runtime (the engine that runs the OCR models) would otherwise try to send to Microsoft; a full run was measured to make no outbound connections.

---

## 1. What you get

For each input document, in the output folder:

| File | What it is |
|---|---|
| `<name>_extracted.xlsx` | **Extracted Items** sheet: one row per requirement / table / caption. Columns include page, section, paragraph number or requirement ID, keyword, class (mandatory/goal/intent), **verification method** and **references** (see below the table), plus confidence, review flags and **OCR Corrections** (the words the tool corrected, as `'requ1red' -> 'required'`). A table's row links to its own sheet (`T001`, `T002`, …), which holds the table cell by cell, with its heading row shown as one only when the scan prints it as one. **Document Structure** is the document as an outline: every heading with its level and paragraph number, and every paragraph, list and table under the heading it belongs to, with the section type (scope, applicable documents, requirements, verification …). **Applicable Documents** lists the standards and specifications of section 2, one per row: document number, title, the paragraphs that call it up, and the group it is listed under (*SPECIFICATIONS / Military*). **Full Text** has every text block in reading order. **Page Quality** has per-page scan quality. **Run Info** has the settings, the column help and the *Tested configuration* check ([Python versions](#python-versions)). |
| `<name>_verification.docx` | Page by page: the cleaned scan image, then the text the tool read (headings, paragraphs, lists, real Word tables, captions, figures). The page label ("Page 12 of 40 - text read by the tool") and the page's notes are in the **page header**, so the pages themselves hold only the scan and what was read from it. The scanned document's headings are Word headings at the level their paragraph number gives them (3.1.1 is Heading 3). Words that need a look are **highlighted yellow**, words the tool corrected are **highlighted green**, and blue tags such as **[R-0012]** show which Excel row a sentence became. Its fonts, sizes and spacing can be changed, or taken from your own Word template: see [The look of the Word report](#the-look-of-the-word-report-your-own-template-fonts-sizes-and-spacing). |
| `<name>_for_doors.docx` | The document's own text only - headings, paragraphs, lists, tables, captions and pictures, without page images, labels, tags or marks - in the form IBM DOORS imports cleanly. See [Importing into DOORS](#5-importing-into-doors). |
| `ALL_DOCUMENTS_<date>.xlsx` | All documents in one workbook (only when several files are processed). |
| `spec_extractor_log.txt` | The run log. |
| `_cache\` | Saved OCR results. Re-runs of unchanged files skip the slow OCR step. Safe to delete. |

The output folder is `extraction_output_1.5.0` next to the input (the tool's version is in its name, so the results of two versions never mix); `-o FOLDER` chooses another.

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
* **Inline IDs** such as `[SRS-101] The software shall …` or `SRS-103: …`, also on a tab stop in front of the text (`SRS-101:      The radar shall …`).

How the page is read into **sections, tables and lists**:

* **Sections follow their paragraph numbers.** A numbered paragraph is a heading at the level its number gives it, whatever its indent or spacing on the page: 3.1.1.1 sits inside 3.1.1, which sits inside 3.1. A title run into its text is split off it - `3.2.1 Power input. The equipment shall …` becomes the heading *3.2.1 Power input* and the text *The equipment shall …* on a line of its own - also when the number is indented by a tab and the title is **underlined** instead of ended with a full stop (`    3.2.1  Power input  The equipment shall …`, with *Power input* underlined). An underlined line on its own is taken as a title too.
* **Common specification sections are recognised by their titles** (MIL-STD-961 and MIL-STD-490 layouts): scope, applicable documents, requirements, verification / quality assurance provisions, packaging, notes, definitions, appendixes. In **applicable documents**, each line of a document list is read as one document - its number (`MIL-STD-461G`, `ANSI/EIA-649`, `SAE AS50881`, `QQ-A-250/4` …), its title, which may wrap, and the paragraphs that call it up - under its group title (`SPECIFICATIONS`) and sub-title (`Military`, indented by a tab). Such a list is never taken for a table.
* **A table needs a heading row or a title.** A block of text in columns is a table only when it has a title (`TABLE I. …`) or a heading row printed as one - underlined, bold, in capitals, shaded, with a rule under it, or made of column names (*Parameter / Minimum / Maximum*). Columns with neither are a **list**: each row becomes one entry, with its cells in order. The one exception is the top of a page, where a table carried over from the page before goes on without its heading: it is joined to that table, with its columns matched by position.
* **Look-alike misreads are corrected and shown.** When the scan misread a letter or digit for one of the same shape and exactly one ordinary word comes out of swapping it back - a digit inside a word (`requ1red` → `required`, `c0ntrol` → `control`), or, in a word of six letters or more, letters of nearly the same shape (`systern` → `system`) - the word is corrected, highlighted green in the Word report and listed in the *OCR Corrections* column (for a heading, in the *Document Structure* sheet). The same goes for a capital in the middle of a small-letter word (`sCope`), a number with a letter O in it or an l between digits (`1O0` → `100`, `l5.5` → `15.5`; in text and in table cells, and always flagged for review: a number decides what a requirement says), a list marker that does not fit the sequence (`a.` `b.` `C.` → `c.`), and a word one letter away from a word the document itself writes elsewhere (`governmient` beside `government`; also flagged, because it is a guess). Never changed: a word the document writes twice or more, an acronym in capitals (`UTC`), a term with a capital inside it (`PCIe`, `mAh`, `DoS`), a Roman numeral (`VIII`), a word with its number (`Mode5`, `Note1`), a short word whose letters only look alike (`clk`, `Rcv`), a litre sign or a table's rule beside a number (`20l`, `12|`), and anything else that is not certain. `--no-autocorrect` switches it off.

---

## 2. Quick start (Windows)

1. Install a 64-bit **Python 3.11 or 3.12** from python.org (3.10, 3.13 and 3.14 also work, see [Python versions](#python-versions)). With the python.org installer, tick **"Add python.exe to PATH"**. With the newer **Python install manager**, open a terminal and run `py install 3.12`.
2. Put this folder somewhere (e.g. `C:\Tools\spec_extractor`).
3. Double-click **`setup_windows.bat`**. This is a one-time step of a few minutes that creates a private `.venv` environment with **exactly the package versions the tool was tested with** (`constraints.txt`). It picks a tested Python by itself, and says what to install if there is none.
4. Double-click **`run_extractor.bat`** and pick PDF/TIFF files. If you press *Cancel*, you get a folder picker instead. You can also **drag and drop** files or folders onto `run_extractor.bat` (Windows cannot pass a name containing `&` this way: rename the file, or use the picker). The folder may be on a network share.
5. Open the `extraction_output_1.5.0` folder next to your documents (the name carries the tool's version).
6. Optional: to give the Word report your organisation's look, put your Word template in the `word_style` folder and write its name in the style file `word_style\report_style.ini`. See [Using your organisation's Word template, step by step](#using-your-organisations-word-template-step-by-step).

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

Release 1.4.0 was re-run on Python 3.10, 3.11, 3.12 and 3.13 with the exact package versions in `constraints.txt`; **Python 3.14 has not been re-run since release 1.0.1** (see section 10). Every run states whether it used this **tested configuration**: in the first lines of the run log, in the *Tested configuration* row of the Excel **Run Info** sheet (the installed versions are listed below it) and in the header of the Word report. If it says **NO**, the accuracy figures in section 7 do not apply to that run; see section 8.

---

## 3. Command-line options

| Option | Meaning |
|---|---|
| `-o FOLDER` | Output folder (default: `extraction_output_<version>` next to the input, e.g. `extraction_output_1.5.0`) |
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
| `--no-word` | Write no Word file at all: neither the verification report nor the DOORS-ready file (only the Excel workbook) |
| `--no-doors`, `--no-page-images`, `--no-combined` | Leave out the DOORS-ready Word file, the page images in the verification report (a smaller file), or the combined workbook of a multi-file run |
| `--no-autocorrect` | Change no word and no list marker the OCR misread: `requ1red` and `C.` (after `a.` `b.`) stay as read, and a word or number that the tool would have corrected (in the text or in a paragraph's title) is flagged for review instead, with what it would have become; in a table, its cell is flagged. A list marker the scan lost entirely is still supplied from the sequence (and flagged), and a garbled requirement keyword is still repaired (`sha11` → `shall`), so the sentence is still found as a requirement |
| `--no-keyword-repair` | Do not repair garbled requirement keywords (`sha11`, `shaII`, `5hall`, `rnust` ...): a sentence whose keyword stays garbled is not found as a requirement. The look-alike correction puts only a few of them right, and only where the document writes the garbled word once (`sha11`; not with `--no-autocorrect`) |
| `--word-style FILE` | Use another style file for the Word report's look (default: `word_style\report_style.ini`, see below) |
| `--write-word-template FOLDER` | Write a Word file with every style of the report and a sample of each, to restyle in Word and use as the template, then stop. `make_word_template.bat` does this with one double-click |
| `--no-cache` | Always redo the OCR |
| `--engine docling` | Optional AI layout/table engine (section 9) |
| `--debug-images` | Save the cleaned page images in `_cache` |

Everything else, such as keyword classes, table header names and thresholds, is in the **`Settings`** class near the top of `spec_extractor.py`, with an explanation next to each value.

### The look of the Word report: your own template, fonts, sizes and spacing

The Word report (`<name>_verification.docx`) can be made to look like your organisation's other documents. There are three ways, and they can be combined:

* **Use your organisation's Word template.** The template's fonts, heading styles, colours, page size, margins, header and footer (logo, classification marking, page numbers) are then used for every report. See the steps just below.
* **Restyle the report in Word itself**, with `make_word_template.bat`. See [Restyling the report in Word](#restyling-the-report-in-word).
* **Change single values**, such as a font, a heading size, the spacing or the paper size, in the *style file* `word_style\report_style.ini`. This is a text file of settings that you open in Notepad. See [Changing single values](#changing-single-values-fonts-sizes-spacing-page-layout).

None of this changes what the tool reads or what goes into the Excel file; only the look of the Word report changes. Trying a change is quick. The slow reading of a scan is kept in the `_cache` folder, so running a document again only writes its reports again, which takes seconds.

#### Using your organisation's Word template, step by step

**1. Get the template file.**

* A Word template from your organisation (a `.dotx` file) can be used as it is.
* A Word document that already looks right (a `.docx` file) can be used too. Its styles, page layout, headers and footers are used, but not the text on its pages.
  * The text in its headers and footers does go into every report, including what their fields show, such as a document number, a title or an author's name. So choose a document whose header and footer hold nothing that belongs to that one document, or delete such text from them first.
  * Never use a finished verification report, or any other document with sensitive content: the file stays in the `word_style` folder, and goes wherever that folder is copied. To restyle the report itself, use `make_word_template.bat` (see [Restyling the report in Word](#restyling-the-report-in-word)).
* A `.dotm` or `.docm` file (these can hold macros), or an old `.dot` or `.doc` file, is not used. To make a usable copy:
  1. Open it in Word and choose **File > Save As**.
  2. Set *Save as type* to **Word Template (\*.dotx)**.
  3. If Word asks whether to save it without macros, choose **Yes**.
  4. Word suggests its *Custom Office Templates* folder. Choose the `word_style` folder of step 2 instead, or copy the file there afterwards.

**2. Copy the template into the `word_style` folder.** This folder is inside the tool's folder, next to `spec_extractor.py`:

```text
spec_extractor\
    run_extractor.bat
    make_word_template.bat
    spec_extractor.py
    word_style\
        report_style.ini          <- the style file (step 3)
        Company Report.dotx       <- put your template here
```

**3. Write the template's name in the style file.**

1. Open `word_style\report_style.ini` in Notepad: right-click it, then choose *Open with* > *Notepad*. This is the *style file*; the tool's messages call it that.
2. Near the top, under `[document]`, find the line that is just `template =`, with nothing in front of it. The line a little above it, `;     template = Company Report.dotx`, is only an example: a line that starts with a semicolon (`;`) is a comment, which the tool ignores.
3. Change that line: after `template =`, write the template's file name exactly as it is spelt, including its ending (`.dotx` or `.docx`). Do not add a second `template =` line; a setting written twice stops the run.
4. Save the file with **File > Save**.

```ini
[document]
template = Company Report.dotx
```

* Spaces in the name are fine, and no quotes are needed.
* If Windows hides file endings, File Explorer's *Type* column shows *Microsoft Word Template* for a `.dotx` file and *Microsoft Word Document* for a `.docx` file.
* A template kept in another folder can be given with its full path, for example `template = C:\Templates\Company Report.dotx`.

**4. Run the tool as usual.** Double-click `run_extractor.bat`, or run `python spec_extractor.py ...`. Among the first lines of the run is the look that is used, followed by what was left out of the template or changed in it:

```text
Word report look: template Company Report.dotx (sha256 3f9a1c7e2b40), report_style.ini (nothing changed)
  from the template, its link to an attached template was left out (file:///\\fileserver\templates\Corporate.dotm)
  from the template, field(s) DOCPROPERTY in the footer became the text they showed
  from the template, its own text was left out (only its styles, page layout, headers and footers are used)
```

* These lines are information only; the run goes on.
* The code after `sha256` identifies the template file. Yours will be different. It changes whenever the template is saved again, so it also shows that a new version was used.
* The same lines are written to `spec_extractor_log.txt` in the output folder.
* If the template cannot be used, or the style file has a mistake, the run stops at this point, before any document is read. The message, shown in the window and written to `spec_extractor_log.txt`, says what to do. See [When the template is refused](#when-the-template-is-refused-or-the-report-does-not-look-right).

**5. Check the report.** Open `<name>_verification.docx`. It now has the template's fonts and heading styles, its page size and margins, and its header and footer. The summary at the top of the report and the *Run Info* sheet of the Excel file name the template that was used.

* **To change the template later**, edit it in Word and save it under the same name; the next run uses the new version. To open a `.dotx` file for editing, right-click it and choose *Open*. Double-clicking a `.dotx` file starts a new document from it instead.
* **To go back to the tool's own look**, delete the name after `template =`, leave the line as `template =`, and save.

#### What the report takes from the template, and what it never takes

Every report is a new Word document. Only the following are copied into it from the template, after they have been checked:

* the **styles**, such as Normal, the headings, the captions and the table styles, with their fonts, sizes, colours and spacing;
* the **theme** fonts and colours, and the list numbering;
* the **page size, orientation and margins** (those of the template's last section), and a few page-layout settings: default tab stops, hyphenation, different odd and even pages;
* the **headers and footers** with their pictures, including a different first page and different odd and even pages.

The following are never copied:

* the template's own text;
* its document properties (author, company, comments). However, the text its header and footer show is copied, including what their fields showed, such as an author's name or a document number;
* its link to an attached template, which is often on a network share;
* macros, embedded objects, and anything else in the file.

Some things in the headers and footers are changed as they are copied:

* A link becomes plain text.
* Tracked changes are accepted.
* A field other than a page number, page count, date or heading reference becomes the text it showed, so the header reads just as it does in the template. Examples are `TITLE`, `DOCPROPERTY` and `INCLUDEPICTURE`.

Automatic heading numbering ("1.1") is switched off in the report, because the scanned headings carry their own numbers. Each scanned page of the report is a Word section of its own, so that its page header can carry its label ("Page 12 of 40 - scanned page"); the template's own header (a logo, a classification marking) stays above the label on every page, and the footer is the template's.

All of this is because the reports may hold sensitive content, and a Word file can reach outside the computer when it is opened. It can do so through an attached template on a network share, a picture linked to a web address, or a field that fetches a file. Before each report is saved, the tool checks once more that nothing in it points outside the computer.

**Which style is used for each part of the report.** The report uses Word's usual style names, so a template that defines them gives the report its look straight away:

| Part of the report | Word style | Section of the style file |
|---|---|---|
| Report title | Title | `[title]` |
| Headings of the scanned document, at the level of their paragraph number (3 is level 1, 3.1 level 2, 3.1.1 level 3 ...) | Heading 1 to Heading 9 | `[heading 1]` to `[heading 9]` |
| Titles without a number inside a section ("SPECIFICATIONS" above a list of documents), and a title under such a title ("Military") | Subheading, Subheading 2 | `[subheadings]`, `[subheadings 2]` |
| "Page 12 of 40 - text read by the tool" in the page header, and the page's notes | Page Label | `[page label]` |
| Ordinary paragraphs | Normal | `[body]` |
| List entries | List Paragraph | `[list items]` |
| The documents listed in section 2 of the scan: number, title on a tab stop, referencing paragraphs at the right margin | Document List | `[document list]` |
| Paragraphs that became a requirement | Requirement Text | `[requirements]` |
| The `[R-0001]` tags, and the keywords (shall, must ...) | Requirement Tag, Requirement Keyword | `[requirement tag]`, `[requirement keywords]` |
| Table and figure captions | Caption | `[captions]` |
| Tables, their heading rows and their text | Table Grid, Table Heading, Table Text | `[tables]`, `[table header row]`, `[table text]` |
| Running headers and footers read from the scan | Scanned Header Footer | `[scanned header footer]` |
| The tool's own notes | Report Note | `[notes]` |
| Words to check, and words the tool corrected | (highlights) | `[review marks]` |
| `<name>_for_doors.docx`: whether it is written, and whether its headings keep their numbers | - | `[doors]` |

A style the template does not have is added, with the look it has in the tool's own report:

* **Title and the headings** (often Heading 3 and Heading 4, because Word stores only the styles a file uses) take the template's *theme* fonts and colours. In Word, these are under *Design > Fonts* and *Design > Colors*. Many company templates set their font in each style instead. Then these headings come out in another font, often Calibri. To fix this, write your font under `[document]` in the style file (for example `font = Arial`), or set up those headings in the template.
* **Caption** is black, italic and centred, in the body font. **List Paragraph** is like the body text, indented.
* **The report's own paragraph styles** (Requirement Text, Table Text, Scanned Header Footer and Report Note) are based on the template's Normal style. Table Heading is based on Table Text.
* **Requirement Tag and Requirement Keyword** change only the words they mark, which keep the font of their paragraph.

To use a style of your template for a part instead, name it in the style file. For example, if your requirements are normally set in a style called *Req Text*:

```ini
[requirements]
word_style = Req Text
```

Write the name as Word's *Styles* pane shows it. For Word's built-in styles, use the English name, such as *Heading 1* or *Body Text*.

#### Restyling the report in Word

1. Double-click **`make_word_template.bat`**. It writes `word_style\report_template.docx` and opens it in Word. The file holds every style the report uses, with a sample of each part of the report. If that file already exists, the new one is called `report_template (2).docx`, and so on. The window shows the name and the line to write in step 4.
2. Change the styles there: on the *Home* tab open the *Styles* pane (Alt+Ctrl+Shift+S), right-click a style and choose *Modify*. For a logo, a classification marking or page numbers, double-click the top or bottom of the page and edit the header or footer. Page size and margins are on the *Layout* tab.
3. Save the file, keeping the `.docx` format.
4. In `word_style\report_style.ini`, under `[document]`, change the `template =` line (the one with nothing in front of it) to `template = report_template.docx`, and save. If the window showed another name, such as `report_template (2).docx`, write that name instead. Do not add a second `template =` line.

An existing file is never overwritten. If a template is already named in the style file, the new file starts from that template. So this is also a quick way to see, and fine-tune, how your organisation's template looks in the report.

#### Changing single values: fonts, sizes, spacing, page layout

The style file `word_style\report_style.ini` already has a section for each part of the report, with a line for each setting, and every setting is explained inside the file.

* To change a value, write it after the `=` of the line that is already there, and save.
* Do not paste a second copy of a section or of a line. Each may appear only once, or the run stops.

* A value left **empty** keeps the template's look. Without a template, it keeps the tool's own look, which the file shows in brackets.
* A value you fill in always wins, even over the template. So fill in only what you want to change.

For example, after filling in these lines, the file contains:

```ini
[document]
template = Company Report.dotx
font = Arial

[page]
paper = A4
margin_left = 2.5 cm

[heading 1]
size = 16

[body]
space_after = 6
line_spacing = 1.15

[requirements]
tag_position = start
mark_keywords = yes

[table header row]
fill = D9D9D9
```

How to write the values:

* **Font sizes, and space before and after,** are in points, as in Word (`10.5`).
* **Line spacing** is `single`, `double` or a number of lines (`1.15`, `1.5`). For a fixed height, add `pt` (`12 pt`), or write `at least 12 pt`.
* **Indents and margins** need a unit: `cm`, `mm` or `in`.
* **Text colours** are the 6-character code from Word's *Font Color > More Colors > Custom* (`1F4E9A`), or a name such as `dark blue`.
* **Shading** (`fill`, `cell_fill`) takes only the 6-character code (`D9D9D9`); `fill = none` gives no shading.
* **Highlights** take the name of one of Word's highlighter colours, such as `yellow`. The style file lists them.
* **Switches** are `yes` or `no`.

Two settings set the convention for requirement text:

* `tag_position = start` puts the `[R-0001]` tag in front of each requirement, where a requirement ID usually stands.
* `mark_keywords = yes` prints *shall*, *must*, *should* ... in the Requirement Keyword style, which is bold.

`[table header row]` sets the shading of table heading rows, and repeats the heading row at the top of each page a long table runs onto. A heading row is shown only when the scan prints it as one (see [section 1](#1-what-you-get)). If the heading text would come out in the colour of its shading - white text from a template's *Table Heading* style on a light or no shading, the usual cause of heading rows that look empty - it is written in Word's automatic colour (black on light, white on dark) instead, and the run log says so. The review marks (highlighted words, shaded table cells) can be recoloured under `[review marks]`, but not switched off, because they are the point of the report.

A mistake in the file stops the run **before any document is read**, with the line number and what to write instead. Examples are a misspelt setting, a size of "ten", or a style the template does not have. `--word-style FILE` uses another style file, for example one per customer or program. Its template name is looked for next to that file.

#### When the template is refused, or the report does not look right

| The message or problem | What to do |
|---|---|
| *... can hold macros, so it is not used* (a `.dotm` or `.docm` file), or *... contains macros* | In Word: **File > Save As**, *Save as type* **Word Template (\*.dotx)**. If Word asks whether to save it without macros, choose **Yes**. Save it in the `word_style` folder (Word suggests another folder), then write the new name after `template =` in the style file |
| *... contains ActiveX controls* | These are boxes or buttons added from Word's *Developer* tab, and saving again does not remove them. On the *Developer* tab click *Design Mode*, select each control, press Delete, and save the template again |
| *... is not in Word's current format* (a `.dot` or `.doc` file) | The same: save it as **Word Template (\*.dotx)** in the `word_style` folder, and write the new name in the style file |
| *... is protected with a password* | Save an unprotected copy as **Word Template (\*.dotx)** in the `word_style` folder, and use that |
| *The header (or footer, first-page header ...) of the template holds a picture that is not stored in the template* | The picture is linked to a file or a web address. In Word, double-click the header or footer the message names. Delete the picture and insert it again with **Insert > Pictures > This Device**, without choosing *Link to File* |
| *The header (or footer ...) of the template holds an embedded object or control*, or *... something other than text and pictures* | Remove that object from the header or footer, or replace it with a picture of it |
| *The Word template named in report_style.ini was not found* | Check the spelling and the ending (`.dotx` or `.docx`). The message shows where the tool looked and lists the Word files in that folder |
| *A style named in report_style.ini does not exist* | Write the style's name as Word's *Styles* pane shows it. The message lists similar names in the template |
| *The page of the report would leave only ... in for the text* | The margins are wider than the paper allows. Make them smaller in the template or under `[page]` |
| *The template ... could not be read*, *could not be used*, *is damaged*, *is not a Word .docx/.dotx file* or *has no document in it* | The file is damaged, or is not really a Word file (for example a web page or an RTF file whose name ends in `.docx`). Open it in Word, save it again as **Word Template (\*.dotx)** in the `word_style` folder, and use the new file |
| The report does not look like the template | Check that the *Word report look* line of the run names your template, and that the name is on the `template =` line itself, not on the example line above it that starts with `;`. A value filled in in the style file wins over the template: empty it |
| The third-level headings and below are in another font (often Calibri) | The template sets its font in each style rather than in its theme, and has no Heading 3 or Heading 4 of its own. Write the font under `[document]` in the style file (`font = Arial`), or add those headings to the template |
| The fonts look different on another computer | That computer does not have the template's font. Word then uses a similar one; install the font, or choose another in the template |

**Keeping the template.** Templates put in the `word_style` folder are not committed to git (`word_style\.gitignore`), because a template can carry logos, classification markings, author names and server paths. If your repository is internal and should keep the template, delete those lines from `word_style\.gitignore`. Keep the `word_style` folder, with your template and `report_style.ini`, when you install a new version of the tool.

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
5. Check that **Run Info** says *Tested configuration: Yes*. *NO* means the Python or package versions differ from the tested set (each difference is listed in that cell), so the accuracy figures in section 7 do not apply to the run.

> Words of your own program that the dictionary does not know (part names, acronyms written in lower case) can be added to `extra_dictionary_words` in `Settings`, so they are not flagged. Common engineering words (uplink, checksum, boresight, …) are already accepted.

> Why not just trust the OCR confidence? Testing showed that most real misreads on degraded scans still scored above 0.95. For example, "telémetry", "fro" (for "from") and "16.AWG" were all "confident". The review flags therefore combine confidence with independent checks: dictionary, accent marks, punctuation, number and ID consistency. Treat the flags as a strong filter, not a guarantee. On important documents, still read the requirement rows against the scan.

---

## 5. Importing into DOORS

Each run also writes **`<name>_for_doors.docx`**: the document's own text, structure, tables and pictures, without anything the tool added, in the form IBM DOORS turns into a clean module. Check the text against the scan in the verification report and the Excel file first: a Word import cannot be undone item by item.

**What the file holds, and why.** DOORS builds a module from a Word file by these rules (IBM's documentation for DOORS 9.7 and DOORS Next 7.x, and Telelogic's *How to Write Word Documents for Easy Import into DOORS*), and the file is written to fit them:

| In the DOORS file | Because DOORS … |
|---|---|
| Every numbered paragraph is a **Word heading at the level of its number**: 3 is Heading 1, 3.1 Heading 2, 3.1.1 Heading 3 … (Heading 9 at most); an appendix title is Heading 1 | makes each paragraph with a heading's outline level a heading object, and nests the objects by that level |
| A heading never skips a level. A parent the scan did not show is written as *3.2.1 [heading not found in the scan]* | would otherwise put 3.2.1.1 straight under 3.2, and every DOORS number after it would be off |
| A run-in title is split off its text: the heading *3.2.1 Power input*, then *The equipment shall …* as a paragraph of its own. A numbered paragraph without a title is the heading *3.2.1.1* with its text under it | cannot put part of a Word paragraph in Object Heading and the rest in Object Text |
| **One paragraph of the scan is one Word paragraph** (its wrapped lines joined), with no empty paragraphs, line breaks or tab characters | makes one object of every Word paragraph |
| Nothing else has an outline level; nothing uses Word's automatic numbering or bullets; list labels (`a.`, `(1)`) are typed text | would make any other paragraph with an outline level a heading, and loses automatic numbers |
| Tables are plain grids: the same number of cells in every row, **no merged cells** (a merged cell's text is in its top-left cell), borders on every cell, the heading row bold and marked as a heading row | imports merged and uneven tables badly, and DOORS Next ignores table styles |
| Pictures are inline, alone in their own paragraph; captions are plain paragraphs | does not support floating pictures, text boxes or caption fields |
| No page images, page labels, review marks, `[R-0001]` tags, notes or running headers and footers of the scan. A heading before section 1 (a document number, *FOREWORD*) is written as ordinary text | would make each of them an object; an extra heading before section 1 shifts every DOORS number by one |

Your Word template's page header and footer (a classification marking, for example) are kept; DOORS does not import them, so set the module's marking in DOORS itself.

**Importing into DOORS Classic (9.x).** DOORS has no *Import Word* command; the document is sent from Word:

1. In DOORS, open the folder or project the module should go in (you need create access to it).
2. Open `<name>_for_doors.docx` in Word and choose **Export to DOORS** (on the *Add-ins* tab, or *Tools > Export to DOORS* in older Word; it comes with the DOORS client).
3. Give the module a name and choose the options: leave **Remove heading numbers** off (see below); tick **Capture paragraph styles** to keep the style of each paragraph in the *Paragraph Style* attribute, which tells requirement paragraphs (*Requirement Text*) from other text. A list entry keeps the *List Paragraph* style, also when it is a requirement; the **Document Structure** sheet (below) marks it as one and gives its `R-` ID.

**Importing into DOORS Next.** Choose **Artifacts > Create > Import Artifact**, then *Import requirements from within a text document*, select the file and choose to create a module. The headings build the module's hierarchy. To give requirement paragraphs their own artifact type, use the keyword option (`shall`) in the import wizard. DOORS Next cannot remove typed heading numbers, so use `heading_numbers = remove` (below) if they show twice.

**Heading numbers.** By default each heading keeps its number from the scan (*3.2.1 Power input*), so the module can be checked against the document even where DOORS numbers differently. DOORS shows its own number too, so the number appears twice. To leave the numbers out, set this in the style file `word_style\report_style.ini`:

```ini
[doors]
heading_numbers = remove
```

A heading that is only a number (*3.2.1.1*, above its requirement) keeps it even then: an empty heading would be dropped and its text would land under the heading before it. In DOORS Classic, leave *Remove heading numbers* off for the same reason.

**Requirement IDs, pages and other attributes.** A Word import fills only the heading and text of each object. To carry the paragraph numbers, the `R-0001` row IDs, the source pages and the section types into attributes, import the **Document Structure** sheet of the Excel file (save it as CSV first): one row per object in document order, with its level, paragraph number, heading or text, parent and requirement IDs.

**After the import, check:**

* that the module's hierarchy follows the paragraph numbers of the document, and that any *[heading not found in the scan]* object is filled in or removed;
* every table, cell by cell, and every picture;
* once, on your own DOORS version, how it treats headings of level 7 to 9, table heading rows and pictures - these are not described in IBM's documentation and could not be tried where the tool was made.

`make_doors_document = no` under `[doors]` in the style file, or `--no-doors`, leaves the file out.

---

## 6. How it works (pipeline)

1. **Load pages.** PDFs are rendered with pypdfium2 at the scan's own resolution; TIFF/PNG/JPG are read with Pillow. Multi-page TIFF, 1-bit fax and non-square fax pixels (204×98 dpi) are handled.
2. **Clean the image (OpenCV).** Pages are resized to about 220 dpi (a page with no resolution recorded, or one recorded as a screen resolution, has its resolution estimated from the height of its printed characters; a page exported at screen size is enlarged up to four times to bring it near 220 dpi, within the memory limit), turned upright (orientation classifier, confirmed by OCR), straightened with projection-profile deskew (accurate to about 0.05°), and cleared of binder punch holes. Stains, shadows and yellowing are flattened and specks removed with a light median filter. This combination measured best; hard black/white binarization made the deep-learning OCR worse.
3. **OCR.** PaddleOCR **PP-OCRv6** text detection and recognition, run by **RapidOCR** on ONNX Runtime, gives word boxes and confidences.
4. **Layout.** **img2table** finds ruled tables, and borderless tables are found from text alignment. Where a table rules its columns but prints no line between its rows - the usual layout of a verification matrix, and one that is otherwise missed completely, because a row needs two horizontal lines before it exists - the missing separators are worked out from where the text sits. That reading is used only where the printed ruling lines cannot describe the table (nothing was found, or its rows have each swallowed several rows of text); a table that draws all of its lines keeps exactly the grid it had, and if the worked-out reading turns out not to look like a table, the printed one is used after all. Column headers printed sideways, as narrow method columns nearly always are, are read by turning that band upright and reading it again, and each header is put back on the column its ink was printed over. Rows worked out this way are then grouped into **records**: a row of the table plus the lines its cells wrap onto. A cell that wraps must not become a row of its own, so the grouping follows the table's key column where it has one (a value in the left-hand column starts a record; a line without one continues the record above) and otherwise the table's own leading - the lines inside a record sit closer together than the records do, and both spacings are constant through a table, so the dividing line is measured from that table rather than fixed in advance. A **legend band** across the top of a matrix ("LEGEND: 1 = First article  2 = Periodic  A = Visual …", printed above the column headers and spanning the whole width) is recognised as its own row, so the headers below it are still read as headers and the wrapped label of a narrow first column (*Requirement / reference*) does not swallow the first requirement. OCR words are placed into cells; a caption printed inside a table's frame (even over several lines) is taken out again. A **list laid out on tab stops** lines up exactly like a table without ruling lines, and its wide tabs look like the gutter between two text columns; neither is taken as such when the left-hand pieces are list markers or short labels ("a.", "Acceleration:") sitting on the same lines as the text to their right, or when a would-be table's first column counts a., b., c. (or holds only labels, when the bullets were too faint for the OCR). A table with a real third column of short repeated entries (a Method column: *Test*, *Analysis*), a header row or its caption right above it (or directly under it) stays a table, even under a lead-in. Two text columns are kept apart when the right-hand one reads as running text (lines that carry a sentence on from one line to the next), holds numbered paragraphs, or holds a list of its own. Once a band of whitespace is found to be a list's tab stops, it is not judged again for a few rows of the same list on their own. Each item then keeps its label and value together, and a line that starts in the item's label or value column stays with the item whatever it begins with. A label that wraps onto a second line is read before the value beside it. Figures are found as non-text graphics, reading order comes from a recursive XY-cut (which handles columns), and lines are grouped into headings, paragraphs and list items. A line only ends a block when there is evidence: final punctuation, a larger gap, a list marker, or a line that stops short of its column's edge although the next word would have fitted. So a number, unit or designator at the start of a wrapped line ("12. The…", "3.3 V…", "F-35…", "(CB12)") stays in its sentence, on one- and two-column pages and with any line spacing. Numbered lines that follow "NOTES:" or a stem, or that follow each other as sentences ("1. Note text…", "2. …"), are list items rather than headings; "3. REQUIREMENTS" stays a heading.

   **Print formatting** is measured on the page image itself, before its clean-up (whose light median filter would erase a thin underline): a word is **underlined** when a stroke runs under it, below its letters and apart from them, and not past the text as a ruled line would; a line is **bold** when its strokes are clearly heavier than the page's ordinary text. Underlining marks titles (`3.2.1  Power input  The equipment …`) and, with bold, capitals, shading or a rule under it, the heading row of a table. A grid with no heading row printed as one and no title is read as a **list**, row by row (at the top of a page it may be the rest of the table from the page before; that is decided in step 5).
5. **Document clean-up.** Running headers/footers and page numbers are removed. Paragraphs and tables that continue on the next page are joined (in page order); a table at the top of a page without a heading row is joined to the table that ended the page before, its columns matched by position, and is otherwise a list. Words hyphenated at line ends are re-joined, look-alike misreads are corrected where the correction is certain (see [section 1](#1-what-you-get)), and captions are linked to their table or figure. Caption linking learns whether the document puts captions above or below, then matches all captions on a page at once, so a caption cannot take the neighbouring table.
6. **Requirement extraction.** Deterministic, auditable rules (details below).
7. **Document structure.** Every numbered paragraph becomes a section at the level of its number, and each block is filed under its section; run-in titles are split from their text, sections are typed by their titles (scope, applicable documents, requirements, verification …), and the document lists of section 2 are read entry by entry.
8. **Export** to Excel (openpyxl) and Word (python-docx): the verification report and the DOORS-ready file.

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

## 7. Accuracy measured on the test documents

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

Results of the current version (42 pages in 12 files, `python tests/run_regression.py`):

| | Clean / office scan | Heavy photocopy | Fax | Supplied pages (≈64 dpi) |
|---|---|---|---|---|
| Requirements found (recall) | 100 % | 100 % | 100 % | 100 % |
| Extracted rows that are real requirements (precision) | 100 % | 100 % | 100 % | 100 % |
| Paragraph number / requirement ID correct | 100 % | 100 % | 100 % | 100 % |
| Requirement text exactly right | 100 % | 53–81 % | 43 % | 50 % |
| Character errors in the requirement text | 0 % | 0.3–0.8 % | 1.9 % | 0.6 % |
| Captions and tables found, each table linked to its own caption | all | all | all | all |

Of the 32 requirement rows that still contained an OCR character error, **26 were flagged** *Needs Review* (81 %), and one correct row was flagged (a "115" that the OCR itself read at 0.51 confidence - the cautious direction). The six unflagged errors are a "95%" read as "958", a "150 km" read as "150 kn", a "45 kilograms" read as "45.kilograms" and, on the photocopy of the tabbed-list document, specks read as a full stop beside a number ("32 VDC,. 28 VDC", "time:. 2.0 s"): in each the misread token carries a digit or a mark, which no dictionary can check.

Table **cells** are 100 % right on the clean and office scans of the ordinary documents and 97 % on the table-structure document, where the sideways headers are read from a quarter-turned crop and lose a character or two. On the heavy photocopies cell accuracy is 82–100 %, on the supplied low-resolution pages 90 % and on the fax 71 %; those are OCR misreads inside cells that were correctly found and correctly divided into rows and columns, and they are flagged for review.

The same test was re-run for 1.4.0 on Python **3.10, 3.11, 3.12 and 3.13**. All four pass, and their results are identical: every cell of every Excel sheet matches (apart from the run information), so the figures above apply to each of them. **Python 3.14 has not been re-run since release 1.0.1**, where it also passed (see section 10). On 3.13 and 3.14 the OCR-based orientation check costs a few seconds per page - about 13 s per page against 7.6 s on 3.12 on the single-core test machine.

Page orientation was right in 32 of 32 tests (every quarter turn of 8 different pages, among them a title page and pages with only a few lines at their top or foot), with the orientation classifier (Python 3.11) and without it (3.13). Processing took 5–9 s per page (6.4 s on average) on a 2-core virtual machine; typical laptops with more cores are faster. After the OCR, a synthetic 300-page document with a 40-row table on every page needed about one minute for document clean-up, extraction, Excel and Word output.

The requirement text errors that remain are OCR misreads of damaged print (for example "fro" for "from", "958" for "95%"). Only misreads that can be undone with certainty are corrected (a look-alike letter or digit; see [section 1](#1-what-you-get)), and never silently: every correction is highlighted in the Word report and listed in the *OCR Corrections* column (a heading's in the *Document Structure* sheet), and a corrected number, keyword or one-letter guess is still flagged for review. Everything else is left as read, which is why the review flags matter.

**The test-case library.** Besides these documents, `tests/cases` holds 162 small scans, each showing one situation the tool must get right or once got wrong - a list on wide tab stops, a marker the scan lost, a lead-in without a colon, a heading after a list, a list beside a column of prose, a table under a lead-in, a list that carries on over a page break, an underlined title, a list of applicable documents, a table without a heading row - with the exact rows (and, where it matters, the headings and documents) it must produce. Each has a fixed ID such as `TAB-01`, and `tests/cases/CASEBOOK.pdf` shows them all, one page per case. 154 of them pass; the 8 marked there as *known limitations* are what the tool still gets wrong, each with a description of what happens instead (see section 10). [tests/README.md](tests/README.md) explains how to run one case, and how to add a case - or a page of your own documents - as a test.

**Real documents will differ.** Before relying on the tool for a program, run a pilot of 20–30 pages of your own documents and compare against a manual extraction.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `Missing Python packages` | Run `setup_windows.bat` again, or `python -m pip install -r requirements.txt -c constraints.txt`. If the message also says the Python version is not a tested one, install the 64-bit Python 3.12 first |
| `setup_windows.bat` says *No supported Python was found* | Install the 64-bit Python 3.12 from python.org (python.org installer: tick *Add python.exe to PATH*; Python install manager: run `py install 3.12`), then run the setup again. Python 3.15 and newer, 32-bit Python and the free-threaded build are not supported |
| The run log or *Run Info* says **NOT the tested configuration** | The Python version or a package version differs from `constraints.txt`; the message lists each difference. Delete the `.venv` folder and run `setup_windows.bat` again (other systems: `python -m pip install -r requirements.txt -c constraints.txt`). The results are still written, but the accuracy in section 7 was not measured for that setup. A Docling run is always reported this way, because the Docling engine's accuracy has not been measured |
| pip cannot reach the internet | Configure pip for the company proxy or mirror, or use the offline `wheels` method (section 2) |
| `ImportError` mentioning `cv2` | The OCR and table libraries each install an OpenCV build into the same folder, and one of them was damaged. Run `python -m pip install --force-reinstall --no-deps -c constraints.txt opencv-contrib-python` (the most complete build, in its tested version) |
| "the PDF is password-protected" | Save an unprotected copy (with permission) and run again |
| A page is text but nothing was found | Look at *Page Quality* and the Word report. Try `--dpi 300` for very small print, or `--remove-color-marks` for colored stamps |
| Every line of a table cell became its own table row | Fixed in 1.1.1. If it reappears, the table's records are not being told from its wrapped lines: check the Word report to see how the page was grouped, and try `--no-inferred-rows` to see whether the row inference is responsible |
| A verification matrix came out as **one huge row**, with every X bundled together | Fixed in 1.2.0 for the usual shape: a legend band across the top, a header row, column rules and no line between the requirements. If it reappears, the rows are not being found from the text: check the Word report to see how the page was grouped, and send the page to the maintainer - a fixture of that exact shape is the way these get fixed |
| A list item has only its label ("a. Acceleration:") and its value appears elsewhere, or later items are missing | Fixed in 1.3.0: wide tab stops between marker, label and value are no longer taken for text columns or for a borderless table. If it reappears, check the Word report: if the values sit in paragraphs of their own, the layout step split the items - send the page to the maintainer. Test cases TAB-01 to TAB-54 cover these layouts |
| A list entry was joined to the one before it | The scan lost that entry's letter or number, so its line looks like a wrapped line of the item above. When the letters either side show the gap (`a.` then `c.`), the item is split where the new sentence starts and the entry gets its letter back, marked *List marker missing - taken as 'b.' from the sequence*; when the split point is not clear, the item before the gap is flagged (*The list goes from 'a.' to 'c.' …*). An entry that lost its marker at the END of a list has no letter after it to show the gap - correct it in the Excel file Test cases LST-03 to LST-12; a lost marker on the LAST item of a list is not found yet (LST-24) |
| List items lost their values right above a two-column section | *Known limitation* (test case COL-13): when a list on wide tab stops is followed directly by text set in two columns, with no full-width line between them, the list's tab and the column gutter merge into one band and are read as columns. The values are still in the Word report and the *Full Text* sheet; add them to the rows by hand |
| A table came out as list rows, or a list came out as a table | Since 1.5.0 a block of text in columns is a **table** only when it has a title ("TABLE I. …", right above it or directly under it) or a heading row printed as one: underlined, bold, in capitals, shaded, with a rule under it, or made of column names (*Parameter*, *Minimum*, *Method* …). Otherwise it is a **list**, one row per entry, its cells in order - also when it was a table up to 1.4.0. A table at the top of a page without a heading row is taken as the rest of the table on the page before when it has as many columns, at the same positions. The *Excel table sheet* (row 2) says why a row was taken as the heading row. Test cases TBL-01 to TBL-21 and STR-08 to STR-11 |
| A document is missing from the *Applicable Documents* sheet, is in the wrong *Group*, or its title is cut short or runs into the next one | The lists of documents are read from the layout of the page: where an entry starts, where its title wraps, and which lines are group titles (*DEPARTMENT OF DEFENSE STANDARDS*) or sub-titles. A few layouts are still read wrongly: a group title right under a title that runs to the margin, with no blank line between them, in a list typed in capitals or when the group title is only an acronym (*ASTM*, *IEEE*); a centred sub-title on a page where no line starts at the margin; and a title that wraps just before a supplement's number ("..., Supplement" / "4.1 ..."), which is read as a paragraph. Check the sheet against the scan for lists like these. No text is lost: a document read wrongly is still in the requirement text, the *Full Text* sheet and the Word report |
| A page image looks fine but the text is read badly | Check *Scan dpi* and *OCR dpi* in the **Page Quality** sheet. A page exported at screen size (roughly 60-100 dpi) is enlarged automatically, but a photograph of a page, or a page cropped to part of a sheet, can still be too coarse to read: re-export or re-scan it at 200-300 dpi |
| A list became normal paragraphs, or a table was missed | Check the Word report for how the page was grouped. Very faint ruling lines can make a ruled table fall back to text; the text and requirements are still extracted |
| A result looks wrong for a particular layout | Look the layout up in `tests/cases/CASEBOOK.pdf`: each test case shows one situation, the rows the tool must give for it, and - for the ones marked *known limitation* - what the tool does instead. Quote the case ID (for example LST-20) when reporting a problem, or send a page of the same shape |
| The first row or two of a table are blank in the Word report, but filled in the Excel sheet | Fixed in 1.5.0. The text was there, in the colour of its shading (a template's white *Table Heading* text on a light row), or a merged cell was written over. Heading text now gets Word's automatic colour when it would not show, and the Word and Excel tables use the same merged cells. If it reappears, check `[table header row]` in the style file and the template's *Table Heading* style |
| A word in the report is green, or the *OCR Corrections* column is filled in | The tool corrected a look-alike misread there (`requ1red` → `required`); the column lists what the scan read. Check corrected numbers against the scan (they are flagged). `--no-autocorrect` leaves every word as read |
| The DOORS module is nested wrongly, or has objects called *[heading not found in the scan]* | The levels come from the paragraph numbers: a misread number (`3.2.l` for `3.2.1`) or a heading the scan lost puts a section in the wrong place. Correct the number in `<name>_for_doors.docx` before importing (the placeholder marks a parent heading the scan did not show: fill it in or delete it). See section 5 |
| Excel file "is open in another program" | The tool saves a copy with the time added to the name |
| *The Word style file has a mistake*, a Word template is refused, or the report does not look like the template | A style-file message gives the line and what to write instead; an empty value, or deleting the line, gives the normal look. For templates, see [When the template is refused, or the report does not look right](#when-the-template-is-refused-or-the-report-does-not-look-right) |
| Dragging a file onto `run_extractor.bat` does nothing or shows an error | The file or folder name probably contains `&`. Rename it, or double-click the .bat and use the file picker |
| A page is graded **FAILED** in *Page Quality* | That page could not be read (usually damaged in the file). The other pages were processed. Results with a failed page are not cached, so simply running again retries it; if it fails again, open the page in an image viewer, and if it opens, save/print it to a new PDF and run that |
| Slow on large batches | Normal on CPU. Unchanged files re-use `_cache`. `--threads N` sets CPU threads |
| Python 3.13 or 3.14 | Works, with the same accuracy; page orientation is checked with a slower OCR-based method (a few seconds more per page). Python 3.11/3.12 is faster. Do not force-install the orientation classifier on 3.13/3.14: it was not tested there, and runs would be reported as *not the tested configuration* |

---

## 9. Optional Docling engine (more advanced layout/table AI)

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

## 10. For maintainers

* `spec_extractor.py` is one file in 12 numbered sections, listed at the top of the file. All tunable values are in `Settings`. **[CODE_GUIDE.md](CODE_GUIDE.md)** explains the code for someone about to change it: what each section does, which function does each step of a run and what it calls, and where to make the usual changes (a new keyword, a table rule, a column of the Excel file, a part of the Word report).
* **Testing** is explained step by step in **[tests/README.md](tests/README.md)**: how to run one test or one case, how to add a case of your own design, and how to keep a page of your own documents as a test (on your computer only).

### Changing the version number by hand

The version is the line `__version__ = "1.5.0"` near the top of `spec_extractor.py` (section 1). The heading at the top of this README must say the same: `tests/test_rules.py` checks that they agree.

* **For a release** (a merge into the main branch): raise the number - the last part for a fix (1.5.0 → 1.5.1), the middle one for new behaviour (1.5.0 → 1.6.0) - in `spec_extractor.py` **and** in the heading *Version …* of this README, in the same commit.
* **After a hand edit of your own**, mark it so its results can be told apart: add to the number, for example `__version__ = "1.5.0-local.1"`, and write the same in the README heading (`> ## Version 1.5.0-local.1`). Use letters, digits and `.` `-` `+` only. Raise the last part for each further edit.
* What the version changes: the line every run prints and the *Run Info* sheet and Word report show; the output folder (`extraction_output_1.5.0-local.1`, so results of two versions never mix); and the OCR cache, which is keyed on it, so each document is read again once.
* **The build** (`build a1b2c3d commit 4e5f6a7`) cannot be set by hand, and need not be: it is a fingerprint of the bytes of `spec_extractor.py` (`build_id` in section 1), so it changes by itself with every edit, even one that forgot the version. The commit is read from the `.git` folder when there is one. Two copies with the same build run the same code.
* **After any change**, run the three test levels (install once: `python -m pip install -r requirements-dev.txt -c constraints.txt`):
  * `python tests/test_rules.py` takes seconds and needs no OCR. It feeds realistic page geometry through the layout, clean-up and extraction rules: text across a page break, numbers/units/designators at the start of wrapped lines, headings without a period, unmarked lists, footer-zone items, captions inside table frames and below tables, merged cells, page selection, output names, a damaged page, and more. The table-structure tests draw a **real page image** and run the real detector on it, because those failures are in how the ruling lines (or the absence of them) are read: a table with column rules and no row lines, a fully ruled table that must be left alone, a cell that wraps and must not be split, sparse verification matrices, sideways headers and the arithmetic that maps them back onto their columns. It also checks that `constraints.txt`, the `requirements*.txt` files and `setup_windows.bat` agree on the supported Python versions and packages, and it ends by saying whether it ran on the tested configuration. Add a test here for every new rule or bug.
  * `python tests/run_regression.py` takes a few minutes. It builds the synthetic scanned documents, runs the whole tool, scores it against exact ground truth (requirement recall/precision, paragraph numbers, captions, caption-to-table links, tables, review flags) and prints PASS/FAIL. `--reuse` skips the OCR.
  * `python tests/cases/run_cases.py` takes ten to twenty minutes. It runs the whole tool, with the real OCR, on the **test-case library**: 162 small scanned documents, each showing **one situation** the tool must get right - lists on wide tab stops, list markers the scan lost or misread, lead-ins with and without a colon, paragraph numbers and headings, paragraphs after a list, two-column pages, tables beside lists, page breaks - together with the exact rows it must produce. Every case has a fixed ID (`TAB-01`, `LST-07`, `PAGE-02` ...): use it to refer to a situation in a report, a review or a commit. **`tests/cases/CASEBOOK.pdf`** is the catalog - one page per case with the situation, what the tool must do and why, the page itself and the rows expected - and `python tests/cases/build_cases.py` draws the scanned documents into `tests/cases/documents/` (one PDF per case, named by its ID) so that any case can be opened and looked at, or run through the tool on its own. A case marked **known limitation** is one the tool still gets wrong; it is kept, with what happens instead, and does not fail the run. Every other case must pass. Each run lists the cases whose result changed since the previous run, and writes the full comparison to `tests/cases/_results/case_report.txt`; `--only TAB` runs one area, `--only TAB-07` one case. **To add a case**, write its page and rows in the right `tests/cases/area_*.py` file (the format is explained at the top of `tests/cases/casekit.py`) under the next free ID, then run `build_cases.py` to draw it and rewrite the catalog; `test_rules.py` fails until the catalog is up to date.
* **The Word report** is section 11. Its look comes from one table, `REPORT_PARTS` (each part's Word style and the tool's own look), the style file `word_style/report_style.ini` (read by `read_style_file`) and an optional template (read by `read_word_template`). A template is never used as the base document. `_report_document` makes a new document and copies in only the checked styles, theme, list numbering, layout settings, page size and headers/footers. `outside_references` checks every finished report before `_save_word_file` writes it. When adding a part to the report, add it to `REPORT_PARTS` and to `report_style.ini`: `test_rules.py` checks the two agree. Apart from the review marks, a few labels (*Source:*, *Text inside figure:*, the could-not-be-read warning, *[continues across pages]*), the bold and italic of the tags and keywords (Word's bold and italic are toggles, so a style alone cannot hold them inside a bold or italic paragraph), picture paragraphs, the table width, a table alignment set in the style file and the tool's own heading-row shading, the report is formatted only through styles, so a template or Word itself decides the look.
* **Table detection** lives in section 6c and turns on three questions, each in its own function, so a misbehaving document can be traced to one of them: `_rows_are_under_split` (did the printed ruling lines really describe this table, or has each row swallowed several rows of text?), `_plausible_borderless_table` / `_reads_like_prose` (is this a table at all, or tidy-looking running text?) and `_is_mark_matrix` (is it a verification matrix, which is mostly empty on purpose and must not be judged on how many of its cells are filled?).
* Rows that had to be worked out from the text are grouped into records by `_record_breaks` (the key column, else `_gap_threshold` on the table's own leading) and joined by `_merge_continuation_rows`; the same grouping drives the borderless detector, so both read a wrapped cell the same way.
* Each area of a page is read up to three ways, and `_better_row_split` puts them in the order to try: as the printed ruling lines describe it; with the missing separators inferred by img2table; and, when that inference gives up - it does on badly degraded scans, where the ink is too broken for it to measure a row pitch - with the rows cut from the text by `_resplit_rows`. A reading that the checks above then reject falls back to the next one, so a table is never lost by trying to improve it. Both behaviours can be switched off, with `--no-inferred-rows` and `--no-sideways-headers`; that is the quickest way to tell whether one of them is behind a surprising result.
* **Tested configurations.** Release **1.4.0** passed the rule tests (236 of them) and the regression on 64-bit Python 3.10.20, 3.11.15, 3.12.3 and 3.13.12 with the package versions in `constraints.txt` (the tests ran on Linux; Windows installs the same package versions), with identical results on every one of them - every cell of every Excel sheet - and the test-case library (`tests/cases/run_cases.py`) on 3.11 and 3.13: 136 cases pass, and the other 13 are the known limitations, still wrong as the catalog describes. Its Word report was also checked with about 50 test templates, both company-style ones and ones built to reach outside the computer, and every report written passed the Word file format schema. Word itself was not available there: open a report, and one made with a company template, in Word before handing this version out. **Python 3.14 was not available where 1.4.0 was built, so it has not been re-run since release 1.0.1: run both test levels on 3.14 before handing this version out.** Release 1.0.1 passed on 64-bit Python 3.10.21, 3.11.16, 3.12.3, 3.13.15 and 3.14.6. To add a Python version or change a package version: update `SUPPORTED_PYTHON` in `spec_extractor.py`, the search list and `PY_CHECK` in `setup_windows.bat`, `constraints.txt` and this README; install; run both test levels on **every** supported version; hand the folder out only when all of them pass.
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
