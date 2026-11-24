# Build standalone AudioCapture.exe
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

if (-not (Test-Path "icon.ico")) {
    pip install pillow
    python make_icon.py
}

python -m PyInstaller AudioCapture.spec --clean --noconfirm

Write-Host ""
Write-Host "Built: dist\AudioCapture.exe"