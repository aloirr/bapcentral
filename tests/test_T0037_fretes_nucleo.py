"""T-0037 — Farol de Fretes no PC (relatorios_nucleo.fretes), valor × regra.

Duas partes:
- o rn.fretes de verdade sobre um Contexto FICTÍCIO (tmp_path, clientes
  "CLIENTE TESTE", cidades inventadas, sem CNPJ), com uma devolução no mês:
  RN-POS-007 (nota com frete), RN-POS-008 (VLR FRETE), RN-POS-009 (o "% do
  faturado" com o faturado LÍQUIDO de devolução, P3 B) e RN-GER-006 (UF do
  cliente);
- as bases congeladas do repositório (NOV/26): o cartão da BAP inteira e o
  de uma UF batem com o faturado líquido do farol de origem
  (_eventos_faturamento, o mesmo do indicador "Faturamento (R$)" líquido) e
  com o pacote da web.
Desenho: docs/desenho/T-0037.md §3 e §9 (P3 B); contrato §10.12.2.
"""
import json
from collections import defaultdict
from datetime import date

import pytest

import relatorios_nucleo as rn

if not hasattr(rn, "kpis_fretes"):
    pytest.skip("faróis da T-0037 ainda não entraram", allow_module_level=True)

HOJE = date(2026, 11, 24)
PARAMS = {"ANO": "2026", "MÊS": "11"}
NOV = rn.rotulo_mes("2026-11")
TR1 = "TRANSPORTADORA FICTICIA 1"
CAD = {"pct_padrao": 5, "transportadoras": [
    {"nome": TR1, "ufs": ["PA"], "pct_frete": 4, "frete_minimo": 50}]}
CLIENTES = [   # cod, nome, cidade, uf (Manaus e Belém: capitais sem frete)
    ("000201", "CLIENTE TESTE 21", "CIDADE FICT A", "PA"),
    ("000202", "CLIENTE TESTE 22", "CIDADE FICT B", "MA"),
    ("000203", "CLIENTE TESTE 23", "MANAUS", "AM"),
    ("000204", "CLIENTE TESTE 24", "BELÉM", "PA"),
]


def _it(tipo, cli, nf, valor, dt_nf, dt_ped=None, fil="0101"):
    return {"tipo": tipo, "cliente": cli, "filial": fil, "nf": nf,
            "serie": "1", "pedido": "P" + nf, "valor": valor, "dt_nf": dt_nf,
            "dt_pedido": dt_ped or dt_nf, "razao": "", "p_tab": 0, "qtd": 1,
            "produto": "", "vend": ""}


ITENS = [
    _it("VND", "000201", "000001", 600.0, date(2026, 11, 10), date(2026, 11, 8)),
    _it("VND", "000201", "000001", 400.0, date(2026, 11, 10), date(2026, 11, 8)),
    _it("VND", "000202", "000002", 2000.0, date(2026, 11, 12)),
    _it("VND", "000202", "000005", 800.0, date(2026, 11, 13)),
    _it("VND", "000203", "000003", 6000.0, date(2026, 11, 11)),   # Manaus
    _it("VND", "000204", "000006", 3000.0, date(2026, 11, 11)),   # Belém
    _it("DEV", "000201", "000007", 500.0, date(2026, 11, 15)),    # devolução
    _it("VEA", "000202", "", 900.0, None, date(2026, 11, 20)),    # em aberto
    _it("VND", "000201", "000004", 9999.0, date(2025, 11, 10)),   # > 12 meses
]
ENTREGAS = [
    {"filial": "0101", "nf": "1", "chave": "0101|1|1", "etapa": "ENTREGUE",
     "transportadora": TR1, "prevista_manual": "20/11/2026",
     "entregue_em": "14/11/2026", "responsavel": "", "frete_real": ""},
    {"filial": "0101", "nf": "2", "chave": "0101|2|1",
     "etapa": "EM TRÂNSITO", "transportadora": "", "prevista_manual": "",
     "entregue_em": "", "responsavel": "", "frete_real": "120,00"},
]


@pytest.fixture
def farol(tmp_path):
    # cadastro de transportadoras FICTÍCIO, só na pasta temporária
    (tmp_path / "transportadoras_config.json").write_text(
        json.dumps(CAD), encoding="utf-8")
    ctx = rn.Contexto(tmp_path, hoje=HOJE, params=dict(PARAMS))
    ctx._b["tabela"] = {"itens": [dict(i) for i in ITENS], "clientes": {},
                        "filiais": {"0101": "FILIAL FICTICIA"}}
    ctx._b["base"] = {"clientes": [
        {"cod": c, "nome": n, "fantasia": "", "cidade": cid, "uf": uf,
         "segmento": "", "vend": "", "status": "ATIVO"}
        for c, n, cid, uf in CLIENTES], "pessoas": {}}
    ctx._b["posvenda"] = {"existe": True, "entregas": [dict(e) for e in
                                                        ENTREGAS],
                          "devolucoes": []}
    r = rn.fretes(ctx)
    return r, r["tabelas"][0]


def _k(kpis):
    return {k["rotulo"]: (k["valor"], k.get("detalhe") or "") for k in kpis}


def _por_nf(t):
    return {l[3]: l for l in t["linhas"]}


# ------------------------------------------------------------ fictício (PC)
def test_RN_POS_007_nota_com_frete_fora_das_capitais(farol):
    _r, t = farol
    # NF 1, 2 e 5 (interior); fora: Manaus (3), Belém (6), a DEV (7), o
    # pedido em aberto e a NF de NOV/25 (fora dos 12 meses)
    assert sorted(_por_nf(t)) == ["1", "2", "5"]
    # a nota soma os itens dela: 600 + 400
    assert _por_nf(t)["1"][8] == 1000.0


def test_T0037_pc_mostra_o_mes_nas_abas_de_resumo(farol):
    """RD-0198: no PC nada muda; o MÊS é oculto só no "Notas com frete"
    (nas 3 de resumo o "(todos)" mostra os 12 meses). Quem o esconde nas 3
    abas do site é o robô (contrato bcb5582 §10.7.3)."""
    r, _t = farol
    oculta = {t["titulo"]: bool(t["colunas"][0].get("oculta"))
              for t in r["tabelas"]}
    assert oculta == {"Notas com frete": True, "Por UF": False,
                      "Por cidade": False, "Por transportadora": False}
    assert all(t["colunas"][0]["nome"] == "MÊS" for t in r["tabelas"])


def test_RN_GER_006_fretes_na_uf_do_cliente(farol):
    _r, t = farol
    ls = _por_nf(t)
    assert (ls["1"][6], ls["1"][7]) == ("CIDADE FICT A", "PA")
    assert (ls["2"][7], ls["5"][7]) == ("MA", "MA")


def test_RN_POS_008_vlr_frete_real_ou_estimado_com_minimo(farol):
    _r, t = farol
    ls = _por_nf(t)
    # NF 1: 4% de 1.000 = 40, abaixo do FRETE MÍNIMO 50 → 50
    assert ls["1"][9] == 50.0
    # NF 2: o FRETE REAL informado na entrega (120,00) vale
    assert ls["2"][9] == 120.0
    # NF 5: sem entrega/transportadora → % padrão 5% de 800 = 40
    assert ls["5"][9] == pytest.approx(40.0)


def test_RN_POS_009_pct_faturado_usa_o_liquido_de_devolucao(farol):
    r, _t = farol
    k = _k(r["kpis"])
    assert k["Notas com frete"] == ("3", "R$ 3.800")
    # faturado líquido NOV = 1.000+2.000+800+6.000+3.000 − 500 (DEV) = 12.300
    # 3.800 ÷ 12.300 = 30,9% → 31% (o bruto, 12.800, daria 30%)
    assert k["% do faturado"][0] == "31%"
    # frete = 50 + 120 + 40 = 210; 210 ÷ 3.800 = 5,5% → 6%
    assert k["Frete estimado"] == ("R$ 210", "6% do valor")
    assert k["Cidades atendidas"][0] == "2"
    # entregue só a NF 1 (14/11 ≤ 20/11): 100% no prazo
    assert k["Entregues"] == ("1", "100% no prazo")
    # sem transportadora: a NF 2 (com linha no acompanhamento); a NF 5,
    # sem acompanhamento, fica fora
    assert k["Sem transportadora"][0] == "1"


def test_RN_POS_009_pct_faturado_no_recorte_usa_a_uf_com_devolucao(farol):
    _r, t = farol
    pa = [l for l in t["linhas"] if l[7] == "PA"]
    k = _k(t["kpis_de"](pa, {"UF": "PA"}))
    # PA líquido = 1.000 + 3.000 (Belém) − 500 = 3.500; 1.000 ÷ 3.500 = 29%
    assert k["% do faturado"][0] == "29%"
    ma = [l for l in t["linhas"] if l[7] == "MA"]
    # MA: 2.800 ÷ 2.800 = 100%
    assert _k(t["kpis_de"](ma, {"UF": "MA"}))["% do faturado"][0] == "100%"


def test_RN_POS_009_pct_faturado_com_conjunto_de_ufs_soma_o_liquido(farol):
    """Filtro com vários estados: o denominador soma o líquido de cada UF."""
    _r, t = farol
    ls = [l for l in t["linhas"] if l[7] in ("PA", "MA")]
    k = _k(t["kpis_de"](ls, {"UF": {"PA", "MA"}}))
    # (1.000 + 2.800) ÷ (3.500 PA + 2.800 MA) = 3.800 ÷ 6.300 = 60,3% → 60%
    assert k["% do faturado"][0] == "60%"
    # o texto e o conjunto de 1 UF dão o mesmo
    pa = [l for l in ls if l[7] == "PA"]
    assert t["kpis_de"](pa, {"UF": {"PA"}}) == t["kpis_de"](pa, {"UF": "PA"})
    # conjunto com todas as UFs que faturaram (AM, PA, MA) = a BAP inteira
    assert t["kpis_de"](ls, {"UF": {"AM", "PA", "MA"}}) == t["kpis_de"](ls)
    # na função pura: lista ou frozenset valem como conjunto
    fat = {(NOV, "PA"): 3500.0, (NOV, "MA"): 2800.0, (NOV, "AM"): 6000.0}
    assert rn.kpis_fretes(ls, fat, ["PA", "MA"]) == rn.kpis_fretes(
        ls, fat, frozenset({"MA", "PA"}))
    assert _k(rn.kpis_fretes(ls, fat, frozenset({"PA", "MA"})))[
        "% do faturado"][0] == "60%"


def test_RN_POS_010_fretes_sem_frete_real_no_pc(farol):
    """P2 A: a edição do PC no Fretes não oferece o frete_real."""
    _r, t = farol
    campos = [c["campo"] for c in t["edicao"]["campos"]]
    assert "frete_real" not in campos
    assert set(campos) == {"etapa", "transportadora", "prevista_manual",
                           "entregue_em", "responsavel"}


# ------------------------------------------------- bases congeladas (NOV/26)
@pytest.fixture(scope="module")
def real():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    ctx = rn.Contexto(raiz, hoje=HOJE, params=dict(PARAMS))
    r = rn.fretes(ctx)
    liq = defaultdict(float)
    for d, v in rn._eventos_faturamento(ctx, liquido=True):   # noqa: SLF001
        if d and rn.mes_de(d) == "2026-11":
            liq["BAP"] += v
    for it in ctx.tabela["itens"]:
        v = rn._liquido(it) if it["dt_nf"] else None            # noqa: SLF001
        if v is not None and rn.mes_de(it["dt_nf"]) == "2026-11":
            liq[ctx.cliente(it["cliente"]).get("uf", "")] += v
    return r, liq


def test_RN_POS_009_bap_inteira_bate_com_o_faturado_liquido_de_origem(real):
    r, liq = real
    t = r["tabelas"][0]
    nov = [l for l in t["linhas"] if l[0] == NOV]
    val = sum(l[8] for l in nov)
    # denominador = o "Faturamento (R$)" líquido do mês (soma das UFs)
    assert sum(v for u, v in liq.items() if u != "BAP") == pytest.approx(
        liq["BAP"])
    k = _k(r["kpis"])
    assert k["Notas com frete"] == (rn.br(len(nov)), rn.moeda(val))
    assert k["% do faturado"][0] == rn.p(rn.pct_de(val, liq["BAP"]))
    # nas bases do repositório: 64.759,95 ÷ 112.701,43 = 57,46% → 57%
    assert round(val / liq["BAP"] * 100, 2) == 57.46
    assert k["% do faturado"][0] == "57%"


def test_RN_POS_009_uf_bate_com_o_faturado_liquido_da_uf(real):
    r, liq = real
    t = r["tabelas"][0]
    ma = [l for l in t["linhas"] if l[0] == NOV and l[7] == "MA"]
    val = sum(l[8] for l in ma)
    k = _k(t["kpis_de"](ma, {"UF": "MA"}))
    assert k["% do faturado"][0] == rn.p(rn.pct_de(val, liq["MA"]))
    # nas bases do repositório: 53.889,49 ÷ 59.536,32 = 90,5% → 91%
    assert k["% do faturado"][0] == "91%"


def test_RN_POS_009_web_bate_com_o_pc_bap_e_uf(real):
    import bap_automation as ba
    if "pl_fretes" not in getattr(ba, "FAROIS_WEB", ()):
        pytest.skip("robô da T-0037 ainda não entrou")
    r, _liq = real
    t = r["tabelas"][0]
    notas = ba.tabelas_farol_web("pl_fretes", r)[0][0]
    nov = [l for l in t["linhas"] if l[0] == NOV]
    assert notas["kpis_padrao"] == t["kpis_de"](nov)
    rec = ba._recortes_do_farol_web("pl_fretes", r)          # noqa: SLF001
    ma = [l for l in nov if l[7] == "MA"]
    assert rec["MA"]["kpis"] == t["kpis_de"](ma, {"UF": "MA"})
