"""
RESUMO GERENCIAL PADRAO DOS FAROIS (06/10)

O mesmo desenho do Farol de Visita e do Farol Roteirizacao, para todos os
faróis que ainda tinham a capa antiga (3 graficos de um indicador so):

    +-----------------+---------------------------------------------+
    | O QUE O FAROL   | indicador 1 · dia a dia (mes escolhido)     |
    | DIZ (insights,  +----------------------+----------------------+
    | do mais grave   | ind. 1 · semana a    | ind. 1 · mes a mes   |
    | ao informativo) | semana               | (ultimos 12 meses)   |
    +-----------------+----------------------+----------------------+
    | ind. 2 · dia    | ind. 2 · semana      | ind. 2 · mes a mes   |
    | ind. 3 · dia    | ind. 3 · semana      | ind. 3 · mes a mes   |
    +-----------------+----------------------+----------------------+
    | os graficos proprios do farol e os rankings (3 por linha)     |
    +---------------------------------------------------------------+

Cada farol diz SO o que e dele (painel_farol.PAINEIS no relatorios_nucleo):
os indicadores (eventos [(data, valor...)] + como juntar), os rankings e
os insights do negocio. O resto - as series, a comparacao com o mes
anterior no mesmo ponto do mes, a projecao, o melhor mes, os cartoes em
alerta - sai daqui, igual para todos.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

VERDE, CINZA, VERMELHO, AZUL, AMARELO = ("#59BA61", "#A7B0AA", "#B42318",
                                         "#2F6FB0", "#B7791F")
MESES = ["", "JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET",
         "OUT", "NOV", "DEZ"]
ORDEM_TOM = {"alerta": 0, "atencao": 1, "ok": 2, "info": 3}
MAX_INSIGHTS = 9


def _br(v, casas=0):
    from bap_visual import br                           # noqa: PLC0415
    return br(v, casas)


def _moeda(v):
    from bap_visual import moeda                        # noqa: PLC0415
    return moeda(v)


def fmt(v, formato):
    """O valor do jeito do indicador (texto do insight)."""
    if v is None:
        return "—"
    if formato == "moeda":
        return _moeda(v)
    if formato in ("pct", "pct1"):
        return f"{_br(v, 1)}%"
    if formato == "dias":
        return f"{_br(v, 1)} dia(s)"
    if isinstance(v, float) and abs(v) < 100 and v % 1:
        return _br(v, 1)
    return _br(v)


def ind(nome, eventos, agg="soma", formato="num", cor=VERDE, bom="alto",
        meta_dia=None, projetar=True):
    """Um indicador do painel.
    eventos: [(data, valor...)]; agg: "soma" | "conta" | "unicos" (conta
    o 1o valor distinto) | "media" | "pct" (soma do 1o / soma do 2o, x100)
    | funcao(lista de tuplas sem a data). bom: "alto" | "baixo" | None
    (so informa). meta_dia: a linha tracejada do dia a dia."""
    return {"nome": nome, "eventos": eventos, "agg": agg, "formato": formato,
            "cor": cor, "bom": bom, "meta_dia": meta_dia,
            "projetar": projetar}


def pct_do_liquido(parte, liquido):
    """RN-GER-002: o percentual sobre o faturado LIQUIDO (VND - DEV). Faturado
    liquido <= 0 nao da percentual (None, "—"): nunca negativo ou absurdo."""
    return parte / liquido * 100.0 if liquido and liquido > 0 else None


def _juntar(vals, agg):
    if not vals:
        return None
    if callable(agg):
        return agg(vals)
    if agg == "conta":
        return len(vals)
    if agg == "unicos":
        return len({v[0] for v in vals})
    if agg == "media":
        xs = [v[0] for v in vals if v[0] is not None]
        return sum(xs) / len(xs) if xs else None
    if agg == "pct":
        num = sum(v[0] or 0 for v in vals)
        den = sum(v[1] or 0 for v in vals)
        return pct_do_liquido(num, den)
    return sum(v[0] or 0 for v in vals)


def _dia(d):
    if isinstance(d, datetime):
        return d.date()
    return d if isinstance(d, date) else None


def _meses_ate(ano, mes, n=12):
    saida, a, m = [], ano, mes
    for _ in range(n):
        saida.insert(0, (a, m))
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return saida


def mes_de_referencia(ctx, ano, mes):
    """O mes do dia a dia e da semana a semana: o escolhido; em TODOS OS
    MESES, o mes atual (ano corrente) ou dezembro (ano passado)."""
    if mes:
        return mes
    return ctx.hoje.month if ano == ctx.hoje.year else 12


def series(ctx, ind_, ano, mes):
    """{dia: (rotulos, valores, cores), semana: (...), mes: (...)}"""
    ndias = calendar.monthrange(ano, mes)[1]
    por_dia, por_mes = defaultdict(list), defaultdict(list)
    meses12 = _meses_ate(ano, mes)
    janela = set(meses12)
    for ev in ind_["eventos"]:
        d = _dia(ev[0])
        if not d:
            continue
        if (d.year, d.month) in janela:
            por_mes[(d.year, d.month)].append(ev[1:])
        if d.year == ano and d.month == mes:
            por_dia[d.day].append(ev[1:])
    agg = ind_["agg"]

    def val(xs):
        v = _juntar(xs, agg)
        return 0 if v is None else round(v, 2)
    dias = list(range(1, ndias + 1))
    fer = getattr(ctx, "fer", set()) or set()
    cores = [ind_["cor"] if date(ano, mes, d).weekday() < 5
             and date(ano, mes, d) not in fer else CINZA for d in dias]
    semanas = []
    for d in dias:
        if not semanas or date(ano, mes, d).weekday() == 0:
            semanas.append((f"{d:02d}/{mes:02d}", []))
        semanas[-1][1].append(d)
    return {
        "dia": ([str(d) for d in dias], [val(por_dia[d]) for d in dias],
                cores),
        "semana": ([s[0] for s in semanas],
                   [val(sum((por_dia[d] for d in s[1]), [])) for s in semanas]),
        "mes": ([MESES[m] for a, m in meses12],
                [val(por_mes[k]) for k in meses12], meses12),
        "por_dia": por_dia, "por_mes": por_mes,
    }


def _no_intervalo(eventos, de, ate):
    return [ev[1:] for ev in eventos
            if _dia(ev[0]) and de <= _dia(ev[0]) <= ate]


def _tom_var(var, bom):
    if var is None or not bom:
        return "info"
    melhor = var if bom == "alto" else -var
    if melhor >= 5:
        return "ok"
    if melhor <= -25:
        return "alerta"
    if melhor <= -10:
        return "atencao"
    return "info"


def insights_do_indicador(ctx, ind_, ano, mes, s, principal=False):
    """O mes (ate hoje) contra o mes anterior NO MESMO PONTO do mes, a
    projecao (soma/conta no mes corrente) e, no indicador principal, o
    melhor mes dos ultimos 12."""
    hoje = ctx.hoje
    ini = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    corrente = ini <= hoje <= fim
    ate = hoje if corrente else fim
    a_ant, m_ant = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    ini_a = date(a_ant, m_ant, 1)
    fim_a = date(a_ant, m_ant, calendar.monthrange(a_ant, m_ant)[1])
    ate_a = min(fim_a, ini_a + timedelta(days=(ate - ini).days)) \
        if corrente else fim_a
    agg, f_ = ind_["agg"], ind_["formato"]
    atual = _juntar(_no_intervalo(ind_["eventos"], ini, ate), agg)
    ant = _juntar(_no_intervalo(ind_["eventos"], ini_a, ate_a), agg)
    saida = []
    if atual is None and ant is None:
        return saida
    if atual is None and agg in ("soma", "conta", "unicos"):
        atual = 0                       # sem movimento = zero
    # a variacao so faz sentido com a base positiva (saldo negativo: so o
    # valor do mes anterior)
    var = ((atual or 0) / ant - 1) * 100.0 if ant and ant > 0 else None
    quando = (f"em {MESES[mes]} até {ate:%d/%m}" if corrente
              else f"em {MESES[mes]}/{str(ano)[2:]}")
    txt = f"{ind_['nome']}: {fmt(atual, f_)} {quando}"
    if ant is not None:
        txt += (f"; {MESES[m_ant]}" + (" no mesmo ponto" if corrente else "")
                + f": {fmt(ant, f_)}"
                + (f" ({'+' if var >= 0 else ''}{_br(var)}%)"
                   if var is not None else ""))
    if corrente and agg in ("soma", "conta") and atual and \
            ind_.get("projetar", True):
        try:
            feitos = ctx.uteis(ini - timedelta(days=1), hoje - timedelta(days=1))
            total = ctx.uteis(ini - timedelta(days=1), fim)
        except Exception:                               # noqa: BLE001
            feitos = total = 0
        if feitos and total:
            txt += f" · projeção {fmt(atual / feitos * total, f_)}"
    saida.append((_tom_var(var, ind_["bom"]), txt + "."))
    if principal:
        vals = [(v, k) for v, k in zip(s["mes"][1], s["mes"][2]) if v]
        if len(vals) >= 3:
            v_b, (a_b, m_b) = (max(vals) if ind_["bom"] != "baixo"
                               else min(vals))
            media = sum(v for v, _ in vals) / len(vals)
            saida.append(("info", f"Últimos 12 meses: média {fmt(media, f_)}"
                                  f" por mês; melhor mês {MESES[m_b]}/"
                                  f"{str(a_b)[2:]} ({fmt(v_b, f_)})."))
    return saida


def insights_dos_cartoes(kpis, limite=4):
    """Os cartoes de cima que estao em alerta ou atencao."""
    saida = []
    for k in kpis or []:
        if k.get("cor") in ("alerta", "atencao"):
            det = f" ({k['detalhe']})" if k.get("detalhe") else ""
            saida.append((k["cor"], f"{k['rotulo']}: {k['valor']}{det}."))
    return saida[:limite]


def curto(rotulo) -> str:
    """'000031 - JOCIMAR SOARES FRANCA JUNIOR' -> 'JOCIMAR JUNIOR'."""
    import re                                           # noqa: PLC0415
    t = re.sub(r"^\d{3,}\s*-\s*", "", str(rotulo)).strip()
    ps = [w for w in t.split() if w not in ("DA", "DE", "DO", "DAS", "DOS",
                                            "E")]
    if len(ps) > 3 and not t.startswith("("):
        return f"{ps[0]} {ps[-1]}"
    return t or str(rotulo)


def ranking(titulo, pares, formato="num", top=8, menor_primeiro=False,
            cores=None, referencia=None, insight=True, bom="alto",
            nomes_curtos=True):
    """Um bloco de barras horizontais (o maior em cima)."""
    pares = [(curto(a) if nomes_curtos else str(a), round(v, 2))
             for a, v in pares if v is not None]
    pares.sort(key=lambda x: x[1], reverse=not menor_primeiro)
    pares = pares[:top]
    b = {"tipo": "hbarras", "titulo": titulo,
         "rotulos": [a for a, _ in pares], "valores": [v for _, v in pares],
         "formato": formato, "_insight": insight, "_bom": bom}
    if cores:
        b["cores"] = cores(pares) if callable(cores) else cores
    if referencia is not None:
        b["referencia"] = referencia
    return b


def _insight_ranking(b):
    if not b.get("_insight") or len(b["rotulos"]) < 2:
        return None
    f_ = b.get("formato", "num")
    a, z = (b["rotulos"][0], b["valores"][0]), (b["rotulos"][-1],
                                                 b["valores"][-1])
    return ("info", f"{b['titulo']}: maior {a[0]} ({fmt(a[1], f_)}), menor "
                    f"{z[0]} ({fmt(z[1], f_)}).")


def montar(r, ctx, indicadores, extras=(), rankings=(), titulo_ins=None,
           blocos_extra=True, manter=()):
    """Monta r["painel"] no padrao. extras: [(tom, texto)] do farol."""
    from relatorios_nucleo import periodo               # noqa: PLC0415
    ano, mes_e = periodo(ctx)
    mes = mes_de_referencia(ctx, ano, mes_e)
    sufixo = f"{MESES[mes]}/{str(ano)[2:]}"
    # so os indicadores com movimento nos 12 meses (o farol pode mandar
    # mais de 3 candidatos: ficam os 3 primeiros que tem dado)
    janela = set(_meses_ate(ano, mes))

    def tem_dado(i_):
        return any(_dia(ev[0]) and (_dia(ev[0]).year, _dia(ev[0]).month)
                   in janela and any(x for x in ev[1:] if x)
                   for ev in i_["eventos"])
    indicadores = [i for i in indicadores if i and tem_dado(i)][:3]
    ins = list(extras)
    blocos = []
    linha = 0
    for n, i_ in enumerate(indicadores):
        s = series(ctx, i_, ano, mes)
        ins += insights_do_indicador(ctx, i_, ano, mes, s, principal=n == 0)
        rd, vd, cd = s["dia"]
        g_dia = {"titulo": f"{i_['nome']} · dia a dia · {sufixo}",
                 "rotulos": rd,
                 "series": [{"nome": i_["nome"], "cor": i_["cor"],
                             "valores": vd, "cores": cd}],
                 "formato": _fmt_graf(i_["formato"]),
                 "rotular": "nao" if i_["formato"] == "moeda" else "nao_zero"}
        if i_.get("meta_dia"):
            g_dia.update({"meta": i_["meta_dia"], "rotulo_meta": "meta/dia"})
        rs, vs = s["semana"]
        g_sem = {"titulo": f"{i_['nome']} · semana a semana · {sufixo}",
                 "rotulos": rs,
                 "series": [{"nome": i_["nome"], "cor": i_["cor"],
                             "valores": vs}],
                 "formato": _fmt_graf(i_["formato"]), "rotular": True}
        rm, vm, _k = s["mes"]
        g_mes = {"titulo": f"{i_['nome']} · mês a mês (12 meses)",
                 "rotulos": rm,
                 "series": [{"nome": i_["nome"], "cor": i_["cor"],
                             "valores": vm}],
                 "formato": _fmt_graf(i_["formato"]),
                 "rotular": "nao" if i_["formato"] == "moeda" else "nao_zero"}
        if n == 0:
            blocos += [
                {"tipo": "barras", "col": 1, "row": 0, "colspan": 2,
                 "grafico": g_dia},
                {"tipo": "barras", "col": 1, "row": 1, "grafico": g_sem},
                {"tipo": "barras", "col": 2, "row": 1, "grafico": g_mes}]
            linha = 2
        else:
            blocos += [
                {"tipo": "barras", "col": 0, "row": linha, "grafico": g_dia},
                {"tipo": "barras", "col": 1, "row": linha, "grafico": g_sem},
                {"tipo": "barras", "col": 2, "row": linha, "grafico": g_mes}]
            linha += 1
    # os graficos proprios do farol (os que nao sao os 3 de tempo) e os
    # rankings, 3 por linha
    # (as series no tempo ja estao acima: so ficam os cortes - por filial,
    # por vendedor... - e o que o farol pedir em "manter")
    outros = []
    if blocos_extra:
        for g in r.get("graficos") or []:
            t_ = g.get("titulo", "")
            baixo = t_.lower()
            tempo = ("mês a mês" in baixo or "semana a semana" in baixo
                     or baixo.startswith("dia a dia"))
            if tempo and not any(t_.startswith(m_) for m_ in manter):
                continue
            outros.append({"tipo": "barras",
                           "grafico": dict(g, rotular=g.get("rotular", True))})
    for b in rankings:
        if b and b.get("rotulos"):
            outros.append(b)
            i_r = _insight_ranking(b)
            if i_r:
                ins.append(i_r)
    if not indicadores and not outros:
        return r                        # sem dado: fica o resumo antigo
    for j, b in enumerate(outros):
        b = {k: v for k, v in b.items() if not k.startswith("_")}
        blocos.append(dict(b, col=j % 3, row=linha + j // 3))
    linhas_tot = linha + (len(outros) + 2) // 3
    ins += insights_dos_cartoes(r.get("kpis"))
    # sem repetir frase; do mais grave ao informativo
    vistos, final = set(), []
    for tom, txt in ins:
        if txt not in vistos:
            vistos.add(txt)
            final.append((tom, txt))
    final.sort(key=lambda x: ORDEM_TOM.get(x[0], 4))
    if not final:
        final = [("info", "Sem movimento no período escolhido.")]
    blocos.insert(0, {"tipo": "insights",
                      "titulo": titulo_ins or "O que o farol diz",
                      "linhas": final[:MAX_INSIGHTS], "col": 0, "row": 0,
                      "rowspan": 2})
    r["painel"] = {"colunas": (1, 1, 1), "altura_min": max(4, linhas_tot)
                   * 250, "blocos": blocos}
    r["painel_titulo"] = "Resumo gerencial"
    r["insights_painel"] = final
    return r


def _fmt_graf(formato):
    return {"dias": "num1", "pct": "pct"}.get(formato, formato)


# ---------------------------------------------------------------- tabelas
def tabela_de(r, titulo):
    """(linhas, {coluna: indice}) da tabela do relatorio (ou ([], {}))."""
    for t in r.get("tabelas") or []:
        if t["titulo"] == titulo or t["titulo"].startswith(titulo + " ("):
            return t["linhas"], {c["nome"]: j for j, c in
                                 enumerate(t["colunas"])}
    return [], {}


def somar_por(linhas, ix, chave, valor=None, filtro=None):
    """{chave: soma do valor (ou contagem)} das linhas."""
    out = defaultdict(float)
    if chave not in ix or (valor and valor not in ix):
        return {}
    for l in linhas:
        if filtro and not filtro(l):
            continue
        out[l[ix[chave]] or "(vazio)"] += (l[ix[valor]] or 0) if valor else 1
    return dict(out)
