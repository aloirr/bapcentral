# -*- coding: utf-8 -*-
"""
Gera a BASE_CLIENTE.xlsx a partir da TABELA_BAP.xlsx.

E a base que o planner consome. Roda dentro do BAP Tools no fim de
cada rotina (o bap_automation chama gerar_base_cliente) e tambem pode ser
executada sozinha:

    python base_cliente.py "TABELA_BAP.xlsx" "BASE_CLIENTE.xlsx"

Regras combinadas com o Alexandre:

  CURVA (media mensal dos ultimos 3 meses de faturamento, TIPO = VND,
         liquido de devolucao TIPO = DEV):
      S  media >= 20.000/mes
      A  media >= 10.000/mes
      B  media >=  5.000/mes
      C  media >=      1,00
      Z  zerado

  STATUS (dias desde a ultima nota faturada):
      ATIVO          ate 30 dias
      CHURN 30       31 a 60
      CHURN 60       61 a 90
      CHURN 90       91 ate o corte de inativo
      CHURN 90+      acima do corte (padrao 90 -> CHURN 90 fica vazio)
                     (06/10: INATIVO e so o cliente inativado no Planner)
      NUNCA COMPROU  sem nenhuma nota

  ULTIMO VENDEDOR: C5_VEND1 da nota faturada mais recente do cliente.
"""
from __future__ import annotations

import datetime as dt
import re
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
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook, load_workbook
try:  # leitura rapida com cache (sem o arquivo: openpyxl)
    from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
except ImportError:
    from openpyxl import load_workbook  # noqa: PLC0415
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

CURVA_S, CURVA_A, CURVA_B, CURVA_C = 20000.0, 10000.0, 5000.0, 1.0
MESES_CURVA = 3
MESES_FATURAMENTO = 6       # a janela do FAT. M6M do resumo gerencial
DIAS_COMPRANTE = 90         # comprante = comprou nos ultimos N dias
CHURN_30, CHURN_60, CHURN_90, INATIVO = 30, 60, 90, 90

# Os cortes acima sao apenas o padrao de fabrica. A aba PARAMETROS do
# planner manda os valores dela em gerar_base_cliente(parametros=...)
# e esta funcao os aplica antes de qualquer calculo.
PADRAO_PARAMETROS = {
    "curva_s": CURVA_S, "curva_a": CURVA_A,
    "curva_b": CURVA_B, "curva_c": CURVA_C,
    "meses_curva": MESES_CURVA,
    "meses_faturamento": MESES_FATURAMENTO,
    "dias_comprante": DIAS_COMPRANTE,
    "churn_30": CHURN_30, "churn_60": CHURN_60,
    "churn_90": CHURN_90, "inativo": INATIVO,
}


def aplicar_parametros(parametros=None) -> dict:
    """Troca os cortes usados no calculo. Devolve os que ficaram valendo."""
    global CURVA_S, CURVA_A, CURVA_B, CURVA_C, MESES_CURVA
    global MESES_FATURAMENTO, DIAS_COMPRANTE
    global CHURN_30, CHURN_60, CHURN_90, INATIVO

    p = dict(PADRAO_PARAMETROS)
    for chave, valor in (parametros or {}).items():
        if chave in p and valor not in (None, ""):
            try:
                p[chave] = float(valor)
            except (TypeError, ValueError):
                pass

    CURVA_S, CURVA_A = float(p["curva_s"]), float(p["curva_a"])
    CURVA_B, CURVA_C = float(p["curva_b"]), float(p["curva_c"])
    MESES_CURVA = max(1, int(p["meses_curva"]))
    MESES_FATURAMENTO = max(1, int(p["meses_faturamento"]))
    DIAS_COMPRANTE = max(1, int(p["dias_comprante"]))
    CHURN_30, CHURN_60 = int(p["churn_30"]), int(p["churn_60"])
    CHURN_90, INATIVO = int(p["churn_90"]), int(p["inativo"])
    return {
        "curva_s": CURVA_S, "curva_a": CURVA_A, "curva_b": CURVA_B,
        "curva_c": CURVA_C, "meses_curva": MESES_CURVA,
        "meses_faturamento": MESES_FATURAMENTO,
        "dias_comprante": DIAS_COMPRANTE,
        "churn_30": CHURN_30, "churn_60": CHURN_60,
        "churn_90": CHURN_90, "inativo": INATIVO,
    }

COLUNAS_VENDEDOR = [
    "VENDEDOR_PROTHEUS", "NOME_VENDEDOR_PROTHEUS",
    "SUPERVISOR_PROTHEUS", "NOME_SUPERVISOR_PROTHEUS",
    "VENDEDOR_PLANNER", "NOME_VENDEDOR_PLANNER",
    "SUPERVISOR_PLANNER", "NOME_SUPERVISOR_PLANNER"]

CABECALHO = [
    # O CNPJ (A1_CGC do Protheus) vem junto do COD e da LOJA porque e a
    # terceira forma de identificar o mesmo cliente - e a unica que
    # casa com sistema de fora (nota fiscal, Serasa, Receita). Fica
    # como TEXTO: CNPJ comecado em zero vira numero e perde o zero.
    "COD_CLIENTE", "LOJA", "CNPJ", "NOME_CLIENTE", "NOME_FANTASIA",
    "UF", "CIDADE", "BAIRRO", "ENDERECO", "NUMERO", "CONTATO",
    "DDD", "TELEFONE",
    "LIMITE_APROVADO", "LIMITE_DISPONIVEL", "EM_ABERTO", "VALOR_EM_ATRASO",
    "DIAS_ATRASO", "INADIMPLENTE",
    "RECEITA_PERIODO", "MEDIA_MENSAL",
    "RECEITA_PERIODO_ANTERIOR", "MEDIA_MENSAL_ANTERIOR",
    "RECEITA_6M", "MEDIA_MENSAL_6M",
    "RECEITA_ACUMULADA", "CURVA_RECEITA", "ULTIMA_COMPRA", "DIAS_SEM_COMPRA", "STATUS_CLIENTE",
    "COD_ULTIMO_VENDEDOR", "QTD_NOTAS", "PRIMEIRA_COMPRA",
    # do cadastro do Protheus, para o indicador CADASTRO COM COMPRA:
    # A1_DTCAD e A1_PRICOM. Quando o cliente e cadastrado e compra no
    # MESMO mes, CADASTRO_COM_COMPRA sai SIM.
    "DATA_CADASTRO", "DATA_1A_COMPRA", "CADASTRO_COM_COMPRA",
    # CNAE da Receita (pelo CNPJ) e o SEGMENTO do cliente - vem do
    # cnae_bap.py: o cache da pasta "Consulta CNAE" e as regras da
    # SEGMENTACAO_BAP.xlsx. Ficam no FIM de proposito: quem le a base pelo
    # nome da coluna nao percebe a diferenca.
    "CNAE_PRINCIPAL", "CNAE_DESCRICAO", "CNAES_SECUNDARIOS",
    "SITUACAO_RECEITA", "SEGMENTO", "SUBSEGMENTO", "SEGMENTO_ORIGEM",
    # (06/10) o PONTO do endereco no mapa (geocodificar.py, OpenStreetMap):
    # e a referencia da rota do Planner. Atualiza sozinho quando o cliente
    # e novo ou o endereco muda; vazio = ainda nao localizado (a rota usa o
    # centro do bairro)
    "LATITUDE", "LONGITUDE",
    # (07/10) o VENDEDOR e o SUPERVISOR do cliente nos dois lados: o do
    # Protheus (A1_VEND; o supervisor e o chefe dele no cadastro do
    # Planner - o A1_SUPER vem vazio) e o do PLANNER (zona + segmento, ou a
    # excecao do analitico). E o que casa a base com o .json do Protheus
    *COLUNAS_VENDEDOR,
    # (28/10, Alexandre - regra 2 das coordenadas) o CEP do cadastro do
    # Protheus (A1_CEP, 8 digitos): vai na consulta do geocodificar
    "CEP",
    # (10/11, Alexandre) o ATIVO/INATIVO do cadastro do Protheus (coluna
    # STATUS da dClientesBap; sem ela, A1_MSBLQL = 1 e INATIVO): o INATIVO
    # sai da rota do vendedor no Planner e vai com o vendedor padrao no
    # .json da base de clientes
    "STATUS_PROTHEUS",
]
COLUNAS_CNAE = ["CNAE_PRINCIPAL", "CNAE_DESCRICAO", "CNAES_SECUNDARIOS",
                "SITUACAO_RECEITA", "SEGMENTO", "SUBSEGMENTO",
                "SEGMENTO_ORIGEM"]
# quanto tempo o BAP Tools gasta consultando endereco novo/alterado a cada
# rodada (1 por segundo); o resto fica para a proxima rodada ou para o
# botao "Atualizar coordenadas" do Planner
# (05/11, auditoria do robo) 300 -> 60 s: desde 29/10 a fila gastava os 300 s
# inteiros em toda rodada (12 -> 17 min); a fila grande vai pelo
# atualizar_coordenadas_google.bat
TEMPO_COORDENADAS = 60
LARGURA = [12, 6, 18, 40, 30, 5, 22, 24, 36, 8, 20, 7, 14, 14, 14, 13, 14, 10,
           12, 15, 14, 23, 22, 14, 16, 17, 10, 13, 12, 15, 13, 10, 14,
           15, 16, 21,
           11, 40, 50, 12, 24, 30, 16, 11, 11,
           12, 30, 12, 30, 12, 30, 12, 30, 11, 12]
assert len(LARGURA) == len(CABECALHO), "LARGURA e CABECALHO com tamanhos diferentes"

# o formato das celulas sai do NOME da coluna, nunca do numero dela: assim
# acrescentar uma coluna no meio nao desalinha a formatacao (ja aconteceu)
COLUNAS_DINHEIRO = [CABECALHO.index(n) + 1 for n in (
    "LIMITE_APROVADO", "LIMITE_DISPONIVEL", "EM_ABERTO", "VALOR_EM_ATRASO",
    "RECEITA_PERIODO", "MEDIA_MENSAL",
    "RECEITA_PERIODO_ANTERIOR", "MEDIA_MENSAL_ANTERIOR",
    "RECEITA_6M", "MEDIA_MENSAL_6M", "RECEITA_ACUMULADA")]
COLUNAS_DATA = [CABECALHO.index(n) + 1 for n in (
    "ULTIMA_COMPRA", "PRIMEIRA_COMPRA", "DATA_CADASTRO", "DATA_1A_COMPRA")]
# CNPJ, COD e LOJA sao TEXTO, nunca numero: "04550434001007" virando
# numero perde o zero da frente e deixa de casar com a nota fiscal
COLUNAS_TEXTO = [CABECALHO.index(n) + 1 for n in (
    "COD_CLIENTE", "LOJA", "CNPJ", "CNAE_PRINCIPAL", "CEP")]


def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def numero(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def data_de(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = texto(v)
    if not s:
        return None
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y"):
        try:
            return dt.datetime.strptime(s[:10], f).date()
        except ValueError:
            pass
    # o Protheus grava data como texto AAAAMMDD ("20210504")
    if len(s) == 8 and s.isdigit():
        try:
            return dt.datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            pass
    return None


# --------------------------------------------------------------------------
# A TABELA_BAP vem do Protheus com os acentos perdidos: cada letra acentuada
# virou "¿" (PE¿AS, N¿MERO, CONSTRU¿¿ES). Como o resto do programa trabalha
# sem acento, aqui a letra some de vez e a palavra volta legivel. O que nao
# estiver na lista fica como esta - nunca se inventa letra.
PALAVRAS_QUEBRADAS = {
    "AB¿LIO": "ABILIO", "ALIAN¿A": "ALIANCA", "AMAZ¿NI": "AMAZONI",
    "ANT¿NIA": "ANTONIA", "ANT¿NIO": "ANTONIO", "ARA¿JO": "ARAUJO",
    "ASSUN¿¿O": "ASSUNCAO", "ATA¿DE": "ATAIDE", "AUTOPE¿AS": "AUTOPECAS",
    "BARAT¿O": "BARATAO", "CABE¿A": "CABECA", "CAMAPU¿": "CAMAPUA",
    "CENTEN¿RIO": "CENTENARIO", "CL¿NICA": "CLINICA", "COL¿NIA": "COLONIA",
    "COMBUST¿VEIS": "COMBUSTIVEIS", "COM¿": "COME", "COM¿RCIO": "COMERCIO",
    "CONCEI¿¿O": "CONCEICAO", "CONCESSION¿RIA": "CONCESSIONARIA",
    "CONSTRU¿¿": "CONSTRUCA", "CONSTRU¿¿ES": "CONSTRUCOES",
    "CONSTRU¿ES": "CONSTRUCOES", "ORGANIZA¿ES": "ORGANIZACOES",
    "¿": "A",                       # a crase perdida ("EM FRENTE ¿ ...")
    "MINERA?CO": "MINERACAO", "F¿TIMA": "FATIMA",
    "CONSTRU¿¿O": "CONSTRUCAO", "C¿CERO": "CICERO", "DIN¿MICA": "DINAMICA",
    "DR¿": "DRA", "D¿BORA": "DEBORA", "ESPERAN¿A": "ESPERANCA",
    "FABRICA¿¿O": "FABRICACAO", "FLOREN¿A": "FLORENCA", "GALL¿O": "GALLAO",
    "GALP¿O": "GALPAO", "GLIC¿RIO": "GLICERIO", "GRA¿AS": "GRACAS",
    "HIDR¿ULICA": "HIDRAULICA", "H¿LIO": "HELIO", "IND¿STRIA": "INDUSTRIA",
    "IRM¿O": "IRMAO", "IRM¿OS": "IRMAOS", "ITAET¿": "ITAETE", "I¿A": "ICA",
    "JERUSAL¿M": "JERUSALEM", "JOS¿": "JOSE", "JO¿O": "JOAO",
    "JEOV¿": "JEOVA", "J¿NIOR": "JUNIOR", "LE¿O": "LEAO",
    "LOCA¿¿ES": "LOCACOES", "LOG¿STICA": "LOGISTICA",
    "MAGALH¿ES": "MAGALHAES", "MARANH¿O": "MARANHAO", "MEC¿NICA": "MECANICA",
    "MENDON¿A": "MENDONCA", "MILIT¿O": "MILITAO", "MOTOPE¿AS": "MOTOPECAS",
    "MUCAJA¿": "MUCAJAI", "M¿QUINAS": "MAQUINAS", "M¿RIO": "MARIO",
    "N¿MERO": "NUMERO", "OP¿": "OPA", "ORGANIZA¿¿ES": "ORGANIZACOES",
    "PARAGUA¿¿": "PARAGUACU", "PARTICIPA¿¿ES": "PARTICIPACOES",
    "PENETRA¿¿O": "PENETRACAO", "PETR¿LEO": "PETROLEO", "PE¿A": "PECA",
    "PE¿AS": "PECAS", "REBOU¿AS": "REBOUCAS", "REVIS¿O": "REVISAO",
    "ROG¿RIO": "ROGERIO", "SANTAR¿M": "SANTAREM", "SEBASTI¿O": "SEBASTIAO",
    "SERVI¿OS": "SERVICOS", "SOLU¿OES": "SOLUCOES", "SOPICKU¿S": "SOPICKUS",
    "SUMA¿MA": "SUMAUMA", "SUSPENS¿O": "SUSPENSAO", "S¿O": "SAO",
    "TARUM¿": "TARUMA", "TEER¿": "TEERA", "TEF¿": "TEFE", "UNI¿O": "UNIAO",
    "URUCAR¿": "URUCARA", "VIA¿¿O": "VIACAO", "¿LEO": "OLEO",
}
_NUMERO_QUEBRADO = re.compile(r"N¿(?=\d|\s|[.,;]|$)")
_PALAVRA = re.compile(r"[A-Za-z¿]+")


def _so_digitos(valor) -> str:
    """
    O CNPJ como o Protheus guarda: so os 14 digitos, sem mascara.

    Sem mascara de proposito - e assim que ele casa com a nota fiscal e
    com qualquer cruzamento de fora. Quem quiser ver pontuado formata na
    planilha. O zero da frente fica: "04550434001007" nao e numero.

    Pessoa fisica tem 11 digitos (CPF) e passa igual; o que vier com
    outro tamanho vai como esta, porque inventar digito seria pior.
    """
    limpo = re.sub(r"\D", "", texto(valor))
    if not limpo:
        return ""
    if len(limpo) <= 11:
        return limpo.zfill(11)      # CPF
    return limpo.zfill(14)          # CNPJ


def arrumar_texto(valor: str) -> str:
    """Devolve o texto com as palavras quebradas do Protheus arrumadas."""
    s = texto(valor)
    if "¿" not in s and "?¿" not in s:
        return s
    s = s.replace("?¿", "¿")
    s = _NUMERO_QUEBRADO.sub("N.", s)          # N¿1520 -> N.1520
    s = s.replace("N ¿ ", "N. ").replace("N¿MERO", "NUMERO")

    def trocar(m):
        palavra = m.group(0)
        nova = PALAVRAS_QUEBRADAS.get(palavra.upper())
        if not nova:
            return palavra
        return nova if palavra.isupper() else nova.capitalize()

    # a palavra e so letra: virgula, ponto e numero ao lado nao atrapalham
    return _PALAVRA.sub(trocar, s)


def curva_de(media: float) -> str:
    if media >= CURVA_S:
        return "S"
    if media >= CURVA_A:
        return "A"
    if media >= CURVA_B:
        return "B"
    if media >= CURVA_C:
        return "C"
    return "Z"


def status_de(dias) -> str:
    if dias is None:
        return "NUNCA COMPROU"
    if dias <= CHURN_30:
        return "ATIVO"
    if dias <= CHURN_60:
        return "CHURN 30"
    if dias <= CHURN_90:
        return "CHURN 60"
    if dias <= INATIVO:
        return "CHURN 90"
    return "CHURN 90+"


# --------------------------------------------------------------------------
def _primeiro_do_mes(d: dt.date) -> dt.date:
    return dt.date(d.year, d.month, 1)


def _volta_meses(d: dt.date, meses: int) -> dt.date:
    """O dia 1 de N meses antes do mes de d. Ex.: 06/09 e 3 -> 01/06."""
    total = d.year * 12 + (d.month - 1) - meses
    return dt.date(total // 12, total % 12 + 1, 1)


def _historico(wb, referencia=None):
    """
    Le a ftPedidos e devolve, por cliente:
        receita dos ultimos N meses, ultima compra, ultimo vendedor, notas.
    A referencia e a data da nota mais recente da base (e nao "hoje"),
    para o calculo nao mudar de resultado se a TABELA_BAP estiver com
    alguns dias de atraso.
    """
    if "ftPedidos" not in wb.sheetnames:
        return {}, None
    ws = wb["ftPedidos"]
    it = ws.iter_rows(values_only=True)
    cab = list(next(it))

    def idx(*nomes):
        for n in nomes:
            if n in cab:
                return cab.index(n)
        return None

    i_cli = idx("D2_CLIENTE")
    i_tipo = idx("TIPO")
    i_val = idx("VALOR TOTAL", "VALOR_TOTAL")
    i_nf = idx("DATA_NF")
    i_em = idx("D2_EMISSAO")
    i_vend = idx("C5_VEND1")
    i_doc = idx("D2_DOC")
    if i_cli is None or i_tipo is None:
        return {}, None

    movimentos = []
    for r in it:
        tipo = texto(r[i_tipo]).upper()
        if tipo not in ("VND", "DEV"):
            continue
        d = data_de(r[i_nf]) or data_de(r[i_em])
        if not d:
            continue
        movimentos.append((
            texto(r[i_cli]).zfill(6), d, numero(r[i_val]),
            texto(r[i_vend]) if i_vend is not None else "",
            texto(r[i_doc]) if i_doc is not None else "", tipo,
        ))
    if not movimentos:
        return {}, None

    ref = referencia or max(m[1] for m in movimentos)
    # AS JANELAS SAO DE MESES FECHADOS, e o mes da referencia NAO entra:
    # se a referencia cai em setembro, o M3M e junho+julho+agosto e o M3M
    # ANTERIOR e marco+abril+maio. Assim a meta de setembro nunca e feita
    # com pedaco do proprio setembro, e nenhum mes entra pela metade.
    #     |--- anterior: mar abr mai ---|--- atual: jun jul ago ---| set
    corte = _volta_meses(ref, MESES_CURVA)
    corte_ant = _volta_meses(ref, MESES_CURVA * 2)
    corte6 = _volta_meses(ref, MESES_FATURAMENTO)
    fim = _primeiro_do_mes(ref)          # o mes da referencia fica de fora

    h = defaultdict(lambda: {"receita": 0.0, "receita_ant": 0.0,
                             "receita6": 0.0, "acumulado": 0.0,
                             "ultima": None, "primeira": None, "vendedor": "",
                             "notas": set()})
    for cod, d, valor, vendedor, doc, tipo in movimentos:
        reg = h[cod]
        reg["acumulado"] += valor            # tudo o que ja faturou, liquido
        if d >= fim:
            pass                             # o mes corrente nao entra
        elif d >= corte:
            reg["receita"] += valor          # DEV ja vem negativo
        elif d >= corte_ant:
            reg["receita_ant"] += valor      # a janela de antes dela
        if corte6 <= d < fim:
            reg["receita6"] += valor         # a janela do FAT. M6M
        if tipo == "VND":
            reg["notas"].add(doc or f"{d}")
            if reg["ultima"] is None or d > reg["ultima"]:
                reg["ultima"] = d
                reg["vendedor"] = vendedor
            if reg["primeira"] is None or d < reg["primeira"]:
                reg["primeira"] = d
    return h, ref


# ==========================================================================
# O HISTORICO DE COMPRA - as duas abas novas da BASE_CLIENTE
# ==========================================================================
# HIST_POR_NF     uma linha por NOTA FISCAL do cliente
# HIST_DETALHADO  o mesmo espelho, uma linha por PRODUTO daquela nota
#
# As duas saem da aba ftPedidos da TABELA_BAP, que ja vem no nivel do
# produto. A de NF e a soma da de produto - por construcao, nao por
# calculo paralelo: uma e agrupada a partir da outra, entao os totais
# fecham sempre.
#
# ENTRA o que foi FATURADO: TIPO = VND (venda) e DEV (devolucao, que ja
# vem com o valor negativo e por isso abate sozinha). Ficam de fora o TRF
# (transferencia entre filiais, nao e compra do cliente), o EXC
# (excluido) e o VEA (venda em ABERTO, pedido que ainda nao virou nota).
TIPOS_DO_HISTORICO = ("VND", "DEV")

COLUNAS_HIST_NF = [
    "COD CLIENTE", "CNPJ", "NF", "PEDIDO", "DT COMPRA", "FORM PAGAMENTO",
    "QTD", "VALOR TABELA", "PERC. DESCONTO", "VALOR TOTAL",
]
LARGURA_HIST_NF = [13, 20, 13, 13, 12, 26, 10, 14, 15, 14]

COLUNAS_HIST_DET = [
    "COD CLIENTE", "CNPJ", "NF", "PEDIDO", "DT COMPRA", "FORM PAGAMENTO",
    "COD PRODUTO", "DESCRICAO PRODUTO",
    "QTD", "VALOR TABELA", "PERC. DESCONTO", "VALOR TOTAL",
]
LARGURA_HIST_DET = [13, 20, 13, 13, 12, 26, 16, 44, 10, 14, 15, 14]

assert len(LARGURA_HIST_NF) == len(COLUNAS_HIST_NF)
assert len(LARGURA_HIST_DET) == len(COLUNAS_HIST_DET)


def _indice(cabecalho):
    """Devolve uma funcao que acha a coluna pelo nome, sem quebrar se faltar."""
    mapa = {texto(c): i for i, c in enumerate(cabecalho)}

    def achar(*nomes):
        for n in nomes:
            if n in mapa:
                return mapa[n]
        return None
    return achar


def _cnpj_dos_clientes(wb) -> dict:
    """{codigo do cliente com 6 digitos: CNPJ} - o A1_CGC da dClientesBap."""
    if "dClientesBap" not in wb.sheetnames:
        return {}
    ws = wb["dClientesBap"]
    it = ws.iter_rows(values_only=True)
    achar = _indice(list(next(it)))
    i_cod, i_cgc = achar("A1_COD"), achar("A1_CGC")
    if i_cod is None or i_cgc is None:
        return {}
    saida = {}
    for r in it:
        cod = texto(r[i_cod]).zfill(6)
        if cod and cod not in saida:
            saida[cod] = texto(r[i_cgc])
    return saida


def _descricao_dos_produtos(wb) -> dict:
    """
    {CODIGO DO PRODUTO em maiuscula: descricao}.

    A descricao de verdade nao esta na ProdutosBAP - la a coluna "Cod.
    Produto" muitas vezes repete o proprio codigo. Ela vem de duas abas,
    nesta ordem:
        ftTabelaPreco   DA1_CODPRO -> B1_DESC        (a mais completa)
        ftEstoquePMZ    PRODUTO    -> DESCRICAO_COMPL
    A chave e o codigo do produto, que e o mesmo D2_COD da ftPedidos.
    """
    saida = {}
    for aba, col_cod, col_desc in (
            ("ftTabelaPreco", ("DA1_CODPRO",), ("B1_DESC", "DESCRICAO")),
            ("ftEstoquePMZ", ("PRODUTO",),
             ("DESCRICAO_COMPL", "DESCRICAO", "B1_DESC"))):
        if aba not in wb.sheetnames:
            continue
        ws = wb[aba]
        it = ws.iter_rows(values_only=True)
        achar = _indice(list(next(it)))
        i_cod, i_desc = achar(*col_cod), achar(*col_desc)
        if i_cod is None or i_desc is None:
            continue
        for r in it:
            cod = texto(r[i_cod]).upper()
            desc = texto(r[i_desc])
            # o primeiro que aparece manda: a ftTabelaPreco vem antes
            if cod and desc and cod not in saida:
                saida[cod] = desc
    return saida


def _formas_de_pagamento(wb) -> dict:
    """{codigo: descricao} - a aba ftCondicaoPagamentos."""
    if "ftCondicaoPagamentos" not in wb.sheetnames:
        return {}
    ws = wb["ftCondicaoPagamentos"]
    it = ws.iter_rows(values_only=True)
    achar = _indice(list(next(it)))
    i_cod, i_desc = achar("Codigo", "CODIGO", "Código"), achar("Descricao",
                                                              "Descrição")
    if i_cod is None or i_desc is None:
        return {}
    saida = {}
    for r in it:
        cod = texto(r[i_cod])
        if not cod:
            continue
        saida[cod] = texto(r[i_desc])
        saida[cod.lstrip("0")] = texto(r[i_desc])   # "026" e "26" acham igual
    return saida


def _perc_desconto(tabela: float, total: float) -> float:
    """
    O desconto da NOTA sai dos totais, nao da media dos itens: quanto o
    cliente deixou de pagar sobre o valor de tabela daquela nota inteira.
    Sem valor de tabela (devolucao, brinde) o desconto e zero - nao se
    divide por zero nem se inventa 100%.
    """
    if tabela <= 0:
        return 0.0
    return round((1 - total / tabela) * 100, 2)


def historico_de_compras(wb) -> tuple:
    """
    Le a ftPedidos e devolve (linhas_por_nf, linhas_detalhadas), ja
    prontas para virar as abas HIST_POR_NF e HIST_DETALHADO.
    """
    if "ftPedidos" not in wb.sheetnames:
        return [], []
    cnpj = _cnpj_dos_clientes(wb)
    produto = _descricao_dos_produtos(wb)
    pagamento = _formas_de_pagamento(wb)

    ws = wb["ftPedidos"]
    it = ws.iter_rows(values_only=True)
    achar = _indice(list(next(it)))
    i = {
        "cliente": achar("D2_CLIENTE"), "tipo": achar("TIPO"),
        "nf": achar("NUM_NF", "D2_DOC"), "pedido": achar("NUM_PEDIDO", "D2_PEDIDO"),
        "data": achar("DATA_NF"), "emissao": achar("D2_EMISSAO"),
        "cond": achar("C5_CONDPAG"), "qtd": achar("D2_QUANT"),
        "ptabela": achar("PRECO_TABELA"), "total": achar("VALOR TOTAL", "VALOR_TOTAL"),
        "desconto": achar("PORCENTAGEM_DESCONTO"),
        "cod_prod": achar("D2_COD"), "id_prod": achar("ID_PRODUTO"),
        "filial": achar("D2_FILIAL"), "serie": achar("D2_SERIE"),
    }
    if i["cliente"] is None or i["tipo"] is None:
        return [], []

    def pega(r, chave, padrao=None):
        j = i.get(chave)
        return r[j] if j is not None and j < len(r) else padrao

    detalhado, por_nf = [], {}
    for r in it:
        if texto(pega(r, "tipo")).upper() not in TIPOS_DO_HISTORICO:
            continue
        cod = texto(pega(r, "cliente")).zfill(6)
        if not cod.strip("0"):
            continue
        d = data_de(pega(r, "data")) or data_de(pega(r, "emissao"))
        nf = texto(pega(r, "nf"))
        pedido = texto(pega(r, "pedido"))
        cond = texto(pega(r, "cond"))
        forma = pagamento.get(cond) or pagamento.get(cond.lstrip("0")) or cond
        qtd = numero(pega(r, "qtd"))
        total = numero(pega(r, "total"))
        # VALOR TABELA e o valor CHEIO da linha: preco de tabela x quantidade.
        # Guardar o preco unitario aqui nao serviria - na aba por NF, onde a
        # linha soma varios produtos, um preco unitario nao quer dizer nada.
        tabela = round(numero(pega(r, "ptabela")) * qtd, 2)
        cod_prod = texto(pega(r, "cod_prod"))

        detalhado.append([
            cod, cnpj.get(cod, ""), nf, pedido, d, forma,
            cod_prod, produto.get(cod_prod.upper(), ""),
            qtd, tabela, numero(pega(r, "desconto")), round(total, 2),
        ])

        # a chave da nota inclui a FILIAL e a SERIE: o numero da NF so e
        # unico dentro delas, e sem isso duas notas de filiais diferentes
        # virariam uma linha so
        chave = (cod, texto(pega(r, "filial")), texto(pega(r, "serie")), nf)
        linha = por_nf.get(chave)
        if linha is None:
            por_nf[chave] = [cod, cnpj.get(cod, ""), nf, pedido, d, forma,
                             qtd, tabela, 0.0, round(total, 2)]
        else:
            linha[6] = round(linha[6] + qtd, 4)
            linha[7] = round(linha[7] + tabela, 2)
            linha[9] = round(linha[9] + total, 2)
            if not linha[4] and d:
                linha[4] = d
            if not linha[5]:
                linha[5] = forma

    for linha in por_nf.values():
        linha[8] = _perc_desconto(linha[7], linha[9])

    ordem = lambda x: (x[0], x[4] or dt.date(1900, 1, 1), texto(x[2]))
    return sorted(por_nf.values(), key=ordem), sorted(detalhado, key=ordem)


def _folha_do_historico(wb, titulo, colunas, largura, linhas,
                        col_dinheiro=(), col_data=(), col_pct=()):
    ws = wb.create_sheet(titulo)
    ws.append(colunas)
    borda = Border(*(Side(style="thin", color="D9D9D9"),) * 4)
    for c, _ in enumerate(colunas, start=1):
        cel = ws.cell(1, c)
        cel.font = Font(bold=True, color="FFFFFF", size=9)
        cel.fill = PatternFill("solid", fgColor="1F4E79")
        cel.alignment = Alignment(horizontal="center", vertical="center",
                                  wrap_text=True)
        cel.border = borda
        ws.column_dimensions[get_column_letter(c)].width = largura[c - 1]
    ws.row_dimensions[1].height = 30
    for l in linhas:
        ws.append(l)
    # (05/11, auditoria do robo) fonte e borda entram UMA vez na lista de
    # estilos e cada celula recebe so o numero delas (antes um Font() novo
    # em cada celula: ~1 min por rodada). O Excel sai igual.
    formato = {}
    for c in col_dinheiro:
        formato[c] = '#,##0.00'
    for c in col_data:
        formato[c] = "DD/MM/YYYY"
    for c in col_pct:
        formato[c] = '#,##0.00'
    try:
        from openpyxl.styles.cell_style import StyleArray  # noqa: PLC0415
        fid = wb._fonts.add(Font(size=9))
        bid = wb._borders.add(borda)
        nid = {c: _id_do_formato(wb, f) for c, f in formato.items()}
    except Exception:                                    # noqa: BLE001
        fid = bid = nid = None
    n_col = len(colunas)
    if fid is not None and ws.max_row > 1:
        for linha in ws.iter_rows(min_row=2, max_row=ws.max_row,
                                  max_col=n_col):
            for c, cel in enumerate(linha, start=1):
                st = cel._style
                if st is None:
                    st = cel._style = StyleArray()
                st.fontId = fid
                st.borderId = bid
                if c in nid:
                    st.numFmtId = nid[c]
        return _fim_do_historico(ws, colunas)
    for l in range(2, ws.max_row + 1):
        for c in range(1, n_col + 1):
            cel = ws.cell(l, c)
            cel.font = Font(size=9)
            cel.border = borda
        for c, f in formato.items():
            ws.cell(l, c).number_format = f
    return _fim_do_historico(ws, colunas)


def _id_do_formato(wb, formato):
    """O numero do formato de celula (o mesmo que o openpyxl usa)."""
    from openpyxl.styles.numbers import (                # noqa: PLC0415
        BUILTIN_FORMATS_MAX_SIZE, BUILTIN_FORMATS_REVERSE)
    if formato in BUILTIN_FORMATS_REVERSE:
        return BUILTIN_FORMATS_REVERSE[formato]
    return wb._number_formats.add(formato) + BUILTIN_FORMATS_MAX_SIZE


def _fim_do_historico(ws, colunas):
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = (f"A1:{get_column_letter(len(colunas))}"
                              f"{ws.max_row}")
    return ws


# a aba EXCLUIDOS: as mesmas colunas da BASE_CLIENTE + o porque
COLUNAS_EXCLUIDOS_EXTRA = ["MOTIVO_EXCLUSAO", "SEGMENTO_SUGERIDO"]
LARGURA_EXCLUIDOS_EXTRA = [50, 24]


def _decisao_cnae(contexto, cod, loja, cgc, nome, fantasia) -> dict:
    """
    As 7 colunas de CNAE e segmento + se o cliente fica de fora da base.
    Sem o modulo de CNAE ninguem e excluido: a base sai inteira, com o
    segmento em branco (melhor sobrar cliente do que sumir carteira por
    causa de um arquivo faltando).
    """
    vazio = {c: "" for c in COLUNAS_CNAE}
    vazio.update(EXCLUIDO=False, MOTIVO_EXCLUSAO="", SEGMENTO_SUGERIDO="")
    if contexto is None:
        return vazio
    try:
        return contexto.decidir(cod, loja, cgc, nome or "", fantasia or "")
    except Exception:                             # noqa: BLE001
        vazio["SEGMENTO_ORIGEM"] = "ERRO"
        return vazio


RELATORIO_CLIENTES = "Relatorio_Clientes_"


def pontos_do_relatorio(caminho_saida) -> dict:
    """(13/11) {CHAVE_CLIENTE: (lat, lon)} do Relatorio Clientes mais novo
    que o robo arquivou (SISTEMA BAP/BACKUP_RELATORIOS/
    BKP_RELATORIOS_BAPTOOLS) - para quando a dClientesBap ainda nao tem
    as colunas A1_LATITU/A1_LONGIT. Sem arquivo ou sem as colunas: {}."""
    try:
        pasta = Path(caminho_saida).resolve().parent
        raiz = pasta.parent if pasta.name.upper() == "RELATORIOS" else pasta
        bkp = raiz / "SISTEMA BAP" / "BACKUP_RELATORIOS" / \
            "BKP_RELATORIOS_BAPTOOLS"
        arqs = sorted(bkp.glob(RELATORIO_CLIENTES + "*.xlsx"))
        if not arqs:
            return {}
        wb = load_workbook(arqs[-1], read_only=True, data_only=True)
        try:
            it = wb.worksheets[0].iter_rows(values_only=True)
            cab = [texto(c).upper() for c in next(it)]
            if "A1_LATITU" not in cab or "A1_LONGIT" not in cab:
                return {}
            ic, il = cab.index("A1_COD"), cab.index("A1_LOJA")
            ila, ilo = cab.index("A1_LATITU"), cab.index("A1_LONGIT")
            saida = {}
            for r in it:
                if not r or r[ic] in (None, ""):
                    continue
                chave = f"{texto(r[ic]).zfill(6)}-{texto(r[il]) or '00'}"
                saida[chave] = (r[ila], r[ilo])
            return saida
        finally:
            wb.close()
    except Exception:                                   # noqa: BLE001
        return {}


def _coordenadas(linhas, caminho_saida, segundos=None,
                 protheus=None) -> None:
    """LATITUDE e LONGITUDE de cada linha: o que ja foi localizado vem do
    COORDENADAS_CLIENTES.json; o endereco novo ou alterado e consultado
    agora, por ate TEMPO_COORDENADAS segundos. Sem internet, fica vazio
    (e a rota usa o centro do bairro). (13/11) protheus = {CHAVE: (lat,
    lon)} do Protheus: o ponto valido passa na frente (so o MANUAL fica)."""
    try:
        import geocodificar                             # noqa: PLC0415
    except ImportError:
        return
    i = {n: CABECALHO.index(n) for n in ("COD_CLIENTE", "LOJA", "ENDERECO",
                                          "NUMERO", "BAIRRO", "CIDADE", "UF",
                                          "LATITUDE", "LONGITUDE", "CEP")}
    clientes = [{"CHAVE_CLIENTE": f"{texto(l[i['COD_CLIENTE']]).zfill(6)}-"
                                  f"{texto(l[i['LOJA']]) or '00'}",
                 "ENDERECO": l[i["ENDERECO"]], "NUMERO": l[i["NUMERO"]],
                 "BAIRRO": l[i["BAIRRO"]], "CIDADE": l[i["CIDADE"]],
                 "UF": l[i["UF"]],
                 "CEP": l[i["CEP"]] if len(l) > i["CEP"] else "",
                 "_linha": l} for l in linhas]
    arq = geocodificar.caminho(Path(caminho_saida))
    _coordenadas.protheus = None
    if protheus:
        try:
            _coordenadas.protheus = geocodificar.aplicar_protheus(
                clientes, arq, protheus)
        except Exception:                               # noqa: BLE001
            pass
    try:
        r = geocodificar.atualizar(
            arq.parent / "BASE_CLIENTE.xlsx", clientes=clientes,
            limite_seg=TEMPO_COORDENADAS if segundos is None else segundos)
        _coordenadas.resultado = r
    except Exception:                                   # noqa: BLE001
        pass
    geocodificar.completar(clientes, arq)
    for c in clientes:
        if c.get("LATITUDE") is not None:
            c["_linha"][i["LATITUDE"]] = round(float(c["LATITUDE"]), 6)
            c["_linha"][i["LONGITUDE"]] = round(float(c["LONGITUDE"]), 6)


def _config_do_planner(caminho_saida):
    """A configuracao do Planner do mes (para o VENDEDOR_PLANNER): a base
    fica em <pasta>/RELATORIOS; sem Planner, None (as colunas do Planner
    saem vazias)."""
    try:
        import planner_nucleo as _nu              # noqa: PLC0415
        import pastas_bap as _pb                  # noqa: PLC0415
        pasta = Path(caminho_saida).resolve().parent
        raiz = pasta.parent if pasta.name.upper() == "RELATORIOS" else pasta
        arq = _pb.config_vigente(raiz)
        if not Path(arq).exists():
            return None
        return _nu.carregar_config(arq)
    except Exception:                             # noqa: BLE001
        return None


def status_protheus(status, bloqueio=None) -> str:
    """(10/11) INATIVO quando a dClientesBap diz INATIVO na coluna STATUS
    ou, sem ela, quando o A1_MSBLQL e 1 (bloqueado no Protheus)."""
    st = texto(status).upper()
    if st in ("ATIVO", "INATIVO"):
        return st
    return "INATIVO" if texto(bloqueio) == "1" else "ATIVO"


def gerar_base_cliente(caminho_tabela, caminho_saida, referencia=None,
                       parametros=None):
    aplicar_parametros(parametros)
    caminho_tabela = Path(caminho_tabela)
    caminho_saida = Path(caminho_saida)
    wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    if "dClientesBap" not in wb.sheetnames:
        wb.close()
        raise ValueError("TABELA_BAP sem a aba dClientesBap.")

    hist, ref = _historico(wb, referencia)
    # o historico de compra sai do mesmo workbook, antes de ele fechar
    hist_nf, hist_det = historico_de_compras(wb)

    ws = wb["dClientesBap"]
    it = ws.iter_rows(values_only=True)
    cab = list(next(it))

    def idx(*nomes):
        for n in nomes:
            if n in cab:
                return cab.index(n)
        return None

    campos = {
        "cod": idx("A1_COD"), "loja": idx("A1_LOJA"), "nome": idx("A1_NOME"),
        "cgc": idx("A1_CGC", "A1_CNPJ", "CGC", "CNPJ"),
        "fantasia": idx("A1_NREDUZ", "A1_NOMREDUZ", "A1_NOMEFAN"),
        "uf": idx("A1_EST"), "mun": idx("A1_MUN"), "bairro": idx("A1_BAIRRO"),
        "end": idx("A1_END"), "contato": idx("A1_CONTATO", "A1_TEL"),
        "ddd": idx("A1_DDD"), "tel": idx("A1_TEL"),
        "dtcad": idx("A1_DTCAD"), "pricom": idx("A1_PRICOM"),
        "limite": idx("Limite"), "saldo": idx("Saldo Disponivel"),
        "aberto": idx("Valores em aberto"), "atraso": idx("Valor  em atraso"),
        "dias": idx("Dias em atraso"), "vend": idx("A1_VEND"),
        "cep": idx("A1_CEP"),
        # (10/11) ATIVO/INATIVO do Protheus
        "status": idx("STATUS"), "blq": idx("A1_MSBLQL"),
        # (13/11) a coordenada do Protheus
        "lat": idx("A1_LATITU"), "lon": idx("A1_LONGIT"),
    }
    pontos_protheus = {}
    if campos["cod"] is None:
        wb.close()
        raise ValueError("dClientesBap sem a coluna A1_COD.")

    def pega(r, chave, padrao=None):
        i = campos.get(chave)
        return r[i] if i is not None and i < len(r) else padrao

    # o segmento: cache e regras lidos UMA vez (nao vai a internet aqui -
    # quem consulta a Receita e o BAP Tools, antes de chamar esta funcao)
    try:
        import cnae_bap as _cnae                  # noqa: PLC0415
        contexto_cnae = _cnae.Contexto()
        gerar_base_cliente.aviso_cnae = contexto_cnae.aviso
    except Exception as erro:                     # noqa: BLE001
        contexto_cnae = None
        gerar_base_cliente.aviso_cnae = f"sem CNAE/segmento: {erro}"

    cfg_planner = _config_do_planner(caminho_saida)

    def vendedores(r, uf, cidade, bairro, segmento, na_base):
        """as 8 colunas do vendedor/supervisor (Protheus e Planner)"""
        v = texto(pega(r, "vend"))
        v = v.zfill(6) if v.isdigit() else v
        if cfg_planner is None:
            return [v, "", "", "", "", "", "", ""]
        import planner_nucleo as _nu              # noqa: PLC0415
        (vp, nvp), (sp, nsp) = _nu.pessoa_e_chefe(cfg_planner, v)
        if not na_base:                 # excluido: nao entra no Planner
            return [vp or v, nvp, sp, nsp, "", "", "", ""]
        (vl, nvl), (sl, nsl) = _nu.vendedor_e_supervisor(
            cfg_planner, cod, loja, uf, cidade, bairro, segmento)
        return [vp or v, nvp, sp, nsp, vl, nvl, sl, nsl]

    linhas = []
    excluidos = []          # (linha, motivo, sugestao)
    vistos = set()
    for r in it:
        cod_bruto = pega(r, "cod")
        if cod_bruto is None:
            continue
        cod = texto(cod_bruto).zfill(6)
        loja = texto(pega(r, "loja"))
        if (cod, loja) in vistos:
            continue
        vistos.add((cod, loja))
        if campos["lat"] is not None and campos["lon"] is not None:
            pontos_protheus[f"{cod}-{loja or '00'}"] = (pega(r, "lat"),
                                                        pega(r, "lon"))

        endereco = texto(pega(r, "end"))
        numero_end = ""
        if "," in endereco:
            cabeca, _, cauda = endereco.rpartition(",")
            if cauda.strip()[:6].replace("N", "").replace("º", "").strip().isdigit():
                endereco, numero_end = cabeca.strip(), cauda.strip()

        h = hist.get(cod)
        # ATENCAO AO QUE E SOMA E AO QUE E MEDIA:
        #   RECEITA_*      somam a janela inteira
        #   MEDIA_MENSAL*  dividem pelos meses da janela - e SO ELAS que
        #                  podem ser chamadas de M3M e M6M. Todo "MxM" no
        #                  BAP e media mensal, nunca soma.
        receita = round(h["receita"], 2) if h else 0.0
        media = round(receita / MESES_CURVA, 2) if h else 0.0
        receita_ant = round(h["receita_ant"], 2) if h else 0.0
        media_ant = round(receita_ant / MESES_CURVA, 2) if h else 0.0
        receita6 = round(h["receita6"], 2) if h else 0.0
        media6 = round(receita6 / MESES_FATURAMENTO, 2) if h else 0.0
        acumulado = round(h["acumulado"], 2) if h else 0.0
        ultima = h["ultima"] if h else None
        dias_sem = (ref - ultima).days if (ultima and ref) else None
        atraso = numero(pega(r, "atraso"))
        # o Protheus grava essas duas como texto AAAAMMDD
        cadastrado = data_de(pega(r, "dtcad"))
        primeira_cad = data_de(pega(r, "pricom"))

        decisao = _decisao_cnae(contexto_cnae, cod, loja, pega(r, "cgc"),
                                pega(r, "nome"), pega(r, "fantasia"))
        linha = ([
            cod, loja, _so_digitos(pega(r, "cgc")),
            arrumar_texto(pega(r, "nome")),
            arrumar_texto(pega(r, "fantasia")),
            texto(pega(r, "uf")).upper(),
            arrumar_texto(pega(r, "mun")).upper(),
            arrumar_texto(pega(r, "bairro")).upper(),
            arrumar_texto(endereco), numero_end,
            arrumar_texto(pega(r, "contato")),
            texto(pega(r, "ddd")), texto(pega(r, "tel")),
            numero(pega(r, "limite")), numero(pega(r, "saldo")),
            numero(pega(r, "aberto")), atraso, numero(pega(r, "dias")),
            "SIM" if atraso > 0 else "NAO",
            receita, media, receita_ant, media_ant, receita6, media6,
            acumulado,
            curva_de(max(0.0, media)),
            ultima, dias_sem, status_de(dias_sem),
            (h["vendedor"] if h else ""), (len(h["notas"]) if h else 0),
            (h["primeira"] if h else None),
            cadastrado, primeira_cad,
            ("SIM" if (cadastrado and primeira_cad
                       and cadastrado.strftime("%Y-%m")
                       == primeira_cad.strftime("%Y-%m")) else "NAO"),
        ] + [decisao[c] for c in COLUNAS_CNAE] + [None, None])
        linha += vendedores(r, linha[5], linha[6], linha[7],
                            decisao.get("SEGMENTO"),
                            not decisao.get("EXCLUIDO"))
        # (28/10) o CEP (A1_CEP), so os 8 digitos
        cep_ = re.sub(r"\D", "", texto(pega(r, "cep")))
        linha.append(cep_.zfill(8) if 5 <= len(cep_) <= 8 else "")
        # (10/11) o ATIVO/INATIVO do cadastro do Protheus
        linha.append(status_protheus(pega(r, "status"), pega(r, "blq")))
        if decisao.get("EXCLUIDO"):
            excluidos.append(linha + [decisao.get("MOTIVO_EXCLUSAO", ""),
                                      decisao.get("SEGMENTO_SUGERIDO", "")])
        else:
            linhas.append(linha)
    wb.close()

    linhas.sort(key=lambda x: (x[4], x[5], x[6], x[0]))
    # (13/11) a coordenada do Protheus: da dClientesBap ou, enquanto ela
    # nao tem a coluna, do Relatorio Clientes mais novo que o robo arquivou
    if not pontos_protheus:
        pontos_protheus = pontos_do_relatorio(caminho_saida)
    # na SIMULACAO nao vai a internet: so o que ja foi localizado
    _coordenadas(linhas + excluidos, caminho_saida,
                 0 if caminho_saida.name.upper().startswith("SIMULACAO")
                 else None, protheus=pontos_protheus)
    # os excluidos que mais compraram primeiro: e dali que sai o ajuste
    excluidos.sort(key=lambda x: (-(x[CABECALHO.index("RECEITA_6M")] or 0),
                                  x[4], x[0]))

    out = Workbook()
    w = out.active
    w.title = "BASE_CLIENTE"
    w.append(CABECALHO)
    borda = Border(*(Side(style="thin", color="D9D9D9"),) * 4)
    for c, _ in enumerate(CABECALHO, start=1):
        cel = w.cell(1, c)
        cel.font = Font(bold=True, color="FFFFFF", size=9)
        cel.fill = PatternFill("solid", fgColor="1F4E79")
        cel.alignment = Alignment(horizontal="center", vertical="center",
                                  wrap_text=True)
        cel.border = borda
        w.column_dimensions[get_column_letter(c)].width = LARGURA[c - 1]
    w.row_dimensions[1].height = 30
    for l in linhas:
        w.append(l)
    for l in range(2, w.max_row + 1):
        for c in range(1, len(CABECALHO) + 1):
            cel = w.cell(l, c)
            cel.font = Font(size=9)
            cel.border = borda
        for c in COLUNAS_DINHEIRO:
            w.cell(l, c).number_format = '#,##0.00'
        for c in COLUNAS_DATA:
            w.cell(l, c).number_format = "DD/MM/YYYY"
        for c in COLUNAS_TEXTO:
            w.cell(l, c).number_format = "@"
    w.freeze_panes = "A2"
    w.auto_filter.ref = f"A1:{get_column_letter(len(CABECALHO))}{w.max_row}"

    # ---- EXCLUIDOS: quem nao cabe nos 8 segmentos -----------------------
    # Fica fora de rota, meta e oportunidade - todo programa le so a aba
    # BASE_CLIENTE. Para trazer alguem de volta: AJUSTE_MANUAL da
    # SEGMENTACAO_BAP.xlsx (a coluna SEGMENTO_SUGERIDO ajuda).
    cab_exc = CABECALHO + COLUNAS_EXCLUIDOS_EXTRA
    larg_exc = LARGURA + LARGURA_EXCLUIDOS_EXTRA
    _folha_do_historico(out, "EXCLUIDOS", cab_exc, larg_exc, excluidos,
                        col_dinheiro=COLUNAS_DINHEIRO, col_data=COLUNAS_DATA)
    we = out["EXCLUIDOS"]
    for l in range(2, we.max_row + 1):
        for c in COLUNAS_TEXTO:
            we.cell(l, c).number_format = "@"
    gerar_base_cliente.excluidos = len(excluidos)

    # ---- as duas abas do HISTORICO DE COMPRA ----------------------------
    # HIST_DETALHADO e o espelho do HIST_POR_NF a nivel de produto: as
    # seis primeiras colunas sao as mesmas, e o que muda e que aqui a
    # linha e o produto.
    _folha_do_historico(out, "HIST_POR_NF", COLUNAS_HIST_NF, LARGURA_HIST_NF,
                        hist_nf,
                        col_dinheiro=(8, 10), col_data=(5,), col_pct=(9,))
    _folha_do_historico(out, "HIST_DETALHADO", COLUNAS_HIST_DET,
                        LARGURA_HIST_DET, hist_det,
                        col_dinheiro=(10, 12), col_data=(5,), col_pct=(11,))

    # aba com as regras, para quem abrir o arquivo saber de onde veio o numero
    wr = out.create_sheet("REGRAS")
    wr["A1"] = "Como esta base e calculada"
    wr["A1"].font = Font(bold=True, size=12, color="1F4E79")
    regras = [
        ("Origem", "TABELA_BAP.xlsx - abas dClientesBap e ftPedidos"),
        ("Data de referencia", str(ref) if ref else "sem faturamento na base"),
        ("Janela da curva", f"os {MESES_CURVA} MESES FECHADOS antes do mes "
                            f"da data de referencia - o mes da referencia "
                            f"nao entra em janela nenhuma"),
        ("Receita", "TIPO = VND menos TIPO = DEV"),
        ("RECEITA_PERIODO", f"SOMA do faturado nos ultimos {MESES_CURVA} "
                            f"meses (a janela da curva)"),
        ("MEDIA_MENSAL", f"o M3M: a RECEITA_PERIODO dividida pelos "
                         f"{MESES_CURVA} meses da janela. E ela que define "
                         f"a curva"),
        ("MEDIA_MENSAL_ANTERIOR", f"o M3M ANTERIOR: a media mensal dos "
                                  f"{MESES_CURVA} meses de ANTES da janela "
                                  f"atual. Comparado com o M3M, diz se o "
                                  f"cliente esta crescendo ou caindo"),
        ("RECEITA_6M", f"SOMA do faturado nos ultimos {MESES_FATURAMENTO} "
                       f"meses"),
        ("MEDIA_MENSAL_6M", f"o M6M: a RECEITA_6M dividida pelos "
                            f"{MESES_FATURAMENTO} meses. E o FAT. M6M do "
                            f"resumo gerencial"),
        ("CNPJ", "A1_CGC da dClientesBap, so os digitos e como TEXTO - "
                 "CNPJ que comeca em zero vira numero e perde o zero. "
                 "Pessoa fisica sai com os 11 do CPF"),
        ("NOME_FANTASIA", "A1_NREDUZ da dClientesBap"),
        ("DDD e TELEFONE", "A1_DDD e A1_TEL da dClientesBap, em coluna "
                           "separada - para discar sem ter de separar o "
                           "numero na mao"),
        ("COMPRANTE", f"cliente que comprou nos ultimos {DIAS_COMPRANTE} dias"),
        ("RECEITA_ACUMULADA", "faturado desde sempre, o que existe na base"),
        ("Curva S", f"media mensal >= {CURVA_S:,.2f}"),
        ("Curva A", f"media mensal >= {CURVA_A:,.2f}"),
        ("Curva B", f"media mensal >= {CURVA_B:,.2f}"),
        ("Curva C", f"media mensal >= {CURVA_C:,.2f}"),
        ("Curva Z", "sem faturamento na janela"),
        ("ATIVO", f"comprou ha ate {CHURN_30} dias"),
        ("CHURN 30", f"{CHURN_30 + 1} a {CHURN_60} dias sem comprar"),
        ("CHURN 60", f"{CHURN_60 + 1} a {CHURN_90} dias sem comprar"),
        ("CHURN 90", f"{CHURN_90 + 1} a {INATIVO} dias sem comprar"
                     + (" (vazio: o corte de inativo e 90)" if INATIVO <= CHURN_90 else "")),
        ("CHURN 90+", f"mais de {INATIVO} dias sem comprar"),
        ("NUNCA COMPROU", "sem nenhuma nota faturada na base"),
        ("INADIMPLENTE", "valor em atraso maior que zero"),
        ("Ultimo vendedor", "C5_VEND1 da nota faturada mais recente"),
        ("VENDEDOR_PROTHEUS", "A1_VEND da dClientesBap; o SUPERVISOR_PROTHEUS "
                              "e o chefe dele no cadastro do Planner (o "
                              "A1_SUPER vem vazio)"),
        ("VENDEDOR_PLANNER", "quem o Planner da ao cliente: a excecao do "
                             "analitico, senao quem atende o SEGMENTO na zona "
                             "do bairro; SUPERVISOR_PLANNER e o chefe dele. "
                             "Vazio = zona/segmento sem vendedor (ou cliente "
                             "da aba EXCLUIDOS)"),
        ("HIST_POR_NF", "uma linha por NOTA FISCAL do cliente, da aba "
                        "ftPedidos"),
        ("HIST_DETALHADO", "a mesma coisa, uma linha por PRODUTO da nota. O "
                           "HIST_POR_NF e a soma deste - os totais fecham"),
        ("O que entra no historico", "TIPO = VND (venda) e DEV (devolucao, "
                                     "que ja vem negativa). TRF, EXC e VEA "
                                     "(pedido em aberto) ficam de fora"),
        ("VALOR TABELA", "PRECO_TABELA x quantidade: o valor CHEIO da linha, "
                         "nao o preco unitario"),
        ("PERC. DESCONTO", "no detalhado e o PORCENTAGEM_DESCONTO da propria "
                           "linha; por NF sai dos totais da nota "
                           "(1 - VALOR TOTAL / VALOR TABELA)"),
        ("FORM PAGAMENTO", "a descricao do C5_CONDPAG, pela aba "
                           "ftCondicaoPagamentos"),
        ("CNPJ", "A1_CGC da dClientesBap"),
        ("DESCRICAO PRODUTO", "ProdutosBAP, ligada pelo ID_PRODUTO"),
        ("CNAE_PRINCIPAL e afins", "Receita Federal pelo CNPJ (BrasilAPI, "
                                   "Minha Receita ou CNPJ.ws), guardado em "
                                   "Consulta CNAE\\cache_cnae.json. O BAP Tools "
                                   "consulta so quem ainda nao tem"),
        ("SEGMENTO", "um dos 8 segmentos da SEGMENTACAO_BAP.xlsx (raiz da "
                     "pasta). Ordem: AJUSTE MANUAL > CNAE principal > CNAE "
                     "secundario - a coluna SEGMENTO_ORIGEM diz qual valeu. "
                     "O CNAE e a regra: o nome do cliente nao decide"),
        ("SITUACAO_RECEITA", "ATIVA, INAPTA, BAIXADA, SUSPENSA na Receita; "
                             "PESSOA FISICA para CPF"),
        ("STATUS_PROTHEUS", "ATIVO/INATIVO do cadastro do Protheus (STATUS "
                            "da dClientesBap = A1_MSBLQL 1 bloqueado). "
                            "INATIVO sai da rota do vendedor no Planner e "
                            "vai INATIVO, com o vendedor padrao, no .json da "
                            "base de clientes"),
        ("Os 8 SEGMENTOS", "AUTOPECAS, MOTOPECAS, DISTRIBUIDOR DE BATERIAS, "
                           "AUTOCENTER, OFICINA MECANICA, POSTO E TROCA DE "
                           "OLEO, FROTISTA/REVENDEDOR, INDUSTRIA"),
        ("EXCLUIDOS", "quem nao cabe nos 8 (CPF, sem CNPJ, sem CNAE, CNAE "
                      "fora dos 8, ou EXCLUIR no ajuste manual). Sai da "
                      "BASE_CLIENTE: fora de rota, meta e oportunidade. A "
                      "aba EXCLUIDOS traz o MOTIVO e um SEGMENTO_SUGERIDO "
                      "pelo nome"),
    ]
    for i, (a, b) in enumerate(regras, start=3):
        wr.cell(i, 1, a).font = Font(bold=True, size=10)
        wr.cell(i, 2, b).font = Font(size=10)
    wr.column_dimensions["A"].width = 22
    wr.column_dimensions["B"].width = 62

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    out.save(caminho_saida)
    out.close()
    gerar_base_cliente.ultimo_historico = {"notas": len(hist_nf),
                                           "itens": len(hist_det)}
    return len(linhas), ref


if __name__ == "__main__":
    entrada = sys.argv[1] if len(sys.argv) > 1 else "TABELA_BAP.xlsx"
    saida = sys.argv[2] if len(sys.argv) > 2 else "BASE_CLIENTE.xlsx"
    qtd, ref = gerar_base_cliente(entrada, saida)
    print(f"BASE_CLIENTE gravada: {qtd} clientes (referencia {ref}) -> {saida}")


def colunas_faltando(caminho) -> list:
    """
    As colunas que esta versao do programa escreve e que NAO estao na
    BASE_CLIENTE do caminho. Lista vazia = a base esta no formato de hoje.

    Serve para pegar o caso que a data nao pega: a base foi gerada por uma
    versao ANTIGA do BAP Tools, e a TABELA_BAP nao mudou desde entao -
    entao, pela data, esta "tudo em dia", mas faltam colunas (foi assim
    que o M3M ANTERIOR ficou zerado sem ninguem entender).
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return list(CABECALHO)
    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
        ws = wb["BASE_CLIENTE"] if "BASE_CLIENTE" in wb.sheetnames else wb.active
        cab = {texto(c) for c in next(ws.iter_rows(values_only=True))}
        wb.close()
    except (OSError, ValueError, StopIteration, KeyError):
        return []
    return [c for c in CABECALHO if c not in cab]
