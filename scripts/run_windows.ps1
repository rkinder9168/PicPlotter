$ErrorActionPreference = "Stop"

param(
    [string]$WindowsPath = "C:\\dev\\PicPlotter_auto_gpt",
    [string]$WslPath = "\\wsl$\\Ubuntu\\home\\rkinder9168\\projects\\PicPlotter_auto_gpt"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$syncScript = Join-Path $scriptDir "sync_windows.ps1"

& $syncScript -WslPath $WslPath -WindowsPath $WindowsPath

if (!(Test-Path $WindowsPath)) {
    Write-Error "Windows path not found: $WindowsPath"
    exit 1
}

Set-Location $WindowsPath

$pythonCmd = @("py", "-3.12")
$venvPython = Join-Path $WindowsPath ".venv\\Scripts\\python.exe"

if (!(Test-Path $venvPython)) {
    & $pythonCmd[0] $pythonCmd[1] -m venv .venv
}

& $venvPython -m pip install -r requirements.txt
& $venvPython src\\main.py
