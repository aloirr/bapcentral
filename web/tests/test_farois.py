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
    assert "Baixado do ERP em 24/11/2026 08:10" in h
    assert "Resumo e gráficos: BAP inteira" not in h
    assert "<form" not in h.split("<main>")[1]            # nenhum botão de gravar


def test_farol_filtro_por_estado_troca_so_os_cartoes(admin):
    postar(admin, pacote_farol())
    h = admin.get("/farol/pl_inadimplencia?uf=AM").text
    assert "R$ 700 mil" in h and "R$ 1,20 mi" not in h
    assert "Resumo e gráficos: BAP inteira." in h and "· BAP inteira" not in h
    assert "Recebido (R$) · mês a mês" in h              # gráficos seguem da BAP inteira
    h = admin.get("/farol/pl_inadimplencia?uf=RR").text  # sem recorte: traço, nunca o total
    assert "R$ 1,20 mi" not in h and "—" in h


def test_farol_malformado_nao_quebra(admin):
    p = pacote_farol()
    p["relatorios"]["pl_inadimplencia"]["painel"]["blocos"].append({"tipo": "barras", "grafico": "x"})
    postar(admin, p)
    r = admin.get("/farol/pl_inadimplencia")
    assert r.status_code == 200 and r.text.count("ainda não disponível na web") >= 2


def _com_estados(p):
    k = p["relatorios"]["pl_inadimplencia"]["kpis"][0]
    k["estados"] = {"barras": [["PA", 107832.5, "R$ 107,8 mil", "", ""], ["AM", 92893.1, "R$ 92,9 mil", "", ""],
                               ["AP", 630.0, "R$ 630", "", ""]], "legenda": ""}
    return p


def test_cartao_com_mini_barras_por_estado(admin):
    assert postar(admin, _com_estados(pacote_farol())).status_code == 200
    h = admin.get("/farol/pl_inadimplencia").text
    assert h.count('class="col"') == 3 and "R$ 107,8 mil" in h
    assert h.count('class="rc-barras"') == 1                   # só o cartão que trouxe `estados`


def test_estados_no_cartao_invalido_422(cli):
    p = _com_estados(pacote_farol())
    p["relatorios"]["pl_inadimplencia"]["kpis"][0]["estados"]["barras"][0] = ["PA", 1]
    assert postar(cli, p).status_code == 422


def test_estado_sem_recorte_de_um_cartao_mostra_traco_e_dica(admin):
    postar(admin, pacote_farol())
    h = admin.get("/farol/pl_inadimplencia?uf=AM").text
    assert h.count("só na BAP inteira") >= 4          # cartões da BAP que o estado não tem
    assert '<div class="kpi-valor">R$ 980 mil' not in h   # nunca o número da BAP inteira no cartão


def test_rotulo_nao_quebra_no_meio_do_numero():
    from app.render import junta
    assert junta("R$ 348,8 mil") == "R$ 348,8 mil" and junta("R$ 1,02 mi") == "R$ 1,02 mi"


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


def _tres():
    from farol_fixture import farol_entregas, farol_pedidos, farol_visitas
    return pacote_farol(pl_entregas=farol_entregas(), pv_pedidos=farol_pedidos(), vc_visitas=farol_visitas())


def test_tabela_do_painel_desenha_alinhada_com_total(admin):
    assert postar(admin, _tres()).status_code == 200
    h = admin.get("/farol/pl_entregas").text
    assert "Frete por estado · nov/2026" in h and 'class="rolagem rolagem-dados"' in h
    assert '<td class="num">R$ 1.250.000</td>' in h and '<td class="num">3,0%</td>' in h and '<td class="num">310</td>' in h
    assert "<tfoot>" in h and "TOTAL" in h
    assert "ainda não disponível na web" not in h


def test_pedidos_em_faixa_e_visita_sem_bloco_indisponivel(admin):
    postar(admin, _tres())
    h = admin.get("/farol/pv_pedidos").text
    assert 'class="kpis faixa"' in h and "92,0%" in h
    assert 'class="kpis"' in admin.get("/farol/pl_entregas").text
    v = admin.get("/farol/vc_visitas").text
    assert "Visitas por semana" in v and "ainda não disponível na web" not in v


def test_menu_com_os_4_farois_disponiveis(admin):
    p = _tres()
    p["relatorios"]["pl_inadimplencia"] = pacote_farol()["relatorios"]["pl_inadimplencia"]
    assert postar(admin, p).status_code == 200
    h = admin.get("/").text
    for rid in ("pv_pedidos", "vc_visitas", "pl_entregas", "pl_inadimplencia"):
        assert f'href="/farol/{rid}"' in h


def test_tabela_recusa_coluna_de_cliente_cnpj_telefone(cli):
    from farol_fixture import farol_entregas
    for nome in ("CLIENTE", "Cliente / Nome", "CNPJ", "Telefone", "WhatsApp", "E-mail"):
        e = farol_entregas()
        e["painel"]["blocos"][0]["colunas"].append({"nome": nome, "tipo": "texto"})
        assert postar(cli, pacote_farol(pl_entregas=e)).status_code == 422, nome
    e = farol_entregas()
    e["painel"]["blocos"][0]["colunas"][0] = "CNPJ"             # coluna em texto simples também
    assert postar(cli, pacote_farol(pl_entregas=e)).status_code == 422
    assert postar(cli, pacote_farol(pl_entregas=farol_entregas())).status_code == 200


def test_formato_unico_de_celula():
    from app.render import fmt_celula
    assert fmt_celula(1250000.0, "moeda") == "R$ 1.250.000"
    assert fmt_celula(None, "pct1") == "" and fmt_celula(3.04, "pct1") == "3,0%" and fmt_celula("x", "int") == "x"


def test_colunas_fora_numa_lista_so_igual_ao_contrato():
    import re
    from pathlib import Path
    from app import render, tabelas
    assert tabelas.COLUNAS_FORA is render.COLUNAS_FORA and tabelas.fmt_celula is render.fmt_celula
    contrato = Path(__file__).resolve().parents[2] / ".coord" / "contratos" / "relatorio.md"
    m = re.search(r"```text colunas-fora\n(.*?)```", contrato.read_text(encoding="utf-8"), re.S)
    if m:                                             # o contrato da branch já traz o bloco
        assert set(m.group(1).split()) == set(render.COLUNAS_FORA)
    assert render.coluna_proibida("CONTATO") and render.coluna_proibida("Razão social")
    assert not render.coluna_proibida("FRETE R$")


def test_barras_de_horario_e_duracao_nao_mostram_segundos():
    from app.render import fmt_valor
    assert fmt_valor(35280, "hora") == "09:48" and fmt_valor(1500, "min") == "25 min"
    from app.render import farol_para_tela
    from farol_fixture import farol_visitas
    v = farol_visitas()
    g = v["painel"]["blocos"][0]["grafico"]
    g["formato"], g["series"][0]["valores"] = "hora", [35280, 0, 61200]
    cols = farol_para_tela(v)["blocos"][0]["cols"]
    assert cols[0]["barras"][0]["txt"] == "09:48" and cols[2]["barras"][0]["txt"] == "17:00"


def test_tabela_numeros_perto_da_1a_coluna_e_dica_de_rolagem(admin):
    postar(admin, _tres())
    h = admin.get("/farol/pl_entregas").text
    ths = h.split("<thead>")[1].split("</thead>")[0]
    assert ths.index("FRETE R$") < ths.index("REGIÃO") and ths.index("UF") < ths.index("NOTAS")
    assert "Role para o lado" in h


def test_bloco_tabela_do_painel_igual_ao_golden_gerado_com_o_codigo_de_antes():
    import json
    from pathlib import Path
    from app import render
    from painel_tabela_fixture import blocos_tabela
    g = json.loads((Path(__file__).parent / "golden_painel_tabela.json").read_text(encoding="utf-8"))
    novos = []
    for b in blocos_tabela():
        r = render._bloco_tabela(b)
        novos.append({"titulo": r["titulo"], "cols": [[c["nome"], c["num"]] for c in r["cols"]],
                      "linhas": [[c["t"] for c in ln["cel"]] for ln in r["linhas"]],
                      "total": [c["t"] for c in r["total"]] if r["total"] else None})
    assert json.loads(json.dumps(novos, ensure_ascii=False)) == g
    assert any("—" in ln for b in g for ln in b["linhas"])            # o vazio continua "—" no Painel
