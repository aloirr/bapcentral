"""T-0026 (robô): parciais em imagem e as 5 tabelas de resumo da Inadimplência no pacote web.

Rodado de novo sobre o main com o robô da T-0026 (#80) já dentro."""
import base64
from datetime import datetime

import bap_automation as ba


def test_parciais_web_nunca_levanta_e_sai_vazio_sem_base(tmp_path):
    assert ba.parciais_web(tmp_path, datetime(2026, 11, 20).date()) == {}


def test_montar_pacote_leva_parciais_so_dos_3_farois():
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    par = {"pv_pedidos": {"acum": {"rotulo": "x", "png": png}}, "vc_painel": {"acum": {}}}
    pac = ba.montar_pacote_web({}, 2026, 11, parciais=par)
    assert pac["relatorios"] == {}          # sem farol montado, nada vai (a parcial não cria farol)


def test_tabela_extra_cobranca_exige_colunas_do_contrato():
    lista = ba._COLUNAS_EXTRAS_COBRANCA_WEB["Por UF"]
    ok = {"colunas": [{"nome": n, "tipo": t} for n, t in lista], "linhas": [["AM"] + [1] * 11], "total": None}
    assert ba._tabela_extra_cobranca_web(ok, "Por UF", lista)["titulo"] == "Por UF"
    torta = dict(ok, colunas=ok["colunas"][:-1])
    assert ba._tabela_extra_cobranca_web(torta, "Por UF", lista) is None
