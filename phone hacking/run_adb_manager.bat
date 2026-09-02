@echo off
cd /d "%~dp0"
py adb_manager.py
if errorlevel 1 pause
