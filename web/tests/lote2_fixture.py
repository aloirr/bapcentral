"""T-0024: pacote FICTÍCIO dos 5 faróis do lote 2 (Painel de indicadores, Clientes, Roteirização, Giro, Estoque FRW)
com as ABAS, COLUNAS e CARTÕES reais de cada farol (lote2_estrutura.py, tirada do que o robô monta) e só valores
inventados: CLIENTE FICTICIO nn, VENDEDOR FICTICIO nn, produtos e códigos 9xxxxx. Nenhum valor real entra aqui."""
from __future__ import annotations

from copy import deepcopy

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
    "SLA médio": ("3,6 dia(s)", "meta 3,0"), "Entregues no prazo": ("81,0%", "de 1.150 entregues"),
    "Clientes com compra": ("1.820", "62% da base"), "Clientes sem compra": ("1.110", ""),
    "Clientes": ("2.930", "na base do mês"), "Ativos": ("2.410", "82% dos clientes"),
    "Compraram no mês": ("1.540", "52% dos clientes"), "Com limite e sem compra": ("640", ""),
    "Limite disponível": ("R$ 18,4 mi", ""), "Oportunidade (falta)": ("R$ 2,3 mi", "até a meta"),
    "Cobertura da carteira": ("94,2%", "carteira com rota"), "Visitas no mês": ("6.820", "no mês"),
    "Ocupação da agenda": ("78,0%", "dias úteis com rota"), "Positivação da rota": ("41,5%", "da carteira"),
    "Sem vendedor": ("112", "lojas fora da rota"), "Nunca comprou": ("388", "na carteira"),
    "Estoque FRW + PMZ": ("R$ 9,8 mi", "310 mil un."), "Venda média por dia": ("1.480 un.", "últimos 90 dias"),
    "Venda perdida prevista": ("R$ 420 mil", "até a compra chegar"), "Em ruptura": ("86", "itens"),
    "Mix que gira": ("63,0%", "dos SKUs com estoque"), "Curva A parada": ("29", "itens"), "Comprar": ("141", "itens"),
    "SKUs em estoque": ("4.120", "em 6 filiais"), "Pedir": ("212", "itens"), "Devolver à PMZ": ("64", "itens"),
    "Sem venda em 6 meses": ("503", "itens"), "Entradas no mês": ("37", "entradas"),
    "Base Planner": ("2.610", "lojas no Planner"), "Cidades": ("230", ""), "Com limite": ("2.050", "com limite"),
    "Compradores": ("1.540", "no mês"), "Dias úteis com visita": ("17", "no mês"), "Estoque": ("310 mil un.", ""),
    "Faturamento 6M": ("R$ 41 mi", "últimos 6 meses"), "Inadimplentes": ("212", "lojas"),
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


def _tabela(rid, ufs, tb):
    cols = deepcopy(tb["colunas"])
    n = tb["n"]
    linhas, ufl, tons = [], [], []
    for i in range(1, n + 1):
        uf = ufs[i % len(ufs)] if ufs else "AM"
        if tb["titulo"] in ("Por UF", "Por cidade") and cols[0]["nome"] == "UF":
            uf = UFS_TODAS[(i - 1) % len(UFS_TODAS)]
        fil = f"FILIAL FICTICIA {uf}"
        ln = [_celula(rid, tb["titulo"], c, i, uf, fil) for c in cols]
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
        return [f"FILIAL FICTICIA {UFS_TODAS[k % len(UFS_TODAS)]}" for k in range(n)]
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
    return {"versao_contrato": 1, "gerado_em": "2026-11-24T08:30:00-04:00", "ano": 2026, "mes": 11,
            "relatorios": {rid: farol_lote2(rid) for rid in RIDS}}


def slug_abas(rid):
    """Como a web nomeia as abas (tabelas.abas_do_farol): para os PNG da simulação."""
    from app import tabelas
    return tabelas.abas_do_farol(rid, farol_lote2(rid))
