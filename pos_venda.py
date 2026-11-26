# -*- coding: utf-8 -*-
"""
ACOMPANHAMENTO DE POS-VENDA - entrega, devolucao e garantia.

Um arquivo so, RELATORIOS\\ACOMPANHAMENTO_POS_VENDA.xlsx, que as tres
assistentes editam juntas no Excel online:

    PAINEL ....... o resumo, sozinho (formulas)
    ENTREGAS ..... uma linha por NOTA FISCAL DE VENDA - da nota ao canhoto
    DEVOLUCOES ... uma linha por devolucao - da solicitacao ao credito
    GARANTIAS .... uma linha por peca em garantia - ate o parecer do
                   fornecedor e a resposta ao cliente
    PRAZOS ....... quantos dias cada destino leva para receber
    Leia-me

A MESMA REGRA DA SOLICITACAO_BAP:
  * o BAP Tools ABRE a linha sozinho, com a etapa inicial - a nota de venda
    nova vira ENTREGA (etapa FATURADA), a nota de devolucao nova vira
    DEVOLUCAO (etapa NF DEV EMITIDA);
  * daqui para frente a linha e 100% da assistente. O script NUNCA mexe numa
    linha que ja esta gravada - nem na etapa, nem em nada;
  * garantia nao existe no Protheus: e aberta a mao.

Este modulo e o mesmo que os programas BAP leem para mostrar os indicadores
- por isso ele tambem sabe LER o arquivo, calculando atraso e dias em aberto
aqui mesmo, sem depender do Excel ter recalculado as formulas.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook
try:  # leitura rapida com cache (sem o arquivo: openpyxl)
    from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
except ImportError:
    from openpyxl import load_workbook  # noqa: PLC0415
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

ARQUIVO = "ACOMPANHAMENTO_POS_VENDA.xlsx"
# Notas a partir desta data entram no acompanhamento. O historico antigo
# nao entra: ele ja foi entregue, e abrir milhares de linhas para alguem
# fechar uma a uma so atrapalharia o comeco.
INICIO_PADRAO = date(2026, 10, 1)

LINHA_CABECALHO = 4
PRIMEIRA = 5
ULTIMA_VALIDACAO = 5000           # ate onde valem as listas suspensas
FOLGA_DE_FORMULAS = 300           # linhas prontas para quem abre a mao

ABA_PAINEL, ABA_ENT, ABA_DEV, ABA_GAR = ("PAINEL", "ENTREGAS", "DEVOLUCOES",
                                         "GARANTIAS")
ABA_PRAZOS, ABA_LISTAS, ABA_LEIA = "PRAZOS", "Listas", "Leia-me"

# (30/10, Alexandre) as ETAPAS da entrega: AGUARDANDO COLETA, EM TRANSITO,
# ENTREGUE e CANCELADA. As antigas que ja estao no arquivo aparecem como a
# nova equivalente (o arquivo nao e reescrito): FATURADA -> AGUARDANDO
# COLETA, EXPEDIDA -> EM TRANSITO.
ETAPAS_ENTREGA = ["AGUARDANDO COLETA", "EM TRÂNSITO", "ENTREGUE",
                  "CANCELADA"]
ETAPA_ANTIGA = {"FATURADA": "AGUARDANDO COLETA", "EXPEDIDA": "EM TRÂNSITO"}
# a ordem do andamento (a etapa que "volta" e cara de versao velha): as
# antigas continuam na ordem para o diario saber o que e avanco
ORDEM_ETAPA_ENTREGA = ["FATURADA", "AGUARDANDO COLETA", "EXPEDIDA",
                       "EM TRÂNSITO", "ENTREGUE", "OCORRÊNCIA", "CANCELADA"]
OCORRENCIAS = ["AVARIA", "FALTA DE VOLUME", "RECUSA DO CLIENTE",
               "ENDEREÇO / CLIENTE NÃO LOCALIZADO", "ATRASO DA TRANSPORTADORA",
               "OUTRA"]
ETAPAS_DEVOLUCAO = ["SOLICITADA", "AUTORIZADA", "RECEBIDA E CONFERIDA",
                    "NF DEV EMITIDA", "CRÉDITO LANÇADO", "ENCERRADA", "NEGADA",
                    "CANCELADA"]
MOTIVOS_DEVOLUCAO = ["ERRO DE PEDIDO (VENDEDOR)",
                     "ERRO DE DIGITAÇÃO / FATURAMENTO",
                     "PRODUTO ERRADO ENVIADO", "AVARIA NO TRANSPORTE",
                     "DEFEITO (GARANTIA)", "DESISTÊNCIA DO CLIENTE",
                     "PREÇO OU CONDIÇÃO DIVERGENTE", "ATRASO NA ENTREGA",
                     "OUTRO"]
FORMAS_CREDITO = ["ABATIMENTO NO TÍTULO", "REEMBOLSO", "RA (CRÉDITO EM CONTA)",
                  "TROCA DE PRODUTO", "SEM CRÉDITO"]
ETAPAS_GARANTIA = ["ABERTA", "EM ANÁLISE", "NO FORNECEDOR", "PROCEDENTE",
                   "IMPROCEDENTE", "CRÉDITO/TROCA AO CLIENTE", "ENCERRADA"]
SOLUCOES_GARANTIA = ["CRÉDITO", "TROCA", "REPARO", "NEGADA (IMPROCEDENTE)"]
SIM_NAO = ["SIM", "NÃO"]

ENCERRADAS_DEV = {"ENCERRADA", "NEGADA", "CANCELADA"}
ENCERRADAS_ENT = {"ENTREGUE", "CANCELADA"}
ENCERRADAS_GAR = {"ENCERRADA"}

# DIAS UTEIS da nota ate a entrega (decidido em 03/10/2026):
#   capital do estado = 3 dias uteis | interior = ate 5 dias uteis
# A busca tenta UF|CIDADE (as capitais) e cai no PADRAO (o interior).
# Sabado, domingo e os feriados da coluna E da aba PRAZOS nao contam.
PRAZO_CAPITAL, PRAZO_INTERIOR = 3, 5
CAPITAIS = [
    # as da regional BAP primeiro
    ("AM", "MANAUS"), ("PA", "BELEM"), ("MA", "SAO LUIS"), ("RR", "BOA VISTA"),
    ("AP", "MACAPA"), ("MT", "CUIABA"), ("RO", "PORTO VELHO"),
    ("AC", "RIO BRANCO"), ("TO", "PALMAS"), ("PI", "TERESINA"),
    ("CE", "FORTALEZA"), ("RN", "NATAL"), ("PB", "JOAO PESSOA"),
    ("PE", "RECIFE"), ("AL", "MACEIO"), ("SE", "ARACAJU"), ("BA", "SALVADOR"),
    ("DF", "BRASILIA"), ("GO", "GOIANIA"), ("MS", "CAMPO GRANDE"),
    ("MG", "BELO HORIZONTE"), ("ES", "VITORIA"), ("RJ", "RIO DE JANEIRO"),
    ("SP", "SAO PAULO"), ("PR", "CURITIBA"), ("SC", "FLORIANOPOLIS"),
    ("RS", "PORTO ALEGRE"),
]
# o Excel compara acento: a capital acentuada entra tambem com acento
_COM_ACENTO = {"BELEM": "BELÉM", "SAO LUIS": "SÃO LUÍS", "MACAPA": "MACAPÁ",
               "CUIABA": "CUIABÁ", "JOAO PESSOA": "JOÃO PESSOA",
               "MACEIO": "MACEIÓ", "BRASILIA": "BRASÍLIA",
               "GOIANIA": "GOIÂNIA", "VITORIA": "VITÓRIA",
               "SAO PAULO": "SÃO PAULO", "FLORIANOPOLIS": "FLORIANÓPOLIS"}
PRAZOS_PADRAO = [("PADRÃO", PRAZO_INTERIOR, "interior: cidade que não é capital")]
for _uf, _cid in CAPITAIS:
    PRAZOS_PADRAO.append((f"{_uf}|{_cid}", PRAZO_CAPITAL, "capital"))
# Santarem e Varzea Grande nao sao capital, mas a BAP entrega la sem frete
# (03/10/2026): contam como capital, 3 dias uteis.
for _uf, _cid, _ac in (("PA", "SANTAREM", "SANTARÉM"),
                       ("MT", "VARZEA GRANDE", "VÁRZEA GRANDE")):
    PRAZOS_PADRAO.append((f"{_uf}|{_cid}", PRAZO_CAPITAL, "cidade BAP sem frete"))
    PRAZOS_PADRAO.append((f"{_uf}|{_ac}", PRAZO_CAPITAL,
                          "cidade BAP sem frete (grafia com acento)"))
for _uf, _cid in CAPITAIS:
    if _cid in _COM_ACENTO:
        PRAZOS_PADRAO.append((f"{_uf}|{_COM_ACENTO[_cid]}", PRAZO_CAPITAL,
                              "capital (grafia com acento)"))
    if _cid == "SAO LUIS":
        PRAZOS_PADRAO.append((f"{_uf}|SÃO LUIS", PRAZO_CAPITAL,
                              "capital (grafia com acento)"))

# feriados NACIONAIS que nao contam no prazo (coluna E da aba PRAZOS -
# acrescente la os de 2028 em diante e os locais, se quiser)
FERIADOS_ENTREGA = [
    ("2026-01-01", "Confraternização Universal"), ("2026-02-16", "Carnaval"),
    ("2026-02-17", "Carnaval"), ("2026-04-03", "Sexta-feira Santa"),
    ("2026-04-21", "Tiradentes"), ("2026-05-01", "Dia do Trabalho"),
    ("2026-06-04", "Corpus Christi"), ("2026-09-07", "Independência"),
    ("2026-10-12", "N. Sra. Aparecida"), ("2026-11-02", "Finados"),
    ("2026-11-15", "Proclamação da República"),
    ("2026-11-20", "Consciência Negra"), ("2026-12-25", "Natal"),
    ("2027-01-01", "Confraternização Universal"), ("2027-02-08", "Carnaval"),
    ("2027-02-09", "Carnaval"), ("2027-03-26", "Sexta-feira Santa"),
    ("2027-04-21", "Tiradentes"), ("2027-05-01", "Dia do Trabalho"),
    ("2027-05-27", "Corpus Christi"), ("2027-09-07", "Independência"),
    ("2027-10-12", "N. Sra. Aparecida"), ("2027-11-02", "Finados"),
    ("2027-11-15", "Proclamação da República"),
    ("2027-11-20", "Consciência Negra"), ("2027-12-25", "Natal"),
]
FERIADOS_ATE = 200                # linha final da coluna E lida pelo WORKDAY


def somar_dias_uteis(inicio: date, dias: int, feriados=()) -> date:
    """O WORKDAY do Excel: pula sabado, domingo e feriado."""
    fer = set(feriados)
    d, falta = inicio, int(dias)
    while falta > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in fer:
            falta -= 1
    return d


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c)).upper().strip()


# ---------------------------------------------------------------------------
# as colunas: (titulo, chave, largura, tipo)
#   tipo: "sis" o BAP Tools preenche | "ass" a assistente preenche |
#         "f" formula | "data" e "valor" so formatam
# ---------------------------------------------------------------------------
COLUNAS_ENTREGA = [
    ("NF", "nf", 11, "sis"), ("SÉRIE", "serie", 6, "sis"),
    ("DATA NF", "data_nf", 11, "sis data"), ("CLIENTE", "cliente", 34, "sis"),
    ("CIDADE", "cidade", 18, "sis"), ("UF", "uf", 5, "sis"),
    ("VALOR R$", "valor", 12, "sis valor"),
    ("ETAPA", "etapa", 14, "ass"),
    ("PREVISTA ATÉ", "prevista", 12, "f data"),
    ("SITUAÇÃO", "situacao", 20, "f"),
    ("DIAS", "dias", 7, "f"),
    ("TRANSPORTADORA", "transportadora", 20, "ass"),
    ("EXPEDIDA EM", "expedida_em", 12, "ass data"),
    ("ENTREGUE EM", "entregue_em", 12, "ass data"),
    ("CANHOTO", "canhoto", 9, "ass"),
    ("OCORRÊNCIA", "ocorrencia", 22, "ass"),
    ("OBSERVAÇÃO", "observacao", 30, "ass"),
    ("RESPONSÁVEL", "responsavel", 16, "ass"),
    ("CÓD. CLIENTE", "cod_cliente", 10, "sis"),
    ("VENDEDOR", "vendedor", 22, "sis"),
    ("FILIAL", "filial", 10, "sis"),
    ("CIDADE FILIAL", "cidade_filial", 14, "sis"),
    ("PEDIDO", "pedido", 10, "sis"),
    ("ITENS", "itens", 6, "sis"),
    ("CHAVE", "chave", 20, "sis"),
    ("ABERTA EM", "aberta_em", 15, "sis data"),
    # (16/10, Alexandre) o FRETE REAL da nota (o que a transportadora
    # cobrou). Vazio = o estimado (% da transportadora). No Farol de Saldo:
    # 5% da nota - frete real vira saldo (positivo ou negativo)
    ("FRETE REAL R$", "frete_real", 12, "ass valor"),
    # (30/10, Alexandre) a PREVISAO DE ENTREGA ajustada pela assistente na
    # tela (Farol de Entregas › Editar). Vazio = a previsao calculada (SLA a
    # partir do pedido). A PREVISTA ATE do Excel continua a formula.
    ("PREVISTA AJUSTADA", "prevista_manual", 12, "ass data"),
]
COLUNAS_DEVOLUCAO = [
    ("DATA", "data", 11, "sis data"),
    ("NF DEVOLUÇÃO", "nf_dev", 12, "sis"),
    ("NF DE ORIGEM", "nf_origem", 12, "sis"),
    ("DATA DA VENDA", "data_venda", 12, "sis data"),
    ("CLIENTE", "cliente", 34, "sis"),
    ("VENDEDOR", "vendedor", 22, "sis"),
    ("VALOR R$", "valor", 12, "sis valor"),
    ("PRODUTOS", "produtos", 34, "sis"),
    ("ETAPA", "etapa", 18, "ass"),
    ("MOTIVO", "motivo", 28, "ass"),
    ("AUTORIZADO POR", "autorizado_por", 16, "ass"),
    ("RECEBIDA EM", "recebida_em", 12, "ass data"),
    ("FORMA DO CRÉDITO", "credito", 20, "ass"),
    ("CRÉDITO EM", "credito_em", 12, "ass data"),
    ("DIAS EM ABERTO", "dias", 9, "f"),
    ("OBSERVAÇÃO", "observacao", 30, "ass"),
    ("RESPONSÁVEL", "responsavel", 16, "ass"),
    ("CÓD. CLIENTE", "cod_cliente", 10, "sis"),
    ("FILIAL", "filial", 10, "sis"),
    ("ORIGEM DA LINHA", "origem", 14, "sis"),
    ("CHAVE", "chave", 20, "sis"),
    ("ABERTA EM", "aberta_em", 15, "sis data"),
]
COLUNAS_GARANTIA = [
    ("Nº", "numero", 8, "f"),
    ("ABERTA EM", "aberta_em", 11, "ass data"),
    ("CÓD. CLIENTE", "cod_cliente", 10, "ass"),
    ("CLIENTE", "cliente", 30, "ass"),
    ("VENDEDOR", "vendedor", 18, "ass"),
    ("CÓD. PRODUTO", "cod_produto", 14, "ass"),
    ("DESCRIÇÃO", "descricao", 30, "ass"),
    ("FORNECEDOR", "fornecedor", 18, "ass"),
    ("NF DE VENDA", "nf_venda", 11, "ass"),
    ("DATA DA VENDA", "data_venda", 12, "ass data"),
    ("QTD", "qtd", 6, "ass"),
    ("VALOR R$", "valor", 11, "ass valor"),
    ("DEFEITO ALEGADO", "defeito", 28, "ass"),
    ("ETAPA", "etapa", 20, "ass"),
    ("PROTOCOLO FORNECEDOR", "protocolo", 16, "ass"),
    ("ENVIADA AO FORNECEDOR EM", "enviada_em", 13, "ass data"),
    ("PARECER EM", "parecer_em", 12, "ass data"),
    ("SOLUÇÃO", "solucao", 20, "ass"),
    ("ENCERRADA EM", "encerrada_em", 12, "ass data"),
    ("DIAS EM ABERTO", "dias", 9, "f"),
    ("DIAS NO FORNECEDOR", "dias_fornecedor", 10, "f"),
    ("RESPONSÁVEL", "responsavel", 16, "ass"),
    ("OBSERVAÇÃO", "observacao", 30, "ass"),
]


def _letra(colunas, chave) -> str:
    for i, c in enumerate(colunas, start=1):
        if c[1] == chave:
            return get_column_letter(i)
    raise KeyError(chave)


def _formulas_entrega(n: int) -> dict:
    L = lambda k: f"{_letra(COLUNAS_ENTREGA, k)}{n}"      # noqa: E731
    return {
        "prevista": (f'=IF({L("data_nf")}="","",WORKDAY({L("data_nf")},IFERROR('
                     f'VLOOKUP({L("uf")}&"|"&{L("cidade")},{ABA_PRAZOS}!$A:$B,2,0),'
                     f'IFERROR(VLOOKUP({L("uf")},{ABA_PRAZOS}!$A:$B,2,0),'
                     f'{ABA_PRAZOS}!$B$5)),'
                     f'{ABA_PRAZOS}!$E${PRIMEIRA}:$E${FERIADOS_ATE}))'),
        "situacao": (f'=IF({L("data_nf")}="","",IF({L("etapa")}="CANCELADA","—",'
                     f'IF({L("entregue_em")}<>"",IF({L("entregue_em")}<={L("prevista")},'
                     f'"NO PRAZO","ENTREGUE COM ATRASO"),'
                     f'IF(TODAY()>{L("prevista")},"ATRASADA","NO PRAZO"))))'),
        "dias": (f'=IF({L("data_nf")}="","",IF({L("entregue_em")}<>"",'
                 f'{L("entregue_em")}-{L("data_nf")},TODAY()-{L("data_nf")}))'),
    }


def _formulas_devolucao(n: int) -> dict:
    L = lambda k: f"{_letra(COLUNAS_DEVOLUCAO, k)}{n}"    # noqa: E731
    return {
        "dias": (f'=IF({L("data")}="","",IF(OR({L("etapa")}="ENCERRADA",'
                 f'{L("etapa")}="NEGADA",{L("etapa")}="CANCELADA"),"",'
                 f'TODAY()-{L("data")}))'),
    }


def _formulas_garantia(n: int) -> dict:
    L = lambda k: f"{_letra(COLUNAS_GARANTIA, k)}{n}"     # noqa: E731
    return {
        "numero": f'=IF({L("aberta_em")}="","","G-"&TEXT(ROW()-4,"0000"))',
        "dias": (f'=IF({L("aberta_em")}="","",IF({L("encerrada_em")}<>"",'
                 f'{L("encerrada_em")}-{L("aberta_em")},TODAY()-{L("aberta_em")}))'),
        "dias_fornecedor": (f'=IF({L("enviada_em")}="","",IF({L("parecer_em")}<>"",'
                            f'{L("parecer_em")}-{L("enviada_em")},'
                            f'TODAY()-{L("enviada_em")}))'),
    }


FORMULAS = {ABA_ENT: (COLUNAS_ENTREGA, _formulas_entrega),
            ABA_DEV: (COLUNAS_DEVOLUCAO, _formulas_devolucao),
            ABA_GAR: (COLUNAS_GARANTIA, _formulas_garantia)}

# ---------------------------------------------------------------------------
# estilo
# ---------------------------------------------------------------------------
AZUL = "2F7D32"          # o verde BAP (era o azul)
FINO = Side(style="thin", color="D5DAD4")
BORDA = Border(left=FINO, right=FINO, top=FINO, bottom=FINO)
CAB = PatternFill("solid", fgColor=AZUL)
CAB_SIS = PatternFill("solid", fgColor="69736D")    # o que o script preenche
CAB_FONTE = Font(color="FFFFFF", bold=True, size=9)
VERDE = PatternFill("solid", fgColor="DDF1E4")
AMARELO = PatternFill("solid", fgColor="FFF4D6")
VERMELHO = PatternFill("solid", fgColor="FBE3E3")
CINZA = PatternFill("solid", fgColor="F3F4F2")


def _montar_aba(ws, titulo: str, sub: str, colunas: list) -> None:
    ws["A1"] = titulo
    ws["A1"].font = Font(bold=True, size=14, color=AZUL)
    ws["A2"] = sub
    ws["A2"].font = Font(size=9, color="6B7A8D")
    for i, (t, _k, w, tipo) in enumerate(colunas, start=1):
        c = ws.cell(LINHA_CABECALHO, i, t)
        c.fill = CAB_SIS if tipo.startswith("sis") else CAB
        c.font = CAB_FONTE
        c.border = BORDA
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[LINHA_CABECALHO].height = 32
    ws.freeze_panes = ws.cell(PRIMEIRA, 2)
    ultima = get_column_letter(len(colunas))
    ws.auto_filter.ref = f"A{LINHA_CABECALHO}:{ultima}{ULTIMA_VALIDACAO}"


def _lista(ws, colunas, chave, ref) -> None:
    dv = DataValidation(type="list", formula1=ref, allow_blank=True)
    ws.add_data_validation(dv)
    col = _letra(colunas, chave)
    dv.add(f"{col}{PRIMEIRA}:{col}{ULTIMA_VALIDACAO}")


def criar_arquivo() -> Workbook:
    """O arquivo vazio, com as abas, listas, formulas e o painel."""
    wb = Workbook()
    leia = wb.active
    leia.title = ABA_LEIA
    painel = wb.create_sheet(ABA_PAINEL)
    ent = wb.create_sheet(ABA_ENT)
    dev = wb.create_sheet(ABA_DEV)
    gar = wb.create_sheet(ABA_GAR)
    prazos = wb.create_sheet(ABA_PRAZOS)
    listas = wb.create_sheet(ABA_LISTAS)

    # ---- listas -----------------------------------------------------------
    todas = [ETAPAS_ENTREGA, OCORRENCIAS, SIM_NAO, ETAPAS_DEVOLUCAO,
             MOTIVOS_DEVOLUCAO, FORMAS_CREDITO, ETAPAS_GARANTIA,
             SOLUCOES_GARANTIA]
    refs = []
    for j, valores in enumerate(todas, start=1):
        for i, v in enumerate(valores, start=1):
            listas.cell(i, j, v)
        col = get_column_letter(j)
        refs.append(f"{ABA_LISTAS}!${col}$1:${col}${len(valores)}")
    (r_etapa_e, r_ocor, r_simnao, r_etapa_d, r_motivo, r_credito,
     r_etapa_g, r_solucao) = refs
    listas.sheet_state = "hidden"

    # ---- ENTREGAS ---------------------------------------------------------
    _montar_aba(ent, "ENTREGAS — da nota fiscal ao canhoto",
                "O BAP Tools abre uma linha por nota de venda nova (colunas "
                "cinza-azuladas). Daí em diante é com a assistente: etapa, "
                "transportadora, datas, canhoto e ocorrência. SITUAÇÃO e DIAS se "
                "calculam sozinhos pelo prazo da aba PRAZOS.", COLUNAS_ENTREGA)
    _lista(ent, COLUNAS_ENTREGA, "etapa", r_etapa_e)
    _lista(ent, COLUNAS_ENTREGA, "ocorrencia", r_ocor)
    _lista(ent, COLUNAS_ENTREGA, "canhoto", r_simnao)
    sit = _letra(COLUNAS_ENTREGA, "situacao")
    faixa = f"{sit}{PRIMEIRA}:{sit}{ULTIMA_VALIDACAO}"
    ent.conditional_formatting.add(faixa, CellIsRule(
        operator="equal", formula=['"ATRASADA"'], fill=VERMELHO))
    ent.conditional_formatting.add(faixa, CellIsRule(
        operator="equal", formula=['"ENTREGUE COM ATRASO"'], fill=AMARELO))
    et = _letra(COLUNAS_ENTREGA, "etapa")
    ent.conditional_formatting.add(
        f"{et}{PRIMEIRA}:{et}{ULTIMA_VALIDACAO}",
        CellIsRule(operator="equal", formula=['"ENTREGUE"'], fill=VERDE))
    ent.conditional_formatting.add(
        f"{et}{PRIMEIRA}:{et}{ULTIMA_VALIDACAO}",
        CellIsRule(operator="equal", formula=['"OCORRÊNCIA"'], fill=VERMELHO))

    # ---- DEVOLUCOES -------------------------------------------------------
    _montar_aba(dev, "DEVOLUÇÕES — da solicitação ao crédito",
                "Nota de devolução nova entra sozinha (etapa NF DEV EMITIDA). "
                "Pedido que chegou ANTES da nota: abra a linha à mão, etapa "
                "SOLICITADA, e preencha a NF DEVOLUÇÃO quando ela sair — assim "
                "o BAP Tools não abre outra linha para a mesma nota. MOTIVO é "
                "obrigatório: é ele que diz o que corrigir.", COLUNAS_DEVOLUCAO)
    _lista(dev, COLUNAS_DEVOLUCAO, "etapa", r_etapa_d)
    _lista(dev, COLUNAS_DEVOLUCAO, "motivo", r_motivo)
    _lista(dev, COLUNAS_DEVOLUCAO, "credito", r_credito)
    mot = _letra(COLUNAS_DEVOLUCAO, "motivo")
    d0 = _letra(COLUNAS_DEVOLUCAO, "data")
    dev.conditional_formatting.add(
        f"{mot}{PRIMEIRA}:{mot}{ULTIMA_VALIDACAO}",
        FormulaRule(formula=[f'AND(${d0}{PRIMEIRA}<>"",{mot}{PRIMEIRA}="")'],
                    fill=VERMELHO))
    dias = _letra(COLUNAS_DEVOLUCAO, "dias")
    dev.conditional_formatting.add(
        f"{dias}{PRIMEIRA}:{dias}{ULTIMA_VALIDACAO}",
        CellIsRule(operator="greaterThan", formula=["15"], fill=AMARELO))

    # ---- GARANTIAS --------------------------------------------------------
    _montar_aba(gar, "GARANTIAS — da peça recebida ao parecer do fornecedor",
                "Garantia não existe no Protheus: abra a linha à mão. O Nº, os "
                "DIAS EM ABERTO e os DIAS NO FORNECEDOR se calculam sozinhos. "
                "Peça parada no fornecedor é dinheiro preso — a coluna fica "
                "amarela com 15 dias e vermelha com 30.", COLUNAS_GARANTIA)
    _lista(gar, COLUNAS_GARANTIA, "etapa", r_etapa_g)
    _lista(gar, COLUNAS_GARANTIA, "solucao", r_solucao)
    df_ = _letra(COLUNAS_GARANTIA, "dias_fornecedor")
    rng = f"{df_}{PRIMEIRA}:{df_}{ULTIMA_VALIDACAO}"
    gar.conditional_formatting.add(rng, CellIsRule(
        operator="greaterThan", formula=["30"], fill=VERMELHO))
    gar.conditional_formatting.add(rng, CellIsRule(
        operator="between", formula=["15", "30"], fill=AMARELO))

    # as linhas prontas para quem abre a mao
    for aba in (dev, gar):
        _garantir_folga(aba, PRIMEIRA - 1)

    # ---- PRAZOS -----------------------------------------------------------
    prazos["A1"] = "PRAZOS DE ENTREGA (DIAS ÚTEIS a partir da nota)"
    prazos["A1"].font = Font(bold=True, size=14, color=AZUL)
    prazos["A2"] = (f"Capital = {PRAZO_CAPITAL} dias úteis; interior = até "
                    f"{PRAZO_INTERIOR} dias úteis (PADRÃO, linha 5). A busca tenta "
                    "UF|CIDADE, depois a UF, e cai no PADRÃO. Sábado, domingo e os "
                    "FERIADOS da coluna E não contam.")
    prazos["A2"].font = Font(size=9, color="5A6B82")
    for i, t in enumerate(["DESTINO", "DIAS ÚTEIS", "OBSERVAÇÃO", None,
                           "FERIADOS", "FERIADO"], start=1):
        if t:
            c = prazos.cell(LINHA_CABECALHO, i, t)
            c.fill, c.font, c.border = CAB, CAB_FONTE, BORDA
    for i, (k, d, obs) in enumerate(PRAZOS_PADRAO, start=PRIMEIRA):
        prazos.cell(i, 1, k)
        prazos.cell(i, 2, d)
        prazos.cell(i, 3, obs)
    for i, (d, nome) in enumerate(FERIADOS_ENTREGA, start=PRIMEIRA):
        c = prazos.cell(i, 5, datetime.strptime(d, "%Y-%m-%d"))
        c.number_format = "DD/MM/YYYY"
        prazos.cell(i, 6, nome)
    prazos.column_dimensions["A"].width = 24
    prazos.column_dimensions["C"].width = 34
    prazos.column_dimensions["E"].width = 12
    prazos.column_dimensions["F"].width = 28

    _montar_painel(painel)
    _montar_leia_me(leia)
    wb.move_sheet(ABA_PAINEL, offset=-1)
    return wb


def _montar_painel(p) -> None:
    p["A1"] = "PAINEL DO PÓS-VENDA"
    p["A1"].font = Font(bold=True, size=14, color=AZUL)
    p["A2"] = "Tudo aqui é fórmula: muda sozinho quando alguém muda uma etapa."
    p["A2"].font = Font(size=9, color="6B7A8D")
    p.column_dimensions["A"].width = 34
    for col in "BCDEFGH":
        p.column_dimensions[col].width = 16

    def rng(aba, colunas, chave):
        c = _letra(colunas, chave)
        return f"{aba}!${c}${PRIMEIRA}:${c}${ULTIMA_VALIDACAO}"

    def bloco(linha, titulo):
        c = p.cell(linha, 1, titulo)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = CAB
        for col in range(2, 4):
            p.cell(linha, col).fill = CAB
        return linha + 1

    def par(linha, rotulo, formula, fmt=None):
        p.cell(linha, 1, rotulo).border = BORDA
        c = p.cell(linha, 2, formula)
        c.border = BORDA
        if fmt:
            c.number_format = fmt
        return linha + 1

    E, D, G = COLUNAS_ENTREGA, COLUNAS_DEVOLUCAO, COLUNAS_GARANTIA
    n = 4
    n = bloco(n, "ENTREGAS")
    nf_e = rng(ABA_ENT, E, "nf")
    et_e = rng(ABA_ENT, E, "etapa")
    sit_e = rng(ABA_ENT, E, "situacao")
    for etapa in ETAPAS_ENTREGA:
        n = par(n, f"   {etapa}", f'=COUNTIFS({et_e},"{etapa}")')
    n = par(n, "Atrasadas (ainda não entregues)",
            f'=COUNTIFS({sit_e},"ATRASADA")')
    n = par(n, "Entregues no prazo (%)",
            f'=IFERROR(COUNTIFS({sit_e},"NO PRAZO",{rng(ABA_ENT, E, "entregue_em")},"<>")'
            f'/COUNTIFS({rng(ABA_ENT, E, "entregue_em")},"<>"),"")', "0.0%")
    n = par(n, "Entregues sem canhoto",
            f'=COUNTIFS({et_e},"ENTREGUE",{rng(ABA_ENT, E, "canhoto")},"<>SIM")')
    n = par(n, "Notas no acompanhamento", f'=COUNTIFS({nf_e},"<>")')
    n += 1
    n = bloco(n, "DEVOLUÇÕES")
    et_d = rng(ABA_DEV, D, "etapa")
    val_d = rng(ABA_DEV, D, "valor")
    dt_d = rng(ABA_DEV, D, "data")
    for etapa in ETAPAS_DEVOLUCAO:
        n = par(n, f"   {etapa}", f'=COUNTIFS({et_d},"{etapa}")')
    abertas = (f'COUNTIFS({dt_d},"<>")-COUNTIFS({et_d},"ENCERRADA")'
               f'-COUNTIFS({et_d},"NEGADA")-COUNTIFS({et_d},"CANCELADA")')
    n = par(n, "Em aberto", f"={abertas}")
    n = par(n, "Valor em aberto (R$)",
            f'=SUMIFS({val_d},{dt_d},"<>")-SUMIFS({val_d},{et_d},"ENCERRADA")'
            f'-SUMIFS({val_d},{et_d},"NEGADA")-SUMIFS({val_d},{et_d},"CANCELADA")',
            "#,##0.00")
    n = par(n, "Sem motivo preenchido",
            f'=COUNTIFS({dt_d},"<>",{rng(ABA_DEV, D, "motivo")},"")')
    n += 1
    p.cell(n, 1, "Por motivo").font = Font(bold=True, color=AZUL)
    p.cell(n, 2, "Qtd").font = Font(bold=True, color=AZUL)
    p.cell(n, 3, "Valor R$").font = Font(bold=True, color=AZUL)
    n += 1
    mot_d = rng(ABA_DEV, D, "motivo")
    for motivo in MOTIVOS_DEVOLUCAO:
        p.cell(n, 1, f"   {motivo}").border = BORDA
        p.cell(n, 2, f'=COUNTIFS({mot_d},"{motivo}")').border = BORDA
        c = p.cell(n, 3, f'=SUMIFS({val_d},{mot_d},"{motivo}")')
        c.border, c.number_format = BORDA, "#,##0.00"
        n += 1
    n += 1
    n = bloco(n, "GARANTIAS")
    et_g = rng(ABA_GAR, G, "etapa")
    for etapa in ETAPAS_GARANTIA:
        n = par(n, f"   {etapa}", f'=COUNTIFS({et_g},"{etapa}")')
    dfo = rng(ABA_GAR, G, "dias_fornecedor")
    n = par(n, "No fornecedor há mais de 30 dias",
            f'=COUNTIFS({et_g},"NO FORNECEDOR",{dfo},">30")')
    n = par(n, "No fornecedor entre 15 e 30 dias",
            f'=COUNTIFS({et_g},"NO FORNECEDOR",{dfo},">=15",{dfo},"<=30")')


def _montar_leia_me(ws) -> None:
    ws["A1"] = "ACOMPANHAMENTO DE PÓS-VENDA — BAP"
    ws["A1"].font = Font(bold=True, size=14, color=AZUL)
    texto = [
        "QUEM CUIDA DE QUÊ",
        "• ENTREGAS — Pós-venda e Logística: da nota fiscal ao canhoto.",
        "• DEVOLUÇÕES e GARANTIAS — Devolução e Garantia (Mayara).",
        "• A pré-venda (Juliana) entrega o bastão na nota fiscal: a partir dela o pedido aparece aqui.",
        "",
        "A REGRA (a mesma da SOLICITACAO_BAP)",
        "• O BAP Tools ABRE a linha sozinho nas rodadas das 08h e 14h: nota de venda nova → ENTREGAS (FATURADA);",
        "  nota de devolução nova → DEVOLUÇÕES (NF DEV EMITIDA). As colunas de cabeçalho cinza-azulado são dele.",
        "• Daí em diante a linha é 100% da assistente. O script NUNCA mexe numa linha que já está gravada.",
        "• Garantia não existe no Protheus: é aberta à mão, na próxima linha vazia.",
        "• Devolução que chegou antes da nota: abra à mão (SOLICITADA) e, quando a nota sair, escreva a",
        "  NF DEVOLUÇÃO na mesma linha — assim o BAP Tools reconhece e não abre outra.",
        "",
        "AS ETAPAS",
        f"• Entrega: {' → '.join(ETAPAS_ENTREGA)}.",
        f"• Devolução: {' → '.join(ETAPAS_DEVOLUCAO)}.",
        f"• Garantia: {' → '.join(ETAPAS_GARANTIA)}.",
        "",
        "O QUE SE CALCULA SOZINHO",
        f"• PREVISTA ATÉ = data da nota + prazo do destino em DIAS ÚTEIS (aba PRAZOS: capital {PRAZO_CAPITAL}, interior {PRAZO_INTERIOR}). SITUAÇÃO = no prazo / atrasada / entregue com atraso.",
        "• DIAS (entregas) = dias corridos desde a nota, só para leitura; o prazo é medido em dias úteis.",
        "• DIAS EM ABERTO das devoluções e garantias, e DIAS NO FORNECEDOR das garantias.",
        "• A aba PAINEL junta tudo — e o Gerador de Meta (aba 4. Indicadores executivos) lê este arquivo.",
        "",
        "Os feriados da aba PRAZOS (coluna E) cobrem 2026 e 2027. Acrescente os anos seguintes e, se quiser, os locais.",
    ]
    for i, t in enumerate(texto, start=3):
        c = ws.cell(i, 1, t)
        if t and t == t.upper() and not t.startswith("•"):
            c.font = Font(bold=True, color=AZUL)
        elif t.startswith("A VALIDAR"):
            c.font = Font(bold=True, color="B3261E")
    ws.column_dimensions["A"].width = 125


# ---------------------------------------------------------------------------
# as linhas: escrever e ler
# ---------------------------------------------------------------------------
def _ultima_com_dado(ws, colunas) -> int:
    """A ultima linha com algum dado de verdade (formula nao conta)."""
    ultima = PRIMEIRA - 1
    cols = [i for i, c in enumerate(colunas, start=1) if c[3] != "f"
            and not c[3].startswith("f ")]
    for linha in ws.iter_rows(min_row=PRIMEIRA, max_col=len(colunas)):
        for idx in cols:
            v = linha[idx - 1].value
            if v not in (None, ""):
                ultima = max(ultima, linha[0].row)
                break
    return ultima


def _formatar_linha(ws, n, colunas) -> None:
    for i, (_t, _k, _w, tipo) in enumerate(colunas, start=1):
        c = ws.cell(n, i)
        c.border = BORDA
        if "data" in tipo:
            c.number_format = "dd/mm/yyyy"
        elif "valor" in tipo:
            c.number_format = "#,##0.00"
        if tipo.startswith("sis"):
            c.fill = CINZA


def _gravar_formulas(ws, n) -> None:
    colunas, fabrica = FORMULAS[ws.title]
    for chave, formula in fabrica(n).items():
        ws[f"{_letra(colunas, chave)}{n}"] = formula


def _garantir_folga(ws, ultima_dado: int) -> None:
    """Deixa formula e formato prontos nas proximas linhas vazias."""
    colunas = FORMULAS[ws.title][0]
    for n in range(ultima_dado + 1, ultima_dado + 1 + FOLGA_DE_FORMULAS):
        if n > ULTIMA_VALIDACAO:
            break
        _gravar_formulas(ws, n)
        _formatar_linha(ws, n, colunas)


def _escrever(ws, n, colunas, registro: dict) -> None:
    for i, (_t, chave, _w, tipo) in enumerate(colunas, start=1):
        if tipo.startswith("f") or chave not in registro:
            continue
        ws.cell(n, i, registro[chave])
    _gravar_formulas(ws, n)
    _formatar_linha(ws, n, colunas)


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _digitos(v) -> str:
    """'000000046' e 46 sao a mesma nota."""
    s = re.sub(r"\D", "", _texto(v))
    return s.lstrip("0") or ("0" if s else "")


def _data(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _texto(v)
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None


def _numero(v) -> float:
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = _texto(v).replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def chave_nf(filial, nf, serie="") -> str:
    return f"{_texto(filial)}|{_digitos(nf)}|{_texto(serie)}"


# ---------------------------------------------------------------------------
# o que vem da TABELA_BAP
# ---------------------------------------------------------------------------
def _nomes_dos_vendedores(pasta: Path) -> dict:
    try:
        cfg = json.loads((pasta / "planner_config.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return {_texto(p.get("cod_protheus")): _texto(p.get("nome"))
            for p in cfg.get("pessoas") or []}


def notas_da_tabela(caminho_tabela, desde: date = INICIO_PADRAO,
                    pasta_config: Path | None = None) -> tuple:
    """
    (entregas, devolucoes): uma entrada por NOTA, a partir de `desde`.

    A ftPedidos tem uma linha por ITEM da nota. Aqui elas viram uma por nota
    - filial + numero + serie -, com o valor somado e os produtos juntos.
    Na devolucao, o D2_PEDIDO guarda a NOTA DE ORIGEM (e assim que a propria
    TABELA_BAP liga a devolucao a venda, no STATUS VENDA).
    """
    wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    try:
        clientes = {}
        if "dClientesBap" in wb.sheetnames:
            ws = wb["dClientesBap"]
            it = ws.iter_rows(values_only=True)
            cab = [_texto(c) for c in next(it)]

            def col(nome):
                return cab.index(nome) if nome in cab else None
            i_cod, i_nome, i_fant = col("A1_COD"), col("A1_NOME"), col("A1_NREDUZ")
            i_mun, i_uf = col("A1_MUN"), col("A1_EST")
            for r in it:
                cod = _texto(r[i_cod]) if i_cod is not None else ""
                if cod and cod not in clientes:
                    clientes[cod] = {
                        "nome": _texto(r[i_nome]) if i_nome is not None else "",
                        "cidade": _texto(r[i_mun]).upper() if i_mun is not None else "",
                        "uf": _texto(r[i_uf]).upper() if i_uf is not None else "",
                    }
        cidade_filial = {}
        if "Filiais" in wb.sheetnames:
            for r in wb["Filiais"].iter_rows(min_row=2, values_only=True):
                if r and r[4] is not None and _texto(r[4]) not in cidade_filial:
                    cidade_filial[_texto(r[4])] = _texto(r[2])
        ws = wb["ftPedidos"]
        it = ws.iter_rows(values_only=True)
        cab = [_texto(c) for c in next(it)]

        def col(*nomes):
            for n in nomes:
                if n in cab:
                    return cab.index(n)
            return None
        i = {k: col(*v) for k, v in {
            "filial": ("D2_FILIAL",), "cliente": ("D2_CLIENTE",),
            "vend": ("C5_VEND1",), "emissao": ("D2_EMISSAO",),
            "doc": ("D2_DOC",), "pedido": ("D2_PEDIDO",),
            "serie": ("D2_SERIE",), "tipo": ("TIPO",), "cod": ("D2_COD",),
            "qtd": ("D2_QUANT",), "preco": ("PRECO_VENDA",),
            "valor": ("VALOR TOTAL",), "razao": ("RAZÃO_SOCIAL",)}.items()}
        if None in (i["filial"], i["doc"], i["tipo"], i["emissao"]):
            raise ValueError("A ftPedidos não tem D2_FILIAL, D2_DOC, TIPO ou "
                             "D2_EMISSAO.")
        notas = {"VND": {}, "DEV": {}}
        data_da_venda = {}
        for r in it:
            tipo = _texto(r[i["tipo"]]).upper()
            if tipo not in ("VND", "DEV"):
                continue
            emissao = _data(r[i["emissao"]])
            filial = _texto(r[i["filial"]])
            if tipo == "VND" and emissao:
                k = (filial, _digitos(r[i["doc"]]))
                data_da_venda.setdefault(k, emissao)
            if emissao is None or emissao < desde:
                continue
            chave = chave_nf(filial, r[i["doc"]],
                             r[i["serie"]] if i["serie"] is not None else "")
            nota = notas[tipo].get(chave)
            if nota is None:
                cod = _texto(r[i["cliente"]]) if i["cliente"] is not None else ""
                info = clientes.get(cod, {})
                nota = notas[tipo][chave] = {
                    "chave": chave, "filial": filial,
                    "cidade_filial": cidade_filial.get("4" + filial, ""),
                    "doc": _texto(r[i["doc"]]),
                    "serie": _texto(r[i["serie"]]) if i["serie"] is not None else "",
                    "pedido": _texto(r[i["pedido"]]) if i["pedido"] is not None else "",
                    "data": emissao, "cod_cliente": cod,
                    "cliente": (info.get("nome")
                                or (_texto(r[i["razao"]]) if i["razao"] is not None else "")),
                    "cidade": info.get("cidade", ""), "uf": info.get("uf", ""),
                    "vend": _texto(r[i["vend"]]) if i["vend"] is not None else "",
                    "valor": 0.0, "itens": 0, "produtos": defaultdict(float),
                }
            if i["valor"] is not None and isinstance(r[i["valor"]], (int, float)):
                valor = float(r[i["valor"]])
            else:
                valor = (_numero(r[i["qtd"]]) * _numero(r[i["preco"]])
                         if i["qtd"] is not None and i["preco"] is not None else 0.0)
            nota["valor"] += valor
            nota["itens"] += 1
            if i["cod"] is not None:
                nota["produtos"][_texto(r[i["cod"]])] += abs(
                    _numero(r[i["qtd"]]) if i["qtd"] is not None else 0)
    finally:
        wb.close()

    nomes = _nomes_dos_vendedores(pasta_config or Path(caminho_tabela).parent.parent)

    def vendedor(cod):
        nome = nomes.get(cod) or nomes.get(cod.zfill(6)) or ""
        return f"{cod} - {nome}" if nome else cod

    entregas = [{
        "nf": n["doc"], "serie": n["serie"], "data_nf": n["data"],
        "cliente": n["cliente"], "cidade": n["cidade"], "uf": n["uf"],
        "valor": round(n["valor"], 2), "etapa": ETAPAS_ENTREGA[0],
        "cod_cliente": n["cod_cliente"], "vendedor": vendedor(n["vend"]),
        "filial": n["filial"], "cidade_filial": n["cidade_filial"],
        "pedido": n["pedido"], "itens": n["itens"], "chave": n["chave"],
    } for n in sorted(notas["VND"].values(), key=lambda x: (x["data"], x["doc"]))]

    devolucoes = []
    for n in sorted(notas["DEV"].values(), key=lambda x: (x["data"], x["doc"])):
        produtos = sorted(n["produtos"].items(), key=lambda x: -x[1])
        texto = "; ".join(f"{p} x{q:g}" for p, q in produtos[:4])
        if len(produtos) > 4:
            texto += f"; +{len(produtos) - 4}"
        devolucoes.append({
            "data": n["data"], "nf_dev": n["doc"], "nf_origem": n["pedido"],
            "data_venda": data_da_venda.get((n["filial"], _digitos(n["pedido"]))),
            "cliente": n["cliente"], "vendedor": vendedor(n["vend"]),
            "valor": round(abs(n["valor"]), 2), "produtos": texto,
            "etapa": "NF DEV EMITIDA", "cod_cliente": n["cod_cliente"],
            "filial": n["filial"], "origem": "BAP Tools", "chave": n["chave"],
        })
    return entregas, devolucoes


# ---------------------------------------------------------------------------
# acrescentar: so linha nova, nunca mexe na que ja existe
# ---------------------------------------------------------------------------
def _chaves_existentes(ws, colunas) -> set:
    i_chave = [c[1] for c in colunas].index("chave")
    return {_texto(r[i_chave]) for r in ws.iter_rows(min_row=PRIMEIRA,
                                                      values_only=True)
            if r and i_chave < len(r) and _texto(r[i_chave])}


def _nfs_de_devolucao_existentes(ws) -> set:
    """
    As notas de devolucao que ja tem linha - inclusive a aberta A MAO, que
    nao tem CHAVE mas tem a NF DEVOLUCAO escrita pela assistente.
    """
    nomes = [c[1] for c in COLUNAS_DEVOLUCAO]
    i_nf, i_fil = nomes.index("nf_dev"), nomes.index("filial")
    saida = set()
    for r in ws.iter_rows(min_row=PRIMEIRA, values_only=True):
        if not r or i_nf >= len(r):
            continue
        nf = _digitos(r[i_nf])
        if nf:
            saida.add((_texto(r[i_fil]) if i_fil < len(r) else "", nf))
            saida.add(("", nf))
    return saida


def acrescentar(wb, entregas: list, devolucoes: list,
                agora: datetime | None = None) -> dict:
    """
    Poe no fim de cada aba SO o que ainda nao tem linha. Devolve quantas
    entraram. Linha que ja existe nao e lida para nada alem da chave.
    """
    agora = agora or datetime.now().replace(second=0, microsecond=0)
    resumo = {"entregas": 0, "devolucoes": 0}

    ws = wb[ABA_ENT]
    _garantir_cabecalho(ws, COLUNAS_ENTREGA)     # (16/10) FRETE REAL R$
    ja = _chaves_existentes(ws, COLUNAS_ENTREGA)
    n = _ultima_com_dado(ws, COLUNAS_ENTREGA) + 1
    for e in entregas:
        if e["chave"] in ja:
            continue
        _escrever(ws, n, COLUNAS_ENTREGA, {**e, "aberta_em": agora})
        ja.add(e["chave"])
        n += 1
        resumo["entregas"] += 1

    ws = wb[ABA_DEV]
    ja = _chaves_existentes(ws, COLUNAS_DEVOLUCAO)
    ja_nf = _nfs_de_devolucao_existentes(ws)
    n = _ultima_com_dado(ws, COLUNAS_DEVOLUCAO) + 1
    for d in devolucoes:
        nf = _digitos(d["nf_dev"])
        if (d["chave"] in ja or (d["filial"], nf) in ja_nf
                or ("", nf) in ja_nf and _so_manual_sem_filial(ws, nf)):
            continue
        _escrever(ws, n, COLUNAS_DEVOLUCAO, {**d, "aberta_em": agora})
        ja.add(d["chave"])
        n += 1
        resumo["devolucoes"] += 1
    _garantir_folga(ws, n - 1)
    _garantir_folga(wb[ABA_GAR], _ultima_com_dado(wb[ABA_GAR], COLUNAS_GARANTIA))
    return resumo


def _garantir_cabecalho(ws, colunas) -> int:
    """(16/10) Coluna nova (no fim) num arquivo de antes dela: escreve o
    titulo, a cor e a largura. Devolve quantas colunas ganharam titulo."""
    n = 0
    for i, (t, _k, w, tipo) in enumerate(colunas, start=1):
        c = ws.cell(LINHA_CABECALHO, i)
        if c.value not in (None, ""):
            continue
        c.value = t
        c.fill = CAB_SIS if tipo.startswith("sis") else CAB
        c.font = CAB_FONTE
        c.border = BORDA
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
        n += 1
    return n


def valor_digitado(v):
    """(16/10) O valor que a assistente escreveu (R$ 1.234,56 · 278,4 ·
    278.40 · 1234) como numero. Vazio = None. Texto que nao e numero:
    ValueError."""
    if v is None or isinstance(v, (int, float)):
        return None if v is None else float(v)
    s = str(v).strip().upper().replace("R$", "").replace(" ", "")
    if s == "":
        return None
    neg = s.startswith("-")
    s = s.lstrip("+-")
    if "," in s:                       # 1.234,56 / 278,4
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1
                              and len(s.split(".")[1]) == 3):
        s = s.replace(".", "")         # 1.234 = mil duzentos e trinta e 4
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        raise ValueError(f"Valor inválido: {v}")
    return -float(s) if neg else float(s)


def _so_manual_sem_filial(ws, nf: str) -> bool:
    """A nota foi escrita a mao numa linha SEM filial? Entao ja e dela."""
    nomes = [c[1] for c in COLUNAS_DEVOLUCAO]
    i_nf, i_fil = nomes.index("nf_dev"), nomes.index("filial")
    for r in ws.iter_rows(min_row=PRIMEIRA, values_only=True):
        if r and i_nf < len(r) and _digitos(r[i_nf]) == nf \
                and not (_texto(r[i_fil]) if i_fil < len(r) else ""):
            return True
    return False


def atualizar_arquivo(caminho_tabela, destino, desde: date = INICIO_PADRAO,
                      pasta_config: Path | None = None) -> dict:
    """
    Abre (ou cria) o acompanhamento, acrescenta as notas novas e grava em
    `destino`. Quem chama decide onde gravar e como trocar o arquivo.
    """
    destino = Path(destino)
    entregas, devolucoes = notas_da_tabela(caminho_tabela, desde, pasta_config)
    novo = not destino.exists()
    wb = criar_arquivo() if novo else load_workbook(destino)
    resumo = acrescentar(wb, entregas, devolucoes)
    try:
        wb.calculation.fullCalcOnLoad = True
    except Exception:                                   # noqa: BLE001
        pass
    return {"wb": wb, "novo": novo, **resumo,
            "notas_lidas": len(entregas), "devolucoes_lidas": len(devolucoes)}


# ---------------------------------------------------------------------------
# a leitura para os programas BAP (indicadores)
# ---------------------------------------------------------------------------
def _linhas(ws, colunas) -> list[dict]:
    chaves = [c[1] for c in colunas]
    saida = []
    for r in ws.iter_rows(min_row=PRIMEIRA, max_col=len(colunas),
                          values_only=True):
        d = {k: (r[i] if i < len(r) else None) for i, k in enumerate(chaves)}
        tem = any(d[k] not in (None, "") for k, c in zip(chaves, colunas)
                  if not c[3].startswith("f"))
        if tem:
            saida.append(d)
    return saida


def _prazos(ws) -> tuple[dict, int, set]:
    mapa, padrao, feriados = {}, PRAZO_INTERIOR, set()
    for r in ws.iter_rows(min_row=PRIMEIRA, values_only=True):
        if not r:
            continue
        if len(r) > 4 and _data(r[4]):
            feriados.add(_data(r[4]))
        if not r[0]:
            continue
        k, d = _sem_acento(_texto(r[0])), _numero(r[1])
        if k == "PADRAO":
            padrao = int(d)
        else:
            mapa[k] = int(d)
    return mapa, padrao, feriados


def _feriados_padrao() -> set:
    return {datetime.strptime(d, "%Y-%m-%d").date() for d, _ in FERIADOS_ENTREGA}


def ler_acompanhamento(caminho, hoje: date | None = None) -> dict:
    """
    As tres abas, com atraso e dias calculados AQUI (sem depender do Excel
    ter recalculado), e os numeros que vao para o Gerador de Meta.
    """
    hoje = hoje or date.today()
    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        ent = _linhas(wb[ABA_ENT], COLUNAS_ENTREGA)
        dev = _linhas(wb[ABA_DEV], COLUNAS_DEVOLUCAO)
        gar = _linhas(wb[ABA_GAR], COLUNAS_GARANTIA)
        prazos, padrao, feriados = (_prazos(wb[ABA_PRAZOS])
                                    if ABA_PRAZOS in wb.sheetnames
                                    else ({}, PRAZO_INTERIOR, set()))
        feriados = feriados or _feriados_padrao()
    finally:
        wb.close()
    # (09/10) o diario de edicoes por cima: o que foi editado aparece mesmo
    # que o arquivo desta maquina ainda esteja atrasado
    diario = ler_diario(pasta_do_diario(caminho))
    sobrepor_diario(ent, ABA_ENT, diario)
    sobrepor_diario(dev, ABA_DEV, diario)
    # (10/10) o SLA cadastrado no BAP Analista › Entrega › Parametros
    # (cidade > filial) vale por cima da aba PRAZOS; sem cadastro, a aba
    try:
        import transportadoras as _tr                   # noqa: PLC0415
        sla_cad = _tr.ler_sla(Path(caminho).resolve().parent.parent)
    except Exception:                                   # noqa: BLE001
        _tr, sla_cad = None, {}

    for e in ent:
        d = _data(e["data_nf"])
        e["data_nf"] = d
        # (30/10) etapa antiga aparece como a nova (o arquivo nao muda)
        et_ = _texto(e.get("etapa")).upper()
        if et_ in ETAPA_ANTIGA:
            e["etapa"] = ETAPA_ANTIGA[et_]
        uf, cid = _sem_acento(_texto(e["uf"])), _sem_acento(_texto(e["cidade"]))
        dias = prazos.get(f"{uf}|{cid}", prazos.get(uf, padrao))
        if _tr is not None and sla_cad:
            n_sla, _o = _tr.sla_de(sla_cad, uf, e["cidade"],
                                   e.get("cidade_filial"))
            if n_sla is not None:
                dias = n_sla
        e["prevista"] = somar_dias_uteis(d, dias, feriados) if d else None
        # (30/10) a previsao calculada fica guardada (os farois refazem a
        # conta pela data do pedido a partir dela); a AJUSTADA na tela manda
        e["prevista_nf"] = e["prevista"]
        manual = _data(e.get("prevista_manual"))
        e["prevista_manual"] = manual
        if manual:
            e["prevista"] = manual
        entregue = _data(e["entregue_em"])
        e["entregue_em"] = entregue
        etapa = _texto(e["etapa"]).upper()
        if etapa == "CANCELADA" or not d:
            e["situacao"] = "—"
        elif entregue:
            e["situacao"] = ("NO PRAZO" if entregue <= e["prevista"]
                             else "ENTREGUE COM ATRASO")
        else:
            e["situacao"] = "ATRASADA" if hoje > e["prevista"] else "NO PRAZO"
        e["dias"] = ((entregue or hoje) - d).days if d else None
    for x in dev:
        x["data"] = _data(x["data"])
        etapa = _texto(x["etapa"]).upper()
        x["aberta"] = etapa not in ENCERRADAS_DEV
        x["dias"] = (hoje - x["data"]).days if x["data"] and x["aberta"] else None
        x["valor"] = _numero(x["valor"])
    for g in gar:
        g["aberta_em"] = _data(g["aberta_em"])
        g["enviada_em"] = _data(g["enviada_em"])
        g["parecer_em"] = _data(g["parecer_em"])
        etapa = _texto(g["etapa"]).upper()
        g["aberta"] = etapa not in ENCERRADAS_GAR
        g["dias_fornecedor"] = (((g["parecer_em"] or hoje) - g["enviada_em"]).days
                                if g["enviada_em"] else None)
    return {"entregas": ent, "devolucoes": dev, "garantias": gar,
            "indicadores": indicadores(ent, dev, gar, hoje)}


def indicadores(ent, dev, gar, hoje: date) -> dict:
    """Os numeros do mes corrente que o Gerador de Meta mostra."""
    def do_mes(d):
        return d is not None and d.year == hoje.year and d.month == hoje.month
    entregues = [e for e in ent if e["entregue_em"]]
    no_prazo = [e for e in entregues if e["situacao"] == "NO PRAZO"]
    dev_mes = [x for x in dev if do_mes(x["data"])]
    por_motivo = defaultdict(lambda: [0, 0.0])
    for x in dev_mes:
        m = _texto(x["motivo"]).upper() or "(SEM MOTIVO)"
        por_motivo[m][0] += 1
        por_motivo[m][1] += x["valor"]
    no_forn = [g for g in gar if _texto(g["etapa"]).upper() == "NO FORNECEDOR"]
    return {
        "entregas_atrasadas": sum(1 for e in ent if e["situacao"] == "ATRASADA"),
        "entregas_no_prazo_pct": (len(no_prazo) / len(entregues) * 100.0
                                  if entregues else None),
        "entregas_sem_canhoto": sum(
            1 for e in ent if _texto(e["etapa"]).upper() == "ENTREGUE"
            and _texto(e["canhoto"]).upper() != "SIM"),
        "devolucoes_mes_qtd": len(dev_mes),
        "devolucoes_mes_valor": round(sum(x["valor"] for x in dev_mes), 2),
        "devolucoes_abertas": sum(1 for x in dev if x["aberta"]),
        "devolucoes_sem_motivo": sum(1 for x in dev if not _texto(x["motivo"])),
        "devolucoes_por_motivo": {k: tuple(v) for k, v in
                                  sorted(por_motivo.items(), key=lambda i: -i[1][1])},
        "garantias_abertas": sum(1 for g in gar if g["aberta"]),
        "garantias_no_fornecedor_30": sum(
            1 for g in no_forn if (g["dias_fornecedor"] or 0) > 30),
    }


# ---------------------------------------------------------------------------
# EDICAO PELOS RELATORIOS (BAP Central) - a assistente escolhe na lista e
# salva; aqui so as colunas DELA (as "ass") sao gravadas, nunca as do
# sistema. A linha e achada pela CHAVE. Nada de linha nova.
# ---------------------------------------------------------------------------
TRANSPORTADORAS_PADRAO = ["PRÓPRIA (BAP)", "RETIRA NO BALCÃO", "CORREIOS",
                          "TRANSPORTADORA TERCEIRIZADA"]
COLUNA_TRANSPORTADORAS = 9          # coluna I da aba Listas (oculta)
COLUNAS_DA_ABA = {ABA_ENT: COLUNAS_ENTREGA, ABA_DEV: COLUNAS_DEVOLUCAO,
                  ABA_GAR: COLUNAS_GARANTIA}


def transportadoras(caminho=None) -> list:
    """
    A lista de transportadoras que a assistente escolhe: o cadastro do
    Analista (BAP Analista > Lista de transportadoras, no
    transportadoras_config.json). caminho = o ACOMPANHAMENTO_POS_VENDA (a
    pasta dos programas e dois niveis acima).
    """
    import transportadoras as tr                         # noqa: PLC0415
    raiz = Path(caminho).resolve().parent.parent if caminho else None
    return tr.nomes(tr.carregar(raiz))


def transportadoras_antigas(caminho=None) -> list:
    """A lista de antes do cadastro (so para a primeira carga dele): a
    coluna I da aba Listas, as que ja estao nas ENTREGAS e o padrao."""
    nomes = list(TRANSPORTADORAS_PADRAO)
    if caminho and Path(caminho).exists():
        try:
            wb = load_workbook(caminho, read_only=True, data_only=True)
            try:
                if ABA_LISTAS in wb.sheetnames:
                    for r in wb[ABA_LISTAS].iter_rows(
                            min_col=COLUNA_TRANSPORTADORAS,
                            max_col=COLUNA_TRANSPORTADORAS, values_only=True):
                        if r and r[0]:
                            nomes.append(_texto(r[0]).upper())
                if ABA_ENT in wb.sheetnames:
                    for d in _linhas(wb[ABA_ENT], COLUNAS_ENTREGA):
                        if d.get("transportadora"):
                            nomes.append(_texto(d["transportadora"]).upper())
            finally:
                wb.close()
        except Exception:                               # noqa: BLE001
            pass
    vistos, saida = set(), []
    for n in nomes:
        if n and n not in vistos:
            vistos.add(n)
            saida.append(n)
    return saida


def gravar_edicoes(caminho, aba: str, edicoes: dict) -> int:
    """
    edicoes = {chave: {campo: valor}}. Grava so nas colunas da assistente
    ("ass"); data vira data do Excel; "" limpa a celula. Devolve quantas
    celulas mudaram. Levanta PermissionError se o arquivo estiver aberto
    (Excel) - quem chama avisa a assistente.
    """
    colunas = COLUNAS_DA_ABA[aba]
    chaves = [c[1] for c in colunas]
    tipos = {c[1]: c[3] for c in colunas}
    for campos in edicoes.values():
        for campo in campos:
            if campo not in tipos or not tipos[campo].startswith("ass"):
                raise ValueError(f"A coluna {campo} nao e da assistente - "
                                 f"so o sistema escreve nela.")
    if "chave" not in chaves:
        raise ValueError(f"A aba {aba} nao tem CHAVE.")
    # (16/10) valor (FRETE REAL R$): o que se digitou vira numero
    edicoes = {k: {campo: (("" if valor_digitado(v) is None
                            else valor_digitado(v))
                           if "valor" in tipos[campo] else v)
                   for campo, v in campos.items()}
               for k, campos in edicoes.items()}
    caminho = Path(caminho)
    # (09/10) primeiro o DIARIO: a edicao fica guardada mesmo que o Excel
    # esteja aberto ou que esta maquina nao seja a que grava o arquivo
    pasta = pasta_do_diario(caminho)
    registros = [(aba, str(k), campo, _norm(v, tipos[campo]))
                 for k, campos in edicoes.items()
                 for campo, v in campos.items()]
    no_diario = registrar_no_diario(pasta, registros, "app")
    if not pode_gravar_aqui():
        if not no_diario:
            raise OSError(f"Nao consegui gravar o diario de edicoes em "
                          f"{pasta} - tente de novo.")
        return len(registros)
    wb = load_workbook(caminho)
    colher_do_excel(wb, pasta, _quando_do_arquivo(caminho))
    ws = wb[aba]
    _garantir_cabecalho(ws, colunas)             # (16/10) coluna nova
    i_chave = chaves.index("chave") + 1
    pendentes = {str(k): v for k, v in edicoes.items()}
    mudou = 0
    for n in range(PRIMEIRA, ws.max_row + 1):
        k = _texto(ws.cell(n, i_chave).value)
        if k not in pendentes:
            continue
        for campo, valor in pendentes.pop(k).items():
            col = chaves.index(campo) + 1
            cel = ws.cell(n, col)
            if "data" in tipos[campo]:
                valor = _data(valor) if valor not in (None, "") else None
                if valor is not None:
                    valor = datetime(valor.year, valor.month, valor.day)
                    cel.number_format = "dd/mm/yyyy"
            elif valor == "":
                valor = None
            elif "valor" in tipos[campo]:
                cel.number_format = "#,##0.00"
            if cel.value != valor:
                cel.value = valor
                mudou += 1
        if not pendentes:
            break
    if pendentes:
        raise ValueError(f"Nao achei no {caminho.name} a(s) linha(s): "
                         f"{', '.join(pendentes)}")
    aplicar_diario(wb, pasta)          # e o que outra versao tenha apagado
    try:
        wb.calculation.fullCalcOnLoad = True
    except Exception:                                   # noqa: BLE001
        pass
    tmp = caminho.with_name(f"~salvando_{caminho.name}")
    wb.save(tmp)
    try:
        import os                                       # noqa: PLC0415
        os.replace(tmp, caminho)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    guardar_leitura(pasta, foto_do_arquivo(wb))
    return mudou


def _quando_do_arquivo(caminho) -> str:
    """A hora do arquivo (para o que foi colhido dele no diario) - nunca
    depois de agora."""
    try:
        t = min(Path(caminho).stat().st_mtime, datetime.now().timestamp())
        return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return _agora()


# ---------------------------------------------------------------------------
# DIARIO DE EDICOES (09/10/2026)
#
# O que aconteceu em 09/10: uma maquina ligou com a copia do OneDrive
# atrasada, rodou o BAP Central e trocou o arquivo pela versao velha dela -
# todas as edicoes da vespera sumiram. O Excel sozinho nao tem como se
# defender disso, entao cada edicao passa a ficar TAMBEM num diario:
#
#   RELATORIOS\_EDICOES_POS_VENDA\EDICOES_<MAQUINA>.csv
#       uma linha por campo editado (QUANDO, MAQUINA, ORIGEM, ABA, CHAVE,
#       CAMPO, VALOR). Cada maquina so escreve no SEU arquivo e so
#       acrescenta - nunca apaga, nunca reescreve.
#   RELATORIOS\_EDICOES_POS_VENDA\LEITURA_<MAQUINA>.json
#       o que a maquina que grava viu no arquivo da ultima vez - e assim
#       que ela percebe o que a assistente mudou direto no Excel.
#
# Regras:
#   * vale a edicao MAIS RECENTE de cada campo, de qualquer maquina;
#   * edicao feita no BAP (Farol) vai para o diario na hora - mesmo com o
#     Excel aberto, nada se perde;
#   * edicao feita direto no Excel entra no diario na rodada seguinte;
#   * campo que "volta" a ficar vazio, ou ETAPA que volta para tras, sem
#     passar pelo BAP, e tratado como versao velha do arquivo e e
#     restaurado. Para limpar um campo ou voltar uma etapa, use o BAP;
#   * so UMA maquina grava o arquivo (MAQUINA_DO_POS_VENDA). As outras
#     leem e mostram o diario por cima - nunca trocam o arquivo.
# ---------------------------------------------------------------------------
import csv as _csv
import os as _os
import platform as _platform

# a maquina que fica ligada e roda o BAP Central de hora em hora. Vazio =
# qualquer maquina grava (o jeito antigo, sujeito a copia atrasada)
MAQUINA_DO_POS_VENDA = "NT-AMADMVD13"
PASTA_DIARIO = "_EDICOES_POS_VENDA"
CAMPOS_DIARIO = ["QUANDO", "MAQUINA", "ORIGEM", "ABA", "CHAVE", "CAMPO",
                 "VALOR"]
ETAPA_INICIAL = {ABA_ENT: ETAPAS_ENTREGA[0], ABA_DEV: "NF DEV EMITIDA"}
_ORDEM_ETAPA = {ABA_ENT: ORDEM_ETAPA_ENTREGA, ABA_DEV: ETAPAS_DEVOLUCAO}
ETAPA_INICIAL_ANTIGA = {ABA_ENT: "FATURADA"}


def maquina() -> str:
    nome = _os.environ.get("COMPUTERNAME") or _platform.node() or "MAQUINA"
    return re.sub(r"[^A-Za-z0-9_-]", "_", nome).upper()


def pode_gravar_aqui() -> bool:
    return (not MAQUINA_DO_POS_VENDA
            or maquina() == MAQUINA_DO_POS_VENDA.strip().upper())


def pasta_do_diario(caminho_arquivo) -> Path:
    return Path(caminho_arquivo).parent / PASTA_DIARIO


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _abas_com_chave() -> dict:
    return {aba: cols for aba, cols in COLUNAS_DA_ABA.items()
            if "chave" in [c[1] for c in cols]}


def _norm(v, tipo: str) -> str:
    """O valor como texto comparavel (o que vai para o diario)."""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return (v.date() if isinstance(v, datetime) else v).isoformat()
    if "data" in tipo:
        d = _data(v)
        return d.isoformat() if d else str(v).strip()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _para_celula(s: str, tipo: str):
    if s == "":
        return None
    if "data" in tipo:
        d = _data(s)
        return datetime(d.year, d.month, d.day) if d else s
    if "valor" in tipo:
        try:
            return float(s)
        except ValueError:
            return s
    return s


def _rank(aba, etapa) -> int:
    ordem = _ORDEM_ETAPA.get(aba, [])
    e = _texto(etapa).upper()
    return ordem.index(e) if e in ordem else -1


def registrar_no_diario(pasta, registros, origem: str,
                        quando: str | None = None) -> int:
    """registros = [(aba, chave, campo, valor)]. Acrescenta no arquivo DESTA
    maquina. Devolve quantas linhas entraram (0 se nao deu para gravar)."""
    if not registros:
        return 0
    pasta = Path(pasta)
    arq = pasta / f"EDICOES_{maquina()}.csv"
    quando = quando or _agora()
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        novo = not arq.exists()
        with open(arq, "a", newline="",
                  encoding="utf-8-sig" if novo else "utf-8") as f:
            w = _csv.writer(f, delimiter=";")
            if novo:
                w.writerow(CAMPOS_DIARIO)
            for aba, chave, campo, valor in registros:
                w.writerow([quando, maquina(), origem, aba, chave, campo,
                            valor])
        return len(registros)
    except OSError:
        return 0


def arquivos_do_diario(pasta) -> list:
    pasta = Path(pasta)
    return sorted(pasta.glob("EDICOES_*.csv")) if pasta.exists() else []


def ler_diario(pasta) -> dict:
    """{(aba, chave, campo): (quando, valor)} - a edicao mais recente de
    cada campo, juntando os diarios de todas as maquinas."""
    saida = {}
    for arq in arquivos_do_diario(pasta):
        try:
            with open(arq, newline="", encoding="utf-8-sig") as f:
                for r in _csv.DictReader(f, delimiter=";"):
                    k = (r.get("ABA") or "", r.get("CHAVE") or "",
                         r.get("CAMPO") or "")
                    q = r.get("QUANDO") or ""
                    if not all(k) or not q:
                        continue
                    if k not in saida or q >= saida[k][0]:
                        saida[k] = (q, r.get("VALOR") or "")
        except (OSError, UnicodeDecodeError, _csv.Error):
            continue
    return saida


def _celulas(wb):
    """(aba, chave, campo, tipo, celula) de cada coluna da assistente das
    linhas com CHAVE."""
    for aba, cols in _abas_com_chave().items():
        if aba not in wb.sheetnames:
            continue
        ws = wb[aba]
        nomes = [c[1] for c in cols]
        i_chave = nomes.index("chave") + 1
        ass = [(i + 1, c[1], c[3]) for i, c in enumerate(cols)
               if c[3].startswith("ass")]
        for n in range(PRIMEIRA, ws.max_row + 1):
            chave = _texto(ws.cell(n, i_chave).value)
            if not chave:
                continue
            for col, campo, tipo in ass:
                yield aba, chave, campo, tipo, ws.cell(n, col)


def _leitura_path(pasta) -> Path:
    return Path(pasta) / f"LEITURA_{maquina()}.json"


def ler_leitura(pasta) -> dict | None:
    try:
        return json.loads(_leitura_path(pasta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def foto_do_arquivo(wb) -> dict:
    return {f"{a}|{k}|{c}": _norm(cel.value, t)
            for a, k, c, t, cel in _celulas(wb)}


def guardar_leitura(pasta, foto: dict) -> None:
    try:
        Path(pasta).mkdir(parents=True, exist_ok=True)
        tmp = _leitura_path(pasta).with_suffix(".tmp")
        tmp.write_text(json.dumps(foto, ensure_ascii=False),
                       encoding="utf-8")
        _os.replace(tmp, _leitura_path(pasta))
    except OSError:
        pass


def colher_do_excel(wb, pasta, quando: str) -> int:
    """
    O que a assistente mudou DIRETO no Excel desde a ultima leitura vai
    para o diario (ORIGEM planilha). Campo que ficou vazio ou ETAPA que
    voltou nao entram: isso e cara de versao velha, e o diario restaura.
    Sem leitura anterior (primeira vez), entra o que difere do diario.
    """
    antes = ler_leitura(pasta)
    diario = ler_diario(pasta)
    novos = []
    etapa_antes = {}
    for a, k, c, t, cel in _celulas(wb):
        v = _norm(cel.value, t)
        if not v:
            continue
        if antes is not None:
            velho = antes.get(f"{a}|{k}|{c}")
            if velho is None:            # linha nova desde a ultima leitura
                velho = ETAPA_INICIAL.get(a, "") if c == "etapa" else ""
            if v == velho:
                continue
            if c == "etapa" and _rank(a, v) < _rank(a, velho):
                continue
        elif c == "etapa" and v in (ETAPA_INICIAL.get(a),
                                    ETAPA_INICIAL_ANTIGA.get(a)):
            continue
        if diario.get((a, k, c), ("", None))[1] == v:
            continue
        novos.append((a, k, c, v))
    return registrar_no_diario(pasta, novos, "planilha", quando)


def aplicar_diario(wb, pasta, diario: dict | None = None) -> int:
    """Poe no arquivo a edicao mais recente de cada campo. Devolve quantas
    celulas voltaram/mudaram."""
    diario = ler_diario(pasta) if diario is None else diario
    if not diario:
        return 0
    mudou = 0
    for a, k, c, t, cel in _celulas(wb):
        reg = diario.get((a, k, c))
        if reg is None or _norm(cel.value, t) == reg[1]:
            continue
        cel.value = _para_celula(reg[1], t)
        if "data" in t and cel.value is not None:
            cel.number_format = "dd/mm/yyyy"
        mudou += 1
    return mudou


def sobrepor_diario(linhas: list, aba: str, diario: dict) -> int:
    """Para a LEITURA (farois): o diario por cima do que o arquivo tem."""
    cols = _abas_com_chave().get(aba)
    if not cols or not diario:
        return 0
    tipos = {c[1]: c[3] for c in cols if c[3].startswith("ass")}
    mudou = 0
    for d in linhas:
        k = _texto(d.get("chave"))
        if not k:
            continue
        for campo, tipo in tipos.items():
            reg = diario.get((aba, k, campo))
            if reg is None or _norm(d.get(campo), tipo) == reg[1]:
                continue
            v = _para_celula(reg[1], tipo)
            d[campo] = v.date() if isinstance(v, datetime) else v
            mudou += 1
    return mudou


# ---------------------------------------------------------------------------
# (11/10) PRAZOS e Listas: parametro e do ANALISTA. A aba PRAZOS e reescrita
# a partir do SLA cadastrado (BAP Analista › Entrega › Parametros) - uma
# linha UF|CIDADE para cada cidade das entregas, no valor que o BAP usa - e
# as duas abas ficam protegidas (so consulta). Sem SLA cadastrado, a aba
# fica como esta (so ganha a protecao).
# ---------------------------------------------------------------------------
def sincronizar_prazos(wb, raiz) -> bool:
    """Devolve True se mexeu no arquivo."""
    mudou = False
    try:
        import transportadoras as _tr                   # noqa: PLC0415
        sla = _tr.ler_sla(raiz)
    except Exception:                                   # noqa: BLE001
        _tr, sla = None, {}
    if _tr is not None and ABA_PRAZOS in wb.sheetnames and (
            sla.get("filiais") or sla.get("cidades")):
        ws = wb[ABA_PRAZOS]
        desejado = [("PADRÃO", _tr.SLA_FRETE_PADRAO,
                     "cidade sem cadastro: o padrão de frete")]
        vistos = set()
        for k, n in sorted((sla.get("cidades") or {}).items()):
            desejado.append((k, int(n), "cidade cadastrada (BAP Analista)"))
            vistos.add(k)
        if ABA_ENT in wb.sheetnames:
            nomes = [c[1] for c in COLUNAS_ENTREGA]
            i_uf, i_cid, i_fil = (nomes.index("uf"), nomes.index("cidade"),
                                  nomes.index("cidade_filial"))
            for r in wb[ABA_ENT].iter_rows(min_row=PRIMEIRA, values_only=True):
                if not r or i_cid >= len(r):
                    continue
                uf, cid = _texto(r[i_uf]).upper(), _texto(r[i_cid]).upper()
                if not uf or not cid:
                    continue
                k = f"{uf}|{cid}"
                if k in vistos:
                    continue
                vistos.add(k)
                fil = _texto(r[i_fil]) if i_fil < len(r) else ""
                n, origem = _tr.sla_de(sla, uf, cid, fil)
                if n is None:
                    n = _tr.sla_ou_padrao(sla, uf, cid, fil)
                frete = _tr.e_frete(cid)
                desejado.append((k, n, {"cidade": "cidade cadastrada",
                                        "filial": f"filial {fil or uf} · "
                                                  f"{'frete' if frete else 'local'}"
                                        }.get(origem, "padrão")))
        atual = [(ws.cell(i, 1).value, ws.cell(i, 2).value)
                 for i in range(PRIMEIRA, ws.max_row + 1)
                 if ws.cell(i, 1).value not in (None, "")]
        if atual != [(k, d) for k, d, _o in desejado]:
            for i in range(PRIMEIRA, max(ws.max_row, PRIMEIRA) + 1):
                for j in (1, 2, 3):
                    ws.cell(i, j).value = None
            for i, (k, d, obs) in enumerate(desejado, start=PRIMEIRA):
                ws.cell(i, 1, k)
                ws.cell(i, 2, d)
                ws.cell(i, 3, obs)
            ws["A2"] = ("Gerada pelo BAP a partir do SLA cadastrado no BAP "
                        "Analista › Entrega › Parâmetros (dias úteis a partir "
                        "da nota). Só consulta: para mudar, use o BAP "
                        "Analista. Sábado, domingo e os FERIADOS da coluna E "
                        "não contam.")
            mudou = True
    # (30/10) a lista de ETAPA da entrega no Excel (aba Listas, coluna A:
    # a validacao do arquivo aponta para A1:A6) com as etapas novas
    if ABA_LISTAS in wb.sheetnames:
        wl = wb[ABA_LISTAS]
        n_l = max(6, len(ETAPAS_ENTREGA))
        quero = ETAPAS_ENTREGA + [None] * (n_l - len(ETAPAS_ENTREGA))
        if [wl.cell(i, 1).value for i in range(1, n_l + 1)] != quero:
            for i, v in enumerate(quero, start=1):
                wl.cell(i, 1).value = v
            mudou = True
    for nome in (ABA_PRAZOS, ABA_LISTAS):
        if nome in wb.sheetnames and not wb[nome].protection.sheet:
            wb[nome].protection.sheet = True
            mudou = True
    return mudou
