"""T-0017: faróis na web (só leitura). Fixture sem dado pessoal."""
import json

from conftest import entrar, postar, token_form
from farol_fixture import pacote_farol
from fastapi.testclient import TestClient


def _usuario(admin, login, perfil):
    senha = "senha-de-teste-12"
    r = admin.post("/usuarios", data={"acao": "criar", "login": login, "perfil": perfil,
                                      "senha": senha, "csrf": token_form(admin, "/usuarios")})
    assert r.status_code == 200
    c = TestClient(admin.app, base_url="https://testserver")
    assert entrar(c, login, senha).status_code == 303
    c.post("/senha", data={"atual": senha, "nova": "senha-nova-teste-9", "confirma": "senha-nova-teste-9",
                           "csrf": token_form(c, "/senha")})
    return c


def test_farol_aceito_e_guardado_sem_abas(cli, amb):
    assert postar(cli, pacote_farol()).status_code == 200
    g = json.loads(sorted((amb / "pacotes").glob("*.json"))[-1].read_text(encoding="utf-8"))
    r = g["relatorios"]["pl_inadimplencia"]
    assert r["forma"] == "farol" and r["recortes"]["AM"]["kpis"] and "abas" not in r


def test_farol_recusa_chaves_de_edicao_tabelas_e_internas(cli):
    for chave in ("tabelas", "juntas", "edicao", "editar", "abrir", "_eventos"):
        p = pacote_farol()
        p["relatorios"]["pl_inadimplencia"][chave] = []
        assert postar(cli, p).status_code == 422, chave
    p = pacote_farol()                                   # chave com _ em nível fundo
    p["relatorios"]["pl_inadimplencia"]["painel"]["blocos"][1]["grafico"]["_x"] = 1
    assert postar(cli, p).status_code == 422
    p = pacote_farol()
    del p["relatorios"]["pl_inadimplencia"]["forma"]
    assert postar(cli, p).status_code == 422
    p = pacote_farol()
    p["relatorios"]["pl_inadimplencia"]["kpis"] = [{"rotulo": "x", "valor": 3}]
    assert postar(cli, p).status_code == 422
    p = pacote_farol()
    p["relatorios"]["pl_inadimplencia"]["recortes"] = {"am": {"kpis": []}}
    assert postar(cli, p).status_code == 422


def test_farol_desenha_kpis_resumo_barras_e_bloco_desconhecido(admin):
    postar(admin, pacote_farol())
    h = admin.get("/farol/pl_inadimplencia").text
    assert "R$ 1,20 mi" in h and "Resumo gerencial" in h and "Atraso acima de 90 dias" in h
    assert "Recebido (R$) · mês a mês" in h and 'class="hb"' in h and "Vendedor 01" in h
    assert "ainda não disponível na web" in h            # bloco tabela
    assert "Baixado em 24/11/2026 08:10" in h
    assert "Cartões por estado" not in h
    assert "<form" not in h.split("<main>")[1]            # nenhum botão de gravar


def test_farol_filtro_por_estado_troca_so_os_cartoes(admin):
    postar(admin, pacote_farol())
    h = admin.get("/farol/pl_inadimplencia?uf=AM").text
    assert "R$ 700 mil" in h and "R$ 1,20 mi" not in h
    assert "Cartões por estado; gráficos da BAP inteira" in h
    assert "Recebido (R$) · mês a mês" in h              # gráficos seguem da BAP inteira
    h = admin.get("/farol/pl_inadimplencia?uf=RR").text  # sem recorte: traço, nunca o total
    assert "R$ 1,20 mi" not in h and "—" in h


def test_farol_malformado_nao_quebra(admin):
    p = pacote_farol()
    p["relatorios"]["pl_inadimplencia"]["painel"]["blocos"].append({"tipo": "barras", "grafico": "x"})
    postar(admin, p)
    r = admin.get("/farol/pl_inadimplencia")
    assert r.status_code == 200 and r.text.count("ainda não disponível na web") >= 2


def test_menu_4_itens_e_indisponivel(admin):
    postar(admin, pacote_farol())
    h = admin.get("/").text
    for n in ("Farol de Pedidos", "Farol de Visita", "Farol de Entregas", "Farol de Inadimplência"):
        assert n in h
    assert 'href="/farol/pl_inadimplencia"' in h and 'href="/farol/pv_pedidos"' not in h
    assert "ainda não disponível" in h
    r = admin.get("/farol/pv_pedidos")
    assert r.status_code == 200 and "Ainda não disponível" in r.text


def test_acesso_negado_por_perfil(admin):
    postar(admin, pacote_farol())
    casos = {"pos_venda": (["pl_inadimplencia", "pl_entregas"], ["pv_pedidos", "vc_visitas", "painel"]),
             "pre_venda": (["pv_pedidos"], ["pl_inadimplencia", "pl_entregas", "vc_visitas", "painel"]),
             "vendas": (["vc_visitas"], ["pl_inadimplencia", "pv_pedidos", "pl_entregas", "painel"])}
    for perfil, (oks, negas) in casos.items():
        c = _usuario(admin, "u." + perfil.replace("_", ""), perfil)
        for n in oks:
            assert c.get(f"/farol/{n}").status_code == 200, (perfil, n)
        for n in negas:
            url = "/painel" if n == "painel" else f"/farol/{n}"
            assert c.get(url).status_code == 403, (perfil, n)
        assert c.get("/usuarios").status_code == 403
        assert c.get("/farol/inexistente").status_code == 403
    g = _usuario(admin, "ger.farol", "gerente")
    for rid in ("pv_pedidos", "vc_visitas", "pl_entregas", "pl_inadimplencia"):
        assert g.get(f"/farol/{rid}").status_code == 200
