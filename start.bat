@echo off
chcp 65001 >nul
title ClasseViva Dashboard

:: Verifica che .env esista e abbia le credenziali
if not exist ".env" (
    echo [ERRORE] File .env non trovato. Esegui prima setup.bat
    pause
    exit /b 1
)

:: Verifica che il venv esista
if not exist "venv\Scripts\activate.bat" (
    echo [ERRORE] Ambiente virtuale non trovato. Esegui prima setup.bat
    pause
    exit /b 1
)

:: Attiva venv
call venv\Scripts\activate.bat

:: Apri browser dopo 3 secondi
start /b cmd /c "timeout /t 4 /nobreak >nul && start http://127.0.0.1:5000"

echo.
echo  ╔═══════════════════════════════════════════════════╗
echo  ║         ClasseViva Dashboard in avvio...          ║
echo  ║                                                   ║
echo  ║   Il browser si aprira' automaticamente.          ║
echo  ║   Per fermare: premi CTRL+C                       ║
echo  ╚═══════════════════════════════════════════════════╝
echo.

python app.py

pause
