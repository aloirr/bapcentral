"""T-0024: pacote web dos 5 faróis do lote 2 (colunas livres). Dados fictícios.

Sem o lote 2 no robô (PR #91 ainda fora do main), o módulo é pulado: o PR do
testes passa em qualquer ordem de merge."""
import pytest

import bap_automation as ba

if not hasattr(ba, "RIDS_LIVRES_WEB"):
    pytest.skip("o robô não tem o lote 2 (PR #91)", allow_module_level=True)


def test_params_por_farol():
    assert ba.params_farol_web("pv_indicadores", 2026, 11) == {"MÊS": "2026-11"}
    assert ba.params_farol_web("vc_base", 2026, 3) == {"ANO": "2026", "MÊS": "3"}


def test_lote2_esta_em_FAROIS_WEB_e_nas_tabelas():
    for rid in ba.RIDS_LIVRES_WEB:
        assert rid in ba.FAROIS_WEB and rid in ba.RIDS_TABELAS_WEB


def test_tabela_livre_corta_colunas_que_nunca_vao_e_limpa_cliente():
    cols = [{"nome": "FILIAL", "tipo": "texto"}, {"nome": "CLIENTE", "tipo": "texto"},
            {"nome": "TELEFONE", "tipo": "texto"}, {"nome": "ENDEREÇO", "tipo": "texto"},
            {"nome": "Nº", "tipo": "texto"}, {"nome": "_I", "tipo": "int", "oculta": True},
            {"nome": "VENDA", "tipo": "moeda"}]
    linhas = [["MANAUS", "000001 - LOJA TESTE", "9299999", "RUA X", "10", 1, 5.0],
              ["BELÉM", "000002 - OUTRA", "9288888", "RUA Y", "20", 2, 6.0]]
    t = ba.tabela_web7("vc_base", {"titulo": "Clientes", "colunas": cols, "linhas": linhas,
                                   "tons": ["", ""], "filtros": [{"coluna": "FILIAL"}]})
    assert [c["nome"] for c in t["colunas"]] == ["FILIAL", "CLIENTE", "VENDA"]
    assert t["linhas"][0][0] == "MANAUS" and len(t["linhas"][0]) == 3
    assert "9299999" not in str(t) and "RUA" not in str(t)


def test_tabela_livre_com_tipo_desconhecido_fica_fora():
    t = ba.tabela_web7("pl_frw", {"titulo": "Estoque FRW", "colunas": [{"nome": "A", "tipo": "xyz"}],
                                  "linhas": [], "tons": []})
    assert t is None


def test_selo_torto_vai_sem_selo():
    cols = [{"nome": "SLA", "tipo": "int", "chip": [[1, "x"]]}]
    t = ba.tabela_web7("pl_giro", {"titulo": "Ruptura", "colunas": cols, "linhas": [[3]], "tons": [""]})
    assert t and "chip" not in t["colunas"][0]


def test_farol_sem_painel_leva_os_graficos_do_pc():
    r = {"titulo": "Painel de indicadores", "kpis": [{"rotulo": "a", "valor": "1", "cor": "ok"}],
         "graficos": [{"titulo": "G", "rotulos": ["a", "b"], "series": [{"nome": "s", "valores": [1, 2], "cor": "#62BB47"}],
                       "formato": "pct"}], "avisos": []}
    v = ba.selecionar_farol_web("pv_indicadores", r)
    assert [b["tipo"] for b in v["painel"]["blocos"]] == ["barras"]
