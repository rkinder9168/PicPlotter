@echo off
echo PicPlotter Auto
echo ===============
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

REM Check if dependencies are installed
python -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

REM Run the application
echo Starting PicPlotter Auto...
python -m src.main

pause
