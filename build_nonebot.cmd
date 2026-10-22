@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_plugin.ps1" -Platform nonebot %*
set "FARM_BUILD_EXIT=%ERRORLEVEL%"
if not "%FARM_BUILD_NO_PAUSE%"=="1" pause
exit /b %FARM_BUILD_EXIT%
