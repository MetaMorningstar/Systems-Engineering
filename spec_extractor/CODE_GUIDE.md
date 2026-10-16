# Code guide: how `spec_extractor.py` is built

This guide is for someone about to change the tool by hand. It says what each part of `spec_extractor.py` does,
which function does each step of a run and what that function relies on, and where to make the usual changes.

* The whole tool is **one file**, `spec_extractor.py`, in **12 numbered sections**. Each starts with a banner such
  as `# 6. OCR AND PAGE LAYOUT ANALYSIS`; sub-sections start with `# ---- 6c. Tables ...`. To find a section or a
  function, search the file (Ctrl+F) for its banner or for `def function_name` - line numbers change with every
  edit, so this guide does not use them.
* Functions are written `name()` here, and methods `Class.name()`. Every function has a comment (docstring) at its
  top saying what it does, with examples; read it before changing the function.
* Names starting with `_` are helpers used only inside the file.

**Before you edit:** keep a copy of the file, and after the edit run the tests (see [tests/README.md](tests/README.md)
and *Traps* at the end of this guide). After a hand edit, mark the version as the README explains (*Changing the
version number by hand*); the build fingerprint changes by itself.

---

## 1. One run, step by step

What happens when you run `python spec_extractor.py spec.pdf` (section numbers in brackets):

1. **`main()`** [12] reads the command line (`build_arg_parser()`, `settings_from_args()`), turning the options into
   a `Settings` object [2]. `configure_keywords()` [6f] tells the layout rules which requirement keywords to protect.
   `collect_input_files()` finds the documents. `report_look()` [11d] reads and checks the Word style file and
   template **before** any document is read, so a mistake there stops the run at once. `report_configuration()`
   [12] logs whether the Python and package versions are the tested ones (section 1b).
2. For each document, **`SpecExtractor.process_file()`** [12] runs the pipeline:
   1. **The OCR cache.** The folder `_cache/<file>_<hash>_<settings>_<pages>` is named from the file's SHA-256,
      `Settings.ocr_fingerprint()` [2] (which holds the settings that change the reading of a page, the version and
      `_cached_code_hash()`, a fingerprint of sections 3-6 and 8). If its `result.json` exists, the pages are not
      read again: `DocResult.from_json()` [3] loads them and steps 2.2 is skipped.
   2. **Reading the pages** - `SpecExtractor._read_document()` [12], page by page:
      * `iter_raw_pages()` [4] - one page image at a time, with its resolution (`_iter_pdf_pages()` with pypdfium2,
        `_iter_image_pages()` with Pillow for TIFF/PNG/JPG).
      * `prepare_page()` [5] - resized to about 220 dpi, turned upright (`OrientationDetector`), straightened
        (`estimate_skew()`, `rotate_bound()`), punch holes painted out (`remove_punch_holes()`), background
        flattened (`flatten_background()`) and a light median filter. Gives a `PreparedPage` with `ocr_image` (cleaned,
        for the OCR) and `view_image` (not filtered, for pictures and for measuring print).
      * `RapidOcrEngine.read()` [6b] - the OCR: a list of `Line`s, each with its `Word`s, boxes and confidences.
      * **`analyze_page()`** [6f] - turns the lines of one page into `Block`s in reading order:
        * `measure_text_format()` [6b-2] marks underlined words (`Word.underline`) and how heavy each line is
          (`Line.weight`, for bold), on `view_image`.
        * `detect_tables()` [6c] finds tables (see section 3 of this guide) and returns them with the lines inside.
          A table with neither a title nor a heading row printed as one is turned into list rows by
          `table_rows_as_list()` [6c]; at the top of a page it is kept, marked `may_continue`, for step 2.3.
        * `detect_figures()` [6d] finds drawings and photos.
        * `xy_cut()` [6e] puts the rest in reading order, cutting columns apart (`_column_cut()`, with
          `_is_tab_not_gutter()` deciding whether a band of white space is a column gutter or a list's tab stop).
        * The grouping loop inside `analyze_page()` joins lines into headings, paragraphs and list items, using the
          tests of 6f (`_is_heading_text()`, `_starts_list_item()`, `_starts_document_entry()`, `_underlined_title()`
          ...), and `classify_text_block()` gives each block its kind.
      * The blocks are saved to the cache (`DocResult.to_json()`), with each page's picture.
   3. **`finalize_document()`** [7] - the document as a whole:
      * `build_text_context()` - word statistics of the document and its `WordChecker`, which spots misreads
        (`WordChecker.issue()`) and corrects the certain ones (`WordChecker.correct()`), see section 4 below.
      * `block_tokens()` / `word_tokens()` - each block's text as `Token`s (word, confidence, what to check, what the
        scan read before a correction, underlined). `_correct_table_cells()` corrects table cells the same way.
      * `_mark_page_furniture()` (running headers, footers, page numbers), `_merge_across_pages()` (a paragraph cut
        by a page break), `_merge_continued_tables()` (a table that goes on over the page, also without its heading
        row: `_fit_columns()`), `_link_captions()` (each caption to its table or figure), `_tables_without_titles()`
        (a `may_continue` table that did not continue anything becomes list rows).
   4. **`RequirementExtractor.extract()`** [9] - the Excel rows (`ExtractedItem`s):
      * `RequirementExtractor._text_block_items()` for paragraphs and list items: `RequirementExtractor.parse_head()` splits the paragraph number, run-in
        title (ended by a full stop, or by underlining: `underlined_after_number()`) and text; `RequirementExtractor._list_items()`
        makes one row per list item, with the lead-in in front (`RequirementExtractor._sequence_markers()` checks and repairs the markers);
        `RequirementExtractor._req_item()` makes one row from one sentence.
      * `RequirementExtractor._table_items()`, `RequirementExtractor._requirement_rows_from_table()` and `RequirementExtractor._verification_matrix()` for tables.
      * `RequirementExtractor.review_for_tokens()` decides *Needs Review* and the *Review Reasons*; `RequirementExtractor.quality_notes()` the INCOSE checks.
        Corrections go to the *OCR Corrections* column.
   5. **The document's structure** [9b, 9c]: `build_outline()` gives every numbered paragraph its section and level
      (`_heading_level()`: the number of parts of the number), files it under its number's parent (a parent the scan
      did not show gets a part of its own, `"missing": True`), types the top-level sections by their titles
      (`section_type()`, `SPEC_SECTION_TYPES`), and stores it on the blocks (`Block.meta["outline"]`). The writers
      take each part's words with `_part_tokens()` [7], which splits a word the boundary cuts ("Leakage.No").
      `read_document_lists()` reads the documents of section 2 (`parse_document_entry()`), and
      `note_section_types()` adds the quality note for a requirement in section 6 (Notes).
   6. **The outputs**:
      * `write_workbook()` [10] - the Excel file: *Extracted Items* (`MASTER_COLUMNS`), one sheet per table, *Full
        Text*, *Page Quality*, *Document Structure* (`_write_structure_sheet()`), *Applicable Documents*
        (`_write_documents_sheet()`), *Run Info*.
      * `write_word_report()` [11e] - the verification report; `write_doors_document()` [11e] - the DOORS file. Both
        start from `_report_document()` [11d] (a new document with the styles of `REPORT_PARTS` [11a], the style file
        and the template) and write the blocks with `_ReportWriter` [11e]. `_save_word_file()` checks with
        `outside_references()` [11d] that nothing in the file points outside the computer before it is saved.
3. With several documents, `main()` also writes `ALL_DOCUMENTS_<date>.xlsx` (`write_workbook()` with all of them).

---

## 2. The sections

| Section | What it holds | Main functions and names |
|---|---|---|
| **1. Imports and dependency check** | the version (`__version__`), the build fingerprint, the supported Python versions; loads the packages and stops with a clear message when one is missing; switches off ONNX Runtime and Hugging Face telemetry before they load | `build_id()`, `version_line()`, `SUPPORTED_PYTHON`, `python_support_problem()` |
| **1b. Tested configuration** | compares this computer's Python and package versions with `constraints.txt` | `tested_versions()`, `installed_versions()`, `configuration_differences()`, `configuration_status()` |
| **2. Settings** | every default the user can change, each explained; the output folder name; the cache key | `Settings`, `Settings.ocr_fingerprint()`, `OUTPUT_FOLDER`, `_cached_code_hash()` |
| **3. Data model** | the containers every step fills (see section 3 below) | `Word`, `Line`, `TableData`, `Block`, `PageInfo`, `DocResult`, `ExtractedItem` |
| **4. Loading pages** | PDF, TIFF, PNG, JPG into page images with their resolution, one page at a time | `iter_raw_pages()`, `parse_page_selection()`, `count_pages()` |
| **5. Image clean-up** | turning, straightening, punch holes, background, the two page images | `prepare_page()`, `OrientationDetector`, `estimate_skew()`, `flatten_background()` |
| **6a. Text patterns** | the regular expressions shared by layout and extraction: paragraph numbers (`RE_PARA_NUM`), list markers (`RE_LIST_MARKER`), requirement IDs (`RE_REQ_ID`), **document numbers** (`RE_DOC_ID`), units, captions | `clean_para_number()`, `plausible_next_number()`, `_next_marker()`, `remove_ocr_specks()` |
| **6b. OCR engine** | PaddleOCR PP-OCRv6 through RapidOCR and ONNX Runtime | `RapidOcrEngine` |
| **6b-2. Underline and bold** | measures how the text is printed, on the page image | `measure_text_format()`, `_strokes_under()`, `_stroke_beside()`, `_stroke_weight()` |
| **6c. Tables** | ruled tables (img2table), tables with column rules but no row lines, borderless tables (`detect_aligned_tables()`), records, sideways headers (6c-2), **heading rows** (`_header_rows()`), tables shown as lists | `detect_tables()`, `_better_row_split()`, `_header_rows()`, `_names_columns()`, `_COLUMN_NAME_WORDS`, `table_rows_as_list()`, `_reads_like_prose()`, `_plausible_borderless_table()` |
| **6d. Figures** | drawings and photos (ink that is not text) | `detect_figures()` |
| **6e. Reading order** | the recursive XY-cut: columns and reading order | `xy_cut()`, `_column_cut()`, `_is_tab_not_gutter()` |
| **6f. Grouping lines** | lines into headings, paragraphs and list items; the whole page step | `analyze_page()`, `classify_text_block()`, `_is_heading_text()`, `_starts_document_entry()`, `_underlined_title()` |
| **7. Document-level clean-up** | misread checks and **autocorrection**, tokens, headers and footers, page-break joins, continued tables, captions | `finalize_document()`, `WordChecker`, `WordChecker.correct()`, `word_tokens()`, `_merge_continued_tables()`, `_link_captions()`, `_tables_without_titles()` |
| **8. Docling engine** | the optional AI layout engine (`--engine docling`), mapped onto the same `Block`s | `DoclingEngine` |
| **9. Extraction** | the Excel rows: requirements, list items, tables, captions, review reasons | `RequirementExtractor`, `RequirementExtractor.extract()`, `RequirementExtractor.parse_head()`, `split_sentences()` |
| **9b. The outline** | sections, levels and types (MIL-STD-961/490) | `build_outline()`, `section_type()`, `SPEC_SECTION_TYPES`, `_heading_level()`, `note_section_types()` |
| **9c. Lists of documents** | the documents of section 2 | `read_document_lists()`, `parse_document_entry()`, `_DOCUMENT_LIST_TITLES` |
| **10. Excel export** | the workbook | `write_workbook()`, `MASTER_COLUMNS`, `shown_header_rows()`, `_table_merges()`, `_write_structure_sheet()`, `_write_documents_sheet()` |
| **11a-11b. Report parts and style file** | each part of the Word report with its style and look; reading `report_style.ini` | `REPORT_PARTS`, `read_style_file()`, `BUILT_IN_SWITCHES` |
| **11c. Word template** | reads a template safely: only styles, theme, layout, headers and footers, all checked | `read_word_template()`, `_clean_story()`, `_reaches_outside()` |
| **11d. Making the document** | a new report document with the right styles and page; the final safety check | `report_look()`, `_report_document()`, `outside_references()` |
| **11e. Writing the report** | the verification report and the DOORS file | `_ReportWriter`, `write_word_report()`, `write_doors_document()`, `_doors_ready()`, `_page_header()`, `_add_confidence_runs()` |
| **11f. Starter template** | `make_word_template.bat` | `write_starter_template()` |
| **12. Batch runner** | the per-file pipeline, the cache, file names, the command line, `main()` | `SpecExtractor`, `SpecExtractor.process_file()`, `build_arg_parser()`, `settings_from_args()`, `main()` |

---

## 3. The data passed from step to step (section 3)

* **`Word`** - one OCR word: `text`, `conf` (0-1), `box` (x0, y0, x1, y1 in pixels of the cleaned page) and
  `underline`.
* **`Line`** - one OCR line: its text, words, box, and `weight` (how heavy it is printed; 1.0 = the page's
  ordinary text).
* **`TableData`** - a table: `grid` (rows of cell texts), `conf`, `merges` (merged ranges `(r0, c0, r1, c1)`),
  `header_rows` (how many rows name the columns), `header_format` (how its heading row is set apart - "underlined",
  "bold", "column names" ...; empty = no heading row is shown), `cell_boxes`, `cell_words`.
* **`Block`** - one element of a page in reading order: `kind` (`heading`, `paragraph`, `list_item`, `table`,
  `figure`, `caption`, `page_header`, `page_footer`), `page`, `box`, `lines`, `text`, `table` and `meta`, a
  dictionary of what the steps found out about it. The most used `meta` keys:

  | Key | Set by | Meaning |
  |---|---|---|
  | `number`, `title`, `level` | `classify_text_block()` | a heading's paragraph number, title, level |
  | `marker` | `classify_text_block()` | a list item's marker (`a.`, `(1)`) |
  | `from_table`, `cells`, `cell_x`, `cell_words` | `table_rows_as_list()` | a row of a table shown as a list: its cells and where they sit |
  | `may_continue` | `analyze_page()` | a table at the top of a page with no title or heading row (decided in `finalize_document()`) |
  | `caption`, `caption_of`, `caption_label` | `_link_captions()` | a table's caption; a caption's table or figure |
  | `cell_corrections` | `_correct_table_cells()` | the table cells the tool corrected |
  | `outline` | `build_outline()` | the headings and body parts inside the block, with their levels and section types |
  | `document_entry`, `document_group` | `read_document_lists()` | a document of section 2; a group title above such documents |
  | `continued_across_pages` | `_merge_across_pages()` | text joined over a page break |

* **`DocResult`** - one document: its pages (`PageInfo`) and blocks; saved to the cache as `result.json`.
* **`Token`** [7] - one word as the outputs show it: `text`, `conf`, `issue` (why to check it), `line_start`,
  `original` (what the scan read, when the word was corrected), `underline`.
* **`ExtractedItem`** [3, filled in 9] - one row of *Extracted Items*: type, pages, section, doc ref, title,
  text, keyword, class, review reasons, corrections, quality notes, table and so on. Never cached.

---

## 4. Where to make the usual changes

| To change ... | Look at | Notes |
|---|---|---|
| a default (dpi, review threshold, which outputs are made) | `Settings` [2] | each value is explained beside it; most are also command-line options (`build_arg_parser()`) |
| the requirement keywords and their classes | `Settings.keywords` [2] | or `--keywords` on the command line |
| words the dictionary should accept | `Settings.extra_dictionary_words` [2], `ENGINEERING_WORDS` [7] | words of your program that are not misreads |
| what autocorrection may change | `WordChecker.correct()` [7], `_LOOKALIKES`, `_LOOKALIKE_PAIRS`, `_SAME_SHAPE_CAPITALS`, `_NUMBER_LOOKALIKES` [7] | it changes a word only when exactly one ordinary word comes out; `Settings.autocorrect = False` or `--no-autocorrect` switches it off |
| when a block of columns is a table | `analyze_page()` (the comment "A table needs a heading row ... or a title"), `_header_rows()`, `_names_columns()`, `_COLUMN_NAME_WORDS` [6c] | add a column name to `_COLUMN_NAME_WORDS` when a heading row in plain type is not recognised |
| how a table going on over the page is joined | `_merge_continued_tables()`, `_fit_columns()`, `_tables_without_titles()` [7] | |
| how underlining and bold are measured | `measure_text_format()` and the helpers of 6b-2 | thresholds are in line heights, explained in the comments |
| which titles start which kind of section | `SPEC_SECTION_TYPES`, `_DOCUMENT_LIST_TITLES`, `_DOCUMENTS_FOLLOW` [9b, 9c] | a title is matched as a whole, ignoring case |
| which document numbers are recognised (`MIL-STD-461G`, `SAE AS50881` ...) | `RE_DOC_ID` [6a] | one alternative per family of documents, with a comment; test with `tests/test_rules.py doc` |
| how a paragraph number, title and text are split | `RequirementExtractor.parse_head()` [9], `underlined_after_number()` [9] | an underlined title must end like one (no sentence end inside, no comma at the end) |
| how the lines of a document list are told apart | `_starts_document_entry()` (tab stops, dash), `_starts_listed_document()` (single-spaced) [6f], `parse_document_entry()` [9c] | a document title never holds a requirement keyword |
| which unnumbered titles start a top-level section | `build_outline()` [9b] (its inner function `starts_new_section`) | section numbers only go forward: a "1." inside section 3 is a note, not section 1 |
| heading levels | `_heading_level()` [9b] and `_ReportWriter.heading()` [11e] | the level is the number of parts of the paragraph number, at most 9 |
| a column of the Excel file | `MASTER_COLUMNS` [10] and where `write_workbook()` fills the row | find columns by name (`_COL["Content"]`), never by position |
| a part of the Word report (a new style) | `REPORT_PARTS` [11a], `word_style/report_style.ini`, `write_starter_template()` [11f], the README's style table | `tests/test_rules.py` checks that the parts and the style file agree |
| what the DOORS file holds | `_ReportWriter` (its `verify` flag is False for the DOORS file), `_doors_ready()`, `write_doors_document()` [11e] | the rules are in README section 5 |
| the supported Python versions | `SUPPORTED_PYTHON` [1], `setup_windows.bat` (`PY_CHECK`), `constraints.txt`, the README | then run all tests on every version |

---

## 5. Traps

* **The OCR cache.** Results of sections 3-6 and 8 are cached; editing those sections - even a comment - or the
  version makes every document be read again (minutes per document). Edits in sections 7 and 9-12 use the cache,
  so they take effect at once - test them with and without `--no-cache`. The cache key finds sections 3, 7, 8 and 9
  **by their banner titles** (`_cached_code_hash()`); keep those titles as they are. A setting that changes how a
  page is read must be added to the list in `Settings.ocr_fingerprint()`.
* **New fields on `Word`, `Line`, `TableData` or `Block`** must also be read back in `DocResult.from_json()`, or a
  cached run loses them. `Block.meta` is saved whole. Store plain Python values (`bool()`, `int()`, `float()`),
  never numpy values: the cache is JSON.
* **`Block.meta`** is shared by many steps: add keys to it, do not replace it. After `finalize_document()` renumbers
  the blocks (`Block.uid`), captions refer to their table by that number.
* **Thin lines vanish from `ocr_image`** (the median filter): measure print on `view_image`.
* **Tables are found in two ways** (`detect_tables()` on the image, `detect_aligned_tables()` on the text); a rule
  about what a table is must hold in both. Rows given back by a table must become list rows, or they are lost.
* **Word tables are slow to build**: never call `Table.cell()` in a loop (read `tbl._cells` once), and give the
  Excel sheet and the Word report the same merged cells (`_table_merges()`).
* **The tests read the Excel layout**: table sheets start at row 5, and every sheet but the fixed ones is a table
  (`tests/evaluate.py`). A new sheet must be added to the list there.
* **Security** (the tool is used on sensitive data): it must never reach the network. Do not add a package without
  checking that it works offline and sends nothing (no telemetry, no model downloads), pin it in `constraints.txt`,
  and say so in the README. A Word template or report must never point outside the computer (`outside_references()`).
  Nothing with the document's text may be written outside the output folder: the Excel file is saved with its
  temporary files in a folder of their own there (`_temporary_files_in()` [10]). Test scans of your own go in
  `tests/cases/my_cases/`, which git ignores; `tests/cases/run_cases.py` keeps everything it writes for them in
  `my_cases/_results`.
