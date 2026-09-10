@echo off
setlocal EnableExtensions
chcp 65001 >nul
title 發票 PDF／Word 處理平台
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "READY_FILE=%VENV_DIR%\.packages_ready"
set "LOG_FILE=%~dp0launcher.log"

echo [%date% %time%] 啟動程序開始>"%LOG_FILE%"

if exist "%VENV_PY%" goto install_packages

echo [1/3] 正在建立專案專用環境，首次執行請稍候...
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv "%VENV_DIR%" >>"%LOG_FILE%" 2>&1
) else (
    where python >nul 2>&1
    if errorlevel 1 goto no_python
    python -m venv "%VENV_DIR%" >>"%LOG_FILE%" 2>&1
)
if errorlevel 1 goto setup_failed

:install_packages
if exist "%READY_FILE%" goto start_app
echo [2/3] 正在安裝必要套件，需要網路連線...
"%VENV_PY%" -m pip install --upgrade pip >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto install_failed
"%VENV_PY%" -m pip install -r "%~dp0requirements.lock.txt" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto install_failed
"%VENV_PY%" -c "from pathlib import Path; Path(r'%READY_FILE%').write_text('ready', encoding='utf-8')" >>"%LOG_FILE%" 2>&1
if errorlevel 1 goto install_failed

:start_app
echo [3/3] 正在啟動平台...
echo 瀏覽器即將開啟：http://localhost:8501/
start "" "http://localhost:8501/"
"%VENV_PY%" -m streamlit run "%~dp0app.py" --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false >>"%LOG_FILE%" 2>&1
goto app_stopped

:no_python
echo.
echo 找不到 Python 3。
echo 請先至 https://www.python.org/downloads/ 安裝 Python，安裝時勾選 Add Python to PATH。
goto failed

:setup_failed
echo.
echo 無法建立專案環境。
goto failed

:install_failed
echo.
echo 套件安裝失敗，請確認網路連線後再執行一次。
goto failed

:app_stopped
echo.
echo 平台已停止，或連接埠 8501 已被其他程式使用。
goto failed

:failed
echo 錯誤記錄：%LOG_FILE%
pause
exit /b 1
