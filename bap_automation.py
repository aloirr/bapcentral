#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
===============================================================================
 BAP TOOLS  ->  TABELA_BAP.xlsx        (automacao em script unico)
===============================================================================

 DOIS MODOS DE ACESSO A NUVEM (constante MODO_NUVEM, no bloco CONFIG):

   MODO_NUVEM = "graph"  (padrao, recomendado para a assistente)
       O script fala direto com o SharePoint/OneDrive pela API da Microsoft.
       NAO precisa de pasta sincronizada, NAO precisa do computador do
       Alexandre. Cada pessoa entra com a PROPRIA conta Microsoft; basta ter
       permissao de edicao na pasta "Regionais - Leandro".

   MODO_NUVEM = "local"
       Usa a pasta do OneDrive sincronizada na maquina (jeito antigo).

 ATENCAO - LIMITE QUE NENHUM CODIGO RESOLVE:
   O BAP Tools esta em http://172.19.20.76:8501 , um IP PRIVADO. So maquinas
   dentro da rede interna (ou na VPN) conseguem chegar la. A maquina que roda
   este script precisa desse acesso. A planilha, essa sim, vai e volta pela
   nuvem.

-------------------------------------------------------------------------------
 FLUXO
-------------------------------------------------------------------------------
   1. Trava: impede que voce e a assistente rodem ao mesmo tempo.
   2. Copia a TABELA_BAP.xlsx para uma pasta temporaria de trabalho.
   3. Guarda um backup datado em BACKUP_RELATORIOS\\BKP_RELATORIOS_AUXILIARES.
   4. Chromium invisivel -> BAP Tools -> login -> para cada relatorio:
      escolhe na lista, "Consultar", "Baixar excel".
   5. Arquiva cada relatorio em BACKUP_RELATORIOS\\BKP_RELATORIOS_BAPTOOLS
      com a data no nome (historico completo, nada e apagado).
   6. Grava cada relatorio na sua aba SUBSTITUINDO APENAS AS COLUNAS DE
      MESMO NOME. Colunas calculadas ficam intactas e suas formulas sao
      propagadas para as linhas novas.
   7. Monta a solicitacao de coleta e os CSVs de importacao.
   8. So entao devolve a TABELA_BAP.xlsx para o lugar dela (a ordem importa:
      devolver antes deixaria a solicitacao sem arquivo para ler).
   9. Libera a trava. Log detalhado, saida 0 (ok) / 1 (falha).

 ONDE FICAM OS ARQUIVOS
   A rotina usa A PASTA ONDE O bap_automation.py ESTA. Mova o script e tudo
   vai junto - nao ha caminho fixo no codigo.

   <pasta do script>\\
       bap_automation.py             <- o script
       RELATORIOS\\                  <- OS EXCEL DO DIA A DIA, os atuais
           TABELA_BAP.xlsx           <- a planilha de verdade
           SOLICITACAO_BAP.xlsx      <- as coletas, acumulativa
           ESTOQUE_BAP.xlsx
           BASE_CLIENTE.xlsx
           ALTERACOES_PRECO.xlsx
           PLANNER_BAP_<data>.xlsx   <- so o mais recente
       BACKUP_RELATORIOS\\           <- TUDO que e copia, em quatro gavetas
           BKP_RELATORIOS_BAPTOOLS\\    os relatorios baixados, com a data
           BKP_RELATORIOS_PRECO\\       historico_precos e copias do preco
           BKP_RELATORIOS_AUXILIARES\\  copias datadas da TABELA_BAP, do
                                        ESTOQUE_BAP e a base de produtos
           BKP_RELATORIOS_PLANNER\\     PLANNER e BASE_CLIENTE anteriores
       Arquivos para Importar\\      <- os CSVs de reversa e separacao
       logs\\ evidencias\\ cards\\ auth\\

   A pasta se arruma sozinha: em toda execucao os arquivos soltos vao para
   a gaveta certa. Nada e apagado nem sobrescrito - se ja houver um arquivo
   de mesmo nome no destino, o que estava solto ganha " (da raiz)" no nome.

   ATENCAO: a TABELA_BAP.xlsx passou a morar na subpasta RELATORIOS. Quem
   aponta para ela de fora - Power BI, atalho, formula de outra planilha -
   precisa apontar para ...\\RELATORIOS\\TABELA_BAP.xlsx.

   Os temporarios ficam FORA dessa pasta (na pasta temporaria do Windows),
   para nao sincronizar 15 MB a cada rodada quando a pasta esta no OneDrive.
   Para voltar a usar a pasta do OneDrive, mude LOCAL_DA_PLANILHA no CONFIG.

     Relatorio Clientes                  -> aba dClientesBap
     Relatorio Titulos em Aberto         -> aba ftTitulos
     Relatorio Estoque BAP Protheus      -> aba ftEstoqueBap
     Relatorio Movimentacao_Protheus_BAP -> aba ftPedidos
     Relatorio Tabela de Preco           -> aba ftTabelaPreco

-------------------------------------------------------------------------------
 INSTALACAO (uma vez, em cada maquina que for rodar)
-------------------------------------------------------------------------------
     python -m venv .venv
     .venv\\Scripts\\activate
     pip install playwright pandas openpyxl xlrd keyring msal requests
     playwright install chromium

-------------------------------------------------------------------------------
 PRIMEIRA CONFIGURACAO DA NUVEM (modo graph)
-------------------------------------------------------------------------------
  Precisa de um "ID de aplicativo" da Microsoft. Voce mesmo cria, em 5 minutos,
  sem abrir chamado - a menos que a empresa bloqueie registro de apps:

     1. entre em  https://entra.microsoft.com  com a conta corporativa
     2. Identidade > Aplicativos > Registros de aplicativo > Novo registro
     3. Nome: "Automacao BAP Tools"
        Contas: "Somente contas neste diretorio organizacional"
        NAO precisa preencher URI de redirecionamento
     4. Registrar
     5. Na tela do app, em "Autenticacao" > "Adicionar uma plataforma" >
        "Aplicativos moveis e da area de trabalho" > marque
        "https://login.microsoftonline.com/common/oauth2/nativeclient"
        e ative "Permitir fluxos de cliente publico" = Sim
     6. Em "Permissoes de API" > Adicionar > Microsoft Graph >
        Permissoes delegadas > marque  Files.ReadWrite.All  e  User.Read
     7. Copie "ID do aplicativo (cliente)" e "ID do diretorio (locatario)"
        para GRAPH_CLIENT_ID e GRAPH_TENANT_ID aqui embaixo.

  Depois, em cada maquina, rode uma vez:
        python bap_automation.py --configurar-nuvem
  Ele mostra um codigo, voce abre microsoft.com/devicelogin, entra com a
  conta e pronto. O token fica salvo e se renova sozinho nas execucoes
  seguintes (por isso vale rodar todo dia: o refresh se mantem vivo).

  IMPORTANTE: a assistente entra com a CONTA DELA. Voce precisa ter
  compartilhado a pasta "Regionais - Leandro" com ela, com permissao de EDICAO.

-------------------------------------------------------------------------------
 SE A MICROSOFT DISSER "Aprovacao necessaria"
-------------------------------------------------------------------------------
  Tela: "Este aplicativo exige aprovacao do seu administrador".
  Isso NAO e problema do script nem das permissoes escolhidas: significa que o
  locatario (grupopmz.com.br) desligou o consentimento por usuario. Repare que
  ate "View users' basic profile" aparece na lista - essa permissao nunca
  exigiria admin. Ou seja, NENHUMA combinacao de permissoes passa sem o TI.

  Dois caminhos:

  (A) Pedir a liberacao - escreva a justificativa e clique em
      "Solicitar aprovacao". O administrador aprova uma vez e vale para
      voce e para a assistente. Sugestao de texto:

        "Aplicativo interno de automacao que baixa relatorios do sistema
         BAP Tools e atualiza a planilha TABELA_BAP.xlsx no meu OneDrive
         corporativo, usada como fonte do Power BI. Cliente publico, sem
         segredo, permissao delegada: acessa somente arquivos que o usuario
         que fez login ja tem acesso. Uso: eu e minha assistente."

  (B) Nao depender do Entra ID - troque a linha abaixo para:
             MODO_NUVEM = "local"
      Ai o script usa a pasta do OneDrive sincronizada na maquina. Para a
      assistente: voce compartilha a pasta "Regionais - Leandro" com ela com
      permissao de EDICAO, ela abre no OneDrive web e usa "Adicionar atalho ao
      Meu OneDrive". A pasta passa a aparecer no Explorer dela e o script a
      encontra sozinho, mesmo estando na raiz do OneDrive dela.
      Funciona hoje, sem TI. So exige que o OneDrive esteja sincronizando.

-------------------------------------------------------------------------------
 MODOS DE USO
-------------------------------------------------------------------------------
     python bap_automation.py                    # execucao normal (invisivel)
     python bap_automation.py --configurar-nuvem # login Microsoft (1a vez)
     python bap_automation.py --checar           # confere nuvem, arquivo e abas
     python bap_automation.py --descobrir        # mapeia os seletores da tela
     python bap_automation.py --visivel          # mostra o navegador (testes)
     python bap_automation.py --simular          # NAO altera a planilha real
     python bap_automation.py --relatorio clientes,estoque
     python bap_automation.py --sem-baixar       # usa os relatorios ja enviados
     python bap_automation.py --destravar        # remove uma trava presa

 ORDEM NA PRIMEIRA VEZ:
     1) --configurar-nuvem   2) --checar   3) --descobrir
     4) --visivel            5) --simular  6) execucao normal + Agendador

===============================================================================
"""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
import logging
import os
import re
import shutil
import subprocess
import sys

# (29/10, Alexandre: "o minimo de pasta possivel") o cache do Python fica fora
# da pasta do BAP (no %LOCALAPPDATA%\BAP_TOOLS\cache de cada maquina): sem
# __pycache__ na pasta e sem sincronizar cache pelo OneDrive.
try:
    import os as _os_c
    sys.pycache_prefix = sys.pycache_prefix or _os_c.path.join(
        _os_c.environ.get("LOCALAPPDATA") or _os_c.path.join(
            _os_c.path.dirname(_os_c.path.abspath(__file__)), "SISTEMA BAP"),
        *(("BAP_TOOLS", "cache") if _os_c.environ.get("LOCALAPPDATA")
          else ("cache",)))
except Exception:                                       # noqa: BLE001
    pass
import tempfile
import time
import unicodedata
from bisect import bisect_left
from collections import Counter, defaultdict
from copy import copy
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.formula.translate import Translator
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# (05/11) a fotografia das abas de dados e as contas "como o Excel" (os
# _xl_* moraram aqui ate 05/11; agora sao do dados_bap, o mesmo calculo
# para o robo e para a rodada rapida)
import dados_bap
# (05/11) o aviso "Arquivo XXXX em aberto" (Continuar / Cancelar)
import aviso_arquivo
from dados_bap import (VAZIO_XL, _EPOCA_XL, _xl_chave, _xl_limpo,  # noqa: F401
                       _xl_numero, _xl_serial, _xl_texto, _xl_trim,
                       _xl_value, _xl_vazio)

try:
    import keyring
except ImportError:
    keyring = None


# =============================================================================
# ============================  BLOCO CONFIG  =================================
# =====  E AQUI QUE VOCE MEXE. O RESTO DO SCRIPT NAO PRECISA SER ALTERADO. ====
# =============================================================================

URL_BAP = "http://172.19.20.76:8501/"

# "graph" = fala direto com o SharePoint | "local" = usa pasta sincronizada
#
# ATENCAO: esta em "local" porque o locatario grupopmz.com.br exige aprovacao
# do administrador para qualquer aplicativo. Enquanto o TI nao aprovar o
# registro "Automacao BAP Tools", o modo "graph" fica travado na tela
# "Aprovacao necessaria" e nenhum token e emitido.
# Quando aprovarem, basta trocar esta linha de volta para "graph" - o
# GRAPH_CLIENT_ID e o GRAPH_TENANT_ID ja estao preenchidos aqui embaixo.
MODO_NUVEM = "local"

# ----------------------------- MODO GRAPH ------------------------------------
GRAPH_CLIENT_ID = "3d5e39c3-5230-4e2b-a7ae-cb2b71fad1c7"
GRAPH_TENANT_ID = "743d9744-08b4-4b52-b358-56ae77c79473"   # ou "organizations"

# As MESMAS URLs que voce abre no navegador. O script resolve sozinho qual
# drive e qual pasta sao, entao nao ha caminho de disco para adivinhar.
URL_PASTA_PLANILHA = (
    "https://pmz365-my.sharepoint.com/personal/"
    "alexandre_guerreiro_bapautoparts_com_br/Documents/"
    "1%20-%20PMZ/2025/IM%20PMZ/Regionais%20-%20Leandro"
)
# O DESENHO DA PASTA (o mesmo do pastas_bap.py, repetido aqui porque o
# bap_automation.py e um script UNICO e tem de rodar sozinho):
#     RELATORIOS\                     os Excel do dia a dia
#     BACKUP_RELATORIOS\
#         BKP_RELATORIOS_BAPTOOLS\    o que o BAP Tools baixa
#         BKP_RELATORIOS_PRECO\       historico_precos + copias do preco
#         BKP_RELATORIOS_AUXILIARES\  copias da TABELA_BAP e do ESTOQUE_BAP
#         BKP_RELATORIOS_PLANNER\     PLANNER e BASE_CLIENTE antigos
SUBPASTA_RELATORIOS = "RELATORIOS"
# (29/10) as pastas do programa ficam na SISTEMA BAP (o mesmo do pastas_bap)
SUBPASTA_SISTEMA = "SISTEMA BAP"
SUBPASTA_BACKUP = f"{SUBPASTA_SISTEMA}/BACKUP_RELATORIOS"
BKP_BAPTOOLS = f"{SUBPASTA_BACKUP}/BKP_RELATORIOS_BAPTOOLS"
BKP_PRECO = f"{SUBPASTA_BACKUP}/BKP_RELATORIOS_PRECO"
BKP_AUXILIARES = f"{SUBPASTA_BACKUP}/BKP_RELATORIOS_AUXILIARES"
BKP_PLANNER = f"{SUBPASTA_BACKUP}/BKP_RELATORIOS_PLANNER"

URL_PASTA_RELATORIOS = URL_PASTA_PLANILHA + "/" + SUBPASTA_RELATORIOS
URL_PASTA_DOWNLOADS = URL_PASTA_PLANILHA + "/" + BKP_BAPTOOLS

NOME_PLANILHA = "TABELA_BAP.xlsx"

# Guardar tambem uma copia datada da planilha na nuvem, antes de alterar.
BACKUP_NA_NUVEM = True
SUBPASTA_BACKUP_NUVEM = "BACKUPS_TABELA_BAP"

# ----------------------------- MODO LOCAL ------------------------------------
# ONDE FICA A TABELA_BAP.xlsx (e, junto com ela, SEPARACAO_BAP, backups,
# SOLICITACAO_BAP e os CSVs de importacao):
#
#   "mesma_pasta" -> a pasta onde o bap_automation.py esta.  <<< em uso hoje
#                    Se essa pasta ja for a do OneDrive, otimo: a planilha
#                    fica visivel para o time e para o Power BI, e a rotina
#                    nao precisa procurar nada. Na primeira vez, se a planilha
#                    ainda nao estiver la, o script traz a do OneDrive.
#
#   "onedrive"    -> procura a pasta "Regionais - Leandro" dentro do OneDrive,
#                    onde quer que o script esteja.
LOCAL_DA_PLANILHA = "mesma_pasta"
# "bap_tools" era o nome antigo desta mesma opcao.
if LOCAL_DA_PLANILHA == "mesma_pasta":
    LOCAL_DA_PLANILHA = "mesma_pasta"

CAMINHO_RELATIVO_PLANILHA = r"1 - PMZ\2025\IM PMZ\Regionais - Leandro"
SUBPASTA_DOWNLOADS = BKP_BAPTOOLS
# Nomes antigos da mesma pasta. Se ainda existirem, o conteudo e mudado de
# lugar na primeira execucao - nada e copiado nem apagado.
SUBPASTA_DOWNLOADS_ANTIGA = "SEPARACAO_BAP"
SUBPASTA_DOWNLOADS_ANTIGA2 = "BACKUP_RELATORIOS_ANTIGA"
PASTA_NUVEM_MANUAL: Path | None = None   # preencha se a deteccao falhar

# --------------------------- PASTA DE TRABALHO -------------------------------
# A rotina usa A PASTA ONDE ESTE ARQUIVO ESTA. Mova o bap_automation.py para
# outro lugar e tudo vai junto: TABELA_BAP, SOLICITACAO_BAP, BACKUP_RELATORIOS,
# backups, logs, evidencias e os CSVs de importacao.
#
# Para fixar um caminho, independente de onde o script estiver, preencha:
#   PASTA_TRABALHO_FIXA = Path(r"C:\Automacoes\BAP_TOOLS")
PASTA_TRABALHO_FIXA: Path | None = None

PASTA_LOCAL = (Path(PASTA_TRABALHO_FIXA) if PASTA_TRABALHO_FIXA
               else Path(__file__).resolve().parent)

# Os temporarios sao uma copia de 15 MB da planilha, criada e apagada a cada
# rodada. Com a pasta de trabalho dentro do OneDrive isso vira sincronizacao
# jogada fora - por isso o padrao e usar a pasta temporaria do Windows.
# Deixe False para manter os temporarios junto com o resto.
TEMPORARIOS_FORA_DA_PASTA = True

DIAS_MANTER_DOWNLOADS = 0     # 0 = guardar tudo
MANTER_BACKUPS = 30           # backups locais

# --------------------- SOLICITACAO DE COLETA (ALOCACAO) ----------------------
# Reproduz em Python a medida DAX Vol_BAP_Alocacao_Total: para cada cidade e
# produto, distribui a demanda em cascata FRW -> CDs -> Lojas e diz de qual
# filial coletar cada unidade. Sai um arquivo na SEPARACAO_BAP.
#
# O QUE CONTA COMO ESTOQUE (mudou em 13/09/2026)
#   Estoque, aqui, e o que esta LIVRE para sair - nao o saldo contabil. Das
#   lojas PMZ ja se descontava o separado; das filiais BAP nao se descontava
#   nada, e uma peca inteiramente reservada ou ja vendida entrava na conta
#   como se estivesse na prateleira. Era assim que uma coleta ia parar no
#   FRW de uma peca que o FRW nao tinha para entregar. Agora as duas pontas
#   seguem a mesma regra (veja ESTOQUE_BAP_DESCONTAR_EMPENHO).
#
#   A coluna ESTOQUE_NA_ORIGEM, na aba de detalhe, guarda o saldo livre que
#   a filial tinha na hora - e por ela que se confere depois. Para as linhas
#   gravadas antes da correcao, rode o corrigir_solicitacao.bat.
GERAR_SOLICITACAO = True

# Arquivo UNICO e acumulativo na SEPARACAO_BAP. Cada execucao acrescenta
# somente o que ainda nao esta la; nada e reescrito nem apagado.
# O arquivo de solicitacao fica SEMPRE na raiz da pasta de trabalho - nao
# dentro da pasta de backup dos relatorios.
ARQUIVO_SOLICITACAO = "SOLICITACAO_BAP.xlsx"
# Na simulacao ele ganha outro nome, para nunca escrever por cima do de verdade.
ARQUIVO_SOLICITACAO_SIMULACAO = "SIMULACAO_SOLICITACAO_BAP.xlsx"
STATUS_PADRAO = "ABRIR SOLICITAÇÃO"

# Linhas sem origem (nao ha estoque em lugar nenhum) nao entram em nenhuma aba
# de solicitacao, entao o STATUS delas na aba Coletas e escrito direto.
STATUS_SEM_ORIGEM = "SEM ESTOQUE"

# A chave que decide se uma coleta ja foi solicitada. O mesmo numero de pedido
# pode existir em cidades diferentes, por isso a cidade entra na chave.
# A FILIAL DE ORIGEM entra na chave porque o mesmo item de um mesmo pedido
# pode ser coletado em varias filiais (a cascata FRW -> CD -> lojas divide a
# quantidade). Sem ela, a primeira origem gravada bloquearia todas as outras.
#
# ATENCAO: esta chave e apenas uma REDE DE SEGURANCA contra linha identica.
# Ela NAO controla quantidade - quem faz isso e o saldo por pedido (abaixo).
CHAVE_SOLICITACAO = ["CIDADE", "NUM_PEDIDO", "ID_PRODUTO", "COLETAR_EM"]

# ---------------------------------------------------------------------------
# CONTROLE POR QUANTIDADE - a regra que impede pedir mais do que foi pedido.
#
#   saldo(cidade, pedido, item) = demanda VEA - o que ja foi solicitado antes
#
# Pedido de 400 com 400 ja solicitadas tem saldo zero e NAO entra na cascata,
# nao importa onde o estoque esteja hoje. Se o pedido crescer para 500, sai so
# a diferenca de 100.
CONTROLAR_POR_SALDO = True

# CONFERENCIA CONTRA A ABA. O saldo usado na alocacao passa pelo de-para de
# produto e por colunas que podem ser formula - e formula guarda o resultado
# da rodada ANTERIOR ate alguem abrir a planilha no Excel. Com isto ligado, o
# programa le o estoque uma segunda vez direto da aba, pelo CODIGO do produto
# como ele esta escrito la, e so aceita coletar onde as duas leituras
# concordam. Custa uma varredura a mais e evita mandar alguem buscar o que
# nao existe. O que for barrado aparece no log e no resumo da rodada.
CONFERIR_ESTOQUE_NA_FONTE = True

# O estoque ja prometido a um pedido ainda em aberto nao pode ser prometido de
# novo a outro pedido:
#
#   estoque_livre(filial, item) = estoque - o que ja foi solicitado ali
#
# Sem isto, 100 unidades prometidas ontem reaparecem livres hoje e sao
# oferecidas a um pedido novo - que na pratica nunca seria atendido.
RESERVAR_ESTOQUE_JA_SOLICITADO = True

# Situacao do pedido, lida do ftPedidos a cada rodada. Coluna propria: o
# SCRIPT nunca escreve no STATUS depois de criar a linha.
COLUNA_SITUACAO = "SITUACAO_PEDIDO"
SITUACAO_ABERTO = "EM ABERTO"        # ainda consta como VEA
SITUACAO_FATURADO = "FATURADO"       # virou VND   - vira MOTIVO
SITUACAO_EXCLUIDO = "EXCLUIDO"       # sumiu do ftPedidos - vira MOTIVO
SITUACAO_ENCERRADO = "ENCERRADO"     # nenhum pedido vivo nesta linha

# AS DUAS LISTAS QUE O TIME ESCOLHE NA PLANILHA.
#
# A coluna SITUACAO_PEDIDO e do SCRIPT: ele a reescreve a cada rodada e ela
# so tem dois estados - o pedido esta vivo ou nao esta. O POR QUE ele
# encerrou (faturou ou sumiu do ftPedidos) foi para a coluna MOTIVO, na aba
# de detalhe: assim a lista fica curta sem perder a informacao.
OPCOES_SITUACAO = [SITUACAO_ABERTO, SITUACAO_ENCERRADO]
COLUNA_MOTIVO = "MOTIVO"

# A coluna STATUS e do TIME. O script so escreve ABRIR SOLICITAÇÃO na linha
# que ele acabou de criar; daí em diante quem move e a assistente, e e por
# esta lista que ela move.
# ate onde a lista suspensa vale (o limite de linhas do Excel)
MAXIMO_LINHAS_EXCEL = 1048576

OPCOES_STATUS = [
    "ABRIR SOLICITAÇÃO",
    "REVERSA GERADA",
    "FATURADO PARA FRW",
    "RUPTURA",
    "CANCELADO",
]

# ---------------------------------------------------------------------------
# A SOLICITACAO_BAP tem duas naturezas de aba:
#
#   "DETALHADO_PEDIDO" -> o DETALHAMENTO. Uma linha por pedido/item/origem,
#                       NUM_PEDIDO e CLIENTE. E onde se ve de que pedido veio
#                       cada unidade.
#
#   "Solicitacao *"  -> o que vai virar SEP. O produto aparece UMA vez por
#                       filial de origem (so repete se a loja/CD mudar), com
#                       a quantidade somada e os pedidos juntos na coluna
#                       PEDIDOS. Sem NUM_PEDIDO e sem CLIENTE.
#
# O time preenche a SEP e o STATUS nas abas "Solicitacao *"; a aba
# "DETALHADO_PEDIDO" le esses valores por FORMULA, pela coluna CHAVE.
# ---------------------------------------------------------------------------

# Aba Coletas - o detalhamento, uma linha por pedido.
COLUNAS_SOLICITACAO = [
    "DATA", "HORA", "CIDADE", "COD_PRODUTO", "ID_PRODUTO", "NUM_PEDIDO",
    "DT_PEDIDO", "CLIENTE", "FILIAL_PEDIDO", "COLETAR_EM", "TIPO_ORIGEM",
    "QUANTIDADE", "DEMANDA_PEDIDO",
    # auditoria do saldo, gravadas na criacao da linha:
    "JA_SOLICITADO", "SALDO_A_SOLICITAR", "ESTOQUE_NA_ORIGEM",
    # relidas do ftPedidos a cada rodada (colunas do script, nao do time):
    "SITUACAO_PEDIDO", "MOTIVO",
    # preenchidas por FORMULA, a partir das abas de solicitacao:
    "CONTROLE_SEP_LOJA", "ID_REVERSA",
    "CONTROLE_SEP_CD", "ID_SEPARACAO",
    "STATUS",
]

# Colunas da aba Coletas que sao formula (o script nao escreve valor nelas).
COLUNAS_POR_FORMULA = ["CONTROLE_SEP_LOJA", "ID_REVERSA",
                       "CONTROLE_SEP_CD", "ID_SEPARACAO", "STATUS"]

# Abas de solicitacao: colunas comuns + os controles de cada tipo.
COLUNAS_RESUMO_BASE = [
    "DATA", "HORA", "UF", "CIDADE", "COD_PRODUTO", "ID_PRODUTO",
    "COLETAR_EM", "FILIAL_DESTINO", "QUANTIDADE", "PEDIDOS", "SITUACAO_PEDIDO",
]
CONTROLES_POR_ABA = {
    "Solicitacao FRW":   [],
    "Solicitacao CD":    ["CONTROLE_SEP_CD", "ID_SEPARACAO"],
    "Solicitacao Lojas": ["CONTROLE_SEP_LOJA", "ID_REVERSA"],
}
# Toda aba de solicitacao termina com STATUS e CHAVE (CHAVE liga a Coletas).
COLUNA_CHAVE = "CHAVE"

# O que agrupa uma linha de solicitacao: mudou a filial de origem, e outra
# linha. DATA e HORA entram porque cada rodada gera a sua propria SEP.
CHAVE_RESUMO = ["DATA", "HORA", "UF", "CIDADE", "COD_PRODUTO", "ID_PRODUTO",
                "COLETAR_EM", "FILIAL_DESTINO"]

# Como os numeros de pedido aparecem juntos na coluna PEDIDOS.
SEPARADOR_PEDIDOS = "|"

# Colunas que o SCRIPT nunca preenche - sao do time. Nascem vazias e o que
# for escrito nelas jamais e sobrescrito.
COLUNAS_DO_TIME = ["ID_REVERSA", "ID_SEPARACAO", "STATUS"]

# Nomes antigos -> novos. Se a planilha ja existir com o nome velho, o titulo
# e renomeado no lugar, preservando tudo o que ja estava na coluna.
RENOMEAR_COLUNAS = {
    "SEPARACAO_LOJA": "CONTROLE_SEP_LOJA",
    "SEPARACAO_CD": "CONTROLE_SEP_CD",
}

# Abas com nome antigo -> nome novo. Renomeadas no lugar, sem perder dados.
RENOMEAR_ABAS = {
    "Coletas": "DETALHADO_PEDIDO",
}

# ----------------------------- FORMATACAO ------------------------------------
FONTE_PLANILHA = "Calibri"
TAMANHO_FONTE = 9
COR_CABECALHO = "1E4620"       # verde escuro
COR_FONTE_CABECALHO = "FFFFFF"

# UF de cada cidade da regional.
UF_POR_CIDADE = {
    "SAO LUIS":   "MA",
    "BELEM":      "PA",
    "SANTAREM":   "PA",
    "MANAUS":     "AM",
    "MATOGROSSO": "MT",
    "BOA VISTA":  "RR",
    "MACAPA":     "AP",
}

# ---------------------- ARQUIVOS CSV PARA IMPORTAR ---------------------------
# Depois de atualizar a SOLICITACAO_BAP, o script gera um CSV por cidade
# (reversa de loja) e um por CD (separacao), e devolve o numero de cada um
# para as colunas SEPARACAO_LOJA / SEPARACAO_CD da planilha.
GERAR_CSV_IMPORTACAO = True
SUBPASTA_IMPORTAR = f"{SUBPASTA_SISTEMA}/Arquivos para Importar"

# Nome: data primeiro, para a pasta se organizar sozinha por ordem cronologica.
#   240826_001_BELEM_BAPReversaLoja.csv
#   240826_001_BELEM_BAPSeparacaoCD.csv
SUFIXO_REVERSA = "BAPReversaLoja"
SUFIXO_SEPARACAO = "BAPSeparacaoCD"
# (T-0021) CSVs que vao para a web (aba Solicitacao BAP): ultimos 30 dias
CSV_WEB_DIAS = 30
CSV_WEB_MAX_ARQUIVOS = 60
CSV_WEB_MAX_BYTES = 200_000
CSV_WEB_MAX_TOTAL = 1_500_000

EMPRESA_PADRAO = "1"
CSV_SEPARADOR = ";"
CSV_CABECALHO = ["FILIAL ORIGEM", "EMPRESA PADRAO", "FORNECEDOR", "PRODUTO",
                 "FILIAL DESTINO", "QUANTIDADE UNIDADES"]

# A aba que guarda o detalhamento, uma linha por pedido.
ABA_DETALHE = "DETALHADO_PEDIDO"

# Aba -> quais TIPO_ORIGEM ela recebe. None = recebe tudo.
ABAS_SOLICITACAO = {
    "DETALHADO_PEDIDO":  None,
    "Solicitacao FRW":   ("FRW",),
    "Solicitacao CD":    ("CD",),
    "Solicitacao Lojas": ("LOJA PREFERENCIAL", "LOJA", "LOJA DO VENDEDOR"),
}

# Demanda: quais TIPOs de ftPedidos contam como pedido a atender.
TIPOS_DEMANDA = ["VEA"]
# TIPOs que significam "o pedido saiu, nao atenda mais". O que nao estiver nem
# aqui nem em TIPOS_DEMANDA some do calculo do mesmo jeito.
TIPOS_FATURADO = ["VND"]

# Data do pedido - define a ordem de atendimento (mais antigo primeiro).
# O primeiro nome que existir na aba ftPedidos e usado.
COLS_PEDIDO_DATA = ["DT_PEDIDO", "DATA_PEDIDO", "D2_EMISSAO", "DT_EMISSAO"]

# Cascata de prioridade. FRW = filiais cujo COD_FILIAL comeca com o prefixo.
PREFIXO_FRW = "40101"
CDS = ["26", "91", "28", "29", "27", "25", "62", "64"]

# ---------------------------------------------------------------------------
# PRIORIDADE POR VENDEDOR
#
# Alguns vendedores atendem uma praca que tem loja propria, mesmo que a loja
# esteja bloqueada em FiliaisExcluir para o fluxo normal. Para os pedidos
# desses vendedores a filial indicada aqui e olhada ANTES de tudo - antes do
# FRW, do CD e das lojas - e o bloqueio de FiliaisExcluir e ignorado SO para
# ela e SO nesses pedidos.
#
# O que a loja nao tiver segue a cascata normal da cidade do pedido.
# A chave e o codigo do vendedor na coluna C5_VEND1 do ftPedidos.
VENDEDORES_PRIORIDADE_FILIAL = {
    "000029": "63",      # CRISANTO -> loja 63 (Parauapebas)
}
# So para o log ficar legivel.
NOME_DO_VENDEDOR = {
    "000029": "CRISANTO",
}
# Colunas possiveis do vendedor no ftPedidos (a primeira que existir e usada).
COLS_PEDIDO_VENDEDOR = ["C5_VEND1", "A1_VEND", "VENDEDOR"]
# Como essas linhas aparecem em TIPO_ORIGEM. Precisa estar em ABAS_SOLICITACAO.
ORIGEM_VENDEDOR = "LOJA DO VENDEDOR"

# Reversa de loja: quando a demanda chega no nivel das lojas, esta loja e
# consultada PRIMEIRO na cidade. So se ela nao tiver o produto e que as demais
# entram, na ordem normal (maior estoque primeiro).
# A chave e a CIDADE da aba Filiais; acento e caixa nao importam.
LOJA_PREFERENCIAL_POR_CIDADE = {
    "BELÉM":      "67",
    "MATOGROSSO": "1",     # loja 01
    "BOA VISTA":  "16",    # Roraima
    "SÃO LUIS":   "97",    # Maranhao
    "MANAUS":     "18",
    "SANTARÉM":   "55",
    "MACAPÁ":     "40",
}

# Aba com o estoque das lojas PMZ, extraida da consulta
# "Estoques PMZ WEB-LEGADO". Sem ela, so o estoque BAP e considerado.
ABA_ESTOQUE_PMZ = "ftEstoquePMZ"
# Nomes possiveis das colunas nessa aba (o primeiro que existir e usado):
COLS_PMZ_FILIAL   = ["FILIAL", "COD_FILIAL", "B2_FILIAL", "CD_FILIAL"]
COLS_PMZ_PRODUTO  = ["ID_PRODUTO", "COD_PRODUTO", "B2_COD", "PRODUTO", "CODIGO"]
COLS_PMZ_QTDE     = ["QTD_TOTAL", "QTDE", "QTD", "B2_QATU", "SALDO", "ESTOQUE"]

# A medida DAX usa ftEstoquePMZ[QTDE] com o comentario "(*) disponivel".
# Se o estoque disponivel for o total MENOS o que ja esta separado/reservado,
# deixe True e informe a coluna. Se QTD_TOTAL ja for o disponivel, use False.
ESTOQUE_PMZ_DESCONTAR_SEPARADA = True
COLS_PMZ_SEPARADA = ["QTD_SEPARADA", "QTD_RESERVADA", "B2_RESERVA"]
# o CUSTO do produto, na ftEstoquePMZ. Ele varia de loja para loja, e o
# que vale para a BAP e o do CD da filial (a coluna CD_FILIAL da aba
# Filiais diz qual loja e o CD de cada filial BAP).
COLS_PMZ_CUSTO    = ["PPEDIDO", "CUSTO", "PRECO_PEDIDO", "CUSTO_MEDIO"]

# O ESTOQUE DAS FILIAIS BAP (aba ftEstoqueBap) tem o mesmo problema: o
# B2_QATU e o saldo CONTABIL, nao o que esta livre para coletar. O que ja
# esta reservado (B2_RESERVA) ou amarrado a um pedido de venda
# (B2_QPEDVEN) nao pode ser prometido de novo - senao o programa manda
# buscar no FRW uma peca que o FRW nao tem para entregar.
ESTOQUE_BAP_DESCONTAR_EMPENHO = True
COLS_BAP_RESERVA  = ["B2_RESERVA"]
COLS_BAP_PEDIDO   = ["B2_QPEDVEN"]
# O B2_QPEDVEN inclui o pedido que estamos alocando agora. Descontar ele
# inteiro tiraria a mesma peca da conta duas vezes - por isso a demanda
# VEA em aberto daquela filial e devolvida antes do desconto. Deixe False
# para descontar o empenho cheio (mais conservador, e manda buscar longe
# o que ja esta separado ali).
DEVOLVER_EMPENHO_DA_PROPRIA_DEMANDA = True

# --------------------- COMPARACAO DA TABELA DE PRECO -------------------------
# A cada rodada o script guarda uma foto da aba de precos e compara com a foto
# anterior. O que mudou vai para um Excel acumulativo, com o valor antigo, o
# novo, a diferenca e o percentual - por filial e produto.
COMPARAR_TABELA_PRECO = True
ABA_TABELA_PRECO = "ftTabelaPreco"
ARQUIVO_PRECOS = "ALTERACOES_PRECO.xlsx"
ABA_ALTERACOES_PRECO = "ALTERACOES"
# Onde ficam as fotos diarias (dentro da pasta de trabalho).
SUBPASTA_FOTOS_PRECO = f"{BKP_PRECO}/historico_precos"
DIAS_MANTER_FOTOS_PRECO = 180
# Nomes possiveis das colunas na aba de precos (o primeiro que existir e usado).
COLS_PRECO_FILIAL = ["DA1_FILIAL", "FILIAL", "COD_FILIAL"]
COLS_PRECO_TABELA = ["DA1_CODTAB", "CODTAB", "TABELA"]
COLS_PRECO_PRODUTO = ["DA1_CODPRO", "CODPRO", "COD_PRODUTO", "PRODUTO"]
COLS_PRECO_DESCRICAO = ["B1_DESC", "DESCRICAO", "DESC"]
COLS_PRECO_VALOR = ["DA1_PRCVEN", "PRCVEN", "PRECO", "PRECO_VENDA"]
# Variacao menor que isto e ruido de arredondamento e nao vira linha.
VARIACAO_MINIMA_PRECO = 0.005
COLUNAS_ALTERACAO_PRECO = [
    "DATA", "HORA", "FILIAL", "TABELA", "COD_PRODUTO", "DESCRICAO",
    "PRECO_ANTERIOR", "PRECO_ATUAL", "DIFERENCA", "PERCENTUAL", "TIPO",
    "ESTOQUE_FILIAL", "ESTOQUE_TOTAL_BAP", "DATA_ANTERIOR",
]
ABA_CONTROLE_PRECO = "CONTROLE"
COLUNAS_CONTROLE_PRECO = ["DATA", "HORA", "PRECOS_LIDOS", "COMPARADO_COM",
                          "ALTERACOES", "OBSERVACAO"]

# Estoque das lojas PMZ somado por FILIAL BAP (Filiais.COD_FILIAL ->
# Filiais.FILIAL_BAP). Entra em cada linha de alteracao e numa aba propria.
ABA_ESTOQUE_FILIAL_PRECO = "ESTOQUE_POR_FILIAL"
ABA_RESUMO_TRADE = "RESUMO_TRADE"
COLUNAS_RESUMO_TRADE = ["DATA", "HORA", "FILIAL_BAP", "CIDADE", "ITENS_ALTERADOS",
                        "PRODUTOS", "AUMENTOS", "REDUCOES", "VARIACAO_MEDIA",
                        "MAIOR_ALTA", "MAIOR_BAIXA", "ESTOQUE_IMPACTADO"]

# Card em PNG para o time de trade divulgar nos grupos. Usa o Chromium que o
# Playwright ja instala para baixar os relatorios - nao precisa de mais nada.
GERAR_CARD_PRECOS = True
SUBPASTA_CARDS = f"{SUBPASTA_SISTEMA}/cards"
DIAS_MANTER_CARDS = 180
ITENS_POR_BLOCO_CARD = 30   # quantos itens em cada bloco do card
TIPO_AUMENTO = "AUMENTO"
TIPO_REDUCAO = "REDUCAO"
TIPO_NOVO = "PRECO NOVO"
TIPO_REMOVIDO = "SAIU DA TABELA"

# --------------------- ESTOQUE x PRECO POR FILIAL ----------------------------
# No fim de cada rodada, um arquivo com uma linha por FILIAL BAP e produto:
# estoque disponivel das lojas PMZ e os dois precos daquela filial.
#
# Cada filial tem duas tabelas de preco, com o mesmo prefixo e final 1 ou 2:
#   40101002 (MANAUS) -> AM1 = capital, AM2 = interior
#   40101005 (BELEM)  -> PA1 = capital, PA2 = interior
# O script descobre isso sozinho, pelo final do codigo da tabela.
GERAR_ESTOQUE_BAP = True
ARQUIVO_ESTOQUE_BAP = "ESTOQUE_BAP.xlsx"

# ---------------------------------------------------------------------------
# A BASE_CLIENTE.xlsx VOLTOU a ser gerada aqui, no fim de cada rodada.
#
# Ela ja tinha saido daqui uma vez, por custar ~30 s e abrir a TABELA_BAP de
# 16 MB uma segunda vez; quem passou a gerar foi o proprio bap_planner.py,
# ao abrir. So que ai ela so ficava em dia quando alguem abria o Planner -
# quem olha o Power BI ou o Oportunidades via uma base velha sem saber.
# Agora sai junto com o resto, e o Planner continua fazendo o dele quando
# precisa (os dois usam a MESMA funcao, entao o arquivo e identico).
#
# ATENCAO AOS CORTES DA CURVA: eles NAO sao os padroes do base_cliente.py,
# sao os que estao no planner_config.json (aba PARAMETROS do Planner).
# Gerar com os padroes trocaria a curva de milhares de clientes e mudaria
# a rota inteira sem ninguem pedir - por isso parametros_do_planner().
GERAR_BASE_CLIENTE = True
# CNAE: antes de montar a BASE_CLIENTE, consulta na Receita (pelo CNPJ) so os
# clientes que ainda nao tem CNAE no cache da pasta "Consulta CNAE". Com
# limite de tempo por rodada (cnae_bap.LIMITE_SEGUNDOS): o que nao couber
# fica para a proxima, e sem internet a rodada segue normal.
CONSULTAR_CNAE = True
ARQUIVO_BASE_CLIENTE = "BASE_CLIENTE.xlsx"

# ------------------- ACOMPANHAMENTO DE POS-VENDA ------------------------------
# Entrega, devolucao e garantia, num arquivo que as assistentes editam juntas
# (RELATORIOS\ACOMPANHAMENTO_POS_VENDA.xlsx). Mesma regra da SOLICITACAO_BAP:
# o script ABRE a linha da nota nova e nunca mais mexe nela. Quem monta e o
# pos_venda.py, o mesmo modulo que o Gerador de Meta le.
GERAR_POS_VENDA = True
ARQUIVO_POS_VENDA = "ACOMPANHAMENTO_POS_VENDA.xlsx"
# notas a partir deste dia entram no acompanhamento (AAAA-MM-DD)
INICIO_POS_VENDA = "2026-10-01"

# OS DADOS DOS RELATORIOS (BAP Central / BAP Analista). No fim de cada rodada
# o bap_dados.py deixa prontos, em RELATORIOS\_CACHE_RELATORIOS, os dados
# que os relatorios dos assistentes leem - assim ninguem espera a TABELA_BAP
# ser lida quando abre um relatorio. Nao grava em planilha nenhuma.
GERAR_DADOS_RELATORIOS = True
ARQ_CONFIG_PLANNER = "planner_config.json"
ABA_ESTOQUE_BAP = "ESTOQUE_BAP"
FINAL_TABELA_CAPITAL = "1"
FINAL_TABELA_INTERIOR = "2"
# False = lista todo produto que tem preco na filial, mesmo com estoque zero.
ESTOQUE_BAP_SOMENTE_COM_ESTOQUE = False
COLUNAS_ESTOQUE_BAP = [
    "DATA", "HORA", "CIDADE", "FILIAL_BAP", "ID_PRODUTO", "COD_FORNECEDOR",
    "FORNECEDOR", "COD_PRODUTO", "DESCRICAO_PRODUTO", "ESTOQUE",
    "FILIAL_CD", "PPEDIDO", "ORIGEM_CUSTO",
    "TABELA_CAPITAL", "PRECO_CAPITAL", "TABELA_INTERIOR", "PRECO_INTERIOR",
    "MARKUP_CAPITAL", "MARKUP_INTERIOR",
    # 06/10: a CATEGORIA no FIM, para nao mexer na posicao das colunas que
    # ja existiam (Power BI).
    # 15/10: a CLASSIFICACAO DO CATALOGO BAP 2026 (BASE_BAP_UNIFICADA v8):
    # CATEGORIA (PEÇAS, BATERIAS, LUBRIFICANTES, QUÍMICOS, PNEUS,
    # ACESSÓRIOS), SISTEMA, FAMILIA e LINHA - e a referencia de todos os
    # relatorios (catalogo_bap.py). A classificacao para na LINHA: o
    # produto e o proprio COD_PRODUTO/DESCRICAO_PRODUTO da linha.
    "CATEGORIA", "SISTEMA", "FAMILIA", "LINHA",
    # 19/10 (Alexandre, via Analista): o custo da BATERIA e o P. PEDIDO +
    # a SUCATA (tabela do Oportunidades, pela amperagem). MARKUP_CAPITAL e
    # MARKUP_INTERIOR sao sobre o CUSTO_TOTAL; o PPEDIDO fica como veio
    # (o Oportunidades soma a sucata por conta dele). No fim, para nao
    # mexer na posicao das colunas do Power BI.
    "SUCATA", "CUSTO_TOTAL",
]

# ------------------------- AVISO AO POWER AUTOMATE ---------------------------
# Opcional. Se voce criar um fluxo de nuvem com o gatilho "Quando uma
# solicitacao HTTP e recebida", cole a URL gerada aqui. Ao terminar, o script
# envia um resumo em JSON e o fluxo pode, por exemplo, atualizar o dataset do
# Power BI e avisar no Teams. A URL ja carrega a assinatura de seguranca:
# trate-a como senha e nao publique em lugar nenhum.
URL_WEBHOOK_FINAL = ""

# ------------------------- RECALCULO DAS FORMULAS ----------------------------
# O openpyxl grava as formulas, mas JOGA FORA o valor calculado de cada uma.
# Enquanto ninguem abre a planilha no Excel, toda celula de formula fica sem
# valor - e quem le o arquivo sem ser pelo Excel (Power BI, Power Query,
# Python) enxerga vazio. Por isso a rotina abre o Excel invisivel no fim,
# manda recalcular tudo e salva.
#
# Precisa de: Excel instalado na maquina + biblioteca pywin32.
# Sem um dos dois, a rotina apenas avisa e segue - a planilha continua certa,
# so vai recalcular quando alguem abrir.
RECALCULAR_FORMULAS = True
# (05/11) 600 -> 120 s: um Excel preso (arquivo aberto, janela escondida)
# segurava a rodada 10 minutos. Passou disto, o robo encerra SO o Excel que
# ele mesmo abriu (pelo numero do processo) e segue.
TIMEOUT_RECALCULO = 120        # segundos por arquivo

# ------------------------ ARQUIVO ABERTO: O AVISO (05/11) --------------------
# (05/11, Alexandre) Antes de gravar por cima de uma planilha (TABELA_BAP,
# SOLICITACAO_BAP, ESTOQUE_BAP, BASE_CLIENTE, ALTERACOES_PRECO,
# ACOMPANHAMENTO_POS_VENDA) e antes de recalcular no Excel, o robo confere se
# ela esta aberta. Aberta: aparece o aviso "Arquivo XXXX em aberto. Feche e
# clique em Continuar." - Continuar confere de novo (o aviso volta enquanto
# ela estiver aberta), Cancelar interrompe a rodada.
# Sem resposta neste tempo (segundos) o aviso fecha sozinho e o robo PULA so
# aquele passo (a SOLICITACAO e o pos-venda ficam em NAO_GRAVADO_..., como
# sempre) - a rodada agendada sem ninguem na maquina nao fica parada.
# 0 = espera para sempre. Sem tela (tarefa sem ninguem logado, tela
# bloqueada) o passo e pulado na hora e fica no log.
ESPERA_POPUP_ARQUIVO = 15 * 60

# --------------------- TABELA_BAP SO COMO SAIDA (05/11) ----------------------
# (05/11, Alexandre: "coloque o python para calcular as formulas. TABELA_BAP
# fica uma saida") Abrir, gravar, salvar e recalcular a TABELA_BAP custava
# uns 4 minutos por rodada. Com isto ligado:
#   * RODADA COMPLETA - a 1a do dia, a que nao acha fotografia valida, a que
#     acha a TABELA_BAP salva por outra pessoa/programa depois da ultima
#     rodada, ou a pedida com --completa: igual a de sempre (abre, grava,
#     salva, o Excel recalcula) e, no fim, tira a FOTOGRAFIA das 7 abas de
#     dados em RELATORIOS\DADOS (.csv.gz + _estado.json);
#   * RODADA RAPIDA - as outras: NAO abre a TABELA_BAP. Monta as 7 abas em
#     memoria a partir da fotografia, grava os relatorios novos com as
#     mesmas rotinas, calcula as formulas em Python (dados_bap) e grava a
#     fotografia nova. Solicitacao, precos, ESTOQUE_BAP, BASE_CLIENTE,
#     pos-venda e os farois leem a fotografia (o xlsx_rapido ja entrega a
#     TABELA_BAP com as abas de dados dela). Qualquer falha da rapida vira
#     rodada completa na hora - a rodada nunca fica sem dado.
# A TABELA_BAP.xlsx continua sendo atualizada pela rodada completa (a saida
# do dia, para quem abre no Excel). Desligado (False): toda rodada e
# completa, como antes, e a fotografia sai de circulacao.
TABELA_BAP_SO_SAIDA = True
# a 1a rodada de cada dia e completa (False: so quando nao ha fotografia)
COMPLETA_NA_PRIMEIRA_DO_DIA = True
# copias da fotografia anterior guardadas antes de cada rodada rapida
MANTER_BACKUPS_DADOS = 20

# ---------------------- SCRIPT PARA RODAR NO FINAL ---------------------------
# Roda DEPOIS que a planilha e a solicitacao ja foram gravadas - tipicamente
# para mandar o Power BI atualizar o modelo semantico. Aceita .py, .ps1, .bat
# ou .exe; o script recebe o caminho do ultimo_resumo.json como argumento.
# Exemplo:
#   SCRIPT_FINAL = "atualizar_powerbi.ps1"      (relativo a pasta de trabalho)
#   SCRIPT_FINAL = r"D:\scripts\meu_script.py"  (caminho completo)
SCRIPT_FINAL = ""
# Segundos de paciencia com ele. Passou disso, a automacao segue a vida.
TIMEOUT_SCRIPT_FINAL = 900
# Rodar mesmo quando algum relatorio falhou? Por padrao nao: nao faz sentido
# atualizar o Power BI com a planilha incompleta.
SCRIPT_FINAL_SO_SE_TUDO_OK = True

# -------------------- SINCRONIZACAO DO BAP AJUDA 2.0 (27/10) -----------------
# (27/10, Alexandre - recado do BAP Ajuda 20261027-0649) No fim de cada rodada,
# depois de gravar ESTOQUE_BAP e BASE_CLIENTE, roda o
# "BAP Ajuda 2.0\sincronizar_bap.py": manda estoque, carteira e base para o
# app (GitHub -> Render) e BAIXA AS RESPOSTAS DO APP (Pesquisa, Indicacao,
# Prospeccao e fotos) para RELATORIOS\BAP_AJUDA_RESPOSTAS. Sem janela, sem
# travar o robo: falha aqui nunca derruba a rodada (fica no log e no
# ultimo_resumo.json). Se o envio falhar (ex.: token sem escrita, 403), as
# respostas sao baixadas assim mesmo (so a etapa_respostas do script).
SINCRONIZAR_BAP_AJUDA = True
PASTA_BAP_AJUDA = "BAP Ajuda 2.0"          # ao lado do bap_automation.py
TIMEOUT_BAP_AJUDA = 900                    # segundos (git + deploy)
GIT_PADRAO_WINDOWS = r"C:\Program Files\Git\cmd"
# outra maquina sincronizando agora (trava de no maximo 15 min)
TRAVA_BAP_AJUDA = ".sincronizando_robo"
TRAVA_BAP_AJUDA_MINUTOS = 15

TIMEOUT_PAGINA = 60_000
TIMEOUT_DOWNLOAD = 300_000

# ------------------------------- CREDENCIAIS BAP -----------------------------
USUARIO_BAP = os.environ.get("BAP_USUARIO", "bap")
# (10/11, migracao GitHub) a senha NAO fica no codigo: cofre do Windows
# (--salvar-senha) ou a variavel de ambiente BAP_SENHA
SENHA_PADRAO = os.environ.get("BAP_SENHA", "")
SERVICO_KEYRING = "BAP_TOOLS"

# --------------------------------- SELETORES ---------------------------------
# Rode "--descobrir" para o script imprimir os seletores reais da tela.
#   texto puro / "css=..." / "xpath=..." / "texto=..." / "" (automatico)
# Valores CONFIRMADOS pelo --descobrir em 24/08/2026 na tela real do BAP Tools.
SELETORES = {
    "campo_usuario": "Usuario",              # sem acento, como esta na tela
    "campo_senha": "Senha",
    "botao_entrar": "Entrar",
    "confirmacao_login": "css=[data-testid='stSidebar']",   # so aparece logado
    "lista_relatorios": "css=[data-testid='stSelectbox']",  # "Selecione a consulta"
    "botao_gerar": "Executar Consulta",      # na tela: "▶ Executar Consulta"
    "botao_download": "Baixar Excel",        # na tela: "📥 Baixar Excel"
    # Texto que confirma que a consulta terminou (aparece na faixa verde):
    "consulta_ok": "executada com sucesso",
    "erro_login": "css=[data-testid='stAlert']",
}

RECARREGAR_ENTRE_RELATORIOS = False

# --------------------------------- RELATORIOS --------------------------------
# nome_site: texto EXATO da lista "Selecione a consulta", conferido na tela
# em 24/08/2026. A comparacao ignora acento e caixa, mas mantenha fiel.
RELATORIOS = [
    {
        "id": "clientes",
        "nome_site": "Clientes",
        "aba_excel": "dClientesBap",
        "arquivo": "Relatorio_Clientes",
        "linha_cabecalho": 1,
        "filtros": {},
        "colunas_ignorar": [],
        "linhas_a_mais": "limpar",
        # OUT/2026: o relatorio ganhou a coluna STATUS (ATIVO/INATIVO) e
        # perdeu A1_FILIAL e A1_MSBLQL. Coluna nova do relatorio vira coluna
        # nova no fim da aba (so as desta lista - as outras sem par seguem
        # ignoradas, como sempre), e as duas que sumiram sao refeitas a
        # partir do que veio - senao ficavam com o valor VELHO de cada
        # linha, que nao e mais do mesmo cliente.
        "criar_colunas": ["STATUS"],
        "derivar": "clientes",
    },
    {
        "id": "titulos",
        "nome_site": "Titulos em Abertos Protheus",
        "aba_excel": "ftTitulos",
        "arquivo": "Relatorio_Titulos_em_Abertos",
        "linha_cabecalho": 1,
        "filtros": {},
        "colunas_ignorar": [],
        "linhas_a_mais": "limpar",
    },
    {
        "id": "estoque",
        "nome_site": "Estoque BAP Protheus",
        "aba_excel": "ftEstoqueBap",
        "arquivo": "Relatorio_Estoque_BAP_Protheus",
        "linha_cabecalho": 1,
        "filtros": {},
        "colunas_ignorar": [],
        "linhas_a_mais": "limpar",
        # Na aba, a coluna A "B2_FILIAL" e uma FORMULA (=CONCAT(4;D)) e o dado
        # bruto do relatorio mora em "B2_FILIAL_ORIGINAL".
        "mapa_colunas": {"B2_FILIAL": "B2_FILIAL_ORIGINAL"},
    },
    {
        "id": "pedidos",
        "nome_site": "Movimentos BAP Protheus",
        "aba_excel": "ftPedidos",
        "arquivo": "Relatorio_Movimentos_BAP_Protheus",
        "linha_cabecalho": 1,
        "filtros": {},
        "colunas_ignorar": [],
        "linhas_a_mais": "limpar",
    },
    {
        "id": "estoquepmz",
        "nome_site": "Estoques PMZ WEB-LEGADO",
        "aba_excel": "ftEstoquePMZ",
        "arquivo": "Relatorio_Estoques_PMZ_WEB_LEGADO",
        "linha_cabecalho": 1,
        "filtros": {},
        "colunas_ignorar": [],
        "linhas_a_mais": "limpar",
    },
    {
        # (14/10) NCC PENDENTES: os creditos dos clientes a compensar (Farol
        # de NCC, Pos-venda). A aba ftNCC nasce na 1a rodada (criar_aba).
        "id": "ncc",
        "nome_site": "NCC Pendentes",
        "aba_excel": "ftNCC",
        "arquivo": "Relatorio_NCC_Pendentes",
        "linha_cabecalho": 1,
        "filtros": {},
        "colunas_ignorar": [],
        "linhas_a_mais": "limpar",
        "criar_aba": True,
    },
    {
        "id": "precos",
        "nome_site": "Tabela preços",
        "aba_excel": "ftTabelaPreco",
        "arquivo": "Relatorio_Tabela_precos",
        "linha_cabecalho": 1,
        "filtros": {},
        "colunas_ignorar": [],
        "linhas_a_mais": "limpar",
    },
]

# Outras consultas existentes no BAP Tools, sem aba de destino hoje:
#   Ped.Abertos / Faturados | Exclusoes Capa Ped. | SKU Exclusoes pedido
# Para trazer alguma delas, copie um bloco acima e aponte para a aba desejada.

# =============================================================================
# =========================  FIM DO BLOCO CONFIG  =============================
# =============================================================================


EXTENSOES_ACEITAS = {".xlsx", ".xlsm", ".xls", ".csv", ".txt"}
NOME_TRAVA = "_EXECUCAO_EM_ANDAMENTO.txt"
IDADE_MAXIMA_TRAVA = 4 * 60 * 60

PASTA_RELATORIOS = PASTA_LOCAL / SUBPASTA_RELATORIOS
# (05/11) a fotografia das abas de dados da TABELA_BAP
PASTA_DADOS = PASTA_RELATORIOS / dados_bap.SUBPASTA
PASTA_BACKUPS = PASTA_LOCAL / BKP_AUXILIARES
PASTA_LOGS = PASTA_LOCAL / SUBPASTA_SISTEMA / "logs"
PASTA_AUTH = PASTA_LOCAL / SUBPASTA_SISTEMA / "auth"
PASTA_TEMP = (Path(tempfile.gettempdir()) / "BAP_TOOLS_temporarios"
              if TEMPORARIOS_FORA_DA_PASTA else PASTA_LOCAL / "temporarios")
PASTA_EVIDENCIAS = PASTA_LOCAL / SUBPASTA_SISTEMA / "evidencias"
CACHE_MSAL = PASTA_AUTH / "microsoft_token.bin"

DOWNLOADS_DO_USUARIO = Path.home() / "Downloads"

log = logging.getLogger("bap")


# =============================================================================
# 1. INFRAESTRUTURA LOCAL
# =============================================================================

def arrumar_pasta_de_trabalho() -> list[str]:
    """
    Poe a pasta no desenho novo: os Excel do dia a dia na RELATORIOS e as
    copias na BACKUP_RELATORIOS. Roda em toda execucao, MOVE e nunca apaga,
    e nao faz nada quando ja esta tudo no lugar.

    Quando o pastas_bap.py estiver ao lado (ele vem junto com o PLANNER),
    e ele quem manda - assim os dois programas arrumam a pasta igual. Sem
    ele, esta funcao faz o basico sozinha: o bap_automation.py tem de rodar
    mesmo numa pasta onde so ele exista.
    """
    try:
        sys.path.insert(0, str(PASTA_LOCAL))
        import pastas_bap as _pb          # noqa: PLC0415
        return _pb.arrumar(PASTA_LOCAL, registrar=lambda t: log.info("  %s", t))
    except Exception:                     # noqa: BLE001 - sem ele, o basico
        pass
    feito = []
    for nome in (NOME_PLANILHA, ARQUIVO_SOLICITACAO, ARQUIVO_ESTOQUE_BAP,
                 ARQUIVO_PRECOS, "BASE_CLIENTE.xlsx"):
        de = PASTA_LOCAL / nome
        para = PASTA_RELATORIOS / nome
        if de.is_file() and not para.exists():
            try:
                shutil.move(str(de), str(para))
                feito.append(f"{nome} -> {SUBPASTA_RELATORIOS}")
            except OSError:
                pass
    # a BACKUP_RELATORIOS era a propria pasta dos relatorios do BAP Tools;
    # agora e o guarda-chuva, e o que estiver solto dentro dela desce para a
    # BKP_RELATORIOS_BAPTOOLS
    guarda_chuva = PASTA_LOCAL / SUBPASTA_BACKUP
    if guarda_chuva.is_dir():
        destino_rel = PASTA_LOCAL / SUBPASTA_DOWNLOADS
        destino_rel.mkdir(parents=True, exist_ok=True)
        for item in list(guarda_chuva.iterdir()):
            if item.is_dir() or item.suffix.lower() in (".txt", ".log"):
                continue
            if not (destino_rel / item.name).exists():
                try:
                    shutil.move(str(item), str(destino_rel / item.name))
                    feito.append(f"{item.name} -> {SUBPASTA_DOWNLOADS}")
                except OSError:
                    pass
    for antiga, nova in (("SEPARACAO_BAP", SUBPASTA_DOWNLOADS),
                         ("BACKUP_RELATORIOS_ANTIGA", SUBPASTA_DOWNLOADS),
                         ("backups", BKP_AUXILIARES),
                         ("historico_precos", SUBPASTA_FOTOS_PRECO)):
        de, para = PASTA_LOCAL / antiga, PASTA_LOCAL / nova
        if not de.is_dir() or de.resolve() == para.resolve():
            continue
        para.mkdir(parents=True, exist_ok=True)
        for item in list(de.iterdir()):
            if not (para / item.name).exists():
                try:
                    shutil.move(str(item), str(para / item.name))
                except OSError:
                    pass
        try:
            de.rmdir()
            feito.append(f"{antiga} -> {nova}")
        except OSError:
            pass
    for texto in feito:
        log.info("Pasta arrumada: %s", texto)
    return feito


def garantir_pastas_locais() -> None:
    for pasta in (PASTA_LOCAL, PASTA_RELATORIOS, PASTA_BACKUPS, PASTA_LOGS,
                  PASTA_AUTH, PASTA_TEMP, PASTA_EVIDENCIAS,
                  PASTA_LOCAL / SUBPASTA_DOWNLOADS,
                  PASTA_LOCAL / BKP_PRECO, PASTA_LOCAL / BKP_PLANNER,
                  PASTA_LOCAL / SUBPASTA_FOTOS_PRECO):
        pasta.mkdir(parents=True, exist_ok=True)
    arrumar_pasta_de_trabalho()


def configurar_log(verboso: bool = False) -> None:
    log.setLevel(logging.DEBUG if verboso else logging.INFO)
    log.handlers.clear()
    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%d/%m/%Y %H:%M:%S"
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formato)
    log.addHandler(console)
    # O nome da maquina entra no arquivo: com a pasta compartilhada entre duas
    # pessoas, um log unico viraria copia conflitante do OneDrive toda hora.
    maquina = re.sub(r"[^A-Za-z0-9_-]", "", os.environ.get("COMPUTERNAME", "")) or "PC"
    arquivo = logging.FileHandler(
        PASTA_LOGS / f"execucao_{datetime.now():%Y%m}_{maquina}.log", encoding="utf-8"
    )
    arquivo.setFormatter(formato)
    log.addHandler(arquivo)


def limpar_temporarios() -> None:
    for arquivo in PASTA_TEMP.glob("*"):
        try:
            if arquivo.is_file():
                arquivo.unlink()
            else:
                shutil.rmtree(arquivo, ignore_errors=True)
        except Exception:
            pass


def caminho_da_solicitacao(simular: bool = False) -> Path:
    """
    O SOLICITACAO_BAP.xlsx fica na pasta RELATORIOS, junto com os outros
    Excel do dia a dia. Na simulacao, com outro nome, para nunca escrever
    por cima do arquivo de verdade.
    """
    nome = ARQUIVO_SOLICITACAO_SIMULACAO if simular else ARQUIVO_SOLICITACAO
    return PASTA_RELATORIOS / nome


def backup_local(caminho: Path) -> None:
    destino = PASTA_BACKUPS / (
        f"{Path(NOME_PLANILHA).stem}_{datetime.now():%Y%m%d_%H%M%S}"
        f"{Path(NOME_PLANILHA).suffix}"
    )
    shutil.copy2(caminho, destino)
    log.info("Backup local: %s", destino)

    if MANTER_BACKUPS:
        backups = sorted(PASTA_BACKUPS.glob(f"{Path(NOME_PLANILHA).stem}_*"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for antigo in backups[MANTER_BACKUPS:]:
            antigo.unlink(missing_ok=True)


# =============================================================================
# 2. CAMADA DE NUVEM  -  duas implementacoes com a mesma interface
# =============================================================================

class ArmazenamentoBase:
    """Interface usada pelo resto do script."""

    def conectar(self) -> None: ...
    def descrever(self) -> str: ...
    def adquirir_trava(self, forcar: bool = False) -> None: ...
    def liberar_trava(self) -> None: ...
    def planilha_ocupada(self) -> bool: return False
    def baixar_planilha(self, destino: Path) -> Path: ...
    def enviar_planilha(self, origem: Path) -> None: ...
    def guardar_relatorio(self, origem: Path, nome: str) -> str: ...
    def guardar_backup_nuvem(self, origem: Path, nome: str) -> None: ...
    def relatorio_mais_recente(self, prefixo: str, destino: Path) -> Path | None: ...
    def obter_arquivo(self, nome: str, destino: Path) -> Path | None: ...
    def abas_da_planilha(self) -> list[str]: ...


# ------------------------------ MODO LOCAL -----------------------------------

class ArmazenamentoLocal(ArmazenamentoBase):

    def __init__(self):
        self.pasta_nuvem: Path | None = None
        self.pasta_separacao: Path | None = None
        self.planilha: Path | None = None
        self.trava: Path | None = None

    @staticmethod
    def _detectar_raiz_onedrive() -> Path | None:
        for variavel in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive"):
            valor = os.environ.get(variavel)
            if valor and Path(valor).is_dir():
                return Path(valor)
        candidatas = [p for p in Path.home().glob("OneDrive*") if p.is_dir()]
        if len(candidatas) == 1:
            return candidatas[0]
        for candidata in candidatas:
            if (candidata / CAMINHO_RELATIVO_PLANILHA.split("\\")[0]).is_dir():
                return candidata
        return None

    @staticmethod
    def _procurar_pasta(raiz: Path) -> Path | None:
        """
        Procura a pasta alvo em qualquer nivel do OneDrive.
        Serve para quem usou "Adicionar atalho ao Meu OneDrive": nesse caso a
        pasta aparece direto na raiz, sem o caminho "1 - PMZ\\2025\\...".
        """
        alvo = Path(CAMINHO_RELATIVO_PLANILHA.replace("\\", "/")).name.lower()
        encontradas: list[Path] = []

        def varrer(pasta: Path, nivel: int) -> None:
            if nivel > 5 or len(encontradas) > 20:
                return
            try:
                itens = [i for i in pasta.iterdir() if i.is_dir()]
            except (PermissionError, OSError):
                return
            for item in itens:
                if item.name.startswith((".", "~")):
                    continue
                if item.name.lower() == alvo:
                    encontradas.append(item)
                else:
                    varrer(item, nivel + 1)

        varrer(raiz, 0)
        com_planilha = [p for p in encontradas if (p / NOME_PLANILHA).exists()]
        if com_planilha:
            return com_planilha[0]
        return encontradas[0] if encontradas else None

    def _pasta_antiga_no_onedrive(self) -> Path | None:
        """Onde a rotina guardava tudo antes de mudar para a pasta local."""
        try:
            raiz = self._detectar_raiz_onedrive()
            if raiz is None:
                return None
            direta = raiz / CAMINHO_RELATIVO_PLANILHA
            if direta.is_dir():
                return direta
            return self._procurar_pasta(raiz)
        except Exception as erro:
            log.debug("Nao consegui localizar a pasta antiga: %s", erro)
            return None

    def _importar_historico(self, antiga: Path | None = None) -> None:
        """
        O SOLICITACAO_BAP.xlsx passou a morar na raiz de BAP_TOOLS. Se ele
        ainda estiver num dos lugares antigos, e trazido para ca - sem ele,
        coletas ja abertas voltariam a ser solicitadas com SEPs novas.
        """
        destino = PASTA_RELATORIOS / ARQUIVO_SOLICITACAO
        if destino.exists():
            return

        candidatos = [
            PASTA_LOCAL / ARQUIVO_SOLICITACAO,     # onde ficava antes
            PASTA_LOCAL / SUBPASTA_DOWNLOADS / ARQUIVO_SOLICITACAO,
            PASTA_LOCAL / SUBPASTA_DOWNLOADS_ANTIGA / ARQUIVO_SOLICITACAO,
        ]
        if antiga is None:
            antiga = self._pasta_antiga_no_onedrive()
        if antiga is not None:
            candidatos += [
                Path(antiga) / SUBPASTA_DOWNLOADS / ARQUIVO_SOLICITACAO,
                Path(antiga) / SUBPASTA_DOWNLOADS_ANTIGA / ARQUIVO_SOLICITACAO,
            ]

        origem = next((c for c in candidatos if c.exists()), None)
        if origem is None:
            return
        try:
            shutil.copy2(origem, destino)
            log.warning("Solicitacao trazida para a raiz de %s:", PASTA_LOCAL)
            log.warning("  %s -> %s", origem, destino)
        except Exception as erro:
            log.error("NAO consegui trazer o %s: %s", ARQUIVO_SOLICITACAO, erro)
            log.error("  Copie na mao para %s antes de rodar, ou coletas ja "
                      "abertas serao solicitadas de novo.", destino)

    def _importar_do_onedrive(self) -> bool:
        """
        Primeira execucao com LOCAL_DA_PLANILHA = "bap_tools": a TABELA_BAP
        ainda nao esta na pasta local. Traz do OneDrive a planilha E o
        historico da SOLICITACAO_BAP - sem ele, coletas ja abertas seriam
        pedidas de novo. Devolve True se a planilha veio.
        """
        antiga = self._pasta_antiga_no_onedrive()
        if antiga is None:
            return False

        origem = Path(antiga) / NOME_PLANILHA
        if not origem.exists():
            return False

        try:
            log.warning("=" * 70)
            log.warning("PRIMEIRA EXECUCAO COM A PLANILHA EM %s", self.pasta_nuvem)
            log.warning("Trazendo o que estava no OneDrive:")
            log.warning("  origem: %s", antiga)
            shutil.copy2(origem, self.planilha)
            log.warning("  [ok] %s", NOME_PLANILHA)
        except Exception as erro:
            log.error("Nao consegui copiar a planilha: %s", erro)
            return False

        log.warning("A partir de agora a rotina usa SO a pasta local.")
        log.warning("  - a %s do OneDrive nao sera mais atualizada;", NOME_PLANILHA)
        log.warning("  - os relatorios antigos continuam arquivados la.")
        log.warning("=" * 70)
        return True

    def conectar(self) -> None:
        if LOCAL_DA_PLANILHA == "mesma_pasta":
            # Tudo na pasta do script: nada a procurar.
            self.pasta_nuvem = PASTA_LOCAL
            self.pasta_nuvem.mkdir(parents=True, exist_ok=True)
        elif PASTA_NUVEM_MANUAL is not None:
            self.pasta_nuvem = Path(PASTA_NUVEM_MANUAL)
        else:
            raiz = self._detectar_raiz_onedrive()
            if raiz is None:
                raise RuntimeError(
                    "Nao encontrei a pasta do OneDrive nesta maquina. Sincronize a "
                    "pasta, preencha PASTA_NUVEM_MANUAL ou use MODO_NUVEM = 'graph'."
                )

            direta = raiz / CAMINHO_RELATIVO_PLANILHA
            if direta.is_dir():
                self.pasta_nuvem = direta
            else:
                log.info("Caminho padrao nao existe aqui; procurando a pasta '%s' "
                         "dentro do OneDrive...",
                         Path(CAMINHO_RELATIVO_PLANILHA.replace("\\", "/")).name)
                achada = self._procurar_pasta(raiz)
                if achada is None:
                    raise RuntimeError(
                        f"Nao achei a pasta '"
                        f"{Path(CAMINHO_RELATIVO_PLANILHA.replace(chr(92), '/')).name}"
                        f"' dentro de {raiz}.\n"
                        "  - Se voce recebeu a pasta compartilhada, abra-a no OneDrive "
                        "web e use 'Adicionar atalho ao Meu OneDrive';\n"
                        "  - depois confirme no Explorer que ela aparece;\n"
                        "  - ou preencha PASTA_NUVEM_MANUAL com o caminho completo."
                    )
                self.pasta_nuvem = achada
                log.info("Pasta localizada: %s", achada)

        if not self.pasta_nuvem.is_dir():
            raise RuntimeError(f"Pasta nao encontrada nesta maquina:\n  {self.pasta_nuvem}")

        # os relatorios do BAP Tools agora ficam em
        # BACKUP_RELATORIOS\BKP_RELATORIOS_BAPTOOLS. As pastas antigas, se
        # ainda existirem, tem o conteudo mudado de lugar - nada e apagado.
        self.pasta_separacao = self.pasta_nuvem / SUBPASTA_DOWNLOADS
        self.pasta_separacao.mkdir(parents=True, exist_ok=True)
        for antigo in (SUBPASTA_DOWNLOADS_ANTIGA, SUBPASTA_BACKUP):
            antiga_pasta = self.pasta_nuvem / antigo
            if not antiga_pasta.is_dir():
                continue
            movidos = 0
            for item in list(antiga_pasta.iterdir()):
                if item.is_dir() or (self.pasta_separacao / item.name).exists():
                    continue
                try:
                    item.rename(self.pasta_separacao / item.name)
                    movidos += 1
                except OSError:
                    pass
            if movidos:
                log.warning("%d relatorio(s) de '%s' foram para '%s'.",
                            movidos, antigo, SUBPASTA_DOWNLOADS)

        # a TABELA_BAP mora na RELATORIOS. Se ainda estiver na raiz, vai
        # para la agora - e o mesmo arquivo, so mudou de gaveta.
        (self.pasta_nuvem / SUBPASTA_RELATORIOS).mkdir(parents=True,
                                                       exist_ok=True)
        self.planilha = self.pasta_nuvem / SUBPASTA_RELATORIOS / NOME_PLANILHA
        na_raiz = self.pasta_nuvem / NOME_PLANILHA
        if na_raiz.is_file() and not self.planilha.exists():
            try:
                na_raiz.rename(self.planilha)
                log.warning("%s foi para a pasta %s.", NOME_PLANILHA,
                            SUBPASTA_RELATORIOS)
            except OSError as erro:
                log.warning("Nao consegui mover a %s para %s: %s",
                            NOME_PLANILHA, SUBPASTA_RELATORIOS, erro)
                self.planilha = na_raiz
        self.trava = self.pasta_separacao / NOME_TRAVA

        if LOCAL_DA_PLANILHA == "mesma_pasta":
            if not self.planilha.exists():
                self._importar_do_onedrive()
            # o historico e conferido sempre: ele pode ter ficado numa das
            # pastas antigas mesmo com a planilha ja no lugar certo
            self._importar_historico()

        if not self.planilha.exists():
            if LOCAL_DA_PLANILHA == "mesma_pasta":
                raise RuntimeError(
                    f"Planilha nao encontrada:\n  {self.planilha}\n"
                    f"  - coloque a {NOME_PLANILHA} dentro de {PASTA_LOCAL};\n"
                    f"  - ou volte LOCAL_DA_PLANILHA para \"onedrive\" no topo "
                    f"do script para usar a pasta sincronizada."
                )
            raise RuntimeError(f"Planilha nao encontrada:\n  {self.planilha}")

    def descrever(self) -> str:
        if LOCAL_DA_PLANILHA == "mesma_pasta":
            return f"pasta local: {self.pasta_nuvem}"
        return f"pasta sincronizada: {self.pasta_nuvem}"

    def adquirir_trava(self, forcar: bool = False) -> None:
        if self.trava.exists() and not forcar:
            idade = time.time() - self.trava.stat().st_mtime
            if idade < IDADE_MAXIMA_TRAVA:
                raise RuntimeError(
                    f"Outra execucao em andamento:\n  "
                    f"{self.trava.read_text(encoding='utf-8', errors='ignore').strip()}\n"
                    f"Se estiver presa, rode com --destravar."
                )
            log.warning("Trava antiga (%.0f min) ignorada.", idade / 60)
        self.trava.write_text(
            f"{os.environ.get('USERNAME', 'desconhecido')} em "
            f"{os.environ.get('COMPUTERNAME', '?')} desde "
            f"{datetime.now():%d/%m/%Y %H:%M:%S}",
            encoding="utf-8",
        )

    def liberar_trava(self) -> None:
        if self.trava:
            self.trava.unlink(missing_ok=True)

    def planilha_ocupada(self) -> bool:
        if (self.planilha.parent / f"~${self.planilha.name}").exists():
            return True
        try:
            with open(self.planilha, "r+b"):
                return False
        except (PermissionError, OSError):
            return True

    def baixar_planilha(self, destino: Path) -> Path:
        shutil.copy2(self.planilha, destino)
        return destino

    def enviar_planilha(self, origem: Path) -> None:
        for tentativa in range(1, 7):
            try:
                try:
                    os.replace(origem, self.planilha)
                except OSError as erro:
                    if getattr(erro, "errno", None) != 18:   # EXDEV: discos diferentes
                        raise
                    shutil.copy2(origem, self.planilha)
                    origem.unlink(missing_ok=True)
                return
            except PermissionError:
                if tentativa == 6:
                    raise
                log.warning("Arquivo em uso (OneDrive/Excel). Tentativa %d/6...", tentativa)
                time.sleep(5)

    def guardar_relatorio(self, origem: Path, nome: str) -> str:
        destino = self.pasta_separacao / nome
        shutil.move(str(origem), destino)
        return str(destino)

    def guardar_backup_nuvem(self, origem: Path, nome: str) -> None:
        # Com tudo na mesma pasta, este backup cairia na mesma
        # pasta do backup local. Um so basta: o de backups\, que ja tem
        # rotacao (MANTER_BACKUPS).
        if self.pasta_nuvem == PASTA_LOCAL:
            log.debug("Backup unico em %s (pasta de destino = pasta local).",
                      PASTA_BACKUPS)
            return
        pasta = self.pasta_nuvem / SUBPASTA_BACKUP_NUVEM
        pasta.mkdir(exist_ok=True)
        shutil.copy2(origem, pasta / nome)

    def relatorio_mais_recente(self, prefixo: str, destino: Path) -> Path | None:
        arquivos = sorted(self.pasta_separacao.glob(f"{prefixo}_*"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        return arquivos[0] if arquivos else None

    def obter_arquivo(self, nome: str, destino: Path) -> Path | None:
        origem = self.pasta_separacao / nome
        if not origem.exists():
            return None
        shutil.copy2(origem, destino)
        return destino

    def abas_da_planilha(self) -> list[str]:
        wb = load_workbook(self.planilha, read_only=True)
        abas = wb.sheetnames
        wb.close()
        return abas


# ------------------------------ MODO GRAPH -----------------------------------

class ArmazenamentoGraph(ArmazenamentoBase):
    """Acesso direto ao SharePoint/OneDrive pela API Microsoft Graph."""

    RAIZ = "https://graph.microsoft.com/v1.0"
    ESCOPOS = ["Files.ReadWrite.All"]
    LIMITE_UPLOAD_SIMPLES = 4 * 1024 * 1024
    TAMANHO_BLOCO = 5 * 320 * 1024      # 1,6 MB (multiplo de 320 KiB, exigido)

    def __init__(self):
        self.sessao = None
        self.token: str | None = None
        self.drive_raiz = self.item_pasta_raiz = None
        self.drive_planilha = self.item_pasta_planilha = None
        self.drive_downloads = self.item_pasta_downloads = None
        self.item_planilha = None
        self.usuario = "?"

    # ---------------------------- autenticacao -------------------------------

    def _autenticar(self, interativo_permitido: bool) -> str:
        try:
            import msal
        except ImportError:
            raise RuntimeError("Falta a biblioteca: pip install msal requests")

        if GRAPH_CLIENT_ID.startswith("COLE-AQUI"):
            raise RuntimeError(
                "GRAPH_CLIENT_ID nao foi preenchido. Veja o passo a passo no "
                "cabecalho do script (registro do aplicativo no Entra ID)."
            )

        cache = msal.SerializableTokenCache()
        if CACHE_MSAL.exists():
            try:
                cache.deserialize(CACHE_MSAL.read_text(encoding="utf-8"))
            except Exception:
                log.warning("Cache de token ilegivel; sera refeito.")

        app = msal.PublicClientApplication(
            GRAPH_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}",
            token_cache=cache,
        )

        resultado = None
        contas = app.get_accounts()
        if contas:
            resultado = app.acquire_token_silent(self.ESCOPOS, account=contas[0])

        if not resultado:
            if not interativo_permitido:
                raise RuntimeError(
                    "Sem token valido da Microsoft nesta maquina.\n"
                    "Rode uma vez:  python bap_automation.py --configurar-nuvem"
                )
            fluxo = app.initiate_device_flow(scopes=self.ESCOPOS)
            if "user_code" not in fluxo:
                raise RuntimeError(f"Falha ao iniciar o login: {fluxo}")
            print("\n" + "=" * 70)
            print("  LOGIN NA MICROSOFT")
            print("=" * 70)
            print(f"\n  1. Abra:  {fluxo['verification_uri']}")
            print(f"  2. Digite o codigo:  {fluxo['user_code']}")
            print("  3. Entre com a conta corporativa e autorize o aplicativo.\n")
            resultado = app.acquire_token_by_device_flow(fluxo)

        if "access_token" not in resultado:
            raise RuntimeError(
                f"Login falhou: {resultado.get('error_description', resultado)}"
            )

        if cache.has_state_changed:
            CACHE_MSAL.write_text(cache.serialize(), encoding="utf-8")
            try:
                os.chmod(CACHE_MSAL, 0o600)
            except Exception:
                pass

        reivindicacoes = resultado.get("id_token_claims") or {}
        self.usuario = (reivindicacoes.get("preferred_username")
                        or reivindicacoes.get("name") or "?")
        return resultado["access_token"]

    def conectar(self, interativo_permitido: bool = False) -> None:
        import requests

        self.token = self._autenticar(interativo_permitido)
        self.sessao = requests.Session()
        self.sessao.headers.update({"Authorization": f"Bearer {self.token}"})

        # a raiz e a pasta "Regionais - Leandro"; a planilha mora na
        # RELATORIOS e os relatorios baixados na BKP_RELATORIOS_BAPTOOLS
        self.drive_raiz, self.item_pasta_raiz = self._resolver_pasta(
            URL_PASTA_PLANILHA
        )
        self.drive_planilha = self.drive_raiz
        self.item_pasta_planilha = self._garantir_caminho(
            self.drive_raiz, self.item_pasta_raiz, SUBPASTA_RELATORIOS)
        self.drive_downloads = self.drive_raiz
        self.item_pasta_downloads = self._garantir_caminho(
            self.drive_raiz, self.item_pasta_raiz, SUBPASTA_DOWNLOADS)

        self.item_planilha = self._buscar_filho(
            self.drive_planilha, self.item_pasta_planilha, NOME_PLANILHA
        )
        if self.item_planilha is None:
            # ainda na raiz, de antes da pasta RELATORIOS existir
            self.item_planilha = self._buscar_filho(
                self.drive_raiz, self.item_pasta_raiz, NOME_PLANILHA)
            if self.item_planilha is not None:
                log.warning("A %s ainda esta na raiz da pasta da nuvem. "
                            "Mova-a para %s - o lugar dela agora e la.",
                            NOME_PLANILHA, SUBPASTA_RELATORIOS)
                self.item_pasta_planilha = self.item_pasta_raiz
        if self.item_planilha is None:
            raise RuntimeError(
                f"'{NOME_PLANILHA}' nao encontrada nem em "
                f"{SUBPASTA_RELATORIOS} nem na raiz da pasta indicada por "
                f"URL_PASTA_PLANILHA. Confira o nome e a permissao de acesso."
            )

    # ------------------------------ utilitarios ------------------------------

    def _pedir(self, metodo: str, url: str, **kwargs):
        if not url.startswith("http"):
            url = self.RAIZ + url
        for tentativa in range(1, 5):
            resposta = self.sessao.request(metodo, url, timeout=180, **kwargs)
            if resposta.status_code in (429, 503, 504):
                espera = int(resposta.headers.get("Retry-After", 5 * tentativa))
                log.warning("Graph pediu espera (%s). Aguardando %ds...",
                            resposta.status_code, espera)
                time.sleep(espera)
                continue
            if resposta.status_code >= 400:
                raise RuntimeError(
                    f"Graph {metodo} {url} -> {resposta.status_code}: "
                    f"{resposta.text[:400]}"
                )
            return resposta
        raise RuntimeError("Graph indisponivel apos varias tentativas.")

    @staticmethod
    def _caminho_nome(nome: str) -> str:
        from urllib.parse import quote
        return quote(nome, safe="")

    @staticmethod
    def _token_compartilhamento(url: str) -> str:
        codificado = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii")
        return "u!" + codificado.rstrip("=")

    def _resolver_pasta(self, url: str) -> tuple[str, str]:
        """Descobre driveId + itemId a partir da URL que se abre no navegador."""
        dados = self._pedir(
            "GET", f"/shares/{self._token_compartilhamento(url)}/driveItem"
        ).json()
        if "folder" not in dados:
            raise RuntimeError(f"A URL nao aponta para uma pasta: {url}")
        return dados["parentReference"]["driveId"], dados["id"]

    def _buscar_filho(self, drive: str, pasta: str, nome: str) -> dict | None:
        url = f"/drives/{drive}/items/{pasta}/children?$top=200"
        alvo = nome.strip().lower()
        while url:
            pagina = self._pedir("GET", url).json()
            for item in pagina.get("value", []):
                if item["name"].strip().lower() == alvo:
                    return item
            url = pagina.get("@odata.nextLink")
        return None

    def _listar_filhos(self, drive: str, pasta: str) -> list[dict]:
        itens, url = [], f"/drives/{drive}/items/{pasta}/children?$top=200"
        while url:
            pagina = self._pedir("GET", url).json()
            itens.extend(pagina.get("value", []))
            url = pagina.get("@odata.nextLink")
        return itens

    def _criar_pasta(self, drive: str, pai: str, nome: str) -> str:
        dados = self._pedir(
            "POST", f"/drives/{drive}/items/{pai}/children",
            json={"name": nome, "folder": {},
                  "@microsoft.graph.conflictBehavior": "return"},
        ).json()
        return dados["id"]

    def _garantir_pasta(self, drive: str, pai: str, nome: str) -> str:
        existente = self._buscar_filho(drive, pai, nome)
        if existente and "folder" in existente:
            return existente["id"]
        return self._criar_pasta(drive, pai, nome)

    def _garantir_caminho(self, drive: str, pai: str, caminho: str) -> str:
        """
        Garante uma sequencia de pastas ("BACKUP_RELATORIOS/BKP_..."), uma
        de cada vez. Devolve o id da ultima.
        """
        atual = pai
        for parte in str(caminho).replace("\\", "/").split("/"):
            if parte:
                atual = self._garantir_pasta(drive, atual, parte)
        return atual

    def _enviar(self, origem: Path, drive: str, pasta: str, nome: str) -> dict:
        tamanho = origem.stat().st_size
        alvo = self._caminho_nome(nome)

        if tamanho <= self.LIMITE_UPLOAD_SIMPLES:
            with open(origem, "rb") as arquivo:
                return self._pedir(
                    "PUT", f"/drives/{drive}/items/{pasta}:/{alvo}:/content",
                    data=arquivo,
                    headers={"Content-Type": "application/octet-stream"},
                ).json()

        sessao = self._pedir(
            "POST", f"/drives/{drive}/items/{pasta}:/{alvo}:/createUploadSession",
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        ).json()
        url_upload = sessao["uploadUrl"]

        import requests
        enviado, resposta = 0, None
        with open(origem, "rb") as arquivo:
            while enviado < tamanho:
                bloco = arquivo.read(self.TAMANHO_BLOCO)
                fim = enviado + len(bloco) - 1
                cabecalhos = {
                    "Content-Length": str(len(bloco)),
                    "Content-Range": f"bytes {enviado}-{fim}/{tamanho}",
                }
                resposta = requests.put(url_upload, data=bloco,
                                        headers=cabecalhos, timeout=300)
                if resposta.status_code not in (200, 201, 202):
                    raise RuntimeError(
                        f"Upload falhou em {enviado}: "
                        f"{resposta.status_code} {resposta.text[:300]}"
                    )
                enviado = fim + 1
                log.debug("  enviado %.1f%%", 100 * enviado / tamanho)
        return resposta.json() if (resposta is not None and resposta.content) else {}

    def _baixar(self, drive: str, item: str, destino: Path) -> Path:
        resposta = self._pedir("GET", f"/drives/{drive}/items/{item}/content",
                               stream=True)
        with open(destino, "wb") as arquivo:
            for bloco in resposta.iter_content(chunk_size=1024 * 512):
                arquivo.write(bloco)
        return destino

    # ------------------------------ interface --------------------------------

    def descrever(self) -> str:
        return f"Microsoft Graph, conectado como {self.usuario}"

    def adquirir_trava(self, forcar: bool = False) -> None:
        existente = self._buscar_filho(self.drive_downloads,
                                       self.item_pasta_downloads, NOME_TRAVA)
        if existente and not forcar:
            modificado = existente.get("lastModifiedDateTime", "")
            try:
                quando = datetime.fromisoformat(modificado.replace("Z", "+00:00"))
                idade = (datetime.now(quando.tzinfo) - quando).total_seconds()
            except Exception:
                idade = 0
            if idade < IDADE_MAXIMA_TRAVA:
                conteudo = self._pedir(
                    "GET",
                    f"/drives/{self.drive_downloads}/items/{existente['id']}/content"
                ).text
                raise RuntimeError(
                    f"Outra pessoa esta rodando a automacao agora:\n  "
                    f"{conteudo.strip()}\nSe a trava ficou presa, use --destravar."
                )
            log.warning("Trava antiga (%.0f min) ignorada.", idade / 60)

        texto = (f"{self.usuario} em {os.environ.get('COMPUTERNAME', '?')} desde "
                 f"{datetime.now():%d/%m/%Y %H:%M:%S}")
        self._pedir(
            "PUT",
            f"/drives/{self.drive_downloads}/items/"
            f"{self.item_pasta_downloads}:/{self._caminho_nome(NOME_TRAVA)}:/content",
            data=texto.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )

    def liberar_trava(self) -> None:
        try:
            existente = self._buscar_filho(self.drive_downloads,
                                           self.item_pasta_downloads, NOME_TRAVA)
            if existente:
                self._pedir("DELETE",
                            f"/drives/{self.drive_downloads}/items/{existente['id']}")
        except Exception as erro:
            log.warning("Nao consegui remover a trava da nuvem: %s", erro)

    def baixar_planilha(self, destino: Path) -> Path:
        tamanho = self.item_planilha.get("size", 0)
        log.info("Baixando %s da nuvem (%.1f MB)...", NOME_PLANILHA, tamanho / 1048576)
        return self._baixar(self.drive_planilha, self.item_planilha["id"], destino)

    def enviar_planilha(self, origem: Path) -> None:
        log.info("Enviando %s de volta para a nuvem (%.1f MB)...",
                 NOME_PLANILHA, origem.stat().st_size / 1048576)
        self._enviar(origem, self.drive_planilha, self.item_pasta_planilha,
                     NOME_PLANILHA)

    def guardar_relatorio(self, origem: Path, nome: str) -> str:
        self._enviar(origem, self.drive_downloads, self.item_pasta_downloads, nome)
        origem.unlink(missing_ok=True)
        return f"{SUBPASTA_DOWNLOADS}/{nome}"

    def guardar_backup_nuvem(self, origem: Path, nome: str) -> None:
        pasta = self._garantir_caminho(self.drive_raiz, self.item_pasta_raiz,
                                       f"{BKP_AUXILIARES}/{SUBPASTA_BACKUP_NUVEM}")
        self._enviar(origem, self.drive_planilha, pasta, nome)
        log.info("Backup na nuvem: %s/%s", SUBPASTA_BACKUP_NUVEM, nome)

    def relatorio_mais_recente(self, prefixo: str, destino: Path) -> Path | None:
        candidatos = [
            item for item in self._listar_filhos(self.drive_downloads,
                                                 self.item_pasta_downloads)
            if item["name"].startswith(prefixo + "_") and "file" in item
        ]
        if not candidatos:
            return None
        escolhido = max(candidatos, key=lambda i: i.get("lastModifiedDateTime", ""))
        alvo = destino / escolhido["name"]
        self._baixar(self.drive_downloads, escolhido["id"], alvo)
        return alvo

    def obter_arquivo(self, nome: str, destino: Path) -> Path | None:
        item = self._buscar_filho(self.drive_downloads,
                                  self.item_pasta_downloads, nome)
        if item is None:
            return None
        return self._baixar(self.drive_downloads, item["id"], destino)

    def abas_da_planilha(self) -> list[str]:
        temporario = PASTA_TEMP / f"_abas_{NOME_PLANILHA}"
        self.baixar_planilha(temporario)
        wb = load_workbook(temporario, read_only=True)
        abas = wb.sheetnames
        wb.close()
        temporario.unlink(missing_ok=True)
        return abas


def criar_armazenamento(interativo: bool = False) -> ArmazenamentoBase:
    if MODO_NUVEM.lower() == "graph":
        armazenamento = ArmazenamentoGraph()
        armazenamento.conectar(interativo_permitido=interativo)
    else:
        armazenamento = ArmazenamentoLocal()
        armazenamento.conectar()
    if MODO_NUVEM.lower() != "graph" and LOCAL_DA_PLANILHA == "mesma_pasta":
        log.info("Planilha: %s", armazenamento.descrever())
    else:
        log.info("Nuvem: %s", armazenamento.descrever())
    return armazenamento


# =============================================================================
# 3. CREDENCIAIS DO BAP TOOLS
# =============================================================================

def obter_senha() -> str:
    senha = os.environ.get("BAP_SENHA")
    if senha:
        return senha
    if keyring is not None:
        try:
            senha = keyring.get_password(SERVICO_KEYRING, USUARIO_BAP)
            if senha:
                return senha
        except Exception:
            pass
    if SENHA_PADRAO:
        return SENHA_PADRAO
    raise RuntimeError("Senha do BAP Tools nao encontrada (use --salvar-senha).")


def salvar_senha_interativo() -> None:
    import getpass
    if keyring is None:
        print("Instale a biblioteca:  pip install keyring")
        return
    usuario = input(f"Usuario [{USUARIO_BAP}]: ").strip() or USUARIO_BAP
    senha = getpass.getpass("Senha (nao aparece na tela): ")
    keyring.set_password(SERVICO_KEYRING, usuario, senha)
    print(f"\nSenha gravada no Windows para '{usuario}'.")


# =============================================================================
# 4. NAVEGADOR (Playwright)
# =============================================================================

def localizar(page, expressao: str, papel: str | None = None):
    if not expressao:
        return None
    if expressao.startswith(("css=", "xpath=")):
        return page.locator(expressao)
    if expressao.startswith("texto="):
        return page.get_by_text(expressao[6:], exact=False).first

    candidatos = []
    if papel:   # para botoes, o papel e o criterio mais confiavel
        candidatos.append(lambda: page.get_by_role(papel, name=expressao))
    candidatos += [
        lambda: page.get_by_label(expressao, exact=False),
        lambda: page.get_by_placeholder(expressao, exact=False),
        lambda: page.get_by_text(expressao, exact=False),
    ]

    for construir in candidatos:
        try:
            alvo = construir().first
            if alvo.count() > 0:
                return alvo
        except Exception:
            continue
    return page.get_by_text(expressao, exact=False).first


def esperar_streamlit(page, segundos: float = 1.5) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_PAGINA)
    except Exception:
        pass
    try:
        page.wait_for_selector("[data-testid='stStatusWidget']", state="detached",
                               timeout=20_000)
    except Exception:
        pass
    page.wait_for_timeout(int(segundos * 1000))


# (13/11) O site BAP Tools as vezes demora para desenhar a tela ("CONNECTING"
# no canto): o robo olhava 5 s depois de abrir, nao via o campo Usuario,
# concluia "ja abriu autenticado" e ficava esperando a lista de consultas na
# TELA DE LOGIN (os prints de evidencias/erro_* desde set/26 sao todos a tela
# de login) - "Nao consegui selecionar 'Clientes'" em todos. Agora espera a
# tela ficar pronta (o campo de senha OU a lista de consultas) antes de
# decidir, e confere o login de novo antes de cada relatorio.
ESPERA_TELA_PRONTA = 120_000            # ms
_JS_TELA_PRONTA = """() => !!(document.querySelector("input[type='password']")
    || document.querySelector("[data-testid='stSelectbox']"))"""


def tela_de_login(page) -> bool:
    """A tela de login esta aberta (tem campo de senha visivel)."""
    try:
        return page.locator("input[type='password']").first.is_visible()
    except Exception:
        return False


def esperar_tela_pronta(page, ms: int = ESPERA_TELA_PRONTA) -> bool:
    """Espera o Streamlit desenhar o login ou a lista de consultas."""
    try:
        page.wait_for_function(_JS_TELA_PRONTA, timeout=ms)
        page.wait_for_timeout(800)
        return True
    except Exception:
        return False


def garantir_login(page) -> None:
    """(13/11) Antes de cada relatorio: se a sessao caiu e o site voltou para
    o login, entra de novo."""
    if tela_de_login(page):
        log.warning("  O BAP Tools voltou para a tela de login: entrando de "
                    "novo...")
        fazer_login(page)


def fazer_login(page) -> None:
    if not esperar_tela_pronta(page):
        log.warning("O BAP Tools nao desenhou a tela em %d s (nem login nem "
                    "lista de consultas). Tentando assim mesmo.",
                    ESPERA_TELA_PRONTA // 1000)
    campo = localizar(page, SELETORES["campo_usuario"])
    if not tela_de_login(page) or campo is None or campo.count() == 0:
        log.info("Tela de login nao encontrada - o BAP Tools ja abriu autenticado.")
        return

    log.info("Login no BAP Tools como '%s'...", USUARIO_BAP)
    campo.fill(USUARIO_BAP)
    localizar(page, SELETORES["campo_senha"]).fill(obter_senha())
    localizar(page, SELETORES["botao_entrar"], papel="button").click()
    esperar_streamlit(page, 2.5)
    # (13/11) a lista de consultas tambem pode demorar a aparecer
    try:
        page.wait_for_selector("[data-testid='stSelectbox']",
                               timeout=ESPERA_TELA_PRONTA)
    except Exception:
        pass

    confirmacao = SELETORES.get("confirmacao_login")
    if confirmacao:
        try:
            localizar(page, confirmacao).wait_for(timeout=30_000)
            log.info("Login confirmado.")
            return
        except Exception:
            pass

    erro = localizar(page, SELETORES.get("erro_login", ""))
    if erro is not None and erro.count() > 0:
        raise RuntimeError(f"Falha no login: {erro.first.inner_text()[:200]}")
    log.warning("Login nao confirmado pelo seletor configurado. Seguindo.")


def caixa_de_consulta(page):
    """O selectbox 'Selecione a consulta' do BAP Tools."""
    expressao = SELETORES.get("lista_relatorios", "")
    if expressao:
        alvo = localizar(page, expressao)
        if alvo is not None and alvo.count() > 0:
            return alvo.first
    return page.locator("[data-testid='stSelectbox']").first


def abrir_lista_consultas(page):
    """Abre o dropdown e devolve o locator das opcoes."""
    caixa_de_consulta(page).click()
    page.wait_for_timeout(700)
    return page.get_by_role("option")


def listar_consultas(page) -> list[str]:
    opcoes = abrir_lista_consultas(page)
    textos = []
    for indice in range(opcoes.count()):
        try:
            texto = opcoes.nth(indice).inner_text().strip()
            if texto:
                textos.append(texto)
        except Exception:
            continue
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return textos


def melhor_opcao(textos: list[str], desejado: str) -> int | None:
    """
    Acha a opcao correspondente ignorando acento, caixa e pontuacao.
    'Tabela precos' casa com 'Tabela preços'; 'Movimento BAP' casa com
    'Movimentos BAP Protheus'.
    """
    import difflib

    alvo = normalizar(desejado)
    normalizados = [normalizar(t) for t in textos]

    for indice, texto in enumerate(normalizados):
        if texto == alvo:
            return indice
    for indice, texto in enumerate(normalizados):
        if texto.startswith(alvo) or alvo.startswith(texto):
            return indice
    for indice, texto in enumerate(normalizados):
        if alvo in texto or texto in alvo:
            return indice

    proximos = difflib.get_close_matches(alvo, normalizados, n=1, cutoff=0.75)
    if proximos:
        return normalizados.index(proximos[0])

    # ultimo criterio: maior numero de palavras em comum
    palavras_alvo = set(alvo.split())
    pontuacoes = [(len(palavras_alvo & set(t.split())), i)
                  for i, t in enumerate(normalizados)]
    melhor, indice = max(pontuacoes, default=(0, None))
    return indice if melhor >= 2 else None


def limpar_busca(page, caixa) -> None:
    """Apaga o que foi digitado no campo de busca do selectbox."""
    try:
        campo = caixa.locator("input").first
        campo.press("Control+a")
        campo.press("Backspace")
        page.wait_for_timeout(300)
    except Exception:
        pass


def selecionar_relatorio(page, nome_site: str) -> None:
    """
    Streamlit selectbox (BaseWeb) nao e um <select> nativo. A forma confiavel e
    abrir a lista, LER as opcoes e clicar na que corresponde - sem digitar.
    Digitar filtra a lista e, se o texto nao bater exatamente, o componente
    responde 'No results' e nada pode ser selecionado.
    """
    # (13/11) a lista pode demorar a aparecer (site lento)
    try:
        page.wait_for_selector("[data-testid='stSelectbox']",
                               state="visible", timeout=ESPERA_TELA_PRONTA)
    except Exception:
        pass
    caixa = caixa_de_consulta(page)

    try:
        caixa.select_option(label=nome_site)
        esperar_streamlit(page)
        return
    except Exception:
        pass

    vistos: list[str] = []

    for tentativa in (1, 2):
        try:
            opcoes = abrir_lista_consultas(page)
            textos = []
            for indice in range(opcoes.count()):
                try:
                    textos.append(opcoes.nth(indice).inner_text().strip())
                except Exception:
                    textos.append("")

            uteis = [t for t in textos if t and t.lower() != "no results"]
            if uteis:
                vistos = uteis

            if not uteis:
                limpar_busca(page, caixa)
                continue

            indice = melhor_opcao(textos, nome_site)
            if indice is not None:
                escolhido = textos[indice]
                opcoes.nth(indice).click(timeout=10_000)
                esperar_streamlit(page)
                if normalizar(escolhido) != normalizar(nome_site):
                    log.info("  (consulta '%s' casada com a opcao '%s')",
                             nome_site, escolhido)
                return

            if tentativa == 1:
                # a opcao pode estar fora da area visivel: filtra pela 1a palavra
                primeira = re.split(r"[\s/.]+", nome_site.strip())[0]
                try:
                    caixa.locator("input").first.type(primeira, delay=30)
                    page.wait_for_timeout(700)
                except Exception:
                    pass
                continue
        except Exception as erro:
            log.debug("Tentativa %d de selecionar falhou: %s", tentativa, erro)
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

    try:
        page.keyboard.press("Escape")
    except Exception:
        pass

    raise RuntimeError(
        f"Nao consegui selecionar '{nome_site}'.\n"
        f"  Opcoes que a tela oferece: {vistos or '(nenhuma lida)'}\n"
        f"  Ajuste 'nome_site' no bloco RELATORIOS para um desses textos."
    )


def preencher_filtros(page, filtros: dict) -> None:
    for rotulo, valor in (filtros or {}).items():
        texto = valor.strftime("%d/%m/%Y") if isinstance(valor, (datetime, date)) else valor
        try:
            campo = page.get_by_label(rotulo, exact=False).first
            campo.click()
            try:
                campo.fill(str(texto))
            except Exception:
                campo.press("Control+a")
                campo.type(str(texto), delay=30)
            campo.press("Enter")
            esperar_streamlit(page)
        except Exception as erro:
            log.warning("Filtro '%s' nao preenchido: %s", rotulo, erro)


def clicar_consultar(page) -> None:
    expressao = SELETORES.get("botao_gerar", "")
    if not expressao:
        return
    localizar(page, expressao, papel="button").click()
    log.info("  'Executar Consulta' acionado, aguardando a geracao...")
    esperar_streamlit(page, 2.5)

    confirmacao = SELETORES.get("consulta_ok", "")
    if confirmacao:
        try:
            page.get_by_text(confirmacao, exact=False).first.wait_for(
                timeout=TIMEOUT_DOWNLOAD
            )
            log.info("  consulta concluida.")
        except Exception:
            log.warning("  nao vi a mensagem de sucesso; seguindo mesmo assim.")


def capturar_do_downloads(desde: float) -> Path | None:
    """Plano B: o arquivo caiu na pasta Downloads do usuario."""
    if not DOWNLOADS_DO_USUARIO.is_dir():
        return None
    for _ in range(30):
        candidatos = [
            p for p in DOWNLOADS_DO_USUARIO.iterdir()
            if p.is_file() and p.suffix.lower() in EXTENSOES_ACEITAS
            and p.stat().st_mtime >= desde
            and not p.name.endswith((".crdownload", ".tmp", ".part"))
        ]
        if candidatos:
            return max(candidatos, key=lambda p: p.stat().st_mtime)
        time.sleep(2)
    return None


# A tabela do Streamlit tem uma barra de ferramentas propria, com um icone de
# download que exporta CSV. Ele NAO e o botao "Baixar Excel" do BAP Tools:
# clicar nele traz outro arquivo (com coluna de indice) ou so ordena a tabela.
# Nada dentro deste seletor pode ser aceito como botao de download.
BARRA_DA_TABELA = "[data-testid='stElementToolbar']"


def _botao_utilizavel(alvo) -> bool:
    """Existe, esta visivel e NAO faz parte da barra de ferramentas da tabela."""
    try:
        if alvo.count() == 0 or not alvo.first.is_visible():
            return False
        return bool(alvo.first.evaluate(
            "el => !el.closest(\"[data-testid='stElementToolbar']\")"))
    except Exception:
        return False


def esperar_botao_download(page):
    """
    Espera o botao REAL de download (st.download_button). So depois de esgotar
    o tempo e que tenta alternativas - e mesmo assim nunca a barra da tabela.
    """
    verdadeiro = page.locator(
        "[data-testid='stDownloadButton'] button, "
        "[data-testid='stDownloadButton'] a"
    )

    limite = time.time() + TIMEOUT_DOWNLOAD / 1000
    ultimo_aviso = 0.0
    while time.time() < limite:
        if _botao_utilizavel(verdadeiro):
            return verdadeiro.first
        if time.time() - ultimo_aviso > 30:
            ultimo_aviso = time.time()
            log.info("  ...aguardando o botao de download aparecer")
        page.wait_for_timeout(1500)

    log.warning("  O botao padrao do Streamlit nao apareceu; tentando alternativas.")

    alternativas = []
    expressao = SELETORES.get("botao_download", "")
    if expressao:
        alternativas.append(page.get_by_role("button", name=expressao, exact=False))
    alternativas.append(page.get_by_role(
        "button", name=re.compile(r"baixar\s+excel|baixar\s+arquivo", re.I)))
    alternativas.append(page.locator("a[download]"))

    for alvo in alternativas:
        if _botao_utilizavel(alvo):
            return alvo.first

    raise RuntimeError(
        "O botao de download nao apareceu depois da consulta. "
        "Rode --descobrir, gere um relatorio na mao e copie o texto do botao "
        "para SELETORES['botao_download']."
    )


SCRIPT_BAIXAR_POR_LINK = """
async () => {
  const alvo = document.querySelector(
    '[data-testid="stDownloadButton"] a[href], a[download][href]'
  );
  if (!alvo) return null;
  const resposta = await fetch(alvo.href);
  const buffer = await resposta.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binario = '';
  const passo = 8192;
  for (let i = 0; i < bytes.length; i += passo) {
    binario += String.fromCharCode.apply(null, bytes.subarray(i, i + passo));
  }
  return { nome: alvo.getAttribute('download') || 'download.xlsx',
           b64: btoa(binario) };
}
"""


def clicar_e_baixar(page, botao):
    """
    O clique simples estava expirando: o Playwright espera o elemento ficar
    'acionavel' (visivel, estavel, habilitado, sem nada por cima) e desiste.
    Aqui tentamos, em ordem, do mais educado ao mais direto.
    """
    try:
        botao.scroll_into_view_if_needed(timeout=10_000)
    except Exception:
        pass

    # A primeira tentativa espera o tempo cheio (o arquivo pode demorar a ser
    # preparado); as seguintes sao rapidas, para nao arrastar a execucao.
    tentativas = [
        ("clique normal", lambda: botao.click(timeout=30_000), TIMEOUT_DOWNLOAD),
        ("clique forcado", lambda: botao.click(timeout=20_000, force=True), 60_000),
        ("evento de clique", lambda: botao.dispatch_event("click"), 45_000),
        ("clique via JavaScript", lambda: botao.evaluate("el => el.click()"), 45_000),
    ]

    for descricao, acao, espera in tentativas:
        try:
            with page.expect_download(timeout=espera) as info:
                acao()
            log.info("  download iniciado (%s)", descricao)
            return info.value
        except Exception as erro:
            log.warning("  %s nao gerou download (%s)", descricao, type(erro).__name__)
    return None


def baixar_arquivo(page, cfg: dict) -> Path:
    """Baixa para a pasta temporaria local. O envio a nuvem e feito depois."""
    botao = esperar_botao_download(page)

    try:
        rotulo = botao.inner_text(timeout=5_000).strip().replace("\n", " ")
        log.info("  botao de download encontrado: %r", rotulo[:60])
    except Exception:
        pass

    marca = time.time() - 5
    destino = None

    # 1) caminho normal: clique + evento de download do navegador
    download = clicar_e_baixar(page, botao)
    if download is not None:
        sufixo = Path(download.suggested_filename).suffix or ".xlsx"
        destino = PASTA_TEMP / f"{cfg['id']}{sufixo}"
        download.save_as(destino)

    # 2) o arquivo pode ter caido na pasta Downloads do usuario
    if destino is None:
        log.warning("  Procurando o arquivo em %s...", DOWNLOADS_DO_USUARIO)
        achado = capturar_do_downloads(marca)
        if achado is not None:
            destino = PASTA_TEMP / f"{cfg['id']}{achado.suffix}"
            shutil.move(str(achado), destino)

    # 3) ultimo recurso: puxar o conteudo direto do link, dentro da pagina
    if destino is None:
        log.warning("  Tentando puxar o arquivo pelo link da propria pagina...")
        try:
            dados = page.evaluate(SCRIPT_BAIXAR_POR_LINK)
        except Exception as erro:
            dados = None
            log.debug("  leitura por link falhou: %s", erro)
        if dados:
            import base64
            sufixo = Path(dados.get("nome") or "download.xlsx").suffix or ".xlsx"
            destino = PASTA_TEMP / f"{cfg['id']}{sufixo}"
            destino.write_bytes(base64.b64decode(dados["b64"]))
            log.info("  arquivo recuperado pelo link da pagina.")

    if destino is None:
        raise RuntimeError(
            "Nao consegui obter o arquivo apos a consulta. O botao foi "
            "encontrado, mas nenhuma das formas de clique gerou download. "
            "Veja o print em evidencias e o log com --verboso."
        )

    tamanho = destino.stat().st_size
    if tamanho < 100:
        raise RuntimeError(f"Arquivo vazio ou invalido ({tamanho} bytes).")
    log.info("  Baixado (%.1f KB)", tamanho / 1024)
    return destino


def baixar_todos(relatorios: list[dict], visivel: bool) -> dict[str, Path]:
    from playwright.sync_api import sync_playwright

    arquivos: dict[str, Path] = {}

    with sync_playwright() as pw:
        navegador = pw.chromium.launch(
            headless=not visivel, slow_mo=400 if visivel else 0,
            args=["--disable-dev-shm-usage"],
        )
        contexto = navegador.new_context(accept_downloads=True,
                                         viewport={"width": 1600, "height": 950})
        contexto.set_default_timeout(TIMEOUT_PAGINA)
        page = contexto.new_page()

        try:
            log.info("Abrindo %s", URL_BAP)
            try:
                page.goto(URL_BAP, wait_until="domcontentloaded", timeout=TIMEOUT_PAGINA)
            except Exception as erro:
                raise RuntimeError(
                    f"Nao consegui abrir {URL_BAP}.\n"
                    "Esta maquina esta na rede interna / VPN da empresa? "
                    "O endereco e um IP privado e so responde de dentro da rede.\n"
                    f"Detalhe: {erro}"
                )
            esperar_streamlit(page, 2.0)
            fazer_login(page)

            for indice, cfg in enumerate(relatorios):
                nome = cfg["nome_site"]
                log.info("[%d/%d] %s  ->  aba %s",
                         indice + 1, len(relatorios), nome, cfg["aba_excel"])
                try:
                    if RECARREGAR_ENTRE_RELATORIOS and indice > 0:
                        page.goto(URL_BAP, wait_until="domcontentloaded")
                        esperar_streamlit(page, 2.0)
                    garantir_login(page)            # (13/11)
                    selecionar_relatorio(page, nome)
                    preencher_filtros(page, cfg.get("filtros"))
                    clicar_consultar(page)
                    arquivos[cfg["id"]] = baixar_arquivo(page, cfg)
                except Exception as erro:
                    evidencia = (PASTA_EVIDENCIAS /
                                 f"erro_{cfg['id']}_{datetime.now():%Y%m%d_%H%M%S}.png")
                    try:
                        page.screenshot(path=str(evidencia), full_page=True)
                        log.error("  FALHA em '%s': %s | print: %s",
                                  nome, erro, evidencia.name)
                    except Exception:
                        log.error("  FALHA em '%s': %s", nome, erro)
        finally:
            contexto.close()
            navegador.close()

    return arquivos


# =============================================================================
# 5. MODO DESCOBERTA
# =============================================================================

SCRIPT_MAPEAMENTO = """
() => {
  const visivel = (el) => { const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0; };
  const limpar = (t) => (t || '').replace(/\\s+/g, ' ').trim().slice(0, 90);
  const testid = (el) => { const c = el.closest('[data-testid]');
                           return c ? c.getAttribute('data-testid') : ''; };
  const saida = { botoes: [], entradas: [], selects: [], testids: [], opcoes: [] };

  document.querySelectorAll('button').forEach((el) => {
    if (visivel(el)) saida.botoes.push({ texto: limpar(el.innerText), testid: testid(el) });
  });

  document.querySelectorAll('input, textarea').forEach((el) => {
    if (!visivel(el)) return;
    let rotulo = '';
    if (el.id) { const lab = document.querySelector(`label[for="${el.id}"]`);
                 if (lab) rotulo = limpar(lab.innerText); }
    if (!rotulo) { const c = el.closest('[data-testid]');
                   if (c) { const lab = c.querySelector('label');
                            if (lab) rotulo = limpar(lab.innerText); } }
    saida.entradas.push({ rotulo, tipo: el.type || el.tagName.toLowerCase(),
                          placeholder: el.placeholder || '', testid: testid(el) });
  });

  document.querySelectorAll('select').forEach((el) => {
    saida.selects.push({ id: el.id || '',
      opcoes: Array.from(el.options).slice(0, 30).map((o) => limpar(o.text)) });
  });

  document.querySelectorAll('[role="option"], [role="radio"]').forEach((el) => {
    if (visivel(el) && limpar(el.innerText)) saida.opcoes.push(limpar(el.innerText));
  });

  const contagem = {};
  document.querySelectorAll('[data-testid]').forEach((el) => {
    if (!visivel(el)) return;
    const t = el.getAttribute('data-testid');
    contagem[t] = (contagem[t] || 0) + 1;
  });
  saida.testids = Object.entries(contagem)
    .filter(([t]) => /select|button|input|download|radio|multi|date|form|tab|expander|sidebar/i.test(t))
    .map(([t, n]) => `${t} (${n}x)`);

  return saida;
}
"""


PALAVRAS_ABA = [
    ("cliente", "dClientesBap", "clientes", "Relatorio_Clientes"),
    ("titulos em aberto", "ftTitulos", "titulos", "Relatorio_Titulos_em_Abertos"),
    ("estoque bap", "ftEstoqueBap", "estoque", "Relatorio_Estoque_BAP_Protheus"),
    ("moviment", "ftPedidos", "pedidos", "Relatorio_Movimentos_BAP_Protheus"),
    ("tabela preco", "ftTabelaPreco", "precos", "Relatorio_Tabela_precos"),
]


def modo_listar_consultas(visivel: bool) -> int:
    """Loga sozinho, abre a lista e imprime o bloco RELATORIOS pronto."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=not visivel,
                                       slow_mo=300 if visivel else 0)
        contexto = navegador.new_context(viewport={"width": 1600, "height": 950})
        contexto.set_default_timeout(TIMEOUT_PAGINA)
        page = contexto.new_page()
        try:
            log.info("Abrindo %s", URL_BAP)
            page.goto(URL_BAP, wait_until="domcontentloaded", timeout=TIMEOUT_PAGINA)
            esperar_streamlit(page, 2.0)
            fazer_login(page)
            opcoes = listar_consultas(page)
        finally:
            contexto.close()
            navegador.close()

    if not opcoes:
        log.error("A lista veio vazia. Confira SELETORES['lista_relatorios'].")
        return 1

    print("\n" + "=" * 78)
    print(f"  {len(opcoes)} CONSULTAS DISPONIVEIS NO BAP TOOLS")
    print("=" * 78)
    for opcao in opcoes:
        print(f'   - "{opcao}"')

    print("\n" + "=" * 78)
    print("  BLOCO RELATORIOS SUGERIDO - confira e cole no script")
    print("=" * 78)
    print("RELATORIOS = [")
    usados = set()
    for opcao in opcoes:
        chave = normalizar(opcao)
        combinacao = next(
            ((aba, ident, arq) for palavra, aba, ident, arq in PALAVRAS_ABA
             if palavra in chave and ident not in usados), None
        )
        if not combinacao:
            print(f'    # sem aba correspondente (ignorado): "{opcao}"')
            continue
        aba, ident, arquivo = combinacao
        usados.add(ident)
        print(f'    {{"id": "{ident}", "nome_site": "{opcao}",')
        print(f'     "aba_excel": "{aba}", "arquivo": "{arquivo}",')
        print('     "linha_cabecalho": 1, "filtros": {}, "colunas_ignorar": [],')
        print('     "linhas_a_mais": "limpar"},')
    print("]")

    faltando = [ident for _, _, ident, _ in PALAVRAS_ABA if ident not in usados]
    if faltando:
        print(f"\n  ATENCAO: sem consulta correspondente para: {faltando}")
    print()
    return 0


def modo_descoberta() -> None:
    from playwright.sync_api import sync_playwright

    def imprimir(mapa: dict, titulo: str) -> None:
        print("\n" + "=" * 78)
        print(f"  {titulo}")
        print("=" * 78)
        print("\n[BOTOES]  -> botao_entrar / botao_gerar (Consultar) / botao_download")
        for b in mapa["botoes"]:
            extra = f"   data-testid={b['testid']}" if b["testid"] else ""
            print(f'   - "{b["texto"]}"{extra}')
        print("\n[CAMPOS]  -> campo_usuario / campo_senha / filtros")
        for e in mapa["entradas"]:
            print(f'   - rotulo="{e["rotulo"]}"  tipo={e["tipo"]}  '
                  f'placeholder="{e["placeholder"]}"  testid={e["testid"]}')
        print("\n[LISTA DE RELATORIOS - opcoes visiveis]")
        print("   >>> COPIE O TEXTO EXATO para 'nome_site' no bloco RELATORIOS <<<")
        for o in dict.fromkeys(mapa["opcoes"]):
            print(f'   - "{o}"')
        for s in mapa["selects"]:
            print(f'   - <select id={s["id"]}> opcoes={s["opcoes"]}')
        print("\n[COMPONENTES STREAMLIT NA TELA]")
        for t in mapa["testids"]:
            print(f"   - css=[data-testid='{t.split(' ')[0]}']")

    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=False, slow_mo=200)
        contexto = navegador.new_context(accept_downloads=True,
                                         viewport={"width": 1600, "height": 950})
        page = contexto.new_page()
        page.goto(URL_BAP, wait_until="domcontentloaded", timeout=TIMEOUT_PAGINA)
        esperar_streamlit(page, 2.0)
        imprimir(page.evaluate(SCRIPT_MAPEAMENTO), "TELA INICIAL / LOGIN")

        while True:
            print("\n" + "-" * 78)
            print(" Faca a proxima etapa NA JANELA DO NAVEGADOR (logar com bap/bap,")
            print(" abrir a lista de relatorios, escolher um, Consultar...) e volte aqui.")
            if input(" ENTER = mapear a tela atual  |  s = sair: ").strip().lower() == "s":
                break
            imprimir(page.evaluate(SCRIPT_MAPEAMENTO),
                     f"TELA MAPEADA {datetime.now():%H:%M:%S}")

        contexto.close()
        navegador.close()

    print("\nCopie os valores acima para os blocos SELETORES e RELATORIOS.\n")


# =============================================================================
# 6. LEITURA DOS ARQUIVOS BAIXADOS
# =============================================================================

def detectar_separador(caminho: Path, encoding: str) -> str:
    with open(caminho, "r", encoding=encoding, errors="replace") as arq:
        amostra = arq.read(8192)
    try:
        return csv.Sniffer().sniff(amostra, delimiters=";,\t|").delimiter
    except Exception:
        return ";" if amostra.count(";") >= amostra.count(",") else ","


def ler_arquivo(caminho: Path, cfg: dict) -> pd.DataFrame:
    extensao = caminho.suffix.lower()
    if extensao in {".csv", ".txt"}:
        encoding = cfg.get("encoding", "utf-8-sig")
        separador = cfg.get("separador") or detectar_separador(caminho, encoding)
        df = pd.read_csv(caminho, sep=separador, encoding=encoding,
                         dtype=object, keep_default_na=False, na_values=[""])
    elif extensao in {".xlsx", ".xlsm"}:
        df = pd.read_excel(caminho, engine="openpyxl", dtype=object)
    elif extensao == ".xls":
        df = pd.read_excel(caminho, engine="xlrd", dtype=object)
    else:
        raise ValueError(f"Formato nao suportado: {extensao}")

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all")
    if df.empty:
        raise ValueError(f"{caminho.name} veio sem linhas.")
    log.info("  Lido: %d linhas x %d colunas", len(df), len(df.columns))
    return df


# =============================================================================
# 7. GRAVACAO - SUBSTITUI APENAS AS COLUNAS DE MESMO NOME
# =============================================================================

# RN-GER-013 (Alexandre, 26/11/2026, "1 A"): pedido de cliente fora da base de
# clientes da BAP (RAZAO_SOCIAL = "NAO LOCALIZADO NA BASE", gravada pelo robo no
# ftPedidos) e pedido interno (transferencia, filial): nao entra como demanda da
# SOLICITACAO_BAP (Gerar ID CD, Reversa, Analitico).
def pedido_fora_da_base(razao) -> bool:
    return normalizar(razao) == "nao localizado na base"


def normalizar(texto) -> str:
    if texto is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower().strip())
    return re.sub(r"\s+", " ", texto).strip()


def converter_valor(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    if hasattr(valor, "item"):
        try:
            return valor.item()
        except Exception:
            pass
    if isinstance(valor, str):
        return valor.strip()
    return valor


def ultima_linha_com_dados(ws, linha_cabecalho: int) -> int:
    """
    Ultima linha com conteudo de verdade.

    A versao ingenua (varrer de max_row para tras com ws.cell) custava DEZENAS
    DE SEGUNDOS por aba: o openpyxl CRIA a celula a cada leitura, entao varrer
    o vazio ate max_row materializava dezenas de milhares de celulas - lento e
    ainda inchava o arquivo salvo. Aqui percorremos so as celulas que existem.
    """
    celulas = getattr(ws, "_cells", None)
    if celulas is not None:
        ultima = linha_cabecalho
        for (linha, _), celula in celulas.items():
            if linha > ultima:
                valor = celula.value
                if valor is not None and str(valor).strip() != "":
                    ultima = linha
        return ultima

    # fallback (modo read_only): uma passada para frente, sem criar celulas
    ultima = linha_cabecalho
    for indice, linha in enumerate(
            ws.iter_rows(min_row=linha_cabecalho + 1, values_only=True),
            start=linha_cabecalho + 1):
        if any(v is not None and str(v).strip() != "" for v in linha):
            ultima = indice
    return ultima


def colunas_calculadas(ws, linha_cabecalho: int, amostra: int = 40) -> set[int]:
    """
    Descobre quais colunas sao CALCULADAS, olhando se as celulas de dados
    contem formula. Essas colunas nunca podem ser sobrescritas: sao elas que
    montam ID_PRODUTO, NUM_PEDIDO, chaves de relacionamento, etc.
    """
    formulas: set[int] = set()
    primeira = linha_cabecalho + 1
    ultima = min(ws.max_row, primeira + amostra - 1)
    if ultima < primeira:
        return formulas
    for linha in ws.iter_rows(min_row=primeira, max_row=ultima):
        for celula in linha:
            if isinstance(celula.value, str) and celula.value.startswith("="):
                formulas.add(celula.column)
    return formulas


# As colunas calculadas de cada aba nao mudam durante a rodada, mas eram
# descobertas de novo em cada rotina - e cada descoberta abria a TABELA_BAP
# inteira (16 MB) so para olhar 40 linhas. Numa execucao completa isso
# acontecia quatro vezes. Agora a resposta fica guardada por arquivo, e o
# arquivo so e reaberto quando muda de tamanho ou de data.
_CALCULADAS_GUARDADAS: dict[tuple, dict[str, set[int]]] = {}


def calculadas_das_abas(caminho: Path, abas: list[str]) -> dict[str, set[int]]:
    """
    {aba -> colunas com formula}, para as abas pedidas. Abre a planilha uma
    vez por rodada, nao uma vez por rotina.
    """
    caminho = Path(caminho)
    # (05/11) TABELA_BAP com fotografia valida: as abas de dados vem dela
    # (o robo anota as colunas de formula de cada aba na fotografia)
    foto = dados_bap.fotografia_para(caminho)
    try:
        st = caminho.stat()
        chave = (str(caminho.resolve()), st.st_size, int(st.st_mtime),
                 foto["carimbo"] if foto else "")
    except OSError:
        chave = (str(caminho), 0, 0, "")
    guardado = _CALCULADAS_GUARDADAS.setdefault(chave, {})
    if foto is not None and "__abas__" not in guardado:
        for aba, info in foto["abas"].items():
            guardado[aba] = set(info.get("calculadas") or [])
    faltam = [a for a in abas if a not in guardado]
    if faltam or (foto is not None and "__abas__" not in guardado):
        wb = load_workbook(caminho, read_only=True, data_only=False)
        try:
            for aba in faltam:
                guardado[aba] = (colunas_calculadas(wb[aba], 1)
                                 if aba in wb.sheetnames else set())
            guardado["__abas__"] = set(wb.sheetnames) | (
                set(foto["abas"]) if foto is not None else set())
        finally:
            wb.close()
    return guardado


def _abrir_valores(caminho):
    """
    Para LER os valores da planilha (o load_workbook(read_only=True,
    data_only=True) de sempre). (05/11) A TABELA_BAP com fotografia valida
    vem pelo leitor hibrido do xlsx_rapido: as 7 abas de dados da
    fotografia, o cadastro do .xlsx. Sem fotografia: o openpyxl, como antes.
    """
    if dados_bap.fotografia_para(caminho) is not None:
        import xlsx_rapido                          # noqa: PLC0415
        return xlsx_rapido.abrir(caminho)
    return load_workbook(caminho, read_only=True, data_only=True)


def abas_da_planilha(caminho: Path) -> set:
    """Os nomes das abas, do mesmo cache de calculadas_das_abas()."""
    guardado = calculadas_das_abas(caminho, [])
    if "__abas__" not in guardado:
        wb = load_workbook(caminho, read_only=True, data_only=False)
        try:
            guardado["__abas__"] = set(wb.sheetnames)
        finally:
            wb.close()
    return guardado["__abas__"]


def mapear_cabecalhos(ws, linha_cabecalho: int,
                      evitar: set[int] | None = None) -> dict[str, int]:
    """
    Titulo -> indice da coluna. Quando o mesmo titulo aparece duas vezes
    (acontece em ftPedidos e ftEstoqueBap, onde a coluna A e uma formula e a B
    e o dado bruto do relatorio), fica com a coluna que NAO e calculada.
    """
    evitar = evitar or set()
    mapa: dict[str, int] = {}
    for coluna in range(1, ws.max_column + 1):
        chave = normalizar(ws.cell(linha_cabecalho, coluna).value)
        if not chave:
            continue
        if chave not in mapa:
            mapa[chave] = coluna
        elif mapa[chave] in evitar and coluna not in evitar:
            mapa[chave] = coluna       # troca a formula pelo dado bruto
    return mapa


def preparar_modelo_de_linha(ws, linha_modelo: int,
                             colunas_de_dados: set[int]) -> list:
    """
    Le a linha modelo UMA vez e guarda, por coluna, o estilo e a formula a
    replicar. Antes isso era relido a cada linha nova - com dezenas de milhares
    de linhas incluidas, virava o gargalo da gravacao.
    Coluna sem estilo proprio e sem formula vira None e e pulada.
    """
    modelo = []
    for coluna in range(1, ws.max_column + 1):
        celula = ws.cell(linha_modelo, coluna)
        estilo = celula._style if celula.has_style else None
        formula = origem = None
        if coluna not in colunas_de_dados:
            valor = celula.value
            if isinstance(valor, str) and valor.startswith("="):
                formula, origem = valor, celula.coordinate
        modelo.append((estilo, formula, origem)
                      if (estilo is not None or formula is not None) else None)
    return modelo


def clonar_estilo_e_formulas(ws, linha_destino: int, modelo: list) -> None:
    """Aplica numa linha nova o modelo ja preparado."""
    for indice, item in enumerate(modelo, start=1):
        if item is None:
            continue
        estilo, formula, origem = item
        nova = ws.cell(linha_destino, indice)
        if estilo is not None:
            try:
                nova._style = copy(estilo)
            except Exception:
                pass
        if formula is not None:
            nova.value = Translator(formula, origin=origem).translate_formula(
                nova.coordinate)


def ajustar_referencias(ws, linha_cabecalho: int, ultima_linha: int) -> None:
    ultima_coluna = get_column_letter(ws.max_column)
    try:
        for tabela in list(getattr(ws, "tables", {}).values()):
            inicio = tabela.ref.split(":")[0]
            col_inicial = re.match(r"([A-Z]+)", inicio).group(1)
            tabela.ref = f"{col_inicial}{linha_cabecalho}:{ultima_coluna}{ultima_linha}"
    except Exception as erro:
        log.debug("Tabela estruturada nao ajustada: %s", erro)
    try:
        if ws.auto_filter and ws.auto_filter.ref:
            ws.auto_filter.ref = f"A{linha_cabecalho}:{ultima_coluna}{ultima_linha}"
    except Exception:
        pass


def atualizar_aba(ws, df: pd.DataFrame, cfg: dict) -> dict:
    linha_cabecalho = int(cfg.get("linha_cabecalho", 1))
    ignorar = {normalizar(c) for c in cfg.get("colunas_ignorar", [])}

    # apelidos: coluna do relatorio -> coluna da aba, quando os nomes diferem
    apelidos = {normalizar(k): normalizar(v)
                for k, v in (cfg.get("mapa_colunas") or {}).items()}

    calculadas = colunas_calculadas(ws, linha_cabecalho)
    # AS COLUNAS QUE O SCRIPT CALCULA continuam protegidas mesmo sem formula:
    # depois da primeira rodada elas guardam VALOR, e sem isto o relatorio
    # podia gravar por cima delas (o D2_FILIAL bruto em cima do D2FILIAL).
    if ws.title == "ftPedidos":
        titulos = [ws.cell(linha_cabecalho, c).value
                   for c in range(1, ws.max_column + 1)]
        calculadas |= {i for i, t in enumerate(titulos, start=1)
                       if t in COLUNAS_FTPEDIDOS_EM_PYTHON}
    cabecalhos = mapear_cabecalhos(ws, linha_cabecalho, evitar=calculadas)
    if not cabecalhos:
        raise RuntimeError(f"A aba '{ws.title}' nao tem cabecalhos na linha "
                           f"{linha_cabecalho}.")

    mapa_gravacao: dict[str, int] = {}
    nao_encontradas: list[str] = []
    protegidas: list[str] = []
    for coluna_df in df.columns:
        chave = normalizar(coluna_df)
        if chave in ignorar:
            continue
        chave = apelidos.get(chave, chave)
        if chave not in cabecalhos:
            nao_encontradas.append(str(coluna_df))
            continue
        destino = cabecalhos[chave]
        if destino in calculadas:
            # o unico par possivel para essa coluna e uma coluna de formula:
            # nao grava de jeito nenhum, senao a formula morre.
            protegidas.append(str(coluna_df))
            continue
        mapa_gravacao[coluna_df] = destino

    # coluna NOVA do relatorio (ex.: STATUS do Relatorio Clientes): entra
    # no fim do cabecalho, com o estilo do ultimo titulo, e passa a ser
    # gravada como as outras. So as que o relatorio lista em criar_colunas.
    criar = {normalizar(c) for c in cfg.get("criar_colunas") or []}
    if nao_encontradas and criar and mapa_gravacao:
        criadas = []
        for nome in [c for c in nao_encontradas if normalizar(c) in criar]:
            ultima = 0
            for c in range(1, ws.max_column + 1):
                if ws.cell(linha_cabecalho, c).value not in (None, ""):
                    ultima = c
            nova = ws.cell(linha_cabecalho, ultima + 1)
            nova.value = nome
            if ultima:
                try:
                    nova._style = copy(ws.cell(linha_cabecalho, ultima)._style)
                except Exception:
                    pass
            cabecalhos[normalizar(nome)] = ultima + 1
            mapa_gravacao[nome] = ultima + 1
            nao_encontradas.remove(nome)
            criadas.append(nome)
        if criadas:
            log.info("  coluna(s) NOVA(S) criada(s) na aba '%s': %s",
                     ws.title, ", ".join(criadas))

    if not mapa_gravacao:
        raise RuntimeError(
            f"Nenhuma coluna do relatorio bate com os cabecalhos da aba '{ws.title}'.\n"
            f"  Relatorio: {list(df.columns)[:15]}\n"
            f"  Aba      : {[ws.cell(linha_cabecalho, i).value for i in range(1, ws.max_column + 1)][:15]}"
        )

    colunas_de_dados = set(mapa_gravacao.values())
    preservadas = [ws.cell(linha_cabecalho, indice).value
                   for indice in cabecalhos.values() if indice not in colunas_de_dados]

    primeira_linha = linha_cabecalho + 1
    ultima_existente = ultima_linha_com_dados(ws, linha_cabecalho)
    linha_modelo = ultima_existente if ultima_existente >= primeira_linha else None
    modelo_linha = (preparar_modelo_de_linha(ws, linha_modelo, colunas_de_dados)
                    if linha_modelo else None)

    resumo = {
        "aba": ws.title,
        "colunas_atualizadas": list(mapa_gravacao.keys()),
        "colunas_preservadas": [c for c in preservadas if c],
        "colunas_sem_par": nao_encontradas,
        "colunas_protegidas": protegidas,
        "linhas_antes": max(ultima_existente - linha_cabecalho, 0),
        "linhas_atualizadas": 0,
        "linhas_incluidas": 0,
        "linhas_limpas": 0,
    }

    for deslocamento, (_, registro) in enumerate(df.iterrows()):
        linha_alvo = primeira_linha + deslocamento
        if linha_alvo > ultima_existente:
            if modelo_linha is not None:
                clonar_estilo_e_formulas(ws, linha_alvo, modelo_linha)
            resumo["linhas_incluidas"] += 1
        else:
            resumo["linhas_atualizadas"] += 1
        for coluna_df, coluna_excel in mapa_gravacao.items():
            ws.cell(linha_alvo, coluna_excel).value = converter_valor(registro[coluna_df])

    ultima_linha_dados = primeira_linha + len(df) - 1
    excedentes = list(range(ultima_linha_dados + 1, ultima_existente + 1))
    politica = cfg.get("linhas_a_mais", "limpar")

    if excedentes and politica == "limpar":
        for linha in excedentes:
            for coluna_excel in colunas_de_dados:
                ws.cell(linha, coluna_excel).value = None
        resumo["linhas_limpas"] = len(excedentes)
    elif excedentes and politica == "excluir":
        ws.delete_rows(excedentes[0], len(excedentes))
        resumo["linhas_limpas"] = len(excedentes)
        log.warning("  %d linhas excluidas da aba '%s'.", len(excedentes), ws.title)

    ultima_linha_final = (ultima_linha_dados if politica == "excluir"
                          else max(ultima_linha_dados, ultima_existente))
    ajustar_referencias(ws, linha_cabecalho, ultima_linha_final)
    resumo["linhas_depois"] = ultima_linha_final - linha_cabecalho
    return resumo


# =============================================================================
# 7b. AS COLUNAS CALCULADAS DO ftPedidos, EM PYTHON
# =============================================================================
#
# ESTAS 22 COLUNAS ERAM FORMULAS - e as que somam ou contam olhavam so ate a
# linha 11.000 ($S$2:$S$11000). A aba passou disso em setembro/2026: toda
# venda depois da linha 11.000 ficava sem STATUS VENDA, sem DATA_DEV e fora
# do % ATENDIDO e da DEMANDA_ANTERIOR. E piorava um pouco a cada dia.
#
# Agora o script calcula cada uma aqui, com a MESMA regra da formula, e grava
# o VALOR. Sem teto de linhas, e o Excel deixa de refazer milhares de
# COUNTIFS em cima de 11 mil linhas a cada recalculo. Quem le o arquivo sem
# o Excel (Power BI, os programas BAP) ja encontra o numero pronto.
#
# A regra de cada coluna esta escrita ao lado, igual a formula antiga - e o
# teste do script confere este calculo contra os valores que o proprio Excel
# tinha gravado, linha por linha.
COLUNAS_FTPEDIDOS_EM_PYTHON = [
    "D2FILIAL",            # ="4" & D2_FILIAL
    "DT_PEDIDO",           # DATA_PEDIDO, ou D2_EMISSAO quando vazia
    "DATA_NF",             # D2_EMISSAO em DEV, TRF e em quem tem pedido
    "DATA_DEV",            # a ultima devolucao daquela nota (so VND)
    "NUM_PEDIDO",          # D2_PEDIDO, ou D2_DOC quando vazio
    "NUM_NF",              # D2_DOC quando ha pedido
    "VALOR TOTAL",         # D2_QUANT x PRECO_VENDA
    "ESTOQUE_PRODUTO",     # B2_QATU da filial+produto no ftEstoqueBap
    "% ATENDIDO",          # atendido / pedido do mesmo pedido (so VEA)
    "ID_PRODUTO",          # do ProdutosBAP, pelo codigo
    "RAZÃO_SOCIAL",        # do dClientesBap, pelo codigo do cliente
    "STATUS VENDA",        # CONCLUIDO / DEVOLUCAO TOTAL / PARCIAL (so VND)
    "CHAVE_FIL_DOC",       # filial|numero da nota
    "CHAVE_FIL_PED",       # filial|numero do pedido
    "DATA_NF_NUM",         # DATA_NF como numero de data do Excel
    "CHAVE_PED_CLI",       # D2FILIAL|cliente|NUM_PEDIDO
    "QTD_ATENDIDA",        # o que o estoque cobre (so VEA)
    "DT_PED_NUM",          # DT_PEDIDO como numero de data (so VEA)
    "CHAVE_FIL_PROD",      # filial|produto (so VEA)
    "ORDEM_FIFO",          # data, pedido e linha - quem chegou primeiro
    "DEMANDA_ANTERIOR",    # o que os pedidos mais antigos ja pedem
    "ESTOQUE_DISPONIVEL",  # estoque menos a demanda anterior
]
# VAZIO_XL, _EPOCA_XL e os _xl_* (como o Excel transforma valor) moram
# no dados_bap desde 05/11 - importados no topo, mesmo nome.


def _indice_da_busca(ws, coluna_chave: str, coluna_valor: str,
                     chave_calculada=None) -> dict:
    """
    XLOOKUP(x, aba!CHAVE:CHAVE, aba!VALOR:VALOR, , 0): o PRIMEIRO de cima
    para baixo. Celula vazia devolvida vale 0, como no Excel.
    """
    cab = [c.value for c in ws[1]]
    try:
        i_chave = cab.index(coluna_chave) if chave_calculada is None else None
        i_valor = cab.index(coluna_valor)
    except ValueError:
        return {}
    indice = {}
    for linha in ws.iter_rows(min_row=2, values_only=True):
        chave = (chave_calculada(linha, cab) if chave_calculada
                 else linha[i_chave])
        k = _xl_chave(chave)
        if k is None or k in indice:
            continue
        valor = linha[i_valor] if i_valor < len(linha) else None
        indice[k] = 0 if valor is None else valor
    return indice


def calcular_colunas_do_ftpedidos(wb, limite_linha: int | None = None) -> dict:
    """
    Recalcula e grava as colunas de COLUNAS_FTPEDIDOS_EM_PYTHON.

    `limite_linha` so existe para o teste: imita o teto antigo das formulas
    ($2:$11000) e prova que o calculo daqui bate com o que o Excel gravava.
    Na rotina ele fica None - sem teto.
    """
    if "ftPedidos" not in wb.sheetnames:
        return {"linhas": 0}
    ws = wb["ftPedidos"]
    cab = [c.value for c in ws[1]]

    def col(nome):
        # a primeira coluna com esse titulo EXATO - D2FILIAL e D2_FILIAL
        # sao colunas diferentes, e a ordem importa
        return cab.index(nome) if nome in cab else None

    faltam = [n for n in COLUNAS_FTPEDIDOS_EM_PYTHON if col(n) is None]
    brutas = ["D2_FILIAL", "D2_CLIENTE", "D2_EMISSAO", "D2_DOC", "D2_COD",
              "D2_PEDIDO", "PRECO_VENDA", "D2_QUANT", "TIPO", "DATA_PEDIDO"]
    faltam_brutas = [n for n in brutas if col(n) is None]
    if faltam_brutas:
        log.warning("ftPedidos sem as colunas %s - colunas calculadas nao "
                    "foram refeitas.", ", ".join(faltam_brutas))
        return {"linhas": 0, "faltam": faltam_brutas}

    i = {n: col(n) for n in brutas}

    # ---- as tabelas de busca ---------------------------------------------
    estoque = {}
    if "ftEstoqueBap" in wb.sheetnames:
        # a chave de la (coluna C) tambem e formula: =CONCAT(D, F)
        def chave_estoque(linha, cab_e):
            try:
                return (_xl_texto(linha[cab_e.index("B2_FILIAL_ORIGINAL")])
                        + _xl_texto(linha[cab_e.index("B2_COD")]))
            except ValueError:
                return None
        estoque = _indice_da_busca(wb["ftEstoqueBap"], None, "B2_QATU",
                                   chave_calculada=chave_estoque)
    produtos = (_indice_da_busca(wb["ProdutosBAP"], "Cód. Produto",
                                 "ID_PRODUTO")
                if "ProdutosBAP" in wb.sheetnames else {})
    clientes = (_indice_da_busca(wb["dClientesBap"], "A1_COD", "A1_NOME")
                if "dClientesBap" in wb.sheetnames else {})

    # ---- 1a passada: o que so depende da propria linha -------------------
    linhas = []
    for n_linha, celulas in enumerate(
            ws.iter_rows(min_row=2, max_col=len(cab), values_only=True),
            start=2):
        v = {n: (celulas[k] if k < len(celulas) else None)
             for n, k in i.items()}
        if all(_xl_vazio(x) for x in v.values()):
            linhas.append(None)             # linha vazia: limpa o calculo
            continue
        tipo = _xl_texto(v["TIPO"]).upper()
        r = {"_linha": n_linha, "_tipo": tipo, "_q": v["D2_QUANT"]}
        r["D2FILIAL"] = "4" + _xl_texto(v["D2_FILIAL"])
        r["DT_PEDIDO"] = (v["DATA_PEDIDO"] if not _xl_vazio(v["DATA_PEDIDO"])
                          else v["D2_EMISSAO"])
        if tipo in ("DEV", "TRF") or not _xl_vazio(v["DATA_PEDIDO"]):
            r["DATA_NF"] = v["D2_EMISSAO"]
        else:
            r["DATA_NF"] = VAZIO_XL
        tem_pedido = not _xl_vazio(v["D2_PEDIDO"])
        r["NUM_PEDIDO"] = v["D2_PEDIDO"] if tem_pedido else v["D2_DOC"]
        r["NUM_NF"] = v["D2_DOC"] if tem_pedido else VAZIO_XL
        r["VALOR TOTAL"] = _xl_numero(v["D2_QUANT"]) * _xl_numero(
            v["PRECO_VENDA"])
        r["ESTOQUE_PRODUTO"] = estoque.get(
            _xl_chave(_xl_texto(v["D2_FILIAL"]) + _xl_texto(v["D2_COD"])), 0)
        r["ID_PRODUTO"] = produtos.get(_xl_chave(v["D2_COD"]), VAZIO_XL)
        r["RAZÃO_SOCIAL"] = clientes.get(_xl_chave(v["D2_CLIENTE"]),
                                         "NÃO LOCALIZADO NA BASE")
        doc = _xl_value(v["D2_DOC"])
        ped = _xl_value(v["D2_PEDIDO"])
        filial = _xl_trim(v["D2_FILIAL"])
        r["CHAVE_FIL_DOC"] = f"{filial}|{_xl_texto(doc if doc is not None else 0)}"
        r["CHAVE_FIL_PED"] = f"{filial}|{_xl_texto(ped if ped is not None else 0)}"
        r["DATA_NF_NUM"] = _xl_serial(r["DATA_NF"])
        r["CHAVE_PED_CLI"] = (f"{r['D2FILIAL']}|{_xl_texto(v['D2_CLIENTE'])}"
                              f"|{_xl_texto(r['NUM_PEDIDO'])}")
        if tipo == "VEA":
            r["DT_PED_NUM"] = _xl_serial(r["DT_PEDIDO"])
            r["CHAVE_FIL_PROD"] = f"{filial}|{_xl_trim(v['D2_COD'])}"
            num = _xl_value(_xl_trim(r["NUM_PEDIDO"]))
            r["ORDEM_FIFO"] = (r["DT_PED_NUM"] * 10000000000
                               + min(num if num is not None else 0, 99999)
                               * 100000 + n_linha)
        else:
            r["DT_PED_NUM"] = 0
            r["CHAVE_FIL_PROD"] = VAZIO_XL
            r["ORDEM_FIFO"] = VAZIO_XL
        linhas.append(r)

    def dentro(r):
        """A linha entra nas somas? (so o teste imita o teto antigo)"""
        return limite_linha is None or r["_linha"] <= limite_linha

    validas = [r for r in linhas if r is not None]

    # ---- DEMANDA_ANTERIOR e ESTOQUE_DISPONIVEL: fila por filial+produto --
    # SUMIFS(D2_QUANT, TIPO "VEA", mesma CHAVE_FIL_PROD, ORDEM_FIFO < esta)
    fila = defaultdict(list)
    for r in validas:
        if r["_tipo"] == "VEA" and dentro(r):
            fila[r["CHAVE_FIL_PROD"].lower()].append(
                (r["ORDEM_FIFO"], _xl_numero(r["_q"])))
    acumulado = {}
    for chave, itens in fila.items():
        itens.sort(key=lambda x: x[0])
        # somas[k] = o que os k primeiros da fila pedem, ja somado
        ordens, somas = [], [0.0]
        for ordem, qtd in itens:
            ordens.append(ordem)
            somas.append(somas[-1] + qtd)
        acumulado[chave] = (ordens, somas)

    for r in validas:
        if r["_tipo"] != "VEA":
            r["DEMANDA_ANTERIOR"] = VAZIO_XL
            r["ESTOQUE_DISPONIVEL"] = VAZIO_XL
            r["QTD_ATENDIDA"] = 0
            continue
        ordens, somas = acumulado.get(r["CHAVE_FIL_PROD"].lower(),
                                      ([], [0.0]))
        # "<" estrito, como no SUMIFS: o proprio pedido nao entra
        anterior = somas[bisect_left(ordens, r["ORDEM_FIFO"])]
        r["DEMANDA_ANTERIOR"] = anterior
        r["ESTOQUE_DISPONIVEL"] = max(0.0, _xl_numero(r["ESTOQUE_PRODUTO"])
                                      - anterior)
        r["QTD_ATENDIDA"] = min(_xl_numero(r["_q"]), r["ESTOQUE_DISPONIVEL"])

    # ---- as somas por chave ----------------------------------------------
    atend_ped = defaultdict(float)       # % ATENDIDO: por CHAVE_PED_CLI
    qtd_ped = defaultdict(float)
    dev_qtd = defaultdict(int)           # devolucoes por CHAVE_FIL_PED
    dev_valor = defaultdict(float)
    dev_data = {}
    vnd_valor = defaultdict(float)       # vendas por CHAVE_FIL_DOC
    for r in validas:
        if not dentro(r):
            continue
        if r["_tipo"] == "VEA":
            atend_ped[r["CHAVE_PED_CLI"].lower()] += _xl_numero(
                r["QTD_ATENDIDA"])
            qtd_ped[r["CHAVE_PED_CLI"].lower()] += _xl_numero(r["_q"])
        elif r["_tipo"] == "DEV":
            k = r["CHAVE_FIL_PED"].lower()
            dev_qtd[k] += 1
            dev_valor[k] += r["VALOR TOTAL"]
            serial = _xl_numero(r["DATA_NF_NUM"])
            if k not in dev_data or serial > dev_data[k]:
                dev_data[k] = serial
        elif r["_tipo"] == "VND":
            vnd_valor[r["CHAVE_FIL_DOC"].lower()] += r["VALOR TOTAL"]

    for r in validas:
        if r["_tipo"] == "VEA":
            pedido = qtd_ped.get(r["CHAVE_PED_CLI"].lower(), 0.0)
            r["% ATENDIDO"] = (atend_ped[r["CHAVE_PED_CLI"].lower()] / pedido
                               if pedido else VAZIO_XL)
        else:
            r["% ATENDIDO"] = VAZIO_XL
        if r["_tipo"] == "VND":
            k = r["CHAVE_FIL_DOC"].lower()
            data = dev_data.get(k, 0)
            r["DATA_DEV"] = data if data else VAZIO_XL
            if not dev_qtd.get(k):
                r["STATUS VENDA"] = "CONCLUIDO"
            elif round(vnd_valor.get(k, 0.0) + dev_valor.get(k, 0.0), 2) == 0:
                r["STATUS VENDA"] = "DEVOLUÇÃO TOTAL"
            else:
                r["STATUS VENDA"] = "DEVOLUÇÃO PARCIAL"
        else:
            r["DATA_DEV"] = VAZIO_XL
            r["STATUS VENDA"] = VAZIO_XL

    # ---- grava ------------------------------------------------------------
    destino = {n: col(n) + 1 for n in COLUNAS_FTPEDIDOS_EM_PYTHON
               if col(n) is not None}
    gravadas = 0
    for deslocamento, r in enumerate(linhas):
        n_linha = 2 + deslocamento
        for nome, coluna in destino.items():
            ws.cell(n_linha, coluna).value = (None if r is None
                                               else _xl_limpo(r.get(nome)))
        if r is not None:
            gravadas += 1
    return {"linhas": gravadas, "colunas": len(destino),
            "colunas_faltando": faltam}


def derivar_colunas_clientes(df: pd.DataFrame, ws,
                             linha_cabecalho: int = 1) -> pd.DataFrame:
    """
    O Relatorio Clientes do BAP Tools (OUT/2026) trocou A1_MSBLQL e
    A1_FILIAL pela coluna STATUS (ATIVO/INATIVO). Quem le a dClientesBap
    pelas colunas antigas (Power BI, programas BAP) continua certo:
        A1_MSBLQL = "1" quando STATUS = INATIVO, "2" quando ATIVO
        A1_FILIAL = a filial mais comum que ja esta na aba
    So preenche o que o relatorio NAO trouxe - se um dia a coluna voltar,
    vale a do relatorio.
    """
    colunas = {normalizar(c): c for c in df.columns}
    st = colunas.get(normalizar("STATUS"))
    if st is None:
        return df
    df = df.copy()
    if normalizar("A1_MSBLQL") not in colunas:
        df["A1_MSBLQL"] = [
            "1" if normalizar(v) == "inativo" else
            ("2" if normalizar(v) == "ativo" else "")
            for v in df[st]]
    if normalizar("A1_FILIAL") not in colunas:
        cab = mapear_cabecalhos(ws, linha_cabecalho)
        j = cab.get(normalizar("A1_FILIAL"))
        if j:
            cont = Counter()
            for linha in range(linha_cabecalho + 1, ws.max_row + 1):
                v = ws.cell(linha, j).value
                if v not in (None, "") and str(v).strip():
                    cont[v] += 1
            if cont:
                df["A1_FILIAL"] = cont.most_common(1)[0][0]
    return df


def gravar_planilha(caminho_local: Path, dados: dict[str, pd.DataFrame],
                    configs: dict[str, dict],
                    estrutura: dict | None = None) -> list[dict]:
    """
    A gravacao da rodada COMPLETA: abre a planilha, grava (gravar_no_livro)
    e salva. `estrutura` (05/11): se vier um dict, recebe as formulas, os
    formatos de data e as colunas calculadas das abas de dados, tirados do
    livro ANTES de salvar - e o que a fotografia guarda para a rodada
    rapida montar as abas em memoria.
    """
    manter_vba = caminho_local.suffix.lower() == ".xlsm"
    wb = load_workbook(caminho_local, keep_vba=manter_vba, data_only=False)
    try:
        resumos = gravar_no_livro(wb, dados, configs)
        if estrutura is not None:
            try:
                estrutura.update(dados_bap.estrutura_do_livro(wb))
            except Exception as erro:                   # noqa: BLE001
                log.warning("Nao consegui anotar a estrutura para a "
                            "fotografia: %s", erro)
                estrutura.clear()
        # O openpyxl grava a formula mas descarta o valor calculado dela. Este
        # interruptor manda o Excel refazer TODAS as contas ao abrir - e a
        # garantia minima quando nao da para recalcular aqui mesmo.
        try:
            wb.calculation.fullCalcOnLoad = True
        except Exception:
            pass
        wb.save(caminho_local)
    finally:
        wb.close()

    conferencia = load_workbook(caminho_local, read_only=True)
    conferencia.close()
    return resumos


def gravar_no_livro(wb, dados: dict[str, pd.DataFrame],
                    configs: dict[str, dict]) -> list[dict]:
    """
    Grava os relatorios nas abas de um livro do openpyxl ja aberto (com
    data_only=False) - a planilha de verdade na rodada completa, o livro em
    memoria da fotografia na rapida. Nao salva.
    """
    resumos: list[dict] = []
    for identificador, df in dados.items():
        cfg = configs[identificador]
        aba = cfg["aba_excel"]
        if aba not in wb.sheetnames and cfg.get("criar_aba"):
            # (14/10) aba nova (ex.: ftNCC): nasce no fim, com o
            # cabecalho do relatorio - nao mexe nas outras abas
            ws_nova = wb.create_sheet(aba)
            lc = int(cfg.get("linha_cabecalho", 1))
            for j, nome_col in enumerate(df.columns, start=1):
                ws_nova.cell(lc, j).value = str(nome_col)
            log.info("Aba '%s' criada em %s.", aba, NOME_PLANILHA)
        if aba not in wb.sheetnames:
            raise RuntimeError(f"A aba '{aba}' nao existe em {NOME_PLANILHA}.\n"
                               f"Abas encontradas: {wb.sheetnames}")

        log.info("Gravando na aba '%s'...", aba)
        if cfg.get("derivar") == "clientes":
            df = derivar_colunas_clientes(df, wb[aba],
                                          int(cfg.get("linha_cabecalho", 1)))
        resumo = atualizar_aba(wb[aba], df, cfg)
        resumos.append(resumo)
        log.info("  colunas substituidas: %s",
                 ", ".join(resumo["colunas_atualizadas"]) or "-")
        log.info("  colunas preservadas : %s",
                 ", ".join(str(c) for c in resumo["colunas_preservadas"]) or "-")
        if resumo.get("colunas_protegidas"):
            log.info("  colunas CALCULADAS protegidas (nao gravadas): %s",
                     ", ".join(resumo["colunas_protegidas"]))
        if resumo["colunas_sem_par"]:
            log.warning("  colunas do relatorio SEM par na aba (ignoradas): %s",
                        ", ".join(resumo["colunas_sem_par"]))
        log.info("  linhas: %d atualizadas, %d incluidas, %d limpas (%d -> %d)",
                 resumo["linhas_atualizadas"], resumo["linhas_incluidas"],
                 resumo["linhas_limpas"], resumo["linhas_antes"],
                 resumo["linhas_depois"])
    # as colunas calculadas do ftPedidos, refeitas aqui com o valor -
    # sem o teto de 11.000 linhas das formulas antigas
    if "ftPedidos" in wb.sheetnames:
        calculo = calcular_colunas_do_ftpedidos(wb)
        log.info("ftPedidos: %d coluna(s) calculada(s) em Python, "
                 "%d linha(s)", calculo.get("colunas", 0),
                 calculo.get("linhas", 0))
        if calculo.get("colunas_faltando"):
            log.warning("  colunas que nao existem na aba (puladas): %s",
                        ", ".join(calculo["colunas_faltando"]))
    return resumos


# =============================================================================
# 8. ORQUESTRACAO
# =============================================================================

# =============================================================================
# 8b. SOLICITACAO DE COLETA - a medida DAX reescrita em Python
# =============================================================================

def ler_aba(wb, nome_aba: str, linha_cabecalho: int = 1,
            calculadas: set[int] | None = None) -> pd.DataFrame:
    """
    Le uma aba para DataFrame usando os titulos como colunas. Quando o mesmo
    titulo aparece duas vezes (coluna calculada + coluna crua), fica com a
    CRUA - a calculada perde o valor assim que o openpyxl salva o arquivo.

    ATENCAO: 'calculadas' TEM de vir de um workbook aberto com
    data_only=False. Com data_only=True a formula chega ja como valor e
    seria impossivel distinguir uma coluna calculada de uma coluna crua.
    """
    ws = wb[nome_aba]
    if calculadas is None:
        calculadas = colunas_calculadas(ws, linha_cabecalho)
    mapa = mapear_cabecalhos(ws, linha_cabecalho, evitar=calculadas)
    uteis = {chave: indice for chave, indice in mapa.items() if indice not in calculadas}
    if not uteis:
        return pd.DataFrame()

    nomes = list(uteis.keys())
    indices = [uteis[n] for n in nomes]
    registros = []
    for linha in ws.iter_rows(min_row=linha_cabecalho + 1, values_only=True):
        valores = [linha[i - 1] if i - 1 < len(linha) else None for i in indices]
        if any(v is not None and str(v).strip() != "" for v in valores):
            registros.append(valores)
    return pd.DataFrame(registros, columns=nomes)


def texto(valor) -> str:
    """
    Normaliza codigos: 61.0 -> '61', ' 0101001 ' -> '0101001', vazio -> ''.
    ATENCAO: celula vazia lida pelo pandas vira NaN, e str(NaN) e 'nan' -
    uma string NAO vazia. Sem este tratamento, todo pedido sem numero virava
    o codigo 'nan' e a alocacao juntava tudo num pedido so.
    """
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def loja_preferencial(cidade) -> str:
    """Loja que deve ser consultada primeiro na reversa de loja daquela cidade."""
    alvo = normalizar(cidade)
    for nome, cod in LOJA_PREFERENCIAL_POR_CIDADE.items():
        if normalizar(nome) == alvo:
            return texto(cod)
    return ""


def rank_filial(cod: str, cidade=None) -> int:
    """
    1 = FRW | 2 = CD | 3 = loja preferencial da cidade | 4 = demais lojas.
    O nivel 3 e a reversa de loja: a loja indicada e sempre olhada antes das
    outras; se nao tiver o produto, ela nem aparece e o fluxo segue normal.
    """
    if cod.startswith(PREFIXO_FRW):
        return 1
    if cod in CDS:
        return 2
    if cidade is not None and cod and cod == loja_preferencial(cidade):
        return 3
    return 4


NOME_RANK = {1: "FRW", 2: "CD", 3: "LOJA PREFERENCIAL", 4: "LOJA"}


DATA_DESCONHECIDA = datetime(9999, 12, 31)


def data_do_pedido(valor) -> datetime:
    """
    Data de emissao do pedido, usada para atender do mais antigo para o mais
    novo. Quem nao tem data vai para o fim da fila - nunca na frente de um
    pedido com data conhecida.
    """
    if valor is None:
        return DATA_DESCONHECIDA
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    bruto = texto(valor)
    if not bruto:
        return DATA_DESCONHECIDA
    # 20260825 (o Protheus grava assim com frequencia)
    if re.fullmatch(r"\d{8}", bruto):
        for formato in ("%Y%m%d", "%d%m%Y"):
            try:
                return datetime.strptime(bruto, formato)
            except ValueError:
                pass
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y",
                    "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(bruto, formato)
        except ValueError:
            continue
    return DATA_DESCONHECIDA


def numero_do_pedido(valor) -> tuple:
    """
    Desempate quando dois pedidos tem a mesma data. '000440' e '440' viram o
    mesmo numero 440; o que nao for numerico cai no fim, em ordem alfabetica.
    """
    bruto = texto(valor)
    digitos = re.sub(r"\D", "", bruto)
    if digitos:
        return (0, int(digitos), bruto)
    return (1, 0, bruto)


def ordem_de_atendimento(data_pedido, num_pedido) -> tuple:
    """Do mais antigo para o mais novo; empate resolvido pelo numero."""
    return (data_do_pedido(data_pedido), numero_do_pedido(num_pedido))


def alocar_cascata(demandas: list[tuple], pool: list[tuple],
                   ordem_do_pedido=None) -> list[dict]:
    """
    demandas: [(num_pedido, quantidade, dados_extra)] ja ordenadas
    pool    : [(cod_filial, estoque)] ja ordenado pela cascata
    ordem_do_pedido: opcional, recebe o 'extra' de um pedido e devolve a ordem
                de filiais daquele pedido. Serve para a prioridade por
                vendedor: o pedido dele olha a loja propria primeiro, mas
                consome do MESMO estoque que os demais - nada e prometido
                duas vezes.

    Distribui em FIFO: o primeiro pedido consome o primeiro estoque da fila.
    Sem 'ordem_do_pedido' equivale, unidade a unidade, a interseccao de
    intervalos que a medida DAX calcula com vEstoqueAntes / vDemandaAntes.
    """
    saldo = {cod: float(est) for cod, est in pool}
    padrao = [cod for cod, _ in pool]
    resultado = []

    for num_pedido, quantidade, extra in demandas:
        fila = padrao
        if ordem_do_pedido is not None:
            propria = ordem_do_pedido(extra)
            if propria:
                fila = propria
        restante = float(quantidade)
        for cod in fila:
            if restante <= 1e-9:
                break
            disponivel = saldo.get(cod, 0.0)
            if disponivel <= 1e-9:
                continue
            usado = min(restante, disponivel)
            saldo[cod] = disponivel - usado
            restante -= usado
            resultado.append({
                "num_pedido": num_pedido,
                "filial_origem": cod,
                "quantidade": usado,
                "extra": extra,
            })
        if restante > 1e-9:
            resultado.append({
                "num_pedido": num_pedido,
                "filial_origem": None,      # sem estoque na cidade
                "quantidade": restante,
                "extra": extra,
            })
    return resultado


def alocar_como_dax(demandas: list[tuple], pool: list[tuple]) -> dict:
    """
    Implementacao LITERAL da formula da medida, usada so para conferir se o
    FIFO acima chega ao mesmo resultado. Para cada par (pedido, filial):
        vAloc = MAX(0, MIN(estoqueAteAqui, demandaAcumulada)
                       - MAX(estoqueAntes, demandaAntes))
    """
    total: dict[tuple, float] = {}
    demanda_acumulada = 0.0
    for num_pedido, quantidade, _ in demandas:
        demanda_antes = demanda_acumulada
        demanda_acumulada += float(quantidade)
        estoque_antes = 0.0
        for cod, estoque in pool:
            estoque_ate_aqui = estoque_antes + float(estoque)
            aloc = max(0.0, min(estoque_ate_aqui, demanda_acumulada)
                            - max(estoque_antes, demanda_antes))
            if aloc > 1e-9:
                total[(num_pedido, cod)] = total.get((num_pedido, cod), 0.0) + aloc
            estoque_antes = estoque_ate_aqui
    return total


def montar_solicitacao(caminho_planilha: Path,
                       historico: dict | None = None) -> tuple:
    """
    Le a planilha ja atualizada e devolve (coletas_novas, contexto).

    'historico' e o que ja foi solicitado em rodadas anteriores. Ele entra no
    calculo por dois caminhos:
      1. abate a demanda de cada pedido (nunca pedir mais do que foi pedido);
      2. reserva o estoque ja prometido (nunca prometer a mesma unidade duas
         vezes).
    """
    precisamos = ["Filiais", "ftPedidos", "ftEstoqueBap", "ProdutosBAP",
                  "ProdutosExcluir", "FiliaisExcluir", ABA_ESTOQUE_PMZ]

    # 1a passada: com as formulas a vista, para saber quais colunas sao calculadas
    calculadas = calculadas_das_abas(caminho_planilha, precisamos)

    # 2a passada: com os valores, ignorando as colunas calculadas
    wb = _abrir_valores(caminho_planilha)
    try:
        def ler(aba):
            if aba not in wb.sheetnames:
                return pd.DataFrame()
            return ler_aba(wb, aba, calculadas=calculadas.get(aba, set()))

        filiais = ler("Filiais")
        pedidos = ler("ftPedidos")
        estoque_bap = ler("ftEstoqueBap")
        produtos = ler("ProdutosBAP")
        prod_excluir = ler("ProdutosExcluir")
        fil_excluir = ler("FiliaisExcluir")
        estoque_pmz = ler(ABA_ESTOQUE_PMZ)
    finally:
        wb.close()

    if estoque_pmz.empty:
        log.warning("Aba '%s' ausente ou vazia: a alocacao vai considerar "
                    "SOMENTE o estoque BAP.", ABA_ESTOQUE_PMZ)

    # --- de codigo de produto para ID_PRODUTO (o XLOOKUP da planilha) --------
    de_para_produto: dict[str, str] = {}
    ids_conhecidos: set[str] = set()
    ids_sem_espaco: dict[str, str] = {}
    # Tirar os espacos para comparar resolve o caso do PMZ, que escreve o
    # mesmo produto com espaco a mais. Mas se DOIS codigos diferentes
    # virarem o mesmo texto sem espaco, o de-para passa a apontar para o
    # produto errado - e ai o estoque de um vira o do outro. Quando isso
    # acontece, esses codigos SO casam pelo texto exato.
    comprimidos: dict[str, set] = {}
    if not produtos.empty:
        for _, linha in produtos.iterrows():
            codigo = texto(linha.get("cod produto"))
            identificador = texto(linha.get("id produto"))
            if codigo and identificador:
                comprimidos.setdefault(codigo.replace(" ", ""),
                                       set()).add(identificador)
    ambiguos = {c for c, ids in comprimidos.items() if len(ids) > 1}
    if ambiguos:
        log.warning("ProdutosBAP: %d codigo(s) ficam iguais quando se tira os "
                    "espacos e apontam para produtos diferentes (%s...). Eles "
                    "so vao casar pelo codigo exato.",
                    len(ambiguos), ", ".join(sorted(ambiguos)[:3]))
    if not produtos.empty:
        for _, linha in produtos.iterrows():
            codigo = texto(linha.get("cod produto"))
            identificador = texto(linha.get("id produto"))
            if codigo:
                de_para_produto[codigo] = identificador
                comprimido = codigo.replace(" ", "")
                if comprimido not in ambiguos:
                    de_para_produto.setdefault(comprimido, identificador)
            if identificador:
                ids_conhecidos.add(identificador)
                ids_sem_espaco.setdefault(identificador.replace(" ", ""),
                                          identificador)

    fornecedor_de_id: dict[str, str] = {}
    if not produtos.empty:
        for _, linha in produtos.iterrows():
            identificador = texto(linha.get("id produto"))
            bruto = texto(linha.get("fornecedor"))      # "7980 - BAP MOTOS"
            if identificador and bruto:
                fornecedor_de_id[identificador] = bruto.split("-")[0].strip()

    # CD de destino de cada filial (coluna CD_FILIAL da aba Filiais).
    # Loja 97 -> 91, CD 27 -> 27: a mesma regra serve para reversa e separacao.
    cd_de_filial = {texto(l.get("cod filial")): texto(l.get("cd filial"))
                    for _, l in filiais.iterrows()}

    def id_produto(*candidatos) -> str:
        """
        Resolve o ID_PRODUTO aceitando: o proprio ID, o ID com espacos a mais
        (a aba do PMZ traz '1598080W90 SHIFTEASE BD9CSW-8B' enquanto o
        ProdutosBAP tem '1598080W90SHIFTEASEBD9CSW-8B') ou o codigo do produto.
        """
        for valor in candidatos:
            bruto = texto(valor)
            if not bruto:
                continue
            if bruto in ids_conhecidos:
                return bruto
            comprimido = bruto.replace(" ", "")
            if comprimido in ids_sem_espaco:
                return ids_sem_espaco[comprimido]
            achado = de_para_produto.get(bruto) or de_para_produto.get(comprimido)
            if achado:
                return achado
        return ""

    # --- cidade de cada filial ----------------------------------------------
    cidade_de = {texto(l.get("cod filial")): l.get("cidade")
                 for _, l in filiais.iterrows()}
    filiais_da_cidade: dict[object, list[str]] = {}
    for cod, cidade in cidade_de.items():
        filiais_da_cidade.setdefault(cidade, []).append(cod)

    # ---- o que fica de fora da coleta -------------------------------------
    #
    # As duas listas moram no SOLICITACAO_BAP, que e SEU e nao e regerado a
    # cada rodada. A TABELA_BAP so entra como heranca: se as abas de la
    # tiverem conteudo e as do arquivo de solicitacao ainda estiverem
    # vazias, o conteudo antigo continua valendo ate a migracao acontecer.
    do_arquivo = (historico or {}).get("exclusao") or {}
    da_tabela = {
        ABA_PRODUTOS_EXCLUIR: [
            {normalizar(c): texto(l.get(c)) for c in prod_excluir.columns}
            for _, l in prod_excluir.iterrows()],
        ABA_FILIAIS_EXCLUIR: [
            {normalizar(c): texto(l.get(c)) for c in fil_excluir.columns}
            for _, l in fil_excluir.iterrows()],
    }
    # guardado para a migracao na hora de gravar
    if historico is not None:
        historico["exclusao_da_tabela"] = da_tabela

    def linhas_de(nome):
        proprias = do_arquivo.get(nome) or []
        return proprias if proprias else (da_tabela.get(nome) or [])

    def campo(registro, *nomes):
        for nome in nomes:
            valor = registro.get(normalizar(nome))
            if valor:
                return texto(valor)
        return ""

    excluir_filiais = set()
    for registro in linhas_de(ABA_FILIAIS_EXCLUIR):
        filial = campo(registro, "Filial", "COD_FILIAL", "FILIAL_BAP")
        if filial:
            excluir_filiais.add(filial)

    # o par produto x filial aceita o ID ou o CODIGO do produto: quem
    # escreve na planilha tem o codigo na mao, nao o ID.
    excluir_produto_filial = set()
    for registro in linhas_de(ABA_PRODUTOS_EXCLUIR):
        filial = campo(registro, "Filial", "COD_FILIAL")
        if not filial:
            continue
        identificador = campo(registro, "ID_PRODUTO")
        codigo = campo(registro, "Cód", "Cod", "COD_PRODUTO", "Produto")
        for bruto in (identificador, codigo):
            if not bruto:
                continue
            resolvido = id_produto(bruto)
            if resolvido:
                excluir_produto_filial.add((resolvido, filial))
        if not identificador and not codigo:
            continue
    log.info("Fora da coleta: %d filial(is) e %d par(es) produto x filial "
             "(fonte: %s).", len(excluir_filiais), len(excluir_produto_filial),
             ARQUIVO_SOLICITACAO if (do_arquivo.get(ABA_FILIAIS_EXCLUIR)
                                     or do_arquivo.get(ABA_PRODUTOS_EXCLUIR))
             else NOME_PLANILHA)

    estoque_pmz_por_chave: dict[tuple, float] = {}
    fonte_pmz: dict[tuple, float] = {}
    if not estoque_pmz.empty:
        def achar(colunas):
            for candidata in colunas:
                chave = normalizar(candidata)
                if chave in estoque_pmz.columns:
                    return chave
            return None
        c_fil, c_prod, c_qtd = (achar(COLS_PMZ_FILIAL), achar(COLS_PMZ_PRODUTO),
                                achar(COLS_PMZ_QTDE))
        c_sep = achar(COLS_PMZ_SEPARADA) if ESTOQUE_PMZ_DESCONTAR_SEPARADA else None

        if not all((c_fil, c_prod, c_qtd)):
            log.warning("Aba '%s': nao achei as colunas de filial/produto/qtde. "
                        "Colunas presentes: %s", ABA_ESTOQUE_PMZ,
                        list(estoque_pmz.columns))
        else:
            if ESTOQUE_PMZ_DESCONTAR_SEPARADA and not c_sep:
                log.warning("Aba '%s': pedi para descontar o separado, mas nao "
                            "achei a coluna. Vou usar o total.", ABA_ESTOQUE_PMZ)

            def numero(valor) -> float:
                try:
                    return float(valor or 0)
                except (TypeError, ValueError):
                    return 0.0

            negativos = 0
            nao_resolvidos = 0
            for _, linha in estoque_pmz.iterrows():
                cod = texto(linha.get(c_fil))
                pid = id_produto(linha.get(c_prod),
                                 linha.get("produto"), linha.get("cod produto"),
                                 linha.get("b2 cod"))
                if not pid:
                    nao_resolvidos += 1
                qtd = numero(linha.get(c_qtd))
                if c_sep:
                    qtd -= numero(linha.get(c_sep))
                    if qtd < 0:
                        negativos += 1
                        qtd = 0.0
                if pid and qtd > 0:
                    estoque_pmz_por_chave[(cod, pid)] = \
                        estoque_pmz_por_chave.get((cod, pid), 0.0) + qtd
                if qtd > 0:
                    # todas as grafias que a aba usa para este item: o
                    # codigo, o ID, com e sem espaco. A conferencia aceita
                    # qualquer uma - ela quer saber se o item ESTA ali.
                    for candidata in (c_prod, "produto", "cod produto",
                                      "b2 cod", "id produto"):
                        bruto_cru = texto(linha.get(candidata)).upper()
                        if not bruto_cru:
                            continue
                        for chave_cru in {bruto_cru,
                                          bruto_cru.replace(" ", "")}:
                            fonte_pmz[(cod, chave_cru)] = (
                                fonte_pmz.get((cod, chave_cru), 0.0) + qtd)

            log.info("Estoque PMZ: %d combinacoes filial/produto com saldo.",
                     len(estoque_pmz_por_chave))
            if negativos:
                log.warning("  %d linhas tinham separado maior que o total "
                            "(tratadas como zero).", negativos)
            if nao_resolvidos:
                log.warning("  %d linhas do estoque PMZ nao casaram com nenhum "
                            "produto do ProdutosBAP e foram ignoradas.",
                            nao_resolvidos)

    # --- demanda ------------------------------------------------------------
    #
    # Le o ftPedidos INTEIRO, nao so as linhas VEA. As demais servem para dizer
    # o que aconteceu com um pedido que ja esta gravado na solicitacao:
    # virou VND (FATURADO) ou sumiu da consulta (EXCLUIDO).
    tipos = {t.upper() for t in TIPOS_DEMANDA}
    tipos_fora = {t.upper() for t in TIPOS_FATURADO}

    def achar_coluna(candidatas):
        for candidata in candidatas:
            if normalizar(candidata) in pedidos.columns:
                return normalizar(candidata)
        return None

    coluna_data = achar_coluna(COLS_PEDIDO_DATA)
    if coluna_data is None and not pedidos.empty:
        log.warning("Nao achei a coluna de data do pedido (%s) no ftPedidos. "
                    "Vou atender na ordem do NUMERO do pedido.",
                    ", ".join(COLS_PEDIDO_DATA))

    coluna_vendedor = achar_coluna(COLS_PEDIDO_VENDEDOR)
    if coluna_vendedor is None and VENDEDORES_PRIORIDADE_FILIAL:
        log.warning("Nao achei a coluna do vendedor (%s) no ftPedidos. "
                    "A prioridade por vendedor NAO vai ser aplicada.",
                    ", ".join(COLS_PEDIDO_VENDEDOR))

    demanda: dict[tuple, dict] = {}     # (cidade, produto, pedido) -> dados
    situacao: dict[tuple, str] = {}     # (cidade, pedido, item) -> situacao
    for _, linha in pedidos.iterrows():
        tipo = texto(linha.get("tipo")).upper()
        cod_filial = "4" + texto(linha.get("d2 filial"))
        cidade = cidade_de.get(cod_filial)
        if cidade is None:
            continue
        pid = id_produto(linha.get("d2 cod"), linha.get("id produto"))
        if not pid:
            continue
        pedido = texto(linha.get("d2 pedido")) or texto(linha.get("d2 doc"))

        # situacao do item, para as linhas ja gravadas na solicitacao
        chave_item = item_do_pedido(cidade, pedido, pid)
        if tipo in tipos:
            situacao[chave_item] = SITUACAO_ABERTO
        elif tipo in tipos_fora and situacao.get(chave_item) != SITUACAO_ABERTO:
            situacao[chave_item] = SITUACAO_FATURADO

        if tipo not in tipos:
            continue
        if pedido_fora_da_base(linha.get("razao social")):
            continue                    # RN-GER-013: pedido interno nao e demanda
        try:
            qtd = float(linha.get("d2 quant") or 0)
        except (TypeError, ValueError):
            qtd = 0.0
        if qtd <= 0:
            continue
        chave = (cidade, pid, pedido)
        registro = demanda.setdefault(chave, {
            "quantidade": 0.0,
            "cod_produto": texto(linha.get("d2 cod")),
            "cliente": texto(linha.get("d2 cliente")),
            "filial_pedido": cod_filial,
            "data_pedido": (linha.get(coluna_data) if coluna_data else None),
            "vendedor": (texto(linha.get(coluna_vendedor))
                         if coluna_vendedor else ""),
        })
        registro["quantidade"] += qtd
        if registro.get("data_pedido") is None and coluna_data:
            registro["data_pedido"] = linha.get(coluna_data)
        if not registro.get("vendedor") and coluna_vendedor:
            registro["vendedor"] = texto(linha.get(coluna_vendedor))

    # --- estoque por (filial, produto) --------------------------------------
    #
    # CUIDADO COM O B2_QPEDVEN. Ele e "quantidade em pedido de venda" - e
    # boa parte dele E A PROPRIA DEMANDA QUE ESTAMOS ALOCANDO: o pedido VEA
    # do cliente ja nasce empenhado no Protheus. Descontar isso seria tirar
    # o produto da conta DUAS vezes e mandar buscar longe o que esta bem
    # ali, separado para este mesmo pedido.
    #
    # Entao o que sai da conta e so o empenho que NAO e a nossa demanda:
    #
    #     livre = QATU - RESERVA - max(0, QPEDVEN - demanda VEA em aberto)
    #
    # BDA50001 no FRW de Manaus: QATU 5, QPEDVEN 5, e o pedido 378 pede 5.
    # O empenho E o pedido - a filial tem as 5 e a coleta fica ali mesmo.
    # CAR19 em Belem: QATU 1, QPEDVEN 360 e nenhum VEA aberto - aquele
    # empenho e de outra venda, e a peca nao esta livre.
    demanda_aberta: dict[tuple, float] = {}
    for (cidade_d, pid_d, _), dados_d in demanda.items():
        chave_d = (dados_d["filial_pedido"], pid_d)
        demanda_aberta[chave_d] = (demanda_aberta.get(chave_d, 0.0)
                                   + float(dados_d["quantidade"]))

    estoque: dict[tuple, float] = {}
    fonte_bap: dict[tuple, float] = {}
    empenhado_bap = 0.0
    linhas_empenhadas = 0

    def coluna_do_estoque_bap(candidatas):
        for candidata in candidatas:
            chave = normalizar(candidata)
            if chave in estoque_bap.columns:
                return chave
        return None

    b_res = (coluna_do_estoque_bap(COLS_BAP_RESERVA)
             if ESTOQUE_BAP_DESCONTAR_EMPENHO else None)
    b_ped = (coluna_do_estoque_bap(COLS_BAP_PEDIDO)
             if ESTOQUE_BAP_DESCONTAR_EMPENHO else None)
    if ESTOQUE_BAP_DESCONTAR_EMPENHO and not (b_res or b_ped):
        log.warning("Aba '%s': pedi para descontar o empenho, mas nao achei "
                    "nem B2_RESERVA nem B2_QPEDVEN. Vou usar o B2_QATU cheio "
                    "- confira antes de mandar coletar.", "ftEstoqueBap")

    for _, linha in estoque_bap.iterrows():
        cod = "4" + texto(linha.get("b2 filial original"))
        pid = id_produto(linha.get("b2 cod"), linha.get("id produto"))

        def numero_bap(chave):
            if not chave:
                return 0.0
            try:
                return float(linha.get(chave) or 0)
            except (TypeError, ValueError):
                return 0.0

        try:
            qtd = float(linha.get("b2 qatu") or 0)
        except (TypeError, ValueError):
            qtd = 0.0
        # o que esta reservado, mais o empenho que nao e a nossa demanda
        empenho = numero_bap(b_ped)
        nosso = (demanda_aberta.get((cod, pid), 0.0)
                 if pid and DEVOLVER_EMPENHO_DA_PROPRIA_DEMANDA else 0.0)
        preso = numero_bap(b_res) + max(0.0, empenho - nosso)
        if preso and qtd > 0:
            empenhado_bap += min(preso, qtd)
            if qtd - preso <= 0:
                linhas_empenhadas += 1
        qtd = max(0.0, qtd - preso)
        if pid and qtd:
            estoque[(cod, pid)] = estoque.get((cod, pid), 0.0) + qtd
        # A SEGUNDA LEITURA, pelo CODIGO DO PRODUTO como ele esta escrito
        # na aba - sem passar pelo de-para, sem depender de formula
        # nenhuma. Ela nao entra na conta: serve para CONFERIR, logo
        # adiante, se o que a alocacao encontrou existe mesmo ali.
        if qtd > 0:
            for candidata in ("b2 cod", "id produto"):
                bruto_cru = texto(linha.get(candidata)).upper()
                if not bruto_cru:
                    continue
                for chave_cru in {bruto_cru, bruto_cru.replace(" ", "")}:
                    fonte_bap[(cod, chave_cru)] = (
                        fonte_bap.get((cod, chave_cru), 0.0) + qtd)
    if empenhado_bap:
        log.info("Estoque BAP: %.0f unidade(s) fora da conta por reserva ou "
                 "pedido de venda; %d combinacao(oes) ficaram sem saldo livre.",
                 empenhado_bap, linhas_empenhadas)

    # --- o que ja foi solicitado antes --------------------------------------
    historico = historico or historico_vazio()
    ja_solicitado: dict[tuple, float] = dict(historico.get("solicitado", {}))

    # Reserva de estoque: o que foi prometido a um pedido AINDA EM ABERTO nao
    # pode ser prometido de novo. Pedido faturado ou excluido devolve o estoque.
    reserva: dict[tuple, float] = {}
    if RESERVAR_ESTOQUE_JA_SOLICITADO:
        for (filial, produto_upper), itens in historico.get(
                "prometido_bruto", {}).items():
            for chave_item, quantidade in itens:
                if situacao.get(chave_item, SITUACAO_EXCLUIDO) != SITUACAO_ABERTO:
                    continue
                reserva[(filial, produto_upper)] = \
                    reserva.get((filial, produto_upper), 0.0) + quantidade
        if reserva:
            log.info("  reserva: %d combinacoes filial/item com estoque ja "
                     "prometido (%.0f unidades)",
                     len(reserva), sum(reserva.values()))

    # --- alocacao por cidade + produto --------------------------------------
    linhas_saida = []
    divergencias = 0
    zerados = 0                 # itens ja totalmente solicitados
    reservado_usado = 0.0

    prioridade_usada: dict[str, float] = {}   # vendedor -> unidades pela loja
    livre_na_origem: dict[tuple, float] = {}  # (filial, produto) -> saldo livre

    # CODIGOS de produto que caem em cada ID, vindos da propria demanda.
    # E por eles que a conferencia pergunta "isto existe mesmo ali?".
    codigos_do_pid: dict[str, set] = {}
    for (_, pid_c, _), dados_c in demanda.items():
        codigo_c = texto(dados_c.get("cod_produto")).upper()
        if codigo_c:
            codigos_do_pid.setdefault(pid_c, set()).update(
                {codigo_c, codigo_c.replace(" ", "")})

    # As coletas barradas pela conferencia. Se esta lista sair com algo,
    # e porque a alocacao achou saldo que a aba nao tem - e a coleta NAO
    # e emitida naquela filial.
    barradas_pela_fonte: list[dict] = []

    def existe_na_aba(cod: str, pid: str) -> bool:
        """
        A CONFERENCIA. O saldo que a alocacao usa vem do de-para de
        produto e de colunas que podem ser formula; esta segunda leitura
        pergunta a mesma coisa direto na aba, pelo codigo do produto como
        ele esta escrito la. Se as duas discordam, a aba manda - e melhor
        deixar de coletar do que mandar alguem buscar o que nao existe.
        """
        if not CONFERIR_ESTOQUE_NA_FONTE:
            return True
        codigos = set(codigos_do_pid.get(pid) or ())
        alvo = texto(pid).upper()
        if alvo:
            codigos |= {alvo, alvo.replace(" ", "")}
        if not codigos:
            return True          # sem codigo para conferir, nao inventa
        for codigo in codigos:
            if fonte_bap.get((cod, codigo), 0.0) > 0:
                return True
            if not cod.startswith(PREFIXO_FRW) and \
                    fonte_pmz.get((cod, codigo), 0.0) > 0:
                return True
        return False

    def estoque_livre_de(cod: str, pid: str) -> float:
        """Estoque da filial menos o que ja foi prometido a pedido em aberto."""
        if cod.startswith(PREFIXO_FRW):
            bruto = estoque.get((cod, pid), 0.0)              # so BAP
        else:
            bruto = (estoque_pmz_por_chave.get((cod, pid), 0.0)
                     + estoque.get((cod, pid), 0.0))
        if bruto > 0 and not existe_na_aba(cod, pid):
            barradas_pela_fonte.append({
                "filial": cod, "id_produto": pid,
                "codigos": sorted(codigos_do_pid.get(pid, ())),
                "saldo_calculado": bruto,
            })
            return 0.0, 0.0
        prometido = reserva.get((cod, texto(pid).upper()), 0.0)
        return max(0.0, bruto - prometido), min(prometido, bruto)

    def filial_do_vendedor(dados: dict) -> str:
        """A loja que atende primeiro os pedidos deste vendedor, se houver."""
        if not coluna_vendedor:
            return ""
        return VENDEDORES_PRIORIDADE_FILIAL.get(texto(dados.get("vendedor")), "")

    chaves = sorted({(c, p) for (c, p, _) in demanda})
    for cidade, pid in chaves:
        candidatas = []
        for cod in filiais_da_cidade.get(cidade, []):
            if cod in excluir_filiais or (pid, cod) in excluir_produto_filial:
                continue
            disponivel, usado_da_reserva = estoque_livre_de(cod, pid)
            reservado_usado += usado_da_reserva
            if disponivel > 0:
                candidatas.append((cod, disponivel))

        pool = sorted(candidatas,
                      key=lambda x: (rank_filial(x[0], cidade), -x[1], x[0]))
        for _cod, _livre in pool:
            livre_na_origem[(_cod, pid)] = _livre

        # Do pedido MAIS ANTIGO para o mais novo: se o estoque acabar, quem
        # fica sem e o pedido mais recente.
        fila = []
        for (c, p, pedido), dados in demanda.items():
            if c != cidade or p != pid:
                continue
            chave_item = item_do_pedido(cidade, pedido, pid)
            ja = ja_solicitado.get(chave_item, 0.0) if CONTROLAR_POR_SALDO else 0.0
            saldo = max(0.0, float(dados["quantidade"]) - ja)
            if saldo <= 1e-9:
                zerados += 1
                continue        # pedido ja atendido por inteiro: nao entra
            dados = {**dados, "ja_solicitado": ja, "saldo": saldo}
            fila.append((pedido, saldo, dados))

        if not fila:
            continue
        pedidos_da_chave = sorted(
            fila, key=lambda x: ordem_de_atendimento(x[2].get("data_pedido"),
                                                     x[0]))

        # --- prioridade por vendedor -------------------------------------
        # A loja indicada entra no pool mesmo estando em FiliaisExcluir, e
        # SOMENTE os pedidos daquele vendedor a enxergam - na frente de tudo.
        lojas_prioritarias = {filial_do_vendedor(d) for _, _, d in fila}
        lojas_prioritarias.discard("")
        ordem_do_pedido = None
        if lojas_prioritarias:
            no_pool = {cod for cod, _ in pool}
            for loja in sorted(lojas_prioritarias):
                if loja in no_pool:
                    continue        # ja esta na cidade e nao estava bloqueada
                if (pid, loja) in excluir_produto_filial:
                    continue        # bloqueio de PRODUTO x filial continua valendo
                disponivel, usado_da_reserva = estoque_livre_de(loja, pid)
                reservado_usado += usado_da_reserva
                if disponivel > 0:
                    pool.append((loja, disponivel))

            saldo_no_pool = {cod for cod, _ in pool}
            ordem_padrao = [cod for cod, _ in pool
                            if cod not in lojas_prioritarias]

            def ordem_do_pedido(dados, _padrao=ordem_padrao,
                                _no_pool=saldo_no_pool):
                loja = filial_do_vendedor(dados)
                if not loja:
                    # quem nao e do vendedor nunca enxerga a loja prioritaria
                    return _padrao
                if loja not in _no_pool:
                    return _padrao
                return [loja] + _padrao

        alocado = alocar_cascata(pedidos_da_chave, pool, ordem_do_pedido)

        # Conferencia contra a formula da medida. So vale quando todos os
        # pedidos enxergam a mesma fila - com prioridade por vendedor a
        # medida DAX nao tem equivalente, e a comparacao nao faz sentido.
        if ordem_do_pedido is None:
            referencia = alocar_como_dax(pedidos_da_chave, pool)
            obtido: dict[tuple, float] = {}
            for item in alocado:
                if item["filial_origem"]:
                    chave = (item["num_pedido"], item["filial_origem"])
                    obtido[chave] = obtido.get(chave, 0.0) + item["quantidade"]
            if any(abs(obtido.get(k, 0.0) - v) > 1e-6
                   for k, v in referencia.items()) \
               or any(k not in referencia for k in obtido):
                divergencias += 1

        for item in alocado:
            dados = item["extra"]
            cod = item["filial_origem"]
            data_pedido = dados.get("data_pedido")
            loja_do_vendedor = filial_do_vendedor(dados)
            if cod and cod == loja_do_vendedor:
                origem_tipo = ORIGEM_VENDEDOR
                vendedor = texto(dados.get("vendedor"))
                prioridade_usada[vendedor] = \
                    prioridade_usada.get(vendedor, 0.0) + item["quantidade"]
            elif cod:
                origem_tipo = NOME_RANK[rank_filial(cod, cidade)]
            else:
                origem_tipo = "-"
            linhas_saida.append({
                "CIDADE": cidade,
                "ID_PRODUTO": pid,
                "COD_PRODUTO": dados["cod_produto"],
                "NUM_PEDIDO": item["num_pedido"],
                "DT_PEDIDO": converter_valor(data_pedido),
                "CLIENTE": dados["cliente"],
                "FILIAL_PEDIDO": dados["filial_pedido"],
                "COLETAR_EM": cod or STATUS_SEM_ORIGEM,
                "TIPO_ORIGEM": origem_tipo,
                "QUANTIDADE": round(item["quantidade"], 4),
                "DEMANDA_PEDIDO": round(dados["quantidade"], 4),
                "JA_SOLICITADO": round(dados.get("ja_solicitado", 0.0), 4),
                "SALDO_A_SOLICITAR": round(dados.get("saldo", 0.0), 4),
                # o saldo LIVRE que a origem tinha nesta rodada: e por ele
                # que se confere, depois, se a coleta fazia sentido
                "ESTOQUE_NA_ORIGEM": round(livre_na_origem.get((cod, pid), 0.0),
                                           4) if cod else 0.0,
                "SITUACAO_PEDIDO": SITUACAO_ABERTO,
                # usados so para montar os CSVs de importacao
                "FORNECEDOR": fornecedor_de_id.get(pid, ""),
                "FILIAL_DESTINO": cd_de_filial.get(cod, "") if cod else "",
            })

    if divergencias:
        log.warning("Alocacao: %d combinacoes divergiram da formula de "
                    "intervalos da medida. Confira antes de usar.", divergencias)
    else:
        log.info("Alocacao confere com a formula de intervalos da medida em "
                 "todas as combinacoes (usando a prioridade configurada aqui).")

    usadas = {c for c in LOJA_PREFERENCIAL_POR_CIDADE
              if any(normalizar(c) == normalizar(cid) for cid, _ in chaves)}
    if usadas:
        log.info("Reversa de loja ativa em: %s",
                 ", ".join(f"{c} -> loja {LOJA_PREFERENCIAL_POR_CIDADE[c]}"
                           for c in sorted(usadas)))
    if zerados:
        log.info("  %d itens de pedido ja estavam totalmente solicitados e "
                 "ficaram de fora.", zerados)
    if reservado_usado:
        log.info("  %.0f unidades de estoque estavam reservadas a pedidos ja "
                 "solicitados e nao foram oferecidas de novo.", reservado_usado)
    for vendedor, quantas in sorted(prioridade_usada.items()):
        log.info("  prioridade do vendedor %s (%s): %.0f unidade(s) saindo da "
                 "loja %s.", vendedor, NOME_DO_VENDEDOR.get(vendedor, "?"),
                 quantas, VENDEDORES_PRIORIDADE_FILIAL.get(vendedor, "?"))

    df = pd.DataFrame(linhas_saida)
    contexto = {
        "situacao": situacao,
        "ja_solicitado": ja_solicitado,
        # o saldo LIVRE de cada filial, para quem precisa conferir depois
        # se uma coleta ja gravada ainda faz sentido
        "estoque_bap": dict(estoque),
        "estoque_pmz": dict(estoque_pmz_por_chave),
        # a segunda leitura, pelo codigo do produto como esta na aba
        "fonte_bap": dict(fonte_bap),
        "fonte_pmz": dict(fonte_pmz),
        "id_produto": id_produto,
        "cidade_de": dict(cidade_de),
        "cd_de_filial": dict(cd_de_filial),
        "filiais_da_cidade": {c: list(f)
                              for c, f in filiais_da_cidade.items()},
        "demanda_por_item": {
            item_do_pedido(c, pedido, p): dados["quantidade"]
            for (c, p, pedido), dados in demanda.items()
        },
        "excessos": conferir_excessos(df, ja_solicitado, demanda),
        "barradas_pela_fonte": barradas_pela_fonte,
    }
    if barradas_pela_fonte:
        log.warning("CONFERENCIA DO ESTOQUE: %d combinacao(oes) filial/produto "
                    "tinham saldo na conta mas NAO estao na aba do estoque. "
                    "Nenhuma coleta foi emitida nelas:",
                    len(barradas_pela_fonte))
        for caso in barradas_pela_fonte[:15]:
            log.warning("   filial %s, produto %s (%s): a conta dizia %.0f, a "
                        "aba nao tem a linha",
                        caso["filial"], "/".join(caso["codigos"][:2]) or "?",
                        caso["id_produto"], caso["saldo_calculado"])
        log.warning("   Isso quase sempre e formula desatualizada na "
                    "TABELA_BAP: abra a planilha no Excel, deixe recalcular "
                    "e salve.")
    return df, contexto


def conferir_excessos(df: pd.DataFrame, ja_solicitado: dict,
                      demanda: dict) -> list[dict]:
    """
    Trava de conferencia: nenhum item de pedido pode terminar a rodada com
    mais unidades solicitadas do que a sua demanda em aberto.

    Separa duas coisas bem diferentes:
      HERDADO - o excesso ja estava gravado no arquivo antes desta rodada.
                Nada que o script faca hoje conserta: alguem precisa cancelar
                a SEP. Vira AVISO, e nao erro, para nao gritar todo dia.
      NOVO    - foi esta rodada que passou do limite. Isso e defeito, e a
                trava existe para pegar.
    """
    novo_por_item: dict[tuple, float] = {}
    if df is not None and not df.empty:
        for _, linha in df.iterrows():
            if texto(linha.get("COLETAR_EM")) == STATUS_SEM_ORIGEM:
                continue
            item = item_do_pedido(linha.get("CIDADE"), linha.get("NUM_PEDIDO"),
                                  linha.get("ID_PRODUTO"))
            novo_por_item[item] = novo_por_item.get(item, 0.0) + \
                float(linha.get("QUANTIDADE") or 0)

    excessos = []
    for (cidade, pid, pedido), dados in demanda.items():
        item = item_do_pedido(cidade, pedido, pid)
        antes = ja_solicitado.get(item, 0.0)
        agora = antes + novo_por_item.get(item, 0.0)
        pedida = float(dados["quantidade"])
        if agora <= pedida + 1e-6:
            continue
        excessos.append({
            "cidade": texto(cidade), "pedido": texto(pedido),
            "produto": texto(pid),
            "demanda": round(pedida, 4),
            "solicitado": round(agora, 4),
            "excesso": round(agora - pedida, 4),
            "herdado": antes > pedida + 1e-6,
        })

    herdados = [c for c in excessos if c["herdado"]]
    novos = [c for c in excessos if not c["herdado"]]

    def listar(casos, registrar):
        for caso in sorted(casos, key=lambda c: -c["excesso"])[:10]:
            registrar("  pedido %s | %s | %s: pediu %.0f, solicitado %.0f "
                      "(+%.0f)", caso["pedido"], caso["cidade"],
                      caso["produto"], caso["demanda"], caso["solicitado"],
                      caso["excesso"])
        if len(casos) > 10:
            registrar("  ... e mais %d.", len(casos) - 10)

    if novos:
        log.error("=" * 70)
        log.error("TRAVA: %d item(ns) de pedido passaram da demanda NESTA "
                  "rodada. Isso nao deveria acontecer - me avise.", len(novos))
        listar(novos, log.error)
        log.error("=" * 70)

    if herdados:
        log.warning("=" * 70)
        log.warning("AVISO: %d item(ns) de pedido ja estavam com mais unidades "
                    "solicitadas do que a demanda ANTES desta rodada "
                    "(%.0f unidades no total).",
                    len(herdados), sum(c["excesso"] for c in herdados))
        listar(herdados, log.warning)
        log.warning("  O script nao gera mais nada para esses itens, mas as")
        log.warning("  SEPs abertas em excesso precisam ser canceladas na mao.")
        log.warning("  Rode 'python conferir_solicitacao.py' para a lista toda.")
        log.warning("=" * 70)

    return excessos


def preparar_historico(simular: bool) -> tuple:
    """
    Traz o arquivo acumulado para a pasta temporaria e le o que ja foi
    solicitado. Precisa acontecer ANTES da alocacao: e o historico que abate a
    demanda de cada pedido e reserva o estoque ja prometido.

    ATENCAO ao modo simulacao. Ele grava a solicitacao SO na pasta local e
    nunca na nuvem. Se mesmo assim lesse o historico do arquivo oficial, cada
    simulacao recomecaria do zero: tudo viraria "novo" e ganharia SEP nova, em
    cima de coletas ja abertas. Por isso a simulacao usa o proprio arquivo de
    teste - so cai para o real na primeira vez.
    """
    local = PASTA_TEMP / ARQUIVO_SOLICITACAO
    oficial = caminho_da_solicitacao(simular=False)
    existente = None
    try:
        if simular:
            copia_simulacao = caminho_da_solicitacao(simular=True)
            origem = copia_simulacao if copia_simulacao.exists() else oficial
            if origem.exists():
                shutil.copy2(origem, local)
                existente = local
                log.warning("  [simulacao] historico lido de: %s", origem)
            else:
                log.warning("  [simulacao] nao achei historico nenhum.")
        elif oficial.exists():
            shutil.copy2(oficial, local)
            existente = local
    except Exception as erro:
        log.warning("Nao consegui ler o %s existente (%s). Por seguranca, "
                    "nao vou sobrescrever.", ARQUIVO_SOLICITACAO, erro)
        return None, historico_vazio(), str(erro)

    return existente, ler_historico_solicitacao(existente), None


def gerar_solicitacao(caminho_planilha: Path, armazenamento,
                      simular: bool = False) -> dict:
    log.info("Montando a solicitacao de coleta...")

    # Rede de seguranca: a copia de trabalho e MOVIDA quando a planilha e
    # devolvida (os.replace). Se por qualquer motivo ela ja tiver saido daqui,
    # leia a planilha no destino em vez de quebrar a rodada inteira.
    caminho_planilha = Path(caminho_planilha)
    if not caminho_planilha.exists():
        oficial = getattr(armazenamento, "planilha", None)
        if oficial and Path(oficial).exists():
            log.debug("A copia de trabalho ja foi devolvida; lendo %s", oficial)
            caminho_planilha = Path(oficial)

    existente, historico, erro = preparar_historico(simular)
    if erro:
        return {"linhas": 0, "arquivo": ARQUIVO_SOLICITACAO, "erro": erro}

    saida = montar_solicitacao(caminho_planilha, historico)
    # tolera implementacoes antigas que devolvem so o DataFrame
    df, contexto = saida if isinstance(saida, tuple) else (saida, {})

    if df.empty:
        log.warning("Nenhuma coleta nova a solicitar (todos os pedidos em "
                    "aberto ja estao atendidos, ou nao ha demanda TIPO %s).",
                    "/".join(TIPOS_DEMANDA))
        # mesmo sem linha nova, a situacao dos pedidos e as linhas SEM ESTOQUE
        # precisam ser atualizadas no arquivo.
        return acumular_solicitacao(df, armazenamento, simular,
                                    existente=existente, historico=historico,
                                    contexto=contexto)

    sem_estoque = int((df["COLETAR_EM"] == STATUS_SEM_ORIGEM).sum())
    log.info("  %d linhas de coleta | %d produtos | %d pedidos | %d sem estoque",
             len(df), df["ID_PRODUTO"].nunique(), df["NUM_PEDIDO"].nunique(),
             sem_estoque)

    return acumular_solicitacao(df, armazenamento, simular,
                                existente=existente, historico=historico,
                                contexto=contexto)


# --------------------- arquivo unico, acumulativo -----------------------------

def chave_da_linha(cidade, pedido, produto, origem) -> tuple:
    """
    Identifica uma coleta ja solicitada: cidade + pedido + item + filial de
    origem. Repetir o item e permitido desde que a origem seja outra - e cada
    origem nova recebe a sua propria SEP.
    """
    return (normalizar(cidade), texto(pedido).upper(),
            texto(produto).upper(), texto(origem).upper())


def item_do_pedido(cidade, pedido, produto) -> tuple:
    """Identifica um item de pedido, independente de onde ele foi coletado."""
    return (normalizar(cidade), texto(pedido).upper(), texto(produto).upper())


def historico_vazio() -> dict:
    return {"arquivo": None, "linhas": [], "chaves": set(),
            "solicitado": {}, "prometido_bruto": {},
            # as duas listas de exclusao, lidas do proprio arquivo
            "exclusao": {ABA_PRODUTOS_EXCLUIR: [], ABA_FILIAIS_EXCLUIR: []},
            "exclusao_da_tabela": {}}


def ler_historico_solicitacao(caminho: Path) -> dict:
    """
    Le a aba de detalhe do arquivo acumulado. E a fonte da verdade do que ja
    foi solicitado - toda coleta passa por ela.

    Devolve:
      linhas    - uma entrada por linha gravada, com item, origem e quantidade
      chaves    - a rede de seguranca contra linha identica
      solicitado - {(cidade, pedido, item): quantidade ja solicitada}
                   Linhas SEM ESTOQUE nao contam: nada foi pedido de fato.
      prometido_bruto - {(filial, item): [(chave_do_item, quantidade)]}
                   Vira reserva de estoque so para os pedidos ainda em aberto -
                   por isso a lista fica crua aqui.
    """
    historico = historico_vazio()
    if not caminho or not Path(caminho).exists():
        return historico
    historico["arquivo"] = Path(caminho)

    # as abas de exclusao precisam do modo normal (read_only nao da o
    # mapa de cabecalhos do jeito que garantir_abas_de_exclusao espera)
    wb_ex = load_workbook(caminho, data_only=True)
    try:
        historico["exclusao"] = ler_abas_de_exclusao(wb_ex)
    finally:
        wb_ex.close()

    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        nome = next((a for a in (ABA_DETALHE, *RENOMEAR_ABAS)
                     if a in wb.sheetnames), None)
        if nome is None:
            return historico
        ws = wb[nome]
        linhas = ws.iter_rows(values_only=True)
        try:
            cabecalho = [normalizar(c) for c in next(linhas)]
        except StopIteration:
            return historico
        try:
            i_cid = cabecalho.index(normalizar("CIDADE"))
            i_ped = cabecalho.index(normalizar("NUM_PEDIDO"))
            i_pro = cabecalho.index(normalizar("ID_PRODUTO"))
            i_ori = cabecalho.index(normalizar("COLETAR_EM"))
        except ValueError:
            log.warning("O arquivo de solicitacao nao tem as colunas da chave "
                        "(%s). Vou tratar tudo como novo.",
                        ", ".join(CHAVE_SOLICITACAO))
            return historico
        try:
            i_qtd = cabecalho.index(normalizar("QUANTIDADE"))
        except ValueError:
            i_qtd = None
            log.warning("O arquivo de solicitacao nao tem a coluna QUANTIDADE. "
                        "Sem ela nao da para controlar o saldo por pedido.")

        indices = (i_cid, i_ped, i_pro, i_ori)
        sem_origem = normalizar(STATUS_SEM_ORIGEM)
        for numero, linha in enumerate(linhas, start=2):
            if len(linha) <= max(indices):
                continue
            if all(linha[i] is None for i in indices):
                continue
            cidade, pedido, produto, origem = (linha[i] for i in indices)
            historico["chaves"].add(
                chave_da_linha(cidade, pedido, produto, origem))

            quantidade = 0.0
            if i_qtd is not None and i_qtd < len(linha):
                try:
                    quantidade = float(linha[i_qtd] or 0)
                except (TypeError, ValueError):
                    quantidade = 0.0

            item = item_do_pedido(cidade, pedido, produto)
            nao_atendida = normalizar(origem) == sem_origem
            historico["linhas"].append({
                "linha": numero,
                "item": item,
                "cidade": texto(cidade),
                "pedido": texto(pedido),
                "produto": texto(produto),
                "origem": texto(origem),
                "quantidade": quantidade,
                "sem_estoque": nao_atendida,
            })
            if nao_atendida:
                continue        # recado, nao compromisso: nao consome nada
            historico["solicitado"][item] = \
                historico["solicitado"].get(item, 0.0) + quantidade
            filial = texto(origem)
            historico["prometido_bruto"].setdefault(
                (filial, texto(produto).upper()), []).append((item, quantidade))
    finally:
        wb.close()

    log.info("  historico: %d linhas | %d itens de pedido ja atendidos",
             len(historico["linhas"]), len(historico["solicitado"]))
    return historico


def ler_chaves_existentes(caminho: Path) -> set:
    """Compatibilidade: so as chaves, sem o resto do historico."""
    return ler_historico_solicitacao(caminho)["chaves"]


def estilo_do_cabecalho(ws, ate_coluna: int | None = None) -> None:
    """Cabecalho verde escuro com fonte branca, congelado."""
    ultima = ate_coluna or ws.max_column
    for coluna in range(1, ultima + 1):
        celula = ws.cell(1, coluna)
        celula.font = Font(name=FONTE_PLANILHA, size=TAMANHO_FONTE, bold=True,
                           color=COR_FONTE_CABECALHO)
        celula.fill = PatternFill("solid", fgColor=COR_CABECALHO)
        celula.alignment = Alignment(horizontal="center", vertical="center",
                                     wrap_text=True)
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"


def estilo_da_linha(ws, linha: int, ate_coluna: int | None = None) -> None:
    """Calibri 9 em tudo o que o script escreve.

    (05/11, auditoria do robo) a fonte entra UMA vez na lista de estilos do
    arquivo e cada celula so recebe o numero dela: criar um Font() e
    procura-lo na lista a cada celula custava ~1 min por rodada no
    ESTOQUE_BAP. O resultado no Excel e o mesmo."""
    ultima = ate_coluna or ws.max_column
    fonte = Font(name=FONTE_PLANILHA, size=TAMANHO_FONTE)
    try:
        from openpyxl.styles.cell_style import StyleArray  # noqa: PLC0415
        fid = ws.parent._fonts.add(fonte)
    except Exception:                                    # noqa: BLE001
        fid = None
    for coluna in range(1, ultima + 1):
        cel = ws.cell(linha, coluna)
        if fid is None:
            cel.font = fonte
            continue
        if cel._style is None:
            cel._style = StyleArray()
        cel._style.fontId = fid


def renomear_abas_antigas(wb) -> None:
    """Coletas -> DETALHADO_PEDIDO, preservando tudo o que esta na aba."""
    for velho, novo in RENOMEAR_ABAS.items():
        if velho in wb.sheetnames and novo not in wb.sheetnames:
            wb[velho].title = novo
            log.info("  aba '%s' renomeada para '%s'", velho, novo)


def colunas_da_aba_resumo(nome_aba: str) -> list[str]:
    """Colunas de uma aba de solicitacao, na ordem em que sao criadas."""
    return (COLUNAS_RESUMO_BASE + CONTROLES_POR_ABA.get(nome_aba, [])
            + ["STATUS", COLUNA_CHAVE])


def chave_do_resumo(data, hora, produto, filial) -> str:
    """Liga uma linha da aba Coletas a sua linha na aba de solicitacao."""
    return "|".join((texto(data), texto(hora), texto(produto), texto(filial)))


def resumir_para_solicitacao(novas: pd.DataFrame, nome_aba: str,
                             tipos) -> pd.DataFrame:
    """
    Junta as linhas de coleta numa por produto + filial de origem: quantidade
    somada e os pedidos lado a lado em PEDIDOS. Sem NUM_PEDIDO nem CLIENTE -
    esse detalhe fica na aba Coletas.
    """
    recorte = novas if tipos is None else novas[novas["TIPO_ORIGEM"].isin(tipos)]
    if recorte.empty:
        return pd.DataFrame(columns=colunas_da_aba_resumo(nome_aba))

    juntos: dict[tuple, dict] = {}
    for _, linha in recorte.iterrows():
        cidade = texto(linha.get("CIDADE"))
        item = {
            "DATA": texto(linha.get("DATA")),
            "HORA": texto(linha.get("HORA")),
            "UF": UF_POR_CIDADE.get(normalizar(cidade).upper(), ""),
            "CIDADE": cidade,
            "COD_PRODUTO": texto(linha.get("COD_PRODUTO")),
            "ID_PRODUTO": texto(linha.get("ID_PRODUTO")),
            "COLETAR_EM": texto(linha.get("COLETAR_EM")),
            "FILIAL_DESTINO": texto(linha.get("FILIAL_DESTINO")),
        }
        chave = tuple(item[c] for c in CHAVE_RESUMO)
        destino = juntos.setdefault(chave, {**item, "QUANTIDADE": 0.0,
                                            "_pedidos": []})
        destino["QUANTIDADE"] += float(linha.get("QUANTIDADE") or 0)
        pedido = texto(linha.get("NUM_PEDIDO"))
        if pedido and pedido not in destino["_pedidos"]:
            destino["_pedidos"].append(pedido)

    linhas = []
    for item in juntos.values():
        pedidos = sorted(item.pop("_pedidos"),
                         key=lambda p: (len(p), p))   # 9 antes de 10
        item["PEDIDOS"] = SEPARADOR_PEDIDOS.join(pedidos)
        item["QUANTIDADE"] = round(item["QUANTIDADE"], 4)
        item["STATUS"] = STATUS_PADRAO
        item[COLUNA_CHAVE] = chave_do_resumo(
            item["DATA"], item["HORA"], item["COD_PRODUTO"], item["COLETAR_EM"])
        linhas.append(item)

    df = pd.DataFrame(linhas)
    for coluna in colunas_da_aba_resumo(nome_aba):
        if coluna not in df.columns:
            df[coluna] = None
    ordem = ["UF", "CIDADE", "COD_PRODUTO", "COLETAR_EM"]
    return df[colunas_da_aba_resumo(nome_aba)].sort_values(ordem)


def acrescentar_no_resumo(wb, nome_aba: str, resumo: pd.DataFrame) -> int:
    """Acrescenta as linhas de solicitacao, casando pelos titulos existentes."""
    if resumo.empty:
        return 0
    colunas = colunas_da_aba_resumo(nome_aba)

    if nome_aba not in wb.sheetnames:
        ws = wb.create_sheet(nome_aba)
        ws.append(colunas)
    ws = wb[nome_aba]
    estilo_do_cabecalho(ws)

    for coluna in range(1, ws.max_column + 1):
        atual = texto(ws.cell(1, coluna).value)
        for velho, novo in RENOMEAR_COLUNAS.items():
            if normalizar(atual) == normalizar(velho):
                ws.cell(1, coluna).value = novo

    cabecalho = mapear_cabecalhos(ws, 1)
    if not cabecalho:
        for indice, titulo in enumerate(colunas, start=1):
            ws.cell(1, indice).value = titulo
        cabecalho = mapear_cabecalhos(ws, 1)

    # Formato antigo: a aba tinha uma linha por pedido. Nao apagamos nada, mas
    # avisamos - as linhas novas vem agrupadas e essas colunas ficarao vazias.
    antigas = [c for c in ("NUM_PEDIDO", "CLIENTE")
               if normalizar(c) in cabecalho]
    if antigas:
        log.warning("  aba '%s' ainda tem as colunas %s do formato antigo. "
                    "As linhas novas vem agrupadas por produto+filial e "
                    "deixarao essas colunas em branco - o detalhe por pedido "
                    "esta na aba %s.", nome_aba, ", ".join(antigas), ABA_DETALHE)

    faltando = [c for c in colunas if normalizar(c) not in cabecalho]
    for titulo in faltando:
        coluna = ws.max_column + 1
        ws.cell(1, coluna).value = titulo
        cabecalho[normalizar(titulo)] = coluna
    if faltando:
        log.info("  aba '%s': criei as colunas %s", nome_aba, ", ".join(faltando))

    proxima = ultima_linha_com_dados(ws, 1) + 1
    for _, registro in resumo.iterrows():
        for titulo in colunas:
            coluna = cabecalho.get(normalizar(titulo))
            if not coluna:
                continue
            if titulo in COLUNAS_DO_TIME and titulo != "STATUS":
                continue          # ID_REVERSA e ID_SEPARACAO nascem vazias
            ws.cell(proxima, coluna).value = converter_valor(registro.get(titulo))
        estilo_da_linha(ws, proxima)
        proxima += 1
    return len(resumo)


def formulas_da_coletas(wb) -> dict[str, str]:
    """
    Monta, para cada coluna de formula da aba Coletas, um modelo com {chave}
    no lugar da expressao que forma a chave. Procura nas abas de solicitacao
    que realmente existem, na ordem CD -> Lojas -> FRW.
    """
    fontes: dict[str, tuple[str, dict]] = {}
    for nome_aba in CONTROLES_POR_ABA:
        if nome_aba in wb.sheetnames:
            fontes[nome_aba] = (nome_aba, mapear_cabecalhos(wb[nome_aba], 1))

    def busca(nome_aba: str, coluna_alvo: str) -> str | None:
        if nome_aba not in fontes:
            return None
        _, cabecalho = fontes[nome_aba]
        alvo = cabecalho.get(normalizar(coluna_alvo))
        chave = cabecalho.get(normalizar(COLUNA_CHAVE))
        if not alvo or not chave:
            return None
        letra_alvo = get_column_letter(alvo)
        letra_chave = get_column_letter(chave)
        return (f"INDEX('{nome_aba}'!${letra_alvo}:${letra_alvo},"
                f"MATCH({{chave}},'{nome_aba}'!${letra_chave}:${letra_chave},0))")

    def vazio_vira_branco(expressao: str) -> str:
        """Celula vazia no destino devolve 0 no INDEX; aqui vira branco."""
        return f'IF({expressao}="","",{expressao})'

    modelos: dict[str, str] = {}
    for coluna, aba in (("CONTROLE_SEP_CD", "Solicitacao CD"),
                        ("ID_SEPARACAO", "Solicitacao CD"),
                        ("CONTROLE_SEP_LOJA", "Solicitacao Lojas"),
                        ("ID_REVERSA", "Solicitacao Lojas")):
        expressao = busca(aba, coluna)
        if expressao:
            modelos[coluna] = f'=IFERROR({vazio_vira_branco(expressao)},"")'

    # STATUS pode vir de qualquer uma das tres abas
    partes = [busca(aba, "STATUS") for aba in
              ("Solicitacao CD", "Solicitacao Lojas", "Solicitacao FRW")]
    partes = [p for p in partes if p]
    if partes:
        formula = '""'
        for expressao in reversed(partes):
            formula = f"IFERROR({vazio_vira_branco(expressao)},{formula})"
        modelos["STATUS"] = "=" + formula
    return modelos


def acrescentar_na_aba(wb, nome_aba: str, novas: pd.DataFrame,
                       modelos: dict | None = None) -> int:
    """
    Acrescenta linhas ao fim da aba, casando pelos TITULOS existentes - assim
    a assistente pode reordenar colunas ou criar colunas proprias sem quebrar
    nada. Linhas antigas (e os STATUS que ela editou) nao sao tocadas.
    """
    if novas.empty:
        return 0

    if nome_aba not in wb.sheetnames:
        ws = wb.create_sheet(nome_aba)
        ws.append(COLUNAS_SOLICITACAO)
    ws = wb[nome_aba]
    estilo_do_cabecalho(ws)

    # migra titulos antigos antes de mapear, para nao criar coluna duplicada
    for coluna in range(1, ws.max_column + 1):
        atual = texto(ws.cell(1, coluna).value)
        for velho, novo in RENOMEAR_COLUNAS.items():
            if normalizar(atual) == normalizar(velho):
                ws.cell(1, coluna).value = novo
                log.info("  aba '%s': coluna '%s' renomeada para '%s'",
                         nome_aba, velho, novo)

    cabecalho = mapear_cabecalhos(ws, 1)
    if not cabecalho:
        for indice, titulo in enumerate(COLUNAS_SOLICITACAO, start=1):
            ws.cell(1, indice).value = titulo
        cabecalho = mapear_cabecalhos(ws, 1)

    faltando = [c for c in COLUNAS_SOLICITACAO if normalizar(c) not in cabecalho]
    for titulo in faltando:
        coluna = ws.max_column + 1
        ws.cell(1, coluna).value = titulo
        cabecalho[normalizar(titulo)] = coluna
    if faltando:
        log.info("  aba '%s': criei as colunas %s", nome_aba, ", ".join(faltando))

    # colunas que formam a chave da linha, para as formulas
    letras = {}
    for titulo in ("DATA", "HORA", "COD_PRODUTO", "COLETAR_EM"):
        indice = cabecalho.get(normalizar(titulo))
        if indice:
            letras[titulo] = get_column_letter(indice)
    pode_formular = len(letras) == 4

    proxima = ultima_linha_com_dados(ws, 1) + 1
    tipos_com_aba = {t for tipos in ABAS_SOLICITACAO.values() if tipos
                     for t in tipos}
    for _, registro in novas.iterrows():
        sem_origem = texto(registro.get("TIPO_ORIGEM")) not in tipos_com_aba
        chave = None
        if pode_formular and not sem_origem:
            chave = '&"|"&'.join(f"${letras[t]}{proxima}" for t in
                                 ("DATA", "HORA", "COD_PRODUTO", "COLETAR_EM"))
        for titulo in COLUNAS_SOLICITACAO:
            coluna = cabecalho.get(normalizar(titulo))
            if not coluna:
                continue
            if titulo in COLUNAS_POR_FORMULA:
                # o valor mora na aba de solicitacao; aqui e so espelho.
                # Linha sem origem nao tem aba de solicitacao: escreve direto.
                if sem_origem:
                    if titulo == "STATUS":
                        ws.cell(proxima, coluna).value = STATUS_SEM_ORIGEM
                    continue
                modelo = (modelos or {}).get(titulo)
                if modelo and chave:
                    ws.cell(proxima, coluna).value = modelo.format(chave=chave)
                continue
            celula = ws.cell(proxima, coluna)
            celula.value = converter_valor(registro.get(titulo))
            if titulo == "DT_PEDIDO" and isinstance(celula.value, (datetime, date)):
                celula.number_format = "DD/MM/YYYY"
        estilo_da_linha(ws, proxima)
        proxima += 1
    return len(novas)


def ultima_coluna_do_cabecalho(ws) -> int:
    """
    Ultimo titulo REALMENTE preenchido na linha 1. ws.max_column conta celula
    so formatada, e usar ele deixava colunas em branco no meio da planilha.
    """
    ultima = 0
    for coluna in range(1, ws.max_column + 1):
        if texto(ws.cell(1, coluna).value):
            ultima = coluna
    return ultima


def limpar_colunas_vazias(ws) -> int:
    """
    Apaga colunas sem titulo que ficaram no MEIO do cabecalho. Versoes antigas
    criavam a coluna nova em ws.max_column + 1, que conta celula so formatada -
    e sobrava um buraco entre os titulos. Conserta o que ja esta assim.
    """
    ultima = ultima_coluna_do_cabecalho(ws)
    vazias = [c for c in range(1, ultima) if not texto(ws.cell(1, c).value)]
    for coluna in reversed(vazias):
        ws.delete_cols(coluna)
    return len(vazias)


# --------------------------------------------------------------------------
# AS DUAS LISTAS DE EXCLUSAO, agora dentro da SOLICITACAO_BAP
#
# Elas nasceram na TABELA_BAP, que e REGERADA a cada rodada do BAP Tools:
# o que voce escrevia la ia embora junto. Aqui, no arquivo de solicitacao,
# elas ficam. Escreveu, vale - hoje, amanha e depois da proxima carga.
#
# Na primeira rodada, se a TABELA_BAP ainda tiver as abas antigas com
# conteudo, ele e copiado para ca e a partir dai a SOLICITACAO_BAP manda.
# --------------------------------------------------------------------------
ABA_PRODUTOS_EXCLUIR = "ProdutosExcluir"
ABA_FILIAIS_EXCLUIR = "FiliaisExcluir"
COLUNAS_PRODUTOS_EXCLUIR = ["Filial", "Forn", "Cód", "ID_PRODUTO"]
COLUNAS_FILIAIS_EXCLUIR = ["Filial"]

AJUDA_EXCLUSAO = {
    ABA_PRODUTOS_EXCLUIR: (
        "Produto que NAO pode ser coletado naquela filial. Uma linha por "
        "par: escreva a Filial e o Cód do produto (o ID_PRODUTO ajuda, mas "
        "o Cód ja basta). Vale a partir da proxima rodada."),
    ABA_FILIAIS_EXCLUIR: (
        "Filial que fica FORA da coleta, para qualquer produto. Uma linha "
        "por filial. Vale a partir da proxima rodada."),
}


def ler_abas_de_exclusao(wb) -> dict:
    """{aba -> lista de linhas}, como dicionarios de titulo -> valor."""
    saida = {ABA_PRODUTOS_EXCLUIR: [], ABA_FILIAIS_EXCLUIR: []}
    for nome in saida:
        if nome not in wb.sheetnames:
            continue
        ws = wb[nome]
        cabecalho = mapear_cabecalhos(ws, 1)
        if not cabecalho:
            continue
        for linha in range(2, ultima_linha_com_dados(ws, 1) + 1):
            registro = {titulo: texto(ws.cell(linha, indice).value)
                        for titulo, indice in cabecalho.items()}
            if any(registro.values()):
                saida[nome].append(registro)
    return saida


def garantir_abas_de_exclusao(wb, historico: dict | None = None) -> dict:
    """
    Cria as abas na SOLICITACAO_BAP se faltarem e, na primeira vez, traz o
    que estava na TABELA_BAP. Nunca apaga o que voce escreveu.
    """
    herdado = (historico or {}).get("exclusao_da_tabela") or {}
    resumo = {}
    for nome, colunas in ((ABA_PRODUTOS_EXCLUIR, COLUNAS_PRODUTOS_EXCLUIR),
                          (ABA_FILIAIS_EXCLUIR, COLUNAS_FILIAIS_EXCLUIR)):
        nova = nome not in wb.sheetnames
        if nova:
            ws = wb.create_sheet(nome)
            ws.append(colunas)
        ws = wb[nome]
        cabecalho = mapear_cabecalhos(ws, 1)
        if not cabecalho:
            for indice, titulo in enumerate(colunas, start=1):
                ws.cell(1, indice).value = titulo
            cabecalho = mapear_cabecalhos(ws, 1)
        for titulo in colunas:
            if normalizar(titulo) not in cabecalho:
                indice = ultima_coluna_do_cabecalho(ws) + 1
                ws.cell(1, indice).value = titulo
                cabecalho[normalizar(titulo)] = indice
        estilo_do_cabecalho(ws)
        for indice, titulo in enumerate(colunas, start=1):
            ws.column_dimensions[get_column_letter(indice)].width = max(
                14, len(titulo) + 4)

        # a migracao: so na primeira vez, e so se a aba estiver vazia
        trazidas = 0
        if ultima_linha_com_dados(ws, 1) < 2 and herdado.get(nome):
            proxima = 2
            for registro in herdado[nome]:
                for titulo in colunas:
                    coluna = cabecalho.get(normalizar(titulo))
                    if coluna:
                        ws.cell(proxima, coluna).value = registro.get(
                            normalizar(titulo)) or None
                proxima += 1
                trazidas += 1
            log.info("  %s: %d linha(s) trazidas da TABELA_BAP para o %s.",
                     nome, trazidas, ARQUIVO_SOLICITACAO)
        # o recado de como usar, embaixo do cabecalho, so quando a aba
        # acabou de nascer vazia
        if nova and not trazidas:
            ws.cell(3, 1).value = AJUDA_EXCLUSAO[nome]
            ws.cell(3, 1).font = Font(name=FONTE_PLANILHA, size=8,
                                      italic=True, color="808080")
        resumo[nome] = trazidas
    return resumo


def aplicar_lista_de_opcoes(ws, titulo: str, opcoes: list) -> bool:
    """
    Transforma a coluna numa LISTA SUSPENSA do Excel: quem preenche escolhe,
    nao digita. Isso e o que impede "REVERSA GERADA " com espaco no fim, ou
    "CANCELADO" escrito de tres jeitos - e o script compara esses valores
    para decidir o que mexer e o que nao mexer.

    A validacao vale da linha 2 ate o fim da planilha, entao linha nova ja
    nasce com a lista. Quem estiver fora dela nao e apagado: o Excel so
    marca como invalido, e a pessoa corrige.
    """
    cabecalho = mapear_cabecalhos(ws, 1)
    coluna = cabecalho.get(normalizar(titulo))
    if not coluna:
        return False
    letra = get_column_letter(coluna)
    faixa = f"{letra}2:{letra}{MAXIMO_LINHAS_EXCEL}"
    lista = '"' + ",".join(opcoes) + '"'
    # se ja existe uma validacao igual nessa coluna, nao duplica
    for validacao in list(ws.data_validations.dataValidation):
        if validacao.sqref is not None and faixa in str(validacao.sqref):
            if validacao.formula1 == lista:
                return True
            ws.data_validations.dataValidation.remove(validacao)
    validacao = DataValidation(type="list", formula1=lista, allow_blank=True,
                               showDropDown=False, showErrorMessage=True,
                               errorTitle="Valor fora da lista",
                               error="Escolha uma das opcoes da lista.",
                               promptTitle=titulo,
                               prompt="Escolha uma das opcoes.")
    ws.add_data_validation(validacao)
    validacao.add(faixa)
    return True


def aplicar_listas_da_solicitacao(wb) -> int:
    """As listas suspensas em todas as abas do arquivo de solicitacao."""
    quantas = 0
    for nome_aba in list(ABAS_SOLICITACAO):
        if nome_aba not in wb.sheetnames:
            continue
        ws = wb[nome_aba]
        if aplicar_lista_de_opcoes(ws, COLUNA_SITUACAO, OPCOES_SITUACAO):
            quantas += 1
        if aplicar_lista_de_opcoes(ws, "STATUS", OPCOES_STATUS):
            quantas += 1
    return quantas


def garantir_coluna(ws, titulo: str) -> tuple:
    """Devolve (cabecalho, indice_da_coluna), criando a coluna se faltar."""
    cabecalho = mapear_cabecalhos(ws, 1)
    indice = cabecalho.get(normalizar(titulo))
    if not indice:
        indice = ultima_coluna_do_cabecalho(ws) + 1
        ws.cell(1, indice).value = titulo
        estilo_do_cabecalho(ws)
        cabecalho[normalizar(titulo)] = indice
    return cabecalho, indice


def limpar_sem_estoque(wb, situacao: dict) -> int:
    """
    Apaga as linhas SEM ESTOQUE de pedidos que continuam EM ABERTO - elas sao
    recalculadas do zero a cada rodada, porque pode ter entrado mercadoria.
    Linhas com origem de verdade (que viraram SEP) nunca sao tocadas, e as
    linhas SEM ESTOQUE de pedido faturado/excluido ficam como historico.
    """
    if ABA_DETALHE not in wb.sheetnames:
        return 0
    ws = wb[ABA_DETALHE]
    cabecalho = mapear_cabecalhos(ws, 1)
    i_cid = cabecalho.get(normalizar("CIDADE"))
    i_ped = cabecalho.get(normalizar("NUM_PEDIDO"))
    i_pro = cabecalho.get(normalizar("ID_PRODUTO"))
    i_ori = cabecalho.get(normalizar("COLETAR_EM"))
    if not all((i_cid, i_ped, i_pro, i_ori)):
        return 0

    alvo = normalizar(STATUS_SEM_ORIGEM)
    apagar = []
    for linha in range(2, ultima_linha_com_dados(ws, 1) + 1):
        if normalizar(ws.cell(linha, i_ori).value) != alvo:
            continue
        item = item_do_pedido(ws.cell(linha, i_cid).value,
                              ws.cell(linha, i_ped).value,
                              ws.cell(linha, i_pro).value)
        if situacao.get(item) == SITUACAO_ABERTO:
            apagar.append(linha)

    for linha in reversed(apagar):      # de baixo para cima, senao desalinha
        ws.delete_rows(linha)
    if apagar:
        log.info("    %-20s -%d linha(s) SEM ESTOQUE (recalculadas)",
                 ABA_DETALHE, len(apagar))
    return len(apagar)


def refazer_formulas_detalhe(wb, modelos: dict) -> int:
    """
    Reescreve as formulas da aba de detalhe linha a linha. Necessario depois
    de apagar linhas: o openpyxl move as celulas, mas nao corrige a referencia
    escrita dentro da formula. Como todas apontam para a PROPRIA linha, refazer
    e barato e ainda conserta formula quebrada de rodadas antigas.
    """
    if ABA_DETALHE not in wb.sheetnames or not modelos:
        return 0
    ws = wb[ABA_DETALHE]
    cabecalho = mapear_cabecalhos(ws, 1)
    letras = {}
    for titulo in ("DATA", "HORA", "COD_PRODUTO", "COLETAR_EM"):
        indice = cabecalho.get(normalizar(titulo))
        if indice:
            letras[titulo] = get_column_letter(indice)
    if len(letras) != 4:
        return 0
    i_ori = cabecalho.get(normalizar("COLETAR_EM"))
    alvo = normalizar(STATUS_SEM_ORIGEM)

    refeitas = 0
    for linha in range(2, ultima_linha_com_dados(ws, 1) + 1):
        sem_origem = normalizar(ws.cell(linha, i_ori).value) == alvo
        chave = '&"|"&'.join(f"${letras[t]}{linha}" for t in
                             ("DATA", "HORA", "COD_PRODUTO", "COLETAR_EM"))
        for titulo in COLUNAS_POR_FORMULA:
            coluna = cabecalho.get(normalizar(titulo))
            if not coluna:
                continue
            celula = ws.cell(linha, coluna)
            if sem_origem:
                # nao existe aba de solicitacao para essa linha
                if titulo == "STATUS":
                    atual = texto(celula.value)
                    if not atual or atual == STATUS_SEM_ORIGEM:
                        celula.value = STATUS_SEM_ORIGEM
                else:
                    celula.value = None
                continue
            modelo = modelos.get(titulo)
            if modelo:
                celula.value = modelo.format(chave=chave)
                refeitas += 1
    return refeitas


def atualizar_situacao(wb, situacao: dict) -> dict:
    """
    Reescreve a coluna SITUACAO_PEDIDO em todas as abas, a cada rodada.
    E a UNICA coluna que o script atualiza numa linha ja gravada - ele nunca
    encosta em STATUS, ID_SEPARACAO ou ID_REVERSA depois de criar a linha.

    No detalhe: EM ABERTO / FATURADO / EXCLUIDO, por item de pedido.
    Nas abas de solicitacao (uma linha reune varios pedidos): EM ABERTO
    enquanto sobrar algum pedido vivo, ENCERRADO quando todos sairam.
    """
    contagem = {SITUACAO_ABERTO: 0, SITUACAO_FATURADO: 0,
                SITUACAO_EXCLUIDO: 0, SITUACAO_ENCERRADO: 0}

    if ABA_DETALHE in wb.sheetnames:
        ws = wb[ABA_DETALHE]
        cabecalho, coluna = garantir_coluna(ws, COLUNA_SITUACAO)
        cabecalho, i_motivo = garantir_coluna(ws, COLUNA_MOTIVO)
        i_cid = cabecalho.get(normalizar("CIDADE"))
        i_ped = cabecalho.get(normalizar("NUM_PEDIDO"))
        i_pro = cabecalho.get(normalizar("ID_PRODUTO"))
        if all((i_cid, i_ped, i_pro)):
            for linha in range(2, ultima_linha_com_dados(ws, 1) + 1):
                item = item_do_pedido(ws.cell(linha, i_cid).value,
                                      ws.cell(linha, i_ped).value,
                                      ws.cell(linha, i_pro).value)
                bruto = situacao.get(item, SITUACAO_EXCLUIDO)
                valor = (SITUACAO_ABERTO if bruto == SITUACAO_ABERTO
                         else SITUACAO_ENCERRADO)
                celula = ws.cell(linha, coluna)
                celula.value = valor
                celula.font = Font(name=FONTE_PLANILHA, size=TAMANHO_FONTE)
                # o MOTIVO guarda o que a situacao deixou de dizer
                if i_motivo:
                    motivo = ws.cell(linha, i_motivo)
                    motivo.value = ("" if bruto == SITUACAO_ABERTO else bruto)
                    motivo.font = Font(name=FONTE_PLANILHA,
                                       size=TAMANHO_FONTE)
                contagem[bruto] = contagem.get(bruto, 0) + 1

    for nome_aba in CONTROLES_POR_ABA:
        if nome_aba not in wb.sheetnames:
            continue
        ws = wb[nome_aba]
        cabecalho, coluna = garantir_coluna(ws, COLUNA_SITUACAO)
        i_cid = cabecalho.get(normalizar("CIDADE"))
        i_pro = cabecalho.get(normalizar("ID_PRODUTO"))
        i_ped = cabecalho.get(normalizar("PEDIDOS"))
        if not all((i_cid, i_pro, i_ped)):
            continue
        for linha in range(2, ultima_linha_com_dados(ws, 1) + 1):
            cidade = ws.cell(linha, i_cid).value
            produto = ws.cell(linha, i_pro).value
            juntos = texto(ws.cell(linha, i_ped).value)
            pedidos = [p for p in juntos.split(SEPARADOR_PEDIDOS) if p.strip()]
            vivo = any(situacao.get(item_do_pedido(cidade, p, produto))
                       == SITUACAO_ABERTO for p in pedidos)
            valor = SITUACAO_ABERTO if vivo else SITUACAO_ENCERRADO
            celula = ws.cell(linha, coluna)
            celula.value = valor
            celula.font = Font(name=FONTE_PLANILHA, size=TAMANHO_FONTE)
            if not vivo:
                contagem[SITUACAO_ENCERRADO] += 1

    resumo = ", ".join(f"{quantas} {nome.lower()}"
                       for nome, quantas in contagem.items() if quantas)
    if resumo:
        log.info("  situacao dos pedidos: %s", resumo)
    return contagem


def nome_para_arquivo(texto_bruto) -> str:
    """BELÉM -> BELEM | SÃO LUIS -> SAOLUIS. Nome de arquivo sem acento nem espaco."""
    limpo = unicodedata.normalize("NFKD", str(texto_bruto or ""))
    limpo = "".join(c for c in limpo if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]", "", limpo).upper()


def nome_csv(data: str, numero: int, local: str, tipo: str) -> str:
    """240826_001_BELEM_BAPReversaLoja.csv"""
    return f"{data}_{numero:03d}_{local}_{tipo}.csv"


def proximo_numero(pasta: Path, local: str, tipo: str) -> int:
    """
    Le a pasta e continua de onde parou. A sequencia e por local + tipo:
    240826_007_BELEM_BAPReversaLoja -> o proximo de BELEM e 008, sem mexer
    nas outras cidades nem na sequencia de separacao de CD.
    """
    padrao = re.compile(
        rf"^(\d{{6}})_(\d+)_{re.escape(local)}_{re.escape(tipo)}\.csv$", re.I)
    maior = 0
    if pasta.is_dir():
        for arquivo in pasta.glob(f"*_{local}_{tipo}.csv"):
            achado = padrao.match(arquivo.name)
            if achado:
                maior = max(maior, int(achado.group(2)))
    return maior + 1


def escrever_csv_importacao(caminho: Path, linhas: list[dict]) -> None:
    """Formato do importador: ';' como separador, quebra CRLF, UTF-8."""
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=CSV_SEPARADOR, lineterminator="\r\n")
        escritor.writerow(CSV_CABECALHO)
        for linha in linhas:
            escritor.writerow([
                linha["origem"], EMPRESA_PADRAO, linha["fornecedor"],
                linha["produto"], linha["destino"],
                int(linha["quantidade"]) if float(linha["quantidade"]).is_integer()
                else linha["quantidade"],
            ])


def gerar_csvs_importacao(novas: pd.DataFrame, simular: bool) -> dict:
    """
    Um CSV por CIDADE com a reversa de loja e um CSV por CD com a separacao.
    Devolve o numero de cada arquivo, para atrelar aos pedidos na planilha.
    """
    pasta = PASTA_LOCAL / SUBPASTA_IMPORTAR
    if simular:
        pasta = pasta / "SIMULACAO"
    pasta.mkdir(parents=True, exist_ok=True)

    data = datetime.now().strftime("%d%m%y")
    numeros = {"loja": {}, "cd": {}}     # chave -> numero atribuido
    gerados = []

    def agrupar(recorte: pd.DataFrame) -> list[dict]:
        """Uma linha por origem+produto; quantidades somadas."""
        juntos: dict[tuple, dict] = {}
        for _, linha in recorte.iterrows():
            origem = texto(linha.get("COLETAR_EM"))
            produto = texto(linha.get("COD_PRODUTO"))
            fornecedor = texto(linha.get("FORNECEDOR"))
            destino = texto(linha.get("FILIAL_DESTINO"))
            if not origem or not produto:
                continue
            chave = (origem, fornecedor, produto, destino)
            item = juntos.setdefault(chave, {
                "origem": origem, "fornecedor": fornecedor,
                "produto": produto, "destino": destino, "quantidade": 0.0})
            item["quantidade"] += float(linha.get("QUANTIDADE") or 0)
        return sorted(juntos.values(), key=lambda i: (i["origem"], i["produto"]))

    # ---- reversa de loja: um arquivo por cidade --------------------------
    lojas = novas[novas["TIPO_ORIGEM"].isin(("LOJA PREFERENCIAL", "LOJA"))]
    for cidade in sorted(lojas["CIDADE"].dropna().unique()):
        linhas = agrupar(lojas[lojas["CIDADE"] == cidade])
        if not linhas:
            continue
        local = nome_para_arquivo(cidade)
        numero = proximo_numero(pasta, local, SUFIXO_REVERSA)
        arquivo = pasta / nome_csv(data, numero, local, SUFIXO_REVERSA)
        escrever_csv_importacao(arquivo, linhas)
        numeros["loja"][cidade] = f"{numero:03d}"
        gerados.append((arquivo.name, len(linhas)))

    # ---- separacao de CD: um arquivo por CD ------------------------------
    # O nome usa a CIDADE do CD. Quando a cidade tem mais de um CD (Santarem
    # tem o 27 e o 62), cada um ganha seu proprio numero na sequencia - o CD
    # exato fica na coluna FILIAL ORIGEM do arquivo e no COLETAR_EM da planilha.
    cds = novas[novas["TIPO_ORIGEM"] == "CD"]
    for cd in sorted(cds["COLETAR_EM"].dropna().unique(), key=texto):
        recorte = cds[cds["COLETAR_EM"] == cd]
        linhas = agrupar(recorte)
        if not linhas:
            continue
        cidade = recorte["CIDADE"].iloc[0]
        local = nome_para_arquivo(cidade)
        numero = proximo_numero(pasta, local, SUFIXO_SEPARACAO)
        arquivo = pasta / nome_csv(data, numero, local, SUFIXO_SEPARACAO)
        escrever_csv_importacao(arquivo, linhas)
        numeros["cd"][texto(cd)] = f"{numero:03d}"
        gerados.append((arquivo.name, len(linhas)))

    if gerados:
        log.info("  %d arquivo(s) CSV em %s", len(gerados), pasta)
        for nome, quantas in gerados:
            log.info("    %-40s %d linha(s)", nome, quantas)
    else:
        log.info("  nenhuma reversa de loja nem separacao de CD desta vez.")

    return {"numeros": numeros, "arquivos": [n for n, _ in gerados], "pasta": str(pasta)}


def acumular_solicitacao(df: pd.DataFrame, armazenamento, simular: bool,
                         existente: Path | None = None,
                         historico: dict | None = None,
                         contexto: dict | None = None) -> dict:
    agora = datetime.now()
    contexto = contexto or {}
    situacao = contexto.get("situacao", {})
    excessos = contexto.get("excessos", [])

    df = df.copy() if df is not None else pd.DataFrame()
    if not df.empty:
        df["DATA"] = agora.strftime("%d/%m/%Y")
        df["HORA"] = agora.strftime("%H:%M")
        df["STATUS"] = STATUS_PADRAO
    for coluna in COLUNAS_SOLICITACAO:
        if coluna not in df.columns:
            df[coluna] = None
    # FORNECEDOR e FILIAL_DESTINO nao vao para a aba de detalhe, mas sao usados
    # nos CSVs de importacao e nas abas de solicitacao.
    auxiliares = [c for c in ("FORNECEDOR", "FILIAL_DESTINO") if c in df.columns]
    df = df[COLUNAS_SOLICITACAO + auxiliares]

    # ---- historico ja lido em preparar_historico() ------------------------
    local = PASTA_TEMP / ARQUIVO_SOLICITACAO
    oficial = caminho_da_solicitacao(simular=False)
    if historico is None:
        # chamada direta (testes, uso avulso): le agora
        existente, historico, erro = preparar_historico(simular)
        if erro:
            return {"linhas": 0, "arquivo": ARQUIVO_SOLICITACAO, "erro": erro}
    if existente is None:
        existente = historico.get("arquivo")

    # As linhas SEM ESTOQUE sao apagadas e refeitas a cada rodada, entao NAO
    # podem entrar na chave que filtra o que ja existe - senao seriam apagadas
    # e nunca regravadas, e a falta some do arquivo.
    marca_sem_estoque = texto(STATUS_SEM_ORIGEM).upper()
    ja_solicitado = {c for c in historico.get("chaves", set())
                     if c[3] != marca_sem_estoque}

    # Sem historico, TODA coleta em aberto vira "nova" e ganha SEP nova - em
    # cima das que o time ja abriu. Vale um aviso bem visivel.
    if not ja_solicitado and not simular:
        log.warning("=" * 70)
        log.warning("ATENCAO: nao achei historico de solicitacoes.")
        log.warning("  procurado em: %s", oficial)
        log.warning("  Se ja existem coletas abertas, elas serao solicitadas de")
        log.warning("  novo, com SEPs novas. Se o arquivo antigo existir em outra")
        log.warning("  pasta, cancele, coloque-o no caminho acima e rode de novo.")
        log.warning("=" * 70)

    # Rede de seguranca: se o historico esta vazio mas ja existem CSVs na pasta
    # de importacao, alguem apagou ou recriou a planilha. Tudo seria tratado
    # como novo e ganharia SEP nova, em cima de pedidos ja atendidos.
    if not ja_solicitado:
        pasta_csv = PASTA_LOCAL / SUBPASTA_IMPORTAR
        antigos = list(pasta_csv.glob("*.csv")) if pasta_csv.is_dir() else []
        if antigos:
            log.warning("=" * 66)
            log.warning("ATENCAO: o historico da SOLICITACAO_BAP esta vazio, mas ja")
            log.warning("existem %d arquivo(s) CSV em '%s'.", len(antigos),
                        SUBPASTA_IMPORTAR)
            log.warning("Isso significa que a planilha foi apagada ou recriada.")
            log.warning("TUDO sera tratado como novo e vai receber SEP nova, mesmo")
            log.warning("o que ja foi solicitado antes. Se nao e isso que voce quer,")
            log.warning("interrompa agora e restaure a SOLICITACAO_BAP anterior.")
            log.warning("=" * 66)

    # ---- separa o que e novo ---------------------------------------------
    # A chave e so a rede de seguranca contra linha identica. Quem impede
    # pedir demais e o saldo por pedido, ja aplicado na alocacao.
    if df.empty:
        novas, repetidas = df, 0
    else:
        marca_nova = [
            chave_da_linha(l["CIDADE"], l["NUM_PEDIDO"], l["ID_PRODUTO"],
                           l["COLETAR_EM"]) not in ja_solicitado
            for _, l in df.iterrows()
        ]
        novas = df[pd.Series(marca_nova, index=df.index)]
        repetidas = len(df) - len(novas)

    # ---- gera os CSVs ANTES da planilha, para atrelar os numeros ---------
    csvs = {"numeros": {"loja": {}, "cd": {}}, "arquivos": []}
    if novas.empty:
        log.info("  nenhuma linha nova a gravar (%d ja constavam no %s).",
                 repetidas, ARQUIVO_SOLICITACAO)
    else:
        log.info("  %d linhas novas (%d ja estavam la) | %d pedidos",
                 len(novas), repetidas, novas["NUM_PEDIDO"].nunique())
        if GERAR_CSV_IMPORTACAO:
            try:
                csvs = gerar_csvs_importacao(novas, simular)
            except Exception as erro:
                log.error("Nao consegui gerar os CSVs de importacao: %s", erro)
                log.debug("", exc_info=True)

    novas = novas.copy()

    # ---- acrescenta em cada aba ------------------------------------------
    if existente:
        wb = load_workbook(existente)
        renomear_abas_antigas(wb)
    elif novas.empty:
        log.info("  nada a gravar e nenhum arquivo anterior: nada a fazer.")
        return {"linhas": 0, "repetidas": repetidas, "novos_pedidos": 0,
                "arquivo": ARQUIVO_SOLICITACAO, "excessos": excessos}
    else:
        wb = Workbook()
        wb.remove(wb.active)
        log.info("  criando o %s pela primeira vez", ARQUIVO_SOLICITACAO)

    # As abas de solicitacao vem PRIMEIRO: a aba Coletas aponta para elas por
    # formula, entao precisam existir (e ter cabecalho) antes.
    resumo_abas = {}
    for nome_aba, tipos in ABAS_SOLICITACAO.items():
        if nome_aba == ABA_DETALHE:
            continue
        resumo = resumir_para_solicitacao(novas, nome_aba, tipos)
        if not resumo.empty:
            # o numero do CSV gerado nesta rodada
            if "CONTROLE_SEP_LOJA" in resumo.columns:
                resumo["CONTROLE_SEP_LOJA"] = [
                    csvs["numeros"]["loja"].get(c, "") for c in resumo["CIDADE"]]
            if "CONTROLE_SEP_CD" in resumo.columns:
                resumo["CONTROLE_SEP_CD"] = [
                    csvs["numeros"]["cd"].get(texto(f), "")
                    for f in resumo["COLETAR_EM"]]
        resumo_abas[nome_aba] = acrescentar_no_resumo(wb, nome_aba, resumo)

    # As linhas SEM ESTOQUE sao um recado, nao um compromisso: apaga as dos
    # pedidos ainda em aberto e regrava a falta de hoje. Linhas com origem de
    # verdade (que viraram SEP) nunca sao tocadas.
    apagadas = limpar_sem_estoque(wb, situacao)

    modelos = formulas_da_coletas(wb)
    resumo_abas[ABA_DETALHE] = acrescentar_na_aba(wb, ABA_DETALHE, novas, modelos)

    # Apagar linha desloca as de baixo, mas nao corrige a referencia escrita
    # dentro da formula. Como toda formula aponta para a propria linha, refazer
    # e barato e ainda conserta formula quebrada de rodadas antigas.
    if apagadas:
        refazer_formulas_detalhe(wb, modelos)

    # Unica coluna que o script atualiza em linha ja gravada.
    atualizar_situacao(wb, situacao)

    # As listas suspensas: SITUACAO_PEDIDO e STATUS viram escolha, nao
    # digitacao. E as abas de exclusao, que agora moram aqui.
    aplicar_listas_da_solicitacao(wb)
    garantir_abas_de_exclusao(wb, historico)

    # Se o Excel nao estiver disponivel para recalcular, ao menos garante que
    # ele refaz tudo assim que alguem abrir o arquivo.
    try:
        wb.calculation.fullCalcOnLoad = True
    except Exception:
        pass
    wb.save(local)
    wb.close()

    for nome_aba, quantas in resumo_abas.items():
        log.info("    %-20s +%d linha(s)", nome_aba, quantas)

    if simular:
        destino = caminho_da_solicitacao(simular=True)
        shutil.copy2(local, destino)
        log.warning("  [simulacao] solicitacao gravada so no arquivo de teste: %s",
                    destino)
    else:
        try:
            # (05/11) aberta no Excel: o aviso antes; sem resposta, cai no
            # NAO_GRAVADO de sempre
            if aguardar_arquivo_livre(oficial, "gravar a solicitacao") \
                    != "livre":
                raise PermissionError(f"{ARQUIVO_SOLICITACAO} em aberto")
            os.replace(local, oficial)
            destino = str(oficial)
            log.info("  Solicitacao acumulada em %s", destino)
            # As colunas CONTROLE_SEP_* e STATUS da aba de detalhe sao formula:
            # sem recalcular, ficam vazias para quem le o arquivo sem o Excel.
            recalcular_com_excel(oficial, ARQUIVO_SOLICITACAO)
        except Exception as erro:
            # Cenario tipico: a assistente esta com o arquivo aberto no Excel.
            # Guardamos a versao pronta ao lado, com a hora no nome, para nada
            # se perder - e o proximo ciclo reencontra tudo pela chave.
            reserva = (PASTA_LOCAL /
                       f"NAO_GRAVADO_{datetime.now():%Y%m%d_%H%M}_{ARQUIVO_SOLICITACAO}")
            shutil.copy2(local, reserva)
            log.error("Nao consegui gravar o %s: %s", ARQUIVO_SOLICITACAO, erro)
            log.error("Provavelmente alguem esta com ele aberto no Excel. "
                      "A versao completa ficou em %s", reserva)
            return {"arquivo": ARQUIVO_SOLICITACAO, "linhas": 0,
                    "repetidas": repetidas, "novos_pedidos": 0,
                    "erro": f"gravacao bloqueada: {erro}",
                    "copia_de_seguranca": str(reserva)}

    return {
        "arquivo": ARQUIVO_SOLICITACAO,
        "linhas": len(novas),
        "repetidas": repetidas,
        "novos_pedidos": int(novas["NUM_PEDIDO"].nunique()) if not novas.empty else 0,
        "por_aba": resumo_abas,
        "unidades_novas": float(novas["QUANTIDADE"].sum()) if not novas.empty else 0.0,
        "sem_estoque_recalculadas": apagadas,
        "excessos": excessos,
        "csv_gerados": csvs.get("arquivos", []),
        "pasta_csv": csvs.get("pasta"),
    }


# ==============================================================================
#                      TABELA DE PRECO: ONTEM x HOJE
# ==============================================================================

def pasta_das_fotos_de_preco() -> Path:
    pasta = PASTA_LOCAL / SUBPASTA_FOTOS_PRECO
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def ler_tabela_de_preco(caminho_planilha: Path, aba: str | None = None) -> dict:
    """
    Le a aba de precos e devolve {(filial, tabela, produto): (preco, descricao)}.

    A aba tem DA1_FILIAL duas vezes; ler_aba ja fica com a coluna crua. Quando
    a mesma chave aparece repetida, vale a ULTIMA linha - e o que o Protheus
    mostra na tela.

    'aba' permite ler o RELATORIO baixado (que tem uma aba so, 'Resultado')
    com exatamente a mesma regra da TABELA_BAP - importante para montar o
    historico antigo sem inventar diferenca que nao existe.
    """
    precos: dict[tuple, tuple] = {}
    nomes = abas_da_planilha(caminho_planilha)
    nome = aba or ABA_TABELA_PRECO
    if nome not in nomes:
        if aba is None and len(nomes) == 1:
            nome = next(iter(nomes))        # o relatorio cru
        else:
            log.warning("Aba '%s' nao existe: nao da para comparar precos.",
                        nome)
            return precos
    calculadas = calculadas_das_abas(caminho_planilha, [nome])[nome]

    wb = _abrir_valores(caminho_planilha)
    try:
        tabela = ler_aba(wb, nome, calculadas=calculadas)
    finally:
        wb.close()
    if tabela.empty:
        log.warning("Aba '%s' vazia: nao da para comparar precos.", nome)
        return precos

    def achar(candidatas):
        for candidata in candidatas:
            if normalizar(candidata) in tabela.columns:
                return normalizar(candidata)
        return None

    c_fil = achar(COLS_PRECO_FILIAL)
    c_tab = achar(COLS_PRECO_TABELA)
    c_pro = achar(COLS_PRECO_PRODUTO)
    c_val = achar(COLS_PRECO_VALOR)
    c_des = achar(COLS_PRECO_DESCRICAO)
    if not all((c_fil, c_pro, c_val)):
        log.warning("Aba '%s': nao achei filial/produto/preco. Colunas: %s",
                    ABA_TABELA_PRECO, list(tabela.columns))
        return precos

    def filial_longa(valor) -> str:
        """
        A aba tem DA1_FILIAL duas vezes: '40101001' e '0101001'. Deixa sempre
        na forma longa, que e a usada no resto da automacao.
        """
        bruto = texto(valor)
        if bruto.startswith("0101") and len(bruto) == 7:
            return "4" + bruto
        return bruto

    repetidas = 0
    for _, linha in tabela.iterrows():
        filial = filial_longa(linha.get(c_fil))
        produto = texto(linha.get(c_pro))
        if not filial or not produto:
            continue
        try:
            valor = float(linha.get(c_val) or 0)
        except (TypeError, ValueError):
            continue
        if valor <= 0:
            continue
        chave = (filial, texto(linha.get(c_tab)) if c_tab else "", produto)
        if chave in precos:
            repetidas += 1
        precos[chave] = (round(valor, 4),
                         texto(linha.get(c_des)) if c_des else "")
    if repetidas:
        log.debug("  tabela de preco: %d chave(s) repetida(s); fiquei com a "
                  "ultima linha de cada.", repetidas)
    return precos


def ler_estoque_por_filial_bap(caminho_planilha: Path) -> tuple:
    """
    Estoque disponivel das lojas PMZ somado por FILIAL BAP.

    A aba ftEstoquePMZ traz a LOJA (6, 7, 46...). A aba Filiais liga cada loja
    a sua filial BAP (Filiais.COD_FILIAL -> Filiais.FILIAL_BAP), que e a mesma
    granularidade da tabela de preco. O produto casa por ftEstoquePMZ.PRODUTO
    = ftTabelaPreco.DA1_CODPRO.

    Devolve ({(filial_bap, produto): qtd}, [filiais em ordem], {filial: cidade}).
    """
    vazio: dict[tuple, float] = {}
    nomes = abas_da_planilha(caminho_planilha)
    precisa = [a for a in ("Filiais", ABA_ESTOQUE_PMZ) if a in nomes]
    if len(precisa) < 2:
        log.warning("Sem '%s' ou 'Filiais': o relatorio de preco vai sem "
                    "estoque.", ABA_ESTOQUE_PMZ)
        return vazio, [], {}
    calculadas = calculadas_das_abas(caminho_planilha, precisa)

    wb = _abrir_valores(caminho_planilha)
    try:
        filiais = ler_aba(wb, "Filiais", calculadas=calculadas["Filiais"])
        estoque = ler_aba(wb, ABA_ESTOQUE_PMZ,
                          calculadas=calculadas[ABA_ESTOQUE_PMZ])
    finally:
        wb.close()
    if filiais.empty or estoque.empty:
        return vazio, [], {}

    # loja -> filial BAP
    c_cod = normalizar("COD_FILIAL")
    c_bap = normalizar("FILIAL_BAP")
    if c_cod not in filiais.columns or c_bap not in filiais.columns:
        log.warning("Aba 'Filiais' sem COD_FILIAL/FILIAL_BAP: sem estoque no "
                    "relatorio de preco.")
        return vazio, [], {}
    de_loja = {texto(l.get(c_cod)): texto(l.get(c_bap))
               for _, l in filiais.iterrows() if texto(l.get(c_cod))}
    c_cid = normalizar("CIDADE")
    cidades: dict[str, str] = {}
    if c_cid in filiais.columns:
        for _, l in filiais.iterrows():
            bap, cidade = texto(l.get(c_bap)), texto(l.get(c_cid))
            if bap and cidade:
                cidades.setdefault(bap, cidade)

    def achar(candidatas):
        for candidata in candidatas:
            if normalizar(candidata) in estoque.columns:
                return normalizar(candidata)
        return None

    c_fil = achar(COLS_PMZ_FILIAL)
    c_pro = achar(["PRODUTO", "COD_PRODUTO", "B2_COD"])
    c_qtd = achar(COLS_PMZ_QTDE)
    c_sep = achar(COLS_PMZ_SEPARADA) if ESTOQUE_PMZ_DESCONTAR_SEPARADA else None
    if not all((c_fil, c_pro, c_qtd)):
        log.warning("Aba '%s' sem filial/produto/qtde: sem estoque no relatorio "
                    "de preco.", ABA_ESTOQUE_PMZ)
        return vazio, [], {}

    por_filial: dict[tuple, float] = {}
    sem_mapa = 0
    for _, linha in estoque.iterrows():
        loja = texto(linha.get(c_fil))
        bap = de_loja.get(loja)
        if not bap:
            sem_mapa += 1
            continue
        produto = texto(linha.get(c_pro)).upper()
        if not produto:
            continue
        try:
            qtd = float(linha.get(c_qtd) or 0)
        except (TypeError, ValueError):
            continue
        if c_sep:
            try:
                qtd -= float(linha.get(c_sep) or 0)
            except (TypeError, ValueError):
                pass
        if qtd <= 0:
            continue
        chave = (bap, produto)
        por_filial[chave] = por_filial.get(chave, 0.0) + qtd

    ordem = sorted({b for b, _ in por_filial})
    if sem_mapa:
        log.debug("  %d linha(s) do estoque PMZ sem filial BAP correspondente.",
                  sem_mapa)
    log.info("  estoque por filial BAP: %d filiais, %d combinacoes",
             len(ordem), len(por_filial))
    return por_filial, ordem, cidades


def guardar_foto_de_preco(precos: dict, quando: datetime) -> Path:
    """Grava a foto do dia em CSV, para a proxima rodada comparar."""
    pasta = pasta_das_fotos_de_preco()
    # Comprimido: sao ~30 mil linhas por rodada. Em CSV puro seriam 2 MB por
    # dia dentro do OneDrive; em .gz ficam menos de 300 KB.
    caminho = pasta / f"precos_{quando:%Y%m%d_%H%M%S}.csv.gz"
    with gzip.open(caminho, "wt", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["FILIAL", "TABELA", "COD_PRODUTO", "PRECO",
                           "DESCRICAO"])
        for (filial, tab, produto), (valor, descricao) in sorted(precos.items()):
            escritor.writerow([filial, tab, produto, f"{valor:.4f}", descricao])
    return caminho


def ler_foto_de_preco(caminho: Path) -> dict:
    precos: dict[tuple, tuple] = {}
    abrir = (gzip.open if str(caminho).endswith(".gz") else open)
    try:
        with abrir(caminho, "rt", encoding="utf-8", newline="") as arquivo:
            leitor = csv.reader(arquivo, delimiter=";")
            next(leitor, None)
            for linha in leitor:
                if len(linha) < 4:
                    continue
                try:
                    valor = float(linha[3])
                except ValueError:
                    continue
                precos[(linha[0], linha[1], linha[2])] = (
                    round(valor, 4), linha[4] if len(linha) > 4 else "")
    except OSError as erro:
        log.warning("Nao consegui ler a foto de precos %s: %s", caminho, erro)
    return precos


def foto_de_preco_anterior(ignorar: Path | None = None) -> Path | None:
    """A foto mais recente que NAO seja a desta rodada."""
    pasta = pasta_das_fotos_de_preco()
    fotos = sorted([*pasta.glob("precos_*.csv"), *pasta.glob("precos_*.csv.gz")])
    if ignorar:
        fotos = [f for f in fotos if f != ignorar]
    return fotos[-1] if fotos else None


def limpar_cards() -> None:
    if DIAS_MANTER_CARDS <= 0:
        return
    pasta = PASTA_LOCAL / SUBPASTA_CARDS
    if not pasta.is_dir():
        return
    limite = time.time() - DIAS_MANTER_CARDS * 86400
    for card in pasta.glob("card_precos_*.png"):
        try:
            if card.stat().st_mtime < limite:
                card.unlink()
        except OSError:
            pass


def limpar_fotos_de_preco() -> None:
    if DIAS_MANTER_FOTOS_PRECO <= 0:
        return
    limite = time.time() - DIAS_MANTER_FOTOS_PRECO * 86400
    pasta = pasta_das_fotos_de_preco()
    for foto in [*pasta.glob("precos_*.csv"), *pasta.glob("precos_*.csv.gz")]:
        try:
            if foto.stat().st_mtime < limite:
                foto.unlink()
        except OSError:
            pass


def data_da_foto(caminho: Path) -> str:
    """precos_20260826_1030.csv -> 26/08/2026 10:30"""
    achado = re.search(r"precos_(\d{8})_(\d{4})", caminho.name)
    if not achado:
        return ""
    try:
        quando = datetime.strptime(achado.group(1) + achado.group(2),
                                   "%Y%m%d%H%M")
    except ValueError:
        return ""
    return quando.strftime("%d/%m/%Y %H:%M")


def comparar_precos(antes: dict, agora: dict, quando: datetime,
                    rotulo_anterior: str) -> list[dict]:
    """Uma linha por (filial, tabela, produto) que mudou de preco."""
    data = quando.strftime("%d/%m/%Y")
    hora = quando.strftime("%H:%M")
    mudancas = []

    for chave, (valor, descricao) in sorted(agora.items()):
        filial, tab, produto = chave
        anterior = antes.get(chave)
        if anterior is None:
            mudancas.append({
                "DATA": data, "HORA": hora, "FILIAL": filial, "TABELA": tab,
                "COD_PRODUTO": produto, "DESCRICAO": descricao,
                "PRECO_ANTERIOR": None, "PRECO_ATUAL": valor,
                "DIFERENCA": None, "PERCENTUAL": None,
                "TIPO": TIPO_NOVO, "DATA_ANTERIOR": rotulo_anterior,
            })
            continue
        antigo = anterior[0]
        diferenca = round(valor - antigo, 4)
        if abs(diferenca) < VARIACAO_MINIMA_PRECO:
            continue
        mudancas.append({
            "DATA": data, "HORA": hora, "FILIAL": filial, "TABELA": tab,
            "COD_PRODUTO": produto, "DESCRICAO": descricao or anterior[1],
            "PRECO_ANTERIOR": antigo, "PRECO_ATUAL": valor,
            "DIFERENCA": diferenca,
            "PERCENTUAL": round(diferenca / antigo, 6) if antigo else None,
            "TIPO": TIPO_AUMENTO if diferenca > 0 else TIPO_REDUCAO,
            "DATA_ANTERIOR": rotulo_anterior,
        })

    for chave, (antigo, descricao) in sorted(antes.items()):
        if chave in agora:
            continue
        filial, tab, produto = chave
        mudancas.append({
            "DATA": data, "HORA": hora, "FILIAL": filial, "TABELA": tab,
            "COD_PRODUTO": produto, "DESCRICAO": descricao,
            "PRECO_ANTERIOR": antigo, "PRECO_ATUAL": None,
            "DIFERENCA": None, "PERCENTUAL": None,
            "TIPO": TIPO_REMOVIDO, "DATA_ANTERIOR": rotulo_anterior,
        })
    return mudancas


def nome_da_filial(filial: str, cidades: dict | None = None) -> str:
    """40101002 -> 'MANAUS'. Sem a cidade mapeada, devolve o proprio codigo."""
    cidade = (cidades or {}).get(texto(filial))
    return cidade or texto(filial) or "-"


def resumir_para_trade(mudancas: list[dict], quando: datetime,
                       cidades: dict | None = None) -> list[dict]:
    """Uma linha por filial BAP, com o que o time de trade precisa ver."""
    por_filial: dict[str, dict] = {}
    # O mesmo produto muda em varias tabelas da mesma filial (MT1 e MT2, por
    # exemplo). O estoque dele conta UMA vez por filial, senao o numero dobra.
    ja_contado: set = set()
    for mudanca in mudancas:
        filial = texto(mudanca.get("FILIAL")) or "-"
        item = por_filial.setdefault(filial, {
            "itens": 0, "altas": 0, "baixas": 0, "variacoes": [],
            "estoque": 0.0, "produtos": set()})
        item["itens"] += 1
        if mudanca.get("TIPO") == TIPO_AUMENTO:
            item["altas"] += 1
        elif mudanca.get("TIPO") == TIPO_REDUCAO:
            item["baixas"] += 1
        if mudanca.get("PERCENTUAL") is not None:
            item["variacoes"].append(float(mudanca["PERCENTUAL"]))
        produto = texto(mudanca.get("COD_PRODUTO"))
        item["produtos"].add(produto)
        if (filial, produto) not in ja_contado:
            ja_contado.add((filial, produto))
            item["estoque"] += float(mudanca.get("ESTOQUE_FILIAL") or 0)

    linhas = []
    for filial in sorted(por_filial):
        item = por_filial[filial]
        variacoes = item["variacoes"]
        linhas.append({
            "DATA": quando.strftime("%d/%m/%Y"),
            "HORA": quando.strftime("%H:%M"),
            "FILIAL_BAP": filial,
            "CIDADE": nome_da_filial(filial, cidades),
            "ITENS_ALTERADOS": item["itens"],
            "PRODUTOS": len(item["produtos"]),
            "AUMENTOS": item["altas"],
            "REDUCOES": item["baixas"],
            "VARIACAO_MEDIA": (round(sum(variacoes) / len(variacoes), 6)
                               if variacoes else None),
            "MAIOR_ALTA": round(max(variacoes), 6) if variacoes else None,
            "MAIOR_BAIXA": round(min(variacoes), 6) if variacoes else None,
            "ESTOQUE_IMPACTADO": round(item["estoque"], 2),
        })
    return linhas


def gravar_alteracoes_de_preco(mudancas: list[dict], simular: bool,
                               controle: dict | None = None,
                               estoque_filial: dict | None = None,
                               filiais: list | None = None,
                               cidades: dict | None = None,
                               quando: datetime | None = None) -> str:
    """
    Acrescenta as mudancas no Excel acumulativo. Nada e reescrito.

    O arquivo e criado ja na PRIMEIRA rodada, mesmo sem nenhuma alteracao:
    sem isso, quem procura o arquivo depois de rodar acha que deu errado. A
    aba CONTROLE registra o que aconteceu em cada rodada, inclusive as em que
    nada mudou.
    """
    nome = ("SIMULACAO_" + ARQUIVO_PRECOS) if simular else ARQUIVO_PRECOS
    caminho = PASTA_RELATORIOS / nome

    if caminho.exists():
        wb = load_workbook(caminho)
    else:
        wb = Workbook()
        wb.remove(wb.active)

    if ABA_ALTERACOES_PRECO not in wb.sheetnames:
        ws = wb.create_sheet(ABA_ALTERACOES_PRECO)
        ws.append(COLUNAS_ALTERACAO_PRECO)
    ws = wb[ABA_ALTERACOES_PRECO]
    removidas = limpar_colunas_vazias(ws)
    if removidas:
        log.info("  removi %d coluna(s) em branco do cabecalho.", removidas)
    estilo_do_cabecalho(ws, ultima_coluna_do_cabecalho(ws))

    cabecalho = mapear_cabecalhos(ws, 1)
    faltando = [c for c in COLUNAS_ALTERACAO_PRECO
                if normalizar(c) not in cabecalho]
    for titulo in faltando:
        coluna = ultima_coluna_do_cabecalho(ws) + 1
        ws.cell(1, coluna).value = titulo
        cabecalho[normalizar(titulo)] = coluna

    proxima = ultima_linha_com_dados(ws, 1) + 1
    for registro in mudancas:
        for titulo in COLUNAS_ALTERACAO_PRECO:
            coluna = cabecalho.get(normalizar(titulo))
            if not coluna:
                continue
            celula = ws.cell(proxima, coluna)
            celula.value = registro.get(titulo)
            if titulo in ("PRECO_ANTERIOR", "PRECO_ATUAL", "DIFERENCA"):
                celula.number_format = '#,##0.00'
            elif titulo == "PERCENTUAL":
                celula.number_format = '0.00%'
        estilo_da_linha(ws, proxima, len(COLUNAS_ALTERACAO_PRECO))
        proxima += 1

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = (f"A1:{get_column_letter(len(COLUNAS_ALTERACAO_PRECO))}"
                          f"{max(proxima - 1, 1)}")
    for titulo, largura in (("DATA", 11), ("HORA", 7), ("FILIAL", 11),
                            ("TABELA", 9), ("COD_PRODUTO", 16),
                            ("DESCRICAO", 48), ("PRECO_ANTERIOR", 15),
                            ("PRECO_ATUAL", 13), ("DIFERENCA", 12),
                            ("PERCENTUAL", 12), ("TIPO", 16),
                            ("DATA_ANTERIOR", 18)):
        coluna = cabecalho.get(normalizar(titulo))
        if coluna:
            ws.column_dimensions[get_column_letter(coluna)].width = largura

    # ---- aba ESTOQUE_POR_FILIAL: os produtos que mudaram, filial a filial --
    quando = quando or datetime.now()
    if mudancas and estoque_filial and filiais:
        rotulo_filial = {f: f"{nome_da_filial(f, cidades)} ({f})"
                         for f in filiais}
        colunas = (["DATA", "HORA", "COD_PRODUTO", "DESCRICAO"]
                   + [rotulo_filial[f] for f in filiais] + ["TOTAL_BAP"])
        if ABA_ESTOQUE_FILIAL_PRECO not in wb.sheetnames:
            we = wb.create_sheet(ABA_ESTOQUE_FILIAL_PRECO)
            we.append(colunas)
            we.freeze_panes = "A2"
        we = wb[ABA_ESTOQUE_FILIAL_PRECO]
        cab_e = mapear_cabecalhos(we, 1)
        for titulo in colunas:
            if normalizar(titulo) not in cab_e:
                indice = we.max_column + 1
                we.cell(1, indice).value = titulo
                cab_e[normalizar(titulo)] = indice
        estilo_do_cabecalho(we, we.max_column)

        vistos = {}
        for mudanca in mudancas:
            produto = texto(mudanca.get("COD_PRODUTO")).upper()
            if produto and produto not in vistos:
                vistos[produto] = texto(mudanca.get("DESCRICAO"))
        proxima_e = ultima_linha_com_dados(we, 1) + 1
        for produto, descricao in sorted(vistos.items()):
            total = 0.0
            valores = {"DATA": quando.strftime("%d/%m/%Y"),
                       "HORA": quando.strftime("%H:%M"),
                       "COD_PRODUTO": produto, "DESCRICAO": descricao}
            for filial in filiais:
                qtd = estoque_filial.get((filial, produto), 0.0)
                valores[rotulo_filial[filial]] = round(qtd, 2)
                total += qtd
            valores["TOTAL_BAP"] = round(total, 2)
            for titulo in colunas:
                coluna = cab_e.get(normalizar(titulo))
                if coluna:
                    we.cell(proxima_e, coluna).value = valores.get(titulo)
            estilo_da_linha(we, proxima_e, we.max_column)
            proxima_e += 1
        we.column_dimensions["A"].width = 11
        we.column_dimensions["B"].width = 7
        we.column_dimensions["C"].width = 16
        we.column_dimensions["D"].width = 46

    # ---- aba RESUMO_TRADE: agregado por filial ---------------------------
    if mudancas:
        if ABA_RESUMO_TRADE not in wb.sheetnames:
            wr = wb.create_sheet(ABA_RESUMO_TRADE)
            wr.append(COLUNAS_RESUMO_TRADE)
            wr.freeze_panes = "A2"
        wr = wb[ABA_RESUMO_TRADE]
        estilo_do_cabecalho(wr, len(COLUNAS_RESUMO_TRADE))
        proxima_r = ultima_linha_com_dados(wr, 1) + 1
        for registro in resumir_para_trade(mudancas, quando, cidades):
            for indice, titulo in enumerate(COLUNAS_RESUMO_TRADE, start=1):
                celula = wr.cell(proxima_r, indice)
                celula.value = registro.get(titulo)
                if titulo in ("VARIACAO_MEDIA", "MAIOR_ALTA", "MAIOR_BAIXA"):
                    celula.number_format = '0.00%'
                elif titulo == "ESTOQUE_IMPACTADO":
                    celula.number_format = '#,##0'
            estilo_da_linha(wr, proxima_r, len(COLUNAS_RESUMO_TRADE))
            proxima_r += 1
        for indice, largura in enumerate(
                (11, 7, 13, 14, 16, 11, 12, 12, 15, 13, 14, 18), start=1):
            wr.column_dimensions[get_column_letter(indice)].width = largura

    # ---- aba CONTROLE: uma linha por rodada, mudando ou nao --------------
    if controle:
        if ABA_CONTROLE_PRECO not in wb.sheetnames:
            wc = wb.create_sheet(ABA_CONTROLE_PRECO)
            wc.append(COLUNAS_CONTROLE_PRECO)
            wc.freeze_panes = "A2"
        wc = wb[ABA_CONTROLE_PRECO]
        estilo_do_cabecalho(wc, len(COLUNAS_CONTROLE_PRECO))
        proxima_c = ultima_linha_com_dados(wc, 1) + 1
        for indice, titulo in enumerate(COLUNAS_CONTROLE_PRECO, start=1):
            wc.cell(proxima_c, indice).value = controle.get(titulo)
        estilo_da_linha(wc, proxima_c, len(COLUNAS_CONTROLE_PRECO))
        for indice, largura in enumerate((11, 7, 12, 20, 13, 44), start=1):
            wc.column_dimensions[get_column_letter(indice)].width = largura

    # (05/11) aberta no Excel: o aviso antes de gravar por cima
    if aguardar_arquivo_livre(Path(caminho), "gravar as alteracoes de "
                              "preco") != "livre":
        wb.close()
        raise PermissionError(f"{Path(caminho).name} em aberto")
    wb.save(caminho)
    wb.close()
    return str(caminho)


CARD_HTML = """<!doctype html><html lang="pt-br"><meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:1200px; }}
  body {{ font-family:'Segoe UI',Calibri,Arial,sans-serif;
         background:#0F2417; color:#0E1A12; }}
  .topo {{ padding:48px 56px 30px; color:#fff; }}
  .marca {{ font-size:18px; letter-spacing:.22em; color:#8FCB9B; font-weight:600; }}
  h1 {{ font-size:56px; line-height:1.05; margin:14px 0 8px; font-weight:700; }}
  .quando {{ font-size:21px; color:#B9D6C1; }}
  .corpo {{ background:#F4F7F4; border-radius:34px 34px 0 0; padding:38px 56px 26px; }}
  .kpis {{ display:flex; gap:16px; margin-bottom:30px; }}
  .kpi {{ flex:1; background:#fff; border-radius:18px; padding:20px 20px;
          box-shadow:0 3px 12px rgba(20,50,30,.08); }}
  .kpi .rot {{ font-size:14px; color:#5E7566; text-transform:uppercase;
               letter-spacing:.07em; font-weight:600; }}
  .kpi .num {{ font-size:42px; font-weight:700; margin-top:6px; line-height:1; }}
  .sobe {{ color:#B3261E; }} .desce {{ color:#1E6B3A; }} .novo {{ color:#1D4ED8; }}
  .bloco {{ margin-bottom:30px; }}
  .cab {{ display:flex; align-items:baseline; gap:12px; margin-bottom:12px;
          padding-bottom:8px; border-bottom:2px solid #DCE5DE; }}
  .cab h2 {{ font-size:23px; font-weight:700; }}
  .cab .qt {{ font-size:16px; color:#5E7566; }}
  .grade {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr);
            gap:0 34px; }}
  .item {{ display:flex; align-items:baseline; gap:8px; padding:7px 0;
           border-bottom:1px solid #E7EDE8; font-size:16px; min-width:0; }}
  .item .cod {{ font-weight:700; width:118px; flex:none;
                overflow:hidden; white-space:nowrap; }}
  .item .des {{ color:#5A6E61; font-size:14px; flex:1 1 0; min-width:0;
                overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }}
  .item .pre {{ font-variant-numeric:tabular-nums; white-space:nowrap;
                font-size:15px; }}
  .item .pct {{ font-weight:700; width:66px; text-align:right; flex:none;
                font-variant-numeric:tabular-nums; font-size:15px; }}
  .item .est {{ width:56px; text-align:right; flex:none; color:#7F9686;
                font-size:14px; font-variant-numeric:tabular-nums; }}
  .filiais {{ font-size:18px; color:#42544A; line-height:1.9;
              border-top:2px solid #DCE5DE; padding-top:16px; }}
  .rodape {{ padding:20px 56px 26px; color:#7F9686; font-size:16px;
             background:#F4F7F4; }}
</style>
<body>
  <div class="topo">
    <div class="marca">BAP AUTOPARTS &middot; TRADE</div>
    <h1>Alterações de preço</h1>
    <div class="quando">{periodo}</div>
  </div>
  <div class="corpo">
    <div class="kpis">
      <div class="kpi"><div class="rot">Itens alterados</div>
        <div class="num">{total}</div></div>
      <div class="kpi"><div class="rot">Reduções</div>
        <div class="num desce">{baixas}</div></div>
      <div class="kpi"><div class="rot">Preços novos</div>
        <div class="num novo">{novos}</div></div>
      <div class="kpi"><div class="rot">Aumentos</div>
        <div class="num sobe">{altas}</div></div>
      <div class="kpi"><div class="rot">Variação típica</div>
        <div class="num">{mediana}</div></div>
    </div>
    {blocos}
    {rodape_filiais}
  </div>
  <div class="rodape">{rodape}</div>
</body></html>"""


def moeda(valor) -> str:
    if valor is None:
        return "-"
    return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def inteiro(valor) -> str:
    try:
        return f"{int(float(valor)):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def percentual(valor, sinal: bool = True) -> str:
    if valor is None:
        return "-"
    texto_pct = f"{float(valor) * 100:.1f}".replace(".", ",")
    if sinal and float(valor) > 0:
        texto_pct = "+" + texto_pct
    return texto_pct + "%"


def um_por_produto(mudancas: list[dict], chave) -> list[dict]:
    """
    Um produto muda em varias filiais e tabelas ao mesmo tempo. No card ele
    entra UMA vez, pela linha mais representativa segundo 'chave'.
    """
    melhor: dict[str, dict] = {}
    for mudanca in mudancas:
        produto = texto(mudanca.get("COD_PRODUTO"))
        atual = melhor.get(produto)
        if atual is None or chave(mudanca) > chave(atual):
            melhor[produto] = mudanca
    return list(melhor.values())


def linha_do_card(mudanca: dict, mostrar_de: bool) -> str:
    pct = mudanca.get("PERCENTUAL")
    classe = "novo" if pct is None else ("sobe" if float(pct) > 0 else "desce")
    if mostrar_de and mudanca.get("PRECO_ANTERIOR") is not None:
        precos = (f'{moeda(mudanca.get("PRECO_ANTERIOR"))} &rarr; '
                  f'<b>{moeda(mudanca.get("PRECO_ATUAL"))}</b>')
    else:
        precos = f'<b>{moeda(mudanca.get("PRECO_ATUAL"))}</b>'
    return (f'<div class="item">'
            f'<span class="cod">{texto(mudanca.get("COD_PRODUTO"))}</span>'
            f'<span class="des">{texto(mudanca.get("DESCRICAO"))}</span>'
            f'<span class="pre">{precos}</span>'
            f'<span class="pct {classe}">'
            f'{"NOVO" if pct is None else percentual(pct)}</span>'
            f'<span class="est">{inteiro(mudanca.get("ESTOQUE_TOTAL_BAP"))}</span>'
            f'</div>')


def bloco_do_card(titulo: str, itens: list[dict], total: int,
                  mostrar_de: bool = True) -> str:
    if not itens:
        return ""
    quantos = (f"{len(itens)} de {inteiro(total)}" if total > len(itens)
               else f"{len(itens)}")
    linhas = "".join(linha_do_card(m, mostrar_de) for m in itens)
    return (f'<div class="bloco"><div class="cab"><h2>{titulo}</h2>'
            f'<span class="qt">{quantos} &middot; código · descrição · preço · '
            f'variação · estoque BAP</span></div>'
            f'<div class="grade">{linhas}</div></div>')


def montar_html_do_card(mudancas: list[dict], quando: datetime,
                        rotulo_anterior: str, cidades: dict | None = None) -> str:
    variacoes = [float(m["PERCENTUAL"]) for m in mudancas
                 if m.get("PERCENTUAL") is not None]
    altas = sum(1 for m in mudancas if m.get("TIPO") == TIPO_AUMENTO)
    baixas = sum(1 for m in mudancas if m.get("TIPO") == TIPO_REDUCAO)
    novos = sum(1 for m in mudancas if m.get("TIPO") == TIPO_NOVO)
    media = percentual(sum(variacoes) / len(variacoes)) if variacoes else "-"
    ordenadas = sorted(variacoes)
    mediana = percentual(ordenadas[len(ordenadas) // 2]) if ordenadas else "-"

    def do_tipo(tipo):
        return [m for m in mudancas if m.get("TIPO") == tipo]

    # Reducoes e aumentos: os maiores movimentos, um por produto.
    # Precos novos: nao tem variacao, entao ordena pelo estoque - o que a
    # equipe tem em casa e o que interessa saber que ganhou preco.
    def estoque_de(m):
        return float(m.get("ESTOQUE_TOTAL_BAP") or 0)

    reducoes = sorted(um_por_produto(do_tipo(TIPO_REDUCAO),
                                     lambda m: -float(m["PERCENTUAL"])),
                      key=lambda m: float(m["PERCENTUAL"]))[:ITENS_POR_BLOCO_CARD]
    aumentos = sorted(um_por_produto(do_tipo(TIPO_AUMENTO),
                                     lambda m: float(m["PERCENTUAL"])),
                      key=lambda m: -float(m["PERCENTUAL"]))[:ITENS_POR_BLOCO_CARD]
    entrantes = sorted(um_por_produto(do_tipo(TIPO_NOVO), estoque_de),
                       key=lambda m: -estoque_de(m))[:ITENS_POR_BLOCO_CARD]

    blocos = "".join((
        bloco_do_card("Maiores reduções", reducoes, baixas),
        bloco_do_card("Preços novos (maior estoque)", entrantes, novos,
                      mostrar_de=False),
        bloco_do_card("Maiores aumentos", aumentos, altas),
    ))

    resumo = resumir_para_trade(mudancas, quando, cidades)
    rodape_filiais = ""
    if len(resumo) > 1:
        partes = " &nbsp;|&nbsp; ".join(
            f'<b>{r["CIDADE"]}</b> {inteiro(r["ITENS_ALTERADOS"])} '
            f'({percentual(r["VARIACAO_MEDIA"])})' for r in resumo)
        rodape_filiais = f'<div class="filiais">{partes}</div>'

    # O mesmo produto aparece em varias tabelas da mesma filial; o estoque
    # dele nao pode ser contado uma vez por tabela.
    ja_contado = set()
    unidades = 0.0
    for mudanca in mudancas:
        chave = (texto(mudanca.get("FILIAL")), texto(mudanca.get("COD_PRODUTO")))
        if chave in ja_contado:
            continue
        ja_contado.add(chave)
        unidades += float(mudanca.get("ESTOQUE_FILIAL") or 0)

    return CARD_HTML.format(
        periodo=f"Comparado com {rotulo_anterior}" if rotulo_anterior
                else quando.strftime("%d/%m/%Y"),
        total=inteiro(len(mudancas)), altas=inteiro(altas),
        baixas=inteiro(baixas), novos=inteiro(novos), mediana=mediana,
        blocos=blocos or "<p>Sem itens a destacar.</p>",
        rodape_filiais=rodape_filiais,
        rodape=f"Variação média {media} · estoque afetado {inteiro(unidades)} un "
               f"· gerado em {quando:%d/%m/%Y às %H:%M} · fonte: tabela de "
               f"preço do Protheus · estoque das lojas PMZ")


def gerar_card_precos(mudancas: list[dict], quando: datetime,
                      rotulo_anterior: str,
                      cidades: dict | None = None) -> str | None:
    """
    Renderiza o resumo num PNG pronto para mandar nos grupos. Usa o Chromium do
    Playwright, que ja e instalado para baixar os relatorios.
    """
    if not GERAR_CARD_PRECOS or not mudancas:
        return None
    pasta = PASTA_LOCAL / SUBPASTA_CARDS
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"card_precos_{quando:%Y%m%d_%H%M}.png"
    html = pasta / f".card_{quando:%Y%m%d_%H%M}.html"

    try:
        html.write_text(
            montar_html_do_card(mudancas, quando, rotulo_anterior, cidades),
            encoding="utf-8")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            navegador = pw.chromium.launch()
            pagina = navegador.new_page(viewport={"width": 1200, "height": 600})
            pagina.goto(html.as_uri())
            pagina.wait_for_timeout(250)
            # full_page: a altura acompanha o conteudo, sem sobra em branco
            pagina.screenshot(path=str(destino), full_page=True)
            navegador.close()
        log.info("  card do trade gerado: %s", destino)
        return str(destino)
    except Exception as erro:
        log.warning("Nao consegui gerar o card (%s). O Excel continua completo.",
                    erro)
        log.debug("", exc_info=True)
        return None
    finally:
        try:
            html.unlink(missing_ok=True)
        except OSError:
            pass


def acompanhar_tabela_de_preco(caminho_planilha: Path,
                               simular: bool = False) -> dict:
    """
    Compara a tabela de preco de hoje com a da rodada anterior e alimenta o
    Excel acumulativo. Devolve o resumo para o log e para a janela.
    """
    if not COMPARAR_TABELA_PRECO:
        return {}
    log.info("Comparando a tabela de preco com a rodada anterior...")

    agora = datetime.now()
    try:
        atual = ler_tabela_de_preco(caminho_planilha)
    except Exception as erro:
        log.error("Nao consegui ler a tabela de preco: %s", erro)
        log.debug("", exc_info=True)
        return {"erro": str(erro)}
    if not atual:
        return {"linhas": 0, "precos": 0}

    # LE a foto anterior ANTES de gravar a de hoje: se as duas cairem no mesmo
    # nome (duas rodadas no mesmo segundo), gravar primeiro apagaria a antiga
    # e a comparacao daria "nada mudou".
    anterior_caminho = foto_de_preco_anterior()
    antes = ler_foto_de_preco(anterior_caminho) if anterior_caminho else {}
    rotulo = ""
    if anterior_caminho is not None:
        rotulo = data_da_foto(anterior_caminho) or anterior_caminho.name

    foto = guardar_foto_de_preco(atual, agora)
    log.info("  %d precos hoje | foto guardada em %s", len(atual), foto.name)

    def registrar(mudancas: list[dict], observacao: str,
                  estoque=None, filiais=None, cidades=None) -> str | None:
        """Grava o Excel SEMPRE - mesmo sem alteracao nenhuma."""
        controle = {
            "DATA": agora.strftime("%d/%m/%Y"),
            "HORA": agora.strftime("%H:%M"),
            "PRECOS_LIDOS": len(atual),
            "COMPARADO_COM": rotulo or "-",
            "ALTERACOES": len(mudancas),
            "OBSERVACAO": observacao,
        }
        try:
            return gravar_alteracoes_de_preco(
                mudancas, simular, controle,
                estoque_filial=estoque, filiais=filiais, cidades=cidades,
                quando=agora)
        except Exception as erro:
            log.error("Nao consegui gravar o %s: %s", ARQUIVO_PRECOS, erro)
            log.error("Provavelmente alguem esta com ele aberto no Excel.")
            return None

    if anterior_caminho is None:
        log.info("  primeira foto: nao ha com o que comparar ainda. A proxima "
                 "rodada ja compara com esta.")
        arquivo = registrar([], "primeira foto - nada a comparar ainda")
        if arquivo:
            log.info("  %s criado (ainda sem alteracoes)", ARQUIVO_PRECOS)
        limpar_fotos_de_preco()
        return {"linhas": 0, "precos": len(atual), "primeira_foto": True,
                "arquivo": ARQUIVO_PRECOS if arquivo else None}

    mudancas = comparar_precos(antes, atual, agora, rotulo)

    if not mudancas:
        log.info("  nenhum preco mudou desde %s.", rotulo)
        # (05/11, auditoria do robo) sem preco mudado o Excel (3,5 MB) nao e
        # mais aberto e salvo (~30 s por rodada): a linha "nenhum preco
        # mudou" fica so no log. Se o arquivo nao existir, e criado.
        if not (PASTA_RELATORIOS / (("SIMULACAO_" if simular else "")
                                    + ARQUIVO_PRECOS)).exists():
            registrar([], "nenhum preco mudou")
        limpar_fotos_de_preco()
        return {"linhas": 0, "precos": len(atual), "comparado_com": rotulo,
                "arquivo": ARQUIVO_PRECOS}

    contagem: dict[str, int] = {}
    for mudanca in mudancas:
        contagem[mudanca["TIPO"]] = contagem.get(mudanca["TIPO"], 0) + 1
    log.info("  %d alteracao(oes) desde %s: %s", len(mudancas), rotulo,
             ", ".join(f"{q} {t.lower()}" for t, q in sorted(contagem.items())))

    variacoes = [m["PERCENTUAL"] for m in mudancas if m.get("PERCENTUAL")]
    if variacoes:
        log.info("  maior alta %.2f%% | maior baixa %.2f%%",
                 max(variacoes) * 100, min(variacoes) * 100)
    for mudanca in sorted(
            [m for m in mudancas if m.get("PERCENTUAL")],
            key=lambda m: -abs(m["PERCENTUAL"]))[:5]:
        log.info("    %s %s | %s: %.2f -> %.2f (%.2f%%)",
                 mudanca["FILIAL"], mudanca["TABELA"], mudanca["COD_PRODUTO"],
                 mudanca["PRECO_ANTERIOR"], mudanca["PRECO_ATUAL"],
                 mudanca["PERCENTUAL"] * 100)

    # ---- estoque por filial BAP, para o relatorio e para o card ----------
    estoque_filial, filiais_bap, cidades_bap = {}, [], {}
    try:
        estoque_filial, filiais_bap, cidades_bap = \
            ler_estoque_por_filial_bap(caminho_planilha)
    except Exception as erro:
        log.warning("Nao consegui ler o estoque por filial (%s). O relatorio "
                    "sai sem as colunas de estoque.", erro)
    for mudanca in mudancas:
        produto = texto(mudanca.get("COD_PRODUTO")).upper()
        filial = texto(mudanca.get("FILIAL"))
        mudanca["ESTOQUE_FILIAL"] = round(
            estoque_filial.get((filial, produto), 0.0), 2)
        mudanca["ESTOQUE_TOTAL_BAP"] = round(
            sum(q for (f, p), q in estoque_filial.items() if p == produto), 2)

    arquivo = registrar(mudancas, "", estoque_filial, filiais_bap,
                        cidades_bap)
    if arquivo is None:
        return {"linhas": len(mudancas),
                "erro": f"nao consegui gravar o {ARQUIVO_PRECOS}",
                "comparado_com": rotulo}
    log.info("  alteracoes gravadas em %s", arquivo)

    card = gerar_card_precos(mudancas, agora, rotulo, cidades_bap)

    limpar_fotos_de_preco()
    limpar_cards()
    return {
        "arquivo": ARQUIVO_PRECOS,
        "linhas": len(mudancas),
        "precos": len(atual),
        "comparado_com": rotulo,
        "por_tipo": contagem,
        "maior_alta": round(max(variacoes) * 100, 2) if variacoes else None,
        "maior_baixa": round(min(variacoes) * 100, 2) if variacoes else None,
        "estoque_impactado": round(
            sum(float(m.get("ESTOQUE_FILIAL") or 0) for m in mudancas), 2),
        "card": card,
    }


# ==============================================================================
#              ESTOQUE POR FILIAL BAP, COM OS DOIS PRECOS
# ==============================================================================

def parametros_do_planner() -> dict:
    """
    Os cortes de curva e de churn que o Planner usa, do planner_config.json.

    Sem eles a BASE_CLIENTE sairia com os padroes de fabrica do
    base_cliente.py (curva S a partir de 20.000, A de 10.000...), que NAO
    sao os da BAP (10.000 e 5.000). Cada cliente mudaria de curva, e com
    a curva muda a frequencia de visita: a rota do mes inteiro viraria
    outra, sem ninguem ter pedido. Se o arquivo nao existir, devolve {} e
    o base_cliente.py usa os padroes dele.
    """
    caminho = PASTA_LOCAL / ARQ_CONFIG_PLANNER
    if not caminho.is_file():
        log.warning("Sem %s na pasta: a BASE_CLIENTE vai usar os cortes "
                    "PADRAO de curva, que podem nao ser os da BAP.",
                    ARQ_CONFIG_PLANNER)
        return {}
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            return dict(json.load(arquivo).get("parametros") or {})
    except (OSError, ValueError) as erro:
        log.warning("Nao consegui ler o %s (%s): a BASE_CLIENTE vai usar os "
                    "cortes padrao.", ARQ_CONFIG_PLANNER, erro)
        return {}


def gerar_base_cliente_bap(caminho_planilha: Path, simular: bool = False) -> dict:
    """
    Monta a BASE_CLIENTE.xlsx: a carteira do Planner, com tres abas.

      BASE_CLIENTE    uma linha por cliente (codigo + loja), com curva,
                      status, faturamento e limite
      HIST_POR_NF     uma linha por NOTA FISCAL faturada do cliente
      HIST_DETALHADO  o mesmo espelho, uma linha por PRODUTO da nota

    Quem faz o trabalho e o base_cliente.py, o MESMO modulo que o Planner
    chama - assim o arquivo sai igual, venha de onde vier. O que este
    involucro acrescenta e o de que o Planner cuidava sozinho: guardar a
    base anterior no backup e usar os cortes do planner_config.json.
    """
    if not GERAR_BASE_CLIENTE:
        return {}
    log.info("Montando a %s...", ARQUIVO_BASE_CLIENTE)
    try:
        if str(PASTA_LOCAL) not in sys.path:
            sys.path.insert(0, str(PASTA_LOCAL))
        import base_cliente as _bcli          # noqa: PLC0415
    except Exception as erro:                 # noqa: BLE001
        log.error("NAO DA PARA MONTAR A %s: nao achei o base_cliente.py na "
                  "pasta (%s).", ARQUIVO_BASE_CLIENTE, erro)
        return {"erro": f"base_cliente.py ausente: {erro}",
                "arquivo": ARQUIVO_BASE_CLIENTE}

    # ---- CNAE de quem ainda nao tem ------------------------------------
    # Roda ANTES da base: o base_cliente.py so le o cache, e assim o
    # cliente novo de hoje ja sai com CNAE e SEGMENTO. Em simulacao nao vai
    # a internet (a base sai com o que o cache ja tem).
    cnae = {}
    if CONSULTAR_CNAE and not simular:
        try:
            import cnae_bap as _cnae          # noqa: PLC0415
            cnae = _cnae.atualizar_cache(
                _cnae.cnpjs_da_tabela(caminho_planilha), log=log)
        except Exception as erro:             # noqa: BLE001
            log.warning("Nao consegui consultar o CNAE (%s) - a BASE_CLIENTE "
                        "sai com o CNAE que ja estava no cache.", erro)
            log.debug("", exc_info=True)
            cnae = {"erro": str(erro)}

    nome = (("SIMULACAO_" + ARQUIVO_BASE_CLIENTE) if simular
            else ARQUIVO_BASE_CLIENTE)
    destino = PASTA_RELATORIOS / nome
    # a base de ontem vai para o backup ANTES, e por COPIA: se a gravacao
    # de hoje falhar, a de ontem continua no lugar e ninguem fica sem base
    if not simular and destino.exists():
        try:
            if str(PASTA_LOCAL) not in sys.path:
                sys.path.insert(0, str(PASTA_LOCAL))
            import pastas_bap as _pb          # noqa: PLC0415
            _pb.guardar_anterior(destino, PASTA_LOCAL, copiar=True)
        except Exception:                     # noqa: BLE001
            pass                              # backup e conforto, nao regra

    # (05/11) aberta no Excel: o aviso antes de gravar por cima
    if aguardar_arquivo_livre(destino, "gravar a BASE_CLIENTE") != "livre":
        log.error("A %s NAO foi atualizada nesta rodada: estava em aberto.",
                  nome)
        return {"erro": "arquivo em aberto (pulado)", "arquivo": nome}
    try:
        quantos, referencia = _bcli.gerar_base_cliente(
            caminho_planilha, destino, parametros=parametros_do_planner())
    except Exception as erro:                 # noqa: BLE001
        log.error("Nao consegui gravar a %s: %s", nome, erro)
        log.error("Provavelmente alguem esta com ela aberta no Excel.")
        log.debug("", exc_info=True)
        return {"erro": str(erro), "arquivo": nome}

    historico = getattr(_bcli.gerar_base_cliente, "ultimo_historico", {}) or {}
    log.info("  %d cliente(s) | referencia %s | %d nota(s) e %d item(ns) de "
             "historico", quantos, referencia, historico.get("notas", 0),
             historico.get("itens", 0))
    excluidos = getattr(_bcli.gerar_base_cliente, "excluidos", 0)
    if excluidos:
        log.info("  %d cliente(s) fora dos 8 segmentos -> aba EXCLUIDOS "
                 "(fora de rota, meta e oportunidade)", excluidos)
    # (14/10) as COORDENADAS: quantos localizou nesta rodada, e por que nao
    # (sem internet / OpenStreetMap bloqueado na rede desta maquina)
    geo_r = getattr(_bcli._coordenadas, "resultado", None) or {}  # noqa: SLF001
    if geo_r:
        if geo_r.get("erro") and not geo_r.get("consultados"):
            log.warning("  Coordenadas: o OpenStreetMap nao respondeu nesta "
                        "maquina (%s) - %d cliente(s) sem ponto. Rode o "
                        "atualizar_coordenadas.bat num computador com acesso.",
                        geo_r.get("erro"), geo_r.get("faltam", 0))
        else:
            log.info("  Coordenadas: %d consultado(s), %d localizado(s), "
                     "%d na fila", geo_r.get("consultados", 0),
                     geo_r.get("achados", 0), geo_r.get("faltam", 0))
    aviso_cnae = getattr(_bcli.gerar_base_cliente, "aviso_cnae", "")
    if aviso_cnae:
        log.warning("  Segmento: %s", aviso_cnae)
    log.info("  gravado em %s", destino)
    return {
        "arquivo": nome,
        "clientes": quantos,
        "referencia": str(referencia) if referencia else "",
        "notas": historico.get("notas", 0),
        "itens": historico.get("itens", 0),
        "cnae": cnae,
        "excluidos": excluidos,
    }


def gerar_dados_relatorios(simular: bool = False) -> dict:
    """Deixa prontos os dados dos relatorios (bap_dados.atualizar_tudo)."""
    if not GERAR_DADOS_RELATORIOS or simular:
        return {}
    log.info("Preparando os dados dos relatorios do BAP Central...")
    inicio = time.time()
    try:
        import bap_dados as _bd               # noqa: PLC0415
    except ImportError as erro:
        log.error("Sem o bap_dados.py na pasta: os relatorios vao montar os "
                  "dados na hora em que forem abertos (%s).", erro)
        return {"erro": f"bap_dados.py ausente: {erro}"}
    resultado = _bd.atualizar_tudo(PASTA_LOCAL, log=log.warning)
    erros = {k: v for k, v in resultado.items() if str(v).startswith("ERRO")}
    log.info("Dados dos relatorios prontos em %.1f s%s.", time.time() - inicio,
             f" (com erro em: {', '.join(erros)})" if erros else "")
    return {"blocos": resultado, "erros": list(erros)}



# =============================================================================
# PACOTE WEB (passo 4f, T-0013): o PC monta, a web so le a parte dado
# =============================================================================
# Decisao de 20/11: a web (Render, 512 MB) nao roda o montar. O PC monta o
# vc_painel e manda so as abas "Painel · resultado" e "Painel · produtividade"
# (parte dado do contrato, .coord/contratos/relatorio.md, secao 10): sem
# callables, sem chave com "_", chave sempre texto. Segredo: BAP_WEB_URL e
# BAP_WEB_TOKEN em variavel de ambiente ou no cofre do Windows (servico
# BAP_WEB). Nunca no log.

SERVICO_KEYRING_WEB = "BAP_WEB"
_ABAS_WEB = {"res": "resultado", "prod": "produtividade",
             "du": "por_dia_util"}   # visao -> chave (T-0022: + por dia util)
_TITULOS_ABAS_WEB = {"Painel · resultado": "resultado",
                     "Painel · produtividade": "produtividade",
                     "Painel · por dia útil": "por_dia_util"}
_PACOTE_WEB_CHAVES_ACAO = frozenset({
    "detalhe_pedido", "kpis_de", "total_de", "ordem_exportar", "edicao",
    "garantia", "importar_preenchidos"})
# o farol (T-0017) tira tambem tabelas (tem cliente/CNPJ), juntas e o que edita
_CHAVES_FORA_FAROL_WEB = _PACOTE_WEB_CHAVES_ACAO | {
    "tabelas", "juntas", "editar", "abrir"}
_DESCARTAR = object()

# (T-0017) Os faroes do PC no site, so leitura (modelo M2: o PC monta e manda
# o JSON pronto). Entram um por entrega: Inadimplencia, Pedidos, Entregas, Visita.
FAROIS_WEB = ("pl_inadimplencia", "pv_pedidos", "pl_entregas", "vc_visitas",
              # (T-0024) lote 2: abas de tabela com as colunas do PC (livres)
              "pv_indicadores", "vc_base", "vc_planner", "pl_giro", "pl_frw",
              "vc_meta",
              # (T-0023 v2, 10.10) Garantias, Devolucoes e NCC, com as colunas
              # fechadas do contrato 10.10.2
              "pl_garantias", "pl_devolucoes", "pl_ncc")
# (T-0024) farois cujas tabelas vao com as colunas que o PC monta (sem a lista
# fechada do contrato 10.7.3): so se corta o que nunca vai e se limpa o nome
RIDS_LIVRES_WEB = ("pv_indicadores", "vc_base", "vc_planner", "pl_giro",
                   "pl_frw")
# colunas que alem de _COLUNAS_FORA_WEB nunca vao nos farois livres (numero
# do endereco; coluna interna comeca com "_")
_COLUNAS_FORA_LIVRES_WEB = frozenset({"Nº", "N°", "NUMERO", "NÚMERO"})
# D1 do Alexandre ("2 A", 24/11): grafico e frase com nome de vendedor ou
# supervisor VAO no pacote (True). Cliente e CNPJ nunca vao. Com False, o
# grafico e as frases com nome de pessoa saem (1 linha).
WEB_GRAFICOS_COM_NOME = True
_TIPOS_BLOCO_FAROL_WEB = ("insights", "barras", "hbarras")   # kpis vao no topo
# o que no titulo (ou na frase) denuncia nome de pessoa
_TERMOS_PESSOA_WEB = ("vendedor", "supervisor")
# cliente e CNPJ nunca vao (regra 6), com ou sem a constante
# (frase "136 clientes" e contagem, nao nome: so o grafico por cliente sai)
_TERMOS_CLIENTE_WEB = ("devedor", "cnpj")
_TERMOS_TITULO_CLIENTE_WEB = ("cliente",)
# (T-0017, entregas 3 a 5) tabela do farol que o cartao por estado usa
# (kpis_de; RN-GER-006). A coluna da UF e a conversao (filial da nota ou UF do
# cliente) vem de _UF_LINHAS_WEB: uma regra so, para o cartao e para o
# `uf_linhas` das tabelas. Visita fica fora: nenhuma tabela traz a UF do
# cliente, o farol vai sem recortes e com aviso.
_TABELA_RECORTE_WEB = {"pl_inadimplencia": "Títulos", "pv_pedidos": "Pedidos",
                       "pl_entregas": "Entregas",
                       # (T-0023 v2, P3 A) estado = FILIAL da nota; Garantias
                       # nao tem filial: vai sem recorte e com aviso
                       "pl_devolucoes": "Devoluções", "pl_ncc": "NCC pendentes",
                       # (T-0024) cartao por estado dos farois livres
                       "pl_giro": "Todos os produtos",
                       "pl_frw": "Estoque FRW"}
# bloco do painel a mais por farol: so o "Frete por estado" do Farol de Entregas
_TIPOS_BLOCO_EXTRA_WEB = {"pl_entregas": ("tabela",)}
# bloco tabela com coluna de pessoa/cliente nunca vai (regra 6)
_COLUNAS_PESSOA_TABELA_WEB = ("cliente", "cnpj", "cpf", "razão", "razao",
                              "fantasia", "nome", "telefone", "e-mail",
                              "email", "contato")
# (T-0017, entrega 5) a Prospeccao agora vai ao site; fica no PC so o aviso
# da pasta das fotos (a coluna FOTO nunca vai)
_AVISO_SO_PC_WEB = ("foto da fachada", "(coluna foto)")


def _para_json(obj, _nivel: int = 0, fora=_PACOTE_WEB_CHAVES_ACAO):
    """Converte para tipos JSON; devolve _DESCARTAR para o que nao vai."""
    if _nivel > 40:
        return _DESCARTAR
    if obj is None or isinstance(obj, (bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if obj == obj and obj not in (float("inf"), float("-inf")) \
            else None
    if isinstance(obj, str):
        baixo = obj.lower().strip()
        return _DESCARTAR if baixo.endswith((".pkl", ".pickle")) else obj
    if isinstance(obj, (bytes, bytearray, Path)) or callable(obj):
        return _DESCARTAR
    if obj is pd.NaT:
        return None
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, pd.DataFrame):
        return _para_json(obj.to_dict("records"), _nivel + 1, fora)
    if isinstance(obj, pd.Series):
        return _para_json(obj.tolist(), _nivel + 1, fora)
    try:
        import decimal                                  # noqa: PLC0415
        if isinstance(obj, decimal.Decimal):
            return _para_json(float(obj), _nivel + 1, fora)
    except Exception:                                   # noqa: BLE001
        pass
    if isinstance(obj, dict):
        saida = {}
        for k, v in obj.items():
            ch = k if isinstance(k, str) else str(k)
            if ch.startswith("_") or ch in fora:
                continue
            val = _para_json(v, _nivel + 1, fora)
            if val is not _DESCARTAR:
                saida[ch] = val
        return saida
    if isinstance(obj, (list, tuple, set, frozenset)):
        itens = sorted(obj, key=str) if isinstance(obj, (set, frozenset)) \
            else obj
        saida = []
        for v in itens:
            val = _para_json(v, _nivel + 1, fora)
            if val is not _DESCARTAR:
                saida.append(val)
        return saida
    for metodo in ("item", "tolist"):                   # numpy
        if callable(getattr(obj, metodo, None)):
            try:
                return _para_json(getattr(obj, metodo)(), _nivel + 1, fora)
            except Exception:                           # noqa: BLE001
                pass
    return _DESCARTAR


def _agora_manaus() -> datetime:
    try:
        from zoneinfo import ZoneInfo                   # noqa: PLC0415
        return datetime.now(ZoneInfo("America/Manaus"))
    except Exception:                                   # noqa: BLE001
        from datetime import timedelta, timezone        # noqa: PLC0415
        return datetime.now(timezone(timedelta(hours=-4)))   # sem horario de verao


def _com_fuso_manaus(quando=None) -> datetime:
    """Funcao pura: `quando` (ou agora) com fuso; sem fuso vale Manaus (-04:00)."""
    quando = quando or _agora_manaus()
    if getattr(quando, "tzinfo", None) is None:
        from datetime import timedelta, timezone        # noqa: PLC0415
        quando = quando.replace(tzinfo=timezone(timedelta(hours=-4)))
    return quando


# de onde vem o "baixado em" de cada farol: (subpasta da raiz, padrao do arquivo
# que o robo baixou do ERP; vale o de nome mais novo). Os proximos farois
# (Pedidos, Entregas, Visita) ganham a propria fonte aqui.
_FONTE_BAIXADO_WEB = {
    "pl_inadimplencia": (Path(BKP_BAPTOOLS),
                         "Relatorio_Titulos_em_Abertos_*.xlsx"),
    # Pedidos e Entregas nascem dos Movimentos do Protheus (aba ftPedidos)
    "pv_pedidos": (Path(BKP_BAPTOOLS),
                   "Relatorio_Movimentos_BAP_Protheus_*.xlsx"),
    "pl_entregas": (Path(BKP_BAPTOOLS),
                    "Relatorio_Movimentos_BAP_Protheus_*.xlsx"),
    # Visita: o "Atualizar visitas" e manual no PC; vale a ultima gravacao do
    # VISITAS_POR_CLIENTE (o passo final do visitas_maxima)
    "vc_visitas": (Path(SUBPASTA_RELATORIOS) / "Visitas",
                   "VISITAS_POR_CLIENTE.xlsx"),
    # (T-0024) os faroes do lote 2 nascem dos Movimentos do Protheus
    **{r_: (Path(BKP_BAPTOOLS), "Relatorio_Movimentos_BAP_Protheus_*.xlsx")
       for r_ in RIDS_LIVRES_WEB},
    # Metas (T-0022): nasce dos mesmos Movimentos do Protheus (ftPedidos)
    "vc_meta": (Path(BKP_BAPTOOLS), "Relatorio_Movimentos_BAP_Protheus_*.xlsx"),
    # (T-0023 v2) Devolucoes e Garantias nascem dos Movimentos; a NCC, do
    # relatorio de NCC pendentes
    "pl_devolucoes": (Path(BKP_BAPTOOLS),
                      "Relatorio_Movimentos_BAP_Protheus_*.xlsx"),
    "pl_garantias": (Path(BKP_BAPTOOLS),
                     "Relatorio_Movimentos_BAP_Protheus_*.xlsx"),
    "pl_ncc": (Path(BKP_BAPTOOLS), "Relatorio_NCC_Pendentes*.xlsx")}


def _baixado_em_da_base(rid: str, raiz=None, arquivo=None):
    """Quando a base do farol foi baixada do ERP: a data de gravacao do
    arquivo de origem do rid (_FONTE_BAIXADO_WEB; inadimplencia = o relatorio
    Titulos em Abertos mais novo), em Manaus. `arquivo` forca o arquivo.
    Sem arquivo: None (o site diz que nao sabe, nao mostra a hora de hoje)."""
    try:
        if arquivo is None:
            pasta, padrao = _FONTE_BAIXADO_WEB[rid]
            arquivo = sorted((Path(raiz or PASTA_LOCAL) / pasta)
                             .glob(padrao))[-1]
        return datetime.fromtimestamp(Path(arquivo).stat().st_mtime,
                                      _agora_manaus().tzinfo)
    except Exception:                                   # noqa: BLE001
        return None


def recortes_por_uf(cartoes) -> dict:
    """Funcao pura (T-0014, RN-GER-006): as visoes prontas por estado, para o
    filtro da web. Nada e calculado: cada cartao da visao de um estado mostra
    a barra que o PC ja desenha para esse estado (texto e % ou variacao, com
    a legenda da barra); estado = filial da nota, como no PC.
    Cartao sem barra do estado fica com "—". Sem filtro por supervisor
    (R-20261123-191448-alexandre: so o filtro por estado).
    Devolve {"uf": {UF: {"cartoes": [...]}}}. Testes: tests/test_T0014_recortes_web.py."""
    ordem, por_uf = [], {}
    for c in cartoes or []:
        if not isinstance(c, dict):
            continue
        for b in ((c.get("estados") or {}).get("barras") or []):
            if (isinstance(b, (list, tuple)) and len(b) >= 5 and b[0]
                    and b[1] is not None and b[0] not in ordem):
                ordem.append(b[0])
    for uf in ordem:
        lista = []
        for c in cartoes or []:
            if not isinstance(c, dict):
                continue
            est = c.get("estados") or {}
            b = next((x for x in (est.get("barras") or [])
                      if isinstance(x, (list, tuple)) and len(x) >= 5
                      and x[0] == uf and x[1] is not None), None)
            # uma informacao, um lugar: sem a barra unica (repetiria o
            # numero); o % ou a variacao vai na legenda, com o que significa
            leg = " · ".join(x for x in ((b[3] if b else ""),
                                         (est.get("legenda") or "") if b
                                         and b[3] else "") if x)
            lista.append({
                "chave": c.get("chave"), "titulo": c.get("titulo", ""),
                "valor": (b[2] or "—") if b else "—", "legenda": leg,
                "aneis": [], "faixa": [], "estados": None,
                "ajuda": c.get("ajuda") or ""})
        por_uf[uf] = {"cartoes": lista}
    return {"uf": por_uf}


def selecionar_abas_web(r: dict) -> dict:
    """Funcao pura: do vc_painel montado, so as abas resultado e produtividade
    ({"titulo", "abas": {...}, "avisos"?}). A tela RRM le so dados[visao],
    sub[visao] e como_ler; o "diretor" (dd) nao e lido por ela e fica fora."""
    abas, avisos = {}, []
    for p in (r or {}).get("paineis") or []:
        if not isinstance(p, dict):
            continue
        bloco = next((b for b in ((p.get("painel") or {}).get("blocos") or [])
                      if isinstance(b, dict) and b.get("tipo") == "rrm"), None)
        vis = (bloco or {}).get("visao")
        chave = (_ABAS_WEB.get(vis) if vis
                 else _TITULOS_ABAS_WEB.get(p.get("titulo")))
        if not chave or chave in abas or bloco is None:
            continue
        vis = vis or next(v for v, c in _ABAS_WEB.items() if c == chave)
        d = bloco.get("dados") or {}
        dados = {k: d.get(k) for k in ("comp", "ano", "mes", "como_ler",
                                       "dados_ate", "avisos")}
        dados[vis] = d.get(vis)
        dados["sub"] = {vis: (d.get("sub") or {}).get(vis)}
        abas[chave] = {
            "titulo": p.get("titulo"),
            "kpis_export": p.get("kpis_export"),
            "painel": {"blocos": [{"tipo": "rrm", "visao": vis,
                                   "dados": dados,
                                   "row": bloco.get("row", 0),
                                   "col": bloco.get("col", 0),
                                   "colspan": bloco.get("colspan", 3)}],
                       "altura_min": (p.get("painel") or {}).get("altura_min")},
            "altura_min": (p.get("painel") or {}).get("altura_min"),
            # (T-0014) visoes prontas por estado (filtro da web)
            "recortes": recortes_por_uf(d.get(vis)),
        }
    for chave in _ABAS_WEB.values():
        if chave not in abas:
            avisos.append(f"Aba {chave} ausente do Painel neste pacote.")
    saida = {"titulo": (r or {}).get("titulo"), "abas": abas}
    if avisos:
        saida["avisos"] = avisos
    return saida


def _texto_com_pessoa(txt, grafico_com_nome, titulo=False) -> bool:
    baixo = str(txt or "").lower()
    termos = _TERMOS_CLIENTE_WEB + (() if grafico_com_nome
                                    else _TERMOS_PESSOA_WEB)
    if titulo:                          # titulo de grafico: por cliente sai
        termos += _TERMOS_TITULO_CLIENTE_WEB
    return any(t in baixo for t in termos)


def _linhas_insight(linhas, titulos_fora, grafico_com_nome) -> list:
    """Insights [(tom, texto)] sem a frase que cita cliente ou o grafico que
    saiu (a frase do ranking comeca pelo titulo do bloco)."""
    saida = []
    for ln in linhas or []:
        txt = ln[1] if isinstance(ln, (list, tuple)) and len(ln) > 1 else ln
        if _texto_com_pessoa(txt, grafico_com_nome) or any(
                str(txt).startswith(t) for t in titulos_fora):
            continue
        saida.append(ln)
    return saida


_AVISO_TECNICO_WEB = ("aderência =", "aderencia =", "rota_protheus")


AVISO_ABAS_FORA = "Abas fora desta atualização: {lista}. Veja no PC."


def _ordenar_avisos_web(avisos) -> list:
    """Funcao pura (contrato 10.7.6, ordem dos avisos do farol): 1 abas fora
    (falta de dado), 2 "Sem o arquivo", 3 "Sem filtro por estado", 4 os
    outros, na ordem do PC."""
    def peso(a):
        a = str(a)
        return (0 if a.startswith(AVISO_ABAS_FORA.split("{")[0]) else
                1 if a.startswith("Sem o arquivo") else
                2 if a.startswith("Sem filtro por estado") else 3)
    return sorted(avisos, key=peso)           # sorted e estavel


def _avisos_curtos_visita_web(avisos, maximo: int = 2) -> list:
    """Funcao pura: no celular o aviso do Farol de Visita e no maximo 2
    linhas, em linguagem de quem usa: sai o que traz nome de arquivo de rota
    ou a formula da aderencia. Ordem do contrato 10.7.6 (abas fora, arquivo
    faltando, estado, o resto); corta do fim, entao "abas fora" nunca sai."""
    ok = [a for a in avisos
          if not any(t in str(a).lower() for t in _AVISO_TECNICO_WEB)]
    return _ordenar_avisos_web(ok)[:maximo]


def _kpis_com_estados(r: dict, sem_dado_fora: bool = False) -> list:
    """Os cartoes do farol; cada um com "estados" ({"barras": [[UF, numero,
    texto, "% na barra", tom]], "legenda"}) quando o PC desenha as mini-barras
    por estado (relatorios_nucleo.estados_do_cartao, filial da nota). So
    numero por estado, sem pessoa."""
    saida = []
    for k in (r or {}).get("kpis") or []:
        if not isinstance(k, dict):
            continue
        k = dict(k)
        try:
            import relatorios_nucleo as _rn             # noqa: PLC0415
            est = _rn.estados_do_cartao(r, k) or {}
        except Exception:                               # noqa: BLE001
            est = {}
        barras = est.get("barras") or []
        if sem_dado_fora:          # estado sem dado (ex.: sem vendedor) sai
            barras = [b for b in barras if len(b) > 1 and b[1] is not None]
        if barras:
            k["estados"] = {"barras": barras,
                            "legenda": est.get("legenda", "")}
        saida.append(k)
    return saida


def selecionar_farol_web(rid: str, r: dict, baixado_em=None,
                         grafico_com_nome=None, cobranca=None,
                         raiz=None, por_uf=None) -> dict:
    """Funcao pura (T-0017): do farol montado, so a parte dado da forma "farol"
    (contrato, secao 10): {"forma", "titulo", "kpis", "painel": {"blocos"},
    "insights_painel", "avisos", "recortes", "baixado_em"}. baixado_em = a
    hora em que a base foi baixada do ERP (parametro; None se nao se sabe),
    nao a da montagem. Fica de fora: as
    tabelas (tem cliente/CNPJ), juntas, callables, chaves com "_" e as de
    edicao. Blocos do painel mantidos: insights, barras, hbarras (os cartoes vao
    em "kpis", no topo). hbarras (ou
    frase) com nome de pessoa sai enquanto WEB_GRAFICOS_COM_NOME for False;
    cliente e CNPJ nunca vao.
    (T-0017, entrega 2, contrato §10.6) So no pl_inadimplencia, com `cobranca`
    (o bloco de cobranca_whatsapp.pacote_web): acrescenta `tabelas` (Titulos e
    Por cliente, sem TELEFONE) e `cobranca`; as duas chaves vao juntas ou
    nenhuma.
    (T-0017, entregas 3 a 5, contrato §10.7) Nos 3 rid de RIDS_TABELAS_WEB
    acrescenta `tabelas` com todas as abas do PC (tabelas_farol_web; `raiz` =
    onde esta o SOLICITACAO_BAP.xlsx, padrao PASTA_LOCAL); a aba que nao
    bate com o contrato fica fora, com aviso."""
    if grafico_com_nome is None:
        grafico_com_nome = WEB_GRAFICOS_COM_NOME
    r = r or {}
    blocos, titulos_fora, avisos_extra = [], [], []
    tipos = _TIPOS_BLOCO_FAROL_WEB + _TIPOS_BLOCO_EXTRA_WEB.get(rid, ())
    brutos = list((r.get("painel") or {}).get("blocos") or [])
    if not brutos and (rid in RIDS_LIVRES_WEB
                       or rid in _GRAFICOS_NO_PAINEL_WEB):
        # (T-0024) farol sem painel (Painel de indicadores): os graficos do PC
        # viram blocos de barras, um embaixo do outro
        brutos = [{"tipo": "barras", "row": i, "col": 0, "colspan": 3,
                   "grafico": g} for i, g in enumerate(
                       g for g in r.get("graficos") or []
                       if isinstance(g, dict) and g.get("rotulos"))]
    for b in brutos:
        if not isinstance(b, dict) or b.get("tipo") not in tipos:
            continue
        if b.get("tipo") == "tabela":
            nomes = [str(c.get("nome") if isinstance(c, dict) else c).lower()
                     for c in b.get("colunas") or []]
            if any(t in n for n in nomes for t in _COLUNAS_PESSOA_TABELA_WEB):
                avisos_extra.append(f"Bloco {b.get('titulo') or 'tabela'} "
                                    "fica so no PC (traz cliente).")
                continue
        if b.get("tipo") == "hbarras" and _texto_com_pessoa(
                b.get("titulo"), grafico_com_nome, titulo=True):
            titulos_fora.append(str(b.get("titulo") or ""))
            continue
        if b.get("tipo") == "insights":
            b = dict(b)           # as frases so depois de saber os titulos fora
        blocos.append(b)
    for i, b in enumerate(blocos):
        if b.get("tipo") == "insights":
            blocos[i] = dict(b, linhas=_linhas_insight(
                b.get("linhas"), titulos_fora, grafico_com_nome))
    saida = {
        "forma": "farol",
        "titulo": r.get("titulo"),
        "kpis": _kpis_com_estados(r, sem_dado_fora=(rid == "vc_visitas")),
        "painel": {"blocos": blocos},
        "insights_painel": _linhas_insight(
            r.get("insights_painel"), titulos_fora, grafico_com_nome),
        "avisos": [str(a) for a in (r.get("avisos") or [])
                   if not any(t in str(a).lower() for t in _AVISO_SO_PC_WEB)]
                  + avisos_extra,
        "recortes": (_recortes_meta_web(por_uf, grafico_com_nome)
                     if rid == RID_META_WEB
                     else _recortes_kpis_por_uf_web(por_uf)
                     if rid in RIDS_KPIS_POR_UF_WEB
                     else _recortes_do_farol_web(rid, r)),
        # quando a base foi baixada do ERP (nao a hora da montagem); None = nao sei
        "baixado_em": (_com_fuso_manaus(baixado_em).isoformat()
                       if baixado_em else None)}
    if r.get("kpis_faixa"):          # Pedidos: cartoes em faixa, como o PC
        saida["kpis_faixa"] = True
    if not saida["recortes"] and rid != "pl_inadimplencia":
        saida["avisos"].append("Sem filtro por estado: os cartões "
                               "mostram a BAP inteira.")
    val = _para_json(saida, fora=_CHAVES_FORA_FAROL_WEB)
    val = val if isinstance(val, dict) else {}
    if rid == RID_COBRANCA_WEB and val and isinstance(cobranca, dict):
        tabs = tabelas_cobranca_web(r)
        cob = _para_json(cobranca, fora=_CHAVES_FORA_TABELA_WEB)
        if tabs and isinstance(cob, dict):
            val["tabelas"] = tabs
            val["cobranca"] = cob
        else:
            # colunas fora do contrato: o farol segue sem as abas novas
            log.warning("Pacote web: as colunas das tabelas do farol nao "
                        "batem com o contrato 10.6.2; farol sem tabelas e "
                        "sem cobranca.")
            val.setdefault("avisos", []).append(
                "Tabelas e cobrança no WhatsApp ficaram fora desta "
                "atualização: as colunas do PC não batem com o contrato.")
    if rid == RID_META_WEB and val:           # (T-0022) abas de tabela
        try:
            tabs, avs = tabelas_meta_web(r)
        except Exception as erro:                       # noqa: BLE001
            log.warning("Pacote web: tabelas do Farol de Metas fora do "
                        "pacote (%s).", type(erro).__name__)
            tabs, avs = [], [AVISO_ABAS_FORA.format(
                lista=", ".join(_ABAS_META_WEB))]
        if tabs:
            val["tabelas"] = tabs
        val["avisos"] = _ordenar_avisos_web((val.get("avisos") or []) + avs)
    if rid in RIDS_TABELAS_WEB and val:
        try:
            tabs, avs = tabelas_farol_web(rid, r, raiz)
        except Exception as erro:                       # noqa: BLE001
            log.warning("Pacote web: tabelas do farol %s fora do pacote "
                        "(%s).", rid, type(erro).__name__)
            tabs, avs = [], [AVISO_ABAS_FORA.format(
                lista=", ".join(_ABAS_TABELAS_WEB.get(rid) or [
                    t.get("titulo") for t in (r or {}).get("tabelas") or []
                    if isinstance(t, dict)]))]
        if tabs:
            val["tabelas"] = tabs
        val["avisos"] = (val.get("avisos") or []) + avs
        # ordem do contrato 10.7.6; na Visita, no maximo 2 (celular)
        val["avisos"] = (_avisos_curtos_visita_web(val["avisos"])
                         if rid == "vc_visitas"
                         else _ordenar_avisos_web(val["avisos"]))
    return val


# =============================================================================
# (T-0022) PAINEL EXECUTIVO COMPLETO E FAROL DE METAS EQUIPE NA WEB
# =============================================================================
# O Painel Executivo do PC tem 12 abas de painel (as tabelas Faróis, Por filial
# ... Executivos so vao no Excel/PDF: so_exportar). Resultado, produtividade e
# por dia util vao como cartoes RRM ("abas"); as outras 9 vao em "paineis", na
# forma do farol (kpis + blocos). O filtro e o do estado: a versao pronta de
# cada aba, montada pelo PC com o parametro UF (sem supervisor: R-20261123-191448).
# Farol de Metas Equipe (vc_meta): forma farol + as abas de tabela do PC
# (Equipe, Top 30 clientes, Por UF ... Por familia da peca), por estado igual.
# Fica de fora, de proposito: a aba "Acomp. RH" (META RH e RV: regra 8, so no
# Exportar para o RH, no e-mail e na parcial de RV).
PAINEIS_WEB = (("Resumo gerencial", "resumo"), ("Faturamento", "faturamento"),
               ("Volume", "volume"), ("Produtividade", "visitas"),
               ("Positivação", "positivacao"), ("Itens por pedido", "itens"),
               ("Markup", "markup"), ("Preço", "preco"),
               ("Inadimplência", "inadimplencia"))
# as outras 3 abas (Produtividade, Preco, Inadimplencia) sao da BAP inteira
# no PC tambem: o filtro de cima nao vale para elas
_PAINEIS_UF_WEB = frozenset({"resumo", "faturamento", "volume", "positivacao",
                             "itens", "markup"})
_TIPOS_PAINEL_WEB = ("insights", "barras", "hbarras", "tabela", "placar")
_TIPOS_META_WEB = ("insights", "barras", "hbarras")
# grafico POR cliente sai (regra 6); "1º cliente do dia" e "ultimo cliente"
# sao horarios, nao cliente: ficam
_TITULOS_POR_CLIENTE_WEB = ("por cliente", "cliente a cliente",
                            "maiores clientes", "top 30", "top 50")
# coluna de pessoa/cliente em bloco tabela: a palavra inteira ("KM/CLIENTE" e
# "CLIENTES" sao numeros, nao o nome do cliente); = render._PESSOA_NO_BLOCO
_PESSOA_BLOCO_WEB = re.compile(
    r"(?<![\w/])(cliente|raz[aã]o|fantasia|nome|cnpj|cpf|telefone|e-mail|"
    r"email|contato)(?!\w)", re.I)
_PLACAR_CHAVES_WEB = ("farol", "valor", "rotulo", "tom", "detalhe",
                      "sentido", "frase", "dica", "impacto")
RID_META_WEB = "vc_meta"
_ABAS_META_WEB = ("Equipe", "Top 30 clientes", "Por UF", "Por cidade",
                  "Por bairro", "Por segmento", "Por zona", "Por categoria",
                  "Por família da peça")
# a aba Acomp. RH tem a META RH: nunca vai (regra 8 do CLAUDE.md)
_ABAS_META_FORA_WEB = ("Acomp. RH",)
_FAIXA_ATING_WEB = [[79.9999, "#FBDDDA", "#B3261E"],
                    [99.9999, "#FFF1C7", "#8A5A00"],
                    [None, "#E5F3DF", "#2F7D32"]]      # = FAIXA_PCT_META


def _blocos_painel_web(r, tipos, grafico_com_nome):
    """(blocos, titulos_fora, avisos) do `painel` de um relatorio do PC, so os
    `tipos`; tabela com coluna de pessoa/cliente e grafico por cliente saem;
    cartao do placar com cliente na frase sai (regra 6)."""
    blocos, fora, avisos = [], [], []
    for b in ((r or {}).get("painel") or {}).get("blocos") or []:
        if not isinstance(b, dict) or b.get("tipo") not in tipos:
            continue
        tipo = b["tipo"]
        titulo = b.get("titulo") or (b.get("grafico") or {}).get("titulo")
        if tipo == "tabela":
            nomes = [str(c.get("nome") if isinstance(c, dict) else c)
                     for c in b.get("colunas") or []]
            if any(_PESSOA_BLOCO_WEB.search(n) for n in nomes):
                avisos.append(f"Bloco {titulo or 'tabela'} fica so no PC "
                              "(traz cliente).")
                continue
        if tipo in ("barras", "hbarras") and (_texto_com_pessoa(
                titulo, grafico_com_nome) or any(
                    t in str(titulo or "").lower()
                    for t in _TITULOS_POR_CLIENTE_WEB)):
            fora.append(str(titulo or ""))
            continue
        if tipo == "placar":
            cs = [{k: c[k] for k in _PLACAR_CHAVES_WEB if k in c}
                  for c in b.get("cartoes") or []
                  if isinstance(c, dict) and not any(
                      _texto_com_pessoa(c.get(k), grafico_com_nome)
                      for k in ("frase", "detalhe", "dica"))]
            b = dict(b, cartoes=cs)
        blocos.append(b)
    for i, b in enumerate(blocos):
        if b.get("tipo") == "insights":
            blocos[i] = dict(b, linhas=_linhas_insight(
                b.get("linhas"), fora, grafico_com_nome))
    return blocos, fora, avisos


def _corpo_painel_web(r, tipos, grafico_com_nome):
    """{"kpis", "painel": {"blocos"}} de um painel (ou de um relatorio) do PC."""
    blocos, _f, avisos = _blocos_painel_web(r, tipos, grafico_com_nome)
    return ({"kpis": [k for k in (r or {}).get("kpis") or []
                      if isinstance(k, dict)],
             "painel": {"blocos": blocos}}, avisos)


def selecionar_paineis_web(r: dict, r_uf=None, grafico_com_nome=None) -> dict:
    """Funcao pura (T-0022): as 9 abas de painel do Painel Executivo (depois
    das 3 RRM) na forma do farol, {chave: {"titulo", "kpis", "painel":
    {"blocos"}, "recortes"?, "so_bap"?}}. `r_uf` = {UF: vc_painel montado com
    o parametro UF}: vira `recortes` das abas que o filtro do PC alcanca
    (_PAINEIS_UF_WEB); as outras levam `so_bap` (como no PC). Aba que nao veio
    fica fora. Nada e recalculado."""
    if grafico_com_nome is None:
        grafico_com_nome = WEB_GRAFICOS_COM_NOME
    por_titulo = {p.get("titulo"): p for p in (r or {}).get("paineis") or []
                  if isinstance(p, dict)}
    saida = {}
    for titulo, chave in PAINEIS_WEB:
        p = por_titulo.get(titulo)
        if not p:
            continue
        corpo, avisos = _corpo_painel_web(p, _TIPOS_PAINEL_WEB,
                                          grafico_com_nome)
        aba = {"titulo": titulo, **corpo}
        if avisos:
            aba["avisos"] = avisos
        if chave not in _PAINEIS_UF_WEB:
            aba["so_bap"] = True
        else:
            rec = {}
            for uf in sorted(r_uf or {}):
                pu = next((x for x in (r_uf[uf] or {}).get("paineis") or []
                           if isinstance(x, dict) and x.get("titulo")
                           == titulo), None)
                if pu:
                    rec[uf], _a = _corpo_painel_web(pu, _TIPOS_PAINEL_WEB,
                                                    grafico_com_nome)
            if rec:
                aba["recortes"] = rec
        saida[chave] = aba
    return saida


def _ufs_do_parametro_web(r) -> list:
    """Os estados do filtro UF do PC (as opcoes da caixa), sem '(todos)'."""
    import re                                           # noqa: PLC0415
    for p in (r or {}).get("parametros") or []:
        if isinstance(p, dict) and p.get("nome") == "UF":
            vals = [v[0] if isinstance(v, (list, tuple)) else v
                    for v in p.get("valores") or []]
            return sorted(v for v in vals
                          if isinstance(v, str) and re.fullmatch("[A-Z]{2}", v))
    return []


# (T-0024, RN-GER-006) farois cujo cartao do estado e o do PC com o filtro UF
RIDS_KPIS_POR_UF_WEB = ("vc_base",)


def _recortes_kpis_por_uf_web(por_uf) -> dict:
    """Funcao pura: {UF: {"kpis": cartoes do `montar` com UF=<estado>}}, o
    mesmo numero do filtro de estado do PC. Sem `por_uf`: {}."""
    saida = {}
    for uf in sorted(por_uf or {}):
        ks = [dict(k) for k in (por_uf[uf] or {}).get("kpis") or []
              if isinstance(k, dict)]
        if ks:
            saida[uf] = {"kpis": ks}
    return saida


def montar_por_uf_web(rid: str, rel, raiz, params: dict, hoje=None) -> dict:
    """{UF: relatorio montado com o parametro UF} (o filtro de estado do PC),
    para o recorte da web. vc_painel guarda so os `paineis` (memoria). Um
    estado que falhar fica fora, com aviso no log (o resto segue)."""
    import relatorios_nucleo as _rn                     # noqa: PLC0415
    saida = {}
    for uf in _ufs_do_parametro_web(rel):
        try:
            r_uf = _rn.montar(rid, Path(raiz), hoje=hoje,
                              params=dict(params, UF=uf),
                              tela=(rid == RID_META_WEB))
        except Exception as erro:                       # noqa: BLE001
            log.warning("Pacote web: %s do estado %s fora do pacote (%s).",
                        rid, uf, type(erro).__name__)
            continue
        saida[uf] = ({"paineis": r_uf.get("paineis")} if rid == "vc_painel"
                     else r_uf)
    return saida


def _coluna_meta_web(c, com_grupos):
    c = c if isinstance(c, dict) else {"nome": c, "tipo": "texto"}
    col = {"nome": c["nome"], "tipo": c.get("tipo") or "texto"}
    for k in ("largura", "larg_fixa"):
        if c.get(k) is not None:
            col[k] = int(c[k])
    if c.get("oculta"):
        col["oculta"] = True
    if com_grupos and c.get("curto"):
        col["curto"] = str(c["curto"])
    if c.get("ating"):                  # % ating.: vermelho/amarelo/verde
        col["chip"] = [list(f) for f in _FAIXA_ATING_WEB]
    return col


def tabela_meta_web(t: dict, _junta: bool = False):
    """Funcao pura (T-0022): uma tabela do Farol de Metas Equipe no formato
    web, ou None se nao der (so essa aba fica fora). Colunas, linhas, total,
    grupos (cabecalho agrupado), filtros e, no Top 30, a carteira inteira
    (`linhas_filtro`) e o `top_n`, como a tela do PC. Cliente sem documento
    (RN-GER-011); coluna de telefone/CNPJ... nunca vai."""
    titulo = (t or {}).get("titulo")
    pc = list(t.get("colunas") or [])
    nomes = [c.get("nome") if isinstance(c, dict) else c for c in pc]
    if not nomes or any(_coluna_proibida_web(n) for n in nomes):
        log.warning("Pacote web: tabela '%s' do Farol de Metas fora do "
                    "pacote (coluna proibida ou vazia).", titulo)
        return None
    funcs = _funcoes_limpeza_web()
    grupos = [[str(g), int(n)] for g, n in t.get("grupos") or []]
    if grupos and sum(n for _g, n in grupos) != len(nomes):
        grupos = []
    cols = [_coluna_meta_web(c, bool(grupos)) for c in pc]
    cli = [i for i, n in enumerate(nomes) if n == "CLIENTE"]

    def limpar(ln):
        ln = list(ln)
        for i in cli:
            ln[i] = _limpar_celula_web(ln[i], funcs["cliente_sem_documento"])
        return ln
    brutas = t.get("linhas_filtro") if t.get("top_n") and t.get(
        "linhas_filtro") else t.get("linhas")
    tons = (t.get("tons_filtro") if brutas is t.get("linhas_filtro")
            else t.get("tons")) or []
    linhas = [limpar(ln) for ln in brutas or []]
    if any(len(ln) != len(nomes) for ln in linhas):
        log.warning("Pacote web: tabela '%s' do Farol de Metas fora do "
                    "pacote (linhas).", titulo)
        return None
    saida = {"titulo": titulo, "colunas": cols, "linhas": linhas,
             "tons": [str(x or "") for x in tons][:len(linhas)]
             + [""] * max(0, len(linhas) - len(tons))}
    if t.get("total"):                  # celula vazia do PC ("") = null
        saida["total"] = [None if v == "" else v for v in t["total"]]
    if grupos:
        saida["grupos"] = grupos
    fl = [f for f in t.get("filtros") or []
          if (f if isinstance(f, str) else (f or {}).get("coluna")) in nomes]
    if fl:
        saida["filtros"] = fl
    if t.get("top_n"):
        saida["top_n"] = int(t["top_n"])
        if t.get("ordem_top"):
            saida["ordem_top"] = [int(x) for x in t["ordem_top"]]
        # sem total: com filtro o total e recalculado no PC (callable)
        saida.pop("total", None)
    if not _junta:
        if t.get("juntas_em_cima"):
            saida["juntas_em_cima"] = True
        if t.get("titulo_tabela"):
            saida["titulo_tabela"] = str(t["titulo_tabela"])
        juntas = []
        for j in t.get("juntas") or []:
            tj = tabela_meta_web(j.get("tabela") or {}, _junta=True)
            if tj is None:
                return None
            juntas.append({"titulo": j.get("titulo") or tj["titulo"],
                           "tabela": tj})
        if juntas:
            saida["juntas"] = juntas
    return saida


def tabelas_meta_web(r: dict):
    """(lista de tabelas, avisos) do Farol de Metas Equipe, na ordem do PC;
    sem a aba Acomp. RH (regra 8). A aba que nao der fica fora, com aviso."""
    por_titulo = {t.get("titulo"): t for t in (r or {}).get("tabelas") or []
                  if isinstance(t, dict)}
    saida, fora = [], []
    for titulo in _ABAS_META_WEB:
        t = por_titulo.get(titulo)
        if not t:
            continue
        tab = tabela_meta_web(t)
        (saida if tab is not None else fora).append(
            tab if tab is not None else titulo)
    avisos = [AVISO_ABAS_FORA.format(lista=", ".join(fora))] if fora else []
    return saida, avisos


def _recortes_meta_web(por_uf, grafico_com_nome) -> dict:
    """{UF: {"kpis", "painel": {"blocos"}, "tabelas"}}: o Farol de Metas
    montado pelo PC com o filtro de UF (cartoes, graficos e tabelas do
    estado). Estado cujas tabelas nao deram fica so com os cartoes."""
    saida = {}
    for uf in sorted(por_uf or {}):
        r_uf = por_uf[uf] or {}
        corpo, _a = _corpo_painel_web(r_uf, _TIPOS_META_WEB, grafico_com_nome)
        ins = _linhas_insight(r_uf.get("insights_painel"), [],
                              grafico_com_nome)
        if ins:
            corpo["insights_painel"] = ins
        tabs, _av = tabelas_meta_web(r_uf)
        if tabs:
            corpo["tabelas"] = tabs
        saida[uf] = corpo
    return saida


# ---------------------------------------------------------------------------
# (T-0017, entrega 2) Titulos e Por cliente no pacote do pl_inadimplencia
# (contrato §10.6.2): so as colunas da lista do contrato (nome e tipo), sem
# TELEFONE, CNPJ, CPF ou E-MAIL. Fora das tabelas: edicao, detalhe, kpis_de,
# recortes, callables e chaves com "_".
RID_COBRANCA_WEB = "pl_inadimplencia"
_COLUNAS_SEM_STATUS_WEB = {
    "Títulos": (
        ("SITUAÇÃO", "texto"), ("FAIXA", "texto"), ("FILIAL", "texto"),
        ("NF", "texto"), ("PARC.", "texto"), ("EMISSÃO", "data"),
        ("VENCIMENTO", "data"), ("DIAS ATRASO", "int"),
        ("CLIENTE", "texto"), ("NOME", "texto"), ("CIDADE", "texto"),
        ("UF", "texto"), ("VENDEDOR", "texto"), ("SUPERVISOR", "texto"),
        ("CONDIÇÃO", "texto"), ("VALOR", "moeda"), ("SALDO", "moeda")),
    "Por cliente": (
        ("SITUAÇÃO", "texto"), ("FAIXA", "texto"), ("CLIENTE", "texto"),
        ("NOME", "texto"), ("CIDADE", "texto"), ("UF", "texto"),
        ("VENDEDOR", "texto"), ("SUPERVISOR", "texto"),
        ("TÍTULOS VENCIDOS", "int"), ("EM ATRASO", "moeda"),
        ("MAIOR ATRASO", "int"), ("A VENCER", "moeda"),
        ("PRÓX. VENCIMENTO", "data"), ("LIMITE", "moeda"),
        ("PEDIDO EM ABERTO", "moeda"), ("ÚLTIMA COMPRA", "data"))}
# o bloco de status (as 3 juntas, logo depois de NOME) e opcional (10.6.2)
_STATUS_WEB = (("STATUS PROTHEUS", "texto"), ("STATUS", "texto"),
               ("SITUAÇÃO PLANNER", "texto"))
_STATUS_OCULTAS_WEB = {"STATUS PROTHEUS", "SITUAÇÃO PLANNER"}
_COLUNAS_COM_CHIP_WEB = ("SITUAÇÃO", "FAIXA", "STATUS")


def _colunas_esperadas_web(titulo: str, com_status: bool) -> tuple:
    base = _COLUNAS_SEM_STATUS_WEB[titulo]
    if not com_status:
        return base
    i = [n for n, _ in base].index("NOME") + 1
    return base[:i] + _STATUS_WEB + base[i:]


_CHAVES_FORA_TABELA_WEB = (_CHAVES_FORA_FAROL_WEB - {"tabelas"}) | {
    "detalhe", "recortes", "exportar", "exportar_protheus"}


def tabelas_cobranca_web(r: dict):
    """Funcao pura: [Titulos, Por cliente] do farol montado no formato do
    contrato 10.6.2, ou None se as colunas do PC (menos TELEFONE) nao baterem
    com a lista do contrato (nome, ordem, tipo e oculta; o bloco de status
    vai inteiro, depois de NOME, ou nao vai): nunca manda tabela torta, que
    a web recusaria no pacote inteiro. `chip` e `tons` como o PC entrega
    (chip so em SITUACAO, FAIXA e STATUS). NOME sai sem CPF/CNPJ no
    comeco (cobranca_whatsapp.nome_sem_documento, RN-POS-004); sem essa
    funcao, None."""
    por_titulo = {t.get("titulo"): t for t in (r or {}).get("tabelas") or []
                  if isinstance(t, dict)}
    try:                # RN-POS-004: NOME sem CPF/CNPJ no comeco. Sem a
        sem_doc = _cobranca_whatsapp().nome_sem_documento   # funcao, nao vai
    except Exception:                                   # noqa: BLE001
        return None
    saida = []
    for titulo in _COLUNAS_SEM_STATUS_WEB:
        t = por_titulo.get(titulo)
        if not t:
            return None
        pc = [c if isinstance(c, dict) else {"nome": c, "tipo": "texto"}
              for c in t.get("colunas") or []]
        idx = [i for i, c in enumerate(pc)
               if str(c.get("nome")).upper() != "TELEFONE"]
        atuais = [(pc[i].get("nome"), pc[i].get("tipo"),
                   bool(pc[i].get("oculta"))) for i in idx]
        esperado = None
        for com_status in (True, False):
            lista = _colunas_esperadas_web(titulo, com_status)
            if atuais == [(n, tp, n in _STATUS_OCULTAS_WEB)
                          for n, tp in lista]:
                esperado = lista
                break
        if esperado is None:
            return None
        colunas = []
        for i in idx:
            c = pc[i]
            col = {"nome": c["nome"], "tipo": c["tipo"]}
            if c.get("largura") is not None:
                col["largura"] = int(c["largura"])
            if c.get("larg_fixa") is not None:
                col["larg_fixa"] = int(c["larg_fixa"])
            if c.get("oculta"):
                col["oculta"] = True
            if c.get("chip") and c["nome"] in _COLUNAS_COM_CHIP_WEB:
                col["chip"] = c["chip"]
            colunas.append(col)
        linhas = []
        for ln in t.get("linhas") or []:
            if len(ln) != len(pc):
                return None
            linhas.append([ln[i] for i in idx])
        inome = [c["nome"] for c in colunas].index("NOME")
        for ln in linhas:
            ln[inome] = sem_doc(ln[inome]) if ln[inome] else ln[inome]
        total = t.get("total")
        if isinstance(total, (list, tuple)) and len(total) == len(pc):
            total = [total[i] for i in idx]
        else:
            total = None
        nomes = {n for n, _ in esperado}
        filtros = []
        for f in t.get("filtros") or []:
            col = f.get("coluna") if isinstance(f, dict) else f
            if col in nomes:
                filtros.append(f)
        tons = [str(x or "") for x in t.get("tons") or []]
        if len(tons) != len(linhas):
            tons = [""] * len(linhas)
        saida.append({"titulo": titulo, "colunas": colunas, "linhas": linhas,
                      "tons": tons, "total": total, "filtros": filtros})
    for titulo, lista in _COLUNAS_EXTRAS_COBRANCA_WEB.items():   # T-0026
        t = por_titulo.get(titulo)
        extra = _tabela_extra_cobranca_web(t, titulo, lista) if t else None
        if extra is None:
            break                       # so a sequencia inteira vai (a web confere a ordem)
        saida.append(extra)
    val = _para_json(saida, fora=_CHAVES_FORA_TABELA_WEB)
    return val if isinstance(val, list) and len(val) >= 2 else None


# (T-0026) As 5 tabelas de resumo da Inadimplencia (sem cliente nem telefone):
# lista fechada de colunas, como as duas de cima; se nao bater, ficam fora.
_FAIXAS_COBRANCA_WEB = (
    ("CARTEIRA ABERTA", "moeda"), ("A VENCER", "moeda"),
    ("1–15 DIAS", "moeda"), ("16–30 DIAS", "moeda"),
    ("31–60 DIAS", "moeda"), ("61–90 DIAS", "moeda"),
    ("91–180 DIAS", "moeda"), ("+180 DIAS", "moeda"),
    ("EM ATRASO", "moeda"), ("% INADIMPL.", "pct"),
    ("CLIENTES INADIMPL.", "int"))
_COLUNAS_EXTRAS_COBRANCA_WEB = {
    "Por vendedor": (("VENDEDOR", "texto"),) + _FAIXAS_COBRANCA_WEB,
    "Por supervisor": (("SUPERVISOR", "texto"),) + _FAIXAS_COBRANCA_WEB,
    "Por filial": (("FILIAL", "texto"),) + _FAIXAS_COBRANCA_WEB,
    "Por UF": (("UF", "texto"),) + _FAIXAS_COBRANCA_WEB,
    "Dia a dia": (("DATA", "data"), ("CARTEIRA ABERTA", "moeda"),
                  ("A VENCER", "moeda"), ("EM ATRASO", "moeda"),
                  ("% INADIMPL.", "pct"), ("CLIENTES INADIMPL.", "int"),
                  ("TÍTULOS VENCIDOS", "int"), ("RECEBIDO", "moeda"),
                  ("RECUPERADO", "moeda")),
}


def _tabela_extra_cobranca_web(t: dict, titulo: str, lista):
    """Funcao pura: a tabela de resumo no formato do contrato, ou None se as
    colunas do PC nao baterem com a lista."""
    pc = [c if isinstance(c, dict) else {"nome": c, "tipo": "texto"}
          for c in t.get("colunas") or []]
    if [(c.get("nome"), c.get("tipo")) for c in pc] != list(lista):
        return None
    linhas = [list(ln) for ln in t.get("linhas") or []]
    if any(len(ln) != len(pc) for ln in linhas):
        return None
    total = t.get("total")
    total = list(total) if isinstance(total, (list, tuple)) and len(
        total) == len(pc) else None
    tons = [str(x or "") for x in t.get("tons") or []]
    if len(tons) != len(linhas):
        tons = [""] * len(linhas)
    return {"titulo": titulo,
            "colunas": [{"nome": n, "tipo": tp} for n, tp in lista],
            "linhas": linhas, "tons": tons, "total": total, "filtros": []}


# ---------------------------------------------------------------------------
# (T-0017, entregas 3 a 5, contrato §10.7) Todas as abas de tabela do PC nos
# Farois de Pedidos, Entregas e Visita. Regras das tabelas da Inadimplencia
# ("1 A", "2 A", "6 A"): sem CPF/CNPJ, telefone, e-mail, contato e foto; sem
# exportar; o que grava (autorizar, trocar loja de coleta, editar entrega,
# atualizar visitas) fica so no PC. RN-GER-011: nome de cliente limpo de
# documento (o codigo fica) e texto livre sem telefone/e-mail/documento.
# Decisoes tomadas com a recomendacao A (D1 a D6, ainda com o Alexandre):
# D2 so o mes; D3 Solicitacao BAP inteira; D6 texto livre vai com
# texto_sem_contato.
# ---------------------------------------------------------------------------
WEB_PACOTE_TETO_MB = 20            # trava do robo (o teto da web e 25: render.yaml)
WEB_FAROL_TETO_MB = 8              # (T-0035, 10.8.7) formato 2: JSON do farol sem anexos
_ANEXOS_FAROL_WEB = ("parciais", "csvs_protheus")
# tetos dos anexos: os MESMOS da web (web/app/pacotes.py); acima deles a web
# recusa o farol (422), entao o robo tira so o anexo, com aviso (10.8.7)
MAX_PNG_B64 = 3_000_000            # por imagem de parcial (caracteres base64)
MAX_CSVS_WEB = 60                  # quantidade de CSVs do Protheus
MAX_CSV_BYTES_WEB = 200_000        # por CSV (UTF-8)
MAX_CSVS_TOTAL = 1_500_000         # soma dos CSVs (UTF-8)
AVISO_PARCIAIS_FORA = ("As parciais em imagem ficaram fora desta "
                       "atualização (pacote grande). Veja no PC.")
AVISO_CSVS_FORA = ("Os CSVs do Protheus ficaram fora desta atualização "
                   "(pacote grande). Veja no PC.")
AVISO_SOLICITACAO_ABERTO = ("A Solicitação BAP foi reduzida aos pedidos em "
                            "aberto para caber no pacote.")
AVISO_JUNTA_ENTREGAS = ("A junta de pendências dos meses anteriores ficou "
                        "fora desta atualização (pacote grande). Veja no PC.")
AVISO_ENTREGAS_RECENTES = ("A aba Entregas ficou só com as entregas mais "
                           "recentes para caber no pacote. Veja o resto no "
                           "PC.")
# ordem dos cortes por farol (10.8.7); no fim, qualquer farol perde as `tabelas`
_CORTES_FAROL_WEB = {
    # (T-0023 v2, 10.10.4) o Historico de compra (1,25 MB) sai primeiro
    "pl_garantias": ("historico_fora", "tabelas"),
    "pv_pedidos": ("solicitacao_so_em_aberto", "tabelas"),
    "pl_entregas": ("junta_pendencias_fora", "entregas_so_recentes",
                    "tabelas"),
    "vc_visitas": ("cliente_a_cliente_fora", "tabelas"),
}
# Entregas: fatias de linhas (mais recentes primeiro) tentadas antes de a aba
# sair inteira. [SUPOSICAO] colunas nao sao cortadas: o `tons`, os recortes e
# a edicao apontam para o indice delas.
_FRACOES_ENTREGAS_WEB = (0.75, 0.5, 0.25)
RIDS_TABELAS_WEB = ("pv_pedidos", "pl_entregas", "vc_visitas") \
    + RIDS_LIVRES_WEB + ("pl_garantias", "pl_devolucoes", "pl_ncc")
# (T-0023 v2, 10.10.1) o NCC nao tem painel no PC: os `graficos` viram blocos
# `barras` do painel, na ordem do PC (o robo monta, a web nao calcula)
_GRAFICOS_NO_PAINEL_WEB = ("pl_ncc",)
# colunas que nunca vao (sem acento, maiusculas), em qualquer tabela/junta/sub-aba
_COLUNAS_FORA_WEB = frozenset({
    "TELEFONE", "CELULAR", "WHATSAPP", "CNPJ", "CPF", "E-MAIL", "EMAIL",
    "CONTATO", "FOTO", "ENDERECO"})
# a aba da web -> o titulo da tabela do PC (ordem do contrato 10.7.1)
_ABAS_TABELAS_WEB = {
    "pv_pedidos": ("Pedidos", "Solicitação BAP"),
    "pl_entregas": ("Entregas",),
    "vc_visitas": ("Por supervisor", "Por vendedor", "Dia a dia",
                   "Aderência dia a dia", "Cliente a cliente", "Prospecção",
                   "Indicação"),
    # (T-0023 v2, 10.10.1) na ordem do PC
    "pl_garantias": ("Garantias", "Histórico de compra", "Por produto",
                     "Status x resultado"),
    "pl_devolucoes": ("Devoluções", "Por motivo", "Por vendedor (12 meses)",
                      "Por cliente (12 meses)", "Por produto (12 meses)"),
    "pl_ncc": ("NCC pendentes", "Por cliente", "Por filial", "Por vendedor",
               "Por supervisor")}
TITULO_SOLICITACAO_WEB = "Solicitação BAP"
# tabelas que o PC carrega com 12 meses e a web recebe so do mes (D2 A)
_TABELAS_SO_MES_WEB = ("Pedidos", "Entregas")
# UF de cada linha (RN-GER-006): (coluna, "filial" = filial da nota |
# "uf" = UF do cliente)
_UF_LINHAS_WEB = {
    ("pl_inadimplencia", "Títulos"): ("FILIAL", "filial"),
    ("pv_pedidos", "Pedidos"): ("FILIAL", "filial"),
    ("pl_entregas", "Entregas"): ("UF", "uf"),
    ("pl_entregas", "Pendências dos meses anteriores"): ("UF", "uf"),
    # (T-0024) filial (estoque). Base de clientes: o estado vem do `montar`
    # com UF (RIDS_POR_UF_WEB); Planner nao tem filtro UF: sem recorte
    ("pl_giro", "Todos os produtos"): ("FILIAL", "filial"),
    ("pl_frw", "Estoque FRW"): ("FILIAL", "filial"),
    # (T-0023 v2, P3 A) a FILIAL da nota, como o faturamento. Garantias nao
    # tem; o "Por cliente" da NCC nao tem FILIAL: vai sem estado
    ("pl_devolucoes", "Devoluções"): ("FILIAL", "filial"),
    ("pl_ncc", "NCC pendentes"): ("FILIAL", "filial")}


def _c(nome, tipo, oculta=False, selo=None):
    """(nome, tipo, oculta, selo); selo = None | "faixa" (chip por faixa de
    numero) | "texto" (chip por texto) | "barra" | "tom" (chip_tom)."""
    return (nome, tipo, oculta, selo)


_SEPARACAO_WEB = (
    _c("DATA", "dia"), _c("UF", "texto"), _c("CIDADE", "texto"),
    _c("PEDIDOS", "texto"), _c("FORN.", "texto"), _c("CÓD. PROD.", "texto"),
    _c("DESCRIÇÃO", "texto"), _c("QTD", "num"), _c("COLETAR EM", "texto"),
    _c("FILIAL DEST.", "texto"))
_ENTREGAS_WEB = (
    _c("SITUAÇÃO", "texto"), _c("SLA", "int", selo="tom"),
    _c("DT. PED", "dia"), _c("DT. NF", "dia"), _c("DT. PREVISTA", "dia"),
    _c("DT. REAL", "dia"), _c("UF", "texto"), _c("CIDADE", "texto"),
    _c("CLIENTE", "texto"), _c("VLR NF", "moeda"), _c("VLR FRETE", "moeda"),
    _c("TRANSPORTADORA", "texto"), _c("RESPONSÁVEL", "texto"),
    _c("TBL FRETE", "moeda"), _c("VLR REAL FRETE", "moeda"),
    _c("ETAPA", "texto"), _c("NF", "texto"), _c("FILIAL", "texto"),
    _c("LOCAL/FRETE", "texto", True), _c("TOM SLA", "texto", True),
    _c("PRAZO", "texto", True, "texto"))
_METRICAS_VISITA_WEB = (
    _c("META", "num"), _c("VISIT.", "int"),
    _c("% META", "pct", selo="faixa"), _c("% CONV.", "pct"),
    _c("% FORA DE ROTA", "pct"), _c("CAD.", "int"),
    _c("CAD. C/ COMPRA", "int"), _c("PROSP.", "int"),
    _c("INÍCIO", "hora"), _c("ÚLT. ATIV.", "hora"),
    _c("JORNADA LÍQ.", "hora"), _c("DIAS < JORN. LÍQ.", "int"),
    _c("INTERV. ALMOÇO", "hora"), _c("DIAS ALMOÇO > MÁX.", "int"),
    _c("TMA", "hora"), _c("TMD", "hora"), _c("KM", "num"),
    _c("KM/CLIENTE", "num1"))

# contrato 10.7.3: {rid: {titulo da tabela: colunas depois do corte}}
_COLUNAS_TABELAS_WEB = {
    "pv_pedidos": {
        "Pedidos": (
            _c("DT. PED", "dia"), _c("FATURAR ATÉ", "dia"),
            _c("PEDIDO", "texto"), _c("PED. MÁX.", "texto"),
            _c("CÓD.", "texto"), _c("RAZÃO SOCIAL", "texto"),
            _c("FANTASIA", "texto"), _c("UF", "texto"),
            _c("CIDADE", "texto"), _c("LIMITE", "moeda"),
            _c("DISP.", "moeda"), _c("ATRASO", "moeda"),
            _c("VOL.", "num"), _c("R$ TABELA", "moeda"),
            _c("R$ VENDA", "moeda"), _c("% DESC.", "pct1"),
            _c("SLA", "int", selo="faixa"),
            _c("% ATENDIDO", "pct", selo="barra"),
            _c("ANÁLISE CRÉDITO", "texto"), _c("COND. PAGTO", "texto"),
            _c("SITUAÇÃO", "texto"), _c("FILIAL", "texto"),
            _c("PRAZO", "texto"), _c("VENDEDOR", "texto"), _c("NF", "texto"),
            _c("DT. NF", "dia"), _c("R$ TABELA CHEIA", "moeda", True),
            _c("CÓD. AUTORIZAÇÃO", "texto", True),
            _c("AUTORIZADO POR", "texto", True), _c("MÊS", "texto", True),
            _c("ENTREGUE EM", "dia", True), _c("PRODUTO", "texto", True),
            _c("CHAVE", "texto", True)),
        "Gerar separação CD": _SEPARACAO_WEB,
        "Gerar reversa de lojas": _SEPARACAO_WEB,
        "Analítico produto": (
            _c("PEDIDO", "texto"), _c("DATA", "dia"), _c("CIDADE", "texto"),
            _c("FILIAL", "texto"), _c("FORN.", "texto"),
            _c("CÓD. PROD.", "texto"), _c("DESCRIÇÃO", "texto"),
            _c("QTD", "num"), _c("EST. FRW", "num"),
            _c("PEDIDOS ANTES", "num"), _c("DISP. P/ ESTE", "num"),
            _c("ATENDIDO", "num"), _c("FALTA", "num"),
            _c("CLIENTE", "texto"), _c("FILIAL BAP", "texto", True),
            _c("VALOR FALTANTE", "moeda"))},
    "pl_entregas": {
        "Entregas": (_c("MÊS", "texto", True),) + _ENTREGAS_WEB,
        "Pendências dos meses anteriores": (
            (_c("MÊS", "texto"),) + _ENTREGAS_WEB)},
    "vc_visitas": {
        "Por supervisor": (
            _c("SUPERVISOR", "texto"), _c("REPRES.", "int"))
        + _METRICAS_VISITA_WEB + (_c("CHAVE", "texto", True),),
        "Por vendedor": (
            _c("SUPERVISOR", "texto"), _c("VENDEDOR", "texto"),
            _c("CARGO", "texto", True), _c("FILIAL", "texto", True),
            _c("CÓD.", "texto", True))
        + _METRICAS_VISITA_WEB + (_c("CHAVE", "texto", True),),
        "Dia a dia": (
            _c("DATA", "data"), _c("DIA", "texto"),
            _c("SUPERVISOR", "texto"), _c("VENDEDOR", "texto"),
            _c("CARGO", "texto", True), _c("SITUAÇÃO", "texto"))
        + _METRICAS_VISITA_WEB + (_c("CHAVE", "texto", True),),
        "Cliente a cliente": (
            _c("DATA", "data"), _c("DIA", "texto"),
            _c("SUPERVISOR", "texto"), _c("VENDEDOR", "texto"),
            _c("SITUAÇÃO", "texto"), _c("CÓD.", "texto"),
            _c("CLIENTE", "texto"), _c("NOME FANTASIA", "texto"),
            _c("SEGMENTO", "texto"), _c("BAIRRO", "texto"),
            _c("CIDADE", "texto"), _c("CURVA", "texto"),
            _c("STATUS", "texto"), _c("DIAS S/ COMPRA", "int"),
            _c("ATRASO", "moeda"), _c("SEQ. PREV.", "texto"),
            _c("SEQ. REAL", "texto"), _c("INÍCIO", "hora"),
            _c("FIM", "hora"), _c("ATEND.", "hora"),
            _c("PEDIDO NO DIA", "texto"), _c("VALOR PEDIDO", "moeda"),
            _c("JUSTIFICATIVA", "texto"), _c("ATEND. SEG.", "int", True)),
        "Prospecção": (
            _c("DATA", "data"), _c("HORA", "hora"), _c("DIA", "texto"),
            _c("SUPERVISOR", "texto"), _c("VENDEDOR", "texto"),
            _c("STATUS", "texto"), _c("FONTE", "texto"),
            _c("ESTABELECIMENTO", "texto"), _c("SEGMENTO", "texto"),
            _c("CIDADE", "texto"), _c("UF", "texto"),
            _c("RESULTADO", "texto"), _c("LINHAS DE INTERESSE", "texto"),
            _c("OBSERVAÇÃO", "texto")),
        "Indicação": (
            _c("DATA", "data"), _c("DIA", "texto"),
            _c("SUPERVISOR", "texto"), _c("VENDEDOR", "texto"),
            _c("SITUAÇÃO", "texto"), _c("CÓD. QUEM INDICOU", "texto"),
            _c("CLIENTE QUE INDICOU", "texto"), _c("INDICADO", "texto"),
            _c("CIDADE", "texto"), _c("BAIRRO", "texto"),
            _c("SEGMENTO", "texto"), _c("VISITADA EM", "data"),
            _c("OBSERVAÇÃO", "texto"), _c("REGISTRADO EM", "texto"))}}
# (T-0023 v2, 10.10.2) as colunas dos 3 farois novos, depois do corte (sem o
# CONTATO CLIENTE da garantia e sem o TELEFONE da NCC). (o) = oculta.
_AGRUPA_NCC_WEB = lambda nome: (   # noqa: E731
    _c(nome, "texto"), _c("NCC", "int"), _c("CLIENTES", "int"),
    _c("0-30 DIAS", "moeda"), _c("31-90 DIAS", "moeda"),
    _c("91-180 DIAS", "moeda"), _c("+180 DIAS", "moeda"),
    _c("SALDO", "moeda"), _c("COMPENSAR JÁ", "moeda"))
_COLUNAS_TABELAS_WEB.update({
    "pl_garantias": {
        "Garantias": (
            _c("STATUS", "texto", selo="texto"),
            _c("RESULTADO ANÁLISE", "texto"), _c("TICKET", "texto"),
            _c("DT. SOLICITAÇÃO", "data"), _c("DT. FECHAMENTO", "data"),
            _c("SLA ATUAL", "int", selo="tom"),
            _c("PRAZO", "texto", selo="texto"),
            _c("CÓD. CLIENTE", "texto"), _c("CLIENTE", "texto"),
            _c("CIDADE", "texto"), _c("CÓD. PRODUTO", "texto"),
            _c("DESCRIÇÃO PRODUTO", "texto", True), _c("QTD", "num"),
            _c("PENDÊNCIAS", "texto", True),
            _c("RETORNO DO CLIENTE", "texto", True),
            _c("VENDEDOR", "texto", True), _c("SUPERVISOR", "texto", True),
            _c("SITUAÇÃO DO PRAZO", "texto", True),
            _c("TOM SLA", "texto", True), _c("DT. FECHOU", "data", True),
            _c("RECLAMAÇÃO", "texto", True), _c("OBSERVAÇÃO", "texto", True),
            _c("DT. RETORNO", "data", True)),
        "Histórico de compra": (
            _c("CÓD. CLIENTE", "texto"), _c("RAZÃO SOCIAL", "texto"),
            _c("FANTASIA", "texto"), _c("CIDADE", "texto"),
            _c("PEDIDO", "texto"), _c("PED. MÁXIMA", "texto"),
            _c("NF", "texto"), _c("PRAZO", "texto"), _c("DT. PEDIDO", "dia"),
            _c("DT. NF", "dia"), _c("DT. ENTREGA", "dia"),
            _c("TRANSPORTADORA", "texto"), _c("RESPONSÁVEL", "texto"),
            _c("CÓD. PRODUTO", "texto"), _c("DESCRIÇÃO", "texto"),
            _c("QTD", "num"), _c("VALOR", "moeda"), _c("VENDEDOR", "texto"),
            _c("FILIAL", "texto")),
        "Por produto": (
            _c("CÓD. PRODUTO", "texto"), _c("DESCRIÇÃO", "texto"),
            _c("GARANTIAS", "int"), _c("EM ABERTO", "int"),
            _c("PROCEDENTES", "int"), _c("IMPROCEDENTES", "int")),
        "Status x resultado": (
            _c("STATUS", "texto", selo="texto"), _c("PENDENTE", "int"),
            _c("PROCEDENTE", "int"), _c("IMPROCEDENTE", "int"),
            _c("TOTAL", "int"))},
    "pl_devolucoes": {
        "Devoluções": (
            _c("MÊS", "texto"), _c("DATA", "data"), _c("NF DEV.", "texto"),
            _c("FILIAL", "texto"), _c("CLIENTE", "texto"),
            _c("CIDADE", "texto"), _c("UF", "texto"),
            _c("VENDEDOR", "texto"), _c("VALOR", "moeda"),
            _c("ITENS", "int"), _c("PRODUTOS", "texto"),
            _c("ETAPA", "texto"), _c("MOTIVO", "texto"),
            _c("AUTORIZADO POR", "texto"), _c("RECEBIDA EM", "data"),
            _c("CRÉDITO", "texto"), _c("CRÉDITO EM", "data"),
            _c("RESPONSÁVEL", "texto")),
        "Por motivo": (
            _c("MÊS", "texto"), _c("MOTIVO", "texto"),
            _c("DEVOLUÇÕES", "int"), _c("VALOR", "moeda")),
        "Por vendedor (12 meses)": (
            _c("VENDEDOR", "texto"), _c("DEVOLUÇÕES", "int"),
            _c("VALOR", "moeda"), _c("FATURADO 12M", "moeda"),
            _c("% DEVOLVIDO", "pct")),
        "Por cliente (12 meses)": (
            _c("CLIENTE", "texto"), _c("DEVOLUÇÕES", "int"),
            _c("VALOR", "moeda")),
        "Por produto (12 meses)": (
            _c("PRODUTO", "texto"), _c("DESCRIÇÃO", "texto"),
            _c("QTD", "num"), _c("VALOR", "moeda"))},
    "pl_ncc": {
        "NCC pendentes": (
            _c("A COMPENSAR", "texto"), _c("SLA NCC", "texto", selo="texto"),
            _c("DT. ÚLT. MOV.", "data"), _c("D.U. S/ MOV.", "int"),
            _c("IDADE", "texto"), _c("FILIAL", "texto"), _c("NCC", "texto"),
            _c("PARC.", "texto"), _c("EMISSÃO", "data"), _c("DIAS", "int"),
            _c("CLIENTE", "texto"), _c("NOME", "texto"),
            _c("CIDADE", "texto"), _c("UF", "texto"),
            _c("VENDEDOR", "texto"), _c("SUPERVISOR", "texto", True),
            _c("VALOR NCC", "moeda"), _c("JÁ ABATIDO", "moeda"),
            _c("SALDO", "moeda"), _c("TÍTULOS EM ABERTO", "moeda"),
            _c("PEDIDO EM ABERTO", "moeda"), _c("ÚLTIMA COMPRA", "data")),
        "Por cliente": (
            _c("A COMPENSAR", "texto"), _c("IDADE", "texto"),
            _c("CLIENTE", "texto"), _c("NOME", "texto"),
            _c("CIDADE", "texto"), _c("UF", "texto"),
            _c("VENDEDOR", "texto"), _c("SUPERVISOR", "texto", True),
            _c("NCC", "int"), _c("SALDO", "moeda"),
            _c("NCC MAIS ANTIGA (DIAS)", "int"),
            _c("TÍTULOS EM ABERTO", "moeda"),
            _c("PEDIDO EM ABERTO", "moeda"),
            _c("ÚLTIMA COMPRA", "data")),
        "Por filial": _AGRUPA_NCC_WEB("FILIAL"),
        "Por vendedor": _AGRUPA_NCC_WEB("VENDEDOR"),
        "Por supervisor": _AGRUPA_NCC_WEB("SUPERVISOR")}})
# "Aderência dia a dia": as colunas dos dias mudam com o mes (padrao de nome)
_ADERENCIA_WEB = ("Aderência dia a dia",
                  r"^\d{2}/\d{2} (SEG|TER|QUA|QUI|SEX|SÁB|DOM)$",
                  r"^% ADERÊNCIA ACUM\. ATÉ \d{2}/\d{2}$")
# a junta: titulo da tabela de cima -> [(titulo do quadro no PC, titulo da
# tabela, liga [col_junta, col_tabela, sep])]
_JUNTAS_WEB = {
    ("pv_pedidos", "Pedidos"): (
        ("Gerar ID de separação CD", "Gerar separação CD",
         ("PEDIDOS", "PEDIDO", "|")),
        ("Gerar reversa de lojas", "Gerar reversa de lojas",
         ("PEDIDOS", "PEDIDO", "|")),
        ("Analítico por pedido", "Analítico produto",
         ("PEDIDO", "PEDIDO", None))),
    ("pl_entregas", "Entregas"): (
        ("Pendências dos meses anteriores",
         "Pendências dos meses anteriores", None),)}
# nome de cliente/estabelecimento: "sem_documento" (so o texto) ou
# "cliente_sem_documento" ("codigo - nome": o codigo fica)
_COLUNAS_LIMPAS_WEB = {
    ("pv_pedidos", "Pedidos"): {"RAZÃO SOCIAL": "sem_documento",
                                "FANTASIA": "sem_documento"},
    ("pv_pedidos", "Analítico produto"): {
        "CLIENTE": "cliente_sem_documento"},
    ("pl_entregas", "Entregas"): {"CLIENTE": "cliente_sem_documento"},
    ("pl_entregas", "Pendências dos meses anteriores"): {
        "CLIENTE": "cliente_sem_documento"},
    ("vc_visitas", "Cliente a cliente"): {
        "CLIENTE": "cliente_sem_documento", "NOME FANTASIA": "sem_documento"},
    ("vc_visitas", "Prospecção"): {"ESTABELECIMENTO": "nome_sem_contato"},
    ("vc_visitas", "Indicação"): {"CLIENTE QUE INDICOU": "nome_sem_contato",
                                  "INDICADO": "nome_sem_contato"},
    # (T-0023 v2, 10.10.3) o CLIENTE da garantia e digitado
    ("pl_garantias", "Garantias"): {"CLIENTE": "nome_sem_contato"},
    ("pl_garantias", "Histórico de compra"): {
        "RAZÃO SOCIAL": "sem_documento", "FANTASIA": "sem_documento"},
    ("pl_devolucoes", "Devoluções"): {"CLIENTE": "cliente_sem_documento"},
    ("pl_devolucoes", "Por cliente (12 meses)"): {
        "CLIENTE": "cliente_sem_documento"},
    ("pl_ncc", "NCC pendentes"): {"NOME": "sem_documento"},
    ("pl_ncc", "Por cliente"): {"NOME": "sem_documento"}}
# texto livre (D6 A): telefone, e-mail e CPF/CNPJ viram "[removido]"
_COLUNAS_TEXTO_LIVRE_WEB = frozenset({
    "JUSTIFICATIVA", "OBSERVAÇÃO", "RESULTADO", "LINHAS DE INTERESSE",
    "MOTIVO",
    # (T-0023 v2, 10.10.3) Garantias e Expositores
    "PENDÊNCIAS", "RETORNO DO CLIENTE", "RECLAMAÇÃO", "OBSERVAÇÕES"})
# (T-0023 v2, 10.10.3, RN-GER-011) colunas que nunca vao em UMA tabela (a
# fonte unica da web e `tabelas.FORA_POR_TABELA`): o contato do cliente
_COLUNAS_FORA_TABELA_WEB = {
    ("pl_garantias", "Garantias"): frozenset({"CONTATO CLIENTE"})}
_COLUNAS_LARGAS_SOLICITACAO_WEB = ("ID_PRODUTO", "CHAVE", "MOTIVO", "PEDIDOS")


class _TabelaTortaWeb(Exception):
    """A tabela do PC nao bate com o contrato 10.7.3 (a aba fica fora)."""


def _coluna_proibida_web(nome) -> bool:
    import bap_dados as _bd                             # noqa: PLC0415
    return _bd.sem_acento(nome) in _COLUNAS_FORA_WEB


def _mes_padrao(t):
    """O padrao do filtro MÊS da tabela do PC (ex.: "NOV/26"), ou None."""
    return next((f.get("padrao") for f in (t or {}).get("filtros") or []
                 if isinstance(f, dict) and f.get("coluna") == "MÊS"
                 and f.get("padrao")), None)


def _funcoes_limpeza_web() -> dict:
    """As funcoes puras do nucleo (RN-GER-011). Sem elas, levanta."""
    import relatorios_nucleo as _rn                     # noqa: PLC0415
    funcs = {n: getattr(_rn, n) for n in (
        "sem_documento", "cliente_sem_documento", "texto_sem_contato")}
    # (25/11, revisor) nome digitado pelo vendedor (prospeccao/indicacao)
    # pode trazer telefone ou e-mail: sai o documento E o contato
    funcs["nome_sem_contato"] = lambda v: _rn.texto_sem_contato(
        _rn.sem_documento(v))
    return funcs


def _limpar_celula_web(valor, fn):
    if valor in (None, ""):
        return valor
    return fn(valor)


def _esperado_web(rid: str, titulo: str, nomes: list):
    """As colunas esperadas (nome, tipo, oculta, selo) da tabela depois do
    corte, ou levanta _TabelaTortaWeb."""
    if rid == "vc_visitas" and titulo == _ADERENCIA_WEB[0]:
        import re                                       # noqa: PLC0415
        meio = nomes[2:-1]
        if (len(nomes) < 4 or nomes[:2] != ["SUPERVISOR", "VENDEDOR"]
                or not all(re.match(_ADERENCIA_WEB[1], n) for n in meio)
                or not re.match(_ADERENCIA_WEB[2], nomes[-1])):
            raise _TabelaTortaWeb("colunas")
        return ((_c("SUPERVISOR", "texto"), _c("VENDEDOR", "texto"))
                + tuple(_c(n, "pct", selo="faixa_opc") for n in nomes[2:]))
    esperado = _COLUNAS_TABELAS_WEB.get(rid, {}).get(titulo)
    if esperado is None:
        raise _TabelaTortaWeb("titulo")
    return esperado


def _selo_web(col: dict, selo, nomes_pc: list, ocultas_pc: set) -> dict:
    """O selo da coluna no formato do contrato 10.7.2 (a cor sai do PC).
    Forma diferente da esperada: levanta."""
    saida = {}
    chip, barra, tom = col.get("chip"), col.get("barra"), col.get("chip_tom")
    if selo is None:
        return saida                       # selo fora da lista: nao vai
    if selo == "faixa_opc":                # Aderencia (T-0033, RN-VIS-001)
        if chip is None:
            return saida                   # PC sem a cor: a web usa o tom
        selo = "faixa"
    if selo == "faixa":
        if not (isinstance(chip, (list, tuple)) and chip and all(
                isinstance(f, (list, tuple)) and len(f) == 3 for f in chip)):
            raise _TabelaTortaWeb("selo")
        saida["chip"] = [[f[0], f[1], f[2]] for f in chip]
    elif selo == "texto":
        if not (isinstance(chip, dict) and chip and all(
                isinstance(v, (list, tuple)) and len(v) == 2
                for v in chip.values())):
            raise _TabelaTortaWeb("selo")
        saida["chip"] = {str(k): [v[0], v[1]] for k, v in chip.items()}
    elif selo == "barra":
        if not (isinstance(barra, dict) and "max" in barra
                and isinstance(barra.get("faixas"), (list, tuple))):
            raise _TabelaTortaWeb("selo")
        saida["barra"] = {"max": barra["max"],
                          "faixas": [[f[0], f[1], f[2]]
                                     for f in barra["faixas"]]}
    elif selo == "tom":
        if not (isinstance(tom, int) and not isinstance(tom, bool)
                and 0 <= tom < len(nomes_pc) and nomes_pc[tom] in ocultas_pc):
            raise _TabelaTortaWeb("selo")
        saida["chip_tom"] = nomes_pc[tom]
    return saida


_TIPOS_LIVRES_WEB = frozenset({"texto", "dia", "data", "hora", "int", "num",
                               "num1", "num2", "moeda", "moeda2", "pct",
                               "pct1", "valor"})


def _selo_auto_web(c: dict):
    """(T-0024) a forma do selo que a coluna do PC traz (chip em faixa, chip
    por texto, barra, chip_tom), para os farois livres; None sem selo."""
    if isinstance(c.get("chip"), dict):
        return "texto"
    if isinstance(c.get("chip"), (list, tuple)):
        return "faixa"
    if isinstance(c.get("barra"), dict):
        return "barra"
    if c.get("chip_tom") is not None:
        return "tom"
    return None


def _uf_valida_web(v) -> str:
    v = str(v or "").strip().upper()
    return v if len(v) == 2 and v.isalpha() else ""


_TIPOS_NUM_WEB = frozenset({"int", "num", "num1", "num2", "moeda", "moeda2",
                            "pct", "pct1", "valor"})
_RE_DATA_WEB = re.compile(r"^\d{4}-\d{2}-\d{2}")
# CPF/CNPJ formatado dentro de uma celula: a web recusa o pacote inteiro
_RE_DOC_WEB = re.compile(
    r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")


def _numero_web(v) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and v == v and v not in (float("inf"), float("-inf")))


def _celula_ok_web(v, tipo: str) -> bool:
    """A celula segue o tipo da coluna (contrato 10.7.6; a mesma regra da web)."""
    if v is None:
        return True
    if tipo in _TIPOS_NUM_WEB:
        return _numero_web(v)
    if tipo in ("dia", "data"):
        return isinstance(v, str) and (v == "" or bool(_RE_DATA_WEB.match(v)))
    if tipo == "hora":
        return isinstance(v, str) and len(v) <= 12
    if isinstance(v, str):
        return len(v) <= 2000 and not _RE_DOC_WEB.search(v)
    return _numero_web(v)


def normalizar_total_web(colunas: list, total):
    """Funcao pura (contrato 10.7.2.1): a linha de total do PC, ja cortada
    nas colunas do pacote, no formato da web: "" e None viram None; o rotulo
    (a 1a celula, quando e texto) vai para a 1a coluna visivel de tipo texto
    (ex.: "TOTAL" sai de DATA e vai para DIA); celula com tipo errado para a
    coluna vira None. Sem total: None. O total nunca vai em `linhas`."""
    if not isinstance(total, (list, tuple)) or len(total) != len(colunas):
        return None
    cel = [None if (v is None or v == "" or (isinstance(v, float) and v != v))
           else v for v in total]
    if isinstance(cel[0], str):
        k = next((i for i, c in enumerate(colunas)
                  if c.get("tipo") == "texto" and not c.get("oculta")), None)
        if k is not None and k != 0:
            rotulo, cel[0] = cel[0], None
            cel[k] = rotulo
    saida = []
    for v, c in zip(cel, colunas):
        tp = c.get("tipo")
        if v is not None and tp in ("dia", "data") and not isinstance(v, str):
            v = v.isoformat() if hasattr(v, "isoformat") else None
        elif v is not None and tp == "texto" and _numero_web(v):
            v = str(v)
        saida.append(v if _celula_ok_web(v, tp) else None)
    return saida


def _conferir_tabela_web(t: dict) -> None:
    """A mesma conferencia de celulas da web (R1): linha e total seguem o tipo
    da coluna e nao trazem CPF/CNPJ formatado. Levanta _TabelaTortaWeb (so a
    aba sai)."""
    tipos = [c.get("tipo") for c in t["colunas"]]
    for ln in t["linhas"]:
        if not all(_celula_ok_web(v, tp) for v, tp in zip(ln, tipos)):
            raise _TabelaTortaWeb("celulas")
    if t.get("total") is not None and not (
            len(t["total"]) == len(tipos) and all(
                _celula_ok_web(v, tp) for v, tp in zip(t["total"], tipos))):
        raise _TabelaTortaWeb("total")


# ---------------------------------------------------------------------------
# (T-0021) Edicao na web do Farol de Pedidos (autorizacao) e do Farol de
# Entregas (a linha), so do perfil admin. O PC manda no pacote a especificacao
# (campos, opcoes, coluna da tela e a chave de cada linha); o robo puxa as
# edicoes do site, grava no PC pela MESMA funcao da tela do PC (so acrescenta)
# e confirma. Generico por (rid, tabela, modulo): NCC, Garantias, DDR e
# Expositores entram acrescentando o lugar aqui e na web (edicoes.LUGARES).
_ARQ_POS_VENDA_WEB = "RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx"
EDICOES_WEB = {
    ("pv_pedidos", "Pedidos"): {
        "modulo": "autorizacoes", "arquivo": "RELATORIOS/_AUTORIZACOES",
        "aba": "", "acao": "Autorização"},
    ("pl_entregas", "Entregas"): {
        "modulo": "pos_venda", "arquivo": _ARQ_POS_VENDA_WEB,
        "aba": "ENTREGAS", "acao": "Editar"},
    ("pl_entregas", "Pendências dos meses anteriores"): {
        "modulo": "pos_venda", "arquivo": _ARQ_POS_VENDA_WEB,
        "aba": "ENTREGAS", "acao": "Editar"},
    # (T-0023 v2, 10.9.3) NCC, Devolucoes e Garantias. `pref` = o prefixo das
    # listas fechadas em `opcoes_edicao_web` (o `etapa` da Devolucao nao e o
    # da Entrega); `novo` = aceita linha nova (so a Garantia)
    ("pl_ncc", "NCC pendentes"): {
        "modulo": "ncc", "arquivo": "RELATORIOS/_NCC", "aba": "",
        "acao": "Editar"},
    ("pl_devolucoes", "Devoluções"): {
        "modulo": "pos_venda", "arquivo": _ARQ_POS_VENDA_WEB,
        "aba": "DEVOLUCOES", "acao": "Editar", "pref": "devolucoes"},
    ("pl_garantias", "Garantias"): {
        "modulo": "garantias", "arquivo": "RELATORIOS/_GARANTIAS",
        "aba": "", "acao": "Editar", "novo": True}}
# os campos de cada modulo e o tipo de conferencia no robo: "lista" (lista
# fechada do PC), "data" (dd/mm/aaaa), "data_livre" (uma data do calendario,
# de 01/01/2020 a hoje + 1 ano), "livre" (texto de uma linha), "longo" (texto
# de varias linhas), "ticket" (numero da garantia), "valor" (R$)
CAMPOS_EDICAO_WEB = {
    "autorizacoes": {"codigo": "livre", "por": "lista"},
    "pos_venda": {"etapa": "lista", "transportadora": "lista",
                  "prevista_manual": "data", "entregue_em": "data",
                  "responsavel": "livre", "frete_real": "valor"},
    "ncc": {"status": "lista", "dt_mov": "data_livre"},
}
# (RD-0134) os campos da Garantia vem do nucleo (CAMPOS_EDICAO_GARANTIA): so
# se traduz o tipo do nucleo para o da conferencia do robo
_TIPO_GARANTIA_WEB = {"texto": "livre", "data": "data_livre",
                      "lista": "lista", "longo": "longo"}


def _campos_garantia_web() -> dict:
    import relatorios_nucleo as _rn                     # noqa: PLC0415
    return {campo: ("ticket" if campo == "ticket"
                    else _TIPO_GARANTIA_WEB[tipo])
            for campo, _rot, tipo, _col in _rn.CAMPOS_EDICAO_GARANTIA}
# (T-0023 v2) o modulo `pos_venda` serve a Entrega e a Devolucao, com campos
# diferentes: o que o lugar tem de proprio vale antes do do modulo
CAMPOS_LUGAR_WEB = {
    ("pl_devolucoes", "Devoluções"): {
        "etapa": "lista", "motivo": "lista", "autorizado_por": "livre",
        "recebida_em": "data", "credito": "lista", "credito_em": "data",
        "responsavel": "livre"}}
_RE_CHAVE_EDICAO_WEB = re.compile(r"^[\w .|/-]{1,80}$")
_MAX_OPCOES_EDICAO_WEB = 400
_MAX_CAMPOS_EDICAO_WEB = 16


def campos_do_lugar_web(rid: str, titulo: str) -> dict:
    """{campo: tipo de conferencia} do lugar: o proprio (CAMPOS_LUGAR_WEB) ou
    o do modulo."""
    lugar = EDICOES_WEB[(rid, titulo)]
    if lugar["modulo"] == "garantias":
        return _campos_garantia_web()
    return CAMPOS_LUGAR_WEB.get((rid, titulo)) or CAMPOS_EDICAO_WEB[
        lugar["modulo"]]


def _ops_web(lista) -> list:
    return [str(o) for o in (lista or []) if o not in (None, "")][
        :_MAX_OPCOES_EDICAO_WEB]


def edicao_web(rid: str, titulo: str, ed_pc, linhas: list, pc: list,
               nomes_web: list):
    """Funcao pura (T-0021): a `edicao` do contrato da web para a tabela
    (`linhas` = as linhas do PC que vao, na ordem; `pc` = colunas do PC), ou
    None. O Pedidos usa a edicao da autorizacao do nucleo
    (`_edicao_autorizacao`, a mesma da janela do pedido); o Entregas e as
    Pendencias usam a `edicao` da tabela do PC (`_entrega_editavel`). Se o
    arquivo/aba/modulo do PC nao baterem com EDICOES_WEB, nada vai."""
    lugar = EDICOES_WEB.get((rid, titulo))
    if not lugar:
        return None
    nomes_pc = [c.get("nome") if isinstance(c, dict) else c for c in pc]
    if lugar["modulo"] == "autorizacoes":
        import relatorios_nucleo as _rn                 # noqa: PLC0415
        precisa = ("CHAVE", "CÓD. AUTORIZAÇÃO", "AUTORIZADO POR")
        if not all(n in nomes_pc for n in precisa):
            return None
        ed_pc = _rn._edicao_autorizacao(*[nomes_pc.index(n) for n in precisa])
    if not isinstance(ed_pc, dict) or not isinstance(ed_pc.get("chave"), int):
        return None
    if ((ed_pc.get("modulo") or "pos_venda") != lugar["modulo"]
            or ed_pc.get("arquivo") != lugar["arquivo"]
            or (ed_pc.get("aba") or "") != lugar["aba"]):
        raise ValueError("edicao do PC diferente de EDICOES_WEB")
    i_ch = ed_pc["chave"]
    chaves = []
    for ln in linhas:
        ch = str(ln[i_ch] if len(ln) > i_ch and ln[i_ch] is not None
                 else "").strip()
        chaves.append(ch if _RE_CHAVE_EDICAO_WEB.match(ch) else "")
    permitidos = campos_do_lugar_web(rid, titulo)
    import relatorios_nucleo as _rn2                    # noqa: PLC0415
    campos = []
    for c in ed_pc.get("campos") or []:
        if c.get("campo") not in permitidos:
            continue
        col = c.get("col")
        nome = (nomes_pc[col] if isinstance(col, int) and col < len(nomes_pc)
                else None)
        tipo = ("data" if c.get("data") else "numero" if c.get("numero")
                else "texto" if c.get("livre") else "lista")
        item = {"campo": c["campo"], "rotulo": str(c.get("rotulo") or
                                                    c["campo"])[:60],
                "coluna": nome if nome in nomes_web else None,
                "tipo": tipo, "opcoes": _ops_web(c.get("opcoes"))}
        if permitidos[c["campo"]] == "data_livre" and tipo == "data":
            item["opcoes"] = []            # sem opcoes = data livre (10.9.1)
        if c.get("mantem_caixa"):
            item["caixa"] = True
        if tipo in ("texto", "numero"):
            # o teto vem do nucleo (MAX_TEXTO_EDICAO); o `max` da spec do PC
            # diferente dele = a edicao nao vai (10.9.1)
            teto = _rn2.max_texto_edicao(lugar["modulo"], c["campo"])
            if int(c.get("max") or _rn2.MAX_TEXTO_PADRAO) != teto:
                raise ValueError("max da edicao diferente do nucleo")
            if teto != _rn2.MAX_TEXTO_PADRAO:
                item["max"] = teto
            if c.get("multilinha"):
                item["multilinha"] = True
                item["caixa"] = True
        if isinstance(c.get("padrao"), str) and c["padrao"]:
            item["padrao"] = c["padrao"][:80]
        if callable(c.get("opcoes_de")):
            por = [tuple(_ops_web(c["opcoes_de"](ln))) for ln in linhas]
            if tipo == "lista":
                grupos, ix = [], {}
                for p_ in por:
                    if p_ not in ix:
                        ix[p_] = len(grupos)
                        grupos.append(list(p_))
                item["grupos"] = grupos
                item["grupo_linhas"] = [ix[p_] for p_ in por]
            else:                       # a lista so sugere (VLR FRETE 5%)
                item["sugestoes_linhas"] = [p_[0][:40] if p_ else ""
                                            for p_ in por]
        if callable(c.get("so_se")):
            item["linhas"] = [j for j, ln in enumerate(linhas)
                              if c["so_se"](ln)]
        campos.append(item)
    if not campos:
        return None
    saida = {"modulo": lugar["modulo"], "acao": lugar["acao"],
             "chaves": chaves, "campos": campos[:_MAX_CAMPOS_EDICAO_WEB]}
    nv = ed_pc.get("novo_web")      # a linha nova (so onde o lugar aceita)
    if lugar.get("novo") and isinstance(nv, dict) and isinstance(
            nv.get("rotulo"), str) and 1 <= len(nv["rotulo"]) <= 30:
        saida["novo"] = {"rotulo": nv["rotulo"]}
    return saida


def tabela_web7(rid: str, t: dict, mes_rot=None, _junta: bool = False,
                _edicao=None):
    """Funcao pura (T-0017, contrato 10.7): a tabela do PC (depois do
    `montar`) no formato TabelaWeb7, ou None se as colunas nao baterem com a
    lista do contrato 10.7.3 (so essa aba fica fora; a linha do log nao tem
    dado pessoal).

    - corta as colunas que nunca vao (_COLUNAS_FORA_WEB) e a celula a mais
      da linha (a chave da entrega);
    - D2 A: em "Pedidos" e "Entregas" so as linhas do mes (`mes_rot`, padrao
      = o filtro MÊS da tabela);
    - limpa nome de cliente (sem_documento / cliente_sem_documento) e texto
      livre (texto_sem_contato) do nucleo;
    - `kpis_padrao`, `recortes_linhas` e `uf_linhas` saem das linhas
      ORIGINAIS do PC e so depois sao remapeados para as linhas do mes.
    A tabela de junta (`_junta`) nao leva kpis_padrao.
    (T-0021) `_edicao`: a edicao do PC da tabela de cima, para a junta que
    edita como ela (Pendencias dos meses anteriores)."""
    titulo = (t or {}).get("titulo")
    try:
        return _tabela_web7(rid, t, mes_rot, _junta, _edicao)
    except _TabelaTortaWeb as erro:
        log.warning("Pacote web: tabela '%s' do farol %s fora do pacote (%s "
                    "nao batem com o contrato 10.7.3).", titulo, rid, erro)
        return None
    except Exception as erro:                           # noqa: BLE001
        log.warning("Pacote web: tabela '%s' do farol %s fora do pacote "
                    "(%s).", titulo, rid, type(erro).__name__)
        return None


def _tabela_web7(rid, t, mes_rot, junta, ed_mae=None):
    import relatorios_nucleo as _rn                     # noqa: PLC0415
    titulo = t.get("titulo")
    pc = [c if isinstance(c, dict) else {"nome": c, "tipo": "texto"}
          for c in t.get("colunas") or []]
    nomes_pc = [c.get("nome") for c in pc]
    livre = rid in RIDS_LIVRES_WEB
    fora_tab = _COLUNAS_FORA_TABELA_WEB.get((rid, titulo), ())
    idx = [i for i, n in enumerate(nomes_pc) if not _coluna_proibida_web(n)
           and n not in fora_tab
           and not (livre and (str(n).startswith("_")
                               or n in _COLUNAS_FORA_LIVRES_WEB))]
    atuais = [(pc[i]["nome"], pc[i].get("tipo"), bool(pc[i].get("oculta")))
              for i in idx]
    ocultas_pc = {c["nome"] for c in pc if c.get("oculta")}
    if livre:       # T-0024: as colunas sao as do PC (menos as que nao vao)
        if not atuais or any(tp not in _TIPOS_LIVRES_WEB
                             for _n, tp, _o in atuais):
            raise _TabelaTortaWeb("colunas")
        esperado = [(n, tp, o, _selo_auto_web(pc[i])) for i, (n, tp, o)
                    in zip(idx, atuais)]
        nomes_ficam = {a[0] for a in atuais}
        ocultas_pc = {n for n in ocultas_pc if n in nomes_ficam}
    else:
        esperado = _esperado_web(rid, titulo, [a[0] for a in atuais])
        if atuais != [(n, tp, o) for n, tp, o, _s in esperado]:
            raise _TabelaTortaWeb("colunas")
    colunas = []
    for i, (_n, _tp, _o, selo) in zip(idx, esperado):
        c = pc[i]
        col = {"nome": c["nome"], "tipo": c["tipo"]}
        if c.get("largura") is not None:
            col["largura"] = int(c["largura"])
        if c.get("larg_fixa") is not None:
            col["larg_fixa"] = int(c["larg_fixa"])
        if c.get("oculta"):
            col["oculta"] = True
        if c.get("inteira"):
            col["inteira"] = True
        if livre:
            try:
                col.update(_selo_web(c, selo, nomes_pc, ocultas_pc))
            except _TabelaTortaWeb:     # selo torto: a coluna vai sem selo
                pass
        else:
            col.update(_selo_web(c, selo, nomes_pc, ocultas_pc))
        colunas.append(col)
    nomes = [c["nome"] for c in colunas]
    brutas = t.get("linhas") or []
    for ln in brutas:
        if len(ln) < len(pc):
            raise _TabelaTortaWeb("linhas")
    # indices ORIGINAIS: filtros padrao, recortes, UF (antes de cortar/limpar)
    tons_pc = [str(x or "") for x in t.get("tons") or []]
    if len(tons_pc) != len(brutas):
        tons_pc = [""] * len(brutas)
    manter = list(range(len(brutas)))
    if titulo in _TABELAS_SO_MES_WEB and "MÊS" in nomes_pc:
        ix_mes = nomes_pc.index("MÊS")
        mes_rot = mes_rot or _mes_padrao(t)
        if not mes_rot:
            raise _TabelaTortaWeb("mes")
        manter = [k for k in manter
                  if str(brutas[k][ix_mes]) == str(mes_rot)]
    novo = {k: j for j, k in enumerate(manter)}
    saida = {"titulo": titulo, "colunas": colunas}
    funcs = _funcoes_limpeza_web()
    limpas = {n: funcs[f] for n, f in _COLUNAS_LIMPAS_WEB.get(
        (rid, titulo), {}).items()}
    for n in nomes:
        if n in _COLUNAS_TEXTO_LIVRE_WEB:
            limpas[n] = funcs["texto_sem_contato"]
    if livre:       # T-0024: nome de cliente limpo de documento (RN-GER-011)
        for n in nomes:
            if n == "CLIENTE":
                limpas[n] = funcs["cliente_sem_documento"]
            elif n in ("NOME", "FANTASIA", "NOME FANTASIA", "RAZÃO SOCIAL"):
                limpas[n] = funcs["sem_documento"]
    pos_limpa = [(nomes.index(n), fn) for n, fn in limpas.items()
                 if n in nomes]
    linhas = []
    for k in manter:
        ln = [brutas[k][i] for i in idx]
        for j, fn in pos_limpa:
            ln[j] = _limpar_celula_web(ln[j], fn)
        linhas.append(ln)
    saida["linhas"] = linhas
    saida["tons"] = [tons_pc[k] for k in manter]
    total = t.get("total")
    saida["total"] = normalizar_total_web(
        colunas, [total[i] for i in idx]
        if isinstance(total, (list, tuple)) and len(total) == len(pc)
        else None)
    saida["filtros"] = []
    for f in t.get("filtros") or []:
        if (f.get("coluna") if isinstance(f, dict) else f) not in nomes:
            continue
        if (titulo in _TABELAS_SO_MES_WEB and isinstance(f, dict)
                and f.get("coluna") == "MÊS"):
            f = dict(f, oculto=True)      # o pacote so tem o mes: sem caixa
        saida["filtros"].append(f)
    if t.get("zebra"):
        saida["zebra"] = True
    kpis_de = t.get("kpis_de")
    kpis_padrao = None
    if callable(kpis_de) and not junta:
        try:
            padrao = _rn.linhas_padrao(t)
            ks = _rn.chamar_kpis_de(kpis_de, [brutas[k] for k in padrao])
        except Exception as erro:                       # noqa: BLE001
            log.warning("Pacote web: cartoes da aba '%s' do farol %s fora "
                        "(%s).", titulo, rid, type(erro).__name__)
            ks = None
        if ks:      # o cartao inteiro, com o `detalhe` do Kpi (achado 12)
            kpis_padrao = _para_json(
                ks, fora=_CHAVES_FORA_TABELA_WEB - {"detalhe"})
    rec = []
    for r in _rn.recortes_em_linhas(t):
        rec.append({"rotulo": r["rotulo"],
                    "linhas": [novo[k] for k in r["linhas"] if k in novo]})
    if rec:
        saida["recortes_linhas"] = rec
    uf_cfg = _UF_LINHAS_WEB.get((rid, titulo))
    if uf_cfg and uf_cfg[0] in nomes_pc:
        ix = nomes_pc.index(uf_cfg[0])
        conv = _rn.uf_do_nome_da_filial if uf_cfg[1] == "filial" \
            else _uf_valida_web
        saida["uf_linhas"] = [_uf_valida_web(conv(brutas[k][ix]))
                              for k in manter]
    val = _para_json(saida, fora=_CHAVES_FORA_TABELA_WEB)
    if not isinstance(val, dict):
        raise _TabelaTortaWeb("tabela")
    # o _para_json tira celula que nao e JSON: o numero de celulas nao muda
    if (len(val.get("colunas", [])) != len(colunas)
            or len(val.get("linhas", [])) != len(linhas)
            or any(len(a) != len(colunas) for a in val["linhas"])):
        raise _TabelaTortaWeb("linhas")
    if kpis_padrao:
        val["kpis_padrao"] = kpis_padrao
    _conferir_tabela_web(val)         # a mesma conferencia da web (R1)
    if (rid, titulo) in EDICOES_WEB:  # (T-0021) so a especificacao; falhou = sem
        try:
            ed = edicao_web(rid, titulo, ed_mae if junta else t.get("edicao"),
                            [brutas[k] for k in manter], pc, nomes)
        except Exception as erro:                       # noqa: BLE001
            log.warning("Pacote web: edicao da tabela '%s' do farol %s fora "
                        "(%s).", titulo, rid, type(erro).__name__)
            ed = None
        if ed:
            val["edicao"] = ed
    return val


def _celula_solicitacao_web(v, tipo: str):
    """Celula da Solicitacao BAP em JSON: data/hora viram texto, numero em
    coluna de texto vira texto (como a tela mostra)."""
    from datetime import time as _time                  # noqa: PLC0415
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, datetime):
        return (v.date().isoformat() if tipo == "data"
                else (v.strftime("%d/%m/%Y") if not (v.hour or v.minute)
                      else v.strftime("%d/%m/%Y %H:%M")))
    if isinstance(v, date):
        return v.isoformat() if tipo == "data" else v.strftime("%d/%m/%Y")
    if isinstance(v, _time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return None
        if tipo == "texto":
            return str(int(v)) if v.is_integer() else str(v)
        return v
    if isinstance(v, int):
        return str(v) if tipo == "texto" else v
    return v if isinstance(v, str) else str(v)


def solicitacao_web(raiz):
    """(T-0017, contrato 10.7.3) A aba "Solicitação BAP" (TabelaWeb7 com 7
    `subabas`) a partir de RELATORIOS/SOLICITACAO_BAP.xlsx
    (solicitacao_bap.ler), as linhas inteiras (D3 A; a trava de tamanho corta
    depois). Sem as colunas que nunca vao; CLIENTE sem documento; MOTIVO sem
    contato. A troca de loja de coleta (grava) fica no PC. Sem o arquivo ou
    sem aba: None."""
    import solicitacao_bap as _sb                       # noqa: PLC0415
    dados = _sb.ler(raiz)
    if not dados:
        return None
    funcs = _funcoes_limpeza_web()
    subabas = []
    for aba in _sb.ABAS_TELA:
        d = dados.get(aba)
        if not d:
            continue
        cols = list(d["colunas"])
        tipos = _sb.tipos_colunas(cols, d["linhas"])
        idx = [i for i, c in enumerate(cols)
               if c and not _coluna_proibida_web(c)]
        colunas = [{"nome": cols[i], "tipo": tipos[i],
                    "largura": 170 if cols[i] in
                    _COLUNAS_LARGAS_SOLICITACAO_WEB else 90} for i in idx]
        limpas = [(j, funcs["cliente_sem_documento"] if cols[i] == "CLIENTE"
                   else funcs["texto_sem_contato"])
                  for j, i in enumerate(idx)
                  if cols[i] == "CLIENTE"
                  or cols[i] in _COLUNAS_TEXTO_LIVRE_WEB]
        linhas = []
        for ln in d["linhas"]:
            nova = [_celula_solicitacao_web(ln[i] if i < len(ln) else None,
                                            tipos[i]) for i in idx]
            for j, fn in limpas:
                nova[j] = _limpar_celula_web(nova[j], fn)
            if not all(_celula_ok_web(v, "texto") for v in nova):
                raise _TabelaTortaWeb("celulas")
            linhas.append(nova)
        subabas.append({"titulo": aba, "colunas": colunas, "linhas": linhas,
                        "tons": [""] * len(linhas)})
    if not subabas:
        return None
    val = _para_json({"titulo": TITULO_SOLICITACAO_WEB, "colunas": [],
                      "linhas": [], "tons": [], "total": None,
                      "filtros": [], "subabas": subabas},
                     fora=_CHAVES_FORA_TABELA_WEB)
    for sa in (val or {}).get("subabas", []):
        if any(len(a) != len(sa["colunas"]) for a in sa["linhas"]):
            raise _TabelaTortaWeb("linhas")
    return val


def _junta_web7(rid, titulo_mae, pc_juntas, mes_rot, ed_mae=None):
    """As juntas da tabela de cima no formato do contrato, ou None se uma
    junta faltar, estiver com outra `liga` ou torta."""
    saida = []
    for quadro, titulo_tab, liga in _JUNTAS_WEB.get((rid, titulo_mae), ()):
        j = next((x for x in pc_juntas or [] if isinstance(x, dict)
                  and x.get("titulo") == quadro), None)
        if j is None or not isinstance(j.get("tabela"), dict):
            return None
        pc_liga = j.get("liga")
        if (tuple(pc_liga) if pc_liga else None) != liga:
            return None
        tab = tabela_web7(rid, j["tabela"], mes_rot, _junta=True,
                          _edicao=ed_mae if j.get("editavel") else None)
        if tab is None or tab.get("titulo") != titulo_tab:
            return None
        nomes = [c["nome"] for c in tab["colunas"]]
        item = {"titulo": quadro, "liga": list(liga) if liga else None,
                "tabela": tab}
        mostrar = [n for n in j.get("mostrar") or [] if n in nomes]
        if mostrar:
            item["mostrar"] = mostrar
        saida.append(item)
    return saida


def tabelas_farol_web(rid: str, r: dict, raiz=None):
    """Funcao (T-0017, contrato 10.7): (lista de TabelaWeb7, avisos) das abas
    de tabela do farol, na ordem do contrato 10.7.1. Cada aba e independente:
    a que nao bater com o contrato fica fora, com aviso no farol e uma linha
    de log sem dado pessoal; as outras seguem. O Pedidos leva as 3 juntas, o
    Entregas leva a das pendencias, e o Pedidos leva a Solicitacao BAP."""
    recusadas, saida = [], []
    por_titulo = {t.get("titulo"): t for t in (r or {}).get("tabelas") or []
                  if isinstance(t, dict)}

    def fora(titulo):
        recusadas.append(titulo)
    for titulo in (list(por_titulo) if rid in RIDS_LIVRES_WEB
                   else _ABAS_TABELAS_WEB.get(rid, ())):
        if titulo == TITULO_SOLICITACAO_WEB:
            try:
                tab = solicitacao_web(raiz or PASTA_LOCAL)
            except Exception as erro:                   # noqa: BLE001
                log.warning("Pacote web: Solicitacao BAP fora do pacote "
                            "(%s).", type(erro).__name__)
                fora(titulo)
                continue
            if tab:
                saida.append(tab)
            continue
        t = por_titulo.get(titulo)
        if not t:                    # aba que nao existe no farol: sem aviso
            continue
        tab = tabela_web7(rid, t)
        if tab is not None and (rid, titulo) in _JUNTAS_WEB:
            juntas = _junta_web7(rid, titulo, t.get("juntas"),
                                 _mes_padrao(t), t.get("edicao"))
            if juntas is None:
                tab = None
            else:
                tab["juntas"] = juntas
        if tab is None:
            fora(titulo)
            continue
        saida.append(tab)
    avisos = []
    if recusadas:         # um aviso so (teto de 2 avisos no celular)
        log.warning("Pacote web: abas fora do pacote no farol %s: %s.", rid,
                    ", ".join(recusadas))
        avisos.append(AVISO_ABAS_FORA.format(lista=", ".join(recusadas)))
    return saida, avisos


def _limitar_anexos_web(rid: str, farol: dict) -> tuple:
    """Funcao pura (T-0035, 10.8.7): aplica no robo os tetos de anexo da web.
    Parcial acima de MAX_PNG_B64 sai (so ela); csvs_protheus fora do teto
    (quantidade, bytes de um, soma) sai inteiro. Devolve (farol, avisos); sem
    nada a tirar devolve o proprio `farol` e []. O de entrada nao muda."""
    avisos, novo = [], None
    parc = farol.get("parciais")
    if isinstance(parc, dict):
        ok = {q: v for q, v in parc.items() if not (
            isinstance(v, dict) and isinstance(v.get("png"), str)
            and len(v["png"]) > MAX_PNG_B64)}
        if len(ok) != len(parc):
            novo = dict(farol)
            if ok:
                novo["parciais"] = ok
            else:
                novo.pop("parciais")
            avisos.append(AVISO_PARCIAIS_FORA)
    csvs = farol.get("csvs_protheus")
    if isinstance(csvs, list):
        tams = [len(str((c or {}).get("conteudo", "")).encode("utf-8"))
                for c in csvs]
        if (len(csvs) > MAX_CSVS_WEB
                or any(n > MAX_CSV_BYTES_WEB for n in tams)
                or sum(tams) > MAX_CSVS_TOTAL):
            novo = novo if novo is not None else dict(farol)
            novo.pop("csvs_protheus", None)
            avisos.append(AVISO_CSVS_FORA)
    if novo is None:
        return farol, []
    for _a in avisos:
        log.warning("Pacote web: %s (farol %s).", _a, rid)
    av = list(novo.get("avisos") or []) + avisos
    novo["avisos"] = (_avisos_curtos_visita_web(av) if rid == "vc_visitas"
                      else _ordenar_avisos_web(av))
    return novo, avisos


def _avisar_web(rid: str, rel: dict, texto: str) -> None:
    """Acrescenta o aviso ao farol `rel` (muda `rel`), na ordem do 10.7.6."""
    log.warning("Pacote web: %s (farol %s).", texto, rid)
    av = rel.setdefault("avisos", [])
    av.append(texto)
    rel["avisos"] = (_avisos_curtos_visita_web(av) if rid == "vc_visitas"
                     else _ordenar_avisos_web(av))


def _abas_fora_web(rid: str, rel: dict, titulos) -> None:
    """Junta os titulos no aviso unico de abas fora (contrato 10.7.6)."""
    pre, pos = AVISO_ABAS_FORA.split("{lista}")
    av = rel.setdefault("avisos", [])
    antes = []
    for a in list(av):
        if str(a).startswith(pre):
            antes = [x for x in str(a)[len(pre):-len(pos)].split(", ") if x]
            av.remove(a)
    ordem = _ABAS_TABELAS_WEB.get(rid, ())
    todos = antes + [x for x in titulos if x not in antes]
    todos.sort(key=lambda x: ordem.index(x) if x in ordem else 99)
    _avisar_web(rid, rel, AVISO_ABAS_FORA.format(lista=", ".join(todos)))


def _corte_solicitacao_web(rid: str, rel: dict) -> None:
    """Muda `rel` (ja copia): a Solicitacao BAP so com pedidos EM ABERTO."""
    if rid not in RIDS_TABELAS_WEB:
        return
    for t in rel.get("tabelas") or []:
        if t.get("titulo") != TITULO_SOLICITACAO_WEB:
            continue
        for sa in t.get("subabas") or []:
            nomes = [c["nome"] for c in sa["colunas"]]
            if "SITUACAO_PEDIDO" not in nomes:
                continue            # as listas de exclusao vao inteiras
            i = nomes.index("SITUACAO_PEDIDO")
            sa["linhas"] = [ln for ln in sa["linhas"]
                            if str(ln[i]).strip().upper() == "EM ABERTO"]
            sa["tons"] = [""] * len(sa["linhas"])
        _avisar_web(rid, rel, AVISO_SOLICITACAO_ABERTO)


def _corte_cliente_a_cliente_web(rid: str, rel: dict) -> None:
    tabs = rel.get("tabelas")
    if tabs and any(t.get("titulo") == "Cliente a cliente" for t in tabs):
        rel["tabelas"] = [t for t in tabs
                          if t.get("titulo") != "Cliente a cliente"]
        _abas_fora_web(rid, rel, ["Cliente a cliente"])


def _corte_historico_web(rid: str, rel: dict) -> None:
    """(T-0023 v2, 10.10.4) Garantias: o "Historico de compra" (a maior parte
    do farol) sai primeiro, com o aviso das abas fora."""
    tabs = rel.get("tabelas")
    if tabs and any(t.get("titulo") == "Histórico de compra" for t in tabs):
        rel["tabelas"] = [t for t in tabs
                          if t.get("titulo") != "Histórico de compra"]
        _abas_fora_web(rid, rel, ["Histórico de compra"])


def _corte_tabelas_web(rid: str, rel: dict) -> None:
    if rel.get("tabelas"):
        _abas_fora_web(rid, rel, [t.get("titulo") for t in rel.pop("tabelas")])


def _corte_junta_entregas_web(rid: str, rel: dict) -> None:
    """Entregas: tira as juntas (as pendencias dos meses anteriores)."""
    achou = False
    for t in rel.get("tabelas") or []:
        if t.get("titulo") == "Entregas" and t.get("juntas"):
            t.pop("juntas")
            achou = True
    if achou:
        _avisar_web(rid, rel, AVISO_JUNTA_ENTREGAS)


def _data_linha_web(ln, ix_ped, ix_nf) -> str:
    """Chave de recencia da entrega: DT. PED, senao DT. NF ('' = a mais antiga)."""
    for ix in (ix_ped, ix_nf):
        if ix is not None and ix < len(ln) and isinstance(ln[ix], str) \
                and ln[ix]:
            return ln[ix]
    return ""


def _reindexar_linhas_web(t: dict, orig: dict, ficam: list) -> None:
    """Muda `t`: fica so com as linhas `ficam` (indices da `orig`, ja em ordem
    original) e refaz tudo que depende do indice da linha: tons, uf_linhas,
    recortes_linhas e a edicao (chaves, grupo_linhas, sugestoes_linhas,
    linhas dos campos). A web recusa a tabela se algum deles nao bater."""
    import copy                                         # noqa: PLC0415
    novo = {k: j for j, k in enumerate(ficam)}
    t["linhas"] = [orig["linhas"][k] for k in ficam]
    for chave in ("tons", "uf_linhas"):
        if isinstance(orig.get(chave), list):
            t[chave] = [orig[chave][k] for k in ficam]
    if isinstance(orig.get("recortes_linhas"), list):
        t["recortes_linhas"] = [
            dict(r, linhas=[novo[k] for k in r.get("linhas", []) if k in novo])
            for r in orig["recortes_linhas"]]
    ed = orig.get("edicao")
    if isinstance(ed, dict):
        ed = copy.deepcopy(ed)
        ed["chaves"] = [ed["chaves"][k] for k in ficam]
        for c in ed.get("campos") or []:
            for chave in ("grupo_linhas", "sugestoes_linhas"):
                if isinstance(c.get(chave), list):
                    c[chave] = [c[chave][k] for k in ficam]
            if isinstance(c.get("linhas"), list):
                c["linhas"] = [novo[k] for k in c["linhas"] if k in novo]
        t["edicao"] = ed


def _corte_linhas_entregas_web(rid: str, rel: dict, cabe) -> None:
    """Entregas: mantem so as linhas mais recentes (DT. PED), em fatias de
    _FRACOES_ENTREGAS_WEB, ate `cabe(rel)`. Tira `tons` junto. Se nem a menor
    fatia couber, devolve a aba na menor fatia (o corte seguinte tira a aba)."""
    import copy                                         # noqa: PLC0415
    for t in rel.get("tabelas") or []:
        if t.get("titulo") != "Entregas" or not t.get("linhas"):
            continue
        nomes = [c["nome"] for c in t["colunas"]]
        ix_ped = nomes.index("DT. PED") if "DT. PED" in nomes else None
        ix_nf = nomes.index("DT. NF") if "DT. NF" in nomes else None
        chave = [_data_linha_web(ln, ix_ped, ix_nf) for ln in t["linhas"]]
        ordem = sorted(range(len(chave)), key=lambda k: chave[k],
                       reverse=True)                # mais novas primeiro
        total, cortou = len(ordem), False
        orig = copy.deepcopy(t)                     # sempre refaz do inteiro
        for fr in _FRACOES_ENTREGAS_WEB:
            n = max(1, int(total * fr))
            if n >= total:
                continue
            _reindexar_linhas_web(t, orig, sorted(ordem[:n]))
            cortou = True
            if cabe(rel):
                break
        if cortou:
            _avisar_web(rid, rel, AVISO_ENTREGAS_RECENTES)
        return


def _tamanho_pacote_web(pacote: dict) -> int:
    return len(json.dumps(pacote, ensure_ascii=False).encode("utf-8"))


def _cortar_pacote_web(pacote: dict, teto_mb=None) -> dict:
    """Funcao pura (T-0017, contrato 10.7.8): se o pacote serializado passar
    de `teto_mb` (WEB_PACOTE_TETO_MB), corta nesta ordem, ate caber, com um
    aviso no farol e uma linha no log: (0) as imagens das parciais (T-0026)
    fora, primeiro (pesam mais e o PC as tem); (1) "Solicitação BAP" so com as linhas
    de pedido EM ABERTO (ProdutosExcluir e FiliaisExcluir vao inteiras);
    (2) "Cliente a cliente" fora; (3) todas as `tabelas` dos tres farois
    fora (o farol cai no 10.1). Nunca muda a `tabelas` do pl_inadimplencia.
    Devolve outro dicionario; o de entrada nao muda."""
    import copy                                         # noqa: PLC0415
    limite = int((teto_mb if teto_mb is not None
                  else WEB_PACOTE_TETO_MB) * 1024 * 1024)
    # (T-0035, 10.8.7) anexo acima do teto da web sai ja, mesmo com o pacote
    # pequeno: senao a web recusa o pacote inteiro
    rels0 = pacote.get("relatorios") or {}
    limpos = {rid: _limitar_anexos_web(rid, f)[0] if isinstance(f, dict)
              else f for rid, f in rels0.items()}
    if any(limpos[r] is not rels0[r] for r in rels0):
        pacote = dict(pacote, relatorios=limpos)
    if _tamanho_pacote_web(pacote) <= limite:
        return pacote
    novo = copy.deepcopy(pacote)
    rels = novo.get("relatorios") or {}

    def passo0():               # T-0026: primeiro, as imagens das parciais
        for rid in rels:
            if rels[rid].pop("parciais", None):
                _avisar_web(rid, rels[rid], AVISO_PARCIAIS_FORA)

    def passo1():
        for rid in RIDS_TABELAS_WEB:
            if rid in rels:
                _corte_solicitacao_web(rid, rels[rid])

    def passo2():
        for rid in RIDS_TABELAS_WEB:
            if rid in rels:
                _corte_cliente_a_cliente_web(rid, rels[rid])

    def passo3():
        for rid in RIDS_TABELAS_WEB:
            if rid in rels:
                _corte_tabelas_web(rid, rels[rid])
    for passo in (passo0, passo1, passo2, passo3):
        passo()
        if _tamanho_pacote_web(novo) <= limite:
            break
    else:
        log.warning("Pacote web: continua acima do teto de %s MB depois dos "
                    "4 cortes.", teto_mb if teto_mb is not None
                    else WEB_PACOTE_TETO_MB)
    return novo


def _json_farol_web(farol: dict) -> bytes:
    """Os bytes do farol como vao no corpo (10.8.3)."""
    return json.dumps(farol, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _cortar_farol_web(rid: str, farol: dict, teto_mb=None) -> dict:
    """Funcao pura (T-0035, contrato 10.8.7): primeiro os anexos acima dos
    tetos da web saem, so eles, com aviso (_limitar_anexos_web). Depois, se o
    JSON do farol SEM os anexos (parciais e csvs_protheus) passar de `teto_mb`
    (WEB_FAROL_TETO_MB), corta na ordem de _CORTES_FAROL_WEB[rid] ate caber;
    o ultimo corte tira as `tabelas` (o farol cai no 10.1), com o
    AVISO_ABAS_FORA. Os anexos que cabem nao entram na conta nem sao tocados.
    Devolve outro dicionario; o de entrada nao muda."""
    import copy                                         # noqa: PLC0415
    mb = teto_mb if teto_mb is not None else WEB_FAROL_TETO_MB
    limite = int(mb * 1024 * 1024)
    farol, _ = _limitar_anexos_web(rid, farol)

    def tam(f):
        return len(_json_farol_web({k: v for k, v in f.items()
                                    if k not in _ANEXOS_FAROL_WEB}))
    if tam(farol) <= limite:
        return farol
    anexos = {k: farol[k] for k in _ANEXOS_FAROL_WEB if k in farol}
    out = copy.deepcopy({k: v for k, v in farol.items()
                         if k not in _ANEXOS_FAROL_WEB})
    cortes = {"solicitacao_so_em_aberto": _corte_solicitacao_web,
              "cliente_a_cliente_fora": _corte_cliente_a_cliente_web,
              "junta_pendencias_fora": _corte_junta_entregas_web,
              "historico_fora": _corte_historico_web,
              "tabelas": _corte_tabelas_web}
    for nome in _CORTES_FAROL_WEB.get(rid, ("tabelas",)):
        if nome == "entregas_so_recentes":
            _corte_linhas_entregas_web(rid, out, lambda f: tam(f) <= limite)
        else:
            cortes[nome](rid, out)
        if tam(out) <= limite:
            break
    else:
        log.warning("Pacote web: o farol %s continua acima do teto de %s MB "
                    "depois dos cortes.", rid, mb)
    out.update(anexos)
    return out


def _recortes_do_farol_web(rid: str, r: dict) -> dict:
    """Recortes por estado do rid, pela regra da RN-GER-006 (filial da nota no
    faturamento; UF do cliente em fretes/Planner), com a coluna e a conversao
    de _UF_LINHAS_WEB. Sem a UF do cliente (Visita): {}. No Entregas o
    cartao e calculado como o PC: kpis_de(linhas da UF, filtro={coluna UF: UF}),
    e "Pendências anteriores" entra no recorte (RD-0019)."""
    titulo = _TABELA_RECORTE_WEB.get(rid)
    cfg = _UF_LINHAS_WEB.get((rid, titulo))
    if not cfg:
        return {}
    col, modo = cfg
    if modo == "uf":
        return recortes_farol_por_uf(r, titulo, coluna_filial=col,
                                     uf_de=_uf_valida_web, filtro_uf=True)
    return recortes_farol_por_uf(r, titulo, coluna_filial=col)


def recortes_farol_por_uf(r: dict, titulo_tabela: str = "Títulos",
                          coluna_filial: str = "FILIAL", uf_de=None,
                          filtro_uf: bool = False) -> dict:
    """Funcao pura (T-0017, RN-GER-006: estado = filial da nota): os cartoes
    do farol por estado, prontos. Chama o kpis_de da tabela com as linhas
    daquela filial, como o filtro da tela do PC. Sem kpis_de, sem a tabela
    ou sem a coluna: {}. Com filtro padrao MES na tabela (Pedidos, Entregas), so
    as linhas desse mes (o mesmo escopo dos cartoes do topo). Filial que nao e de um estado conhecido fica fora
    (o total do farol segue inteiro em "kpis"). uf_de: nome/codigo da filial
    -> UF (padrao: relatorios_nucleo.uf_do_nome_da_filial). filtro_uf: chama
    relatorios_nucleo.chamar_kpis_de(kpis_de, linhas, filtro={indice da
    coluna: UF}), como o filtro de UF da tela (Entregas).
    Devolve {"<UF>": {"kpis": [...]}}."""
    tab = next((t for t in (r or {}).get("tabelas") or []
                if isinstance(t, dict) and t.get("titulo") == titulo_tabela),
               None)
    kpis_de = (tab or {}).get("kpis_de")
    if not callable(kpis_de):
        return {}
    nomes = [c.get("nome") if isinstance(c, dict) else c
             for c in tab.get("colunas") or []]
    if coluna_filial not in nomes:
        return {}
    ix = nomes.index(coluna_filial)
    if uf_de is None:
        import relatorios_nucleo as _rn                 # noqa: PLC0415
        uf_de = _rn.uf_do_nome_da_filial
    # o recorte parte do MESMO escopo dos cartoes do topo: o filtro padrao MES
    # da tabela (Pedidos e Entregas abrem no mes); os outros padroes sao so
    # visao da tela (ex.: SITUACAO = EM ABERTO) e nao entram no farol
    mes_val = _mes_padrao(tab)
    mes_ix = nomes.index("MÊS") if mes_val and "MÊS" in nomes else None
    por_uf = {}
    for ln in tab.get("linhas") or []:
        if mes_ix is not None and (len(ln) <= mes_ix
                                   or str(ln[mes_ix]) != str(mes_val)):
            continue
        try:
            uf = uf_de(ln[ix])
        except Exception:                               # noqa: BLE001
            uf = ""
        if uf:
            por_uf.setdefault(uf, []).append(ln)
    if filtro_uf:     # RN-GER-006: o estado so com pendencia de mes anterior
        for j in tab.get("juntas") or []:       # tambem aparece (como no PC)
            tj = j.get("tabela") if isinstance(j, dict) else None
            nj = [c.get("nome") if isinstance(c, dict) else c
                  for c in (tj or {}).get("colunas") or []]
            if coluna_filial not in nj:
                continue
            ij = nj.index(coluna_filial)
            for ln in tj.get("linhas") or []:
                try:
                    uf = uf_de(ln[ij])
                except Exception:                       # noqa: BLE001
                    uf = ""
                if uf:
                    por_uf.setdefault(uf, [])
    saida = {}
    for uf in sorted(por_uf):
        try:
            if filtro_uf:
                import relatorios_nucleo as _rn         # noqa: PLC0415
                ks = _rn.chamar_kpis_de(kpis_de, por_uf[uf], {ix: uf})
            else:
                ks = kpis_de(por_uf[uf])
        except Exception:                               # noqa: BLE001
            continue
        saida[uf] = {"kpis": ks or []}
    return saida


# (T-0026) PARCIAL em imagem (WhatsApp): a mesma imagem do PC (parcial_imagem.py,
# o resumo, sem o detalhe por vendedor), pronta no robo, uma por periodo, em PNG
# base64 dentro do farol (`parciais`). A web so mostra, baixa e monta o PDF.
PARCIAIS_WEB = {"pv_pedidos": "parcial_pedidos", "pl_entregas": "parcial_entregas",
                "vc_visitas": "parcial_visitas"}
QUANDOS_PARCIAL_WEB = ("acum", "d1", "hoje")


def parciais_web(raiz, hoje=None, log=None) -> dict:
    """{rid: {quando: {"rotulo", "png" (base64)}}} dos 3 faroes com parcial.
    Cada imagem num try proprio: a que falhar fica de fora (aviso no log);
    nunca levanta."""
    log = log or (lambda m: None)
    saida: dict = {}
    try:
        import io                                       # noqa: PLC0415
        import relatorios_nucleo as _rn                 # noqa: PLC0415
        import parcial_imagem as _pi                    # noqa: PLC0415
        hoje = hoje or _agora_manaus().date()
        hoje = hoje.date() if isinstance(hoje, datetime) else hoje
        ctx = _rn.Contexto(Path(raiz), hoje, None, {})
    except Exception as erro:                           # noqa: BLE001
        log(f"Parciais web: fora do pacote ({type(erro).__name__}).")
        return saida
    for rid, nome in PARCIAIS_WEB.items():
        for q in QUANDOS_PARCIAL_WEB:
            try:
                p = getattr(_rn, nome)(ctx, q)
                buf = io.BytesIO()
                _pi.desenhar(p, 1.5).save(buf, "PNG", optimize=True)
                saida.setdefault(rid, {})[q] = {
                    "rotulo": str(p.get("quando") or q),
                    "png": base64.b64encode(buf.getvalue()).decode("ascii")}
            except Exception as erro:                   # noqa: BLE001
                log(f"Parciais web: {rid}/{q} fora ({type(erro).__name__}).")
    return saida


def csvs_importar_web(raiz, hoje=None, log=None) -> list:
    """(T-0021) Os CSVs de importacao no Protheus (reversa de loja e separacao
    de CD) dos ultimos CSV_WEB_DIAS dias, para a aba Pedidos/Solicitacao BAP
    da web: [{"nome", "conteudo"}] com o texto exato do arquivo (UTF-8, mesmo
    separador e CRLF). So nomes no padrao AAMMDD_NNN_LOCAL_<tipo>.csv; teto de
    arquivos, de tamanho por arquivo e total. Nunca levanta."""
    log = log or (lambda m: None)
    saida: list = []
    try:
        pasta = Path(raiz) / SUBPASTA_IMPORTAR
        if not pasta.is_dir():
            return saida
        hoje = hoje or _agora_manaus().date()
        hoje = hoje.date() if isinstance(hoje, datetime) else hoje
        padrao = re.compile(
            rf"^(\d{{6}})_(\d{{1,4}})_([A-Z0-9]{{1,30}})_"
            rf"({SUFIXO_REVERSA}|{SUFIXO_SEPARACAO})\.csv$")
        achados = []
        for arq in pasta.iterdir():
            m = padrao.match(arq.name) if arq.is_file() else None
            if not m:
                continue
            try:
                dia = datetime.strptime(m.group(1), "%y%m%d").date()
            except ValueError:
                continue
            if 0 <= (hoje - dia).days <= CSV_WEB_DIAS:
                achados.append((m.group(1), int(m.group(2)), arq))
        achados.sort(key=lambda x: (x[0], x[1], x[2].name), reverse=True)
        total = 0
        for _d, _n, arq in achados[:CSV_WEB_MAX_ARQUIVOS]:
            try:
                bruto = arq.read_bytes()
                if len(bruto) > CSV_WEB_MAX_BYTES or \
                        total + len(bruto) > CSV_WEB_MAX_TOTAL:
                    log(f"CSV web: {arq.name} fora do pacote (tamanho).")
                    continue
                texto = bruto.decode("utf-8")
                if texto.startswith("\ufeff") or "\x00" in texto:
                    continue
                total += len(bruto)
                saida.append({"nome": arq.name, "conteudo": texto})
            except (OSError, UnicodeDecodeError):
                log(f"CSV web: {arq.name} fora do pacote (leitura).")
    except Exception as erro:                           # noqa: BLE001
        log(f"CSV web: fora do pacote ({type(erro).__name__}).")
        return []
    return saida


def montar_pacote_web(resultados: dict, ano: int, mes: int,
                      agora=None, raiz=None, arquivos_base=None,
                      cobranca=None, parciais=None, csvs=None,
                      cortar: bool = True) -> dict:
    """Funcao pura: recebe {"vc_painel": r} ja montado e leva so as abas
    resultado e produtividade, limpas para JSON. `cobranca` ({rid: bloco},
    T-0017 entrega 2): o bloco de cobranca_whatsapp.pacote_web do
    pl_inadimplencia, que leva junto as tabelas Titulos e Por cliente."""
    try:
        import relatorios_nucleo as _rn                 # noqa: PLC0415
        versao = int(getattr(_rn, "VERSAO_CONTRATO", 1))
    except Exception:                                   # noqa: BLE001
        versao = 1                                      # ausente = 1 (contrato)
    agora = _com_fuso_manaus(agora)
    limpos = {}
    rel = (resultados or {}).get("vc_painel")
    if isinstance(rel, dict):
        val = _para_json(selecionar_abas_web(rel))
        if isinstance(val, dict):
            try:                    # (T-0022) as outras 9 abas do Painel
                pn = _para_json(selecionar_paineis_web(
                    rel, (resultados or {}).get("vc_painel_uf")))
            except Exception as erro:                   # noqa: BLE001
                log.warning("Pacote web: abas de painel fora do pacote "
                            "(%s).", type(erro).__name__)
                pn = {}
            if pn:
                val["paineis"] = pn
            limpos["vc_painel"] = val
    for rid in FAROIS_WEB:                  # (T-0017) cada farol isolado
        rel = (resultados or {}).get(rid)
        if not isinstance(rel, dict) or rel.get("erro_montagem"):
            continue
        try:
            val = selecionar_farol_web(rid, rel, _baixado_em_da_base(
                rid, raiz, (arquivos_base or {}).get(rid)),
                cobranca=(cobranca or {}).get(rid), raiz=raiz,
                por_uf=(resultados or {}).get(rid + "_uf"))
        except Exception as erro:                       # noqa: BLE001
            log.warning("Pacote web: farol %s fora do pacote (%s).", rid,
                        type(erro).__name__)
            continue
        if val:
            if isinstance(parciais, dict) and parciais.get(rid):
                val["parciais"] = parciais[rid]         # T-0026
            if rid == "pv_pedidos" and csvs:            # T-0021
                val["csvs_protheus"] = [dict(c) for c in csvs]
            limpos[rid] = val
    pacote = {"versao_contrato": versao, "gerado_em": agora.isoformat(),
              "ano": int(ano), "mes": int(mes), "relatorios": limpos}
    # (T-0035) o envio por farol corta farol a farol: chama com cortar=False
    return _cortar_pacote_web(pacote) if cortar else pacote


def params_farol_web(rid: str, ano: int, mes: int) -> dict:
    """Funcao pura (T-0024): os parametros do `montar` de cada farol no mes do
    pacote. O Painel de indicadores le o MÊS como "AAAA-MM"; os demais, ANO e
    MÊS."""
    if rid == "pv_indicadores":
        return {"MÊS": f"{int(ano):04d}-{int(mes):02d}"}
    return {"ANO": str(ano), "MÊS": str(mes)}


def simular_pacote_farol(rid, raiz, destino, ano: int, mes: int,
                         hoje=None) -> dict:
    """Apoio da SIMULACAO (T-0017): monta o farol a partir das bases da pasta
    `raiz` (as congeladas do repositorio) e grava o pacote em `destino`.
    `rid` = um id ou uma lista (os 3 faroes de tabelas, entregas 3 a 5: o
    pacote sai com as abas, para medir o tamanho). O JSON pode ter dado
    pessoal (nome de vendedor com a D1 ligada): nao vai para o repositorio.
    Devolve o pacote."""
    import relatorios_nucleo as _rn                     # noqa: PLC0415
    rids = [rid] if isinstance(rid, str) else list(rid)
    hoje = hoje or _agora_manaus().date()
    rels, cobranca = {}, {}
    for r_id in rids:
        params = params_farol_web(r_id, ano, mes)
        rels[r_id] = _rn.montar(r_id, Path(raiz), hoje=hoje, params=params,
                                tela=(r_id == RID_META_WEB))
        if r_id in ("vc_painel", RID_META_WEB) + RIDS_KPIS_POR_UF_WEB:  # por estado
            rels[r_id + "_uf"] = montar_por_uf_web(r_id, rels[r_id], raiz,
                                                   params, hoje)
        if r_id == RID_COBRANCA_WEB:
            cobranca.update(preparar_cobranca_web(
                {r_id: rels[r_id]}, raiz, hoje, False, log=lambda m: None))
    pacote = montar_pacote_web(rels, ano, mes, raiz=raiz, cobranca=cobranca,
                               parciais=parciais_web(raiz, hoje),
                               csvs=csvs_importar_web(raiz, hoje))
    Path(destino).write_text(json.dumps(pacote, ensure_ascii=False,
                                        indent=1), encoding="utf-8")
    return pacote


def coletar_relatorios_web(ano: int, mes: int) -> dict:
    """Monta no PC o vc_painel do mes (o montar grava o historico do Diretor)
    e os faroes de FAROIS_WEB. Cada farol num try proprio: se um falhar, vira
    {"erro_montagem": ...} (aviso no log) e o pacote segue sem ele."""
    import relatorios_nucleo as _rn                     # noqa: PLC0415
    params = {"ANO": str(ano), "MÊS": str(mes)}
    saida = {"vc_painel": _rn.montar("vc_painel", PASTA_LOCAL,
                                     params=dict(params))}
    try:                         # (T-0022) o filtro de estado das abas do Painel
        saida["vc_painel_uf"] = montar_por_uf_web(
            "vc_painel", saida["vc_painel"], PASTA_LOCAL, params)
    except Exception as erro:                           # noqa: BLE001
        log.warning("Pacote web: Painel por estado fora (%s).",
                    type(erro).__name__)
    for rid in FAROIS_WEB:
        try:
            saida[rid] = _rn.montar(rid, PASTA_LOCAL,
                                    params=params_farol_web(rid, ano, mes),
                                    tela=(rid == RID_META_WEB))
            if rid == RID_META_WEB or rid in RIDS_KPIS_POR_UF_WEB:
                saida[rid + "_uf"] = montar_por_uf_web(   # (T-0022) por estado
                    rid, saida[rid], PASTA_LOCAL, params_farol_web(rid, ano, mes))
        except Exception as erro:                       # noqa: BLE001
            log.warning("Pacote web: o farol %s nao montou (%s); segue sem "
                        "ele.", rid, type(erro).__name__)
            saida[rid] = {"erro_montagem": type(erro).__name__}
    return saida


def _segredo_web(env: str, usuario: str):
    valor = (os.environ.get(env) or "").strip()
    if valor:
        return valor
    if keyring is not None:
        try:
            return (keyring.get_password(SERVICO_KEYRING_WEB, usuario)
                    or "").strip() or None
        except Exception:                               # noqa: BLE001
            return None
    return None


def enviar_pacote_web(pacote: dict, url=None, token=None, log=print) -> bool:
    """POST <url>/api/pacote (Bearer), 30 s, 3 tentativas, so https:443."""
    url = (url or _segredo_web("BAP_WEB_URL", "url") or "").strip()
    token = (token or _segredo_web("BAP_WEB_TOKEN", "token") or "").strip()
    if not url or not token:
        log("Pacote web: BAP_WEB_URL/BAP_WEB_TOKEN nao configurados; "
            "envio pulado.")
        return False

    def limpa(txt) -> str:
        return str(txt).replace(token, "***")

    base = _base_web(url)
    if not base:
        log("Pacote web: BAP_WEB_URL invalida ou nao e https na porta 443; "
            "envio recusado.")
        return False
    destino = f"{base}/api/pacote"
    try:
        corpo = json.dumps(pacote, ensure_ascii=False,
                           allow_nan=False).encode("utf-8")
        import requests                                 # noqa: PLC0415
    except Exception as erro:                           # noqa: BLE001
        log(f"Pacote web: nao deu para preparar o envio ({limpa(erro)}).")
        return False
    cab = {"Authorization": f"Bearer {token}",
           "Content-Type": "application/json; charset=utf-8"}
    for tentativa in range(1, 4):
        try:
            r = requests.post(destino, data=corpo, headers=cab, timeout=30)
            if 200 <= r.status_code < 300:
                log(f"Pacote web enviado ({len(corpo) / 1024:.0f} KB).")
                return True
            log(f"Pacote web: o servidor respondeu {r.status_code} "
                f"(tentativa {tentativa}/3).")
        except Exception as erro:                       # noqa: BLE001
            log(f"Pacote web: falha de rede, {type(erro).__name__}: "
                f"{limpa(erro)[:200]} (tentativa {tentativa}/3).")
        if tentativa < 3:
            time.sleep(2 * tentativa)
    return False


def _lote_web(gerado_em: str) -> str:
    """AAAAMMDDTHHMMSS do gerado_em (Manaus), como pacotes.nome_arquivo."""
    from datetime import timedelta, timezone            # noqa: PLC0415
    d = datetime.fromisoformat(str(gerado_em))
    if d.tzinfo is not None:            # outro fuso -> Manaus (-04:00, sem DST)
        d = d.astimezone(timezone(timedelta(hours=-4)))
    return d.strftime("%Y%m%dT%H%M%S")


def _formatos_web(base: str, requests) -> list:
    """GET /saude -> pacote.formatos; web antiga ou falha = [1] (10.8.1)."""
    try:
        r = requests.get(f"{base}/saude", timeout=15)
        if r.status_code == 200:
            f = ((r.json() or {}).get("pacote") or {}).get("formatos")
            if isinstance(f, list):
                return [x for x in f if isinstance(x, int)] or [1]
    except Exception:                                   # noqa: BLE001
        pass
    return [1]


def enviar_pacote_por_farol(pacote: dict, url=None, token=None, log=print,
                            requests=None) -> bool:
    """Formato 2 (T-0035, contrato 10.8): um POST por farol (gzip + sha256) e
    o `fechar`. Farol que falha (413/422/rede) vai no `manter`; o 404 sai; os
    outros seguem. So True se o `fechar` for aceito."""
    import gzip                                         # noqa: PLC0415
    import hashlib                                      # noqa: PLC0415
    url = (url or _segredo_web("BAP_WEB_URL", "url") or "").strip()
    token = (token or _segredo_web("BAP_WEB_TOKEN", "token") or "").strip()
    base = _base_web(url) if url else None
    if not url or not token or not base:
        log("Pacote web: URL/token ausentes ou invalidos; envio recusado.")
        return False
    if requests is None:
        import requests                                 # noqa: PLC0415

    def limpa(txt) -> str:
        return str(txt).replace(token, "***")
    try:
        lote = _lote_web(pacote["gerado_em"])
    except Exception as erro:                           # noqa: BLE001
        log(f"Pacote web: gerado_em invalido ({limpa(erro)}).")
        return False
    aceitos, manter, bytes_gz, prontos = {}, [], 0, {}
    for rid, farol in (pacote.get("relatorios") or {}).items():
        corpo = _json_farol_web(_cortar_farol_web(rid, farol))
        prontos[rid] = (hashlib.sha256(corpo).hexdigest(),
                        gzip.compress(corpo, 6))

    def enviar(rid) -> str:
        """'ok', 'manter', 'fora' ou 'auth' (401/403: para o lote)."""
        sha, gz = prontos[rid]
        cab = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json",
               "Content-Encoding": "gzip", "X-BAP-SHA256": sha}
        for tentativa in range(1, 4):
            try:
                r = requests.post(f"{base}/api/pacote/{lote}/farol/{rid}",
                                  data=gz, headers=cab, timeout=60)
                if 200 <= r.status_code < 300:
                    return "ok"
                if r.status_code in (401, 403):
                    log(f"Pacote web: token recusado ({r.status_code}); "
                        "o lote para aqui.")
                    return "auth"
                if r.status_code == 404:
                    log(f"Pacote web: farol {rid} desconhecido na web (404); "
                        "fica fora.")
                    return "fora"
                if r.status_code in (413, 422):
                    det = ""
                    try:
                        det = str((r.json() or {}).get("detalhes", ""))[:200]
                    except Exception:                   # noqa: BLE001
                        pass
                    log(f"Pacote web: farol {rid} recusado ({r.status_code}) "
                        f"{limpa(det)}; fica no manter.")
                    return "manter"
                log(f"Pacote web: farol {rid}: servidor {r.status_code} "
                    f"(tentativa {tentativa}/3).")
            except Exception as erro:                   # noqa: BLE001
                log(f"Pacote web: farol {rid}: falha de rede, "
                    f"{type(erro).__name__} (tentativa {tentativa}/3).")
            if tentativa < 3:
                time.sleep(2 * tentativa)
        return "manter"

    for rid in prontos:
        res = enviar(rid)
        if res == "auth":
            return False
        if res == "ok":
            aceitos[rid] = prontos[rid][0]
            bytes_gz += len(prontos[rid][1])
        elif res == "manter":
            manter.append(rid)
    if not aceitos:
        log("Pacote web: nenhum farol aceito; o lote nao e fechado.")
        return False
    for volta in range(2):          # o 409 "faltam": reenvia e fecha de novo
        corpo = {k: pacote.get(k) for k in
                 ("versao_contrato", "gerado_em", "ano", "mes")}
        corpo["farois"] = dict(aceitos)
        if manter:
            corpo["manter"] = list(manter)
        r = None
        for tentativa in range(1, 4):
            try:
                r = requests.post(
                    f"{base}/api/pacote/{lote}/fechar",
                    data=json.dumps(corpo).encode("utf-8"),
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"}, timeout=60)
                if r.status_code < 500:
                    break
                log(f"Pacote web: fechar: servidor {r.status_code} "
                    f"(tentativa {tentativa}/3).")
            except Exception as erro:                   # noqa: BLE001
                r = None
                log(f"Pacote web: fechar: falha de rede, "
                    f"{type(erro).__name__} (tentativa {tentativa}/3).")
            if tentativa < 3:
                time.sleep(2 * tentativa)
        if r is None:
            return False
        if 200 <= r.status_code < 300:
            log(f"Pacote web enviado por farol: {len(aceitos)} farois, "
                f"{bytes_gz / 1024:.0f} KB gzip, {len(manter)} no manter.")
            return True
        if r.status_code == 409 and volta == 0:
            try:
                faltam = [x for x in (r.json() or {}).get("farois", [])
                          if x in prontos]
            except Exception:                           # noqa: BLE001
                faltam = []
            for rid in faltam:
                aceitos.pop(rid, None)
                res = enviar(rid)
                if res == "auth":
                    return False
                if res == "ok":
                    aceitos[rid] = prontos[rid][0]
                elif res == "manter":
                    manter.append(rid)
            if aceitos:
                continue
        log(f"Pacote web: fechar recusado ({r.status_code}).")
        return False
    return False


def enviar_pacote(pacote: dict, url=None, token=None, log=print,
                  requests=None) -> bool:
    """Escolhe o formato pelo /saude (10.8.1): com `2` em pacote.formatos,
    por farol; senao (web antiga ou /saude fora), o formato 1 de sempre, com
    o corte global de 20 MB."""
    url = (url or _segredo_web("BAP_WEB_URL", "url") or "").strip()
    token = (token or _segredo_web("BAP_WEB_TOKEN", "token") or "").strip()
    base = _base_web(url) if url else None
    if base and token:
        if requests is None:
            try:
                import requests                         # noqa: PLC0415
            except Exception:                           # noqa: BLE001
                requests = None
        if requests is not None and 2 in _formatos_web(base, requests):
            return enviar_pacote_por_farol(pacote, url, token, log, requests)
    return enviar_pacote_web(_cortar_pacote_web(pacote), url, token, log)


# ---------------------------------------------------------------------------
# (T-0017, entrega 2, contrato §10.6.6 e §10.6.7) Cobranca no WhatsApp: o robo
# puxa do site o que a assistente marcou, grava no PC (COBRANCA_WEB.csv, pelo
# modulo-posvenda), so entao confirma, e monta a fila nova do pacote.
ARQ_ESTADO_COBRANCA_WEB = "ESTADO_COBRANCA_WEB.json"   # fora do glob COBRANCA_*.csv
_PAGINAS_MAX_COBRANCA_WEB = 200            # 200 x 1000 registros: trava de laco


def _cobranca_whatsapp(raiz=None):
    """O modulo cobranca_whatsapp (modulo-posvenda), da pasta do programa."""
    raiz = str(raiz or PASTA_LOCAL)
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import cobranca_whatsapp as cw                      # noqa: PLC0415
    return cw


def _pasta_cobranca(raiz) -> Path:
    return _cobranca_whatsapp(raiz).pasta(raiz)         # RELATORIOS/_COBRANCA_WHATSAPP


def ler_estado_cobranca(raiz) -> dict:
    """{"epoca": str, "ate_seq": int}: a epoca do diario do site e o maior seq
    dela ja gravado no COBRANCA_WEB.csv (contrato 10.6.7). Sem arquivo (ou
    estragado): epoca "" e 0 (puxa desde=0; o `id` evita repetir)."""
    try:
        d = json.loads((_pasta_cobranca(raiz) / ARQ_ESTADO_COBRANCA_WEB)
                       .read_text(encoding="utf-8"))
        n = int(d.get("ate_seq"))
        ep = d.get("epoca")
        if n < 0 or not isinstance(ep, str):
            raise ValueError("estado")
        return {"epoca": ep, "ate_seq": n}
    except Exception:                                   # noqa: BLE001
        return {"epoca": "", "ate_seq": 0}


def gravar_estado_cobranca(raiz, epoca: str, ate_seq: int, agora=None) -> None:
    """Grava o estado inteiro numa copia e troca (nunca fica pela metade)."""
    pasta = _pasta_cobranca(raiz)
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / ARQ_ESTADO_COBRANCA_WEB
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "epoca": str(epoca), "ate_seq": int(ate_seq),
        "em": _com_fuso_manaus(agora).replace(microsecond=0).isoformat()}),
        encoding="utf-8")
    os.replace(tmp, alvo)


def _base_web(url) -> str | None:
    """https://host[/caminho] sem barra no fim, ou None (so https, porta 443)."""
    from urllib.parse import urlparse                   # noqa: PLC0415
    try:
        p = urlparse((url or "").strip())
        if p.scheme != "https" or not p.hostname or p.port not in (None, 443):
            return None
        return f"https://{p.hostname}{p.path.rstrip('/')}"
    except Exception:                                   # noqa: BLE001
        return None


def _msg_http(codigo: int) -> str:
    if codigo == 401:
        return "token da web recusado (troque o BAP_WEB_TOKEN)"
    if codigo == 404:
        return "o site ainda nao tem /api/cobranca (404)"
    return f"o site respondeu {codigo}"


def baixar_cobranca_web(desde: int, base: str, token: str, sessao=None,
                        log=print) -> dict | None:
    """GET <base>/api/cobranca?desde=<seq> (Bearer), repetindo enquanto
    `mais`. Devolve {"epoca", "linhas", "ate_seq"}. None = nao deu para puxar
    (404 = web antiga, 401, 5xx, rede, resposta torta): quem chama segue sem
    importar. Falha depois da primeira pagina, ou epoca que muda no meio,
    devolve o que ja veio (ate_seq da ultima pagina boa). Log sem dado
    pessoal e sem token."""
    sessao = sessao or __import__("requests")
    cab = {"Authorization": f"Bearer {token}"}
    linhas, atual, epoca = [], int(desde), None
    for _ in range(_PAGINAS_MAX_COBRANCA_WEB):
        try:
            r = sessao.get(f"{base}/api/cobranca", params={"desde": atual},
                           headers=cab, timeout=30)
            if r.status_code != 200:
                log(f"Cobranca web: {_msg_http(r.status_code)}; sigo sem "
                    "importar" + (" o resto." if epoca is not None else "."))
                break
            d = r.json()
            pag, ate, ep = d["linhas"], int(d["ate_seq"]), str(d["epoca"])
            if not isinstance(pag, list) or (
                    epoca is not None and ep != epoca):
                raise ValueError("resposta")
        except Exception as erro:                       # noqa: BLE001
            log("Cobranca web: falha ao puxar o diario do site "
                f"({type(erro).__name__}); sigo sem importar"
                + (" o resto." if epoca is not None else "."))
            break
        epoca = ep
        linhas.extend(pag)
        mais = bool(d.get("mais"))
        if ate < atual or (mais and ate == atual):
            mais = False                    # servidor nao andou: nao laca
        atual = max(atual, ate)
        if not mais:
            break
    if epoca is None:
        return None
    return {"epoca": epoca, "linhas": linhas, "ate_seq": atual}


def confirmar_cobranca_web(epoca: str, ate_seq: int, base: str, token: str,
                           sessao=None, log=print) -> bool:
    """POST <base>/api/cobranca/confirmar {"epoca", "ate_seq"} (idempotente).
    So depois de gravar no PC."""
    sessao = sessao or __import__("requests")
    try:
        r = sessao.post(f"{base}/api/cobranca/confirmar",
                        json={"epoca": str(epoca), "ate_seq": int(ate_seq)},
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=30)
        if r.status_code == 200:
            return True
        log(f"Cobranca web: a confirmacao voltou {r.status_code} "
            f"({_msg_http(r.status_code)}); confirmo de novo na proxima "
            "rodada.")
    except Exception as erro:                           # noqa: BLE001
        log(f"Cobranca web: falha ao confirmar ({type(erro).__name__}); "
            "confirmo de novo na proxima rodada.")
    return False


def sincronizar_cobranca_web(raiz, nomes, cw, base: str, token: str,
                             sessao=None, log=print) -> dict:
    """Passos 1 a 3 do 10.6.7. Devolve o estado da rodada {"epoca", "ate_seq"}
    = o maior seq da epoca ja gravado no COBRANCA_WEB.csv (vira o
    `web_ate_seq` do pacote, tenha a confirmacao dado certo ou nao).
    - epoca da resposta diferente da do estado: descarta e puxa de novo com
      desde=0 (o `id` evita repetir no CSV);
    - erro de disco no importar: nao confirma e nao mexe no estado;
    - confirma em toda rodada com ate_seq > 0 (refaz a que falhou).
    Nunca levanta."""
    estado = ler_estado_cobranca(raiz)
    try:
        desde = estado["ate_seq"] if estado["epoca"] else 0
        res = baixar_cobranca_web(desde, base, token, sessao, log)
        if res and estado["epoca"] != res["epoca"]:
            if estado["epoca"]:
                log("Cobranca web: o diario do site recomecou (epoca nova); "
                    "puxo tudo de novo.")
            estado = {"epoca": res["epoca"], "ate_seq": 0}
            if desde:                   # com desde=0 a resposta ja vale
                res = baixar_cobranca_web(0, base, token, sessao, log)
                if res and res["epoca"] != estado["epoca"]:
                    res = None
        if not res:
            return estado               # sem rede/web antiga: estado de antes
        if res["linhas"]:
            novas = cw.importar_web(raiz, res["linhas"], nomes)
            log(f"Cobranca web: {novas} registro(s) novo(s) do site gravados "
                "no PC.")
        maior = max([int(x.get("seq") or 0) for x in res["linhas"]] or [0])
        novo = {"epoca": res["epoca"],
                "ate_seq": max(estado["ate_seq"], maior)
                if estado["epoca"] == res["epoca"] else maior}
    except Exception as erro:                           # noqa: BLE001
        log("Cobranca web: nao gravei no PC "
            f"({type(erro).__name__}); nao confirmo, tento de novo na "
            "proxima rodada.")
        return estado
    try:
        gravar_estado_cobranca(raiz, novo["epoca"], novo["ate_seq"])
    except Exception as erro:                           # noqa: BLE001
        log(f"Cobranca web: nao guardei o estado ({type(erro).__name__}); "
            "a proxima rodada puxa de novo (o id evita repetir).")
    if novo["ate_seq"] > 0:
        confirmar_cobranca_web(novo["epoca"], novo["ate_seq"], base, token,
                               sessao, log)
    return novo


def nomes_por_cliente_web(r: dict) -> dict:
    """{CLIENTE (cod-loja): NOME} da aba Por cliente (para o COBRANCA_WEB.csv)."""
    t = next((x for x in (r or {}).get("tabelas") or []
              if isinstance(x, dict) and x.get("titulo") == "Por cliente"),
             None)
    if not t:
        return {}
    nm = [c.get("nome") if isinstance(c, dict) else c
          for c in t.get("colunas") or []]
    if "CLIENTE" not in nm or "NOME" not in nm:
        return {}
    ic, inome = nm.index("CLIENTE"), nm.index("NOME")
    return {str(ln[ic]).strip(): str(ln[inome] or "").strip()
            for ln in t.get("linhas") or []}


def montar_cobranca_web(rel: dict, raiz, cw, web_ate_seq: int, agora=None,
                        fantasias=None, web_epoca: str = "") -> dict | None:
    """O bloco `cobranca` do §10.6.3, lendo o historico DEPOIS da importacao.
    None se o cobranca_whatsapp do PC for antigo (sem pacote_web)."""
    if not (callable(getattr(cw, "pacote_web", None))
            and callable(getattr(cw, "historico_origem", None))):
        return None
    agora = _com_fuso_manaus(agora).replace(microsecond=0)
    return cw.pacote_web(rel, fantasias or {}, cw.historico_origem(raiz),
                         agora, web_ate_seq=int(web_ate_seq),
                         web_epoca=str(web_epoca or ""),
                         gerado_em=agora.isoformat())


def _fantasias_clientes(raiz) -> dict:
    """{cod (sem loja): fantasia ou nome} do cadastro, o mesmo nome que a
    janela do PC usa na mensagem. Falhou = {} (a mensagem usa o NOME)."""
    try:
        import relatorios_nucleo as _rn                 # noqa: PLC0415
        ctx = _rn.Contexto(Path(raiz), date.today(), None, {})
        return {_rn.texto(c.get("cod")): _rn.texto(c.get("fantasia"))
                or _rn.texto(c.get("nome"))
                for c in ctx.base.get("clientes") or []}
    except Exception:                                   # noqa: BLE001
        return {}


def preparar_cobranca_web(resultados: dict, raiz, hoje, sincronizar: bool,
                          url=None, token=None, log=print):
    """Passo 4f, parte da cobranca: devolve {RID: bloco} para o
    montar_pacote_web (ou {} se nao der: o farol vai sem as abas novas)."""
    rel = (resultados or {}).get(RID_COBRANCA_WEB)
    if not isinstance(rel, dict) or rel.get("erro_montagem"):
        return {}
    try:
        if str(raiz) not in sys.path:
            sys.path.insert(0, str(raiz))
        cw = _cobranca_whatsapp(raiz)
        estado = ler_estado_cobranca(raiz)
        base = _base_web(url)
        if sincronizar and base and token:
            estado = sincronizar_cobranca_web(
                raiz, nomes_por_cliente_web(rel), cw, base, token, log=log)
        bloco = montar_cobranca_web(rel, raiz, cw, estado["ate_seq"],
                                    _agora_manaus(), _fantasias_clientes(raiz),
                                    estado["epoca"])
        return {RID_COBRANCA_WEB: bloco} if bloco else {}
    except Exception as erro:                           # noqa: BLE001
        log(f"Cobranca web: a fila ficou fora do pacote ({type(erro).__name__}).")
        return {}


# ---------------------------------------------------------------------------
# (T-0021) O robo traz as edicoes do site: GET /api/edicoes?desde=<seq>,
# grava no PC pela funcao da tela do PC (bap_relatorios.Janela.salvar: so
# acrescenta linha) e confirma POST /api/edicoes/confirmar. Antes de montar o
# pacote: o pacote desta rodada ja sai com a edicao. Nunca derruba a rodada;
# o log nao tem dado pessoal nem token.
PASTA_EDICOES_WEB = Path("RELATORIOS") / "_EDICOES_WEB"
ARQ_ESTADO_EDICOES_WEB = "ESTADO_EDICOES_WEB.json"
_PAGINAS_MAX_EDICOES_WEB = 50
# motivos de recusa (vao ao site): frases fixas, sem dado pessoal
MOTIVO_LUGAR_WEB = "tabela ou campo que não edita na web"
MOTIVO_CHAVE_WEB = "chave da linha inválida"
MOTIVO_OPCAO_WEB = "valor fora das opções do PC"
MOTIVO_DATA_WEB = "data inválida"
MOTIVO_VALOR_WEB = "valor inválido"


def motivo_texto_web(maximo=None) -> str:
    """A frase fixa do texto recusado, com o teto do campo (10.9.1); sem
    `maximo`, o padrao do nucleo (MAX_TEXTO_PADRAO)."""
    if maximo is None:
        import relatorios_nucleo as _rn                 # noqa: PLC0415
        maximo = _rn.MAX_TEXTO_PADRAO
    return (f"texto inválido (até {int(maximo)} caracteres, sem CPF, CNPJ, "
            "telefone ou e-mail)")


def __getattr__(nome):          # MOTIVO_TEXTO_WEB: a frase com o teto padrao
    if nome == "MOTIVO_TEXTO_WEB":
        return motivo_texto_web()
    raise AttributeError(nome)


MOTIVO_REMOVIDO_WEB = "texto com trecho removido pelo site"
MOTIVO_TICKET_WEB = "já existe uma garantia com esse número"
_RE_CHAVE_NOVA_WEB = re.compile(r"^NOVO-[0-9A-F]{8}$")
_RE_TICKET_WEB = re.compile(r"^[\w.\-/ ]{1,40}$")
_DATA_LIVRE_MIN_WEB = date(2020, 1, 1)
MOTIVO_LINHA_WEB = "linha não encontrada no PC"


def _pasta_edicoes_web(raiz) -> Path:
    return Path(raiz) / PASTA_EDICOES_WEB


def _importar_do_pc(nome: str, raiz):
    """Um modulo do PC (pos_venda, autorizacoes...) da pasta do programa."""
    raiz = str(raiz or PASTA_LOCAL)
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    import importlib                                    # noqa: PLC0415
    return importlib.import_module(nome)


def gravar_edicoes_pc(raiz, modulo: str, arquivo: str, aba: str,
                      edicoes: dict) -> int:
    """A MESMA gravacao da tela do PC (bap_relatorios.Janela.salvar), por
    modulo: {chave: {campo: valor}}. Levanta PermissionError (arquivo aberto
    no Excel), OSError ou ValueError como a tela."""
    raiz = Path(raiz)
    if modulo == "autorizacoes":
        return _importar_do_pc("autorizacoes", raiz).gravar(raiz, edicoes)
    if modulo == "expositores":
        return _importar_do_pc("expositores", raiz).gravar_edicoes(raiz,
                                                                    edicoes)
    if modulo == "ncc":
        return _importar_do_pc("ncc_controle", raiz).gravar(raiz, edicoes)
    if modulo == "garantias":
        return _gravar_garantia_pc(raiz, edicoes)
    if modulo == "farol":
        return _importar_do_pc("farol_ddr", raiz).gravar_marcacoes(
            raiz / arquivo, aba, edicoes)
    if modulo == "pos_venda":
        return _importar_do_pc("pos_venda", raiz).gravar_edicoes(
            raiz / arquivo, aba, edicoes)
    raise ValueError("modulo sem gravacao no robo")


def _gravar_garantia_pc(raiz, edicoes: dict) -> int:
    """(T-0023 v2) A MESMA gravacao da janela da garantia do PC
    (bap_relatorios.DialogoGarantia.salvar): so acrescenta linha no diario
    (`garantias.gravar`; o ticket trocado, `garantias.renomear`). `edicoes` =
    {ticket atual ("" = garantia nova): {campo: valor}}; um "ticket" dentro
    dos campos e o numero novo. Devolve quantos campos mudaram; levanta
    ValueError (ticket recusado) ou OSError como a tela."""
    gm = _importar_do_pc("garantias", raiz)
    n = 0
    for atual, campos in edicoes.items():
        campos = dict(campos)
        novo_t = campos.pop("ticket", atual) or ""
        if novo_t != atual:
            erro = gm.renomear(raiz, atual or None, novo_t)
            if erro:
                raise ValueError(erro)
            n += 1 if atual else 0
        n += gm.gravar(raiz, novo_t, campos)
    return n


def opcoes_edicao_web(raiz) -> dict:
    """As listas fechadas do PC para conferir a edicao: {campo: set}. As da
    (T-0023 v2) NCC, da Devolucao e da Garantia levam o prefixo do lugar
    ("ncc.status", "devolucoes.etapa", "garantias.status"...), porque o mesmo
    nome de campo tem outra lista em outro lugar."""
    rn_ = _importar_do_pc("relatorios_nucleo", raiz)
    pv = _importar_do_pc("pos_venda", raiz)
    tr = _importar_do_pc("transportadoras", raiz)
    nc = _importar_do_pc("ncc_controle", raiz)
    gm = _importar_do_pc("garantias", raiz)
    return {"por": set(rn_.QUEM_AUTORIZA), "etapa": set(pv.ETAPAS_ENTREGA),
            "transportadora": set(tr.nomes(tr.carregar(Path(raiz)))),
            "ncc.status": set(rn_.NCC_SUGESTOES) | set(nc.STATUS_NOVOS),
            "devolucoes.etapa": set(pv.ETAPAS_DEVOLUCAO),
            "devolucoes.motivo": set(pv.MOTIVOS_DEVOLUCAO),
            "devolucoes.credito": set(pv.FORMAS_CREDITO),
            "garantias.status": set(gm.STATUS),
            "garantias.resultado": set(gm.RESULTADOS)}


def _opcoes_do_campo_web(lugar: dict, campo: str, opcoes: dict):
    """A lista fechada do campo no lugar: a do prefixo do lugar, senao a
    chata (a mesma de antes da T-0023)."""
    pref = lugar.get("pref") or lugar["modulo"]
    for k in (f"{pref}.{campo}", campo):
        if k in opcoes:
            return opcoes[k] or ()
    return ()


def _mais_um_ano_web(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:                                  # 29/02
        return d.replace(year=d.year + 1, day=28)


def _texto_normalizado_web(v: str) -> str:
    """A comparacao do texto livre (10.9.1, regra 1): quebras de linha
    iguais (CRLF e CR viram LF) e sem espaco nas pontas."""
    return v.replace("\r\n", "\n").replace("\r", "\n").strip()


def valores_normalizados_web(reg: dict) -> dict:
    """Os valores que vao ao PC: o texto livre com as quebras de linha e as
    pontas normalizadas (so le `reg`, devolve outro dicionario)."""
    lugar = EDICOES_WEB.get((reg.get("rid"), reg.get("tabela"))) or {}
    campos = (campos_do_lugar_web(reg.get("rid"), reg.get("tabela"))
              if lugar else {})
    return {k: (_texto_normalizado_web(v) if campos.get(k) in ("livre",
                                                                "longo")
                and isinstance(v, str) else v)
            for k, v in (reg.get("valores") or {}).items()}


def validar_edicao_web(reg: dict, opcoes: dict) -> str:
    """Funcao pura (T-0021): "" se a edicao do site pode ir ao PC; senao o
    motivo (frase fixa, sem dado pessoal). Confere de novo o que a web ja
    conferiu: lugar, campos do lugar, listas fechadas, data, valor, texto
    (teto do nucleo, sem dado pessoal, sem "[removido]") e, na linha nova
    (T-0023 v2), a chave NOVO-xxxxxxxx. `opcoes["_hoje"]` (opcional) = o dia
    de hoje, para a data livre."""
    lugar = EDICOES_WEB.get((reg.get("rid"), reg.get("tabela")))
    if not lugar or reg.get("modulo") != lugar["modulo"]:
        return MOTIVO_LUGAR_WEB
    chave = reg.get("chave")
    novo = reg.get("novo") is True
    if novo and not lugar.get("novo"):
        return MOTIVO_LUGAR_WEB
    if novo:
        if not (isinstance(chave, str) and _RE_CHAVE_NOVA_WEB.match(chave)):
            return MOTIVO_CHAVE_WEB
    elif not (isinstance(chave, str) and _RE_CHAVE_EDICAO_WEB.match(chave)):
        return MOTIVO_CHAVE_WEB
    if lugar["modulo"] == "autorizacoes" and not re.fullmatch(
            r"\d+\|\d+", chave):
        return MOTIVO_CHAVE_WEB
    if lugar["modulo"] == "pos_venda" and chave.count("|") != 2:
        return MOTIVO_CHAVE_WEB
    if lugar["modulo"] == "ncc" and chave.count("|") != 3:
        return MOTIVO_CHAVE_WEB
    valores = reg.get("valores")
    campos = campos_do_lugar_web(reg.get("rid"), reg.get("tabela"))
    if not (isinstance(valores, dict) and valores
            and set(valores) <= set(campos)):
        return MOTIVO_LUGAR_WEB
    import relatorios_nucleo as _rn                     # noqa: PLC0415
    hoje = opcoes.get("_hoje") or _agora_manaus().date()
    for campo, v in valores.items():
        tipo = campos[campo]
        texto_livre = tipo in ("livre", "longo")
        teto = (_rn.max_texto_edicao(lugar["modulo"], campo)
                if texto_livre or tipo == "ticket"
                else _rn.MAX_TEXTO_PADRAO)
        if not isinstance(v, str):
            return motivo_texto_web(teto)
        if texto_livre:
            v = _texto_normalizado_web(v)
        if re.search(r"[\x00-\x09\x0b-\x1f\x7f]" if tipo == "longo"
                     else r"[\x00-\x1f\x7f]", v):
            return motivo_texto_web(teto)
        if len(v) > teto:
            return motivo_texto_web(teto)
        if texto_livre:
            if _rn.REMOVIDO in v:
                return MOTIVO_REMOVIDO_WEB
            if _rn.texto_sem_contato(v) != v:
                return motivo_texto_web(teto)
        if tipo == "ticket" and not _RE_TICKET_WEB.match(v):
            return MOTIVO_VALOR_WEB
        if tipo == "lista" and v and v not in _opcoes_do_campo_web(
                lugar, campo, opcoes):
            return MOTIVO_OPCAO_WEB
        if tipo in ("data", "data_livre") and v:
            try:
                d = datetime.strptime(v, "%d/%m/%Y").date()
            except ValueError:
                return MOTIVO_DATA_WEB
            if tipo == "data_livre" and not (
                    _DATA_LIVRE_MIN_WEB <= d <= _mais_um_ano_web(hoje)):
                return MOTIVO_DATA_WEB
        if tipo == "valor" and v:
            try:
                n = _importar_do_pc("pos_venda", None).valor_digitado(v)
            except ValueError:
                return MOTIVO_VALOR_WEB
            if n is not None and n < 0:
                return MOTIVO_VALOR_WEB
    return ""


def plano_garantia_web(reg: dict, valores: dict, existentes: dict,
                       novo_ticket: str, hoje: date, fer=()) -> tuple:
    """Funcao pura (T-0023 v2, 10.9.2): (plano, motivo). `plano` = {"atual":
    ticket que ja existe ("" = garantia nova), "campos": {...}, "ticket":
    numero final}; sem plano, o motivo e a frase fixa. `existentes` = {ticket:
    cadastro} (garantias.ler); `novo_ticket` = o garantias.novo_ticket da
    hora; `fer` = os feriados. A regra do prazo e da origem e a do nucleo
    (`campos_garantia_a_gravar`, RN-POS-005): o prazo igual ao padrao fica em
    branco, como no PC.
    - Linha nova: o ticket enviado igual ao `antes.ticket` que o formulario
      mostrou e que ja existe no PC vira o `novo_ticket` da hora; o digitado
      diferente do padrao que ja existe e recusado. Status ABERTO, resultado
      PENDENTE e a data de hoje valem quando a web nao mandou (padrao do
      formulario); a origem e a do PC ("FAROL DE GARANTIAS").
    - Edicao: a garantia tem de existir; o ticket trocado nao pode ser de
      outra."""
    campos = dict(valores)
    if reg.get("novo") is True:
        t = str(campos.pop("ticket", "") or "").strip()
        if not t:
            return None, MOTIVO_VALOR_WEB
        antes_t = str((reg.get("antes") or {}).get("ticket") or "").strip()
        if t == antes_t and t in existentes:
            t = novo_ticket
        elif t in existentes:
            return None, MOTIVO_TICKET_WEB
        import relatorios_nucleo as _rn                 # noqa: PLC0415
        base = {**_rn.PADRAO_NOVA_GARANTIA,
                "dt_solicitacao": f"{hoje:%d/%m/%Y}"}
        base.update(campos)
        atual, campos = "", base
    else:
        atual = str(reg.get("chave") or "")
        if atual not in existentes:
            return None, MOTIVO_LINHA_WEB
        t = atual
        if "ticket" in campos:
            t = str(campos.pop("ticket") or "").strip()
            if not t:
                return None, MOTIVO_VALOR_WEB
            if t != atual and t in existentes:
                return None, MOTIVO_TICKET_WEB
    import relatorios_nucleo as _rn2                    # noqa: PLC0415
    sol = campos.get("dt_solicitacao") or (
        existentes.get(atual) or {}).get("dt_solicitacao") or ""
    campos = {k: v for k, v in _rn2.campos_garantia_a_gravar(
        {**campos, "dt_solicitacao": sol}, fer, novo=not atual).items()
        if k != "dt_solicitacao" or "dt_solicitacao" in campos or not atual}
    if t != atual:
        campos["ticket"] = t
    return {"atual": atual, "campos": campos, "ticket": t}, ""


def aplicar_edicao_web(raiz, reg: dict, opcoes: dict,
                       gravar=gravar_edicoes_pc, _saida=None) -> tuple:
    """(status, motivo): "aplicada", "erro" (recusada: vai ao site) ou
    "pendente" (arquivo aberto/disco: tenta na proxima rodada). `_saida`
    (opcional, um dict) recebe {"chave_pc": o ticket gravado} na garantia."""
    motivo = validar_edicao_web(reg, opcoes)
    if motivo:
        return "erro", motivo
    lugar = EDICOES_WEB[(reg["rid"], reg["tabela"])]
    valores = valores_normalizados_web(reg)
    edicoes = {reg["chave"]: valores}
    try:
        if lugar["modulo"] == "garantias":
            gm = _importar_do_pc("garantias", raiz)
            hoje = opcoes.get("_hoje") or _agora_manaus().date()
            try:
                fer = _importar_do_pc("bap_dados", raiz).feriados(raiz)
            except Exception:                           # noqa: BLE001
                fer = set()
            plano, motivo = plano_garantia_web(
                reg, valores, gm.ler(raiz), gm.novo_ticket(raiz), hoje, fer)
            if not plano:
                return "erro", motivo
            edicoes = {plano["atual"]: plano["campos"]}
            if _saida is not None:
                _saida["chave_pc"] = plano["ticket"]
        gravar(raiz, lugar["modulo"], lugar["arquivo"], lugar["aba"],
               edicoes)
    except PermissionError:
        return "pendente", "arquivo aberto no Excel"
    except ValueError:
        return "erro", MOTIVO_LINHA_WEB
    except OSError:
        return "pendente", "falha de disco"
    return "aplicada", ""


def ler_estado_edicoes_web(raiz) -> dict:
    """{"epoca", "ate_seq", "a_confirmar"}; sem arquivo (ou torto): do zero."""
    try:
        d = json.loads((_pasta_edicoes_web(raiz) / ARQ_ESTADO_EDICOES_WEB)
                       .read_text(encoding="utf-8"))
        n, ep = int(d.get("ate_seq")), d.get("epoca")
        ac = d.get("a_confirmar") or []
        if n < 0 or not isinstance(ep, str) or not isinstance(ac, list):
            raise ValueError("estado")
        return {"epoca": ep, "ate_seq": n, "a_confirmar": ac}
    except Exception:                                   # noqa: BLE001
        return {"epoca": "", "ate_seq": 0, "a_confirmar": []}


def gravar_estado_edicoes_web(raiz, estado: dict) -> None:
    pasta = _pasta_edicoes_web(raiz)
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / ARQ_ESTADO_EDICOES_WEB
    tmp = alvo.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, alvo)


def _arq_aplicadas_web(raiz) -> Path:
    maq = re.sub(r"[^A-Za-z0-9_-]", "_", os.environ.get("COMPUTERNAME")
                 or __import__("platform").node() or "PC")
    return _pasta_edicoes_web(raiz) / f"APLICADAS_WEB_{maq}.jsonl"


def aplicadas_web(raiz) -> dict:
    """{id da edicao: (status, motivo)} de todas as maquinas (so acrescenta):
    a edicao ja gravada no PC nunca e gravada de novo."""
    saida = {}
    pasta = _pasta_edicoes_web(raiz)
    for arq in sorted(pasta.glob("APLICADAS_WEB_*.jsonl")) if pasta.is_dir() \
            else []:
        try:
            for ln in arq.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(ln)
                    saida[str(r["id"])] = (r["status"], r.get("motivo", ""))
                except (ValueError, KeyError, TypeError):
                    continue
        except OSError:
            continue
    return saida


def _registrar_aplicada_web(raiz, reg, status, motivo, epoca,
                            extra=None) -> None:
    arq = _arq_aplicadas_web(raiz)
    arq.parent.mkdir(parents=True, exist_ok=True)
    linha = {"quando": _agora_manaus().strftime("%Y-%m-%d %H:%M:%S"),
             "epoca": epoca, "seq": reg.get("seq"), "id": reg.get("id"),
             "usuario_web": reg.get("usuario"), "rid": reg.get("rid"),
             "tabela": reg.get("tabela"), "chave": reg.get("chave"),
             "valores": reg.get("valores"), "status": status,
             "motivo": motivo}
    if isinstance(reg.get("antes"), dict):     # o valor de antes (10.9.3)
        linha["antes"] = reg["antes"]
    if reg.get("novo") is True:
        linha["novo"] = True
    linha.update(extra or {})
    with open(arq, "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def baixar_edicoes_web(desde: int, base: str, token: str, sessao=None,
                       log=print) -> dict | None:
    """GET <base>/api/edicoes?desde=<seq> (Bearer), repetindo enquanto
    `mais`. {"epoca", "linhas", "ate_seq"} ou None (404 = web antiga, 401,
    rede...). Log sem dado pessoal e sem token."""
    sessao = sessao or __import__("requests")
    cab = {"Authorization": f"Bearer {token}"}
    linhas, atual, epoca = [], int(desde), None
    for _ in range(_PAGINAS_MAX_EDICOES_WEB):
        try:
            r = sessao.get(f"{base}/api/edicoes", params={"desde": atual},
                           headers=cab, timeout=30)
            if r.status_code != 200:
                log(f"Edicoes web: o site respondeu {r.status_code}; sigo "
                    "sem importar.")
                break
            d = r.json()
            pag, ate, ep = d["linhas"], int(d["ate_seq"]), str(d["epoca"])
            if not isinstance(pag, list) or (epoca is not None
                                              and ep != epoca):
                raise ValueError("resposta")
        except Exception as erro:                       # noqa: BLE001
            log("Edicoes web: falha ao puxar as edicoes do site "
                f"({type(erro).__name__}); sigo sem importar.")
            break
        epoca = ep
        linhas.extend(x for x in pag if isinstance(x, dict))
        mais = bool(d.get("mais"))
        if ate < atual or (mais and ate == atual):
            mais = False
        atual = max(atual, ate)
        if not mais:
            break
    if epoca is None:
        return None
    return {"epoca": epoca, "linhas": linhas, "ate_seq": atual}


def confirmar_edicoes_web(epoca: str, resultados: list, base: str,
                          token: str, sessao=None, log=print) -> bool:
    sessao = sessao or __import__("requests")
    try:
        r = sessao.post(f"{base}/api/edicoes/confirmar",
                        json={"epoca": str(epoca), "resultados": resultados},
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=30)
        if r.status_code == 200:
            return True
        log(f"Edicoes web: a confirmacao voltou {r.status_code}; confirmo "
            "de novo na proxima rodada.")
    except Exception as erro:                           # noqa: BLE001
        log(f"Edicoes web: falha ao confirmar ({type(erro).__name__}); "
            "confirmo de novo na proxima rodada.")
    return False


def sincronizar_edicoes_web(raiz, base: str, token: str, sessao=None,
                            log=print, gravar=gravar_edicoes_pc,
                            opcoes=None) -> dict:
    """Puxa, grava no PC (na ordem do seq; a primeira que fica pendente -
    Excel aberto - para a fila ate a proxima rodada), guarda o estado e
    confirma. Devolve {"aplicadas", "erros", "pendentes", "confirmado"}.
    Nunca levanta."""
    cont = {"aplicadas": 0, "erros": 0, "pendentes": 0, "confirmado": False}
    try:
        estado = ler_estado_edicoes_web(raiz)
        desde = estado["ate_seq"] if estado["epoca"] else 0
        res = baixar_edicoes_web(desde, base, token, sessao, log)
        if res and res["epoca"] != estado["epoca"]:
            if estado["epoca"]:
                log("Edicoes web: a fila do site recomecou (epoca nova); "
                    "puxo tudo de novo.")
            estado = {"epoca": res["epoca"], "ate_seq": 0, "a_confirmar": []}
            if desde:
                res = baixar_edicoes_web(0, base, token, sessao, log)
                if res and res["epoca"] != estado["epoca"]:
                    res = None
        if not res:
            if estado["a_confirmar"] and estado["epoca"]:
                cont["confirmado"] = confirmar_edicoes_web(
                    estado["epoca"], estado["a_confirmar"], base, token,
                    sessao, log)
            return cont
        opcoes = opcoes if opcoes is not None else opcoes_edicao_web(raiz)
        ja = aplicadas_web(raiz)
        resultados = {int(x["seq"]): x for x in estado["a_confirmar"]
                      if isinstance(x, dict) and "seq" in x}
        ate = estado["ate_seq"]
        for reg in sorted(res["linhas"], key=lambda x: int(x.get("seq") or 0)):
            seq = int(reg.get("seq") or 0)
            if seq <= ate:
                continue
            if reg.get("status") != "pendente":
                ate = seq                   # ja confirmada no site
                continue
            if str(reg.get("id")) in ja:
                status, motivo = ja[str(reg.get("id"))]
            else:
                extra = {}
                status, motivo = aplicar_edicao_web(
                    raiz, reg, opcoes, gravar, _saida=extra)
                if status == "pendente":
                    cont["pendentes"] += 1
                    log(f"Edicoes web: {motivo}; a fila espera a proxima "
                        "rodada.")
                    break
                _registrar_aplicada_web(raiz, reg, status, motivo,
                                        res["epoca"], extra)
            cont["aplicadas" if status == "aplicada" else "erros"] += 1
            resultados[seq] = {"seq": seq, "status": status, "motivo": motivo}
            ate = seq
        estado = {"epoca": res["epoca"], "ate_seq": ate,
                  "a_confirmar": sorted(resultados.values(),
                                        key=lambda x: x["seq"])}
        gravar_estado_edicoes_web(raiz, estado)
        if cont["aplicadas"] or cont["erros"]:
            log(f"Edicoes web: {cont['aplicadas']} gravada(s) no PC, "
                f"{cont['erros']} recusada(s).")
        if estado["a_confirmar"]:
            cont["confirmado"] = confirmar_edicoes_web(
                estado["epoca"], estado["a_confirmar"], base, token, sessao,
                log)
            if cont["confirmado"]:
                gravar_estado_edicoes_web(raiz, dict(estado, a_confirmar=[]))
    except Exception as erro:                           # noqa: BLE001
        log(f"Edicoes web: nao terminei ({type(erro).__name__}); tento de "
            "novo na proxima rodada.")
    return cont


def gravar_lote_simulado_web(pacote: dict, pasta) -> dict:
    """(T-0035) Grava ao lado do JSON a pasta do lote: `<rid>.json.gz` e o
    `indice.json` (so tamanhos e sha). Devolve {rid: {bytes_json, bytes_gz}}."""
    import gzip                                         # noqa: PLC0415
    import hashlib                                      # noqa: PLC0415
    dest = Path(pasta) / _lote_web(pacote["gerado_em"])
    dest.mkdir(parents=True, exist_ok=True)
    tam, indice = {}, {}
    for rid, farol in (pacote.get("relatorios") or {}).items():
        farol = _cortar_farol_web(rid, farol)
        corpo = _json_farol_web(farol)
        gz = gzip.compress(corpo, 6)
        (dest / f"{rid}.json.gz").write_bytes(gz)
        tam[rid] = {"bytes_json": len(corpo), "bytes_gz": len(gz)}
        indice[rid] = dict(tam[rid], sha256=hashlib.sha256(corpo).hexdigest())
    (dest / "indice.json").write_text(json.dumps(
        {"formato": 2, "farois": indice}), encoding="utf-8")
    return tam


def passo_pacote_web(simular_pacote: bool = False) -> dict:
    """4f: monta, e envia (ou so grava o simulado). Nunca levanta."""
    try:
        # (23/11, revisao do PR #16) sem URL/token da web, nem monta: a rodada
        # do robo fica como antes do 4f (sem montar o Painel a toa)
        if not simular_pacote and not (
                _segredo_web("BAP_WEB_URL", "url")
                and _segredo_web("BAP_WEB_TOKEN", "token")):
            log.info("Pacote web: BAP_WEB_URL/BAP_WEB_TOKEN nao configurados; "
                     "passo 4f pulado (o Painel nao e montado).")
            return {"enviado": False, "pulado": True}
        hoje = _agora_manaus()
        if not simular_pacote:          # (T-0021) as edicoes do site antes do montar
            _tk = _segredo_web("BAP_WEB_TOKEN", "token") or ""
            _base = _base_web(_segredo_web("BAP_WEB_URL", "url"))
            if _base and _tk:
                sincronizar_edicoes_web(
                    PASTA_LOCAL, _base, _tk,
                    log=lambda m: log.info("%s", str(m).replace(_tk, "***")))
        resultados = coletar_relatorios_web(hoje.year, hoje.month)
        # (T-0017, entrega 2) GET -> importar -> confirmar -> fila; na
        # simulacao nao toca na rede nem no disco do diario
        cobranca = preparar_cobranca_web(
            resultados, PASTA_LOCAL, hoje, not simular_pacote,
            _segredo_web("BAP_WEB_URL", "url"),
            _segredo_web("BAP_WEB_TOKEN", "token"),
            log=lambda m: log.info("%s", str(m).replace(
                _segredo_web("BAP_WEB_TOKEN", "token") or "\0", "***")))
        pacote = montar_pacote_web(
            resultados, hoje.year, hoje.month, hoje, cobranca=cobranca,
            parciais=parciais_web(PASTA_LOCAL, hoje.date(), log=lambda m:
                                  log.warning("%s", m)),
            csvs=csvs_importar_web(PASTA_LOCAL, hoje.date(), log=lambda m:
                                   log.warning("%s", m)),
            cortar=False)           # T-0035: corta no envio (por farol ou global)
        tam = len(json.dumps(pacote, ensure_ascii=False).encode("utf-8"))
        if simular_pacote:
            pasta = Path(tempfile.gettempdir()) / "BAP_PACOTE_WEB"
            pasta.mkdir(parents=True, exist_ok=True)
            arq = pasta / f"pacote_web_{hoje.year}{hoje.month:02d}.json"
            arq.write_text(json.dumps(_cortar_pacote_web(pacote),
                                      ensure_ascii=False), encoding="utf-8")
            log.info("Pacote web simulado gravado em %s (%d KB).", arq,
                     tam // 1024)
            lote = gravar_lote_simulado_web(pacote, pasta)
            return {"simulado": str(arq), "kb": tam // 1024, "lote": lote}
        ok = enviar_pacote(pacote, log=log.info)
        return {"enviado": ok, "kb": tam // 1024}
    except Exception as erro:                           # noqa: BLE001
        log.warning("Pacote web (4f): %s", erro)
        return {"erro": str(erro)}


def gerar_acompanhamento_pos_venda(caminho_planilha: Path,
                                   simular: bool = False) -> dict:
    """
    Acrescenta no ACOMPANHAMENTO_POS_VENDA as notas de venda e de devolucao
    que ainda nao tem linha. Linha que ja existe nao e tocada - e da
    assistente.

    Grava numa copia e so entao troca o arquivo, como a SOLICITACAO_BAP: se
    alguem estiver com ele travado no Excel, a versao pronta fica ao lado
    com NAO_GRAVADO no nome e a proxima rodada reencontra tudo pela chave.
    """
    if not GERAR_POS_VENDA:
        return {}
    log.info("Atualizando o %s...", ARQUIVO_POS_VENDA)
    try:
        if str(PASTA_LOCAL) not in sys.path:
            sys.path.insert(0, str(PASTA_LOCAL))
        import pos_venda as _pv               # noqa: PLC0415
    except Exception as erro:                 # noqa: BLE001
        log.error("NAO DA PARA ATUALIZAR O %s: nao achei o pos_venda.py na "
                  "pasta (%s).", ARQUIVO_POS_VENDA, erro)
        return {"erro": f"pos_venda.py ausente: {erro}",
                "arquivo": ARQUIVO_POS_VENDA}
    try:
        desde = datetime.strptime(INICIO_POS_VENDA, "%Y-%m-%d").date()
    except ValueError:
        desde = _pv.INICIO_PADRAO
    nome = ("SIMULACAO_" + ARQUIVO_POS_VENDA) if simular else ARQUIVO_POS_VENDA
    oficial = PASTA_RELATORIOS / nome
    local = PASTA_TEMP / nome
    diario = _pv.pasta_do_diario(PASTA_RELATORIOS / ARQUIVO_POS_VENDA)
    # (09/10) so a maquina dona grava o arquivo: outra maquina com a copia do
    # OneDrive atrasada trocava o arquivo pela versao velha e as edicoes da
    # assistente sumiam. Aqui ela so le - o que for editado no BAP vai para
    # o diario e entra na proxima rodada da dona
    if not simular and not _pv.pode_gravar_aqui():
        log.info("  o %s e gravado so pela %s (esta e a %s): aqui nao mexo "
                 "nele.", nome, _pv.MAQUINA_DO_POS_VENDA, _pv.maquina())
        return {"arquivo": nome, "pulado": "outra maquina"}
    for _tentativa in range(3):
        try:
            PASTA_TEMP.mkdir(parents=True, exist_ok=True)
            marca = oficial.stat().st_mtime_ns if oficial.exists() else None
            if oficial.exists():
                shutil.copy2(oficial, local)
            elif local.exists():
                local.unlink()
            passo = _pv.atualizar_arquivo(caminho_planilha, local, desde,
                                          pasta_config=PASTA_LOCAL)
            wb = passo["wb"]
            colhidas = 0
            if not simular:
                # o que a assistente mudou direto no Excel vai para o diario
                # ANTES de qualquer coisa
                colhidas = _pv.colher_do_excel(
                    wb, diario, _pv._quando_do_arquivo(oficial))  # noqa: SLF001
            restauradas = _pv.aplicar_diario(wb, diario)
            # (11/10) a aba PRAZOS segue o SLA do BAP Analista; PRAZOS e
            # Listas protegidas (parametro e do analista)
            prazos_ = _pv.sincronizar_prazos(wb, PASTA_LOCAL)
            foto = _pv.foto_do_arquivo(wb)
            mudou = (passo["novo"] or passo["entregas"] or passo["devolucoes"]
                     or restauradas or prazos_)
            if not mudou:
                wb.close()
                if not simular:
                    _pv.guardar_leitura(diario, foto)
                log.info("  nada novo%s - o arquivo nao foi tocado.",
                         f" ({colhidas} edicao(oes) do Excel guardada(s) no "
                         f"diario)" if colhidas else "")
                return {"arquivo": nome, "entregas_novas": 0,
                        "devolucoes_novas": 0, "criado": False,
                        "restauradas": 0, "colhidas": colhidas}
            wb.save(local)
            wb.close()
        except Exception as erro:             # noqa: BLE001
            log.error("Nao consegui montar o %s: %s", nome, erro)
            log.debug("", exc_info=True)
            return {"erro": str(erro), "arquivo": nome}
        # alguem salvou (Excel online, OneDrive) enquanto eu montava? refaz
        # em cima da versao nova - nunca troca por cima de edicao recente
        if (oficial.stat().st_mtime_ns if oficial.exists() else None) == marca:
            break
        log.warning("  o %s mudou enquanto eu montava - refazendo em cima da "
                    "versao nova.", nome)
    else:
        log.error("O %s mudou 3 vezes seguidas enquanto eu montava: nao "
                  "gravei (nada se perdeu - fica para a proxima rodada).", nome)
        return {"erro": "arquivo mudando durante a montagem", "arquivo": nome}

    if oficial.exists():
        try:
            gaveta = PASTA_LOCAL / SUBPASTA_BACKUP / "POS_VENDA"
            gaveta.mkdir(parents=True, exist_ok=True)
            shutil.copy2(oficial, gaveta /
                         f"{oficial.stem}_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
            copias = sorted(gaveta.glob(f"{oficial.stem}_*.xlsx"))
            for velha in copias[:-200]:       # guarda as 200 mais recentes
                velha.unlink()
        except OSError as erro:
            log.warning("  nao consegui guardar a copia de seguranca do %s: "
                         "%s", nome, erro)
    try:
        # (05/11) aberto no Excel: o aviso antes; sem resposta, NAO_GRAVADO
        if aguardar_arquivo_livre(oficial, f"gravar o {nome}") != "livre":
            raise PermissionError(f"{nome} em aberto")
        os.replace(local, oficial)
    except Exception as erro:                 # noqa: BLE001
        reserva = (PASTA_LOCAL /
                   f"NAO_GRAVADO_{datetime.now():%Y%m%d_%H%M}_{nome}")
        shutil.copy2(local, reserva)
        log.error("Nao consegui gravar o %s: %s", nome, erro)
        log.error("Provavelmente alguem esta com ele aberto no Excel. A versao "
                  "completa ficou em %s", reserva)
        return {"erro": f"gravacao bloqueada: {erro}", "arquivo": nome,
                "copia_de_seguranca": str(reserva)}
    if not simular:
        _pv.guardar_leitura(diario, foto)
    if restauradas:
        log.warning("  %d campo(s) editado(s) pela assistente voltaram do "
                    "diario (o arquivo tinha sido trocado por uma versao "
                    "velha ou editado em outra maquina).", restauradas)
    log.info("  +%d entrega(s) e +%d devolucao(oes) novas%s",
             passo["entregas"], passo["devolucoes"],
             " (arquivo criado agora)" if passo["novo"] else "")
    # SITUACAO, DIAS e o PAINEL sao formula: sem recalcular, ficam vazios
    # para quem le o arquivo sem o Excel
    recalcular_com_excel(oficial, nome)
    return {"arquivo": nome, "entregas_novas": passo["entregas"],
            "devolucoes_novas": passo["devolucoes"], "criado": passo["novo"],
            "restauradas": restauradas, "colhidas": colhidas}


def _classificacao_do_catalogo(categoria_antiga):
    """(15/10) f(produto, fornecedor, descricao) -> {CATEGORIA, SISTEMA,
    FAMILIA, LINHA} do Catalogo BAP 2026 (BASE_BAP_UNIFICADA v8).
    Produto fora da base: a regra antiga convertida (catalogo_bap)."""
    try:
        import catalogo_bap as cb                       # noqa: PLC0415
        cat = cb.Catalogo(PASTA_LOCAL, usar_estoque=False)
    except Exception as erro:                           # noqa: BLE001
        log.warning("Catalogo BAP indisponivel (%s): CATEGORIA antiga.", erro)
        return lambda p, f, d: {"CATEGORIA": categoria_antiga(p, f, d)}
    if not cat.base:
        log.warning("BASE_BAP_UNIFICADA_PRODUTOS_BAP.xlsx (v8) nao achada: "
                    "classificacao pela regra antiga.")
    else:
        log.info("Catalogo BAP: %d produtos (%s).", len(cat.base),
                 cat.arq_base.name if cat.arq_base else "")

    def classe(produto, fornecedor, descricao):
        try:
            return cat.de(produto, categoria_antiga(produto, fornecedor,
                                                    descricao), descricao)
        except Exception:                               # noqa: BLE001
            return {"CATEGORIA": categoria_antiga(produto, fornecedor,
                                                  descricao)}
    return classe


def _sucata_da_bateria():
    """f(descricao) -> R$ da sucata daquela bateria (19/10): a mesma tabela
    e a mesma conta do Oportunidades e do Farol de Markup
    (oportunidade_nucleo.valor_da_sucata com o oportunidade_config.json ›
    kit). Sem o modulo ou a tabela, zero (o markup fica como antes)."""
    try:
        if str(PASTA_LOCAL) not in sys.path:
            sys.path.insert(0, str(PASTA_LOCAL))
        import oportunidade_nucleo as on                # noqa: PLC0415
    except Exception as erro:                           # noqa: BLE001
        log.warning("Sucata da bateria indisponivel (%s): markup sem ela.",
                    erro)
        return lambda _d: 0.0
    try:
        kit = (json.loads((PASTA_LOCAL / "oportunidade_config.json")
                          .read_text("utf-8")).get("kit") or {})
    except Exception:                                   # noqa: BLE001
        kit = {}

    def sucata(descricao):
        try:
            return float(on.valor_da_sucata(descricao or "", kit) or 0.0)
        except Exception:                               # noqa: BLE001
            return 0.0
    return sucata


def _categorias_bap_do_estoque():
    """f(produto, fornecedor, descricao) -> CATEGORIA BAP, pela mesma regra
    dos acompanhamentos (meta_nucleo.categoria_bap: CATEGORIAS_PRODUTO.csv
    + fornecedor + descricao). Sem o meta_nucleo na pasta, fica vazio."""
    try:
        import meta_nucleo as mn                        # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        return lambda *_a: ""
    try:
        crua = mn.ler_categoria_crua(mn.achar_csv_de_categorias(PASTA_LOCAL))
    except Exception:                                   # noqa: BLE001
        crua = {}

    def categoria(produto, fornecedor, descricao):
        try:
            return mn.categoria_bap(crua.get(str(produto), ""), fornecedor,
                                    descricao)
        except Exception:                               # noqa: BLE001
            return ""
    return categoria


def gerar_estoque_bap(caminho_planilha: Path, simular: bool = False) -> dict:
    """
    Monta o ESTOQUE_BAP.xlsx: uma linha por FILIAL BAP e produto, com o
    estoque disponivel das lojas PMZ e os precos de capital e interior.

    De onde vem cada coisa:
      CIDADE, FILIAL_BAP     aba Filiais (COD_FILIAL -> FILIAL_BAP -> CIDADE)
      ID_PRODUTO, FORNECEDOR aba ProdutosBAP, pelo 'Cod. Produto'
      COD_PRODUTO, DESCRICAO ftEstoquePMZ / ftTabelaPreco
      ESTOQUE                ftEstoquePMZ: QTD_TOTAL - QTD_SEPARADA, somando
                             todas as lojas da mesma filial BAP
      PRECO_CAPITAL          ftTabelaPreco, tabela da filial terminada em 1
      PRECO_INTERIOR         idem, terminada em 2
      FILIAL_CD              aba Filiais, coluna CD_FILIAL: a loja que e o
                             CD daquela filial BAP
      PPEDIDO                o CUSTO, da ftEstoquePMZ, na linha do CD. O CD
                             nem sempre tem o item - ai vale a media da
                             propria filial e, por ultimo, a da rede
      ORIGEM_CUSTO           CD, FILIAL ou REDE: de onde saiu o PPEDIDO
      MARKUP_CAPITAL         preco de venda / custo - 1, em percentual
      MARKUP_INTERIOR        idem, com o preco de interior

    O arquivo e REESCRITO a cada rodada: e uma foto do momento, nao historico.
    """
    if not GERAR_ESTOQUE_BAP:
        return {}
    log.info("Montando o %s...", ARQUIVO_ESTOQUE_BAP)
    agora = datetime.now()

    precisamos = ["Filiais", "ProdutosBAP", ABA_ESTOQUE_PMZ, ABA_TABELA_PRECO]
    faltando = [a for a in precisamos
                if a not in abas_da_planilha(caminho_planilha)]
    if faltando:
        # ERRO, nao aviso: sem isto o ESTOQUE_BAP para de ser gerado e o
        # resto da rodada segue normal - foi assim que ele ficou nove dias
        # parado sem ninguem notar.
        log.error("NAO DA PARA MONTAR O %s: falta a(s) aba(s) %s na %s.",
                  ARQUIVO_ESTOQUE_BAP, ", ".join(faltando), NOME_PLANILHA)
        log.error("  Abas que a planilha tem: %s",
                  ", ".join(abas_da_planilha(caminho_planilha)))
        return {"erro": f"abas ausentes: {', '.join(faltando)}",
                "arquivo": ARQUIVO_ESTOQUE_BAP}
    calculadas = calculadas_das_abas(caminho_planilha, precisamos)

    wb = _abrir_valores(caminho_planilha)
    try:
        filiais = ler_aba(wb, "Filiais", calculadas=calculadas["Filiais"])
        produtos = ler_aba(wb, "ProdutosBAP",
                           calculadas=calculadas["ProdutosBAP"])
        estoque = ler_aba(wb, ABA_ESTOQUE_PMZ,
                          calculadas=calculadas[ABA_ESTOQUE_PMZ])
        precos = ler_aba(wb, ABA_TABELA_PRECO,
                         calculadas=calculadas[ABA_TABELA_PRECO])
    finally:
        wb.close()

    def achar(tabela, candidatas):
        for candidata in candidatas:
            if normalizar(candidata) in tabela.columns:
                return normalizar(candidata)
        return None

    # ---- filial BAP e cidade --------------------------------------------
    c_cod = normalizar("COD_FILIAL")
    c_bap = normalizar("FILIAL_BAP")
    c_cid = normalizar("CIDADE")
    if c_cod not in filiais.columns or c_bap not in filiais.columns:
        log.error("NAO DA PARA MONTAR O %s: a aba 'Filiais' esta sem "
                  "COD_FILIAL/FILIAL_BAP.", ARQUIVO_ESTOQUE_BAP)
        return {"erro": "Filiais sem COD_FILIAL/FILIAL_BAP",
                "arquivo": ARQUIVO_ESTOQUE_BAP}
    c_cd = normalizar("CD_FILIAL")
    de_loja: dict[str, str] = {}
    cidade_da_bap: dict[str, str] = {}
    cd_da_bap: dict[str, str] = {}
    for _, linha in filiais.iterrows():
        loja, bap = texto(linha.get(c_cod)), texto(linha.get(c_bap))
        if loja and bap:
            de_loja[loja] = bap
        if bap and c_cid in filiais.columns:
            cidade_da_bap.setdefault(bap, texto(linha.get(c_cid)))
        # o CD e quem manda no CUSTO: e o preco de pedido dele que vale
        # para a filial BAP inteira
        if bap and c_cd in filiais.columns:
            cd = texto(linha.get(c_cd))
            if cd:
                cd_da_bap.setdefault(bap, cd)

    # ---- ID_PRODUTO e fornecedor ----------------------------------------
    c_id = achar(produtos, ["ID_PRODUTO"])
    c_forn = achar(produtos, ["FORNECEDOR"])
    c_codpro = achar(produtos, ["Cód. Produto", "COD_PRODUTO", "CODIGO"])
    ficha: dict[str, dict] = {}
    if c_codpro:
        for _, linha in produtos.iterrows():
            codigo = texto(linha.get(c_codpro)).upper()
            if not codigo:
                continue
            bruto = texto(linha.get(c_forn)) if c_forn else ""
            ficha[codigo] = {
                "id": texto(linha.get(c_id)) if c_id else "",
                # "7980 - BAP MOTOS" -> codigo e nome, em colunas separadas
                "cod_fornecedor": bruto.split("-")[0].strip() if bruto else "",
                "fornecedor": (bruto.split("-", 1)[1].strip()
                               if "-" in bruto else bruto),
            }

    # ---- estoque disponivel por filial BAP -------------------------------
    e_fil = achar(estoque, COLS_PMZ_FILIAL)
    e_pro = achar(estoque, ["PRODUTO", "COD_PRODUTO", "B2_COD"])
    e_qtd = achar(estoque, COLS_PMZ_QTDE)
    e_sep = achar(estoque, COLS_PMZ_SEPARADA) if ESTOQUE_PMZ_DESCONTAR_SEPARADA else None
    e_des = achar(estoque, ["DESCRICAO_COMPL", "DESCRICAO", "B1_DESC"])
    e_id = achar(estoque, ["ID_PRODUTO"])
    e_custo = achar(estoque, COLS_PMZ_CUSTO)
    saldo: dict[tuple, float] = {}
    descricao: dict[str, str] = {}
    id_do_estoque: dict[str, str] = {}
    custo_do_cd: dict[tuple, float] = {}    # (filial BAP, produto) -> custo
    custo_da_filial: dict[tuple, list] = {}
    custo_da_rede: dict[str, list] = {}
    if all((e_fil, e_pro, e_qtd)):
        for _, linha in estoque.iterrows():
            bap = de_loja.get(texto(linha.get(e_fil)))
            produto = texto(linha.get(e_pro)).upper()
            if not bap or not produto:
                continue
            try:
                qtd = float(linha.get(e_qtd) or 0)
            except (TypeError, ValueError):
                continue
            if e_sep:
                try:
                    qtd -= float(linha.get(e_sep) or 0)
                except (TypeError, ValueError):
                    pass
            saldo[(bap, produto)] = saldo.get((bap, produto), 0.0) + max(qtd, 0.0)
            if e_custo:
                try:
                    custo = float(linha.get(e_custo) or 0)
                except (TypeError, ValueError):
                    custo = 0.0
                if custo > 0:
                    if cd_da_bap.get(bap) == texto(linha.get(e_fil)):
                        custo_do_cd[(bap, produto)] = custo
                    custo_da_filial.setdefault((bap, produto), []).append(custo)
                    custo_da_rede.setdefault(produto, []).append(custo)
            if e_des and produto not in descricao:
                descricao[produto] = texto(linha.get(e_des))
            if e_id and produto not in id_do_estoque:
                id_do_estoque[produto] = texto(linha.get(e_id))
    else:
        log.error("A aba '%s' esta sem filial/produto/qtde: o %s vai sair "
                  "COM TODO ESTOQUE ZERADO.", ABA_ESTOQUE_PMZ,
                  ARQUIVO_ESTOQUE_BAP)

    # ---- precos: capital (final 1) e interior (final 2) ------------------
    p_fil = achar(precos, COLS_PRECO_FILIAL)
    p_tab = achar(precos, COLS_PRECO_TABELA)
    p_pro = achar(precos, COLS_PRECO_PRODUTO)
    p_val = achar(precos, COLS_PRECO_VALOR)
    p_des = achar(precos, COLS_PRECO_DESCRICAO)
    if not all((p_fil, p_pro, p_val)):
        log.error("NAO DA PARA MONTAR O %s: a aba '%s' esta sem as colunas "
                  "de filial/produto/preco.", ARQUIVO_ESTOQUE_BAP,
                  ABA_TABELA_PRECO)
        return {"erro": f"{ABA_TABELA_PRECO} sem as colunas de preco",
                "arquivo": ARQUIVO_ESTOQUE_BAP}

    def filial_longa(valor) -> str:
        bruto = texto(valor)
        return "4" + bruto if bruto.startswith("0101") and len(bruto) == 7 else bruto

    preco_capital: dict[tuple, tuple] = {}    # (filial, produto) -> (tab, valor)
    preco_interior: dict[tuple, tuple] = {}
    for _, linha in precos.iterrows():
        bap = filial_longa(linha.get(p_fil))
        produto = texto(linha.get(p_pro)).upper()
        if not bap or not produto:
            continue
        try:
            valor = float(linha.get(p_val) or 0)
        except (TypeError, ValueError):
            continue
        if valor <= 0:
            continue
        tabela = texto(linha.get(p_tab)) if p_tab else ""
        destino = (preco_capital if tabela.endswith(FINAL_TABELA_CAPITAL)
                   else preco_interior if tabela.endswith(FINAL_TABELA_INTERIOR)
                   else None)
        if destino is None:
            continue
        destino[(bap, produto)] = (tabela, round(valor, 4))
        if p_des and produto not in descricao:
            descricao[produto] = texto(linha.get(p_des))

    # ---- monta as linhas --------------------------------------------------
    chaves = set(preco_capital) | set(preco_interior)
    if not ESTOQUE_BAP_SOMENTE_COM_ESTOQUE:
        chaves |= set(saldo)
    else:
        chaves = {c for c in chaves if saldo.get(c, 0.0) > 0}

    def markup(preco, custo):
        """Quanto o preco esta acima do custo, em %. Sem custo, nao da."""
        if not preco or not custo:
            return None
        return round((float(preco) / float(custo) - 1.0) * 100.0, 2)

    data, hora = agora.strftime("%d/%m/%Y"), agora.strftime("%H:%M")
    linhas = []
    sem_ficha = set()
    classe_de = _classificacao_do_catalogo(_categorias_bap_do_estoque())
    sucata_de = _sucata_da_bateria()
    for bap, produto in sorted(chaves):
        dados = ficha.get(produto)
        if dados is None:
            sem_ficha.add(produto)
            dados = {"id": id_do_estoque.get(produto, ""),
                     "cod_fornecedor": "", "fornecedor": ""}
        capital = preco_capital.get((bap, produto))
        interior = preco_interior.get((bap, produto))
        # o custo e o do CD; sem ele, a media da propria filial e, em
        # ultimo caso, a da rede - a coluna ORIGEM_CUSTO diz qual foi
        custo, origem = custo_do_cd.get((bap, produto), 0.0), "CD"
        if not custo and custo_da_filial.get((bap, produto)):
            lista = custo_da_filial[(bap, produto)]
            custo, origem = sum(lista) / len(lista), "FILIAL"
        if not custo and custo_da_rede.get(produto):
            lista = custo_da_rede[produto]
            custo, origem = sum(lista) / len(lista), "REDE"
        if not custo:
            origem = ""
        classe = classe_de(produto, dados["fornecedor"],
                           descricao.get(produto, ""))
        # (19/10) BATERIA: custo de verdade = P. PEDIDO + sucata
        sucata = sucata_de(descricao.get(produto, "")) if custo and \
            classe.get("CATEGORIA") in ("BATERIAS", "BATERIA") else 0.0
        custo_total = custo + sucata if custo else 0.0
        linhas.append({
            "DATA": data, "HORA": hora,
            "CIDADE": cidade_da_bap.get(bap, ""),
            "FILIAL_BAP": bap,
            "ID_PRODUTO": dados["id"] or id_do_estoque.get(produto, ""),
            "COD_FORNECEDOR": dados["cod_fornecedor"],
            "FORNECEDOR": dados["fornecedor"],
            "COD_PRODUTO": produto,
            "DESCRICAO_PRODUTO": descricao.get(produto, ""),
            "ESTOQUE": round(saldo.get((bap, produto), 0.0), 2),
            "FILIAL_CD": cd_da_bap.get(bap, ""),
            "PPEDIDO": round(custo, 4) if custo else None,
            "ORIGEM_CUSTO": origem,
            "TABELA_CAPITAL": capital[0] if capital else "",
            "PRECO_CAPITAL": capital[1] if capital else None,
            "TABELA_INTERIOR": interior[0] if interior else "",
            "PRECO_INTERIOR": interior[1] if interior else None,
            # MARKUP = preco de venda / custo total - 1, em percentual
            # (custo total = P. PEDIDO + sucata na bateria)
            "MARKUP_CAPITAL": markup(capital[1] if capital else None,
                                     custo_total),
            "MARKUP_INTERIOR": markup(interior[1] if interior else None,
                                      custo_total),
            **classe,
            "SUCATA": round(sucata, 2) if sucata else None,
            "CUSTO_TOTAL": round(custo_total, 4) if custo_total else None,
        })

    # ---- grava (o arquivo e uma foto: reescrito a cada rodada) ------------
    nome = ("SIMULACAO_" + ARQUIVO_ESTOQUE_BAP) if simular else ARQUIVO_ESTOQUE_BAP
    destino = PASTA_RELATORIOS / nome
    wb = Workbook()
    ws = wb.active
    ws.title = ABA_ESTOQUE_BAP
    ws.append(COLUNAS_ESTOQUE_BAP)
    for registro in linhas:
        ws.append([registro.get(c) for c in COLUNAS_ESTOQUE_BAP])
    estilo_do_cabecalho(ws, len(COLUNAS_ESTOQUE_BAP))
    ws.freeze_panes = "A2"
    if len(linhas):
        ws.auto_filter.ref = (f"A1:{get_column_letter(len(COLUNAS_ESTOQUE_BAP))}"
                              f"{len(linhas) + 1}")
    for indice, largura in enumerate(
            (11, 7, 14, 13, 30, 15, 16, 18, 52, 11, 15, 14, 16, 15, 14, 16,
             14, 12, 12, 14, 16, 30, 14, 10, 12), start=1):
        ws.column_dimensions[get_column_letter(indice)].width = largura
    for linha in range(2, len(linhas) + 2):
        estilo_da_linha(ws, linha, len(COLUNAS_ESTOQUE_BAP))
        for coluna in (10,):                      # ESTOQUE
            ws.cell(linha, coluna).number_format = '#,##0'
        for coluna in (12, 14):                   # os dois precos
            ws.cell(linha, coluna).number_format = '#,##0.00'
        for nome_c in ("SUCATA", "CUSTO_TOTAL"):  # (19/10)
            ws.cell(linha, COLUNAS_ESTOQUE_BAP.index(nome_c) + 1
                    ).number_format = '#,##0.00'

    try:
        # (05/11) aberto no Excel: o aviso antes de gravar por cima
        if aguardar_arquivo_livre(destino, f"gravar o {nome}") != "livre":
            raise PermissionError(f"{nome} em aberto (pulado)")
        wb.save(destino)
    except Exception as erro:
        log.error("Nao consegui gravar o %s: %s", nome, erro)
        log.error("Provavelmente alguem esta com ele aberto no Excel.")
        return {"arquivo": nome, "linhas": 0, "erro": str(erro)}
    finally:
        wb.close()

    com_estoque = sum(1 for l in linhas if l["ESTOQUE"] > 0)
    log.info("  %d linha(s) | %d com estoque | %d filiais | %d produtos",
             len(linhas), com_estoque,
             len({l["FILIAL_BAP"] for l in linhas}),
             len({l["COD_PRODUTO"] for l in linhas}))
    if sem_ficha:
        log.info("  %d produto(s) sem cadastro no ProdutosBAP (ID e fornecedor "
                 "em branco).", len(sem_ficha))
    # Estoque parado sem preco na propria filial e dinheiro que nao pode ser
    # vendido ali: vale aparecer no log.
    sem_preco = sum(1 for l in linhas
                    if l["ESTOQUE"] > 0 and not l["PRECO_CAPITAL"]
                    and not l["PRECO_INTERIOR"])
    if sem_preco:
        log.warning("  %d linha(s) tem ESTOQUE mas NENHUM preco cadastrado na "
                    "filial - filtre por PRECO_CAPITAL vazio para ver.",
                    sem_preco)
    log.info("  gravado em %s", destino)
    return {
        "arquivo": nome,
        "linhas": len(linhas),
        "com_estoque": com_estoque,
        "filiais": len({l["FILIAL_BAP"] for l in linhas}),
        "produtos": len({l["COD_PRODUTO"] for l in linhas}),
        "sem_cadastro": len(sem_ficha),
        "com_estoque_sem_preco": sem_preco,
    }


ARQUIVO_RESUMO = "ultimo_resumo.json"


def guardar_resumo(resumo: dict) -> None:
    """
    Grava o resultado da execucao em JSON. E o que a janela grafica le para
    montar o painel final, e serve de registro da ultima execucao.
    """
    try:
        caminho = PASTA_LOCAL / ARQUIVO_RESUMO
        caminho.write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as erro:
        log.debug("Nao consegui gravar o resumo: %s", erro)


# Rodado num processo separado, para poder ser abandonado se o Excel travar.
SCRIPT_RECALCULO = r"""
import sys
import win32com.client as com

caminho = sys.argv[1]
excel = None
livro = None
try:
    # DispatchEx abre uma instancia SO nossa: nao mexe no Excel que a pessoa
    # ja tenha aberto, e nao esbarra em arquivo de mesmo nome.
    excel = com.DispatchEx("Excel.Application")
    # (05/11) o numero do processo DESTE Excel: se ele travar, o robo
    # encerra so ele
    if len(sys.argv) > 2:
        try:
            import win32process
            _, pid = win32process.GetWindowThreadProcessId(excel.Hwnd)
            with open(sys.argv[2], "w", encoding="utf-8") as f:
                f.write(str(pid))
        except Exception:
            pass
    excel.Visible = False
    excel.DisplayAlerts = False
    excel.AskToUpdateLinks = False
    excel.EnableEvents = False
    livro = excel.Workbooks.Open(caminho, UpdateLinks=0, ReadOnly=False)
    excel.CalculateFullRebuild()
    livro.Save()
    print("recalculado")
finally:
    try:
        if livro is not None:
            livro.Close(SaveChanges=False)
    except Exception:
        pass
    try:
        if excel is not None:
            excel.Quit()
    except Exception:
        pass
"""


def e_windows() -> bool:
    return os.name == "nt"


# (05/11) True durante uma rodada do robo (executar): ai o Cancelar do aviso
# interrompe a rodada. Fora dela (a troca de loja do BAP Central chama o
# recalculo) o Cancelar so pula o passo.
RODADA_EM_ANDAMENTO = False
RodadaCancelada = aviso_arquivo.Cancelado


def aguardar_arquivo_livre(caminho: Path, passo: str, verificar=None) -> str:
    """
    O arquivo esta aberto (no Excel desta ou de outra maquina)? Mostra o
    aviso Continuar / Cancelar ate ele ficar livre. "livre" = pode seguir;
    "pular" = ninguem respondeu (ou nao ha tela): pule so este passo.
    Cancelar levanta RodadaCancelada (durante uma rodada).
    """
    return aviso_arquivo.aguardar_livre(
        caminho, passo, log=log, espera=ESPERA_POPUP_ARQUIVO,
        verificar=verificar, cancelar_interrompe=RODADA_EM_ANDAMENTO)


def _encerrar_excel_preso(arq_pid: Path, rotulo: str,
                          caminho: Path | None = None) -> bool:
    """Encerra SO o EXCEL.EXE que o script de recalculo abriu (o numero do
    processo que ele anotou) - nunca outro Excel da maquina."""
    try:
        pid = int(arq_pid.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        log.warning("  nao achei o numero do Excel do recalculo de %s: "
                    "CONFIRA se sobrou um EXCEL.EXE preso no Gerenciador de "
                    "Tarefas.", rotulo)
        return False
    try:
        r = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess,
                                                 "CREATE_NO_WINDOW", 0))
        ok = r.returncode == 0
    except Exception as erro:                           # noqa: BLE001
        log.warning("  nao consegui encerrar o Excel %d: %s", pid, erro)
        return False
    if ok:
        log.warning("  o Excel do recalculo (processo %d) foi encerrado.", pid)
        # (05/11, revisor) o Excel encerrado a forca deixa o ~$ do arquivo:
        # sem apagar, o aviso de arquivo em aberto voltava em toda rodada
        if caminho is not None and aviso_arquivo.apagar_dono_solto(caminho):
            log.info("  o ~$%s que ele deixou foi apagado.", caminho.name)
    else:
        log.warning("  taskkill do Excel %d nao deu: %s", pid,
                    (r.stderr or r.stdout or "").strip()[:200])
    return ok


def recalcular_com_excel(caminho: Path, descricao: str = "") -> bool:
    """
    Abre o Excel invisivel, recalcula tudo e salva. Devolve True se conseguiu.
    Falhar aqui nunca derruba a rotina: os dados ja estao gravados, so os
    valores das formulas e que ficam para a proxima abertura no Excel.
    """
    if not RECALCULAR_FORMULAS:
        return False
    caminho = Path(caminho)
    if not caminho.exists():
        return False
    if not e_windows():
        log.debug("Recalculo com Excel so existe no Windows.")
        return False

    rotulo = descricao or caminho.name
    # (05/11) aberto no Excel: o recalculo ficava preso ate o TIMEOUT
    if aguardar_arquivo_livre(caminho, f"o recalculo de {rotulo}") != "livre":
        log.warning("  %s NAO foi recalculado nesta rodada (em aberto): as "
                    "formulas ficam para quando alguem abrir no Excel.",
                    rotulo)
        return False
    script = PASTA_TEMP / "_recalcular.py"
    arq_pid = PASTA_TEMP / f"_recalcular_{os.getpid()}.pid"
    try:
        PASTA_TEMP.mkdir(parents=True, exist_ok=True)
        script.write_text(SCRIPT_RECALCULO, encoding="utf-8")
    except Exception as erro:
        log.warning("Nao consegui preparar o recalculo: %s", erro)
        return False

    log.info("Recalculando as formulas de %s no Excel...", rotulo)
    inicio = time.time()
    try:
        arq_pid.unlink(missing_ok=True)
        saida = subprocess.run(
            [sys.executable, str(script), str(caminho), str(arq_pid)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=TIMEOUT_RECALCULO,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        log.warning("  o Excel passou de %ds recalculando %s e foi abandonado.",
                    TIMEOUT_RECALCULO, rotulo)
        _encerrar_excel_preso(arq_pid, rotulo, caminho)
        return False
    except Exception as erro:
        log.warning("  nao consegui chamar o Excel: %s", erro)
        return False
    finally:
        script.unlink(missing_ok=True)
        arq_pid.unlink(missing_ok=True)

    if saida.returncode == 0:
        log.info("  formulas de %s recalculadas em %.1f s", rotulo,
                 time.time() - inicio)
        return True

    erro = (saida.stderr or saida.stdout or "").strip().splitlines()
    ultimo = erro[-1][:200] if erro else "sem detalhe"
    if "win32com" in (saida.stderr or "") or "No module named" in (saida.stderr or ""):
        log.warning("  falta a biblioteca pywin32 para conversar com o Excel.")
        log.warning("  Instale uma vez:  pip install pywin32")
    else:
        log.warning("  o Excel nao recalculou %s: %s", rotulo, ultimo)
    log.warning("  As formulas continuam la e serao calculadas quando alguem "
                "abrir a planilha no Excel.")
    return False


def rodar_script_final(resumo: dict) -> None:
    """
    Chama SCRIPT_FINAL depois que tudo ja foi gravado. Falha aqui NUNCA derruba
    a automacao nem desfaz o que foi feito: a planilha ja esta salva.
    """
    if not SCRIPT_FINAL:
        return

    alvo = Path(SCRIPT_FINAL)
    if not alvo.is_absolute():
        alvo = PASTA_LOCAL / alvo        # relativo = ao lado do bap_automation
    if not alvo.exists():
        log.warning("SCRIPT_FINAL nao encontrado: %s", alvo)
        return

    if SCRIPT_FINAL_SO_SE_TUDO_OK and resumo.get("status") != "sucesso":
        log.warning("Rodada com pendencias (%s): nao vou chamar o %s.",
                    resumo.get("status"), alvo.name)
        return

    caminho_resumo = str(PASTA_LOCAL / "ultimo_resumo.json")
    sufixo = alvo.suffix.lower()
    if sufixo == ".py":
        comando = [sys.executable, str(alvo), caminho_resumo]
    elif sufixo == ".ps1":
        comando = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", str(alvo), caminho_resumo]
    else:                                    # .bat, .cmd, .exe
        comando = [str(alvo), caminho_resumo]

    log.info("Chamando o script final: %s", alvo.name)
    try:
        saida = subprocess.run(
            comando, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TIMEOUT_SCRIPT_FINAL, cwd=str(PASTA_LOCAL))
    except subprocess.TimeoutExpired:
        log.warning("  o script final passou de %ds e foi abandonado.",
                    TIMEOUT_SCRIPT_FINAL)
        return
    except Exception as erro:
        log.warning("  nao consegui rodar o script final: %s", erro)
        return

    for linha in ((saida.stdout or "") + (saida.stderr or "")).splitlines():
        if linha.strip():
            log.info("  [%s] %s", alvo.stem, linha.rstrip()[:300])
    if saida.returncode == 0:
        log.info("  script final concluido.")
    else:
        log.warning("  script final terminou com codigo %d.", saida.returncode)


def _rodar_bap_ajuda(comando, pasta: Path, env: dict, timeout: int):
    """Roda um passo do BAP Ajuda sem janela; devolve (codigo, saida)."""
    extra = {}
    if e_windows():
        extra["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
    r = subprocess.run(comando, cwd=str(pasta), env=env, input="\n",
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, **extra)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def sincronizar_bap_ajuda() -> dict:
    """
    (27/10, Alexandre) Fim da rodada: roda o sincronizar_bap.py do BAP Ajuda
    2.0 (envia estoque/carteira/base para o app e baixa as respostas do app).
    Se a sincronizacao falhar antes de baixar as respostas (ex.: o GitHub
    recusou o envio), roda so a etapa das respostas. NUNCA levanta erro: o
    resultado vai para o log, para BAP Ajuda 2.0 > ultima_sincronizacao.log e
    para o ultimo_resumo.json.
    """
    import re as _re
    res = {"rodou": False, "codigo": None, "respostas": "", "log": ""}
    if not SINCRONIZAR_BAP_AJUDA:
        return res
    pasta = PASTA_LOCAL / PASTA_BAP_AJUDA
    script = pasta / "sincronizar_bap.py"
    if not (script.exists() and (pasta / "config.json").exists()):
        log.info("BAP Ajuda: sincronizacao pulada (falta %s ou config.json).",
                 script.name)
        res["motivo"] = "sem sincronizar_bap.py ou config.json"
        return res
    trava = pasta / TRAVA_BAP_AJUDA
    try:
        if trava.exists() and (time.time() - trava.stat().st_mtime
                               < TRAVA_BAP_AJUDA_MINUTOS * 60):
            log.warning("BAP Ajuda: outra maquina esta sincronizando (%s); "
                        "pulei desta vez.", trava.read_text("utf-8",
                                                            "replace")[:80])
            res["motivo"] = "outra maquina sincronizando"
            return res
        trava.write_text(f"{os.environ.get('COMPUTERNAME', '?')} "
                         f"{datetime.now():%d/%m/%Y %H:%M}", "utf-8")
    except OSError:
        pass
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if e_windows() and os.path.isdir(GIT_PADRAO_WINDOWS) and \
            GIT_PADRAO_WINDOWS.lower() not in env.get("PATH", "").lower():
        env["PATH"] = GIT_PADRAO_WINDOWS + os.pathsep + env.get("PATH", "")
    saida = ""
    log.info("BAP Ajuda: sincronizando o app (estoque, carteira, base e "
             "respostas)...")
    try:
        cod, saida = _rodar_bap_ajuda([sys.executable, str(script)], pasta,
                                      env, TIMEOUT_BAP_AJUDA)
        res.update(rodou=True, codigo=cod)
        if "RESPOSTAS_BAP_AJUDA" not in saida and "respostas" not in \
                saida.lower():
            # o script parou antes de baixar as respostas (ex.: GitHub
            # recusou o envio): baixa so as respostas
            cod2, saida2 = _rodar_bap_ajuda(
                [sys.executable, "-c",
                 "import json, sincronizar_bap as s; "
                 "s.etapa_respostas(json.load(open('config.json', "
                 "encoding='utf-8')).get('github_token'))"],
                pasta, env, 300)
            saida += "\n--- so as respostas do app ---\n" + saida2
            res["codigo_respostas"] = cod2
    except subprocess.TimeoutExpired:
        log.warning("BAP Ajuda: a sincronizacao passou de %ds e foi "
                    "abandonada.", TIMEOUT_BAP_AJUDA)
        res["motivo"] = "tempo esgotado"
    except Exception as erro:                       # noqa: BLE001
        log.warning("BAP Ajuda: a sincronizacao nao rodou: %s", erro)
        res["motivo"] = str(erro)
    finally:
        try:
            trava.unlink()
        except OSError:
            pass
    limpa = _re.sub(r"\x1b\[[0-9;]*m", "", saida)
    try:
        (pasta / "ultima_sincronizacao.log").write_text(
            f"{datetime.now():%d/%m/%Y %H:%M} em "
            f"{os.environ.get('COMPUTERNAME', '?')}\n{limpa}", "utf-8")
        res["log"] = str(pasta / "ultima_sincronizacao.log")
    except OSError:
        pass
    m = _re.findall(r"RESPOSTAS_BAP_AJUDA[^:\n]*\.xlsx: ([^\n]+)", limpa)
    res["respostas"] = m[-1].strip() if m else ""
    if res.get("codigo") == 0:
        log.info("BAP Ajuda: sincronizado%s.",
                 f" | respostas: {res['respostas']}" if res["respostas"]
                 else "")
    elif res.get("rodou"):
        log.warning("BAP Ajuda: o envio para o app FALHOU (codigo %s) - ver "
                    "BAP Ajuda 2.0\\ultima_sincronizacao.log%s",
                    res["codigo"], f" | respostas baixadas: "
                    f"{res['respostas']}" if res["respostas"] else "")
    return res


def avisar_power_automate(resumo: dict) -> None:
    """
    Envia o resultado para um fluxo do Power Automate (gatilho HTTP), que pode
    entao atualizar o dataset do Power BI, avisar no Teams, etc.
    Falha aqui nunca derruba a automacao: a planilha ja foi gravada.
    """
    if not URL_WEBHOOK_FINAL:
        return
    try:
        import requests
        resposta = requests.post(URL_WEBHOOK_FINAL, json=resumo, timeout=60)
        if resposta.status_code >= 400:
            log.warning("Power Automate respondeu %s: %s",
                        resposta.status_code, resposta.text[:200])
        else:
            log.info("Aviso enviado ao Power Automate (%s).", resposta.status_code)
    except Exception as erro:
        log.warning("Nao consegui avisar o Power Automate: %s", erro)


def modo_configurar_nuvem() -> int:
    if MODO_NUVEM.lower() != "graph":
        print("\nMODO_NUVEM = 'local': nao existe login da Microsoft a configurar.")
        print("O script usa a pasta do OneDrive sincronizada nesta maquina.\n")
        return modo_checagem()

    print("\nConectando na Microsoft (isso pode pedir um codigo no navegador)...\n")
    armazenamento = criar_armazenamento(interativo=True)
    print("\n" + "=" * 70)
    print("  CONEXAO OK")
    print("=" * 70)
    print(f"  Conta ......... {getattr(armazenamento, 'usuario', '-')}")
    print(f"  Planilha ...... {NOME_PLANILHA} (encontrada)")
    print(f"  Downloads ..... {SUBPASTA_DOWNLOADS} (pronta)")
    print(f"  Token salvo ... {CACHE_MSAL}")
    print("\n  Nas proximas execucoes nao havera login manual.")
    print("  Proximo passo:  python bap_automation.py --checar\n")
    return 0


def modo_checagem() -> int:
    log.info("=" * 70)
    log.info("CHECAGEM DE AMBIENTE")
    log.info("=" * 70)

    armazenamento = criar_armazenamento()
    if getattr(armazenamento, "planilha", None):
        log.info("Arquivo em uso : %s", armazenamento.planilha)
        log.info("Separacao      : %s", armazenamento.pasta_separacao)
        log.info("Backups        : %s", PASTA_BACKUPS)
    abas = armazenamento.abas_da_planilha()
    log.info("Abas encontradas em %s: %s", NOME_PLANILHA, abas)

    faltando = [r["aba_excel"] for r in RELATORIOS if r["aba_excel"] not in abas
                and not r.get("criar_aba")]
    for r in RELATORIOS:
        marca = "OK " if r["aba_excel"] in abas else (
            "NOV" if r.get("criar_aba") else "NAO")
        log.info("  [%s] %-38s -> %s", marca, r["nome_site"], r["aba_excel"])

    if faltando:
        log.error("Abas ausentes: %s", faltando)
        return 1

    log.info("Tudo certo. Proximo passo: python bap_automation.py --descobrir")
    return 0


def modo_solicitacao(simular: bool) -> int:
    """Gera a solicitacao de coleta a partir da planilha como ela esta agora."""
    log.info("=" * 70)
    log.info("SOLICITACAO DE COLETA (sem baixar relatorios)")
    log.info("=" * 70)
    limpar_temporarios()
    armazenamento = criar_armazenamento()
    copia = PASTA_TEMP / NOME_PLANILHA
    planilha = getattr(armazenamento, "planilha", None)
    if planilha and dados_bap.fotografia_para(planilha) is not None:
        # (05/11) a copia da TABELA_BAP pode estar com o dado da rodada
        # completa: o dado de agora vem pela fotografia
        fonte = Path(planilha)
    else:
        armazenamento.baixar_planilha(copia)
        fonte = copia
    resultado = gerar_solicitacao(fonte, armazenamento, simular)
    alvo = fonte if fonte.exists() else Path(armazenamento.planilha)
    if COMPARAR_TABELA_PRECO:
        try:
            acompanhar_tabela_de_preco(alvo, simular)
        except Exception as erro:
            log.error("Nao consegui comparar a tabela de preco: %s", erro)
            log.debug("", exc_info=True)
    if GERAR_ESTOQUE_BAP:
        try:
            passo = gerar_estoque_bap(alvo, simular)
            if passo.get("erro"):
                log.error("O %s NAO foi atualizado: %s", ARQUIVO_ESTOQUE_BAP,
                          passo["erro"])
        except Exception as erro:
            log.error("Nao consegui montar o %s: %s", ARQUIVO_ESTOQUE_BAP, erro)
            log.debug("", exc_info=True)
    if GERAR_BASE_CLIENTE:
        try:
            passo = gerar_base_cliente_bap(alvo, simular)
            if passo.get("erro"):
                log.error("A %s NAO foi atualizada: %s", ARQUIVO_BASE_CLIENTE,
                          passo["erro"])
        except Exception as erro:
            log.error("Nao consegui montar a %s: %s", ARQUIVO_BASE_CLIENTE,
                      erro)
            log.debug("", exc_info=True)
    if GERAR_POS_VENDA:
        try:
            passo = gerar_acompanhamento_pos_venda(alvo, simular)
            if passo.get("erro"):
                log.error("O %s NAO foi atualizado: %s", ARQUIVO_POS_VENDA,
                          passo["erro"])
        except Exception as erro:
            log.error("Nao consegui atualizar o %s: %s", ARQUIVO_POS_VENDA,
                      erro)
            log.debug("", exc_info=True)
    try:
        gerar_dados_relatorios(simular)
    except Exception as erro:
        log.error("Nao consegui preparar os dados dos relatorios: %s", erro)
        log.debug("", exc_info=True)
    limpar_temporarios()
    # Zero linha nova NAO e erro: quer dizer que todo pedido em aberto ja esta
    # atendido. Erro e so o que impediu a rodada de terminar.
    if resultado.get("erro"):
        return 1
    # excesso herdado e aviso; excesso criado agora e defeito.
    if any(not c.get("herdado") for c in resultado.get("excessos", [])):
        return 2
    return 0


def modo_limpar_simulacao() -> int:
    """
    Zera o ambiente de teste: apaga a copia local da solicitacao e os CSVs da
    subpasta SIMULACAO. Nao toca em nada da nuvem nem nos arquivos reais.
    """
    alvos = []
    copia = caminho_da_solicitacao(simular=True)
    if copia.exists():
        copia.unlink()
        alvos.append(str(copia))

    pasta = PASTA_LOCAL / SUBPASTA_IMPORTAR / "SIMULACAO"
    if pasta.is_dir():
        for arquivo in pasta.glob("*.csv"):
            arquivo.unlink()
            alvos.append(arquivo.name)

    simulada = PASTA_LOCAL / f"SIMULACAO_{NOME_PLANILHA}"
    if simulada.exists():
        simulada.unlink()
        alvos.append(simulada.name)

    if alvos:
        log.info("Ambiente de simulacao zerado (%d item(ns)):", len(alvos))
        for nome in alvos:
            log.info("   removido: %s", nome)
    else:
        log.info("Nada de simulacao para limpar.")
    log.info("Os arquivos reais e a nuvem nao foram tocados.")
    return 0


def modo_destravar() -> int:
    armazenamento = criar_armazenamento()
    armazenamento.adquirir_trava(forcar=True)
    armazenamento.liberar_trava()
    log.info("Trava removida.")
    return 0


# =============================================================================
# 8c. A TABELA_BAP SO COMO SAIDA: rodada completa x rodada rapida (05/11)
# =============================================================================

def escolher_rodada(args, armazenamento) -> tuple[str, str]:
    """("completa" | "rapida", o motivo) - ver TABELA_BAP_SO_SAIDA."""
    if not TABELA_BAP_SO_SAIDA:
        return "completa", "TABELA_BAP_SO_SAIDA desligado"
    if getattr(args, "completa", False):
        return "completa", "pedida com --completa"
    if args.simular:
        return "completa", "simulacao"
    if not isinstance(armazenamento, ArmazenamentoLocal) or \
            not getattr(armazenamento, "planilha", None):
        return "completa", "planilha fora da pasta local (modo graph)"
    foto = dados_bap.fotografia_para(armazenamento.planilha)
    if foto is None:
        return "completa", ("sem fotografia valida em RELATORIOS\\DADOS (ou "
                            "a TABELA_BAP foi salva por fora depois dela)")
    if COMPLETA_NA_PRIMEIRA_DO_DIA and str(foto.get("completa_em", ""))[:10] \
            != date.today().isoformat():
        return "completa", "primeira rodada do dia"
    # (05/11, revisor) a completa do dia achou diferenca entre o calculo em
    # Python e o Excel: as rapidas NAO usam o Python ate a proxima completa
    # sem diferenca - toda rodada vira completa (o Excel calcula)
    conf = foto.get("conferencia_excel") or {}
    if conf.get("diferencas"):
        log.warning("A ultima rodada completa achou %d diferenca(s) entre as "
                    "formulas em Python e o Excel (ex.: %s): rodada COMPLETA "
                    "ate isso ser corrigido - avise o Maestro Sistemas.",
                    conf["diferencas"], (conf.get("exemplos") or [])[:3])
        return "completa", (f"formulas em Python x Excel com "
                            f"{conf['diferencas']} diferenca(s)")
    return "rapida", f"fotografia de {foto.get('gerada_em')}"


def preparar_copia(armazenamento, copia: Path, simular: bool) -> None:
    """O passo 1 de sempre: a copia de trabalho local e os backups."""
    armazenamento.baixar_planilha(copia)
    backup_local(copia)
    if BACKUP_NA_NUVEM and not simular:
        armazenamento.guardar_backup_nuvem(
            copia, f"{Path(NOME_PLANILHA).stem}_{datetime.now():%Y%m%d_%H%M%S}"
                   f"{Path(NOME_PLANILHA).suffix}"
        )


def backup_dos_dados(pasta: Path) -> None:
    """Antes da rodada rapida: a fotografia de agora vai para o backup
    (BKP_RELATORIOS_AUXILIARES\\DADOS_aaaammdd_hhmmss), com rodizio."""
    if not MANTER_BACKUPS_DADOS or not (pasta / dados_bap.ARQ_ESTADO).exists():
        return
    destino = PASTA_BACKUPS / f"DADOS_{datetime.now():%Y%m%d_%H%M%S}"
    try:
        destino.mkdir(parents=True, exist_ok=True)
        for arq in pasta.iterdir():
            if arq.is_file() and (arq.name == dados_bap.ARQ_ESTADO
                                  or arq.name.endswith(".csv.gz")):
                shutil.copy2(arq, destino / arq.name)
        antigos = sorted(PASTA_BACKUPS.glob("DADOS_*"), reverse=True)
        for velho in antigos[MANTER_BACKUPS_DADOS:]:
            shutil.rmtree(velho, ignore_errors=True)
    except OSError as erro:
        log.warning("Backup da fotografia nao feito: %s", erro)


def tocar_planilha(planilha: Path, quando: float | None = None) -> bool:
    """Atualiza SO a data da TABELA_BAP (o conteudo nao muda): quem guarda
    cache pela data dela (Gerador de Meta, Planner, farois) sabe que o dado
    mudou na rodada rapida."""
    try:
        os.utime(planilha, None if quando is None else (quando, quando))
        return True
    except OSError as erro:
        log.warning("Nao consegui atualizar a data da %s (%s): os programas "
                    "que guardam cache pela data dela podem mostrar o dado "
                    "da rodada anterior ate a proxima.", NOME_PLANILHA, erro)
        return False


def rodada_rapida(planilha: Path, dados: dict, configs: dict) -> tuple:
    """
    A RODADA RAPIDA: as 7 abas montadas em memoria a partir da fotografia,
    a MESMA gravacao da completa (gravar_no_livro), as formulas calculadas
    em Python e a fotografia nova gravada. A TABELA_BAP nao e aberta para
    gravar - so as abas de cadastro que a conta usa sao lidas.
    Qualquer erro sobe: quem chama faz a rodada completa.
    """
    inicio = time.time()
    planilha = Path(planilha)
    pasta = dados_bap.pasta_dados(planilha)
    foto = dados_bap.fotografia_para(planilha)
    if foto is None:
        raise RuntimeError("a fotografia deixou de valer")
    base = dados_bap.base_do_xlsx(planilha)
    backup_dos_dados(pasta)
    log.info("Rodada RAPIDA: montando as abas da fotografia de %s...",
             foto.get("gerada_em"))
    wb = dados_bap.livro_em_memoria(pasta, foto, planilha)
    t_montar = time.time() - inicio
    try:
        resumos = gravar_no_livro(wb, dados, configs)
        t_gravar = time.time() - inicio - t_montar
        cadastro = dados_bap.linhas_do_xlsx(planilha, ["ProdutosBAP"])
        abas, estrutura = dados_bap.fotografia_do_livro(
            wb, foto, resumos, {a: v[0] for a, v in cadastro.items()})
    finally:
        wb.close()
    t_calcular = time.time() - inicio - t_montar - t_gravar
    if dados_bap.base_do_xlsx(planilha) != base:
        raise RuntimeError(f"a {NOME_PLANILHA} foi salva por fora durante a "
                           "rodada")
    novo = dados_bap.gravar_fotografia(
        pasta, abas, estrutura, {k: v for k, v in base.items()},
        "rapida", completa_em=foto.get("completa_em"),
        ordem=(foto.get("ordem") or []) + [
            a for a in abas if a not in (foto.get("ordem") or [])],
        # a conferencia Python x Excel da rodada completa segue em todas as
        # fotografias do dia (escolher_rodada olha para ela)
        extra={"conferencia_excel": foto.get("conferencia_excel") or {},
               "excel_recalculou": foto.get("excel_recalculou")})
    tocar_planilha(planilha)
    duracao = time.time() - inicio
    log.info("Fotografia gravada em %s (%.1f s: montar %.1f, gravar %.1f, "
             "formulas %.1f).", pasta, duracao, t_montar, t_gravar,
             t_calcular)
    return resumos, {"rodada": "rapida", "pasta": str(pasta),
                     "gerada_em": novo["gerada_em"],
                     "segundos": round(duracao, 1),
                     "linhas": {a: i["linhas"] for a, i in
                                novo["abas"].items()}}


def fotografar_completa(copia: Path, estrutura: dict, recalculou: bool,
                        planilha: Path) -> dict:
    """
    No fim da rodada completa (a planilha recalculada ja no lugar): a
    fotografia das 7 abas a partir dela (os valores do Excel). O calculo em Python e
    conferido contra o Excel e a diferenca vai para o log. Sem conseguir, a
    fotografia anterior sai de circulacao (os leitores voltam ao .xlsx e a
    proxima rodada e completa).
    """
    pasta = dados_bap.pasta_dados(planilha)
    try:
        if not estrutura:
            raise RuntimeError("a estrutura das abas nao foi anotada")
        inicio = time.time()
        abas, est_final, conf = dados_bap.fotografia_da_completa(
            copia, estrutura, recalculou)
        novo = dados_bap.gravar_fotografia(
            pasta, abas, est_final, dados_bap.base_do_xlsx(copia), "completa",
            ordem=estrutura.get("_ordem"),
            extra={"conferencia_excel": conf, "excel_recalculou": recalculou})
        if conf.get("erro"):
            log.warning("Formulas em Python: nao conferidas com o Excel "
                        "(%s).", conf["erro"])
        elif conf.get("diferencas"):
            log.warning("Formulas em Python x Excel: %d diferenca(s) em %d "
                        "celula(s) - ex.: %s. As proximas rodadas do dia serao "
                        "COMPLETAS: avise o Maestro Sistemas.",
                        conf["diferencas"], conf["celulas"],
                        conf["exemplos"][:3])
        else:
            log.info("Formulas em Python x Excel: %d celula(s) iguais.",
                     conf.get("celulas", 0))
        log.info("Fotografia da TABELA_BAP gravada em %s (%.1f s).", pasta,
                 time.time() - inicio)
        return {"rodada": "completa", "pasta": str(pasta),
                "gerada_em": novo["gerada_em"],
                "conferencia_excel": {k: conf.get(k) for k in
                                      ("celulas", "diferencas", "erro")}}
    except Exception as erro:                           # noqa: BLE001
        log.error("Nao consegui gravar a fotografia da TABELA_BAP: %s - as "
                  "proximas rodadas serao completas.", erro)
        log.debug("", exc_info=True)
        dados_bap.invalidar(pasta, str(erro))
        return {"rodada": "completa", "erro": str(erro)}


def executar(args) -> int:
    global RODADA_EM_ANDAMENTO
    inicio = time.time()

    selecionados = RELATORIOS
    if args.relatorio:
        pedidos = {r.strip().lower() for r in args.relatorio.split(",")}
        selecionados = [r for r in RELATORIOS if r["id"].lower() in pedidos]
        if not selecionados:
            log.error("Nenhum id em %s. Disponiveis: %s",
                      pedidos, [r["id"] for r in RELATORIOS])
            return 1

    log.info("=" * 70)
    log.info("BAP TOOLS -> %s | relatorios: %s",
             NOME_PLANILHA, ", ".join(r["id"] for r in selecionados))
    log.info("=" * 70)

    limpar_temporarios()
    armazenamento = criar_armazenamento()

    if armazenamento.planilha_ocupada():
        # (05/11) o aviso Continuar / Cancelar no lugar de sair na hora
        RODADA_EM_ANDAMENTO = True
        try:
            passo = aguardar_arquivo_livre(
                Path(getattr(armazenamento, "planilha", NOME_PLANILHA)),
                "comecar a rodada",
                verificar=lambda _p: aviso_arquivo.em_uso(
                    _p, olhar=lambda _q: armazenamento.planilha_ocupada()))
        except RodadaCancelada as cancel:
            log.error("Rodada cancelada pelo usuario: %s em aberto",
                      cancel.arquivo)
            return 1
        finally:
            RODADA_EM_ANDAMENTO = False
        if passo != "livre":
            log.error("A %s esta aberta no Excel nesta maquina. Feche e rode "
                      "de novo.", NOME_PLANILHA)
            return 1

    armazenamento.adquirir_trava()
    RODADA_EM_ANDAMENTO = True
    try:
        return _executar_rodada(args, armazenamento, selecionados, inicio)
    except RodadaCancelada as cancel:
        # (05/11) Cancelar no aviso de arquivo em aberto: para aqui, sem
        # resumo de sucesso (a trava e os temporarios saem no finally)
        log.error("Rodada cancelada pelo usuario: %s em aberto",
                  cancel.arquivo)
        try:
            guardar_resumo({
                "status": "cancelado",
                "planilha": NOME_PLANILHA,
                "quando": datetime.now().isoformat(timespec="seconds"),
                "maquina": os.environ.get("COMPUTERNAME", "?"),
                "mensagem": f"Rodada cancelada pelo usuario: "
                            f"{cancel.arquivo} em aberto"})
        except Exception:                               # noqa: BLE001
            pass
        return 1
    finally:
        RODADA_EM_ANDAMENTO = False
        armazenamento.liberar_trava()
        limpar_temporarios()


def _executar_rodada(args, armazenamento, selecionados, inicio) -> int:
    """O miolo de executar (entre a trava e o fim). O "if True" so guarda
    a indentacao do codigo de antes (o diff fica so com o que mudou)."""
    if True:
        # ---- 0. (05/11) rodada completa ou rapida (TABELA_BAP_SO_SAIDA) ------
        rodada, motivo = escolher_rodada(args, armazenamento)
        log.info("Rodada %s: %s.", rodada.upper(), motivo)
        if not TABELA_BAP_SO_SAIDA and getattr(armazenamento, "planilha",
                                               None):
            # desligado: a fotografia sai de circulacao (os leitores voltam
            # a TABELA_BAP, que e atualizada em toda rodada)
            if dados_bap.invalidar(dados_bap.pasta_dados(
                    armazenamento.planilha), "TABELA_BAP_SO_SAIDA desligado"):
                log.info("Fotografia em RELATORIOS\\DADOS desligada.")

        # ---- 1. traz a planilha para uma copia de trabalho local -------------
        # (na rodada rapida nao: a TABELA_BAP nao e aberta)
        copia = PASTA_TEMP / NOME_PLANILHA
        try:
            copia.unlink(missing_ok=True)
        except OSError as erro:
            # copia velha travada: a completa a sobrescreve; a rapida nem
            # usa - nao derruba a rodada
            log.warning("Nao consegui apagar a copia antiga %s: %s", copia,
                        erro)
        if rodada == "completa":
            preparar_copia(armazenamento, copia, args.simular)

        # ---- 2. baixa os relatorios do BAP Tools -----------------------------
        if args.sem_baixar:
            arquivos = {}
            for cfg in selecionados:
                recente = armazenamento.relatorio_mais_recente(
                    cfg.get("arquivo") or cfg["id"], PASTA_TEMP
                )
                if recente:
                    arquivos[cfg["id"]] = recente
                    log.info("Reaproveitando: %s", recente.name)
                else:
                    log.error("Sem relatorio anterior para '%s'.", cfg["id"])
        else:
            arquivos = baixar_todos(selecionados, args.visivel)

        if not arquivos:
            log.error("Nenhum relatorio obtido. Nada a atualizar.")
            return 1

        # ---- 3. le e (se for o caso) arquiva na nuvem -------------------------
        configs = {r["id"]: r for r in selecionados}
        dados: dict[str, pd.DataFrame] = {}

        for identificador, caminho in arquivos.items():
            cfg = configs[identificador]
            try:
                dados[identificador] = ler_arquivo(caminho, cfg)
            except Exception as erro:
                log.error("  Erro na leitura de %s: %s", caminho.name, erro)
                continue

            if not args.sem_baixar:
                nome_nuvem = (f"{cfg.get('arquivo') or identificador}_"
                              f"{datetime.now():%Y-%m-%d}{caminho.suffix}")
                if args.simular:
                    log.warning("  [simulacao] nao enviei %s para a nuvem", nome_nuvem)
                else:
                    destino = armazenamento.guardar_relatorio(caminho, nome_nuvem)
                    log.info("  Arquivado na nuvem: %s", destino)

        if not dados:
            log.error("Nenhum arquivo pode ser lido. Nada a atualizar.")
            return 1

        # ---- 4. grava nas abas e devolve a planilha --------------------------
        fotografia = {}
        resumos = None
        if rodada == "rapida":
            try:
                resumos, fotografia = rodada_rapida(
                    Path(armazenamento.planilha), dados, configs)
            except Exception as erro:                   # noqa: BLE001
                log.warning("Rodada rapida nao deu (%s): fazendo a COMPLETA.",
                            erro)
                log.debug("", exc_info=True)
                rodada, motivo = "completa", f"a rapida falhou: {erro}"
                preparar_copia(armazenamento, copia, args.simular)

        if rodada == "completa":
            estrutura = {}
            resumos = gravar_planilha(copia, dados, configs,
                                      estrutura=estrutura)

            if args.simular:
                destino = PASTA_LOCAL / f"SIMULACAO_{NOME_PLANILHA}"
                shutil.copy2(copia, destino)
                log.warning("MODO SIMULACAO: a planilha de destino NAO foi alterada.")
                log.warning("Resultado para conferencia: %s", destino)

            # ---- 4a. recalcula as formulas da planilha -----------------------
            # Tem de ser aqui: a solicitacao le esta copia logo abaixo, e quem
            # consome a planilha depois (Power BI, Power Query) le valores,
            # nao formulas.
            recalculou = recalcular_com_excel(copia, NOME_PLANILHA)

        # de onde os passos 4b leem: a copia recalculada (completa) ou a
        # TABELA_BAP com a fotografia nova (rapida)
        fonte = copia if rodada == "completa" else Path(armazenamento.planilha)

        # ---- 4b. solicitacao de coleta (a medida DAX em Python) --------------
        # ATENCAO A ORDEM: isto roda ANTES de devolver a planilha, porque
        # enviar_planilha MOVE a copia de trabalho para o destino. Se inverter,
        # a solicitacao fica sem arquivo para ler.
        solicitacao = {}
        if GERAR_SOLICITACAO:
            try:
                solicitacao = gerar_solicitacao(fonte, armazenamento,
                                                args.simular)
            except Exception as erro:
                log.error("Nao consegui montar a solicitacao de coleta: %s", erro)
                log.debug("", exc_info=True)

        # ---- 4b2. tabela de preco: ontem x hoje ------------------------------
        # Tambem tem de rodar ANTES de a planilha ser devolvida.
        precos = {}
        if COMPARAR_TABELA_PRECO:
            try:
                alvo = fonte if fonte.exists() else Path(armazenamento.planilha)
                precos = acompanhar_tabela_de_preco(alvo, args.simular)
            except Exception as erro:
                log.error("Nao consegui comparar a tabela de preco: %s", erro)
                log.debug("", exc_info=True)

        # ---- 4b3. estoque x preco por filial ---------------------------------
        estoque_bap = {}
        if GERAR_ESTOQUE_BAP:
            try:
                alvo = fonte if fonte.exists() else Path(armazenamento.planilha)
                estoque_bap = gerar_estoque_bap(alvo, args.simular)
            except Exception as erro:
                log.error("Nao consegui montar o %s: %s", ARQUIVO_ESTOQUE_BAP, erro)
                log.debug("", exc_info=True)
                # o resumo tem de carregar a falha, senao a janela termina
                # dizendo "Concluido com sucesso" e o arquivo nao saiu
                estoque_bap = {"erro": str(erro),
                               "arquivo": ARQUIVO_ESTOQUE_BAP}

        # ---- 4b4. a carteira do Planner -------------------------------------
        # Tem de rodar aqui, com a copia local ainda na mao: e a TABELA_BAP
        # recem-atualizada que alimenta a base.
        base_cliente = {}
        if GERAR_BASE_CLIENTE:
            try:
                alvo = fonte if fonte.exists() else Path(armazenamento.planilha)
                base_cliente = gerar_base_cliente_bap(alvo, args.simular)
            except Exception as erro:
                log.error("Nao consegui montar a %s: %s",
                          ARQUIVO_BASE_CLIENTE, erro)
                log.debug("", exc_info=True)
                base_cliente = {"erro": str(erro),
                                "arquivo": ARQUIVO_BASE_CLIENTE}

        # ---- 4b5. entrega, devolucao e garantia ------------------------------
        # Le a TABELA_BAP recem-atualizada: a nota que saiu hoje ja vira linha.
        pos_venda = {}
        if GERAR_POS_VENDA:
            try:
                alvo = fonte if fonte.exists() else Path(armazenamento.planilha)
                pos_venda = gerar_acompanhamento_pos_venda(alvo, args.simular)
            except Exception as erro:
                log.error("Nao consegui atualizar o %s: %s", ARQUIVO_POS_VENDA,
                          erro)
                log.debug("", exc_info=True)
                pos_venda = {"erro": str(erro), "arquivo": ARQUIVO_POS_VENDA}

        # ---- 4c. so agora a planilha volta para o lugar ----------------------
        # (na rodada rapida a TABELA_BAP nao foi aberta: o dado novo esta na
        # fotografia, RELATORIOS\DADOS)
        tabela_gravada = False
        if not args.simular and rodada == "completa":
            # (05/11) aberta no Excel: o aviso antes de trocar o arquivo
            if getattr(armazenamento, "planilha", None) and \
                    aguardar_arquivo_livre(
                        Path(armazenamento.planilha), "devolver a TABELA_BAP",
                        verificar=lambda _p: aviso_arquivo.em_uso(
                            _p, olhar=lambda _q:
                            armazenamento.planilha_ocupada())) != "livre":
                log.error("%s NAO foi atualizada nesta rodada (em aberto): a "
                          "proxima rodada refaz.", NOME_PLANILHA)
            else:
                armazenamento.enviar_planilha(copia)
                tabela_gravada = True
                log.info("%s atualizada em %s.", NOME_PLANILHA,
                         armazenamento.descrever())
        elif rodada == "rapida":
            log.info("%s nao foi aberta (rodada rapida): dados novos em %s.",
                     NOME_PLANILHA, fotografia.get("pasta", PASTA_DADOS))

        # ---- 4c2. (05/11) a fotografia das abas de dados (rodada completa) ---
        # Depois de a planilha estar no lugar: ate aqui quem le a TABELA_BAP
        # continua com a fotografia da rodada anterior (que confere com a
        # TABELA_BAP anterior); a nova sai da planilha que acabou de chegar.
        if rodada == "completa" and TABELA_BAP_SO_SAIDA and \
                not args.simular and tabela_gravada and \
                isinstance(armazenamento, ArmazenamentoLocal):
            fotografia = fotografar_completa(
                Path(armazenamento.planilha), estrutura, recalculou,
                Path(armazenamento.planilha))

        # ---- 4d. os dados dos relatorios do BAP Central ----------------------
        # Depois da planilha no lugar: o cache e da TABELA_BAP que ficou.
        dados_relatorios = {}
        try:
            dados_relatorios = gerar_dados_relatorios(args.simular)
        except Exception as erro:
            log.error("Nao consegui preparar os dados dos relatorios: %s", erro)
            log.debug("", exc_info=True)
            dados_relatorios = {"erro": str(erro)}

        # ---- 4e. o app BAP Ajuda 2.0 (27/10, Alexandre) ----------------------
        # Depois de ESTOQUE_BAP e BASE_CLIENTE gravados: manda para o app e
        # baixa as respostas do app (Pesquisa, Indicacao, Prospeccao). Falha
        # aqui nunca derruba a rodada.
        bap_ajuda = {}
        if not args.simular:
            try:
                bap_ajuda = sincronizar_bap_ajuda()
            except Exception as erro:                   # noqa: BLE001
                log.warning("BAP Ajuda: %s", erro)
                bap_ajuda = {"erro": str(erro)}

        # ---- 4f. o pacote da web (T-0013) ------------------------------------
        # Monta o vc_painel e manda so as abas resultado e produtividade. --pacote-web-simular grava em arquivo local sem enviar.
        # Falha aqui nunca derruba a rodada.
        if not args.simular or args.pacote_web_simular:
            try:
                passo_pacote_web(args.pacote_web_simular)
            except Exception as erro:                   # noqa: BLE001
                log.warning("Pacote web (4f): %s", erro)

        falhas = len(selecionados) - len(dados)
        duracao = time.time() - inicio
        log.info("=" * 70)
        log.info("Concluido em %.1f s | %d de %d relatorios | %d falha(s)",
                 duracao, len(dados), len(selecionados), falhas)
        log.info("=" * 70)

        # ---- 5. avisa quem quiser saber (Power BI, Teams, e-mail) ------------
        if not args.simular:
            resumo_final = {
                "status": "sucesso" if falhas == 0 else "parcial",
                "planilha": NOME_PLANILHA,
                "rodada": rodada,
                "rodada_motivo": motivo,
                "fotografia": fotografia,
                "quando": datetime.now().isoformat(timespec="seconds"),
                "maquina": os.environ.get("COMPUTERNAME", "?"),
                "usuario": os.environ.get("USERNAME", "?"),
                "duracao_segundos": round(duracao, 1),
                "relatorios_ok": len(dados),
                "relatorios_pedidos": len(selecionados),
                "falhas": falhas,
                "solicitacao": solicitacao,
                "precos": precos,
                "estoque_bap": estoque_bap,
                "base_cliente": base_cliente,
                "pos_venda": pos_venda,
                "dados_relatorios": dados_relatorios,
                "bap_ajuda": bap_ajuda,
                "abas": [
                    {
                        "aba": r["aba"],
                        "linhas_antes": r["linhas_antes"],
                        "linhas_depois": r["linhas_depois"],
                        "linhas_incluidas": r["linhas_incluidas"],
                        "colunas_substituidas": len(r["colunas_atualizadas"]),
                    }
                    for r in resumos
                ],
            }
            guardar_resumo(resumo_final)
            avisar_power_automate(resumo_final)
            rodar_script_final(resumo_final)

        return 0 if falhas == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BAP Tools -> TABELA_BAP.xlsx (SharePoint via Graph ou OneDrive local).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--configurar-nuvem", action="store_true",
                        help="faz o login da Microsoft e valida o acesso (1a vez)")
    parser.add_argument("--checar", action="store_true",
                        help="confere nuvem, planilha e abas; nao baixa nada")
    parser.add_argument("--descobrir", action="store_true",
                        help="abre o site e imprime os seletores reais da tela")
    parser.add_argument("--listar-consultas", action="store_true",
                        help="loga sozinho e imprime a lista de consultas do BAP Tools")
    parser.add_argument("--visivel", action="store_true",
                        help="mostra o navegador (para testes)")
    parser.add_argument("--simular", action="store_true",
                        help="processa tudo, mas NAO altera nada na nuvem")
    parser.add_argument("--pacote-web-simular", action="store_true",
                        help="passo 4f: monta o pacote da web e grava em "
                             "arquivo local (pasta temporaria), sem enviar")
    parser.add_argument("--relatorio", metavar="IDS",
                        help="roda so estes ids (clientes,titulos,estoque,pedidos,precos)")
    parser.add_argument("--sem-baixar", action="store_true",
                        help="reaproveita os relatorios ja arquivados na nuvem")
    parser.add_argument("--completa", action="store_true",
                        help="rodada completa: abre, grava e recalcula a "
                             "TABELA_BAP (e refaz a fotografia)")
    parser.add_argument("--solicitacao", action="store_true",
                        help="so monta a solicitacao de coleta da planilha atual")
    parser.add_argument("--limpar-simulacao", action="store_true",
                        help="zera a copia local e os CSVs de teste da simulacao")
    parser.add_argument("--destravar", action="store_true",
                        help="remove uma trava presa de execucao anterior")
    parser.add_argument("--salvar-senha", action="store_true",
                        help="grava a senha do BAP Tools no cofre do Windows")
    parser.add_argument("--verboso", action="store_true", help="log detalhado")
    args = parser.parse_args()

    if args.salvar_senha:
        salvar_senha_interativo()
        return 0

    garantir_pastas_locais()
    configurar_log(args.verboso)

    try:
        if args.configurar_nuvem:
            return modo_configurar_nuvem()
        if args.listar_consultas:
            return modo_listar_consultas(args.visivel)
        if args.descobrir:
            modo_descoberta()
            return 0
        if args.checar:
            return modo_checagem()
        if args.solicitacao:
            return modo_solicitacao(args.simular)
        if args.limpar_simulacao:
            return modo_limpar_simulacao()
        if args.destravar:
            return modo_destravar()
        return executar(args)
    except KeyboardInterrupt:
        log.warning("Interrompido pelo usuario.")
        return 1
    except Exception as erro:
        log.exception("FALHA: %s", erro)
        try:
            resumo_erro = {
                "status": "erro",
                "planilha": NOME_PLANILHA,
                "quando": datetime.now().isoformat(timespec="seconds"),
                "maquina": os.environ.get("COMPUTERNAME", "?"),
                "mensagem": str(erro)[:500],
            }
            guardar_resumo(resumo_erro)
            avisar_power_automate(resumo_erro)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
