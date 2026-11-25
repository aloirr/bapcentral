"""Pacote fictício de farol (T-0017): números inventados, sem cliente, CNPJ ou vendedor com nome."""


def farol_inadimplencia(baixado_em="2026-11-24T08:10:00-04:00"):
    def k(rot, valor, cor="neutro", det="", linhas=None):
        d = {"rotulo": rot, "valor": valor, "cor": cor, "detalhe": det}
        if linhas:
            d["linhas"] = linhas
        return d
    meses = ["JUN", "JUL", "AGO", "SET", "OUT", "NOV"]
    return {
        "forma": "farol", "titulo": "Inadimplência",
        "kpis": [k("Em atraso", "R$ 1,20 mi", "alerta", "38 títulos", [["Acima de 90 dias", "R$ 310 mil", "alerta"]]),
                 k("A vencer", "R$ 2,85 mi", "neutro", "120 títulos"),
                 k("% em atraso", "29,6%", "atencao"),
                 k("Recebido no mês", "R$ 980 mil", "ok"),
                 k("Prazo médio de atraso", "41 dias", "atencao"),
                 k("Clientes em atraso", "—")],
        "painel": {"colunas": [1, 1, 1], "blocos": [
            {"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 0,
             "linhas": [["alerta", "Atraso acima de 90 dias soma R$ 310 mil."], ["info", "Recebido no mês: R$ 980 mil."]]},
            {"tipo": "barras", "row": 0, "col": 1, "colspan": 2, "grafico": {
                "titulo": "Recebido (R$) · mês a mês", "rotulos": meses, "formato": "moeda",
                "series": [{"nome": "Recebido", "cor": "#62BB47", "valores": [820000, 910000, 760000, 1020000, 870000, 980000]}]}},
            {"tipo": "barras", "row": 1, "col": 0, "grafico": {
                "titulo": "Vencido × a vencer", "rotulos": meses, "formato": "moeda",
                "series": [{"nome": "Vencido", "cor": "#B3261E", "valores": [90000, 120000, 80000, 150000, 110000, 120000]},
                           {"nome": "A vencer", "cor": "#B7791F", "valores": [200000, 250000, 230000, 280000, 260000, 285000]}]}},
            {"tipo": "hbarras", "row": 1, "col": 1, "titulo": "Em atraso por vendedor (R$)", "formato": "moeda",
             "rotulos": ["Vendedor 01", "Vendedor 02", "Vendedor 03", "Vendedor 04"],
             "valores": [410000, 320000, 150000, 60000], "cores": ["#B3261E"] * 4},
            {"tipo": "pizza", "row": 2, "col": 0, "titulo": "Bloco de outro tipo"},
        ]},
        "insights_painel": [["alerta", "Atraso acima de 90 dias soma R$ 310 mil."], ["info", "Recebido no mês: R$ 980 mil."]],
        "avisos": [],
        "recortes": {"AM": {"kpis": [k("Em atraso", "R$ 700 mil", "alerta"), k("A vencer", "R$ 1,50 mi")]},
                     "PA": {"kpis": [k("Em atraso", "R$ 300 mil", "alerta"), k("A vencer", "R$ 800 mil")]}},
        "baixado_em": baixado_em,
    }


def pacote_farol(**rels):
    return {"versao_contrato": 1, "gerado_em": "2026-11-24T08:30:00-04:00", "ano": 2026, "mes": 11,
            "relatorios": rels or {"pl_inadimplencia": farol_inadimplencia()}}


def _col(nome, tipo="texto"):
    return {"nome": nome, "tipo": tipo, "largura": 90, "oculta": False}


def _base(titulo, kpis, blocos):
    return {"forma": "farol", "titulo": titulo, "kpis": kpis, "painel": {"blocos": blocos},
            "insights_painel": [["info", "Frase fictícia."]], "avisos": [], "baixado_em": "2026-11-24T08:10:00-04:00"}


def farol_entregas():
    cols = [_col("UF"), _col("REGIÃO"), _col("NOTAS", "int"), _col("VALOR NF", "moeda"),
            _col("FRETE R$", "moeda"), _col("% S/ NOTA", "pct1"), _col("FRETE/NOTA", "moeda")]
    return _base("Farol de Entregas", [{"rotulo": "Frete do mês", "valor": "R$ 52 mil", "cor": "info", "detalhe": "410 notas"}], [
        {"tipo": "tabela", "titulo": "Frete por estado · nov/2026", "colunas": cols, "col": 1, "row": 0,
         "linhas": [["AM", "Norte", 310, 1250000.0, 38000.5, 3.04, 122.58], ["PA", "Norte", 100, 400000.0, 14000.0, 3.5, 140.0]],
         "total": ["TOTAL", "", 410, 1650000.0, 52000.5, 3.15, 126.83]},
        {"tipo": "hbarras", "titulo": "SLA por estado", "rotulos": ["AM", "PA"], "valores": [2.5, 4.0], "formato": "num1"}])


def farol_pedidos():
    return _base("Farol de Pedidos", [{"rotulo": "Pedidos", "valor": "320", "cor": "ok"},
                                      {"rotulo": "Atendimento", "valor": "92,0%", "cor": "atencao", "detalhe": "meta 95%"},
                                      {"rotulo": "SLA médio", "valor": "3,1 dia(s)", "cor": "neutro"}], [])


def farol_visitas():
    return _base("Farol de Visita", [{"rotulo": "Visitas", "valor": "180", "cor": "ok"}], [
        {"tipo": "barras", "grafico": {"titulo": "Visitas por semana", "rotulos": ["S1", "S2", "S3"], "formato": "num",
                                       "series": [{"nome": "Visitas", "cor": "#62BB47", "valores": [50, 60, 70]}]}}])
