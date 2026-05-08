@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ========================================
echo   OutreachHub API Server
echo ========================================
echo DB: %~dp0data\outreach.db
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+ first.
    pause
    exit /b 1
)

:: Install dependencies
pip show flask >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing flask flask-cors requests ...
    pip install flask flask-cors requests -q
    echo [OK]
)

:: Get local IP
set "LOCAL_IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "ipv4" ^| findstr /v "127."') do (
    if not defined LOCAL_IP set "LOCAL_IP=%%a"
)
set "LOCAL_IP=%LOCAL_IP: =%"

echo [INFO] Local IP: http://%LOCAL_IP%:5000
echo.
echo Other PCs: set API_BASE = "http://%LOCAL_IP%:5000" in config.py
echo.
echo Press Ctrl+C to stop server.
echo ========================================
echo.

:: Firewall (skip if already added)
netsh advfirewall firewall show rule name="OutreachHub API" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Opening firewall port 5000 ...
    netsh advfirewall firewall add rule name="OutreachHub API" dir=in action=allow protocol=TCP localport=5000
)

echo [INFO] Starting server ...
python server\api_server.py 5000
pause
