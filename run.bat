@echo off
cd /d "%~dp0"
if not exist .venv (call install.bat)
start "" .venv\Scripts\pythonw.exe -m vox
