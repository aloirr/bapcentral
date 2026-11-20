"""Fixtures: dados 100% fictícios; segredos só por monkeypatch."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import criar_app  # noqa: E402

TOKEN = "token-de-teste-0123456789"
ADMIN = "admin.teste"
SENHA0 = "senha-inicial-123"


def pacote_ficticio(gerado_em="2026-11-20T08:30:00-04:00", n=3):
    def kp(r, v, cor="neutro"):
        return {"rotulo": r, "valor": v, "cor": cor, "detalhe": "detalhe fictício",
                "linhas": [["Atrasados", "3", "alerta"]]}

    tab = {"titulo": "Por filial", "colunas": [
        {"nome": "FILIAL", "tipo": "texto"}, {"nome": "VALOR", "tipo": "moeda"},
        {"nome": "PCT", "tipo": "pct1"}, {"nome": "DATA", "tipo": "data"},
        {"nome": "OCULTA", "tipo": "texto", "oculta": True}],
        "linhas": [[f"Filial {i:02d}", 1000.5 * (i + 1), 12.34 * i, "2026-11-19", "x"]
                   for i in range(n)],
        "tons": ["", "alerta", "ok"][:n], "filtros": ["FILIAL"],
        "total": ["TOTAL", 9999.0, None, None, None],
        "cores_celulas": [{"1": "#B3261E"}] + [{}] * (n - 1)}
    return {"versao_contrato": 1, "gerado_em": gerado_em, "ano": 2026, "mes": 11,
            "relatorios": {
                "vc_painel_diretor": {
                    "titulo": "Painel do Diretor", "subtitulo": "Posição fictícia", "kpis": [],
                    "paineis": [
                        {"titulo": "Painel · resultado", "kpis": [], "kpis_export": [
                            kp("Faturamento", "R$ 1.500.000", "ok"),
                            kp("Positivação", "42 clientes", "atencao")]},
                        {"titulo": "Painel · produtividade", "kpis": [],
                         "kpis_export": [kp("Visitas", "310")]},
                        {"titulo": "Painel · por dia útil", "kpis": [],
                         "kpis_export": [kp("Fat. por DU", "R$ 75.000")]}],
                    "tabelas": [tab]},
                "pl_inadimplencia": {
                    "titulo": "Farol de Inadimplência", "kpis": [kp("Vencido", "R$ 200.000", "alerta")],
                    "avisos": ["Aviso fictício"], "tabelas": [
                        {**tab, "titulo": "Por cliente",
                         "linhas": [["Cliente Fictício 01", 500.0, 1.0, "2026-10-01", ""],
                                    ["<script>alert(1)</script>", 700.0, 2.0, "2026-10-02", ""]],
                         "tons": ["", ""], "cores_celulas": [{}, {}]}]}}}


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
