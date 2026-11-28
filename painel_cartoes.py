"""
PAINEL EM CARTOES (06/11, recado 20261106-1524 do Maestro Comercial, o
formato do RRM do Diretor v20): duas abas novas no Painel Executivo.

  Painel · visao absoluta  - 15 cartoes: o numero do mes (ate ontem), o
      atingimento (real e projetado), o gap do mes, a variacao contra o mes
      -1, -2 e -4 e as barras dos 4 meses (o mes corrente escuro, projetado
      nos volumes; os outros em cinza).
  Painel · por dia util    - 6 cartoes de volume (faturamento,
      positivacao, pedidos, visitas, pecas e cadastros com compra), cada
      mes dividido pelos dias uteis dele.

Fontes: o Painel do Diretor (painel_diretor.calcular) do mes e dos 3 meses
de comparacao; pedidos, itens, pecas, cadastros com compra, TOP 30 e
pedidos em aberto saem da TABELA_BAP (o mesmo do Painel Executivo).
Regras do recado:
  - volumes (faturamento, positivacao, pedidos, pecas, visitas, cadastros):
    a variacao compara a PROJECAO do mes (media por DU x DU do mes) com o
    mes fechado; taxas e TOP 30 comparam direto;
  - verde = melhorou; desconto, visita em nao comprador e inadimplencia:
    subir e pior; taxas em p.p., jornada em minutos;
  - gap = meta - real (taxas: a distancia ate o minimo ou o teto); verde
    quando a projecao bate a meta;
  - por DU: meta/DU = meta / DU do mes; gap = (meta - real) / DU que
    faltam.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

MESES_C = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set",
           "out", "nov", "dez"]
MESES_L = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
           "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIST = (1, 2, 4)                    # os meses de comparacao: -1, -2 e -4
UFS_TOP30 = {"AM", "RR", "PA", "MA"}
M = "−"
VOL = ("fat", "pos", "ped", "pecas", "vis", "cad")
SEM_VISITA_ANTES = date(2026, 8, 27)     # o Espelho da Maxima comeca aqui
# (09/11, recado 20261109-1100) o registro cliente a cliente (conversao e
# 1a visita) comeca em OUT/26
INICIO_REGISTRO_CLIENTE = (2026, 10)
_MEMO = {}


# --------------------------------------------------------------- formatos
def br(v, c=0):
    if v is None:
        return "—"
    s = f"{v:,.{c}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def reais(v):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e6:
        return f"R$ {br(v / 1e6, 2)} mi"
    if a >= 1e5:
        return f"R$ {br(v / 1e3, 0)} mil"
    if a >= 1e3:
        return f"R$ {br(v / 1e3, 1)} mil"
    return f"R$ {br(v, 0)}"


def pc(v, d=0):
    return "—" if v is None else br(v, d) + "%"


def hm(h):
    if h is None:
        return "—"
    t = int(round(h * 60))
    return f"{t // 60}h{t % 60:02d}"


def _rn():
    import relatorios_nucleo as rn                      # noqa: PLC0415
    return rn


def _mes_ant(ano, mes, n=1):
    i = ano * 12 + (mes - 1) - n
    return i // 12, i % 12 + 1


def _var_pct(a, b, maior_bom=True):
    if a is None or not b:
        return ("—", "")
    x = (a / b - 1) * 100
    if abs(x) < 0.5:
        return ("igual", "")
    return (("+" if x > 0 else M) + br(abs(x), 0) + "%",
            "bom" if (x > 0) == maior_bom else "ruim")


def _var_pp(a, b, maior_bom=True, dec=1):
    if a is None or b is None:
        return ("—", "")
    x = a - b
    if abs(x) < 0.05:
        return ("igual", "")
    return (("+" if x > 0 else M) + br(abs(x), dec) + " p.p.",
            "bom" if (x > 0) == maior_bom else "ruim")


def _var_n(a, b, maior_bom=True):
    if a is None or b is None:
        return ("—", "")
    x = a - b
    if not x:
        return ("igual", "")
    return (("+" if x > 0 else M) + br(abs(x), 0),
            "bom" if (x > 0) == maior_bom else "ruim")


def _var_min(a, b):
    if a is None or b is None:
        return ("—", "")
    x = round((a - b) * 60)
    if not x:
        return ("igual", "")
    return (("+" if x > 0 else M) + f"{abs(x)} min",
            "bom" if x > 0 else "ruim")


# --------------------------------------------------------------- os dados
def _diretor(ctx, ano, mes, dd=None):
    """Os numeros do Painel do Diretor do mes ({chave: card}) e os DU."""
    import painel_diretor as pdr                        # noqa: PLC0415
    if dd is None:
        hoje = ctx.hoje if hasattr(ctx.hoje, "year") else date.today()
        k = (str(ctx.raiz), ano, mes, id(ctx.tabela))
        fechado = (ano, mes) < (hoje.year, hoje.month)
        if fechado and k in _MEMO:
            return _MEMO[k]
        dd = pdr.calcular(ctx, ano, mes, gravar_hist=False)
        if fechado:
            _MEMO[k] = dd
    return dd


def _da_tabela(ctx, ano, mes, ate):
    """Pedidos faturados, itens (SKU por nota), pecas e cadastros com compra
    do mes ate a data (o mesmo do analitico do Painel Executivo)."""
    import relatorios_nucleo as rn                      # noqa: PLC0415
    nfs, no_mes = defaultdict(set), []
    pecas = 0.0
    for it in ctx.tabela["itens"]:
        d = it.get("dt_nf")
        if not d or d.year != ano or d.month != mes or d > ate:
            continue
        v = rn._liquido(it)
        if v is None:                   # interno
            continue
        if rn._eh_pecas(ctx, it["cod"]):
            pecas += v
        if it["tipo"] == "VND":
            nfs[(it["filial"], it["nf"])].add(it["cod"])
        no_mes.append(it)
    ped = rn.pedidos_faturados_ate(no_mes, ate)     # RN-GER-002, 005
    positivou = rn.clientes_positivados_ate(no_mes, ate)    # RN-GER-003, 005
    cad = 0
    for cod, c in (ctx.tabela.get("clientes") or {}).items():
        dc = rn._dia(c.get("dtcad"))
        if dc and dc.year == ano and dc.month == mes and dc <= ate \
                and cod in positivou:
            cad += 1
    return {"ped": len(ped), "itens": sum(len(x) for x in nfs.values()),
            "pecas": pecas, "cad": cad}


def _liquido_por_cliente(ctx, meses, ate=None):
    import relatorios_nucleo as rn                      # noqa: PLC0415
    s = defaultdict(float)
    for it in ctx.tabela["itens"]:
        d = it.get("dt_nf")
        if d and (d.year, d.month) in meses and (ate is None or d <= ate):
            v = rn._liquido(it)
            if v is not None:
                s[it["cliente"]] += v
    return s


def _top30(ctx, ano, mes):
    """TOP 30 do gerente comercial: os 30 de maior faturamento liquido nos
    4 meses fechados antes do mes (a regra das contas-chave do Painel do
    Diretor), so AM, RR, PA e MA."""
    meses = {_mes_ant(ano, mes, n) for n in (1, 2, 3, 4)}
    s = _liquido_por_cliente(ctx, meses)
    cands = [c for c, v in s.items() if v > 0.005 and str(
        (ctx.cliente(c) or {}).get("uf") or "").upper() in UFS_TOP30]
    return sorted(cands, key=lambda c: -s[c])[:30]


def _hist(raiz) -> dict:
    try:
        import painel_diretor as pdr                    # noqa: PLC0415
        return json.loads(pdr._hist_path(raiz).read_text("utf-8"))
    except (OSError, ValueError, ImportError):
        return {}


def dist_rrm(mes) -> tuple:
    """(10/11, recado 20261109-1345) a faixa de comparacao: o mes
    anterior, o anterior a ele e JULHO (benchmarking) [SUPOSICAO: de AGO a
    SET o julho e o do ano passado]."""
    j_ = mes - 7 if mes >= 10 else mes + 5
    return (1, 2, j_ if j_ > 2 else 4)


def calcular(ctx, ano, mes, dd=None, dist=DIST) -> dict:
    """Os cartoes das duas abas. dd: o Painel do Diretor do mes ja
    calculado (a aba Painel do Diretor) - nao recalcula."""
    dd = _diretor(ctx, ano, mes, dd)
    meses = [(ano, mes)] + [_mes_ant(ano, mes, n) for n in dist]
    rot = [MESES_C[m] for _a, m in meses]
    cards_m = {(ano, mes): {c["chave"]: c for c in dd["cards"]}}
    du_m = {(ano, mes): dd["ndm"]}
    dds = {(ano, mes): dd}
    avisos = list(dd.get("avisos") or [])
    for am in meses[1:]:
        try:
            d_ = _diretor(ctx, *am)
            dds[am] = d_
            cards_m[am] = {c["chave"]: c for c in d_["cards"]}
            du_m[am] = d_["ndm"]
        except Exception as erro:                       # noqa: BLE001
            cards_m[am], du_m[am] = {}, None
            avisos.append(f"{MESES_C[am[1]]}: {erro}")
    ndp, ndm = dd["ndp"], dd["ndm"]
    ndp_a = dd.get("ndp_a", ndp)            # grupo A: hoje conta
    rest = max(0, ndm - ndp)
    ate = dd["dados_ate"]
    ate_a = dd.get("dados_ate_a") or ate

    def fim(a, m):
        return date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    tab = {}
    for am in meses:
        if am != (ano, mes):
            tab[am] = _da_tabela(ctx, *am, fim(*am))
            continue
        t_a, t_b = _da_tabela(ctx, *am, ate_a), _da_tabela(ctx, *am, ate)
        # pedidos e itens: grupo A (hoje conta); pecas e cadastros: ate ontem
        tab[am] = dict(t_a, pecas=t_b["pecas"], cad=t_b["cad"])

    def num(am, chave, escala=1.0):
        c = cards_m.get(am, {}).get(chave)
        v = c.get("numero") if c else None
        return None if v is None else v * escala

    def visita(am, chave, escala=1.0):
        """sem registro antes do Espelho (27/08) ou sem visita no mes"""
        if fim(*am) < SEM_VISITA_ANTES or not num(am, "visitas"):
            return None
        return num(am, chave, escala)
    hist = _hist(ctx.raiz)
    V = {"fat": {am: num(am, "fat") for am in meses},
         "pos": {am: num(am, "pos") for am in meses},
         "ped": {am: tab[am]["ped"] for am in meses},
         "itens": {am: tab[am]["itens"] for am in meses},
         "ticket": {am: num(am, "ticket") for am in meses},
         "markup": {am: num(am, "markup") for am in meses},
         "desc": {am: num(am, "desconto") for am in meses},
         "pecas": {am: tab[am]["pecas"] for am in meses},
         "vis": {am: visita(am, "visitas") for am in meses},
         # (09/11, recado 20261109-1100) % conversao nos visitados e % 1a
         # visita no lugar de nao comprador e conversao em quem compra
         # (o cliente a cliente comeca em OUT/26: antes = sem registro)
         "convv": {am: (visita(am, "conv_visitados", 100)
                        if am >= INICIO_REGISTRO_CLIENTE else None)
                   for am in meses},
         "prim": {am: visita(am, "primeira_visita", 100) for am in meses},
         "ader": {am: visita(am, "aderencia") for am in meses},
         "jorn": {am: visita(am, "jornada") for am in meses},
         "cad": {am: tab[am]["cad"] for am in meses},
         "inad": {}}
    # inadimplencia: foto do dia (o mes corrente) e o fechamento gravado
    # pelo Painel do Diretor nos outros (sem foto = "sem foto")
    for am in meses:
        if am == (ano, mes):
            V["inad"][am] = num(am, "inad")
        else:
            x = (hist.get(f"{am[0]}-{am[1]:02d}") or {}).get("inad")
            V["inad"][am] = x if isinstance(x, (int, float)) else None
    # TOP 30 e os pedidos em aberto digitados no mes
    top = _top30(ctx, ano, mes)
    V["top30"] = {}
    for am in meses:
        s = _liquido_por_cliente(ctx, {am},
                                 ate_a if am == (ano, mes) else None)
        V["top30"][am] = sum(1 for c in top if s.get(c, 0) > 0.005)
    s_at = _liquido_por_cliente(ctx, {(ano, mes)}, ate_a)
    hoje = ctx.hoje if hasattr(ctx.hoje, "year") else date.today()
    abertos = [it for it in ctx.tabela["itens"] if it["tipo"] == "VEA"
               and it.get("dt_pedido") and it["dt_pedido"].year == ano
               and it["dt_pedido"].month == mes]
    corre = (ano, mes) == (hoje.year, hoje.month)
    ab_ped = {(i["filial"], i["pedido"]) for i in abertos}
    ab_v = sum(i["valor"] or 0 for i in abertos)
    top_ab = {i["cliente"] for i in abertos} & {
        c for c in top if s_at.get(c, 0) <= 0.005}
    top_ab_v = sum(i["valor"] or 0 for i in abertos
                   if i["cliente"] in top_ab)
    metas = {"fat": (cards_m[(ano, mes)].get("fat") or {}).get("meta"),
             "pos": (cards_m[(ano, mes)].get("pos") or {}).get("meta"),
             "vis": (cards_m[(ano, mes)].get("visitas") or {}).get("meta")}
    at = meses[0]

    def proj(k):
        v = V[k][at]
        if v is None:
            return None
        c = {"fat": "fat", "pos": "pos", "vis": "visitas"}.get(k)
        pj = (cards_m[at].get(c) or {}).get("projecao") if c else None
        if pj is not None:
            return pj
        n_ = _rn().du_corridos(k, ndp, ndp_a)
        return v / n_ * ndm if n_ else None

    proj_mes = corre                 # mes em curso: ha projecao
    r_at = rot[0]

    def barras(k, fmt, projetar=False, por_du=False):
        out = []
        for am, r in zip(meses, rot):
            v = V[k][am]
            if v is None:
                vazio = "sem registro" if k in ("vis", "convv", "prim",
                                                "ader", "jorn") else "sem foto"
                if k == "prim" and am == INICIO_REGISTRO_CLIENTE:
                    vazio = "início do registro"
                out.append((r, None, vazio, am == at))
                continue
            if por_du:
                n = _rn().du_corridos(k, ndp, ndp_a) if am == at \
                    else du_m.get(am)
                v = v / n if n else None
                if v is None:
                    out.append((r, None, "—", am == at))
                    continue
            elif projetar and am == at and proj_mes:
                v = proj(k)
                r = f"{r} (proj.)"
            out.append((r, v, fmt(v), am == at))
        return out

    def vars_abs(k, fn, **kw):
        a = proj(k) if (k in VOL and proj_mes) else V[k][at]
        return [(r, *fn(a, V[k][am], **kw)) for am, r in
                zip(meses[1:], rot[1:])]

    vh_vol = f"proj. vs" if proj_mes else f"{r_at} vs"
    vh_dir = f"{r_at} vs"
    cards = []

    def card(chave, titulo, valor, vhead, vars_, linha, gap=None,
             gap_tom="", bars=None, extra=None, regra=""):
        cards.append({"chave": chave, "titulo": titulo, "valor": valor,
                      "vhead": vhead, "vars": vars_, "linha": linha,
                      "gap": gap, "gap_tom": gap_tom, "barras": bars or [],
                      "extra": extra, "regra": regra})

    def ating_vol(k, fmt_gap):
        m_, v = metas.get(k), V[k][at]
        if not m_ or v is None:
            return "sem meta no Painel", None, ""
        pj = proj(k)
        lin = f"ating. {pc(v / m_ * 100)}" + (
            f" (proj. {pc(pj / m_ * 100)})" if pj is not None and proj_mes
            else "")
        falta = m_ - v
        if falta <= 0:
            return lin, "meta batida", "bom"
        return lin, f"gap {fmt_gap(falta)}", (
            "bom" if (pj or 0) >= m_ else "ruim")

    # ---- 1. faturamento
    lin, gap, tom = ating_vol("fat", reais)
    card("fat", "Faturamento líquido", reais(V["fat"][at]), vh_vol,
         vars_abs("fat", _var_pct), lin, gap, tom,
         barras("fat", reais, projetar=True),
         extra=(f"+ {reais(ab_v)} em pedidos em aberto" if ab_v > 0.5
                and corre else None),
         regra="venda − devolução pela data da NF, sem internos, até "
               "ontem; projeção = média por DU × DU do mês; meta = desafio "
               "comercial (Farol de Metas)")
    lin, gap, tom = ating_vol("pos", lambda v: br(v, 0))
    card("pos", "Positivação", br(V["pos"][at], 0), vh_vol,
         vars_abs("pos", _var_pct), lin, gap, tom,
         barras("pos", lambda v: br(v, 0), projetar=True),
         regra="clientes com líquido > 0 no mês (Painel do Diretor); meta = "
               "a do Farol de Metas")
    ipp = {am: (V["itens"][am] / V["ped"][am]) if V["ped"][am] else None
           for am in meses}
    card("ped", "Pedidos faturados", br(V["ped"][at], 0), vh_vol,
         vars_abs("ped", _var_pct),
         f"{br(ipp[at], 1)} itens/ped. · " + " · ".join(
             f"{r} {br(ipp[am], 1)}" for am, r in zip(meses[1:], rot[1:])),
         bars=barras("ped", lambda v: br(v, 0), projetar=True),
         extra=(f"+ {len(ab_ped)} pedidos em aberto ({reais(ab_v)})"
                if ab_ped and corre else None),
         regra="filial + pedido com nota de venda no mês; itens por pedido "
               "= SKUs por nota ÷ pedidos; em aberto = itens sem nota (VEA) "
               "digitados no mês")
    card("ticket", "Ticket por cliente", reais(V["ticket"][at]), vh_dir,
         vars_abs("ticket", _var_pct), "sem meta no Painel",
         bars=barras("ticket", reais),
         regra="faturamento líquido ÷ positivados")
    mk = V["markup"][at]
    card("markup", "Markup", pc(mk, 1), vh_dir, vars_abs("markup", _var_pp),
         f"mín. 15% · ating. {pc(mk / 15 * 100) if mk is not None else '—'}",
         None if mk is None else (
             f"+{br(mk - 15, 1)} p.p. acima" if mk >= 15
             else f"{br(15 - mk, 1)} p.p. abaixo"),
         "" if mk is None else ("bom" if mk >= 15 else "ruim"),
         barras("markup", lambda v: pc(v, 1)),
         regra="venda ÷ custo (P. PEDIDO + sucata) − 1; mínimo 15%")
    dc = V["desc"][at]
    card("desc", "Desconto comercial", pc(dc, 1), vh_dir,
         vars_abs("desc", _var_pp, maior_bom=False),
         f"teto 15% · ating. {pc(15 / dc * 100) if dc else '—'}",
         None if dc is None else (
             f"{br(dc - 15, 1)} p.p. acima do teto" if dc > 15
             else f"{br(15 - dc, 1)} p.p. abaixo do teto"),
         "" if dc is None else ("ruim" if dc > 15 else "bom"),
         barras("desc", lambda v: pc(v, 1)),
         regra="% sobre a tabela, sem o financeiro (Farol de Saldo); teto "
               "15% (subir é pior)")
    card("pecas", "Faturamento de peças", reais(V["pecas"][at]), vh_vol,
         vars_abs("pecas", _var_pct), "sem meta no Painel",
         bars=barras("pecas", reais, projetar=True),
         regra="líquido das famílias de peças (o mesmo do Painel "
               "Executivo)")
    n30 = V["top30"][at]
    m4 = [_mes_ant(ano, mes, n) for n in (4, 1)]
    card("top30", "TOP 30 do gerente que comprou", f"{n30} de 30", vh_dir,
         vars_abs("top30", _var_n), f"lista de 30 · {pc(n30 / 30 * 100)}",
         "lista completa" if n30 >= 30 else f"faltam {30 - n30}",
         "bom" if n30 >= 30 else "ruim", barras("top30", lambda v: br(v, 0)),
         extra=(f"+ {len(top_ab)} com pedido em aberto ({reais(top_ab_v)})"
                if top_ab and corre else None),
         regra=f"os 30 maiores clientes de AM, RR, PA e MA em faturamento "
               f"líquido de {MESES_C[m4[0][1]]} a {MESES_C[m4[1][1]]} (a "
               "regra das contas-chave); quantos compraram em cada mês "
               "(sem projeção: é lista de clientes)")
    # ---- 2. execucao
    lin, gap, tom = ating_vol("vis", lambda v: br(v, 0))
    card("vis", "Visitas", br(V["vis"][at], 0), vh_vol,
         vars_abs("vis", _var_pct), lin, gap, tom,
         barras("vis", lambda v: br(v, 0), projetar=True),
         regra="Espelho da Máxima + prospecção que conta, até ontem; meta "
               "do Farol de Visita")
    cv = V["convv"][at]
    c_dd = cards_m.get((ano, mes), {})
    card("convv", "% Conversão nos visitados", pc(cv), vh_dir,
         vars_abs("convv", _var_pp), "sem meta no Painel",
         None, "", barras("convv", lambda v: pc(v)),
         regra="visitados no mês com pedido VND/VEA no dia da 1ª visita ou "
               "depois ÷ visitados (o cliente conta uma vez na BAP, já "
               "compre ou não)")
    pv1 = V["prim"][at]
    card("prim", "% 1ª visita",
         pc(pv1) if pv1 is not None else (
             (c_dd.get("primeira_visita") or {}).get("valor") or "—"),
         vh_dir, vars_abs("prim", _var_pp), "sem meta no Painel",
         None, "", barras("prim", lambda v: pc(v)),
         regra="visitados no mês que nunca tinham sido visitados antes (em "
               "nenhum mês, por nenhum vendedor) ÷ visitados; o registro "
               "cliente a cliente começa em OUT/26")
    ad = V["ader"][at]
    card("ader", "Aderência à rota", pc(ad), vh_dir, vars_abs("ader", _var_pp,
                                                             dec=0),
         f"meta 90% · ating. {pc(ad / 90 * 100) if ad is not None else '—'}",
         None if ad is None else ("meta batida" if ad >= 90
                                  else f"gap {br(90 - ad, 0)} p.p."),
         "" if ad is None else ("bom" if ad >= 90 else "ruim"),
         barras("ader", lambda v: pc(v)),
         regra="programados do Planner que foram visitados; meta 90%")
    jl = V["jorn"][at]
    card("jorn", "Jornada líquida", hm(jl), vh_dir,
         [(r, *_var_min(jl, V["jorn"][am])) for am, r in
          zip(meses[1:], rot[1:])],
         f"meta 8h · ating. {pc(jl / 8 * 100) if jl is not None else '—'}",
         None if jl is None else ("meta batida" if jl >= 8
                                  else f"gap {hm(8 - jl)}"),
         "" if jl is None else ("bom" if jl >= 8 else "ruim"),
         barras("jorn", hm),
         regra="1ª à última atividade (cliente ou prospecção), no "
               "expediente (média dos dias); "
               "meta 8h; variação em minutos")
    card("cad", "Cadastros com compra", br(V["cad"][at], 0), vh_vol,
         vars_abs("cad", _var_pct), "sem meta no Painel",
         bars=barras("cad", lambda v: br(v, 0), projetar=True),
         regra="clientes cadastrados no mês que compraram no mês")
    ina = V["inad"][at]
    card("inad", "Inadimplência", reais(ina),
         f"foto de {hoje:%d/%m} vs" if corre else vh_dir,
         [(r, *(_var_pct(ina, V["inad"][am], maior_bom=False)
                if V["inad"][am] is not None else ("sem foto", "")))
          for am, r in zip(meses[1:], rot[1:])],
         "títulos vencidos · sem meta no Painel",
         bars=barras("inad", reais),
         regra="títulos vencidos em aberto (foto do dia); os meses "
               "anteriores = o fechamento gravado pelo Painel do Diretor "
               "(subir é pior)")

    # ---- por dia util
    du = []

    def du_card(k, titulo, fmt, com_meta, extra=None, regra=""):
        v = V[k][at]
        n_ = _rn().du_corridos(k, ndp, ndp_a)
        rest = max(0, ndm - n_)         # DU que faltam do cartao
        r_ = v / n_ if (v is not None and n_) else None
        vars_ = []
        for am, r in zip(meses[1:], rot[1:]):
            b = V[k][am]
            n = du_m.get(am)
            vars_.append((r, *_var_pct(r_, b / n if (b is not None and n)
                                       else None)))
        lin, gap, tom = "sem meta no Painel", None, ""
        m_ = metas.get(k) if com_meta else None
        if m_ and r_ is not None:
            md = m_ / ndm
            lin = f"meta {fmt(md)}/DU · ating. {pc(r_ / md * 100)}"
            falta = m_ - v
            if falta <= 0:
                gap, tom = "meta batida", "bom"
            elif rest:
                fd = falta / rest
                gap = f"gap {fmt(fd)}/DU nos {rest} DU"
                tom = "bom" if r_ >= fd else "ruim"
        du.append({"chave": k, "titulo": titulo, "valor": fmt(r_),
                   "vhead": f"{r_at}/DU vs", "vars": vars_, "linha": lin,
                   "gap": gap, "gap_tom": tom, "extra": extra,
                   "barras": barras(k, fmt, por_du=True), "regra": regra})

    du_card("fat", "Faturamento por DU", reais, True,
            regra="faturamento líquido ÷ DU de cada mês")
    du_card("pos", "Positivação por DU", lambda v: br(v, 1), True,
            regra="positivados do mês ÷ DU (o mesmo critério do Painel do "
                  "Diretor)")
    du_card("ped", "Pedidos faturados por DU", lambda v: br(v, 1), False,
            extra=(f"+ {len(ab_ped)} pedidos em aberto "
                   f"({br(len(ab_ped) / ndp, 1)} por DU)"
                   if ab_ped and corre and ndp else None),
            regra="pedidos com nota de venda ÷ DU")
    du_card("vis", "Visitas por DU", lambda v: br(v, 1), True,
            regra="visitas ÷ DU")
    du_card("pecas", "Faturamento de peças por DU", reais, False,
            regra="peças ÷ DU")
    du_card("cad", "Cadastros com compra por DU", lambda v: br(v, 2), False,
            regra="cadastros com compra ÷ DU")
    du_txt = ", ".join(f"{r} {du_m.get(am) or '—'}"
                       for am, r in zip(meses[1:], rot[1:]))
    return {"comp": f"{ano}-{mes:02d}", "ano": ano, "mes": mes,
            "rotulos": rot, "ndp": ndp, "ndm": ndm, "rest": rest,
            "dados_ate": ate, "corre": corre, "abs": cards, "du": du,
            "du_meses": du_txt, "metas": metas, "avisos": avisos,
            "top30": top,
            # (10/11) a base dos cartoes RRM (painel_rrm.py)
            "_V": V, "_meses": meses, "_du_m": du_m, "_dds": dds,
            "_proj": {k_: proj(k_) for k_ in VOL}}


def kpis(dados, visao="abs") -> list:
    """Os cartoes como kpi (Exportar a aba atual: Excel e PDF)."""
    import relatorios_nucleo as rn                      # noqa: PLC0415
    out = []
    for c in dados[visao]:
        det = " · ".join(x for x in (c["linha"], c.get("gap"), c.get("extra"))
                         if x)
        var = " · ".join(f"{m} {t}" for m, t, _tom in c["vars"])
        out.append(rn.kpi(c["titulo"], c["valor"],
                          {"bom": "ok", "ruim": "alerta"}.get(c["gap_tom"],
                                                              "neutro"),
                          f"{det} · {c['vhead']} {var}"))
    return out


def subtitulo(dados, visao="abs") -> str:
    ate = dados["dados_ate"]
    mes_l = MESES_L[dados["mes"]]
    base = (f"{mes_l} até {ate:%d/%m}" if dados["corre"]
            else f"{mes_l} fechado")
    if visao == "abs":
        return (f"{base} · variação × mês fechado (volumes pela projeção) · "
                "barras do mais recente ao mais antigo")
    return (f"{base} · cada mês ÷ os seus dias úteis ({dados['du_meses']}) "
            "· por DU a variação difere da projetada")


# --------------------------------------------------------------- a tela
COR = {"bom": "#2E7D32", "ruim": "#C62828", "": "#5E6B63"}
BARRA_ATUAL = "#1E2722"
BARRA_VELHA = "#C9D1DC"


def tela(pai, dados, visao="abs"):
    """A aba: o titulo com os DU, o subtitulo e a grade de cartoes (4 por
    linha na visao absoluta, com o COMO LER no fim; 3 por linha por DU)."""
    import tkinter as tk                                # noqa: PLC0415
    import bap_visual as bv                             # noqa: PLC0415
    raiz_f = tk.Frame(pai, background=bv.FUNDO)
    cab = tk.Frame(raiz_f, background=bv.FUNDO)
    cab.pack(fill="x", pady=(0, 4))
    tk.Label(cab, text=("Painel · visão absoluta" if visao == "abs"
                        else "Painel · por dia útil"),
             background=bv.FUNDO, foreground=bv.TEXTO,
             font=bv.fonte(11, "bold")).pack(side="left")
    tk.Label(cab, text=f"· {dados['ndp']} de {dados['ndm']} DU",
             background=bv.FUNDO, foreground="#2E7D32",
             font=bv.fonte(11, "bold")).pack(side="left", padx=(8, 0))
    tk.Label(cab, text=subtitulo(dados, visao), background=bv.FUNDO,
             foreground=bv.SUAVE, font=bv.fonte(8)).pack(side="left",
                                                          padx=(10, 0))
    grade = tk.Frame(raiz_f, background=bv.FUNDO)
    grade.pack(fill="both", expand=True)
    cards = list(dados[visao])
    por = 4 if visao == "abs" else 3
    n = len(cards) + (1 if visao == "abs" else 0)
    linhas = (n + por - 1) // por
    for j in range(por):
        grade.columnconfigure(j, weight=1, uniform="c")
    for i in range(linhas):
        grade.rowconfigure(i, weight=1, uniform="l")
    for k, c in enumerate(cards):
        cv = tk.Canvas(grade, background=bv.CARTAO, highlightthickness=1,
                       highlightbackground=bv.CINZA_LINHA, height=150)
        cv.grid(row=k // por, column=k % por, sticky="nsew",
                padx=(0, 8), pady=(0, 8))
        cv.bind("<Configure>", lambda e, cv=cv, c=c: _desenhar(
            cv, c, e.width, e.height, visao))
        bv.Dica(cv, c.get("regra") or "")
    if visao == "abs":
        k = len(cards)
        cv = tk.Canvas(grade, background=bv.TEXTO, highlightthickness=0,
                       height=150)
        cv.grid(row=k // por, column=k % por, sticky="nsew",
                padx=(0, 8), pady=(0, 8))
        cv.bind("<Configure>", lambda e, cv=cv: _como_ler(
            cv, dados, e.width, e.height))
    return raiz_f


def _desenhar(cv, c, w, h, visao):
    import bap_visual as bv                             # noqa: PLC0415
    cv.delete("all")
    x0, y = 14, 10
    alto_ = h >= 300                    # o cartao alto (por DU): letra maior
    grande = 26 if alto_ else 20 if h >= 190 else 16
    cv.create_text(x0, y, anchor="nw", text=c["titulo"].upper(),
                   fill=bv.SUAVE, font=bv.fonte(8, "bold"))
    cv.create_text(x0, y + 17, anchor="nw", text=c["valor"], fill=bv.TEXTO,
                   font=bv.fonte(grande, "bold"))
    # as variacoes empilhadas a direita
    xr = w - 12
    cv.create_text(xr, y, anchor="ne", text=c["vhead"], fill=bv.SUAVE,
                   font=bv.fonte(7))
    for i, (m_, t_, tom) in enumerate(c["vars"]):
        yy = y + 15 + i * 15
        it = cv.create_text(xr, yy, anchor="ne", text=t_, fill=COR[tom],
                            font=bv.fonte(9, "bold"))
        bx = cv.bbox(it)
        cv.create_text((bx[0] if bx else xr - 50) - 6, yy, anchor="ne",
                       text=m_, fill=bv.SUAVE, font=bv.fonte(8))
    # atingimento e gap
    y2 = y + 17 + (grande + 14)
    it = cv.create_text(x0, y2, anchor="nw", text=c["linha"], fill=bv.TEXTO,
                        font=bv.fonte(8))
    if c.get("gap"):
        bx = cv.bbox(it)
        xg = (bx[2] if bx else x0 + 120) + 4
        it2 = cv.create_text(xg, y2, anchor="nw", text="·  ", fill=bv.SUAVE,
                             font=bv.fonte(8))
        bx2 = cv.bbox(it2)
        cv.create_text(bx2[2] if bx2 else xg + 10, y2, anchor="nw",
                       text=c["gap"], fill=COR[c.get("gap_tom") or ""],
                       font=bv.fonte(8, "bold"))
    y3 = y2 + 16
    if c.get("extra"):
        cv.create_text(x0, y3, anchor="nw", text=c["extra"], fill="#2E7D32",
                       font=bv.fonte(8, "bold"))
    y3 += 17
    # as barras dos meses (do mais recente ao mais antigo)
    bars = c["barras"]
    if not bars:
        return
    alto = max(14, min(40 if alto_ else 20, (h - y3 - 8) / len(bars)))
    fb = 10 if alto >= 28 else 8
    rot_w = (74 if any("proj" in b[0] for b in bars) else 40) + (
        12 if fb > 8 else 0)
    bx0 = x0 + rot_w
    txt_w = 110 if fb > 8 else 88
    bmax = max(20, w - bx0 - txt_w - 12)
    nums = [b[1] for b in bars if b[1] is not None and b[1] > 0]
    mx = max(nums) if nums else 1
    for i, (mes, v, txt, atual) in enumerate(bars):
        yy = y3 + i * alto
        cv.create_text(x0, yy + alto / 2, anchor="w", text=mes,
                       fill=bv.TEXTO if atual else bv.SUAVE,
                       font=bv.fonte(fb, "bold" if atual else "normal"))
        if v is None:
            cv.create_text(bx0, yy + alto / 2, anchor="w", text=txt,
                           fill=bv.SUAVE, font=bv.fonte(fb))
            continue
        bw = max(3, bmax * max(v, 0) / mx)
        e = max(6, min(alto * 0.5, 16))
        cv.create_rectangle(bx0, yy + (alto - e) / 2, bx0 + bw,
                            yy + (alto + e) / 2, width=0,
                            fill=BARRA_ATUAL if atual else BARRA_VELHA)
        cv.create_text(bx0 + bw + 6, yy + alto / 2, anchor="w", text=txt,
                       fill=bv.TEXTO,
                       font=bv.fonte(fb, "bold" if atual else "normal"))


def _como_ler(cv, dados, w, h):
    import bap_visual as bv                             # noqa: PLC0415
    cv.delete("all")
    x0, y = 14, 10
    cv.create_text(x0, y, anchor="nw", text="COMO LER", fill="#59BA61",
                   font=bv.fonte(9, "bold"))
    ate = dados["dados_ate"]
    linhas = [
        ("Número grande:", f"{MESES_C[dados['mes']]} até {ate:%d/%m} (o dia "
                           "de hoje fica fora)"),
        ("Ating.:", "real ÷ meta · proj. = no ritmo de hoje até o fim do "
                    "mês"),
        ("Gap:", "meta − real (taxas: até o mínimo ou o teto)"),
        ("", "verde se a projeção bate a meta, vermelho se não bate"),
        ("Variação:", "volumes pela projeção × o mês fechado"),
        ("", "taxas e TOP 30 direto, sem projeção"),
        ("Cores:", "verde melhorou, vermelho piorou"),
        ("", "desconto e inadimplência: subir é pior"),
        ("Por dia útil:", "a aba Painel · por dia útil")]
    yy = y + 24
    passo = max(15, min(20, (h - yy - 8) / len(linhas)))
    for a, b in linhas:
        xb = x0
        if a:
            it = cv.create_text(x0, yy, anchor="nw", text=a, fill="#FFFFFF",
                                font=bv.fonte(8, "bold"))
            bx = cv.bbox(it)
            xb = (bx[2] if bx else x0 + 80) + 5
        else:
            xb = x0 + 12
        cv.create_text(xb, yy, anchor="nw", text=b, fill="#C9D1DC",
                       font=bv.fonte(8), width=w - xb - 10)
        yy += passo
