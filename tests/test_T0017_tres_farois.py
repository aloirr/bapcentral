"""T-0017, entregas 3 a 5: Farol de Pedidos (pv_pedidos), de Entregas
(pl_entregas) e de Visita (vc_visitas) no pacote da web (forma "farol",
contrato 10.1 de .coord/contratos/relatorio.md).

Regras citadas:
- RN-GER-006: estado do faturamento = filial da nota (Pedidos); fretes,
  Planner e carteira = UF do cliente (Entregas pela coluna UF; Visita não
  tem a UF do cliente e vai sem recortes, com aviso);
- RN-GER-007: hoje fora do DU (o Farol de Visita não cobra o arquivo de
  hoje) e data de hoje no fuso America/Manaus.

Junta os testes do robô (bap_automation) e do modulo-farois
(relatorios_nucleo), sem casos repetidos. O teste antigo que só conferia o
texto da chamada no fonte foi trocado por um de comportamento: pasta de
visitas fictícia em tmp_path, sem o arquivo de hoje.

Dados 100% fictícios (sem cliente, CNPJ, telefone ou nome de pessoa real).
"""
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import bap_automation as ba
import relatorios_nucleo as rn

HOJE = date(2026, 11, 24)                 # terça-feira, NOV/2026
AVISO_SEM_ESTADO = "Sem filtro por estado: os cartões mostram a BAP inteira."
COLS_FRETE = ["UF", "REGIÃO", "NOTAS", "VALOR NF", "FRETE R$", "% S/ NOTA",
              "FRETE/NOTA"]


# ------------------------------------------------------------------ fixture
def _kpis_de(linhas):
    """Cartão fictício: contagem de linhas."""
    return [{"rotulo": "Pedidos", "valor": str(len(linhas)), "cor": "ok"}]


def _tabela(titulo, linhas, mes=None, extra_filtros=()):
    """linhas: (MÊS, FILIAL[, UF do cliente])."""
    colunas = [{"nome": n, "tipo": "texto"}
               for n in ("MÊS", "FILIAL", "VENDEDOR", "UF")]
    corpo = [[m, f, "Vendedor 01", (u[0] if u else "XX")]
             for m, f, *u in linhas]
    filtros = list(extra_filtros)
    if mes:
        filtros.insert(0, {"coluna": "MÊS", "padrao": mes})
    return {"titulo": titulo, "colunas": colunas, "linhas": corpo,
            "filtros": filtros, "kpis_de": _kpis_de,
            "edicao": {"campos": ["x"]}}


def _farol(titulo, tabela, blocos=None, **extra):
    r = {"titulo": titulo, "kpis": [{"rotulo": "Pedidos", "valor": "3"}],
         "tabelas": [tabela], "painel": {"blocos": blocos or []},
         "insights_painel": [["info", "Sem nome de cliente."]], "avisos": [],
         "editar": lambda *a: None, "abrir": "RELATORIOS/x.xlsx",
         "detalhe_pedido": lambda *a: None}
    r.update(extra)
    return r


def _bloco_frete(colunas):
    return {"tipo": "tabela", "titulo": "Frete por estado · NOV/26",
            "colunas": [{"nome": c, "tipo": "texto"} for c in colunas],
            "linhas": [["AM", "NORTE", 3, 100.0, 5.0, 5.0, 1.6]],
            "total": ["TOTAL", "", 3, 100.0, 5.0, 5.0, 1.6],
            "editar": "x", "row": 0, "col": 1, "colspan": 2}


def _valores(recortes):
    return {u: v["kpis"][0]["valor"] for u, v in recortes.items()}


# --------------------------------------------------------- os quatro faróis
def test_RN_GER_006_FAROIS_WEB_tem_os_quatro_farois_com_fonte_e_tabela():
    """Os 4 faróis vão ao site, cada um com a base do "baixado em". Tabela
    de recorte por estado em todos, menos a Visita (RN-GER-006: nenhuma
    tabela da Visita traz a UF do cliente)."""
    assert set(ba.FAROIS_WEB) == {"pl_inadimplencia", "pv_pedidos",
                                  "pl_entregas", "vc_visitas"}
    for rid in ba.FAROIS_WEB:
        assert rid in ba._FONTE_BAIXADO_WEB
    assert ba._TABELA_RECORTE_WEB == {"pl_inadimplencia": "Títulos",
                                      "pv_pedidos": "Pedidos",
                                      "pl_entregas": "Entregas"}
    # a coluna e a regra da UF: filial da nota no Pedidos, UF do cliente no
    # Entregas (a mesma do uf_linhas)
    assert ba._UF_LINHAS_WEB[("pv_pedidos", "Pedidos")] == ("FILIAL",
                                                            "filial")
    assert ba._UF_LINHAS_WEB[("pl_entregas", "Entregas")] == ("UF", "uf")


def test_RN_GER_006_pacote_com_tres_farois_um_com_erro_nao_derruba():
    def montado(titulo, tab):
        return _farol(titulo, _tabela(tab, [("NOV/26", "MANAUS")],
                                      mes="NOV/26"))
    res = {"pv_pedidos": montado("Farol de Pedidos", "Pedidos"),
           "pl_entregas": {"erro_montagem": "KeyError"},
           "vc_visitas": montado("Farol de Visita", "Por vendedor")}
    p = ba.montar_pacote_web(res, 2026, 11, raiz=Path("/nao/existe"))
    assert set(p["relatorios"]) == {"pv_pedidos", "vc_visitas"}
    for v in p["relatorios"].values():
        assert v["forma"] == "farol" and v["baixado_em"] is None
    json.dumps(p, allow_nan=False)


# ------------------------------------------------------------------ Pedidos
def test_RN_GER_006_pedidos_estado_pela_filial_da_nota_so_do_mes_do_farol():
    """Os cartões por estado partem do mesmo escopo do total (filtro MÊS);
    o padrão SITUAÇÃO = EM ABERTO é só visão da tela e não corta; a soma dos
    estados fecha o total do mês."""
    t = _tabela("Pedidos", [("NOV/26", "MANAUS"), ("NOV/26", "MANAUS"),
                            ("NOV/26", "BELÉM"), ("OUT/26", "BELÉM"),
                            ("OUT/26", "SÃO LUIS")], mes="NOV/26",
                extra_filtros=[{"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}])
    rec = ba.recortes_farol_por_uf(_farol("Farol de Pedidos", t), "Pedidos")
    assert _valores(rec) == {"AM": "2", "PA": "1"}
    assert sum(int(v) for v in _valores(rec).values()) == 3


# Pedidos conforme o contrato §10.7.3 (lista escrita aqui, à mão: nome, tipo,
# oculta). Dados fictícios.
_PED_COLS = (
    ("DT. PED", "dia", 0), ("FATURAR ATÉ", "dia", 0), ("PEDIDO", "texto", 0),
    ("PED. MÁX.", "texto", 0), ("CÓD.", "texto", 0),
    ("RAZÃO SOCIAL", "texto", 0), ("FANTASIA", "texto", 0),
    ("UF", "texto", 0), ("CIDADE", "texto", 0), ("LIMITE", "moeda", 0),
    ("DISP.", "moeda", 0), ("ATRASO", "moeda", 0), ("VOL.", "num", 0),
    ("R$ TABELA", "moeda", 0), ("R$ VENDA", "moeda", 0),
    ("% DESC.", "pct1", 0), ("SLA", "int", 0), ("% ATENDIDO", "pct", 0),
    ("ANÁLISE CRÉDITO", "texto", 0), ("COND. PAGTO", "texto", 0),
    ("SITUAÇÃO", "texto", 0), ("FILIAL", "texto", 0), ("PRAZO", "texto", 0),
    ("VENDEDOR", "texto", 0), ("NF", "texto", 0), ("DT. NF", "dia", 0),
    ("R$ TABELA CHEIA", "moeda", 1), ("CÓD. AUTORIZAÇÃO", "texto", 1),
    ("AUTORIZADO POR", "texto", 1), ("MÊS", "texto", 1),
    ("ENTREGUE EM", "dia", 1), ("PRODUTO", "texto", 1), ("CHAVE", "texto", 1))
_GERAR_COLS = (("DATA", "dia"), ("UF", "texto"), ("CIDADE", "texto"),
               ("PEDIDOS", "texto"), ("FORN.", "texto"),
               ("CÓD. PROD.", "texto"), ("DESCRIÇÃO", "texto"),
               ("QTD", "num"), ("COLETAR EM", "texto"),
               ("FILIAL DEST.", "texto"))
_ANALITICO_COLS = (
    ("PEDIDO", "texto", 0), ("DATA", "dia", 0), ("CIDADE", "texto", 0),
    ("FILIAL", "texto", 0), ("FORN.", "texto", 0), ("CÓD. PROD.", "texto", 0),
    ("DESCRIÇÃO", "texto", 0), ("QTD", "num", 0), ("EST. FRW", "num", 0),
    ("PEDIDOS ANTES", "num", 0), ("DISP. P/ ESTE", "num", 0),
    ("ATENDIDO", "num", 0), ("FALTA", "num", 0), ("CLIENTE", "texto", 0),
    ("FILIAL BAP", "texto", 1), ("VALOR FALTANTE", "moeda", 0))


def _cols(lista):
    saida = []
    for n, tp, *o in lista:
        c = {"nome": n, "tipo": tp}
        if o and o[0]:
            c["oculta"] = True
        if n == "SLA":
            c["chip"] = rn.CHIP_SLA()
        if n == "% ATENDIDO":
            c["barra"] = rn.BARRA_ATENDIDO
        saida.append(c)
    return saida


def _pedidos_conforme():
    """A tabela Pedidos do PC no formato do contrato, com as 3 juntas, a
    edição da autorização (grava) e um pedido fictício de MANAUS."""
    nomes = [c[0] for c in _PED_COLS]
    ln = [None] * len(nomes)
    for n, v in (("DT. PED", date(2026, 11, 3)), ("PEDIDO", "912345"),
                 ("CÓD.", "900001"), ("RAZÃO SOCIAL",
                                      "12345678000190 CLIENTE FICTICIO"),
                 ("FANTASIA", "CLIENTE FICTICIO"), ("UF", "AM"),
                 ("CIDADE", "MANAUS"), ("R$ VENDA", 100.0), ("SLA", 2),
                 ("% ATENDIDO", 100.0), ("SITUAÇÃO", "EM ABERTO"),
                 ("FILIAL", "MANAUS"), ("VENDEDOR", "Vendedor 01"),
                 ("MÊS", "NOV/26"), ("CHAVE", "x1")):
        ln[nomes.index(n)] = v

    def junta(quadro, titulo, cols, liga):
        return {"titulo": quadro, "liga": liga, "mostrar": [],
                "tabela": {"titulo": titulo, "colunas": _cols(cols),
                           "linhas": [], "tons": [], "filtros": []}}
    return {
        "titulo": "Pedidos", "colunas": _cols(_PED_COLS), "linhas": [ln],
        "tons": [""], "kpis_de": _kpis_de, "enxuta": True,
        "filtros": [{"coluna": "MÊS", "padrao": "NOV/26", "oculto": True},
                    {"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}],
        "recortes": [("Mais de 4 dias", lambda l: (l[16] or 0) > 4)],
        "edicao": {"arquivo": "RELATORIOS/_AUTORIZACOES", "campos": ["x"]},
        "detalhe": True,
        "juntas": [
            junta("Gerar ID de separação CD", "Gerar separação CD",
                  _GERAR_COLS, ("PEDIDOS", "PEDIDO", "|")),
            junta("Gerar reversa de lojas", "Gerar reversa de lojas",
                  _GERAR_COLS, ("PEDIDOS", "PEDIDO", "|")),
            junta("Analítico por pedido", "Analítico produto",
                  _ANALITICO_COLS, ("PEDIDO", "PEDIDO", None))]}


def _chaves(o, achadas=None):
    """Todas as chaves de dict, em qualquer nível."""
    achadas = set() if achadas is None else achadas
    if isinstance(o, dict):
        for k, v in o.items():
            achadas.add(k)
            _chaves(v, achadas)
    elif isinstance(o, list):
        for v in o:
            _chaves(v, achadas)
    return achadas


def test_RN_GER_006_pedidos_com_tabelas_sem_acao_com_faixa_e_vendedor(
        tmp_path):
    """Regra nova (T-0017, entregas 3 a 5, contrato §10.7): o Farol de
    Pedidos leva `tabelas` (todas as abas do PC), sem nenhuma ação que
    grava (autorização, Ver pedido, Editar no Excel, troca de coleta);
    cartões em faixa e nome de vendedor como antes."""
    r = _farol("Farol de Pedidos", _pedidos_conforme(), kpis_faixa=True,
               blocos=[{"tipo": "hbarras",
                        "titulo": "Pedidos em aberto por vendedor (R$)",
                        "rotulos": ["Vendedor 01"], "valores": [10.0],
                        "formato": "moeda"},
                       {"tipo": "tabela", "titulo": "outra", "colunas": [],
                        "linhas": []}])
    # raiz sem SOLICITACAO_BAP.xlsx: a aba Solicitação BAP não vai, sem aviso
    s = ba.selecionar_farol_web("pv_pedidos", r, raiz=tmp_path)
    assert s["forma"] == "farol" and s["kpis_faixa"] is True
    assert [t["titulo"] for t in s["tabelas"]] == ["Pedidos"]
    ped = s["tabelas"][0]
    assert [j["titulo"] for j in ped["juntas"]] == [
        "Gerar ID de separação CD", "Gerar reversa de lojas",
        "Analítico por pedido"]
    assert len(ped["linhas"]) == 1
    # RN-GER-011: o CNPJ sai do nome; o código fica
    nomes = [c["nome"] for c in ped["colunas"]]
    assert ped["linhas"][0][nomes.index("RAZÃO SOCIAL")] == "CLIENTE FICTICIO"
    assert ped["linhas"][0][nomes.index("CÓD.")] == "900001"
    # nenhuma ação que grava, em nenhum nível
    acoes = {"editar", "abrir", "edicao", "detalhe", "detalhe_pedido",
             "kpis_de", "total_de", "totais_por", "recortes",
             "solicitacao_bap", "garantia", "importar_preenchidos",
             "ordem_exportar", "cores_celulas", "so_exportar"}
    assert sorted(acoes & _chaves(s["tabelas"])) == []
    assert sorted(acoes & set(s)) == ["recortes"]   # o de cima é por estado
    assert [k for k in _chaves(s) if k.startswith("_")] == []
    # Pedidos é `enxuta` no PC: sem recortes na tela, sem recortes no site
    assert "recortes_linhas" not in ped
    # nome de vendedor VAI (D1); bloco tabela não é do Farol de Pedidos
    assert [b["tipo"] for b in s["painel"]["blocos"]] == ["hbarras"]
    assert "Vendedor 01" in json.dumps(s["painel"], ensure_ascii=False)
    assert ped["linhas"][0][nomes.index("VENDEDOR")] == "Vendedor 01"
    assert set(s["recortes"]) == {"AM"}
    assert ped["uf_linhas"] == ["AM"]


def test_RN_GER_006_pedidos_bloco_frete_nao_entra():
    t = _tabela("Pedidos", [("NOV/26", "MANAUS")], mes="NOV/26")
    r = _farol("Farol de Pedidos", t, blocos=[_bloco_frete(COLS_FRETE)])
    assert ba.selecionar_farol_web("pv_pedidos", r)["painel"]["blocos"] == []


# ----------------------------------------------------------------- Entregas
def test_RN_GER_006_entregas_estado_pela_UF_do_cliente_nao_pela_filial():
    """Frete = UF do cliente: a nota da filial MANAUS entregue no MA conta
    MA; linha de outro mês fica fora; soma dos estados = total do mês."""
    t = _tabela("Entregas", [("NOV/26", "MANAUS", "MA"),
                             ("NOV/26", "MANAUS", "MA"),
                             ("NOV/26", "BELÉM", "AM"),
                             ("OUT/26", "BELÉM", "PA")], mes="NOV/26")
    s = ba.selecionar_farol_web("pl_entregas", _farol("Farol de Entregas", t))
    assert _valores(s["recortes"]) == {"MA": "2", "AM": "1"}
    assert sum(int(v) for v in _valores(s["recortes"]).values()) == 3
    assert "kpis_faixa" not in s
    assert AVISO_SEM_ESTADO not in s["avisos"]


def test_RN_GER_006_entregas_leva_frete_por_estado_sem_edicao():
    t = _tabela("Entregas", [("NOV/26", "MANAUS", "AM"),
                             ("NOV/26", "MANAUS", "MA")], mes="NOV/26")
    r = _farol("Farol de Entregas", t, blocos=[_bloco_frete(COLS_FRETE)])
    s = ba.selecionar_farol_web("pl_entregas", r)
    blocos = s["painel"]["blocos"]
    assert [b["tipo"] for b in blocos] == ["tabela"]
    assert blocos[0]["linhas"] == [["AM", "NORTE", 3, 100.0, 5.0, 5.0, 1.6]]
    assert blocos[0]["total"] == ["TOTAL", "", 3, 100.0, 5.0, 5.0, 1.6]
    assert "editar" not in blocos[0]            # a edição NÃO vai
    assert set(s["recortes"]) == {"AM", "MA"}


def _entrega(uf, dnf, etapa, valor):
    """Entrega fictícia do ACOMPANHAMENTO_POS_VENDA (sem pessoa real)."""
    return {"filial": "0101002", "nf": f"{dnf:%m%d}{uf}{int(valor)}",
            "data_nf": dnf, "situacao": "NO PRAZO", "etapa": etapa, "uf": uf,
            "cidade": "CIDADE FICTICIA", "cliente": "CLIENTE FICTICIO 01",
            "valor": valor, "transportadora": "", "responsavel": "",
            "cidade_filial": "MANAUS", "chave": ""}


def _farol_entregas(tmp_path, entregas):
    """O Farol de Entregas de verdade (relatorios_nucleo.entregas) com
    entregas fictícias; devolve o relatório, a tabela Entregas e os índices
    das colunas UF e MÊS."""
    ctx = rn.Contexto(tmp_path, hoje=HOJE, params={"ANO": "2026", "MÊS": "11"})
    ctx._b["posvenda"] = {"existe": True, "devolucoes": [],
                          "entregas": entregas}
    ctx._b["tabela"] = {"itens": []}
    r = rn.entregas(ctx)
    t = next(t for t in r["tabelas"] if t["titulo"] == "Entregas")
    n = [c["nome"] for c in t["colunas"]]
    return r, t, n.index("UF"), n.index("MÊS")


def _pend(kpis):
    k = next(k for k in kpis if k["rotulo"] == "Pendências anteriores")
    return k["valor"], k["detalhe"]


def _no_mes(t, im, uf=None, iu=None):
    return [l for l in t["linhas"]
            if l[im] == "NOV/26" and (uf is None or l[iu] == uf)]


def test_RN_GER_006_entregas_pendencias_anteriores_por_estado(tmp_path):
    """(a) Pendências anteriores seguem o FILTRO de UF da tela (UF do
    cliente), inclusive em estado sem nota no mês (RR); a soma dos estados
    = o cartão da BAP."""
    r, t, iu, im = _farol_entregas(tmp_path, [
        _entrega("AM", date(2026, 11, 5), "ENTREGUE", 10.0),
        _entrega("PA", date(2026, 11, 6), "ENTREGUE", 20.0),
        _entrega("AM", date(2026, 10, 5), "EM ROTA", 1.0),     # pendentes
        _entrega("AM", date(2026, 10, 6), "EM ROTA", 2.0),
        _entrega("PA", date(2026, 10, 7), "EM ROTA", 4.0),
        _entrega("RR", date(2026, 10, 9), "EM ROTA", 16.0),    # RR sem nota em NOV
        _entrega("PA", date(2026, 10, 8), "ENTREGUE", 8.0)])   # concluída
    assert _pend(r["kpis"]) == ("4", "R$ 23 · meses anteriores")
    por_uf = {uf: _pend(rn.chamar_kpis_de(
        t["kpis_de"], _no_mes(t, im, uf, iu), {iu: uf}))
        for uf in ("AM", "PA", "RR")}
    assert por_uf == {"AM": ("2", "R$ 3 · meses anteriores"),
                      "PA": ("1", "R$ 4 · meses anteriores"),
                      "RR": ("1", "R$ 16 · meses anteriores")}
    assert sum(int(v) for v, _ in por_uf.values()) == 4


def test_RN_GER_006_entregas_pendencias_mes_de_um_estado_so(tmp_path):
    """(b) Mês só com notas do AM e filtro AM: só as pendências do AM (as
    linhas visíveis são todas as do mês, e mesmo assim não vira o total)."""
    r, t, iu, im = _farol_entregas(tmp_path, [
        _entrega("AM", date(2026, 11, 5), "ENTREGUE", 10.0),
        _entrega("AM", date(2026, 10, 5), "EM ROTA", 1.0),
        _entrega("PA", date(2026, 10, 7), "EM ROTA", 4.0)])
    assert _pend(r["kpis"]) == ("2", "R$ 5 · meses anteriores")
    assert _no_mes(t, im, "AM", iu) == _no_mes(t, im)
    assert _pend(rn.chamar_kpis_de(t["kpis_de"], _no_mes(t, im, "AM", iu),
                                   {iu: "AM"})) == ("1", "R$ 1 · meses anteriores")


def test_RN_GER_006_entregas_pendencias_sem_filtro_de_UF_e_total_BAP(tmp_path):
    """(c) Sem filtro, com {} e com filtro de outra coluna (MÊS): o total da
    BAP, igual a antes da T-0017; chamada direta sem `filtro` também."""
    r, t, iu, im = _farol_entregas(tmp_path, [
        _entrega("AM", date(2026, 11, 5), "ENTREGUE", 10.0),
        _entrega("AM", date(2026, 10, 5), "EM ROTA", 1.0),
        _entrega("PA", date(2026, 10, 7), "EM ROTA", 4.0)])
    total = ("2", "R$ 5 · meses anteriores")
    assert _pend(r["kpis"]) == total
    linhas = _no_mes(t, im)
    for filtro in (None, {}, {im: "NOV/26"}):
        assert _pend(rn.chamar_kpis_de(t["kpis_de"], linhas, filtro)) == total
    assert _pend(t["kpis_de"](linhas)) == total


def test_RN_GER_006_chamar_kpis_de_sem_parametro_recebe_so_as_linhas():
    """(d) kpis_de sem o parâmetro `filtro` (todas, menos a de Entregas)
    recebe só as linhas, com ou sem filtro, como antes; com o parâmetro,
    recebe o filtro."""
    chamadas = []

    def sem(ls):
        chamadas.append(ls)
        return [{"rotulo": "x", "valor": str(len(ls))}]
    for filtro in (None, {}, {7: "AM"}):
        assert rn.chamar_kpis_de(sem, [[1], [2]], filtro)[0]["valor"] == "2"
    assert chamadas == [[[1], [2]]] * 3
    assert rn.chamar_kpis_de(lambda ls, filtro=None: filtro, [[1]],
                             {7: "AM"}) == {7: "AM"}
    # e a kpis_de real de um farol sem o parâmetro (fixture do Pedidos)
    t = _tabela("Pedidos", [("NOV/26", "MANAUS"), ("NOV/26", "BELÉM")])
    assert rn.chamar_kpis_de(t["kpis_de"], t["linhas"], {1: "MANAUS"}) == \
        _kpis_de(t["linhas"])


def _kjs(ks):
    return json.loads(json.dumps(ba._para_json(ks), ensure_ascii=False))


_ENTREGAS_PEND = [
    _entrega("AM", date(2026, 11, 5), "ENTREGUE", 10.0),
    _entrega("PA", date(2026, 11, 6), "ENTREGUE", 20.0),
    _entrega("PA", date(2026, 11, 7), "EM ROTA", 30.0),
    _entrega("AM", date(2026, 10, 5), "EM ROTA", 1.0),     # pendentes
    _entrega("AM", date(2026, 10, 6), "EM ROTA", 2.0),
    _entrega("PA", date(2026, 10, 7), "EM ROTA", 4.0),
    _entrega("PA", date(2026, 10, 8), "ENTREGUE", 8.0)]    # concluída


def test_RN_GER_006_entregas_pendencias_anteriores_por_UF_bate_com_o_pc(
        tmp_path):
    """Regra nova (RD-0019; `_KPIS_SO_BAP_WEB` saiu): no site, o recorte
    por estado do Entregas traz "Pendências anteriores" daquela UF, e cada
    cartão do estado é o que o PC mostra com o filtro de UF (kpis_de das
    linhas do mês da UF, filtro={coluna UF: UF})."""
    assert not hasattr(ba, "_KPIS_SO_BAP_WEB")
    r, t, iu, im = _farol_entregas(tmp_path, _ENTREGAS_PEND)
    s = ba.selecionar_farol_web("pl_entregas", r, raiz=tmp_path)
    assert sorted(s["recortes"]) == ["AM", "PA"]
    for uf, v in s["recortes"].items():
        pc = rn.chamar_kpis_de(t["kpis_de"], _no_mes(t, im, uf, iu), {iu: uf})
        assert v["kpis"] == _kjs(pc), uf
    assert _pend(s["recortes"]["AM"]["kpis"]) == ("2",
                                                  "R$ 3 · meses anteriores")
    assert _pend(s["recortes"]["PA"]["kpis"]) == ("1",
                                                  "R$ 4 · meses anteriores")
    # o total da BAP segue no topo, e a soma dos estados fecha com ele
    assert _pend(s["kpis"]) == ("3", "R$ 7 · meses anteriores")
    assert sum(int(_pend(v["kpis"])[0]) for v in s["recortes"].values()) == 3


def test_RN_GER_006_entregas_estado_so_com_pendencia_tambem_aparece(
        tmp_path):
    """Estado sem nota no mês, mas com pendência de mês anterior (RR): no PC,
    o filtro UF = RR mostra a pendência (a caixa de UF lista os 12 meses).
    No site, a soma dos estados tem de fechar com o total da BAP."""
    r, t, iu, im = _farol_entregas(tmp_path, _ENTREGAS_PEND + [
        _entrega("RR", date(2026, 10, 9), "EM ROTA", 16.0)])
    s = ba.selecionar_farol_web("pl_entregas", r, raiz=tmp_path)
    total = int(_pend(s["kpis"])[0])
    assert total == 4
    pc_rr = rn.chamar_kpis_de(t["kpis_de"], _no_mes(t, im, "RR", iu),
                              {iu: "RR"})
    assert _pend(pc_rr)[0] == "1"
    soma = sum(int(_pend(v["kpis"])[0]) for v in s["recortes"].values())
    assert (sorted(s["recortes"]), soma) == (["AM", "PA", "RR"], total)


def test_RN_GER_006_entregas_tabela_com_cliente_fica_so_no_pc():
    t = _tabela("Entregas", [("NOV/26", "MANAUS")], mes="NOV/26")
    cols = ["UF", "CLIENTE"] + COLS_FRETE[2:]
    s = ba.selecionar_farol_web(
        "pl_entregas", _farol("Farol de Entregas", t,
                              blocos=[_bloco_frete(cols)]))
    assert s["painel"]["blocos"] == []
    assert any("so no PC" in a for a in s["avisos"])


# ------------------------------------------------------------------- Visita
_METRICAS_VISITA = (
    ("META", "num"), ("VISIT.", "int"), ("% META", "pct"), ("% CONV.", "pct"),
    ("% FORA DE ROTA", "pct"), ("CAD.", "int"), ("CAD. C/ COMPRA", "int"),
    ("PROSP.", "int"), ("INÍCIO", "hora"), ("ÚLT. ATIV.", "hora"),
    ("JORNADA LÍQ.", "hora"), ("DIAS < JORN. LÍQ.", "int"),
    ("INTERV. ALMOÇO", "hora"), ("DIAS ALMOÇO > MÁX.", "int"),
    ("TMA", "hora"), ("TMD", "hora"), ("KM", "num"), ("KM/CLIENTE", "num1"))


def _por_vendedor(filiais=("MANAUS",)):
    """"Por vendedor" conforme o §10.7.3 (24 colunas), dados fictícios."""
    cols = ([("SUPERVISOR", "texto", 0), ("VENDEDOR", "texto", 0),
             ("CARGO", "texto", 1), ("FILIAL", "texto", 1),
             ("CÓD.", "texto", 1)]
            + [(n, tp, 0) for n, tp in _METRICAS_VISITA]
            + [("CHAVE", "texto", 1)])
    colunas = []
    for n, tp, o in cols:
        c = {"nome": n, "tipo": tp}
        if o:
            c["oculta"] = True
        if n == "% META":
            c["chip"] = rn.FAIXA_PCT_META
        colunas.append(c)
    linhas = []
    for k, fil in enumerate(filiais):
        ln = [None] * len(cols)
        ln[0], ln[1], ln[2], ln[3], ln[4] = ("Supervisor 01",
                                             f"Vendedor 0{k + 1}",
                                             "VENDEDOR", fil, f"90010{k}")
        ln[6] = 10
        ln[-1] = f"v{k}"
        linhas.append(ln)
    return {"titulo": "Por vendedor", "colunas": colunas, "linhas": linhas,
            "tons": [""] * len(linhas), "filtros": ["SUPERVISOR", "VENDEDOR",
                                                     "FILIAL"],
            "kpis_de": _kpis_de}


AVISO_FORA = "Abas fora desta atualização: {lista}. Veja no PC."


def test_RN_GER_006_visita_sem_UF_do_cliente_vai_sem_recortes_e_com_aviso(
        tmp_path):
    """Visita (Planner/carteira): estado = UF do cliente; "Por vendedor" só
    tem a filial do vendedor, então NÃO se recorta por ela. A aba vai (tabela
    válida), sem aviso de aba fora; o aviso da pasta das fotos fica no PC."""
    t = _por_vendedor(("MANAUS", "BELÉM", "BELÉM"))
    r = _farol("Farol de Visita", t, blocos=[
        {"tipo": "barras", "grafico": {"titulo": "Visitas dia a dia",
                                       "rotulos": ["1"], "series": []}}],
        avisos=["O dia de hoje é parcial: muda até o vendedor sincronizar.",
                "Prospecção do app BAP Ajuda: a foto da fachada (coluna FOTO)"
                " fica na pasta do PC."])
    s = ba.selecionar_farol_web("vc_visitas", r, raiz=tmp_path)
    assert s["recortes"] == {}
    assert [x["titulo"] for x in s["tabelas"]] == ["Por vendedor"]
    assert "uf_linhas" not in s["tabelas"][0]
    assert ("abrir" in json.dumps(s)) is False
    # ordem nova (contrato §10.7.6): estado antes dos outros; teto de 2
    assert s["avisos"] == [
        AVISO_SEM_ESTADO,
        "O dia de hoje é parcial: muda até o vendedor sincronizar."]


_AVISOS_VISITA = [
    "O dia de hoje é parcial: muda até o vendedor sincronizar.",
    "Sem o arquivo de 2 dia(s) útil(eis): 20/11, 23/11",
    "Aderência = programados do Planner do dia (ROTA_PROTHEUS 2026)",
    "Prospecção: 1 resposta(s) da conta de teste"]


def test_RN_GER_006_visita_avisos_curtos_sem_arquivo_de_rota_nem_formula(
        tmp_path):
    """Celular: no máximo 2 avisos, sem nome de arquivo de rota nem fórmula,
    na ordem do contrato §10.7.6: aba fora, "Sem o arquivo", "Sem filtro por
    estado", os outros (cortando do fim)."""
    r = _farol("Farol de Visita", _por_vendedor(), avisos=_AVISOS_VISITA)
    s = ba.selecionar_farol_web("vc_visitas", r, raiz=tmp_path)
    assert s["avisos"] == ["Sem o arquivo de 2 dia(s) útil(eis): 20/11, 23/11",
                           AVISO_SEM_ESTADO]
    # com uma aba torta, o aviso de aba fora vem primeiro e nunca é cortado
    torta = _por_vendedor()
    torta["colunas"] = [dict(torta["colunas"][0], nome="COLUNA NOVA")] + \
        torta["colunas"][1:]
    r = _farol("Farol de Visita", torta, avisos=_AVISOS_VISITA)
    s = ba.selecionar_farol_web("vc_visitas", r, raiz=tmp_path)
    assert "tabelas" not in s or s["tabelas"] == []
    assert s["avisos"] == [AVISO_FORA.format(lista="Por vendedor"),
                           "Sem o arquivo de 2 dia(s) útil(eis): 20/11, 23/11"]


def test_RN_GER_006_inadimplencia_segue_pela_filial_sem_aviso_novo():
    """Entrega 1 intacta: Inadimplência recorta pela filial, sem filtro MÊS,
    e não ganha o aviso 'Sem filtro por estado' (nem sem recorte)."""
    t = _tabela("Títulos", [("", "MANAUS"), ("", "MANAUS"), ("", "BELÉM")])
    s = ba.selecionar_farol_web("pl_inadimplencia", _farol("Farol", t))
    assert _valores(s["recortes"]) == {"AM": "2", "PA": "1"}
    t2 = _tabela("Títulos", [("", "FILIAL DESCONHECIDA")])
    s2 = ba.selecionar_farol_web("pl_inadimplencia", _farol("Farol", t2))
    assert s2["recortes"] == {} and s2["avisos"] == []


def test_RN_GER_006_visita_cartao_por_estado_sem_dado_sai(monkeypatch):
    monkeypatch.setattr(rn, "estados_do_cartao", lambda r, k: {
        "barras": [["AM", 10.0, "10", "", ""], ["RR", None, "", "", ""]],
        "legenda": "x"})
    r = _farol("Farol de Visita", _por_vendedor())
    s = ba.selecionar_farol_web("vc_visitas", r)
    assert [b[0] for b in s["kpis"][0]["estados"]["barras"]] == ["AM"]
    assert s["kpis"][0]["estados"]["legenda"] == "x"


# -------------------------------------------------- RN-GER-007: datas/hoje
def test_RN_GER_007_hoje_manaus_e_a_data_no_fuso_de_manaus():
    antes = datetime.now(ZoneInfo("America/Manaus")).date()
    h = rn.hoje_manaus()
    depois = datetime.now(ZoneInfo("America/Manaus")).date()
    assert h in (antes, depois)
    assert rn.Contexto(Path("/nao/existe")).hoje in (h, depois)
    assert rn.Contexto(Path("/nao/existe"), hoje=HOJE).hoje == HOJE


def _pasta_visitas(raiz, falta=()):
    """GridRca fictício de 02/11 a ONTEM (23/11), dias úteis; hoje (24/11)
    sem arquivo, como na vida real antes do vendedor sincronizar."""
    pasta = raiz / "RELATORIOS" / "Visitas" / "diario"
    pasta.mkdir(parents=True)
    cab = "CodigoGeral;Nome;TotalVisitados;Agendados;TotalVisitas\n"
    d = date(2026, 11, 2)
    while d < HOJE:
        if d.weekday() < 5 and d not in falta:
            (pasta / f"{d:%Y%m%d}.csv").write_text(
                cab + "901;VENDEDOR FICTICIO 01;5;6;5\n", encoding="utf-8")
        d += timedelta(days=1)


def _farol_visita(raiz, monkeypatch):
    # sem Planner na pasta fictícia: o vendedor fictício vira ativo
    monkeypatch.setattr(rn, "com_cadastro_como_visita",
                        lambda ctx, regs, *a, **k: [
                            dict(l, ativo=True, cargo="VENDEDOR")
                            for l in regs])
    return rn.montar("vc_visitas", raiz, hoje=HOJE,
                     params={"ANO": "2026", "MÊS": "11"})


def test_RN_GER_007_visita_nao_cobra_o_arquivo_de_hoje(tmp_path, monkeypatch):
    """Hoje fica fora do DU: sem o arquivo de 24/11 (hoje), o aviso 'Sem o
    arquivo' não aparece (antes da T-0017 aparecia '1 dia(s): 24/11')."""
    _pasta_visitas(tmp_path)
    r = _farol_visita(tmp_path, monkeypatch)
    assert not any("Sem o arquivo" in a for a in r["avisos"])
    assert not any("24/11" in a for a in r["avisos"])


def test_RN_GER_007_visita_segue_cobrando_dia_passado_sem_arquivo(
        tmp_path, monkeypatch):
    """Dia útil fechado sem arquivo (20/11) continua no aviso; hoje não."""
    _pasta_visitas(tmp_path, falta={date(2026, 11, 20)})
    r = _farol_visita(tmp_path, monkeypatch)
    aviso = [a for a in r["avisos"] if a.startswith("Sem o arquivo")]
    assert aviso == ["Sem o arquivo de 1 dia(s) útil(eis): 20/11"]


def test_RN_GER_007_baixado_em_de_cada_farol_pelo_arquivo_de_origem(tmp_path):
    """Carimbo 'baixado em' no fuso de Manaus (UTC-4), pela base de origem
    de cada farol; sem a base, None."""
    mov = tmp_path / ba.BKP_BAPTOOLS
    mov.mkdir(parents=True)
    (mov / "Relatorio_Movimentos_BAP_Protheus_2026-11-18.xlsx").write_text("a")
    (mov / "Relatorio_Movimentos_BAP_Protheus_2026-11-19.xlsx").write_text("b")
    vis = tmp_path / ba.SUBPASTA_RELATORIOS / "Visitas"
    vis.mkdir(parents=True)
    (vis / "VISITAS_POR_CLIENTE.xlsx").write_text("c")
    ts = datetime(2026, 11, 20, 8, 30,
                  tzinfo=timezone(timedelta(hours=-4))).timestamp()
    os.utime(vis / "VISITAS_POR_CLIENTE.xlsx", (ts, ts))
    q = ba._baixado_em_da_base("vc_visitas", tmp_path)
    assert q is not None and q.utcoffset().total_seconds() == -4 * 3600
    assert q.replace(tzinfo=None) == datetime(2026, 11, 20, 8, 30)
    for rid in ("pv_pedidos", "pl_entregas"):
        assert ba._baixado_em_da_base(rid, tmp_path) is not None
    assert ba._baixado_em_da_base("vc_visitas", tmp_path / "vazio") is None
