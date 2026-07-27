@echo off
REM Double-click launcher for the adversarial brain eval. Writes eval_log.txt. Synthetic only.
pushd "%~dp0"
set "PY=Z:\Administration\cowork\tools\refagent-venv\Scripts\python.exe"
"%PY%" "%~dp0adversarial_eval.py"
echo.
echo Done. Output in eval_log.txt
echo.
pause
popd
