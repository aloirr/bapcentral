"""T-0023 v2: Garantias, Devoluções e NCC na web, com edição só do admin (contrato §10.9 e §10.10).

Perfis e 403 (RN-GER-014), edição só do admin (RN-GER-012), o ticket da garantia nova (§10.9.2), o contato fora
(P2 A, RN-GER-011), o texto livre (teto, dado pessoal e "[removido]") e o estado pela filial da nota (P3 A, RN-GER-006).
Dados 100% fictícios (posvenda_fixture): nenhum cliente, CNPJ ou telefone real.
"""
import json
import re
from pathlib import Path

import pytest

from conftest import TOKEN, postar, token_form
from posvenda_fixture import ETAPAS_D, N_G, farol_ncc, garantias_registros, pacote_posvenda
from app import edicoes, tabelas

H = {"Authorization": f"Bearer {TOKEN}"}
SENHA = "senha-teste-forte-9"
GAR = "/farol/pl_garantias?aba=garantias"
DEV = "/farol/pl_devolucoes?aba=devolucoes"
NCC = "/farol/pl_ncc?aba=pendentes"
RIDS = ("pl_garantias", "pl_devolucoes", "pl_ncc")


def _criar(admin, perfil):
    login = f"t23.{perfil}"
    r = admin.post("/usuarios", data={"acao": "criar", "login": login, "perfil": perfil,
                                      "senha": SENHA, "csrf": token_form(admin, "/usuarios")})
    assert r.status_code in (200, 303)
    return login


def _entrar_como(cli, login):
    cli.post("/sair", data={"csrf": token_form(cli, "/")})
    cli.post("/login", data={"usuario": login, "senha": SENHA, "csrf": token_form(cli, "/login")})
    cli.post("/senha", data={"atual": SENHA, "nova": "senha-teste-forte-10", "confirma": "senha-teste-forte-10",
                             "csrf": token_form(cli, "/senha")})


@pytest.fixture
def pv(admin):
    assert postar(admin, pacote_posvenda()).status_code == 200
    return admin


def _fila(amb):
    return [json.loads(x) for a in sorted((amb / "edicoes").glob("EDICOES_WEB_*.jsonl"))
            for x in a.read_text(encoding="utf-8").splitlines()]


def _link(html, n=0):
    return re.findall(r'class="bt-ed" href="([^"]+)"', html)[n].replace("&amp;", "&")


def _form(cli, url):
    html = cli.get(url).text
    campos = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html))
    return {k: v.replace("&amp;", "&") for k, v in campos.items()}, html


def _url_novo(pv):
    return re.search(r'href="(/farol/pl_garantias/editar\?[^"]*novo=1[^"]*)"', pv.get(GAR).text).group(1).replace("&amp;", "&")


# ------------------------------------------------------------------ pacote (§10.10.2)
def test_T0023_pacote_dos_3_farois_aceito_e_abas_na_ordem_do_pc(pv):
    """§10.10.1: Garantias 4 abas, Devoluções 5, NCC 5, na ordem do PC; a web aceita (200) o pacote."""
    assert [t for _, t in tabelas.ABAS["pl_garantias"]] == ["Garantias", "Histórico de compra", "Por produto", "Status x resultado"]
    assert len(tabelas.ABAS["pl_devolucoes"]) == 5 and len(tabelas.ABAS["pl_ncc"]) == 5
    for aba in ("garantias", "historico", "produto", "status"):
        assert pv.get(f"/farol/pl_garantias?aba={aba}").status_code == 200
    for aba in ("devolucoes", "motivo", "vendedor", "cliente", "produto"):
        assert pv.get(f"/farol/pl_devolucoes?aba={aba}").status_code == 200
    for aba in ("pendentes", "cliente", "filial", "vendedor", "supervisor"):
        assert pv.get(f"/farol/pl_ncc?aba={aba}").status_code == 200


def test_T0023_colunas_por_rid_e_titulo_nunca_so_pelo_titulo():
    """§10.10.1: "Por vendedor" existe no Visita e na NCC com colunas diferentes; vale (rid, título)."""
    ncc = [n for n, _, _ in tabelas.COLUNAS_RID[("pl_ncc", "Por vendedor")]]
    vis = [n for n, _, _ in tabelas.COLUNAS["Por vendedor"]]
    assert ncc[0] == "VENDEDOR" and "COMPENSAR JÁ" in ncc and ncc != vis


@pytest.mark.parametrize("estraga", [
    lambda f: f["tabelas"][0]["colunas"].append({"nome": "CONTATO CLIENTE", "tipo": "texto", "oculta": False}),
    lambda f: f["tabelas"][0]["colunas"].pop(),
])
def test_RN_GER_011_contato_da_garantia_recusado_no_pacote(admin, estraga):
    """P2 A: o CONTATO CLIENTE (nome e telefone) nunca vai ao site; coluna fora da lista do contrato = 400."""
    p = pacote_posvenda()
    estraga(p["relatorios"]["pl_garantias"])
    r = postar(admin, p)
    assert r.status_code == 422


@pytest.mark.parametrize("chave", ["garantia", "campanha_export", "detalhe_pedido"])
def test_RN_GER_011_chaves_que_nunca_vao_recusadas(admin, chave):
    """§10.10.3: `garantia`, `campanha_export` e `detalhe_pedido` ficam fora da lista branca do farol."""
    p = pacote_posvenda()
    p["relatorios"]["pl_garantias"][chave] = {"x": 1}
    assert postar(admin, p).status_code == 422


def test_RN_GER_012_campo_de_contato_na_edicao_recusado(admin):
    """P2 A: a edição da Garantia não tem campo de contato (o contato fica só no PC)."""
    p = pacote_posvenda()
    ed = p["relatorios"]["pl_garantias"]["tabelas"][0]["edicao"]
    ed["campos"].append({"campo": "contato_fone", "rotulo": "CONTATO CLIENTE", "coluna": None, "tipo": "texto", "opcoes": []})
    assert postar(admin, p).status_code == 422


def test_RN_GER_011_contato_nao_aparece_na_tela_nem_no_formulario(pv):
    for url in (GAR, _url_novo(pv)):
        h = pv.get(url).text.upper()
        assert "CONTATO" not in h and 'NAME="C_CONTATO' not in h and 'NAME="C_FONE' not in h


def test_T0023_numero_do_resumo_bate_com_a_aba(pv):
    """Item 2 da tarefa: o cartão do Resumo e o cartão da aba têm o mesmo texto, e batem com as linhas (RN-POS-005)."""
    reg = garantias_registros()
    em_aberto = sum(r["RESULTADO ANÁLISE"] == "PENDENTE" for r in reg)
    atrasadas = sum(r["PRAZO"] == "ATRASADA" for r in reg)
    resumo = pv.get("/farol/pl_garantias").text
    aba = pv.get(GAR).text
    for h in (resumo, aba):
        assert re.search(r"Em aberto\s*</[^>]+>\s*<[^>]+>\s*%d\b" % em_aberto, h) or f">{em_aberto}<" in h
    assert "Atrasadas" in resumo and "Atrasadas" in aba
    linhas_atrasadas = aba.split("<tbody>")[1].split("</tbody>")[0].count(">ATRASADA<")
    assert linhas_atrasadas == atrasadas == 3


# ------------------------------------------------------------------ RN-GER-014: quem vê
@pytest.mark.parametrize("rid", RIDS)
def test_RN_GER_014_diretor_so_o_resumo(admin, amb, rid):
    """Matriz: o diretor recebe 200 no Resumo e 403 em cada aba de tabela (e no Excel)."""
    assert postar(admin, pacote_posvenda()).status_code == 200
    _criar(admin, "diretor")
    _entrar_como(admin, "t23.diretor")
    assert admin.get(f"/farol/{rid}").status_code == 200
    for chave, _ in tabelas.ABAS[rid]:
        assert admin.get(f"/farol/{rid}?aba={chave}").status_code == 403
    assert admin.get(f"/farol/{rid}/exportar?aba={tabelas.ABAS[rid][0][0]}&formato=xlsx").status_code == 403


@pytest.mark.parametrize("perfil", ["vendas", "pre_venda"])
@pytest.mark.parametrize("rid", RIDS)
def test_RN_GER_014_outros_perfis_sem_o_farol(admin, perfil, rid):
    assert postar(admin, pacote_posvenda()).status_code == 200
    _criar(admin, perfil)
    _entrar_como(admin, f"t23.{perfil}")
    assert admin.get(f"/farol/{rid}").status_code == 403
    assert admin.get(f"/farol/{rid}?aba={tabelas.ABAS[rid][0][0]}").status_code == 403
    assert rid not in admin.get("/senha").text                       # nem na lateral


@pytest.mark.parametrize("perfil", ["gerente", "pos_venda"])
def test_RN_GER_012_pos_venda_e_gerente_veem_sem_editar(admin, amb, perfil):
    """Matriz: 200 nas abas, sem a coluna Editar e sem o "Nova garantia", e 403 no formulário de edição."""
    assert postar(admin, pacote_posvenda()).status_code == 200
    url_novo = _url_novo(admin)
    link = _link(admin.get(DEV).text)
    _criar(admin, perfil)
    _entrar_como(admin, f"t23.{perfil}")
    for url in (GAR, DEV, NCC):
        r = admin.get(url)
        assert r.status_code == 200 and 'class="bt-ed"' not in r.text and "Nova garantia" not in r.text
    assert admin.get(url_novo).status_code == 403
    assert admin.get(link).status_code == 403
    assert admin.post("/farol/pl_garantias/editar",
                      data={"tab": "Garantias", "novo": "1", "c_ticket": "G-0013", "c_cod_cliente": "9",
                            "csrf": token_form(admin, "/senha")}).status_code == 403
    assert not (amb / "edicoes").exists() or _fila(amb) == []


def test_RN_GER_012_admin_ve_editar_e_nova_garantia(pv):
    h = pv.get(GAR).text
    assert h.count('class="bt-ed"') == 2 * N_G and "Nova garantia" in h and h.count('class="bc3-bt bc3-bt-verde"') == 1
    assert 'class="bt-ed"' in pv.get(DEV).text and 'class="bt-ed"' in pv.get(NCC).text
    assert "Nova garantia" not in pv.get(DEV).text           # só a Garantia tem linha nova


# ------------------------------------------------------------------ RN-GER-006: estado pela filial da nota
def test_RN_GER_006_estado_das_devolucoes_e_da_ncc_pela_filial(pv):
    """P3 A: Devoluções e "NCC pendentes" filtram pelo estado da linha (a filial da nota)."""
    h_am = pv.get(DEV + "&uf=PA&f0=NOV%2F26").text
    h_tudo = pv.get(DEV).text
    assert h_am.count("<tr class") < h_tudo.count("<tr class")
    assert "FILIAL PA" not in h_am or "FILIAL AM" not in h_am.split("<tbody>")[1]
    ncc_pa = pv.get(NCC + "&uf=PA").text
    assert ncc_pa.count("<tr class") < pv.get(NCC).text.count("<tr class")


def test_RN_GER_006_garantias_e_ncc_por_cliente_sem_estado_com_aviso(pv):
    """Garantias e a "Por cliente" da NCC não têm a filial da nota: vão da BAP inteira, com o aviso."""
    assert "Sem filtro por estado" in pv.get("/farol/pl_garantias").text
    h = pv.get("/farol/pl_ncc?aba=cliente&uf=PA").text
    assert tabelas.AVISO_SEM_ESTADO in h and h.count("<tr class") == pv.get("/farol/pl_ncc?aba=cliente").text.count("<tr class")


# ------------------------------------------------------------------ tela: grade (tela-bc3 §6, §15)
def test_T0023_grade_com_10_colunas_ou_menos_e_chave_na_grade():
    p = pacote_posvenda()
    for rid in RIDS:
        for t in p["relatorios"][rid]["tabelas"]:
            visiveis = [c["nome"] for c in t["colunas"] if not c.get("oculta")]
            g = tabelas.GRADE.get((rid, t["titulo"]))
            if g is None:
                assert len(visiveis) <= 10, (rid, t["titulo"])       # fora da GRADE só com 10 colunas ou menos
                continue
            no_pacote = [n for n in g["grade"] if n in visiveis]
            assert len(no_pacote) <= 10 and g["chave"] in visiveis, (rid, t["titulo"])
            assert set(no_pacote) <= set(visiveis) and all(c in visiveis for c in g["cel"] if c)


def test_T0023_popup_nao_repete_a_grade_e_oculta_nao_vai_a_tela(pv):
    h = pv.get(GAR).text
    cab = h.split("<thead>")[1].split("</thead>")[0]
    assert "TICKET" in cab and "RECLAMAÇÃO" not in cab and "TOM SLA" not in cab and "PENDÊNCIAS" not in cab


# ------------------------------------------------------------------ linha nova da Garantia (§10.9.2)
def test_RN_GER_012_form_da_garantia_nova_traz_o_ticket_do_pacote_e_a_data_de_hoje(pv):
    """A web não calcula número: o ticket sugerido é o `padrao` do pacote; a data "@hoje" vira hoje em Manaus."""
    h = pv.get(_url_novo(pv)).text
    assert 'name="c_ticket" value="G-0013"' in h and 'name="p_ticket" value="G-0013"' in h
    assert f'name="c_dt_solicitacao" value="{edicoes.hoje_manaus().isoformat()}"' in h
    assert re.search(r'<option value="ABERTO" selected>', h) and re.search(r'<option value="PENDENTE" selected>', h)
    assert "<textarea" in h and 'maxlength="600"' in h and "CONTATO" not in h.upper()
    assert 'name="chave"' in h and 'value=""' in h


def test_RN_GER_012_garantia_nova_na_fila_com_antes_ticket(pv, amb):
    """§10.9.2: chave NOVO-xxxxxxxx, `novo: true`, `antes.ticket` = o padrão mostrado; só o que difere do padrão + ticket."""
    url = _url_novo(pv)
    campos, _ = _form(pv, url)
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_ticket="G-0013", c_cod_cliente="900123",
                                                         c_reclamacao="peça veio trocada", c_status="ABERTO"),
                follow_redirects=False)
    assert r.status_code == 303
    reg = _fila(amb)[-1]
    assert re.fullmatch(r"NOVO-[0-9A-F]{8}", reg["chave"]) and reg["novo"] is True
    assert reg["rid"] == "pl_garantias" and reg["modulo"] == "garantias" and reg["tabela"] == "Garantias"
    assert reg["antes"] == {"ticket": "G-0013"}
    assert reg["valores"] == {"cod_cliente": "900123", "reclamacao": "peça veio trocada", "ticket": "G-0013"}
    assert "status" not in reg["valores"] and "dt_solicitacao" not in reg["valores"]     # iguais ao padrão: não vão


def test_RN_GER_012_garantia_nova_sem_campo_alem_do_padrao_recusada(pv, amb):
    campos, _ = _form(pv, _url_novo(pv))
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_ticket="G-0013"))
    assert r.status_code == 400 and edicoes.MSG_NOVO_VAZIO in r.text
    assert not (amb / "edicoes").exists() or _fila(amb) == []


def test_RN_GER_012_ticket_digitado_diferente_do_padrao_vai_com_o_antes_do_padrao(pv, amb):
    """O robô compara com `antes.ticket`: o ticket digitado vai em `valores`, o padrão que o formulário mostrou em `antes`."""
    campos, _ = _form(pv, _url_novo(pv))
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_ticket="x-777"), follow_redirects=False)
    assert r.status_code == 303
    reg = _fila(amb)[-1]
    assert reg["valores"] == {"ticket": "X-777"} and reg["antes"] == {"ticket": "G-0013"}


def test_RN_GER_012_ticket_vazio_recusado(pv, amb):
    campos, _ = _form(pv, _url_novo(pv))
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_ticket="", c_cod_cliente="900123"))
    assert r.status_code == 400 and "obrigatório" in r.text
    assert not (amb / "edicoes").exists() or _fila(amb) == []


def test_T0023_linha_nova_aguardando_o_pc_na_aba_e_na_api_do_robo(pv, amb):
    """A contagem "N · Aguardando o PC" ao lado do botão, até chegar farol novo; a API do robô passa o `novo` sem mudança."""
    campos, _ = _form(pv, _url_novo(pv))
    for n in (1, 2):
        assert pv.post("/farol/pl_garantias/editar", data=dict(campos, c_ticket="G-0013", c_cod_cliente=f"90000{n}"),
                       follow_redirects=False).status_code == 303
    assert f"2 · {edicoes.MSG_AGUARDA}" in pv.get(GAR).text
    linhas = pv.get("/api/edicoes?desde=0", headers=H).json()["linhas"]
    assert len(linhas) == 2 and all(x["novo"] is True and x["antes"] == {"ticket": "G-0013"} for x in linhas)


def test_T0023_linha_nova_so_onde_o_pacote_traz_novo(pv):
    assert pv.get("/farol/pl_ncc/editar?tab=NCC+pendentes&novo=1").status_code == 404
    assert pv.get("/farol/pl_devolucoes/editar?tab=Devolu%C3%A7%C3%B5es&novo=1").status_code == 404
    p = pacote_posvenda()
    p["relatorios"]["pl_ncc"]["tabelas"][0]["edicao"]["novo"] = {"rotulo": "Nova NCC"}
    assert postar(pv, p).status_code == 422                           # `novo` fora dos lugares com linha nova


# ------------------------------------------------------------------ edição de linha (NCC e Devoluções)
def test_RN_GER_012_edicao_da_ncc_status_e_data_livre(pv, amb):
    html = pv.get(NCC).text
    campos, form = _form(pv, _link(html))
    hoje = edicoes.hoje_manaus()                                       # data livre: min/max = 2020 até hoje + 1 ano
    assert 'type="date"' in form and 'min="2020-01-01"' in form and f'max="{edicoes._mais_um_ano(hoje).isoformat()}"' in form
    base = dict(campos)
    r = pv.post("/farol/pl_ncc/editar", data=dict(base, c_dt_mov="2019-12-31"))
    assert r.status_code == 400 and "fora das permitidas" in r.text
    r = pv.post("/farol/pl_ncc/editar", data=dict(base, c_dt_mov="2099-01-01"))
    assert r.status_code == 400 and "fora das permitidas" in r.text
    r = pv.post("/farol/pl_ncc/editar", data=dict(base, c_status="OUTRA COISA"))
    assert r.status_code == 400 and "escolha uma opção" in r.text
    hoje = edicoes.hoje_manaus()
    r = pv.post("/farol/pl_ncc/editar", data=dict(base, c_status="CONTATAR CLIENTE", c_dt_mov=hoje.isoformat()),
                follow_redirects=False)
    assert r.status_code == 303
    reg = _fila(amb)[-1]
    assert reg["modulo"] == "ncc" and reg["valores"]["status"] == "CONTATAR CLIENTE"
    assert reg["valores"]["dt_mov"] == f"{hoje:%d/%m/%Y}" and "novo" not in reg and set(reg["antes"]) == {"status", "dt_mov"}
    assert "Aguardando o PC" in pv.get(NCC).text


def test_RN_GER_012_edicao_da_devolucao_os_7_campos(pv, amb):
    campos, form = _form(pv, _link(pv.get(DEV).text))
    for rot in ("ETAPA", "MOTIVO", "AUTORIZADO POR", "RECEBIDA EM", "FORMA DO CRÉDITO", "CRÉDITO EM", "RESPONSÁVEL"):
        assert rot in form
    r = pv.post("/farol/pl_devolucoes/editar", data=dict(campos, c_etapa=ETAPAS_D[2]), follow_redirects=False)
    assert r.status_code == 303
    assert _fila(amb)[-1]["modulo"] == "pos_venda" and _fila(amb)[-1]["valores"] == {"etapa": ETAPAS_D[2]}


def test_RN_GER_012_garantia_existente_edita_e_troca_o_ticket(pv, amb):
    campos, form = _form(pv, _link(pv.get(GAR).text))
    for rot in ("TICKET", "DT. SOLICITAÇÃO", "DT. FECHAMENTO (PRAZO)", "DT. RETORNO", "RESULTADO ANÁLISE", "RECLAMAÇÃO",
                "PENDÊNCIAS", "RETORNO DO CLIENTE", "OBSERVAÇÃO"):
        assert rot in form
    assert form.count("<textarea") == 4 and "CONTATO" not in form.upper()
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_ticket="g-0099", c_observacao="ligar na segunda"),
                follow_redirects=False)
    assert r.status_code == 303
    reg = _fila(amb)[-1]
    assert reg["valores"] == {"ticket": "G-0099", "observacao": "ligar na segunda"} and "novo" not in reg
    assert reg["chave"] == garantias_registros()[0]["TICKET"] and reg["antes"]["ticket"] == "G-0001"


# ------------------------------------------------------------------ texto livre (§10.9.1)
def _form_gar(pv):
    return _form(pv, _link(pv.get(GAR).text))[0]


def test_RN_GER_011_teto_do_texto_vem_do_pacote(pv, amb):
    """O `max` do pacote (600) vale: 600 passa, 601 não; o `maxlength` do navegador acompanha."""
    campos = _form_gar(pv)
    ok = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_observacao="a" * 600), follow_redirects=False)
    assert ok.status_code == 303
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_observacao="a" * 601))
    assert r.status_code == 400 and "até 600 caracteres" in r.text
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_cod_cliente="x" * 61))
    assert r.status_code == 400 and "até 60 caracteres" in r.text          # sem `max` no campo, o teto é 60


@pytest.mark.parametrize("texto", ["retorno no 92999998888", "retorno no 9233334444", "retorno no 33334444",
                                   "retorno no (92) 3333-4444", "fulano@exemplo.com", "CPF 123.456.789-00",
                                   "doc 12345678000190", "doc 12.345.678/0001-90"])
def test_RN_GER_011_dado_pessoal_no_texto_recusado(pv, amb, texto):
    """Telefone nos 3 tamanhos do padrão FONE (11, 10 e 8 dígitos), e-mail, CPF e CNPJ: recusados e fora da fila."""
    r = pv.post("/farol/pl_garantias/editar", data=dict(_form_gar(pv), c_observacao=texto))
    assert r.status_code == 400 and "sem CPF, CNPJ, telefone ou e-mail" in r.text
    assert not (amb / "edicoes").exists() or _fila(amb) == []


def test_RN_GER_011_valor_em_reais_nao_e_telefone(pv, amb):
    r = pv.post("/farol/pl_garantias/editar", data=dict(_form_gar(pv), c_observacao="crédito de R$ 12345678"),
                follow_redirects=False)
    assert r.status_code == 303 and _fila(amb)[-1]["valores"]["observacao"] == "crédito de R$ 12345678"


def test_RN_GER_011_texto_com_removido_nunca_volta_ao_pc(pv, amb):
    """§10.9.1, regra 4: o texto que voltou com "[removido]" é recusado; o original do PC nunca é trocado pelo limpo."""
    r = pv.post("/farol/pl_garantias/editar", data=dict(_form_gar(pv), c_observacao="ligar no [removido] amanhã"))
    assert r.status_code == 400 and "tire o" in r.text and "[removido]" in r.text and "escreva o texto de novo" in r.text
    assert not (amb / "edicoes").exists() or _fila(amb) == []


def test_RN_GER_011_removido_nao_mudado_nao_bloqueia_outro_campo(admin, amb):
    """O valor de hoje já veio limpo do PC: se a pessoa não mexeu nele, ele não vai, e outro campo segue sendo editado."""
    p = pacote_posvenda()
    t = p["relatorios"]["pl_garantias"]["tabelas"][0]
    i = [c["nome"] for c in t["colunas"]].index("OBSERVAÇÃO")
    t["linhas"][0][i] = "ligar no [removido]"
    assert postar(admin, p).status_code == 200
    link = _link(admin.get(GAR).text)
    campos, form = _form(admin, link)
    assert "ligar no [removido]" in form
    # o navegador reenvia o texto como está; a web não o manda ao PC
    r = admin.post("/farol/pl_garantias/editar", data=dict(campos, c_observacao="ligar no [removido]",
                                                           c_pendencias="aguardando foto nova"), follow_redirects=False)
    assert r.status_code == 303
    assert _fila(amb)[-1]["valores"] == {"pendencias": "aguardando foto nova"}


def test_T0023_max_do_pacote_acima_de_600_recusado(admin):
    p = pacote_posvenda()
    p["relatorios"]["pl_garantias"]["tabelas"][0]["edicao"]["campos"][-1]["max"] = 601
    assert postar(admin, p).status_code == 422


def test_T0023_multilinha_so_em_texto_com_caixa(admin):
    p = pacote_posvenda()
    p["relatorios"]["pl_garantias"]["tabelas"][0]["edicao"]["campos"][-1]["caixa"] = False
    assert postar(admin, p).status_code == 422


def test_T0023_quebra_de_linha_so_na_multilinha(pv, amb):
    campos = _form_gar(pv)
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_observacao="linha 1\r\nlinha 2"), follow_redirects=False)
    assert r.status_code == 303 and _fila(amb)[-1]["valores"]["observacao"] == "linha 1\nlinha 2"
    r = pv.post("/farol/pl_garantias/editar", data=dict(campos, c_cod_cliente="9\n1"))
    assert r.status_code == 400 and "valor inválido" in r.text           # campo de uma linha: quebra é controle


def test_RN_GER_012_perfil_nao_edita_nem_com_csrf_certo(admin, amb):
    assert postar(admin, pacote_posvenda()).status_code == 200
    link = _link(admin.get(NCC).text)
    _criar(admin, "pos_venda")
    _entrar_como(admin, "t23.pos_venda")
    r = admin.post("/farol/pl_ncc/editar", data={"tab": "NCC pendentes", "chave": "0101001|001|901|01",
                                                 "c_status": "COMPENSADA", "csrf": token_form(admin, "/senha")})
    assert r.status_code == 403 and admin.get(link).status_code == 403
    assert not (amb / "edicoes").exists() or _fila(amb) == []


# ------------------------------------------------------------------ dado pessoal: a cópia do padrão é a do contrato
def test_RN_GER_011_padroes_pessoais_da_web_iguais_ao_bloco_do_contrato():
    """§10.9.1: `edicoes.RE_PESSOAL` tem os mesmos padrões do bloco `padroes-pessoais` do contrato."""
    texto = (Path(__file__).resolve().parents[2] / ".coord" / "contratos" / "relatorio.md").read_text(encoding="utf-8")
    bloco = re.search(r"```text padroes-pessoais\n(.*?)```", texto, re.S).group(1)
    pad = dict(ln.strip().split(" ", 1) for ln in bloco.strip().splitlines())
    web = {"EMAIL": edicoes.RE_EMAIL, "DOC_MEIO": edicoes.RE_DOC_MEIO, "DOC_SOLTO": edicoes.RE_DOC_SOLTO,
           "FONE": edicoes.RE_FONE, "VALOR_RS": edicoes.RE_VALOR_RS}
    assert set(pad) == set(web)
    for nome, rx in web.items():
        assert rx.pattern == pad[nome], nome
    assert set(edicoes.RE_PESSOAL) == {web["EMAIL"], web["DOC_MEIO"], web["DOC_SOLTO"], web["FONE"]}


def test_RN_GER_011_json_guardado_sem_contato_nem_padrao_pessoal(pv, amb):
    """§10.10.3: no JSON dos 3 faróis não há `CONTATO CLIENTE`, nem as chaves proibidas, nem CPF/CNPJ/e-mail."""
    import gzip
    lote = sorted(d for d in (amb / "pacotes").iterdir() if (d / "indice.json").is_file())[-1]
    for a in lote.glob("*.json.gz"):
        txt = gzip.open(a, "rb").read().decode("utf-8")
        assert "CONTATO CLIENTE" not in txt and "TELEFONE" not in txt
        for k in ('"garantia"', '"campanha_export"', '"detalhe_pedido"'):
            assert k not in txt
        assert not edicoes.RE_EMAIL.search(txt) and not edicoes.RE_DOC_MEIO.search(txt)


# ------------------------------------------------------------------ o pacote de verdade (NCC com estado, tetos)
def test_T0023_ncc_estados_do_cartao_e_cartoes_por_estado(pv):
    f = farol_ncc()
    assert f["kpis"][0]["estados"]["barras"] and set(f["recortes"]) <= {"AM", "PA", "MA", "RR", "MT"}
    r = pv.get("/farol/pl_ncc?uf=PA")
    assert r.status_code == 200 and "Saldo a compensar" in r.text


def test_T0023_versao_da_web(admin):
    assert admin.get("/saude").json()["versao"] == "0.8.1"


def test_T0023_formulario_aceita_ate_32kb():
    from app import main
    assert main.FORM_MAX == 32 * 1024


# ------------------------------------------------------------------ correções da revisão (head 3cc4fe0)
def test_RN_GER_012_texto_sem_caixa_com_minuscula_reenviado_sem_mudar_da_nada_mudou(admin, amb):
    """Revisão 🟡 1: a comparação é nos 2 lados no mesmo formato. Valor digitado no PC com minúscula, campo sem `caixa`:
    reenviar sem mexer dá "Nada mudou", e editar outro campo não carrega o `cod_cliente`."""
    p = pacote_posvenda()
    t = p["relatorios"]["pl_garantias"]["tabelas"][0]
    t["linhas"][0][[c["nome"] for c in t["colunas"]].index("CÓD. CLIENTE")] = "ab123"
    assert postar(admin, p).status_code == 200
    campos, form = _form(admin, _link(admin.get(GAR).text))
    assert "ab123" in form
    r = admin.post("/farol/pl_garantias/editar", data=dict(campos, c_cod_cliente="ab123"))
    assert r.status_code == 200 and "Nada mudou" in r.text
    assert not (amb / "edicoes").exists() or _fila(amb) == []
    r = admin.post("/farol/pl_garantias/editar", data=dict(campos, c_cod_cliente="ab123", c_pendencias="foto nova"),
                   follow_redirects=False)
    assert r.status_code == 303 and _fila(amb)[-1]["valores"] == {"pendencias": "foto nova"}


def test_RN_GER_011_removido_em_maiuscula_tambem_recusado(pv, amb):
    r = pv.post("/farol/pl_garantias/editar", data=dict(_form_gar(pv), c_cod_cliente="x [REMOVIDO] y"))
    assert r.status_code == 400 and "escreva o texto de novo" in r.text
    assert not (amb / "edicoes").exists() or _fila(amb) == []


def test_RN_GER_012_linha_nova_volta_do_erro_com_datas_e_ticket_mostrado(pv, amb):
    """Revisão 🟡 2: depois de um 400 a tela traz a data (ISO do navegador) e o `p_ticket` que foi enviado; o reenvio
    corrigido não leva `dt_solicitacao` em `valores` e mantém o `antes.ticket` do formulário original (pacote atrasado)."""
    campos, _ = _form(pv, _url_novo(pv))
    hoje = edicoes.hoje_manaus().isoformat()
    enviado = dict(campos, c_ticket="", c_cod_cliente="900123", p_ticket="G-0007", c_dt_solicitacao=hoje)
    r = pv.post("/farol/pl_garantias/editar", data=enviado)
    assert r.status_code == 400 and "obrigatório" in r.text
    assert f'name="c_dt_solicitacao" value="{hoje}"' in r.text and 'name="p_ticket" value="G-0007"' in r.text
    volta = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', r.text))
    assert volta["p_ticket"] == "G-0007"
    ok = pv.post("/farol/pl_garantias/editar", data=dict(volta, c_ticket="G-0013", c_cod_cliente="900123",
                                                          c_dt_solicitacao=hoje, c_status="ABERTO", c_resultado="PENDENTE"),
                 follow_redirects=False)
    assert ok.status_code == 303
    reg = _fila(amb)[-1]
    assert "dt_solicitacao" not in reg["valores"] and reg["antes"] == {"ticket": "G-0007"}


def test_T0023_edicao_diz_qual_linha_e_sugestao_so_quando_o_ticket_mudou(pv):
    """UX A3 e RD-0144: a NCC mostra "NCC 901 · NOME · UF" (a GRADE), e a sugestão do ticket não repete o campo."""
    _, form = _form(pv, _link(pv.get(NCC).text))
    assert "NCC 901 · CLIENTE FICTICIO 01 · PA" in form
    novo = pv.get(_url_novo(pv)).text
    assert "Sugestão do PC" not in novo and "linha nova" not in novo and novo.count("sem CPF, CNPJ, telefone ou e-mail") == 1


def test_T0023_devolucoes_grade_so_o_nome_do_cliente_e_codigo_no_popup(pv):
    """UX A7: a coluna CLIENTE da grade não leva o código ("900001 - NOME"); o código vai ao popup."""
    h = pv.get(DEV).text
    corpo = h.split("<tbody>")[1].split("</tbody>")[0]
    assert "CLIENTE FICTICIO 01" in corpo and "900001 - CLIENTE" not in corpo
    assert "900001" in h
