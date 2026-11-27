"""T-0021: edição do Farol de Pedidos (autorização) e do Farol de Entregas (a linha) na web, só admin.

Fila só de acréscimo, permissão (botão só do admin, 403 nos outros), CSRF, API do robô (Bearer),
validação do pacote e o clique no pedido que filtra as tabelas de baixo. Dados fictícios.
"""
import json
import re
import time
from urllib.parse import parse_qs, urlparse

import pytest

from conftest import TOKEN, postar, token_form
from edicao_fixture import pacote_editavel
from app import edicoes

H = {"Authorization": f"Bearer {TOKEN}"}
URL_PED = "/farol/pv_pedidos?aba=pedidos"
URL_ENT = "/farol/pl_entregas?aba=entregas"


def _criar(admin, perfil):
    login = f"t21.{perfil}"
    admin.post("/usuarios", data={"acao": "criar", "login": login, "perfil": perfil,
                                  "senha": "senha-teste-forte-9", "csrf": token_form(admin, "/usuarios")})
    return login


def _entrar_como(cli, login):
    cli.post("/sair", data={"csrf": token_form(cli, "/")})
    cli.post("/login", data={"usuario": login, "senha": "senha-teste-forte-9", "csrf": token_form(cli, "/login")})
    cli.post("/senha", data={"atual": "senha-teste-forte-9", "nova": "senha-teste-forte-10",
                             "confirma": "senha-teste-forte-10", "csrf": token_form(cli, "/senha")})


@pytest.fixture
def ped(admin):
    assert postar(admin, pacote_editavel()).status_code == 200
    return admin


def _link_editar(html, n=0):
    links = re.findall(r'class="bt-ed" href="([^"]+)"', html)
    return links[n].replace("&amp;", "&")


def _form(cli, url):
    html = cli.get(url).text
    campos = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html))
    return {k: v.replace("&amp;", "&") for k, v in campos.items()}, html


def _linhas_fila(amb):
    return [json.loads(x) for a in sorted((amb / "edicoes").glob("EDICOES_WEB_*.jsonl"))
            for x in a.read_text(encoding="utf-8").splitlines()]


# ------------------------------------------------------------------ pacote
def test_pacote_com_edicao_aceito(admin):
    assert postar(admin, pacote_editavel()).status_code == 200


@pytest.mark.parametrize("estraga, onde", [
    (lambda t: t["edicao"]["chaves"].pop(), "chaves"),
    (lambda t: t["edicao"].update(modulo="ncc"), "modulo"),
    (lambda t: t["edicao"]["campos"][0].update(coluna="TELEFONE"), "coluna"),
    (lambda t: t["edicao"].update(arquivo="RELATORIOS/x.xlsx"), "chave"),
    (lambda t: t["edicao"]["campos"].append(dict(t["edicao"]["campos"][0])), "repetido"),
])
def test_pacote_com_edicao_torta_recusado(admin, estraga, onde):
    p = pacote_editavel()
    estraga(p["relatorios"]["pv_pedidos"]["tabelas"][0])
    r = postar(admin, p)
    assert r.status_code == 422, onde


def test_edicao_fora_dos_lugares_recusada(admin):
    p = pacote_editavel()
    sol = p["relatorios"]["pv_pedidos"]["tabelas"][1]          # Solicitação BAP não edita na web
    sol["edicao"] = {"modulo": "autorizacoes", "chaves": [], "campos": []}
    assert postar(admin, p).status_code == 422
    p = pacote_editavel()
    p["relatorios"]["pv_pedidos"]["edicao"] = {}                # no farol (fora da tabela): proibida
    assert postar(admin, p).status_code == 422


def test_data_fora_do_formato_recusada(admin):
    p = pacote_editavel()
    p["relatorios"]["pl_entregas"]["tabelas"][0]["edicao"]["campos"][2]["opcoes"] = ["2026-11-24"]
    assert postar(admin, p).status_code == 422


# ------------------------------------------------------------------ permissão e CSRF
def test_admin_ve_botao_e_os_outros_nao(ped, cli):
    html = ped.get(URL_PED).text
    assert 'class="bt-ed"' in html and ">Autorização</th>" in html
    assert 'class="bt-ed"' in ped.get(URL_ENT).text
    for perfil, url in (("pre_venda", URL_PED), ("gerente", URL_PED)):  # T-0054: o pós-venda edita as Entregas (test_T0054_*)
        login = _criar(ped, perfil)
        _entrar_como(cli, login)
        html = cli.get(url).text
        assert cli.get(url).status_code == 200
        assert 'class="bt-ed"' not in html and "ed-col" not in html
        cli.post("/sair", data={"csrf": token_form(cli, "/")})
        cli.post("/login", data={"usuario": "admin.teste", "senha": "nova-senha-forte-1",
                                 "csrf": token_form(cli, "/login")})


def test_get_e_post_de_outro_perfil_403(ped, cli):
    link = _link_editar(ped.get(URL_PED).text)
    campos, _ = _form(ped, link)
    login = _criar(ped, "pre_venda")
    _entrar_como(cli, login)
    assert cli.get(link).status_code == 403
    d = dict(campos, csrf=token_form(cli, "/senha"), c_por="PRICE")
    assert cli.post("/farol/pv_pedidos/editar", data=d).status_code == 403


def test_post_sem_csrf_403_e_nada_gravado(ped, amb):
    campos, _ = _form(ped, _link_editar(ped.get(URL_PED).text))
    d = dict(campos, c_por="PRICE")
    d.pop("csrf")
    assert ped.post("/farol/pv_pedidos/editar", data=d).status_code == 403
    d["csrf"] = "errado"
    assert ped.post("/farol/pv_pedidos/editar", data=d).status_code == 403
    assert not (amb / "edicoes").exists() or _linhas_fila(amb) == []


def test_sem_login_vai_ao_login(cli):
    r = cli.get("/farol/pv_pedidos/editar?tab=Pedidos&chave=CH0001", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


# ------------------------------------------------------------------ fluxo do admin
def test_autorizacao_fila_e_marca(ped, amb):
    link = _link_editar(ped.get(URL_PED).text)
    campos, html = _form(ped, link)
    assert 'name="c_codigo"' in html and 'name="c_por"' in html and "Ver pedido" in html
    r = ped.post("/farol/pv_pedidos/editar", data=dict(campos, c_codigo="Ab-123", c_por="PRICE"),
                 follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/farol/pv_pedidos?aba=pedidos") and r.headers["location"].endswith("ed=1")
    fila = _linhas_fila(amb)
    assert len(fila) == 1
    reg = fila[0]
    assert reg["tipo"] == "edicao" and reg["seq"] == 1 and reg["modulo"] == "autorizacoes"
    assert reg["tabela"] == "Pedidos" and reg["chave"] == campos["chave"]
    assert reg["valores"] == {"codigo": "Ab-123", "por": "PRICE"}            # o código mantém a caixa (PC)
    pag = ped.get(r.headers["location"]).text
    assert edicoes.MSG_ENVIADA in pag
    assert "Aguardando o PC" in pag


def test_entregas_campos_datas_e_grupo(ped, amb):
    html = ped.get(URL_ENT).text
    assert 'class="ed-nao"' in html                       # a linha sem chave (anterior a 01/10/2026)
    campos, form = _form(ped, _link_editar(html))
    assert 'type="date"' in form and 'min="2026-11-' in form
    assert "TRANSPORTADORA FICTICIA" in form
    base = dict(campos)
    # transportadora fora das opções da cidade da linha
    r = ped.post("/farol/pl_entregas/editar", data=dict(base, c_transportadora="OUTRA"))
    assert r.status_code == 400 and "escolha uma opção" in r.text
    r = ped.post("/farol/pl_entregas/editar", data=dict(base, c_entregue_em="2025-01-01"))
    assert r.status_code == 400 and "fora das permitidas" in r.text
    r = ped.post("/farol/pl_entregas/editar", data=dict(base, c_responsavel="FULANO 123.456.789-00"))
    assert r.status_code == 400 and "sem CPF" in r.text
    r = ped.post("/farol/pl_entregas/editar", data=dict(base, c_frete_real="abc"))
    assert r.status_code == 400 and "não é um valor" in r.text
    assert not (amb / "edicoes").exists() or _linhas_fila(amb) == []
    r = ped.post("/farol/pl_entregas/editar", data=dict(
        base, c_etapa="ENTREGUE", c_entregue_em="2026-11-23", c_responsavel="motorista novo",
        c_frete_real="1.234,5"), follow_redirects=False)
    assert r.status_code == 303
    reg = _linhas_fila(amb)[-1]
    assert reg["modulo"] == "pos_venda"
    assert reg["valores"] == {"etapa": "ENTREGUE", "entregue_em": "23/11/2026",
                              "responsavel": "MOTORISTA NOVO", "frete_real": "1234,50"}


def test_nada_mudou_nao_grava(ped, amb):
    campos, _ = _form(ped, _link_editar(ped.get(URL_ENT).text))
    r = ped.post("/farol/pl_entregas/editar", data=campos)
    assert r.status_code == 200 and "Nada mudou." in r.text
    assert not (amb / "edicoes").exists() or _linhas_fila(amb) == []


def test_pendencias_dos_meses_anteriores_editam(ped, amb):
    html = ped.get(URL_ENT).text
    links = [x.replace("&amp;", "&") for x in re.findall(r'class="bt-ed" href="([^"]+)"', html)]
    pend = [x for x in links if "Pend" in parse_qs(urlparse(x).query)["tab"][0]]
    assert pend
    campos, _ = _form(ped, pend[0])
    r = ped.post("/farol/pl_entregas/editar", data=dict(campos, c_etapa="CANCELADA"), follow_redirects=False)
    assert r.status_code == 303
    assert _linhas_fila(amb)[-1]["tabela"] == "Pendências dos meses anteriores"


def test_volta_de_fora_vira_o_farol(ped):
    campos, _ = _form(ped, _link_editar(ped.get(URL_PED).text))
    r = ped.post("/farol/pv_pedidos/editar", data=dict(campos, c_por="PRICE", volta="https://fora.example/x"),
                 follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/farol/pv_pedidos?ed=1"


def test_linha_que_saiu_do_pacote(ped):
    r = ped.get("/farol/pv_pedidos/editar?tab=Pedidos&chave=NAO-EXISTE")
    assert r.status_code == 404 and "Linha não encontrada" in r.text


# ------------------------------------------------------------------ API do robô
def _editar_uma(ped):
    campos, _ = _form(ped, _link_editar(ped.get(URL_PED).text))
    ped.post("/farol/pv_pedidos/editar", data=dict(campos, c_por="ALEXANDRE"))
    return campos["chave"]


def test_api_token(ped):
    assert ped.get("/api/edicoes?desde=0").status_code == 401
    assert ped.get("/api/edicoes?desde=0", headers={"Authorization": "Bearer errado"}).status_code == 401
    assert ped.post("/api/edicoes/confirmar", json={}).status_code == 401
    assert ped.get("/api/edicoes?desde=-1", headers=H).status_code == 400


def test_api_lista_confirma_e_marca(ped, cli):
    chave = _editar_uma(ped)
    d = ped.get("/api/edicoes?desde=0", headers=H).json()
    assert d["ate_seq"] == 1 and d["mais"] is False
    (ln,) = d["linhas"]
    assert ln["status"] == "pendente" and ln["chave"] == chave and ln["rid"] == "pv_pedidos"
    assert ped.get("/api/edicoes?desde=1", headers=H).json()["linhas"] == []
    r = ped.post("/api/edicoes/confirmar", json={"epoca": "outra", "resultados": []}, headers=H)
    assert r.status_code == 409
    r = ped.post("/api/edicoes/confirmar", json={"epoca": d["epoca"], "resultados": [{"seq": 1}]}, headers=H)
    assert r.status_code == 400
    ok = {"epoca": d["epoca"], "resultados": [{"seq": 1, "status": "aplicada", "motivo": ""}]}
    assert ped.post("/api/edicoes/confirmar", json=ok, headers=H).json()["gravados"] == 1
    assert ped.post("/api/edicoes/confirmar", json=ok, headers=H).json()["gravados"] == 0   # idempotente
    assert ped.get("/api/edicoes?desde=0", headers=H).json()["linhas"][0]["status"] == "aplicada"
    # aplicada, mas o pacote na tela ainda é o antigo: a marca segue
    assert "Aguardando o PC" in ped.get(URL_PED).text
    time.sleep(1.1)                                   # o pacote novo chega depois da confirmação
    assert postar(ped, pacote_editavel("2026-11-24T09:00:00-04:00")).status_code == 200
    assert "Aguardando o PC" not in ped.get(URL_PED).text


def test_api_erro_motivo_so_para_admin(ped, cli):
    _editar_uma(ped)
    d = ped.get("/api/edicoes?desde=0", headers=H).json()
    ped.post("/api/edicoes/confirmar", headers=H, json={
        "epoca": d["epoca"], "resultados": [{"seq": 1, "status": "erro", "motivo": "linha não encontrada no PC"}]})
    html = ped.get(URL_PED).text
    assert "O PC recusou" in html and "linha não encontrada no PC" in html
    login = _criar(ped, "pre_venda")
    _entrar_como(cli, login)
    html = cli.get(URL_PED).text
    assert "O PC recusou" in html and "linha não encontrada no PC" not in html and 'class="bt-ed"' not in html


def test_fila_so_acrescenta(tmp_path):
    f = edicoes.Fila(tmp_path)
    a = f.registrar(usuario="u", rid="pl_entregas", tabela="Entregas", modulo="pos_venda", chave="A|1|1",
                    valores={"etapa": "ENTREGUE"}, antes={"etapa": "EM TRÂNSITO"})
    arq = next((tmp_path / "edicoes").glob("EDICOES_WEB_*.jsonl"))
    antes = arq.read_text(encoding="utf-8")
    b = f.registrar(usuario="u", rid="pl_entregas", tabela="Entregas", modulo="pos_venda", chave="A|1|1",
                    valores={"responsavel": "X"}, antes={"responsavel": ""})
    assert (a["seq"], b["seq"]) == (1, 2)
    depois = arq.read_text(encoding="utf-8")
    assert depois.startswith(antes)                               # nada reescrito
    sit = f.situacao("pl_entregas")[("Entregas", "A|1|1")]
    assert sit["status"] == "pendente" and sit["valores"] == {"etapa": "ENTREGUE", "responsavel": "X"}
    ep = f.desde(0)["epoca"]
    f.confirmar(ep, [{"seq": 1, "status": "aplicada"}, {"seq": 99, "status": "aplicada"}])
    assert arq.read_text(encoding="utf-8").startswith(depois)
    assert [x["status"] for x in f.desde(0)["linhas"]] == ["aplicada", "pendente"]
    assert edicoes.Fila(tmp_path).desde(0)["epoca"] == ep          # a época fica no estado.json


# ------------------------------------------------------------------ um clique no pedido (como o PC)
def test_clique_no_pedido_filtra_as_de_baixo(ped):
    html = ped.get(URL_PED).text
    assert 'class="sel-link"' in html
    sel = re.findall(r'class="sel-link" href="([^"]+)"', html)[0].replace("&amp;", "&")
    k = int(parse_qs(urlparse(sel).query)["sel"][0])
    pag = ped.get(sel).text
    assert "Tabelas de baixo só com" in pag and 'class="tom-' in pag and " sel\"" in pag
    pedido = f"9{k + 1 + 100:05d}"
    analitico = pag.split("Analítico por pedido")[1]
    linhas = re.findall(r"<tr class=\"tom-[^\"]*\">(.*?)</tr>", analitico)
    assert all(pedido in x for x in linhas)
    assert "Tabelas de baixo só com" not in ped.get(URL_PED + "&sel=9999").text
