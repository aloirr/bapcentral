"""T-0037 — Farol de Fretes: o "% do faturado" pelo LÍQUIDO (RN-POS-009,
RN-GER-002) nos limites, e a UF do faturado normalizada (RN-GER-006).

- Líquido do mês/UF <= 0 (devolução >= venda): o cartão "% do faturado"
  mostra "—", nunca percentual negativo ou absurdo (painel_farol.
  pct_do_liquido devolve None).
- UF do cliente com espaço/minúscula (" am"): rn.uf_norm (strip +
  maiúsculas) na linha, no faturado, no recorte do kpis_fretes e no Por UF;
  " am" junta com "AM" em todo lugar: uf_norm direto, rotulo_agrupa_fretes
  ("AM" e "CIDADE / AM") e o recorte da web do robô (chave "AM").
Tudo fictício (tmp_path, "CLIENTE TESTE", cidades inventadas, sem CNPJ).
"""
from datetime import date

import pytest

import relatorios_nucleo as rn
from apoio_fretes import contexto_fretes, item

NOV = rn.rotulo_mes("2026-11")
OUT = rn.rotulo_mes("2026-10")


def _l(mes, uf, vlr, cidade="CIDADE FICT A"):
    """Linha de "Notas com frete" (16 colunas + CHAVE), sem acompanhamento."""
    return [mes, date(2026, 11, 1), date(2026, 11, 2), "900001",
            "FILIAL FICTICIA", "000301 - CLIENTE TESTE 31", cidade, uf, vlr,
            vlr * 0.05, rn.CONCLUIDA, "", None, None, None, "", ""]


def _pct(kpis):
    return {k["rotulo"]: k["valor"] for k in kpis}["% do faturado"]


# ------------------------------------------------- função pura (kpis_fretes)
def test_RN_POS_009_liquido_negativo_na_uf_mostra_traco():
    ls = [_l(NOV, "RR", 1000.0)]
    # RR: venda 1.000 − devolução 1.500 = líquido −500 (≤ 0)
    fat = {(NOV, "RR"): -500.0, (NOV, "PA"): 8000.0}
    # regra: pct_do_liquido(1.000, −500) = None → "—" (nunca "−200%")
    assert _pct(rn.kpis_fretes(ls, fat, uf="RR")) == "—"
    # BAP inteira: 1.000 ÷ (−500 + 8.000 = 7.500) = 13,3% → "13%"
    assert _pct(rn.kpis_fretes(ls, fat)) == "13%"


def test_RN_POS_009_liquido_zero_na_uf_mostra_traco():
    # devolução = venda no mês: líquido 0 → sem divisão, "—"
    fat = {(NOV, "RR"): 0.0}
    assert _pct(rn.kpis_fretes([_l(NOV, "RR", 1000.0)], fat, uf="RR")) == "—"


def test_RN_POS_009_liquido_negativo_na_bap_inteira_mostra_traco():
    ls = [_l(NOV, "RR", 1000.0), _l(NOV, "PA", 500.0)]
    # BAP: −3.000 + 2.000 = −1.000 (≤ 0) → "—"
    fat = {(NOV, "RR"): -3000.0, (NOV, "PA"): 2000.0}
    assert _pct(rn.kpis_fretes(ls, fat)) == "—"
    # o PA isolado segue positivo: 500 ÷ 2.000 = 25%
    assert _pct(rn.kpis_fretes(ls[1:], fat, uf="PA")) == "25%"


def test_RN_POS_009_mes_negativo_compensado_pelo_outro_mes_visivel():
    # meses visíveis OUT+NOV na UF RR: −500 + 4.500 = 4.000 > 0
    ls = [_l(NOV, "RR", 1000.0), _l(OUT, "RR", 1000.0)]
    fat = {(NOV, "RR"): -500.0, (OUT, "RR"): 4500.0}
    # 2.000 ÷ 4.000 = 50%
    assert _pct(rn.kpis_fretes(ls, fat, uf="RR")) == "50%"


@pytest.mark.parametrize("uf", [" am", "am", "AM ", " Am "])
def test_RN_GER_006_recorte_com_uf_suja_casa_com_a_uf_do_faturado(uf):
    ls = [_l(NOV, "AM", 1000.0, "CIDADE FICT AM")]
    fat = {(NOV, "AM"): 4000.0, (NOV, "PA"): 6000.0}
    # " am" → "AM": 1.000 ÷ 4.000 = 25% (sem normalizar daria "—")
    assert _pct(rn.kpis_fretes(ls, fat, uf=uf)) == "25%"
    assert rn.kpis_fretes(ls, fat, uf=uf) == rn.kpis_fretes(ls, fat, uf="AM")
    # conjunto com UF suja também: {" am", "pa "} = AM + PA = 10.000 → 10%
    assert _pct(rn.kpis_fretes(ls, fat, uf={uf, "pa "})) == "10%"


# --------------------------------------- ponta a ponta no PC (rn.fretes)
CLIENTES = [   # cod, nome, cidade, uf — o 000311 tem a UF suja no cadastro
    ("000311", "CLIENTE TESTE 11", "CIDADE FICT AM 1", " am"),
    ("000312", "CLIENTE TESTE 12", "CIDADE FICT AM 2", "AM"),
    ("000313", "CLIENTE TESTE 13", "CIDADE FICT RR", "RR"),
]
ITENS = [
    item("VND", "000311", "000011", 1000.0, date(2026, 11, 10)),   # " am"
    item("VND", "000312", "000012", 3000.0, date(2026, 11, 11)),   # "AM"
    item("VND", "000313", "000013", 1000.0, date(2026, 11, 12)),   # RR
    item("DEV", "000313", "000014", 1500.0, date(2026, 11, 16)),   # RR: dev > venda
]


@pytest.fixture
def farol(tmp_path):
    return contexto_fretes(tmp_path, ITENS, CLIENTES)


def test_RN_POS_009_fretes_uf_com_devolucao_maior_que_venda_mostra_traco(
        farol):
    r, t = farol
    rr = [l for l in t["linhas"] if l[7] == "RR"]
    assert [l[3] for l in rr] == ["13"]
    # RR: 1.000 − 1.500 = −500 → "—" no recorte (nunca negativo)
    assert _pct(t["kpis_de"](rr, {"UF": "RR"})) == "—"
    # BAP inteira: 5.000 notas ÷ (1.000 + 3.000 − 500 = 3.500) = 142,9%
    # → "143%" (a regra não trava em 100%: notas de UF negativa entram)
    assert _pct(r["kpis"]) == "143%"


def test_RN_GER_006_uf_suja_do_cadastro_vira_AM_na_linha_no_faturado_e_no_por_uf(
        farol):
    """uf_norm (strip + maiúsculas) na linha, no faturado, no cartão e no
    Por UF: o cliente com " am" no cadastro é do AM em todo lugar."""
    r, t = farol
    # linhas: a UF já sai normalizada ("AM", nunca " am")
    uf_por_nf = {l[3]: l[7] for l in t["linhas"]}
    assert uf_por_nf == {"11": "AM", "12": "AM", "13": "RR"}
    am = [l for l in t["linhas"] if l[7] == "AM"]
    # faturado AM = 1.000 (" am") + 3.000 ("AM") = 4.000; notas AM = 4.000
    # → 4.000 ÷ 4.000 = 100% (sem normalizar o faturado: 4.000 ÷ 3.000)
    assert _pct(t["kpis_de"](am, {"UF": "AM"})) == "100%"
    # o filtro sujo (" am") casa com o faturado do AM: mesmo cartão
    assert t["kpis_de"](am, {"UF": " am"}) == t["kpis_de"](am, {"UF": "AM"})
    # só a nota do cliente sujo (NF 11): 1.000 ÷ 4.000 = 25%
    so_11 = [l for l in am if l[3] == "11"]
    assert _pct(t["kpis_de"](so_11, {"UF": " am"})) == "25%"
    # Por UF: uma linha só do AM em NOV (2 notas, R$ 4.000), nenhuma " am"
    por_uf = next(x for x in r["tabelas"] if x["titulo"] == "Por UF")
    nov = {l[1]: (l[2], l[3]) for l in por_uf["linhas"] if l[0] == NOV}
    assert nov == {"AM": (2, 4000.0), "RR": (1, 1000.0)}
    # o mesmo número nos cartões da tabela Por UF: notas e valor = soma das UFs
    k = {x["rotulo"]: x["valor"] for x in por_uf["kpis_de"](
        [l for l in por_uf["linhas"] if l[0] == NOV])}
    assert k["Notas"] == "3"
    assert k["Valor"] == rn.moeda(5000.0)


# ------------------------------------------- uf_norm direto e nos rótulos
@pytest.mark.parametrize("bruto, uf", [
    (" am", "AM"), ("am", "AM"), ("AM ", "AM"), (" Am ", "AM"), ("AM", "AM"),
    ("", ""), (None, ""), ("  ", "")])
def test_RN_GER_006_uf_norm_strip_e_maiusculas(bruto, uf):
    # regra: str(u or "").strip().upper(); vazio continua vazio ("Sem UF"
    # é o rótulo, não a UF)
    assert rn.uf_norm(bruto) == uf


def _linha_rotulo(cidade, uf, chave="0101|11|1", transp=""):
    ln = [""] * 17
    ln[6], ln[7], ln[11], ln[16] = cidade, uf, transp, chave
    return ln


@pytest.mark.parametrize("uf", [" am", "am", "AM "])
def test_RN_GER_006_rotulo_agrupa_fretes_uf_suja_vira_AM(uf):
    ln = _linha_rotulo("CIDADE FICT X", uf)
    assert rn.rotulo_agrupa_fretes(7, ln) == "AM"                 # Por UF
    assert rn.rotulo_agrupa_fretes(6, ln) == "CIDADE FICT X / AM"  # Por cidade
    # sem UF: o rótulo "Sem UF", nunca a barra solta
    assert rn.rotulo_agrupa_fretes(7, _linha_rotulo("X", "  ")) == rn.SEM_UF
    assert rn.rotulo_agrupa_fretes(6, _linha_rotulo("X", None)) == \
        "X / " + rn.SEM_UF


def test_RN_GER_006_recorte_da_web_com_a_chave_AM_e_nunca_am_suja(farol):
    """O robô (_recortes_do_farol_web) recorta o Fretes pela UF da linha:
    a chave é "AM" (nunca " am") e o cartão é o do PC filtrado em "AM"."""
    import bap_automation as ba                               # noqa: PLC0415
    r, t = farol
    rec = ba._recortes_do_farol_web("pl_fretes", r)          # noqa: SLF001
    assert set(rec) == {"AM", "RR"}
    assert not any(k != k.strip().upper() for k in rec)
    am = [l for l in t["linhas"] if l[7] == "AM" and l[0] == NOV]
    assert rec["AM"]["kpis"] == t["kpis_de"](am, {"UF": "AM"})
    # valor × regra: 4.000 ÷ 4.000 = 100% no site como no PC; RR "—"
    assert _pct(rec["AM"]["kpis"]) == "100%"
    assert _pct(rec["RR"]["kpis"]) == "—"
