"""T-0034: a página inicial é o Painel Executivo no formato dos faróis (decisão 2 A do Alexandre, 26/11/2026); uma casca só
(barra lateral + faixa) para toda tela logada; Login, Trocar senha, Usuários e Parcial no BC3. Fixture 100% fictícia."""
import re

import pytest
from conftest import postar
from painel22_fixture import pacote_completo
from test_abas import _cli_de

from app import render


@pytest.fixture
def com_painel(admin):
    assert postar(admin, pacote_completo()).status_code == 200
    return admin


@pytest.mark.parametrize("perfil,destino", [("admin", "/painel"), ("diretor", "/painel"), ("gerente", "/painel"),
                                            ("pre_venda", "/farol/pv_pedidos"), ("pos_venda", "/farol/pl_entregas"),
                                            ("vendas", "/farol/vc_visitas")])
def test_home_redireciona_cada_perfil_para_a_tela_dele(com_painel, perfil, destino):
    c = com_painel if perfil == "admin" else _cli_de(com_painel, perfil)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == destino
    assert render.pagina_inicial(perfil) == destino


def test_home_segue_a_ordem_do_menu_lateral():
    # o primeiro farol da área que o perfil vê, na ordem de GRUPOS_MENU
    for perfil in ("pre_venda", "pos_venda", "vendas"):
        rid = render.pagina_inicial(perfil).rsplit("/", 1)[1]
        assert rid == [r for _, rids in render.GRUPOS_MENU for r in rids if r in dict(render.farois_do_perfil(perfil))][0]


def test_home_sem_login_vai_para_o_login(cli):
    r = cli.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_painel_403_para_quem_nao_e_da_diretoria(com_painel):
    for perfil in ("pre_venda", "pos_venda", "vendas"):
        assert _cli_de(com_painel, perfil).get("/painel").status_code == 403, perfil


def test_painel_no_bc3_com_faixa_abas_e_cartoes(com_painel):
    for c in (com_painel, _cli_de(com_painel, "diretor")):
        h = c.get("/painel").text
        assert '<body class="bc3">' in h and 'class="bc3-lado"' in h and 'class="bc3-faixa"' in h
        assert h.count("<h1>Painel Executivo</h1>") == 1 and "Painel do Diretor" not in h           # RD-0038
        assert 'class="topo"' not in h and "BAP Central web v" not in h and 'class="menu"' not in h  # sem o visual antigo
        faixa = h.split('class="bc3-ks"')[1].split("</header>")[0]
        for n in ("FATURAMENTO LÍQUIDO · PROJ.", "R$ 165 mil", "MTD 11%", "POSITIVAÇÃO", "PEDIDOS FATURADOS · PROJ."):
            assert n in faixa, n
        assert h.count("<article") == 3 and "R$ 87,0 mil" in h                          # os cartões RRM seguem no corpo
        abas = re.search(r'<nav class="bc3-abas"[^>]*>(.*?)</nav>', h, re.S).group(1)
        assert "<summary>Indicadores</summary>" in abas and 'aria-current="page"' in abas
        assert 'aria-current="page"' in h.split('class="bc3-lado"')[1].split("</aside>")[0]   # item ativo da lateral


def test_painel_cartoes_comuns_das_abas_vao_para_a_faixa_e_os_ricos_ficam(com_painel):
    h = com_painel.get("/painel?aba=faturamento").text
    faixa = h.split('class="bc3-ks"')[1].split("</header>")[0]
    assert "Real" in faixa and "R$ 500 mil" in faixa and "Desafio comercial" in faixa and "R$ 1,5 mi" in faixa
    assert "Por filial" in h.split("<main")[1]


def test_painel_sem_pacote_diz_quando_chega(admin):
    h = admin.get("/painel").text
    assert "Sem dados ainda. A primeira atualização chega às 06h30." in h and 'class="bc3-faixa"' in h


def test_telas_sem_usuario_usam_a_mesma_casca_sem_lateral(cli):
    h = cli.get("/login").text
    assert '<body class="bc3 sem-lado">' in h and "bc3-lado" not in h and 'class="topo"' not in h
    assert "<h1>BAP Central" in h and "Entrar</h1>" not in h and ">Entrar</button>" in h
    erro = cli.post("/login", data={"usuario": "x", "senha": "y", "csrf": "z"})
    assert erro.status_code == 400
    r = cli.post("/login", data={"usuario": "ninguem", "senha": "y", "csrf": re.search(r'name="csrf" value="([^"]+)"', h).group(1)})
    assert r.status_code == 401 and 'role="alert"' in r.text


def test_trocar_senha_no_bc3_com_o_texto_no_subtitulo(cli, admin):
    h = admin.get("/senha").text
    assert 'class="bc3-faixa simples"' in h and "<h1>Trocar senha</h1>" in h and h.count("<h1>") == 1


def test_usuarios_um_principal_e_desativar_pede_confirmacao(admin):
    h = admin.get("/usuarios").text
    assert h.count("bc3-bt-verde") == 1 and "Novo usuário" in h                 # um só botão principal na tela
    assert "Ativos" in h and "Desativados" in h and "Troca pendente" in h        # a faixa
    assert "<h1>Usuários</h1>" in h and h.count("<h1>") == 1
    assert "<table" not in h and ">Admin<" in h and ">admin<" not in h           # rótulos do perfil, lista que cabe no celular
    # "Desativar" fica dentro de um <details> de confirmação que diz o verbo e o alvo, e o botão de confirmar repete o verbo
    conf = re.search(r'<details class="u-det u-perigo">(.*?)</details>', h, re.S).group(1)
    assert "Desativar o usuário" in conf and 'value="desativar"' in conf and ">Desativar</button>" in conf
    assert 'value="desativar"' not in h.replace(conf, "")                       # nenhum botão de desativar fora da confirmação


def test_usuarios_selos_de_situacao(admin):
    def acao(**d):
        return admin.post("/usuarios", data={**d, "csrf": re.search(r'name="csrf" value="([^"]+)"', admin.get("/usuarios").text).group(1)})
    acao(acao="criar", login="gerente.um", perfil="gerente", senha="senha-do-gerente-1")
    h = acao(acao="desativar", login="gerente.um").text
    assert "Desativado" in h and 'class="selo selo-cinza"' in h and "Troca de senha pendente" in h
    assert 'value="ativar"' in h


def test_usuarios_403_fora_do_admin(com_painel):
    assert _cli_de(com_painel, "gerente").get("/usuarios").status_code == 403


def test_parcial_sem_repetir_a_lateral(com_painel):
    h = com_painel.get("/farol/pv_pedidos/parcial").text
    assert h.count('class="bc3-lado"') == 1 and "<h1>Parcial · Farol de Pedidos</h1>" in h and h.count("<h1>") == 1
    assert 'class="cab-painel"' not in h
    assert _cli_de(com_painel, "vendas").get("/farol/pv_pedidos/parcial").status_code == 403


def test_acesso_negado_na_mesma_casca(com_painel):
    r = _cli_de(com_painel, "vendas").get("/painel")
    assert r.status_code == 403 and "Acesso negado" in r.text and 'class="topo"' not in r.text
