"""T-0033 · contrato visual BC3 §6: Aderência em quadrados e o popup do Pedidos."""
import html as _h
import json
import re

from conftest import postar
from farol_fixture import pacote_tres_farois


def _popup(corpo: str) -> list:
    return json.loads(_h.unescape(re.search(r'data-pop="([^"]*)"', corpo).group(1)))


def test_T0033_aderencia_vendedor_quadrados_e_acum_com_supervisor_no_popup(admin):
    """§6.3: Aderência = VENDEDOR · um quadrado por dia útil · % ACUM.; o SUPERVISOR vai ao popup."""
    assert postar(admin, pacote_tres_farois()).status_code == 200
    corpo = admin.get("/farol/vc_visitas?aba=aderencia").text.split("<main")[1]
    cab = corpo.split("<thead>")[1].split("</thead>")[0]
    assert re.search(r'<th class=" oc"><a [^>]*>SUPERVISOR', cab) and re.search(r'<th class=""><a [^>]*>VENDEDOR', cab)
    assert " ader" in corpo and "% ADERÊNCIA ACUM." in cab
    blocos = _popup(corpo)
    assert blocos[0][0] == "Supervisor" and blocos[0][1][0][0] == "SUPERVISOR"


def test_T0033_popup_do_pedidos_leva_cliente_credito_e_pedido(admin):
    """Item 4 da conferência: o que o contrato manda para o popup do Pedidos está nele."""
    assert postar(admin, pacote_tres_farois()).status_code == 200
    corpo = admin.get("/farol/pv_pedidos?aba=pedidos").text.split("<main")[1]
    blocos = {t: [c for c, _ in cols] for t, cols in _popup(corpo)}
    assert {"RAZÃO SOCIAL", "CÓD."} <= set(blocos["Cliente"])
    assert {"LIMITE", "DISP.", "ATRASO", "COND. PAGTO"} <= set(blocos["Crédito"])
    assert {"ANÁLISE CRÉDITO", "SITUAÇÃO", "VENDEDOR", "VOL.", "R$ TABELA", "FILIAL", "PRAZO"} <= set(blocos["Pedido"])


def test_T0033_faixa_do_celular_tem_altura_fixa_e_abas_sem_corte():
    """Item 3 e abas da Visita: a faixa reserva linha do estado e 2 linhas de números; as abas quebram, não cortam."""
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    assert ".bc3-tt{min-height:100px}" in css and "grid-auto-rows:54px;min-height:118px" in css
    assert ".bc3-abas{display:flex;gap:4px;align-self:stretch;min-width:0;overflow:visible;flex-wrap:wrap}" in css
