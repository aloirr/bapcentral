"""Renderizador do cartão RRM (Painel · resultado e Painel · produtividade).

A web só mostra os números que o PC mandou prontos (painel_rrm.calcular):
nada é recalculado. O que sobra aqui é apresentação: formato do percentual,
geometria do anel (SVG) e altura relativa da barra, como o desenho do PC
(`painel_rrm._cartao_pil`, `bap_visual`, paleta CLARO).
"""
from __future__ import annotations

import math
import re

R_ANEL = 34
CIRC = 2 * math.pi * R_ANEL
TITULOS = {"res": "Painel do Diretor · resultado",
           "prod": "Painel do Diretor · produtividade"}


def br(v, d=0) -> str:
    s = f"{v:,.{d}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def pc(v) -> str:
    return "—" if v is None else br(v) + "%"


def tom_de(p) -> str:
    """Cor do anel: mesma faixa do PC (verde >= 100, amarelo 90-99, vermelho < 90)."""
    if p is None:
        return ""
    return "ok" if p >= 100 else ("atencao" if p >= 90 else "alerta")


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _anel(a) -> dict:
    rot, p, sub = (list(a) + [None, None, None])[:3]
    p = _num(p)
    frac = 0.0 if p is None else max(1.0, min(p, 99.9)) / 100
    return {"rot": rot, "pct": pc(p) if p is not None else "", "sub": sub or "",
            "tom": tom_de(p), "arco": round(CIRC * frac, 1), "circ": round(CIRC, 1),
            "tem": p is not None}


def _faixa(f) -> dict:
    rot, var, tom, real = (list(f) + ["", "", "", ""])[:4]
    return {"rot": rot, "var": var or "", "tom": tom if tom in ("ok", "atencao", "alerta") else "",
            "real": real or "—"}


def _barras(est) -> dict | None:
    bs = (est or {}).get("barras") or []
    if not bs:
        return None
    vals = [abs(b[1]) for b in bs if len(b) > 1 and _num(b[1])]
    mx = max(vals) if vals else 1
    out = []
    for b in bs:
        uf, v, txt, rot, tom = (list(b) + [None, "", "", ""])[:5]
        v = _num(v)
        out.append({"uf": uf, "vazio": v is None, "sem_barra": v is not None and v <= 0,
                    "alt": 0 if not v or v <= 0 else round(12 + 80 * abs(v) / mx, 1),
                    "txt": txt or "", "rot": rot or "",
                    "tom": tom if tom in ("ok", "atencao", "alerta") else ""})
    return {"barras": out, "legenda": est.get("legenda") or ""}


def cartao(c: dict) -> dict:
    return {"titulo": str(c.get("titulo", "")).upper(), "valor": c.get("valor", ""),
            "legenda": c.get("legenda") or "",
            "aneis": [_anel(a) for a in c.get("aneis") or []],
            "faixa": [_faixa(f) for f in (c.get("faixa") or [])[:3]],
            "estados": _barras(c.get("estados")), "ajuda": c.get("ajuda") or ""}


CHAVES_ABAS = (("resultado", "res"), ("produtividade", "prod"))   # = painel_rrm.VISOES; fonte única (pacotes.ABAS usa esta)


def localizar_abas(rel: dict) -> list[dict]:
    """`rel["abas"]` = {"resultado": aba, "produtividade": aba}; cada aba tem
    `titulo`, `kpis_export`, `painel.blocos[0]` (tipo rrm, visao, dados) e `altura_min`."""
    abas = []
    for chave, visao in CHAVES_ABAS:
        a = (rel.get("abas") or {}).get(chave)
        if not a:
            continue
        b = ((a.get("painel") or {}).get("blocos") or [{}])[0]
        abas.append({"chave": chave, "titulo": a.get("titulo", ""), "visao": visao,
                     "dados": b.get("dados") or {}, "recortes": a.get("recortes") or {}})
    return abas


COMO_LER_ESTADO = ("Número do estado como na barra dele no Painel do Diretor do PC; "
                   "% = atingimento da meta do estado, ou variação × mês anterior sem meta. "
                   "Cartão com — não tem número por estado.")


def filtros(aba: dict) -> dict:
    """T-0014: as visões prontas que o PC mandou para esta aba (nada é calculado aqui)."""
    rec = aba.get("recortes") or {}
    return {"ufs": list((rec.get("uf") or {}).keys())}


def escolher_uf(aba: dict, uf: str | None = None) -> str | None:
    """O estado escolhido; fora da lista = BAP inteira."""
    f = filtros(aba)
    uf = (uf or "").upper() or None
    return uf if uf in f["ufs"] else None


def aba_para_tela(aba: dict, uf: str | None = None) -> dict:
    d, v = aba["dados"], aba["visao"]
    sub = (d.get("sub") or {}).get(v, "")
    cartoes = d.get(v) or []
    como_ler = d.get("como_ler") or ""
    if uf:
        # o "como ler" da BAP inteira fala de anel, faixa e barras, que a visão do estado não tem
        como_ler = COMO_LER_ESTADO
        cartoes = ((aba.get("recortes") or {}).get("uf") or {}).get(uf, {}).get("cartoes") or []
        sub = f"{uf} · estado = filial da nota · {sub}" if sub else f"{uf} · estado = filial da nota"
    return {"titulo": TITULOS[v], "sub": sub, "uf": uf,
            "cartoes": [cartao(c) for c in cartoes],
            "como_ler": como_ler, "avisos": d.get("avisos") or []}


# ---------------------------------------------------------------- faróis (T-0017)
# Forma "farol" do pacote (contrato §10): o PC manda kpis, insights e blocos do painel
# prontos. Aqui só se desenha (barras em HTML/CSS); nada é recalculado.
FAROIS = {  # rid -> (nome no PC, perfis que veem)
    "pv_pedidos": ("Farol de Pedidos", ("admin", "diretor", "gerente", "pre_venda")),
    "vc_visitas": ("Farol de Visita", ("admin", "diretor", "gerente", "vendas")),
    "pl_entregas": ("Farol de Entregas", ("admin", "diretor", "gerente", "pos_venda")),
    "pl_inadimplencia": ("Farol de Inadimplência", ("admin", "diretor", "gerente", "pos_venda")),
}
TONS = ("ok", "atencao", "alerta", "info")
AVISO_UF = "Cartões por estado; gráficos da BAP inteira"
INDISPONIVEL = "ainda não disponível na web"
_COR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def farois_do_perfil(perfil: str) -> list[tuple[str, str]]:
    return [(rid, nome) for rid, (nome, perfis) in FAROIS.items() if perfil in perfis]


def _tom(t) -> str:
    return t if t in TONS else ""


def _lista(v) -> list:
    return v if isinstance(v, list) else []


def moeda(v) -> str:
    a, sinal = abs(v), "−" if v < 0 else ""
    if a >= 1e6:
        return f"{sinal}R$ {br(a / 1e6, 2)} mi"
    if a >= 1e4:
        return f"{sinal}R$ {br(a / 1e3, 0 if round(a / 1e3, 1) % 1 == 0 else 1)} mil"
    return f"{sinal}R$ {br(a)}"


def fmt_valor(v, formato) -> str:
    v = _num(v)
    if v is None:
        return "—"
    if formato == "moeda":
        return moeda(v)
    if formato in ("pct", "pct1"):
        return br(v, 1) + "%"
    if formato == "dias":
        return br(v, 1) + " dia(s)"
    if formato == "num1" or (isinstance(v, float) and abs(v) < 100 and v % 1):
        return br(v, 1)
    return br(v)


def _kpi(k) -> dict | None:
    if not isinstance(k, dict):
        return None
    linhas = []
    for ln in _lista(k.get("linhas")):
        if isinstance(ln, (list, tuple)) and len(ln) >= 2:
            linhas.append({"rot": str(ln[0]), "valor": str(ln[1]),
                           "tom": _tom(ln[2] if len(ln) > 2 else "")})
    return {"rot": str(k.get("rotulo", "")), "valor": str(k.get("valor", "—")),
            "cor": _tom(k.get("cor")), "detalhe": str(k.get("detalhe") or ""), "linhas": linhas}


def _insights(linhas) -> list[dict]:
    out = []
    for ln in _lista(linhas):
        if isinstance(ln, (list, tuple)) and len(ln) >= 2:
            out.append({"tom": _tom(ln[0]), "texto": str(ln[1])})
    return out


def _cor(c, padrao) -> str:
    return c if isinstance(c, str) and _COR.match(c) else padrao


def _bloco_barras(b) -> dict:
    g = b.get("grafico")
    if not isinstance(g, dict):
        raise ValueError("sem gráfico")
    rotulos = [str(x) for x in _lista(g.get("rotulos"))]
    formato = g.get("formato", "num")
    series = []
    for s in _lista(g.get("series")):
        series.append({"nome": str(s.get("nome", "")), "cor": _cor(s.get("cor"), "#8fa79a"),
                       "cor_neg": _cor(s.get("cor_negativo"), "#b3261e"),
                       "vals": [_num(v) for v in _lista(s.get("valores"))],
                       "txt": [str(t) for t in _lista(s.get("rotulos"))]})
    meta = _num(g.get("meta"))
    mx = max([abs(v) for s in series for v in s["vals"] if v] + ([abs(meta)] if meta else []) or [1])
    cols = []
    for i, rot in enumerate(rotulos):
        bs = []
        for s in series:
            v = s["vals"][i] if i < len(s["vals"]) else None
            txt = s["txt"][i] if i < len(s["txt"]) else fmt_valor(v, formato)
            bs.append({"txt": "" if not v else txt,
                       "alt": 0 if not v else round(max(3.0, 100 * abs(v) / mx), 1),
                       "cor": s["cor_neg"] if (v or 0) < 0 else s["cor"]})
        cols.append({"rot": rot, "barras": bs})
    return {"tipo": "barras", "titulo": str(g.get("titulo", "")), "cols": cols,
            "legenda": [{"nome": s["nome"], "cor": s["cor"]} for s in series if s["nome"]] if len(series) > 1 else [],
            "meta": {"pos": round(100 * abs(meta) / mx, 1), "txt": fmt_valor(meta, formato)} if meta else None,
            "largo": len(cols) > 8, "denso": len(cols) > 14}


def _bloco_hbarras(b) -> dict:
    rot = [str(x) for x in _lista(b.get("rotulos"))]
    vals = [_num(v) for v in _lista(b.get("valores"))]
    cores = _lista(b.get("cores"))
    formato = b.get("formato", "num")
    ref = _num(b.get("referencia"))
    mx = max([abs(v) for v in vals if v] + ([abs(ref)] if ref else []) or [1])
    linhas = []
    for i, r_ in enumerate(rot):
        v = vals[i] if i < len(vals) else None
        linhas.append({"rot": r_, "txt": fmt_valor(v, formato),
                       "larg": 0 if not v else round(max(2.0, 100 * abs(v) / mx), 1),
                       "cor": _cor(cores[i] if i < len(cores) else None, "#8fa79a")})
    return {"tipo": "hbarras", "titulo": str(b.get("titulo", "")), "linhas": linhas,
            "ref": {"pos": round(100 * abs(ref) / mx, 1), "txt": fmt_valor(ref, formato)} if ref else None}


def _blocos(painel) -> tuple[list[dict], list[dict]]:
    """(insights do painel, blocos desenháveis). Tipo que não sabemos desenhar, ou bloco
    malformado, vira cartão 'ainda não disponível na web' sem quebrar a página."""
    ins, out = [], []
    blocos = [b for b in _lista((painel or {}).get("blocos")) if isinstance(b, dict)]
    blocos.sort(key=lambda b: (_num(b.get("row")) or 0, _num(b.get("col")) or 0))
    for b in blocos:
        try:
            if b.get("tipo") == "insights":
                ins += _insights(b.get("linhas"))
            elif b.get("tipo") == "barras":
                out.append(_bloco_barras(b))
            elif b.get("tipo") == "hbarras":
                out.append(_bloco_hbarras(b))
            else:
                raise ValueError("tipo desconhecido")
        except (ValueError, TypeError, AttributeError):
            g = b.get("grafico")
            titulo = b.get("titulo") or (g.get("titulo") if isinstance(g, dict) else "")
            out.append({"tipo": "indisponivel", "titulo": str(titulo or "")})
    return ins, out


def recortes_farol(rel: dict) -> list[str]:
    rec = rel.get("recortes")
    return sorted(rec) if isinstance(rec, dict) else []


def farol_para_tela(rel: dict, uf: str | None = None) -> dict:
    ufs = recortes_farol(rel)
    uf = (uf or "").upper()
    if uf in ufs:
        kpis = rel["recortes"][uf].get("kpis")
    elif re.match(r"^[A-Z]{2}$", uf):
        # estado sem recorte: "—" nos cartões, nunca o número da BAP inteira
        kpis = [{"rotulo": k.get("rotulo", ""), "valor": "—", "cor": "neutro"}
                for k in _lista(rel.get("kpis")) if isinstance(k, dict)]
    else:
        uf, kpis = None, rel.get("kpis")
    ins_blocos, blocos = _blocos(rel.get("painel"))
    return {"titulo": str(rel.get("titulo", "")), "ufs": ufs, "uf": uf,
            "kpis": [k for k in map(_kpi, _lista(kpis)) if k],
            "insights": _insights(rel.get("insights_painel")) or ins_blocos, "blocos": blocos,
            "avisos": [str(a) for a in _lista(rel.get("avisos"))],
            "aviso_uf": AVISO_UF if uf else "", "baixado_em": rel.get("baixado_em")}
