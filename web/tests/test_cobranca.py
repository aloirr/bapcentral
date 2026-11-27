"""T-0017 entrega 2: Títulos, Por cliente e "Cobrar no WhatsApp" (contrato §10.6; RN-POS-001 a 004).
Fixture fictícia: nada de cliente, CNPJ ou telefone real."""
import json
from datetime import datetime, timedelta

import pytest
from cobranca_fixture import farol_com_cobranca, pacote_cobranca
from conftest import TOKEN, postar, token_form
from farol_fixture import pacote_farol
from test_farois import _usuario

from app import cobranca

URL = "/farol/pl_inadimplencia"
FONE = "5592900000001"
AGORA = datetime(2026, 11, 24, 15, 0, 0, tzinfo=cobranca.MANAUS)


@pytest.fixture(autouse=True)
def _hoje(monkeypatch):
    monkeypatch.setattr(cobranca, "agora", lambda: AGORA)


def _com(**mud):
    p = pacote_cobranca()
    f = p["relatorios"]["pl_inadimplencia"]
    for k, v in mud.items():
        f[k] = v
    return p


def _acoes(c, cliente="000001-01", acao="ENVIADO", telefone="", csrf=None):
    return c.post(URL + "/cobranca", data={"csrf": csrf or token_form(c, URL + "?aba=cobrar"),
                                           "cliente": cliente, "acao": acao, "telefone": telefone})


# ----------------------------------------------------------------- validador
def test_pacote_com_tabelas_e_cobranca_aceito(cli):
    assert postar(cli, pacote_cobranca()).status_code == 200


def _recusa(cli, p, trecho=""):
    r = postar(cli, p)
    assert r.status_code == 422, r.text
    assert trecho in json.dumps(r.json(), ensure_ascii=False)
    assert "Cliente 001" not in r.text and FONE not in r.text      # o motivo não traz dado pessoal


def test_recusa_coluna_telefone_cnpj_cpf_email(cli):
    for nome in ("TELEFONE", "CNPJ", "CPF", "E-MAIL", "EMAIL"):
        p = pacote_cobranca()
        t = p["relatorios"]["pl_inadimplencia"]["tabelas"][1]
        t["colunas"].append({"nome": nome, "tipo": "texto"})
        for ln in t["linhas"]:
            ln.append("x")
        _recusa(cli, p, "coluna proibida")


def test_recusa_colunas_fora_da_lista_ordem_ou_tipo(cli):
    p = pacote_cobranca()
    c = p["relatorios"]["pl_inadimplencia"]["tabelas"][0]["colunas"]
    c[0], c[1] = c[1], c[0]
    _recusa(cli, p, "colunas diferentes")
    p = pacote_cobranca()
    p["relatorios"]["pl_inadimplencia"]["tabelas"][0]["colunas"][18]["tipo"] = "texto"
    _recusa(cli, p, "colunas diferentes")
    p = pacote_cobranca()
    p["relatorios"]["pl_inadimplencia"]["tabelas"][0]["linhas"][0].pop()
    _recusa(cli, p, "células")
    p = pacote_cobranca()
    p["relatorios"]["pl_inadimplencia"]["tabelas"].reverse()
    _recusa(cli, p, "titulo inesperado")


@pytest.mark.parametrize("chave", ["edicao", "editar", "abrir", "detalhe", "kpis_de", "recortes",
                                   "_interna", "exportar_excel"])
def test_recusa_chave_proibida_na_tabela(cli, chave):
    p = pacote_cobranca()
    p["relatorios"]["pl_inadimplencia"]["tabelas"][0][chave] = {}
    _recusa(cli, p, "chave não aceita")


def test_recusa_cobranca_com_telefone_cadastral_ou_chave_extra(cli):
    p = pacote_cobranca()
    p["relatorios"]["pl_inadimplencia"]["cobranca"]["fila"][0]["telefone_cad"] = "(92) 90000-0001"
    _recusa(cli, p, "chaves diferentes")
    p = pacote_cobranca()
    p["relatorios"]["pl_inadimplencia"]["cobranca"]["fila"][0]["whatsapp"] = "(92) 90000-0001"
    _recusa(cli, p, "whatsapp inválido")


def test_tabelas_e_cobranca_vao_juntas_e_so_no_pl_inadimplencia(cli):
    p = pacote_cobranca()
    del p["relatorios"]["pl_inadimplencia"]["cobranca"]
    _recusa(cli, p, "vão juntas")
    p = pacote_cobranca()
    del p["relatorios"]["pl_inadimplencia"]["tabelas"]
    _recusa(cli, p, "vão juntas")
    p = pacote_farol(pv_pedidos=farol_com_cobranca())
    _recusa(cli, p, "só no pl_inadimplencia")


def test_fixo_vem_em_whatsapp_com_aviso_e_vazio_so_sem_numero_valido(cli):
    assert postar(cli, pacote_cobranca()).status_code == 200   # item 2: fixo (55+DDD+8) com aviso; item 3: vazio


# ----------------------------------------------------------------- perfis (RN-POS-004)
def _tela(c, aba=None):
    return c.get(URL + (f"?aba={aba}" if aba else ""))


def test_perfil_admin_ve_tudo_e_cobra(admin):
    postar(admin, pacote_cobranca())
    for aba in ("titulos", "cliente", "cobrar", None):
        assert _tela(admin, aba).status_code == 200
    h = _tela(admin, "cobrar").text
    assert "wa.me/" + FONE in h and "ENVIADO" in h and "PULADO" in h
    assert _acoes(admin).status_code == 200


def test_perfil_pos_venda_ve_tudo_e_cobra(admin):
    postar(admin, pacote_cobranca())
    c = _usuario(admin, "pv.cobra", "pos_venda")
    for aba in ("titulos", "cliente", "cobrar"):
        assert _tela(c, aba).status_code == 200
    assert _acoes(c, "000002-01", "PULADO").status_code == 200


def test_perfil_gerente_so_tabelas_sem_telefone_e_sem_botao(admin):
    postar(admin, pacote_cobranca())
    g = _usuario(admin, "ger.cobra", "gerente")
    for aba in ("titulos", "cliente"):
        h = _tela(g, aba).text
        assert "Cliente 001" in h and FONE not in h and "wa.me" not in h
        assert "ENVIADO" not in h and "TELEFONE" not in h
    assert "Cobrar no WhatsApp" not in _tela(g).text           # a aba nem aparece
    assert _tela(g, "cobrar").status_code == 403
    r = g.post(URL + "/cobranca", data={"csrf": token_form(g, URL + "?aba=titulos"),
                                        "cliente": "000001-01", "acao": "ENVIADO"})
    assert r.status_code == 403
    assert cobranca.Diario(_dados(admin)).desde(0)["linhas"] == []


def _dados(admin):
    import os
    return __import__("pathlib").Path(os.environ["BAP_WEB_DADOS"])


def test_perfil_diretor_so_cartoes_e_graficos(admin):
    postar(admin, pacote_cobranca())
    d = _usuario(admin, "dir.cobra", "diretor")
    h = _tela(d).text
    assert "R$ 1,20 mi" in h and "Cliente 001" not in h and 'class="abas"' not in h
    for aba in ("titulos", "cliente", "cobrar"):
        assert _tela(d, aba).status_code == 403
    r = d.post(URL + "/cobranca", data={"csrf": token_form(d, URL), "cliente": "000001-01",
                                        "acao": "PULADO"})
    assert r.status_code == 403


@pytest.mark.parametrize("perfil", ["pre_venda", "vendas"])
def test_outros_perfis_403_no_farol_e_nas_acoes(admin, perfil):
    postar(admin, pacote_cobranca())
    c = _usuario(admin, "o." + perfil.replace("_", ""), perfil)
    assert _tela(c).status_code == 403 and _tela(c, "titulos").status_code == 403
    assert c.post(URL + "/cobranca", data={"csrf": "x"}).status_code == 403


def test_aba_de_tabela_em_outro_farol_403(admin):
    postar(admin, pacote_farol(pl_entregas=farol_inadimplencia_simples()))
    assert admin.get("/farol/pl_entregas?aba=titulos").status_code == 403


def farol_inadimplencia_simples():
    from farol_fixture import farol_inadimplencia
    return farol_inadimplencia()


def test_sem_login_vai_ao_login(cli):
    r = cli.get(URL + "?aba=cobrar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert cli.post(URL + "/cobranca", data={"cliente": "x"}, follow_redirects=False).status_code == 303


def test_robo_antigo_sem_tabelas_nao_mostra_abas(admin):
    postar(admin, pacote_farol())
    h = _tela(admin).text
    assert 'class="abas"' not in h
    assert "inda não disponível" in _tela(admin, "titulos").text


# ----------------------------------------------------------------- abas
def test_paginas_com_tabela_e_fila_no_store_e_noindex(admin):
    postar(admin, pacote_cobranca())
    for aba in ("titulos", "cliente", "cobrar"):
        r = _tela(admin, aba)
        assert r.headers["cache-control"] == "no-store"
        assert '<meta name="robots" content="noindex, nofollow">' in r.text
    assert "noindex" not in _tela(admin).text


def test_aba_titulos_colunas_total_e_exportacao_por_link(admin):
    postar(admin, pacote_cobranca())
    h = _tela(admin, "titulos").text
    for n in ("SITUAÇÃO", "DIAS ATRASO", "SALDO", "SUPERVISOR"):
        assert n in h
    assert "R$ 1.500,00" in h and "01/09/2026" in h and "R$ 93.600,00" in h
    assert "/exportar?" in h and 'method="post"' not in h.split("<main")[1].lower()       # T-0026: Excel e PDF por link (só leitura)
    assert "Cliente 012" in h


def test_filtro_e_ordenacao_na_url(admin):
    postar(admin, pacote_cobranca())
    h = _tela(admin, "titulos").text
    assert h.count("<tr class=") == 12
    h = admin.get(URL + "?aba=titulos&f14=PA").text              # UF = PA: clientes 3, 6, 9, 12
    assert h.count("<tr class=") == 4 and "Cliente 003" in h and "Cliente 001" not in h
    h = admin.get(URL + "?aba=titulos&f14=PA&f14=AM").text      # multi
    assert h.count("<tr class=") == 12
    h = admin.get(URL + "?aba=titulos&ord=18&dir=desc").text    # VALOR decrescente
    assert h.index("Cliente 012") < h.index("Cliente 001")
    h = admin.get(URL + "?aba=titulos&ord=18&dir=asc").text
    assert h.index("Cliente 001") < h.index("Cliente 012")
    assert admin.get(URL + "?aba=titulos&ord=zz&pag=abc").status_code == 200


def test_aba_por_cliente(admin):
    postar(admin, pacote_cobranca())
    h = _tela(admin, "cliente").text
    assert "TÍTULOS VENCIDOS" in h and "ÚLTIMA COMPRA" in h and "R$ 14.400,00" in h
    assert "TELEFONE" not in h


# ----------------------------------------------------------------- fila e cobrança
def test_fila_mostra_mensagem_link_aviso_e_situacao(admin):
    postar(admin, pacote_cobranca())
    h = _tela(admin, "cobrar").text
    assert "Cobranças do PC até 08:07" in h
    assert "Olá, Cliente 001! Tudo bem?" in h and "<textarea" in h
    assert "https://wa.me/559232000002?text=" in h and "Fixo: confira se tem WhatsApp" in h
    assert "Sem celular: digite um número" in h                  # sem número: aviso, sem link
    assert h.count("https://wa.me/") == 4                      # 3 na fila + 1 no bloco recolhido
    # já tratados hoje vão ao fim, recolhidos
    assert "Já tratados hoje (1)" in h and h.index("Já tratados hoje") > h.index("Cliente 003")
    assert h.index("Cliente 004") > h.index("Já tratados hoje")
    assert "ENVIADO 21/11" in h                                  # cliente 5: site, 3 dias
    assert h.count("A COBRAR") == 3
    assert 'method="post"' not in h.split("<main")[1]            # botões por fetch, sem formulário (T-0031)


def test_um_so_botao_principal_enviado_escondido_ate_abrir_o_whatsapp(admin):
    postar(admin, pacote_cobranca())
    h = _tela(admin, "cobrar").text
    assert h.count("Abrir WhatsApp") >= 3
    assert 'data-acao="ENVIADO" hidden>Marquei como enviado' in h   # só aparece depois do toque no link
    assert "Pular" in h and "Desfazer" not in h                      # o Desfazer nasce no navegador
    js = admin.get("/static/cobranca.js").text
    assert "Desfazer" in js and "10000" in js and "pagehide" in js


def test_fila_pagina_de_10_em_10(admin):
    p = pacote_cobranca()
    f = p["relatorios"]["pl_inadimplencia"]["cobranca"]["fila"]
    base = f[0]
    for i in range(6, 26):
        f.append({**base, "cod": f"{i:06d}-01", "nome": f"Cliente {i:03d}", "ultimo": None,
                  "em_atraso": 100.0 - i})
    postar(admin, p)
    h1 = _tela(admin, "cobrar").text
    assert h1.count('<article class="cob') == 10 and "Página 1 de 3" in h1 and "Já tratados" not in h1
    h3 = admin.get(URL + "?aba=cobrar&pag=3").text
    assert "Página 3 de 3" in h3 and "Já tratados hoje (1)" in h3
    assert admin.get(URL + "?aba=cobrar&pag=99").status_code == 200 and admin.get(URL + "?aba=cobrar&pag=x").status_code == 200


def test_tabela_na_tela_cliente_nome_e_valor_primeiro_sem_mudar_o_pacote(admin, amb):
    postar(admin, pacote_cobranca())
    h = _tela(admin, "titulos").text
    cab = h[h.index("<thead>"):h.index("</thead>")]
    ordem = [c for c in ("CLIENTE", "NOME", "SALDO", "VALOR", "SITUAÇÃO", "NF") if c in cab]
    assert cab.index("CLIENTE") < cab.index("NOME") < cab.index("SALDO") < cab.index("VALOR") < cab.index("SITUAÇÃO")
    cab = _tela(admin, "cliente").text
    cab = cab[cab.index("<thead>"):cab.index("</thead>")]
    assert cab.index("CLIENTE") < cab.index("NOME") < cab.index("EM ATRASO") < cab.index("SITUAÇÃO")
    g = json.loads(sorted((amb / "pacotes").glob("*.json"))[-1].read_text(encoding="utf-8"))
    assert [c["nome"] for c in g["relatorios"]["pl_inadimplencia"]["tabelas"][0]["colunas"]][:3] == \
        ["SITUAÇÃO", "FAIXA", "FILIAL"]                              # o pacote segue a ordem do PC


def test_abas_quebram_em_linhas_e_dica_de_rolagem(admin):
    postar(admin, pacote_cobranca())
    assert "abas-quebra" in _tela(admin).text or "bc3-abas" in _tela(admin).text   # T-0031
    assert "Role para o lado" not in _tela(admin, "titulos").text      # T-0033: nenhuma tabela rola para o lado, sem a dica
def test_enviado_grava_diario_com_valores_do_pacote(admin):
    postar(admin, pacote_cobranca())
    r = _acoes(admin, "000001-01", "ENVIADO")
    j = r.json()
    assert r.status_code == 200 and j["ok"] and j["seq"] == 1 and j["repetido"] is False
    assert j["situacao"] == "ENVIADO HOJE" and len(j["id"]) == 36
    reg = cobranca.Diario(_dados(admin)).desde(0)["linhas"][0]
    assert reg["cliente"] == "000001-01" and reg["telefone"] == FONE and reg["em_atraso"] == 8000.0
    assert reg["titulos"] == 2 and reg["acao"] == "ENVIADO" and reg["usuario"] == "admin.teste"
    assert reg["quando"] == "2026-11-24 15:00:00" and len(reg["pacote_sha"]) == 64
    assert (_dados(admin) / "cobranca" / "COBRANCA_WEB_2026-11.jsonl").exists()


def test_valores_nao_vem_do_navegador(admin):
    postar(admin, pacote_cobranca())
    admin.post(URL + "/cobranca", data={"csrf": token_form(admin, URL + "?aba=cobrar"), "cliente": "000001-01",
                                        "acao": "PULADO", "em_atraso": "1", "titulos": "99"})
    reg = cobranca.Diario(_dados(admin)).desde(0)["linhas"][0]
    assert reg["em_atraso"] == 8000.0 and reg["titulos"] == 2 and reg["telefone"] == FONE


def test_clique_repetido_em_60s_devolve_repetido(admin):
    postar(admin, pacote_cobranca())
    a = _acoes(admin).json()
    b = _acoes(admin).json()
    assert b["ok"] and b["repetido"] is True and b["seq"] == a["seq"]
    assert len(cobranca.Diario(_dados(admin)).desde(0)["linhas"]) == 1
    c = _acoes(admin, acao="PULADO").json()                      # outra ação grava
    assert c["repetido"] is False and c["seq"] == 2 and c["situacao"] == "PULADO HOJE"


def test_telefone_corrigido_vale_so_para_o_envio(admin):
    postar(admin, pacote_cobranca())
    j = _acoes(admin, "000003-01", "ENVIADO", "(92) 99999-1234").json()    # item sem whatsapp
    assert j["ok"]
    assert cobranca.Diario(_dados(admin)).desde(0)["linhas"][0]["telefone"] == "5592999991234"
    assert "Sem celular: digite um número" in _tela(admin, "cobrar").text     # a fila não mudou
    assert _acoes(admin, "000003-01", "ENVIADO", "123").status_code == 400
    assert _acoes(admin, "000003-01", "PULADO").status_code == 200       # PULADO sem número
    assert _acoes(admin, "000003-01", "ENVIADO", "").status_code == 400  # sem número nenhum


def test_erros_da_rota_cobranca(admin):
    postar(admin, pacote_cobranca())
    assert _acoes(admin, "999999-99").status_code == 404
    assert _acoes(admin, acao="XPTO").status_code == 400
    assert _acoes(admin, csrf="errado").status_code == 403
    r = admin.post(URL + "/cobranca", data={"cliente": "000001-01", "acao": "ENVIADO"})
    assert r.status_code == 403                                  # sem csrf
    assert cobranca.Diario(_dados(admin)).desde(0)["linhas"] == []


def _epoca(admin):
    return cobranca.Diario(_dados(admin)).epoca()


def test_situacao_junta_diario_pela_epoca_e_web_ate_seq(admin):
    postar(admin, pacote_cobranca(web_ate_seq=0))               # web_epoca vazia: todo o diário conta
    _acoes(admin, "000002-01", "PULADO")
    assert "PULADO HOJE" in _tela(admin, "cobrar").text
    ep = _epoca(admin)
    # época atual e o PC já importou o seq 1: vale o `ultimo` do pacote (§10.6.3)
    postar(admin, pacote_cobranca(web_ate_seq=1, web_epoca=ep, gerado_em="2026-11-24T14:00:00-04:00"))
    h = _tela(admin, "cobrar").text
    assert "PULADO HOJE" not in h and "Cobranças do PC até 08:07" in h
    # época diferente (diário recomeçado): todo o diário conta como não visto
    postar(admin, pacote_cobranca(web_ate_seq=99, web_epoca="outra", gerado_em="2026-11-24T14:10:00-04:00"))
    assert "PULADO HOJE" in _tela(admin, "cobrar").text


def test_item_sai_do_pacote_da_pagina_ou_do_vigente_ou_404(admin):
    postar(admin, pacote_cobranca(gerado_em="2026-11-24T08:30:00-04:00"))
    import re
    sha_velho = re.search(r'data-sha="([0-9a-f]{64})"', _tela(admin, "cobrar").text).group(1)
    p2 = pacote_cobranca(gerado_em="2026-11-24T14:00:00-04:00")
    p2["relatorios"]["pl_inadimplencia"]["cobranca"]["fila"][0]["em_atraso"] = 7777.0
    postar(admin, p2)
    sha_novo = re.search(r'data-sha="([0-9a-f]{64})"', _tela(admin, "cobrar").text).group(1)
    assert sha_velho != sha_novo

    def post(cod, sha):
        return admin.post(URL + "/cobranca", data={"csrf": token_form(admin, URL + "?aba=cobrar"),
                                                   "pacote_sha": sha, "cliente": cod, "acao": "PULADO"})
    assert post("000001-01", sha_velho).status_code == 200      # item do pacote da página
    assert post("000002-01", sha_novo).status_code == 200       # item do vigente
    assert post("000003-01", "0" * 64).status_code == 200       # sha desconhecido: vigente
    assert post("000004-01", "").status_code == 200             # sem sha: vigente
    assert post("999999-99", sha_velho).status_code == 404
    regs = {r["cliente"]: r for r in cobranca.Diario(_dados(admin)).desde(0)["linhas"]}
    assert regs["000001-01"]["pacote_sha"] == sha_velho and regs["000001-01"]["em_atraso"] == 8000.0
    assert regs["000002-01"]["pacote_sha"] == sha_novo
    assert regs["000003-01"]["pacote_sha"] == sha_novo


def test_cliente_que_saiu_da_fila_mas_esta_no_pacote_da_pagina_ainda_registra(admin):
    import re
    postar(admin, pacote_cobranca(gerado_em="2026-11-24T08:30:00-04:00"))
    sha_velho = re.search(r'data-sha="([0-9a-f]{64})"', _tela(admin, "cobrar").text).group(1)
    p2 = pacote_cobranca(gerado_em="2026-11-24T14:00:00-04:00")
    p2["relatorios"]["pl_inadimplencia"]["cobranca"]["fila"].pop(0)      # 000001-01 pagou
    postar(admin, p2)
    r = admin.post(URL + "/cobranca", data={"csrf": token_form(admin, URL + "?aba=cobrar"),
                                            "pacote_sha": sha_velho, "cliente": "000001-01", "acao": "ENVIADO"})
    assert r.status_code == 200                                  # o registro não se perde
    r = admin.post(URL + "/cobranca", data={"csrf": token_form(admin, URL + "?aba=cobrar"),
                                            "cliente": "000001-01", "acao": "PULADO"})
    assert r.status_code == 404                                  # sem o sha, só o vigente: não está nele


def test_situacao_regras_rn_pos_002():
    hoje = AGORA.date()
    s = cobranca.situacao
    assert s(None, 7, hoje) == ""
    assert s({"quando": "2026-11-24 08:00:00", "acao": "ENVIADO", "origem": "PC"}, 7, hoje) == "ENVIADO HOJE"
    assert s({"quando": "2026-11-18 08:00:00", "acao": "ENVIADO", "origem": "PC"}, 7, hoje) == "ENVIADO 18/11"
    assert s({"quando": "2026-11-17 08:00:00", "acao": "ENVIADO", "origem": "PC"}, 7, hoje) == ""
    assert s({"quando": "2026-11-24 08:00:00", "acao": "PULADO", "origem": "PC"}, 7, hoje) == "PULADO HOJE"
    assert s({"quando": "2026-11-23 08:00:00", "acao": "PULADO", "origem": "PC"}, 7, hoje) == ""


def test_celular_mesma_regra_do_pc():
    assert cobranca.celular("(92) 99999-1234") == "5592999991234"
    assert cobranca.celular("092 3200-0002") == "559232000002"        # fixo segue, com aviso no PC
    assert cobranca.celular("92 8888-1111") == "5592988881111"        # 8 dígitos iniciados em 6-9 ganham o 9
    assert cobranca.celular("92 99999-9999") == "" and cobranca.celular("123") == ""


# ----------------------------------------------------------------- API do robô
def _h(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_api_exige_bearer(cli):
    for r in (cli.get("/api/cobranca"), cli.get("/api/cobranca", headers=_h("errado")),
              cli.post("/api/cobranca/confirmar", json={"ate_seq": 0})):
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_api_get_desde_e_confirmar(admin):
    postar(admin, pacote_cobranca())
    for cod in ("000001-01", "000002-01", "000003-01"):
        _acoes(admin, cod, "PULADO")
    ep = _epoca(admin)
    r = admin.get("/api/cobranca", headers=_h())
    j = r.json()
    assert r.status_code == 200 and [x["seq"] for x in j["linhas"]] == [1, 2, 3] and j["epoca"] == ep
    assert j["ate_seq"] == 3 and j["mais"] is False
    assert set(j["linhas"][0]) == {"seq", "id", "quando", "usuario", "cliente", "telefone", "em_atraso",
                                   "titulos", "acao", "pacote_sha"}
    j = admin.get("/api/cobranca?desde=2", headers=_h()).json()
    assert [x["seq"] for x in j["linhas"]] == [3] and j["ate_seq"] == 3
    j = admin.get("/api/cobranca?desde=3", headers=_h()).json()
    assert j == {"epoca": ep, "linhas": [], "ate_seq": 3, "mais": False}
    for ruim in ("-1", "x", "1.5"):
        assert admin.get(f"/api/cobranca?desde={ruim}", headers=_h()).status_code == 400

    def conf(**c):
        return admin.post("/api/cobranca/confirmar", json=c, headers=_h())
    r = conf(epoca=ep, ate_seq=2)
    assert r.status_code == 200 and r.json() == {"ok": True, "epoca": ep, "confirmado_ate": 2}
    assert conf(epoca=ep, ate_seq=2).json()["confirmado_ate"] == 2
    assert conf(epoca=ep, ate_seq=1).json()["confirmado_ate"] == 2
    assert conf(epoca=ep, ate_seq=4).status_code == 409
    r = conf(epoca="outra", ate_seq=2)
    assert r.status_code == 409 and r.json() == {"erro": "epoca"}
    for ruim in ({"epoca": ep, "ate_seq": -1}, {"epoca": ep, "ate_seq": "2"}, {"epoca": ep, "ate_seq": 1.5},
                 {"epoca": ep, "ate_seq": True}, {"epoca": ep}, {"ate_seq": 1}, {"epoca": 5, "ate_seq": 1}, {}):
        assert conf(**ruim).status_code == 400, ruim
    assert admin.post("/api/cobranca/confirmar", json=[], headers=_h()).status_code == 400
    assert admin.post("/api/cobranca/confirmar", content=b"xx", headers=_h()).status_code == 400


def test_api_nao_aceita_cookie_de_sessao(admin):
    assert admin.get("/api/cobranca").status_code == 401         # logado, sem Bearer


def test_api_get_limita_a_1000_com_mais(amb):
    d = cobranca.Diario(amb)
    for i in range(1002):
        d.registrar(usuario="u", cliente=f"c{i}", acao="PULADO", telefone="", em_atraso=1, titulos=1,
                    pacote_sha="0" * 64, agora_=AGORA)
    j = d.desde(0)
    assert len(j["linhas"]) == 1000 and j["ate_seq"] == 1000 and j["mais"] is True
    j = d.desde(1000)
    assert [x["seq"] for x in j["linhas"]] == [1001, 1002] and j["mais"] is False


# ----------------------------------------------------------------- diário
def _reg(d, cod, quando):
    return d.registrar(usuario="u", cliente=cod, acao="ENVIADO", telefone=FONE, em_atraso=1.5,
                       titulos=1, pacote_sha="0" * 64, agora_=quando)[0]


def test_diario_nunca_reescreve_e_limpa_por_arquivo_de_mes_fechado(amb):
    d = cobranca.Diario(amb)
    a, b = _reg(d, "a", AGORA), _reg(d, "b", AGORA)
    assert (a["seq"], b["seq"]) == (1, 2) and a["quando"] == "2026-11-24 15:00:00"
    nov = amb / "cobranca" / "COBRANCA_WEB_2026-11.jsonl"
    antes = nov.read_bytes()
    d.confirmar(d.epoca(), 2, AGORA)
    assert nov.read_bytes() == antes                              # confirmar não mexe nas linhas
    est = json.loads((amb / "cobranca" / "estado.json").read_text(encoding="utf-8"))
    assert est["ultimo_seq"] == 2 and est["confirmado_ate"] == 2 and len(est["epoca"]) == 32
    assert est["arquivos"]["COBRANCA_WEB_2026-11.jsonl"]["maior_seq"] == 2
    # mês aberto nunca sai, mesmo confirmado há mais de 30 dias
    d.confirmar(d.epoca(), 2, AGORA + timedelta(days=5))
    assert nov.exists()
    # dezembro: novembro é mês fechado; a confirmação que o cobre marca o arquivo
    dez = AGORA + timedelta(days=10)
    c = _reg(d, "c", dez)
    assert c["seq"] == 3 and (amb / "cobranca" / "COBRANCA_WEB_2026-12.jsonl").exists()
    d.confirmar(d.epoca(), 3, dez)
    est = json.loads((amb / "cobranca" / "estado.json").read_text(encoding="utf-8"))
    assert est["arquivos"]["COBRANCA_WEB_2026-11.jsonl"]["confirmado_em"] == "2026-12-04 15:00:00"
    d.confirmar(d.epoca(), 3, dez + timedelta(days=29))
    assert nov.exists()                                           # 30 dias ainda não passaram
    d.confirmar(d.epoca(), 3, dez + timedelta(days=31))
    assert not nov.exists()                                       # o arquivo some inteiro
    assert [r["seq"] for r in d.desde(0)["linhas"]] == [3]
    e = _reg(d, "e", dez + timedelta(days=32))
    assert e["seq"] == 4                                          # seq nunca reaproveitado


def test_diario_linha_nao_confirmada_nunca_e_apagada(amb):
    d = cobranca.Diario(amb)
    d.registrar(usuario="u", cliente="a", acao="PULADO", telefone="", em_atraso=1, titulos=1,
                pacote_sha="0" * 64, agora_=AGORA)
    d.registrar(usuario="u", cliente="b", acao="PULADO", telefone="", em_atraso=1, titulos=1,
                pacote_sha="0" * 64, agora_=AGORA + timedelta(days=90))
    assert [r["seq"] for r in d.desde(0)["linhas"]] == [1, 2]       # mês fechado, mas sem confirmação


def test_diario_sem_estado_cria_epoca_nova_e_segue_acima_do_maior_seq(amb):
    d = cobranca.Diario(amb)
    _reg(d, "a", AGORA)
    ep = d.epoca()
    (amb / "cobranca" / "estado.json").unlink()
    assert d.epoca() != ep
    assert _reg(d, "b", AGORA)["seq"] == 2
    d2 = cobranca.Diario(amb / "outro")                              # disco novo: recomeça em 1
    assert _reg(d2, "a", AGORA)["seq"] == 1


def test_diario_linha_json_valida_uma_por_linha(amb):
    d = cobranca.Diario(amb)
    d.registrar(usuario="u", cliente="a", acao="ENVIADO", telefone=FONE, em_atraso=1, titulos=1,
                pacote_sha="0" * 64, agora_=AGORA)
    linhas = (amb / "cobranca" / "COBRANCA_WEB_2026-11.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 1 and json.loads(linhas[0])["telefone"] == FONE


# ----------------------------------------------------------------- registro de acesso
def test_registro_de_acesso_sem_cliente_e_sem_telefone(admin):
    postar(admin, pacote_cobranca())
    _tela(admin, "cobrar")
    _acoes(admin, "000001-01", "ENVIADO", "(92) 98888-7777")
    texto = next((_dados(admin) / "acessos").glob("ACESSO_*.jsonl")).read_text(encoding="utf-8")
    regs = [json.loads(x) for x in texto.splitlines()]
    assert {"quando", "login", "rid", "aba", "acao"} == set(regs[-1])
    assert any(r["aba"] == "cobrar" and r["acao"] == "ver" for r in regs)
    assert any(r["acao"] == "ENVIADO" for r in regs)
    assert "000001" not in texto and "8887777" not in texto and FONE not in texto


def test_pacote_guardado_e_so_os_7_ultimos(cli, amb):
    for i in range(9):
        assert postar(cli, pacote_cobranca(gerado_em=f"2026-11-{i + 1:02d}T08:30:00-04:00")).status_code == 200
    assert len(list((amb / "pacotes").glob("*.json"))) == 7


def test_colunas_ocultas_vem_no_pacote_mas_nao_na_tela_e_marca_diferente_do_pc_recusa(admin, cli):
    postar(admin, pacote_cobranca())
    h = _tela(admin, "titulos").text
    assert "STATUS PROTHEUS" not in h and "SITUAÇÃO PLANNER" not in h and "STATUS</a>" in h
    p = pacote_cobranca()
    p["relatorios"]["pl_inadimplencia"]["tabelas"][0]["colunas"][10]["oculta"] = False
    _recusa(cli, p, "colunas diferentes")


def test_limpeza_roda_na_confirmacao_repetida_e_ao_subir(amb):
    d = cobranca.Diario(amb)
    _reg(d, "a", AGORA)
    ep = d.epoca()
    dez = AGORA + timedelta(days=10)
    d.confirmar(ep, 1, dez)                                  # nov fecha e é marcado
    nov = amb / "cobranca" / "COBRANCA_WEB_2026-11.jsonl"
    d.confirmar(ep, 1, dez + timedelta(days=31))             # mesma confirmação, repetida: limpa
    assert not nov.exists()
    _reg(d, "b", dez + timedelta(days=32))
    jan = amb / "cobranca" / "COBRANCA_WEB_2027-01.jsonl"
    assert jan.exists()
    d.limpar(dez + timedelta(days=100))                      # ao subir o app
    assert jan.exists()                                      # sem confirmação: fica


def _sem_status(p, quais=cobranca.STATUS_BLOCO):
    for tb in p["relatorios"]["pl_inadimplencia"]["tabelas"]:
        idx = [k for k, c in enumerate(tb["colunas"]) if c["nome"] in quais]
        for k in reversed(idx):
            del tb["colunas"][k]
            for ln in tb["linhas"]:
                del ln[k]
            if tb["total"]:
                del tb["total"][k]
        tb["filtros"] = [f for f in tb["filtros"] if (f if isinstance(f, str) else f["coluna"]) not in quais]
    return p


def test_colunas_de_status_opcionais_em_bloco(cli, admin):
    assert postar(cli, _sem_status(pacote_cobranca())).status_code == 200   # nenhuma das 3
    h = _tela(admin, "titulos").text
    assert "Cliente 001" in h and "VENCIMENTO" in h
    assert _tela(admin, "cliente").status_code == 200
    assert postar(cli, pacote_cobranca()).status_code == 200                # as 3 juntas
    for quais in (("STATUS",), ("STATUS PROTHEUS",), ("STATUS PROTHEUS", "SITUAÇÃO PLANNER"),
                  ("STATUS", "SITUAÇÃO PLANNER")):
        _recusa(cli, _sem_status(pacote_cobranca(), quais), "colunas diferentes")


def test_chip_vira_selo_nas_colunas_permitidas_e_valida_cor_e_coluna(admin, cli):
    p = pacote_cobranca()
    t = p["relatorios"]["pl_inadimplencia"]["tabelas"][0]
    t["colunas"][0]["chip"] = {"VENCIDO": ["#FDECEA", "#B3261E"]}
    t["tons"] = [""] * len(t["tons"])
    assert postar(admin, p).status_code == 200
    h = _tela(admin, "titulos").text
    assert 'class="selo" style="background:#FDECEA;color:#B3261E">VENCIDO' in h
    p["relatorios"]["pl_inadimplencia"]["tabelas"][0]["colunas"][0]["chip"] = {"VENCIDO": ["vermelho", "#000000"]}
    _recusa(cli, p, "colunas diferentes")
    p = pacote_cobranca()                                                    # chip em coluna fora das 3
    p["relatorios"]["pl_inadimplencia"]["tabelas"][0]["colunas"][1 + 2]["chip"] = {"x": ["#000000", "#FFFFFF"]}
    _recusa(cli, p, "colunas diferentes")


def test_larg_fixa_da_coluna_e_aceita(cli):
    p = pacote_cobranca()
    p["relatorios"]["pl_inadimplencia"]["tabelas"][0]["colunas"][0]["larg_fixa"] = 106
    assert postar(cli, p).status_code == 200
    p["relatorios"]["pl_inadimplencia"]["tabelas"][0]["colunas"][0]["larg_fixa"] = "x"
    _recusa(cli, p, "colunas diferentes")


def test_falha_ao_gravar_o_diario_devolve_503_json_e_nada_e_registrado(admin, monkeypatch):
    postar(admin, pacote_cobranca())

    def quebra(self, **kw):
        raise OSError("disco")
    with monkeypatch.context() as m:
        m.setattr(cobranca.Diario, "registrar", quebra)
        r = _acoes(admin, "000001-01", "ENVIADO")
    assert r.status_code == 503 and r.json()["ok"] is False and "gravar" in r.json()["erro"]
    assert cobranca.Diario(_dados(admin)).desde(0)["linhas"] == []
    assert _acoes(admin, "000001-01", "ENVIADO").status_code == 200          # o toque de novo grava


def test_js_da_fila_envia_ao_sair_guarda_pendente_e_so_confirma_com_ok_do_servidor(admin):
    js = admin.get("/static/cobranca.js").text
    for trecho in ("visibilitychange", "pagehide", "sessionStorage", "keepalive", "selo-erro",
                   "enviaTodos(true, card.dataset.cod)", "REGISTRANDO"):
        assert trecho in js, trecho
    # o selo "HOJE" só é escrito com a resposta do servidor (res[1].situacao), nunca no toque
    assert "' HOJE'" not in js and "res[1].situacao" in js


def test_tratados_acessivel_da_primeira_pagina(admin):
    postar(admin, pacote_cobranca())
    h = _tela(admin, "cobrar").text
    assert 'href="/farol/pl_inadimplencia?aba=cobrar&amp;pag=1#tratados">1 já tratados hoje</a>' in h
    assert 'id="tratados"' in h


def test_aviso_de_numero_repetido_diz_digitos_repetidos():
    assert cobranca.aviso_curto("telefone inválido (repetido)") == "Número com dígitos repetidos: digite o certo"


def test_limpeza_com_exatamente_30_dias_ja_apaga(amb):
    d = cobranca.Diario(amb)
    _reg(d, "a", AGORA)
    ep = d.epoca()
    dez = AGORA + timedelta(days=10)
    d.confirmar(ep, 1, dez)                                       # nov fecha; marcado em 04/12 15:00
    nov = amb / "cobranca" / "COBRANCA_WEB_2026-11.jsonl"
    d.confirmar(ep, 1, dez + timedelta(days=30) - timedelta(seconds=1))
    assert nov.exists()
    d.confirmar(ep, 1, dez + timedelta(days=30))                  # "30 dias ou mais" (§10.6.5)
    assert not nov.exists()


def test_chip_casa_sem_espacos_e_sem_diferenca_de_caixa(admin):
    p = pacote_cobranca()
    t = p["relatorios"]["pl_inadimplencia"]["tabelas"][0]
    t["colunas"][0]["chip"] = {" vencido ": ["#FDECEA", "#B3261E"]}
    postar(admin, p)
    assert 'class="selo" style="background:#FDECEA;color:#B3261E">VENCIDO' in _tela(admin, "titulos").text


def test_desde_com_digito_unicode_da_400_e_nao_500(admin):
    assert admin.get("/api/cobranca?desde=%C2%B2", headers=_h()).status_code == 400


def test_js_numero_espelha_o_celular_do_pc():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node")
    js = (Path(cobranca.__file__).parent / "static" / "cobranca.js").read_text(encoding="utf-8")
    ini = js.index("  function celular(v) {")
    fim = js.index("  function numero(card, link) {")
    casos = ["(92) 99999-1234", "092 3200-0002", "92 8888-1111", "92 99999-9999", "123", "", "5592999991234",
             "(92) 3200-0002 / (92) 99999-1234", "92 91234-5678 e 92 3200-0002", "0 92 98888-7777"]
    prog = js[ini:fim] + "\nconsole.log(JSON.stringify(" + json.dumps(casos) + ".map(celular)));"
    saida = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=30).stdout
    assert json.loads(saida) == [cobranca.celular(c) for c in casos]
