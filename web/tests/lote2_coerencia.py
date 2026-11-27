"""T-0024 (reteste de UX, N3): torna o pacote FICTÍCIO dos 5 faróis do lote 2 coerente. A faixa, o TOTAL das tabelas, os
recortes por estado e os gráficos saem da MESMA conta das linhas das tabelas (uma partição de totais inventados).
Só valores fictícios; a estrutura (abas, colunas, cartões) continua a do robô (lote2_estrutura.py)."""
from __future__ import annotations

from datetime import date, timedelta

HOJE = date(2026, 11, 24)
ULTIMO_DIA = 23                                     # hoje fica fora (regra 4)
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
ROTULO_MESES = ["DEZ"] + MESES[:11]                 # 12 meses, o último é NOV/26
FILIAIS = ["AM", "AP", "MA", "MT", "PA", "RR"]
CIDADE_DA_UF = {"AM": "MANAUS", "AP": "MACAPÁ", "MA": "SÃO LUÍS", "MT": "CUIABÁ", "PA": "BELÉM", "RR": "BOA VISTA"}

BASE = {"CLIENTES": 2930, "ATIVOS": 2410, "COMPRARAM NO MÊS": 1540, "NUNCA COMPRARAM": 240, "COM LIMITE": 1690,
        "C/ LIMITE E S/ COMPRA": 507, "LIMITE DISP.": 8_790_000.0, "RECEITA 6M": 41_000_000.0, "META": 9_600_000.0,
        "REALIZADO": 6_900_000.0}
ROTA = {"BASE PLANNER": 2610, "BASE PROTHEUS": 2625, "BASE VISITA": 2349, "VISITAS/MÊS": 2600,
        "VISITAS/MÊS DIAS ÚTEIS": 2470, "COM LIMITE": 1960, "INADIMPL.": 290, "COMPRADORES": 1080}
GIRO = {"SKUs C/ ESTOQUE": 4120, "ESTOQUE UN.": 310_000, "VENDA 90D UN.": 112_000, "ITENS EM RUPTURA": 24,
        "ITENS A COMPRAR": 32, "SUGESTÃO UN.": 5400, "CURVA A PARADA (ITENS)": 18, "VENDA PERDIDA PREVISTA": 148_000.0}


# --------------------------------------------------------------------------- ajudas
def pt(n, dec=0):
    s = f"{n:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def moeda_curta(v):
    return f"R$ {pt(v / 1e6, 1)} mi" if v >= 1e6 else f"R$ {pt(v / 1e3, 0)} mil"


def reparte(total, n, pesos):
    """Divide `total` em `n` partes proporcionais aos pesos; a soma das partes é exatamente `total`."""
    soma = sum(pesos)
    if isinstance(total, int):
        partes = [int(total * p / soma) for p in pesos]
        resto = total - sum(partes)
        for k in range(resto):                        # o resto vai de 1 em 1, sem inflar a última parte
            partes[k % len(partes)] += 1
        return partes
    partes = [round(total * p / soma, 2) for p in pesos]
    partes[-1] = round(partes[-1] + total - sum(partes), 2)
    return partes


def pesos(n, plano=False, desvio=0):
    """Pesos da partição. `desvio` muda a razão entre duas colunas (ex.: compraram × ativos) sem quebrar o <=."""
    if plano:
        return [10 + (k * 3) % 5 for k in range(n)]
    base = [2 + (k * 7 + 3) % 9 for k in range(n)]
    return [p * (40 + (k * (7 + desvio)) % 21) for k, p in enumerate(base)] if desvio else base


def tabela(rel, titulo):
    return next((t for t in rel["tabelas"] if t["titulo"] == titulo), None)


def idx(t, nome):
    return [c["nome"] for c in t["colunas"]].index(nome)


def col(t, nome):
    i = idx(t, nome)
    return [ln[i] for ln in t["linhas"]]


def poe(t, nome, valores):
    i = idx(t, nome)
    for ln, v in zip(t["linhas"], valores):
        ln[i] = v


def tem(t, *nomes):
    ns = [c["nome"] for c in t["colunas"]]
    return all(x in ns for x in nomes)


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def refaz_total(t):
    """TOTAL = soma das colunas aditivas das linhas; % = razão das somas; o resto fica vazio."""
    if t.get("total") is None:
        return
    razoes = {"% POSITIVAÇÃO": ("COMPRARAM NO MÊS", "ATIVOS"), "% COMPRADORES": ("COMPRADORES", "BASE PLANNER")}
    tot = []
    for k, c in enumerate(t["colunas"]):
        n = c["nome"]
        if k == 0:
            tot.append("TOTAL")
        elif n in razoes and tem(t, *razoes[n]):
            a, b = (sum(col(t, x)) for x in razoes[n])
            tot.append(pct(a, b))
        elif c["tipo"] in ("int", "num", "moeda") and not any(s in n for s in ("%", "/DIA", "GIRO", "COB", "MIX")):
            tot.append(round(sum(v or 0 for v in col(t, n)), 2))
        else:
            tot.append(None)
    t["total"] = tot


def kpi(rel, rotulo, valor, detalhe=None):
    for k in rel["kpis"]:
        if k["rotulo"] == rotulo:
            k["valor"] = valor
            if k.get("detalhe") and detalhe is not None:
                k["detalhe"] = detalhe
            elif not k.get("detalhe"):
                k["detalhe"] = ""
            return


def bloco(rel, prefixo):
    return next((b for b in rel["painel"]["blocos"] if (b.get("titulo") or (b.get("grafico") or {}).get("titulo", "")).startswith(prefixo)), None)


def serie(b, k=0):
    return b["grafico"]["series"][k]["valores"]


def poe_barras(b, rotulos, *valores):
    g = b["grafico"]
    g["rotulos"] = rotulos
    for s, v in zip(g["series"], valores):
        s["valores"] = v


def dias_uteis_ate(ultimo=ULTIMO_DIA):
    return [d for d in range(1, ultimo + 1) if date(2026, 11, d).weekday() < 5]


def diario(total, n_dias=ULTIMO_DIA, inteiro=True):
    """Valores dia a dia (só dia útil), somando exatamente `total`."""
    uteis = dias_uteis_ate(n_dias)
    partes = reparte(total, len(uteis), [8 + (d * 5) % 5 for d in uteis])
    por_dia = dict(zip(uteis, partes))
    return [por_dia.get(d, 0) for d in range(1, n_dias + 1)]


def semanal(diarios):
    return [sum(diarios[i:i + 7]) for i in range(0, len(diarios), 7)]


def blocos_periodo(rel, metrica, mtd, nivel=None, inteiro=True):
    """Os 3 gráficos (dia a dia, semana a semana, mês a mês) de uma métrica, coerentes entre si: a semana é a soma dos
    dias, e o último mês é o acumulado do mês até ontem."""
    d = diario(mtd, inteiro=inteiro)
    s = semanal(d)
    ant = reparte(mtd * 11, 11, [9 + (k * 4) % 4 for k in range(11)]) if inteiro else [mtd] * 11
    for prefixo, rot, vals in ((f"{metrica} · dia a dia", [f"{x:02d}" for x in range(1, ULTIMO_DIA + 1)], d),
                               (f"{metrica} · semana a semana", [f"S{k + 1}" for k in range(len(s))], s),
                               (f"{metrica} · mês a mês", ROTULO_MESES, ant + [mtd])):
        b = bloco(rel, prefixo)
        if b:
            poe_barras(b, rot, vals)


# --------------------------------------------------------------------------- Clientes
def coerencia_base(rel):
    for titulo in ("Por UF", "Por segmento", "Por cidade", "Por vendedor", "Por supervisor"):
        t = tabela(rel, titulo)
        n = len(t["linhas"])
        for nome, total in BASE.items():
            if nome in [c["nome"] for c in t["colunas"]]:
                poe(t, nome, reparte(total, n, pesos(n, desvio=3 if nome in ("COMPRARAM NO MÊS", "REALIZADO") else 0)))
        cli, ativos, comp, nunca, comlim = (col(t, x) for x in ("CLIENTES", "ATIVOS", "COMPRARAM NO MÊS", "NUNCA COMPRARAM", "COM LIMITE"))
        poe(t, "% POSITIVAÇÃO", [pct(a, b) for a, b in zip(comp, ativos)])
        poe(t, "OPORTUNIDADE (FALTA)", [round(m - r, 2) for m, r in zip(col(t, "META"), col(t, "REALIZADO"))])
        if "BASE PROTHEUS" in [c["nome"] for c in t["colunas"]]:
            poe(t, "BASE PROTHEUS", [c + max(1, c // 100) for c in cli])
        if titulo == "Por cidade":                       # cidade tem nome próprio; a UF é a da cidade
            poe(t, "CIDADE", [f"CIDADE FICTICIA {k + 1:02d}" for k in range(n)])
            poe(t, "UF", [FILIAIS[k % 6] for k in range(n)])
        refaz_total(t)
    t = tabela(rel, "Por UF")
    poe(t, "UF", [["AM", "AP", "MA", "PA", "RR"][k % 5] for k in range(len(t["linhas"]))])
    fam = tabela(rel, "Por família (6 meses)")
    n = len(fam["linhas"])
    ativos = BASE["ATIVOS"]
    comp = [100 + (k * 61) % 1500 for k in range(n)]
    poe(fam, "CLIENTES QUE COMPRAM", comp)
    poe(fam, "% DOS ATIVOS", [pct(c, ativos) for c in comp])
    poe(fam, "ATIVOS QUE NÃO COMPRAM", [ativos - c for c in comp])
    # a tabela Clientes: cidade derivada da UF, atraso <= limite, falta = meta - realizado
    cl = tabela(rel, "Clientes")
    n = len(cl["linhas"])
    ufs = col(cl, "UF")
    poe(cl, "CIDADE", [CIDADE_DA_UF.get(u, "MANAUS") for u in ufs])
    lim = [round(3000.0 + (k * 1370) % 21000, 2) for k in range(n)]
    poe(cl, "LIMITE DISP.", lim)
    poe(cl, "EM ATRASO", [round(l * 0.18, 2) if k % 5 == 0 else 0.0 for k, l in enumerate(lim)])
    meta = [round(4000.0 + (k * 910) % 9000, 2) for k in range(n)]
    real = [round(m * (0.4 + (k % 7) / 8), 2) for k, m in enumerate(meta)]
    poe(cl, "META", meta)
    poe(cl, "REALIZADO", real)
    poe(cl, "FALTA", [round(max(m - r, 0), 2) for m, r in zip(meta, real)])
    # faixa e recortes = Por UF
    uf_t = tabela(rel, "Por UF")
    tot = dict(zip([c["nome"] for c in uf_t["colunas"]], uf_t["total"]))
    kpis_de = lambda v, ref: (("Clientes", pt(v["CLIENTES"])), ("Ativos", pt(v["ATIVOS"]), f"{round(100 * v['ATIVOS'] / v['CLIENTES'])}% dos clientes"),
                              ("Compraram no mês", pt(v["COMPRARAM NO MÊS"]), f"{round(100 * v['COMPRARAM NO MÊS'] / v['CLIENTES'])}% dos clientes"),
                              ("Com limite e sem compra", pt(v["C/ LIMITE E S/ COMPRA"])),
                              ("Limite disponível", moeda_curta(v["LIMITE DISP."])),
                              ("Oportunidade (falta)", moeda_curta(v["OPORTUNIDADE (FALTA)"]), "até a meta"))
    for item in kpis_de(tot, rel):
        kpi(rel, *item)
    for k_uf, rec in rel["recortes"].items():
        linha = next((dict(zip([c["nome"] for c in uf_t["colunas"]], ln)) for ln in uf_t["linhas"] if ln[0] == k_uf), None)
        if not linha:
            continue
        for k in rec["kpis"]:
            for item in kpis_de(linha, rel):
                if item[0] == k["rotulo"]:
                    k["valor"] = item[1]
                    k["detalhe"] = item[2] if len(item) > 2 else ""
    # gráficos
    mtd = BASE["COMPRARAM NO MÊS"]
    blocos_periodo(rel, "Clientes com compra", mtd)
    blocos_periodo(rel, "Faturamento (R$)", int(BASE["REALIZADO"]))
    blocos_periodo(rel, "Clientes novos (1ª compra)", 95)
    seg, ven = tabela(rel, "Por segmento"), tabela(rel, "Por vendedor")
    b = bloco(rel, "Positivação por segmento")
    b["rotulos"], b["valores"] = [x.replace(" FICTICIO", "") for x in col(seg, "SEGMENTO")], col(seg, "% POSITIVAÇÃO")
    b.pop("cores", None)
    b = bloco(rel, "Oportunidade (falta) por vendedor")
    b["rotulos"], b["valores"] = [x.replace(" FICTICIO", "") for x in col(ven, "VENDEDOR")], col(ven, "OPORTUNIDADE (FALTA)")
    b.pop("cores", None)


# --------------------------------------------------------------------------- Roteirização
def coerencia_rota(rel):
    for titulo in ("Por zona", "Por vendedor", "Por supervisor", "Por segmento", "Por UF", "Por cidade"):
        t = tabela(rel, titulo)
        n = len(t["linhas"])
        for nome, total in ROTA.items():
            if nome in [c["nome"] for c in t["colunas"]]:
                poe(t, nome, reparte(total, n, pesos(n, plano=True)))
        du = col(t, "VISITAS/MÊS DIAS ÚTEIS")
        cd = [round(v / 20.0, 2) for v in du]
        poe(t, "CLIENTES/DIA", cd)
        poe(t, "CAPACIDADE/DIA", [max(1, int(-(-c // 0.8))) for c in cd])
        base = col(t, "BASE PLANNER")
        poe(t, "% COMPRADORES", [pct(a, b) for a, b in zip(col(t, "COMPRADORES"), base)])
        if titulo == "Por cidade":
            poe(t, "CIDADE", [f"CIDADE FICTICIA {k + 1:02d}" for k in range(n)])
            poe(t, "UF", [FILIAIS[k % 6] for k in range(n)])
        refaz_total(t)
    ven = tabela(rel, "Por vendedor")
    nomes = [x.replace("VENDEDOR FICTICIO", "VEND.") for x in col(ven, "VENDEDOR")]
    cd, cap = col(ven, "CLIENTES/DIA"), col(ven, "CAPACIDADE/DIA")
    kpi(rel, "Visitas no mês", pt(ROTA["VISITAS/MÊS"]))
    kpi(rel, "Cobertura da carteira", f"{pt(pct(ROTA['BASE VISITA'], ROTA['BASE PROTHEUS']), 1)}%".replace(".", ","))
    kpi(rel, "Positivação da rota", f"{pt(pct(ROTA['COMPRADORES'], ROTA['BASE PLANNER']), 1)}%")
    ocup = [round(100.0 * c / k, 1) for c, k in zip(cd, cap)]
    kpi(rel, "Ocupação da agenda", f"{pt(sum(ocup) / len(ocup), 1)}%")
    b = bloco(rel, "Visitas por dia útil")
    b["rotulos"], b["valores"] = nomes, [float(c) for c in cd]
    b["cores"] = ["#62BB47" if c <= 12 else "#B3261E" for c in cd]
    b = bloco(rel, "Ocupação da agenda")
    b["rotulos"], b["valores"] = nomes, ocup
    b["cores"] = ["#62BB47" if o <= 85 else ("#C98A00" if o <= 95 else "#B3261E") for o in ocup]
    b = bloco(rel, "Positivação da carteira")
    b["rotulos"], b["valores"] = nomes, col(ven, "% COMPRADORES")
    b.pop("cores", None)
    b = bloco(rel, "Visitas no sábado")
    b["rotulos"] = nomes
    b["valores"] = [float(k % 3) for k in range(len(nomes))]
    b["cores"] = ["#C98A00" if k % 3 else "#62BB47" for k in range(len(nomes))]
    # visitas planejadas: dia útil ~ visitas/mês ÷ 20; sábado só o excedente
    b = bloco(rel, "Visitas planejadas")
    g = b["grafico"]
    g["titulo"] = "Visitas planejadas · dia a dia · NOV/26"
    uteis = [d for d in range(1, 31) if date(2026, 11, d).weekday() < 5]
    por_dia = dict(zip(uteis, reparte(ROTA["VISITAS/MÊS"], len(uteis), [10 + (d * 3) % 3 for d in uteis])))
    g["rotulos"] = [f"{d:02d}" for d in range(1, 31)]
    g["series"][0]["valores"] = [por_dia.get(d, 0) for d in range(1, 31)]
    b = bloco(rel, "Clientes positivados")
    g = b["grafico"]
    g["rotulos"] = MESES[:11]
    g["series"][0]["valores"] = [900 + (k * 53) % 190 for k in range(10)] + [ROTA["COMPRADORES"]]


# --------------------------------------------------------------------------- Giro
def coerencia_giro(rel):
    n = len(FILIAIS)
    pf = tabela(rel, "Resumo por filial")
    pf["linhas"] = pf["linhas"][:n]
    pf["tons"] = pf["tons"][:n]
    for nome, total in GIRO.items():
        if nome in [c["nome"] for c in pf["colunas"]]:
            poe(pf, nome, reparte(total, n, pesos(n)))
    poe(pf, "FILIAL", [f"FILIAL FICTICIA {u}" for u in FILIAIS])
    poe(pf, "VENDA/DIA UN.", [round(v / 90.0, 1) for v in col(pf, "VENDA 90D UN.")])
    poe(pf, "MIX QUE GIRA", [round(55.0 + (k * 3) % 14, 1) for k in range(n)])
    # contagens por filial iguais entre a tabela por filial e as de produto
    rup, comp_, par = (reparte(GIRO[x], n, [1] * n) for x in ("ITENS EM RUPTURA", "ITENS A COMPRAR", "CURVA A PARADA (ITENS)"))
    poe(pf, "ITENS EM RUPTURA", rup)
    poe(pf, "ITENS A COMPRAR", comp_)
    poe(pf, "CURVA A PARADA (ITENS)", par)
    for titulo, cont in (("Ruptura", rup), ("Necessidade de compra", comp_), ("Curva A parada", par)):
        t = tabela(rel, titulo)
        filiais = [f"FILIAL FICTICIA {u}" for u, q in zip(FILIAIS, cont) for _ in range(q)]
        t["linhas"] = t["linhas"][:len(filiais)]
        t["tons"] = t["tons"][:len(filiais)]
        poe(t, "FILIAL", filiais)
        if t.get("uf_linhas"):
            t["uf_linhas"] = [x[-2:] for x in filiais]
        refaz_total(t)
    # curva A parada: produto de curva A; produto parado = sem venda recente
    t = tabela(rel, "Curva A parada")
    poe(t, "CURVA", ["A"] * len(t["linhas"]))
    tp = tabela(rel, "Todos os produtos")
    tp["total"] = None                                   # só uma amostra das linhas: sem TOTAL que contrarie a faixa
    si, cu = idx(tp, "SITUAÇÃO"), idx(tp, "CURVA")
    for ln in tp["linhas"]:
        if ln[si] == "A PARADA":
            ln[cu] = "A"
    # faixa
    mix = sum(m * s for m, s in zip(col(pf, "MIX QUE GIRA"), col(pf, "SKUs C/ ESTOQUE"))) / GIRO["SKUs C/ ESTOQUE"]
    kpi(rel, "Estoque FRW + PMZ", moeda_curta(9_800_000.0), f"{pt(GIRO['ESTOQUE UN.'] / 1000)} mil un.")
    kpi(rel, "Venda média por dia", f"{pt(GIRO['VENDA 90D UN.'] / 90)} un.", "últimos 90 dias")
    kpi(rel, "Venda perdida prevista", moeda_curta(GIRO["VENDA PERDIDA PREVISTA"]), "até a compra chegar")
    kpi(rel, "Em ruptura", pt(GIRO["ITENS EM RUPTURA"]), "")
    kpi(rel, "Mix que gira", f"{pt(mix, 1)}%", "")
    kpi(rel, "Curva A parada", pt(GIRO["CURVA A PARADA (ITENS)"]), "")
    kpi(rel, "Comprar", pt(GIRO["ITENS A COMPRAR"]), "")
    # gráficos
    vend = int(GIRO["VENDA 90D UN."] / 90 * len(dias_uteis_ate()))
    blocos_periodo(rel, "Venda (unidades)", vend)
    blocos_periodo(rel, "Unidades vendidas", vend)          # o robô manda os dois iguais (a web mostra um só)
    blocos_periodo(rel, "SKUs vendidos", 780 * len(dias_uteis_ate()) // 10)
    rot = list(FILIAIS)
    b = bloco(rel, "Venda perdida prevista por filial")
    poe_barras(b, rot, col(pf, "VENDA PERDIDA PREVISTA"))
    b = bloco(rel, "Por filial: ruptura")
    poe_barras(b, rot, rup, comp_, par)
    b = bloco(rel, "Venda perdida prevista (R$) por filial")
    b["rotulos"], b["valores"] = rot, col(pf, "VENDA PERDIDA PREVISTA")
    b["cores"] = ["#B3261E"] * n
    # Por família / categoria: uma filial por linha
    for titulo in ("Por família", "Por categoria"):
        t = tabela(rel, titulo)
        poe(t, "FILIAL", [f"FILIAL FICTICIA {FILIAIS[k % 6]}" for k in range(len(t["linhas"]))])
    rel["recortes"] = {u: v for u, v in rel["recortes"].items() if u in FILIAIS}
    for u, rec in rel["recortes"].items():
        k = FILIAIS.index(u)
        valores = {"Estoque FRW + PMZ": moeda_curta(9_800_000.0 * col(pf, "ESTOQUE UN.")[k] / GIRO["ESTOQUE UN."]),
                   "Venda média por dia": f"{pt(col(pf, 'VENDA/DIA UN.')[k])} un.",
                   "Venda perdida prevista": moeda_curta(col(pf, "VENDA PERDIDA PREVISTA")[k]),
                   "Em ruptura": pt(rup[k]), "Mix que gira": f"{pt(col(pf, 'MIX QUE GIRA')[k], 1)}%",
                   "Curva A parada": pt(par[k]), "Comprar": pt(comp_[k])}
        for kk in rec["kpis"]:
            kk["valor"] = valores.get(kk["rotulo"], kk["valor"])
            kk["detalhe"] = ""


# --------------------------------------------------------------------------- Estoque FRW
def coerencia_frw(rel):
    t = tabela(rel, "Estoque FRW")
    n = len(t["linhas"])
    nomes = [c["nome"] for c in t["colunas"]]
    I = {x: nomes.index(x) for x in ("FILIAL", "ENTRADA NA FRW", "QTD ENTRADA", "ESTOQUE", "VENDA MÊS (MÉD. 6M)", "NECESSIDADE", "AÇÃO", "VALOR")}
    ufs = []
    for k, ln in enumerate(t["linhas"]):
        uf = FILIAIS[k % 6]
        ufs.append(uf)
        ln[I["FILIAL"]] = f"FILIAL FICTICIA {uf}"
        qtd = float(30 + (k * 13) % 120)
        est = float(round(qtd * (0.2 + (k % 5) / 8)))
        vm = 0.0 if k % 9 == 8 else round(8.0 + (k % 7) * 3.5, 2)         # alguns sem venda
        nec = int(round(vm * 2 - est)) if vm else -int(est)
        preco = 55.0 + (k * 9) % 140
        ln[I["QTD ENTRADA"]], ln[I["ESTOQUE"]], ln[I["VENDA MÊS (MÉD. 6M)"]] = qtd, est, vm
        ln[I["NECESSIDADE"]] = nec
        ln[I["AÇÃO"]] = "PEDIR" if nec > 0 else ("DEVOLVER À PMZ" if nec < 0 else "OK")
        ln[I["VALOR"]] = round(abs(nec) * preco, 2)
        ent = HOJE - timedelta(days=(k * 5) % 200)
        ln[I["ENTRADA NA FRW"]] = ent.isoformat()
        ln[idx(t, "DIAS NA FRW")] = (HOJE - ent).days
    t["uf_linhas"] = ufs
    t["tons"] = [{"PEDIR": "atencao", "DEVOLVER À PMZ": "alerta"}.get(ln[I["AÇÃO"]], "") for ln in t["linhas"]]
    n_ped = sum(ln[I["AÇÃO"]] == "PEDIR" for ln in t["linhas"])
    n_dev = sum(ln[I["AÇÃO"]] == "DEVOLVER À PMZ" for ln in t["linhas"])
    t["recortes_linhas"] = [
        {"rotulo": "Pedir", "linhas": [k for k, ln in enumerate(t["linhas"]) if ln[I["AÇÃO"]] == "PEDIR"]},
        {"rotulo": "Devolver à PMZ", "linhas": [k for k, ln in enumerate(t["linhas"]) if ln[I["AÇÃO"]] == "DEVOLVER À PMZ"]},
        {"rotulo": "Com estoque", "linhas": [k for k, ln in enumerate(t["linhas"]) if ln[I["ESTOQUE"]] > 0]}]
    dados = [(ln, date.fromisoformat(ln[I["ENTRADA NA FRW"]])) for ln in t["linhas"]]
    no_mes = [(ln, d) for ln, d in dados if d.month == 11]
    sem_venda = sum(ln[I["VENDA MÊS (MÉD. 6M)"]] == 0 for ln in t["linhas"])

    def faixa(rows, ufn=None):
        rs = [r for r in rows if ufn is None or r[-1] == ufn]
        return rs
    kpi(rel, "SKUs em estoque", pt(sum(ln[I["ESTOQUE"]] > 0 for ln in t["linhas"])), "")
    kpi(rel, "Pedir", pt(n_ped), "")
    kpi(rel, "Devolver à PMZ", pt(n_dev), "")
    kpi(rel, "Sem venda em 6 meses", pt(sem_venda), "")
    kpi(rel, "Entradas no mês", pt(len(no_mes)), "")
    for u, rec in rel["recortes"].items():
        rows = [ln for ln, uu in zip(t["linhas"], ufs) if uu == u]
        v = {"SKUs em estoque": pt(sum(r[I["ESTOQUE"]] > 0 for r in rows)),
             "Pedir": pt(sum(r[I["AÇÃO"]] == "PEDIR" for r in rows)),
             "Devolver à PMZ": pt(sum(r[I["AÇÃO"]] == "DEVOLVER À PMZ" for r in rows)),
             "Sem venda em 6 meses": pt(sum(r[I["VENDA MÊS (MÉD. 6M)"]] == 0 for r in rows))}
        for kk in rec["kpis"]:
            kk["valor"] = v.get(kk["rotulo"], kk["valor"])
            kk["detalhe"] = ""
    # gráficos a partir das próprias linhas
    por_dia_un, por_dia_sku = {}, {}
    for ln, d in no_mes:
        if d.day <= ULTIMO_DIA:
            por_dia_un[d.day] = por_dia_un.get(d.day, 0) + ln[I["QTD ENTRADA"]]
            por_dia_sku[d.day] = por_dia_sku.get(d.day, 0) + 1
    dias = list(range(1, ULTIMO_DIA + 1))
    un = [int(por_dia_un.get(d, 0)) for d in dias]
    sk = [por_dia_sku.get(d, 0) for d in dias]
    mes_un, mes_sk = [0] * 12, [0] * 12
    for ln, d in dados:
        pos = (d.year - 2025) * 12 + d.month - 12             # DEZ/25 = 0 ... NOV/26 = 11
        if 0 <= pos < 12:
            mes_un[pos] += int(ln[I["QTD ENTRADA"]])
            mes_sk[pos] += 1
    for metrica, d, m in (("Entradas na FRW (unidades)", un, mes_un), ("SKUs que entraram", sk, mes_sk)):
        for prefixo, rot, vals in ((f"{metrica} · dia a dia", [f"{x:02d}" for x in dias], d),
                                   (f"{metrica} · semana a semana", [f"S{k + 1}" for k in range(len(semanal(d)))], semanal(d)),
                                   (f"{metrica} · mês a mês", ROTULO_MESES, m)):
            b = bloco(rel, prefixo)
            if b:
                poe_barras(b, rot, vals)
    blocos_periodo(rel, "Unidades vendidas", 1850)
    b = bloco(rel, "Devolver à PMZ (R$) por filial")
    b["rotulos"] = list(FILIAIS)
    b["valores"] = [round(sum(r[I["VALOR"]] for r, uu in zip(t["linhas"], ufs) if uu == u and r[I["AÇÃO"]] == "DEVOLVER À PMZ"), 2) for u in FILIAIS]
    b["cores"] = ["#B3261E"] * len(FILIAIS)
    b = bloco(rel, "Itens a pedir por filial")
    b["rotulos"] = list(FILIAIS)
    b["valores"] = [sum(1 for r, uu in zip(t["linhas"], ufs) if uu == u and r[I["AÇÃO"]] == "PEDIR") for u in FILIAIS]
    b["cores"] = ["#C98A00"] * len(FILIAIS)


# --------------------------------------------------------------------------- Indicadores
def coerencia_indicadores(rel):
    sem, mes = tabela(rel, "Semana a semana"), tabela(rel, "Mês a mês")
    for t in (sem, mes):
        n = len(t["linhas"])
        ped = [70 + (k * 9) % 31 for k in range(n)]
        parc = [3 + k % 5 for k in range(n)]
        atr = [8 + (k * 3) % 8 for k in range(n)]
        nop = [p - a - r for p, a, r in zip(ped, atr, parc)]
        ent = [p - 6 - k % 4 for k, p in enumerate(ped)]
        poe(t, "PEDIDOS", ped)
        poe(t, "NO PRAZO", nop)
        poe(t, "ATRASO", atr)
        poe(t, "PARCIAL", parc)
        poe(t, "ENTREGUES", ent)
        poe(t, "% NO PRAZO", [pct(a, b) for a, b in zip(nop, ped)])
        poe(t, "% ATRASO", [pct(a, b) for a, b in zip(atr, ped)])
        poe(t, "% PARCIAL", [pct(a, b) for a, b in zip(parc, ped)])
        poe(t, "% ENTREGA NO PRAZO", [pct(e - k % 5, e) for k, e in enumerate(ent)])
        poe(t, "PERÍODO", [f"SEM {36 + k}" for k in range(n)] if t is sem else [f"{m}/{'25' if m == 'DEZ' else '26'}" for m in ROTULO_MESES])
    bm = tabela(rel, "Base com compra (mês a mês)")
    base = [2600 + k * 25 for k in range(len(bm["linhas"]))]
    com = [int(b * (0.5 + (k % 5) / 40)) for k, b in enumerate(base)]
    poe(bm, "MÊS", [f"{m}/{'25' if m == 'DEZ' else '26'}" for m in ROTULO_MESES][:len(base)])
    poe(bm, "CLIENTES NA BASE", base)
    poe(bm, "COM COMPRA", com)
    poe(bm, "SEM COMPRA", [b - c for b, c in zip(base, com)])
    poe(bm, "% COM COMPRA", [pct(c, b) for c, b in zip(com, base)])
    bs = tabela(rel, "Base com compra em NOV/26, por segmento")
    n = len(bs["linhas"])
    cli = reparte(base[-1], n, pesos(n))
    cc = reparte(com[-1], n, pesos(n))
    poe(bs, "CLIENTES", cli)
    poe(bs, "COM COMPRA", cc)
    poe(bs, "SEM COMPRA", [a - b for a, b in zip(cli, cc)])
    poe(bs, "% COM COMPRA", [pct(b, a) for a, b in zip(cli, cc)])
    # faixa = última linha (NOV/26) das tabelas
    u = {c["nome"]: v for c, v in zip(mes["colunas"], mes["linhas"][-1])}
    kpi(rel, "Pedidos faturados · NOV/26", pt(u["PEDIDOS"]), "")
    kpi(rel, "Faturados no prazo", f"{pt(u['% NO PRAZO'], 1)}%", f"{pt(u['NO PRAZO'])} de {pt(u['PEDIDOS'])}")
    kpi(rel, "Faturados com atraso", f"{pt(u['% ATRASO'], 1)}%", f"{pt(u['ATRASO'])} pedidos")
    kpi(rel, "Faturamento parcial", f"{pt(u['% PARCIAL'], 1)}%", "")
    kpi(rel, "SLA médio", f"{pt(u['SLA MÉDIO (DIAS)'], 1)} dias", "meta 3,0")
    kpi(rel, "Entregues no prazo", f"{pt(u['% ENTREGA NO PRAZO'], 1)}%", f"de {pt(u['ENTREGUES'])} entregues")
    kpi(rel, "Clientes com compra", pt(com[-1]), f"{round(100 * com[-1] / base[-1])}% da base")
    kpi(rel, "Clientes sem compra", pt(base[-1] - com[-1]), "")
    # gráficos = as próprias tabelas
    b = bloco(rel, "Semana a semana")
    poe_barras(b, [f"S{36 + k}" for k in range(len(sem["linhas"]))], col(sem, "% NO PRAZO"), col(sem, "% PARCIAL"))
    b = bloco(rel, "Mês a mês")
    poe_barras(b, ROTULO_MESES, col(mes, "% NO PRAZO"), col(bm, "% COM COMPRA"))


def aplica(p):
    """Coerência dos 5 faróis do lote 2 (altera o pacote no lugar)."""
    r = p["relatorios"]
    coerencia_indicadores(r["pv_indicadores"])
    coerencia_base(r["vc_base"])
    coerencia_rota(r["vc_planner"])
    coerencia_giro(r["pl_giro"])
    coerencia_frw(r["pl_frw"])
    return p
