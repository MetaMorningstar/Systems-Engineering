@echo off
REM ============================================================================
REM  Make a Word template for the verification report.
REM  Double-click this file. It writes word_style\report_template.docx (or
REM  "report_template (2).docx" ... - an existing file is never overwritten)
REM  with every style the report uses and a sample of each, and opens it.
REM   1. Restyle it in Word: Home > Styles pane, right-click a style > Modify.
REM      Double-click the top or bottom of a page for the header and footer
REM      (logo, classification marking, page numbers).
REM   2. Save it (keep the .docx format).
REM   3. Write its name in word_style\report_style.ini under [document]:
REM          template = report_template.docx
REM  Every report made after that has this look. The text of the template is
REM  never copied into a report - only its styles, page layout, headers and
REM  footers.
REM ============================================================================
REM pushd (not cd) also works when this folder is on a network share (\\server\share)
pushd "%~dp0"
set SPEC_EXTRACTOR_LAUNCHER=1
set PYTHONUTF8=1

if exist ".venv\Scripts\python.exe" goto :use_venv
python spec_extractor.py --write-word-template word_style
goto :done
:use_venv
".venv\Scripts\python.exe" spec_extractor.py --write-word-template word_style
:done
popd
echo.
pause
