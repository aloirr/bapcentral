@echo off
rem =====================================================================
rem  INSTALAR AS BIBLIOTECAS DE PDF E DE IMAGEM (reportlab e pillow)
rem  Fazem o "Exportar PDF" dos relatorios e as Parciais (imagem do
rem  WhatsApp e PDF).
rem  Instala nos dois Pythons que os programas BAP usam nesta maquina:
rem    1) o ambiente do BAP Tools (%LOCALAPPDATA%\BAP_TOOLS\.venv)
rem    2) o Python do Windows (py / python)
rem  Precisa de internet (pypi.org). Pode rodar de novo sem problema.
rem =====================================================================
title Instalar biblioteca de PDF - BAP
cd /d "%~dp0"
set "OK=0"

set "VPY=%LOCALAPPDATA%\BAP_TOOLS\.venv\Scripts\python.exe"
if exist "%VPY%" (
  echo.
  echo  [1/2] Ambiente do BAP Tools: %VPY%
  "%VPY%" -m pip install --upgrade reportlab pillow --disable-pip-version-check
  "%VPY%" -c "import reportlab, PIL; print('   reportlab', reportlab.Version, '+ pillow', PIL.__version__, 'OK')" && set "OK=1"
) else (
  echo  [1/2] Ambiente do BAP Tools nao existe nesta maquina - pulei.
)

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if defined PY (
  echo.
  echo  [2/2] Python do Windows: %PY%
  %PY% -m pip install --upgrade reportlab pillow --disable-pip-version-check
  %PY% -c "import reportlab, PIL; print('   reportlab', reportlab.Version, '+ pillow', PIL.__version__, 'OK')" && set "OK=1"
) else (
  echo  [2/2] Nao achei o Python do Windows - pulei.
)

if not exist "SISTEMA BAP\logs" mkdir "SISTEMA BAP\logs"
echo PDF instalado em %date% %time% - OK=%OK% > "SISTEMA BAP\logs\instalar_pdf_ultimo.txt"
echo.
if "%OK%"=="1" (
  echo  ============================================================
  echo   Pronto. O "Exportar PDF" e as Parciais ja funcionam.
  echo  ============================================================
) else (
  echo  ============================================================
  echo   Nao consegui instalar. Costuma ser proxy/firewall bloqueando
  echo   o pypi.org. Rode o VERIFICAR_REQUISITOS.bat e me mande o
  echo   DIAGNOSTICO_BAP.txt.
  echo  ============================================================
)
echo.
timeout /t 15
