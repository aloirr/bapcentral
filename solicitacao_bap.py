# -*- coding: utf-8 -*-
"""
SOLICITACAO BAP na tela (09/10) - a aba "Solicitação BAP" do Farol de
Pedidos: o arquivo RELATORIOS/SOLICITACAO_BAP.xlsx com as abas dele, e a
TROCA DE LOJA DE COLETA.

Duplo clique num item de Solicitacao CD / Lojas / FRW:
  1. o item vai para a ProdutosExcluir NAQUELA loja (a proxima rodada do
     BAP Tools ja nao manda buscar la);
  2. a tela sugere outra loja DA MESMA CIDADE com estoque (ftEstoquePMZ da
     TABELA_BAP, menos o que ja esta prometido em solicitacao aberta e
     menos o que esta na ProdutosExcluir / FiliaisExcluir);
  3. escolhida a loja, gera a LINHA NOVA (aba de Lojas ou de CD, e uma por
     pedido na DETALHADO_PEDIDO) com STATUS "ABRIR SOLICITAÇÃO" e o CSV
     novo na pasta "Arquivos para Importar" (reversa de loja ou separacao de
     CD), com o numero na coluna CONTROLE.

As regras sao as do BAP Tools (bap_automation): as mesmas funcoes gravam as
linhas, as formulas e o CSV. Linha ja gravada NUNCA e alterada - so se
acrescenta. Antes de gravar, uma copia do arquivo vai para
BACKUP_RELATORIOS.
"""
from __future__ import annotations

import os
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

ARQUIVO = "SOLICITACAO_BAP.xlsx"
ABAS_TELA = ("Solicitacao Lojas", "Solicitacao CD", "Solicitacao FRW",
             "Solicitacao Manual", "DETALHADO_PEDIDO", "ProdutosExcluir",
             "FiliaisExcluir")
ABAS_TROCA = ("Solicitacao Lojas", "Solicitacao CD", "Solicitacao FRW")
STATUS_NOVO = "ABRIR SOLICITAÇÃO"


COLUNAS_NUM = ("QUANTIDADE", "DEMANDA_PEDIDO", "JA_SOLICITADO",
               "SALDO_A_SOLICITAR", "ESTOQUE_NA_ORIGEM")


def tipos_colunas(colunas, linhas) -> list:
    """Funcao pura: o tipo de cada coluna das abas da tela e do site. "num"
    nas colunas de quantidade; "data" em DATA quando toda celula preenchida e
    data (tem .year); "texto" no resto. A tela (bap_relatorios) e o robo
    (bap_automation.solicitacao_web) usam esta regra (RD-0020)."""
    colunas = list(colunas)
    i_data = colunas.index("DATA") if "DATA" in colunas else None
    saida = []
    for c in colunas:
        if c in COLUNAS_NUM:
            saida.append("num")
        elif c == "DATA" and all(
                hasattr(l[i_data], "year") for l in linhas
                if l[i_data] not in (None, "")):
            saida.append("data")
        else:
            saida.append("texto")
    return saida


def texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def chave(v) -> str:
    t = unicodedata.normalize("NFKD", texto(v))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", t.upper())


def numero(v) -> float:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def caminho(raiz) -> Path:
    return Path(raiz) / "RELATORIOS" / ARQUIVO


# ---------------------------------------------------------------- leitura
def ler(raiz) -> dict:
    """{aba: {"colunas": [...], "linhas": [[...], ...]}} so com as linhas
    que tem algum valor (o modelo vazio do fim da aba fica de fora)."""
    from openpyxl import load_workbook                  # noqa: PLC0415
    arq = caminho(raiz)
    saida = {}
    if not arq.exists():
        return saida
    wb = load_workbook(arq, read_only=True, data_only=True)
    try:
        for aba in ABAS_TELA:
            if aba not in wb.sheetnames:
                continue
            it = wb[aba].iter_rows(values_only=True)
            cab = [texto(c) for c in next(it, [])]
            while cab and not cab[-1]:
                cab.pop()
            linhas = []
            for r in it:
                r = list(r[:len(cab)]) + [None] * (len(cab) - len(r or ()))
                if any(v not in (None, "") for v in r) and not (
                        isinstance(r[0], str) and r[0].startswith("=")):
                    linhas.append([v if not (isinstance(v, str)
                                             and v.startswith("=")) else ""
                                   for v in r])
            saida[aba] = {"colunas": cab, "linhas": linhas}
    finally:
        wb.close()
    return saida


def _campo(d, linha, nome):
    i = d["colunas"].index(nome) if nome in d["colunas"] else None
    return linha[i] if i is not None and i < len(linha) else None


def item_da_linha(dados, aba, linha) -> dict:
    """O item de uma linha da aba de solicitacao (o que o duplo clique
    manda para a troca)."""
    d = dados[aba]
    return {"aba": aba,
            **{c: _campo(d, linha, c) for c in (
                "DATA", "HORA", "UF", "CIDADE", "COD_PRODUTO", "ID_PRODUTO",
                "COLETAR_EM", "FILIAL_DESTINO", "QUANTIDADE", "PEDIDOS",
                "SITUACAO_PEDIDO", "STATUS")}}


def excluidos(dados) -> tuple:
    """(filiais fora, pares (filial, produto) fora) - o produto pelo codigo
    ou pelo ID, sem espaco."""
    fil = {texto(l[0]) for l in (dados.get("FiliaisExcluir") or {}).get(
        "linhas", []) if l and texto(l[0])}
    pares = set()
    d = dados.get("ProdutosExcluir") or {}
    for l in d.get("linhas", []):
        f = texto(_campo(d, l, "Filial"))
        for c in ("Cód", "ID_PRODUTO"):
            p = chave(_campo(d, l, c))
            if f and p:
                pares.add((f, p))
    return fil, pares


def comprometido(dados) -> dict:
    """{(filial, produto): unidades} das solicitacoes ainda abertas (pedido
    EM ABERTO, sem ID) - o estoque que ja foi prometido."""
    saida = {}
    for aba, campo_id in (("Solicitacao Lojas", "ID_REVERSA"),
                          ("Solicitacao CD", "ID_SEPARACAO")):
        d = dados.get(aba) or {}
        for l in d.get("linhas", []):
            if texto(_campo(d, l, "SITUACAO_PEDIDO")).upper() != "EM ABERTO":
                continue
            if texto(_campo(d, l, campo_id)):
                continue
            k = (texto(_campo(d, l, "COLETAR_EM")),
                 chave(_campo(d, l, "COD_PRODUTO")))
            saida[k] = saida.get(k, 0.0) + numero(_campo(d, l, "QUANTIDADE"))
    return saida


# ------------------------------------------------------------ candidatos
def _filiais_e_estoque(raiz, produto_chaves: set) -> tuple:
    """(filiais {cod: (cd, cidade)}, estoque {filial: qtd}) da TABELA_BAP
    (Filiais e ftEstoquePMZ: QTD_TOTAL - QTD_SEPARADA) so do produto."""
    try:  # (05/11) o leitor rapido: com a fotografia, o estoque de agora
        from xlsx_rapido import load_workbook           # noqa: PLC0415
    except ImportError:
        from openpyxl import load_workbook              # noqa: PLC0415
    arq = Path(raiz) / "RELATORIOS" / "TABELA_BAP.xlsx"
    filiais, est = {}, {}
    wb = load_workbook(arq, read_only=True, data_only=True)
    try:
        it = wb["Filiais"].iter_rows(values_only=True)
        cab = [chave(c) for c in next(it, [])]
        i_f, i_cd, i_c = (cab.index("CODFILIAL"), cab.index("CDFILIAL"),
                          cab.index("CIDADE"))
        for r in it:
            if r and r[i_f] is not None:
                filiais[texto(r[i_f])] = (texto(r[i_cd]), texto(r[i_c]))
        it = wb["ftEstoquePMZ"].iter_rows(values_only=True)
        cab = [chave(c) for c in next(it, [])]

        def ix(*ns):
            return next((cab.index(n) for n in ns if n in cab), None)
        i_f, i_p, i_id = ix("FILIAL"), ix("PRODUTO"), ix("IDPRODUTO")
        i_q, i_s = ix("QTDTOTAL", "QTDE", "QTD"), ix("QTDSEPARADA")
        for r in it:
            if not r:
                continue
            if chave(r[i_p]) not in produto_chaves and (
                    i_id is None or chave(r[i_id]) not in produto_chaves):
                continue
            q = numero(r[i_q]) - (numero(r[i_s]) if i_s is not None else 0)
            f = texto(r[i_f])
            est[f] = est.get(f, 0.0) + max(q, 0.0)
    finally:
        wb.close()
    return filiais, est


def candidatos(raiz, item, dados=None) -> list:
    """As lojas (e o CD) DA MESMA CIDADE que podem atender o item, menos a
    de agora e as excluidas. Ordem do BAP Tools: CD, loja preferencial da
    cidade, depois as demais pelo maior disponivel."""
    import bap_automation as ba                         # noqa: PLC0415
    dados = dados or ler(raiz)
    prod = {chave(item.get("COD_PRODUTO")), chave(item.get("ID_PRODUTO"))}
    prod.discard("")
    filiais, est = _filiais_e_estoque(raiz, prod)
    fora_fil, fora_par = excluidos(dados)
    prom = comprometido(dados)
    atual = texto(item.get("COLETAR_EM"))
    cidade = chave(item.get("CIDADE"))
    qtd = numero(item.get("QUANTIDADE"))
    saida = []
    for f, (cd, cid) in filiais.items():
        if chave(cid) != cidade or f == atual or f in fora_fil:
            continue
        if f.startswith(ba.PREFIXO_FRW):
            continue                    # FRW: o BAP Tools ja olhou primeiro
        if any((f, p) in fora_par for p in prod):
            continue
        e = est.get(f, 0.0)
        if e <= 0:
            continue
        ja = sum(v for (ff, p), v in prom.items() if ff == f and p in prod)
        disp = max(e - ja, 0.0)
        rank = ba.rank_filial(f, item.get("CIDADE"))
        saida.append({"filial": f, "tipo": ba.NOME_RANK.get(rank, "LOJA"),
                      "rank": rank, "estoque": e, "comprometido": ja,
                      "disponivel": disp, "cabe": disp >= qtd - 1e-9,
                      "destino": cd or f})
    saida.sort(key=lambda c: (not c["cabe"], c["rank"], -c["disponivel"],
                              c["filial"]))
    return saida


# ----------------------------------------------------------------- troca
def trocar_coleta(raiz, item, nova: dict, agora=None) -> dict:
    """Grava a troca: ProdutosExcluir + linha nova (aba de Lojas ou CD e a
    DETALHADO_PEDIDO) + o CSV de importacao. Devolve o resumo."""
    import pandas as pd                                 # noqa: PLC0415
    from openpyxl import load_workbook                  # noqa: PLC0415
    import bap_automation as ba                         # noqa: PLC0415
    raiz = Path(raiz)
    arq = caminho(raiz)
    agora = agora or datetime.now()
    dados = ler(raiz)
    det = dados.get(ba.ABA_DETALHE) or {"colunas": [], "linhas": []}
    alvo = (texto(item.get("DATA")), texto(item.get("HORA")),
            chave(item.get("COD_PRODUTO")), texto(item.get("COLETAR_EM")))
    pedidos = [l for l in det["linhas"]
               if (texto(_campo(det, l, "DATA")), texto(_campo(det, l, "HORA")),
                   chave(_campo(det, l, "COD_PRODUTO")),
                   texto(_campo(det, l, "COLETAR_EM"))) == alvo]
    nova_f = texto(nova["filial"])
    tipo = nova["tipo"]
    forn = _fornecedor(raiz, item)
    base = {"DATA": agora.strftime("%d/%m/%Y"), "HORA": agora.strftime("%H:%M"),
            "CIDADE": texto(item.get("CIDADE")),
            "COD_PRODUTO": texto(item.get("COD_PRODUTO")),
            "ID_PRODUTO": texto(item.get("ID_PRODUTO")),
            "COLETAR_EM": nova_f, "TIPO_ORIGEM": tipo,
            "SITUACAO_PEDIDO": "EM ABERTO", "STATUS": ba.STATUS_PADRAO,
            "ESTOQUE_NA_ORIGEM": nova.get("estoque"),
            "MOTIVO": f"TROCA DE COLETA: sem o item na {alvo[3]} "
                      f"(foi para ProdutosExcluir)",
            "FORNECEDOR": forn, "FILIAL_DESTINO": texto(nova.get("destino"))}
    linhas = []
    if pedidos:
        for l in pedidos:
            r = dict(base)
            for c in ("NUM_PEDIDO", "DT_PEDIDO", "CLIENTE", "FILIAL_PEDIDO",
                      "QUANTIDADE", "DEMANDA_PEDIDO", "JA_SOLICITADO",
                      "SALDO_A_SOLICITAR"):
                r[c] = _campo(det, l, c)
            linhas.append(r)
    else:                       # sem detalhe: uma linha so com os pedidos
        for p in texto(item.get("PEDIDOS")).split("|") or [""]:
            r = dict(base)
            r.update({"NUM_PEDIDO": p.strip(), "QUANTIDADE": numero(
                item.get("QUANTIDADE")) if p == texto(item.get(
                    "PEDIDOS")).split("|")[0] else 0})
            linhas.append(r)
        linhas = [r for r in linhas if r["QUANTIDADE"]]
    novas = pd.DataFrame(linhas)
    for c in ba.COLUNAS_SOLICITACAO:
        if c not in novas.columns:
            novas[c] = None
    novas = novas[ba.COLUNAS_SOLICITACAO + ["FORNECEDOR", "FILIAL_DESTINO"]]

    # o arquivo tem de poder ser gravado (ninguem com ele aberto no Excel)
    try:
        with open(arq, "r+b"):
            pass
    except PermissionError as e:
        raise PermissionError(
            f"{ARQUIVO} está aberto no Excel. Feche e tente de novo.") from e
    bk = raiz / "SISTEMA BAP" / "BACKUP_RELATORIOS" / "SOLICITACAO_BAP"
    bk.mkdir(parents=True, exist_ok=True)
    copia = bk / f"SOLICITACAO_BAP_antes_troca_{agora:%Y%m%d_%H%M%S}.xlsx"
    shutil.copy2(arq, copia)

    # o CSV antes da planilha, para atrelar o numero (como o BAP Tools)
    csvs = ba.gerar_csvs_importacao(novas, False)
    wb = load_workbook(arq)
    try:
        aba_nova = None
        for nome_aba, tipos in ba.ABAS_SOLICITACAO.items():
            if nome_aba == ba.ABA_DETALHE or not tipos or tipo not in tipos:
                continue
            resumo = ba.resumir_para_solicitacao(novas, nome_aba, tipos)
            if "SITUACAO_PEDIDO" in resumo.columns:
                resumo["SITUACAO_PEDIDO"] = "EM ABERTO"
            if "CONTROLE_SEP_LOJA" in resumo.columns:
                resumo["CONTROLE_SEP_LOJA"] = [
                    csvs["numeros"]["loja"].get(c, "") for c in resumo["CIDADE"]]
            if "CONTROLE_SEP_CD" in resumo.columns:
                resumo["CONTROLE_SEP_CD"] = [
                    csvs["numeros"]["cd"].get(ba.texto(f), "")
                    for f in resumo["COLETAR_EM"]]
            ba.acrescentar_no_resumo(wb, nome_aba, resumo)
            aba_nova = nome_aba
        modelos = ba.formulas_da_coletas(wb)
        ba.acrescentar_na_aba(wb, ba.ABA_DETALHE, novas, modelos)
        # a loja antiga: ProdutosExcluir (acrescenta, nunca altera)
        ba.garantir_abas_de_exclusao(wb, None)
        ws = wb[ba.ABA_PRODUTOS_EXCLUIR]
        cab = ba.mapear_cabecalhos(ws, 1)
        lin = ba.ultima_linha_com_dados(ws, 1) + 1
        for titulo, valor in (("Filial", alvo[3]), ("Forn", forn),
                              ("Cód", texto(item.get("COD_PRODUTO"))),
                              ("ID_PRODUTO", texto(item.get("ID_PRODUTO")))):
            c = cab.get(ba.normalizar(titulo))
            if c:
                ws.cell(lin, c).value = valor
        try:
            wb.calculation.fullCalcOnLoad = True
        except Exception:                               # noqa: BLE001
            pass
        tmp = arq.with_name(f"~troca_{os.getpid()}_{ARQUIVO}")
        wb.save(tmp)
    finally:
        wb.close()
    os.replace(tmp, arq)
    try:                                 # as formulas ja calculadas no arquivo
        ba.recalcular_com_excel(arq, ARQUIVO)
    except Exception:                                   # noqa: BLE001
        pass
    return {"aba": aba_nova, "linhas_detalhe": len(novas),
            "pedidos": sorted({texto(p) for p in novas["NUM_PEDIDO"] if p}),
            "csv": csvs.get("arquivos", []), "pasta_csv": csvs.get("pasta"),
            "excluido": (alvo[3], texto(item.get("COD_PRODUTO"))),
            "backup": str(copia)}


def _fornecedor(raiz, item) -> str:
    """O codigo do fornecedor (980, 7980...) pela ProdutosBAP da
    TABELA_BAP."""
    from openpyxl import load_workbook                  # noqa: PLC0415
    alvo = {chave(item.get("COD_PRODUTO")), chave(item.get("ID_PRODUTO"))}
    alvo.discard("")
    wb = load_workbook(Path(raiz) / "RELATORIOS" / "TABELA_BAP.xlsx",
                       read_only=True, data_only=True)
    try:
        if "ProdutosBAP" not in wb.sheetnames:
            return ""
        it = wb["ProdutosBAP"].iter_rows(values_only=True)
        cab = [chave(c) for c in next(it, [])]
        i_id, i_f, i_c = (cab.index("IDPRODUTO"), cab.index("FORNECEDOR"),
                          cab.index("CODPRODUTO"))
        for r in it:
            if r and (chave(r[i_id]) in alvo or chave(r[i_c]) in alvo):
                return texto(r[i_f]).split("-")[0].strip()
    finally:
        wb.close()
    return ""
