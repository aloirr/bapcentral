"""T-0023 v2: pacote FICTÍCIO dos 3 faróis do Pós-venda (Garantias, Devoluções e NCC) na forma que o robô manda
(formato do pacote real, medido em `montar` no `main`): as colunas são as do contrato §10.10.2 (lidas de
`tabelas.COLUNAS_RID`), e os valores são inventados ("CLIENTE FICTICIO nn", "VENDEDOR FICTICIO nn"). Os cartões, as abas
e os totais saem das MESMAS linhas, para o número do Resumo bater com a aba. Nenhum cliente, CNPJ ou telefone real."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

from app import tabelas

HOJE = date(2026, 11, 24)
BAIXADO = "2026-11-24T08:10:00-04:00"
TOM = {"cinza": ["#EEEEEA", "#5F6360"], "ok": ["#F0F7EC", "#2F7D32"], "atencao": ["#FFF4D6", "#8A5A00"], "alerta": ["#FDECEA", "#B42318"]}
CHIP = {"ABERTO": TOM["atencao"], "EM TRATATIVA": TOM["atencao"], "FINALIZADA": TOM["ok"], "ATRASADA": TOM["alerta"],
        "NO PRAZO": TOM["ok"], "FECHADA NO PRAZO": TOM["cinza"], "FECHADA COM ATRASO": TOM["cinza"], "SLA ATRASADO": TOM["alerta"], "NO SLA": TOM["ok"], "ATENÇÃO": TOM["atencao"],
        "PENDENTE": TOM["atencao"], "PROCEDENTE": TOM["ok"], "IMPROCEDENTE": TOM["alerta"]}
CIDADES = [("MANAUS", "AM"), ("BELÉM", "PA"), ("SÃO LUÍS", "MA"), ("BOA VISTA", "RR"), ("CUIABÁ", "MT")]
FILIAL_DE = {"AM": "FILIAL AM", "PA": "FILIAL PA", "MA": "FILIAL MA", "RR": "FILIAL RR", "MT": "FILIAL MT"}
UF_ORDEM = ("AM", "PA", "MA", "RR", "MT")


def _iso(d: date) -> str:
    return d.isoformat()


def _cli(i):
    return f"CLIENTE FICTICIO {i:02d}"


def _vend(i):
    return f"VENDEDOR FICTICIO {i % 4 + 1:02d}"


def _sup(i):
    return f"SUPERVISOR FICTICIO {i % 2 + 1:02d}"


def _br(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def moeda(v: float) -> str:
    if v >= 1e6:
        return f"R$ {v / 1e6:.2f} mi".replace(".", ",")
    if v >= 1e4:
        return f"R$ {v / 1e3:.1f} mil".replace(".", ",")
    return f"R$ {_br(v)}"


def _colunas(rid: str, titulo: str) -> list[dict]:
    """As colunas do contrato (§10.10.2) como o robô manda, com o selo de cada coluna marcada."""
    out = []
    for n, tp, o in tabelas.COLUNAS_RID[(rid, titulo)]:
        c = {"nome": n, "tipo": tp, "largura": 90, "oculta": o}
        sel = tabelas.SELOS_RID.get((rid, titulo), {}).get(n)
        if sel == "texto":
            c["chip"] = deepcopy(CHIP)
        elif sel == "tom":
            c["chip_tom"] = "TOM SLA"
        out.append(c)
    return out


def _linha(cols, valores):
    nomes = [c["nome"] for c in cols]
    extra = set(valores) - set(nomes)
    assert not extra, extra
    return [valores.get(n) for n in nomes]


def _tabela(rid, titulo, registros, **extra):
    cols = _colunas(rid, titulo)
    t = {"titulo": titulo, "colunas": cols, "linhas": [_linha(cols, r) for r in registros], "tons": [""] * len(registros)}
    t.update(extra)
    return t


def _kpi(rot, valor, cor="neutro", det=""):
    return {"rotulo": rot, "valor": valor, "cor": cor, "detalhe": det}


def _painel(titulo, rotulos, valores, formato, tempo=False, insights=None):
    """Como o PC: o ranking (hbarras) ou o gráfico no tempo (barras), sem cor solta (a web usa a do tema)."""
    graf = ({"tipo": "barras", "row": 0, "col": 1, "colspan": 2,
             "grafico": {"titulo": titulo, "rotulos": rotulos, "formato": formato,
                         "series": [{"nome": titulo, "valores": valores}]}} if tempo else
            {"tipo": "hbarras", "titulo": titulo, "row": 0, "col": 1, "colspan": 2, "formato": formato,
             "rotulos": rotulos, "valores": valores})
    if insights == []:                                   # NCC: sem painel no PC, só os gráficos (§10.10.1)
        return {"blocos": [{**graf, "col": 0, "colspan": 3}]}
    return {"blocos": [{"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 0,
                        "linhas": [["info", t] for t in (insights or ["Números de exemplo, todos fictícios."])]}, graf]}


# ------------------------------------------------------------------ Garantias
STATUS_G = ["ABERTO", "EM TRATATIVA", "FINALIZADA", "CANCELADA"]
RESULTADOS_G = ["PENDENTE", "PROCEDENTE", "IMPROCEDENTE"]
N_G = 12


def garantias_registros() -> list[dict]:
    """12 garantias: 1 a 6 abertas (1 a 3 atrasadas), 7 a 10 procedentes e 11 e 12 improcedentes (finalizadas)."""
    out = []
    for i in range(1, N_G + 1):
        cid, uf = CIDADES[i % 5]
        sol = HOJE - timedelta(days=60 - i * 3)
        aberta = i <= 6
        atrasada = i <= 3
        fech = sol + timedelta(days=21) if not aberta else sol + timedelta(days=21)
        out.append({
            "TICKET": f"G-{i:04d}", "CLIENTE": _cli(i), "CIDADE": cid, "CÓD. CLIENTE": f"9{i:05d}",
            "STATUS": ("ABERTO" if i % 2 else "EM TRATATIVA") if aberta else "FINALIZADA",
            "RESULTADO ANÁLISE": "PENDENTE" if aberta else ("PROCEDENTE" if i <= 10 else "IMPROCEDENTE"),
            "DT. SOLICITAÇÃO": _iso(sol), "DT. FECHAMENTO": _iso(fech),
            "SLA ATUAL": (HOJE - sol).days if aberta else 18 + i % 4,
            "PRAZO": "ATRASADA" if atrasada else ("NO PRAZO" if aberta else ("FECHADA NO PRAZO" if i <= 10 else "FECHADA COM ATRASO")),
            "CÓD. PRODUTO": f"PROD-{i % 5 + 1:03d}", "DESCRIÇÃO PRODUTO": f"PRODUTO FICTICIO {i % 5 + 1:02d}",
            "QTD": float(1 + i % 3), "PENDÊNCIAS": "AGUARDANDO FOTO" if i == 2 else "",
            "RETORNO DO CLIENTE": "", "VENDEDOR": _vend(i), "SUPERVISOR": _sup(i),
            "SITUAÇÃO DO PRAZO": "ATRASADA" if atrasada else "NO PRAZO", "TOM SLA": "alerta" if atrasada else ("ok" if aberta else "cinza"),
            "DT. FECHOU": None if aberta else _iso(fech), "RECLAMAÇÃO": "PEÇA CHEGOU COM DEFEITO" if i == 1 else "",
            "OBSERVAÇÃO": "", "DT. RETORNO": None})
    return out


def historico_registros(n=40) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        cid, _ = CIDADES[i % 5]
        d = HOJE - timedelta(days=i * 4)
        out.append({"CÓD. CLIENTE": f"9{i % 12 + 1:05d}", "RAZÃO SOCIAL": f"RAZAO FICTICIA {i % 12 + 1:02d}",
                    "FANTASIA": f"FANTASIA FICTICIA {i % 12 + 1:02d}", "CIDADE": cid, "PEDIDO": f"P{i:05d}",
                    "PED. MÁXIMA": f"P{i:05d}", "NF": f"{5000 + i}", "PRAZO": "30/60", "DT. PEDIDO": _iso(d),
                    "DT. NF": _iso(d + timedelta(days=1)), "DT. ENTREGA": _iso(d + timedelta(days=5)),
                    "TRANSPORTADORA": "TRANSPORTADORA FICTICIA 1", "RESPONSÁVEL": "MOTORISTA FICTICIO 1",
                    "CÓD. PRODUTO": f"PROD-{i % 5 + 1:03d}", "DESCRIÇÃO": f"PRODUTO FICTICIO {i % 5 + 1:02d}",
                    "QTD": float(1 + i % 4), "VALOR": 100.0 * (1 + i % 7), "VENDEDOR": _vend(i), "FILIAL": FILIAL_DE[CIDADES[i % 5][1]]})
    return out


def _soma(linhas, cols, nomes):
    tot = [None] * len(cols)
    for nome in nomes:
        k = [c["nome"] for c in cols].index(nome)
        tot[k] = sum(ln[k] or 0 for ln in linhas)
    tot[0] = "TOTAL"
    return tot


def spec_garantias(t: dict) -> dict:
    n = len(t["linhas"])
    nomes = [c["nome"] for c in t["colunas"]]
    ich = nomes.index("TICKET")
    longo = {"caixa": True, "max": 600, "multilinha": True}
    return {"modulo": "garantias", "acao": "Editar", "novo": {"rotulo": "Nova garantia"},
            "chaves": [str(ln[ich]) for ln in t["linhas"]],
            "campos": [
                {"campo": "ticket", "rotulo": "TICKET", "coluna": "TICKET", "tipo": "texto", "opcoes": [], "padrao": "G-0013"},
                {"campo": "dt_solicitacao", "rotulo": "DT. SOLICITAÇÃO", "coluna": "DT. SOLICITAÇÃO", "tipo": "data",
                 "opcoes": [], "padrao": "@hoje"},
                {"campo": "dt_prazo", "rotulo": "DT. FECHAMENTO (PRAZO)", "coluna": "DT. FECHAMENTO", "tipo": "data", "opcoes": []},
                {"campo": "dt_retorno", "rotulo": "DT. RETORNO", "coluna": "DT. RETORNO", "tipo": "data", "opcoes": []},
                {"campo": "status", "rotulo": "STATUS", "coluna": "STATUS", "tipo": "lista", "opcoes": STATUS_G, "padrao": "ABERTO"},
                {"campo": "resultado", "rotulo": "RESULTADO ANÁLISE", "coluna": "RESULTADO ANÁLISE", "tipo": "lista",
                 "opcoes": RESULTADOS_G, "padrao": "PENDENTE"},
                {"campo": "cod_cliente", "rotulo": "CÓD. CLIENTE", "coluna": "CÓD. CLIENTE", "tipo": "texto", "opcoes": []},
                {"campo": "cod_produto", "rotulo": "CÓD. PRODUTO", "coluna": "CÓD. PRODUTO", "tipo": "texto", "opcoes": []},
                {"campo": "descricao", "rotulo": "DESCRIÇÃO PRODUTO", "coluna": "DESCRIÇÃO PRODUTO", "tipo": "texto",
                 "opcoes": [], "caixa": True},
                {"campo": "qtd", "rotulo": "QTD", "coluna": "QTD", "tipo": "texto", "opcoes": []},
                {"campo": "reclamacao", "rotulo": "RECLAMAÇÃO", "coluna": "RECLAMAÇÃO", "tipo": "texto", "opcoes": [], **longo},
                {"campo": "pendencias", "rotulo": "PENDÊNCIAS", "coluna": "PENDÊNCIAS", "tipo": "texto", "opcoes": [], **longo},
                {"campo": "retorno_cliente", "rotulo": "RETORNO DO CLIENTE", "coluna": "RETORNO DO CLIENTE", "tipo": "texto",
                 "opcoes": [], **longo},
                {"campo": "observacao", "rotulo": "OBSERVAÇÃO", "coluna": "OBSERVAÇÃO", "tipo": "texto", "opcoes": [], **longo}]}


def farol_garantias(com_historico=True) -> dict:
    rid = "pl_garantias"
    reg = garantias_registros()
    ab = [r for r in reg if r["RESULTADO ANÁLISE"] == "PENDENTE"]
    atras = [r for r in reg if r["PRAZO"] == "ATRASADA"]
    proc = [r for r in reg if r["RESULTADO ANÁLISE"] == "PROCEDENTE"]
    imp = [r for r in reg if r["RESULTADO ANÁLISE"] == "IMPROCEDENTE"]
    fin = [r for r in reg if r["STATUS"] == "FINALIZADA"]
    sem_trat = [r for r in ab if r["STATUS"] == "ABERTO"]
    sla_medio = sum(r["SLA ATUAL"] for r in fin) / len(fin)
    kpis = [_kpi("Em aberto", str(len(ab)), "atencao", f"{len(sem_trat)} sem tratativa"),
            _kpi("Atrasadas", str(len(atras)), "alerta", "abertas depois da DT. FECHAMENTO"),
            _kpi("Análise pendente", str(len(ab))), _kpi("Procedentes", str(len(proc)), "ok"),
            _kpi("Improcedentes", str(len(imp))),
            _kpi("SLA médio (finalizadas)", f"{sla_medio:.0f} dias", "neutro", f"{len(fin)} finalizadas")]
    t_g = _tabela(rid, "Garantias", reg, filtros=["STATUS", "RESULTADO ANÁLISE", "PRAZO", "CIDADE", "VENDEDOR"],
                  kpis_padrao=deepcopy(kpis),
                  recortes_linhas=[{"rotulo": "Em aberto", "linhas": [k for k, r in enumerate(reg) if r in ab]},
                                   {"rotulo": "Atrasadas", "linhas": [k for k, r in enumerate(reg) if r in atras]}])
    t_g["edicao"] = spec_garantias(t_g)
    tabs = [t_g]
    if com_historico:
        hist = historico_registros()
        cols = _colunas(rid, "Histórico de compra")
        th = _tabela(rid, "Histórico de compra", hist, filtros=[],
                     kpis_padrao=[_kpi("Pedidos", str(len({h["PEDIDO"] for h in hist})), "neutro", f"{len({h['NF'] for h in hist})} notas"),
                                  _kpi("Itens", str(len(hist)), "neutro", f"{int(sum(h['QTD'] for h in hist))} unidades"),
                                  _kpi("Valor comprado", moeda(sum(h["VALOR"] for h in hist)))])
        th["total"] = _soma(th["linhas"], cols, ("QTD", "VALOR"))
        tabs.append(th)
    prods = {}
    for r in reg:
        p = prods.setdefault(r["CÓD. PRODUTO"], {"CÓD. PRODUTO": r["CÓD. PRODUTO"], "DESCRIÇÃO": r["DESCRIÇÃO PRODUTO"],
                                                  "GARANTIAS": 0, "EM ABERTO": 0, "PROCEDENTES": 0, "IMPROCEDENTES": 0})
        p["GARANTIAS"] += 1
        p["EM ABERTO"] += r["RESULTADO ANÁLISE"] == "PENDENTE"
        p["PROCEDENTES"] += r["RESULTADO ANÁLISE"] == "PROCEDENTE"
        p["IMPROCEDENTES"] += r["RESULTADO ANÁLISE"] == "IMPROCEDENTE"
    tabs.append(_tabela(rid, "Por produto", sorted(prods.values(), key=lambda x: -x["GARANTIAS"]), filtros=[]))
    cruz = []
    for st in ("ABERTO", "EM TRATATIVA", "FINALIZADA"):
        sub = [r for r in reg if r["STATUS"] == st]
        pen, pro, imp_ = (sum(r["RESULTADO ANÁLISE"] == x for r in sub) for x in RESULTADOS_G)
        cruz.append({"STATUS": st, "PENDENTE": pen, "PROCEDENTE": pro, "IMPROCEDENTE": imp_, "TOTAL": len(sub)})
    tabs.append(_tabela(rid, "Status x resultado", cruz, filtros=[]))
    return {"forma": "farol", "titulo": "Farol de Garantias", "kpis": kpis,
            "painel": _painel("Garantias por produto", [p["CÓD. PRODUTO"] for p in prods.values()],
                              [p["GARANTIAS"] for p in prods.values()], "int"),
            "insights_painel": [["alerta", f"Atrasadas: {len(atras)} (abertas depois da DT. FECHAMENTO)."]],
            "avisos": ["Sem filtro por estado: os cartões mostram a BAP inteira."], "tabelas": tabs, "baixado_em": BAIXADO}


# ------------------------------------------------------------------ Devoluções
ETAPAS_D = ["AGUARDANDO RECEBIMENTO", "RECEBIDA", "EM ANÁLISE", "CRÉDITO LIBERADO", "CONCLUÍDA"]
MOTIVOS_D = ["PRODUTO ERRADO", "AVARIA NO TRANSPORTE", "DESISTÊNCIA", "DEFEITO", "OUTROS"]
FATURADO_NOV = 1_200_000.0


def devolucoes_registros() -> list[dict]:
    out = []
    for i in range(1, 15):
        nov = i <= 10
        cid, uf = CIDADES[i % 5]
        d = date(2026, 11, 2 + i) if nov else date(2026, 10, 5 + i)
        concl = i % 3 == 0
        out.append({"MÊS": "NOV/26" if nov else "OUT/26", "DATA": _iso(d), "NF DEV.": f"{7000 + i}", "FILIAL": FILIAL_DE[uf],
                    "CLIENTE": f"9{i:05d} - {_cli(i)}", "CIDADE": cid, "UF": uf, "VENDEDOR": _vend(i),
                    "VALOR": 350.0 * (1 + i % 6), "ITENS": 1 + i % 4, "PRODUTOS": f"PRODUTO FICTICIO {i % 5 + 1:02d}",
                    "ETAPA": ETAPAS_D[4 if concl else i % 3], "MOTIVO": "" if i in (1, 2, 3) else MOTIVOS_D[i % 5],
                    "AUTORIZADO POR": "" if i % 2 else "GERENTE FICTICIO", "RECEBIDA EM": _iso(d + timedelta(days=3)) if concl else None,
                    "CRÉDITO": "CRÉDITO EM CONTA" if concl else "", "CRÉDITO EM": _iso(d + timedelta(days=6)) if concl else None,
                    "RESPONSÁVEL": "ASSISTENTE FICTICIA" if i % 2 else ""})
    return out


def farol_devolucoes() -> dict:
    rid = "pl_devolucoes"
    reg = devolucoes_registros()
    nov = [r for r in reg if r["MÊS"] == "NOV/26"]
    val = sum(r["VALOR"] for r in nov)

    def cartoes(rs, fat):
        v = sum(r["VALOR"] for r in rs)
        ab = [r for r in rs if r["ETAPA"] != "CONCLUÍDA"]
        return [_kpi("Devoluções", str(len(rs)), "alerta", moeda(v)),
                _kpi("% do faturado", f"{100 * v / fat:.0f}%", "alerta"),
                _kpi("Clientes", str(len({r["CLIENTE"] for r in rs}))),
                _kpi("Abertas no acompanhamento", str(len(ab)), "atencao"),
                _kpi("Sem motivo", str(sum(1 for r in rs if not r["MOTIVO"])), "alerta")]
    kpis = cartoes(nov, FATURADO_NOV)
    por_uf = {u: [r for r in nov if r["UF"] == u] for u in UF_ORDEM}
    rec = {u: {"kpis": cartoes(rs, FATURADO_NOV / 5)} for u, rs in por_uf.items() if rs}
    cols = _colunas(rid, "Devoluções")
    t_d = _tabela(rid, "Devoluções", reg, kpis_padrao=deepcopy(kpis), uf_linhas=[r["UF"] for r in reg],
                  filtros=[{"coluna": "MÊS", "padrao": "NOV/26"}, "FILIAL", "VENDEDOR", "MOTIVO", "ETAPA"])
    t_d["edicao"] = {
        "modulo": "pos_venda", "acao": "Editar", "chaves": [f"0101001|{r['NF DEV.']}|1" for r in reg],
        "campos": [
            {"campo": "etapa", "rotulo": "ETAPA", "coluna": "ETAPA", "tipo": "lista", "opcoes": ETAPAS_D},
            {"campo": "motivo", "rotulo": "MOTIVO", "coluna": "MOTIVO", "tipo": "lista", "opcoes": MOTIVOS_D},
            {"campo": "autorizado_por", "rotulo": "AUTORIZADO POR", "coluna": "AUTORIZADO POR", "tipo": "lista",
             "opcoes": ["GERENTE FICTICIO", "DIRETOR FICTICIO"]},
            {"campo": "recebida_em", "rotulo": "RECEBIDA EM", "coluna": "RECEBIDA EM", "tipo": "data",
             "opcoes": [f"{HOJE - timedelta(days=k):%d/%m/%Y}" for k in range(30)]},
            {"campo": "credito", "rotulo": "FORMA DO CRÉDITO", "coluna": "CRÉDITO", "tipo": "lista",
             "opcoes": ["CRÉDITO EM CONTA", "ABATIMENTO EM TÍTULO", "ESTORNO"]},
            {"campo": "credito_em", "rotulo": "CRÉDITO EM", "coluna": "CRÉDITO EM", "tipo": "data",
             "opcoes": [f"{HOJE - timedelta(days=k):%d/%m/%Y}" for k in range(30)]},
            {"campo": "responsavel", "rotulo": "RESPONSÁVEL", "coluna": "RESPONSÁVEL", "tipo": "lista",
             "opcoes": ["ASSISTENTE FICTICIA", "ASSISTENTE FICTICIA 2"]}]}
    mot = {}
    for r in reg:
        m = mot.setdefault((r["MÊS"], r["MOTIVO"] or "(sem motivo)"), {"MÊS": r["MÊS"], "MOTIVO": r["MOTIVO"] or "(sem motivo)",
                                                                       "DEVOLUÇÕES": 0, "VALOR": 0.0})
        m["DEVOLUÇÕES"] += 1
        m["VALOR"] += r["VALOR"]
    vend = {}
    for r in reg:
        v = vend.setdefault(r["VENDEDOR"], {"VENDEDOR": r["VENDEDOR"], "DEVOLUÇÕES": 0, "VALOR": 0.0, "FATURADO 12M": 3_000_000.0})
        v["DEVOLUÇÕES"] += 1
        v["VALOR"] += r["VALOR"]
    for v in vend.values():
        v["% DEVOLVIDO"] = round(100 * v["VALOR"] / v["FATURADO 12M"], 2)
    cli = {}
    for r in reg:
        c = cli.setdefault(r["CLIENTE"], {"CLIENTE": r["CLIENTE"], "DEVOLUÇÕES": 0, "VALOR": 0.0})
        c["DEVOLUÇÕES"] += 1
        c["VALOR"] += r["VALOR"]
    prod = {}
    for r in reg:
        p = prod.setdefault(r["PRODUTOS"], {"PRODUTO": f"PROD-{r['PRODUTOS'][-2:]}", "DESCRIÇÃO": r["PRODUTOS"], "QTD": 0.0, "VALOR": 0.0})
        p["QTD"] += r["ITENS"]
        p["VALOR"] += r["VALOR"]
    tabs = [t_d, _tabela(rid, "Por motivo", list(mot.values()), filtros=[{"coluna": "MÊS", "padrao": "NOV/26"}]),
            _tabela(rid, "Por vendedor (12 meses)", list(vend.values()), filtros=[]),
            _tabela(rid, "Por cliente (12 meses)", list(cli.values()), filtros=[]),
            _tabela(rid, "Por produto (12 meses)", list(prod.values()), filtros=[])]
    return {"forma": "farol", "titulo": "Farol de Devolução e Reembolsos", "kpis": kpis,
            "painel": _painel("Valor devolvido (R$) · mês a mês", ["OUT", "NOV"],
                              [sum(r["VALOR"] for r in reg if r["MÊS"] == m) for m in ("OUT/26", "NOV/26")], "moeda", tempo=True,
                              insights=[f"Sem motivo informado: {sum(1 for r in nov if not r['MOTIVO'])} notas em NOV."]),
            "insights_painel": [["alerta", f"Sem motivo informado: {sum(1 for r in nov if not r['MOTIVO'])} notas em NOV."]],
            "avisos": [], "recortes": rec, "tabelas": tabs, "baixado_em": BAIXADO}


# ------------------------------------------------------------------ NCC
STATUS_N = ["A COMPENSAR", "COMPENSAR JÁ (TÍTULO ABERTO)", "CONTATAR CLIENTE", "AGUARDANDO CLIENTE", "COMPENSADA"]
IDADES = ["0-30 DIAS", "31-90 DIAS", "91-180 DIAS", "+180 DIAS"]


def ncc_registros() -> list[dict]:
    out = []
    for i in range(1, 12):
        cid, uf = CIDADES[i % 5]
        dias = [12, 25, 48, 70, 95, 110, 150, 190, 210, 240, 20][i - 1]
        saldo = 400.0 * (1 + i % 5) + 7.5 * i
        sla_atr = i >= 2
        out.append({"A COMPENSAR": STATUS_N[1] if i in (1, 4, 6, 7) else STATUS_N[2 if i % 2 else 0],
                    "SLA NCC": "SLA ATRASADO" if sla_atr else "NO SLA", "DT. ÚLT. MOV.": _iso(HOJE - timedelta(days=dias // 3)),
                    "D.U. S/ MOV.": dias // 5, "IDADE": IDADES[0 if dias <= 30 else 1 if dias <= 90 else 2 if dias <= 180 else 3],
                    "FILIAL": FILIAL_DE[uf], "NCC": f"{900 + i}", "PARC.": "01", "EMISSÃO": _iso(HOJE - timedelta(days=dias)),
                    "DIAS": dias, "CLIENTE": f"9{(i + 1) // 2:05d}", "NOME": _cli((i + 1) // 2), "CIDADE": cid, "UF": uf,
                    "VENDEDOR": _vend(i), "SUPERVISOR": _sup(i), "VALOR NCC": saldo + 100.0, "JÁ ABATIDO": 100.0, "SALDO": saldo,
                    "TÍTULOS EM ABERTO": 0.0 if i % 2 else 1500.0, "PEDIDO EM ABERTO": None, "ÚLTIMA COMPRA": _iso(HOJE - timedelta(days=dias // 2))})
    return out


def _agrupa(reg, chave, nome):
    g = {}
    for r in reg:
        x = g.setdefault(r[chave], {nome: r[chave], "NCC": 0, "CLIENTES": set(), **{f: 0.0 for f in IDADES}, "SALDO": 0.0, "COMPENSAR JÁ": 0.0})
        x["NCC"] += 1
        x["CLIENTES"].add(r["CLIENTE"])
        x[r["IDADE"]] += r["SALDO"]
        x["SALDO"] += r["SALDO"]
        x["COMPENSAR JÁ"] += r["SALDO"] if r["A COMPENSAR"] == STATUS_N[1] else 0.0
    for x in g.values():
        x["CLIENTES"] = len(x["CLIENTES"])
    return list(g.values())


def farol_ncc() -> dict:
    rid = "pl_ncc"
    reg = ncc_registros()

    def cartoes(rs):
        s = sum(r["SALDO"] for r in rs)
        ja = [r for r in rs if r["A COMPENSAR"] == STATUS_N[1]]
        return [_kpi("Saldo a compensar", moeda(s), "atencao", f"{len(rs)} NCC · {len({r['CLIENTE'] for r in rs})} clientes"),
                _kpi("Compensar já", moeda(sum(r["SALDO"] for r in ja)), "info", f"{len({r['CLIENTE'] for r in ja})} clientes · título ou pedido aberto"),
                _kpi("Acima de 90 dias", moeda(sum(r["SALDO"] for r in rs if r["DIAS"] > 90)), "alerta",
                     f"{sum(1 for r in rs if r['DIAS'] > 90)} NCC"),
                _kpi("SLA atrasado (3 d.u.)", str(sum(1 for r in rs if r["SLA NCC"] == "SLA ATRASADO")), "alerta")]
    kpis = cartoes(reg)
    kpis[0]["estados"] = {"barras": [[u, sum(r["SALDO"] for r in reg if r["UF"] == u),
                                      moeda(sum(r["SALDO"] for r in reg if r["UF"] == u)), "", ""]
                                     for u in UF_ORDEM if any(r["UF"] == u for r in reg)], "legenda": ""}
    rec = {u: {"kpis": cartoes([r for r in reg if r["UF"] == u])} for u in UF_ORDEM if any(r["UF"] == u for r in reg)}
    t_n = _tabela(rid, "NCC pendentes", reg, uf_linhas=[r["UF"] for r in reg], kpis_padrao=deepcopy(kpis),
                  filtros=["A COMPENSAR", "SLA NCC", "IDADE", "FILIAL", "VENDEDOR", "SUPERVISOR", "UF"],
                  recortes_linhas=[{"rotulo": "SLA atrasado", "linhas": [k for k, r in enumerate(reg) if r["SLA NCC"] == "SLA ATRASADO"]},
                                   {"rotulo": "Acima de 90 dias", "linhas": [k for k, r in enumerate(reg) if r["DIAS"] > 90]}])
    nomes = [c["nome"] for c in t_n["colunas"]]
    t_n["edicao"] = {
        "modulo": "ncc", "acao": "Editar",
        "chaves": [f"0101001|001|{r['NCC']}|01" for r in reg],
        "campos": [{"campo": "status", "rotulo": "A COMPENSAR", "coluna": "A COMPENSAR", "tipo": "lista", "opcoes": STATUS_N},
                   {"campo": "dt_mov", "rotulo": "DT. ÚLT. MOV.", "coluna": "DT. ÚLT. MOV.", "tipo": "data", "opcoes": []}]}
    assert "A COMPENSAR" in nomes
    cli = {}
    for r in reg:
        c = cli.setdefault(r["CLIENTE"], {"A COMPENSAR": r["A COMPENSAR"], "IDADE": r["IDADE"], "CLIENTE": r["CLIENTE"], "NOME": r["NOME"],
                                          "CIDADE": r["CIDADE"], "UF": r["UF"], "VENDEDOR": r["VENDEDOR"], "SUPERVISOR": r["SUPERVISOR"],
                                          "NCC": 0, "SALDO": 0.0, "NCC MAIS ANTIGA (DIAS)": 0, "TÍTULOS EM ABERTO": r["TÍTULOS EM ABERTO"],
                                          "PEDIDO EM ABERTO": None, "ÚLTIMA COMPRA": r["ÚLTIMA COMPRA"]})
        c["NCC"] += 1
        c["SALDO"] += r["SALDO"]
        c["NCC MAIS ANTIGA (DIAS)"] = max(c["NCC MAIS ANTIGA (DIAS)"], r["DIAS"])
    t_c = _tabela(rid, "Por cliente", list(cli.values()), filtros=["A COMPENSAR", "IDADE", "VENDEDOR", "SUPERVISOR", "UF"])
    t_c["total"] = _soma(t_c["linhas"], t_c["colunas"], ("NCC", "SALDO"))
    tabs = [t_n, t_c]
    for tit, ch in (("Por filial", "FILIAL"), ("Por vendedor", "VENDEDOR"), ("Por supervisor", "SUPERVISOR")):
        t = _tabela(rid, tit, _agrupa(reg, ch, ch), filtros=[])
        t["total"] = _soma(t["linhas"], t["colunas"], ("NCC", "CLIENTES") + tuple(IDADES) + ("SALDO", "COMPENSAR JÁ"))
        tabs.append(t)
    return {"forma": "farol", "titulo": "Farol de NCC", "kpis": kpis,
            "painel": _painel("Saldo por faixa de idade (R$)", IDADES, [sum(r["SALDO"] for r in reg if r["IDADE"] == f) for f in IDADES], "moeda", insights=[]),
            "insights_painel": [], "avisos": [], "recortes": rec, "tabelas": tabs, "baixado_em": BAIXADO}


def pacote_posvenda(gerado_em="2026-11-24T08:30:00-04:00", **so) -> dict:
    rels = {"pl_garantias": farol_garantias(), "pl_devolucoes": farol_devolucoes(), "pl_ncc": farol_ncc()}
    rels.update(so)
    return {"versao_contrato": 1, "gerado_em": gerado_em, "ano": 2026, "mes": 11, "relatorios": rels}
