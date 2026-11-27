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
    kpis = [{"valor": "R$ 980 mil", "detalhe": "45% dos pedidos", "linhas": [{"rot": "Acima de 90 dias", "valor": "R$ 310 mil"}]},
            {"valor": "10", "detalhe": "5 atrasado(s)", "linhas": []}, {"valor": "100%", "detalhe": "", "linhas": []}]
    ins = [{"tom": "info", "texto": "Recebido no mês: R$ 980 mil."},
           {"tom": "alerta", "texto": "Em aberto: 10 (5 atrasados)."},
           {"tom": "alerta", "texto": "Atraso acima de 90 dias soma R$ 310 mil (45%)."},
           {"tom": "alerta", "texto": "12 clientes acima de 90 dias somam R$ 310 mil."},
           {"tom": "alerta", "texto": "Vendedor 03 com 100% da carteira vencida."},
           {"tom": "info", "texto": "Pedidos digitados subiram."}]
    assert [i["texto"] for i in render.sem_repeticao(ins, kpis)] == [
        "12 clientes acima de 90 dias somam R$ 310 mil.", "Vendedor 03 com 100% da carteira vencida.",
        "Pedidos digitados subiram."]


def test_T0020_so_a_razao_social_sai_e_so_com_fantasia_preenchida():
    tab = {"cols": [{"nome": "PEDIDO"}, {"nome": "PED. MÁX."}, {"nome": "RAZÃO SOCIAL"}, {"nome": "FANTASIA"},
                    {"nome": "DT. PREVISTA"}, {"nome": "DT. REAL"}, {"nome": "UF"}, {"nome": "FILIAL"}],
           "linhas": [_cel("1", "1", "A LTDA", "A", "20/11", "20/11", "AM", "AM")]}
    assert tabelas.colunas_ocultas(tab) == {2}             # coluna igual por coincidência fica
    tab["linhas"].append(_cel("2", "2", "B LTDA", "", "21/11", "21/11", "PA", "PA"))
    assert tabelas.colunas_ocultas(tab) == set()           # FANTASIA vazia numa linha: a RAZÃO SOCIAL fica
    assert tabelas.colunas_ocultas({"cols": [{"nome": "RAZÃO SOCIAL"}], "linhas": []}) == set()


def test_T0020_pedidos_juntas_lado_a_lado_titulo_sem_aba_e_sem_rotulo_estado(admin):
    assert postar(admin, pacote_tres_farois()).status_code == 200
    h = admin.get("/farol/pv_pedidos?aba=pedidos").text
    corpo = h.split("<main")[1]
    assert '<div class="juntas bc3-juntas">' in corpo and corpo.count('<details class="junta bc3-junta"') == 3   # T-0030
    assert "<h1>Farol de Pedidos</h1>" in corpo and "Farol de Pedidos · Pedidos" not in corpo
    assert '<span class="f-rot">Estado</span>' not in corpo
    import re
    ocultas = re.findall(r'<th class="[^"]*\boc\b[^"]*"><a [^>]*>([^<]+)</a>', corpo)
    assert "RAZÃO SOCIAL" in ocultas and "FANTASIA" not in ocultas   # T-0028: FANTASIA fica; o resto vai ao popup
    assert "DT. PED" not in ocultas and "FATURAR ATÉ" not in ocultas


def test_T0020_baixado_do_erp_so_quando_difere_do_pacote(admin):
    p = pacote_farol()
    p["relatorios"]["pl_inadimplencia"]["baixado_em"] = "2026-11-22T18:27:00-04:00"
    assert postar(admin, p).status_code == 200
    assert "Baixado do ERP em 22/11/2026 18:27" in admin.get("/farol/pl_inadimplencia").text
    assert render.datas_proximas("2026-11-24T08:58:00-04:00", "2026-11-24T09:01:00-04:00")
    assert not render.datas_proximas("2026-11-22T18:27:00-04:00", "2026-11-24T08:30:00-04:00")


def test_T0020_visual_c_marca_bap_sem_azul_nem_laranja():
    """T-0033: o logo inteiro vem de arquivo (não mais embutido) e as cores só existem como token do :root."""
    bloco = CSS.split("/* T-0020 · visual C")[1]
    assert "url(/static/logo_bap.png)" in bloco and "var(--verde-escuro)" in bloco
    for cor in ("#0b3a6b", "#e8590c"):                      # azul-marinho e laranja de antes
        assert cor not in CSS.lower()


def test_T0028_juntas_numa_linha_so_no_pc_e_empilhadas_no_celular():
    """T-0028 (T-0033/RD-0036): Gerar ID CD, Reversa e Analítico lado a lado no PC; no celular uma embaixo da outra,
    e a regra do celular vem DEPOIS da do PC (antes a do PC, repetida, vencia e deixava 3 colunas de 110 px)."""
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    pc = css.index(".bc3-juntas{margin:10px 0 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(0,1fr))")
    cel = css.index(".bc3-juntas{grid-template-columns:1fr}")
    assert css.count(".bc3-juntas{grid-template-columns:repeat(auto-fit") == 0 and pc < cel
    assert ".juntas{display:flex" not in css            # a camada antiga (flex) saiu: só a grade do BC3 manda (RD-0045)
    assert css.index("@media(max-width:700px){", pc) < cel


def test_T0028_pedidos_sem_rolagem_com_popup_e_juntas_enxutas(admin):
    """T-0028: tabela de Pedidos sem rolagem, colunas extras só no popup (data-pop), script do popup na página e
    as tabelas de baixo sem UF, CIDADE, FORN. e CLIENTE (o popup já mostra)."""
    import json, html as _h, re
    assert postar(admin, pacote_tres_farois()).status_code == 200
    h = admin.get("/farol/pv_pedidos?aba=pedidos").text
    corpo = h.split("<main")[1]
    assert 'rolagem-dados sem-rolagem' in corpo and '/static/popup_linha.js' in corpo and 'id="pop-linha"' in corpo
    pops = re.findall(r'data-pop="([^"]*)"', corpo)
    assert pops
    blocos = json.loads(_h.unescape(pops[0]))                  # T-0033: o popup vem em blocos [título, [[coluna, valor]]]
    assert [b[0] for b in blocos] == ["Cliente", "Crédito", "Pedido"]
    nomes = [c for _, cols in blocos for c, _v in cols]
    assert "LIMITE" in nomes and "COND. PAGTO" in nomes        # vai ao popup
    cab = corpo.split('<table')[1].split('</thead>')[0]
    assert '<th class=" oc"><a' in cab or ' oc"' in cab           # e sai da grade
    juntas = corpo.split('<div class="juntas bc3-juntas">')[1]
    assert juntas.count('<th class=" oc">CIDADE</th>') + juntas.count('<th class=" oc">UF</th>') >= 2
