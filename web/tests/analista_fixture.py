"""T-0036: pacote fictício dos 4 faróis do Analista Comercial (contrato §10.11). Tudo inventado: sem nome, CNPJ,
telefone ou e-mail real; o cliente aparece só pelo código fictício (RN-GER-011)."""
from copy import deepcopy

from app import tabelas

MESES = ("2026-10", "2026-11")
_UF = ("AM", "PA", "MA")
_FILIAL = ("MANAUS", "BELEM", "SAO LUIS")


def _valor(nome, tipo, i):
    if nome in ("UF",):
        return _UF[i % 3]
    if nome == "FILIAL":
        return _FILIAL[i % 3]
    if nome in ("CÓD.", "COD", "A1_COD"):
        return f"9{i:05d}-01"
    if nome == "PONTO":
        return "SEM COORDENADA"
    if nome in ("MÊS", "AAAA-MM"):
        return MESES[i % 2]
    if tipo in ("dia", "data"):
        return f"2026-11-{i % 20 + 1:02d}"
    if tipo == "hora":
        return "08:00"
    if tipo == "int":
        return i + 1
    if tipo in ("num", "num1", "num2", "valor", "moeda", "moeda2"):
        return round(100.5 * (i + 1), 2)
    if tipo in ("pct", "pct1"):
        return round(10.0 + i, 1)
    if nome == "VENDEDOR PROTHEUS (A1_VEND)":          # diferente do Planner: é a divergência
        return f"VENDEDOR FICTICIO {(i + 1) % 3 + 1:02d}"
    if "VENDEDOR" in nome:
        return f"VENDEDOR FICTICIO {i % 3 + 1:02d}"
    if "SUPERVISOR" in nome:
        return f"SUPERVISOR FICTICIO {i % 2 + 1:02d}"
    if nome in ("CIDADE",):
        return f"CIDADE FICTICIA {i % 3 + 1:02d}"
    return f"{nome[:12]} {i + 1}"


def tabela(rid, titulo, n=6, **extra):
    esp = tabelas.COLUNAS_RID[(rid, titulo)]
    cols = [{"nome": nm, "tipo": tp, "largura": 90, "oculta": o} for nm, tp, o in esp]
    linhas = [[_valor(nm, tp, i) for nm, tp, _ in esp] for i in range(n)]
    t = {"titulo": titulo, "colunas": cols, "linhas": linhas}
    nomes = [c["nome"] for c in cols]
    if "UF" in nomes:
        k = nomes.index("UF")
        t["uf_linhas"] = [ln[k] for ln in linhas]
    t.update(extra)
    return t


KPIS = {
    "vc_saldo": ["Faturado", "Desconto comercial", "Saldo", "Saldo do frete"],
    "vc_markup": ["Venda", "Custo", "Margem", "Markup", "Abaixo do mínimo", "Sem custo", "Em aberto"],
    "vc_preco": ["Faturamento NOV", "Efeito preço", "Efeito volume", "Efeito mix", "Reajustes", "Queda após reajuste"],
    "an_divergencias": ["Clientes na base (Planner)", "Batem", "Vendedor diferente", "Sem vendedor no Planner",
                        "Fora da base do Planner", "Código duplicado", "Sem coordenada / endereço"],
}
TITULOS = {"vc_saldo": "Farol de Saldo", "vc_markup": "Farol de Markup", "vc_preco": "Farol de Preço",
           "an_divergencias": "Divergências clientes Planner x Protheus"}


def farol(rid, n=6):
    f = {"forma": "farol", "titulo": TITULOS[rid],
         "kpis": [{"rotulo": r, "valor": f"{(i + 1) * 12},5", "cor": "neutro", "detalhe": ""} for i, r in enumerate(KPIS[rid])],
         "painel": {"blocos": [{"tipo": "insights", "titulo": "O que o farol diz", "row": 0, "col": 0,
                                "linhas": [["info", "Frase fictícia do farol."]]}]},
         "insights_painel": [["info", "Frase fictícia do farol."]], "avisos": [],
         "baixado_em": "2026-11-24T08:10:00-04:00",
         "tabelas": [tabela(rid, t, n) for _, t in tabelas.ABAS[rid]]}
    if rid == "vc_saldo":                      # recorte por estado (o robô confere o kpis_de; §10.11.1)
        f["recortes"] = {uf: {"kpis": f["kpis"]} for uf in _UF}
    return f


def correcao():
    cor = [[f"01", f"9{i:05d}", "01", f"CIDADE FICTICIA {i}", "AM", "V001", "V002", f"VENDEDOR FICTICIO {i}",
            "SUPERVISOR FICTICIO 01", "ATIVO"] for i in range(3)]
    ana = [["01", f"9{i:05d}", "01", f"CIDADE FICTICIA {i}", "AM", "VENDEDOR FICTICIO 01", "V001",
            "SEM VENDEDOR NO PLANNER", "Analisar no Planner"] for i in range(2)]
    return {"corrigir": {"titulo": "CORRIGIR NO PROTHEUS", "linhas": cor, "colunas": [
                {"nome": n, "tipo": "texto"} for n in
                ("A1_FILIAL", "A1_COD", "A1_LOJA", "CIDADE", "UF", "A1_VEND ATUAL", "A1_VEND CORRETO",
                 "VENDEDOR CORRETO", "SUPERVISOR", "STATUS PROTHEUS")]},
            "analisar": {"titulo": "ANALISAR", "linhas": ana, "colunas": [
                {"nome": n, "tipo": "texto"} for n in
                ("A1_FILIAL", "A1_COD", "A1_LOJA", "CIDADE", "UF", "VENDEDOR NO PLANNER", "A1_VEND ATUAL",
                 "SITUAÇÃO", "O QUE FAZER")]}}


RIDS_NOVOS = ("vc_saldo", "vc_markup", "vc_preco", "an_divergencias")


def pacote_analista(com_correcao=True, n=6):
    rels = {rid: farol(rid, n) for rid in RIDS_NOVOS}
    if com_correcao:
        rels["an_divergencias"]["correcao"] = correcao()
    return deepcopy({"versao_contrato": 1, "gerado_em": "2026-11-24T08:30:00-04:00", "ano": 2026, "mes": 11,
                     "relatorios": rels})


# ------------------------------------------------------------------ simulação (regra 10): números coerentes
# Os mesmos 4 faróis, com valores que fecham entre si: desconto = tabela − venda, margem = venda − custo,
# markup = venda ÷ custo − 1, as abas agregadas somam a aba de pedido e os cartões da faixa saem dessas somas.
# Tudo inventado (nomes "FICTICIO", códigos 9xxxxx); serve à simulação PNG, não aos testes de regra.
_CATS = ("FREIOS", "SUSPENSÃO", "MOTOR", "ELÉTRICA", "ARREFECIMENTO")
_LINHA = ("LEVE", "PESADA", "MOTO")


def _brl(v):
    return ("−" if v < 0 else "") + "R$ " + f"{abs(v):,.0f}".replace(",", ".")


def _pct(v):
    return f"{v:.1f}".replace(".", ",") + "%"


def _qtd(v):
    return f"{v:,}".replace(",", ".")


def _kpi(rot, valor, cor="neutro", detalhe=""):
    return {"rotulo": rot, "valor": valor, "cor": cor, "detalhe": detalhe}


def _vend(i):
    return f"VENDEDOR FICTICIO {i % 6 + 1:02d}"


def _sup(i):
    return f"SUPERVISOR FICTICIO {i % 6 // 3 + 1:02d}"


def _linhas(rid, titulo, registros):
    esp = tabelas.COLUNAS_RID[(rid, titulo)]
    cols = [{"nome": nm, "tipo": tp, "largura": 90, "oculta": o} for nm, tp, o in esp]
    linhas = [[r.get(nm, _valor(nm, tp, i)) for nm, tp, _ in esp] for i, r in enumerate(registros)]
    t = {"titulo": titulo, "colunas": cols, "linhas": linhas}
    nomes = [c["nome"] for c in cols]
    if "UF" in nomes:
        t["uf_linhas"] = [ln[nomes.index("UF")] for ln in linhas]
    return t


def _agrupa(regs, chave, somas):
    out: dict = {}
    for r in regs:
        g = out.setdefault(r[chave], {chave: r[chave], "_n": 0, "SUPERVISOR": r.get("SUPERVISOR"),
                                      **{s: 0.0 for s in somas}})
        g["_n"] += 1
        for s in somas:
            g[s] = round(g[s] + r[s], 2)
    return sorted(out.values(), key=lambda g: -g[somas[1]])


def _saldo(n):
    peds = []
    for i in range(n):
        tab = 4200 + (i * 1373) % 21000
        d = round(3.5 + (i * 7) % 11 * 0.9, 1)              # % de desconto comercial
        venda = round(tab * (1 - d / 100), 2)
        desc = round(tab - venda, 2)
        saldo = round(venda * 0.10 - desc, 2)              # [fictício] verba de 10% da venda, menos o desconto
        frete = round(venda * (0.012 if i % 3 else -0.008), 2)
        peds.append({"MÊS": "2026-11", "DATA NF": f"2026-11-{i % 19 + 3:02d}", "FILIAL": _FILIAL[i % 3],
                     "PEDIDO": f"P{70100 + i}", "CÓD.": f"9{i:05d}-01", "VENDEDOR": _vend(i), "SUPERVISOR": _sup(i),
                     "COND. PAGTO": ("28 DIAS", "28/56", "À VISTA")[i % 3], "VLR TABELA": tab, "VLR VENDA": venda,
                     "% DESC. COM.": d, "DESC. COMERCIAL": desc, "SALDO DO PEDIDO": saldo, "SALDO FRETE": frete,
                     "NO SALDO": round(saldo + frete, 2), "NF": f"NF {41000 + i}", "UF": _UF[i % 3], "CHAVE": f"K{i}"})

    def agr(chave):
        gs = _agrupa(peds, chave, ("VLR TABELA", "VLR VENDA", "DESC. COMERCIAL", "SALDO FRETE", "SALDO DO PEDIDO"))
        for g in gs:
            meta = round(g["VLR VENDA"] * 0.035, 2)        # [fictício] meta de saldo = 3,5% da venda
            g.update({"MÊS": "2026-11", "PEDIDOS": g["_n"], "SALDO": g["SALDO DO PEDIDO"], "META SALDO": meta,
                      "% DESC. COM.": round(g["DESC. COMERCIAL"] / g["VLR TABELA"] * 100, 1),
                      "% ATING.": round(g["SALDO DO PEDIDO"] / meta * 100)})
        return gs
    tab_, venda = sum(p["VLR TABELA"] for p in peds), sum(p["VLR VENDA"] for p in peds)
    desc, saldo = sum(p["DESC. COMERCIAL"] for p in peds), sum(p["SALDO DO PEDIDO"] for p in peds)
    frete = sum(p["SALDO FRETE"] for p in peds)
    kpis = [_kpi("Faturado", _brl(venda), detalhe=f"{n} pedidos"),
            _kpi("Desconto comercial", _brl(desc), "atencao", _pct(desc / tab_ * 100) + " da tabela"),
            _kpi("Saldo", _brl(saldo), "ok" if saldo >= 0 else "alerta"),
            _kpi("Saldo do frete", _brl(frete), "ok" if frete >= 0 else "alerta")]
    return kpis, [_linhas("vc_saldo", "Pedido a pedido", peds), _linhas("vc_saldo", "Por vendedor", agr("VENDEDOR")),
                  _linhas("vc_saldo", "Por supervisor", agr("SUPERVISOR")), _linhas("vc_saldo", "Por UF", agr("UF"))]


def _markup(n):
    peds = []
    for i in range(n):
        venda = 2500 + (i * 977) % 16000
        mk = 18 + (i * 11) % 37                              # markup % do pedido
        custo = round(venda / (1 + mk / 100), 2)
        peds.append({"SITUAÇÃO": "ABAIXO DO MÍNIMO" if mk < 25 else "OK", "DATA PED.": f"2026-11-{i % 19 + 2:02d}",
                     "DATA NF": f"2026-11-{i % 19 + 3:02d}", "FILIAL": _FILIAL[i % 3], "PEDIDO": f"P{80200 + i}",
                     "NF": f"NF {52000 + i}", "CÓD.": f"9{i:05d}-01", "STATUS": "FATURADO" if i % 5 else "EM ABERTO",
                     "STATUS PROTHEUS": "NF EMITIDA", "SITUAÇÃO PLANNER": "NA ROTA", "UF": _UF[i % 3],
                     "CIDADE": f"CIDADE FICTICIA {i % 5 + 1:02d}", "SUPERVISOR": _sup(i), "VENDEDOR": _vend(i),
                     "QTD": 8 + i % 30, "R$ VENDA": venda, "CUSTO": custo, "SUCATA": 0, "MARGEM": round(venda - custo, 2),
                     "MARKUP %": float(mk), "MKP TABELA %": float(mk + 6 + i % 4), "% DESC.": round(4 + i % 6 * 0.8, 1),
                     "SEM CUSTO": 0, "VENDA SEM CUSTO": 0, "SO BATERIA": "NÃO", "CÓD. AUTORIZAÇÃO": "", "AUTORIZADO POR": ""})
    marg_ped = sum(p["MARGEM"] for p in peds)

    def agr(chave):
        gs = _agrupa(peds, chave, ("QTD", "R$ VENDA", "CUSTO", "MARGEM", "SEM CUSTO"))
        for g in gs:
            mk_ = round((g["R$ VENDA"] / g["CUSTO"] - 1) * 100, 1)
            g.update({"PEDIDOS": g["_n"], "MARKUP %": mk_, "MKP TABELA %": round(mk_ + 7, 1), "% DESC.": 5.6,
                      "PART. MARGEM": round(g["MARGEM"] / marg_ped * 100, 1)})
        return gs
    prods = []
    for i in range(n):
        cu = round(18.5 + (i * 37) % 420, 2)
        mkv = 22 + (i * 13) % 40
        pv = round(cu * (1 + mkv / 100), 2)
        pt = round(pv / 0.94, 2)                             # 6% de desconto sobre a tabela
        vol, est = 4 + (i * 7) % 90, 10 + (i * 17) % 300
        prods.append({"PRODUTO": f"BAP{30100 + i}", "DESCRIÇÃO": f"PEÇA FICTICIA {i + 1:03d}", "CATEGORIA": _CATS[i % 5],
                      "SISTEMA": f"SISTEMA {i % 4 + 1}", "FAMÍLIA": f"FAMÍLIA {i % 7 + 1:02d}", "LINHA": _LINHA[i % 3],
                      "FORNECEDOR": f"FORNECEDOR FICTICIO {i % 4 + 1:02d}", "ORIGEM CUSTO": "ÚLTIMA ENTRADA",
                      "SITUAÇÃO": "ABAIXO DO MÍNIMO" if mkv < 28 else "OK", "ESTOQUE": est, "EST.": est,
                      "CUSTO UNIT.": cu, "PRC. TABELA MÉD.": pt, "PRC. VENDA MÉD.": pv,
                      "MKP TABELA %": round((pt / cu - 1) * 100, 1), "MKP VENDA %": float(mkv), "MKP REAL %": float(mkv),
                      "VOL. VENDIDO": vol, "QTD VEND.": vol, "R$ VENDA": round(pv * vol, 2), "CUSTO": round(cu * vol, 2),
                      "MARGEM": round((pv - cu) * vol, 2), "% DESC.": 6.0, "PREÇO INTERIOR MÉDIO": round(pv * 1.04, 2),
                      "MKP INTERIOR %": round((pv * 1.04 / cu - 1) * 100, 1), "ÚLT. VENDA": f"2026-11-{i % 19 + 3:02d}",
                      "SEM CUSTO": 0})
    marg_prod = sum(p["MARGEM"] for p in prods)
    for p in prods:
        p["PART. MARGEM"] = round(p["MARGEM"] / marg_prod * 100, 1)

    def pagr(chave):
        gs = _agrupa(prods, chave, ("ESTOQUE", "R$ VENDA", "VOL. VENDIDO", "CUSTO", "MARGEM", "SEM CUSTO"))
        for g in gs:
            mk_ = round((g["R$ VENDA"] / g["CUSTO"] - 1) * 100, 1)
            g.update({"PRODUTOS": g["_n"], "MKP REAL %": mk_, "MKP VENDA %": mk_, "MKP TABELA %": round(mk_ + 7.5, 1),
                      "% DESC.": 6.0, "PART. MARGEM": round(g["MARGEM"] / marg_prod * 100, 1)})
        return gs
    venda, custo = sum(p["R$ VENDA"] for p in peds), sum(p["CUSTO"] for p in peds)
    abaixo = sum(p["SITUAÇÃO"] == "ABAIXO DO MÍNIMO" for p in peds)
    aberto = sum(p["STATUS"] == "EM ABERTO" for p in peds)
    kpis = [_kpi("Venda", _brl(venda), detalhe=f"{n} pedidos"), _kpi("Custo", _brl(custo)),
            _kpi("Margem", _brl(venda - custo), "ok"),
            _kpi("Markup", _pct((venda / custo - 1) * 100), "ok", "mínimo 25,0%"),
            _kpi("Abaixo do mínimo", str(abaixo), "alerta" if abaixo else "ok", "pedidos"),
            _kpi("Sem custo", "0", "ok", "pedidos"), _kpi("Em aberto", str(aberto), detalhe="pedidos")]
    ts = [_linhas("vc_markup", "Por pedido", peds)]
    ts += [_linhas("vc_markup", t, agr(c)) for t, c in (("Por UF", "UF"), ("Por cidade", "CIDADE"),
                                                          ("Por supervisor", "SUPERVISOR"), ("Por vendedor", "VENDEDOR"))]
    ts += [_linhas("vc_markup", t, pagr(c)) for t, c in (("Por categoria", "CATEGORIA"), ("Por sistema", "SISTEMA"),
                                                           ("Por família", "FAMÍLIA"), ("Por linha", "LINHA"))]
    return kpis, ts + [_linhas("vc_markup", "Por produto", prods), _linhas("vc_markup", "Todos os produtos", prods)]


def _preco_grupo(nome, chave, i, fat0):
    """Um grupo de OUT para NOV: os 3 efeitos (preço, volume e mix) somam a variação do faturamento em R$."""
    vp, vv = round(-3.0 + (i * 2.3) % 9, 1), round(-8.0 + (i * 4.1) % 18, 1)    # var. de preço e de volume, em %
    q0 = round(fat0 / (40 + i * 3))
    p0 = fat0 / q0
    q1, p1 = round(q0 * (1 + vv / 100)), p0 * (1 + vp / 100)
    fat1 = round(q1 * p1 * (1 + (i % 3 - 1) * 0.012), 2)   # o mix (troca de produto dentro do grupo) mexe ±1,2%
    ef_preco, ef_vol = round((p1 - p0) * q1, 2), round((q1 - q0) * p0, 2)
    leitura = ("PREÇO SUBIU, VOLUME CAIU" if vp > 0 >= vv else "PREÇO E VOLUME SUBIRAM" if vp > 0
               else "PREÇO CAIU, VOLUME SUBIU" if vv > 0 else "PREÇO E VOLUME CAÍRAM")
    return {"MÊS": "NOV/2026", "AAAA-MM": "2026-11", chave: nome, "LEITURA": leitura, "FATURAMENTO": fat1,
            "VAR. FAT. %": round((fat1 / fat0 - 1) * 100, 1), "VOLUME": q1, "VAR. VOL. %": round((q1 / q0 - 1) * 100, 1),
            "PREÇO MÉDIO": round(fat1 / q1, 2), "PREÇO TABELA": round(p1 / 0.94, 2), "VAR. PREÇO %": vp,
            "VAR. TABELA %": round(vp + 0.5, 1), "VAR. FAT. R$": round(fat1 - fat0, 2), "EFEITO PREÇO": ef_preco,
            "EFEITO VOLUME": ef_vol, "EFEITO MIX": round(fat1 - fat0 - ef_preco - ef_vol, 2),
            "ELASTICIDADE": round((q1 / q0 - 1) / (vp / 100), 2) if vp else 0.0}


def _preco(n):
    cats = [_preco_grupo(c, "CATEGORIA", i, 380000 - i * 52000) for i, c in enumerate(_CATS)]
    fams = [_preco_grupo(f"FAMÍLIA {i + 1:02d}", "FAMÍLIA", i, 160000 - i * 9000) for i in range(14)]
    f0 = sum(c["FATURAMENTO"] - c["VAR. FAT. R$"] for c in cats)
    tot = {k: round(sum(c[k] for c in cats), 2)
           for k in ("FATURAMENTO", "VAR. FAT. R$", "EFEITO PREÇO", "EFEITO VOLUME", "EFEITO MIX", "VOLUME")}
    tot.update({"MÊS": "NOV/2026", "AAAA-MM": "2026-11", "TOTAL": "BAP", "PREÇO MÉDIO": round(tot["FATURAMENTO"] / tot["VOLUME"], 2),
                "VAR. FAT. %": round((tot["FATURAMENTO"] / f0 - 1) * 100, 1),
                "LEITURA": "PREÇO SUBIU" if tot["EFEITO PREÇO"] > 0 else "PREÇO CAIU"})
    reaj = []
    for i in range(n):
        ta, vt = round(40.9 + (i * 23) % 380, 2), float(3 + i % 5)
        pa = round(ta * 0.94, 2)
        pp = round(pa * (1 + (vt - 1.5 + i % 3) / 100), 2)
        qa = 20 + (i * 9) % 120
        q = max(1, round(qa * (1 - (i % 7 - 2) * 0.04)))
        reaj.append({"MÊS": "NOV/2026", "AAAA-MM": "2026-11", "FILIAL": _FILIAL[i % 3], "CÓD. PRODUTO": f"BAP{30100 + i}",
                     "PRODUTO": f"PEÇA FICTICIA {i + 1:03d}", "CATEGORIA": _CATS[i % 5], "FAMÍLIA": f"FAMÍLIA {i % 7 + 1:02d}",
                     "LEITURA": "VENDA CAIU APÓS REAJUSTE" if q < qa else "VENDA MANTIDA", "TABELA ANTES": ta,
                     "TABELA AGORA": round(ta * (1 + vt / 100), 2), "VAR. TABELA %": vt, "PRATICADO ANTES": pa,
                     "PREÇO PRATICADO": pp, "VAR. PREÇO %": round((pp / pa - 1) * 100, 1), "QTD ANTES": qa, "QTD": q,
                     "VAR. QTD %": round((q / qa - 1) * 100, 1), "FAT. ANTES": round(pa * qa, 2),
                     "FATURAMENTO": round(pp * q, 2), "VAR. FAT. %": round((pp * q / (pa * qa) - 1) * 100, 1),
                     "SISTEMA": f"SISTEMA {i % 4 + 1}", "LINHA": _LINHA[i % 3]})
    pesq = []
    for i in range(24):
        cb = round(60 + i * 7.5, 2)
        cc = round(cb * (0.92 + i % 5 * 0.04), 2)
        vb, vc = round(cb * 1.45, 2), round(cc * 1.5, 2)
        eb, ec, volb, volc = 20 + i % 9 * 5, 15 + i % 6 * 7, 10 + i % 8 * 3, 8 + i % 5 * 4
        pesq.append({"MÊS": "2026-11", "DATA": f"2026-11-{i % 19 + 3:02d}", "VENDEDOR": _vend(i), "SUPERVISOR": _sup(i),
                     "CIDADE": f"CIDADE FICTICIA {i % 5 + 1:02d}", "UF": _UF[i % 3], "SEGMENTO": "AUTOPEÇAS",
                     "LINHA DIA FOCO": "LEVE", "PAPEL": "PREÇO", "CÓD. BAP": f"BAP{30100 + i}",
                     "PRODUTO": f"PEÇA FICTICIA {i + 1:03d}", "CONCORRENTE": f"CONCORRENTE {'ABC'[i % 3]}",
                     "CÓD. CONCORRENTE": f"C{900 + i}", "LEITURA": "BAP MAIS CARA" if cb > cc else "BAP MAIS BARATA",
                     "COMPRA BAP": cb, "COMPRA CONC.": cc, "DIF. COMPRA %": round((cb / cc - 1) * 100, 1),
                     "VENDA BAP": vb, "VENDA CONC.": vc, "DIF. VENDA %": round((vb / vc - 1) * 100, 1),
                     "MKP CLIENTE BAP %": round((vb / cb - 1) * 100, 1), "MKP CLIENTE CONC. %": round((vc / cc - 1) * 100, 1),
                     "PRC. TABELA BAP": round(cb / 0.94, 2), "COMPRA x TABELA %": -6.0, "ESTOQUE BAP": eb,
                     "ESTOQUE CONC.": ec, "SHARE ESTOQUE %": round(eb / (eb + ec) * 100, 1), "VOL. BAP": volb,
                     "VOL. CONC.": volc, "SHARE VOLUME %": round(volb / (volb + volc) * 100, 1),
                     "OBSERVAÇÃO": "Sem observação.", "CATEGORIA": _CATS[i % 5], "FAMÍLIA": f"FAMÍLIA {i % 7 + 1:02d}"})
    queda = sum(r["QTD"] < r["QTD ANTES"] for r in reaj)
    sinal = lambda v: "ok" if v >= 0 else "alerta"   # noqa: E731
    kpis = [_kpi("Faturamento NOV", _brl(tot["FATURAMENTO"]), detalhe=_pct(tot["VAR. FAT. %"]) + " sobre OUT"),
            _kpi("Efeito preço", _brl(tot["EFEITO PREÇO"]), sinal(tot["EFEITO PREÇO"])),
            _kpi("Efeito volume", _brl(tot["EFEITO VOLUME"]), sinal(tot["EFEITO VOLUME"])),
            _kpi("Efeito mix", _brl(tot["EFEITO MIX"])), _kpi("Reajustes", str(len(reaj)), detalhe="produtos"),
            _kpi("Queda após reajuste", str(queda), "atencao" if queda else "ok", "produtos")]
    return kpis, [_linhas("vc_preco", "Por categoria", cats), _linhas("vc_preco", "Por família", fams),
                  _linhas("vc_preco", "Total BAP", [tot]), _linhas("vc_preco", "Reajustes por produto", reaj),
                  _linhas("vc_preco", "Pesquisa de mercado", pesq)]


def _divergencias(n):
    sits = ("VENDEDOR DIFERENTE", "SEM VENDEDOR NO PLANNER", "FORA DA BASE DO PLANNER")
    fazer = ("Corrigir o vendedor no Protheus", "Pôr o cliente na rota do Planner", "Conferir o cadastro no Planner")
    divs = [{"COD": f"9{i:05d}", "LOJA": "01", "CIDADE": f"CIDADE FICTICIA {i % 5 + 1:02d}", "UF": _UF[i % 3],
             "SEGMENTO": "AUTOPEÇAS", "ZONA": f"ZONA {i % 4 + 1}", "VENDEDOR PLANNER": _vend(i) if i % 3 == 0 else "",
             "VENDEDOR PROTHEUS (A1_VEND)": _vend(i + 1), "STATUS PROTHEUS": "ATIVO", "SITUAÇÃO": sits[i % 3],
             "O QUE FAZER": fazer[i % 3]} for i in range(min(n, 30))]
    vends = []
    for v in range(6):                      # a contagem por vendedor (o do Protheus) sai da lista de divergentes
        minhas = [d for d in divs if d["VENDEDOR PROTHEUS (A1_VEND)"] == _vend(v)]
        dif, semv, fora = (sum(d["SITUAÇÃO"] == x for d in minhas) for x in sits)
        iguais = 120 + v * 17
        vends.append({"VENDEDOR": _vend(v), "SUPERVISOR": _sup(v), "CARTEIRA PLANNER": iguais + dif,
                      "BASE PROTHEUS": iguais + dif + semv + fora, "IGUAIS": iguais, "SÓ NO PLANNER": dif,
                      "SÓ NO PROTHEUS": dif + semv + fora, "· FORA DA BASE": fora, "· PLANNER SEM VENDEDOR": semv,
                      "BATE?": "SIM" if not minhas else "NÃO"})
    semc = [{"CÓD.": f"9{500 + i:05d}", "LOJA": "01", "O QUE FALTA": ("COORDENADA", "ENDEREÇO", "COORDENADA E ENDEREÇO")[i % 3],
             "NA ROTA DO MÊS": "SIM" if i % 2 else "NÃO", "UF": _UF[i % 3], "CIDADE": f"CIDADE FICTICIA {i % 5 + 1:02d}",
             "VENDEDOR PLANNER": _vend(i), "SUPERVISOR PLANNER": _sup(i), "SEGMENTO": "AUTOPEÇAS", "CURVA": "ABC"[i % 3],
             "SITUAÇÃO": "ATIVO", "PONTO": "SEM COORDENADA"} for i in range(18)]
    base, bate = sum(v["CARTEIRA PLANNER"] for v in vends), sum(v["IGUAIS"] for v in vends)
    conta = lambda s: str(sum(d["SITUAÇÃO"] == s for d in divs))   # noqa: E731
    kpis = [_kpi("Clientes na base (Planner)", _qtd(base)), _kpi("Batem", _qtd(bate), "ok", _pct(bate / base * 100)),
            _kpi("Vendedor diferente", conta(sits[0]), "alerta"), _kpi("Sem vendedor no Planner", conta(sits[1]), "atencao"),
            _kpi("Fora da base do Planner", conta(sits[2]), "atencao"), _kpi("Código duplicado", "0", "ok"),
            _kpi("Sem coordenada / endereço", str(len(semc)), "atencao")]
    return kpis, [_linhas("an_divergencias", "Por vendedor", vends), _linhas("an_divergencias", "Clientes divergentes", divs),
                  _linhas("an_divergencias", "Sem coordenada / endereço", semc)]


def pacote_coerente(n=40):
    """O pacote da simulação PNG: os 4 faróis com números que fecham entre si (sem dado real)."""
    pacote = pacote_analista(n=1)
    for rid, gerar in (("vc_saldo", _saldo), ("vc_markup", _markup), ("vc_preco", _preco),
                       ("an_divergencias", _divergencias)):
        kpis, ts = gerar(n)
        f = pacote["relatorios"][rid]
        f.pop("recortes", None)
        f.update({"kpis": kpis, "tabelas": ts})
    return pacote
