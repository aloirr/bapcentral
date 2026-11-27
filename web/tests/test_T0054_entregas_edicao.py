"""T-0054 (RN-POS-011, contrato §10.9.7): o pós-venda edita o Farol de Entregas no site; os outros perfis não.

Dados 100% fictícios. RN-GER-018: o farol liberado a outro perfil não dá edição.
"""
import json
import re

import pytest
from conftest import postar, token_form
from edicao_fixture import pacote_editavel
from test_farois import _usuario

from app import acesso, edicoes

URL_ENT = "/farol/pl_entregas?aba=entregas"
PEND = "Pendências dos meses anteriores"


@pytest.fixture
def ped(admin):
    assert postar(admin, pacote_editavel()).status_code == 200
    return admin


def _links(html):
    return [x.replace("&amp;", "&") for x in re.findall(r'class="bt-ed" href="([^"]+)"', html)]


def _link(html, n=0):
    return _links(html)[n]


def _form(c, url):
    html = c.get(url).text
    campos = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html))
    return {k: v.replace("&amp;", "&") for k, v in campos.items()}


def _fila(amb):
    return [json.loads(x) for a in sorted((amb / "edicoes").glob("EDICOES_WEB_*.jsonl"))
            for x in a.read_text(encoding="utf-8").splitlines()]


def _fila_vazia(amb):
    return not (amb / "edicoes").exists() or _fila(amb) == []


def test_RN_POS_011_pode_criar():
    lugar = ("pl_entregas", "x")
    assert edicoes.pode_criar("admin", lugar)
    assert not edicoes.pode_criar("pos_venda", lugar)
    assert not edicoes.pode_criar("gerente", lugar)


def test_RN_POS_011_tabela_e_pode_editar():
    for t in ("Entregas", PEND):
        assert edicoes.pode_editar("admin", ("pl_entregas", t)) and edicoes.pode_editar("pos_venda", ("pl_entregas", t))
        for p in ("gerente", "analista", "diretor", "pre_venda", "vendas", "trade"):
            assert not edicoes.pode_editar(p, ("pl_entregas", t))
    # o resto continua só do admin (RN-GER-012)
    for lugar in (("pv_pedidos", "Pedidos"), ("pl_ncc", "NCC pendentes"), ("pl_devolucoes", "Devoluções"),
                  ("pl_garantias", "Garantias")):
        assert edicoes.pode_editar("admin", lugar) and not edicoes.pode_editar("pos_venda", lugar)
    assert edicoes.EDITA == ("admin",)


def test_RN_POS_011_pos_venda_ve_botao_edita_e_a_fila_leva_o_perfil(ped, amb):
    c = _usuario(ped, "t54.posvenda", "pos_venda")
    html = c.get(URL_ENT).text
    assert 'class="bt-ed"' in html and ">Editar</th>" in html
    link = _link(html)
    assert c.get(link).status_code == 200
    campos = _form(c, link)
    r = c.post("/farol/pl_entregas/editar", data=dict(campos, csrf=token_form(c, "/senha"), c_etapa="ENTREGUE",
                                                      c_responsavel="motorista teste"), follow_redirects=False)
    assert r.status_code == 303
    reg = _fila(amb)[-1]
    assert reg["perfil"] == "pos_venda" and reg["usuario"] == "t54.posvenda" and reg["modulo"] == "pos_venda"
    assert reg["valores"]["etapa"] == "ENTREGUE" and reg["valores"]["responsavel"] == "MOTORISTA TESTE"
    assert "Aguardando o PC" in c.get(URL_ENT).text


def test_RN_POS_011_pos_venda_edita_pendencias(ped, amb):
    c = _usuario(ped, "t54.posvenda", "pos_venda")
    links = _links(c.get(URL_ENT).text)
    pend = [x for x in links if "Pend" in x]
    assert pend
    campos = _form(c, pend[0])
    r = c.post("/farol/pl_entregas/editar", data=dict(campos, csrf=token_form(c, "/senha"), c_etapa="CANCELADA"),
               follow_redirects=False)
    assert r.status_code == 303 and _fila(amb)[-1]["tabela"] == PEND


def test_RN_POS_011_admin_grava_o_perfil_admin(ped, amb):
    campos = _form(ped, _link(ped.get(URL_ENT).text))
    r = ped.post("/farol/pl_entregas/editar", data=dict(campos, c_etapa="CANCELADA"), follow_redirects=False)
    assert r.status_code == 303 and _fila(amb)[-1]["perfil"] == "admin"


@pytest.mark.parametrize("perfil", ["gerente", "analista", "diretor"])
def test_RN_POS_011_outros_perfis_sem_edicao_403(ped, amb, perfil):
    link = _link(ped.get(URL_ENT).text)
    campos = _form(ped, link)
    c = _usuario(ped, "t54." + perfil, perfil)
    html = c.get(URL_ENT).text
    assert 'class="bt-ed"' not in html and "ed-col" not in html
    assert c.get(link).status_code == 403
    r = c.post("/farol/pl_entregas/editar", data=dict(campos, csrf=token_form(c, "/senha"), c_etapa="CANCELADA"))
    assert r.status_code == 403
    assert _fila_vazia(amb)


def test_RN_POS_011_pos_venda_continua_sem_edicao_nos_outros_lugares(ped, amb):
    link = re.search(r'href="(/farol/pv_pedidos/editar[^"]*)"', ped.get("/farol/pv_pedidos?aba=pedidos").text)
    link = link.group(1).replace("&amp;", "&")
    campos = _form(ped, link)
    c = _usuario(ped, "t54.posvenda", "pos_venda")
    assert c.get(link).status_code == 403
    assert c.post("/farol/pv_pedidos/editar", data=dict(campos, csrf=token_form(c, "/senha"))).status_code == 403
    # a tabela de outro lugar apontada no farol que o pós-venda edita: 403 também
    campos = _form(ped, _link(ped.get(URL_ENT).text))
    r = c.post("/farol/pl_entregas/editar", data=dict(campos, csrf=token_form(c, "/senha"), tab="Garantias"))
    assert r.status_code == 403
    assert _fila_vazia(amb)


def test_RN_GER_018_farol_liberado_nao_da_edicao(ped, amb):
    link = _link(ped.get(URL_ENT).text)
    campos = _form(ped, link)
    c = _usuario(ped, "t54.vendas", "vendas")
    assert c.get("/farol/pl_entregas").status_code == 403             # sem a exceção, nem vê
    r = ped.post("/usuarios", data={"acao": "acesso", "login": "t54.vendas", "lista": "1", "farol": sorted(acesso.padrao_do_perfil("vendas") | {"pl_entregas"}),
                                    "csrf": token_form(ped, "/usuarios")})
    assert r.status_code == 200
    html = c.get("/farol/pl_entregas")                              # só o Resumo: a tabela não é do perfil
    assert html.status_code == 200 and 'class="bt-ed"' not in html.text and "ed-col" not in html.text
    assert c.get(link).status_code == 403
    assert c.post("/farol/pl_entregas/editar", data=dict(campos, csrf=token_form(c, "/senha"))).status_code == 403
    assert _fila_vazia(amb)


def test_RN_POS_011_formulario_diz_a_nota_e_o_cliente(ped):
    c = _usuario(ped, "t54.posvenda", "pos_venda")
    html = c.get(_link(c.get(URL_ENT).text)).text
    m = re.search(r'<p class="ed-resumo">([^<]+)</p>', html)
    assert m and re.match(r"NF \d+ · CLIENTE TESTE \d+ · [A-Z]{2}$", m.group(1).replace("FICTICIO", "TESTE"))


def test_RN_POS_011_erro_devolve_o_digitado_e_marca_so_o_campo_recusado(ped, amb):
    c = _usuario(ped, "t54.posvenda", "pos_venda")
    link = _link(c.get(URL_ENT).text)
    campos = _form(c, link)
    r = c.post("/farol/pl_entregas/editar", data=dict(campos, csrf=token_form(c, "/senha"), c_etapa="ENTREGUE",
                                                      c_frete_real="321,00", c_responsavel="FULANO 123.456.789-00"))
    assert r.status_code == 400 and "sem CPF" in r.text
    assert 'value="321,00"' in r.text and '<option value="ENTREGUE" selected>' in r.text
    assert "123.456.789-00" not in r.text.split('class="erro"')[1].split("</p>")[1]   # o CPF não volta no campo
    assert r.text.count('aria-invalid="true"') == 1
    assert re.search(r'<input type="text" aria-invalid="true" name="c_responsavel" value=""', r.text)
    assert _fila_vazia(amb)


def test_RN_POS_011_dica_da_data_calculada_so_na_prevista(ped):
    html = ped.get(_link(ped.get(URL_ENT).text)).text
    assert html.count("Apague a data para voltar") == 1


def test_RN_POS_010_notas_com_frete_pos_venda_edita_gerente_nao():
    lugar = ("pl_fretes", "Notas com frete")
    assert edicoes.pode_editar("admin", lugar) and edicoes.pode_editar("pos_venda", lugar)
    for p in ("gerente", "analista", "diretor", "pre_venda", "vendas", "trade"):
        assert not edicoes.pode_editar(p, lugar)
    assert "pos_venda" in edicoes.perfis_do_rid("pl_fretes")


def test_RN_POS_010_lugar_ainda_fora_de_LUGARES_nao_quebra(ped):
    c = _usuario(ped, "t54.posvenda", "pos_venda")        # no main o Fretes não tem edição: 403/404, nunca 500
    assert c.get("/farol/pl_fretes/editar?tab=Notas+com+frete&chave=x").status_code in (403, 404)


def test_RN_POS_011_linha_nova_so_do_admin(ped, amb):
    c = _usuario(ped, "t54.posvenda", "pos_venda")
    url = "/farol/pl_entregas/editar?tab=Entregas&novo=1"
    assert c.get(url).status_code == 403
    assert ped.get(url).status_code == 404                # o admin passa do perfil; sem `edicao.novo` no pacote, 404
    r = c.post("/farol/pl_entregas/editar", data={"csrf": token_form(c, "/senha"), "tab": "Entregas", "novo": "1"})
    assert r.status_code == 403
    assert _fila_vazia(amb)
