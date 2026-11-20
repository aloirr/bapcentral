@echo off
rem =====================================================================
rem  FAROL DDR - gera o arquivo do mes em RELATORIOS
rem    FAROL_DDR_BAP_AAAA-MM.xlsx
rem  Le a Rotina, a Equipe e os Feriados do Farol MAIS RECENTE da pasta.
rem  Mes que ja existe NUNCA e sobrescrito (guarda o que o time marcou).
rem =====================================================================
title Farol DDR
cd /d "%~dp0"

set "PY="
if exist "%LOCALAPPDATA%\BAP_TOOLS\.venv\Scripts\python.exe" set "PY="%LOCALAPPDATA%\BAP_TOOLS\.venv\Scripts\python.exe""
if not defined PY where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo  Nao achei o Python nesta maquina. Rode o VERIFICAR_REQUISITOS.bat.
  pause
  exit /b 1
)

echo.
echo  Qual mes gerar? Digite AAAA-MM (ex.: 2026-11)
echo  ou so ENTER para o mes atual.
echo.
set "MES="
set /p "MES=Mes: "
%PY% "%~dp0farol_ddr.py" %MES%
echo.
pause
