$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path .venv)) {
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}

& .\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8080
