@echo off
REM Double-click launcher for the chatbot brain smoke test.
REM Runs all three synthetic scenarios and writes the output to smoke_log.txt
REM so it can be read back afterward. Synthetic data only - no real patients.

pushd "%~dp0"

set "PY=Z:\Administration\cowork\tools\refagent-venv\Scripts\python.exe"
set "LOG=%~dp0smoke_log.txt"

echo Running chatbot brain smoke test... > "%LOG%"
echo Started: %DATE% %TIME% >> "%LOG%"
echo ------------------------------------------------------------ >> "%LOG%"

"%PY%" "%~dp0fake_chat.py" --scenario all >> "%LOG%" 2>&1

echo ------------------------------------------------------------ >> "%LOG%"
echo Finished: %DATE% %TIME% >> "%LOG%"

echo.
echo Done. Output written to smoke_log.txt
echo.
type "%LOG%"
echo.
pause
popd
