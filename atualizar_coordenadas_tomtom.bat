@echo off
rem =====================================================================
rem  COORDENADAS PELA TOMTOM - so os clientes DIVERGENTES (sem ponto,
rem  ponto longe da cidade, so da rua, so do bairro ou BAIRRO DIFERENTE).
rem  Usa a Geocoding API da TomTom com a CHAVE do Alexandre (plano gratis).
rem  A chave fica em tomtom_config.json, NESTA pasta (Regionais - Leandro).
rem  Sem chave: o arquivo abre no Bloco de Notas para
rem  colar a chave no lugar de COLE_A_CHAVE_AQUI, salvar e rodar de novo.
rem  Teto: 19.000 consultas por MES (RELATORIOS\TOMTOM_USO.json); se
rem  parar no meio, rode de novo (continua de onde parou).
rem  Nao rode junto com o atualizar_coordenadas.bat (os dois gravam o
rem  mesmo arquivo).
rem =====================================================================
title Coordenadas pela TomTom - so os divergentes
cd /d "%~dp0"

set "CFG=%~dp0tomtom_config.json"
if not exist "%CFG%" (
  > "%CFG%" echo {"api_key": "COLE_A_CHAVE_AQUI"}
)

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
%PY% "%~dp0geocodificar.py" --tomtom
goto :fim

:rodar
"%PY%" "%~dp0geocodificar.py" --tomtom

:fim
if errorlevel 2 (
  echo.
  echo  Falta a chave da API da TomTom. Vou abrir o arquivo no Bloco de Notas:
  echo  troque COLE_A_CHAVE_AQUI pela chave, salve, feche e rode de novo.
  echo.
  start "" notepad "%CFG%"
)
pause
exit /b 0
