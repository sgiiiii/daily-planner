@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python run.py --open %*
    goto :end
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 run.py --open %*
    goto :end
)

echo.
echo Python не найден. Установите Python 3.10+ с https://www.python.org/downloads/
echo и запустите этот файл снова.
echo.
pause

:end
