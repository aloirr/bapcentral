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
            {"tipo": "tabela", "row": 2, "col": 0, "titulo": "Frete por estado", "colunas": ["UF"], "linhas": [["AM"]]},
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
