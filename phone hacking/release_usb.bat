@echo off
echo Stopping background ADB server...
"%~dp0platform-tools\adb.exe" kill-server
echo.
echo ADB server stopped successfully. USB port is now free for WebUSB!
timeout /t 3 >nul
