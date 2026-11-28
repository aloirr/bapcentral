"""T-0058 (RN-GER-002): estado = filial da nota, também na devolução.

De ponta a ponta, nas bases congeladas (20/11/2026): o Farol de Pedidos
(pv_pedidos) e o Farol de Saldo (vc_saldo), no PC (kpis_de com o filtro da
tela) e na web (bap_automation._recortes_do_farol_web), no recorte por
estado descontam TODA a devolução da filial, inclusive a de vendedor que só
devolveu (sem venda no mês), e batem com o Painel (`por_filial_da_nota`).
O filtro de vendedor ou supervisor continua por par (filial, vendedor).
Sem dado pessoal: o teste só cita UF, filial e totais.
"""
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 20)
FAT = ("FATURADO", "ENTREGUE", "DEVOLVIDO", "CANCELADO")


@pytest.fixture(scope="module")
def farol():
    r = rn.montar("pv_pedidos", RAIZ, hoje=HOJE)
    t = r["tabelas"][0]
    ix = {c["nome"]: i for i, c in enumerate(t["colunas"])}
    ctx = rn.Contexto(RAIZ)
    return t, ix, ctx


def _faturado(t, ls, filtro=None):
    """O cartao Faturado da tela; filtro = {indice da coluna: valor} (o que
    a tela filtrou, contrato do `chamar_kpis_de`)."""
    ks = rn.chamar_kpis_de(t["kpis_de"], ls, filtro)
    return {k["rotulo"]: k for k in ks}["Faturado"]["valor"]


def _fat_por_uf(rec):
    """{UF: valor do cartao Faturado} de um recorte por estado."""
    return {uf: {k["rotulo"]: k for k in x["kpis"]}["Faturado"]["valor"]
            for uf, x in rec.items()}


def _estados(t, mes):
    """De ponta a ponta: os cartoes por estado como o recorte de UF da web
    (bap_automation.recortes_farol_por_uf, filtro_uf=True), no mes `mes`
    (o filtro padrao MES da tabela trocado por ele)."""
    tab = dict(t, filtros=[{"coluna": "MÊS", "padrao": mes}])
    rec = ba.recortes_farol_por_uf({"tabelas": [tab]}, t["titulo"],
                                   filtro_uf=True)
    return _fat_por_uf(rec)


def _do_mes(t, ix, mes):
    return [l for l in t["linhas"] if l[ix["MÊS"]] == mes]


def test_RN_GER_002_estado_pa_ago26_desconta_devolucao_de_quem_nao_vendeu(farol):
    t, ix, ctx = farol
    # o caso existe na base: devolução em BELÉM de vendedor sem venda lá no mês
    com_venda = {(l[ix["FILIAL"]], l[ix["VENDEDOR"]])
                 for l in _do_mes(t, ix, "AGO/26") if l[ix["SITUAÇÃO"]] in FAT}
    so_devolveu = [x for (m, f, v), x in rn._devolucoes_por_chave(ctx).items()
                   if m == "AGO/26" and f == "BELÉM" and (f, v) not in com_venda]
    assert so_devolveu and sum(so_devolveu) > 1
    pf = rn.por_filial_da_nota(ctx, "2026-08")["fat"]
    assert pf["PA"] == pytest.approx(33833.74, abs=0.005)
    assert _estados(t, "AGO/26")["PA"] == rn.moeda(pf["PA"]) == "R$ 33.834"


def test_RN_GER_002_soma_dos_estados_igual_ao_total_e_ao_painel(farol):
    t, ix, ctx = farol
    pf = rn.por_filial_da_nota(ctx, "2026-08")["fat"]
    # RN-GER-005 (T-0060): o AP de AGO/26 só tinha a conta 000040 - sai
    assert set(pf) == {"AM", "MA", "MT", "PA", "RR"}
    est = _estados(t, "AGO/26")
    for uf, valor in pf.items():        # estado sem linha no mes = R$ 0
        assert est.get(uf, rn.moeda(0.0)) == rn.moeda(valor), uf
    # estado com linha só da conta 000040 (o AP) aparece com R$ 0
    assert all(est[uf] == rn.moeda(0.0) for uf in set(est) - set(pf))
    # o total do farol (mês inteiro) = a soma dos estados do Painel
    total = _faturado(t, _do_mes(t, ix, "AGO/26"), {ix["MÊS"]: "AGO/26"})
    assert total == rn.moeda(sum(pf.values()))


def test_RN_GER_002_filtro_de_vendedor_continua_por_par(farol):
    """SET/26, MATOGROSSO: um só vendedor com venda na filial e outro que
    só devolveu. Filtrado pelo vendedor, o Faturado NÃO leva a devolução do
    outro (só a do par filial+vendedor das linhas)."""
    t, ix, ctx = farol
    ls = [l for l in _do_mes(t, ix, "SET/26")
          if l[ix["FILIAL"]] == "MATOGROSSO" and l[ix["SITUAÇÃO"]] in FAT]
    vends = {l[ix["VENDEDOR"]] for l in ls}
    n = len(vends)
    assert n == 1
    (vend,) = vends
    dev = rn._devolucoes_por_chave(ctx)
    de_outro = sum(x for (m, f, v), x in dev.items()
                   if m == "SET/26" and f == "MATOGROSSO" and v != vend)
    assert de_outro > 1
    venda = sum(l[ix["R$ VENDA"]] for l in ls
                if l[ix["RAZÃO SOCIAL"]] != rn.NOME_FORA_DA_BASE)
    esperado = venda - dev.get(("SET/26", "MATOGROSSO", vend), 0.0)
    filtro = {ix["MÊS"]: "SET/26", ix["FILIAL"]: ["MATOGROSSO"],
              ix["VENDEDOR"]: vend}
    fat = _faturado(t, ls, filtro)
    assert fat == rn.moeda(esperado)


def test_RN_GER_002_filiais_do_recorte_uf_do_saldo_e_filial_inteira():
    """Funcao pura: no Farol de Saldo a UF tambem recorta por filial da nota
    (i_fil = (FILIAL, UF)); com vendedor ou supervisor no filtro, por par.
    Nomes ficticios."""
    I_FIL, I_UF, I_VEND, I_SUP = 0, 1, 2, 3
    ls = [["BELÉM", "PA", "VENDEDOR A", "SUPERVISOR X"],
          ["SANTARÉM", "PA", "VENDEDOR B", "SUPERVISOR X"]]
    cols, pessoas = (I_FIL, I_UF), (I_VEND, I_SUP)
    assert rn.filiais_do_recorte(ls, {I_UF: "PA"}, cols, pessoas) \
        == frozenset({"BELÉM", "SANTARÉM"})
    assert rn.filiais_do_recorte(
        ls, {I_UF: "PA", I_VEND: "VENDEDOR A"}, cols, pessoas) == frozenset()
    assert rn.filiais_do_recorte(
        ls, {I_UF: "PA", I_SUP: "SUPERVISOR X"}, cols, pessoas) == frozenset()


def test_RN_GER_002_saldo_filtro_uf_pa_ago26_desconta_toda_a_filial():
    """vc_saldo (Pedido a pedido) filtrado so pela UF = PA em AGO/26: o
    Faturado = venda - TODA a devolucao das filiais da nota = o Painel."""
    r = rn.montar("vc_saldo", RAIZ, hoje=HOJE)
    t = r["tabelas"][0]
    ix = {c["nome"]: i for i, c in enumerate(t["colunas"])}
    ctx = rn.Contexto(RAIZ)
    ls = [l for l in _do_mes(t, ix, "AGO/26") if l[ix["UF"]] == "PA"]
    fils = {l[ix["FILIAL"]] for l in ls}
    toda_dev = sum(x for (m, f, _v), x in rn._devolucoes_por_chave(ctx).items()
                   if m == "AGO/26" and f in fils)
    venda = sum(l[ix["VLR VENDA"]] for l in ls)
    pf = rn.por_filial_da_nota(ctx, "2026-08")["fat"]
    fat = _faturado(t, ls, {ix["MÊS"]: "AGO/26", ix["UF"]: "PA"})
    assert fat == rn.moeda(venda - toda_dev) == rn.moeda(pf["PA"]) \
        == "R$ 33.834"


@pytest.mark.parametrize("rid", ["pv_pedidos", "vc_saldo"])
def test_RN_GER_002_recorte_por_estado_na_web_ago26_pa_igual_painel(rid):
    """Web (bap_automation._recortes_do_farol_web): o cartao Faturado de PA
    em AGO/26 = por_filial_da_nota = "R$ 33.834", como no PC."""
    r = rn.montar(rid, RAIZ, hoje=HOJE, params={"ANO": "2026", "MÊS": "08"})
    rec = ba._recortes_do_farol_web(rid, r)
    fat = _fat_por_uf(rec)
    pf = rn.por_filial_da_nota(rn.Contexto(RAIZ), "2026-08")["fat"]
    assert fat["PA"] == "R$ 33.834"
    for uf, valor in fat.items():       # estado sem venda (o AP) = R$ 0
        assert valor == rn.moeda(pf.get(uf, 0.0)), uf
