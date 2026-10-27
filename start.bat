@echo off
rem One-click start for judges: double-click this file. Equivalent to start.ps1 (offline mode when node_modules is absent).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
pause
