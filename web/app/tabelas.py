"""T-0017, entregas 3 a 5 (contrato §10.7): todas as abas de tabela de Pedidos, Entregas e Visita.

Aqui ficam três coisas:
1. a lista fechada de abas e colunas (§10.7.1 e §10.7.3) e a validação do pacote (§10.7.6);
2. quem vê as tabelas (`VE_TABELAS`, decisão D1, recomendação A: o perfil do farol vê tudo);
3. a tela genérica de tabela (`tabela_para_tela`): filtro, recorte, estado, ordenação, páginas,
   selos, juntas. A Inadimplência (`cobranca.py`) usa a mesma função.

Nenhuma regra de negócio é decidida aqui: filtro padrão, recortes, UF de cada linha, cartões da aba e
limpeza de nome vêm prontos do PC. A web só confere o formato e desenha.
"""
from __future__ import annotations

import math
import re
import unicodedata

from . import render
from .render import COLUNAS_FORA, RE_DATA, coluna_fora, fmt_celula   # a lista e o formato são do render (fonte única)

# ------------------------------------------------------------------ D1: quem vê as tabelas
# Decisão D1 do Alexandre ainda aberta: recomendação A = o perfil de cada farol vê todas as abas
# (como o pós-venda na Inadimplência). Trocar aqui: B = só ("admin", "gerente"); C = tirar de
# "vendas" as abas cliente, prospeccao e indicacao em `ABAS_SO_GERENCIA`.
VE_TABELAS = {
    "pv_pedidos": ("admin", "gerente", "pre_venda"),
    "pl_entregas": ("admin", "gerente", "pos_venda"),
    "vc_visitas": ("admin", "gerente", "vendas"),
}
ABAS_SO_GERENCIA: dict[str, tuple[str, ...]] = {}      # D1 C: {"vc_visitas": ("cliente", "prospeccao", "indicacao")}
PERFIS_GERENCIA = ("admin", "gerente")

RIDS = tuple(VE_TABELAS)
RESUMO = ("resumo", "Resumo")
# chave na URL -> título da tabela no pacote (§10.7.1), na ordem do PC
ABAS = {
    "pv_pedidos": (("pedidos", "Pedidos"), ("solicitacao", "Solicitação BAP")),
    "pl_entregas": (("entregas", "Entregas"),),
    "vc_visitas": (("supervisor", "Por supervisor"), ("vendedor", "Por vendedor"), ("dia", "Dia a dia"),
                   ("aderencia", "Aderência dia a dia"), ("cliente", "Cliente a cliente"),
                   ("prospeccao", "Prospecção"), ("indicacao", "Indicação")),
}
SUBABAS = ("Solicitacao Lojas", "Solicitacao CD", "Solicitacao FRW", "Solicitacao Manual",
           "DETALHADO_PEDIDO", "ProdutosExcluir", "FiliaisExcluir")
# D5 (recomendação A): estado filtra as linhas só onde o pacote traz `uf_linhas`
AVISO_SEM_ESTADO = "Sem filtro por estado: esta tabela mostra a BAP inteira."
AVISO_CARTOES = "Cartões sem filtro. Com filtro, veja as linhas na tabela."
AVISO_ABAS_FORA = "Abas fora desta atualização: {lista}. Veja no PC."
# coluna que identifica a linha: fica fixa à esquerda ao rolar para o lado (celular)
FIXA = {"Por vendedor": "VENDEDOR", "Dia a dia": "VENDEDOR", "Aderência dia a dia": "VENDEDOR",
        "Cliente a cliente": "VENDEDOR"}
LIVRES = {"OBSERVAÇÃO", "JUSTIFICATIVA", "RESULTADO", "LINHAS DE INTERESSE", "DESCRIÇÃO"}   # texto livre: quebra
ROTULO_SUB = {"Solicitacao Lojas": "Lojas", "Solicitacao CD": "CD", "Solicitacao FRW": "FRW",
              "Solicitacao Manual": "Manual", "DETALHADO_PEDIDO": "Detalhado por pedido",
              "ProdutosExcluir": "Produtos excluídos", "FiliaisExcluir": "Filiais excluídas"}
_TROCA_ROTULO = {"COD": "CÓD.", "DESCRICAO": "DESCRIÇÃO", "JA": "JÁ", "UF": "UF", "CD": "CD", "FRW": "FRW"}


def ve_tabelas(rid: str, perfil: str) -> bool:
    return rid in VE_TABELAS and perfil in VE_TABELAS[rid]


def ve_aba(rid: str, chave: str, perfil: str) -> bool:
    if not ve_tabelas(rid, perfil):
        return False
    return perfil in PERFIS_GERENCIA or chave not in ABAS_SO_GERENCIA.get(rid, ())


def chaves(rid: str) -> list[str]:
    return [c for c, _ in ABAS.get(rid, ())]


# ------------------------------------------------------------------ colunas (§10.7.3)
def _c(nome, tipo="texto", oculta=False):
    return (nome, tipo, oculta)


_METRICAS = [_c("META", "num"), _c("VISIT.", "int"), _c("% META", "pct"), _c("% CONV.", "pct"),
             _c("% FORA DE ROTA", "pct"), _c("CAD.", "int"), _c("CAD. C/ COMPRA", "int"), _c("PROSP.", "int"),
             _c("INÍCIO", "hora"), _c("ÚLT. ATIV.", "hora"), _c("JORNADA LÍQ.", "hora"),
             _c("DIAS < JORN. LÍQ.", "int"), _c("INTERV. ALMOÇO", "hora"), _c("DIAS ALMOÇO > MÁX.", "int"),
             _c("TMA", "hora"), _c("TMD", "hora"), _c("KM", "num"), _c("KM/CLIENTE", "num1")]


def _entregas(mes_oculto: bool):
    return [_c("MÊS", "texto", mes_oculto), _c("SITUAÇÃO"), _c("SLA", "int"), _c("DT. PED", "dia"),
            _c("DT. NF", "dia"), _c("DT. PREVISTA", "dia"), _c("DT. REAL", "dia"), _c("UF"), _c("CIDADE"),
            _c("CLIENTE"), _c("VLR NF", "moeda"), _c("VLR FRETE", "moeda"), _c("TRANSPORTADORA"),
            _c("RESPONSÁVEL"), _c("TBL FRETE", "moeda"), _c("VLR REAL FRETE", "moeda"), _c("ETAPA"),
            _c("NF"), _c("FILIAL"), _c("LOCAL/FRETE", "texto", True), _c("TOM SLA", "texto", True),
            _c("PRAZO", "texto", True)]


_GERAR = [_c("DATA", "dia"), _c("UF"), _c("CIDADE"), _c("PEDIDOS"), _c("FORN."), _c("CÓD. PROD."),
          _c("DESCRIÇÃO"), _c("QTD", "num"), _c("COLETAR EM"), _c("FILIAL DEST.")]

COLUNAS: dict[str, list] = {
    "Pedidos": [_c("DT. PED", "dia"), _c("FATURAR ATÉ", "dia"), _c("PEDIDO"), _c("PED. MÁX."), _c("CÓD."),
                _c("RAZÃO SOCIAL"), _c("FANTASIA"), _c("UF"), _c("CIDADE"), _c("LIMITE", "moeda"),
                _c("DISP.", "moeda"), _c("ATRASO", "moeda"), _c("VOL.", "num"), _c("R$ TABELA", "moeda"),
                _c("R$ VENDA", "moeda"), _c("% DESC.", "pct1"), _c("SLA", "int"), _c("% ATENDIDO", "pct"),
                _c("ANÁLISE CRÉDITO"), _c("COND. PAGTO"), _c("SITUAÇÃO"), _c("FILIAL"), _c("PRAZO"),
                _c("VENDEDOR"), _c("NF"), _c("DT. NF", "dia"), _c("R$ TABELA CHEIA", "moeda", True),
                _c("CÓD. AUTORIZAÇÃO", "texto", True), _c("AUTORIZADO POR", "texto", True),
                _c("MÊS", "texto", True), _c("ENTREGUE EM", "dia", True), _c("PRODUTO", "texto", True),
                _c("CHAVE", "texto", True)],
    "Gerar separação CD": _GERAR,
    "Gerar reversa de lojas": _GERAR,
    "Analítico produto": [_c("PEDIDO"), _c("DATA", "dia"), _c("CIDADE"), _c("FILIAL"), _c("FORN."),
                          _c("CÓD. PROD."), _c("DESCRIÇÃO"), _c("QTD", "num"), _c("EST. FRW", "num"),
                          _c("PEDIDOS ANTES", "num"), _c("DISP. P/ ESTE", "num"), _c("ATENDIDO", "num"),
                          _c("FALTA", "num"), _c("CLIENTE"), _c("FILIAL BAP", "texto", True),
                          _c("VALOR FALTANTE", "moeda")],
    "Entregas": _entregas(True),
    "Pendências dos meses anteriores": _entregas(False),
    "Por supervisor": [_c("SUPERVISOR"), _c("REPRES.", "int")] + _METRICAS + [_c("CHAVE", "texto", True)],
    "Por vendedor": [_c("SUPERVISOR"), _c("VENDEDOR"), _c("CARGO", "texto", True), _c("FILIAL", "texto", True),
                     _c("CÓD.", "texto", True)] + _METRICAS + [_c("CHAVE", "texto", True)],
    "Dia a dia": [_c("DATA", "data"), _c("DIA"), _c("SUPERVISOR"), _c("VENDEDOR"), _c("CARGO", "texto", True),
                  _c("SITUAÇÃO")] + _METRICAS + [_c("CHAVE", "texto", True)],
    "Cliente a cliente": [_c("DATA", "data"), _c("DIA"), _c("SUPERVISOR"), _c("VENDEDOR"), _c("SITUAÇÃO"),
                          _c("CÓD."), _c("CLIENTE"), _c("NOME FANTASIA"), _c("SEGMENTO"), _c("BAIRRO"),
                          _c("CIDADE"), _c("CURVA"), _c("STATUS"), _c("DIAS S/ COMPRA", "int"),
                          _c("ATRASO", "moeda"), _c("SEQ. PREV."), _c("SEQ. REAL"), _c("INÍCIO", "hora"),
                          _c("FIM", "hora"), _c("ATEND.", "hora"), _c("PEDIDO NO DIA"),
                          _c("VALOR PEDIDO", "moeda"), _c("JUSTIFICATIVA"), _c("ATEND. SEG.", "int", True)],
    "Prospecção": [_c("DATA", "data"), _c("HORA", "hora"), _c("DIA"), _c("SUPERVISOR"), _c("VENDEDOR"),
                   _c("STATUS"), _c("FONTE"), _c("ESTABELECIMENTO"), _c("SEGMENTO"), _c("CIDADE"), _c("UF"),
                   _c("RESULTADO"), _c("LINHAS DE INTERESSE"), _c("OBSERVAÇÃO")],
    "Indicação": [_c("DATA", "data"), _c("DIA"), _c("SUPERVISOR"), _c("VENDEDOR"), _c("SITUAÇÃO"),
                  _c("CÓD. QUEM INDICOU"), _c("CLIENTE QUE INDICOU"), _c("INDICADO"), _c("CIDADE"),
                  _c("BAIRRO"), _c("SEGMENTO"), _c("VISITADA EM", "data"), _c("OBSERVAÇÃO"),
                  _c("REGISTRADO EM")],
}
# "Aderência dia a dia": 2 + N + 1 colunas, conferidas por padrão de nome (§10.7.3)
ADERENCIA = "Aderência dia a dia"
_RE_DIA = re.compile(r"^\d{2}/\d{2} (SEG|TER|QUA|QUI|SEX|SÁB|DOM)$")
_RE_ACUM = re.compile(r"^% ADERÊNCIA ACUM\. ATÉ \d{2}/\d{2}$")

# juntas (§10.7.2): rid -> aba -> ((título do quadro, título da tabela, liga), ...)
JUNTAS = {
    ("pv_pedidos", "Pedidos"): (
        ("Gerar ID de separação CD", "Gerar separação CD", ["PEDIDOS", "PEDIDO", "|"]),
        ("Gerar reversa de lojas", "Gerar reversa de lojas", ["PEDIDOS", "PEDIDO", "|"]),
        ("Analítico por pedido", "Analítico produto", ["PEDIDO", "PEDIDO", None])),
    ("pl_entregas", "Entregas"): (
        ("Pendências dos meses anteriores", "Pendências dos meses anteriores", None),),
}
# selo permitido por coluna (§10.7.2): "faixa" (chip em lista), "barra", "tom" (chip_tom), "texto" (chip em dict)
SELOS = {
    "Pedidos": {"SLA": "faixa", "% ATENDIDO": "barra"},
    "Entregas": {"SLA": "tom", "PRAZO": "texto"},
    "Pendências dos meses anteriores": {"SLA": "tom", "PRAZO": "texto"},
    "Por supervisor": {"% META": "faixa"}, "Por vendedor": {"% META": "faixa"},
    "Dia a dia": {"% META": "faixa"},
}
# tabelas que levam `uf_linhas` e `kpis_padrao` etc. não têm lista própria: o formato basta.

PROIBIDAS = {"edicao", "editar", "abrir", "detalhe", "kpis_de", "total_de", "totais_por", "recortes",
             "ordem_exportar", "cores_celulas", "so_exportar", "solicitacao_bap", "nota_pdf"}
# dentro dos cartões (`kpis_padrao`) "detalhe" é o texto do cartão; as outras chaves de ação nunca
PROIBIDAS_KPI = (PROIBIDAS - {"detalhe"}) | {"edicao", "editar", "abrir", "tabelas", "juntas", "cobranca", "kpis_de"}
CHAVES_TABELA = {"titulo", "colunas", "linhas", "tons", "total", "filtros", "kpis_padrao", "recortes_linhas",
                 "uf_linhas", "zebra"}
CHAVES_COLUNA = {"nome", "tipo", "largura", "larg_fixa", "oculta", "chip", "barra", "chip_tom", "inteira"}
CHAVES_JUNTA = {"titulo", "liga", "mostrar", "tabela"}
TONS = {"", "ok", "alerta", "atencao", "info", "azul", "cinza", "grave"}
TIPOS_SUB = {"texto", "num", "data"}
NUM_TIPOS = {"int", "num", "num1", "num2", "moeda", "moeda2", "pct", "pct1", "valor"}
TIPOS = NUM_TIPOS | {"texto", "dia", "data", "hora"}
# paleta fixa do selo pela linha (bap_visual.py), §10.7.2
PALETA_TOM = {"ok": ("#E5F3DF", "#2F7D32"), "atencao": ("#FFF1C7", "#8A5A00"),
              "alerta": ("#B3261E", "#FFFFFF"), "cinza": ("#E4E7E4", "#69736D")}
MAX_LINHAS = 60000
MAX_RECORTES = 20
MAX_OPCOES = 300
JUNTA_MAX = 200
RE_UF = re.compile(r"^[A-Z]{2}$")
RE_COR = re.compile(r"^#[0-9A-Fa-f]{6}$")
# CPF/CNPJ já formatado dentro de uma célula: o PC deveria ter limpado (RN-GER-011); a web recusa
RE_DOC = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# ------------------------------------------------------------------ validação (§10.7.6)
def _proibida(o, nivel=0) -> str | None:
    if nivel > 10:
        return "aninhado demais"
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(k, str) and (k in PROIBIDAS_KPI or k.startswith("_") or k.startswith("exportar")
                                       or k.startswith("pdf")):
                return k[:20]
            achou = _proibida(v, nivel + 1)
            if achou:
                return achou
    elif isinstance(o, list):
        for v in o:
            achou = _proibida(v, nivel + 1) if isinstance(v, (dict, list)) else None
            if achou:
                return achou
    return None


def _celula_ok(v, tipo) -> bool:
    """Célula de linha: `null`, ou o valor do tipo; `""` vale em qualquer tipo (o PC deixa célula em branco)."""
    if v is None or v == "":
        return True
    if tipo in NUM_TIPOS:
        return _num(v)
    if tipo in ("dia", "data"):
        return isinstance(v, str) and (v == "" or bool(RE_DATA.match(v)))
    if tipo == "hora":
        return isinstance(v, str) and len(v) <= 12
    if isinstance(v, str):
        return len(v) <= 2000
    return _num(v)


def _celula_sub_ok(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return len(v) <= 2000
    return _num(v)


def _total_ok(tot, tipos) -> bool:
    """§10.7.2.1: uma célula por coluna; `null` ou o valor do tipo (texto só em texto e hora)."""
    return (isinstance(tot, list) and len(tot) == len(tipos)
            and all(v is None or (_celula_ok(v, tp) and v != "") for v, tp in zip(tot, tipos)))


def _cols_esperadas(titulo: str, cols) -> list | None:
    """A lista do §10.7.3; na "Aderência dia a dia" ela sai dos nomes (padrão), None se não bate."""
    if titulo != ADERENCIA:
        return COLUNAS.get(titulo)
    nomes = [c.get("nome") if isinstance(c, dict) else None for c in cols]
    n = len(nomes)
    if not (4 <= n <= 34 and nomes[:2] == ["SUPERVISOR", "VENDEDOR"]):
        return None
    meio = nomes[2:-1]
    if not (all(isinstance(x, str) and _RE_DIA.match(x) for x in meio)
            and isinstance(nomes[-1], str) and _RE_ACUM.match(nomes[-1])):
        return None
    return [_c("SUPERVISOR"), _c("VENDEDOR")] + [_c(x, "pct") for x in meio] + [_c(nomes[-1], "pct")]


def _chip_texto_ok(chip) -> bool:
    return isinstance(chip, dict) and len(chip) <= 60 and all(
        isinstance(k, str) and len(k) < 60 and isinstance(v, (list, tuple)) and len(v) == 2
        and all(isinstance(x, str) and RE_COR.match(x) for x in v) for k, v in chip.items())


def _faixas_ok(fx, numerica=True) -> bool:
    if not (isinstance(fx, list) and 0 < len(fx) <= 20):
        return False
    for f in fx:
        if not (isinstance(f, (list, tuple)) and len(f) == 3):
            return False
        ate, fundo, texto = f
        if not (ate is None or _num(ate)):
            return False
        if not all(x is None or (isinstance(x, str) and RE_COR.match(x)) for x in (fundo, texto)):
            return False
    return True


def _selo_ok(c, forma, nomes_ocultas) -> bool:
    """O selo que a coluna traz bate com o permitido para ela (§10.7.2)."""
    presentes = {k for k in ("chip", "barra", "chip_tom") if c.get(k) is not None}
    if not presentes:
        return True
    if forma == "faixa":
        return presentes == {"chip"} and _faixas_ok(c["chip"])
    if forma == "barra":
        b = c.get("barra")
        return (presentes == {"barra"} and isinstance(b, dict) and set(b) == {"max", "faixas"}
                and _num(b["max"]) and b["max"] > 0 and _faixas_ok(b["faixas"]))
    if forma == "tom":
        return presentes == {"chip_tom"} and isinstance(c["chip_tom"], str) and c["chip_tom"] in nomes_ocultas
    if forma == "texto":
        return presentes == {"chip"} and _chip_texto_ok(c["chip"])
    return False


def _colunas_erro(titulo, cols) -> tuple[str | None, list]:
    esperado = _cols_esperadas(titulo, cols if isinstance(cols, list) else [])
    if esperado is None:
        return "colunas diferentes da lista do contrato", []
    if not (isinstance(cols, list) and len(cols) == len(esperado)):
        return "colunas diferentes da lista do contrato", []
    ocultas = {n for n, _, o in esperado if o}
    selos = SELOS.get(titulo, {})
    for c, (n, tp, o) in zip(cols, esperado):
        if not (isinstance(c, dict) and not (set(c) - CHAVES_COLUNA) and c.get("nome") == n
                and c.get("tipo") == tp and bool(c.get("oculta")) == o):
            return "colunas diferentes da lista do contrato", []
        if coluna_fora(n):
            return "coluna que não vai ao site (telefone, CNPJ, CPF, e-mail, contato, foto, endereço)", []
        if not (c.get("largura") is None or _int(c["largura"])) or not (c.get("larg_fixa") is None or _int(c["larg_fixa"])):
            return "largura inválida", []
        if c.get("inteira") is not None and not isinstance(c["inteira"], bool):
            return "inteira inválida", []
        if not _selo_ok(c, selos.get(n), ocultas):
            return "selo fora das colunas marcadas ou mal formado", []
    return None, esperado


def _kpis_ok(ks) -> bool:
    from . import pacotes                      # tardio: pacotes importa este módulo
    return pacotes._kpis_ok(ks)


def _tabela_erro(t, titulo, nivel="aba", rid="") -> str | None:
    """`nivel`: "aba" (com juntas/subabas), "junta" ou "sub" (sub-aba da Solicitação BAP)."""
    if not isinstance(t, dict) or t.get("titulo") != titulo:
        return "titulo inesperado"
    permitidas = set(CHAVES_TABELA) | ({"juntas", "subabas"} if nivel == "aba" else set())
    if nivel == "sub":
        permitidas = {"titulo", "colunas", "linhas", "tons", "filtros", "total"}
    extra = set(t) - permitidas
    if extra:
        return f"chave não aceita: {sorted(extra)[0][:20]}"
    achou = _proibida(t.get("kpis_padrao"))
    if achou:
        return f"chave não aceita: {achou}"
    cols, linhas = t.get("colunas"), t.get("linhas")
    if not (isinstance(cols, list) and isinstance(linhas, list)) or len(linhas) > MAX_LINHAS:
        return "colunas ou linhas inválidas"
    if nivel == "sub":
        return _sub_erro(t, cols, linhas)
    if nivel == "aba" and titulo == "Solicitação BAP":
        if cols or linhas or not isinstance(t.get("subabas"), list) or not t["subabas"]:
            return "Solicitação BAP precisa de subabas e de colunas/linhas vazias"
        return _subabas_erro(t["subabas"])
    erro, esperado = _colunas_erro(titulo, cols)
    if erro:
        return erro
    n = len(esperado)
    tipos = [tp for _, tp, _ in esperado]
    for ln in linhas:
        if not (isinstance(ln, list) and len(ln) == n and all(_celula_ok(v, tp) for v, tp in zip(ln, tipos))):
            return "linha com número de células ou valores inválidos"
    tons = t.get("tons")
    if tons is not None and not (isinstance(tons, list) and len(tons) == len(linhas)
                                 and all(isinstance(x, str) and x in TONS for x in tons)):
        return "tons inválidos"
    if t.get("total") is not None and not _total_ok(t["total"], tipos):
        return "total inválido"
    nomes = [x[0] for x in esperado]
    fl = t.get("filtros", [])
    if not isinstance(fl, list):
        return "filtros inválidos"
    for f in fl:
        col = f if isinstance(f, str) else (f.get("coluna") if isinstance(f, dict) else None)
        if col not in nomes or (isinstance(f, dict) and set(f) - {"coluna", "padrao", "multi", "oculto"}):
            return "filtro fora da lista de colunas"
    if t.get("kpis_padrao") is not None and not _kpis_ok(t["kpis_padrao"]):
        return "kpis_padrao inválidos"
    rl = t.get("recortes_linhas")
    if rl is not None:
        if not (isinstance(rl, list) and len(rl) <= MAX_RECORTES):
            return "recortes_linhas inválidos"
        for r in rl:
            if not (isinstance(r, dict) and set(r) == {"rotulo", "linhas"} and isinstance(r["rotulo"], str)
                    and len(r["rotulo"]) <= 80 and isinstance(r["linhas"], list)
                    and all(_int(i) and 0 <= i < len(linhas) for i in r["linhas"])):
                return "recortes_linhas fora de linhas"
    uf = t.get("uf_linhas")
    if uf is not None and not (isinstance(uf, list) and len(uf) == len(linhas)
                               and all(isinstance(x, str) and (x == "" or RE_UF.match(x)) for x in uf)):
        return "uf_linhas inválidas"
    if t.get("zebra") is not None and not isinstance(t["zebra"], bool):
        return "zebra inválida"
    if nivel == "aba":
        return _juntas_erro(t, titulo, rid)
    return None


def _sub_erro(t, cols, linhas) -> str | None:
    if not (isinstance(cols, list) and 0 < len(cols) <= 60):
        return "subaba: colunas inválidas"
    for c in cols:
        if not (isinstance(c, dict) and not (set(c) - {"nome", "tipo", "largura", "larg_fixa", "oculta"})
                and isinstance(c.get("nome"), str) and c.get("tipo") in TIPOS_SUB):
            return "subaba: coluna com tipo fora de texto, num e data"
        if coluna_fora(c["nome"]):
            return "subaba: coluna que não vai ao site (telefone, CNPJ, CPF, e-mail, contato, foto, endereço)"
    n = len(cols)
    if not all(isinstance(ln, list) and len(ln) == n and all(_celula_sub_ok(v) for v in ln) for ln in linhas):
        return "subaba: linha com número de células ou valores inválidos"
    tons = t.get("tons")
    if tons is not None and not (isinstance(tons, list) and len(tons) == len(linhas)
                                 and all(isinstance(x, str) and x in TONS for x in tons)):
        return "subaba: tons inválidos"
    if t.get("filtros") not in (None, []):                      # a Solicitação BAP não tem filtros (§10.7.2)
        return "subaba: filtros fora do contrato"
    if t.get("total") is not None and not _total_ok(t["total"], [c["tipo"] for c in cols]):
        return "total inválido"
    return None


def _subabas_erro(subs) -> str | None:
    pos = -1
    for s in subs:
        titulo = s.get("titulo") if isinstance(s, dict) else None
        if titulo not in SUBABAS or SUBABAS.index(titulo) <= pos:
            return "subaba fora da lista, fora da ordem ou repetida"
        pos = SUBABAS.index(titulo)
        e = _tabela_erro(s, titulo, "sub")
        if e:
            return e
    return None


def _juntas_erro(t, titulo_aba, rid) -> str | None:
    js = t.get("juntas")
    esperado = JUNTAS.get((rid, titulo_aba), ())
    if js is None:
        return None
    if not (isinstance(js, list) and len(js) <= len(esperado)):
        return "juntas fora do lugar"
    pos = -1
    for j in js:
        if not (isinstance(j, dict) and not (set(j) - CHAVES_JUNTA) and isinstance(j.get("tabela"), dict)):
            return "junta mal formada"
        ach = [k for k, (tq, _, _) in enumerate(esperado) if tq == j.get("titulo")]
        if not ach or ach[0] <= pos:
            return "junta fora do lugar, fora da ordem ou repetida"
        pos = ach[0]
        tq, tt, liga = esperado[pos]
        if j.get("liga") != liga:
            return "junta com liga diferente do contrato"
        e = _tabela_erro(j["tabela"], tt, "junta")
        if e:
            return "junta: " + e
        nomes = [c["nome"] for c in j["tabela"]["colunas"]]
        m = j.get("mostrar")
        if m is not None and not (isinstance(m, list) and all(isinstance(x, str) and x in nomes for x in m)):
            return "junta: mostrar cita coluna que não existe"
        if liga and not (liga[0] in nomes):
            return "junta: coluna da liga ausente"
    return None


def validar(rid: str, r: dict) -> list[str]:
    """Erros de `tabelas` de um farol (§10.7.6). Mensagens sem dado pessoal. `cobranca` aqui nunca vale."""
    if "cobranca" in r:
        return [f"{rid}: cobranca só no pl_inadimplencia"]
    if "tabelas" not in r:
        return []
    if rid not in RIDS:
        return [f"{rid}: tabelas só no pl_inadimplencia, pv_pedidos, pl_entregas e vc_visitas"]
    ts = r["tabelas"]
    if not isinstance(ts, list) or len(ts) > len(ABAS[rid]):
        return [f"{rid}: tabelas precisa ser lista de até {len(ABAS[rid])} abas"]
    ordem = [t for _, t in ABAS[rid]]
    pos = -1
    for t in ts:
        titulo = t.get("titulo") if isinstance(t, dict) else None
        if titulo not in ordem or ordem.index(titulo) <= pos:
            return [f"{rid}: tabela com titulo fora da lista, fora da ordem ou repetida"]
        pos = ordem.index(titulo)
        e = _tabela_erro(t, titulo, "aba", rid)
        if e:
            return [f"{rid}: tabela {titulo}: {e}"]
    return []


# ------------------------------------------------------------------ documento em texto: só a aba cai (W2)
_RE_AVISO_FORA = re.compile(r"^" + re.escape(AVISO_ABAS_FORA).replace(r"\{lista\}", "(.+)") + "$")


def _celulas_com_documento(linhas) -> bool:
    return any(isinstance(v, str) and RE_DOC.search(v) for ln in linhas if isinstance(ln, list) for v in ln)


def _aba_tem_documento(t: dict) -> bool:
    """CPF/CNPJ já formatado em célula de texto de qualquer parte da aba (linhas, total, juntas, sub-abas)."""
    partes = [t] + [j["tabela"] for j in t.get("juntas") or []] + list(t.get("subabas") or [])
    return any(_celulas_com_documento(list(p.get("linhas") or []) + [p.get("total") or []]) for p in partes)


def tirar_abas_com_documento(corpo: dict) -> list[str]:
    """Defesa da web (RN-GER-011): a aba com CPF/CNPJ formatado numa célula sai do pacote, com o aviso
    `AVISO_ABAS_FORA`; o resto do pacote (Painel, Inadimplência, as outras abas) segue. Devolve os títulos."""
    fora_todas: list[str] = []
    for rid in RIDS:
        rel = (corpo.get("relatorios") or {}).get(rid)
        if not isinstance(rel, dict) or not isinstance(rel.get("tabelas"), list):
            continue
        fora = [t["titulo"] for t in rel["tabelas"] if _aba_tem_documento(t)]
        if not fora:
            continue
        rel["tabelas"] = [t for t in rel["tabelas"] if t["titulo"] not in fora]
        avisos = [a for a in rel.get("avisos") or [] if isinstance(a, str)]
        ja = []
        for a in avisos:
            m = _RE_AVISO_FORA.match(a)
            if m:
                ja += m.group(1).split(", ")
        lista = [x for _, x in ABAS[rid] if x in set(ja) | set(fora)]
        avisos = [a for a in avisos if not _RE_AVISO_FORA.match(a)]
        rel["avisos"] = [AVISO_ABAS_FORA.format(lista=", ".join(lista))] + avisos
        fora_todas += fora
    return fora_todas


# ------------------------------------------------------------------ apresentação
def _chave_ordem(v, tipo):
    if v is None or v == "" or v == "—":
        return (1, 0, "")
    if tipo in NUM_TIPOS and _num(v):
        return (0, v, "")
    return (0, 0, str(v).casefold())


def _faixa_de(v, faixas):
    """bap_visual.Tabela._faixa_de: a primeira faixa com `valor <= ate` (None = sem teto)."""
    for ate, fundo, texto in faixas:
        if ate is None or v <= ate:
            return fundo, texto
    return None, None


def _norm_liga(v, sep) -> set[str]:
    partes = str(v if v is not None else "").split(sep) if sep else [str(v if v is not None else "")]
    return {p.replace(" ", "").lstrip("0") or "0" for p in partes if p.replace(" ", "")}


def _filtros(t, cols, consulta, todas):
    """(lista para a tela, lista de (i, valores escolhidos) a aplicar)."""
    nomes = [c["nome"] for c in cols]
    tela, aplicar = [], []
    for f in t.get("filtros") or []:
        nome = f if isinstance(f, str) else f["coluna"]
        if nome not in nomes:
            continue
        i = nomes.index(nome)
        padrao = f.get("padrao") if isinstance(f, dict) else None
        multi = bool(isinstance(f, dict) and f.get("multi"))
        oculto = bool(isinstance(f, dict) and f.get("oculto"))
        pad = [str(padrao)] if padrao not in (None, "") else []
        chave = f"f{i}"
        if oculto:                                      # só o padrão: a pessoa não escolhe (MÊS do Pedidos)
            sel = pad
        elif chave in consulta:
            sel = [v for v in consulta[chave] if v != ""]
        else:
            sel = pad
        if sel:
            aplicar.append((i, sel))
        if oculto:
            continue
        opcoes = sorted({str(ln[i]) for ln in todas if ln[i] not in (None, "")}, key=str.casefold)
        tela.append({"nome": nome, "chave": chave, "i": i, "multi": multi, "opcoes": opcoes[:MAX_OPCOES],
                     "sel": sel, "padrao": pad})
    return tela, aplicar


def _celula_tela(v, k, row, cols, tipo, centavos):
    """{"t", "f", "c", "b"}: texto, fundo e letra do selo, barra (largura %, cor)."""
    c = cols[k]
    out = {"t": fmt_celula(v, tipo, centavos), "f": None, "c": None, "b": None}
    if v is None or v == "":
        return out
    chip = c.get("chip")
    if isinstance(chip, dict):                          # selo por texto (§10.6.2)
        alvo = str(v).strip().upper()
        cor = next((x for ch, x in chip.items() if str(ch).strip().upper() == alvo), None)
        if cor:
            out["f"], out["c"] = cor[0], cor[1]
    elif isinstance(chip, list) and _num(v):            # selo por faixa
        fundo, texto = _faixa_de(v, chip)
        if fundo:
            out["f"], out["c"] = fundo, texto or "#1B2430"
    elif isinstance(c.get("barra"), dict) and _num(v):
        b = c["barra"]
        fundo, texto = _faixa_de(v, b["faixas"])
        out["b"] = {"w": round(max(0.0, min(1.0, v / b["max"])) * 100, 1), "f": fundo or "#8FA79A"}
        out["c"] = texto
    elif isinstance(c.get("chip_tom"), str):            # selo pela linha (coluna oculta pelo nome)
        j = next((i for i, x in enumerate(cols) if x["nome"] == c["chip_tom"]), None)
        cor = PALETA_TOM.get(str(row[j]).strip().lower()) if j is not None and j < len(row) else None
        if cor:
            out["f"], out["c"] = cor
    return out


def _tela_basica(t, idxs, vista, centavos):
    cols = t["colunas"]
    tons = t.get("tons") or []
    return [{"tom": tons[k] if k < len(tons) else "",
             "cel": [_celula_tela(t["linhas"][k][c], c, t["linhas"][k], cols, cols[c]["tipo"], centavos)
                     for c in vista]} for k in idxs]


def _vista(t, ordem_tela=None):
    cols = t["colunas"]
    ordem = ordem_tela if ordem_tela is not None else list(range(len(cols)))
    return [k for k in ordem if not cols[k].get("oculta")]


def _cabecalho(t, vista):
    cols = t["colunas"]
    return [{"i": k, "nome": cols[k]["nome"], "tipo": cols[k]["tipo"], "num": cols[k]["tipo"] in NUM_TIPOS,
             "inteira": bool(cols[k].get("inteira")), "livre": cols[k]["nome"] in LIVRES} for k in vista]


def tabela_para_tela(t: dict, consulta: dict, *, uf: str | None = None, pagina_tam: int = 100,
                     ordem_tela=None, centavos: bool = False, total_sempre: bool = False,
                     vazios_no_fim: bool = True, titulo: str | None = None) -> dict:
    """Filtra, ordena e pagina no servidor (genérica: Inadimplência e as abas do §10.7).

    `consulta`: f<i> (lista de valores), rec (índice do recorte), ord, dir, pag. `uf`: estado escolhido
    (só vale se a tabela traz `uf_linhas`). `ordem_tela`: ordem das colunas na tela (lista de índices).
    `total_sempre`: mostra a linha de total mesmo com filtro (Inadimplência); sem ele, só sem filtro (§10.7.2).
    `vazios_no_fim`: na ordem decrescente a célula vazia vai para o fim (a Inadimplência mantém o jeito de antes).
    """
    cols, todas = t["colunas"], t["linhas"]
    n = len(todas)
    filtros, aplicar = _filtros(t, cols, consulta, todas)
    idxs = list(range(n))
    ufl = t.get("uf_linhas")
    uf_aplicada = bool(uf and ufl)
    if uf_aplicada:
        idxs = [k for k in idxs if ufl[k] == uf]
    for i, sel in aplicar:
        idxs = [k for k in idxs if str(todas[k][i]) in sel]
    # recortes (§11.4): índices prontos do PC
    recs = t.get("recortes_linhas") or []
    try:
        rec = int(consulta.get("rec", [""])[0])
    except ValueError:
        rec = None
    rec = rec if rec is not None and 0 <= rec < len(recs) else None
    base = set(idxs)
    recortes = [{"n": q, "rotulo": r["rotulo"], "qtd": len(base.intersection(r["linhas"])),
                 "ativo": q == rec} for q, r in enumerate(recs)]
    if rec is not None:
        dentro = set(recs[rec]["linhas"])
        idxs = [k for k in idxs if k in dentro]
    ordem = consulta.get("ord", [""])[0]
    desc = consulta.get("dir", ["asc"])[0] == "desc"
    j = int(ordem) if ordem.isdigit() and int(ordem) < len(cols) else None
    if j is not None:
        chave = lambda k: _chave_ordem(todas[k][j], cols[j]["tipo"])  # noqa: E731
        if desc and vazios_no_fim:
            cheios = [k for k in idxs if chave(k)[0] == 0]
            idxs = sorted(cheios, key=chave, reverse=True) + [k for k in idxs if chave(k)[0] == 1]
        else:
            idxs = sorted(idxs, key=chave, reverse=desc)
    total = len(idxs)
    try:
        pag = max(1, int(consulta.get("pag", ["1"])[0]))
    except ValueError:
        pag = 1
    paginas = max(1, -(-total // pagina_tam))
    pag = min(pag, paginas)
    visiveis = idxs[(pag - 1) * pagina_tam: pag * pagina_tam]
    if ordem_tela is None and FIXA.get(t.get("titulo")) in [c["nome"] for c in cols]:
        f0 = [c["nome"] for c in cols].index(FIXA[t["titulo"]])        # a coluna da linha vai à frente
        ordem_tela = [f0] + [k for k in range(len(cols)) if k != f0]
    vista = _vista(t, ordem_tela)
    padrao = (rec is None and not uf_aplicada
              and all(set(f["sel"]) == set(f["padrao"]) for f in filtros))
    tot = t.get("total")
    mostra_total = bool(tot) and (total_sempre or (total == n))
    return {
        "titulo": titulo or t.get("titulo", ""), "total_linhas": total, "pag": pag, "paginas": paginas,
        "cols": _cabecalho(t, vista),
        "linhas": _tela_basica(t, visiveis, vista, centavos),
        "total": ([_celula_tela(tot[c], c, tot, cols, cols[c]["tipo"], centavos) for c in vista]
                  if mostra_total else None),
        "filtros": filtros, "ord": j, "desc": desc, "recortes": recortes, "rec": rec,
        "padrao": padrao, "filtrado": rec is not None or any(set(f["sel"]) != set(f["padrao"]) for f in filtros),
        "uf_aplicada": uf_aplicada, "zebra": bool(t.get("zebra")),
        "idxs": idxs,                                   # as linhas visíveis (todas as páginas), para as juntas
    }


def juntas_para_tela(t: dict, idxs: list[int], uf: str | None = None, centavos: bool = False) -> list[dict]:
    """As juntas da aba: com `liga`, só as linhas ligadas às linhas visíveis de cima (todas as páginas,
    depois de filtro, recorte e estado, §10.7.2); sem `liga`, todas (e o estado, se a junta traz UF)."""
    out = []
    for j in t.get("juntas") or []:
        jt, liga = j["tabela"], j.get("liga")
        if liga:
            col_j, col_t, sep = liga
            ci = [c["nome"] for c in t["colunas"]].index(col_t)
            alvo = set()
            for k in idxs:
                alvo |= _norm_liga(t["linhas"][k][ci], None)
            cj = [c["nome"] for c in jt["colunas"]].index(col_j)
            ks = [k for k, ln in enumerate(jt["linhas"]) if _norm_liga(ln[cj], sep) & alvo]
        else:
            ks = list(range(len(jt["linhas"])))
        if uf and jt.get("uf_linhas"):
            ks = [k for k in ks if jt["uf_linhas"][k] == uf]
        nomes = [c["nome"] for c in jt["colunas"]]
        mostrar = j.get("mostrar")
        vista = [k for k, c in enumerate(jt["colunas"]) if not c.get("oculta") and (not mostrar or c["nome"] in mostrar)]
        out.append({"titulo": j.get("titulo") or jt.get("titulo", ""), "total_linhas": len(ks),
                    "mais": len(ks) > JUNTA_MAX, "cols": _cabecalho(jt, vista),
                    "linhas": _tela_basica(jt, ks[:JUNTA_MAX], vista, centavos)})
    return out


def subabas_para_tela(t: dict, sub: int, consulta: dict, pagina_tam: int = 100) -> tuple[list[str], dict]:
    """Solicitação BAP: os nomes das sub-abas e a escolhida (índice `sub`), paginada. Sem filtros."""
    subs = t["subabas"]
    sub = sub if 0 <= sub < len(subs) else 0
    s = subs[sub]
    tela = tabela_para_tela({"titulo": s["titulo"], "colunas": s["colunas"], "linhas": s["linhas"],
                             "tons": s.get("tons")}, consulta, pagina_tam=pagina_tam)
    tela["sub"] = sub
    for c in tela["cols"]:                                 # só na exibição: rótulo legível (o contrato guarda o do arquivo)
        c["nome"] = " ".join(_TROCA_ROTULO.get(w, w) for w in c["nome"].replace("_", " ").split())
    return [ROTULO_SUB.get(x["titulo"], x["titulo"]) for x in subs], tela
