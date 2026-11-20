@echo off
rem =====================================================================
rem  ATUALIZAR COORDENADAS - latitude e longitude dos clientes pelo
rem  endereco (OpenStreetMap, 1 consulta por segundo). So vai quem e novo
rem  ou mudou de endereco. A primeira vez leva perto de 1 hora.
rem  Funciona de qualquer pasta: tudo aqui usa a pasta deste .bat
rem =====================================================================
title Atualizar coordenadas dos clientes
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\BAP_TOOLS\.venv\Scripts\python.exe"
if exist "%PY%" goto :rodar
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" goto :rodar

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo.
  echo  Nao achei o Python nesta maquina.
  echo  Rode o VERIFICAR_REQUISITOS.bat - ele diz o que falta e como resolver.
  echo.
  pause
  exit /b 1
)
%PY% "%~dp0geocodificar.py"
pause
exit /b 0

:rodar
"%PY%" "%~dp0geocodificar.py"
pause
exit /b 0
