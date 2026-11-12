# Build dist\Vox\ (the program folder) and dist\VoxSetup-<version>.exe
#
# Vox ships on the official Python runtime from python.org, whose programs are
# digitally signed by the Python Software Foundation. Vox.exe is that signed
# pythonw.exe under another name; nothing is packed or self-extracting, which
# is what antivirus tools tend to distrust.
#
# Needs: Python 3.12 (64-bit) with pip, and Inno Setup 6 for the installer.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$version = (python -c "import vox; print(vox.__version__)").Trim()
$py = (python -c "import platform; print(platform.python_version())").Trim()
$tag = "python" + (($py.Split('.')[0..1]) -join '')
$out = "dist\Vox"
Write-Host "Building Vox $version on Python $py"

Remove-Item dist -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $out -Force | Out-Null
New-Item -ItemType Directory build -Force | Out-Null

# 1. Official embeddable Python runtime
$zip = "build\python-$py-embed-amd64.zip"
if (-not (Test-Path $zip)) {
  Invoke-WebRequest "https://www.python.org/ftp/python/$py/python-$py-embed-amd64.zip" -OutFile $zip
}
Expand-Archive $zip -DestinationPath $out -Force
Copy-Item "$out\pythonw.exe" "$out\Vox.exe"
foreach ($exe in "pythonw.exe", "Vox.exe") {
  $signature = Get-AuthenticodeSignature "$out\$exe"
  Write-Host "$exe signature: $($signature.Status), $($signature.SignerCertificate.Subject)"
  if ($signature.Status -ne "Valid") { throw "$exe is not validly signed" }
}
# Look for modules in the runtime, this folder (the vox package) and Lib\site-packages
Set-Content "$out\$tag._pth" "$tag.zip`r`n.`r`nimport site" -Encoding ascii

# 2. Libraries
python -m pip install -r requirements.txt --target "$out\Lib\site-packages" `
  --no-warn-script-location --disable-pip-version-check --quiet
if ($LASTEXITCODE -ne 0) { exit 1 }

# 3. Vox itself, as plain readable source
Copy-Item vox "$out\vox" -Recurse
Get-ChildItem $out -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python packaging/make_icon.py
if ($LASTEXITCODE -ne 0) { exit 1 }
Copy-Item packaging\vox.ico "$out\vox.ico"

# 4. Installer
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
  Write-Host "Inno Setup not found; skipping the installer. $out is ready (run: Vox.exe -m vox)."
  exit 0
}
$env:VOX_VERSION = $version
& $iscc /Qp packaging\installer.iss
if ($LASTEXITCODE -ne 0) { exit 1 }

$setup = "dist\VoxSetup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
[System.IO.File]::WriteAllText("$setup.sha256", "$hash  VoxSetup-$version.exe`n")
Write-Host "Built $setup ($hash)"
