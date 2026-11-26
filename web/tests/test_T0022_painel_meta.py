"""T-0022: Painel Executivo completo (12 abas do PC) e Farol de Metas Equipe na web.

Fixture 100% fictícia (`painel22_fixture`). O número que a web mostra é o que o PC mandou: aqui se confere a
forma, o filtro de estado, os perfis, a regra 8 (meta RH fora) e o dado pessoal. O teste que compara o pacote com
`relatorios_nucleo.montar` (número do Diretor = farol de origem) está em tests/test_T0022_numero_bate.py."""
import re
from copy import deepcopy

import pytest
from conftest import postar
from painel22_fixture import farol_meta, pacote_completo, painel_completo
from test_abas import _cli_de

from app import pacotes, render, tabelas


def _corpo(h):
    return h.split("<main")[1]


@pytest.fixture
def com_painel(admin):
    assert postar(admin, pacote_completo()).status_code == 200
    return admin


def test_pacote_completo_valida_e_robo_antigo_tambem():
    assert pacotes.validar(pacote_completo()) == []
    antigo = pacote_completo()
    del antigo["relatorios"]["vc_painel"]["abas"]["por_dia_util"]
    del antigo["relatorios"]["vc_painel"]["paineis"]
    del antigo["relatorios"]["vc_meta"]
    assert pacotes.validar(antigo) == []                          # robô antigo: só resultado e produtividade


def test_painel_tem_as_12_abas_do_pc_na_ordem(com_painel):
    h = com_painel.get("/painel").text
    nav = re.search(r'<nav class="abas">(.*?)</nav>', h, re.S).group(1)
    assert re.findall(r">([^<]+)</a>", nav) == [
        "Painel · resultado", "Painel · produtividade", "Painel · por dia útil", "Resumo gerencial", "Faturamento", "Volume",
        "Produtividade", "Positivação", "Itens por pedido", "Markup", "Preço", "Inadimplência"]
    assert "FATURAMENTO POR DU" in com_painel.get("/painel?aba=por_dia_util").text


def test_resumo_gerencial_traz_placar_insights_e_grafico(com_painel):
    c = _corpo(com_painel.get("/painel?aba=resumo").text)
    assert c.count('class="pl-c ') == 2 and "No ritmo de hoje o mês fecha abaixo do desafio." in c
    assert "A projeção está 48% abaixo do desafio." in c and "Entrega x resultado" in c
    assert "<h1>Painel Executivo</h1>" in c and "O que o painel diz" in c


def test_faturamento_leva_as_tabelas_de_baixo_do_pc(com_painel):
    c = _corpo(com_painel.get("/painel?aba=faturamento").text)
    assert c.count("graf-tab") == 3 and "Por filial" in c and "Por categoria" in c and "Por segmento" in c
    assert "R$ 160" in c and "55,5%" in c


def test_filtro_de_estado_troca_cartoes_e_graficos_nas_abas_alcancadas(com_painel):
    base = _corpo(com_painel.get("/painel?aba=faturamento").text)
    am = _corpo(com_painel.get("/painel?aba=faturamento&uf=AM").text)
    assert "Estado AM · Faturamento" in am and "Faturamento projetado" not in am and "Por filial" not in am
    assert "R$ 100 mil" in am and "Faturamento projetado" in base
    assert 'class="ativa">AM<' in am


def test_aba_da_bap_inteira_ignora_o_estado_e_avisa(com_painel):
    h = _corpo(com_painel.get("/painel?aba=inadimplencia&uf=AM").text)
    assert render.AVISO_SO_BAP in h and "Carteira por faixa" in h and 'aria-label="Filtro por estado"' not in h
    assert render.AVISO_SO_BAP not in com_painel.get("/painel?aba=inadimplencia").text


def test_coluna_km_por_cliente_vai_mas_coluna_cliente_nao():
    ok = painel_completo()
    assert pacotes._paineis_erros("vc_painel", ok["paineis"]) == []            # KM/CLIENTE é número
    ruim = deepcopy(ok)
    ruim["paineis"]["faturamento"]["painel"]["blocos"][1]["colunas"][0]["nome"] = "CLIENTE"
    assert pacotes._paineis_erros("vc_painel", ruim["paineis"])


def test_painel_recusa_chave_de_edicao_e_aba_desconhecida():
    p = pacote_completo()
    p["relatorios"]["vc_painel"]["paineis"]["faturamento"]["edicao"] = {"x": 1}
    assert pacotes.validar(p)
    p = pacote_completo()
    p["relatorios"]["vc_painel"]["paineis"]["outra"] = p["relatorios"]["vc_painel"]["paineis"]["markup"]
    assert pacotes.validar(p)


def test_perfis_do_painel_e_do_farol_de_metas(com_painel):
    for perfil, painel, meta in (("diretor", 200, 200), ("gerente", 200, 200), ("vendas", 403, 200),
                                 ("pos_venda", 403, 403), ("pre_venda", 403, 403)):
        c = _cli_de(com_painel, perfil)
        assert c.get("/painel").status_code == painel, perfil
        assert c.get("/farol/vc_meta").status_code == meta, perfil
    assert [r for r, _ in render.farois_do_perfil("vendas")] == ["vc_visitas", "vc_meta"]


def test_farol_de_metas_resumo_com_estado(com_painel):
    c = _corpo(com_painel.get("/farol/vc_meta").text)
    assert "R$ 112 mil" in c and "Faturamento líquido · dia a dia" in c and "Faturamento abaixo do desafio comercial." in c
    am = _corpo(com_painel.get("/farol/vc_meta?uf=AM").text)
    assert "R$ 60 mil" in am and "Faturamento AM dia a dia" in am and "AM: faturamento abaixo do desafio." in am
    assert "Resumo e gráficos: BAP inteira" not in am          # o estado traz o painel dele


def test_equipe_tem_grupos_e_as_tres_tabelas_com_as_de_cima_primeiro(com_painel):
    c = _corpo(com_painel.get("/farol/vc_meta?aba=equipe").text)
    assert "FATURAMENTO" in c and 'colspan="3"' in c and "% ATING." in c           # cabeçalho agrupado, nome curto
    assert c.index("Gerente 01") < c.index("Supervisor 01") < c.index("Vendedor 01")   # GERENTE, SUPERVISORES, VENDEDORES
    assert 'class="junta-cima"' in c and c.count("<table") == 3
    assert "selo" in c                                                                 # % ating. com faixa de cor


def test_top30_refaz_o_top_dentro_do_filtro(com_painel):
    t = pacotes._sem_internas(farol_meta())["tabelas"][1]
    tela = tabelas.tabela_para_tela(t, {})
    assert tela["total_linhas"] == 30 and tela["total"] is None
    nomes = [l["cel"][0]["t"] for l in tela["linhas"]]
    esperado = sorted(range(30), key=lambda i: (-(i % 7 * 100), i))                       # os 30 primeiros, da maior meta (PC)
    assert nomes == [f"{i:06d} - LOJA {i}" for i in esperado]
    f = tabelas.tabela_para_tela(t, {"f1": ["AM"]})                            # filtra UF = AM na carteira de 40
    assert f["total_linhas"] == 20 and all(l["cel"][1]["t"] == "AM" for l in f["linhas"])
    assert tabelas.tabela_para_tela(t, {"f1": ["PA"]})["total_linhas"] == 20


def test_estado_traz_as_tabelas_dele(com_painel):
    c = _corpo(com_painel.get("/farol/vc_meta?aba=uf&uf=AM").text)
    assert ">AM</td>" in c and ">PA</td>" not in c
    assert ">PA</td>" in _corpo(com_painel.get("/farol/vc_meta?aba=uf").text)
    h = com_painel.get("/farol/vc_meta?aba=cidade&uf=AM").text                  # a aba que o estado não trouxe: BAP inteira, com aviso
    assert "Sem as tabelas de AM neste pacote" in h


def test_diretor_so_ve_o_resumo_do_farol_de_metas(com_painel):
    d = _cli_de(com_painel, "diretor")
    assert d.get("/farol/vc_meta").status_code == 200
    assert d.get("/farol/vc_meta?aba=top30").status_code == 403
    assert "aba=equipe" not in d.get("/farol/vc_meta").text


def test_regra_8_meta_rh_fora_da_web():
    p = pacote_completo()
    t = deepcopy(p["relatorios"]["vc_meta"]["tabelas"][0])
    t["titulo"] = "Acomp. RH"
    p["relatorios"]["vc_meta"]["tabelas"].insert(1, t)
    assert pacotes.validar(p)                                                   # a aba Acomp. RH (META RH, RV) não é aceita
    assert all("RH" not in n for _, n in tabelas.ABAS["vc_meta"])


def test_cnpj_em_celula_derruba_so_a_aba(admin):
    p = pacote_completo()
    p["relatorios"]["vc_meta"]["tabelas"][3]["linhas"][0][0] = "12.345.678/0001-90"
    p["relatorios"]["vc_meta"]["recortes"]["AM"]["tabelas"][0]["linhas"][0][0] = "12.345.678/0001-90"
    assert postar(admin, p).status_code == 200
    h = admin.get("/farol/vc_meta?aba=cidade").text
    assert "12.345.678" not in h
    assert "12.345.678" not in admin.get("/farol/vc_meta?aba=uf&uf=AM").text
    assert admin.get("/farol/vc_meta?aba=segmento").status_code == 200       # as outras abas seguem


def test_tabela_de_meta_recusa_coluna_de_telefone_e_grupos_tortos():
    p = pacote_completo()
    p["relatorios"]["vc_meta"]["tabelas"][2]["colunas"][0]["nome"] = "TELEFONE"
    assert pacotes.validar(p)
    p = pacote_completo()
    p["relatorios"]["vc_meta"]["tabelas"][2]["grupos"] = [["X", 99]]
    assert pacotes.validar(p)
    p = pacote_completo()
    p["relatorios"]["vc_meta"]["recortes"]["AM"]["tabelas"][0]["editar"] = True
    assert pacotes.validar(p)


def test_home_lista_o_farol_de_metas_para_vendas(com_painel):
    h = _cli_de(com_painel, "vendas").get("/").text
    assert "/farol/vc_meta" in h and "Farol de Metas Equipe" in h
