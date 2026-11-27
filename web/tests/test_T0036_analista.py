"""T-0036 (contrato §10.11, desenho T-0036): faróis do Analista Comercial e perfis `analista` e `trade`.

Dados 100% fictícios. Cada teste cita a RN: RN-GER-017 (perfis analista e trade, a matriz do §2 do desenho, com a
P1 = A: o analista vê os outros faróis como o gerente) e RN-GER-014 (nos faróis novos, o diretor vê só o Resumo).
"""
import io
import re
import zipfile
from copy import deepcopy

import pytest
from analista_fixture import RIDS_NOVOS, correcao, pacote_analista, pacote_coerente, tabela
from conftest import postar, token_form
from farol_fixture import pacote_tres_farois
from test_farois import _usuario

from app import VERSAO, cobranca, edicoes, exportar, pacotes, render, tabelas, usuarios

TODOS = ("admin", "gerente", "analista", "diretor", "trade", "pre_venda", "vendas", "pos_venda")
VE_NOVOS = {"admin": "T", "gerente": "T", "analista": "T", "diretor": "R", "trade": "-", "pre_venda": "-",
            "vendas": "-", "pos_venda": "-"}
PROIBIDAS = ("CLIENTE", "RAZÃO SOCIAL", "NOME FANTASIA", "ENDEREÇO", "BAIRRO", "Nº", "CONTATO (TELEFONE)")
CORRECAO = "/farol/an_divergencias/correcao.xlsx"


@pytest.fixture
def usu(admin):
    cache = {"admin": admin}

    def _de(perfil):
        if perfil not in cache:
            cache[perfil] = _usuario(admin, "t36." + perfil.replace("_", ""), perfil)
        return cache[perfil]
    return _de


@pytest.fixture
def com_analista(admin):
    assert postar(admin, pacote_analista()).status_code == 200
    return admin


def _erros(pacote):
    return pacotes.validar_relatorio(next(iter(pacote["relatorios"])), pacote["relatorios"][next(iter(pacote["relatorios"]))])


def _recusa(cli, pacote):
    r = postar(cli, pacote)
    assert r.status_code == 422, r.text
    return r


# ------------------------------------------------------------------ perfis e menu
def test_RN_GER_017_perfis_analista_e_trade():
    assert "analista" in usuarios.PERFIS and "trade" in usuarios.PERFIS
    assert len(usuarios.PERFIS) == 8


def test_RN_GER_017_leitura_geral_e_fonte_unica():
    # P1 = A: o analista entra pela constante, em todos os faróis e tabelas
    assert render.LEITURA_GERAL == ("admin", "gerente", "analista")
    for rid, (_, perfis) in render.FAROIS.items():
        assert "analista" in perfis, rid
        assert "trade" not in perfis, rid
    for rid, perfis in tabelas.VE_TABELAS.items():
        assert set(render.LEITURA_GERAL) <= set(perfis) and "diretor" not in perfis, rid
    assert "analista" in cobranca.VE_TABELAS and "analista" not in cobranca.COBRA


def test_RN_GER_017_menu_do_analista_tem_o_grupo_analista_comercial():
    no_pacote = {rid: {} for rid in render.FAROIS}
    grupos = render.menu_lateral("analista", no_pacote, None, painel=True)
    nomes = [g["nome"] for g in grupos]
    assert nomes[0] == "Diretoria" and "Analista Comercial" in nomes and nomes[-1] == "Conta"
    ana = next(g for g in grupos if g["nome"] == "Analista Comercial")
    assert [i["nome"] for i in ana["itens"]] == ["Saldo", "Markup", "Preço", "Divergências"]    # lateral curta (UX 7)
    assert render.FAROIS["an_divergencias"][0] == "Divergências de clientes Planner × Protheus"
    assert [i["href"] for i in ana["itens"]] == [f"/farol/{r}" for r in RIDS_NOVOS]
    # o grupo só aparece para quem tem farol dele
    for p in ("trade", "pre_venda", "vendas", "pos_venda"):
        assert "Analista Comercial" not in [g["nome"] for g in render.menu_lateral(p, no_pacote, None)]
    assert "Analista Comercial" in [g["nome"] for g in render.menu_lateral("diretor", no_pacote, None)]
    # o grupo "Trade" (contrato §10.10.1) existe e fica vazio até o Farol de Expositores entrar (T-0025 v2)
    assert ("Trade", ("tm_expositores",)) in render.GRUPOS_MENU
    assert "Trade" not in [g["nome"] for g in render.menu_lateral("trade", no_pacote, None)]


def test_T0036_grupo_do_proprio_perfil_vem_primeiro():
    no_pacote = {rid: {} for rid in render.FAROIS}
    assert [g["nome"] for g in render.menu_lateral("analista", no_pacote, None)][0] == "Analista Comercial"
    assert render.grupos_na_ordem("trade")[0][0] == "Trade"
    for p in ("diretor", "gerente", "admin", "vendas"):                 # os outros perfis: a ordem de sempre
        assert render.grupos_na_ordem(p) == render.GRUPOS_MENU
    nomes = [g["nome"] for g in render.menu_lateral("diretor", no_pacote, None)]
    assert nomes.index("Vendas") < nomes.index("Analista Comercial")


def test_T0036_pacote_da_simulacao_passa_no_contrato_e_fecha_as_contas():
    p = pacote_coerente()
    for rid, f in p["relatorios"].items():
        assert tabelas.validar(rid, f) == [], rid
    t = {x["titulo"]: x for x in p["relatorios"]["vc_saldo"]["tabelas"]}["Pedido a pedido"]
    n = [c["nome"] for c in t["colunas"]]
    for ln in t["linhas"]:                                   # desconto = tabela − venda (a faixa soma isso)
        assert abs(ln[n.index("VLR TABELA")] - ln[n.index("VLR VENDA")] - ln[n.index("DESC. COMERCIAL")]) < 0.02


def test_RN_GER_017_pagina_inicial_do_trade_sem_farol(admin, usu):
    r = usu("trade").get("/")
    assert r.status_code == 200 and "Os faróis do Trade Marketing ainda não estão no site." in r.text
    assert "bc3-lado" in r.text and "BAP AUTOPARTS" in r.text            # casca BC3 com a marca (UX 9, 5)
    assert "/farol/" not in r.text and "/painel" not in r.text and "/senha" in r.text
    assert "Dados de" not in r.text and "v0.5" not in r.text and "aviso atencao" not in r.text


def test_RN_GER_017_inicio_do_analista_abre_no_farol_de_saldo(admin, usu):
    r = usu("analista").get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/farol/vc_saldo"
    assert usu("gerente").get("/", follow_redirects=False).status_code == 200


def test_RN_GER_017_analista_abre_o_painel_como_o_gerente(usu):
    for p in ("analista", "gerente", "diretor"):
        assert usu(p).get("/painel").status_code == 200
    assert usu("trade").get("/painel").status_code == 403


# ------------------------------------------------------------------ matriz perfil x farol x aba
def test_RN_GER_017_matriz_de_perfis_nos_quatro_farois(com_analista, usu):
    for perfil in TODOS:
        c = usu(perfil)
        for rid in RIDS_NOVOS:
            resumo = 200 if VE_NOVOS[perfil] in ("T", "R") else 403
            assert c.get(f"/farol/{rid}").status_code == resumo, (perfil, rid)
            for chave, _ in tabelas.ABAS[rid]:
                esperado = 200 if VE_NOVOS[perfil] == "T" else 403
                assert c.get(f"/farol/{rid}?aba={chave}").status_code == esperado, (perfil, rid, chave)


def test_RN_GER_014_diretor_so_resumo_nos_farois_do_analista(com_analista, usu):
    c = usu("diretor")
    for rid in RIDS_NOVOS:
        assert c.get(f"/farol/{rid}").status_code == 200, rid
        for chave, _ in tabelas.ABAS[rid]:
            assert c.get(f"/farol/{rid}?aba={chave}").status_code == 403, (rid, chave)


def test_RN_GER_017_analista_ve_os_outros_farois_como_o_gerente(admin, usu):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    for rid in ("pv_pedidos", "pl_entregas", "vc_visitas"):
        for perfil in ("analista", "gerente"):
            assert usu(perfil).get(f"/farol/{rid}").status_code == 200
            assert usu(perfil).get(f"/farol/{rid}?aba={tabelas.ABAS[rid][0][0]}").status_code == 200
        assert usu("trade").get(f"/farol/{rid}").status_code == 403


def test_RN_POS_004_analista_ve_tabelas_da_inadimplencia_sem_cobrar(admin, usu):
    from farol_fixture import farol_inadimplencia, pacote_farol
    assert postar(admin, pacote_farol(pl_inadimplencia=farol_inadimplencia())).status_code == 200
    c = usu("analista")
    assert c.get("/farol/pl_inadimplencia").status_code == 200
    assert c.get("/farol/pl_inadimplencia?aba=cobrar").status_code == 403       # o analista não cobra
    r = c.post("/farol/pl_inadimplencia/cobranca", data={"csrf": token_form(c, "/senha"), "acao": "PULADO",
                                                          "cliente": "900001"})
    assert r.status_code == 403


def test_RN_GER_012_analista_sem_edicao_e_sem_usuarios(admin, usu):
    assert "analista" not in edicoes.EDITA and "trade" not in edicoes.EDITA and edicoes.EDITA == ("admin",)
    for p in ("analista", "gerente", "trade"):
        assert usu(p).get("/usuarios").status_code == 403


def test_RN_GER_001_meta_rh_fora_do_analista_e_do_trade(admin, usu):
    # a web não tem rota de meta RH (Acomp. RH / Exportar para o RH ficam no PC); nada novo abre isso
    rotas = " ".join(getattr(r, "path", "") for r in admin.app.routes).lower()
    assert "rh" not in re.findall(r"[a-z]+", rotas) and "acomp" not in rotas
    for p in ("analista", "trade", "diretor"):
        for url in ("/farol/vc_meta/exportar_rh", "/rh", "/acomp-rh"):
            assert usu(p).get(url).status_code in (403, 404)


# ------------------------------------------------------------------ colunas: lista positiva (§10.11.3)
def test_RN_GER_011_pacote_do_analista_aceito_e_sem_coluna_de_nome(cli, amb):
    assert postar(cli, pacote_analista()).status_code == 200
    from conftest import guardado
    g = guardado(amb)["relatorios"]
    assert set(RIDS_NOVOS) <= set(g)
    for rid in RIDS_NOVOS:
        assert [t["titulo"] for t in g[rid]["tabelas"]] == [t for _, t in tabelas.ABAS[rid]]
        for t in g[rid]["tabelas"]:
            nomes = {c["nome"] for c in t["colunas"]}
            assert not nomes & set(PROIBIDAS), (rid, t["titulo"])
    assert "correcao" not in g["an_divergencias"]                 # o anexo sai do dicionário do farol


def test_RN_GER_011_cliente_so_pelo_codigo_nos_quatro_farois():
    for (rid, titulo), cols in tabelas.COLUNAS_RID.items():
        assert not {n for n, _, _ in cols} & set(PROIBIDAS), (rid, titulo)
    cod = [n for n, _, _ in tabelas.COLUNAS_RID[("vc_saldo", "Pedido a pedido")]]
    assert "CÓD." in cod and "CLIENTE" not in cod
    cod = [n for n, _, _ in tabelas.COLUNAS_RID[("vc_markup", "Por pedido")]]
    assert cod[6] == "CÓD." and "CLIENTE" not in cod


@pytest.mark.parametrize("rid,titulo,extra", [
    ("vc_saldo", "Pedido a pedido", "CLIENTE"), ("vc_markup", "Por pedido", "CLIENTE"),
    ("vc_preco", "Pesquisa de mercado", "CLIENTE"), ("an_divergencias", "Clientes divergentes", "CLIENTE"),
    ("an_divergencias", "Sem coordenada / endereço", "ENDEREÇO"),
    ("an_divergencias", "Sem coordenada / endereço", "CONTATO (TELEFONE)"),
])
def test_RN_GER_011_coluna_fora_da_lista_tira_a_aba(cli, rid, titulo, extra):
    p = pacote_analista()
    t = next(x for x in p["relatorios"][rid]["tabelas"] if x["titulo"] == titulo)
    t["colunas"].append({"nome": extra, "tipo": "texto", "largura": 90, "oculta": False})
    for ln in t["linhas"]:
        ln.append("NOME INVENTADO")
    r = _recusa(cli, p)
    assert "NOME INVENTADO" not in r.text and "colunas diferentes" in r.text


def test_RN_GER_011_coluna_trocada_de_lugar_ou_de_tipo_recusa(cli):
    p = pacote_analista()
    t = p["relatorios"]["vc_markup"]["tabelas"][0]
    t["colunas"][6], t["colunas"][7] = t["colunas"][7], t["colunas"][6]
    _recusa(cli, p)
    p = pacote_analista()
    p["relatorios"]["vc_saldo"]["tabelas"][0]["colunas"][7]["tipo"] = "texto"       # VLR TABELA é moeda
    _recusa(cli, p)


def test_RN_GER_011_ponto_com_coordenada_recusa_a_aba(cli):
    p = pacote_analista()
    t = p["relatorios"]["an_divergencias"]["tabelas"][2]
    k = [c["nome"] for c in t["colunas"]].index("PONTO")
    t["linhas"][0][k] = "-3.123456"
    r = _recusa(cli, p)
    assert "-3.123456" not in r.text


def test_RN_GER_005_tabelas_so_nos_rids_conhecidos(cli):
    p = pacote_analista()
    p["relatorios"]["vc_preco"]["tabelas"][0]["titulo"] = "Por categoria x"
    _recusa(cli, p)


def test_T0036_titulos_repetidos_usam_as_colunas_de_cada_farol():
    # "Por vendedor" existe em Visita, Saldo, Markup e Divergências, cada um com as suas colunas
    a = [n for n, _, _ in tabelas.COLUNAS_RID[("vc_saldo", "Por vendedor")]]
    b = [n for n, _, _ in tabelas.COLUNAS_RID[("an_divergencias", "Por vendedor")]]
    assert a != b and tabelas._cols_esperadas("Por vendedor", [], "vc_saldo")[1][0] == "VENDEDOR"
    assert tabelas._cols_esperadas("Por vendedor", [], "vc_visitas") == tabelas.COLUNAS["Por vendedor"]


def test_T0036_abas_na_ordem_do_pc():
    assert [t for _, t in tabelas.ABAS["vc_saldo"]] == ["Pedido a pedido", "Por vendedor", "Por supervisor", "Por UF"]
    assert len(tabelas.ABAS["vc_markup"]) == 11 and tabelas.ABAS["vc_markup"][-1][0] == "todos"
    assert [c for c, _ in tabelas.ABAS["vc_preco"]] == ["categoria", "familia", "total", "reajustes", "pesquisa"]
    assert [c for c, _ in tabelas.ABAS["an_divergencias"]] == ["vendedor", "divergentes", "sem_coordenada"]


# ------------------------------------------------------------------ telas
def test_RN_GER_011_telas_mostram_codigo_e_nunca_o_cabecalho_cliente(com_analista):
    for rid in RIDS_NOVOS:
        for chave, _ in tabelas.ABAS[rid]:
            h = com_analista.get(f"/farol/{rid}?aba={chave}").text
            assert not re.search(r">\s*(CLIENTE|RAZÃO SOCIAL|NOME FANTASIA|ENDEREÇO|BAIRRO)\s*<", h), (rid, chave)
    h = com_analista.get("/farol/vc_saldo?aba=pedido").text
    assert "900001-01" in h


def test_RN_GER_006_estado_pela_coluna_uf_das_linhas(com_analista):
    todo = com_analista.get("/farol/vc_saldo?aba=pedido").text
    h = com_analista.get("/farol/vc_saldo?aba=pedido&uf=PA").text
    assert todo.count("MANAUS") > 0 and h.count("MANAUS") == 0 and h.count("BELEM") > 0


# ------------------------------------------------------------------ Excel de correção (§10.11.4): só admin
def test_RN_GER_017_correcao_so_admin(com_analista, usu):
    for p in ("gerente", "analista", "diretor", "trade", "pre_venda", "vendas", "pos_venda"):
        assert usu(p).get(CORRECAO).status_code == 403, p


def test_T0036_correcao_sem_anexo_da_404(admin):
    assert postar(admin, pacote_analista(com_correcao=False)).status_code == 200
    assert admin.get(CORRECAO).status_code == 404


def test_RN_GER_011_correcao_xlsx_do_admin_sem_nome_de_cliente(com_analista):
    r = com_analista.get(CORRECAO)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.testzip() is None
    wb = z.read("xl/workbook.xml").decode()
    assert "CORRIGIR NO PROTHEUS" in wb and "ANALISAR" in wb
    todo = " ".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
    assert "A1_VEND CORRETO" in todo and "CLIENTE" not in todo.upper()


def test_RN_GER_011_correcao_com_coluna_cliente_recusa(cli):
    p = pacote_analista()
    p["relatorios"]["an_divergencias"]["correcao"]["corrigir"]["colunas"].insert(
        3, {"nome": "CLIENTE", "tipo": "texto"})
    _recusa(cli, p)
    p = pacote_analista()
    p["relatorios"]["vc_saldo"]["correcao"] = correcao()                  # anexo só nas Divergências
    _recusa(cli, p)
    p = pacote_analista()
    p["relatorios"]["an_divergencias"]["correcao"]["analisar"]["linhas"][0][3] = "x" * 600
    _recusa(cli, p)


def test_T0036_correcao_acima_do_teto_recusa(cli, monkeypatch):
    monkeypatch.setattr(pacotes, "MAX_CORRECAO_BYTES", 500)
    _recusa(cli, pacote_analista())
    assert pacotes.MAX_CORRECAO_BYTES == 500 and pacotes.json_compacto(correcao())


def test_T0036_xlsx_correcao_tem_duas_abas_so_texto():
    z = zipfile.ZipFile(io.BytesIO(exportar.xlsx_correcao(correcao())))
    assert len([n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]) == 2


def test_T0036_correcao_herdada_junto_do_farol(admin, amb):
    # o farol que o robô não mandou hoje é herdado com o anexo (§10.8.4)
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from conftest import por_farol
    agora = lambda h: (datetime.now(ZoneInfo("America/Manaus")) - timedelta(hours=h)).replace(microsecond=0).isoformat()  # noqa: E731
    p = pacote_analista()
    p["gerado_em"] = agora(20)
    assert por_farol(admin, p)[0].status_code == 200
    p2 = deepcopy(p)
    p2["gerado_em"] = agora(0)
    r, _ = por_farol(admin, p2, omitir=("an_divergencias",), manter=("an_divergencias",))
    assert r.status_code == 200 and r.json()["herdados"] == ["an_divergencias"]
    assert admin.get(CORRECAO).status_code == 200


# ------------------------------------------------------------------ versão
def test_T0036_versao_nova_no_saude(cli):
    assert VERSAO == "0.5.0" and cli.get("/saude").json()["versao"] == VERSAO


def test_T0036_tabela_fixture_confere_com_a_lista():
    t = tabela("vc_markup", "Por produto", 2)
    assert len(t["colunas"]) == 20 and tabelas._tabela_erro(t, "Por produto", "aba", "vc_markup") is None


# ------------------------------------------------------------------ revisão de UX (T-0036)
def test_RN_GER_011_grade_nos_quatro_farois_sem_rolagem_lateral(com_analista):
    # UX 1: toda tabela de cima tem GRADE (até 10 colunas no PC, 4 no celular) e a dica de rolagem não aparece
    for (rid, titulo), cols in tabelas.COLUNAS_RID.items():
        g = tabelas.GRADE[(rid, titulo)]
        nomes = [n for n, _, o in cols if not o]
        assert len(g["grade"]) <= 10 and len(g["cel"]) == 4 and g["chave"] in g["grade"], (rid, titulo)
        assert set(g["grade"]) <= set(nomes) and set(g["cel"]) - {None} <= set(nomes), (rid, titulo)
    for rid in RIDS_NOVOS:
        for chave, _ in tabelas.ABAS[rid]:
            h = com_analista.get(f"/farol/{rid}?aba={chave}").text
            assert "Role para o lado" not in h and "bc3-lista" in h, (rid, chave)


def test_T0036_abas_curtas_e_dica_da_busca_por_farol(com_analista):
    h = com_analista.get("/farol/vc_markup?aba=pedido").text
    for curto in (">Pedido", ">Cidade<", ">Todos<", ">Produto<"):
        assert curto in h
    assert "Por pedido" not in h
    for rid in RIDS_NOVOS:
        for chave, titulo in tabelas.ABAS[rid]:
            dica = tabelas.DICA_BUSCA[(rid, titulo)]                 # uma dica por (farol, aba); sem DICA_FAROL
            assert f'placeholder="{dica}"' in com_analista.get(f"/farol/{rid}?aba={chave}").text
            assert len(dica) <= 26, dica                              # cabe a 1366 px sem corte
    assert not hasattr(tabelas, "DICA_FAROL")
    assert tabelas.DICA_BUSCA[("vc_saldo", "Pedido a pedido")] == "Buscar pedido, vendedor"


def test_T0036_faixa_com_no_maximo_seis_numeros(com_analista):
    for rid, n7 in (("an_divergencias", 7), ("vc_markup", 7)):
        h = com_analista.get(f"/farol/{rid}?aba={tabelas.ABAS[rid][0][0]}").text
        assert h.count('class="bc3-k ') == 6, rid


def test_T0036_faixa_com_a_data_do_cabecalho_comum(com_analista):
    h = com_analista.get("/farol/vc_saldo").text           # a mesma faixa dos outros faróis (tela-bc3 §4.1, T-0033)
    assert 'class="bc3-quando" title="Dados de 24/11/2026 08:30, horário de Manaus"' in h


def test_T0036_rotulo_da_coluna_sem_nome_do_campo_do_protheus(com_analista):
    h = com_analista.get("/farol/an_divergencias?aba=divergentes").text
    assert "VENDEDOR PROTHEUS" in h and "A1_VEND" not in h
    z = zipfile.ZipFile(io.BytesIO(com_analista.get(CORRECAO).content))
    assert "A1_VEND" in " ".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))


def test_T0036_casca_com_a_marca_bap(com_analista):
    h = com_analista.get("/farol/vc_saldo").text
    assert 'class="bc3-marca"' in h and "BAP AUTOPARTS" in h      # o logo vem do CSS da marca (T-0033)
    assert com_analista.get("/static/logo_bap.png").content[:4] == b"\x89PNG"


def test_T0036_faixa_do_celular_com_rotulo_curto_e_titulo_inteiro_no_title(com_analista):
    h = com_analista.get("/farol/an_divergencias?aba=divergentes").text
    assert '<span class="r-cel">Na base</span>' in h and 'title="Clientes na base (Planner)"' in h
    assert '<span class="r-cel">Divergências Planner × Protheus</span>' in h
    assert tabelas.kpi_curto("Faturamento NOV") == "Fat. NOV" and tabelas.kpi_curto("Markup") == "Markup"
    assert dict(tabelas.ABAS["an_divergencias"])["sem_coordenada"] and \
        tabelas.rotulo_aba("an_divergencias", "Sem coordenada / endereço") == "Sem coord."
    assert tabelas.GRADE[("an_divergencias", "Clientes divergentes")]["cel"] == ("COD", "CIDADE", "SITUAÇÃO", None)


def test_T0036_titulo_da_coluna_sem_a_unidade_do_numero(com_analista):
    h = com_analista.get("/farol/vc_markup?aba=pedido").text
    assert ">VENDA<" in h and ">MARKUP<" in h and "R$ VENDA" not in h and "MARKUP %" not in h
    assert "% DESC. COM." not in com_analista.get("/farol/vc_saldo?aba=pedido").text


def _base_rotulo(r: str) -> list[str]:
    return [w.strip(".") for w in r.upper().replace("/", " ").split() if w.strip(".")]


def _mesma_base(a: str, b: str) -> bool:
    """"DESC. COM." e "DESC. COMERCIAL" têm a mesma base: as palavras de uma abreviam as da outra."""
    a, b = _base_rotulo(a), _base_rotulo(b)
    return len(a) == len(b) and all(x.startswith(y) or y.startswith(x) for x, y in zip(a, b))


def test_T0036_nenhuma_tabela_com_dois_rotulos_de_mesma_base():
    assert _mesma_base("DESC. COM.", "DESC. COMERCIAL") and not _mesma_base("DESC. S/ TABELA", "DESC. COMERCIAL")
    for (rid, titulo), cols in tabelas.COLUNAS_RID.items():
        if rid not in tabelas.RIDS_ANALISTA:
            continue
        tab = {"cols": [{"nome": n, "tipo": tp} for n, tp, _ in cols]}
        tabelas.aplicar_rotulos(tab, rid)
        rs = [c["rot"] for c in tab["cols"]]
        dup = [(a, b) for i, a in enumerate(rs) for b in rs[i + 1:] if _mesma_base(a, b)]
        assert not dup, (rid, titulo, dup)


def test_T0036_saldo_separa_desconto_em_percentual_e_em_reais(com_analista):
    h = com_analista.get("/farol/vc_saldo?aba=pedido").text
    assert ">DESC. S/ TABELA<" in h and ">DESC. COMERCIAL<" in h and ">DESC. COM.<" not in h
    assert tabelas.kpi_curto("Vendedor diferente") == "Vend. dif."


def test_T0036_selo_curto_na_lista_do_celular_e_inteiro_no_detalhe(admin):
    assert postar(admin, pacote_coerente()).status_code == 200
    h = admin.get("/farol/an_divergencias?aba=divergentes").text
    itens = re.findall(r'<details class="bc3-item[^"]*"><summary>(.*?)</summary>\s*<dl>(.*?)</dl>', h, re.S)
    assert itens
    for summ, dl in itens:
        assert "VENDEDOR DIFERENTE" not in summ and "SEM VENDEDOR NO PLANNER" not in summ \
            and "FORA DA BASE DO PLANNER" not in summ
        curto = next(c for c in ("Vend. dif.", "Sem vendedor", "Fora da base") if c in summ)
        inteiro = {v: k for k, v in tabelas.SELO_CURTO.items()}[curto]
        assert inteiro in dl
    assert tabelas.selo_curto("OK") == "OK"


# ------------------------------------------------------------------ revisão 🟢: OBSERVAÇÃO da Pesquisa limpa na web
def _farol_pesquisa(obs):
    from analista_fixture import farol
    f = farol("vc_preco")
    t = next(t for t in f["tabelas"] if t["titulo"] == "Pesquisa de mercado")
    t["linhas"][0][[c["nome"] for c in t["colunas"]].index("OBSERVAÇÃO")] = obs
    return f


def test_RN_GER_011_observacao_da_pesquisa_limpa_na_web():
    assert tabelas.limpar_texto("Ligar (92) 99999-1234, falar com a.b@c.com doc 123.456.789-01 ok") == \
        "Ligar , falar com doc ok"
    far = pacotes.preparar_farol("vc_preco", _farol_pesquisa("Ver 12.345.678/0001-90 e 92 98888-7777"))
    t = next(t for t in far["tabelas"] if t["titulo"] == "Pesquisa de mercado")   # a aba segue (não cai por documento)
    i = [c["nome"] for c in t["colunas"]].index("OBSERVAÇÃO")
    assert t["linhas"][0][i] == "Ver e"
    assert not any(tabelas._RE_LIMPA.search(str(ln[i])) for ln in t["linhas"])


def test_RN_GER_017_perfis_e_listas_numa_fonte_so():
    assert set(cobranca.VE_TABELAS) == {"admin", "pos_venda", "gerente", "analista"}
    assert tabelas.PERFIS_GERENCIA is render.LEITURA_GERAL
    assert tabelas.RIDS_ANALISTA is render.RIDS_ANALISTA
    assert ("Analista Comercial", render.RIDS_ANALISTA) in render.GRUPOS_MENU
    assert tabelas.SELO_CURTO == {"VENDEDOR DIFERENTE": "Vend. dif.", "SEM VENDEDOR NO PLANNER": "Sem vendedor",
                                  "FORA DA BASE DO PLANNER": "Fora da base"}
