$ErrorActionPreference = "Stop"

param(
    [string]$WslPath = "\\wsl$\\Ubuntu\\home\\rkinder9168\\projects\\PicPlotter_auto_gpt",
    [string]$WindowsPath = "C:\\dev\\PicPlotter_auto_gpt"
)

if (!(Test-Path $WslPath)) {
    Write-Error "WSL path not found: $WslPath"
    exit 1
}

if (!(Test-Path $WindowsPath)) {
    New-Item -ItemType Directory -Path $WindowsPath | Out-Null
}

robocopy $WslPath $WindowsPath /E /XD ".venv" "__pycache__" ".git" /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -ge 8) {
    exit $LASTEXITCODE
}

Write-Host "Synced $WslPath -> $WindowsPath"
