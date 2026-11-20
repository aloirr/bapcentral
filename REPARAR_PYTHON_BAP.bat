@echo off
rem =====================================================================
rem  REPARAR O PYTHON DO BAP (12/10/2026)
rem  1) Diagnostico: quais Pythons existem nesta maquina, a versao de cada
rem     um e quais bibliotecas do BAP estao faltando.
rem  2) Reparo: instala o que falta (openpyxl, reportlab, pillow, requests)
rem     no Python que o BAP Central usa e no Python do Windows.
rem  Precisa de internet (pypi.org). Pode rodar de novo sem problema.
rem  O resultado fica em logs\REPARO_PYTHON_ultimo.txt
rem =====================================================================
title Reparar Python do BAP
cd /d "%~dp0"
if not exist "SISTEMA BAP\logs" mkdir "SISTEMA BAP\logs"
set "LOG=%~dp0SISTEMA BAP\logs\REPARO_PYTHON_ultimo.txt"
set "LIBS=openpyxl reportlab pillow requests"
set "TESTE=import openpyxl, reportlab, PIL, requests, tkinter; print('BIBLIOTECAS OK - openpyxl', openpyxl.__version__)"

echo REPARO PYTHON BAP - %date% %time% > "%LOG%"
echo Computador: %COMPUTERNAME%  Usuario: %USERNAME% >> "%LOG%"

echo.
echo  ============================================================
echo   1/3  DIAGNOSTICO (antes)
echo  ============================================================
call :diagnostico ANTES

echo.
echo  ============================================================
echo   2/3  REPARO
echo  ============================================================
echo. >> "%LOG%"
echo ===== REPARO ===== >> "%LOG%"
set "VPY=%LOCALAPPDATA%\BAP_TOOLS\.venv\Scripts\python.exe"
if exist "%VPY%" (
  echo  Ambiente do BAP Tools: %VPY%
  "%VPY%" -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo  [!] O ambiente do BAP Tools esta QUEBRADO ^(o Python dele sumiu ou mudou de versao^).
    echo  [!] AMBIENTE BAP_TOOLS QUEBRADO - nao abre >> "%LOG%"
  ) else (
    "%VPY%" -m pip install --upgrade %LIBS% --disable-pip-version-check >> "%LOG%" 2>&1
    echo  ... instalado no ambiente do BAP Tools
  )
) else (
  echo  Ambiente do BAP Tools nao existe nesta maquina.
  echo  BAP_TOOLS .venv NAO EXISTE >> "%LOG%"
)
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if defined PY (
  echo  Python do Windows: %PY%
  %PY% -m pip install --upgrade %LIBS% --disable-pip-version-check >> "%LOG%" 2>&1
  echo  ... instalado no Python do Windows
) else (
  echo  [!] Nao achei o Python do Windows.
  echo  PYTHON DO WINDOWS NAO ENCONTRADO >> "%LOG%"
)

echo.
echo  ============================================================
echo   3/3  DIAGNOSTICO (depois)
echo  ============================================================
call :diagnostico DEPOIS

echo.
echo  Pronto. Abra o BAP Central de novo.
echo  O relatorio ficou em SISTEMA BAP\logs\REPARO_PYTHON_ultimo.txt
echo.
timeout /t 20
exit /b 0

rem ---------------------------------------------------------------------
:diagnostico
echo. >> "%LOG%"
echo ===== DIAGNOSTICO %1 ===== >> "%LOG%"
echo --- py -0p (Pythons instalados) >> "%LOG%"
py -0p >> "%LOG%" 2>&1
echo --- where python / pythonw / pyw >> "%LOG%"
where python >> "%LOG%" 2>&1
where pythonw >> "%LOG%" 2>&1
where pyw >> "%LOG%" 2>&1
set "V=%LOCALAPPDATA%\BAP_TOOLS\.venv"
echo --- ambiente BAP_TOOLS: %V% >> "%LOG%"
if exist "%V%\pyvenv.cfg" (type "%V%\pyvenv.cfg" >> "%LOG%") else (echo pyvenv.cfg nao existe >> "%LOG%")
if exist "%V%\Scripts\python.exe" (
  "%V%\Scripts\python.exe" -c "import sys; print('VENV', sys.version, sys.executable)" >> "%LOG%" 2>&1
  "%V%\Scripts\python.exe" -c "%TESTE%" >> "%LOG%" 2>&1
  "%V%\Scripts\python.exe" -c "%TESTE%" >nul 2>&1 && (echo   [ OK ] ambiente do BAP Tools) || (echo   [FALTA] ambiente do BAP Tools - falta biblioteca ou Python quebrado)
)
echo --- Python do Windows >> "%LOG%"
py -3 -c "import sys; print('PY', sys.version, sys.executable)" >> "%LOG%" 2>&1
py -3 -c "%TESTE%" >> "%LOG%" 2>&1
py -3 -c "%TESTE%" >nul 2>&1 && (echo   [ OK ] Python do Windows) || (echo   [FALTA] Python do Windows - falta biblioteca)
exit /b 0
