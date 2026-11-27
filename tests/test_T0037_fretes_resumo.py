"""T-0037 — o Resumo do Farol de Fretes (pl_fretes) que o robô manda à web.

O PC não tem painel próprio do Fretes: o robô monta o Resumo
(`bap_automation.blocos_resumo_fretes_web`) com as barras dos 12 meses, as 3
tabelas do mês do pacote ("Por UF (NOV/26)", "Por cidade (NOV/26)" e "Por
transportadora (NOV/26)") e 2 frases. Valor × regra: os TOTAIS das 3 tabelas
são iguais entre si e iguais ao cartão "Notas com frete" (nº de notas e soma
do VLR NF) e ao "Frete estimado" (RN-POS-007 e RN-POS-009); a barra do mês é
o mesmo nº de notas. Sem dado pessoal (RN-GER-011, regra 6).

Base: o pacote real das bases congeladas, hoje = 24/11/2026. Teste trazido
do modulo-robo (robô 4370d2d). Contrato §10.12; desenho docs/desenho/T-0037.md.
Sem os faróis e o robô da T-0037, pula.
"""
import json
import re
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

if not (hasattr(rn, "kpis_fretes")
        and "pl_fretes" in getattr(ba, "FAROIS_WEB", ())
        and hasattr(ba, "blocos_resumo_fretes_web")):
    pytest.skip("robô/faróis da T-0037 ainda não entraram",
                allow_module_level=True)

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
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


def test_T0037_resumo_tem_barras_3_tabelas_do_mes_e_frases(real):
    _, f = real
    tipos = [b["tipo"] for b in f["painel"]["blocos"]]
    assert tipos.count("barras") == 1
    assert tipos.count("tabela") == 3
    assert tipos.count("insights") == 1
    assert [b["titulo"] for b in _tabelas(f)] == TITULOS_RESUMO
    assert f["insights_painel"]


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


def test_RN_POS_009_totais_iguais_nas_3_tabelas(real):
    _, f = real
    tots = [b["total"] for b in _tabelas(f)]
    assert len(tots) == 3
    assert tots[0] == tots[1] == tots[2]


def test_T0037_resumo_so_2_frases_e_nao_repetem_cartao(real):
    _, f = real
    fr = [x for _, x in f["insights_painel"]]
    ins = next(b for b in f["painel"]["blocos"] if b["tipo"] == "insights")
    assert len(fr) == 2
    assert fr == [x for _, x in ins["linhas"]]
    assert re.fullmatch(r"\w\w tem \d+ das \d+ notas com frete e \d+% do "
                        r"valor \(R\$ [\d.]+\)\.", fr[0])
    assert re.fullmatch(r".+ leva \d+% do valor: R\$ [\d.]+ em \d+ notas?\.",
                        fr[1])
    assert not any("líquido" in x or "entregues" in x
                   or "sem transportadora" in x for x in fr)


def test_T0037_resumo_frase_de_uf_bate_com_a_tabela(real):
    """Valor × regra da 1ª frase: a UF de maior VLR NF (sem a linha "Sem
    UF"), o nº de notas dela, o total (= cartão) e o % do valor saem da
    tabela "Por UF (NOV/26)"."""
    _, f = real
    fr = f["insights_painel"][0][1]
    m = re.fullmatch(r"(\w\w) tem (\d+) das (\d+) notas com frete e (\d+)% "
                     r"do valor \(R\$ ([\d.]+)\)\.", fr)
    assert m
    uf, n_uf, n_tot, pct, rs = m.groups()
    t_uf = _tabelas(f)[0]
    lin = {x[0]: x for x in t_uf["linhas"]}
    assert uf in lin
    assert int(n_uf) == lin[uf][1]
    assert int(n_tot) == t_uf["total"][1]
    assert uf != "Sem UF"                       # a linha sem UF não é citada
    assert lin[uf][2] == max(x[2] for x in t_uf["linhas"]
                             if x[0] != "Sem UF")
    assert int(pct) == round(100 * lin[uf][2] / t_uf["total"][2])
    assert int(rs.replace(".", "")) == round(lin[uf][2])


def test_T0037_rotulos_sem_parenteses():
    r = {"kpis": [], "tabelas": [
        {"titulo": "Por UF", "colunas": [{"nome": n} for n in (
            "MÊS", "UF", "NOTAS", "VLR NF", "VLR FRETE")],
         "filtros": [{"coluna": "MÊS", "padrao": "NOV/26"}],
         "linhas": [["NOV/26", "(sem)", 1, 10.0, 1.0],
                    ["NOV/26", "PA", 2, 30.0, 3.0]]},
        {"titulo": "Por cidade", "colunas": [{"nome": n} for n in (
            "MÊS", "CIDADE", "NOTAS", "VLR NF", "VLR FRETE")],
         "filtros": [{"coluna": "MÊS", "padrao": "NOV/26"}],
         "linhas": [["NOV/26", "(sem) / PA", 1, 10.0, 0.1]]},
        {"titulo": "Por transportadora", "colunas": [{"nome": n} for n in (
            "MÊS", "TRANSPORTADORA", "NOTAS", "VLR NF", "VLR FRETE")],
         "filtros": [{"coluna": "MÊS", "padrao": "NOV/26"}],
         "linhas": [["NOV/26", "(sem)", 1, 10.0, 0.1],
                    ["NOV/26", "TRANSPORTADORA FICTICIA", 1, 30.0, 0.2]]}]}
    blocos, frases = ba.blocos_resumo_fretes_web(r)
    rot = [x[0] for b in blocos if b["tipo"] == "tabela"
           for x in b.get("linhas", [])]
    assert rot == ["PA", "Sem UF", "Sem cidade / PA",
                   "TRANSPORTADORA FICTICIA", "Sem transportadora"]
    assert frases[1][1] == ("TRANSPORTADORA FICTICIA leva 75% do valor: "
                            "R$ 30 em 1 nota.")


def test_T0037_uma_uf_sem_frase_de_uf():
    t = {"titulo": "Por UF", "colunas": [{"nome": n} for n in (
        "MÊS", "UF", "NOTAS", "VLR NF", "VLR FRETE")],
         "filtros": [{"coluna": "MÊS", "padrao": "NOV/26"}],
         "linhas": [["NOV/26", "PA", 2, 30.0, 3.0]]}
    _, frases = ba.blocos_resumo_fretes_web({"tabelas": [t]})
    assert frases == []


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
    """"Sem UF" tem o maior valor, mas não é a UF citada; o total (6 notas)
    e o % do valor ainda a incluem (50 de 150 = 33%)."""
    _, fr = ba.blocos_resumo_fretes_web({"tabelas": [_tab_uf([
        ["NOV/26", "(sem)", 5, 100.0, 1.0],
        ["NOV/26", "PA", 1, 50.0, 1.0]])]})
    assert fr == [("info",
                   "PA tem 1 das 6 notas com frete e 33% do valor (R$ 50).")]


def test_T0037_frase_da_uf_e_a_de_maior_valor_nao_a_de_mais_notas():
    """PA tem mais notas (5, R$ 100) e RR mais valor (1, R$ 300): a frase
    cita RR, com 300 de 400 = 75% do valor."""
    _, fr = ba.blocos_resumo_fretes_web({"tabelas": [_tab_uf([
        ["NOV/26", "PA", 5, 100.0, 5.0],
        ["NOV/26", "RR", 1, 300.0, 9.0]])]})
    assert fr == [("info",
                   "RR tem 1 das 6 notas com frete e 75% do valor (R$ 300).")]


def test_T0037_so_sem_uf_nao_tem_frase_de_uf():
    _, fr = ba.blocos_resumo_fretes_web({"tabelas": [_tab_uf([
        ["NOV/26", "(sem)", 5, 100.0, 1.0]])]})
    assert fr == []


def test_T0037_cidade_sem_uf_sem_barra_solta():
    """A cidade sem UF sai só com o nome (sem " /"); "(sem) / " vira "Sem
    cidade"."""
    f = ba._rotulo_sem_fretes_web
    assert f("CIDADE", "CIDADE FICT A / ") == "CIDADE FICT A"
    assert f("CIDADE", "CIDADE FICT A /") == "CIDADE FICT A"
    assert f("CIDADE", "CIDADE FICT A / PA") == "CIDADE FICT A / PA"
    assert f("CIDADE", "(sem) / ") == "Sem cidade"
    assert f("CIDADE", "(sem) / PA") == "Sem cidade / PA"
