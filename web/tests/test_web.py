import json
import os
import time
from pathlib import Path

from conftest import ADMIN, SENHA0, TOKEN, entrar, guardado, guardado_txt, pacote_ficticio, postar, token_form

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
    for url in ("/", "/painel", "/usuarios"):
        r = cli.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_primeiro_acesso_obriga_trocar_senha(cli):
    assert entrar(cli, ADMIN, SENHA0).status_code == 303
    r = cli.get("/painel", follow_redirects=False)
    assert r.headers["location"] == "/senha"
    r = cli.post("/senha", data={"atual": SENHA0, "nova": "curta", "confirma": "curta",
                                 "csrf": token_form(cli, "/senha")})
    assert r.status_code == 400
    r = cli.post("/senha", data={"atual": SENHA0, "nova": "uma-senha-nova-10",
                                 "confirma": "uma-senha-nova-10",
                                 "csrf": token_form(cli, "/senha")}, follow_redirects=False)
    assert r.status_code == 303
    assert cli.get("/painel").status_code == 200


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
        assert g.get("/painel").status_code == 200
        assert "Usuários" not in g.get("/").text


# ---------------------------------------------------------------- pacote
def test_pacote_sem_token_ou_errado_401(cli, amb):
    assert postar(cli, token=None).status_code == 401
    assert postar(cli, token="errado").status_code == 401
    assert not (amb / "pacotes").exists()


def test_pacote_ok_grava_atomico_e_mantem_7(cli, amb):
    for i in range(17):
        r = postar(cli, pacote_ficticio(f"2026-11-{i + 1:02d}T08:30:00-04:00"))
        assert r.status_code == 200, r.text
    arqs = sorted(p.name for p in (amb / "pacotes").glob("*"))
    assert len(arqs) == 7 and arqs[-1].startswith("20261117")
    assert not [a for a in arqs if a.startswith(".tmp")]


def test_pacote_gerado_em_saneado(cli, amb):
    assert postar(cli, pacote_ficticio("2026-11-20T08:30:00-04:00")).status_code == 200
    assert (amb / "pacotes" / "20261120T083000" / "indice.json").exists()
    assert postar(cli, pacote_ficticio("../../etc/passwd")).status_code == 422
    # nome pela hora de Manaus (UTC-4): 23:30-04:00 e 03:30Z do dia seguinte dão o mesmo nome
    assert pacotes.nome_arquivo("2026-11-20T23:30:00-04:00") == "20261120T233000"
    assert pacotes.nome_arquivo("2026-11-21T03:30:00+00:00") == "20261120T233000"
    with __import__("pytest").raises(ValueError):
        pacotes.nome_arquivo("2026-11-20T08:30:00/../x")


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
    p["relatorios"]["vc_painel"]["_champions"] = {"vendedores": ["Pessoa Fictícia"]}
    assert postar(cli, p).status_code == 200
    assert "_champions" not in guardado_txt(amb)


# ---------------------------------------------------------------- telas
def test_sem_pacote_aviso(admin):
    r = admin.get("/painel")
    assert "Ainda não chegou nenhum pacote do PC" in r.text


def test_render_painel_abas_aneis_barras_rodapes(admin):
    postar(admin, pacote_ficticio())
    r = admin.get("/painel").text
    assert "Dados de 20/11/2026 08:30" in r and "BAP AUTOPARTS" in r
    for t in ("Resultado", "Produtividade", "Painel Executivo",
              "visão absoluta · novembro até 19/11 (13 de 19 dias úteis)",
              "FATURAMENTO LÍQUIDO · PROJ.", "R$ 165 mil", "projeção do mês 66", "POSITIVAÇÃO",
              "PEDIDOS FATURADOS · PROJ.", "jul (bench.)", "−74%", "R$ 626 mil",
              "atingimento da meta do mês (projeção ÷ meta)", "Como ler de exemplo."):
        assert t in r, t
    assert r.count("<article") == 3 and r.count('class="arco"') == 4
    assert "11%" in r and "1,03 mi" in r and "100%" in r
    assert 'class="anel t-alerta"' in r and 'class="anel t-ok"' in r and 'class="anel t-atencao"' not in r.split("POSITIVAÇÃO")[0]
    for uf in ("PA", "MA", "AM", "RR"):
        assert f'<div class="uf">{uf}</div>' in r
    assert "R$ 87,0 mil" in r and "R$ 28,6 mil" in r
    assert "height:92.0%" in r                      # a maior barra
    assert "Visitas" not in r
    r = admin.get("/painel?aba=produtividade").text
    assert "VISITAS" in r and "FATURAMENTO" not in r
    assert "FATURAMENTO LÍQUIDO · PROJ." in admin.get("/painel?aba=qualquer").text


def test_pacote_sem_vc_painel_422(cli):
    p = pacote_ficticio()
    p["relatorios"] = {"pl_inadimplencia": {"titulo": "x"}}
    r = postar(cli, p)
    assert r.status_code == 422
    p["relatorios"] = {}
    assert postar(cli, p).status_code == 422
    p = pacote_ficticio()
    del p["relatorios"]["vc_painel"]["abas"]["produtividade"]
    assert postar(cli, p).status_code == 422
    p = pacote_ficticio()
    p["relatorios"]["vc_painel"]["abas"]["resultado"]["painel"]["blocos"][0]["dados"]["res"][0]["faixa"] = [["a"]]
    assert postar(cli, p).status_code == 422


def test_pacote_guarda_so_o_que_a_tela_le(cli, amb):
    p = pacote_ficticio()
    a = p["relatorios"]["vc_painel"]["abas"]["resultado"]
    a["diretor"] = {"cliente": "Cliente Fictício 01"}
    a["painel"]["blocos"][0]["dados"]["du"] = [{"titulo": "x"}]
    assert postar(cli, p).status_code == 200
    txt = guardado_txt(amb)
    assert "Cliente Fictício 01" not in txt and '"du"' not in txt


def test_autoescape(admin):
    p = pacote_ficticio()
    p["relatorios"]["vc_painel"]["abas"]["resultado"]["painel"]["blocos"][0]["dados"]["res"][0]["titulo"] = "<script>alert(1)</script>"
    postar(admin, p)
    r = admin.get("/painel").text
    assert "<script>alert(1)</script>" not in r.lower() and "&lt;SCRIPT&gt;" in r


def test_formatos_e_tom_do_anel():
    assert render.pc(11.2) == "11%" and render.pc(None) == "—" and render.br(1250.5, 2) == "1.250,50"
    assert [render.tom_de(x) for x in (100, 95, 89.9, None)] == ["ok", "atencao", "alerta", ""]


# ---------------------------------------------------------------- saúde e TZ
def test_saude_e_tz(cli, monkeypatch):
    r = cli.get("/saude").json()
    assert r["status"] == "ok" and r["tz_ok"] is True and r["ultimo_pacote"] is None
    assert r["versao"] and len(r["hora_manaus"]) == 19 and r["motivo"] is None
    postar(cli, pacote_ficticio())
    assert cli.get("/saude").json()["ultimo_pacote"] == "2026-11-20T08:30:00-04:00"
    monkeypatch.setenv("TZ", "UTC")
    r = cli.get("/saude")
    assert r.status_code == 200
    r = r.json()
    assert r["tz_ok"] is False and r["tz"] == "UTC" and r["telas_bloqueadas"] is True
    assert "America/Manaus" in r["motivo"]


def test_tz_errado_telas_503_saude_e_robo_seguem(admin, monkeypatch):
    assert admin.get("/").status_code == 200
    monkeypatch.setenv("TZ", "UTC")
    for url in ("/", "/painel", "/login", "/usuarios"):
        assert admin.get(url).status_code == 503
    assert admin.post("/login", data={}).status_code == 503
    assert postar(admin).status_code == 200            # o robô não depende do fuso da tela
    monkeypatch.setenv("TZ", "America/Manaus")
    assert admin.get("/").status_code == 200


def test_data_do_servidor_diferente_de_manaus_503(admin, monkeypatch):
    from datetime import date, timedelta, datetime
    from app import main
    amanha = datetime.now(main.MANAUS).date() + timedelta(days=1)
    monkeypatch.setattr(main, "hoje_local", lambda: amanha)
    assert admin.get("/").status_code == 503
    r = admin.get("/saude").json()
    assert r["tz_ok"] is False and "data" in r["motivo"]


def test_subprocesso_com_tz_errado_responde_503(tmp_path):
    import subprocess
    import sys
    import secrets
    from pathlib import Path
    env = {"PATH": os.environ.get("PATH", ""), "TZ": "UTC",
           "SESSION_SECRET": secrets.token_urlsafe(32), "BAP_WEB_TOKEN": secrets.token_urlsafe(32),
           "BAP_WEB_DADOS": str(tmp_path), "BAP_ADMIN_USUARIO": "admin.teste",
           "BAP_ADMIN_SENHA_INICIAL": secrets.token_urlsafe(16)}
    codigo = ("from fastapi.testclient import TestClient\n"
              "from app.main import criar_app\n"
              "c = TestClient(criar_app(), base_url='https://testserver')\n"
              "print(c.get('/login').status_code, c.get('/saude').json()['tz_ok'])\n")
    raiz = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-c", codigo], cwd=raiz, env=env, capture_output=True,
                       text=True, timeout=60)
    assert r.stdout.split() == ["503", "False"], r.stderr[-500:]


# ---------------------------------------------------------------- sessão no servidor
def _logar_outro(admin, login, senha):
    from fastapi.testclient import TestClient
    c = TestClient(admin.app, base_url="https://testserver")
    assert entrar(c, login, senha).status_code == 303
    return c


def test_cookie_antigo_depois_do_sair_nao_entra(admin):
    cookie = admin.cookies.get("bap_sessao")
    assert admin.get("/painel", follow_redirects=False).status_code == 200
    r = admin.post("/sair", data={"csrf": token_form(admin, "/senha")}, follow_redirects=False)
    assert r.status_code == 303
    from fastapi.testclient import TestClient
    with TestClient(admin.app, base_url="https://testserver") as velho:
        velho.cookies.set("bap_sessao", cookie)
        r = velho.get("/", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
        assert velho.get("/painel", follow_redirects=False).headers["location"] == "/login"


def test_troca_de_senha_derruba_outra_sessao(admin):
    nova = "nova-senha-forte-1"
    outra = _logar_outro(admin, ADMIN, nova)
    assert outra.get("/painel", follow_redirects=False).status_code == 200
    novissima = "senha-ainda-mais-forte-2"
    r = admin.post("/senha", data={"atual": nova, "nova": novissima, "confirma": novissima,
                                   "csrf": token_form(admin, "/senha")}, follow_redirects=False)
    assert r.status_code == 303
    assert admin.get("/painel", follow_redirects=False).status_code == 200       # quem trocou segue
    r = outra.get("/painel", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_desativar_derruba_sessao_aberta(admin):
    def acao(**d):
        return admin.post("/usuarios", data={**d, "csrf": token_form(admin, "/usuarios")})
    senha = "senha-do-diretor-1"
    acao(acao="criar", login="diretor.um", perfil="diretor", senha=senha)
    outro = _logar_outro(admin, "diretor.um", senha)
    assert outro.get("/senha", follow_redirects=False).status_code == 200
    acao(acao="desativar", login="diretor.um")
    assert outro.get("/senha", follow_redirects=False).status_code == 303


# ---------------------------------------------------------------- acertos do parecer
def test_csrf_nao_ascii_nao_da_500(cli):
    r = cli.post("/login", data={"usuario": "x", "senha": "y", "csrf": "ção-não-ascii"})
    assert r.status_code == 400


def test_login_mesma_mensagem_para_inexistente_e_bloqueado(cli):
    for _ in range(5):
        entrar(cli, ADMIN, "errada-errada-1")
    bloq = entrar(cli, ADMIN, "errada-errada-1")
    nao = entrar(cli, "ninguem.aqui", "errada-errada-1")
    assert bloq.status_code == nao.status_code == 401
    import re
    cap = lambda r: re.search(r'class="[^"]*erro[^"]*"[^>]*>(.*?)<', r.text, re.S)
    assert (cap(bloq) and cap(bloq).group(1)) == (cap(nao) and cap(nao).group(1))


def test_usuarios_get_ignora_msg_e_erro(admin):
    assert "TEXTO-INJETADO" not in admin.get("/usuarios?msg=TEXTO-INJETADO&erro=TEXTO-INJETADO").text


def test_pacote_tipos_errados_422_e_nao_500(cli):
    def com(mexe):
        p = pacote_ficticio()
        mexe(p["relatorios"]["vc_painel"]["abas"]["resultado"]["painel"]["blocos"][0]["dados"])
        return postar(cli, p)
    assert com(lambda d: d["res"][0].update(aneis=5)).status_code == 422
    assert com(lambda d: d["res"][0].update(faixa="abc")).status_code == 422
    assert com(lambda d: d["res"][0].update(aneis={"a": 1})).status_code == 422
    assert com(lambda d: d["res"][0].update(estados={"barras": 7})).status_code == 422
    assert com(lambda d: d.update(sub=["x"])).status_code == 422
    assert com(lambda d: d.update(sub="texto")).status_code == 422
    assert com(lambda d: None).status_code == 200


def test_config_token_curto_nao_sobe_e_limite_padrao(amb, monkeypatch):
    import pytest
    monkeypatch.setenv("BAP_WEB_TOKEN", "curto")
    with pytest.raises(config.ConfigErro, match="BAP_WEB_TOKEN") as e:
        criar_app()
    assert "curto" not in str(e.value).replace("curto (", "")
    monkeypatch.setenv("BAP_WEB_TOKEN", TOKEN)
    monkeypatch.delenv("BAP_WEB_PACOTE_MAX_MB")
    assert config.carregar().pacote_max == 25 * 1024 * 1024      # o mesmo do render.yaml


def test_css_barras_sem_colunas_fixas():
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    assert "repeat(4,1fr)" not in css and "grid-auto-columns:1fr" in css


# ------------------------------------------------------------ T-0014: visões prontas por estado
def _recortes():
    from conftest import _cartao
    pa = [_cartao("Faturamento líquido · proj.", "R$ 28,6 mil", "9%",
                  uf_bars=[["PA", 28600.0, "R$ 28,6 mil", "9%", "alerta"]])]
    ma = [_cartao("Faturamento líquido · proj.", "R$ 87,0 mil", "110%",
                  uf_bars=[["MA", 87000.0, "R$ 87,0 mil", "110%", "ok"]])]
    for c in pa + ma:
        c["aneis"], c["faixa"] = [], []
    return {"uf": {"PA": {"cartoes": pa}, "MA": {"cartoes": ma}}}


def _pacote_com_recortes():
    from conftest import pacote_ficticio
    p = pacote_ficticio()
    for a in p["relatorios"]["vc_painel"]["abas"].values():
        a["recortes"] = _recortes()
    return p


def test_T0014_pacote_com_recortes_aceito_e_guardado(cli, amb):
    from conftest import postar
    assert postar(cli, _pacote_com_recortes()).status_code == 200
    import json
    g = guardado(amb)
    assert set(g["relatorios"]["vc_painel"]["abas"]["resultado"]["recortes"]["uf"]) == {"PA", "MA"}


def test_T0014_recortes_invalidos_422(cli):
    from conftest import postar
    p = _pacote_com_recortes()
    p["relatorios"]["vc_painel"]["abas"]["resultado"]["recortes"]["supervisor"] = {"X": "PA"}
    assert postar(cli, p).status_code == 422                         # só filtro por estado
    p = _pacote_com_recortes()
    p["relatorios"]["vc_painel"]["abas"]["resultado"]["recortes"]["uf"]["pa"] = {"cartoes": []}
    assert postar(cli, p).status_code == 422


def test_T0014_filtro_mostra_a_visao_pronta_sem_calcular(admin):
    from conftest import postar
    assert postar(admin, _pacote_com_recortes()).status_code == 200
    html = admin.get("/painel?aba=resultado").text
    assert ">BAP</a>" in html and "R$ 165 mil" in html          # sem filtro: o total
    html = admin.get("/painel?aba=resultado&uf=MA").text
    assert "R$ 87,0 mil" in html and "R$ 165 mil" not in html       # a barra do MA, como veio
    assert "rrm-recorte" in html                                     # cartão compacto no recorte
    assert "Número do estado como na barra dele" in html             # "como ler" próprio da visão do estado
    assert "Faixa:" not in html                                      # sem o texto de anel/faixa da BAP inteira
    html = admin.get("/painel?aba=resultado&uf=pa").text
    assert "R$ 28,6 mil" in html and "PA · estado = filial da nota" in html
    assert "Supervisor" not in html                                  # sem filtro por supervisor
    html = admin.get("/painel?aba=resultado&uf=ZZ").text           # estado sem visão = BAP inteira
    assert "R$ 165 mil" in html


def test_T0014_sem_recortes_sem_filtro(admin):
    from conftest import postar
    assert postar(admin).status_code == 200
    html = admin.get("/painel?aba=resultado").text
    assert 'class="filtros"' not in html
