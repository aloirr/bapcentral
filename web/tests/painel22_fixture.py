"""T-0022: pacote fictício do Painel Executivo completo e do Farol de Metas Equipe. Números inventados."""
from copy import deepcopy

from conftest import _aba, _cartao, pacote_ficticio

MESES = ["JUL", "AGO", "SET", "OUT", "NOV"]
FAIXA = [[79.9999, "#FBDDDA", "#B3261E"], [99.9999, "#FFF1C7", "#8A5A00"], [None, "#E5F3DF", "#2F7D32"]]


def _k(rot, valor, cor="neutro", det=""):
    return {"rotulo": rot, "valor": valor, "cor": cor, "detalhe": det}


def _barras(titulo, vals=(10, 20, 15, 30, 25)):
    return {"tipo": "barras", "grafico": {"titulo": titulo, "rotulos": MESES, "formato": "moeda",
                                          "series": [{"nome": "Real", "cor": "#62BB47", "valores": list(vals)}]}}


def _tab(titulo, n=3, extra=()):
    cols = [{"nome": titulo.split()[-1].upper(), "tipo": "texto"}, {"nome": "DESAFIO", "tipo": "moeda"},
            {"nome": "REAL", "tipo": "moeda"}, {"nome": "% PROJ.", "tipo": "pct"}, *extra]
    return {"tipo": "tabela", "titulo": titulo, "colunas": cols, "total": ["TOTAL", 900.0, 500.0, 55.5][:len(cols)],
            "linhas": [[f"Item {i}", 300.0, 160.0 + i, 50.0 + i] for i in range(n)]}


def _placar():
    return {"tipo": "placar", "titulo": "Os faróis no mês", "row": 0, "col": 0, "colspan": 2, "cartoes": [
        {"farol": "Meta x Real", "valor": "52%", "rotulo": "ating. projetado", "tom": "alerta",
         "detalhe": "proj. R$ 780 mil de R$ 1,5 mi", "sentido": "vs desafio", "frase": "No ritmo de hoje o mês fecha abaixo do desafio.",
         "dica": "Projeção menos o desafio.", "impacto": -720000.0},
        {"farol": "Markup", "valor": "31,0%", "rotulo": "do faturado", "tom": "ok", "detalhe": "", "sentido": "", "frase": "", "dica": ""}]}


def _painel_aba(titulo, blocos, ufs=("AM", "PA"), so_bap=False, fator=1.0):
    a = {"titulo": titulo, "kpis": [_k("Real", f"R$ {int(500 * fator)} mil", "alerta", "projeção do mês"),
                                    _k("Desafio comercial", "R$ 1,5 mi")],
         "painel": {"blocos": blocos}}
    if so_bap:
        a["so_bap"] = True
    else:
        a["recortes"] = {uf: {"kpis": [_k("Real", f"R$ {int(100 * fator + i)} mil", "ok"), _k("Desafio comercial", "R$ 300 mil")],
                              "painel": {"blocos": [_barras(f"Estado {uf} · {titulo}", (1, 2, 3, 4, 5 + i))]}}
                         for i, uf in enumerate(ufs)}
    return a


def painel_completo():
    """vc_painel com as 3 abas RRM (a de dia útil é nova) e as 9 abas de painel."""
    rel = deepcopy(pacote_ficticio()["relatorios"]["vc_painel"])
    rel["abas"]["por_dia_util"] = _aba("du", "Painel · por dia útil", [_cartao("Faturamento por DU", "R$ 8,7 mil")])
    ps = {"resumo": _painel_aba("Resumo gerencial", [_placar(), {"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 2,
                                 "linhas": [["alerta", "A projeção está 48% abaixo do desafio."]]}, _barras("Entrega x resultado")]),
          "faturamento": _painel_aba("Faturamento", [_barras("Faturamento projetado"), _tab("Por filial"), _tab("Por categoria"),
                                                     _tab("Por segmento")]),
          "volume": _painel_aba("Volume", [_barras("Volume"), _tab("Por categoria")]),
          "visitas": _painel_aba("Produtividade", [_barras("Visitas dia a dia"), _tab("Por vendedor", 2, [{"nome": "KM/CLIENTE", "tipo": "num1"}])],
                                 so_bap=True),
          "positivacao": _painel_aba("Positivação", [_barras("Positivação e gap"), _tab("Por filial")]),
          "itens": _painel_aba("Itens por pedido", [_barras("Itens por pedido")]),
          "markup": _painel_aba("Markup", [_barras("Markup")]),
          "preco": _painel_aba("Preço", [_barras("Preço de tabela"), {"tipo": "hbarras", "titulo": "Efeito preço por categoria", "formato": "moeda",
                                                                       "rotulos": ["A", "B"], "valores": [10, -5], "cores": ["#62BB47", "#B3261E"]}], so_bap=True),
          "inadimplencia": _painel_aba("Inadimplência", [_barras("Carteira por faixa")], so_bap=True)}
    rel["paineis"] = ps
    return rel


def _col(nome, tipo="texto", **kw):
    return {"nome": nome, "tipo": tipo, "largura": 90, **kw}


def _meta_cols(primeira):
    return [_col(primeira, curto=primeira), _col("CLIENTES ATIVOS", "int", curto="ATIVOS"),
            _col("FAT. META", "moeda", curto="DESAFIO"), _col("FAT. REAL", "moeda", curto="REAL"),
            _col("FAT. % ATING.", "pct", curto="% ATING.", chip=FAIXA), _col("POSIT. REAL", "int", curto="REAL")]


GRUPOS = [["", 2], ["FATURAMENTO", 3], ["POSITIVAÇÃO", 1]]


def _meta_tab(titulo, primeira, nomes, **kw):
    t = {"titulo": titulo, "colunas": _meta_cols(primeira), "grupos": [list(g) for g in GRUPOS],
         "linhas": [[n, 10 + i, 1000.0 * (i + 1), 400.0 * (i + 1), 40.0 * (i + 1), 3 + i] for i, n in enumerate(nomes)],
         "tons": [""] * len(nomes), "total": ["TOTAL", 30, 6000.0, 2400.0, 40.0, 12]}
    t.update(kw)
    return t


def _top30(n=40):
    cols = [_col("CLIENTE"), _col("UF"), _col("FAT. 6 MESES", "moeda"), _col("FAT. META", "moeda", curto="DESAFIO"),
            _col("FAT. REAL", "moeda", curto="REAL")]
    linhas = [[f"{i:06d} - LOJA {i}", "AM" if i % 2 else "PA", 10000.0 - i, float(i % 7 * 100), float(i)] for i in range(n)]
    return {"titulo": "Top 30 clientes", "colunas": cols, "linhas": linhas, "tons": [""] * n, "top_n": 30, "ordem_top": [3, 2],
            "filtros": ["UF"], "grupos": [["", 2], ["FAT.", 1], ["FATURAMENTO", 2]]}


def tabelas_meta(escala=1):
    equipe = _meta_tab("Equipe", "VENDEDORES", ["Vendedor 01", "Vendedor 02", "Vendedor 03"], juntas_em_cima=True, titulo_tabela="VENDEDORES")
    equipe["juntas"] = [{"titulo": "GERENTE", "tabela": _meta_tab("GERENTE", "GERENTE", ["Gerente 01"], total=None)},
                        {"titulo": "SUPERVISORES", "tabela": _meta_tab("SUPERVISORES", "SUPERVISORES", ["Supervisor 01", "Supervisor 02"], total=None)}]
    return [equipe, _top30(), _meta_tab("Por UF", "UF", ["AM", "PA"]), _meta_tab("Por cidade", "CIDADE", ["Cidade A", "Cidade B"]),
            _meta_tab("Por segmento", "SEGMENTO", ["Seg A"]), _meta_tab("Por categoria", "CATEGORIA", ["Cat A", "Cat B"])]


def farol_meta():
    kp = [_k("Faturamento · desafio comercial", "R$ 112 mil", "alerta", "real até a data"), _k("Positivação", "45", "alerta")]
    rec = {uf: {"kpis": [_k("Faturamento · desafio comercial", f"R$ {60 - 10 * i} mil", "alerta"), _k("Positivação", str(20 - i))],
                "painel": {"blocos": [_barras(f"Faturamento {uf} dia a dia")]},
                "insights_painel": [["alerta", f"{uf}: faturamento abaixo do desafio."]],
                "tabelas": [_top30(5), _meta_tab("Por UF", "UF", [uf])]} for i, uf in enumerate(("AM", "PA"))}
    return {"forma": "farol", "titulo": "Farol de Metas Equipe", "kpis": kp,
            "painel": {"blocos": [{"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 0,
                                   "linhas": [["alerta", "Faturamento abaixo do desafio comercial."]]}, _barras("Faturamento líquido · dia a dia")]},
            "insights_painel": [["alerta", "Faturamento abaixo do desafio comercial."]], "avisos": [], "recortes": rec,
            "baixado_em": "2026-11-24T08:10:00-04:00", "tabelas": tabelas_meta()}


def pacote_completo():
    p = pacote_ficticio()
    p["relatorios"] = {"vc_painel": painel_completo(), "vc_meta": farol_meta()}
    return p
