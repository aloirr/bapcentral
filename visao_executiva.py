"""
VISAO EXECUTIVA (12/10) - a primeira aba do Painel Executivo: o resumo de
TODOS os farois num placar, cada um com a situacao (bom/atencao/ruim) e o
IMPACTO ESTIMADO NO FATURAMENTO do mes, e o que mais pesa no resultado.

Regras (todas no mes escolhido em cima; vendas com os filtros do Painel):
  META x REAL ....... projecao - desafio
  M3M ............... projecao - media dos 3 meses fechados anteriores
  CLIENTES .......... recorrentes (compraram em 2 dos 3 meses) ainda sem
                      compra no mes: a media mensal deles (em jogo)
  NOVOS/REATIVADOS .. compraram no mes sem compra nos 12 meses anteriores
  VISITAS ........... (visitas - meta no ritmo) x R$ faturado por visita
  EXPOSITORES ....... media mensal da categoria do expositor depois da
                      assinatura - a dos 3 meses antes (por cliente)
  PEDIDOS EM ABERTO . R$ a faturar (VEA); atrasados: mais de 2 dias uteis
  PEDIDOS EXCLUIDOS . R$ excluido no mes (venda perdida)
  GIRO .............. venda perdida em 30 dias pela ruptura
  TICKET E IPP ...... (ticket do mes - ticket M3M) x pedidos do mes
  ENTREGAS .......... R$ das notas atrasadas (e o prazo x resultado por UF)
  DEVOLUCOES ........ R$ devolvido no mes (sai do liquido)
  GARANTIAS ......... R$ em garantia aberta (credito parado no cliente)
  INADIMPLENCIA ..... M3M dos clientes com titulo vencido (compra travada)
  MARGEM E DESCONTO . saldo do teto de 15% de desconto
  INDICADORES EXEC. . pontos do trimestre (sem R$)
Os operacionais (entregas, garantias, inadimplencia, giro, expositores,
visitas, indicadores) sao da BAP inteira.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta


def _rn():
    import relatorios_nucleo as rn                      # noqa: PLC0415
    return rn


def _num(txt):
    """'R$ 1.234' / '53%' / '1.765' -> 1234.0 / 53.0 / 1765.0."""
    m = re.search(r"-?[\d.]+(?:,\d+)?", str(txt or ""))
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def _filho(ctx, ano, mes):
    """Um contexto com o mesmo mes e os mesmos dados ja lidos (sem os
    filtros de venda do Painel: os farois operacionais sao da BAP)."""
    rn = _rn()
    c2 = rn.Contexto(ctx.raiz, hoje=ctx.hoje, log=ctx.log,
                     params={"MÊS": str(mes) if mes else rn.TODOS_MESES,
                             "ANO": str(ano)})
    c2._b = ctx._b                                      # noqa: SLF001
    return c2


def _tab(r, titulo):
    for t in (r or {}).get("tabelas") or []:
        if t.get("titulo") == titulo:
            return t
    return None


def _cols(t):
    return {c["nome"]: i for i, c in enumerate(t["colunas"])}


def _mil(v):
    """R$ curto: R$ 1,2 mi · R$ 35 mil · R$ 820."""
    rn = _rn()
    if v is None:
        return "—"
    s = "−" if v < 0 else "+"
    a = abs(v)
    if a >= 1e6:
        return f"{s}R$ {rn.br(a / 1e6, 1)} mi"
    if a >= 1e4:
        return f"{s}R$ {rn.br(a / 1e3)} mil"
    return f"{s}R$ {rn.br(a)}"


def _cartao(farol, valor, rotulo, tom, detalhe="", impacto=None,
            sentido="", dica="", frase=""):
    return {"farol": farol, "valor": valor, "rotulo": rotulo, "tom": tom,
            "detalhe": detalhe, "impacto": impacto, "sentido": sentido,
            "dica": dica, "frase": frase}


def _sem_dado(farol, motivo="sem dado no mês"):
    return _cartao(farol, "—", motivo, "neutro")


def montar(ctx, b) -> dict:
    """b: o que o Painel ja calculou (ano, mes, real, tend, meta, itens com
    o filtro, fator, du_pass, du_rest, mkp, desc, ac, slim, filtrado)."""
    rn = _rn()
    ano, mes = b["ano"], b["mes"]
    if not mes:
        return {}
    comp = f"{ano}-{mes:02d}"
    m3 = rn._meses_antes(comp, 3)                       # noqa: SLF001
    m12 = rn._meses_antes(comp, 12)                     # noqa: SLF001
    itens = b["itens"]
    hoje = ctx.hoje
    du_tot = (b.get("du_pass") or 0) + (b.get("du_rest") or 0)
    frac = (b["du_pass"] / du_tot) if du_tot and b.get("du_pass") else 1.0
    correndo = bool(b.get("du_rest"))
    real, tend, meta = b["real"], b["tend"], b.get("meta")
    c2 = _filho(ctx, ano, mes)
    cartoes = {}

    # ---- vendas: mes, M3M, clientes, ticket (com o filtro do Painel)
    por_mes = defaultdict(float)
    cli_mes = defaultdict(lambda: defaultdict(float))
    ped_mes = defaultdict(set)
    nf_mes = defaultdict(lambda: defaultdict(set))
    vnd_mes = defaultdict(float)
    dev_mes = defaultdict(float)
    for it in itens:
        if it.get("_ped") or not it["dt_nf"] or it["tipo"] not in ("VND",
                                                                   "DEV"):
            continue
        m = rn.mes_de(it["dt_nf"])
        if m != comp and m not in m12:
            continue
        v = rn._liquido(it)                             # noqa: SLF001
        por_mes[m] += v
        cli_mes[m][it["cliente"]] += v
        if it["tipo"] == "VND":
            ped_mes[m].add((it["filial"], it["pedido"]))
            nf_mes[m][(it["filial"], it["nf"])].add(it["cod"])
            vnd_mes[m] += it["valor"]
        else:
            dev_mes[m] += abs(it["valor"])
    m3m = sum(por_mes[m] for m in m3) / 3.0

    # 1) META x REAL
    if meta:
        at_p = tend / meta * 100.0
        cartoes["meta"] = _cartao(
            "Meta x Real", rn.p(at_p), "ating. projetado",
            "ok" if at_p >= 100 else "atencao" if at_p >= 90 else "alerta",
            f"proj. {_mil(tend)[1:]} de {_mil(meta)[1:]}", tend - meta,
            "vs desafio", "Projeção (real ÷ dias úteis passados × dias "
            "úteis do mês) menos o desafio comercial.",
            f"No ritmo de hoje o mês fecha {_mil(abs(tend - meta))[1:]} "
            f"{'acima' if tend >= meta else 'abaixo'} do desafio.")
    else:
        cartoes["meta"] = _sem_dado("Meta x Real", "sem desafio no mês")

    # 2) M3M
    if m3m:
        var = (tend / m3m - 1) * 100.0
        cartoes["m3m"] = _cartao(
            "M3M · média 3 meses", f"{'+' if var >= 0 else '−'}"
            f"{rn.br(abs(var), 1)}%", "projeção x M3M",
            "ok" if var >= 0 else "atencao" if var >= -10 else "alerta",
            f"M3M {_mil(m3m)[1:]}/mês", tend - m3m, "vs M3M",
            f"Média do faturamento líquido de {', '.join(rn.rotulo_mes(m) for m in m3)}"
            " contra a projeção do mês.",
            f"A projeção está {_mil(abs(tend - m3m))[1:]} "
            f"{'acima' if tend >= m3m else 'abaixo'} da média dos 3 meses.")
    else:
        cartoes["m3m"] = _sem_dado("M3M · média 3 meses")

    # 3) CLIENTES: positivacao x M3M e os recorrentes sem compra
    pos = {c for c, v in cli_mes[comp].items() if v > 0}
    pos_m3 = sum(len([c for c, v in cli_mes[m].items() if v > 0])
                 for m in m3) / 3.0
    freq = defaultdict(int)
    med = defaultdict(float)
    for m in m3:
        for c, v in cli_mes[m].items():
            if v > 0:
                freq[c] += 1
                med[c] += v / 3.0
    recorr = [c for c, n in freq.items() if n >= 2 and c not in pos]
    em_jogo = sum(med[c] for c in recorr)
    ritmo = (len(pos) / (pos_m3 * frac) * 100.0) if pos_m3 else None
    cartoes["clientes"] = _cartao(
        "Clientes", rn.br(len(pos)), "positivados",
        "neutro" if ritmo is None else "ok" if ritmo >= 100
        else "atencao" if ritmo >= 85 else "alerta",
        f"M3M {rn.br(pos_m3)}/mês · {rn.br(len(recorr))} recorrentes sem compra",
        -em_jogo if em_jogo else None,
        "em jogo" if correndo else "perdido",
        "Recorrentes = compraram em pelo menos 2 dos 3 meses anteriores. "
        "Impacto: a média mensal dos que ainda não compraram no mês.",
        f"{rn.br(len(recorr))} clientes recorrentes ainda não compraram: "
        f"{_mil(em_jogo)[1:]}/mês {'em jogo' if correndo else 'que não veio'}.")

    # 4) NOVOS E REATIVADOS
    antes = set()
    for m in m12:
        antes |= {c for c, v in cli_mes[m].items() if v > 0}
    novos = [c for c in pos if c not in antes]
    v_novos = sum(cli_mes[comp][c] for c in novos)
    tot_g = ((b.get("ac") or {}).get("totais") or {}).get("gerente") or {}
    mc, rc = tot_g.get("meta_cadastro"), tot_g.get("cadastros_com_compra")
    cartoes["novos"] = _cartao(
        "Novos e reativados", rn.br(len(novos)), "sem compra em 12 meses",
        "ok" if novos else "atencao",
        (f"cad. com compra {rn.br(rc)} de {rn.br(mc)}" if mc else ""),
        v_novos or None, "no faturamento",
        "Clientes que compraram no mês e não tinham compra nos 12 meses "
        "anteriores (novos ou reativados).",
        f"{rn.br(len(novos))} clientes novos/reativados trouxeram "
        f"{_mil(v_novos)[1:]}.")

    # 5) VISITAS (Farol de Metas: o GridRca do mes x a meta de visita)
    vis, mv = tot_g.get("visitas_realizadas"), tot_g.get("meta_visita")
    if vis is not None and mv:
        esp = mv * frac
        r_vis = real / vis if vis else 0.0
        at_v = vis / esp * 100.0 if esp else None
        cartoes["visitas"] = _cartao(
            "Visitas", rn.br(vis), f"de {rn.br(mv)} no mês",
            "ok" if (at_v or 0) >= 100 else "atencao" if (at_v or 0) >= 80
            else "alerta", f"{rn.p(at_v)} do ritmo · {_mil(r_vis)[1:]}/visita",
            (vis - esp) * r_vis if r_vis else None, "estimado",
            "Visitas (Máxima) contra a meta no ritmo dos dias úteis; impacto "
            "= visitas a mais/menos × faturamento por visita.",
            f"Visitas em {rn.p(at_v)} do ritmo da meta: "
            f"{_mil((vis - esp) * r_vis)} estimados no faturamento.")
    else:
        cartoes["visitas"] = _sem_dado("Visitas", "sem meta de visita")

    # 6) EXPOSITORES: a categoria do expositor antes x depois
    cartoes["expositores"] = _expositores(ctx, c2, rn)

    # 7) PEDIDOS EM ABERTO e 8) EXCLUIDOS (da BAP no filtro de venda)
    abertos = [it for it in itens if it["tipo"] == "VEA"]
    peds = defaultdict(list)
    for it in abertos:
        peds[(it["filial"], it["pedido"])].append(it)
    v_ab = sum(it["valor"] for it in abertos)
    atras = 0
    for its in peds.values():
        prazo = ctx.mais_uteis(its[0]["dt_pedido"], rn.bd.PRAZO_FATURAR)
        if prazo and hoje > prazo:
            atras += 1
    cartoes["abertos"] = _cartao(
        "Pedidos em aberto", _mil(v_ab)[1:], f"{rn.br(len(peds))} pedidos",
        "ok" if not atras else "atencao" if atras <= 2 else "alerta",
        f"{rn.br(atras)} atrasados (+{rn.bd.PRAZO_FATURAR} dias úteis)",
        v_ab or None, "a faturar",
        "Pedidos digitados e ainda sem nota (VEA). Atrasado: passou do "
        "prazo de faturar.",
        f"{_mil(v_ab)[1:]} em {rn.br(len(peds))} pedidos esperando nota "
        f"({rn.br(atras)} atrasados).")
    exc = [it for it in itens if it["tipo"] == "EXC" and it.get("dt_pedido")
           and rn.mes_de(it["dt_pedido"]) == comp]
    v_exc = sum(it["valor"] for it in exc)
    n_exc = len({(it["filial"], it["pedido"]) for it in exc})
    base_ped = v_exc + vnd_mes[comp] + v_ab
    pct_exc = v_exc / base_ped * 100.0 if base_ped else 0.0
    cartoes["excluidos"] = _cartao(
        "Pedidos excluídos", _mil(v_exc)[1:], f"{rn.br(n_exc)} pedidos",
        "ok" if pct_exc <= 5 else "atencao" if pct_exc <= 15 else "alerta",
        f"{rn.br(pct_exc, 1)}% do que foi pedido", -v_exc if v_exc else None,
        "venda perdida", "Pedidos do mês excluídos (EXC): venda que não "
        "virou nota.",
        f"{rn.br(n_exc)} pedidos excluídos: {_mil(v_exc)[1:]} de venda perdida.")

    # 9) GIRO (ruptura e curva A parada)
    cartoes["giro"] = _giro(c2, rn, tend)

    # 10) TICKET e IPP x M3M
    n_ped = len(ped_mes[comp])
    tk = vnd_mes[comp] / n_ped if n_ped else None
    n_p3 = sum(len(ped_mes[m]) for m in m3)
    tk3 = sum(vnd_mes[m] for m in m3) / n_p3 if n_p3 else None
    nfs = nf_mes[comp]
    ipp = (sum(len(v) for v in nfs.values()) / len(nfs)) if nfs else None
    if tk and tk3:
        d_tk = (tk / tk3 - 1) * 100.0
        cartoes["ticket"] = _cartao(
            "Ticket e IPP", _mil(tk)[1:], "por pedido",
            "ok" if d_tk >= 0 else "atencao" if d_tk >= -10 else "alerta",
            f"M3M {_mil(tk3)[1:]} · {rn.br(ipp or 0, 1)} SKU/nota",
            (tk - tk3) * n_ped, "vs M3M",
            "Ticket médio por pedido do mês contra o dos 3 meses anteriores, "
            "vezes os pedidos do mês.",
            f"Ticket por pedido {'+' if d_tk >= 0 else '−'}"
            f"{rn.br(abs(d_tk), 1)}% vs M3M: "
            f"{_mil((tk - tk3) * n_ped)} no faturamento.")
    else:
        cartoes["ticket"] = _sem_dado("Ticket e IPP")

    # 11) ENTREGAS (e o prazo x resultado por UF)
    ent, por_uf_ent = _entregas(c2, rn, comp)
    cartoes["entregas"] = ent

    # 12) DEVOLUCOES
    v_dev = dev_mes[comp]
    pct_dev = v_dev / vnd_mes[comp] * 100.0 if vnd_mes[comp] else 0.0
    cartoes["devolucoes"] = _cartao(
        "Devoluções", _mil(v_dev)[1:], f"{rn.br(pct_dev, 1)}% do faturado",
        "ok" if pct_dev <= 2 else "atencao" if pct_dev <= 4 else "alerta",
        "sai do faturamento líquido", -v_dev if v_dev else None,
        "no faturamento", "Notas de devolução do mês (já descontadas do "
        "real).", f"Devoluções tiraram {_mil(v_dev)[1:]} do faturamento "
        f"({rn.br(pct_dev, 1)}%).")

    # 13) GARANTIAS
    cartoes["garantias"] = _garantias(c2, rn, hoje)

    # 14) INADIMPLENCIA
    cartoes["inadimplencia"] = _inadimplencia(c2, rn, cli_mes, m3)

    # 15) MARGEM E DESCONTO
    vnd = [it for it in itens if it["tipo"] == "VND" and it["dt_nf"]
           and rn.mes_de(it["dt_nf"]) == comp and not it.get("_ped")]
    tab_ = sum((it["p_tab"] * it["qtd"]) if it["p_tab"] > 0 else it["valor"]
               for it in vnd)
    # (13/10) o saldo do Farol de Saldo: o financeiro da condicao fora e
    # acima do teto so o autorizado pelo Alexandre
    saldo = sum(rn.saldo_do_item(ctx, it) for it in vnd) if tab_ else None
    sem_aut = {(it["filial"], it["pedido"] or it["nf"]) for it in vnd
               if (rn.saldos_dos_pedidos(ctx).get(
                   (it["filial"], it["pedido"] or it["nf"])) or {}).get(
                       "grave")}
    mkp, desc = b.get("mkp"), b.get("desc")
    cartoes["margem"] = _cartao(
        "Margem e desconto", "—" if mkp is None else f"{rn.br(mkp, 1)}%",
        "markup", "neutro" if saldo is None else "alerta" if sem_aut
        else "ok" if saldo >= 0 else "atencao",
        (f"{rn.br(len(sem_aut))} acima de 15% sem autorização" if sem_aut
         else f"desconto {rn.p(desc)} · teto {rn.br(rn.TETO_DESCONTO)}%"),
        saldo, "saldo do teto",
        "Saldo do Farol de Saldo: o financeiro da condição de pagamento "
        "fica fora; acima de 15% desconta, menos o autorizado pelo Price.",
        f"Desconto comercial {rn.p(desc)}: saldo de {_mil(saldo)} no teto de 15%."
        if saldo is not None else "")

    # 16) INDICADORES EXECUTIVOS
    cartoes["executivos"] = _executivos(c2, rn)

    # ---- o que mais pesa e os graficos
    ordem = ["meta", "m3m", "margem", "executivos",
             "clientes", "novos", "visitas", "expositores",
             "abertos", "excluidos", "giro", "ticket",
             "entregas", "devolucoes", "garantias", "inadimplencia"]
    lista = [cartoes[k] for k in ordem if k in cartoes]
    com_imp = [c for c in lista if c.get("impacto") and c["farol"] not in
               ("Meta x Real", "M3M · média 3 meses")]
    com_imp.sort(key=lambda c: -abs(c["impacto"]))
    insights = []
    for c in lista[:2]:
        if c.get("frase"):
            insights.append((c["tom"] if c["tom"] != "neutro" else "info",
                             c["frase"]))
    for c in com_imp[:3]:
        if c.get("frase"):
            insights.append(("ok" if c["impacto"] > 0 else "alerta",
                             c["frase"]))
    extra = _visitas_x_resultado(b, rn)
    if extra:
        insights.append(extra[0])
    ins_uf = _frase_entrega_uf(por_uf_ent, b, rn, ctx)
    if ins_uf:
        insights.append(ins_uf[0])
    hb = {"titulo": "Impacto estimado no faturamento do mês",
          "rotulos": [c["farol"] for c in com_imp],
          "valores": [c["impacto"] for c in com_imp],
          "cores": ["#59BA61" if c["impacto"] > 0 else "#B42318"
                    for c in com_imp], "formato": "moeda"}
    graficos = []
    if ins_uf and ins_uf[1]:
        graficos.append(ins_uf[1])
    if extra and extra[1]:
        graficos.append(extra[1])
    return {"cartoes": lista, "insights": insights, "hbarras": hb,
            "graficos": graficos, "filtrado": b.get("filtrado")}


# =========================================================================
def _expositores(ctx, c2, rn):
    farol = "Expositores"
    fator = rn._fator_do_mes(ctx, ctx.hoje.year,                # noqa: SLF001
                             ctx.hoje.month)[0]
    try:
        r = rn.farol_expositores(_filho(ctx, ctx.hoje.year, 0))
    except Exception:                                   # noqa: BLE001
        return _sem_dado(farol)
    t = _tab(r, "Expositores")
    if not t or not t["linhas"]:
        return _sem_dado(farol, "nenhum expositor")
    j = _cols(t)
    ok_st = ("Entregue", "Contrato assinado")
    inst = [l for l in t["linhas"] if l[j["STATUS"]] in ok_st]
    if not inst:
        return _cartao(farol, "0", "instalados", "neutro",
                       f"{rn.br(len(t['linhas']))} no acompanhamento")
    clientes = ctx.tabela.get("clientes") or {}
    por_nome = {}
    for cod, c in clientes.items():
        for n in (c.get("nome"), c.get("fantasia")):
            k = _chave_nome(n)
            if k:
                por_nome.setdefault(k, cod)
    # (15/10) a CATEGORIA do Catalogo BAP 2026 (ctx.categoria_bap); o
    # expositor de lubrificante leva junto os quimicos (aditivos, fluidos)
    cat_map = {"BATERIAS": {"BATERIAS"}, "PNEUS": {"PNEUS"},
               "LUBRIFICANTES": {"LUBRIFICANTES", "QUÍMICOS"},
               "PEÇAS": set(rn.LINHAS_PECAS), "PECAS": set(rn.LINHAS_PECAS)}
    corre = rn.mes_de(ctx.hoje)
    vend = defaultdict(lambda: defaultdict(float))
    for it in ctx.tabela["itens"]:
        # (06/11) a nota de hoje fica fora (o mes corrente e projetado)
        if it["tipo"] == "VND" and it["dt_nf"] and \
                not rn._de_hoje(ctx, it):               # noqa: SLF001
            vend[it["cliente"]][(rn.mes_de(it["dt_nf"]),
                                 ctx.categoria_bap(it["cod"]))] += it["valor"]
    delta, casados, sem = 0.0, 0, 0
    vistos = set()
    for l in inst:
        cod = rn.texto(l[j["CÓD. CLIENTE"]])
        cod = cod.zfill(6) if cod.isdigit() else ""
        if not cod:
            for parte in str(l[j["CLIENTE"]] or "").split("/"):
                cod = por_nome.get(_chave_nome(parte)) or ""
                if cod:
                    break
        d0 = l[j["ASSINATURA"]] or l[j["SOLICITAÇÃO"]]
        if not cod or not d0:
            sem += 1
            continue
        cat = cat_map.get(rn.texto(l[j["CATEGORIA"]]).upper())
        k = (cod, tuple(sorted(cat)) if cat else None)
        if k in vistos:
            continue
        vistos.add(k)
        m0 = rn.mes_de(d0)
        # ANTES: os 3 meses antes da SOLICITACAO (a compra de abastecimento
        # do expositor, entre a solicitacao e a assinatura, fica fora)
        antes = rn._meses_antes(rn.mes_de(l[j["SOLICITAÇÃO"]] or d0), 3)  # noqa: SLF001
        depois = []                  # os meses DEPOIS da assinatura (o da
        a, mm = int(m0[:4]), int(m0[5:])    # assinatura e parcial); o que
        m = f"{a + (mm == 12)}-{mm % 12 + 1:02d}"   # corre: projetado
        while m <= corre and len(depois) < 6:
            depois.append(m)
            a, mm = int(m[:4]), int(m[5:])
            m = f"{a + (mm == 12)}-{mm % 12 + 1:02d}"
        if not depois:
            continue                 # assinou este mes: mede no proximo
        casados += 1

        def soma(ms, fat=1.0):
            return sum(v * (fat if mx == corre else 1.0)
                       for (mx, cx), v in vend[cod].items()
                       if mx in ms and (cat is None or cx in cat))
        delta += soma(depois, fator) / len(depois) - soma(antes) / 3.0
    tom = "neutro" if not casados else "ok" if delta >= 0 else "alerta"
    return _cartao(
        farol, rn.br(len(inst)), "instalados", tom,
        (f"{rn.br(casados)} medidos" + (f" · {rn.br(sem)} sem código"
                                        if sem else "")),
        delta if casados else None, "por mês",
        "Por cliente com expositor entregue ou contrato assinado: média "
        "mensal da categoria do expositor nos meses depois da assinatura (o "
        "mês corrente projetado) menos a dos 3 meses antes da solicitação. "
        "Sem CÓD. CLIENTE, casa pelo nome.",
        (f"Clientes com expositor: {_mil(delta)}/mês na categoria do "
         "expositor desde a assinatura." if casados else ""))


def _chave_nome(n):
    rn = _rn()
    s = rn.sem_acento(str(n or "")).upper()
    s = re.sub(r"\b(LTDA|ME|EPP|EIRELI|S/?A|MEI)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(s.split())


def _giro(c2, rn, tend):
    """(16/10) O Farol de Giro e em unidades; o R$ e a VENDA PERDIDA
    PREVISTA: dias sem estoque ate a compra chegar (45 dias) x a venda
    media por dia, dos itens com menos de 45 dias de cobertura."""
    farol = "Giro de produtos"
    try:
        r = rn.giro_produtos(c2)
    except Exception:                                   # noqa: BLE001
        return _sem_dado(farol)
    rup = _tab(r, "Ruptura")
    par = _tab(r, "Curva A parada")
    cmp_ = _tab(r, "Necessidade de compra")
    perda = 0.0
    n_rup = len(rup["linhas"]) if rup else 0
    if cmp_ and cmp_["linhas"]:
        j = _cols(cmp_)
        perda = sum((l[j["VENDA PERDIDA"]] or 0) for l in cmp_["linhas"])
    un_par = 0.0
    if par and par["linhas"]:
        j = _cols(par)
        un_par = sum((l[j["EST."]] or 0) for l in par["linhas"])
    prazo = rn.GIRO_PRAZO_CHEGADA
    pct = perda / tend * 100.0 if tend else 0.0
    return _cartao(
        farol, rn.br(n_rup), "itens em ruptura",
        "ok" if not perda else "atencao" if pct <= 3 else "alerta",
        f"curva A parada {rn.br(un_par)} un.", -perda if perda else None,
        f"até a compra chegar ({prazo} dias)",
        f"Venda perdida prevista = dias sem estoque até a compra chegar "
        f"({prazo} dias − cobertura) × venda média por dia (Farol de Giro).",
        (f"{_mil(perda)[1:]} de venda perdida prevista nos itens com menos "
         f"de {prazo} dias de estoque ({rn.br(n_rup)} já em ruptura)."
         if perda else ""))


def _entregas(c2, rn, comp):
    farol = "Entregas"
    try:
        r = rn.entregas(c2)
    except Exception:                                   # noqa: BLE001
        return _sem_dado(farol), {}
    t = _tab(r, "Entregas")
    if not t:
        return _sem_dado(farol), {}
    j = _cols(t)
    rot = rn.rotulo_mes(comp)
    ls = [l for l in t["linhas"] if l[j["MÊS"]] == rot]
    if not ls:
        return _sem_dado(farol), {}
    atr = [l for l in ls if l[j["SITUAÇÃO"]] in ("ATRASADA",
                                                 "ENTREGUE COM ATRASO")]
    no_p = [l for l in ls if l[j["SITUAÇÃO"]] == "NO PRAZO"]
    julg = len(atr) + len(no_p)
    pct = len(no_p) / julg * 100.0 if julg else None
    slas = [l[j["SLA"]] for l in ls
            if isinstance(l[j["SLA"]], (int, float))]
    v_atr = sum((l[j["VLR NF"]] or 0) for l in atr
                if l[j["SITUAÇÃO"]] == "ATRASADA")
    por_uf = defaultdict(lambda: {"n": 0, "prazo": 0, "julg": 0, "sla": []})
    for l in ls:
        x = por_uf[rn.texto(l[j["UF"]]) or "?"]
        x["n"] += 1
        if l[j["SITUAÇÃO"]] == "NO PRAZO":
            x["prazo"] += 1
            x["julg"] += 1
        elif l in atr:
            x["julg"] += 1
        if isinstance(l[j["SLA"]], (int, float)):
            x["sla"].append(l[j["SLA"]])
    sla_m = sum(slas) / len(slas) if slas else None
    return _cartao(
        farol, rn.p(pct) if pct is not None else "—", "no prazo",
        "neutro" if pct is None else "ok" if pct >= rn.META_PRAZO
        else "atencao" if pct >= 75 else "alerta",
        (f"SLA médio {rn.br(sla_m, 1)} dias · " if sla_m is not None else "")
        + f"{rn.br(len(atr))} atrasadas", -v_atr if v_atr else None,
        "atrasado", "Notas do mês no Farol de Entregas: % no prazo e o R$ "
        "das que estão atrasadas.",
        (f"{rn.br(len(atr))} entregas atrasadas ({_mil(v_atr)[1:]})."
         if atr else f"Entregas {rn.p(pct)} no prazo.")), dict(por_uf)


def _frase_entrega_uf(por_uf, b, rn, ctx):
    """O prazo de entrega x o resultado de cada UF: a UF que entrega mais
    rapido vende melhor? (ating. projetado da UF pela carteira)."""
    if not por_uf:
        return None
    ac = b.get("ac") or {}
    meta_uf = defaultdict(float)
    for c in b.get("slim") or []:
        meta_uf[rn.texto(c.get("uf")).upper()] += c.get("meta") or 0.0
    real_uf = defaultdict(float)
    for it in b.get("no_periodo") or []:
        uf = rn.territorio_do_cliente(ctx, it["cliente"], "uf")
        real_uf[uf] += ((rn._liquido(it) or 0.0)       # noqa: SLF001
                        - rn._de_hoje(ctx, it))         # noqa: SLF001
    _ = ac
    linhas = []
    for uf, x in por_uf.items():
        if not meta_uf.get(uf):
            continue
        sla = sum(x["sla"]) / len(x["sla"]) if x["sla"] else None
        at = real_uf[uf] * b["fator"] / meta_uf[uf] * 100.0
        pz = x["prazo"] / x["julg"] * 100.0 if x["julg"] else None
        linhas.append((uf, sla, pz, at))
    if not linhas:
        return None
    linhas.sort(key=lambda l: (l[1] is None, l[1] or 0))
    g = {"titulo": "Entrega x resultado por UF · da mais rápida para a "
                   "mais lenta", "rotulos": [l[0] for l in linhas],
         "series": [{"nome": "% ating. proj.", "cor": "#59BA61",
                     "valores": [l[3] for l in linhas]}],
         "formato": "pct", "rotular": True,
         "subrotulos": [f"SLA {rn.br(l[1], 1)} d" if l[1] is not None
                        else "SLA —" for l in linhas]}
    com = [l for l in linhas if l[1] is not None]
    if len(com) < 2:
        return ("info", "Entrega x resultado: poucas UFs com entrega no mês "
                "para comparar."), g
    rap, len_ = com[: len(com) // 2 or 1], com[len(com) // 2 or 1:]

    def med(ls_):
        return sum(l[3] for l in ls_) / len(ls_)
    a, z = med(rap), med(len_)
    tom = "ok" if a >= z else "atencao"
    return (tom, f"UFs que entregam mais rápido ({', '.join(l[0] for l in rap)}"
                 f") projetam {rn.p(a)} do desafio; as mais lentas "
                 f"({', '.join(l[0] for l in len_)}) {rn.p(z)}."), g


def _visitas_x_resultado(b, rn):
    """Quem visita mais fatura mais? Vendedores acima e abaixo da mediana
    de % da meta de visita x % da meta de faturamento."""
    ac = b.get("ac") or {}
    ls = [l for l in (ac.get("recortes") or {}).get("vendedor") or []
          if l.get("meta_visita") and l.get("meta")]
    if len(ls) < 3:
        return None
    pts = sorted(((l.get("rotulo") or l.get("nome") or l.get("chave"),
                   (l.get("visitas_realizadas") or 0) / l["meta_visita"]
                   * 100.0, (l.get("realizado") or 0) / l["meta"] * 100.0)
                  for l in ls), key=lambda x: -x[1])
    meio = len(pts) // 2
    hi, lo = pts[:meio], pts[meio:]

    def med(xs):
        return sum(x[2] for x in xs) / len(xs) if xs else 0.0
    a, z = med(hi), med(lo)
    g = {"titulo": "Visitas x faturamento por vendedor · % da meta",
         "rotulos": [_curto(x[0]) for x in pts],
         "series": [{"nome": "visitas", "cor": "#B9DEAB",
                     "valores": [x[1] for x in pts]},
                    {"nome": "faturamento", "cor": "#59BA61",
                     "valores": [x[2] for x in pts]}],
         "formato": "pct", "rotular": True}
    return (("ok" if a >= z else "atencao"),
            f"Quem mais cumpre a meta de visita já faturou {rn.p(a)} da "
            f"meta; quem menos visita, {rn.p(z)}."), g


def _curto(nome):
    s = str(nome or "")
    if " - " in s:
        s = s.split(" - ", 1)[1]
    p = s.split()
    return " ".join(p[:2]) if p else s


def _garantias(c2, rn, hoje):
    farol = "Garantias"
    try:
        r = rn.garantias(c2)
    except Exception:                                   # noqa: BLE001
        return _sem_dado(farol)
    t = _tab(r, "Garantias")
    if not t:
        return _sem_dado(farol)
    j = _cols(t)
    # (14/10) o farol novo: STATUS e PRAZO (30 dias da solicitacao)
    ab = [l for l in t["linhas"]
          if rn.texto(l[j["STATUS"]]).upper() not in ("FINALIZADA",
                                                      "CANCELADA")]
    velhas = sum(1 for l in ab if l[j["PRAZO"]] == "ATRASADA")
    proc = sum(1 for l in t["linhas"] if l[j["RESULTADO ANÁLISE"]]
               == "PROCEDENTE")
    return _cartao(
        farol, rn.br(len(ab)), "em aberto",
        "ok" if not ab else "atencao" if not velhas else "alerta",
        f"{rn.br(velhas)} com mais de 30 dias", None,
        "sem valor", "Garantias em aberto no Farol de Garantias (prazo de "
        "30 dias da solicitação).",
        (f"{rn.br(len(ab))} garantias em aberto ({rn.br(velhas)} atrasadas)"
         f"; {rn.br(proc)} procedentes." if ab else ""))


def _inadimplencia(c2, rn, cli_mes, m3):
    farol = "Inadimplência"
    try:
        r = rn.farol_inadimplencia(c2)
    except Exception:                                   # noqa: BLE001
        return _sem_dado(farol)
    t = _tab(r, "Por cliente")
    k = {x.get("rotulo"): x for x in r.get("kpis") or []}
    v_atr = _num((k.get("Em atraso") or {}).get("valor")) or 0.0
    pct = _num((k.get("Inadimplência") or {}).get("valor"))
    clis = set()
    if t:
        j = _cols(t)
        for l in t["linhas"]:
            if (l[j["EM ATRASO"]] or 0) > 0:
                cod = rn.texto(l[j["CLIENTE"]]).split(" ")[0].split("-")[0]
                clis.add(cod.zfill(6) if cod.isdigit() else cod)
    trav = sum(sum(cli_mes[m].get(c, 0.0) for m in m3) / 3.0 for c in clis)
    return _cartao(
        farol, _mil(v_atr)[1:], "em atraso",
        "neutro" if pct is None else "ok" if pct <= 5 else "atencao"
        if pct <= 15 else "alerta",
        f"{rn.p(pct)} da carteira · {rn.br(len(clis))} clientes",
        -trav if trav else None, "M3M travado",
        "Clientes com título vencido tendem a ficar sem limite: o impacto é "
        "a média mensal de compra deles (M3M).",
        (f"{rn.br(len(clis))} clientes inadimplentes compravam "
         f"{_mil(trav)[1:]}/mês." if trav else ""))


def _executivos(c2, rn):
    farol = "Indicadores executivos"
    try:
        r = rn.indicadores_executivos(c2)
    except Exception:                                   # noqa: BLE001
        return _sem_dado(farol)
    k = {x.get("rotulo"): x for x in r.get("kpis") or []}
    x = k.get("Resultado do tri")
    if not x:
        return _sem_dado(farol)
    v = _num(x.get("valor"))
    fat = k.get("Faturamento total") or {}
    return _cartao(
        farol, x.get("valor"), "pontos do trimestre",
        "neutro" if v is None else "ok" if v >= 90 else "atencao"
        if v >= 70 else "alerta", (f"faturamento {fat.get('valor')}"
                                   if fat else x.get("detalhe") or ""),
        None, "", "Farol Indicadores Executivos: pontos do trimestre "
        "(faturamento, positivação, despesas, peças, cadastro).")
