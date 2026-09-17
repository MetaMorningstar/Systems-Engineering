@echo off
REM ============================================================================
REM  Run Spec Extractor.
REM   * Double-click: a window opens to choose scanned PDF/TIFF files (or a folder).
REM   * Or drag and drop files/folders onto this .bat file.
REM     (A file or folder name containing "&" cannot be dragged onto a .bat file -
REM      rename it, or double-click and use the file window instead.)
REM  Results are written to an "extraction_output" folder next to the documents.
REM ============================================================================
REM pushd (not cd) also works when this folder is on a network share (\\server\share)
pushd "%~dp0"
set SPEC_EXTRACTOR_LAUNCHER=1
set PYTHONUTF8=1

REM (no parentheses around %* : a dragged file name like "Spec(RevA).pdf" would break them)
if exist ".venv\Scripts\python.exe" goto :use_venv
python spec_extractor.py %*
goto :done
:use_venv
".venv\Scripts\python.exe" spec_extractor.py %*
:done
popd
echo.
pause
