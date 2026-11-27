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


def test_T0033_faixa_do_celular_altura_fixa_abas_mais_e_filtro_sem_corte():
    """Parecer UX C2/C3/C11/C12: seletor de estado sempre no mesmo lugar (desligado nas abas da BAP), 3 abas + Mais."""
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    assert "grid-auto-rows:auto;min-height:112px" in css and ".bc3-mais[hidden]{display:none!important}" in css
    assert ".bc3-abas a.so-pc{display:none}" in css and ".bc3 .filtros-det>summary::after" in css


def test_T0033_abas_mais_e_seletor_de_estado_desligado(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    h = admin.get("/farol/vc_visitas?aba=cliente").text
    assert h.count("Sem filtro por estado") == 1 and 'class="bc3-uf' not in h.split("<main")[0].split("bc3-main")[1]
    assert 'class="bc3-mais-abas"' in h and h.count(" so-pc") >= 3          # celular: 3 abas e as outras em "Mais"
    h = admin.get("/farol/pv_pedidos?aba=solicitacao").text                  # aba só da BAP: o seletor fica, desligado
    assert 'class="bc3-uf bc3-uf-off"' in h and "<span>AM</span>" in h


def test_T0033_ordem_da_grade_e_total_com_rotulo(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    h = admin.get("/farol/pl_entregas?aba=entregas").text
    cab = re.findall(r"<th class=\"[^\"]*\"><a [^>]*>([^<▲▼]+)", h.split("<thead>")[1].split("</thead>")[0])
    assert cab[0].strip() == "NF"                                           # a chave abre a grade (contrato §6.2)
    h = admin.get("/farol/vc_visitas?aba=vendedor").text
    assert "<tfoot><tr><td class=\"\"><b>Total</b>" in h
