@echo off
REM ============================================================================
REM  One-time setup for Spec Extractor on Windows.
REM  Double-click this file. It creates a private Python environment (.venv) in
REM  this folder and installs the required packages. Takes a few minutes.
REM ============================================================================
REM pushd (not cd) also works when this folder is on a network share (\\server\share)
pushd "%~dp0"

REM Find a supported 64-bit Python (3.10 to 3.13): the "py" launcher from python.org first
REM (3.12 and 3.11 preferred), then "python" on the PATH.
set "PY="
for %%V in (3.12 3.11 3.13 3.10) do (
    if not defined PY py -%%V -c "import sys; sys.exit(0 if sys.maxsize > 2**32 else 1)" >nul 2>nul && set "PY=py -%%V"
)
if not defined PY python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) and sys.maxsize > 2**32 else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto :no_python

echo Using %PY%
echo Creating the Python environment in "%CD%\.venv" ...
%PY% -m venv .venv || goto :error

REM Offline install: if a "wheels" folder exists (see README), install from it without internet.
if exist "wheels\" goto :offline
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
goto :done
:offline
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt || goto :error

:done
echo.
echo Setup complete. Double-click run_extractor.bat (or drag PDF/TIFF files onto it).
popd
pause
exit /b 0

:no_python
echo No supported Python was found. Install the 64-bit Python 3.12 or 3.11 from python.org,
echo tick "Add python.exe to PATH" during installation, then run this file again.
goto :fail

:error
echo.
echo Setup failed - read the messages above. A company proxy may need to be configured
echo for pip, or use the offline "wheels" method described in README.md.
:fail
popd
pause
exit /b 1
