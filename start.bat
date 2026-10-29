@echo off
rem One-click start on Windows: double-click this file.
rem Optional arguments are passed to start.ps1:  start.bat -Build  /  start.bat -NoBrowser
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
