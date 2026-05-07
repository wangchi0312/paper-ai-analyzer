@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "PYTHON_EXE=D:\software\anaconda\envs\paper-ai\python.exe"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "FRONTEND_NODE_MODULES=%FRONTEND_DIR%\node_modules"
set "APP_URL=http://127.0.0.1:5173"

echo.
echo [Academic Agent] Preparing to start...

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python env not found:
    echo         %PYTHON_EXE%
    echo Please make sure the paper-ai conda env exists.
    pause
    exit /b 1
)

if not exist "%FRONTEND_NODE_MODULES%" (
    echo [ERROR] Frontend dependencies are missing:
    echo         %FRONTEND_NODE_MODULES%
    echo Run the following first:
    echo         cd /d "%FRONTEND_DIR%"
    echo         npm install
    pause
    exit /b 1
)

echo [1/3] Starting backend...
start "Academic Agent Backend" cmd /k "cd /d ""%ROOT_DIR%"" && ""%PYTHON_EXE%"" -m paper_analyzer.server"

echo [2/3] Starting frontend...
start "Academic Agent Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev -- --host 127.0.0.1 --port 5173"

echo [3/3] Opening browser...
timeout /t 3 /nobreak >nul
start "" "%APP_URL%"

echo [Academic Agent] Start commands sent.
echo If the page is not ready yet, wait a few seconds and refresh.
exit /b 0
