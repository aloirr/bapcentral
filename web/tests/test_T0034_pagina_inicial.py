"""T-0034: a página inicial é o Painel Executivo no formato dos faróis (decisão 2 A do Alexandre, 26/11/2026); uma casca só
(barra lateral + faixa) para toda tela logada; Login, Trocar senha, Usuários e Parcial no BC3. Fixture 100% fictícia."""
import re
from pathlib import Path

import pytest
from conftest import postar
from test_abas import _cli_de

from app import render


@pytest.mark.parametrize("perfil,destino", [("admin", "/painel"), ("diretor", "/painel"), ("gerente", "/painel"),
                                            ("pre_venda", "/farol/pv_pedidos"), ("pos_venda", "/farol/pl_entregas"),
                                            ("vendas", "/farol/vc_visitas")])
def test_home_redireciona_cada_perfil_para_a_tela_dele(com_painel, perfil, destino):
    c = com_painel if perfil == "admin" else _cli_de(com_painel, perfil)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == destino
    assert render.pagina_inicial(perfil) == destino


def test_painel_no_bc3_com_faixa_abas_e_cartoes(com_painel):
    for c in (com_painel, _cli_de(com_painel, "diretor")):
        h = c.get("/painel").text
        assert '<body class="bc3">' in h and 'class="bc3-lado"' in h and 'class="bc3-faixa"' in h
        assert h.count("<h1>Painel Executivo") == 1 and "Painel do Diretor" not in h           # RD-0038
        assert 'class="topo"' not in h and "BAP Central web v" not in h and 'class="menu"' not in h  # sem o visual antigo
        assert 'class="bc3-ks"' not in h                                             # T-0052: a faixa da aba RRM não leva números
        for n in ("FATURAMENTO LÍQUIDO · PROJ.", "R$ 165 mil", "POSITIVAÇÃO", "PEDIDOS FATURADOS · PROJ."):
            assert n in h, n                                                         # os títulos e o valor estão nos cartões
        assert h.count("rc-valor") == 3 and h.count("R$ 165 mil") == 1               # U1: o número grande, uma vez só (no cartão)
        assert re.search(r'class="d-pc">\d\d/\d\d/\d{4} \d\d:\d\d', h) and "Dados de" not in re.sub(r'title="[^"]*"', "", h)   # §4.1: só a data; o texto vai no title
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
    assert h.count("Sem dados ainda") == 1 and 'class="bc3-faixa' in h          # RD-0064: um aviso só


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


def test_parcial_sem_repetir_a_lateral(com_painel):
    h = com_painel.get("/farol/pv_pedidos/parcial").text
    assert h.count('class="bc3-lado"') == 1 and "<h1>Parcial · Farol de Pedidos</h1>" in h and h.count("<h1>") == 1
    assert 'class="cab-painel"' not in h
    assert "Voltar ao farol" not in h                                           # RD-0059: a lateral, com "Pedidos" ativo, volta em 1 toque
    assert _cli_de(com_painel, "vendas").get("/farol/pv_pedidos/parcial").status_code == 403


def test_acesso_negado_na_mesma_casca(com_painel):
    r = _cli_de(com_painel, "vendas").get("/painel")
    assert r.status_code == 403 and "Acesso negado" in r.text and 'class="topo"' not in r.text


def test_lateral_marca_usuarios_e_trocar_senha_como_ativos(admin):
    # U5 (contrato §3): o item da lateral da tela aberta fica ativo
    for url, nome in (("/usuarios", "Usuários"), ("/senha", "Trocar senha")):
        lado = admin.get(url).text.split('class="bc3-lado"')[1].split("</aside>")[0]
        assert f'class="on" aria-current="page">{nome}<' in lado and lado.count('aria-current="page"') == 1, url


def test_faixa_dentro_do_main_em_toda_tela_para_ter_a_mesma_margem(com_painel):
    # U4: a faixa não encosta no topo nem na lateral: ela fica dentro do <main class="bc3-corpo"> como nos faróis
    for url in ("/painel", "/usuarios", "/senha", "/farol/pv_pedidos", "/farol/pv_pedidos/parcial"):
        h = com_painel.get(url).text
        assert h.index("<main") < h.index('class="bc3-faixa') < h.index("</main>"), url


def test_usuarios_sem_selo_ativo_em_toda_linha(admin):
    h = admin.get("/usuarios").text
    assert ">Ativo<" not in h and ">Ativos<" in h                               # RD-0068: o normal não leva selo; a faixa conta


def test_nomes_das_abas_do_painel_numa_tabela_so():
    # RD-0038: "Painel Executivo" é o nome da tela; as abas têm nome curto e a chave `visitas` é "Visitas"
    assert not hasattr(render, "TITULOS") and not hasattr(render, "AVISO_SO_BAP")
    assert dict(render.PAINEIS)["visitas"] == "Visitas" and dict(render.PAINEIS)["itens"] == "Itens"
    assert set(render.PAINEL_CURTO) == {"resultado", "produtividade", "por_dia_util"}


def test_regra_cartao_comum_na_faixa_rico_no_corpo_e_uma_so():
    ks = [{"rot": "a"}, {"rot": "b", "estados": [1]}, {"rot": "c", "linhas": [1]}]
    assert [k["rot"] for k in render.kpis_da_faixa(ks)] == ["a"]
    assert [k["rot"] for k in render.kpis_do_corpo(ks)] == ["b", "c"]


def test_dias_uteis_na_faixa_de_todas_as_abas_do_painel(com_painel):
    # U8: "13 de 19 DU" lido do `sub` do PC, ao lado da data, em todas as abas; o resto da nota fica no title
    for aba in ("resultado", "produtividade", "faturamento", "inadimplencia"):
        h = com_painel.get(f"/painel?aba={aba}").text
        faixa = h.split('class="bc3-quando"')[1].split("</span></span>")[0]
        assert " · 13 de 19 DU" in faixa, aba
    assert render.du_do_painel([]) == "" and render.du_do_painel([{"visao": "res", "dados": {"sub": {"res": "sem dias"}}}]) == ""


def test_regra_das_3_abas_no_celular_e_uma_so():
    assert render.abas_no_celular(list("abcde"), "a") == [0, 1, 2] and render.abas_no_celular(list("abcde"), "b") == [0, 1, 2]
    assert render.abas_no_celular(list("abcde"), "d") == [0, 1, 3] and render.abas_no_celular(list("abc"), "x") == [0, 1, 2]


def test_cartoes_alem_dos_3_primeiros_mantem_numero_e_legenda(admin):
    # R1 / T-0052: o PC manda 10 cartões no Resultado; todos mostram o valor no cartão (nenhum vai para a faixa).
    from conftest import _cartao, pacote_ficticio
    p = pacote_ficticio()
    res = p["relatorios"]["vc_painel"]["abas"]["resultado"]["painel"]["blocos"][0]["dados"]["res"]
    res += [_cartao(f"Cartão extra {k}", f"R$ {k},00 extra", f"legenda {k}", [("MÊS", 50.0, "x")]) for k in range(4, 11)]
    assert len(res) == 10 and postar(admin, p).status_code == 200
    h = admin.get("/painel").text
    assert h.count("rc-valor") == 10                                                  # um por cartão
    assert 'class="rc-valor">R$ 4,00 extra<' in h and 'class="rc-valor">R$ 10,00 extra<' in h
    assert '>legenda 4</div>' in h and '>legenda 10</div>' in h
    assert 'class="bc3-ks"' not in h and h.count("R$ 165 mil") == 1                   # o 1º também tem o valor, só no cartão


def test_T0052_todo_cartao_tem_valor_legenda_reservada_e_faixa(admin):
    # T-0052: mesma estrutura em todos os cartões; legenda e faixa reservadas mesmo vazias; faixa do topo sem números
    from conftest import _cartao, pacote_ficticio
    p = pacote_ficticio()
    res = p["relatorios"]["vc_painel"]["abas"]["resultado"]["painel"]["blocos"][0]["dados"]["res"]
    res.append(_cartao("Sem faixa", "R$ 7,00", "", faixa=[]))
    assert postar(admin, p).status_code == 200
    h = admin.get("/painel").text
    cartoes = re.findall(r"<article class=\"rc\">.*?</article>", h, re.S)
    assert len(cartoes) == 4
    for a in cartoes:
        assert 'class="rc-valor"' in a and 'class="rc-leg"' in a
    assert [('class="rc-faixa vazia"' in a) for a in cartoes] == [False, False, False, True]
    assert all(('class="rc-faixa"' in a) or ('rc-faixa vazia' in a) for a in cartoes)
    for v in ("R$ 165 mil", "R$ 7,00"):
        assert h.count(v) == 1                                                        # o valor aparece uma vez só
    assert 'class="bc3-ks"' not in h
    assert render.faixa_painel({"cartoes": [{"titulo": "X", "valor": "1", "legenda": "", "aneis": []}]}, None) == []


def test_perfis_do_painel_numa_constante_so():
    # T-0036 (P1 = A): o analista também vê o Painel, mas abre no 1º farol do grupo dele (UX 8)
    assert render.VEEM_PAINEL == render.LEITURA_GERAL + ("diretor",)
    assert set(render.VEEM_PAINEL) == {"admin", "diretor", "gerente", "analista"}
    assert all(render.pagina_inicial(p) == "/painel" for p in render.VEEM_PAINEL if p != "analista")
    assert render.pagina_inicial("analista") == "/farol/vc_saldo"


def test_troca_obrigatoria_mostra_so_a_casca_sem_menu(cli):
    from conftest import ADMIN, SENHA0, entrar
    assert entrar(cli, ADMIN, SENHA0).status_code == 303
    h = cli.get("/senha").text
    assert "bc3-lado" in h and "bc3-grupo" not in h and ">Sair<" in h


def test_dias_uteis_do_mes_fechado_e_o_css_do_numero_do_cartao():
    # U11: o PC manda "outubro fechado (22 dias úteis)" no 1º dia útil do mês; o DU não pode sumir da faixa
    aba = lambda sub: [{"visao": "res", "dados": {"sub": {"res": sub}}}]
    assert render.du_do_painel(aba("outubro fechado (22 dias úteis)")) == "22 DU · mês fechado"
    assert render.du_do_painel(aba("visão absoluta · novembro até 19/11 (13 de 19 dias úteis)")) == "13 de 19 DU"
    # U10: enquanto o template usar `rc-valor` e `rc-leg`, o CSS tem as duas regras (o número do 4º cartão em diante é o maior)
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    assert ".rc-valor{" in css and "clamp(1.125rem,5.2vw,1.375rem);font-weight:700" in css and ".rc-leg{" in css
    assert "minmax(380px,1fr)" in css                                           # U12: a linha seguinte aparece sem cortar cartão


def test_inter_hospedada_e_ajustes_da_marca(cli):
    # MC-0020: @font-face com a Inter 400, 600 e 700 (woff2 + licença OFL) servida pelo próprio site, com o fallback na pilha
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    for w in (400, 600, 700):
        assert f"font-weight:{w};font-display:swap;src:url(/static/fontes/Inter-{w}.woff2)" in css
        r = cli.get(f"/static/fontes/Inter-{w}.woff2")
        assert r.status_code == 200 and r.content[:4] == b"wOF2" and "immutable" in r.headers["cache-control"]
    assert b"SIL Open Font License" in cli.get("/static/fontes/OFL.txt").content
    assert 'Inter,"Segoe UI",Arial' in css
    # MC-0021, MC-0022, MC-0023, MC-0024
    assert "width:96px;height:122px" in css and "padding:13px" in css
    assert ".rc-barras .barra .rot-b{background:var(--cartao)" in css
    assert "font-weight:800" not in css                                          # manual §5: só 400, 600 e 700
    assert ".selo-cinza{background:var(--borda);color:var(--suave)}" in css


def test_cada_cartao_traz_a_comparacao_do_proprio_indicador(admin):
    # condição do po: a faixa out/set/jul de Positivação e Pedidos não é a do Faturamento (R$ 149/237/626 mil)
    from conftest import pacote_ficticio
    assert postar(admin, pacote_ficticio()).status_code == 200
    h = admin.get("/painel").text
    cartoes = h.split('<article class="rc">')[1:]
    assert len(cartoes) == 3
    fat, pos, ped = cartoes
    assert "R$ 626 mil" in fat and "R$ 626 mil" not in pos and "R$ 626 mil" not in ped
    assert ">126<" in pos and ">168<" in ped and "R$" not in pos.split('class="rc-faixa"')[1].split("</div></div>")[0]


def test_lateral_com_lista_que_rola_e_pe_sempre_visivel(admin):
    # a lista de itens fica numa <nav> que rola por dentro; "usuário · Sair" fica fora dela, no pé da lateral
    lado = admin.get("/senha").text.split('class="bc3-lado"')[1].split("</aside>")[0]
    assert lado.index('class="bc3-nav"') < lado.index("</nav>") < lado.index('class="bc3-eu"')
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    assert ".bc3-nav{flex:1 1 auto;min-height:0;overflow-y:auto" in css and ".rc-faixa b{font-weight:700;white-space:nowrap}" in css


def test_T0052_css_do_celular_desfaz_as_reservas_e_o_valor_tem_teto_de_22px():
    # T-0052: até 600 px não há linha para alinhar (faixa vazia some, legenda e topo sem altura fixa); o valor nunca passa de 22 px
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    cel = css.split("@media(max-width:600px){")[1]
    assert ".rc-faixa.vazia{display:none}" in cel and ".rc-leg:empty{display:none}" in cel
    assert ".rrm:not(.rrm-recorte) .rc-topo{height:auto}" in cel
    assert "clamp(1.125rem,5.2vw,1.375rem)" in css
