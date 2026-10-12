@echo off
cd /d "%~dp0"
python -m build_patch restore
echo.
pause
