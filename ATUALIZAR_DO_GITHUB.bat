@echo off
rem T-0003: leva os .py/.bat do main para esta pasta (ver atualizar_do_github.py).
rem Uso: ATUALIZAR_DO_GITHUB.bat [--simular] [--assunto T0003] [--origem C:\bapcentral]
rem T-0018 (ADR 0002): --diario (rotina das 06h30) | --primeira-vez --confirmar | --agendar | --remover-agendamento
py -3.12 "%~dp0atualizar_do_github.py" %*
set "BAP_CODIGO=%ERRORLEVEL%"
pause
exit /b %BAP_CODIGO%
