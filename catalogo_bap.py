# -*- coding: utf-8 -*-
"""
CATALOGO BAP 2026 - a classificacao de cada produto (15/10, Alexandre)

    CATEGORIA  PEÇAS LINHA LEVE, PEÇAS LINHA PESADA, PEÇAS LINHA MOTO,
               BATERIAS, LUBRIFICANTES, QUÍMICOS, PNEUS, ACESSÓRIOS
               (03/11, Alexandre: PEÇAS dividida pela LINHA - MOTO = moto,
               PESADA = pesada, o resto (LEVE, LEVE E PESADA...) = leve)
    SISTEMA    o sistema do veiculo (SUSPENSÃO, FREIO, MOTOR, ELÉTRICA...)
    FAMÍLIA    a familia do catalogo (AMORTECEDORES E KITS, FILTROS DE AR...)
    LINHA      LEVE, PESADA, LEVE E PESADA, MOTO ou UNIVERSAL

A classificacao para na LINHA. PRODUTO e o produto em si (o codigo e a
descricao de cada linha dos relatorios), nao uma classificacao.

De onde vem (nesta ordem):
  1. o ESTOQUE_BAP.xlsx (RELATORIOS) - a Automacao grava as colunas
     CATEGORIA, SISTEMA, FAMILIA e LINHA. E a referencia de todos
     os relatorios: um lugar so, sem ambiguidade;
  2. a BASE_BAP_UNIFICADA_PRODUTOS_BAP.xlsx (aba PRODUTOS, v8) - e dela que
     a Automacao tira as colunas (e o que completa quem nao esta no estoque);
  3. sem nenhum dos dois: a regra antiga (CATEGORIAS_PRODUTO.csv, fornecedor
     e descricao), convertida para os nomes novos.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

CAMPOS = ("CATEGORIA", "SISTEMA", "FAMILIA", "LINHA")
NAO_CLASSIFICADO = "NÃO CLASSIFICADO"
OUTROS = "OUTROS"

# a ordem das opcoes nos filtros e nas tabelas
# (03/11, Alexandre) PECAS em tres: "em categoria e importante ter PECAS
# LINHA LEVE, PECAS LINHA PESADA e PECAS LINHA MOTO". A meta de pecas e a
# campanha (5 pts por unidade de peca) continuam valendo para a soma das tres
PECAS_LEVE = "PEÇAS LINHA LEVE"
PECAS_PESADA = "PEÇAS LINHA PESADA"
PECAS_MOTO = "PEÇAS LINHA MOTO"
CATEGORIAS_PECAS = (PECAS_LEVE, PECAS_PESADA, PECAS_MOTO)
ORDEM_CATEGORIA = CATEGORIAS_PECAS + ("BATERIAS", "LUBRIFICANTES", "QUÍMICOS",
                                      "PNEUS", "ACESSÓRIOS", "OUTROS")
ORDEM_SISTEMA = ("SUSPENSÃO", "DIREÇÃO", "TRANSMISSÃO", "FREIO",
                 "ARREFECIMENTO", "MOTOR", "ELÉTRICA", "FILTRAÇÃO",
                 "LUBRIFICANTES", "QUÍMICOS", "RODAGEM", "ACESSÓRIOS",
                 "OUTROS")
ORDEM_LINHA = ("LEVE", "PESADA", "LEVE E PESADA", "MOTO", "UNIVERSAL",
               "OUTROS")

# (19/10, Alexandre) ARREFECIMENTO DO MOTOR: as duas familias do sistema
# ARREFECIMENTO viram uma so - COMPONENTES MECANICOS (so bomba d'agua) e
# COMPONENTES ELETRICOS E TERMICOS (eletroventilador e motor de ventilador).
# Vale por cima do ESTOQUE_BAP e da base unificada ate a base mudar (v9);
# o produto do ARREFECIMENTO sem familia (fora do estoque) entra junto.
FAMILIA_ARREFECIMENTO = "ARREFECIMENTO DO MOTOR"
_FAMILIA_TROCADA = {"COMPONENTESMECANICOS": FAMILIA_ARREFECIMENTO,
                    "COMPONENTESELETRICOSETERMICOS": FAMILIA_ARREFECIMENTO}
# muda quando a regra acima muda: entra na assinatura dos caches
# "arr2" (20/10): agua desmineralizada e aditivos em QUIMICOS no
# familia_nucleo (a regra de quem nao esta na base)
# "pl3" (03/11): PECAS em LINHA LEVE / PESADA / MOTO
VERSAO_REGRAS = "arr2-pl3"

NOME_BASE = "BASE_BAP_UNIFICADA_PRODUTOS_BAP.xlsx"
PASTA_AJUDA = "BAP Ajuda 2.0"

# a regra antiga (familia_nucleo) -> o SISTEMA novo
_SISTEMA_DA_FAMILIA_ANTIGA = {
    "FREIO": "FREIO", "SUSPENSAO": "SUSPENSÃO", "DIRECAO": "DIREÇÃO",
    "TRANSMISSAO": "TRANSMISSÃO", "ARREFECIMENTO": "ARREFECIMENTO",
    "MOTOR": "MOTOR", "FILTRACAO": "FILTRAÇÃO", "RODAGEM": "RODAGEM",
    "ELETRICA": "ELÉTRICA", "QUIMICOS": "QUÍMICOS",
    "LUBRIFICANTES": "LUBRIFICANTES", "ACESSORIOS": "ACESSÓRIOS",
}


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _chave(v) -> str:
    s = unicodedata.normalize("NFKD", _texto(v))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def cod(v) -> str:
    """O codigo do produto como chave (maiusculo, sem espaco nas pontas)."""
    return _texto(v).upper()


def ordenar(valores, ordem) -> list:
    pos = {v: i for i, v in enumerate(ordem)}
    return sorted(set(v for v in valores if v),
                  key=lambda v: (pos.get(v, len(ordem)), v))


# ------------------------------------------------------------ as fontes
def achar_base(raiz) -> Path | None:
    """A BASE_BAP_UNIFICADA mais nova: BAP Ajuda 2.0, raiz, RELATORIOS ou o
    backup de auxiliares."""
    raiz = Path(raiz)
    candidatos = []
    for pasta in (raiz / PASTA_AJUDA, raiz, raiz / "RELATORIOS"):
        candidatos += list(pasta.glob("BASE_BAP_UNIFICADA*PRODUTO*.xls*"))
    if not candidatos:
        for pasta in raiz.glob("BACKUP*/*AUXILIARES*"):
            candidatos += list(pasta.glob("BASE_BAP_UNIFICADA*PRODUTO*.xls*"))
    candidatos = [c for c in candidatos if not c.name.startswith("~$")]
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c.stat().st_mtime)


# (18/10) A LEITURA FICA NA MEMORIA: o Gerador de Meta abria o ESTOQUE_BAP
# 4 vezes por calculo (uma por mes do M3M), com o openpyxl - era quase todo
# o tempo do Farol de Clientes, do Farol de Metas e dos Kits. Agora le uma
# vez (com o leitor rapido, xlsx_rapido) e guarda ate o arquivo mudar
_MEMORIA_ABAS = {}


def _ler_aba(caminho, nome_aba, coluna_cod) -> dict:
    try:
        st = Path(caminho).stat()
        chave = (str(caminho), st.st_mtime_ns, st.st_size, nome_aba,
                 coluna_cod)
    except OSError:
        chave = None
    if chave is not None and chave in _MEMORIA_ABAS:
        return _MEMORIA_ABAS[chave]
    saida = _ler_aba_do_arquivo(caminho, nome_aba, coluna_cod)
    if chave is not None:
        for k in [k for k in _MEMORIA_ABAS if k[0] == chave[0]
                  and k[3] == nome_aba]:
            _MEMORIA_ABAS.pop(k, None)          # a versao velha do arquivo
        _MEMORIA_ABAS[chave] = saida
    return saida


def _ler_aba_do_arquivo(caminho, nome_aba, coluna_cod) -> dict:
    try:
        from xlsx_rapido import load_workbook   # noqa: PLC0415
    except ImportError:
        from openpyxl import load_workbook      # noqa: PLC0415
    saida = {}
    try:
        wb = load_workbook(caminho, read_only=True, data_only=True)
    except Exception:                                   # noqa: BLE001
        return saida
    try:
        ws = wb[nome_aba] if nome_aba in wb.sheetnames else wb.active
        it = ws.iter_rows(values_only=True)
        cab = [_chave(c) for c in next(it)]
        if _chave(coluna_cod) not in cab or "CATEGORIA" not in cab:
            return saida
        i_cod = cab.index(_chave(coluna_cod))
        idx = {c: cab.index(c) for c in CAMPOS if c in cab}
        if not {"SISTEMA", "FAMILIA", "LINHA"} <= set(idx):
            return saida                # arquivo antigo: sem a classificacao
        for r in it:
            if i_cod >= len(r):
                continue
            k = cod(r[i_cod])
            if not k or k in saida:
                continue
            reg = {c: _texto(r[i]) if i < len(r) else "" for c, i in idx.items()}
            if not reg.get("CATEGORIA"):
                continue
            saida[k] = reg
    except StopIteration:
        pass
    finally:
        wb.close()
    return saida


def ler_base(caminho) -> dict:
    """{codigo: {CATEGORIA, SISTEMA, FAMILIA, LINHA}} da aba
    PRODUTOS da base unificada (v8 em diante)."""
    if not caminho or not Path(caminho).exists():
        return {}
    return _ler_aba(caminho, "PRODUTOS", "CODIGO_BAP")


def ler_estoque(caminho) -> dict:
    """O mesmo, das colunas do ESTOQUE_BAP.xlsx (a referencia)."""
    if not caminho or not Path(caminho).exists():
        return {}
    return _ler_aba(caminho, "ESTOQUE_BAP", "COD_PRODUTO")


def regra_antiga(categoria_bap="", descricao="") -> dict:
    """Quem nao esta no estoque nem na base: a CATEGORIA BAP antiga e a
    familia por descricao, nos nomes novos."""
    cat = _texto(categoria_bap).upper()
    try:
        import familia_nucleo as fam                    # noqa: PLC0415
        f_ant, _g, lin = fam.classificar(descricao or "")
    except Exception:                                   # noqa: BLE001
        f_ant, lin = "OUTROS", "LEVE"
    sistema = _SISTEMA_DA_FAMILIA_ANTIGA.get(f_ant, OUTROS)
    if cat in ("PNEU", "PNEUS"):
        categoria, sistema = "PNEUS", "RODAGEM"
    elif cat in ("BATERIA", "BATERIAS"):
        categoria, sistema = "BATERIAS", "ELÉTRICA"
    elif cat == "LUBRIFICANTES":
        categoria, sistema = "LUBRIFICANTES", "LUBRIFICANTES"
    elif sistema == "QUÍMICOS":
        categoria = "QUÍMICOS"
    elif sistema == "ACESSÓRIOS":
        categoria = "ACESSÓRIOS"
    elif cat in ("", "OUTROS") and sistema == OUTROS:
        categoria = OUTROS
    else:
        categoria = "PEÇAS"
    if cat == "LINHA MOTO":
        lin = "MOTO"
    elif cat == "LINHA PESADA":
        lin = "PESADA"
    lin = {"AGRICOLA": "PESADA"}.get(lin, lin or "LEVE")
    return {"CATEGORIA": categoria, "SISTEMA": sistema,
            "FAMILIA": NAO_CLASSIFICADO, "LINHA": lin}


def e_pecas(categoria) -> bool:
    """PECAS (o nome antigo) ou uma das tres linhas de pecas."""
    return _chave(categoria).startswith("PECAS")


def categoria_da_linha(categoria, linha="") -> str:
    """(03/11) PECAS -> PECAS LINHA LEVE / PESADA / MOTO pela LINHA: MOTO
    = moto, PESADA = pesada e o resto (LEVE, LEVE E PESADA, UNIVERSAL,
    sem linha) = leve (Alexandre: "LEVE E PESADA" entra na leve). As outras
    categorias passam como estao."""
    if not e_pecas(categoria):
        return categoria
    c = _chave(categoria)
    for nova in CATEGORIAS_PECAS:          # ja dividida: so o nome certo
        if c == _chave(nova):
            return nova
    lin = _chave(linha)
    if lin == "MOTO":
        return PECAS_MOTO
    if lin == "PESADA":
        return PECAS_PESADA
    return PECAS_LEVE


def ajustar(reg: dict) -> dict:
    """As trocas de familia decididas depois da base (ver acima) e (03/11)
    a CATEGORIA de pecas pela LINHA."""
    if reg.get("CATEGORIA"):
        reg["CATEGORIA"] = categoria_da_linha(reg["CATEGORIA"],
                                              reg.get("LINHA"))
    fam = _FAMILIA_TROCADA.get(_chave(reg.get("FAMILIA")))
    if fam:
        reg["FAMILIA"] = fam
    elif _chave(reg.get("SISTEMA")) == "ARREFECIMENTO" and \
            reg.get("FAMILIA") in ("", NAO_CLASSIFICADO):
        reg["FAMILIA"] = FAMILIA_ARREFECIMENTO
    return reg


class Catalogo:
    """A classificacao pronta para consulta: estoque > base > regra."""

    def __init__(self, raiz, caminho_estoque=None, usar_estoque=True):
        raiz = Path(raiz)
        self.arq_base = achar_base(raiz)
        self.base = ler_base(self.arq_base)
        est = Path(caminho_estoque) if caminho_estoque else \
            raiz / "RELATORIOS" / "ESTOQUE_BAP.xlsx"
        self.estoque = ler_estoque(est) if usar_estoque else {}
        self.arq_estoque = est if self.estoque else None

    def __bool__(self):
        return bool(self.base or self.estoque)

    def de(self, codigo, categoria_bap="", descricao="") -> dict:
        k = cod(codigo)
        reg = self.estoque.get(k) or self.base.get(k)
        if reg:
            out = {c: reg.get(c, "") for c in CAMPOS}
            out["LINHA"] = out["LINHA"] or OUTROS
            out["FAMILIA"] = out["FAMILIA"] or NAO_CLASSIFICADO
            out["SISTEMA"] = out["SISTEMA"] or OUTROS
            return ajustar(out)
        return ajustar(regra_antiga(categoria_bap, descricao))
