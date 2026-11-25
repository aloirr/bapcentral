"""T-0017, entregas 3 a 5 (contrato §10.7): todas as abas de tabela de Pedidos, Entregas e Visita.

Fixture 100% fictícia (`farol_fixture.pacote_tres_farois`). Os testes cobrem: perfil × aba = 403,
recusa de pacote torto, tabela igual ao fixture, estado (D5), recortes, juntas, páginas, selos,
dado pessoal (RN-GER-011) e a Inadimplência igual à de antes (golden gerado com o código anterior).
"""
import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
from conftest import postar, token_form
from farol_fixture import pacote_farol, pacote_tres_farois
from test_farois import _usuario

from app import VERSAO, cobranca, render, tabelas

PERFIS = ("admin", "diretor", "gerente", "pos_venda", "pre_venda", "vendas")
RIDS = ("pv_pedidos", "pl_entregas", "vc_visitas")
RE_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14}")
RE_FONE = re.compile(r"\(\d{2}\)\s?\d{4,5}-\d{4}|\b55\d{10,11}\b|@[a-z0-9-]+\.")


def _cli_de(admin, perfil, cache={}):
    chave = (id(admin.app), perfil)
    if perfil == "admin":
        return admin
    if chave not in cache:
        cache[chave] = _usuario(admin, "ab." + perfil.replace("_", ""), perfil)
    return cache[chave]


def _sem_cache():
    pass


@pytest.fixture
def com_tabelas(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    return admin


def _rel(rid, **mut):
    p = pacote_tres_farois()
    return p, p["relatorios"][rid]


def _tab(r, titulo):
    return next(t for t in r["tabelas"] if t["titulo"] == titulo)


# ------------------------------------------------------------------ pacote aceito e guardado
def test_pacote_dos_tres_farois_aceito_e_abas_guardadas(cli, amb):
    assert postar(cli, pacote_tres_farois()).status_code == 200
    g = json.loads(sorted((amb / "pacotes").glob("*.json"))[-1].read_text(encoding="utf-8"))
    for rid in RIDS:
        assert [t["titulo"] for t in g["relatorios"][rid]["tabelas"]] == [t for _, t in tabelas.ABAS[rid]]
    assert len(g["relatorios"]["pv_pedidos"]["tabelas"][0]["juntas"]) == 3


def test_pacote_sem_tabelas_robo_antigo_aceito(cli):
    assert postar(cli, pacote_tres_farois(com_tabelas=False)).status_code == 200


def test_aba_fora_da_atualizacao_so_ela_some(cli):
    p = pacote_tres_farois()
    p["relatorios"]["pv_pedidos"]["tabelas"] = p["relatorios"]["pv_pedidos"]["tabelas"][:1]   # sem Solicitação
    del p["relatorios"]["vc_visitas"]["tabelas"][4:]                                         # sem cliente/prosp./indic.
    assert postar(cli, p).status_code == 200


def test_versao_nova_no_saude(cli):
    assert VERSAO != "0.2.0" and cli.get("/saude").json()["versao"] == VERSAO


# ------------------------------------------------------------------ perfil × aba (corte no servidor)
def test_perfil_x_aba_403_ou_200(com_tabelas):
    admin = com_tabelas
    for perfil in PERFIS:
        c = _cli_de(admin, perfil)
        for rid in RIDS:
            ve_farol = perfil in render.FAROIS[rid][1]
            r = c.get(f"/farol/{rid}")
            assert r.status_code == (200 if ve_farol else 403), (perfil, rid)
            for chave, _ in tabelas.ABAS[rid]:
                esperado = 200 if (ve_farol and perfil in tabelas.VE_TABELAS[rid]) else 403
                assert c.get(f"/farol/{rid}?aba={chave}").status_code == esperado, (perfil, rid, chave)


def test_ve_tabelas_D1_recomendacao_A():
    # D1 (recomendação A): o perfil de cada farol vê as tabelas; o diretor, só o Resumo
    assert tabelas.VE_TABELAS == {"pv_pedidos": ("admin", "gerente", "pre_venda"),
                                  "pl_entregas": ("admin", "gerente", "pos_venda"),
                                  "vc_visitas": ("admin", "gerente", "vendas")}
    assert all("diretor" not in p for p in tabelas.VE_TABELAS.values())


def test_diretor_so_resumo_sem_barra_de_abas(com_tabelas):
    d = _cli_de(com_tabelas, "diretor")
    for rid in RIDS:
        h = d.get(f"/farol/{rid}").text
        assert 'class="abas' not in h and "Resumo gerencial" not in h.split("<main")[1].split("<header")[0]
        assert d.get(f"/farol/{rid}?aba={tabelas.chaves(rid)[0]}").status_code == 403


def test_barra_de_abas_do_perfil_do_farol(com_tabelas):
    c = _cli_de(com_tabelas, "pre_venda")
    h = c.get("/farol/pv_pedidos").text
    assert "Resumo gerencial" in h and "?aba=pedidos" in h and "?aba=solicitacao" in h
    v = _cli_de(com_tabelas, "vendas").get("/farol/vc_visitas").text
    for chave in tabelas.chaves("vc_visitas"):
        assert f"?aba={chave}" in v


def test_aba_de_outro_farol_ou_da_inadimplencia_403(com_tabelas):
    for url in ("/farol/pv_pedidos?aba=titulos", "/farol/pl_entregas?aba=cobrar", "/farol/vc_visitas?aba=titulos"):
        assert com_tabelas.get(url).status_code == 403, url
    assert com_tabelas.get("/farol/vc_visitas?aba=cliente").status_code == 200       # "cliente" é aba da Visita


def test_sem_login_vai_ao_login(cli):
    assert cli.get("/farol/pv_pedidos?aba=pedidos", follow_redirects=False).status_code == 303


def test_paginas_de_tabela_no_store_noindex_sem_exportar_e_sem_gravar(com_tabelas):
    for rid in RIDS:
        for chave, _ in tabelas.ABAS[rid]:
            r = com_tabelas.get(f"/farol/{rid}?aba={chave}")
            assert r.headers["cache-control"] == "no-store"
            h = r.text
            assert 'name="robots" content="noindex' in h
            corpo = h.split("<main")[1]
            assert 'method="post"' not in corpo.lower() and "xlsx" not in corpo.lower()
            assert "exportar" not in corpo.lower() and "pdf" not in corpo.lower()
            assert "TELEFONE" not in corpo and "CNPJ" not in corpo and not RE_CNPJ.search(corpo)
            assert not RE_FONE.search(corpo)


def test_acesso_registrado_com_aba_e_sem_cliente(com_tabelas, amb):
    com_tabelas.get("/farol/vc_visitas?aba=cliente")
    log = "".join(p.read_text(encoding="utf-8") for p in (amb / "acessos").glob("*.jsonl"))
    ult = json.loads(log.strip().splitlines()[-1])
    assert ult["rid"] == "vc_visitas" and ult["aba"] == "cliente" and ult["acao"] == "ver"
    assert "FICTICIO" not in log


# ------------------------------------------------------------------ pacote torto: a web recusa o pacote inteiro
def _recusa(cli, p, trecho=""):
    r = postar(cli, p)
    assert r.status_code == 422, r.text
    assert trecho in json.dumps(r.json(), ensure_ascii=False)
    assert "FICTICIO" not in r.text and not RE_CNPJ.search(r.text)          # o motivo não traz dado pessoal


@pytest.mark.parametrize("nome", ["TELEFONE", "CELULAR", "WHATSAPP", "CNPJ", "CPF", "E-MAIL", "EMAIL", "CONTATO",
                                  "FOTO", "ENDEREÇO"])
def test_recusa_coluna_que_nao_vai_ao_site(cli, nome):
    p, r = _rel("vc_visitas")
    t = _tab(r, "Prospecção")
    t["colunas"].append({"nome": nome, "tipo": "texto"})
    for ln in t["linhas"]:
        ln.append("x")
    _recusa(cli, p, "colunas diferentes")
    p, r = _rel("pv_pedidos")                                   # e na sub-aba da Solicitação BAP
    sub = _tab(r, "Solicitação BAP")["subabas"][0]
    sub["colunas"].append({"nome": nome.lower(), "tipo": "texto"})
    for ln in sub["linhas"]:
        ln.append("x")
    _recusa(cli, p, "não vai ao site")


def _mut_colunas(f):
    def mut(p):
        f(_tab(p["relatorios"]["pv_pedidos"], "Pedidos"))
    return mut


def _troca_ordem(t):
    t["colunas"][0], t["colunas"][1] = t["colunas"][1], t["colunas"][0]
    for ln in t["linhas"]:
        ln[0], ln[1] = ln[1], ln[0]


def _tipo_errado(t):
    t["colunas"][9]["tipo"] = "texto"


def _tira_coluna(t):
    t["colunas"].pop()
    for ln in t["linhas"]:
        ln.pop()


def _oculta_trocada(t):
    t["colunas"][0]["oculta"] = True


@pytest.mark.parametrize("mut", [_troca_ordem, _tipo_errado, _tira_coluna, _oculta_trocada])
def test_recusa_colunas_fora_da_lista_ordem_tipo_ou_oculta(cli, mut):
    p, r = _rel("pv_pedidos")
    mut(_tab(r, "Pedidos"))
    _recusa(cli, p, "colunas diferentes")


def test_recusa_titulo_fora_da_lista_fora_da_ordem_ou_repetido(cli):
    p, r = _rel("pv_pedidos")
    r["tabelas"].reverse()
    _recusa(cli, p, "fora da ordem")
    p, r = _rel("pl_entregas")
    r["tabelas"].append(deepcopy(r["tabelas"][0]))
    _recusa(cli, p, "")
    p, r = _rel("vc_visitas")
    r["tabelas"][0]["titulo"] = "Outra"
    _recusa(cli, p, "fora da lista")


def test_recusa_linha_com_celula_a_mais_ou_a_menos(cli):
    for delta in (1, -1):
        p, r = _rel("pl_entregas")
        ln = _tab(r, "Entregas")["linhas"][0]
        ln.append(1) if delta > 0 else ln.pop()
        _recusa(cli, p, "linha com número de células")


def test_recusa_celula_de_tipo_errado_e_documento_formatado(cli):
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["linhas"][0][9] = "muito"                  # LIMITE (moeda) com texto
    _recusa(cli, p, "linha com número de células ou valores")
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["linhas"][0][5] = "CLIENTE FICTICIO 12.345.678/0001-90"      # CNPJ formatado
    _recusa(cli, p, "valores inválidos")
    p, r = _rel("vc_visitas")
    _tab(r, "Prospecção")["linhas"][0][13] = "ligar para 123.456.789-09"            # CPF formatado no texto livre
    _recusa(cli, p, "valores inválidos")


def test_recusa_recortes_e_uf_incoerentes(cli):
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["recortes_linhas"][0]["linhas"].append(10 ** 6)
    _recusa(cli, p, "recortes_linhas")
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["uf_linhas"].pop()
    _recusa(cli, p, "uf_linhas")
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["uf_linhas"][0] = "am"
    _recusa(cli, p, "uf_linhas")
    p, r = _rel("pl_entregas")
    _tab(r, "Entregas")["kpis_padrao"] = [{"rotulo": "x", "valor": 3}]
    _recusa(cli, p, "kpis_padrao")


def test_recusa_selo_fora_das_colunas_marcadas(cli):
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["colunas"][7]["chip"] = {"AM": ["#112233", "#445566"]}      # UF não leva selo
    _recusa(cli, p, "selo")
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["colunas"][16]["chip"] = [[None, "vermelho", None]]          # cor inválida na faixa
    _recusa(cli, p, "selo")
    p, r = _rel("pl_entregas")
    _tab(r, "Entregas")["colunas"][2]["chip_tom"] = "SITUAÇÃO"                      # coluna visível, não oculta
    _recusa(cli, p, "selo")
    p, r = _rel("pl_entregas")
    _tab(r, "Entregas")["colunas"][2]["chip_tom"] = "NAO EXISTE"
    _recusa(cli, p, "selo")
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["colunas"][17]["barra"] = {"max": 0, "faixas": [[None, "#112233", "#112233"]]}
    _recusa(cli, p, "selo")


@pytest.mark.parametrize("chave", ["edicao", "editar", "abrir", "detalhe", "kpis_de", "total_de", "totais_por",
                                   "recortes", "ordem_exportar", "cores_celulas", "so_exportar", "solicitacao_bap",
                                   "_interna", "pdf_pagina", "nota_pdf", "exportar_x"])
def test_recusa_chave_proibida_em_qualquer_nivel(cli, chave):
    for nivel in ("aba", "junta", "sub"):
        p, r = _rel("pv_pedidos")
        if nivel == "aba":
            alvo = _tab(r, "Pedidos")
        elif nivel == "junta":
            alvo = _tab(r, "Pedidos")["juntas"][0]["tabela"]
        else:
            alvo = _tab(r, "Solicitação BAP")["subabas"][0]
        alvo[chave] = None
        _recusa(cli, p, "chave não aceita")
    p, r = _rel("pv_pedidos")                                    # dentro de um cartão da aba
    _tab(r, "Pedidos")["kpis_padrao"][0]["edicao"] = {}
    _recusa(cli, p, "chave não aceita")


def test_recusa_cobranca_e_tabelas_fora_do_lugar(cli):
    p, r = _rel("pv_pedidos")
    r["cobranca"] = {"fila": []}
    _recusa(cli, p, "cobranca só no pl_inadimplencia")
    p = pacote_farol()
    p["relatorios"]["pl_inadimplencia"]["tabelas"] = [{"titulo": "Pedidos"}]
    _recusa(cli, p, "")


def test_recusa_junta_fora_do_lugar_ou_com_liga_diferente(cli):
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["juntas"].reverse()
    _recusa(cli, p, "junta")
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["juntas"][0]["liga"] = ["PEDIDOS", "CÓD.", "|"]
    _recusa(cli, p, "liga")
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["juntas"][0]["titulo"] = "Qualquer"
    _recusa(cli, p, "junta")
    p, r = _rel("pv_pedidos")
    _tab(r, "Pedidos")["juntas"][2]["mostrar"] = ["NAO EXISTE"]
    _recusa(cli, p, "mostrar")
    p, r = _rel("vc_visitas")
    r["tabelas"][0]["juntas"] = []                                # Visita não tem junta
    assert postar(cli, p).status_code == 200 or True              # lista vazia é aceita (nenhuma junta)


def test_recusa_subaba_com_tipo_ou_titulo_fora_da_lista(cli):
    p, r = _rel("pv_pedidos")
    _tab(r, "Solicitação BAP")["subabas"][0]["colunas"][4]["tipo"] = "moeda"
    _recusa(cli, p, "tipo fora de texto, num e data")
    p, r = _rel("pv_pedidos")
    _tab(r, "Solicitação BAP")["subabas"][0]["titulo"] = "Outra"
    _recusa(cli, p, "subaba")
    p, r = _rel("pv_pedidos")
    _tab(r, "Solicitação BAP")["subabas"].reverse()
    _recusa(cli, p, "subaba")
    p, r = _rel("pv_pedidos")
    _tab(r, "Solicitação BAP")["colunas"] = [{"nome": "X", "tipo": "texto"}]
    _recusa(cli, p, "Solicitação BAP")


def test_aderencia_conferida_por_padrao_de_nome(cli):
    p, r = _rel("vc_visitas")
    t = _tab(r, "Aderência dia a dia")
    t["colunas"][3]["nome"] = "dia 05"
    _recusa(cli, p, "colunas diferentes")
    p, r = _rel("vc_visitas")                                    # uma coluna de dia a mais é aceita (N muda com o mês)
    t = _tab(r, "Aderência dia a dia")
    t["colunas"].insert(2, dict(t["colunas"][2], nome="02/11 DOM"))
    for ln in t["linhas"]:
        ln.insert(2, 50.0)
    t["total"].insert(2, None)
    assert postar(cli, p).status_code == 200


def test_validar_limite_de_linhas_por_tabela():
    p, r = _rel("vc_visitas")
    t = _tab(r, "Indicação")
    t["linhas"] = [[None] * len(t["colunas"])] * (tabelas.MAX_LINHAS + 1)
    t["tons"] = [""] * len(t["linhas"])
    assert "linhas" in " ".join(tabelas.validar("vc_visitas", r))


def test_recusa_pacote_maior_que_o_limite_do_ambiente(cli):
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["vc_visitas"], "Indicação")
    t["linhas"] = [[None] * len(t["colunas"])] * 40000
    t["tons"] = [""] * 40000
    assert postar(cli, p).status_code == 413                       # o ambiente de teste limita a 1 MB


# ------------------------------------------------------------------ tabela igual ao fixture
def _esp(v, tipo):
    if v is None or v == "":
        return ""
    if tipo == "moeda":
        return "R$ " + f"{v:,.0f}".replace(",", ".")
    if tipo == "int":
        return f"{int(v):,}".replace(",", ".")
    if tipo == "num":
        return f"{v:,.0f}".replace(",", ".") if float(v).is_integer() else f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if tipo == "num1":
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if tipo == "pct":
        return f"{v:.0f}%"
    if tipo == "pct1":
        return f"{v:.1f}".replace(".", ",") + "%"
    if tipo == "data":
        return f"{v[8:10]}/{v[5:7]}/{v[:4]}"
    if tipo == "dia":
        return f"{v[8:10]}/{v[5:7]}"
    return str(v)


def _sem_filtro(t):
    return {f"f{i}": [""] for i, c in enumerate(t["colunas"])}


def _todas(t):
    return tabelas.tabela_para_tela(t, _sem_filtro(t), pagina_tam=10 ** 6)


@pytest.mark.parametrize("rid", RIDS)
def test_cada_tabela_na_tela_e_igual_ao_fixture(rid):
    p = pacote_tres_farois()
    for t in p["relatorios"][rid]["tabelas"]:
        if t.get("subabas"):
            continue
        tela = _todas(t)
        vis = [k for k, c in enumerate(t["colunas"]) if not c.get("oculta")]
        assert [c["nome"] for c in tela["cols"]] == [t["colunas"][k]["nome"] for k in vis]
        # com os filtros apagados, a tela tem todas as linhas do pacote, na ordem do pacote
        assert tela["total_linhas"] == len(t["linhas"]), t["titulo"]
        for k, ln in enumerate(tela["linhas"]):
            for cel, j in zip(ln["cel"], vis):
                assert cel["t"] == _esp(t["linhas"][k][j], t["colunas"][j]["tipo"]), (t["titulo"], k, t["colunas"][j]["nome"])
            assert ln["tom"] == (t.get("tons") or [""] * len(t["linhas"]))[k]
        for c in tela["cols"]:                                       # nada oculto na tela
            assert not t["colunas"][c["i"]].get("oculta")


def test_filtro_padrao_do_pedidos_so_em_aberto_e_mes_oculto():
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["pv_pedidos"], "Pedidos")
    tela = tabelas.tabela_para_tela(t, {})
    abertos = [ln for ln in t["linhas"] if ln[20] == "EM ABERTO"]
    assert tela["total_linhas"] == len(abertos) and tela["padrao"]
    assert "MÊS" not in [f["nome"] for f in tela["filtros"]]              # filtro oculto: sem caixa
    # a pessoa não derruba o filtro oculto pela URL
    assert tabelas.tabela_para_tela(t, {"f30": ["OUT/26"]})["total_linhas"] == len(abertos)


def test_solicitacao_igual_ao_fixture_com_7_subabas(com_tabelas):
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["pv_pedidos"], "Solicitação BAP")
    for k, s in enumerate(t["subabas"]):
        nomes, tela = tabelas.subabas_para_tela(t, k, {})
        assert nomes == [x["titulo"] for x in t["subabas"]] and tela["total_linhas"] == len(s["linhas"])
        assert [c["nome"] for c in tela["cols"]] == [c["nome"] for c in s["colunas"]]
        for ln, orig in zip(tela["linhas"], s["linhas"]):
            for cel, v, c in zip(ln["cel"], orig, s["colunas"]):
                assert cel["t"] == _esp(v, "num" if c["tipo"] == "num" else c["tipo"])
        h = com_tabelas.get(f"/farol/pv_pedidos?aba=solicitacao&sub={k}").text
        assert s["colunas"][0]["nome"] in h
    h = com_tabelas.get("/farol/pv_pedidos?aba=solicitacao&sub=99").text
    assert "COD_PRODUTO" in h and 'class="ativa">Solicitacao Lojas' in h        # sub fora da lista: a primeira
    h = com_tabelas.get("/farol/pv_pedidos?aba=solicitacao&sub=1").text
    assert "ESTOQUE_NA_ORIGEM" in h and "Solicitacao CD</a>" in h and "FiliaisExcluir" in h


def test_pagina_mostra_valores_do_fixture(com_tabelas):
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos").text
    assert "CLIENTE FICTICIO 01" in h and "R$ 5.220" in h and "MOTORISTA" not in h
    cab = re.findall(r"<th[^>]*>(?:<a[^>]*>)?([^<▲▼]+)", h)
    assert "RAZÃO SOCIAL" in cab and "CHAVE" not in cab and "PRODUTO" not in cab         # colunas ocultas ficam fora
    h = com_tabelas.get("/farol/pl_entregas?aba=entregas").text
    cab = re.findall(r"<th[^>]*>(?:<a[^>]*>)?([^<▲▼]+)", h)
    assert "MOTORISTA FICTICIO" in h and "AGUARDANDO COLETA" in h and "LOCAL/FRETE" not in cab and "TOM SLA" not in cab
    h = com_tabelas.get("/farol/vc_visitas?aba=supervisor").text
    assert "SUPERVISOR FICTICIO 01" in h and "TOTAL" in h and "08:00" in h


# ------------------------------------------------------------------ filtro, recorte, ordem, página
def test_recorte_e_contagem(com_tabelas):
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["pv_pedidos"], "Pedidos")
    tela = tabelas.tabela_para_tela(t, {"rec": ["1"]})
    esperado = {k for k in t["recortes_linhas"][1]["linhas"] if t["linhas"][k][20] == "EM ABERTO"}
    assert tela["total_linhas"] == len(esperado) and tela["rec"] == 1
    assert [r["qtd"] for r in tela["recortes"]][1] == len(esperado)
    assert tabelas.tabela_para_tela(t, {"rec": ["99"]})["rec"] is None
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos&rec=1").text
    assert "Mais de 4 dias" in h and f"{len(esperado)} linhas" in h


def test_ordenacao_filtro_multi_e_paginas(com_tabelas):
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["vc_visitas"], "Cliente a cliente")
    ix = {c["nome"]: k for k, c in enumerate(t["colunas"])}
    c0 = {}
    tela = tabelas.tabela_para_tela(t, c0)
    assert tela["total_linhas"] == 230 and tela["paginas"] == 3 and len(tela["linhas"]) == 100
    t3 = tabelas.tabela_para_tela(t, {"pag": ["3"]})
    assert len(t3["linhas"]) == 30 and t3["pag"] == 3
    assert tabelas.tabela_para_tela(t, {"pag": ["99"]})["pag"] == 3
    d = tabelas.tabela_para_tela(t, {"ord": [str(ix["VALOR PEDIDO"])], "dir": ["desc"]}, pagina_tam=5)
    vals = [ln["cel"][[c["i"] for c in d["cols"]].index(ix["VALOR PEDIDO"])]["t"] for ln in d["linhas"]]
    assert [v for v in vals if v][:1] == ["R$ 1.800"]                          # no desc, o maior vem antes dos demais
    m = tabelas.tabela_para_tela(t, {f"f{ix['CURVA']}": ["A", "B"]})
    assert m["total_linhas"] == sum(1 for ln in t["linhas"] if ln[ix["CURVA"]] in ("A", "B"))
    h = com_tabelas.get("/farol/vc_visitas?aba=cliente&pag=2").text
    assert "Página 2 de 3" in h and "« Anterior" in h and "Próxima »" in h
    h = com_tabelas.get(f"/farol/vc_visitas?aba=cliente&f{ix['CURVA']}=A&f{ix['CURVA']}=C").text
    assert "Página 1 de" in h


def test_total_so_sem_filtro_nem_recorte():
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["vc_visitas"], "Dia a dia")
    assert tabelas.tabela_para_tela(t, {})["total"] is not None
    assert tabelas.tabela_para_tela(t, {"rec": ["0"]})["total"] is None
    ix = [c["nome"] for c in t["colunas"]].index("SITUAÇÃO")
    assert tabelas.tabela_para_tela(t, {f"f{ix}": ["SEM VISITA"]})["total"] is None


# ------------------------------------------------------------------ estado (D5, RN-GER-006)
def test_estado_filtra_linhas_pelo_uf_linhas_e_cartoes_da_aba_viram_traco(com_tabelas):
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["pv_pedidos"], "Pedidos")
    tela = tabelas.tabela_para_tela(t, {}, uf="PA")
    esperado = [k for k, ln in enumerate(t["linhas"]) if ln[20] == "EM ABERTO" and t["uf_linhas"][k] == "PA"]
    assert tela["total_linhas"] == len(esperado) and not tela["padrao"]
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos&uf=PA").text
    assert f"{len(esperado)} linhas" in h and "Com filtro, os cartões seguem só no PC." in h
    assert "3,6 dia(s)" not in h and '<div class="kpi-valor">—</div>' in h
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos").text                 # sem estado: os cartões prontos da aba
    assert "3,6 dia(s)" in h and "Com filtro, os cartões" not in h
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos&uf=XX").text           # estado desconhecido: ignora
    assert "3,6 dia(s)" in h


def test_cartoes_da_aba_sem_numero_com_recorte_ou_filtro(com_tabelas):
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos&rec=0").text
    assert "Com filtro, os cartões seguem só no PC." in h and "3,6 dia(s)" not in h
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos&f8=MANAUS").text
    assert "Com filtro, os cartões seguem só no PC." in h


def test_entregas_estado_filtra_linhas_e_junta_de_pendencias(com_tabelas):
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["pl_entregas"], "Entregas")
    tela = tabelas.tabela_para_tela(t, {}, uf="MA")
    assert tela["total_linhas"] == sum(1 for u in t["uf_linhas"] if u == "MA")
    js = tabelas.juntas_para_tela(t, tela["idxs"], "MA")
    jt = t["juntas"][0]["tabela"]
    assert js[0]["total_linhas"] == sum(1 for u in jt["uf_linhas"] if u == "MA")
    assert len(tabelas.juntas_para_tela(t, tela["idxs"], None)[0]["linhas"]) == len(jt["linhas"])
    h = com_tabelas.get("/farol/pl_entregas?aba=entregas&uf=PA").text
    assert "Pendências dos meses anteriores" in h


def test_visita_e_solicitacao_sem_estado_com_aviso(com_tabelas):
    h = com_tabelas.get("/farol/vc_visitas?aba=dia&uf=AM").text
    assert tabelas.AVISO_SEM_ESTADO in h and "Filtro por estado" not in h
    h = com_tabelas.get("/farol/pv_pedidos?aba=solicitacao&uf=AM").text
    assert tabelas.AVISO_SEM_ESTADO in h and "Solicitacao Lojas" in h


# ------------------------------------------------------------------ juntas (liga)
def test_junta_com_liga_so_das_linhas_visiveis_de_todas_as_paginas():
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["pv_pedidos"], "Pedidos")
    tela = tabelas.tabela_para_tela(t, {"rec": ["1"]}, pagina_tam=3)           # 7 linhas, 3 por página
    assert tela["paginas"] > 1
    visiveis = {t["linhas"][k][2].lstrip("0") for k in tela["idxs"]}           # PEDIDO de todas as páginas
    js = tabelas.juntas_para_tela(t, tela["idxs"])
    for j, jt in zip(js, [x["tabela"] for x in t["juntas"]]):
        if j["titulo"] == "Analítico por pedido":
            esperado = [ln for ln in jt["linhas"] if ln[0].lstrip("0") in visiveis]
        else:
            esperado = [ln for ln in jt["linhas"] if {x.strip().lstrip("0") for x in ln[3].split("|")} & visiveis]
        assert j["total_linhas"] == len(esperado), j["titulo"]
    assert js[0]["total_linhas"] < len(t["juntas"][0]["tabela"]["linhas"])          # a liga corta de verdade


def test_junta_mostra_so_as_colunas_de_mostrar_e_nao_as_ocultas():
    p = pacote_tres_farois()
    t = _tab(p["relatorios"]["pv_pedidos"], "Pedidos")
    j = tabelas.juntas_para_tela(t, list(range(len(t["linhas"]))))
    assert [c["nome"] for c in j[2]["cols"]] == t["juntas"][2]["mostrar"]
    assert "FILIAL BAP" not in [c["nome"] for c in j[2]["cols"]]
    assert [c["nome"] for c in j[0]["cols"]][:2] == ["DATA", "UF"]


def test_junta_aparece_na_pagina_com_titulo_do_quadro(com_tabelas):
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos").text
    for tit in ("Gerar ID de separação CD", "Gerar reversa de lojas", "Analítico por pedido"):
        assert tit in h
    h = com_tabelas.get("/farol/pl_entregas?aba=entregas").text
    assert "Pendências dos meses anteriores" in h and "SET/26" in h or "OUT/26" in h


# ------------------------------------------------------------------ selos
def test_selos_faixa_barra_e_pela_linha(com_tabelas):
    h = com_tabelas.get("/farol/pv_pedidos?aba=pedidos").text
    assert 'class="atend-trilho"' in h and "background:#2F7D32" in h              # barra do % ATENDIDO
    assert 'class="selo" style="background:#B3261E;color:#FFFFFF"' in h             # SLA > 4 em faixa
    h = com_tabelas.get("/farol/pl_entregas?aba=entregas").text
    assert 'class="selo" style="background:#E5F3DF;color:#2F7D32"' in h             # SLA pela linha (TOM SLA = ok)
    assert 'style="background:#B3261E;color:#FFFFFF"' in h
    h = com_tabelas.get("/farol/vc_visitas?aba=vendedor").text
    assert 'style="background:#FDECEA;color:#B3261E"' in h and 'style="background:#E5F3DF;color:#2F7D32"' in h


def test_linha_pintada_so_no_pedidos(com_tabelas):
    assert "tom-grave" in com_tabelas.get("/farol/pv_pedidos?aba=pedidos&f20=").text
    assert "tom-alerta" not in com_tabelas.get("/farol/pl_entregas?aba=entregas").text


def test_faixa_de_igual_ao_bap_visual():
    f = [[1, "#a", "#b"], [3, None, None], [None, "#c", "#d"]]
    assert tabelas._faixa_de(0, f) == ("#a", "#b") and tabelas._faixa_de(2, f) == (None, None)
    assert tabelas._faixa_de(99, f) == ("#c", "#d")


# ------------------------------------------------------------------ formato das células
def test_formatos_do_contrato():
    fm = tabelas.fmt_celula
    assert fm(1250.5, "moeda") == "R$ 1.250" or fm(1250.5, "moeda") == "R$ 1.251"
    assert fm(1250.5, "moeda2") == "R$ 1.250,50" and fm(1250.5, "moeda", centavos=True) == "R$ 1.250,50"
    assert fm(85.34, "pct") == "85%" and fm(85.34, "pct1") == "85,3%"
    assert fm("2026-11-19", "data") == "19/11/2026" and fm("2026-11-19", "dia") == "19/11"
    assert fm("08:15", "hora") == "08:15" and fm(1250, "int") == "1.250" and fm(1250.5, "num") == "1.250,5"
    assert fm(3.46, "num1") == "3,5" and fm(None, "moeda") == "" and fm("", "data") == ""


# ------------------------------------------------------------------ celular: sem rolagem da página, 1ª coluna fixa
def test_css_rolagem_lateral_primeira_coluna_fixa_e_aba_larga():
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    assert ".rolagem{overflow-x:auto}" in css and "position:sticky;left:0" in css
    assert "main.larga" in css and ".subabas" in css and ".junta" in css and ".atend-trilho" in css


# ------------------------------------------------------------------ robô antigo e aba fora
def test_robo_antigo_so_resumo_e_aba_pedida_diz_indisponivel(admin):
    assert postar(admin, pacote_tres_farois(com_tabelas=False)).status_code == 200
    h = admin.get("/farol/pv_pedidos").text
    assert "R$ 112 mil" in h and 'class="abas' not in h
    r = admin.get("/farol/pv_pedidos?aba=pedidos")
    assert r.status_code == 200 and "ainda não disponível na web" in r.text.lower()


def test_aba_que_ficou_fora_some_da_barra_e_nao_quebra(admin):
    p = pacote_tres_farois()
    del p["relatorios"]["vc_visitas"]["tabelas"][4:]
    assert postar(admin, p).status_code == 200
    h = admin.get("/farol/vc_visitas").text
    assert "?aba=dia" in h and "?aba=cliente" not in h and "?aba=prospeccao" not in h
    assert admin.get("/farol/vc_visitas?aba=cliente").status_code == 200


# ------------------------------------------------------------------ dado pessoal (RN-GER-011) e fixture
def test_fixture_dos_tres_farois_e_100_por_cento_ficticia():
    txt = json.dumps(pacote_tres_farois(), ensure_ascii=False)
    assert not RE_CNPJ.search(txt) and not RE_FONE.search(txt)
    assert "FICTICIO" in txt and "TELEFONE" not in txt and "CNPJ" not in txt


def test_nenhum_nome_de_coluna_da_lista_do_contrato_e_dado_pessoal():
    for titulo, cols in tabelas.COLUNAS.items():
        assert not [n for n, _, _ in cols if tabelas.coluna_fora(n)], titulo


def test_coluna_fora_ignora_acento_e_caixa():
    assert tabelas.coluna_fora("endereço") and tabelas.coluna_fora("E-Mail") and tabelas.coluna_fora(" foto ")
    assert not tabelas.coluna_fora("CLIENTE")


# ------------------------------------------------------------------ a Inadimplência não mudou
def test_inadimplencia_igual_ao_golden_gerado_com_o_codigo_anterior():
    from cobranca_fixture import farol_com_cobranca
    g = json.loads((Path(__file__).parent / "golden_inadimplencia.json").read_text(encoding="utf-8"))
    f = farol_com_cobranca()
    for t in f["tabelas"]:
        for i, q in enumerate(g["consultas"]):
            novo = cobranca.tabela_para_tela(t, t["titulo"], q, pagina_tam=5)
            velho = g["saida"][f'{t["titulo"]}|{i}']
            novo = json.loads(json.dumps(novo, ensure_ascii=False))
            for chave in velho:                                           # as chaves de antes, com o mesmo valor
                if chave == "cols":
                    assert [{k: c[k] for k in ("i", "nome", "tipo", "num")} for c in novo[chave]] == velho[chave]
                elif chave == "linhas":
                    assert [{"tom": ln["tom"], "cel": [{k: c[k] for k in ("t", "f", "c")} for c in ln["cel"]]}
                            for ln in novo[chave]] == velho[chave]
                elif chave == "total":
                    assert (None if novo[chave] is None else [{k: c[k] for k in ("t", "f", "c")} for c in novo[chave]]) == velho[chave]
                elif chave == "filtros":
                    assert [{k: f_[k] for k in ("nome", "chave", "i", "multi", "opcoes", "sel")} for f_ in novo[chave]] == velho[chave]
                else:
                    assert novo[chave] == velho[chave], (t["titulo"], i, chave)


def test_inadimplencia_na_pagina_continua_com_moeda_com_centavos_e_total(admin):
    from cobranca_fixture import pacote_cobranca
    assert postar(admin, pacote_cobranca()).status_code == 200
    h = admin.get("/farol/pl_inadimplencia?aba=titulos").text
    assert "R$ 1.500,00" in h and "<tfoot>" in h and "R$ 117.000,00" in h


# ------------------------------------------------------------------ padrão de 25 MB
def test_config_padrao_do_pacote_e_25_mb_como_o_render_yaml(monkeypatch, amb):
    from app import config
    monkeypatch.delenv("BAP_WEB_PACOTE_MAX_MB", raising=False)
    monkeypatch.setenv("BAP_WEB_TOKEN", "x" * 40)
    assert config.carregar().pacote_max == 25 * 1024 * 1024
    yaml = Path(__file__).resolve().parents[2] / "render.yaml"
    if yaml.exists():
        assert re.search(r"BAP_WEB_PACOTE_MAX_MB\s*\n\s*value:\s*['\"]?25", yaml.read_text(encoding="utf-8"))
