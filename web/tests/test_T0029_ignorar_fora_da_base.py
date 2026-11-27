"""T-0029 / RN-GER-013 (Alexandre, 26/11/2026): no Farol de Pedidos, os pedidos de cliente fora da base (internos)
chegam com o nome CLIENTE FORA DA BASE; a caixa "Ignorar fora da base" vem marcada e tira essas linhas
(e as ligadas a elas nas tabelas de baixo). Desmarcada (fora=1), elas voltam. Dados fictícios."""
from __future__ import annotations

import copy

from conftest import postar
from farol_fixture import pacote_tres_farois

from app import tabelas


def _pacote_com_fora_da_base():
    p = copy.deepcopy(pacote_tres_farois())
    t = p["relatorios"]["pv_pedidos"]["tabelas"][0]
    nomes = [c["nome"] for c in t["colunas"]]
    i = nomes.index("RAZÃO SOCIAL")
    t["linhas"][0][i] = tabelas.NOME_FORA_DA_BASE
    ped = t["linhas"][0][nomes.index("PEDIDO")]
    return p, ped


def test_RN_GER_013_linhas_fora_da_base():
    p, _ = _pacote_com_fora_da_base()
    assert tabelas.linhas_fora_da_base(p["relatorios"]["pv_pedidos"]["tabelas"][0]) == frozenset({0})


def test_RN_GER_013_caixa_ignorar_marcada_por_padrao_e_desmarcar_mostra(admin):
    p, ped = _pacote_com_fora_da_base()
    assert postar(admin, p).status_code == 200
    h = admin.get("/farol/pv_pedidos?aba=pedidos").text
    assert 'class="bc3-chk"' in h and '✓</i>Ignorar fora da base (1)' in h and ": ligado</span>" in h
    assert f">{ped}<" not in h.split('class="bc3-corpo"')[1]
    h = admin.get("/farol/pv_pedidos?aba=pedidos&fora=1").text
    assert ": desligado</span>" in h and "✓</i>Ignorar" not in h and f">{ped}<" in h and tabelas.NOME_FORA_DA_BASE in h


def test_RN_GER_013_nome_antigo_do_pacote_tambem_conta():
    p, _ = _pacote_com_fora_da_base()
    t = p["relatorios"]["pv_pedidos"]["tabelas"][0]
    i = [c["nome"] for c in t["colunas"]].index("RAZÃO SOCIAL")
    t["linhas"][1][i] = "NÃO LOCALIZADO NA BASE"
    assert tabelas.linhas_fora_da_base(t) == frozenset({0, 1})
