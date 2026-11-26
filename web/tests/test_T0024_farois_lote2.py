"""T-0024: os 5 faróis do lote 2 (Painel de indicadores, Clientes, Roteirização, Giro, Estoque FRW).
Fixture 100% fictícia: abas livres (colunas do PC), perfil, estado, exportação e recusa de dado pessoal."""
from copy import deepcopy

from conftest import postar
from farol_fixture import _base, _col
from test_abas import _cli_de

from app import render, tabelas

RIDS = tabelas.FAROIS_LIVRES


def _tab(titulo, extra_cols=(), uf=True):
    cols = [_col("FILIAL"), _col("PRODUTO"), _col("VENDA", "moeda")] + [_col(n) for n in extra_cols]
    cols[1]["oculta"] = False
    linhas = [["MANAUS", "P1", 10.5] + [""] * len(extra_cols), ["BELÉM", "P2", 7.0] + [""] * len(extra_cols)]
    t = {"titulo": titulo, "colunas": cols, "linhas": linhas, "tons": ["", ""], "total": None,
         "filtros": [{"coluna": "FILIAL"}]}
    if uf:
        t["uf_linhas"] = ["AM", "PA"]
    return t


def _farol(nome, titulos):
    f = _base(nome, [{"rotulo": "Itens", "valor": "2", "cor": "ok"}], [])
    f["tabelas"] = [_tab(t) for t in titulos]
    f["recortes"] = {"AM": {"kpis": [{"rotulo": "Itens", "valor": "1", "cor": "ok"}]}}
    return f


def _pacote():
    rels = {rid: _farol(render.FAROIS[rid][0], ["Resumo por filial", "Todos os produtos"]) for rid in RIDS}
    return {"versao_contrato": 1, "gerado_em": "2026-11-24T08:30:00-04:00", "ano": 2026, "mes": 11, "relatorios": rels}


def test_abas_livres_sairam_das_tabelas_do_pacote():
    rel = _farol("X", ["Resumo por filial", "Base com compra em NOV/26, por segmento"])
    assert tabelas.abas_do_farol("vc_base", rel) == [
        ("resumo-por-filial", "Resumo por filial"),
        ("base-com-compra-em-nov-26-por-segmento", "Base com compra em NOV/26, por segmento")]
    assert tabelas.abas_do_farol("vc_base", None) == []


def test_pacote_aceita_e_perfis_vem_do_quadrado_do_pc(admin):
    assert postar(admin, _pacote()).status_code == 200
    vendas = _cli_de(admin, "vendas")
    assert vendas.get("/farol/vc_base?aba=todos-os-produtos").status_code == 200
    assert vendas.get("/farol/pl_frw").status_code == 403
    assert _cli_de(admin, "pos_venda").get("/farol/pl_frw?aba=todos-os-produtos").status_code == 200
    assert _cli_de(admin, "pre_venda").get("/farol/pv_indicadores").status_code == 200
    assert _cli_de(admin, "diretor").get("/farol/pl_giro?aba=todos-os-produtos").status_code == 403


def test_estado_filtra_linhas_e_exporta(admin):
    postar(admin, _pacote())
    h = admin.get("/farol/pl_giro?aba=todos-os-produtos&uf=AM").text
    assert ">MANAUS</td>" in h and ">BELÉM</td>" not in h
    r = admin.get("/farol/pl_giro/exportar?aba=todos-os-produtos&formato=xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_recusa_coluna_de_telefone_e_cnpj_na_aba_livre(admin):
    p = _pacote()
    p["relatorios"]["vc_base"]["tabelas"][1]["colunas"].append(_col("TELEFONE"))
    for ln in p["relatorios"]["vc_base"]["tabelas"][1]["linhas"]:
        ln.append("")
    assert postar(admin, p).status_code == 422
    p = _pacote()
    p["relatorios"]["vc_base"]["tabelas"][1]["linhas"][0][1] = "12.345.678/0001-95"
    r = postar(admin, p)
    assert r.status_code == 200      # a aba com documento sai, o resto segue (W2)
    assert "aba=todos-os-produtos" not in admin.get("/farol/vc_base").text


def test_selo_livre_malformado_recusado(admin):
    p = deepcopy(_pacote())
    p["relatorios"]["pl_frw"]["tabelas"][0]["colunas"][2]["chip"] = [[1, "red"]]
    assert postar(admin, p).status_code == 422
