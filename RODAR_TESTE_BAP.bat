@echo off
rem Roda as baterias smoke_processos.py e smoke_relatorios.py na pasta deste .bat
rem e grava o resultado em logs\smoke_processos_ultimo.txt e
rem logs\smoke_relatorios_ultimo.txt.
cd /d "%~dp0"
if not exist "SISTEMA BAP\logs" mkdir "SISTEMA BAP\logs"
set "PY=python"
where python >/dev/null 2>/dev/null || set "PY=py"
set SAIDA=SISTEMA BAP\logs\smoke_processos_ultimo.txt
echo Teste iniciado em %date% %time% > "%SAIDA%"
%PY% smoke_processos.py >> "%SAIDA%" 2>&1
echo. >> "%SAIDA%"
echo Codigo de saida: %errorlevel% >> "%SAIDA%"
echo Teste terminado em %date% %time% >> "%SAIDA%"
set SAIDA2=SISTEMA BAP\logs\smoke_relatorios_ultimo.txt
echo Teste iniciado em %date% %time% > "%SAIDA2%"
%PY% smoke_relatorios.py >> "%SAIDA2%" 2>&1
echo. >> "%SAIDA2%"
echo Codigo de saida: %errorlevel% >> "%SAIDA2%"
echo Teste terminado em %date% %time% >> "%SAIDA2%"
type "%SAIDA%"
type "%SAIDA2%"
timeout /t 8 >nul
