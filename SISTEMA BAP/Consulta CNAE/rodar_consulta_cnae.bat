@echo off
cd /d "%~dp0"
echo Consultando CNAE dos clientes BAP pelo CNPJ...
python consulta_cnae_bap.py
echo.
pause
