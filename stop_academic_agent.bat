@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_academic_agent.ps1"
exit /b %ERRORLEVEL%
