@echo off
cd /d "%~dp0"
python -m build_patch status
echo.
pause
