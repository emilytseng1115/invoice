@echo off
setlocal
start "" /b "%~dp0runtime\pythonw.exe" "%~dp0app\portable_launcher.py"
exit /b 0
