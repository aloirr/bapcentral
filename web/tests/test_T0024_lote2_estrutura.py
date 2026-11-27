"""T-0024: a fixture dos 5 faróis do lote 2 tem as abas e colunas reais do robô e só valores fictícios."""
import re

from conftest import postar
from lote2_fixture import RIDS, pacote_lote2

from app import pacotes, tabelas

ABAS = {
    "pv_indicadores": ["Semana a semana", "Mês a mês", "Base com compra (mês a mês)", "Base com compra em NOV/26, por segmento"],
    "vc_base": ["Por UF", "Por segmento", "Por cidade", "Por vendedor", "Por supervisor", "Por família (6 meses)",
                "Por produto (top 400, 6 meses)", "Clientes"],
    "vc_planner": ["Por zona", "Por vendedor", "Por supervisor", "Por segmento", "Por UF", "Por cidade", "Por cliente",
                   "Calendário"],
    "pl_giro": ["Resumo por filial", "Ruptura", "Curva A parada", "Necessidade de compra", "Por família",
                "Por categoria", "Todos os produtos"],
    "pl_frw": ["Estoque FRW"],
}
FICTICIO = re.compile(r"FICTICI|^9\d{5}$|^Z\d\d$")


def test_pacote_do_lote2_valida_com_as_abas_do_robo():
    p = pacote_lote2()
    assert pacotes.validar(p) == []
    assert tuple(p["relatorios"]) == RIDS
    for rid, abas in ABAS.items():
        assert [t["titulo"] for t in p["relatorios"][rid]["tabelas"]] == abas, rid


def test_colunas_do_planner_sao_de_rota_e_do_giro_de_produto():
    p = pacote_lote2()["relatorios"]
    nomes = lambda rid, aba: [c["nome"] for t in p[rid]["tabelas"] if t["titulo"] == aba for c in t["colunas"]]
    assert "CAPACIDADE/DIA" in nomes("vc_planner", "Por vendedor") and "VISITAS/MÊS" in nomes("vc_planner", "Por zona")
    assert "VENDA" not in nomes("vc_planner", "Por zona") and "ESTOQUE" not in nomes("vc_planner", "Por zona")
    assert "COB (DIAS)" in nomes("pl_giro", "Todos os produtos")


def test_valores_de_texto_sao_ficticios():
    p = pacote_lote2()["relatorios"]
    livres = {"UF", "CIDADE", "FILIAL", "STATUS", "STATUS PROTHEUS", "SITUAÇÃO PLANNER", "CURVA", "COM LIMITE", "INADIMPLENTE",
              "COMPRADOR", "COMPROU NO MÊS", "VISÃO", "SEMANA", "DIA", "VISITA", "DATAS DAS VISITAS", "PERÍODO", "MÊS",
              "SITUAÇÃO", "AÇÃO", "ZONA"}
    for rid, r in p.items():
        for t in r["tabelas"]:
            for k, c in enumerate(t["colunas"]):
                if c["tipo"] != "texto" or c["nome"] in livres or c["nome"] == "TOTAL":
                    continue
                for ln in t["linhas"]:
                    assert FICTICIO.search(str(ln[k])), (rid, t["titulo"], c["nome"], ln[k])


def test_web_mostra_as_abas_reais_para_admin(admin):
    assert postar(admin, pacote_lote2()).status_code == 200
    for rid, abas in ABAS.items():
        assert [t for _, t in tabelas.abas_do_farol(rid, pacote_lote2()["relatorios"][rid])] == abas
        assert admin.get(f"/farol/{rid}").status_code == 200


# ---------------------------------------------------------------- parecer de UX (R1 a R5)
def test_GRADE_do_lote2_tem_ate_10_colunas_e_so_colunas_do_robo():
    p = pacote_lote2()["relatorios"]
    for (rid, titulo), g in tabelas.GRADE.items():
        if rid not in tabelas.FAROIS_LIVRES:      # Pedidos, Entregas, Inadimplência e Visita: T-0033; Analista: T-0036
            continue
        t = next(x for x in p[rid]["tabelas"] if x["titulo"] == titulo)
        nomes = [c["nome"] for c in t["colunas"] if not c.get("oculta")]
        assert len(g["grade"]) <= 10, (rid, titulo)
        assert g["chave"] in g["grade"] and all(c in g["grade"] for c in g["cel"] if c), (rid, titulo)
        faltando = [c for c in g["grade"] if c not in [x["nome"] for x in t["colunas"]]]
        assert not faltando, (rid, titulo, faltando)
        assert len([n for n in nomes if n in g["grade"]]) <= 10


def test_abas_curtas_sem_mes_na_url_e_sem_quebra(admin):
    p = pacote_lote2()
    assert postar(admin, p).status_code == 200
    abas = dict(tabelas.abas_do_farol("pv_indicadores", p["relatorios"]["pv_indicadores"]))
    assert "base-por-segmento" in abas and not any("nov" in c for c in abas)
    h = admin.get("/farol/vc_base").text
    nav = re.search(r'<nav class="bc3-abas".*?</nav>', h, re.S).group(0)
    assert ">UF<" in nav and ">Produto<" in nav and "top 400" not in nav and "6 meses" not in nav
    assert admin.get("/farol/vc_base?aba=uf").status_code == 200


def test_busca_com_dica_da_tabela_e_sem_busca_em_tabela_curta(admin):
    assert postar(admin, pacote_lote2()).status_code == 200
    assert 'placeholder="Buscar cliente ou cidade"' in admin.get("/farol/vc_base?aba=clientes").text
    assert 'placeholder="Buscar produto"' in admin.get("/farol/pl_frw?aba=estoque-frw").text
    assert 'class="bc3-busca"' not in admin.get("/farol/pv_indicadores?aba=semana-a-semana").text      # 12 linhas
    assert 'class="bc3-busca"' not in admin.get("/farol/vc_base?aba=uf").text                           # 5 linhas
    assert "Buscar pedido" not in admin.get("/farol/pl_giro?aba=todos-os-produtos").text


def test_aviso_sem_filtro_por_estado_nao_aparece_no_lote2(admin):
    assert postar(admin, pacote_lote2()).status_code == 200
    for rid in ("vc_base", "pv_indicadores"):
        assert "Sem filtro por estado" not in admin.get(f"/farol/{rid}").text


def test_resumo_um_cartao_por_metrica_com_dia_semana_mes(admin):
    assert postar(admin, pacote_lote2()).status_code == 200
    h = admin.get("/farol/vc_base").text
    assert h.count('class="graf graf-per"') == 3 and "dia a dia" not in h.split('class="graficos"')[1]
    for rot in ("Dia", "Semana", "Mês"):
        assert f'class="per-l per-l{["Dia", "Semana", "Mês"].index(rot) + 1}">{rot}<' in h


def test_grade_esconde_colunas_e_abre_popup_na_chave(admin):
    assert postar(admin, pacote_lote2()).status_code == 200
    h = admin.get("/farol/pl_giro?aba=necessidade-de-compra").text
    assert 'class="sel-link"' in h and re.search(r'data-tit="[^"]*900001"', h)   # T-0033: o popup é o `popup_linha.js`
    cab = re.search(r"<thead>.*?</thead>", h.split('class="bc3-corpo"')[1], re.S).group(0)
    assert cab.count('class="oc') + cab.count(' oc"') >= 1            # colunas fora da grade ficam só no popup
    assert "SUGESTÃO" in re.sub(r'<th class="[^"]*\boc\b[^"]*">.*?</th>', "", cab, flags=re.S)


def test_diretor_so_o_resumo_e_sem_faixa_de_abas_vazia(admin):
    assert postar(admin, pacote_lote2()).status_code == 200
    from test_abas import _cli_de
    d = _cli_de(admin, "diretor")
    h = d.get("/farol/pl_giro").text
    assert d.get("/farol/pl_giro?aba=por-filial").status_code == 403
    assert 'class="bc3-sub"' not in h


# ---------------------------------------------------------------- reteste de UX (N1 a N3)
def _tot(t):
    return dict(zip([c["nome"] for c in t["colunas"]], t["total"]))


def test_faixa_e_total_saem_da_mesma_conta_das_linhas():
    p = pacote_lote2()["relatorios"]
    tab = lambda rid, titulo: next(t for t in p[rid]["tabelas"] if t["titulo"] == titulo)
    cartao = lambda rid, rot: next(k["valor"] for k in p[rid]["kpis"] if k["rotulo"] == rot)
    for aba in ("Por UF", "Por segmento", "Por cidade", "Por vendedor", "Por supervisor"):
        t = _tot(tab("vc_base", aba))
        assert (t["CLIENTES"], t["ATIVOS"], t["COMPRARAM NO MÊS"]) == (2930, 2410, 1540), aba
    assert cartao("vc_base", "Clientes") == "2.930" and cartao("vc_base", "Compraram no mês") == "1.540"
    pf = tab("pl_giro", "Resumo por filial")
    col = lambda t, n: [ln[[c["nome"] for c in t["colunas"]].index(n)] for ln in t["linhas"]]
    assert sum(col(pf, "ITENS EM RUPTURA")) == len(tab("pl_giro", "Ruptura")["linhas"]) == 24
    assert sum(col(pf, "ITENS A COMPRAR")) == len(tab("pl_giro", "Necessidade de compra")["linhas"]) == 32
    assert cartao("pl_giro", "Em ruptura") == "24" and cartao("pl_giro", "Comprar") == "32"
    assert len(set(col(pf, "FILIAL"))) == 6 == len(p["pl_giro"]["recortes"])            # uma filial por UF do filtro
    assert "MT" in p["pl_giro"]["recortes"] and "MT" in p["pl_frw"]["recortes"]


def test_cartao_do_estado_e_a_linha_do_estado_na_tabela():
    r = pacote_lote2()["relatorios"]["vc_base"]
    uf = next(t for t in r["tabelas"] if t["titulo"] == "Por UF")
    nomes = [c["nome"] for c in uf["colunas"]]
    for ln in uf["linhas"]:
        v = r["recortes"][ln[0]]["kpis"]
        assert next(k["valor"] for k in v if k["rotulo"] == "Clientes") == f"{ln[nomes.index('CLIENTES')]:,}".replace(",", ".")


def test_numeros_coerentes_por_linha():
    p = pacote_lote2()["relatorios"]
    for t in p["pv_indicadores"]["tabelas"][:2]:
        n = [c["nome"] for c in t["colunas"]]
        for ln in t["linhas"]:
            d = dict(zip(n, ln))
            assert d["NO PRAZO"] + d["ATRASO"] + d["PARCIAL"] == d["PEDIDOS"] and d["ENTREGUES"] <= d["PEDIDOS"]
    mes = p["pv_indicadores"]["tabelas"][1]
    assert [ln[0] for ln in mes["linhas"]][-1] == "NOV/26" and "DEZ/26" not in [ln[0] for ln in mes["linhas"]]
    cl = next(t for t in p["vc_base"]["tabelas"] if t["titulo"] == "Clientes")
    n = [c["nome"] for c in cl["colunas"]]
    for ln in cl["linhas"]:
        d = dict(zip(n, ln))
        assert d["EM ATRASO"] <= d["LIMITE DISP."] and d["LIMITE DISP."] != d["EM ATRASO"] or d["EM ATRASO"] == 0
    pc = next(t for t in p["vc_planner"]["tabelas"] if t["titulo"] == "Por cliente")
    n = [c["nome"] for c in pc["colunas"]]
    from datetime import date
    for ln in pc["linhas"]:
        d = dict(zip(n, ln))
        assert d["DIA"] == ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"][date.fromisoformat(d["DATA"]).weekday()]
    pv = next(t for t in p["vc_planner"]["tabelas"] if t["titulo"] == "Por vendedor")
    n = [c["nome"] for c in pv["colunas"]]
    assert all(dict(zip(n, ln))["CLIENTES/DIA"] <= dict(zip(n, ln))["CAPACIDADE/DIA"] for ln in pv["linhas"])


def test_resumo_sem_grafico_repetido_e_sem_rolagem_lateral_no_cartao(admin):
    assert postar(admin, pacote_lote2()).status_code == 200
    h = admin.get("/farol/pl_giro").text
    corpo = h.split('class="graficos"')[1]
    assert corpo.count('class="graf graf-per"') == 2                  # "Unidades vendidas" repete "Venda (unidades)"
    assert corpo.count("Venda perdida prevista") == 1                  # só o de barras


def test_nome_unico_por_linha_nas_tabelas_por_dimensao_e_faixa_soma_o_mes():
    p = pacote_lote2()["relatorios"]
    for rid, aba, nome in (("vc_base", "Por vendedor", "VENDEDOR"), ("vc_base", "Por segmento", "SEGMENTO"),
                           ("vc_base", "Por supervisor", "SUPERVISOR"), ("vc_planner", "Por vendedor", "VENDEDOR"),
                           ("vc_planner", "Por supervisor", "SUPERVISOR")):
        t = next(x for x in p[rid]["tabelas"] if x["titulo"] == aba)
        i = [c["nome"] for c in t["colunas"]].index(nome)
        nomes = [ln[i] for ln in t["linhas"]]
        assert len(nomes) == len(set(nomes)), (rid, aba)
    for b in p["vc_planner"]["painel"]["blocos"]:                   # gráficos por vendedor: rótulo único
        if b.get("tipo") == "hbarras":
            assert len(b["rotulos"]) == len(set(b["rotulos"])), b["titulo"]
    ind = p["pv_indicadores"]
    sem = next(t for t in ind["tabelas"] if t["titulo"] == "Semana a semana")
    mes = next(t for t in ind["tabelas"] if t["titulo"] == "Mês a mês")
    i = [c["nome"] for c in sem["colunas"]].index("PEDIDOS")
    assert mes["linhas"][-1][i] == sum(ln[i] for ln in sem["linhas"][-4:])
    faixa = next(k["valor"] for k in ind["kpis"] if k["rotulo"] == "Pedidos faturados · NOV/26")
    assert faixa == f"{mes['linhas'][-1][i]:,}".replace(",", ".")
