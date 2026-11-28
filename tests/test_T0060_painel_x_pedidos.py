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
    ac = rn.meta_do_periodo(ctx)["acomp"]
    return {"itens": itens, "exe": exe, "dir": dire, "ac": ac}


def _kpis(rel, painel=None):
    if painel is None:
        return {k["rotulo"]: k for k in rel["kpis"]}
    p = next(x for x in rel["paineis"] if x.get("titulo") == painel)
    return {k["rotulo"]: k for k in p["kpis"]}


def _linha(k, rot):
    """O valor da linha de rótulo exato `rot` de um cartão."""
    return dict((a, b) for a, b, *_ in k["linhas"])[rot]


def _regra_pecas(ctx, itens, ate):
    """Peças (rn._eh_pecas) líquidas do mês até `ate`, sem a 000040."""
    return sum(_liq(it) for it in _do_mes(itens, ate)
               if rn._eh_pecas(ctx, it["cod"]))


def _card(dire, chave):
    return next(c for c in dire["cards"] if c["chave"] == chave)


ROT_REAL = "Real" + rn.sufixo_periodo(HOJE)


def _kpi_real(kpis):
    assert ROT_REAL == "Real · até 19/11"
    return kpis[ROT_REAL]


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
    DU até ontem (12): peças ÷ 12 × 19, como antes da decisão 43."""
    ctx = rn.Contexto(RAIZ, HOJE, None, dict(PARAMS))
    ontem, ndp_b = date(2026, 11, 18), DU_PASSADOS_COM_HOJE - 1
    pecas = _regra_pecas(ctx, base["itens"], ontem)
    r = prm.calcular(ctx, 2026, 11, dd=base["dir"])
    c = next(x for x in r["res"] if x["chave"] == "pecas")
    assert c["valor"] == prm.reais(pecas / ndp_b * DU_MES)   # R$ 16,9 mil
    assert c["titulo"].endswith(" · até 18/11")
    d = next(x for x in r["du"] if x["chave"] == "pecas")
    assert d["valor"] == prm.reais(pecas / ndp_b)             # R$ 889
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


def test_RN_GER_003_positivacao_projetada_66_no_metas_e_no_diretor():
    """45 positivados ÷ 13 × 19 = 65,8 → 66 no cartão do Metas, a mesma
    conta do Diretor (ver o teste do Diretor × Executivo)."""
    ac = _ac(DU_MES - DU_PASSADOS_COM_HOJE, DU_MES - DU_PASSADOS_COM_HOJE + 1)
    k = rn._cartao_indicador("Positivação", 163, 45,
                             ac["dias_restantes"], rn._esperado(ac),
                             real_proj=45, ultimo_dia=rn._ultimo_dia(ac))
    assert _linha(k, "Projeção do mês").startswith("66 ")


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
def test_RN_GER_007_farol_de_pedidos_cartao_pedidos_digitados(base):
    """Pedidos digitados = (filial, pedido) distintos do mês, sem o cliente
    fora da base (RN-GER-013)."""
    p = rn.montar("pv_pedidos", RAIZ, hoje=HOJE, params=dict(PARAMS))
    k = {x["rotulo"]: x for x in p["kpis"]}
    assert "Pedidos" not in k
    t = p["tabelas"][0]
    ix = {c["nome"]: i for i, c in enumerate(t["colunas"])}
    dig = {(ln[ix["FILIAL"]], ln[ix["PEDIDO"]]) for ln in t["linhas"]
           if ln[ix["MÊS"]] == "NOV/26"
           and ln[ix["RAZÃO SOCIAL"]] != rn.NOME_FORA_DA_BASE}
    assert k["Pedidos digitados"]["valor"] == rn.br(len(dig)) == "113"
    # o Faturado do Farol de Pedidos = o real do Executivo (mesma base)
    assert k["Faturado"]["valor"] == rn.moeda(_regra_real(base["itens"],
                                                          HOJE))


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


def _nec(k, rot="Nec./dia"):
    """A linha do Nec./dia (no último DU: "Falta hoje")."""
    return _linha(k, rot)


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
    ult = "Falta hoje"
    assert _nec(ks["Faturamento · desafio comercial"], ult) == rn.moeda(1000.0)
    assert _nec(ks["Positivação"], ult) == rn.br(14)
    assert _nec(ks["Visitas"], ult) == rn.br(70)             # 70 ÷ 1 DU
    assert _nec(ks["Faturamento · meta RH"], ult) == rn.moeda(600.0)
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


# ---------------------- 15 parcial de RV: o que é de hoje (núcleo puro)
def _pc(it, cod):
    return dict(it, cod=cod)


def _eh_p(cod):
    return cod == "PEC"


def test_RN_GER_007_hoje_dos_itens_fat_pecas_e_quem_so_positivou_hoje():
    """Faturamento e peças de hoje separados; C2 só positivou hoje; a conta
    000040 fica fora; a visita de hoje sai do Espelho de hoje."""
    ontem = HOJE.replace(day=18)
    itens = [_pc(_it(ontem, "VND", 100.0, cliente="C1"), "PEC"),
             _pc(_it(HOJE, "VND", 50.0, cliente="C1"), "PEC"),
             _pc(_it(HOJE, "VND", 30.0, cliente="C2"), "BAT"),
             _pc(_it(HOJE, "VND", 999.0, cliente="C9", vend="000040"), "PEC")]
    regs = [{"data": HOJE, "visitas": 3}]
    h = rn.hoje_dos_itens(itens, regs, HOJE, _eh_p)
    assert h["FAT."] == pytest.approx(80.0)                 # 50 + 30
    assert h["PEÇAS"] == pytest.approx(50.0)
    assert h["POSIT."] == 1                                 # só o C2
    assert h["POSIT."] == len(_regra_por_cliente(itens, HOJE)) - len(
        _regra_por_cliente(itens, ontem))
    assert h["VISITA"] == 3
    # o real até ontem = o real do mês − o de hoje
    assert _regra_real(itens, HOJE) - h["FAT."] == pytest.approx(
        _regra_real(itens, ontem))


def test_RN_GER_007_hoje_dos_itens_devolucao_de_hoje_tira_a_positivacao():
    """Devolução total hoje de quem tinha positivado: POSIT. = −1 e FAT.
    negativo (sem max(0): o até ontem continua com o cliente)."""
    ontem = HOJE.replace(day=18)
    itens = [_pc(_it(ontem, "VND", 40.0, cliente="C3"), "BAT"),
             _pc(_it(HOJE, "DEV", 40.0, cliente="C3"), "BAT")]
    h = rn.hoje_dos_itens(itens, [], HOJE, _eh_p)
    assert h["POSIT."] == -1
    assert h["FAT."] == pytest.approx(-40.0)
    assert h["PEÇAS"] == 0.0 and h["VISITA"] == 0


def test_RN_GER_007_hoje_dos_itens_dia_1_ate_ontem_e_zero():
    """Dia 1 do mês: ontem é do mês anterior, então o até ontem do mês é 0
    (a venda de outubro não conta)."""
    d1 = date(2026, 12, 1)
    itens = [_pc(_it(date(2026, 11, 30), "VND", 500.0, cliente="C1"), "PEC"),
             _pc(_it(d1, "VND", 70.0, cliente="C1"), "PEC"),
             _pc(_it(d1, "VND", 20.0, cliente="C2"), "BAT")]
    h = rn.hoje_dos_itens(itens, [{"data": d1, "visitas": 2}], d1, _eh_p)
    assert h["FAT."] == pytest.approx(90.0)
    assert h["PEÇAS"] == pytest.approx(70.0)
    assert h["POSIT."] == 2                     # o mês inteiro é de hoje
    assert h["VISITA"] == 2
    assert _regra_real(itens, d1) - h["FAT."] == pytest.approx(0.0)


def test_RN_GER_007_esperado_do_grupo_B_e_du_da_vista_da_parcial():
    """% corrido: A = (19 − 6) ÷ 19 (hoje conta); B = (19 − 7) ÷ 19. A
    parcial de RV (com corte) é inteira do B."""
    ac = _ac(6, 7)
    assert rn._esperado(ac) == pytest.approx(13 / 19 * 100)
    assert rn._esperado(ac, True) == pytest.approx(12 / 19 * 100)
    assert rn._du_da_vista(ac, date(2026, 11, 18)) == pytest.approx(
        (7, 7, 12 / 19 * 100))
    assert rn._du_da_vista(ac, None) == pytest.approx((6, 7, 13 / 19 * 100))


def test_RN_GER_007_cartoes_da_parcial_projetam_o_real_ate_ontem_no_B():
    """Parcial de RV (grupo B): o real exibido e o projetado são o real até
    ontem (real − o de hoje); projeção = esse real ÷ % corrido do B (12/19);
    Nec./dia = (meta − real até ontem) ÷ DU do B. Cad. não separa hoje e
    leva o período no rótulo."""
    esp_b = rn._esperado(_ac(7, 7), True)
    hoje_b = {"FAT.": 100.0, "POSIT.": 2, "VISITA": 10}
    cols = _COLS + [{"nome": "CAD. META"}, {"nome": "CAD. REAL"}]
    ks = {k["rotulo"]: k for k in rn._cartoes_farol(
        [_LINHA + [10, 4]], cols, 7, esp_b, resta_b=7, hoje_b=hoje_b,
        rot_cad=rn.sufixo_periodo(HOJE))}
    f = 12 / 19
    assert ks["Faturamento · desafio comercial"]["valor"] == rn.moeda(300.0)
    assert ks["Positivação"]["valor"] == rn.br(4)
    assert ks["Visitas"]["valor"] == rn.br(20)
    assert ks["Cad. com compra · até 19/11"]["valor"] == rn.br(4)
    pj = "Projeção do mês"
    assert _linha(ks["Faturamento · desafio comercial"], pj).startswith(
        rn.moeda((400.0 - 100.0) / f) + " ")                # R$ 475
    assert _linha(ks["Faturamento · meta RH"], pj).startswith(
        rn.moeda((400.0 - 100.0) / f) + " ")
    assert _linha(ks["Positivação"], pj).startswith(rn.br((6 - 2) / f) + " ")
    assert _linha(ks["Visitas"], pj).startswith(rn.br((30 - 10) / f) + " ")
    assert _nec(ks["Visitas"]) == rn.br((100 - 20) / 7, 1)      # 11,4


def test_RN_GER_007_cad_nao_separa_hoje_mesmo_com_cad_no_hoje_b():
    """SEM_SEPARAR_HOJE = {"CAD."}: mesmo que hoje_b traga CAD. (≠ 0), o
    real do cartão Cad. continua o do mês (até hoje); o faturamento, sim,
    sai até ontem."""
    assert "CAD." in rn.SEM_SEPARAR_HOJE
    cols = [{"nome": n} for n in ("FAT. META", "FAT. REAL", "CAD. META",
                                  "CAD. REAL")]
    ks = {k["rotulo"]: k for k in rn._cartoes_farol(
        [[1000.0, 400.0, 10, 4]], cols, 7, 60.0, resta_b=7,
        hoje_b={"FAT.": 100.0, "CAD.": 3}, rot_cad=rn.sufixo_periodo(HOJE))}
    assert ks["Faturamento · desafio comercial"]["valor"] == rn.moeda(300.0)
    assert ks["Cad. com compra · até 19/11"]["valor"] == rn.br(4)


def test_RN_GER_007_parcial_de_rv_mostra_o_real_ate_ontem(base):
    """Base congelada, hoje = 19/11, parcial do gerente (a BAP): os cartões
    mostram o real até 18/11 pela regra - faturamento R$ 109.575,
    positivação 43, visitas 989 (= Diretor), peças R$ 10.674; o Cad. leva
    " · até 19/11" (não separa hoje)."""
    ctx = rn.Contexto(RAIZ, HOJE, None, dict(PARAMS))
    ger = base["ac"]["recortes"]["gerente"][0]
    r = rn._exportar_rh(ctx, {"cargo": "GERENTE", "cod": ger.get("chave"),
                              "nome": ger.get("rotulo") or ger.get("nome")})
    k = {x["rotulo"]: x["valor"] for x in r["kpis"]}
    ontem = date(2026, 11, 18)
    itens = base["itens"]
    pecas = _regra_pecas(ctx, itens, ontem)
    assert k["Faturamento · desafio comercial"] == rn.moeda(
        _regra_real(itens, ontem)) == "R$ 109.575"
    assert k["Positivação"] == rn.br(len(_regra_por_cliente(itens, ontem))) \
        == "43"
    assert k["Visitas"] == rn.br(_card(base["dir"], "visitas")["numero"]) \
        == "989"
    assert k["Peças"] == rn.moeda(pecas) == "R$ 10.674"
    assert "Cad. com compra" + rn.sufixo_periodo(HOJE) in k
    assert "Cad. com compra" not in k
    # o e-mail da parcial (resumo_desafio e resumo_pessoa): o mesmo real
    # até ontem (a projeção e o Nec./dia dependem do dia do bloco meta@)
    assert r["resumo_desafio"][2] == "R$ 109.575"
    reais = {x[0]: x[2] for x in r["resumo_pessoa"]}
    assert reais == {"Meta Fat.": "R$ 109.575", "Positivação": "43",
                     "Visita": "989"}
    # PDF de detalhe: a coluna fica "REAL" e o período vai no título
    com_real = [t for t in r["tabelas"]
                if any(c.get("curto") == "REAL" for c in t["colunas"])]
    assert com_real
    for t in com_real:
        assert t["sufixo_titulo"] == rn.sufixo_periodo(HOJE) == " · até 19/11"
        assert " · até" not in t["titulo"]
        assert not any(" · até" in str(c.get("curto") or c["nome"])
                       for c in t["colunas"])


# ------------------------------------- 16 visitas de hoje (núcleo puro)
def test_RN_GER_007_visitas_de_hoje_data_cod_protheus_e_ativo():
    """visitas_de_hoje(regs, hoje, cods): só as linhas de hoje; o filtro de
    vendedor é pelo código PROTHEUS (não o da Máxima). O `ativo` é filtro
    de quem chama (Diretor e Farol de Visita), não da função."""
    regs = [
        {"data": HOJE, "visitas": 5, "cod_protheus": "101", "cod": "9001",
         "ativo": True},
        {"data": HOJE, "visitas": 3, "cod_protheus": "000102", "cod": "101",
         "ativo": True},
        {"data": HOJE, "visitas": 7, "cod_protheus": "000103", "cod": "9003",
         "ativo": False},
        {"data": HOJE.replace(day=18), "visitas": 11, "cod_protheus": "101",
         "cod": "9001", "ativo": True},
        # só prospecção hoje (sem linha da Máxima): a linha própria que o
        # com_cadastro_como_visita cria também sai
        {"data": HOJE, "visitas": 2, "prosp_visita": 2,
         "cod_protheus": "000104", "ativo": True},
    ]
    assert rn.visitas_de_hoje(regs, HOJE) == 17             # cods=None
    assert rn.visitas_de_hoje(regs, HOJE, None) == 17
    assert rn.visitas_de_hoje(regs, HOJE, {"000101"}) == 5   # Protheus
    assert rn.visitas_de_hoje(regs, HOJE, {"009001"}) == 0   # Máxima: não
    assert rn.visitas_de_hoje(regs, HOJE, {"000104"}) == 2   # prospecção
    ativos = [r for r in regs if r.get("ativo")]
    assert rn.visitas_de_hoje(ativos, HOJE) == 10
    assert rn.visitas_de_hoje(regs, HOJE.replace(day=20)) == 0


def test_RN_GER_007_visitas_ate_ontem_do_diretor_igual_ao_farol_de_visita(
        base):
    """Base congelada, hoje = 19/11: Diretor = Farol de Visita − as visitas
    de hoje (ativos, com cadastro como visita) = 1.074 − 85 = 989;
    projeção = 989 ÷ 12 DU até ontem × 19 = 1.566."""
    import visitas_nucleo as vn
    ctx = rn.Contexto(RAIZ, HOJE, None, dict(PARAMS))
    fv = rn.montar("vc_visitas", RAIZ, hoje=HOJE, params=dict(PARAMS))
    k = next(x for x in fv["kpis"] if x["rotulo"] == "Visitas")
    farol = pdr._num(k["valor"])
    hoje_v = rn.visitas_de_hoje(
        [r for r in rn.com_cadastro_como_visita(
            ctx, vn.registros(RAIZ, de=HOJE)) if r.get("ativo")], HOJE)
    assert (farol, hoje_v) == (1074, 85)
    # o lugar único das linhas de hoje (lê o mês, filtra hoje e os ativos)
    assert rn.visitas_de_hoje(rn.linhas_visita_de_hoje(ctx), HOJE) == hoje_v
    c = _card(base["dir"], "visitas")
    assert c["numero"] == farol - hoje_v == 989
    assert c["projecao"] == pytest.approx(989 / (DU_PASSADOS_COM_HOJE - 1)
                                          * DU_MES)
    assert round(c["projecao"]) == 1566


def test_RN_GER_007_ate_ontem_devolve_o_real_e_nunca_none():
    """_ate_ontem(real, hoje_b, ind): sem o de hoje = o próprio real (não
    None); indicador fora de hoje_b = o real (o Cad. tem teste próprio);
    com hoje = real − o
    de hoje, inclusive negativo (devolução)."""
    assert rn._ate_ontem(400.0, None, "FAT.") == 400.0
    assert rn._ate_ontem(400.0, {}, "FAT.") == 400.0
    assert rn._ate_ontem(4, {"FAT.": 100.0}, "CAD.") == 4
    assert rn._ate_ontem(400.0, {"FAT.": 100.0}, "FAT.") == 300.0
    assert rn._ate_ontem(6, {"POSIT.": -1}, "POSIT.") == 7
    assert rn._ate_ontem(None, {"FAT.": 100.0}, "FAT.") is None


def test_RN_GER_007_rv_ate_ontem_paga_pela_faixa_do_real_ate_ontem():
    """rv_ate_ontem: a RV com o real ATE ONTEM (fat pela meta RH, positivação
    e visita). Faixa sintética: < 90% = 0; 90–99,999% = R$ 500; ≥ 100% =
    R$ 1.000. Com hoje bate 100% em tudo; sem hoje cai para 90%, 90% e
    92,6% (125 de 135 visitas)."""
    faixa = [{"de": 0.0, "ate": 89.999, "valor": 0.0},
             {"de": 90.0, "ate": 99.999, "valor": 500.0},
             {"de": 100.0, "ate": 999999.0, "valor": 1000.0}]
    par = {"rv": {"vendedor": {k: faixa for k in ("fat", "positivacao",
                                                  "visita")}}}
    linha = {"realizado": 1000.0, "meta_rh": 1000.0, "atingimento_rh": 100.0,
             "positivados": 10, "meta_positivacao": 10,
             "atingimento_positivacao": 100.0, "visitas_realizadas": 135,
             "meta_visita": 135, "atingimento_visita": 100.0}
    com_hoje = mn.rv_da_linha(par, "vendedor", linha)
    assert com_hoje["rv_total"] == 3000.0
    hoje_b = {"FAT.": 100.0, "POSIT.": 1, "VISITA": 10}
    rv = rn.rv_ate_ontem(mn.rv_da_linha, par, "vendedor", linha, hoje_b,
                         mn.fechar_atingimentos)
    assert (rv["rv_fat"], rv["rv_positivacao"], rv["rv_visita"]) == (
        500.0, 500.0, 500.0)
    assert rv["rv_total"] == 1500.0
    assert linha["atingimento_rh"] == 100.0          # a linha não muda
    # visita sem meta: sem atingimento (o caso {} fica na trava abaixo)
    vis = []
    rn.rv_ate_ontem(lambda p_, n_, l_: vis.append(l_) or {}, par,
                    "vendedor", dict(linha, meta_visita=None), hoje_b,
                    mn.fechar_atingimentos)
    assert vis[0]["atingimento_visita"] is None


@pytest.mark.parametrize("hoje_b", [{}, {"FAT.": 0.0, "POSIT.": 0,
                                         "VISITA": 0}])
def test_RN_GER_007_rv_ate_ontem_com_hoje_zero_igual_a_rv_do_acompanhamento(
        base, hoje_b):
    """Trava (RD-c): sem nada de hoje, rn.rv_ate_ontem = a RV que o
    meta_nucleo.acompanhar gravou em cada linha (vendedor e supervisor) e
    na RV total. Base congelada; só códigos e valores, sem nome."""
    ac = base["ac"]
    par = mn.carregar_parametros(RAIZ / "meta_config.json")
    n = 0
    for nivel in ("vendedor", "supervisor"):
        for linha in ac["recortes"][nivel]:
            if linha.get("rv_total") is None:
                continue
            rv = rn.rv_ate_ontem(mn.rv_da_linha, par, nivel, linha, hoje_b,
                                 mn.fechar_atingimentos)
            for k in ("rv_fat", "rv_positivacao", "rv_visita", "rv_total"):
                assert rv[k] == pytest.approx(linha[k]), (
                    nivel, linha.get("chave"), k)
            n += 1
    assert n > 0


# --------------------------- 17 meta_nucleo.fechar_atingimentos (puro)
def test_RN_GER_007_fechar_atingimentos_casos_e_retorno():
    """fechar_atingimentos(linha, dias_rh): devolve a mesma linha com os
    atingimentos de RH, positivação e visita; meta_rh vazia cai na meta;
    nec_fat_rh só com dias_rh (0 vira None; sem dias_rh fica como estava)."""
    base_l = {"realizado": 600.0, "meta": 1200.0, "meta_rh": 1000.0,
              "positivados": 9, "meta_positivacao": 12,
              "visitas_realizadas": 45, "meta_visita": 60}
    l = dict(base_l)
    assert mn.fechar_atingimentos(l, 2) is l
    assert l["atingimento_rh"] == pytest.approx(60.0)
    assert l["falta_rh"] == pytest.approx(400.0)
    assert l["nec_fat_rh"] == pytest.approx(200.0)          # 400 ÷ 2 DU (B)
    assert l["atingimento_positivacao"] == pytest.approx(75.0)
    assert l["atingimento_visita"] == pytest.approx(75.0)
    # meta_rh vazia: cai para a meta (comercial)
    l = mn.fechar_atingimentos(dict(base_l, meta_rh=None), 2)
    assert l["meta_rh"] == 1200.0
    assert l["atingimento_rh"] == pytest.approx(50.0)
    # dias_rh = 0: nec_fat_rh None; sem dias_rh: não cria nem mexe
    assert mn.fechar_atingimentos(dict(base_l), 0)["nec_fat_rh"] is None
    assert "nec_fat_rh" not in mn.fechar_atingimentos(dict(base_l))
    assert mn.fechar_atingimentos(dict(base_l, nec_fat_rh=7.0))[
        "nec_fat_rh"] == 7.0
    # visita sem meta ou sem real: None
    assert mn.fechar_atingimentos(dict(base_l, meta_visita=None))[
        "atingimento_visita"] is None
    assert mn.fechar_atingimentos(dict(base_l, visitas_realizadas=None))[
        "atingimento_visita"] is None


def test_RN_GER_007_fechar_atingimentos_igual_ao_que_o_acompanhar_grava(
        base):
    """Base congelada: refazer os atingimentos de cada linha (vendedor e
    supervisor) com fechar_atingimentos(dias_restantes_b) dá o mesmo que o
    meta_nucleo.acompanhar gravou. Só códigos e valores, sem nome."""
    ac = base["ac"]
    dias_b = ac["dias_restantes_b"]
    chaves = ("atingimento_rh", "falta_rh", "meta_rh", "nec_fat_rh",
              "atingimento_positivacao", "atingimento_visita")
    n = 0
    for nivel in ("vendedor", "supervisor"):
        for linha in ac["recortes"][nivel]:
            novo = mn.fechar_atingimentos(dict(linha), dias_b)
            for k in chaves:
                assert novo.get(k) == pytest.approx(linha.get(k)), (
                    nivel, linha.get("chave"), k)
            n += 1
    assert n > 0
