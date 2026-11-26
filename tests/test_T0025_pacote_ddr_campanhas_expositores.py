"""T-0025: o pacote do robô com Farol DDR (3 áreas), Campanhas BAP e Farol de Expositores, nas BASES CONGELADAS,
passa na validação da web, leva a especificação de edição e não leva dado pessoal (RN-GER-011).
O Farol DDR usa outubro/2026 (o único mês com Farol nas bases congeladas)."""
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
RIDS = ("farol_pv", "farol_vc", "farol_pl", "vc_champions", "tm_expositores")
ABAS = {"farol_pv": ["Hoje", "Pendentes de marcação", "Até hoje"],
        "farol_vc": ["Hoje", "Pendentes de marcação", "Até hoje"],
        "farol_pl": ["Hoje", "Pendentes de marcação", "Até hoje"],
        "vc_champions": ["Vendedores", "Supervisores", "Aux. Técnico", "Confrontos", "Pts por semana",
                         "Campanha relâmpago", "Regras"],
        "tm_expositores": ["Expositores", "Por estado", "Por status", "Cadastro de expositores"]}
RE_PESSOAL = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|[\w.+-]+@[\w-]+\.[\w.]+|\(?\d{2}\)?\s?9?\d{4}-\d{4}")


@pytest.fixture(scope="module")
def pacote():
    rels = {rid: rn.montar(rid, RAIZ, hoje=date(2026, 10, 26), params={"ANO": "2026", "MÊS": "10"}) for rid in RIDS}
    return rels, ba.montar_pacote_web(rels, 2026, 10, raiz=RAIZ)


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


def test_RN_GER_012_abas_na_ordem_e_a_web_aceita(pacote, web_app):
    _rels, p = pacote
    for rid in RIDS:
        r = p["relatorios"][rid]
        assert [t["titulo"] for t in r["tabelas"]] == ABAS[rid], rid
        assert web_app.tabelas.validar(rid, r) == [], rid
        assert not [a for a in r.get("avisos") or [] if a.startswith("Abas fora")], rid
    assert web_app.pacotes.validar(p) == []


def test_RN_GER_011_sem_documento_telefone_ou_email(pacote):
    _rels, p = pacote
    for rid in RIDS:
        txt = json.dumps(p["relatorios"][rid], ensure_ascii=False)
        assert not RE_PESSOAL.search(txt), rid


def test_RN_GER_012_edicao_no_pacote(pacote, web_app):
    _rels, p = pacote
    for rid in ("farol_pv", "farol_vc", "farol_pl"):
        for t in p["relatorios"][rid]["tabelas"]:
            ed = t.get("edicao")
            assert ed and ed["modulo"] == "farol" and len(ed["chaves"]) == len(t["linhas"]), (rid, t["titulo"])
            assert all(re.fullmatch(r"2026-10\|[^|]+\|\d+", c) for c in ed["chaves"])
            assert [c["campo"] for c in ed["campos"]] == ["status", "motivo"]
    t = p["relatorios"]["tm_expositores"]["tabelas"][0]
    assert t["edicao"]["modulo"] == "expositores" and all(c.startswith("EXP") for c in t["edicao"]["chaves"])
    assert t["edicao"]["novo"]["padroes"]["data"] == "hoje"
    # campanhas: só leitura (champions_config.json é dado digitado)
    assert not [x for x in p["relatorios"]["vc_champions"]["tabelas"] if "edicao" in x]


def test_RN_GER_012_colunas_do_robo_iguais_as_da_web(web_app):
    for rid, titulos in ABAS.items():
        for tit in titulos:
            if tit == "Pts por semana":
                continue                                    # colunas por padrão de nome, conferidas acima
            robo = [(c[0], c[1], c[2]) for c in ba._COLUNAS_TABELAS_WEB[rid][tit]]
            web = [(n, tp, o) for n, tp, o in web_app.tabelas.COLUNAS[tit]]
            assert robo == web, (rid, tit)
