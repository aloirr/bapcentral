"""T-0060: Painel × Farol de Pedidos, com hoje contando no grupo A.

Regras (texto do PR #223, docs/produto/03-regras.md):
- RN-GER-007 (decisões 43 e 48): no grupo A (faturamento, projeção,
  positivação, pedidos, ticket, volume, quebra por UF, Metas e Diretor)
  **hoje conta** como DU passado; projeção = real até agora ÷ DU passados
  (com hoje) × DU do mês. No grupo B (meta RH, RV, peças, cadastros,
  visitas...) hoje fica fora, com o período no rótulo.
- RN-GER-002: faturado = VND − DEV, pela data da NF.
- RN-GER-003: positivação = cliente com líquido > 0 no mês.
- RN-GER-005: a conta 000040 (vendedor de teste) fica fora.
- RN-GER-006: estado do faturamento = filial da nota.
- Definição de pronto: o número do Diretor bate com o farol de origem.

- RN-GER-007 (último DU): hoje = 30/11, dias_restantes = 0 (grupo A) e
  dias_restantes_b = 1 (grupo B); o Metas mostra o que falta e só diz
  "mês fechado" depois.

Dado real: as bases congeladas do repositório com hoje = 19/11/2026 (DU de
NOV/26: 19; passados com hoje: 13). Nada é gravado em RELATORIOS/ (o
histórico do Diretor vai para a cópia do tests/conftest.py). Os testes das
funções puras usam itens fictícios, sem dado pessoal.
"""
from collections import defaultdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import meta_nucleo as mn
import painel_diretor as pdr
import painel_rrm as prm
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 19)
PARAMS = {"ANO": "2026", "MÊS": "11"}
# NOV/26: seg a sex menos 02/11 (Finados) e 20/11 (Consciência Negra).
DU_MES, DU_PASSADOS_COM_HOJE = 19, 13
AM, PA, MA = "0101002", "0101005", "0101006"


# ------------------------------------------------------------ regra (teste)
def _liq(it):
    if it["tipo"] == "VND":
        return it["valor"]
    if it["tipo"] == "DEV":
        return -abs(it["valor"])
    return None


def _do_mes(itens, ate):
    """Notas do mês de `ate`, até `ate` (inclusive), sem a conta 000040."""
    for it in itens:
        d = it.get("dt_nf")
        if not d or d > ate or (d.year, d.month) != (ate.year, ate.month):
            continue
        if str(it.get("vend") or "").strip().zfill(6) == "000040":
            continue
        if _liq(it) is None:
            continue
        yield it


def _regra_real(itens, ate):
    return sum(_liq(it) for it in _do_mes(itens, ate))


def _regra_por_cliente(itens, ate):
    s = defaultdict(float)
    for it in _do_mes(itens, ate):
        s[it["cliente"]] += _liq(it)
    return {c for c, v in s.items() if v > 0.005}


def _regra_por_pedido(itens, ate):
    s = defaultdict(float)
    for it in _do_mes(itens, ate):
        if it.get("pedido"):
            s[(it["filial"], it["pedido"])] += _liq(it)
    return {k for k, v in s.items() if v > 0.005}


def _regra_por_uf(itens, ate):
    s = defaultdict(float)
    for it in _do_mes(itens, ate):
        s[rn.uf_da_filial(it["filial"]) or "?"] += _liq(it)
    return dict(s)


def _it(d, tipo, valor, cliente="C1", filial=AM, pedido="P1",
        vend="000101"):
    return {"dt_nf": d, "tipo": tipo, "valor": valor, "cliente": cliente,
            "filial": filial, "pedido": pedido, "vend": vend, "qtd": 1}


# ------------------------------------------------------- montagem (dado real)
@pytest.fixture(scope="module")
def base():
    ctx = rn.Contexto(RAIZ, HOJE, None, dict(PARAMS))
    itens = [it for it in ctx.tabela["itens"] if not it.get("_ped")]
    exe = rn.montar("vc_painel", RAIZ, hoje=HOJE, params=dict(PARAMS))
    dire = pdr.calcular(rn.Contexto(RAIZ, HOJE, None, dict(PARAMS)),
                        2026, 11, gravar_hist=False)
    return {"itens": itens, "exe": exe, "dir": dire}


def _kpis(rel, painel=None):
    if painel is None:
        return {k["rotulo"]: k for k in rel["kpis"]}
    p = next(x for x in rel["paineis"] if x.get("titulo") == painel)
    return {k["rotulo"]: k for k in p["kpis"]}


def _card(dire, chave):
    return next(c for c in dire["cards"] if c["chave"] == chave)


def _kpi_real(kpis):
    return next(v for r, v in kpis.items() if r.startswith("Real"))


# ---------------------------------------------------------------- 1 projeção
def test_RN_GER_007_projecao_ritmo_uma_conta_so():
    """Grupo A: projeção = real ÷ fração do mês corrida (DU passados, com
    hoje, ÷ DU do mês). As chaves e as bases antigas sumiram."""
    for velho in ("PROJECAO_COM_HOJE", "VOLUME_COM_HOJE", "base_projecao",
                  "_hoje_fora_do_du", "_du_fechados", "_de_hoje"):
        assert not hasattr(rn, velho), velho
    assert rn.projecao_ritmo(112701.0, 13 / 19) == pytest.approx(
        112701.0 / 13 * 19)
    assert rn.projecao_ritmo(500.0, 1.0) == 500.0          # mês fechado
    assert rn.projecao_ritmo(500.0, 0) is None
    assert rn.projecao_ritmo(500.0, None) is None


def test_RN_GER_007_projecao_do_painel_e_do_diretor_hoje_conta(base):
    """Base congelada, hoje = 19/11: 112.701 ÷ 13 × 19 = 164.717."""
    real = _regra_real(base["itens"], HOJE)
    assert round(real) == 112701
    proj = real / DU_PASSADOS_COM_HOJE * DU_MES
    assert round(proj) == 164717
    assert rn.projecao_ritmo(real, DU_PASSADOS_COM_HOJE / DU_MES) == \
        pytest.approx(proj)
    k = _kpis(base["exe"], "Resumo gerencial")
    assert _kpi_real(k)["valor"] == rn.moeda(real)
    assert ("DU", f"{DU_PASSADOS_COM_HOJE} de {DU_MES}", "") in \
        _kpi_real(k)["linhas"]
    assert k["Projeção"]["valor"] == rn.moeda(proj)          # R$ 164.717
    assert _card(base["dir"], "fat")["projecao"] == pytest.approx(proj,
                                                                  abs=1)


def test_RN_GER_007_diretor_grupo_A_hoje_e_grupo_B_ontem(base):
    """dados_ate/ndp = grupo B (até ontem); dados_ate_a/ndp_a = grupo A
    (hoje conta). O cabeçalho do Diretor mostra o grupo A."""
    d = base["dir"]
    assert (d["dados_ate"], d["ndp"]) == (date(2026, 11, 18),
                                          DU_PASSADOS_COM_HOJE - 1)
    assert (d["dados_ate_a"], d["ndp_a"], d["ndm"]) == (
        HOJE, DU_PASSADOS_COM_HOJE, DU_MES)


def test_RN_GER_007_pecas_seguem_ate_ontem_projecao_inalterada(base):
    """Peças são grupo B: o real vai até ontem (18/11) e a projeção usa os
    DU até ontem (12), como antes da decisão 43."""
    ctx = rn.Contexto(RAIZ, HOJE, None, dict(PARAMS))
    r = prm.calcular(ctx, 2026, 11, dd=base["dir"])
    c = next(x for x in r["res"] if x["chave"] == "pecas")
    # os mesmos números de antes da T-0060 (main de 26/11)
    assert c["valor"] == "R$ 16,9 mil"
    assert c["titulo"].endswith(" · até 18/11")
    d = next(x for x in r["du"] if x["chave"] == "pecas")
    assert d["valor"] == "R$ 889"                 # peças ÷ 12 DU (até ontem)
    assert d["titulo"].endswith(" · até 18/11")
    # o faturamento (grupo A) vai até hoje
    f = next(x for x in r["res"] if x["chave"] == "fat")
    assert " · até" not in f["titulo"]


def test_RN_GER_007_corre_no_ultimo_du_segue_o_mes_de_hoje():
    """Hoje = 30/11 (último DU): ndp_a = ndm, mas o mês ainda corre; o
    painel não diz "fechado"."""
    hoje = date(2026, 11, 30)
    ctx = rn.Contexto(RAIZ, hoje, None, dict(PARAMS))
    d = pdr.calcular(ctx, 2026, 11, gravar_hist=False)
    assert d["ndp_a"] == d["ndm"] == DU_MES
    # grupo B: até ontem, limitado à última NF da base congelada (19/11)
    assert (d["dados_ate"], d["ndp"]) == (HOJE, DU_PASSADOS_COM_HOJE)
    r = prm.calcular(ctx, 2026, 11, dd=d)
    assert "novembro fechado" not in r["sub"]["res"]
    assert f"({DU_MES} de {DU_MES} dias úteis)" in r["sub"]["res"]
    p = next(x for x in r["res"] if x["chave"] == "pecas")
    assert " · proj." in p["titulo"]                   # ainda projeta


# ---------------------------------------------------- 2 pedidos faturados
def test_RN_GER_002_pedidos_faturados_ate_chave_filial_pedido():
    d1, d2 = date(2026, 11, 18), date(2026, 11, 19)
    itens = [
        _it(d1, "VND", 100.0, filial=AM, pedido="P1"),
        _it(d1, "VND", 50.0, filial=PA, pedido="P1"),   # mesmo nº, outra filial
        _it(d1, "VND", 80.0, filial=AM, pedido="P2"),
        _it(d1, "DEV", 80.0, filial=AM, pedido="P2"),   # devolução total: sai
        _it(d1, "VND", 90.0, filial=AM, pedido="P3"),
        _it(d1, "DEV", 30.0, filial=AM, pedido="P3"),   # devolução parcial: fica
        _it(d1, "VND", 70.0, filial=AM, pedido="P4", vend="40"),  # 000040
        _it(d2, "VND", 60.0, filial=MA, pedido="P5"),   # no dia do `ate`
        _it(date(2026, 11, 20), "VND", 10.0, filial=MA, pedido="P6"),
    ]
    assert rn.pedidos_faturados_ate(itens, d2) == {
        (AM, "P1"), (PA, "P1"), (AM, "P3"), (MA, "P5")}
    assert rn.pedidos_faturados_ate(itens, d1) == {
        (AM, "P1"), (PA, "P1"), (AM, "P3")}
    assert (MA, "P6") in rn.pedidos_faturados_ate(itens)
    assert rn.pedidos_faturados_ate(itens, d2) == _regra_por_pedido(itens, d2)


def test_RN_GER_005_pedidos_faturados_sem_a_conta_000040():
    d = date(2026, 11, 10)
    itens = [_it(d, "VND", 70.0, pedido="P4", vend=v)
             for v in ("40", "000040", " 000040 ")]
    assert rn.pedidos_faturados_ate(itens, d) == set()


# ------------------------------------------------- 3 clientes positivados
def test_RN_GER_003_clientes_positivados_ate_liquido_e_universo():
    d0, d1, d2 = date(2026, 10, 31), date(2026, 11, 18), date(2026, 11, 19)
    itens = [
        _it(d1, "VND", 100.0, cliente="C1"),
        _it(d1, "VND", 80.0, cliente="C2"),
        _it(d2, "DEV", 80.0, cliente="C2"),            # devolveu tudo: sai
        _it(d2, "VND", 40.0, cliente="C3"),            # comprou hoje: entra
        _it(d0, "VND", 500.0, cliente="C4"),           # mês anterior: fora
        _it(d1, "VND", 30.0, cliente="C5", vend="000040"),  # conta de teste
        _it(date(2026, 11, 20), "VND", 10.0, cliente="C6"),  # depois do ate
    ]
    assert rn.clientes_positivados_ate(itens, d2) == {"C1", "C3"}
    assert rn.clientes_positivados_ate(itens, d1) == {"C1", "C2"}
    assert rn.clientes_positivados_ate(itens, d2, {"C3", "C9"}) == {"C3"}
    assert rn.clientes_positivados_ate(itens, d2) == \
        _regra_por_cliente(itens, d2)


# ---------------------------------------------------- 4 venda líquida por UF
def test_RN_GER_006_venda_liquida_por_uf_pela_filial_da_nota():
    d = date(2026, 11, 19)
    itens = [
        _it(d, "VND", 100.0, filial=AM),
        _it(d, "DEV", 30.0, filial=AM),
        _it(d, "VND", 40.0, filial=PA),
        _it(d, "VND", 25.0, filial="0101007"),         # a outra filial do PA
        _it(d, "VND", 60.0, filial=MA, vend="40"),     # 000040: fora
        _it(date(2026, 10, 30), "VND", 999.0, filial=MA),
        _it(date(2026, 11, 20), "VND", 999.0, filial=AM),
    ]
    assert rn.venda_liquida_por_uf(itens, d) == pytest.approx(
        {"AM": 70.0, "PA": 65.0})
    assert rn.venda_liquida_por_uf(itens, d) == pytest.approx(
        _regra_por_uf(itens, d))


# ---------------------------------------- 5 Metas: dias úteis que faltam
def test_RN_GER_007_dias_uteis_restantes_hoje_conta_no_grupo_A():
    """Grupo A (hoje_conta=True, padrão): faltam os DU depois de hoje.
    Grupo B (meta RH): hoje ainda é dia a vencer (d >= hoje)."""
    fer = [date(2026, 11, 2), date(2026, 11, 20)]
    assert len(mn.dias_uteis_do_mes("2026-11", fer)) == DU_MES
    # depois de 19/11: 23 a 27 e 30 (o 20 é feriado)
    assert mn.dias_uteis_restantes("2026-11", HOJE, fer) == 6
    assert mn.dias_uteis_restantes("2026-11", HOJE, fer, True) == 6
    assert mn.dias_uteis_restantes("2026-11", HOJE, fer, False) == 7
    # passados com hoje + restantes = DU do mês
    assert DU_PASSADOS_COM_HOJE + mn.dias_uteis_restantes(
        "2026-11", HOJE, fer) == DU_MES
    # sábado: nada muda entre os grupos
    sab = date(2026, 11, 21)
    assert mn.dias_uteis_restantes("2026-11", sab, fer, True) == \
        mn.dias_uteis_restantes("2026-11", sab, fer, False) == 6
    # mês fechado e mês que não começou
    assert mn.dias_uteis_restantes("2026-10", HOJE, fer) == 0
    assert mn.dias_uteis_restantes("2026-12", HOJE, fer) == len(
        mn.dias_uteis_do_mes("2026-12", fer))


def _ac(restantes, restantes_b):
    return {"dias_uteis_do_mes": DU_MES, "dias_restantes": restantes,
            "dias_restantes_b": restantes_b}


def _textos(k):
    return [k["valor"], k.get("detalhe") or ""] + [
        f"{a} {b}" for a, b, *_ in k.get("linhas") or []]


def test_RN_GER_007_dias_restantes_b_e_ultimo_du():
    """Último DU (hoje = 30/11): no grupo A não falta DU (hoje conta);
    no grupo B hoje ainda está a vencer."""
    fer = [date(2026, 11, 2), date(2026, 11, 20)]
    ult = date(2026, 11, 30)
    assert mn.dias_uteis_restantes("2026-11", ult, fer) == 0
    assert mn.dias_uteis_restantes("2026-11", ult, fer, False) == 1
    assert rn._ultimo_dia(_ac(0, 1)) is True
    assert rn._ultimo_dia(_ac(0, 0)) is False                # mês fechado
    assert rn._ultimo_dia(_ac(6, 7)) is False


def test_RN_GER_007_nec_visita_usa_os_dias_do_grupo_B():
    """No acompanhamento, NEC./DIA da visita divide pelos DU do grupo B
    (hoje a vencer); o resto, pelos do grupo A."""
    linha = {"meta_visita_int": 100, "visitas_realizadas": 40,
             "meta_positivacao_int": 10, "positivados": 4,
             "meta": 1000.0, "realizado": 400.0}
    mn._fechar_gaps(linha, 0, 1)                             # último DU
    assert linha["nec_visita"] == pytest.approx(60.0)        # 60 ÷ 1
    assert linha["nec_positivacao"] is None                  # 0 DU no A
    assert linha["nec_fat"] is None
    mn._fechar_gaps(linha, 6, 7)
    assert linha["nec_visita"] == pytest.approx(60 / 7)
    assert linha["nec_fat"] == pytest.approx(600 / 6)


def test_RN_GER_007_cartao_do_metas_no_ultimo_du_mostra_o_que_falta():
    """Último DU: a linha do NEC./DIA mostra desafio − real (R$ 1.387.299)
    e o cartão não diz "mês fechado"; depois do último DU, diz."""
    meta, real = 1500000.0, 112701.43
    falta = rn.moeda(meta - real)
    ac = _ac(0, 1)
    k = rn._cartao_indicador("Faturamento", meta, real, 0, rn._esperado(ac),
                             dinheiro=True, ultimo_dia=rn._ultimo_dia(ac))
    assert falta == "R$ 1.387.299"
    assert any(falta in str(b) for _a, b, *_ in k["linhas"])
    assert not any("mês fechado" in t for t in _textos(k))
    ac = _ac(0, 0)
    k = rn._cartao_indicador("Faturamento", meta, real, 0, rn._esperado(ac),
                             dinheiro=True, ultimo_dia=rn._ultimo_dia(ac))
    assert any("mês fechado" in t for t in _textos(k))


def test_RN_GER_003_positivacao_projetada_66_no_metas_e_no_diretor(base):
    """45 positivados ÷ 13 × 19 = 65,8 → 66 no cartão do Metas (mesma
    conta, `projecao_ritmo`) e no Diretor."""
    ac = _ac(DU_MES - DU_PASSADOS_COM_HOJE, DU_MES - DU_PASSADOS_COM_HOJE + 1)
    k = rn._cartao_indicador("Positivação", 163, 45,
                             ac["dias_restantes"], rn._esperado(ac),
                             real_proj=45, ultimo_dia=rn._ultimo_dia(ac))
    proj = dict((a, b) for a, b, *_ in k["linhas"])["Projeção do mês"]
    assert proj.startswith("66 ")
    c = _card(base["dir"], "pos")
    assert c["numero"] == 45 and round(c["projecao"]) == 66


# ------------------------------------------- 6 Diretor = Executivo (origem)
def test_RN_GER_007_numero_do_diretor_faturamento_bate_com_o_executivo(base):
    real = _regra_real(base["itens"], HOJE)
    k = _kpi_real(_kpis(base["exe"], "Resumo gerencial"))
    c = _card(base["dir"], "fat")
    assert c["numero"] == pytest.approx(real, abs=0.01)
    assert rn.moeda(c["numero"]) == k["valor"] == rn.moeda(real)
    assert c["valor"] == pdr.moeda(real, True)              # R$ 113 mil


def test_RN_GER_003_numero_do_diretor_positivacao_bate_com_o_executivo(base):
    pos = _regra_por_cliente(base["itens"], HOJE)
    assert len(pos) == 45
    k = _kpis(base["exe"], "Positivação")["Positivados"]
    c = _card(base["dir"], "pos")
    assert c["numero"] == len(pos)
    assert k["valor"] == rn.br(len(pos)) == c["valor"]
    # projeção da positivação, com hoje: 45 ÷ 13 × 19 ≈ 66
    assert c["projecao"] == pytest.approx(
        len(pos) / DU_PASSADOS_COM_HOJE * DU_MES)
    assert round(c["projecao"]) == 66


# ----------------------------------------- 7 Saldo: barras por UF = cartão
def test_RN_GER_006_saldo_barras_por_uf_somam_o_faturado_liquido(base):
    s = rn.montar("vc_saldo", RAIZ, hoje=HOJE, params=dict(PARAMS))
    k = next(x for x in s["kpis"] if x["rotulo"] == "Faturado")
    real = _regra_real(base["itens"], HOJE)
    assert k["valor"] == rn.moeda(real)                     # líquido
    por_uf = _regra_por_uf(base["itens"], HOJE)
    assert s["_liquido_por_uf"] == pytest.approx(por_uf)
    e = rn.estados_do_cartao(s, k)
    barras = {b[0]: b[1] for b in e["barras"] if b[1] is not None}
    assert barras == pytest.approx(por_uf)
    assert sum(barras.values()) == pytest.approx(real, abs=0.01)
    assert e["conferencia"]["fonte"] == "filial da nota"
    assert abs(e["conferencia"]["fora_dos_estados"]) < 1    # arredondamento


# --------------------------------------------------- 8 ticket por pedido
def test_RN_GER_002_ticket_e_liquido_por_pedido_faturado(base):
    real = _regra_real(base["itens"], HOJE)
    peds = _regra_por_pedido(base["itens"], HOJE)
    k = _kpis(base["exe"], "Itens por pedido")
    assert k["Pedidos faturados"]["valor"] == rn.br(len(peds))
    assert k["Ticket por pedido"]["valor"] == rn.moeda(real / len(peds))
    # a função não corta o mês: o farol passa só as notas do mês
    nov = [i for i in base["itens"] if i["dt_nf"]
           and (i["dt_nf"].year, i["dt_nf"].month) == (2026, 11)]
    assert rn.pedidos_faturados_ate(nov, HOJE) == peds


# -------------------------------------- 9 Farol de Pedidos: pedidos digitados
def test_RN_GER_007_farol_de_pedidos_cartao_pedidos_digitados():
    p = rn.montar("pv_pedidos", RAIZ, hoje=HOJE, params=dict(PARAMS))
    k = {x["rotulo"]: x for x in p["kpis"]}
    assert "Pedidos digitados" in k and "Pedidos" not in k
    assert k["Pedidos digitados"]["valor"] == "113"
    # o Faturado do Farol de Pedidos = o real do Executivo (mesma base)
    ctx = rn.Contexto(RAIZ, HOJE, None, dict(PARAMS))
    real = _regra_real([i for i in ctx.tabela["itens"] if not i.get("_ped")],
                       HOJE)
    assert k["Faturado"]["valor"] == rn.moeda(real)


# ------------------------------------------------- 10 hora com segundos
def test_RN_GER_007_painel_rrm_hora_le_os_segundos():
    assert prm._hora("00:15:53") == pytest.approx(15 / 60 + 53 / 3600)
    assert round(prm._hora("00:15:53"), 4) == 0.2647
    assert prm._hora("08:53") == pytest.approx(8 + 53 / 60)
    assert prm._hora(None) is None and prm._hora("") is None


# ------------------------------------- 11 DU por grupo (funções puras)
def test_RN_GER_007_du_corridos_grupo_B_ate_ontem_grupo_A_com_hoje():
    """du_corridos(chave, ndp, ndp_a): cartão do grupo B usa ndp (até
    ontem); o resto, ndp_a (hoje conta)."""
    assert rn.GRUPO_B_CARTOES
    for k in rn.GRUPO_B_CARTOES:
        assert rn.du_corridos(k, 12, 13) == 12, k
    for k in ("fat", "pos", "ped", "ticket"):
        assert k not in rn.GRUPO_B_CARTOES
        assert rn.du_corridos(k, 12, 13) == 13, k


def test_RN_GER_007_du_restantes_grupo_B_do_farol_com_hoje_a_vencer():
    """du_restantes(chave, resta_a, resta_b): coluna do grupo B do Farol
    de Metas (visita, meta RH) usa resta_b; desafio e positivação, resta_a."""
    assert rn.GRUPO_B_FAROL
    assert any("VISITA" in str(k).upper() for k in rn.GRUPO_B_FAROL)
    for k in rn.GRUPO_B_FAROL:
        assert rn.du_restantes(k, 0, 1) == 1, k
    for k in ("FAT. META", "POSIT."):
        assert k not in rn.GRUPO_B_FAROL
        assert rn.du_restantes(k, 0, 1) == 0, k


# ------------------- 12 Nec./dia: visita e meta RH no B; desafio e posit no A
_COLS = [{"nome": n} for n in (
    "FAT. META", "FAT. META RH", "FAT. REAL", "POSIT. META", "POSIT. REAL",
    "VISITA META", "VISITA REAL")]
_LINHA = [1400.0, 1000.0, 400.0, 20, 6, 100, 30]   # gaps 1000/600/14/70


def _nec(k):
    return dict((a, b) for a, b, *_ in k["linhas"])["Nec./dia"] \
        if any(a == "Nec./dia" for a, *_ in k["linhas"]) else k["linhas"][-1][1]


def test_RN_GER_007_cartao_nec_dia_visita_e_rh_no_B_desafio_e_posit_no_A():
    """Dia comum (6 DU no A, 7 no B): o Nec./dia divide pelos DU do grupo."""
    ks = {k["rotulo"]: k for k in rn._cartoes_farol(
        [_LINHA], _COLS, 6, 13 / 19 * 100, resta_b=7)}
    assert _nec(ks["Faturamento · desafio comercial"]) == rn.moeda(1000 / 6)
    assert _nec(ks["Positivação"]) == rn.br(14 / 6, 1)
    assert _nec(ks["Visitas"]) == rn.br(70 / 7, 1)
    assert _nec(ks["Faturamento · meta RH"]) == rn.moeda(600 / 7)


def test_RN_GER_007_cartao_nec_dia_no_ultimo_du_visita_e_rh_usam_o_B():
    """Último DU (dias_restantes = 0, dias_restantes_b = 1): visita e meta
    RH dividem por 1 DU (B); desafio e positivação mostram o que falta;
    nenhum cartão diz "mês fechado"."""
    ac = _ac(0, 1)
    ks = {k["rotulo"]: k for k in rn._cartoes_farol(
        [_LINHA], _COLS, 0, rn._esperado(ac), ultimo_dia=rn._ultimo_dia(ac),
        resta_b=rn._resta_b(ac))}
    assert rn.moeda(1000.0) in _nec(ks["Faturamento · desafio comercial"])
    assert "14" in _nec(ks["Positivação"])
    assert "70" in _nec(ks["Visitas"])                      # 70 ÷ 1 DU
    assert rn.moeda(600.0) in _nec(ks["Faturamento · meta RH"])
    for k in ks.values():
        assert not any("mês fechado" in t for t in _textos(k)), k["rotulo"]


def test_RN_GER_007_tabela_do_metas_nec_visita_e_rh_no_B():
    """meta_nucleo (a tabela): nec_visita e nec_fat_rh pelos DU do B;
    nec_fat e nec_positivacao pelos do A."""
    linha = {"meta_visita_int": 100, "visitas_realizadas": 30,
             "meta_positivacao_int": 20, "positivados": 6,
             "meta": 1400.0, "meta_rh": 1000.0, "realizado": 400.0}
    mn._fechar_gaps(linha, 6, 7)
    mn._fechar_rh(linha, 7)
    assert linha["nec_visita"] == pytest.approx(70 / 7)
    assert linha["nec_fat_rh"] == pytest.approx(600 / 7)
    assert linha["nec_fat"] == pytest.approx(1000 / 6)
    assert linha["nec_positivacao"] == pytest.approx(14 / 6)


# ----------------------- 13 RRM por UF: a conta 000040 fora (caso fictício)
def test_RN_GER_005_rrm_por_uf_sem_a_conta_000040():
    """painel_rrm._da_tabela_uf: fat, peças e ticket por UF sem a 000040."""
    d = date(2026, 11, 10)
    itens = [dict(_it(d, "VND", 100.0, cliente="C1", filial=AM), cod="X1"),
             dict(_it(d, "VND", 50.0, cliente="C2", filial=PA), cod="X1"),
             dict(_it(d, "VND", 999.0, cliente="C3", filial=PA, vend="40"),
                  cod="X1"),
             dict(_it(d, "VND", 777.0, cliente="C1", filial=AM,
                      vend="000040"), cod="X1")]
    ctx = SimpleNamespace(
        tabela={"itens": itens, "clientes": {}, "categorias": {"X1": "pecas"}},
        cliente=lambda c: {}, produto=lambda c: "")
    r = prm._da_tabela_uf(ctx, 2026, 11, date(2026, 11, 19), [])
    assert r["fat"]["AM"] == pytest.approx(100.0)
    assert r["fat"]["PA"] == pytest.approx(50.0)
    assert r["pecas"]["AM"] == pytest.approx(100.0)
    assert r["pecas"]["PA"] == pytest.approx(50.0)
    assert r["ticket"]["AM"] == pytest.approx(100.0)
    assert r["ticket"]["PA"] == pytest.approx(50.0)
    # estado da BAP sem nota no mês = 0 (regra de 10/11); o resto = a regra
    assert {u: v for u, v in r["fat"].items() if v} == pytest.approx(
        _regra_por_uf(itens, date(2026, 11, 19)))


# ------------------------------ 14 parcial de RV: inteira no grupo B
def test_RN_GER_007_parcial_de_rv_inteira_no_grupo_B_no_ultimo_du(
        monkeypatch):
    """A parcial de RV é toda do grupo B (#223): no último DU
    (dias_restantes = 0, dias_restantes_b = 1) todos os cartões, inclusive
    desafio e positivação, dividem pelo 1 DU do B; nenhum diz "mês
    fechado". Base congelada; o acompanhamento é o real com os dias
    trocados (o bloco meta@ usa o dia de Manaus da máquina)."""
    ctx = rn.Contexto(RAIZ, date(2026, 11, 30), None, dict(PARAMS))
    original = rn.meta_do_periodo

    def meta_do_periodo(c):
        d = dict(original(c))
        d["acomp"] = dict(d["acomp"], dias_restantes=0, dias_restantes_b=1)
        return d
    monkeypatch.setattr(rn, "meta_do_periodo", meta_do_periodo)
    chamadas = []
    cartoes = rn._cartoes_farol

    def espiao(ls, cols, resta, esperado, *a, **kw):
        chamadas.append((resta, kw.get("resta_b", resta)))
        return cartoes(ls, cols, resta, esperado, *a, **kw)
    monkeypatch.setattr(rn, "_cartoes_farol", espiao)
    ac = meta_do_periodo(ctx)["acomp"]
    v = next(x for x in ac["recortes"]["vendedor"] if x.get("chave"))
    r = rn._exportar_rh(ctx, {"cargo": "VENDEDOR", "cod": v["chave"],
                              "nome": "VENDEDOR"})
    assert chamadas and all(c == (1, 1) for c in chamadas), chamadas
    assert "1 dia(s) útil(eis) até o fim do mês" in r["subtitulo"]
    for k in r["kpis"]:
        assert not any("mês fechado" in t for t in _textos(k)), k["rotulo"]
