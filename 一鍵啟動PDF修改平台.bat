@echo off
setlocal
chcp 65001 >nul
title PDF Field Editor - Launcher Status
color 0B

set "APP_DIR=%~dp0pdf_field_editor"
set "LOG_DIR=%~dp0pdf_field_editor\logs"
set "LOG_FILE=%LOG_DIR%\launcher.log"
set "OCR_KEY_FILE=%~dp0pdf_field_editor\ocr_api_key.txt"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo [%date% %time%] Launcher started>"%LOG_FILE%"

echo ============================================================
echo   PDF / Word Invoice Editor
echo ============================================================
echo   [1/4] Checking application files...

if not exist "%APP_DIR%\app.py" goto no_app

echo   [2/4] Checking Python environment...
where python >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto no_python

if exist "%OCR_KEY_FILE%" set /p OCR_API_KEY=<"%OCR_KEY_FILE%"

echo   [3/4] Checking required packages...
python -c "import streamlit, pdfplumber, pypdf, reportlab, requests, pypdfium2, docx" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto install_packages
goto start_app

:install_packages
echo         Missing packages detected. Installing now...
echo [%date% %time%] Installing requirements>>"%LOG_FILE%"
python -m pip install -r "%APP_DIR%\requirements.txt" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto install_failed

:start_app
echo   [4/4] Starting local web service...
echo         Address: http://localhost:8501
echo         Keep this window open while using the platform.
echo         Runtime log: %LOG_FILE%
echo ============================================================
cd /d "%APP_DIR%"
start "" "http://localhost:8501"
python -u -m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false >>"%LOG_FILE%" 2>&1
set "APP_EXIT=%errorlevel%"
goto app_stopped

:no_python
echo   [ERROR] Python was not found. Please install Python 3 first.
echo [%date% %time%] ERROR Python not found>>"%LOG_FILE%"
goto failed

:no_app
echo   [ERROR] app.py was not found in: %APP_DIR%
echo [%date% %time%] ERROR app.py not found>>"%LOG_FILE%"
goto failed

:install_failed
echo   [ERROR] Package installation failed. Check the log and internet connection.
echo [%date% %time%] ERROR package installation failed>>"%LOG_FILE%"
goto failed

:app_stopped
echo.
echo The platform stopped. Port 8501 may already be in use.
echo [%date% %time%] ERROR Streamlit stopped with exit code %APP_EXIT%>>"%LOG_FILE%"
goto failed

:failed
echo.
echo Error details were saved to:
echo %LOG_FILE%
echo.
echo Last 15 log lines:
powershell -NoProfile -Command "if (Test-Path -LiteralPath '%LOG_FILE%') { Get-Content -LiteralPath '%LOG_FILE%' -Tail 15 }"
pause
exit /b 1
