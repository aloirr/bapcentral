"""T-0024: os 5 faróis do lote 2 (Painel de indicadores, Clientes, Roteirização, Giro, Estoque FRW).
Fixture 100% fictícia: abas livres (colunas do PC), perfil, estado, exportação e recusa de dado pessoal."""
from copy import deepcopy

from conftest import postar
from farol_fixture import _base, _col
from lote2_fixture import pacote_lote2
from test_abas import _cli_de

from app import render, tabelas

RIDS = tabelas.FAROIS_LIVRES


def _farol(nome, titulos):
    """Farol livre pequeno (para testar a derivação das abas pelo título)."""
    f = _base(nome, [{"rotulo": "Itens", "valor": "2", "cor": "ok"}], [])
    f["tabelas"] = [{"titulo": t, "colunas": [_col("FILIAL"), _col("VENDA", "moeda")], "linhas": [["MANAUS", 1.0]],
                     "tons": [""], "total": None, "filtros": []} for t in titulos]
    return f


def _pacote():
    return pacote_lote2()           # abas, colunas e cartões reais de cada farol; só valores fictícios


def test_abas_livres_sairam_das_tabelas_do_pacote():
    rel = _farol("X", ["Resumo por filial", "Base com compra em NOV/26, por segmento"])
    assert tabelas.abas_do_farol("vc_base", rel) == [
        ("resumo-por-filial", "Resumo por filial"),
        ("base-com-compra-em-nov-26-por-segmento", "Base com compra em NOV/26, por segmento")]
    assert tabelas.abas_do_farol("vc_base", None) == []


def test_pacote_aceita_e_perfis_vem_do_quadrado_do_pc(admin):
    assert postar(admin, _pacote()).status_code == 200
    vendas = _cli_de(admin, "vendas")
    assert vendas.get("/farol/vc_base?aba=clientes").status_code == 200
    assert vendas.get("/farol/pl_frw").status_code == 403
    assert _cli_de(admin, "pos_venda").get("/farol/pl_frw?aba=estoque-frw").status_code == 200
    assert _cli_de(admin, "pre_venda").get("/farol/pv_indicadores").status_code == 200
    assert _cli_de(admin, "diretor").get("/farol/pl_giro?aba=todos-os-produtos").status_code == 403


def test_estado_filtra_linhas_e_exporta(admin):
    postar(admin, _pacote())
    h = admin.get("/farol/pl_giro?aba=todos-os-produtos&uf=AM").text
    assert ">FILIAL FICTICIA AM</td>" in h and ">FILIAL FICTICIA PA</td>" not in h
    r = admin.get("/farol/pl_giro/exportar?aba=todos-os-produtos&formato=xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_recusa_coluna_de_telefone_e_cnpj_na_aba_livre(admin):
    p = _pacote()
    p["relatorios"]["vc_base"]["tabelas"][1]["colunas"].append(_col("TELEFONE"))
    for ln in p["relatorios"]["vc_base"]["tabelas"][1]["linhas"]:
        ln.append("")
    assert postar(admin, p).status_code == 422
    p = _pacote()
    p["relatorios"]["vc_base"]["tabelas"][7]["linhas"][0][1] = "12.345.678/0001-95"
    r = postar(admin, p)
    assert r.status_code == 200      # a aba com documento sai, o resto segue (W2)
    assert "aba=clientes" not in admin.get("/farol/vc_base").text


def test_selo_livre_malformado_recusado(admin):
    p = deepcopy(_pacote())
    p["relatorios"]["pl_frw"]["tabelas"][0]["colunas"][2]["chip"] = [[1, "red"]]
    assert postar(admin, p).status_code == 422


def test_lote2_no_formato_por_farol_da_T0035(admin):
    """§10.8: os 5 faróis entram um a um (POST por farol + fechar) e abrem do disco, com perfil e abas."""
    from conftest import por_farol
    r, _ = por_farol(admin, _pacote())
    assert r.status_code == 200, r.text
    for rid in RIDS:
        assert admin.get(f"/farol/{rid}").status_code == 200
    assert admin.get("/farol/vc_base?aba=clientes").status_code == 200
    assert _cli_de(admin, "vendas").get("/farol/pl_frw").status_code == 403
