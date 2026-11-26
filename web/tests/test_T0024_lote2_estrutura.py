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
