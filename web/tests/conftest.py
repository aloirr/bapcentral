"""Fixtures: dados de exemplo (agregados por UF), nada de pessoa ou cliente; segredos só por monkeypatch."""
import secrets
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import criar_app  # noqa: E402

TOKEN = secrets.token_urlsafe(32)
ADMIN = "admin.teste"
SENHA0 = "senha-inicial-123"


def _cartao(titulo, valor, leg="", aneis=(), uf_bars=None, ant=True):
    return {"chave": "x", "titulo": titulo, "valor": valor, "legenda": leg,
            "aneis": [list(a) for a in aneis],
            "faixa": [["out", "+11%", "ok", "R$ 149 mil"], ["set", "−31%", "alerta", "R$ 237 mil"],
                      ["jul (bench.)", "−74%", "alerta", "R$ 626 mil"]],
            "estados": {"barras": uf_bars or [["PA", 28600.0, "R$ 28,6 mil", "9%", "alerta"],
                                              ["MA", 87000.0, "R$ 87,0 mil", "110%", "ok"],
                                              ["AM", 49100.0, "R$ 49,1 mil", "95%", "atencao"],
                                              ["RR", 0.0, "R$ 0", "", ""]],
                        "legenda": "atingimento da meta do mês (projeção ÷ meta)"},
            "ajuda": "texto de ajuda de exemplo"}


def _aba(visao, titulo, cartoes):
    return {"titulo": titulo, "kpis_export": [], "altura_min": 2000,
            "painel": {"blocos": [{"tipo": "rrm", "visao": visao, "row": 0, "col": 0, "colspan": 3,
                                   "dados": {"comp": "2026-11", "ano": 2026, "mes": 11,
                                             visao: cartoes,
                                             "sub": {visao: "visão absoluta · novembro até 19/11 (13 de 19 dias úteis) · variação × mês fechado"},
                                             "como_ler": "Como ler de exemplo.", "dados_ate": "2026-11-19",
                                             "avisos": []}}]}}


def pacote_ficticio(gerado_em="2026-11-20T08:30:00-04:00", n=3):
    res = [_cartao("Faturamento líquido · proj.", "R$ 165 mil", "projeção do mês",
                   [("MTD", 11.2, "1,03 mi"), ("MÊS", 100.4, "1,50 mi")]),
           _cartao("Positivação", "45", "projeção do mês 66", [("MTD", 40.0, "112"), ("MÊS", 93.0, "163")]),
           _cartao("Pedidos faturados · proj.", "85", "projeção do mês")]
    prod = [_cartao("Visitas", "310", "", [("MÊS", 70.0, "440")])]
    return {"versao_contrato": 1, "gerado_em": gerado_em, "ano": 2026, "mes": 11,
            "relatorios": {"vc_painel": {"titulo": "Painel Executivo", "abas": {
                "resultado": _aba("res", "Painel · resultado", res),
                "produtividade": _aba("prod", "Painel · produtividade", prod)}}}}


@pytest.fixture
def amb(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "segredo-de-teste-0123456789abcdef")
    monkeypatch.setenv("BAP_WEB_DADOS", str(tmp_path))
    monkeypatch.setenv("BAP_WEB_TOKEN", TOKEN)
    monkeypatch.setenv("BAP_ADMIN_USUARIO", ADMIN)
    monkeypatch.setenv("BAP_ADMIN_SENHA_INICIAL", SENHA0)
    monkeypatch.setenv("BAP_WEB_PACOTE_MAX_MB", "1")
    monkeypatch.setenv("TZ", "America/Manaus")
    return tmp_path


@pytest.fixture
def cli(amb):
    with TestClient(criar_app(), base_url="https://testserver") as c:
        yield c


def csrf_de(cli):
    import re
    html = cli.get("/login").text
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def entrar(cli, usuario, senha):
    return cli.post("/login", data={"usuario": usuario, "senha": senha, "csrf": csrf_de(cli)},
                    follow_redirects=False)


def token_form(cli, url):
    import re
    return re.search(r'name="csrf" value="([^"]+)"', cli.get(url).text).group(1)


@pytest.fixture
def admin(cli):
    """Admin já com a senha trocada, logado."""
    r = entrar(cli, ADMIN, SENHA0)
    assert r.status_code == 303
    r = cli.post("/senha", data={"atual": SENHA0, "nova": "nova-senha-forte-1",
                                 "confirma": "nova-senha-forte-1",
                                 "csrf": token_form(cli, "/senha")}, follow_redirects=False)
    assert r.status_code == 303
    return cli


def postar(cli, corpo=None, token=TOKEN, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return cli.post("/api/pacote", json=corpo if corpo is not None else pacote_ficticio(),
                    headers=h, **kw)
