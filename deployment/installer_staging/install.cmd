@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; & '%~dp0install.ps1'"
if errorlevel 1 (
  powershell.exe -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('安裝失敗，請聯絡系統管理員。','ECS 發票處理工具','OK','Error')"
  exit /b 1
)
exit /b 0
