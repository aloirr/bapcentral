"""T-0030 (Alexandre, 26/11/2026): visual BC3 — barra lateral com os faróis do perfil, faixa verde com título, data,
estado e números; abas com busca e Exportar; no PC a página do Farol de Pedidos cabe numa tela (bc3.js pagina);
no celular a tabela vira a lista que abre (M3)."""
from __future__ import annotations

from conftest import postar
from farol_fixture import pacote_tres_farois

from app import render


def test_T0030_farol_de_pedidos_no_visual_bc3(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    h = admin.get("/farol/pv_pedidos?aba=pedidos").text
    assert '<body class="bc3">' in h and 'class="bc3-lado"' in h and "/static/bc3.js" in h
    assert 'class="bc3-faixa"' in h and 'class="bc3-ks"' in h and 'class="bc3-uf"' in h
    assert 'class="bc3-abas"' in h and 'class="bc3-busca"' in h and 'class="bc3-exp"' in h
    # o cabeçalho antigo não aparece junto (sem repetição)
    assert 'class="cab-painel"' not in h and 'class="acoes-farol"' not in h and 'class="kpis faixa"' not in h
    # celular: a lista que abre, uma por pedido, com os dados do popup dentro
    assert h.count('<details class="bc3-item') >= 1 and 'class="bc3-sel"' in h
    # as tabelas de baixo recolhíveis, a primeira aberta
    assert '<details class="junta bc3-junta" open>' in h


def test_T0030_menu_lateral_so_com_o_que_o_perfil_ve():
    g = render.menu_lateral("pre_venda", {"pv_pedidos": {}}, "pv_pedidos")
    nomes = [i["nome"] for x in g for i in x["itens"]]
    assert "Pedidos" in nomes and "Visita" not in nomes and "Painel Executivo" not in nomes
    assert any(i["ativo"] for x in g for i in x["itens"] if i["nome"] == "Pedidos")
    g = render.menu_lateral("admin", {}, None, painel=True, admin=True)
    nomes = [i["nome"] for x in g for i in x["itens"]]
    assert "Painel Executivo" in nomes and "Usuários" in nomes
    # farol fora do pacote: aparece sem link (indisponível)
    assert all(not i["href"] for x in g if x["nome"] in dict(render.GRUPOS_MENU) for i in x["itens"]
               if i["nome"] != "Atualizar visitas")       # T-0045: ação (não farol), sempre com link
    assert any(x["nome"] in dict(render.GRUPOS_MENU) for x in g)


def test_T0031_todos_os_farois_no_visual_bc3(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    for rid in ("pl_entregas", "vc_visitas"):
        h = admin.get(f"/farol/{rid}").text
        assert '<body class="bc3">' in h and 'class="topo"' not in h and 'class="bc3-faixa"' in h


def test_T0032_botoes_de_parcial_como_no_pc(admin):
    """T-0032 (Alexandre, 26/11): os botões das parciais (o que a assistente manda no WhatsApp) em Pedidos, Visita e
    Entregas, com o nome do PC, mesmo quando o pacote ainda não trouxe as imagens."""
    assert postar(admin, pacote_tres_farois()).status_code == 200
    for rid, rot in (("pv_pedidos", "Parcial Pedidos"), ("vc_visitas", "Parcial Visitas e Conversão"),
                     ("pl_entregas", "Parcial Entregas")):
        h = admin.get(f"/farol/{rid}").text.replace('<span class="rot-long">', "").replace("</span></a>", "</a>")
        assert f'href="/farol/{rid}/parcial"' in h and rot in h        # até 1500 px o " e Conversão" some (CSS), o nome inteiro segue no HTML
