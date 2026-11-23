"""Renderizador do cartão RRM (Painel · resultado e Painel · produtividade).

A web só mostra os números que o PC mandou prontos (painel_rrm.calcular):
nada é recalculado. O que sobra aqui é apresentação: formato do percentual,
geometria do anel (SVG) e altura relativa da barra, como o desenho do PC
(`painel_rrm._cartao_pil`, `bap_visual`, paleta CLARO).
"""
from __future__ import annotations

import math

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
