"""T-0021: arquivos para importar no Protheus na web (Farol de Pedidos). Dados fictícios."""
from copy import deepcopy

import pytest

from conftest import postar
from csv_fixture import CSVS, pacote_com_csvs
from test_T0021_edicao import _criar, _entrar_como


@pytest.fixture
def com_csv(admin):
    assert postar(admin, pacote_com_csvs()).status_code == 200
    return admin


def test_lista_nas_duas_abas_e_baixa_byte_a_byte(com_csv):
    for url in ("/farol/pv_pedidos?aba=pedidos", "/farol/pv_pedidos?aba=solicitacao"):
        h = com_csv.get(url).text
        assert "Arquivos para importar no Protheus" in h
        for c in CSVS:
            assert f'/farol/pv_pedidos/csv/{c["nome"]}' in h
        assert h.index("261124_002") < h.index("261120_007")      # mais novo primeiro
    for c in CSVS:
        r = com_csv.get(f'/farol/pv_pedidos/csv/{c["nome"]}')
        assert r.status_code == 200
        assert r.content == c["conteudo"].encode("utf-8")         # mesmo separador, CRLF e codificação
        assert r.headers["content-type"].startswith("text/csv")
        assert c["nome"] in r.headers["content-disposition"]


def test_resumo_nao_lista(com_csv):
    assert "Arquivos para importar" not in com_csv.get("/farol/pv_pedidos").text


@pytest.mark.parametrize("perfil,ve", [("gerente", True), ("pre_venda", True), ("diretor", False), ("vendas", False)])
def test_quem_baixa(com_csv, cli, perfil, ve):
    _entrar_como(cli, _criar(com_csv, perfil))
    r = cli.get(f'/farol/pv_pedidos/csv/{CSVS[0]["nome"]}')
    assert (r.status_code == 200) is ve
    if not ve:
        assert r.status_code in (403, 404)


def test_sem_login_nao_baixa(cli):
    assert cli.get(f'/farol/pv_pedidos/csv/{CSVS[0]["nome"]}', follow_redirects=False).status_code in (302, 303, 401, 403)


def test_nome_fora_do_pacote_ou_traversal_404(com_csv):
    for n in ("261124_009_BELEM_BAPReversaLoja.csv", "..%2Fx.csv", "x.csv"):
        assert com_csv.get(f"/farol/pv_pedidos/csv/{n}").status_code in (404, 422)


def test_pacote_sem_csv_nao_mostra(admin):
    from edicao_fixture import pacote_editavel
    assert postar(admin, pacote_editavel()).status_code == 200
    assert "Arquivos para importar" not in admin.get("/farol/pv_pedidos?aba=pedidos").text


def _invalido(admin, mexe):
    p = pacote_com_csvs()
    mexe(p["relatorios"]["pv_pedidos"])
    r = postar(admin, p)
    assert r.status_code == 422, r.text


def test_validacao_do_pacote(admin):
    _invalido(admin, lambda f: f.__setitem__("csvs_protheus", [{"nome": "x.csv", "conteudo": "a"}]))
    _invalido(admin, lambda f: f.__setitem__("csvs_protheus", [{"nome": "../261124_001_B_BAPReversaLoja.csv", "conteudo": "a"}]))
    _invalido(admin, lambda f: f.__setitem__("csvs_protheus", deepcopy(CSVS) + deepcopy(CSVS[:1])))   # nome repetido
    _invalido(admin, lambda f: f.__setitem__("csvs_protheus", [dict(CSVS[0], conteudo="a" * 200_001)]))
    _invalido(admin, lambda f: f.__setitem__("csvs_protheus", "texto"))
    _invalido(admin, lambda f: f.__setitem__("csvs_protheus", [dict(CSVS[0], extra=1)]))


def test_csv_so_em_pedidos(admin):
    p = pacote_com_csvs()
    p["relatorios"]["pl_entregas"]["csvs_protheus"] = deepcopy(CSVS)
    assert postar(admin, p).status_code == 422
