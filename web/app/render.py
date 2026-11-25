"""Renderizador do cartão RRM (Painel · resultado e Painel · produtividade).

A web só mostra os números que o PC mandou prontos (painel_rrm.calcular):
nada é recalculado. O que sobra aqui é apresentação: formato do percentual,
geometria do anel (SVG) e altura relativa da barra, como o desenho do PC
(`painel_rrm._cartao_pil`, `bap_visual`, paleta CLARO).
"""
from __future__ import annotations

import math
import re
import unicodedata

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
AVISO_UF = "Resumo e gráficos: BAP inteira."
SEM_DADO_UF = "Sem números de {uf} neste pacote."
SEM_RECORTE = "só na BAP inteira"
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
    if formato == "hora":                      # segundos do dia -> 09:48 (como o bap_visual)
        s_ = int(round(v))
        return f"{s_ // 3600:02d}:{s_ % 3600 // 60:02d}"
    if formato == "min":                       # segundos -> 25 min (TMA/TMD)
        return f"{br(v / 60.0, 0)} min"
    if formato == "num1" or (isinstance(v, float) and abs(v) < 100 and v % 1):
        return br(v, 1)
    return br(v)


NBSP = "\u00a0"


def junta(txt) -> str:
    """Não quebra o rótulo no meio do número: só entre o número e 'mil'/'mi'."""
    t = str(txt or "")
    corpo, _, fim = t.rpartition(" ")
    if fim in ("mil", "mi") and corpo:
        return corpo.replace(" ", NBSP) + " " + fim
    return t.replace(" ", NBSP)


def _mini(est) -> dict | None:
    """Barrinhas por estado dentro do cartão (as mesmas do PC): `estados.barras` pronto."""
    b = _barras(est)
    if not b:
        return None
    for x in b["barras"]:
        x["txt"] = junta(x["txt"])
    return b


def _kpi(k) -> dict | None:
    if not isinstance(k, dict):
        return None
    linhas = []
    for ln in _lista(k.get("linhas")):
        if isinstance(ln, (list, tuple)) and len(ln) >= 2:
            linhas.append({"rot": str(ln[0]), "valor": str(ln[1]),
                           "tom": _tom(ln[2] if len(ln) > 2 else "")})
    return {"rot": str(k.get("rotulo", "")), "valor": str(k.get("valor", "—")),
            "cor": _tom(k.get("cor")), "detalhe": str(k.get("detalhe") or ""), "linhas": linhas,
            "estados": _mini(k.get("estados"))}


def kpis_para_tela(kpis) -> list[dict]:
    """Os cartões prontos do PC (`kpis` ou `kpis_padrao` da aba) já na forma da tela."""
    return [k for k in map(_kpi, _lista(kpis)) if k and not cartao_vazio(k)]


# T-0020 (decisão do Alexandre, 25/11/2026): cartão sem dado não aparece e o resumo gerencial não repete
# o número que já está nos cartões (R$, % e contagem; a frase só sai quando TODOS os números dela já estão lá).
_NUM_TELA = re.compile(r"R\$ ?-?\d[\d.,]*(?: ?(?:mi|mil)\b)?|-?\d[\d.,]*%|\d[\d.,]*\d|\d")


def _numeros(txt) -> set[str]:
    return {re.sub(r"\s+", " ", m) for m in _NUM_TELA.findall(str(txt or ""))}


def cartao_vazio(k: dict) -> bool:
    """Cartão só com "—" (sem detalhe, linhas nem barras): não aparece na tela."""
    return (str(k.get("valor", "")).strip() in ("", "—", "–", "-") and not k.get("detalhe")
            and not k.get("linhas") and not k.get("estados"))


def sem_repeticao(insights: list[dict], kpis: list[dict]) -> list[dict]:
    """Tira do resumo a frase cujos números (R$, % e contagens) já aparecem todos nos cartões."""
    vistos: set[str] = set()
    for k in kpis:
        for txt in [k.get("rot"), k.get("valor"), k.get("detalhe")] + [
                x for ln in k.get("linhas", []) for x in (ln.get("rot"), ln.get("valor"))]:
            vistos |= _numeros(txt)
    return [i for i in insights if not (_numeros(i.get("texto")) and _numeros(i.get("texto")) <= vistos)]


def datas_proximas(a, b, minutos: int = 60) -> bool:
    """T-0020: o "Baixado do ERP" só aparece quando fica a mais de `minutos` da hora do pacote."""
    from datetime import datetime
    try:
        return abs((datetime.fromisoformat(str(a)) - datetime.fromisoformat(str(b))).total_seconds()) <= minutos * 60
    except (TypeError, ValueError):
        return False


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
            bs.append({"txt": "" if not v else junta(txt), "titulo": f"{rot}: {txt}" if v else "",
                       "alt": 0 if not v else round(max(3.0, 100 * abs(v) / mx), 1),
                       "cor": s["cor_neg"] if (v or 0) < 0 else s["cor"]})
        cols.append({"rot": rot, "barras": bs})
    nbarras = len(cols) * max(len(series), 1)
    maxrot = max([len(c["rot"]) for c in cols] or [0])
    denso = len(cols) > 14
    return {"tipo": "barras", "titulo": str(g.get("titulo", "")), "cols": cols,
            "denso": denso, "vert": 8 < nbarras and not denso,       # valor em pé: não se sobrepõe
            "rotv": (len(cols) > 5 and maxrot > 5) or (len(cols) > 8 and maxrot > (3 if denso else 4)),   # data/nome comprido em pé
            "legenda": [{"nome": s["nome"], "cor": s["cor"]} for s in series if s["nome"]] if len(series) > 1 else [],
            "meta": {"pos": round(100 * abs(meta) / mx, 1), "txt": fmt_valor(meta, formato)} if meta else None,
            "largo": len(cols) > 8}


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


MAX_LINHAS_TAB = 200
# Colunas que nunca vão ao site (contrato §10.7.4, bloco `colunas-fora`): a lista é daqui, e o
# `tabelas` importa. Nome inteiro, sem acento e em maiúsculas.
COLUNAS_FORA = frozenset({"TELEFONE", "CELULAR", "WHATSAPP", "CNPJ", "CPF", "E-MAIL", "EMAIL", "CONTATO",
                         "FOTO", "ENDERECO"})
_CLIENTE_NO_BLOCO = re.compile(r"cliente|raz[aã]o|fantasia", re.I)     # regra a mais, só do bloco tabela (§10.1)
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _sem_acento(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").upper()


def coluna_fora(nome) -> bool:
    return _sem_acento(nome).strip() in COLUNAS_FORA


def coluna_proibida(nome) -> bool:
    """Bloco tabela do painel: a lista do contrato mais coluna de cliente (regra 6 do CLAUDE.md)."""
    return coluna_fora(nome) or bool(_CLIENTE_NO_BLOCO.search(str(nome or "")))


def _nome_col(c) -> str:
    return str(c.get("nome", "")) if isinstance(c, dict) else str(c)


def _tipo_col(c) -> str:
    return str(c.get("tipo", "texto")) if isinstance(c, dict) else "texto"


def fmt_celula(v, tipo, centavos=False, painel=False) -> str:
    """Texto da célula de tabela (a única função: abas, juntas, bloco tabela do painel).
    Moeda sem centavos como o PC; `centavos=True` (Inadimplência) mantém as 2 casas.
    `painel=True` (bloco tabela do Painel e dos faróis): o jeito que o Painel já mostra no ar:
    vazio fora de coluna de texto vira "—" e pct/pct1 levam 1 casa decimal."""
    if painel:
        if v is None or v == "":
            return "—" if tipo != "texto" else ""
        if isinstance(v, str):
            return v
        n = _num(v)
        if n is None:
            return str(v)
        if tipo in ("moeda", "moeda2"):
            return ("−" if n < 0 else "") + "R$ " + br(abs(n), 2 if tipo == "moeda2" else 0)
        if tipo in ("pct", "pct1"):
            return br(n, 1) + "%"
        if tipo in ("num1", "dia"):
            return br(n, 1)
        if tipo == "num2":
            return br(n, 2)
        return br(n, 0 if float(n).is_integer() else 1)
    if v is None or v == "":
        return ""
    n = _num(v)
    if tipo in ("moeda", "moeda2") and n is not None:
        return ("−" if n < 0 else "") + "R$ " + br(abs(n), 2 if (centavos or tipo == "moeda2") else 0)
    if tipo == "int" and n is not None:
        return f"{int(n):,}".replace(",", ".")
    if tipo in ("num", "valor") and n is not None:
        return br(n, 0 if float(n).is_integer() else 1)
    if tipo == "num1" and n is not None:
        return br(n, 1)
    if tipo == "num2" and n is not None:
        return br(n, 2)
    if tipo == "pct" and n is not None:
        return br(n, 0) + "%"
    if tipo == "pct1" and n is not None:
        return br(n, 1) + "%"
    if tipo in ("data", "dia") and isinstance(v, str) and RE_DATA.match(v):
        return f"{v[8:10]}/{v[5:7]}/{v[:4]}"             # sempre com ano
    return str(v)


def _bloco_tabela(b) -> dict:
    """Bloco `tabela` do painel, na forma que o macro `grade` desenha (a mesma das abas)."""
    cols = _lista(b.get("colunas"))
    if not cols or len(cols) > 20:
        raise ValueError("colunas")
    vis = [i for i, c in enumerate(cols) if not (isinstance(c, dict) and c.get("oculta"))]
    vis = vis[:1] + [i for i in vis[1:] if _tipo_col(cols[i]) != "texto"] + [i for i in vis[1:] if _tipo_col(cols[i]) == "texto"]

    def cel(ln, i):
        return {"t": fmt_celula(ln[i] if i < len(ln) else None, _tipo_col(cols[i]), painel=True), "f": None, "c": None, "b": None}

    linhas = [{"tom": "", "cel": [cel(_lista(ln), i) for i in vis]}
              for ln in _lista(b.get("linhas"))[:MAX_LINHAS_TAB]]
    tot = _lista(b.get("total"))
    return {"tipo": "tabela", "titulo": str(b.get("titulo", "")),
            "cols": [{"i": i, "nome": _nome_col(cols[i]), "tipo": _tipo_col(cols[i]),
                      "num": _tipo_col(cols[i]) != "texto", "inteira": False, "livre": False} for i in vis],
            "linhas": linhas, "total": [cel(tot, i) for i in vis] if tot else None, "zebra": False,
            "ord": None, "desc": False}


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
            elif b.get("tipo") == "tabela":
                out.append(_bloco_tabela(b))
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


def farol_para_tela(rel: dict, uf: str | None = None, rid: str | None = None) -> dict:
    ufs = recortes_farol(rel)
    uf = (uf or "").upper()
    sem_dado = False
    if uf in ufs:
        rec = [r for r in _lista(rel["recortes"][uf].get("kpis")) if isinstance(r, dict)]
        todos = [k for k in _lista(rel.get("kpis")) if isinstance(k, dict)]
        # cartão da BAP inteira que o estado não tem (ex.: fotos sem filial): "—" e a dica
        kpis = [next((r for r in rec if r.get("rotulo") == k.get("rotulo")), None)
                or {"rotulo": k.get("rotulo", ""), "valor": "—", "cor": "neutro", "detalhe": SEM_RECORTE}
                for k in todos]
        kpis += [r for r in rec if r.get("rotulo") not in {k.get("rotulo") for k in todos}]
    elif re.match(r"^[A-Z]{2}$", uf):
        sem_dado = True
        # estado sem recorte: "—" nos cartões, nunca o número da BAP inteira
        kpis = [{"rotulo": k.get("rotulo", ""), "valor": "—", "cor": "neutro"}
                for k in _lista(rel.get("kpis")) if isinstance(k, dict)]
    else:
        uf, kpis = None, rel.get("kpis")
    ins_blocos, blocos = _blocos(rel.get("painel"))
    cartoes = [k for k in map(_kpi, _lista(kpis)) if k and not cartao_vazio(k)]
    return {"titulo": str(rel.get("titulo", "")), "ufs": ufs, "uf": uf,
            "faixa": bool(rel.get("kpis_faixa")),   # cartões em faixa fina, como o PC
            "kpis": cartoes,
            "insights": sem_repeticao(_insights(rel.get("insights_painel")) or ins_blocos, cartoes), "blocos": blocos,
            "avisos": [str(a) for a in _lista(rel.get("avisos")) if not str(a).startswith("Sem filtro por estado")],
            "avisos_info": [str(a) for a in _lista(rel.get("avisos")) if str(a).startswith("Sem filtro por estado")],
            "aviso_uf": ((SEM_DADO_UF.format(uf=uf) + " ") if sem_dado else "") + AVISO_UF if uf else "", "baixado_em": rel.get("baixado_em")}
