"""Busca livre nas tabelas dos faróis (pedido do Alexandre, 26/11/2026: "Cadê o filtro por pedido?")."""
from conftest import postar
from farol_fixture import pacote_tres_farois


def test_busca_por_pedido_filtra_a_tabela_e_segue_na_paginacao(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    h = admin.get("/farol/pv_pedidos?aba=pedidos").text
    assert 'name="busca"' in h and "Buscar pedido ou cliente" in h                  # T-0033: o texto do campo no BC3
    h = admin.get("/farol/pv_pedidos?aba=pedidos&busca=900104").text
    corpo = h.split("<main")[1]
    assert "900104" in corpo and ("<span>1 linha</span>" in corpo or "<span>· 1</span>" in corpo)   # T-0030: BC3
    assert "Limpar busca" in corpo and "busca=900104" in corpo          # links de ordenar levam a busca


def test_busca_sem_resultado_e_texto_estranho_nao_quebram(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    r = admin.get("/farol/pv_pedidos?aba=pedidos&busca=%3Cscript%3E" + "x" * 200)
    assert r.status_code == 200 and "<script>x" not in r.text
