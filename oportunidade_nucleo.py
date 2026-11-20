# -*- coding: utf-8 -*-
"""
O MOTOR DO OPORTUNIDADES BAP - a conta, sem tela nenhuma.

Duas oportunidades, duas perguntas diferentes:

  DE CLIENTE ... a quem ir atras. Vem da BASE_CLIENTE (limite, atraso,
                 dias sem compra) mais o PLANNER (vendedor, zona) mais a
                 TABELA_BAP (o ultimo item comprado). A conta ja existia
                 no meta_nucleo e e reaproveitada daqui.

  DE ESTOQUE ... o que empurrar. O QUE TEM EM CADA FILIAL sai do
                 RELATORIOS\\ESTOQUE_BAP.xlsx - o mesmo arquivo que voce
                 abre para conferir. Da TABELA_BAP vem o resto:
                 ftTabelaPreco o preco de capital e de interior, Filiais
                 a regiao de cada filial, e ftPedidos quando o item foi
                 vendido pela ultima vez - e dai sai a CURVA DO PRODUTO.

DE ONDE VEM O ESTOQUE (nesta ordem)
  1. RELATORIOS\\ESTOQUE_BAP.xlsx ..... o estoque das lojas PMZ ja somado
     por filial BAP, com os dois precos. E a fonte oficial.
  2. TABELA_BAP, aba ftEstoquePMZ .... a mesma conta feita na hora
     (QTD_TOTAL - QTD_SEPARADA, somando as lojas de cada filial BAP),
     para quando o ESTOQUE_BAP ainda nao foi gerado.
  3. TABELA_BAP, aba ftEstoqueBap .... ultimo recurso. CUIDADO: essa aba
     e o estoque proprio do Protheus da BAP, que e outra coisa e da
     numeros MUITO menores. Ate 07/09/2026 era ela que o app lia, e por
     isso a tela mostrava 8 onde o ESTOQUE_BAP mostrava 124.

A CURVA DO PRODUTO
  Nao e a curva do cliente. Aqui ela responde "com que frequencia este
  item gira", olhando SEMPRE de HOJE para tras:

      A   vende toda quinzena ....... ultima venda ate 15 dias
      B   vende todo mes ............ ate 30 dias
      C   vendeu nos ultimos 3 meses  ate 90 dias
      D   vendeu nos ultimos 6 meses  ate 180 dias
      Z   parado ..................... mais de 180 dias, ou nunca

  Os cortes sao parametrizaveis na aba PARAMETROS. Cada produto recebe
  DUAS curvas:

      CURVA FILIAL ... pela venda DAQUELA filial - e a que diz se o item
                       gira ALI, que e o que interessa para quem vende ali
      CURVA GERAL .... pela venda em QUALQUER filial - mostra se o item
                       gira na BAP como um todo

  Item A no geral e Z na filial e a oportunidade classica: vende bem na
  rede e esta encalhado naquele estoque.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
try:  # leitura rapida com cache (sem o arquivo: openpyxl)
    from xlsx_rapido import load_workbook  # noqa: F811,PLC0415
except ImportError:
    from openpyxl import load_workbook  # noqa: PLC0415

try:
    from pastas_bap import RELATORIOS as RELATORIOS_SUB
except ImportError:
    RELATORIOS_SUB = "RELATORIOS"

import familia_nucleo as fam

ARQUIVO_TABELA = "TABELA_BAP.xlsx"
ARQUIVO_ESTOQUE = "ESTOQUE_BAP.xlsx"

# --------------------------------------------------------------------------
# parametros
# --------------------------------------------------------------------------
# Os cortes da curva, em DIAS desde a ultima venda. A ordem importa: a
# primeira faixa em que o produto couber e a dele.
CURVAS_PADRAO = [
    {"letra": "A", "dias": 15,
     "texto": "vende toda quinzena (ate 15 dias)"},
    {"letra": "B", "dias": 30,
     "texto": "vende todo mes (ate 30 dias)"},
    {"letra": "C", "dias": 90,
     "texto": "vendeu nos ultimos 3 meses (ate 90 dias)"},
    {"letra": "D", "dias": 180,
     "texto": "vendeu nos ultimos 6 meses (ate 180 dias)"},
]
LETRA_PARADO = "Z"
TEXTO_PARADO = "sem venda ha mais de 180 dias (ou nunca vendeu)"

PARAMETROS_PADRAO = {
    "curvas": CURVAS_PADRAO,
    # o sufixo da tabela de preco que e capital e o que e interior.
    # Na TABELA_BAP as tabelas sao AM1, AM2, PA1, PA2... - o numero no
    # fim diz qual e qual.
    "sufixo_capital": "1",
    "sufixo_interior": "2",
    "so_com_estoque": True,
    "kit": None,          # preenchido com kit_padrao() no primeiro uso
}


def parametros_novos() -> dict:
    p = json.loads(json.dumps(PARAMETROS_PADRAO))
    p["kit"] = kit_padrao()
    return p


def carregar_parametros(caminho) -> dict:
    caminho = Path(caminho)
    p = parametros_novos()
    if caminho.exists():
        try:
            with open(caminho, encoding="utf-8") as f:
                guardado = json.load(f)
            for k, v in guardado.items():
                if k in p:
                    p[k] = v
        except (OSError, ValueError):
            pass
    if not p.get("curvas"):
        p["curvas"] = json.loads(json.dumps(CURVAS_PADRAO))
    p["kit"] = {**kit_padrao(), **(p.get("kit") or {})}
    p["kit"]["cotas"] = {**kit_padrao()["cotas"],
                         **(p["kit"].get("cotas") or {})}
    # config antigo nao tinha a trava: entra com o padrao, nao com zero
    # a alcada unica virou um % DESC. GERENTE por curva: o valor antigo
    # vira o ponto de partida das cinco, para ninguem perder a regra
    _alcada = p["kit"].pop("alcada_gerente", None)
    if _alcada is not None:
        for _regra in p["kit"]["cotas"].values():
            _regra.setdefault("desc_gerente", _numero(_alcada))
    for _curva, _regra in p["kit"]["cotas"].items():
        for _novo in ("markup_min", "desc_gerente"):
            if _novo not in _regra:
                _regra[_novo] = (kit_padrao()["cotas"].get(_curva)
                                 or {}).get(_novo, 0.0)
    p["kit"]["investimento"] = {**kit_padrao()["investimento"],
                                **(p["kit"].get("investimento") or {})}
    if not p["kit"].get("caixas"):
        p["kit"]["caixas"] = caixas_padrao()
    if not p["kit"].get("sucata"):
        p["kit"]["sucata"] = sucata_padrao()
    if not p["kit"].get("sucata_ss"):
        p["kit"]["sucata_ss"] = sucata_ss_padrao()
    for chave in ("verba_geral", "gerar"):
        p["kit"][chave] = {**kit_padrao()[chave],
                           **(p["kit"].get(chave) or {})}
    # as filiais sao SO o que o usuario escolheu: nao ha padrao para
    # herdar, e config antigo simplesmente nao tem a chave
    p["kit"]["filiais"] = {_texto(c): bool(v) for c, v
                           in (p["kit"].get("filiais") or {}).items()}
    p["kit"].pop("limite_valor", None)     # saiu em 14/09/2026
    return p


def gravar_parametros(par: dict, caminho) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(par, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _numero(v) -> float:
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


def _data(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = _texto(v)
    if not s:
        return None
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y"):
        try:
            return dt.datetime.strptime(s[:10], f).date()
        except ValueError:
            pass
    return None


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def limpar(v) -> str:
    """Sem acento, maiusculo e sem espaco sobrando - para comparar."""
    return re.sub(r"\s+", " ", _sem_acento(_texto(v)).upper()).strip()


def achar_tabela(raiz):
    raiz = Path(raiz)
    for tentativa in (raiz / RELATORIOS_SUB / ARQUIVO_TABELA,
                      raiz / ARQUIVO_TABELA):
        if tentativa.exists():
            return tentativa
    return None


def achar_estoque_bap(raiz=None, perto_de=None):
    """
    O ESTOQUE_BAP.xlsx, procurado na pasta atual e ao lado da TABELA_BAP -
    nunca por caminho fixo, para a pasta poder ser movida de lugar.
    """
    tentativas = []
    if raiz:
        raiz = Path(raiz)
        tentativas += [raiz / RELATORIOS_SUB / ARQUIVO_ESTOQUE,
                       raiz / ARQUIVO_ESTOQUE]
    if perto_de:
        pasta = Path(perto_de).parent
        tentativas += [pasta / ARQUIVO_ESTOQUE,
                       pasta.parent / RELATORIOS_SUB / ARQUIVO_ESTOQUE,
                       pasta.parent / ARQUIVO_ESTOQUE]
    for t in tentativas:
        if t.exists():
            return t
    return None


# --------------------------------------------------------------------------
# a curva do produto
# --------------------------------------------------------------------------
def curva_de(dias, par: dict) -> str:
    """
    A letra da curva a partir dos DIAS desde a ultima venda. Sem venda
    nenhuma (dias None) e Z, igual a quem parou faz tempo.
    """
    if dias is None:
        return LETRA_PARADO
    for faixa in par.get("curvas") or CURVAS_PADRAO:
        try:
            if float(dias) <= float(faixa["dias"]):
                return _texto(faixa["letra"]) or LETRA_PARADO
        except (TypeError, ValueError, KeyError):
            continue
    return LETRA_PARADO


def texto_das_curvas(par: dict) -> list:
    """As faixas em texto, para a tela e para a aba PARAMETROS do Excel."""
    saida = []
    anterior = 0
    for faixa in par.get("curvas") or CURVAS_PADRAO:
        dias = int(_numero(faixa.get("dias")))
        saida.append((_texto(faixa.get("letra")),
                      f"ultima venda entre {anterior + 1} e {dias} dias",
                      _texto(faixa.get("texto"))))
        anterior = dias
    saida.append((LETRA_PARADO,
                  f"ultima venda ha mais de {anterior} dias, ou nunca",
                  TEXTO_PARADO))
    return saida


# --------------------------------------------------------------------------
# ler a TABELA_BAP: filiais, estoque, preco e a ultima venda de cada item
# --------------------------------------------------------------------------
def _cabecalho(ws):
    it = ws.iter_rows(values_only=True)
    return [_texto(c) for c in next(it)], it


def _onde(cab, *nomes):
    for n in nomes:
        if n in cab:
            return cab.index(n)
    return None


def ler_filiais(wb) -> dict:
    """
    {codigo da filial -> {'regiao': 'MANAUS', 'cidades': [...]}}.
    A REGIAO e a coluna CIDADE da aba Filiais: e o nome do polo (MANAUS,
    BELEM, BOA VISTA...), nao a cidade do cliente.
    """
    if "Filiais" not in wb.sheetnames:
        return {}
    cab, it = _cabecalho(wb["Filiais"])
    i_bap = _onde(cab, "FILIAL_BAP")
    i_reg = _onde(cab, "CIDADE")
    i_cid = _onde(cab, "CIDADE_INTERIOR")
    if i_bap is None:
        return {}
    saida = {}
    for r in it:
        cod = _texto(r[i_bap])
        if not cod:
            continue
        reg = saida.setdefault(cod, {"regiao": "", "cidades": []})
        if i_reg is not None and not reg["regiao"]:
            reg["regiao"] = _texto(r[i_reg])
        if i_cid is not None:
            cidade = _texto(r[i_cid])
            if cidade and cidade not in reg["cidades"]:
                reg["cidades"].append(cidade)
    return saida


def ler_precos(wb, par: dict) -> dict:
    """
    {(filial, produto) -> {'capital': x, 'interior': y, 'tabelas': {...}}}

    Na TABELA_BAP as tabelas se chamam AM1, AM2, PA1, PA2... O NUMERO NO
    FIM diz se e capital ou interior; qual e qual esta nos parametros,
    porque isso e regra de negocio e nao coisa que se adivinhe.
    """
    if "ftTabelaPreco" not in wb.sheetnames:
        return {}
    cab, it = _cabecalho(wb["ftTabelaPreco"])
    i_fil = _onde(cab, "DA1_FILIAL")
    i_tab = _onde(cab, "DA1_CODTAB")
    i_pro = _onde(cab, "DA1_CODPRO")
    i_pre = _onde(cab, "DA1_PRCVEN")
    if None in (i_tab, i_pro, i_pre):
        return {}
    # a coluna DA1_FILIAL aparece DUAS vezes: a primeira com o codigo
    # longo (40101001) e a segunda com o curto (0101001). Vale a longa,
    # que e a mesma do estoque.
    cap = _texto(par.get("sufixo_capital") or "1")
    inte = _texto(par.get("sufixo_interior") or "2")
    saida = {}
    for r in it:
        filial = _texto(r[i_fil]) if i_fil is not None else ""
        produto = _texto(r[i_pro])
        if not produto:
            continue
        tabela = _texto(r[i_tab]).upper()
        preco = _numero(r[i_pre])
        reg = saida.setdefault((filial, produto),
                               {"capital": 0.0, "interior": 0.0,
                                "tabelas": {}})
        reg["tabelas"][tabela] = preco
        if tabela.endswith(cap):
            reg["capital"] = preco
        elif tabela.endswith(inte):
            reg["interior"] = preco
    return saida


def _meses_para_tras(hoje, quantos=12) -> list:
    """Os N meses fechados ate o mes de hoje, do mais antigo ao mais novo."""
    ano, mes = hoje.year, hoje.month
    saida = []
    for _ in range(quantos):
        saida.append(f"{ano:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    return list(reversed(saida))


def ler_giro(wb, hoje=None, meses=12) -> dict:
    """
    UMA passada pela ftPedidos, de onde sai tudo que fala de VENDA:

        ultima_filial / ultima_geral ... quando o produto saiu pela
                                         ultima vez (a CURVA vem daqui)
        qtd_filial / qtd_geral ........  o volume de sempre
        ultima_vend ................... a ultima venda DAQUELE VENDEDOR
        janela[escopo][produto] ....... em que meses dos ultimos 12 ele
                                        saiu, como um mapa de bits: o bit
                                        0 e o mes mais antigo. E dai que
                                        sai a MEDIA SKU/MES
        volume[escopo][produto] ....... quanto saiu nos ultimos 12 meses
        filial_do_vendedor ............ a filial onde ele mais vende - e
                                        o estoque dela que vale para ele

    So conta VENDA: devolucao nao e giro, e transferencia menos ainda.
    O escopo e ("geral",), ("filial", cod) ou ("vendedor", cod).
    """
    hoje = hoje or dt.date.today()
    vazio = {"ultima_filial": {}, "ultima_geral": {}, "qtd_filial": {},
             "qtd_geral": {}, "ultima_vend": {}, "janela": {}, "volume": {},
             "filial_do_vendedor": {}, "meses": _meses_para_tras(hoje, meses),
             "vendedores": []}
    if "ftPedidos" not in wb.sheetnames:
        return vazio
    cab, it = _cabecalho(wb["ftPedidos"])
    i_fil = _onde(cab, "D2FILIAL", "D2_FILIAL")
    i_pro = _onde(cab, "D2_COD")
    i_tipo = _onde(cab, "TIPO")
    i_nf = _onde(cab, "DATA_NF")
    i_em = _onde(cab, "D2_EMISSAO")
    i_qtd = _onde(cab, "D2_QUANT")
    i_vend = _onde(cab, "C5_VEND1", "C5_VEND", "COD_VENDEDOR")
    if i_pro is None:
        return vazio

    lista_meses = _meses_para_tras(hoje, meses)
    bit_do_mes = {m: 1 << i for i, m in enumerate(lista_meses)}
    por_filial, geral, por_vend = {}, {}, {}
    qtd_filial, qtd_geral = defaultdict(float), defaultdict(float)
    janela = defaultdict(lambda: defaultdict(int))
    volume = defaultdict(lambda: defaultdict(float))
    filiais_do_vend = defaultdict(lambda: defaultdict(float))

    for r in it:
        if i_tipo is not None and _texto(r[i_tipo]).upper() not in ("VND",
                                                                   "VEA"):
            continue
        produto = _texto(r[i_pro])
        if not produto:
            continue
        d = _data(r[i_nf] if i_nf is not None else None) \
            or _data(r[i_em] if i_em is not None else None)
        if not d:
            continue
        filial = _texto(r[i_fil]) if i_fil is not None else ""
        vend = _texto(r[i_vend]) if i_vend is not None else ""
        qtd = _numero(r[i_qtd]) if i_qtd is not None else 0.0
        chave = (filial, produto)
        if chave not in por_filial or por_filial[chave] < d:
            por_filial[chave] = d
        if produto not in geral or geral[produto] < d:
            geral[produto] = d
        qtd_filial[chave] += qtd
        qtd_geral[produto] += qtd
        if vend:
            cv = (vend, produto)
            if cv not in por_vend or por_vend[cv] < d:
                por_vend[cv] = d
            filiais_do_vend[vend][filial] += qtd

        bit = bit_do_mes.get(f"{d.year:04d}-{d.month:02d}")
        if not bit:
            continue                      # fora dos ultimos 12 meses
        for escopo in (("geral",), ("filial", filial)) + (
                (("vendedor", vend),) if vend else ()):
            janela[escopo][produto] |= bit
            volume[escopo][produto] += qtd

    filial_do_vend = {}
    for cod, contas in filiais_do_vend.items():
        # a filial DELE e aquela de onde ele mais tira mercadoria
        filial_do_vend[cod] = max(contas, key=contas.get)

    return {
        "ultima_filial": por_filial, "ultima_geral": geral,
        "qtd_filial": dict(qtd_filial), "qtd_geral": dict(qtd_geral),
        "ultima_vend": por_vend,
        "janela": {k: dict(v) for k, v in janela.items()},
        "volume": {k: dict(v) for k, v in volume.items()},
        "filial_do_vendedor": filial_do_vend,
        "meses": lista_meses,
        "vendedores": sorted(filial_do_vend),
    }


def ler_ultima_venda(wb, hoje=None) -> tuple:
    """
    Quando cada produto foi vendido pela ultima vez, por filial e no
    geral. So conta VENDA - devolucao nao e giro, e transferencia menos
    ainda.

    Devolve (por_filial, geral, qtd_filial, qtd_geral), cada um um dicio-
    nario com a data (ou a quantidade) da ultima venda.
    """
    g = ler_giro(wb, hoje)
    return (g["ultima_filial"], g["ultima_geral"],
            g["qtd_filial"], g["qtd_geral"])


def _vazio():
    return {"juntas": defaultdict(lambda: {"estoque": 0.0, "reserva": 0.0,
                                           "pedido": 0.0, "custo": 0.0,
                                           "origem_custo": ""}),
            "nomes": {}, "curtas": {}, "precos": {}, "cds": {},
            "fonte": "", "quando": ""}


def ler_estoque_do_arquivo(caminho) -> dict:
    """
    O RELATORIOS\\ESTOQUE_BAP.xlsx - a foto oficial do estoque, uma linha
    por FILIAL_BAP e produto, com os dois precos ja resolvidos. E o mesmo
    arquivo que o usuario abre para conferir, entao a tela tem de bater
    com ele numero por numero.
    """
    saida = _vazio()
    wb = load_workbook(Path(caminho), read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        cab, it = _cabecalho(ws)
        i_fil = _onde(cab, "FILIAL_BAP")
        i_pro = _onde(cab, "COD_PRODUTO")
        i_des = _onde(cab, "DESCRICAO_PRODUTO")
        i_est = _onde(cab, "ESTOQUE")
        i_custo = _onde(cab, "PPEDIDO", "CUSTO")
        i_cd = _onde(cab, "FILIAL_CD")
        i_org = _onde(cab, "ORIGEM_CUSTO")
        i_cap = _onde(cab, "PRECO_CAPITAL")
        i_int = _onde(cab, "PRECO_INTERIOR")
        i_data = _onde(cab, "DATA")
        i_hora = _onde(cab, "HORA")
        if None in (i_fil, i_pro, i_est):
            raise ValueError(
                f"{ARQUIVO_ESTOQUE} sem FILIAL_BAP/COD_PRODUTO/ESTOQUE.")
        for r in it:
            produto = _texto(r[i_pro])
            filial = _texto(r[i_fil])
            if not produto or not filial:
                continue
            chave = (filial, produto)
            saida["juntas"][chave]["estoque"] += _numero(r[i_est])
            if i_custo is not None:
                custo = _numero(r[i_custo])
                if custo:
                    saida["juntas"][chave]["custo"] = custo
                    saida["juntas"][chave]["origem_custo"] = (
                        _texto(r[i_org]) if i_org is not None else "CD")
            if i_cd is not None and filial not in saida["cds"]:
                saida["cds"][filial] = _texto(r[i_cd])
            if i_des is not None and produto not in saida["nomes"]:
                saida["nomes"][produto] = _texto(r[i_des])
            cap = _numero(r[i_cap]) if i_cap is not None else 0.0
            inte = _numero(r[i_int]) if i_int is not None else 0.0
            if cap or inte:
                saida["precos"][chave] = {"capital": cap, "interior": inte,
                                          "tabelas": {}}
            if not saida["quando"] and i_data is not None:
                saida["quando"] = (
                    _texto(r[i_data])
                    + (" " + _texto(r[i_hora]) if i_hora is not None else "")
                ).strip()
    finally:
        wb.close()
    saida["fonte"] = f"{RELATORIOS_SUB}\\{ARQUIVO_ESTOQUE}"
    return saida


def ler_estoque_pmz(wb) -> dict:
    """
    O estoque das lojas PMZ somado por FILIAL BAP, direto da TABELA_BAP -
    a mesma conta que gera o ESTOQUE_BAP.xlsx (QTD_TOTAL - QTD_SEPARADA,
    loja por loja). Serve para quando o ESTOQUE_BAP ainda nao existe.
    """
    saida = _vazio()
    if "ftEstoquePMZ" not in wb.sheetnames or "Filiais" not in wb.sheetnames:
        return saida
    # loja PMZ -> filial BAP
    cab, it = _cabecalho(wb["Filiais"])
    i_loja = _onde(cab, "COD_FILIAL")
    i_bap = _onde(cab, "FILIAL_BAP")
    if None in (i_loja, i_bap):
        return saida
    i_cd = _onde(cab, "CD_FILIAL")
    de_loja = {}
    cd_da_bap = {}
    for r in it:
        loja, bap = _texto(r[i_loja]), _texto(r[i_bap])
        if loja and bap:
            de_loja[loja] = bap
        # o CUSTO da filial e o do CD dela, nao o de cada loja
        if bap and i_cd is not None and bap not in cd_da_bap:
            cd = _texto(r[i_cd])
            if cd:
                cd_da_bap[bap] = cd
    saida["cds"] = dict(cd_da_bap)

    cab, it = _cabecalho(wb["ftEstoquePMZ"])
    i_fil = _onde(cab, "FILIAL")
    i_pro = _onde(cab, "PRODUTO", "COD_PRODUTO", "B2_COD")
    i_des = _onde(cab, "DESCRICAO_COMPL", "DESCRICAO", "B1_DESC")
    i_qtd = _onde(cab, "QTD_TOTAL", "QTDE", "QTD")
    i_sep = _onde(cab, "QTD_SEPARADA", "QTD_RESERVADA")
    i_custo = _onde(cab, "PPEDIDO", "CUSTO")
    if None in (i_fil, i_pro, i_qtd):
        return saida
    # O CUSTO vem do CD da filial. Quando o CD nao tem aquele item (e
    # acontece em 2 de cada 3 linhas), vale a media das lojas da propria
    # filial e, em ultimo caso, a da rede - e a coluna ORIGEM DO CUSTO
    # diz qual foi, para ninguem tomar media por custo do CD.
    do_cd, da_filial, da_rede = {}, defaultdict(list), defaultdict(list)
    for r in it:
        produto = _texto(r[i_pro])
        loja = _texto(r[i_fil])
        filial = de_loja.get(loja)
        if not produto or not filial:
            continue
        qtd = _numero(r[i_qtd])
        if i_sep is not None:
            qtd -= _numero(r[i_sep])
        saida["juntas"][(filial, produto)]["estoque"] += max(qtd, 0.0)
        if i_custo is not None:
            custo = _numero(r[i_custo])
            if custo > 0:
                if cd_da_bap.get(filial) == loja:
                    do_cd[(filial, produto)] = custo
                da_filial[(filial, produto)].append(custo)
                da_rede[produto].append(custo)
        if i_des is not None and produto not in saida["nomes"]:
            saida["nomes"][produto] = _texto(r[i_des])
    for chave in saida["juntas"]:
        custo, origem = do_cd.get(chave), "CD"
        if not custo and da_filial.get(chave):
            custo = sum(da_filial[chave]) / len(da_filial[chave])
            origem = "FILIAL"
        if not custo and da_rede.get(chave[1]):
            custo = sum(da_rede[chave[1]]) / len(da_rede[chave[1]])
            origem = "REDE"
        if custo:
            saida["juntas"][chave]["custo"] = custo
            saida["juntas"][chave]["origem_custo"] = origem
    saida["fonte"] = f"{ARQUIVO_TABELA} (ftEstoquePMZ)"
    return saida


def ler_estoque_protheus(wb) -> dict:
    """
    A aba ftEstoqueBap: o estoque PROPRIO da BAP no Protheus. Nao e o que
    as lojas tem para vender - e bem menor. So entra como ultimo recurso,
    quando nao ha ESTOQUE_BAP.xlsx nem ftEstoquePMZ.
    """
    saida = _vazio()
    if "ftEstoqueBap" not in wb.sheetnames:
        return saida
    cab, it = _cabecalho(wb["ftEstoqueBap"])
    i_fil = _onde(cab, "B2_FILIAL")
    i_curta = _onde(cab, "B2_FILIAL_ORIGINAL")
    i_cod = _onde(cab, "B2_COD")
    i_desc = _onde(cab, "B1_DESC")
    i_qatu = _onde(cab, "B2_QATU")
    i_res = _onde(cab, "B2_RESERVA")
    i_ped = _onde(cab, "B2_QPEDVEN")
    i_custo = _onde(cab, "B2_CM1")
    if i_cod is None:
        return saida
    for r in it:
        produto = _texto(r[i_cod])
        if not produto:
            continue
        filial = _texto(r[i_fil]) if i_fil is not None else ""
        reg = saida["juntas"][(filial, produto)]
        reg["estoque"] += _numero(r[i_qatu]) if i_qatu is not None else 0.0
        reg["reserva"] += _numero(r[i_res]) if i_res is not None else 0.0
        reg["pedido"] += _numero(r[i_ped]) if i_ped is not None else 0.0
        custo = _numero(r[i_custo]) if i_custo is not None else 0.0
        if custo:
            reg["custo"] = custo
        if i_desc is not None and produto not in saida["nomes"]:
            saida["nomes"][produto] = _texto(r[i_desc])
        if i_curta is not None and filial not in saida["curtas"]:
            saida["curtas"][filial] = _texto(r[i_curta])
    saida["fonte"] = f"{ARQUIVO_TABELA} (ftEstoqueBap - estoque proprio)"
    return saida


# ==========================================================================
# O PESO DE CADA FILIAL NA VERBA
# ==========================================================================
# A verba da categoria nao se divide em partes iguais: filial que fatura
# mais vende mais kit, e tem de receber mais verba. O peso sai do
# FATURAMENTO dos ultimos 12 meses de cada filial BAP, lido da mesma
# ftPedidos de que todo o resto sai.
#
# COM UM PISO: nenhuma filial fica abaixo de PISO_DA_FILIAL. Uma praca
# pequena que receba 2% da verba nao monta kit nenhum - e kit nenhum e
# pior do que um kit pequeno, porque ali ninguem tem o que oferecer.
# Depois do piso os pesos sao normalizados para somar 100%.
#
# O numero e so a SUGESTAO: ele nasce calculado na aba de parametros,
# ao lado de cada filial, e pode ser trocado na mao a qualquer momento.
PISO_DA_FILIAL = 10.0
MESES_DO_PESO = 12


def faturamento_por_filial(wb, hoje=None, meses=MESES_DO_PESO) -> dict:
    """{codigo da filial BAP -> faturado em R$ nos ultimos N meses}."""
    hoje = hoje or dt.date.today()
    if "ftPedidos" not in getattr(wb, "sheetnames", ()):
        return {}
    cab, it = _cabecalho(wb["ftPedidos"])
    i_fil = _onde(cab, "D2FILIAL", "D2_FILIAL")
    i_val = _onde(cab, "VALOR TOTAL", "VALOR_TOTAL")
    i_tipo = _onde(cab, "TIPO")
    i_nf = _onde(cab, "DATA_NF")
    i_em = _onde(cab, "D2_EMISSAO")
    if i_fil is None or i_val is None:
        return {}
    limite = set(_meses_para_tras(hoje, meses))
    soma = defaultdict(float)
    for r in it:
        if i_tipo is not None and _texto(r[i_tipo]).upper() not in ("VND",
                                                                   "VEA"):
            continue
        d = (_data(r[i_nf] if i_nf is not None else None)
             or _data(r[i_em] if i_em is not None else None))
        if not d or f"{d.year:04d}-{d.month:02d}" not in limite:
            continue
        filial = _texto(r[i_fil])
        if filial:
            soma[filial] += _numero(r[i_val])
    return dict(soma)


def pesos_das_filiais(faturamento: dict, filiais=None,
                      piso: float = PISO_DA_FILIAL) -> dict:
    """
    {filial -> % da verba}, pelo peso no faturamento, com piso.

    `filiais` e a lista que DEVE aparecer - filial que existe no cadastro
    mas nao faturou nada no periodo entra mesmo assim, no piso, senao ela
    sumiria da tela e ninguem entenderia por que nao saiu kit.

    A soma dos percentuais e sempre 100, e isso e o que importa: o peso
    de cada uma e lido contra o total, nao contra a verba.
    """
    chaves = sorted(set(filiais or faturamento or {}))
    if not chaves:
        return {}
    piso = max(0.0, min(100.0, float(piso or 0.0)))
    # o piso nao pode valer mais do que a divisao igual: com 7 filiais e
    # piso de 20% nao haveria o que distribuir, entao ele cede
    teto_do_piso = 100.0 / len(chaves)
    piso = min(piso, teto_do_piso)
    total = sum(max(0.0, faturamento.get(c, 0.0)) for c in chaves)
    if total <= 0:
        igual = 100.0 / len(chaves)
        return {c: round(igual, 2) for c in chaves}
    # a parte que o piso ja garantiu sai do bolo; o resto vai por peso
    sobra = 100.0 - piso * len(chaves)
    pesos = {}
    for c in chaves:
        fatia = max(0.0, faturamento.get(c, 0.0)) / total
        pesos[c] = round(piso + sobra * fatia, 2)
    # o arredondamento tira ou poe alguns centesimos: a diferenca vai
    # para a maior, que e quem menos sente
    falta = round(100.0 - sum(pesos.values()), 2)
    if falta and pesos:
        maior = max(pesos, key=lambda c: pesos[c])
        pesos[maior] = round(pesos[maior] + falta, 2)
    return pesos


def _dinheiro_simples(valor) -> str:
    """R$ 1.234,56 - so para as mensagens de diagnostico."""
    try:
        return "R$ " + f"{float(valor):,.2f}".replace(",", "@").replace(
            ".", ",").replace("@", ".")
    except (TypeError, ValueError):
        return "R$ 0,00"


def _markup(preco, custo):
    """
    O MARKUP: quanto o preco de venda esta acima do custo, em %.
        markup = preco de venda / custo - 1
    Sem custo nao da para calcular, e ai fica vazio mesmo - numero
    inventado aqui viraria decisao errada la na frente.
    """
    preco, custo = float(preco or 0), float(custo or 0)
    if preco <= 0 or custo <= 0:
        return None
    return (preco / custo - 1.0) * 100.0


def _classificacao(descricao) -> dict:
    """FAMILIA, GRUPO e LINHA da peca, a partir da descricao."""
    familia, grupo, linha = fam.classificar(descricao)
    return {"familia": familia, "grupo": grupo, "linha": linha}


def montar_estoque(caminho_tabela, par: dict, hoje=None, raiz=None) -> dict:
    """
    Uma linha por PRODUTO EM CADA FILIAL, com o estoque, os dois precos,
    a regiao e as duas curvas. E a lista de onde sai a oportunidade: o
    que esta parado aqui e girando ali.

    O ESTOQUE vem do RELATORIOS\\ESTOQUE_BAP.xlsx - o mesmo arquivo que
    voce confere. Sem ele, a conta e refeita na hora pelo ftEstoquePMZ.
    """
    caminho_tabela = Path(caminho_tabela)
    hoje = hoje or dt.date.today()
    arq_estoque = achar_estoque_bap(raiz, caminho_tabela)
    lido = None
    aviso = ""
    if arq_estoque:
        try:
            lido = ler_estoque_do_arquivo(arq_estoque)
        except (OSError, ValueError, KeyError) as erro:
            aviso = f"nao consegui ler o {ARQUIVO_ESTOQUE}: {erro}"
            lido = None

    wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    try:
        filiais = ler_filiais(wb)
        precos = ler_precos(wb, par)
        giro = ler_giro(wb, hoje)
        # o faturamento de cada filial, que e de onde sai o PESO DELA na
        # verba (ver pesos_das_filiais)
        fat_filial = faturamento_por_filial(wb, hoje)
        ult_filial = giro["ultima_filial"]
        ult_geral = giro["ultima_geral"]
        qtd_filial = giro["qtd_filial"]
        qtd_geral = giro["qtd_geral"]
        if lido is None or not lido["juntas"]:
            lido = ler_estoque_pmz(wb)
            if not aviso and not arq_estoque:
                aviso = (f"{ARQUIVO_ESTOQUE} nao encontrado em "
                         f"{RELATORIOS_SUB}: refiz a conta pelo ftEstoquePMZ.")
        if not lido["juntas"]:
            lido = ler_estoque_protheus(wb)
            aviso = (f"sem {ARQUIVO_ESTOQUE} e sem ftEstoquePMZ: usei o "
                     f"estoque proprio do Protheus, que e bem menor.")
        if not lido["juntas"]:
            raise ValueError(
                f"Nao achei estoque nenhum: nem {ARQUIVO_ESTOQUE} em "
                f"{RELATORIOS_SUB}, nem as abas ftEstoquePMZ/ftEstoqueBap "
                f"da {ARQUIVO_TABELA}.")
    finally:
        wb.close()

    juntas = lido["juntas"]
    nomes = lido["nomes"]
    curtas = lido["curtas"]
    # o preco da TABELA_BAP manda; o do arquivo de estoque cobre o resto
    for chave, valor in (lido["precos"] or {}).items():
        precos.setdefault(chave, valor)

    so_com = bool(par.get("so_com_estoque", True))
    linhas = []
    for (filial, produto), reg in juntas.items():
        if so_com and reg["estoque"] <= 0:
            continue
        d_fil = ult_filial.get((filial, produto))
        d_ger = ult_geral.get(produto)
        dias_fil = (hoje - d_fil).days if d_fil else None
        dias_ger = (hoje - d_ger).days if d_ger else None
        preco = (precos.get((filial, produto))
                 or precos.get((curtas.get(filial, ""), produto)) or {})
        info = filiais.get(filial, {})
        linhas.append({
            "filial": filial,
            "regiao": info.get("regiao", "") or "(sem regiao)",
            "produto": produto,
            "descricao": nomes.get(produto, ""),
            **_classificacao(nomes.get(produto, "")),
            "estoque": reg["estoque"],
            "reserva": reg["reserva"],
            "pedido": reg["pedido"],
            "disponivel": reg["estoque"] - reg["reserva"] - reg["pedido"],
            "custo": reg["custo"],
            "origem_custo": reg.get("origem_custo", ""),
            "filial_cd": lido["cds"].get(filial, ""),
            "preco_capital": preco.get("capital", 0.0),
            "preco_interior": preco.get("interior", 0.0),
            "markup_capital": _markup(preco.get("capital"), reg["custo"]),
            "markup_interior": _markup(preco.get("interior"), reg["custo"]),
            "curva_filial": curva_de(dias_fil, par),
            "curva_geral": curva_de(dias_ger, par),
            "dias_sem_venda_filial": dias_fil,
            "dias_sem_venda_geral": dias_ger,
            "ultima_venda_filial": d_fil,
            "ultima_venda_geral": d_ger,
            "qtd_vendida_filial": qtd_filial.get((filial, produto), 0.0),
            "qtd_vendida_geral": qtd_geral.get(produto, 0.0),
        })
        ultima = linhas[-1]
        ultima["valor_estoque"] = ultima["estoque"] * (
            ultima["preco_capital"] or ultima["preco_interior"]
            or ultima["custo"])
        # A OPORTUNIDADE: gira na rede e esta parado AQUI. E a unica
        # combinacao que aponta acao clara - ha para quem vender.
        ultima["oportunidade"] = (
            ultima["curva_geral"] in ("A", "B")
            and ultima["curva_filial"] in ("C", "D", LETRA_PARADO)
            and ultima["estoque"] > 0)

    linhas.sort(key=lambda x: (-x["valor_estoque"], x["produto"]))
    return {
        "linhas": linhas,
        "hoje": hoje,
        "filiais": filiais,
        "arquivo": caminho_tabela,
        "fonte_estoque": lido["fonte"],
        "arquivo_estoque": arq_estoque,
        "extraido_em": lido["quando"],
        "aviso_estoque": aviso,
        "com_preco": sum(1 for l in linhas if l["preco_capital"]
                         or l["preco_interior"]),
        "oportunidades": sum(1 for l in linhas if l["oportunidade"]),
        "com_custo": sum(1 for l in linhas if l["custo"]),
        "cds": lido["cds"],
        "faturamento_filial": fat_filial,
        # tudo que a ftPedidos disse sobre giro - e daqui que o MIX tira a
        # venda por vendedor, a MEDIA SKU/MES e o VOLUME MEDIO/MES
        "giro": giro,
    }


# --------------------------------------------------------------------------
# o Excel do estoque
# --------------------------------------------------------------------------
COLUNAS_ESTOQUE = [
    ("REGIAO", "regiao", 18, None),
    ("COD FILIAL", "filial", 13, None),
    ("PRODUTO", "produto", 22, None),
    ("DESCRICAO", "descricao", 46, None),
    ("FAMILIA", "familia", 16, None),
    ("GRUPO", "grupo", 30, None),
    ("LINHA", "linha", 12, None),
    ("CURVA FILIAL", "curva_filial", 14, None),
    ("CURVA GERAL", "curva_geral", 14, None),
    ("OPORTUNIDADE", "oportunidade_txt", 15, None),
    ("ESTOQUE", "estoque", 11, "#,##0"),
    ("RESERVA", "reserva", 11, "#,##0"),
    ("EM PEDIDO", "pedido", 12, "#,##0"),
    ("DISPONIVEL", "disponivel", 13, "#,##0"),
    ("CUSTO (CD) R$", "custo", 16, "#,##0.00"),
    ("% MARKUP CAPITAL", "markup_capital", 17, "#,##0.00"),
    ("% MARKUP INTERIOR", "markup_interior", 18, "#,##0.00"),
    ("PRECO CAPITAL R$", "preco_capital", 18, "#,##0.00"),
    ("PRECO INTERIOR R$", "preco_interior", 19, "#,##0.00"),
    ("FILIAL CD", "filial_cd", 12, None),
    ("ORIGEM DO CUSTO", "origem_custo", 16, None),
    ("ESTOQUE EM R$", "valor_estoque", 16, "#,##0.00"),
    ("DIAS SEM VENDA (FILIAL)", "dias_sem_venda_filial", 24, None),
    ("DIAS SEM VENDA (GERAL)", "dias_sem_venda_geral", 23, None),
    ("ULTIMA VENDA NA FILIAL", "ultima_venda_filial", 23, "DD/MM/YYYY"),
    ("ULTIMA VENDA NA REDE", "ultima_venda_geral", 22, "DD/MM/YYYY"),
    ("VENDIDO NA FILIAL", "qtd_vendida_filial", 18, "#,##0"),
    ("VENDIDO NA REDE", "qtd_vendida_geral", 17, "#,##0"),
]


def nome_do_arquivo_de_estoque(hoje=None) -> str:
    hoje = hoje or dt.date.today()
    return f"OPORTUNIDADE_ESTOQUE_BAP_{hoje:%Y%m%d}.xlsx"


def gravar_excel_estoque(linhas: list, par: dict, caminho, hoje=None,
                         fonte: str = "", extraido_em: str = "") -> Path:
    """A lista do estoque mais a aba PARAMETROS, dizendo de onde ela veio."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    caminho = Path(caminho)
    hoje = hoje or dt.date.today()
    wb = Workbook()
    ws = wb.active
    ws.title = "ESTOQUE"
    ws.append([t for t, _, _, _ in COLUNAS_ESTOQUE])
    cabecalho = PatternFill("solid", fgColor="14375E")
    branco = Font(color="FFFFFF", bold=True, size=9)
    for i, (_, _, largura, _) in enumerate(COLUNAS_ESTOQUE, start=1):
        ws.cell(1, i).fill = cabecalho
        ws.cell(1, i).font = branco
        ws.cell(1, i).alignment = Alignment(horizontal="center",
                                            wrap_text=True)
        ws.column_dimensions[ws.cell(1, i).column_letter].width = largura
    for linha in linhas:
        copia = dict(linha)
        copia["oportunidade_txt"] = "SIM" if linha.get("oportunidade") else ""
        ws.append([copia.get(k) for _, k, _, _ in COLUNAS_ESTOQUE])
    for j, (_, _, _, formato) in enumerate(COLUNAS_ESTOQUE, start=1):
        if formato:
            for n in range(2, ws.max_row + 1):
                ws.cell(n, j).number_format = formato
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = (f"A1:{ws.cell(1, len(COLUNAS_ESTOQUE)).column_letter}"
                              f"{ws.max_row}")

    wp = wb.create_sheet("PARAMETROS")
    wp["A1"] = "De onde vem cada numero desta lista"
    wp["A1"].font = Font(bold=True, size=12, color="1F4E79")
    regras = [("Data de referencia da curva", hoje.strftime("%d/%m/%Y")),
              ("Estoque",
               (fonte or f"{RELATORIOS_SUB}\\{ARQUIVO_ESTOQUE}")
               + (f" - foto de {extraido_em}" if extraido_em else "")),
              ("Preco", "ftTabelaPreco da TABELA_BAP (DA1_PRCVEN)"),
              ("Regiao", "aba Filiais da TABELA_BAP (coluna CIDADE)"),
              ("Ultima venda", "ftPedidos, so TIPO VND/VEA"),
              ("Tabela de CAPITAL",
               f"a que termina em {par.get('sufixo_capital')}"),
              ("Tabela de INTERIOR",
               f"a que termina em {par.get('sufixo_interior')}"),
              ("CURVA FILIAL", "pela ultima venda DAQUELA filial"),
              ("CURVA GERAL", "pela ultima venda em QUALQUER filial"),
              ("OPORTUNIDADE",
               "curva A ou B na rede e C, D ou Z na filial, com estoque")]
    regras += [(f"CURVA {letra}", f"{faixa} - {texto}")
               for letra, faixa, texto in texto_das_curvas(par)]
    for i, (a, b) in enumerate(regras, start=3):
        wp.cell(i, 1, a).font = Font(bold=True, size=10)
        wp.cell(i, 2, b).font = Font(size=10)
    wp.column_dimensions["A"].width = 28
    wp.column_dimensions["B"].width = 64

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


# ==========================================================================
# MIX DISPONIVEL x MIX POSITIVADO
# ==========================================================================
# A pergunta e curta: DO QUE EU TENHO NA PRATELEIRA, QUANTO EU CONSIGO
# VENDER? O numerador e o mix POSITIVADO (SKUs diferentes que sairam na
# janela) e o denominador e o mix DISPONIVEL (SKUs diferentes que tem
# estoque). A divisao dos dois e o % MIX.
#
# O que conta e SKU DIFERENTE, nao unidade: um produto vendido 300 vezes
# conta 1, igual a um vendido uma vez so. E o mix, nao o volume.
#
# UM CUIDADO NA LEITURA: no recorte da CIDADE o produto so e positivado
# se ele saiu ALI (a ultima venda da filial). No BAP GERAL vale a ultima
# venda da REDE. Por isso o geral nao e a soma das cidades - um item que
# gira em Manaus e esta parado em Belem entra positivado no geral e
# parado em Belem. E essa diferenca, justamente, que aponta a acao.
# ==========================================================================
JANELAS_DO_MIX = [30, 60, 90, 180, 365]
JANELA_DO_MIX_PADRAO = 90
MESES_DA_MEDIA = 12
ROTULO_MIX_TOTAL = "(todas as categorias)"
ROTULO_SEM_CATEGORIA = "(sem categoria)"
ROTULO_SEM_VENDEDOR = "(sem vendedor)"

# OS QUATRO NIVEIS do mix. A chave e o que vai no titulo da primeira
# coluna; o resto da tabela e igual em todos.
NIVEIS_DO_MIX = [("bap", "BAP"), ("uf", "UF"), ("cidade", "CIDADE"),
                 ("vendedor", "VENDEDOR")]

# O polo da filial nao diz a UF, e a aba Filiais nao tem coluna de
# estado. Sao sete polos e eles nao mudam - entao a lista e esta, com a
# tabela de cidades da geografia como rede de seguranca.
UF_DA_REGIAO = {
    "MANAUS": "AM", "BOA VISTA": "RR", "MACAPA": "AP", "BELEM": "PA",
    "SANTAREM": "PA", "PARAUAPEBAS": "PA", "SAO LUIS": "MA",
    "IMPERATRIZ": "MA", "MATOGROSSO": "MT", "MATO GROSSO": "MT",
    "CUIABA": "MT", "RORAIMA": "RR", "AMAPA": "AP",
}


def uf_da_regiao(regiao: str) -> str:
    """A UF do polo da filial. Sem saber, devolve a propria regiao."""
    chave = _sem_acento(_texto(regiao)).upper().strip()
    if chave in UF_DA_REGIAO:
        return UF_DA_REGIAO[chave]
    try:
        from geografia import CIDADES
        for uf, cidade in CIDADES:
            if _sem_acento(cidade).upper() == chave:
                return uf
    except ImportError:
        pass
    return regiao or "(sem UF)"


def rotulo_da_categoria(chave: str) -> str:
    """A etiqueta de tela da categoria do kit."""
    for c, rotulo in CATEGORIAS_KIT:
        if c == chave:
            return rotulo
    return ROTULO_SEM_CATEGORIA


def _linha_de_mix(nome: str, categoria: str, quebra=False) -> dict:
    """
    `quebra` diz se a linha E de uma categoria. Sem quebra, a linha junta
    tudo e o rotulo e "(todas as categorias)"; com quebra e sem categoria
    no CSV, ela e "(sem categoria)" - que e coisa bem diferente.
    """
    return {"nome": nome, "categoria": categoria,
            "rotulo": (rotulo_da_categoria(categoria) if quebra
                       else ROTULO_MIX_TOTAL),
            "_disp": set(), "_posit": set(), "_filiais": set(),
            "curva": defaultdict(set),
            "estoque": 0.0, "valor_estoque": 0.0, "valor_parado": 0.0}


def _somar_no_mix(alvo: dict, linha: dict, produto: str, positivado: bool,
                  quantidade: float, curva: str = "") -> None:
    alvo["_disp"].add(produto)
    if positivado:
        alvo["_posit"].add(produto)
    else:
        alvo["valor_parado"] += linha.get("valor_estoque") or 0.0
    if curva:
        alvo["curva"][curva].add(produto)
    alvo["_filiais"].add(linha.get("filial", ""))
    alvo["estoque"] += quantidade
    alvo["valor_estoque"] += linha.get("valor_estoque") or 0.0


def _media_do_escopo(giro: dict, escopo, produtos, meses=MESES_DA_MEDIA):
    """
    MEDIA SKU/MES e VOLUME MEDIO/MES nos ultimos 12 meses, para um escopo
    (a rede, uma filial, um vendedor) e um conjunto de produtos.

    A media de SKU e a media dos DOZE meses, nao dos meses em que houve
    venda: mes parado e parte da historia. E ela conta SKU DIFERENTE
    dentro de cada mes - por isso o mapa de bits, um bit por mes.
    """
    janela = (giro or {}).get("janela", {}).get(escopo) or {}
    volume = (giro or {}).get("volume", {}).get(escopo) or {}
    if not janela and not volume:
        return 0.0, 0.0
    contagem = [0] * meses
    total = 0.0
    for produto in produtos:
        mascara = janela.get(produto)
        if mascara:
            for b in range(meses):
                if mascara & (1 << b):
                    contagem[b] += 1
        total += volume.get(produto, 0.0)
    return round(sum(contagem) / meses, 1), round(total / meses, 0)


def _fechar_mix(alvo: dict, giro=None, escopo=None) -> dict:
    disp = len(alvo["_disp"])
    posit = len(alvo["_posit"] & alvo["_disp"])
    alvo["skus_disponiveis"] = disp
    alvo["skus_positivados"] = posit
    alvo["skus_sem_giro"] = disp - posit
    alvo["pct_mix"] = round(posit / disp * 100.0, 1) if disp else 0.0
    alvo["qtd_filiais"] = len(alvo["_filiais"] - {""})
    for letra in ORDEM_DAS_CURVAS:
        alvo[f"curva_{letra}"] = len(alvo["curva"].get(letra) or ())
    alvo["estoque"] = round(alvo["estoque"], 0)
    alvo["valor_estoque"] = round(alvo["valor_estoque"], 2)
    alvo["valor_parado"] = round(alvo["valor_parado"], 2)
    # a media olha o que a linha VENDE, nao so o que esta na prateleira:
    # produto que saiu e acabou continua contando no giro do mes dele
    escopo = escopo or ("geral",)
    produtos = set((giro or {}).get("janela", {}).get(escopo) or ())
    if alvo["categoria"] or alvo["rotulo"] != ROTULO_MIX_TOTAL:
        produtos &= alvo["_produtos_da_categoria"]
    alvo["media_sku_mes"], alvo["volume_medio_mes"] = _media_do_escopo(
        giro, escopo, produtos)
    alvo.pop("_produtos_da_categoria", None)
    return alvo


def montar_mix(estoque: dict, categorias: dict = None,
               janela: int = JANELA_DO_MIX_PADRAO,
               usar_disponivel: bool = False,
               nomes_de_vendedor: dict = None,
               familia: str = "", grupo: str = "", linha_bap: str = "") -> dict:
    """
    O mix disponivel x positivado em quatro niveis - a BAP inteira, a UF,
    a CIDADE (o polo da filial) e o VENDEDOR - e cada um deles com ou sem
    a quebra por CATEGORIA.

      janela ........... quantos dias para tras contam como VENDIDO
      usar_disponivel .. True olha o DISPONIVEL (estoque menos reserva e
                         pedido); False, o estoque fisico da prateleira

    O VENDEDOR e um caso a parte: o estoque dele e o da FILIAL ONDE ELE
    MAIS VENDE (dois vendedores da mesma filial mostram o mesmo estoque,
    de proposito - a prateleira e uma so), e o POSITIVADO e o que ELE
    vendeu, nao o que a filial vendeu. E a leitura certa: o denominador
    e a prateleira que ele tem para oferecer.
    """
    categorias = categorias or {}
    nomes_de_vendedor = nomes_de_vendedor or {}
    janela = max(1, int(janela or JANELA_DO_MIX_PADRAO))
    linhas = list((estoque or {}).get("linhas") or [])
    # FAMILIA / GRUPO / LINHA enxugam a PRATELEIRA antes da conta: o
    # denominador passa a ser so aquele pedaco do estoque, e o % MIX
    # responde "do freio que tenho, quanto consigo vender".
    if familia:
        linhas = [l for l in linhas if l.get("familia") == familia]
    if grupo:
        linhas = [l for l in linhas if l.get("grupo") == grupo]
    if linha_bap:
        linhas = [l for l in linhas if l.get("linha") == linha_bap]
    giro = (estoque or {}).get("giro") or {}
    ultima_vend = giro.get("ultima_vend") or {}
    filial_do_vend = giro.get("filial_do_vendedor") or {}
    hoje = (estoque or {}).get("hoje") or dt.date.today()

    # os produtos de cada categoria, para a media por categoria
    da_categoria = defaultdict(set)
    for produto, cat in categorias.items():
        da_categoria[cat].add(produto)

    # quem vende em cada filial
    vend_da_filial = defaultdict(list)
    for cod, fil in filial_do_vend.items():
        vend_da_filial[fil].append(cod)

    blocos = {}       # (nivel, nome, categoria) -> linha
    escopos = {}      # (nivel, nome) -> escopo do giro

    def _entrar(nivel, nome, escopo, l, produto, positivado, qtd, curva,
                cat):
        escopos[(nivel, nome)] = escopo
        for quebra, chave_cat in ((False, ""), (True, cat)):
            chave = (nivel, quebra, nome, chave_cat if quebra else "")
            alvo = blocos.get(chave)
            if alvo is None:
                alvo = blocos[chave] = _linha_de_mix(
                    nome, chave_cat if quebra else "", quebra)
                alvo["_escopo"] = escopo
                alvo["_nivel"] = nivel
                alvo["_produtos_da_categoria"] = (da_categoria.get(chave_cat)
                                                  or set()) if quebra else set()
            _somar_no_mix(alvo, l, produto, positivado, qtd, curva)

    for l in linhas:
        qtd = (l.get("disponivel") if usar_disponivel
               else l.get("estoque")) or 0.0
        if qtd <= 0:
            continue
        produto = l.get("produto") or ""
        if not produto:
            continue
        filial = l.get("filial") or ""
        cidade = l.get("regiao") or "(sem regiao)"
        uf = uf_da_regiao(cidade)
        cat = categorias.get(produto, "")
        dias_fil = l.get("dias_sem_venda_filial")
        dias_ger = l.get("dias_sem_venda_geral")
        # NA FILIAL vale a venda DALI; no BAP, a venda da rede
        aqui = dias_fil is not None and dias_fil <= janela
        rede = dias_ger is not None and dias_ger <= janela
        c_fil = l.get("curva_filial") or ""
        c_ger = l.get("curva_geral") or ""

        _entrar("bap", "BAP", ("geral",), l, produto, rede, qtd, c_ger, cat)
        _entrar("uf", uf, ("filial", filial), l, produto, aqui, qtd, c_fil,
                cat)
        _entrar("cidade", cidade, ("filial", filial), l, produto, aqui, qtd,
                c_fil, cat)
        for cod in vend_da_filial.get(filial, ()):
            d = ultima_vend.get((cod, produto))
            dele = d is not None and (hoje - d).days <= janela
            nome = nomes_de_vendedor.get(cod)
            _entrar("vendedor", f"{cod} - {nome}" if nome else cod,
                    ("vendedor", cod), l, produto, dele, qtd, c_fil, cat)

    # A UF junta varias filiais: o escopo do giro dela nao e uma filial so
    escopo_da_uf = defaultdict(set)
    for l in linhas:
        escopo_da_uf[uf_da_regiao(l.get("regiao") or "")].add(
            l.get("filial") or "")

    saida = {}
    for (nivel, quebra, nome, cat), alvo in blocos.items():
        escopo = alvo.pop("_escopo")
        alvo.pop("_nivel", None)
        if nivel == "uf":
            # soma os mapas de bits das filiais da UF, produto a produto
            escopo = ("uf", nome)
            if escopo not in (giro.get("janela") or {}):
                giro.setdefault("janela", {})[escopo] = _juntar_janelas(
                    giro, [("filial", f) for f in escopo_da_uf.get(nome, ())])
                giro.setdefault("volume", {})[escopo] = _juntar_volumes(
                    giro, [("filial", f) for f in escopo_da_uf.get(nome, ())])
        saida.setdefault((nivel, quebra), []).append(
            _fechar_mix(alvo, giro, escopo))

    def _ordenar(linhas_):
        return sorted(linhas_, key=lambda x: (x["nome"],
                                              -x["skus_disponiveis"]))

    recortes = {f"{nivel}{'_cat' if quebra else ''}": _ordenar(v)
                for (nivel, quebra), v in saida.items()}
    geral = recortes.get("bap") or [_fechar_mix(_linha_de_mix("BAP", ""),
                                                giro, ("geral",))]
    return {
        "janela": janela,
        "usar_disponivel": bool(usar_disponivel),
        "hoje": hoje,
        "familia": familia,
        "grupo": grupo,
        "linha_bap": linha_bap,
        "com_categoria": bool(categorias),
        "meses_da_media": MESES_DA_MEDIA,
        "geral": geral[0],
        "vendedores": sorted(filial_do_vend),
        "filial_do_vendedor": dict(filial_do_vend),
        **recortes,
    }


def _juntar_janelas(giro, escopos) -> dict:
    saida = defaultdict(int)
    for e in escopos:
        for produto, mascara in ((giro.get("janela") or {}).get(e)
                                 or {}).items():
            saida[produto] |= mascara
    return dict(saida)


def _juntar_volumes(giro, escopos) -> dict:
    saida = defaultdict(float)
    for e in escopos:
        for produto, qtd in ((giro.get("volume") or {}).get(e)
                             or {}).items():
            saida[produto] += qtd
    return dict(saida)


def recorte_do_mix(nivel: str, por_categoria: bool) -> str:
    """A chave do recorte dentro do que montar_mix devolveu."""
    return f"{nivel}{'_cat' if por_categoria else ''}"


def linhas_do_mix(mix: dict, nivel: str, por_categoria=False) -> list:
    """As linhas de um recorte."""
    return list((mix or {}).get(recorte_do_mix(nivel, por_categoria)) or [])


COLUNAS_MIX = [
    ("RECORTE", "nome", 22, None),
    ("CATEGORIA", "rotulo", 24, None),
    ("SKUS DISPONIVEIS", "skus_disponiveis", 18, "#,##0"),
    ("SKUS POSITIVADOS", "skus_positivados", 18, "#,##0"),
    ("% MIX", "pct_mix", 10, "#,##0.0"),
    ("SKUS SEM GIRO", "skus_sem_giro", 16, "#,##0"),
    ("CURVA A", "curva_A", 10, "#,##0"),
    ("CURVA B", "curva_B", 10, "#,##0"),
    ("CURVA C", "curva_C", 10, "#,##0"),
    ("CURVA D", "curva_D", 10, "#,##0"),
    ("CURVA Z", "curva_Z", 10, "#,##0"),
    ("MEDIA SKU/MES (12M)", "media_sku_mes", 20, "#,##0.0"),
    ("VOLUME MEDIO/MES", "volume_medio_mes", 19, "#,##0"),
    ("ESTOQUE (UN)", "estoque", 14, "#,##0"),
    ("ESTOQUE EM R$", "valor_estoque", 17, "#,##0.00"),
    ("R$ PARADO (SEM GIRO)", "valor_parado", 22, "#,##0.00"),
]


def nome_do_arquivo_de_mix(hoje=None) -> str:
    hoje = hoje or dt.date.today()
    return f"MIX_DE_PRODUTOS_BAP_{hoje:%Y%m%d}.xlsx"


def gravar_excel_mix(mix: dict, caminho, hoje=None) -> Path:
    """Uma aba por recorte: BAP, CATEGORIA, CIDADE e CIDADE x CATEGORIA."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    caminho = Path(caminho)
    hoje = hoje or (mix or {}).get("hoje") or dt.date.today()
    wb = Workbook()
    fundo = PatternFill("solid", fgColor="1F3864")

    def _folha(ws, linhas, titulo):
        ws["A1"] = titulo
        ws["A1"].font = Font(bold=True, size=13, color="1F3864")
        ws["A2"] = (f"janela de {mix['janela']} dias  |  mix positivado = "
                    f"SKUs vendidos / SKUs com estoque  |  apurado em "
                    f"{hoje:%d/%m/%Y}")
        ws["A2"].font = Font(size=10, italic=True)
        for i, (titulo_col, _, larg, _f) in enumerate(COLUNAS_MIX, start=1):
            cel = ws.cell(3, i, titulo_col)
            cel.font = Font(bold=True, color="FFFFFF", size=10)
            cel.fill = fundo
            cel.alignment = Alignment(horizontal="center", vertical="center",
                                      wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = larg
        ws.row_dimensions[3].height = 30
        ws.freeze_panes = "A4"
        for l in linhas:
            ws.append([l.get(chave) for _, chave, _, _ in COLUNAS_MIX])
        for linha in range(4, ws.max_row + 1):
            for col, (_, _, _, fmt) in enumerate(COLUNAS_MIX, start=1):
                cel = ws.cell(linha, col)
                cel.font = Font(size=9)
                if fmt:
                    cel.number_format = fmt
        if ws.max_row > 3:
            ws.auto_filter.ref = (f"A3:{get_column_letter(len(COLUNAS_MIX))}"
                                  f"{ws.max_row}")

    ws = wb.active
    ws.title = "BAP"
    _folha(ws, linhas_do_mix(mix, "bap"), "MIX DE PRODUTOS - BAP INTEIRA")
    _folha(wb.create_sheet("BAP_CATEGORIA"), linhas_do_mix(mix, "bap", True),
           "MIX DE PRODUTOS - BAP x CATEGORIA")
    _folha(wb.create_sheet("POR_UF"), linhas_do_mix(mix, "uf"),
           "MIX DE PRODUTOS - POR UF")
    _folha(wb.create_sheet("UF_CATEGORIA"), linhas_do_mix(mix, "uf", True),
           "MIX DE PRODUTOS - UF x CATEGORIA")
    _folha(wb.create_sheet("POR_CIDADE"), linhas_do_mix(mix, "cidade"),
           "MIX DE PRODUTOS - POR CIDADE")
    _folha(wb.create_sheet("CIDADE_CATEGORIA"),
           linhas_do_mix(mix, "cidade", True),
           "MIX DE PRODUTOS - CIDADE x CATEGORIA")
    _folha(wb.create_sheet("POR_VENDEDOR"), linhas_do_mix(mix, "vendedor"),
           "MIX DE PRODUTOS - POR VENDEDOR")
    _folha(wb.create_sheet("VENDEDOR_CATEGORIA"),
           linhas_do_mix(mix, "vendedor", True),
           "MIX DE PRODUTOS - VENDEDOR x CATEGORIA")

    wl = wb.create_sheet("COMO_LER")
    regras = [
        ("MIX DISPONIVEL", "quantos SKUs DIFERENTES tem estoque no recorte. "
                           "Conta produto, nao unidade."),
        ("MIX POSITIVADO", f"quantos desses SKUs foram vendidos nos ultimos "
                           f"{mix['janela']} dias."),
        ("% MIX", "positivado dividido por disponivel, vezes 100."),
        ("SKUS SEM GIRO", "os que estao na prateleira e nao sairam na janela."),
        ("CURVA A a Z", "quantos SKUs do recorte estao em cada curva de "
                        "giro. No BAP vale a curva GERAL; nos outros "
                        "niveis, a curva DAQUELA FILIAL."),
        ("MEDIA SKU/MES", f"quantos SKUs DIFERENTES o recorte vendeu por "
                          f"mes, na media dos ultimos "
                          f"{mix.get('meses_da_media', 12)} meses. E a "
                          f"media dos doze meses, nao so dos meses com "
                          f"venda: mes parado e parte da historia."),
        ("VOLUME MEDIO/MES", "as unidades vendidas nos ultimos 12 meses "
                             "divididas por 12."),
        ("FILIAL x BAP", "na UF, na CIDADE e no VENDEDOR so conta a venda "
                         "DALI; no BAP vale a venda da rede. Por isso o "
                         "geral nao e a soma das cidades - e essa "
                         "diferenca que aponta a acao."),
        ("VENDEDOR", "o estoque dele e o da FILIAL ONDE ELE MAIS VENDE - "
                     "dois vendedores da mesma filial mostram o mesmo "
                     "estoque, de proposito: a prateleira e uma so. O "
                     "POSITIVADO, esse sim, e o que ELE vendeu."),
        ("ESTOQUE", "fisico da prateleira" if not mix.get("usar_disponivel")
         else "o DISPONIVEL: estoque menos reserva e menos o que ja esta "
              "em pedido"),
    ]
    for i, (a, b) in enumerate(regras, start=1):
        wl.cell(i, 1, a).font = Font(bold=True, size=10)
        wl.cell(i, 2, b).font = Font(size=10)
    wl.column_dimensions["A"].width = 24
    wl.column_dimensions["B"].width = 78

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


# ==========================================================================
# SUGESTAO DE KITS
# ==========================================================================
# Um kit e uma cesta fechada, por FILIAL e por CATEGORIA, montada com o
# que ESTA na prateleira daquela filial. A ideia e simples de dizer e
# chata de acertar: o diretor comercial aprova UMA vez a cesta e o
# desconto, e o vendedor sai vendendo a mesma cesta a semana inteira.
#
# A REGRA DE MONTAGEM
#   Os parametros dizem quantos SKUs de cada curva entram e quantas
#   unidades de cada um. O motor percorre as curvas na ordem A, B, C, D,
#   Z e vai preenchendo.
#
#   SE FALTAR PRODUTO NUMA CURVA, O QUE SOBROU DA COTA PASSA PARA A
#   PROXIMA. Bater a quantidade do kit vale mais que respeitar a cota:
#   um kit com 8 itens quando foram pedidos 10 nao e um kit, e um kit
#   pela metade. O DE ONDE VEIO de cada linha diz se ela entrou na cota
#   dela ou herdou a vaga de uma curva que nao tinha produto.
#
#   O LIMITE DE VALOR corta por cima: se a proxima linha estourasse o
#   teto do kit, ela nao entra.
#
# O DESCONTO
#   E por CURVA, nao por produto: curva Z pode levar desconto maior -
#   afinal e o que esta parado - e curva A, menos. Quem escolhe e voce,
#   nos parametros.
CATEGORIAS_KIT = [
    ("pecas_leve", "PECAS - LINHA LEVE"),
    ("pecas_pesada", "PECAS - LINHA PESADA"),
    ("pecas_moto", "PECAS - MOTO"),
    ("lubrificante", "LUBRIFICANTES"),
    ("bateria", "BATERIAS"),
    ("pneu", "PNEUS"),
]

# O que o arquivo de estoque escreve -> a categoria do kit. O mesmo
# produto pode vir escrito no singular ou no plural, com ou sem acento,
# com hifen ou sem - entao a comparacao e feita com o nome ja limpo, e
# OLEO e LUBRIFICANTE sao a MESMA COISA (no sistema, o oleo E o
# lubrificante; separar as duas so criava uma categoria vazia).
CATEGORIA_DO_CSV = {
    "PECAS LINHA LEVE": "pecas_leve",
    "PECA LINHA LEVE": "pecas_leve",
    "LINHA LEVE": "pecas_leve",
    "PECAS LINHA PESADA": "pecas_pesada",
    "PECA LINHA PESADA": "pecas_pesada",
    "LINHA PESADA": "pecas_pesada",
    "PECAS MOTO": "pecas_moto",
    "PECA MOTO": "pecas_moto",
    "MOTO": "pecas_moto",
    "MOTOPECAS": "pecas_moto",
    "LUBRIFICANTES": "lubrificante",
    "LUBRIFICANTE": "lubrificante",
    "OLEOS": "lubrificante",
    "OLEO": "lubrificante",
    "BATERIAS": "bateria",
    "BATERIA": "bateria",
    "PNEUS": "pneu",
    "PNEU": "pneu",
    # o que vier so como "PECAS", sem dizer a linha, entra na leve
    "PECAS": "pecas_leve",
    "PECA": "pecas_leve",
}

ORDEM_DAS_CURVAS = ["A", "B", "C", "D", LETRA_PARADO]

KIT_PADRAO = {
    "itens_no_kit": 10,          # quantos SKUs diferentes o kit tem
    "estoque_minimo": 5.0,       # so entra produto com pelo menos isso
    # AS FILIAIS QUE ENTRAM NA ACAO: {codigo da filial: True/False}.
    # Vazio ou tudo marcado = a rede inteira. Filial desmarcada nao
    # monta kit nenhum, de categoria nenhuma.
    "filiais": {},
    # a tabela de sucata da bateria, por amperagem (ver SUCATA_DE_BATERIA)
    "sucata": [],
    "sucata_ss": [],
    # so para a tela: {codigo: nome} da ultima vez que o estoque foi
    # lido, para a lista de filiais aparecer antes de abrir Excel
    "filiais_nomes": {},
    "usar_curva": "filial",      # "filial" ou "geral"
    "preco_base": "capital",     # que tabela de preco o kit usa
    # por curva: quantos SKUs entram e quantas unidades de cada um.
    #   desc_gerente .. o desconto que o GERENTE da em cima do preco de
    #                   tabela. Ele sai do preco ANTES de o kit ser
    #                   montado e nao aparece em coluna nenhuma: o que a
    #                   tela chama de VLR. UNIT. TABELA ja vem sem ele
    #   desconto ...... o desconto da ACAO, em cima desse preco. E ele,
    #                   inteiro, que a verba paga
    #   markup_min .... a TRAVA: nenhum item sai do kit com markup
    #                   abaixo disso, doa a quem doer no desconto
    "cotas": {
        "A": {"skus": 3, "qtd": 2, "desc_gerente": 15.0, "desconto": 5.0,
              "markup_min": 15.0},
        "B": {"skus": 3, "qtd": 2, "desc_gerente": 15.0, "desconto": 8.0,
              "markup_min": 15.0},
        "C": {"skus": 2, "qtd": 3, "desc_gerente": 15.0, "desconto": 12.0,
              "markup_min": 15.0},
        "D": {"skus": 1, "qtd": 3, "desc_gerente": 15.0, "desconto": 18.0,
              "markup_min": 15.0},
        "Z": {"skus": 1, "qtd": 4, "desc_gerente": 15.0, "desconto": 25.0,
              "markup_min": 15.0},
    },
    # quanto a BAP topa investir em cada categoria - e dai que sai
    # quantos kits podem ser vendidos
    "investimento": {"pecas_leve": 100000.0, "pecas_pesada": 40000.0,
                     "pecas_moto": 40000.0, "lubrificante": 50000.0,
                     "bateria": 80000.0, "pneu": 20000.0},
    # a verba acima e da REDE INTEIRA (True) ou vale PARA CADA FILIAL
    # (False)? Muda quantos kits cada filial pode por na rua.
    "verba_geral": {c: True for c, _ in CATEGORIAS_KIT},
    # que categorias entram nesta rodada. A desmarcada nao gera kit.
    "gerar": {c: True for c, _ in CATEGORIAS_KIT},
    # quebrar as PECAS por familia (AMORTECEDOR, FILTRO, JOGO PASTILHA...)
    # em vez de um kit unico de peças
    "por_familia": False,
    # O PESO DE CADA FILIAL NA VERBA, em %. Vazio = calcular pelo
    # faturamento dos ultimos 12 meses, com piso de 10% (ver
    # pesos_das_filiais). Preenchido, manda o que esta aqui.
    "peso_filial": {},
    "piso_da_filial": PISO_DA_FILIAL,
    # LUBRIFICANTE NAO SE VENDE SOLTO: sai em caixa fechada, e a caixa
    # muda de tamanho conforme o produto. Ver CAIXAS_DE_LUBRIFICANTE.
    "caixa_lubrificante": True,
    "caixas": None,          # preenchido com caixas_padrao() no primeiro uso
}

# ---------------------------------------------------------------------------
# A CAIXA DO LUBRIFICANTE
#
# Oleo nao sai unidade a unidade: sai caixa fechada, e cada familia tem o
# seu tamanho. Um kit que peca 2 unidades de um DOT4 esta pedindo algo que
# nao existe - o minimo ali e uma caixa de 24.
#
# A regra e lida DE CIMA PARA BAIXO: a primeira que casar com a descricao
# manda. Por isso o fluido de freio vem antes do oleo - "OLEO FLUIDO FREIO
# DOT 4" casaria com as duas.
#
# Quem nao casa com nenhuma (balde de 20L, tambor de 200L, galao de 5L)
# vende avulso, unidade a unidade, como todo o resto.
# ---------------------------------------------------------------------------
CAIXAS_DE_LUBRIFICANTE = [
    {"nome": "Fluido de freio (DOT 3 e DOT 4)", "unidades": 24,
     "palavras": ["DOT 3", "DOT3", "DOT 4", "DOT4"]},
    {"nome": "Oleo de 1 litro (10W, 5W, 20W50...)", "unidades": 24,
     "palavras": ["LITRO OLEO"]},
    {"nome": "Aditivo de 1 litro e agua", "unidades": 12,
     "palavras": ["LITRO ADITIVO", "LITRO FLUIDO", "LITRO AGUA",
                  "ADITIVO FLUIDO", "FLUIDO ADITIVO"]},
]
# o que nao casa com regra nenhuma sai de um em um
CAIXA_AVULSA = 1
# palavras que dizem "isto ja e uma embalagem grande": balde, tambor,
# galao. Nunca entram em caixa, seja qual for a palavra que venha antes.
FORA_DA_CAIXA = ["BALDE", "TAMBOR", "GALAO", "CX", "CAIXA", " 5 LITROS",
                 " 05 LITROS", " 20 LITROS", " 200 L", " 1.000L"]


def caixas_padrao() -> list:
    return json.loads(json.dumps(CAIXAS_DE_LUBRIFICANTE))


def caixa_do_produto(descricao, kit: dict = None) -> tuple:
    """
    Quantas unidades vem na caixa daquele produto, e de que grupo ele e.
    Devolve (unidades, nome do grupo). Sem grupo, (1, "").
    """
    texto = limpar(descricao)
    if not texto:
        return CAIXA_AVULSA, ""
    for marca in FORA_DA_CAIXA:
        if marca.strip() and marca in texto:
            return CAIXA_AVULSA, ""
    regras = ((kit or {}).get("caixas") or CAIXAS_DE_LUBRIFICANTE)
    for regra in regras:
        for palavra in (regra.get("palavras") or []):
            if limpar(palavra) and limpar(palavra) in texto:
                return (max(1, int(_numero(regra.get("unidades")) or 1)),
                        _texto(regra.get("nome")))
    return CAIXA_AVULSA, ""


# A SUCATA DA BATERIA. Para comprar bateria da fabrica e preciso
# entregar a sucata junto - entao o custo de verdade de uma bateria e o
# P. PEDIDO do CD MAIS o que a sucata vale. Sem isso o markup da bateria
# sai inflado e o combo fica desequilibrado contra as outras categorias.
#
# A faixa e por AMPERAGEM, lida da descricao do produto ("( 60AMP )",
# "60 AMPERES"...). "ate" e o teto da faixa em amperes.
SUCATA_DE_BATERIA = [
    {"ate": 40, "valor": 35.0},        # 32A/40A
    {"ate": 50, "valor": 47.0},        # 45A/50A
    {"ate": 60, "valor": 62.0},        # 55A/60A
    {"ate": 75, "valor": 69.0},        # 65A/75A
    {"ate": 90, "valor": 86.0},        # 80A/90A
    {"ate": 100, "valor": 105.0},      # 95A/100A
    {"ate": 115, "valor": 124.0},      # 105A/115A
    {"ate": 135, "valor": 145.0},      # 135A
    {"ate": 180, "valor": 182.0},      # 150A/170A/180A
    {"ate": 9999, "valor": 229.0},     # 200A e acima
]

# A bateria START STOP tem a sua propria tabela, mais cara
SUCATA_START_STOP = [
    {"ate": 60, "valor": 70.0},        # 50A/60A
    {"ate": 72, "valor": 81.0},        # 70A/72A
    {"ate": 92, "valor": 91.0},        # 80A/92A
    {"ate": 95, "valor": 105.0},       # 95A
    {"ate": 9999, "valor": 123.0},     # 105A e acima
]

# como a descricao avisa que a bateria e start stop
PALAVRAS_START_STOP = ["EFB", "AGM", "START STOP", "STARTSTOP", "START-STOP"]


def sucata_padrao() -> list:
    return json.loads(json.dumps(SUCATA_DE_BATERIA))


def sucata_ss_padrao() -> list:
    return json.loads(json.dumps(SUCATA_START_STOP))


def amperagem_do_produto(descricao) -> int:
    """
    Os amperes que a descricao anuncia. Ela costuma dizer duas vezes -
    "BATERIA 60 AMPERES MXBF60D - 12 MESES ( 60AMP )" - e as duas
    grafias valem. Sem nada disso, devolve 0.
    """
    texto = limpar(descricao)
    if not texto:
        return 0
    achados = re.findall(r"(\d{2,3})\s*(?:AMPERES|AMPERE|AMP\b|A\b)", texto)
    if not achados:
        achados = re.findall(r"\(\s*(\d{2,3})\s*AMP", texto)
    for bruto in achados:
        n = int(bruto)
        if 20 <= n <= 300:            # fora disso nao e amperagem
            return n
    return 0


def e_start_stop(descricao) -> bool:
    texto = limpar(descricao)
    return any(limpar(p) in texto for p in PALAVRAS_START_STOP)


def valor_da_sucata(descricao, kit: dict = None) -> float:
    """
    Quanto vale a sucata daquela bateria, pela tabela da aba 5. Zero
    quando a descricao nao diz a amperagem - melhor nao inventar custo.
    """
    amp = amperagem_do_produto(descricao)
    if amp <= 0:
        return 0.0
    kit = kit or {}
    if e_start_stop(descricao):
        faixas = kit.get("sucata_ss") or SUCATA_START_STOP
    else:
        faixas = kit.get("sucata") or SUCATA_DE_BATERIA
    for faixa in sorted(faixas, key=lambda f: _numero(f.get("ate"))):
        if amp <= _numero(faixa.get("ate")):
            return float(_numero(faixa.get("valor")))
    return float(_numero((faixas or [{}])[-1].get("valor")))


def kit_padrao() -> dict:
    p = json.loads(json.dumps(KIT_PADRAO))
    p["caixas"] = caixas_padrao()
    return p


def ler_categoria_dos_produtos(caminho_csv) -> dict:
    """{codigo do produto -> categoria do kit}, do CATEGORIAS_PRODUTO.csv."""
    caminho_csv = Path(caminho_csv) if caminho_csv else None
    if not caminho_csv or not caminho_csv.exists():
        return {}
    import csv as _csv
    saida = {}
    try:
        with open(caminho_csv, encoding="utf-8-sig", newline="") as f:
            amostra = f.read(4096)
            f.seek(0)
            sep = ";" if amostra.count(";") > amostra.count(",") else ","
            for linha in _csv.DictReader(f, delimiter=sep):
                limpo = {limpar(k).replace(".", ""): v
                         for k, v in linha.items() if k}
                cod = _texto(limpo.get("COD PROD") or limpo.get("CODIGO")
                             or limpo.get("COD PRODUTO"))
                bruta = limpar(limpo.get("CATEGORIA")).replace("-", " ")
                bruta = re.sub(r"\s+", " ", bruta).strip()
                categoria = CATEGORIA_DO_CSV.get(bruta)
                if cod and categoria:
                    saida[cod] = categoria
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return saida


# --------------------------------------------------------------------------
# a FAMILIA da peca
# --------------------------------------------------------------------------
# Peca e quase tudo: das 4.685 linhas do CATEGORIAS_PRODUTO, 4.385 sao
# LINHA LEVE. Um kit unico de "pecas" nao diz nada ao vendedor - ele
# vende FREIO, ou AMORTECEDOR, ou FILTRO. A familia sai da descricao,
# que e onde essa informacao existe de fato.
PALAVRA_GENERICA = {"KIT", "JOGO", "JG", "CJ", "CONJUNTO", "SEMI", "PAR",
                    "JOGO/", "KIT/"}
PALAVRA_DE_LIGACAO = {"DE", "DO", "DA", "DOS", "DAS", "P", "PARA", "COM",
                      "E", "C", "EM", "A", "O"}
CATEGORIAS_COM_FAMILIA = ("pecas_leve", "pecas_pesada", "pecas_moto")


def familia_do_produto(descricao) -> str:
    """
    A familia pela primeira palavra da descricao: AMORTECEDOR, FILTRO,
    TERMINAL, SENSOR... Quando ela e generica (KIT, JOGO), leva junto a
    palavra seguinte - "JOGO PASTILHA" diz algo, "JOGO" nao diz nada.
    """
    bruto = _sem_acento(_texto(descricao)).upper()
    # parte do estoque vem como "(980 - BAN14597DP) -BANDEJA SUSPENSAO":
    # o codigo entre parenteses na frente nao e a familia
    bruto = re.sub(r"^\s*\([^)]*\)\s*[-–]*\s*", " ", bruto)
    texto = re.sub(r"[^A-Z0-9 ]", " ", bruto)
    # codigo nao e familia: nem numero solto ("980 PASTILHA"), nem
    # letra com numero grudado ("BAN14597DP")
    palavras = [p for p in texto.split()
                if p and p not in PALAVRA_DE_LIGACAO
                and not any(c.isdigit() for c in p)]
    if not palavras:
        return "(sem descricao)"
    if palavras[0] in PALAVRA_GENERICA:
        for p in palavras[1:]:
            if p not in PALAVRA_GENERICA and not p.isdigit():
                return f"{palavras[0]} {p}"
    return palavras[0]


def _preco_do_item(linha, kit: dict) -> float:
    """O preco de tabela que o kit usa. Sem o escolhido, vale o outro."""
    base = _texto(kit.get("preco_base") or "capital").lower()
    primeiro = linha.get(f"preco_{base}") or 0.0
    outro = (linha.get("preco_interior") if base == "capital"
             else linha.get("preco_capital")) or 0.0
    return float(primeiro or outro or linha.get("custo") or 0.0)


# AS TRES LETRAS DA CATEGORIA NO CODIGO DO KIT. As tres primeiras do
# rotulo resolvem bateria, pneu e lubrificante, mas as TRES linhas de
# peca virariam "PEC" - o codigo deixaria de diferenciar justamente onde
# mais ha kit. Por isso a peca leva a letra da linha no fim: PLE, PPE,
# PMO.
LETRAS_DA_CATEGORIA = {
    "bateria": "BAT",
    "pneu": "PNE",
    "lubrificante": "LUB",
    "pecas_leve": "PLE",
    "pecas_pesada": "PPE",
    "pecas_moto": "PMO",
}


def letras_da_categoria(categoria: str) -> str:
    """As 3 letras que vao no codigo do kit."""
    if categoria in LETRAS_DA_CATEGORIA:
        return LETRAS_DA_CATEGORIA[categoria]
    rotulo = dict(CATEGORIAS_KIT).get(categoria, _texto(categoria)).upper()
    so_letras = re.sub(r"[^A-Z]", "", rotulo)
    return (so_letras[:3] or "KIT").ljust(3, "X")


def codigo_do_kit(filial: str, categoria: str = "", hoje=None,
                  seq: int = 1) -> str:
    """
    O CODIGO DO KIT, que substitui o nome comprido na coluna KIT:

        K - 3 letras da categoria - 4 ultimos numeros da filial
          - mes - dia - sequencia

        K-BAT-1002-09-14-01

    A categoria no codigo e o que faz um kit se distinguir do outro na
    boca do vendedor, sem precisar abrir a planilha. A sequencia de dois
    digitos continua no fim porque a MESMA categoria pode gerar mais de
    um kit na mesma filial no mesmo dia, quando a peca e quebrada por
    familia.
    """
    hoje = hoje or dt.date.today()
    return (f"K-{letras_da_categoria(categoria)}-"
            f"{prefixo_da_filial(filial)}-{hoje:%m}-{hoje:%d}-{seq:02d}")


def prefixo_da_filial(filial: str) -> str:
    """Os 4 ultimos numeros da filial, com zero a esquerda se faltar."""
    numeros = re.sub(r"\D", "", _texto(filial))
    return (numeros[-4:] if numeros else "0").rjust(4, "0")


def _fechar_as_caixas(detalhe: list, liberados_do_kit: dict) -> int:
    """
    O TOTAL DE CADA ITEM, e o cinto de seguranca da caixa.

    A caixa ja fecha DENTRO do kit: um lubrificante entra com a caixa
    cheia, entao a quantidade do kit vezes a quantidade de kits sempre
    cai num multiplo da caixa sozinha. Esta funcao calcula esse total e
    confere - se algum dia a conta la em cima mudar e deixar um total
    quebrado, aqui ele sobe e a contagem devolvida passa a ser maior que
    zero, que e o sinal de que algo saiu do lugar.

    Quem nao tem caixa (bateria, pneu, peca, balde de 20L) tem
    por_caixa = 1 e passa direto.
    """
    subiram = 0
    for l in detalhe:
        vezes = liberados_do_kit.get(l["kit"], 0)
        cru = int(l["quantidade"]) * int(vezes or 0)
        por_caixa = int(l.get("por_caixa") or 1)
        if por_caixa > 1 and cru > 0:
            caixas = -(-cru // por_caixa)          # divisao para CIMA
            total = caixas * por_caixa
        else:
            caixas = 0
            total = cru
        l["qtd_total_cru"] = cru
        l["qtd_total"] = total
        l["caixas_compra"] = caixas or None
        l["sobra_da_caixa"] = total - cru
        if total > cru:
            subiram += 1
    return subiram


def montar_kits(estoque: dict, categorias: dict, kit: dict,
                hoje=None) -> dict:
    """
    Monta UM kit por FILIAL e por CATEGORIA - e, se voce pedir, um por
    FAMILIA dentro das categorias de peca. Devolve o detalhamento (uma
    linha por produto do kit) e o resumo gerencial (uma linha por kit).
    """
    kit = {**kit_padrao(), **(kit or {})}
    cotas = {**kit_padrao()["cotas"], **(kit.get("cotas") or {})}
    investimento = {**kit_padrao()["investimento"],
                    **(kit.get("investimento") or {})}
    verba_geral = {**kit_padrao()["verba_geral"],
                   **(kit.get("verba_geral") or {})}
    gerar = {**kit_padrao()["gerar"], **(kit.get("gerar") or {})}
    por_familia = bool(kit.get("por_familia"))
    campo_curva = ("curva_filial" if _texto(kit.get("usar_curva")).lower()
                   != "geral" else "curva_geral")
    minimo = float(_numero(kit.get("estoque_minimo")))
    # as filiais escolhidas na aba 5. Nenhuma marcada = a rede inteira -
    # quem nunca abriu o campo nao fica sem kit por causa disso.
    so_filiais = {_texto(c) for c, v in (kit.get("filiais") or {}).items()
                  if v}
    filiais_fora = 0
    total_itens = int(_numero(kit.get("itens_no_kit")) or 0)
    em_caixa = bool(kit.get("caixa_lubrificante", True))
    sem_caixa_cheia = 0
    barrados_markup = 0

    # os candidatos, separados por (filial, categoria) e por curva.
    # O DIAGNOSTICO anda junto: quando um kit nao sai, a pergunta que
    # vem em seguida e sempre "por que nao saiu?" - e responder isso
    # depois, na mao, custa muito mais caro do que contar aqui.
    baldes = defaultdict(lambda: defaultdict(list))
    filiais = {}
    barrados = defaultdict(lambda: {"sem_categoria": 0, "sem_estoque": 0,
                                    "sem_preco": 0, "entraram": 0})
    desligadas = set()
    for linha in estoque.get("linhas") or []:
        categoria = categorias.get(linha["produto"])
        conta = barrados[(linha["filial"], categoria or "?")]
        filiais.setdefault(linha["filial"], linha["regiao"])
        # A FILIAL ESCOLHIDA NA ABA 5 manda antes de qualquer outra
        # regra: filial fora da acao nao monta kit e nem entra na conta
        # do "por que nao saiu" - ela foi desligada de proposito.
        if so_filiais and _texto(linha["filial"]) not in so_filiais:
            filiais_fora += 1
            continue
        if not categoria:
            conta["sem_categoria"] += 1
            continue
        if not gerar.get(categoria, True):
            # a categoria esta desmarcada nos parametros: nem entra na
            # disputa, e nem aparece como "kit que nao saiu"
            desligadas.add(categoria)
            barrados.pop((linha["filial"], categoria), None)
            continue
        if linha["estoque"] < minimo:
            conta["sem_estoque"] += 1
            continue
        preco = _preco_do_item(linha, kit)
        if preco <= 0:
            conta["sem_preco"] += 1
            continue                      # sem preco nao da para montar kit
        conta["entraram"] += 1
        familia = (familia_do_produto(linha["descricao"])
                   if por_familia and categoria in CATEGORIAS_COM_FAMILIA
                   else "")
        chave = (linha["filial"], categoria, familia)
        baldes[chave][linha[campo_curva]].append({**linha, "preco": preco,
                                                  "familia": familia})

    # dentro de cada curva, o mais valioso primeiro: o kit tem de ter
    # peso para valer a assinatura do diretor
    for balde in baldes.values():
        for lista in balde.values():
            lista.sort(key=lambda x: -(x["preco"] * x["estoque"]))

    detalhe, resumo = [], []
    hoje = hoje or dt.date.today()
    # O contador anda pelo que aparece NO CODIGO - as letras da categoria
    # mais os 4 numeros da filial -, nao pela filial inteira: duas
    # filiais que terminem nos mesmos 4 digitos nao podem sair com o
    # mesmo codigo no mesmo dia.
    sequencia = defaultdict(int)
    for (filial, categoria, familia) in sorted(baldes):
        balde = baldes[(filial, categoria, familia)]
        usados = set()
        linhas_kit = []
        valor = 0.0
        # a cota que sobrou de uma curva passa para a proxima: bater a
        # quantidade do kit vale mais que respeitar a divisao por curva
        sobra = 0
        for curva in ORDEM_DAS_CURVAS:
            regra = cotas.get(curva) or {}
            quero = int(_numero(regra.get("skus"))) + sobra
            unidades = int(_numero(regra.get("qtd")) or 1)
            desconto = float(_numero(regra.get("desconto")))
            mk_min = float(_numero(regra.get("markup_min")))
            # O DESCONTO DO GERENTE e descontado do preco de tabela ANTES
            # de tudo: o kit e montado ja em cima do preco de balcao que
            # a filial pratica. Dali para a frente a conta e uma so - o
            # desconto da acao - e a verba paga ele inteiro.
            g = max(0.0, min(100.0, float(_numero(regra.get("desc_gerente")))))
            pegos = 0
            for item in balde.get(curva, []):
                if pegos >= quero or len(linhas_kit) >= total_itens:
                    break
                if item["produto"] in usados:
                    continue
                # LUBRIFICANTE VAI NO KIT EM CAIXA FECHADA.
                #
                # O kit e uma cesta de VENDA: o cliente leva a caixa
                # inteira. Se entrar um 5W30, entram as 24 unidades da
                # caixa - nunca 1, nunca 7. A quantidade da curva vira
                # entao um PISO: ela sobe ate a proxima caixa cheia.
                #
                #     curva pede 1 ou 2 -> 24 (uma caixa)
                #     curva pede 30     -> 48 (duas caixas)
                #
                # Quem nao tiver estoque para UMA caixa inteira nao entra
                # no kit: meia caixa nao existe.
                por_caixa, grupo_caixa = 1, ""
                if categoria == "lubrificante":
                    por_caixa, grupo_caixa = caixa_do_produto(
                        item["descricao"], kit)
                if por_caixa > 1:
                    cheias = int(item["estoque"] // por_caixa)
                    if cheias <= 0:
                        sem_caixa_cheia += 1
                        continue
                    # a quantidade da curva arredondada PARA CIMA ate a
                    # caixa, limitada pelo que a filial tem inteiro
                    caixas = min(cheias, max(1, -(-unidades // por_caixa)))
                    unid = caixas * por_caixa
                else:
                    unid = min(unidades, int(item["estoque"]))
                if unid <= 0:
                    continue
                # O PRECO DE PARTIDA DO KIT: a tabela ja com o desconto
                # do gerente tirado. E este que vai para a coluna
                # VLR. UNIT. TABELA - o desconto dele nao aparece em
                # lugar nenhum, so acontece.
                preco_gerente = item["preco"] * (1 - g / 100.0)
                preco_final = preco_gerente * (1 - desconto / 100.0)

                # A TRAVA DO MARKUP. Desconto que derruba o markup abaixo
                # do piso da curva nao vale: o preco sobe ate o piso e o
                # desconto encolhe. Quem nem no preco de partida alcanca
                # o piso nao entra no kit - vender ali e vender no
                # negativo. Sem custo nao ha markup, e a linha passa.
                # O CUSTO DE VERDADE DA BATERIA: o P. PEDIDO do CD mais
                # a sucata que precisa ser entregue a fabrica junto com
                # a compra. So vale para bateria; nas outras categorias
                # a sucata e zero.
                sucata = (valor_da_sucata(item["descricao"], kit)
                          if categoria == "bateria" else 0.0)
                custo_unitario = float(item.get("custo") or 0.0)
                if custo_unitario > 0:
                    custo_unitario += sucata
                piso = (custo_unitario * (1 + mk_min / 100.0)
                        if custo_unitario > 0 and mk_min > 0 else 0.0)
                if piso:
                    if preco_gerente < piso - 1e-9:
                        barrados_markup += 1
                        continue
                    preco_final = max(preco_final, piso)
                    desconto_efetivo = (1 - preco_final / preco_gerente) * 100.0
                else:
                    desconto_efetivo = desconto
                soma = preco_final * unid
                # A VERBA PAGA O DESCONTO DA ACAO INTEIRO. Como o preco
                # de partida ja vem sem o desconto do gerente, nao ha
                # mais duas fatias: o que a coluna CUSTO/KIT mostra e
                # exatamente o que divide a verba.
                acao = max(0.0, preco_gerente - preco_final) * unid
                usados.add(item["produto"])
                linhas_kit.append({
                    "filial": filial,
                    "regiao": filiais.get(filial, ""),
                    "categoria": categoria,
                    "familia": familia,
                    "produto": item["produto"],
                    "descricao": item["descricao"],
                    "quantidade": unid,
                    "curva_filial": item["curva_filial"],
                    "curva_geral": item["curva_geral"],
                    "curva_usada": curva,
                    "cota_de": curva,
                    "herdou": pegos >= int(_numero(regra.get("skus"))),
                    # PRECO TABELA = o de balcao, ja sem o desconto do
                    # gerente. O cheio fica guardado ao lado, para quem
                    # precisar conferir, mas nao vai para coluna nenhuma.
                    "preco_tabela": preco_gerente,
                    "preco_tabela_cheio": item["preco"],
                    "desconto": desconto_efetivo,
                    "desconto_da_curva": desconto,
                    "markup_min": mk_min,
                    "desc_gerente": g,
                    "desc_acao": ((preco_gerente - preco_final)
                                  / preco_gerente * 100.0
                                  if preco_gerente else 0.0),
                    "preco_gerente": preco_gerente,
                    "preco_final": preco_final,
                    "valor_kit": soma,
                    # OS DOIS VALORES DA LINHA:
                    #   tabela (ja sem o desconto do gerente)
                    #        -> acao (com o desconto da curva)
                    "valor_tabela": preco_gerente * unid,
                    "valor_tabela_cheio": item["preco"] * unid,
                    # VALOR UNIT x QTD = VALOR TOTAL. No detalhe a conta
                    # e por produto; no resumo, por kit.
                    "valor_unit": preco_gerente,
                    "valor_total": preco_gerente * unid,
                    "valor_venda": preco_gerente * unid,
                    "valor_acao": soma,
                    "desconto_gerente_rs": (item["preco"] - preco_gerente)
                    * unid,
                    # CUSTO/KIT e o investimento da acao sao AGORA O
                    # MESMO NUMERO: o desconto que a acao da em cima do
                    # preco de partida. E ele que divide a verba e define
                    # a QTD LIBERADA - a conta fecha na tela.
                    "valor_investimento": acao,
                    "custo_por_kit": acao,
                    # o % MKP TABELA da linha sai do preco de partida -
                    # o mesmo que aparece na coluna VLR. UNIT. TABELA
                    "markup_normal": _markup(preco_gerente, custo_unitario),
                    "por_caixa": por_caixa if por_caixa > 1 else None,
                    "grupo_caixa": grupo_caixa,
                    "custo": custo_unitario,
                    "custo_cd": item.get("custo") or 0.0,
                    "sucata": sucata,
                    # o P. PEDIDO da linha: por UNIDADE e vezes a
                    # quantidade que entra no kit
                    "custo_unit": custo_unitario,
                    "custo_total": custo_unitario * unid,
                    # o desconto por UNIDADE - o de linha inteira e o
                    # custo_por_kit, logo acima
                    "desc_unit": max(0.0, preco_gerente - preco_final),
                    # O MARKUP DA ACAO: com o desconto ja dado, quanto o
                    # preco do kit ainda fica acima do custo do CD
                    "markup_acao": _markup(preco_final, custo_unitario),
                    "markup_tabela": _markup(item["preco"], custo_unitario),
                    "estoque": item["estoque"],
                })
                valor += soma
                pegos += 1
            sobra = max(0, quero - pegos)
            if len(linhas_kit) >= total_itens:
                break

        if not linhas_kit:
            continue
        rotulo = dict(CATEGORIAS_KIT).get(categoria, categoria.upper())
        prefixo = (letras_da_categoria(categoria), prefixo_da_filial(filial))
        sequencia[prefixo] += 1
        nome = codigo_do_kit(filial, categoria, hoje, sequencia[prefixo])
        # o nome por extenso nao some: ele continua no rodape do kit, na
        # aba NAO SAIU KIT e em qualquer aviso - so deixou de ocupar
        # meia tela na coluna
        descricao_kit = (f"KIT {rotulo}" + (f" / {familia}" if familia else "")
                         + f" - {filiais.get(filial, filial)}")
        # o preco de partida do kit: a tabela ja sem o desconto do
        # gerente. O cheio anda ao lado, so para conferencia.
        tabela = sum(l["valor_tabela"] for l in linhas_kit)
        tabela_cheia = sum(l["valor_tabela_cheio"] for l in linhas_kit)
        pos_gerente = tabela
        final = sum(l["valor_kit"] for l in linhas_kit)
        # o que a VERBA paga e o desconto da acao INTEIRO - o mesmo
        # numero que a coluna CUSTO/KIT mostra
        por_kit = sum(l["valor_investimento"] for l in linhas_kit)
        verba = float(_numero(investimento.get(categoria)))
        for l in linhas_kit:
            l["kit"] = nome
            l["kit_nome"] = descricao_kit
            l["rotulo_cat"] = rotulo
        detalhe.extend(linhas_kit)
        resumo.append({
            "kit": nome,
            "kit_nome": descricao_kit,
            "filial": filial,
            "regiao": filiais.get(filial, ""),
            "categoria": categoria,
            "rotulo": rotulo,
            "familia": familia,
            "itens": len(linhas_kit),
            "unidades": sum(l["quantidade"] for l in linhas_kit),
            "valor_tabela": tabela,
            "valor_tabela_cheio": tabela_cheia,
            "desc_gerente": ((1 - tabela / tabela_cheia) * 100.0
                             if tabela_cheia else 0.0),
            "desconto_gerente_rs": tabela_cheia - tabela,
            "preco_gerente": pos_gerente,
            "desc_acao": ((pos_gerente - final) / pos_gerente * 100.0
                          if pos_gerente else 0.0),
            "desconto": (1 - final / tabela) * 100.0 if tabela else 0.0,
            "preco_final": final,
            "investimento_kit": por_kit,
            "custo_total": sum(l["custo_total"] for l in linhas_kit),
            # a escada do kit inteiro
            "valor_venda": pos_gerente,
            "valor_unit": pos_gerente,      # o valor de UM kit
            "valor_acao": final,
            # o desconto da acao: e ele que a verba paga, e e ele que
            # divide a verba para dizer quantos kits saem
            "custo_por_kit": por_kit,
            # O MARKUP NORMAL e o do PRECO DE TABELA: quanto o kit esta
            # acima do custo ANTES de qualquer desconto. E dele que sai o
            # ROI, la embaixo.
            "markup_normal": _markup(tabela,
                                     sum(l["custo_total"]
                                         for l in linhas_kit)),
            "markup_acao": _markup(final,
                                   sum(l["custo_total"] for l in linhas_kit)),
            "verba": verba,
            "verba_geral": bool(verba_geral.get(categoria, True)),
            "completo": len(linhas_kit) >= total_itens,
            "herdadas": sum(1 for l in linhas_kit if l["herdou"]),
        })

    # A VERBA, DIVIDIDA ENTRE OS KITS QUE DISPUTAM ELA. So da para fazer
    # isso agora, com todos os kits na mao: a verba GERAL se reparte
    # entre os kits da categoria na rede inteira; a POR FILIAL, entre os
    # kits daquela categoria naquela filial (mais de um quando as pecas
    # sao quebradas por familia).
    quantos_na_rede = defaultdict(int)
    quantos_na_filial = defaultdict(int)
    for r in resumo:
        quantos_na_rede[r["categoria"]] += 1
        quantos_na_filial[(r["filial"], r["categoria"])] += 1
    # O PESO DE CADA FILIAL. Vale o que estiver nos parametros; sem
    # nada la, ele e calculado pelo faturamento dos ultimos 12 meses.
    pesos = {_texto(c): float(_numero(v))
             for c, v in (kit.get("peso_filial") or {}).items()
             if _numero(v) > 0}
    if not pesos:
        pesos = pesos_das_filiais(
            (estoque or {}).get("faturamento_filial") or {},
            filiais, float(_numero(kit.get("piso_da_filial"))
                           or PISO_DA_FILIAL))
    soma_dos_pesos = sum(pesos.values()) or 100.0

    # O PESO SE NORMALIZA ENTRE QUEM REALMENTE MONTOU KIT, categoria por
    # categoria.
    #
    # Sem isso a verba vaza: se MACAPA pesa 11% mas nao montou kit de
    # lubrificante, esses 11% da verba de lubrificante ficavam parados -
    # nao iam para ninguem. O peso continua saindo do faturamento da
    # rede inteira; o que muda e o DENOMINADOR, que passa a ser so a
    # soma das filiais que tem kit DAQUELA categoria.
    peso_da_categoria = defaultdict(float)
    for r in resumo:
        if r["verba_geral"]:
            peso_da_categoria[r["categoria"]] += pesos.get(r["filial"], 0.0)

    for r in resumo:
        # A VERBA GERAL SE REPARTE POR PESO DE FATURAMENTO, nao em partes
        # iguais: filial que fatura mais vende mais kit. Quando a verba
        # ja e POR FILIAL, o peso nao entra - a filial tem a dela inteira.
        peso = pesos.get(r["filial"], 0.0)
        r["peso_filial"] = peso
        divide = quantos_na_filial[(r["filial"], r["categoria"])]
        if r["verba_geral"]:
            # o peso divide a verba entre as FILIAIS que montaram kit
            # desta categoria; dentro da filial, os kits dela ainda
            # dividem entre si (as pecas quebradas por familia sao
            # mais de um)
            base = peso_da_categoria.get(r["categoria"]) or soma_dos_pesos
            r["peso_na_categoria"] = peso / base * 100.0 if base else 0.0
            da_filial = r["verba"] * peso / base
        else:
            r["peso_na_categoria"] = 100.0
            da_filial = r["verba"]
        r["kits_na_verba"] = divide
        r["verba_txt"] = ("GERAL (por peso da filial)" if r["verba_geral"]
                          else "POR FILIAL")
        r["verba_da_filial"] = da_filial
        r["verba_do_kit"] = da_filial / divide if divide else 0.0
        por_kit = r["investimento_kit"]
        # quantos kits a verba paga. Se o desconto todo coube na alcada
        # do gerente, a acao nao gasta nada - e a verba nao limita.
        liberados = int(r["verba_do_kit"] // por_kit) if por_kit > 0 else None
        r["kits_liberados"] = liberados
        r["valor_investido"] = (liberados or 0) * por_kit
        r["saldo_verba"] = r["verba_do_kit"] - r["valor_investido"]
        r["faturamento"] = (liberados or 0) * r["preco_final"]
        r["sem_verba"] = por_kit <= 0
        r["valor_total"] = (liberados or 0) * r["valor_unit"]
        # AS DUAS COLUNAS "TOTAL" DO RESUMO, as unicas que o kit inteiro
        # multiplica pela quantidade liberada:
        #
        #   CUSTO/TOTAL ....... CUSTO/KIT x QTD LIBERADA: o desconto
        #                       inteiro que a acao da, na quantidade toda
        #   VLR. TOTAL TABELA . VLR. UNIT. TABELA x QTD LIBERADA: o que
        #                       essa quantidade vale a preco cheio
        #
        # E o ROI sai delas duas com o markup de tabela:
        #
        #   ROI = (% MKP TABELA x VLR. TOTAL TABELA) - CUSTO/TOTAL
        r["custo_liberado"] = (liberados or 0) * r["custo_por_kit"]
        r["valor_total_tabela"] = (liberados or 0) * r["valor_tabela"]
        r["valor_kit_total"] = (liberados or 0) * r["valor_acao"]
        # o custo de COMPRA na mesma escala das colunas TT. Nao tem
        # coluna, mas e ele que da o markup certo na linha de TOTAL.
        r["custo_total_tt"] = (liberados or 0) * r["custo_total"]
        # MKP KIT TT: o markup da acao inteira em REAIS - o que entra
        # menos o que a mercadoria custou, ja na quantidade liberada.
        _c = r["custo_total"]
        r["roi_previsto"] = ((r["valor_kit_total"] - r["custo_total_tt"])
                             if _c > 0 else None)
        r["kits_liberados_txt"] = ("SEM LIMITE" if liberados is None
                                   else liberados)

    # AS MESMAS TRES COLUNAS NO DETALHE, linha a linha. O markup usado no
    # ROI e o DO KIT, nao o da linha: e o que faz a soma das linhas de um
    # kit fechar exatamente com o ROI daquele kit no resumo. A coluna
    # % MKP TABELA da linha continua sendo a da linha - ela informa, nao
    # entra na conta.
    liberados_do_kit = {r["kit"]: (r["kits_liberados"] or 0) for r in resumo}
    caixas_fechadas = _fechar_as_caixas(detalhe, liberados_do_kit)
    for l in detalhe:
        vezes = liberados_do_kit.get(l["kit"], 0)
        l["kits_liberados"] = vezes
        l["custo_liberado"] = vezes * l["custo_por_kit"]
        l["valor_total_tabela"] = vezes * l["valor_tabela"]
        l["valor_kit_total"] = vezes * l["valor_acao"]
        l["custo_total_tt"] = vezes * l["custo_total"]
        _c = l["custo_total"]
        l["roi_previsto"] = ((l["valor_kit_total"] - l["custo_total_tt"])
                             if _c > 0 else None)
        # MKP TT % e ROI % - os dois numeros que o diretor le primeiro
        l["markup_tt_pct"] = ((l["roi_previsto"] / l["custo_total_tt"] * 100.0)
                              if l["custo_total_tt"] and l["roi_previsto"]
                              is not None else None)
        l["roi_pct"] = ((l["roi_previsto"] / l["custo_liberado"] * 100.0)
                        if l["custo_liberado"] and l["roi_previsto"]
                        is not None else None)
    for r in resumo:
        r["markup_tt_pct"] = ((r["roi_previsto"] / r["custo_total_tt"] * 100.0)
                              if r["custo_total_tt"] and r["roi_previsto"]
                              is not None else None)
        r["roi_pct"] = ((r["roi_previsto"] / r["custo_liberado"] * 100.0)
                        if r["custo_liberado"] and r["roi_previsto"]
                        is not None else None)
        # as unidades que a compra daquele kit soma, ja em caixa fechada
        r["qtd_total"] = sum(l["qtd_total"] for l in detalhe
                             if l["kit"] == r["kit"])
        # QTD do resumo = as unidades que o kit inteiro leva
        r["quantidade"] = r["unidades"]
        r["sobra_da_caixa"] = sum(l["sobra_da_caixa"] for l in detalhe
                                  if l["kit"] == r["kit"])

    # O QUE NAO VIROU KIT, e por que. Uma combinacao filial x categoria
    # que existe no estoque mas nao gerou cesta vira uma linha aqui.
    saiu = {(r["filial"], r["categoria"]) for r in resumo}
    faltas = []
    for (filial, categoria), conta in sorted(barrados.items()):
        if categoria == "?" or (filial, categoria) in saiu:
            continue
        total = sum(conta[k] for k in ("sem_estoque", "sem_preco",
                                       "entraram"))
        if not total:
            continue
        if conta["entraram"] == 0 and conta["sem_estoque"]:
            motivo = (f"nenhum dos {conta['sem_estoque']} produto(s) chega "
                      f"ao estoque minimo de {minimo:.0f}")
        elif conta["entraram"] == 0 and conta["sem_preco"]:
            motivo = (f"os {conta['sem_preco']} produto(s) nao tem preco "
                      f"nesta tabela")
        else:
            motivo = ("nenhum produto sobrou depois das cotas por curva")
        faltas.append({
            # ESCOPO diz de que tipo e a falta: "filial" e uma combinacao
            # filial x categoria que tinha candidato e nao fechou kit;
            # "categoria" e uma categoria inteira que nem candidato teve.
            # Sao coisas diferentes e se leem diferente.
            "escopo": "filial",
            "filial": filial, "regiao": filiais.get(filial, ""),
            "categoria": categoria, "motivo": motivo,
            "sem_estoque": conta["sem_estoque"],
            "sem_preco": conta["sem_preco"],
            "candidatos": conta["entraram"],
        })

    # CATEGORIA MARCADA, COM VERBA, E SEM UM UNICO PRODUTO.
    #
    # Ela nao entra no laco acima porque nunca chegou a ter candidato -
    # e some da tela sem explicacao, levando a verba junto. Foi assim
    # que 5.000 reais de PECAS-MOTO ficaram parados: nao existe um
    # produto sequer classificado como moto no CATEGORIAS_PRODUTO.csv.
    por_categoria = defaultdict(int)
    for produto_cat in categorias.values():
        por_categoria[produto_cat] += 1
    com_kit = {r["categoria"] for r in resumo}
    for cat_chave, rotulo_cat in CATEGORIAS_KIT:
        if cat_chave in com_kit or not gerar.get(cat_chave, True):
            continue
        verba_cat = float(_numero(investimento.get(cat_chave)))
        quantos = por_categoria.get(cat_chave, 0)
        if quantos and any(f["categoria"] == cat_chave for f in faltas):
            continue                      # o laco de cima ja explicou
        if not quantos:
            motivo = ("nao ha UM produto sequer classificado nesta "
                      "categoria no CATEGORIAS_PRODUTO.csv")
        elif quantos:
            motivo = (f"os {quantos} produto(s) desta categoria nao "
                      f"estao no estoque de nenhuma filial escolhida")
        if verba_cat:
            motivo += (f" - e por isso {_dinheiro_simples(verba_cat)} de "
                       f"verba ficaram parados")
        faltas.append({
            "escopo": "categoria",
            "filial": "", "regiao": "(todas)", "categoria": cat_chave,
            "motivo": motivo, "sem_estoque": 0, "sem_preco": 0,
            "candidatos": quantos, "verba_parada": verba_cat,
        })

    resumo.sort(key=lambda x: (x["categoria"], x["familia"], x["regiao"]))
    detalhe.sort(key=lambda x: (x["categoria"], x["familia"], x["regiao"],
                                -x["valor_investimento"]))
    return {
        "detalhe": detalhe,
        "resumo": resumo,
        "hoje": estoque.get("hoje") or dt.date.today(),
        "campo_curva": campo_curva,
        "sem_categoria": sum(1 for l in (estoque.get("linhas") or [])
                             if l["produto"] not in categorias),
        "incompletos": sum(1 for r in resumo if not r["completo"]),
        "faltas": faltas,
        "estoque_minimo": minimo,
        "desc_gerente": {c: float(_numero((cotas.get(c) or {})
                                          .get("desc_gerente")))
                         for c in ORDEM_DAS_CURVAS},
        "por_familia": por_familia,
        "caixa_lubrificante": True,       # agora e sempre, ver _fechar_as_caixas
        "caixas_fechadas": caixas_fechadas,
        "pesos_das_filiais": pesos,
        # a verba que CHEGOU aos kits e a que foi de fato usada: a
        # diferenca e o resto que nao fecha mais um kit inteiro
        "verba_nos_kits": sum(r["verba_do_kit"] * r["kits_na_verba"]
                              for r in resumo),
        "verba_usada": sum(r["custo_liberado"] for r in resumo),
        "verba_parada": sum(f.get("verba_parada") or 0.0 for f in faltas),
        "sem_caixa_cheia": sem_caixa_cheia,
        "barrados_markup": barrados_markup,
        "desligadas": sorted(desligadas),
        # as filiais que o estoque conhece, para a aba 5 montar a lista,
        # e quantas linhas ficaram de fora por filial desmarcada
        "filiais_do_estoque": dict(sorted(filiais.items(),
                                          key=lambda x: (x[1], x[0]))),
        "filiais_escolhidas": sorted(so_filiais),
        "filiais_fora": filiais_fora,
        "barrados_estoque": sum(c["sem_estoque"] for c in barrados.values()),
        "barrados_preco": sum(c["sem_preco"] for c in barrados.values()),
    }


# AS COLUNAS DO KIT - primeiro o que e de UM kit, depois o que ja esta
# multiplicado pela QTD LIBERADA (as colunas TT). Cada valor vem com o
# seu markup ao lado:
#
#   VLR TABELA ..... um kit (ou um item) a preco de tabela, ja sem o
#                    % DESC. GERENTE da curva
#   MKP TABELA ..... VLR TABELA / P. PEDIDO - 1
#   % DESC. ........ o desconto da acao em cima desse preco
#   DESC. R$ ....... o mesmo desconto em reais. E ele o investimento da
#                    acao, e e ele que divide a verba
#   VLR KIT ........ o que o cliente paga
#   MKP KIT ........ VLR KIT / P. PEDIDO - 1
#   P. PEDIDO ...... o que a mercadoria custou: o PPEDIDO do CD da aba
#                    3 MAIS a sucata, quando e bateria
#   QTD LIBERADA ... a verba da categoria dividida pelo DESC. R$
#   ... TT ......... cada uma das de cima x QTD LIBERADA
#   MKP KIT TT ..... VLR KIT TT - P. PEDIDO TT: o markup em REAIS da
#                    acao inteira
#
# Os nomes sao curtos de proposito: tudo tem de caber numa tela so.
# AS COLUNAS DO KIT
#
# Sao AS MESMAS no resumo e no detalhe, so mudando o que cada linha e:
# no resumo, um KIT inteiro; no detalhe, um PRODUTO dentro dele. Isso
# deixa a folha que vai para o diretor com uma leitura so - ele ve o
# total em cima e, se quiser, desce para o item que formou o total.
#
# A REGRA DAS QUANTIDADES:
#   QTD ................ quanto daquele item vai em UM kit
#   QTD KIT ORCADA ..... quantos kits a verba paga
#   QTD A COMPRAR ...... QTD x QTD KIT ORCADA, arredondado para CIMA ate
#                        fechar caixa. E o numero que vai para o
#                        fornecedor. Ver _fechar_as_caixas().
#
# VLR P. PEDIDO, VLR TABELA e DESC. R$ ja saem MULTIPLICADOS PELA QTD -
# a pergunta e sempre "quanto custa a quantidade que eu pedi deste
# item", nunca "quanto custa uma unidade".
#
# As colunas de % (DESC., MKP) nao multiplicam nada: percentual e
# percentual em qualquer quantidade.
COLUNAS_KIT_VALOR = [
    ("QTD", "quantidade", 8, "#,##0"),
    ("P. PEDIDO", "custo_total", 14, "#,##0.00"),
    # o VLR TABELA ja vem com o desconto do gerente tirado - o nome diz
    # isso, para ninguem comparar com a tabela cheia e achar que falta
    ("VLR TAB. C/ 15%", "valor_tabela", 16, "#,##0.00"),
    ("DESC. R$", "custo_por_kit", 13, "#,##0.00"),
    ("DESC. %", "desconto", 10, "#,##0.00"),
    ("VLR KIT", "valor_acao", 13, "#,##0.00"),
    ("QTD KITS", "kits_liberados", 11, "#,##0"),
    ("VLR TOTAL", "valor_kit_total", 15, "#,##0.00"),
    ("INVEST. R$", "custo_liberado", 17, "#,##0.00"),
    ("MKP TT R$", "roi_previsto", 14, "#,##0.00"),
    ("MKP TT %", "markup_tt_pct", 11, "#,##0.00"),
    ("ROI %", "roi_pct", 10, "#,##0.00"),
]

# no detalhe, quem e a linha: o produto
def _com_valor_unitario(colunas: list) -> list:
    """As colunas de valor com o VLR UNIT. encaixado antes do VLR KIT."""
    saida = []
    for coluna in colunas:
        if coluna[1] == "valor_acao":
            saida.append(("VLR UNIT.", "preco_final", 13, "#,##0.00"))
        saida.append(coluna)
    return saida


# No DETALHE entra tambem o VLR UNIT.: quanto UMA unidade daquele item
# custa dentro do kit. Ele fica LOGO ANTES do VLR KIT porque e dali que
# o VLR KIT sai - a linha se le em sequencia, de ponta a ponta:
#
#   P. PEDIDO -> VLR TAB. C/ 15% -> DESC. R$ -> DESC. % -> VLR UNIT.
#   -> VLR KIT (= VLR UNIT. x QTD) -> QTD KITS -> VLR TOTAL
COLUNAS_KIT_DETALHE = ([
    ("KIT", "kit", 21, None),
    ("FILIAL", "regiao", 18, None),
    ("CATEGORIA", "rotulo_cat", 22, None),
    ("COD. PRODUTO", "produto", 22, None),
    ("DESCRICAO", "descricao", 46, None),
] + _com_valor_unitario(COLUNAS_KIT_VALOR))

# no resumo, quem e a linha: o kit
COLUNAS_KIT_RESUMO = ([
    ("KIT", "kit", 21, None),
    ("FILIAL", "regiao", 18, None),
    ("CATEGORIA", "rotulo", 22, None),
] + [(t, ("kits_liberados_txt" if c == "kits_liberados" else c), l, f)
     for t, c, l, f in COLUNAS_KIT_VALOR])


# A FOLHA DOS KITS - para o diretor aprovar
#
# A mesma leitura em duas alturas: a primeira pagina e o RESUMO, um kit
# por linha, com o total embaixo - e isso que se assina. Depois vem uma
# pagina por kit, com os produtos que formaram aquele numero, para quem
# quiser descer ao item.
#
# O "tipo" aqui e do _celula_impressa do meta_nucleo: ele so diz como
# formatar (R$ com duas casas, contagem sem casa, percentual).
TIPO_DA_COLUNA_KIT = {
    "quantidade": "inteiro", "qtd_total": "inteiro",
    "kits_liberados": "inteiro", "kits_liberados_txt": "inteiro",
    "desconto": "pct", "markup_acao": "pct",
    "markup_tt_pct": "pct", "roi_pct": "pct",
}


def _colunas_para_folha(colunas: list) -> list:
    """(rotulo, chave, tipo) a partir das colunas do Excel."""
    return [(rotulo, chave, TIPO_DA_COLUNA_KIT.get(chave, "dinheiro")
             if formato else TIPO_DA_COLUNA_KIT.get(chave, "texto"))
            for rotulo, chave, _largura, formato in colunas]


def blocos_da_folha_de_kits(kits: dict, resumo=None, detalhe=None) -> list:
    """
    Os blocos do PDF: o RESUMO primeiro, depois um bloco por KIT.

    `resumo` e `detalhe` deixam a tela mandar a lista que esta filtrada
    nela; sem eles, vale o que montar_kits() devolveu.
    """
    resumo = list(resumo if resumo is not None else (kits or {}).get("resumo")
                  or [])
    detalhe = list(detalhe if detalhe is not None
                   else (kits or {}).get("detalhe") or [])
    if not resumo:
        return []
    # no resumo a coluna KIT leva o codigo; o nome por extenso vai na
    # FILIAL, que e o que o diretor procura na hora de ler
    colunas_r = _colunas_para_folha(
        [c for c in COLUNAS_KIT_RESUMO if c[1] != "rotulo"]
        if len({r.get("rotulo") for r in resumo}) == 1
        else COLUNAS_KIT_RESUMO)
    blocos = [{
        "titulo": "RESUMO",
        "colunas": colunas_r,
        "linhas": resumo,
        "total": _total_da_folha(resumo),
    }]
    # e uma pagina por kit, so com os produtos daquele kit
    colunas_d = _colunas_para_folha(
        [c for c in COLUNAS_KIT_DETALHE if c[1] not in ("kit", "regiao",
                                                        "rotulo_cat")])
    por_kit = defaultdict(list)
    for l in detalhe:
        por_kit[l.get("kit")].append(l)
    for r in resumo:
        linhas = por_kit.get(r.get("kit")) or []
        if not linhas:
            continue
        blocos.append({
            "titulo": f"{r.get('kit')}  -  {r.get('kit_nome') or ''}".strip(),
            "colunas": colunas_d,
            "linhas": linhas,
            "total": _total_da_folha(linhas),
        })
    return blocos


def _kits_do_conjunto(linhas: list) -> int:
    """
    A QTD KIT ORCADA de um conjunto de linhas.

    NAO E UMA SOMA SIMPLES: no detalhe, as cinco linhas de um kit de
    oito repetem o mesmo 8, e somar daria 40 kits que nao existem. Cada
    kit entra UMA vez, pelo codigo dele.
    """
    por_kit = {}
    for l in linhas:
        por_kit[l.get("kit")] = l.get("kits_liberados") or 0
    return sum(por_kit.values())


def _total_da_folha(linhas: list) -> dict:
    """A linha de TOTAL de um bloco da folha."""
    # VLR UNIT. nao se soma: preco de unidade com unidade nao da nada
    soma = {"kit": "TOTAL", "regiao": "", "rotulo": "", "rotulo_cat": "",
            "produto": "", "descricao": f"{len(linhas)} linha(s)",
            "preco_final": None}
    for campo in SOMA_NO_DETALHE:
        soma[campo] = sum(l.get(campo) or 0 for l in linhas)
    soma["kits_liberados"] = _kits_do_conjunto(linhas)
    soma["kits_liberados_txt"] = soma["kits_liberados"]
    soma["preco_final"] = None
    _totais_do_conjunto(soma)
    return soma


def nome_da_folha_de_kits(hoje=None) -> str:
    hoje = hoje or dt.date.today()
    return f"KITS_PARA_APROVACAO_{hoje:%Y%m%d}.html"


def gravar_folha_de_kits(kits: dict, caminho, resumo=None, detalhe=None,
                         subtitulo: str = "") -> Path:
    """A folha A4 deitada pronta para o Ctrl+P do navegador."""
    from meta_nucleo import html_para_imprimir

    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    blocos = blocos_da_folha_de_kits(kits, resumo, detalhe)
    if not blocos:
        raise ValueError("Nao ha kit nenhum para imprimir.")
    hoje = (kits or {}).get("hoje") or dt.date.today()
    rodape = ("QTD = quantas unidades do item vao em UM kit.   "
              "P. PEDIDO, VLR TAB. C/ 15% e DESC. R$ ja vem multiplicados "
              "pela QTD.   VLR TOTAL = QTD KITS x VLR KIT.   "
              "INVEST. R$ = QTD KITS x DESC. R$, o que a verba paga.   "
              "ROI % = MKP TT R$ dividido pelo INVEST. R$.   "
              "O P. PEDIDO da bateria ja inclui a sucata que vai junto "
              "para a fabrica.")
    caminho.write_text(
        html_para_imprimir(blocos, "SUGESTAO DE KITS",
                           subtitulo or f"gerado em {hoje:%d/%m/%Y}",
                           rodape),
        encoding="utf-8")
    return caminho


def nome_do_arquivo_de_kits(hoje=None) -> str:
    hoje = hoje or dt.date.today()
    return f"SUGESTAO_DE_KITS_BAP_{hoje:%Y%m%d}.xlsx"


SOMA_NO_DETALHE = ("quantidade", "qtd_total", "sobra_da_caixa",
                   "valor_tabela", "valor_unit",
                   "valor_total", "valor_venda", "valor_acao",
                   "custo_por_kit", "roi_previsto", "custo_total",
                   "custo_liberado", "valor_total_tabela",
                   "valor_kit_total", "custo_total_tt",
                   "desc_unit", "custo_unit", "preco_tabela", "preco_final",
                   "sucata")


def _totais_do_conjunto(soma: dict) -> None:
    """
    OS PERCENTUAIS DA LINHA DE TOTAL.

    Eles saem das colunas POR KIT - VLR TABELA, VLR KIT e CUSTO CD -,
    que ficam ali do lado, somadas. Assim quem quiser conferir divide
    duas celulas vizinhas e chega no mesmo numero.

    O markup ponderado pela QUANTIDADE que vai a rua (as colunas TT) e
    outro numero, geralmente menor: um kit que libera 138 unidades pesa
    138 vezes mais ali do que um que libera 2. Ele nao aparece porque
    nenhuma coluna da tela fecharia com ele - o MKP KIT TT e uma
    subtracao, VLR KIT TT menos CUSTO CD TT, e fecha sozinho.
    """
    tabela = soma.get("valor_tabela") or 0.0
    venda = soma.get("valor_acao") or 0.0
    custo = soma.get("custo_total") or 0.0
    soma["markup_normal"] = _markup(tabela, custo)
    soma["markup_acao"] = _markup(venda, custo)
    soma["desconto"] = (1 - venda / tabela) * 100.0 if tabela else 0.0
    # MKP TT % e ROI % do TOTAL saem das colunas somadas ao lado, para
    # quem quiser conferir dividir duas celulas vizinhas
    mkp_tt = soma.get("roi_previsto") or 0.0
    custo_tt = soma.get("custo_total_tt") or 0.0
    investido = soma.get("custo_liberado") or 0.0
    soma["markup_tt_pct"] = (mkp_tt / custo_tt * 100.0) if custo_tt else None
    soma["roi_pct"] = (mkp_tt / investido * 100.0) if investido else None


def _total_do_kit(linhas: list, nome: str) -> dict:
    """A linha de fecho de um kit, no fim das linhas dele."""
    # o nome por extenso do kit vive aqui, na linha de fecho: a coluna
    # KIT passou a ser so o codigo
    por_extenso = (linhas[0].get("kit_nome") if linhas else "") or ""
    soma = {"kit": f"TOTAL DO {nome}", "regiao": "", "rotulo_cat": "",
            "familia": "", "categoria": "",
            "descricao": (f"{por_extenso} - " if por_extenso else "")
            + f"{len(linhas)} produto(s) no kit"}
    for campo in SOMA_NO_DETALHE:
        soma[campo] = sum(l.get(campo) or 0 for l in linhas)
    soma["kits_liberados"] = _kits_do_conjunto(linhas)
    soma["kits_liberados_txt"] = soma["kits_liberados"]
    custo = sum(l.get("custo_total") or 0 for l in linhas)
    # o kit inteiro: preco de tabela x quantidade, e o mesmo com desconto
    soma["markup_normal"] = _markup(soma["valor_tabela"], custo)
    soma["markup_acao"] = _markup(soma["valor_acao"], custo)
    soma["desconto"] = ((1 - soma["valor_acao"] / soma["valor_tabela"]) * 100.0
                        if soma["valor_tabela"] else 0.0)
    return soma


def _nome_de_aba(texto: str, usados: set) -> str:
    """Um nome de aba que o Excel aceita: sem : \\ / ? * [ ] e ate 31."""
    limpo = re.sub(r"[:\\/?*\[\]]", " ", _texto(texto)).strip() or "REGIAO"
    limpo = re.sub(r"\s+", " ", limpo)[:31]
    base, n = limpo, 2
    while limpo.upper() in usados:
        limpo = f"{base[:28]} {n}"
        n += 1
    usados.add(limpo.upper())
    return limpo


def gravar_excel_kits(kits: dict, par: dict, kit: dict, caminho) -> Path:
    """
    O arquivo que vai para o diretor comercial: o RESUMO GERENCIAL na
    frente - e por ele que se aprova -, o DETALHAMENTO atras e a aba
    PARAMETROS dizendo com que regra tudo isso foi montado.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    caminho = Path(caminho)
    wb = Workbook()
    wb.remove(wb.active)

    def folha(titulo, colunas, linhas, total=None, por_kit=False):
        ws = wb.create_sheet(titulo[:31])
        ws.append([t for t, _, _, _ in colunas])
        fundo = PatternFill("solid", fgColor="14375E")
        branco = Font(color="FFFFFF", bold=True, size=9)
        cinza = PatternFill("solid", fgColor="EDF1F7")
        for i, (_, _, largura, _) in enumerate(colunas, start=1):
            ws.cell(1, i).fill = fundo
            ws.cell(1, i).font = branco
            ws.cell(1, i).alignment = Alignment(horizontal="center",
                                                wrap_text=True)
            ws.column_dimensions[ws.cell(1, i).column_letter].width = largura

        def escrever(linha, negrito=False, fundo_claro=False):
            ws.append([linha.get(k) for _, k, _, _ in colunas])
            if negrito or fundo_claro:
                for j in range(1, len(colunas) + 1):
                    celula = ws.cell(ws.max_row, j)
                    if negrito:
                        celula.font = Font(bold=True, size=9)
                    if fundo_claro:
                        celula.fill = cinza

        if por_kit:
            # cada kit fecha com a sua propria linha de total: e assim que
            # o gerente le a folha da regiao dele, kit por kit
            atual, bloco = None, []
            for linha in linhas:
                if atual is not None and linha.get("kit") != atual:
                    escrever(_total_do_kit(bloco, atual), True, True)
                    bloco = []
                atual = linha.get("kit")
                bloco.append(linha)
                escrever(linha)
            if bloco:
                escrever(_total_do_kit(bloco, atual), True, True)
        else:
            for linha in linhas:
                escrever(linha)
        if total:
            escrever(total, True)
        for j, (_, _, _, formato) in enumerate(colunas, start=1):
            if formato:
                for n in range(2, ws.max_row + 1):
                    ws.cell(n, j).number_format = formato
        ws.freeze_panes = "A2"
        fim = ws.max_row - (1 if total else 0)
        if fim > 1 and not por_kit:
            ws.auto_filter.ref = (f"A1:{ws.cell(1, len(colunas)).column_letter}"
                                  f"{fim}")
        return ws

    resumo = kits.get("resumo") or []
    total = {"kit": "TOTAL", "regiao": f"{len(resumo)} kit(s)",
             "rotulo": "", "familia": "",
             "kits_liberados_txt": sum(r["kits_liberados"] or 0
                                       for r in resumo)}
    for campo in ("valor_tabela", "valor_total", "valor_venda", "valor_acao",
                  "custo_por_kit", "roi_previsto", "custo_total",
                  "valor_investido", "custo_liberado", "valor_total_tabela",
                  "valor_kit_total", "verba_do_kit",
                  "custo_total_tt"):
        total[campo] = sum(r.get(campo) or 0 for r in resumo)
    total["valor_unit"] = None
    _totais_do_conjunto(total)
    # As tres colunas POR KIT sao valor de UM kit: somar 21 delas nao da
    # numero nenhum. Os markups e o % DESC. ja sairam delas, logo acima.
    # O que fecha em baixo e o que ja e TOTAL: CUSTO/TOTAL, VLR. TOTAL
    # TABELA e ROI.
    folha("RESUMO GERENCIAL", COLUNAS_KIT_RESUMO, resumo, total)
    detalhe = kits.get("detalhe") or []
    folha("DETALHAMENTO", COLUNAS_KIT_DETALHE, detalhe, por_kit=True)

    # UMA ABA POR CATEGORIA: quem compra bateria abre a folha de bateria
    # e nao ve mais nada. Cada kit fecha com a sua linha de total.
    colunas_cat = [c for c in COLUNAS_KIT_DETALHE if c[1] != "rotulo_cat"]
    usados = {"RESUMO GERENCIAL", "DETALHAMENTO", "NAO SAIU KIT",
              "PARAMETROS"}
    titulos = dict(CATEGORIAS_KIT)
    vistas = []
    for linha in detalhe:
        if linha.get("categoria") not in vistas:
            vistas.append(linha.get("categoria"))
    for categoria in vistas:
        linhas = [l for l in detalhe if l.get("categoria") == categoria]
        if not linhas:
            continue
        folha(_nome_de_aba(titulos.get(categoria, str(categoria)), usados),
              colunas_cat, linhas, por_kit=True)
    if kits.get("faltas"):
        titulos = dict(CATEGORIAS_KIT)
        faltas = [{**f, "rotulo": titulos.get(f["categoria"], f["categoria"])}
                  for f in kits["faltas"]]
        folha("NAO SAIU KIT", [
            ("FILIAL", "regiao", 18, None),
            ("COD FILIAL", "filial", 13, None),
            ("CATEGORIA", "rotulo", 22, None),
            ("POR QUE NAO SAIU", "motivo", 60, None),
            ("BARRADOS PELO ESTOQUE MINIMO", "sem_estoque", 29, "#,##0"),
            ("SEM PRECO NA TABELA", "sem_preco", 20, "#,##0"),
            ("CANDIDATOS QUE SOBRARAM", "candidatos", 24, "#,##0"),
        ], faltas)

    wp = wb.create_sheet("PARAMETROS")
    wp["A1"] = "Com que regra estes kits foram montados"
    wp["A1"].font = Font(bold=True, size=12, color="1F4E79")
    cotas = {**kit_padrao()["cotas"], **(kit.get("cotas") or {})}
    regras = [
        ("Data de referencia", kits.get("hoje", dt.date.today())
         .strftime("%d/%m/%Y")),
        ("Itens (SKUs) no kit", _texto(kit.get("itens_no_kit"))),
        ("Estoque minimo por produto", _texto(kit.get("estoque_minimo"))),
        ("Filiais na acao",
         ", ".join(f"{n} ({c})" for c, n
                   in (kits.get("filiais_do_estoque") or {}).items()
                   if c in set(kits.get("filiais_escolhidas") or ()))
         or "todas as filiais com estoque"),
        ("Desconto do gerente",
         "sai do preco de tabela ANTES de o kit ser montado, por curva "
         "(abaixo). O VLR. UNIT. TABELA das planilhas ja vem sem ele"),
        ("Verba consumida por kit",
         "o desconto da ACAO inteiro - o mesmo numero da coluna "
         "CUSTO/KIT. E ele que divide a verba da categoria"),
        ("Curva usada na montagem",
         "a da FILIAL" if kits.get("campo_curva") == "curva_filial"
         else "a GERAL da BAP"),
        ("Preco de tabela usado", _texto(kit.get("preco_base")).upper()),
        ("", ""),
        ("POR CURVA", "quantos SKUs, quantas unidades de cada, o desconto "
                      "do gerente, o da acao e a trava do markup"),
    ]
    for curva in ORDEM_DAS_CURVAS:
        c = cotas.get(curva) or {}
        regras.append((f"   CURVA {curva}",
                       f"{int(_numero(c.get('skus')))} SKU(s) x "
                       f"{int(_numero(c.get('qtd')))} unidade(s), "
                       f"gerente {_numero(c.get('desc_gerente')):.1f}%, "
                       f"acao {_numero(c.get('desconto')):.1f}%, "
                       f"markup min {_numero(c.get('markup_min')):.1f}%"))
    regras += [("", ""),
               ("VERBA POR CATEGORIA",
                "e ela que diz quantos kits podem ir para a rua")]
    _geral = {**kit_padrao()["verba_geral"], **(kit.get("verba_geral") or {})}
    _liga = {**kit_padrao()["gerar"], **(kit.get("gerar") or {})}
    for chave, rotulo in CATEGORIAS_KIT:
        verba = _numero((kit.get("investimento") or {}).get(chave))
        if not _liga.get(chave, True):
            regras.append((f"   {rotulo}", "DESMARCADA - nao gerou kit"))
            continue
        regras.append((f"   {rotulo}",
                       f"R$ {verba:,.2f} - "
                       + ("da REDE INTEIRA, dividida entre os kits da "
                          "categoria" if _geral.get(chave, True)
                          else "vale PARA CADA FILIAL")))
    regras += [("", ""),
               ("A CAIXA DO LUBRIFICANTE",
                "oleo sai em caixa fechada: a QTD DO ITEM da curva conta "
                "CAIXAS, e quem nao tem estoque para uma caixa inteira fica "
                "de fora" if kit.get("caixa_lubrificante", True)
                else "DESLIGADA - o lubrificante sai unidade a unidade")]
    if kit.get("caixa_lubrificante", True):
        for regra in (kit.get("caixas") or caixas_padrao()):
            regras.append((f"   {_texto(regra.get('nome'))}",
                           f"{int(_numero(regra.get('unidades')) or 1)} "
                           f"unidade(s) por caixa - reconhece por: "
                           f"{', '.join(regra.get('palavras') or [])}"))
        regras.append(("   (os demais)",
                       "balde, tambor e galao saem avulsos, um a um"))
    regras += [("", ""),
               ("KIT DE PECA POR FAMILIA",
                "SIM - cada familia de peca vira um kit proprio"
                if kit.get("por_familia") else
                "NAO - um kit unico por categoria de peca")]
    regras += [
        ("", ""),
        ("A COTA QUE SOBRA PASSA ADIANTE",
         "se faltar produto numa curva, a vaga vai para a proxima - bater "
         "a quantidade do kit vale mais que respeitar a divisao"),
        ("ENTROU PELA CURVA",
         "a curva cuja cota pagou aquela linha; quando difere da curva do "
         "produto, a linha herdou uma vaga"),
        ("Kits incompletos", _texto(kits.get("incompletos"))),
    ]
    for i, (a, b) in enumerate(regras, start=3):
        wp.cell(i, 1, a).font = Font(bold=True, size=10)
        wp.cell(i, 2, b).font = Font(size=10)
    wp.column_dimensions["A"].width = 32
    wp.column_dimensions["B"].width = 72

    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


# ==========================================================================
#  O ANALITICO DE ROTA
#
#  A mesma consulta que existe no Planner, aqui do lado da base de
#  oportunidade - porque a pergunta "quando eu passo nesse cliente?" vem
#  junto com "o que eu vendo para ele?", e ficar trocando de programa para
#  responder as duas era o incomodo.
#
#  A diferenca esta na FONTE: o Planner calcula a rota do mes a partir do
#  cadastro; aqui a rota e LIDA do PLANNER_BAP que ja foi gerado - a que
#  esta valendo na rua. Por isso a lista nunca diverge do arquivo que o
#  vendedor recebeu.
# ==========================================================================
# a base de oportunidade e as colunas dela vivem no meta_nucleo: aqui so
# se acrescenta a agenda na frente ou atras
from meta_nucleo import COLUNAS_OPORTUNIDADE, TODOS      # noqa: E402

VISAO_CLIENTE = "CLIENTE (sem repetir)"
VISAO_VISITA = "DIA E SEMANA (repetindo)"
VISOES_DA_ROTA = [VISAO_CLIENTE, VISAO_VISITA]

# as colunas de agenda, na frente da lista quando a visao e por VISITA
COLUNAS_ROTA_VISITA = [
    ("SEMANA", "semana", 11, None),
    ("DIA", "dia", 7, None),
    ("DIA DA SEMANA", "dia_semana", 15, None),
    ("DATA", "data", 12, "DD/MM/YYYY"),
    ("ORDEM", "ordem", 8, None),
]
# e as que resumem a agenda quando a visao e por CLIENTE
COLUNAS_ROTA_CLIENTE = [
    ("VISITAS NO MES", "visitas", 15, None),
    ("DIAS DE VISITA", "dias", 22, None),
    ("SEMANAS", "semanas", 14, None),
]


def _chave_do_cliente(cod, loja) -> str:
    return f"{_texto(cod)}-{_texto(loja) or '00'}"


def ler_visitas_do_planner(caminho) -> list:
    """
    Uma entrada por VISITA do PLANNER_BAP - o arquivo que ja foi gerado,
    nao um recalculo. Sem a aba PLANNER, devolve lista vazia e a aba
    simplesmente avisa que falta gerar a rota.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        return []
    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        aba = "PLANNER" if "PLANNER" in wb.sheetnames else wb.sheetnames[0]
        cab, it = _cabecalho(wb[aba])
        indice = {limpar(t): i for i, t in enumerate(cab) if t}

        def pega(linha, *nomes):
            for nome in nomes:
                i = indice.get(limpar(nome))
                if i is not None and i < len(linha):
                    return linha[i]
            return None

        saida = []
        for r in it:
            cod = _texto(pega(r, "COD_CLIENTE"))
            if not cod:
                continue
            saida.append({
                "chave": _chave_do_cliente(cod, pega(r, "LOJA")),
                "cod_cliente": cod,
                "semana": _texto(pega(r, "SEMANA_VISITA", "SEMANA")),
                "dia": _texto(pega(r, "DIA_VISITA", "DIA")),
                "dia_semana": _texto(pega(r, "DIA_DA_SEMANA")),
                "data": _data(pega(r, "DATA_VISITA", "DATA")),
                "ordem": _texto(pega(r, "ORDEM_VISITA", "ORDEM_DE_VISITA")),
            })
    finally:
        wb.close()
    return saida


def agenda_por_cliente(visitas: list) -> dict:
    """{chave do cliente -> visitas dele, na ordem do mes}."""
    agenda = defaultdict(list)
    for v in visitas:
        agenda[v["chave"]].append(v)
    for lista in agenda.values():
        lista.sort(key=lambda v: (v["data"] or dt.date.max,
                                  _numero(v["ordem"])))
    return dict(agenda)


def semanas_e_dias(visitas: list) -> tuple:
    """As caixinhas de SEMANA e DIA, com o que existe na rota."""
    semanas = sorted({v["semana"] for v in visitas if v["semana"]})
    dias = sorted({v["dia"] for v in visitas if v["dia"]},
                  key=lambda d: _numero(d))
    return semanas, dias


# ==========================================================================
# O HISTORICO POR FAMILIA
# ==========================================================================
# A pergunta que o vendedor faz na rua: "esse cliente compra freio?".
# Ela nao se responde pela BASE_CLIENTE, que e por cliente, nem pelo
# estoque, que e por produto. So se responde no ITEM DA NOTA - e a
# ftPedidos e item a item.
#
# Uma passada pela ftPedidos monta {cliente -> familia -> quanto}. Com
# isso a lista de clientes ganha duas leituras que valem dinheiro:
#
#   QUEM COMPRA ....... quanto da familia ja sai para ele, e ha quanto
#                       tempo. Serve para reposicao.
#   QUEM NAO COMPRA ... cliente ativo, que compra de outras familias,
#                       mas nunca levou aquela. E a oportunidade limpa:
#                       o cadastro ja existe, o limite ja existe, so
#                       falta oferecer.
#
# A DEVOLUCAO entra com o sinal dela: familia que so teve devolucao fica
# com valor negativo, e isso e informacao, nao erro.
DIAS_DO_HISTORICO = [90, 180, 365, 730]
DIAS_DO_HISTORICO_PADRAO = 365
TIPOS_DE_VENDA = ("VND", "VEA")
TIPO_DE_DEVOLUCAO = "DEV"


def compras_por_familia(caminho_tabela, hoje=None,
                        dias: int = DIAS_DO_HISTORICO_PADRAO) -> dict:
    """
    {cod do cliente -> {"familias": {familia: {...}}, "grupos": {...},
                        "total": R$, "ultima": data}}

    `dias` conta de HOJE para tras. O codigo do cliente vem da nota
    (D2_CLIENTE) sem a loja, que e como a BASE_CLIENTE tambem o guarda.
    """
    caminho_tabela = Path(caminho_tabela)
    hoje = hoje or dt.date.today()
    corte = hoje - dt.timedelta(days=max(1, int(dias or 1)))
    wb = load_workbook(caminho_tabela, read_only=True, data_only=True)
    try:
        descricoes = fam.descricoes_da_tabela(wb)
        if "ftPedidos" not in wb.sheetnames:
            return {"clientes": {}, "hoje": hoje, "dias": dias,
                    "linhas": 0, "sem_descricao": 0}
        cab, it = _cabecalho(wb["ftPedidos"])
        i_cli = _onde(cab, "D2_CLIENTE")
        i_pro = _onde(cab, "D2_COD")
        i_tipo = _onde(cab, "TIPO")
        i_nf = _onde(cab, "DATA_NF")
        i_dev = _onde(cab, "DATA_DEV")
        i_em = _onde(cab, "D2_EMISSAO")
        i_val = _onde(cab, "VALOR TOTAL", "VALOR_TOTAL")
        i_qtd = _onde(cab, "D2_QUANT")
        if i_cli is None or i_pro is None:
            return {"clientes": {}, "hoje": hoje, "dias": dias,
                    "linhas": 0, "sem_descricao": 0}

        clientes: dict[str, dict] = {}
        contadas = 0
        sem_descricao = 0
        for r in it:
            tipo = _texto(r[i_tipo]).upper() if i_tipo is not None else "VND"
            if tipo not in TIPOS_DE_VENDA and tipo != TIPO_DE_DEVOLUCAO:
                continue
            d = (_data(r[i_nf] if i_nf is not None else None)
                 or _data(r[i_dev] if i_dev is not None else None)
                 or _data(r[i_em] if i_em is not None else None))
            if d is None or d < corte or d > hoje:
                continue
            cod = _texto(r[i_cli])
            produto = _texto(r[i_pro])
            if not cod or not produto:
                continue
            desc = descricoes.get(produto.upper(), "")
            if not desc:
                sem_descricao += 1
            familia, grupo, _ = fam.classificar(desc)
            valor = _numero(r[i_val]) if i_val is not None else 0.0
            qtd = _numero(r[i_qtd]) if i_qtd is not None else 0.0
            if tipo == TIPO_DE_DEVOLUCAO:
                valor, qtd = -abs(valor), -abs(qtd)
            c = clientes.get(cod)
            if c is None:
                c = clientes[cod] = {"familias": {}, "grupos": {},
                                     "total": 0.0, "ultima": None,
                                     "skus": set()}
            c["total"] += valor
            c["skus"].add(produto)
            if c["ultima"] is None or d > c["ultima"]:
                c["ultima"] = d
            for onde_, chave in (("familias", familia), ("grupos", grupo)):
                alvo = c[onde_].get(chave)
                if alvo is None:
                    alvo = c[onde_][chave] = {"valor": 0.0, "quantidade": 0.0,
                                              "ultima": None, "skus": set()}
                alvo["valor"] += valor
                alvo["quantidade"] += qtd
                alvo["skus"].add(produto)
                if alvo["ultima"] is None or d > alvo["ultima"]:
                    alvo["ultima"] = d
            contadas += 1
    finally:
        wb.close()

    for c in clientes.values():
        c["skus"] = len(c["skus"])
        for onde_ in ("familias", "grupos"):
            for alvo in c[onde_].values():
                alvo["skus"] = len(alvo["skus"])
    return {"clientes": clientes, "hoje": hoje, "dias": dias,
            "linhas": contadas, "sem_descricao": sem_descricao,
            "produtos_com_descricao": len(descricoes),
            "arquivo": caminho_tabela}


COLUNAS_FAMILIA_CLI = [
    ("UF", "uf", 6, None),
    ("CIDADE", "cidade", 22, None),
    ("COD.", "cod_cliente", 12, None),
    ("RAZAO SOCIAL", "cliente", 38, None),
    ("SEGMENTO", "segmento", 24, None),
    ("COD VD", "cod_vendedor", 10, None),
    ("VENDEDOR", "vendedor", 26, None),
    ("ZONA", "zona", 22, None),
    ("COMPROU", "comprou_txt", 10, None),
    ("R$ NA FAMILIA", "valor_familia", 16, "#,##0.00"),
    ("SKUS DA FAMILIA", "skus_familia", 17, "#,##0"),
    ("ULTIMA DA FAMILIA", "ultima_familia", 19, "DD/MM/YYYY"),
    ("DIAS SEM A FAMILIA", "dias_familia", 19, "#,##0"),
    ("R$ TOTAL NO PERIODO", "valor_total", 21, "#,##0.00"),
    ("% DA FAMILIA", "perc_familia", 14, "#,##0.0"),
    ("LIM. DISP. R$", "limite_disponivel", 15, "#,##0.00"),
    ("CURVA", "curva", 8, None),
]


def montar_familia_do_cliente(oportunidade: list, compras: dict,
                              familia: str = "", grupo: str = "") -> list:
    """
    A lista de clientes com o que cada um comprou DAQUELA familia (ou
    daquele grupo, que e mais fino) no periodo.

    Sem familia nem grupo, a coluna mostra o total do cliente - que e o
    mesmo que dizer "comprou alguma coisa".
    """
    hoje = (compras or {}).get("hoje") or dt.date.today()
    dados = (compras or {}).get("clientes") or {}
    onde_ = "grupos" if grupo else "familias"
    alvo_nome = grupo or familia
    saida = []
    for c in (oportunidade or []):
        cod = _texto(c.get("cod_cliente"))
        reg = dados.get(cod) or {}
        if alvo_nome:
            item = (reg.get(onde_) or {}).get(alvo_nome) or {}
        else:
            item = {"valor": reg.get("total", 0.0), "skus": reg.get("skus", 0),
                    "ultima": reg.get("ultima")}
        valor = item.get("valor") or 0.0
        ultima = item.get("ultima")
        total = reg.get("total") or 0.0
        saida.append({
            "uf": c.get("uf", ""), "cidade": c.get("cidade", ""),
            "cod_cliente": cod, "cliente": c.get("cliente", ""),
            "segmento": c.get("segmento", ""),
            "cod_vendedor": c.get("cod_vendedor", ""),
            "vendedor": c.get("vendedor", ""), "zona": c.get("zona", ""),
            "comprou": bool(item),
            "comprou_txt": "SIM" if item else "NAO",
            "valor_familia": valor,
            "skus_familia": item.get("skus") or 0,
            "ultima_familia": ultima,
            "dias_familia": (hoje - ultima).days if ultima else None,
            "valor_total": total,
            "perc_familia": (valor / total * 100) if total else 0.0,
            "limite_disponivel": c.get("limite_disponivel", 0.0),
            "curva": c.get("curva", ""),
            # quem compra da BAP mas nunca levou ESTA familia e a
            # oportunidade limpa: o cadastro e o limite ja existem
            "oportunidade": bool(alvo_nome) and not item and total > 0,
        })
    saida.sort(key=lambda x: (-x["valor_familia"], x["cliente"]))
    return saida


def resumo_das_familias(compras: dict) -> list:
    """Uma linha por familia: quanto saiu e para quantos clientes."""
    dados = (compras or {}).get("clientes") or {}
    por_familia: dict[str, dict] = {}
    for reg in dados.values():
        for nome, item in (reg.get("familias") or {}).items():
            alvo = por_familia.get(nome)
            if alvo is None:
                alvo = por_familia[nome] = {"familia": nome, "valor": 0.0,
                                            "clientes": 0, "skus": 0}
            alvo["valor"] += item.get("valor") or 0.0
            alvo["clientes"] += 1
            alvo["skus"] = max(alvo["skus"], item.get("skus") or 0)
    total = sum(x["valor"] for x in por_familia.values()) or 1.0
    linhas = []
    for nome in fam.ORDEM_FAMILIA:
        if nome in por_familia:
            x = por_familia[nome]
            x["perc"] = x["valor"] / total * 100
            linhas.append(x)
    return linhas


def gravar_excel_familia(linhas: list, caminho, compras: dict = None,
                         alvo: str = "") -> Path:
    """A lista da tela em Excel, com uma aba RESUMO por familia."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    caminho = Path(caminho)
    colunas = COLUNAS_FAMILIA_CLI
    wb = Workbook()
    ws = wb.active
    ws.title = "CLIENTE POR FAMILIA"
    ws.append([t for t, _, _, _ in colunas])
    fundo = PatternFill("solid", fgColor="14375E")
    branco = Font(color="FFFFFF", bold=True, size=9)
    for i, (_, _, largura, _) in enumerate(colunas, start=1):
        ws.cell(1, i).fill = fundo
        ws.cell(1, i).font = branco
        ws.cell(1, i).alignment = Alignment(horizontal="center",
                                            wrap_text=True)
        ws.column_dimensions[ws.cell(1, i).column_letter].width = largura
    for linha in linhas:
        ws.append([linha.get(k) for _, k, _, _ in colunas])
    for j, (_, _, _, formato) in enumerate(colunas, start=1):
        if formato:
            for n in range(2, ws.max_row + 1):
                ws.cell(n, j).number_format = formato
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = (f"A1:{ws.cell(1, len(colunas)).column_letter}"
                              f"{ws.max_row}")

    wr = wb.create_sheet("RESUMO POR FAMILIA")
    wr.append(["FAMILIA", "FATURADO R$", "% DO TOTAL", "CLIENTES"])
    for i in range(1, 5):
        wr.cell(1, i).fill = fundo
        wr.cell(1, i).font = branco
    for r in resumo_das_familias(compras or {}):
        wr.append([r["familia"], r["valor"], r["perc"], r["clientes"]])
    for n in range(2, wr.max_row + 1):
        wr.cell(n, 2).number_format = "#,##0.00"
        wr.cell(n, 3).number_format = "#,##0.0"
    for col, largura in (("A", 20), ("B", 18), ("C", 13), ("D", 12)):
        wr.column_dimensions[col].width = largura

    wf = wb.create_sheet("FILTRO")
    dias = (compras or {}).get("dias") or DIAS_DO_HISTORICO_PADRAO
    for i, (rotulo, valor) in enumerate([
            ("Recorte", alvo or "(todas as familias)"),
            ("Periodo", f"os ultimos {dias} dias"),
            ("Clientes", f"{len(linhas):,}".replace(",", ".")),
            ("Fonte", "TABELA_BAP, aba ftPedidos - item a item"),
            ("Familia", "sai da DESCRICAO do produto (familia_nucleo.py)")],
            start=1):
        wf[f"A{i}"] = rotulo
        wf[f"A{i}"].font = Font(bold=True, size=9)
        wf[f"B{i}"] = valor
        wf[f"B{i}"].font = Font(size=9)
    wf.column_dimensions["A"].width = 22
    wf.column_dimensions["B"].width = 70
    wb.save(caminho)
    wb.close()
    return caminho


def nome_do_arquivo_de_familia(familia: str = "", hoje=None) -> str:
    hoje = hoje or dt.date.today()
    pedaco = re.sub(r"[^A-Z0-9]+", "_", (familia or "TODAS").upper()).strip("_")
    return f"CLIENTES_POR_FAMILIA_{pedaco}_{hoje:%Y%m%d}.xlsx"


def montar_rota(oportunidade: list, visitas: list, visao: str = VISAO_CLIENTE,
                semana: str = "", dia: str = "") -> list:
    """
    Junta a agenda do PLANNER com a base de oportunidade. Na visao de
    VISITA o cliente aparece uma vez por visita; na de CLIENTE, uma vez
    so, com os dias dele resumidos em tres colunas.
    """
    agenda = agenda_por_cliente(visitas)
    por_chave = {}
    for linha in oportunidade:
        por_chave[_texto(linha.get("chave"))] = linha
        por_chave.setdefault(
            _chave_do_cliente(linha.get("cod_cliente"), linha.get("loja")),
            linha)

    saida = []
    if _texto(visao) == VISAO_VISITA:
        for v in visitas:
            if semana and semana != TODOS and v["semana"] != semana:
                continue
            if dia and dia != TODOS and v["dia"] != dia:
                continue
            base = por_chave.get(v["chave"])
            if base is None:
                continue
            saida.append({**base, **{k: v[k] for k in
                                     ("semana", "dia", "dia_semana",
                                      "data", "ordem")}})
        saida.sort(key=lambda l: (l.get("data") or dt.date.max,
                                  _numero(l.get("ordem"))))
        return saida

    for linha in oportunidade:
        minhas = (agenda.get(_texto(linha.get("chave")))
                  or agenda.get(_chave_do_cliente(linha.get("cod_cliente"),
                                                  linha.get("loja")))
                  or [])
        if semana and semana != TODOS:
            minhas = [v for v in minhas if v["semana"] == semana]
        if dia and dia != TODOS:
            minhas = [v for v in minhas if v["dia"] == dia]
        if (semana and semana != TODOS) or (dia and dia != TODOS):
            if not minhas:
                continue        # com filtro de agenda, quem nao tem, sai
        dias = sorted({v["dia"] for v in minhas if v["dia"]},
                      key=lambda d: _numero(d))
        semanas = sorted({v["semana"] for v in minhas if v["semana"]})
        saida.append({**linha,
                      "visitas": len(minhas),
                      "dias": ", ".join(dias),
                      "semanas": ", ".join(semanas)})
    saida.sort(key=lambda l: (_texto(l.get("uf")), _texto(l.get("cidade")),
                              _texto(l.get("bairro")),
                              _texto(l.get("cliente"))))
    return saida


def colunas_da_rota(visao: str) -> list:
    """As colunas da lista, na ordem: a agenda na frente, a base atras."""
    corpo = [c for c in COLUNAS_OPORTUNIDADE]
    if _texto(visao) == VISAO_VISITA:
        return COLUNAS_ROTA_VISITA + corpo
    return corpo + COLUNAS_ROTA_CLIENTE


def nome_do_arquivo_de_rota(hoje=None) -> str:
    hoje = hoje or dt.date.today()
    return f"ANALITICO_ROTA_BAP_{hoje:%Y%m%d}.xlsx"


def gravar_excel_rota(linhas: list, caminho, visao: str = VISAO_CLIENTE,
                      filtro: str = "") -> Path:
    """A lista da tela em Excel, com uma aba FILTRO dizendo de onde veio."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    caminho = Path(caminho)
    colunas = colunas_da_rota(visao)
    wb = Workbook()
    ws = wb.active
    ws.title = "ROTA"
    ws.append([t for t, _, _, _ in colunas])
    fundo = PatternFill("solid", fgColor="14375E")
    branco = Font(color="FFFFFF", bold=True, size=9)
    for i, (_, _, largura, _) in enumerate(colunas, start=1):
        ws.cell(1, i).fill = fundo
        ws.cell(1, i).font = branco
        ws.cell(1, i).alignment = Alignment(horizontal="center",
                                            wrap_text=True)
        ws.column_dimensions[ws.cell(1, i).column_letter].width = largura
    for linha in linhas:
        ws.append([linha.get(k) for _, k, _, _ in colunas])
    for j, (_, _, _, formato) in enumerate(colunas, start=1):
        if formato:
            for n in range(2, ws.max_row + 1):
                ws.cell(n, j).number_format = formato
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = (f"A1:{ws.cell(1, len(colunas)).column_letter}"
                              f"{ws.max_row}")

    wf = wb.create_sheet("FILTRO")
    wf["A1"] = "De onde veio esta lista"
    wf["A1"].font = Font(bold=True, size=12, color="1F4E79")
    for i, (rotulo, valor) in enumerate([
            ("Visao", visao),
            ("Filtro", filtro or "(a rota inteira)"),
            ("Linhas", f"{len(linhas):,}".replace(",", ".")),
            ("Fonte da agenda", "PLANNER_BAP - a rota que ja foi gerada"),
            ("Fonte do resto", "a mesma base de oportunidade da aba 1")],
            start=3):
        wf[f"A{i}"] = rotulo
        wf[f"A{i}"].font = Font(bold=True, size=9)
        wf[f"B{i}"] = valor
        wf[f"B{i}"].font = Font(size=9)
    wf.column_dimensions["A"].width = 22
    wf.column_dimensions["B"].width = 70
    wb.save(caminho)
    wb.close()
    return caminho
