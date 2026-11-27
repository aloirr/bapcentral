"""T-0035 (robô, 10.8.7): teto dos anexos igual ao da web, cortes por farol na
ordem de _CORTES_FAROL_WEB e corte intermediário do Entregas. Dados fictícios.

Trazido do modulo-robo (T-0035) e revisto pelo testes. Os tetos do robô
conferidos com os da web em test_T0035_robo_web.py."""
import base64
import copy
from pathlib import Path

import pytest

import bap_automation as ba

MB = 1024 * 1024


def _png(n):
    return base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * n).decode()


def _csv(i, n=100):
    return {"nome": f"20261127_{i}_ABC_BAPReversaLoja.csv", "conteudo": "a;b\n" * n}


def _entregas(n_linhas=400, junta=True):
    cols = [{"nome": "DT. PED", "tipo": "dia"}, {"nome": "CIDADE", "tipo": "texto"}]
    linhas = [[f"2026-11-{1 + i % 27:02d}", "x" * 60] for i in range(n_linhas)]
    tab = {"titulo": "Entregas", "colunas": cols, "linhas": linhas,
           "tons": [str(i % 3) for i in range(n_linhas)]}
    if junta:
        tab["juntas"] = [{"titulo": "Pendências dos meses anteriores", "liga": None,
                          "tabela": {"titulo": "Pendências dos meses anteriores", "colunas": cols,
                                     "linhas": linhas[:200], "tons": [""] * 200}}]
    return {"titulo": "Farol de Entregas", "avisos": [], "tabelas": [tab]}


def test_ADR0003_parcial_acima_do_teto_sai_so_ela_com_aviso():
    f = {"avisos": [], "parciais": {"acum": {"rotulo": "a", "png": "x" * (ba.MAX_PNG_B64 + 1)},
                                    "d1": {"rotulo": "d", "png": _png(10)}}}
    ent = copy.deepcopy(f)
    novo = ba._cortar_farol_web("pv_pedidos", f)
    assert list(novo["parciais"]) == ["d1"]
    assert any("parciais em imagem" in a for a in novo["avisos"])
    assert f == ent


def test_ADR0003_csvs_acima_do_teto_saem_com_aviso_nos_dois_formatos():
    grande = [dict(_csv(i), conteudo="a" * 400_000) for i in (1, 2)]      # > 200 KB cada
    f = {"avisos": [], "csvs_protheus": grande}
    novo = ba._cortar_farol_web("pv_pedidos", f)
    assert "csvs_protheus" not in novo
    assert any("CSVs do Protheus" in a for a in novo["avisos"])
    out = ba._cortar_pacote_web({"relatorios": {"pv_pedidos": f}})["relatorios"]["pv_pedidos"]
    assert "csvs_protheus" not in out                                      # formato 1, pacote pequeno
    assert any("CSVs do Protheus" in a for a in out["avisos"])
    soma = [dict(_csv(i), conteudo="a" * 190_000) for i in range(1, 10)]   # soma > 1,5 MB
    assert "csvs_protheus" not in ba._cortar_farol_web("pv_pedidos", {"avisos": [], "csvs_protheus": soma})
    ok = {"avisos": [], "csvs_protheus": [_csv(1)]}
    assert ba._cortar_farol_web("pv_pedidos", ok) is ok


def test_ADR0003_parcial_grande_no_formato_1_sai_so_o_anexo():
    f = {"avisos": [], "parciais": {"hoje": {"rotulo": "h", "png": "x" * (ba.MAX_PNG_B64 + 1)}},
         "tabelas": [{"titulo": "Cliente a cliente", "colunas": [], "linhas": [], "tons": []}]}
    out = ba._cortar_pacote_web({"relatorios": {"vc_visitas": f}})["relatorios"]["vc_visitas"]
    assert "parciais" not in out and out["tabelas"]


def test_ADR0003_entregas_corta_junta_depois_linhas_antes_de_perder_a_aba():
    f = _entregas()
    sem_junta = copy.deepcopy(f)
    sem_junta["tabelas"][0].pop("juntas")

    def tam(x):
        return len(ba._json_farol_web(x))
    # 1) cabe so sem a junta
    out = ba._cortar_farol_web("pl_entregas", f, teto_mb=(tam(sem_junta) + 400) / MB)
    t = out["tabelas"][0]
    assert "juntas" not in t and len(t["linhas"]) == 400
    assert any("junta de pendências" in a for a in out["avisos"])
    # 2) cabe com 3/4 das linhas: ficam as mais recentes, `tons` junto
    alvo = copy.deepcopy(sem_junta)
    alvo["tabelas"][0]["linhas"] = alvo["tabelas"][0]["linhas"][:300]
    alvo["tabelas"][0]["tons"] = alvo["tabelas"][0]["tons"][:300]
    out = ba._cortar_farol_web("pl_entregas", f, teto_mb=(tam(alvo) + 900) / MB)
    t = out["tabelas"][0]
    assert 0 < len(t["linhas"]) <= 300 and len(t["tons"]) == len(t["linhas"])
    datas = sorted(ln[0] for ln in f["tabelas"][0]["linhas"])
    assert min(ln[0] for ln in t["linhas"]) >= datas[len(datas) - len(t["linhas"]) - 1]
    assert any("entregas mais recentes" in a for a in out["avisos"])
    # 3) nada cabe: a aba sai (10.1), com o aviso de abas fora
    out = ba._cortar_farol_web("pl_entregas", f, teto_mb=0.0001)
    assert "tabelas" not in out and any("Abas fora" in a for a in out["avisos"])
    assert len(f["tabelas"][0]["linhas"]) == 400                # a entrada não mudou


def test_ADR0003_ordem_de_cortes_vem_de_CORTES_FAROL_WEB(monkeypatch):
    monkeypatch.setitem(ba._CORTES_FAROL_WEB, "pl_entregas", ("tabelas",))
    out = ba._cortar_farol_web("pl_entregas", _entregas(), teto_mb=0.0001)
    assert "tabelas" not in out and not any("junta" in a for a in out["avisos"])


def test_ADR0003_entregas_cortado_passa_na_web_alinhado_e_na_ordem_original(monkeypatch):
    """(testes, revisão do 03fb166) O corte das linhas do Entregas tem de manter a tabela válida na
    web: `uf_linhas`, `tons` e `recortes_linhas` alinhados às linhas que ficam, e as linhas na ordem
    original (só saem as mais antigas). A tabela é a fixture fictícia da web (web/tests)."""
    pytest.importorskip("fastapi")
    web = Path(__file__).resolve().parent.parent / "web"
    monkeypatch.syspath_prepend(str(web / "tests"))
    monkeypatch.syspath_prepend(str(web))
    from app import pacotes
    from farol_fixture import farol_entregas_com_abas, tabela_entregas
    f = farol_entregas_com_abas()
    f["tabelas"] = [tabela_entregas(n=400, pend=40)]
    t = f["tabelas"][0]
    nomes = [c["nome"] for c in t["colunas"]]
    i_nf, i_uf, i_ped, i_prazo = (nomes.index(n) for n in ("NF", "UF", "DT. PED", "PRAZO"))
    tons = ("ok", "atencao", "alerta")
    t["tons"] = [tons[k % 3] for k in range(len(t["linhas"]))]
    t["recortes_linhas"] = [{"rotulo": "Atrasadas", "linhas": [k for k, ln in enumerate(t["linhas"])
                                                              if ln[i_prazo] == "ATRASADA"]}]
    assert pacotes.validar_relatorio("pl_entregas", copy.deepcopy(f)) == []     # a fixture vale na web
    entrada = copy.deepcopy(f)
    pos = {ln[i_nf]: k for k, ln in enumerate(t["linhas"])}
    tom_de = {ln[i_nf]: t["tons"][k] for k, ln in enumerate(t["linhas"])}
    sem_junta = copy.deepcopy(f)
    sem_junta["tabelas"][0].pop("juntas")
    teto = len(ba._json_farol_web(sem_junta)) * 0.85 / MB        # sem a junta não basta; 3/4 das linhas cabe
    out = ba._cortar_farol_web("pl_entregas", f, teto_mb=teto)
    assert f == entrada                                                          # a entrada não mudou
    to = out["tabelas"][0]
    assert 0 < len(to["linhas"]) < 400 and ba.AVISO_ENTREGAS_RECENTES in out["avisos"]
    erros = pacotes.validar_relatorio("pl_entregas", copy.deepcopy(out))
    assert erros == [], f"a web recusaria o farol cortado: {erros}"
    ordem = [pos[ln[i_nf]] for ln in to["linhas"]]
    assert ordem == sorted(ordem), "as linhas que ficam saíram da ordem original"
    assert to["uf_linhas"] == [ln[i_uf] for ln in to["linhas"]]
    assert to["tons"] == [tom_de[ln[i_nf]] for ln in to["linhas"]]
    atras = {k for k, ln in enumerate(to["linhas"]) if ln[i_prazo] == "ATRASADA"}
    assert set(to["recortes_linhas"][0]["linhas"]) == atras
    fora = set(pos) - {ln[i_nf] for ln in to["linhas"]}
    ped = {ln[i_nf]: ln[i_ped] for ln in t["linhas"]}
    assert min(ped[ln[i_nf]] for ln in to["linhas"]) >= max(ped[n] for n in fora)   # ficam as mais recentes
