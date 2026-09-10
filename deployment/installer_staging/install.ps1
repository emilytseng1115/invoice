$ErrorActionPreference = "Stop"

$productName = "ECS 發票處理工具"
$installDir = Join-Path $env:LOCALAPPDATA "ECS Invoice Tool"
$payloadZip = Join-Path $PSScriptRoot "payload.zip"
$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"

New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Expand-Archive -LiteralPath $payloadZip -DestinationPath $installDir -Force

$shell = New-Object -ComObject WScript.Shell
$launcher = Join-Path $installDir "launch_invoice_tool.cmd"

foreach ($shortcutPath in @(
    (Join-Path $desktop "$productName.lnk"),
    (Join-Path $startMenu "$productName.lnk")
)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcher
    $shortcut.WorkingDirectory = $installDir
    $shortcut.Description = $productName
    $shortcut.Save()
}

Start-Process -FilePath $launcher -WorkingDirectory $installDir
[System.Windows.Forms.MessageBox]::Show(
    "安裝完成。已建立桌面捷徑並啟動發票處理工具。",
    $productName,
    "OK",
    "Information"
) | Out-Null
