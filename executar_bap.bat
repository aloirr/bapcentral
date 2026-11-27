@echo off
REM ===========================================================================
REM  BAP TOOLS -> TABELA_BAP.xlsx
REM  Arquivo chamado pelo Agendador de Tarefas do Windows (08h00 e 14h00).
REM
REM  NAO TEM CAMINHO FIXO: ele usa a pasta onde ele mesmo esta. Mova a pasta
REM  inteira de lugar e continua funcionando - so recrie a tarefa agendada
REM  apontando para o novo caminho deste arquivo.
REM
REM  A janela mostra o andamento do robo e o log (SISTEMA BAP\logs\agendador.log)
REM  recebe as mesmas linhas (T-0057).
REM
REM  Codigo de saida 0 = tudo certo | 1 = alguma falha (o Agendador registra).
REM ===========================================================================
chcp 65001 >nul
setlocal

set "PASTA=%~dp0"
if "%PASTA:~-1%"=="\" set "PASTA=%PASTA:~0,-1%"
REM O ambiente virtual fica na pasta local desta maquina, fora do OneDrive:
REM cada computador tem o seu, e nada disso sincroniza.
set "PYTHON=%LOCALAPPDATA%\BAP_TOOLS\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%PASTA%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

set "LOG=SISTEMA BAP\logs\agendador.log"

cd /d "%PASTA%" || (echo Pasta %PASTA% nao encontrada. & exit /b 1)
if not exist "SISTEMA BAP\logs" mkdir "SISTEMA BAP\logs"

if not exist "%PASTA%\bap_automation.py" (
    call :linha "bap_automation.py nao esta em %PASTA%."
    exit /b 1
)

call :linha ""
call :linha "===================================================="
call :linha "INICIO %date% %time% em %COMPUTERNAME% por %USERNAME%"
call :linha "pasta: %PASTA%"
call :linha "===================================================="

"%PYTHON%" "%PASTA%\bap_automation.py" --espelho "%LOG%"
set CODIGO=%ERRORLEVEL%

call :linha "FIM %date% %time% - codigo de saida: %CODIGO%"
exit /b %CODIGO%

REM Sub-rotina: a mesma linha na tela e no log. %~1 tira as aspas; "" = linha em branco.
:linha
echo(%~1
>> "%LOG%" echo(%~1
exit /b 0
