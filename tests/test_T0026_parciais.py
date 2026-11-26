"""T-0026 (robô): parciais em imagem e as 5 tabelas de resumo da Inadimplência no pacote web.

Rodado de novo sobre o main com o robô da T-0026 (#80) já dentro."""
import base64
import sys
import types
from datetime import datetime

import bap_automation as ba
import relatorios_nucleo as rn

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()


def test_parciais_web_nunca_levanta_e_sai_vazio_sem_base(tmp_path):
    assert ba.parciais_web(tmp_path, datetime(2026, 11, 20).date()) == {}


def test_parciais_web_falha_de_import_tira_todas_e_avisa_uma_vez(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "parcial_imagem", None)      # import levanta ModuleNotFoundError
    linhas = []
    assert ba.parciais_web(tmp_path, datetime(2026, 11, 20).date(), log=linhas.append) == {}
    assert linhas == ["Parciais web: fora do pacote (ModuleNotFoundError)."]


def test_parciais_web_imagem_que_falha_fica_fora_e_as_outras_vao(tmp_path, monkeypatch):
    class _Img:
        def save(self, buf, *_a, **_k):
            buf.write(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setitem(sys.modules, "parcial_imagem",
                        types.SimpleNamespace(desenhar=lambda p, escala: _Img()))
    monkeypatch.setattr(rn, "Contexto", lambda *a, **k: object())

    def _parcial(rid):
        def f(ctx, q):
            if rid == "pv_pedidos" and q == "d1":
                raise ValueError("sem dado")
            return {"quando": f"{rid} {q}"}
        return f
    for rid, nome in ba.PARCIAIS_WEB.items():
        monkeypatch.setattr(rn, nome, _parcial(rid))
    linhas = []
    saida = ba.parciais_web(tmp_path, datetime(2026, 11, 20).date(), log=linhas.append)
    assert set(saida) == set(ba.PARCIAIS_WEB)
    assert set(saida["pv_pedidos"]) == {"acum", "hoje"}            # só a d1 saiu
    for rid in ("pl_entregas", "vc_visitas"):
        assert set(saida[rid]) == set(ba.QUANDOS_PARCIAL_WEB), rid
    assert saida["pv_pedidos"]["acum"] == {"rotulo": "pv_pedidos acum", "png": PNG}
    assert linhas == ["Parciais web: pv_pedidos/d1 fora (ValueError)."]


def test_montar_pacote_sem_farol_montado_nao_cria_farol_pela_parcial():
    par = {"pv_pedidos": {"acum": {"rotulo": "x", "png": PNG}}, "vc_painel": {"acum": {}}}
    pac = ba.montar_pacote_web({}, 2026, 11, parciais=par)
    assert pac["relatorios"] == {}          # sem farol montado, nada vai (a parcial não cria farol)


def test_montar_pacote_leva_parciais_so_no_farol_que_tem(monkeypatch):
    monkeypatch.setattr(ba, "selecionar_farol_web",
                        lambda rid, rel, *a, **k: {"forma": "farol", "titulo": rid, "kpis": []})
    monkeypatch.setattr(ba, "selecionar_abas_web", lambda rel: {"abas": {}})
    monkeypatch.setattr(ba, "selecionar_paineis_web", lambda rel, r_uf=None, *a, **k: {})
    acum = {"acum": {"rotulo": "Acumulado", "png": PNG}}
    par = {"pv_pedidos": acum, "vc_painel": {"acum": {"rotulo": "y", "png": PNG}}}
    res = {"vc_painel": {"titulo": "Painel"}, "pv_pedidos": {"titulo": "Pedidos"},
           "pl_entregas": {"titulo": "Entregas"}}
    rels = ba.montar_pacote_web(res, 2026, 11, parciais=par)["relatorios"]
    assert set(rels) == {"vc_painel", "pv_pedidos", "pl_entregas"}
    assert rels["pv_pedidos"]["parciais"] == acum
    assert "parciais" not in rels["vc_painel"]             # o Painel nunca leva parcial
    assert "parciais" not in rels["pl_entregas"]           # farol sem parcial no dicionário


def test_tabela_extra_cobranca_exige_colunas_do_contrato():
    lista = ba._COLUNAS_EXTRAS_COBRANCA_WEB["Por UF"]
    ok = {"colunas": [{"nome": n, "tipo": t} for n, t in lista], "linhas": [["AM"] + [1] * 11], "total": None}
    assert ba._tabela_extra_cobranca_web(ok, "Por UF", lista)["titulo"] == "Por UF"
    torta = dict(ok, colunas=ok["colunas"][:-1])
    assert ba._tabela_extra_cobranca_web(torta, "Por UF", lista) is None
    curta = dict(ok, linhas=[["AM"] + [1] * 10])          # linha com uma célula a menos
    assert ba._tabela_extra_cobranca_web(curta, "Por UF", lista) is None
