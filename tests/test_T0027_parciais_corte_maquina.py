"""T-0027: (a) parcial no pacote só no farol que a tem, nunca no vc_painel; (b) o corte do pacote grande começa
pela imagem da parcial; (c) a máquina oficial do pós-venda é o notebook. Dados fictícios.

(b) e (c) entram antes do código (ordem testes -> modulo-robo/modulo-posvenda): `xfail` não estrito, ficam
verdes antes e depois."""
import base64
import copy
import json

import pytest

import bap_automation as ba
import pos_venda as pv
from test_T0013_pacote_web import _vc_painel_ficticio
from test_T0017_farol_web_robo import _farol

AGORA = ba._agora_manaus() if hasattr(ba, "_agora_manaus") else None
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 200_000).decode()
PARCIAL = {q: {"rotulo": q, "png": PNG} for q in ("acum", "d1", "hoje")}


def _farol_pedidos():
    return {**_farol(), "id": "pv_pedidos", "titulo": "Farol de Pedidos"}


def test_parcial_vai_no_farol_que_a_tem_e_nunca_no_vc_painel():
    res = {"vc_painel": _vc_painel_ficticio(), "pv_pedidos": _farol_pedidos()}
    pac = ba.montar_pacote_web(res, 2026, 11, AGORA, parciais={"pv_pedidos": PARCIAL, "vc_painel": PARCIAL})
    assert pac["relatorios"]["pv_pedidos"]["parciais"] == PARCIAL
    assert "parciais" not in pac["relatorios"]["vc_painel"]
    assert "parciais" not in json.dumps(pac["relatorios"]["vc_painel"])


def test_farol_sem_parcial_no_dicionario_sai_sem_a_chave():
    pac = ba.montar_pacote_web({"pv_pedidos": _farol_pedidos()}, 2026, 11, AGORA, parciais={"pl_entregas": PARCIAL})
    assert "parciais" not in pac["relatorios"]["pv_pedidos"]


def _pacote_grande():
    pac = ba.montar_pacote_web({"pv_pedidos": _farol_pedidos()}, 2026, 11, AGORA, parciais={"pv_pedidos": PARCIAL})
    rel = pac["relatorios"]["pv_pedidos"]
    rel["tabelas"] = [{"titulo": "Cliente a cliente", "colunas": [{"nome": "A", "tipo": "texto"}],
                       "linhas": [["x" * 40]] * 300, "tons": [""] * 300}]
    return pac


@pytest.mark.xfail(strict=False, reason="T-0027 (robô): o corte começa pela imagem da parcial")
def test_corte_do_pacote_grande_tira_a_parcial_primeiro():
    pac = _pacote_grande()
    sem_parcial = copy.deepcopy(pac)
    sem_parcial["relatorios"]["pv_pedidos"].pop("parciais")
    MB = 1024 * 1024
    teto = (ba._tamanho_pacote_web(sem_parcial) + 2000) / MB      # cabe sem a imagem, com a tabela
    cortado = ba._cortar_pacote_web(pac, teto_mb=teto)["relatorios"]["pv_pedidos"]
    assert "parciais" not in cortado
    assert [t["titulo"] for t in cortado["tabelas"]] == ["Cliente a cliente"]      # a tabela ficou
    assert any("parciais em imagem" in a for a in cortado["avisos"])
    assert "parciais" in pac["relatorios"]["pv_pedidos"]                           # a entrada não mudou


def test_so_a_maquina_oficial_grava_o_pos_venda(monkeypatch):
    monkeypatch.setattr(pv, "maquina", lambda: pv.MAQUINA_DO_POS_VENDA.upper())
    assert pv.pode_gravar_aqui()
    monkeypatch.setattr(pv, "maquina", lambda: "OUTRA-MAQUINA")
    assert not pv.pode_gravar_aqui()


@pytest.mark.xfail(strict=False, reason="T-0027 (pós-venda): o robô oficial passa a ser o notebook")
def test_maquina_oficial_do_pos_venda_e_o_notebook():
    assert pv.MAQUINA_DO_POS_VENDA == "NT-AMADMVD13"
