"""T-0025: Farol DDR (3 áreas), Campanhas BAP e Farol de Expositores na web; edição só admin (STATUS/MOTIVO e linha nova)."""
import json
import re

import pytest

from conftest import TOKEN, postar, token_form
from t25_fixture import pacote_t25
from app import edicoes, tabelas


def _criar(admin, perfil):
    login = f"t25.{perfil}"
    admin.post("/usuarios", data={"acao": "criar", "login": login, "perfil": perfil,
                                  "senha": "senha-teste-forte-9", "csrf": token_form(admin, "/usuarios")})
    return login


def _entrar_como(cli, login):
    cli.post("/sair", data={"csrf": token_form(cli, "/")})
    cli.post("/login", data={"usuario": login, "senha": "senha-teste-forte-9", "csrf": token_form(cli, "/login")})
    cli.post("/senha", data={"atual": "senha-teste-forte-9", "nova": "senha-teste-forte-10",
                             "confirma": "senha-teste-forte-10", "csrf": token_form(cli, "/senha")})


@pytest.fixture
def pac(admin):
    assert postar(admin, pacote_t25()).status_code == 200
    return admin


def _fila(amb):
    return [json.loads(x) for a in sorted((amb / "edicoes").glob("EDICOES_WEB_*.jsonl"))
            for x in a.read_text(encoding="utf-8").splitlines()]


def test_pacote_aceito_e_abas(pac):
    for url, achar in (("/farol/farol_pv?aba=hoje", "Atividade fictícia 0"),
                       ("/farol/farol_vc?aba=pendentes", "Pendente 1"),
                       ("/farol/farol_pl?aba=ate_hoje", "Feita 2"),
                       ("/farol/vc_champions?aba=vendedores", "VENDEDOR FICTICIO 01"),
                       ("/farol/vc_champions?aba=semanas", "SEM. 09/11"),
                       ("/farol/vc_champions?aba=regras", "Regra fictícia"),
                       ("/farol/tm_expositores?aba=expositores", "EXPOSITOR FICTICIO"),
                       ("/farol/tm_expositores?aba=estado", "AM")):
        r = pac.get(url)
        assert r.status_code == 200 and achar in r.text, url


def test_pacote_recusa_colunas_fora_do_contrato(admin):
    p = pacote_t25()
    p["relatorios"]["vc_champions"]["tabelas"][2]["colunas"][1]["nome"] = "REGRA X"
    assert postar(admin, p).status_code == 422
    p = pacote_t25()
    p["relatorios"]["tm_expositores"]["tabelas"][0]["edicao"]["campos"][0]["max"] = 500
    assert postar(admin, p).status_code == 422


def test_perfis_por_area(pac):
    cli = pac
    logins = {p: _criar(pac, p) for p in ("pre_venda", "vendas", "pos_venda", "gerente", "diretor")}
    quadro = {"pre_venda": ("farol_pv", ("farol_vc", "farol_pl", "tm_expositores", "vc_champions")),
              "vendas": ("farol_vc", ("farol_pv", "farol_pl", "tm_expositores")),
              "pos_venda": ("farol_pl", ("farol_pv", "farol_vc", "vc_champions", "tm_expositores")),
              "gerente": ("tm_expositores", ())}
    for perfil, (ok, fora) in quadro.items():
        _entrar_como(cli, logins[perfil])
        assert cli.get(f"/farol/{ok}").status_code == 200
        assert cli.get(f"/farol/{ok}?aba={tabelas.ABAS[ok][0][0]}").status_code == 200
        for rid in fora:
            assert cli.get(f"/farol/{rid}").status_code == 403, (perfil, rid)
    _entrar_como(cli, logins["vendas"])
    assert cli.get("/farol/vc_champions?aba=vendedores").status_code == 200       # Campanhas: área CRM/vendas
    _entrar_como(cli, logins["diretor"])
    assert cli.get("/farol/farol_pv").status_code == 200                            # o diretor vê o Resumo do DDR
    assert cli.get("/farol/farol_pv?aba=hoje").status_code == 403                   # mas não as tabelas (D1)
    assert cli.get("/farol/tm_expositores").status_code == 403                      # Expositores: admin e gerente


def test_edicao_ddr_so_admin(pac, amb):
    html = pac.get("/farol/farol_pv?aba=hoje").text
    links = re.findall(r'class="bt-ed" href="([^"]+)"', html)
    assert len(links) == 4
    url = links[1].replace("&amp;", "&")
    form = pac.get(url).text
    campos = {k: v.replace("&amp;", "&") for k, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form)}
    assert campos["chave"] == "2026-11|PESSOA FICTICIA|6" and "STATUS" in form
    dados = {**campos, "c_status": "ENTREGUE PARCIAL", "c_motivo": "Sobrecarga Operacional"}
    r = pac.post("/farol/farol_pv/editar", data=dados, follow_redirects=False)
    assert r.status_code == 303
    (reg,) = [x for x in _fila(amb) if x.get("tipo") == "edicao"]
    assert (reg["rid"], reg["tabela"], reg["modulo"], reg["chave"]) == ("farol_pv", "Hoje", "farol", "2026-11|PESSOA FICTICIA|6")
    assert reg["valores"] == {"status": "ENTREGUE PARCIAL", "motivo": "Sobrecarga Operacional"}
    # fora da lista = recusado, nada entra na fila
    r = pac.post("/farol/farol_pv/editar", data={**campos, "c_status": "INVENTADO"})
    assert r.status_code == 400 and len([x for x in _fila(amb) if x.get("tipo") == "edicao"]) == 1


def test_edicao_ddr_outros_perfis_sem_botao(pac, amb):
    login = _criar(pac, "pre_venda")
    _entrar_como(pac, login)
    html = pac.get("/farol/farol_pv?aba=hoje").text
    assert "bt-ed" not in html
    url = "/farol/farol_pv/editar?tab=Hoje&chave=2026-11%7CPESSOA%20FICTICIA%7C5"
    assert pac.get(url).status_code == 403
    r = pac.post("/farol/farol_pv/editar", data={"tab": "Hoje", "chave": "2026-11|PESSOA FICTICIA|5",
                                                "c_status": "ENTREGUE", "csrf": token_form(pac, "/")})
    assert r.status_code == 403
    assert not [x for x in _fila(amb)] if (amb / "edicoes").exists() else True


def test_expositores_linha_nova_e_texto_longo(pac, amb):
    url = "/farol/tm_expositores/editar?tab=Expositores&chave=NOVO&volta=/farol/tm_expositores%3Faba%3Dexpositores"
    form = pac.get(url).text
    assert pac.get("/farol/tm_expositores?aba=expositores").text.count("Novo expositor") == 1
    campos = {k: v.replace("&amp;", "&") for k, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form)}
    assert campos["chave"] == "NOVO" and 'name="c_observacoes"' in form and 'maxlength="200"' in form
    # só os padrões: recusa
    vazio = {**campos, "c_status": "Solicitado", "c_qtd": "1", "c_cliente": "", "c_observacoes": ""}
    assert pac.post("/farol/tm_expositores/editar", data=vazio).status_code == 400
    ok = {**campos, "c_status": "Solicitado", "c_qtd": "2", "c_cliente": "900001 - Cliente Fictício",
          "c_observacoes": "x" * 150}
    assert pac.post("/farol/tm_expositores/editar", data=ok, follow_redirects=False).status_code == 303
    (reg,) = [x for x in _fila(amb) if x.get("tipo") == "edicao"]
    assert re.fullmatch(r"NOVO[0-9A-F]{8}", reg["chave"]) and reg["modulo"] == "expositores"
    assert reg["valores"]["cliente"] == "900001 - Cliente Fictício" and len(reg["valores"]["observacoes"]) == 150
    longo = {**ok, "c_observacoes": "x" * 201}
    assert pac.post("/farol/tm_expositores/editar", data=longo).status_code == 400
    pessoal = {**ok, "c_observacoes": "falar com fulano@exemplo.com"}
    assert pac.post("/farol/tm_expositores/editar", data=pessoal).status_code == 400


def test_expositores_editar_existente_e_gerente_so_le(pac, amb):
    html = pac.get("/farol/tm_expositores?aba=expositores").text
    assert len(re.findall(r'class="bt-ed"', html)) == 2
    _entrar_como(pac, _criar(pac, "gerente"))
    html = pac.get("/farol/tm_expositores?aba=expositores").text
    assert "bt-ed" not in html and "Novo expositor" not in html
    assert pac.get("/farol/tm_expositores/editar?tab=Expositores&chave=NOVO").status_code == 403
    assert pac.get("/farol/tm_expositores/exportar?aba=expositores&formato=xlsx").status_code == 200


def test_spec_novo_e_max_validos():
    p = pacote_t25()["relatorios"]["tm_expositores"]["tabelas"][0]
    nomes = [c["nome"] for c in p["colunas"]]
    assert edicoes.erro_spec("tm_expositores", "Expositores", p["edicao"], nomes, len(p["linhas"])) is None
    ruim = json.loads(json.dumps(p["edicao"]))
    ruim["novo"] = {"padroes": {"status": 5}}
    assert edicoes.erro_spec("tm_expositores", "Expositores", ruim, nomes, len(p["linhas"]))
    ruim = json.loads(json.dumps(p["edicao"]))
    ruim["campos"][0]["max"] = 100                     # só campo de texto leva `max`
    assert edicoes.erro_spec("tm_expositores", "Expositores", ruim, nomes, len(p["linhas"]))
