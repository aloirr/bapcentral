"""T-0024: pacote FICTÍCIO dos 5 faróis do lote 2 (Painel de indicadores, Clientes, Roteirização, Giro, Estoque FRW)
com as ABAS, COLUNAS e CARTÕES reais de cada farol (lote2_estrutura.py, tirada do que o robô monta) e só valores
inventados: CLIENTE FICTICIO nn, VENDEDOR FICTICIO nn, produtos e códigos 9xxxxx. Nenhum valor real entra aqui."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

from lote2_coerencia import aplica
from lote2_estrutura import ESTRUTURA

RIDS = tuple(ESTRUTURA)
UFS_TODAS = ["AM", "PA", "MA", "AP", "RR", "AC", "RO", "TO", "MT", "PI", "CE"]
CID = ["MANAUS", "BELÉM", "SÃO LUÍS", "MACAPÁ", "BOA VISTA"]
DIAS = ["SEG", "TER", "QUA", "QUI", "SEX"]
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

# Cartões: (valor, detalhe) fictícios; o rótulo, a cor e se leva detalhe vêm da estrutura real.
CARTOES = {
    "Pedidos faturados · NOV/26": ("1.240", ""), "Faturados no prazo": ("72,4%", "898 de 1.240"),
    "Faturados com atraso": ("19,1%", "237 pedidos"), "Faturamento parcial": ("8,5%", ""),
    "SLA médio": ("3,6 dias", "meta 3,0"), "Entregues no prazo": ("81,0%", "de 1.150 entregues"),
    "Clientes com compra": ("1.820", "62% da base"), "Clientes sem compra": ("1.110", ""),
    "Clientes": ("2.930", "na base do mês"), "Ativos": ("2.410", "82% dos clientes"),
    "Compraram no mês": ("1.540", "52% dos clientes"), "Com limite e sem compra": ("640", ""),
    "Limite disponível": ("R$ 18,4 mi", ""), "Oportunidade (falta)": ("R$ 2,3 mi", "até a meta"),
    "Cobertura da carteira": ("94,2%", "carteira com rota"), "Visitas no mês": ("6.820", ""),
    "Ocupação da agenda": ("78,0%", "dias úteis com rota"), "Positivação da rota": ("41,5%", "da carteira"),
    "Sem vendedor": ("112", "lojas fora da rota"), "Nunca comprou": ("388", "na carteira"),
    "Estoque FRW + PMZ": ("R$ 9,8 mi", "310 mil un."), "Venda média por dia": ("1.480 un.", "últimos 90 dias"),
    "Venda perdida prevista": ("R$ 420 mil", "até a compra chegar"), "Em ruptura": ("86", "itens"),
    "Mix que gira": ("63,0%", "dos SKUs com estoque"), "Curva A parada": ("29", "itens"), "Comprar": ("141", "itens"),
    "SKUs em estoque": ("4.120", "em 6 filiais"), "Pedir": ("212", ""), "Devolver à PMZ": ("64", "itens"),
    "Sem venda em 6 meses": ("503", "itens"), "Entradas no mês": ("37", ""),
    "Base Planner": ("2.610", "lojas no Planner"), "Cidades": ("230", ""), "Com limite": ("2.050", ""),
    "Compradores": ("1.540", ""), "Dias úteis com visita": ("17", "no mês"), "Estoque": ("310 mil un.", ""),
    "Faturamento 6M": ("R$ 41 mi", "últimos 6 meses"), "Inadimplentes": ("212", ""),
    "Itens a comprar": ("141", "itens"), "Itens em ruptura": ("86", "itens"), "Ocupação": ("78,0%", "da agenda"),
    "SKUs": ("4.120", "com estoque"), "Sábado": ("2 dias", "com rota"), "Venda 90 dias": ("92 mil un.", ""),
    "Vendedores": ("9", "ativos"), "Zonas": ("26", "com rota"),
}
INSIGHTS = [
    "Texto de exemplo do farol, com números fictícios.", "Segundo destaque de exemplo (valores inventados).",
    "Terceiro destaque de exemplo.", "Quarto destaque de exemplo.", "Quinto destaque de exemplo.",
    "Sexto destaque de exemplo.", "Sétimo destaque de exemplo.", "Oitavo destaque de exemplo.",
    "Nono destaque de exemplo.", "Décimo destaque de exemplo.",
]
SOMA_NAO = ("%", "GIRO", "COB", "/DIA", "MIX", "CLIENTES/DIA", "SLA", "TICKET", "DIAS", "KM/")


def _kpi(rot, cor, tem_det, escala=1):
    valor, det = CARTOES.get(rot, ("0", ""))
    return {"rotulo": rot, "valor": valor, "cor": cor, "detalhe": det if tem_det else ""}


def _texto(rid, aba, nome, i, uf, fil):
    """Valor de texto fictício, pelo nome da coluna do robô."""
    n2 = f"{i:02d}"
    sup = f"SUPERVISOR FICTICIO {1 + i % 4:02d}"
    ven = f"VENDEDOR FICTICIO {1 + i % 9:02d}"
    if (rid, aba, nome) == ("vc_planner", "Por cliente", "CLIENTE") or nome in ("CÓD.", "ZONA", "PRODUTO") \
            or (rid, aba, nome) == ("vc_planner", "Calendário", "CLIENTE"):
        return f"9{i:05d}" if nome != "ZONA" else f"Z{1 + i % 30:02d}"
    mapa = {
        "CLIENTE": f"CLIENTE FICTICIO {n2}", "NOME": f"CLIENTE FICTICIO {n2}", "FANTASIA": f"FANTASIA FICTICIA {n2}",
        "VENDEDOR": ven, "VENDEDOR PLANNER": ven, "VENDEDOR PROTHEUS": ven, "SUPERVISOR": sup,
        "SUPERVISOR PLANNER": sup, "SUPERVISOR PROTHEUS": sup,
        "VENDEDORES": f"{ven}, VENDEDOR FICTICIO {1 + (i + 3) % 9:02d}",
        "SUPERVISORES": f"{sup}, SUPERVISOR FICTICIO {1 + (i + 1) % 4:02d}",
        "UF": uf, "CIDADE": f"{CID[i % len(CID)]}", "BAIRRO": f"BAIRRO FICTICIO {1 + i % 12:02d}",
        "SEGMENTO": f"SEGMENTO FICTICIO {1 + i % 8:02d}", "CATEGORIA": f"CATEGORIA FICTICIA {1 + i % 6:02d}",
        "SISTEMA": f"SISTEMA FICTICIO {1 + i % 5:02d}", "FAMÍLIA": f"FAMILIA FICTICIA {1 + i % 9:02d}",
        "LINHA": f"LINHA FICTICIA {1 + i % 4:02d}", "FILIAL": fil, "DESCRIÇÃO": f"PRODUTO FICTICIO {i:03d}",
        "ÚLTIMO PRODUTO": f"PRODUTO FICTICIO {1 + (i * 7) % 90:03d}",
        "STATUS": "ATIVO" if i % 9 else "INATIVO", "STATUS PROTHEUS": "ATIVO" if i % 9 else "INATIVO",
        "SITUAÇÃO PLANNER": ["ATIVO", "CHURN 30", "CHURN 60", "CHURN 90", "NUNCA COMPROU"][i % 5],
        "CURVA": "ABC"[i % 3], "COM LIMITE": "SIM" if i % 4 else "NÃO", "INADIMPLENTE": "NÃO" if i % 5 else "SIM",
        "COMPRADOR": "SIM" if i % 3 else "NÃO", "COMPROU NO MÊS": "SIM" if i % 3 else "NÃO",
        "VISÃO": "SEM REPETIÇÃO", "SEMANA": f"SEMANA {1 + i % 5}", "DIA": DIAS[i % 5], "VISITA": "PREVISTA",
        "DATAS DAS VISITAS": "02/11, 16/11", "PERÍODO": (f"SEM {44 + i % 10}" if "Semana" in aba else f"{MESES[i % 12]}/26"),
        "MÊS": f"{MESES[i % 12]}/26",
    }
    if aba == "Por zona" and nome == "NOME":
        return f"ZONA FICTICIA {n2}"
    if nome == "SITUAÇÃO":
        return ["RUPTURA", "COMPRAR", "A PARADA", "OK"][i % 4]
    if nome == "AÇÃO":
        return ["PEDIR", "OK", "DEVOLVER À PMZ", "OK"][i % 4]
    return mapa.get(nome, f"{nome} FICTICIO {n2}")


def _numero(nome, tipo, i):
    i = i + sum(map(ord, nome)) % 11             # colunas diferentes não repetem o mesmo número
    if tipo == "int":
        base = 8 + (i * 13) % 90
        return {"SEQ.": 1 + i % 12, "DIAS S/ COMPRA": (i * 17) % 220}.get(nome, base)
    if tipo == "num":
        return 40.0 + (i * 37) % 900
    if tipo == "num1":
        return round(1.0 + (i % 9) / 2, 1)
    if tipo == "num2":
        return round(0.3 + (i % 7) / 5, 2)
    if tipo == "moeda":
        return round(1500.0 + (i * 733) % 48000, 2)
    if tipo == "moeda2":
        return round(12.5 + (i % 17) * 1.7, 2)
    if tipo in ("pct", "pct1"):
        return round(18.0 + (i * 11) % 80, 1)
    return None


def _celula(rid, aba, c, i, uf, fil):
    t = c["tipo"]
    if t == "texto":
        return _texto(rid, aba, c["nome"], i, uf, fil)
    if t in ("dia", "data"):
        return f"2026-11-{1 + (i * 3) % 27:02d}"
    if t == "hora":
        return f"{8 + i % 9:02d}:{(i * 7) % 60:02d}"
    return _numero(c["nome"], t, i)


# --------------------------------------------------------------------------- coerência (parecer de UX, R6)
HOJE = date(2026, 11, 24)                                  # dia do pacote (Manaus)
DIAS_UTEIS = [date(2026, 11, d) for d in range(1, 31) if date(2026, 11, d).weekday() < 5]
SEMANA = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]


def _pct(parte, todo):
    return round(100.0 * parte / todo, 1) if todo else 0.0


def _ajusta(rid, aba, ln, i, n):
    """Corrige, na linha (dict nome -> valor), os campos que dependem uns dos outros."""
    def tem(*nomes):
        return all(x in ln for x in nomes)
    if tem("PEDIDOS", "NO PRAZO", "ATRASO", "PARCIAL"):                    # Indicadores: semana a semana / mês a mês
        ped = 60 + (i * 9) % 35
        parcial, atraso = 3 + i % 5, 8 + (i * 3) % 10
        ent = ped - 6 - i % 4
        ln.update({"PEDIDOS": ped, "ATRASO": atraso, "PARCIAL": parcial, "NO PRAZO": ped - atraso - parcial,
                   "ENTREGUES": ent, "SLA MÉDIO (DIAS)": round(2.8 + (i % 7) / 5, 2)})
        ln.update({"% NO PRAZO": _pct(ped - atraso - parcial, ped), "% ATRASO": _pct(atraso, ped),
                   "% PARCIAL": _pct(parcial, ped), "% ENTREGA NO PRAZO": _pct(ent - i % 5, ent)})
        ln["PERÍODO"] = (f"SEM {35 + i}" if "Semana" in aba else (["DEZ/25"] + [f"{m}/26" for m in MESES[:11]])[i - 1])
    if tem("CLIENTES NA BASE", "COM COMPRA", "SEM COMPRA") or (aba.startswith("Base") and "CLIENTES" in ln and "COM COMPRA" in ln):
        base = 2600 + i * 40 if "CLIENTES NA BASE" in ln else 180 + (i * 53) % 400
        com = int(base * (0.42 + (i % 6) / 25))
        ln["CLIENTES NA BASE" if "CLIENTES NA BASE" in ln else "CLIENTES"] = base
        ln.update({"COM COMPRA": com, "SEM COMPRA": base - com, "% COM COMPRA": _pct(com, base)})
        if "MÊS" in ln:
            ln["MÊS"] = (["DEZ/25"] + [f"{m}/26" for m in MESES[:11]])[i - 1]
    if tem("COMPRARAM NO MÊS", "% POSITIVAÇÃO", "OPORTUNIDADE (FALTA)"):      # Clientes: carteira
        cli = 300 + (i * 83) % 900
        ativos = int(cli * 0.82)
        comp = int(ativos * (0.45 + (i % 5) / 20))
        com_lim = int(ativos * 0.7)
        meta = 150000.0 + (i * 21000) % 400000
        real = round(meta * (0.55 + (i % 6) / 10), 2)
        ln.update({"CLIENTES": cli, "ATIVOS": ativos, "COMPRARAM NO MÊS": comp, "% POSITIVAÇÃO": _pct(comp, ativos),
                   "NUNCA COMPRARAM": int(cli * 0.08), "COM LIMITE": com_lim,
                   "C/ LIMITE E S/ COMPRA": int(com_lim * 0.3), "LIMITE DISP.": com_lim * 5200.0,
                   "RECEITA 6M": ativos * 3100.0, "META": meta, "REALIZADO": real,
                   "OPORTUNIDADE (FALTA)": round(max(meta - real, 0), 2)})
        if "BASE PROTHEUS" in ln:
            ln["BASE PROTHEUS"] = cli + 12
    if tem("CLIENTES QUE COMPRAM", "% DOS ATIVOS"):                         # Clientes: por família
        comp = 300 + (i * 61) % 1600
        fat = 80000.0 + (i * 9100) % 400000
        ln.update({"CLIENTES QUE COMPRAM": comp, "% DOS ATIVOS": _pct(comp, 2400), "ATIVOS QUE NÃO COMPRAM": 2400 - comp,
                   "FATURAMENTO 6M": fat, "TICKET/CLIENTE": round(fat / comp, 2)})
    if tem("BASE PLANNER", "VISITAS/MÊS", "CAPACIDADE/DIA"):                 # Roteirização: agregadas
        bp = 160 + (i * 47) % 500
        bv = int(bp * 0.9)
        vis = int(bv * 1.1)
        du = int(vis * 0.95)
        com_lim = int(bp * 0.75)
        comp = int(bp * (0.3 + (i % 5) / 20))
        ln.update({"BASE PLANNER": bp, "BASE PROTHEUS": bp + 15, "BASE VISITA": bv, "VISITAS/MÊS": vis,
                   "VISITAS/MÊS DIAS ÚTEIS": du, "CLIENTES/DIA": round(du / 20.0, 2), "CAPACIDADE/DIA": 12,
                   "COM LIMITE": com_lim, "INADIMPL.": int(com_lim * 0.15), "COMPRADORES": comp,
                   "% COMPRADORES": _pct(comp, bp)})
    if tem("DATA", "DIA") and rid == "vc_planner":                           # Roteirização: cliente a cliente
        d = DIAS_UTEIS[(i - 1) % len(DIAS_UTEIS)]
        ln.update({"DATA": d.isoformat(), "DIA": SEMANA[d.weekday()], "SEMANA": f"SEMANA {1 + (d.day - 1) // 7}",
                   "SEQ.": 1 + (i - 1) // len(DIAS_UTEIS) * 3 + (i - 1) % 5})
    if rid == "pl_giro" and tem("SKUs C/ ESTOQUE", "ESTOQUE UN."):           # Giro: por filial
        est = 24000.0 + i * 3100
        v90 = est * 0.35
        sk = 900 + i * 40
        ln.update({"SKUs C/ ESTOQUE": sk, "ESTOQUE UN.": est, "VENDA 90D UN.": v90, "VENDA/DIA UN.": round(v90 / 90, 1),
                   "MIX QUE GIRA": round(55.0 + i * 2.5, 1), "ITENS EM RUPTURA": 6 + i * 3, "ITENS A COMPRAR": 20 + i * 4,
                   "SUGESTÃO UN.": 800.0 + i * 120, "CURVA A PARADA (ITENS)": 3 + i,
                   "VENDA PERDIDA PREVISTA": 18000.0 + i * 5500})
    if rid == "pl_giro" and tem("VD 30D", "VD 90D", "EST."):                 # Giro: por produto
        situ = ln.get("SITUAÇÃO") or ["RUPTURA", "COMPRAR", "A PARADA", "OK"][i % 4]
        if aba == "Ruptura":
            situ = "RUPTURA"
        elif aba == "Curva A parada":
            situ = "A PARADA"
        elif aba == "Necessidade de compra":
            situ = "COMPRAR"
        v90 = 90.0 + (i * 37) % 600 if situ != "A PARADA" else 0.0
        v30 = round(v90 * 0.32, 0)
        est = 0.0 if situ == "RUPTURA" else 40.0 + (i * 29) % 500
        if situ == "COMPRAR":                       # precisa comprar: o estoque não cobre 60 dias de venda
            est = round(v90 / 90.0 * (8 + i % 20), 0)
        vdia = round(v90 / 90.0, 1)
        ult = HOJE - timedelta(days=(i * 11) % 25 if situ != "A PARADA" else 95 + i)
        preco = 38.0 + (i * 7) % 90
        dsem = 9.0 + (i % 6) if situ == "RUPTURA" else (2.0 * (1 + i % 3) if situ == "COMPRAR" else 0.0)
        ln.update({"SITUAÇÃO": situ, "EST.": est, "VD 30D": v30, "VD 90D": v90, "VD/DIA": vdia,
                   "GIRO": round(v90 / est, 2) if est else 0.0, "COB (DIAS)": round(est / vdia, 0) if vdia else None,
                   "ÚLT. VENDA": ult.isoformat(), "PARADO (D)": (HOJE - ult).days,
                   "SUGESTÃO": round(vdia * 60 - est, 0) if situ in ("COMPRAR", "RUPTURA") else 0.0,
                   "DIAS S/ EST.": dsem, "VENDA/DIA": round(vdia * preco, 2),
                   "VENDA PERDIDA": round(dsem * vdia * preco, 2)})
    if rid == "pl_giro" and tem("SKUs", "GIRAM", "RUPTURA"):                 # Giro: por família / categoria
        sk = 80 + (i * 13) % 200
        ce = int(sk * 0.8)
        gir = int(ce * (0.55 + (i % 5) / 20))
        ln.update({"SKUs": sk, "C/ EST.": ce, "GIRAM": gir, "MIX": _pct(gir, sk), "% SKUs": round(sk / 40.0, 1),
                   "EST. UN.": ce * 18.0, "% EST.": round(ce / 60.0, 1), "VD 90D": gir * 21.0, "% VD": round(gir / 15.0, 1),
                   "NOTAS": 120 + i * 3, "% NOTAS": round(2.0 + i % 9, 1), "CLIENTES": 90 + i * 2, "UN./NOTA": 3.4,
                   "RUPTURA": i % 6, "A PARADA": i % 4, "COMPRAR": 2 + i % 7, "SUGESTÃO": 150.0 + i * 11,
                   "VENDA PERDIDA": 2500.0 + i * 310})
    if rid == "pl_frw" and tem("ENTRADA NA FRW", "DIAS NA FRW"):             # Estoque FRW
        ent = HOJE - timedelta(days=(i * 7) % 200)
        qtd = 30.0 + (i * 13) % 120
        est = round(qtd * (0.2 + (i % 5) / 8), 0)
        vm = round(8.0 + (i % 7) * 3.5, 2)
        nec = int(round(vm * 2 - est, 0))
        preco = 55.0 + (i * 9) % 140
        ln.update({"ENTRADA NA FRW": ent.isoformat(), "QTD ENTRADA": qtd, "DIAS NA FRW": (HOJE - ent).days,
                   "ESTOQUE": est, "VENDA MÊS (MÉD. 6M)": vm, "NECESSIDADE": nec,
                   "AÇÃO": "PEDIR" if nec > 0 else ("DEVOLVER À PMZ" if nec < 0 else "OK"),
                   "VALOR": round(abs(nec) * preco, 2)})
    return ln


# tamanho de tabela que a faixa exige (as contagens por filial somam o cartão): ver lote2_coerencia.py
FORCA_N = {("pl_giro", "Resumo por filial"): 6, ("pl_giro", "Ruptura"): 24, ("pl_giro", "Necessidade de compra"): 32,
           ("pl_giro", "Curva A parada"): 18}


def _tabela(rid, ufs, tb):
    cols = deepcopy(tb["colunas"])
    n = FORCA_N.get((rid, tb["titulo"]), tb["n"])
    linhas, ufl, tons = [], [], []
    for i in range(1, n + 1):
        uf = ufs[i % len(ufs)] if ufs else "AM"
        if tb["titulo"] in ("Por UF", "Por cidade") and cols[0]["nome"] == "UF":
            uf = UFS_TODAS[(i - 1) % len(UFS_TODAS)]
        fil = f"FILIAL FICTICIA {uf}"
        d = {c["nome"]: _celula(rid, tb["titulo"], c, i, uf, fil) for c in cols}
        d = _ajusta(rid, tb["titulo"], d, i, n)
        ln = [int(round(d.get(c["nome"]))) if (c["tipo"] == "num" and isinstance(d.get(c["nome"]), float))
              else d.get(c["nome"]) for c in cols]
        linhas.append(ln)
        ufl.append(uf)
        acao = next((v for c, v in zip(cols, ln) if c["nome"] == "AÇÃO"), "")
        tons.append({"PEDIR": "atencao", "DEVOLVER À PMZ": "alerta"}.get(acao, ""))
    t = {"titulo": tb["titulo"], "colunas": cols, "linhas": linhas, "tons": tons,
         "filtros": [f for f in tb["filtros"]]}
    if tb["total"]:
        tot = []
        for k, c in enumerate(cols):
            if k == 0:
                tot.append("TOTAL" if c["tipo"] == "texto" else None)
            elif c["tipo"] in ("int", "num", "moeda") and not any(s in c["nome"] for s in SOMA_NAO):
                tot.append(round(sum(ln[k] or 0 for ln in linhas), 2))
            else:
                tot.append(None)
        t["total"] = tot
    if tb["uf"]:
        t["uf_linhas"] = ufl
    if tb["rec"]:
        t["recortes_linhas"] = [{"rotulo": r, "linhas": [k for k in range(n) if k % len(tb["rec"]) == q]}
                                for q, r in enumerate(tb["rec"])]
    if tb["kpis_padrao"]:
        t["kpis_padrao"] = [_kpi(r, "neutro", True) for r in tb["kpis_padrao"]]
    return t


def _rotulos(titulo, n):
    t = titulo.lower()
    if "dia a dia" in t:
        return [f"{1 + k:02d}" for k in range(n)]
    if "semana a semana" in t:
        return [f"S{1 + k}" for k in range(n)]
    if "mês a mês" in t:
        return [MESES[(k + 12 - n) % 12] if n <= 12 else f"M{k}" for k in range(n)]
    if "filial" in t:
        return [UFS_TODAS[k % len(UFS_TODAS)] for k in range(n)]        # a filial é a sigla do estado
    if "vendedor" in t or "agenda" in t or "dia útil" in t or "sábado" in t or "carteira" in t:
        return [f"VENDEDOR FICTICIO {1 + k:02d}" for k in range(n)]
    if "segmento" in t:
        return [f"SEGMENTO FICTICIO {1 + k:02d}" for k in range(n)]
    return [f"ITEM FICTICIO {1 + k:02d}" for k in range(n)]


def _valores(formato, n, desloc=0):
    if formato == "pct":
        return [round(30.0 + ((k + desloc) * 13) % 65, 1) for k in range(n)]
    if formato == "moeda":
        return [round(20000.0 + ((k + desloc) * 7919) % 90000, 0) for k in range(n)]
    return [round(20.0 + ((k + desloc) * 11) % 70, 1) for k in range(n)]


def _painel(est):
    blocos = []
    for b in est["painel"]:
        o = {k: v for k, v in b.items() if k in ("tipo", "row", "col", "colspan", "rowspan")}
        if b["tipo"] == "insights":
            o["titulo"] = b["titulo"]
            o["linhas"] = [[tom, INSIGHTS[k % len(INSIGHTS)]] for k, tom in enumerate(b["tons"])]
        elif "grafico" in b:
            g = b["grafico"]
            sr = []
            for q, s in enumerate(g["series"]):
                sr.append({"nome": s["nome"], "cor": s["cor"], "valores": _valores(g["formato"], g["n"], q * 3)})
            o["grafico"] = {"titulo": g["titulo"], "rotulos": _rotulos(g["titulo"], g["n"]), "series": sr,
                            "formato": g["formato"]}
            if g.get("rotular"):
                o["grafico"]["rotular"] = g["rotular"]
            if b["tipo"] == "hbarras":
                pass
        else:                                                   # hbarras com valores no próprio bloco
            o.update({"titulo": b["titulo"], "formato": b["formato"], "rotulos": _rotulos(b["titulo"], b["n"]),
                      "valores": _valores(b["formato"], b["n"])})
            if b.get("cores"):
                o["cores"] = [b["cores"][k % len(b["cores"])] for k in range(b["n"])]
            if b["titulo"].startswith("Visitas por dia útil"):        # teto de 12 visitas por dia útil: cor pela regra
                o["valores"] = [float(6 + (k * 3) % 8) for k in range(b["n"])]
                o["cores"] = ["#62BB47" if v <= 12 else "#B3261E" for v in o["valores"]]
            elif b["titulo"].startswith("Ocupação da agenda"):
                o["valores"] = [float(55 + (k * 9) % 42) for k in range(b["n"])]
                o["cores"] = ["#62BB47" if v <= 85 else ("#C98A00" if v <= 95 else "#B3261E") for v in o["valores"]]
        blocos.append(o)
    return {"blocos": blocos}


def farol_lote2(rid):
    est = ESTRUTURA[rid]
    ufs = est["ufs"]
    f = {"forma": "farol", "titulo": est["titulo"],
         "kpis": [_kpi(r, cor, det) for r, cor, det in est["kpis"]],
         "painel": _painel(est),
         "insights_painel": [["info", INSIGHTS[0]], ["atencao", INSIGHTS[1]]] if est["painel"] and
         any(b["tipo"] == "insights" for b in est["painel"]) else [],
         "avisos": ["Sem filtro por estado: os cartões mostram a BAP inteira."] if est["avisos"] else [],
         "tabelas": [_tabela(rid, ufs, tb) for tb in est["tabs"]],
         "baixado_em": "2026-11-24T08:10:00-04:00"}
    if ufs:
        f["recortes"] = {uf: {"kpis": [_kpi(r, "neutro", True) for r in est["kpis_uf"]]} for uf in ufs}
    return f


def pacote_lote2():
    p = {"versao_contrato": 1, "gerado_em": "2026-11-24T08:30:00-04:00", "ano": 2026, "mes": 11,
         "relatorios": {rid: farol_lote2(rid) for rid in RIDS}}
    return aplica(p)                                       # faixa, TOTAL, recortes e gráficos saem das linhas


def slug_abas(rid):
    """Como a web nomeia as abas (tabelas.abas_do_farol): para os PNG da simulação."""
    from app import tabelas
    return tabelas.abas_do_farol(rid, farol_lote2(rid))
