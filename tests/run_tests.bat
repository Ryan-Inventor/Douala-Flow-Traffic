@echo off
echo ================================================================
echo   DOUALAFLOW — Lancement des Tests
echo ================================================================
echo.

cd /d "%~dp0.."

echo  [1/3] Verification du serveur Flask...
curl -s -o nul -w "%%{http_code}" http://localhost:5000/ > tmp_status.txt 2>&1
set /p STATUS=<tmp_status.txt
del tmp_status.txt

if "%STATUS%"=="200" (
    echo  OK  Serveur Flask accessible
) else (
    echo  ERREUR  Serveur non accessible. Lance : python backend/app.py
    pause
    exit /b 1
)

echo.
echo  [2/3] Tests de l'API (endpoints + structure + variation)...
python tests/test_api.py

echo.
echo  [3/3] Moniteur temps reel (30 secondes)...
python tests/test_realtime.py 30

echo.
echo ================================================================
echo   Tests termines.
echo ================================================================
pause
