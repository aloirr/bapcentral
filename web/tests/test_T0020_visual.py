"""T-0020 (decisões do Alexandre em 25/11/2026): visual C (cores e logo da BAP AUTOPARTS), tabelas de baixo
lado a lado como no farol do PC e as repetições cortadas (cartão vazio, frase que repete cartão, título com a
aba, rótulo "Estado", coluna que só repete outra, segunda data)."""
from __future__ import annotations

from pathlib import Path

from conftest import postar
from farol_fixture import pacote_farol, pacote_tres_farois

from app import render, tabelas

CSS = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")


def _cel(*vals):
    return {"cel": [{"t": v} for v in vals]}


def test_T0020_cartao_so_com_traco_nao_aparece():
    assert render.cartao_vazio({"valor": "—", "detalhe": "", "linhas": [], "estados": None})
    assert not render.cartao_vazio({"valor": "—", "detalhe": "só na BAP inteira", "linhas": [], "estados": None})
    assert not render.cartao_vazio({"valor": "R$ 0", "detalhe": "", "linhas": [], "estados": None})
    assert render.kpis_para_tela([{"rotulo": "Clientes", "valor": "—"}, {"rotulo": "Em atraso", "valor": "10"}]) \
        == [render._kpi({"rotulo": "Em atraso", "valor": "10"})]


def test_T0020_resumo_nao_repete_numero_de_cartao():
    kpis = [{"valor": "R$ 980 mil", "detalhe": "45% dos pedidos", "linhas": [{"valor": "R$ 310 mil"}]}]
    ins = [{"tom": "info", "texto": "Recebido no mês: R$ 980 mil."},
           {"tom": "alerta", "texto": "Atraso acima de 90 dias soma R$ 310 mil (45%)."},
           {"tom": "alerta", "texto": "5 pedidos fora do prazo (R$ 5.837)."},
           {"tom": "info", "texto": "Pedidos digitados subiram."}]
    assert [i["texto"] for i in render.sem_repeticao(ins, kpis)] == [
        "5 pedidos fora do prazo (R$ 5.837).", "Pedidos digitados subiram."]


def test_T0020_coluna_que_so_repete_outra_e_razao_social_com_fantasia():
    tab = {"cols": [{"nome": "PEDIDO"}, {"nome": "PED. MÁX."}, {"nome": "RAZÃO SOCIAL"}, {"nome": "FANTASIA"},
                    {"nome": "QTD", "num": True}, {"nome": "ATENDIDO", "num": True}, {"nome": "OBS"}, {"nome": "OBS 2"}],
           "linhas": [_cel("1", "1", "A LTDA", "A", "2", "2", "", ""), _cel("2", "2", "B LTDA", "B", "3", "3", "", "")]}
    assert tabelas.colunas_ocultas(tab) == {1, 2}          # número igual e coluna vazia ficam
    tab["linhas"][1]["cel"][1]["t"] = "9"
    assert tabelas.colunas_ocultas(tab) == {2}             # PED. MÁX. diferente em uma linha: fica
    assert tabelas.colunas_ocultas({"cols": [{"nome": "RAZÃO SOCIAL"}], "linhas": []}) == set()


def test_T0020_pedidos_juntas_lado_a_lado_titulo_sem_aba_e_sem_rotulo_estado(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    h = admin.get("/farol/pv_pedidos?aba=pedidos").text
    corpo = h.split("<main")[1]
    assert '<div class="juntas">' in corpo and corpo.count('<section class="junta">') == 3
    assert "<h1>Farol de Pedidos</h1>" in corpo and "Farol de Pedidos · Pedidos" not in corpo
    assert '<span class="f-rot">Estado</span>' not in corpo
    assert 'class=" oc"' in corpo or ' oc"' in corpo       # RAZÃO SOCIAL escondida (há FANTASIA)


def test_T0020_baixado_do_erp_so_quando_difere_do_pacote(admin):
    p = pacote_farol()
    p["relatorios"]["pl_inadimplencia"]["baixado_em"] = "2026-11-22T18:27:00-04:00"
    assert postar(admin, p).status_code == 200
    assert "Baixado do ERP em 22/11/2026 18:27" in admin.get("/farol/pl_inadimplencia").text


def test_T0020_visual_c_marca_bap_sem_azul_nem_laranja():
    bloco = CSS.split("/* T-0020 · visual C")[1]
    assert "data:image/png;base64," in bloco and "#2F7D32" in bloco and ".juntas{display:flex" in bloco
    for cor in ("#0b3a6b", "#e8590c"):                      # azul-marinho e laranja de antes
        assert cor not in bloco.lower()
