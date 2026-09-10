@echo off
setlocal
title PDF Field Editor

set "APP_DIR=%~dp0pdf_field_editor"
set "LOG_FILE=%~dp0pdf_field_editor\launcher.log"
set "OCR_KEY_FILE=%~dp0pdf_field_editor\ocr_api_key.txt"

echo [%date% %time%] Launcher started>"%LOG_FILE%"

where python >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto no_python

if not exist "%APP_DIR%\app.py" goto no_app

if exist "%OCR_KEY_FILE%" set /p OCR_API_KEY=<"%OCR_KEY_FILE%"

python -c "import streamlit, pdfplumber, pypdf, reportlab, requests, pypdfium2, docx" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto install_packages
goto start_app

:install_packages
echo Installing required packages...
python -m pip install -r "%APP_DIR%\requirements.txt" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto install_failed

:start_app
echo Starting PDF Field Editor...
echo Your browser will open automatically.
cd /d "%APP_DIR%"
start "" "http://localhost:8501"
python -m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false >>"%LOG_FILE%" 2>&1
goto app_stopped

:no_python
echo Python was not found. Please install Python 3 first.
goto failed

:no_app
echo app.py was not found in: %APP_DIR%
goto failed

:install_failed
echo Package installation failed. Check your internet connection.
goto failed

:app_stopped
echo.
echo The platform stopped or port 8501 is already in use.
goto failed

:failed
echo.
echo Error details were saved to:
echo %LOG_FILE%
pause
exit /b 1
