@echo off
REM ---------------------------------------------------------------------
REM  Scan de requisitos do BAP Tools e do Planner BAP.
REM  Clique duas vezes. Gera o DIAGNOSTICO_BAP.txt nesta pasta.
REM ---------------------------------------------------------------------
title Scan de requisitos - BAP
cd /d "%~dp0"

set "PY="
call :achar py
call :achar python
call :achar python3
if not defined PY goto :sempython

echo.
echo  Rodando o scan com: %PY%
echo  (pode levar ate um minuto - ele abre e fecha a janela para testar)
echo.
%PY% "%~dp0verificar_requisitos.py"
echo.
echo  ============================================================
echo   Relatorio salvo em DIAGNOSTICO_BAP.txt, nesta pasta.
echo   Mande esse arquivo para o Claude.
echo  ============================================================
echo.
pause
exit /b 0

:achar
if defined PY exit /b 0
%1 -c "import sys" >nul 2>&1
if errorlevel 1 exit /b 0
set "PY=%1"
exit /b 0

:sempython
echo.
echo  ============================================================
echo   NAO ENCONTREI PYTHON NESTE COMPUTADOR.
echo.
echo   E esse o motivo de o .bat abrir e fechar.
echo.
echo   1. Baixe em https://www.python.org/downloads/
echo   2. No instalador marque as DUAS caixas:
echo         [x] Add python.exe to PATH
echo         [x] tcl/tk and IDLE
echo   3. Reinicie o computador e rode este .bat de novo.
echo.
echo   Obs.: se ao digitar "python" abrir a Microsoft Store, e um
echo   atalho falso. Desligue em Configuracoes ^> Aplicativos ^>
echo   Configuracoes avancadas de aplicativo ^> Aliases de
echo   execucao de aplicativo ^> desmarque python.exe.
echo  ============================================================
echo.
pause
exit /b 1
