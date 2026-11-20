@echo off
REM ===========================================================================
REM  INSTALADOR DA AUTOMACAO BAP TOOLS
REM  Coloque este arquivo na MESMA PASTA que bap_automation.py,
REM  executar_bap.bat, tarefa_bap.xml e bap_janela.py, e de um duplo clique.
REM
REM  A PASTA ONDE ESTES ARQUIVOS ESTAO E A PASTA DE TRABALHO. Nao ha caminho
REM  fixo: pode ser C:\Automacoes\BAP_TOOLS, uma pasta do OneDrive, um pen
REM  drive - onde estiver o bap_automation.py, e ali que tudo acontece.
REM
REM  O que ele faz sozinho:
REM    1. confere os arquivos e cria as subpastas
REM    2. acha o Python (e instala pelo winget se nao existir)
REM    3. cria o ambiente virtual (na pasta local, fora do OneDrive)
REM    4. instala as bibliotecas e o navegador Chromium
REM    5. confere se acha a planilha e as 5 abas
REM    6. cria a tarefa agendada de 08h00 e 14h00
REM    7. cria o atalho "Automacao BAP" na Area de Trabalho
REM
REM  O que NAO da para automatizar (a Microsoft nao permite):
REM    - sincronizar a pasta compartilhada do OneDrive
REM    - a senha do Windows, que o proprio Windows vai pedir no passo 6
REM ===========================================================================
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title Instalacao - Automacao BAP Tools
color 0F

set "ORIGEM=%~dp0"
if "%ORIGEM:~-1%"=="\" set "ORIGEM=%ORIGEM:~0,-1%"
set "DESTINO=%ORIGEM%"
set "TAREFA=BAP Tools - Atualizar TABELA_BAP"
REM O ambiente virtual NAO pode ficar na pasta compartilhada: sao milhares de
REM arquivos que o OneDrive sincronizaria a toa, e ele guarda caminhos absolutos
REM que so valem nesta maquina. Por isso vai para a pasta local do usuario.
set "VENV=%LOCALAPPDATA%\BAP_TOOLS\.venv"
set "VPY=%VENV%\Scripts\python.exe"

echo.
echo ============================================================
echo   INSTALACAO DA AUTOMACAO BAP TOOLS
echo ============================================================
echo   Pasta de trabalho: %DESTINO%
echo.

REM ---------------------------------------------------------------- 1. arquivos
echo [1/7] Conferindo os arquivos...
if not exist "%DESTINO%\bap_automation.py" (
    echo.
    echo   ERRO: bap_automation.py nao esta nesta pasta.
    echo   Coloque os arquivos todos juntos e rode de novo.
    goto :falhou
)
if not exist "%DESTINO%\SISTEMA BAP\logs" mkdir "%DESTINO%\SISTEMA BAP\logs"
REM ---- o desenho da pasta: os Excel do dia a dia e as quatro gavetas
REM      de backup. Quem move os arquivos para ca sao os proprios
REM      programas, na primeira vez que abrirem.
if not exist "%DESTINO%\RELATORIOS" mkdir "%DESTINO%\RELATORIOS"
if not exist "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS" mkdir "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS"
if not exist "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_BAPTOOLS" mkdir "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_BAPTOOLS"
if not exist "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_PRECO" mkdir "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_PRECO"
if not exist "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_AUXILIARES" mkdir "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_AUXILIARES"
if not exist "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_PLANNER" mkdir "%DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS\BKP_RELATORIOS_PLANNER"
if not exist "%DESTINO%\SISTEMA BAP\auth" mkdir "%DESTINO%\SISTEMA BAP\auth"
if not exist "%DESTINO%\SISTEMA BAP\evidencias" mkdir "%DESTINO%\SISTEMA BAP\evidencias"
if not exist "%DESTINO%\abrir_bap.bat" (
    echo   AVISO: abrir_bap.bat nao esta na pasta. Use o atalho da Area de
    echo   Trabalho para abrir a janela, nunca o bap_janela.py direto.
)
echo       ok
echo.

REM ------------------------------------------------------------------ 2. python
echo [2/7] Procurando o Python...
set "PY="
python --version >nul 2>nul && set "PY=python"
if not defined PY ( py -3 --version >nul 2>nul && set "PY=py -3" )

if not defined PY (
    echo       Python nao encontrado. Tentando instalar pelo winget...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo.
        echo   O winget nao esta disponivel nesta maquina.
        echo   Instale o Python manualmente em https://www.python.org/downloads/
        echo   marcando a opcao "Add python.exe to PATH" e rode este arquivo de novo.
        goto :falhou
    )
    winget install -e --id Python.Python.3.12 --scope user --silent ^
        --accept-package-agreements --accept-source-agreements
    echo       Reabrindo o ambiente...
    python --version >nul 2>nul && set "PY=python"
    if not defined PY ( py -3 --version >nul 2>nul && set "PY=py -3" )
    if not defined PY (
        echo.
        echo   O Python foi instalado, mas ainda nao esta no PATH desta janela.
        echo   FECHE esta janela e rode instalar_bap.bat de novo.
        goto :falhou
    )
)
for /f "delims=" %%V in ('%PY% --version 2^>^&1') do echo       %%V
echo.

REM --------------------------------------------------------------- 3. ambiente
echo [3/7] Criando o ambiente virtual em %VENV%...
if not exist "%LOCALAPPDATA%\BAP_TOOLS" mkdir "%LOCALAPPDATA%\BAP_TOOLS"
if exist "%VPY%" (
    echo       ja existe, reaproveitando
) else (
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo   ERRO: nao consegui criar o ambiente virtual.
        goto :falhou
    )
    echo       ok
)
echo.

REM ------------------------------------------------------------ 4. bibliotecas
echo [4/7] Instalando bibliotecas ^(pode levar alguns minutos^)...
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
REM  pywin32 = conversar com o Excel para recalcular as formulas no fim.
"%VPY%" -m pip install --quiet --disable-pip-version-check ^
    playwright pandas openpyxl xlrd keyring requests pywin32
if errorlevel 1 (
    echo.
    echo   ERRO ao instalar as bibliotecas.
    echo   Costuma ser proxy ou firewall da empresa bloqueando o pypi.org.
    echo   Peca ao TI liberacao para pypi.org e files.pythonhosted.org.
    goto :falhou
)
echo       bibliotecas ok, baixando o navegador Chromium...
"%VPY%" -m playwright install chromium
if errorlevel 1 (
    echo.
    echo   ERRO ao baixar o Chromium.
    echo   Peca ao TI liberacao para playwright.azureedge.net
    echo   ^(ou cdn.playwright.dev^).
    goto :falhou
)
echo       ok
echo.

REM --------------------------------------------------------------- 5. checagem
echo [5/7] Conferindo o acesso a planilha...
echo.
"%VPY%" "%DESTINO%\bap_automation.py" --checar
if errorlevel 1 (
    echo.
    echo   A checagem falhou. O motivo mais comum: a pasta
    echo   "Regionais - Leandro" ainda nao esta sincronizada nesta maquina.
    echo.
    echo   Como resolver: abra a pasta compartilhada no OneDrive pelo
    echo   navegador e clique em "Adicionar atalho ao Meu OneDrive".
    echo   Espere sincronizar e rode este instalador de novo.
    goto :falhou
)
echo.
echo       ok
echo.

REM ---------------------------------------------------------------- 6. agenda
echo [6/7] Tarefa agendada das 08h00 e 14h00
echo.
if not exist "%DESTINO%\tarefa_bap.xml" (
    echo   AVISO: tarefa_bap.xml nao encontrado. Pulei o agendamento.
    goto :atalho
)

set "RESP="
set /p "RESP=      Criar a tarefa agendada agora? (S/N): "
if /I not "!RESP!"=="S" (
    echo       Pulado. Voce pode rodar este instalador de novo depois.
    goto :atalho
)

REM  .Replace() e substituicao LITERAL - ao contrario de -replace, nao trata
REM  o caminho como expressao regular (uma pasta com $ ou [ quebraria).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$t = Get-Content -Raw -Path '%DESTINO%\tarefa_bap.xml';" ^
  "$t = $t.Replace('__USUARIO__','%USERDOMAIN%\%USERNAME%');" ^
  "$t = $t.Replace('__PASTA__','%DESTINO%');" ^
  "Set-Content -Encoding Unicode -Path '%TEMP%\bap_task.xml' -Value $t"
if not exist "%TEMP%\bap_task.xml" (
    echo   ERRO: nao consegui preparar o arquivo da tarefa.
    goto :falhou
)

echo.
echo   O Windows vai pedir a SENHA de %USERDOMAIN%\%USERNAME%.
echo   E a senha desta conta, para a tarefa rodar com a tela bloqueada.
echo   Ela nao fica salva em nenhum arquivo.
echo.
schtasks /Create /TN "%TAREFA%" /XML "%TEMP%\bap_task.xml" /RU "%USERDOMAIN%\%USERNAME%" /RP * /F
set "CODIGO=%ERRORLEVEL%"
del "%TEMP%\bap_task.xml" >nul 2>nul

if not "%CODIGO%"=="0" (
    echo.
    echo   Nao consegui criar a tarefa automaticamente ^(codigo %CODIGO%^).
    echo   Crie na mao pelo Agendador de Tarefas, apontando para:
    echo      %DESTINO%\executar_bap.bat
    goto :atalho
)

echo.
echo       tarefa criada. Conferindo:
schtasks /Query /TN "%TAREFA%" /FO LIST | findstr /I "TaskName Next Status"

REM ------------------------------------------------ 7. atalho na area de trabalho
:atalho
echo.
echo [7/7] Atalho "Automacao BAP" na Area de Trabalho
if not exist "%DESTINO%\bap_janela.py" (
    echo       bap_janela.py nao encontrado; pulei o atalho.
    goto :fim
)

set "PYW=%VENV%\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Automacao BAP.lnk'));" ^
  "$s.TargetPath='%DESTINO%\abrir_bap.bat';" ^
  "$s.Arguments='';" ^
  "$s.WindowStyle=7;" ^
  "$s.WorkingDirectory='%DESTINO%';" ^
  "$s.IconLocation='shell32.dll,44';" ^
  "$s.Description='Acompanhar a automacao BAP';" ^
  "$s.Save(); Write-Host ('      criado em ' + $d)"

if errorlevel 1 (
    echo       Nao consegui criar o atalho. Crie na mao apontando para:
    echo          "%PYW%" "%DESTINO%\bap_janela.py"
)

:fim
echo.
echo ============================================================
echo   INSTALACAO CONCLUIDA
echo ============================================================
echo.
echo   Pasta ......... %DESTINO%
echo   Ambiente ...... %VENV%   ^(local, nao sincroniza^)
echo   Logs .......... %DESTINO%\SISTEMA BAP\logs
echo   Relatorios .... %DESTINO%\RELATORIOS
echo   Backups ....... %DESTINO%\SISTEMA BAP\BACKUP_RELATORIOS
echo.
echo   Para acompanhar pela janela: duplo clique em "Automacao BAP"
echo   na Area de Trabalho, ou no abrir_bap.bat desta pasta.
echo   NAO abra o bap_janela.py direto: o Windows usa o Python do
echo   sistema, que nao tem as bibliotecas.
echo.
echo   Teste agora, sem alterar a planilha de verdade:
echo      cd %DESTINO%
echo      "%VPY%" bap_automation.py --relatorio clientes --visivel --simular
echo.
echo   Para rodar a tarefa na hora: Agendador de Tarefas,
echo   botao direito em "%TAREFA%" ^> Executar.
echo.
pause
exit /b 0

:falhou
echo.
echo ============================================================
echo   INSTALACAO INTERROMPIDA
echo ============================================================
echo   Nada foi agendado. Corrija o ponto acima e rode de novo.
echo.
pause
exit /b 1
