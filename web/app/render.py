"""Renderizador do Painel Executivo (cartões RRM e abas de painel).

A web só mostra os números que o PC mandou prontos (painel_rrm.calcular):
nada é recalculado. O que sobra aqui é apresentação: formato do percentual,
geometria do anel (SVG) e altura relativa da barra, como o desenho do PC
(`painel_rrm._cartao_pil`, `bap_visual`, paleta CLARO).
"""
from __future__ import annotations

import math
import re
import unicodedata

from . import marca, visitas

R_ANEL = 34
CIRC = 2 * math.pi * R_ANEL


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


CHAVES_ABAS = (("resultado", "res"), ("produtividade", "prod"), ("por_dia_util", "du"))   # = painel_rrm.VISOES; fonte única (pacotes.ABAS usa esta)
ABAS_OPCIONAIS = ("por_dia_util",)         # T-0022: robô antigo manda só as duas primeiras
# T-0022: as outras 9 abas do Painel Executivo (forma farol, em `paineis` do pacote), na ordem do PC
# nomes curtos (cabem numa linha a 1366, contrato tela-bc3 §13); o nome "Painel Executivo" é o da tela (RD-0038)
PAINEIS = (("resumo", "Resumo"), ("faturamento", "Faturamento"), ("volume", "Volume"),
           ("visitas", "Visitas"), ("positivacao", "Positivação"), ("itens", "Itens"),
           ("markup", "Markup"), ("preco", "Preço"), ("inadimplencia", "Inadimplência"))
PAINEL_CURTO = {"resultado": "Resultado", "produtividade": "Produtividade", "por_dia_util": "Por DU"}   # as 3 abas RRM


_DU = re.compile(r"\((\d+) de (\d+) dias úteis\)")
_DU_FECHADO = re.compile(r"fechado \((\d+) dias úteis\)")


def du_do_painel(abas: list[dict]) -> str:
    """U8/U11: os dias úteis da faixa, lidos do `sub` que o PC mandou nas abas RRM (nada é recalculado). Mês aberto:
    "13 de 19 DU"; mês fechado ("outubro fechado (22 dias úteis)"): "22 DU · mês fechado". Vazio se o PC não mandou."""
    for a in abas or []:
        sub = str((a.get("dados") or {}).get("sub", {}).get(a["visao"], ""))
        m = _DU.search(sub)
        if m:
            return f"{m.group(1)} de {m.group(2)} DU"
        m = _DU_FECHADO.search(sub)
        if m:
            return f"{m.group(1)} DU · mês fechado"
    return ""


def kpis_da_faixa(kpis: list[dict]) -> list[dict]:
    """RD-0065: os cartões comuns vão para a faixa; o que tem barras por estado ou linhas de detalhe fica no corpo (`_resumo.html`)."""
    return [k for k in (kpis or []) if not k.get("estados") and not k.get("linhas")]


def kpis_do_corpo(kpis: list[dict]) -> list[dict]:
    """RD-0065: o complemento de `kpis_da_faixa`: primeiro os com barras por estado, depois os com linhas."""
    ks = kpis or []
    return [k for k in ks if k.get("estados")] + [k for k in ks if not k.get("estados") and k.get("linhas")]


def abas_no_celular(chaves: list, atual) -> list[int]:
    """RD-0065 (b): no celular a barra mostra 3 abas (as duas primeiras e a aberta) e "Mais" leva as outras (contrato §5.3).
    Aba desconhecida = a página caiu na 1ª aba: aparecem as 3 primeiras."""
    pos = list(chaves).index(atual) if atual in chaves else 0
    return [0, 1, pos] if pos > 1 else [0, 1, 2]


NA_FAIXA = 3          # os 3 primeiros cartões RRM levam o número à faixa; os outros (o PC manda 10, 10 e 6) mantêm o deles no cartão


def faixa_painel(tela: dict | None, tela_f: dict | None) -> list[dict]:
    """T-0034: os números da faixa do Painel Executivo, prontos do pacote (nada é recalculado). Aba RRM: os 3 cartões de
    cabeça (os anéis MTD e MÊS ficam só no cartão, RD-0063); aba de painel: os cartões comuns (os ricos ficam no corpo)."""
    if tela_f:
        return kpis_da_faixa(tela_f["kpis"])
    out = []
    for c in ((tela or {}).get("cartoes") or [])[:NA_FAIXA]:
        aneis = [a for a in c["aneis"] if a["tem"]]
        det = c["legenda"] if any(ch.isdigit() for ch in c["legenda"]) else ""     # sem número próprio, o rótulo já diz
        out.append({"rot": c["titulo"], "valor": c["valor"], "detalhe": det,
                    "cor": aneis[-1]["tom"] if aneis else ""})
    return out


def localizar_paineis(rel: dict) -> list[dict]:
    """T-0022: as abas de painel (forma farol) que o PC mandou, na ordem do PC."""
    ps = (rel or {}).get("paineis")
    ps = ps if isinstance(ps, dict) else {}
    return [{"chave": c, "titulo": t, "so_bap": bool(ps[c].get("so_bap")),
             "ufs": sorted((ps[c].get("recortes") or {}))} for c, t in PAINEIS
            if isinstance(ps.get(c), dict)]


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


COMO_LER_ESTADO = ("Número do estado como na barra dele no Painel Executivo do PC; "
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
    return {"sub": sub, "uf": uf,
            "cartoes": [{**cartao(c), "na_faixa": i < NA_FAIXA} for i, c in enumerate(cartoes)],
            "como_ler": como_ler, "avisos": d.get("avisos") or []}


# ---------------------------------------------------------------- faróis (T-0017)
# Forma "farol" do pacote (contrato §10): o PC manda kpis, insights e blocos do painel
# prontos. Aqui só se desenha (barras em HTML/CSS); nada é recalculado.
# T-0036 (desenho §2, P1 = A): o analista vê como o gerente tudo o que não é meta RH nem edição.
# Uma fonte só: com a P1 = B, troca esta linha (e o analista sai das tuplas dos outros faróis).
LEITURA_GERAL = ("admin", "gerente", "analista")
# T-0036 (RD-0004): os faróis do Analista Comercial, lista única (menu, busca e rótulos do `tabelas`)
RIDS_ANALISTA = ("vc_saldo", "vc_markup", "vc_preco", "an_divergencias")
FAROIS = {  # rid -> (nome no PC, perfis que veem)
    "pv_pedidos": ("Farol de Pedidos", LEITURA_GERAL + ("diretor", "pre_venda")),
    "vc_visitas": ("Farol de Visita", LEITURA_GERAL + ("diretor", "vendas")),
    "pl_entregas": ("Farol de Entregas", LEITURA_GERAL + ("diretor", "pos_venda")),
    "pl_inadimplencia": ("Farol de Inadimplência", LEITURA_GERAL + ("diretor", "pos_venda")),
    # T-0037: Farol de Fretes (contrato §10.12); o analista lê como o gerente (RN-GER-017), sem editar
    "pl_fretes": ("Farol de Fretes", LEITURA_GERAL + ("diretor", "pos_venda")),
    # T-0024 (lote 2): o perfil de cada quadrado do PC (bap_central.py)
    "pv_indicadores": ("Painel de indicadores", LEITURA_GERAL + ("diretor", "pre_venda")),
    "vc_base": ("Farol de Clientes", LEITURA_GERAL + ("diretor", "vendas")),
    "vc_planner": ("Farol Roteirização", LEITURA_GERAL + ("diretor", "vendas")),
    "pl_giro": ("Farol de Giro de Produtos", LEITURA_GERAL + ("diretor", "vendas")),
    "pl_frw": ("Farol de Estoque FRW", LEITURA_GERAL + ("diretor", "pre_venda", "pos_venda")),
    # T-0023 v2 (contrato §10.10.1): Pós-venda. O diretor vê só o Resumo (RN-GER-014: ver `tabelas.VE_TABELAS`)
    "pl_garantias": ("Farol de Garantias", LEITURA_GERAL + ("diretor", "pos_venda")),
    "pl_devolucoes": ("Farol de Devolução e Reembolsos", LEITURA_GERAL + ("diretor", "pos_venda")),
    "pl_ncc": ("Farol de NCC", LEITURA_GERAL + ("diretor", "pos_venda")),
    # T-0022: o Farol de Metas Equipe é da área CRM e Pós-venda (vendas), como o de Visita
    "vc_meta": ("Farol de Metas Equipe", LEITURA_GERAL + ("diretor", "vendas")),
    # T-0036 (contrato §10.11.6): Analista Comercial; o diretor vê só o Resumo
    "vc_saldo": ("Farol de Saldo", LEITURA_GERAL + ("diretor",)),
    "vc_markup": ("Farol de Markup", LEITURA_GERAL + ("diretor",)),
    "vc_preco": ("Farol de Preço", LEITURA_GERAL + ("diretor",)),
    "an_divergencias": ("Divergências de clientes Planner × Protheus", LEITURA_GERAL + ("diretor",)),
}
VEEM_PAINEL = LEITURA_GERAL + ("diretor",)      # T-0036 (P1 = A, RD-0003): o analista vê como o gerente. Quem vê o Painel Executivo: a `/`, a lateral e a rota usam esta tupla só
TONS = ("ok", "atencao", "alerta", "info")
LOTE2 = ("pv_indicadores", "vc_base", "vc_planner", "pl_giro", "pl_frw")    # T-0024: faróis de abas livres
# T-0024 (R4 do parecer de UX): nome curto na barra lateral; o nome completo do PC fica no título da faixa
NOME_MENU = {"pv_indicadores": "Indicadores", "vc_base": "Clientes", "vc_planner": "Roteirização",
             "pl_giro": "Giro de produtos", "pl_frw": "Estoque FRW",
             # T-0036 (revisão de UX, 7): na lateral o nome é curto; o completo fica na faixa
             "vc_saldo": "Saldo", "vc_markup": "Markup", "vc_preco": "Preço", "an_divergencias": "Divergências",
             "pl_garantias": "Garantias", "pl_devolucoes": "Devoluções", "pl_ncc": "NCC"}
AVISO_UF = "Os outros cartões, o resumo e os gráficos: só na BAP inteira."   # T-0033 (RD-0034): um aviso só
SEM_DADO_UF = "Sem números de {uf} neste pacote."
INDISPONIVEL = "ainda não disponível na web"
_COR = re.compile(r"^#[0-9A-Fa-f]{6}$")


GRUPOS_MENU = (("Pré-venda", ("pv_pedidos", "pv_indicadores")),
               ("Pós-venda", ("pl_entregas", "pl_inadimplencia", "pl_garantias", "pl_devolucoes", "pl_ncc", "pl_frw", "pl_fretes")),
               ("Vendas", ("vc_visitas", "vc_meta", "vc_base", "vc_planner", "pl_giro")),   # T-0024: lote 2 no menu
               ("Analista Comercial", RIDS_ANALISTA),
               # T-0036 (contrato §10.10.1): o grupo do trade; aparece quando o Farol de Expositores entrar (T-0025 v2)
               ("Trade", ("tm_expositores",)))
# T-0036 (revisão UX): o grupo do próprio perfil abre a barra; os outros perfis seguem a ordem de GRUPOS_MENU
GRUPO_DO_PERFIL = {"analista": "Analista Comercial", "trade": "Trade"}


def grupos_na_ordem(perfil: str) -> tuple:
    meu = GRUPO_DO_PERFIL.get(perfil)
    return tuple(sorted(GRUPOS_MENU, key=lambda g: g[0] != meu))


def menu_lateral(perfil: str, no_pacote: dict, ativo: str | None, painel: bool = False,
                 admin: bool = False) -> list[dict]:
    """T-0030: os grupos da barra lateral, só com o que o perfil vê (fonte única do menu; a página inicial usa `pagina_inicial`)."""
    meus = dict(farois_do_perfil(perfil))
    grupos = []
    if painel:
        grupos.append({"nome": "Diretoria", "itens": [{"href": "/painel", "nome": "Painel Executivo",
                                                       "ativo": ativo == "painel"}]})
    for nome, rids in grupos_na_ordem(perfil):
        itens = [{"href": f"/farol/{r}" if r in no_pacote else "", "nome": NOME_MENU.get(r, meus[r].removeprefix("Farol de ")),
                  "ativo": r == ativo}
                 for r in rids if r in meus]
        if "vc_visitas" in rids and perfil in visitas.PODEM_PEDIR:     # T-0045: ☰ → Atualizar visitas → botão (3 toques)
            i = next((k for k, x in enumerate(itens) if x["nome"] == NOME_MENU.get("vc_visitas", "Visita")), None)
            itens.insert(len(itens) if i is None else i + 1,
                         {"href": "/visitas/atualizar", "nome": "Atualizar visitas", "ativo": ativo == "visitas_atualizar"})
        if itens:
            grupos.append({"nome": nome, "itens": itens})
    conta = [{"href": "/senha", "nome": "Trocar senha", "ativo": ativo == "senha"}]
    if admin:
        conta.insert(0, {"href": "/usuarios", "nome": "Usuários", "ativo": ativo == "usuarios"})
    grupos.append({"nome": "Conta", "itens": conta})
    return grupos


def pagina_inicial(perfil: str) -> str:
    """T-0034 (Alexandre, 26/11, decisão 2 A): admin, diretor e gerente abrem no Painel Executivo; os outros, no primeiro
    farol da área, pela ordem do menu lateral (GRUPOS_MENU). T-0036 (UX 8): o perfil com grupo próprio (analista) abre
    no 1º farol do grupo, antes do Painel."""
    meus = dict(farois_do_perfil(perfil))
    for nome, rids in GRUPOS_MENU:
        if nome == GRUPO_DO_PERFIL.get(perfil):
            for r in rids:
                if r in meus:
                    return f"/farol/{r}"
    if perfil in VEEM_PAINEL:
        return "/painel"
    for _, rids in GRUPOS_MENU:
        for r in rids:
            if r in meus:
                return f"/farol/{r}"
    return "/senha"


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
    """R1 (UX T-0037): só entra cor da paleta da marca (`marca.TOKENS`); qualquer outra (o AZUL do PC, por exemplo)
    vira o padrão (`--grafico-3`)."""
    if isinstance(c, str) and _COR.match(c):
        if c.lower() in {v.lower() for v in marca.TOKENS.values() if isinstance(v, str)}:
            return c
    return padrao


def _bloco_barras(b) -> dict:
    g = b.get("grafico")
    if not isinstance(g, dict):
        raise ValueError("sem gráfico")
    rotulos = [str(x) for x in _lista(g.get("rotulos"))]
    formato = g.get("formato", "num")
    series = []
    for s in _lista(g.get("series")):
        series.append({"nome": str(s.get("nome", "")), "cor": _cor(s.get("cor"), marca.TOKENS["--grafico-3"]),
                       "cor_neg": _cor(s.get("cor_negativo"), marca.TOKENS["--alerta"]),
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
    larga = (_num(b.get("colspan")) or 1) >= 2 and not denso          # A1: o gráfico que pede a largura toda
    for c in cols:                                                       # celular: "DEZ/25" vira "DEZ"
        m = re.match(r"^([A-ZÇ]{3})/\d{2}$", c["rot"])
        c["rot_c"] = m.group(1) if m else c["rot"]
    return {"tipo": "barras", "larga": larga, "titulo": str(g.get("titulo", "")), "cols": cols,
            "denso": denso, "vert": 8 < nbarras and not denso and not larga,       # valor em pé: não se sobrepõe
            "rotv": not larga and ((len(cols) > 5 and maxrot > 5) or (len(cols) > 8 and maxrot > (3 if denso else 4))),   # data/nome comprido em pé
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
                       "cor": _cor(cores[i] if i < len(cores) else None, marca.TOKENS["--grafico-3"])})
    return {"tipo": "hbarras", "titulo": str(b.get("titulo", "")), "linhas": linhas,
            "ref": {"pos": round(100 * abs(ref) / mx, 1), "txt": fmt_valor(ref, formato)} if ref else None}


MAX_LINHAS_TAB = 200
# Colunas que nunca vão ao site (contrato §10.7.4, bloco `colunas-fora`): a lista é daqui, e o
# `tabelas` importa. Nome inteiro, sem acento e em maiúsculas.
COLUNAS_FORA = frozenset({"TELEFONE", "CELULAR", "WHATSAPP", "CNPJ", "CPF", "E-MAIL", "EMAIL", "CONTATO",
                         "FOTO", "ENDERECO"})
# regra a mais, só do bloco tabela (§10.1): a palavra inteira, "KM/CLIENTE" e "CLIENTES" são números (T-0022)
_CLIENTE_NO_BLOCO = re.compile(r"(?<![\w/])(cliente|raz[aã]o|fantasia)(?!\w)", re.I)
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


def _bloco_placar(b) -> dict:
    """T-0022: "Os faróis no mês" do Resumo gerencial (cartões prontos do PC: farol, valor, tom, frase)."""
    cs = []
    for c in _lista(b.get("cartoes")):
        if isinstance(c, dict) and c.get("farol"):
            cs.append({"farol": str(c["farol"]), "valor": str(c.get("valor", "—")), "rot": str(c.get("rotulo") or ""),
                       "tom": _tom(c.get("tom")), "detalhe": str(c.get("detalhe") or ""),
                       "sentido": str(c.get("sentido") or ""), "frase": str(c.get("frase") or ""),
                       "dica": str(c.get("dica") or "")})
    if not cs:
        raise ValueError("sem cartões")
    return {"tipo": "placar", "titulo": str(b.get("titulo", "")), "cartoes": cs}


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
            elif b.get("tipo") == "placar":
                out.append(_bloco_placar(b))
            else:
                raise ValueError("tipo desconhecido")
        except (ValueError, TypeError, AttributeError):
            g = b.get("grafico")
            titulo = b.get("titulo") or (g.get("titulo") if isinstance(g, dict) else "")
            out.append({"tipo": "indisponivel", "titulo": str(titulo or "")})
    # A1: a largura toda só quando é o único gráfico da tela (os outros faróis seguem como estavam)
    if sum(1 for x in out if x.get("tipo") in ("barras", "hbarras")) != 1:
        for x in out:
            if x.get("larga"):
                x["larga"] = False
                n = len(x["cols"])
                maxrot = max([len(c["rot"]) for c in x["cols"]] or [0])
                x["vert"] = 8 < n * max(len(x["cols"][0]["barras"]), 1) and not x["denso"]
                x["rotv"] = (n > 5 and maxrot > 5) or (n > 8 and maxrot > (3 if x["denso"] else 4))
    return ins, out


_RE_PERIODO = re.compile(r"^(.*?) · (dia a dia|semana a semana|mês a mês)\b")
_ROTULO_PERIODO = {"dia a dia": "Dia", "semana a semana": "Semana", "mês a mês": "Mês"}


def agrupar_periodos(blocos: list[dict]) -> list[dict]:
    """T-0024 (R2 do parecer de UX): os gráficos "métrica · dia a dia / semana a semana / mês a mês" viram UM cartão
    por métrica, com o seletor Dia · Semana · Mês dentro. O resto dos blocos segue como veio, na mesma ordem."""
    grupos: dict[str, dict] = {}
    out: list[dict] = []
    for b in blocos:
        m = _RE_PERIODO.match(b.get("titulo", "")) if b.get("tipo") == "barras" else None
        if not m:
            out.append(b)
            continue
        g = grupos.get(m.group(1))
        if g is None:
            g = grupos[m.group(1)] = {"tipo": "periodos", "titulo": m.group(1), "vistas": []}
            out.append(g)
        g["vistas"].append({"nome": _ROTULO_PERIODO[m.group(2)], "b": b})
    return [g if g.get("tipo") != "periodos" or len(g["vistas"]) > 1 else g["vistas"][0]["b"] for g in out]


def _dados_do_bloco(b: dict):
    """Os números que o bloco desenha (para achar gráfico repetido); None se não souber."""
    if b.get("tipo") == "periodos":
        return tuple(_dados_do_bloco(v["b"]) for v in b["vistas"])
    if b.get("tipo") == "barras":
        return tuple(tuple(x.get("txt") for x in c.get("barras") or []) for c in b.get("cols") or [])
    if b.get("tipo") == "hbarras":
        return tuple(l.get("txt") for l in b.get("linhas") or [])
    return None


def sem_graficos_repetidos(blocos: list[dict]) -> list[dict]:
    """T-0024 (reteste de UX, N2): o mesmo número não aparece em dois gráficos do Resumo. Sai o bloco que desenha
    os mesmos números de outro, e o gráfico de colunas de uma só série que repete as barras de mesmo assunto
    (ex.: "Venda perdida prevista por filial" × "Venda perdida prevista (R$) por filial")."""
    vistos, saida = set(), []
    for b in blocos:
        d = _dados_do_bloco(b)
        if d is not None and d in vistos:
            continue
        if d is not None:
            vistos.add(d)
        saida.append(b)
    barras_h = [" ".join(b.get("titulo", "").split()[:3]) for b in saida if b.get("tipo") == "hbarras"]
    return [b for b in saida
            if not (b.get("tipo") == "barras" and len(b.get("legenda") or []) <= 1
                    and " ".join(b.get("titulo", "").split()[:3]) in barras_h and len(b.get("cols") or []) <= 12)]


def recortes_farol(rel: dict) -> list[str]:
    rec = rel.get("recortes")
    return sorted(rec) if isinstance(rec, dict) else []


def farol_para_tela(rel: dict, uf: str | None = None, rid: str | None = None) -> dict:
    ufs = recortes_farol(rel)
    uf = (uf or "").upper()
    sem_dado = False
    r_uf = {}
    if uf in ufs:
        r_uf = rel["recortes"][uf]
        rec = [r for r in _lista(r_uf.get("kpis")) if isinstance(r, dict)]
        todos = [k for k in _lista(rel.get("kpis")) if isinstance(k, dict)]
        # cartão da BAP inteira que o estado não tem (ex.: fotos sem filial): "—" sem dica (o `cartao_vazio` o tira e o
        # AVISO_UF diz uma vez só que os outros são da BAP inteira)
        kpis = [next((r for r in rec if r.get("rotulo") == k.get("rotulo")), None)
                or {"rotulo": k.get("rotulo", ""), "valor": "—", "cor": "neutro"}
                for k in todos]
        kpis += [r for r in rec if r.get("rotulo") not in {k.get("rotulo") for k in todos}]
    elif re.match(r"^[A-Z]{2}$", uf):
        sem_dado = True
        # estado sem recorte: "—" nos cartões, nunca o número da BAP inteira
        kpis = [{"rotulo": k.get("rotulo", ""), "valor": "—", "cor": "neutro"}
                for k in _lista(rel.get("kpis")) if isinstance(k, dict)]
    else:
        uf, kpis = None, rel.get("kpis")
    # T-0022: o estado traz o painel dele (Painel Executivo e Farol de Metas); sem painel, o da BAP inteira
    fonte = r_uf if isinstance(r_uf.get("painel"), dict) else rel
    ins_blocos, blocos = _blocos(fonte.get("painel"))
    if rid in LOTE2:                                    # T-0024 (R2): um cartão por métrica, Dia · Semana · Mês dentro
        blocos = sem_graficos_repetidos(agrupar_periodos(blocos))
    cartoes = [k for k in map(_kpi, _lista(kpis)) if k and not cartao_vazio(k)]
    insights = sem_repeticao(_insights(fonte.get("insights_painel")) or ins_blocos, cartoes)
    ditas = {i["texto"] for i in insights}                 # RD-0035: a frase fica só em "O que o painel diz"
    for b in blocos:
        for c in (b.get("cartoes") or []) if b.get("tipo") == "placar" else []:
            if c.get("frase") in ditas:
                c["frase"] = ""
    return {"titulo": str(rel.get("titulo", "")), "ufs": ufs, "uf": uf,
            "faixa": bool(rel.get("kpis_faixa")),   # cartões em faixa fina, como o PC
            "kpis": cartoes,
            "insights": insights, "blocos": blocos,
            "avisos": [str(a) for a in _lista(rel.get("avisos")) if not str(a).startswith("Sem filtro por estado")],
            "avisos_info": [str(a) for a in _lista(rel.get("avisos")) if str(a).startswith("Sem filtro por estado")],
            "aviso_uf": (((SEM_DADO_UF.format(uf=uf) + " ") if sem_dado else "") + AVISO_UF
                         if uf and fonte is rel else ""),
            "baixado_em": rel.get("baixado_em"), "so_bap": bool(rel.get("so_bap"))}
