@echo off
cd /d "%~dp0"
python -m build_patch apply
echo.
pause
