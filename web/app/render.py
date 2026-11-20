"""Renderizador genérico do contrato (parte dado): formato, filtro, ordem.

Sem regra de negócio: só apresenta o que o núcleo mandou (contrato §3, §4, §10).
"""
from __future__ import annotations

import re
from datetime import date, datetime

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
LIMITE_LINHAS = 300     # linhas desenhadas por tabela (celular); o resto vem pela busca
TONS = {"", "ok", "alerta", "atencao", "info", "azul", "cinza", "grave"}


def br(v, d=0) -> str:
    s = f"{v:,.{d}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _data(v):
    try:
        return datetime.fromisoformat(v) if isinstance(v, str) else None
    except ValueError:
        return None


def formatar(v, tipo="texto") -> str:
    if v is None or isinstance(v, (dict, list)):
        return ""
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if tipo in ("data", "dia"):
        d = _data(v)
        if d is not None:
            return d.strftime("%d/%m/%Y" if tipo == "data" else "%d/%m")
        return str(v)
    if isinstance(v, (int, float)):
        if tipo == "moeda":
            return "R$ " + br(v, 0)
        if tipo == "moeda2":
            return "R$ " + br(v, 2)
        if tipo == "pct":
            return br(v, 0) + "%"
        if tipo == "pct1":
            return br(v, 1) + "%"
        if tipo == "num1":
            return br(v, 1)
        if tipo == "num2":
            return br(v, 2)
        if tipo in ("int", "num", "valor"):
            return br(v, 0 if float(v).is_integer() else 1)
    return str(v)


def _chave(v):
    """Ordem: números antes de texto; vazio por último."""
    if v is None or v == "":
        return (2, 0, "")
    if isinstance(v, bool):
        return (0, int(v), "")
    if isinstance(v, (int, float)):
        return (0, v, "")
    return (1, 0, str(v).casefold())


def preparar_tabela(tab: dict, idx: int, args) -> dict:
    """Aplica filtros da URL (q, f<idx>_<col>, o, d) e devolve o que a tela mostra.

    Parâmetros da URL da tabela idx: `q` (busca), `f<col>` (valor da coluna),
    `o` (coluna de ordem) e `d` (desc). Só vale para a tabela `t == idx`.
    """
    cols = tab.get("colunas", [])
    n = len(cols)
    visiveis = [i for i, c in enumerate(cols) if not c.get("oculta")]
    ativa = args.get("t") == str(idx)
    q = (args.get("q") or "").strip().casefold() if ativa else ""
    linhas = [(i, l[:n]) for i, l in enumerate(tab.get("linhas", []))]
    tons = tab.get("tons") or []
    cores = tab.get("cores_celulas") or []
    # filtros por coluna (a lista `filtros` do contrato; nomes ou dict {"coluna"})
    filtros = []
    for f in tab.get("filtros") or []:
        nome = f.get("coluna") if isinstance(f, dict) else f
        for ci in visiveis:
            if cols[ci].get("nome") == nome:
                opcoes = sorted({formatar(l[ci], cols[ci].get("tipo", "texto"))
                                 for _, l in linhas if ci < len(l)} - {""}, key=_chave)
                filtros.append({"ci": ci, "nome": nome, "opcoes": opcoes,
                                "valor": args.get(f"f{ci}", "") if ativa else ""})
    for fl in filtros:
        if fl["valor"]:
            ci = fl["ci"]
            linhas = [(i, l) for i, l in linhas if ci < len(l)
                      and formatar(l[ci], cols[ci].get("tipo", "texto")) == fl["valor"]]
    if q:
        linhas = [(i, l) for i, l in linhas if any(
            q in formatar(l[ci], cols[ci].get("tipo", "texto")).casefold()
            for ci in visiveis if ci < len(l))]
    ordem, desc = None, False
    if ativa and (args.get("o") or "").isdigit() and int(args["o"]) in visiveis:
        ordem, desc = int(args["o"]), args.get("d") == "1"
        linhas.sort(key=lambda il: _chave(il[1][ordem] if ordem < len(il[1]) else None),
                    reverse=desc)
    # total só quando todas as linhas estão visíveis (contrato §11.3, sem total_de)
    total = tab.get("total") if len(linhas) == len(tab.get("linhas", [])) else None
    saida = []
    for i, l in linhas[:LIMITE_LINHAS]:
        tom = tons[i] if i < len(tons) and tons[i] in TONS else ""
        cc = cores[i] if i < len(cores) and isinstance(cores[i], dict) else {}
        cel = []
        for ci in visiveis:
            v = l[ci] if ci < len(l) else None
            cor = cc.get(str(ci)) or cc.get(ci)
            cel.append({"t": formatar(v, cols[ci].get("tipo", "texto")),
                        "num": isinstance(v, (int, float)) and not isinstance(v, bool),
                        "cor": cor if isinstance(cor, str) and _HEX.match(cor) else ""})
        saida.append({"tom": tom, "cel": cel})
    return {
        "idx": idx, "titulo": tab.get("titulo", ""), "ativa": ativa, "q": q if ativa else "",
        "cabecalho": [{"ci": ci, "nome": cols[ci].get("nome", ""),
                       "prox_desc": "0" if (ordem == ci and desc) else "1" if ordem == ci else "0",
                       "seta": ("▼" if desc else "▲") if ordem == ci else ""} for ci in visiveis],
        "linhas": saida, "filtros": filtros,
        "total": None if not total else [
            formatar(total[ci] if ci < len(total) else None, cols[ci].get("tipo", "texto"))
            for ci in visiveis],
        "n_total": len(tab.get("linhas", [])), "n_visiveis": len(linhas),
        "cortada": len(linhas) > LIMITE_LINHAS, "limite": LIMITE_LINHAS,
    }


def cor_kpi(k: dict) -> str:
    c = k.get("cor", "neutro")
    return c if c in ("neutro", "ok", "atencao", "alerta", "info") else "neutro"


def hoje_iso() -> str:
    return date.today().isoformat()
