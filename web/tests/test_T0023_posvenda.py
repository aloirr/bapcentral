"""T-0023: Garantias, Devoluções e NCC na web (leitura e edição só do admin). Dados fictícios."""
import re
from copy import deepcopy

import pytest

from conftest import TOKEN, postar, token_form
from farol_fixture import _base
from app import edicoes, tabelas

H = {"Authorization": f"Bearer {TOKEN}"}
COR = ["#E5F3DF", "#2F7D32"]


def _tab(rid, titulo, linhas, **extra):
    cols = []
    for n, tp, o in tabelas.COLUNAS_RID[(rid, titulo)]:
        c = {"nome": n, "tipo": tp, "largura": 90}
        if o:
            c["oculta"] = True
        cols.append(c)
    selos = tabelas.SELOS_RID.get((rid, titulo), {})
    for c in cols:
        s = selos.get(c["nome"])
        if s == "texto":
            c["chip"] = {"ABERTO": COR, "ATRASADA": COR, "FECHADA": COR, "NO PRAZO": COR, "NO PRAZO ": COR}
        elif s == "tom":
            c["chip_tom"] = "TOM SLA"
    nomes = [c["nome"] for c in cols]
    ls = []
    for v in linhas:
        ls.append([v.get(n) for n in nomes])
    return {"titulo": titulo, "colunas": cols, "linhas": ls, "tons": [""] * len(ls), "filtros": [], **extra}


GAR = [{"STATUS": "ABERTO", "RESULTADO ANÁLISE": "PENDENTE", "TICKET": "G-0001", "DT. SOLICITAÇÃO": "2026-11-03",
        "DT. FECHAMENTO": "2026-11-24", "SLA ATUAL": 20, "PRAZO": "NO PRAZO", "CÓD. CLIENTE": "900001",
        "CLIENTE": "CLIENTE FICTICIO 01", "SLA": 1, "TOM SLA": "ok", "PENDÊNCIAS": "enviar nota",
        "OBSERVAÇÃO": "", "RECLAMAÇÃO": "", "DT. RETORNO": None},
       {"STATUS": "FINALIZADA", "RESULTADO ANÁLISE": "PROCEDENTE", "TICKET": "G-0002", "DT. SOLICITAÇÃO": "2026-10-03",
        "DT. FECHAMENTO": "2026-10-24", "SLA ATUAL": 20, "PRAZO": "FECHADA", "TOM SLA": "ok"}]


def spec_gar(t):
    nomes = [c["nome"] for c in t["colunas"]]
    ch = [ln[nomes.index("TICKET")] for ln in t["linhas"]]

    def c(campo, rot, col, tipo, **k):
        return {"campo": campo, "rotulo": rot, "coluna": col, "tipo": tipo, "opcoes": k.pop("opcoes", []), **k}
    return {"modulo": "garantias", "acao": "Editar", "chaves": ch, "novo": {"chave": "G-0003"},
            "campos": [c("ticket", "Ticket", "TICKET", "texto", max=40, caixa=True),
                       c("dt_solicitacao", "Dt. solicitação", "DT. SOLICITAÇÃO", "data", padrao="@hoje"),
                       c("status", "Status", "STATUS", "lista", opcoes=["ABERTO", "FINALIZADA"], padrao="ABERTO"),
                       c("pendencias", "Pendências", "PENDÊNCIAS", "texto", max=600, multilinha=True, caixa=True)]}


def pacote():
    t = _tab("pl_garantias", "Garantias", GAR)
    t["edicao"] = spec_gar(t)
    f = {**_base("Farol de Garantias", [{"rotulo": "Em aberto", "valor": "1", "cor": "ok"}], []), "tabelas": [t]}
    return {"versao_contrato": 1, "gerado_em": "2026-11-24T08:30:00-04:00", "ano": 2026, "mes": 11,
            "relatorios": {"pl_garantias": f}}


@pytest.fixture
def adm(admin):
    assert postar(admin, pacote()).status_code == 200
    return admin


def test_pacote_recusa_coluna_fora_do_contrato(admin):
    p = pacote()
    p["relatorios"]["pl_garantias"]["tabelas"][0]["colunas"][2]["nome"] = "OUTRA"
    assert postar(admin, p).status_code == 422


def test_pacote_recusa_edicao_fora_do_lugar(admin):
    p = pacote()
    p["relatorios"]["pl_garantias"]["tabelas"][0]["edicao"]["modulo"] = "ncc"
    assert postar(admin, p).status_code == 422


def test_RN_POSVENDA_web_garantias_e_leitura_com_botao_novo(adm):
    h = adm.get("/farol/pl_garantias?aba=garantias").text
    assert "G-0001" in h and "Nova garantia" in h and "CONTATO" not in h


def test_garantia_nova_vai_para_a_fila_com_novo(adm):
    url = "/farol/pl_garantias/editar?tab=Garantias&novo=1&volta=/farol/pl_garantias"
    h = adm.get(url).text
    assert 'name="novo" value="1"' in h and 'value="G-0003"' in h and "<textarea" in h
    f = {"csrf": token_form(adm, url), "tab": "Garantias", "chave": "", "novo": "1", "volta": "/farol/pl_garantias",
         "c_ticket": "G-0003", "c_dt_solicitacao": "2026-11-24", "c_status": "ABERTO",
         "c_pendencias": "linha 1\nlinha 2"}
    r = adm.post("/farol/pl_garantias/editar", data=f, follow_redirects=False)
    assert r.status_code == 303
    api = adm.get("/api/edicoes?desde=0", headers=H).json()["linhas"]
    assert api[0]["novo"] is True and api[0]["chave"] == "G-0003"
    assert api[0]["valores"]["pendencias"] == "linha 1\nlinha 2" and "ticket" not in api[0]["valores"]
    assert api[0]["valores"]["dt_solicitacao"] == "24/11/2026"


def test_garantia_nova_recusa_ticket_repetido_e_telefone(adm):
    url = "/farol/pl_garantias/editar?tab=Garantias&novo=1"
    base = {"csrf": token_form(adm, url), "tab": "Garantias", "chave": "", "novo": "1", "volta": "",
            "c_status": "ABERTO"}
    r = adm.post("/farol/pl_garantias/editar", data={**base, "c_ticket": "G-0001"})
    assert r.status_code == 400 and "Já existe" in r.text
    r = adm.post("/farol/pl_garantias/editar", data={**base, "c_ticket": "G-0009", "c_pendencias": "ligar 92 99999-9999"})
    assert r.status_code == 400 and "telefone" in r.text


def test_so_admin_cria_garantia(adm):
    from conftest import TOKEN  # noqa: F401
    adm.post("/usuarios", data={"acao": "criar", "login": "t23.pos", "perfil": "pos_venda",
                                "senha": "senha-teste-forte-9", "csrf": token_form(adm, "/usuarios")})
    adm.post("/sair", data={"csrf": token_form(adm, "/")})
    adm.post("/login", data={"usuario": "t23.pos", "senha": "senha-teste-forte-9", "csrf": token_form(adm, "/login")})
    adm.post("/senha", data={"atual": "senha-teste-forte-9", "nova": "senha-teste-forte-10",
                             "confirma": "senha-teste-forte-10", "csrf": token_form(adm, "/senha")})
    assert adm.get("/farol/pl_garantias?aba=garantias").status_code == 200
    assert "Nova garantia" not in adm.get("/farol/pl_garantias?aba=garantias").text
    assert adm.get("/farol/pl_garantias/editar?tab=Garantias&novo=1").status_code == 403


def test_edicao_de_texto_longo_so_ate_o_maximo():
    ed = spec_gar(_tab("pl_garantias", "Garantias", GAR))
    nomes = ["TICKET", "PENDÊNCIAS", "STATUS", "DT. SOLICITAÇÃO"]
    m, a, e = edicoes.valores_do_form(ed, 0, [None] * 4, nomes, {"c_pendencias": "x" * 601})
    assert e
    m, a, e = edicoes.valores_do_form(ed, 0, [None] * 4, nomes, {"c_pendencias": "ok\ncerto"})
    assert not e and m == {"pendencias": "ok\ncerto"}


def test_ticket_do_form_so_letras_numeros():
    ed = spec_gar(_tab("pl_garantias", "Garantias", GAR))
    m, a, e = edicoes.valores_do_form(ed, 0, ["G-0001"], ["TICKET"], {"c_ticket": "G;1"})
    assert e
