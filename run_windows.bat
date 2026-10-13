@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -m venv .venv
  if errorlevel 1 goto error
)
echo Installing or updating dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo Starting API at http://127.0.0.1:8000/docs
".venv\Scripts\python.exe" -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
if errorlevel 1 goto error
goto end
:error
echo Setup or startup failed. Check the error above.
pause
:end
endlocal
