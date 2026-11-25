"""T-0017, entregas 3 a 5: todas as abas do PC dos Faróis de Pedidos,
Entregas e Visita no site. Funções puras de `relatorios_nucleo`
(modulo-farois):

- RN-GER-011: nome e texto de cliente vão ao site sem CPF/CNPJ (no começo,
  no meio ou no fim do nome) e o texto livre vai sem telefone, e-mail e
  documento (trocados por "[removido]"); o código do cliente fica.
  -> `sem_documento`, `cliente_sem_documento`, `texto_sem_contato`.
- Abas do PC no site: `linhas_padrao(t, params)` devolve as linhas que a
  tela mostra ao abrir a aba (a mesma regra de
  `bap_relatorios.VistaTabela._filtradas` no estado inicial) e
  `recortes_em_linhas(t)` os índices de cada recorte por função (o recorte
  `{"top": N}` fica fora).

A comparação com a tela roda o `VistaTabela.__init__` e o `_filtradas` DE
VERDADE, com um Tk de mentira (sem janela): StringVar guarda o valor e o
resto (Frame, Label, Combobox, Tabela) aceita qualquer chamada. Sem tkinter
instalado (Python sem Tk), os módulos `tkinter*` entram como coringa só
durante o import e saem depois (o `sys.modules` volta ao que era).

Dados 100% fictícios: "CLIENTE FICTICIO", códigos 9xxxxx, documentos e
telefones inventados.
"""
import logging
import sys
import types
from datetime import date, datetime

import pytest

import relatorios_nucleo as rn

R = "[removido]"


# =================================================================== RN-GER-011
@pytest.mark.parametrize("entrada, esperado", [
    # começo, com e sem máscara
    ("12.345.678/0001-90 CLIENTE FICTICIO LTDA", "CLIENTE FICTICIO LTDA"),
    ("12345678000190 CLIENTE FICTICIO", "CLIENTE FICTICIO"),
    ("123.456.789-01 - CLIENTE FICTICIO", "CLIENTE FICTICIO"),
    ("12345678901 CLIENTE FICTICIO", "CLIENTE FICTICIO"),
    # fim, com e sem máscara
    ("CLIENTE FICTICIO - 12.345.678/0001-90", "CLIENTE FICTICIO"),
    ("CLIENTE FICTICIO 123.456.789-01", "CLIENTE FICTICIO"),
    ("CLIENTE FICTICIO 12345678000190", "CLIENTE FICTICIO"),
    ("CLIENTE FICTICIO 12345678901 ", "CLIENTE FICTICIO"),
    # meio, com máscara
    ("CLIENTE 12.345.678/0001-90 FICTICIO", "CLIENTE FICTICIO"),
    ("CLIENTE FICTICIO 123.456.789-01 FILIAL", "CLIENTE FICTICIO FILIAL"),
    # meio, SEM máscara (a RN-GER-011 diz "no começo, no meio ou no fim")
    ("CLIENTE 12345678000190 FICTICIO", "CLIENTE FICTICIO"),
    ("CLIENTE FICTICIO CPF 12345678901 LOJA 2", "CLIENTE FICTICIO CPF LOJA 2"),
    # dois documentos
    ("CLIENTE FICTICIO 12.345.678/0001-90 - 123.456.789-01",
     "CLIENTE FICTICIO"),
    # só o documento
    ("12.345.678/0001-90", ""),
    (12345678000190, ""),
    # número que não é documento fica
    ("AUTO PECAS 2000 LTDA", "AUTO PECAS 2000 LTDA"),
    ("3 IRMAOS PECAS FICTICIA", "3 IRMAOS PECAS FICTICIA"),
    ("CLIENTE FICTICIO 1234567890123", "CLIENTE FICTICIO 1234567890123"),
    # vazio
    (None, ""),
    ("", ""),
], ids=["comeco_cnpj_mascara", "comeco_cnpj_sem_mascara",
        "comeco_cpf_mascara", "comeco_cpf_sem_mascara",
        "fim_cnpj_mascara", "fim_cpf_mascara", "fim_cnpj_sem_mascara",
        "fim_cpf_sem_mascara_espaco", "meio_cnpj_mascara", "meio_cpf_mascara",
        "meio_cnpj_sem_mascara", "meio_cpf_sem_mascara", "dois_documentos",
        "so_documento", "so_documento_numero", "numero_curto_fica",
        "numero_no_comeco_fica", "13_digitos_fica", "none", "vazio"])
def test_RN_GER_011_sem_documento_comeco_fim_meio(entrada, esperado):
    assert rn.sem_documento(entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("900001 - CLIENTE FICTICIO 12.345.678/0001-90",
     "900001 - CLIENTE FICTICIO"),
    ("900001 - 12.345.678/0001-90 CLIENTE FICTICIO",
     "900001 - CLIENTE FICTICIO"),
    ("900001-01 - 12345678000190 CLIENTE FICTICIO",
     "900001-01 - CLIENTE FICTICIO"),
    ("900002 - CLIENTE FICTICIO 12345678901", "900002 - CLIENTE FICTICIO"),
    # o código de 6 dígitos não é confundido com documento
    ("900003 - 3 IRMAOS PECAS FICTICIA", "900003 - 3 IRMAOS PECAS FICTICIA"),
    ("900001-01 - CLIENTE FICTICIO", "900001-01 - CLIENTE FICTICIO"),
    # texto só com o código (com e sem loja, com espaço, número)
    ("900001", "900001"),
    ("900001-01", "900001-01"),
    (" 900001 ", "900001"),
    (900001, "900001"),
    # nome que era só o documento: fica o código
    ("900001 - 12345678000190", "900001"),
    ("900001 - 123.456.789-01", "900001"),
    ("900001 - ", "900001"),
    # documento sem máscara no meio do nome (RN-GER-011: "no meio")
    ("900004 - CLIENTE 12345678901 FICTICIO", "900004 - CLIENTE FICTICIO"),
    # sem código: limpa como sem_documento
    ("CLIENTE FICTICIO 12345678901", "CLIENTE FICTICIO"),
    (None, ""),
], ids=["fim_cnpj_mascara", "comeco_nome_cnpj_mascara",
        "loja_cnpj_sem_mascara", "fim_cpf_sem_mascara",
        "nome_com_numero", "loja_sem_documento", "so_codigo",
        "so_codigo_loja", "so_codigo_espacos", "so_codigo_numero",
        "nome_so_cnpj", "nome_so_cpf", "nome_vazio",
        "meio_cpf_sem_mascara", "sem_codigo", "none"])
def test_RN_GER_011_cliente_mantem_codigo(entrada, esperado):
    assert rn.cliente_sem_documento(entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    # telefone (8 a 13 dígitos, com ou sem DDD/55 e máscara)
    ("Ligar (92) 99123-4567 amanha", f"Ligar {R} amanha"),
    ("fone 92 991234567 ok", f"fone {R} ok"),
    ("+55 92 99123-4567", R),
    ("5592991234567", R),
    ("92991234567", R),
    ("tel 3234-5678", f"tel {R}"),
    ("(92) 3234-5678", R),
    # e-mail
    ("mandar para fulano.ficticio@exemplo.com.br hoje", f"mandar para {R} hoje"),
    # documento com e sem máscara, no meio do texto
    ("doc 12.345.678/0001-90 ok", f"doc {R} ok"),
    ("doc 12345678000190 ok", f"doc {R} ok"),
    ("cpf 123.456.789-01", f"cpf {R}"),
    ("cpf 12345678901", f"cpf {R}"),
    # tudo junto
    ("CLIENTE FICTICIO 92 99123-4567 / x@exemplo.com / 12345678000190",
     f"CLIENTE FICTICIO {R} / {R} / {R}"),
    # o que não é contato fica: código do cliente, pedido, NF, data
    ("cliente 900001", "cliente 900001"),
    ("pedido 912345 de 24/11/2026", "pedido 912345 de 24/11/2026"),
    ("NF 000912345", "NF 000912345"),
    (None, ""),
    ("", ""),
], ids=["fone_celular_mascara", "fone_celular_sem_mascara", "fone_55",
        "fone_13_digitos", "fone_11_digitos", "fone_fixo_sem_ddd",
        "fone_fixo_ddd", "email", "cnpj_mascara", "cnpj_sem_mascara",
        "cpf_mascara", "cpf_sem_mascara", "tudo_junto", "codigo_fica",
        "pedido_e_data_ficam", "nf_9_digitos_fica", "none", "vazio"])
def test_RN_GER_011_texto_livre_sem_contato(entrada, esperado):
    assert rn.texto_sem_contato(entrada) == esperado


@pytest.mark.parametrize("valor", [
    "R$ 1.234,56", "R$ 9.999,99", "R$ 123.456,78", "R$ 12.345.678,90",
    "R$ 1.234.567.890,12", "R$ 1234,56", "R$ 1234567,89",
    "R$ 12345678,90",
], ids=["milhar", "milhar_9", "centena_de_milhar", "dezena_de_milhao",
        "bilhao", "sem_ponto_4", "sem_ponto_7", "sem_ponto_8"])
def test_RN_GER_011_texto_livre_valor_em_reais_fica(valor):
    """Valor em reais no texto livre não é telefone: não vira [removido]."""
    texto = f"saldo de {valor} em aberto"
    assert rn.texto_sem_contato(texto) == texto


def test_RN_GER_011_limpeza_e_idempotente():
    """Limpar de novo o que já foi limpo não muda nada (o robô pode passar
    duas vezes pela mesma coluna)."""
    for f, s in ((rn.sem_documento, "12345678000190 CLIENTE FICTICIO"),
                 (rn.cliente_sem_documento,
                  "900001 - CLIENTE FICTICIO 123.456.789-01"),
                 (rn.texto_sem_contato,
                  "Ligar (92) 99123-4567 ou x@exemplo.com")):
        uma = f(s)
        assert f(uma) == uma


# ======================================================= a tela de verdade
class _Coringa:
    """Qualquer widget: aceita qualquer chamada e qualquer atributo."""

    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Coringa()

    def __getattr__(self, nome):
        return _Coringa()


class _Var:
    """tk.StringVar sem Tk: guarda o valor."""

    def __init__(self, master=None, value=None, name=None):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class _ModTk(types.ModuleType):
    def __getattr__(self, nome):
        return _Coringa


def _mod_tk(nome):
    m = _ModTk(nome)
    m.StringVar = _Var
    m.TclError = Exception
    return m


@pytest.fixture(scope="module")
def br():
    """bap_relatorios importado; sem tkinter, com coringas só no import."""
    antes = set(sys.modules)
    cache = sys.pycache_prefix
    try:
        import tkinter  # noqa: F401
        stub = False
    except ImportError:
        stub = True
        for nome in ("tkinter", "tkinter.ttk", "tkinter.messagebox",
                     "tkinter.filedialog", "tkinter.font",
                     "tkinter.simpledialog", "tkinter.colorchooser"):
            sys.modules[nome] = _mod_tk(nome)
    try:
        import bap_relatorios
        yield bap_relatorios
    finally:
        sys.pycache_prefix = cache          # o import mexe no cache do Python
        if stub:
            for k in set(sys.modules) - antes:
                del sys.modules[k]


@pytest.fixture
def tela(br, monkeypatch):
    """tela(t, params) -> índices (em linhas_filtro ou linhas) que a
    VistaTabela mostra ao abrir; recorte=rotulo escolhe um recorte."""
    monkeypatch.setattr(br, "tk", _mod_tk("tk_falso"))
    monkeypatch.setattr(br, "ttk", _mod_tk("ttk_falso"))
    monkeypatch.setattr(br, "caixa_de_filtro", _Coringa)
    monkeypatch.setattr(br.bv, "Tabela", _Coringa)
    monkeypatch.setattr(br.VistaTabela, "aplicar", lambda self, **k: None)

    def _ver(t, params=(), recorte=None):
        janela = types.SimpleNamespace(
            gerais=[], gerais_escolha={}, nomes_params=list(params),
            _filtros_guardados=None, rel={})
        v = br.VistaTabela(_Coringa(), t, janela)
        if recorte is not None:
            v.var_recorte.set(recorte)
        base = t.get("linhas_filtro") or t["linhas"]
        pos = {id(l): k for k, l in enumerate(base)}
        return [pos[id(l)] for l, _tom in v._filtradas()]
    return _ver


# ------------------------------------------------------------ tabela fictícia
COLS = [{"nome": "MÊS", "tipo": "texto"}, {"nome": "SITUAÇÃO", "tipo": "texto"},
        {"nome": "DATA", "tipo": "data"}, {"nome": "UF", "tipo": "texto"},
        {"nome": "VENDEDOR PLANNER", "tipo": "texto"},
        {"nome": "PRODUTO", "tipo": "texto"}, {"nome": "QTD", "tipo": "int"},
        {"nome": "META", "tipo": "moeda"}]
V_A, V_B, V_C = ("900101 - VENDEDOR FICTICIO A",
                 "900102 - VENDEDOR FICTICIO B",
                 "900103 - VENDEDOR FICTICIO C")


def _linhas():
    return [
        ["NOV/26", "EM ABERTO", date(2026, 11, 3), "AM", V_A, "P1; P2", 5,
         100.0],
        ["OUT/26", "EM ABERTO", date(2026, 10, 30), "AM", V_B, "P2", 2,
         300.0],
        ["NOV/26", "FATURADO", date(2026, 11, 3), "PA", V_A, "P3", 7, 50.0],
        ["NOV/26", "EM ABERTO", date(2026, 11, 4), "PA", V_B, "", 0, 200.0],
        ["NOV/26", None, None, "RR", V_C, None, None, None],
    ]


def _t(filtros, **extra):
    t = {"titulo": "Pedidos", "colunas": COLS, "linhas": _linhas(),
         "tons": [""] * 5, "filtros": list(filtros), "recortes": []}
    t.update(extra)
    return t


MES_NOV = {"coluna": "MÊS", "padrao": "NOV/26", "oculto": True}
TODAS = [0, 1, 2, 3, 4]

CASOS = {
    # filtro oculto: vale e não aparece
    "oculto": ([MES_NOV], (), {}, [0, 2, 3, 4]),
    # oculto vale mesmo sem linha no mês (a aba não abre com os 12 meses)
    "oculto_sem_linha": ([{"coluna": "MÊS", "padrao": "DEZ/26",
                           "oculto": True}], (), {}, []),
    # padrão válido
    "padrao_valido": ([MES_NOV, {"coluna": "SITUAÇÃO",
                                 "padrao": "EM ABERTO"}], (), {}, [0, 3]),
    # padrão inválido (não há o valor): a caixa abre em (todos)
    "padrao_invalido": ([{"coluna": "SITUAÇÃO", "padrao": "XX"}], (), {},
                        TODAS),
    # data: compara dd/mm/aaaa
    "padrao_data": ([{"coluna": "DATA", "padrao": "03/11/2026"}], (), {},
                    [0, 2]),
    "padrao_data_invalida": ([{"coluna": "DATA", "padrao": "2026-11-03"}],
                             (), {}, TODAS),
    # número: compara o texto
    "padrao_numero": ([{"coluna": "QTD", "padrao": "7"}], (), {}, [2]),
    # multi: o valor numa lista separada por ";"
    "padrao_multi": ([{"coluna": "PRODUTO", "multi": True, "padrao": "P2"}],
                     (), {}, [0, 1]),
    # filtro sem padrão (texto solto) não corta
    "sem_padrao": (["UF", "VENDEDOR PLANNER", {"coluna": "SITUAÇÃO"}], (),
                   {}, TODAS),
    # coluna que não existe é ignorada
    "coluna_inexistente": ([{"coluna": "FILIAL", "padrao": "AM"}], (), {},
                           TODAS),
    # filtros_fora: a aba não mostra o filtro e ele não corta
    "filtros_fora": ([{"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}], (),
                     {"filtros_fora": ["SITUAÇÃO"]}, TODAS),
    # repetido com o parâmetro de cima (VENDEDOR PLANNER = VENDEDOR): vira
    # oculto e vale
    "repetido_oculto": ([{"coluna": "VENDEDOR PLANNER", "padrao": V_A}],
                        ("VENDEDOR",), {}, [0, 2]),
    # repetido, oculto, com padrão sem linha: vale (nenhuma linha)
    "repetido_sem_linha": ([{"coluna": "VENDEDOR PLANNER",
                             "padrao": "900199 - VENDEDOR FICTICIO Z"}],
                           ("VENDEDOR",), {}, []),
    # o mesmo padrão sem parâmetro em cima: inválido, (todos)
    "nao_repetido_invalido": ([{"coluna": "VENDEDOR PLANNER",
                                "padrao": "900199 - VENDEDOR FICTICIO Z"}],
                              (), {}, TODAS),
    # repetido sem padrão (texto solto): sai da aba
    "repetido_solto": (["VENDEDOR PLANNER"], ("VENDEDOR",), {}, TODAS),
    # top_n: corta depois do filtro
    "top_n": ([{"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}], (),
              {"top_n": 2}, [0, 1]),
    # top_n com ordem_top (META, QTD): da maior meta
    "top_n_ordem": ([{"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}], (),
                    {"top_n": 2, "ordem_top": (7, 6)}, [1, 0]),
    # top_n maior que as linhas
    "top_n_folga": ([MES_NOV], (), {"top_n": 10}, [0, 2, 3, 4]),
}


@pytest.mark.parametrize("nome", list(CASOS))
def test_T0017_linhas_padrao_igual_a_tela(nome, tela):
    filtros, params, extra, esperado = CASOS[nome]
    t = _t(filtros, **extra)
    meu = rn.linhas_padrao(t, list(params) if params else None)
    assert meu == esperado                     # a regra, escrita à mão
    assert meu == tela(t, params)              # = VistaTabela._filtradas


def test_T0017_linhas_padrao_top_n_na_carteira_inteira(tela):
    """Top N com `linhas_filtro` (carteira inteira): o filtro corre na
    carteira e o top se refaz dentro dele; os índices são de
    `linhas_filtro`, como a tela."""
    carteira = _linhas()
    t = _t([{"coluna": "SITUAÇÃO", "padrao": "EM ABERTO"}],
           top_n=2, ordem_top=(7, 6))
    t["linhas_filtro"], t["tons_filtro"] = carteira, [""] * 5
    t["linhas"], t["tons"] = carteira[:2], [""] * 2
    meu = rn.linhas_padrao(t)
    assert meu == [1, 0]
    assert meu == tela(t)


def test_T0017_linhas_padrao_data_com_hora(tela):
    """Coluna de data com hora (datetime): o padrão dd/mm/aaaa pega o dia."""
    t = _t([{"coluna": "DATA", "padrao": "03/11/2026"}])
    for l in t["linhas"]:
        if l[2] is not None:
            l[2] = datetime(l[2].year, l[2].month, l[2].day, 10, 30)
    meu = rn.linhas_padrao(t)
    assert meu == [0, 2]
    assert meu == tela(t)


def test_T0017_linhas_padrao_sem_filtros_mostra_tudo(tela):
    t = _t([])
    t.pop("filtros")
    assert rn.linhas_padrao(t) == TODAS
    t["filtros"] = []
    assert rn.linhas_padrao(t) == tela(t) == TODAS


# --------------------------------------------------------- recortes_em_linhas
def _t_recortes():
    return _t([], recortes=[
        ("Só AM", lambda l: l[3] == "AM"),
        ("Top 2 da meta", {"top": 2, "coluna": 7}),
        ("Com meta", lambda l: (l[7] or 0) > 0),
        ("Qtd acima de 3", lambda l: l[6] > 3),   # a linha sem QTD quebra
        ("Top 1 positivo", {"top": 1, "coluna": 6, "so_positivo": True}),
    ])


def test_T0017_recortes_em_linhas_sem_o_top(caplog):
    t = _t_recortes()
    with caplog.at_level(logging.WARNING):
        saida = rn.recortes_em_linhas(t)
    assert saida == [
        {"rotulo": "Só AM", "linhas": [0, 1]},
        {"rotulo": "Com meta", "linhas": [0, 1, 2, 3]},
        {"rotulo": "Qtd acima de 3", "linhas": [0, 2]},
    ]
    assert all("top" not in r["rotulo"].lower() for r in saida)
    avisos = " ".join(r.getMessage() for r in caplog.records)
    assert "Top 2 da meta" in avisos and "Top 1 positivo" in avisos


def test_T0017_recortes_em_linhas_igual_a_tela(tela):
    """Cada recorte por função deixa as mesmas linhas que a tela (sem
    filtro, recorte escolhido na caixa)."""
    t = _t_recortes()
    for r in rn.recortes_em_linhas(t):
        if r["rotulo"] == "Qtd acima de 3":
            continue        # na tela a linha sem QTD quebra (TypeError)
        assert r["linhas"] == tela(t, recorte=r["rotulo"]), r["rotulo"]


def test_T0017_recortes_em_linhas_vazio():
    assert rn.recortes_em_linhas(_t([])) == []
    t = _t([])
    t.pop("recortes")
    assert rn.recortes_em_linhas(t) == []
    t["recortes"] = None
    assert rn.recortes_em_linhas(t) == []
