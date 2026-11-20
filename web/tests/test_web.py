import json
import os
import time

from conftest import ADMIN, SENHA0, TOKEN, entrar, pacote_ficticio, postar, token_form

from app import config, pacotes, render
from app.main import criar_app


# ---------------------------------------------------------------- config
def test_sem_session_secret_nao_sobe(amb, monkeypatch):
    import pytest
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(config.ConfigErro, match="SESSION_SECRET"):
        criar_app()


def test_sem_usuarios_e_sem_admin_env_falha_claro(amb, monkeypatch):
    import pytest
    monkeypatch.delenv("BAP_ADMIN_SENHA_INICIAL")
    with pytest.raises(config.ConfigErro, match="primeiro admin"):
        criar_app()


# ---------------------------------------------------------------- login
def test_senha_com_hash_e_sal(cli, amb):
    arq = (amb / "usuarios.json").read_text()
    assert SENHA0 not in arq
    d = json.loads(arq)["usuarios"][ADMIN]
    assert len(d["hash"]) == 64 and len(d["sal"]) == 32


def test_rotas_exigem_login(cli):
    for url in ("/", "/diretor", "/inadimplencia", "/usuarios"):
        r = cli.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_primeiro_acesso_obriga_trocar_senha(cli):
    assert entrar(cli, ADMIN, SENHA0).status_code == 303
    r = cli.get("/diretor", follow_redirects=False)
    assert r.headers["location"] == "/senha"
    r = cli.post("/senha", data={"atual": SENHA0, "nova": "curta", "confirma": "curta",
                                 "csrf": token_form(cli, "/senha")})
    assert r.status_code == 400
    r = cli.post("/senha", data={"atual": SENHA0, "nova": "uma-senha-nova-10",
                                 "confirma": "uma-senha-nova-10",
                                 "csrf": token_form(cli, "/senha")}, follow_redirects=False)
    assert r.status_code == 303
    assert cli.get("/diretor").status_code == 200


def test_bloqueio_depois_de_5_erros(cli):
    for _ in range(4):
        assert entrar(cli, ADMIN, "errada-errada").status_code == 401
    r = entrar(cli, ADMIN, "errada-errada")
    assert r.status_code == 401 and "bloqueado" in r.text
    r = entrar(cli, ADMIN, SENHA0)               # a certa também é recusada
    assert r.status_code == 401 and "bloqueado" in r.text


def test_login_invalido_e_csrf(cli):
    assert entrar(cli, "ninguem", "qualquer-coisa").status_code == 401
    r = cli.post("/login", data={"usuario": ADMIN, "senha": SENHA0, "csrf": "falso"})
    assert r.status_code == 400


def test_admin_cria_desativa_e_troca_senha(admin):
    def acao(**d):
        return admin.post("/usuarios", data={**d, "csrf": token_form(admin, "/usuarios")})
    assert acao(acao="criar", login="diretor.um", perfil="diretor", senha="senha-do-diretor-1").status_code == 200
    assert acao(acao="criar", login="diretor.um", perfil="diretor", senha="senha-do-diretor-1").status_code == 400
    assert acao(acao="criar", login="x", perfil="diretor", senha="senha-do-diretor-1").status_code == 400
    assert acao(acao="criar", login="ger.um", perfil="root", senha="senha-do-diretor-1").status_code == 400
    assert acao(acao="senha", login="diretor.um", senha="outra-senha-forte-2").status_code == 200
    assert acao(acao="desativar", login=ADMIN).status_code == 400          # a si mesmo
    assert acao(acao="desativar", login="diretor.um").status_code == 200
    from fastapi.testclient import TestClient
    with TestClient(admin.app, base_url="https://testserver") as outro:
        assert entrar(outro, "diretor.um", "outra-senha-forte-2").status_code == 401


# ---------------------------------------------------------------- perfil
def test_perfil_gerente_nao_ve_usuarios(admin):
    admin.post("/usuarios", data={"acao": "criar", "login": "ger.um", "perfil": "gerente",
                                  "senha": "senha-do-gerente-1", "csrf": token_form(admin, "/usuarios")})
    from fastapi.testclient import TestClient
    with TestClient(admin.app, base_url="https://testserver") as g:
        assert entrar(g, "ger.um", "senha-do-gerente-1").status_code == 303
        g.post("/senha", data={"atual": "senha-do-gerente-1", "nova": "senha-nova-gerente-9",
                               "confirma": "senha-nova-gerente-9", "csrf": token_form(g, "/senha")})
        assert g.get("/usuarios").status_code == 403
        assert g.post("/usuarios", data={"acao": "criar", "csrf": token_form(g, "/senha")}).status_code == 403
        assert g.get("/diretor").status_code == 200
        assert g.get("/inadimplencia").status_code == 200
        assert "Usuários" not in g.get("/").text


# ---------------------------------------------------------------- pacote
def test_pacote_sem_token_ou_errado_401(cli, amb):
    assert postar(cli, token=None).status_code == 401
    assert postar(cli, token="errado").status_code == 401
    assert not (amb / "pacotes").exists()


def test_pacote_ok_grava_atomico_e_mantem_15(cli, amb):
    for i in range(17):
        r = postar(cli, pacote_ficticio(f"2026-11-{i + 1:02d}T08:30:00-04:00"))
        assert r.status_code == 200, r.text
    arqs = sorted(p.name for p in (amb / "pacotes").glob("*"))
    assert len(arqs) == 15 and arqs[-1].startswith("20261117")
    assert not [a for a in arqs if a.startswith(".tmp")]


def test_pacote_gerado_em_saneado(cli, amb):
    assert postar(cli, pacote_ficticio("2026-11-20T08:30:00-04:00")).status_code == 200
    assert (amb / "pacotes" / "20261120T0830000400.json").exists()
    assert postar(cli, pacote_ficticio("../../etc/passwd")).status_code == 422
    assert pacotes.nome_arquivo("2026-11-20T08:30:00/../x") == "20261120T083000x"


def test_pacote_grande_413(cli, amb):
    grande = b"x" * (2 * 1024 * 1024)
    r = cli.post("/api/pacote", content=grande, headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    assert r.status_code == 413
    def gerador():                               # sem Content-Length (streaming)
        for _ in range(4):
            yield b"y" * (512 * 1024)
    r = cli.post("/api/pacote", content=gerador(), headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    assert r.status_code == 413


def test_pacote_415_e_422(cli):
    h = {"Authorization": f"Bearer {TOKEN}"}
    assert cli.post("/api/pacote", files={"a": ("x.pkl", b"abc")}, headers=h).status_code == 415
    assert cli.post("/api/pacote", content=b"\x80\x04.", headers={
        **h, "Content-Type": "application/octet-stream"}).status_code == 415
    assert cli.post("/api/pacote", content=b"{nao json", headers={
        **h, "Content-Type": "application/json"}).status_code == 422
    ruim = pacote_ficticio()
    ruim["mes"] = 13
    ruim["relatorios"]["outro"] = {}
    r = postar(cli, ruim)
    assert r.status_code == 422 and len(r.json()["detalhes"]) == 2


def test_pacote_remove_chaves_internas(cli, amb):
    p = pacote_ficticio()
    p["relatorios"]["pl_inadimplencia"]["_champions"] = {"vendedores": ["Pessoa Fictícia"]}
    assert postar(cli, p).status_code == 200
    assert "_champions" not in (next((amb / "pacotes").glob("*.json"))).read_text()


# ---------------------------------------------------------------- telas
def test_sem_pacote_aviso(admin):
    r = admin.get("/diretor")
    assert "Ainda não chegou nenhum pacote do PC" in r.text


def test_render_diretor_abas_e_inadimplencia(admin):
    postar(admin, pacote_ficticio())
    r = admin.get("/diretor")
    assert "Dados de 20/11/2026 08:30" in r.text
    for t in ("Painel · resultado", "Painel · produtividade", "Painel · por dia útil",
              "Faturamento", "R$ 1.500.000", "BAP AUTOPARTS"):
        assert t in r.text
    assert "Visitas" not in r.text
    assert "Visitas" in admin.get("/diretor?aba=1").text
    assert "Fat. por DU" in admin.get("/diretor?aba=2").text
    assert "R$ 1.000" in r.text and "R$ 3.002" in r.text and "12,3%" in r.text and "19/11/2026" in r.text
    assert "OCULTA" not in r.text and "background:#B3261E" in r.text
    r = admin.get("/inadimplencia")
    assert "Vencido" in r.text and "R$ 200.000" in r.text and "Aviso fictício" in r.text
    assert "Cliente Fictício 01" in r.text


def test_autoescape(admin):
    postar(admin, pacote_ficticio())
    r = admin.get("/inadimplencia")
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_filtro_ordem_na_url_e_total(admin):
    postar(admin, pacote_ficticio(n=3))
    r = admin.get("/diretor?t=0&q=filial 01")
    assert ">Filial 01</td>" in r.text and ">Filial 02</td>" not in r.text
    assert "TOTAL" not in r.text                  # com filtro, sem total (contrato 11.3)
    assert "TOTAL" in admin.get("/diretor").text
    r = admin.get("/diretor?t=0&f0=Filial 02")
    assert ">Filial 02</td>" in r.text and ">Filial 00</td>" not in r.text
    r = admin.get("/diretor?t=0&o=1&d=1").text
    assert r.index(">Filial 02</td>") < r.index(">Filial 00</td>")
    r = admin.get("/diretor?t=0&o=1&d=0").text
    assert r.index(">Filial 00</td>") < r.index(">Filial 02</td>")


def test_formatos_do_contrato():
    assert render.formatar(1250.0, "moeda") == "R$ 1.250"
    assert render.formatar(1250.5, "moeda2") == "R$ 1.250,50"
    assert render.formatar(85.34, "pct1") == "85,3%"
    assert render.formatar("2026-11-19", "dia") == "19/11"
    assert render.formatar(None, "moeda") == ""


# ---------------------------------------------------------------- saúde e TZ
def test_saude_e_tz(cli, monkeypatch):
    r = cli.get("/saude").json()
    assert r["status"] == "ok" and r["tz_ok"] is True and r["ultimo_pacote"] is None
    assert r["versao"] and len(r["hora_manaus"]) == 19
    postar(cli, pacote_ficticio())
    assert cli.get("/saude").json()["ultimo_pacote"] == "2026-11-20T08:30:00-04:00"
    monkeypatch.setenv("TZ", "UTC")
    r = cli.get("/saude").json()
    assert r["tz_ok"] is False and r["tz"] == "UTC"


def test_home_avisa_tz_errado(admin, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    assert "Fuso do servidor fora do padrão" in admin.get("/").text
    monkeypatch.setenv("TZ", "America/Manaus")
    assert "Fuso do servidor fora do padrão" not in admin.get("/").text


def test_tabela_grande_corta_linhas(admin):
    p = pacote_ficticio()
    t = p["relatorios"]["pl_inadimplencia"]["tabelas"][0]
    t["linhas"] = [[f"Cliente Fictício {i:04d}", 1.0, 1.0, "2026-10-01", ""] for i in range(500)]
    t["tons"], t["cores_celulas"] = [], []
    postar(admin, p)
    r = admin.get("/inadimplencia").text
    assert "Mostrando as primeiras 300 linhas de 500" in r
    assert ">Cliente Fictício 0299</td>" in r and ">Cliente Fictício 0300</td>" not in r
    assert ">Cliente Fictício 0450</td>" in admin.get("/inadimplencia?t=0&q=0450").text
