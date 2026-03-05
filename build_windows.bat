@echo off
echo PicPlotter Auto - Windows Build Script
echo =======================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Building executable...
python build\build.py

echo.
echo Build complete! Check the 'dist' folder for PicPlotterAuto.exe
pause
