"""T-0033, RN-VIS-001: a cor da Aderência vai do PC ao site pelo pacote.

RN-VIS-001 (docs/produto/03-regras.md): verde a partir de 80%, amarelo de
50% a 79,99%, vermelho abaixo de 50%; a mesma regra pinta a linha e cada dia,
no PC e no site. O PC põe o `chip` (relatorios_nucleo.faixa_aderencia) nas
colunas de dia e na % acumulada; o robô (bap_automation, selo "faixa_opc")
leva o chip ao pacote. Sem o chip no PC, as colunas vão sem cor (a web usa o
tom da linha) e a aba não cai.

Bases congeladas do repositório (NOV/2026, hoje = 24/11/2026, terça, Manaus).
Nenhum valor de célula é impresso: só título, coluna e contagem.
"""
import copy
import json
import re
import sys
import types
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
PARAMS = {"ANO": "2026", "MÊS": "11"}
RID, TITULO = "vc_visitas", "Aderência dia a dia"
RE_DIA = re.compile(r"^\d{2}/\d{2} (SEG|TER|QUA|QUI|SEX|SÁB|DOM)$")
RE_ACUM = re.compile(r"^% ADERÊNCIA ACUM\. ATÉ \d{2}/\d{2}$")


def _faixa_json():
    return [[a, f, t] for a, f, t in rn.faixa_aderencia()]


def _sem_chip(t):
    t2 = copy.copy(t)
    t2["colunas"] = [{k: v for k, v in c.items() if k != "chip"}
                     for c in t["colunas"]]
    return t2


def _tab(tabelas):
    return next(t for t in tabelas if t.get("titulo") == TITULO)


@pytest.fixture(scope="module")
def pc():
    """O Farol de Visita do PC nas bases congeladas."""
    return rn.montar(RID, RAIZ, hoje=HOJE, params=dict(PARAMS))


@pytest.fixture(scope="module")
def web_app():
    antes = set(sys.modules)
    sys.path.insert(0, str(RAIZ / "web"))
    try:
        from app import pacotes, tabelas
        yield types.SimpleNamespace(pacotes=pacotes, tabelas=tabelas)
    finally:
        sys.path.remove(str(RAIZ / "web"))
        for k in set(sys.modules) - antes:
            if k == "app" or k.startswith("app."):
                del sys.modules[k]


def test_RN_VIS_001_pc_pinta_os_dias_e_a_acumulada_com_a_faixa(pc):
    t = _tab(pc["tabelas"])
    nomes = [c["nome"] for c in t["colunas"]]
    assert nomes[:2] == ["SUPERVISOR", "VENDEDOR"]
    assert all(RE_DIA.match(n) for n in nomes[2:-1]) and RE_ACUM.match(nomes[-1])
    for c in t["colunas"][2:]:
        assert [list(f) for f in c["chip"]] == _faixa_json(), c["nome"]


def test_RN_VIS_001_robo_leva_o_chip_das_colunas_de_dia(pc):
    w = ba.tabela_web7(RID, _tab(pc["tabelas"]))
    assert w is not None
    cols = w["colunas"]
    assert [c["nome"] for c in cols[:2]] == ["SUPERVISOR", "VENDEDOR"]
    assert all("chip" not in c for c in cols[:2])
    for c in cols[2:]:
        assert c["tipo"] == "pct" and c["chip"] == _faixa_json(), c["nome"]
    json.dumps(w, allow_nan=False, default=str)


def test_RN_VIS_001_sem_chip_no_pc_sai_sem_cor_e_a_aba_fica(pc):
    t = _sem_chip(_tab(pc["tabelas"]))
    w = ba.tabela_web7(RID, t)
    assert w is not None                                  # a aba não cai
    assert [c["nome"] for c in w["colunas"]] == [c["nome"] for c in t["colunas"]]
    assert all("chip" not in c for c in w["colunas"])
    assert len(w["linhas"]) == len(t["linhas"])


def test_RN_VIS_001_chip_torto_no_pc_tira_so_a_aba(pc):
    t = _tab(pc["tabelas"])
    t2 = copy.copy(t)
    t2["colunas"] = [dict(c, chip="vermelho") if i == 2 else c
                     for i, c in enumerate(t["colunas"])]
    assert ba.tabela_web7(RID, t2) is None


def test_RN_VIS_001_pacote_real_leva_o_chip_e_passa_na_validacao(pc, web_app):
    p = ba.montar_pacote_web({RID: pc}, 2026, 11, raiz=RAIZ)
    q = json.loads(json.dumps(p, ensure_ascii=False, default=str))
    r = q["relatorios"][RID]
    t = _tab(r["tabelas"])
    for c in t["colunas"][2:]:
        assert c["chip"] == _faixa_json(), c["nome"]
    assert web_app.tabelas.validar(RID, r) == []
    assert web_app.pacotes.validar(q) == []


def test_RN_VIS_001_pacote_sem_chip_tem_a_aba_e_passa_na_validacao(pc,
                                                                   web_app):
    rel = dict(pc)
    rel["tabelas"] = [_sem_chip(t) if t.get("titulo") == TITULO else t
                      for t in pc["tabelas"]]
    p = ba.montar_pacote_web({RID: rel}, 2026, 11, raiz=RAIZ)
    q = json.loads(json.dumps(p, ensure_ascii=False, default=str))
    r = q["relatorios"][RID]
    assert TITULO in [t["titulo"] for t in r["tabelas"]]
    assert all("chip" not in c for c in _tab(r["tabelas"])["colunas"])
    assert web_app.tabelas.validar(RID, r) == []
    assert web_app.pacotes.validar(q) == []
