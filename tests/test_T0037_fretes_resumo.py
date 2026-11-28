"""T-0037 — o Resumo do Farol de Fretes (pl_fretes) que o robô manda à web.

O PC não tem painel próprio do Fretes: o robô monta o Resumo
(`bap_automation.blocos_resumo_fretes_web`) com as barras dos 12 meses, as 3
tabelas do mês do pacote ("Por UF (NOV/26)", "Por cidade (NOV/26)" e "Por
transportadora (NOV/26)") e 2 frases (só em `insights_painel`, RD-0192). Valor × regra: os TOTAIS das 3 tabelas
são iguais entre si e iguais ao cartão "Notas com frete" (nº de notas e soma
do VLR NF) e ao "Frete estimado" (RN-POS-007 e RN-POS-009); a barra do mês é
o mesmo nº de notas. Sem dado pessoal (RN-GER-011, regra 6).

Base: o pacote real das bases congeladas, hoje = 24/11/2026. Teste trazido
do modulo-robo (robô 91e6f8a). Contrato §10.13; desenho docs/desenho/T-0037.md.
"""
import json
import re
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
_SEM_TRANSP = ("Sem transportadora", "Sem acompanhamento")
TITULOS_RESUMO = ["Por UF (NOV/26)", "Por cidade (NOV/26)",
                  "Por transportadora (NOV/26)"]


def _num(s):
    return int(re.sub(r"\D", "", s))


def _tabelas(f):
    return [b for b in f["painel"]["blocos"] if b["tipo"] == "tabela"]


@pytest.fixture(scope="module")
def real():
    r = rn.montar("pl_fretes", RAIZ, hoje=HOJE,
                  params=ba.params_farol_web("pl_fretes", 2026, 11))
    pac = ba.montar_pacote_web({"pl_fretes": r}, 2026, 11, raiz=RAIZ)
    return r, pac["relatorios"]["pl_fretes"]


def test_T0037_resumo_tem_barras_e_3_tabelas_do_mes(real):
    _, f = real
    tipos = [b["tipo"] for b in f["painel"]["blocos"]]
    assert tipos.count("barras") == 1
    assert tipos.count("tabela") == 3
    assert tipos.count("insights") == 0     # RD-0192: frases só no painel
    assert [b["titulo"] for b in _tabelas(f)] == TITULOS_RESUMO


def test_RN_POS_009_totais_das_tabelas_batem_com_o_cartao(real):
    """TOTAL de cada tabela = cartão "Notas com frete" (nº e VLR NF do
    detalhe) e "Frete estimado"; a barra de NOV/26 = o nº de notas."""
    _, f = real
    k = {c["rotulo"]: c for c in f["kpis"]}
    notas = _num(k["Notas com frete"]["valor"])
    valor = _num(k["Notas com frete"]["detalhe"])
    frete = _num(k["Frete estimado"]["valor"])
    assert notas > 0
    for b in _tabelas(f):
        assert b["total"][0] == "TOTAL", b["titulo"]
        assert b["total"][1] == notas == sum(x[1] for x in b["linhas"]), \
            b["titulo"]
        assert round(b["total"][2]) == valor, b["titulo"]
        assert round(b["total"][3]) == frete, b["titulo"]
        # o TOTAL sai do valor sem arredondar (= cartão); as linhas vêm em
        # centavos: a soma delas difere no máximo meio centavo por linha
        meio = 0.005 * len(b["linhas"]) + 1e-9
        assert abs(b["total"][2] - sum(x[2] for x in b["linhas"])) <= meio
        assert abs(b["total"][3] - sum(x[3] for x in b["linhas"])) <= meio
    barras = next(b for b in f["painel"]["blocos"] if b["tipo"] == "barras")
    assert len(barras["grafico"]["rotulos"]) == 12
    assert barras["grafico"]["series"][0]["valores"][-1] == notas


def test_RN_POS_009_sem_transportadora_da_tabela_bate_com_o_cartao(real):
    """Linha "Sem transportadora" de "Por transportadora (NOV/26)" = cartão
    "Sem transportadora" (a "Sem acompanhamento" fica fora dos dois)."""
    _, f = real
    k = {c["rotulo"]: c for c in f["kpis"]}
    t_tr = _tabelas(f)[2]
    lin = {x[0]: x for x in t_tr["linhas"]}
    n_tab = lin["Sem transportadora"][1] if "Sem transportadora" in lin else 0
    assert _num(k["Sem transportadora"]["valor"]) == n_tab


def test_RN_POS_009_totais_iguais_nas_3_tabelas(real):
    _, f = real
    tots = [b["total"] for b in _tabelas(f)]
    assert len(tots) == 3
    assert tots[0] == tots[1] == tots[2]


def test_T0037_resumo_so_2_frases_e_nao_repetem_cartao(real):
    _, f = real
    fr = [x for _, x in f["insights_painel"]]
    assert len(fr) == 2
    assert re.fullmatch(r"\w\w concentra \d+% do valor das notas com "
                        r"frete\.", fr[0])
    assert re.fullmatch(r".+ leva \d+% do valor\.", fr[1])
    assert not any("líquido" in x or "entregues" in x
                   or "sem transportadora" in x for x in fr)


def test_T0037_resumo_frases_batem_com_as_tabelas(real):
    """Valor × regra das 2 frases: a UF de maior VLR NF (sem a linha "Sem
    UF") e o % dela no TOTAL de "Por UF (NOV/26)"; a transportadora de maior
    VLR NF (sem "Sem transportadora" e "Sem acompanhamento") e o % dela no
    TOTAL de "Por transportadora (NOV/26)"."""
    _, f = real
    t_uf, _t_cid, t_tr = _tabelas(f)
    m = re.fullmatch(r"(\w\w) concentra (\d+)% do valor das notas com "
                     r"frete\.", f["insights_painel"][0][1])
    assert m
    uf, pct = m.group(1), int(m.group(2))
    lin = {x[0]: x for x in t_uf["linhas"]}
    assert uf in lin and uf != "Sem UF"
    assert lin[uf][2] == max(x[2] for x in t_uf["linhas"]
                             if x[0] != "Sem UF")
    assert pct == round(100 * lin[uf][2] / t_uf["total"][2])
    m = re.fullmatch(r"(.+) leva (\d+)% do valor\.",
                     f["insights_painel"][1][1])
    assert m
    tr, pct = m.group(1), int(m.group(2))
    lin = {x[0]: x for x in t_tr["linhas"]}
    assert tr in lin and tr not in _SEM_TRANSP
    assert lin[tr][2] == max(x[2] for x in t_tr["linhas"]
                             if x[0] not in _SEM_TRANSP)
    assert pct == round(100 * lin[tr][2] / t_tr["total"][2])


def _t(titulo, rot, linhas):
    return {"titulo": titulo, "colunas": [{"nome": n} for n in (
        "MÊS", rot, "NOTAS", "VLR NF", "VLR FRETE")],
            "filtros": [{"coluna": "MÊS", "padrao": "NOV/26"}],
            "linhas": linhas}


def test_T0037_rotulo_do_pc_passa_adiante_e_sem_acompanhamento_nao_vira_frase():
    """Os rótulos do PC (relatorios_nucleo.rotulo_agrupa_fretes) vão como
    estão; "Sem acompanhamento" (R$ 90, o maior) não é citado: a frase cita
    a de maior valor com transportadora, 30 de 140 = 21%."""
    r = {"tabelas": [
        _t("Por UF", "UF", [["NOV/26", "Sem UF", 1, 10.0, 1.0],
                            ["NOV/26", "PA", 2, 30.0, 3.0]]),
        _t("Por cidade", "CIDADE", [
            ["NOV/26", "CIDADE FICT A / Sem UF", 1, 10.0, 0.1],
            ["NOV/26", "Sem cidade / MA", 1, 5.0, 0.1]]),
        _t("Por transportadora", "TRANSPORTADORA", [
            ["NOV/26", "Sem acompanhamento", 1, 90.0, 0.1],
            ["NOV/26", "Sem transportadora", 1, 20.0, 0.1],
            ["NOV/26", "TRANSPORTADORA FICTICIA", 1, 30.0, 0.2]])]}
    blocos, frases = ba.blocos_resumo_fretes_web(r)
    rot = [x[0] for b in blocos if b["tipo"] == "tabela" for x in b["linhas"]]
    assert rot == ["PA", "Sem UF", "CIDADE FICT A / Sem UF",
                   "Sem cidade / MA", "Sem acompanhamento",
                   "TRANSPORTADORA FICTICIA", "Sem transportadora"]
    assert frases[1][1] == "TRANSPORTADORA FICTICIA leva 21% do valor."


def test_RN_GER_011_resumo_sem_dado_pessoal(real):
    r, f = real
    texto = (json.dumps(f["painel"], ensure_ascii=False)
             + json.dumps(f["insights_painel"], ensure_ascii=False))
    assert not re.search(r"(?<![\d.])\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}"
                         r"(?!\d)|(?<![\d.])\d{14}(?![\d.])", texto)
    assert "@" not in texto
    assert not re.search(r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}", texto)
    tn = next(t for t in r["tabelas"] if t["titulo"] == "Notas com frete")
    ic = [c["nome"] for c in tn["colunas"]].index("CLIENTE")
    nomes = {str(x[ic]) for x in tn["linhas"] if x[ic]}
    assert not [n for n in nomes if len(n) > 6 and n in texto]
    for b in _tabelas(f):
        assert not any(x in c["nome"].lower() for c in b["colunas"]
                       for x in ba._COLUNAS_PESSOA_TABELA_WEB)


def test_T0037_funcao_pura_sem_painel_e_sem_dado():
    assert ba.blocos_resumo_fretes_web({}) == ([], [])
    blocos, _ = ba.blocos_resumo_fretes_web(
        {"graficos": [{"rotulos": ["A"], "series": []}]})
    assert [b["tipo"] for b in blocos] == ["barras"]


def _tab_uf(linhas):
    return {"titulo": "Por UF", "colunas": [{"nome": n} for n in (
        "MÊS", "UF", "NOTAS", "VLR NF", "VLR FRETE")],
            "filtros": [{"coluna": "MÊS", "padrao": "NOV/26"}],
            "linhas": linhas}


def test_T0037_frase_da_uf_pula_a_linha_sem_uf():
    """"Sem UF" tem o maior valor, mas não é a UF citada; o % do valor
    ainda a inclui no total (50 de 150 = 33%)."""
    _, fr = ba.blocos_resumo_fretes_web({"tabelas": [_tab_uf([
        ["NOV/26", "Sem UF", 5, 100.0, 1.0],
        ["NOV/26", "PA", 1, 50.0, 1.0]])]})
    assert fr == [("info", "PA concentra 33% do valor das notas com frete.")]


def test_T0037_frase_da_uf_e_a_de_maior_valor_nao_a_de_mais_notas():
    """PA tem mais notas (5, R$ 100) e RR mais valor (1, R$ 300): a frase
    cita RR, com 300 de 400 = 75% do valor."""
    _, fr = ba.blocos_resumo_fretes_web({"tabelas": [_tab_uf([
        ["NOV/26", "PA", 5, 100.0, 5.0],
        ["NOV/26", "RR", 1, 300.0, 9.0]])]})
    assert fr == [("info", "RR concentra 75% do valor das notas com frete.")]


@pytest.mark.parametrize("rotulo", ["PA", "Sem UF"])
def test_T0037_uma_linha_no_por_uf_sem_frase_de_uf(rotulo):
    """Com uma linha só no "Por UF" (uma UF, ou só a "Sem UF") não há frase
    de UF (substitui os 2 testes do mesmo ramo, RD-0203)."""
    _, fr = ba.blocos_resumo_fretes_web({"tabelas": [_tab_uf([
        ["NOV/26", rotulo, 5, 100.0, 1.0]])]})
    assert fr == []
