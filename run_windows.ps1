$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -m venv .venv
}
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
Write-Host 'Starting API at http://127.0.0.1:8000/docs'
& '.\.venv\Scripts\python.exe' -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
