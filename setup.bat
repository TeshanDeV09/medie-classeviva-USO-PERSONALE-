@echo off
title ClasseViva Dashboard - Setup

echo.
echo =====================================================
echo    ClasseViva Dashboard - Setup Automatico
echo    Uso strettamente personale
echo =====================================================
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Python non trovato.
    echo Scaricalo da https://python.org e riavvia.
    pause
    exit /b 1
)
echo [OK] Python trovato.

:: Crea virtualenv
if not exist "venv" (
    echo [INFO] Creo ambiente virtuale...
    python -m venv venv
)
echo [OK] Ambiente virtuale pronto.

:: Attiva e installa dipendenze
echo [INFO] Installo dipendenze (potrebbe richiedere qualche minuto)...
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERRORE] Installazione dipendenze fallita.
    pause
    exit /b 1
)
echo [OK] Dipendenze installate.

:: Crea cartella logs
if not exist "logs" mkdir logs

:: Crea .env se non esiste
if not exist ".env" (
    echo [INFO] Creo file .env...
    (
        echo CLASSEVIVA_USER=inserisci_qui_il_tuo_username
        echo CLASSEVIVA_PASS=inserisci_qui_la_tua_password
        echo FLASK_ENV=development
        echo FLASK_SECRET_KEY=chiave-segreta-casuale-123
        echo CACHE_TTL=300
        echo THROTTLE_SECONDS=30
    ) > .env
    echo.
    echo =====================================================
    echo  IMPORTANTE: si apre il file .env
    echo  Inserisci le tue credenziali ClasseViva e salva.
    echo =====================================================
    echo.
    start notepad .env
) else (
    echo [OK] File .env gia' esistente.
)

echo.
echo =====================================================
echo  Setup completato! Avvia con: start.bat
echo =====================================================
echo.
pause
