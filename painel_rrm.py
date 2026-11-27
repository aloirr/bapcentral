"""
PAINEL DO DIRETOR NO MODELO DA RRM (10/11, recado 20261109-1345 do Maestro
Comercial, aprovado pelo Alexandre): tres abas no Painel Executivo, o mesmo
cartao dos slides 3 a 5 do RRM/RPS do Diretor.

  Painel · resultado      - 10 cartoes (faturamento, positivacao, pedidos,
      ticket, pecas, markup, desconto, TOP 30, cadastros com compra e
      inadimplencia);
  Painel · produtividade  - 10 cartoes (visitas, % conversao nos visitados,
      % 1a visita, % fora de rota, jornada, 1o cliente, ultimo cliente,
      almoco, TMA, TMD);
  Painel · por dia util   - os 6 volumes por DU, com os circulos RITMO e
      "N DU".

O cartao: faixa (rotulo, numero grande, circulos MTD/MES ou RITMO/N DU com
o % e so a meta embaixo), a faixa de comparacao (mes anterior, o anterior a
ele e julho - benchmarking - com a variacao colorida e o fechamento real),
o filete verde e, na parte branca, as barras por estado (PA, MA, AM, RR,
na ordem do faturamento no ano; MT/AP quando tem valor) com o % de
atingimento da meta do estado ou, sem meta, a variacao x mes anterior.

Fontes: o Painel do Diretor (painel_diretor.calcular) do mes e dos meses de
comparacao, o Painel em cartoes (painel_cartoes.calcular: pedidos, pecas,
cadastros, TOP 30) e a TABELA_BAP (o estado do faturamento, positivacao,
pedidos, pecas e cadastros = FILIAL DA NOTA). Visitas, jornada, horarios,
TMA, TMD, % fora de rota, conversao e 1a visita = o estado do supervisor
(Farol de Visita, Por supervisor). Markup = Farol de Markup Por UF;
desconto = Farol de Saldo Por UF; inadimplencia = Por UF (filial do
titulo); metas por estado = Farol de Metas Equipe, Por supervisor.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

import painel_cartoes as pcx

M = "−"
ORDEM_UF = ["PA", "MA", "AM", "RR"]      # [SUPOSICAO] faturamento no ano
MESES_C = pcx.MESES_C
MESES_L = pcx.MESES_L
SUP_UF = {"DENYLSON": "MA", "LAIS": "PA", "FRANCISCO": "AM"}
# metas fixas das taxas e dos horarios (Alexandre, 09/11)
META_MARKUP, META_DESC, META_FORA = 15.0, 15.0, 20.0
META_JORN, META_INI, META_ULT, META_ALM = 8.0, 8.0, 17.0, 1.5
META_TMA, META_TMD = 20.0, 15.0          # minutos (TMA [SUPOSICAO] minimo)
VISOES = (("res", "Painel · resultado"), ("prod", "Painel · produtividade"),
          ("du", "Painel · por dia útil"))
TITULOS = {"res": "Painel do Diretor · resultado",
           "prod": "Painel do Diretor · produtividade",
           "du": "Painel do Diretor · por dia útil"}


# --------------------------------------------------------------- formatos
br, reais = pcx.br, pcx.reais


def pc(v, d=0):
    return "—" if v is None else br(v, d) + "%"


def hm(h):
    if h is None:
        return "—"
    t = int(round(h * 60))
    return f"{t // 60}h{t % 60:02d}"


def mins(h):
    return "—" if h is None else f"{int(round(h * 60))} min"


def compacto(v, dinheiro=False):
    """o numero embaixo do % do circulo (so a meta): 1,50 mi, 395 mil, 43."""
    if v is None:
        return ""
    a = abs(v)
    if dinheiro or a >= 1e4:
        if a >= 1e6:
            return f"{br(v / 1e6, 2)} mi"
        if a >= 1e5:
            return f"{br(v / 1e3, 0)} mil"
        if a >= 1e3:
            return f"{br(v / 1e3, 1)} mil"
        return br(v, 0)
    return br(v, 0) if a >= 10 or a == int(a) else br(v, 1)


def _rn():
    import relatorios_nucleo as rn                      # noqa: PLC0415
    return rn


def _hora(s):
    """'08:53' -> 8,883 (horas); '00:15:53' -> 0,2647 (com os segundos,
    T-0060: arredonda so no fim); None/'' -> None."""
    m_ = re.match(r"\s*(\d{1,2}):(\d{2})(?::(\d{2}))?", str(s or ""))
    return (int(m_.group(1)) + int(m_.group(2)) / 60
            + int(m_.group(3) or 0) / 3600) if m_ else None


def _num(v):
    return v if isinstance(v, (int, float)) else None


def tom_de(p):
    if p is None:
        return ""
    return "ok" if p >= 100 else ("atencao" if p >= 90 else "alerta")


# --- variacoes: (texto, tom) com tom ok (melhorou) / alerta (piorou)
def v_pct(a, b, bom=True):
    if a is None or not b:
        return ("", "")
    x = (a / b - 1) * 100
    if abs(x) < 0.5:
        return ("igual", "")
    return (("+" if x > 0 else M) + br(abs(x), 0) + "%",
            "ok" if (x > 0) == bom else "alerta")


def v_pp(a, b, bom=True, dec=1):
    if a is None or b is None:
        return ("", "")
    x = a - b
    if abs(x) < 0.05:
        return ("igual", "")
    return (("+" if x > 0 else M) + br(abs(x), dec) + " p.p.",
            "ok" if (x > 0) == bom else "alerta")


def v_n(a, b, bom=True):
    if a is None or b is None:
        return ("", "")
    x = a - b
    if not x:
        return ("igual", "")
    return (("+" if x > 0 else M) + br(abs(x), 0),
            "ok" if (x > 0) == bom else "alerta")


def v_min(a, b, bom=True):
    if a is None or b is None:
        return ("", "")
    x = round((a - b) * 60)
    if not x:
        return ("igual", "")
    return (("+" if x > 0 else M) + f"{abs(x)} min",
            "ok" if (x > 0) == bom else "alerta")


# ------------------------------------------------------------ por estado
def _uf_sup(nome):
    import relatorios_nucleo as rn                      # noqa: PLC0415
    n_ = rn.sem_acento(str(nome or "")).upper()
    return next((u for p_, u in SUP_UF.items() if n_.startswith(p_)), None)


def _coluna(cols, *nomes):
    for n_ in nomes:
        if n_ in cols:
            return cols.index(n_)
    return None


def _por_sup(tab, *nomes, conv=None):
    """{UF: valor} da tabela Por supervisor (cols, linhas, total)."""
    cols, linhas, _t = tab or ([], [], None)
    i = _coluna(cols, *nomes)
    if i is None:
        return {}
    out = {}
    for l in linhas:
        uf = _uf_sup(l[0])
        if uf:
            v = conv(l[i]) if conv else _num(l[i])
            if v is not None:
                out[uf] = v
    return out


def _total(tab, *nomes, conv=None):
    cols, _l, tot = tab or ([], [], None)
    i = _coluna(cols, *nomes)
    if i is None or not tot:
        return None
    return conv(tot[i]) if conv else _num(tot[i])


def _por_uf(tab, *nomes, mes_txt=None):
    """{UF: valor} da tabela Por UF (o Saldo comeca pelo MES)."""
    cols, linhas, _t = tab or ([], [], None)
    i = _coluna(cols, *nomes)
    i_uf = _coluna(cols, "UF")
    if i is None or i_uf is None:
        return {}
    i_m = _coluna(cols, "MÊS")
    out = {}
    for l in linhas:
        if i_m is not None and mes_txt and str(l[i_m]).upper() != mes_txt:
            continue
        v = _num(l[i])
        if v is not None and l[i_uf]:
            out[str(l[i_uf]).upper()] = v
    return out


def _da_tabela_uf(ctx, ano, mes, ate, top):
    """Por ESTADO (filial da nota) no mes ate a data: faturamento,
    positivados, pedidos, pecas, cadastros com compra (o estado da 1a nota
    do cliente no mes [SUPOSICAO]) e o TOP 30 (UF do cliente)."""
    import relatorios_nucleo as rn                      # noqa: PLC0415
    fat, pecas = defaultdict(float), defaultdict(float)
    por_uf, prim = defaultdict(list), {}
    tot_cli = defaultdict(float)
    for it in ctx.tabela["itens"]:
        d = it.get("dt_nf")
        if not d or d.year != ano or d.month != mes or d > ate:
            continue
        v = rn._liquido(it)
        if v is None:
            continue
        uf = rn.uf_da_filial(it.get("filial")) or "?"
        fat[uf] += v
        tot_cli[it["cliente"]] += v
        por_uf[uf].append(it)
        if rn._eh_pecas(ctx, it["cod"]):
            pecas[uf] += v
        if it["tipo"] == "VND":
            if it["cliente"] not in prim or d < prim[it["cliente"]][0]:
                prim[it["cliente"]] = (d, uf)
    cad = defaultdict(int)
    # T-0060 (item 4): cadastro com COMPRA = positivado (liquido > 0 ate a
    # data), a mesma regra do Metas
    posit = rn.clientes_positivados_ate(ctx.tabela["itens"], ate)
    for cod, c in (ctx.tabela.get("clientes") or {}).items():
        dc = rn._dia(c.get("dtcad"))
        if dc and dc.year == ano and dc.month == mes and dc <= ate \
                and cod in prim and cod in posit:
            cad[prim[cod][1]] += 1
    # RN-GER-002, 003 e 005: positivados e pedidos por UF pelas funcoes puras
    pos = {u: len(rn.clientes_positivados_ate(its, ate))
           for u, its in por_uf.items()}
    ped = {u: len(rn.pedidos_faturados_ate(its, ate))
           for u, its in por_uf.items()}
    t30, n30 = defaultdict(int), defaultdict(int)
    for c in top or []:
        u = str((ctx.cliente(c) or {}).get("uf") or "").upper()
        n30[u] += 1
        if tot_cli.get(c, 0) > 0.005:
            t30[u] += 1
    tk = {u: fat[u] / pos[u] for u in fat if pos.get(u)}
    out = {"fat": dict(fat), "pos": pos,
           "ped": ped,
           "pecas": dict(pecas), "cad": dict(cad), "ticket": tk,
           "top30": {u: t30.get(u, 0) for u in n30}, "top30_n": dict(n30)}
    # (10/11) estado da BAP (filial) sem nota no mes = 0, nao em branco
    for k in ("fat", "pos", "ped", "pecas", "cad"):
        for u in ORDEM_UF:
            out[k].setdefault(u, 0)
    return out


def barras_uf(vals, fmt, meta_uf=None, ating=None, ant=None, var=v_pct,
              extras=False, txt_uf=None, leg_meta=None):
    """{"barras": [(UF, numero, texto, % ou variacao, tom)], "legenda"}.
    Com meta do estado: % = valor / meta; com meta fixa (taxas): ating(v);
    sem meta: a variacao x mes anterior (ant). Estado sem dado: em branco."""
    ufs = list(ORDEM_UF)
    if extras:
        ufs += sorted((u for u, v in vals.items()
                       if u not in ORDEM_UF and u not in ("", "?") and v),
                      key=lambda u: -abs(vals[u]))
    out, usou_m, usou_v = [], False, False
    for uf in ufs:
        v = vals.get(uf)
        if v is None:
            out.append((uf, None, "", "", ""))
            continue
        txt = txt_uf(uf, v) if txt_uf else fmt(v)
        if ating is not None:
            p_ = ating(v)
            out.append((uf, v, txt, pc(p_) if p_ is not None else "",
                        tom_de(p_)))
            usou_m = usou_m or p_ is not None
            continue
        m_ = (meta_uf or {}).get(uf)
        if m_:
            p_ = v / m_ * 100
            out.append((uf, v, txt, pc(p_), tom_de(p_)))
            usou_m = True
            continue
        if ant is not None and ant.get(uf) is not None:
            t_, tm = var(v, ant.get(uf))
            t_ = t_.replace(" p.p.", "").replace(" min", "")
            out.append((uf, v, txt, "" if t_ == "igual" else t_, tm))
            usou_v = usou_v or bool(t_)
            continue
        out.append((uf, v, txt, "", ""))
    un = {v_pp: " (p.p.)", v_min: " (min)", v_n: " (clientes)"}.get(var, "")
    partes = []
    if usou_m:
        partes.append(leg_meta or "atingimento da meta do mês "
                                  "(projeção ÷ meta)")
    if usou_v:
        partes.append("variação × mês anterior" + un)
    if all(b[1] in (None, 0) for b in out):
        return None
    return {"barras": out, "legenda": " · ".join(partes)}


# ------------------------------------------------------------- calcular
def calcular(ctx, ano, mes, dd=None, dc=None) -> dict:
    """As 3 visoes (res, prod, du), cada uma uma lista de cartoes:
    {chave, titulo, valor, legenda, aneis [(rotulo, %, meta)], faixa [(mes,
    variacao, tom, fechamento)], estados, ajuda}."""
    dd = pcx._diretor(ctx, ano, mes, dd)
    if dc is None or dc.get("_meses", [None, None, None, None])[3] != \
            pcx._mes_ant(ano, mes, pcx.dist_rrm(mes)[2]):
        dc = pcx.calcular(ctx, ano, mes, dd, dist=pcx.dist_rrm(mes))
    V, meses, du_m, dds = dc["_V"], dc["_meses"], dc["_du_m"], dc["_dds"]
    at, comp_m = meses[0], meses[1:]
    rot = [("jul (bench.)" if (j == 2 and m_ == 7) else MESES_C[m_])
           for j, (_a, m_) in enumerate(comp_m)]
    ndp, ndm = dd["ndp"], dd["ndm"]
    rest = max(0, ndm - ndp)
    ate = dd["dados_ate"]                    # grupo B (ate ontem)
    ndp_a = dd.get("ndp_a", ndp)             # grupo A: hoje conta
    ate_a = dd.get("dados_ate_a") or ate
    corre = at == (ctx.hoje.year, ctx.hoje.month)
    cards_at = {c["chave"]: c for c in dd["cards"]}
    tabs = dd.get("_tabs") or {}
    ant = comp_m[0]
    d_ant = dds.get(ant) or {}
    tabs_ant = d_ant.get("_tabs") or {}

    def fim(a, m):
        return date(a + (m == 12), m % 12 + 1, 1) - timedelta(days=1)

    top = dc.get("top30") or []
    uf_at = _da_tabela_uf(ctx, *at, ate_a, top)
    if ate != ate_a:                # decisao 48: pecas e cadastros ate ontem
        uf_b = _da_tabela_uf(ctx, *at, ate, top)
        uf_at["pecas"], uf_at["cad"] = uf_b["pecas"], uf_b["cad"]
    uf_ant = _da_tabela_uf(ctx, *ant, fim(*ant), top)

    # metas do mes e por estado (Farol de Metas Equipe, Por supervisor)
    ms = tabs.get("meta_sup")
    meta_uf = {k: _por_sup(ms, c_) for k, c_ in (
        ("fat", "FAT. META"), ("pos", "POSIT. META"),
        ("vis", "VISITA META"), ("pecas", "PEÇAS META"),
        ("cad", "CAD. META"))}
    metas = {"fat": (cards_at.get("fat") or {}).get("meta"),
             "pos": (cards_at.get("pos") or {}).get("meta"),
             "vis": (cards_at.get("visitas") or {}).get("meta"),
             "pecas": _total(ms, "PEÇAS META") or (
                 sum(meta_uf["pecas"].values()) or None),
             "cad": _total(ms, "CAD. META") or (
                 sum(meta_uf["cad"].values()) or None)}
    vs = tabs.get("vis_sup")
    meta_vis_ate = _total(vs, "META")          # Farol de Visita (ate a data)

    def proj(k):
        return dc["_proj"].get(k) if corre else V[k][at]

    def faixa(k, fn, fmt, projetar=False, **kw):
        a_ = proj(k) if projetar else V[k][at]
        out = []
        for am, r in zip(comp_m, rot):
            b = V[k].get(am)
            t_, tm = fn(a_, b, **kw) if b is not None else ("", "")
            out.append((r, t_, tm, fmt(b) if b is not None else "—"))
        return out

    def aneis_vol(k, real, pj, dinheiro=False, meta_ate=None):
        m_ = metas.get(k)
        if not m_ or real is None:
            return []
        n_ = ndp if k in _rn().GRUPO_B_CARTOES else ndp_a    # A: hoje conta
        ma = meta_ate if meta_ate else m_ * n_ / ndm if ndm else None
        out = []
        if ma:
            out.append(("MTD", real / ma * 100, compacto(ma, dinheiro)))
        if pj is not None:
            out.append(("MÊS", pj / m_ * 100, compacto(m_, dinheiro)))
        return out

    def fator(k):
        r_, p_ = V[k][at], proj(k)
        return (p_ / r_) if (r_ and p_ is not None) else 1.0

    def proj_uf(vals, k):
        f_ = fator(k)
        return {u: v * f_ for u, v in vals.items()}

    res, prod, du = [], [], []

    def card(lista, chave, titulo, valor, legenda="", aneis=(), fx=(),
             estados=None, ajuda=""):
        if corre and ate != ate_a and chave in _rn().GRUPO_B_CARTOES:
            titulo += _rn().sufixo_periodo(ate)
        lista.append({"chave": chave, "titulo": titulo, "valor": valor,
                      "legenda": legenda, "aneis": list(aneis),
                      "faixa": list(fx), "estados": estados,
                      "ajuda": ajuda})

    leg_proj = "projeção do mês" if corre else "fechamento do mês"

    # ============================== RESULTADO
    pj = proj("fat")
    card(res, "fat", "Faturamento líquido" + (" · proj." if corre else ""),
         reais(pj), leg_proj,
         aneis_vol("fat", V["fat"][at], pj, True),
         faixa("fat", v_pct, reais, True),
         barras_uf(proj_uf(uf_at["fat"], "fat"), reais, meta_uf["fat"],
                   extras=True),
         "venda − devolução pela data da NF, sem internos, até ontem; "
         "projeção = real ÷ DU passados × DU do mês; estado = filial da "
         "nota; % = projeção do estado ÷ meta do supervisor do estado")
    pj = proj("pos")
    card(res, "pos", "Positivação", br(V["pos"][at]),
         f"projeção do mês {br(pj)}" if corre else "",
         aneis_vol("pos", V["pos"][at], pj),
         faixa("pos", v_pct, br, True),
         barras_uf(proj_uf(uf_at["pos"], "pos"), br, meta_uf["pos"],
                   extras=True),
         "clientes com líquido > 0 no mês; estado = filial da nota")
    pj = proj("ped")
    card(res, "ped", "Pedidos faturados" + (" · proj." if corre else ""),
         br(pj), leg_proj, (), faixa("ped", v_pct, br, True),
         barras_uf(proj_uf(uf_at["ped"], "ped"), br,
                   ant=uf_ant["ped"], extras=True),
         "filial + pedido com nota de venda no mês; sem meta: a barra "
         "mostra a variação da projeção do estado × mês anterior")
    card(res, "ticket", "Ticket por cliente", reais(V["ticket"][at]), "", (),
         faixa("ticket", v_pct, reais),
         barras_uf(uf_at["ticket"], reais, ant=uf_ant["ticket"]),
         "faturamento líquido ÷ positivados; sem meta")
    pj = proj("pecas")
    card(res, "pecas", "Faturamento de peças" + (" · proj." if corre
                                                 else ""),
         reais(pj), leg_proj, aneis_vol("pecas", V["pecas"][at], pj, True),
         faixa("pecas", v_pct, reais, True),
         barras_uf(proj_uf(uf_at["pecas"], "pecas"), reais,
                   meta_uf["pecas"], extras=True),
         "líquido das linhas de peças; meta = Farol de Metas Equipe "
         "(PEÇAS META, soma dos supervisores)")
    mk = V["markup"][at]
    card(res, "markup", "Markup", pc(mk, 1), "",
         [("MÊS", mk / META_MARKUP * 100, "mín. 15%")] if mk is not None
         else [],
         faixa("markup", v_pp, lambda v: pc(v, 1)),
         barras_uf(_por_uf(tabs.get("mk_uf"), "MARKUP %"),
                   lambda v: pc(v, 1),
                   ating=lambda v: v / META_MARKUP * 100,
                   leg_meta="atingimento da meta (mín. 15%)"),
         "venda ÷ custo − 1 (Farol de Markup); mínimo 15%; estado = "
         "Farol de Markup Por UF (filial da nota)")
    ds = V["desc"][at]
    mes_txt = f"{MESES_C[at[1]].upper()}/{str(at[0])[2:]}"
    card(res, "desc", "Desconto comercial", pc(ds, 1), "",
         [("MÊS", META_DESC / ds * 100, "teto 15%")] if ds else [],
         faixa("desc", v_pp, lambda v: pc(v, 1), bom=False),
         barras_uf(_por_uf(tabs.get("saldo_uf"), "% DESC. COM.",
                           mes_txt=mes_txt),
                   lambda v: pc(v, 1),
                   ating=lambda v: META_DESC / v * 100 if v else None,
                   leg_meta="atingimento da meta (teto 15%)"),
         "% sobre a tabela (Farol de Saldo); teto 15% (menor é melhor: "
         "teto ÷ real); estado = Farol de Saldo Por UF")
    n30 = V["top30"][at]
    card(res, "top30", "TOP 30 que comprou", f"{br(n30)} de 30", "",
         [("MÊS", n30 / 30 * 100, "30")] if n30 is not None else [],
         faixa("top30", v_n, br),
         barras_uf(uf_at["top30"], br, ant=uf_ant["top30"], var=v_n,
                   txt_uf=lambda u, v: f"{br(v)} de "
                   f"{br(uf_at['top30_n'].get(u, 0))}"),
         "os 30 maiores clientes de AM, RR, PA e MA nos 4 meses fechados "
         "antes do mês; estado = UF do cliente")
    pj = proj("cad")
    card(res, "cad", "Cadastros com compra", br(V["cad"][at]),
         f"projeção do mês {br(pj)}" if corre else "",
         aneis_vol("cad", V["cad"][at], pj),
         faixa("cad", v_pct, br, True),
         barras_uf(proj_uf(uf_at["cad"], "cad"), br, meta_uf["cad"]),
         "clientes cadastrados no mês que compraram no mês; meta = Farol "
         "de Metas Equipe (CAD. META); estado = filial da 1ª nota "
         "[SUPOSIÇÃO]")
    ina = V["inad"][at]
    card(res, "inad", "Inadimplência", reais(ina), "", (),
         faixa("inad", v_pct, reais, bom=False),
         barras_uf(_por_uf(tabs.get("inad_uf"), "EM ATRASO"), reais,
                   extras=True),
         "títulos vencidos em aberto (foto do dia); estado = filial do "
         "título; meses anteriores = o fechamento gravado pelo Painel do "
         "Diretor")

    # ============================== PRODUTIVIDADE
    def tot_m(am, *nomes, conv=None):
        if V["vis"].get(am) is None:
            return None
        t_ = ((dds.get(am) or {}).get("_tabs") or {}).get("vis_sup")
        return _total(t_, *nomes, conv=conv)
    P = {k: {am: tot_m(am, *n_, conv=cv) for am in meses}
         for k, n_, cv in (("fora", ("% FORA DE ROTA",), None),
                           ("ini", ("INÍCIO",), _hora),
                           ("ult", ("ÚLT. ATIV.",), _hora),
                           ("alm", ("INTERV. ALMOÇO",), _hora),
                           ("tma", ("TMA",), _hora),
                           ("tmd", ("TMD",), _hora))}
    V2 = dict(V)
    V2.update(P)

    def fx2(k, fn, fmt, **kw):
        a_ = V2[k][at]
        out = []
        for am, r in zip(comp_m, rot):
            b = V2[k].get(am)
            t_, tm = fn(a_, b, **kw) if (b is not None and a_ is not None) \
                else ("", "")
            out.append((r, t_, tm, fmt(b) if b is not None else "—"))
        return out

    vis, pjv = V["vis"][at], proj("vis")
    card(prod, "vis", "Visitas", br(vis),
         f"projeção do mês {br(pjv)}" if corre else "",
         aneis_vol("vis", vis, pjv, meta_ate=meta_vis_ate),
         faixa("vis", v_pct, br, True),
         barras_uf(proj_uf(_por_sup(vs, "VISIT."), "vis"), br,
                   meta_uf["vis"]),
         "Espelho da Máxima + prospecção que conta, até ontem; MTD = real ÷ "
         "meta até a data do Farol de Visita; estado = supervisor")
    cu_ = dd.get("_conv_uf") or {}
    cu_a = d_ant.get("_conv_uf") or {}

    def conv_uf(cu, i):
        return {u: t[i] / t[0] * 100 for u, t in cu.items()
                if t[0] and t[i] is not None}
    card(prod, "convv", "% Conversão nos visitados", pc(V["convv"][at], 1),
         "", (), fx2("convv", v_pp, lambda v: pc(v, 1)),
         barras_uf(conv_uf(cu_, 1), lambda v: pc(v, 1),
                   ant=conv_uf(cu_a, 1), var=v_pp),
         "visitados no mês com pedido no dia da 1ª visita ou depois ÷ "
         "visitados; sem meta; estado = supervisor do vendedor")
    card(prod, "prim", "% 1ª visita", pc(V["prim"][at], 1), "", (),
         fx2("prim", v_pp, lambda v: pc(v, 1)),
         barras_uf(conv_uf(cu_, 2), lambda v: pc(v, 1),
                   ant=conv_uf(cu_a, 2), var=v_pp),
         "visitados no mês nunca visitados antes ÷ visitados; sem meta")
    fo = V2["fora"][at]
    card(prod, "fora", "% Fora de rota", pc(fo), "",
         [("MÊS", META_FORA / fo * 100, "20%")] if fo else [],
         fx2("fora", v_pp, pc, bom=False, dec=0),
         barras_uf(_por_sup(vs, "% FORA DE ROTA"), pc,
                   ating=lambda v: META_FORA / v * 100 if v else None,
                   leg_meta="atingimento da meta (máx. 20%)"),
         "visitas fora da rota do Planner ÷ visitas; meta máx. 20% "
         "(menor é melhor)")
    jl = V["jorn"][at]
    card(prod, "jorn", "Jornada líquida", hm(jl), "",
         [("MÊS", jl / META_JORN * 100, "8h00")] if jl else [],
         fx2("jorn", v_min, hm),
         barras_uf(_por_sup(vs, "JORNADA LÍQ.", conv=_hora), hm,
                   ating=lambda v: v / META_JORN * 100,
                   leg_meta="atingimento da meta (8h)"),
         "1ª à última atividade (cliente ou prospecção), no expediente; "
         "meta 8h")
    for k, tit, col, meta_, menor, fmt, rot_m in (
            ("ini", "1º cliente", "INÍCIO", META_INI, True, hm, "8h00"),
            ("ult", "Último cliente", "ÚLT. ATIV.", META_ULT, False, hm,
             "17h00"),
            ("alm", "Intervalo de almoço", "INTERV. ALMOÇO", META_ALM,
             True, hm, "1h30"),
            ("tma", "TMA · atendimento", "TMA", META_TMA / 60, False, mins,
             "20 min"),
            ("tmd", "TMD · deslocamento", "TMD", META_TMD / 60, True, mins,
             "15 min")):
        v_ = V2[k][at]

        def at_(x, m_=meta_, men=menor):
            if not x:
                return None
            return (m_ / x if men else x / m_) * 100
        card(prod, k, tit, fmt(v_), "",
             [("MÊS", at_(v_), rot_m)] if v_ else [],
             fx2(k, v_min, fmt, bom=not menor),
             barras_uf(_por_sup(vs, col, conv=_hora), fmt, ating=at_,
                       leg_meta=f"atingimento da meta ({rot_m})"),
             f"Farol de Visita (Por supervisor, TOTAL = BAP); meta {rot_m} "
             + ("(menor é melhor: meta ÷ real)" if menor
                else "(real ÷ meta)"))

    # ============================== POR DIA UTIL
    def du_card(k, titulo, fmt, vals_uf, com_meta=True, n_=None):
        n_ = n_ or (ndp if k in _rn().GRUPO_B_CARTOES else ndp_a)
        rest = max(0, ndm - n_)         # A: ndm - ndp_a; B: ndm - ndp
        v = V[k][at]
        r_ = v / n_ if (v is not None and n_) else None
        fx = []
        for am, r in zip(comp_m, rot):
            b, nb = V[k].get(am), du_m.get(am)
            bd_ = b / nb if (b is not None and nb) else None
            t_, tm = v_pct(r_, bd_)
            fx.append((r, t_, tm, fmt(bd_) if bd_ is not None else "—"))
        m_ = metas.get(k) if com_meta else None
        aneis = []
        if m_ and r_ is not None and ndm:
            md = m_ / ndm
            aneis.append(("RITMO", r_ / md * 100, fmt(md).replace("R$ ",
                                                                  "")))
            falta = m_ - v
            if rest:
                fd = max(falta, 0) / rest
                aneis.append((f"{rest} DU", r_ / fd * 100 if fd else 100.0,
                              fmt(fd).replace("R$ ", "")))
        ru = {u: x / n_ for u, x in vals_uf.items()} if n_ else {}
        mu = {u: x / ndm for u, x in (meta_uf.get(k) or {}).items()} \
            if com_meta else None
        ant_u = None
        if not com_meta:
            nb = du_m.get(ant)
            ant_u = {u: x / nb for u, x in uf_ant.get(k, {}).items()} \
                if nb else None
        card(du, k, titulo, fmt(r_), "", aneis, fx,
             barras_uf(ru, fmt, mu, ant=ant_u,
                       leg_meta="atingimento do ritmo × meta por DU"),
             f"{titulo}: o mês ÷ os seus dias úteis; RITMO = ritmo ÷ meta "
             f"do mês por DU; {rest} DU = ritmo ÷ o que falta da meta por "
             "DU restante")
    du_card("fat", "Faturamento por DU", reais, uf_at["fat"], n_=ndp_a)
    du_card("pos", "Positivação por DU", lambda v: br(v, 1), uf_at["pos"],
            n_=ndp_a)
    du_card("ped", "Pedidos faturados por DU", lambda v: br(v, 1),
            uf_at["ped"], com_meta=False, n_=ndp_a)
    du_card("vis", "Visitas por DU", lambda v: br(v, 1),
            _por_sup(vs, "VISIT."), n_=dd.get("_ndp_vis") or ndp)
    du_card("pecas", "Faturamento de peças por DU", reais, uf_at["pecas"])
    du_card("cad", "Cadastros com compra por DU", lambda v: br(v, 2),
            uf_at["cad"])

    base = (f"{MESES_L[mes]} até {ate_a:%d/%m} ({ndp_a} de {ndm} dias úteis)"
            if corre else f"{MESES_L[mes]} fechado ({ndm} dias úteis)")
    du_txt = ", ".join(f"{r.split()[0]} {du_m.get(am) or '—'}"
                       for am, r in zip(comp_m, rot))
    sub = {"res": f"visão absoluta · {base} · variação × mês fechado",
           "prod": f"visão absoluta · {base} · variação × mês fechado",
           "du": f"visão por dia útil · {MESES_C[mes]} tem {ndm} DU "
                 f"({du_txt}): por DU a variação difere da projetada"}
    como = ("Número grande: faturamento, peças e pedidos = projeção do mês; "
            "os demais = real até a data. MTD = real ÷ meta até a data; "
            "MÊS = projeção ÷ meta do mês (embaixo do % só a meta); nas "
            "taxas, um círculo (real ÷ meta; menor é melhor = meta ÷ real). "
            "Faixa: fechamento real do mês anterior, do anterior a ele e de "
            "julho (benchmarking), com a variação. Barras: estados na ordem "
            "do faturamento no ano (" + ", ".join(ORDEM_UF) + "); % = "
            "atingimento da meta do estado, ou variação × mês anterior sem "
            "meta. Cores: verde ≥ 100%, amarelo 90–99%, vermelho < 90%.")
    return {"comp": f"{ano}-{mes:02d}", "ano": ano, "mes": mes,
            "res": res, "prod": prod, "du": du, "sub": sub,
            "como_ler": como, "dados_ate": ate_a,
            "avisos": list(dc.get("avisos") or [])}


def kpis(dados, visao="res") -> list:
    """Os cartoes como kpi (Exportar a aba atual: Excel e PDF)."""
    import relatorios_nucleo as rn                      # noqa: PLC0415
    out = []
    for c in dados[visao]:
        lin = [(f"Ating. {a}", pc(p), "") for a, p, _m in c["aneis"]]
        lin += [(f"{r} {t}".strip(), f_, "") for r, t, _tm, f_ in c["faixa"]]
        if c.get("estados"):
            lin += [(f"{b[0]}", f"{b[2]} {b[3]}".strip(), "")
                    for b in c["estados"]["barras"] if b[1] is not None]
        tom = tom_de(c["aneis"][-1][1]) if c["aneis"] else ""
        out.append(rn.kpi(c["titulo"], c["valor"],
                          {"ok": "ok", "atencao": "atencao",
                           "alerta": "alerta"}.get(tom, "neutro"),
                          c.get("legenda") or "", lin))
    return out


# ------------------------------------------------------------------ tela
# (11/11, Alexandre: "Aumente os cartoes, reduza um em cada linha... quatro
# por linha no maximo para ficar legivel tanto o numero principal quanto os
# debaixo") - resultado e produtividade com 4 por linha; por dia util com 3
# (11/11 ~09h15, Alexandre: "ainda pequeno, preciso aumentar mais" -> 3 por
# linha com a letra minima maior; "Aprovado. so coloque um espaco maior
# embaixo do card para separar um do outro")
POR_LINHA = {"res": 3, "prod": 3, "du": 3}
ESPACO_ENTRE = 26                       # px embaixo de cada cartao
# a altura minima da aba (a tela rola quando a janela e menor)
ALTURA_MIN = {"res": 4 * (560 + ESPACO_ENTRE),
              "prod": 4 * (560 + ESPACO_ENTRE),
              "du": 2 * (560 + ESPACO_ENTRE) + 30}


def escala_da_tela(pai, ncol):
    """(11/11) largura do cartao pela largura da tela e a escala da letra:
    1920 px com 4 por linha = ~450 px e letra 1,35x."""
    try:
        sw = int(pai.winfo_screenwidth())
    except Exception:                                   # noqa: BLE001
        sw = 1920
    larg = int((max(sw, 1280) - 70) / ncol) - 10
    return larg, max(1.0, min(1.6, larg / 330))


def tela(pai, dados, visao="res", exportar=None):
    import tkinter as tk                                # noqa: PLC0415
    import bap_visual as bv                             # noqa: PLC0415
    f = tk.Frame(pai, background=bv.FUNDO)
    cab = tk.Frame(f, background=bv.FUNDO)
    cab.pack(fill="x", pady=(0, 6))
    tk.Label(cab, text=TITULOS[visao], background=bv.FUNDO,
             foreground=bv.TEXTO, font=bv.fonte(12, "bold")).pack(
                 side="left")
    tk.Label(cab, text=dados["sub"][visao], background=bv.FUNDO,
             foreground=bv.SUAVE, font=bv.fonte(9)).pack(side="left",
                                                        padx=(10, 0))
    if exportar:
        for t_, tipo in (("PDF", "pdf"), ("PNG", "png")):
            tk.Button(cab, text=t_, relief="flat", cursor="hand2",
                      background=bv.CARTAO, foreground=bv.TEXTO,
                      font=bv.fonte(9), padx=12,
                      command=lambda tp=tipo: exportar(tp)).pack(
                          side="right", padx=(6, 0))
    grade = tk.Frame(f, background=bv.FUNDO)
    grade.pack(fill="both", expand=True)
    cs = dados[visao]
    ncol = POR_LINHA.get(visao, 4)
    larg, esc = escala_da_tela(pai, ncol)
    for i, c in enumerate(cs):
        r_, k_ = divmod(i, ncol)
        grade.columnconfigure(k_, weight=1, uniform="rrm")
        grade.rowconfigure(r_, weight=1, uniform="lin")
        bv.cartao_rrm_spec(grade, c, larg, escala=esc).grid(
            row=r_, column=k_, sticky="nsew", padx=(0, 10),
            pady=(0, ESPACO_ENTRE))
    tk.Label(f, text=dados["como_ler"], background=bv.FUNDO,
             foreground=bv.SUAVE, font=bv.fonte(7), anchor="w",
             justify="left", wraplength=1500).pack(fill="x", pady=(2, 0))
    return f


# ------------------------------------------------------- imagem / PDF
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def imagem(dados, visao="res", destino_png=None, destino_pdf=None):
    """O painel numa imagem (1920 de largura x 1,25) no mesmo modelo da
    tela e dos slides do RRM: PNG (WhatsApp) e/ou PDF de 1 pagina.
    (11/11) 4 cartoes por linha (por dia util: 3), maiores: a altura cresce
    com o numero de linhas."""
    from PIL import Image, ImageDraw                    # noqa: PLC0415
    import bap_visual as bv                             # noqa: PLC0415
    import parcial_imagem as pi                         # noqa: PLC0415
    s = 1.25
    cs = dados[visao]
    ncol = POR_LINHA.get(visao, 4)
    nlin = max(1, -(-len(cs) // ncol))
    k_esc = 1.2 if ncol == 4 else 1.25          # cartao e letra maiores
    W = int(1920 * s)
    H = int((134 + nlin * 436 * k_esc + (nlin - 1) * 34 + 74) * s)
    pal = {k: _rgb(v) for k, v in bv._PAL.items()}
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    def F(t, peso="normal"):
        return pi.fonte(t, peso, s)

    def P(v):
        return int(round(v * s))

    def txt(x, y, t, f_, cor, anc="la"):
        d.text((x, y), str(t), font=f_, fill=cor, anchor=anc)

    # cabecalho
    txt(P(40), P(26), TITULOS[visao], F(40, "bold"), (17, 17, 17))
    txt(P(42), P(84), dados["sub"][visao], F(17), (95, 104, 98))
    d.rectangle([P(40), P(116), P(1880), P(118)], fill=pal["filete"])
    gx, gy = P(16), P(34)
    x0, y0 = P(40), P(134)
    cw = (W - 2 * x0 - (ncol - 1) * gx) // ncol
    chh = int(P(436) * k_esc)

    def Fk(t, peso="normal"):
        return F(t * k_esc, peso)

    def Pk(v):
        return P(v * k_esc)
    for i, c in enumerate(cs):
        r_, k_ = divmod(i, ncol)
        xc, yc = x0 + k_ * (cw + gx), y0 + r_ * (chh + gy)
        _cartao_pil(d, xc, yc, cw, chh, c, pal, Fk, Pk)
        # (11/11) a borda do cartao, como na tela
        d.rectangle([xc, yc, xc + cw, yc + chh], outline=(143, 156, 147),
                    width=P(2))
    # como ler
    linhas, atual = [], ""
    for w_ in dados["como_ler"].split():
        t_ = (atual + " " + w_).strip()
        if d.textlength(t_, font=F(11)) <= W - 2 * x0:
            atual = t_
        else:
            linhas.append(atual)
            atual = w_
    linhas.append(atual)
    yy = H - P(14) - len(linhas[:3]) * P(15)
    for ln in linhas[:3]:
        txt(x0, yy, ln, F(11), (110, 116, 112))
        yy += P(15)
    if destino_png:
        img.save(destino_png)
    if destino_pdf:
        img.save(destino_pdf, "PDF", resolution=150)
    return img


def _cartao_pil(d, x, y, w, h, c, pal, F, P):
    preto, rot, trilho = pal["faixa"], pal["rotulo"], pal["trilho"]
    num = pal["numero"]
    tons = {"ok": pal["ok"], "atencao": pal["atencao"],
            "alerta": pal["alerta"]}
    tons_b = {"ok": pal["ok_b"], "atencao": pal["atencao_b"],
              "alerta": pal["alerta_b"]}
    d.rectangle([x, y, x + w, y + h], fill=pal["branco"],
                outline=pal["borda"], width=1)
    bh = P(196)
    d.rectangle([x, y, x + w, y + bh], fill=preto)
    d.rectangle([x, y + bh, x + w, y + bh + P(4)], fill=pal["filete"])
    pad = P(18)
    # circulos (da direita para a esquerda)
    dA = P(74)
    an = c.get("aneis") or []
    for i, (lab, p_, sub) in enumerate(reversed(an)):
        ax = x + w - pad - dA - i * (dA + P(10))
        ay = y + P(30)
        cor = tons[tom_de(p_)] if p_ is not None else rot
        d.text((ax + dA / 2, y + P(14)), lab, font=F(10, "bold"), fill=rot,
               anchor="mm")
        d.ellipse([ax, ay, ax + dA, ay + dA], outline=trilho, width=P(8))
        if p_ is not None:
            ext = max(1.0, min(p_, 99.9)) / 100 * 360
            d.arc([ax, ay, ax + dA, ay + dA], start=-90, end=-90 + ext,
                  fill=cor, width=P(8))
            d.text((ax + dA / 2, ay + dA / 2 - P(7)), pc(p_),
                   font=F(14 if p_ < 1000 else 12, "bold"), fill=cor,
                   anchor="mm")
        if sub:
            d.text((ax + dA / 2, ay + dA / 2 + P(13)), sub, font=F(9),
                   fill=rot, anchor="mm")
    larg_t = w - 2 * pad - len(an) * (dA + P(10))
    # rotulo (ate 2 linhas)
    t_ = str(c["titulo"]).upper()
    f_r = F(11, "bold")
    linhas, atual = [], ""
    for w_ in t_.split():
        tt = (atual + " " + w_).strip()
        if d.textlength(tt, font=f_r) <= larg_t:
            atual = tt
        else:
            linhas.append(atual)
            atual = w_
    linhas.append(atual)
    yy = y + P(16)
    for ln in linhas[:2]:
        d.text((x + pad, yy), ln, font=f_r, fill=rot)
        yy += P(15)
    tam = 30 if not an else (26 if len(an) == 1 else 24)
    while tam > 14 and d.textlength(c["valor"], font=F(tam, "bold")) > \
            larg_t:
        tam -= 1
    d.text((x + pad, y + P(54)), c["valor"], font=F(tam, "bold"), fill=num)
    if c.get("legenda"):
        lg = str(c["legenda"])
        if d.textlength(lg, font=F(10)) > larg_t:
            while lg and d.textlength(lg + "…", font=F(10)) > larg_t:
                lg = lg[:-1]
            lg = lg.rstrip() + "…"
        d.text((x + pad, y + P(100)), lg, font=F(10), fill=rot)
    # faixa de comparacao
    fy = y + P(124)
    d.line([x + pad, fy, x + w - pad, fy], fill=trilho, width=1)
    fx = c.get("faixa") or []
    if fx:
        ws = [0.3, 0.3, 0.4]
        cx = x + pad
        for j, (m_, t_v, tm, real) in enumerate(fx[:3]):
            cwj = (w - 2 * pad) * ws[j]
            d.text((cx, fy + P(10)), m_, font=F(10), fill=rot)
            if t_v:
                d.text((cx + d.textlength(m_ + " ", font=F(10)),
                        fy + P(10)), t_v, font=F(10, "bold"),
                       fill=tons.get(tm, rot))
            tr_ = 15
            while tr_ > 9 and d.textlength(real, font=F(tr_, "bold")) > \
                    cwj - P(8):
                tr_ -= 1
            d.text((cx, fy + P(30)), real, font=F(tr_, "bold"),
                   fill=num if real != "—" else rot)
            cx += cwj
    # barras por estado
    est = c.get("estados") or {}
    b = est.get("barras") or []
    if not b:
        return
    top, base = y + bh + P(30), y + h - P(34)
    n = len(b)
    cwb = (w - 2 * pad) / n
    nums = [abs(z[1]) for z in b if z[1]]
    mx = max(nums) if nums else 1
    for i, (uf, v, txt_, rot_, tom) in enumerate(b):
        cx = x + pad + i * cwb + cwb / 2
        if d.textlength(str(txt_), font=F(10, "bold")) > cwb - P(4):
            txt_ = str(txt_).replace("R$ ", "").replace(" mil", "k")
        d.text((cx, base + P(12)), uf, font=F(11, "bold"),
               fill=(43, 47, 51), anchor="mm")
        if v is None:
            continue
        cor_r = tons_b.get(tom, (107, 112, 117))
        if not v or v <= 0:
            d.text((cx, base - P(10)), txt_, font=F(10, "bold"),
                   fill=(17, 17, 17), anchor="mm")
            if rot_:
                d.text((cx, base - P(28)), rot_, font=F(11, "bold"),
                       fill=cor_r, anchor="mm")
            continue
        alt = P(26) + (base - top - P(46)) * abs(v) / mx
        bw = min(P(54), cwb * 0.56)
        d.rounded_rectangle([cx - bw / 2, base - alt, cx + bw / 2, base],
                            radius=P(5), fill=pal["barra"],
                            corners=(True, True, False, False))
        d.text((cx, base - alt - P(10)), txt_, font=F(10, "bold"),
               fill=(17, 17, 17), anchor="mm")
        if rot_:
            d.text((cx, base - alt + P(13)), rot_, font=F(11, "bold"),
                   fill=tons.get(tom, pal["branco"]), anchor="mm")
    if est.get("legenda"):
        d.text((x + w - pad, y + h - P(10)), "● " + est["legenda"],
               font=F(8), fill=(107, 112, 117), anchor="rm")
