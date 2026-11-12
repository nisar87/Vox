# Build dist\Vox\Vox.exe and dist\VoxSetup-<version>.exe
# Needs: pip install -r requirements-dev.txt, and Inno Setup 6 for the installer.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$version = (python -c "import vox; print(vox.__version__)").Trim()
Write-Host "Building Vox $version"

python packaging/make_icon.py
if ($LASTEXITCODE -ne 0) { exit 1 }

python -m PyInstaller --noconfirm --windowed --name Vox --icon packaging/vox.ico `
  --add-data "vox/ui;vox/ui" `
  --collect-all faster_whisper --collect-all ctranslate2 `
  --collect-submodules uvicorn --collect-submodules websockets `
  --hidden-import pystray._win32 --hidden-import win32com.client `
  --hidden-import pythoncom --hidden-import win32timezone `
  launcher.py
if ($LASTEXITCODE -ne 0) { exit 1 }

$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
  Write-Host "Inno Setup not found; skipping the installer. dist\Vox\Vox.exe is ready."
  exit 0
}
$env:VOX_VERSION = $version
& $iscc /Qp packaging\installer.iss
if ($LASTEXITCODE -ne 0) { exit 1 }

$setup = "dist\VoxSetup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
[System.IO.File]::WriteAllText("$setup.sha256", "$hash  VoxSetup-$version.exe`n")
Write-Host "Built $setup ($hash)"
