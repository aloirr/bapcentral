@echo off
rem =====================================================================
rem  COORDENADAS PELO GOOGLE - (02/11, Alexandre) TODOS os clientes da
rem  base de novo, menos os pontos postos a mao (MANUAL / link do Google).
rem  Parou no meio? Rode de novo: continua de onde parou.
rem  (02/11) Depois, a EMPRESA pela Places API (New) - a mesma chave - para
rem  quem ficou fora da casa (rua/bairro ou outra rua/outro bairro/outro
rem  numero). Ative a "Places API (New)" no projeto da chave no Google Cloud.
rem  Usa a Geocoding API oficial do Google com a CHAVE do Alexandre.
rem  A chave fica em google_maps_config.json, NESTA pasta (Regionais - Leandro).
rem  Sem chave: o arquivo abre no Bloco de Notas para
rem  colar a chave no lugar de COLE_A_CHAVE_AQUI, salvar e rodar de novo.
rem  Teto: 9.000 consultas por mes (RELATORIOS\GOOGLE_MAPS_USO.json).
rem  Rode DEPOIS do atualizar_coordenadas.bat (o gratuito).
rem =====================================================================
title Coordenadas pelo Google - todos os clientes
cd /d "%~dp0"

set "CFG=%~dp0google_maps_config.json"
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
%PY% "%~dp0geocodificar.py" --google --todos
goto :fim

:rodar
"%PY%" "%~dp0geocodificar.py" --google --todos

:fim
if errorlevel 2 (
  echo.
  echo  Falta a chave da API do Google. Vou abrir o arquivo no Bloco de Notas:
  echo  troque COLE_A_CHAVE_AQUI pela chave, salve, feche e rode de novo.
  echo.
  start "" notepad "%CFG%"
)
pause
exit /b 0
