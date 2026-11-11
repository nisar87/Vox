@echo off
cd /d "%~dp0"
echo Setting up Vox (first run takes a few minutes)...
where python >nul 2>nul || (echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add to PATH". & pause & exit /b 1)
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (echo. & echo Setup hit a problem. Scroll up for the first error. & pause & exit /b 1)
echo.
echo Done. Double-click run.bat to start Vox.
pause
