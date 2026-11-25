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
    return {**_base("Farol de Pedidos", [{"rotulo": "Pedidos", "valor": "320", "cor": "ok"},
                                      {"rotulo": "Atendimento", "valor": "92,0%", "cor": "atencao", "detalhe": "meta 95%"},
                                      {"rotulo": "SLA médio", "valor": "3,1 dia(s)", "cor": "neutro"}], []),
            "kpis_faixa": True}


def farol_visitas():
    return _base("Farol de Visita", [{"rotulo": "Visitas", "valor": "180", "cor": "ok"}], [
        {"tipo": "barras", "grafico": {"titulo": "Visitas por semana", "rotulos": ["S1", "S2", "S3"], "formato": "num",
                                       "series": [{"nome": "Visitas", "cor": "#62BB47", "valores": [50, 60, 70]}]}}])


# ---------------------------------------------------------------------------------------------
# T-0017, entregas 3 a 5 (contrato §10.7): abas de tabela de Pedidos, Entregas e Visita.
# 100% fictício: "CLIENTE FICTICIO nn", "VENDEDOR FICTICIO nn", códigos 9xxxxx, sem CNPJ nem telefone.
# ---------------------------------------------------------------------------------------------
from copy import deepcopy  # noqa: E402
from datetime import date  # noqa: E402

from app import tabelas  # noqa: E402

# iguais às do PC: relatorios_nucleo.CHIP_SLA() (PRAZO_FATURAR = 2), BARRA_ATENDIDO e FAIXA_PCT_META
FAIXA_SLA = [[1, "#E5F3DF", "#2F7D32"], [2, "#FFF1C7", "#8A5A00"], [4, "#FBDDDA", "#B3261E"], [None, "#B3261E", "#FFFFFF"]]
BARRA_ATEND = {"max": 100, "faixas": [[49.99, "#D9534F", "#B3261E"], [99.98, "#E0A526", "#8A5A00"],
                                      [None, "#62BB47", "#2F7D32"]]}
FAIXA_META = [[79.9999, "#FBDDDA", "#B3261E"], [99.9999, "#FFF1C7", "#8A5A00"], [None, "#E5F3DF", "#2F7D32"]]
CHIP_PRAZO = {"NO PRAZO": ["#E5F3DF", "#2F7D32"], "ATRASADA": ["#B3261E", "#FFFFFF"]}
SELO = {"Pedidos": {"SLA": ("chip", FAIXA_SLA), "% ATENDIDO": ("barra", BARRA_ATEND)},
        "Entregas": {"SLA": ("chip_tom", "TOM SLA"), "PRAZO": ("chip", CHIP_PRAZO)},
        "Pendências dos meses anteriores": {"SLA": ("chip_tom", "TOM SLA"), "PRAZO": ("chip", CHIP_PRAZO)},
        "Por supervisor": {"% META": ("chip", FAIXA_META)}, "Por vendedor": {"% META": ("chip", FAIXA_META)},
        "Dia a dia": {"% META": ("chip", FAIXA_META)}}
UFS3 = ["AM", "PA", "MA"]
CIDADES3 = ["MANAUS", "BELÉM", "SÃO LUÍS"]
DIAS_SEM = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]


def _dow(dia, mes=11):
    """Dia da semana pela data real (01/11/2026 é domingo)."""
    return DIAS_SEM[date(2026, mes, dia).weekday()]


UTEIS = [d for d in range(1, 20) if date(2026, 11, d).weekday() < 5 and d != 2]      # 02/11 é feriado


def _colunas(titulo, nomes=None):
    """As colunas do contrato (§10.7.3) como o robô manda, com o selo de cada coluna marcada."""
    esp = nomes if nomes is not None else tabelas.COLUNAS[titulo]
    out = []
    for n, tp, o in esp:
        c = {"nome": n, "tipo": tp, "largura": 90, "oculta": o}
        if n == "ETAPA":
            c["inteira"] = True
        sel = SELO.get(titulo, {}).get(n)
        if sel:
            c[sel[0]] = deepcopy(sel[1])
        out.append(c)
    return out


def _ln(cols, valores):
    nomes = [c["nome"] for c in cols]
    extra = set(valores) - set(nomes)
    assert not extra, extra
    return [valores.get(n) for n in nomes]


def _vend(i):
    return f"VENDEDOR FICTICIO {i % 5 + 1:02d}"


def _sup(i):
    return f"SUPERVISOR FICTICIO {i % 3 + 1:02d}"


def _cli(i):
    return f"CLIENTE FICTICIO {i:02d}"


def _cod(i):
    return f"9{i:05d}"


def _iso(dia, mes=11):
    return f"2026-{mes:02d}-{dia:02d}"


def _tabela7(titulo, linhas, tons=None, filtros=None, **extra):
    t = {"titulo": titulo, "colunas": _colunas(titulo), "linhas": linhas}
    if tons is not None:
        t["tons"] = tons
    if filtros is not None:
        t["filtros"] = filtros
    t.update(extra)
    return t


def _kpi(rot, valor, cor="neutro", det=""):
    return {"rotulo": rot, "valor": valor, "cor": cor, "detalhe": det}


# ------------------------------------------------------------------ Pedidos
def tabela_pedidos(n=24):
    cols = _colunas("Pedidos")
    linhas, tons, ufs = [], [], []
    for i in range(1, n + 1):
        sla = (i * 7) % 10
        atend = [100, 100, 75, 40, 100, 90][i % 6]
        sit = "FATURADO" if i % 8 == 0 else "EM ABERTO"
        linhas.append(_ln(cols, {
            "DT. PED": _iso(i % 19 + 1), "FATURAR ATÉ": _iso(i % 19 + 4), "PEDIDO": f"9{i + 100:05d}",
            "PED. MÁX.": f"9{i + 100:05d}", "CÓD.": _cod(i), "RAZÃO SOCIAL": _cli(i),
            "FANTASIA": f"FANTASIA FICTICIA {i:02d}", "UF": UFS3[i % 3], "CIDADE": CIDADES3[i % 3],
            "LIMITE": 20000.0 + 500 * i, "DISP.": 12000.0 + 300 * i, "ATRASO": 0.0 if i % 4 else 1800.0,
            "VOL.": 10 + i, "R$ TABELA": 5000.0 + 220 * i, "R$ VENDA": 4400.0 + 200 * i,
            "% DESC.": 10.0 + (i % 7) * 1.5, "SLA": sla, "% ATENDIDO": atend,
            "ANÁLISE CRÉDITO": "A ANALISAR" if i % 5 == 0 else "LIBERADO", "COND. PAGTO": "30/60 DD",
            "SITUAÇÃO": sit, "FILIAL": f"FILIAL FICTICIA {UFS3[i % 3]}",
            "PRAZO": "ATRASADA" if sla > 4 else "NO PRAZO", "VENDEDOR": _vend(i),
            "NF": f"9{i + 500:05d}" if sit == "FATURADO" else "",
            "DT. NF": _iso(i % 19 + 2) if sit == "FATURADO" else None, "R$ TABELA CHEIA": 5600.0 + 220 * i,
            "CÓD. AUTORIZAÇÃO": "", "AUTORIZADO POR": "", "MÊS": "NOV/26", "ENTREGUE EM": None,
            "PRODUTO": f"PRODUTO FICTICIO {i % 4 + 1}", "CHAVE": f"CH{i:04d}"}))
        tons.append("grave" if sla > 7 else "alerta" if sla > 4 else "atencao" if sla == 4
                    else "ok" if atend == 100 else "")
        ufs.append(UFS3[i % 3])
    ix = {c["nome"]: k for k, c in enumerate(cols)}
    ab = [k for k, ln in enumerate(linhas) if ln[ix["SITUAÇÃO"]] == "EM ABERTO"]
    faturar = [k for k in ab if linhas[k][ix["% ATENDIDO"]] == 100]
    mais4 = [k for k in ab if linhas[k][ix["SLA"]] > 4]
    pedidos = [ln[ix["PEDIDO"]] for ln in linhas]

    def gerar(t, ks):
        return [_ln(_colunas(t), {
            "DATA": _iso(k % 19 + 1), "UF": UFS3[k % 3], "CIDADE": CIDADES3[k % 3],
            "PEDIDOS": "|".join(pedidos[j] for j in (k, k + 1) if j < n),
            "FORN.": f"FORNECEDOR FICTICIO {k % 3 + 1}", "CÓD. PROD.": f"9{k + 700:05d}",
            "DESCRIÇÃO": f"PRODUTO FICTICIO {k % 4 + 1}", "QTD": 4 + k, "COLETAR EM": "CD FICTICIO",
            "FILIAL DEST.": f"FILIAL FICTICIA {UFS3[k % 3]}"}) for k in ks]
    analitico = [_ln(_colunas("Analítico produto"), {
        "PEDIDO": pedidos[k], "DATA": _iso(k % 19 + 1), "CIDADE": CIDADES3[k % 3],
        "FILIAL": f"FILIAL FICTICIA {UFS3[k % 3]}", "FORN.": f"FORNECEDOR FICTICIO {k % 3 + 1}",
        "CÓD. PROD.": f"9{k + 700:05d}", "DESCRIÇÃO": f"PRODUTO FICTICIO {k % 4 + 1}", "QTD": 6, "EST. FRW": 2,
        "PEDIDOS ANTES": 3, "DISP. P/ ESTE": 1, "ATENDIDO": 1, "FALTA": 5,
        "CLIENTE": f"{_cod(k + 1)} - {_cli(k + 1)}", "FILIAL BAP": f"FILIAL FICTICIA {UFS3[k % 3]}",
        "VALOR FALTANTE": 350.0 + 10 * k}) for k in range(0, n, 2)]
    juntas = [
        {"titulo": "Gerar ID de separação CD", "liga": ["PEDIDOS", "PEDIDO", "|"],
         "tabela": {"titulo": "Gerar separação CD", "colunas": _colunas("Gerar separação CD"),
                    "linhas": gerar("Gerar separação CD", range(0, n, 3))}},
        {"titulo": "Gerar reversa de lojas", "liga": ["PEDIDOS", "PEDIDO", "|"],
         "tabela": {"titulo": "Gerar reversa de lojas", "colunas": _colunas("Gerar reversa de lojas"),
                    "linhas": gerar("Gerar reversa de lojas", range(1, n, 5))}},
        {"titulo": "Analítico por pedido", "liga": ["PEDIDO", "PEDIDO", None],
         "mostrar": ["PEDIDO", "CIDADE", "CÓD. PROD.", "DESCRIÇÃO", "QTD", "FALTA", "CLIENTE", "VALOR FALTANTE"],
         "tabela": {"titulo": "Analítico produto", "colunas": _colunas("Analítico produto"), "linhas": analitico}}]
    kp = [_kpi("SLA médio", "3,6 dia(s)", "atencao"), _kpi("Pedidos", str(len(ab))), _kpi("R$ em aberto", "R$ 112 mil"),
          _kpi("Faturar (100%)", str(len(faturar)), "ok"), _kpi("Mais de 4 dias", str(len(mais4)), "alerta"),
          _kpi("Volume", "401 un.")]
    return _tabela7("Pedidos", linhas, tons,
                    [{"coluna": "MÊS", "padrao": "NOV/26", "oculto": True},
                     {"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}, "CIDADE", "VENDEDOR",
                     {"coluna": "PRODUTO", "multi": True}],
                    uf_linhas=ufs, kpis_padrao=kp,
                    juntas=juntas, zebra=True)


SUBS = {
    "Solicitacao Lojas": ["DATA", "LOJA", "COD_PRODUTO", "DESCRICAO", "QUANTIDADE", "SALDO_A_SOLICITAR"],
    "Solicitacao CD": ["DATA", "FILIAL_DESTINO", "COD_PRODUTO", "DESCRICAO", "FORNECEDOR", "QUANTIDADE",
                       "DEMANDA_PEDIDO", "JA_SOLICITADO", "SALDO_A_SOLICITAR", "ESTOQUE_NA_ORIGEM"],
    "Solicitacao FRW": ["DATA", "FILIAL_DESTINO", "COD_PRODUTO", "DESCRICAO", "QUANTIDADE", "ESTOQUE_NA_ORIGEM"],
    "Solicitacao Manual": ["DATA", "FILIAL_DESTINO", "COD_PRODUTO", "QUANTIDADE"],
    "DETALHADO_PEDIDO": ["PEDIDO", "CLIENTE", "DATA", "COD_PRODUTO", "DESCRICAO", "QUANTIDADE",
                         "SALDO_A_SOLICITAR", "STATUS"],
    "ProdutosExcluir": ["COD_PRODUTO", "DESCRICAO", "MOTIVO"], "FiliaisExcluir": ["FILIAL", "MOTIVO"]}
NUM_SUB = {"QUANTIDADE", "DEMANDA_PEDIDO", "JA_SOLICITADO", "SALDO_A_SOLICITAR", "ESTOQUE_NA_ORIGEM"}
N_SUB = {"Solicitacao Lojas": 14, "Solicitacao CD": 12, "Solicitacao FRW": 10, "Solicitacao Manual": 3,
         "DETALHADO_PEDIDO": 40, "ProdutosExcluir": 8, "FiliaisExcluir": 4}


def tabela_solicitacao():
    subs = []
    for titulo, nomes in SUBS.items():
        cols = [{"nome": n, "tipo": "num" if n in NUM_SUB else "data" if n == "DATA" else "texto"} for n in nomes]
        linhas = []
        for i in range(1, N_SUB[titulo] + 1):
            v = {"DATA": _iso(i % 19 + 1), "LOJA": f"LOJA FICTICIA {i % 4 + 1}",
                 "FILIAL_DESTINO": f"FILIAL FICTICIA {UFS3[i % 3]}", "COD_PRODUTO": f"9{i + 700:05d}",
                 "DESCRICAO": f"PRODUTO FICTICIO {i % 6 + 1}", "FORNECEDOR": f"FORNECEDOR FICTICIO {i % 3 + 1}",
                 "QUANTIDADE": 3 + i, "DEMANDA_PEDIDO": 6 + i, "JA_SOLICITADO": i, "SALDO_A_SOLICITAR": 6,
                 "ESTOQUE_NA_ORIGEM": 20 + i, "PEDIDO": f"9{i + 100:05d}", "CLIENTE": _cod(i), "STATUS": "EM ABERTO",
                 "MOTIVO": "FORA DE LINHA", "FILIAL": f"FILIAL FICTICIA {UFS3[i % 3]}"}
            linhas.append([v[n] for n in nomes])
        subs.append({"titulo": titulo, "colunas": cols, "linhas": linhas, "filtros": [], "total": None})
    return {"titulo": "Solicitação BAP", "colunas": [], "linhas": [], "subabas": subs}


def farol_pedidos_com_abas():
    f = farol_pedidos()
    f["tabelas"] = [tabela_pedidos(), tabela_solicitacao()]
    f["kpis_faixa"] = True
    f["kpis"] = deepcopy(f["tabelas"][0]["kpis_padrao"])
    f["recortes"] = {uf: {"kpis": [_kpi("Pedidos", str(40 + k)), _kpi("Em aberto", str(25 + k), "atencao")]}
                     for k, uf in enumerate(UFS3)}
    return f


# ------------------------------------------------------------------ Entregas
def _linhas_entregas(titulo, n, mes, pend=False):
    cols = _colunas(titulo)
    linhas, tons, ufs = [], [], []
    for i in range(1, n + 1):
        sla = [1, 2, 3, 5, 8][i % 5]
        tom = "ok" if sla <= 2 else "atencao" if sla <= 4 else "alerta"
        m = (10 if i % 2 else 9) if pend else 11
        mes_i = mes if not pend else ("OUT/26" if i % 2 else "SET/26")
        linhas.append(_ln(cols, {
            "MÊS": mes_i, "SITUAÇÃO": "PENDENTE" if pend or i % 3 else "ENTREGUE", "SLA": sla,
            "DT. PED": _iso(i % 17 + 1, m), "DT. NF": _iso(i % 17 + 2, m), "DT. PREVISTA": _iso(i % 17 + 6, m),
            "DT. REAL": _iso(i % 17 + 5, 11) if not pend and i % 3 == 0 else None,
            "UF": UFS3[i % 3], "CIDADE": CIDADES3[i % 3], "CLIENTE": f"{_cod(i)} - {_cli(i)}",
            "VLR NF": 8000.0 + 310 * i, "VLR FRETE": 240.0 + 9 * i,
            "TRANSPORTADORA": f"TRANSPORTADORA FICTICIA {i % 3 + 1}", "RESPONSÁVEL": f"MOTORISTA FICTICIO {i % 4 + 1}",
            "TBL FRETE": 210.0 + 8 * i, "VLR REAL FRETE": 235.0 + 9 * i,
            "ETAPA": ["AGUARDANDO COLETA", "EM TRÂNSITO", "ENTREGUE AO CLIENTE", "PEDIDO EM SEPARAÇÃO NO CD"][i % 4],
            "NF": f"9{i + 500:05d}", "FILIAL": f"FILIAL FICTICIA {UFS3[i % 3]}", "LOCAL/FRETE": "CIF",
            "TOM SLA": tom, "PRAZO": "ATRASADA" if sla > 4 else "NO PRAZO"}))
        tons.append("")
        ufs.append(UFS3[i % 3])
    return cols, linhas, tons, ufs


def tabela_entregas(n=18, pend=6):
    _, linhas, tons, ufs = _linhas_entregas("Entregas", n, "NOV/26")
    pc, pl, pt, pu = _linhas_entregas("Pendências dos meses anteriores", pend, "OUT/26", pend=True)
    kp = [_kpi("Entregas no mês", str(n)), _kpi("SLA médio", "3,8 dia(s)", "atencao"),
          _kpi("Frete do mês", "R$ 4,6 mil"), _kpi("Atrasadas", "7", "alerta"),
          _kpi("Pendências antigas", str(pend), "alerta")]
    return _tabela7("Entregas", linhas, tons,
                    [{"coluna": "MÊS", "padrao": "NOV/26", "oculto": True}, "SITUAÇÃO", "ETAPA", "PRAZO", "FILIAL"],
                    uf_linhas=ufs, kpis_padrao=kp,
                    juntas=[{"titulo": "Pendências dos meses anteriores", "liga": None,
                             "tabela": {"titulo": "Pendências dos meses anteriores", "colunas": pc, "linhas": pl,
                                        "tons": pt, "uf_linhas": pu}}])


def farol_entregas_com_abas():
    f = farol_entregas()
    f["tabelas"] = [tabela_entregas()]
    f["recortes"] = {uf: {"kpis": [_kpi("Frete do mês", f"R$ {k + 1},2 mil"), _kpi("Notas", str(100 + k))]}
                     for k, uf in enumerate(UFS3)}
    return f


# ------------------------------------------------------------------ Visita
def _metricas(i, sem_visita=False):
    visit = 0 if sem_visita else 12 + (i * 3) % 11
    if sem_visita:                       # como o PC: contadores em 0, razões e horas vazias ("—")
        return {"META": 20.0, "VISIT.": 0, "% META": 0.0, "% CONV.": None, "% FORA DE ROTA": None, "CAD.": 0,
                "CAD. C/ COMPRA": 0, "PROSP.": 0, "INÍCIO": "—", "ÚLT. ATIV.": "—", "JORNADA LÍQ.": "—",
                "DIAS < JORN. LÍQ.": 0, "INTERV. ALMOÇO": "—", "DIAS ALMOÇO > MÁX.": 0, "TMA": "—", "TMD": "—",
                "KM": 0.0, "KM/CLIENTE": None}
    return {"META": 20.0, "VISIT.": visit, "% META": round(100.0 * visit / 20.0, 1), "% CONV.": 38.5 + i % 6,
            "% FORA DE ROTA": 8.0 + i % 4, "CAD.": i % 3, "CAD. C/ COMPRA": i % 2, "PROSP.": i % 4,
            "INÍCIO": f"{8 + i % 2:02d}:{(i * 7) % 60:02d}", "ÚLT. ATIV.": f"17:{(i * 11) % 60:02d}",
            "JORNADA LÍQ.": "7:42", "DIAS < JORN. LÍQ.": i % 5, "INTERV. ALMOÇO": "1:05",
            "DIAS ALMOÇO > MÁX.": i % 3, "TMA": "0:21", "TMD": "0:09", "KM": round(88.0 + i * 3.4, 1),
            "KM/CLIENTE": 6.5 + (i % 5) / 2}


def _soma(linhas, cols):
    """Total que fecha com as linhas: META e VISIT. somadas e % META = visitas ÷ meta."""
    ix = {c["nome"]: k for k, c in enumerate(cols)}
    meta = sum(ln[ix["META"]] for ln in linhas)
    visit = sum(ln[ix["VISIT."]] for ln in linhas)
    m = _metricas(9)
    m.update({"META": meta, "VISIT.": visit, "% META": round(100.0 * visit / meta, 1) if meta else 0.0})
    return m


def tabela_supervisor():
    cols = _colunas("Por supervisor")
    linhas = [_ln(cols, {"SUPERVISOR": _sup(i), "REPRES.": 3, **_metricas(i), "CHAVE": f"S{i}"}) for i in range(3)]
    tot = _ln(cols, {"SUPERVISOR": "TOTAL", "REPRES.": 9, **_soma(linhas, cols)})
    return _tabela7("Por supervisor", linhas, [""] * 3, total=tot)


def tabela_vendedor():
    cols = _colunas("Por vendedor")
    linhas = [_ln(cols, {"SUPERVISOR": _sup(i), "VENDEDOR": _vend(i), "CARGO": "REPRESENTANTE",
                         "FILIAL": "FILIAL FICTICIA", "CÓD.": _cod(i), **_metricas(i), "CHAVE": f"V{i}"})
              for i in range(9)]
    tot = _ln(cols, {"SUPERVISOR": "TOTAL", **_soma(linhas, cols)})
    return _tabela7("Por vendedor", linhas, [""] * 9, ["SUPERVISOR"], total=tot)


def tabela_dia(n=120):
    cols = _colunas("Dia a dia")
    linhas, sem = [], []
    for i in range(n):
        dia = UTEIS[i % len(UTEIS)]
        sit = "SEM VISITA" if i % 11 == 0 else "TRABALHADO"
        if sit == "SEM VISITA":
            sem.append(i)
        linhas.append(_ln(cols, {"DATA": _iso(dia), "DIA": _dow(dia), "SUPERVISOR": _sup(i),
                                 "VENDEDOR": _vend(i), "CARGO": "REPRESENTANTE", "SITUAÇÃO": sit,
                                 **_metricas(i, sem_visita=sit == "SEM VISITA"), "CHAVE": f"D{i}"}))
    ix = {c["nome"]: k for k, c in enumerate(cols)}
    return _tabela7("Dia a dia", linhas, [""] * n, ["SUPERVISOR", "VENDEDOR", "SITUAÇÃO"],
                    total=_ln(cols, {"DIA": "TOTAL", **_soma(linhas, cols)}),
                    recortes_linhas=[
                        {"rotulo": "Sem visita em dia útil", "linhas": sem},
                        {"rotulo": "Abaixo da meta", "linhas": [k for k in range(n) if linhas[k][ix["% META"]] < 80]},
                        {"rotulo": "Fora de rota acima de 10%",
                         "linhas": [k for k in range(n) if (linhas[k][ix["% FORA DE ROTA"]] or 0) > 10]}])


def tabela_aderencia():
    dias = [(d, _dow(d)) for d in UTEIS]
    nomes = ([("SUPERVISOR", "texto", False), ("VENDEDOR", "texto", False)]
             + [(f"{d:02d}/11 {s}", "pct", False) for d, s in dias] + [("% ADERÊNCIA ACUM. ATÉ 19/11", "pct", False)])
    cols = _colunas("Aderência dia a dia", nomes)
    linhas = []
    for i in range(9):
        v = {"SUPERVISOR": _sup(i), "VENDEDOR": _vend(i), "% ADERÊNCIA ACUM. ATÉ 19/11": 80.0 + i}
        for k, (d, s) in enumerate(dias):
            v[f"{d:02d}/11 {s}"] = [100.0, 75.0, 50.0, 90.0, 0.0][(i + k) % 5]
        linhas.append(_ln(cols, v))
    return {"titulo": "Aderência dia a dia", "colunas": cols, "linhas": linhas, "tons": [""] * 9,
            "total": _ln(cols, {"SUPERVISOR": "TOTAL", "% ADERÊNCIA ACUM. ATÉ 19/11": 84.0})}


def tabela_cliente(n=230):
    cols = _colunas("Cliente a cliente")
    linhas, sem = [], []
    for i in range(n):
        tem = i % 4 != 0
        if not tem:
            sem.append(i)
        linhas.append(_ln(cols, {
            "DATA": _iso(UTEIS[i % len(UTEIS)]), "DIA": _dow(UTEIS[i % len(UTEIS)]), "SUPERVISOR": _sup(i), "VENDEDOR": _vend(i),
            "SITUAÇÃO": "VISITADO" if tem else "NÃO VISITADO", "CÓD.": f"9{i + 1:05d}-01",
            "CLIENTE": f"9{i + 1:05d} - {_cli(i % 99 + 1)}", "NOME FANTASIA": f"FANTASIA FICTICIA {i % 99 + 1:02d}",
            "SEGMENTO": ["AUTOPEÇAS", "OFICINA", "LOJA"][i % 3], "BAIRRO": f"BAIRRO FICTICIO {i % 7 + 1}",
            "CIDADE": CIDADES3[i % 3], "CURVA": "ABC"[i % 3], "STATUS": "ATIVO", "DIAS S/ COMPRA": (i * 5) % 120,
            "ATRASO": 0.0 if i % 6 else 1250.0, "SEQ. PREV.": str(i % 12 + 1),
            "SEQ. REAL": str(i % 12 + 1) if tem else "",
            "INÍCIO": f"{8 + i % 8:02d}:{i % 60:02d}" if tem else "",
            "FIM": f"{8 + i % 8:02d}:{(i + 20) % 60:02d}" if tem else "", "ATEND.": "0:20" if tem else "",
            "PEDIDO NO DIA": "SIM" if tem and i % 3 == 0 else "",
            "VALOR PEDIDO": 1800.0 if tem and i % 3 == 0 else None,
            "JUSTIFICATIVA": "" if tem else "CLIENTE FECHADO", "ATEND. SEG.": 1200 if tem else 0}))
    return _tabela7("Cliente a cliente", linhas, [""] * n,
                    ["SUPERVISOR", "VENDEDOR", "SITUAÇÃO", "CIDADE", "CURVA"],
                    recortes_linhas=[{"rotulo": "Não visitados", "linhas": sem}])


def tabela_prospeccao(n=12):
    cols = _colunas("Prospecção")
    linhas = [_ln(cols, {
        "DATA": _iso(UTEIS[i % len(UTEIS)]), "HORA": f"{9 + i % 8:02d}:{i * 5 % 60:02d}", "DIA": _dow(UTEIS[i % len(UTEIS)]), "SUPERVISOR": _sup(i),
        "VENDEDOR": _vend(i), "STATUS": "NOVO", "FONTE": "RUA", "ESTABELECIMENTO": f"OFICINA FICTICIA {i + 1:02d}",
        "SEGMENTO": "OFICINA", "CIDADE": CIDADES3[i % 3], "UF": UFS3[i % 3],
        "RESULTADO": "VISITA AGENDADA" if i % 2 else "SEM INTERESSE", "LINHAS DE INTERESSE": "FREIOS; SUSPENSÃO",
        "OBSERVAÇÃO": "Voltar na próxima semana."}) for i in range(n)]
    return _tabela7("Prospecção", linhas, [""] * n, ["SUPERVISOR", "VENDEDOR", "STATUS"],
                    recortes_linhas=[{"rotulo": "Com visita agendada", "linhas": [k for k in range(n) if k % 2]}])


def tabela_indicacao():
    return _tabela7("Indicação", [], [], ["SUPERVISOR", "VENDEDOR"], recortes_linhas=[])


def farol_visitas_com_abas():
    f = farol_visitas()
    f["avisos"] = ["Sem filtro por estado: os cartões mostram a BAP inteira."]
    sup = tabela_supervisor()                  # os cartões saem da mesma conta do TOTAL da tabela
    tot = dict(zip([c["nome"] for c in sup["colunas"]], sup["total"]))
    pct = tot["% META"]
    f["kpis"] = [_kpi("Visitas", str(tot["VISIT."]), "ok" if pct >= 100 else "atencao" if pct >= 80 else "alerta"),
                 _kpi("% da meta", f"{pct:.1f}%".replace(".", ","), "ok" if pct >= 100 else "atencao" if pct >= 80 else "alerta"),
                 _kpi("Meta", str(int(tot["META"]))), _kpi("Conversão", f"{tot['% CONV.']:.1f}%".replace(".", ",")),
                 _kpi("Km rodados", f"{tot['KM']:,.0f}".replace(",", "."))]
    f["tabelas"] = [sup, tabela_vendedor(), tabela_dia(), tabela_aderencia(), tabela_cliente(),
                    tabela_prospeccao(), tabela_indicacao()]
    return f


def pacote_tres_farois(com_tabelas=True):
    """Pacote fictício dos três faróis (Pedidos, Entregas e Visita), com ou sem as abas de tabela."""
    p = pacote_farol(pv_pedidos=farol_pedidos_com_abas(), pl_entregas=farol_entregas_com_abas(),
                     vc_visitas=farol_visitas_com_abas())
    if not com_tabelas:
        for r in p["relatorios"].values():
            r.pop("tabelas", None)
    return deepcopy(p)
