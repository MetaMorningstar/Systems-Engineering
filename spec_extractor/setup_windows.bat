@echo off
REM ============================================================================
REM  One-time setup for Spec Extractor on Windows.
REM  Double-click this file. It creates a private Python environment (.venv) in
REM  this folder and installs the required packages in exactly the versions the
REM  tool was tested with (constraints.txt). Takes a few minutes.
REM ============================================================================
REM pushd (not cd) also works when this folder is on a network share (\\server\share)
pushd "%~dp0"

REM Find a tested Python: 64-bit, version 3.10 to 3.14, standard build.
REM  * First the "py" command (python.org launcher or the newer Python install
REM    manager), then "python" on the PATH. PY_CHECK rejects 32-bit Python, the
REM    optional free-threaded build (python3.14t) and every version outside 3.10
REM    to 3.14: the OCR and table packages were not tested there, and most of
REM    them cannot even be installed there.
REM  * Search order: 3.12 and 3.11 first, because only Python 3.12 and older can
REM    install the fast page-orientation classifier. 3.13 and 3.14 are just as
REM    accurate but check page orientation with a slower OCR-based method.
REM    3.10 comes last: it reaches end of life in October 2026.
REM  * PYTHON_MANAGER_AUTOMATIC_INSTALL=0 stops the Python install manager from
REM    silently downloading a Python during this search. If no suitable Python
REM    is installed, the message at the end says what to install.
REM  * Each check is written as two lines: run the command, then test its exit
REM    code with "if not errorlevel 1". Do not shorten this to the one-line form
REM    that chains the "set" onto the command. After a command that could not be
REM    started at all (no Python installed), some command interpreters still run
REM    the chained "set" and this script would pick a Python that is not there.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=0"
set "PY_CHECK=import sys, sysconfig; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) and sys.maxsize > 2**32 and not sysconfig.get_config_var('Py_GIL_DISABLED') else 1)"
set "PY="
for %%V in (3.12 3.11 3.13 3.14 3.10) do (
    if not defined PY (
        py -%%V -c "%PY_CHECK%" >nul 2>nul
        if not errorlevel 1 set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "%PY_CHECK%" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :no_python

echo Using %PY%
%PY% --version
echo Creating the Python environment in "%CD%\.venv" ...
%PY% -m venv .venv || goto :error

REM Install the packages. constraints.txt pins each one to the version that passed the tests.
REM Offline install: if a "wheels" folder exists (see README), install from it without internet.
if exist "wheels\" goto :offline
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt -c constraints.txt || goto :error
goto :done
:offline
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt -c constraints.txt || goto :error

:done
echo.
echo Setup complete. Double-click run_extractor.bat (or drag PDF/TIFF files onto it).
popd
pause
exit /b 0

:no_python
echo No supported Python was found. Spec Extractor needs a 64-bit Python 3.10, 3.11,
echo 3.12, 3.13 or 3.14 in its standard build. Python 3.15 and newer are not supported yet.
echo Install the 64-bit Python 3.12 from python.org - it can sit next to other versions:
echo  * python.org installer: tick "Add python.exe to PATH" during installation.
echo  * Python install manager: open a new terminal and run   py install 3.12
echo Then run this file again.
goto :fail

:error
echo.
echo Setup failed - read the messages above. A company proxy may need to be configured
echo for pip, or use the offline "wheels" method described in README.md.
:fail
popd
pause
exit /b 1
