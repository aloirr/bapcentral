@echo off
rem =====================================================================
rem  BAP CENTRAL - a porta de entrada do time (um cartao por papel)
rem  Funciona de qualquer pasta: tudo aqui usa a pasta deste .bat
rem =====================================================================
title BAP Central
cd /d "%~dp0"

rem 1) o ambiente do BAP Tools nesta maquina (tem tudo instalado)
set "PY=%LOCALAPPDATA%\BAP_TOOLS\.venv\Scripts\pythonw.exe"
if exist "%PY%" goto :abrir
set "PY=%~dp0.venv\Scripts\pythonw.exe"
if exist "%PY%" goto :abrir

rem 2) o Python da maquina, sem janela preta
set "PY="
where pyw >nul 2>&1 && set "PY=pyw -3"
if not defined PY where pythonw >nul 2>&1 && set "PY=pythonw"
if not defined PY (
  echo.
  echo  Nao achei o Python nesta maquina.
  echo  Rode o VERIFICAR_REQUISITOS.bat - ele diz o que falta e como resolver.
  echo.
  pause
  exit /b 1
)
start "" %PY% "%~dp0bap_central.py"
exit /b 0

:abrir
start "" "%PY%" "%~dp0bap_central.py"
exit /b 0
