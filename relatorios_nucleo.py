# -*- coding: utf-8 -*-
"""
RELATORIOS BAP - a conta de cada relatorio dos assistentes.

Cada relatorio e uma funcao que devolve um dicionario so de LEITURA:

    {"id", "area", "titulo", "subtitulo", "fonte",
     "kpis":     [{"rotulo", "valor", "cor", "detalhe"}],
     "graficos": [{"titulo", "rotulos", "series": [{"nome","valores","cor"}],
                   "formato"}],
     "tabelas":  [{"titulo", "colunas": [{"nome","tipo","largura"}],
                   "linhas", "tons", "filtros": [nomes de coluna]}],
     "avisos":   [texto],
     "editar":   arquivo que o botao EDITAR NO EXCEL abre (ou None)}

O bap_relatorios.py desenha; aqui so se faz a conta. Os dados vem do
bap_dados (o cache), entao nada aqui le Excel direto - a nao ser o Farol.

REGRAS (03/10/2026):
  * prazo do pedido, a contar da DATA DO PEDIDO, em dias uteis:
    faturar em ate 2; entregar em ate 3 (cidades BAP) - interior/frete, 5;
  * FRETE = pedido para cliente fora de Manaus, Boa Vista, Belem, Santarem,
    Sao Luis, Cuiaba e Varzea Grande.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import bap_dados as bd
from painel_farol import pct_do_liquido
from bap_dados import sem_acento, texto

PRE = "Pré-venda e Faturamento"
VEN = "Vendas e CRM"
POS = "Pós-venda e Logística"
ANA = "Analista Comercial"
TRADE = "Trade Marketing"

VERDE_TXT, AMARELO_TXT = "#2F7D32", "#B7791F"    # texto legivel no branco
VERDE, CINZA, VERMELHO, AZUL, AMARELO = ("#59BA61", "#A7B0AA", "#B42318",
                                         "#1F4FD1", "#C98A00")
MESES = ["", "JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET",
         "OUT", "NOV", "DEZ"]


# ---------------------------------------------------------------- ajudas
def col(nome, tipo="texto", largura=None, oculta=False):
    """oculta: a coluna serve so ao filtro (nao aparece na tela nem no PDF)."""
    padrao = {"texto": 140, "moeda": 110, "moeda2": 110, "pct": 70,
              "pct1": 70, "int": 70, "num": 80, "num1": 80, "num2": 80, "data": 90,
              "dia": 70, "valor": 100}
    return {"nome": nome, "tipo": tipo, "largura": largura or padrao[tipo],
            "oculta": oculta}


def kpi(rotulo, valor, cor="neutro", detalhe="", linhas=None):
    """linhas: [(rotulo, valor, tom)] - as linhas pequenas embaixo do numero
    (tom: "ok", "atencao", "alerta" ou "")."""
    k = {"rotulo": rotulo, "valor": valor, "cor": cor, "detalhe": detalhe}
    if linhas:
        k["linhas"] = linhas
    return k


# (10/11, Alexandre) VISAO POR ESTADO nos cartoes dos farois: as barras
# por estado saem da tabela "Por UF" do proprio farol (a coluna do
# indicador do cartao), na ordem do faturamento acumulado no ano.
ORDEM_UF_CARTAO = ["PA", "MA", "AM", "RR"]   # [SUPOSICAO] fat. no ano
_COLUNA_DO_CARTAO = (            # palavra do rotulo -> prefixo da coluna
    ("faturamento", ("FAT.", "FATURAMENTO", "VENDA", "R$")),
    # (10/11) Farol de Saldo e de Markup
    ("faturado", ("VLR VENDA", "FAT.", "R$ VENDA")),
    ("venda", ("VENDA", "R$ VENDA", "VLR VENDA", "FAT.", "R$")),
    ("sem custo", ("SEM CUSTO",)),
    ("custo", ("CUSTO",)),
    ("margem", ("MARGEM",)),
    ("desconto", ("% DESC. COM.", "% DESC.")),
    ("saldo do frete", ("SALDO FRETE",)),
    ("saldo", ("SALDO",)),
    ("positiva", ("POSIT.", "POSITIVADOS")),
    ("peca", ("PEÇAS",)),
    ("visita", ("VISITA", "VISIT.", "VISITAS")),
    ("cidade", ("CID.",)),
    ("cad", ("CAD.",)),
    ("ticket", ("TICKET",)),
    ("markup", ("MARKUP %", "MARKUP")),
    # (10/11) taxa/dias: so com a coluna propria (sem ela, sem barras)
    ("atraso medio", ("ATRASO MÉDIO", "DIAS ATRASO MÉDIO")),
    ("atraso", ("EM ATRASO", "VENCIDO")),
    ("inadimpl", ("% INADIMPL.", "INADIMPLÊNCIA")),
)
# (10/11) sem a coluna no Por UF: o Por supervisor, pelo estado de cada
# supervisor (recado 20261109-1345: MA Denylson, PA Lais, AM Francisco
# Edson; RR sem vendedor de campo) [SUPOSICAO: fixo ate vir do Planner]
SUPERVISOR_UF = {"DENYLSON": "MA", "LAIS": "PA", "FRANCISCO": "AM"}


# (10/11, Alexandre: "Tudo deve bater... coloque a filial da nota, pois
# ela define de onde vem o faturamento") o ESTADO do faturamento, da
# positivacao, dos pedidos e das pecas e o da FILIAL DA NOTA (D2_FILIAL):
# AM 0101002, RR 0101004, PA 0101005 + 0101007, MA 0101006 (recado
# 20261109-1345). As outras filiais (MT 0101001, AP 0101003) nao tem
# coluna no cartao.
FILIAL_UF = {"0101002": "AM", "0101004": "RR", "0101005": "PA",
             "0101007": "PA", "0101006": "MA", "0101003": "AP",
             "0101001": "MT"}


def uf_da_filial(filial) -> str:
    return FILIAL_UF.get(re.sub(r"\D", "", texto(filial))[-7:], "")


# o nome da filial (ctx.filial) -> UF
_UF_DO_NOME_FILIAL = {"MANAUS": "AM", "BOA VISTA": "RR", "BELEM": "PA",
                      "SANTAREM": "PA", "SAO LUIS": "MA", "MACAPA": "AP",
                      "MATOGROSSO": "MT", "MATO GROSSO": "MT"}


def uf_do_nome_da_filial(nome) -> str:
    return _UF_DO_NOME_FILIAL.get(sem_acento(texto(nome)).upper().strip(),
                                  uf_da_filial(nome))


def por_filial_da_nota(ctx, comp) -> dict:
    """{"fat"|"pecas"|"posit"|"pedidos": {UF: real}} do mes (AAAA-MM), pela
    FILIAL DA NOTA - a mesma conta das linhas do Farol de Metas
    (_juntar_itens: liquido VND - DEV pela data da NF, pecas pela regra da
    meta, positivado = cliente positivo no mes com venda na filial, notas
    de venda distintas). E a mesma fonte da tabela Por UF (10/11)."""
    mix = _juntar_itens(ctx, comp, lambda it: [
        ("uf", uf_da_filial(it.get("filial")) or "?")], {})
    saida = {"fat": {}, "pecas": {}, "posit": {}, "pedidos": {}}
    for (_r, uf), x in mix.items():
        saida["fat"][uf] = x["real"]
        saida["pecas"][uf] = x["pecas"]
        saida["posit"][uf] = len(x["cli"])
        saida["pedidos"][uf] = len(x["nf"])
    return saida


# o indicador do cartao -> a chave do por_filial_da_nota
_FILIAL_DO_CARTAO = (("faturamento", "fat"), ("venda", "fat"),
                     ("peca", "pecas"), ("positiva", "posit"),
                     ("pedido", "pedidos"))


def _colunas_do_cartao(nomes, prefixos):
    """(indice do valor, indice da meta) do indicador na tabela."""
    for pf in prefixos:
        for cand in (pf + " REAL", pf):
            if cand in nomes:
                i_m = nomes.index(pf + " META") \
                    if pf + " META" in nomes else None
                return nomes.index(cand), i_m
    return None, None


def _num_do_texto(t):
    """'R$ 236.110 (16%)' -> 236110.0; '1.072 (66%)' -> 1072.0."""
    m_ = re.search(r"-?\d[\d.]*(?:,\d+)?", str(t or "").replace("R$", ""))
    if not m_:
        return None
    try:
        return float(m_.group(0).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def estados_do_cartao(rel, k) -> dict:
    """(10/11) a VISAO POR ESTADO do cartao: {"barras": [(UF, numero, texto,
    % na barra, tom)], "legenda", "conferencia"} ou {}.
      - REAL do estado: faturamento, positivacao, pedidos e pecas = FILIAL
        DA NOTA (por_filial_da_nota, gravado pelo farol em rel["_por_filial"]);
        o resto = a tabela Por supervisor (estado do supervisor) ou Por UF.
      - Com "Projecao do mes" no cartao, a barra mostra a PROJECAO do estado
        (real x projecao do cartao / real do cartao: a soma das barras = a
        projecao do cartao) e o % = projecao / meta do estado (META do Por
        supervisor), como na RRM; sem projecao, o real e o % = real / meta.
      - "conferencia": soma dos estados x numero do cartao (tem de bater)."""
    r_ = sem_acento(str(k.get("rotulo", ""))).lower()
    # (10/11) taxa por dia (Visitas por dia, R$/dia...) nao soma por
    # estado: sem barras ate a tabela ter a coluna da taxa
    if re.search(r"por dia|/ ?dia|por du\b|/du\b", r_):
        return {}
    prefixos = next((pf for chave, pf in _COLUNA_DO_CARTAO
                     if chave in r_), None)
    chave_f = next((ch for pal, ch in _FILIAL_DO_CARTAO if pal in r_), None)
    tabs = {}
    for t_ in (rel or {}).get("tabelas") or []:
        tabs.setdefault(t_.get("titulo"), t_)
        for j_ in t_.get("juntas") or []:
            tj = j_.get("tabela") or {}
            tabs.setdefault(tj.get("titulo"), tj)
            if str(j_.get("titulo", "")).upper().startswith("SUPERVISOR"):
                tabs.setdefault("Por supervisor", tj)
    # meta e real por estado nas tabelas (Por supervisor primeiro: e la que
    # estao as metas por estado)
    # (10/11, Alexandre: "verifique os demais indicadores se estao no
    # formato filial por nota") o REAL vem do Por UF (agrupado pela filial
    # da nota/titulo nos farois de Markup, Inadimplencia e Saldo) quando o
    # farol tem; o Por supervisor deixa de fora o "(sem supervisor)". O
    # Farol de Metas (com _por_filial) segue o Por supervisor no que nao e
    # nota (visitas, cadastros, cidades: o estado do time). A META do
    # estado: Por supervisor primeiro (e la que estao as metas).
    real_t, meta_uf, eh_dinheiro, eh_pct = {}, {}, False, False
    ordem_t = ("Por supervisor", "Por UF", "Por estado") \
        if "_por_filial" in (rel or {}) else \
        ("Por UF", "Por estado", "Por filial", "Por supervisor")
    for tit in ordem_t:
        t = tabs.get(tit)
        if not t or not t.get("linhas") or not prefixos:
            continue
        nomes = [c["nome"] for c in t["colunas"]]
        i_v, i_m = _colunas_do_cartao(nomes, prefixos)
        if i_v is None:
            continue
        if not real_t:
            eh_dinheiro = t["colunas"][i_v].get("tipo") in ("moeda",
                                                            "moeda2")
            eh_pct = str(t["colunas"][i_v].get("tipo") or "").startswith(
                "pct") or "%" in nomes[i_v]
        r_tab = {}
        # a coluna do estado/supervisor (o Por UF do Saldo comeca pelo MES)
        i_n = next((nomes.index(c_) for c_ in ("UF", "ESTADO", "FILIAL",
                                               "SUPERVISOR")
                    if c_ in nomes), 0)
        linhas_t = t["linhas"]
        if "MÊS" in nomes and i_n != nomes.index("MÊS"):
            # tabela mes a mes: so o mes mais recente (o do cartao)
            i_mes = nomes.index("MÊS")
            mes_ = {m_: i_ for i_, m_ in enumerate(
                ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO",
                 "SET", "OUT", "NOV", "DEZ"))}

            def _ord(v_):
                m_ = re.match(r"([A-Z]{3})/(\d{2})", texto(v_).upper())
                return (int(m_.group(2)), mes_.get(m_.group(1), -1)) \
                    if m_ else (-1, -1)
            ult = max((_ord(l[i_mes]) for l in linhas_t), default=None)
            linhas_t = [l for l in linhas_t if _ord(l[i_mes]) == ult]
        for l in linhas_t:
            nome = sem_acento(texto(l[i_n])).upper()
            if tit == "Por filial":
                # (10/11) Farol de NCC: a filial pelo nome (Belem e
                # Santarem somam no PA)
                uf = uf_do_nome_da_filial(nome)
                if uf:
                    r_tab[uf] = (r_tab.get(uf) or 0) + (l[i_v] or 0)
                continue
            uf = nome if tit != "Por supervisor" else next(
                (u for pre, u in SUPERVISOR_UF.items()
                 if nome.startswith(pre)), None)
            if not uf:
                continue
            r_tab.setdefault(uf, l[i_v] or 0)
            if i_m is not None and l[i_m]:
                meta_uf.setdefault(uf, l[i_m])
        if not real_t:
            real_t = r_tab
    pf_ = ((rel or {}).get("_por_filial") or {}).get(chave_f) \
        if chave_f else None
    real_uf = pf_ if pf_ is not None else real_t
    if chave_f in ("fat", "pecas"):
        eh_dinheiro = True
    if not real_uf:
        return {}
    real_c = _num_do_texto(k.get("valor"))
    proj_c = next((_num_do_texto(v) for r, v, _t in k.get("linhas") or []
                   if sem_acento(r).lower().startswith("projecao do mes")),
                  None)
    fator = (proj_c / real_c) if (proj_c and real_c) else None
    barras, soma = [], 0.0
    # (10/11) as 4 UFs da RRM e, depois, as outras filiais com valor (MT,
    # AP: a soma das barras fecha o cartao)
    extras = sorted((u for u, v in real_uf.items()
                     if u not in ORDEM_UF_CARTAO and u and v),
                    key=lambda u: -abs(real_uf[u] or 0))
    for uf in list(ORDEM_UF_CARTAO) + extras:
        v = real_uf.get(uf)
        if v is None and uf not in meta_uf:
            barras.append((uf, None, "", "", ""))
            continue
        v = v or 0.0
        soma += v
        vb = v * fator if fator else v
        txt = moeda_curta(vb) if eh_dinheiro else (
            f"{br(vb, 1)}%" if eh_pct else br(vb))
        m_ = meta_uf.get(uf)
        if m_:
            a_ = vb / m_ * 100
            barras.append((uf, vb, txt, p(a_), "ok" if a_ >= 100 else (
                "atencao" if a_ >= 90 else "alerta")))
        else:
            barras.append((uf, vb, txt, "", ""))
    if all(b_[1] in (None, 0) for b_ in barras):
        return {}
    fora = (real_c or 0) - soma if real_c is not None else None
    leg = ("projeção do mês ÷ meta do estado" if fator and meta_uf else
           "real ÷ meta do mês do estado" if meta_uf else "")
    return {"barras": barras, "legenda": leg,
            "conferencia": {"cartao": real_c, "soma_estados": soma,
                            "fora_dos_estados": fora,
                            "fonte": "filial da nota" if pf_ is not None
                            else "tabela do farol",
                            # taxa (%): cada estado tem a sua, nao soma
                            "taxa": eh_pct}}


# Pares (fundo, texto) do farol, UM lugar so (manual da marca, 4.2):
# alerta, atencao e ok (--ok-claro #F0F7EC: o verde escuro passa de 4,5:1).
_VERM = ("#FDECEA", "#B42318")
_AMAR = ("#FFF4D6", "#8A5A00")
_VERD = ("#F0F7EC", "#2F7D32")


def tabela(titulo, colunas, linhas, tons=None, filtros=(), total=None,
           kpis_de=None, recortes=None, edicao=None):
    """
    filtros: nomes de coluna, ou {"coluna", "padrao", "multi"} (multi = a
    celula tem varios valores separados por "; ").
    kpis_de(linhas_visiveis) -> cartoes: os numeros de cima seguem o filtro.
    recortes: [(rotulo, funcao(linha) -> bool)] ou (rotulo, {"top": N,
    "coluna": i}) - a caixa RECORTE.
    edicao: o que a assistente pode mudar (ver bap_relatorios.Edicao).
    """
    return {"titulo": titulo, "colunas": colunas, "linhas": linhas,
            "tons": tons or [""] * len(linhas), "filtros": list(filtros),
            "total": total, "kpis_de": kpis_de, "recortes": recortes or [],
            "edicao": edicao}


def novo(rid, area, titulo, subtitulo="", fonte=""):
    return {"id": rid, "area": area, "titulo": titulo, "subtitulo": subtitulo,
            "fonte": fonte, "kpis": [], "graficos": [], "tabelas": [],
            "avisos": [], "editar": None}


def br(v, casas=0):
    from bap_visual import br as _br                    # noqa: PLC0415
    return _br(v, casas)


def moeda(v, casas=0):
    from bap_visual import moeda as _m                  # noqa: PLC0415
    return _m(v, casas)


def pct_de(parte, total):
    return (parte / total * 100.0) if total else None


def p(v):
    return "—" if v is None else f"{br(v, 0)}%"


def mes_de(d) -> str:
    return f"{d.year}-{d.month:02d}" if d else ""


def rotulo_mes(m: str) -> str:
    if not m:
        return ""
    return f"{MESES[int(m[5:7])]}/{m[2:4]}"


# =========================================================================
# CAPA DO FAROL: periodo (mes e ano) e os tres graficos de tempo
# =========================================================================
TODOS_MESES = "TODOS"           # o valor do MES quando sao todos os meses


def periodo(ctx):
    """(ano, mes) escolhidos no Resumo gerencial (padrao: hoje).
    mes = 0 quando a escolha e TODOS OS MESES (o ano inteiro)."""
    try:
        ano = int(ctx.param("ANO") or ctx.hoje.year)
    except (TypeError, ValueError):
        ano = ctx.hoje.year
    v = ctx.param("MÊS")
    if v == TODOS_MESES:
        return ano, 0
    try:
        mes = int(v or ctx.hoje.month)
    except (TypeError, ValueError):
        mes = ctx.hoje.month
    return ano, mes


def todos_os_meses(ctx) -> bool:
    return periodo(ctx)[1] == 0


def mes_escolhido(ctx) -> str:
    """O rotulo do mes escolhido (ex.: OUT/26), para o filtro das tabelas.
    Em TODOS OS MESES o filtro abre em (todos)."""
    ano, mes = periodo(ctx)
    return rotulo_mes(f"{ano}-{mes:02d}") if mes else "(todos)"


def rotulo_no_periodo(ctx, rot) -> bool:
    """O rotulo de mes (SET/26) esta no periodo escolhido?"""
    ano, mes = periodo(ctx)
    if mes:
        return rot == rotulo_mes(f"{ano}-{mes:02d}")
    return str(rot or "").endswith(f"/{ano % 100:02d}")


def no_periodo_txt(ctx, no_mes="no mês") -> str:
    return no_mes if periodo(ctx)[1] else "no ano"


def capa(r, ctx, anos=None):
    """Marca o relatorio como FAROL: abre no Resumo gerencial, com a escolha
    de mes (ou TODOS OS MESES) e ano."""
    ano, mes = periodo(ctx)
    anos = sorted(set(anos or []) | {ctx.hoje.year, ano})
    r["capa"] = True
    r["parametros"] = [
        {"nome": "MÊS", "valores": [(TODOS_MESES, "TODOS OS MESES")]
         + [(m, MESES[m]) for m in range(1, 13)],
         "valor": mes or TODOS_MESES},
        {"nome": "ANO", "valores": [(a, str(a)) for a in anos], "valor": ano}]


def anos_dos_dados(ctx):
    return sorted({it["dt_nf"].year for it in ctx.tabela["itens"]
                   if it.get("dt_nf")} | {ctx.hoje.year})


def _agregar(vals, agg):
    if callable(agg):
        return agg(vals)
    if agg == "conta":
        return len(vals)
    if agg == "unicos":
        return len({v[0] for v in vals})
    if agg == "pct":
        num = sum(v[0] for v in vals)
        den = sum(v[1] for v in vals)
        return num / den * 100.0 if den else 0
    return sum(v[0] for v in vals)            # soma


def graficos_tempo(r, ctx, nome, eventos, formato="num", cor=None, agg="soma"):
    """
    Os tres graficos de toda capa de farol:
      mes a mes (janeiro a dezembro do ANO escolhido), semana a semana e
      dia a dia do MES escolhido.
    eventos: [(data, valor...)] - o agg junta os valores de cada periodo
      "soma" | "conta" | "unicos" (conta valores distintos) | "pct"
      (soma do 1o / soma do 2o) | funcao(lista de tuplas) -> numero.
    """
    import calendar                                       # noqa: PLC0415
    cor = cor or VERDE
    # (06/10) o indicador fica guardado: o Resumo gerencial padrao
    # (painel_farol) refaz dia a dia, semana a semana e 12 meses dele
    r.setdefault("_eventos", []).append({"nome": nome, "eventos": eventos,
                                         "formato": formato, "cor": cor,
                                         "agg": agg})
    ano, mes = periodo(ctx)
    por_mes, por_dia = defaultdict(list), defaultdict(list)
    for ev in eventos:
        d = ev[0]
        if not d:
            continue
        if isinstance(d, datetime):
            d = d.date()
        if d.year == ano:
            por_mes[d.month].append(ev[1:])
            if d.month == mes:
                por_dia[d.day].append(ev[1:])
    if ano < ctx.hoje.year:
        ate = 12
    elif ano == ctx.hoje.year:
        ate = max(ctx.hoje.month, mes)
    else:
        ate = mes
    meses = list(range(1, ate + 1))           # de janeiro ate o mes atual
    r["graficos"].append({
        "titulo": f"{nome} · mês a mês {ano}", "largo": True,
        "rotulos": [MESES[m] for m in meses],
        "series": [{"nome": nome, "cor": cor,
                    "valores": [_agregar(por_mes[m], agg) if por_mes[m]
                                else 0 for m in meses]}],
        "formato": formato})
    if not mes:                    # TODOS OS MESES: as semanas do ano todo
        _semanas_do_ano(r, ctx, ano, nome, eventos, formato, cor, agg)
        return
    ndias = calendar.monthrange(ano, mes)[1]
    semanas = []                                 # [(rotulo, [dias])]
    for dia in range(1, ndias + 1):
        d = date(ano, mes, dia)
        if not semanas or d.weekday() == 0:
            semanas.append((f"{dia:02d}/{mes:02d}", []))
        semanas[-1][1].append(dia)
    r["graficos"].append({
        "titulo": f"Semana a semana · {MESES[mes]}/{str(ano)[2:]}",
        "rotulos": [s[0] for s in semanas],
        "series": [{"nome": nome, "cor": cor, "valores": [
            _agregar(sum((por_dia[d] for d in s[1]), []), agg)
            if any(por_dia[d] for d in s[1]) else 0 for s in semanas]}],
        "formato": formato})
    r["graficos"].append({
        "titulo": f"Dia a dia · {MESES[mes]}/{str(ano)[2:]}",
        "rotulos": [str(d) for d in range(1, ndias + 1)],
        "series": [{"nome": nome, "cor": cor, "valores": [
            _agregar(por_dia[d], agg) if por_dia[d] else 0
            for d in range(1, ndias + 1)]}],
        "formato": formato})


DIAS_SEMANA = ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM")


def _semanas_do_ano(r, ctx, ano, nome, eventos, formato, cor, agg):
    """Em TODOS OS MESES: semana a semana do ano inteiro e o total por dia
    da semana (no lugar do dia a dia, que nao cabe num ano)."""
    fim = min(ctx.hoje, date(ano, 12, 31)) if ano >= ctx.hoje.year \
        else date(ano, 12, 31)
    por_sem, por_dsem = defaultdict(list), defaultdict(list)
    for ev in eventos:
        d = ev[0]
        if not d:
            continue
        if isinstance(d, datetime):
            d = d.date()
        if d.year == ano:
            por_sem[semana_de(d)].append(ev[1:])
            por_dsem[d.weekday()].append(ev[1:])
    def m_(x):                      # a semana de 29/12 ja e de janeiro
        return max(x, date(ano, 1, 1)).month
    semanas, s = [], semana_de(date(ano, 1, 1))
    while s <= fim:
        semanas.append(s)
        s += timedelta(days=7)
    r["graficos"].append({
        "titulo": f"{nome} · semana a semana {ano}", "largo": True,
        # o nome do mes so na 1a semana dele (40 rotulos nao cabem)
        "rotulos": [MESES[m_(x)] if n == 0 or m_(x) != m_(semanas[n - 1])
                    else "" for n, x in enumerate(semanas)],
        "series": [{"nome": nome, "cor": cor, "valores": [
            _agregar(por_sem[x], agg) if por_sem[x] else 0
            for x in semanas]}],
        "formato": formato})
    dias = [d for d in range(7) if d < 6 or por_dsem[d]]
    r["graficos"].append({
        "titulo": f"Por dia da semana · {ano}",
        "rotulos": [DIAS_SEMANA[d] for d in dias],
        "series": [{"nome": nome, "cor": cor, "valores": [
            _agregar(por_dsem[d], agg) if por_dsem[d] else 0 for d in dias]}],
        "formato": formato})


def _eventos_faturamento(ctx, liquido=False):
    """[(data da NF, valor)] das vendas; liquido = menos as devolucoes."""
    ev = []
    for it in ctx.tabela["itens"]:
        v = _liquido(it) if liquido else (
            it["valor"] if it["tipo"] == "VND" else None)
        if v is not None:                    # RN-GER-002: o _liquido
            ev.append((it["dt_nf"], v))
    return ev


def no_mes(ctx, d) -> bool:
    """A data esta no mes escolhido (ou no ano, em TODOS OS MESES)?"""
    ano, mes = periodo(ctx)
    if isinstance(d, datetime):
        d = d.date()
    return bool(d) and d.year == ano and (not mes or d.month == mes)


def semana_de(d):
    """A segunda-feira da semana."""
    return d - timedelta(days=d.weekday()) if d else None


def ultimos_meses(hoje, n):
    saida, a, m = [], hoje.year, hoje.month
    for _ in range(n):
        saida.append(f"{a}-{m:02d}")
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    return list(reversed(saida))


FORA_DO_PLANNER = "FORA DO PLANNER"
ORDEM_STATUS = {"ATIVO": 0, "CHURN 30": 1, "CHURN 60": 2, "CHURN 90": 3,
                "CHURN 90+": 4, "INATIVO": 4, "NUNCA COMPROU": 5}
COL_ST_PROTHEUS, COL_ST_PLANNER = "STATUS PROTHEUS", "STATUS PLANNER"
COL_SIT_PLANNER = "SITUAÇÃO PLANNER"     # ATIVO, CHURN 30/60/90, INATIVO...


def status_planner_binario(situacao, inativo=False) -> str:
    """STATUS PLANNER so tem ATIVO ou INATIVO. (06/10) TODO cliente do
    Planner e ATIVO; INATIVO e so o inativado a mao na aba Base cliente do
    Planner. Fora do Planner fica como esta. (20/10) No .json da base de
    clientes todos vao ATIVO (o inativado com o vendedor padrao)."""
    if situacao in (FORA_DO_PLANNER, "SEM STATUS", "", None):
        return situacao or ""
    return "INATIVO" if inativo else "ATIVO"


def _loja2(loja) -> str:
    d = "".join(ch for ch in texto(loja) if ch.isdigit())
    return d.zfill(2) if d else ""


def _cod_loja_de(v):
    """"001234-01" -> ("001234", "01"); "001234 - NOME" -> ("001234", None)."""
    m = re.match(r"\s*(\d+)(?:-(\d+))?", texto(v))
    return (m.group(1), m.group(2)) if m else ("", None)


def com_status(ctx, t, pos=None, i_cli=None, chaves=None, planner=True,
               situacao=True):
    """
    Poe STATUS PROTHEUS, STATUS PLANNER (ATIVO/INATIVO) e SITUACAO PLANNER
    (ATIVO, CHURN 30/60/90, INATIVO, NUNCA COMPROU), com filtro, na tabela
    t, na posicao pos (sem pos: no fim). O cliente de cada linha vem da
    coluna i_cli ("cod-loja" ou "cod - nome") ou da lista chaves
    [(cod, loja)]. planner=False: so o STATUS PROTHEUS; situacao=False:
    sem a SITUACAO PLANNER (a tabela ja tem).
    Os cartoes, recortes, total e os indices do calendario/Protheus seguem
    vendo a linha como era - as colunas novas sao tiradas antes.
    """
    novas = [col(COL_ST_PROTHEUS, "texto", 130)]
    if planner:
        novas.append(col(COL_ST_PLANNER, "texto", 130))
        if situacao:
            novas.append(col(COL_SIT_PLANNER, "texto", 135))
    n = len(novas)
    k = len(t["colunas"]) if pos is None else pos
    t["colunas"][k:k] = novas
    linhas = []
    for j, l in enumerate(t["linhas"]):
        cod, loja = chaves[j] if chaves is not None else _cod_loja_de(l[i_cli])
        if not cod:
            vals = [""] * n
        else:
            vals = [ctx.status_protheus(cod, loja)]
            if planner:
                sit = ctx.status_planner(cod, loja)
                vals.append(status_planner_binario(
                    sit, getattr(ctx, "inativo", lambda *_: False)(
                        cod, loja)))
                if situacao:
                    vals.append(sit)
        l = list(l)
        linhas.append(l[:k] + vals + l[k:])
    t["linhas"] = linhas

    def tira(ls):
        return [l[:k] + l[k + n:] for l in ls]
    if isinstance(t.get("total"), list) and len(t["total"]) >= k:
        t["total"] = t["total"][:k] + [""] * n + t["total"][k:]
    f = t.get("kpis_de")
    if f:
        def kp_sem_novas(ls, filtro=None, f=f):
            # o filtro vem com os indices da tela (com as colunas novas)
            fo = {(j if not isinstance(j, int) or j < k else j - n): v
                  for j, v in (filtro or {}).items()
                  if not (isinstance(j, int) and k <= j < k + n)}
            return chamar_kpis_de(f, tira(ls), fo or None)
        t["kpis_de"] = kp_sem_novas
    ed = t.get("edicao")                # (13/10) a edicao segue a coluna
    if isinstance(ed, dict):
        ed = dict(ed)
        if isinstance(ed.get("chave"), int) and ed["chave"] >= k:
            ed["chave"] += n
        ed["campos"] = [dict(c_, col=c_["col"] + n)
                        if isinstance(c_.get("col"), int) and c_["col"] >= k
                        else c_ for c_ in ed.get("campos") or []]
        if ed.get("so_colunas"):
            ed["so_colunas"] = [x + n if x >= k else x
                                for x in ed["so_colunas"]]
        t["edicao"] = ed
    for chave_d in ("detalhe",):
        d_ = t.get(chave_d)
        if isinstance(d_, dict):
            t[chave_d] = {a: (b + n if isinstance(b, int) and b >= k else b)
                          for a, b in d_.items()}
    td = t.get("total_de")              # (12/10) o total que segue o filtro
    if callable(td):
        def _td(ls, td=td):
            x = td(tira(ls))
            return (x[:k] + [""] * n + x[k:]) if isinstance(x, list) else x
        t["total_de"] = _td
    rec = []
    for rot, x in t.get("recortes") or []:
        if callable(x):
            rec.append((rot, lambda l, x=x: x(l[:k] + l[k + n:])))
        elif isinstance(x, dict) and isinstance(x.get("coluna"), int) and \
                x["coluna"] >= k:
            rec.append((rot, dict(x, coluna=x["coluna"] + n)))
        else:
            rec.append((rot, x))
    t["recortes"] = rec
    for chave in ("calendario", "protheus"):
        d = t.get(chave)
        if isinstance(d, dict):
            t[chave] = {a: (b + n if a.startswith("i_") and isinstance(b, int)
                            and b >= k else b) for a, b in d.items()}
    t["filtros"] = list(t.get("filtros") or []) + \
        [c["nome"] for c in novas]
    return t


# as tabelas que ganham STATUS PROTHEUS / STATUS PLANNER:
# rid -> [(titulo da tabela, coluna do cliente, posicao das colunas novas)]
STATUS_NAS_TABELAS = {
    # Farol de Pedidos: no fim, para nao mexer na ordem do Power BI
    # (23/10, Alexandre) Farol de Pedidos sem o STATUS do cliente
    "pv_abertos": [("Pedidos em aberto", 7, 8)],
    "pv_faturados": [("Notas faturadas", 11, 12)],
    "pv_excluidos": [("Pedidos excluídos", 5, 6)],
    "vc_planner": [("Calendário", 10, 12)],     # Por cliente: na funcao
    "vc_painel": [("Clientes", 0, 6)],
    "vc_markup": [("Por pedido", 6, 7)],
    # (22/10, Alexandre) Farol de Saldo simplificado: sem o STATUS
    "pl_inadimplencia": [("Títulos", 8, 10), ("Por cliente", 2, 4)],
}


def _status_nas_tabelas(ctx, rel):
    for titulo, i_cli, pos in STATUS_NAS_TABELAS.get(rel.get("id"), ()):
        for t in rel["tabelas"]:
            if t["titulo"] == titulo and \
                    COL_ST_PROTHEUS not in [c["nome"] for c in t["colunas"]]:
                try:
                    com_status(ctx, t, pos, i_cli)
                except Exception as erro:               # noqa: BLE001
                    rel.setdefault("avisos", []).append(
                        f"Status do cliente fora da tabela {titulo}: {erro}")


# RN-GER-013 (Alexandre, 26/11/2026: "mudar para cliente fora da base e deixar
# um checkbox no farol de pedidos para ignorar eles, pois sao pedidos internos e
# nao pode ir para solicitacao de lojas"): pedido de cliente que nao esta na base
# de clientes da BAP (o robo grava "NAO LOCALIZADO NA BASE" na RAZAO_SOCIAL do
# ftPedidos) fica no Farol de Pedidos com o nome NOME_FORA_DA_BASE, sem casar o
# codigo com zeros (o "6171" virava "006171" e mostrava outro cliente da BAP).
# A caixa "ignorar" fica na web; a Solicitacao BAP nao usa esse pedido (robo).
CLIENTE_FORA_DA_BASE = "NÃO LOCALIZADO NA BASE"
NOME_FORA_DA_BASE = "CLIENTE FORA DA BASE"


LOJA_NAO_IDENTIFICADA = "(loja não identificada)"


def cadastro_do_pedido(filial, lojas_do_codigo) -> dict:
    """RN-GER-019 (fonte: docs/produto/03-regras.md).
    Entrada: lojas_do_codigo = [{uf, nome, fantasia, cidade, limite, saldo,
    atraso_valor}]; saldo None = nao conhecido.
    Saida: {nome, fantasia, uf, cidade, limite, saldo, atraso_valor,
    identificada, credito_apurado}."""
    lojas = [x for x in (lojas_do_codigo or []) if isinstance(x, dict)]
    uf_f = uf_da_filial(filial)
    na_uf = [x for x in lojas if uf_f and texto(x.get("uf")).upper() == uf_f]
    escolhida = None
    if len(na_uf) == 1:
        escolhida = na_uf[0]
    elif len(lojas) == 1:                 # loja unica: usa essa loja (RN)
        escolhida = lojas[0]
    if escolhida is not None:
        saldo = escolhida.get("saldo")
        return {"nome": texto(escolhida.get("nome")),
                "fantasia": texto(escolhida.get("fantasia")),
                "uf": texto(escolhida.get("uf")).upper(),
                "cidade": texto(escolhida.get("cidade")).upper(),
                "limite": escolhida.get("limite"), "saldo": saldo,
                "atraso_valor": escolhida.get("atraso_valor"),
                "identificada": True, "credito_apurado": saldo is not None}
    base = na_uf or lojas
    nomes = {sem_acento(texto(x.get("nome"))).upper() for x in base}
    nome = texto(base[0].get("nome")) if base and len(nomes) == 1 else ""
    nome = nome or LOJA_NAO_IDENTIFICADA
    # fantasia = nome: o titulo do cartao (celular) nunca fica so com o numero
    return {"nome": nome,
            "fantasia": nome, "uf": uf_f, "cidade": "", "limite": None,
            "saldo": None, "atraso_valor": None, "identificada": False,
            "credito_apurado": False}


def fora_da_base(razao) -> bool:
    """RN-GER-013: o item e de cliente fora da base de clientes da BAP."""
    return sem_acento(texto(razao)).upper().strip() == \
        sem_acento(CLIENTE_FORA_DA_BASE)


def _sem_internos(nome, bloco):
    """(13/10) Os CNPJs internos (FRW, BAP AUTOPARTS, PMZ DISTRIBUIDORA) fora do resultado
    tambem no cache montado antes da regra: a venda sai da TABELA e o
    cliente fica INATIVO na base. O cache novo ja vem assim."""
    try:
        # (14/10) SEMPRE pela regra de hoje (o cache montado antes de a
        # PMZ DISTRIBUIDORA entrar na regra tambem filtra) - sem remontar
        if nome == "tabela":
            cli = bloco.get("clientes") or {}
            fora = {c for c, x in cli.items()
                    if bd._interno(x.get("nome"), x.get("fantasia"))}  # noqa: SLF001
            fora |= set(bloco.get("internos") or ())
            bloco = dict(bloco, internos=sorted(fora), itens=[
                it for it in bloco.get("itens") or []
                if it["cliente"] not in fora
                and not bd._interno(it.get("razao"))])  # noqa: SLF001
        elif nome == "inadimplencia":
            bloco = dict(bloco, titulos=bd.titulos_sem_internos(
                bloco.get("titulos")))
        elif nome == "base":
            cs = bloco.get("clientes") or []
            if cs:
                novos = []
                for c in cs:
                    i_ = bool(c.get("interno")) or bd._interno(  # noqa: SLF001
                        c.get("nome"), c.get("fantasia"))
                    novos.append(dict(c, interno=i_,
                                      inativo=c.get("inativo") or i_))
                bloco = dict(bloco, clientes=novos)
    except Exception:                                   # noqa: BLE001
        pass
    return bloco


def hoje_manaus() -> date:
    """Data de hoje no fuso America/Manaus (regra 4); sem tzdata, UTC-4 fixo."""
    from datetime import timezone
    try:
        from zoneinfo import ZoneInfo
        fuso = ZoneInfo("America/Manaus")
    except Exception:                                   # noqa: BLE001
        fuso = timezone(timedelta(hours=-4))
    return datetime.now(fuso).date()


def chamar_kpis_de(f, linhas, filtro=None):
    """kpis_de(linhas) e, se aceitar, kpis_de(linhas, filtro={col: valor}).
    Sem `filtro` na assinatura, a chamada e identica a de antes."""
    import inspect
    try:
        if "filtro" in inspect.signature(f).parameters:
            return f(linhas, filtro=filtro)
    except (TypeError, ValueError):
        pass
    return f(linhas)


# ---------------------------------------------------------------------------
# RN-GER-011 (T-0017): nome e texto de cliente vao ao site sem documento e sem
# contato. Funcoes puras; o PC continua mostrando o texto como esta.
# ---------------------------------------------------------------------------
_CPF_FMT = r"\d{3}\.\d{3}\.\d{3}-\d{2}"
_CNPJ_FMT = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
_DOC_MEIO = re.compile(
    r"(?<![\w])(?:\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"
    r"|\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?![\w])")
_ROTULO_DOC = r"(?:(?:CNPJ|CPF)\s*[:.\-]?\s*)?"
_DOC_QUALQUER = re.compile(
    rf"{_ROTULO_DOC}(?<![\w])(?:{_CNPJ_FMT}|{_CPF_FMT}"
    r"|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})"
    r"(?![\w])", re.IGNORECASE)
# pedaco de documento no comeco (MEI "12.345.678 FULANO", RN-POS-004): so
# quando tem separador entre digitos; numero puro de 6 a 10 digitos fica
_DOC_PEDACO_INI = re.compile(r"^\s*(?=(?:[.\-/\s]*\d){6})[\d.\-/\s]+")
_VALOR_RS = re.compile(r"(R\$\s*\d[\d.]*(?:,\d+)?)")
_DOC_SOLTO = re.compile(r"(?<!\d)(?:\d{14}|\d{11})(?!\d)")
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
_FONE = re.compile(
    r"(?<![\w])(?:\+?55[\s.\-]?)?(?:\(?\d{2}\)?[\s.\-]?)?9?\d{4}[\s.\-]?\d{4}"
    r"(?![\w]|,\d)")
_COD_CLIENTE = re.compile(r"^\d{6}(?:-\d{2})? - ")
REMOVIDO = "[removido]"


def _limpa_pontas(s: str) -> str:
    s = re.sub(r"\(\s*\)|\[\s*\]", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" \t-/.,;:")


def sem_documento(texto) -> str:
    """Tira CPF/CNPJ do comeco, do fim (11 ou 14 digitos, com ou sem
    mascara) e o formatado no meio. RN-GER-011."""
    if texto in (None, ""):
        return ""
    s = _DOC_QUALQUER.sub(" ", str(texto))
    m = _DOC_PEDACO_INI.match(s)
    if m and re.search(r"\d[.\-/]\d", m.group(0)):
        s = s[m.end():]
    return _limpa_pontas(s)


def cliente_sem_documento(texto) -> str:
    """Coluna 'codigo - nome': mantem o codigo do comeco e limpa o resto."""
    if texto in (None, ""):
        return ""
    s = str(texto)
    if re.fullmatch(r"\d{6}(?:-\d{2})?", s.strip()):
        return s.strip()                 # so o codigo
    m = _COD_CLIENTE.match(s)
    if not m:
        return sem_documento(s)
    nome = sem_documento(s[m.end():])
    return m.group(0) + nome if nome else m.group(0).rstrip(" -")


def texto_sem_contato(texto) -> str:
    """Troca telefone (8 a 13 digitos, com ou sem DDD/55 e mascara), e-mail e
    CPF/CNPJ por '[removido]'. RN-GER-011."""
    if texto in (None, ""):
        return ""
    def limpa(parte):
        parte = _EMAIL.sub(REMOVIDO, parte)
        parte = _DOC_MEIO.sub(REMOVIDO, parte)
        parte = _DOC_SOLTO.sub(REMOVIDO, parte)
        return _FONE.sub(REMOVIDO, parte)
    # valor em reais (R$ ...) nunca e telefone
    partes = _VALOR_RS.split(str(texto))
    return "".join(p if k % 2 else limpa(p) for k, p in enumerate(partes))


def _texto_filtro(valor, tipo) -> str:
    """O texto da celula como a tela compara no filtro (bv.formatar 'texto'
    e bv.data_br nas colunas de data)."""
    if tipo in ("data", "dia"):
        if isinstance(valor, datetime):
            valor = valor.date()
        if isinstance(valor, date):
            return f"{valor:%d/%m/%Y}"
        return "" if valor is None else str(valor)
    return "" if valor in (None, "") else str(valor)


def _indices_em_linhas(t, linhas):
    """Indices, em t["linhas"], das linhas dadas (por identidade)."""
    pos = {id(l): k for k, l in enumerate(t["linhas"])}
    return [pos[id(l)] for l in linhas if id(l) in pos]


def linhas_padrao(t, params=None) -> list:
    """Indices (base 0) das linhas que a tela mostra ao abrir a aba: os
    filtros com `padrao`, sem recorte e sem busca. Mesma regra de
    `bap_relatorios.VistaTabela._filtradas` no estado inicial. `params` =
    nomes dos parametros de cima (so decide o filtro repetido que vira
    oculto); filtros gerais da janela nao entram (sem Tk). Os indices sao
    sempre de `t["linhas"]` (com `linhas_filtro`, a linha da base que nao
    esta em `t["linhas"]` fica fora)."""
    nomes = [c["nome"] for c in t["colunas"]]
    fora = set(t.get("filtros_fora") or ())
    base = t.get("linhas_filtro") or t["linhas"]
    tons_b = (t.get("tons_filtro") if t.get("linhas_filtro")
              else t.get("tons")) or [""] * len(base)
    ativos = {}
    for f in t.get("filtros") or ():
        nome = nome_filtro(f)
        if nome not in nomes or nome in fora or not isinstance(f, dict):
            continue
        padrao = f.get("padrao")
        oculto = bool(f.get("oculto"))
        if params is not None and (nome in params or nome.removesuffix(
                " PLANNER").removesuffix(" PROTHEUS") in params):
            oculto = "padrao" in f or oculto
        i = nomes.index(nome)
        multi = bool(f.get("multi"))
        if oculto:
            v = padrao if padrao not in (None, "") else None
        else:
            if padrao in (None, ""):
                continue
            tipo = t["colunas"][i].get("tipo")
            if multi:
                valores = {x.strip() for l in base
                           for x in str(l[i] or "").split(";") if x.strip()}
            else:
                valores = {_texto_filtro(l[i], tipo) for l in base
                           if l[i] not in (None, "")}
            v = padrao if padrao in valores else None
        if v is not None:
            ativos[i] = (v, multi)
    saida = []
    for k, l in enumerate(base):
        ok = True
        for i, (v, multi) in ativos.items():
            if multi:
                if v not in [x.strip() for x in str(l[i] or "").split(";")]:
                    ok = False
                    break
            elif _texto_filtro(l[i], t["colunas"][i].get("tipo")) != v:
                ok = False
                break
        if ok:
            saida.append((k, l))
    if t.get("top_n"):
        saida = saida[:t["top_n"]]
        if t.get("ordem_top"):
            i_m, i_f = t["ordem_top"]
            saida.sort(key=lambda x: (-(x[1][i_m] or 0), -(x[1][i_f] or 0)))
    return _indices_em_linhas(t, [l for _k, l in saida])


def recortes_em_linhas(t) -> list:
    """[{"rotulo", "linhas"}]: para cada recorte por funcao da tabela, na
    ordem do PC, os indices (base 0, em `linhas`) que ele deixa. Recorte
    {"top": N} fica fora, com aviso no log. Recorte que falha fica vazio.
    Tabela `enxuta` (sem recortes no PC): lista vazia. Os indices sao de
    `t["linhas"]`, a mesma base de `linhas_padrao`; com `linhas_filtro` o
    recorte corre na base do filtro e so entram as linhas que estao em
    `t["linhas"]`."""
    import logging
    saida = []
    if t.get("enxuta"):
        return saida
    base = t.get("linhas_filtro") or t["linhas"]
    for r in t.get("recortes") or ():
        rotulo, regra = r[0], r[1]
        if callable(regra):
            idx = []
            ok = []
            for l in base:
                try:
                    if regra(l):
                        ok.append(l)
                except Exception:                       # noqa: BLE001
                    continue
            idx = _indices_em_linhas(t, ok)
            saida.append({"rotulo": rotulo, "linhas": idx})
        else:
            logging.getLogger(__name__).warning(
                "recorte '%s' (top) fica fora do pacote da web", rotulo)
    return saida


class Contexto:
    """Os blocos de dado que um relatorio pede, carregados sob demanda."""

    def __init__(self, raiz, hoje=None, log=None, params=None):
        self.raiz = Path(raiz)
        self.hoje = hoje or hoje_manaus()
        self.log = log
        self.params = dict(params or {})
        self._b = {}
        self.fer = bd.feriados(self.raiz)

    def __getattr__(self, nome):
        if nome.startswith("_") or nome not in bd.BLOCOS:
            raise AttributeError(nome)
        if nome not in self._b:
            self._b[nome] = _sem_internos(
                nome, bd.carregar(self.raiz, nome, log=self.log))
            if nome == "posvenda":
                _prever_pelo_pedido(self, self._b[nome])
        return self._b[nome]

    def param(self, nome, padrao=None):
        v = self.params.get(nome)
        return padrao if v in (None, "", "(todos)") else v

    # -- os cadastros, juntos
    def cliente(self, cod):
        """Nome, cidade, UF, segmento e vendedor de um codigo de cliente."""
        if not hasattr(self, "_cli"):
            self._cli = {c["cod"]: c for c in self.base["clientes"]}
        c = self._cli.get(cod)
        if c:
            return c
        t = self.tabela["clientes"].get(cod, {})
        return {"cod": cod, "nome": t.get("nome", ""),
                "fantasia": t.get("fantasia", ""), "cidade": t.get("cidade", ""),
                "uf": t.get("uf", ""), "segmento": "(FORA DA BASE)",
                "vend": "", "vend_nome": "", "supervisor": "", "status": ""}

    # -- RN-GER-019: o cadastro do cliente NO PEDIDO (a loja da filial)
    def lojas_do_codigo(self, cod):
        """Todas as lojas de um codigo (protheus_lojas, do bap_dados) com o
        limite de cada uma; o saldo e o atraso so existem para a loja que o
        cadastro (tabela['clientes']) guarda por codigo. Retorno so de
        leitura (memo)."""
        def _ficha(d, saldo, atraso, loja):
            return {"loja": loja, "nome": d.get("nome"),
                    "fantasia": d.get("fantasia"), "cidade": d.get("cidade"),
                    "uf": d.get("uf"), "limite": d.get("limite"),
                    "saldo": saldo, "atraso_valor": atraso}

        if not hasattr(self, "_lojas_idx"):
            idx = defaultdict(list)
            guarda = self.tabela.get("clientes") or {}
            for (c_, loja), d in _lojas_protheus(self).items():
                g = guarda.get(c_) or {}
                mesma = bool(g) and texto(g.get("loja")) == texto(loja)
                idx[c_].append(_ficha(
                    d, g.get("saldo") if mesma else None,
                    g.get("atraso_valor") if mesma else None, loja))
            self._lojas_idx = idx
        lojas = self._lojas_idx.get(cod)
        if lojas:
            return lojas
        g = (self.tabela.get("clientes") or {}).get(cod)
        return [_ficha(g, g.get("saldo"), g.get("atraso_valor"),
                       g.get("loja"))] if g else []

    def cadastro_do_pedido(self, filial, cod):
        """cadastro_do_pedido() (RN-GER-019) com as lojas deste codigo; {}
        se o codigo nao esta no cadastro (cliente fora da base). Retorno so
        de leitura (memo)."""
        memo = self.__dict__.setdefault("_memo_cad_ped", {})
        k = (uf_da_filial(filial), cod)
        if k not in memo:
            lojas = self.lojas_do_codigo(cod)
            memo[k] = cadastro_do_pedido(filial, lojas) if lojas else {}
        return memo[k]

    def cliente_do_pedido(self, filial, cod):
        """ctx.cliente(cod) com nome, fantasia, cidade e UF da loja do
        pedido (RN-GER-019); o resto (segmento, vendedor) fica o do codigo."""
        c = self.cliente(cod)
        r = self.cadastro_do_pedido(filial, cod)
        if not r:
            return c
        return dict(c, nome=r["nome"], fantasia=r["fantasia"],
                    cidade=r["cidade"], uf=r["uf"])

    def credito_do_pedido(self, filial, cod):
        """A ficha de credito (limite, saldo, atraso, credito_apurado) da
        loja do pedido."""
        r = self.cadastro_do_pedido(filial, cod)
        if not r:
            return {}
        return {"limite": r["limite"], "saldo": r["saldo"],
                "atraso_valor": r["atraso_valor"],
                "credito_apurado": r["credito_apurado"]}

    # -- ATIVO/INATIVO do cliente: o do Protheus (coluna STATUS do BAP
    #    Tools, na dClientesBap) e o do Planner (a situacao pelos dias sem
    #    compra: ATIVO, CHURN 30/60/90, INATIVO, NUNCA COMPROU)
    def status_protheus(self, cod, loja=None):
        if not hasattr(self, "_stp"):
            self._stp = dict(self.tabela.get("status_lojas") or {})
            self._stp_cod = {}
            for (c, _), st in self._stp.items():
                if st == "ATIVO" or c not in self._stp_cod:
                    self._stp_cod[c] = st
        cod = bd.cod6(cod)
        if loja not in (None, ""):
            st = self._stp.get((cod, _loja2(loja)))
            if st is not None:
                return st or "SEM STATUS"
        st = self._stp_cod.get(cod)
        return "SEM CADASTRO" if st is None else (st or "SEM STATUS")

    def status_planner(self, cod, loja=None):
        if not hasattr(self, "_stl"):
            self._stl, self._stl_cod = {}, {}
            for c in self.base.get("clientes") or []:
                st = c.get("status") or "SEM STATUS"
                self._stl[(c["cod"], _loja2(c.get("loja")))] = st
                atual = self._stl_cod.get(c["cod"])
                if atual is None or ORDEM_STATUS.get(st, 9) < \
                        ORDEM_STATUS.get(atual, 9):
                    self._stl_cod[c["cod"]] = st
        cod = bd.cod6(cod)
        if loja not in (None, ""):
            st = self._stl.get((cod, _loja2(loja)))
            if st is not None:
                return st
        return self._stl_cod.get(cod) or FORA_DO_PLANNER

    def inativo(self, cod, loja=None):
        """O cliente foi inativado no Planner (aba Base cliente)? Sem a
        loja: inativo so quando TODAS as lojas dele estao inativas."""
        if not hasattr(self, "_inat"):
            self._inat, self._inat_cod = set(), {}
            for c in self.base.get("clientes") or []:
                self._inat_cod.setdefault(c["cod"], []).append(
                    bool(c.get("inativo")))
                if c.get("inativo"):
                    self._inat.add((c["cod"], _loja2(c.get("loja"))))
        cod = bd.cod6(cod)
        if loja not in (None, "") and self._tem_loja(cod, loja):
            return (cod, _loja2(loja)) in self._inat
        lojas = self._inat_cod.get(cod) or []
        return bool(lojas) and all(lojas)

    def _tem_loja(self, cod, loja):
        if not hasattr(self, "_lojas"):
            self._lojas = {(c["cod"], _loja2(c.get("loja")))
                           for c in self.base.get("clientes") or []}
        return (cod, _loja2(loja)) in self._lojas

    def nome_cliente(self, cod, filial=None):
        """filial (RN-GER-019): o nome da loja do pedido, nao o do codigo."""
        c = self.cliente_do_pedido(filial, cod) if filial \
            else self.cliente(cod)
        return f"{cod} - {c.get('fantasia') or c.get('nome') or ''}".strip(" -")

    def vendedor(self, cod):
        p_ = self.base["pessoas"].get(texto(cod))
        if p_:
            return f"{cod} - {p_['nome']}"
        nome = self._nomes_antigos().get(texto(cod))   # saiu da equipe
        return f"{cod} - {nome}" if nome else (cod or "(sem vendedor)")

    def _nomes_antigos(self):
        """O nome de quem ja esteve na equipe em algum mes do Planner."""
        if not hasattr(self, "_nomes_ant"):
            import json as _json                        # noqa: PLC0415
            self._nomes_ant = {}
            arqs = sorted((self.raiz / "SISTEMA BAP" / "PLANNER_MESES").glob(
                "planner_config_*.json")) + [self.raiz / "planner_config.json"]
            for a in arqs:
                try:
                    for p_ in _json.loads(a.read_text("utf-8")).get(
                            "pessoas") or []:
                        if p_.get("cod_protheus") and p_.get("nome"):
                            self._nomes_ant[texto(p_["cod_protheus"])] = \
                                texto(p_["nome"])
                except (OSError, ValueError):
                    pass
        return self._nomes_ant

    def supervisor_de(self, cod_vend):
        p_ = self.base["pessoas"].get(texto(cod_vend)) or {}
        s = self.base["pessoas"].get(p_.get("chefe", "")) or {}
        return s.get("nome") or "(SEM SUPERVISOR)"

    def filial(self, cod):
        return self.tabela["filiais"].get(cod, cod)

    def cond(self, cod):
        c = texto(cod).zfill(3) if cod else ""
        return self.tabela["condpag"].get(c, c)

    def produto(self, cod):
        return self.tabela["nomes"].get(cod, "")

    def familia(self, cod):
        """(15/10) A FAMILIA do Catalogo BAP 2026 (AMORTECEDORES E KITS...)."""
        return self.tabela["familias"].get(cod) or "OUTROS"

    def categoria_bap(self, cod):
        """(15/10) A CATEGORIA do Catalogo BAP 2026: PEÇAS LINHA LEVE /
        PESADA / MOTO (03/11), BATERIAS, LUBRIFICANTES, QUÍMICOS, PNEUS,
        ACESSÓRIOS (o resto: OUTROS). Vem do ESTOQUE_BAP (colunas da
        Automacao) / BASE_BAP_UNIFICADA; o "PEÇAS" antigo (estoque ou cache
        de antes de 03/11) vira a linha de pecas pela LINHA do produto."""
        c = (self.tabela.get("categorias_bap") or {}).get(cod) or "OUTROS"
        if c == "PEÇAS" or (c not in LINHAS_PECAS and c.startswith("PE")
                            and sem_acento(c).upper().startswith("PECAS")):
            try:
                import catalogo_bap as cbp              # noqa: PLC0415
                return cbp.categoria_da_linha(c, self.linha(cod))
            except Exception:                           # noqa: BLE001
                return c
        return c

    def sistema(self, cod):
        """(15/10) O SISTEMA do Catalogo BAP 2026 (SUSPENSÃO, FREIO...)."""
        return (self.tabela.get("sistemas") or {}).get(cod) or "OUTROS"

    def linha(self, cod):
        """(15/10) A LINHA do Catalogo BAP 2026 (LEVE, PESADA, LEVE E
        PESADA, MOTO, UNIVERSAL)."""
        return (self.tabela.get("linhas") or {}).get(cod) or "OUTROS"

    def classe(self, cod, nome):
        """CATEGORIA, SISTEMA, FAMÍLIA ou LINHA do produto."""
        return {"CATEGORIA": self.categoria_bap, "SISTEMA": self.sistema,
                "FAMÍLIA": self.familia, "LINHA": self.linha}[nome](cod)

    def uteis(self, a, b):
        return bd.dias_uteis_entre(a, b, self.fer)

    def corridos(self, a, b):
        """(22/10) SLA de entrega: dias CORRIDOS do pedido ate a data de
        entrega que a assistente lancou (sabado, domingo e feriado contam).
        Dia util so vale para a DT. PREVISTA."""
        if not a or not b:
            return None
        return max((b - a).days, 0)

    def mais_uteis(self, d, n):
        return bd.somar_uteis(d, n, self.fer) if d else None

    def sla(self) -> dict:
        """(10/10) o SLA de entrega cadastrado (BAP Analista › Entrega ›
        Parametros): por filial (local/frete) e por cidade."""
        if not hasattr(self, "_sla"):
            try:
                import transportadoras as tr            # noqa: PLC0415
                self._sla = tr.ler_sla(self.raiz)
            except Exception:                           # noqa: BLE001
                self._sla = {}
        return self._sla

    def texto_sla(self) -> str:
        try:
            import transportadoras as tr                # noqa: PLC0415
            return tr.texto_sla(self.sla())
        except Exception:                               # noqa: BLE001
            return (f"SLA de entrega: {bd.PRAZO_ENTREGAR} dias úteis · "
                    f"interior {bd.PRAZO_ENTREGAR_FRETE}")

    def prazo_entrega(self, cod_cliente):
        c = self.cliente(cod_cliente)
        frete = bd.e_frete(c.get("cidade"))
        if self.sla():                    # cidade > filial > a regra antiga
            import transportadoras as tr                # noqa: PLC0415
            n, _o = tr.sla_de(self.sla(), c.get("uf"), c.get("cidade"),
                              frete=frete)
            if n is not None:
                return n
        return bd.PRAZO_ENTREGAR_FRETE if frete else bd.PRAZO_ENTREGAR

    def nomes_da_equipe(self):
        try:
            import farol_ddr                            # noqa: PLC0415
            return [e[0] for e in farol_ddr.EQUIPE_INICIAL if e[3] == "SIM"]
        except Exception:                               # noqa: BLE001
            return []

    def autorizadores(self):
        return sorted({p_["nome"] for p_ in self.base["pessoas"].values()
                       if p_.get("cargo") in ("SUPERVISOR", "GERENTE")
                       and p_.get("nome")})


def _pedidos(ctx, tipo):
    """Agrupa os itens de um tipo por pedido (VEA/EXC) ou por NF (VND/DEV)."""
    grupos = defaultdict(list)
    for it in ctx.tabela["itens"]:
        if it["tipo"] != tipo:
            continue
        if tipo in ("VND", "DEV"):
            chave = (it["filial"], it["nf"], it["serie"])
        else:
            chave = (it["filial"], it["pedido"])
        grupos[chave].append(it)
    return grupos


def _desconto(itens):
    tab = sum(i["p_tab"] * i["qtd"] for i in itens if i["p_tab"] > 0)
    val = sum(i["valor"] for i in itens if i["p_tab"] > 0)
    return (1 - val / tab) * 100.0 if tab else None


# =========================================================================
# DETALHE DO PEDIDO (duplo clique numa linha que tem pedido ou nota)
# =========================================================================
SIT_ITEM = {"VND": "FATURADO", "VEA": "EM ABERTO", "EXC": "EXCLUÍDO",
            "DEV": "DEVOLUÇÃO"}


def _sem_zeros(v) -> str:
    return texto(v).lstrip("0")


def detalhe_pedido(ctx, filial="", pedido="", nf=""):
    """
    Tudo do pedido: o cabecalho (cliente, vendedor, datas, notas, condicao
    de pagamento...) e os itens com quantidade, preco de tabela, preco de
    venda, desconto e saldo de cada um. filial pode vir pelo nome (como na
    tela) ou pelo codigo. Sem pedido, acha pela nota (venda ou devolucao).
    Devolve None quando nao acha nada.
    """
    fil = texto(filial)
    filiais = {c for c, n in ctx.tabela["filiais"].items()
               if texto(n).upper() == fil.upper()} | {fil}
    if len(fil) == 8 and fil.startswith("4"):     # 40101002 -> 0101002
        filiais.add(fil[1:])
    ped, n_f = _sem_zeros(pedido), _sem_zeros(nf)
    itens = [i for i in ctx.tabela["itens"]
             if (not fil or i["filial"] in filiais)]
    achados = []
    if ped:
        achados = [i for i in itens if i["tipo"] in ("VND", "VEA", "EXC")
                   and _sem_zeros(i["pedido"]) == ped]
    if not achados and n_f:
        por_nf = [i for i in itens if i["tipo"] in ("VND", "DEV")
                  and _sem_zeros(i["nf"]) == n_f]
        vnd = [i for i in por_nf if i["tipo"] == "VND"]
        if vnd and _sem_zeros(vnd[0]["pedido"]):
            ped = _sem_zeros(vnd[0]["pedido"])
            achados = [i for i in itens if i["tipo"] in ("VND", "VEA", "EXC")
                       and i["filial"] == vnd[0]["filial"]
                       and _sem_zeros(i["pedido"]) == ped]
        else:
            achados = por_nf
    if not achados:
        return None
    i0 = achados[0]
    devolucao = all(i["tipo"] == "DEV" for i in achados)
    cli = ctx.cliente_do_pedido(i0["filial"], i0["cliente"])
    notas = sorted({texto(i["nf"]).lstrip("0") for i in achados if i["nf"]})
    dts_nf = sorted({i["dt_nf"] for i in achados if i["dt_nf"]})
    conds = sorted({ctx.cond(i["cond"]) for i in achados if i["cond"]})
    obs = sorted({i["obs"] for i in achados if i["obs"]})
    maxima = sorted({i["maxima"] for i in achados if i["maxima"]})
    sits = Counter(SIT_ITEM.get(i["tipo"], i["tipo"]) for i in achados)
    # (13/10) o saldo pela regra nova: o financeiro da condicao fora
    base_sp = [i for i in achados if i["tipo"] == "VND"] or [
        i for i in achados if i["tipo"] in ("VEA", "EXC")]
    sp = saldo_do_pedido(ctx, base_sp, i0["filial"], i0["pedido"]) \
        if base_sp and not devolucao else None
    f_pct = (sp or {}).get("fin_pct") or 0.0
    linhas, tons = [], []
    for i in sorted(achados, key=lambda x: (x["tipo"] != "VND", x["nf"],
                                            x["cod"])):
        tab = (i["p_tab"] * i["qtd"] if i["p_tab"] > 0 else i["valor"]) * (
            1 + f_pct / 100.0)
        venda = i["valor"]
        desc = (1 - venda / tab) * 100.0 if tab else None
        linhas.append([SIT_ITEM.get(i["tipo"], i["tipo"]),
                       texto(i["nf"]).lstrip("0"), i["cod"],
                       ctx.produto(i["cod"]) or "", i["qtd"],
                       i["p_tab"] or None, i["p_venda"] or (
                           venda / i["qtd"] if i["qtd"] else None),
                       desc, tab, venda, tab - venda, _saldo(tab, venda)])
        tons.append("alerta" if desc is not None and desc > TETO_DESCONTO
                    + 0.05 else ({"EXC": "cinza", "DEV": "alerta",
                                  "VEA": "info"}.get(i["tipo"], "")))
    soma = [sum(l[j] or 0 for l in linhas) for j in (8, 9, 10, 11)]
    d_tot = (1 - soma[1] / soma[0]) * 100.0 if soma[0] else None
    total = ["TOTAL", "", f"{len(linhas)} itens", "",
             sum(l[4] or 0 for l in linhas), None, None, d_tot] + soma
    cols = [col("SITUAÇÃO", "texto", 92), col("NF", "texto", 60),
            col("PRODUTO", "texto", 110), col("DESCRIÇÃO", "texto", 300),
            col("QTD", "num", 50), col("P. TABELA", "moeda2", 90),
            col("P. VENDA", "moeda2", 90), col("DESC. COM. %", "pct1", 80),
            col("TABELA C/ FINANC." if f_pct else "TOTAL TABELA", "moeda",
                110), col("TOTAL VENDA", "moeda", 100),
            col("DESCONTO", "moeda", 90), col("SALDO 15%", "moeda", 90)]
    # SITUACAO e NF so aparecem quando mudam de item para item (senao ja
    # estao no cabecalho)
    for j in (1, 0):
        if len({l[j] for l in linhas}) <= 1:
            cols[j] = dict(cols[j], oculta=True)
    dt_p = i0["dt_pedido"]
    campos = [
        ("Cliente", ctx.nome_cliente(i0["cliente"], i0["filial"])),
        ("Cidade", " / ".join(x for x in (cli.get("cidade", ""),
                                           cli.get("uf", "")) if x)),
        ("Vendedor", ctx.vendedor(i0["vend"])),
        ("Supervisor", ctx.supervisor_de(i0["vend"])),
        ("Filial", ctx.filial(i0["filial"])),
        ("Data do pedido", (f"{dt_p:%d/%m/%Y}" if dt_p else "—")
         + (f"  {i0['hora']}" if i0.get("hora") else "")),
        ("Nota fiscal", ", ".join(notas) or "—"),
        ("Data da nota", ", ".join(f"{d:%d/%m/%Y}" for d in dts_nf) or "—"),
        ("Prazo de pagamento", (", ".join(conds) or "—") + (
            f" · financeiro {'+' if f_pct > 0 else '−'}"
            f"{br(abs(f_pct), 2)}%" if f_pct else "")),
        ("Situação", " · ".join(f"{k} {v}" if len(sits) > 1 else k
                                for k, v in sits.items())),
    ]
    if maxima:
        campos.append(("Pedido Máxima", ", ".join(maxima)))
    if dt_p and dts_nf and not devolucao:
        campos.append(("Dias úteis até faturar", br(ctx.uteis(dt_p, dts_nf[0]))))
    if obs:
        campos.append(("Observação", " · ".join(obs)[:300]))
    kpis = [kpi("Itens", br(len(linhas)), "neutro",
                f"{br(sum(l[4] or 0 for l in linhas))} unidades"),
            kpi("Total tabela", moeda(sp["tab"] if sp else soma[0]),
                "neutro", (f"financeiro {moeda(-sp['fin'])}"
                           if sp and sp["fin"] else "")),
            kpi("Total venda", moeda(soma[1]), "neutro"),
            kpi("Desconto comercial", "—" if d_tot is None
                else f"{br(d_tot, 1)}%",
                "alerta" if (d_tot or 0) > TETO_DESCONTO + TOLERANCIA_TETO
                else "ok", moeda(soma[2]) + (
                    f" + financeiro {br(abs(f_pct), 1)}%" if f_pct < 0
                    else "")),
            kpi("Saldo 15%", moeda(soma[3]),
                "ok" if soma[3] >= -0.5 else "alerta",
                "dentro do teto" if soma[3] >= -0.5 else "acima do teto")]
    if sp and sp.get("frete") is not None:       # (16/10)
        kpis.append(kpi("Saldo do frete", moeda(sp["frete"]),
                        "ok" if sp["frete"] >= -0.005 else "alerta",
                        f"frete real {moeda(sp['frete_real'])} · "
                        f"{br(pct_frete_cheio(ctx), 0)}% = "
                        f"{moeda(sp['frete_cheio'])}"))
    titulo = (f"Devolução NF {', '.join(notas)}" if devolucao
              else f"Pedido {texto(i0['pedido']) or ped}")
    aut = None
    if sp and texto(i0.get("pedido")):     # (13/10) a autorizacao, aqui
        precisa = sp["situacao"] != SIT_DENTRO
        aut = {"chave": chave_pedido(i0["filial"], i0["pedido"]),
               "codigo": sp["codigo"], "por": sp["por"],
               "precisa": precisa, "grave": sp["grave"],
               "aviso": ("Acima de 15% sem autorização — informe quem "
                         "autorizou" if sp["grave"] else
                         f"Acima de 15% · {sp['situacao'].lower()}"
                         if precisa else "")}
    return {"titulo": titulo, "subtitulo": f"{ctx.filial(i0['filial'])} · "
            f"{ctx.nome_cliente(i0['cliente'], i0['filial'])}", "campos": campos,
            "kpis": kpis, "colunas": cols, "linhas": linhas, "tons": tons,
            "total": total, "autorizacao": aut}


def _colunas_do_pedido(t):
    """As colunas que localizam o pedido numa tabela (FILIAL + PEDIDO e/ou
    NF), ou None se a tabela nao tem pedido."""
    nomes = [(c["nome"], c.get("tipo", "texto")) for c in t["colunas"]]

    def ix(*opcoes):
        return next((j for j, (n, tp) in enumerate(nomes)
                     if n in opcoes and tp == "texto"), None)
    pedido, nf = ix("PEDIDO"), ix("NF", "NF DEV.")
    if pedido is None and nf is None:
        return None
    return {"filial": ix("FILIAL"), "pedido": pedido, "nf": nf}


def _entregas_por_nf(ctx):
    saida = {}
    for e in ctx.posvenda.get("entregas", []):
        saida[(texto(e.get("filial")), texto(e.get("nf")).lstrip("0"))] = e
    return saida


# =========================================================================
# PRE-VENDA E FATURAMENTO
# =========================================================================
def pedidos_em_aberto(ctx):
    r = novo("pv_abertos", PRE, "Pedidos em aberto",
             f"Prazo de faturamento: {bd.PRAZO_FATURAR} dias úteis",
             "TABELA_BAP › ftPedidos (VEA) + limite do cliente (dClientesBap)")
    hoje = ctx.hoje
    linhas, tons, faltas, tons_f = [], [], [], []
    for (fil, ped), itens in sorted(_pedidos(ctx, "VEA").items(),
                                    key=lambda kv: kv[1][0]["dt_pedido"] or hoje):
        i0 = itens[0]
        cod = i0["cliente"]
        cli = ctx.cliente_do_pedido(fil, cod)               # RN-GER-019
        cred = ctx.credito_do_pedido(fil, cod)
        if any(fora_da_base(i.get("razao")) for i in itens):     # RN-GER-013
            cli = dict(cli, nome=NOME_FORA_DA_BASE, fantasia="", uf="",
                       cidade="")
        valor = sum(i["valor"] for i in itens)
        dtp = i0["dt_pedido"]
        prazo = ctx.mais_uteis(dtp, bd.PRAZO_FATURAR)
        dias = ctx.uteis(dtp, hoje)
        if prazo and hoje > prazo:
            sit, tom = "ATRASADO", "alerta"
        elif prazo and hoje == prazo:
            sit, tom = "VENCE HOJE", "atencao"
        else:
            sit, tom = "NO PRAZO", ""
        apurado = analise_credito(cred, valor) != CREDITO_NAO_APURADO
        saldo = cred.get("saldo", 0.0) if apurado else None
        atraso = cred.get("atraso_valor", 0.0) if apurado else None
        if not apurado:
            credito = CREDITO_NAO_APURADO.upper()          # RN-GER-019
        elif atraso > 0:
            credito = "CLIENTE EM ATRASO"
        elif saldo < valor:
            credito = "SEM LIMITE"
        else:
            credito = "OK"
        if credito != "OK":
            tom = tom or "atencao"
        falt = [i for i in itens if i["qtd_at"] < i["qtd"]]
        pct_at = next((i["pct_at"] for i in itens if i["pct_at"] is not None),
                      None)
        tab = sum(i["p_tab"] * i["qtd"] for i in itens if i["p_tab"] > 0)
        linhas.append([sit, ped, ctx.filial(fil), dtp, i0["hora"], dias, prazo,
                       ctx.nome_cliente(cod, fil), cli.get("cidade", ""),
                       cli.get("uf", ""), cli.get("segmento", ""),
                       ctx.vendedor(i0["vend"]), ctx.cond(i0["cond"]), valor,
                       desconto_comercial(ctx, itens), pct_at, len(itens),
                       len(falt), saldo, atraso, credito, i0["maxima"],
                       {"tabela": tab, "base": sum(
                           base_do_item(ctx, i)[0] for i in itens),
                        "dcom": sum(base_do_item(ctx, i)[1] for i in itens)}])
        tons.append(tom)
        for i in falt:
            faltas.append([ped, ctx.filial(fil),
                           ctx.nome_cliente(cod, fil), i["cod"],
                           ctx.produto(i["cod"]), i["qtd"], i["qtd_at"],
                           i["qtd"] - i["qtd_at"],
                           (i["qtd"] - i["qtd_at"]) * i["p_venda"],
                           i["est_disp"]])
            tons_f.append("alerta" if i["qtd_at"] == 0 else "atencao")

    def cartoes(ls):
        n = len(ls)
        total = sum(l[13] for l in ls)
        atr = [l for l in ls if l[0] == "ATRASADO"]
        cred = sum(1 for l in ls if l[20] != "OK")
        at = sum(l[13] * (l[15] or 0) / 100.0 for l in ls)
        base = sum(l[22]["base"] for l in ls)
        dcom = sum(l[22]["dcom"] for l in ls)
        falt = sum(l[17] for l in ls)
        return [
            kpi("Pedidos em aberto", br(n), "neutro", moeda(total)),
            kpi("Atrasados", br(len(atr)), "alerta" if atr else "ok",
                moeda(sum(l[13] for l in atr)) if atr else "nenhum fora do prazo"),
            kpi("Crédito a resolver", br(cred), "atencao" if cred else "ok",
                ""),
            kpi("% atendido", p(pct_de(at, total)), "info",
                ""),
            kpi("Itens faltantes", br(falt), "alerta" if falt else "ok",
                ""),
            kpi("Desconto comercial", p(pct_de(dcom, base)), "neutro",
                "sem o financeiro"),
        ]
    r["kpis"] = cartoes(linhas)
    r["tabelas"].append(tabela(
        "Pedidos em aberto",
        [col("SITUAÇÃO", "texto", 95), col("PEDIDO", "texto", 70),
         col("FILIAL", "texto", 95), col("DATA", "data"),
         col("HORA", "texto", 65), col("DIAS ÚTEIS", "int"),
         col("FATURAR ATÉ", "data"), col("CLIENTE", "texto", 230),
         col("CIDADE", "texto", 120), col("UF", "texto", 40),
         col("SEGMENTO", "texto", 140), col("VENDEDOR", "texto", 190),
         col("CONDIÇÃO", "texto", 130), col("VALOR", "moeda"),
         col("DESC. %", "pct1"), col("% ATENDIDO", "pct"),
         col("ITENS", "int", 55), col("FALTANTES", "int", 75),
         col("LIMITE DISP.", "moeda"), col("EM ATRASO", "moeda"),
         col("CRÉDITO", "texto", 130), col("PED. MÁXIMA", "texto", 85)],
        linhas, tons, filtros=("SITUAÇÃO", "FILIAL", "VENDEDOR", "CRÉDITO",
                               "UF"), kpis_de=cartoes))
    r["tabelas"].append(tabela(
        "Itens faltantes",
        [col("PEDIDO", "texto", 70), col("FILIAL", "texto", 95),
         col("CLIENTE", "texto", 220), col("PRODUTO", "texto", 130),
         col("DESCRIÇÃO", "texto", 260), col("PEDIDO", "num"),
         col("ATENDIDO", "num"), col("FALTA", "num"),
         col("VALOR FALTANTE", "moeda"), col("ESTOQUE DISP.", "num")],
        faltas, tons_f, filtros=("FILIAL", "PRODUTO"),
        kpis_de=lambda ls: [
            kpi("Itens faltantes", br(len(ls)), "alerta" if ls else "ok"),
            kpi("Pedidos com falta", br(len({l[0] for l in ls})), "atencao"),
            kpi("Valor faltante", moeda(sum(l[8] for l in ls)), "alerta"),
            kpi("Sem nenhuma unidade", br(sum(1 for l in ls if not l[6])),
                "alerta")]))
    if not linhas:
        r["avisos"].append("Nenhum pedido em aberto.")
    return r


def pedidos_faturados(ctx):
    r = novo("pv_faturados", PRE, "Pedidos faturados",
             "Últimos 3 meses",
             "TABELA_BAP › ftPedidos (VND) + ACOMPANHAMENTO_POS_VENDA")
    hoje = ctx.hoje
    meses = set(ultimos_meses(hoje, 3))
    ent = _entregas_por_nf(ctx)
    nfs_por_pedido = defaultdict(set)
    for (fil, nf, serie), itens in _pedidos(ctx, "VND").items():
        nfs_por_pedido[(fil, itens[0]["pedido"])].add(nf)
    linhas, tons = [], []
    for (fil, nf, serie), itens in _pedidos(ctx, "VND").items():
        i0 = itens[0]
        dnf = i0["dt_nf"]
        if mes_de(dnf) not in meses:
            continue
        cod = i0["cliente"]
        cli = ctx.cliente(cod)
        valor = sum(i["valor"] for i in itens)
        dtp = i0["dt_pedido"]
        dias_fat = ctx.uteis(dtp, dnf)
        fat_ok = dias_fat is not None and dias_fat <= bd.PRAZO_FATURAR
        parcial = len(nfs_por_pedido[(fil, i0["pedido"])]) > 1
        status_dev = {i["status"] for i in itens}
        e = ent.get((fil, nf.lstrip("0")))
        prazo_ent = ctx.mais_uteis(dtp, ctx.prazo_entrega(cod)) if dtp else None
        entregue = e.get("entregue_em") if e else None
        if "DEVOLUÇÃO TOTAL" in status_dev:
            st = "DEVOLVIDO"
        elif "DEVOLUÇÃO PARCIAL" in status_dev:
            st = "DEVOLVIDO PARCIAL"
        elif e:
            etapa = texto(e.get("etapa")).upper()
            if etapa == "ENTREGUE":
                st = "ENTREGUE"
            elif etapa in ("EXPEDIDA", "EM TRÂNSITO"):
                st = "EM ROTA"
            elif etapa == "OCORRÊNCIA":
                st = "OCORRÊNCIA"
            elif etapa == "CANCELADA":
                st = "CANCELADA"
            else:
                st = "PARADO" if (ctx.uteis(dnf, hoje) or 0) >= 1 else \
                    "AGUARDANDO EXPEDIÇÃO"
        elif dnf and dnf < _inicio_controle():
            st = "ENTREGUE"              # de antes do controle: concluido
        else:
            st = "SEM ACOMPANHAMENTO"
        if entregue:
            sit_ent = "NO PRAZO" if prazo_ent and entregue <= prazo_ent \
                else "COM ATRASO"
        elif st in ("PARADO", "EM ROTA", "AGUARDANDO EXPEDIÇÃO", "OCORRÊNCIA"):
            sit_ent = "ATRASADA" if prazo_ent and hoje > prazo_ent else "NO PRAZO"
        else:
            sit_ent = ""
        tom = ""
        if st in ("DEVOLVIDO", "DEVOLVIDO PARCIAL", "OCORRÊNCIA") or \
                sit_ent in ("ATRASADA", "COM ATRASO"):
            tom = "alerta"
        elif st == "PARADO":
            tom = "atencao"
        elif st == "ENTREGUE":
            tom = "ok"
        frete = "FRETE" if bd.e_frete(cli.get("cidade")) else "LOCAL"
        linhas.append([rotulo_mes(mes_de(dnf)), st, nf, serie, ctx.filial(fil),
                       i0["pedido"], dtp, dnf, dias_fat,
                       "SIM" if fat_ok else "NÃO", "SIM" if parcial else "",
                       ctx.nome_cliente(cod), cli.get("cidade", ""),
                       cli.get("uf", ""), frete, ctx.vendedor(i0["vend"]),
                       valor, len(itens), prazo_ent, entregue, sit_ent,
                       texto(e.get("transportadora")) if e else ""])
        tons.append(tom)
    linhas.sort(key=lambda x: (x[7] or date.min), reverse=True)

    def cartoes(ls):
        n = len(ls)
        st = Counter(l[1] for l in ls)
        ok = sum(1 for l in ls if l[9] == "SIM")
        dev = st["DEVOLVIDO"] + st["DEVOLVIDO PARCIAL"]
        return [
            kpi("Notas", br(n), "neutro", moeda(sum(l[16] for l in ls))),
            kpi("Faturado no prazo", p(pct_de(ok, n)),
                "ok" if (pct_de(ok, n) or 0) >= 90 else "alerta",
                f"meta {bd.PRAZO_FATURAR} dias úteis"),
            kpi("Entregues", br(st["ENTREGUE"]), "ok"),
            kpi("Em rota", br(st["EM ROTA"]), "info"),
            kpi("Paradas", br(st["PARADO"]), "atencao" if st["PARADO"] else "ok",
                ""),
            kpi("Devolvidas", br(dev), "alerta" if dev else "ok",
                ""),
        ]
    r["kpis"] = cartoes([l for l in linhas
                         if l[0] == rotulo_mes(mes_de(hoje))])
    r["tabelas"].append(tabela(
        "Notas faturadas",
        [col("MÊS", "texto", 60), col("SITUAÇÃO", "texto", 170),
         col("NF", "texto", 85), col("SÉRIE", "texto", 45),
         col("FILIAL", "texto", 95), col("PEDIDO", "texto", 75),
         col("DATA PEDIDO", "data"), col("DATA NF", "data"),
         col("DIAS P/ FATURAR", "int", 100), col("NO PRAZO?", "texto", 75),
         col("PARCIAL", "texto", 60), col("CLIENTE", "texto", 230),
         col("CIDADE", "texto", 120), col("UF", "texto", 40),
         col("LOCAL/FRETE", "texto", 85), col("VENDEDOR", "texto", 190),
         col("VALOR", "moeda"), col("ITENS", "int", 55),
         col("ENTREGAR ATÉ", "data"), col("ENTREGUE EM", "data"),
         col("ENTREGA", "texto", 90), col("TRANSPORTADORA", "texto", 140)],
        linhas, tons,
        filtros=({"coluna": "MÊS", "padrao": rotulo_mes(mes_de(hoje))},
                 "SITUAÇÃO", "FILIAL", "VENDEDOR", "LOCAL/FRETE"),
        kpis_de=cartoes))
    if not ctx.posvenda.get("existe"):
        r["avisos"].append("Acompanhamento do pós-venda ainda não gerado.")
    r["editar"] = "RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx"
    return r


def pedidos_excluidos(ctx):
    r = novo("pv_excluidos", PRE, "Pedidos excluídos",
             "Últimos 12 meses",
             "TABELA_BAP › ftPedidos (EXC)")
    hoje = ctx.hoje
    linhas = []
    por_mes = defaultdict(lambda: [0, 0.0])
    for (fil, ped), itens in _pedidos(ctx, "EXC").items():
        i0 = itens[0]
        valor = sum(i["valor"] for i in itens)
        m = mes_de(i0["dt_pedido"])
        por_mes[m][0] += 1
        por_mes[m][1] += valor
        cli = ctx.cliente_do_pedido(fil, i0["cliente"])     # RN-GER-019
        linhas.append([rotulo_mes(m), ped, ctx.filial(fil), i0["dt_pedido"],
                       i0["hora"], ctx.nome_cliente(i0["cliente"], fil),
                       cli.get("cidade", ""), cli.get("uf", ""),
                       ctx.vendedor(i0["vend"]), ctx.cond(i0["cond"]), valor,
                       len(itens), desconto_comercial(ctx, itens),
                       i0["maxima"]])
    linhas.sort(key=lambda x: (x[3] or date.min), reverse=True)
    # pedidos digitados por mes = faturados + em aberto + excluidos
    digitados = defaultdict(set)
    for i in ctx.tabela["itens"]:
        if i["tipo"] in ("VND", "VEA", "EXC"):
            digitados[rotulo_mes(mes_de(i["dt_pedido"]))].add(
                (i["filial"], i["pedido"]))

    def cartoes(ls):
        meses_vis = {l[0] for l in ls}
        dig = sum(len(digitados[m]) for m in meses_vis)
        vend = Counter(l[8] for l in ls)
        return [
            kpi("Pedidos excluídos", br(len(ls)), "alerta" if ls else "ok",
                moeda(sum(l[10] for l in ls))),
            kpi("% dos pedidos digitados", p(pct_de(len(ls), dig)), "neutro",
                f"de {br(dig)} digitados"),
            kpi("Clientes", br(len({texto(l[5]).split(" - ")[0]
                                    for l in ls})), "neutro"),   # por codigo
            kpi("Vendedor com mais exclusões",
                vend.most_common(1)[0][0].split(" - ")[-1][:22] if vend else "—",
                "atencao" if vend else "neutro",
                f"{vend.most_common(1)[0][1]} pedido(s)" if vend else ""),
        ]
    r["kpis"] = cartoes([l for l in linhas if l[0] == rotulo_mes(mes_de(hoje))])
    meses = ultimos_meses(hoje, 12)
    r["graficos"].append({"titulo": "Pedidos excluídos por mês",
                          "rotulos": [rotulo_mes(x) for x in meses],
                          "series": [{"nome": "pedidos", "cor": VERMELHO,
                                      "valores": [por_mes[x][0] for x in meses]}],
                          "formato": "num"})
    r["tabelas"].append(tabela(
        "Pedidos excluídos",
        [col("MÊS", "texto", 60), col("PEDIDO", "texto", 70),
         col("FILIAL", "texto", 95), col("DATA", "data"),
         col("HORA", "texto", 65), col("CLIENTE", "texto", 230),
         col("CIDADE", "texto", 120), col("UF", "texto", 40),
         col("VENDEDOR", "texto", 190), col("CONDIÇÃO", "texto", 130),
         col("VALOR", "moeda"), col("ITENS", "int", 55),
         col("DESC. %", "pct1"), col("PED. MÁXIMA", "texto", 85)],
        linhas,
        filtros=({"coluna": "MÊS", "padrao": rotulo_mes(mes_de(hoje))},
                 "FILIAL", "VENDEDOR", "UF"),
        kpis_de=cartoes))
    for titulo, i_chave, larg in (("Por vendedor", 8, 260),
                                  ("Por cliente", 5, 280)):
        g = defaultdict(lambda: [0, 0.0, set()])
        for l in linhas:
            g[(l[0], l[i_chave])][0] += 1
            g[(l[0], l[i_chave])][1] += l[10]
        r["tabelas"].append(tabela(
            titulo,
            [col("MÊS", "texto", 60), col(titulo[4:].upper(), "texto", larg),
             col("PEDIDOS", "int"), col("VALOR", "moeda")],
            sorted([[k[0], k[1], v[0], v[1]] for k, v in g.items()],
                   key=lambda x: (x[0] != rotulo_mes(mes_de(hoje)), -x[2])),
            filtros=({"coluna": "MÊS", "padrao": rotulo_mes(mes_de(hoje))},),
            kpis_de=lambda ls: [
                kpi("Pedidos excluídos", br(sum(l[2] for l in ls)), "alerta"),
                kpi("Valor", moeda(sum(l[3] for l in ls)), "neutro")]))
    return r


SITUACOES_PEDIDO = ["EM ABERTO", "FATURADO", "ENTREGUE", "DEVOLVIDO",
                    "CANCELADO", "EXCLUÍDO"]


CREDITO_SEM = "Sem Limite"
CREDITO_PARCIAL = "Com Limite Parcial"
CREDITO_ATRASO = "Com Limite, mas em Atraso"
CREDITO_OK = "Com Limite"
CREDITO_NAO_APURADO = "Saldo Não Apurado"     # RN-GER-019: loja sem saldo


def analise_credito(cli: dict, valor: float) -> str:
    """A ANALISE CREDITO do Farol de Pedidos (a mesma leitura do BI):
    sem limite -> o disponivel nao cobre o pedido -> tem atraso -> ok.
    RN-GER-019: credito_apurado False -> CREDITO_NAO_APURADO (fonte:
    docs/produto/03-regras.md)."""
    if cli.get("credito_apurado") is False:
        return CREDITO_NAO_APURADO
    if (cli.get("limite") or 0) <= 0:
        return CREDITO_SEM
    if (cli.get("saldo") or 0) < valor:
        return CREDITO_PARCIAL
    if (cli.get("atraso_valor") or 0) > 0:
        return CREDITO_ATRASO
    return CREDITO_OK


def _tabela_cond(it):
    """O preco de TABELA ja com o acrescimo (ou desconto) financeiro da
    condicao de pagamento - ACRES_FIN do ftPedidos (a vista -1,71%,
    a prazo +1,32%...). E sobre ele que o BI calcula o % DESC."""
    tab = it["p_tab"] * it["qtd"] if it["p_tab"] > 0 else it["valor"]
    return tab * (1 + (it.get("acres") or 0.0) / 100.0)


# (08/10) Farol de Pedidos: SLA e % ATENDIDO em destaque na tela. O SLA
# (dias uteis desde o pedido) pintado pela regra do prazo de faturar:
# ate 1 dia verde (folga), no prazo (2) amarelo (ultimo dia), passou do
# prazo vermelho claro, mais de 4 dias vermelho cheio (o cartao "> 4
# dias"). O % ATENDIDO vira barra: 100% verde (pode faturar), de 50% a 99%
# amarelo (parcial), abaixo de 50% vermelho.
def CHIP_SLA():                                         # noqa: N802
    return [(bd.PRAZO_FATURAR - 1, *_VERD),
            (bd.PRAZO_FATURAR, *_AMAR),
            (4, *_VERM),
            (None, "#B42318", "#FFFFFF")]


BARRA_ATENDIDO = {"max": 100, "faixas": [(49.99, "#D9534F", "#B42318"),
                                         (99.98, "#E0A526", "#8A5A00"),
                                         (None, "#59BA61", "#2F7D32")]}


def _edicao_autorizacao(i_chave, i_cod, i_por):
    """(13/10) A edicao do CODIGO DE AUTORIZACAO e de QUEM AUTORIZOU: duplo
    clique nessas colunas (no resto da linha, o pedido abre)."""
    return {"arquivo": "RELATORIOS/_AUTORIZACOES", "aba": "",
            "modulo": "autorizacoes", "chave": i_chave,
            "so_colunas": [i_cod, i_por],
            "campos": [{"campo": "codigo", "rotulo": "CÓD. AUTORIZAÇÃO",
                        "opcoes": [], "livre": True, "mantem_caixa": True,
                        "col": i_cod},
                       {"campo": "por", "rotulo": "AUTORIZADO POR",
                        "opcoes": list(QUEM_AUTORIZA), "col": i_por}]}


# (T-0023 v2, contrato 10.9.1) O teto do texto de cada campo editavel pela
# web, um lugar so: o nucleo poe no "max" da edicao e o robo confere contra
# o mesmo numero. Sem entrada = 60 caracteres (o padrao da web).
TETO_TEXTO_LONGO = 600
MAX_TEXTO_PADRAO = 60
MAX_TEXTO_EDICAO = {("garantias", c): TETO_TEXTO_LONGO
                    for c in ("reclamacao", "pendencias", "retorno_cliente",
                              "observacao")}
MAX_TEXTO_EDICAO[("garantias", "ticket")] = 40       # RD-0136

# RN-POS-005 e a garantia nova: UMA regra, para a janela do PC, a edicao da
# web e o robo (RD-0139).
PADRAO_NOVA_GARANTIA = {"status": "ABERTO", "resultado": "PENDENTE"}
ORIGEM_GARANTIA_FAROL = "FAROL DE GARANTIAS"


def prazo_padrao_txt(dt_solicitacao_txt, fer=()) -> str:
    """RN-POS-005: a DT. FECHAMENTO padrao (solicitacao + 15 dias uteis,
    hoje fora) em dd/mm/aaaa; "" sem solicitacao valida."""
    import garantias as gm                              # noqa: PLC0415
    d = gm.prazo_padrao(gm.data(dt_solicitacao_txt), fer)
    return f"{d:%d/%m/%Y}" if d else ""


def campos_garantia_a_gravar(campos, fer=(), novo=False) -> dict:
    """RN-POS-005: o prazo igual ao padrao fica em branco (acompanha a
    solicitacao); a garantia nova leva a origem do farol. Funcao pura."""
    saida = dict(campos)
    if saida.get("dt_prazo") and saida["dt_prazo"] == prazo_padrao_txt(
            saida.get("dt_solicitacao"), fer):
        saida["dt_prazo"] = ""
    if novo:
        saida["origem"] = ORIGEM_GARANTIA_FAROL
    return saida

# (T-0023 v2, 10.9.3) os 14 campos da Garantia que a web edita, na ordem do
# contrato: (campo, rotulo, tipo, coluna da tabela). O contato do cliente
# NAO entra (P2 A: so se edita no PC).
CAMPOS_EDICAO_GARANTIA = (
    ("ticket", "TICKET", "texto", "TICKET"),
    ("dt_solicitacao", "DT. SOLICITAÇÃO", "data", "DT. SOLICITAÇÃO"),
    ("dt_prazo", "DT. FECHAMENTO (PRAZO)", "data", "DT. FECHAMENTO"),
    ("dt_retorno", "DT. RETORNO", "data", "DT. RETORNO"),
    ("status", "STATUS", "lista", "STATUS"),
    ("resultado", "RESULTADO ANÁLISE", "lista", "RESULTADO ANÁLISE"),
    ("cod_cliente", "CÓD. CLIENTE", "texto", "CÓD. CLIENTE"),
    ("cod_produto", "CÓD. PRODUTO", "texto", "CÓD. PRODUTO"),
    ("descricao", "DESCRIÇÃO PRODUTO", "texto", "DESCRIÇÃO PRODUTO"),
    ("qtd", "QTD", "texto", "QTD"),
    ("reclamacao", "RECLAMAÇÃO", "longo", "RECLAMAÇÃO"),
    ("pendencias", "PENDÊNCIAS", "longo", "PENDÊNCIAS"),
    ("retorno_cliente", "RETORNO DO CLIENTE", "longo", "RETORNO DO CLIENTE"),
    ("observacao", "OBSERVAÇÃO", "longo", "OBSERVAÇÃO"))


def max_texto_edicao(modulo, campo) -> int:
    """O teto (1 a 600) do texto do campo; sem entrada, 60."""
    return MAX_TEXTO_EDICAO.get((modulo, campo), MAX_TEXTO_PADRAO)


def edicao_garantia(i_col, status, resultados, ticket_padrao="") -> dict:
    """(T-0023 v2, RN-GER-012) A `edicao` da tabela Garantias, a que o robo
    traduz para a web. Funcao pura: `i_col` = {nome da coluna: indice},
    `status`/`resultados` = as listas do garantias.py, `ticket_padrao` =
    garantias.novo_ticket (a web nao calcula numero). A linha nova nasce
    com ABERTO, PENDENTE e a data de hoje ("@hoje"). O contato do cliente
    fica fora (dado pessoal)."""
    listas = {"status": list(status), "resultado": list(resultados)}
    padroes = {**PADRAO_NOVA_GARANTIA, "ticket": ticket_padrao,
               "dt_solicitacao": "@hoje"}
    campos = []
    for campo, rotulo, tipo, coluna in CAMPOS_EDICAO_GARANTIA:
        c = {"campo": campo, "rotulo": rotulo, "opcoes": [],
             "col": i_col[coluna]}
        if tipo == "lista":
            c["opcoes"] = listas[campo]
        elif tipo == "data":
            c["data"] = True                 # sem opcoes = data livre
        else:
            c["livre"] = True
            c["mantem_caixa"] = tipo == "longo" or campo == "descricao"
        if tipo == "longo":
            c["multilinha"] = True
        if max_texto_edicao("garantias", campo) != MAX_TEXTO_PADRAO:
            c["max"] = max_texto_edicao("garantias", campo)   # RD-0136
        if padroes.get(campo):
            c["padrao"] = padroes[campo]
        campos.append(c)
    return {"arquivo": "RELATORIOS/_GARANTIAS", "aba": "",
            "modulo": "garantias", "acao": "Editar", "chave": i_col["TICKET"],
            "novo_web": {"rotulo": "Nova garantia"}, "campos": campos}


def farol_pedidos(ctx):
    """
    Um farol so para o pedido inteiro: EM ABERTO, FATURADO, EXCLUIDO e - pelo
    acompanhamento do pos-venda - ENTREGUE, DEVOLVIDO e CANCELADO.
    As colunas seguem a ordem do Farol de Pedidos do Power BI.
    """
    hoje = ctx.hoje
    m_hoje = rotulo_mes(mes_de(hoje))
    r = novo("pv_pedidos", PRE, "Farol de Pedidos",
             f"Faturar em {bd.PRAZO_FATURAR} dias úteis",
             "TABELA_BAP › ftPedidos + ACOMPANHAMENTO_POS_VENDA + "
             "SOLICITACAO_BAP")
    capa(r, ctx, anos_dos_dados(ctx))
    ent = _entregas_por_nf(ctx)
    dev_acomp = {texto(x.get("nf_origem")).lstrip("0")
                 for x in ctx.posvenda.get("devolucoes", [])
                 if texto(x.get("nf_origem"))}
    inicio = _inicio_controle()
    meses12 = set(ultimos_meses(hoje, 12))
    linhas, tons = [], []
    I_DATA, I_PED, I_MAX, I_COD, I_RAZ, I_FAN, I_UF, I_CID, I_LIM, I_DISP, \
        I_ATR, I_VOL, I_TAB, I_TABA, I_VEN, I_DESC, I_SLA, I_ATEND, \
        I_CRED, I_COND, I_AUTC, I_AUTP, I_SIT, I_MES, I_FIL, I_NF, I_DNF, \
        I_ATE, I_PRAZO, I_VEND, I_ENT, I_PROD, I_CHV = range(33)

    def linha(sit, mes_r, fil, ped, nf, dtp, dnf, sla, ate, cod, vend,
              itens, cred=None, entregue=None, prazo_txt="", sp=None):
        """(13/10) sp: o saldo do pedido pela regra nova - R$ TABELA ja
        com o financeiro da condicao e o % DESC. COMERCIAL (o do saldo),
        mais a autorizacao (codigo e quem autorizou)."""
        cli = ctx.cliente_do_pedido(fil, cod)               # RN-GER-019
        ctab = ctx.credito_do_pedido(fil, cod)
        if any(fora_da_base(i.get("razao")) for i in itens):     # RN-GER-013
            cli = {"nome": NOME_FORA_DA_BASE, "fantasia": "", "uf": "",
                   "cidade": ""}
            ctab = {}
        valor = sum(i["valor"] for i in itens)
        tab = sum(i["p_tab"] * i["qtd"] if i["p_tab"] > 0 else i["valor"]
                  for i in itens)
        cidade = cli.get("cidade", "")
        # (14/10) AUDITORIA: a BASE so dos itens da linha (o pedido que
        # saiu em 3 notas levava a base do pedido inteiro em cada nota)
        tab_c = sum(base_do_item(ctx, i)[0] for i in itens) if sp \
            else sum(_tabela_cond(i) for i in itens)
        pcts = [i["pct_at"] for i in itens if i.get("pct_at") is not None]
        i0 = itens[0]
        return [dtp, ped, i0.get("maxima", ""), cod,
                cli.get("nome") or i0.get("razao", ""),
                cli.get("fantasia", ""),
                cli.get("uf", ""), cidade, ctab.get("limite"),
                ctab.get("saldo"), ctab.get("atraso_valor"),
                sum(i["qtd"] for i in itens), tab,
                tab_c, valor,
                (sp["pcom"] if sp else
                 ((1 - valor / tab_c) * 100.0 if tab_c else None)),
                sla, max(pcts) if pcts else None,
                cred if cred is not None else "", ctx.cond(i0["cond"]),
                (sp or {}).get("codigo", ""), (sp or {}).get("por", ""),
                sit, mes_r, ctx.filial(fil), nf.lstrip("0"), dnf, ate,
                prazo_txt, ctx.vendedor(vend), entregue,
                "; ".join(sorted({i["cod"] for i in itens})),
                chave_pedido(fil, ped)]
    # ---- em aberto (a carteira de agora: entra no mes atual)
    for (fil, ped), itens in _pedidos(ctx, "VEA").items():
        i0 = itens[0]
        valor = sum(i["valor"] for i in itens)
        dtp = i0["dt_pedido"]
        ate = ctx.mais_uteis(dtp, bd.PRAZO_FATURAR)
        atr = "ATRASADO" if ate and hoje > ate else (
            "VENCE HOJE" if ate and hoje == ate else "NO PRAZO")
        cred = analise_credito(ctx.credito_do_pedido(fil, i0["cliente"]),
                               valor)
        sp = saldo_do_pedido(ctx, itens, fil, ped)
        linhas.append(linha("EM ABERTO", m_hoje, fil, ped, "", dtp, None,
                            ctx.uteis(dtp, hoje), ate, i0["cliente"],
                            i0["vend"], itens, cred, prazo_txt=atr, sp=sp))
        tons.append("grave" if sp["grave"] else
                    "alerta" if atr == "ATRASADO" else
                    ("atencao" if atr == "VENCE HOJE" or cred != CREDITO_OK
                     else ""))
    # ---- excluidos
    for (fil, ped), itens in _pedidos(ctx, "EXC").items():
        i0 = itens[0]
        m = mes_de(i0["dt_pedido"])
        if m not in meses12:
            continue
        linhas.append(linha("EXCLUÍDO", rotulo_mes(m), fil, ped, "",
                            i0["dt_pedido"], None, None, None, i0["cliente"],
                            i0["vend"], itens,
                            sp=saldo_do_pedido(ctx, itens, fil, ped)))
        tons.append("")
    # ---- faturados (uma linha por nota)
    saldos_ped = saldos_dos_pedidos(ctx)
    for (fil, nf, serie), itens in _pedidos(ctx, "VND").items():
        i0 = itens[0]
        dnf = i0["dt_nf"]
        m = mes_de(dnf)
        if m not in meses12:
            continue
        dtp = i0["dt_pedido"]
        dias = ctx.uteis(dtp, dnf) if dtp else None
        e = ent.get((fil, nf.lstrip("0"))) or {}
        etapa = texto(e.get("etapa")).upper()
        status = {i["status"] for i in itens}
        entregue = bd.data_de(e.get("entregue_em"))
        if status & {"DEVOLUÇÃO TOTAL", "DEVOLUÇÃO PARCIAL"} or \
                nf.lstrip("0") in dev_acomp:
            sit = "DEVOLVIDO"
        elif etapa == "CANCELADA":
            sit = "CANCELADO"
        elif etapa == "ENTREGUE" or (not e and dnf and dnf < inicio):
            sit = "ENTREGUE"
        else:
            sit = "FATURADO"
        atr = ("FORA DO PRAZO" if dias is not None
               and dias > bd.PRAZO_FATURAR else "NO PRAZO")
        sp = saldos_ped.get((fil, i0["pedido"] or nf))
        linhas.append(linha(sit, rotulo_mes(m), fil, i0["pedido"], nf, dtp,
                            dnf, dias, None, i0["cliente"], i0["vend"], itens,
                            entregue=entregue, prazo_txt=atr, sp=sp))
        tons.append("grave" if sp and sp["grave"] and sit != "CANCELADO"
                    else {"DEVOLVIDO": "alerta", "CANCELADO": "alerta",
                          "ENTREGUE": "ok"}.get(sit, ""))
    ordem = {s_: n for n, s_ in enumerate(SITUACOES_PEDIDO)}
    juntos = sorted(zip(linhas, tons), key=lambda x: (
        ordem.get(x[0][I_SIT], 9),
        -(x[0][I_DNF] or x[0][I_DATA] or date.min).toordinal()))
    linhas = [x[0] for x in juntos]
    tons = [x[1] for x in juntos]
    # (22/10) as notas de todas as linhas, por mes: para a devolucao do
    # FATURADO real (devolucoes_da_vista)
    todas_nf = defaultdict(set)
    for l in linhas:
        if l[I_SIT] in ("FATURADO", "ENTREGUE", "DEVOLVIDO", "CANCELADO"):
            todas_nf[l[I_MES]].add((l[I_FIL], l[I_VEND]))

    def cartoes_bi(ls):
        """Os cartoes do Farol do BI (pedidos em aberto)."""
        slas = [l[I_SLA] for l in ls if l[I_SLA] is not None]
        sla = sum(slas) / len(slas) if slas else None
        prontos = sum(1 for l in ls if (l[I_ATEND] or 0) >= 99.99)
        velhos = sum(1 for l in ls if (l[I_SLA] or 0) > 4)
        return [
            kpi("SLA", br(sla, 1) if sla is not None else "—",
                "alerta" if (sla or 0) > bd.PRAZO_FATURAR else "ok",
                "dias úteis (média)"),
            kpi("Pedidos", br(len(ls)), "neutro"),
            kpi("R$", moeda(sum(l[I_VEN] for l in ls)), "neutro"),
            kpi("Faturar", br(prontos), "ok" if prontos else "neutro",
                "100% atendidos"),
            kpi("> 4 dias", br(velhos), "alerta" if velhos else "ok"),
            kpi("Volume", br(sum(l[I_VOL] or 0 for l in ls)), "neutro",
                "unidades"),
        ]

    def cartoes(ls, filtro=None):
        # RN-GER-013 (Alexandre, 26/11: "A"): os numeros sem os pedidos de
        # cliente fora da base, como a tabela do site (caixa "Ignorar" marcada)
        ls = [l for l in ls if l[I_RAZ] != NOME_FORA_DA_BASE]
        if ls and all(l[I_SIT] == "EM ABERTO" for l in ls):
            return cartoes_bi(ls)
        c = Counter(l[I_SIT] for l in ls)
        val = defaultdict(float)
        for l in ls:
            val[l[I_SIT]] += l[I_VEN]
        fat = [l for l in ls if l[I_SIT] in ("FATURADO", "ENTREGUE",
                                             "DEVOLVIDO", "CANCELADO")]
        dev_f = devolucoes_da_vista(
            ctx, {(l[I_MES], l[I_FIL], l[I_VEND]) for l in fat}, todas_nf,
            filiais_do_recorte(fat, filtro, I_FIL, (I_VEND,)))
        no_prazo = sum(1 for l in fat if l[I_SLA] is not None
                       and l[I_SLA] <= bd.PRAZO_FATURAR)
        com_dias = sum(1 for l in fat if l[I_SLA] is not None)
        atr = sum(1 for l in ls if l[I_PRAZO] == "ATRASADO")
        dig = len({(l[I_FIL], l[I_PED]) for l in ls
                   if l[I_SIT] != "EM ABERTO"
                   or rotulo_no_periodo(ctx, l[I_MES])})
        return [
            kpi("Pedidos", br(dig), "neutro",
                moeda(sum(l[I_VEN] for l in ls))),
            # (22/10, Alexandre) FATURADO = o real, ja sem as devolucoes
            kpi("Faturado", moeda(sum(l[I_VEN] for l in fat) - dev_f),
                "neutro", f"{br(len(fat))} notas" + (
                    f" · devoluções {moeda(dev_f)}" if dev_f >= 0.5
                    else "")),
            kpi("Faturado no prazo", p(pct_de(no_prazo, com_dias)),
                "ok" if (pct_de(no_prazo, com_dias) or 100) >= 90 else "alerta",
                f"meta {bd.PRAZO_FATURAR} dias úteis"),
            kpi("Em aberto", br(c["EM ABERTO"]), "atencao" if atr else "neutro",
                f"{br(atr)} atrasado(s)" if atr else moeda(val["EM ABERTO"])),
            kpi("Entregues", br(c["ENTREGUE"]), "ok"),
            # (14/10) AUDITORIA: e o PEDIDO que voltou (valor do pedido); o
            # valor devolvido do mes esta no Farol de Devolucoes
            kpi("Pedidos devolvidos", br(c["DEVOLVIDO"]),
                "alerta" if c["DEVOLVIDO"] else "ok",
                f"{moeda(val['DEVOLVIDO'])} em pedidos" if c["DEVOLVIDO"]
                else ""),
            kpi("Excluídos", br(c["EXCLUÍDO"]),
                "atencao" if c["EXCLUÍDO"] else "ok",
                p(pct_de(c["EXCLUÍDO"], dig)) + " dos pedidos"
                if c["EXCLUÍDO"] else ""),
            kpi("Cancelados", br(c["CANCELADO"]),
                "alerta" if c["CANCELADO"] else "ok"),
        ]
    no_per = [l for l in linhas if rotulo_no_periodo(ctx, l[I_MES])]
    r["kpis"] = cartoes(no_per)
    # os graficos: pedidos (pela data do pedido) + por filial (como no BI)
    evs = {}
    for it in ctx.tabela["itens"]:
        if it["tipo"] in ("VND", "VEA", "EXC") and it["dt_pedido"]:
            evs.setdefault((it["filial"], it["pedido"]),
                           (it["dt_pedido"], (it["filial"], it["pedido"])))
    graficos_tempo(r, ctx, "Pedidos digitados", list(evs.values()), "num",
                   VERDE, "unicos")
    por_fil = defaultdict(lambda: {"fat": 0, "abe": 0, "sla": []})
    for l in no_per:
        f_ = por_fil[l[I_FIL]]
        if l[I_SIT] == "EM ABERTO":
            f_["abe"] += 1
        elif l[I_SIT] != "EXCLUÍDO":
            f_["fat"] += 1
        if l[I_SLA] is not None and l[I_SIT] != "EXCLUÍDO":
            f_["sla"].append(l[I_SLA])
    fils = sorted(por_fil, key=lambda k: -(por_fil[k]["fat"]
                                           + por_fil[k]["abe"]))
    if fils:
        r["graficos"].append({
            "titulo": "Por filial: faturados x em aberto",
            "rotulos": fils,
            "series": [{"nome": "Faturados", "cor": VERDE,
                        "valores": [por_fil[k]["fat"] for k in fils]},
                       {"nome": "Em aberto", "cor": VERMELHO,
                        "valores": [por_fil[k]["abe"] for k in fils]}],
            "formato": "num"})
        r["graficos"].append({
            "titulo": "Por filial: SLA médio (dias úteis)",
            "rotulos": fils, "meta": bd.PRAZO_FATURAR,
            "series": [{"nome": "SLA", "cor": AZUL, "valores": [
                round(sum(por_fil[k]["sla"]) / len(por_fil[k]["sla"]), 1)
                if por_fil[k]["sla"] else 0 for k in fils]}],
            "formato": "num"})
    cols = [col("DT. PED", "dia", 66), col("PEDIDO", "texto", 62),
            col("PED. MÁX.", "texto", 58), col("CÓD.", "texto", 58),
            col("RAZÃO SOCIAL", "texto", 190), col("FANTASIA", "texto", 150),
            col("UF", "texto", 34), col("CIDADE", "texto", 110),
            col("LIMITE", "moeda", 76), col("DISP.", "moeda", 76),
            col("ATRASO", "moeda", 70), col("VOL.", "num", 48),
            # (08/10) a tabela cheia sai da tela; a COM a condicao de
            # pagamento (a do % DESC.) passa a se chamar R$ TABELA
            col("R$ TABELA CHEIA", "moeda", 82, oculta=True),
            col("R$ TABELA", "moeda", 82),
            col("R$ VENDA", "moeda", 82),
            # (13/10) o desconto COMERCIAL (o financeiro da condicao fora)
            col("% DESC.", "pct1", 60),
            dict(col("SLA", "int", 64), chip=CHIP_SLA(), larg_fixa=64),
            dict(col("% ATENDIDO", "pct", 170), barra=BARRA_ATENDIDO,
                 larg_fixa=170),
            col("ANÁLISE CRÉDITO", "texto", 160),
            col("COND. PAGTO", "texto", 120),
            # (13/10) a autorizacao fica no PEDIDO (duplo clique); aqui so a
            # linha vermelha - as colunas so vao para o Excel/PDF
            col("CÓD. AUTORIZAÇÃO", "texto", 120, oculta=True),
            col("AUTORIZADO POR", "texto", 96, oculta=True),
            col("SITUAÇÃO", "texto", 92), col("MÊS", "texto", 58, oculta=True),
            col("FILIAL", "texto", 90), col("NF", "texto", 58),
            col("DT. NF", "dia", 66), col("FATURAR ATÉ", "dia", 80),
            col("PRAZO", "texto", 100), col("VENDEDOR", "texto", 170),
            # (23/10, Alexandre) fora da tela (fica no dado)
            col("ENTREGUE EM", "dia", 80, oculta=True),
            col("PRODUTO", "texto", 120, oculta=True),
            col("CHAVE", "texto", 80, oculta=True)]
    # (23/10, Alexandre) a ORDEM da tela: FATURAR ATE ao lado da DT. PED;
    # NF e DT. NF no fim. A linha e os indices I_ andam juntos (as
    # funcoes de cartao e recorte leem os I_ na hora)
    _vis = ["DT. PED", "FATURAR ATÉ", "PEDIDO", "PED. MÁX.", "CÓD.",
            "RAZÃO SOCIAL", "FANTASIA", "UF", "CIDADE", "LIMITE", "DISP.",
            "ATRASO", "VOL.", "R$ TABELA", "R$ VENDA", "% DESC.", "SLA",
            "% ATENDIDO", "ANÁLISE CRÉDITO", "COND. PAGTO", "SITUAÇÃO",
            "FILIAL", "PRAZO", "VENDEDOR", "NF", "DT. NF"]
    _nomes = [c_["nome"] for c_ in cols]
    perm = [_nomes.index(n_) for n_ in _vis] + [
        j for j, n_ in enumerate(_nomes) if n_ not in _vis]
    cols = [cols[j] for j in perm]
    for l in linhas:
        l[:] = [l[j] for j in perm] + l[len(perm):]
    (I_DATA, I_PED, I_MAX, I_COD, I_RAZ, I_FAN, I_UF, I_CID, I_LIM, I_DISP,
     I_ATR, I_VOL, I_TAB, I_TABA, I_VEN, I_DESC, I_SLA, I_ATEND, I_CRED,
     I_COND, I_AUTC, I_AUTP, I_SIT, I_MES, I_FIL, I_NF, I_DNF, I_ATE,
     I_PRAZO, I_VEND, I_ENT, I_PROD, I_CHV) = [perm.index(k)
                                              for k in range(33)]
    r["tabelas"].append(tabela(
        "Pedidos", cols, linhas, tons,
        # (08/10) o MES segue o Mes/Ano de cima (sem caixa na aba)
        filtros=({"coluna": "MÊS", "padrao": mes_escolhido(ctx),
                  "oculto": True},
                 {"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}, "CIDADE",
                 "VENDEDOR", {"coluna": "PRODUTO", "multi": True}),
        kpis_de=cartoes,
        recortes=[("Faturar (100% atendidos)",
                   lambda l: (l[I_ATEND] or 0) >= 99.99),
                  ("Mais de 4 dias", lambda l: (l[I_SLA] or 0) > 4),
                  ("Crédito a analisar", lambda l: l[I_SIT] == "EM ABERTO"
                   and l[I_CRED] != CREDITO_OK),
                  ("Acima de 15% sem autorização",
                   lambda l: l[I_SIT] != "EXCLUÍDO" and (l[I_DESC] or 0) >
                   TETO_DESCONTO + TOLERANCIA_TETO and not l[I_AUTP])]))
    # (08/10) sem a cor de fundo por linha: branco e cinza bem claro; o
    # destaque fica no SLA e no % ATENDIDO
    r["tabelas"][-1]["zebra"] = True
    # (08/10) a tabela dos pedidos maior: sem STATUS, RECORTE e BUSCAR,
    # letra menor (compacta) e a divisoria abrindo em 68% para ela
    r["tabelas"][-1].update({"filtros_fora": ["STATUS"], "enxuta": True,
                             "compacta": True, "divisao": 0.6})
    # (09/10) os numeros de cima numa faixa fina: mais altura para as
    # tabelas (pedidos e os 3 quadros de baixo)
    r["kpis_faixa"] = True
    # (06/10) ANALITICO PRODUTO, GERAR SEPARACAO CD e GERAR REVERSA DE
    # LOJAS na MESMA aba dos Pedidos, embaixo: mostram so o que e dos
    # pedidos que estao na tela (o filtro de cima vale para as tres)
    juntas = [_analitico_produto(ctx)] + _solicitacoes_pendentes(ctx)
    # lado a lado, como no Overview (BI): separacao | reversa | analitico;
    # "mostrar": as colunas que cabem no quadro (o PDF/Excel leva todas)
    sol_vis = ["DATA", "PEDIDOS", "CÓD. PROD.", "QTD", "COLETAR EM",
               "FILIAL DEST."]
    larg_sol = {"DATA": 46, "CIDADE": 72, "PEDIDOS": 58, "CÓD. PROD.": 96,
                "COLETAR EM": 70, "FILIAL DEST.": 70, "QTD": 38}
    r["tabelas"][-1]["juntas"] = [
        {"tabela": juntas[1], "liga": ("PEDIDOS", "PEDIDO", "|"),
         "titulo": "Gerar ID de separação CD", "mostrar": sol_vis,
         "larguras": larg_sol, "peso": 6},
        {"tabela": juntas[2], "liga": ("PEDIDOS", "PEDIDO", "|"),
         "titulo": "Gerar reversa de lojas", "mostrar": sol_vis,
         "larguras": larg_sol, "peso": 6},
        {"tabela": juntas[0], "liga": ("PEDIDO", "PEDIDO", None),
         "titulo": "Analítico por pedido",
         "mostrar": ["PEDIDO", "DATA", "CIDADE", "FILIAL", "FORN.",
                     "CÓD. PROD.", "QTD", "EST. FRW", "ATENDIDO", "FALTA"],
         "peso": 9}]
    # (09/10) a aba SOLICITACAO BAP: o arquivo de solicitacao com as abas
    # dele e a troca de loja de coleta (montada pela janela, sob demanda)
    r["tabelas"].append({"titulo": "Solicitação BAP", "solicitacao_bap": True,
                         "colunas": [], "linhas": [], "tons": [],
                         "filtros": [], "total": None, "kpis_de": None,
                         "recortes": [], "edicao": None})
    r["editar"] = "RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx"
    return r


def _fornecedor(ctx, cod) -> str:
    f_ = ctx.tabela.get("fornecedores", {}).get(cod, "")
    return f_.split(" - ")[0].strip() if f_ else ""


def _analitico_produto(ctx):
    """
    ANALITICO PRODUTO: cada item dos pedidos EM ABERTO com o estoque da FRW.
    O ATENDIDO e o do ftPedidos (QTD_ATENDIDA), que segue a fila por data
    do pedido (ORDEM_FIFO): o estoque que entrou cobre primeiro o pedido
    mais antigo daquela filial+produto; o mais novo so leva o que sobrar.
    """
    linhas, tons = [], []
    for it in ctx.tabela["itens"]:
        if it["tipo"] != "VEA":
            continue
        cli = ctx.cliente(it["cliente"])
        falta = max(0.0, it["qtd"] - it["qtd_at"])
        linhas.append([it["pedido"], it["dt_pedido"], cli.get("cidade", ""),
                       "4" + it["filial"], _fornecedor(ctx, it["cod"]),
                       it["cod"], ctx.produto(it["cod"]), it["qtd"],
                       it["est_prod"], it.get("dem_ant", 0.0),
                       it["est_disp"], it["qtd_at"], falta,
                       ctx.nome_cliente(it["cliente"]), ctx.filial(it["filial"]),
                       it["p_venda"] * falta if falta else 0.0])
        tons.append("alerta" if it["qtd_at"] <= 0 else
                    ("atencao" if falta else "ok"))
    juntos = sorted(zip(linhas, tons), key=lambda z: (
        z[0][0], z[0][5]))
    linhas, tons = [z[0] for z in juntos], [z[1] for z in juntos]
    cols = [col("PEDIDO", "texto", 62), col("DATA", "dia", 70),
            col("CIDADE", "texto", 110), col("FILIAL", "texto", 76),
            col("FORN.", "texto", 52), col("CÓD. PROD.", "texto", 150),
            col("DESCRIÇÃO", "texto", 240), col("QTD", "num", 50),
            col("EST. FRW", "num", 70), col("PEDIDOS ANTES", "num", 92),
            col("DISP. P/ ESTE", "num", 84), col("ATENDIDO", "num", 70),
            col("FALTA", "num", 52), col("CLIENTE", "texto", 200),
            col("FILIAL BAP", "texto", 90, oculta=True),
            col("VALOR FALTANTE", "moeda", 92)]
    return tabela(
        "Analítico produto", cols, linhas, tons,
        filtros=("CIDADE", "FORN.", "CÓD. PROD."),
        recortes=[("Com falta", lambda l: l[12] > 0),
                  ("Sem nenhuma unidade", lambda l: l[11] <= 0)],
        kpis_de=lambda ls: [
            kpi("Itens", br(len(ls)), "neutro",
                f"{br(len({l[0] for l in ls}))} pedidos"),
            kpi("Volume", br(sum(l[7] for l in ls)), "neutro", "unidades"),
            kpi("Atendido", br(sum(l[11] for l in ls)), "ok",
                p(pct_de(sum(l[11] for l in ls), sum(l[7] for l in ls)))),
            kpi("Falta", br(sum(l[12] for l in ls)),
                "alerta" if any(l[12] for l in ls) else "ok",
                moeda(sum(l[15] for l in ls))),
            kpi("Itens com falta", br(sum(1 for l in ls if l[12] > 0)),
                "atencao" if any(l[12] for l in ls) else "ok")])


def _solicitacoes_pendentes(ctx):
    """As abas GERAR SEPARACAO CD e GERAR REVERSA DE LOJAS do BI: linhas da
    SOLICITACAO_BAP de pedido EM ABERTO, em ABRIR SOLICITACAO e sem ID."""
    sol = ctx.comercial.get("solicitacoes") or {}
    saida = []
    for chave, titulo, rot_id in (("cd", "Gerar separação CD", "SEPARAÇÃO"),
                                  ("lojas", "Gerar reversa de lojas",
                                   "REVERSA")):
        # (06/10) sem HORA e sem CONTROLE; FILIAL DESTINO -> FILIAL DEST.
        ls = [[x["data"], x["uf"], x["cidade"], x["pedidos"],
               _fornecedor(ctx, x["cod"]), x["cod"], ctx.produto(x["cod"]),
               x["qtd"], x["coletar"], x["destino"]]
              for x in sol.get(chave, [])]
        saida.append(tabela(
            titulo,
            [col("DATA", "dia", 70), col("UF", "texto", 34),
             col("CIDADE", "texto", 110), col("PEDIDOS", "texto", 110),
             col("FORN.", "texto", 52), col("CÓD. PROD.", "texto", 150),
             col("DESCRIÇÃO", "texto", 240), col("QTD", "num", 50),
             col("COLETAR EM", "texto", 80), col("FILIAL DEST.", "texto", 80)],
            ls, ["atencao"] * len(ls), filtros=("CIDADE",),
            kpis_de=lambda l_, r_=rot_id: [
                kpi(f"Linhas para gerar {r_.lower()}", br(len(l_)),
                    "atencao" if l_ else "ok"),
                kpi("Pedidos", br(len({x for l in l_
                                       for x in str(l[3]).split("|") if x})),
                    "neutro"),
                kpi("Unidades", br(sum(l[7] for l in l_)), "neutro")]))
    return saida


def painel_indicadores(ctx):
    hoje = ctx.hoje
    m_sel = ctx.param("MÊS") or mes_de(hoje)
    f_fil, f_vend, f_seg = ctx.param("FILIAL"), ctx.param("VENDEDOR"), \
        ctx.param("SEGMENTO")
    r = novo("pv_indicadores", PRE, "Painel de indicadores",
             f"SLA: faturar em {bd.PRAZO_FATURAR} dias úteis · "
             f"{ctx.texto_sla()}",
             "TABELA_BAP › ftPedidos + BASE_CLIENTE + ACOMPANHAMENTO_POS_VENDA")
    ent = _entregas_por_nf(ctx)

    def passa(it):
        if f_fil and ctx.filial(it["filial"]) != f_fil:
            return False
        if f_vend and ctx.vendedor(it["vend"]) != f_vend:
            return False
        if f_seg and ctx.cliente(it["cliente"]).get("segmento") != f_seg:
            return False
        return True
    peds = defaultdict(lambda: {"nfs": set(), "datas": [], "cli": "", "dtp": None,
                                "entregas": []})
    filiais, vendedores = set(), set()
    for it in ctx.tabela["itens"]:
        if it["tipo"] != "VND" or not it["dt_pedido"]:
            continue
        filiais.add(ctx.filial(it["filial"]))
        vendedores.add(ctx.vendedor(it["vend"]))
        if not passa(it):
            continue
        k = (it["filial"], it["pedido"])
        d = peds[k]
        d["nfs"].add(it["nf"])
        d["datas"].append(it["dt_nf"])
        d["cli"], d["dtp"] = it["cliente"], it["dt_pedido"]
        e = ent.get((it["filial"], it["nf"].lstrip("0")))
        if e and e.get("entregue_em"):
            d["entregas"].append(e["entregue_em"])
    por_sem = defaultdict(Counter)
    por_mes = defaultdict(Counter)
    dias_mes = defaultdict(list)
    for d in peds.values():
        primeira = min(x for x in d["datas"] if x) if any(d["datas"]) else None
        dias = ctx.uteis(d["dtp"], primeira)
        if dias is None:
            continue
        ok = dias <= bd.PRAZO_FATURAR
        parcial = len(d["nfs"]) > 1
        for grupo, chave in ((por_sem, semana_de(d["dtp"])),
                             (por_mes, mes_de(d["dtp"]))):
            c = grupo[chave]
            c["pedidos"] += 1
            c["no_prazo"] += ok
            c["atraso"] += not ok
            c["parcial"] += parcial
            if d["entregas"]:
                c["entregues"] += 1
                limite = ctx.mais_uteis(d["dtp"], ctx.prazo_entrega(d["cli"]))
                c["entrega_ok"] += max(d["entregas"]) <= limite
        dias_mes[mes_de(d["dtp"])].append(dias)
    # positivacao: clientes da BASE (do filtro) com compra no mes
    base = [c for c in ctx.base["clientes"]
            if (not f_seg or c["segmento"] == f_seg)
            and (not f_vend or ctx.vendedor(c["vend"]) == f_vend)]
    cods_base = {c["cod"] for c in base}
    compr_mes = defaultdict(set)
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND" and it["cliente"] in cods_base and \
                (not f_fil or ctx.filial(it["filial"]) == f_fil):
            if positivou(ctx, it["cliente"], it["dt_nf"]):
                compr_mes[mes_de(it["dt_nf"])].add(it["cliente"])
    n_base = len(base)

    def n_compr(mm):
        return sum(1 for cl in base if cl["cod"] in compr_mes[mm])
    meses = ultimos_meses(hoje, 12)
    r["parametros"] = [
        {"nome": "MÊS", "valor": m_sel,
         "valores": [(TODOS_MESES, "TODOS OS MESES")]
         + [(x, rotulo_mes(x)) for x in reversed(meses)]},
        {"nome": "FILIAL", "valor": f_fil or "(todos)",
         "valores": ["(todos)"] + sorted(filiais)},
        {"nome": "VENDEDOR", "valor": f_vend or "(todos)",
         "valores": ["(todos)"] + sorted(vendedores)},
        {"nome": "SEGMENTO", "valor": f_seg or "(todos)",
         "valores": ["(todos)"] + sorted({c["segmento"]
                                          for c in ctx.base["clientes"]})},
    ]
    if m_sel == TODOS_MESES:            # os 12 meses juntos
        c = Counter()
        for x in meses:
            c.update(por_mes[x])
        compr_sel = set().union(*(compr_mes[x] for x in meses))
        dias_sel = [d for x in meses for d in dias_mes[x]]
        rot_sel = "12 meses"
    else:
        c, compr_sel = por_mes[m_sel], compr_mes[m_sel]
        dias_sel, rot_sel = dias_mes[m_sel], rotulo_mes(m_sel)
    compraram = sum(1 for cl in base if cl["cod"] in compr_sel)
    r["kpis"] = [
        kpi(f"Pedidos faturados · {rot_sel}", br(c["pedidos"]),
            "neutro"),
        kpi("Faturados no prazo", p(pct_de(c["no_prazo"], c["pedidos"])),
            "ok" if (pct_de(c["no_prazo"], c["pedidos"]) or 0) >= 90 else "alerta",
            f"meta {bd.PRAZO_FATURAR} dias úteis"),
        kpi("Faturados com atraso", p(pct_de(c["atraso"], c["pedidos"])),
            "alerta" if c["atraso"] else "ok", f"{br(c['atraso'])} pedido(s)"),
        kpi("Faturamento parcial", p(pct_de(c["parcial"], c["pedidos"])),
            "atencao" if c["parcial"] else "ok"),
        kpi("SLA médio", f"{br(_media(dias_sel), 1)} dias", "info",
            "do pedido à nota"),
        kpi("Entregues no prazo", p(pct_de(c["entrega_ok"], c["entregues"])),
            "neutro", f"{br(c['entregues'])} com entrega"),
        kpi("Clientes com compra", br(compraram), "ok",
            f"{p(pct_de(compraram, n_base))} da base"),
        kpi("Clientes sem compra", br(n_base - compraram), "atencao",
            ""),
    ]
    semanas = sorted(k for k in por_sem if k)[-12:]
    r["graficos"].append({
        "titulo": "Semana a semana: % faturado no prazo",
        "rotulos": [f"{s:%d/%m}" for s in semanas],
        "series": [{"nome": "% no prazo", "cor": VERDE,
                    "valores": [pct_de(por_sem[s]["no_prazo"],
                                       por_sem[s]["pedidos"]) or 0
                                for s in semanas]},
                   {"nome": "% parcial", "cor": AZUL,
                    "valores": [pct_de(por_sem[s]["parcial"],
                                       por_sem[s]["pedidos"]) or 0
                                for s in semanas]}],
        "formato": "pct"})
    r["graficos"].append({
        "titulo": "Mês a mês: % faturado no prazo e % da base que comprou",
        "rotulos": [rotulo_mes(x) for x in meses],
        "series": [{"nome": "% no prazo", "cor": VERDE,
                    "valores": [pct_de(por_mes[x]["no_prazo"],
                                       por_mes[x]["pedidos"]) or 0
                                for x in meses]},
                   {"nome": "% base c/ compra", "cor": AZUL,
                    "valores": [pct_de(n_compr(x), n_base) or 0
                                for x in meses]}],
        "formato": "pct"})

    def linha(rot, c_, dias=None):
        return [rot, c_["pedidos"], c_["no_prazo"],
                pct_de(c_["no_prazo"], c_["pedidos"]), c_["atraso"],
                pct_de(c_["atraso"], c_["pedidos"]), c_["parcial"],
                pct_de(c_["parcial"], c_["pedidos"]),
                _media(dias) if dias is not None else None, c_["entregues"],
                pct_de(c_["entrega_ok"], c_["entregues"])]
    cols = [col("PERÍODO", "texto", 110), col("PEDIDOS", "int"),
            col("NO PRAZO", "int"), col("% NO PRAZO", "pct"),
            col("ATRASO", "int"), col("% ATRASO", "pct"),
            col("PARCIAL", "int"), col("% PARCIAL", "pct"),
            col("SLA MÉDIO (DIAS)", "num2", 110), col("ENTREGUES", "int"),
            col("% ENTREGA NO PRAZO", "pct", 120)]
    lin_s = [linha(f"semana {s:%d/%m/%Y}", por_sem[s]) for s in reversed(semanas)]
    r["tabelas"].append(tabela("Semana a semana", cols, lin_s,
                               [_tom_pct(x[3]) for x in lin_s]))
    lin_m = [linha(rotulo_mes(x), por_mes[x], dias_mes[x]) for x in reversed(meses)
             if por_mes[x]["pedidos"]]
    r["tabelas"].append(tabela("Mês a mês", cols, lin_m,
                               [_tom_pct(x[3]) for x in lin_m]))
    lin_b = [[rotulo_mes(x), n_base, n_compr(x), pct_de(n_compr(x), n_base),
              n_base - n_compr(x)] for x in reversed(meses)]
    r["tabelas"].append(tabela(
        "Base com compra (mês a mês)",
        [col("MÊS", "texto", 80), col("CLIENTES NA BASE", "int", 110),
         col("COM COMPRA", "int", 90), col("% COM COMPRA", "pct", 90),
         col("SEM COMPRA", "int", 90)], lin_b))
    seg = defaultdict(lambda: [0, 0])
    for cl in base:
        seg[cl["segmento"]][0] += 1
        seg[cl["segmento"]][1] += cl["cod"] in compr_sel
    lin_seg = sorted([[k, v[0], v[1], pct_de(v[1], v[0]), v[0] - v[1]]
                      for k, v in seg.items()], key=lambda x: -x[1])
    r["tabelas"].append(tabela(
        f"Base com compra em {rot_sel}, por segmento",
        [col("SEGMENTO", "texto", 200), col("CLIENTES", "int"),
         col("COM COMPRA", "int", 90), col("% COM COMPRA", "pct", 90),
         col("SEM COMPRA", "int", 90)], lin_seg))
    return r


def _media(xs):
    xs = [x for x in xs or [] if x is not None]
    return sum(xs) / len(xs) if xs else None


def _tom_pct(v, bom=90, ruim=70):
    if v is None:
        return ""
    return "ok" if v >= bom else ("alerta" if v < ruim else "atencao")


# =========================================================================
# VENDAS E CRM
# =========================================================================
def meta_do_periodo(ctx):
    """O Farol de Metas do MES escolhido em cima (meta, equipe e realizado
    daquele mes). TODOS OS MESES: o mes aberto no Gerador de Meta."""
    ano, mes = periodo(ctx)
    if not mes:
        return _com_cidades(ctx, ctx.meta)
    comp = f"{ano}-{mes:02d}"
    if comp not in ctx._b:
        ctx._b[comp] = bd.carregar(ctx.raiz, f"meta@{comp}", log=ctx.log)
    return _com_cidades(ctx, ctx._b[comp])


# (15/10, Alexandre) CLIENTES POR CIDADE: cada cidade do INTERIOR da
# carteira do vendedor tem de ter CLI_POR_CIDADE clientes cadastrados.
#   META = cidades do interior da carteira x 12
#   REAL = soma, cidade a cidade, dos cadastrados ATE 12 (a cidade com 40
#          nao cobre a que tem 2)
# Carteira = clientes do Planner (BASE_CLIENTE) com o vendedor, sem os
# inativados e sem os internos. Capital do estado nao entra. E a FOTO da
# base de hoje (nao muda com o mes escolhido). Indicador de acompanhamento:
# NAO entra na RV.
CLI_POR_CIDADE = 12
CAPITAIS_UF = {
    ("AM", "MANAUS"), ("PA", "BELEM"), ("MA", "SAO LUIS"),
    ("RR", "BOA VISTA"), ("AP", "MACAPA"), ("MT", "CUIABA"),
    ("RO", "PORTO VELHO"), ("AC", "RIO BRANCO"), ("TO", "PALMAS"),
    ("PI", "TERESINA"), ("CE", "FORTALEZA"), ("RN", "NATAL"),
    ("PB", "JOAO PESSOA"), ("PE", "RECIFE"), ("AL", "MACEIO"),
    ("SE", "ARACAJU"), ("BA", "SALVADOR"), ("DF", "BRASILIA"),
    ("GO", "GOIANIA"), ("MS", "CAMPO GRANDE"), ("MG", "BELO HORIZONTE"),
    ("ES", "VITORIA"), ("RJ", "RIO DE JANEIRO"), ("SP", "SAO PAULO"),
    ("PR", "CURITIBA"), ("SC", "FLORIANOPOLIS"), ("RS", "PORTO ALEGRE")}


def e_capital(uf, cidade) -> bool:
    return (sem_acento(uf), sem_acento(cidade)) in CAPITAIS_UF


def clientes_por_cidade(ctx) -> dict:
    """{cod do vendedor: {(uf, cidade): clientes cadastrados}} - so as
    cidades do interior da carteira (Planner)."""
    if not hasattr(ctx, "_cli_cid"):
        g = defaultdict(Counter)
        for c in ctx.base.get("clientes") or []:
            v = _cod6(c.get("vend")) if texto(c.get("vend")) else ""
            uf, cid = sem_acento(c.get("uf")), sem_acento(c.get("cidade"))
            if not v or not cid or c.get("inativo") or c.get("interno") \
                    or e_capital(uf, cid):
                continue
            g[v][(uf, cid)] += 1
        ctx._cli_cid = {v: dict(x) for v, x in g.items()}
    return ctx._cli_cid


def cobertura_cidades(ctx, cod) -> tuple:
    """(meta, real, cidades, cidades completas) de um vendedor."""
    cids = clientes_por_cidade(ctx).get(_cod6(cod)) or {}
    real = sum(min(n, CLI_POR_CIDADE) for n in cids.values())
    return (float(len(cids) * CLI_POR_CIDADE), real, len(cids),
            sum(1 for n in cids.values() if n >= CLI_POR_CIDADE))


def _com_cidades(ctx, dados):
    """Pendura META/REAL de clientes por cidade nas linhas de pessoa do
    acompanhamento (vendedor; supervisor e gerente = a soma da equipe)."""
    ac = (dados or {}).get("acomp") if isinstance(dados, dict) else None
    if not ac or ac.get("_cidades_ok"):
        return dados
    try:
        rec = ac.get("recortes") or {}
        equipe = ac.get("equipe_vend") or {}
        vend = rec.get("vendedor") or []
        por_v = {}
        for l in vend:
            m, r_, n_, k_ = cobertura_cidades(ctx, l.get("chave"))
            l.update(meta_cidades=m, cli_cidades=r_, cidades=n_,
                     cidades_ok=k_)
            por_v[_cod6(l.get("chave"))] = l

        def soma(ls, alvo):
            alvo.update(
                meta_cidades=sum(x["meta_cidades"] for x in ls),
                cli_cidades=sum(x["cli_cidades"] for x in ls),
                cidades=sum(x["cidades"] for x in ls),
                cidades_ok=sum(x["cidades_ok"] for x in ls))
        for l in rec.get("supervisor") or []:
            nome = sem_acento(l.get("chave") or l.get("nome"))
            soma([x for x in vend if sem_acento(x.get("supervisor")) == nome],
                 l)
        gers = rec.get("gerente") or []
        for l in gers:
            nome = sem_acento(l.get("chave") or l.get("nome"))
            dele = [x for c_, x in por_v.items()
                    if sem_acento((equipe.get(c_) or {}).get("gerente"))
                    == nome]
            soma(dele if (dele or len(gers) > 1) else vend, l)
        for k_ in ("vendedor", "supervisor", "gerente"):
            if (ac.get("totais") or {}).get(k_):
                soma(vend, ac["totais"][k_])
        ac["_cidades_ok"] = True
    except Exception:                                   # noqa: BLE001
        pass            # sem base de clientes: o indicador fica vazio
    return dados


def _COLS_MIX(nome):
    """As colunas dos paineis de mix (familia da peca e segmento)."""
    return [col(nome, "texto", 200), col("REALIZADO", "moeda"),
            col("% DO TOTAL", "pct"), col("M3M R$", "moeda"),
            col("% M3M", "pct", 75), col("CLIENTES", "int"),
            col("NOTAS", "int"), col("SKUs", "int"), col("TICKET", "moeda")]


def _meses_antes(comp, n):
    ano, mes = (int(x) for x in comp.split("-")[:2])
    saida = []
    for _ in range(n):
        mes -= 1
        if not mes:
            ano, mes = ano - 1, 12
        saida.append(f"{ano}-{mes:02d}")
    return saida


def _uteis_ate_ontem(ctx):
    """RN-GER-007: a contagem de dias uteis que deixa HOJE fora (conta ate
    ontem). Uma so, para o montar e o ao_mudar da NCC."""
    return lambda a, b: ctx.uteis(a, min(b, ctx.hoje - timedelta(days=1)))


def _liquido(it):
    """Venda soma, devolucao subtrai (o liquido do faturamento)."""
    if it["tipo"] == "VND":
        return it["valor"]
    if it["tipo"] == "DEV":
        return -abs(it["valor"])
    return None


def positivou(ctx, cliente, quando) -> bool:
    """(14/10, Alexandre) POSITIVACAO = o cliente COMPROU e NAO DEVOLVEU
    TUDO no mes: liquido (venda - devolucao) dele no mes > 0. A mesma
    regra em todo farol (Painel, Clientes, Metas, Executivos, Resumo)."""
    if not hasattr(ctx, "_liq_cli_mes"):
        soma = defaultdict(float)
        for it in ctx.tabela["itens"]:
            if it["dt_nf"]:
                v = _liquido(it)
                if v is not None:
                    soma[(it["cliente"], mes_de(it["dt_nf"]))] += v
        ctx._liq_cli_mes = soma
    if not quando:
        return False
    m = quando if isinstance(quando, str) else mes_de(quando)
    return ctx._liq_cli_mes.get((cliente, m), 0.0) > 0.005


def _ev_positivados(ctx, itens=None):
    """Eventos (data, cliente) de quem positivou - para os graficos e
    indicadores de 'Clientes positivados' (agg 'unicos')."""
    return [(it["dt_nf"], it["cliente"])
            for it in (ctx.tabela["itens"] if itens is None else itens)
            if it["tipo"] == "VND" and it["dt_nf"]
            and positivou(ctx, it["cliente"], it["dt_nf"])]


def clientes_positivados(ctx, comp) -> set:
    """Os clientes que positivaram no mes (comprou e nao devolveu tudo).
    Sem os CNPJs internos (ja fora de ctx.tabela)."""
    return {it["cliente"] for it in ctx.tabela["itens"]
            if it["tipo"] == "VND" and it["dt_nf"]
            and mes_de(it["dt_nf"]) == comp
            and positivou(ctx, it["cliente"], comp)}


def _m3m_por(ctx, comp, chave):
    """{chave: M3M} - a media mensal do liquido nos 3 meses ANTES do mes da
    meta (a mesma janela do FAT. M3M do Gerador de Meta)."""
    if not comp:
        return {}
    meses = set(_meses_antes(comp, 3))
    soma = defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["dt_nf"] and mes_de(it["dt_nf"]) in meses:
            v = _liquido(it)
            if v is not None:
                soma[chave(it)] += v
    return {k: v / 3.0 for k, v in soma.items()}


def _mix_do_mes(ctx, comp, chave):
    """{chave: realizado, clientes, notas e SKUs} no mes da meta."""
    saida = {}
    for it in ctx.tabela["itens"]:
        if not it["dt_nf"] or mes_de(it["dt_nf"]) != comp:
            continue
        v = _liquido(it)
        if v is None:
            continue
        x = saida.setdefault(chave(it), {"real": 0.0, "cli": set(),
                                         "nf": set(), "sku": set()})
        x["real"] += v
        if it["tipo"] == "VND":
            if positivou(ctx, it["cliente"], comp):
                x["cli"].add(it["cliente"])
            if it.get("nf"):
                x["nf"].add((it["filial"], it["nf"]))
            x["sku"].add(it["cod"])
    return saida


FORA_PLANNER_META = "(FORA DO PLANNER)"
TODA_A_BAP = "BAP INTEIRA"
RECORTES_PESSOA = ("gerente", "supervisor", "vendedor")
RECORTES_TERRITORIO = ("uf", "cidade", "bairro", "segmento", "zona")
# as vistas do Farol de Metas (e do PDF da parcial), nesta ordem
VISTAS_FAROL = (("gerente", "Por gerente"), ("supervisor", "Por supervisor"),
                ("vendedor", "Por vendedor"), ("uf", "Por UF"),
                ("cidade", "Por cidade"), ("bairro", "Por bairro"),
                ("segmento", "Por segmento"), ("zona", "Por zona"))


def _gcol(nome, curto, tipo, largura=None):
    """Coluna de tabela AGRUPADA: o nome inteiro (filtro, busca) e o
    curto, que aparece embaixo do rotulo do grupo."""
    return dict(col(nome, tipo, largura), curto=curto)


def _cod6(v):
    v = texto(v)
    return v.zfill(6) if v.isdigit() else v


def _mix_novo():
    return {"real": 0.0, "cli": set(), "nf": set(), "sku": set(), "m3m": 0.0,
            "pecas": 0.0}


def _eh_pecas(ctx, cod) -> bool:
    c = ctx.tabela["categorias"].get(cod, "")
    if not c and ctx.produto(cod).upper().startswith("BATERIA"):
        return False
    return c in ("", "pecas")


def _juntar_itens(ctx, comp, chaves, saida, so_vend=None):
    """Soma o mes e o M3M de cada item nas chaves que chaves(it) der:
    saida[(recorte, chave)] = mix. so_vend: so as notas desses vendedores."""
    janela = set(_meses_antes(comp, 3)) if comp else set()
    for it in ctx.tabela["itens"]:
        if not it["dt_nf"]:
            continue
        m = mes_de(it["dt_nf"])
        if m != comp and m not in janela:
            continue
        v = _liquido(it)
        if v is None:
            continue
        if so_vend is not None and _cod6(it.get("vend")) not in so_vend:
            continue
        for k in chaves(it):
            x = saida.setdefault(k, _mix_novo())
            if m == comp:
                x["real"] += v
                if _eh_pecas(ctx, it["cod"]):
                    x["pecas"] += v
                if it["tipo"] == "VND":
                    if positivou(ctx, it["cliente"], comp):
                        x["cli"].add(it["cliente"])
                    if it.get("nf"):
                        x["nf"].add((it["filial"], it["nf"]))
                    x["sku"].add(it["cod"])
            else:
                x["m3m"] += v / 3.0
    return saida


def _mix_das_linhas(ctx, comp, ac):
    """{(recorte, chave): mix} das linhas do Farol (sem filtro). Pessoa:
    pela nota (quem vendeu); territorio: pelo cliente; familia: por
    equipe (BAP, gerente, supervisor, vendedor)."""
    equipe = ac.get("equipe_vend") or {}
    mapa = ac.get("mapa_cliente") or {}

    def chaves(it):
        cod = _cod6(it.get("vend"))
        eq = equipe.get(cod)
        mc = mapa.get(it["cliente"]) or {}
        f = ctx.familia(it["cod"])
        cb = ctx.categoria_bap(it["cod"])
        saida = [("vendedor", _cod6(eq["vendedor"]) if eq else cod),
                 ("supervisor", eq["supervisor"] if eq else FORA_PLANNER_META),
                 ("gerente", eq["gerente"] if eq else FORA_PLANNER_META),
                 ("familia", ("bap", TODA_A_BAP, f)),
                 ("categoria", ("bap", TODA_A_BAP, cb)),
                 ("cliente", it["cliente"])]
        # (10/11, Alexandre: "a filial da nota define de onde vem o
        # faturamento") a UF do realizado = a da FILIAL DA NOTA; cidade,
        # bairro, segmento e zona continuam os do cliente
        saida += [(r, (uf_da_filial(it.get("filial")) if r == "uf" else
                       mc.get(r)) or mc.get(r) or FORA_PLANNER_META)
                  for r in RECORTES_TERRITORIO]
        if eq:
            saida += [(g_, (n, _cod6(eq[n]) if n == "vendedor" else eq[n], x_))
                      for n in RECORTES_PESSOA
                      for g_, x_ in (("familia", f), ("categoria", cb))]
        return saida
    return _juntar_itens(ctx, comp, chaves, {})


# ---- as colunas (iguais em todas as vistas, no Farol e no PDF) ----------
# AS LARGURAS DO PDF (pontos): IGUAIS EM TODAS AS TABELAS - cada coluna
# fica exatamente embaixo da outra ao longo do PDF. Medidas para a Calibri
# 6,2 (corpo) e 5,6 (cabecalho): o maior numero cabe sem quebrar. O nome
# (ou UF/CIDADE/BAIRRO) fica com o resto da pagina: PDF_UTIL = A4 deitada
# menos as margens do PDF BAP (17 pt de cada lado).
PDF_UTIL = 806.0
PDF_UF = 22.0           # a coluna UF (cidade e bairro)
PDF_CIDADE = 100.0      # a coluna CIDADE na vista bairro
PDF_TERR = 240.0        # UF/CIDADE/BAIRRO, segmento, zona: o comeco da
#                         linha; os numeros esticam para encher a pagina


# (29/10, Alexandre) TUDO E DESAFIO COMERCIAL: a meta RH (e a RV, que sai
# dela) so aparece no EXPORTAR PARA O RH, no e-mail e na parcial de RV
# (exportar_rh). Nos farois, paineis e no PDF/Excel comum do Farol de Metas
# fica so o DESAFIO (FAT. META). _COM_RH[0] = True so dentro do exportar_rh.
_COM_RH = [False]


def _cols_farol(tipo="pessoa"):
    """As colunas do Farol de Metas (iguais na tela, no Excel e no PDF).
    tipo: "pessoa" (gerente, supervisor, vendedor: tudo, com VISITA,
    CADASTRO COM COMPRA e RV), "territorio" (UF, cidade, bairro, segmento,
    zona: sem VISITA, CADASTRO nem RV), "familia" (so faturamento, os
    clientes que compraram e o mix). ating=True: o % que ganha cor."""
    def c(nome, curto, tipo_, larg, pdf, ating=False):
        return dict(_gcol(nome, curto, tipo_, larg), pdf_larg=pdf,
                    ating=ating)

    def ind(n, dinheiro, nec=True):
        cs = [c(f"{n} META", "META", "moeda" if dinheiro else "num", 76,
                27 if dinheiro else 19),
              c(f"{n} REAL", "REAL", "moeda" if dinheiro else "num", 76,
                27 if dinheiro else 19),
              c(f"{n} % ATING.", "%", "pct", 44, 20, ating=True)]
        if nec:
            cs.append(c(f"{n} NEC./DIA", "NEC. DIA",
                        "moeda" if dinheiro else "num2", 64,
                        22 if dinheiro else 19))
        return cs
    cols, grupos = [], []
    if tipo == "cliente":       # o TOP 30: o faturamento dos ultimos 6 meses
        cols.append(c("FAT. 6 MESES", "6 MESES", "moeda", 90, 26))
        grupos.append(("FAT.", 1))
    elif tipo != "familia":
        cols.append(c("CLIENTES ATIVOS", "ATIVOS", "int", 60, 26))
        grupos.append(("CLIENTES", 1))     # a faixa CLIENTES em cima de ATIVOS
    # (06/10) DESAFIO = a meta comercial (a do gerente desdobrada);
    # META = a meta RH (a que paga a RV)
    if _COM_RH[0]:
        cols += [c("FAT. META", "DESAFIO", "moeda", 80, 30),
                 c("FAT. META RH", "META", "moeda", 80, 30),
                 c("FAT. REAL", "REAL", "moeda", 76, 30),
                 c("FAT. % ATING.", "% DES.", "pct", 46, 20, ating=True),
                 c("FAT. % ATING. RH", "% META", "pct", 44, 20, ating=True),
                 c("FAT. NEC./DIA", "NEC. DIA", "moeda", 66, 22)]
        grupos.append(("FATURAMENTO", 6))
    else:
        cols += [c("FAT. META", "DESAFIO", "moeda", 80, 30),
                 c("FAT. REAL", "REAL", "moeda", 76, 30),
                 c("FAT. % ATING.", "% DES.", "pct", 46, 20, ating=True),
                 c("FAT. NEC./DIA", "NEC. DIA", "moeda", 66, 22)]
        grupos.append(("FATURAMENTO", 4))
    if tipo == "familia":
        cols.append(c("POSIT. REAL", "CLIENTES", "num", 80, 34))
        grupos.append(("POSIT.", 1))
    else:
        cols += ind("POSIT.", False)
        grupos.append(("POSITIVAÇÃO", 4))
        if tipo == "pessoa":
            cols += ind("VISITA", False)
            grupos.append(("VISITA", 4))
            cols += ind("CAD.", False, nec=False)
            grupos.append(("CAD. C/ COMPRA", 3))
            # (15/10) clientes por cidade do interior (12 por cidade)
            cols += ind("CID.", False, nec=False)
            grupos.append(("CLI. P/ CIDADE", 3))
        cols += ind("PEÇAS", True)
        grupos.append(("PEÇAS", 4))
    cols += [c("% PART", "% PART", "pct", 50, 20),
             c("M3M R$", "M3M R$", "moeda", 76, 30),
             c("% M3M", "% M3M", "pct", 48, 20),
             c("NOTAS", "NOTAS", "int", 46, 21),
             c("SKUs", "SKUs", "int", 42, 19),
             c("TICKET", "TICKET", "moeda", 64, 23)]
    grupos.append(("MIX", 6))
    if tipo == "pessoa":
        # (15/10) espaco para CLI. P/ CIDADE no PDF sem apertar os numeros:
        # os % ficam mais estreitos e o % PART sai do PDF (na tela fica)
        for c_ in cols:
            if c_["nome"] == "% PART":
                c_["pdf_oculta"] = True
            elif c_["tipo"] == "pct":
                c_["pdf_larg"] = 17
        if _COM_RH[0]:      # a RV sai da meta RH: so no RH/parcial de RV
            cols += [c("RV FAT.", "FAT.", "moeda", 58, 22),
                     c("RV POSIT.", "POSIT.", "moeda", 58, 22),
                     c("RV VISITA", "VISITA", "moeda", 58, 22),
                     c("RV TOTAL", "TOTAL", "moeda", 62, 23)]
            grupos.append(("RV R$", 4))
    return cols, grupos


def _d_da_linha(l, rh=None):
    """Os numeros de uma linha do acompanhamento, no formato do Farol."""
    mv = l.get("meta_visita")
    return {"meta": l.get("meta") or 0.0,
            "meta_rh": l.get("meta_rh") if rh is None else rh,
            "real": l.get("realizado") or 0.0,
            "mp": l.get("meta_positivacao") or 0.0,
            "rp": l.get("positivados") or 0,
            "mv": mv, "rv": l.get("visitas_realizadas") if mv is not None
            else None,
            "mpe": l.get("meta_pecas") or 0.0,
            "rpe": l.get("real_pecas") or 0.0,
            "mc": l.get("meta_cadastro"),
            "rc": l.get("cadastros_com_compra")
            if l.get("meta_cadastro") is not None else None,
            "mcid": l.get("meta_cidades"), "rcid": l.get("cli_cidades"),
            "rv_fat": l.get("rv_fat"), "rv_pos": l.get("rv_positivacao"),
            "rv_vis": l.get("rv_visita"), "rv_tot": l.get("rv_total")}


def _somar_d(ds, com_rv=True):
    tot = {"meta": 0.0, "meta_rh": 0.0, "real": 0.0, "mp": 0.0, "rp": 0,
           "mv": None, "rv": None, "mpe": 0.0, "rpe": 0.0, "mc": None,
           "rc": None, "mcid": None, "rcid": None, "ativos": 0}
    for d in ds:
        for k in ("meta", "meta_rh", "real", "mp", "rp", "mpe", "rpe",
                  "ativos"):
            tot[k] += d.get(k) or 0
        if d.get("mv") is not None:
            tot["mv"] = (tot["mv"] or 0) + d["mv"]
            tot["rv"] = (tot["rv"] or 0) + (d.get("rv") or 0)
        if d.get("mc") is not None:
            tot["mc"] = (tot["mc"] or 0) + d["mc"]
            tot["rc"] = (tot["rc"] or 0) + (d.get("rc") or 0)
        if d.get("mcid") is not None:
            tot["mcid"] = (tot["mcid"] or 0) + d["mcid"]
            tot["rcid"] = (tot["rcid"] or 0) + (d.get("rcid") or 0)
    for k in ("rv_fat", "rv_pos", "rv_vis", "rv_tot"):
        vals = [d.get(k) for d in ds if d.get(k) is not None]
        tot[k] = sum(vals) if (vals and com_rv) else None
    return tot


def _valores_farol(d, mix, total_real, resta, tipo="pessoa"):
    """Os valores na MESMA ordem de _cols_farol(tipo)."""
    def nec(meta, real):
        if meta is None or not resta:
            return None
        return max(0.0, (meta or 0) - (real or 0)) / resta
    meta, rh, real = d["meta"], d.get("meta_rh"), d["real"]
    mv, rv_ = d.get("mv"), d.get("rv")
    v = [] if tipo == "familia" else [d.get("ativos")]
    if _COM_RH[0]:
        v += [meta, rh, real, pct_de(real, meta),
              pct_de(real, rh) if rh else None, nec(meta, real)]
    else:
        v += [meta, real, pct_de(real, meta), nec(meta, real)]
    if tipo == "familia":
        v.append(d.get("rp"))
    else:
        v += [d.get("mp"), d.get("rp"), pct_de(d.get("rp") or 0, d.get("mp")),
              nec(d.get("mp"), d.get("rp"))]
        if tipo == "pessoa":
            v += [mv, rv_, pct_de(rv_ or 0, mv) if mv else None, nec(mv, rv_)]
            mc, rc = d.get("mc"), d.get("rc")
            v += [mc, rc, pct_de(rc or 0, mc) if mc else None]
            mci, rci = d.get("mcid"), d.get("rcid")
            v += [mci, rci, pct_de(rci or 0, mci) if mci else None]
        v += [d.get("mpe"), d.get("rpe"),
              pct_de(d.get("rpe") or 0, d.get("mpe")),
              nec(d.get("mpe"), d.get("rpe"))]
    if mix is None:
        v += [pct_de(real, total_real), None, None, None, None, None]
    else:
        nf = len(mix["nf"])
        v += [pct_de(real, total_real), mix["m3m"], pct_de(real, mix["m3m"]),
              nf, len(mix["sku"]), (mix["real"] / nf) if nf else None]
    if tipo == "pessoa" and _COM_RH[0]:
        v += [d.get("rv_fat"), d.get("rv_pos"), d.get("rv_vis"),
              d.get("rv_tot")]
    return v


def _mix_total(mixes):
    """O mix do TOTAL: soma o dinheiro; cliente, nota e SKU sem repetir."""
    tot = _mix_novo()
    for x in mixes:
        if not x:
            continue
        tot["real"] += x["real"]
        tot["m3m"] += x["m3m"]
        tot["cli"] |= x["cli"]
        tot["nf"] |= x["nf"]
        tot["sku"] |= x["sku"]
    return tot


def _tom_ating(v):
    """vermelho < 80%, amarelo < 100%, verde >= 100% (o mesmo do PDF)."""
    if v is None:
        return ""
    return "alerta" if v < 80 else "atencao" if v < 100 else "ok"


def _cartao_indicador(nome, meta, real, resta, esperado, dinheiro=False,
                      rot_meta="meta", ate=None, meta_ate=None,
                      real_proj=None):
    """O cartao de um indicador: o REAL grande (o realizado ATE A DATA), a
    META DO MES embaixo e as linhas - ATING. DO MES (real / meta do mes),
    META ATE A DATA (a meta do mes na proporcao dos dias uteis ja
    corridos), ATING. ATE A DATA (real / meta ate a data), PROJECAO (o
    ritmo de hoje ate o fim do mes, com % da meta) e NEC./DIA (o que falta /
    dias uteis). (18/10, Alexandre: o cartao tem de dizer o que e do mes e o
    que e ate a data.) `ate`: a data do realizado, para o rotulo."""
    def fmt(v):
        if v is None:
            return "—"
        return moeda(v) if dinheiro else br(v)
    meta, real = meta or 0.0, real or 0.0
    at = pct_de(real, meta)
    corrido = (esperado or 0.0) / 100.0
    # (05/11) real_proj: o realizado SEM O DIA DE HOJE (hoje nao conta nos
    # DU corridos, entao a venda/visita de hoje tambem sai da projecao)
    rp_ = real if real_proj is None else max(0.0, real_proj)
    proj = rp_ / corrido if corrido > 0 else None
    pp = pct_de(proj, meta) if proj is not None else None
    nec = max(0.0, meta - real) / resta if resta else None
    nec_txt = "—" if nec is None else (moeda(nec) if dinheiro
                                       else br(nec, 1 if nec < 100 else 0))
    tom = _tom_ating(pp if pp is not None else at)
    # (21/10) meta_ate: a meta ate a data ja somada dia a dia (a do Farol de
    # Visita, desde a admissao); senao, a do mes na proporcao dos dias uteis
    if meta_ate is None:
        meta_ate = meta * corrido if corrido > 0 else None
    at_ate = pct_de(real, meta_ate) if meta_ate else None
    rot_ate = f"até {ate:%d/%m}" if ate else "até a data"
    fechado = corrido >= 0.999
    linhas = [("Ating. do mês", p(at), _tom_ating(at))]
    if not fechado:
        linhas += [(f"{rot_meta.capitalize()} {rot_ate}", fmt(meta_ate), ""),
                   (f"Ating. {rot_ate}", p(at_ate), _tom_ating(at_ate))]
    linhas += [("Projeção do mês", fmt(proj) + (f" ({p(pp)})" if pp
                                                 is not None else ""),
                _tom_ating(pp)),
               ("Nec./dia", nec_txt if resta else "mês fechado", "")]
    return kpi(nome, fmt(real), {"ok": "ok", "atencao": "atencao",
                                 "alerta": "alerta"}.get(tom, "neutro"),
               f"real {rot_ate if not fechado else 'do mês'} · {rot_meta} "
               f"do mês {fmt(meta)}", linhas)


def _hoje_do_farol(ctx, ac, comp) -> dict:
    """(05/11, Alexandre: "tirar a venda de hoje da conta do DU") O QUE E DE
    HOJE (o dia aberto) no Farol de Metas, para sair da PROJECAO (os DU
    corridos ja nao contam hoje): {nivel: {chave/nome: {"FAT.", "POSIT.",
    "VISITA", "PEÇAS"}}, "_bap": {...}}. Faturamento e pecas = liquido das
    notas de hoje por quem vendeu (C5_VEND1, a regra da RV); positivacao =
    cliente que so ficou positivo com a nota de hoje; visita = Espelho de
    hoje. Mes que nao e o corrente: {} (nada muda)."""
    hoje = getattr(ctx, "hoje", None)
    if not comp or not hoje or mes_de(hoje) != comp:
        return {}
    memo = getattr(ctx, "_hoje_farol", None)
    if memo is None:
        memo = ctx._hoje_farol = {}
    if comp in memo:
        return memo[comp]
    por_v = defaultdict(lambda: defaultdict(float))
    bap = defaultdict(float)
    liq_t, liq_o = defaultdict(float), defaultdict(float)
    cli_t, cli_o = defaultdict(float), defaultdict(float)
    for it in ctx.tabela["itens"]:
        d = it.get("dt_nf")
        if not d or mes_de(d) != comp:
            continue
        v = _liquido(it)
        if v is None:
            continue
        cv = _cod6(it.get("vend"))
        liq_t[(cv, it["cliente"])] += v
        cli_t[it["cliente"]] += v
        if d >= hoje:
            por_v[cv]["FAT."] += v
            bap["FAT."] += v
            if ctx.categoria_bap(it.get("cod")) in LINHAS_PECAS:
                por_v[cv]["PEÇAS"] += v
                bap["PEÇAS"] += v
        else:
            liq_o[(cv, it["cliente"])] += v
            cli_o[it["cliente"]] += v
    for (cv, c), v in liq_t.items():
        if v > 0.005 and liq_o.get((cv, c), 0.0) <= 0.005:
            por_v[cv]["POSIT."] += 1
    bap["POSIT."] = sum(1 for c, v in cli_t.items()
                        if v > 0.005 and cli_o.get(c, 0.0) <= 0.005)
    try:
        import visitas_nucleo as vn                     # noqa: PLC0415
        for r_ in vn.registros(ctx.raiz):
            if r_["data"] >= hoje and mes_de(r_["data"]) == comp \
                    and r_.get("ativo") and r_.get("cod_protheus"):
                n_ = r_.get("visitas") or 0
                por_v[_cod6(r_["cod_protheus"])]["VISITA"] += n_
                bap["VISITA"] += n_
    except Exception:                                   # noqa: BLE001
        pass
    equipe = ac.get("equipe_vend") or {}
    nome_v = {_cod6(l.get("chave")): l.get("nome") or l.get("rotulo")
              for l in (ac.get("recortes") or {}).get("vendedor") or []
              if l.get("chave")}
    out = {"vendedor": {}, "supervisor": {}, "gerente": {}, "_bap": dict(bap)}

    def somar(nivel, chave, vals):
        if not texto(chave):
            return
        alvo = out[nivel].setdefault(norm_nome(chave), defaultdict(float))
        for a, b in vals.items():
            alvo[a] += b
    for cv, vals in por_v.items():
        somar("vendedor", cv, vals)
        if nome_v.get(cv):
            somar("vendedor", nome_v[cv], vals)
        f_ = equipe.get(cv) or {}
        somar("supervisor", f_.get("supervisor"), vals)
        somar("gerente", f_.get("gerente"), vals)
    memo[comp] = out
    return out


def _cartoes_farol(ls, cols, resta, esperado, hoje_de=None, hoje_total=None):
    """Os cartoes de cima de uma vista (pelos nomes das colunas dela): um
    por indicador - faturamento (meta comercial e meta RH), positivacao,
    visita, pecas e cadastro com compra. (05/11) hoje_de {nome da linha:
    o que e de hoje} ou hoje_total (a BAP inteira): sai da PROJECAO."""
    idx = {c["nome"]: i for i, c in enumerate(cols)}

    def soma(nome):
        return sum(l[idx[nome]] or 0 for l in ls) if nome in idx else None

    def de_hoje(ind):
        if hoje_total is not None:
            return hoje_total.get(ind) or 0.0
        if not hoje_de:
            return 0.0
        return sum((hoje_de.get(norm_nome(l[0])) or {}).get(ind) or 0.0
                   for l in ls if l)

    def proj_de(real_, ind):
        return None if real_ is None else real_ - de_hoje(ind)
    real = soma("FAT. REAL")
    saida = [_cartao_indicador("Faturamento · desafio comercial",
                               soma("FAT. META"), real, resta, esperado,
                               True, rot_meta="desafio",
                               real_proj=proj_de(real, "FAT."))]
    if "FAT. META RH" in idx:       # so no RH / parcial de RV (_COM_RH)
        saida.append(_cartao_indicador("Faturamento · meta RH",
                                       soma("FAT. META RH"), real, resta,
                                       esperado, True,
                                       real_proj=proj_de(real, "FAT.")))
    for nome, rot, din in (("POSIT.", "Positivação", False),
                           ("VISITA", "Visitas", False),
                           ("PEÇAS", "Peças", True),
                           ("CAD.", "Cad. com compra", False)):
        if f"{nome} META" in idx:
            r_ = soma(f"{nome} REAL")
            saida.append(_cartao_indicador(rot, soma(f"{nome} META"),
                                           r_, resta, esperado, din,
                                           real_proj=proj_de(r_, nome)))
    if "CID. META" in idx and soma("CID. META"):
        # (15/10) e estoque, nao ritmo: sem projecao nem nec./dia
        m_, r_ = soma("CID. META"), soma("CID. REAL")
        at_ = pct_de(r_, m_)
        saida.append(kpi("Clientes por cidade", br(r_),
                         {"ok": "ok", "atencao": "atencao",
                          "alerta": "alerta"}.get(_tom_ating(at_), "neutro"),
                         f"meta {br(m_)}",
                         [("Ating.", p(at_), _tom_ating(at_)),
                          ("Cidades", br(m_ / CLI_POR_CIDADE), ""),
                          ("Por cidade", br(CLI_POR_CIDADE), ""),
                          ("Faltam", br(max(0.0, m_ - r_)), "")]))
    return saida


def _tom_farol(at, esperado):
    if (at or 0) >= 100:
        return "ok"
    if esperado is not None and (at or 0) < esperado * 0.8:
        return "alerta"
    return ""


def _tabela_farol(titulo, cab, itens, total, resta, esperado, tipo="pessoa",
                  hoje_de=None,
                  **kw):
    """itens: [(valores do cabecalho, d, mix)]; total: o mesmo, ou None."""
    cols_i, grupos_i = _cols_farol(tipo)
    k = len(cab)
    tot_real = sum(d["real"] for _c, d, _m in itens)
    linhas = [list(c) + _valores_farol(d, m, tot_real, resta, tipo)
              for c, d, m in itens]
    tl = (list(total[0]) + _valores_farol(total[1], total[2], tot_real,
                                          resta, tipo)) if total else None
    cab = _cab_no_pdf(cab, tipo)
    fator = _larguras_pdf(tipo)[1]
    if fator != 1.0:
        for c_ in cols_i:
            c_["pdf_larg"] = round(c_["pdf_larg"] * fator, 2)
    cols = cab + cols_i
    i_at = next(i for i, c_ in enumerate(cols) if c_["nome"] == "FAT. % ATING.")
    t_ = tabela(titulo, cols, linhas,
                [_tom_farol(l[i_at], esperado) for l in linhas], total=tl,
                kpis_de=lambda xs: _cartoes_farol(xs, cols, resta, esperado,
                                                  hoje_de),
                **kw)
    t_["grupos"] = [("", k)] + grupos_i
    t_["compacta"] = True
    t_["pdf"] = {"verticais": True, "cab": 4.6, "sem_rs": True, "corpo": 5.2,
                 "pad": 2, "sem_quebra": True}
    return t_


PDF_NOME_PESSOA = 84.0     # o comeco da linha de pessoa (cod. + nome)


def _larguras_pdf(tipo):
    """(comeco da linha, fator dos numeros) no PDF. Pessoa: os numeros na
    medida e o nome com o resto. Territorio: o comeco com PDF_TERR e os
    numeros esticados ate a margem. Familia: o mesmo fator e o comeco +
    CLIENTES ATIVOS, para o FATURAMENTO ficar embaixo do dos territorios."""
    if tipo == "pessoa":
        # (15/10) com CLI. P/ CIDADE os numeros apertam um pouco para o
        # nome nao encolher (fica com PDF_NOME_PESSOA)
        cols, _g = _cols_farol("pessoa")
        soma_ = sum(c_["pdf_larg"] for c_ in cols if not c_.get("pdf_oculta"))
        if PDF_UTIL - soma_ >= PDF_NOME_PESSOA:
            return PDF_UTIL - soma_, 1.0
        return PDF_NOME_PESSOA, (PDF_UTIL - PDF_NOME_PESSOA) / soma_
    cols, _g = _cols_farol("territorio")
    fator = (PDF_UTIL - PDF_TERR) / sum(c_["pdf_larg"] for c_ in cols)
    if tipo == "familia":
        return PDF_TERR + cols[0]["pdf_larg"] * fator, fator
    return PDF_TERR, fator


def _sobra_pdf(tipo) -> float:
    return _larguras_pdf(tipo)[0]


def _cab_no_pdf(cab, tipo):
    """As colunas do comeco da linha com a largura do PDF: as que ja tem
    (UF, CIDADE) ficam; a ultima visivel leva o resto."""
    cab = [dict(c_) for c_ in cab]
    vis = [c_ for c_ in cab if not c_.get("pdf_oculta")]
    for c_ in cab:
        if c_.get("pdf_oculta"):
            c_.setdefault("pdf_larg", 1.0)
    vis[-1]["pdf_larg"] = _sobra_pdf(tipo) - sum(
        c_.get("pdf_larg") or 0 for c_ in vis[:-1])
    return cab


def _cab_territorio(recorte):
    """As colunas do comeco da linha de cada territorio: UF, CIDADE e
    BAIRRO em colunas separadas (nao 'BAIRRO · CIDADE/UF')."""
    uf = dict(col("UF", "texto", 44), pdf_larg=PDF_UF, fixa=True)
    if recorte == "cidade":
        return [uf, col("CIDADE", "texto", 190)]
    if recorte == "bairro":
        return [uf, dict(col("CIDADE", "texto", 150), pdf_larg=PDF_CIDADE),
                col("BAIRRO", "texto", 170)]
    return [col({"uf": "UF", "segmento": "SEGMENTO", "zona": "ZONA"}.get(
        recorte, "NOME"), "texto", 60 if recorte == "uf" else 190)]


def _partes_da_linha(recorte, l) -> list:
    """Os valores de UF/CIDADE/BAIRRO de uma linha do acompanhamento."""
    if recorte == "cidade" and l.get("codigo"):
        return [l["codigo"], texto(l.get("nome")) or "(SEM CIDADE)"]
    if recorte == "bairro" and l.get("codigo"):
        return [str(l.get("chave") or "").split("|")[0], l["codigo"],
                texto(l.get("nome")) or "(SEM BAIRRO)"]
    return [l.get("nome") or l.get("rotulo")] + [""] * (
        len(_cab_territorio(recorte)) - 1)


def _partes_do_rotulo(recorte, k) -> list:
    """O mesmo, a partir do rotulo do filtro ('CID/UF', 'B · CID/UF')."""
    k = str(k)
    if recorte == "cidade" and "/" in k:
        cid, uf = k.rsplit("/", 1)
        return [uf, cid if cid.strip("? ") else "(SEM CIDADE)"]
    if recorte == "bairro" and " · " in k:
        b, resto = k.split(" · ", 1)
        cid, uf = resto.rsplit("/", 1) if "/" in resto else (resto, "")
        return [uf, cid, b if b.strip("? ") else "(SEM BAIRRO)"]
    return [k] + [""] * (len(_cab_territorio(recorte)) - 1)


def _linha_vazia(recorte, rot) -> list:
    """TOTAL / DEMAIS: o texto na ultima coluna (a larga); TOTAL na 1a."""
    n = len(_cab_territorio(recorte))
    if rot == "TOTAL":
        return ["TOTAL"] + [""] * (n - 1)
    return [""] * (n - 1) + [rot]


# O RECORTE do Farol de Metas: escolhido em cima (como o mes), vale para
# todas as abas. As opcoes de cada caixa vem do que sobra nas outras.
RECORTE_META = ("SEGMENTO", "SUPERVISOR", "VENDEDOR", "UF", "CIDADE",
                "BAIRRO")
TERRITORIOS = ("uf", "cidade", "bairro", "segmento")


def _chaves_terr(a) -> dict:
    """Os rotulos de territorio de um cliente (o mesmo do filtro)."""
    uf = texto(a.get("uf")) or "?"
    cid = texto(a.get("cidade")) or "?"
    return {"uf": uf, "cidade": f"{cid}/{uf}",
            "bairro": f"{texto(a.get('bairro')) or '?'} · {cid}/{uf}",
            "segmento": texto(a.get("segmento")) or "(SEM SEGMENTO)"}


def _nomes_vendedor(ac) -> dict:
    return {_cod6(l["chave"]): texto(l.get("nome") or l.get("rotulo"))
            for l in (ac.get("recortes") or {}).get("vendedor", [])
            if l.get("chave")}


def _rotulo_vend(cod, nomes) -> str:
    return f"{cod} - {nomes.get(cod, '')}".strip(" -")


def recorte_da_meta(ctx, r, ac):
    """As seis caixas de cima e o que foi escolhido: (V, T, sup, texto).
    V = codigos dos vendedores (None = todos); T(chaves) -> bool para o
    territorio (None = todos); sup = a linha do supervisor escolhido."""
    nomes = _nomes_vendedor(ac)
    cli = [c for c in ac.get("clientes_slim") or []
           if not c.get("fora_do_planner")]

    def campo(c, nome):
        k = _chaves_terr(c)
        return {"SEGMENTO": k["segmento"], "UF": k["uf"],
                "CIDADE": k["cidade"], "BAIRRO": k["bairro"],
                "SUPERVISOR": texto(c.get("supervisor")) or "(SEM SUPERVISOR)",
                "VENDEDOR": _rotulo_vend(_cod6(c.get("cod_vendedor")),
                                         nomes)}[nome]
    escolha = {n: ctx.param(n) for n in RECORTE_META}
    for nome in RECORTE_META:
        outros = [c for c in cli if all(
            escolha[n] is None or campo(c, n) == escolha[n]
            for n in RECORTE_META if n != nome)]
        valores = sorted({campo(c, nome) for c in outros})
        if escolha[nome] is not None and escolha[nome] not in valores:
            valores.append(escolha[nome])
        r.setdefault("parametros", []).append({
            "nome": nome, "valores": [TODOS_RECORTE] + valores,
            "valor": escolha[nome] or TODOS_RECORTE})
    txt = " · ".join(f"{n.capitalize()}: {escolha[n]}" for n in RECORTE_META
                     if escolha[n])
    if not txt:
        return None, None, None, ""
    V = None
    if escolha["SUPERVISOR"] or escolha["VENDEDOR"]:
        V = {cod for cod, e in (ac.get("equipe_vend") or {}).items()
             if (escolha["SUPERVISOR"] is None
                 or texto(e.get("supervisor")) == escolha["SUPERVISOR"])
             and (escolha["VENDEDOR"] is None
                  or _rotulo_vend(cod, nomes) == escolha["VENDEDOR"])}
    terr = {"segmento": escolha["SEGMENTO"], "uf": escolha["UF"],
            "cidade": escolha["CIDADE"], "bairro": escolha["BAIRRO"]}
    T = None
    if any(terr.values()):
        def T(k, terr=terr):                         # noqa: E306
            return all(v is None or k[r_] == v for r_, v in terr.items())
    sup = None
    if escolha["SUPERVISOR"] and not escolha["VENDEDOR"] and T is None:
        sup = next((l for l in ac["recortes"].get("supervisor", [])
                    if texto(l.get("chave")) == escolha["SUPERVISOR"]), None)
    return V, T, sup, txt


def acompanhamento_meta(ctx):
    dados = meta_do_periodo(ctx)
    ac = dados["acomp"]
    comp = dados["competencia"]
    r = novo("vc_meta", VEN, "Farol de Metas Equipe",
             f"Competência {rotulo_mes(comp)} · meta e desafio comercial",
             "Gerador de Meta (BAP Analista) + TABELA_BAP")
    capa(r, ctx, anos_dos_dados(ctx))
    V, T, sup, txt = recorte_da_meta(ctx, r, ac)
    graficos_tempo(r, ctx, "Faturamento líquido (R$)",
                   _eventos_faturamento(ctx, liquido=True), "moeda", VERDE)
    vend = [l for l in ac["recortes"].get("vendedor", [])
            if not _inativo_oculto(ctx, comp, l)]           # (06/11)
    if V is not None:
        vend = [l for l in vend if _cod6(l.get("chave")) in V]
    top = sorted(vend, key=lambda l: -(l.get("meta") or 0))[:15]
    r["graficos"].append({
        "titulo": "Atingimento do faturamento por vendedor (%)",
        "rotulos": [(l.get("nome") or l.get("rotulo", "")).split(" ")[0]
                    for l in top],
        "series": [{"nome": "atingimento", "cor": VERDE,
                    "valores": [pct_de(l.get("realizado") or 0, l.get("meta"))
                                or 0 for l in top]}],
        "formato": "pct"})
    r.update({"estilo": "bap",
              "faixa": f"FAROL DE METAS EQUIPE · {rotulo_mes(comp)}",
              "eyebrow": bv_cabecalho(), "titulo_curto": "Farol de Metas Equipe"})
    if txt:
        r["subtitulo"] += f" · {txt}"
        r["tabelas"] = vistas_escopo(ctx, ac, comp, V, T, sup)
    else:
        r["tabelas"] = vistas_do_farol(ctx, ac, comp)
    ger = next((t for t in r["tabelas"] if t["titulo"] == "Por gerente"), None)
    if ger:
        hj_b = _hoje_do_farol(ctx, ac, comp).get("_bap")
        cart_ger = _cartoes_farol(ger["linhas"], ger["colunas"],
                                  ac.get("dias_restantes") or 0, _esperado(ac),
                                  hoje_total=hj_b)
        # (14/10) AUDITORIA: o cartao de POSITIVACAO e o numero de clientes
        # DISTINTOS que compraram no mes (= Painel, Farol de Clientes e
        # Indicadores Executivos). A soma das linhas contava duas vezes o
        # cliente atendido por um vendedor da equipe e por um de fora do
        # planner. As linhas por vendedor seguem a regra da RV (liquido do
        # vendedor no cliente > 0) - nada muda na RV.
        if not txt:
            n_pos = len(clientes_positivados(ctx, comp))
            idx = {c["nome"]: i for i, c in enumerate(ger["colunas"])}
            meta_p = sum(l[idx["POSIT. META"]] or 0 for l in ger["linhas"]) \
                if "POSIT. META" in idx else 0.0
            cart_ger = [_cartao_indicador(
                "Positivação", meta_p, n_pos, ac.get("dias_restantes") or 0,
                _esperado(ac), real_proj=n_pos - (hj_b or {}).get(
                    "POSIT.", 0)) if k.get("rotulo") == "Positivação" else k
                for k in cart_ger]
        r["kpis"] = cart_ger
        # (10/11) o estado do faturamento = a filial da nota
        try:
            r["_por_filial"] = por_filial_da_nota(ctx, comp)
        except Exception:                               # noqa: BLE001
            r["_por_filial"] = {}
        for t in r["tabelas"]:
            f = t.get("kpis_de")
            if f is None or t["titulo"] in ("Por família da peça",
                                            "Por categoria") or \
                    t["titulo"].startswith("Top "):
                continue
            n = len(t["linhas"])
            t["kpis_de"] = (lambda ls, f=f, n=n:
                            cart_ger if len(ls) == n else f(ls))
    # (04/11, Alexandre) "Gerente, supervisor e vendedor nao precisa ficar
    # em 3 abas. faca so uma" + "uma mesma aba para Acomp. RH que tera a
    # meta do RH deles" - SO NA TELA (rn.montar(..., tela=True)): o Painel
    # do Diretor, o e-mail da parcial, a RV e o resumo seguem lendo as
    # tabelas Por gerente / Por supervisor / Por vendedor
    r["_equipe"] = (lambda r_=r: _juntar_equipe(r_, ctx, ac, comp, txt, V, T,
                                                sup))
    if not dados.get("tem_visitas"):
        r["avisos"].append(
            f"Sem o arquivo de visitas de {rotulo_mes(comp)} "
            f"(RELATORIOS\\Visitas\\{comp.replace('-', '')}.csv): "
            f"visita realizada fica zerada.")
    if T is not None:
        r["avisos"].append("Com recorte de segmento/UF/cidade/bairro, visita "
                           "e RV não se abrem por território: ficam em branco.")
    if dados.get("modo") == "crescimento":
        r["avisos"].append(
            f"Meta de {rotulo_mes(comp)} não cadastrada no Gerador de Meta: "
            f"aqui está a meta calculada pelo histórico (M3M).")
    return r


TITULOS_PESSOA = (("Por gerente", "GERENTE"), ("Por supervisor", "SUPERVISOR"),
                  ("Por vendedor", "VENDEDOR"))


def _so_meta_rh(t_, resta):
    """(04/11) A aba Acomp. RH: sai o DESAFIO (FAT. META e o % dele); a
    META e a RH, o NEC./DIA contra ela."""
    nomes = [c["nome"] for c in t_["colunas"]]
    if "FAT. META RH" not in nomes:
        return t_
    t_ = dict(t_)
    i_d, i_pd = nomes.index("FAT. META"), nomes.index("FAT. % ATING.")
    i_rh, i_r = nomes.index("FAT. META RH"), nomes.index("FAT. REAL")
    i_nec = nomes.index("FAT. NEC./DIA") if "FAT. NEC./DIA" in nomes else None
    fora = {i_d, i_pd}

    def ajusta(l):
        l = list(l)
        if i_nec is not None and isinstance(l[i_rh], (int, float)):
            rh, real = l[i_rh] or 0.0, l[i_r] or 0.0
            l[i_nec] = (max(0.0, rh - real) / resta) if resta else None
        return [x for k, x in enumerate(l) if k not in fora]
    t_["colunas"] = [dict(c, curto="META RH") if c["nome"] == "FAT. META RH"
                     else c for k, c in enumerate(t_["colunas"])
                     if k not in fora]
    t_["linhas"] = [ajusta(l) for l in t_["linhas"]]
    if t_.get("total"):
        t_["total"] = ajusta(t_["total"])
    t_["grupos"] = [(g, n - 2) if g == "FATURAMENTO" else (g, n)
                    for g, n in t_.get("grupos") or []]
    t_.pop("cores_celulas", None)
    return t_


def _empilhar(titulo, tabs):
    """(04/11, Alexandre) Uma aba com TABELINHAS, uma embaixo da outra:
    GERENTE, SUPERVISORES e VENDEDORES (a de vendedores e a principal: os
    filtros, a busca e os cartoes sao dela; as de cima vem inteiras)."""
    vend = tabs.get("VENDEDOR")
    if vend is None:
        return None
    t_ = dict(vend)
    t_["titulo"] = titulo
    t_["titulo_tabela"] = "VENDEDORES"
    t_["juntas_em_cima"] = True
    # (04/11, Alexandre) "Nao quero tambem ter barra de rolar para o lado":
    # as colunas cabem na largura da tela (a letra diminui se precisar)
    t_["sem_rolar_lado"] = True

    def com_rotulo(grupos, rot):
        """(04/11, Alexandre) o nome do nivel na faixa de cima, em cima de
        NOME (antes ficava um espaco em branco), com a cor das demais"""
        g_ = list(grupos or [])
        if g_ and not g_[0][0]:
            g_[0] = (rot, g_[0][1])
        return g_
    t_["grupos"] = com_rotulo(vend.get("grupos"), "VENDEDORES")
    juntas = []
    # (04/11, Alexandre) "deixe o espaco para 4 supervisores tambem e 2
    # gerentes de venda": a tabelinha ja nasce com essas linhas
    for nivel, rot, vagas in (("GERENTE", "GERENTE", 2),
                              ("SUPERVISOR", "SUPERVISORES", 4)):
        t = tabs.get(nivel)
        if not t:
            continue
        # "(sem gerente)", "(sem supervisor)", "(FORA DO PLANNER)": a mesma
        # carteira das linhas de vendedor - ficam so embaixo
        ls = [l for l in t["linhas"] if not texto(l[0]).startswith("(")]
        # sem TOTAL: a linha do gerente ja e o total dos supervisores
        tj = dict(t, titulo=rot, linhas=ls, tons=[""] * len(ls), total=None,
                  grupos=com_rotulo(t.get("grupos"), rot))
        tj.pop("kpis_de", None)
        juntas.append({"tabela": tj, "titulo": rot, "com_total": True,
                       "altura": max(vagas, len(ls))})
    t_["juntas"] = juntas
    return t_


def _juntar_equipe(r, ctx, ac, comp, txt, V, T, sup):
    """(04/11, Alexandre) No Farol de Metas Equipe as abas Por gerente, Por
    supervisor e Por vendedor viram UMA aba (Equipe) com 3 tabelinhas, e
    nasce a Acomp. RH: as mesmas tabelinhas com a META RH e a RV."""
    tabs = {nv: t for t in r["tabelas"] for tit, nv in TITULOS_PESSOA
            if t["titulo"] == tit}
    eq = _empilhar("Equipe", tabs)
    if eq is None:
        return
    novas, pos = [], None
    for t in r["tabelas"]:
        if t["titulo"] in dict(TITULOS_PESSOA):
            if pos is None:
                pos = len(novas)
            continue
        novas.append(t)
    novas.insert(pos or 0, eq)
    antes = _COM_RH[0]
    _COM_RH[0] = True
    try:
        if txt:
            rh_tabs = vistas_escopo(ctx, ac, comp, V, T, sup)
        else:
            rh_tabs = vistas_do_farol(ctx, ac, comp, sem=(
                "uf", "cidade", "bairro", "segmento", "zona"))
    except Exception:                                   # noqa: BLE001
        rh_tabs = []
    finally:
        _COM_RH[0] = antes
    resta = ac.get("dias_restantes") or 0
    tabs_rh = {nv: _so_meta_rh(t, resta) for t in rh_tabs
               for tit, nv in TITULOS_PESSOA if t["titulo"] == tit}
    rh = _empilhar("Acomp. RH", tabs_rh) if tabs_rh else None
    if rh is not None:
        ger_rh = next((t for t in rh_tabs if t["titulo"] == "Por gerente"),
                      None)
        cart_rh = (_cartoes_farol(ger_rh["linhas"], ger_rh["colunas"], resta,
                                  _esperado(ac), hoje_total=_hoje_do_farol(
                                      ctx, ac, comp).get("_bap"))
                   if ger_rh else None)
        if cart_rh:      # o cartao do desafio fica na aba Equipe
            cart_rh = [k for k in cart_rh
                       if "desafio" not in texto(k.get("rotulo")).lower()]
        rh["kpis_de"] = (lambda ls, c_=cart_rh: c_) if cart_rh else None
        novas.insert((pos or 0) + 1, rh)
    r["tabelas"] = novas


def _esperado(ac):
    du, resta = ac.get("dias_uteis_do_mes"), ac.get("dias_restantes")
    return (du - resta) / du * 100.0 if du and resta is not None else None


def _cab_vendedor(com_cod=False):
    """com_cod: o CODIGO DE VENDA (Protheus) na frente do nome - o PDF das
    parciais (06/10)."""
    cab = [col("NOME", "texto", 190),
           dict(col("SUPERVISOR", "texto", 150), pdf_oculta=True)]
    if com_cod:
        cab.insert(0, dict(col("CÓD.", "texto", 60), pdf_larg=24.0))
    return cab


# (06/11, Alexandre: "Vendedor inativo em novembro consta para as parciais
# de meta. ele deve ficar oculto ao nao ser que tenha movimentacao ou venda
# no codigo dele. isso e regra") - o que conta como movimento no mes
_MOV_LINHA = ("realizado", "faturado", "devolvido", "positivados",
              "visitas_realizadas", "cadastros_com_compra",
              "cadastros_no_mes", "notas", "real_pecas")


def _codigos_com_movimento(ctx, comp) -> set:
    """Os codigos de venda com QUALQUER item no mes (nota, devolucao,
    pedido em aberto, pedido excluido), pela data da NF ou do pedido."""
    memo = getattr(ctx, "_cod_mov_memo", None)
    if memo is None:
        memo = ctx._cod_mov_memo = {}
    if comp not in memo:
        cods = set()
        try:
            for it in ctx.tabela["itens"]:
                if any(d and mes_de(d) == comp
                       for d in (it.get("dt_nf"), it.get("dt_pedido"))):
                    for k in ("vend", "vend2"):
                        c = _cod6(it.get(k))
                        if c and c.strip("0"):
                            cods.add(c)
        except Exception:                               # noqa: BLE001
            pass
        memo[comp] = cods
    return memo[comp]


def _inativo_oculto(ctx, comp, l) -> bool:
    """(06/11) REGRA: vendedor INATIVO no Planner do mes fica fora das
    tabelas e parciais de meta, a nao ser que tenha movimento no codigo dele
    no mes (venda, devolucao, pedido, positivacao, visita, cadastro)."""
    if l.get("vendedor_ativo", True) is not False:
        return False
    if any(abs(l.get(k) or 0) > 0.005 for k in _MOV_LINHA):
        return False
    return _cod6(l.get("chave") or l.get("codigo")) not in \
        _codigos_com_movimento(ctx, comp)


def _cods_ocultos(ctx, ac, comp) -> set:
    """(06/11) os codigos dos vendedores inativos sem movimento no mes."""
    return {_cod6(l.get("chave")) for l in
            (ac.get("recortes") or {}).get("vendedor", []) or []
            if _inativo_oculto(ctx, comp, l)}


def _tem_meta_ou_mov(l) -> bool:
    """(06/11) a linha tem alguma meta ou algum movimento no mes?"""
    return any(abs(l.get(k) or 0) > 0.005 for k in (
        "meta", "meta_positivacao", "meta_visita", "meta_pecas")) or any(
        abs(l.get(k) or 0) > 0.005 for k in _MOV_LINHA)


def vistas_do_farol(ctx, ac, comp, corte=None, sem=()):
    """As vistas do Farol de Metas, a equipe inteira (sem recorte):
    gerente, supervisor, vendedor, UF, cidade, bairro, segmento, zona e
    familia. corte: no maximo tantas linhas nos territorios (o PDF)."""
    resta = ac.get("dias_restantes") or 0
    esperado = _esperado(ac)
    mix = _mix_das_linhas(ctx, comp, ac)
    rh_por = ac.get("rh_por") or {}
    slim = ac.get("clientes_slim") or []
    # (06/11, Alexandre: "porque amapa esta aparecendo se nao tem meta nem
    # real") o territorio que so tem a carteira do vendedor inativo sem
    # movimento (o oculto), sem meta e sem venda, sai (UF, cidade, bairro,
    # segmento); os ATIVOS continuam contando todos os clientes (iguais ao
    # Painel Executivo e ao Farol de Clientes)
    ocultos = _cods_ocultos(ctx, ac, comp)
    slim_vivo = [c for c in slim
                 if _cod6(c.get("cod_vendedor")) not in ocultos]
    mapa = ac.get("mapa_cliente") or {}
    equipe = ac.get("equipe_vend") or {}

    def chave_cli(recorte):
        if recorte == "vendedor":
            return lambda c: _cod6(c.get("cod_vendedor"))
        if recorte in ("supervisor", "gerente"):
            return lambda c: texto((equipe.get(_cod6(c.get("cod_vendedor")))
                                    or {}).get(recorte)) or texto(
                                        c.get(recorte))
        if recorte in ("uf", "cidade", "bairro", "segmento"):
            # (12/10) a UF/cidade/bairro de CADA LOJA (um cliente com loja
            # em AM e RR conta nas duas, como no Painel e no Farol de
            # Clientes); zona: a do mapa (o slim nao tem a zona)
            import meta_nucleo as _mn                   # noqa: PLC0415
            return lambda c: _mn.chave_da_linha(recorte, {
                "uf": c.get("uf") or "", "cidade": c.get("cidade") or "",
                "bairro": c.get("bairro") or "",
                "segmento": c.get("segmento") or ""})
        return lambda c: (mapa.get(c["cod_cliente"]) or {}).get(recorte)
    tabelas = []
    for chave, titulo in VISTAS_FAROL:
        if chave in sem:
            continue
        ls = sorted(ac["recortes"].get(chave, []),
                    key=lambda l: -(l.get("meta") or 0))
        if chave == "vendedor":         # (06/11) inativo sem movimento: fora
            ls = [l for l in ls if not _inativo_oculto(ctx, comp, l)]
        elif chave in ("supervisor", "gerente"):
            # (06/11) o "(sem supervisor)" / "(sem gerente)" que so tinha o
            # inativo: sem meta e sem movimento, sai junto
            ls = [l for l in ls if not (
                texto(l.get("nome") or l.get("rotulo")).startswith("(")
                and not (l.get("meta") or 0)
                and not any(abs(l.get(k) or 0) > 0.005 for k in _MOV_LINHA))]
        elif ocultos and chave in TERRITORIOS:
            # (06/11) o territorio so do oculto, sem meta e sem movimento
            vivos = {chave_cli(chave)(c) for c in slim_vivo}
            ls = [l for l in ls if l["chave"] in vivos or _tem_meta_ou_mov(l)]
        if not ls:
            continue
        pessoa = chave in RECORTES_PESSOA
        cart = Counter()
        ativos = _ativos(ctx, slim, chave_cli(chave), cart)
        itens = []
        for l in ls:
            ch = _cod6(l["chave"]) if chave == "vendedor" else l["chave"]
            rh = None if pessoa else (rh_por.get(chave) or {}).get(l["chave"],
                                                                   0.0)
            cab = [l.get("nome") or l.get("rotulo")] if pessoa else \
                _partes_da_linha(chave, l)
            if chave == "vendedor" and corte:   # parcial: o codigo de venda
                cab.insert(0, ch)
            if chave == "vendedor":         # o supervisor curto: cabe na tela
                cab.append(_nome_curto(l.get("supervisor"))
                           or "(sem supervisor)")
            d_ = _d_da_linha(l, rh)
            d_["ativos"] = ativos.get(ch if chave == "vendedor"
                                      else l["chave"], 0)
            if chave == "uf":
                # (10/11) o realizado do estado = filial da nota (a meta
                # continua a do territorio)
                m_ = mix.get(("uf", ch)) or _mix_novo()
                d_["real"], d_["rpe"] = m_["real"], m_["pecas"]
                d_["rp"] = len(m_["cli"])
            itens.append((cab, d_, mix.get((chave, ch)), l["chave"]))
        if pessoa:
            itens = [x[:3] for x in itens]
        else:
            itens = _ordenar_territorio(chave, itens, cart,
                                        TOP_CIDADES if corte else None)
        if corte and chave in ("cidade", "bairro"):      # o PDF da parcial
            titulo = f"Top {TOP_CIDADES if chave == 'cidade' else TOP_BAIRROS}" \
                     f" {'cidades' if chave == 'cidade' else 'bairros'}"
        tot_d = _somar_d([d for _c, d, _m in itens], com_rv=pessoa)
        if pessoa:
            tot_l = ac["totais"].get(chave)
            if tot_l:
                tot_d.update({k: v for k, v in _d_da_linha(tot_l).items()
                              if k not in ("rv_fat", "rv_pos", "rv_vis",
                                           "rv_tot")})
        tot_m = _mix_total([m for _c, _d, m in itens])
        cab_cols = _cab_vendedor(bool(corte)) if chave == "vendedor" else [
            col("NOME", "texto", 190)] if pessoa else _cab_territorio(chave)
        tabelas.append(_tabela_farol(
            titulo, cab_cols, itens, (["TOTAL"] + [""] * (len(cab_cols) - 1),
                                      tot_d, tot_m),
            resta, esperado, tipo="pessoa" if pessoa else "territorio",
            hoje_de=(_hoje_do_farol(ctx, ac, comp).get(chave)
                     if pessoa else None),
            filtros=("SUPERVISOR",) if chave == "vendedor" else ()))
        if chave == "vendedor":          # o TOP 30 clientes vem logo depois
            tabelas.append(_top_clientes_tabela(
                ctx, comp, [c for c in slim if not c.get("fora_do_planner")],
                mix, resta, esperado))
    # a familia: a BAP inteira (o recorte de cima abre por pessoa/territorio)
    cli = [c for c in ac.get("clientes_slim") or []
           if not c.get("fora_do_planner")]
    mix_c = {k[1][2]: x for k, x in mix.items()
             if k[0] == "categoria" and k[1][0] == "bap"}
    tabelas.append(_familia_tabela(ac, cli, mix_c, resta, esperado,
                                   (ac.get("categoria_meta") or {}).get("bap"),
                                   categoria=True))
    mix_f = {k[1][2]: x for k, x in mix.items()
             if k[0] == "familia" and k[1][0] == "bap"}
    tabelas.append(_familia_tabela(ac, cli, mix_f, resta, esperado,
                                   (ac.get("familia_meta") or {}).get("bap")))
    return tabelas


def _familia_tabela(ac, cli, mix_f, resta, esperado, meta_pronta=None,
                    categoria=False):
    """Por família da peça (ou, categoria=True, por CATEGORIA BAP: linha
    leve, pesada, moto, pneu, bateria, lubrificantes): meta comercial e RH
    (a do cliente aberta pelo mix do M3M dele) contra o que foi vendido."""
    fator = ac.get("fator_rh_vendedor") or {}
    campo = "meta_categoria" if categoria else "meta_familia"
    com_f, rh_f = defaultdict(float), defaultdict(float)
    for c in cli:
        fv = fator.get(c.get("cod_vendedor"), 0.0)
        for f, v in (c.get(campo) or {}).items():
            com_f[f] += v
            rh_f[f] += v * fv
    if meta_pronta:
        com_f = defaultdict(float, meta_pronta)
    if categoria:      # as seis sempre (maior meta primeiro); OUTROS so se
        ordem = list(mn_categorias())             # houver
        fams = ordem + sorted(f for f in set(com_f) | {
            f for f, x in mix_f.items() if x["real"] or x["m3m"]}
            if f not in ordem and ((com_f.get(f) or 0) >= 0.5 or (
                mix_f.get(f) or {}).get("real") or (
                    mix_f.get(f) or {}).get("m3m")))
        fams.sort(key=lambda f: (-(com_f.get(f) or 0),
                                 -(mix_f.get(f) or {}).get("real", 0)))
    else:
        fams = sorted(set(com_f) | {f for f, x in mix_f.items()
                                    if x["real"] or x["m3m"]},
                      key=lambda f: (-(com_f.get(f) or 0),
                                     -(mix_f.get(f) or {}).get("real", 0)))
    itens = []
    for f in fams:
        x = mix_f.get(f)
        itens.append(([f], {"meta": com_f.get(f) or 0.0,
                            "meta_rh": rh_f.get(f, 0.0),
                            "real": x["real"] if x else 0.0, "mp": None,
                            "rp": len(x["cli"]) if x else 0, "mv": None,
                            "rv": None, "mpe": None, "rpe": None}, x))
    tot_d = _somar_d([d for _c, d, _m in itens], com_rv=False)
    tot_m = _mix_total([m for _c, _d, m in itens])
    tot_d.update({"rp": len(tot_m["cli"]), "mp": None, "mpe": None,
                  "rpe": None})
    return _tabela_farol("Por categoria" if categoria else
                         "Por família da peça",
                         [col("CATEGORIA" if categoria else "FAMÍLIA",
                              "texto", 190)], itens,
                         (["TOTAL"], tot_d, tot_m), resta, esperado,
                         tipo="familia")


def vistas_escopo(ctx, ac, comp, V=None, T=None, sup=None, corte=None,
                  zona=False):
    """As MESMAS vistas do Farol, so com o recorte: V = os vendedores
    (pela nota, e a carteira deles); T = o territorio do cliente. Sem
    territorio, as linhas de pessoa sao as do acompanhamento (com visita e
    RV); com territorio, saem da soma dos clientes e das notas."""
    resta = ac.get("dias_restantes") or 0
    esperado = _esperado(ac)
    equipe = ac.get("equipe_vend") or {}
    nomes = _nomes_vendedor(ac)
    slim = [c for c in ac.get("clientes_slim") or []
            if not c.get("fora_do_planner")]
    attr = {}
    for c in slim:
        attr.setdefault(c["cod_cliente"], c)
    ocultos = _cods_ocultos(ctx, ac, comp)      # (06/11) inativo sem mov.
    cli = [c for c in slim
           if (V is None or _cod6(c.get("cod_vendedor")) in V)
           and (T is None or T(_chaves_terr(c)))]

    def chaves(it):
        cod = _cod6(it.get("vend"))
        if V is not None and cod not in V:
            return []
        k = _chaves_terr(attr.get(it["cliente"]) or ctx.cliente(it["cliente"])
                         or {})
        if T is not None and not T(k):
            return []
        eq = equipe.get(cod) or {}
        return ([("vendedor", cod),
                 ("supervisor", texto(eq.get("supervisor"))
                  or FORA_PLANNER_META),
                 ("gerente", texto(eq.get("gerente")) or FORA_PLANNER_META),
                 ("familia", ctx.familia(it["cod"])),
                 ("categoria", ctx.categoria_bap(it["cod"])),
                 ("cliente", it["cliente"])]
                + [(r_, (uf_da_filial(it.get("filial")) or k[r_])
                    if r_ == "uf" else k[r_]) for r_ in TERRITORIOS])
    mix = _juntar_itens(ctx, comp, chaves, {})
    fator = ac.get("fator_rh_vendedor") or {}

    def soma_clientes(chave_de):
        g = defaultdict(lambda: {"meta": 0.0, "meta_rh": 0.0, "real": 0.0,
                                 "mp": 0.0, "rp": 0, "mv": None, "rv": None,
                                 "mpe": 0.0, "rpe": 0.0})
        for c in cli:
            d = g[chave_de(c)]
            d["meta"] += c.get("meta") or 0.0
            d["meta_rh"] += c.get("meta_rh_vend") or 0.0
            d["mp"] += c.get("meta_positivacao") or 0.0
            d["rp"] += 1 if c.get("positivou") else 0
            d["mpe"] += c.get("meta_pecas") or 0.0
        return g

    def com_vendas(g, recorte):
        for (r_, k), x in mix.items():
            if r_ == recorte:
                d = g[k]
                d["real"] = x["real"]
                d["rpe"] = x["pecas"]
                if recorte == "uf":     # (10/11) positivado pela filial
                    d["rp"] = len(x["cli"])
        return g
    tabs = []
    terr_de = {c["cod_cliente"]: _chaves_terr(c) for c in cli}
    # ---- as pessoas
    if T is None:
        vend_l = [l for l in ac["recortes"].get("vendedor", [])
                  if (V is None or _cod6(l.get("chave")) in V)
                  and _cod6(l.get("chave")) not in ocultos]
        d_v = {_cod6(l["chave"]): _d_da_linha(l) for l in vend_l}
    else:
        g = com_vendas(soma_clientes(lambda c: _cod6(c.get("cod_vendedor"))),
                       "vendedor")
        d_v = {k: d for k, d in g.items()
               if (V is None or k in V) and k not in ocultos}
    at_v = _ativos(ctx, cli, lambda c: _cod6(c.get("cod_vendedor")))
    for c_, d in d_v.items():
        d["ativos"] = at_v.get(c_, 0)
    sup_de = {c: texto((equipe.get(c) or {}).get("supervisor"))
              or "(sem supervisor)" for c in d_v}
    ger_de = {c: texto((equipe.get(c) or {}).get("gerente"))
              or "(sem gerente)" for c in d_v}
    for nivel, de in (("gerente", ger_de), ("supervisor", sup_de)):
        grupos = defaultdict(list)
        for c_, d in d_v.items():
            grupos[de[c_]].append(d)
        itens = []
        for nome, ds in grupos.items():
            if nivel == "supervisor" and sup is not None:
                d = _d_da_linha(sup)
                d["ativos"] = sum(x.get("ativos") or 0 for x in ds)
            else:
                d = _somar_d(ds, com_rv=False)
            itens.append(([nome], d, mix.get((nivel, nome))))
        itens.sort(key=lambda x: -(x[1]["meta"] or 0))
        tot = (["TOTAL"], _somar_d([d for _c, d, _m in itens], com_rv=False),
               _mix_total([m for _c, _d, m in itens])) \
            if len(itens) > 1 else None
        tabs.append(_tabela_farol(f"Por {nivel}", [col("NOME", "texto", 190)],
                                  itens, tot, resta, esperado,
                                  hoje_de=_hoje_do_farol(ctx, ac, comp).get(
                                      nivel)))
    com_cod = bool(corte)               # parcial: o codigo de venda
    itens_v = sorted([(([c_] if com_cod else [])
                       + [nomes.get(c_, c_), _nome_curto(sup_de[c_])], d,
                       mix.get(("vendedor", c_))) for c_, d in d_v.items()],
                     key=lambda x: -(x[1]["meta"] or 0))
    tot_v = (["TOTAL", ""] + ([""] if com_cod else []),
             _somar_d([d for _c, d, _m in itens_v],
                                     com_rv=T is None),
             _mix_total([m for _c, _d, m in itens_v])) \
        if len(itens_v) > 1 else None
    tabs.append(_tabela_farol("Por vendedor", _cab_vendedor(com_cod), itens_v,
                              tot_v,
                              resta, esperado, filtros=("SUPERVISOR",),
                              hoje_de=_hoje_do_farol(ctx, ac, comp).get(
                                  "vendedor")))
    tabs.append(_top_clientes_tabela(ctx, comp, cli, mix, resta, esperado))
    # ---- os territorios
    for recorte, titulo in (("uf", "Por UF"), ("cidade", "Por cidade"),
                            ("bairro", "Por bairro"),
                            ("segmento", "Por segmento")):
        g = com_vendas(soma_clientes(lambda c, r_=recorte:
                                     _chaves_terr(c)[r_]), recorte)
        if ocultos:
            # (06/11) o territorio so do vendedor inativo sem movimento (o
            # Amapa do 000040), sem meta e sem venda, sai da tabela
            vivos = {_chaves_terr(c)[recorte] for c in cli
                     if _cod6(c.get("cod_vendedor")) not in ocultos}
            g = {k: d for k, d in g.items() if k in vivos or any(
                abs(d.get(x) or 0) > 0.005
                for x in ("meta", "meta_rh", "real", "mp", "rp", "mpe",
                          "rpe"))}
        cart_t = Counter()
        at_t = _ativos(ctx, cli, lambda c, r_=recorte: terr_de[
            c["cod_cliente"]][r_], cart_t)
        for k_, d_ in g.items():
            d_["ativos"] = at_t.get(k_, 0)
        itens = _ordenar_territorio(
            recorte, [(_partes_do_rotulo(recorte, k), d,
                       mix.get((recorte, k)), k) for k, d in g.items()],
            cart_t, TOP_CIDADES if corte else None)
        if corte and recorte in ("cidade", "bairro"):    # o PDF da parcial
            titulo = (f"Top {TOP_CIDADES} cidades" if recorte == "cidade"
                      else f"Top {TOP_BAIRROS} bairros")
        tot = (_linha_vazia(recorte, "TOTAL"),
               _somar_d([d for _c, d, _m in itens], com_rv=False),
               _mix_total([m for _c, _d, m in itens]))
        tabs.append(_tabela_farol(titulo, _cab_territorio(recorte), itens,
                                  tot, resta, esperado, tipo="territorio"))
    mix_c = {k: x for (r_, k), x in mix.items() if r_ == "categoria"}
    tabs.append(_familia_tabela(ac, cli, mix_c, resta, esperado,
                                categoria=True))
    mix_f = {k: x for (r_, k), x in mix.items() if r_ == "familia"}
    tabs.append(_familia_tabela(ac, cli, mix_f, resta, esperado))
    _ = fator, zona
    return tabs


TOP_CLIENTES = 30
TOP_CIDADES = 30            # no PDF da parcial: as 30 cidades com mais
#                             clientes ativos (o resto em DEMAIS)


def _fat_6_meses(ctx, comp) -> dict:
    """{cliente: faturamento liquido (venda - devolucao) nos 6 meses
    fechados antes da competencia}."""
    guardado = getattr(ctx, "_fat6", None)
    if guardado and guardado[0] == comp:
        return guardado[1]
    meses = set(_meses_antes(comp, 6))
    soma = defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["dt_nf"] and it["tipo"] in ("VND", "DEV") and \
                mes_de(it["dt_nf"]) in meses:
            soma[it["cliente"]] += _liquido(it) or 0.0
    ctx._fat6 = (comp, soma)
    return soma


def _top_clientes_tabela(ctx, comp, cli, mix, resta, esperado,
                         n=TOP_CLIENTES):
    """TOP 30 CLIENTES da carteira (do recorte): os de maior faturamento
    nos ultimos 6 meses; faltando, os de maior LIMITE; faltando ainda, os
    que houver. As mesmas colunas dos territorios (meta comercial e RH,
    real, positivacao, pecas e mix), com o FAT. 6 MESES na frente.
    Na tela, os filtros UF, CIDADE, BAIRRO, SUPERVISOR e VENDEDOR refazem o
    top 30 dentro do filtro (a tabela leva a carteira inteira, na ordem do
    ranking, em "linhas_filtro"); o PDF e o Excel levam os 30."""
    por = {}
    for c in cli:
        d = por.setdefault(c["cod_cliente"], {
            "meta": 0.0, "meta_rh": 0.0, "real": 0.0, "mp": 0.0, "rp": 0,
            "mv": None, "rv": None, "mpe": 0.0, "rpe": 0.0, "_c": c})
        d["meta"] += c.get("meta") or 0.0
        d["meta_rh"] += c.get("meta_rh_vend") or 0.0
        d["mp"] += c.get("meta_positivacao") or 0.0
        d["rp"] = max(d["rp"], 1 if c.get("positivou") else 0)
        d["mpe"] += c.get("meta_pecas") or 0.0
    fat = _fat_6_meses(ctx, comp)

    def limite(k):
        try:
            return float(ctx.cliente(k).get("limite") or 0)
        except (TypeError, ValueError):
            return 0.0
    # O RANKING: faturamento 6 meses > limite > meta
    ranking = sorted(por, key=lambda k: (
        0 if fat.get(k, 0) > 0 else 1 if limite(k) > 0 else 2,
        -(fat.get(k, 0) if fat.get(k, 0) > 0 else limite(k) or
          por[k]["meta"])))
    itens = []
    for k in ranking:
        d = por[k]
        c = d.pop("_c")
        x = mix.get(("cliente", k))
        if x:
            d["real"], d["rpe"] = x["real"], x["pecas"]
        d["ativos"] = fat.get(k, 0.0)        # a 1a coluna: FAT. 6 MESES
        nome = texto(ctx.nome_cliente(k)) or k
        if not nome.startswith(k):
            nome = f"{k} - {nome}"
        cid, uf = texto(c.get("cidade")), texto(c.get("uf"))
        vend = _cod6(c.get("cod_vendedor"))
        itens.append(([nome, f"{cid}/{uf}" if cid else "",
                       texto(c.get("segmento")) or "(SEM SEGMENTO)", uf or "?",
                       texto(c.get("bairro")) or "?",
                       texto(c.get("supervisor")) or "(SEM SUPERVISOR)",
                       ctx.vendedor(vend) if vend else "(sem vendedor)"],
                      d, x))

    def oculta(nome, larg=120):
        return dict(col(nome, "texto", larg), oculta=True, pdf_oculta=True)
    cab = [dict(col("CLIENTE", "texto", 280), pdf_larg=112.0),
           dict(col("CIDADE", "texto", 160), pdf_larg=72.0),
           col("SEGMENTO", "texto", 150), oculta("UF", 40), oculta("BAIRRO"),
           oculta("SUPERVISOR", 160), oculta("VENDEDOR", 200)]

    def total_de(its):
        return (["TOTAL"] + [""] * 6,
                _somar_d([d for _c, d, _m in its], com_rv=False),
                _mix_total([m for _c, _d, m in its]))
    t = _tabela_farol(f"Top {n} clientes", cab, itens, total_de(itens[:n]),
                      resta, esperado, tipo="cliente",
                      filtros=("UF", "CIDADE", "BAIRRO", "SEGMENTO",
                               "SUPERVISOR", "VENDEDOR"))
    # a carteira inteira (na ordem do ranking) para os filtros da tela
    tot_real = sum(d["real"] for _c, d, _m in itens)
    de_linha = {id(l): it for l, it in zip(t["linhas"], itens)}

    def total_da_tela(ls):
        its = [de_linha[id(l)] for l in ls if id(l) in de_linha]
        tc, td, tm = total_de(its)
        return list(tc) + _valores_farol(td, tm, tot_real, resta, "cliente")
    t["linhas_filtro"], t["tons_filtro"] = t["linhas"], t["tons"]
    i_meta = [c_["nome"] for c_ in t["colunas"]].index("FAT. META")
    i_fat = [c_["nome"] for c_ in t["colunas"]].index("FAT. 6 MESES")
    ordem = sorted(range(min(n, len(t["linhas"]))), key=lambda i: (
        -(t["linhas"][i][i_meta] or 0), -(t["linhas"][i][i_fat] or 0)))
    t["linhas"] = [t["linhas"][i] for i in ordem]   # da maior meta p/ menor
    t["tons"] = [t["tons"][i] for i in ordem]
    t["top_n"] = n
    t["ordem_top"] = (i_meta, i_fat)
    t["total_de"] = total_da_tela
    return t


def bv_cabecalho() -> str:
    from bap_visual import CABECALHO_PDF               # noqa: PLC0415
    return CABECALHO_PDF


def mn_categorias() -> tuple:
    """(15/10) As CATEGORIAS do Catalogo BAP 2026, na ordem do catalogo."""
    try:
        import catalogo_bap as cbp                      # noqa: PLC0415
        return tuple(c for c in cbp.ORDEM_CATEGORIA if c != "OUTROS")
    except Exception:                                   # noqa: BLE001
        return ("PEÇAS LINHA LEVE", "PEÇAS LINHA PESADA", "PEÇAS LINHA MOTO",
                "BATERIAS", "LUBRIFICANTES", "QUÍMICOS", "PNEUS",
                "ACESSÓRIOS")


# (15/10, Alexandre) OS FILTROS DE PRODUTO: CATEGORIA, SISTEMA, FAMILIA e
# LINHA do Catalogo BAP 2026 (a referencia e o ESTOQUE_BAP)
CLASSE_PRODUTO = ("CATEGORIA", "SISTEMA", "FAMÍLIA", "LINHA")
META_DA_CLASSE = (("FAMÍLIA", "meta_familia"), ("SISTEMA", "meta_sistema"),
                  ("CATEGORIA", "meta_categoria"), ("LINHA", "meta_linha"))


def ordem_da_classe(nome, valores) -> list:
    """As opcoes de um filtro na ordem do catalogo (familia: alfabetica)."""
    try:
        import catalogo_bap as cbp                      # noqa: PLC0415
        ordem = {"CATEGORIA": cbp.ORDEM_CATEGORIA,
                 "SISTEMA": cbp.ORDEM_SISTEMA,
                 "LINHA": cbp.ORDEM_LINHA}.get(nome, ())
        return cbp.ordenar(valores, ordem)
    except Exception:                                   # noqa: BLE001
        return sorted(set(v for v in valores if v))


def meta_do_filtro(s_, esc):
    """A meta do cliente com o filtro de produto: a do grupo mais fino
    escolhido (FAMILIA > SISTEMA > CATEGORIA > LINHA). None: sem filtro."""
    for nome, campo in META_DA_CLASSE:
        if esc.get(nome):
            return (s_.get(campo) or {}).get(esc[nome], 0.0)
    return None


def _ativos(ctx, clientes, chave_de, carteira=None) -> Counter:
    """CLIENTES ATIVOS por linha: os da carteira com STATUS PLANNER ATIVO
    (CHURN e NUNCA COMPROU contam; INATIVO nao), sem repetir loja.
    carteira: um Counter que recebe TODOS os clientes da linha."""
    vistos, conta = set(), Counter()
    for c in clientes:
        if c.get("fora_do_planner"):
            continue
        k = chave_de(c)
        if (k, c["cod_cliente"]) in vistos:
            continue
        vistos.add((k, c["cod_cliente"]))
        if carteira is not None:
            carteira[k] += 1
        st = (ctx.cliente(c["cod_cliente"]) or {}).get("status")
        if status_planner_binario(st, (ctx.cliente(c["cod_cliente"]) or {})
                                  .get("inativo")) == "ATIVO":
            conta[k] += 1
    return conta


# =========================================================================
# (12/10) A CARTEIRA DO MES - a MESMA em todos os farois (auditoria): os
# clientes do PLANNER do mes da meta com vendedor, um por CODIGO. O
# segmento, a UF, a cidade e o vendedor de cada loja sao os desse PLANNER
# (o mesmo da meta); mudou na BASE_CLIENTE no meio do mes, vale no proximo
# PLANNER. Venda de quem nao esta nela: (FORA DO PLANNER). CLIENTES = os
# codigos da carteira sem os inativados no Planner (o CLIENTES ATIVOS do
# Farol de Metas e o CLIENTES do Painel Executivo).
# =========================================================================
def carteira_do_mes(ctx):
    """{"lojas": {(cod, loja): cliente do PLANNER}, "mapa": {cod: segmento,
    uf, cidade... da 1a loja}, "ac": o acompanhamento} - ou None (sem
    PLANNER/meta do mes)."""
    if not hasattr(ctx, "_carteira"):
        ctx._carteira = None
        try:
            ac = meta_do_periodo(ctx)["acomp"] or {}
        except Exception:                               # noqa: BLE001
            ac = {}
        slim = [c for c in ac.get("clientes_slim") or []
                if not c.get("fora_do_planner")]
        if slim:
            lojas = {}       # a loja como esta no PLANNER ("1" e "01" sao
            for c in slim:   # duas linhas la - Divergencias: duplicado)
                lojas.setdefault((_cod6(c.get("cod_cliente")),
                                  texto(c.get("loja"))), c)
            # quem comprou sem estar no PLANNER: o Gerador de Meta poe o
            # cliente no realizado com o segmento/UF dele (fora_do_planner)
            fora = {}
            for c in ac.get("clientes_slim") or []:
                if c.get("fora_do_planner"):
                    fora.setdefault(_cod6(c.get("cod_cliente")), c)
            ctx._carteira = {"lojas": lojas, "fora": fora,
                             "mapa": ac.get("mapa_cliente") or {}, "ac": ac}
    return ctx._carteira


def territorio_do_cliente(ctx, cod, campo):
    """segmento, uf ou cidade de um codigo (a venda dele cai nessa linha
    em todos os farois): o do PLANNER do mes (1a loja); quem comprou fora
    do PLANNER: o que o Gerador de Meta deu a ele; senao FORA DO PLANNER."""
    cart = carteira_do_mes(ctx)
    if cart is None:
        return texto(ctx.cliente(cod).get(campo)) or (
            "(SEM SEGMENTO)" if campo == "segmento" else "")
    cod = _cod6(cod)
    m = cart["mapa"].get(cod)
    if m:
        v = m.get(campo) or ""
        return v.split("|")[-1] if campo == "cidade" else v
    f = cart["fora"].get(cod)
    if f and texto(f.get(campo)):
        return texto(f.get(campo)).upper() if campo != "segmento" \
            else texto(f.get(campo))
    return FORA_PLANNER_META


def segmento_do_cliente(ctx, cod) -> str:
    """O SEGMENTO de um codigo de cliente em todos os farois: o do PLANNER
    do mes (a 1a loja, como no Farol de Metas); fora dele: FORA DO PLANNER."""
    return territorio_do_cliente(ctx, cod, "segmento")


def _clientes_da_carteira(ctx, cart):
    """As lojas da carteira do mes com o cadastro da BASE_CLIENTE (limite,
    status, contato...) e o segmento/UF/cidade/vendedor do PLANNER do mes."""
    base = {(c["cod"], _loja2(c.get("loja"))): c
            for c in ctx.base.get("clientes") or []}
    pessoas = ctx.base.get("pessoas") or {}
    saida = []
    for (cod, loja_p), s in cart["lojas"].items():
        loja = _loja2(loja_p)
        b = base.get((cod, loja))
        c = dict(b) if b else {
            "cod": cod, "loja": loja, "nome": "", "fantasia": "",
            "endereco": "", "numero": "", "contato": "", "bairro": "",
            "status": ctx.status_planner(cod, loja), "chave": f"{cod}-{loja}",
            "inativo": False, "curva": "", "limite": 0.0, "limite_disp": 0.0,
            "atraso": 0.0, "receita_6m": 0.0, "media_6m": 0.0,
            "dias_sem_compra": None, "ultima_compra": None, "zona": "",
            "zona_nome": ""}
        if not b:
            t = ctx.tabela["clientes"].get(cod, {})
            c["nome"], c["fantasia"] = t.get("nome", ""), t.get("fantasia", "")
        vend = _cod6(s.get("cod_vendedor")) if s.get("cod_vendedor") else ""
        c.update({
            "segmento": texto(s.get("segmento")) or "(SEM SEGMENTO)",
            "uf": texto(s.get("uf")).upper() or c.get("uf", ""),
            "cidade": texto(s.get("cidade")).upper() or c.get("cidade", ""),
            "vend": vend,
            "vend_nome": (pessoas.get(vend) or {}).get("nome")
            or c.get("vend_nome") or vend or "(SEM VENDEDOR)",
            "supervisor": texto(s.get("supervisor")) or "(SEM SUPERVISOR)",
            "_meta": s})
        saida.append(c)
    return saida


TOP_BAIRROS = 30


def _ordenar_territorio(recorte, itens, cart=None, top_cidades=None):
    """UF e cidade: TODAS, em ordem alfabetica (no PDF da parcial,
    top_cidades: as 30 de MAIOR META - empate/sem meta: mais clientes na
    carteira - e o resto em DEMAIS). Bairro: o mesmo (as 30 de maior meta,
    desempate pela carteira), o resto numa linha DEMAIS. Os outros: maior
    meta primeiro."""
    if recorte == "cidade" and top_cidades:
        cart = cart or {}          # maior META; sem meta, mais clientes
        ordem = sorted(itens, key=lambda x: (     # cadastrados (carteira)
            str(x[0][-1]).startswith(("(", "?")),
            -(x[1]["meta"] or 0), -cart.get(x[3], 0)))
        vivos, resto = ordem[:top_cidades], ordem[top_cidades:]
        saida = [x[:3] for x in vivos]
        if resto:
            saida.append((_linha_vazia("cidade", f"DEMAIS CIDADES "
                                                  f"({len(resto)})"),
                          _somar_d([x[1] for x in resto], com_rv=False),
                          _mix_total([x[2] for x in resto])))
        return saida
    if recorte in ("uf", "cidade"):     # pelo nome da cidade (ou da UF)
        return [x[:3] for x in sorted(
            itens, key=lambda x: (str(x[0][-1]).startswith(("(", "?")),
                                  sem_acento(str(x[0][-1])),
                                  sem_acento(str(x[0][0]))))]
    if recorte == "bairro":
        cart = cart or {}
        ordem = sorted(itens, key=lambda x: (     # maior META; sem meta,
            str(x[0][-1]).startswith(("(", "?")),  # mais clientes na carteira
            -(x[1]["meta"] or 0), -cart.get(x[3], 0)))
        vivos, resto = ordem[:TOP_BAIRROS], ordem[TOP_BAIRROS:]
        saida = [x[:3] for x in vivos]
        if resto:
            saida.append((_linha_vazia("bairro", f"DEMAIS BAIRROS "
                                                  f"({len(resto)})"),
                          _somar_d([x[1] for x in resto], com_rv=False),
                          _mix_total([x[2] for x in resto])))
        return saida
    return [x[:3] for x in sorted(itens, key=lambda x: -(x[1]["meta"] or 0))]


def _nome_curto(nome) -> str:
    """PRIMEIRO e ULTIMO nome (o que esta entre parenteses fica)."""
    nome = texto(nome)
    partes = nome.split()
    if len(partes) <= 2 or nome.startswith("(") or "(" in nome:
        return nome
    return f"{partes[0]} {partes[-1]}"


def _cortar(itens, corte, n_cab):
    """As linhas com meta ou venda (no maximo `corte`), e o resto numa
    linha DEMAIS."""
    vivos = [x for x in itens if x[1]["meta"] > 0.5 or x[1]["real"]][:corte]
    ids = {id(x) for x in vivos}
    resto = [x for x in itens if id(x) not in ids]
    if not resto:
        return vivos
    cab = [f"DEMAIS ({len(resto)})"] + [""] * (n_cab - 1)
    return vivos + [(cab, _somar_d([x[1] for x in resto], com_rv=False),
                     _mix_total([x[2] for x in resto]))]


TRIMESTRES = ("1º", "2º", "3º", "4º")


def _tri_escolhido(ctx, tris):
    """O trimestre da tela: o que foi escolhido; sem escolha, o de hoje -
    e se o de hoje ainda nao tem meta, o ultimo que tem (com recado)."""
    def tem_meta(t):
        return (t["fechamento"]["total"]["meses_com_meta"] or 0) > 0
    v = ctx.param("TRIMESTRE")
    if v:
        try:
            n = int(v)
            return next(t for t in tris if t["numero"] == n), None
        except (TypeError, ValueError, StopIteration):
            pass
    ano = int(str((tris[0]["meses"] or ["0000"])[0])[:4]) if tris else 0
    n_hoje = (ctx.hoje.month - 1) // 3 + 1 if ano == ctx.hoje.year else 4
    hoje_t = next((t for t in tris if t["numero"] == n_hoje), None)
    if hoje_t and tem_meta(hoje_t):
        return hoje_t, None
    antes = [t for t in tris if t["numero"] <= n_hoje and tem_meta(t)]
    if antes:
        return antes[-1], (f"O {TRIMESTRES[n_hoje - 1]} trimestre ainda não "
                           f"tem meta cadastrada: mostrando o "
                           f"{TRIMESTRES[antes[-1]['numero'] - 1]}.")
    return hoje_t or (tris[0] if tris else None), None


def indicadores_executivos(ctx):
    """
    PAINEL EXECUTIVO DO TRIMESTRE (06/10): por indicador, META, REAL e
    % ATING. de cada mes do tri e do tri fechado (soma dos meses com
    meta - nao a media dos %), os PONTOS no peso e o resultado ponderado.
    Sem insights: so o numero. O cadastro (meta, peso, despesa) abre pelo
    botao Metas executivas desta janela.
    """
    import meta_nucleo as mn                            # noqa: PLC0415
    dados = ctx.executivo
    painel = dados["painel"]
    linhas = painel.get("linhas") or []
    tris = mn.trimestres_do_executivo(painel)
    tri, recado = _tri_escolhido(ctx, tris)
    n = tri["numero"] if tri else 1
    meses_t = tri["meses"] if tri else []
    fech = (tri or {}).get("fechamento") or {"linhas": {}, "total": {}}
    r = novo("vc_executivo", ANA, "Farol Indicadores Executivos",
             f"{TRIMESTRES[n - 1]} trimestre {dados['ano']} · "
             + " · ".join(rotulo_mes(m) for m in meses_t),
             "Metas executivas (meta_config) + TABELA_BAP")
    r["parametros"] = [{"nome": "TRIMESTRE",
                        "valores": [(t["numero"], f"{TRIMESTRES[t['numero'] - 1]}"
                                     f" tri {dados['ano']}") for t in tris],
                        "valor": n}]
    if recado:
        r["avisos"].append(recado)
    elif tri and not fech["total"].get("meses_com_meta"):
        r["avisos"].append("Trimestre sem meta cadastrada: clique em Metas "
                           "executivas para cadastrar.")

    tom = _tom_exec
    # ---- cartoes: o tri fechado de cada indicador + o resultado
    r["kpis"] += _cartoes_exec(linhas, fech, meses_t)
    tot = fech.get("total") or {}

    # ---- a tabela do tri: mes a mes + o tri fechado
    cab = [col("INDICADOR", "texto", 215), col("PESO", "pct", 52)]
    grupos = [("", 2)]
    for m in meses_t:
        rm = rotulo_mes(m)
        cab += [dict(col(f"META {rm}", "valor", 92), curto="META"),
                dict(col(f"REAL {rm}", "valor", 92), curto="REAL"),
                dict(col(f"% {rm}", "pct", 64), curto="% ATING.")]
        grupos.append((rm, 3))
    cab += [dict(col("META TRI", "valor", 100), curto="META"),
            dict(col("REAL TRI", "valor", 100), curto="REAL"),
            dict(col("% TRI", "pct", 66), curto="% ATING."),
            dict(col("PONTOS TRI", "num1", 66), curto="PONTOS")]
    grupos.append((f"{TRIMESTRES[n - 1]} TRIMESTRE", 4))
    lin_t, tons = [], []
    for l in linhas:
        lin = [_rot_exec(l) + (" (inverso)" if l.get("invertido") else ""),
               l.get("peso")]
        for m in meses_t:
            c = l["meses"].get(m) or {}
            lin += [_fmt_exec(l, c.get("meta") or None),
                    _fmt_exec(l, c.get("real")), c.get("ating")]
        c = fech["linhas"].get(l["chave"]) or {}
        lin += [_fmt_exec(l, c.get("meta")), _fmt_exec(l, c.get("real")),
                c.get("ating"), c.get("ating_peso")]
        lin_t.append(lin)
        a = c.get("ating")
        tons.append("" if a is None else ("ok" if a >= 100 else
                                          ("atencao" if a >= mn.PISO_DO_PESO
                                           else "alerta")))
    tot_m = (painel.get("total") or {}).get("meses") or {}
    total = ["RESULTADO", 100.0]
    for m in meses_t:
        total += ["", "", (tot_m.get(m) or {}).get("ating_peso")]
    total += ["", "", tot.get("ating_peso"), tot.get("ating_peso")]
    t_tri = tabela(f"{TRIMESTRES[n - 1]} trimestre", cab, lin_t, tons,
                   total=total)
    t_tri["grupos"] = grupos

    # ---- fechamento dos quatro trimestres
    cab_f = [col("INDICADOR", "texto", 178), col("PESO", "pct", 46)] + \
        [col(f"{TRIMESTRES[t['numero'] - 1]} TRI", "pct", 50) for t in tris]
    lin_f = [[_rot_exec(l).capitalize(), l.get("peso")] +
             [((t["fechamento"]["linhas"].get(l["chave"]) or {}).get("ating"))
              for t in tris] for l in linhas]
    tot_f = ["RESULTADO", 100.0] + \
        [t["fechamento"]["total"].get("ating_peso") for t in tris]
    t_fech = tabela("Fechamento dos trimestres",
                    [dict(c_, pdf_larg=(190 if c_["tipo"] == "texto" else 64))
                     for c_ in cab_f], lin_f, total=tot_f)

    # ---- o painel: a tabela do tri em cima; embaixo o atingimento de
    # cada indicador, o resultado de cada tri e o fechamento dos quatro
    ating_ind = [((fech["linhas"].get(l["chave"]) or {}).get("ating") or 0)
                 for l in linhas]
    r["painel"] = {
        "colunas": (1, 1, 1), "altura_min": 2 * 250,
        "blocos": [
            {"tipo": "tabela", "row": 0, "col": 0, "colspan": 3,
             "titulo": f"{TRIMESTRES[n - 1]} trimestre · meta, real e "
                       f"atingimento", "colunas": cab, "linhas": lin_t,
             "tons": tons, "total": total, "grupos": grupos,
             "compacta": False},
            {"tipo": "hbarras", "row": 1, "col": 0,
             "titulo": f"Atingimento no {TRIMESTRES[n - 1]} tri",
             "rotulos": [_rot_exec(l).capitalize() for l in linhas],
             "valores": ating_ind, "formato": "pct", "referencia": 100,
             "cores": [{"ok": VERDE, "atencao": AMARELO, "alerta": VERMELHO,
                        "neutro": CINZA}[tom(v if v else None)]
                       for v in ating_ind]},
            {"tipo": "barras", "row": 1, "col": 1, "grafico": {
                "titulo": "Resultado ponderado por trimestre",
                "rotulos": [f"{TRIMESTRES[t['numero'] - 1]} TRI" for t in tris],
                "series": [{"nome": "resultado", "cor": VERDE, "valores": [
                    t["fechamento"]["total"].get("ating_peso") or 0
                    for t in tris], "cores": [
                    {"ok": VERDE, "atencao": AMARELO, "alerta": VERMELHO,
                     "neutro": CINZA}[tom(t["fechamento"]["total"].get(
                         "ating_peso"))] for t in tris]}],
                "subrotulos": ["" if t["fechamento"]["total"].get(
                    "meses_com_meta") else "sem meta" for t in tris],
                "formato": "pct", "meta": 100, "rotulo_meta": "meta 100%"}},
            {"tipo": "tabela", "row": 1, "col": 2,
             "titulo": "Fechamento dos trimestres", "colunas": cab_f,
             "linhas": lin_f, "total": tot_f, "compacta": True},
        ]}
    r["painel_titulo"] = "Painel executivo"
    r["tabelas_seguidas"] = True        # PDF: cartoes e tabelas juntos

    # ---- as abas (para filtrar e exportar)
    meses = painel.get("meses") or []
    cab_a = [col("INDICADOR", "texto", 210), col("PESO", "pct", 60)] + \
        [col(rotulo_mes(m), "pct", 70) for m in meses]
    lin_a = [[_rot_exec(l), l.get("peso")] + [(l["meses"].get(m) or {}).get("ating")
                                            for m in meses] for l in linhas]
    tot_a = ["RESULTADO PONDERADO", 100.0] + [
        (tot_m.get(m) or {}).get("ating_peso") for m in meses]
    cab_r = [col("INDICADOR", "texto", 210)] + \
        [col(rotulo_mes(m), "valor", 96) for m in meses]
    r["tabelas"] += [
        t_tri, t_fech,
        tabela("Atingimento mês a mês", cab_a, lin_a, total=tot_a),
        tabela("Realizado mês a mês", cab_r, [
            [_rot_exec(l)] + [_fmt_exec(l, (l["meses"].get(m) or {}).get("real"))
                             for m in meses] for l in linhas]),
        tabela("Meta mês a mês", cab_r, [
            [_rot_exec(l)] + [_fmt_exec(l, (l["meses"].get(m) or {}).get("meta")
                                       or None) for m in meses]
            for l in linhas])]
    r["tabelas"].append(_analitico_executivo(ctx, dados, linhas, meses_t))
    return r


def _tom_exec(v):
    import meta_nucleo as mn                            # noqa: PLC0415
    if v is None:
        return "neutro"
    return "ok" if v >= 100 else ("atencao" if v >= mn.PISO_DO_PESO
                                  else "alerta")


def _cartoes_exec(linhas, fech, meses_t):
    """Os cartoes do tri fechado: um por indicador + o resultado."""
    ks = []
    for l in linhas:
        c = fech["linhas"].get(l["chave"]) or {}
        ks.append(kpi(
            _rot_exec(l).capitalize()[:24], p(c.get("ating")),
            _tom_exec(c.get("ating")),
            f"{_fmt_exec(l, c.get('real'))} de {_fmt_exec(l, c.get('meta'))}"
            if c.get("meta") else "sem meta"))
    tot = fech.get("total") or {}
    ks.append(kpi(
        "Resultado do tri", p(tot.get("ating_peso")),
        _tom_exec(tot.get("ating_peso")),
        f"de 100 pontos · {tot.get('meses_com_meta') or 0} de "
        f"{len(meses_t)} meses com meta"))
    return ks


def _conta_exec(l, m):
    """O mes entra no real do tri? (o mesmo criterio do fechamento)"""
    c = l["meses"].get(m) or {}
    if not c.get("meta"):
        return False, "mês sem meta: fora do tri"
    if not c.get("apurado", True):
        return False, "mês não apurado: fora do tri"
    return True, ""


# (08/10) ANALITICO do Farol Indicadores Executivos: a linha de cada coisa
# que entrou no REAL do trimestre, para a auditoria. Sai da MESMA passada
# pela TABELA_BAP que apura o real (bap_dados/meta_nucleo), entao bate
# com o farol por construcao - e os cartoes da aba conferem isso.
IND_DE_CONTAGEM = ("positivacao", "cadastro_compra")


def _analitico_executivo(ctx, dados, linhas, meses_t):
    det = dados.get("analitico") or []
    rot_ind = {l["chave"]: _rot_exec(l).capitalize() for l in linhas}
    ordem = {l["chave"]: i for i, l in enumerate(linhas)}

    conta = _conta_exec

    def cat(c):
        return "PEÇAS" if c == "pecas" else str(c or "").upper()

    lin = []
    for l in linhas:
        ch = l["chave"]
        for m in meses_t:
            entra, obs_m = conta(l, m)
            rm = rotulo_mes(m)
            if not l.get("automatico", True):
                c = l["meses"].get(m) or {}
                lin.append([rot_ind[ch], rm, "SIM" if entra else "NÃO", None,
                            "", "", "", "", "", "", "", "", "", "",
                            c.get("real"), None,
                            obs_m or f"digitado em Metas executivas · meta "
                                     f"{_fmt_exec(l, c.get('meta') or None)}"])
                continue
            for d in det:
                if d["mes"] != m:
                    continue
                if ch == "faturamento" and d["ind"] == "faturamento" or \
                        ch == "pecas" and d["ind"] == "faturamento" \
                        and d.get("pecas"):
                    obs = obs_m or ("devolução (abate)" if d.get("tipo") ==
                                    "DEV" else "")
                    lin.append([rot_ind[ch], rm, "SIM" if entra else "NÃO",
                                d["data"], d["filial"], d["doc"], d["pedido"],
                                d["tipo"], d["cli"], d["nome"],
                                ctx.vendedor(d["vend"]) if d["vend"] else "",
                                d["prod"], ctx.produto(d["prod"]),
                                cat(d["cat"]), d["valor"], None, obs])
                elif ch == d["ind"] == "positivacao":
                    lin.append([rot_ind[ch], rm, "SIM" if entra else "NÃO",
                                d["data"], d["filial"], "", "", "", d["cli"],
                                d["nome"],
                                ctx.vendedor(d["vend"]) if d["vend"] else "",
                                "", "", "", d["valor"], 1 if entra else 0,
                                obs_m or f"{d['docs']} NF(s) no mês · data = "
                                         f"1ª NF"])
                elif ch == d["ind"] == "cadastro_compra":
                    ok = entra and d["comprou"]
                    lin.append([rot_ind[ch], rm, "SIM" if ok else "NÃO",
                                d["data"], d["filial"], "", "", "", d["cli"],
                                d["nome"],
                                ctx.vendedor(d["vend"]) if d["vend"] else "",
                                "", "", "", d["valor"], 1 if ok else 0,
                                obs_m or ("cadastrado e comprou no mês"
                                          if d["comprou"] else
                                          "cadastrado sem compra no mês")])
    por_rot = {rot_ind[l["chave"]]: l for l in linhas}
    mes_de_rot = {rotulo_mes(m): m for m in meses_t}
    lin.sort(key=lambda x: (ordem.get(por_rot[x[0]]["chave"], 99),
                            mes_de_rot.get(x[1], ""), x[3] or date.min, x[8]))

    def cartoes(ls):
        inds = {x[0] for x in ls}
        if len(inds) != 1:
            return [kpi("Linhas", br(len(ls)), "neutro"),
                    kpi("Indicadores", br(len(inds)), "neutro",
                        "filtre um indicador para conferir")]
        l = por_rot[next(iter(inds))]
        ch = l["chave"]
        sim = [x for x in ls if x[2] == "SIM"]
        if ch in IND_DE_CONTAGEM:
            v_an = sum(x[15] or 0 for x in sim)
        else:
            v_an = sum(x[14] or 0 for x in sim)
        meses_v = {mes_de_rot[x[1]] for x in ls if x[1] in mes_de_rot}
        v_fa = sum(((l["meses"].get(m) or {}).get("real") or 0)
                   for m in meses_v if conta(l, m)[0])
        dif = v_an - v_fa
        bate = abs(dif) < 0.5
        return [kpi("Linhas", br(len(ls)), "neutro",
                    f"{br(len(sim))} entram no real"),
                kpi("Real no analítico", _fmt_exec(l, v_an), "neutro",
                    "soma das linhas que entram"),
                kpi("Real no farol", _fmt_exec(l, v_fa), "neutro",
                    " · ".join(rotulo_mes(m) for m in sorted(meses_v))),
                kpi("Conferência", "confere" if bate else
                    _fmt_exec(l, dif), "ok" if bate else "alerta",
                    "analítico = farol" if bate else
                    "diferença (filtro de vendedor/cliente abre isso)")]
    cab = [col("INDICADOR", "texto", 150), col("MÊS", "texto", 60),
           col("ENTRA NO REAL", "texto", 90), col("DATA", "data"),
           col("FILIAL", "texto", 60), col("NF", "texto", 80),
           col("PEDIDO", "texto", 75), col("TIPO", "texto", 45),
           col("CLIENTE", "texto", 70), col("RAZÃO SOCIAL", "texto", 220),
           col("VENDEDOR", "texto", 190), col("PRODUTO", "texto", 100),
           col("DESCRIÇÃO", "texto", 220), col("CATEGORIA", "texto", 80),
           col("VALOR", "moeda"), col("QTD", "int", 50),
           col("OBSERVAÇÃO", "texto", 240)]
    tons = ["" if x[2] == "SIM" else "cinza" for x in lin]
    return tabela(
        "Analítico", cab, lin, tons,
        filtros=({"coluna": "INDICADOR",
                  "padrao": rot_ind[linhas[0]["chave"]] if linhas else ""},
                 "MÊS", "ENTRA NO REAL", "VENDEDOR", "FILIAL"),
        kpis_de=cartoes)


# (08/10) EXPORTAR PARA O RH (Farol Indicadores Executivos): o trimestre
# escolhido num arquivo so - na 1a pagina o RESUMO EXECUTIVO (cartoes e a
# tabela do tri com os pontos) e depois o ANALITICO de cada indicador, uma
# pagina (ou aba do Excel) por indicador. So o que ENTRA no real do tri:
# a soma de cada analitico e o real do resumo (a nota de cada um confere).
# Faturamento e pecas vao por NF (o item a item fica na aba Analitico).
def exportar_rh_executivo(ctx):
    import meta_nucleo as mn                            # noqa: PLC0415
    dados = ctx.executivo
    painel = dados["painel"]
    linhas = painel.get("linhas") or []
    tris = mn.trimestres_do_executivo(painel)
    tri, _rec = _tri_escolhido(ctx, tris)
    if not tri:
        raise ValueError("Não há trimestre com metas executivas.")
    n, meses_t, fech = tri["numero"], tri["meses"], tri["fechamento"]
    ano = dados["ano"]
    nome_tri = f"{TRIMESTRES[n - 1]} trimestre {ano}"
    r = novo("vc_executivo_rh", ANA, "Indicadores Executivos",
             f"{nome_tri} · " + " · ".join(rotulo_mes(m) for m in meses_t)
             + f" · posição de {ctx.hoje:%d/%m/%Y}",
             "Metas executivas (meta_config) + TABELA_BAP")
    r.update({"estilo": "bap", "eyebrow": bv_cabecalho(),
              "faixa": f"INDICADORES EXECUTIVOS · {TRIMESTRES[n - 1]} TRI "
                       f"{ano} · RH",
              "titulo_curto": "Indicadores Executivos"})
    r["tri"] = n
    r["assinaturas"] = ["Analista Comercial", "Gerente Comercial", "RH"]
    r["fecho_na_1a"] = True      # o RH assina o resumo, na 1a pagina
    r["kpis"] = _cartoes_exec(linhas, fech, meses_t)
    if not (fech.get("total") or {}).get("meses_com_meta"):
        r["avisos"].append(f"O {nome_tri} não tem meta cadastrada.")

    # ---- 1a pagina: o RESUMO EXECUTIVO
    cab = [col("INDICADOR", "texto", 200), col("PESO", "pct", 60)]
    grupos = [("", 2)]
    for m in meses_t:
        cab.append(dict(col(f"% {rotulo_mes(m)}", "pct", 70),
                        curto=rotulo_mes(m), ating=True))
    grupos.append(("ATINGIMENTO MÊS A MÊS", len(meses_t)))
    cab += [dict(col("META TRI", "valor", 110), curto="META"),
            dict(col("REAL TRI", "valor", 110), curto="REAL"),
            dict(col("% TRI", "pct", 70), curto="% ATING.", ating=True),
            dict(col("PONTOS", "num1", 70), curto="PONTOS")]
    grupos.append((f"{TRIMESTRES[n - 1]} TRIMESTRE", 4))
    lin_r = []
    for l in linhas:
        c = fech["linhas"].get(l["chave"]) or {}
        lin_r.append([_rot_exec(l).capitalize()
                      + (" (inverso)" if l.get("invertido") else ""),
                      l.get("peso")]
                     + [(l["meses"].get(m) or {}).get("ating")
                        for m in meses_t]
                     + [_fmt_exec(l, c.get("meta")), _fmt_exec(l, c.get("real")),
                        c.get("ating"), c.get("ating_peso")])
    tot_m = (painel.get("total") or {}).get("meses") or {}
    tot = fech.get("total") or {}
    t_res = tabela("Resumo executivo", cab, lin_r, total=(
        ["RESULTADO DO TRI", 100.0]
        + [(tot_m.get(m) or {}).get("ating_peso") for m in meses_t]
        + ["", "", tot.get("ating_peso"), tot.get("ating_peso")]))
    t_res["grupos"] = grupos
    t_res["nota_tom"] = "suave"
    t_res["nota_pdf"] = (
        f"Pontos: abaixo de {br(mn.PISO_DO_PESO)}% de atingimento, zero; em "
        f"{br(mn.PISO_DO_PESO)}%, {br(mn.PESO_NO_PISO)}% do peso; cada ponto "
        f"acima soma {br(mn.PONTOS_POR_PONTO, 1)}%; teto de "
        f"{br(mn.TETO_DO_PESO)}% do peso. O tri é a soma dos meses com meta "
        "(não a média dos %). Inverso: gastar menos que a meta é melhor.")
    r["tabelas"].append(t_res)

    # ---- um ANALITICO por indicador (pagina nova cada)
    det = ctx.executivo.get("analitico") or []
    for l in linhas:
        ch = l["chave"]
        ok_m = [m for m in meses_t if _conta_exec(l, m)[0]]
        fora = [rotulo_mes(m) for m in meses_t if m not in ok_m]
        c_tri = fech["linhas"].get(ch) or {}
        rot = _rot_exec(l).capitalize()
        t = _analitico_rh(ctx, l, ch, ok_m, det)
        if t is None:
            continue
        real_an = t.pop("_real")
        bate = c_tri.get("real") is not None and \
            abs((real_an or 0) - (c_tri.get("real") or 0)) < 0.5
        t["titulo"] = rot
        t["pdf_quebra_antes"] = True
        t["nota_tom"] = "suave" if bate else ""
        t["nota_pdf"] = (
            f"{t.pop('_como')} Soma do analítico: {_fmt_exec(l, real_an)} · "
            f"real do resumo: {_fmt_exec(l, c_tri.get('real'))} · "
            + ("confere." if bate else "NÃO CONFERE - revisar.")
            + (f" Fora do tri (sem meta ou não apurado): {', '.join(fora)}."
               if fora else ""))
        r["tabelas"].append(t)
    return r


def _analitico_rh(ctx, l, ch, meses, det):
    """A tabela do analitico de UM indicador, so com o que entra no tri."""
    rm = {m: rotulo_mes(m) for m in meses}

    def vend(c):
        return ctx.vendedor(c) if c else ""
    if not l.get("automatico", True):
        lin = []
        for m in meses:
            c = l["meses"].get(m) or {}
            lin.append([rm[m], _fmt_exec(l, c.get("meta") or None),
                        _fmt_exec(l, c.get("real")), c.get("ating")])
        real = sum((l["meses"].get(m) or {}).get("real") or 0 for m in meses)
        meta = sum((l["meses"].get(m) or {}).get("meta") or 0 for m in meses)
        import meta_nucleo as mn                        # noqa: PLC0415
        t = tabela("", [col("MÊS", "texto", 90), col("META", "valor", 120),
                        col("REAL", "valor", 120),
                        dict(col("% ATING.", "pct", 80), ating=True)], lin,
                   total=["TOTAL DO TRI", _fmt_exec(l, meta or None),
                          _fmt_exec(l, real),
                          mn.atingimento(real, meta, l.get("invertido"))
                          if meta else None])
        t.update(_real=real, _como="Valor digitado mês a mês em Metas "
                                    "executivas.")
        return t
    if ch in ("faturamento", "pecas"):
        nfs = {}
        for d in det:
            if d["ind"] != "faturamento" or d["mes"] not in rm or (
                    ch == "pecas" and not d.get("pecas")):
                continue
            k = (d["mes"], d["filial"], d["doc"], d["tipo"], d["cli"])
            x = nfs.setdefault(k, {"d": d, "data": d["data"], "itens": 0,
                                   "valor": 0.0})
            x["data"] = min(x["data"], d["data"])
            x["itens"] += 1
            x["valor"] += d["valor"]
        lin, cores = [], []
        for (m, fil, doc, tp, cli), x in sorted(
                nfs.items(), key=lambda kv: (kv[0][0], kv[1]["data"],
                                             kv[0][2])):
            d = x["d"]
            lin.append([rm[m], x["data"], fil, doc, d["pedido"], tp, cli,
                        d["nome"], vend(d["vend"]), x["itens"], x["valor"]])
            cores.append({10: VERMELHO} if x["valor"] < 0 else {})
        real = sum(x["valor"] for x in nfs.values())
        t = tabela("", [col("MÊS", "texto", 55), col("DATA", "data", 70),
                        col("FILIAL", "texto", 70), col("NF", "texto", 80),
                        col("PEDIDO", "texto", 70), col("TIPO", "texto", 40),
                        col("CLIENTE", "texto", 60),
                        col("RAZÃO SOCIAL", "texto", 240),
                        col("VENDEDOR", "texto", 200),
                        col("ITENS", "int", 50), col("VALOR", "moeda", 100)],
                   lin, ["devolucao" if x[-1] < 0 else "" for x in lin],
                   total=["TOTAL", None, "", f"{br(len(lin))} NFs", "", "",
                          "", "", "", sum(x[9] for x in lin), real])
        t["cores_celulas"] = cores
        t.update(_real=real, _como=(
            "Uma linha por NF (VND) ou devolução (DEV, abate) do mês, pela "
            "data da NF" + (", só os itens de peças (linha leve, pesada e "
                            "moto)." if ch == "pecas" else ".")))
        return t
    if ch == "positivacao":
        ls = sorted((d for d in det if d["ind"] == "positivacao"
                     and d["mes"] in rm),
                    key=lambda d: (d["mes"], d["nome"]))
        lin = [[rm[d["mes"]], d["cli"], d["nome"], vend(d["vend"]),
                d["filial"], d["data"], d["docs"], d["valor"]] for d in ls]
        t = tabela("", [col("MÊS", "texto", 55), col("CLIENTE", "texto", 60),
                        col("RAZÃO SOCIAL", "texto", 260),
                        col("VENDEDOR", "texto", 220),
                        col("FILIAL", "texto", 70), col("1ª NF", "data", 70),
                        col("NFS", "int", 45),
                        col("COMPRAS NO MÊS", "moeda", 110)], lin,
                   total=["TOTAL", "", f"{br(len(lin))} positivações", "",
                          "", None, sum(x[6] for x in lin),
                          sum(x[7] for x in lin)])
        t.update(_real=len(lin), _como="Um cliente por mês com compra (NF "
                                       "de valor positivo) no mês.")
        return t
    if ch == "cadastro_compra":
        ls = sorted((d for d in det if d["ind"] == "cadastro_compra"
                     and d["mes"] in rm and d["comprou"]),
                    key=lambda d: (d["mes"], d["data"], d["cli"]))
        lin = [[rm[d["mes"]], d["data"], d["cli"], d["nome"], vend(d["vend"]),
                d["filial"], d["valor"]] for d in ls]
        t = tabela("", [col("MÊS", "texto", 55), col("CADASTRO", "data", 70),
                        col("CLIENTE", "texto", 60),
                        col("RAZÃO SOCIAL", "texto", 280),
                        col("VENDEDOR", "texto", 230),
                        col("FILIAL", "texto", 70),
                        col("COMPRAS NO MÊS", "moeda", 110)], lin,
                   total=["TOTAL", None, "", f"{br(len(lin))} cadastros com "
                          "compra", "", "", sum(x[6] for x in lin)])
        t.update(_real=len(lin), _como="Cliente cadastrado no mês (A1_DTCAD) "
                                       "que comprou no mesmo mês.")
        return t
    return None


def _fmt_exec(linha, v):
    if v is None:
        return "—"
    rot = (linha.get("rotulo") or "").upper()
    if "FATURAMENTO" in rot or "DESPESA" in rot or "R$" in rot:
        return moeda(v)
    v = float(v)
    return br(v, 0 if v == int(v) or v >= 100 else 1)


ACENTOS_EXEC = (("POSITIVACAO", "POSITIVAÇÃO"), ("PECAS", "PEÇAS"))


def _rot_exec(linha) -> str:
    """O nome do indicador na tela: com acento e so a 1a maiuscula."""
    t = (linha.get("rotulo") or "").upper()
    for de, para in ACENTOS_EXEC:
        t = t.replace(de, para)
    return t


def resumo_planner(ctx):
    res = ctx.base["resumo"]
    r = novo("vc_planner", VEN, "Farol Roteirização",
             f"Rota de {res.get('mes', '')} · {res.get('du', '')} dias úteis",
             "Planner (BAP Analista) + BASE_CLIENTE")
    capa(r, ctx, anos_dos_dados(ctx))
    graficos_tempo(r, ctx, "Clientes positivados", _ev_positivados(ctx),
                   "num", VERDE, "unicos")
    if res.get("erro"):
        r["avisos"].append(f"Não consegui montar o resumo: {res['erro']}")
        return r
    t = res.get("total") or {}
    # (07/10) VISITAS/MÊS DIAS ÚTEIS: as visitas da rota sem o 1o sabado
    # do mes (o deposito do excedente)
    # (21/10, Alexandre) SO ROTA E VISITA: sem valor em R$ (limite, atraso,
    # receita 6M, faturamento mensal); o qualitativo em QUANTIDADE de
    # clientes; CLIENTES -> BASE PLANNER (a carteira do vendedor no
    # Planner, inclusive o excedente). As MESMAS colunas, na mesma ordem,
    # em todas as abas agregadas (a identificacao termina na BASE PROTHEUS)
    cols = [col("BASE PLANNER", "int", 100), col("BASE VISITA", "int", 85),
            col("VISITAS/MÊS", "int", 85),
            col("VISITAS/MÊS DIAS ÚTEIS", "int", 140),
            col("CLIENTES/DIA", "num2", 85),
            col("CAPACIDADE/DIA", "int", 95), col("COM LIMITE", "int", 85),
            col("INADIMPL.", "int", 75),
            col("COMPRADORES", "int", 90), col("% COMPRADORES", "pct", 95)]
    n_nums = len(cols)

    def nums(d):
        return [d.get("clientes"), d.get("base_visita"), d.get("visitas_mes"),
                d.get("visitas_uteis"),
                d.get("clientes_dia"), d.get("capacidade_dia"),
                d.get("com_limite"), d.get("inadimplentes"),
                d.get("compradores"), d.get("pct_compradores")]

    def cartoes_de(n_cab, extra=None):
        def f(ls):
            soma = [sum((l[n_cab + j] or 0) for l in ls)
                    for j in range(n_nums)]
            cli, vis, lim, ina, comp = soma[0], soma[2], soma[6], soma[7], \
                soma[8]
            saida = [
                kpi("Base Planner", br(cli), "neutro",
                    f"{br(soma[1])} na base de visita"),
                kpi("Visitas no mês", br(vis), "info",
                    f"{br(soma[3])} em dias úteis (sem o 1º sábado)"),
                kpi("Compradores", br(comp), "ok", p(pct_de(comp, cli))),
                kpi("Com limite", br(lim), "info", p(pct_de(lim, cli))),
                kpi("Inadimplentes", br(ina), "alerta" if ina else "ok",
                    p(pct_de(ina, cli)))]
            return (extra(ls) if extra else []) + saida
        return f
    r["kpis"] = [
        kpi("Base Planner", br(t.get("clientes")), "neutro",
            f"{br(ctx.base.get('excluidos'))} excluídos"),
        kpi("Zonas", br(t.get("qtd_zonas")), "neutro",
            f"{br(t.get('zonas_sem_vde'))} sem vendedor"),
        kpi("Vendedores", br(t.get("qtd_vendedores")), "neutro",
            f"{br(t.get('qtd_supervisores'))} supervisores"),
        kpi("Visitas no mês", br(t.get("visitas_mes")), "info",
            f"{br(t.get('clientes_dia'), 1)} clientes/dia"),
        kpi("Compradores no mês", p(t.get("pct_compradores")), "ok",
            f"{br(t.get('compradores'))} clientes"),
        kpi("Com limite", br(t.get("com_limite")), "info",
            f"{br(t.get('inadimplentes'))} inadimplente(s)"),
    ]

    def junta(xs):
        return "; ".join(xs or [])
    # (21/10) BASE PROTHEUS em TODAS as abas agregadas (a ultima coluna da
    # identificacao). UF e cidade: as lojas do Protheus naquele A1_EST /
    # A1_MUN. Zona e segmento nao existem no Protheus: fica vazio.
    bp_uf, bp_cid = _base_protheus_por_lugar(ctx)
    BP = col("BASE PROTHEUS", "int", 105)
    vistas = [
        ("zona", "Por zona",
         [col("ZONA", "texto", 80), col("NOME", "texto", 220),
          col("VENDEDOR", "texto", 220), col("SUPERVISOR", "texto", 220),
          col("UF", "texto", 40), BP],
         lambda d: [d.get("codigo"), d.get("zona_nome"),
                    f"{d.get('vendedor', '')} - {d.get('vendedor_nome', '')}"
                    .strip(" -") or "(SEM VENDEDOR)",
                    d.get("supervisor") or "(SEM SUPERVISOR)", d.get("uf"),
                    None],
         ("VENDEDOR", "SUPERVISOR", "UF"),
         lambda ls: [kpi("Zonas", br(len(ls)), "neutro",
                         f"{sum(1 for l in ls if l[2] == '(SEM VENDEDOR)')} "
                         f"sem vendedor")]),
        # (07/10) BASE PROTHEUS: as lojas com o A1_VEND do vendedor (ou dos
        # vendedores do supervisor) no Protheus, ao lado da carteira
        ("vendedor", "Por vendedor",
         [col("VENDEDOR", "texto", 240), col("SUPERVISOR", "texto", 220),
          col("BASE PROTHEUS", "int", 105)],
         lambda d: [f"{d.get('vendedor', '')} - {d.get('vendedor_nome', '')}",
                    d.get("supervisor") or "(SEM SUPERVISOR)",
                    base_protheus_contar(ctx, vend=d.get("vendedor"))
                    if texto(d.get("vendedor")).strip("0") and
                    d.get("vendedor") != "(sem vendedor)" else
                    base_protheus_contar(ctx, sem_vendedor=True)],
         ("SUPERVISOR",), None),
        ("supervisor", "Por supervisor",
         [col("SUPERVISOR", "texto", 260), col("BASE PROTHEUS", "int", 105)],
         lambda d: [d.get("supervisor"),
                    base_protheus_contar(ctx, supervisor=d.get("supervisor"))
                    if d.get("supervisor") and not texto(d.get(
                        "supervisor")).lower().startswith("(sem")
                    else None], (), None),
        ("segmento", "Por segmento", [col("SEGMENTO", "texto", 220),
                                      col("VENDEDOR", "texto", 240), BP],
         lambda d: [d.get("segmento"), TODOS_VENDEDORES, None],
         ({"coluna": "VENDEDOR", "padrao": TODOS_VENDEDORES},), None),
        ("uf", "Por UF", [col("UF", "texto", 60),
                          col("VENDEDORES", "texto", 300),
                          col("SUPERVISORES", "texto", 260), BP],
         lambda d: [d.get("uf"), junta(d.get("vendedores_lista")),
                    junta(d.get("supervisores_lista")),
                    bp_uf.get(_lugar(d.get("uf")), 0)],
         ({"coluna": "VENDEDORES", "multi": True},
          {"coluna": "SUPERVISORES", "multi": True}), None),
        ("cidade", "Por cidade",
         [col("CIDADE", "texto", 200), col("UF", "texto", 40),
          col("VENDEDORES", "texto", 300), col("SUPERVISORES", "texto", 260),
          BP],
         lambda d: [d.get("cidade_nome"), d.get("uf"),
                    junta(d.get("vendedores_lista")),
                    junta(d.get("supervisores_lista")),
                    bp_cid.get((_lugar(d.get("cidade_nome")),
                                _lugar(d.get("uf"))), 0)],
         ("UF", {"coluna": "VENDEDORES", "multi": True},
          {"coluna": "SUPERVISORES", "multi": True}),
         lambda ls: [kpi("Cidades", br(len(ls)), "neutro")]),
    ]
    def rotulo_vend(d):
        cod = d.get("vendedor") or ""
        return (f"{cod} - {d.get('vendedor_nome', '')}".strip(" -")
                if cod and cod != "(sem vendedor)" else "(SEM VENDEDOR)")
    for chave, titulo, cab, rot, filtros, extra in vistas:
        ls = res.get(chave) or []
        linhas = [rot(d) + nums(d) for d in ls]
        tons = ["alerta" if chave == "zona" and not d.get("vendedor") else ""
                for d in ls]
        total = ["TOTAL"] + [""] * (len(cab) - 1) + nums(t)
        if cab[-1]["nome"] == "BASE PROTHEUS":
            i_bp = len(cab) - 1
            if chave == "vendedor":     # (sem vendedor) = o resto do cadastro
                for l in linhas:
                    if texto(l[0]).lower().startswith("(sem vendedor)"):
                        l[i_bp] = base_protheus_contar(ctx) - sum(
                            x[i_bp] or 0 for x in linhas if x is not l)
            # zona e segmento: sem Protheus, o TOTAL tambem fica vazio
            total[i_bp] = (sum(l[i_bp] or 0 for l in linhas)
                           if any(l[i_bp] is not None for l in linhas)
                           else None)
        kp = cartoes_de(len(cab), extra)
        tb = tabela(titulo, cab + cols, linhas, tons, filtros=filtros,
                    total=total, kpis_de=kp)
        if chave == "segmento":
            # POR SEGMENTO com filtro VENDEDOR: as linhas de TODOS OS
            # VENDEDORES (o padrao) e o segmento de cada vendedor. O TOTAL
            # de um vendedor e a linha dele no Por vendedor.
            sv = sorted(res.get("segmento_vendedor") or [],
                        key=lambda d: (rotulo_vend(d), -(d.get("clientes")
                                                         or 0)))
            tb["linhas"] += [[d.get("segmento"), rotulo_vend(d), None]
                             + nums(d) for d in sv]
            tb["tons"] += [""] * len(sv)
            tb["totais_por"] = {"coluna": 1, "valores": dict(
                [(TODOS_VENDEDORES, total)] + [
                    (rotulo_vend(d), ["TOTAL", rotulo_vend(d), None]
                     + nums(d))
                    for d in res.get("vendedor") or []])}
            # "(todos)" no filtro mostra as duas coisas: os cartoes contam
            # so as linhas de TODOS OS VENDEDORES, sem somar duas vezes
            tb["kpis_de"] = lambda ls, kp=kp: kp(
                [l for l in ls if l[1] == TODOS_VENDEDORES]
                if any(l[1] == TODOS_VENDEDORES for l in ls) else ls)
        r["tabelas"].append(tb)
    _rota_por_cliente(r, ctx)
    _rota_calendario(r, ctx)
    # (06/10) o RESUMO GERENCIAL virou painel com os indicadores da rota
    try:
        _painel_roteirizacao(r, ctx)
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Resumo gerencial: {erro}")
    r["exportar_protheus"] = _exportar_protheus_da_rota(ctx)
    r["exportar_base_protheus"] = _exportar_base_protheus(ctx)
    return r


def _nome_curto_rota(vend) -> str:
    """ "000041 - EDSON NEVES DO NASCIMENTO" -> "Edson Nascimento"."""
    nome = str(vend).split(" - ", 1)[-1].split()
    if not nome:
        return str(vend)
    return " ".join(x.title() for x in ([nome[0], nome[-1]] if len(nome) > 1
                                       else nome))


def _painel_roteirizacao(r, ctx):
    """
    O RESUMO GERENCIAL do Farol Roteirizacao (desenho do Claude Design):
    os cartoes de cima com os indicadores da rota e um painel com
      * O QUE A ROTA DIZ: os insights calculados (o que precisa de acao);
      * visitas por dia util x teto e a ocupacao da agenda, por vendedor;
      * as visitas planejadas dia a dia (sabado em cinza);
      * o sabado do excedente, a situacao dos clientes visitados e a
        positivacao da rota no mes, por vendedor;
      * os clientes positivados mes a mes.
    """
    import calendar as _cal                             # noqa: PLC0415
    base = ctx.base
    vis = base.get("visitas") or []
    clientes = base.get("clientes") or []
    if not vis or not clientes:
        return
    mes_rota = base.get("mes") or ""
    ano, mes = (int(x) for x in mes_rota.split("-")[:2])
    fer = set()
    for f_ in base.get("feriados") or []:
        try:
            fer.add(date.fromisoformat(str(f_)[:10]))
        except ValueError:
            pass
    teto_pad = int(base.get("teto_padrao") or 12)
    teto_sex = int(base.get("teto_sexta") or 0)
    tetos = base.get("tetos") or {}
    ndias = _cal.monthrange(ano, mes)[1]
    dias_mes = [date(ano, mes, d) for d in range(1, ndias + 1)]
    uteis = [d for d in dias_mes if d.weekday() < 5 and d not in fer]

    def teto_do(vend, d):
        t = int(tetos.get(vend) or teto_pad)
        return min(t, teto_sex) if (teto_sex and d.weekday() == 4) else t
    por_vend = defaultdict(list)
    for v in vis:
        if v.get("data"):
            por_vend[v["vendedor"]].append(v)
    sit = {(c["cod"], _loja2(c.get("loja"))): c.get("status") or ""
           for c in clientes}
    # compradores do MES DA ROTA (notas de venda)
    comp = {bd.cod6(it["cliente"]) for it in ctx.tabela.get("itens") or []
            if it.get("tipo") == "VND" and it.get("dt_nf")
            and (it["dt_nf"].year, it["dt_nf"].month) == (ano, mes)}
    na_rota = {(v["cod"], _loja2(v.get("loja"))) for v in vis}
    cods_rota = {v["cod"] for v in vis}
    total_cli = len(clientes)
    sem_vend = [c for c in clientes if not c.get("vend")]
    zonas_sem = {c.get("zona") for c in sem_vend if c.get("zona")}
    inativos = sum(1 for c in clientes if c.get("inativo"))
    # ---- por vendedor
    linhas_v = []
    for vend, vs in sorted(por_vend.items()):
        uteis_v = [v for v in vs if v["data"].weekday() < 5]
        dias_com = {v["data"] for v in uteis_v}
        # (27/10, Alexandre) a CAPACIDADE so conta os dias uteis em que o
        # vendedor TEM ROTA (quem entrou dia 16 nao conta do dia 15 para
        # tras); antes era o teto x todos os dias uteis do mes
        cap = sum(teto_do(vend, d) for d in dias_com)
        sab = [v for v in vs if v["data"].weekday() == 5]
        cli_v = {v["cod"] for v in vs}
        linhas_v.append({
            "vend": vend, "curto": _nome_curto_rota(vend),
            "visitas": len(vs), "uteis": len(uteis_v),
            "dia": len(uteis_v) / len(dias_com) if dias_com else 0.0,
            "ocup": 100.0 * len(uteis_v) / cap if cap else 0.0,
            "sab": len(sab), "clientes": len(cli_v),
            "comp": len(cli_v & comp),
            "teto": int(tetos.get(vend) or teto_pad), "cap": cap})
    vis_uteis = sum(x["uteis"] for x in linhas_v)
    cap_total = sum(x["cap"] for x in linhas_v)
    vis_sab = sum(x["sab"] for x in linhas_v)
    cli_rota = len(na_rota)
    comp_rota = sum(1 for k in na_rota if k[0] in comp)
    sit_vis = Counter(sit.get((v["cod"], _loja2(v.get("loja"))), "") or
                      "(SEM SITUAÇÃO)" for v in vis)
    nunca = sit_vis.get("NUNCA COMPROU", 0)
    # o SABADO DO EXCEDENTE: o sabado com mais visitas que o teto da equipe
    sab_dia = Counter(v["data"] for v in vis if v["data"].weekday() == 5)
    cap_sab = sum(x["teto"] for x in linhas_v)
    excedente = {d: n for d, n in sab_dia.items() if n > cap_sab}
    atraso = {}
    for v in vis:
        if (v.get("atraso") or 0) > 0:
            atraso[(v["cod"], v.get("loja"))] = v["atraso"]

    # ---- os cartoes de cima
    pct = (lambda a, b_: 100.0 * a / b_ if b_ else 0.0)
    r["kpis"] = [
        kpi("Cobertura da carteira", p(pct(cli_rota, total_cli)),
            "ok" if pct(cli_rota, total_cli) >= 90 else "atencao",
            f"{br(cli_rota)} de {br(total_cli)} clientes na rota"),
        kpi("Visitas no mês", br(len(vis)), "info",
            f"{br(vis_uteis)} em dia útil · {br(vis_sab)} no sábado"),
        kpi("Ocupação da agenda", p(pct(vis_uteis, cap_total)),
            "ok" if pct(vis_uteis, cap_total) >= 80 else "atencao",
            f"dias úteis com rota · teto {teto_pad}/dia"
            + (f", sexta {teto_sex}" if teto_sex else "")),
        kpi("Positivação da rota", f"{br(pct(comp_rota, cli_rota), 1)}%",
            "info", f"{br(comp_rota)} cliente(s) da rota compraram em "
                    f"{MESES[mes]}/{str(ano)[2:]}"),
        kpi("Sem vendedor", br(len(sem_vend)),
            "alerta" if sem_vend else "ok",
            f"{br(len(zonas_sem))} zona(s) sem vendedor · fora da rota"),
        kpi("Nunca comprou", p(pct(nunca, len(vis))), "neutro",
            "das visitas (prospecção)")]

    # ---- O QUE A ROTA DIZ (os insights, do mais grave ao informativo)
    ins = []
    if sem_vend:
        ins.append(("alerta", f"{br(len(sem_vend))} clientes "
                              f"({p(pct(len(sem_vend), total_cli))}) estão em "
                              f"{br(len(zonas_sem))} zona(s) sem vendedor e "
                              f"ficam fora da rota."))
    for d, n in sorted(excedente.items()):
        top = sorted(((x["sab"], x["curto"]) for x in linhas_v if x["sab"]),
                     reverse=True)[:3]
        ins.append(("alerta", f"Sábado {d:%d/%m}: {br(n)} visitas de "
                              f"excedente (" + ", ".join(
                                  f"{nm} {br(q)}" for q, nm in top)
                    + "). A carteira não cabe no teto do mês."))
    ociosos = [x for x in linhas_v if x["dia"] < 0.5 * x["teto"]]
    if ociosos:
        ins.append(("atencao", "Agenda ociosa (menos da metade do teto): "
                    + ", ".join(f"{x['curto']} {br(x['dia'], 1)}"
                                f"/dia" for x in sorted(
                                    ociosos, key=lambda x: x["dia"]))
                    + "."))
    if atraso:
        # (21/10) so a quantidade: o farol da rota nao mostra valor em R$
        ins.append(("atencao", f"{br(len(atraso))} cliente(s) da rota com "
                               f"título em atraso: cobrar na visita."))
    ins.append(("info", f"{p(pct(nunca, len(vis)))} das visitas são em "
                        f"clientes que nunca compraram: a rota é, na maior "
                        f"parte, de prospecção."))
    ins.append(("info", f"Positivação: {br(comp_rota)} de {br(cli_rota)}"
                        f" clientes da rota compraram em {MESES[mes]}/"
                        f"{str(ano)[2:]}."))
    melhor = max(linhas_v, key=lambda x: (x["comp"], -x["clientes"]),
                 default=None)
    if melhor and melhor["comp"]:
        ins.append(("ok", f"Mais positivados no mês: {melhor['curto']} "
                          f"({br(melhor['comp'])} cliente(s))."))
    sab_curva = Counter(v.get("curva") for v in vis)
    nobres = sum(sab_curva.get(c_, 0) for c_ in ("S", "A", "B"))
    ins.append(("info", f"Curva S, A e B: {br(nobres)} visitas "
                        f"({p(pct(nobres, len(vis)))}); o resto é curva C e "
                        f"Z."))
    carteira = Counter(texto(c.get("vend")) for c in clientes
                       if not c.get("inativo"))
    for x in linhas_v:
        x["carteira"] = carteira.get(x["vend"].split(" - ", 1)[0].strip(),
                                     x["clientes"])
    acima = [x for x in linhas_v
             if x["carteira"] > sum(teto_do(x["vend"], d) for d in uteis)]
    if acima:
        ins.append(("atencao", "Carteira maior que as vagas do mês: "
                    + ", ".join(f"{x['curto']} {br(x['carteira'])} clientes "
                                f"para {br(sum(teto_do(x['vend'], d) for d in uteis))}"
                                f" vagas" for x in sorted(
                                    acima, key=lambda x: -x["carteira"]))
                    + ". Dividir a carteira ou subir o teto."))
    if inativos:
        ins.append(("info", f"{br(inativos)} cliente(s) inativado(s) no "
                            f"Planner, fora da rota."))

    # do mais grave ao informativo
    ins.sort(key=lambda x: {"alerta": 0, "atencao": 1, "ok": 2,
                            "info": 3}.get(x[0], 4))

    # ---- os graficos
    def hb(titulo, pares, fmt, ref=None, cores=None):
        b_ = {"tipo": "hbarras", "titulo": titulo,
              "rotulos": [a for a, _ in pares],
              "valores": [v for _, v in pares], "formato": fmt}
        if ref is not None:
            b_["referencia"] = ref
        if cores:
            b_["cores"] = cores
        return b_
    ord_v = sorted(linhas_v, key=lambda x: -x["dia"])
    b_dia = hb(f"Visitas por dia útil × teto ({teto_pad})",
               [(x["curto"], round(x["dia"], 1)) for x in ord_v], "num1",
               ref=teto_pad,
               cores=[VERDE if x["dia"] >= 0.8 * x["teto"] else
                      (AMARELO if x["dia"] >= 0.5 * x["teto"] else VERMELHO)
                      for x in ord_v])
    ord_o = sorted(linhas_v, key=lambda x: -x["ocup"])
    b_ocup = hb("Ocupação da agenda (dias úteis com rota)",
                [(x["curto"], round(x["ocup"])) for x in ord_o], "pct",
                ref=100,
                cores=[VERDE if x["ocup"] >= 80 else
                       (AMARELO if x["ocup"] >= 50 else VERMELHO)
                       for x in ord_o])
    por_dia = Counter(v["data"] for v in vis)
    # o sabado do EXCEDENTE sai do grafico (achatava os outros dias): o
    # numero dele fica no titulo e no quadro O que a rota diz
    for d in excedente:
        por_dia[d] = 0
    fora_txt = " · ".join(f"sábado {d:%d/%m}: {br(n)} de excedente, fora da "
                          f"escala" for d, n in sorted(excedente.items()))
    b_dd = {"tipo": "barras", "colspan": 2, "grafico": {
        "titulo": f"Visitas planejadas dia a dia · {MESES[mes]}/{str(ano)[2:]}"
                  + (f"  ({fora_txt})" if fora_txt else ""),
        "rotulos": [str(d.day) for d in dias_mes],
        "series": [{"nome": "Visitas", "cor": VERDE,
                    "valores": [por_dia.get(d, 0) for d in dias_mes],
                    "cores": [CINZA if (d.weekday() >= 5 or d in fer)
                              else VERDE for d in dias_mes]}],
        "formato": "num", "rotular": "nao_zero"}}
    ord_s = sorted([x for x in linhas_v if x["sab"]], key=lambda x: -x["sab"])
    b_sab = hb("Visitas no sábado (excedente e último sábado)",
               [(x["curto"], x["sab"]) for x in ord_s] or [("—", 0)], "num",
               cores=[VERMELHO if x["sab"] > 3 * x["teto"] else AMARELO
                      for x in ord_s] or None)
    ordem_sit = ["ATIVO", "CHURN 30", "CHURN 60", "CHURN 90", "CHURN 90+",
                 "NUNCA COMPROU"]
    cor_sit = {"ATIVO": VERDE, "CHURN 30": VERDE, "CHURN 60": AMARELO,
               "CHURN 90": AMARELO, "CHURN 90+": VERMELHO,
               "NUNCA COMPROU": CINZA}
    tem_sit = [s_ for s_ in ordem_sit if sit_vis.get(s_)]
    b_sit = hb("Visitas por situação do cliente",
               [(s_.capitalize(), sit_vis[s_]) for s_ in tem_sit], "num",
               cores=[cor_sit[s_] for s_ in tem_sit])
    ord_c = sorted(linhas_v, key=lambda x: (-pct(x["comp"], x["clientes"]),
                                            x["curto"]))
    b_pos = hb(f"Positivação da carteira em {MESES[mes]} (%)",
               [(x["curto"], round(pct(x["comp"], x["clientes"]), 1))
                for x in ord_c], "pct")
    blocos = [
        {"tipo": "insights", "titulo": "O que a rota diz", "linhas": ins,
         "col": 0, "row": 0, "rowspan": 2},
        dict(b_dia, col=1, row=0), dict(b_ocup, col=2, row=0),
        dict(b_dd, col=1, row=1),
        dict(b_sab, col=0, row=2), dict(b_sit, col=1, row=2),
        dict(b_pos, col=2, row=2)]
    gm = next((g for g in r.get("graficos") or []
               if "mês a mês" in g.get("titulo", "")), None)
    if gm:
        blocos.append({"tipo": "barras", "col": 0, "row": 3, "colspan": 3,
                       "grafico": dict(gm, rotular=True)})
    r["painel"] = {"colunas": (1, 1, 1),
                   "altura_min": 4 * max(250, 70 + 22 * len(linhas_v)),
                   "blocos": blocos}
    r["painel_titulo"] = "Resumo gerencial"
    r["insights_rota"] = ins            # o teste e o e-mail leem daqui


def vendedor_padrao_de(ctx, chave="vendedor_padrao") -> str:
    """(15/10) O VENDEDOR PADRAO do Planner (aba Parametros, 000000): o
    A1_VEND do cliente fora do Planner no .json do Protheus.
    chave="supervisor_padrao": o SUPERVISOR PADRAO (000037)."""
    try:
        import planner_nucleo as nu                     # noqa: PLC0415
        return nu.vendedor_padrao(nu.carregar_config(bd._cfg_planner(
            ctx.raiz)), chave)
    except Exception:                                   # noqa: BLE001
        return "000000" if chave == "vendedor_padrao" else "000037"


def _exportar_base_protheus(ctx):
    """funcao(tabela, linhas_da_tela) -> a BASE DE CLIENTES no layout do
    Protheus: A1_FILIAL, A1_COD, A1_LOJA, A1_VEND, A1_NOME, A1_NREDUZ,
    SUPERVISOR e STATUS. O vendedor e o que a roteirizacao do Planner deu a
    cada cliente. Na aba Calendario ou Por cliente, so os clientes da tela;
    nas outras, a base inteira. (20/10, Alexandre) TODOS vao ATIVO; sem
    vendedor, de cadeira vaga/provisoria ou inativado: com o VENDEDOR e o
    SUPERVISOR PADRAO."""
    import re as _re                                    # noqa: PLC0415

    def montar(t=None, linhas=None):
        import planner_nucleo as nu                     # noqa: PLC0415
        pessoas = ctx.base.get("pessoas") or {}
        v_padrao = vendedor_padrao_de(ctx)
        s_padrao = vendedor_padrao_de(ctx, "supervisor_padrao")
        filiais = nu.filiais_dos_clientes(
            ctx.raiz / "RELATORIOS" / "TABELA_BAP.xlsx")
        padrao = Counter(filiais.values()).most_common(1)
        padrao = padrao[0][0] if padrao else ""
        alvo = None
        pr = (t or {}).get("protheus")
        if pr and linhas is not None:
            vis = ctx.base.get("visitas") or []
            if "i_visita" in pr:
                alvo = {(vis[l[pr["i_visita"]]]["cod"],
                         vis[l[pr["i_visita"]]]["loja"] or "01")
                        for l in linhas}
            else:
                alvo = {tuple(str(l[pr["i_cliente"]]).split("-", 1))
                        for l in linhas}
        saida = []
        for c in ctx.base.get("clientes") or []:
            cod = _re.sub(r"\D", "", texto(c["cod"])).zfill(6)
            loja = _re.sub(r"\D", "", texto(c["loja"])).zfill(2)
            if alvo is not None and (cod, loja) not in alvo and \
                    (cod, texto(c["loja"]) or "01") not in alvo:
                continue
            vend = texto(c.get("vend"))
            pv = pessoas.get(vend) or {}
            # (15/10, Alexandre) fora do Planner (sem vendedor, cadeira
            # vaga/provisoria, inativado): com o VENDEDOR PADRAO (ATIVO, 20/10)
            fora = (not _re.fullmatch(r"\d{6}", vend) or pv.get("provisorio")
                    or bool(c.get("inativo")))
            if fora:
                vend, pv = v_padrao, {}
            chefe = pv.get("chefe", "")
            sup = chefe if (pessoas.get(chefe) or {}).get("cargo") == \
                "SUPERVISOR" else ""
            if fora:
                sup = s_padrao
            saida.append({
                "A1_FILIAL": filiais.get((cod, loja), padrao),
                "A1_COD": cod, "A1_LOJA": loja, "A1_VEND": vend,
                "A1_NOME": c.get("nome", ""),
                "A1_NREDUZ": c.get("fantasia", ""),
                "SUPERVISOR": sup.zfill(6) if sup.isdigit() else sup,
                # (20/10) o nome da coluna do BAP Tools: sempre ATIVO
                "STATUS": nu.status_no_json(fora),
                # (14/10) o ponto do cliente (BASE_CLIENTE/COORDENADAS)
                "LATITUDE": nu.coordenada_protheus(c.get("lat"),
                                                   c.get("lon"))[0],
                "LONGITUDE": nu.coordenada_protheus(c.get("lat"),
                                                    c.get("lon"))[1]})
        saida.sort(key=lambda x: (x["A1_VEND"], x["A1_COD"], x["A1_LOJA"]))
        return saida
    return montar


def _sim_nao(x) -> str:
    return "SIM" if x else "NÃO"


def _qualitativo_dos_clientes(ctx) -> dict:
    """(21/10) O qualitativo de cada cliente da base, como o Planner conta
    (planner_nucleo.indicadores): COM LIMITE = limite aprovado ou
    disponivel > 0; INADIMPLENTE = valor em atraso > 0; COMPRADOR =
    RECEITA_PERIODO (3 meses) > 0. {(cod, loja2): (lim, inad, comp)}."""
    saida = {}
    for c in ctx.base.get("clientes") or []:
        saida[(c["cod"], _loja2(c.get("loja")))] = (
            (c.get("limite") or 0) > 0 or (c.get("limite_disp") or 0) > 0,
            (c.get("atraso") or 0) > 0,
            (c.get("receita_periodo") or 0) > 0)
    return saida


def _qual_da_visita(qual, v) -> tuple:
    """COM LIMITE, INADIMPLENTE e COMPRADOR (SIM/NAO) do cliente da visita.
    Cliente fora da base: o limite e o atraso que vieram na rota."""
    q = qual.get((v["cod"], _loja2(v.get("loja"))))
    if q is None:
        q = ((v.get("limite_disp") or 0) > 0, (v.get("atraso") or 0) > 0,
             False)
    return tuple(_sim_nao(x) for x in q)


def _rota_calendario(r, ctx):
    """
    Aba CALENDARIO do Farol Roteirizacao: as visitas do mes no calendario
    (semana x SEG..SAB), como a Rota por cidade do Planner. As linhas sao
    as visitas - os filtros (vendedor, supervisor, UF, cidade) escolhem o
    que entra na conta de cada dia.
    """
    vis = ctx.base.get("visitas") or []
    if not vis:
        return
    cab = [col("DATA", "data", 85), col("DIA", "texto", 70),
           col("SEMANA", "texto", 75), col("SEQ.", "int", 50),
           col("VENDEDOR", "texto", 220), col("SUPERVISOR", "texto", 200),
           col("UF", "texto", 40), col("CIDADE", "texto", 150),
           col("BAIRRO", "texto", 150), col("ZONA", "texto", 70),
           col("CLIENTE", "texto", 80), col("NOME", "texto", 230),
           col("CURVA", "texto", 55), col("_I", "int", 10, oculta=True),
           # so para a janela do dia (clique no calendario)
           col("SEGMENTO", "texto", 120, oculta=True),
           col("FANTASIA", "texto", 160, oculta=True),
           # (21/10) SIM/NAO em vez do valor em R$
           col("COM LIMITE", "texto", 80, oculta=True),
           col("INADIMPLENTE", "texto", 90, oculta=True)]
    qual = _qualitativo_dos_clientes(ctx)
    ordem = sorted(range(len(vis)), key=lambda i: (
        vis[i]["data"] or date.min, vis[i]["vendedor"], vis[i]["ordem"]))
    linhas = [[vis[i]["data"], vis[i]["dia"], vis[i]["semana"],
               vis[i]["ordem"], vis[i]["vendedor"], vis[i]["supervisor"],
               vis[i]["uf"], vis[i]["cidade"], vis[i]["bairro"],
               vis[i]["zona"], f"{vis[i]['cod']}-{vis[i]['loja'] or '01'}",
               vis[i]["nome"], vis[i]["curva"], i,
               vis[i].get("segmento", ""), vis[i].get("fantasia", ""),
               *_qual_da_visita(qual, vis[i])[:2]]
              for i in ordem]

    def cartoes(ls):
        # A MEDIA E DOS DIAS UTEIS: o sabado (o primeiro e o deposito dos
        # excedentes) aparece a parte, para nao inflar as visitas/dia
        def util(l):
            d = l[0]
            return bool(d) and d.weekday() < 5
        uteis = [l for l in ls if util(l)]
        sab = [l for l in ls if l[0] and l[0].weekday() == 5]
        dias = {l[0] for l in uteis}
        vend = {l[4] for l in ls}
        tetos = ctx.base.get("tetos") or {}
        # (27/10, Alexandre) capacidade = o teto de cada vendedor SO nos dias
        # uteis em que ELE tem rota (antes: todos os vendedores x todos os
        # dias com visita de alguem, e quem entrou no meio do mes contava
        # os dias de antes da admissao); sexta com o teto da sexta
        t_pad = ctx.base.get("teto_padrao") or 0
        t_sex = ctx.base.get("teto_sexta") or 0

        def teto_dia(v, d):
            t = tetos.get(v) or t_pad
            return min(t, t_sex) if (t_sex and d.weekday() == 4) else t
        cap = sum(teto_dia(v, d) for v, d in {(l[4], l[0]) for l in uteis})
        return [
            kpi("Visitas no mês", br(len(ls)), "info",
                f"{br(len({l[10] for l in ls}))} clientes"),
            kpi("Dias úteis com visita", br(len(dias)), "neutro",
                f"{br(len(uteis) / len(dias), 1)} visitas/dia útil"
                if dias else ""),
            kpi("Sábado", br(len(sab)), "atencao" if sab else "neutro",
                " · ".join(f"{d:%d/%m}: {br(n)}" for d, n in sorted(
                    Counter(l[0] for l in sab).items()))
                if sab else "sem visita no sábado"),
            kpi("Vendedores", br(len(vend)), "neutro",
                f"{br(len({(l[6], l[7]) for l in ls}))} cidades"),
            kpi("Ocupação", p(pct_de(len(uteis), cap)) if cap else "—",
                "info", "visitas ÷ capacidade dos dias com rota"),
        ]
    r["tabelas"].append(dict(tabela(
        "Calendário", cab, linhas,
        filtros=("VENDEDOR", "SUPERVISOR", "UF", "CIDADE"),
        kpis_de=cartoes),
        calendario={"mes": ctx.base.get("mes") or "",
                    "feriados": ctx.base.get("feriados") or [],
                    "tetos": ctx.base.get("tetos") or {},
                    "teto_padrao": ctx.base.get("teto_padrao") or 0,
                    "teto_sexta": ctx.base.get("teto_sexta", 6) or 0,
                    "i_data": 0, "i_vendedor": 4, "i_cidade": 7,
                    "i_cliente": 10},
        protheus={"i_visita": 13}))
    # na aba Por cliente, o Protheus leva as visitas dos clientes da tela
    for t in r["tabelas"]:
        if t["titulo"] == "Por cliente":
            nm_ = [c_["nome"] for c_ in t["colunas"]]
            t["protheus"] = {"i_cliente": nm_.index("CLIENTE"),
                             "i_vendedor": nm_.index("VENDEDOR")}


def _exportar_protheus_da_rota(ctx):
    """funcao(tabela, linhas_da_tela) -> as visitas no layout do Protheus
    (o mesmo .json da aba Exportar Protheus do Planner). Sem tabela: a
    rota inteira."""
    vis = ctx.base.get("visitas") or []
    # (15/10) o ponto de cada cliente vai junto (latitude/longitude)
    ponto = {c.get("chave"): (c.get("lat"), c.get("lon"))
             for c in ctx.base.get("clientes") or [] if c.get("chave")}

    def montar(t=None, linhas=None):
        import planner_nucleo as nu                     # noqa: PLC0415
        escolhidas = vis
        pr = (t or {}).get("protheus")
        if pr and linhas is not None:
            if "i_visita" in pr:
                escolhidas = [vis[l[pr["i_visita"]]] for l in linhas]
            else:
                alvo = {(l[pr["i_cliente"]], l[pr["i_vendedor"]])
                        for l in linhas}
                escolhidas = [v for v in vis if
                              (f"{v['cod']}-{v['loja'] or '01'}",
                               v["vendedor"]) in alvo]
        rota = [{"COD_CLIENTE": v.get("cod_cliente") or v["cod"],
                 "LOJA": v.get("loja_cru") or v["loja"],
                 "COD_VENDEDOR": v.get("cod_vend") or
                 v["vendedor"].split(" - ")[0],
                 "DATA": v["data"], "ORDEM_DE_VISITA": v["ordem"] or 1,
                 "CHAVE_CLIENTE": v.get("chave") or "",
                 "CURVA_RECEITA": v["curva"] or "Z",
                 "LATITUDE": ponto.get(v.get("chave"), (None, None))[0],
                 "LONGITUDE": ponto.get(v.get("chave"), (None, None))[1],
                 "SEMANA": v["semana"],
                 # (20/11) o gerador filtra INTERNO pelo nome; gerador
                 # antigo ignora
                 "NOME_CLIENTE": v.get("nome") or "",
                 "NOME_FANTASIA": v.get("fantasia") or "",
                 # (23/11, T-0010) a visita semanal (bap_dados marca b5):
                 # o gerador usa periodicidade 7 (RN-ROT-001)
                 "VISITA_SEMANAL": v.get("visita_semanal") or ""}
                for v in escolhidas if v["data"]]
        return nu.linhas_protheus({}, [], linhas=rota)
    return montar


ROTA_SEM_REP = "SEM REPETIÇÃO"
ROTA_COM_REP = "COM REPETIÇÃO (VISITA A VISITA)"


def _rota_por_cliente(r, ctx):
    """
    Aba POR CLIENTE do Farol Roteirizacao: o analitico da rota.
    VISAO = SEM REPETICAO: uma linha por cliente, com as datas das visitas.
    VISAO = COM REPETICAO: uma linha por visita, na sequencia do vendedor
    (data e ordem do dia) - o cliente aparece tantas vezes quantas visitas.
    """
    vis = ctx.base.get("visitas") or []
    if not vis:
        return
    # (21/10) COM LIMITE, INADIMPLENTE e COMPRADOR (SIM/NAO) no lugar do
    # limite, do atraso e da receita 6M em R$
    qual = _qualitativo_dos_clientes(ctx)
    # (06/10) SEMPRE por DATA e, na data, pela SEQUENCIA de visita (com
    # varios vendedores: data, vendedor, sequencia)
    ordem = sorted(vis, key=lambda v: (v["data"] or date.min, v["vendedor"],
                                       v["ordem"]))
    # (06/10) SEMANA antes do DIA; ENDERECO e Nº do cliente; sem VISITAS NA
    # ROTA, PREVISTAS e DATAS DAS VISITAS na tela e no PDF (ficam ocultas:
    # o cartao de visitas usa); STATUS = o do Planner
    nomes_r = ["VISÃO", "VENDEDOR", "SUPERVISOR", "SEMANA", "DATA", "DIA",
               "SEQ.", "VISITA", "CLIENTE", "NOME", "FANTASIA", "ENDEREÇO",
               "Nº", "BAIRRO", "CIDADE", "UF", "ZONA", "SEGMENTO", "CURVA",
               "VISITAS NA ROTA", "PREVISTAS", "DATAS DAS VISITAS",
               "COM LIMITE", "INADIMPLENTE", "COMPRADOR"]
    J = {n_: i for i, n_ in enumerate(nomes_r)}
    tipo_r = {"DATA": ("data", 85), "SEQ.": ("int", 50),
              "VISITAS NA ROTA": ("int", 100), "PREVISTAS": ("int", 75),
              "COM LIMITE": ("texto", 80), "INADIMPLENTE": ("texto", 90),
              "COMPRADOR": ("texto", 85)}
    larg_r = {"VISÃO": 60, "VENDEDOR": 220, "SUPERVISOR": 200, "SEMANA": 90,
              "DIA": 70, "VISITA": 60, "CLIENTE": 80, "NOME": 230,
              "FANTASIA": 170, "ENDEREÇO": 230, "Nº": 50, "BAIRRO": 150,
              "CIDADE": 150, "UF": 40, "ZONA": 70, "SEGMENTO": 150,
              "CURVA": 55, "DATAS DAS VISITAS": 200}
    ocultas_r = ("VISÃO", "VISITAS NA ROTA", "PREVISTAS", "DATAS DAS VISITAS")
    cab = [col(n_, *tipo_r.get(n_, ("texto", larg_r.get(n_))),
               oculta=n_ in ocultas_r) for n_ in nomes_r]
    linhas, tons = [], []
    por_cliente = {}

    def juntar(xs):
        return "; ".join(dict.fromkeys(x for x in xs if x))

    def linha_(visao, v, visitas, dia, visita, datas, semana):
        return [visao, v["vendedor"], v["supervisor"], semana, v["data"],
                dia, v["ordem"], visita, f"{v['cod']}-{v['loja'] or '01'}",
                v["nome"], v["fantasia"], v.get("endereco") or "",
                v.get("numero") or "", v["bairro"], v["cidade"], v["uf"],
                v["zona"], v["segmento"], v["curva"], len(visitas), v["de"],
                datas, *_qual_da_visita(qual, v)]
    for v in ordem:
        chave = (v["cod"], v["loja"])
        por_cliente.setdefault(chave, []).append(v)
    for v in ordem:
        visitas = por_cliente[(v["cod"], v["loja"])]
        linhas.append(linha_(ROTA_COM_REP, v, visitas, v["dia"],
                             f"{visitas.index(v) + 1}/{len(visitas)}", "",
                             v.get("semana") or ""))
        tons.append("alerta" if linhas[-1][J["INADIMPLENTE"]] == "SIM"
                    else "")
    vistos = set()
    for v in ordem:
        chave = (v["cod"], v["loja"])
        if chave in vistos:
            continue
        vistos.add(chave)
        visitas = por_cliente[chave]
        datas = ", ".join(f"{x['data']:%d/%m}" for x in visitas if x["data"])
        linhas.append(linha_(ROTA_SEM_REP, v, visitas,
                             juntar(x["dia"] for x in visitas), "", datas,
                             juntar(x.get("semana") for x in visitas)))
        tons.append("alerta" if linhas[-1][J["INADIMPLENTE"]] == "SIM"
                    else "")
    I_CLI, I_UF, I_CID, I_NV = J["CLIENTE"], J["UF"], J["CIDADE"], \
        J["VISITAS NA ROTA"]
    I_LIM, I_ATR, I_COM = J["COM LIMITE"], J["INADIMPLENTE"], \
        J["COMPRADOR"]

    def cartoes(ls):
        clientes = {l[I_CLI] for l in ls}
        um = {}
        for l in ls:
            um.setdefault(l[I_CLI], l)
        n_vis = (sum(l[I_NV] or 0 for l in um.values())
                 if not any(l[0] == ROTA_COM_REP for l in ls) else len(ls))
        cid = {(l[I_UF], l[I_CID]) for l in ls}
        n_lim = sum(1 for l in um.values() if l[I_LIM] == "SIM")
        n_atr = sum(1 for l in um.values() if l[I_ATR] == "SIM")
        n_com = sum(1 for l in um.values() if l[I_COM] == "SIM")
        return [
            kpi("Cidades", br(len(cid)), "neutro"),
            kpi("Clientes", br(len(clientes)), "neutro"),
            kpi("Visitas no mês", br(n_vis), "info",
                f"{br(n_vis / len(clientes), 1)} por cliente"
                if clientes else ""),
            kpi("Com limite", br(n_lim), "info", p(pct_de(n_lim, len(um)))),
            kpi("Inadimplentes", br(n_atr), "alerta" if n_atr else "ok",
                p(pct_de(n_atr, len(um)))),
            kpi("Compradores", br(n_com), "ok", p(pct_de(n_com, len(um))))]
    r["tabelas"].append(tabela(
        "Por cliente", cab, linhas, tons,
        filtros=({"coluna": "VISÃO", "padrao": ROTA_SEM_REP},
                 {"coluna": "SEMANA", "multi": True},
                 {"coluna": "DIA", "multi": True}, "UF", "CIDADE",
                 "VENDEDOR", "SUPERVISOR", "COM LIMITE", "INADIMPLENTE",
                 "COMPRADOR"),
        kpis_de=cartoes))
    t_r = r["tabelas"][-1]
    try:                    # STATUS (o do Planner) antes da CURVA
        com_status(ctx, t_r, J["CURVA"], I_CLI, situacao=False)
        for c_ in t_r["colunas"]:
            if c_["nome"] == COL_ST_PROTHEUS:
                c_["oculta"] = True
            elif c_["nome"] == COL_ST_PLANNER:
                c_["nome"] = "STATUS"
        t_r["filtros"] = ["STATUS" if x == COL_ST_PLANNER else x
                          for x in t_r["filtros"] if x != COL_ST_PROTHEUS]
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Status do cliente fora da tabela: {erro}")
    nm_ = [c_["nome"] for c_ in t_r["colunas"]]
    i_d, i_v, i_s = nm_.index("DATA"), nm_.index("VENDEDOR"), \
        nm_.index("SEQ.")
    # a ordem de SEMPRE no PDF e no Excel, mesmo com a tela reordenada
    t_r["ordem_exportar"] = lambda l: (l[i_d] or date.min, str(l[i_v]),
                                       l[i_s] or 0)
    curto_r = {"COM LIMITE": "LIMITE", "INADIMPLENTE": "INADIMPL.",
               "COMPRADOR": "COMPROU 3M"}
    for c_ in t_r["colunas"]:
        c_["pdf_nome"] = curto_r.get(c_["nome"], c_["nome"])
    t_r["pdf"] = {
        "compacto": True, "sem_rs": True, "verticais": True, "zebra": True,
        "traco_zero": True, "data_curta": True, "corpo": 6.2, "cab": 5.5,
        "pad": 2.5, "colapsa": ("VENDEDOR", "SUPERVISOR", "SEMANA", "UF",
                                "ZONA", "SEGMENTO", "STATUS"),
        "quebra": ("ENDEREÇO",), "inteiras": ("CLIENTE",),
        "nome_curto": ("SUPERVISOR",), "contagem": "linhas",
        "grupos": [("", ["VENDEDOR", "SUPERVISOR"]),
                   ("VISITA", ["SEMANA", "DATA", "DIA", "SEQ.", "VISITA"]),
                   ("CLIENTE", ["CLIENTE", "NOME", "FANTASIA", "ENDEREÇO",
                                "Nº", "BAIRRO", "CIDADE", "UF", "ZONA",
                                "SEGMENTO", "STATUS", "CURVA"]),
                   ("CLIENTE TEM", ["COM LIMITE", "INADIMPLENTE",
                                    "COMPRADOR"])]}


# o RECORTE do Farol de Clientes: escolhido em cima (como o mes), vale
# para todas as abas - segmento, familia, produto, cidade...
RECORTE_CLIENTES = (
    ("VENDEDOR", lambda c: c.get("vend_nome") or "(SEM VENDEDOR)"),
    ("SUPERVISOR", lambda c: c.get("supervisor") or "(SEM SUPERVISOR)"),
    ("UF", lambda c: c.get("uf") or "(SEM UF)"),
    ("CIDADE", lambda c: f"{c.get('cidade') or '(SEM CIDADE)'}/"
                         f"{c.get('uf') or '-'}"),
    ("ZONA", lambda c: " - ".join(x for x in (c.get("zona"),
                                              c.get("zona_nome")) if x)
     or "(SEM ZONA)"),
    ("CLIENTE", lambda c: f"{c['cod']} - "
                          f"{c.get('fantasia') or c.get('nome') or ''}"
                          .strip(" -")),
)
TODOS_RECORTE = "(todos)"


def recorte_de_clientes(ctx, r, clientes):
    """Aplica o recorte escolhido (vendedor, supervisor, UF, cidade, zona,
    cliente) e poe as caixas na barra de cima. As opcoes de cada caixa vem
    dos clientes que sobram nas OUTRAS escolhas (escolheu o vendedor, a
    cidade so mostra as dele). Devolve (clientes do recorte, texto)."""
    escolha = {nome: ctx.param(nome) for nome, _ in RECORTE_CLIENTES}
    for nome, f in RECORTE_CLIENTES:
        outros = [c for c in clientes if all(
            v is None or g(c) == v for (n, g), v in
            ((x, escolha[x[0]]) for x in RECORTE_CLIENTES) if n != nome)]
        valores = sorted({f(c) for c in outros})
        if escolha[nome] is not None and escolha[nome] not in valores:
            valores.append(escolha[nome])
        r.setdefault("parametros", []).append({
            "nome": nome, "valores": [TODOS_RECORTE] + valores,
            "valor": escolha[nome] or TODOS_RECORTE})
    sel = [c for c in clientes if all(
        escolha[n] is None or f(c) == escolha[n] for n, f in RECORTE_CLIENTES)]
    texto_ = " · ".join(f"{n.capitalize()}: {escolha[n]}"
                        for n, _ in RECORTE_CLIENTES if escolha[n])
    return sel, texto_


FILTROS_PRODUTO = CLASSE_PRODUTO + ("PRODUTO",)


def recorte_de_produto(ctx, r, cods):
    """(10/10) CATEGORIA, SISTEMA, FAMILIA, LINHA (15/10) e PRODUTO na barra
    de cima - o filtro padrao de produto. As opcoes de cada caixa seguem as
    outras escolhas (escolheu BATERIAS, o sistema, a familia e o produto so
    mostram bateria). cods: os produtos que existem no farol. Devolve
    (ok(cod) ou None, texto)."""
    esc = {n: ctx.param(n) for n in FILTROS_PRODUTO}
    cods = {texto(c) for c in cods if texto(c)}
    info = {c: {n: ctx.classe(c, n) for n in CLASSE_PRODUTO} for c in cods}

    def passa(c, menos):
        return all(n == menos or not esc[n] or info[c][n] == esc[n]
                   for n in CLASSE_PRODUTO) and \
            (menos == "PRODUTO" or not esc["PRODUTO"] or c == esc["PRODUTO"])
    for nome in FILTROS_PRODUTO:
        resto = [c for c in cods if passa(c, nome)]
        if nome in CLASSE_PRODUTO:
            vals = ordem_da_classe(nome, {info[c][nome] for c in resto})
        else:
            vals = [(c, f"{c} - {ctx.produto(c)}".strip(" -"))
                    for c in sorted(resto)]
        chaves = [v[0] if isinstance(v, tuple) else v for v in vals]
        if esc[nome] is not None and esc[nome] not in chaves:
            vals.append(esc[nome])
        r.setdefault("parametros", []).append({
            "nome": nome, "valores": [TODOS_RECORTE] + vals,
            "valor": esc[nome] or TODOS_RECORTE})
    if not any(esc.values()):
        return None, ""

    def ok(cod):
        c = texto(cod)
        x = info.get(c) or {n: ctx.classe(c, n) for n in CLASSE_PRODUTO}
        return (all(not esc[n] or x[n] == esc[n] for n in CLASSE_PRODUTO)
                and (not esc["PRODUTO"] or c == esc["PRODUTO"]))
    txt = " · ".join(f"{n.capitalize()}: {esc[n]}" for n in FILTROS_PRODUTO
                     if esc[n])
    return ok, txt


# =========================================================================
# (07/10) BASE PROTHEUS - o cadastro do Protheus (A1_VEND da dClientesBap)
# ao lado da carteira do Planner, para acompanhar a conciliacao. Tudo nos
# farois continua pela base do Planner; esta coluna so CONTA o Protheus.
# =========================================================================
def _vend6(v) -> str:
    v = texto(v)
    return v.zfill(6) if v.isdigit() else v


def _lojas_protheus(ctx) -> dict:
    return ctx.tabela.get("protheus_lojas") or {}


def _vendedores_do_planner(ctx) -> dict:
    """{cod: {nome, chefe, cargo}} das pessoas do Planner (com 6 digitos).
    (18/10) montado uma vez por relatorio (era refeito a cada loja)."""
    pes = ctx.__dict__.get("_memo_pessoas")
    if pes is None:
        pes = {_vend6(k): v for k, v in
               (ctx.base.get("pessoas") or {}).items()}
        ctx.__dict__["_memo_pessoas"] = pes
    return pes


def _sup_nome(ctx, vend) -> str:
    memo = ctx.__dict__.setdefault("_memo_sup", {})
    if vend in memo:
        return memo[vend]
    pes = _vendedores_do_planner(ctx)
    chefe = (pes.get(_vend6(vend)) or {}).get("chefe", "")
    memo[vend] = (pes.get(_vend6(chefe)) or {}).get("nome", "")
    return memo[vend]


def base_protheus_contar(ctx, vend=None, supervisor=None, sem_vendedor=False,
                         filtro=None) -> int:
    """Quantas lojas o Protheus da ao vendedor (A1_VEND), ou a todos os
    vendedores do supervisor. sem_vendedor: as lojas cujo A1_VEND nao e
    vendedor do Planner (ou esta vazio). filtro(loja) -> bool: o recorte
    (UF, cidade...) aplicado no cadastro do Protheus."""
    pes = _vendedores_do_planner(ctx)
    planner = ctx.__dict__.get("_memo_planner_vend")
    if planner is None:
        planner = {v for v, x in pes.items()
                   if x.get("cargo") != "SUPERVISOR"} \
            | {_vend6(c.get("vend")) for c in ctx.base.get("clientes") or []
               if c.get("vend")}
        ctx.__dict__["_memo_planner_vend"] = planner
    lojas = ctx.__dict__.get("_memo_lojas_v6")
    if lojas is None:          # (18/10) o A1_VEND de cada loja, uma vez so
        lojas = [(cod, loja, x, _vend6(x.get("vend")))
                 for (cod, loja), x in _lojas_protheus(ctx).items()]
        ctx.__dict__["_memo_lojas_v6"] = lojas
    n = 0
    for cod, loja, x, v in lojas:
        if sem_vendedor:
            ok = not v or v not in planner
        elif vend is not None:
            ok = v == _vend6(vend)
        elif supervisor is not None:
            ok = bool(v) and _sup_nome(ctx, v) == supervisor
        else:
            ok = True
        if ok and (filtro is None or filtro(cod, loja, x)):
            n += 1
    return n


def _lugar(x) -> str:
    """UF/cidade para cruzar o Planner com o Protheus: maiuscula, sem
    acento e sem espaco sobrando ("São Luís" = "SAO LUIS")."""
    import unicodedata as _ud                           # noqa: PLC0415
    t = _ud.normalize("NFKD", texto(x)).encode("ascii", "ignore").decode()
    return " ".join(t.upper().split())


def _base_protheus_por_lugar(ctx):
    """(21/10) Quantas lojas o Protheus tem em cada UF (A1_EST) e em cada
    cidade (A1_MUN + A1_EST), para a coluna BASE PROTHEUS das abas Por UF
    e Por cidade do Farol Roteirizacao. Devolve ({uf: n}, {(cid, uf): n})."""
    por_uf, por_cid = Counter(), Counter()
    for x in _lojas_protheus(ctx).values():
        uf = _lugar(x.get("uf"))
        por_uf[uf] += 1
        por_cid[(_lugar(x.get("cidade")), uf)] += 1
    return por_uf, por_cid


def _filtro_protheus_do_recorte(ctx, clientes):
    """O recorte do Farol de Clientes (UF, cidade, zona, cliente) no
    cadastro do Protheus: UF e cidade pelo A1_EST/A1_MUN; zona e cliente
    pelos clientes do recorte (o Protheus nao tem zona)."""
    uf, cid = ctx.param("UF"), ctx.param("CIDADE")
    zona, cli = ctx.param("ZONA"), ctx.param("CLIENTE")
    if not any((uf, cid, zona, cli)):
        return None
    cods = {c["cod"] for c in clientes} if (zona or cli) else None

    def f(cod, loja, x):
        if uf and x.get("uf") != uf:
            return False
        if cid and f"{x.get('cidade') or '(SEM CIDADE)'}/{x.get('uf') or '-'}" \
                != cid:
            return False
        return cods is None or cod in cods
    return f


def base_e_oportunidades(ctx):
    hoje = ctx.hoje
    r = novo("vc_base", VEN, "Farol de Clientes",
             "8 segmentos",
             "BASE_CLIENTE + Planner + Gerador de Meta + TABELA_BAP")
    capa(r, ctx, anos_dos_dados(ctx))
    # (12/10) AUDITORIA: a CARTEIRA DO MES (a do Painel Executivo e do
    # Farol de Metas), um por codigo; quem nao tem vendedor no PLANNER do
    # mes fica fora das contas (ve-se no farol Divergencias)
    cart = carteira_do_mes(ctx)
    universo = (_clientes_da_carteira(ctx, cart) if cart
                else ctx.base["clientes"])
    if cart:
        _ks = {(k[0], _loja2(k[1])) for k in cart["lojas"]}
        _fora = sum(1 for c in ctx.base["clientes"]
                    if (c["cod"], _loja2(c.get("loja"))) not in _ks)
        if _fora:
            r["avisos"].append(
                f"Carteira do mês (PLANNER): {br(_fora)} lojas da BASE_CLIENTE "
                "sem vendedor no Planner ficam fora (farol Divergências).")
    clientes, rec_txt = recorte_de_clientes(ctx, r, universo)
    no_recorte = {c["cod"] for c in clientes} if rec_txt else None
    # (10/10) CATEGORIA, FAMILIA e PRODUTO em cima: o faturamento 6M, quem
    # comprou e o TOP 30 passam a ser SO do produto escolhido
    prod_ok, prod_txt = recorte_de_produto(
        ctx, r, {it["cod"] for it in ctx.tabela["itens"]
                 if it["tipo"] == "VND"})
    if rec_txt or prod_txt:
        r["subtitulo"] = " · ".join(x for x in ("8 segmentos", rec_txt,
                                                prod_txt) if x)
    itens_vnd = [it for it in ctx.tabela["itens"] if it["tipo"] == "VND"
                 and (no_recorte is None or it["cliente"] in no_recorte)
                 and (prod_ok is None or prod_ok(it["cod"]))]
    if prod_txt:
        r["avisos"].append(f"{prod_txt}: faturamento 6M, compra no período, "
                           "famílias, produtos e Top 30 só desse produto; "
                           "meta, limite e status são do cliente.")
    graficos_tempo(r, ctx, "Clientes com compra",
                   _ev_positivados(ctx, itens_vnd), "num", AZUL, "unicos")
    opo = {}
    try:                        # so o ultimo produto e o telefone
        for l in ctx.oportunidade["linhas"]:
            opo.setdefault(texto(l.get("cod_cliente")).zfill(6), l)
    except Exception:                                   # noqa: BLE001
        pass
    # (12/10) META e REALIZADO iguais aos do Painel Executivo: a meta de
    # cada loja (com CATEGORIA/FAMILIA escolhida, a meta nela), o real
    # liquido (venda - devolucao) do mes por codigo, uma vez so
    esc_p = {n: ctx.param(n) for n in FILTROS_PRODUTO}

    def meta_da_loja(c):
        s_ = c.get("_meta")
        if s_ is None:
            return (opo.get(c["cod"]) or {}).get("meta") or 0.0
        if esc_p["PRODUTO"]:
            return 0.0
        m_ = meta_do_filtro(s_, esc_p)
        return (s_.get("meta") or 0.0) if m_ is None else m_
    real_cod = defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["tipo"] in ("VND", "DEV") and it["dt_nf"] \
                and no_mes(ctx, it["dt_nf"]) \
                and (prod_ok is None or prod_ok(it["cod"])):
            v = _liquido(it)
            if v is not None:
                real_cod[it["cliente"]] += v
    principal = set()            # a 1a loja de cada codigo leva o real
    _vistos = set()
    for c in universo:
        if c["cod"] not in _vistos:
            _vistos.add(c["cod"])
            principal.add(id(c))

    def real_da_loja(c):
        return (real_cod.get(c["cod"], 0.0)
                if id(c) in principal else 0.0)
    compr_mes, fat6 = set(), defaultdict(float)
    desde = hoje - timedelta(days=183)
    por_fam_cli = defaultdict(set)
    por_fam_val = defaultdict(float)
    por_prod = defaultdict(lambda: {"cli": set(), "val": 0.0, "qtd": 0.0})
    for it in itens_vnd:
        if no_mes(ctx, it["dt_nf"]):
            if positivou(ctx, it["cliente"], it["dt_nf"]):
                compr_mes.add(it["cliente"])
        if it["dt_nf"] and it["dt_nf"] >= desde:
            fat6[it["cliente"]] += it["valor"]
            f = ctx.familia(it["cod"])
            por_fam_cli[f].add(it["cliente"])
            por_fam_val[f] += it["valor"]
            pp = por_prod[it["cod"]]
            pp["cli"].add(it["cliente"])
            pp["val"] += it["valor"]
            pp["qtd"] += it["qtd"]
    ativos = {c["cod"] for c in clientes if c["status"] in
              ("ATIVO", "CHURN 30", "CHURN 60")}
    base_cods = {c["cod"] for c in clientes}

    def agrupar(chave, tot=False):
        """(12/10) CLIENTES, ATIVOS, COMPRARAM...: CODIGOS (um cliente com
        3 lojas conta 1), como no Painel e no Farol de Metas; CLIENTES sem
        os inativados. Meta: a soma das lojas; real: uma vez por codigo."""
        g = defaultdict(Counter)
        vistos = set()
        for c in clientes:
            k = "TOTAL" if tot else (c.get(chave) or "(vazio)")
            x = g[k]
            x["limite"] += c["limite_disp"]
            x["meta"] += meta_da_loja(c)
            x["real"] += real_da_loja(c)
            x["receita"] += c["receita_6m"]
            if (k, c["cod"]) in vistos:
                continue
            vistos.add((k, c["cod"]))
            x["clientes"] += not ctx.inativo(c["cod"], c.get("loja"))
            x["ativos"] += c["cod"] in ativos
            x["compraram"] += c["cod"] in compr_mes
            x["nunca"] += c["status"] == "NUNCA COMPROU"
            x["com_limite"] += c["limite_disp"] > 0
            x["prontos"] += c["limite_disp"] > 0 and c["cod"] not in compr_mes
        if cart and not rec_txt and not tot:   # a venda fora da carteira
            for cod in ({c_ for c_ in real_cod if c_ not in base_cods}
                        | {c_ for c_ in compr_mes if c_ not in base_cods}):
                k = (territorio_do_cliente(ctx, cod, chave)
                     if chave in ("segmento", "uf") else FORA_PLANNER_META)
                g[k]["real"] += real_cod.get(cod, 0.0)
                g[k]["compraram"] += cod in compr_mes
        return g
    cols = [col("CLIENTES", "int"), col("ATIVOS", "int"),
            col("COMPRARAM NO MÊS", "int", 115), col("% POSITIVAÇÃO", "pct", 95),
            col("NUNCA COMPRARAM", "int", 110), col("COM LIMITE", "int", 85),
            col("C/ LIMITE E S/ COMPRA", "int", 130),
            col("LIMITE DISP.", "moeda"), col("RECEITA 6M", "moeda"),
            col("META", "moeda"), col("REALIZADO", "moeda"),
            col("OPORTUNIDADE (FALTA)", "moeda", 130)]

    def nums(x):
        return [x["clientes"], x["ativos"], x["compraram"],
                pct_de(x["compraram"], x["clientes"]), x["nunca"],
                x["com_limite"], x["prontos"], x["limite"], x["receita"],
                x["meta"], x["real"], max(0.0, x["meta"] - x["real"])]

    def cartoes_agr(n_cab):
        def f(ls):
            s = [sum((l[n_cab + j] or 0) for l in ls) for j in range(12)]
            return [
                kpi("Clientes", br(s[0]), "neutro"),
                kpi("Ativos", br(s[1]), "ok", "até 90 dias"),
                kpi(f"Compraram {no_periodo_txt(ctx)}", br(s[2]), "ok", p(pct_de(s[2], s[0]))),
                kpi("Com limite e sem compra", br(s[6]), "atencao"),
                kpi("Limite disponível", moeda(s[7]), "info"),
                kpi("Oportunidade (falta)", moeda(s[11]), "alerta",
                    rotulo_mes(ctx.oportunidade.get('competencia', ''))),
            ]
        return f
    tot = agrupar("segmento", tot=True).get("TOTAL") or Counter()
    if cart and not rec_txt:          # o TOTAL com a venda fora da carteira
        for cod in ({c_ for c_ in real_cod if c_ not in base_cods}
                    | {c_ for c_ in compr_mes if c_ not in base_cods}):
            tot["real"] += real_cod.get(cod, 0.0)
            tot["compraram"] += cod in compr_mes
    r["kpis"] = cartoes_agr(1)([["T"] + nums(tot)])
    r["kpis"][0]["detalhe"] = ("no recorte" if rec_txt else
                               f"{br(ctx.base.get('excluidos'))} excluídos")
    _f_bp = _filtro_protheus_do_recorte(ctx, clientes)
    _cod_de_nome = {}
    for c in clientes:
        if c.get("vend"):
            _cod_de_nome[c.get("vend_nome")] = c["vend"]
    for _cod, _x in _vendedores_do_planner(ctx).items():
        _cod_de_nome.setdefault(_x.get("nome"), _cod)
    _vend_esc = ctx.param("VENDEDOR")

    def _bp_linha(chave, k):
        if chave == "vend_nome":
            if k == "(SEM VENDEDOR)":
                return base_protheus_contar(ctx, sem_vendedor=True,
                                            filtro=_f_bp)
            return base_protheus_contar(ctx, vend=_cod_de_nome.get(k, k),
                                        filtro=_f_bp)
        if _vend_esc:               # recorte de vendedor: so o dele
            return base_protheus_contar(
                ctx, vend=_cod_de_nome.get(_vend_esc, _vend_esc),
                filtro=_f_bp)
        if k == "(SEM SUPERVISOR)":
            return None
        return base_protheus_contar(ctx, supervisor=k, filtro=_f_bp)

    for chave, titulo, extra in (
            ("uf", "Por UF", None), ("segmento", "Por segmento", None),
            ("cidade", "Por cidade", "uf"), ("vend_nome", "Por vendedor", None),
            ("supervisor", "Por supervisor", None)):
        g = agrupar(chave)
        if extra:
            uf_de = {c["cidade"]: c["uf"] for c in clientes}
            linhas = [[k, uf_de.get(k, "")] + nums(x) for k, x in g.items()]
            cab = [col(titulo[4:].upper(), "texto", 190), col("UF", "texto", 40)]
            filtros = ("UF",)
        elif chave in ("vend_nome", "supervisor"):
            # (07/10) BASE PROTHEUS: as lojas que o Protheus da a quem esta
            # na linha (A1_VEND) - o resto da linha segue o Planner
            linhas = [[k, _bp_linha(chave, k)] + nums(x) for k, x in g.items()]
            if chave == "vend_nome":
                # (SEM VENDEDOR) = o resto do cadastro: A1_VEND vazio ou de
                # quem nao tem carteira no Planner (o TOTAL e o Protheus todo)
                sem = [l for l in linhas if l[0] == "(SEM VENDEDOR)"]
                if not sem and not rec_txt:      # (12/10) a carteira so tem
                    sem = [["(SEM VENDEDOR)", 0] + nums(Counter())]  # quem
                    linhas.append(sem[0])        # tem vendedor no Planner
                if sem:
                    sem[0][1] = base_protheus_contar(ctx, filtro=_f_bp) - sum(
                        l[1] or 0 for l in linhas if l[0] != "(SEM VENDEDOR)")
            cab = [col(titulo[4:].upper(), "texto", 220),
                   col("BASE PROTHEUS", "int", 105)]
            filtros = ()
            linhas.sort(key=lambda l: -(l[-1] or 0))
            r["tabelas"].append(tabela(
                titulo, cab + cols, linhas, filtros=filtros,
                total=["TOTAL", sum(l[1] or 0 for l in linhas)] + nums(tot),
                kpis_de=cartoes_agr(len(cab))))
            continue
        else:
            linhas = [[k] + nums(x) for k, x in g.items()]
            cab = [col(titulo[4:].upper(), "texto", 220)]
            filtros = ()
        linhas.sort(key=lambda l: -(l[-1] or 0))
        r["tabelas"].append(tabela(titulo, cab + cols, linhas, filtros=filtros,
                                   total=["TOTAL"] + [""] * (len(cab) - 1)
                                   + nums(tot), kpis_de=cartoes_agr(len(cab))))
    n_ativos = len(ativos)
    lin_f = []
    for f, clis in por_fam_cli.items():
        cb = clis & base_cods
        lin_f.append([f, len(cb), por_fam_val[f], pct_de(len(cb & ativos), n_ativos),
                      len(ativos - cb), por_fam_val[f] / len(clis) if clis else 0])
    lin_f.sort(key=lambda l: -l[2])
    r["tabelas"].append(tabela(
        "Por família (6 meses)",
        [col("FAMÍLIA", "texto", 200), col("CLIENTES QUE COMPRAM", "int", 140),
         col("FATURAMENTO 6M", "moeda", 120), col("% DOS ATIVOS", "pct", 90),
         col("ATIVOS QUE NÃO COMPRAM", "int", 150), col("TICKET/CLIENTE", "moeda")],
        lin_f))
    est = defaultdict(float)
    for e in ctx.tabela["estoque"]:
        est[e["cod"]] += max(0.0, e["qatu"] - e["reserva"])
    lin_p = []
    for cod, x in sorted(por_prod.items(), key=lambda kv: -kv[1]["val"])[:400]:
        cb = x["cli"] & base_cods
        lin_p.append([cod, ctx.produto(cod), ctx.categoria_bap(cod),
                      ctx.sistema(cod), ctx.familia(cod), ctx.linha(cod),
                      len(cb), x["qtd"],
                      x["val"], len(ativos - cb), est.get(cod, 0.0)])
    r["tabelas"].append(tabela(
        "Por produto (top 400, 6 meses)",
        [col("PRODUTO", "texto", 140), col("DESCRIÇÃO", "texto", 280),
         col("CATEGORIA", "texto", 110), col("SISTEMA", "texto", 110),
         col("FAMÍLIA", "texto", 160), col("LINHA", "texto", 90),
         col("CLIENTES", "int"),
         col("QTD", "num"), col("FATURAMENTO", "moeda"),
         col("ATIVOS SEM O PRODUTO", "int", 140), col("ESTOQUE BAP", "num")],
        lin_p, filtros=FILTROS_PRODUTO))
    # CLIENTES (06/10): UF antes da CIDADE, ENDERECO e NUMERO; sem STATUS
    # PROTHEUS, SITUACAO, SUPERVISOR e COMPROU NO MES na tela e no PDF (as
    # tres ultimas ficam ocultas: servem ao filtro, aos recortes e aos
    # cartoes); STATUS PLANNER vira STATUS
    nomes_c = ["CÓD.", "CLIENTE", "UF", "CIDADE", "ENDEREÇO", "Nº",
               "SEGMENTO", "VENDEDOR PLANNER", "SUPERVISOR PLANNER",
               # (07/10) o vendedor do cadastro do Protheus (A1_VEND) e o
               # supervisor dele, ao lado do Planner: a conciliacao
               "VENDEDOR PROTHEUS", "SUPERVISOR PROTHEUS", COL_SIT_PLANNER,
               "CURVA", "DIAS S/ COMPRA", "LIMITE DISP.", "EM ATRASO",
               "FAT. 6M", "META", "REALIZADO", "FALTA", "COMPROU NO MÊS",
               "ÚLTIMO PRODUTO", "TELEFONE", "CONTATO"]
    J = {n_: i for i, n_ in enumerate(nomes_c)}
    I_SIT, I_LIM, I_ATR, I_FAT, I_FALTA, I_COMPROU = (
        J[COL_SIT_PLANNER], J["LIMITE DISP."], J["EM ATRASO"], J["FAT. 6M"],
        J["FALTA"], J["COMPROU NO MÊS"])
    lin_c, tons = [], []
    _lj_c = _lojas_protheus(ctx)
    _pes_c = _vendedores_do_planner(ctx)

    def _prot(c):
        v = _vend6((_lj_c.get((texto(c["cod"]).zfill(6),
                               _loja2(c.get("loja")))) or {}).get("vend"))
        if not v:
            return "(vazio)", ""
        return ((_pes_c.get(v) or {}).get("nome") or v,
                _sup_nome(ctx, v) or "")
    for c in clientes:
        o = opo.get(c["cod"], {})
        vpr, spr = _prot(c)
        meta, real = meta_da_loja(c), real_da_loja(c)
        lin_c.append([c["cod"], c["fantasia"] or c["nome"], c["uf"],
                      c["cidade"], c.get("endereco") or "",
                      c.get("numero") or "", c["segmento"], c["vend_nome"],
                      c["supervisor"], vpr, spr, c["status"], c["curva"],
                      c["dias_sem_compra"], c["limite_disp"], c["atraso"],
                      fat6.get(c["cod"], 0.0), meta, real,
                      max(0.0, meta - real),
                      "SIM" if c["cod"] in compr_mes else "",
                      o.get("ult_produto_nome") or "", o.get("fone") or "",
                      c.get("contato") or ""])
        tons.append("ok" if c["cod"] in compr_mes else
                    ("atencao" if c["limite_disp"] > 0 else ""))
    ordem = sorted(range(len(lin_c)), key=lambda i: (-lin_c[i][I_FALTA],
                                                     -lin_c[i][I_LIM]))
    recortes = [
        ("Churn 30 (31 a 60 dias)", lambda l: l[I_SIT] == "CHURN 30"),
        ("Churn 60 (61 a 90 dias)", lambda l: l[I_SIT] == "CHURN 60"),
        ("Churn 90 (mais de 90 dias)",
         lambda l: l[I_SIT] in ("CHURN 90", "CHURN 90+", "INATIVO")),
        ("Com limite", lambda l: (l[I_LIM] or 0) > 0),
        (f"Com limite e sem compra {no_periodo_txt(ctx)}",
         lambda l: (l[I_LIM] or 0) > 0 and l[I_COMPROU] != "SIM"),
        ("Só adimplentes", lambda l: not (l[I_ATR] or 0)),
        ("Top 30 (maior faturamento 6M)", {"top": 30, "coluna": I_FAT,
                                            "so_positivo": True}),
        (f"Comprou {no_periodo_txt(ctx)}", lambda l: l[I_COMPROU] == "SIM"),
        ("Nunca comprou", lambda l: l[I_SIT] == "NUNCA COMPROU"),
    ]

    def cartoes_cli(ls):
        return [
            kpi("Clientes", br(len(ls)), "neutro"),
            kpi("Ativos", br(sum(1 for l in ls if l[I_SIT] in
                                 ("ATIVO", "CHURN 30", "CHURN 60"))), "ok"),
            kpi(f"Compraram {no_periodo_txt(ctx)}",
                br(sum(1 for l in ls if l[I_COMPROU] == "SIM")), "ok"),
            kpi("Com limite e sem compra", br(sum(
                1 for l in ls if (l[I_LIM] or 0) > 0
                and l[I_COMPROU] != "SIM")), "atencao"),
            kpi("Limite disponível",
                moeda(sum(max(0, l[I_LIM] or 0) for l in ls)), "info"),
            kpi("Faturamento 6M", moeda(sum(l[I_FAT] or 0 for l in ls)),
                "neutro",
                f"oportunidade {moeda(sum(l[I_FALTA] or 0 for l in ls))}"),
        ]
    tipo_c = {"LIMITE DISP.": ("moeda", 100), "EM ATRASO": ("moeda", 95),
              "FAT. 6M": ("moeda", 95), "META": ("moeda", 90),
              "REALIZADO": ("moeda", 90), "FALTA": ("moeda", 90),
              "DIAS S/ COMPRA": ("int", 95)}
    larg_c = {"CÓD.": 65, "CLIENTE": 220, "UF": 40, "CIDADE": 120,
              "ENDEREÇO": 240, "Nº": 50, "SEGMENTO": 150,
              "VENDEDOR PLANNER": 180, "SUPERVISOR PLANNER": 180,
              "VENDEDOR PROTHEUS": 180, "SUPERVISOR PROTHEUS": 180,
              COL_SIT_PLANNER: 135, "CURVA": 50,
              "COMPROU NO MÊS": 100, "ÚLTIMO PRODUTO": 220,
              "TELEFONE": 120, "CONTATO": 200}
    ocultas = ("COMPROU NO MÊS",)
    cols_c = [col(n_, *tipo_c.get(n_, ("texto", larg_c.get(n_))),
                  oculta=n_ in ocultas) for n_ in nomes_c]
    r["tabelas"].append(tabela(
        "Clientes", cols_c,
        [lin_c[i] for i in ordem], [tons[i] for i in ordem],
        filtros=("UF", "SEGMENTO", "VENDEDOR PLANNER", "SUPERVISOR PLANNER",
                 "VENDEDOR PROTHEUS", "CURVA"),
        recortes=recortes, kpis_de=cartoes_cli))
    t_c = r["tabelas"][-1]
    try:
        com_status(ctx, t_c, I_SIT,
                   chaves=[(clientes[i]["cod"], clientes[i]["loja"])
                           for i in ordem], situacao=False)
        for c_ in t_c["colunas"]:
            if c_["nome"] in (COL_ST_PROTHEUS, COL_SIT_PLANNER):
                c_["oculta"] = True          # fora da tela e do PDF
            elif c_["nome"] == COL_ST_PLANNER:
                c_["nome"] = "STATUS"        # ATIVO / INATIVO
        f = [x for x in t_c["filtros"] if x not in (COL_ST_PROTHEUS,
                                                    COL_SIT_PLANNER)]
        f = ["STATUS" if x == COL_ST_PLANNER else x for x in f]
        if "STATUS" in f:
            f.remove("STATUS")
            f.insert(f.index("CURVA"), "STATUS")
        t_c["filtros"] = f
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Status do cliente fora da tabela: {erro}")
    # PDF ENXUTO (06/10): so o ENDERECO e o ULTIMO PRODUTO quebram linha
    t_c["pdf"] = {"compacto": True, "sem_rs": True, "verticais": True,
                  "zebra": True, "traco_zero": True, "corpo": 6.2,
                  "cab": 5.5, "pad": 2.5,
                  "nome_curto": ("VENDEDOR PLANNER",),
                  "colapsa": ("UF", "SEGMENTO", "VENDEDOR PLANNER", "STATUS"),
                  # (08/10) o CONTATO inteiro, quebrando linha se preciso
                  "quebra": ("ENDEREÇO", "CONTATO"),
                  "destaque": ("FALTA",), "contagem": "clientes",
                  "grupos": [("CLIENTE", ["CÓD.", "CLIENTE", "UF", "CIDADE",
                                          "ENDEREÇO", "Nº", "SEGMENTO",
                                          "VENDEDOR PLANNER", "STATUS",
                                          "CURVA"]),
                             ("CRÉDITO E COMPRA R$", ["DIAS S/ COMPRA",
                                                      "LIMITE DISP.",
                                                      "EM ATRASO"]),
                             ("META DO MÊS R$", ["META", "REALIZADO",
                                                 "FALTA"]),
                             ("CONTATO", ["TELEFONE", "CONTATO"])]}
    # (08/10) PDF: so o vendedor do Planner (como VENDEDOR); sem supervisor,
    # sem o Protheus, sem FAT. 6M e sem ULTIMO PRODUTO; FALTA vira GAP.
    # O CONTATO ja traz o telefone. Na tela e no Excel continua tudo.
    fora_pdf = ("TELEFONE", "SUPERVISOR PLANNER", "VENDEDOR PROTHEUS",
                "SUPERVISOR PROTHEUS", "FAT. 6M", "ÚLTIMO PRODUTO")
    for c_ in t_c["colunas"]:
        if c_["nome"] in fora_pdf:
            c_["pdf_oculta"] = True
    curto_c = {"DIAS S/ COMPRA": "DIAS S/ COMPRA", "LIMITE DISP.": "LIMITE",
               "EM ATRASO": "ATRASO", "REALIZADO": "REAL", "FALTA": "GAP",
               "VENDEDOR PLANNER": "VENDEDOR"}
    for c_ in t_c["colunas"]:
        c_["pdf_nome"] = curto_c.get(c_["nome"], c_["nome"])
    if clientes and all(c["segmento"] == "(SEM SEGMENTO)" for c in clientes):
        r["avisos"].append(
            "A BASE_CLIENTE lida não tem o SEGMENTO preenchido: gere a "
            "BASE_CLIENTE de novo no BAP Tools (o segmento sai dela).")
    return r


# =========================================================================
# POS-VENDA E LOGISTICA
# =========================================================================
def _inicio_controle():
    """Data em que o ACOMPANHAMENTO_POS_VENDA comecou: o que e de antes
    conta como CONCLUIDO (entregue / devolucao encerrada)."""
    try:
        import pos_venda                                 # noqa: PLC0415
        return pos_venda.INICIO_PADRAO
    except Exception:                                    # noqa: BLE001
        return date(2026, 10, 1)


CONCLUIDA = "CONCLUÍDA"


def situacao_da_entrega(etapa, atual=None):
    """(30/10, Alexandre) A SITUACAO da entrega no Farol de Entregas:
    PENDENTE, CONCLUIDA (entregue) ou CANCELADA, pela ETAPA. O prazo (NO
    PRAZO / ATRASADA / ENTREGUE COM ATRASO) vai para a coluna PRAZO."""
    e = texto(etapa).upper()
    if atual == CONCLUIDA or e == "ENTREGUE":
        return CONCLUIDA
    if e == "CANCELADA":
        return "CANCELADA"
    return "PENDENTE"


def _prever_pelo_pedido(ctx, pv):
    """(22/10, Alexandre) a DT. PREVISTA da entrega conta da DATA DO
    PEDIDO, sempre a partir do dia seguinte ao pedido (o WORKDAY: 1 dia
    util depois do pedido = dia 1). O prazo (3 capital/local, 5 interior/
    frete, ou o SLA cadastrado por cidade/filial) e o mesmo que o pos-venda
    usou na nota; muda so o ponto de partida. A SITUACAO (NO PRAZO /
    ATRASADA / ENTREGUE COM ATRASO) e os indicadores sao refeitos com a
    previsao nova. Nota sem pedido na TABELA_BAP fica pela data da NF."""
    ents = (pv or {}).get("entregas") or []
    if not ents:
        return
    # (30/10, Alexandre) etapa antiga aparece como a nova (FATURADA ->
    # AGUARDANDO COLETA, EXPEDIDA -> EM TRANSITO); o arquivo nao muda
    try:
        import pos_venda as _pvm                        # noqa: PLC0415
        for e in ents:
            et_ = texto(e.get("etapa")).upper()
            if et_ in _pvm.ETAPA_ANTIGA:
                e["etapa"] = _pvm.ETAPA_ANTIGA[et_]
    except Exception:                                   # noqa: BLE001
        pass
    try:
        ped = _pedido_da_nf(ctx)
    except Exception:                                   # noqa: BLE001
        return
    hoje = ctx.hoje
    for e in ents:
        dnf = bd.data_de(e.get("data_nf"))
        # (a 2a passada no mesmo bloco parte da previsao da NF guardada)
        prev = bd.data_de(e.get("prevista_nf") or e.get("prevista"))
        dtp, _n = ped.get((texto(e.get("filial")),
                           texto(e.get("nf")).lstrip("0")), (None, ""))
        dtp = bd.data_de(dtp)
        # (30/10, Alexandre) a previsao AJUSTADA na tela (Editar) manda
        manual = bd.data_de(e.get("prevista_manual"))
        nova = None
        if dnf and prev and dtp:
            dias = bd.dias_uteis_entre(dnf, prev, ctx.fer) or 0
            if dias > 0:
                nova = bd.somar_uteis(dtp, dias, ctx.fer)
        if manual:
            nova = manual
        if not nova:
            continue
        if prev:
            e["prevista_nf"] = prev
        e["prevista"] = nova
        etapa = texto(e.get("etapa")).upper()
        entregue = bd.data_de(e.get("entregue_em"))
        if etapa == "CANCELADA":
            e["situacao"] = "—"
        elif entregue:
            e["situacao"] = ("NO PRAZO" if entregue <= nova
                             else "ENTREGUE COM ATRASO")
        else:
            e["situacao"] = "ATRASADA" if hoje > nova else "NO PRAZO"
    try:
        import pos_venda as _pv                         # noqa: PLC0415
        pv["indicadores"] = _pv.indicadores(
            ents, pv.get("devolucoes") or [], pv.get("garantias") or [], hoje)
    except Exception:                                   # noqa: BLE001
        pass


def _pedido_da_nf(ctx):
    """(filial, nf sem zeros) -> (data do pedido, numero do pedido)."""
    saida = {}
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND" and it["nf"]:
            k = (it["filial"], it["nf"].lstrip("0"))
            if k not in saida or (it["dt_pedido"] and not saida[k][0]):
                saida[k] = (it["dt_pedido"], it["pedido"])
    return saida


def _frete(transp, vlr_nf, e_frete, cadastro, real=None, uf=None,
           cidade=None):
    """VLR FRETE: so nota de FRETE; o FRETE REAL quando a assistente
    informou (16/10), senao o % da transportadora (ou o padrao). (30/10)
    Com a UF/cidade da nota: o % da cidade cadastrado na transportadora."""
    import transportadoras as tr                         # noqa: PLC0415
    if not e_frete or not vlr_nf:
        return None
    if real is not None:
        return real
    # (23/10) com o FRETE MINIMO da transportadora (BAP Analista › Entrega)
    return tr.frete_estimado(cadastro, transp, vlr_nf, uf, cidade)


# (16/10, Alexandre) SALDO DO FRETE: o frete "cheio" de uma nota de FRETE
# e 5% do valor dela (o % padrao do BAP Analista › Transportadoras). O
# frete REAL (o que a transportadora cobrou, informado no Farol de
# Entregas) abaixo disso sobra e vira SALDO; acima, desconta do saldo.
# Sem frete real informado: nao mexe no saldo.
def pct_frete_cheio(ctx=None, cadastro=None) -> float:
    import transportadoras as tr                         # noqa: PLC0415
    try:
        cad = cadastro if cadastro is not None else tr.carregar(ctx.raiz)
        return float(cad.get("pct_padrao") or tr.PCT_PADRAO)
    except Exception:                                    # noqa: BLE001
        return float(tr.PCT_PADRAO)


def frete_real_de(e):
    """O FRETE REAL R$ informado na entrega (None = nao informado)."""
    v = (e or {}).get("frete_real")
    if v in (None, ""):
        return None
    try:
        import pos_venda as pv                           # noqa: PLC0415
        return pv.valor_digitado(v)
    except (ValueError, ImportError):
        return None


def saldo_do_frete(vlr_nf, real, pct_cheio, e_frete=True):
    """(cheio, saldo): cheio = pct_cheio% da nota; saldo = cheio - real
    (None quando nao ha frete real ou a nota nao e de frete)."""
    if not e_frete or not vlr_nf:
        return None, None
    cheio = vlr_nf * pct_cheio / 100.0
    return cheio, (None if real is None else cheio - real)


def saldos_de_frete(ctx) -> dict:
    """{(filial, nf sem zeros): {"vlr", "cheio", "real", "saldo"}} das
    notas de FRETE com o frete real informado (cache no ctx)."""
    if not hasattr(ctx, "_saldos_frete"):
        saida = {}
        try:
            ents = ctx.posvenda.get("entregas", []) or []
        except Exception:                               # noqa: BLE001
            ents = []
        pct = pct_frete_cheio(ctx) if ents else 0.0
        for e in ents:
            real = frete_real_de(e)
            if real is None or texto(e.get("etapa")).upper() == "CANCELADA":
                continue
            if not bd.e_frete(e.get("cidade")):
                continue
            vlr = bd.numero(e.get("valor"))
            cheio, sd = saldo_do_frete(vlr, real, pct)
            if sd is None:
                continue
            k = (texto(e.get("filial")), texto(e.get("nf")).lstrip("0"))
            saida[k] = {"vlr": vlr, "cheio": cheio, "real": real,
                        "saldo": sd}
        ctx._saldos_frete = saida
    return ctx._saldos_frete


# =========================================================================
# FAROL DE INADIMPLENCIA (pos-venda e logistica)
# =========================================================================
FAIXAS_ATRASO = (("A VENCER", None, 0), ("1–15 DIAS", 1, 15),
                 ("16–30 DIAS", 16, 30), ("31–60 DIAS", 31, 60),
                 ("61–90 DIAS", 61, 90), ("91–180 DIAS", 91, 180),
                 ("+180 DIAS", 181, None))
NOMES_FAIXAS = [f[0] for f in FAIXAS_ATRASO]


def faixa_de_atraso(dias) -> str:
    if dias is None or dias <= 0:
        return "A VENCER"
    for nome, ini, fim in FAIXAS_ATRASO[1:]:
        if dias >= ini and (fim is None or dias <= fim):
            return nome
    return NOMES_FAIXAS[-1]


def _ultimo(vals):
    """A foto mais recente do periodo (as fotos vem em ordem de data)."""
    return vals[-1][0] if vals else 0


def farol_inadimplencia(ctx):
    """
    Farol de Inadimplencia: os titulos em aberto do Protheus (TABELA_BAP ›
    ftTitulos). VENCIDO = vencimento real (E1_VENCREA) antes de hoje; o
    atraso e contado em dias corridos. A evolucao vem das fotos diarias do
    relatorio que a automacao guarda (BKP_RELATORIOS_BAPTOOLS): RECEBIDO e
    o saldo que baixou de uma foto para a outra, RECUPERADO e a parte dele
    que ja estava vencida.
    """
    hoje = ctx.hoje
    r = novo("pl_inadimplencia", POS, "Farol de Inadimplência",
             "Títulos em aberto · vencido = vencimento real antes de hoje",
             "TABELA_BAP › ftTitulos + fotos diárias do BAP Tools")
    dados = ctx.inadimplencia
    fotos = dados.get("fotos") or []
    capa(r, ctx, sorted({f["data"].year for f in fotos}) or None)
    graficos_tempo(r, ctx, "Em atraso (R$, última foto)",
                   [(f["data"], f["atraso"]) for f in fotos], "moeda",
                   VERMELHO, _ultimo)
    titulos = dados.get("titulos") or []
    if not titulos:
        r["avisos"].append("Sem títulos em aberto na TABELA_BAP (ftTitulos).")
        return r
    cad = ctx.tabela.get("clientes") or {}
    pedidos_abertos = defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VEA":
            pedidos_abertos[it["cliente"]] += it["valor"]

    def quem(cod):
        c = ctx.cliente(cod)
        v_cad = texto(cad.get(cod, {}).get("vend"))
        vend = c.get("vend_nome") or (
            ctx.vendedor(v_cad) if v_cad.strip("0") else "(SEM VENDEDOR)")
        return c, vend, c.get("supervisor") or "(SEM SUPERVISOR)"

    lin_t, tons_t = [], []
    por_cli = {}
    for t in titulos:
        if t["saldo"] <= 0.005:
            continue
        dias = (hoje - t["venc"]).days if t["venc"] else None
        faixa = faixa_de_atraso(dias)
        sit = ("VENCIDO" if dias is not None and dias > 0 else
               "VENCE HOJE" if dias == 0 else "A VENCER")
        c, vend, sup = quem(t["cod"])
        cli = f"{t['cod']}-{t['loja'] or '01'}"
        nome = c.get("fantasia") or c.get("nome") or t["nome"]
        lin_t.append([
            sit, faixa, ctx.filial(t["filial"]), t["num"].lstrip("0"),
            t["parcela"], t["emissao"], t["venc"], dias, cli, nome,
            c.get("cidade", ""), c.get("uf", ""), vend, sup,
            t["cond_desc"] or ctx.cond(t["cond"]), t["valor"], t["saldo"],
            cad.get(t["cod"], {}).get("fone", "")])
        tons_t.append("alerta" if (dias or 0) > 30 else
                      "atencao" if (dias or 0) > 0 else "")
        x = por_cli.setdefault(t["cod"], {
            "loja": t["loja"], "nome": nome, "c": c, "vend": vend, "sup": sup,
            "venc": 0, "n_venc": 0, "a_vencer": 0.0, "atraso": 0.0,
            "maior": 0, "prox": None})
        if sit == "VENCIDO":
            x["atraso"] += t["saldo"]
            x["n_venc"] += 1
            x["maior"] = max(x["maior"], dias)
        else:
            x["a_vencer"] += t["saldo"]
            if t["venc"] and (x["prox"] is None or t["venc"] < x["prox"]):
                x["prox"] = t["venc"]
    ordem = sorted(range(len(lin_t)), key=lambda i: (-(lin_t[i][7] or -9999),
                                                     -lin_t[i][16]))
    lin_t = [lin_t[i] for i in ordem]
    tons_t = [tons_t[i] for i in ordem]
    I_SIT, I_FX, I_DIAS, I_SALDO = 0, 1, 7, 16

    def resumo(ls):
        venc = [l for l in ls if l[I_SIT] == "VENCIDO"]
        aberto = sum(l[I_SALDO] for l in ls)
        atraso = sum(l[I_SALDO] for l in venc)
        return venc, aberto, atraso

    def cartoes(ls):
        venc, aberto, atraso = resumo(ls)
        mais90 = sum(l[I_SALDO] for l in venc if l[I_DIAS] > 90)
        prox7 = [l for l in ls if l[I_SIT] != "VENCIDO" and l[I_DIAS] is not
                 None and -7 <= l[I_DIAS] <= 0]
        medio = (sum(l[I_SALDO] * l[I_DIAS] for l in venc) / atraso
                 if atraso else None)
        return [
            kpi("Em atraso", moeda(atraso), "alerta" if atraso else "ok",
                f"{br(len(venc))} títulos · "
                f"{br(len({l[8] for l in venc}))} clientes"),
            kpi("Inadimplência", p(pct_de(atraso, aberto)),
                "alerta" if (pct_de(atraso, aberto) or 0) > 20 else "atencao",
                f"da carteira em aberto de {moeda(aberto)}"),
            kpi("A vencer em 7 dias", moeda(sum(l[I_SALDO] for l in prox7)),
                "info", f"{br(len(prox7))} títulos"),
            kpi("Acima de 90 dias", moeda(mais90),
                "alerta" if mais90 else "ok", p(pct_de(mais90, atraso))
                + " do atraso" if atraso else ""),
            kpi("Atraso médio", f"{br(medio)} dias" if medio else "—",
                "neutro", "ponderado pelo saldo"),
        ]
    venc0, aberto0, atraso0 = resumo(lin_t)
    r["kpis"] = cartoes(lin_t)
    ano, mes = periodo(ctx)
    no_per = [f for f in fotos if f["data"].year == ano
              and (not mes or f["data"].month == mes)]
    recup = sum(f["recuperado"] or 0 for f in no_per)
    receb = sum(f["recebido"] or 0 for f in no_per)
    r["kpis"].append(kpi(f"Recuperado {no_periodo_txt(ctx)}", moeda(recup),
                         "ok" if recup else "neutro",
                         f"recebido no total {moeda(receb)}"))
    # ---- graficos alem da capa
    por_fx = defaultdict(float)
    for l in lin_t:
        por_fx[l[I_FX]] += l[I_SALDO]
    r["graficos"].append({
        "titulo": "Carteira em aberto por faixa de atraso",
        "rotulos": NOMES_FAIXAS, "formato": "moeda",
        "series": [{"nome": "saldo", "cor": VERMELHO,
                    "valores": [por_fx.get(f, 0) for f in NOMES_FAIXAS]}]})
    por_fil = defaultdict(lambda: [0.0, 0.0])
    for l in lin_t:
        por_fil[l[2]][0 if l[I_SIT] == "VENCIDO" else 1] += l[I_SALDO]
    fils = sorted(por_fil, key=lambda k: -por_fil[k][0])
    r["graficos"].append({
        "titulo": "Por filial: em atraso e a vencer", "rotulos": fils,
        "formato": "moeda",
        "series": [{"nome": "em atraso", "cor": VERMELHO,
                    "valores": [por_fil[k][0] for k in fils]},
                   {"nome": "a vencer", "cor": AZUL,
                    "valores": [por_fil[k][1] for k in fils]}]})
    if no_per:
        r["graficos"].append({
            "titulo": "Recuperado dia a dia · " + (
                rotulo_mes(f"{ano}-{mes:02d}") if mes else str(ano)),
            "rotulos": [f"{f['data']:%d/%m}" for f in no_per],
            "formato": "moeda",
            "series": [{"nome": "recuperado", "cor": VERDE,
                        "valores": [f["recuperado"] or 0 for f in no_per]}]})
    # ---- titulos
    cols_t = [col("SITUAÇÃO", "texto", 90), col("FAIXA", "texto", 95),
              col("FILIAL", "texto", 95), col("NF", "texto", 70),
              col("PARC.", "texto", 45), col("EMISSÃO", "data"),
              col("VENCIMENTO", "data"), col("DIAS ATRASO", "int", 85),
              col("CLIENTE", "texto", 85), col("NOME", "texto", 220),
              col("CIDADE", "texto", 120), col("UF", "texto", 40),
              col("VENDEDOR", "texto", 190), col("SUPERVISOR", "texto", 170),
              col("CONDIÇÃO", "texto", 140), col("VALOR", "moeda"),
              col("SALDO", "moeda"), col("TELEFONE", "texto", 120)]
    r["tabelas"].append(tabela(
        "Títulos", cols_t, lin_t, tons_t,
        # sem padrao na SITUACAO: os cartoes (% de inadimplencia, a vencer)
        # precisam da carteira inteira; os vencidos ja vem primeiro
        filtros=("SITUAÇÃO", "FAIXA", "FILIAL", "VENDEDOR", "SUPERVISOR",
                 "UF"),
        kpis_de=cartoes,
        recortes=[("Acima de 90 dias", lambda l: (l[I_DIAS] or 0) > 90),
                  ("Vence nos próximos 7 dias",
                   lambda l: l[I_DIAS] is not None and -7 <= l[I_DIAS] <= 0),
                  ("Cliente com pedido em aberto",
                   lambda l: pedidos_abertos.get(l[8][:6], 0) > 0)]))
    # ---- por cliente
    lin_c, tons_c = [], []
    for cod, x in por_cli.items():
        c = x["c"]
        lin_c.append([
            "INADIMPLENTE" if x["atraso"] > 0 else "EM DIA",
            faixa_de_atraso(x["maior"]) if x["atraso"] > 0 else "A VENCER",
            f"{cod}-{x['loja'] or '01'}", x["nome"], c.get("cidade", ""),
            c.get("uf", ""), x["vend"], x["sup"], x["n_venc"], x["atraso"],
            x["maior"] or None, x["a_vencer"], x["prox"],
            cad.get(cod, {}).get("limite", 0.0),
            pedidos_abertos.get(cod, 0.0), c.get("ultima_compra"),
            cad.get(cod, {}).get("fone", "")])
        tons_c.append("alerta" if x["maior"] > 30 else
                      "atencao" if x["atraso"] > 0 else "")
    ordem = sorted(range(len(lin_c)), key=lambda i: -lin_c[i][9])
    lin_c = [lin_c[i] for i in ordem]
    tons_c = [tons_c[i] for i in ordem]

    def cartoes_cli(ls):
        inad = [l for l in ls if l[0] == "INADIMPLENTE"]
        atraso = sum(l[9] for l in inad)
        ped = [l for l in inad if l[14] > 0]
        return [
            kpi("Clientes inadimplentes", br(len(inad)), "alerta" if inad
                else "ok", f"de {br(len(ls))} com título em aberto"
                if len(ls) > len(inad) else ""),
            kpi("Em atraso", moeda(atraso), "alerta" if atraso else "ok"),
            kpi("Inadimplente com pedido aberto", br(len(ped)),
                "atencao" if ped else "ok",
                moeda(sum(l[14] for l in ped)) if ped else ""),
            kpi("Maior devedor", moeda(max((l[9] for l in inad), default=0)),
                "neutro", inad[0][3][:28] if inad else ""),
        ]
    r["tabelas"].append(tabela(
        "Por cliente",
        [col("SITUAÇÃO", "texto", 100), col("FAIXA", "texto", 95),
         col("CLIENTE", "texto", 85), col("NOME", "texto", 220),
         col("CIDADE", "texto", 120), col("UF", "texto", 40),
         col("VENDEDOR", "texto", 190), col("SUPERVISOR", "texto", 170),
         col("TÍTULOS VENCIDOS", "int", 110), col("EM ATRASO", "moeda"),
         col("MAIOR ATRASO", "int", 95), col("A VENCER", "moeda"),
         col("PRÓX. VENCIMENTO", "data", 110), col("LIMITE", "moeda"),
         col("PEDIDO EM ABERTO", "moeda", 115),
         col("ÚLTIMA COMPRA", "data", 100), col("TELEFONE", "texto", 120)],
        lin_c, tons_c,
        filtros=({"coluna": "SITUAÇÃO", "padrao": "INADIMPLENTE"}, "FAIXA",
                 "VENDEDOR", "SUPERVISOR", "UF"),
        kpis_de=cartoes_cli,
        recortes=[("Com pedido em aberto", lambda l: l[14] > 0),
                  ("Top 20 (maior atraso em R$)",
                   {"top": 20, "coluna": 9})]))
    # ---- aging por vendedor, supervisor, filial e UF
    cols_a = [col("CARTEIRA ABERTA", "moeda", 115)] + [
        col(f, "moeda", 95) for f in NOMES_FAIXAS] + [
        col("EM ATRASO", "moeda"), col("% INADIMPL.", "pct", 90),
        col("CLIENTES INADIMPL.", "int", 120)]

    def aging(ls):
        fx = defaultdict(float)
        for l in ls:
            fx[l[I_FX]] += l[I_SALDO]
        aberto = sum(fx.values())
        atraso = aberto - fx.get("A VENCER", 0)
        return ([aberto] + [fx.get(f, 0) for f in NOMES_FAIXAS]
                + [atraso, pct_de(atraso, aberto),
                   len({l[8][:6] for l in ls if l[I_SIT] == "VENCIDO"})])
    for titulo, ix, nome_col, larg in (
            ("Por vendedor", 12, "VENDEDOR", 220),
            ("Por supervisor", 13, "SUPERVISOR", 200),
            ("Por filial", 2, "FILIAL", 140), ("Por UF", 11, "UF", 60)):
        g = defaultdict(list)
        for l in lin_t:
            # (10/11) Por UF = a filial do titulo (a da nota que o gerou)
            k_ = (uf_do_nome_da_filial(l[2]) or l[ix]) if nome_col == "UF" \
                else l[ix]
            g[k_ or "(vazio)"].append(l)
        ls = sorted(([k] + aging(v) for k, v in g.items()),
                    key=lambda x: -x[-3])
        r["tabelas"].append(tabela(
            titulo, [col(nome_col, "texto", larg)] + cols_a, ls,
            ["alerta" if (l[-2] or 0) > 50 else "" for l in ls],
            total=["TOTAL"] + aging(lin_t)))
    # ---- as fotos (evolucao)
    lin_f = [[f["data"], f["aberto"], f["a_vencer"], f["atraso"],
              pct_de(f["atraso"], f["aberto"]), f["clientes"], f["titulos"],
              f["recebido"], f["recuperado"]] for f in reversed(fotos)]
    r["tabelas"].append(tabela(
        "Dia a dia",
        [col("DATA", "data"), col("CARTEIRA ABERTA", "moeda", 115),
         col("A VENCER", "moeda"), col("EM ATRASO", "moeda"),
         col("% INADIMPL.", "pct", 90), col("CLIENTES INADIMPL.", "int", 120),
         col("TÍTULOS VENCIDOS", "int", 110), col("RECEBIDO", "moeda"),
         col("RECUPERADO", "moeda")], lin_f))
    if not fotos:
        r["avisos"].append("Sem fotos diárias dos títulos em "
                           "BKP_RELATORIOS_BAPTOOLS: a evolução fica vazia.")
    return r


# =========================================================================
# (14/10) FAROL DE NCC - CREDITOS A COMPENSAR (Pos-venda, Estefanie)
# =========================================================================
# A NCC (nota de credito ao cliente) e saldo do CLIENTE na empresa: tem de
# ser compensada (abatida num titulo em aberto dele ou num pedido) ou
# devolvida. Fonte: o relatorio "NCC Pendentes" do BAP Tools, que a
# automacao grava na aba ftNCC da TABELA_BAP (E1_FILIAL, E1_PREFIXO,
# E1_NUM, E1_PARCELA, E1_TIPO, E1_CLIENTE, E1_LOJA, E1_NOMCLI, E1_EMISSAO,
# E1_VENCTO, E1_VENCREA, E1_VALOR, E1_SALDO). A IDADE conta da emissao.
FAIXAS_NCC = (("0-30 DIAS", 0, 30), ("31-90 DIAS", 31, 90),
              ("91-180 DIAS", 91, 180), ("+180 DIAS", 181, None))
# o que fazer com o credito (a ordem e a prioridade)
NCC_TITULO, NCC_PEDIDO, NCC_COMPRA, NCC_CONTATO = (
    "NO TÍTULO", "NO PEDIDO", "PRÓX. COMPRA", "CONTATAR")
NOMES_FAIXAS_NCC = [f[0] for f in FAIXAS_NCC]
# (20/10, Alexandre) o A COMPENSAR e editavel: as sugestoes acima mais os
# status do pos-venda (ncc_controle.py); DT. ULT. MOV. editavel e o SLA da
# NCC (3 dias uteis da ultima movimentacao; FINALIZADO e CANCELADO saem)
NCC_SUGESTOES = (NCC_TITULO, NCC_PEDIDO, NCC_COMPRA, NCC_CONTATO)


def faixa_ncc(dias) -> str:
    for nome, ini, fim in FAIXAS_NCC:
        if (dias or 0) >= ini and (fim is None or (dias or 0) <= fim):
            return nome
    return NOMES_FAIXAS_NCC[-1]


def ler_ncc(ctx) -> list:
    """As NCC com saldo (ftNCC da TABELA_BAP), uma por titulo."""
    if hasattr(ctx, "_ncc"):
        return ctx._ncc
    linhas = _ler_aba_da_tabela(ctx, "ftNCC")
    saida = []
    if linhas:
        cab = [texto(c).upper() for c in linhas[0]]

        def g(r, n_):
            i = cab.index(n_) if n_ in cab else None
            return r[i] if i is not None and i < len(r) else None
        for r_ in linhas[1:]:
            if not r_ or not texto(g(r_, "E1_CLIENTE")):
                continue
            saldo = bd.numero(g(r_, "E1_SALDO"))
            if saldo <= 0.005:
                continue
            nome = texto(g(r_, "E1_NOMCLI"))
            if bd._interno(nome):                       # noqa: SLF001
                continue
            saida.append({
                "filial": texto(g(r_, "E1_FILIAL")),
                "prefixo": texto(g(r_, "E1_PREFIXO")),
                "num": texto(g(r_, "E1_NUM")),
                "parcela": texto(g(r_, "E1_PARCELA")),
                "cod": bd.cod6(g(r_, "E1_CLIENTE")),
                "loja": texto(g(r_, "E1_LOJA")).zfill(2),
                "nome": nome,
                "emissao": bd.data_de(g(r_, "E1_EMISSAO")),
                "valor": bd.numero(g(r_, "E1_VALOR")), "saldo": saldo})
    ctx._ncc = saida
    return saida


def farol_ncc(ctx):
    """
    Farol de NCC: os creditos que os clientes tem na empresa (notas de
    credito pendentes). COMO COMPENSAR, na ordem: o cliente tem TITULO EM
    ABERTO (abate nele, ftTitulos) > tem PEDIDO EM ABERTO (abate no
    pedido) > comprou nos ultimos 90 dias (abate na proxima compra) >
    sem compra ha mais de 90 dias (contatar: devolver ou reembolsar).
    """
    hoje = ctx.hoje
    r = novo("pl_ncc", POS, "Farol de NCC",
             "Créditos dos clientes a compensar",
             "TABELA_BAP › ftNCC (BAP Tools › NCC Pendentes) + ftTitulos")
    nccs = ler_ncc(ctx)
    capa(r, ctx, sorted({n["emissao"].year for n in nccs if n["emissao"]})
         or None)
    graficos_tempo(r, ctx, "NCC emitidas com saldo (R$)",
                   [(n["emissao"], n["saldo"]) for n in nccs
                    if n["emissao"]], "moeda", AZUL)
    if not nccs:
        r["avisos"].append("Sem NCC pendente na TABELA_BAP (aba ftNCC - "
                           "vem do BAP Tools › NCC Pendentes).")
    titulos_cli = defaultdict(float)
    try:
        for t in ctx.inadimplencia.get("titulos") or []:
            if t["saldo"] > 0.005 and texto(t.get("tipo")).upper() != "NCC":
                titulos_cli[t["cod"]] += t["saldo"]
    except Exception:                                   # noqa: BLE001
        pass
    pedidos_cli = defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VEA":
            pedidos_cli[it["cliente"]] += it["valor"]

    def como(cod, ult):
        if titulos_cli.get(cod, 0) > 0.005:
            return NCC_TITULO
        if pedidos_cli.get(cod, 0) > 0.005:
            return NCC_PEDIDO
        if ult and (hoje - ult).days <= 90:
            return NCC_COMPRA
        return NCC_CONTATO
    import ncc_controle as nc                           # noqa: PLC0415
    try:
        ctrl = nc.ler(ctx.raiz)
    except Exception:                                   # noqa: BLE001
        ctrl = {}
    opcoes_st = list(NCC_SUGESTOES) + list(nc.STATUS_NOVOS)
    lin, tons, orig = [], [], {}
    for n in nccs:
        c = ctx.cliente(n["cod"])
        dias = (hoje - n["emissao"]).days if n["emissao"] else None
        ult = c.get("ultima_compra")
        vend = c.get("vend_nome") or "(SEM VENDEDOR)"
        k_nc = nc.chave(n["filial"], n["prefixo"], n["num"], n["parcela"])
        ed_ = ctrl.get(k_nc) or {}
        status = ed_.get("status") or como(n["cod"], ult)
        dt_mov = ed_.get("dt_mov")
        du_, _prz, sit_sla = nc.sla(
            status, dt_mov, n["emissao"], hoje, _uteis_ate_ontem(ctx),
            ctx.mais_uteis)
        orig[k_nc] = (status, dt_mov)
        lin.append([
            status, sit_sla, dt_mov, du_,
            faixa_ncc(dias), ctx.filial(n["filial"]),
            n["num"].lstrip("0"), n["parcela"], n["emissao"], dias,
            f"{n['cod']}-{n['loja']}", c.get("fantasia") or c.get("nome")
            or n["nome"], c.get("cidade", ""), c.get("uf", ""), vend,
            c.get("supervisor") or "(SEM SUPERVISOR)", n["valor"],
            n["valor"] - n["saldo"], n["saldo"],
            titulos_cli.get(n["cod"], 0.0) or None,
            pedidos_cli.get(n["cod"], 0.0) or None, ult,
            ctx.tabela.get("clientes", {}).get(n["cod"], {}).get("fone", ""),
            k_nc])
        tons.append("alerta" if sit_sla == nc.SLA_ATRASADO else "")
    I_COMO, I_SLA, I_MOV, I_DU, I_FX, I_DIAS, I_CLI, I_SALDO = (
        0, 1, 2, 3, 4, 9, 10, 18)
    I_ABAT = 17
    # encerradas (FINALIZADO / CANCELADO) no fim; o resto pelo saldo
    ordem = sorted(range(len(lin)), key=lambda i: (
        lin[i][I_SLA] == nc.SLA_ENCERRADO, -lin[i][I_SALDO]))
    lin, tons = [lin[i] for i in ordem], [tons[i] for i in ordem]

    def cartoes(ls_todas):
        # (20/10) as encerradas (FINALIZADO / CANCELADO) saem dos cartoes
        ls = [l for l in ls_todas if l[I_SLA] != nc.SLA_ENCERRADO]
        atr = [l for l in ls if l[I_SLA] == nc.SLA_ATRASADO]
        saldo = sum(l[I_SALDO] for l in ls)
        clis = {l[I_CLI] for l in ls}
        ja = [l for l in ls if l[I_COMO] in (NCC_TITULO,
                                             NCC_PEDIDO)]
        mais90 = [l for l in ls if (l[I_DIAS] or 0) > 90]
        contatar = [l for l in ls if l[I_COMO] == NCC_CONTATO]
        parc = [l for l in ls if l[I_ABAT] > 0.005]
        idade = (sum(l[I_SALDO] * (l[I_DIAS] or 0) for l in ls) / saldo
                 if saldo else None)
        return [
            kpi("Saldo a compensar", moeda(saldo), "atencao" if saldo
                else "ok", f"{br(len(ls))} NCC · {br(len(clis))} clientes"),
            kpi("Compensar já", moeda(sum(l[I_SALDO] for l in ja)),
                "info" if ja else "ok",
                f"{br(len({l[I_CLI] for l in ja}))} clientes · título ou "
                "pedido aberto"),
            kpi("Acima de 90 dias", moeda(sum(l[I_SALDO] for l in mais90)),
                "alerta" if mais90 else "ok", f"{br(len(mais90))} NCC"),
            kpi("Contatar cliente", br(len({l[I_CLI] for l in contatar})),
                "atencao" if contatar else "ok",
                moeda(sum(l[I_SALDO] for l in contatar))
                + " · sem compra 90 d" if contatar else ""),
            kpi("Idade média", f"{br(idade)} dias" if idade is not None
                else "—", "neutro", "ponderada pelo saldo"),
            kpi("Parcialmente compensadas", br(len(parc)), "neutro",
                moeda(sum(l[I_ABAT] for l in parc)) + " já abatidos"
                if parc else ""),
            kpi(f"SLA atrasado ({nc.SLA_NCC} d.u.)", br(len(atr)),
                "alerta" if atr else "ok",
                moeda(sum(l[I_SALDO] for l in atr)) + " · sem movimentação"
                if atr else "todas no prazo"),
        ]
    r["kpis"] = cartoes(lin)
    # ---- graficos alem da capa
    por_fx = defaultdict(float)
    por_como = defaultdict(float)
    for l in lin:
        por_fx[l[I_FX]] += l[I_SALDO]
        por_como[l[I_COMO]] += l[I_SALDO]
    r["graficos"].append({
        "titulo": "Saldo por idade da NCC", "rotulos": NOMES_FAIXAS_NCC,
        "formato": "moeda",
        "series": [{"nome": "saldo", "cor": AZUL,
                    "valores": [por_fx.get(f, 0) for f in NOMES_FAIXAS_NCC]}]})
    rot_c = [k for k in opcoes_st if por_como.get(k)] or list(NCC_SUGESTOES)
    r["graficos"].append({
        "titulo": "Como compensar (R$)", "rotulos": rot_c,
        "formato": "moeda",
        "series": [{"nome": "saldo", "cor": VERDE,
                    "valores": [por_como.get(k, 0) for k in rot_c]}]})
    cols = [dict(col("A COMPENSAR", "texto", 185), larg_fixa=185),
            dict(col("SLA NCC", "texto", 92), larg_fixa=92),
            col("DT. ÚLT. MOV.", "data", 90), col("D.U. S/ MOV.", "int", 80),
            col("IDADE", "texto", 90),
            col("FILIAL", "texto", 95), col("NCC", "texto", 80),
            col("PARC.", "texto", 45), col("EMISSÃO", "data"),
            col("DIAS", "int", 55), col("CLIENTE", "texto", 85),
            col("NOME", "texto", 210), col("CIDADE", "texto", 120),
            col("UF", "texto", 40), col("VENDEDOR", "texto", 190),
            col("SUPERVISOR", "texto", 170, oculta=True),
            col("VALOR NCC", "moeda"),
            col("JÁ ABATIDO", "moeda"), col("SALDO", "moeda"),
            col("TÍTULOS EM ABERTO", "moeda", 115),
            col("PEDIDO EM ABERTO", "moeda", 115),
            col("ÚLTIMA COMPRA", "data", 100),
            col("TELEFONE", "texto", 120)]
    datas_mov = datas_para_escolher(hoje)

    def ao_mudar(linha):
        """Refaz o SLA na tela. Mudou o status sem mudar a data: a
        movimentacao e hoje (o mesmo que o ncc_controle grava)."""
        st0, dt0 = orig.get(linha[len(cols)], (None, None))
        if linha[I_COMO] != st0 and linha[I_MOV] == dt0:
            linha[I_MOV] = hoje
        emis = linha[8]                     # a EMISSAO
        linha[I_DU], _p, linha[I_SLA] = nc.sla(
            linha[I_COMO], linha[I_MOV], emis, hoje, _uteis_ate_ontem(ctx),
            ctx.mais_uteis)
    r["tabelas"].append(tabela(
        "NCC pendentes", cols, lin, tons,
        filtros=("A COMPENSAR", "SLA NCC", "IDADE", "FILIAL", "VENDEDOR",
                 "SUPERVISOR", "UF"),
        kpis_de=cartoes,
        recortes=[("SLA atrasado", lambda l: l[I_SLA] == nc.SLA_ATRASADO),
                  ("Compensar já", lambda l: l[I_COMO] in (
                       NCC_TITULO, NCC_PEDIDO)),
                  ("Acima de 90 dias", lambda l: (l[I_DIAS] or 0) > 90),
                  ("Parcialmente compensadas",
                   lambda l: l[I_ABAT] > 0.005),
                  ("Em aberto (sem finalizadas e canceladas)",
                   lambda l: l[I_SLA] != nc.SLA_ENCERRADO)],
        edicao={"arquivo": "RELATORIOS/_NCC", "aba": "", "modulo": "ncc",
                "chave": len(cols), "ao_mudar": ao_mudar,
                "campos": [{"campo": "status", "rotulo": "A COMPENSAR",
                            "opcoes": opcoes_st, "col": I_COMO,
                            "data": False},
                           {"campo": "dt_mov", "rotulo": "DT. ÚLT. MOV.",
                            "opcoes": datas_mov, "col": I_MOV,
                            "data": True}]}))
    # ---- por cliente (o credito somado)
    g = {}
    for l in lin:
        x = g.setdefault(l[I_CLI], {"l": l, "n": 0, "saldo": 0.0,
                                    "dias": 0})
        x["n"] += 1
        x["saldo"] += l[I_SALDO]
        x["dias"] = max(x["dias"], l[I_DIAS] or 0)
    lin_c = []
    for cli, x in g.items():
        l = x["l"]
        lin_c.append([l[I_COMO], faixa_ncc(x["dias"]), cli, l[11], l[12],
                      l[13], l[14], l[15], x["n"], x["saldo"], x["dias"],
                      l[19], l[20], l[21], l[22]])
    lin_c.sort(key=lambda l: -l[9])
    r["tabelas"].append(tabela(
        "Por cliente",
        [col("A COMPENSAR", "texto", 150), col("IDADE", "texto", 90),
         col("CLIENTE", "texto", 85), col("NOME", "texto", 210),
         col("CIDADE", "texto", 120), col("UF", "texto", 40),
         col("VENDEDOR", "texto", 190),
         col("SUPERVISOR", "texto", 170, oculta=True),
         col("NCC", "int", 50), col("SALDO", "moeda"),
         col("NCC MAIS ANTIGA (DIAS)", "int", 140),
         col("TÍTULOS EM ABERTO", "moeda", 115),
         col("PEDIDO EM ABERTO", "moeda", 115),
         col("ÚLTIMA COMPRA", "data", 100), col("TELEFONE", "texto", 120)],
        lin_c, ["alerta" if l[10] > 180 else "atencao" if l[10] > 90
                else "" for l in lin_c],
        filtros=("A COMPENSAR", "IDADE", "VENDEDOR", "SUPERVISOR", "UF"),
        total=["TOTAL", "", "", "", "", "", "", "",
               sum(l[8] for l in lin_c), sum(l[9] for l in lin_c), None,
               None, None, None, ""]))
    # ---- por filial, vendedor e supervisor (idade do saldo)
    cols_a = [col("NCC", "int", 50), col("CLIENTES", "int", 70)] + [
        col(f, "moeda", 105) for f in NOMES_FAIXAS_NCC] + [
        col("SALDO", "moeda"), col("COMPENSAR JÁ", "moeda", 110)]

    def idade(ls):
        fx = defaultdict(float)
        for l in ls:
            fx[l[I_FX]] += l[I_SALDO]
        return ([len(ls), len({l[I_CLI] for l in ls})]
                + [fx.get(f, 0) for f in NOMES_FAIXAS_NCC]
                + [sum(fx.values()),
                   sum(l[I_SALDO] for l in ls if l[I_COMO] in (
                       NCC_TITULO, NCC_PEDIDO))])
    for titulo, ix, nome_col, larg in (
            ("Por filial", 5, "FILIAL", 140),
            ("Por vendedor", 14, "VENDEDOR", 220),
            ("Por supervisor", 15, "SUPERVISOR", 200)):
        gg = defaultdict(list)
        for l in lin:
            gg[l[ix] or "(vazio)"].append(l)
        ls = sorted(([k] + idade(v) for k, v in gg.items()),
                    key=lambda x: -x[-2])
        r["tabelas"].append(tabela(
            titulo, [col(nome_col, "texto", larg)] + cols_a, ls,
            total=["TOTAL"] + idade(lin)))
    return r


def ctx_sla_txt(ctx) -> str:
    """O subtitulo do SLA (o cadastrado no BAP Analista › Entrega)."""
    return ctx.texto_sla()


def entregas(ctx):
    import transportadoras as tr                         # noqa: PLC0415
    pv = ctx.posvenda
    r = novo("pl_entregas", POS, "Farol de Entregas",
             ctx_sla_txt(ctx),
             "ACOMPANHAMENTO_POS_VENDA › ENTREGAS")
    r["editar"] = "RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx"
    if not pv.get("existe"):
        r["avisos"].append("Acompanhamento do pós-venda ainda não gerado.")
        return r
    hoje = ctx.hoje
    capa(r, ctx, anos_dos_dados(ctx))
    notas = {}
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND" and it["dt_nf"]:
            notas[(it["filial"], it["nf"])] = (it["dt_nf"], 1)
    graficos_tempo(r, ctx, "Notas para entregar", list(notas.values()),
                   "num", VERDE, "conta")
    cad = tr.carregar(ctx.raiz)
    pct_cheio = pct_frete_cheio(cadastro=cad)
    ped = _pedido_da_nf(ctx)
    ents = pv["entregas"]
    linhas, tons = [], []
    for e in sorted(ents, key=lambda e: (e.get("situacao") != "ATRASADA",
                                         e.get("data_nf") or date.min)):
        sit = e.get("situacao") or ""
        dt_ped, _n = ped.get((texto(e.get("filial")),
                              texto(e.get("nf")).lstrip("0")), (None, ""))
        entregue = bd.data_de(e.get("entregue_em"))
        sla = ctx.corridos(dt_ped, entregue or hoje) if dt_ped else None
        frete = bd.e_frete(e.get("cidade"))
        vlr = bd.numero(e.get("valor"))
        transp = texto(e.get("transportadora"))
        real = frete_real_de(e) if frete else None
        cheio, sd_fr = saldo_do_frete(vlr, real, pct_cheio, frete)
        linhas.append([rotulo_mes(mes_de(bd.data_de(e.get("data_nf")))), sit,
                       texto(e.get("etapa")), texto(e.get("nf")).lstrip("0"),
                       dt_ped,
                       e.get("data_nf"), e.get("prevista"), sla,
                       texto(e.get("cliente")), texto(e.get("cidade")),
                       texto(e.get("uf")), "FRETE" if frete else "LOCAL",
                       vlr, _frete(transp, vlr, frete, cad, real,
                                   texto(e.get("uf")),
                                   texto(e.get("cidade"))), transp,
                       entregue, texto(e.get("responsavel")),
                       texto(e.get("cidade_filial")), cheio, real, sd_fr,
                       texto(e.get("chave"))])
        tons.append("alerta" if sit in ("ATRASADA", "ENTREGUE COM ATRASO")
                    else ("ok" if texto(e.get("etapa")).upper() == "ENTREGUE"
                          else ""))
    # o que ficou para tras (antes do controle) entra como CONCLUIDA
    inicio = _inicio_controle()
    meses12 = set(ultimos_meses(hoje, 12))
    ja = {(texto(e.get("filial")), texto(e.get("nf")).lstrip("0"))
          for e in ents}
    antigas = []
    for (fil, nf, serie), itens in _pedidos(ctx, "VND").items():
        i0 = itens[0]
        dnf = i0["dt_nf"]
        if not dnf or dnf >= inicio or mes_de(dnf) not in meses12 \
                or (fil, nf.lstrip("0")) in ja:
            continue
        cli = ctx.cliente(i0["cliente"])
        frete = bd.e_frete(cli.get("cidade"))
        vlr = sum(i["valor"] for i in itens)
        antigas.append([rotulo_mes(mes_de(dnf)), CONCLUIDA, "ENTREGUE",
                        nf.lstrip("0"), i0["dt_pedido"], dnf, None, None,
                        ctx.nome_cliente(i0["cliente"]), cli.get("cidade", ""),
                        cli.get("uf", ""), "FRETE" if frete else "LOCAL", vlr,
                        _frete("", vlr, frete, cad), "", None, "",
                        ctx.filial(fil),
                        saldo_do_frete(vlr, None, pct_cheio, frete)[0],
                        None, None, ""])
    antigas.sort(key=lambda x: x[5], reverse=True)
    linhas += antigas
    tons += [""] * len(antigas)

    # (22/10, Alexandre) a ORDEM da tela: DT. PED, DT. NF, DT. PREVISTA,
    # DT. REAL, SITUACAO, UF, CIDADE, CLIENTE, VLR NF, VLR FRETE,
    # TRANSPORTADORA, RESPONSAVEL, TBL FRETE (o antigo FRETE 5%), VLR REAL
    # FRETE; depois SLA (pintado pelo prazo), ETAPA (inteira), NF, LOCAL/
    # FRETE e FILIAL [SUPOSICAO: as que ele nao listou vao no fim]. Sem o
    # SALDO FRETE (e do Farol de Saldo). As linhas "velhas" (ordem antiga)
    # seguem para o resumo executivo.
    velhas = linhas

    def tom_sla(o):
        """ok / atencao / alerta do SLA pelo PRAZO (a DT. PREVISTA)."""
        prev, ent_ = bd.data_de(o[6]), bd.data_de(o[15])
        if not prev or o[1] in ("", "—", CONCLUIDA) or \
                texto(o[2]).upper() == "CANCELADA":
            return ""
        if ent_:
            return "ok" if ent_ <= prev else "alerta"
        if hoje > prev:
            return "alerta"
        return "atencao" if (prev - hoje).days <= 1 else "ok"

    # (22/10, 17h) SITUACAO primeiro, o SLA logo depois; LOCAL/FRETE fora
    # da tela (fica oculta: o frete da edicao e o cartao usam)
    # (30/10, Alexandre) SITUACAO = PENDENTE / CONCLUIDA / CANCELADA (pela
    # etapa); o prazo (NO PRAZO / ATRASADA / ENTREGUE COM ATRASO) fica na
    # coluna PRAZO (oculta, com filtro), que os cartoes usam
    def nova(o):
        return [o[0], situacao_da_entrega(o[2], o[1]), o[7], o[4], o[5],
                o[6], o[15], o[10], o[9],
                o[8], o[12], o[13], o[14], o[16], o[18], o[19], o[2], o[3],
                o[17], o[11], tom_sla(o),
                "" if o[1] in (CONCLUIDA, "—") else o[1], o[21]]
    linhas = [nova(o) for o in velhas]
    (E_MES, E_SIT, E_SLA, E_PED, E_NF_D, E_PREV, E_REAL, E_UF, E_CID, E_CLI,
     E_VNF, E_VFR, E_TRP, E_RESP, E_TBL, E_FREAL, E_ETAPA, E_NF, E_FIL,
     E_LF, E_TOM, E_PRAZO) = range(22)

    def cartoes(ls):
        abertas = [l for l in ls
                   if l[E_ETAPA].upper() not in ("ENTREGUE", "CANCELADA")]
        entregues = [l for l in ls if l[E_ETAPA].upper() == "ENTREGUE"]
        com_data = [l for l in ls if l[E_REAL]]
        no_prazo = [l for l in com_data if l[E_PRAZO] == "NO PRAZO"]
        atr = sum(1 for l in ls if l[E_PRAZO] == "ATRASADA")
        slas = [l[E_SLA] for l in com_data if l[E_SLA] is not None]
        sem_t = sum(1 for l in abertas if l[E_LF] == "FRETE"
                    and not l[E_TRP])
        com_real = [l for l in ls if l[E_FREAL] is not None]
        return [
            kpi("Em aberto", br(len(abertas)), "neutro",
                moeda(sum(l[E_VNF] for l in abertas))),
            kpi("Atrasadas", br(atr), "alerta" if atr else "ok"),
            kpi("Entregues", br(len(entregues)), "ok"),
            kpi("No prazo", p(pct_de(len(no_prazo), len(com_data))),
                "ok" if (pct_de(len(no_prazo), len(com_data)) or 100) >= 90
                else "alerta"),
            kpi("SLA médio de entrega",
                f"{br(sum(slas) / len(slas), 1)} dias" if slas else "—",
                "neutro", "do pedido à entrega"),
            kpi("Frete estimado" if not com_real else "Frete",
                moeda(sum(l[E_VFR] or 0 for l in ls)),
                "neutro", (f"{p(pct_de(sum(l[E_VFR] or 0 for l in ls), sum(l[E_VNF] or 0 for l in ls if l[E_VFR])))} sobre as notas"
                           + (f" · {br(sem_t)} s/ transp." if sem_t else ""))),
        ]
    mes_atual = mes_escolhido(ctx)
    no_mes_ = [l for l in linhas if rotulo_no_periodo(ctx, l[E_MES])]
    # (10/10) PENDENCIAS DOS MESES ANTERIORES: o que ficou sem concluir
    # (etapa diferente de ENTREGUE/CANCELADA) de antes do mes escolhido
    ano_e, mes_e = periodo(ctx)
    ini_e = f"{ano_e}-{mes_e:02d}" if mes_e else None
    pares = sorted([(n_, o_) for n_, o_ in zip(linhas, velhas)
                    if ini_e and n_[E_NF_D]
                    and mes_de(bd.data_de(n_[E_NF_D])) < ini_e
                    and n_[E_ETAPA].upper() not in ("ENTREGUE", "CANCELADA")
                    and n_[E_SIT] != CONCLUIDA],
                   key=lambda x: bd.data_de(x[0][E_NF_D]) or date.min)
    pend = [x[0] for x in pares]
    pend_velhas = [x[1] for x in pares]
    tons_pend = ["alerta" if l[E_PRAZO] == "ATRASADA" else "atencao"
                 for l in pend]

    def cartoes_mes(ls, filtro=None):
        # RN-GER-006: as pendencias seguem o filtro de UF de fato (o
        # {coluna: valor} da tela), nunca deduzido das linhas. Sem filtro
        # de UF (ou chamada sem `filtro`) = total da BAP.
        uf = (filtro or {}).get(E_UF)
        pd = pend if uf in (None, "") else [l for l in pend if l[E_UF] == uf]
        return cartoes(list(ls)) + [kpi(
            "Pendências anteriores", br(len(pd)),
            "alerta" if pd else "ok",
            f"{moeda(sum(l[E_VNF] or 0 for l in pd))} · meses anteriores"
            if pd else "nada pendente")]
    r["kpis"] = cartoes_mes(no_mes_)
    etapas = Counter(l[E_ETAPA].upper() or "(vazio)" for l in linhas
                     if rotulo_no_periodo(ctx, l[E_MES]))
    import pos_venda as _pvm                            # noqa: PLC0415
    ordem = list(_pvm.ETAPAS_ENTREGA) + sorted(
        x for x in etapas if x not in _pvm.ETAPAS_ENTREGA)
    r["graficos"].append({"titulo": "Notas por etapa", "rotulos": ordem,
                          "series": [{"nome": "notas", "cor": VERDE,
                                      "valores": [etapas[x] for x in ordem]}],
                          "formato": "num"})
    # o SLA pintado pelo prazo: verde no prazo, amarelo vence hoje/amanha,
    # vermelho passou (selo por linha: a coluna oculta TOM SLA)
    cols = [col("MÊS", "texto", 58, oculta=True),
            col("SITUAÇÃO", "texto", 105),
            dict(col("SLA", "int", 50), chip_tom=E_TOM),
            col("DT. PED", "dia", 64), col("DT. NF", "dia", 64),
            col("DT. PREVISTA", "dia", 78), col("DT. REAL", "dia", 70),
            col("UF", "texto", 36),
            col("CIDADE", "texto", 120), col("CLIENTE", "texto", 210),
            col("VLR NF", "moeda", 88), col("VLR FRETE", "moeda", 80),
            col("TRANSPORTADORA", "texto", 140),
            col("RESPONSÁVEL", "texto", 130),
            col("TBL FRETE", "moeda", 80),
            col("VLR REAL FRETE", "moeda", 96),
            dict(col("ETAPA", "texto", 110), inteira=True),
            col("NF", "texto", 60), col("FILIAL", "texto", 90),
            col("LOCAL/FRETE", "texto", 72, oculta=True),
            col("TOM SLA", "texto", 40, oculta=True),
            col("PRAZO", "texto", 120, oculta=True)]
    _cor_tom = {"ok": VERDE_TXT, "atencao": AMARELO_TXT, "alerta": VERMELHO}
    r["tabelas"].append(tabela(
        "Entregas", cols, linhas, tons,
        filtros=({"coluna": "MÊS", "padrao": mes_atual}, "SITUAÇÃO", "ETAPA",
                 "PRAZO", "FILIAL"),
        kpis_de=cartoes_mes,
        edicao=_entrega_editavel(ctx, len(cols), {
            "etapa": E_ETAPA, "transportadora": E_TRP, "entregue_em": E_REAL,
            "prevista_manual": E_PREV,
            "responsavel": E_RESP, "frete_real": E_FREAL}, cad, uf_col=E_UF,
            cidade_col=E_CID, frete=(E_VNF, E_LF, E_VFR),
            saldo_frete=(E_TBL, None),
            situacao=(E_SIT, E_ETAPA, E_PRAZO))))
    r["tabelas"][-1]["cores_celulas"] = [
        {E_SLA: _cor_tom[l[E_TOM]]} if l[E_TOM] in _cor_tom else {}
        for l in linhas]
    t_ent = r["tabelas"][-1]
    # (10/10) a tabela do mes em cima e, embaixo, as PENDENCIAS DOS MESES
    # ANTERIORES (as mesmas colunas, com o MES aparecendo; duplo clique
    # edita igual). A aba FRETE saiu: o frete esta na propria entrega
    cols_p = [dict(c_, oculta=False) if c_["nome"] == "MÊS" else c_
              for c_ in cols]
    t_ent["juntas"] = [{
        "tabela": tabela("Pendências dos meses anteriores", cols_p, pend,
                         tons_pend),
        "liga": None, "editavel": True,
        "titulo": "Pendências dos meses anteriores",
        "filtro_texto": "Entregas de meses anteriores ainda não concluídas"}]
    t_ent["divisao"] = 0.58
    _painel_entregas_exec(r, ctx, velhas, pend_velhas)
    return r


REGIAO_UF = {**{u: "NORTE" for u in ("AM", "PA", "AP", "RR", "AC", "RO",
                                       "TO")},
             **{u: "NORDESTE" for u in ("MA", "PI", "CE", "RN", "PB", "PE",
                                         "AL", "SE", "BA")},
             **{u: "CENTRO-OESTE" for u in ("MT", "MS", "GO", "DF")},
             **{u: "SUDESTE" for u in ("SP", "RJ", "MG", "ES")},
             **{u: "SUL" for u in ("PR", "SC", "RS")}}


def _painel_entregas_exec(r, ctx, linhas, pend):
    """(10/10) RESUMO GERENCIAL do Farol de Entregas, executivo: QUANTO SE
    GASTA DE FRETE e ONDE - por estado (com o % sobre a nota), por regiao,
    as cidades que mais custam, a transportadora, o frete mes a mes com o
    %, o SLA por estado e as pendencias. Tudo do mes escolhido (o mes a
    mes: os 12 meses ate ele)."""
    import painel_farol as pf                           # noqa: PLC0415
    ano, mes = periodo(ctx)
    mes_ls = [l for l in linhas if rotulo_no_periodo(ctx, l[0])]
    com_fr = [l for l in mes_ls if l[13]]
    frete = sum(l[13] for l in com_fr)
    nf_fr = sum(l[12] or 0 for l in com_fr)
    pct_fr = pct_de(frete, nf_fr)
    # mes anterior, no mesmo criterio
    if mes:
        ant = _meses_antes(f"{ano}-{mes:02d}", 1)[0]
        rot_ant = rotulo_mes(ant)
        fr_ant = sum(l[13] or 0 for l in linhas if l[0] == rot_ant)
    else:
        rot_ant, fr_ant = "", 0.0
    # por UF
    uf = defaultdict(lambda: {"n": 0, "nf": 0.0, "fr": 0.0, "nf_fr": 0.0,
                              "sla": []})
    for l in mes_ls:
        x = uf[l[10] or "?"]
        x["n"] += 1
        x["nf"] += l[12] or 0
        if l[13]:
            x["fr"] += l[13]
            x["nf_fr"] += l[12] or 0
        if l[15] and l[7] is not None:
            x["sla"].append(l[7])
    lin_uf = sorted(([u, REGIAO_UF.get(u, "—"), x["n"], x["nf"], x["fr"],
                      pct_de(x["fr"], x["nf_fr"]),
                      x["fr"] / x["n"] if x["n"] else 0.0]
                     for u, x in uf.items()), key=lambda l: -l[4])
    tot_uf = ["TOTAL", "", sum(l[2] for l in lin_uf),
              sum(l[3] for l in lin_uf), frete, pct_fr,
              frete / len(mes_ls) if mes_ls else 0.0]
    reg = defaultdict(float)
    for l in lin_uf:
        reg[l[1]] += l[4]
    cid = defaultdict(float)
    transp = defaultdict(float)
    for l in com_fr:
        cid[f"{l[9]}/{l[10]}"] += l[13]
        # antes do controle (01/10) a nota nao tem transportadora: entra no
        # padrao, sem acusar falta
        transp[l[14] or ("(sem transportadora)" if len(l) > 21 and l[21]
                         else "PADRÃO (antes do controle)")] += l[13]
    sla_uf = {u: sum(x["sla"]) / len(x["sla"]) for u, x in uf.items()
              if x["sla"]}
    # o frete dos 12 meses ate o escolhido (R$ e o % sobre a nota)
    fim = date(ano, mes or ctx.hoje.month, 1)
    meses = ultimos_meses(fim, 12)
    rots = [rotulo_mes(m_) for m_ in meses]
    fr_m = {r_: [0.0, 0.0] for r_ in rots}
    for l in linhas:
        if l[0] in fr_m and l[13]:
            fr_m[l[0]][0] += l[13]
            fr_m[l[0]][1] += l[12] or 0
    g_mes = {"titulo": "Frete estimado · mês a mês (R$ e % sobre a nota)",
             "rotulos": [r_[:3] for r_ in rots],
             "series": [{"nome": "frete R$", "cor": VERDE,
                         "valores": [fr_m[r_][0] for r_ in rots]}],
             "formato": "moeda", "rotular": True,
             "linha": {"nome": "% s/ nota",
                       "valores": [pct_de(*fr_m[r_]) for r_ in rots]}}
    # O QUE IMPORTA, em frases
    ins = []
    per = rotulo_mes(f"{ano}-{mes:02d}") if mes else f"o ano {ano}"
    if frete:
        var = f"; {rot_ant} fechou em {moeda(fr_ant)}" if fr_ant else ""
        ins.append(("info", f"Frete estimado em {per}: {moeda(frete)} — "
                            f"{p(pct_fr)} sobre {moeda(nf_fr)} em notas com "
                            f"frete ({br(len(com_fr))} notas){var}."))
        if lin_uf:
            caro = max((l for l in lin_uf if l[5] is not None),
                       key=lambda l: l[5], default=None)
            ins.append(("atencao", f"Estado com o maior gasto: {lin_uf[0][0]}"
                                   f" ({moeda(lin_uf[0][4])}, "
                                   f"{p(lin_uf[0][5])} da nota)."))
            pcts_ = {round(l[5], 1) for l in lin_uf if l[5] is not None}
            if caro and caro[0] != lin_uf[0][0] and len(pcts_) > 1:
                ins.append(("atencao", f"Maior % sobre a nota: {caro[0]} "
                                       f"({p(caro[5])})."))
        if cid:
            c1 = max(cid.items(), key=lambda kv: kv[1])
            ins.append(("atencao", f"Cidade que mais custa frete: {c1[0]} "
                                   f"({moeda(c1[1])}, "
                                   f"{p(pct_de(c1[1], frete))} do total)."))
        if reg:
            r1 = max(reg.items(), key=lambda kv: kv[1])
            ins.append(("info", f"Região: {r1[0]} concentra "
                                f"{p(pct_de(r1[1], frete))} do frete."))
        sem_t = transp.get("(sem transportadora)")
        if sem_t:
            ins.append(("alerta", f"{moeda(sem_t)} de frete em notas sem "
                                  f"transportadora informada."))
    else:
        ins.append(("info", f"Sem nota com frete em {per}."))
    atr = sum(1 for l in mes_ls if l[1] == "ATRASADA")
    if atr:
        ins.append(("alerta", f"{br(atr)} entrega(s) atrasada(s) no mês."))
    if pend:
        ins.append(("alerta", f"{br(len(pend))} pendência(s) de meses "
                              f"anteriores ({moeda(sum(l[12] or 0 for l in pend))}"
                              f") — veja a aba Entregas."))
    # a ordem e a do negocio: quanto se gasta primeiro, depois onde
    cols_uf = [col("UF", "texto", 40), col("REGIÃO", "texto", 100),
               col("NOTAS", "int", 55), col("VALOR NF", "moeda", 90),
               col("FRETE R$", "moeda", 85), col("% S/ NOTA", "pct1", 70),
               col("FRETE/NOTA", "moeda", 80)]
    blocos = [
        {"tipo": "insights", "titulo": "O que importa no mês",
         "linhas": ins[:pf.MAX_INSIGHTS], "col": 0, "row": 0, "rowspan": 2},
        {"tipo": "tabela", "titulo": f"Frete por estado · {per}",
         "colunas": cols_uf, "linhas": lin_uf, "total": tot_uf,
         "col": 1, "row": 0, "colspan": 2},
        dict(pf.ranking("Cidades que mais custam frete (R$)",
                        list(cid.items()), "moeda", nomes_curtos=False),
             col=1, row=1),
        (dict(pf.ranking("% do frete sobre a nota, por estado",
                         [(l[0], l[5]) for l in lin_uf if l[5] is not None],
                         "pct", nomes_curtos=False), col=2, row=1)
         if len({round(l[5], 1) for l in lin_uf if l[5] is not None}) > 1
         else dict(pf.ranking("Frete médio por nota, por estado (R$)",
                              [(l[0], l[6]) for l in lin_uf if l[4]],
                              "moeda", nomes_curtos=False), col=2, row=1)),
        {"tipo": "barras", "grafico": g_mes, "col": 0, "row": 2,
         "colspan": 2},
        dict(pf.ranking("Frete por região (R$)", list(reg.items()), "moeda",
                        nomes_curtos=False), col=2, row=2),
        dict(pf.ranking("Frete por transportadora (R$)",
                        list(transp.items()), "moeda", nomes_curtos=False),
             col=0, row=3),
        dict(pf.ranking("SLA médio de entrega por estado (dias corridos)",
                        list(sla_uf.items()), "num1", nomes_curtos=False,
                        menor_primeiro=True), col=1, row=3),
        dict(pf.ranking("Pendências anteriores por cidade",
                        list(Counter(f"{l[9]}/{l[10]}" for l in pend).items()),
                        "num", nomes_curtos=False), col=2, row=3),
    ]
    blocos = [{k: v for k, v in b.items() if not k.startswith("_")}
              for b in blocos if b.get("tipo") != "hbarras" or b["rotulos"]]
    r["painel"] = {"colunas": (1, 1, 1), "altura_min": 4 * 250,
                   "blocos": blocos}
    r["painel_titulo"] = "Resumo gerencial"
    r["insights_painel"] = ins


def _historico_de_compra(ctx):
    """(23/10) Todas as vendas (VND) da TABELA_BAP item a item, da mais
    nova para a mais antiga: cliente, pedido Protheus e Maxima, NF, prazo
    (condicao de pagamento), datas do pedido/NF/entrega, transportadora e
    responsavel (do pos-venda), produto, quantidade e valor. Devolucao nao
    entra [SUPOSICAO]."""
    ents = {}
    try:
        for e in ctx.posvenda.get("entregas", []) or []:
            ents[(texto(e.get("filial")), texto(e.get("nf")).lstrip("0"))] = e
    except Exception:                                   # noqa: BLE001
        pass
    linhas = []
    for it in ctx.tabela["itens"]:
        if it["tipo"] != "VND":
            continue
        cod = it["cliente"]
        cli = ctx.cliente(cod)
        ctab = ctx.tabela["clientes"].get(cod, {})
        nf = texto(it.get("nf")).lstrip("0")
        e = ents.get((texto(it["filial"]), nf)) or {}
        linhas.append([
            cod, ctab.get("nome") or cli.get("nome") or it.get("razao", ""),
            ctab.get("fantasia") or cli.get("fantasia", ""),
            cli.get("cidade", ""), it.get("pedido") or "",
            texto(it.get("maxima")), nf, ctx.cond(it.get("cond")),
            it.get("dt_pedido"), it.get("dt_nf"),
            bd.data_de(e.get("entregue_em")),
            texto(e.get("transportadora")), texto(e.get("responsavel")),
            it["cod"], ctx.produto(it["cod"]), it["qtd"], it["valor"],
            ctx.vendedor(it["vend"]), ctx.filial(it["filial"])])
    linhas.sort(key=lambda l: (-(l[9] or date.min).toordinal(), l[6],
                               l[13]))
    cols = [col("CÓD. CLIENTE", "texto", 70),
            col("RAZÃO SOCIAL", "texto", 220),
            col("FANTASIA", "texto", 160), col("CIDADE", "texto", 110),
            col("PEDIDO", "texto", 62), col("PED. MÁXIMA", "texto", 70),
            col("NF", "texto", 60), col("PRAZO", "texto", 120),
            col("DT. PEDIDO", "dia", 70), col("DT. NF", "dia", 66),
            col("DT. ENTREGA", "dia", 74),
            col("TRANSPORTADORA", "texto", 140),
            col("RESPONSÁVEL", "texto", 130),
            col("CÓD. PRODUTO", "texto", 100),
            col("DESCRIÇÃO", "texto", 240), col("QTD", "num", 50),
            col("VALOR", "moeda", 90), col("VENDEDOR", "texto", 160),
            col("FILIAL", "texto", 80)]

    def cartoes(ls):
        peds = {(l[18], l[4]) for l in ls if l[4]}
        nfs = {(l[18], l[6]) for l in ls if l[6]}
        ult = max((l[9] for l in ls if l[9]), default=None)
        return [kpi("Pedidos", br(len(peds)), "neutro",
                    f"{br(len(nfs))} notas"),
                kpi("Itens", br(len(ls)), "neutro",
                    f"{br(sum(l[15] or 0 for l in ls))} unidades"),
                kpi("Valor comprado", moeda(sum(l[16] or 0 for l in ls)),
                    "neutro"),
                kpi("Última compra", ult.strftime("%d/%m/%Y") if ult
                    else "—", "neutro",
                    f"{br(len({l[0] for l in ls}))} cliente(s)")]

    def total(ls):
        if not ls:
            return None
        return ["TOTAL", f"{br(len(ls))} itens"] + [""] * 13 + [
            sum(l[15] or 0 for l in ls), sum(l[16] or 0 for l in ls),
            "", ""]
    hoje = ctx.hoje
    t_ = tabela("Histórico de compra", cols, linhas, total=total(linhas),
                kpis_de=cartoes,
                recortes=[("Últimos 30 dias", lambda l: l[9] and
                           (hoje - l[9]).days <= 30),
                          ("Últimos 90 dias", lambda l: l[9] and
                           (hoje - l[9]).days <= 90),
                          ("Sem data de entrega", lambda l: not l[10])])
    t_["total_de"] = total
    t_["compacta"] = True
    return t_


# (06/11, Alexandre) o PRAZO da garantia: FECHADA verde quando fechou ate a
# DT. FECHAMENTO, "laranja esverdeado" (verde-oliva) quando fechou depois
CORES_PRAZO_GARANTIA = {
    "ATRASADA": _VERM,
    "NO PRAZO": _VERD,
    "FECHADA NO PRAZO": ("#2F7D32", "#FFFFFF"),
    "FECHADA COM ATRASO": ("#9E9D24", "#FFFFFF")}


def garantias(ctx):
    """
    (14/10) FAROL DE GARANTIAS: cada garantia e um TICKET (garantias.py -
    diario por maquina em RELATORIOS/_GARANTIAS). Duplo clique abre a
    garantia: o detalhe do cliente (endereco, bairro, cidade, vendedor,
    supervisor) e a edicao (status, resultado da analise, retorno do
    cliente, pendencias, cliente, produto, quantidade, contato).
    DT. FECHAMENTO = o prazo (06/11): solicitacao + 15 dias uteis, ou a
    data editada na garantia; SLA ATUAL = dias desde a solicitacao
    (fechada: ate o fechamento, e fica cinza); PRAZO FECHADA verde se
    fechou ate a DT. FECHAMENTO, verde-oliva se fechou depois.
    """
    import garantias as gm                              # noqa: PLC0415
    hoje = ctx.hoje
    fer = getattr(ctx, "fer", set()) or set()
    r = novo("pl_garantias", POS, "Farol de Garantias",
             f"Prazo: DT. FECHAMENTO = {gm.PRAZO_UTEIS} dias úteis da "
             "solicitação (editável na garantia)",
             "RELATORIOS › _GARANTIAS (edição no próprio farol)")
    dados = gm.ler(ctx.raiz)
    capa(r, ctx, sorted({d.year for d in (
        gm.data(g.get("dt_solicitacao")) for g in dados.values()) if d})
        or None)
    graficos_tempo(r, ctx, "Garantias solicitadas",
                   [(gm.data(g.get("dt_solicitacao")), 1)
                    for g in dados.values()
                    if gm.data(g.get("dt_solicitacao"))], "num", AMARELO,
                   "conta")
    linhas, tons = [], []

    def cliente_base(cod):
        """O cadastro do cliente na base, nos campos cli_* da garantia."""
        c = ctx.cliente(texto(cod)) if texto(cod) else {}
        return {"_nome": c.get("nome", ""),
                "cli_fantasia": c.get("fantasia", ""),
                "cli_endereco": " ".join(x for x in (
                    c.get("endereco", ""), c.get("numero", "")) if x),
                "cli_bairro": c.get("bairro", ""),
                "cli_cidade": c.get("cidade", ""), "cli_uf": c.get("uf", ""),
                "cli_telefone": c.get("contato", ""),
                "cli_vendedor": c.get("vend_nome", ""),
                "cli_supervisor": c.get("supervisor", "")}
    for t, g in dados.items():
        st = gm.situacao(g, hoje, fer)
        cod = texto(g.get("cod_cliente"))
        c = ctx.cliente(cod) if cod else {}
        cad = gm.cadastro(g, cliente_base(cod))
        cod_p = texto(g.get("cod_produto"))
        desc = texto(g.get("descricao")) or (ctx.produto(cod_p) if cod_p
                                             else "")
        contato = " · ".join(x for x in (texto(g.get("contato_nome")),
                                         texto(g.get("contato_fone"))) if x)
        linhas.append([
            texto(g.get("status")) or "ABERTO",
            texto(g.get("resultado")) or "PENDENTE", t, st["inicio"],
            st["prevista"], st["sla"],
            "ATRASADA" if st["atrasada"] else (
                "FECHADA" if st["fechada"] else "NO PRAZO"),
            cod, c.get("fantasia") or c.get("nome") or
            texto(g.get("cliente")), cad["cli_cidade"], cod_p, desc,
            bd.numero(g.get("qtd")) or None, contato,
            texto(g.get("pendencias")), texto(g.get("retorno_cliente")),
            cad["cli_vendedor"], cad["cli_supervisor"],
            st["chave_prazo"], st["tom_sla"], st["fim"]])
        tons.append("alerta" if st["atrasada"] else (
            "atencao" if st["tom_sla"] == "atencao" else ""))
    ordem = sorted(range(len(linhas)), key=lambda i: (
        linhas[i][0] in gm.FECHADOS, -(linhas[i][5] or 0)))
    linhas, tons = [linhas[i] for i in ordem], [tons[i] for i in ordem]
    I_ST, I_RES, I_SLA, I_PRAZO, I_CHAVE = 0, 1, 5, 6, 18

    def cartoes(ls):
        abertas = [l for l in ls if l[I_ST] not in gm.FECHADOS]
        atras = [l for l in abertas if l[I_PRAZO] == "ATRASADA"]
        fechadas = [l for l in ls if l[I_ST] == "FINALIZADA"]
        sla_f = [l[I_SLA] for l in fechadas if l[I_SLA] is not None]
        no_pz = sum(1 for l in fechadas if l[I_CHAVE] == "FECHADA NO PRAZO")
        return [
            kpi("Em aberto", br(len(abertas)), "atencao" if abertas else
                "ok", f"{br(sum(1 for l in abertas if l[I_ST] == 'ABERTO'))}"
                f" sem tratativa"),
            kpi("Atrasadas", br(len(atras)), "alerta" if atras else "ok",
                "abertas depois da DT. FECHAMENTO"),
            kpi("Análise pendente", br(sum(1 for l in ls
                                            if l[I_RES] == "PENDENTE")),
                "neutro"),
            kpi("Procedentes", br(sum(1 for l in ls
                                      if l[I_RES] == "PROCEDENTE")), "ok"),
            kpi("Improcedentes", br(sum(1 for l in ls
                                        if l[I_RES] == "IMPROCEDENTE")),
                "neutro"),
            kpi("SLA médio (finalizadas)",
                (f"{br(sum(sla_f) / len(sla_f))} dia"
                 + ("s" if sum(sla_f) / len(sla_f) >= 1.5 else ""))
                if sla_f else "—",
                "neutro", f"{br(len(fechadas))} finalizadas · "
                f"{br(no_pz)} no prazo"),
        ]
    r["kpis"] = cartoes(linhas)
    cols = [col("STATUS", "texto", 105), col("RESULTADO ANÁLISE", "texto", 110),
            col("TICKET", "texto", 60), col("DT. SOLICITAÇÃO", "data", 85),
            # (06/11, Alexandre) DT. PREVISTA virou DT. FECHAMENTO: o
            # prazo, 15 dias uteis da solicitacao ou o editado na garantia
            col("DT. FECHAMENTO", "data", 90),
            # (06/11) o SLA pinta pela LINHA (coluna TOM SLA): aberta no
            # prazo verde, faltando ate 3 dias uteis amarelo, atrasada
            # vermelho; FECHADA para de contar e fica cinza
            dict(col("SLA ATUAL", "int", 70), chip_tom=19, larg_fixa=70),
            # (06/11) FECHADA verde se fechou ate a DT. FECHAMENTO, verde-
            # oliva se fechou depois (a cor vem da SITUACAO DO PRAZO)
            dict(col("PRAZO", "texto", 92), chip=CORES_PRAZO_GARANTIA,
                 chip_chave=18, larg_fixa=92),
            col("CÓD. CLIENTE", "texto", 70),
            col("CLIENTE", "texto", 160), col("CIDADE", "texto", 100),
            col("CÓD. PRODUTO", "texto", 90),
            # (14/10) so o codigo na tela (a descricao fica no filtro/Excel e
            # na janela da garantia); QTD; o CONTATO inteiro, sem cortar
            col("DESCRIÇÃO PRODUTO", "texto", 200, oculta=True),
            col("QTD", "num", 45),
            dict(col("CONTATO CLIENTE", "texto", 210), larg_fixa=max(
                [180] + [len(str(l[13] or "")) * 7 + 20 for l in linhas])),
            col("PENDÊNCIAS", "texto", 200, oculta=True),
            col("RETORNO DO CLIENTE", "texto", 200, oculta=True),
            col("VENDEDOR", "texto", 160, oculta=True),
            col("SUPERVISOR", "texto", 160, oculta=True),
            col("SITUAÇÃO DO PRAZO", "texto", 140, oculta=True),
            col("TOM SLA", "texto", 60, oculta=True),
            col("DT. FECHOU", "data", 85, oculta=True),
            # (T-0023 v2) ocultas: a web mostra o valor de hoje no
            # formulario de edicao. A tela do PC nao muda.
            col("RECLAMAÇÃO", "texto", 200, oculta=True),
            col("OBSERVAÇÃO", "texto", 200, oculta=True),
            col("DT. RETORNO", "data", 85, oculta=True)]
    for l in linhas:
        g = dados[l[2]]
        l.extend([texto(g.get("reclamacao")), texto(g.get("observacao")),
                  gm.data(g.get("dt_retorno"))])
    edicao_g = edicao_garantia(
        {c["nome"]: i for i, c in enumerate(cols)}, gm.STATUS,
        gm.RESULTADOS, gm.novo_ticket(ctx.raiz))
    t_ = tabela("Garantias", cols, linhas, tons, edicao=edicao_g,
                filtros=("STATUS", "RESULTADO ANÁLISE", "PRAZO", "CIDADE",
                         "VENDEDOR"),
                kpis_de=cartoes,
                recortes=[("Em aberto", lambda l: l[I_ST] not in gm.FECHADOS),
                          ("Atrasadas", lambda l: l[I_PRAZO] == "ATRASADA"),
                          ("Sem cliente ou produto",
                           lambda l: not l[7] or not l[10])])
    t_["garantia"] = {"i_ticket": 2}     # duplo clique: a garantia
    t_["compacta"] = True
    r["tabelas"].append(t_)
    # (23/10, Alexandre) HISTORICO DE COMPRA: a assistente consulta tudo o
    # que o cliente comprou (item a item) pelo codigo, razao social ou nome
    # fantasia - o BUSCAR da aba procura nessas colunas
    try:
        r["tabelas"].append(_historico_de_compra(ctx))
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Histórico de compra: {erro}")
    # ---- por produto e por status x resultado
    pp = defaultdict(lambda: [0, 0, 0, 0])
    for l in linhas:
        x = pp[(l[10] or "(sem produto)", l[11])]
        x[0] += 1
        x[1] += l[I_ST] not in gm.FECHADOS
        x[2] += l[I_RES] == "PROCEDENTE"
        x[3] += l[I_RES] == "IMPROCEDENTE"
    r["tabelas"].append(tabela(
        "Por produto",
        [col("CÓD. PRODUTO", "texto", 120), col("DESCRIÇÃO", "texto", 260),
         col("GARANTIAS", "int"), col("EM ABERTO", "int"),
         col("PROCEDENTES", "int"), col("IMPROCEDENTES", "int")],
        sorted(([k[0], k[1]] + v for k, v in pp.items()),
               key=lambda x: -x[2])))
    sr = defaultdict(lambda: defaultdict(int))
    for l in linhas:
        sr[l[I_ST]][l[I_RES]] += 1
    r["tabelas"].append(tabela(
        "Status x resultado",
        [col("STATUS", "texto", 130)] + [col(x, "int", 110)
                                         for x in gm.RESULTADOS]
        + [col("TOTAL", "int")],
        [[s_] + [sr[s_][x] for x in gm.RESULTADOS] + [sum(sr[s_].values())]
         for s_ in gm.STATUS if sr.get(s_)]))

    def dados_da_garantia(ticket):
        """O que a janela da garantia mostra (detalhe + campos)."""
        g = dict(gm.ler(ctx.raiz).get(ticket) or {"ticket": ticket})
        cod = texto(g.get("cod_cliente"))
        c = ctx.cliente(cod) if cod else {}
        st = gm.situacao(g, ctx.hoje, fer)
        return {"g": g, "situacao": st, "base": cliente_base(cod),
                "cliente": {
            "Cliente": (f"{cod} - {c.get('nome', '')}" if cod
                        else texto(g.get("cliente")) or "—"),
            "Fantasia": c.get("fantasia", ""),
            "Endereço": " ".join(x for x in (c.get("endereco", ""),
                                             c.get("numero", "")) if x),
            "Bairro": c.get("bairro", ""),
            "Cidade": " / ".join(x for x in (c.get("cidade", ""),
                                             c.get("uf", "")) if x),
            "Telefone (cadastro)": c.get("contato", ""),
            "Vendedor": c.get("vend_nome", ""),
            "Supervisor": c.get("supervisor", "")}}

    r["garantia"] = {"dados": dados_da_garantia,
                     "campos_cliente": gm.CAMPOS_CLIENTE}
    if not dados:
        r["avisos"].append("Nenhuma garantia registrada.")
    return r


def devolucoes(ctx):
    import pos_venda as pvm                             # noqa: PLC0415
    hoje = ctx.hoje
    r = novo("pl_devolucoes", POS, "Farol de Devolução e Reembolsos",
             "Últimos 12 meses",
             "TABELA_BAP › ftPedidos (DEV) + ACOMPANHAMENTO_POS_VENDA")
    r["editar"] = "RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx"
    capa(r, ctx, anos_dos_dados(ctx))
    graficos_tempo(r, ctx, "Valor devolvido (R$)",
                   [(it["dt_nf"], abs(it["valor"])) for it in ctx.tabela["itens"]
                    if it["tipo"] == "DEV"], "moeda", VERMELHO)
    meses = ultimos_meses(hoje, 12)
    acomp = {texto(x.get("nf_dev")).lstrip("0"): x
             for x in ctx.posvenda.get("devolucoes", [])}
    fat_mes, fat_vend = defaultdict(float), defaultdict(float)
    for it in ctx.tabela["itens"]:
        # RN-GER-002: faturado = VND - DEV, pela data da NF
        v = _liquido(it)
        if v is not None and it["dt_nf"]:
            fat_mes[rotulo_mes(mes_de(it["dt_nf"]))] += v
            if mes_de(it["dt_nf"]) in meses:
                fat_vend[ctx.vendedor(it["vend"])] += v
    dev_mes = defaultdict(float)
    por_vend, por_cli, por_prod = (defaultdict(lambda: [0, 0.0])
                                   for _ in range(3))
    linhas, tons = [], []
    for (fil, nf, serie), itens in _pedidos(ctx, "DEV").items():
        i0 = itens[0]
        m = mes_de(i0["dt_nf"])
        if m not in meses:
            continue
        valor = abs(sum(i["valor"] for i in itens))
        dev_mes[m] += valor
        a = acomp.get(nf.lstrip("0"), {})
        antiga = not a and i0["dt_nf"] and i0["dt_nf"] < _inicio_controle()
        motivo = texto(a.get("motivo")) or ("(SEM MOTIVO)" if a else "")
        etapa = texto(a.get("etapa")) or (CONCLUIDA if antiga else
                                          "(sem acompanhamento)" if not a
                                          else "")
        vend = ctx.vendedor(i0["vend"])
        for g, k in ((por_vend, vend), (por_cli, ctx.nome_cliente(i0["cliente"]))):
            g[k][0] += 1
            g[k][1] += valor
        for i in itens:
            por_prod[i["cod"]][0] += abs(i["qtd"])
            por_prod[i["cod"]][1] += abs(i["valor"])
        cli = ctx.cliente(i0["cliente"])
        linhas.append([rotulo_mes(m), i0["dt_nf"], nf, ctx.filial(fil),
                       ctx.nome_cliente(i0["cliente"]), cli.get("cidade", ""),
                       cli.get("uf", ""), vend, valor, len(itens),
                       ", ".join(sorted({i["cod"] for i in itens}))[:120],
                       etapa, motivo, texto(a.get("autorizado_por")),
                       bd.data_de(a.get("recebida_em")), texto(a.get("credito")),
                       bd.data_de(a.get("credito_em")),
                       texto(a.get("responsavel")),
                       texto(a.get("chave")) if a else ""])
        tons.append("alerta" if a.get("aberta") else
                    ("" if a or antiga else "atencao"))
    linhas.sort(key=lambda x: x[1] or date.min, reverse=True)

    def cartoes(ls):
        meses_vis = {l[0] for l in ls}
        fat = sum(fat_mes[x] for x in meses_vis)
        val = sum(l[8] for l in ls)
        pd_ = pct_do_liquido(val, fat)                  # RN-GER-002
        com = [l for l in ls if l[18]]
        abertas = sum(1 for l in com if l[11].upper() not in
                      pvm.ENCERRADAS_DEV)
        sem_mot = sum(1 for l in com if l[12] in ("", "(SEM MOTIVO)"))
        return [
            kpi("Devoluções", br(len(ls)), "alerta" if ls else "ok", moeda(val)),
            kpi("% do faturado", p(pd_), "alerta" if (pd_ or 0) > 3 else "ok",
                ""),
            kpi("Clientes", br(len({l[4] for l in ls})), "neutro"),
            kpi("Abertas no acompanhamento", br(abertas),
                "atencao" if abertas else "ok"),
            kpi("Sem motivo", br(sem_mot), "alerta" if sem_mot else "ok",
                ""),
        ]
    r["kpis"] = cartoes([l for l in linhas if rotulo_no_periodo(ctx, l[0])])
    r["graficos"].append({
        "titulo": "Mês a mês: % do faturado",
        "rotulos": [rotulo_mes(x) for x in meses],
        "series": [{"nome": "% devolvido", "cor": AMARELO,
                    "valores": [pct_do_liquido(dev_mes[x], fat_mes[rotulo_mes(x)]) or 0
                                for x in meses]}],
        "formato": "pct"})
    datas = datas_para_escolher(hoje)
    cols = [col("MÊS", "texto", 60), col("DATA", "data"), col("NF DEV.", "texto", 85),
            col("FILIAL", "texto", 95), col("CLIENTE", "texto", 220),
            col("CIDADE", "texto", 120), col("UF", "texto", 40),
            col("VENDEDOR", "texto", 180), col("VALOR", "moeda"),
            col("ITENS", "int", 50), col("PRODUTOS", "texto", 200),
            col("ETAPA", "texto", 150), col("MOTIVO", "texto", 210),
            col("AUTORIZADO POR", "texto", 170), col("RECEBIDA EM", "data"),
            col("CRÉDITO", "texto", 150), col("CRÉDITO EM", "data"),
            col("RESPONSÁVEL", "texto", 140)]
    edicao = {"arquivo": "RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx",
              "aba": pvm.ABA_DEV, "chave": len(cols),
              "campos": [
                  {"campo": "etapa", "rotulo": "ETAPA",
                   "opcoes": pvm.ETAPAS_DEVOLUCAO, "col": 11},
                  {"campo": "motivo", "rotulo": "MOTIVO",
                   "opcoes": pvm.MOTIVOS_DEVOLUCAO, "col": 12},
                  {"campo": "autorizado_por", "rotulo": "AUTORIZADO POR",
                   "opcoes": ctx.autorizadores(), "col": 13},
                  {"campo": "recebida_em", "rotulo": "RECEBIDA EM",
                   "opcoes": datas, "data": True, "col": 14},
                  {"campo": "credito", "rotulo": "FORMA DO CRÉDITO",
                   "opcoes": pvm.FORMAS_CREDITO, "col": 15},
                  {"campo": "credito_em", "rotulo": "CRÉDITO EM",
                   "opcoes": datas, "data": True, "col": 16},
                  {"campo": "responsavel", "rotulo": "RESPONSÁVEL",
                   "opcoes": ctx.nomes_da_equipe(), "col": 17}]}
    r["tabelas"].append(tabela(
        "Devoluções", cols, linhas, tons,
        filtros=({"coluna": "MÊS", "padrao": mes_escolhido(ctx)},
                 "FILIAL", "VENDEDOR", "MOTIVO", "ETAPA"),
        kpis_de=cartoes, edicao=edicao))
    mot = defaultdict(lambda: [0, 0.0])
    for l in linhas:
        k_m = l[12] or ("(anterior ao controle)" if l[11] == CONCLUIDA
                        else "(sem acompanhamento)")
        mot[(l[0], k_m)][0] += 1
        mot[(l[0], k_m)][1] += l[8]
    r["tabelas"].append(tabela(
        "Por motivo", [col("MÊS", "texto", 60), col("MOTIVO", "texto", 260),
                       col("DEVOLUÇÕES", "int"), col("VALOR", "moeda")],
        sorted([[k[0], k[1]] + v for k, v in mot.items()], key=lambda x: -x[3]),
        filtros=({"coluna": "MÊS", "padrao": mes_escolhido(ctx)},)))
    r["tabelas"].append(tabela(
        "Por vendedor (12 meses)",
        [col("VENDEDOR", "texto", 240), col("DEVOLUÇÕES", "int"),
         col("VALOR", "moeda"), col("FATURADO 12M", "moeda"),
         col("% DEVOLVIDO", "pct")],
        sorted([[k, v[0], v[1], fat_vend.get(k, 0.0),
                 pct_do_liquido(v[1], fat_vend.get(k, 0.0))]
                for k, v in por_vend.items()], key=lambda x: -x[2])))
    r["tabelas"].append(tabela(
        "Por cliente (12 meses)", [col("CLIENTE", "texto", 280),
                                   col("DEVOLUÇÕES", "int"), col("VALOR", "moeda")],
        sorted([[k] + v for k, v in por_cli.items()], key=lambda x: -x[2])))
    r["tabelas"].append(tabela(
        "Por produto (12 meses)",
        [col("PRODUTO", "texto", 140), col("DESCRIÇÃO", "texto", 280),
         col("QTD", "num"), col("VALOR", "moeda")],
        sorted([[k, ctx.produto(k)] + v for k, v in por_prod.items()],
               key=lambda x: -x[3])))
    return r


# (T-0037, RD-0193) rotulos "Sem ..." do Farol de Fretes: o robo importa daqui
SEM_UF = "Sem UF"
SEM_CIDADE = "Sem cidade"
SEM_TRANSP = "Sem transportadora"
SEM_ACOMP = "Sem acompanhamento"


def rotulo_agrupa_fretes(i, l) -> str:
    """(T-0037, A2/A3) Rotulo da linha das tabelas Por UF (i=7), Por cidade
    (i=6) e Por transportadora (i=11) do Farol de Fretes. Funcao pura.
    Vazio vira "Sem UF", "Sem cidade" ou "Sem transportadora"; a cidade leva
    a UF ("SERRA BONITA / Sem UF", nunca a barra solta). Nota sem chave (sem
    acompanhamento) e sem transportadora vai para "Sem acompanhamento": assim
    "Sem transportadora" tem o mesmo criterio do cartao (chave e sem transp.)."""
    v = (l[i] or "").strip() if isinstance(l[i], str) else (l[i] or "")
    if i == 7:
        return uf_norm(v) or SEM_UF
    if i == 6:
        return (v or SEM_CIDADE) + " / " + (uf_norm(l[7]) or SEM_UF)
    if not v:
        return SEM_TRANSP if l[16] else SEM_ACOMP
    return v


def uf_norm(u) -> str:
    """(T-0037) UF da nota normalizada: strip + maiusculas. Funcao pura, unica
    para o cartao, o fator do faturado, o agrupamento Por UF e o filtro."""
    return str(u or "").strip().upper()


def kpis_fretes(ls, fat_por_mes_uf, uf=None) -> list:
    """Os 6 cartoes do Fretes (RN-POS-009). ls = linhas de "Notas com frete"
    (MES=0, CIDADE=6, UF=7, VLR NF=8, VLR FRETE=9, ETAPA=10, TRANSP.=11,
    ENTREGAR ATE=12, ENTREGUE=13, CHAVE=16). fat_por_mes_uf = {(mes, uf):
    faturado LIQUIDO de devolucao (RN-GER-002, pela data da NF; P3 B)} de
    todas as notas, por UF do cliente. Denominador: meses visiveis; com `uf`
    (o recorte, informado por quem chama) so o faturado dessa UF; uf=None
    soma todas as UFs (BAP inteira, nunca adivinhada pelas linhas). `uf` pode
    ser um texto ou um conjunto de UFs (filtro com varios estados: soma-as)."""
    meses_vis = {l[0] for l in ls}
    ufs = None if not uf else {uf} if isinstance(uf, str) else set(uf)
    if ufs is not None:                 # strip + maiusculas (uf_norm)
        ufs = {uf_norm(u) for u in ufs}
    fat = sum(v for (m, u), v in fat_por_mes_uf.items()
              if m in meses_vis and (ufs is None or u in ufs))
    val = sum(l[8] for l in ls)
    fr = sum(l[9] or 0 for l in ls)
    entregues = [l for l in ls if l[13] or l[10] in ("ENTREGUE", CONCLUIDA)]
    com_data = [l for l in ls if l[13]]
    no_prazo = [l for l in com_data if l[12] and l[13] <= l[12]]
    return [
        kpi("Notas com frete", br(len(ls)), "neutro", moeda(val)),
        kpi("% do faturado", p(pct_do_liquido(val, fat)), "info"),   # RN-GER-002
        kpi("Frete estimado", moeda(fr), "neutro",
            p(pct_de(fr, val)) + " do valor"),
        kpi("Cidades atendidas", br(len({l[6] for l in ls})), "neutro"),
        kpi("Entregues", br(len(entregues)), "ok",
            f"{p(pct_de(len(no_prazo), len(com_data)))} no prazo"
            if com_data else ""),
        kpi("Sem transportadora", br(sum(
            1 for l in ls if l[16] and not l[11])), "atencao"),
    ]


def fretes(ctx):
    import transportadoras as tr                         # noqa: PLC0415
    hoje = ctx.hoje
    r = novo("pl_fretes", POS, "Fretes",
             "Clientes fora das capitais · 12 meses",
             "TABELA_BAP › ftPedidos (VND) + cidade do cliente")
    cad = tr.carregar(ctx.raiz)
    meses = ultimos_meses(hoje, 12)
    ent = _entregas_por_nf(ctx)
    por_mes = defaultdict(int)          # notas com frete por mes
    # {(mes, UF do cliente): faturado liquido de devolucao} (RN-GER-002, P3 B)
    fat = defaultdict(float)
    for it in ctx.tabela["itens"]:
        v = _liquido(it) if it["dt_nf"] else None
        if v is None or mes_de(it["dt_nf"]) not in meses:
            continue
        fat[(rotulo_mes(mes_de(it["dt_nf"])),
             uf_norm(ctx.cliente(it["cliente"]).get("uf", "")))] += v
    linhas, tons = [], []
    for (fil, nf, serie), itens in _pedidos(ctx, "VND").items():
        i0 = itens[0]
        m = mes_de(i0["dt_nf"])
        if m not in meses:
            continue
        cli = ctx.cliente(i0["cliente"])
        valor = sum(i["valor"] for i in itens)
        if not bd.e_frete(cli.get("cidade")):
            continue
        por_mes[rotulo_mes(m)] += 1
        e = ent.get((fil, nf.lstrip("0")), {})
        prazo = ctx.mais_uteis(i0["dt_pedido"],
                               ctx.prazo_entrega(i0["cliente"])) \
            if i0["dt_pedido"] else None
        # (30/10) a previsao ajustada na tela (Farol de Entregas › Editar)
        prazo = bd.data_de(e.get("prevista_manual")) or prazo
        entregue = bd.data_de(e.get("entregue_em"))
        sla = ctx.corridos(i0["dt_pedido"], entregue or hoje) \
            if i0["dt_pedido"] and e else None
        transp = texto(e.get("transportadora"))
        linhas.append([rotulo_mes(m), i0["dt_pedido"], i0["dt_nf"], nf,
                       ctx.filial(fil), ctx.nome_cliente(i0["cliente"]),
                       cli.get("cidade", ""), uf_norm(cli.get("uf", "")), valor,
                       _frete(transp, valor, True, cad, frete_real_de(e),
                              uf_norm(cli.get("uf", "")),
                              cli.get("cidade", "")),
                       texto(e.get("etapa")) or (
                           CONCLUIDA if i0["dt_nf"] and i0["dt_nf"]
                           < _inicio_controle() else "(sem acompanhamento)"),
                       transp, prazo, entregue, sla,
                       texto(e.get("responsavel")), texto(e.get("chave"))])
        tons.append("alerta" if (not entregue and prazo and hoje > prazo
                                 and e) else ("ok" if entregue else ""))
    linhas.sort(key=lambda x: x[2] or date.min, reverse=True)
    for l in linhas:
        l[3] = l[3].lstrip("0")

    def cartoes(ls, filtro=None):
        f = filtro or {}
        return kpis_fretes(ls, fat, f.get(7) or f.get("UF") or None)

    r["kpis"] = cartoes([l for l in linhas if rotulo_no_periodo(ctx, l[0])])
    r["graficos"].append({
        "titulo": "Mês a mês: notas com frete",
        "rotulos": [rotulo_mes(x) for x in meses],
        "series": [{"nome": "notas", "cor": AZUL,
                    "valores": [por_mes[rotulo_mes(x)] for x in meses]}],
        "formato": "num"})
    cols = [col("MÊS", "texto", 58, oculta=True), col("DATA PED.", "dia", 70),
            col("DATA NF", "dia", 66), col("NF", "texto", 78),
            col("FILIAL", "texto", 90), col("CLIENTE", "texto", 210),
            col("CIDADE", "texto", 130), col("UF", "texto", 36),
            col("VLR NF", "moeda", 88), col("VLR FRETE", "moeda", 80),
            col("ETAPA", "texto", 120), col("TRANSPORTADORA", "texto", 140),
            col("ENTREGAR ATÉ", "dia", 90), col("ENTREGUE", "dia", 70),
            col("SLA ENTREGA", "int", 60), col("RESPONSÁVEL", "texto", 130)]
    r["tabelas"].append(tabela(
        "Notas com frete", cols, linhas, tons,
        filtros=({"coluna": "MÊS", "padrao": mes_escolhido(ctx)},
                 "UF", "FILIAL", "ETAPA", "TRANSPORTADORA"),
        kpis_de=cartoes,
        edicao=_entrega_editavel(ctx, len(cols), {
            "etapa": 10, "transportadora": 11, "entregue_em": 13,
            "prevista_manual": 12,
            "responsavel": 15}, cad, uf_col=7, cidade_col=6,
            frete=(8, None, 9))))
    for titulo, i, larg in (("Por UF", 7, 60), ("Por cidade", 6, 240),
                            ("Por transportadora", 11, 220)):
        g = defaultdict(lambda: [0, 0.0, 0.0])
        for l in linhas:
            k = (l[0], rotulo_agrupa_fretes(i, l))
            g[k][0] += 1
            g[k][1] += l[8]
            g[k][2] += l[9] or 0
        r["tabelas"].append(tabela(
            titulo, [col("MÊS", "texto", 60), col(titulo[4:].upper(), "texto", larg),
                     col("NOTAS", "int"), col("VLR NF", "moeda"),
                     col("VLR FRETE", "moeda")],
            sorted([[k[0], k[1]] + v for k, v in g.items()], key=lambda x: -x[3]),
            filtros=({"coluna": "MÊS", "padrao": mes_escolhido(ctx)},),
            kpis_de=lambda ls: [kpi("Notas", br(sum(l[2] for l in ls)), "neutro"),
                                kpi("Valor", moeda(sum(l[3] for l in ls)),
                                    "info"),
                                kpi("Frete estimado",
                                    moeda(sum(l[4] for l in ls)), "neutro")]))
    return r


TETO_DESCONTO = 15.0          # % de desconto maximo sobre o preco de tabela


def _saldo(tab, venda):
    """Saldo = o que sobrou do teto: tabela x 15% - (tabela - venda).
    Positivo: deu menos desconto que o teto. Negativo: passou do teto."""
    return tab * TETO_DESCONTO / 100.0 - (tab - venda)


# =========================================================================
# (13/10) SALDO PELA REGRA NOVA - o financeiro da condicao de pagamento
# fora do saldo e o acima do teto so com autorizacao (ver autorizacoes.py)
# =========================================================================
TOLERANCIA_TETO = 0.05          # 15,05%: o arredondamento do preco
SIT_DENTRO = "DENTRO DO TETO"
SIT_AUT_EU = "AUTORIZADO · ALEXANDRE"
SIT_AUT_PRICE = "AUTORIZADO · PRICE"
SIT_SEM_AUT = "SEM AUTORIZAÇÃO"
QUEM_AUTORIZA = ("ALEXANDRE", "PRICE")
INICIO_VERMELHO = date(2026, 8, 1)    # (13/10) antes: sem o alarme


def _ler_aba_da_tabela(ctx, aba):
    """(13/10) Uma aba da TABELA_BAP direto do arquivo (leitor rapido, sem
    openpyxl) - so enquanto o cache e de antes desta versao."""
    try:
        from xlsx_rapido import load_workbook as _lw    # noqa: PLC0415
        wb = _lw(bd.pasta_relatorios(ctx.raiz) / "TABELA_BAP.xlsx",
                 read_only=True, data_only=True)
        if aba not in wb.sheetnames:
            return []
        return list(wb[aba].iter_rows(values_only=True))
    except Exception:                                   # noqa: BLE001
        return []


def _condpag_fin(ctx) -> dict:
    if not hasattr(ctx, "_cpfin"):
        d = ctx.tabela.get("condpag_fin")
        if d is None:                     # cache antigo: le a aba
            d = {}
            for r in _ler_aba_da_tabela(ctx, "ftCondicaoPagamentos")[1:]:
                if r and r[0] and len(r) > 8:
                    d[texto(r[0]).zfill(3)] = bd.numero(r[8])
        ctx._cpfin = d
    return ctx._cpfin


def _autorizacoes_tabela(ctx) -> list:
    a = ctx.tabela.get("autorizacoes")
    if a is not None:
        return a
    linhas = _ler_aba_da_tabela(ctx, "ftAutorizacaoVenda")
    if not linhas:
        return []
    cab = [sem_acento(texto(c)).upper() for c in linhas[0]]

    def _i(n_):
        return next((j for j, c in enumerate(cab) if n_ in c), None)
    i_f, i_p, i_c = _i("FILIAL"), _i("PEDIDO"), _i("APROVA")
    return [{"filial": texto(r[i_f]) if i_f is not None else "",
             "pedido": texto(r[i_p]).split(".")[0], "codigo": texto(r[i_c])}
            for r in linhas[1:] if r and i_p is not None and i_c is not None
            and r[i_p] not in (None, "") and texto(r[i_c])]


def fin_da_cond(ctx, cond) -> float:
    """% ACRES. FIN. da condicao de pagamento (a vista -1,71)."""
    c = texto(cond).zfill(3) if cond else ""
    return float(_condpag_fin(ctx).get(c) or 0.0)


def autorizacoes_de_venda(ctx) -> dict:
    """{chave filial|pedido: {"codigo", "por"}}: o codigo do Protheus
    (ftAutorizacaoVenda) e, por cima, o que foi escrito nos farois."""
    if not hasattr(ctx, "_aut_venda"):
        import autorizacoes as au                       # noqa: PLC0415
        nome_cod = {re.sub(r"[^A-Z]", "", sem_acento(v).upper()): k
                    for k, v in (ctx.tabela.get("filiais") or {}).items()}
        saida = {}
        for a in _autorizacoes_tabela(ctx):
            f_ = nome_cod.get(re.sub(r"[^A-Z]", "",
                                     sem_acento(a.get("filial")).upper()))
            if f_:
                saida[au.chave(f_, a.get("pedido"))] = {
                    "codigo": texto(a.get("codigo")), "por": ""}
        try:
            for k, v in au.ler(ctx.raiz).items():
                saida[k] = {"codigo": v.get("codigo") or (
                    saida.get(k) or {}).get("codigo", ""),
                    "por": v.get("por") or ""}
        except Exception:                               # noqa: BLE001
            pass
        ctx._aut_venda = saida
    return ctx._aut_venda


def chave_pedido(filial, pedido) -> str:
    import autorizacoes as au                           # noqa: PLC0415
    return au.chave(filial, pedido)


def saldo_do_pedido(ctx, itens, filial=None, pedido=None) -> dict:
    """O desconto e o saldo de UM pedido pela regra nova:
    tab, venda, fin_pct (o financeiro aplicado), fin (R$), base (tabela com
    o financeiro), dcom (desconto comercial R$), pcom (%), teto, saldo (o
    que sobra ou passa do teto), situacao, conta (o que entra no saldo),
    codigo e por (a autorizacao).
    O financeiro aplicado: a condicao tem um % (a vista -1,71); como nem
    todo pedido leva o financeiro, vale o que deixa a condicao NEUTRA - nao
    gera saldo (dentro do teto: o maior desconto) e nao consome (fora: o
    menor)."""
    i0 = itens[0]
    tab = sum(i["p_tab"] * i["qtd"] if i["p_tab"] > 0 else i["valor"]
              for i in itens)
    venda = sum(i["valor"] for i in itens)
    a = fin_da_cond(ctx, i0.get("cond"))
    lim = TETO_DESCONTO + TOLERANCIA_TETO
    if tab > 0:
        d0 = (1 - venda / tab) * 100.0
        b1 = tab * (1 + a / 100.0)
        d1 = (1 - venda / b1) * 100.0 if b1 else d0
        if a and d0 <= lim and d1 <= lim:
            usa = d1 >= d0
        elif a:
            usa = d1 <= d0
        else:
            usa = False
    else:
        usa = False
    fin_pct = a if usa else 0.0
    base = tab * (1 + fin_pct / 100.0)
    dcom = base - venda
    pcom = dcom / base * 100.0 if base else 0.0
    teto = base * TETO_DESCONTO / 100.0
    saldo = teto - dcom
    aut = autorizacoes_de_venda(ctx).get(chave_pedido(
        filial or i0["filial"], pedido or i0["pedido"])) or {}
    por = aut.get("por") or ""
    # (13/10, Alexandre) acima do teto: desconta do saldo (sem autorizacao
    # ou autorizado pelo ALEXANDRE); o aprovado pelo PRICE NAO desconta
    # (22/10: confirmado pelo Alexandre - o Farol de Saldo so nao mostra
    # mais a autorizacao; quem grava e o Farol de Pedidos)
    if pcom <= lim:
        sit, conta = SIT_DENTRO, max(0.0, saldo)
    elif por == "ALEXANDRE":
        sit, conta = SIT_AUT_EU, saldo
    elif por == "PRICE":
        sit, conta = SIT_AUT_PRICE, 0.0
    else:
        sit, conta = SIT_SEM_AUT, saldo
    datas = [i.get("dt_nf") or i.get("dt_pedido") for i in itens
             if i.get("dt_nf") or i.get("dt_pedido")]
    desde = max(datas) >= INICIO_VERMELHO if datas else True
    # (16/10) o SALDO DO FRETE das notas do pedido (5% da nota - frete
    # real): entra no saldo sempre - sobra ou desconta - fora do teto
    sfr = saldos_de_frete(ctx)
    nfs = {(texto(i["filial"]), texto(i.get("nf")).lstrip("0"))
           for i in itens if i.get("tipo") == "VND" and i.get("nf")}
    fr = [sfr[k] for k in nfs if k in sfr]
    frete = sum(x["saldo"] for x in fr) if fr else None
    conta += frete or 0.0
    return {"tab": tab, "venda": venda, "fin_pct": fin_pct,
            "frete": frete, "frete_real": sum(x["real"] for x in fr) if fr
            else None, "frete_cheio": sum(x["cheio"] for x in fr) if fr
            else None,
            "fin": tab - base, "base": base, "dcom": dcom, "pcom": pcom,
            "teto": teto, "saldo": saldo, "situacao": sit, "conta": conta,
            "codigo": aut.get("codigo") or "", "por": por,
            # a linha VERMELHA: sem autorizacao, de 01/08/2026 em diante
            "grave": sit == SIT_SEM_AUT and desde}


def saldos_dos_pedidos(ctx) -> dict:
    """{(filial, pedido ou nf): saldo_do_pedido} de todo VND (cache)."""
    if not hasattr(ctx, "_saldos_ped"):
        g = defaultdict(list)
        for it in ctx.tabela["itens"]:
            if it["tipo"] == "VND":
                g[(it["filial"], it["pedido"] or it["nf"])].append(it)
        ctx._saldos_ped = {k: saldo_do_pedido(ctx, v) for k, v in g.items()}
    return ctx._saldos_ped


def saldo_do_item(ctx, it) -> float:
    """A parte do item no saldo do pedido (pela tabela dele) - para somar
    o saldo por filial, categoria, familia, vendedor..."""
    s = saldos_dos_pedidos(ctx).get((it["filial"], it["pedido"] or it["nf"]))
    if not s or not s["tab"]:
        return 0.0
    tab_i = it["p_tab"] * it["qtd"] if it["p_tab"] > 0 else it["valor"]
    return s["conta"] * tab_i / s["tab"]


def _saldo_de_qualquer(ctx, it):
    """O saldo_do_pedido do pedido do item: faturado (VND) pelo cache do
    Farol de Saldo; em aberto (VEA) e excluido (EXC) pelo pedido inteiro
    daquele tipo (cache proprio)."""
    k = (it["filial"], it["pedido"] or it["nf"])
    if it["tipo"] == "VND":
        return saldos_dos_pedidos(ctx).get(k)
    if not hasattr(ctx, "_saldos_outros"):
        g = defaultdict(list)
        for i in ctx.tabela["itens"]:
            if i["tipo"] in ("VEA", "EXC"):
                g[(i["tipo"], i["filial"], i["pedido"] or i["nf"])].append(i)
        ctx._saldos_outros = {kk: saldo_do_pedido(ctx, v)
                              for kk, v in g.items()}
    return ctx._saldos_outros.get((it["tipo"],) + k)


def base_do_item(ctx, it):
    """(14/10) (BASE, DESC. COMERCIAL) do item em R$: a parte dele na base
    (tabela com o financeiro da condicao) e no desconto comercial do
    pedido - as mesmas contas do Farol de Saldo, para todo farol que
    mostra desconto (Painel, Markup, Pedidos, Resumo de indicadores)."""
    tab_i = it["p_tab"] * it["qtd"] if it["p_tab"] > 0 else it["valor"]
    s = _saldo_de_qualquer(ctx, it)
    if not s or not s["tab"]:
        return tab_i, tab_i - it["valor"]
    f = tab_i / s["tab"]
    return s["base"] * f, s["dcom"] * f


def desconto_comercial(ctx, itens):
    """(14/10) O % DESCONTO COMERCIAL de um conjunto de itens (VND, VEA ou
    EXC) = desconto comercial / base, como no Farol de Saldo."""
    base = dcom = 0.0
    for it in itens:
        if it["tipo"] not in ("VND", "VEA", "EXC"):
            continue
        b, d = base_do_item(ctx, it)
        base += b
        dcom += d
    return dcom / base * 100.0 if base else None


# =========================================================================
# FAROL DE MARKUP (Analista Comercial)
# =========================================================================
MARKUP_MIN = 15.0              # a trava do Oportunidades (markup minimo)
CATEGORIA_ROTULO = {"pecas": "PEÇAS", "lubrificante": "LUBRIFICANTES",
                    "bateria": "BATERIAS", "pneu": "PNEUS"}


def _categoria(ctx, cod) -> str:
    """A CATEGORIA de todos os acompanhamentos: (15/10) a do Catalogo BAP
    2026 - PEÇAS, BATERIAS, LUBRIFICANTES, QUÍMICOS, PNEUS, ACESSÓRIOS (o
    resto: OUTROS), do ESTOQUE_BAP (ctx.categoria_bap)."""
    return ctx.categoria_bap(cod)


def _custo_do_item(ctx, it):
    """
    (custo unitario, sucata unitaria, origem) - o P. PEDIDO que o
    ESTOQUE_BAP tem para a filial+produto (CD, ou a media da filial/rede,
    como diz o ORIGEM_CUSTO); sem ele na filial, a media do produto na rede.
    BATERIA: o custo de verdade e o P. PEDIDO MAIS a sucata que vai junto
    para a fabrica (tabela de sucata do Oportunidades, pela amperagem).
    """
    com = ctx.comercial
    if not hasattr(ctx, "_custo_rede"):
        soma = defaultdict(list)
        for (_f, cod), c in com["custos"].items():
            if c.get("custo"):
                soma[cod].append(c["custo"])
        ctx._custo_rede = {k: sum(v) / len(v) for k, v in soma.items()}
    c = com["custos"].get(("4" + it["filial"], it["cod"])) or {}
    custo, origem = c.get("custo") or 0.0, c.get("origem") or "CD"
    if not custo and it["cod"] in ctx._custo_rede:
        custo, origem = ctx._custo_rede[it["cod"]], "REDE"
    sucata = 0.0
    if custo and _categoria(ctx, it["cod"]) == "BATERIAS":
        try:
            import oportunidade_nucleo as on            # noqa: PLC0415
            sucata = on.valor_da_sucata(ctx.produto(it["cod"]), com["kit"])
        except Exception:                               # noqa: BLE001
            sucata = 0.0
    return custo, sucata, (origem if custo else "")


def _todos_os_produtos(ctx, itens, mkp_bat, filial=None):
    """
    Aba TODOS OS PRODUTOS do Farol de Markup: o cadastro inteiro (com ou
    sem venda) - custo (P. PEDIDO medio da rede; bateria com a sucata),
    preco de tabela de capital e de interior (media das filiais), o markup
    de tabela, o estoque (BAP + lojas PMZ) e o que vendeu no periodo. A busca acha pelo
    codigo ou pela descricao.
    (07/10) Com a FILIAL escolhida, o preco e o custo sao os DELA (o mesmo
    preco da ALTERACOES_PRECO); em TODAS, a media das filiais (a coluna
    diz MEDIA).
    """
    com = ctx.comercial
    precos = com.get("precos") or {}
    cod_fil = ""
    if filial:
        cods = sorted(c for c, n in (ctx.tabela.get("filiais") or {}).items()
                      if n == filial)
        cod_fil = cods[0] if cods else ""
        longos = {"4" + c for c in cods} | set(cods)
        precos = {prod: v for (f, prod), v in
                  (com.get("precos_filial") or {}).items() if f in longos}
    est = defaultdict(float)
    for e in ctx.tabela.get("estoque") or []:
        if filial and ctx.filial(e.get("filial")) != filial:
            continue                    # (07/10) o estoque da filial
        est[e["cod"]] += max(0.0, e["qatu"] - e["reserva"])
    # (15/10, Alexandre) EST. = o estoque TOTAL: BAP (disponivel) + as
    # lojas PMZ (a mesma soma do Giro e do Oportunidades)
    for e in ctx.tabela.get("estoque_pmz") or []:
        if filial and ctx.filial(e.get("filial")) != filial:
            continue
        est[e["cod"]] += max(0.0, e.get("qtd") or 0.0)
    ult = {}
    for it in ctx.tabela["itens"]:
        if filial and ctx.filial(it["filial"]) != filial:
            continue
        if it["tipo"] == "VND" and it["dt_nf"] and \
                (it["cod"] not in ult or it["dt_nf"] > ult[it["cod"]]):
            ult[it["cod"]] = it["dt_nf"]
    vend = defaultdict(lambda: {"qtd": 0.0, "venda": 0.0, "venda_c": 0.0,
                                "custo": 0.0})
    for x in itens:
        v = vend[x["it"]["cod"]]
        v["qtd"] += x["it"]["qtd"]
        v["venda"] += x["venda"]
        if x["custo"]:
            v["venda_c"] += x["venda"]
            v["custo"] += x["custo"]
    codigos = (set(ctx.tabela.get("nomes") or {}) | set(precos) | set(est)
               | {c for (_f, c) in com.get("custos") or {}} | set(vend))
    codigos.discard("")
    linhas, tons = [], []
    for cod in codigos:
        custo_u, suc_u, origem = _custo_do_item(ctx, {"filial": cod_fil,
                                                      "cod": cod})
        custo = custo_u + suc_u
        cap, inte = precos.get(cod, (0.0, 0.0))
        cat = _categoria(ctx, cod)
        v = vend.get(cod)
        # (09/10) o PRECO DE VENDA = tabela (capital) menos o desconto
        # padrao (TETO_DESCONTO, 15%); o markup que vale e sobre ele
        venda_p = cap * (1 - TETO_DESCONTO / 100.0) if cap else 0.0
        mkp_v = _mkp(venda_p, custo)
        minimo = mkp_bat if cat == "BATERIAS" else MARKUP_MIN
        linhas.append([
            cod, ctx.produto(cod), cat, ctx.sistema(cod), ctx.familia(cod),
            ctx.linha(cod),
            texto((ctx.tabela.get("fornecedores") or {}).get(cod)),
            custo or None, origem or "SEM CUSTO", cap or None,
            TETO_DESCONTO if cap else None, venda_p or None, mkp_v,
            inte or None, _mkp(cap, custo), _mkp(inte, custo),
            est.get(cod, 0.0), "VENDEU" if v else "SEM VENDA",
            v["qtd"] if v else 0, v["venda"] if v else 0.0,
            _mkp(v["venda_c"], v["custo"]) if v else None, ult.get(cod)])
        tons.append("cinza" if not custo else
                    "alerta" if mkp_v is not None and mkp_v < 0 else
                    "atencao" if mkp_v is not None and mkp_v < minimo
                    else "")
    ordem = sorted(range(len(linhas)), key=lambda i: (-linhas[i][19],
                                                      linhas[i][0]))
    linhas = [linhas[i] for i in ordem]
    tons = [tons[i] for i in ordem]

    def cartoes(ls):
        com_c = [l for l in ls if l[7]]
        vend_ = [l for l in ls if l[18]]
        abaixo = [l for l in com_c if l[12] is not None and l[12] < (
            mkp_bat if l[2] == "BATERIAS" else MARKUP_MIN)]
        return [
            kpi("Produtos", br(len(ls)), "neutro",
                f"{br(len(vend_))} venderam {no_periodo_txt(ctx)}"),
            kpi("Sem custo", br(len(ls) - len(com_c)),
                "atencao" if len(ls) > len(com_c) else "ok"),
            kpi("Sem preço de tabela", br(sum(1 for l in ls if not l[9])),
                "neutro", "capital"),
            kpi("Markup de venda abaixo do mínimo", br(len(abaixo)),
                "atencao" if abaixo else "ok",
                f"tabela capital − {br(TETO_DESCONTO)}%"),
            kpi("Com estoque", br(sum(1 for l in ls if l[16] > 0)),
                "info", "BAP + lojas PMZ"),
        ]
    return tabela(
        "Todos os produtos",
        [col("PRODUTO", "texto", 140), col("DESCRIÇÃO", "texto", 300),
         col("CATEGORIA", "texto", 110), col("SISTEMA", "texto", 110),
         col("FAMÍLIA", "texto", 150), col("LINHA", "texto", 90),
         col("FORNECEDOR", "texto", 150), col("CUSTO", "moeda2", 90),
         # (15/10, Alexandre) a origem do custo sai da tela (fica no Excel)
         col("ORIGEM CUSTO", "texto", 110, oculta=True),
         # (09/10) TABELA (capital; em TODAS as filiais, a media delas),
         # o DESCONTO PADRAO, o PRECO DE VENDA e o MARKUP sobre ele. O
         # interior e o markup de tabela ficam ocultos (vao no Excel)
         # (15/10, Alexandre) nomes curtos: PRC. TABELA, % DESC., PRC. VENDA
         col("PRC. TABELA" if filial else "PRC. TABELA MÉD.",
             "moeda2", 90 if filial else 105),
         col("% DESC.", "pct1", 62),
         col("PRC. VENDA" if filial else "PRC. VENDA MÉD.",
             "moeda2", 90 if filial else 105),
         col("MKP VENDA %", "pct1", 90),
         col("PREÇO INTERIOR" if filial else "PREÇO INTERIOR MÉDIO",
             "moeda2", 100 if filial else 130, oculta=True),
         col("MKP TABELA %", "pct1", 95, oculta=True),
         col("MKP INTERIOR %", "pct1", 100, oculta=True),
         col("EST.", "num", 60), col("SITUAÇÃO", "texto", 90),
         col("QTD VEND.", "num", 72), col("R$ VENDA", "moeda", 90),
         col("MKP REAL %", "pct1", 82), col("ÚLT. VENDA", "data", 82)],
        linhas, tons,
        filtros=("SITUAÇÃO",) + FILTROS_PRODUTO + ("FORNECEDOR",),
        kpis_de=cartoes,
        recortes=[("Com custo", lambda l: bool(l[7])),
                  ("Sem custo", lambda l: not l[7]),
                  ("Markup de venda abaixo do mínimo",
                   lambda l: l[12] is not None and l[12] < (
                       mkp_bat if l[2] == "BATERIAS" else MARKUP_MIN)),
                  ("Com estoque e sem venda no período",
                   lambda l: l[16] > 0 and not l[18])])


def _mkp(venda, custo):
    return (venda / custo - 1.0) * 100.0 if custo > 0 and venda > 0 else None


MESES_CURTOS = ("", "JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO",
                "SET", "OUT", "NOV", "DEZ")


FILTROS_PAINEL = ("UF", "CIDADE", "SUPERVISOR", "VENDEDOR", "SEGMENTO",
                  "CATEGORIA", "SISTEMA", "FAMÍLIA", "LINHA", "PRODUTO")
FILIAL_DA_UF = {"AM": "MANAUS", "RR": "BOA VISTA", "AP": "MACAPÁ",
                "MT": "MATOGROSSO", "MA": "SÃO LUIS", "PA": "BELÉM"}


def _filtro_painel(ctx, r, ac):
    """As caixas de cima do Painel Executivo (UF, cidade, supervisor,
    vendedor, segmento, familia, categoria). Devolve (item_ok(it),
    meta_de(c, grupo, chave), cli_ok(c), texto). A meta do cliente segue o
    filtro: com FAMILIA, a meta da familia no cliente; com CATEGORIA, a da
    categoria (e a outra visao de produto fica sem meta)."""
    nomes = _nomes_vendedor(ac)
    equipe = ac.get("equipe_vend") or {}
    slim = [c for c in ac.get("clientes_slim") or []
            if not c.get("fora_do_planner")]
    esc = {n: ctx.param(n) for n in FILTROS_PAINEL}

    def campos_cli(c):
        k = _chaves_terr(c)
        return {"UF": k["uf"], "CIDADE": k["cidade"],
                "SEGMENTO": k["segmento"],
                "SUPERVISOR": texto(c.get("supervisor")) or "(SEM SUPERVISOR)",
                "VENDEDOR": _rotulo_vend(_cod6(c.get("cod_vendedor")), nomes)}
    # as opcoes de cada caixa: o que sobra com as outras escolhas
    fc = [(c, campos_cli(c)) for c in slim]
    for nome in FILTROS_PAINEL:
        if nome == "PRODUTO":          # (10/10) o padrao de produto
            vals = [(c, f"{c} - {ctx.produto(c)}".strip(" -"))
                    for c in sorted({it["cod"] for it in ctx.tabela["itens"]
                                     if it["tipo"] == "VND" and all(
                        not esc[n_] or ctx.classe(it["cod"], n_) == esc[n_]
                        for n_ in CLASSE_PRODUTO)})]
            if esc[nome] is not None and esc[nome] not in [v[0] for v in vals]:
                vals.append(esc[nome])
            r.setdefault("parametros", []).append({
                "nome": nome, "valores": [TODOS_RECORTE] + vals,
                "valor": esc[nome] or TODOS_RECORTE})
            continue
        if nome in CLASSE_PRODUTO:
            # (15/10) as opcoes seguem as outras escolhas de produto
            cods_ = {it["cod"] for it in ctx.tabela["itens"]
                     if it["tipo"] == "VND" and all(
                         n_ == nome or not esc[n_]
                         or ctx.classe(it["cod"], n_) == esc[n_]
                         for n_ in CLASSE_PRODUTO)}
            vals = ordem_da_classe(nome, {ctx.classe(c_, nome)
                                          for c_ in cods_})
        else:
            vals = sorted({x[nome] for _c, x in fc if all(
                esc[n] is None or x[n] == esc[n]
                for n in ("UF", "CIDADE", "SUPERVISOR", "VENDEDOR",
                          "SEGMENTO") if n != nome)})
        if esc[nome] is not None and esc[nome] not in vals:
            vals.append(esc[nome])
        r.setdefault("parametros", []).append({
            "nome": nome, "valores": [TODOS_RECORTE] + vals,
            "valor": esc[nome] or TODOS_RECORTE})
    txt = " · ".join(f"{n.capitalize()}: {esc[n]}" for n in FILTROS_PAINEL
                     if esc[n])
    de_cli = {}
    for c, x in fc:                   # (12/10) a 1a loja, como no Farol de Metas
        de_cli.setdefault(c["cod_cliente"], x)
    filtro_cli = [n for n in ("UF", "CIDADE", "SUPERVISOR", "VENDEDOR",
                              "SEGMENTO") if esc[n]]

    def cli_ok(c):                    # (12/10) a meta: loja a loja
        x = campos_cli(c)
        return all(x[n] == esc[n] for n in filtro_cli)
    cache = {}

    def item_ok(it):
        if esc["PRODUTO"] and texto(it["cod"]) != esc["PRODUTO"]:
            return False
        for n_ in CLASSE_PRODUTO:
            if esc[n_] and ctx.classe(it["cod"], n_) != esc[n_]:
                return False
        if not filtro_cli:
            return True
        k = (it["cliente"], it.get("vend"))
        if k not in cache:
            x = dict(de_cli.get(it["cliente"]) or {})
            if not x:
                b = ctx.cliente(it["cliente"]) or {}
                t_ = _chaves_terr(b)
                x = {"UF": t_["uf"], "CIDADE": t_["cidade"],
                     "SEGMENTO": segmento_do_cliente(ctx, it["cliente"])}
            cod = _cod6(it.get("vend"))      # pessoa: quem vendeu (a nota)
            e = equipe.get(cod) or {}
            x["VENDEDOR"] = _rotulo_vend(cod, nomes)
            x["SUPERVISOR"] = (texto(e.get("supervisor"))
                               or ctx.supervisor_de(it.get("vend")))
            cache[k] = all(x.get(n) == esc[n] for n in filtro_cli)
        return cache[k]

    def meta_de(c, grupo=None, chave=None):
        """A meta do cliente no filtro; grupo/chave: a de uma linha do
        quadro (familia ou categoria abre pela meta do cliente nelas)."""
        if esc["PRODUTO"]:              # meta nao abre por produto
            return None if grupo else 0.0
        # (15/10) o grupo mais fino escolhido manda (FAMILIA > SISTEMA >
        # CATEGORIA > LINHA); a outra visao de produto fica sem meta
        grupo_de = {"FAMÍLIA": "familia", "SISTEMA": "sistema",
                    "CATEGORIA": "categoria", "LINHA": "linha"}
        for nome_, campo_ in META_DA_CLASSE:
            if esc[nome_]:
                base = (c.get(campo_) or {}).get(esc[nome_], 0.0)
                if grupo and grupo != grupo_de[nome_]:
                    return None
                if grupo:
                    return base if chave == esc[nome_] else 0.0
                return base
        if grupo:
            return (c.get(f"meta_{grupo}") or {}).get(chave, 0.0)
        return c.get("meta") or 0.0
    return item_ok, meta_de, cli_ok, txt


def _fator_do_mes(ctx, ano, mes):
    """(fator da projecao, dias uteis passados, restantes) do mes: so o mes
    que esta correndo projeta; mes fechado = 1."""
    hoje = ctx.hoje
    ini = date(ano, mes, 1)
    fim = (date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1))
    du_tot = bd.dias_uteis_entre(ini - timedelta(days=1), fim, ctx.fer)
    if ini <= hoje <= fim:
        du_pass = bd.dias_uteis_entre(ini - timedelta(days=1), hoje, ctx.fer)
        # (06/11, Alexandre: "ajuste a projecao... que esta divergente"; regra
        # de 05/11 "tirar a venda de hoje da conta do DU") os DU passados vao
        # ate ONTEM, como no Painel do Diretor; a venda de hoje sai da
        # projecao (_de_hoje). No 1o dia util (nada fechado), como era.
        if _hoje_fora_do_du(ctx, ano, mes):
            du_pass = _du_fechados(ctx, ano, mes)
        du_rest = max(0, (du_tot or 0) - (du_pass or 0))
        return ((du_tot / du_pass) if du_pass else 1.0), du_pass, du_rest
    return 1.0, du_tot, 0


def _du_fechados(ctx, ano, mes) -> int:
    """(06/11) os DU FECHADOS do mes que esta correndo, como no Painel do
    Diretor: ate ONTEM, e nunca depois da ultima NF que entrou no mes (o
    robo parado nao derruba a media)."""
    hoje = getattr(ctx, "hoje", None)
    if not hoje or not mes or (ano, mes) != (hoje.year, hoje.month):
        return 0
    memo = getattr(ctx, "_du_fechados_memo", None)
    if memo is None:
        memo = ctx._du_fechados_memo = {}
    if (ano, mes) not in memo:
        ini = date(ano, mes, 1)
        ate = hoje - timedelta(days=1)
        ult = None
        try:
            for it in ctx.tabela["itens"]:
                d = it.get("dt_nf")
                if d and d.year == ano and d.month == mes and \
                        (ult is None or d > ult):
                    ult = d
        except Exception:                               # noqa: BLE001
            ult = None
        if ult and ult < ate:
            ate = ult
        memo[(ano, mes)] = (bd.dias_uteis_entre(ini - timedelta(days=1), ate,
                                                ctx.fer) or 0) \
            if ate >= ini else 0
    return memo[(ano, mes)]


def _hoje_fora_do_du(ctx, ano, mes) -> bool:
    """(06/11) o mes que esta correndo ja tem dia util FECHADO: entao hoje
    (o dia aberto) fica fora dos DU e da projecao."""
    return _du_fechados(ctx, ano, mes) > 0


def _de_hoje(ctx, it, qtd=False):
    """(06/11) a parte do item que SAI da projecao: a nota de hoje (o dia
    aberto) quando hoje esta fora dos DU; o pedido em aberto (_ped) nao
    (entra inteiro). qtd=True: a quantidade (com sinal da devolucao)."""
    d = it.get("dt_nf")
    hoje = getattr(ctx, "hoje", None)
    if not d or not hoje or d != hoje or it.get("_ped") or \
            not _hoje_fora_do_du(ctx, hoje.year, hoje.month):
        return 0.0
    if qtd:
        return ((it["qtd"] or 0) if it["tipo"] == "VND"
                else -abs(it["qtd"] or 0))
    return _liquido(it) or 0.0


def _mom(vals):
    """% de um mes para o outro (o primeiro: sem)."""
    return [None] + [((b / a - 1) * 100.0) if a else None
                     for a, b in zip(vals, vals[1:])]


def painel_executivo(ctx):
    """
    PAINEL EXECUTIVO (reuniao), desenhado no Claude Design: cartoes (meta,
    real, projecao, ating. projetado, markup, desconto); FILIAL, CATEGORIA,
    FAMILIA (pizza do projetado) e SEGMENTO com META, REAL, PROJECAO,
    % PROJ., POSITIVACAO, IPP, VOLUME e MARKUP (% e R$); e o ano mes a mes
    (faturamento projetado, positivacao e gap, ticket e IPP, markup R$ e %,
    com a linha do % MoM). Filtros: UF, cidade, supervisor, vendedor,
    segmento, familia e categoria.
        PROJECAO = real / dias uteis passados x dias uteis do mes
        GAP = quem ja comprou no ano ate o mes e nao comprou no mes
        IPP = itens (SKUs) por nota
    """
    hoje = ctx.hoje
    ano, mes = periodo(ctx)
    r = novo("vc_painel", VEN, "Painel Executivo",
             f"{rotulo_mes(f'{ano}-{mes:02d}') if mes else f'Ano {ano}'}"
             " · faturamento líquido (venda − devolução)",
             "TABELA_BAP › ftPedidos + Gerador de Meta + custo (P. PEDIDO)")
    capa(r, ctx, anos_dos_dados(ctx))
    ac = {}
    if mes:
        try:
            ac = meta_do_periodo(ctx)["acomp"] or {}
        except Exception:                               # noqa: BLE001
            ac = {}
    item_ok, meta_de, cli_ok, txt = _filtro_painel(ctx, r, ac)
    if txt:
        r["subtitulo"] += f" · {txt}"
    itens = [it for it in ctx.tabela["itens"] if item_ok(it)]
    # (06/10) VISAO PEDIDO: os pedidos em aberto (VEA) de hoje. Marcando a
    # caixa, eles somam no REAL do mes que esta correndo como se ja fossem
    # nota (data de hoje) - e na projecao entram inteiros (pedido nao se
    # projeta: ja esta na mao)
    flag_ped = ctx.param("PEDIDOS") == "SIM"
    r["parametros"].append({"nome": "PEDIDOS", "tipo": "flag",
                            "rotulo": "Somar pedidos em aberto",
                            "valores": [("SIM", "com pedidos em aberto")],
                            "valor": "SIM" if flag_ped else None})
    corre_mes = ano == hoje.year and (not mes or mes == hoje.month)
    abertos = [it for it in itens if it["tipo"] == "VEA"]
    if flag_ped and corre_mes:
        itens = itens + [dict(it, tipo="VND", dt_nf=hoje, serie="",
                              nf=f"PED {it['pedido']}", _ped=True)
                         for it in abertos]
        r["subtitulo"] += " · + pedidos em aberto"
    elif flag_ped:
        r["avisos"].append("Pedidos em aberto só somam no mês que está "
                           "correndo.")
    custo_de = {}

    def custo(it):
        k = id(it)
        if k not in custo_de:
            cu, suc, _o = _custo_do_item(ctx, it)
            custo_de[k] = (cu + suc) * it["qtd"]
        return custo_de[k]

    def liq(it):
        return _liquido(it)
    no_periodo = [it for it in itens if it["dt_nf"] and no_mes(ctx, it["dt_nf"])
                  and it["tipo"] in ("VND", "DEV")]
    vnd = [it for it in no_periodo if it["tipo"] == "VND"]
    real = sum(liq(it) for it in no_periodo)
    ped_v = sum(it["valor"] for it in no_periodo if it.get("_ped"))
    fator, du_pass, du_rest = (_fator_do_mes(ctx, ano, mes) if mes
                               else (1.0, None, None))
    hoje_v = sum(_de_hoje(ctx, it) for it in no_periodo)    # (06/11)
    tend = (real - ped_v - hoje_v) * fator + ped_v
    slim = [c for c in ac.get("clientes_slim") or []
            if not c.get("fora_do_planner") and cli_ok(c)]
    meta = None
    if mes:
        meta = sum(meta_de(c) or 0 for c in slim) or None
        if meta is None and not txt:
            ger = (ac.get("recortes") or {}).get("gerente") or []
            meta = sum(l.get("meta") or 0 for l in ger) or None
    com_c = [it for it in vnd if custo(it)]
    venda_c = sum(it["valor"] for it in com_c)
    custo_t = sum(custo(it) for it in com_c)
    mkp = _mkp(venda_c, custo_t)
    # (14/10) o desconto COMERCIAL do Farol de Saldo (o financeiro fora)
    desc = desconto_comercial(ctx, [it for it in vnd if not it.get("_ped")])
    esperado = (du_pass / (du_pass + du_rest) * 100.0
                if du_pass is not None and (du_pass + (du_rest or 0)) else None)
    at = pct_de(real, meta) if meta else None
    at_p = pct_de(tend, meta) if meta else None
    r["kpis"] = [
        kpi("Desafio comercial", moeda(meta) if meta else "—", "neutro",
            (f"falta {moeda(max(0, meta - real))}" if meta
             else "sem desafio no mês")),
        kpi("Real + pedidos" if ped_v else "Real", moeda(real), "ok",
            (f"faturado {moeda(real - ped_v)} + pedidos {moeda(ped_v)}"
             if ped_v else
             f"ating. {p(at)} · {moeda((real - hoje_v) / du_pass)}/dia"
             if meta and du_pass else
             f"{moeda((real - hoje_v) / du_pass)}/dia" if du_pass else "")),
        _kpi_pedidos(ctx, abertos, flag_ped and corre_mes),
        kpi("Projeção", moeda(tend), "info",
            ("no ritmo de hoje" + (" + pedidos" if ped_v else ""))
            if du_rest else "mês fechado"),
        kpi("Ating. projetado", p(at_p) if meta else "—",
            _tom_ating(at_p) if at_p is not None else "neutro",
            (f"nec. {moeda(max(0, meta - real) / du_rest)}/dia"
             if meta and du_rest else
             f"esperado {p(esperado)}" if esperado is not None else "")),
        kpi("Markup", "—" if mkp is None else f"{br(mkp, 1)}%", "info",
            f"receita {moeda(venda_c - custo_t)}" if com_c else ""),
        kpi("Desconto comercial", p(desc), "neutro", "sem o financeiro"),
    ]
    # ---- vendedores e clientes (as abas)
    pv = defaultdict(lambda: {"real": 0.0, "vol": 0.0, "cli": set(),
                              "vc": 0.0, "cu": 0.0, "ped": 0.0, "hoje": 0.0})
    for it in no_periodo:
        x = pv[it["vend"]]
        x["real"] += liq(it)
        x["hoje"] += _de_hoje(ctx, it)
        if it.get("_ped"):
            x["ped"] += it["valor"]
        if it["tipo"] == "VND":
            x["vol"] += it["qtd"]
            if it.get("_ped") or positivou(ctx, it["cliente"], it["dt_nf"]):
                x["cli"].add(it["cliente"])
            if custo(it):
                x["vc"] += it["valor"]
                x["cu"] += custo(it)
    lv = sorted(([ctx.vendedor(v), ctx.supervisor_de(v), x["real"],
                  (x["real"] - x["ped"] - x["hoje"]) * fator + x["ped"],
                  x["vol"],
                  len(x["cli"]),
                  _mkp(x["vc"], x["cu"])] for v, x in pv.items()),
                key=lambda l: -l[2])
    cols_v = [col("VENDEDOR", "texto", 220), col("SUPERVISOR", "texto", 180),
              col("R$", "moeda"), col("PROJEÇÃO", "moeda"),
              col("VOL.", "num", 70), col("CLIENTES", "int", 70),
              col("% MKP", "pct1", 70)]
    tot_v = ["TOTAL", "", real, tend, sum(l[4] for l in lv),
             len({it["cliente"] for it in vnd if it.get("_ped")
                  or positivou(ctx, it["cliente"], it["dt_nf"])}), mkp]
    # ---- (12/10) CLIENTES: a carteira do filtro (com o DESAFIO) + quem
    # comprou fora dela; desafio, real, gap, % ating., M3M, notas e IPP
    comp_p = f"{ano}-{mes:02d}" if mes else ""
    m3_p = set(_meses_antes(comp_p, 3)) if comp_p else set()
    m3m_cli, m3m_prod = defaultdict(float), defaultdict(float)
    if m3_p:
        for it in itens:
            if it["dt_nf"] and not it.get("_ped") and \
                    mes_de(it["dt_nf"]) in m3_p and it["tipo"] in ("VND",
                                                                 "DEV"):
                m3m_cli[it["cliente"]] += liq(it) / 3.0
                m3m_prod[it["cod"]] += liq(it) / 3.0
    pc = defaultdict(lambda: {"real": 0.0, "nf": defaultdict(set),
                              "vend": None})
    for it in no_periodo:
        x = pc[it["cliente"]]
        x["real"] += liq(it)
        if it["tipo"] == "VND":
            x["nf"][(it["filial"], it["nf"])].add(it["cod"])
            x["vend"] = x["vend"] or it.get("vend")
    des_cli, vend_cli = defaultdict(float), {}
    for c in slim:
        cod = c["cod_cliente"]
        des_cli[cod] += meta_de(c) or 0.0
        if cod not in vend_cli and c.get("cod_vendedor"):
            vend_cli[cod] = c["cod_vendedor"]
    lc = []
    # (12/10) quem comprou no M3M tambem entra (o M3M fecha com Produtos)
    for c in sorted(set(pc) | set(des_cli)
                    | {k for k, v in m3m_cli.items() if abs(v) > 0.5}):
        x = pc.get(c) or {"real": 0.0, "nf": {}, "vend": None}
        cli = ctx.cliente(c)
        uf = territorio_do_cliente(ctx, c, "uf")
        cid = territorio_do_cliente(ctx, c, "cidade")
        if uf == FORA_PLANNER_META:
            uf, cid = cli.get("uf", ""), cli.get("cidade", "")
        des = des_cli.get(c) if c in des_cli else None
        nfs = x["nf"]
        lc.append([ctx.nome_cliente(c), cid, uf, segmento_do_cliente(ctx, c),
                   ctx.vendedor(vend_cli.get(c) or x["vend"] or "")
                   .split(" - ", 1)[-1],
                   cli.get("curva") or "", des, x["real"],
                   max(0.0, des - x["real"]) if des else None,
                   pct_de(x["real"], des) if des else None,
                   m3m_cli.get(c, 0.0), len(nfs),
                   (sum(len(v) for v in nfs.values()) / len(nfs)) if nfs
                   else None])
    lc.sort(key=lambda l: (-(l[8] or 0), -(l[7] or 0)))
    cols_c = [col("CLIENTE", "texto", 270), col("CIDADE", "texto", 170),
              col("UF", "texto", 34), col("SEGMENTO", "texto", 175),
              col("VENDEDOR", "texto", 210), col("CURVA", "texto", 50),
              col("DESAFIO", "moeda", 90), col("REAL", "moeda", 85),
              col("GAP", "moeda", 90), col("% ATING.", "pct", 66),
              col("M3M", "moeda", 85), col("NOTAS", "int", 52),
              col("IPP", "num2", 46)]

    def tot_cli(ls):
        d_ = sum(l[6] or 0 for l in ls)
        r_ = sum(l[7] or 0 for l in ls)
        n_ = sum(l[11] or 0 for l in ls)
        sk = sum((l[12] or 0) * (l[11] or 0) for l in ls)
        return ["TOTAL", "", "", "", "", "", d_ or None, r_,
                sum(l[8] or 0 for l in ls) or None,
                pct_de(r_, d_) if d_ else None,
                sum(l[10] or 0 for l in ls), n_, sk / n_ if n_ else None]

    inat_cli = {c for c in des_cli if ctx.inativo(c)}

    def cartoes_cli(ls):
        t_ = tot_cli(ls)
        pos_ = len({l[0] for l in ls if l[11]})
        # CLIENTES: os da carteira sem os inativados (= o Painel e o Farol
        # de Metas); quem so comprou fora da carteira nao conta aqui
        cart_ = sum(1 for l in ls if l[6] is not None
                    and l[0].split(" - ")[0] not in inat_cli)
        return [kpi("Clientes", br(cart_), "neutro",
                    f"{br(pos_)} positivados"),
                kpi("Desafio", moeda(t_[6]) if t_[6] else "—", "neutro"),
                kpi("Real", moeda(t_[7]), "ok",
                    f"ating. {p(t_[9])}" if t_[9] is not None else ""),
                kpi("Gap", moeda(t_[8] or 0),
                    "alerta" if (t_[8] or 0) > 0 else "ok", "falta no desafio"),
                kpi("M3M", moeda(t_[10]), "info", "média 3 meses"),
                kpi("IPP", br(t_[12] or 0, 2), "neutro", "SKU por nota")]
    # ---- (12/10) PRODUTOS: curva ABC (a do Giro), clientes, notas, preco
    # medio, M3M e a variacao projetada, markup e estoque
    prod = defaultdict(lambda: {"real": 0.0, "qtd": 0.0, "cli": set(),
                                "nf": set(), "vc": 0.0, "cu": 0.0,
                                "ped": 0.0, "hoje": 0.0})
    for it in no_periodo:
        x = prod[it["cod"]]
        x["real"] += liq(it)
        x["hoje"] += _de_hoje(ctx, it)
        if it.get("_ped"):
            x["ped"] += it["valor"]
        if it["tipo"] == "VND":
            x["qtd"] += it["qtd"]
            x["cli"].add(it["cliente"])
            x["nf"].add((it["filial"], it["nf"]))
            if custo(it):
                x["vc"] += it["valor"]
                x["cu"] += custo(it)
    curva_p = curva_de_produtos(ctx)
    est_p = defaultdict(float)
    for e in ctx.tabela.get("estoque") or []:
        est_p[e["cod"]] += max(0.0, (e.get("qatu") or 0) - (e.get("reserva")
                                                             or 0))
    lp = []
    vc_cu = {}              # (14/10) o MKP % do TOTAL (venda e custo)
    for c in set(prod) | {k for k, v in m3m_prod.items() if abs(v) > 0.5}:
        x = prod.get(c) or {"real": 0.0, "qtd": 0.0, "cli": set(),
                            "nf": set(), "vc": 0.0, "cu": 0.0, "ped": 0.0,
                            "hoje": 0.0}
        vc_cu[c] = (x["vc"], x["cu"])
        proj = (x["real"] - x["ped"] - x["hoje"]) * fator + x["ped"]
        m3 = m3m_prod.get(c, 0.0)
        lp.append([c, ctx.produto(c), ctx.categoria_bap(c), ctx.familia(c),
                   curva_p.get(c, "-"), x["real"], x["qtd"], len(x["cli"]),
                   len(x["nf"]),
                   (x["real"] / x["qtd"]) if x["qtd"] else None, m3,
                   ((proj / m3 - 1) * 100.0) if m3 > 0.5 else None,
                   _mkp(x["vc"], x["cu"]), est_p.get(c, 0.0),
                   # (15/10) SISTEMA e LINHA do catalogo (no fim: as
                   # posicoes de cima nao mudam)
                   ctx.sistema(c), ctx.linha(c)])
    lp.sort(key=lambda l: (-(l[5] or 0), -(l[10] or 0)))
    cols_p = [col("PRODUTO", "texto", 125), col("DESCRIÇÃO", "texto", 380),
              col("CATEGORIA", "texto", 120), col("FAMÍLIA", "texto", 125),
              col("CURVA", "texto", 50), col("R$", "moeda", 85),
              col("QTD", "num", 52), col("CLIENTES", "int", 62),
              col("NOTAS", "int", 52), col("PREÇO MÉDIO", "moeda2", 88),
              col("M3M", "moeda", 85), col("VAR. x M3M", "pct1", 82),
              col("MKP %", "pct1", 60), col("ESTOQUE", "num", 66),
              col("SISTEMA", "texto", 110), col("LINHA", "texto", 90)]

    def tot_prod(ls):
        r_ = sum(l[5] or 0 for l in ls)
        m_ = sum(l[10] or 0 for l in ls)
        h_ = sum(prod[l[0]]["hoje"] for l in ls if l[0] in prod)  # (06/11)
        return ["TOTAL", "", "", "", "", r_, sum(l[6] or 0 for l in ls),
                None, None, None, m_,
                (((r_ - h_) * fator / m_ - 1) * 100.0) if m_ > 0.5
                else None,
                _mkp(sum(vc_cu.get(l[0], (0, 0))[0] for l in ls),
                     sum(vc_cu.get(l[0], (0, 0))[1] for l in ls)),
                sum(l[13] or 0 for l in ls), "", ""]

    def cartoes_prod(ls):
        t_ = tot_prod(ls)
        com_v = sum(1 for l in ls if l[5])
        parados = sum(1 for l in ls if not l[5] and (l[10] or 0) > 0)
        return [kpi("Produtos", br(com_v), "neutro", "com venda no mês"),
                kpi("Real", moeda(t_[5]), "ok"),
                kpi("M3M", moeda(t_[10]), "info", "média 3 meses"),
                kpi("Var. projetada", p(t_[11]) if t_[11] is not None
                    else "—", "ok" if (t_[11] or 0) >= 0 else "alerta",
                    "projeção x M3M"),
                kpi("Sem venda no mês", br(parados), "atencao" if parados
                    else "ok", "vendiam no M3M"),
                kpi("Curva A", br(sum(1 for l in ls if l[4] == "A")),
                    "neutro", "na lista")]
    # ---- o ano mes a mes (o mes que esta correndo: PROJETADO)
    ate = 12 if ano < hoje.year else hoje.month
    meses = [f"{ano}-{m:02d}" for m in range(1, ate + 1)]
    por_mes = {m: {"real": 0.0, "cli": set(), "nf": defaultdict(set),
                   "ped": set(), "vnd": 0.0, "vc": 0.0, "cu": 0.0,
                   "aberto": 0.0, "hoje": 0.0} for m in meses}
    for it in itens:
        d = it["dt_nf"]
        if not d or it["tipo"] not in ("VND", "DEV"):
            continue
        m = mes_de(d)
        if m not in por_mes:
            continue
        x = por_mes[m]
        x["real"] += liq(it)
        x["hoje"] += _de_hoje(ctx, it)
        if it.get("_ped"):
            x["aberto"] += it["valor"]
        if it["tipo"] == "VND":
            if it.get("_ped") or positivou(ctx, it["cliente"], it["dt_nf"]):
                x["cli"].add(it["cliente"])
            x["nf"][(it["filial"], it["nf"])].add(it["cod"])
            x["ped"].add((it["filial"], it["pedido"]))
            x["vnd"] += it["valor"]
            if custo(it):
                x["vc"] += it["valor"]
                x["cu"] += custo(it)
    corre = f"{hoje.year}-{hoje.month:02d}"
    f_corre = _fator_do_mes(ctx, hoje.year, hoje.month)[0]
    ja, lm = set(), []
    for m in meses:
        x = por_mes[m]
        ja |= x["cli"]
        nfs = x["nf"]
        sku_nf = (sum(len(v) for v in nfs.values()) / len(nfs)) if nfs else 0
        lm.append([rotulo_mes(m), x["real"], len(x["cli"]),
                   len(ja) - len(x["cli"]), len(nfs), sku_nf,
                   x["vnd"] / len(x["ped"]) if x["ped"] else 0.0,
                   _mkp(x["vc"], x["cu"]), x["vc"] - x["cu"],
                   (x["real"] - x["aberto"] - x["hoje"])
                   * (f_corre if m == corre else 1.0) + x["aberto"]
                   + (0.0 if m == corre else x["hoje"])])
    cols_m = [col("MÊS", "texto", 80), col("FATURAMENTO", "moeda", 110),
              col("POSITIVADOS", "int", 90), col("GAP", "int", 70),
              col("NOTAS", "int", 70), col("IPP (SKU/NF)", "num2", 90),
              col("TKM PEDIDO", "moeda", 100), col("MARKUP %", "pct1", 80),
              col("MARKUP R$", "moeda", 100),
              col("FAT. PROJETADO", "moeda", 110)]
    rot_m = [MESES_CURTOS[int(m[5:])] for m in meses]
    proj_m = [l[9] for l in lm]
    claro = "#A9DBA9"
    g_fat = {"titulo": f"Faturamento projetado · {ano}", "rotulos": rot_m,
             "series": [{"nome": "R$", "cor": VERDE, "valores": proj_m,
                         "cores": [claro if m == corre and f_corre > 1
                                   else VERDE for m in meses]}],
             "formato": "moeda", "rotular": True,
             "linha": {"nome": "% MoM", "valores": _mom(proj_m)}}
    if meta and mes and f"{ano}-{mes:02d}" == corre:
        g_fat["meta"] = meta
        g_fat["rotulo_meta"] = "desafio"
    pos_m = [l[2] for l in lm]
    g_pos = {"titulo": "Positivação e gap", "rotulos": rot_m,
             "series": [{"nome": "positivados", "cor": VERDE,
                         "valores": pos_m},
                        {"nome": "gap", "cor": "#E8A0A0",
                         "valores": [l[3] for l in lm]}], "formato": "num",
             "rotular": True,
             "linha": {"nome": "% MoM posit.", "valores": _mom(pos_m)}}
    tkm_m = [l[6] for l in lm]
    g_tkm = {"titulo": "Ticket médio por pedido · IPP (SKU por nota)",
             "rotulos": rot_m,
             "series": [{"nome": "TKM", "cor": "#2F5D3A", "valores": tkm_m}],
             "formato": "moeda", "rotular": True,
             "subrotulos": [f"{br(l[5], 2)} sku/nf\n{br(l[4])} nf"
                            for l in lm],
             "linha": {"nome": "% MoM ticket", "valores": _mom(tkm_m)}}
    g_mkp = {"titulo": "Markup · R$ (barras) e % (linha)", "rotulos": rot_m,
             "series": [{"nome": "markup R$", "cor": VERDE,
                         "valores": [l[8] for l in lm]}],
             "formato": "moeda", "rotular": True,
             "linha": {"nome": "markup %", "valores": [l[7] for l in lm]}}
    r["graficos"] = [dict(g_fat, largo=True), g_pos, g_tkm, g_mkp]
    # ---- os quadros: filial, categoria, familia e segmento
    grupos = _painel_grupos(ctx, no_periodo, custo, fator, ano, mes, ac,
                            slim, meta_de, item_ok)
    r["painel"] = {"colunas": (1, 1), "altura_min": 4 * 270, "blocos": [
        {"col": 0, "row": 0, "tipo": "pizza", **grupos["filial"]},
        {"col": 1, "row": 0, "tipo": "pizza", **grupos["categoria"]},
        {"col": 0, "row": 1, "tipo": "pizza", **grupos["familia_top"]},
        {"col": 1, "row": 1, "tipo": "pizza", **grupos["segmento"]},
        {"col": 0, "row": 2, "tipo": "barras", "grafico": g_fat},
        {"col": 1, "row": 2, "tipo": "barras", "grafico": g_pos},
        {"col": 0, "row": 3, "tipo": "barras", "grafico": g_tkm},
        {"col": 1, "row": 3, "tipo": "barras", "grafico": g_mkp},
    ]}
    # ---- (12/10) VISAO EXECUTIVA: todos os farois num placar, com o
    # impacto estimado no faturamento (a primeira aba)
    try:
        import visao_executiva as vx                    # noqa: PLC0415
        vis_x = vx.montar(ctx, {
            "ano": ano, "mes": mes, "real": real, "tend": tend, "meta": meta,
            "itens": itens, "no_periodo": no_periodo, "fator": fator,
            "du_pass": du_pass, "du_rest": du_rest, "mkp": mkp, "desc": desc,
            "ac": ac, "slim": slim, "filtrado": bool(txt)})
    except Exception as erro:                           # noqa: BLE001
        vis_x = {}
        r["avisos"].append(f"Visão executiva fora do ar: {erro}")
    if vis_x.get("cartoes"):
        blocos = [{"col": 0, "row": 0, "colspan": 2, "rowspan": 2,
                   "tipo": "placar", "titulo": "Os faróis no mês",
                   "cartoes": vis_x["cartoes"], "por_linha": 4},
                  {"col": 0, "row": 2, "tipo": "insights",
                   "titulo": "O que move o faturamento",
                   "linhas": vis_x["insights"]},
                  {"col": 1, "row": 2, "tipo": "hbarras",
                   **vis_x["hbarras"]}]
        for i_, g_ in enumerate(vis_x["graficos"][:2]):
            blocos.append({"col": i_, "row": 3, "tipo": "barras",
                           "grafico": g_})
        r["painel_pre"] = {"titulo": "Visão executiva", "painel": {
            "colunas": (1, 1), "altura_min": (3 + bool(vis_x["graficos"]))
            * 270, "blocos": blocos}}
        if vis_x.get("filtrado"):
            r["avisos"].append("Visão executiva: vendas, clientes, ticket e "
                               "devoluções seguem o filtro; entregas, "
                               "garantias, inadimplência, giro, expositores, "
                               "visitas e indicadores são da BAP inteira.")
        lin_x = [[c_["farol"], {"ok": "BOM", "atencao": "ATENÇÃO",
                                "alerta": "RUIM"}.get(c_["tom"], "—"),
                  c_["valor"], c_["rotulo"], c_["detalhe"], c_["impacto"],
                  c_["sentido"], c_.get("frase") or c_.get("dica") or ""]
                 for c_ in vis_x["cartoes"]]
        r["tabelas"].insert(0, tabela(
            "Faróis", [col("FAROL", "texto", 170), col("SITUAÇÃO", "texto", 80),
                       col("VALOR", "texto", 100), col("INDICADOR", "texto", 150),
                       col("DETALHE", "texto", 260),
                       col("IMPACTO R$", "moeda", 110),
                       col("IMPACTO", "texto", 110),
                       col("LEITURA", "texto", 420)],
            lin_x, [c_["tom"] if c_["tom"] in ("ok", "atencao", "alerta")
                    else "" for c_ in vis_x["cartoes"]]))
    cols_g = [col("NOME", "texto", 200), col("DESAFIO", "moeda"),
              col("REAL", "moeda"), col("PROJEÇÃO", "moeda"),
              col("% PROJ.", "pct"), col("SALDO", "moeda"),
              col("CLIENTES", "int", 80), col("POSITIVAÇÃO", "int", 90),
              col("IPP", "num2", 60), col("VOLUME", "num", 80),
              col("MKP %", "pct1", 70), col("MKP R$", "moeda")]
    for chave, tit in (("filial", "Por filial"), ("categoria", "Por categoria"),
                       ("sistema", "Por sistema"),
                       ("familia", "Por família"), ("linha", "Por linha"),
                       ("segmento", "Por segmento")):
        g_ = grupos[chave]
        cs = [dict(cols_g[0], nome=g_["nome_col"])] + cols_g[1:]
        r["tabelas"].append(tabela(
            tit, cs, g_["linhas"], [_tom_ating(l[4]) for l in g_["linhas"]],
            total=g_["total"]))
    r["tabelas"] += [
        tabela("Vendedores", cols_v, lv, filtros=("SUPERVISOR",),
               total=tot_v),
        tabela("Clientes", cols_c, lc,
               [_tom_ating(l[9]) if l[6] else "" for l in lc],
               filtros=("UF", "CIDADE", "SEGMENTO", "VENDEDOR", "CURVA"),
               total=tot_cli(lc), kpis_de=cartoes_cli),
        tabela("Produtos", cols_p, lp,
               filtros=FILTROS_PRODUTO + ("CURVA",),
               total=tot_prod(lp), kpis_de=cartoes_prod),
        tabela("Mês a mês", cols_m, lm),
    ]
    for t_ in r["tabelas"]:             # o TOTAL segue o filtro da tela
        if t_["titulo"] == "Clientes" and t_.get("kpis_de") is cartoes_cli:
            t_["total_de"], t_["compacta"] = tot_cli, True
        elif t_["titulo"] == "Produtos" and t_.get("kpis_de") is cartoes_prod:
            t_["total_de"], t_["compacta"] = tot_prod, True
    if not com_c:
        r["avisos"].append("Sem custo (P. PEDIDO) para o markup.")
    # (16/10, Alexandre) UM PAINEL SO: os INDICADORES EXECUTIVOS (o
    # trimestre do mes escolhido) viram abas do Painel Executivo
    _executivos_no_painel(ctx, r)
    # (26/10, Alexandre) so as abas Resumo gerencial, Faturamento, Volume,
    # Produtividade, Positivacao, Itens por pedido, Markup, Preco e
    # Inadimplencia (as tabelas ficam so no Excel/PDF de todas as abas)
    try:
        _abas_do_painel(ctx, r, {
            "ano": ano, "mes": mes, "grupos": grupos, "itens": itens,
            "no_periodo": no_periodo, "vnd": vnd, "fator": fator,
            "custo": custo, "f_corre": f_corre, "meses": meses, "txt": txt,
            "tend": tend, "slim": slim, "meta_de": meta_de, "pv": pv,
            "lp": lp, "lm": lm, "tot_v": tot_v, "ac": ac, "mkp": mkp,
            "venda_c": venda_c, "custo_t": custo_t, "desc": desc,
            "g_fat": g_fat, "g_pos": g_pos, "g_tkm": g_tkm, "g_mkp": g_mkp,
            "painel_pre": r.get("painel_pre"),
            "vis_cartoes": (vis_x or {}).get("cartoes")})
    except Exception as erro:                           # noqa: BLE001
        r.pop("paineis", None)
        for t_ in r["tabelas"]:
            t_.pop("so_exportar", None)
        r["avisos"].append(f"Abas do Painel no formato antigo: {erro}")
    return r


NOMES_EXEC_NO_PAINEL = {"Fechamento dos trimestres": "Executivos · trimestres",
                        "Atingimento mês a mês": "Executivos · atingimento",
                        "Realizado mês a mês": "Executivos · realizado",
                        "Meta mês a mês": "Executivos · meta"}


def _executivos_no_painel(ctx, r):
    """As abas do Farol Indicadores Executivos dentro do Painel Executivo,
    com os cartoes do trimestre. O trimestre e o do MES escolhido (TODOS
    OS MESES: o de hoje). O cadastro (Metas executivas) e o Exportar para
    o RH ficam nos botoes da janela do painel."""
    try:
        _ano, mes_ = periodo(ctx)
        params = dict(ctx.params)
        if mes_ and not ctx.param("TRIMESTRE"):
            params["TRIMESTRE"] = (mes_ - 1) // 3 + 1
        c2 = Contexto(ctx.raiz, hoje=ctx.hoje, log=ctx.log, params=params)
        c2._b = ctx._b                  # os mesmos blocos ja carregados
        ex = indicadores_executivos(c2)
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Indicadores executivos: {erro}")
        return
    k_ex = list(ex.get("kpis") or [])
    for t_ in ex["tabelas"]:
        tit = t_["titulo"]
        if tit.endswith("trimestre"):
            tit = f"Executivos · {tit.replace('trimestre', 'tri')}"
        t_["titulo"] = NOMES_EXEC_NO_PAINEL.get(
            tit, tit if tit.startswith("Executivos") else f"Executivos · "
            f"{tit[:1].lower() + tit[1:]}")
        t_["kpis_de"] = (lambda _ls, k=k_ex: k)
        t_["executivo"] = True
    r["tabelas"] += ex["tabelas"]
    r["exec_tri"] = next((p_ for p_ in ex.get("parametros") or []
                          if p_["nome"] == "TRIMESTRE"), None)
    r["avisos"] += ex.get("avisos") or []


# =========================================================================
# (26/10, Alexandre) O PAINEL EXECUTIVO SO COM AS ABAS QUE ELE USA:
#   Resumo gerencial · Faturamento · Volume · Produtividade · Positivacao ·
#   Itens por pedido · Markup · Preco · Inadimplencia
# Cada aba e um painel (graficos e quadros) com os cartoes dela em cima.
# As tabelas de antes (Faróis, Por filial ... Executivos) saem da tela e
# ficam so no Excel/PDF de todas as abas (so_exportar).
# Produtividade, Preco e Inadimplencia sao os farois de Visita, Preco e
# Inadimplencia (da BAP inteira, no mes escolhido); as outras seguem os
# filtros de cima do Painel.
# =========================================================================
ABAS_DO_PAINEL = ("Resumo gerencial", "Faturamento", "Volume",
                  "Produtividade", "Positivação", "Itens por pedido",
                  "Markup", "Preço", "Inadimplência")
ALTURA_LINHA_PAINEL = 270


def _grade_painel(itens):
    """itens: [(bloco, largo, linhas)] -> o painel em 2 colunas (largo =
    as duas colunas; linhas = quantas linhas da grade o quadro ocupa)."""
    blocos, row, colu = [], 0, 0
    for b, largo, alto in itens:
        if largo:
            if colu:
                row, colu = row + 1, 0
            blocos.append(dict(b, col=0, row=row, colspan=2, rowspan=alto))
            row += alto
        else:
            blocos.append(dict(b, col=colu, row=row, rowspan=alto))
            colu += 1
            if colu == 2:
                row, colu = row + alto, 0
    n = row + (1 if colu else 0)
    return {"colunas": (1, 1), "altura_min": max(1, n) * ALTURA_LINHA_PAINEL,
            "blocos": blocos}


def _quadro(titulo, colunas, linhas, total=None):
    return {"tipo": "tabela", "titulo": titulo, "colunas": colunas,
            "linhas": linhas, "total": total, "compacta": True}


def _barras(g):
    return {"tipo": "barras", "grafico": g}


def _col_ating(nome="% PROJ."):
    return dict(col(nome, "pct", 70), chip=FAIXA_PCT_META, larg_fixa=70)


def _titulo_bloco(b):
    return b.get("titulo") or (b.get("grafico") or {}).get("titulo") or ""


def _blocos_por_titulo(painel, prefixos):
    """Os quadros de um painel de farol, na ordem dos prefixos do titulo."""
    saida = []
    blocos = (painel or {}).get("blocos") or []
    for pre in prefixos:
        b = next((b_ for b_ in blocos if _titulo_bloco(b_).startswith(pre)),
                 None)
        if b is not None:
            b = {k: v for k, v in b.items()
                 if k not in ("col", "row", "colspan", "rowspan")}
            saida.append(b)
    return saida


def _farol_do_mes(ctx, rid):
    """Um farol (da BAP inteira) no mesmo mes e ano do Painel, com os dados
    ja lidos; o Resumo gerencial padrao quando o farol nao tem painel."""
    funcao = POR_ID[rid][3]
    ano, mes = periodo(ctx)
    c2 = Contexto(ctx.raiz, hoje=ctx.hoje, log=ctx.log,
                  params={"MÊS": str(mes) if mes else TODOS_MESES,
                          "ANO": str(ano)})
    c2._b = ctx._b                                      # noqa: SLF001
    rel = funcao(c2)
    if rel.get("capa") and not rel.get("painel") and rid in PAINEIS_PADRAO:
        PAINEIS_PADRAO[rid](rel, c2)
    rel.pop("_eventos", None)
    rel.pop("_equipe", None)
    return rel


def _colunas_de(t, nomes):
    """Pega as colunas (pelo nome) de uma tabela de farol: (colunas, linhas,
    total)."""
    idx = {c["nome"]: j for j, c in enumerate(t["colunas"])}
    js = [idx[n] for n in nomes if n in idx]
    cols = [dict(t["colunas"][j], oculta=False) for j in js]
    linhas = [[l[j] for j in js] for l in t["linhas"]]
    tot = t.get("total")
    tot = [tot[j] if j < len(tot) else None for j in js] if tot else None
    return cols, linhas, tot


def _abas_do_painel(ctx, r, d):
    """Monta r["paineis"] (as 9 abas) e tira as tabelas da tela."""
    ano, mes = d["ano"], d["mes"]
    comp = f"{ano}-{mes:02d}" if mes else ""
    m3_p = set(_meses_antes(comp, 3)) if comp else set()
    grupos, itens, no_periodo = d["grupos"], d["itens"], d["no_periodo"]
    fator, custo = d["fator"], d["custo"]
    hoje = ctx.hoje
    corre = f"{hoje.year}-{hoje.month:02d}"
    f_corre = d["f_corre"]
    meses = d["meses"]
    rot_m = [MESES_CURTOS[int(m[5:])] for m in meses]
    filtro_txt = d["txt"]
    avisos_abas = []

    # ---- o mes a mes (do ano e dos 3 meses antes): volume, notas, pedidos
    def acc_mes():
        return {"real": 0.0, "vol": 0.0, "vol_ped": 0.0, "vol_hoje": 0.0,
                "nf": defaultdict(set), "ped": set(), "vnd": 0.0,
                "cli": defaultdict(float)}
    pm = defaultdict(acc_mes)
    alvo = set(meses) | m3_p
    for it in itens:
        dt_ = it["dt_nf"]
        if not dt_ or it["tipo"] not in ("VND", "DEV"):
            continue
        m = mes_de(dt_)
        if m not in alvo:
            continue
        x = pm[m]
        v = _liquido(it)
        x["real"] += v
        x["vol_hoje"] += _de_hoje(ctx, it, qtd=True)     # (06/11)
        x["cli"][it["cliente"]] += v
        if it["tipo"] == "VND":
            x["vol"] += it["qtd"] or 0
            if it.get("_ped"):
                x["vol_ped"] += it["qtd"] or 0
            x["nf"][(it["filial"], it["nf"])].add(it["cod"])
            x["ped"].add((it["filial"], it["pedido"]))
            x["vnd"] += it["valor"]
        else:
            x["vol"] -= abs(it["qtd"] or 0)

    def ipp_de(nfs):
        return (sum(len(v) for v in nfs.values()) / len(nfs)) if nfs \
            else None

    def media3(f):
        if not m3_p:
            return None
        return sum(f(pm[m]) for m in m3_p) / 3.0

    atual = pm[comp] if comp else acc_mes()
    if not comp:                        # TODOS OS MESES: o ano inteiro
        for m in meses:
            x = pm[m]
            atual["real"] += x["real"]
            atual["vol"] += x["vol"]
            atual["vnd"] += x["vnd"]
            atual["ped"] |= x["ped"]
            for k, v in x["nf"].items():
                atual["nf"][k] |= v
    vol = atual["vol"]
    vol_proj = (vol - atual["vol_ped"] - atual["vol_hoje"]) * fator \
        + atual["vol_ped"]
    m3_vol = media3(lambda x: x["vol"])
    m3_real = media3(lambda x: x["real"])
    nfs_at = atual["nf"]
    ipp = ipp_de(nfs_at)
    n_nf3 = sum(len(pm[m]["nf"]) for m in m3_p)
    ipp3 = (sum(sum(len(v) for v in pm[m]["nf"].values()) for m in m3_p)
            / n_nf3) if n_nf3 else None
    n_ped = len(atual["ped"])
    tk = atual["vnd"] / n_ped if n_ped else None
    n_ped3 = sum(len(pm[m]["ped"]) for m in m3_p)
    tk3 = (sum(pm[m]["vnd"] for m in m3_p) / n_ped3) if n_ped3 else None

    def var_de(a, b):
        return ((a / b - 1) * 100.0) if a is not None and b else None

    def tom_var(v):
        return "neutro" if v is None else "ok" if v >= 0 else "alerta"

    def sinal(v, casas=1):
        return "—" if v is None else \
            f"{'+' if v >= 0 else '−'}{br(abs(v), casas)}%"

    # ---- (03/11, Alexandre) MoM e M3M NAS TABELAS do Faturamento e do
    # Volume, em R$/unidades e em %: a PROJECAO do mes x o mes anterior
    # fechado (MoM) e x a media dos 3 meses anteriores (M3M) - a mesma
    # conta dos cartoes do Painel do Diretor
    m1_p = set(_meses_antes(comp, 1)) if comp else set()

    def comparativo(chave_de):
        """{chave: {"vol", "vped" (mes), "m1", "v1" (mes anterior),
        "m3", "v3" (soma dos 3 meses)}} pelos itens do filtro."""
        acc = defaultdict(lambda: {"vol": 0.0, "vped": 0.0, "vhoje": 0.0,
                                   "m1": 0.0, "v1": 0.0, "m3": 0.0,
                                   "v3": 0.0})
        if not comp:
            return acc
        for it in itens:
            dt_ = it["dt_nf"]
            if not dt_ or it["tipo"] not in ("VND", "DEV"):
                continue
            m = mes_de(dt_)
            if m != comp and m not in m3_p:
                continue
            x = acc[chave_de(it)]
            q = (it["qtd"] or 0) if it["tipo"] == "VND" else \
                -abs(it["qtd"] or 0)
            if m == comp:
                x["vol"] += q
                if it.get("_ped") and it["tipo"] == "VND":
                    x["vped"] += q
                x["vhoje"] += _de_hoje(ctx, it, qtd=True)   # (06/11)
                continue
            v = _liquido(it) or 0.0
            x["m3"] += v
            x["v3"] += q
            if m in m1_p:
                x["m1"] += v
                x["v1"] += q
        return acc

    def var_mm(proj, x, k1="m1", k3="m3"):
        """[MoM (dif.), MoM %, M3M (dif.), M3M %] da projecao."""
        if not comp or x is None or proj is None:
            return [None, None, None, None]
        b1, b3 = x[k1], x[k3] / 3.0
        return [proj - b1, var_de(proj, b1), proj - b3, var_de(proj, b3)]

    def vol_proj_de(x):
        return (x["vol"] - x["vped"] - x.get("vhoje", 0.0)) * fator \
            + x["vped"]

    def cols_mm(sufixo, tipo):
        return [col(f"MoM {sufixo}", tipo, 88), col("MoM %", "pct1", 64),
                col(f"M3M {sufixo}", tipo, 88), col("M3M %", "pct1", 64)]
    chave_grupo = {
        "filial": lambda it: ctx.filial(it["filial"]),
        "categoria": lambda it: ctx.categoria_bap(it["cod"]),
        "familia": lambda it: ctx.familia(it["cod"]),
        "segmento": lambda it: segmento_do_cliente(ctx, it["cliente"])}
    cmp_g = {g: comparativo(f_) for g, f_ in chave_grupo.items()}
    cmp_g["familia_top"] = cmp_g["familia"]
    cmp_tot = comparativo(lambda it: "TOTAL")["TOTAL"]
    cmp_v = comparativo(lambda it: _cod6(it.get("vend"))
                        if texto(it.get("vend")) else "")
    if comp:
        avisos_abas.append(
            "MoM e M3M nas tabelas (Faturamento e Volume): a projeção do "
            "mês x o mês anterior fechado (MoM) e x a média dos 3 meses "
            "anteriores (M3M), em R$/unidades e em %.")

    paineis = []

    # ======================= 1) RESUMO GERENCIAL =======================
    if d.get("painel_pre"):
        pn_res = d["painel_pre"]["painel"]
    else:                               # TODOS OS MESES: os graficos do ano
        pn_res = _grade_painel([(_barras(d["g_fat"]), True, 1),
                                (_barras(d["g_pos"]), False, 1),
                                (_barras(d["g_tkm"]), False, 1)])
    paineis.append({"titulo": "Resumo gerencial", "painel": pn_res,
                    "kpis": list(r["kpis"])})

    # ======================= 2) FATURAMENTO =======================
    def cols_fat(nome):
        return [col(nome, "texto", 170), col("DESAFIO", "moeda", 95),
                col("REAL", "moeda", 90), col("PROJEÇÃO", "moeda", 95),
                _col_ating()] + cols_mm("R$", "moeda")

    def quadro_fat(chave, titulo, linhas=None):
        g_ = grupos[chave]
        ls = linhas if linhas is not None else g_["linhas"]
        c_ = cmp_g.get(chave) or {}
        return _quadro(titulo, cols_fat(g_["nome_col"]),
                       [l[:5] + var_mm(l[3], c_.get(l[0])) for l in ls],
                       g_["total"][:5] + var_mm(g_["total"][3], cmp_tot))
    des_v = defaultdict(float)
    for c in d["slim"]:
        des_v[_cod6(c.get("cod_vendedor"))] += d["meta_de"](c) or 0.0
    pv = d["pv"]
    reais_v = {}
    for v, x in pv.items():
        k = _cod6(v)
        rv = reais_v.setdefault(k, [0.0, 0.0])
        rv[0] += x["real"]
        rv[1] += (x["real"] - x["ped"] - x.get("hoje", 0.0)) * fator \
            + x["ped"]
    lv_f, sup_f = [], defaultdict(lambda: [0.0, 0.0, 0.0])
    # o supervisor de hoje de cada vendedor, em todos os meses (quem saiu
    # entra no supervisor dele ou em "(SEM SUPERVISOR)")
    sup_c = comparativo(lambda it: ctx.supervisor_de(_cod6(it.get("vend")))
                        if texto(it.get("vend")) else "(SEM SUPERVISOR)")
    for k in sorted(set(reais_v) | {k for k, v in des_v.items() if v >= 0.5}):
        if not k:
            continue
        de_ = des_v.get(k) or None
        re_, pr_ = reais_v.get(k, (0.0, 0.0))
        x_c = cmp_v.get(k)
        lv_f.append([ctx.vendedor(k).split(" - ", 1)[-1], de_, re_, pr_,
                     pct_de(pr_, de_) if de_ else None]
                    + var_mm(pr_, x_c or {"m1": 0.0, "m3": 0.0}))
        s_ = sup_f[ctx.supervisor_de(k)]
        s_[0] += de_ or 0.0
        s_[1] += re_
        s_[2] += pr_
    lv_f.sort(key=lambda l: (-(l[1] or 0), -(l[2] or 0)))
    ls_f = sorted(([n, x[0] or None, x[1], x[2], pct_de(x[2], x[0])
                    if x[0] else None] + var_mm(x[2], sup_c.get(n) or
                                                {"m1": 0.0, "m3": 0.0})
                   for n, x in sup_f.items()),
                  key=lambda l: (-(l[1] or 0), -(l[2] or 0)))

    def tot_fat(ls):
        de_ = sum(l[1] or 0 for l in ls)
        pr_ = sum(l[3] or 0 for l in ls)
        # MoM/M3M do TOTAL: a BAP do filtro (o mesmo TOTAL das outras
        # tabelas; quem saiu da equipe entra no mes anterior)
        return ["TOTAL", de_ or None, sum(l[2] or 0 for l in ls), pr_,
                pct_de(pr_, de_) if de_ else None] + var_mm(pr_, cmp_tot)
    dev = sum(abs(it["valor"]) for it in no_periodo if it["tipo"] == "DEV")
    var_m3 = var_de(d["tend"], m3_real)
    k_res = {k["rotulo"]: k for k in r["kpis"]}
    kpis_fat = [k for k in r["kpis"] if k["rotulo"] not in
                ("Markup", "Desconto comercial")]
    pd_ = pct_do_liquido(dev, atual["real"])            # RN-GER-002
    kpis_fat += [
        kpi("M3M", moeda(m3_real) if m3_real is not None else "—",
            tom_var(var_m3), f"projeção {sinal(var_m3)} x média 3 meses"),
        kpi("Devoluções", moeda(dev), "atencao" if dev else "ok",
            f"{br(pd_, 1)}% do faturado" if pd_ is not None else "")]
    _ = k_res
    paineis.append({"titulo": "Faturamento", "kpis": kpis_fat,
                    "painel": _grade_painel([
                        (_barras(d["g_fat"]), True, 1),
                        (quadro_fat("filial", "Por filial"), True, 1),
                        (quadro_fat("categoria", "Por categoria"), True, 1),
                        (quadro_fat("familia", "Por família",
                                    grupos["familia_top"]["linhas"]),
                         True, 1),
                        (quadro_fat("segmento", "Por segmento"), True, 1),
                        (_quadro("Por vendedor", cols_fat("VENDEDOR"), lv_f,
                                 tot_fat(lv_f)), True, 1),
                        (_quadro("Por supervisor", cols_fat("SUPERVISOR"),
                                 ls_f, tot_fat(ls_f)), True, 1)])})

    # ======================= 3) VOLUME =======================
    vol_m = [pm[m]["vol"] for m in meses]
    vol_m_proj = [((pm[m]["vol"] - pm[m]["vol_ped"] - pm[m]["vol_hoje"])
                   * f_corre
                   + pm[m]["vol_ped"]) if m == corre else pm[m]["vol"]
                  for m in meses]
    _ = vol_m
    g_vol = {"titulo": f"Volume (unidades, projetado) · {ano}",
             "rotulos": rot_m,
             "series": [{"nome": "unidades", "cor": VERDE,
                         "valores": vol_m_proj,
                         "cores": ["#A9DBA9" if m == corre and f_corre > 1
                                   else VERDE for m in meses]}],
             "formato": "num", "rotular": True,
             "linha": {"nome": "% MoM", "valores": _mom(vol_m_proj)}}

    def cols_vol(nome):
        return [col(nome, "texto", 170), col("VOLUME", "num", 80),
                col("PROJEÇÃO", "num", 80),
                col("PART. %", "pct1", 66), col("R$", "moeda", 90),
                col("PREÇO MÉDIO", "moeda2", 90)] + cols_mm("UN.", "num")
    tot_vol = grupos["filial"]["total"][9] or 0.0

    def quadro_vol(chave, titulo, limite=None):
        g_ = grupos[chave]
        c_ = cmp_g.get(chave) or {}
        ls = sorted(g_["linhas"], key=lambda l: -(l[9] or 0))[:limite]
        lin = []
        for l in ls:
            if not (l[9] or l[2]):
                continue
            x_ = c_.get(l[0])
            vp_ = vol_proj_de(x_) if x_ else l[9]
            lin.append([l[0], l[9], vp_ if comp else None,
                        pct_de(l[9], tot_vol), l[2],
                        (l[2] / l[9]) if l[9] else None]
                       + var_mm(vp_, x_ or {"v1": 0.0, "v3": 0.0},
                                "v1", "v3"))
        if comp and (limite is None or len(lin) < limite):
            # (03/11) quem vendeu nos meses anteriores e nada no mes
            # aparece com volume 0, para o MoM/M3M das linhas fechar
            # com o do TOTAL
            ja = {l_[0] for l_ in lin}
            sobra = sorted(((k_, x2) for k_, x2 in c_.items()
                            if k_ and k_ not in ja
                            and (x2.get("v1") or x2.get("v3"))),
                           key=lambda kx: -(kx[1].get("v1") or 0))
            for k_, x2 in sobra[:(None if limite is None
                                  else limite - len(lin))]:
                vp_ = vol_proj_de(x2)
                lin.append([k_, 0.0, vp_, pct_de(0.0, tot_vol), 0.0, None]
                           + var_mm(vp_, x2, "v1", "v3"))
        t_ = g_["total"]
        vpt = vol_proj_de(cmp_tot)
        return _quadro(titulo, cols_vol(g_["nome_col"]), lin,
                       ["TOTAL", t_[9], vpt if comp else None,
                        100.0 if tot_vol else None, t_[2],
                        (t_[2] / t_[9]) if t_[9] else None]
                       + var_mm(vpt, cmp_tot, "v1", "v3"))
    lp = sorted((l for l in d["lp"] if l[6]), key=lambda l: -(l[6] or 0))
    top_p = [[l[0], l[1], l[2], l[6], l[5], l[9]] for l in lp[:15]]
    var_vol = var_de(vol_proj, m3_vol)
    pm_preco = (atual["real"] / vol) if vol else None
    pm3 = (m3_real / m3_vol) if m3_vol else None
    kpis_vol = [
        kpi("Volume", br(vol), "ok", "unidades líquidas (venda − devolução)"),
        kpi("Projeção", br(vol_proj), "info",
            "no ritmo de hoje" if fator > 1 else "mês fechado"),
        kpi("M3M", br(m3_vol) if m3_vol is not None else "—", "neutro",
            "média dos 3 meses anteriores"),
        kpi("Var. x M3M", sinal(var_vol), tom_var(var_vol),
            "projeção x média 3 meses"),
        kpi("Preço médio", moeda(pm_preco, 2) if pm_preco else "—", "neutro",
            f"M3M {moeda(pm3, 2)}" if pm3 else "R$ por unidade"),
        kpi("Produtos com venda", br(len(lp)), "neutro", "no mês")]
    paineis.append({"titulo": "Volume", "kpis": kpis_vol,
                    "painel": _grade_painel([
                        (_barras(g_vol), True, 1),
                        (quadro_vol("categoria", "Por categoria"), True, 1),
                        (quadro_vol("familia", "Por família (as 12 "
                                    "maiores)", 12), True, 1),
                        (quadro_vol("filial", "Por filial"), True, 1),
                        (quadro_vol("segmento", "Por segmento"), True, 1),
                        (_quadro("Os 15 produtos de maior volume",
                                 [col("PRODUTO", "texto", 120),
                                  col("DESCRIÇÃO", "texto", 380),
                                  col("CATEGORIA", "texto", 120),
                                  col("VOLUME", "num", 80),
                                  col("R$", "moeda", 90),
                                  col("PREÇO MÉDIO", "moeda2", 90)],
                                 top_p), True, 2)])})

    # ======================= 4) PRODUTIVIDADE =======================
    try:
        rv_ = _farol_do_mes(ctx, "vc_visitas")
        t_v = {t["titulo"]: t for t in rv_["tabelas"]}
        quer = ("Visitas", "Aderência", "Atendimento", "Início",
                "Jornada líquida", "Intervalo almoço")
        kpis_p = [k for k in rv_["kpis"] if k["rotulo"] != "Visitas por dia"
                  and any(k["rotulo"].startswith(q) for q in quer)]
        # (09/11, recado 20261109-1300) CAD., CAD. C/ COMPRA e PROSP.
        # sempre a vista nos indicadores de produtividade
        nomes_t = ["VENDEDOR", "META", "VISIT.", "% META", "% CONV.",
                   "% FORA DE ROTA", "CAD.", "CAD. C/ COMPRA", "PROSP.",
                   "INÍCIO", "ÚLT. ATIV.", "JORNADA LÍQ.",
                   "INTERV. ALMOÇO", "TMA", "TMD", "KM/CLIENTE"]
        itens_p = [(b, False, 1) for b in _blocos_por_titulo(
            rv_.get("painel"), ("Visitas dia a dia", "Visitas mês a mês",
                                "Início do 1º cliente dia a dia",
                                "Jornada (1º ao último cliente) dia a dia"))]
        for tit, nome_1 in (("Por supervisor", "SUPERVISOR"),
                            ("Por vendedor", "VENDEDOR")):
            t_ = t_v.get(tit)
            if not t_:
                continue
            cs, ls, tt = _colunas_de(t_, [nome_1] + nomes_t[1:])
            if tit == "Por vendedor":
                cs0, ls0, _t0 = _colunas_de(t_, ["SUPERVISOR"])
                cs, ls = cs0 + cs, [a + b for a, b in zip(ls0, ls)]
                tt = ([""] + tt) if tt else None
            itens_p.append((_quadro(tit, cs, ls, tt), True,
                            1 if tit == "Por supervisor" else 2))
        if t_v.get("Por supervisor") and t_v["Por supervisor"].get("total"):
            cs_, _l, tt_ = _colunas_de(t_v["Por supervisor"], ["% CONV."])
            if tt_ and tt_[0] is not None:
                kpis_p.insert(1, kpi("Conversão", p(tt_[0]), "neutro",
                                     "visitados que compraram"))
        paineis.append({"titulo": "Produtividade", "kpis": kpis_p,
                        "painel": _grade_painel(itens_p)})
    except Exception as erro:                           # noqa: BLE001
        avisos_abas.append(f"Produtividade (Farol de Visita): {erro}")
        paineis.append({"titulo": "Produtividade", "kpis": [],
                        "painel": _grade_painel([])})

    # ======================= 5) POSITIVACAO =======================
    ac = d["ac"] or {}
    rec = ac.get("recortes") or {}
    nomes_v = _nomes_vendedor(ac)
    esc_v, esc_s = ctx.param("VENDEDOR"), ctx.param("SUPERVISOR")

    def linha_pos(l, nome):
        mp, po = l.get("meta_positivacao"), l.get("positivados") or 0
        return [nome, mp or None, po, pct_de(po, mp) if mp else None,
                max(0.0, (mp or 0) - po) if mp else None]
    pos_v = []
    for l in rec.get("vendedor") or []:
        cod = _cod6(l.get("codigo") or l.get("chave"))
        if esc_v and _rotulo_vend(cod, nomes_v) != esc_v:
            continue
        if esc_s and texto(l.get("supervisor")) != esc_s:
            continue
        if not (l.get("meta_positivacao") or l.get("positivados")):
            continue
        pos_v.append(linha_pos(l, texto(l.get("nome") or l.get("rotulo"))))
    pos_v.sort(key=lambda l: (-(l[1] or 0), -(l[2] or 0)))
    pos_s = []
    for l in rec.get("supervisor") or []:
        nome_s = texto(l.get("nome") or l.get("rotulo"))
        if esc_s and esc_s not in nome_s:
            continue
        if not (l.get("meta_positivacao") or l.get("positivados")):
            continue
        pos_s.append(linha_pos(l, nome_s.split(" - ", 1)[-1]))
    pos_s.sort(key=lambda l: (-(l[1] or 0), -(l[2] or 0)))

    def tot_pos(ls):
        mp = sum(l[1] or 0 for l in ls)
        po = sum(l[2] or 0 for l in ls)
        return ["TOTAL", mp or None, po, pct_de(po, mp) if mp else None,
                sum(l[4] or 0 for l in ls) or None]
    cols_pos = [col("META POSIT.", "num", 86), col("POSITIVADOS", "int", 86),
                _col_ating("% ATING."), col("FALTA", "num", 66)]

    def quadro_cart(chave, titulo):
        g_ = grupos[chave]
        ls = [[l[0], l[6], l[7], pct_de(l[7], l[6]) if l[6] else None]
              for l in g_["linhas"] if l[6] or l[7]]
        ls.sort(key=lambda l: -(l[2] or 0))
        t_ = g_["total"]
        return _quadro(titulo, [col(g_["nome_col"], "texto", 170),
                                col("CARTEIRA", "int", 76),
                                col("POSITIVADOS", "int", 86),
                                col("% POSIT.", "pct1", 70)], ls,
                       ["TOTAL", t_[6], t_[7],
                        pct_de(t_[7], t_[6]) if t_[6] else None])
    tot_pv = tot_pos(pos_v)
    n_pos = d["tot_v"][5]
    cart = grupos["filial"]["total"][6]
    gap = d["lm"][mes - 1][3] if mes and mes <= len(d["lm"]) else None
    pos3 = media3(lambda x: sum(1 for v in x["cli"].values() if v > 0))
    novos = next((c_ for c_ in (d.get("vis_cartoes") or [])
                  if c_["farol"] == "Novos e reativados"), None)
    kpis_pos = [
        kpi("Positivados", br(n_pos), "ok",
            f"{br(pct_de(n_pos, cart) or 0, 1)}% da carteira ({br(cart)})"
            if cart else "clientes com compra no mês"),
        kpi("Meta de positivação", br(tot_pv[1]) if tot_pv[1] else "—",
            _tom_ating(tot_pv[3]) or "neutro",
            f"ating. {p(tot_pv[3])} · falta {br(tot_pv[4] or 0)}"
            if tot_pv[1] else "sem meta no Farol de Metas"),
        kpi("M3M", br(pos3) if pos3 is not None else "—", "neutro",
            "positivados por mês (3 meses)"),
        kpi("Gap", br(gap) if gap is not None else "—",
            "atencao" if gap else "neutro",
            "compraram no ano e não no mês"),
        kpi("Novos e reativados", novos["valor"] if novos else "—",
            "ok" if novos and novos["valor"] not in ("0", "—") else "neutro",
            "sem compra nos 12 meses antes")]
    itens_pos = [(_barras(d["g_pos"]), True, 1)]
    if grupos.get("posit_segmento", {}).get("rotulos"):
        itens_pos += [(_barras(grupos["posit_segmento"]), False, 1),
                      (_barras(grupos["posit_categoria"]), False, 1)]
    itens_pos += [
        (_quadro("Por vendedor · meta do Farol de Metas",
                 [col("VENDEDOR", "texto", 210)] + cols_pos, pos_v,
                 tot_pv), False, 1),
        (_quadro("Por supervisor · meta do Farol de Metas",
                 [col("SUPERVISOR", "texto", 210)] + cols_pos, pos_s,
                 tot_pos(pos_s)), False, 1),
        (quadro_cart("filial", "Por filial · carteira"), False, 1),
        (quadro_cart("segmento", "Por segmento · carteira"), False, 1)]
    paineis.append({"titulo": "Positivação", "kpis": kpis_pos,
                    "painel": _grade_painel(itens_pos)})

    # ======================= 6) ITENS POR PEDIDO =======================
    ipp_m = [ipp_de(pm[m]["nf"]) or 0.0 for m in meses]
    g_ipp = {"titulo": f"Itens por pedido (SKU por nota) · {ano}",
             "rotulos": rot_m,
             "series": [{"nome": "IPP", "cor": VERDE, "valores": ipp_m}],
             "formato": "num1", "rotular": True,
             "subrotulos": [f"{br(len(pm[m]['nf']))} nf" for m in meses],
             "linha": {"nome": "% MoM", "valores": _mom(ipp_m)}}
    g_tk = dict(d["g_tkm"], titulo=f"Ticket médio por pedido · {ano}")
    g_tk.pop("subrotulos", None)

    def ipp_por(chave_de):
        acc = defaultdict(lambda: {"nf": defaultdict(set), "ped": set(),
                                   "vnd": 0.0})
        for it in no_periodo:
            if it["tipo"] != "VND":
                continue
            x = acc[chave_de(it)]
            x["nf"][(it["filial"], it["nf"])].add(it["cod"])
            x["ped"].add((it["filial"], it["pedido"]))
            x["vnd"] += it["valor"]
        ls = [[k, len(x["nf"]), ipp_de(x["nf"]),
               x["vnd"] / len(x["ped"]) if x["ped"] else None]
              for k, x in acc.items()]
        ls.sort(key=lambda l: -(l[1] or 0))
        return ls

    def quadro_ipp(titulo, nome, ls):
        return _quadro(titulo, [col(nome, "texto", 190),
                                col("NOTAS", "int", 60),
                                col("IPP", "num2", 60),
                                col("TICKET", "moeda", 90)], ls,
                       ["TOTAL", len(nfs_at), ipp, tk])
    var_ipp, var_tk = var_de(ipp, ipp3), var_de(tk, tk3)
    kpis_ipp = [
        kpi("Itens por pedido", br(ipp or 0, 2), tom_var(var_ipp),
            f"SKU por nota · M3M {br(ipp3 or 0, 2)} ({sinal(var_ipp)})"),
        kpi("Ticket por pedido", moeda(tk) if tk else "—", tom_var(var_tk),
            f"M3M {moeda(tk3)} ({sinal(var_tk)})" if tk3 else ""),
        kpi("Notas", br(len(nfs_at)), "neutro", "notas de venda no mês"),
        kpi("Pedidos", br(n_ped), "neutro", "pedidos faturados no mês")]
    paineis.append({"titulo": "Itens por pedido", "kpis": kpis_ipp,
                    "painel": _grade_painel([
                        (_barras(g_ipp), False, 1),
                        (_barras(g_tk), False, 1),
                        (quadro_ipp("Por categoria", "CATEGORIA", ipp_por(
                            lambda it: ctx.categoria_bap(it["cod"]))),
                         False, 1),
                        (quadro_ipp("Por segmento", "SEGMENTO", ipp_por(
                            lambda it: segmento_do_cliente(
                                ctx, it["cliente"]))), False, 1),
                        (quadro_ipp("Por vendedor", "VENDEDOR", ipp_por(
                            lambda it: ctx.vendedor(it.get("vend") or "")
                            .split(" - ", 1)[-1])), False, 1),
                        (quadro_ipp("Por filial", "FILIAL", ipp_por(
                            lambda it: ctx.filial(it["filial"]))),
                         False, 1)])})

    # ======================= 7) MARKUP =======================
    def cols_mkp(nome):
        return [col(nome, "texto", 170), col("FATURADO", "moeda", 95),
                col("MKP %", "pct1", 66), col("MKP R$", "moeda", 90)]

    def quadro_mkp(chave, titulo):
        g_ = grupos[chave]
        ls = [[l[0], l[2], l[10], l[11]] for l in g_["linhas"] if l[2]]
        ls.sort(key=lambda l: -(l[3] or 0))
        t_ = g_["total"]
        return _quadro(titulo, cols_mkp(g_["nome_col"]), ls,
                       ["TOTAL", t_[2], t_[10], t_[11]])
    mv = []
    for v, x in pv.items():
        if x["real"] or x["vc"]:
            mv.append([ctx.vendedor(v).split(" - ", 1)[-1], x["real"],
                       _mkp(x["vc"], x["cu"]),
                       (x["vc"] - x["cu"]) if x["cu"] else None])
    mv.sort(key=lambda l: -(l[3] or 0))
    sem_c = [it for it in d["vnd"] if not custo(it)]
    v_sem = sum(it["valor"] for it in sem_c)
    mkp, venda_c, custo_t = d["mkp"], d["venda_c"], d["custo_t"]
    kpis_mkp = [
        kpi("Markup", "—" if mkp is None else f"{br(mkp, 1)}%",
            "ok" if (mkp or 0) >= 15 else "alerta" if mkp is not None
            else "neutro", "venda ÷ custo − 1 (custo com a sucata)"),
        kpi("Margem", moeda(venda_c - custo_t), "ok"
            if venda_c > custo_t else "alerta", "venda − custo"),
        kpi("Venda com custo", moeda(venda_c), "neutro",
            f"custo {moeda(custo_t)}"),
        kpi("Venda sem custo", moeda(v_sem), "atencao" if v_sem else "ok",
            f"{br(len({it['cod'] for it in sem_c}))} produtos sem P. PEDIDO"),
        kpi("Desconto comercial", p(d["desc"]), "neutro", "sem o financeiro")]
    paineis.append({"titulo": "Markup", "kpis": kpis_mkp,
                    "painel": _grade_painel([
                        (_barras(d["g_mkp"]), True, 1),
                        (quadro_mkp("categoria", "Por categoria"), False, 1),
                        (quadro_mkp("filial", "Por filial"), False, 1),
                        (quadro_mkp("familia", "Por família"), False, 1),
                        (quadro_mkp("segmento", "Por segmento"), False, 1),
                        (_quadro("Por vendedor", cols_mkp("VENDEDOR"), mv,
                                 ["TOTAL", sum(l[1] for l in mv), mkp,
                                  venda_c - custo_t]), True, 1)])})

    # ======================= 8) PRECO e 9) INADIMPLENCIA =======================
    for rid, tit, prefixos in (
            ("vc_preco", "Preço", (
                "O que o farol diz", "Preço de tabela (R$) x volume",
                "Variação % do preço de tabela", "Efeito preço por categoria",
                "Variação % x mês anterior", "Variação da tabela por família")),
            ("pl_inadimplencia", "Inadimplência", (
                "O que o farol diz", "Carteira em aberto por faixa",
                "Em atraso (R$, última foto) · mês a mês",
                "Por filial: em atraso", "Em atraso por vendedor",
                "Recebido (R$) · mês a mês"))):
        try:
            rf = _farol_do_mes(ctx, rid)
            for b in (rf.get("painel") or {}).get("blocos") or []:
                if b["tipo"] == "insights":     # o que cabe no quadro
                    b["linhas"] = list(b.get("linhas") or [])[:6]
            paineis.append({"titulo": tit, "kpis": list(rf["kpis"]),
                            "painel": _grade_painel(
                                [(b, False, 1) for b in _blocos_por_titulo(
                                    rf.get("painel"), prefixos)])})
        except Exception as erro:                       # noqa: BLE001
            avisos_abas.append(f"{tit}: {erro}")
            paineis.append({"titulo": tit, "kpis": [],
                            "painel": _grade_painel([])})
    # (29/10, Alexandre + analista) PAINEL DO DIRETOR: a 1a aba, uma tela
    # so com os 16 cartoes (painel_diretor.py). A BAP inteira (os filtros de
    # cima nao valem aqui); so com um mes escolhido.
    if mes:
        try:
            import painel_diretor as pdr                # noqa: PLC0415
            dd = pdr.calcular(ctx, ano, mes)
            # (10/11, Alexandre: "A") a aba antiga "Painel do Diretor" (16
            # cartoes + leitura/acoes/compromisso) SAI: o Painel do Diretor
            # sao as 3 abas no modelo da RRM (abaixo); o calculo continua
            # (base dos cartoes e do historico do mes)
            avisos_abas += [f"Painel do Diretor · {a_}"
                            for a_ in dd.get("avisos") or []]
        except Exception as erro:                       # noqa: BLE001
            dd = None
            avisos_abas.append(f"Painel do Diretor: {erro}")
        # (06/11, recado 20261106-1524 do Maestro Comercial) o Painel em
        # cartoes com barras, o formato do RRM do Diretor: a visao absoluta
        # (15 cartoes) e a por dia util (6), logo depois do Painel do
        # Diretor; a BAP inteira, como ele (os filtros de cima nao valem)
        # (10/11, recado 20261109-1345) as abas viram o modelo da RRM:
        # resultado (10 cartoes), produtividade (10) e por dia util (6),
        # com circulos MTD/MES, faixa mes anterior/anterior/julho e barras
        # por estado (painel_rrm.py)
        if dd is not None:
            try:
                import painel_cartoes as pcx            # noqa: PLC0415
                import painel_rrm as prm                # noqa: PLC0415
                dc = pcx.calcular(ctx, ano, mes, dd,
                                  dist=pcx.dist_rrm(mes))
                dr = prm.calcular(ctx, ano, mes, dd, dc)
                for i_, (vis_, tit_) in enumerate(prm.VISOES):
                    paineis.insert(i_, {
                        "titulo": tit_, "kpis": [],
                        "diretor": dd if vis_ == "res" else None,
                        "kpis_export": prm.kpis(dr, vis_),
                        "painel": {"blocos": [{
                            "tipo": "rrm", "dados": dr, "visao": vis_,
                            "row": 0, "col": 0, "colspan": 3}],
                            "altura_min": prm.ALTURA_MIN.get(vis_, 720)}})
                avisos_abas += [f"Painel em cartões · {a_}"
                                for a_ in dc.get("avisos") or []
                                if a_ not in (dd.get("avisos") or [])]
            except Exception as erro:                   # noqa: BLE001
                avisos_abas.append(f"Painel em cartões: {erro}")
    r["paineis"] = paineis
    for t in r["tabelas"]:
        t["so_exportar"] = True
    if filtro_txt:
        avisos_abas.append("Produtividade, Preço e Inadimplência são da BAP "
                           "inteira (os filtros de cima valem para "
                           "Faturamento, Volume, Positivação, Itens por "
                           "pedido e Markup). Positivação por vendedor e "
                           "supervisor: a meta do Farol de Metas.")
    r["avisos"] += avisos_abas


def _kpi_pedidos(ctx, abertos, somando):
    """(06/10) O cartao PEDIDOS EM ABERTO do Painel Executivo: valor,
    quantos pedidos, clientes, itens, ticket e atrasados (no filtro)."""
    peds = defaultdict(list)
    for it in abertos:
        peds[(it["filial"], it["pedido"])].append(it)
    valor = sum(it["valor"] for it in abertos)
    n = len(peds)
    atras = 0
    for its in peds.values():
        prazo = ctx.mais_uteis(its[0]["dt_pedido"], bd.PRAZO_FATURAR)
        if prazo and ctx.hoje > prazo:
            atras += 1
    return kpi("Pedidos em aberto", moeda(valor), "info" if n else "neutro",
               ("somados ao real" if somando else
                "não somados ao real") if n else "nenhum pedido em aberto",
               [("Pedidos", br(n), ""),
                ("Clientes", br(len({it["cliente"] for it in abertos})), ""),
                ("Ticket", moeda(valor / n) if n else "—", ""),
                ("Atrasados", br(atras), "alerta" if atras else "")])


def _painel_grupos(ctx, no_periodo, custo, fator, ano, mes, ac, slim,
                   meta_de, item_ok):
    """Os quadros do Painel Executivo por FILIAL, CATEGORIA, FAMILIA e
    SEGMENTO: [nome, meta, real, projecao, % proj., positivacao, IPP,
    volume, mkp %, mkp R$]. Meta: a do Gerador (categoria e familia: a meta
    comercial aberta pelo mix; segmento: a soma dos clientes; filial: a
    soma dos clientes pela filial que mais vendeu para cada um em 12 meses -
    sem historico, a filial da UF). E a positivacao por segmento e por
    categoria contra o mes passado."""
    def segmento(cod):          # (12/10) o mesmo de todos os farois
        return segmento_do_cliente(ctx, cod)
    comp = f"{ano}-{mes:02d}" if mes else ""
    janela = set(_meses_antes(comp, 12)) | {comp} if comp else set()
    fil_cli = defaultdict(lambda: defaultdict(float))
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND" and it["dt_nf"] and mes_de(it["dt_nf"]) in janela:
            fil_cli[it["cliente"]][ctx.filial(it["filial"])] += it["valor"]

    def filial_do_cliente(c):
        f = fil_cli.get(c["cod_cliente"])
        if f:
            return max(f.items(), key=lambda kv: kv[1])[0]
        return FILIAL_DA_UF.get(texto(c.get("uf")), texto(c.get("uf")) or "?")
    metas = {g: defaultdict(float) for g in ("filial", "segmento",
                                            "categoria", "sistema",
                                            "familia", "linha")}
    sem_meta = set()
    # CLIENTES (a carteira de cada linha): filial e segmento, os clientes
    # dela; categoria e familia, os que tem meta nela
    carteira = {g: defaultdict(set) for g in metas}
    for c in slim:
        cod = c["cod_cliente"]
        f_c = filial_do_cliente(c)
        s_c = c.get("segmento") or "(SEM SEGMENTO)"
        metas["filial"][f_c] += meta_de(c) or 0.0
        metas["segmento"][s_c] += meta_de(c) or 0.0
        # (12/10) CLIENTES: a carteira sem os inativados (= Farol de Metas)
        na_cart = not ctx.inativo(cod, c.get("loja"))
        if na_cart:
            carteira["filial"][f_c].add(cod)
            carteira["segmento"][s_c].add(cod)
        for g, campo in (("categoria", "meta_categoria"),
                         ("sistema", "meta_sistema"),
                         ("familia", "meta_familia"),
                         ("linha", "meta_linha")):
            for k, v_c in (c.get(campo) or {}).items():
                v = meta_de(c, g, k)
                if v is None:
                    sem_meta.add(g)
                    if (v_c or 0) > 0 and na_cart:
                        carteira[g][k].add(cod)
                else:
                    metas[g][k] += v
                    if v > 0 and na_cart:
                        carteira[g][k].add(cod)
    chave_de = {"filial": lambda it: ctx.filial(it["filial"]),
                "categoria": lambda it: ctx.categoria_bap(it["cod"]),
                "sistema": lambda it: ctx.sistema(it["cod"]),
                "familia": lambda it: ctx.familia(it["cod"]),
                "linha": lambda it: ctx.linha(it["cod"]),
                "segmento": lambda it: segmento(it["cliente"])}
    nomes = {"filial": ("Por filial", "FILIAL"),
             "categoria": ("Por categoria", "CATEGORIA"),
             "sistema": ("Por sistema", "SISTEMA"),
             "familia": ("Por família", "FAMÍLIA"),
             "linha": ("Por linha", "LINHA"),
             "segmento": ("Por segmento", "SEGMENTO")}

    def novo_acc():
        return {"real": 0.0, "vc": 0.0, "cu": 0.0, "cli": set(),
                "nf": defaultdict(set), "vol": 0.0, "tab": 0.0, "venda": 0.0,
                "ped": 0.0, "saldo": 0.0, "hoje": 0.0}

    def linha(nome, x, m_, cart=()):
        # pedido: inteiro; (06/11) a nota de hoje: fora da projecao
        pr = (x["real"] - x["ped"] - x["hoje"]) * fator + x["ped"]
        nfs = x["nf"]
        return [nome, m_, x["real"], pr,
                pct_de(pr, m_) if m_ else None,
                # SALDO: o do Farol de Saldo (tabela x 15% - desconto dado)
                x["saldo"] if x["tab"] else None,      # (13/10) regra nova
                len(cart),                       # CLIENTES (carteira)
                len(x["cli"]),
                (sum(len(v) for v in nfs.values()) / len(nfs)) if nfs
                else None, x["vol"], _mkp(x["vc"], x["cu"]),
                (x["vc"] - x["cu"]) if x["cu"] else None]

    def juntar(xs):
        t = novo_acc()
        for x in xs:
            for k in ("real", "vc", "cu", "vol", "tab", "venda", "ped",
                      "saldo", "hoje"):
                t[k] += x[k]
            t["cli"] |= x["cli"]
            for k, v in x["nf"].items():
                t["nf"][k] |= v
        return t
    saida = {}
    for g, f_ in chave_de.items():
        acc = defaultdict(novo_acc)
        for it in no_periodo:
            x = acc[f_(it)]
            x["real"] += _liquido(it) or 0.0
            x["hoje"] += _de_hoje(ctx, it)
            if it.get("_ped"):
                x["ped"] += it["valor"]
            if it["tipo"] == "VND":
                if it.get("_ped") or positivou(ctx, it["cliente"],
                                               it["dt_nf"]):
                    x["cli"].add(it["cliente"])
                x["nf"][(it["filial"], it["nf"])].add(it["cod"])
                x["vol"] += it["qtd"] or 0
                x["tab"] += (it["p_tab"] * it["qtd"] if it["p_tab"] > 0
                             else it["valor"])
                x["venda"] += it["valor"]
                if not it.get("_ped"):
                    x["saldo"] += saldo_do_item(ctx, it)
                if custo(it):
                    x["vc"] += it["valor"]
                    x["cu"] += custo(it)
            else:
                x["vol"] -= abs(it["qtd"] or 0)
        so_meta = g in sem_meta
        chaves = set(acc) | {k for k, v in metas[g].items() if v >= 0.5}
        # (12/10) toda linha que tem cliente aparece (INDUSTRIA, sem meta e
        # sem venda, entrava no TOTAL de CLIENTES e nao tinha linha)
        chaves |= {k for k, v in carteira[g].items() if v}
        if g == "categoria":
            chaves = set(chaves) | set(mn_categorias())
        linhas = []
        for k in chaves:
            m_ = None if so_meta else (metas[g].get(k) or None)
            linhas.append(linha(k, acc.get(k) or novo_acc(), m_,
                                carteira[g].get(k, ())))
        # SEMPRE da maior meta para a menor (sem meta: pela projecao)
        linhas.sort(key=lambda l: (-(l[1] or 0), -(l[3] or 0), str(l[0])))
        tm = sum(l[1] or 0 for l in linhas)
        tot = linha("TOTAL", juntar(acc.values()), tm or None,
                    set().union(*carteira[g].values()) if carteira[g]
                    else ())
        saida[g] = {"titulo": nomes[g][0], "nome_col": nomes[g][1],
                    "linhas": linhas, "total": tot}
        if g == "familia":           # o quadro: as 6 maiores + DEMAIS
            top = [l[0] for l in linhas[:6]]
            resto = [l[0] for l in linhas[6:]]
            ls = list(linhas[:6])
            if len(resto) > 1:
                m_r = sum(l[1] or 0 for l in linhas[6:])
                ls.append(linha(f"DEMAIS ({len(resto)})",
                                juntar(acc[k] for k in resto if k in acc),
                                None if so_meta else (m_r or None),
                                set().union(*(carteira[g].get(k, set())
                                              for k in resto))))
            elif resto:
                ls = linhas
            _ = top
            saida["familia_top"] = dict(saida[g], linhas=ls)
    # positivacao por segmento e por categoria: este mes x o passado
    if mes:
        ant = _meses_antes(comp, 1)[0]
        cli = {comp: defaultdict(set), ant: defaultdict(set)}
        cli_c = {comp: defaultdict(set), ant: defaultdict(set)}
        for it in ctx.tabela["itens"]:
            if it["tipo"] != "VND" or not it["dt_nf"]:
                continue
            m = mes_de(it["dt_nf"])
            if m in cli and item_ok(it) and positivou(ctx, it["cliente"], m):
                cli[m][segmento(it["cliente"])].add(it["cliente"])
                cli_c[m][ctx.categoria_bap(it["cod"])].add(it["cliente"])
        rot_a, rot_m = rotulo_mes(ant), rotulo_mes(comp)

        def graf(titulo, dic, ordem):
            ks = ordem or sorted(set(dic[comp]) | set(dic[ant]),
                                 key=lambda k: -len(dic[ant].get(k, ())))
            return {"titulo": titulo, "rotulos": [_curto_seg(k) for k in ks],
                    "series": [{"nome": rot_a, "cor": "#C9D3CC",
                                "valores": [len(dic[ant].get(k, ()))
                                            for k in ks]},
                               {"nome": rot_m, "cor": VERDE,
                                "valores": [len(dic[comp].get(k, ()))
                                            for k in ks]}],
                    "formato": "num", "rotular": True}
        saida["posit_segmento"] = graf(
            "Positivação por segmento · mês atual x passado", cli, None)
        saida["posit_categoria"] = graf(
            "Positivação por categoria · mês atual x passado", cli_c,
            [k for k in mn_categorias()])
    else:
        vazio = {"titulo": "Positivação (escolha um mês)", "rotulos": [],
                 "series": [], "formato": "num"}
        saida["posit_segmento"] = saida["posit_categoria"] = vazio
    return saida


def _curto_seg(nome) -> str:
    """O rotulo curto embaixo da coluna (segmento e categoria)."""
    return {"DISTRIBUIDOR DE BATERIAS": "DISTR. BAT.",
            "POSTO E TROCA DE ÓLEO": "POSTO",
            "FROTISTA/REVENDEDOR": "FROTISTA",
            "(FORA DA BASE)": "FORA BASE", FORA_PLANNER_META: "FORA PLANNER",
            "AUTOCENTER": "AUTOCENTER",
            "OFICINA MECÂNICA": "OFICINA",
            "LUBRIFICANTES": "LUBRIFIC."}.get(str(nome), str(nome))


def farol_markup(ctx):
    """
    Farol de Markup: o markup de cada pedido (faturado no periodo e em
    aberto), com o custo do BAP Tools (P. PEDIDO do ESTOQUE_BAP) e, na
    bateria, a sucata somada ao custo.
        MARKUP = venda / custo - 1      (so os itens que tem custo)
    Visoes: pedido, UF, cidade, supervisor, vendedor, familia, categoria e
    produto.
    """
    hoje = ctx.hoje
    com = ctx.comercial
    mkp_bat = float((com.get("kit") or {}).get("markup_min_bateria")
                    or MARKUP_MIN)
    r = novo("vc_markup", ANA, "Farol de Markup",
             f"Markup = venda ÷ custo − 1 · mínimo {br(MARKUP_MIN)}% "
             f"(bateria {br(mkp_bat)}%, com sucata)",
             "TABELA_BAP › ftPedidos + ftEstoquePMZ (P. PEDIDO) + "
             "sucata do Oportunidades")
    capa(r, ctx, anos_dos_dados(ctx))
    # (07/10) FILIAL: vale para todas as abas (e para os graficos)
    fil_esc = ctx.param("FILIAL")
    if fil_esc in (None, "", TODOS_RECORTE):
        fil_esc = None
    filiais = sorted(set((ctx.tabela.get("filiais") or {}).values()))
    if fil_esc and fil_esc not in filiais:
        filiais.append(fil_esc)
    r["parametros"].append({"nome": "FILIAL",
                            "valores": [TODOS_RECORTE] + filiais,
                            "valor": fil_esc or TODOS_RECORTE})
    if fil_esc:
        r["subtitulo"] += f" · Filial {fil_esc}"
    if not com["custos"]:
        r["avisos"].append("Sem P. PEDIDO na TABELA_BAP: sem custo não há "
                           "markup.")
    # ---- os itens do periodo -------------------------------------------
    itens = []          # (it, data, situacao, venda, tab, tab_c, custo, suc)
    eventos = []
    abertos_no_periodo = no_mes(ctx, hoje)
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND":
            d = it["dt_nf"]
            sit = "FATURADO"
        elif it["tipo"] == "VEA":
            d = it["dt_pedido"]
            sit = "EM ABERTO"
        else:
            continue
        if fil_esc and ctx.filial(it["filial"]) != fil_esc:
            continue
        custo_u, suc_u, origem = _custo_do_item(ctx, it)
        custo = (custo_u + suc_u) * it["qtd"]
        if it["tipo"] == "VND" and custo:
            eventos.append((d, it["valor"], custo))
        if it["tipo"] == "VND" and not no_mes(ctx, d):
            continue
        if it["tipo"] == "VEA" and not abertos_no_periodo:
            continue
        tab = it["p_tab"] * it["qtd"] if it["p_tab"] > 0 else it["valor"]
        itens.append({"it": it, "data": d, "sit": sit, "venda": it["valor"],
                      "tab": tab, "tab_c": base_do_item(ctx, it)[0],
                      "custo": custo,
                      "sucata": suc_u * it["qtd"], "origem": origem,
                      "cat": _categoria(ctx, it["cod"])})
    rec = [x for x in itens if x["origem"].startswith("ÚLTIMO")]
    if rec:
        r["avisos"].append(
            f"{br(len(rec))} itens com P. PEDIDO zerado no relatório do BAP "
            f"Tools: usado o último custo conhecido "
            f"({rec[0]['origem'].split()[-1]})")
    graficos_tempo(r, ctx, "Markup (%)", eventos, "pct", VERDE,
                   lambda vs: _mkp(sum(v[0] for v in vs),
                                   sum(v[1] for v in vs)) or 0)

    def somar(grupo):
        com_c = [x for x in grupo if x["custo"]]
        venda_c = sum(x["venda"] for x in com_c)
        custo = sum(x["custo"] for x in com_c)
        tab_c = sum(x["tab"] for x in com_c)
        venda = sum(x["venda"] for x in grupo)
        tabc = sum(x["tab_c"] for x in grupo)
        return {"venda": venda, "custo": custo,
                "sucata": sum(x["sucata"] for x in com_c),
                "margem": venda_c - custo if com_c else None,
                "mkp": _mkp(venda_c, custo), "mkp_tab": _mkp(tab_c, custo),
                "desc": (1 - venda / tabc) * 100.0 if tabc else None,
                "qtd": sum(x["it"]["qtd"] for x in grupo),
                "sem": sum(1 for x in grupo if not x["custo"]),
                "venda_sem": sum(x["venda"] for x in grupo if not x["custo"]),
                "bateria": bool(grupo) and all(x["cat"] == "BATERIAS"
                                               for x in grupo)}

    def tom(s, minimo=None):
        if s["mkp"] is None:
            return "cinza"
        m = minimo if minimo is not None else (mkp_bat if s["bateria"]
                                               else MARKUP_MIN)
        return "alerta" if s["mkp"] < 0 else ("atencao" if s["mkp"] < m
                                               else "ok")
    # ---- por pedido (uma linha por nota faturada / pedido em aberto) ----
    grupos = defaultdict(list)
    for x in itens:
        it = x["it"]
        k = (x["sit"], it["filial"], it["pedido"],
             it["nf"] if x["sit"] == "FATURADO" else "")
        grupos[k].append(x)
    lp, tp = [], []
    for (sit, fil, ped, nf), g in grupos.items():
        it = g[0]["it"]
        cli = ctx.cliente(it["cliente"])
        s = somar(g)
        lp.append([sit, it["dt_pedido"], g[0]["data"] if sit == "FATURADO"
                   else None, ctx.filial(fil), ped, nf.lstrip("0"),
                   ctx.nome_cliente(it["cliente"]), cli.get("uf", ""),
                   cli.get("cidade", ""), ctx.supervisor_de(it["vend"]),
                   ctx.vendedor(it["vend"]), s["qtd"], s["venda"], s["custo"],
                   s["sucata"], s["margem"], s["mkp"], s["mkp_tab"], s["desc"],
                   s["sem"], s["venda_sem"], s["bateria"]]
                  # (13/10) a autorizacao de venda (Farol de Pedidos)
                  + [(autorizacoes_de_venda(ctx).get(chave_pedido(fil, ped))
                      or {}).get(k_, "") for k_ in ("codigo", "por")])
        tp.append(tom(s))
    juntos = sorted(zip(lp, tp), key=lambda z: (z[0][16] is None,
                                                z[0][16] or 0))
    lp, tp = [z[0] for z in juntos], [z[1] for z in juntos]

    def cartoes(ls):
        # (14/10) AUDITORIA: os numeros sao do FATURADO (= Painel Executivo,
        # Farol de Pedidos e Saldo); o pedido em aberto tem cartao proprio
        ab = [l for l in ls if l[0] != "FATURADO"]
        ls = [l for l in ls if l[0] == "FATURADO"]
        venda = sum(l[12] for l in ls)
        venda_c = sum(l[12] - l[20] for l in ls)
        custo = sum(l[13] for l in ls)
        margem = venda_c - custo
        mkp = _mkp(venda_c, custo)
        abaixo = sum(1 for l in ls if l[16] is not None and l[16] < (
            mkp_bat if l[21] else MARKUP_MIN))
        sem = sum(l[19] for l in ls)
        mkp_ab = _mkp(sum(l[12] - l[20] for l in ab), sum(l[13] for l in ab))
        extra = [kpi("Em aberto", moeda(sum(l[12] for l in ab)), "info",
                     f"{br(len({(l[3], l[4]) for l in ab}))} pedidos · "
                     f"markup {'—' if mkp_ab is None else br(mkp_ab, 1)}%")
                 ] if ab else []
        return [
            kpi("Venda", moeda(venda), "neutro",
                f"{br(len({(l[3], l[4]) for l in ls}))} pedidos"),
            kpi("Custo", moeda(custo), "neutro",
                f"sucata {moeda(sum(l[14] for l in ls))}"),
            kpi("Margem", moeda(margem), "ok" if margem >= 0 else "alerta"),
            kpi("Markup", "—" if mkp is None else f"{br(mkp, 1)}%",
                "alerta" if (mkp or 0) < MARKUP_MIN else "ok",
                f"mínimo {br(MARKUP_MIN)}%"),
            kpi("Abaixo do mínimo", br(abaixo), "atencao" if abaixo else "ok",
                "pedidos"),
            kpi("Sem custo", br(sem), "atencao" if sem else "ok",
                f"itens · {moeda(sum(l[20] for l in ls))}" if sem else "itens"),
        ] + extra
    r["kpis"] = cartoes(lp)
    cols_p = [col("SITUAÇÃO", "texto", 92), col("DATA PED.", "dia", 70),
              col("DATA NF", "dia", 66), col("FILIAL", "texto", 90),
              col("PEDIDO", "texto", 62), col("NF", "texto", 58),
              col("CLIENTE", "texto", 210), col("UF", "texto", 34),
              col("CIDADE", "texto", 110), col("SUPERVISOR", "texto", 160),
              col("VENDEDOR", "texto", 170), col("QTD", "num", 50),
              col("R$ VENDA", "moeda", 86), col("CUSTO", "moeda", 86),
              col("SUCATA", "moeda", 70), col("MARGEM", "moeda", 80),
              col("MARKUP %", "pct1", 70), col("MKP TABELA %", "pct1", 84),
              col("% DESC.", "pct1", 60), col("SEM CUSTO", "int", 66),
              col("VENDA SEM CUSTO", "moeda", 90, oculta=True),
              col("SO BATERIA", "texto", 40, oculta=True),
              col("CÓD. AUTORIZAÇÃO", "texto", 120),
              col("AUTORIZADO POR", "texto", 96)]
    r["tabelas"].append(tabela(
        "Por pedido", cols_p, lp, tp,
        filtros=("SITUAÇÃO", "UF", "SUPERVISOR", "VENDEDOR"),
        kpis_de=cartoes,
        recortes=[("Abaixo do mínimo", lambda l: l[16] is not None and l[16]
                   < (mkp_bat if l[21] else MARKUP_MIN)),
                  ("Markup negativo", lambda l: l[16] is not None
                   and l[16] < 0),
                  ("Com item sem custo", lambda l: l[19] > 0)]))
    # ---- as visoes agrupadas -------------------------------------------
    # (14/10) AUDITORIA: so o FATURADO (o em aberto fica no Por pedido) -
    # antes, no mes corrente, o em aberto somava nas visoes e no cartao
    itens = [x for x in itens if x["sit"] == "FATURADO"]
    total_margem = sum(x["venda"] - x["custo"] for x in itens if x["custo"])

    def visao(titulo, chave, nome_col, larg=200, extra=None):
        g = defaultdict(list)
        for x in itens:
            g[chave(x)].append(x)
        ls, ts = [], []
        for k, gr in g.items():
            s = somar(gr)
            peds = len({(x["it"]["filial"], x["it"]["pedido"]) for x in gr})
            lin = [k] + (extra(k) if extra else []) + [
                peds, s["qtd"], s["venda"], s["custo"], s["margem"], s["mkp"],
                s["mkp_tab"], s["desc"],
                pct_de(s["margem"] or 0, total_margem) if total_margem else None,
                s["sem"]]
            ls.append(lin)
            minimo = mkp_bat if (titulo == "Por categoria"
                                 and k == "BATERIAS") or s["bateria"] \
                else MARKUP_MIN
            ts.append(tom(s, minimo))
        juntos_ = sorted(zip(ls, ts), key=lambda z: -z[0][-8])
        ls, ts = [z[0] for z in juntos_], [z[1] for z in juntos_]
        cols = [col(nome_col, "texto", larg)]
        if extra:
            cols += [col("DESCRIÇÃO", "texto", 260),
                     col("CATEGORIA", "texto", 110)]
        cols += [col("PEDIDOS", "int", 66), col("QTD", "num", 60),
                 col("R$ VENDA", "moeda", 92), col("CUSTO", "moeda", 92),
                 col("MARGEM", "moeda", 86), col("MARKUP %", "pct1", 72),
                 col("MKP TABELA %", "pct1", 86), col("% DESC.", "pct1", 62),
                 col("PART. MARGEM", "pct1", 86), col("SEM CUSTO", "int", 70)]
        s_t = somar(itens)
        n_ex = 2 if extra else 0
        tot = ["TOTAL"] + [""] * n_ex + [
            len({(x["it"]["filial"], x["it"]["pedido"]) for x in itens}),
            s_t["qtd"], s_t["venda"], s_t["custo"], s_t["margem"],
            s_t["mkp"], s_t["mkp_tab"], s_t["desc"], 100.0 if total_margem
            else None, s_t["sem"]]
        return tabela(titulo, cols, ls, ts, total=tot,
                      recortes=[("Abaixo do mínimo",
                                 lambda l, i=n_ex + 6: l[i] is not None
                                 and l[i] < MARKUP_MIN)])

    def cli_de(x):
        return ctx.cliente(x["it"]["cliente"])
    # (10/11) Por UF = a filial da nota (de onde vem o faturamento)
    r["tabelas"].append(visao("Por UF", lambda x: uf_da_filial(
        x["it"].get("filial")) or cli_de(x).get("uf") or "(sem UF)",
        "UF", 60))
    r["tabelas"].append(visao(
        "Por cidade", lambda x: f"{cli_de(x).get('cidade') or '?'} / "
        f"{cli_de(x).get('uf') or '?'}", "CIDADE", 220))
    r["tabelas"].append(visao("Por supervisor", lambda x: ctx.supervisor_de(
        x["it"]["vend"]), "SUPERVISOR", 240))
    r["tabelas"].append(visao("Por vendedor", lambda x: ctx.vendedor(
        x["it"]["vend"]), "VENDEDOR", 260))
    # (19/10, Alexandre) CATEGORIA, SISTEMA, FAMILIA, LINHA e PRODUTO com
    # TUDO do cadastro (nao so o que vendeu), com o preco de tabela, o
    # markup de tabela, o preco de venda e o markup de venda
    r["tabelas"] += _visoes_de_produto(ctx, itens, mkp_bat, fil_esc, somar,
                                       total_margem)
    r["tabelas"].append(_todos_os_produtos(ctx, itens, mkp_bat, fil_esc))
    # dois graficos de barra na capa: categoria e UF (so o que vendeu)
    for tit_ in ("Por categoria", "Por UF"):
        tab_ = next(t_ for t_ in r["tabelas"] if t_["titulo"] == tit_)
        nomes_ = [c_["nome"] for c_ in tab_["colunas"]]
        im = nomes_.index("MKP REAL %" if "MKP REAL %" in nomes_
                          else "MARKUP %")
        iv = nomes_.index("R$ VENDA")
        ls_ = [l for l in tab_["linhas"] if l[im] is not None
               and (l[iv] or 0) > 0][:8]
        if ls_:
            r["graficos"].append({
                "titulo": f"Markup {tab_['titulo'].lower()} (%)",
                "rotulos": [l[0] for l in ls_], "meta": MARKUP_MIN,
                "series": [{"nome": "Markup", "cor": AZUL,
                            "valores": [round(l[im], 1) for l in ls_]}],
                "formato": "pct"})
    return r


def _cadastro_de_precos(ctx, filial=None):
    """{cod: {"cap", "inte", "custo", "venda_p", "est"}} de TODO o cadastro:
    o preco de tabela (capital; com FILIAL, o dela; sem, a media das
    filiais), o custo (P. PEDIDO + sucata na bateria), o preco de venda
    (tabela - TETO_DESCONTO) e o estoque (BAP disponivel + lojas PMZ; com
    FILIAL, o dela). A mesma conta da aba Todos os produtos."""
    com = ctx.comercial
    precos = com.get("precos") or {}
    cod_fil = ""
    if filial:
        cods = sorted(c for c, n in (ctx.tabela.get("filiais") or {}).items()
                      if n == filial)
        cod_fil = cods[0] if cods else ""
        longos = {"4" + c for c in cods} | set(cods)
        precos = {prod: v for (f, prod), v in
                  (com.get("precos_filial") or {}).items() if f in longos}
    est = defaultdict(float)
    for e in ctx.tabela.get("estoque") or []:
        if filial and ctx.filial(e.get("filial")) != filial:
            continue
        est[e["cod"]] += max(0.0, e["qatu"] - e["reserva"])
    for e in ctx.tabela.get("estoque_pmz") or []:
        if filial and ctx.filial(e.get("filial")) != filial:
            continue
        est[e["cod"]] += max(0.0, e.get("qtd") or 0.0)
    codigos = (set(ctx.tabela.get("nomes") or {}) | set(precos)
               | {c for (_f, c) in com.get("custos") or {}})
    codigos.discard("")
    saida = {}
    for cod in codigos:
        custo_u, suc_u, _o = _custo_do_item(ctx, {"filial": cod_fil,
                                                   "cod": cod})
        cap, inte = precos.get(cod, (0.0, 0.0))
        saida[cod] = {"cap": cap or 0.0, "inte": inte or 0.0,
                      "custo": (custo_u + suc_u) or 0.0,
                      "venda_p": cap * (1 - TETO_DESCONTO / 100.0)
                      if cap else 0.0,
                      "est": est.get(cod, 0.0)}
    return saida


def _visoes_de_produto(ctx, itens, mkp_bat, filial, somar, total_margem):
    """
    (19/10, Alexandre) Farol de Markup › Por categoria, Por sistema, Por
    familia, Por linha e Por produto com TODO o cadastro: quem nao vendeu
    aparece com a venda zerada. Cada aba so com a coluna dela (sistema sem
    a categoria ao lado). Colunas: PRODUTOS, ESTOQUE, VOL. VENDIDO, venda,
    custo, margem e os markups:
        MKP REAL %   = o que VENDEU no periodo: venda faturada / custo - 1
                       (com o desconto que foi dado de verdade)
        MKP TABELA % = cadastro: soma do preco de tabela / soma do custo - 1
        MKP VENDA %  = cadastro: soma do preco de venda (tabela - 15%, o
                       teto de desconto) / soma do custo - 1
    MKP TABELA e VENDA nos produtos do grupo com preco e custo
    [SUPOSICAO: media do cadastro, sem peso pela venda].
    SEM CUSTO = produtos sem custo e COM ESTOQUE (o que da para vender sem
    saber a margem).
    """
    cad = _cadastro_de_precos(ctx, filial)
    vend = defaultdict(list)
    for x in itens:
        vend[x["it"]["cod"]].append(x)
    codigos = set(cad) | set(vend)
    classe = {c: (_categoria(ctx, c), ctx.sistema(c), ctx.familia(c),
                  ctx.linha(c)) for c in codigos}

    def minimo_de(cat):
        return mkp_bat if cat == "BATERIAS" else MARKUP_MIN

    def tom_de(mkp, cat):
        if mkp is None:
            return "cinza"
        return "alerta" if mkp < 0 else ("atencao" if mkp < minimo_de(cat)
                                          else "")

    def cadastro(cods):
        ok = [cad[c] for c in cods if c in cad and cad[c]["custo"] > 0
              and cad[c]["cap"] > 0]
        custo = sum(v["custo"] for v in ok)
        return (_mkp(sum(v["cap"] for v in ok), custo),
                _mkp(sum(v["venda_p"] for v in ok), custo))

    def estoque(cods):
        return sum((cad.get(c) or {}).get("est", 0.0) for c in cods)

    def sem_custo(cods):
        return sum(1 for c in cods if not (cad.get(c) or {}).get("custo")
                   and (cad.get(c) or {}).get("est", 0.0) > 0)
    tabelas = []
    niveis = (("Por categoria", "CATEGORIA", 0, 140),
              ("Por sistema", "SISTEMA", 1, 170),
              ("Por família", "FAMÍLIA", 2, 260),
              ("Por linha", "LINHA", 3, 150))
    s_t = somar(itens)
    mkp_tt, mkp_vt = cadastro(codigos)
    for titulo, nome, i_cl, larg in niveis:
        grupos = defaultdict(list)
        for c in codigos:
            grupos[classe[c][i_cl]].append(c)
        ls, ts = [], []
        for k, cods in grupos.items():
            gr = [x for c in cods for x in vend.get(c, ())]
            s = somar(gr) if gr else None
            mkp_t, mkp_v = cadastro(cods)
            ls.append([
                k, len(cods), estoque(cods), s["qtd"] if s else 0,
                s["venda"] if s else 0.0, s["custo"] if s else 0.0,
                s["margem"] if s else None, s["mkp"] if s else None,
                s["desc"] if s else None, mkp_t, mkp_v,
                pct_de(s["margem"] or 0, total_margem)
                if s and total_margem else None, sem_custo(cods)])
            cats = {classe[c][0] for c in cods}
            cat = next(iter(cats)) if len(cats) == 1 else ""
            ts.append(tom_de(s["mkp"] if s and s["mkp"] is not None
                             else mkp_v, cat))
        ordem = sorted(range(len(ls)), key=lambda i: (-(ls[i][4] or 0),
                                                      ls[i][0]))
        ls, ts = [ls[i] for i in ordem], [ts[i] for i in ordem]
        cols = [dict(col(nome, "texto", larg), inteira=True),
                col("PRODUTOS", "int", 72), col("ESTOQUE", "num", 76),
                col("VOL. VENDIDO", "num", 88),
                col("R$ VENDA", "moeda", 90), col("CUSTO", "moeda", 90),
                col("MARGEM", "moeda", 84), col("MKP REAL %", "pct1", 80),
                col("% DESC.", "pct1", 60), col("MKP TABELA %", "pct1", 86),
                col("MKP VENDA %", "pct1", 84),
                col("PART. MARGEM", "pct1", 84),
                col("SEM CUSTO", "int", 70)]
        tot = ["TOTAL", len(codigos), estoque(codigos), s_t["qtd"],
               s_t["venda"], s_t["custo"], s_t["margem"], s_t["mkp"],
               s_t["desc"], mkp_tt, mkp_vt,
               100.0 if total_margem else None, sem_custo(codigos)]
        tabelas.append(tabela(
            titulo, cols, ls, ts, total=tot, filtros=(nome,),
            recortes=[("Com venda no período", lambda l: (l[3] or 0) > 0),
                      ("Sem venda no período", lambda l: not l[3]),
                      ("Com produto sem custo e com estoque",
                       lambda l: l[12] > 0),
                      ("Markup real abaixo do mínimo",
                       lambda l: l[7] is not None and l[7] < MARKUP_MIN),
                      ("Markup de venda abaixo do mínimo",
                       lambda l: l[10] is not None and l[10] < MARKUP_MIN)]))
    # ---- por produto: todo o cadastro --------------------------------
    ls, ts = [], []
    for c in codigos:
        gr = vend.get(c, [])
        s = somar(gr) if gr else None
        v = cad.get(c) or {"cap": 0.0, "custo": 0.0, "venda_p": 0.0,
                           "est": 0.0}
        cat, sis, fam, lin = classe[c]
        mkp_v = _mkp(v["venda_p"], v["custo"])
        ls.append([
            c, ctx.produto(c), cat, sis, fam, lin,
            "VENDEU" if gr else "SEM VENDA", v["est"], v["custo"] or None,
            v["cap"] or None, _mkp(v["cap"], v["custo"]),
            v["venda_p"] or None, mkp_v,
            s["qtd"] if s else 0, s["venda"] if s else 0.0,
            s["custo"] if s else 0.0, s["margem"] if s else None,
            s["mkp"] if s else None, s["desc"] if s else None,
            pct_de(s["margem"] or 0, total_margem)
            if s and total_margem else None])
        ts.append(tom_de(s["mkp"] if s and s["mkp"] is not None else mkp_v,
                         cat))
    ordem = sorted(range(len(ls)), key=lambda i: (-(ls[i][14] or 0),
                                                  ls[i][0]))
    ls, ts = [ls[i] for i in ordem], [ts[i] for i in ordem]
    sufixo = "" if filial else " MÉD."
    # (19/10) so a coluna da aba (PRODUTO e DESCRICAO); a classificacao
    # fica oculta, para os filtros de cima e o Excel
    cols = [dict(col("PRODUTO", "texto", 120), inteira=True),
            dict(col("DESCRIÇÃO", "texto", 300), inteira=True),
            col("CATEGORIA", "texto", 110, oculta=True),
            col("SISTEMA", "texto", 120, oculta=True),
            col("FAMÍLIA", "texto", 170, oculta=True),
            col("LINHA", "texto", 100, oculta=True),
            col("SITUAÇÃO", "texto", 86), col("ESTOQUE", "num", 70),
            col("CUSTO UNIT.", "moeda2", 86),
            col("PRC. TABELA" + sufixo, "moeda2", 96),
            col("MKP TABELA %", "pct1", 86),
            col("PRC. VENDA" + sufixo, "moeda2", 96),
            col("MKP VENDA %", "pct1", 84),
            col("VOL. VENDIDO", "num", 84),
            col("R$ VENDA", "moeda", 88), col("CUSTO", "moeda", 88),
            col("MARGEM", "moeda", 82), col("MKP REAL %", "pct1", 80),
            col("% DESC.", "pct1", 60), col("PART. MARGEM", "pct1", 82)]
    tot = ["TOTAL", f"{br(len(ls))} produtos", "", "", "", "",
           f"{br(len(vend))} venderam", estoque(codigos), None, None, None,
           None, None, s_t["qtd"], s_t["venda"], s_t["custo"],
           s_t["margem"], s_t["mkp"], s_t["desc"],
           100.0 if total_margem else None]
    tabelas.append(tabela(
        "Por produto", cols, ls, ts, total=tot,
        filtros=("SITUAÇÃO",) + FILTROS_PRODUTO,
        recortes=[("Com venda no período", lambda l: l[6] == "VENDEU"),
                  ("Sem venda no período", lambda l: l[6] != "VENDEU"),
                  ("Sem custo e com estoque",
                   lambda l: not l[8] and (l[7] or 0) > 0),
                  ("Sem preço de tabela", lambda l: not l[9]),
                  ("Markup real abaixo do mínimo",
                   lambda l: l[17] is not None and l[17] < (
                       mkp_bat if l[2] == "BATERIAS" else MARKUP_MIN)),
                  ("Markup de venda abaixo do mínimo",
                   lambda l: l[12] is not None and l[12] < (
                       mkp_bat if l[2] == "BATERIAS" else MARKUP_MIN))]))
    return tabelas


# =========================================================================
# EXPORTAR PARA O RH (Farol de Metas Equipe)
# =========================================================================
INDICADORES_RH = (("FATURAMENTO TOTAL (R$)", "FAT.", "meta_rh", "realizado",
                   "rv_fat", "moeda"),
                  ("POSITIVAÇÃO", "POSIT.", "meta_positivacao", "positivados",
                   "rv_positivacao", "int"),
                  ("VISITA", "VISITA", "meta_visita", "visitas_realizadas",
                   "rv_visita", "int"))


def _moeda_txt(v) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


def _mecanica_rv(ctx, comp, ac) -> dict:
    """(04/11, Alexandre - recado 20261104-0800) A MECANICA da RV para a aba
    do Excel do RH: as faixas de cada publico e indicador (em celulas: as
    formulas da aba REMUNERACAO VARIAVEL leem daqui) e as regras de
    apuracao, como o sistema calcula. O que o codigo nao garante sai com
    [SUPOSICAO]."""
    try:
        import meta_nucleo as mn_                       # noqa: PLC0415
        par_ = mn_.carregar_parametros(ctx.raiz / "meta_config.json")
        faixas = {n: {k: [[mn_._numero(f.get("de")),
                           mn_._numero(f.get("ate")),
                           mn_._numero(f.get("valor"))]
                          for f in mn_.faixas_da_rv(par_, n, k)]
                      for k, _r, _a in mn_.KPIS_DA_RV}
                  for n, _r in mn_.NIVEIS_DA_RV}
    except Exception:                                   # noqa: BLE001
        par_, faixas = {}, {}
    teto = float(par_.get("teto_rh_vendedor") or 0.0)
    casa = [float(x or 0) for x in (par_.get("meta_mes_de_casa") or [])]
    casa_txt = ", ".join(f"{i + 1}º mês {_moeda_txt(v)}"
                         for i, v in enumerate(casa)) or "—"
    trav = bool(((par_.get("metas_travadas") or {}).get(comp)))
    trav_ind = bool(((par_.get("metas_travadas_ind") or {}).get(comp)))
    du = par_.get("meta_visita_por_du") or 12
    interior = par_.get("meta_visita_interior") or 6
    pct_vis = par_.get("pct_visita") or 90
    pct_pos = par_.get("pct_positivacao") or 25
    rotulo_k = {"fat": "Faturamento total (meta RH)",
                "positivacao": "Positivação", "visita": "Visita"}
    # buraco entre o ATE de uma faixa e o DE da seguinte (paga 0 no sistema)
    buracos = []
    for n, kp in faixas.items():
        for k, fs in kp.items():
            for a_, b_ in zip(fs, fs[1:]):
                if b_[0] - a_[1] > 0.0011:
                    buracos.append(f"{n} · {rotulo_k[k]}: de "
                                   f"{a_[1]:.3f}% a {b_[0]:.3f}%".replace(
                                       ".", ","))
    regras = [
        ("Meta de faturamento que paga a RV",
         f"META RH. Vendedor: a meta comercial com teto de "
         f"{_moeda_txt(teto)}; nos primeiros meses de casa vale a meta da "
         f"tabela ({casa_txt}), proporcional aos dias úteis desde a admissão "
         f"no 1º mês. Supervisor: a soma da meta RH dos vendedores que "
         f"contam no mês. Gerente: o rateio da meta geral (sem tabela de "
         f"RV)."),
        ("% ATING.", "REAL ÷ META (meta zero ou vazia = 0%). Para achar a "
         "faixa o % é arredondado a 3 casas decimais, como as faixas "
         "(ex.: 79,9996% conta como 80,000%)."),
        ("Valor da RV de cada indicador",
         "O valor da faixa em que o % ATING. cai (DE ≤ % ≤ ATÉ, em "
         "percentual). Acima da última faixa vale a última. RV TOTAL = soma "
         "das três. Na aba REMUNERAÇÃO VARIÁVEL o % e a RV saem por fórmula "
         "lendo as tabelas abaixo."),
        ("Faturamento (REAL)",
         "Faturamento líquido do mês (venda − devolução) da TABELA_BAP, "
         "pela data da nota [SUPOSIÇÃO: data da NF]."),
        ("Positivação",
         f"META = {pct_pos:g}% da base visitada do vendedor. REAL = clientes "
         "com faturamento líquido > 0 no mês; os CNPJs internos do grupo "
         "(BAP AUTOPARTS / FRW / PMZ DISTRIBUIDORA) ficam fora."),
        ("Visita",
         f"META = {du} visitas por dia útil desde a admissão (interior "
         f"{interior}), × {pct_vis:g}% (a meta RH). REAL = visitas da "
         "Máxima (Farol de Visita) + cadastro novo do mês, menos o lote de "
         "cadastros de 16/10."),
        ("Vendedor inativo no Planner do mês",
         "Sem meta e sem RV (RV = 0, coluna OBS.); o desafio da "
         "carteira dele vai para os vendedores ativos. Sem nada realizado "
         "no mês (faturamento, positivação e visita zerados) ele não "
         "aparece na tabela."),
        ("Conta 000040", "Teste do Alexandre: sem meta e sem RV."),
        ("Meses de casa",
         "Meses completos da data de admissão (cadastro da equipe no "
         "Planner do mês) até o último dia do mês da competência. Sem data "
         "de admissão no Planner (hoje: supervisores e gerente), fica em "
         "branco. É informativo: a meta do mês de casa segue a regra da "
         "meta acima."),
        ("Metas travadas",
         "Quando o mês está travado no Gerador de Meta vale a meta gravada. "
         f"Este mês: faturamento {'TRAVADO' if trav else 'não travado'}; "
         f"visita e positivação {'TRAVADAS' if trav_ind else 'não travadas'}."),
        ("COMPLEMENTO e TOTAL A PAGAR",
         "COMPLEMENTO é preenchido pelo RH (células amarelas). TOTAL A "
         "PAGAR = RV TOTAL + COMPLEMENTO."),
        ("Fonte dos dados",
         "Gerador de Meta (meta_config.json e PLANNER do mês), TABELA_BAP "
         "(robô BAP Tools) e Farol de Visita (Máxima). Resultado até o dia "
         "anterior à posição do relatório."),
    ]
    if buracos:
        regras.append((
            "[ATENÇÃO] Faixas com intervalo sem valor",
            "Entre o ATÉ de uma faixa e o DE da seguinte o sistema paga 0 "
            "(a fórmula faz igual): " + "; ".join(buracos) + "."))
    return {"faixas": faixas, "regras": regras, "rotulos": rotulo_k,
            "periodo": f"{comp[5:7]}/{comp[:4]}" if comp else ""}


def _admissoes_do_planner(ctx, comp) -> dict:
    """(04/11) {cod6 ou NOME: data de admissao} do cadastro da equipe no
    Planner do mes (planner_config do mes; sem ele, o da pasta)."""
    saida = {}
    try:
        import json as json_                             # noqa: PLC0415
        import pastas_bap as pb_                         # noqa: PLC0415
        cfg = json_.loads(Path(pb_.config_do_planner(ctx.raiz, comp))
                         .read_text("utf-8"))
    except Exception:                                   # noqa: BLE001
        return saida
    for p_ in cfg.get("pessoas") or []:
        d_ = texto(p_.get("data_admissao"))
        try:
            d_ = date.fromisoformat(d_[:10]) if d_ else None
        except ValueError:
            d_ = None
        if not d_:
            continue
        if texto(p_.get("cod_protheus")):
            saida[_cod6(p_.get("cod_protheus"))] = d_
        if texto(p_.get("nome")):
            saida[sem_acento(texto(p_.get("nome"))).upper()] = d_
    return saida


def _pessoa_rh(l) -> bool:
    """So quem recebe: fora linhas tecnicas (FORA DO PLANNER, sem
    supervisor/gerente) e a vaga sem ninguem."""
    nome = texto(l.get("nome") or l.get("rotulo")).upper()
    return bool(nome) and not nome.startswith("(") and \
        not nome.startswith("VAGO")


def _inativo_sem_nada(l) -> bool:
    """(05/11, Alexandre: "por que o Valmir aparece se esta inativo no
    Planner?") vendedor INATIVO no Planner do mes e SEM NADA realizado no mes
    (faturamento, positivacao e visita zerados) nao aparece na Remuneracao
    Variavel. Se vendeu ou visitou no mes, continua (RV 0 e a regra
    "inativo"), para o total dos vendedores fechar com o do supervisor."""
    if l.get("vendedor_ativo", True) is not False:
        return False
    return not any(abs(l.get(kr) or 0) > 0.005
                   for _g, _c, _km, kr, _krv, _tp in INDICADORES_RH)


def _do_parcial(parcial, chave, l):
    """A linha entra na parcial desta pessoa? vendedor: so ele; supervisor:
    ele e os vendedores dele; gerente: todo mundo."""
    if not parcial:
        return True
    cargo = parcial["cargo"]
    if cargo == "GERENTE":
        return True
    if cargo == "SUPERVISOR":
        if chave == "supervisor":
            return norm_nome(l.get("nome") or l.get("rotulo")) == \
                norm_nome(parcial["nome"])
        if chave == "vendedor":
            return norm_nome(l.get("supervisor")) == norm_nome(parcial["nome"])
        return False
    return chave == "vendedor" and texto(l.get("chave")) == parcial["cod"]


def norm_nome(v) -> str:
    return " ".join(sem_acento(texto(v)).upper().split())


def exportar_rh(ctx, parcial=None):
    """O Exportar para o RH, o e-mail e a parcial de RV: os UNICOS lugares
    com a meta RH e a RV (29/10). Liga _COM_RH so durante a montagem."""
    antes = _COM_RH[0]
    _COM_RH[0] = True
    try:
        return _exportar_rh(ctx, parcial)
    finally:
        _COM_RH[0] = antes


def _exportar_rh(ctx, parcial=None):
    """
    O resultado do mes para o RH pagar a RV: gerente, supervisores e
    vendedores, com META, REAL, % ATING. e RV de faturamento total,
    positivacao e visita (sem NEC./DIA nem pecas). Competencia = a do mes
    escolhido no Farol de Metas (TODOS OS MESES: a do Gerador de Meta).
    parcial = {"cargo", "cod", "nome"}: a PARCIAL de uma pessoa, no mesmo
    formato (vendedor: a linha dele; supervisor: ele e a equipe dele;
    gerente: tudo), sem as assinaturas - e o que vai por e-mail.
    """
    dados = meta_do_periodo(ctx)
    ac, comp = dados["acomp"], dados["competencia"]
    if parcial:
        cod_p = (f" · Cód. {_cod6(parcial.get('cod'))}"
                 if parcial.get("cargo") == "VENDEDOR" and parcial.get("cod")
                 else "")
        r = novo("vc_meta_rh", VEN,
                 f"Parcial de Resultado · {parcial['nome']}{cod_p}",
                 f"Competência {rotulo_mes(comp)} · posição de "
                 f"{ctx.hoje:%d/%m/%Y} · meta, realizado e RV por indicador",
                 "Gerador de Meta (BAP Analista) + TABELA_BAP")
    else:
        r = novo("vc_meta_rh", VEN, "Resultado da Equipe · RH",
                 f"Competência {rotulo_mes(comp)} · meta, realizado e RV por "
                 "indicador", "Gerador de Meta (BAP Analista) + TABELA_BAP")
        # (04/11, Alexandre) sem as assinaturas: "nao precisa"
    r["competencia"] = comp
    r["posicao"] = f"{ctx.hoje:%d/%m/%Y}"
    # o RESULTADO ATE: o dia anterior (o faturamento de hoje ainda corre)
    r["resultado_ate"] = f"{ctx.hoje - timedelta(days=1):%d/%m/%Y}"
    r["tabelas_seguidas"] = True
    # (03/11, Alexandre) o fechamento do RH: COMPLEMENTO (o RH preenche no
    # Excel) e TOTAL A PAGAR = RV TOTAL + COMPLEMENTO; tudo numa pagina e o
    # Excel numa aba so, com o cabecalho da BAP (REMUNERACAO VARIAVEL)
    extra = not parcial
    if extra:
        r["excel_rv"] = True
        r["periodo"] = f"{comp[5:7]}/{comp[:4]}" if comp else ""
        r["uma_pagina"] = True
        # (04/11) a aba MECANICA e as formulas da RV no Excel
        r["mecanica"] = _mecanica_rv(ctx, comp, ac)
    # (04/11, Alexandre) o TEMPO DE CASA em meses de cada um, depois do
    # nome: meses completos da ADMISSAO (cadastro do Planner do mes) ate o
    # fim do mes da competencia; sem data de admissao: vazio
    o = 1 if extra else 0
    admissao = _admissoes_do_planner(ctx, comp) if extra else {}

    def meses_de_casa_(l):
        d_ = (admissao.get(_cod6(l.get("chave")))
              or admissao.get(sem_acento(texto(l.get("nome"))).upper()))
        if not d_ or not comp:
            return None
        a_, m_ = int(comp[:4]), int(comp[5:7])
        fim = date(a_ + (m_ == 12), m_ % 12 + 1, 1)   # 1o dia do mes seguinte
        if d_ >= fim:
            return 0
        n_ = (fim.year - d_.year) * 12 + fim.month - d_.month
        return n_ - (1 if fim.day < d_.day else 0)

    def linha(l, com_sup=False):
        saida = [l.get("nome") or l.get("rotulo")]
        if com_sup:         # o supervisor curto: o nome inteiro ja esta acima
            sup = texto(l.get("supervisor"))
            partes = sup.split()
            saida.append(f"{partes[0]} {partes[-1]}" if len(partes) > 2
                         and not sup.startswith("(") else sup)
        if extra:
            saida.append(meses_de_casa_(l))
        rv_tot = 0.0
        tem_rv = False
        for _g, _c, km, kr, krv, _tp in INDICADORES_RH:
            meta, real = l.get(km) or 0, l.get(kr) or 0
            rv = l.get(krv)
            tem_rv = tem_rv or rv is not None
            rv_tot += rv or 0
            saida += [meta, real, pct_de(real, meta), rv]
        saida.append(l.get("rv_total") if l.get("rv_total") is not None
                     else (rv_tot if tem_rv else None))
        if extra:           # COMPLEMENTO (em branco) e TOTAL A PAGAR
            saida += [None, saida[-1]]
        return saida

    # larguras FIXAS no PDF (pontos): os numeros ficam um embaixo do outro
    # nas tres tabelas; o nome (e o supervisor) ficam com o resto
    L_VALOR, L_QTD, L_PCT, L_RV, L_TOT = 46, 30, 38, 36, 44
    if extra:       # (03/11) +2 colunas: o nome continua numa linha so
        L_VALOR, L_QTD, L_PCT, L_RV, L_TOT = 44, 28, 32, 32, 40

    def colunas(com_sup=False):
        cs = [col("NOME", "texto", (170 if extra else 200) if com_sup
                  else 300)]
        grupos = [("", 1)]
        if com_sup:
            # (03/11) com as 2 colunas novas o supervisor pesa mais (no
            # PDF o texto divide o que sobra pela largura)
            cs.append(col("SUPERVISOR", "texto", 125 if extra else 100))
            grupos = [("", 2)]
        if extra:
            cs.append(dict(col("MESES DE CASA", "int", 60), curto="MESES CASA",
                           pdf_larg=26))
            grupos = [("", grupos[0][1] + 1)]
        for g, c, _km, _kr, _krv, tp in INDICADORES_RH:
            lv = L_VALOR if tp == "moeda" else L_QTD
            cs += [dict(col(f"{c} META", tp, 80), curto="META", pdf_larg=lv),
                   dict(col(f"{c} REAL", tp, 80), curto="REAL", pdf_larg=lv),
                   dict(col(f"{c} % ATING.", "pct", 60), curto="% ATING.",
                        pdf_larg=L_PCT),
                   dict(col(f"{c} RV", "moeda", 70), curto="RV R$",
                        pdf_larg=L_RV)]
            grupos.append((g, 4))
        cs.append(dict(col("RV TOTAL", "moeda", 80), curto="RV TOTAL R$",
                       pdf_larg=L_TOT))
        grupos.append(("", 1))
        if extra:
            cs += [dict(col("COMPLEMENTO", "moeda", 90), curto="COMPL. R$",
                        pdf_larg=L_TOT, editavel_excel=True),
                   dict(col("TOTAL A PAGAR", "moeda", 90),
                        curto="A PAGAR R$", pdf_larg=L_TOT + 4,
                        formula_excel="rv+compl")]
            grupos.append(("", 2))
        return cs, grupos

    def total(ls, com_sup=False):
        k = (2 if com_sup else 1) + o
        tot = ["TOTAL"] + ([""] if com_sup else []) + ([None] if o else [])
        for i in range(3):
            j = k + i * 4
            meta = sum(l[j] or 0 for l in ls)
            real = sum(l[j + 1] or 0 for l in ls)
            rv = [l[j + 3] for l in ls if l[j + 3] is not None]
            tot += [meta, real, pct_de(real, meta), sum(rv) if rv else None]
        j_rv = k + 12                     # a coluna RV TOTAL
        rvt = [l[j_rv] for l in ls if l[j_rv] is not None]
        tot.append(sum(rvt) if rvt else None)
        if extra:
            tot += [None, tot[-1]]
        return tot

    def tom(l):
        return "ok" if (l[-1] or 0) > 0 else ""

    def cor_ating(v):
        """< 80% vermelho · 80 a 99% amarelo · 100% ou mais verde."""
        if v is None:
            return None
        return (VERMELHO if v < 80 else AMARELO_TXT if v < 100
                else VERDE_TXT)

    def cores(l, com_sup):
        k = (2 if com_sup else 1) + o
        saida = {}
        for i in range(3):
            c_ = cor_ating(l[k + i * 4 + 2])
            if c_:
                saida[k + i * 4 + 2] = c_          # % ATING.
                saida[k + i * 4 + 3] = c_          # e a RV dele
        return saida
    blocos = []
    for chave, titulo, com_sup in (("gerente", "Gerente", False),
                                   ("supervisor", "Supervisores", False),
                                   ("vendedor", "Vendedores", True)):
        ls = [l for l in ac["recortes"].get(chave, []) if _pessoa_rh(l)
              and _do_parcial(parcial, chave, l)
              and not _inativo_sem_nada(l)]
        if parcial and not ls:
            continue
        ls.sort(key=lambda l: (texto(l.get("supervisor")).startswith("(")
                               or not texto(l.get("supervisor")),
                               texto(l.get("supervisor")),
                               -(l.get("meta") or 0)) if com_sup
                else (0, "", -(l.get("meta") or 0)))
        linhas = [linha(l, com_sup) for l in ls]
        cs, grupos = colunas(com_sup)
        t_ = tabela(titulo, cs, linhas, [tom(x) for x in linhas],
                    filtros=("SUPERVISOR",) if com_sup else (),
                    total=total(linhas, com_sup) if len(linhas) > 1 else None)
        t_["grupos"] = grupos
        t_["cores_celulas"] = [cores(x, com_sup) for x in linhas]
        if extra:           # (04/11) o Excel do RH: nivel e regra aplicada
            t_["nivel_rv"] = chave

            def regra_(l):
                if l.get("vendedor_ativo") is False:
                    return "inativo no Planner do mês: sem meta e sem RV"
                if chave == "gerente":
                    return ("sem tabela de RV para o gerente · "
                            + texto(l.get("faixa_rh") or ""))
                return texto(l.get("faixa_rh") or l.get("faixa") or "")
            t_["regras_excel"] = [regra_(l) for l in ls]
        if t_["total"]:
            t_["cores_total"] = cores(t_["total"], com_sup)
        t_["pdf"] = {"verticais": True, "cab": 5.6, "sem_rs": True}
        if extra:           # (03/11) as tres tabelas cabem numa pagina
            t_["pdf"].update({"pad": 1.0, "corpo": 6.3})
        r["tabelas"].append(t_)
        blocos.append((chave, linhas))
    rv = {k: sum(l[-1] or 0 for l in ls) for k, ls in blocos}
    vend = dict(blocos).get("vendedor", [])
    sem_tabela = [k for k, ls in blocos if ls and all(l[-1] is None
                                                       for l in ls)]
    r["kpis"] = [
        kpi("RV total a pagar", moeda(sum(rv.values())), "ok"),
        kpi("Vendedores", moeda(rv.get("vendedor", 0)), "neutro",
            f"{br(sum(1 for l in vend if (l[-1] or 0) > 0))} de "
            f"{br(len(vend))} com RV"),
        kpi("Supervisores", moeda(rv.get("supervisor", 0)), "neutro"),
        kpi("Gerente", "—" if "gerente" in sem_tabela
            else moeda(rv.get("gerente", 0)), "neutro",
            "sem tabela de RV" if "gerente" in sem_tabela else ""),
        kpi("Faturamento", p(pct_de(sum(l[3 + o] or 0 for l in vend),
                                    sum(l[2 + o] or 0 for l in vend))), "info",
            "atingimento da equipe"),
    ]
    if not dados.get("tem_rv"):
        r["avisos"].append("Sem tabela de RV cadastrada no Gerador de Meta.")
    if parcial:
        # o resultado DA PESSOA aberto por segmento, familia, cidade e
        # bairro (na META RH dela) e as notas do mes - sem lista de
        # clientes, de proposito
        r["tabelas"] = _detalhe_da_parcial(ctx, ac, comp, parcial)
        # os numeros DA PESSOA: cartoes do PDF e o corpo do e-mail
        chave_p = {"VENDEDOR": "vendedor", "SUPERVISOR": "supervisor",
                   "GERENTE": "gerente"}.get(parcial["cargo"], "vendedor")
        own = dict(blocos).get(chave_p) or []
        r["resumo_pessoa"] = []
        if own:
            l, k = own[0], (2 if chave_p == "vendedor" else 1)
            r["kpis"] = []
            # o e-mail: META FAT. COMERCIAL (sem RV) e META FAT. RH (a que
            # paga a RV), positivacao e visita
            # cada linha: (indicador, meta, real, % ating., RV, projecao,
            # % ating. projetado, GAP do mes, nec./dia) - ja formatados
            resta_ = ac.get("dias_restantes") or 0
            corrido_ = (_esperado(ac) or 0.0) / 100.0

            def resumo_(rot, meta, real, fmt, rv_txt, inteiro=False):
                meta, real = meta or 0.0, real or 0.0
                proj = real / corrido_ if corrido_ > 0 else None
                gap = max(0.0, meta - real)
                nec = gap / resta_ if resta_ else None
                return (rot, fmt(meta), fmt(real), p(pct_de(real, meta)),
                        rv_txt, "—" if proj is None else fmt(proj),
                        p(pct_de(proj, meta)) if proj is not None else "—",
                        fmt(gap), "—" if nec is None else (
                            br(nec, 1) if inteiro else fmt(nec)))
            # o DESAFIO FAT. COMERCIAL (sem RV: so a meta RH paga) fica
            # separado dos indicadores da RV
            lp_, _cods = _escopo_da_parcial(ac, parcial)
            if lp_ is not None:
                r["resumo_desafio"] = resumo_(
                    "Desafio Fat. Comercial", lp_.get("meta"),
                    lp_.get("realizado"), moeda, "")
            rotulos_ = ("Meta Fat.", "Positivação", "Visita")
            for i, (g, _c, _km, _kr, _krv, tp) in enumerate(INDICADORES_RH):
                meta, real, pct, rv_ = l[k + i * 4: k + i * 4 + 4]
                fmt = moeda if tp == "moeda" else br
                r["resumo_pessoa"].append(resumo_(
                    rotulos_[i], meta, real, fmt,
                    moeda(rv_ or 0.0, 2), tp != "moeda"))
                r["kpis"].append(kpi(g.split(" (")[0].title(), fmt(real),
                                     "ok" if (pct or 0) >= 100 else
                                     "atencao" if (pct or 0) >= 80 else
                                     "alerta",
                                     f"{p(pct)} de {fmt(meta)}"))
            r["kpis"].append(kpi("RV total", "—" if l[-1] is None
                                 else moeda(l[-1]), "neutro", "parcial"))
            r["rv_pessoa"] = l[-1]
        # O PDF NA CARA DO CATALOGO BAP: cartoes com a meta comercial E a
        # meta RH, positivacao, visita, cadastro com compra e a RV
        tab_p = next((t for t in r["tabelas"] if t["titulo"] == {
            "vendedor": "Por vendedor", "supervisor": "Por supervisor",
            "gerente": "Por gerente"}[chave_p]), None)
        if tab_p and tab_p["linhas"]:
            ls_p = [x for x in tab_p["linhas"]
                    if not str(x[0]).startswith("(")] or tab_p["linhas"]
            if chave_p != "gerente":
                ls_p = ls_p[:1] if chave_p == "supervisor" else ls_p
            r["kpis"] = _cartoes_farol(ls_p, tab_p["colunas"],
                                       ac.get("dias_restantes") or 0,
                                       _esperado(ac), _hoje_do_farol(
                                           ctx, ac, comp).get(chave_p))
        # (10/10) o resumo dos PEDIDOS EM ABERTO na 1a pagina
        r["kpis"].append(_kpi_abertos_da_parcial(
            ctx, _escopo_da_parcial(ac, parcial)[1]))
        nome_b = " ".join(w.capitalize() if len(w) > 2 else w.lower()
                          for w in texto(parcial["nome"]).split())
        sup_p = ""
        if parcial["cargo"] == "VENDEDOR":
            lv = next((x for x in ac["recortes"].get("vendedor", [])
                       if _cod6(x.get("chave")) == _cod6(parcial["cod"])), {})
            sup_p = _nome_curto(lv.get("supervisor"))
        resta_p = ac.get("dias_restantes") or 0
        r.update({
            "estilo": "bap",
            "faixa": f"PARCIAL DE RESULTADO · {rotulo_mes(comp)}",
            # o vendedor com o CODIGO DE VENDA (06/10)
            "eyebrow": parcial["cargo"]
            + (f" · CÓD. {_cod6(parcial['cod'])}"
               if parcial["cargo"] == "VENDEDOR" and parcial.get("cod")
               else "")
            + (f" · SUPERVISOR {sup_p}" if sup_p else ""),
            "titulo_curto": nome_b,
            "subtitulo": (f"Resultado até {ctx.hoje - timedelta(days=1):%d/%m/%Y} · "
                          + (f"{resta_p} dia(s) útil(eis) até o fim do mês"
                             if resta_p else "mês fechado")
                          + " · meta e desafio comercial")})
    return r


VISTAS_PARCIAL = ("gerente", "supervisor", "vendedor", "uf", "cidade",
                  "bairro", "segmento")
CORTE_PDF = 25          # cidade e bairro no PDF: as de meta/venda, ate 25


def _escopo_da_parcial(ac, parcial):
    """(linha da pessoa, codigos dos vendedores dela) - vendedor: ele;
    supervisor: a equipe; gerente: None (todo mundo)."""
    rec = ac.get("recortes") or {}
    equipe = ac.get("equipe_vend") or {}
    cargo = parcial["cargo"]
    if cargo == "VENDEDOR":
        linha = next((l for l in rec.get("vendedor", [])
                      if _cod6(l.get("chave")) == _cod6(parcial["cod"])), None)
        return linha, {_cod6(parcial["cod"])}
    nivel = "supervisor" if cargo == "SUPERVISOR" else "gerente"
    linha = next((l for l in rec.get(nivel, [])
                  if norm_nome(l.get("nome") or l.get("rotulo"))
                  == norm_nome(parcial["nome"])), None)
    if nivel == "gerente":
        return linha, None
    return linha, {c for c, e in equipe.items()
                   if linha and e.get("supervisor") == linha["chave"]}


def _detalhe_da_parcial(ctx, ac, comp, parcial) -> list:
    """O PDF da parcial: as MESMAS vistas do Farol de Metas (gerente,
    supervisor, vendedor, UF, cidade, bairro, segmento, familia), so com os
    dados da pessoa - vendedor: so ele (gerente e supervisor viram a soma
    dele); supervisor: a equipe dele; gerente: todo mundo - e as notas
    fiscais do mes (devolucao em vermelho). Sem lista de clientes."""
    linha_p, cods = _escopo_da_parcial(ac, parcial)
    if linha_p is None:
        return []
    if cods is None:                     # o gerente: o Farol inteiro
        tabs = vistas_do_farol(ctx, ac, comp, corte=CORTE_PDF, sem=("zona",))
    else:
        tabs = vistas_escopo(ctx, ac, comp, V=cods,
                             sup=linha_p if parcial["cargo"] == "SUPERVISOR"
                             else None, corte=CORTE_PDF)
    for t in tabs:          # cada TOP 30 numa pagina so dele
        if t["titulo"].startswith("Top "):
            t["pdf_pagina"] = True
        if t["titulo"] == f"Top {TOP_CLIENTES} clientes":
            _top_clientes_da_parcial(ctx, t)
    # A ORDEM DO PDF: gerente, supervisor, vendedor, UF, categoria,
    # segmento, familia; os TOP 30 (cidades, bairros, clientes); e as
    # NOTAS por ultimo, numa pagina separada
    ordem = ("Por gerente", "Por supervisor", "Por vendedor", "Por UF",
             "Por categoria", "Por segmento", "Por família da peça",
             "Top 30 cidades", "Top 30 bairros", "Top 30 clientes")
    tabs.sort(key=lambda t: ordem.index(t["titulo"]) if t["titulo"] in ordem
              else len(ordem))
    notas = _notas_da_parcial(ctx, comp, cods)
    notas["pdf_quebra_antes"] = True
    # (10/10) e embaixo das notas, os PEDIDOS EM ABERTO dele, para
    # acompanhar o que ainda vai faturar
    return tabs + [notas, _pedidos_abertos_da_parcial(ctx, cods)]


def _contato_do_cliente(ctx, cod) -> str:
    """O contato do cadastro (NOME · telefone); sem telefone nele, o do
    Gerador de Meta."""
    c = ctx.cliente(cod) or {}
    txt = texto(c.get("contato"))
    if not re.search(r"\d{4}", txt):
        fone = next((texto(l.get("fone")) for l in
                     (ctx.oportunidade or {}).get("linhas") or []
                     if texto(l.get("cod_cliente")).zfill(6) == cod), "")
        txt = " · ".join(x for x in (txt, fone) if x)
    # o TELEFONE primeiro (se faltar espaco, o que corta e o nome)
    partes = [x.strip() for x in txt.split("·") if x.strip()]
    fones = [x for x in partes if re.search(r"\d{4}", x)]
    nomes_ = [x for x in partes if x not in fones]
    return " · ".join(fones + nomes_)


def _top_clientes_da_parcial(ctx, t):
    """(10/10) O TOP 30 CLIENTES da parcial: com o BAIRRO e o CONTATO
    (com telefone) do cliente. (15/10) POSITIVACAO numa coluna so (SIM/NAO)
    e o indicador PECAS (meta, real e %) - cabe numa pagina.
    So no PDF da parcial (a tela do Farol de Metas fica como esta)."""
    nomes = [c_["nome"] for c_ in t["colunas"]]
    if "BAIRRO" not in nomes or "CONTATO" in nomes:
        return
    i_b = nomes.index("BAIRRO")
    # (15/10, Alexandre) a POSITIVACAO vira UMA coluna (SIM/NAO: comprou
    # no mes) e o indicador PECAS volta (META, REAL e %; o NEC./DIA fica
    # fora para caber). O espaco que sobra vai para o CONTATO
    livre = 0.0
    for c_ in t["colunas"]:
        oculto = c_["nome"].startswith("POSIT. ") or \
            c_["nome"] == "PEÇAS NEC./DIA"
        if oculto:
            if not c_.get("pdf_oculta") and not c_.get("oculta"):
                livre += c_.get("pdf_larg") or 0
            c_["pdf_oculta"] = True
    i_pr = nomes.index("POSIT. REAL") if "POSIT. REAL" in nomes else None
    i_pm = nomes.index("POSIT. META") if "POSIT. META" in nomes else None
    larg_sn = 30.0
    if i_pr is not None and i_pm is not None:
        livre -= larg_sn
        for l in (t.get("linhas_filtro") or []) + t["linhas"]:
            if len(l) == len(nomes):
                l.insert(i_pm, "SIM" if (l[i_pr] or 0) > 0 else "NÃO")
        if t.get("total") and len(t["total"]) == len(nomes):
            n_sim = sum(1 for l in t["linhas"] if l[i_pm] == "SIM")
            t["total"].insert(i_pm, f"{n_sim} SIM")
        t["colunas"].insert(i_pm, dict(_gcol("POSITIVOU", "NO MÊS", "texto",
                                             64), pdf_larg=larg_sn))
        if t.get("grupos"):
            # o grupo POSITIVACAO ganha a coluna nova (as 4 ocultas ficam)
            # (o rotulo encurta: a faixa do grupo tem uma coluna so)
            t["grupos"] = [("POSIT.", n_ + 1) if r_ == "POSITIVAÇÃO"
                           else (r_, n_) for r_, n_ in t["grupos"]]
        cc_ = t.get("cores_celulas") or [{} for _ in t["linhas"]]
        cc_ = [{(j + 1 if j >= i_pm else j): v for j, v in d_.items()}
               for d_ in cc_]
        for l, d_ in zip(t["linhas"], cc_):   # SIM verde, NAO vermelho
            d_[i_pm] = VERDE_TXT if l[i_pm] == "SIM" else VERMELHO
        t["cores_celulas"] = cc_
        nomes = [c_["nome"] for c_ in t["colunas"]]
    for c_ in t["colunas"]:
        if c_["nome"].startswith("PEÇAS ") and c_["nome"] != \
                "PEÇAS NEC./DIA" and c_.get("pdf_oculta") and \
                not c_.get("oculta"):
            c_["pdf_oculta"] = False
            livre -= c_.get("pdf_larg") or 0
    t["colunas"][i_b] = dict(t["colunas"][i_b], pdf_oculta=False,
                             oculta=False)
    # o comeco da linha ganha o espaco das PECAS: CLIENTE, CIDADE,
    # SEGMENTO e BAIRRO enxutos; o CONTATO fica com o resto
    inicio = sum(c_.get("pdf_larg") or 0 for c_ in t["colunas"][:i_b + 1]
                 if not c_.get("pdf_oculta") and c_["nome"] != "BAIRRO")
    larg_ = {"CLIENTE": 100.0, "CIDADE": 58.0, "SEGMENTO": 44.0,
             "BAIRRO": 54.0}
    for nome_c, lg in larg_.items():
        j = nomes.index(nome_c)
        t["colunas"][j] = dict(t["colunas"][j], pdf_larg=lg)
    w_cont = max(80.0, inicio + livre - sum(larg_.values()))
    vistos = set()
    for l in (t.get("linhas_filtro") or []) + t["linhas"]:
        if id(l) in vistos:
            continue
        vistos.add(id(l))
        cod = texto(str(l[0]).split(" - ")[0]).zfill(6)
        l.insert(i_b + 1, _contato_do_cliente(ctx, cod))
    t["colunas"].insert(i_b + 1, dict(col("CONTATO", "texto", 220),
                                      pdf_larg=w_cont))
    if t.get("total"):
        t["total"].insert(i_b + 1, "")
    if t.get("grupos"):
        rot0, n0 = t["grupos"][0]
        t["grupos"][0] = (rot0, n0 + 1)
    if t.get("cores_celulas"):
        t["cores_celulas"] = [{(j + 1 if j > i_b else j): v
                               for j, v in d_.items()}
                              for d_ in t["cores_celulas"]]
    # (15/10) com as PECAS na tela o CONTATO pode bater no minimo: o que
    # passar da pagina sai das colunas de texto, por igual
    vis_ = [c_ for c_ in t["colunas"]
            if not c_.get("oculta") and not c_.get("pdf_oculta")]
    sobra = sum(c_.get("pdf_larg") or 0 for c_ in vis_) - PDF_UTIL
    textos = [c_ for c_ in vis_ if c_["nome"] in
              ("CLIENTE", "CIDADE", "SEGMENTO", "BAIRRO", "CONTATO")]
    base_ = sum(c_["pdf_larg"] for c_ in textos)
    if sobra > 0.5 and base_ > sobra:
        k_ = (base_ - sobra) / base_
        for c_ in textos:
            c_["pdf_larg"] = round(c_["pdf_larg"] * k_, 2)
    t["pdf"] = dict(t.get("pdf") or {}, quebra=("CONTATO",))


def _ordenar_por_clientes(t):
    """A tabela do maior para o menor em CLIENTES ATIVOS (empate: a maior
    meta comercial); "(SEM CIDADE)" no fim."""
    nomes = [c["nome"] for c in t["colunas"]]
    i_a, i_m = nomes.index("CLIENTES ATIVOS"), nomes.index("FAT. META")
    ordem = sorted(range(len(t["linhas"])), key=lambda i: (
        str(t["linhas"][i][1]).startswith("("),
        -(t["linhas"][i][i_a] or 0), -(t["linhas"][i][i_m] or 0)))
    t["linhas"] = [t["linhas"][i] for i in ordem]
    t["tons"] = [t["tons"][i] for i in ordem]


def _notas_da_parcial(ctx, comp, cods):
    """As NFs do mes (de quem esta na parcial): NF, emissao, cliente, valor
    e volume; a devolucao (e a nota que teve devolucao) em vermelho."""
    notas, devolvidas = {}, set()
    for it in ctx.tabela["itens"]:
        if not it["dt_nf"] or mes_de(it["dt_nf"]) != comp:
            continue
        if cods is not None and _cod6(it.get("vend")) not in cods:
            continue
        v = _liquido(it)
        if v is None:
            continue
        q = it["qtd"] if it["tipo"] == "VND" else -abs(it["qtd"] or 0)
        k = (it["tipo"], it["filial"], it.get("nf") or it.get("pedido"))
        n = notas.setdefault(k, {"nf": texto(it.get("nf")), "dt": it["dt_nf"],
                                 "vend": _cod6(it.get("vend")),
                                 "cliente": it["cliente"],
                                 "razao": it.get("razao") or "",
                                 "valor": 0.0, "vol": 0.0,
                                 "dev": it["tipo"] == "DEV",
                                 "pedido": texto(it.get("pedido"))})
        n["valor"] += v
        n["vol"] += q
        if it["tipo"] == "DEV":
            devolvidas.add((it["filial"], texto(it.get("nf"))))
            devolvidas.add(("PED", it["cliente"], texto(it.get("pedido"))))
    # (06/10) o CODIGO DO SUPERVISOR e o do VENDEDOR de cada nota (o
    # supervisor = o chefe do vendedor no cadastro do Planner)
    pessoas = {_cod6(k): v for k, v in
               (ctx.base.get("pessoas") or {}).items() if k}

    def cod_sup(cod_v):
        chefe = (pessoas.get(cod_v) or {}).get("chefe")
        return _cod6(chefe) if chefe else ""
    ls_n, cor_n = [], []
    for (tipo, fil, _k), n in sorted(notas.items(),
                                     key=lambda kv: (kv[1]["dt"], kv[1]["nf"])):
        teve_dev = n["dev"] or (fil, n["nf"]) in devolvidas or \
            ("PED", n["cliente"], n["pedido"]) in devolvidas
        ls_n.append([n["nf"], n["dt"], cod_sup(n["vend"]), n["vend"],
                     n["cliente"], n["razao"][:40], n["valor"], n["vol"]])
        cor_n.append({j: VERMELHO for j in range(8)} if teve_dev else {})
    t_ = tabela(f"Notas fiscais do mês ({len(ls_n)})",
                [col("NF", "texto", 70), col("DT. EMISSÃO", "data", 70),
                 col("CÓD. SUPERVISOR", "texto", 80),
                 col("CÓD. VENDEDOR", "texto", 80),
                 col("CÓD. CLIENTE", "texto", 70),
                 col("RAZÃO SOCIAL", "texto", 260),
                 col("VALOR NF", "moeda", 80), col("VOLUME (UN.)", "int", 60)],
                ls_n, ["devolucao" if c_ else "" for c_ in cor_n],
                total=["TOTAL", None, "", "", None, "",
                       sum(l[6] for l in ls_n), sum(l[7] for l in ls_n)]
                if ls_n else None)
    t_["cores_celulas"] = cor_n
    t_["pdf"] = {"cab": 5.4}
    # larguras fixas no PDF (06/10): os codigos estreitos, a razao com o resto
    for c_, lg in zip(t_["colunas"], (62, 54, 66, 64, 60, 380, 64, 56)):
        c_["pdf_larg"] = lg * PDF_UTIL / 806.0
    if any(cor_n):
        t_["nota_pdf"] = ("Em vermelho: devolução (a nota de devolução, com "
                          "valor negativo, e a nota de venda que teve "
                          "devolução).")
    return t_


def _abertos_da_parcial(ctx, cods):
    """{(filial, pedido): [itens]} dos pedidos em aberto (VEA) de quem esta
    na parcial (None = todo mundo)."""
    return {k: its for k, its in _pedidos(ctx, "VEA").items()
            if cods is None or _cod6(its[0].get("vend")) in cods}


def _pedidos_abertos_da_parcial(ctx, cods):
    """(10/10) PEDIDOS EM ABERTO da parcial, pedido a pedido: data, faturar
    ate (2 dias uteis), situacao do prazo, cliente, valor, volume, %
    atendido (do ftPedidos) e o credito. Atrasado em vermelho."""
    hoje = ctx.hoje
    ls, cores_, tons = [], [], []
    for (fil, ped), its in sorted(
            _abertos_da_parcial(ctx, cods).items(),
            key=lambda kv: (kv[1][0]["dt_pedido"] or date.min, kv[0][1])):
        i0 = its[0]
        dtp = i0["dt_pedido"]
        ate = ctx.mais_uteis(dtp, bd.PRAZO_FATURAR) if dtp else None
        sit = ("ATRASADO" if ate and hoje > ate else
               "VENCE HOJE" if ate and hoje == ate else "NO PRAZO")
        valor = sum(i["valor"] for i in its)
        pcts = [i["pct_at"] for i in its if i.get("pct_at") is not None]
        cred = analise_credito(ctx.credito_do_pedido(fil, i0["cliente"]),
                               valor)
        vend = _cod6(i0.get("vend"))
        razao = (i0.get("razao")
                 or texto(ctx.cliente_do_pedido(
                     fil, i0["cliente"]).get("nome")))
        ls.append([texto(ped).lstrip("0") or texto(ped), dtp, ate, sit,
                   vend, i0["cliente"], texto(razao)[:40], valor,
                   sum(i["qtd"] or 0 for i in its),
                   max(pcts) if pcts else None, cred])
        cores_.append({3: VERMELHO} if sit == "ATRASADO" else
                      {3: AMARELO_TXT} if sit == "VENCE HOJE" else {})
        tons.append("alerta" if sit == "ATRASADO" else "")
    t_ = tabela(f"Pedidos em aberto ({len(ls)})",
                [col("PEDIDO", "texto", 70), col("DT. PEDIDO", "data", 70),
                 col("FATURAR ATÉ", "data", 70), col("SITUAÇÃO", "texto", 80),
                 col("CÓD. VENDEDOR", "texto", 80),
                 col("CÓD. CLIENTE", "texto", 70),
                 col("RAZÃO SOCIAL", "texto", 240),
                 col("VALOR", "moeda", 80), col("VOLUME (UN.)", "int", 60),
                 col("% ATENDIDO", "pct", 60), col("CRÉDITO", "texto", 110)],
                ls, tons,
                total=["TOTAL", None, None, "", "", None, "",
                       sum(l[7] for l in ls), sum(l[8] for l in ls), None, ""]
                if ls else None)
    t_["cores_celulas"] = cores_
    t_["pdf"] = {"cab": 5.4}
    for c_, lg in zip(t_["colunas"],
                      (50, 52, 52, 60, 56, 54, 250, 64, 50, 52, 96)):
        c_["pdf_larg"] = lg * PDF_UTIL / 836.0
    t_["nota_pdf"] = ("Pedido em aberto = ainda não faturado (não soma no "
                      "realizado). Prazo para faturar: "
                      f"{bd.PRAZO_FATURAR} dias úteis depois do pedido."
                      if ls else "Nenhum pedido em aberto.")
    t_["nota_tom"] = "suave"
    return t_


def _kpi_abertos_da_parcial(ctx, cods):
    """O cartao PEDIDOS EM ABERTO da 1a pagina da parcial: valor (nao soma
    no realizado), pedidos, clientes, volume e atrasados."""
    peds = _abertos_da_parcial(ctx, cods)
    its_ = [i for its in peds.values() for i in its]
    valor = sum(i["valor"] for i in its_)
    atras = sum(1 for its in peds.values() if its[0]["dt_pedido"] and
                ctx.hoje > (ctx.mais_uteis(its[0]["dt_pedido"],
                                           bd.PRAZO_FATURAR) or ctx.hoje))
    n = len(peds)
    return kpi("Pedidos em aberto", moeda(valor),
               "alerta" if atras else ("info" if n else "neutro"),
               "ainda não soma no realizado" if n else "nenhum pedido em aberto",
               [("Pedidos", br(n), ""),
                ("Clientes", br(len({i["cliente"] for i in its_})), ""),
                ("Volume (un.)", br(sum(i["qtd"] or 0 for i in its_)), ""),
                ("Atrasados", br(atras), "alerta" if atras else "")])


def destinatarios_parcial(ctx, raiz=None):
    """Quem recebe a parcial por e-mail: gerente, supervisores e
    vendedores ATIVOS do Planner que tem linha no resultado do mes, com o
    e-mail do cadastro (Planner › cadastro e alteracao de vendedor)."""
    import planner_nucleo as nu                         # noqa: PLC0415
    cfg = nu.carregar_config(Path(raiz or ctx.raiz) / "planner_config.json")
    ac = meta_do_periodo(ctx)["acomp"]["recortes"]
    tem = {("VENDEDOR", texto(l.get("chave"))) for l in ac.get("vendedor", [])}
    for c in ("supervisor", "gerente"):
        tem |= {(c.upper(), norm_nome(l.get("nome") or l.get("rotulo")))
                for l in ac.get(c, [])}
    ordem = {"GERENTE": 0, "SUPERVISOR": 1, "VENDEDOR": 2}
    # os E-MAILS EM COPIA do gerente (Metas e RV): so na parcial dele
    try:
        import meta_nucleo as mn                        # noqa: PLC0415
        par_m = mn.carregar_parametros(Path(raiz or ctx.raiz)
                                       / "meta_config.json")
        cc_ger = [texto(e).strip().lower()
                  for e in par_m.get("emails_copia_gerente") or []
                  if nu.email_valido(texto(e).strip().lower())][:5]
    except Exception:                                   # noqa: BLE001
        cc_ger = []
    saida = []
    for pz in cfg.get("pessoas") or []:
        cargo = texto(pz.get("cargo")).upper()
        if cargo not in ordem or pz.get("ativo") is False:
            continue
        chave = texto(pz.get("cod_protheus")) if cargo == "VENDEDOR" \
            else norm_nome(pz.get("nome"))
        if (cargo, chave) not in tem or not _pessoa_rh(pz) or \
                "VAGO" in norm_nome(pz.get("nome")).split() or \
                "(VAGO)" in norm_nome(pz.get("nome")):
            continue
        # EM COPIA, SEMPRE: o supervisor no e-mail do vendedor e o gerente
        # no do supervisor (o chefe do cadastro do Planner)
        chefe = ((nu.chefe_de(cfg, pz.get("cod_protheus")) or {})
                 if cargo in ("VENDEDOR", "SUPERVISOR") else {})
        if cargo == "SUPERVISOR" and texto(chefe.get("cargo")).upper() \
                not in ("", "GERENTE"):
            chefe = nu.gerente_de(cfg, pz.get("cod_protheus")) or chefe
        cc = texto(chefe.get("email")).strip().lower() \
            if chefe.get("ativo") is not False else ""
        cc = cc if nu.email_valido(cc) else ""
        cc_nome = texto(chefe.get("nome")) if cc else ""
        if cargo == "GERENTE" and cc_ger:
            cc = "; ".join(cc_ger)
            cc_nome = f"{len(cc_ger)} e-mail(s) em cópia (Metas e RV)"
        saida.append({"cargo": cargo, "cod": texto(pz.get("cod_protheus")),
                      "nome": texto(pz.get("nome")),
                      "email": texto(pz.get("email")).strip().lower(),
                      "cc": cc, "cc_nome": cc_nome})
    saida.sort(key=lambda x: (ordem[x["cargo"]], x["nome"]))
    return saida


def _devolucoes_por_chave(ctx) -> dict:
    """(22/10) {(mes da NF de devolucao, filial, vendedor): R$ devolvido}
    (os nomes como nas linhas dos farois; cache no ctx)."""
    if not hasattr(ctx, "_dev_chave"):
        d = defaultdict(float)
        for it in ctx.tabela["itens"]:
            if it["tipo"] == "DEV" and it.get("dt_nf"):
                d[(rotulo_mes(mes_de(it["dt_nf"])), ctx.filial(it["filial"]),
                   ctx.vendedor(it["vend"]))] += abs(it["valor"])
        ctx._dev_chave = d
    return ctx._dev_chave


def devolucoes_da_vista(ctx, chaves, todas, filiais_inteiras=None) -> float:
    """FATURADO = o REAL: a venda menos as devolucoes (22/10).
    As devolucoes das linhas que estao na tela: chaves = {(mes, filial,
    vendedor)} das linhas; todas = {mes: {(filial, vendedor)}} de todas as
    linhas do farol. Mes com todas as linhas na tela = todas as devolucoes
    do mes (tambem de quem nao vendeu no mes). Mes filtrado: por padrao so
    as dos pares (filial, vendedor) das linhas [SUPOSICAO: o filtro de
    cliente nao recorta a devolucao].
    T-0058 (RN-GER-002): filiais_inteiras = conjunto de filiais que o
    CHAMADOR diz estarem na tela por inteiro (recorte por estado/filial da
    nota, nunca filtro de vendedor ou supervisor): dessas desconta TODA a
    devolucao (mes, filial, *), inclusive de vendedor sem venda na filial
    no mes. So vale para as filiais com linha no mes."""
    dev = _devolucoes_por_chave(ctx)
    inteiras = set(filiais_inteiras or ())
    por_m = defaultdict(set)
    for m, f, v in chaves:
        por_m[m].add((f, v))
    tot = 0.0
    for m, ks in por_m.items():
        if ks >= (todas.get(m) or set()):
            tot += sum(x for (mm, _f, _v), x in dev.items() if mm == m)
            continue
        fils = {f for f, _v in ks} & inteiras
        tot += sum(x for (mm, f, v), x in dev.items()
                   if mm == m and (f in fils or (f, v) in ks))
    return tot


def filiais_do_recorte(linhas, filtro, i_fil, i_pessoa=()) -> frozenset:
    """Funcao pura (T-0058): as filiais das linhas SE o filtro tem a coluna
    FILIAL (recorte por estado ou filial da nota) e nenhuma coluna de
    pessoa (i_pessoa: vendedor, supervisor); senao, vazio (por par).
    i_fil: indice da coluna FILIAL ou tupla (FILIAL, outras colunas que
    tambem recortam por filial da nota, ex.: a UF do Farol de Saldo); as
    filiais vem do primeiro indice. [SUPOSICAO: FILIAL junto com outro
    filtro que nao e de pessoa (cliente, situacao) desconta a filial
    inteira.]"""
    cols = tuple(i_fil) if isinstance(i_fil, (tuple, list)) else (i_fil,)
    if not filtro or not any(filtro.get(j) for j in cols) or \
            any(filtro.get(j) for j in i_pessoa):
        return frozenset()
    return frozenset(l[cols[0]] for l in linhas)


def saldo_desconto(ctx):
    """
    FAROL DE SALDO (13/10; refeito em 22/10 pelo Alexandre): o teto de 15%
    e sobre o DESCONTO COMERCIAL - o financeiro da condicao de pagamento (a
    vista -1,71%, prazo +2,89%...) nunca gera nem consome saldo: o VLR
    TABELA ja e a tabela com o financeiro. Ate 15%: a sobra entra no saldo.
    Acima: desconta do saldo; o aprovado pelo PRICE fica fora (NO SALDO 0,
    o SALDO DO PEDIDO mostra o quanto passou). A autorizacao nao aparece
    aqui (grava no Farol de Pedidos). + o saldo do frete (5% da nota -
    frete real).
    FATURADO = o real (venda - devolucoes).
    """
    hoje = ctx.hoje
    r = novo("vc_saldo", ANA, "Farol de Saldo",
             f"Teto: {br(TETO_DESCONTO)}% de desconto comercial · VLR TABELA "
             "já com o financeiro da condição de pagamento · + saldo do "
             f"frete ({br(pct_frete_cheio(ctx), 0)}% da nota − frete real)",
             "TABELA_BAP › ftPedidos (VND e DEV) + ftCondicaoPagamentos "
             "(% ACRES. FIN.) + frete real (Farol de Entregas)")
    capa(r, ctx, anos_dos_dados(ctx))
    if not _condpag_fin(ctx):
        r["avisos"].append("A TABELA_BAP não tem o % financeiro das "
                           "condições de pagamento (ftCondicaoPagamentos).")
    saldos = saldos_dos_pedidos(ctx)
    meses = ultimos_meses(hoje, 12)
    grupos = defaultdict(list)
    for it in ctx.tabela["itens"]:
        if it["tipo"] != "VND":
            continue
        m = mes_de(it["dt_nf"])
        if m in meses:
            grupos[(m, it["filial"], it["pedido"] or it["nf"])].append(it)
    graficos_tempo(r, ctx, "Saldo (R$)", [
        (it["dt_nf"], saldo_do_item(ctx, it)) for it in ctx.tabela["itens"]
        if it["tipo"] == "VND"], "moeda", VERDE)
    # (22/10, Alexandre) simples: um VLR TABELA so (= a tabela com o
    # financeiro), sem situacao/autorizacao; o que decide na frente
    (I_MES, I_DNF, I_FIL, I_PED, I_CLI, I_VEND, I_COND, I_TAB, I_VEN,
     I_PCOM, I_SPED, I_FRT, I_CONTA, I_NF, I_SUP, I_DCOM, I_UF,
     I_CHV) = range(18)
    lim = TETO_DESCONTO + TOLERANCIA_TETO
    linhas, tons = [], []
    for (m, fil, ped), itens in grupos.items():
        i0 = itens[0]
        sp = saldos.get((fil, ped)) or saldo_do_pedido(ctx, itens, fil, ped)
        nfs = sorted({i["nf"].lstrip("0") for i in itens if i["nf"]})
        lin = [None] * 18
        lin[I_MES] = rotulo_mes(m)
        lin[I_DNF] = max(i["dt_nf"] for i in itens if i["dt_nf"])
        lin[I_FIL], lin[I_PED], lin[I_NF] = ctx.filial(fil), ped, \
            ", ".join(nfs)
        lin[I_CLI] = ctx.nome_cliente(i0["cliente"])
        lin[I_VEND] = ctx.vendedor(i0["vend"])
        lin[I_SUP] = ctx.supervisor_de(i0["vend"])
        lin[I_COND] = ctx.cond(i0["cond"])
        lin[I_TAB], lin[I_VEN] = sp["base"], sp["venda"]
        lin[I_DCOM], lin[I_PCOM] = sp["dcom"], sp["pcom"]
        lin[I_SPED], lin[I_CONTA] = sp["saldo"], sp["conta"]
        lin[I_FRT] = sp.get("frete")
        # (10/11) a UF = a da filial da nota/pedido
        lin[I_UF] = uf_da_filial(i0.get("filial")) or texto(
            ctx.cliente(i0["cliente"]).get("uf"))
        lin[I_CHV] = chave_pedido(fil, ped)
        linhas.append(lin)
        tons.append("alerta" if sp["conta"] < -0.005 else "ok")
    todas_k = defaultdict(set)
    for l in linhas:
        todas_k[l[I_MES]].add((l[I_FIL], l[I_VEND]))
    # a meta de saldo (BAP Analista > Meta de saldo), por mes
    import saldo_meta                                   # noqa: PLC0415
    metas = {rotulo_mes(k): v for k, v in saldo_meta.carregar(ctx.raiz).items()}
    meta_vend, meta_sup, meta_uf = (defaultdict(float) for _ in range(3))
    for rot_m, m_ in metas.items():
        for d in m_.get("divisao", []):
            meta_vend[(rot_m, d["vendedor"])] += d["meta"]
            meta_sup[(rot_m, d["supervisor"])] += d["meta"]
        for uf, v in (m_.get("ufs") or {}).items():
            meta_uf[(rot_m, uf)] += v
    vend_do_mes = defaultdict(set)
    for l in linhas:
        vend_do_mes[l[I_MES]].add(l[I_VEND])

    def meta_de(ls):
        """A meta das linhas na tela: todos os vendedores do mes = a meta
        das UFs; so alguns = a parte deles."""
        total = 0.0
        for m_ in {l[I_MES] for l in ls}:
            if m_ not in metas:
                continue
            vs = {l[I_VEND] for l in ls if l[I_MES] == m_}
            if vs >= vend_do_mes[m_]:
                total += sum((metas[m_].get("ufs") or {}).values())
            else:
                total += sum(meta_vend[(m_, v)] for v in vs)
        return total if any(l[I_MES] in metas for l in ls) else None

    def ating(saldo, meta):
        return saldo / meta * 100.0 if meta else None
    juntos = sorted(zip(linhas, tons), key=lambda x: (
        -(x[0][I_DNF] or date.min).toordinal(), x[0][I_PED]))
    linhas, tons = [x[0] for x in juntos], [x[1] for x in juntos]

    def resumo(ls):
        """Os numeros de um grupo de pedidos (linhas do Pedido a pedido)."""
        x = {"n": len(ls), "base": sum(l[I_TAB] for l in ls),
             "venda": sum(l[I_VEN] for l in ls),
             "dcom": sum(l[I_DCOM] for l in ls),
             "saldo": sum(l[I_CONTA] for l in ls),
             "frete": sum(l[I_FRT] or 0 for l in ls),
             "n_frete": sum(1 for l in ls if l[I_FRT] is not None)}
        x["pcom"] = pct_de(x["dcom"], x["base"])
        return x

    def cartoes(ls, filtro=None):
        x = resumo(ls)
        mt = meta_de(ls)
        dev = devolucoes_da_vista(
            ctx, {(l[I_MES], l[I_FIL], l[I_VEND]) for l in ls}, todas_k,
            filiais_do_recorte(ls, filtro, (I_FIL, I_UF), (I_VEND, I_SUP)))
        cs = [
            # (22/10, Alexandre) FATURADO = o real, ja sem as devolucoes
            kpi("Faturado", moeda(x["venda"] - dev), "neutro",
                f"devoluções {moeda(dev)}" if dev >= 0.5 else
                "sem devolução"),
            kpi("Desconto comercial", p(x["pcom"]),
                "alerta" if (x["pcom"] or 0) > TETO_DESCONTO else "ok",
                moeda(x["dcom"])),
            kpi("Saldo", moeda(x["saldo"]), "ok" if x["saldo"] >= 0
                else "alerta", f"pedidos {moeda(x['saldo'] - x['frete'])}"
                + (f" · frete {moeda(x['frete'])}" if x["n_frete"]
                   else "")),
            kpi("Saldo do frete", moeda(x["frete"]) if x["n_frete"]
                else "—", ("ok" if x["frete"] >= 0 else "alerta")
                if x["n_frete"] else "neutro",
                f"{br(x['n_frete'])} pedido(s) com frete real"
                if x["n_frete"] else "sem frete real informado"),
        ]
        if mt is not None:
            cs.append(kpi("Meta de saldo", moeda(mt),
                          "ok" if x["saldo"] >= mt else "atencao",
                          f"{p(ating(x['saldo'], mt))} atingido"))
        return cs
    mes_atual = mes_escolhido(ctx)
    r["kpis"] = cartoes([l for l in linhas if rotulo_no_periodo(ctx, l[I_MES])])
    por_mes = defaultdict(list)
    for l in linhas:
        por_mes[l[I_MES]].append(l)
    rot = [rotulo_mes(x) for x in meses]
    r["graficos"].append({
        "titulo": f"Desconto comercial mês a mês (%) · teto "
                  f"{br(TETO_DESCONTO)}%",
        "rotulos": rot, "meta": TETO_DESCONTO,
        "series": [{"nome": "desconto comercial", "cor": AZUL,
                    "valores": [resumo(por_mes[x])["pcom"] or 0
                                for x in rot]}],
        "formato": "pct"})
    cols = [None] * 18
    for i_, c_ in ((I_MES, col("MÊS", "texto", 58, oculta=True)),
                   (I_DNF, col("DATA NF", "dia", 60)),
                   (I_FIL, col("FILIAL", "texto", 86)),
                   (I_PED, col("PEDIDO", "texto", 62)),
                   (I_CLI, col("CLIENTE", "texto", 190)),
                   (I_VEND, col("VENDEDOR", "texto", 150)),
                   (I_COND, col("COND. PAGTO", "texto", 110)),
                   (I_TAB, col("VLR TABELA", "moeda", 90)),
                   (I_VEN, col("VLR VENDA", "moeda", 86)),
                   (I_PCOM, col("% DESC. COM.", "pct1", 80)),
                   (I_SPED, col("SALDO DO PEDIDO", "moeda", 96)),
                   (I_FRT, col("SALDO FRETE", "moeda", 86)),
                   (I_CONTA, col("NO SALDO", "moeda", 80)),
                   (I_NF, col("NF", "texto", 60)),
                   (I_SUP, col("SUPERVISOR", "texto", 140)),
                   (I_DCOM, col("DESC. COMERCIAL", "moeda", 95)),
                   (I_UF, col("UF", "texto", 40)),
                   (I_CHV, col("CHAVE", "texto", 80, oculta=True))):
        cols[i_] = c_
    r["tabelas"].append(tabela(
        "Pedido a pedido", cols, linhas, tons,
        filtros=({"coluna": "MÊS", "padrao": mes_atual}, "FILIAL", "VENDEDOR",
                 "SUPERVISOR"),
        kpis_de=cartoes,
        recortes=[("Acima de 15% (desconta do saldo)",
                   lambda l: (l[I_PCOM] or 0) > lim),
                  ("Até 15%", lambda l: (l[I_PCOM] or 0) <= lim),
                  ("Saldo negativo", lambda l: l[I_CONTA] < -0.005),
                  ("Com saldo de frete", lambda l: l[I_FRT] is not None)]))

    def agrupar(chave_de):
        g = defaultdict(list)
        for l in linhas:
            g[(l[I_MES],) + chave_de(l)].append(l)
        return g

    def linha_resumo(m, k, ls, mt):
        """MES, chave, PEDIDOS, VLR TABELA, VLR VENDA, DESC. COMERCIAL,
        % DESC. COM., SALDO FRETE, SALDO, META SALDO, % ATING."""
        x = resumo(ls)
        return [m, k, x["n"], x["base"], x["venda"], x["dcom"], x["pcom"],
                x["frete"] if x["n_frete"] else None, x["saldo"], mt,
                ating(x["saldo"], mt)]

    def cols_resumo(nome, larg):
        return [col("MÊS", "texto", 58, oculta=True), col(nome, "texto", larg),
                col("PEDIDOS", "int", 66), col("VLR TABELA", "moeda", 105),
                col("VLR VENDA", "moeda", 105),
                col("DESC. COMERCIAL", "moeda", 100),
                col("% DESC. COM.", "pct1", 76),
                col("SALDO FRETE", "moeda", 90), col("SALDO", "moeda", 100),
                col("META SALDO", "moeda", 100), col("% ATING.", "pct", 70)]

    def tom_resumo(l):
        return "" if not l[2] else ("alerta" if l[8] < -0.005 else "ok")
    # por vendedor (mes a mes)
    lv = []
    for (m, v, sup), ls in agrupar(lambda l: (l[I_VEND], l[I_SUP])).items():
        mt = meta_vend.get((m, v)) if m in metas else None
        lr = linha_resumo(m, v, ls, mt)
        lv.append(lr[:2] + [sup] + lr[2:])
    # (16/10) todo vendedor da EQUIPE e todo mundo que tem META aparece,
    # mesmo sem pedido no mes (saldo 0, a meta dele e 0% atingido) - nos
    # meses com meta e no mes da tela
    meses_z = set(metas) | {mes_atual}
    equipe = [(ctx.vendedor(c_), ctx.supervisor_de(c_))
              for c_, p_ in (ctx.base.get("pessoas") or {}).items()
              if p_.get("cargo") == "VENDEDOR" and p_.get("ativo", True)]
    sup_meta = {}
    for rot_m, m_ in metas.items():
        for d_ in m_.get("divisao", []):
            sup_meta[(rot_m, d_["vendedor"])] = d_["supervisor"]
    ja_v = {(l_[0], l_[1]) for l_ in lv}
    for m_ in sorted(meses_z):
        quem = {v_: s_ for v_, s_ in equipe}
        quem.update({v_: sup_meta[(mm, v_)] for (mm, v_) in meta_vend
                     if mm == m_ and v_ not in quem})
        for v_, s_ in quem.items():
            if (m_, v_) in ja_v:
                continue
            mt = meta_vend.get((m_, v_)) if m_ in metas else None
            lv.append([m_, v_, s_, 0, 0.0, 0.0, 0.0, None, None, 0.0, mt,
                       ating(0.0, mt)])
    # VENDEDOR tem o SUPERVISOR na 3a coluna: os indices andam 1
    lv.sort(key=lambda l_: (l_[3] == 0, l_[9]))
    cv = cols_resumo("VENDEDOR", 200)
    cv.insert(2, col("SUPERVISOR", "texto", 170))

    def cartoes_v(ls):
        sd = sum(l[9] for l in ls)
        cs = [kpi("Saldo", moeda(sd), "ok" if sd >= 0 else "alerta"),
              kpi("Desconto comercial", p(pct_de(sum(l[6] for l in ls),
                                                 sum(l[4] for l in ls))),
                  "neutro")]
        metas_v = [l[10] for l in ls if l[10] is not None]
        if metas_v:
            cs.append(kpi("Meta de saldo", moeda(sum(metas_v)),
                          "ok" if sd >= sum(metas_v) else "atencao",
                          f"{p(ating(sd, sum(metas_v)))} atingido"))
        return cs
    r["tabelas"].append(tabela(
        "Por vendedor", cv, lv,
        ["" if not l[3] else ("alerta" if l[9] < -0.005 else "ok")
         for l in lv],
        filtros=({"coluna": "MÊS", "padrao": mes_atual}, "SUPERVISOR"),
        kpis_de=cartoes_v))
    # por supervisor e por UF, com a meta
    for titulo, i_k, meta_k, larg in (("Por supervisor", I_SUP, meta_sup, 200),
                                      ("Por UF", I_UF, meta_uf, 70)):
        ls_ = []
        for (m, k), ls in sorted(agrupar(
                lambda l, i_k=i_k: (l[i_k] or "(sem)",)).items()):
            mt = meta_k.get((m, k)) if m in metas else None
            ls_.append(linha_resumo(m, k, ls, mt))
        # (16/10) quem tem meta (supervisor/UF) aparece mesmo sem pedido
        ja_k = {(l_[0], l_[1]) for l_ in ls_}
        for (m, k), mt in sorted(meta_k.items()):
            if (m, k) not in ja_k and m in metas:
                ls_.append([m, k, 0, 0.0, 0.0, 0.0, None, None, 0.0, mt,
                            ating(0.0, mt)])
        r["tabelas"].append(tabela(
            titulo, cols_resumo(titulo[4:].upper(), larg), ls_,
            [tom_resumo(l) for l in ls_],
            filtros=({"coluna": "MÊS", "padrao": mes_atual},)))
    # (22/10, Alexandre) sem a aba Mes a mes (o mes a mes fica nos graficos)
    return r


def estoque_frw(ctx):
    """
    Farol de Estoque FRW: o que esta nas filiais BAP (FRW), quando entrou
    (linha TRF da TABELA_BAP), quanto vende por mes (media de 6 meses) e a
    NECESSIDADE do mes = venda media - estoque. Positiva: pedir para manter
    em estoque. Negativa: sobra - devolver para a PMZ.
    """
    hoje = ctx.hoje
    r = novo("pl_frw", POS, "Farol de Estoque FRW",
             "Necessidade = venda média do mês (6 meses) − estoque",
             "TABELA_BAP › ftEstoqueBap + ftPedidos (TRF e VND)")
    capa(r, ctx, anos_dos_dados(ctx))
    trfs = ctx.tabela.get("transferencias", [])
    graficos_tempo(r, ctx, "Entradas na FRW (unidades)",
                   [(t["data"], t["qtd"]) for t in trfs], "num", AZUL)
    d6 = hoje - timedelta(days=183)
    venda = defaultdict(float)
    preco = defaultdict(list)
    for it in ctx.tabela["itens"]:
        if it["tipo"] != "VND" or not it["dt_nf"]:
            continue
        if it["dt_nf"] >= d6:
            venda[(it["filial"], it["cod"])] += it["qtd"]
        if it["qtd"] > 0:
            preco[it["cod"]].append(it["valor"] / it["qtd"])
    entrada = {}
    d12 = hoje - timedelta(days=365)
    for t in trfs:
        if not t["data"]:
            continue
        k = (t["filial"], t["cod"])
        e = entrada.setdefault(k, {"ult": None, "qtd_ult": 0.0, "prim": None})
        if e["ult"] is None or t["data"] > e["ult"]:
            e["ult"], e["qtd_ult"] = t["data"], t["qtd"]
        elif t["data"] == e["ult"]:
            e["qtd_ult"] += t["qtd"]
        if e["prim"] is None or t["data"] < e["prim"]:
            e["prim"] = t["data"]
    estq = defaultdict(lambda: {"qtd": 0.0, "custo": 0.0, "desc": ""})
    for e in ctx.tabela["estoque"]:
        x = estq[(e["filial"], e["cod"])]
        x["qtd"] += e["qatu"]
        x["custo"] = x["custo"] or e["custo"]
        x["desc"] = x["desc"] or e["desc"]
    chaves = set(estq) | {k for k, v in venda.items() if v > 0} | \
        {k for k, e in entrada.items() if e["ult"] and e["ult"] >= d12}
    linhas, tons = [], []
    for fil, cod in chaves:
        x = estq.get((fil, cod), {"qtd": 0.0, "custo": 0.0, "desc": ""})
        e = entrada.get((fil, cod), {})
        media = venda.get((fil, cod), 0.0) / 6.0
        nec = round(media - x["qtd"])
        acao = "PEDIR" if nec > 0 else ("DEVOLVER À PMZ" if nec < 0 else "OK")
        ps = preco.get(cod)
        cu = x["custo"] or (sum(ps) / len(ps) if ps else 0.0)
        linhas.append([ctx.filial(fil), ctx.categoria_bap(cod),
                       ctx.familia(cod), cod,
                       ctx.produto(cod) or x["desc"], e.get("ult"),
                       e.get("qtd_ult") or None,
                       (hoje - e["ult"]).days if e.get("ult") else None,
                       x["qtd"], round(media, 1), nec, acao, nec * cu,
                       # (15/10) SISTEMA e LINHA do catalogo, no fim
                       ctx.sistema(cod), ctx.linha(cod)])
        tons.append({"PEDIR": "atencao", "DEVOLVER À PMZ": "alerta"}.get(acao,
                                                                        "ok"))
    juntos = sorted(zip(linhas, tons), key=lambda z: (z[0][0], -abs(z[0][10])))
    linhas = [z[0] for z in juntos]
    tons = [z[1] for z in juntos]
    entradas_mes = sum(t["qtd"] for t in trfs if no_mes(ctx, t["data"]))

    def cartoes(ls, com_entradas=True):
        com = [l for l in ls if l[8] > 0]
        pedir = [l for l in ls if l[11] == "PEDIR"]
        dev = [l for l in ls if l[11] == "DEVOLVER À PMZ"]
        parado = sum(1 for l in com if not l[9])
        saida = [
            kpi("SKUs em estoque", br(len(com)), "neutro",
                f"{br(sum(l[8] for l in com))} unidades"),
            kpi("Pedir", br(len(pedir)), "atencao" if pedir else "ok",
                f"{br(sum(l[10] for l in pedir))} un. · "
                f"{moeda(sum(l[12] for l in pedir))}"),
            kpi("Devolver à PMZ", br(len(dev)), "alerta" if dev else "ok",
                f"{br(-sum(l[10] for l in dev))} un. · "
                f"{moeda(-sum(l[12] for l in dev))}"),
            kpi("Sem venda em 6 meses", br(parado),
                "alerta" if parado else "ok", "com estoque"),
        ]
        if com_entradas:
            saida.append(kpi(f"Entradas {no_periodo_txt(ctx)}", br(entradas_mes), "neutro",
                             "unidades (TRF)"))
        return saida
    r["kpis"] = cartoes(linhas)
    cols = [col("FILIAL", "texto", 95), col("CATEGORIA", "texto", 100),
            col("FAMÍLIA", "texto", 130), col("PRODUTO", "texto", 120),
            col("DESCRIÇÃO", "texto", 260), col("ENTRADA NA FRW", "dia", 90),
            col("QTD ENTRADA", "num", 80), col("DIAS NA FRW", "int", 80),
            col("ESTOQUE", "num", 70), col("VENDA MÊS (MÉD. 6M)", "num2", 120),
            col("NECESSIDADE", "int", 90), col("AÇÃO", "texto", 120),
            col("VALOR", "moeda", 95), col("SISTEMA", "texto", 110),
            col("LINHA", "texto", 90)]
    r["tabelas"].append(tabela(
        "Estoque FRW", cols, linhas, tons,
        filtros=("FILIAL",) + FILTROS_PRODUTO,
        kpis_de=lambda ls: cartoes(ls, False),
        recortes=[("Pedir (necessidade positiva)", lambda l: l[10] > 0),
                  ("Devolver à PMZ (necessidade negativa)",
                   lambda l: l[10] < 0),
                  ("Com estoque", lambda l: l[8] > 0)]))
    if not trfs:
        r["avisos"].append("Sem linhas TRF na TABELA_BAP.")
    return r


TOM_EXPOSITOR = {"Entregue": "ok", "Contrato assinado": "azul",
                 "Solicitado": "atencao", "Cancelado": "alerta",
                 "Devolvido": "cinza"}


def _dias_txt(n) -> str:
    n = round(n)
    return f"{br(n)} dia" + ("" if n == 1 else "s")


def farol_expositores(ctx):
    """Farol de Expositores do Trade Marketing (BATERIAS, PECAS,
    LUBRIFICANTES): o acompanhamento editavel + por estado e por status.
    O periodo (mes ou TODOS OS MESES) vale pela DATA DA SOLICITACAO; registro
    sem data so entra em TODOS OS MESES. Abre em TODOS OS MESES."""
    import expositores as ex                            # noqa: PLC0415
    ctx.params.setdefault("MÊS", TODOS_MESES)          # abre no ano todo
    r = novo("tm_expositores", TRADE, "Farol de Expositores",
             "Baterias · Peças · Lubrificantes",
             "RELATORIOS › ACOMPANHAMENTO_EXPOSITORES.xlsx")
    r["editar"] = f"RELATORIOS/{ex.ARQUIVO}"
    regs = ex.ler(ctx.raiz)
    capa(r, ctx, sorted({x["data"].year for x in regs if x.get("data")}
                        | {ctx.hoje.year}))
    graficos_tempo(r, ctx, "Expositores solicitados",
                   [(x["data"], x["qtd"] or 0) for x in regs], "num", AZUL)
    assinados = [(x["data_assinatura"], x["qtd"] or 0)
                 for x in regs if x.get("data_assinatura")]
    if assinados:
        ano = periodo(ctx)[0]
        por_m = defaultdict(float)
        for d, q in assinados:
            if d.year == ano:
                por_m[d.month] += q
        ate = 12 if ano < ctx.hoje.year else max(ctx.hoje.month, 1)
        r["graficos"].insert(1, {
            "titulo": f"Contratos assinados · mês a mês {ano}", "largo": True,
            "rotulos": [MESES[m] for m in range(1, ate + 1)],
            "series": [{"nome": "Assinados", "cor": VERDE,
                        "valores": [por_m[m] for m in range(1, ate + 1)]}],
            "formato": "num"})
    if not ex.caminho(ctx.raiz).exists():
        r["avisos"].append("Acompanhamento de expositores ainda não criado: "
                           "use NOVO para o primeiro registro.")
    ordem = {s_: n for n, s_ in enumerate(ex.STATUS)}
    regs.sort(key=lambda x: (ordem.get(x["status"], 9), x["uf"], x["cidade"]))
    I_ST, I_MES, I_SOL, I_ASS, I_DIAS, I_COD, I_CLI, I_DESC, I_CAT, I_QTD, \
        I_CID, I_UF, I_OBS = range(13)
    SEM_DATA = "(sem data)"

    def dias_p_assinar(sol, ass):
        return (ass - sol).days if sol and ass else None
    linhas, tons = [], []
    for x in regs:
        linhas.append([x["status"],
                       rotulo_mes(mes_de(x["data"])) if x["data"] else SEM_DATA,
                       x["data"], x["data_assinatura"],
                       dias_p_assinar(x["data"], x["data_assinatura"]),
                       x["cod_cliente"], x["cliente"], x["descricao"],
                       x["categoria"], int(x["qtd"] or 0), x["cidade"],
                       x["uf"], x["observacoes"], x["atualizado_em"],
                       x["chave"]])
        tons.append(TOM_EXPOSITOR.get(x["status"], ""))
    ATIVOS = ("Solicitado", "Contrato assinado", "Entregue")

    def no_periodo(l):                  # sem data: so em TODOS OS MESES
        if l[I_MES] == SEM_DATA:
            return todos_os_meses(ctx)
        return rotulo_no_periodo(ctx, l[I_MES])

    def cartoes(ls):
        q = defaultdict(int)
        for l in ls:
            q[l[I_ST]] += l[I_QTD]
        sem = sum(1 for l in ls if not l[I_COD])
        prazos = [l[I_DIAS] for l in ls if l[I_DIAS] is not None]
        return [
            kpi("Expositores", br(sum(q[s_] for s_ in ATIVOS)), "neutro",
                f"{br(len({l[I_CLI] for l in ls if l[I_ST] in ATIVOS}))} "
                f"clientes · {br(sem)} sem código"),
            kpi("Entregues", br(q["Entregue"]), "ok"),
            kpi("Contrato assinado", br(q["Contrato assinado"]), "neutro"),
            kpi("Solicitados", br(q["Solicitado"]),
                "atencao" if q["Solicitado"] else "ok"),
            kpi("Prazo p/ assinar",
                _dias_txt(sum(prazos) / len(prazos)) if prazos else "—",
                "info", "da solicitação à assinatura"),
            kpi("Cancelados / devolvidos",
                br(q["Cancelado"] + q["Devolvido"]),
                "alerta" if q["Cancelado"] + q["Devolvido"] else "ok"),
        ]
    do_periodo = [l for l in linhas if no_periodo(l)]
    r["kpis"] = cartoes(do_periodo)
    cols = [col("STATUS", "texto", 138), col("MÊS", "texto", 58, oculta=True),
            col("SOLICITAÇÃO", "dia", 74), col("ASSINATURA", "dia", 74),
            col("DIAS", "int", 44), col("CÓD. CLIENTE", "texto", 90),
            col("CLIENTE", "texto", 260),
            col("DESCRIÇÃO DO EXPOSITOR", "texto", 240),
            col("CATEGORIA", "texto", 105), col("QTD", "int", 50),
            col("CIDADE", "texto", 150), col("UF", "texto", 36),
            col("OBSERVAÇÕES", "texto", 320), col("ATUALIZADO", "dia", 80)]
    cad = ex.carregar_cadastro(ctx.raiz)
    clientes = sorted(f"{c['cod']} - {c.get('fantasia') or c.get('nome')}"
                      for c in ctx.base["clientes"])
    cidades = sorted({texto(c.get("cidade")).upper()
                      for c in ctx.base["clientes"] if c.get("cidade")})
    nomes_exp = sorted({i["nome"] for i in cad} |
                       {x["descricao"] for x in regs if x["descricao"]})

    def ao_mudar(linha):
        cod, nome = ex.separar_cliente(texto(linha[I_CLI]))
        linha[I_CLI] = nome
        if cod:
            linha[I_COD] = cod
        linha[I_DIAS] = dias_p_assinar(linha[I_SOL], linha[I_ASS])
        linha[I_MES] = (rotulo_mes(mes_de(linha[I_SOL])) if linha[I_SOL]
                        else SEM_DATA)
    datas = datas_para_escolher(ctx.hoje, 180)
    edicao = {"arquivo": f"RELATORIOS/{ex.ARQUIVO}", "aba": ex.ABA,
              "modulo": "expositores", "chave": len(cols), "novo": True,
              "padroes_novo": {"status": "Solicitado", "qtd": "1",
                               "data": f"{ctx.hoje:%d/%m/%Y}"},
              "ao_mudar": ao_mudar,
              "campos": [
                  {"campo": "status", "rotulo": "STATUS", "opcoes": ex.STATUS,
                   "col": I_ST},
                  {"campo": "data", "rotulo": "DATA DA SOLICITAÇÃO",
                   "opcoes": datas, "data": True, "col": I_SOL},
                  {"campo": "data_assinatura", "rotulo": "DATA DA ASSINATURA",
                   "opcoes": datas, "data": True, "col": I_ASS},
                  {"campo": "cliente", "rotulo": "CLIENTE (código - nome)",
                   "opcoes": clientes, "livre": True, "col": I_CLI,
                   "mantem_caixa": True},
                  {"campo": "descricao", "rotulo": "DESCRIÇÃO DO EXPOSITOR",
                   "opcoes": nomes_exp, "livre": True, "col": I_DESC,
                   "mantem_caixa": True},
                  {"campo": "categoria", "rotulo": "CATEGORIA",
                   "opcoes": ex.CATEGORIAS, "col": I_CAT},
                  {"campo": "qtd", "rotulo": "QTD",
                   "opcoes": [str(n) for n in range(1, 21)], "col": I_QTD},
                  {"campo": "cidade", "rotulo": "CIDADE", "opcoes": cidades,
                   "livre": True, "col": I_CID},
                  {"campo": "uf", "rotulo": "UF", "opcoes": ex.UFS,
                   "col": I_UF},
                  {"campo": "observacoes", "rotulo": "OBSERVAÇÕES",
                   "opcoes": [], "livre": True, "col": I_OBS,
                   "mantem_caixa": True}]}
    r["tabelas"].append(tabela(
        "Expositores", cols, linhas, tons,
        filtros=({"coluna": "MÊS", "padrao": mes_escolhido(ctx)},
                 "STATUS", "CATEGORIA", "UF"), kpis_de=cartoes,
        recortes=[("Sem código de cliente", lambda l: not l[I_COD]),
                  ("Sem data de solicitação",
                   lambda l: l[I_MES] == SEM_DATA),
                  ("Solicitado há mais de 30 dias",
                   lambda l: l[I_ST] == "Solicitado" and l[I_SOL]
                   and (ctx.hoje - l[I_SOL]).days > 30)],
        edicao=edicao))
    # por estado (do periodo escolhido)
    por_uf = defaultdict(lambda: Counter())
    cli_uf, cid_uf = defaultdict(set), defaultdict(set)
    for l in do_periodo:
        uf = l[I_UF] or "(sem UF)"
        por_uf[uf][l[I_ST]] += l[I_QTD]
        if l[I_ST] in ATIVOS:
            por_uf[uf]["ATIVOS"] += l[I_QTD]
            cli_uf[uf].add(l[I_CLI])
            cid_uf[uf].add(l[I_CID])
    lu = []
    for uf in [u for u in ex.UFS] + sorted(set(por_uf) - set(ex.UFS)):
        c = por_uf.get(uf, Counter())
        lu.append([uf, c["ATIVOS"], c["Entregue"], c["Contrato assinado"],
                   c["Solicitado"], c["Cancelado"], c["Devolvido"],
                   len(cli_uf[uf]), len(cid_uf[uf])])
    tot = ["TOTAL"] + [sum(l[j] for l in lu) for j in range(1, 9)]
    r["tabelas"].append(tabela(
        "Por estado",
        [col("UF", "texto", 70), col("EXPOSITORES", "int", 100),
         col("ENTREGUES", "int", 90), col("CONTRATO ASSINADO", "int", 130),
         col("SOLICITADOS", "int", 95), col("CANCELADOS", "int", 95),
         col("DEVOLVIDOS", "int", 95), col("CLIENTES", "int", 80),
         col("CIDADES", "int", 80)],
        lu, ["" if l[1] else "cinza" for l in lu], total=tot))
    # por status (o resumo do farol)
    ls_ = []
    for s_ in ex.STATUS:
        reg_s = [l for l in do_periodo if l[I_ST] == s_]
        ls_.append([s_, len(reg_s), sum(l[I_QTD] for l in reg_s)])
    r["tabelas"].append(tabela(
        "Por status", [col("STATUS", "texto", 160), col("REGISTROS", "int", 90),
                       col("EXPOSITORES", "int", 100)],
        ls_, [TOM_EXPOSITOR.get(l[0], "") for l in ls_],
        total=["TOTAL", sum(l[1] for l in ls_), sum(l[2] for l in ls_)]))
    # o cadastro do Analista x o que esta em uso (tudo, sem periodo)
    em_uso = defaultdict(int)
    for l in linhas:
        if l[I_ST] in ("Entregue", "Contrato assinado"):
            em_uso[texto(l[I_DESC]).upper()] += l[I_QTD]
    por_nome = defaultdict(lambda: {"cat": "", "fil": [], "qtd": 0})
    for i in cad:
        d = por_nome[i["nome"]]
        d["cat"] = d["cat"] or i.get("categoria", "")
        d["fil"].append(f"{i.get('filial', '')} {br(i.get('qtd') or 0)}")
        d["qtd"] += int(i.get("qtd") or 0)
    lc = [[k, v["cat"], " · ".join(v["fil"]), v["qtd"], em_uso.get(k, 0),
           v["qtd"] - em_uso.get(k, 0)] for k, v in sorted(por_nome.items())]
    r["tabelas"].append(tabela(
        "Cadastro de expositores",
        [col("EXPOSITOR", "texto", 260), col("CATEGORIA FOCO", "texto", 130),
         col("FILIAIS", "texto", 300), col("CADASTRADOS", "int", 100),
         col("EM USO", "int", 80), col("SALDO", "int", 80)],
        lc, ["alerta" if l[5] < 0 else "" for l in lc]))
    return r


def curva_de_produtos(ctx) -> dict:
    """(12/10) A CURVA ABC do produto em TODOS os farois (Giro e Painel):
    pelo faturamento dos ultimos 183 dias - A ate 80%, B ate 95%, C o
    resto. Sem venda no periodo: fora do dicionario."""
    if not hasattr(ctx, "_curva_prod"):
        d180 = ctx.hoje - timedelta(days=183)
        fat = defaultdict(float)
        for it in ctx.tabela["itens"]:
            if it["tipo"] == "VND" and it["dt_nf"] and it["dt_nf"] >= d180:
                fat[it["cod"]] += it["valor"]
        curva, acum = {}, 0.0
        total = sum(fat.values()) or 1.0
        for cod, v in sorted(fat.items(), key=lambda kv: -kv[1]):
            acum += v
            curva[cod] = "A" if acum / total <= 0.80 else (
                "B" if acum / total <= 0.95 else "C")
        ctx._curva_prod = curva
    return ctx._curva_prod


GIRO_ESTOQUES = ("FRW + PMZ", "FRW", "PMZ")
# REPOSICAO (16/10, Alexandre): a compra demora em media 45 dias para
# chegar. Com 45 dias de estoque (ou mais) da para comprar sem faltar; com
# menos, faltam (45 - cobertura) dias - a VENDA PERDIDA PREVISTA e esses
# dias x a venda media por dia (R$). Ex.: vende R$ 1.000/dia e tem estoque
# para 30 dias -> 15 dias de ruptura -> R$ 15.000 de venda perdida.
# NECESSIDADE DE COMPRA = curva A e B que venderam em 90 dias com menos de
# 45 dias de cobertura. SUGESTAO = venda/dia x (45 de chegada + 90 de
# venda depois de chegar) - estoque.
# O farol e em UNIDADES: o unico R$ e a venda perdida.
GIRO_PRAZO_CHEGADA = 45
GIRO_DIAS_VENDA = 90
GIRO_COB_VERMELHA = 30          # na Necessidade: COB abaixo disso, vermelho


def giro_produtos(ctx):
    hoje = ctx.hoje
    base_est = ctx.param("ESTOQUE", GIRO_ESTOQUES[0])
    if base_est not in GIRO_ESTOQUES:
        base_est = GIRO_ESTOQUES[0]
    prazo = GIRO_PRAZO_CHEGADA
    r = novo("pl_giro", VEN, "Farol de Giro de Produtos",
             f"Chegada da compra: {prazo} dias · compra cobre "
             f"{GIRO_DIAS_VENDA} dias de venda · estoque {base_est}",
             "TABELA_BAP › ftEstoqueBap (FRW) + ftEstoquePMZ (lojas PMZ "
             "por filial BAP) + ftPedidos (VND)")
    capa(r, ctx, anos_dos_dados(ctx))
    r["parametros"].append({"nome": "ESTOQUE", "valor": base_est,
                            "valores": list(GIRO_ESTOQUES)})
    graficos_tempo(r, ctx, "Venda (unidades)",
                   [(it["dt_nf"], it["qtd"]) for it in ctx.tabela["itens"]
                    if it["tipo"] == "VND" and it["dt_nf"]], "num", VERDE)
    d90, d30, d180 = (hoje - timedelta(days=90), hoje - timedelta(days=30),
                      hoje - timedelta(days=183))
    notas90, cli90 = defaultdict(set), defaultdict(set)   # para as visoes
    venda = defaultdict(lambda: {"q90": 0.0, "q30": 0.0, "v90": 0.0,
                                 "ult": None})
    fat_prod = defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["tipo"] != "VND" or not it["dt_nf"]:
            continue
        k = (it["filial"], it["cod"])
        v = venda[k]
        if it["dt_nf"] >= d90:
            v["q90"] += it["qtd"]
            v["v90"] += it["valor"]
            notas90[k].add((it["filial"], it["nf"]))
            cli90[k].add(it["cliente"])
        if it["dt_nf"] >= d30:
            v["q30"] += it["qtd"]
        if v["ult"] is None or it["dt_nf"] > v["ult"]:
            v["ult"] = it["dt_nf"]
        if it["dt_nf"] >= d180:
            fat_prod[it["cod"]] += it["valor"]
    curva = curva_de_produtos(ctx)     # (12/10) a mesma do Painel
    # FRW = o estoque proprio das filiais BAP (ftEstoqueBap); PMZ = o das
    # lojas PMZ somado por filial BAP (ftEstoquePMZ). EST. = o escolhido em
    # cima (FRW + PMZ: a soma dos dois)
    frw, pmz = {}, {}
    for e in ctx.tabela["estoque"]:
        x = frw.setdefault((e["filial"], e["cod"]),
                           {"disp": 0.0, "desc": e["desc"]})
        x["disp"] += max(0.0, e["qatu"] - e["reserva"])
    for e in ctx.tabela.get("estoque_pmz") or []:
        x = pmz.setdefault((e["filial"], e["cod"]), {"disp": 0.0, "desc": ""})
        x["disp"] += max(0.0, e["qtd"])
    usa_frw = base_est in ("FRW", "FRW + PMZ")
    usa_pmz = base_est in ("PMZ", "FRW + PMZ")
    estq = {}
    for k in (set(frw) if usa_frw else set()) | (set(pmz) if usa_pmz
                                                  else set()):
        estq[k] = frw.get(k) or pmz.get(k)
    todos = []
    for k in set(estq) | {k for k, v in venda.items() if v["q90"] > 0}:
        fil, cod = k
        x = estq.get(k, {})
        v = venda.get(k, {"q90": 0.0, "q30": 0.0, "v90": 0.0, "ult": None})
        disp = ((frw.get(k, {}).get("disp", 0.0) if usa_frw else 0.0)
                + (pmz.get(k, {}).get("disp", 0.0) if usa_pmz else 0.0))
        dia = v["q90"] / 90.0
        cob = disp / dia if dia > 0 else None
        cv = curva.get(cod, "C" if cod in fat_prod else "-")
        nome = ctx.produto(cod) or x.get("desc", "")
        ab = cv in ("A", "B") and v["q90"] > 0
        parada = cv == "A" and disp > 0 and v["q30"] == 0
        ruptura = ab and disp <= 0
        comprar = ab and cob is not None and cob < prazo
        # dias sem estoque ate a compra chegar e a venda perdida neles
        d_rup = max(0.0, prazo - cob) if comprar else 0.0
        perda = d_rup * v["v90"] / 90.0
        sug = max(0, math.ceil(dia * (prazo + GIRO_DIAS_VENDA) - disp)) \
            if comprar else 0
        situ = ("RUPTURA" if ruptura else "COMPRAR" if comprar else
                "A PARADA" if parada else "OK")
        todos.append([ctx.filial(fil), cod, nome, _categoria(ctx, cod),
                      ctx.sistema(cod), ctx.familia(cod), cv, situ, disp,
                      v["q30"], v["q90"], dia,
                      (v["q90"] / disp) if disp else None, cob, v["ult"],
                      (hoje - v["ult"]).days if v["ult"] else None,
                      sug, d_rup or None,
                      # (16/10) a VENDA/DIA em R$ (90 dias): a conta da
                      # venda perdida = DIAS S/ EST. x VENDA/DIA
                      (v["v90"] / 90.0) or None, perda or None,
                      ctx.linha(cod)])
    I = {n: i for i, n in enumerate(
        ["fil", "cod", "nome", "cat", "sis", "fam", "curva", "sit", "est",
         "q30", "q90", "dia", "giro", "cob", "ult", "parado", "sug", "drup",
         "vdia_rs", "perda", "lin"])}

    def cartoes(ls):
        com = [l for l in ls if l[I["est"]] > 0]
        mix = sum(1 for l in com if l[I["q90"]] > 0)
        par = [l for l in ls if l[I["sit"]] == "A PARADA"]
        rup = [l for l in ls if l[I["sit"]] == "RUPTURA"]
        cmp_ = [l for l in ls if l[I["sug"]]]
        perda = sum(l[I["perda"]] or 0 for l in ls)
        return [
            kpi(f"Estoque {base_est}", f"{br(sum(l[I['est']] for l in ls))}"
                " un.", "info", f"{br(len(com))} SKUs com estoque"),
            kpi("Venda média por dia",
                f"{br(sum(l[I['dia']] for l in ls), 1)} un.", "neutro",
                "90 dias"),
            kpi("Venda perdida prevista", moeda(perda),
                "alerta" if perda else "ok",
                f"até a compra chegar ({prazo} dias)"),
            kpi("Em ruptura", br(len(rup)), "alerta" if rup else "ok",
                "curva A e B sem estoque"),
            kpi("Mix que gira", p(pct_de(mix, len(com))), "ok",
                "venderam em 90 dias"),
            kpi("Curva A parada", br(len(par)), "alerta" if par else "ok",
                f"{br(sum(l[I['est']] for l in par))} un. paradas"),
            kpi("Comprar", br(len(cmp_)), "atencao",
                f"{br(sum(l[I['sug']] for l in cmp_))} un. · menos de "
                f"{prazo} dias"),
        ]
    r["kpis"] = cartoes(todos)
    # ---- resumo por filial (unidades e itens; o R$ so na venda perdida)
    filiais = sorted({l[0] for l in todos})
    fin = []
    for f in filiais:
        ls = [l for l in todos if l[0] == f]
        com = [l for l in ls if l[I["est"]] > 0]
        fin.append([f, len(com), sum(l[I["est"]] for l in ls),
                    sum(l[I["q90"]] for l in ls),
                    sum(l[I["dia"]] for l in ls),
                    pct_de(sum(1 for l in com if l[I["q90"]] > 0), len(com)),
                    sum(1 for l in ls if l[I["sit"]] == "RUPTURA"),
                    sum(1 for l in ls if l[I["sug"]]),
                    sum(l[I["sug"]] for l in ls),
                    sum(1 for l in ls if l[I["sit"]] == "A PARADA"),
                    sum(l[I["perda"]] or 0 for l in ls)])
    r["graficos"].append({
        "titulo": f"Venda perdida prevista por filial (R$, até a compra "
                  f"chegar em {prazo} dias)",
        "rotulos": [l[0] for l in fin],
        "series": [{"nome": "venda perdida", "cor": VERMELHO,
                    "valores": [l[10] for l in fin]}],
        "formato": "moeda"})
    r["graficos"].append({
        "titulo": "Por filial: ruptura × comprar × curva A parada (itens)",
        "rotulos": [l[0] for l in fin],
        "series": [{"nome": "ruptura", "cor": VERMELHO,
                    "valores": [l[6] for l in fin]},
                   {"nome": "comprar", "cor": AMARELO,
                    "valores": [l[7] for l in fin]},
                   {"nome": "curva A parada", "cor": CINZA,
                    "valores": [l[9] for l in fin]}],
        "formato": "num"})

    def cartoes_fin(ls):
        perda = sum(l[10] for l in ls)
        return [
            kpi("Estoque", f"{br(sum(l[2] for l in ls))} un.", "info"),
            kpi("Venda média por dia", f"{br(sum(l[4] for l in ls), 1)} un.",
                "neutro"),
            kpi("Venda perdida prevista", moeda(perda),
                "alerta" if perda else "ok", f"até {prazo} dias"),
            kpi("Itens em ruptura", br(sum(l[6] for l in ls)), "alerta"),
            kpi("Itens a comprar", br(sum(l[7] for l in ls)), "atencao",
                f"{br(sum(l[8] for l in ls))} un."),
            kpi("Curva A parada", br(sum(l[9] for l in ls)), "atencao"),
        ]
    r["tabelas"].append(tabela(
        "Resumo por filial",
        [col("FILIAL", "texto", 120), col("SKUs C/ ESTOQUE", "int", 110),
         col("ESTOQUE UN.", "num", 95), col("VENDA 90D UN.", "num", 100),
         col("VENDA/DIA UN.", "num1", 100), col("MIX QUE GIRA", "pct", 95),
         col("ITENS EM RUPTURA", "int", 115),
         col("ITENS A COMPRAR", "int", 110),
         col("SUGESTÃO UN.", "num", 100),
         col("CURVA A PARADA (ITENS)", "int", 140),
         col("VENDA PERDIDA PREVISTA", "moeda", 150)],
        fin, ["alerta" if l[10] else "" for l in fin],
        filtros=("FILIAL",), kpis_de=cartoes_fin))
    # ---- as abas de produto (16/10): UNIDADES; CATEGORIA, SISTEMA e
    # FAMILIA na tela; codigo e descricao inteiros; titulos curtos para
    # caber numa tela so
    cols_t = [col("FILIAL", "texto", 90),
              dict(col("PRODUTO", "texto", 110), inteira=True),
              dict(col("DESCRIÇÃO", "texto", 300), inteira=True),
              col("CATEGORIA", "texto", 80), col("SISTEMA", "texto", 80),
              col("FAMÍLIA", "texto", 100), col("CURVA", "texto", 46),
              col("SITUAÇÃO", "texto", 85), col("EST.", "num", 55),
              col("VD 30D", "num", 55), col("VD 90D", "num", 55),
              col("VD/DIA", "num1", 55), col("GIRO", "num2", 48),
              col("COB (DIAS)", "num", 70), col("ÚLT. VENDA", "dia", 60),
              col("PARADO (D)", "int", 70), col("SUGESTÃO", "num", 70),
              col("DIAS S/ EST.", "num1", 80),
              col("VENDA/DIA", "moeda2", 95),
              col("VENDA PERDIDA", "moeda", 95),
              dict(col("LINHA", "texto", 80), oculta=True)]
    curtos = ["FILIAL", "CÓDIGO", "DESCRIÇÃO", "CATEGORIA", "SISTEMA",
              "FAMÍLIA", "CURVA", "SITUAÇÃO", "EST.", "30D", "90D",
              "/DIA", "GIRO", "COB (D)", "ÚLT. VENDA", "PARADO (D)",
              "SUGESTÃO", "DIAS S/ EST.", "VENDA/DIA", "VENDA PERDIDA"]
    for c, curto in zip(cols_t, curtos):
        c["pdf_nome"] = curto
    nomes_t = [c["nome"] for c in cols_t]
    grupos_pdf = [("", nomes_t[:1]), ("PRODUTO", nomes_t[1:8]),
                  (f"ESTOQUE {base_est}", nomes_t[8:9]),
                  ("VENDA (UN.)", nomes_t[9:12]), ("GIRO", nomes_t[12:16]),
                  (f"COMPRA (CHEGA EM {prazo} DIAS)", nomes_t[16:20])]
    # o que cada aba nao precisa: a SITUACAO e igual em toda a aba (ou nao
    # serve); a SUGESTAO e a VENDA PERDIDA so onde ha compra/ruptura
    esconde = {"Ruptura": ("SITUAÇÃO", "VD/DIA", "GIRO", "COB (DIAS)",
                           "PARADO (D)", "SUGESTÃO"),
               "Curva A parada": ("SITUAÇÃO", "SUGESTÃO", "DIAS S/ EST.",
                                  "VENDA/DIA", "VENDA PERDIDA"),
               "Necessidade de compra": ("SITUAÇÃO", "VD 30D", "GIRO",
                                         "VD/DIA", "ÚLT. VENDA",
                                         "PARADO (D)"),
               "Todos os produtos": ("GIRO", "VD/DIA", "ÚLT. VENDA",
                                     "PARADO (D)", "SUGESTÃO",
                                     "DIAS S/ EST.", "VENDA/DIA")}

    def pdf_giro(destaque):
        return {"compacto": True, "colapsa": ("FILIAL", "CURVA", "SITUAÇÃO"),
                "grupos": grupos_pdf, "sem_rs": True, "verticais": True,
                "zebra": True, "traco_zero": True, "data_curta": True,
                "sem_quebra": True, "corpo": 6.6, "cab": 5.8, "pad": 3,
                "contagem": "produtos", "destaque": destaque,
                "inteiras": ("PRODUTO",)}
    tom = {"RUPTURA": "alerta", "A PARADA": "atencao", "COMPRAR": "info",
           "OK": ""}
    destaque_de = {"Ruptura": ("VENDA PERDIDA",),
                   "Curva A parada": ("EST.",),
                   "Necessidade de compra": ("VENDA PERDIDA",),
                   "Todos os produtos": ()}
    # Necessidade de compra: em VERMELHO so o estoque ZERADO (na coluna
    # EST.) e a cobertura abaixo de 30 dias (na COB)
    i_est_t, i_cob_t = nomes_t.index("EST."), nomes_t.index("COB (DIAS)")
    somar = [I[k] for k in ("est", "q30", "q90", "dia", "sug", "vdia_rs",
                            "perda")]

    def total_giro(ls):
        tot = [None] * len(cols_t)
        tot[0] = "TOTAL"
        tot[1] = f"{br(len(ls))} itens"
        for j_ in somar:
            tot[j_] = sum(l[j_] or 0 for l in ls)
        return tot
    _verm = _VERM
    chip_est = [(0, *_verm), (None, None, None)]
    chip_cob = [(GIRO_COB_VERMELHA - 0.001, *_verm), (None, None, None)]
    for titulo, filtro, ordem in (
            ("Ruptura", lambda l: l[I["sit"]] == "RUPTURA",
             lambda l: -(l[I["perda"]] or 0)),
            ("Curva A parada", lambda l: l[I["sit"]] == "A PARADA",
             lambda l: -l[I["est"]]),
            ("Necessidade de compra", lambda l: l[I["sug"]] > 0,
             lambda l: (-(l[I["perda"]] or 0), l[I["cob"]] or 0)),
            ("Todos os produtos", lambda l: True,
             lambda l: (l[0], l[I["curva"]], -l[I["q90"]]))):
        ls = sorted([l for l in todos if filtro(l)], key=ordem)
        cols_aba = [dict(c, oculta=c["oculta"] or c["nome"] in
                         esconde[titulo]) for c in cols_t]
        compra = titulo == "Necessidade de compra"
        if compra:
            cols_aba[i_est_t] = dict(cols_aba[i_est_t], chip=chip_est)
            cols_aba[i_cob_t] = dict(cols_aba[i_cob_t], chip=chip_cob)
        sit_f = ("SITUAÇÃO",) if "SITUAÇÃO" not in esconde[titulo] else ()
        r["tabelas"].append(tabela(
            titulo, cols_aba, ls,
            [""] * len(ls) if compra else [tom[l[I["sit"]]] for l in ls],
            filtros=("FILIAL", "CURVA") + sit_f + FILTROS_PRODUTO,
            kpis_de=cartoes))
        # (16/10) TOTAL embaixo (segue o filtro): unidades e as colunas de
        # receita (VENDA/DIA e VENDA PERDIDA)
        r["tabelas"][-1]["total"] = total_giro(ls)
        r["tabelas"][-1]["total_de"] = total_giro
        if compra:          # o mesmo vermelho no Excel e no PDF
            r["tabelas"][-1]["cores_celulas"] = [
                {**({i_est_t: VERMELHO} if l[I["est"]] <= 0 else {}),
                 **({i_cob_t: VERMELHO} if l[I["cob"]] is not None
                    and l[I["cob"]] < GIRO_COB_VERMELHA else {})}
                for l in ls]
        r["tabelas"][-1]["pdf"] = pdf_giro(destaque_de[titulo])
    # ---- as visoes POR FAMILIA e POR CATEGORIA (unidades): SKUs, estoque,
    # venda, notas e clientes de cada uma, com o % do total. FILIAL = TODAS
    # soma a rede; escolhendo uma filial, so ela.
    fil_cod = {}
    for (fil, cod) in set(estq) | set(venda):
        fil_cod[(ctx.filial(fil), cod)] = (fil, cod)
    for titulo, rotulo, chave in (
            ("Por família", "FAMÍLIA", lambda l: l[I["fam"]]),
            ("Por categoria", "CATEGORIA", lambda l: l[I["cat"]])):
        grupos = defaultdict(list)
        for l in todos:
            g = chave(l) or "(SEM)"
            grupos[(TODAS_FILIAIS, g)].append(l)
            grupos[(l[0], g)].append(l)
        tot_f = defaultdict(lambda: {"skus": 0, "un": 0.0, "q90": 0.0,
                                     "nf": set()})
        agreg = {}
        for (fil, g), ls in grupos.items():
            nf, cl = set(), set()
            for l in ls:
                k = fil_cod.get((l[0], l[I["cod"]]))
                if k:
                    nf |= notas90.get(k, set())
                    cl |= cli90.get(k, set())
            x = {"skus": len({l[I["cod"]] for l in ls}),
                 "com_est": len({l[I["cod"]] for l in ls if l[I["est"]] > 0}),
                 "giram": len({l[I["cod"]] for l in ls if l[I["q90"]] > 0}),
                 "un": sum(l[I["est"]] for l in ls),
                 "q90": sum(l[I["q90"]] for l in ls),
                 "nf": nf, "cli": cl,
                 "rup": sum(1 for l in ls if l[I["sit"]] == "RUPTURA"),
                 "par": sum(1 for l in ls if l[I["sit"]] == "A PARADA"),
                 "comp": sum(1 for l in ls if l[I["sug"]]),
                 "sug": sum(l[I["sug"]] for l in ls),
                 "perda": sum(l[I["perda"]] or 0 for l in ls)}
            agreg[(fil, g)] = x
            t = tot_f[fil]
            t["skus"] += x["skus"]
            t["un"] += x["un"]
            t["q90"] += x["q90"]
            t["nf"] |= nf
        linhas_g, tons_g = [], []
        for (fil, g), x in sorted(agreg.items(), key=lambda kv: (
                kv[0][0] != TODAS_FILIAIS, kv[0][0], -kv[1]["q90"],
                -kv[1]["un"])):
            t = tot_f[fil]
            linhas_g.append([
                fil, g, x["skus"], pct_de(x["skus"], t["skus"]), x["com_est"],
                x["giram"], pct_de(x["giram"], x["com_est"]), x["un"],
                pct_de(x["un"], t["un"]), x["q90"], pct_de(x["q90"], t["q90"]),
                len(x["nf"]), pct_de(len(x["nf"]), len(t["nf"])),
                len(x["cli"]),
                x["q90"] / len(x["nf"]) if x["nf"] else 0.0,
                x["rup"], x["par"], x["comp"], x["sug"], x["perda"]])
            tons_g.append("alerta" if x["rup"] else "atencao" if x["par"]
                          else "")

        def cartoes_g(ls):
            ls = ls or []
            return [
                kpi("SKUs", br(sum(l[2] for l in ls)), "neutro",
                    f"{br(sum(l[4] for l in ls))} com estoque"),
                kpi("Estoque", f"{br(sum(l[7] for l in ls))} un.", "info"),
                kpi("Venda 90 dias", f"{br(sum(l[9] for l in ls))} un.",
                    "neutro"),
                kpi("Mix que gira", p(pct_de(sum(l[5] for l in ls),
                                             sum(l[4] for l in ls))), "ok",
                    "SKUs com estoque que venderam em 90 dias"),
                kpi("Venda perdida prevista", moeda(sum(l[19] for l in ls)),
                    "alerta" if sum(l[19] for l in ls) else "ok",
                    f"ruptura {br(sum(l[15] for l in ls))}"),
                kpi("Comprar", br(sum(l[17] for l in ls)), "atencao",
                    f"{br(sum(l[18] for l in ls))} un.")]
        r["tabelas"].insert(len(r["tabelas"]) - 1, tabela(
            titulo,
            # (16/10) titulos curtos: tudo numa tela so
            [dict(col("FILIAL", "texto", 120), inteira=True),
             dict(col(rotulo, "texto", 150), inteira=True),
             col("SKUs", "int", 50), col("% SKUs", "pct", 55),
             col("C/ EST.", "int", 55), col("GIRAM", "int", 55),
             col("MIX", "pct", 50), col("EST. UN.", "num", 75),
             col("% EST.", "pct", 55), col("VD 90D", "num", 65),
             col("% VD", "pct", 50), col("NOTAS", "int", 55),
             col("% NOTAS", "pct", 60), col("CLIENTES", "int", 65),
             dict(col("UN./NOTA", "num2", 65), oculta=True),
             col("RUPTURA", "int", 65), col("A PARADA", "int", 65),
             col("COMPRAR", "int", 65), col("SUGESTÃO", "num", 70),
             col("VENDA PERDIDA", "moeda", 100)],
            linhas_g, tons_g,
            filtros=({"coluna": "FILIAL", "padrao": TODAS_FILIAIS}, rotulo),
            kpis_de=cartoes_g))
    return r


TODAS_FILIAIS = "TODAS AS FILIAIS"
TODOS_VENDEDORES = "TODOS OS VENDEDORES"


# =========================================================================
# FAROL DDR (leitura)
# =========================================================================
def _linhas_do_farol(ctx, pessoa, ano, mes, com_linha=False):
    """As linhas da aba da pessoa no Farol daquele mes (ou None).
    com_linha: devolve (aba, [(n da linha na planilha, valores)])."""
    import farol_ddr                                    # noqa: PLC0415
    arq = ctx.raiz / "RELATORIOS" / f"{farol_ddr.PREFIXO}{ano}-{mes:02d}.xlsx"
    if not arq.exists():
        return (None, None) if com_linha else None
    cache = getattr(ctx, "_farois", None)
    if cache is None:
        cache = ctx._farois = {}
    st = arq.stat()
    k = (str(arq), pessoa, st.st_mtime_ns, st.st_size)
    if k not in cache:
        from openpyxl import load_workbook              # noqa: PLC0415
        wb = load_workbook(arq, read_only=True, data_only=False)
        try:
            aba = next((n for n in wb.sheetnames
                        if sem_acento(n).startswith(sem_acento(pessoa)[:12])),
                       None)
            cache[k] = (aba, [] if aba is None else [
                (n, x) for n, x in enumerate(
                    wb[aba].iter_rows(min_row=5, values_only=True), start=5)
                if x and len(x) > 3 and x[3]])
        finally:
            wb.close()
    aba, linhas = cache[k]
    if com_linha:
        return aba, linhas
    return [x for _n, x in linhas]


def farol(ctx, pessoa, area, rid):
    import calendar                                     # noqa: PLC0415
    import farol_ddr                                    # noqa: PLC0415
    ano, mes_e = periodo(ctx)
    todos = not mes_e                        # TODOS OS MESES: o ano inteiro
    m_fim = 12 if todos else mes_e
    fim = date(ano, m_fim, calendar.monthrange(ano, m_fim)[1])
    hoje = min(ctx.hoje, fim)                # mes passado: conta o mes todo
    r = novo(rid, area, f"Farol DDR · {pessoa.split()[0]}",
             f"{pessoa} · " + (str(ano) if todos
                               else f"{farol_ddr.MESES[mes_e]}/{ano}"),
             "RELATORIOS › FAROL_DDR_BAP_AAAA-MM.xlsx")
    capa(r, ctx, [ctx.hoje.year])
    m_arq = (ctx.hoje.month if ano == ctx.hoje.year else 12) if todos \
        else mes_e
    arq = ctx.raiz / "RELATORIOS" / f"{farol_ddr.PREFIXO}{ano}-{m_arq:02d}.xlsx"
    r["editar"] = str(arq.relative_to(ctx.raiz))
    # os graficos: % de pontos por dia, de todos os Farois do ano
    eventos = []
    for m_ in range(1, 13):
        ls = _linhas_do_farol(ctx, pessoa, ano, m_) or []
        for x in ls:
            d = bd.data_de(x[0])
            if not d or d > ctx.hoje or texto(x[8]).lower().startswith(
                    "ausência"):
                continue
            pts = bd.numero(x[5])
            eventos.append((d, farol_ddr.pontos_do_status(x[6], pts), pts))
    graficos_tempo(r, ctx, "% dos pontos", eventos, "pct", VERDE, "pct")
    if todos:
        por_mes = [_linhas_do_farol(ctx, pessoa, ano, m_, com_linha=True)
                   for m_ in range(1, 13)]
        linhas = None if all(x[1] is None for x in por_mes) else \
            [(None, n, x) for _a, ls in por_mes if ls for n, x in ls]
        aba = None
    else:
        aba, ls = _linhas_do_farol(ctx, pessoa, ano, mes_e, com_linha=True)
        linhas = None if ls is None else [(aba, n, x) for n, x in ls]
    if linhas is None:
        r["avisos"].append(f"Farol de {mes_e:02d}/{ano} ainda não gerado."
                           if mes_e else f"Nenhum Farol de {ano} gerado.")
        return r
    if not linhas:
        r["avisos"].append(f"{pessoa} não tem aba no Farol deste mês.")
        return r
    STATUS_NAO = farol_ddr.STATUS_NAO
    hoje_l, pend, ate, mes = [], [], [], Counter()
    for aba_, n, x in linhas:
        d = bd.data_de(x[0])
        pts = bd.numero(x[5])
        st = texto(x[6]).upper()
        motivo = texto(x[8])
        aus = motivo.lower().startswith("ausência")
        chave = f"{aba_}|{n}" if aba_ else ""
        ganho = farol_ddr.pontos_do_status(st, pts)
        if not aus:
            mes["possivel"] += pts
        if d and d <= hoje and not aus:
            mes["ate_hoje"] += pts
            mes["ganhos"] += ganho
            if not st:
                mes["sem"] += 1
                if d < hoje:
                    pend.append([d, texto(x[1]), texto(x[2]), texto(x[3]),
                                 texto(x[4]), pts, "", "", texto(x[10]),
                                 chave])
            elif st in STATUS_NAO:
                mes["nao"] += 1
            elif st == farol_ddr.PARCIAL:
                mes["parcial"] += 1
        if d and d <= hoje:
            ate.append([d, texto(x[1]), texto(x[2]), texto(x[3]), texto(x[4]),
                        pts, st, motivo, ganho, texto(x[10]), chave])
        if d == hoje:
            hoje_l.append([texto(x[2]), texto(x[3]), texto(x[4]), pts,
                           st, motivo, texto(x[10]), chave])
    pct = pct_de(mes["ganhos"], mes["ate_hoje"])
    faixa = next((t for lim, t in farol_ddr.FAIXAS if (pct or 0) / 100 >= lim),
                 farol_ddr.FAIXAS[-1][1]) if pct is not None else "—"
    r["kpis"] = [
        kpi("% até hoje", p(pct), "ok" if (pct or 0) >= 95 else
            ("atencao" if (pct or 0) >= 90 else "alerta"), faixa),
        kpi("Pontos ganhos", br(mes["ganhos"], 1 if mes["ganhos"] % 1 else 0),
            "neutro", f"de {br(mes['ate_hoje'])}"),
        kpi("Sem marcação", br(mes["sem"]), "alerta" if mes["sem"] else "ok",
            ""),
        kpi("Não entregues", br(mes["nao"]), "atencao" if mes["nao"] else "ok",
            f"{br(mes['parcial'])} parcial(is)"),
        kpi("Atividades hoje", br(len(hoje_l)), "info"),
    ]

    def tom(st):
        return ("ok" if st in (farol_ddr.ENTREGUE, "SIM") else
                "atencao" if st == farol_ddr.PARCIAL else
                "alerta" if st in STATUS_NAO else "")

    def edicao(i_status, i_motivo, i_chave):
        """STATUS e MOTIVO pela lista, gravados no Farol do mes."""
        if aba is None:
            return None
        return {"arquivo": r["editar"], "aba": aba, "modulo": "farol",
                "chave": i_chave, "campos": [
                    {"campo": "status", "rotulo": "STATUS",
                     "opcoes": list(farol_ddr.STATUS), "col": i_status,
                     "data": False},
                    {"campo": "motivo", "rotulo": "MOTIVO (parcial / não "
                     "entregue)", "opcoes": list(farol_ddr.MOTIVOS),
                     "col": i_motivo, "data": False}]}
    cols_h = [col("HORÁRIO", "texto", 120), col("ATIVIDADE", "texto", 480),
              col("PRIORIDADE", "texto", 80), col("PONTOS", "int", 60),
              col("STATUS", "texto", 130), col("MOTIVO", "texto", 190),
              col("FERRAMENTA BAP", "texto", 280)]
    r["tabelas"].append(tabela(
        "Hoje", cols_h, hoje_l, [tom(l[4]) for l in hoje_l],
        edicao=edicao(4, 5, len(cols_h))))
    cols_p = [col("DATA", "data"), col("DIA", "texto", 45),
              col("HORÁRIO", "texto", 120), col("ATIVIDADE", "texto", 440),
              col("PRIORIDADE", "texto", 80), col("PONTOS", "int", 60),
              col("STATUS", "texto", 130), col("MOTIVO", "texto", 190),
              col("FERRAMENTA BAP", "texto", 240)]
    r["tabelas"].append(tabela(
        "Pendentes de marcação", cols_p, pend, ["atencao"] * len(pend),
        edicao=edicao(6, 7, len(cols_p))))
    cols_a = [col("DATA", "data"), col("DIA", "texto", 45),
              col("HORÁRIO", "texto", 120), col("ATIVIDADE", "texto", 420),
              col("PRIORIDADE", "texto", 80), col("PONTOS", "int", 60),
              col("STATUS", "texto", 130), col("MOTIVO", "texto", 190),
              col("PONTOS GANHOS", "num", 100),
              col("FERRAMENTA BAP", "texto", 240)]
    ate.sort(key=lambda l: (l[0], l[2]), reverse=True)
    r["tabelas"].append(tabela(
        "Até hoje", cols_a, ate, [tom(l[6]) for l in ate],
        filtros=("STATUS", "PRIORIDADE"),
        edicao=edicao(6, 7, len(cols_a))))
    return r


def nome_filtro(f):
    return f["coluna"] if isinstance(f, dict) else f
def datas_para_escolher(hoje, dias=30):
    """As datas da lista (de hoje para tras), no formato da tela."""
    return [f"{hoje - timedelta(days=i):%d/%m/%Y}" for i in range(dias)]


def datas_de_previsao(hoje, frente=45, atras=15):
    """(30/10) As datas da PREVISAO de entrega: de hoje para a frente
    (45 dias) e depois as que ja passaram (15 dias)."""
    return ([f"{hoje + timedelta(days=i):%d/%m/%Y}" for i in range(frente + 1)]
            + [f"{hoje - timedelta(days=i):%d/%m/%Y}"
               for i in range(1, atras + 1)])
def _entrega_editavel(ctx, chave_col, mapa_colunas, cadastro=None,
                      uf_col=None, cidade_col=None, frete=None,
                      saldo_frete=None, situacao=None):
    """
    Os campos de ENTREGAS que a assistente muda pela tela: tudo por lista,
    menos o RESPONSAVEL (o nome do motorista, escrito; a lista so sugere os
    ja usados). A TRANSPORTADORA mostra as do cadastro que atuam na cidade
    da nota. mapa_colunas = {campo: indice da coluna na tabela}.
    frete = (col VLR NF, col LOCAL/FRETE, col VLR FRETE): refaz o frete na
    tela quando a transportadora muda.
    (16/10) "frete_real" no mapa: o VLR FRETE (REAL) que a transportadora
    cobrou, escrito (a lista sugere os 5%). saldo_frete = (col FRETE 5%,
    col SALDO FRETE): refeitos na tela.
    (30/10, Alexandre) "prevista_manual" no mapa: a DT. PREVISTA da entrega
    ajustada pela assistente (vazio = volta a calculada no Atualizar).
    situacao = (col SITUACAO, col ETAPA): a SITUACAO refeita na tela com a
    previsao e a entrega novas.
    """
    import pos_venda as pv                              # noqa: PLC0415
    import transportadoras as tr                        # noqa: PLC0415
    cad = cadastro or tr.carregar(ctx.raiz)
    datas = datas_para_escolher(ctx.hoje)
    ja_usados = sorted({texto(e.get("responsavel")).upper()
                        for e in ctx.posvenda.get("entregas", [])
                        if texto(e.get("responsavel"))})

    def transp_da_linha(linha):
        if uf_col is None:
            return tr.nomes(cad)
        return tr.opcoes_para(cad, linha[uf_col], linha[cidade_col])
    campos = [
        {"campo": "etapa", "rotulo": "ETAPA", "opcoes": pv.ETAPAS_ENTREGA},
        {"campo": "transportadora", "rotulo": "TRANSPORTADORA",
         "opcoes": tr.nomes(cad), "opcoes_de": transp_da_linha},
        {"campo": "prevista_manual", "rotulo": "DT. PREVISTA (ENTREGA)",
         "opcoes": datas_de_previsao(ctx.hoje), "data": True},
        {"campo": "entregue_em", "rotulo": "DT. REAL (ENTREGA)", "opcoes": datas,
         "data": True},
        {"campo": "responsavel", "rotulo": "RESPONSÁVEL (MOTORISTA)",
         "opcoes": ja_usados, "livre": True},
    ]
    pct_cheio = pct_frete_cheio(cadastro=cad)
    if "frete_real" in mapa_colunas and frete:
        i_vlr_, i_tipo_, _i_fr = frete

        def sugestao(linha):
            e_fr = True if i_tipo_ is None else linha[i_tipo_] == "FRETE"
            if not e_fr or not linha[i_vlr_]:
                return []
            return [br(linha[i_vlr_] * pct_cheio / 100.0, 2)]
        campos.append({"campo": "frete_real", "rotulo": "VLR FRETE (REAL)",
                       "opcoes": [], "opcoes_de": sugestao, "livre": True,
                       "numero": True,
                       "so_se": (lambda linha, i_=i_tipo_: i_ is None
                                 or linha[i_] == "FRETE")})
    for c in campos:
        c["col"] = mapa_colunas.get(c["campo"])
        c.setdefault("data", False)

    def ao_mudar(linha):
        i_pv, i_rl = mapa_colunas.get("prevista_manual"), \
            mapa_colunas.get("entregue_em")
        if situacao and i_pv is not None and i_rl is not None:
            # (30/10) situacao = (SITUACAO, ETAPA, PRAZO): o prazo na
            # coluna PRAZO e a SITUACAO pela etapa (PENDENTE/CONCLUIDA/
            # CANCELADA)
            i_st, i_et = situacao[:2]
            i_pz = situacao[2] if len(situacao) > 2 else i_st
            antiga = linha[i_st] == CONCLUIDA and not linha[i_pz]
            prev_, ent_ = bd.data_de(linha[i_pv]), bd.data_de(linha[i_rl])
            if not antiga:
                if texto(linha[i_et]).upper() == "CANCELADA":
                    linha[i_pz] = "" if i_pz != i_st else "—"
                elif prev_ and ent_:
                    linha[i_pz] = ("NO PRAZO" if ent_ <= prev_
                                   else "ENTREGUE COM ATRASO")
                elif prev_:
                    linha[i_pz] = ("ATRASADA" if ctx.hoje > prev_
                                   else "NO PRAZO")
                if i_pz != i_st:
                    linha[i_st] = situacao_da_entrega(linha[i_et])
        if frete:
            i_vlr, i_tipo, i_frete = frete
            e_fr = True if i_tipo is None else linha[i_tipo] == "FRETE"
            i_real = mapa_colunas.get("frete_real")
            real = linha[i_real] if i_real is not None else None
            linha[i_frete] = _frete(linha[mapa_colunas["transportadora"]],
                                    linha[i_vlr], e_fr, cad,
                                    real if e_fr else None,
                                    linha[uf_col] if uf_col is not None
                                    else None,
                                    linha[cidade_col] if cidade_col
                                    is not None else None)
            if saldo_frete:
                i_ch, i_sd = saldo_frete
                ch_, sd_ = saldo_do_frete(linha[i_vlr], real, pct_cheio,
                                          e_fr)
                linha[i_ch] = ch_
                if i_sd is not None:          # (22/10) sem SALDO FRETE
                    linha[i_sd] = sd_
    return {"arquivo": "RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx",
            "aba": pv.ABA_ENT, "chave": chave_col, "campos": campos,
            "ao_mudar": ao_mudar}


def _data_tela(v):
    d = bd.data_de(v)
    return d










# =========================================================================
# RESUMO INDICADORES (Analista Comercial)
# =========================================================================
# Todos os indicadores das assistentes num lugar so: a VISAO GERAL do mes
# escolhido e uma aba por area (mes a mes, semana a semana, dia a dia),
# com META, REAL, % ATING. e NEC./DIA onde o indicador tem meta.
# As contas sao as mesmas dos farois de cada area.
META_PRAZO = 90.0          # % no prazo (o corte verde do Painel/Entregas)
META_FAROL = 95.0          # % dos pontos do Farol DDR (a faixa verde)
PESSOAS = {PRE: "Juliana Almeida", VEN: "Mayara Santos",
           POS: "Estefanie Pacheco", TRADE: "Vaga (Trade Marketing Jr.)",
           ANA: "Leandro Nunes"}
VISOES = ("MÊS A MÊS", "SEMANA A SEMANA", "DIA A DIA")


def _media_ev(vals):
    return sum(v[0] for v in vals) / len(vals) if vals else None


def _ind(area, nome, fmt, eventos=None, agg="soma", meta=None, menor=False,
         acumula=True, mensal=None):
    """Um indicador. eventos(ctx) -> [(data, valores...)] (o agg junta);
    mensal(ctx, 'AAAA-MM') -> real do mes, para o que nao tem dia a dia;
    meta(ctx, 'AAAA-MM') -> meta do mes ou None; menor = menor e melhor;
    acumula = soma no mes (a meta se reparte por dia util e tem NEC./DIA)."""
    return {"area": area, "nome": nome, "fmt": fmt, "eventos": eventos,
            "agg": agg, "meta": meta, "menor": menor, "acumula": acumula,
            "mensal": mensal}


def _fmt_ind(v, fmt):
    if v is None:
        return "—"
    if fmt == "moeda":
        return moeda(v)
    if fmt == "pct":
        return p(v)
    if fmt == "dias":
        return f"{br(v, 1)} d"
    return br(v)


def _uteis_de(ctx, ini, fim):
    """Dias uteis de ini a fim, os dois inclusive."""
    return bd.dias_uteis_entre(ini - timedelta(days=1), fim, ctx.fer) or 0


def _fim_do_mes(ano, mes):
    import calendar                                     # noqa: PLC0415
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


# ---- de onde vem cada numero (as mesmas contas dos farois)
def _par_meta(ctx):
    if not hasattr(ctx, "_par_meta"):
        try:
            import meta_nucleo as mn                    # noqa: PLC0415
            ctx._par_meta = mn.carregar_parametros(ctx.raiz / "meta_config.json")
        except Exception:                               # noqa: BLE001
            ctx._par_meta = {}
    return ctx._par_meta


def _acomp_equipe(ctx):
    """(competencia, totais do gerente) do Farol de Metas Equipe."""
    if not hasattr(ctx, "_acomp_eq"):
        try:
            dados = meta_do_periodo(ctx)     # o mes escolhido em cima
            ger = dados["acomp"]["recortes"].get("gerente") or []
            tot = Counter()
            for l in ger:
                for k in ("meta", "realizado", "meta_positivacao",
                          "positivados", "meta_visita", "visitas_realizadas"):
                    tot[k] += l.get(k) or 0
            ctx._acomp_eq = (dados["competencia"], tot)
        except Exception:                               # noqa: BLE001
            ctx._acomp_eq = ("", Counter())
    return ctx._acomp_eq


def _meta_fat(ctx, mes):
    import meta_nucleo as mn                            # noqa: PLC0415
    do_mes = mn.metas_do_mes(_par_meta(ctx).get("metas_importadas") or {}, mes)
    total = sum(v for linha in do_mes.values() for v in (linha or {}).values())
    if total > 0:
        return total
    comp, tot = _acomp_equipe(ctx)
    return (tot["meta"] or None) if comp == mes else None


def _meta_exec(ctx, chave, mes):
    exe = _par_meta(ctx).get("executivo") or {}
    v = (exe.get("metas") or {}).get(chave, {}).get(mes)
    try:
        return float(v) or None
    except (TypeError, ValueError):
        return None


def _meta_posit(ctx, mes):
    comp, tot = _acomp_equipe(ctx)
    if comp == mes and tot["meta_positivacao"]:
        return tot["meta_positivacao"]
    return _meta_exec(ctx, "positivacao", mes)


def _visitas_mes(ctx, mes):
    comp, tot = _acomp_equipe(ctx)
    return tot["visitas_realizadas"] if comp == mes else None


def _meta_visitas(ctx, mes):
    comp, tot = _acomp_equipe(ctx)
    return (tot["meta_visita"] or None) if comp == mes else None


def _meta_saldo(ctx, mes):
    import saldo_meta                                   # noqa: PLC0415
    ufs = (saldo_meta.carregar(ctx.raiz).get(mes) or {}).get("ufs") or {}
    return sum(ufs.values()) or None


def _ev_pedidos(ctx):
    evs = {}
    for it in ctx.tabela["itens"]:
        if it["tipo"] in ("VND", "VEA", "EXC") and it["dt_pedido"]:
            evs.setdefault((it["filial"], it["pedido"]),
                           (it["dt_pedido"], (it["filial"], it["pedido"])))
    return list(evs.values())


def _ev_notas(ctx, so_frete=False):
    notas = {}
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND" and it["dt_nf"]:
            if so_frete and not bd.e_frete(ctx.cliente(it["cliente"])
                                           .get("cidade")):
                continue
            notas[(it["filial"], it["nf"])] = (it["dt_nf"], 1)
    return list(notas.values())


def _ev_prazo_faturar(ctx):
    """[(data do pedido, no prazo?, dias uteis ate a 1a NF)] por pedido."""
    peds = defaultdict(lambda: [None, []])
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND" and it["dt_pedido"] and it["dt_nf"]:
            d = peds[(it["filial"], it["pedido"])]
            d[0] = it["dt_pedido"]
            d[1].append(it["dt_nf"])
    saida = []
    for dtp, nfs in peds.values():
        dias = ctx.uteis(dtp, min(nfs))
        if dias is not None:
            saida.append((dtp, 1 if dias <= bd.PRAZO_FATURAR else 0, 1, dias))
    return saida


def _ev_entregas(ctx):
    """[(entregue em, no prazo?, 1, sla em dias corridos)]."""
    ped = _pedido_da_nf(ctx)
    saida = []
    for e in ctx.posvenda.get("entregas", []):
        ent = bd.data_de(e.get("entregue_em"))
        if not ent:
            continue
        dtp, _n = ped.get((texto(e.get("filial")),
                           texto(e.get("nf")).lstrip("0")), (None, ""))
        sla = ctx.corridos(dtp, ent) if dtp else None
        ok = 1 if (e.get("situacao") or "").upper() == "NO PRAZO" else 0
        saida.append((ent, ok, 1, sla))
    return saida


def _ev_farol(pessoa):
    def ev(ctx):
        import farol_ddr                                # noqa: PLC0415
        ano = periodo(ctx)[0]
        saida = []
        for m_ in range(1, 13):
            for x in _linhas_do_farol(ctx, pessoa, ano, m_) or []:
                d = bd.data_de(x[0])
                if not d or d > ctx.hoje or texto(x[8]).lower().startswith(
                        "ausência"):
                    continue
                pts = bd.numero(x[5])
                saida.append((d, farol_ddr.pontos_do_status(x[6], pts), pts))
        return saida
    return ev


def _ev_expositores(ctx, assinados=False):
    import expositores as ex                            # noqa: PLC0415
    regs = ex.ler(ctx.raiz)
    if assinados:
        return [(x["data_assinatura"], x["qtd"] or 0) for x in regs
                if x.get("data_assinatura")]
    return [(x["data"], x["qtd"] or 0) for x in regs if x.get("data")]


def _ev_dias_assinar(ctx):
    import expositores as ex                            # noqa: PLC0415
    return [(x["data_assinatura"], (x["data_assinatura"] - x["data"]).days)
            for x in ex.ler(ctx.raiz)
            if x.get("data_assinatura") and x.get("data")]


ROTULOS_EXEC = {"faturamento": "Faturamento total",
                "positivacao": "Positivação", "despesas": "Despesas",
                "pecas": "Faturamento de peças",
                "cadastro_compra": "Cadastro com compra"}


def _executivos(ctx):
    """Os indicadores executivos (meta e real mes a mes, digitados e
    apurados no BAP Analista) - so leitura aqui."""
    try:
        linhas = ctx.executivo["painel"]["linhas"]
    except Exception:                                   # noqa: BLE001
        return []
    saida = []
    for l in linhas:
        meses = l.get("meses") or {}

        def real(c, m, ms=meses):
            cel = ms.get(m) or {}
            return cel.get("real") if cel.get("apurado") else None

        def meta(c, m, ms=meses):
            return (ms.get(m) or {}).get("meta") or None
        nome = ROTULOS_EXEC.get(l.get("chave")) or \
            texto(l.get("rotulo")).capitalize()
        fmt = "num" if "positiv" in nome.lower() or "cadastro" in \
            nome.lower() else "moeda"
        saida.append(_ind(ANA, nome, fmt, mensal=real, meta=meta,
                          menor=bool(l.get("invertido"))))
    return saida


def _ev_garantias(ctx):
    import garantias as gm                              # noqa: PLC0415
    return [(gm.data(g.get("dt_solicitacao")), 1)
            for g in gm.ler(ctx.raiz).values()
            if gm.data(g.get("dt_solicitacao"))]


def _indicadores(ctx):
    a = [
        # PRE-VENDA E FATURAMENTO
        _ind(PRE, "Pedidos digitados", "num", _ev_pedidos, "unicos"),
        _ind(PRE, "Notas faturadas", "num", _ev_notas, "conta"),
        _ind(PRE, "Faturados no prazo", "pct", _ev_prazo_faturar, "pct",
             meta=lambda c, m: META_PRAZO, acumula=False),
        _ind(PRE, "SLA de faturamento", "dias",
             lambda c: [(e[0], e[3]) for e in _ev_prazo_faturar(c)], _media_ev,
             meta=lambda c, m: float(bd.PRAZO_FATURAR), menor=True,
             acumula=False),
        _ind(PRE, "Farol DDR", "pct", _ev_farol(PESSOAS[PRE]), "pct",
             meta=lambda c, m: META_FAROL, acumula=False),
        # VENDAS E CRM
        _ind(VEN, "Faturamento líquido", "moeda",
             lambda c: _eventos_faturamento(c, liquido=True),
             meta=_meta_fat),
        _ind(VEN, "Clientes positivados", "num", _ev_positivados,
             "unicos", meta=_meta_posit),
        _ind(VEN, "Visitas", "num", mensal=_visitas_mes, meta=_meta_visitas),
        _ind(VEN, "Saldo de desconto", "moeda",
             lambda c: [(it["dt_nf"], saldo_do_item(c, it))
                        for it in c.tabela["itens"] if it["tipo"] == "VND"],
             meta=_meta_saldo),
        # (14/10) o desconto COMERCIAL do Farol de Saldo
        _ind(VEN, "Desconto comercial", "pct",
             lambda c: [(it["dt_nf"],) + tuple(reversed(base_do_item(c, it)))
                        for it in c.tabela["itens"] if it["tipo"] == "VND"],
             "pct", meta=lambda c, m: TETO_DESCONTO, menor=True,
             acumula=False),
        _ind(VEN, "Farol DDR", "pct", _ev_farol(PESSOAS[VEN]), "pct",
             meta=lambda c, m: META_FAROL, acumula=False),
        # POS-VENDA E LOGISTICA
        _ind(POS, "Notas entregues", "num",
             lambda c: [(e[0], 1) for e in _ev_entregas(c)], "conta"),
        _ind(POS, "Entregues no prazo", "pct", _ev_entregas, "pct",
             meta=lambda c, m: META_PRAZO, acumula=False),
        _ind(POS, "SLA de entrega", "dias",
             lambda c: [(e[0], e[3]) for e in _ev_entregas(c)
                        if e[3] is not None], _media_ev,
             meta=lambda c, m: float(bd.PRAZO_ENTREGAR), menor=True,
             acumula=False),
        _ind(POS, "Notas com frete", "num",
             lambda c: _ev_notas(c, so_frete=True), "conta"),
        # (14/10) as garantias solicitadas no periodo (Farol de Garantias)
        _ind(POS, "Garantias abertas", "num", _ev_garantias, "conta",
             menor=True),
        _ind(POS, "Valor devolvido", "moeda",
             lambda c: [(it["dt_nf"], abs(it["valor"]))
                        for it in c.tabela["itens"] if it["tipo"] == "DEV"],
             menor=True),
        _ind(POS, "Inadimplência", "pct",
             lambda c: [(f["data"], f["atraso"], f["aberto"])
                        for f in c.inadimplencia.get("fotos") or []],
             lambda vals: pct_de(vals[-1][0], vals[-1][1]) if vals else None,
             menor=True, acumula=False),
        _ind(POS, "Recuperado de atraso", "moeda",
             lambda c: [(f["data"], f["recuperado"] or 0)
                        for f in c.inadimplencia.get("fotos") or []]),
        _ind(POS, "Farol DDR", "pct", _ev_farol(PESSOAS[POS]), "pct",
             meta=lambda c, m: META_FAROL, acumula=False),
        # TRADE MARKETING
        _ind(TRADE, "Expositores solicitados", "num", _ev_expositores),
        _ind(TRADE, "Contratos assinados", "num",
             lambda c: _ev_expositores(c, assinados=True)),
        _ind(TRADE, "Dias até assinar", "dias", _ev_dias_assinar, _media_ev,
             menor=True, acumula=False),
    ]
    return a + _executivos(ctx)


def _calcular_ind(ctx, ind, ano, mes):
    """Os numeros de um indicador: por mes do ano, por semana e por dia do
    mes escolhido, a meta de cada periodo, o atingimento e a NEC./DIA."""
    hoje = ctx.hoje
    ate = 12 if ano < hoje.year else (max(hoje.month, mes or 1)
                                      if ano == hoje.year else (mes or 12))
    erro = ""
    por_mes, por_dia, por_sem = defaultdict(list), defaultdict(list), \
        defaultdict(list)
    if ind["eventos"]:
        try:
            evs = ind["eventos"](ctx) or []
        except Exception as e:                          # noqa: BLE001
            evs, erro = [], str(e)
        for ev in evs:
            d = ev[0]
            if not d:
                continue
            if isinstance(d, datetime):
                d = d.date()
            if d.year != ano:
                continue
            por_mes[d.month].append(ev[1:])
            if mes and d.month == mes:
                por_dia[d].append(ev[1:])
                por_sem[semana_de(d)].append(ev[1:])
            elif not mes:
                por_sem[semana_de(d)].append(ev[1:])

    def junta(vals):
        if not vals:
            return 0 if ind["acumula"] else None
        return _agregar(vals, ind["agg"])

    def real_do_mes(m):
        if ind["mensal"]:
            try:
                return ind["mensal"](ctx, f"{ano}-{m:02d}")
            except Exception:                           # noqa: BLE001
                return None
        return junta(por_mes[m])

    def meta_do_mes(m):
        if not ind["meta"]:
            return None
        try:
            return ind["meta"](ctx, f"{ano}-{m:02d}")
        except Exception:                               # noqa: BLE001
            return None

    def meta_parcial(m, ini, fim):
        """A meta de um pedaco do mes: a do mes pelos dias uteis."""
        mm = meta_do_mes(m)
        if mm is None or not ind["acumula"]:
            return mm
        du = _uteis_de(ctx, date(ano, m, 1), _fim_do_mes(ano, m))
        return mm * _uteis_de(ctx, ini, fim) / du if du else None

    def ating(real, meta):
        if real is None or not meta:
            return None
        if ind["menor"]:
            return meta / real * 100.0 if real > 0 else 100.0
        return real / meta * 100.0

    meses = []
    for m in range(1, ate + 1):
        r_, m_ = real_do_mes(m), meta_do_mes(m)
        meses.append((MESES[m], m, m_, r_, ating(r_, m_)))
    semanas, dias = [], []
    if not ind["mensal"]:
        for s in sorted(por_sem):
            ini = max(s, date(ano, mes or 1, 1))
            fim = min(s + timedelta(days=6),
                      _fim_do_mes(ano, mes) if mes else date(ano, 12, 31))
            r_ = junta(por_sem[s])
            m_ = meta_parcial(ini.month, ini, fim)
            semanas.append((f"{ini:%d/%m} a {fim:%d/%m}", m_, r_,
                            ating(r_, m_)))
        if mes:
            d = date(ano, mes, 1)
            while d <= min(_fim_do_mes(ano, mes), hoje):
                r_ = junta(por_dia[d])
                util = d.weekday() < 5 and d not in ctx.fer
                if por_dia[d] or util:
                    m_ = meta_parcial(mes, d, d) if util else None
                    dias.append((f"{d:%d/%m} {DIAS_SEMANA[d.weekday()]}",
                                 m_, r_, ating(r_, m_)))
                d += timedelta(days=1)
    # o periodo escolhido (o mes, ou o ano em TODOS OS MESES)
    if mes:
        real, meta = real_do_mes(mes), meta_do_mes(mes)
        ant = real_do_mes(mes - 1) if mes > 1 else None
    else:
        reais = [x[3] for x in meses if x[3] is not None]
        if ind["mensal"] or not ind["eventos"]:
            real = (sum(reais) if ind["acumula"] else
                    (sum(reais) / len(reais) if reais else None)) \
                if reais else None
        else:
            real = junta([v for m in range(1, ate + 1) for v in por_mes[m]])
        metas = [x[2] for x in meses if x[2] is not None]
        meta = (sum(metas) if ind["acumula"] else
                sum(metas) / len(metas)) if metas else None
        ant = None
    nec = None
    if mes and ind["acumula"] and meta and real is not None and \
            (ano, mes) == (hoje.year, hoje.month):
        resta = _uteis_de(ctx, hoje, _fim_do_mes(ano, mes))
        if resta:
            nec = max(0.0, (meta - real) if not ind["menor"] else 0.0) / resta
    var = ((real - ant) / abs(ant) * 100.0
           if real is not None and ant not in (None, 0) else None)
    return {"meta": meta, "real": real, "ating": ating(real, meta),
            "nec": nec, "anterior": ant, "var": var, "meses": meses,
            "semanas": semanas, "dias": dias, "erro": erro}


def _tom_ating(a):
    if a is None:
        return ""
    return "ok" if a >= 100 else ("alerta" if a < 80 else "atencao")


def resumo_indicadores(ctx):
    r = novo("an_resumo", ANA, "Resumo Indicadores",
             "Indicadores de todas as áreas",
             "Os mesmos números dos faróis de cada área")
    capa(r, ctx, anos_dos_dados(ctx))
    ano, mes = periodo(ctx)
    rot_per = f"{MESES[mes]}/{str(ano)[2:]}" if mes else str(ano)
    inds = _indicadores(ctx)
    calc = [(ind, _calcular_ind(ctx, ind, ano, mes)) for ind in inds]

    # ---- a visao geral
    cols = [col("ÁREA", "texto", 170), col("INDICADOR", "texto", 190),
            col("META", "valor", 110), col("REAL", "valor", 110),
            col("% ATING.", "pct", 80), col("NEC./DIA", "valor", 100),
            col("MÊS ANTERIOR", "valor", 110), col("VARIAÇÃO", "pct", 80)]
    linhas, tons = [], []
    for ind, c in calc:
        f = ind["fmt"]
        linhas.append([ind["area"], ind["nome"], _fmt_ind(c["meta"], f),
                       _fmt_ind(c["real"], f), c["ating"],
                       _fmt_ind(c["nec"], f) if c["nec"] is not None else "",
                       _fmt_ind(c["anterior"], f) if mes else "",
                       c["var"]])
        tons.append(_tom_ating(c["ating"]))
    r["tabelas"].append(tabela(f"Visão geral · {rot_per}", cols, linhas, tons,
                               filtros=("ÁREA",)))

    # ---- os cartoes: quantos na meta e o atingimento medio de cada area
    com_meta = [(ind, c) for ind, c in calc if c["ating"] is not None]
    na_meta = sum(1 for _i, c in com_meta if c["ating"] >= 100)
    abaixo = sum(1 for _i, c in com_meta if c["ating"] < 80)
    r["kpis"] = [kpi(f"Na meta · {rot_per}", f"{na_meta} de {len(com_meta)}",
                     "ok" if com_meta and na_meta == len(com_meta) else
                     "neutro"),
                 kpi("Abaixo de 80%", br(abaixo), "alerta" if abaixo else "ok")]
    for area in (PRE, VEN, POS, TRADE, ANA):
        ats = [min(c["ating"], 150) for ind, c in com_meta
               if ind["area"] == area]
        if ats:
            med = sum(ats) / len(ats)
            r["kpis"].append(kpi(area, p(med), _tom_ating(med) or "neutro",
                                 f"{len(ats)} com meta"))

    # ---- os graficos: atingimento de cada indicador e na meta mes a mes
    if com_meta:
        r["graficos"].append({
            "titulo": f"% de atingimento · {rot_per}", "largo": True,
            "rotulos": [ind["nome"] if ind["nome"] != "Farol DDR" else
                        f"DDR {PESSOAS[ind['area']].split()[0]}"
                        for ind, _c in com_meta],
            "series": [{"nome": "% ating.", "cor": VERDE,
                        "valores": [round(c["ating"], 1)
                                    for _i, c in com_meta]}],
            "formato": "pct"})
    ate = len(calc[0][1]["meses"]) if calc else 0
    if ate:
        r["graficos"].append({
            "titulo": f"Indicadores na meta · mês a mês {ano}", "largo": True,
            "rotulos": [MESES[m] for m in range(1, ate + 1)],
            "series": [
                {"nome": "na meta", "cor": VERDE, "valores": [
                    sum(1 for _i, c in calc if c["meses"][k][4] is not None
                        and c["meses"][k][4] >= 100) for k in range(ate)]},
                {"nome": "com meta", "cor": CINZA, "valores": [
                    sum(1 for _i, c in calc if c["meses"][k][4] is not None)
                    for k in range(ate)]}],
            "formato": "num"})

    # ---- uma aba por area: mes a mes, semana a semana e dia a dia
    cols_a = [col("VISÃO", "texto", oculta=True),
              col("INDICADOR", "texto", 190), col("PERÍODO", "texto", 120),
              col("META", "valor", 110), col("REAL", "valor", 110),
              col("% ATING.", "pct", 80), col("NEC./DIA", "valor", 100)]
    for area in (PRE, VEN, POS, TRADE, ANA):
        ls, ts = [], []
        for ind, c in calc:
            if ind["area"] != area:
                continue
            f = ind["fmt"]
            for rot, m, m_, r_, a_ in c["meses"]:
                nec = c["nec"] if mes and m == mes else None
                ls.append([VISOES[0], ind["nome"], f"{rot}/{str(ano)[2:]}",
                           _fmt_ind(m_, f), _fmt_ind(r_, f), a_,
                           _fmt_ind(nec, f) if nec is not None else ""])
                ts.append(_tom_ating(a_))
            for rot, m_, r_, a_ in c["semanas"]:
                ls.append([VISOES[1], ind["nome"], rot, _fmt_ind(m_, f),
                           _fmt_ind(r_, f), a_, ""])
                ts.append(_tom_ating(a_))
            for rot, m_, r_, a_ in c["dias"]:
                ls.append([VISOES[2], ind["nome"], rot, _fmt_ind(m_, f),
                           _fmt_ind(r_, f), a_, ""])
                ts.append(_tom_ating(a_))
        if not ls:
            continue
        quem = PESSOAS[area].split()[0]
        r["tabelas"].append(tabela(
            f"{area.split(' ')[0]} · {quem}", cols_a, ls, ts,
            filtros=({"coluna": "VISÃO", "padrao": VISOES[0]}, "INDICADOR")))
    erros = sorted({f"{ind['nome']} ({ind['area']})" for ind, c in calc
                    if c["erro"]})
    if erros:
        r["avisos"].append("⚠ Sem dado: " + ", ".join(erros))
    return r


# =========================================================================
# FAROL DE VISITA (o GridRca da Maxima, dia a dia)
# =========================================================================
def _meta_de_visita(ctx, ano, mes):
    """A meta de visita do Farol de Metas do mes: ({cod ou N:nome: meta},
    dias uteis do mes, dias uteis que faltam). Sem meta: ({}, None, None)."""
    if not mes:
        return {}, None, None
    try:
        dm = meta_do_periodo(ctx)
        ac = dm.get("acomp") or {}
        if dm.get("competencia") != f"{ano}-{mes:02d}":
            return {}, None, None
    except Exception:                                   # noqa: BLE001
        return {}, None, None
    import visitas_nucleo as vn                         # noqa: PLC0415
    metas = {}
    for l in (ac.get("recortes") or {}).get("vendedor") or []:
        mv = l.get("meta_visita")
        if mv is None:
            continue
        metas[_cod6(l.get("chave"))] = mv
        metas["N:" + vn.chave_de_nome(l.get("nome") or l.get("rotulo"))] = mv
    return metas, ac.get("dias_uteis_do_mes"), ac.get("dias_restantes")


def _metas_de_visita_por_dia(ctx, ano, mes):
    """(21/10) A META DE VISITA DE CADA DIA UTIL do Planner do mes (12;
    interior 6, 12 na cidade base; desde a ADMISSAO): ({cod6: {data: n}},
    {cod6: data de admissao}). Sem Planner do mes: ({}, {})."""
    metas_dia, adm_de = {}, {}
    if not mes:
        return metas_dia, adm_de
    try:
        import pastas_bap as pb                         # noqa: PLC0415
        import planner_nucleo as nu                     # noqa: PLC0415
        cfg_m = nu.carregar_config(pb.config_do_planner(
            ctx.raiz, f"{ano}-{mes:02d}"))
        if cfg_m.get("mes") != f"{ano}-{mes:02d}":
            return {}, {}
        cid_ = {nu.chave_normal(f"{c.get('cod')}-{c.get('loja')}"):
                c.get("cidade") for c in ctx.base.get("clientes") or []}
        for cod_, dias_ in nu.metas_de_visita_do_mes(cfg_m, cid_).items():
            metas_dia[_cod6(cod_)] = dias_
        for p_ in nu.vendedores(cfg_m):
            a_ = nu.data_admissao(p_)
            if a_ and p_.get("cod_protheus"):
                adm_de[_cod6(p_["cod_protheus"])] = a_
    except Exception:                                   # noqa: BLE001
        return {}, {}
    return metas_dia, adm_de


def _meta_visita_no_dia(metas_dia, cod6, m_mes, d, du=None, util=True):
    """A meta de visita do vendedor no dia d: a do Planner (12/6) reescalada
    para fechar com a meta do mes do Farol de Metas (m_mes)."""
    dd = metas_dia.get(cod6)
    if dd:
        tot = sum(dd.values())
        return (dd.get(d, 0) * (m_mes / tot) if m_mes is not None and tot
                else float(dd.get(d, 0)))
    if m_mes is None or not du:
        return None
    return m_mes / du if util else 0


COMPARATIVOS = ("ATÉ A DATA", "MÊS INTEIRO")


def farol_visitas(ctx):
    """
    Visitas, agenda, tempo medio de atendimento (TMA) e de deslocamento
    (TMD), inicio e fim dos trabalhos - por supervisor, por vendedor e dia a
    dia. Fonte: RELATORIOS/Visitas/diario/AAAAMMDD.csv, baixado pelo botao
    "Atualizar visitas" (visitas_maxima.py).
    Medias: por DIA EM CAMPO (dia com visita); TMA e TMD ponderados pelas
    visitas do dia; inicio/fim = primeiro e ultimo cliente atendido.
    O Resumo gerencial e um painel: a meta de visita vem do Farol de Metas
    do mes (a mesma da RV), com projecao pelo ritmo dos dias uteis.
    """
    import visitas_nucleo as vn                         # noqa: PLC0415
    hoje = ctx.hoje
    ano, mes = periodo(ctx)
    if mes:
        de, ate = date(ano, mes, 1), vn.fim_do_mes(ano, mes)
        ant_a, ant_m = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
        de_ant, ate_ant = date(ant_a, ant_m, 1), vn.fim_do_mes(ant_a, ant_m)
    else:
        de, ate = date(ano, 1, 1), date(ano, 12, 31)
        de_ant, ate_ant = date(ano - 1, 1, 1), date(ano - 1, 12, 31)
    todos = com_cadastro_como_visita(ctx, vn.registros(ctx.raiz))
    anos = sorted({l["data"].year for l in todos} | {hoje.year})
    baixado = max((vn.baixado_em(ctx.raiz, f"{l['data']:%Y%m%d}",
                                 vn.arquivo_do_dia(ctx.raiz, l["data"]))
                   for l in todos), default=None,
                  key=lambda x: x or datetime.min)
    r = novo("vc_visitas", VEN, "Farol de Visita",
             "Máxima · Painel Auditoria" + (
                 f" · baixado em {baixado:%d/%m %H:%M}" if baixado else ""),
             "RELATORIOS › Visitas › diario (GridRca da Máxima, dia a dia)")
    r["abrir"] = str(vn.SUB_VISITAS / vn.ARQ_ACOMP)
    r["painel_titulo"] = "Resumo gerencial"
    capa(r, ctx, anos)
    # ---- SO VENDEDOR ATIVO: ativo no Planner do mes e, no mes escolhido,
    # com meta de visita no Farol de Metas (quem saiu nao aparece)
    metas, du, resta = _meta_de_visita(ctx, ano, mes)

    def meta_da(l):
        m = metas.get(_cod6(l["cod_protheus"])) if l["cod_protheus"] else None
        return m if m is not None else metas.get(
            "N:" + vn.chave_de_nome(l["vendedor"]))
    todos = [l for l in todos if l.get("ativo") and (
        not metas or not (de <= l["data"] <= ate) or meta_da(l) is not None)]
    # (21/10, Alexandre) A META DE CADA DIA UTIL (12; interior 6, 12 na
    # cidade base) desde a ADMISSAO - a mesma regra do Gerador de Meta,
    # reescalada para fechar com a meta do mes do Farol de Metas
    metas_dia, adm_de = _metas_de_visita_por_dia(ctx, ano, mes)
    # ---- os filtros de cima (seguem em todas as abas e no painel)
    esc = {n: ctx.param(n) for n in ("SUPERVISOR", "VENDEDOR")}
    no_ano = [l for l in todos if l["data"].year in (ano, ano - 1)]
    for nome, campo in (("SUPERVISOR", "supervisor"), ("VENDEDOR", "vendedor")):
        outro = "VENDEDOR" if nome == "SUPERVISOR" else "SUPERVISOR"
        c_out = "vendedor" if nome == "SUPERVISOR" else "supervisor"
        vals = sorted({l[campo] for l in no_ano
                       if not esc[outro] or l[c_out] == esc[outro]})
        if esc[nome] and esc[nome] not in vals:
            vals.append(esc[nome])
        r["parametros"].append({"nome": nome, "valores": [TODOS_RECORTE] + vals,
                                "valor": esc[nome] or TODOS_RECORTE})

    def no_filtro(l):
        return all(not esc[n] or l[c] == esc[n] for n, c in
                   (("SUPERVISOR", "supervisor"), ("VENDEDOR", "vendedor")))
    todos = [l for l in todos if no_filtro(l)]
    regs = [l for l in todos if de <= l["data"] <= ate]
    regs_ant = [l for l in todos if de_ant <= l["data"] <= ate_ant]
    ad = _aplicar_aderencia_planner(ctx, regs, de, min(ate, hoje))
    # (18/10) ATE A DATA x MES: o realizado vai ate o ultimo dia baixado; o
    # que falta do mes vem da rota do Planner (para o cartao dizer os dois)
    data_ate = max((l["data"] for l in regs if l["data"] <= hoje),
                   default=None)
    # (18/10, Alexandre) A CHAVE DO COMPARATIVO: o mes atual vai ate a data;
    # os meses de antes podem entrar ATE O MESMO DIA (acumulado x acumulado,
    # o padrao) ou com o MES INTEIRO
    comp = ctx.param("COMPARATIVO") or COMPARATIVOS[0]
    if comp not in COMPARATIVOS:
        comp = COMPARATIVOS[0]
    if mes:
        r["parametros"].append({"nome": "COMPARATIVO",
                                "valores": list(COMPARATIVOS),
                                "valor": comp})
    ate_dia = data_ate.day if (mes and comp == COMPARATIVOS[0]
                               and data_ate is not None
                               and data_ate < ate) else None
    if ate_dia:
        regs_ant = [l for l in regs_ant if l["data"].day <= ate_dia]
    prog_resto = defaultdict(int)
    if data_ate is not None and data_ate < ate and \
            hasattr(vn, "programados_por_dia"):
        try:
            for (v_, d_), n_ in vn.programados_por_dia(
                    ctx.raiz, data_ate + timedelta(days=1), ate).items():
                prog_resto[v_] += n_
        except Exception:                               # noqa: BLE001
            prog_resto = defaultdict(int)
    graficos_tempo(r, ctx, "Visitas", [(l["data"], l["visitas"])
                                       for l in todos], "num", VERDE)
    if not todos:
        r["avisos"].append("Nenhum dia baixado ainda: clique em "
                           "“Atualizar visitas”.")
    falta = vn.dias_faltando(ctx.raiz, de,
                             min(ate, hoje - timedelta(days=1)))
    if falta and todos:
        txt = ", ".join(f"{d:%d/%m}" for d in falta[:8])
        r["avisos"].append(f"Sem o arquivo de {len(falta)} dia(s) útil(eis): "
                           f"{txt}{'…' if len(falta) > 8 else ''}")

    if any(not l["fechado"] for l in regs):
        r["avisos"].append("O dia de hoje é parcial: muda até o vendedor "
                           "sincronizar.")
    hm = vn.hhmm
    # ---- os dias uteis (os do Farol de Metas, quando ha meta)
    if mes and du is None:
        du = ctx.uteis(de - timedelta(days=1), ate)
        resta = 0 if ate < hoje else (ctx.uteis(hoje - timedelta(days=1), ate)
                                      if hoje >= de else du)
    esperado = (du - resta) / du * 100.0 if du and resta is not None else None

    def meta_de(raws):
        vistos, tot, achou = set(), 0.0, False
        for l in raws:
            if l["cod"] in vistos:
                continue
            vistos.add(l["cod"])
            m = meta_da(l)
            if m is not None:
                tot, achou = tot + m, True
        return tot if achou else None

    def util(d):
        return d.weekday() < 5 and d not in ctx.fer

    # (09/11, Alexandre, recado 20261109-1200: "a media deve ser em cima dos
    # dias uteis; nao pode contar domingo nem feriado") VISITAS POR DIA =
    # visitas dos VENDEDORES / DIAS UTEIS DE VENDEDOR: todo dia util conta,
    # com ou sem visita, desde a 1a visita do vendedor na Maxima; sabado,
    # domingo, feriado e o dia de hoje (aberto) ficam fora dos dias. Antes
    # dividia so pelos dias com visita (MA 03-06/11: 103 / 12 = 8,6; agora
    # 103 / 16 = 6,4, com o Jocimar sem visita).
    prim_vis = {}
    for l_ in todos:
        if l_["cargo"] == "VENDEDOR" and (l_["visitas"] or 0) > 0 and (
                l_["cod"] not in prim_vis or l_["data"] < prim_vis[l_["cod"]]):
            prim_vis[l_["cod"]] = l_["data"]

    def vis_por_du(raws):
        """(visitas por dia util de vendedor, visitas, dias uteis)."""
        corte_ = hoje - timedelta(days=1)
        vis_, du_ = 0, 0
        for l_ in raws:
            p_ = prim_vis.get(l_["cod"])
            if l_["cargo"] != "VENDEDOR" or l_["data"] > corte_ \
                    or p_ is None or l_["data"] < p_:
                continue
            vis_ += l_["visitas"] or 0
            du_ += 1 if util(l_["data"]) else 0
        return (vis_ / du_ if du_ else None), vis_, du_

    # ---- (21/10) META x RITMO x JORNADA na linha do vendedor
    dias_uteis_mes = [de + timedelta(days=i) for i in range((ate - de).days
                                                            + 1)
                      if util(de + timedelta(days=i))] if mes else []

    def _vends(raws):
        """{cod6: o 1o registro} dos VENDEDORES das linhas."""
        out = {}
        for l in raws:
            if l["cargo"] == "VENDEDOR" and l.get("cod_protheus"):
                out.setdefault(_cod6(l["cod_protheus"]), l)
        return out

    def _meta_dia_de(cod6, l, d):
        """A meta do dia d do vendedor (reescalada para a meta do mes)."""
        return _meta_visita_no_dia(metas_dia, cod6, meta_da(l), d, du,
                                   util(d))

    def _du_desde(cod6, ate_):
        a_ = max(adm_de.get(cod6) or de, de)
        return [d for d in dias_uteis_mes if a_ <= d <= ate_]

    def ritmo(raws):
        """META MES, META ATE A DATA, VISITAS (vendedores), % META, DU DESDE
        A ADMISSAO, DU SEM VISITA, VIS./DU, META/DU, INICIO APOS 9H e
        JORNADA < 4H."""
        if not mes or data_ate is None:
            return [None] * 10
        vs = _vends(raws)
        mm = ma = None
        du_adm = du_mes = sem = 0
        vis_v = sum(l["visitas"] for l in raws if l["cargo"] == "VENDEDOR")
        campo = {(_cod6(l["cod_protheus"]), l["data"]) for l in raws
                 if l["cargo"] == "VENDEDOR" and l.get("cod_protheus")
                 and vn.em_campo(l)}
        corte_sv = min(data_ate, hoje - timedelta(days=1))
        for c6, l in vs.items():
            m_ = meta_da(l)
            if m_ is not None:
                mm = (mm or 0) + m_
                ate_d = [_meta_dia_de(c6, l, d) or 0
                         for d in _du_desde(c6, data_ate)]
                ma = (ma or 0) + sum(ate_d)
            du_adm += len(_du_desde(c6, data_ate))
            du_mes += len(_du_desde(c6, ate))
            sem += sum(1 for d in _du_desde(c6, corte_sv)
                       if (c6, d) not in campo)
        dj = [l for l in raws if vn.em_campo(l) and l["data"].weekday() < 5]
        ini9 = sum(1 for l in dj if l["primeiro"] and l["primeiro"] > 9 * 3600)
        j4 = sum(1 for l in dj if l["primeiro"] and l["ultimo"]
                 and l["ultimo"] - l["primeiro"] < 4 * 3600)
        return [mm, ma, vis_v, pct_de(vis_v, ma) if ma else None,
                du_adm or None, sem if vs else None,
                vis_v / du_adm if du_adm else None,
                mm / du_mes if (mm and du_mes) else None,
                f"{ini9} de {len(dj)}" if dj else None,
                f"{j4} de {len(dj)}" if dj else None]

    def sem_visita(raws):
        """(vendedor, dia util ja passado) sem nenhuma visita."""
        return sum(1 for l in raws if l["cargo"] == "VENDEDOR"
                   and not vn.em_campo(l) and l["data"] < hoje
                   and util(l["data"]))

    def var_txt(a, b, casas=1):
        if a is None or b is None or not b:
            return "—"
        v = (a / b - 1) * 100.0
        return ("+" if v >= 0 else "") + br(v, 0) + "%"

    rot_ant = "Mês anterior" if mes else "Ano anterior"
    if ate_dia:
        rot_ant = f"Mês anterior até {ate_dia:02d}/{ant_m:02d}"

    def resto_de(raws):
        """O que o Planner ainda tem programado depois de data_ate para
        os vendedores destas linhas."""
        vs = {re.sub(r"\D", "", texto(l.get("cod_protheus"))).zfill(6)
              for l in raws if l.get("cod_protheus")
              and l.get("cargo") == "VENDEDOR"}
        return sum(prog_resto.get(v_, 0) for v_ in vs)

    def cartoes(raws):
        s = vn.resumir(raws)
        cods = {l["cod"] for l in raws}
        a = vn.resumir([l for l in regs_ant if l["cod"] in cods])
        mt = meta_de(raws)
        # (21/10, Alexandre) COM FILTRO DE DIA (ou de alguns dias), a meta
        # do cartao e a META DOS DIAS FILTRADOS (a META DIA da tabela), sem
        # projecao nem nec./dia; sem filtro, o mes com a META ATE A DATA
        # igual a da tabela (a soma das metas dos dias, desde a admissao)
        dias_r = {l["data"] for l in raws if de <= l["data"] <= ate}
        dias_m = {l["data"] for l in regs if l["cod"] in cods}
        vs_ = {c6: l for c6, l in _vends(raws).items()
               if meta_da(l) is not None}
        if mt and mes and dias_r and dias_r < dias_m:
            md = sum(_meta_dia_de(c6, l, d) or 0 for c6, l in vs_.items()
                     for d in dias_r if d >= (adm_de.get(c6) or de))
            vis_v = sum(l["visitas"] for l in raws
                        if l["cargo"] == "VENDEDOR")
            at_ = pct_de(vis_v, md) if md else None
            um = len(dias_r) == 1
            rot_d = (f"do dia {min(dias_r):%d/%m}" if um else
                     f"dos {len(dias_r)} dias filtrados")
            c_vis = kpi("Visitas", br(vis_v),
                        {"ok": "ok", "atencao": "atencao",
                         "alerta": "alerta"}.get(_tom_ating(at_), "neutro"),
                        f"meta {rot_d} {br(md)}", linhas=[
                            ("Ating. da meta " + ("do dia" if um else
                                                  "dos dias"), p(at_),
                             _tom_ating(at_)),
                            ("Faltam para a meta", br(max(0.0, md - vis_v)),
                             ""),
                            ("Meta do mês (vendedores)", br(mt), "")])
        elif mt:
            ma_ = None
            if mes and data_ate is not None and vs_:
                ma_ = sum(_meta_dia_de(c6, l, d) or 0 for c6, l in vs_.items()
                          for d in _du_desde(c6, data_ate))
            # (05/11, Alexandre: "tirar a venda de hoje da conta do DU") a
            # PROJECAO = visitas ATE ONTEM / DU ate ontem x DU do mes - o
            # mesmo do Painel do Diretor. Antes hoje ficava fora dos DU,
            # mas as visitas de hoje entravam (202 / 2 x 19 = 1.919).
            hj_ = [l for l in raws if l["data"] >= hoje]
            vis_p = s["visitas"] - (vn.resumir(hj_)["visitas"] or 0
                                    if hj_ else 0)
            c_vis = _cartao_indicador("Visitas", mt, s["visitas"], resta,
                                      esperado, ate=data_ate, meta_ate=ma_,
                                      real_proj=vis_p)
        else:
            c_vis = kpi("Visitas", br(s["visitas"]), "info",
                        f"{br(s['dias_corridos'])} "
                        f"{'dia' if s['dias_corridos'] == 1 else 'dias'} "
                        f"em campo",
                        linhas=[(rot_ant, br(a["visitas"]), "")])
        vend = {l["cod"] for l in raws if l["cargo"] == "VENDEDOR"}
        em = {l["cod"] for l in raws if l["cargo"] == "VENDEDOR"
              and vn.em_campo(l)}
        dias_d = {l["data"] for l in raws if util(l["data"])
                  and l["data"] < hoje}
        dias_cv = sum(1 for l in raws if l["cargo"] == "VENDEDOR"
                      and vn.em_campo(l) and l["data"] in dias_d)
        sv = sem_visita(raws)
        vdu_, vis_du_, du_du_ = vis_por_du(raws)            # (09/11)
        vdu_a = vis_por_du([l for l in regs_ant if l["cod"] in cods])[0]
        pa = s["pct_agenda"]
        # a jornada sem o sabado (06/10): so segunda a sexta
        ini9 = sum(1 for l in raws if vn.em_campo(l) and l["primeiro"]
                   and l["data"].weekday() < 5
                   and l["primeiro"] > 9 * 3600)
        fim16 = sum(1 for l in raws if vn.em_campo(l) and l["ultimo"]
                    and l["data"].weekday() < 5
                    and l["ultimo"] < 16 * 3600)
        return [
            c_vis,
            kpi("Vendedores em campo", f"{br(len(em))} de {br(len(vend))}",
                "ok" if vend and len(em) == len(vend) else "atencao",
                "com visita no período", linhas=[
                    ("Média por dia útil",
                     br(dias_cv / len(dias_d), 1) if dias_d else "—", ""),
                    ("Vendedor-dia sem visita", br(sv),
                     "alerta" if sv else "ok")]),
            kpi("Visitas por dia", br(vdu_, 1)
                if vdu_ is not None else "—", "neutro",
                f"por vendedor, por dia útil · {br(vis_du_)} ÷ {br(du_du_)}"
                " dias úteis", linhas=[
                    (rot_ant, br(vdu_a, 1)
                     if vdu_a is not None else "—", ""),
                    ("Variação", var_txt(vdu_, vdu_a),
                     "" if vdu_ is None or vdu_a is None
                     else "ok" if vdu_ >= vdu_a else "alerta")]),
            kpi("Aderência ao Planner"
                + (f" até {data_ate:%d/%m}" if data_ate else ""), p(pa),
                "neutro" if pa is None else "ok" if pa >= 80
                else "atencao" if pa >= 50 else "alerta",
                f"{br(s['na_agenda'])} visitados de {br(s['agendados'])} "
                f"programados"
                + (f" de {de:%d/%m} a {data_ate:%d/%m}" if data_ate else ""),
                linhas=[("Programados no mês (até "
                         f"{ate:%d/%m})", br(s["agendados"] + resto_de(raws)),
                         ""),
                        ("Ainda a visitar no mês", br(resto_de(raws)), ""),
                        ("Fora da rota", f"{br(s['fora'])} ("
                         f"{p(pct_de(s['fora'], s['visitas']))} das "
                         f"visitas)", ""),
                        ("Programados não visitados",
                         br(sum(l.get("nao_visit") or 0 for l in raws)),
                         "alerta" if any(l.get("nao_visit") for l in raws)
                         else "ok"),
                        (rot_ant + " (agenda Máx.)", p(a["pct_agenda"]),
                         "")]),
            kpi("Atendimento (TMA)", vn.hms(s["tma"]), "neutro",
                "média por visita", linhas=[
                    ("Deslocamento (TMD)", vn.hms(s["tmd"]), ""),
                    ("TMA " + rot_ant.lower(), vn.hms(a["tma"]), "")]),
            kpi("Início dos trabalhos", hm(s["inicio"]), "neutro",
                "1ª atividade do dia (média)", linhas=[
                    ("Depois das 9h",
                     f"{br(ini9)} de {br(s['dias_jornada'])} jornadas",
                     "alerta" if s["dias_jornada"]
                     and ini9 / s["dias_jornada"] > .5
                     else "atencao" if ini9 else "ok"),
                    (rot_ant, hm(a["inicio"]), "")]),
            kpi("Fim dos trabalhos", hm(s["fim"]), "neutro",
                "última atividade do dia (média)", linhas=[
                    ("Jornada média", hm(s["jornada"]), ""),
                    ("Antes das 16h",
                     f"{br(fim16)} de {br(s['dias_jornada'])} jornadas",
                     "alerta" if s["dias_jornada"]
                     and fim16 / s["dias_jornada"] > .5
                     else "atencao" if fim16 else "ok")]),
            _cartao_jornada(resumo_jornada(raws, jt), jt),
            _cartao_almoco(resumo_almoco(raws, alm_f, jt), jt),
            kpi("Km rodado por dia", br(s["km_rod_dia"])
                if s["km_rod_dia"] is not None else "—", "neutro",
                f"{br(s['km_rodado'])} km no período", linhas=[
                    ("KM por cliente (km ÷ visitas)",
                     br(km_por_cliente(s["km_rodado"], s["visitas"]), 1)
                     if km_por_cliente(s["km_rodado"], s["visitas"])
                     is not None else "—", ""),
                    ("Venda na Máxima", moeda(s["venda"]), ""),
                    ("Dias sem GPS", br(s["sem_gps"]),
                     "alerta" if s["sem_gps"] else "ok")]),
        ]
    grupos = {}

    def raws_de(linhas, i_chave):
        out = []
        for l in linhas:
            out.extend(grupos.get(l[i_chave], []))
        return out

    # PEDIDOS (06/10): os pedidos que o vendedor FEZ no dia (TABELA_BAP,
    # data do pedido, VND e VEA - sem excluido e devolucao), pelo codigo
    # Protheus do registro de visita
    ped_dia = defaultdict(set)
    try:
        for it in ctx.tabela["itens"]:
            if it["tipo"] in ("VND", "VEA") and it.get("dt_pedido") \
                    and it.get("pedido"):
                ped_dia[(_cod6(it.get("vend")), it["dt_pedido"])].add(
                    (it["filial"], texto(it["pedido"]),
                     _cod6(it.get("cliente"))))
    except Exception:                                   # noqa: BLE001
        ped_dia = defaultdict(set)
    # (18/10, Alexandre) PEDIDO NA ROTA x FORA DA ROTA: o pedido (Farol de
    # Pedidos = TABELA_BAP, nao o relatorio de pedidos da Maxima) foi
    # lancado NO DIA DA VISITA ao cliente (check-in no Excel analitico da
    # Maxima)? Sim = na rota; nao = fora da rota.
    vis_dia = defaultdict(set)
    for c_ in (ad or {}).get("clientes") or []:
        if c_.get("situacao") != getattr(vn, "SIT_NAO", "-"):
            vis_dia[(_cod6(c_.get("cod_protheus")), c_["data"])].add(
                _cod6(c_.get("cod_cliente")))

    def ped_rota(raws):
        """(na rota, fora da rota) - pedidos do vendedor nesses dias."""
        na = fo = 0
        for l in raws:
            if not l.get("cod_protheus"):
                continue
            k_ = (_cod6(l["cod_protheus"]), l["data"])
            for _f, _p, cli in ped_dia.get(k_, ()):
                if cli in vis_dia.get(k_, ()):
                    na += 1
                else:
                    fo += 1
        return na, fo

    def pct_ped(raws):
        na, fo = ped_rota(raws)
        return pct_de(na, na + fo), pct_de(fo, na + fo)

    # (19/10, Alexandre - pedido via Analista) POSITIVACAO, % VENDA NA ROTA,
    # % VENDA FORA DA ROTA e % VENDA POR VISITA (os indicadores do slide de
    # visita da reuniao com o Diretor):
    #   POSIT. REAL  = clientes com liquido > 0 (VND - DEV pela data da NF,
    #                  a regra do meta_nucleo) no codigo do vendedor, do dia 1
    #                  ate a data (hoje ou o fim do mes escolhido)
    #   POSIT. META  = a meta de positivacao do mes (Farol de Metas)
    #   % VENDA NA ROTA = liquido dos positivados que estavam PROGRAMADOS na
    #                  rota do vendedor no Planner (do dia 1 ate a data) /
    #                  liquido de todos os positivados; FORA = o resto
    #   % VENDA POR VISITA = positivados / visitas (Espelho + cadastros)
    # Supervisor e TOTAL = soma dos vendedores (o cliente comprado de dois
    # vendedores conta nos dois).
    corte = min(ate, hoje)
    liq_v = defaultdict(float)
    try:
        for it in ctx.tabela["itens"]:
            if it["tipo"] in ("VND", "DEV") and it.get("dt_nf") \
                    and de <= it["dt_nf"] <= corte:
                v_ = _liquido(it)
                if v_ is not None:
                    liq_v[(_cod6(it.get("vend")),
                           _cod6(it.get("cliente")))] += v_
    except Exception:                                   # noqa: BLE001
        liq_v = defaultdict(float)          # sem a TABELA_BAP: sem venda
    posit_v = defaultdict(dict)                 # vend -> {cliente: liquido}
    for (vd_, cl_), v_ in liq_v.items():
        if v_ > 0.005:
            posit_v[vd_][cl_] = v_
    prog_v = defaultdict(set)                   # vend -> clientes programados
    for c_ in (ad or {}).get("clientes") or []:
        if c_.get("situacao") in (getattr(vn, "SIT_NA_ROTA", ""),
                                  getattr(vn, "SIT_NAO", "")) \
                and de <= c_["data"] <= corte:
            prog_v[_cod6(c_.get("cod_protheus"))].add(
                _cod6(c_.get("cod_cliente")))
    meta_pos = {}
    try:
        dm_ = meta_do_periodo(ctx)
        if mes and dm_.get("competencia") == f"{ano}-{mes:02d}":
            for l_ in ((dm_.get("acomp") or {}).get("recortes") or {}).get(
                    "vendedor") or []:
                if l_.get("meta_positivacao") is not None:
                    meta_pos[_cod6(l_.get("chave"))] = \
                        l_.get("meta_positivacao")
    except Exception:                                   # noqa: BLE001
        meta_pos = {}

    def cods_de(raws):
        """Os vendedores do grupo (sem o supervisor, que nao tem carteira);
        linha so de supervisor: o codigo dele."""
        v_ = {_cod6(l["cod_protheus"]) for l in raws
              if l.get("cod_protheus") and l.get("cargo") == "VENDEDOR"}
        return v_ or {_cod6(l["cod_protheus"]) for l in raws
                      if l.get("cod_protheus")}

    # (22/10, Alexandre) AS MESMAS COLUNAS DA PARCIAL VISITAS (META, VISIT.,
    # % META, % CONV., % FORA DE ROTA, CAD., INICIO, ULT. ATIV., TMA, TMD)
    # + o CADASTRO COM COMPRA (a regra do Farol de Metas: cadastrado no
    # periodo e positivado no mes)
    vis_cli, compras_cli = _visitados_e_compras(ctx, regs, de, ate)
    jt = _jornada_do_mes(ctx, ano, mes)
    alm_f = almocos_do_periodo(ctx, de, ate)
    cad_vd = defaultdict(list)              # (vend, dia) -> clientes novos
    try:
        for cod_, c_ in (ctx.tabela.get("clientes") or {}).items():
            dc_ = _dia(c_.get("dtcad"))
            if dc_ and de <= dc_ <= corte and texto(c_.get("vend")):
                cad_vd[(_cod6(c_["vend"]), dc_)].append(_cod6(cod_))
    except Exception:                                   # noqa: BLE001
        cad_vd = defaultdict(list)

    def cad_de(raws, so_dias=None):
        cods = cods_de(raws)
        novos = [cl_ for (v_, d_), cls_ in cad_vd.items() if v_ in cods
                 and (so_dias is None or d_ in so_dias) for cl_ in cls_]
        return len(novos), sum(1 for cl_ in novos
                               if positivou(ctx, cl_, d_ate_pos))
    d_ate_pos = corte

    def colunas_parcial(s, raws, meta, p_meta, so_dias=None):
        vends = {_curto_pessoa(l["vendedor"]) for l in raws}
        n_, c_ = _conversao_de(vis_cli, compras_cli, vends, so_dias)
        cad, cad_c = cad_de(raws, so_dias)
        # (22/10) PROSP. = visitas de prospeccao (Forms) que contaram
        prosp = sum(l.get("prosp_visita") or 0 for l in raws
                    if so_dias is None or l["data"] in so_dias)
        rj_ = resumo_jornada(raws, jt)
        ra_ = resumo_almoco(raws, alm_f, jt)
        return [meta, s["visitas"], p_meta,
                pct_de(c_, n_) if n_ else None,
                pct_de(s["fora"], s["visitas"]) if s["visitas"] else None,
                cad, cad_c, prosp, hm(s["inicio"]), hm(s["fim"]),
                # (22/10, Alexandre) a JORNADA LIQUIDA e os dias abaixo dela;
                # TMA e TMD em HH:MM; KM e KM/CLIENTE
                hm(rj_["media"]), rj_["abaixo"],
                hm(ra_["media"]), ra_["acima"],
                hm(s["tma"]), hm(s["tmd"]), s["km_rodado"],
                km_por_cliente(s["km_rodado"], s["visitas"])]

    def metricas(s, raws):
        # META = a meta ATE A DATA (a soma das metas dos dias, desde a
        # admissao) - a mesma do acumulado da Parcial
        (mm, ma, vis_v, pm, du_adm, sem, vdu, mdu, i9, j4) = ritmo(raws)
        return colunas_parcial(s, raws, ma, pm)
    cols_m = [col("META", "num", 64), col("VISIT.", "int", 60),
              dict(col("% META", "pct", 66), chip=FAIXA_PCT_META,
                   larg_fixa=66),
              col("% CONV.", "pct", 64), col("% FORA DE ROTA", "pct", 96),
              col("CAD.", "int", 50), col("CAD. C/ COMPRA", "int", 96),
              col("PROSP.", "int", 56),
              col("INÍCIO", "hora", 56), col("ÚLT. ATIV.", "hora", 70),
              col("JORNADA LÍQ.", "hora", 84),
              col("DIAS < JORN. LÍQ.", "int", 104),
              col("INTERV. ALMOÇO", "hora", 96),
              col("DIAS ALMOÇO > MÁX.", "int", 116),
              col("TMA", "hora", 56), col("TMD", "hora", 56),
              col("KM", "num", 56), col("KM/CLIENTE", "num1", 80)]

    def tom(s, cargo="VENDEDOR"):
        # (22/10) a aderencia saiu da tela: so o vendedor sem dia em campo
        if cargo != "VENDEDOR":
            return ""
        return "alerta" if not s["dias"] else ""

    def total(linhas, i_chave, n_antes):
        if not linhas:
            return None
        raws = raws_de(linhas, i_chave)
        s = vn.resumir(raws)
        return ["TOTAL"] + [""] * (n_antes - 1) + metricas(s, raws) + [""]
    # ---- por supervisor
    por_sup = defaultdict(list)
    for l in regs:
        por_sup[l["supervisor"]].append(l)
    ls = []
    for sup, g in por_sup.items():
        s = vn.resumir(g)
        k = f"S|{sup}"
        grupos[k] = g
        ls.append([sup, len({x["cod"] for x in g})] + metricas(s, g) + [k])
    # (22/10) a ordem: o % da meta de cima para baixo (como a Parcial)
    ls.sort(key=lambda x: -(x[2 + 2] if x[2 + 2] is not None else -1))
    cols_s = [col("SUPERVISOR", "texto", 260), col("REPRES.", "int", 60)] \
        + cols_m + [col("CHAVE", "texto", oculta=True)]
    i_ks = len(cols_s) - 1
    tons_s = []
    for l in ls:
        vend = [x for x in grupos[l[i_ks]] if x["cargo"] == "VENDEDOR"]
        tons_s.append(tom(vn.resumir(vend)) if vend else "")
    t_sup = tabela("Por supervisor", cols_s, ls, tons_s,
                   filtros=("SUPERVISOR",),
                   total=total(ls, i_ks, 2),
                   kpis_de=lambda lin: cartoes(raws_de(lin, i_ks)))
    t_sup["total_de"] = lambda lin: total(lin, i_ks, 2)
    # ---- por vendedor
    por_v = defaultdict(list)
    for l in regs:
        por_v[l["cod"]].append(l)
    lv, tv = [], []
    for cod, g in por_v.items():
        s = vn.resumir(g)
        u = g[-1]
        k = f"V|{cod}"
        grupos[k] = g
        lv.append([u["supervisor"], u["vendedor"], u["cargo"],
                   u["filial_nome"], cod] + metricas(s, g) + [k])
    lv.sort(key=lambda x: (x[0], -(x[5 + 2] if x[5 + 2] is not None
                                   else -1)))
    cols_v = [col("SUPERVISOR", "texto", 210), col("VENDEDOR", "texto", 250),
              # (22/10, Alexandre) CARGO fora da tela (fica oculta: o
              # recorte e o tom do vendedor ainda leem a posicao)
              col("CARGO", "texto", 90, oculta=True),
              col("FILIAL", "texto", oculta=True),
              col("CÓD.", "texto", 60, oculta=True)] + cols_m \
        + [col("CHAVE", "texto", oculta=True)]
    i_kv = len(cols_v) - 1
    for l in lv:
        tv.append(tom(vn.resumir(grupos[l[i_kv]]), l[2]))
    t_v = tabela("Por vendedor", cols_v, lv, tv,
                 filtros=("SUPERVISOR", "VENDEDOR", "FILIAL"),
                 total=total(lv, i_kv, 5),
                 kpis_de=lambda lin: cartoes(raws_de(lin, i_kv)))
    t_v["total_de"] = lambda lin: total(lin, i_kv, 5)
    # ---- dia a dia
    ld, td = [], []
    for l in sorted(regs, key=lambda x: (-x["data"].toordinal(),
                                         x["supervisor"], x["vendedor"])):
        campo = vn.em_campo(l)
        jor = (l["ultimo"] - l["primeiro"]) if (
            l["primeiro"] and l["ultimo"] and l["ultimo"] >= l["primeiro"]) \
            else None
        sit = ("SÓ PROSPECÇÃO" if l.get("so_prospeccao") else
               "EM CAMPO" if campo else "SEM VISITA") + (
            "" if l["fechado"] else " (PARCIAL)")
        rota_ = ("SÁB. DEPÓSITO" if l.get("deposito") else
                 "PLANNER" if l.get("fonte_rota") == "PLANNER" else
                 "PLANNER AJUST." if l.get("fonte_rota")
                 == "PLANNER AJUSTADO" else "AGENDA MÁX.")
        k = f"D|{l['data']:%Y%m%d}|{l['cod']}"
        grupos[k] = [l]
        # ATINGIMENTO DO DIA (06/10): quanto teria de visitar no dia = a
        # meta de visita do mes (Farol de Metas, a da RV) / dias uteis;
        # sabado, domingo e feriado nao tem meta (fica em branco); a soma
        # das metas dos dias uteis = a meta do mes (a do cartao Visitas)
        m_mes = meta_da(l) if l["cargo"] == "VENDEDOR" and du else None
        m_dia = m_mes / du if m_mes is not None and util(l["data"]) \
            else None
        # (21/10) 12 por dia util (interior 6 / base 12) desde a admissao
        if m_dia is not None and l.get("cod_protheus"):
            m_dia = _meta_dia_de(_cod6(l["cod_protheus"]), l, l["data"]) \
                or None
        # (22/10) as colunas da Parcial Visitas, na linha do dia
        ld.append([l["data"], vn.DIAS_SEMANA[l["data"].weekday()],
                   l["supervisor"], l["vendedor"], l["cargo"], sit]
                  + colunas_parcial(vn.resumir([l]), [l], m_dia,
                                    pct_de(l["visitas"], m_dia)
                                    if m_dia else None, {l["data"]})
                  + [k])
        td.append("alerta" if (not campo and l["cargo"] == "VENDEDOR"
                               and l["data"].weekday() < 5) else
                  "atencao" if (campo and not l["gps"]) else "")
    cols_d = [col("DATA", "data", 80), col("DIA", "texto", 40),
              col("SUPERVISOR", "texto", 190), col("VENDEDOR", "texto", 230),
              col("CARGO", "texto", 85, oculta=True),
              col("SITUAÇÃO", "texto", 100),
              ]
    cols_d = cols_d[:6] + cols_m + [col("CHAVE", "texto", oculta=True)]

    i_kd = len(cols_d) - 1
    nd_ = [c_["nome"] for c_ in cols_d]

    def total_d(linhas):
        """(22/10) o TOTAL do dia a dia: a meta somada e as colunas da
        Parcial das linhas na tela."""
        if not linhas:
            return None
        raws = raws_de(linhas, i_kd)
        s_ = vn.resumir(raws)
        md_ = sum((l[nd_.index("META")] or 0) for l in linhas) or None
        vis_v = sum(l["visitas"] for l in raws if l["cargo"] == "VENDEDOR")
        cols_ = colunas_parcial(s_, raws, md_,
                                pct_de(vis_v, md_) if md_ else None,
                                {l["data"] for l in raws})
        return ["TOTAL"] + [""] * 5 + cols_ + [""]
    t_d = tabela("Dia a dia", cols_d, ld, td, total=total_d(ld),
                 filtros=("DATA", "SUPERVISOR", "VENDEDOR", "SITUAÇÃO"),
                 kpis_de=lambda lin: cartoes(raws_de(lin, i_kd)),
                 recortes=[("Só vendedores", lambda l: l[4] == "VENDEDOR"),
                           ("Sem visita em dia útil",
                            lambda l: l[5].startswith("SEM")
                            and l[1] not in ("SÁB", "DOM")),
                           ("Abaixo de 80% da meta",
                            lambda l: l[nd_.index("% META")] is not None
                            and l[nd_.index("% META")] < 80)])
    t_d["total_de"] = total_d             # o total do que esta na tela
    for t_ in (t_sup, t_v, t_d):
        t_["compacta"] = True                 # letra 9: os nomes cabem
    # PDF ENXUTO (06/10, o mesmo do Farol de Giro): titulos curtos numa
    # linha, agrupados; o que e igual em todas as linhas (data, dia,
    # cargo, supervisor do filtro) sobe para a linha do titulo
    curto_v = {"1º CLIENTE": "INÍCIO", "ÚLTIMO": "FIM", "INÍCIO": "INÍCIO",
               "AGENDADOS": "AGEND.", "VISITADOS": "VISIT.",
               "% ADERÊNCIA": "% ADER.",
               "% PED. NA ROTA": "% NA ROTA",
               "% PED. FORA DE ROTA": "% FORA", "META DIA": "META",
               "% ATING.": "%", "VIS./VEND./DIA": "VIS./DIA",
               "META ATÉ A DATA": "ATÉ A DATA", "META MÊS": "MÊS",
               "DU DESDE A ADMISSÃO": "DU", "DU SEM VISITA": "DU S/ VIS.",
               "INÍCIO APÓS 9H": "APÓS 9H", "JORNADA < 4H": "< 4H",
               "PEDIDOS": "PEDIDOS",
               "DIAS CAMPO": "DIAS", "VENDA": "VENDA R$", "REPRES.": "REPR."}
    grupos_v = [("META DE VISITA", ["META", "VISIT.", "% META"]),
                ("RESULTADO", ["% CONV.", "% FORA DE ROTA", "CAD.",
                               "CAD. C/ COMPRA", "PROSP."]),
                ("JORNADA", ["INÍCIO", "ÚLT. ATIV.", "JORNADA LÍQ.",
                             "DIAS < JORN. LÍQ.", "INTERV. ALMOÇO",
                             "DIAS ALMOÇO > MÁX.", "TMA", "TMD"]),
                ("DESLOCAMENTO", ["KM", "KM/CLIENTE"])]
    for t_, dest in ((t_sup, "VISIT."), (t_v, "VISIT."), (t_d, "VISIT.")):
        nomes_ = {c_["nome"] for c_ in t_["colunas"]}
        t_["colunas"] = [dict(c_, pdf_nome=curto_v.get(c_["nome"],
                                                        c_["nome"]))
                         for c_ in t_["colunas"]]
        t_["pdf"] = {
            "compacto": True, "sem_rs": True, "verticais": True,
            "zebra": True, "traco_zero": True, "data_curta": True,
            "sem_quebra": True, "corpo": 6.8, "cab": 5.8, "pad": 3,
            "colapsa": ("DATA", "DIA", "CARGO", "SUPERVISOR"),
            "inteiras": ("SITUAÇÃO",), "destaque": (dest,),
            "contagem": "linhas",
            "grupos": [(g_, [n_ for n_ in ns_ if n_ in nomes_])
                       for g_, ns_ in grupos_v]}
    r["tabelas"] += [t_sup, t_v, t_d]
    r["tabelas"] += _tabelas_aderencia(ctx, regs, ad, hoje)
    # (22/10, Alexandre) a PROSPECCAO do Forms com o STATUS de cada resposta
    # (o supervisor cobra o que nao contou)
    try:
        t_pr = _tabela_prospeccao(ctx, todos, de, ate, no_filtro)
        r["tabelas"].append(t_pr)
        if t_pr.pop("_fotos", False):
            r["avisos"].append(
                "Prospecção do app BAP Ajuda: a foto da fachada (coluna FOTO)"
                " fica em RELATORIOS\\BAP_AJUDA_RESPOSTAS\\fotos.")
        n_t = t_pr.pop("_testes", 0)
        if n_t:
            r["avisos"].append(
                f"Prospecção: {br(n_t)} resposta(s) da conta de teste "
                f"(000040) fora da visita e da aba.")
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Prospecção (Forms): {erro}")
    # (27/10, Alexandre - recado do BAP Ajuda 20261027-0740) a INDICACAO do
    # app BAP Ajuda ("Indicou, ganhou"): nao e visita nem prospeccao
    try:
        r["tabelas"].append(_tabela_indicacao(ctx, todos, de, ate,
                                              no_filtro))
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Indicação (BAP Ajuda): {erro}")
    if ad and ad.get("rotas"):
        sem = sorted(d for d, a_ in ad["rotas"].items()
                     if not a_ and d.weekday() < 5)
        usadas = sorted({x_ for a_ in ad["rotas"].values() for x_ in a_})
        if sem:
            r["avisos"].append(
                "Aderência: " + ", ".join(f"{d:%d/%m}" for d in sem[:8])
                + (" …" if len(sem) > 8 else "")
                + " sem rota do Planner enviada antes do dia — "
                  "contou a agenda da Máxima.")
        if usadas:
            r["avisos"].append(
                "Aderência = programados do Planner do dia (o envio da rota "
                "que valeu para cada vendedor: ROTA_PROTHEUS " + ", ".join(
                    re.sub(r"\d{4}-\d{2}_", "", u.replace("ROTA_PROTHEUS_", "")
                       .replace("TODOS_", "").replace(".json", ""))
                    for u in usadas) + ").")
    r["kpis"] = cartoes(regs)
    r["painel"] = _painel_visitas(ctx, regs, todos, ano, mes, de, ate, du,
                                  resta, esperado, meta_da, meta_de,
                                  sem_visita, util, ate_dia=ate_dia,
                                  vis_por_du=vis_por_du)
    return r


def _tabela_prospeccao(ctx, todos, de, ate, no_filtro=None):
    """(22/10, Alexandre) Aba PROSPECCAO do Farol de Visita: as respostas
    do Microsoft Forms (visita a cliente fora da base) do periodo, com o
    STATUS - so CONTA entra na visita (PROSP.); o resto o supervisor
    cobra. Vendedor e supervisor pelo codigo (o mesmo das linhas).
    (27/10, recado do BAP Ajuda 20261027-0740) + a prospeccao do app BAP
    Ajuda 2.0 (FONTE = APP), com a FOTO da fachada; os TESTES (000040) nao
    aparecem."""
    import prospeccao_forms as pf                       # noqa: PLC0415
    import visitas_nucleo as vn                         # noqa: PLC0415
    quem = {}
    for l in todos:
        if l.get("cod_protheus"):
            quem[_cod6(l["cod_protheus"])] = l
    linhas, tons = [], []
    testes = 0
    for x in pf.linhas(ctx.raiz):
        d = x.get("dia") or _dia(x.get("conclusao"))
        if not d or not (de <= d <= ate):
            continue
        if x.get("status") == pf.ST_TESTE:
            testes += 1
            continue
        l = quem.get(_cod6(x.get("cod6"))) if x.get("cod6") else None
        if no_filtro is not None and l is not None and not no_filtro(l):
            continue
        vend = l["vendedor"] if l else (texto(x.get("vendedor_bap"))
                                         or texto(x.get("vendedor"))
                                         or texto(x.get("email")))
        sup = l["supervisor"] if l else "(SEM SUPERVISOR)"
        st = texto(x.get("status"))
        obs_ = "; ".join(o_ for o_ in (texto(x.get("obs_bap")),
                                       texto(x.get("obs"))) if o_)
        # (09/11, recado 20261109-1300) DATA e HORA lado a lado (o
        # REGISTRADO EM sai); a data segue o dia do envio
        h_ = hora_da_prospeccao(x)
        linhas.append([d, vn.hhmm(h_) if h_ is not None else "",
                       vn_dia_semana(d), sup,
                       vend, st, texto(x.get("fonte")) or pf.FONTE_FORMS,
                       texto(x.get("estab")), texto(x.get("cnpj")),
                       texto(x.get("segmento")), texto(x.get("cidade")),
                       texto(x.get("uf")), texto(x.get("resultado")),
                       texto(x.get("linhas")), texto(x.get("contato")),
                       texto(x.get("telefone")), obs_,
                       texto(x.get("foto"))])
        tons.append("" if st == pf.ST_CONTA else "alerta")
    ordem = sorted(range(len(linhas)), key=lambda i: (
        -linhas[i][0].toordinal(), linhas[i][3], linhas[i][4],
        linhas[i][1]))
    linhas, tons = [linhas[i] for i in ordem], [tons[i] for i in ordem]
    cols = [col("DATA", "data", 80), col("HORA", "hora", 50),
            col("DIA", "texto", 40),
            col("SUPERVISOR", "texto", 190), col("VENDEDOR", "texto", 220),
            col("STATUS", "texto", 130), col("FONTE", "texto", 56),
            col("ESTABELECIMENTO", "texto", 220),
            col("CNPJ", "texto", 120), col("SEGMENTO", "texto", 140),
            col("CIDADE", "texto", 130), col("UF", "texto", 40),
            col("RESULTADO", "texto", 160),
            col("LINHAS DE INTERESSE", "texto", 180),
            col("CONTATO", "texto", 140), col("TELEFONE", "texto", 110),
            col("OBSERVAÇÃO", "texto", 260), col("FOTO", "texto", 200)]

    def cartoes(ls):
        st = Counter(l[5] for l in ls)
        conta = st.get(pf.ST_CONTA, 0)
        fora = len(ls) - conta
        app = sum(1 for l in ls if l[6] == pf.FONTE_APP)
        return [
            kpi("Prospecções registradas", br(len(ls)), "neutro",
                f"app {br(app)} · Forms {br(len(ls) - app)} · "
                f"{br(len({(l[4], l[0]) for l in ls}))} vendedor-dia"),
            kpi("Contam como visita", br(conta), "ok",
                p(pct_de(conta, len(ls))) if ls else ""),
            kpi("Não contam", br(fora), "alerta" if fora else "ok",
                " · ".join(f"{k.lower()} {br(v)}" for k, v in
                           st.most_common() if k != pf.ST_CONTA)
                or "nenhuma")]
    t = tabela("Prospecção", cols, linhas, tons,
               filtros=("STATUS", "FONTE", "SUPERVISOR", "VENDEDOR", "DATA",
                        "UF", "RESULTADO"),
               kpis_de=cartoes,
               recortes=[("Só as que contam",
                          lambda l: l[5] == pf.ST_CONTA),
                         ("Só as que não contam",
                          lambda l: l[5] != pf.ST_CONTA),
                         ("Só do app BAP Ajuda",
                          lambda l: l[6] == pf.FONTE_APP)])
    t["compacta"] = True
    t["pdf"] = {"compacto": True, "zebra": True, "data_curta": True,
                "corpo": 6.5, "cab": 5.6, "pad": 2.5,
                "quebra": ("OBSERVAÇÃO", "ESTABELECIMENTO"),
                "contagem": "linhas"}
    if not linhas:
        t["vazio"] = ("Nenhuma prospecção no período (app BAP Ajuda ou "
                      "Forms). O app entra com a sincronização do BAP Ajuda; "
                      "o Forms, com o Atualizar visitas.")
    t["_testes"] = testes
    t["_fotos"] = any(l[17] for l in linhas)
    return t


def _tabela_indicacao(ctx, todos, de, ate, no_filtro=None):
    """(27/10, Alexandre - recado do BAP Ajuda 20261027-0740) Aba INDICACAO
    do Farol de Visita: as indicacoes do app BAP Ajuda 2.0 ("Indicou,
    ganhou"), uma linha por indicacao. NAO conta como visita nem como
    prospeccao (Alexandre, 24/10). SITUACAO: VISITADA (prospeccao do
    vendedor com o mesmo CNPJ, ou o mesmo nome na mesma cidade, depois da
    indicacao), JA E CLIENTE (CNPJ na BASE_CLIENTE) ou A VISITAR. Os testes
    (000040) nao aparecem."""
    import prospeccao_forms as pf                       # noqa: PLC0415
    import respostas_bap_ajuda as rb                    # noqa: PLC0415
    quem = {}
    for l in todos:
        if l.get("cod_protheus"):
            quem[_cod6(l["cod_protheus"])] = l
    base, _cad = pf.base_e_cadastros(ctx.raiz)
    prosp = [x for x in pf.linhas(ctx.raiz) if x.get("status") != pf.ST_TESTE]
    S_VIS, S_CLI, S_ABRIR = "VISITADA", "JÁ É CLIENTE", "A VISITAR"

    def visitada(x):
        for y in prosp:
            dy = y.get("dia")
            if not dy or (x["dia"] and dy < x["dia"]):
                continue
            if x["cnpj"] and pf.so_digitos(y.get("cnpj")) == x["cnpj"]:
                return dy
            if (rb._sa(y.get("estab")) == rb._sa(x["estab"])
                    and rb._sa(y.get("cidade")) == rb._sa(x["cidade"])):
                return dy
        return None
    linhas, tons = [], []
    for x in rb.indicacoes(ctx.raiz):
        d = x["dia"]
        if not d or not (de <= d <= ate):
            continue
        l = quem.get(x["cod6"]) if x["cod6"] else None
        if no_filtro is not None and l is not None and not no_filtro(l):
            continue
        vend = l["vendedor"] if l else x["vendedor"]
        sup = l["supervisor"] if l else (x["supervisor"]
                                         or "(SEM SUPERVISOR)")
        dv = visitada(x)
        sit = S_CLI if x["cnpj"] in base else (S_VIS if dv else S_ABRIR)
        linhas.append([d, vn_dia_semana(d), sup, vend, sit,
                       x["cod_indicou"], x["quem_indicou"], x["estab"],
                       x["contato"], x["telefone"], x["cidade"], x["bairro"],
                       x["segmento"], x["cnpj"], dv, x["obs"],
                       x["enviado"].strftime("%d/%m/%Y %H:%M")
                       if x["enviado"] else ""])
        tons.append("ok" if sit == S_VIS else "")
    ordem = sorted(range(len(linhas)), key=lambda i: (
        -linhas[i][0].toordinal(), linhas[i][2], linhas[i][3]))
    linhas, tons = [linhas[i] for i in ordem], [tons[i] for i in ordem]
    cols = [col("DATA", "data", 80), col("DIA", "texto", 40),
            col("SUPERVISOR", "texto", 190), col("VENDEDOR", "texto", 220),
            col("SITUAÇÃO", "texto", 100),
            col("CÓD. QUEM INDICOU", "texto", 80),
            col("CLIENTE QUE INDICOU", "texto", 220),
            col("INDICADO", "texto", 200), col("CONTATO", "texto", 130),
            col("TELEFONE", "texto", 110), col("CIDADE", "texto", 120),
            col("BAIRRO", "texto", 120), col("SEGMENTO", "texto", 130),
            col("CNPJ", "texto", 120), col("VISITADA EM", "data", 80),
            col("OBSERVAÇÃO", "texto", 220),
            col("REGISTRADO EM", "texto", 120)]

    def cartoes(ls):
        vis = sum(1 for l in ls if l[4] == S_VIS)
        cli = sum(1 for l in ls if l[4] == S_CLI)
        abrir = len(ls) - vis - cli
        quem_ = Counter((l[5], l[6]) for l in ls)
        top = quem_.most_common(1)
        return [
            kpi("Indicações", br(len(ls)), "neutro",
                f"{br(len({l[3] for l in ls}))} vendedor(es)"),
            kpi("Clientes que indicaram", br(len(quem_)), "neutro",
                (f"mais: {top[0][0][1][:28]} ({br(top[0][1])})"
                 if top else "")),
            kpi("Visitadas", br(vis), "ok" if vis else "neutro",
                p(pct_de(vis, len(ls))) + " das indicações"
                if ls else ""),
            kpi("A visitar", br(abrir), "alerta" if abrir else "ok",
                f"já é cliente {br(cli)}" if cli else "nenhuma já cliente")]
    t = tabela("Indicação", cols, linhas, tons,
               filtros=("SITUAÇÃO", "SUPERVISOR", "VENDEDOR",
                        "CLIENTE QUE INDICOU", "CIDADE", "DATA"),
               kpis_de=cartoes,
               recortes=[("A visitar", lambda l: l[4] == S_ABRIR),
                         ("Visitadas", lambda l: l[4] == S_VIS)])
    t["compacta"] = True
    t["pdf"] = {"compacto": True, "zebra": True, "data_curta": True,
                "corpo": 6.5, "cab": 5.6, "pad": 2.5,
                "quebra": ("OBSERVAÇÃO", "INDICADO", "CLIENTE QUE INDICOU"),
                "contagem": "linhas"}
    if not linhas:
        t["vazio"] = ("Nenhuma indicação no período. As indicações do app "
                      "BAP Ajuda (\"Indicou, ganhou\") entram com a "
                      "sincronização do BAP Ajuda.")
    return t


def vn_dia_semana(d) -> str:
    import visitas_nucleo as vn                         # noqa: PLC0415
    return vn.DIAS_SEMANA[d.weekday()]


def _aplicar_aderencia_planner(ctx, regs, de, ate):
    """(18/10, Alexandre) A ADERENCIA E CONTRA O PLANNER: em cada linha
    (representante x dia) que tem o Espelho analitico, AGENDADOS passa a
    ser os PROGRAMADOS do Planner para o dia, NA AGENDA os programados que
    foram visitados e FORA tudo o que foi visitado fora da rota (o
    cadastro novo do dia entra aqui). A agenda da Maxima fica em
    ag_maxima. Linha sem Espelho: continua a agenda da Maxima."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    ad = None
    if regs and hasattr(vn, "aderencia_planner"):
        try:
            ad = vn.aderencia_planner(ctx.raiz, de, ate)
        except Exception:                               # noqa: BLE001
            ad = None
    dias = (ad or {}).get("dias") or {}
    for l in regs:
        l.setdefault("ag_maxima", l["agendados"])
        x = dias.get((l["cod"], l["data"]))
        if x is None:
            l["fonte_rota"] = "AGENDA MÁXIMA"
            l["nao_visit"] = max(0, l["agendados"] - l["vis_agenda"])
            continue
        na = min(x["na_rota"], l["visitas"])
        l.update(agendados=x["programados"], vis_agenda=na,
                 vis_fora=max(0, l["visitas"] - na),
                 nao_visit=x["nao_visitados"], fonte_rota=x["fonte"],
                 rota_arq=x["rota"], deposito=x["deposito"])
    return ad


# RN-VIS: a faixa de cor da ADERENCIA ao Planner (a mesma do tom da linha no
# PC): >= 80 verde, de 50 a 79,99 amarelo, abaixo de 50 vermelho.
ADERENCIA_VERDE = 80
ADERENCIA_AMARELO = 50


_TOM_COR = {"alerta": _VERM, "atencao": _AMAR, "ok": _VERD}


def tom_aderencia(pct):
    """Tom ("ok" / "atencao" / "alerta") da % de aderencia; "" sem dado.
    Unica fonte do corte: o chip (faixa_aderencia) sai daqui."""
    if pct is None:
        return ""
    return ("ok" if pct >= ADERENCIA_VERDE
            else "atencao" if pct >= ADERENCIA_AMARELO else "alerta")


def faixa_aderencia():
    """O chip em faixa (ate, fundo, texto) com o mesmo corte do tom: o maior
    float abaixo do corte vira o teto de cada faixa (valor <= ate)."""
    import math                                         # noqa: PLC0415
    return [(math.nextafter(ADERENCIA_AMARELO, 0), *_TOM_COR["alerta"]),
            (math.nextafter(ADERENCIA_VERDE, 0), *_TOM_COR["atencao"]),
            (None, *_TOM_COR["ok"])]


def _tabelas_aderencia(ctx, regs, ad, hoje):
    """(18/10) As duas visoes do Farol de Visita:
    ADERENCIA DIA A DIA: uma coluna por dia (% dos agendados do Planner que
    foram visitados) e a % ADERENCIA ACUMULADA - so isso (Alexandre).
    CLIENTE A CLIENTE: o qualitativo da visita - situacao, quem e o cliente
    (segmento, curva, status, dias sem compra, atraso), a jornada (ordem,
    inicio, fim, atendimento) e se teve PEDIDO NO DIA pelo Farol de
    Pedidos (TABELA_BAP), nao pelo relatorio da Maxima. Filtro: so o
    RECORTE."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    saida = []
    vend = [l for l in regs if l["cargo"] == "VENDEDOR"]
    dias = sorted({l["data"] for l in vend if l["agendados"]
                   and l["data"] <= hoje})
    if dias:
        por_v = defaultdict(dict)
        info = {}
        for l in vend:
            por_v[l["cod"]][l["data"]] = l
            info[l["cod"]] = (l["supervisor"], l["vendedor"])
        nomes = [f"{d:%d/%m} {vn.DIAS_SEMANA[d.weekday()]}" for d in dias]
        ate_ = dias[-1]
        n_acum = f"% ADERÊNCIA ACUM. ATÉ {ate_:%d/%m}"
        cols = [col("SUPERVISOR", "texto", 190),
                col("VENDEDOR", "texto", 230)] + [
            dict(col(n_, "pct", 62), chip=faixa_aderencia())
            for n_ in nomes] + [dict(col(n_acum, "pct", 150),
                                     chip=faixa_aderencia())]
        ls, ts = [], []
        for cod, por_d in por_v.items():
            g = list(por_d.values())
            pr = sum(l["agendados"] for l in g)
            na = sum(l["vis_agenda"] for l in g)
            cel = []
            for d in dias:
                l = por_d.get(d)
                cel.append(pct_de(l["vis_agenda"], l["agendados"])
                           if l and l["agendados"] else None)
            tot = pct_de(na, pr)
            ls.append(list(info[cod]) + cel + [tot])
            ts.append(tom_aderencia(tot))
        ordem = sorted(range(len(ls)), key=lambda i: (ls[i][0], ls[i][1]))
        ls, ts = [ls[i] for i in ordem], [ts[i] for i in ordem]

        def total_m(linhas):
            if not linhas:
                return None
            cods = {(x[0], x[1]) for x in linhas}
            g = [l for l in vend if info.get(l["cod"]) in cods]
            cel = []
            for d in dias:
                gd = [l for l in g if l["data"] == d]
                cel.append(pct_de(sum(l["vis_agenda"] for l in gd),
                                  sum(l["agendados"] for l in gd)))
            return ["TOTAL", ""] + cel + [pct_de(
                sum(l["vis_agenda"] for l in g),
                sum(l["agendados"] for l in g))]
        t_m = tabela("Aderência dia a dia", cols, ls, ts,
                     filtros=("SUPERVISOR", "VENDEDOR"), total=total_m(ls))
        t_m["total_de"] = total_m
        t_m["compacta"] = True
        t_m["pdf"] = {"compacto": True, "zebra": True, "traco_zero": True,
                      "sem_quebra": True, "corpo": 6.5, "cab": 5.5,
                      "pad": 2, "colapsa": ("SUPERVISOR",),
                      "destaque": (n_acum,), "contagem": "linhas"}
        saida.append(t_m)
    # ---- cliente a cliente
    if ad and ad.get("clientes"):
        chaves = {(l["cod"], l["data"]): l for l in regs}
        base = {}
        for c in ctx.base.get("clientes") or []:
            base[(c.get("cod"), _loja2(c.get("loja")))] = c
        # o PEDIDO DO DIA pelo Farol de Pedidos: vendedor, dia e cliente
        ped = defaultdict(float)
        try:
            for it in ctx.tabela["itens"]:
                if it["tipo"] in ("VND", "VEA") and it.get("dt_pedido") \
                        and it.get("pedido"):
                    ped[(_cod6(it.get("vend")), it["dt_pedido"],
                         _cod6(it.get("cliente")))] += float(
                             it.get("valor") or 0.0)
        except Exception:                               # noqa: BLE001
            ped = defaultdict(float)
        ls, ts = [], []
        for c in ad["clientes"]:
            l = chaves.get((c["cod_max"], c["data"]))
            if l is None:
                continue
            b = base.get((c["cod_cliente"], _loja2(c["loja"]))) or {}
            nome = c["cliente"] or b.get("nome") or ""
            visitado = c["situacao"] != vn.SIT_NAO
            k_p = (_cod6(c.get("cod_protheus") or l.get("cod_protheus")),
                   c["data"], _cod6(c["cod_cliente"]))
            tem_ped = k_p in ped
            sit = ("VISITADO NA ROTA" if c["situacao"] == vn.SIT_NA_ROTA else
                   "VISITADO FORA DE ROTA" if c["situacao"] == vn.SIT_FORA
                   else "AGENDADO E NÃO VISITADO")
            ls.append([
                c["data"], vn.DIAS_SEMANA[c["data"].weekday()],
                l["supervisor"], l["vendedor"], sit,
                f"{c['cod_cliente']}-{c['loja']}", nome,
                texto(b.get("fantasia")) or "—",
                b.get("segmento") or "", b.get("bairro") or "",
                b.get("cidade") or "", b.get("curva") or "",
                b.get("status") or "", b.get("dias_sem_compra"),
                b.get("atraso") or None,
                c["ord_prev"], c["ord_rea"], vn.hhmm(c["inicio"]),
                vn.hhmm(c["fim"]),
                vn.hms(c["atend"]) if c["atend"] else "—",
                "SIM" if tem_ped else "NÃO",
                ped.get(k_p) if tem_ped else None,
                c["justificativa"] if visitado else "", c["atend"] or 0])
            ts.append("ok" if visitado and tem_ped else
                      "alerta" if not visitado else
                      "" if c["situacao"] == vn.SIT_NA_ROTA else "atencao")
        ordem = sorted(range(len(ls)), key=lambda i: (
            -ls[i][0].toordinal(), ls[i][2], ls[i][3], ls[i][4],
            ls[i][15].zfill(4) if ls[i][15] else "9999"))
        ls = [ls[i] for i in ordem]
        ts = [ts[i] for i in ordem]
        cols = [col("DATA", "data", 80), col("DIA", "texto", 40),
                col("SUPERVISOR", "texto", 170),
                col("VENDEDOR", "texto", 200),
                col("SITUAÇÃO", "texto", 170), col("CÓD.", "texto", 72),
                col("CLIENTE", "texto", 230),
                # (09/11, Alexandre) o NOME FANTASIA (BASE_CLIENTE) e o
                # filtro por DATA, como no Dia a dia
                col("NOME FANTASIA", "texto", 180),
                col("SEGMENTO", "texto", 130),
                col("BAIRRO", "texto", 120), col("CIDADE", "texto", 110),
                col("CURVA", "texto", 46), col("STATUS", "texto", 100),
                col("DIAS S/ COMPRA", "int", 80),
                col("ATRASO", "moeda", 80),
                col("SEQ. PREV.", "texto", 60), col("SEQ. REAL", "texto", 60),
                col("INÍCIO", "hora", 52), col("FIM", "hora", 52),
                col("ATEND.", "hora", 64), col("PEDIDO NO DIA", "texto", 80),
                col("VALOR PEDIDO", "moeda", 90),
                col("JUSTIFICATIVA", "texto", 200),
                col("ATEND. SEG.", "int", oculta=True)]
        i_s, i_p, i_c = 4, 20, 11
        t_c = tabela(
            "Cliente a cliente", cols, ls, ts, filtros=("DATA",),
            recortes=[
                ("Visitados na rota", lambda x: x[i_s] == "VISITADO NA ROTA"),
                ("Visitados fora de rota",
                 lambda x: x[i_s] == "VISITADO FORA DE ROTA"),
                ("Agendados e não visitados",
                 lambda x: x[i_s] == "AGENDADO E NÃO VISITADO"),
                ("Positivados na rota",
                 lambda x: x[i_s] == "VISITADO NA ROTA" and x[i_p] == "SIM"),
                ("Positivados fora de rota",
                 lambda x: x[i_s] == "VISITADO FORA DE ROTA"
                 and x[i_p] == "SIM"),
                ("Visitados sem pedido",
                 lambda x: x[i_s] != "AGENDADO E NÃO VISITADO"
                 and x[i_p] == "NÃO"),
                ("Curva S/A/B agendados e não visitados",
                 lambda x: x[i_s] == "AGENDADO E NÃO VISITADO"
                 and x[i_c] in ("S", "A", "B")),
                ("Visita rápida (menos de 5 min)",
                 lambda x: 0 < (x[-1] or 0) < 300)])
        t_c["compacta"] = True
        t_c["pdf"] = {"compacto": True, "zebra": True, "data_curta": True,
                      "sem_quebra": True, "corpo": 6.5, "cab": 5.5, "pad": 2,
                      "colapsa": ("DATA", "DIA", "SUPERVISOR", "VENDEDOR"),
                      "contagem": "linhas"}
        saida.append(t_c)
    return saida


def _painel_visitas(ctx, regs, todos, ano, mes, de, ate, du, resta,
                    esperado, meta_da, meta_de, sem_visita, util,
                    ate_dia=None, vis_por_du=None):
    """O Resumo gerencial do Farol de Visita: em cada linha, o DIA A DIA do
    mes escolhido a esquerda e o MES A MES (12 meses) a direita -
    visitas, inicio do 1o cliente, % da agenda cumprida, ultimo cliente,
    TMD, TMA e km rodado. Em TODOS OS MESES a esquerda e semana a semana."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    # a esquerda: os dias do mes (ou as semanas do ano)
    if mes:
        ndias = calendar_ndias(ano, mes)
        chaves_e = list(range(1, ndias + 1))
        rot_e = [str(d) for d in chaves_e]
        grupo_e = defaultdict(list)
        for l in regs:
            grupo_e[l["data"].day].append(l)
        uteis_e = [util(date(ano, mes, d)) for d in chaves_e]
        tit_e = f"dia a dia · {MESES[mes]}/{str(ano)[2:]}"
    else:
        grupo_e = defaultdict(list)
        for l in regs:
            grupo_e[l["data"].isocalendar()[1]].append(l)
        chaves_e = sorted(grupo_e) or [1]
        rot_e = [f"S{k:02d}" for k in chaves_e]
        uteis_e = None
        tit_e = f"semana a semana · {ano}"
    # a direita: os 12 meses ate o escolhido
    if mes:
        fim = date(ano, mes, 1)
    else:                       # TODOS OS MESES: ate o ultimo mes com dados
        fim = max((date(l["data"].year, l["data"].month, 1) for l in todos
                   if l["data"].year == ano), default=date(ano, 12, 1))
    meses = []
    a_, m_ = fim.year, fim.month
    for _ in range(12):
        meses.insert(0, (a_, m_))
        a_, m_ = (a_ - 1, 12) if m_ == 1 else (a_, m_ - 1)
    # MES A MES = a MESMA turma do mes escolhido (06/10): o cartao "Mes
    # anterior" conta so quem esta no Farol agora - o grafico tambem, para
    # os dois numeros casarem (SET 6,3/dia no grafico x 6,0 no cartao)
    turma = {l["cod"] for l in regs} if mes and regs else None
    grupo_d = defaultdict(list)
    for l in todos:
        if turma is None or l["cod"] in turma:
            k_ = (l["data"].year, l["data"].month)
            # (18/10) comparativo ATE A DATA: os outros meses so ate o
            # mesmo dia do mes atual
            if ate_dia and k_ != (ano, mes) and l["data"].day > ate_dia:
                continue
            grupo_d[k_].append(l)
    rot_d = [MESES[m] for _a, m in meses]
    res_e = {k: vn.resumir(grupo_e[k]) for k in chaves_e if grupo_e[k]}
    res_d = {k: vn.resumir(grupo_d[k]) for k in meses if grupo_d[k]}
    for k_, s_ in res_d.items():        # (09/11) x/dia = por dia util
        s_["vis_du"] = vis_por_du(grupo_d[k_])[0] if vis_por_du else None

    def par_(nome, campo, formato, cor=VERDE, sub=None, extra_e=None):
        ve = [(res_e[k][campo] or 0) if k in res_e else 0 for k in chaves_e]
        vd = [(res_d[k][campo] or 0) if k in res_d else 0 for k in meses]
        ge = {"titulo": f"{nome} {tit_e}", "rotulos": rot_e,
              "series": [{"nome": nome, "cor": cor, "valores": ve,
                          **({"cores": [cor if u else CINZA for u in uteis_e]}
                             if uteis_e else {})}],
              "formato": formato, "rotular": "nao_zero"}
        ge.update(extra_e or {})
        gd = {"titulo": f"{nome} mês a mês · últimos 12 meses",
              "rotulos": rot_d,
              "series": [{"nome": nome, "cor": cor, "valores": vd}],
              "formato": formato, "rotular": "nao_zero"}
        if sub:
            gd["subrotulos"] = [sub(res_d[k]) if k in res_d else ""
                                for k in meses]
        return ge, gd
    meta_dia = {}
    mt = meta_de(regs) if mes else None
    if mt and du:
        meta_dia = {"meta": mt / du, "rotulo_meta": "meta/dia útil"}
    pares = [
        par_("Visitas", "visitas", "num", extra_e=meta_dia,
             sub=lambda s: f"{br(s['vis_du'], 1)}/dia útil"
             if s.get("vis_du") else ""),
        par_("Início do 1º cliente", "inicio", "hora", AZUL),
        par_("% Aderência ao Planner", "pct_agenda", "pct", VERDE,
             sub=lambda s: f"{br(s['na_agenda'])}/{br(s['agendados'])}"
             if s["agendados"] else ""),
        par_("Último cliente", "fim", "hora", AZUL),
        par_("Jornada (1º ao último cliente)", "jornada", "hora", AZUL),
        par_("TMD (deslocamento)", "tmd", "min", AMARELO),
        par_("TMA (atendimento)", "tma", "min", AMARELO),
        par_("Km rodado", "km_rodado", "num", "#4F6D7A",
             sub=lambda s: f"{br(s['km_rod_dia'])} km/dia"
             if s["km_rod_dia"] else ""),
    ]
    # (18/10, Alexandre) O MES ATUAL E ATE A DATA: o rotulo diz ate quando,
    # e o mes anterior mostra tambem o MESMO PERIODO (do dia 1 ao mesmo
    # dia), para comparar acumulado com acumulado
    data_ate = max((l["data"] for l in regs), default=None)
    if ate_dia and data_ate is not None:
        # comparativo ATE A DATA: todos os meses do dia 1 ao mesmo dia
        for _ge, gd_ in pares:
            gd_["titulo"] = gd_["titulo"].replace(
                "mês a mês · últimos 12 meses",
                f"mês a mês · do dia 1 ao dia {ate_dia} de cada mês")
    elif mes and data_ate is not None and data_ate < vn.fim_do_mes(ano,
                                                                    mes):
        gd_v = pares[0][1]
        subs = list(gd_v.get("subrotulos") or [""] * len(meses))
        i_at = meses.index((ano, mes)) if (ano, mes) in meses else None
        if i_at is not None:
            subs[i_at] = (subs[i_at] + " · " if subs[i_at] else "") + \
                f"até {data_ate:%d/%m}"
            if i_at > 0:
                a_a, m_a = meses[i_at - 1]
                ult = min(data_ate.day, vn.fim_do_mes(a_a, m_a).day)
                mesmo = sum(l["visitas"] for l in grupo_d.get((a_a, m_a), [])
                            if l["data"].day <= ult)
                subs[i_at - 1] = (subs[i_at - 1] + " · " if subs[i_at - 1]
                                  else "") + f"até {ult:02d}/{m_a:02d}: " \
                    f"{br(mesmo)}"
        gd_v["subrotulos"] = subs
        gd_v["titulo"] += f" · {MESES[mes]} até {data_ate:%d/%m}"
    blocos = []
    for i, (ge, gd) in enumerate(pares):
        blocos.append({"col": 0, "row": i, "tipo": "barras", "grafico": ge})
        blocos.append({"col": 1, "row": i, "tipo": "barras", "grafico": gd})
    return {"colunas": (1, 1), "altura_min": len(pares) * 260,
            "blocos": blocos}


def _cor_tom(t):
    return {"ok": VERDE, "atencao": AMARELO, "alerta": VERMELHO}.get(t, CINZA)


def _nome_curto_visita(nome):
    """PAULO UBIRATAN CURVO DE LIMA -> PAULO UBIRATAN (2 primeiros nomes)."""
    p_ = [x for x in str(nome).split() if x not in ("DA", "DE", "DO", "DAS",
                                                     "DOS", "E")]
    return " ".join(p_[:2]) if p_ else str(nome)


def calendar_ndias(ano, mes):
    import calendar                                     # noqa: PLC0415
    return calendar.monthrange(ano, mes)[1]


# =========================================================================
# o cardapio
# =========================================================================
# (id, area, titulo, funcao, icone/rotulo curto)
# =========================================================================
# PARCIAIS (06/10): Parcial Pedidos (Farol de Pedidos) e Parcial Visitas e
# Positivacao (Farol de Visita). ACUMULADO (mes ate hoje), D-1 (o dia util
# anterior) ou HOJE; a tabela por SUPERVISOR e o TOP 3 de vendedores de
# cada indicador. O desenho (imagem para o WhatsApp e PDF) e do
# parcial_imagem.py - aqui so os numeros.
# =========================================================================
QUANDO_PARCIAL = (("acum", "Acumulado"), ("d1", "D-1"), ("hoje", "Hoje"))
DIAS_CURTOS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
# (15/10) a CATEGORIA PEÇAS do Catalogo BAP 2026; (03/11, Alexandre) de novo
# em PEÇAS LINHA LEVE / PESADA / MOTO - quem soma "pecas" soma as tres (e o
# "PEÇAS" antigo, por seguranca)
LINHAS_PECAS = ("PEÇAS LINHA LEVE", "PEÇAS LINHA PESADA", "PEÇAS LINHA MOTO",
                "PEÇAS")


def dia_util_anterior(ctx, d):
    d = d - timedelta(days=1)
    while d.weekday() >= 5 or d in (ctx.fer or set()):
        d -= timedelta(days=1)
    return d


def periodo_parcial(ctx, quando):
    """(de, ate, rotulo) do ACUMULADO, D-1 ou HOJE."""
    h = ctx.hoje
    if quando == "d1":
        d = dia_util_anterior(ctx, h)
        return d, d, f"D-1 · {DIAS_CURTOS[d.weekday()]} {d:%d/%m/%Y}"
    if quando == "hoje":
        return h, h, f"Hoje · {DIAS_CURTOS[h.weekday()]} {h:%d/%m/%Y}"
    de = h.replace(day=1)
    return de, h, f"Acumulado · {de:%d} a {h:%d/%m/%Y}"


def _dia(x):
    return x.date() if isinstance(x, datetime) else x


def _curto_pessoa(nome) -> str:
    nome = texto(nome)
    if " - " in nome and nome.split(" - ", 1)[0].strip().isdigit():
        nome = nome.split(" - ", 1)[1]
    return _nome_curto(nome).upper() if nome else "(SEM NOME)"


CAD_NOVO_DIA = 1       # (15/10) meta de cadastro novo: 1 por dia util
TOP_PARCIAL = 3        # (07/10) DESTAQUES DO PERIODO: o top 3 (era 5)


def _top5(pares, menor=False):
    """[(nome, valor)] -> os TOP_PARCIAL melhores (sem vazio; zero nao e
    ranking)."""
    ok = [(n, v) for n, v in pares if v is not None and (menor or v > 0)]
    return sorted(ok, key=lambda x: (x[1] if menor else -x[1],
                                     x[0]))[:TOP_PARCIAL]


def parcial_pedidos(ctx, quando="acum"):
    """
    PARCIAL PEDIDOS: os pedidos DIGITADOS no periodo (TABELA_BAP, data do
    pedido, VND e VEA - excluido nao entra): quantidade, faturamento total
    (o valor dos pedidos), faturamento de pecas (linha leve, pesada e moto),
    SKU por pedido e % de desconto sobre a tabela. ABERTOS e ATRASADOS: a
    carteira em aberto AGORA (SLA: faturar em ate PRAZO_FATURAR dias
    uteis). Por supervisor e o top 3 de vendedores.
    """
    de, ate, rot = periodo_parcial(ctx, quando)
    hoje = ctx.hoje
    peds = defaultdict(list)
    for it in ctx.tabela["itens"]:
        if it["tipo"] in ("VND", "VEA") and it.get("dt_pedido") \
                and it.get("pedido"):
            peds[(it["filial"], texto(it["pedido"]))].append(it)
    no_per, abertos = [], []
    for its in peds.values():
        i0 = its[0]
        dp = _dia(i0["dt_pedido"])
        aberto = all(i["tipo"] == "VEA" for i in its)
        prazo = ctx.mais_uteis(dp, bd.PRAZO_FATURAR)
        tab = sum(i["p_tab"] * i["qtd"] for i in its if i["p_tab"] > 0)
        x = {"sup": _curto_pessoa(ctx.supervisor_de(i0["vend"])),
             "vend": _curto_pessoa(ctx.vendedor(i0["vend"])),
             "valor": sum(i["valor"] for i in its),
             "pecas": sum(i["valor"] for i in its
                          if ctx.categoria_bap(i["cod"]) in LINHAS_PECAS),
             "bat": sum(i["valor"] for i in its
                        if ctx.categoria_bap(i["cod"]) == "BATERIAS"),
             "sku": len({i["cod"] for i in its}), "tab": tab,
             "com": sum(i["valor"] for i in its if i["p_tab"] > 0),
             "aberto": aberto,
             "atrasado": bool(aberto and prazo and hoje > prazo)}
        if not aberto:
            dnf = min((_dia(i["dt_nf"]) for i in its
                       if i["tipo"] == "VND" and i.get("dt_nf")), default=None)
            x["no_prazo"] = bool(dnf and prazo and dnf <= prazo)
        if aberto:
            abertos.append(x)
        if de <= dp <= ate:
            no_per.append(x)

    def soma(xs, ab):
        n = len(xs)
        tab = sum(x["tab"] for x in xs)
        com = sum(x["com"] for x in xs)
        fat = [x for x in xs if not x["aberto"]]
        return {"ped": n, "fat": sum(x["valor"] for x in xs),
                "pecas": sum(x["pecas"] for x in xs),
                "bat": sum(x["bat"] for x in xs),
                "sku": sum(x["sku"] for x in xs) / n if n else None,
                "desc": (1 - com / tab) * 100.0 if tab else None,
                "ab": len(ab), "ab_v": sum(x["valor"] for x in ab),
                "atr": sum(1 for x in ab if x["atrasado"]),
                "prazo": (sum(1 for x in fat if x.get("no_prazo"))
                          / len(fat) * 100.0) if fat else None}

    def grupo(chave):
        g, ga = defaultdict(list), defaultdict(list)
        for x in no_per:
            g[x[chave]].append(x)
        for x in abertos:
            ga[x[chave]].append(x)
        return {k: soma(g.get(k, []), ga.get(k, [])) for k in set(g) | set(ga)}
    tot = soma(no_per, abertos)
    sup = grupo("sup")
    vend = {k: v for k, v in grupo("vend").items() if v["ped"]}

    def m(v):
        return moeda_curta(v)
    linhas, cores = [], []
    for k, v in sorted(sup.items(), key=lambda kv: (-kv[1]["fat"], kv[0])):
        linhas.append([k, br(v["ped"]), m(v["fat"]), m(v["pecas"]),
                       m(v["bat"]), br(v["sku"], 1) if v["sku"] else "—",
                       br(v["ab"]), br(v["atr"])])
        cores.append([None] * 7 + ["alerta" if v["atr"] else None])
    # (08/10) % desconto saiu da parcial; fat. pecas e fat. baterias so
    # nas tabelas (nao nos cartoes nem nos destaques)
    total = ["TOTAL", br(tot["ped"]), m(tot["fat"]), m(tot["pecas"]),
             m(tot["bat"]), br(tot["sku"], 1) if tot["sku"] else "—",
             br(tot["ab"]), br(tot["atr"])]
    # (07/10) depois dos destaques: TODOS os vendedores (com pedido no
    # periodo ou em aberto agora), como a tabela do supervisor
    lin_v, cor_v = [], []
    for k, v in sorted(grupo("vend").items(),
                       key=lambda kv: (-kv[1]["fat"], kv[0])):
        lin_v.append([k, br(v["ped"]), m(v["fat"]), m(v["pecas"]),
                      m(v["bat"]), br(v["sku"], 1) if v["sku"] else "—",
                      br(v["ab"]), br(v["atr"])])
        cor_v.append([None] * 7 + ["alerta" if v["atr"] else None])
    return {
        "tipo": "Parcial Pedidos", "titulo": rot, "quando": quando,
        "fonte": "fonte TABELA_BAP (pedidos)",
        "cartoes": [
            ("Pedidos", br(tot["ped"]), f"{br(len(vend))} vendedores", "ok"),
            ("Faturamento total", m(tot["fat"]), "valor dos pedidos", "ok"),
            ("SKU por pedido", br(tot["sku"], 1) if tot["sku"] else "—",
             "itens distintos", "ok"),
            # (07/10) a carteira em aberto foi da faixa para os cartoes
            ("Em aberto agora", br(tot["ab"]),
             f"{m(tot['ab_v'])} em pedidos", "ok")],
        "faixa": None,
        "tabela": {"titulo": "Por supervisor",
                   "colunas": ["SUPERVISOR", "PED.", "FAT. TOTAL",
                               "FAT. PEÇAS", "FAT. BAT.", "SKU/PED.",
                               "ABERTOS", "ATRAS."],
                   "linhas": linhas, "cores": cores, "total": total},
        "tabela_vend": {"titulo": "Todos os vendedores",
                        "colunas": ["VENDEDOR", "PED.", "FAT. TOTAL",
                                    "FAT. PEÇAS", "FAT. BAT.", "SKU/PED.",
                                    "ABERTOS", "ATRAS."],
                        "linhas": lin_v, "cores": cor_v, "total": total}
        if lin_v else None,
        "nota": "" if no_per else "Nenhum pedido digitado no período.",
        "rankings": [
            ("Qtd. pedidos", [(k, vend[k]["ped"], br(vend[k]["ped"]))
                              for k, _ in _top5([(k, v["ped"]) for k, v in
                                                 vend.items()])], False),
            ("Faturamento total", [(k, vend[k]["fat"], m(vend[k]["fat"]))
                                   for k, _ in _top5([(k, v["fat"]) for k, v
                                                      in vend.items()])],
             False),
            ("SKU por pedido", [(k, vend[k]["sku"], br(vend[k]["sku"], 1))
                                for k, _ in _top5([(k, v["sku"]) for k, v in
                                                   vend.items()])], False)],
        "numeros": {"total": tot, "sup": sup, "vend": vend},
    }


def lote_fora(ctx) -> set:
    """(21/10, Alexandre) Os dias de cadastro EM LOTE (A1_DTCAD) que nao
    contam como visita em relatorio nenhum (parametro do Planner
    datas_cadastro_lote_fora; hoje 16/10/2026)."""
    if not hasattr(ctx, "_lote_fora"):
        try:
            import json                                 # noqa: PLC0415
            import planner_nucleo as nu                 # noqa: PLC0415
            cfg_ = json.loads((Path(ctx.raiz) / "planner_config.json")
                              .read_text("utf-8"))
            ctx._lote_fora = nu.datas_cadastro_lote_fora(cfg_)
        except Exception:                               # noqa: BLE001
            ctx._lote_fora = {date(2026, 10, 16)}
    return ctx._lote_fora


def cadastros_do_dia(ctx) -> dict:
    """(15/10) {(cod do vendedor, dia): clientes cadastrados} - a
    dClientesBap (A1_DTCAD, A1_VEND), a base que o BAP Tools atualiza.
    (21/10) Sem o cadastro em lote (lote_fora): ele nao e visita."""
    if not hasattr(ctx, "_cad_dia"):
        g = Counter()
        fora_ = lote_fora(ctx)
        try:
            clientes_ = (ctx.tabela.get("clientes") or {}).values()
        except Exception:                               # noqa: BLE001
            clientes_ = ()          # sem TABELA_BAP: so as visitas
        for c in clientes_:
            dc = _dia(c.get("dtcad"))
            if dc in fora_:
                continue
            if dc and texto(c.get("vend")):
                g[(_cod6(c["vend"]), dc)] += 1
        ctx._cad_dia = dict(g)
    return ctx._cad_dia


def prospeccao_do_dia(ctx) -> dict:
    """(22/10, Alexandre) {(cod do vendedor, dia): visitas de PROSPECCAO
    que contam} - as respostas do Microsoft Forms (visita a cliente fora da
    base) validadas pelo "Atualizar visitas" (prospeccao_forms; arquivos
    RELATORIOS\\Visitas\\PROSPECCAO\\PROSPECCAO_AAAAMM.xlsx, STATUS =
    CONTA)."""
    if not hasattr(ctx, "_prosp_dia"):
        try:
            import prospeccao_forms as pf               # noqa: PLC0415
            ctx._prosp_dia = pf.contagem(ctx.raiz)
        except Exception:                               # noqa: BLE001
            ctx._prosp_dia = {}
    return ctx._prosp_dia


def hora_da_prospeccao(x):
    """(09/11, recado 20261109-1300) A HORA local do envio da prospeccao,
    em segundos do dia (None sem hora). App BAP Ajuda: ja vem na hora local
    do celular; Forms: a hora de conclusao (UTC) no fuso da UF do
    estabelecimento [SUPOSICAO: a linha salva nao guarda a UF do vendedor]."""
    import prospeccao_forms as pf                       # noqa: PLC0415
    m = re.search(r"(\d{1,2}):(\d{2})", texto(x.get("conclusao")))
    if not m:
        return None
    s = int(m.group(1)) * 3600 + int(m.group(2)) * 60
    if texto(x.get("fonte")) != pf.FONTE_APP and getattr(
            pf, "HORA_DO_FORMS_EM_UTC", False):
        fuso = getattr(pf, "FUSO_UF", {}).get(
            texto(x.get("uf") or "AM").upper(),
            -4)
        s = (s + fuso * 3600) % 86400
    return s


def horas_da_prospeccao(ctx) -> dict:
    """(09/11, recado 20261109-1300) {(cod6 do vendedor, dia): (hora da 1a,
    hora da ultima)} das prospeccoes que CONTAM (as mesmas do PROSP.) - a
    prospeccao e atividade do dia: entra no INICIO e na ULT. ATIV."""
    if not hasattr(ctx, "_prosp_hora"):
        hs = {}
        try:
            import prospeccao_forms as pf               # noqa: PLC0415
            for x in pf.linhas(ctx.raiz):
                if x.get("status") != pf.ST_CONTA or not x.get("dia") \
                        or not x.get("cod6"):
                    continue
                h = hora_da_prospeccao(x)
                if h is None:
                    continue
                k = (_cod6(x["cod6"]), x["dia"])
                a = hs.get(k)
                hs[k] = (min(a[0], h), max(a[1], h)) if a else (h, h)
        except Exception:                               # noqa: BLE001
            hs = {}
        ctx._prosp_hora = hs
    return ctx._prosp_hora


def _linha_so_prospeccao(ctx, modelo, d, n) -> dict:
    """(22/10) O dia em que o vendedor so tem PROSPECCAO (nenhuma linha da
    Maxima): vira dia em campo com as visitas da prospeccao, sem jornada,
    TMA, TMD e km [SUPOSICAO do Analista]. Os dados do vendedor vem de
    outra linha dele (modelo)."""
    l = dict(modelo)
    for k in ("ag_maxima", "fonte_rota", "nao_visit", "rota_arq",
              "deposito", "fora_rota"):
        l.pop(k, None)
    l.update(data=d, primeiro=None, ultimo=None, ult_pos=None, tmd=0, tma=0,
             agendados=0, vis_agenda=0, vis_fora=n, visitas=n, venda=0.0,
             km_trab=0.0, km_total=0.0, gps=True, versao="",
             arquivo="PROSPECÇÃO (Forms)", fechado=d < ctx.hoje,
             cad_visita=0, prosp_visita=n, so_prospeccao=True)
    return l


def com_cadastro_como_visita(ctx, regs, de=None, ate=None) -> list:
    """(15/10, Alexandre) CADASTRO NOVO FEITO NO DIA CONTA COMO VISITA:
    soma os cadastros do vendedor naquele dia nas visitas da linha do
    GridRca (a linha ganha cad_visita). Vale na Parcial Visitas, no
    Farol de Visita e (no Gerador de Meta) na visita da RV.
    (22/10, Alexandre) A PROSPECCAO do Microsoft Forms (visita a cliente
    fora da base, STATUS = CONTA) soma do mesmo jeito (prosp_visita) e e
    FORA DE ROTA. Dia so com prospeccao (sem linha da Maxima): ganha uma
    linha propria (de/ate: so os dias desse periodo).
    (09/11, recado 20261109-1300) a HORA da prospeccao entra na jornada: a
    ULT. ATIV. = a maior entre o ultimo cliente e a ultima prospeccao; o
    INICIO = a 1a prospeccao quando vem antes do 1o cliente [SUPOSICAO]
    (prosp_ini / prosp_fim na linha; o expediente nao muda)."""
    cad = cadastros_do_dia(ctx)
    pro = prospeccao_do_dia(ctx)
    hrs = horas_da_prospeccao(ctx)
    saida, usados, modelo = [], set(), {}
    for l in regs:
        cp = _cod6(l["cod_protheus"]) if l.get("cod_protheus") else ""
        n = cad.get((cp, l["data"]), 0) if cp else 0
        k = (cp, l["data"])
        pr = pro.get(k, 0) if cp and k not in usados else 0
        if pr:
            usados.add(k)
        if cp and (cp not in modelo or l["data"] > modelo[cp]["data"]):
            modelo[cp] = l
        if n or pr:
            l = dict(l, visitas=(l.get("visitas") or 0) + n + pr,
                     cad_visita=n, prosp_visita=pr,
                     vis_fora=(l.get("vis_fora") or 0) + pr)
        if pr and k in hrs:
            h0, h1 = hrs[k]
            l = dict(l, prosp_ini=h0, prosp_fim=h1,
                     primeiro=min(l["primeiro"], h0) if l.get("primeiro")
                     else h0,
                     ultimo=max(l["ultimo"], h1) if l.get("ultimo")
                     else h1)
        saida.append(l)
    for (cp, d), n in sorted(pro.items()):
        if (cp, d) in usados or cp not in modelo or not n:
            continue
        if (de and d < de) or (ate and d > ate):
            continue
        saida.append(_linha_so_prospeccao(ctx, modelo[cp], d, n))
    return saida


# (22/10, Alexandre) as colunas da Parcial Visitas - o Farol de Visita usa
# as mesmas (+ CAD. C/ COMPRA, depois de CAD.)
COLUNAS_VISITA_PARCIAL = ["META", "VISIT.", "% META", "% CONV.",
                          "% FORA DE ROTA", "CAD.", "PROSP.", "INÍCIO",
                          "ÚLT. ATIV.",
                          "JORNADA LÍQ.", "DIAS < JORN. LÍQ.", "INTERV. ALMOÇO",
                          "DIAS ALMOÇO > MÁX.", "TMA", "TMD", "KM",
                          "KM/CLIENTE"]


def _cartao_almoco(ra, jt):
    """(22/10, Alexandre) o cartao do INTERVALO DE ALMOCO (pelo checkout):
    a media, o maximo e os dias acima dele."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    acima = ra["media"] is not None and ra["media"] > jt["almoco_max"]
    return kpi("Intervalo almoço", vn.hhmm(ra["media"]),
               "alerta" if acima else ("ok" if ra["media"] is not None
                                       else "neutro"),
               "fim da manhã → 1º cliente da tarde", linhas=[
                   ("Máximo", vn.hhmm(jt["almoco_max"]), ""),
                   ("Dias acima do máximo",
                    f"{br(ra['acima'])} de {br(ra['dias'])}",
                    "alerta" if ra["acima"] else "ok")])


def _cartao_jornada(rj, jt):
    """(22/10, Alexandre) o cartao da JORNADA LIQUIDA: a media, a meta e o
    atingimento embaixo, e os dias abaixo dela."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    at = pct_de(rj["media"], jt["liquida"]) if rj["media"] is not None \
        else None
    return kpi("Jornada líquida", vn.hhmm(rj["media"]),
               {"ok": "ok", "atencao": "atencao", "alerta": "alerta"}.get(
                   _tom_ating(at), "neutro"),
               "da 1ª à última atividade do dia", linhas=[
                   ("Meta", vn.hhmm(jt["liquida"]), ""),
                   ("Atingimento", p(at), _tom_ating(at)),
                   ("Dias abaixo da jornada líquida",
                    f"{br(rj['abaixo'])} de {br(rj['dias'])}",
                    "alerta" if rj["abaixo"] else "ok")])


def _jornada_do_mes(ctx, ano, mes) -> dict:
    """(22/10, Alexandre) A JORNADA DE TRABALHO do Planner do mes
    (Parametros > JORNADA DE TRABALHO): {inicio, fim, fim_sexta, liquida}
    em segundos. Sem Planner: o padrao (07:30-18:00, sexta 17:00, 08:00)."""
    try:
        import pastas_bap as pb                         # noqa: PLC0415
        import planner_nucleo as nu                     # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        return {"inicio": 27000, "fim": 64800, "fim_sexta": 61200,
                "liquida": 28800, "almoco_max": 5400}
    cfg = {}
    try:
        ano = ano or ctx.hoje.year
        mes = mes or ctx.hoje.month
        cfg = nu.carregar_config(pb.config_do_planner(ctx.raiz,
                                                      f"{ano}-{mes:02d}"))
    except Exception:                                   # noqa: BLE001
        cfg = {}
    jt = nu.jornada_de_trabalho(cfg)
    jt.setdefault("almoco_max", 5400)
    return jt


def jornada_liquida(l, jt):
    """(22/10) A JORNADA LIQUIDA do vendedor no dia: do 1o ao ultimo cliente
    atendido, so dentro do expediente (segunda a sexta; sexta termina mais
    cedo). Sabado, domingo ou dia sem cliente: None."""
    d = l.get("data")
    if not d or d.weekday() >= 5 or not l.get("primeiro") \
            or not l.get("ultimo"):
        return None
    fim = jt["fim_sexta"] if d.weekday() == 4 else jt["fim"]
    return max(0, min(l["ultimo"], fim) - max(l["primeiro"], jt["inicio"]))


MEIO_DIA = 12 * 3600       # (22/10) o corte entre a manha e a tarde


def _aderencia_memo(ctx, de, ate):
    """aderencia_planner (Espelho cliente a cliente) uma vez por contexto."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    memo = ctx.__dict__.setdefault("_ad_memo", {})
    if (de, ate) not in memo:
        try:
            memo[(de, ate)] = vn.aderencia_planner(ctx.raiz, de, ate) or {}
        except Exception:                               # noqa: BLE001
            memo[(de, ate)] = {}
    return memo[(de, ate)]


def almocos_do_periodo(ctx, de, ate) -> dict:
    """(22/10, Alexandre) INTERVALO DE ALMOCO pelo CHECKOUT: do fim da
    ultima visita que comecou antes das 12:00 ate o inicio da 1a visita que
    comecou as 12:00 ou depois (Espelho da Maxima). {(cod Maxima, data):
    segundos}; dia sem visita de manha ou sem visita a tarde fica de fora."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    dia = defaultdict(list)
    for c in (_aderencia_memo(ctx, de, ate) or {}).get("clientes") or []:
        if c.get("situacao") == vn.SIT_NAO or not c.get("inicio"):
            continue
        dia[(c["cod_max"], c["data"])].append(
            (c["inicio"], c.get("fim") or c["inicio"]))
    saida = {}
    for k, vs in dia.items():
        if k[1].weekday() >= 5:
            continue
        manha = [x for x in vs if x[0] < MEIO_DIA]
        tarde = [x for x in vs if x[0] >= MEIO_DIA]
        if manha and tarde:
            saida[k] = max(0, min(x[0] for x in tarde)
                           - max(x[1] for x in manha))
    return saida


def resumo_almoco(raws, alm, jt) -> dict:
    """{media, acima, dias}: o intervalo de almoco medio das linhas e
    quantos dias passaram do maximo (parametro JORNADA DE TRABALHO)."""
    vals = [alm[(l["cod"], l["data"])] for l in raws
            if (l.get("cod"), l.get("data")) in alm]
    mx = jt.get("almoco_max", 5400)
    return {"media": sum(vals) / len(vals) if vals else None,
            "acima": sum(1 for v in vals if v > mx), "dias": len(vals)}


def resumo_jornada(raws, jt) -> dict:
    """{media, abaixo, dias}: a media da jornada liquida dos dias em campo
    (segunda a sexta) e quantos desses dias JA FECHADOS ficaram abaixo da
    jornada liquida minima (o dia de hoje, ainda aberto, nao conta)."""
    vals, abx, dias, fech = [], 0, 0, []
    for l in raws:
        j = jornada_liquida(l, jt)
        if j is None or not l.get("visitas"):
            continue
        vals.append(j)
        if l.get("fechado", True):
            fech.append(j)
            dias += 1
            if j < jt["liquida"]:
                abx += 1
    # (05/11, Alexandre: "tirar ... hoje da conta") a MEDIA so dos dias
    # fechados; o dia de hoje (aberto) so entra quando e o unico
    base = fech or vals
    return {"media": sum(base) / len(base) if base else None,
            "abaixo": abx, "dias": dias}


def km_por_cliente(km, visitas):
    """(22/10, Alexandre) KM/CLIENTE = o km rodado / as visitas (o km entre
    um cliente e outro)."""
    return km / visitas if km and visitas else None


def _visitados_e_compras(ctx, regs, de, ate):
    """(22/10) ({vend curto: {cliente: {dias da visita}}}, {cliente:
    [datas dos pedidos VND/VEA no periodo]}) - a base da CONVERSAO (Parcial
    Visitas e Farol de Visita). Visitados = Espelho da Maxima (cliente a
    cliente) + cadastros novos do periodo (sem o lote)."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    try:
        ad = vn.aderencia_planner(ctx.raiz, de, ate) if regs else {}
    except Exception:                                   # noqa: BLE001
        ad = {}
    chaves = {(l["cod"], l["data"]): l for l in regs}
    por_cp = {}
    for l in regs:
        if l.get("cod_protheus"):
            por_cp.setdefault(_cod6(l["cod_protheus"]), l)
    vis = defaultdict(lambda: defaultdict(set))
    for c in (ad or {}).get("clientes") or []:
        if c["situacao"] == vn.SIT_NAO or not c.get("cod_cliente"):
            continue
        l = chaves.get((c["cod_max"], c["data"]))
        if l is not None:
            vis[_curto_pessoa(l["vendedor"])][_cod6(c["cod_cliente"])].add(
                c["data"])
    fora_ = lote_fora(ctx)
    try:
        cli_tab = ctx.tabela.get("clientes") or {}
    except Exception:                                   # noqa: BLE001
        cli_tab = {}
    for cod, c in cli_tab.items():
        dc = _dia(c.get("dtcad"))
        l = por_cp.get(_cod6(c.get("vend"))) if texto(c.get("vend")) else None
        if dc and de <= dc <= ate and l is not None and dc not in fora_:
            vis[_curto_pessoa(l["vendedor"])][_cod6(cod)].add(dc)
    compras = defaultdict(list)
    try:
        itens = ctx.tabela["itens"]
    except Exception:                       # noqa: BLE001 - sem TABELA_BAP
        itens = []
    for it in itens:
        dp = _dia(it.get("dt_pedido"))
        if it["tipo"] in ("VND", "VEA") and dp and de <= dp <= ate:
            compras[_cod6(it["cliente"])].append(dp)
    return vis, compras


def _conversao_de(vis, compras, vends, so_dias=None):
    """(visitados, compraram) dos vendedores (nome curto); so_dias: so as
    visitas desses dias (a linha do dia a dia)."""
    n = c = 0
    for v in vends:
        for cod, ds in (vis.get(v) or {}).items():
            dd = [d for d in ds if so_dias is None or d in so_dias]
            if not dd:
                continue
            n += 1
            d0 = min(dd)
            if any(x >= d0 for x in compras.get(cod, ())):
                c += 1
    return n, c


def _conversao_dos_visitados(ctx, regs, de, ate) -> dict:
    """(22/10, Alexandre) CONVERSAO = % dos clientes VISITADOS que
    COMPRARAM. Por vendedor (nome curto): {vend: (visitados, compraram)}.
    Comprou = pedido VND/VEA do cliente no dia da 1a visita do periodo ou
    depois, ate o fim do periodo."""
    vis, compras = _visitados_e_compras(ctx, regs, de, ate)
    return {v: _conversao_de(vis, compras, [v]) for v in vis}


def parcial_visitas(ctx, quando="acum"):
    """
    PARCIAL VISITAS E POSITIVACAO: do GridRca da Maxima (o mesmo do Farol
    de Visita, so vendedor ativo e com meta de visita no mes) - (21/10) a
    META DE VISITA do periodo (a do Planner: 12 por dia util, interior 6,
    12 na cidade base, desde a admissao - a mesma do Farol de Visita),
    VISITADOS e % DA META; (22/10) % FORA DE ROTA (o do Farol de Visita:
    fora da rota do Planner - a agenda da Maxima saiu); POSITIVACAO = clientes diferentes com
    pedido digitado (VND/VEA) pelo vendedor no periodo; e a JORNADA:
    INICIO (1o cliente), ULT. ATIVIDADE (o ultimo cliente atendido), TMA e
    TMD (no acumulado, as medias dos dias). Por supervisor e o top 3.
    (15/10) CADASTROS NOVOS: clientes com a data de cadastro (A1_DTCAD da
    base do BAP Tools) no periodo, pelo vendedor do cadastro (A1_VEND).
    Meta: CAD_NOVO_DIA por dia util do periodo, por vendedor. E o cadastro
    do dia CONTA COMO VISITA (VISITADOS ja traz os cadastros).
    """
    import visitas_nucleo as vn                         # noqa: PLC0415
    de, ate, rot = periodo_parcial(ctx, quando)
    c_m = Contexto(ctx.raiz, ctx.hoje, params={"MÊS": de.month,
                                               "ANO": de.year})
    metas, du_mes, _r = _meta_de_visita(c_m, de.year, de.month)
    metas_dia, adm_de = _metas_de_visita_por_dia(ctx, de.year, de.month)

    def util(d):
        return d.weekday() < 5 and d not in ctx.fer
    dias_p = [de + timedelta(days=i) for i in range((ate - de).days + 1)]

    def chave_v(l):
        return (_cod6(l["cod_protheus"]) if l.get("cod_protheus") else
                "N:" + vn.chave_de_nome(l["vendedor"]))

    def meta_mes_de(l):
        m = metas.get(_cod6(l["cod_protheus"])) if l.get("cod_protheus") \
            else None
        return m if m is not None else metas.get(
            "N:" + vn.chave_de_nome(l["vendedor"]))

    def tem_meta(l):
        if not metas:
            return True
        return meta_mes_de(l) is not None
    regs = com_cadastro_como_visita(ctx, [
        l for l in vn.registros(ctx.raiz)
        if de <= l["data"] <= ate and l.get("ativo") and tem_meta(l)],
        de, ate)
    # (22/10, Alexandre) % FORA DE ROTA = o mesmo do Farol de Visita: o que
    # foi visitado fora da rota do PLANNER (linha sem Espelho: a agenda da
    # Maxima), numa copia - os outros numeros da parcial nao mudam
    regs = [dict(l) for l in regs]
    _cp = [dict(l) for l in regs]
    _aplicar_aderencia_planner(ctx, _cp, de, ate)
    for l, c_ in zip(regs, _cp):
        l["fora_rota"] = c_.get("vis_fora", l.get("vis_fora") or 0)
    conv_v = _conversao_dos_visitados(ctx, regs, de, ate)
    jt = _jornada_do_mes(ctx, de.year, de.month)
    alm = almocos_do_periodo(ctx, de, ate)
    # (21/10, Alexandre) A META DE VISITA DO PERIODO por vendedor (a soma da
    # meta de cada dia do periodo, desde a admissao)
    meta_v = {}
    for l in regs:
        k_ = chave_v(l)
        if k_ in meta_v or l.get("cargo", "VENDEDOR") != "VENDEDOR":
            continue
        m_mes = meta_mes_de(l)
        if m_mes is None:
            continue
        c6 = k_ if not k_.startswith("N:") else None
        a_ = adm_de.get(c6) if c6 else None
        meta_v[k_] = sum(_meta_visita_no_dia(metas_dia, c6, m_mes, d, du_mes,
                                             util(d)) or 0
                         for d in dias_p if not a_ or d >= a_)
    cli_dia = defaultdict(set)
    for it in ctx.tabela["itens"]:
        if it["tipo"] in ("VND", "VEA") and it.get("dt_pedido"):
            cli_dia[(_cod6(it.get("vend")), _dia(it["dt_pedido"]))].add(
                it["cliente"])

    # os cadastros novos do periodo, por vendedor (A1_VEND)
    cad_v = Counter()
    for c in (ctx.tabela.get("clientes") or {}).values():
        dc = _dia(c.get("dtcad"))
        if dc and de <= dc <= ate and texto(c.get("vend")):
            cad_v[_cod6(c["vend"])] += 1
    du_ = max(1, _uteis_de(ctx, de, ate)) if quando == "acum" else 1

    def pos_de(l):
        if not l.get("cod_protheus"):
            return set()
        return cli_dia.get((_cod6(l["cod_protheus"]), l["data"]), set())

    def soma(ls):
        ag = sum(l["agendados"] for l in ls)
        na = sum(l["vis_agenda"] for l in ls)
        vis = sum(l["visitas"] for l in ls)
        cli = set()
        for l in ls:
            cli |= {(l.get("cod_protheus"), c) for c in pos_de(l)}
        cods = {_cod6(l["cod_protheus"]) for l in ls if l.get("cod_protheus")}
        cad = sum(cad_v.get(c_, 0) for c_ in cods)
        # (22/10) a PROSPECCAO do Forms que contou como visita
        prosp = sum(l.get("prosp_visita") or 0 for l in ls)
        m_cad = du_ * CAD_NOVO_DIA * len(cods)
        ks = {chave_v(l) for l in ls}
        mv = sum(meta_v[k_] for k_ in ks if k_ in meta_v) \
            if any(k_ in meta_v for k_ in ks) else None
        rs = vn.resumir(ls)
        rj = resumo_jornada(ls, jt)
        ra = resumo_almoco(ls, alm, jt)
        fora = sum(l.get("fora_rota", l.get("vis_fora") or 0) for l in ls)
        vs_ = {_curto_pessoa(l["vendedor"]) for l in ls}
        c_vis = sum(conv_v[v][0] for v in vs_ if v in conv_v)
        c_com = sum(conv_v[v][1] for v in vs_ if v in conv_v)
        return {"ag": ag, "vis": vis, "na": na, "fora": fora,
                "p_fora": pct_de(fora, vis) if vis else None,
                "pct": pct_de(na, ag) if ag else None, "pos": len(cli),
                # (22/10) CONVERSAO: % dos clientes visitados que compraram
                "c_vis": c_vis, "c_com": c_com,
                "conv": pct_de(c_com, c_vis) if c_vis else None,
                "cad": cad, "m_cad": m_cad, "prosp": prosp,
                "p_cad": pct_de(cad, m_cad) if m_cad else None,
                "meta": mv, "p_meta": pct_de(vis, mv) if mv else None,
                "ini": rs["inicio"], "ult": rs["fim"], "tma": rs["tma"],
                "tmd": rs["tmd"], "km": rs["km_rodado"],
                "jl": rj["media"], "jl_abx": rj["abaixo"],
                "jl_dias": rj["dias"], "alm": ra["media"],
                "alm_acima": ra["acima"], "alm_dias": ra["dias"],
                "km_cli": km_por_cliente(rs["km_rodado"], vis)}
    g_s, g_v = defaultdict(list), defaultdict(list)
    for l in regs:
        g_s[_curto_pessoa(l["supervisor"] or "(SEM SUPERVISOR)")].append(l)
        g_v[_curto_pessoa(l["vendedor"])].append(l)
    tot = soma(regs)
    sup = {k: soma(v) for k, v in g_s.items()}
    vend_t = {k: soma(v) for k, v in g_v.items()}
    vend = {k: v for k, v in vend_t.items() if v["ag"] or v["vis"]
            or v["meta"]}

    def tom(v):
        if v is None:
            return None
        return "ok" if v >= 80 else ("atencao" if v >= 50 else "alerta")

    def ms(seg):
        """TMA/TMD em minutos:segundos (a Maxima mostra 00:24:30)."""
        if seg is None:
            return "—"
        seg = int(round(seg))
        return f"{seg // 60}:{seg % 60:02d}"

    def linha(k, v):
        # (08/10) o resultado primeiro (meta, visitados, % meta,
        # positivados, conversao), (21/10) a jornada; (22/10, Alexandre) sem
        # AGEND., NA AG. e % CAD. - da agenda so o % FORA DE ROTA
        return [k, br(v["meta"]) if v["meta"] is not None else "—",
                br(v["vis"]), p(v["p_meta"]), p(v["conv"]), p(v["p_fora"]),
                br(v["cad"]), br(v["prosp"]), vn.hhmm(v["ini"]),
                vn.hhmm(v["ult"]),
                # (22/10, Alexandre) a JORNADA LIQUIDA e os dias abaixo dela;
                # TMA e TMD em HH:MM; KM e KM/CLIENTE
                vn.hhmm(v["jl"]), br(v["jl_abx"]),
                # (22/10) o INTERVALO DE ALMOCO (checkout) e os dias acima
                vn.hhmm(v["alm"]), br(v["alm_acima"]),
                vn.hhmm(v["tma"]), vn.hhmm(v["tmd"]), br(v["km"]),
                br(v["km_cli"], 1) if v["km_cli"] is not None else "—"]

    def cor(v):
        pj = pct_de(v["jl"], jt["liquida"]) if v["jl"] is not None else None
        return ([None, None, None, tom(v["p_meta"])] + [None] * 6
                + [_tom_ating(pj) or None, "alerta" if v["jl_abx"] else None]
                + ["alerta" if v["alm"] is not None
                   and v["alm"] > jt["almoco_max"] else None,
                   "alerta" if v["alm_acima"] else None]
                + [None] * 4)

    def ordem(kv):
        return (-(kv[1]["p_meta"] if kv[1]["p_meta"] is not None else -1),
                -kv[1]["vis"], kv[0])
    linhas, cores = [], []
    for k, v in sorted(sup.items(), key=ordem):
        linhas.append(linha(k, v))
        cores.append(cor(v))
    total = linha("TOTAL", tot)
    # (07/10) depois dos destaques: TODOS os vendedores do periodo (com
    # meta, agenda ou visita), como a tabela do supervisor
    lin_v, cor_v = [], []
    for k, v in sorted(vend.items(), key=ordem):
        lin_v.append(linha(k, v))
        cor_v.append(cor(v))
    # (22/10, Alexandre) POSITIVACAO trocada pela CONVERSAO
    cols = list(COLUNAS_VISITA_PARCIAL)
    rot_meta = ("Meta do dia" if quando != "acum" else
                f"Meta até {ate:%d/%m}")
    return {
        "tipo": "Parcial Visitas e Conversão", "titulo": rot,
        "quando": quando, "fonte": "fonte GridRca Máxima + TABELA_BAP",
        "cartoes": [
            # (22/10, Alexandre) sem o cartao da meta (ela esta nas
            # tabelas): VISITADOS com o % da meta e o KM RODADO
            ("Visitados", br(tot["vis"]),
             f"{p(tot['p_meta'])} da {rot_meta.lower()} "
             f"({br(tot['meta']) if tot['meta'] is not None else '—'})",
             tom(tot["p_meta"]) or "ok"),
            # (22/10) a agenda da Maxima saiu: o % FORA DE ROTA (Planner)
            ("% fora de rota", p(tot["p_fora"]),
             f"{br(tot['fora'])} visitas fora da rota do Planner", "ok"),
            ("Conversão", p(tot["conv"]),
             f"{br(tot['c_com'])} de {br(tot['c_vis'])} visitados compraram",
             "ok"),
            ("Cadastros novos", br(tot["cad"]),
             f"meta {br(tot['m_cad'])} · {p(tot['p_cad'])}"
             + (f" · {br(tot['prosp'])} prospecção" if tot["prosp"]
                else ""),
             tom(tot["p_cad"]) or "ok"),
            ("Jornada líquida", vn.hhmm(tot["jl"]),
             f"meta {vn.hhmm(jt['liquida'])} · "
             f"{p(pct_de(tot['jl'], jt['liquida']))} de ating."
             if tot["jl"] is not None else
             f"meta {vn.hhmm(jt['liquida'])}",
             tom(pct_de(tot["jl"], jt["liquida"]))
             if tot["jl"] is not None else "ok"),
            ("Intervalo almoço", vn.hhmm(tot["alm"]),
             f"máx. {vn.hhmm(jt['almoco_max'])} · {br(tot['alm_acima'])} de "
             f"{br(tot['alm_dias'])} dias acima",
             "alerta" if tot["alm"] is not None
             and tot["alm"] > jt["almoco_max"] else "ok"),
            ("KM rodado", br(tot["km"]),
             f"{br(tot['km_cli'], 1) if tot['km_cli'] is not None else '—'}"
             f" km por cliente", "ok")],
        "faixa": None,
        "tabela": {"titulo": "Por supervisor",
                   "colunas": ["SUPERVISOR"] + cols,
                   "linhas": linhas, "cores": cores, "total": total},
        "tabela_vend": {"titulo": "Todos os vendedores",
                        "colunas": ["VENDEDOR"] + cols,
                        "linhas": lin_v, "cores": cor_v, "total": total}
        if lin_v else None,
        # (07/10) a parcial e motivacional: quem nao teve agenda nem
        # visita nao e citado (fica no Farol de Visita)
        "nota": ("INÍCIO = 1º cliente ou prospecção · ÚLT. ATIV. = "
                 "último cliente atendido ou prospecção"
                 + (" (médias dos dias)" if quando == "acum"
                    else "") + " · JORNADA LÍQ. = do 1º ao "
                 f"último cliente/prospecção dentro do expediente "
                 f"({vn.hhmm(jt['inicio'])} às {vn.hhmm(jt['fim'])}, sexta "
                 f"até {vn.hhmm(jt['fim_sexta'])}); meta "
                 f"{vn.hhmm(jt['liquida'])} · ALMOÇO = fim da última "
                 f"visita da manhã → início da 1ª da tarde (máx. "
                 f"{vn.hhmm(jt['almoco_max'])}) · TMA e TMD em HH:MM · "
                 "KM/CLI. = km rodado ÷ visitas · VISIT. já inclui a "
                 "prospecção do Forms")
        if regs else
        "Sem visita baixada no período: clique em Atualizar visitas.",
        "rankings": [
            ("Visitados", [(k, vend[k]["vis"], br(vend[k]["vis"])) for k, _ in
                           _top5([(k, v["vis"]) for k, v in vend.items()])],
             False),
            ("% da meta de visita", [(k, vend[k]["p_meta"],
                                      p(vend[k]["p_meta"]))
                                     for k, _ in _top5([(k, v["p_meta"])
                                                        for k, v in
                                                        vend.items()])],
             False),
            ("Conversão", [(k, vend[k]["conv"], p(vend[k]["conv"])) for k, _
                           in _top5([(k, v["conv"]) for k, v in vend.items()
                                     if v["c_com"]])], False),
            ("Cadastros novos", [(k, vend_t[k]["cad"], br(vend_t[k]["cad"]))
                                 for k, _ in _top5([(k, v["cad"]) for k, v
                                                    in vend_t.items()])],
             False)],
        "numeros": {"total": tot, "sup": sup, "vend": vend},
        # (19/10, Alexandre) o detalhe dos clientes visitados por vendedor
        "detalhe": _detalhe_dos_visitados(
            ctx, regs, de, ate, [x[0] for x in lin_v], quando == "acum",
            [x[0] for x in linhas]),
    }


# =========================================================================
# (19/10, Alexandre) DETALHE DOS CLIENTES VISITADOS na Parcial Visitas: por
# vendedor, cada cliente visitado no periodo (Espelho da Maxima, cliente a
# cliente - o mesmo do Farol de Visita) e os CADASTROS NOVOS do periodo (que
# contam como visita), com o LIMITE (BASE_CLIENTE), se JA COMPROU NO MES
# (positivacao: liquido do mes > 0; EM ABERTO = so pedido sem nota), o
# SEGMENTO (BASE_CLIENTE) e o PRAZO cadastrado (A1_COND do Protheus).
# =========================================================================
LIMITE_DETALHE_PNG = 160    # linhas do detalhe que cabem na imagem da parcial
COMPROU_SIM, COMPROU_ABERTO, COMPROU_NAO = "SIM", "EM ABERTO", "NÃO"
ROTA_NA, ROTA_FORA = "NA ROTA", "FORA DA ROTA"


def _prazo_curto(desc) -> str:
    t = texto(desc).upper()
    return t[3:].strip() if t.startswith("P/ ") else t


def _detalhe_dos_visitados(ctx, regs, de, ate, ordem_vend, acum,
                           ordem_sup=()):
    """{titulo, colunas, blocos: [{vendedor, supervisor, resumo, linhas,
    cores}], linhas (total), sem_detalhe, rodape} - ou None sem nada."""
    import visitas_nucleo as vn                         # noqa: PLC0415
    try:
        ad = vn.aderencia_planner(ctx.raiz, de, ate) if regs else {}
    except Exception:                                   # noqa: BLE001
        ad = {}
    chaves = {(l["cod"], l["data"]): l for l in regs}
    por_cp = {}
    for l in regs:
        if l.get("cod_protheus"):
            por_cp.setdefault(_cod6(l["cod_protheus"]), l)
    vis, sups, com_esp = defaultdict(dict), {}, set()

    def soma(l, cod, loja, nome, d, novo, rota=None):
        v = _curto_pessoa(l["vendedor"])
        sups.setdefault(v, _curto_pessoa(l["supervisor"] or
                                         "(SEM SUPERVISOR)"))
        x = vis[v].setdefault((cod, loja), {"nome": "", "dias": set(),
                                            "novo": False, "sit": {}})
        x["nome"] = x["nome"] or texto(nome)
        x["dias"].add(d)
        x["novo"] = x["novo"] or novo
        # (19/10, Alexandre) ROTA DO DIA: o cliente estava programado no
        # Planner para aquele dia (o mesmo do Farol de Visita). Cadastro
        # novo sem visita no Espelho fica FORA DA ROTA
        if rota is not None or d not in x["sit"]:
            x["sit"][d] = ROTA_NA if rota else ROTA_FORA
    for c in (ad or {}).get("clientes") or []:
        if c["situacao"] == vn.SIT_NAO:
            continue
        l = chaves.get((c["cod_max"], c["data"]))
        if l is not None and c.get("cod_cliente"):
            soma(l, _cod6(c["cod_cliente"]), _loja2(c.get("loja")),
                 c.get("cliente"), c["data"], False,
                 c["situacao"] == vn.SIT_NA_ROTA)
            com_esp.add(_curto_pessoa(l["vendedor"]))
    try:
        cli_tab = ctx.tabela.get("clientes") or {}
    except Exception:                                   # noqa: BLE001
        cli_tab = {}
    fora_ = lote_fora(ctx)            # (21/10) o lote de 16/10 nao e visita
    for cod, c in cli_tab.items():
        dc = _dia(c.get("dtcad"))
        l = por_cp.get(_cod6(c.get("vend"))) if texto(c.get("vend")) else None
        if dc and de <= dc <= ate and l is not None and dc not in fora_:
            soma(l, _cod6(cod), _loja2(c.get("loja")),
                 c.get("fantasia") or c.get("nome"), dc, True)
    if not vis:
        return None
    base = {}
    for b in ctx.base.get("clientes") or []:
        base[(_cod6(b.get("cod")), _loja2(b.get("loja")))] = b
    try:
        lojas = _lojas_protheus(ctx)
    except Exception:                                   # noqa: BLE001
        lojas = {}
    # EM ABERTO: pedido digitado no mes que ainda nao virou nota
    abertos = set()
    try:
        for it in ctx.tabela["itens"]:
            dp = _dia(it.get("dt_pedido"))
            if it["tipo"] == "VEA" and dp and mes_de(dp) == mes_de(ate):
                abertos.add(it["cliente"])
    except Exception:                                   # noqa: BLE001
        abertos = set()
    blocos, n_tot = [], 0
    for v in sorted(vis, key=lambda v: (ordem_vend.index(v)
                                        if v in ordem_vend else 999, v)):
        linhas = []
        for (cod, loja), x in vis[v].items():
            b = base.get((cod, loja)) or {}
            lj = lojas.get((cod, loja)) or {}
            ct = cli_tab.get(cod) or {}
            nome = (b.get("fantasia") or b.get("nome") or x["nome"]
                    or lj.get("fantasia") or lj.get("nome")
                    or ct.get("fantasia") or ct.get("nome") or "")
            limite = b.get("limite") if b else None
            if not limite:
                limite = lj.get("limite") or ct.get("limite") or 0.0
            cond = lj.get("cond") or (ct.get("cond") if ct.get("loja", loja)
                                      == loja else "")
            try:
                prazo = _prazo_curto(ctx.cond(cond)) if cond else ""
            except Exception:                           # noqa: BLE001
                prazo = texto(cond)
            if positivou(ctx, cod, ate):
                comprou = COMPROU_SIM
            elif cod in abertos:
                comprou = COMPROU_ABERTO
            else:
                comprou = COMPROU_NAO
            ult = max(x["dias"])
            linhas.append({
                "cod": cod, "loja": loja, "cliente": texto(nome).upper(),
                "novo": x["novo"], "segmento": texto(b.get("segmento"))
                if b else "", "limite": limite or 0.0, "prazo": prazo,
                "comprou": comprou, "ult": ult, "vezes": len(x["dias"]),
                "rota": x["sit"].get(ult, ROTA_FORA),
                "na_rota": sum(1 for s_ in x["sit"].values()
                               if s_ == ROTA_NA)})
        # quem nao comprou primeiro; dentro, o maior limite
        ordem_c = {COMPROU_NAO: 0, COMPROU_ABERTO: 1, COMPROU_SIM: 2}
        linhas.sort(key=lambda r: (ordem_c[r["comprou"]], -r["limite"],
                                   r["cliente"]))
        n_c = sum(1 for r in linhas if r["comprou"] == COMPROU_SIM)
        n_novo = sum(1 for r in linhas if r["novo"])
        n_rota = sum(1 for r in linhas if r["rota"] == ROTA_NA)
        resumo = (f"{br(len(linhas))} cliente(s) · {br(n_rota)} na rota · "
                  f"{br(n_c)} comprou(aram) no mês" + (
                      f" · {br(n_novo)} cadastro(s) novo(s)"
                      if n_novo else ""))
        cel, cores = [], []
        for r in linhas:
            # o NOVO na frente do nome (nome comprido nao o corta)
            nome = f"{r['cod']}-{r['loja']} " + (
                "NOVO · " if r["novo"] else "") + r["cliente"]
            c_ = [nome, r["segmento"] or "—",
                  f"R$ {br(r['limite'])}" if r["limite"] else "—",
                  r["prazo"] or "—", r["rota"], r["comprou"]]
            if acum:
                c_.append(f"{r['ult']:%d/%m}" + (f" ({r['vezes']}x)"
                                                if r["vezes"] > 1 else ""))
            cel.append(c_)
            cores.append([None] * 4 + [
                "ok_forte" if r["rota"] == ROTA_NA else "atencao"] + [
                {"SIM": "ok_forte", "EM ABERTO": "atencao"}.get(
                    r["comprou"], "alerta")] + ([None] if acum else []))
        n_tot += len(cel)
        blocos.append({"vendedor": v, "supervisor": sups.get(v, ""),
                       "resumo": resumo, "linhas": cel, "cores": cores,
                       "dados": linhas, "n": len(linhas), "n_rota": n_rota,
                       "n_comprou": n_c})
    cols = ["CLIENTE", "SEGMENTO", "LIMITE", "PRAZO", "ROTA DO DIA",
            "COMPROU NO MÊS"] + (
        ["ÚLT. VISITA"] if acum else [])
    # quem visitou (GridRca) e nao tem o Espelho cliente a cliente
    vis_grid = {_curto_pessoa(l["vendedor"]) for l in regs
                if (l.get("visitas") or 0) - (l.get("cad_visita") or 0) > 0}
    sem = [v for v in ordem_vend if v in vis_grid and v not in com_esp]
    # (20/10, Alexandre) sem a nota de rodape das regras; fica so o aviso
    # de quem visitou e nao tem o Espelho
    rodape = ("Sem detalhe (sem Espelho baixado): " + ", ".join(sem) + "."
              if sem else "")
    # (20/10, Alexandre) AGRUPADO POR SUPERVISOR: um cabecalho por
    # supervisor (com o resumo da equipe) e os vendedores dele embaixo, na
    # ordem do resumo
    grupos, por_sup = [], {}

    def grupo_de(sup_):
        g_ = por_sup.get(sup_)
        if g_ is None:
            g_ = por_sup[sup_] = {"supervisor": sup_, "blocos": [],
                                  "sem_detalhe": []}
            grupos.append(g_)
        return g_
    for b in blocos:
        grupo_de(b["supervisor"])["blocos"].append(b)
    # quem visitou e nao tem o Espelho entra no grupo do supervisor dele
    sup_de = {}
    for l in regs:
        sup_de.setdefault(_curto_pessoa(l["vendedor"]), _curto_pessoa(
            l["supervisor"] or "(SEM SUPERVISOR)"))
    for v in sem:
        grupo_de(sup_de.get(v, "(SEM SUPERVISOR)"))["sem_detalhe"].append(v)
    pos = {sp: i for i, sp in enumerate(ordem_sup or ())}
    grupos.sort(key=lambda g: (pos.get(g["supervisor"], 999),
                               g["supervisor"]))
    for g in grupos:
        g["rodape"] = ("Sem detalhe (sem Espelho baixado): "
                       + ", ".join(g["sem_detalhe"]) + "."
                       if g["sem_detalhe"] else "")
        n_ = sum(b["n"] for b in g["blocos"])
        g["linhas"] = sum(len(b["linhas"]) for b in g["blocos"])
        g["resumo"] = (f"{br(len(g['blocos']))} vendedor(es) · {br(n_)} "
                       f"cliente(s) · "
                       f"{br(sum(b['n_rota'] for b in g['blocos']))} na rota"
                       f" · {br(sum(b['n_comprou'] for b in g['blocos']))} "
                       f"comprou(aram) no mês")
    blocos = [b for g in grupos for b in g["blocos"]]
    return {"titulo": "Clientes visitados por vendedor", "colunas": cols,
            "blocos": blocos, "grupos": grupos, "linhas": n_tot,
            "sem_detalhe": sem, "rodape": rodape}


def parcial_bap(ctx, quando="acum"):
    """
    PARCIAL BAP (07/10, grupo de vendas): a de pedidos e a de visitas numa
    imagem so - pedidos, valor dos pedidos, valor de pecas, SKU por pedido,
    visitas, % visitado dentro do agendado e positivacao. Por supervisor e
    os destaques (top 3) de cada indicador. Os numeros sao os mesmos da
    Parcial Pedidos e da Parcial Visitas e Positivacao.
    """
    pp = parcial_pedidos(ctx, quando)
    pv = parcial_visitas(ctx, quando)
    tp, tv = pp["numeros"]["total"], pv["numeros"]["total"]
    sp, sv = pp["numeros"]["sup"], pv["numeros"]["sup"]
    vp, vv = pp["numeros"]["vend"], pv["numeros"]["vend"]
    m = moeda_curta

    def tom(v):
        if v is None:
            return None
        return "ok" if v >= 80 else ("atencao" if v >= 50 else "alerta")
    vazio_p = {"ped": 0, "fat": 0.0, "pecas": 0.0, "sku": None}
    vazio_v = {"vis": 0, "pct": None, "pos": 0, "ag": 0}
    linhas, cores = [], []
    for k in sorted(set(sp) | set(sv), key=lambda k: (
            -(sp.get(k) or vazio_p)["fat"], k)):
        a_, b_ = sp.get(k) or vazio_p, sv.get(k) or vazio_v
        if not a_["ped"] and not b_["vis"] and not b_["ag"]:
            continue
        linhas.append([k, br(a_["ped"]), m(a_["fat"]), m(a_["pecas"]),
                       br(a_["sku"], 1) if a_["sku"] else "—",
                       br(b_["vis"]), br(b_["pos"]), p(b_["pct"])])
        cores.append([None] * 7 + [tom(b_["pct"])])
    total = ["TOTAL", br(tp["ped"]), m(tp["fat"]), m(tp["pecas"]),
             br(tp["sku"], 1) if tp["sku"] else "—", br(tv["vis"]),
             br(tv["pos"]), p(tv["pct"])]
    pecas_pct = pct_de(tp["pecas"], tp["fat"])

    def top(dic, campo, fmt, menor=False):
        return [(k, dic[k][campo], fmt(dic[k][campo])) for k, _ in
                _top5([(k, v[campo]) for k, v in dic.items()], menor)]
    return {
        "tipo": "Parcial BAP", "titulo": pp["titulo"], "quando": quando,
        "fonte": "fonte TABELA_BAP + GridRca Máxima",
        "cartoes": [
            ("Pedidos", br(tp["ped"]), f"{br(len(vp))} vendedores", "ok"),
            ("R$ Pedidos", m(tp["fat"]), "faturado + em aberto", "ok"),
            ("R$ Peças", m(tp["pecas"]),
             f"{p(pecas_pct)} do total" if pecas_pct is not None else "",
             "ok"),
            ("SKU por pedido", br(tp["sku"], 1) if tp["sku"] else "—",
             "itens distintos", "ok"),
            ("Visitas", br(tv["vis"]),
             f"{br(tv['vis'] - tv['na'])} fora da agenda", "ok"),
            ("% visitado na agenda", p(tv["pct"]),
             f"{br(tv['na'])} de {br(tv['ag'])} agendados",
             tom(tv["pct"]) or "ok"),
            ("Positivação", br(tv["pos"]), "clientes com pedido", "ok")],
        "faixa": None,
        "tabela": {"titulo": "Por supervisor",
                   "colunas": ["SUPERVISOR", "PED.", "R$ PEDIDOS", "R$ PEÇAS",
                               "SKU/PED.", "VISITAS", "POSIT.", "% AGENDA"],
                   "linhas": linhas, "cores": cores, "total": total},
        "nota": "",
        "rankings": [
            ("Qtd. pedidos", top(vp, "ped", br), False),
            ("R$ Pedidos", top(vp, "fat", m), False),
            ("R$ Peças", top({k: v for k, v in vp.items() if v["pecas"]},
                                "pecas", m), False),
            ("SKU por pedido", top(vp, "sku", lambda v: br(v, 1)), False),
            ("Visitas", top(vv, "vis", br), False),
            ("% visitado na agenda", top(vv, "pct", p), False),
            ("Positivação", top({k: v for k, v in vv.items() if v["pos"]},
                                "pos", br), False)],
        "fecho": "PARABÉNS AOS DESTAQUES!",
        "numeros": {"pedidos": pp["numeros"], "visitas": pv["numeros"]},
    }


MAX_LISTA_PARCIAL = 20


def parcial_entregas(ctx, quando="hoje"):
    """
    PARCIAL ENTREGAS (pos-venda, 06/10): o foco e o CLIENTE e o prazo (sem
    vendedor). Entregas pendentes (notas faturadas ainda nao entregues - o
    Farol de Entregas) e pedidos pendentes de faturamento (os Pedidos em
    aberto, SLA de PRAZO_FATURAR dias uteis, com o que segura cada um:
    credito, limite, falta de estoque). As pendencias sao as de AGORA; o
    periodo so muda a faixa das notas faturadas no periodo. Por filial e
    as duas listas, da mais urgente para a menos (no maximo 20 cada).
    """
    de, ate, rot = periodo_parcial(ctx, quando)
    h = ctx.hoje
    re_ = entregas(ctx)
    te = re_["tabelas"][0]
    ie = {c["nome"]: i for i, c in enumerate(te["colunas"])}
    ra = pedidos_em_aberto(ctx)
    ta = ra["tabelas"][0]
    ia = {c["nome"]: i for i, c in enumerate(ta["colunas"])}

    def pil(dias, fem):
        if dias is None:
            return ("pilula", "SEM PREVISÃO", "")
        if dias < 0:
            n = -dias
            return ("pilula", f"{'ATRASADA' if fem else 'ATRASADO'} {n} "
                              f"DIA{'S' if n > 1 else ''}", "alerta")
        if dias == 0:
            return ("pilula", "VENCE HOJE", "atencao")
        if dias == 1:
            return ("pilula", "VENCE AMANHÃ", "atencao")
        return ("pilula", f"NO PRAZO · {dias} DIAS", "ok")

    def cid(c, uf):
        c = texto(c).title()
        return f"{c}/{uf}" if uf else c
    ent, fat_per = [], []
    for l in te["linhas"]:
        dnf = l[ie["DT. NF"]]
        if dnf and de <= _dia(dnf) <= ate:
            fat_per.append(l)
        # (09/10) pendente = o que o Farol de Entregas chama de aberta:
        # ETAPA diferente de ENTREGUE e CANCELADA (a NF 414 estava
        # ENTREGUE em 02/10, SITUACAO "NO PRAZO", e saia como atrasada)
        if l[ie["SITUAÇÃO"]] == "CONCLUÍDA" or texto(
                l[ie["ETAPA"]]).upper() in ("ENTREGUE", "CANCELADA"):
            continue
        prev = l[ie["DT. PREVISTA"]]
        ent.append({"dias": (_dia(prev) - h).days if prev else None,
                    "prev": prev, "l": l})
    ent.sort(key=lambda x: (x["dias"] is None, x["dias"] if x["dias"]
                            is not None else 0, -(x["l"][ie["VLR NF"]] or 0)))
    ped = []
    for l in ta["linhas"]:
        fa = l[ia["FATURAR ATÉ"]]
        ped.append({"dias": (_dia(fa) - h).days if fa else None, "l": l})
    ped.sort(key=lambda x: (x["dias"] is None, x["dias"] if x["dias"]
                            is not None else 0, -(x["l"][ia["VALOR"]] or 0)))

    def atrasado(x):
        return x["dias"] is not None and x["dias"] < 0
    n_atr_e = sum(1 for x in ent if atrasado(x))
    n_vence = sum(1 for x in ent if x["dias"] in (0, 1))
    n_atr_p = sum(1 for x in ped if atrasado(x))
    v_ent = sum(x["l"][ie["VLR NF"]] or 0 for x in ent)
    v_ped = sum(x["l"][ia["VALOR"]] or 0 for x in ped)
    # ---- as listas
    le = []
    for x in ent[:MAX_LISTA_PARCIAL]:
        l = x["l"]
        le.append([pil(x["dias"], True), ("forte", texto(l[ie["CLIENTE"]])),
                   cid(l[ie["CIDADE"]], l[ie["UF"]]), texto(l[ie["NF"]]),
                   f"{l[ie['DT. NF']]:%d/%m}" if l[ie["DT. NF"]] else "—",
                   ("forte", f"{x['prev']:%d/%m}") if x["prev"] else "—",
                   texto(l[ie["LOCAL/FRETE"]]) or "—",
                   texto(l[ie["TRANSPORTADORA"]]) or "—",
                   moeda_curta(l[ie["VLR NF"]] or 0)])
    lp = []
    for x in ped[:MAX_LISTA_PARCIAL]:
        l = x["l"]
        pend = []
        cred = texto(l[ia["CRÉDITO"]])
        if cred != "OK":
            pend.append({"CLIENTE EM ATRASO": "cliente em atraso",
                         "SEM LIMITE": "sem limite"}.get(cred, cred.lower()))
        if l[ia["FALTANTES"]]:
            n_ = l[ia["FALTANTES"]]
            pend.append(f"{n_} {'itens' if n_ > 1 else 'item'} sem estoque")
        nome = texto(l[ia["CLIENTE"]])
        if " - " in nome and nome.split(" - ", 1)[0].strip().isdigit():
            nome = nome.split(" - ", 1)[1]
        dp, fa = l[ia["DATA"]], l[ia["FATURAR ATÉ"]]
        lp.append([pil(x["dias"], False), ("forte", nome),
                   cid(l[ia["CIDADE"]], l[ia["UF"]]), texto(l[ia["PEDIDO"]]),
                   f"{dp:%d/%m}" if dp else "—",
                   ("forte", f"{fa:%d/%m}") if fa else "—",
                   ("cor", " · ".join(pend), "alerta") if pend else
                   ("cor", "liberado", "ok"),
                   moeda_curta(l[ia["VALOR"]] or 0)])
    # ---- por filial
    fil = defaultdict(lambda: [0, 0, 0, 0])
    for x in ent:
        f_ = texto(x["l"][ie["FILIAL"]]) or "?"
        fil[f_][0] += 1
        fil[f_][1] += atrasado(x)
    for x in ped:
        f_ = texto(x["l"][ia["FILIAL"]]) or "?"
        fil[f_][2] += 1
        fil[f_][3] += atrasado(x)
    chips = []
    for k, v in sorted(fil.items(), key=lambda kv: (-(kv[1][1] + kv[1][3]),
                                                    -(kv[1][0] + kv[1][2]),
                                                    kv[0]))[:6]:
        l1 = [("entregas", ""), (br(v[0]), "forte")] + \
            ([("·", ""), (f"{br(v[1])} atras.", "alerta")] if v[1] else [])
        l2 = [("a faturar", ""), (br(v[2]), "forte")] + \
            ([("·", ""), (f"{br(v[3])} fora SLA", "alerta")] if v[3] else [])
        chips.append((k.upper(), l1, l2))
    entregues = sum(1 for l in fat_per if l[ie["ETAPA"]] == "ENTREGUE"
                    or l[ie["SITUAÇÃO"]] == "CONCLUÍDA")
    return {
        "tipo": "Parcial Entregas", "titulo": rot, "quando": quando,
        "fonte": "fonte ACOMPANHAMENTO_POS_VENDA + TABELA_BAP",
        "cartoes": [
            ("Entregas pendentes", br(len(ent)),
             f"{moeda_curta(v_ent)} em notas", "ok"),
            ("Entregas atrasadas", br(n_atr_e), "passaram da data prevista",
             "alerta" if n_atr_e else "ok"),
            ("Vencem hoje/amanhã", br(n_vence), "prioridade de rota",
             "atencao" if n_vence else "ok"),
            ("Pedidos a faturar", br(len(ped)),
             f"{moeda_curta(v_ped)} em aberto", "ok"),
            ("Fora do SLA faturar", br(n_atr_p),
             f"mais de {bd.PRAZO_FATURAR} dias úteis",
             "alerta" if n_atr_p else "ok")],
        "faixa": [("No período", "titulo"),
                  (f"{br(len(fat_per))} nota{'s' if len(fat_per) != 1 else ''}"
                   f" faturada{'s' if len(fat_per) != 1 else ''} · "
                   f"{moeda_curta(sum(l[ie['VLR NF']] or 0 for l in fat_per))}",
                   ""),
                  (f"{br(entregues)} já entregues", "ok"),
                  (ctx.texto_sla(), "suave")],
        "chips": chips,
        "listas": [
            {"titulo": "Entregas pendentes",
             "sub": "notas faturadas ainda não entregues · da mais urgente",
             "colunas": [("SITUAÇÃO", "l", False), ("CLIENTE", "l", True),
                         ("CIDADE/UF", "l", True), ("NF", "r", False),
                         ("FATURADA", "r", False), ("PREVISTA", "r", False),
                         ("ENTREGA", "l", False), ("TRANSP.", "l", True),
                         ("VALOR", "r", False)],
             "linhas": le, "vazio": "Nenhuma entrega pendente.",
             "rodape": (f"e mais {len(ent) - MAX_LISTA_PARCIAL} entrega(s) "
                        f"(na contagem dos cartões)")
             if len(ent) > MAX_LISTA_PARCIAL else ""},
            {"titulo": "Pedidos pendentes de faturamento",
             "sub": f"SLA: faturar em até {bd.PRAZO_FATURAR} dias úteis",
             "colunas": [("SITUAÇÃO", "l", False), ("CLIENTE", "l", True),
                         ("CIDADE/UF", "l", True), ("PEDIDO", "r", False),
                         ("DATA", "r", False), ("FATURAR ATÉ", "r", False),
                         ("PENDÊNCIA", "l", True), ("VALOR", "r", False)],
             "linhas": lp, "vazio": "Nenhum pedido em aberto.",
             "rodape": (f"e mais {len(ped) - MAX_LISTA_PARCIAL} pedido(s) "
                        f"(na contagem dos cartões)")
             if len(ped) > MAX_LISTA_PARCIAL else ""}],
        "tabela": None, "rankings": None, "nota": "",
        "numeros": {"entregas": len(ent), "atrasadas": n_atr_e,
                    "pedidos": len(ped), "fora_sla": n_atr_p},
    }


def moeda_curta(v):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e6:
        return f"R$ {br(v / 1e6, 1)} mi"
    if a >= 1e3:
        return f"R$ {br(v / 1e3, 1)} mil"
    return f"R$ {br(v)}"


def pct1(v):
    return "—" if v is None else f"{br(v, 1)}%"


# =========================================================================
# (07/10) DIVERGENCIAS CLIENTES PLANNER x PROTHEUS - o vendedor de cada
# cliente no Planner (a carteira que vai para a Maxima) contra o A1_VEND do
# cadastro do Protheus. O certo e o PLANNER: o relatorio diz o que corrigir
# no Protheus e exporta a lista (Excel) e o .json da base de clientes.
# =========================================================================
SIT_DIFERENTE = "VENDEDOR DIFERENTE"
SIT_SEM_PROTHEUS = "SEM VENDEDOR NO PROTHEUS"
SIT_SEM_PLANNER = "SEM VENDEDOR NO PLANNER"
SIT_FORA_BASE = "FORA DA BASE DO PLANNER"
SIT_DUPLICADO = "CÓDIGO DUPLICADO NA BASE"
SIT_CORRIGIR = (SIT_DIFERENTE, SIT_SEM_PROTHEUS)


def _loja2(v) -> str:
    return re.sub(r"\D", "", texto(v)).zfill(2) if texto(v) else "01"


def divergencias_de_clientes(ctx) -> list:
    """[{cod, loja, nome, cidade, uf, segmento, zona, vend_planner,
    vend_protheus, status_protheus, situacao, acao, filial}] - so quem
    nao bate."""
    lojas = _lojas_protheus(ctx)
    pes = _vendedores_do_planner(ctx)
    do_planner = {v for v, x in pes.items() if x.get("cargo") != "SUPERVISOR"}
    base, grupos = {}, defaultdict(list)
    for c in ctx.base.get("clientes") or []:
        k = (texto(c["cod"]).zfill(6), _loja2(c.get("loja")))
        base[k] = c
        grupos[k].append(c)
    saida = []
    # (07/10) o mesmo codigo+loja em mais de um cliente da BASE_CLIENTE
    # (loja "1" e "01"): erro de cadastro - cada um aparece, e o vendedor
    # nao e comparado (nao da para saber qual e qual no Protheus)
    dup = {k for k, cs in grupos.items() if len(cs) > 1}
    for k in sorted(dup):
        x = lojas.get(k) or {}
        lojas_txt = " e ".join(f'"{texto(c.get("loja"))}"' for c in grupos[k])
        for c in grupos[k]:
            saida.append({
                "cod": k[0], "loja": texto(c.get("loja")),
                "nome": c.get("fantasia") or c.get("nome"),
                "cidade": c.get("cidade"), "uf": c.get("uf"),
                "segmento": c.get("segmento"), "zona": c.get("zona"),
                "vend_planner": _vend6(c.get("vend")),
                "vend_protheus": _vend6(x.get("vend")),
                "status_protheus": x.get("status") or "",
                "situacao": SIT_DUPLICADO,
                "acao": (f"Código {k[0]} em {len(grupos[k])} clientes "
                         f"diferentes (lojas {lojas_txt}): corrigir a loja "
                         f"no cadastro do Protheus/BASE_CLIENTE"),
                "filial": x.get("filial", "")})
    v_padrao = vendedor_padrao_de(ctx)
    for k, c in base.items():
        if k in dup:
            continue
        vp, x = _vend6(c.get("vend")), lojas.get(k) or {}
        vr = _vend6(x.get("vend"))
        if vp == vr:
            continue
        if not vp and vr == v_padrao:
            continue          # (15/10) fora do Planner e ja no PADRAO: ok
        if vp:
            sit = SIT_DIFERENTE if vr else SIT_SEM_PROTHEUS
            acao = f"Trocar o A1_VEND no Protheus para {vp}"
        else:
            sit = SIT_SEM_PLANNER
            acao = ("Fora do Planner (zona/segmento sem vendedor): vai no "
                    f".json ATIVO com o vendedor padrão {v_padrao} - ou "
                    "definir o vendedor no Planner")
        saida.append({
            "cod": k[0], "loja": k[1],
            "nome": c.get("fantasia") or c.get("nome") or x.get("fantasia"),
            "cidade": c.get("cidade"), "uf": c.get("uf"),
            "segmento": c.get("segmento"), "zona": c.get("zona"),
            "vend_planner": vp, "vend_protheus": vr,
            "status_protheus": x.get("status") or "",
            "situacao": sit, "acao": acao, "filial": x.get("filial", "")})
    for k, x in lojas.items():
        vr = _vend6(x.get("vend"))
        if k in base or vr not in do_planner:
            continue
        saida.append({
            "cod": k[0], "loja": k[1],
            "nome": x.get("fantasia") or x.get("nome"),
            "cidade": x.get("cidade"), "uf": x.get("uf"), "segmento": "",
            "zona": "", "vend_planner": "", "vend_protheus": vr,
            "status_protheus": x.get("status") or "", "situacao": SIT_FORA_BASE,
            "acao": ("Excluído da BASE_CLIENTE (segmento fora): vai no "
                     f".json ATIVO com o vendedor padrão {v_padrao} - ou "
                     "rever o segmento"),
            "filial": x.get("filial", "")})
    ordem = {SIT_DIFERENTE: 0, SIT_SEM_PROTHEUS: 1, SIT_DUPLICADO: 2,
             SIT_SEM_PLANNER: 3, SIT_FORA_BASE: 4}
    saida.sort(key=lambda d: (ordem[d["situacao"]], d["vend_planner"]
                              or d["vend_protheus"], d["cod"], d["loja"]))
    return saida


def nu_status_json() -> str:
    """(20/10) O STATUS do .json da base de clientes: sempre ATIVO."""
    try:
        import planner_nucleo as nu                     # noqa: PLC0415
        return nu.status_no_json()
    except Exception:                                   # noqa: BLE001
        return "ATIVO"


def divergencias_clientes(ctx):
    r = novo("an_divergencias", ANA, "Divergências clientes Planner x Protheus",
             "Vendedor do cliente: Planner x A1_VEND do Protheus",
             "Planner (BASE_CLIENTE) + TABELA_BAP › dClientesBap")
    lojas = _lojas_protheus(ctx)
    if not lojas:
        r["avisos"].append("A TABELA_BAP não trouxe a dClientesBap com o "
                           "A1_VEND: rode o BAP Tools e clique em Atualizar.")
        return r
    pes = _vendedores_do_planner(ctx)

    def nome_v(v):
        if not v:
            return "(vazio)"
        return f"{v} - {pes[v]['nome']}" if v in pes else v
    divs = divergencias_de_clientes(ctx)
    clientes = ctx.base.get("clientes") or []
    n_base = len(clientes)
    cont = Counter(d["situacao"] for d in divs)
    # cada linha da divergencia (menos fora da base) e um cliente da base
    so_base = sum(1 for d in divs if d["situacao"] != SIT_FORA_BASE)
    r["kpis"] = [
        kpi("Clientes na base (Planner)", br(n_base), "neutro"),
        kpi("Batem", br(n_base - so_base), "ok", p(pct_de(n_base - so_base,
                                                          n_base))),
        kpi("Vendedor diferente", br(cont[SIT_DIFERENTE]
                                     + cont[SIT_SEM_PROTHEUS]),
            "alerta" if cont[SIT_DIFERENTE] + cont[SIT_SEM_PROTHEUS] else "ok",
            "corrigir o A1_VEND no Protheus"),
        kpi("Sem vendedor no Planner", br(cont[SIT_SEM_PLANNER]),
            "atencao" if cont[SIT_SEM_PLANNER] else "ok",
            "sem vendedor · .json: ATIVO, vendedor padrão"),
        kpi("Fora da base do Planner", br(cont[SIT_FORA_BASE]), "info",
            "A1_VEND do Planner · .json: ATIVO, vendedor padrão"),
        kpi("Código duplicado", br(cont[SIT_DUPLICADO]),
            "alerta" if cont[SIT_DUPLICADO] else "ok",
            "mesmo código+loja em clientes diferentes"),
    ]
    # ---- por vendedor (a conciliacao da carteira)
    vend_planner = Counter(_vend6(c.get("vend")) for c in clientes
                           if c.get("vend"))
    base_k = {(texto(c["cod"]).zfill(6), _loja2(c.get("loja"))):
              _vend6(c.get("vend")) for c in clientes}
    linhas_v = []
    for v in sorted(vend_planner, key=lambda v: -vend_planner[v]):
        P = {k for k, x in base_k.items() if x == v}
        R = {k for k, x in lojas.items() if _vend6(x.get("vend")) == v}
        # a CARTEIRA conta cliente a cliente (como o Farol de Clientes): o
        # mesmo codigo+loja pode aparecer duas vezes na base ("1" e "01")
        linhas_v.append([nome_v(v), _sup_nome(ctx, v) or "(SEM SUPERVISOR)",
                         vend_planner[v], len(R), len(P & R),
                         vend_planner[v] - len(P & R), len(R - P),
                         sum(1 for k in R - P if k not in base_k),
                         sum(1 for k in R - P if k in base_k and
                             not base_k[k]),
                         "SIM" if P == R and vend_planner[v] == len(P)
                         else "NÃO"])
    cols_v = [col("VENDEDOR", "texto", 250), col("SUPERVISOR", "texto", 200),
              col("CARTEIRA PLANNER", "int", 110),
              col("BASE PROTHEUS", "int", 105), col("IGUAIS", "int", 70),
              col("SÓ NO PLANNER", "int", 100), col("SÓ NO PROTHEUS", "int", 105),
              col("· FORA DA BASE", "int", 100),
              col("· PLANNER SEM VENDEDOR", "int", 145),
              col("BATE?", "texto", 60)]
    soma = [sum(l[j] for l in linhas_v) for j in range(2, 9)]
    r["tabelas"].append(tabela(
        "Por vendedor", cols_v, linhas_v,
        ["ok" if l[-1] == "SIM" else "atencao" for l in linhas_v],
        filtros=("SUPERVISOR", "BATE?"),
        total=["TOTAL", ""] + soma + [""]))
    # ---- cliente a cliente
    cols_c = [col("COD", "texto", 70), col("LOJA", "texto", 45),
              col("CLIENTE", "texto", 230), col("CIDADE", "texto", 140),
              col("UF", "texto", 40), col("SEGMENTO", "texto", 120),
              col("ZONA", "texto", 70),
              col("VENDEDOR PLANNER", "texto", 230),
              col("VENDEDOR PROTHEUS (A1_VEND)", "texto", 230),
              col("STATUS PROTHEUS", "texto", 100),
              col("SITUAÇÃO", "texto", 190), col("O QUE FAZER", "texto", 380)]
    linhas_c = [[d["cod"], d["loja"], d["nome"], d["cidade"], d["uf"],
                 d["segmento"], d["zona"],
                 nome_v(d["vend_planner"]) if d["vend_planner"]
                 else "(SEM VENDEDOR)", nome_v(d["vend_protheus"]),
                 d["status_protheus"], d["situacao"], d["acao"]] for d in divs]
    tons = {SIT_DIFERENTE: "alerta", SIT_SEM_PROTHEUS: "alerta",
            SIT_DUPLICADO: "alerta", SIT_SEM_PLANNER: "atencao",
            SIT_FORA_BASE: ""}
    r["tabelas"].append(tabela(
        "Clientes divergentes", cols_c, linhas_c,
        [tons[d["situacao"]] for d in divs],
        filtros=("SITUAÇÃO", "VENDEDOR PLANNER",
                 "VENDEDOR PROTHEUS (A1_VEND)", "UF", "STATUS PROTHEUS"),
        recortes=[("Corrigir no Protheus",
                   lambda l: l[10] in SIT_CORRIGIR)]))
    # (28/10, Alexandre) a relacao de clientes sem coordenada/endereco,
    # para a analista preencher a mao
    sem = clientes_sem_coordenada(ctx)
    n_rota = sum(1 for d in sem if d.get("na_rota"))
    r["kpis"].append(kpi(
        "Sem coordenada / endereço", br(len(sem)),
        "atencao" if sem else "ok", f"{br(n_rota)} na rota do mês"))
    r["tabelas"].append(_tabela_sem_coordenada(ctx, sem))
    r["exportar_sem_coordenada"] = lambda destino, chaves=None: \
        gravar_sem_coordenada(ctx, destino, chaves)
    r["importar_preenchidos"] = lambda arquivo: \
        importar_preenchidos(ctx, arquivo)
    r["exportar_correcao"] = lambda destino, chaves=None: \
        gravar_correcao(ctx, destino, chaves)
    r["exportar_correcao_json"] = lambda chaves=None: \
        correcao_json(ctx, chaves)
    r["correcao_linhas"] = lambda chaves=None: correcao_linhas(ctx, chaves)
    return r


def _para_corrigir(ctx, chaves=None) -> list:
    return [d for d in divergencias_de_clientes(ctx)
            if chaves is None or (d["cod"], d["loja"]) in chaves]


def codigo_do_cliente(texto_cliente) -> str:
    """RN-GER-011: de "001234-01 - NOME" devolve "001234-01" (codigo e
    loja). Sem o codigo no comeco, "". Nunca devolve o nome."""
    # formato do Protheus: A1_COD 6 digitos + loja opcional de 2; CPF/CNPJ
    # so com digitos (11/14) nao casa e devolve ""
    m = re.match(r"\s*(\d{6}(?:-\d{2})?)(?=\s|$|-)",
                 "" if texto_cliente is None else str(texto_cliente))
    return m.group(1) if m else ""


# RD-0002: os cabecalhos do Excel de correcao, em um lugar so (o
# gravar_correcao e o robo usam estes). Com a coluna CLIENTE; o
# correcao_linhas (RN-GER-011) devolve as linhas sem ela.
CAB_CORRIGIR = ("A1_FILIAL", "A1_COD", "A1_LOJA", "CLIENTE", "CIDADE", "UF",
                "A1_VEND ATUAL", "A1_VEND CORRETO", "VENDEDOR CORRETO",
                "SUPERVISOR", "STATUS PROTHEUS")
CAB_ANALISAR = ("A1_FILIAL", "A1_COD", "A1_LOJA", "CLIENTE", "CIDADE", "UF",
                "VENDEDOR NO PLANNER", "A1_VEND ATUAL", "SITUAÇÃO",
                "O QUE FAZER")


def correcao_linhas(ctx, chaves=None) -> dict:
    """As linhas do Excel de correcao, sem a coluna CLIENTE (RN-GER-011):
    corrigir = CORRIGIR NO PROTHEUS (10 colunas); analisar = ANALISAR (9).
    Funcao pura; o gravar_correcao usa as mesmas linhas (com o nome)."""
    return _correcao_linhas(ctx, chaves, com_nome=False)


def _correcao_linhas(ctx, chaves, com_nome) -> dict:
    pes = _vendedores_do_planner(ctx)
    corrigir, analisar = [], []
    for d in _para_corrigir(ctx, chaves):
        nome = [d["nome"]] if com_nome else []
        if d["situacao"] in SIT_CORRIGIR:
            v = d["vend_planner"]
            corrigir.append([d["filial"], d["cod"], d["loja"], *nome,
                             d["cidade"], d["uf"], d["vend_protheus"], v,
                             (pes.get(v) or {}).get("nome", ""),
                             _sup_nome(ctx, v), d["status_protheus"]])
        else:
            analisar.append([d["filial"], d["cod"], d["loja"], *nome,
                             d["cidade"], d["uf"], d["vend_planner"] or "",
                             d["vend_protheus"], d["situacao"], d["acao"]])
    return {"corrigir": corrigir, "analisar": analisar}


def gravar_correcao(ctx, destino, chaves=None):
    """O Excel para corrigir o Protheus: CORRIGIR NO PROTHEUS (A1_VEND
    atual -> o do Planner) e ANALISAR (o que nao se resolve trocando o
    A1_VEND). chaves: {(cod, loja)} - so o que estava na tela."""
    from openpyxl import Workbook                       # noqa: PLC0415
    from openpyxl.styles import Font, PatternFill       # noqa: PLC0415
    wb = Workbook()
    ws = wb.active
    ws.title = "CORRIGIR NO PROTHEUS"
    an = wb.create_sheet("ANALISAR")
    for w, cab in ((ws, CAB_CORRIGIR), (an, CAB_ANALISAR)):
        for j, x in enumerate(cab, 1):
            c = w.cell(1, j, x)
            c.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
            c.fill = PatternFill("solid", fgColor="2F7D32")
        w.freeze_panes = "A2"
    lin = _correcao_linhas(ctx, chaves, com_nome=True)
    for linha in lin["corrigir"]:
        ws.append(linha)
    for linha in lin["analisar"]:
        an.append(linha)
    n1, n2 = len(lin["corrigir"]), len(lin["analisar"])
    for w, larg in ((ws, (11, 9, 7, 36, 22, 5, 14, 16, 34, 30, 15)),
                    (an, (11, 9, 7, 36, 22, 5, 18, 14, 26, 90))):
        for j, x in enumerate(larg, 1):
            w.column_dimensions[w.cell(1, j).column_letter].width = x
        for row in w.iter_rows(min_row=2):
            for c in row:
                c.font = Font(name="Arial", size=10)
        if w.max_row > 1:
            w.auto_filter.ref = w.dimensions
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino, n1, n2


def correcao_json(ctx, chaves=None) -> list:
    """O .json da BASE DE CLIENTES do Protheus (o mesmo do Farol
    Roteirizacao) so com os clientes a corrigir: A1_VEND = o do Planner.
    (15/10, Alexandre) Tambem quem NAO esta carteirizado: SEM VENDEDOR NO
    PLANNER (com o vendedor padrao, pela base) e FORA DA BASE DO PLANNER
    (o cadastro do Protheus, com o vendedor padrao). (20/10) Todos ATIVO."""
    divs = _para_corrigir(ctx, chaves)
    alvo = {(d["cod"], d["loja"]) for d in divs
            if d["situacao"] in SIT_CORRIGIR + (SIT_SEM_PLANNER,)}
    saida = [x for x in _exportar_base_protheus(ctx)()
             if (x["A1_COD"], x["A1_LOJA"]) in alvo]
    v_padrao = vendedor_padrao_de(ctx)
    s_padrao = vendedor_padrao_de(ctx, "supervisor_padrao")
    lojas = _lojas_protheus(ctx)
    for d in divs:
        if d["situacao"] != SIT_FORA_BASE:
            continue
        x = lojas.get((d["cod"], d["loja"])) or {}
        saida.append({
            "A1_FILIAL": d.get("filial") or x.get("filial", ""),
            "A1_COD": d["cod"], "A1_LOJA": d["loja"], "A1_VEND": v_padrao,
            "A1_NOME": x.get("nome", ""), "A1_NREDUZ": x.get("fantasia", ""),
            "SUPERVISOR": s_padrao, "STATUS": nu_status_json(),
            "LATITUDE": "", "LONGITUDE": ""})
    saida.sort(key=lambda x: (x["A1_VEND"], x["A1_COD"], x["A1_LOJA"]))
    return saida


# =========================================================================
# CLIENTES SEM COORDENADA / ENDERECO (28/10, Alexandre, via BAP Ajuda):
# "quero uma relacao de clientes sem coordenada/endereco, para
# preenchimento manual da minha analista". Entra todo cliente da base do
# Planner (sem os CNPJs internos) com pelo menos um problema:
#   SEM COORDENADA      - sem LATITUDE/LONGITUDE depois do
#                         COORDENADAS_CLIENTES.json (o ponto aproximado do
#                         geografia.aproximar_pontos NAO conta);
#   COORDENADA RECUSADA - o ponto cai a mais de 60 km do centro da cidade
#                         (a regra do geocodificar.py);
#   SEM ENDERECO / SEM NUMERO (vazio, "0", "S/N" e sem numero no
#                         endereco) / SEM BAIRRO / SEM CIDADE.
# O Excel "para preencher" volta pelo "Importar preenchidos": o ponto vai
# para o COORDENADAS_CLIENTES.json com "origem": "MANUAL". O endereco
# certo NAO volta para lugar nenhum: e corrigido no Protheus.
# =========================================================================
F_SEM_COORD = "SEM COORDENADA"
F_RECUSADA = "COORDENADA RECUSADA"
F_SEM_END = "SEM ENDEREÇO"
F_SEM_NUM = "SEM NÚMERO"
F_SEM_BAIRRO = "SEM BAIRRO"
F_SEM_CIDADE = "SEM CIDADE"
F_ENDERECO = (F_SEM_END, F_SEM_NUM, F_SEM_BAIRRO, F_SEM_CIDADE)
# (28/10, Alexandre - regra 2 das coordenadas, recado do analista
# 20261028-1020) o ponto que existe mas nao e o da porta: so da rua (o OSM
# nao tem o numero), so do bairro, ou o OSM achou a rua em OUTRO bairro
# (geocodificar "alerta"). O ponto MANUAL nunca entra aqui.
F_PONTO_RUA = "PONTO SÓ DA RUA"
F_PONTO_BAIRRO = "PONTO SÓ DO BAIRRO"
F_BAIRRO_DIF = "BAIRRO DIFERENTE"
F_IMPRECISO = (F_PONTO_RUA, F_PONTO_BAIRRO, F_BAIRRO_DIF)
RAIO_CIDADE_KM = 60.0
SEP_FALTA = "; "             # o filtro "multi" da tela separa por "; "
ORDEM_CURVA = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "Z": 5}
ABA_SEM_COORD = "Sem coordenada / endereço"
ORIGEM_MANUAL = "MANUAL"


def _tem_numero(numero, endereco) -> bool:
    """O numero da porta: no campo NUMERO ("0" e "S/N" nao valem) ou
    dentro do endereco ("RUA X, 39A", "R SOBRAL N253"); "S/N" no endereco
    = sem numero. (28/10) a mesma regra do geocodificar (separar_numero:
    "RUA 10", "BR 010" e "KM 5" nao sao numero da porta)."""
    try:
        import geocodificar as gc                       # noqa: PLC0415
        return bool(gc.separar_numero(endereco, numero)[1])
    except (ImportError, AttributeError):
        pass
    n = texto(numero).upper()
    if re.search(r"[1-9]", n):
        return True
    e = sem_acento(texto(endereco)).upper()
    if re.search(r"\bS\s*/?\s*N\b", e):
        return False
    return bool(re.search(r"[1-9]", e))


def _coordenadas_do_arquivo(ctx) -> dict:
    """{chave: entrada} do COORDENADAS_CLIENTES.json (precisao e origem)."""
    try:
        import geocodificar as gc                       # noqa: PLC0415
        return gc.ler(gc.caminho(ctx.raiz))
    except Exception:                                   # noqa: BLE001
        return {}


def _ponto_do_arquivo(g) -> str:
    """O tipo de ponto da tela: MANUAL, GOOGLE, ENDEREÇO, RUA, BAIRRO ou
    "". (28/10) GOOGLE = veio da API do Google (geocodificar --google): os
    avisos de ponto impreciso continuam valendo pela precisao."""
    if not g:
        return ""
    if texto(g.get("origem")).upper() in ("GOOGLE", "TOMTOM"):  # (29/10)
        return texto(g.get("origem")).upper()
    if texto(g.get("origem")).upper() == ORIGEM_MANUAL or g.get("fonte"):
        return ORIGEM_MANUAL
    return {"endereco": "ENDEREÇO", "cep": "CEP", "rua": "RUA",
            "bairro": "BAIRRO"}.get(
        texto(g.get("precisao")).lower(), texto(g.get("precisao")).upper())


def _link_busca_maps(c) -> str:
    """Busca no Google Maps pelo nome + endereco escrito (para a analista
    achar o ponto)."""
    from urllib.parse import quote                      # noqa: PLC0415
    end_ = " ".join(x for x in (texto(c.get("endereco")),
                                texto(c.get("numero"))) if x)
    q = ", ".join(x for x in (texto(c.get("fantasia")) or texto(
        c.get("nome")), end_, texto(c.get("bairro")), texto(c.get("cidade")),
        texto(c.get("uf"))) if x.strip())
    return ("https://www.google.com/maps/search/?api=1&query="
            + quote(q, safe="")) if q else ""


def clientes_sem_coordenada(ctx) -> list:
    """[{cliente da base + falta: [..], ponto, dist_km}] - quem tem algum
    problema de coordenada ou de endereco. Ordem: na rota do mes, curva
    (S, A, B, C, Z), cidade, bairro."""
    import geografia as geo                             # noqa: PLC0415
    arq = _coordenadas_do_arquivo(ctx)
    saida = []
    for c in ctx.base.get("clientes") or []:
        if c.get("interno"):
            continue
        falta, dist = [], None
        la, lo = geo._num(c.get("lat")), geo._num(c.get("lon"))  # noqa: SLF001
        if not geo.ponto_valido(la, lo):
            falta.append(F_SEM_COORD)
        else:
            centro = geo.coordenada(c.get("uf"), c.get("cidade"))
            if centro:
                dist = geo.distancia_km(centro, (la, lo))
                if dist > RAIO_CIDADE_KM:
                    falta.append(F_RECUSADA)
        g = arq.get(texto(c.get("chave")))
        if F_SEM_COORD not in falta and F_RECUSADA not in falta and g \
                and _ponto_do_arquivo(g) != ORIGEM_MANUAL:
            # (28/10) regra 2: o ponto existe, mas nao e o da porta
            prec_ = texto(g.get("precisao")).lower()
            if texto(g.get("alerta")).upper() == F_BAIRRO_DIF:
                falta.append(F_BAIRRO_DIF)
            if prec_ == "rua":
                falta.append(F_PONTO_RUA)
            elif prec_ == "bairro":
                falta.append(F_PONTO_BAIRRO)
        if not texto(c.get("endereco")):
            falta.append(F_SEM_END)
        elif not _tem_numero(c.get("numero"), c.get("endereco")):
            falta.append(F_SEM_NUM)
        if texto(c.get("bairro")) in ("", "(SEM BAIRRO)"):
            falta.append(F_SEM_BAIRRO)
        if not texto(c.get("cidade")):
            falta.append(F_SEM_CIDADE)
        if not falta:
            continue
        saida.append(dict(c, falta=falta, dist_km=dist,
                          ponto=_ponto_do_arquivo(g) if F_SEM_COORD
                          not in falta else ""))
    saida.sort(key=lambda d: (
        not d.get("na_rota"),
        ORDEM_CURVA.get(texto(d.get("curva")).upper()[:1], 9),
        texto(d.get("uf")), texto(d.get("cidade")), texto(d.get("bairro")),
        texto(d.get("cod")), texto(d.get("loja"))))
    return saida


def _vend_planner_txt(c) -> str:
    v = texto(c.get("vend"))
    if not v:
        return "(SEM VENDEDOR)"
    nome = texto(c.get("vend_nome"))
    return f"{v} - {nome}" if nome and nome != v else v


def _tabela_sem_coordenada(ctx, lista):
    # O QUE FALTA e NA ROTA logo depois do nome (na tela cabem sem rolar)
    cols = [col("CÓD.", "texto", 65), col("LOJA", "texto", 42),
            col("RAZÃO SOCIAL", "texto", 210),
            col("NOME FANTASIA", "texto", 170),
            col("O QUE FALTA", "texto", 300),
            col("NA ROTA DO MÊS", "texto", 80),
            col("UF", "texto", 38), col("CIDADE", "texto", 130),
            col("BAIRRO", "texto", 130), col("ENDEREÇO", "texto", 230),
            col("Nº", "texto", 50), col("CONTATO (TELEFONE)", "texto", 170),
            col("VENDEDOR PLANNER", "texto", 190),
            col("SUPERVISOR PLANNER", "texto", 150),
            col("SEGMENTO", "texto", 140), col("CURVA", "texto", 50),
            col("SITUAÇÃO", "texto", 110), col("PONTO", "texto", 75)]
    i_falta, i_rota = 4, 5
    linhas, tons = [], []
    for d in lista:
        linhas.append([
            d["cod"], d.get("loja") or "", d.get("nome") or "",
            d.get("fantasia") or "", SEP_FALTA.join(d["falta"]),
            "SIM" if d.get("na_rota") else "NÃO",
            d.get("uf") or "", d.get("cidade") or "", d.get("bairro") or "",
            d.get("endereco") or "", d.get("numero") or "",
            d.get("contato") or "", _vend_planner_txt(d),
            d.get("supervisor") or "(SEM SUPERVISOR)",
            d.get("segmento") or "", d.get("curva") or "",
            d.get("status") or "", d.get("ponto") or ""])
        sem_ponto = F_SEM_COORD in d["falta"] or F_RECUSADA in d["falta"]
        tons.append("alerta" if d.get("na_rota") and sem_ponto else
                    "atencao" if d.get("na_rota") else "")

    def tem(l, *itens):
        return any(x in l[i_falta].split(SEP_FALTA) for x in itens)

    def rota(l):
        return l[i_rota] == "SIM"

    def cartoes(ls):
        n_rota = sum(1 for l in ls if rota(l))
        coord = [l for l in ls if tem(l, F_SEM_COORD, F_RECUSADA)]
        n_end = sum(1 for l in ls if tem(l, *F_ENDERECO))
        imp = [l for l in ls if tem(l, *F_IMPRECISO)]
        return [
            kpi("Clientes para preencher", br(len(ls)),
                "atencao" if ls else "ok", f"{br(n_rota)} na rota do mês"),
            kpi("Sem coordenada", br(len(coord)),
                "alerta" if coord else "ok",
                f"{br(sum(1 for l in coord if rota(l)))} na rota do mês"),
            kpi("Ponto impreciso", br(len(imp)), "atencao" if imp else "ok",
                f"só da rua, só do bairro ou bairro diferente · "
                f"{br(sum(1 for l in imp if tem(l, F_BAIRRO_DIF)))} bairro "
                f"diferente"),
            kpi("Endereço incompleto", br(n_end), "atencao" if n_end else "ok",
                "sem endereço, número, bairro ou cidade"),
            kpi("Na rota do mês", br(n_rota), "alerta" if n_rota else "ok",
                "começar por estes"),
        ]
    return tabela(
        ABA_SEM_COORD, cols, linhas, tons,
        filtros=("UF", "CIDADE", "VENDEDOR PLANNER",
                 {"coluna": "O QUE FALTA", "multi": True},
                 "NA ROTA DO MÊS", "CURVA"),
        kpis_de=cartoes,
        recortes=[("Só sem coordenada",
                   lambda l: tem(l, F_SEM_COORD, F_RECUSADA)),
                  ("Só ponto impreciso",
                   lambda l: tem(l, *F_IMPRECISO)),
                  ("Só bairro diferente",
                   lambda l: tem(l, F_BAIRRO_DIF)),
                  ("Só sem endereço / incompleto",
                   lambda l: tem(l, *F_ENDERECO)),
                  ("Na rota do mês", rota)])


def gravar_sem_coordenada(ctx, destino, chaves=None):
    """O Excel para a analista preencher: as colunas da aba (protegidas)
    e as AMARELAS em branco. chaves: {(cod, loja)} - so o que esta na
    tela. Devolve (destino, n)."""
    from openpyxl import Workbook                       # noqa: PLC0415
    from openpyxl.styles import (Alignment, Border,     # noqa: PLC0415
                                 Font, PatternFill, Protection, Side)
    lista = [d for d in clientes_sem_coordenada(ctx)
             if chaves is None or (d["cod"], d.get("loja") or "") in chaves]
    wb = Workbook()
    ws = wb.active
    ws.title = "PREENCHER"
    base_cab = [("CÓD.", 9), ("LOJA", 6), ("RAZÃO SOCIAL", 34),
                ("NOME FANTASIA", 26), ("O QUE FALTA", 30),
                ("NA ROTA DO MÊS", 10), ("UF", 5), ("CIDADE", 20),
                ("BAIRRO", 20), ("ENDEREÇO", 36), ("Nº", 7),
                ("CONTATO (TELEFONE)", 24), ("VENDEDOR PLANNER", 26),
                ("SUPERVISOR PLANNER", 20), ("SEGMENTO", 20), ("CURVA", 7),
                ("SITUAÇÃO", 14), ("BUSCAR NO MAPS", 11)]
    amarelas = [("ENDEREÇO CORRETO", 36), ("Nº CORRETO", 9),
                ("BAIRRO CORRETO", 22), ("CEP", 11), ("LATITUDE", 13),
                ("LONGITUDE", 13), ("LINK GOOGLE MAPS", 30),
                ("OBSERVAÇÃO", 30), ("PREENCHIDO POR", 18), ("DATA", 11)]
    oculta = [("CHAVE", 12)]
    todas = base_cab + amarelas + oculta
    f_cab = PatternFill("solid", fgColor="2F7D32")
    f_cab_am = PatternFill("solid", fgColor="BF9000")
    f_am = PatternFill("solid", fgColor="FFF2CC")
    f_rota = PatternFill("solid", fgColor="FDE9E7")
    fino = Side(style="thin", color="D9D9D9")
    borda = Border(left=fino, right=fino, top=fino, bottom=fino)
    n_base = len(base_cab)
    for j, (nome, larg) in enumerate(todas, 1):
        c = ws.cell(1, j, nome)
        c.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
        c.fill = f_cab_am if n_base < j <= n_base + len(amarelas) else f_cab
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.protection = Protection(locked=True)
        ws.column_dimensions[c.column_letter].width = larg
    ws.row_dimensions[1].height = 30
    for i, d in enumerate(lista, 2):
        link = _link_busca_maps(d)
        valores = [d["cod"], d.get("loja") or "", d.get("nome") or "",
                   d.get("fantasia") or "", " · ".join(d["falta"]),
                   "SIM" if d.get("na_rota") else "NÃO",
                   d.get("uf") or "", d.get("cidade") or "",
                   d.get("bairro") or "", d.get("endereco") or "",
                   d.get("numero") or "", d.get("contato") or "",
                   _vend_planner_txt(d), d.get("supervisor") or "",
                   d.get("segmento") or "", d.get("curva") or "",
                   d.get("status") or "", "abrir ›" if link else ""]
        valores += [""] * len(amarelas) + [texto(d.get("chave"))]
        for j, v in enumerate(valores, 1):
            c = ws.cell(i, j, v)
            c.font = Font(name="Arial", size=10)
            c.border = borda
            if n_base < j <= n_base + len(amarelas):
                c.fill = f_am
                c.protection = Protection(locked=False)
                c.number_format = "@"    # texto: o Excel nao mexe no ponto
            else:
                c.protection = Protection(locked=True)
                if d.get("na_rota") and j <= n_base:
                    c.fill = f_rota
        if link:
            c = ws.cell(i, n_base)
            c.hyperlink = link
            c.font = Font(name="Arial", size=10, color="1F5FBF",
                          underline="single")
    # linhas em branco a mais tambem ficam livres nas amarelas (copiar e
    # colar de uma vez)
    ult = len(todas)
    ws.column_dimensions[ws.cell(1, ult).column_letter].hidden = True
    ws.freeze_panes = "E2"
    if lista:
        ws.auto_filter.ref = (f"A1:{ws.cell(1, ult).column_letter}"
                              f"{len(lista) + 1}")
    ws.protection.sheet = True
    ws.protection.autoFilter = False       # filtro liberado
    ws.protection.formatColumns = False    # largura liberada
    ws.protection.formatRows = False
    ws.protection.sort = False
    # ---- COMO PREENCHER
    ap = wb.create_sheet("COMO PREENCHER")
    ap.column_dimensions["A"].width = 110
    passos = [
        ("COMO PREENCHER", True),
        ("", False),
        ("1. Só as colunas AMARELAS são editáveis. As outras vêm da base "
         "do Planner (BASE_CLIENTE) e estão protegidas.", False),
        ("2. Comece pelos clientes NA ROTA DO MÊS = SIM (linhas rosadas, "
         "no topo): são os que mais atrapalham a roteirização.", False),
        ("3. Coluna BUSCAR NO MAPS: clique em \"abrir ›\" para procurar o "
         "cliente no Google Maps pelo nome e pelo endereço.", False),
        ("4. LATITUDE e LONGITUDE: no Google Maps, clique com o botão "
         "direito em cima do ponto do cliente. O primeiro item do menu é "
         "a coordenada (ex.: -3.1190, -60.0217); clique nele para copiar.",
         False),
        ("   Cole o primeiro número em LATITUDE e o segundo em LONGITUDE. "
         "Se colar os dois juntos na LATITUDE (\"-3.1190, -60.0217\"), "
         "também vale.", False),
        ("5. Use PONTO como separador decimal (-3.1190), como o Google "
         "mostra. As colunas amarelas estão em formato texto para o Excel "
         "não trocar o ponto.", False),
        ("6. Se preferir, cole o LINK do Google Maps do ponto em LINK "
         "GOOGLE MAPS: quando ele tiver a coordenada, ela é lida dele.",
         False),
        ("7. ENDEREÇO CORRETO, Nº, BAIRRO e CEP: escreva como no cadastro "
         "do Protheus. Estas colunas NÃO atualizam nada sozinhas: o "
         "endereço é corrigido no Protheus (é lá que fica o cadastro).",
         False),
        ("8. Preencha PREENCHIDO POR e DATA. OBSERVAÇÃO é livre (ex.: "
         "\"cliente fechou\", \"mudou para outra cidade\").", False),
        ("9. Salve o arquivo e devolva. No BAP Relatórios › Divergências "
         "clientes › Exportar para correção ▾ › Importar preenchidos, as "
         "coordenadas vão para o arquivo de coordenadas dos clientes "
         "(COORDENADAS_CLIENTES.json), marcadas como MANUAL.", False),
        ("", False),
        ("O QUE É RECUSADO NA IMPORTAÇÃO", True),
        ("· coordenada fora do Brasil ou com latitude e longitude trocadas;",
         False),
        ("· coordenada a mais de 60 km do centro da cidade do cliente;",
         False),
        ("· cliente que não está mais na base do Planner.", False),
        ("O BAP mostra quantas foram gravadas e quantas foram recusadas, "
         "com o motivo.", False),
    ]
    for i, (t, neg) in enumerate(passos, 1):
        c = ap.cell(i, 1, t)
        c.font = Font(name="Arial", size=11 if neg else 10, bold=neg,
                      color="2F7D32" if neg else "000000")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.move_sheet(ap, offset=-1)
    wb.active = 1
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino, len(lista)


def _numero_coord(v):
    """Um numero de coordenada: "-3.1190", -3.119 (celula numerica) ou
    "-3,1190" (virgula decimal, um numero so). None se nao for numero."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = texto(v).strip().replace(" ", "")
    if t.count(",") == 1 and "." not in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def coordenada_preenchida(lat, lon, link=""):
    """(lat, lon) do que a analista preencheu: as duas colunas, os dois
    numeros juntos na LATITUDE ("-3.1190, -60.0217") ou o link do Google
    Maps (".../@-3.119,-60.0217,17z", "?q=-3.119,-60.0217",
    "destination=..."). (None, None) se nada."""
    t = texto(lat).strip()
    m = re.match(r"^\s*(-?\d{1,2}\.\d+)\s*[,;]\s*(-?\d{1,3}\.\d+)\s*$", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    la, lo = _numero_coord(lat), _numero_coord(lon)
    if la is not None and lo is not None:
        return la, lo
    lk = texto(link)
    for rx in (r"@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)",
               r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)",
               r"(?:q|query|destination|ll)=(-?\d{1,2}\.\d+)(?:,|%2C)"
               r"(-?\d{1,3}\.\d+)"):
        m = re.search(rx, lk)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None, None


def importar_preenchidos(ctx, arquivo) -> dict:
    """Le o Excel preenchido e grava as coordenadas no
    COORDENADAS_CLIENTES.json com "origem": "MANUAL" (o geocodificar nao
    apaga o ponto manual). Devolve {"gravados": [..], "recusados":
    [(cliente, motivo)], "sem_coordenada": n, "arquivo": caminho}."""
    from openpyxl import load_workbook                  # noqa: PLC0415
    import geocodificar as gc                           # noqa: PLC0415
    import geografia as geo                             # noqa: PLC0415
    wb = load_workbook(arquivo, read_only=True, data_only=True)
    ws = wb["PREENCHER"] if "PREENCHER" in wb.sheetnames else wb.active
    it = ws.iter_rows(values_only=True)
    cab = [sem_acento(texto(x)).upper() for x in next(it, ())]

    def ix(*nomes):
        for n in nomes:
            n = sem_acento(n).upper()
            if n in cab:
                return cab.index(n)
        return None
    i_cod, i_loja, i_ch = ix("CÓD.", "COD"), ix("LOJA"), ix("CHAVE")
    i_lat, i_lon, i_lk = ix("LATITUDE"), ix("LONGITUDE"), ix(
        "LINK GOOGLE MAPS")
    i_por, i_dt, i_obs = ix("PREENCHIDO POR"), ix("DATA"), ix("OBSERVAÇÃO")
    if i_cod is None or (i_lat is None and i_lk is None):
        wb.close()
        raise ValueError("Este Excel não é o \"Clientes sem coordenada/"
                         "endereço (para preencher)\": faltam as colunas "
                         "CÓD. e LATITUDE.")
    base = {}
    for c in ctx.base.get("clientes") or []:
        base[texto(c.get("chave"))] = c
        base[(texto(c["cod"]).zfill(6), _loja2(c.get("loja")))] = c

    def pega(lin, i):
        return lin[i] if i is not None and i < len(lin) else None
    arq = gc.caminho(ctx.raiz)
    dados = gc.ler(arq)
    gravados, recusados, vazios = [], [], 0
    hoje = ctx.hoje.isoformat() if hasattr(ctx.hoje, "isoformat") else \
        date.today().isoformat()
    for lin in it:
        cod = texto(pega(lin, i_cod))
        if not cod:
            continue
        la, lo = coordenada_preenchida(pega(lin, i_lat), pega(lin, i_lon),
                                       pega(lin, i_lk))
        loja = texto(pega(lin, i_loja))
        quem = f"{cod.zfill(6)}-{loja or '01'}"
        if la is None:
            if texto(pega(lin, i_lat)) or texto(pega(lin, i_lon)):
                recusados.append((quem, "coordenada ilegível (use ponto "
                                        "decimal: -3.1190)"))
            else:
                vazios += 1
            continue
        c = base.get(texto(pega(lin, i_ch))) or base.get(
            (cod.zfill(6), _loja2(loja)))
        if not c:
            recusados.append((quem, "cliente não está na base do Planner"))
            continue
        quem = f"{c['cod']}-{c.get('loja') or '01'} " \
               f"{c.get('fantasia') or c.get('nome') or ''}".strip()
        if not geo.ponto_valido(la, lo):
            motivo = ("latitude e longitude trocadas?"
                      if geo.ponto_valido(lo, la) else "fora do Brasil")
            recusados.append((quem, f"coordenada {la}, {lo}: {motivo}"))
            continue
        centro = geo.coordenada(c.get("uf"), c.get("cidade"))
        if centro and geo.distancia_km(centro, (la, lo)) > RAIO_CIDADE_KM:
            recusados.append((quem, f"a {geo.distancia_km(centro, (la, lo)):.0f}"
                                    f" km do centro de {c.get('cidade')} "
                                    f"(máx. {RAIO_CIDADE_KM:.0f} km)"))
            continue
        por, dt = texto(pega(lin, i_por)), pega(lin, i_dt)
        dt = dt.strftime("%d/%m/%Y") if hasattr(dt, "strftime") else texto(dt)
        partes = [x for x in (por, dt) if x]
        chave = texto(c.get("chave"))
        ant = dados.get(chave) or {}
        novo = {k: v for k, v in ant.items() if k not in ("lat", "lon")}
        novo.update({
            "end": gc.endereco_do_cliente({
                "ENDERECO": c.get("endereco"), "NUMERO": c.get("numero"),
                "CIDADE": c.get("cidade"), "UF": c.get("uf")}),
            "LATITUDE": gc.texto_coordenada(la),
            "LONGITUDE": gc.texto_coordenada(lo),
            "precisao": "endereco", "em": hoje, "origem": ORIGEM_MANUAL,
            "fonte": "Excel de preenchimento" + (
                f" ({', '.join(partes)})" if partes else "")})
        obs = texto(pega(lin, i_obs))
        if obs:
            novo["obs"] = obs
        if ant and gc.ponto(ant)[0] is not None and \
                _ponto_do_arquivo(ant) != ORIGEM_MANUAL:
            novo["antes"] = f"{ant.get('LATITUDE', ant.get('lat'))}, " \
                            f"{ant.get('LONGITUDE', ant.get('lon'))}"
        dados[chave] = novo
        gravados.append(quem)
    wb.close()
    if gravados:
        gc.gravar(arq, dados)
    return {"gravados": gravados, "recusados": recusados,
            "sem_coordenada": vazios, "arquivo": str(arq)}


# =========================================================================
# FAROL DE PRECO (15/10, Alexandre): o impacto do preco no faturamento das
# categorias e familias, mes a mes. Para cada mes x mes anterior:
#   FATURAMENTO, VOLUME (unidades) e PRECO MEDIO (= faturamento / volume);
#   VAR. PRECO (MESMO ITEM): o preco praticado dos MESMOS produtos, na MESMA
#     filial, nos dois meses, pesado pela quantidade do mes (sem o efeito
#     do mix: vender mais bateria nao "sobe o preco");
#   VAR. TABELA: o mesmo, com o PRECO DE TABELA (o reajuste da tabela);
#   EFEITO PRECO = soma (preco do mes - preco do mes anterior) x qtd do mes
#     (so os itens vendidos nos dois meses); EFEITO VOLUME = variacao do
#     volume x preco medio do mes anterior; EFEITO MIX = o resto (produto
#     novo/que saiu e a troca entre itens caros e baratos);
#   ELASTICIDADE = var. % do volume / var. % do preco (so com preco
#     mexendo): -1 = cada 1% de aumento tirou 1% do volume.
# LEITURA: o preco mexeu (>= LIMIAR_PRECO %) e o faturamento caiu ou subiu.
# So o FATURADO (VND, dt da nota), sem os CNPJs internos.
# =========================================================================
LIMIAR_PRECO = 2.0          # % de variacao de preco que conta como mudanca
L_QUEDA = "QUEDA APÓS REAJUSTE"
L_ABSORVIDO = "REAJUSTE ABSORVIDO"
L_RED_VOL = "REDUÇÃO TROUXE VOLUME"
L_RED_SEM = "REDUÇÃO SEM VOLUME"
L_ESTAVEL = "PREÇO ESTÁVEL"
L_SEM_BASE = "SEM MÊS ANTERIOR"


PARCIAL = "*"                # sufixo do mes anterior "ate o mesmo dia"
# as colunas das tabelas mes a mes (categoria, familia, total)
(P_M, P_MM, P_G, P_L, P_FAT, P_VF, P_VOL, P_VV, P_PM, P_PT, P_VP, P_VT,
 P_DF, P_EP, P_EV, P_EM, P_EL) = range(17)


def _var_pct(a, b):
    """% de b sobre a (None quando a e zero/None)."""
    return (b / a - 1) * 100.0 if a else None


def leitura_preco(var_preco, var_fat):
    if var_preco is None or var_fat is None:
        return L_SEM_BASE
    if var_preco >= LIMIAR_PRECO:
        return L_QUEDA if var_fat < 0 else L_ABSORVIDO
    if var_preco <= -LIMIAR_PRECO:
        return L_RED_VOL if var_fat >= 0 else L_RED_SEM
    return L_ESTAVEL


def _meses_do_preco(ctx):
    """Os meses do farol: os 12 ate o mes escolhido (TODOS OS MESES: o ano
    escolhido, ate hoje) - e o mes de antes do primeiro, so como base."""
    ano, mes = periodo(ctx)
    if mes:
        fim = date(ano, mes, 1)
        n = 12
    else:
        fim = date(ano, 12 if ano < ctx.hoje.year else ctx.hoje.month, 1)
        n = fim.month
    meses = []
    d = fim
    for _ in range(n + 1):
        meses.append(f"{d.year}-{d.month:02d}")
        d = (d - timedelta(days=1)).replace(day=1)
    meses.reverse()
    return meses[0], meses[1:]


def comparar_precos(atual: dict, antes: dict) -> dict:
    """atual/antes: {(filial, cod): {"v": R$, "q": qtd, "t": R$ tabela}}.
    Devolve faturamento, volume, preco medio, var. de preco e de tabela
    (mesmo item), efeitos preco/volume/mix e elasticidade."""
    fat1 = sum(x["v"] for x in atual.values())
    vol1 = sum(x["q"] for x in atual.values())
    fat0 = sum(x["v"] for x in antes.values())
    vol0 = sum(x["q"] for x in antes.values())
    comuns = [k for k in atual if k in antes and atual[k]["q"] > 0
              and antes[k]["q"] > 0]
    num = den = tnum = tden = ef_p = q1c = q0c = 0.0
    for k in comuns:
        a, b = atual[k], antes[k]
        q1c += a["q"]
        q0c += b["q"]
        p1, p0 = a["v"] / a["q"], b["v"] / b["q"]
        num += p1 * a["q"]
        den += p0 * a["q"]
        ef_p += (p1 - p0) * a["q"]
        if a["t"] > 0 and b["t"] > 0:
            tnum += a["t"] / a["q"] * a["q"]
            tden += b["t"] / b["q"] * a["q"]
    tem_base = bool(antes)
    var_p = _var_pct(den, num) if comuns else None
    var_t = _var_pct(tden, tnum) if tden else None
    pm1 = fat1 / vol1 if vol1 else None
    pm0 = fat0 / vol0 if vol0 else None
    ef_v = (vol1 - vol0) * pm0 if tem_base and pm0 is not None else None
    d_fat = fat1 - fat0 if tem_base else None
    ef_mix = (d_fat - ef_p - ef_v) if ef_v is not None else None
    var_f = _var_pct(fat0, fat1) if tem_base else None
    var_v = _var_pct(vol0, vol1) if tem_base else None
    # a elasticidade so com os MESMOS itens (o volume total muda com o mix)
    var_vc = _var_pct(q0c, q1c) if comuns else None
    ref_ = var_t if var_t is not None else var_p      # (15/10) a tabela
    elast = (var_vc / ref_) if (var_vc is not None and ref_ is not None
                                and abs(ref_) >= LIMIAR_PRECO) else None
    tab1 = sum(x["t"] for x in atual.values())
    vol_t = sum(x["q"] for x in atual.values() if x["t"] > 0)
    return {"fat": fat1, "vol": vol1, "pm": pm1, "fat0": fat0,
            # (15/10) o PRECO DE TABELA medio (a negociacao fica de fora)
            "pt": tab1 / vol_t if vol_t else None,
            "var_fat": var_f, "var_vol": var_v, "var_p": var_p,
            "var_t": var_t, "d_fat": d_fat,
            "ef_p": ef_p if tem_base and comuns else None, "ef_v": ef_v,
            "ef_mix": ef_mix, "elast": elast, "itens_comuns": len(comuns)}


T_CAPITAL, T_INTERIOR, T_SEM = "CAPITAL", "INTERIOR", "SEM TABELA"


# (27/10) a diferenca de preco BAP x concorrencia que conta como "mais cara"
# / "mais barata" na Pesquisa de mercado [SUPOSICAO 2%]
LIMIAR_PESQUISA = 2.0
L_BAP_CARA, L_BAP_BARATA, L_EMPATE, L_SEM_PRECO = (
    "BAP MAIS CARA", "BAP MAIS BARATA", "PREÇO IGUAL", "SEM PREÇO")
# (28/10, recado 20261027-1555 do BAP Ajuda) o cliente nao trabalha com o
# produto: fora das medias de preco; conta como presenca (% dos itens)
L_NAO_TRABALHA = "NÃO TRABALHA"


def _tabela_pesquisa_mercado(ctx, escolha=None):
    """(27/10, Alexandre - recados do BAP Ajuda 20261027-0740 e 0820) Aba
    PESQUISA DE MERCADO do Farol de Preco: o app BAP Ajuda 2.0, uma linha
    por item pesquisado no cliente (itens do Dia Foco: PRINCIPAL e
    COMPLEMENTAR; itens a mais: PESQUISA). Precos INFORMADOS NO PDV:
    COMPRA = o que o cliente paga; VENDA = o que ele cobra do consumidor.
        DIF. COMPRA % = compra BAP / compra concorrencia - 1 (o mesmo na
                        venda); LEITURA pela compra (+-LIMIAR_PESQUISA)
        MKP CLIENTE % = venda / compra - 1 (de cada lado)
        COMPRA x TABELA % = compra BAP no PDV / PRC. TABELA BAP do cadastro
                        (capital ou interior, pela A1_TABELA do cliente) - 1
        SHARE ESTOQUE / VOLUME % = BAP / (BAP + concorrencia), no PDV
    "SEM CODIGO BAP" (item que a BAP nao tem) e so leitura de mercado: sem
    tabela nem classificacao. CATEGORIA/SISTEMA/FAMILIA/LINHA de cima valem
    (o sem codigo sai quando ha escolha). Testes (000040) fora."""
    import respostas_bap_ajuda as rb                    # noqa: PLC0415
    cad = _cadastro_de_precos(ctx)
    cli_tab = ctx.tabela.get("clientes") or {}
    linhas = []

    def dif(a, b):
        return (a / b - 1) * 100.0 if a and b else None

    def share(a, b):
        t = (a or 0) + (b or 0)
        return (a or 0) / t * 100.0 if t else None
    for x in rb.pesquisas(ctx.raiz):
        cod, sem = x["codigo"], x["sem_codigo"]
        cls = (tuple(ctx.classe(cod, n_) for n_ in CLASSE_PRODUTO)
               if not sem else ("",) * len(CLASSE_PRODUTO))
        if escolha and (sem or any(cls[i_] != v_
                                   for i_, v_ in escolha.items())):
            continue
        c_ = {} if sem else (cad.get(cod) or {})
        tipo = tipo_de_tabela((cli_tab.get(x["cod_cliente"]) or {})
                              .get("tabela_preco"))
        tab = (c_.get("inte") if tipo == T_INTERIOR and c_.get("inte")
               else c_.get("cap")) or None
        dc = dif(x["compra_bap"], x["compra_conc"])
        dv = dif(x["venda_bap"], x["venda_conc"])
        if not x.get("trabalha", True):
            leit = L_NAO_TRABALHA
        elif dc is None:
            leit = L_SEM_PRECO
        elif dc > LIMIAR_PESQUISA:
            leit = L_BAP_CARA
        elif dc < -LIMIAR_PESQUISA:
            leit = L_BAP_BARATA
        else:
            leit = L_EMPATE
        d = x["dia"]
        cli = x["cliente"] or x["cod_cliente"]
        linhas.append([
            rotulo_mes(mes_de(d)) if d else "", d, x["vendedor"],
            x["supervisor"], cli, x["cidade"], x["uf"], x["segmento"],
            x["linha"], x["papel"], cod or rb.SEM_CODIGO,
            (ctx.produto(cod) if not sem and cod else "") or x["descricao"],
            x["marca"], x["cod_conc"], leit,
            x["compra_bap"], x["compra_conc"], dc,
            x["venda_bap"], x["venda_conc"], dv,
            dif(x["venda_bap"], x["compra_bap"]),
            dif(x["venda_conc"], x["compra_conc"]),
            tab, dif(x["compra_bap"], tab),
            x["est_bap"], x["est_conc"], share(x["est_bap"], x["est_conc"]),
            x["vol_bap"], x["vol_conc"], share(x["vol_bap"], x["vol_conc"]),
            x["obs"], cls[0], cls[2]])
    linhas.sort(key=lambda l: (-(l[1].toordinal() if l[1] else 0), l[2],
                               l[4], l[8], l[10]))
    tons = ["alerta" if l[14] == L_BAP_CARA else
            ("ok" if l[14] == L_BAP_BARATA else "") for l in linhas]
    cols = [col("MÊS", "texto", 62, oculta=True), col("DATA", "data", 76),
            col("VENDEDOR", "texto", 200), col("SUPERVISOR", "texto", 180,
                                               oculta=True),
            col("CLIENTE", "texto", 230), col("CIDADE", "texto", 110),
            col("UF", "texto", 36), col("SEGMENTO", "texto", 130,
                                        oculta=True),
            col("LINHA DIA FOCO", "texto", 130), col("PAPEL", "texto", 96),
            col("CÓD. BAP", "texto", 110), col("PRODUTO", "texto", 230),
            col("CONCORRENTE", "texto", 110),
            col("CÓD. CONCORRENTE", "texto", 150, oculta=True),
            col("LEITURA", "texto", 110),
            col("COMPRA BAP", "moeda2", 80), col("COMPRA CONC.", "moeda2", 84),
            col("DIF. COMPRA %", "pct1", 76),
            col("VENDA BAP", "moeda2", 80), col("VENDA CONC.", "moeda2", 80),
            col("DIF. VENDA %", "pct1", 74),
            col("MKP CLIENTE BAP %", "pct1", 88),
            col("MKP CLIENTE CONC. %", "pct1", 92),
            col("PRC. TABELA BAP", "moeda2", 88),
            col("COMPRA x TABELA %", "pct1", 90),
            col("ESTOQUE BAP", "num", 70), col("ESTOQUE CONC.", "num", 74),
            col("SHARE ESTOQUE %", "pct1", 84),
            col("VOL. BAP", "num", 62), col("VOL. CONC.", "num", 66),
            col("SHARE VOLUME %", "pct1", 82),
            col("OBSERVAÇÃO", "texto", 200),
            col("CATEGORIA", "texto", 110, oculta=True),
            col("FAMÍLIA", "texto", 120, oculta=True)]

    def media(vs):
        vs = [v for v in vs if v is not None]
        return sum(vs) / len(vs) if vs else None

    def cartoes(ls):
        if not ls:
            return []
        com = [l for l in ls if l[17] is not None]
        cara = sum(1 for l in com if l[14] == L_BAP_CARA)
        barata = sum(1 for l in com if l[14] == L_BAP_BARATA)
        m_dc = media(l[17] for l in ls)
        se = share(sum(l[25] or 0 for l in ls), sum(l[26] or 0 for l in ls))
        sv = share(sum(l[28] or 0 for l in ls), sum(l[29] or 0 for l in ls))
        m_b, m_c = media(l[21] for l in ls), media(l[22] for l in ls)
        nt = sum(1 for l in ls if l[14] == L_NAO_TRABALHA)
        return [
            kpi("Itens pesquisados", br(len(ls)), "neutro",
                f"{br(len({(l[4], l[1]) for l in ls}))} cliente(s) · "
                f"{br(len({l[2] for l in ls}))} vendedor(es)"
                + (f" · não trabalha {br(nt)} ({p(pct_de(nt, len(ls)))})"
                   if nt else "")),
            kpi("BAP mais cara na compra", br(cara),
                "alerta" if cara else "ok",
                f"de {br(len(com))} com preço · mais barata {br(barata)}"),
            kpi("Dif. de compra (média)",
                "—" if m_dc is None else f"{br(m_dc, 1)}%",
                "neutro" if m_dc is None else ("alerta" if m_dc >
                                               LIMIAR_PESQUISA else "ok"),
                "BAP x concorrência, no PDV"),
            kpi("Markup do cliente", "—" if m_b is None else
                f"{br(m_b, 0)}%", "neutro",
                "BAP · concorrência " + ("—" if m_c is None
                                         else f"{br(m_c, 0)}%")),
            kpi("Share de estoque no PDV", p(se), "neutro",
                "volume vendido " + p(sv))]
    t = tabela("Pesquisa de mercado", cols, linhas, tons,
               filtros=("MÊS", "VENDEDOR", "LINHA DIA FOCO", "PAPEL",
                        "CONCORRENTE", "UF", "CIDADE", "LEITURA"),
               kpis_de=cartoes,
               recortes=[("BAP mais cara na compra",
                          lambda l: l[14] == L_BAP_CARA),
                         ("BAP mais cara na venda",
                          lambda l: (l[20] or 0) > LIMIAR_PESQUISA),
                         ("Itens do Dia Foco",
                          lambda l: l[9] in ("PRINCIPAL", "COMPLEMENTAR")),
                         ("Sem código BAP",
                          lambda l: l[10] == rb.SEM_CODIGO),
                         ("Cliente não trabalha",
                          lambda l: l[14] == L_NAO_TRABALHA)])
    t["compacta"] = True
    t["pdf"] = {"compacto": True, "zebra": True, "data_curta": True,
                "corpo": 6.0, "cab": 5.2, "pad": 2.2,
                "quebra": ("CLIENTE", "PRODUTO", "OBSERVAÇÃO"),
                "contagem": "linhas"}
    if not linhas:
        t["vazio"] = ("Nenhuma pesquisa de mercado no período. A pesquisa do "
                      "app BAP Ajuda (Dia Foco) entra com a sincronização do "
                      "BAP Ajuda (RELATORIOS\\BAP_AJUDA_RESPOSTAS).")
    return t


def tipo_de_tabela(cod_tabela) -> str:
    """(15/10) A1_TABELA do cliente: final 1 = CAPITAL (AM1, PA1...),
    final 2 = INTERIOR (AM2, PA2...); outro codigo fica com o proprio nome
    ("OUTRA: AMP"); vazio = SEM TABELA."""
    t = texto(cod_tabela).upper()
    if not t:
        return T_SEM
    if t.endswith("1"):
        return T_CAPITAL
    if t.endswith("2"):
        return T_INTERIOR
    return f"OUTRA: {t}"


def preco_x_volume(linhas_total, m_corr=None):
    """(15/10, Alexandre) PRECO DE TABELA (R$) x VOLUME (unidades), mes a
    mes, em duas linhas - o preco de TABELA, nao o praticado (a negociacao
    do vendedor nao conta como mudanca de preco). Cada linha na sua faixa
    e o numero de cada ponto e o valor de verdade (R$ e unidades).
    Tambem o grafico da VARIACAO % DO PRECO DE TABELA mes a mes (mesmo
    item). O mes em andamento fica fora (volume pela metade). Devolve os
    graficos e a contagem: meses com a tabela subindo e o volume caindo
    (o esperado) x subindo e o volume subindo junto."""
    ls = sorted((l for l in linhas_total if l[P_MM] != m_corr
                 and l[P_PT]), key=lambda l: l[P_MM])
    if len(ls) < 2:
        return None
    preco = [l[P_PT] for l in ls]
    vol = [l[P_VOL] or 0.0 for l in ls]
    mp = sum(preco) / len(preco) or 1
    mv = sum(vol) / len(vol) or 1
    sobe_cai = sobe_sobe = cai_sobe = 0
    for i in range(1, len(ls)):
        vt_ = ls[i][P_VT]
        if vt_ is None or abs(vt_) < LIMIAR_PRECO:
            continue
        dv = vol[i] - vol[i - 1]
        if vt_ > 0 and dv < 0:
            sobe_cai += 1
        elif vt_ > 0:
            sobe_sobe += 1
        elif dv > 0:
            cai_sobe += 1
    rot = [rotulo_mes(l[P_MM]) for l in ls]
    return {"grafico": {
        "titulo": "Preço de tabela (R$) x volume (unidades)",
        "largo": True, "linhas": True, "formato": "num", "rotulos": rot,
        "series": [{"nome": "Preço de tabela (R$)", "cor": AMARELO,
                    "valores": [round(x / mp * 100, 1) for x in preco],
                    "rotulos": [moeda(x) for x in preco]},
                   {"nome": "Volume (unidades)", "cor": AZUL,
                    "valores": [round(x / mv * 100, 1) for x in vol],
                    "rotulos": [br(x) for x in vol]}]},
        "grafico_tabela": {
            "titulo": "Variação % do preço de tabela x mês anterior",
            "largo": True, "formato": "pct", "variacao_tabela": True,
            "rotulos": rot,
            "series": [{"nome": "Preço de tabela", "cor": AMARELO,
                        "cor_negativo": AZUL,
                        "valores": [round(l[P_VT] or 0, 1) for l in ls]}]},
        "sobe_cai": sobe_cai, "sobe_sobe": sobe_sobe, "cai_sobe": cai_sobe,
        "meses": [l[P_MM] for l in ls]}


def farol_preco(ctx):
    """FAROL DE PRECO: faturamento x volume x preco, mes a mes, por
    categoria, familia e produto - houve queda quando o preco mudou?"""
    r = novo("vc_preco", ANA, "Farol de Preço",
             f"Faturamento x volume x preço, mês a mês · mudança de preço = "
             f"tabela {br(LIMIAR_PRECO)}% ou mais no mesmo item",
             "TABELA_BAP › ftPedidos (faturado, preço praticado e de tabela)")
    capa(r, ctx, anos_dos_dados(ctx))
    fil_esc = ctx.param("FILIAL")
    if fil_esc in (None, "", TODOS_RECORTE):
        fil_esc = None
    filiais = sorted(set((ctx.tabela.get("filiais") or {}).values()))
    if fil_esc and fil_esc not in filiais:
        filiais.append(fil_esc)
    r["parametros"].append({"nome": "FILIAL",
                            "valores": [TODOS_RECORTE] + filiais,
                            "valor": fil_esc or TODOS_RECORTE})
    if fil_esc:
        r["subtitulo"] += f" · Filial {fil_esc}"
    # (15/10, Alexandre) CATEGORIA, SISTEMA, FAMILIA e LINHA (Catalogo BAP
    # 2026) em cima valem para TUDO (cartoes, resumo, graficos e tabelas):
    # sao parametros, o farol refaz. As opcoes seguem as outras escolhas
    info = {}
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND" and it["cod"] not in info:
            info[it["cod"]] = tuple(ctx.classe(it["cod"], n_)
                                    for n_ in CLASSE_PRODUTO)
    escolha = {}
    esc_c = {}
    for pos_, nome_ in enumerate(CLASSE_PRODUTO):
        v_ = ctx.param(nome_)
        esc_c[pos_] = None if v_ in (None, "", TODOS_RECORTE) else v_
    for pos_, nome_ in enumerate(CLASSE_PRODUTO):
        v_ = esc_c[pos_]
        vals_ = ordem_da_classe(nome_, {
            x[pos_] for x in info.values()
            if all(p_ == pos_ or not e_ or x[p_] == e_
                   for p_, e_ in esc_c.items())} | ({v_} if v_ else set()))
        r["parametros"].append({"nome": nome_,
                                "valores": [TODOS_RECORTE] + vals_,
                                "valor": v_ or TODOS_RECORTE})
        if v_:
            escolha[pos_] = v_
            r["subtitulo"] += f" · {nome_.title()} {v_}"
    # (15/10, Alexandre) TABELA: CAPITAL ou INTERIOR - a tabela de preco
    # do cliente no Protheus (A1_TABELA, final 1 ou 2)
    cli_tab = ctx.tabela.get("clientes") or {}
    tab_de = {}
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND" and it["cliente"] not in tab_de:
            tab_de[it["cliente"]] = tipo_de_tabela(
                (cli_tab.get(it["cliente"]) or {}).get("tabela_preco"))
    tab_esc = ctx.param("TABELA")
    tab_esc = None if tab_esc in (None, "", TODOS_RECORTE) else tab_esc
    vals_t = [T_CAPITAL, T_INTERIOR] + sorted(
        set(tab_de.values()) - {T_CAPITAL, T_INTERIOR})
    r["parametros"].append({"nome": "TABELA",
                            "valores": [TODOS_RECORTE] + vals_t,
                            "valor": tab_esc or TODOS_RECORTE})
    if tab_esc:
        r["subtitulo"] += f" · Tabela {tab_esc}"
    if not any(v not in (T_SEM,) for v in tab_de.values()):
        r["avisos"].append("A TABELA_BAP ainda não traz a tabela de preço "
                           "do cliente (A1_TABELA): o filtro TABELA vale "
                           "depois da próxima atualização.")
    # (15/10, Alexandre) PRODUTO: a lista segue a categoria/familia
    # escolhida; da para digitar o codigo ou parte do nome
    prod_esc = ctx.param("PRODUTO")
    prod_esc = None if prod_esc in (None, "", TODOS_RECORTE) else prod_esc
    cods_ = sorted(c_ for c_, x in info.items()
                   if all(x[p_] == v_ for p_, v_ in escolha.items()))
    if prod_esc and escolha and prod_esc not in cods_:
        prod_esc = None          # trocou a categoria: o produto nao e dela
    r["parametros"].append({
        "nome": "PRODUTO",
        "valores": [(TODOS_RECORTE, TODOS_RECORTE)]
        + [(c_, f"{c_} - {ctx.produto(c_)}"[:60]) for c_ in cods_]
        + ([(prod_esc, prod_esc)] if prod_esc and prod_esc not in cods_
           else []),
        "valor": prod_esc or TODOS_RECORTE})
    if prod_esc:
        r["subtitulo"] += f" · Produto {prod_esc}"
    base_m, meses = _meses_do_preco(ctx)
    todos_m = set([base_m] + meses)
    # (mes, grupo) -> {(filial, cod): {"v", "q", "t"}}
    cat_m = defaultdict(lambda: defaultdict(lambda: {"v": 0.0, "q": 0.0,
                                                     "t": 0.0}))
    fam_m = defaultdict(lambda: defaultdict(lambda: {"v": 0.0, "q": 0.0,
                                                     "t": 0.0}))
    tot_m = defaultdict(lambda: defaultdict(lambda: {"v": 0.0, "q": 0.0,
                                                     "t": 0.0}))
    eventos = []
    # o mes em andamento (o de hoje) e o anterior ate o mesmo dia
    m_corr = mes_de(ctx.hoje)
    _d = ctx.hoje.replace(day=1) - timedelta(days=1)
    m_ant_corr = mes_de(_d)
    for it in ctx.tabela["itens"]:
        if it["tipo"] != "VND" or not it.get("dt_nf") or it["qtd"] <= 0:
            continue
        if fil_esc and ctx.filial(it["filial"]) != fil_esc:
            continue
        if escolha and any(info[it["cod"]][p_] != v_
                           for p_, v_ in escolha.items()):
            continue
        if prod_esc and it["cod"] != prod_esc:
            continue
        if tab_esc and tab_de.get(it["cliente"]) != tab_esc:
            continue
        eventos.append((it["dt_nf"], it["valor"], it["qtd"],
                        it["p_tab"] * it["qtd"] if it["p_tab"] > 0 else 0.0))
        m = mes_de(it["dt_nf"])
        if m not in todos_m:
            continue
        cod = it["cod"]
        cat, _sis, fam, _lin = info[cod]
        k = (it["filial"], cod)
        tab = it["p_tab"] * it["qtd"] if it["p_tab"] > 0 else 0.0
        chaves = [m]
        if m == m_ant_corr and it["dt_nf"].day <= ctx.hoje.day:
            chaves.append(m + PARCIAL)
        for m_ in chaves:
            for alvo in (cat_m[(m_, cat)][k], fam_m[(m_, fam)][k],
                         tot_m[(m_, "BAP")][k]):
                alvo["v"] += it["valor"]
                alvo["q"] += it["qtd"]
                alvo["t"] += tab
    graficos_tempo(r, ctx, "Faturamento (R$)", [(d, v) for d, v, _q, _t in
                                                eventos], "moeda", VERDE)

    def linhas_de(por, rotulo):
        grupos = sorted({g for (_m, g) in por})
        saida = []
        for g in grupos:
            for i, m in enumerate(meses):
                atual = por.get((m, g)) or {}
                m0 = meses[i - 1] if i else base_m
                # o mes em andamento x o anterior ATE O MESMO DIA
                if m == m_corr:
                    m0 = m0 + PARCIAL
                ant = por.get((m0, g)) or {}
                if not atual and not ant:
                    continue
                c = comparar_precos(atual, ant)
                saida.append([rotulo_mes(m) + ("*" if m == m_corr else ""),
                              m, g,
                              # (15/10) a LEITURA pela TABELA (negociacao
                              # nao e mudanca de preco); sem tabela, o
                              # praticado
                              leitura_preco(c["var_t"] if c["var_t"]
                                            is not None else c["var_p"],
                                            c["var_fat"]),
                              c["fat"], c["var_fat"],
                              c["vol"], c["var_vol"], c["pm"], c["pt"],
                              c["var_p"],
                              c["var_t"], c["d_fat"], c["ef_p"], c["ef_v"],
                              c["ef_mix"], c["elast"]])
        saida.sort(key=lambda l: (l[1], -(l[P_FAT] or 0)))
        return saida

    def colunas(rotulo):
        return [col("MÊS", "texto", 62), col("AAAA-MM", "texto", 60,
                                             oculta=True),
                col(rotulo, "texto", 130), col("LEITURA", "texto", 170),
                col("FATURAMENTO", "moeda", 100),
                col("VAR. FAT. %", "pct1", 74), col("VOLUME", "num", 74),
                col("VAR. VOL. %", "pct1", 74),
                col("PREÇO MÉDIO", "moeda2", 84),
                col("PREÇO TABELA", "moeda2", 84),
                col("VAR. PREÇO %", "pct1", 82),
                col("VAR. TABELA %", "pct1", 84),
                col("VAR. FAT. R$", "moeda", 96),
                col("EFEITO PREÇO", "moeda", 92),
                col("EFEITO VOLUME", "moeda", 96),
                col("EFEITO MIX", "moeda", 86),
                col("ELASTICIDADE", "num2", 78)]

    def cartoes(ls):
        if not ls:
            return []
        ult = max(l[1] for l in ls)
        do_mes = [l for l in ls if l[1] == ult]
        fat = sum(l[P_FAT] or 0 for l in do_mes)
        dfat = sum(l[P_DF] or 0 for l in do_mes)
        efp = sum(l[P_EP] or 0 for l in do_mes)
        efv = sum(l[P_EV] or 0 for l in do_mes)
        efm = sum(l[P_EM] or 0 for l in do_mes)
        quedas = [l for l in ls if l[P_L] == L_QUEDA]
        reaj = [l for l in ls if (l[P_VT] if l[P_VT] is not None
                                  else l[P_VP] or 0) >= LIMIAR_PRECO]
        return [
            kpi(f"Faturamento {rotulo_mes(ult)}", moeda(fat), "neutro",
                f"{'+' if dfat >= 0 else '−'}{moeda(abs(dfat))} x mês ant."
                + (f" até dia {ctx.hoje.day}" if ult == m_corr else "")),
            kpi("Efeito preço", moeda(efp), "ok" if efp >= 0 else "alerta",
                f"{rotulo_mes(ult)} · mesmo item"),
            kpi("Efeito volume", moeda(efv), "ok" if efv >= 0 else "alerta",
                f"{rotulo_mes(ult)}"),
            kpi("Efeito mix", moeda(efm), "neutro", "itens novos / troca"),
            kpi("Reajustes", br(len(reaj)), "neutro",
                f"mês x grupo com preço +{br(LIMIAR_PRECO)}% ou mais"),
            kpi("Queda após reajuste", br(len(quedas)),
                "alerta" if quedas else "ok",
                f"de {br(len(reaj))} reajustes" if reaj else "")]
    # ---- total BAP, categoria e familia
    lt = linhas_de(tot_m, "TOTAL")
    lc = linhas_de(cat_m, "CATEGORIA")
    lf = linhas_de(fam_m, "FAMÍLIA")
    r["kpis"] = cartoes(lc)
    filtros_ = ("MÊS", "LEITURA")
    r["tabelas"].append(tabela("Por categoria", colunas("CATEGORIA"), lc,
                               filtros=("MÊS", "CATEGORIA", "LEITURA"),
                               kpis_de=cartoes,
                               recortes=[("Queda após reajuste",
                                          lambda l: l[P_L] == L_QUEDA),
                                         ("Preço mexeu",
                                          lambda l: abs(l[P_VT] or 0)
                                          >= LIMIAR_PRECO)]))
    r["tabelas"].append(tabela("Por família", colunas("FAMÍLIA"), lf,
                               filtros=("MÊS", "FAMÍLIA", "LEITURA"),
                               kpis_de=cartoes,
                               recortes=[("Queda após reajuste",
                                          lambda l: l[P_L] == L_QUEDA),
                                         ("Preço mexeu",
                                          lambda l: abs(l[P_VT] or 0)
                                          >= LIMIAR_PRECO)]))
    r["tabelas"].append(tabela("Total BAP", colunas("TOTAL"), lt,
                               filtros=filtros_, kpis_de=cartoes))
    # ---- os reajustes produto a produto (a origem do efeito preco)
    lp = []
    for i, m in enumerate(meses):
        m0 = meses[i - 1] if i else base_m
        if m == m_corr:
            m0 = m0 + PARCIAL
        atual = tot_m.get((m, "BAP")) or {}
        ant = tot_m.get((m0, "BAP")) or {}
        for k, a in atual.items():
            b = ant.get(k)
            if not b or a["q"] <= 0 or b["q"] <= 0:
                continue
            t1 = a["t"] / a["q"] if a["t"] > 0 else None
            t0 = b["t"] / b["q"] if b["t"] > 0 else None
            p1, p0 = a["v"] / a["q"], b["v"] / b["q"]
            vt = _var_pct(t0, t1) if t0 and t1 else None
            vp = _var_pct(p0, p1)
            # entra quem mexeu na tabela OU no preco praticado; a LEITURA
            # e pelo PRATICADO (o que o cliente pagou: tabela +5% com mais
            # desconto nao e aumento para ele)
            if max(abs(vt or 0), abs(vp or 0)) < LIMIAR_PRECO:
                continue
            fil, cod = k
            cat, sis_, fam, lin_ = info.get(cod) or tuple(
                ctx.classe(cod, n_) for n_ in CLASSE_PRODUTO)
            vf = _var_pct(b["v"], a["v"])
            lp.append([rotulo_mes(m) + ("*" if m == m_corr else ""), m,
                       ctx.filial(fil), cod, ctx.produto(cod), cat, fam,
                       leitura_preco(vt if vt is not None else vp, vf),
                       t0, t1, vt, p0, p1, vp,
                       b["q"], a["q"], _var_pct(b["q"], a["q"]), b["v"],
                       a["v"], vf, sis_, lin_])
    lp.sort(key=lambda l: (l[1], -abs(l[13] or 0)))
    r["tabelas"].append(tabela(
        "Reajustes por produto",
        [col("MÊS", "texto", 62), col("AAAA-MM", "texto", 60, oculta=True),
         col("FILIAL", "texto", 90), col("CÓD. PRODUTO", "texto", 100),
         col("PRODUTO", "texto", 260),
         col("CATEGORIA", "texto", 110, oculta=True),
         col("FAMÍLIA", "texto", 120), col("LEITURA", "texto", 170),
         # o "antes" fica no Excel/filtro; na tela, o agora e a variacao
         col("TABELA ANTES", "moeda2", 84, oculta=True),
         col("TABELA AGORA", "moeda2", 84, oculta=True),
         col("VAR. TABELA %", "pct1", 84),
         col("PRATICADO ANTES", "moeda2", 96, oculta=True),
         col("PREÇO PRATICADO", "moeda2", 100),
         col("VAR. PREÇO %", "pct1", 84),
         col("QTD ANTES", "num", 70, oculta=True),
         col("QTD", "num", 60), col("VAR. QTD %", "pct1", 74),
         col("FAT. ANTES", "moeda", 90, oculta=True),
         col("FATURAMENTO", "moeda", 96), col("VAR. FAT. %", "pct1", 74),
         col("SISTEMA", "texto", 110, oculta=True),
         col("LINHA", "texto", 90, oculta=True)],
        lp, filtros=("MÊS", "FILIAL", "CATEGORIA", "SISTEMA", "FAMÍLIA",
                     "LINHA", "LEITURA"),
        recortes=[("Queda após reajuste", lambda l: l[7] == L_QUEDA),
                  ("Aumento de tabela", lambda l: (l[10] or 0)
                   >= LIMIAR_PRECO),
                  ("Redução de tabela", lambda l: (l[10] or 0)
                   <= -LIMIAR_PRECO)]))
    # ---- o grafico que responde a pergunta: as tres variacoes juntas
    tot = {l[1]: l for l in lt}
    if tot:
        ms = [m for m in meses if m in tot]
        r["graficos"].append({
            "titulo": "Variação % x mês anterior · faturamento, volume e "
                      "preço praticado", "largo": True,
            "rotulos": [rotulo_mes(m) for m in ms],
            "series": [{"nome": "Faturamento", "cor": VERDE,
                        "valores": [round(tot[m][P_VF] or 0, 1)
                                    for m in ms]},
                       {"nome": "Volume", "cor": AZUL,
                        "valores": [round(tot[m][P_VV] or 0, 1)
                                    for m in ms]},
                       {"nome": "Preço praticado", "cor": AMARELO,
                        "valores": [round(tot[m][P_VP] or 0, 1)
                                    for m in ms]}],
            "formato": "pct"})
    pv = preco_x_volume(lt, m_corr)
    if pv:
        r["graficos"].append(pv["grafico"])
        r["graficos"].append(pv["grafico_tabela"])
    # (27/10, Alexandre - recados do BAP Ajuda 20261027-0740 e 0820) a
    # PESQUISA DE MERCADO do app BAP Ajuda: preco de compra e de venda no
    # PDV, da BAP e do maior concorrente; estoque e volume no PDV
    try:
        r["tabelas"].append(_tabela_pesquisa_mercado(ctx, escolha))
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Pesquisa de mercado (BAP Ajuda): {erro}")
    r["_preco"] = {"categoria": lc, "familia": lf, "total": lt,
                   "pv": pv,
                   "produtos": lp, "eventos": eventos}
    if not lc:
        r["avisos"].append("Sem faturamento no período escolhido.")
    if m_corr in meses:
        r["avisos"].append(
            f"{rotulo_mes(m_corr)}* é o mês em andamento: comparado com "
            f"{rotulo_mes(m_ant_corr)} até o dia {ctx.hoje.day}.")
    r["avisos"].append(
        "Volume em unidades: na família que mistura litro, peça e balde, o "
        "PREÇO MÉDIO muda com o mix - a VAR. PREÇO % (mesmo item) é a que "
        "mede o preço.")
    return r


# =========================================================================
# BAP CHAMPIONS (28/10, Alexandre): o jogo de pontos do time, TODO MES.
# Regras e cadastro em bap_champions.py / champions_config.json (editaveis
# no proprio relatorio: botao "Parametros BAP Champions").
#   Faturamento = liquido (VND/VEA - DEV) pela data da NF, por QUEM VENDEU
#     (C5_VEND1) - a mesma conta do realizado da RV. Pontos proporcionais
#     (R$ 500 = metade dos pontos de R$ 1.000), nunca negativos
#     [SUPOSICAO].
#   Equipe do supervisor = os vendedores dele no Farol de Metas do mes.
#   Semana do confronto = segunda a domingo; o bonus vai para o mes da
#     segunda-feira; a semana so e decidida depois do domingo; empate =
#     ninguem ganha [SUPOSICAO]. Pontos da semana = faturamento da semana
#     + os aceleradores que aconteceram nela (a 1a vez no mes).
#   Cliente novo com pedido = cadastrado no mes (A1_DTCAD; sem o lote) e
#     com liquido > 0 do vendedor no mes.
#   SKU novo (supervisor) = codigo com liquido > 0 da equipe no mes que a
#     equipe nunca tinha vendido antes (toda a TABELA_BAP).
#   SLA (Aux. Tecnico, mes fechado): faturamento = % dos pedidos da equipe
#     faturados em ate N dias uteis (1a NF no mes); entrega = % das NFs da
#     equipe do mes entregues ate a DT. PREVISTA (entregue depois ou
#     prevista vencida sem entrega = fora do prazo).
# =========================================================================
CH_LIBERADO, CH_BLOQUEADO = "LIBERADO", "BLOQUEADO"


def _ch_semanas(ano, mes):
    """As segundas-feiras das semanas do mes (a segunda dentro do mes)."""
    d = date(ano, mes, 1)
    d += timedelta(days=(7 - d.weekday()) % 7)
    saida = []
    while d.month == mes:
        saida.append(d)
        d += timedelta(days=7)
    return saida


def _categoria_e(categoria, alvo) -> bool:
    """(03/11) A categoria do produto e a da campanha? "PEÇAS" (o padrao do
    champions_config) vale para as tres linhas de pecas; uma linha so
    (ex. "PEÇAS LINHA MOTO") vale so para ela."""
    a, c = sem_acento(alvo).upper().strip(), sem_acento(categoria).upper()
    if a in ("PECAS", "PECA"):
        return c.startswith("PECAS")
    return c == a


def _ch_eventos(ctx, comp, equipes, cat_pecas, fora_lote):
    """Os aceleradores do mes, com a data da 1a vez:
    vend_novo[v][cli], sup_sku[s][cod], sup_pos[s][cli]; e (30/10,
    Alexandre) vend_un[v][dia] = UNIDADES de pecas vendidas pelo vendedor
    no dia da NF, liquidas de devolucao ("100 amortecedores = 500 pontos";
    antes era o codigo distinto no mes)."""
    ini = date(int(comp[:4]), int(comp[5:]), 1)
    liq_v_cod = defaultdict(float)
    liq_v_cli = defaultdict(float)
    liq_s_cod = defaultdict(float)
    liq_s_cli = defaultdict(float)
    prim_v_cod, prim_v_cli, prim_s_cod, prim_s_cli = {}, {}, {}, {}
    vend_un = defaultdict(lambda: defaultdict(float))   # (30/10)
    cat_ok = {}

    def eh_peca(cod):
        if cod not in cat_ok:
            cat_ok[cod] = _categoria_e(ctx.categoria_bap(cod), cat_pecas)
        return cat_ok[cod]
    ja_vendeu = defaultdict(set)          # equipe -> codigos antes do mes
    sup_de = {v: s for s, vs in equipes.items() for v in vs}

    def menor(dic, k, d):
        if d and (k not in dic or d < dic[k]):
            dic[k] = d
    for it in ctx.tabela["itens"]:
        t = it["tipo"]
        if t not in ("VND", "VEA", "DEV") or not it["dt_nf"]:
            continue
        v = _cod6(it["vend"]) if texto(it["vend"]) else ""
        s = sup_de.get(v)
        d = it["dt_nf"]
        if d < ini:
            if s and t != "DEV":
                ja_vendeu[s].add(it["cod"])
            continue
        if mes_de(d) != comp:
            continue
        val = -abs(it["valor"]) if t == "DEV" else it["valor"]
        if v and eh_peca(it["cod"]):
            q = abs(it.get("qtd") or 0)
            vend_un[v][d] += -q if t == "DEV" else q
        liq_v_cod[(v, it["cod"])] += val
        liq_v_cli[(v, it["cliente"])] += val
        if t != "DEV":
            menor(prim_v_cod, (v, it["cod"]), d)
            menor(prim_v_cli, (v, it["cliente"]), d)
        if s:
            liq_s_cod[(s, it["cod"])] += val
            liq_s_cli[(s, it["cliente"])] += val
            if t != "DEV":
                menor(prim_s_cod, (s, it["cod"]), d)
                menor(prim_s_cli, (s, it["cliente"]), d)
    cad = ctx.tabela.get("clientes") or {}
    vend_sku, vend_novo = defaultdict(dict), defaultdict(dict)
    sup_sku, sup_pos = defaultdict(dict), defaultdict(dict)
    for (v, cod), x in liq_v_cod.items():
        if x > 0.005 and (v, cod) in prim_v_cod and \
                _categoria_e(ctx.categoria_bap(cod), cat_pecas):
            vend_sku[v][cod] = prim_v_cod[(v, cod)]
    for (v, cli), x in liq_v_cli.items():
        dc = _dia((cad.get(cli) or {}).get("dtcad"))
        if x > 0.005 and dc and mes_de(dc) == comp and dc not in fora_lote \
                and (v, cli) in prim_v_cli:
            vend_novo[v][cli] = prim_v_cli[(v, cli)]
    for (s, cod), x in liq_s_cod.items():
        if x > 0.005 and cod not in ja_vendeu[s] and (s, cod) in prim_s_cod:
            sup_sku[s][cod] = prim_s_cod[(s, cod)]
    for (s, cli), x in liq_s_cli.items():
        if x > 0.005 and (s, cli) in prim_s_cli:
            sup_pos[s][cli] = prim_s_cli[(s, cli)]
    return ({v: dict(x) for v, x in vend_un.items()}, vend_novo, sup_sku,
            sup_pos)


def _ch_sla(ctx, comp, time_, dias_prazo):
    """(% faturados no prazo, pedidos, % entregues no prazo, entregas) da
    equipe no mes."""
    peds = {}
    for it in ctx.tabela["itens"]:
        if it["tipo"] not in ("VND", "VEA") or not it["dt_nf"]:
            continue
        if (_cod6(it["vend"]) if texto(it["vend"]) else "") not in time_:
            continue
        k = (it["filial"], it["pedido"])
        x = peds.setdefault(k, {"dtp": it["dt_pedido"], "nf": it["dt_nf"]})
        if it["dt_nf"] < x["nf"]:
            x["nf"] = it["dt_nf"]
    ok = n = 0
    for x in peds.values():
        if mes_de(x["nf"]) != comp or not x["dtp"]:
            continue
        dias = ctx.uteis(x["dtp"], x["nf"])
        if dias is None:
            continue
        n += 1
        ok += dias <= dias_prazo
    e_ok = e_n = 0
    try:
        ents = ctx.posvenda.get("entregas") or []
    except Exception:                                   # noqa: BLE001
        ents = []
    for e in ents:
        v = texto(e.get("vendedor")).split(" - ")[0].strip()
        if not v or _cod6(v) not in time_:
            continue
        dn = _dia(e.get("data_nf"))
        if not dn or mes_de(dn) != comp:
            continue
        prev, ent = _dia(e.get("prevista")), _dia(e.get("entregue_em"))
        if ent:
            e_n += 1
            e_ok += bool(prev is None or ent <= prev)
        elif prev and ctx.hoje > prev:
            e_n += 1                    # venceu e nao entregou: fora
    return (pct_de(ok, n) if n else None, n,
            pct_de(e_ok, e_n) if e_n else None, e_n)


def _tabela_relampago(ctx, cfg, ano, mes, jog_v, jog_s, equipes, nomes):
    """(28/10) A aba CAMPANHA RELAMPAGO do BAP Champions (ver
    bap_champions.PADRAO["relampago"])."""
    import bap_champions as bc                          # noqa: PLC0415
    dias = {}                      # dia -> campanha
    for c in cfg.get("relampago") or []:
        for d in c.get("dias") or []:
            try:
                d_ = date.fromisoformat(str(d)[:10])
            except ValueError:
                continue
            if d_.year == ano and d_.month == mes:
                dias[d_] = c
    ped = defaultdict(float)       # (vendedor, dia) -> R$ em pedidos
    bap = defaultdict(float)       # dia -> R$ da BAP inteira
    for it in ctx.tabela["itens"]:
        if it["tipo"] not in ("VND", "VEA"):
            continue
        d = _dia(it.get("dt_pedido"))
        if d not in dias:
            continue
        v = _cod6(it["vend"]) if texto(it["vend"]) else ""
        ped[(v, d)] += it["valor"] or 0.0
        bap[d] += it["valor"] or 0.0
    # quem vendeu nos dias e nao esta na equipe do Planner do mes (ex.:
    # codigo antigo) tambem joga, como FORA DO PLANNER [SUPOSICAO]; o
    # cadastro "fora do jogo" tira
    fora = {_cod6(x) for x in cfg.get("fora_do_jogo") or [] if texto(x)}
    extras = sorted({v for (v, _d), x in ped.items()
                     if v and x > 0.005 and v not in jog_v
                     and v not in jog_s and v not in fora})
    nomes = dict(nomes)
    for v in extras:
        nm = texto(ctx.vendedor(v))
        nomes[v] = nm.split(" - ", 1)[1] if " - " in nm else "(SEM NOME)"
    linhas = []
    # (30/10) os pontos de cada pessoa por campanha (o Resumo geral e o
    # Exportar campanha): (tipo, chave, nome da campanha) -> pontos
    por_quem = defaultdict(int)
    rot_quem = {}
    for d in sorted(dias):
        c = dias[d]
        bloco = bc.numero(c.get("bloco"), 4000.0) or 4000.0
        meta = bc.numero(c.get("meta_bap_dia"), 100000.0)
        bateu = bap[d] >= meta > 0
        des = "BATEU" if bateu else "NÃO BATEU"
        if ctx.hoje <= d:
            des = "EM ANDAMENTO" if ctx.hoje == d else "A JOGAR"
        for tipo, quem, valor, pts_b, bonus, sup in (
                [(bc.VENDEDOR, v, ped[(v, d)], c.get("pts_vendedor"),
                  c.get("bonus_vendedor"), l.get("supervisor") or "")
                 for v, l in jog_v.items()]
                + [(bc.VENDEDOR, v, ped[(v, d)], c.get("pts_vendedor"),
                    c.get("bonus_vendedor"), "(FORA DO PLANNER)")
                   for v in extras]
                # supervisor: a equipe + o que ele mesmo vendeu no codigo
                # dele [SUPOSICAO]
                + [(bc.SUPERVISOR, s_, sum(ped[(v, d)] for v in
                                            set(equipes.get(s_, ()))
                                            | {s_}),
                    c.get("pts_supervisor"), c.get("bonus_supervisor"),
                    nomes.get(s_, s_)) for s_ in jog_s]):
            blocos = int(max(valor, 0.0) // bloco)
            p_ped = blocos * bc.numero(pts_b)
            eleg = valor > 0.005
            p_des = bc.numero(bonus) if bateu and eleg and \
                ctx.hoje > d else 0.0
            linhas.append([d, texto(c.get("nome")), tipo,
                           _ch_rot(quem, nomes.get(quem, quem)), sup, valor,
                           blocos, round(p_ped), "SIM" if eleg else "NÃO",
                           bap[d], meta, des, round(p_des),
                           round(p_ped + p_des)])
            por_quem[(tipo, quem, texto(c.get("nome")))] += \
                round(p_ped + p_des)
            rot_quem[(tipo, quem)] = (nomes.get(quem, quem), sup)
    linhas.sort(key=lambda x: (x[0], x[2] != bc.VENDEDOR, -x[13], -x[5]))
    cols = [col("DIA", "data", 80), col("CAMPANHA", "texto", 160),
            col("TIPO", "texto", 92), col("NOME", "texto", 250),
            col("SUPERVISOR", "texto", 200),
            col("PEDIDOS NO DIA", "moeda", 110),
            col("BLOCOS", "int", 62), col("PTS PEDIDOS", "int", 86),
            col("VENDEU NO DIA", "texto", 92),
            col("BAP NO DIA", "moeda", 110), col("META BAP", "moeda", 100),
            col("DESAFIO", "texto", 110), col("PTS DESAFIO", "int", 86),
            col("PTS", "int", 72)]
    cols[11]["chip"] = {"BATEU": _VERD,
                        "NÃO BATEU": _VERM}

    def cartoes(ls):
        if not ls:
            return []
        por_dia = {}
        for x in ls:
            por_dia[x[0]] = (x[9], x[10], x[11])
        vend = [x for x in ls if x[2] == bc.VENDEDOR]
        acum = defaultdict(int)
        for x in vend:
            acum[x[3]] += x[13]
        lid = max(acum.items(), key=lambda kv: kv[1]) if acum else None
        return [
            kpi("BAP nos dias da campanha", moeda(sum(v[0] for v in
                                                  por_dia.values())),
                "neutro", " · ".join(f"{d:%d/%m} {moeda(v[0])} ({v[2]})"
                                     for d, v in sorted(por_dia.items()))),
            kpi("Desafio do dia", f"{sum(1 for v in por_dia.values() if v[2] == 'BATEU')}"
                f" de {len(por_dia)}", "ok" if any(
                    v[2] == "BATEU" for v in por_dia.values()) else "alerta",
                "meta " + " · ".join(moeda(v[1]) for v in
                                     por_dia.values())),
            kpi("Líder (vendedor)", _curto_pessoa(lid[0]) if lid else "—",
                "ok" if lid and lid[1] else "neutro",
                f"{br(lid[1])} pontos na campanha" if lid else ""),
            kpi("Pts da campanha", br(sum(x[13] for x in ls)), "neutro",
                f"vendedores {br(sum(x[13] for x in vend))} · supervisores "
                f"{br(sum(x[13] for x in ls if x[2] != bc.VENDEDOR))}")]
    t = tabela("Campanha relâmpago", cols, linhas,
               ["ok" if x[13] else "" for x in linhas],
               filtros=("DIA", "TIPO", "SUPERVISOR", "NOME", "DESAFIO"),
               kpis_de=cartoes,
               recortes=[("Só vendedores", lambda x: x[2] == bc.VENDEDOR),
                         ("Só supervisores",
                          lambda x: x[2] == bc.SUPERVISOR),
                         ("Com pontos", lambda x: x[13] > 0)],
               total=["TOTAL", "", "", "", "",
                      sum(x[5] for x in linhas if x[2] == bc.VENDEDOR),
                      sum(x[6] for x in linhas), sum(x[7] for x in linhas),
                      "", None, None, "", sum(x[12] for x in linhas),
                      sum(x[13] for x in linhas)] if linhas else None)
    t["_por_quem"], t["_rot_quem"] = dict(por_quem), rot_quem
    if not linhas:
        t["vazio"] = ("Nenhum dia de campanha relâmpago neste mês. Os dias "
                      "ficam em Parâmetros das campanhas › Campanha "
                      "relâmpago (a de 30 e 31/07/2026 está lá).")
    return t


def _ch_contatos(ctx, comp, cfg):
    """(30/10) CPF e e-mail de cada pessoa: o cadastro "colaboradores" do
    champions_config.json (por codigo ou nome; {"cpf", "email"}), depois o
    e-mail do Planner (o do mes e o atual). Sem CPF = em branco."""
    import json                                         # noqa: PLC0415
    por_cod, por_nome = {}, {}

    def norm(x):
        return sem_acento(texto(x)).upper().strip()
    cfgs = [ctx.raiz / "SISTEMA BAP" / "PLANNER_MESES" /
            f"planner_config_{comp}.json", ctx.raiz / "planner_config.json"]
    for arq in reversed(cfgs):           # o do mes por ultimo (manda)
        try:
            pc = json.loads(Path(arq).read_text("utf-8"))
        except (OSError, ValueError):
            continue
        for p_ in pc.get("pessoas") or []:
            em = texto(p_.get("email")).strip()
            if not em:
                continue
            if texto(p_.get("cod_protheus")):
                por_cod[_cod6(p_.get("cod_protheus"))] = {"email": em}
            por_nome[norm(p_.get("nome"))] = {"email": em}
    colab = cfg.get("colaboradores") or {}
    if isinstance(colab, list):
        colab = {texto(x.get("cod") or x.get("nome")): x for x in colab
                 if isinstance(x, dict)}
    cad_cod, cad_nome = {}, {}
    for k, x in colab.items():
        if not isinstance(x, dict):
            continue
        if texto(k).isdigit():
            cad_cod[_cod6(k)] = x
        cad_nome[norm(k)] = x
        if texto(x.get("nome")):
            cad_nome[norm(x.get("nome"))] = x

    def contato(cod, nome):
        c6 = _cod6(cod) if texto(cod).isdigit() else ""
        cad = cad_cod.get(c6) or cad_nome.get(norm(nome)) or {}
        pl = por_cod.get(c6) or por_nome.get(norm(nome)) or {}
        cpf = re.sub(r"\D", "", texto(cad.get("cpf")))
        return cpf, texto(cad.get("email")).strip() or pl.get("email", "")
    return contato


def _ch_resumo_geral(ctx, r, cfg, comp, resumo, t_rel):
    """(30/10, Alexandre) A aba RESUMO GERAL das Campanhas BAP (1a aba) e
    as linhas do EXPORTAR CAMPANHA. Uma linha por PESSOA (o mesmo nome em
    dois papeis - ex.: vendedor e supervisor - soma) [SUPOSICAO]. Pontos da
    Campanha BAP = os VALIDOS (liberados pela trava); da relampago = todos
    (independe da meta). No Excel: uma linha por pessoa e campanha, so com
    ponto; CNPJ sempre o da BAP; Valor = pontos."""
    import bap_champions as bc                          # noqa: PLC0415
    ano, mes = int(comp[:4]), int(comp[5:])
    mes_l = ("", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
             "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO",
             "DEZEMBRO")[mes]
    nome_bap = (f"CAMPANHA {texto(cfg.get('nome') or 'BAP CHAMPIONS')} - "
                f"{mes_l} {ano}").upper()
    contato = _ch_contatos(ctx, comp, cfg)
    pessoas = {}

    def chave_nome(nome):
        return sem_acento(texto(nome)).upper().strip()

    def pessoa(tipo, cod, nome, sup):
        k = chave_nome(nome) or f"{tipo}|{cod}"
        p_ = pessoas.setdefault(k, {"nome": texto(nome).upper(),
                                    "cods": [], "tipos": [], "sup": sup,
                                    "bap": 0, "valido": 0, "sits": [],
                                    "rel": defaultdict(int)})
        if tipo not in p_["tipos"]:
            p_["tipos"].append(tipo)
        if cod and cod not in p_["cods"]:
            p_["cods"].append(cod)
        if sup and not p_["sup"]:
            p_["sup"] = sup
        return p_
    for (tipo, _k), x in resumo.items():
        p_ = pessoa(tipo, x.get("cod"), x["nome"], x.get("sup"))
        if x.get("at") is not None and (p_.get("at") is None
                                        or tipo == bc.SUPERVISOR):
            p_["at"] = x["at"]
        p_["bap"] += x["bap"]
        p_["valido"] += x["valido"]
        p_["sits"].append(x["sit"])
    for (tipo, quem, camp), pts in ((t_rel or {}).get("_por_quem")
                                    or {}).items():
        nm, sup = (t_rel.get("_rot_quem") or {}).get((tipo, quem),
                                                     (quem, ""))
        if texto(nm) in ("", "(SEM NOME)", quem):
            nm = f"(SEM NOME - CÓD. {quem})"
        p_ = pessoa(tipo, quem if not str(quem).startswith(("SUP-", "?"))
                    else "", nm, sup if tipo == bc.VENDEDOR else "")
        p_["rel"][camp] += pts
    # (30/10, Alexandre) "visual mais executivo; sem a coluna TIPO, apenas
    # vendedor e supervisor": a tabela sai AGRUPADA por supervisor (a linha
    # do supervisor em azul e a equipe dele embaixo), nomes curtos (1o e
    # ultimo nome), % do desafio; CPF e e-mail ficam ocultos (vao so no
    # Exportar campanha).
    def curto(n):
        n = texto(n)
        return n if n.startswith("(") or not n else _curto_pessoa(n)
    linhas, export, grupos = [], [], defaultdict(list)
    for p_ in pessoas.values():
        cod = next((c for c in p_["cods"] if texto(c).isdigit()), "")
        cpf, email = contato(cod, p_["nome"])
        rel = sum(p_["rel"].values())
        sit = (CH_LIBERADO if CH_LIBERADO in p_["sits"] else
               CH_BLOQUEADO if p_["sits"] else "—")
        e_sup = bc.SUPERVISOR in p_["tipos"]
        sup_txt = texto(p_["sup"])
        if "FORA DO PLANNER" in sup_txt.upper():
            sup_txt = ""
        dono = p_["nome"] if e_sup else sup_txt
        # a linha do supervisor so com o nome dele na coluna SUPERVISOR; a
        # equipe embaixo so com o nome na coluna VENDEDOR (EQUIPE oculta,
        # para o filtro)
        if e_sup:
            equipe = curto(p_["nome"])
            sup_c, vend_c = equipe, ""
        else:
            equipe = curto(sup_txt) if sup_txt else "SEM SUPERVISOR"
            sup_c = ""
            vend_c = curto(p_["nome"]) + (" (AUX. TÉCNICO)"
                                          if bc.AUX in p_["tipos"] else "")
        lin = [sup_c, vend_c, p_.get("at"), sit, p_["bap"], p_["valido"],
               rel, p_["valido"] + rel, email, cpf, equipe]
        grupos[chave_nome(dono) or "~"].append((e_sup, lin))
        # (30/10, Alexandre) "junte as campanhas, coloque os nomes um do
        # lado do outro": UMA linha por pessoa no Exportar campanha, Valor =
        # soma das campanhas com ponto, Nome Acao = os nomes lado a lado
        partes = []
        if p_["valido"] > 0:
            partes.append((nome_bap, p_["valido"]))
        for camp, pts in sorted(p_["rel"].items()):
            if pts > 0:
                partes.append((f"{texto(camp) or 'CAMPANHA RELÂMPAGO'} - "
                               f"{mes_l} {ano}".upper(), pts))
        if partes:
            export.append([cpf, bc.CNPJ_EMPRESA, email, p_["nome"],
                           sum(v for _n, v in partes),
                           SEP_CAMPANHAS.join(n for n, _v in partes)])
    # os grupos: o de mais pontos a pagar primeiro; "sem supervisor" no fim;
    # dentro, o supervisor em cima e a equipe pelo total a pagar
    def ordem_grupo(item):
        k, ls = item
        return (k == "~" or k == chave_nome("SEM SUPERVISOR"),
                -sum(x[7] for _s, x in ls), k)
    tons = []
    for _k, ls in sorted(grupos.items(), key=ordem_grupo):
        for e_sup, x in sorted(ls, key=lambda y: (not y[0], -y[1][7],
                                                  -y[1][4], y[1][1])):
            linhas.append(x)
            tons.append("azul" if e_sup else ("ok" if x[7] > 0 else ""))
    export.sort(key=lambda x: (-x[4], x[3]))
    cols = [col("SUPERVISOR", "texto", 170), col("VENDEDOR", "texto", 210),
            col("% DESAFIO", "pct", 84), col("SITUAÇÃO", "texto", 104),
            col("PTS CAMPANHA BAP", "int", 128),
            col("PTS BAP VÁLIDOS", "int", 120),
            col("PTS RELÂMPAGO", "int", 112),
            col("TOTAL A PAGAR", "int", 116),
            col("E-MAIL", "texto", 230, oculta=True),
            col("CPF", "texto", 110, oculta=True),
            col("EQUIPE", "texto", 170, oculta=True)]
    cols[3]["chip"] = {CH_LIBERADO: _VERD,
                       CH_BLOQUEADO: _VERM}

    def cartoes(ls):
        if not ls:
            return []
        pagar = [x for x in ls if x[7] > 0]
        sem_mail = sum(1 for x in pagar if not x[8])
        sem_cpf = sum(1 for x in pagar if not x[9])
        return [
            kpi("Total a pagar (pontos)", br(sum(x[7] for x in ls)), "ok",
                f"{br(len(pagar))} pessoa(s) com ponto"),
            kpi("Campanha BAP (válidos)", br(sum(x[5] for x in ls)),
                "neutro", f"de {br(sum(x[4] for x in ls))} no jogo "
                          "(trava 80%)"),
            kpi("Campanha relâmpago", br(sum(x[6] for x in ls)), "neutro",
                "a cada bloco vendido, independe da meta"),
            kpi("Cadastro para exportar",
                "OK" if not (sem_mail or sem_cpf) else
                f"{br(sem_mail)} sem e-mail",
                "ok" if not sem_mail else "atencao",
                f"{br(sem_cpf)} sem CPF (vai em branco)")]
    t = tabela("Resumo geral", cols, linhas, tons,
               filtros=("EQUIPE", "SITUAÇÃO"),
               kpis_de=cartoes,
               recortes=[("Com pontos a pagar", lambda x: x[7] > 0),
                         ("Só liberados", lambda x: x[3] == CH_LIBERADO),
                         ("Sem e-mail", lambda x: x[7] > 0 and not x[8])],
               total=["TOTAL", "", None, "", sum(x[4] for x in linhas),
                      sum(x[5] for x in linhas), sum(x[6] for x in linhas),
                      sum(x[7] for x in linhas), "", "", ""]
               if linhas else None)
    # (30/10, Alexandre) "ridiculo esse resumo geral": a aba saiu; os pontos
    # da relampago e o TOTAL A PAGAR ficam nas abas Vendedores e
    # Supervisores. O fechamento continua no Exportar campanha.
    del t
    r["campanha_export"] = {"comp": comp, "linhas": export,
                            "nome_bap": nome_bap}
    if any(not x[2] for x in export):
        r["avisos"].append(
            "Exportar campanha: " + ", ".join(sorted({x[3] for x in export
                                                      if not x[2]}))
            + " sem e-mail no Planner (o E-mail é obrigatório na planilha "
            "da premiação).")


# (30/10) os nomes das campanhas lado a lado na coluna Nome Acao
SEP_CAMPANHAS = " + "

CAB_CAMPANHA = ["CPF", "CNPJ Empresa*", "E-mail*", "Nome", "Valor*",
                "Nome Ação"]


def exportar_campanha(rel: dict, destino) -> Path:
    """(30/10, Alexandre) EXPORTAR CAMPANHA: o Excel no formato da planilha
    da premiacao - linha 1 "Valor total" (soma), linha 2 o cabecalho
    (CPF, CNPJ Empresa*, E-mail*, Nome, Valor*, Nome Acao) e uma linha por
    pessoa e campanha (Valor = pontos; CPF vazio quando nao ha)."""
    from openpyxl import Workbook                       # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
    ex = rel.get("campanha_export") or {}
    ls = ex.get("linhas") or []
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Campanha"
    roxo = PatternFill("solid", fgColor="5B1F6E")
    rosa = PatternFill("solid", fgColor="E5007E")
    branco = Font(color="FFFFFF", bold=True)
    ws.cell(1, 4, "Valor total").alignment = Alignment(horizontal="right")
    n_fim = 2 + max(len(ls), 1)
    tot = ws.cell(1, 5, f"=SUM(E3:E{n_fim})")
    tot.number_format = "#,##0.00"
    tot.alignment = Alignment(horizontal="center")
    for j, nome in enumerate(CAB_CAMPANHA, start=1):
        c = ws.cell(2, j, nome)
        c.fill, c.font = roxo, branco
        c.alignment = Alignment(horizontal="center")
    for i, x in enumerate(ls, start=3):
        cpf, cnpj, email, nome, valor, acao = x
        ws.cell(i, 1, cpf or None).number_format = "@"
        ws.cell(i, 2, cnpj).number_format = "@"
        ws.cell(i, 3, email or None)
        ws.cell(i, 4, nome)
        cv = ws.cell(i, 5, int(round(valor)))
        cv.fill, cv.font = rosa, Font(color="FFFFFF")
        cv.alignment = Alignment(horizontal="center")
        ws.cell(i, 6, acao)
        for j in (1, 2):
            ws.cell(i, j).alignment = Alignment(horizontal="center")
    for j, w in enumerate((16, 20, 40, 44, 12, 74), start=1):
        ws.column_dimensions["ABCDEF"[j - 1]].width = w
    ws.freeze_panes = "A3"
    wb.save(destino)
    return destino


def _ch_rot(chave, nome) -> str:
    """"000034 - ANDERSON"; a chave da equipe do mes cadastrada a mao
    (SUP-<nome> / ?<nome>) mostra so o nome (sem codigo: "(SEM CÓD.)")."""
    chave, nome = texto(chave), texto(nome)
    if chave.startswith("SUP-"):
        return nome or chave[4:]
    if chave.startswith("?"):
        return f"(SEM CÓD.) - {nome or chave[1:]}"
    return f"{chave} - {nome}" if nome and nome != chave else chave


def _ch_equipe_manual(linhas):
    """(lin_s, lin_v) no formato das linhas do Farol de Metas, a partir da
    equipe do mes cadastrada a mao. Supervisor: chave "SUP-<NOME>", meta =
    soma da equipe. Vendedor sem codigo: chave "?<NOME>" (sem venda)."""
    import bap_champions as bc                          # noqa: PLC0415
    lin_s, lin_v = {}, {}
    for x in linhas:
        sup = texto(x.get("supervisor")).strip().upper() or "(SEM SUPERVISOR)"
        ks = "SUP-" + sem_acento(sup).upper()
        s = lin_s.setdefault(ks, {"codigo": ks, "nome": sup, "meta": 0.0})
        meta = bc.moeda(x.get("meta"), 0.0) or 0.0
        s["meta"] += meta
        nome = texto(x.get("vendedor")).strip().upper()
        cod = _cod6(x.get("cod")) if texto(x.get("cod")) and \
            texto(x.get("cod")).strip("#") else ""
        kv = cod or "?" + sem_acento(nome)[:24]
        lin_v[kv] = {"codigo": kv, "nome": nome, "supervisor": sup,
                     "cod_supervisor": ks, "meta": meta,
                     "regiao": texto(x.get("regiao"))}
    for s in lin_s.values():
        s["meta"] = s["meta"] or None
    return lin_s, lin_v


def bap_champions(ctx):
    import bap_champions as bc                          # noqa: PLC0415
    cfg = bc.ler(ctx.raiz)
    ano, mes = periodo(ctx)
    aviso_mes = ""
    if not mes:
        mes, aviso_mes = ctx.hoje.month, "TODOS OS MESES não vale no jogo: " \
            "mostrando o mês atual."
    comp = f"{ano}-{mes:02d}"
    ult = (date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1))
    fechado = ctx.hoje > ult
    r = novo("vc_champions", VEN, cfg.get("nome") or "BAP CHAMPIONS",
             f"{rotulo_mes(comp)} · "
             + ("mês fechado" if fechado else
                f"parcial até {min(ctx.hoje, ult):%d/%m}"),
             "TABELA_BAP (faturamento) + Farol de Metas (desafio comercial e equipe) "
             "+ champions_config.json")
    anos = anos_dos_dados(ctx)
    r["parametros"] = [
        {"nome": "MÊS", "valores": [(m, MESES[m]) for m in range(1, 13)],
         "valor": mes},
        {"nome": "ANO", "valores": [(a, str(a)) for a in sorted(
            set(anos) | {ano})], "valor": ano}]
    if aviso_mes:
        r["avisos"].append(aviso_mes)
    ctx.params["MÊS"], ctx.params["ANO"] = mes, ano
    dados = meta_do_periodo(ctx)
    ac = dados["acomp"]
    fora = {_cod6(x) for x in cfg.get("fora_do_jogo") or [] if texto(x)}
    # (28/10) so quem esta no Planner do mes: sem o supervisor vago e sem
    # os "(FORA DO PLANNER)" (codigo que vendeu sem estar na equipe)
    def _no_jogo(l):
        nome_ = texto(l.get("nome")).upper()
        return bool(texto(l.get("codigo"))) and not l.get("fora_do_planner") \
            and "VAGO" not in nome_ and "FORA DO PLANNER" not in nome_
    lin_s = {l["codigo"]: l for l in ac["recortes"].get("supervisor", [])
             if _no_jogo(l)}
    lin_v = {l["codigo"]: l for l in ac["recortes"].get("vendedor", [])
             if _no_jogo(l)}
    # (28/10, Alexandre) mes com EQUIPE E METAS cadastradas a mao
    # (Parametros > Equipe do mes): vale ela, no lugar do Planner/Gerador
    manual = (cfg.get("equipes_mes") or {}).get(comp) or []
    if manual:
        lin_s, lin_v = _ch_equipe_manual(manual)
        r["avisos"].append(
            f"Equipe e metas de {rotulo_mes(comp)} do cadastro (Parâmetros "
            f"das campanhas › Equipe do mês): {len(lin_v)} vendedor(es), "
            f"{len(lin_s)} supervisor(es); meta do supervisor = soma da "
            f"equipe.")
    equipes = {s: {v for v, l in lin_v.items()
                   if l.get("cod_supervisor") == s} for s in lin_s}
    jog_v = {v: l for v, l in lin_v.items()
             if l.get("cod_supervisor") in lin_s and v not in fora}
    jog_s = {s: l for s, l in lin_s.items() if s not in fora}
    ppm = cfg["pontos_por_mil"]
    av, asu, aa = cfg["acel_vendedor"], cfg["acel_supervisor"], cfg["acel_aux"]
    trava = bc.numero(cfg["trava_pct"], 80.0)
    bonus = bc.numero(cfg["bonus_confronto"], 200.0)
    # ---- faturamento por dia (vendedor) e os aceleradores
    semanas = _ch_semanas(ano, mes)
    de = min([date(ano, mes, 1)] + semanas)
    ate = max([ult] + [s + timedelta(days=6) for s in semanas])
    fat_dia = defaultdict(float)
    # (28/10, Alexandre) bruto e devolucoes separados, para transparencia
    bruto_dia, dev_dia = defaultdict(float), defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["tipo"] not in ("VND", "VEA", "DEV") or not it["dt_nf"] \
                or not de <= it["dt_nf"] <= ate:
            continue
        v = _cod6(it["vend"]) if texto(it["vend"]) else ""
        if it["tipo"] == "DEV":
            fat_dia[(v, it["dt_nf"])] -= abs(it["valor"])
            dev_dia[(v, it["dt_nf"])] -= abs(it["valor"])
        else:
            fat_dia[(v, it["dt_nf"])] += it["valor"]
            bruto_dia[(v, it["dt_nf"])] += it["valor"]
    eventos = {}
    for c_ in sorted({mes_de(de), comp, mes_de(ate)}):
        eventos[c_] = _ch_eventos(ctx, c_, equipes, cfg["categoria_pecas"],
                                  lote_fora(ctx))
    ev_v_un, ev_v_novo, ev_s_sku, ev_s_pos = eventos[comp]

    def un_pecas(dic_por_mes, quem, a, b):
        """(30/10) unidades de pecas do vendedor de a ate b (liquidas de
        devolucao; nunca negativo) [SUPOSICAO]."""
        return max(0, round(sum(q for evs in dic_por_mes.values()
                                for d, q in evs[0].get(quem, {}).items()
                                if a <= d <= b)))

    def fat(cods, a, b, dic=None):
        return sum(x for (v, d), x in (fat_dia if dic is None else
                                       dic).items()
                   if v in cods and a <= d <= b)

    def bruto_dev(cods):
        """(bruto, devolucoes) do mes - a devolucao em negativo."""
        a_, b_ = date(ano, mes, 1), ult
        return fat(cods, a_, b_, bruto_dia), fat(cods, a_, b_, dev_dia)

    def n_ev(dic_por_mes, idx, quem, a, b):
        return sum(1 for c_, evs in dic_por_mes.items()
                   for d in evs[idx].get(quem, {}).values() if a <= d <= b)

    def pts_fat(valor, papel):
        return max(valor, 0.0) / 1000.0 * bc.numero(ppm.get(papel), 0.0)

    def pts_semana(tipo, quem, seg):
        dom = seg + timedelta(days=6)
        if tipo == bc.SUPERVISOR:
            return (pts_fat(fat(equipes.get(quem, set()), seg, dom),
                            bc.SUPERVISOR)
                    + n_ev(eventos, 2, quem, seg, dom)
                    * bc.numero(asu["sku_novo"])
                    + n_ev(eventos, 3, quem, seg, dom)
                    * bc.numero(asu["positivado"]))
        return (pts_fat(fat({quem}, seg, dom), bc.VENDEDOR)
                + un_pecas(eventos, quem, seg, dom)
                * bc.numero(av["sku_pecas"])
                + n_ev(eventos, 1, quem, seg, dom)
                * bc.numero(av["cliente_novo"]))
    # ---- os confrontos das semanas do mes
    nomes = {**{v: l.get("nome") or v for v, l in lin_v.items()},
             **{s: l.get("nome") or s for s, l in lin_s.items()}}
    vitorias = Counter()
    lin_j = []
    for j in cfg.get("jogos") or []:
        try:
            seg = date.fromisoformat(str(j.get("semana"))[:10])
        except ValueError:
            continue
        if seg not in semanas:
            continue
        tipo = texto(j.get("tipo")).upper() or bc.VENDEDOR
        a, b = _cod6(j.get("a")), _cod6(j.get("b"))
        pa, pb_ = pts_semana(tipo, a, seg), pts_semana(tipo, b, seg)
        dom = seg + timedelta(days=6)
        if ctx.hoje <= dom:
            res = "EM ANDAMENTO" if ctx.hoje >= seg else "A JOGAR"
        elif round(pa) == round(pb_):
            res = "EMPATE"
        else:
            g = a if pa > pb_ else b
            vitorias[g] += 1
            res = f"VITÓRIA: {_curto_pessoa(nomes.get(g, g))}"
        lin_j.append([f"{seg:%d/%m} a {dom:%d/%m}", tipo,
                      _ch_rot(a, nomes.get(a, a)), round(pa),
                      _ch_rot(b, nomes.get(b, b)), round(pb_), res])

    def situacao(real, meta):
        at = pct_de(real, meta) if meta else None
        return at, (CH_LIBERADO if at is not None and at >= trava
                    else CH_BLOQUEADO)
    # (30/10, Alexandre) "cade os pontos da campanha relampago na aba
    # vendedores e supervisores?": a relampago e calculada antes, para as
    # colunas PTS RELAMPAGO e TOTAL A PAGAR (validos + relampago)
    t_rel, erro_rel = None, None
    try:
        t_rel = _tabela_relampago(ctx, cfg, ano, mes, jog_v, jog_s, equipes,
                                  nomes)
    except Exception as erro:                           # noqa: BLE001
        erro_rel = erro
    rel_de = defaultdict(int)
    for (tp_, quem_, _c), pts_ in ((t_rel or {}).get("_por_quem")
                                   or {}).items():
        rel_de[(tp_, quem_)] += pts_
    # ---- vendedores
    resumo = {}             # (30/10) (tipo, chave) -> pontos do mes
    lin_vend = []
    for v, l in jog_v.items():
        f_ = fat({v}, date(ano, mes, 1), ult)
        at, sit = situacao(f_, l.get("meta"))
        n_sku = un_pecas({comp: eventos[comp]}, v, date(ano, mes, 1), ult)
        n_novo = len(ev_v_novo.get(v, {}))
        p_f = pts_fat(f_, bc.VENDEDOR)
        p_s = n_sku * bc.numero(av["sku_pecas"])
        p_n = n_novo * bc.numero(av["cliente_novo"])
        p_b = vitorias[v] * bonus
        tot = round(p_f + p_s + p_n + p_b)
        resumo[(bc.VENDEDOR, v)] = {
            "nome": texto(l.get("nome")) or v, "cod": v,
            "sup": l.get("supervisor") or "", "bap": tot, "sit": sit,
            "at": at, "valido": tot if sit == CH_LIBERADO else 0}
        rot_v = _ch_rot(v, l.get("nome"))     # (30/10) nome curto
        if " - " in rot_v and rot_v.split(" - ", 1)[0].isdigit():
            rot_v = f"{v} - {_curto_pessoa(rot_v)}"
        sup_v = texto(l.get("supervisor"))
        lin_vend.append([0, rot_v,
                         _curto_pessoa(sup_v) if sup_v and not
                         sup_v.startswith("(") else sup_v,
                         *bruto_dev({v}), f_,
                         l.get("meta"),
                         at, sit, round(p_f), n_sku, round(p_s), n_novo,
                         round(p_n), vitorias[v], round(p_b), tot,
                         tot if sit == CH_LIBERADO else 0,
                         rel_de[(bc.VENDEDOR, v)],
                         (tot if sit == CH_LIBERADO else 0)
                         + rel_de[(bc.VENDEDOR, v)]])
    # ---- supervisores
    lin_sup = []
    for s, l in jog_s.items():
        f_ = fat(equipes.get(s, set()), date(ano, mes, 1), ult)
        at, sit = situacao(f_, l.get("meta"))
        n_sku, n_pos = len(ev_s_sku.get(s, {})), len(ev_s_pos.get(s, {}))
        p_f = pts_fat(f_, bc.SUPERVISOR)
        p_s = n_sku * bc.numero(asu["sku_novo"])
        p_p = n_pos * bc.numero(asu["positivado"])
        p_b = vitorias[s] * bonus
        tot = round(p_f + p_s + p_p + p_b)
        resumo[(bc.SUPERVISOR, s)] = {
            "nome": texto(l.get("nome")) or s, "cod": s, "sup": "",
            "bap": tot, "sit": sit, "at": at,
            "valido": tot if sit == CH_LIBERADO else 0}
        lin_sup.append([0, _curto_pessoa(l.get("nome")) if l.get("nome")
                        else s,
                        len(equipes.get(s, ())),
                        *bruto_dev(equipes.get(s, set())), f_,
                        l.get("meta"), at,
                        sit, round(p_f), n_sku, round(p_s), n_pos,
                        round(p_p), vitorias[s], round(p_b), tot,
                        tot if sit == CH_LIBERADO else 0,
                        rel_de[(bc.SUPERVISOR, s)],
                        (tot if sit == CH_LIBERADO else 0)
                        + rel_de[(bc.SUPERVISOR, s)]])
    # ---- Aux. Tecnico (o supervisor que ele apoia)
    lin_aux = []
    for x in cfg.get("aux") or []:
        s = _cod6(x.get("supervisor")) if texto(x.get("supervisor")) else ""
        l = lin_s.get(s)
        nome = texto(x.get("nome"))
        if not l:
            lin_aux.append([0, nome, "(escolher o supervisor)", None, None,
                            None, None, None, CH_BLOQUEADO, 0, None, 0, None,
                            0, 0, 0])
            continue
        f_ = fat(equipes.get(s, set()), date(ano, mes, 1), ult)
        at, sit = situacao(f_, l.get("meta"))
        sf, nf_, se, ne = _ch_sla(
            ctx, comp, equipes.get(s, set()),
            int(bc.numero(cfg["sla_faturamento_dias"], 2)))
        p_f = pts_fat(f_, bc.AUX)
        p_sf = bc.numero(aa["sla_faturamento"]) if fechado and sf is not None \
            and sf >= bc.numero(cfg["sla_faturamento_meta_pct"]) else 0.0
        p_se = bc.numero(aa["sla_entrega"]) if fechado and se is not None \
            and se >= bc.numero(cfg["sla_entrega_meta_pct"]) else 0.0
        tot = round(p_f + p_sf + p_se)
        resumo[(bc.AUX, nome)] = {
            "nome": nome, "cod": "", "sup": texto(l.get("nome")),
            "bap": tot, "sit": sit, "at": at,
            "valido": tot if sit == CH_LIBERADO else 0}
        lin_aux.append([0, nome, _curto_pessoa(l.get("nome")),
                        *bruto_dev(equipes.get(s, set())), f_,
                        l.get("meta"), at, sit, round(p_f), sf, round(p_sf),
                        se, round(p_se), tot,
                        tot if sit == CH_LIBERADO else 0])

    def ranquear(ls, i_val, i_tot):
        ls.sort(key=lambda x: (-(x[i_val] or 0), -(x[i_tot] or 0), x[1]))
        for i, x in enumerate(ls, 1):
            x[0] = i
    ranquear(lin_vend, 19, 16)          # (30/10) pelo TOTAL A PAGAR
    ranquear(lin_sup, 19, 16)
    ranquear(lin_aux, 15, 14)

    def tons(ls, i_sit):
        return ["ok" if x[i_sit] == CH_LIBERADO else "" for x in ls]
    chip_sit = {CH_LIBERADO: _VERD,
                CH_BLOQUEADO: _VERM}
    cols_pessoa = [col("POS.", "int", 46)]
    cols_ating = [col("FAT. BRUTO", "moeda", 105),
                  col("DEVOLUÇÕES", "moeda", 100),
                  col("FAT. LÍQUIDO", "moeda", 110),
                  col("DESAFIO", "moeda", 100), col("% DESAFIO", "pct", 70),
                  col("SITUAÇÃO", "texto", 92),
                  col("PTS FATUR.", "int", 82)]
    cols_v = cols_pessoa + [col("VENDEDOR", "texto", 240),
                            col("SUPERVISOR", "texto", 200)] + cols_ating + [
        col("PEÇAS (UN.)", "int", 82), col("PTS PEÇAS", "int", 76),
        col("CLI. NOVOS", "int", 76), col("PTS CLI. NOVO", "int", 92),
        col("VITÓRIAS", "int", 66), col("PTS BÔNUS", "int", 76),
        col("PTS", "int", 72), col("PTS VÁLIDOS", "int", 100),
        col("PTS RELÂMPAGO", "int", 100), col("TOTAL A PAGAR", "int", 104)]
    cols_s = cols_pessoa + [col("SUPERVISOR", "texto", 260),
                            col("VENDEDORES", "int", 84)] + cols_ating + [
        col("SKU NOVOS", "int", 76), col("PTS SKU NOVO", "int", 90),
        col("POSITIVADOS", "int", 84), col("PTS POSIT.", "int", 76),
        col("VITÓRIAS", "int", 66), col("PTS BÔNUS", "int", 76),
        col("PTS", "int", 72), col("PTS VÁLIDOS", "int", 100),
        col("PTS RELÂMPAGO", "int", 100), col("TOTAL A PAGAR", "int", 104)]
    cols_a = cols_pessoa + [col("AUX. TÉCNICO", "texto", 200),
                            col("APOIA (SUPERVISOR)", "texto", 260)] + \
        cols_ating + [
        col("SLA FATUR. %", "pct", 86), col("PTS SLA FATUR.", "int", 96),
        col("SLA ENTREGA %", "pct", 92), col("PTS SLA ENTREGA", "int", 104),
        col("PTS", "int", 72), col("PTS VÁLIDOS", "int", 100)]
    for cs in (cols_v, cols_s, cols_a):
        cs[[c["nome"] for c in cs].index("SITUAÇÃO")]["chip"] = chip_sit

    def cartoes_de(ls, papel, i_tot, i_val, i_sit, i_pag=None):
        if not ls:
            return []
        lid = ls[0]
        lib = sum(1 for x in ls if x[i_sit] == CH_LIBERADO)
        ks = [
            kpi(f"Líder ({papel})", _curto_pessoa(lid[1]), "ok",
                f"{br(lid[i_val])} pontos válidos · {br(lid[i_tot])} no "
                f"total"),
            kpi("Pts liberados", f"{br(lib)} de {br(len(ls))}",
                "ok" if lib else "alerta",
                f"atingiu ≥ {br(trava)}% do desafio comercial"),
            kpi("Pts no jogo", br(sum(x[i_tot] for x in ls)), "neutro",
                f"{br(sum(x[i_val] for x in ls))} válidos")]
        if i_pag is not None:
            ks.append(kpi("Total a pagar", br(sum(x[i_pag] or 0 for x in ls)),
                          "ok", f"válidos + {br(sum(x[i_pag - 1] or 0 for x in ls))}"
                                f" da relâmpago"))
        return ks
    rec_lib = [("Só LIBERADOS", lambda x: x[8] == CH_LIBERADO),
               ("Só BLOQUEADOS", lambda x: x[8] == CH_BLOQUEADO)]
    r["tabelas"].append(tabela(
        "Vendedores", cols_v, lin_vend, tons(lin_vend, 8),
        filtros=("SUPERVISOR", "SITUAÇÃO"),
        kpis_de=lambda ls: cartoes_de(ls, "vendedor", 16, 17, 8, 19),
        recortes=rec_lib,
        total=(["", "TOTAL", ""] + [sum(x[j] or 0 for x in lin_vend)
                                    for j in (3, 4, 5, 6)] + [None, ""]
               + [sum(x[j] or 0 for x in lin_vend) for j in range(9, 20)])
        if lin_vend else None))
    r["tabelas"].append(tabela(
        "Supervisores", cols_s, lin_sup, tons(lin_sup, 8),
        filtros=("SITUAÇÃO",),
        kpis_de=lambda ls: cartoes_de(ls, "supervisor", 16, 17, 8, 19),
        recortes=rec_lib,
        total=(["", "TOTAL", sum(x[2] or 0 for x in lin_sup)]
               + [sum(x[j] or 0 for x in lin_sup) for j in (3, 4, 5, 6)]
               + [None, ""]
               + [sum(x[j] or 0 for x in lin_sup) for j in range(9, 20)])
        if lin_sup else None))
    r["tabelas"].append(tabela(
        "Aux. Técnico", cols_a, lin_aux, tons(lin_aux, 8),
        filtros=("APOIA (SUPERVISOR)", "SITUAÇÃO"),
        kpis_de=lambda ls: cartoes_de(ls, "Aux. Técnico", 14, 15, 8)))
    # ---- confrontos e pontos por semana
    cols_j = [col("SEMANA", "texto", 110), col("TIPO", "texto", 96),
              col("JOGADOR A", "texto", 260), col("PTS A", "int", 70),
              col("JOGADOR B", "texto", 260), col("PTS B", "int", 70),
              col("RESULTADO", "texto", 240)]
    t_j = tabela("Confrontos", cols_j, lin_j,
                 ["ok" if x[6].startswith("VITÓRIA") else "" for x in lin_j],
                 filtros=("SEMANA", "TIPO", "RESULTADO"))
    if not lin_j:
        t_j["vazio"] = ("Nenhum jogo cadastrado nas semanas deste mês. "
                        "Cadastre em Parâmetros das campanhas › Confrontos.")
    r["tabelas"].append(t_j)
    rot_sem = [f"{s:%d/%m}" for s in semanas]
    cols_ps = [col("TIPO", "texto", 96), col("JOGADOR", "texto", 280)] + [
        col(f"SEM. {x}", "int", 82) for x in rot_sem] + [
        col("SOMA DAS SEMANAS", "int", 120)]
    lin_ps = []
    for tipo, quem in ([(bc.VENDEDOR, v) for v in jog_v]
                       + [(bc.SUPERVISOR, s) for s in jog_s]):
        pts = [round(pts_semana(tipo, quem, s_)) for s_ in semanas]
        lin_ps.append([tipo, _ch_rot(quem, nomes.get(quem, quem))] + pts
                      + [sum(pts)])
    lin_ps.sort(key=lambda x: (x[0] != bc.VENDEDOR, -x[-1]))
    r["tabelas"].append(tabela(
        "Pts por semana", cols_ps, lin_ps, filtros=("TIPO",)))
    # ---- (28/10, Alexandre) CAMPANHA RELAMPAGO: os dias da campanha no
    # mes. PEDIDOS do dia = itens VND (faturado) e VEA (em aberto) pela
    # DATA DO PEDIDO, por quem vendeu; excluidos e devolucoes fora
    # [SUPOSICAO]. A cada R$ X completos: vendedor e supervisor (equipe).
    # Desafio do dia: a BAP inteira (todos os vendedores) >= a meta do dia.
    # Elegivel = vendeu no dia (supervisor: a equipe vendeu) [SUPOSICAO].
    # Pontos a parte (troca pontos): nao entram no placar do Champions.
    if t_rel is not None:
        r["tabelas"].append(t_rel)
    elif erro_rel is not None:
        r["avisos"].append(f"Campanha relâmpago: {erro_rel}")
    # ---- (30/10, Alexandre) RESUMO GERAL: os pontos da Campanha BAP
    # (validos) e da Campanha relampago, por pessoa - o fechamento - e o
    # que vai no EXPORTAR CAMPANHA (Excel no formato da premiacao)
    try:
        _ch_resumo_geral(ctx, r, cfg, comp, resumo, t_rel)
    except Exception as erro:                           # noqa: BLE001
        r["avisos"].append(f"Resumo geral: {erro}")
    # ---- as regras em vigor (o cadastro)
    reg = [
        ["FATURAMENTO", "Vendedor · a cada R$ 1.000 vendidos",
         bc.numero(ppm.get(bc.VENDEDOR))],
        ["FATURAMENTO", "Supervisor · a cada R$ 1.000 da equipe",
         bc.numero(ppm.get(bc.SUPERVISOR))],
        ["FATURAMENTO", "Aux. Técnico · a cada R$ 1.000 da equipe apoiada",
         bc.numero(ppm.get(bc.AUX))],
        ["CONFRONTO", "Vitória no confronto da semana (vendedor e "
                      "supervisor)", bonus],
        ["ACELERADOR VENDEDOR", "Peça vendida · por unidade (líquida de "
                                "devolução)", bc.numero(av["sku_pecas"])],
        ["ACELERADOR VENDEDOR", "Cliente novo com pedido",
         bc.numero(av["cliente_novo"])],
        ["ACELERADOR SUPERVISOR", "SKU novo vendido pela equipe",
         bc.numero(asu["sku_novo"])],
        ["ACELERADOR SUPERVISOR", "Cliente positivado pela equipe",
         bc.numero(asu["positivado"])],
        ["ACELERADOR AUX. TÉCNICO", "SLA de entrega (mês fechado; ≥ "
         f"{br(bc.numero(cfg['sla_entrega_meta_pct']))}% no prazo)",
         bc.numero(aa["sla_entrega"])],
        ["ACELERADOR AUX. TÉCNICO", "SLA de faturamento (mês fechado; ≥ "
         f"{br(bc.numero(cfg['sla_faturamento_meta_pct']))}% em até "
         f"{int(bc.numero(cfg['sla_faturamento_dias']))} dias úteis)",
         bc.numero(aa["sla_faturamento"])],
        ["TRAVA", f"Atingiu ≥ {br(trava)}% do desafio comercial → pontos LIBERADOS; "
                  f"abaixo → BLOQUEADOS", None]]
    r["tabelas"].append(tabela(
        "Regras", [col("GRUPO", "texto", 200), col("REGRA", "texto", 520),
                   col("PTS", "int", 80)], reg))
    # ---- a visao geral
    top = lin_vend[:12]
    if top:
        r["graficos"].append({
            "titulo": "Pts por vendedor (total e válidos)",
            "rotulos": [_curto_pessoa(x[1]) for x in top],
            "series": [{"nome": "pontos", "cor": AZUL,
                        "valores": [x[16] for x in top]},
                       {"nome": "válidos", "cor": VERDE,
                        "valores": [x[17] for x in top]}],
            "formato": "num", "largo": True})
        r["graficos"].append({
            "titulo": f"% do desafio comercial (trava {br(trava)}%)",
            "rotulos": [_curto_pessoa(x[1]) for x in top],
            "series": [{"nome": "% meta", "cor": VERDE,
                        "valores": [x[7] or 0 for x in top]}],
            "formato": "pct", "meta": trava})
    if lin_sup:
        r["graficos"].append({
            "titulo": "Pts por supervisor (total e válidos)",
            "rotulos": [_curto_pessoa(x[1]) for x in lin_sup],
            "series": [{"nome": "pontos", "cor": AZUL,
                        "valores": [x[16] for x in lin_sup]},
                       {"nome": "válidos", "cor": VERDE,
                        "valores": [x[17] for x in lin_sup]}],
            "formato": "num"})
    # (30/10, Alexandre) "diminua o tamanho das fontes para caber tudo na
    # tela": letra 8 em todas as tabelas das Campanhas
    for t_ in r["tabelas"]:
        t_.setdefault("letra", 8)
    r["kpis"] = (cartoes_de(lin_vend, "vendedor", 16, 17, 8)[:1]
                 + cartoes_de(lin_sup, "supervisor", 16, 17, 8)[:1]
                 + [kpi("Liberados", f"{br(sum(1 for x in lin_vend + lin_sup if x[8] == CH_LIBERADO))}"
                        f" de {br(len(lin_vend) + len(lin_sup))}", "neutro",
                        f"vendedores e supervisores ≥ {br(trava)}% do desafio comercial"),
                    kpi("Confrontos", br(len(lin_j)), "neutro",
                        f"{br(sum(vitorias.values()))} vitória(s) no mês")])
    r["avisos"].append(
        "FAT. BRUTO = vendas (VND/VEA); DEVOLUÇÕES = notas de devolução, em "
        "negativo; FAT. LÍQUIDO = bruto + devoluções. Faturamento = líquido "
        "(venda − devolução) pela data da NF, por quem "
        "vendeu (a mesma conta da RV). Pontos proporcionais aos R$ 1.000. "
        "Semana do confronto = segunda a domingo; decidida depois do domingo.")
    if not fechado:
        r["avisos"].append(
            "Mês em andamento: LIBERADO/BLOQUEADO é pelo faturamento até hoje "
            "e os SLAs do Aux. Técnico só pontuam no mês fechado.")
    sem_sup = [texto(x.get("nome")) for x in cfg.get("aux") or []
               if not texto(x.get("supervisor"))]
    if sem_sup:
        r["avisos"].append("Aux. Técnico sem supervisor (sem pontos): "
                           + ", ".join(sem_sup) + ". Escolha em Parâmetros "
                           "das campanhas.")
    if cfg.get("alterado_em"):
        r["avisos"].append(f"Parâmetros alterados em {cfg['alterado_em']}"
                           + (f" por {cfg['alterado_por']}"
                              if cfg.get("alterado_por") else ""))
    r["_champions"] = {
        "vendedores": [(v, l.get("nome")) for v, l in sorted(
            lin_v.items(), key=lambda x: texto(x[1].get("nome")))
            if l.get("cod_supervisor") in lin_s],
        "supervisores": [(s, l.get("nome")) for s, l in sorted(
            lin_s.items(), key=lambda x: texto(x[1].get("nome")))],
        "semanas": semanas, "competencia": comp}
    return r


CATALOGO = [
    ("pv_pedidos", PRE, "Farol de Pedidos", farol_pedidos),
    ("pv_indicadores", PRE, "Painel de indicadores", painel_indicadores),
    ("farol_pv", PRE, "Farol DDR", lambda c: farol(c, "Juliana Almeida", PRE,
                                                   "farol_pv")),
    ("vc_meta", VEN, "Farol de Metas Equipe", acompanhamento_meta),
    ("vc_planner", VEN, "Farol Roteirização", resumo_planner),
    ("vc_painel", VEN, "Painel Executivo", painel_executivo),
    ("vc_base", VEN, "Farol de Clientes", base_e_oportunidades),
    ("vc_visitas", VEN, "Farol de Visita", farol_visitas),
    # (28/10, Alexandre) o jogo de pontos do time, todo mes
    # (28/10) "Campanhas BAP": o BAP Champions + a Campanha relampago
    ("vc_champions", VEN, "Campanhas BAP", bap_champions),
    ("pl_giro", VEN, "Farol de Giro de Produtos", giro_produtos),
    ("farol_vc", VEN, "Farol DDR", lambda c: farol(c, "Mayara Santos", VEN,
                                                   "farol_vc")),
    ("pl_entregas", POS, "Farol de Entregas", entregas),
    ("pl_garantias", POS, "Farol de Garantias", garantias),
    ("pl_devolucoes", POS, "Farol de Devolução e Reembolsos", devolucoes),
    ("pl_frw", POS, "Farol de Estoque FRW", estoque_frw),
    ("pl_inadimplencia", POS, "Farol de Inadimplência", farol_inadimplencia),
    ("pl_ncc", POS, "Farol de NCC", farol_ncc),
    ("farol_pl", POS, "Farol DDR", lambda c: farol(c, "Estefanie Pacheco", POS,
                                                   "farol_pl")),
    ("tm_expositores", TRADE, "Farol de Expositores", farol_expositores),
    ("vc_saldo", ANA, "Farol de Saldo", saldo_desconto),
    ("vc_markup", ANA, "Farol de Markup", farol_markup),
    ("vc_preco", ANA, "Farol de Preço", farol_preco),
    ("an_divergencias", ANA, "Divergências clientes Planner x Protheus",
     divergencias_clientes),
]
# os ids antigos continuam abrindo (atalhos e o status do BAP Central)
LEGADO = [
    ("pv_abertos", PRE, "Pedidos em aberto", pedidos_em_aberto),
    ("pv_faturados", PRE, "Pedidos faturados", pedidos_faturados),
    ("pv_excluidos", PRE, "Pedidos excluídos", pedidos_excluidos),
    ("pl_fretes", POS, "Fretes", fretes),
    # (16/10) dentro do Painel Executivo (abas Executivos · ...)
    ("vc_executivo", ANA, "Farol Indicadores Executivos",
     indicadores_executivos),
    # (16/10, Alexandre) Resumo Indicadores: fora (nao precisa)
    ("an_resumo", ANA, "Resumo Indicadores", resumo_indicadores),
]
POR_ID = {x[0]: x for x in CATALOGO + LEGADO}



# =========================================================================
# RESUMO GERENCIAL PADRAO (06/10) - o mesmo desenho do Farol de Visita e do
# Farol Roteirizacao em todos os farois: "O que o farol diz" + 3
# indicadores dia a dia, semana a semana e mes a mes + os cortes do farol.
# Cada funcao abaixo diz so o que e do farol (painel_farol faz o resto).
# =========================================================================
def _ev_tempo(r, n=0):
    """O indicador que o farol ja desenhava (graficos_tempo)."""
    import painel_farol as pf                           # noqa: PLC0415
    evs = r.get("_eventos") or []
    if len(evs) <= n:
        return None
    e = evs[n]
    agg = e["agg"]
    return pf.ind(e["nome"], e["eventos"], agg, e["formato"], e["cor"])


def _ev_itens(ctx, tipos=("VND",), data="dt_nf"):
    return [it for it in ctx.tabela["itens"] if it["tipo"] in tipos
            and it.get(data)]


def _ind_positivados(ctx):
    import painel_farol as pf                           # noqa: PLC0415
    return pf.ind("Clientes positivados", _ev_positivados(ctx, _ev_itens(ctx)),
                  "unicos", "num", AZUL)


def _ind_notas(ctx, nome="Notas faturadas"):
    import painel_farol as pf                           # noqa: PLC0415
    return pf.ind(nome, [(it["dt_nf"], (it["filial"], it["nf"]))
                         for it in _ev_itens(ctx)], "unicos", "num", AZUL)


def _ind_faturamento(ctx, nome="Faturamento (R$)", liquido=False):
    import painel_farol as pf                           # noqa: PLC0415
    return pf.ind(nome, _eventos_faturamento(ctx, liquido=liquido), "soma",
                  "moeda", VERDE)


def _painel_pedidos(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    ls, ix = pf.tabela_de(r, "Pedidos")
    sla = {}
    for it in _ev_itens(ctx):
        k = (it["filial"], it["nf"])
        if k not in sla and it.get("dt_pedido"):
            sla[k] = (it["dt_nf"], ctx.uteis(it["dt_pedido"], it["dt_nf"]))
    inds = [_ev_tempo(r), _ind_faturamento(ctx),
            pf.ind("SLA de faturamento", list(sla.values()), "media", "dias",
                   AMARELO, "baixo", meta_dia=bd.PRAZO_FATURAR)]
    ext = []
    if ix:
        abertos = [l for l in ls if l[ix["SITUAÇÃO"]] == "EM ABERTO"]
        atr = [l for l in abertos if l[ix["PRAZO"]] == "ATRASADO"]
        if atr:
            ext.append(("alerta", f"{br(len(atr))} pedido(s) em aberto fora "
                        f"do prazo de {bd.PRAZO_FATURAR} dias úteis "
                        f"({moeda(sum(l[ix['R$ VENDA']] or 0 for l in atr))})"
                        f": faturar ou cobrar a separação."))
        cred = [l for l in abertos if texto(l[ix["ANÁLISE CRÉDITO"]])
                and l[ix["ANÁLISE CRÉDITO"]] != CREDITO_OK]
        if cred:
            ext.append(("atencao", f"{br(len(cred))} pedido(s) em aberto com"
                        f" pendência de crédito "
                        f"({moeda(sum(l[ix['R$ VENDA']] or 0 for l in cred))})."))
        parc = [l for l in abertos if (l[ix["% ATENDIDO"]] or 0) < 99.99]
        if parc:
            ext.append(("atencao", f"{br(len(parc))} pedido(s) em aberto sem "
                        f"estoque para atender 100%."))
    rk = [pf.ranking("Pedidos em aberto por vendedor (R$)", list(pf.somar_por(
        ls, ix, "VENDEDOR", "R$ VENDA",
        lambda l: l[ix["SITUAÇÃO"]] == "EM ABERTO").items()), "moeda")] \
        if ix else []
    pf.montar(r, ctx, inds, ext, rk)


def _painel_ddr(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    e = (r.get("_eventos") or [None])[0]
    if not e:
        return
    evs = e["eventos"]
    inds = [_ev_tempo(r),
            pf.ind("Pontos ganhos", [(d, g) for d, g, _p in evs], "soma",
                   "num", AZUL),
            pf.ind("Pontos perdidos", [(d, (p_ or 0) - (g or 0))
                                       for d, g, p_ in evs], "soma", "num",
                   VERMELHO, "baixo")]
    ls, ix = pf.tabela_de(r, "Até hoje")
    perdidos = pf.somar_por(ls, ix, "ATIVIDADE", "PONTOS")
    ganhos = pf.somar_por(ls, ix, "ATIVIDADE", "PONTOS GANHOS")
    falta = {k: v - ganhos.get(k, 0) for k, v in perdidos.items()
             if v - ganhos.get(k, 0) > 0}
    rk = [pf.ranking("Atividades que mais perderam pontos", list(falta.items()),
                     "num", cores=[VERMELHO] * 8)]
    ext = []
    pend, ixp = pf.tabela_de(r, "Pendentes de marcação")
    if pend:
        ext.append(("alerta", f"{br(len(pend))} atividade(s) sem marcação: "
                              f"marcar no Farol DDR para não perder pontos."))
    pf.montar(r, ctx, inds, ext, rk, titulo_ins="O que o DDR diz")


def _painel_metas(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    inds = [_ev_tempo(r), _ind_positivados(ctx),
            pf.ind("Pedidos faturados", [(it["dt_nf"], (it["filial"],
                                                        it["pedido"]))
                                         for it in _ev_itens(ctx)],
                   "unicos", "num", AZUL)]
    ext = []
    ls, ix = pf.tabela_de(r, "Por gerente")
    if ls and ix.get("FAT. NEC./DIA") is not None:
        nec = sum(l[ix["FAT. NEC./DIA"]] or 0 for l in ls)
        if nec:
            ext.append(("atencao", f"Para bater a meta de faturamento: "
                                   f"{moeda(nec)} por dia útil até o fim do "
                                   f"mês."))
    lv, iv = pf.tabela_de(r, "Por vendedor")
    if iv:
        abaixo = [l for l in lv if (l[iv["FAT. % ATING."]] or 0) < 50]
        if abaixo:
            ext.append(("atencao", f"{br(len(abaixo))} vendedor(es) abaixo de"
                                   f" 50% da meta de faturamento."))
    ss, is_ = pf.tabela_de(r, "Por supervisor")
    rk = [pf.ranking("Atingimento do faturamento por supervisor (%)",
                     [(l[is_["NOME"]], l[is_["FAT. % ATING."]]) for l in ss],
                     "pct", referencia=100)] if is_ else []
    pf.montar(r, ctx, inds, ext, rk)


def _painel_executivo(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    tick = pf.ind("Ticket médio por nota",
                  [(it["dt_nf"], it["valor"], (it["filial"], it["nf"]))
                   for it in _ev_itens(ctx)],
                  lambda vs: sum(v[0] for v in vs) / len({v[1] for v in vs}),
                  "moeda", AZUL)
    pf.montar(r, ctx, [_ev_tempo(r), _ind_positivados(ctx), tick])


def _painel_clientes(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    prim = {}
    for it in _ev_itens(ctx):
        if it["cliente"] not in prim or it["dt_nf"] < prim[it["cliente"]]:
            prim[it["cliente"]] = it["dt_nf"]
    inds = [_ev_tempo(r), _ind_faturamento(ctx),
            pf.ind("Clientes novos (1ª compra)",
                   [(d, c) for c, d in prim.items()], "conta", "num", AZUL)]
    seg, ixs = pf.tabela_de(r, "Por segmento")
    ven, ixv = pf.tabela_de(r, "Por vendedor")
    rk = []
    if ixs:
        rk.append(pf.ranking("Positivação por segmento (%)",
                             [(l[ixs["SEGMENTO"]], l[ixs["% POSITIVAÇÃO"]])
                              for l in seg], "pct"))
    if ixv:
        rk.append(pf.ranking("Oportunidade (falta) por vendedor",
                             [(l[ixv["VENDEDOR"]],
                               l[ixv["OPORTUNIDADE (FALTA)"]]) for l in ven],
                             "moeda", insight=True))
    pf.montar(r, ctx, inds, (), rk)


def _painel_giro(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    inds = [_ev_tempo(r),
            pf.ind("SKUs vendidos", [(it["dt_nf"], it["cod"])
                                     for it in _ev_itens(ctx)],
                   "unicos", "num", AZUL),
            pf.ind("Unidades vendidas", [(it["dt_nf"], it["qtd"])
                                         for it in _ev_itens(ctx)],
                   "soma", "num", AZUL)]
    fin, ix = pf.tabela_de(r, "Resumo por filial")
    rk = [pf.ranking("Venda perdida prevista (R$) por filial",
                     [(l[ix["FILIAL"]], l[ix["VENDA PERDIDA PREVISTA"]])
                      for l in fin], "moeda", cores=[VERMELHO] * 8,
                     bom="baixo")] if ix else []
    pf.montar(r, ctx, inds, (), rk)


def _painel_entregas(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    ls, ix = pf.tabela_de(r, "Entregas")
    if not ix:
        return
    inds = [_ev_tempo(r),
            pf.ind("Entregas concluídas", [(l[ix["DT. REAL"]], 1) for l in ls
                                           if l[ix["DT. REAL"]]],
                   "conta", "num", VERDE),
            pf.ind("SLA de entrega (dias corridos)",
                   [(l[ix["DT. REAL"]], l[ix["SLA"]]) for l in ls
                    if l[ix["DT. REAL"]] and l[ix["SLA"]]
                    is not None], "media", "dias", AMARELO, "baixo")]
    abertas = [l for l in ls if not l[ix["DT. REAL"]]]
    atr = [l for l in abertas if "ATRAS" in texto(l[ix["SITUAÇÃO"]])]
    ext = []
    if atr:
        ext.append(("alerta", f"{br(len(atr))} entrega(s) atrasada(s) "
                    f"({moeda(sum(l[ix['VLR NF']] or 0 for l in atr))})."))
    rk = [pf.ranking("Notas em aberto por cidade",
                     list(pf.somar_por(abertas, ix, "CIDADE").items()),
                     "num")]
    pf.montar(r, ctx, inds, ext, rk)


def _painel_garantias(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    ls, ix = pf.tabela_de(r, "Garantias")
    if not ix:
        return
    inds = [_ev_tempo(r),
            pf.ind("Finalizadas",
                   [(l[ix["DT. SOLICITAÇÃO"]], 1) for l in ls
                    if l[ix["STATUS"]] == "FINALIZADA"
                    and l[ix["DT. SOLICITAÇÃO"]]], "conta", "num", VERDE,
                   None),
            pf.ind("Atrasadas (mais de 30 dias)",
                   [(l[ix["DT. SOLICITAÇÃO"]], 1) for l in ls
                    if l[ix["PRAZO"]] == "ATRASADA"
                    and l[ix["DT. SOLICITAÇÃO"]]], "conta", "num",
                   VERMELHO, "baixo")]
    prod, ixp = pf.tabela_de(r, "Por produto")
    rk = [pf.ranking("Garantias por produto",
                     [(l[ixp["DESCRIÇÃO"]] or l[ixp["CÓD. PRODUTO"]],
                       l[ixp["GARANTIAS"]]) for l in prod], "num")] \
        if ixp else []
    pf.montar(r, ctx, inds, (), rk)


def _painel_devolucoes(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    dev = _ev_itens(ctx, ("DEV",))
    inds = [dict(_ev_tempo(r), bom="baixo"),
            pf.ind("Notas de devolução", [(it["dt_nf"], (it["filial"],
                                                         it["nf"]))
                                          for it in dev], "unicos", "num",
                   VERMELHO, "baixo"),
            pf.ind("% devolvido do faturado",
                   [(it["dt_nf"], abs(it["valor"]), 0) for it in dev]
                   + [(d, 0, v) for d, v in
                      _eventos_faturamento(ctx, liquido=True)],
                   "pct", "pct", VERMELHO,
                   "baixo")]
    ls, ix = pf.tabela_de(r, "Devoluções")
    ano, mes = periodo(ctx)
    rot = rotulo_mes(f"{ano}-{mes:02d}") if mes else None
    rk = []
    if ix:
        rk.append(pf.ranking(
            f"Devolvido por motivo (R$){' · ' + rot if rot else ''}",
            list(pf.somar_por(ls, ix, "MOTIVO", "VALOR",
                              (lambda l: l[ix["MÊS"]] == rot) if rot
                              else None).items()), "moeda",
            cores=[VERMELHO] * 8, bom="baixo"))
    vv, ixv = pf.tabela_de(r, "Por vendedor (12 meses)")
    if ixv:
        rk.append(pf.ranking("% devolvido por vendedor (12 meses)",
                             [(l[ixv["VENDEDOR"]], l[ixv["% DEVOLVIDO"]])
                              for l in vv], "pct", cores=[VERMELHO] * 8,
                             bom="baixo"))
    pf.montar(r, ctx, inds, (), rk)


def _painel_frw(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    trf = ctx.tabela.get("transferencias") or []
    inds = [_ev_tempo(r),
            pf.ind("SKUs que entraram", [(t["data"], t.get("cod"))
                                         for t in trf], "unicos", "num",
                   AZUL),
            pf.ind("Unidades vendidas", [(it["dt_nf"], it["qtd"])
                                         for it in _ev_itens(ctx)], "soma",
                   "num", VERDE)]
    ls, ix = pf.tabela_de(r, "Estoque FRW")
    rk = []
    if ix:
        rk.append(pf.ranking("Devolver à PMZ (R$) por filial", list(
            (k, abs(v)) for k, v in pf.somar_por(
                ls, ix, "FILIAL", "VALOR",
                lambda l: l[ix["AÇÃO"]] == "DEVOLVER À PMZ").items()),
            "moeda", cores=[VERMELHO] * 8, bom="baixo"))
        rk.append(pf.ranking("Itens a pedir por filial", list(
            pf.somar_por(ls, ix, "FILIAL", None,
                         lambda l: l[ix["AÇÃO"]] == "PEDIR").items()),
            "num", cores=[AMARELO] * 8))
    pf.montar(r, ctx, inds, (), rk)


def _painel_inadimplencia(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    dd, ixd = pf.tabela_de(r, "Dia a dia")
    tit, ixt = pf.tabela_de(r, "Títulos")
    ind1 = _ev_tempo(r)
    if ind1:
        ind1["bom"] = "baixo"
    inds = [ind1,
            pf.ind("Recebido (R$)", [(l[ixd["DATA"]], l[ixd["RECEBIDO"]] or 0)
                                     for l in dd], "soma", "moeda", VERDE)
            if ixd else None,
            pf.ind("Vencido no período (R$, pelo vencimento)",
                   [(l[ixt["VENCIMENTO"]], l[ixt["SALDO"]] or 0)
                    for l in tit if l[ixt["SITUAÇÃO"]] == "VENCIDO"],
                   "soma", "moeda", VERMELHO, "baixo", projetar=False)
            if ixt else None,
            pf.ind("Títulos emitidos a prazo (R$)",
                   [(l[ixt["EMISSÃO"]], l[ixt["VALOR"]] or 0) for l in tit],
                   "soma", "moeda", AZUL, None) if ixt else None,
            pf.ind("A vencer (R$, pelo vencimento)",
                   [(l[ixt["VENCIMENTO"]], l[ixt["SALDO"]] or 0)
                    for l in tit if l[ixt["SITUAÇÃO"]] != "VENCIDO"],
                   "soma", "moeda", AMARELO, None, projetar=False)
            if ixt else None]
    vv, ixv = pf.tabela_de(r, "Por vendedor")
    rk = [pf.ranking("Em atraso por vendedor (R$)",
                     [(l[ixv["VENDEDOR"]], l[ixv["EM ATRASO"]]) for l in vv],
                     "moeda", cores=[VERMELHO] * 8, bom="baixo")] \
        if ixv else []
    ext = []
    if ixt:
        por_cli = pf.somar_por(tit, ixt, "NOME", "SALDO",
                               lambda l: l[ixt["SITUAÇÃO"]] == "VENCIDO")
        top = sorted(por_cli.items(), key=lambda x: -x[1])[:3]
        tot = sum(por_cli.values())
        if top and tot:
            ext.append(("alerta", "Maiores devedores: " + ", ".join(
                f"{n} ({moeda(v)})" for n, v in top)
                + f" — {p(pct_de(sum(v for _, v in top), tot))} do atraso."))
    pf.montar(r, ctx, [i for i in inds if i], ext, rk)


def _painel_expositores(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    ls, ix = pf.tabela_de(r, "Expositores")
    if not ix:
        return
    inds = [pf.ind("Expositores solicitados",
                   [(l[ix["SOLICITAÇÃO"]], l[ix["QTD"]] or 0) for l in ls],
                   "soma", "num", AZUL),
            pf.ind("Contratos assinados",
                   [(l[ix["ASSINATURA"]], l[ix["QTD"]] or 0) for l in ls],
                   "soma", "num", VERDE),
            pf.ind("Prazo para assinar",
                   [(l[ix["ASSINATURA"]], l[ix["DIAS"]]) for l in ls
                    if l[ix["DIAS"]] is not None], "media", "dias", AMARELO,
                   "baixo")]
    ext = []
    velhos = [l for l in ls if l[ix["STATUS"]] == "Solicitado"
              and l[ix["SOLICITAÇÃO"]]
              and (ctx.hoje - l[ix["SOLICITAÇÃO"]]).days > 30]
    if velhos:
        ext.append(("atencao", f"{br(len(velhos))} solicitação(ões) há mais "
                               f"de 30 dias sem contrato assinado."))
    uf, ixu = pf.tabela_de(r, "Por estado")
    rk = [pf.ranking("Expositores por estado", [(l[ixu["UF"]],
                                                 l[ixu["EXPOSITORES"]])
                                                for l in uf], "num")] \
        if ixu else []
    pf.montar(r, ctx, inds, ext, rk, blocos_extra=False)


def _painel_saldo(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    ls, ix = pf.tabela_de(r, "Pedido a pedido")
    if not ix:
        return
    d_ = ix["DATA NF"]
    i_s = ix.get("NO SALDO", ix.get("SALDO"))
    inds = [pf.ind("Saldo (R$)", [(l[d_], l[i_s] or 0) for l in ls],
                   "soma", "moeda", VERDE),
            pf.ind("% de desconto comercial", [
                (l[d_], l[ix["DESC. COMERCIAL"]] or 0,
                 l[ix["VLR TABELA"]] or 0) for l in ls],
                   "pct", "pct", AMARELO, "baixo",
                   meta_dia=TETO_DESCONTO),
            # (22/10, Alexandre) o FATURADO e o real: venda - devolucoes
            pf.ind("Faturado (R$)", _eventos_faturamento(ctx, liquido=True),
                   "soma", "moeda", AZUL)]
    ano, mes = periodo(ctx)
    no = [l for l in ls if l[d_] and l[d_].year == ano
          and (not mes or l[d_].month == mes)]
    rk = [pf.ranking("Saldo por vendedor no período (R$)", list(
        pf.somar_por(no, ix, "VENDEDOR", "NO SALDO").items()), "moeda",
        top=10, cores=lambda ps: [VERDE if v >= 0 else VERMELHO
                                  for _, v in ps])]
    neg = [k for k, v in pf.somar_por(no, ix, "VENDEDOR", "NO SALDO").items()
           if v < 0]
    # (22/10, Alexandre) sem o aviso da autorizacao (nao importa no saldo)
    acima = [l for l in no if (l[ix["% DESC. COM."]] or 0)
             > TETO_DESCONTO + TOLERANCIA_TETO]
    ext = ([("atencao", f"{br(len(acima))} pedido(s) acima de 15% no "
                        f"período (descontam "
                        f"{moeda(-sum((l[i_s] or 0) - (l[ix['SALDO FRETE']] or 0) for l in acima))}"
                        " do saldo).")] if acima else []) + \
        ([("atencao", f"{br(len(neg))} vendedor(es) com saldo negativo no "
                      f"período.")] if neg else [])
    pf.montar(r, ctx, inds, ext, rk)


def _painel_markup(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    e = (r.get("_eventos") or [None])[0]
    if not e:
        return
    evs = e["eventos"]                  # (data, venda, custo) item a item
    inds = [_ev_tempo(r),
            pf.ind("Margem (R$)", [(d, v - c) for d, v, c in evs if c],
                   "soma", "moeda", AZUL),
            pf.ind("Venda (R$)", [(d, v) for d, v, _c in evs], "soma",
                   "moeda", AZUL)]
    vv, ixv = pf.tabela_de(r, "Por vendedor")
    rk = [pf.ranking("Markup por vendedor (%)",
                     [(l[ixv["VENDEDOR"]], l[ixv["MARKUP %"]]) for l in vv],
                     "pct", referencia=MARKUP_MIN)] if ixv else []
    pf.montar(r, ctx, inds, (), rk)


def _painel_preco(r, ctx):
    """(15/10) Resumo do Farol de Preco: faturamento, volume e preco medio
    (dia/semana/mes) + o que o preco fez com o faturamento no ultimo mes."""
    import painel_farol as pf                           # noqa: PLC0415
    d = r.pop("_preco", None) or {}
    evs = d.get("eventos") or []
    inds = [_ev_tempo(r),
            pf.ind("Volume (unidades)", [(x, q) for x, _v, q, _t in evs],
                   "soma", "num", AZUL),
            pf.ind("Preço de tabela (R$)",
                   [(x, t, q) for x, _v, q, t in evs if t],
                   lambda vs: (sum(a for a, _b in vs)
                               / sum(b for _a, b in vs))
                   if sum(b for _a, b in vs) else 0, "moeda2", AMARELO,
                   bom=None)]
    lc, lf = d.get("categoria") or [], d.get("familia") or []
    ext, rk = [], []
    if lc:
        ult = max(l[1] for l in lc)
        uc = [l for l in lc if l[1] == ult]
        uf = [l for l in lf if l[1] == ult]
        rk.append(pf.ranking(f"Efeito preço por categoria · "
                             f"{rotulo_mes(ult)} (R$)",
                             [(l[P_G], l[P_EP]) for l in uc], "moeda",
                             cores=lambda ps: [VERDE if v >= 0 else VERMELHO
                                               for _, v in ps],
                             insight=False))
        rk.append(pf.ranking(f"Variação da tabela por família · "
                             f"{rotulo_mes(ult)} (%)",
                             [(l[P_G], l[P_VT]) for l in uf
                              if l[P_VT] is not None],
                             "pct", bom=None, insight=False))
        quedas = [l for l in uc + uf if l[P_L] == L_QUEDA]
        if quedas:
            ext.append(("alerta", f"{uc[0][P_M]}: faturamento caiu "
                        f"depois de reajuste em " + ", ".join(
                            f"{l[P_G]} (tabela {br(l[P_VT], 1)}%, fat. "
                            f"{br(l[P_VF], 1)}%)" for l in quedas[:4]) + "."))
        pv = d.get("pv") or {}
        n_sobe = pv.get("sobe_cai", 0) + pv.get("sobe_sobe", 0)
        if n_sobe:
            ext.append(("alerta" if pv.get("sobe_cai") else "ok",
                        f"Tabela x volume: em {pv['sobe_cai']} de {n_sobe} "
                        f"mês(es) com aumento da tabela o volume caiu"
                        + (f"; em {pv['sobe_sobe']} o volume subiu junto"
                           if pv.get("sobe_sobe") else "") + "."))
        abs_ = [l for l in uc if l[P_L] == L_ABSORVIDO]
        if abs_:
            ext.append(("ok", "Reajuste absorvido (preço e faturamento "
                        "subindo): " + ", ".join(l[P_G] for l in abs_)
                        + "."))
    pf.montar(r, ctx, inds, ext, rk)
    # (15/10) a ordem do resumo: o que o farol diz | TABELA x VOLUME e a
    # VARIACAO % DA TABELA em cima (largos); embaixo faturamento, volume e
    # preco de tabela (dia, semana, mes) e por fim os cortes
    blocos = (r.get("painel") or {}).get("blocos") or []
    ins_ = [b for b in blocos if b.get("tipo") == "insights"]
    graf = [b for b in blocos if b.get("tipo") != "insights"]

    def tit(b):
        return ((b.get("grafico") or {}).get("titulo") or b.get("titulo")
                or "")
    tv = [b for b in graf if (b.get("grafico") or {}).get("linhas")]
    vt = [b for b in graf if (b.get("grafico") or {}).get("variacao_tabela")]
    tempo = [b for b in graf if b not in tv + vt and (
        " · dia a dia" in tit(b) or " · semana a semana" in tit(b)
        or " · mês a mês (12" in tit(b))]
    resto = [b for b in graf if b not in tv + vt + tempo]
    novos = []
    for b in ins_:
        novos.append(dict(b, row=0, col=0, rowspan=2))
    for i, b in enumerate(tv[:1] + vt[:1]):
        b = {k: v for k, v in b.items() if k not in ("row", "col",
                                                     "colspan", "rowspan")}
        novos.append(dict(b, row=i, col=1, colspan=2))
    linha = 2
    for j, b in enumerate(tempo):
        b = {k: v for k, v in b.items() if k not in ("row", "col",
                                                     "colspan", "rowspan")}
        novos.append(dict(b, row=linha + j // 3, col=j % 3))
    linha += (len(tempo) + 2) // 3
    for j, b in enumerate(resto):
        b = {k: v for k, v in b.items() if k not in ("row", "col",
                                                     "colspan", "rowspan")}
        novos.append(dict(b, row=linha + j // 3, col=j % 3))
    linha += (len(resto) + 2) // 3
    if r.get("painel") and novos:
        r["painel"]["blocos"] = novos
        r["painel"]["altura_min"] = max(4, linha) * 250


def _painel_resumo(r, ctx):
    import painel_farol as pf                           # noqa: PLC0415
    vg, ix = next(((ls, ix) for ls, ix in [pf.tabela_de(r, t_["titulo"])
                                            for t_ in r["tabelas"]
                                            if t_["titulo"].startswith(
                                                "Visão geral")]), ([], {}))
    rk, ext = [], []
    if ix:
        pares = [(f"{texto(l[ix['ÁREA']]).split()[0]} · "
                  f"{l[ix['INDICADOR']]}"[:42],
                  l[ix["% ATING."]]) for l in vg
                 if l[ix["% ATING."]] is not None]
        rk.append(pf.ranking("Indicadores mais longe da meta (%)", pares,
                             "pct", menor_primeiro=True, referencia=100,
                             cores=lambda ps: [VERMELHO if v < 80 else
                                               AMARELO if v < 100 else VERDE
                                               for _, v in ps], insight=False))
        piores = sorted(pares, key=lambda x: x[1])[:3]
        if piores and piores[0][1] < 80:
            ext.append(("alerta", "Mais longe da meta: " + ", ".join(
                f"{a} ({p(v)})" for a, v in piores if v < 80) + "."))
    pf.montar(r, ctx, [_ind_faturamento(ctx), _ind_positivados(ctx),
                       pf.ind("Pedidos digitados",
                              [(it["dt_pedido"], (it["filial"], it["pedido"]))
                               for it in _ev_itens(ctx, ("VND", "VEA", "EXC"),
                                                   "dt_pedido")],
                              "unicos", "num", AZUL)],
              ext, rk, manter=("Indicadores na meta",))


def _so_status(rel):
    """(06/10) Em NENHUM relatorio aparece STATUS PROTHEUS nem SITUACAO
    PLANNER (nem como coluna, nem como filtro): so o STATUS do Planner
    (ATIVO/INATIVO), com o nome STATUS. As colunas escondidas continuam na
    linha (cartoes, recortes e o calendario ainda as usam por dentro)."""
    tira = (COL_ST_PROTHEUS, COL_SIT_PLANNER)
    for t in rel.get("tabelas") or []:
        nomes = [c["nome"] for c in t["colunas"]]
        if not set(nomes) & {COL_ST_PROTHEUS, COL_ST_PLANNER, COL_SIT_PLANNER}:
            continue
        novo_n = COL_ST_PLANNER if "STATUS" in nomes else "STATUS"
        for c in t["colunas"]:
            if c["nome"] in tira:
                c["oculta"] = True
            elif c["nome"] == COL_ST_PLANNER:
                c["nome"] = novo_n
        filtros = []
        for f in t.get("filtros") or []:
            n_ = nome_filtro(f)
            if n_ in tira:
                continue
            if n_ == COL_ST_PLANNER:
                f = dict(f, coluna=novo_n) if isinstance(f, dict) else novo_n
            filtros.append(f)
        t["filtros"] = filtros


PAINEIS_PADRAO = {
    "pv_pedidos": _painel_pedidos, "farol_pv": _painel_ddr,
    "farol_vc": _painel_ddr, "farol_pl": _painel_ddr,
    "vc_meta": _painel_metas,
    "vc_base": _painel_clientes, "pl_giro": _painel_giro,
    # pl_entregas: (10/10) resumo executivo proprio (frete por estado...)
    "pl_garantias": _painel_garantias,
    "pl_devolucoes": _painel_devolucoes, "pl_frw": _painel_frw,
    "pl_inadimplencia": _painel_inadimplencia,
    "tm_expositores": _painel_expositores, "vc_saldo": _painel_saldo,
    "vc_markup": _painel_markup, "an_resumo": _painel_resumo,
    "vc_preco": _painel_preco,
}


# (14/10, Alexandre) LINHA PINTADA so nos farois autorizados: Pedidos e
# Markup (e o Saldo, a linha vermelha do "sem autorizacao" pedida em
# 13/10). Nos outros a linha fica limpa e o alerta vai para a COLUNA: o
# STATUS/SITUACAO/PRAZO vira selo colorido (ATRASADA vermelho...) e o SLA
# de cada farol pinta a celula, como no Farol de Pedidos.
LINHA_PINTADA = ("pv_pedidos", "vc_markup", "vc_saldo")
# (21/10) Farol de Visita: % META (>= 100 verde, >= 80 amarelo, abaixo
# vermelho) e DU SEM VISITA (0 sem cor, 1 a 2 amarelo, 3 ou mais vermelho)
FAIXA_PCT_META = [(79.9999, *_VERM),
                  (99.9999, *_AMAR), (None, *_VERD)]
FAIXA_DU_SEM = [(0, None, None), (2, *_AMAR),
                (None, *_VERM)]
COLUNAS_SINAL = ("SITUAÇÃO", "STATUS", "PRAZO", "ETAPA", "FAIXA",
                 "SITUAÇÃO PRAZO", "LEITURA", "SLA NCC")
CORES_SINAL = {
    **{k: _VERM for k in ("ATRASADA", "ATRASADO", "VENCIDO", "INADIMPLENTE",
                          "RUPTURA", "ENTREGUE COM ATRASO", "FORA DO PRAZO",
                          "+180 DIAS", "MAIS DE 180 DIAS", "CRÍTICO")},
    **{k: _AMAR for k in ("VENCE HOJE", "VENCE AMANHÃ", "ATENÇÃO",
                          "PARCIAL", "EM TRATATIVA", "91-180 DIAS")},
    **{k: _VERD for k in ("NO PRAZO", "EM DIA", "FINALIZADA")},
    # (15/10) Farol de Preco
    "QUEDA APÓS REAJUSTE": _VERM, "REDUÇÃO SEM VOLUME": _AMAR,
    "REAJUSTE ABSORVIDO": _VERD, "REDUÇÃO TROUXE VOLUME": _VERD}


def _sinal_nas_colunas(rel) -> None:
    """Fora dos farois de LINHA_PINTADA: tira a cor das linhas e poe o selo
    colorido nas colunas de status/situacao/prazo que tem esses valores."""
    if rel.get("id") in LINHA_PINTADA:
        return
    tabs = list(rel.get("tabelas") or [])
    for t in list(tabs):
        tabs += [j for j in (t.get("juntas") or []) if isinstance(j, dict)]
    for t in tabs:
        if t.get("linhas") is not None:
            t["tons"] = [""] * len(t["linhas"])
        for j, c in enumerate(t.get("colunas") or []):
            if c.get("nome") not in COLUNAS_SINAL or c.get("chip"):
                continue
            if any(str(l[j]).strip().upper() in CORES_SINAL
                   for l in (t.get("linhas") or [])[:2000]
                   if j < len(l) and l[j] not in (None, "")):
                c["chip"] = CORES_SINAL
                # o selo nao pode cortar: a coluna com a largura do maior
                maior = max((len(str(l[j])) for l in t["linhas"][:2000]
                             if j < len(l) and l[j] not in (None, "")),
                            default=8)
                c["largura"] = max(c.get("largura") or 0, maior * 8 + 26)
                c["larg_fixa"] = c["largura"]


def montar(rid: str, raiz, hoje=None, log=None, params=None,
           tela=False) -> dict:
    """tela=True: o BAP Relatorios (a aba Equipe e a Acomp. RH no Farol de
    Metas Equipe); fora da tela as tabelas por pessoa ficam como sempre."""
    _, area, titulo, funcao = POR_ID[rid]
    ctx = Contexto(raiz, hoje, log, params)
    rel = funcao(ctx)
    rel.setdefault("area", area)
    _status_nas_tabelas(ctx, rel)
    # (06/10) o Resumo gerencial padrao (o farol que nao tem painel proprio)
    if rel.get("capa") and not rel.get("painel") and rid in PAINEIS_PADRAO:
        try:
            PAINEIS_PADRAO[rid](rel, ctx)
        except Exception as erro:                       # noqa: BLE001
            rel.setdefault("avisos", []).append(
                f"Resumo gerencial no formato antigo: {erro}")
    rel.pop("_eventos", None)
    equipe = rel.pop("_equipe", None)
    if tela and equipe:
        try:
            equipe()
        except Exception as erro:                       # noqa: BLE001
            rel.setdefault("avisos", []).append(
                f"Aba Equipe fora do ar (seguem as abas por pessoa): {erro}")
    _so_status(rel)
    _sinal_nas_colunas(rel)
    rel["params_usados"] = dict(ctx.params)
    for t in rel["tabelas"]:
        t.setdefault("tons", [""] * len(t["linhas"]))
        t.setdefault("kpis_de", None)
        t.setdefault("recortes", [])
        t.setdefault("edicao", None)
        if "detalhe" not in t:
            t["detalhe"] = _colunas_do_pedido(t)

    def detalhe(t, linha):
        d = t.get("detalhe") or {}

        def v(k):
            j = d.get(k)
            return linha[j] if j is not None and j < len(linha) else ""
        return detalhe_pedido(ctx, v("filial"), v("pedido"), v("nf"))
    rel["detalhe_pedido"] = detalhe
    return rel
