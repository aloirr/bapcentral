"""T-0023 v2: valor x regra dos 3 farois do pos-venda no site (Garantias,
Devolucoes e NCC), com o pacote REAL das bases congeladas (hoje = 24/11/2026,
terca; params ANO=2026, MES=11). Desenho docs/desenho/T-0023.md, secao 5.

Cada numero do site e refeito aqui pela regra, a partir das linhas do proprio
pacote (ou da base), e comparado com o cartao do PC:
- RN-POS-005: DT. FECHAMENTO da garantia = solicitacao + 15 dias uteis;
- RN-POS-006: NCC atrasada = hoje depois de (ultima movimentacao ou emissao)
  + 3 dias uteis;
- RN-GER-007: dia util = seg a sex menos os feriados (bap_dados.feriados);
  hoje fica fora (o prazo que vence hoje ainda nao atrasou);
- RN-GER-006: estado = FILIAL da nota; o cartao do estado soma a BAP;
- RN-GER-002: faturado = VND - DEV pela data da NF (o "% do faturado");
- RN-GER-011: nada de CPF, CNPJ, e-mail ou telefone no JSON do farol, pelos
  padroes do bloco `padroes-pessoais` do contrato (10.9.1);
- RN-GER-014: o cartao do site (o Resumo que o diretor ve) e o do PC, texto
  a texto; o do Painel Executivo bate com o farol de origem.

Nenhum valor de celula e impresso: as mensagens de falha so tem titulo,
coluna, indice e contagens.
"""
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import bap_automation as ba

if "pl_ncc" not in getattr(ba, "FAROIS_WEB", ()) or not hasattr(ba, "CAMPOS_LUGAR_WEB"):
    pytest.skip("robô da T-0023 v2 (modulo-robo/T-0023-robo) ainda não entrou", allow_module_level=True)

import bap_dados as bd  # noqa: E402
import garantias as gm  # noqa: E402
import ncc_controle as nc  # noqa: E402
import relatorios_nucleo as rn  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
TRES = ("pl_garantias", "pl_devolucoes", "pl_ncc")
MES = "NOV/26"
# desenho 5.1: linhas por aba, medidas nas bases congeladas
LINHAS = {"pl_garantias": [12, 4949, 5, 3],
          "pl_devolucoes": [188, 13, 21, 129, 199],
          "pl_ncc": [11, 9, 5, 7, 4]}
# colunas de codigo de produto: o codigo do ERP pode ter 11 ou 14 digitos
# (nao e CPF nem CNPJ). So o numero puro passa; formatado como documento,
# reprova. Fonte: contrato 10.10.2 (CÓD. PRODUTO e PRODUTO = codigo).
COLUNAS_CODIGO_PRODUTO = frozenset({"CÓD. PRODUTO", "PRODUTO"})
# CPF e CNPJ formatados (com ponto, barra e hifen): numero JSON nunca casa
RE_DOC_FORMATADO = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")


def _padroes_do_contrato():
    txt = (RAIZ / ".coord" / "contratos" / "relatorio.md").read_text(encoding="utf-8")
    bloco = txt.split("```text padroes-pessoais", 1)[1].split("```", 1)[0]
    saida = {}
    for ln in bloco.strip().splitlines():
        nome, rx = ln.strip().split(" ", 1)
        saida[nome] = rx
    return saida


PADROES = _padroes_do_contrato()
PESSOAL = {k: re.compile(PADROES[k]) for k in ("EMAIL", "DOC_MEIO", "DOC_SOLTO", "FONE")}


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def real():
    """(PC montado, pacote do site) dos 3 farois nas bases congeladas."""
    pcs = {r: rn.montar(r, RAIZ, hoje=HOJE, params=ba.params_farol_web(r, 2026, 11)) for r in TRES}
    pac = ba.montar_pacote_web(pcs, 2026, 11, raiz=RAIZ)
    return pcs, pac["relatorios"]


@pytest.fixture(scope="module")
def fer():
    return bd.feriados(RAIZ)


def _tab(farois, rid, titulo):
    return next(t for t in farois[rid]["tabelas"] if t["titulo"] == titulo)


def _col(t, nome):
    i = [c["nome"] for c in t["colunas"]].index(nome)
    return [ln[i] for ln in t["linhas"]]


def _linhas(t, *nomes):
    ix = [[c["nome"] for c in t["colunas"]].index(n) for n in nomes]
    return [tuple(ln[i] for i in ix) for ln in t["linhas"]]


def _kpi(ks, rotulo):
    return next(k for k in ks if k["rotulo"] == rotulo)


def _rvd(ks):
    return [(k["rotulo"], k["valor"], k.get("detalhe")) for k in ks]


def _iso(v):
    return date.fromisoformat(v) if isinstance(v, str) and v else (v or None)


def _du_mais(d, n, fer):
    """d + n dias uteis (seg a sex, sem feriado), contados depois de d."""
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in fer:
            n -= 1
    return d


# ------------------------------------------------------------------ 5.1 o pacote
def test_T0023_pacote_os_3_farois_do_pos_venda(real):
    _pcs, f = real
    for rid in TRES:
        assert f[rid]["forma"] == "farol"
        assert [len(t["linhas"]) for t in f[rid]["tabelas"]] == LINHAS[rid], rid
        tam = len(ba._json_farol_web(f[rid]))
        assert tam < ba.WEB_FAROL_TETO_MB * 1048576, rid
    assert 1_000_000 < len(ba._json_farol_web(f["pl_garantias"])) < 1_500_000     # ~1,3 MB


def test_ADR0003_10_10_4_teto_de_1_MB_tira_so_o_historico(real):
    """Desenho 5.8: com o teto artificial de 1 MB, o "Histórico de compra" sai
    com o AVISO_ABAS_FORA, e as outras 3 abas ficam, inteiras."""
    _pcs, f = real
    g = f["pl_garantias"]
    cortado = ba._cortar_farol_web("pl_garantias", g, teto_mb=1)
    assert [t["titulo"] for t in cortado["tabelas"]] == ["Garantias", "Por produto", "Status x resultado"]
    assert ba.AVISO_ABAS_FORA.format(lista="Histórico de compra") in cortado["avisos"]
    assert [len(t["linhas"]) for t in cortado["tabelas"]] == [12, 5, 3]
    assert len(ba._json_farol_web(cortado)) < 1048576
    assert cortado["kpis"] == g["kpis"]                                     # o cartão não muda


def test_T0023_a_web_aceita_os_3_farois(real):
    """Desenho 5.1: a web aceita cada farol (tabelas.validar sem erro). Só
    roda quando a web da T-0023 (COLUNAS_RID, contrato 10.10.1) entrar."""
    _pcs, f = real
    antes = set(sys.modules)
    sys.path.insert(0, str(RAIZ / "web"))
    try:
        from app import tabelas
        if not hasattr(tabelas, "COLUNAS_RID"):
            pytest.skip("web da T-0023 v2 (tabelas.COLUNAS_RID, §10.10.1) ainda não entrou")
        for rid in TRES:
            assert tabelas.validar(rid, f[rid]) == [], rid
    finally:
        sys.path.remove(str(RAIZ / "web"))
        for k in set(sys.modules) - antes:
            if k == "app" or k.startswith("app."):
                del sys.modules[k]


# ------------------------------------------------------------------ 5.2 o número do site é o do PC
def test_RN_GER_014_cartoes_do_site_sao_os_do_pc_texto_a_texto(real):
    pcs, f = real
    for rid in TRES:
        assert _rvd(f[rid]["kpis"]) == _rvd(pcs[rid]["kpis"]), rid
        # a aba principal abre com os mesmos cartões (kpis_padrao)
        t0 = f[rid]["tabelas"][0]
        assert _rvd(t0["kpis_padrao"]) == _rvd(pcs[rid]["kpis"]), rid


def test_RN_GER_014_graficos_do_ncc_no_painel_sao_os_do_pc(real):
    """O NCC não tem Resumo no PC: os gráficos viram blocos de barras, com os
    mesmos rótulos e valores (o robô monta, a web não calcula)."""
    pcs, f = real
    gs = [g for g in pcs["pl_ncc"]["graficos"] if g.get("rotulos")]
    blocos = f["pl_ncc"]["painel"]["blocos"]
    assert len(blocos) == len(gs)
    for b, g in zip(blocos, gs):
        gb = b["grafico"]
        assert gb["titulo"] == g["titulo"] and list(gb["rotulos"]) == list(g["rotulos"])
        assert [list(s["valores"]) for s in gb["series"]] == [list(s["valores"]) for s in g["series"]]


def test_RN_POS_005_prazo_da_garantia_15_du(real, fer):
    """DT. FECHAMENTO = DT. SOLICITAÇÃO + 15 dias úteis (sem prazo editado);
    "Em aberto" = STATUS fora de FINALIZADA/CANCELADA; "Atrasadas" = abertas
    com hoje depois da DT. FECHAMENTO (hoje fora: vencer hoje não atrasa)."""
    pcs, f = real
    t = _tab(f, "pl_garantias", "Garantias")
    brutas = gm.ler(RAIZ)
    conferidas = 0
    abertas = atrasadas = 0
    for st, tk, sol, fech, prazo in _linhas(t, "STATUS", "TICKET", "DT. SOLICITAÇÃO",
                                           "DT. FECHAMENTO", "PRAZO"):
        sol, fech = _iso(sol), _iso(fech)
        if not gm.data(brutas[tk].get("dt_prazo")):
            assert fech == _du_mais(sol, 15, fer), tk
            conferidas += 1
        if st not in ("FINALIZADA", "CANCELADA"):
            abertas += 1
            atrasou = HOJE > fech
            atrasadas += atrasou
            assert (prazo == "ATRASADA") == atrasou, tk
    assert conferidas >= 1
    k = pcs["pl_garantias"]["kpis"]
    assert _kpi(k, "Em aberto")["valor"] == rn.br(abertas)
    assert _kpi(k, "Atrasadas")["valor"] == rn.br(atrasadas)


def test_RN_GER_007_hoje_fora_do_du_no_prazo_da_garantia_e_da_ncc(fer):
    """O prazo que vence hoje ainda não atrasou; o de ontem, sim. Vale para a
    garantia (15 DU) e para a NCC (3 DU). Dados fictícios."""
    def solicitacao_com_prazo(prazo, n):
        d = prazo
        while _du_mais(d, n, fer) != prazo:
            d -= timedelta(days=1)
        return d
    ontem = HOJE - timedelta(days=1)             # 23/11/2026, segunda (dia útil)
    assert ontem.weekday() == 0 and ontem not in fer
    sol_hoje = solicitacao_com_prazo(HOJE, 15)
    sol_ontem = solicitacao_com_prazo(ontem, 15)
    assert gm.situacao({"dt_solicitacao": sol_hoje.strftime("%d/%m/%Y"), "status": "ABERTO"},
                       HOJE, fer)["atrasada"] is False
    assert gm.situacao({"dt_solicitacao": sol_ontem.strftime("%d/%m/%Y"), "status": "ABERTO"},
                       HOJE, fer)["atrasada"] is True

    def mais(d, n):
        return bd.somar_uteis(d, n, fer)

    def uteis(a, b):
        return bd.dias_uteis_entre(a, b, fer)
    base_hoje = solicitacao_com_prazo(HOJE, nc.SLA_NCC)
    base_ontem = solicitacao_com_prazo(ontem, nc.SLA_NCC)
    assert nc.sla("NO TÍTULO", None, base_hoje, HOJE, uteis, mais)[2] == nc.SLA_NO_PRAZO
    assert nc.sla("NO TÍTULO", None, base_ontem, HOJE, uteis, mais)[2] == nc.SLA_ATRASADO
    # sábado e feriado não contam: o prazo de 3 DU de uma sexta cai na quarta
    sexta = date(2026, 11, 13)
    assert sexta.weekday() == 4 and bd.somar_uteis(sexta, 3, set()) == date(2026, 11, 18)
    assert bd.somar_uteis(sexta, 3, {date(2026, 11, 16)}) == date(2026, 11, 19)


def test_RN_POS_006_sla_ncc_3_du(real, fer):
    """NCC atrasada = hoje depois de (DT. ÚLT. MOV. ou EMISSÃO) + 3 DU; as
    encerradas (FINALIZADO / CANCELADO) não contam."""
    pcs, f = real
    t = _tab(f, "pl_ncc", "NCC pendentes")
    atrasadas = 0
    for i, (sla, mov, emi) in enumerate(_linhas(t, "SLA NCC", "DT. ÚLT. MOV.", "EMISSÃO")):
        if sla == nc.SLA_ENCERRADO:
            continue
        prazo = _du_mais(_iso(mov) or _iso(emi), nc.SLA_NCC, fer)
        atrasou = HOJE > prazo
        atrasadas += atrasou
        assert (sla == nc.SLA_ATRASADO) == atrasou, i
    assert _kpi(pcs["pl_ncc"]["kpis"], f"SLA atrasado ({nc.SLA_NCC} d.u.)")["valor"] == rn.br(atrasadas)


def _du_fechados(de, ate, fer):
    """Dias úteis depois de `de` até `ate` (inclusive), contados à mão."""
    n, d = 0, de
    while d < ate:
        d += timedelta(days=1)
        n += d.weekday() < 5 and d not in fer
    return n


def test_RN_GER_007_du_sem_mov_da_ncc_nao_conta_o_hoje(real, fer):
    """D.U. S/ MOV. = dias úteis depois da última movimentação (ou da
    emissão) até ONTEM: hoje (24/11, terça, dia útil) fica fora. Em cada
    linha não encerrada, a conta até hoje daria 1 a mais."""
    _pcs, f = real
    t = _tab(f, "pl_ncc", "NCC pendentes")
    ontem = HOJE - timedelta(days=1)
    assert HOJE.weekday() < 5 and HOJE not in fer
    conferidas = 0
    for i, (sla, mov, emi, du) in enumerate(_linhas(t, "SLA NCC", "DT. ÚLT. MOV.", "EMISSÃO",
                                                    "D.U. S/ MOV.")):
        if sla == nc.SLA_ENCERRADO:
            continue
        base = _iso(mov) or _iso(emi)
        assert du == _du_fechados(base, ontem, fer), i
        if base < HOJE:
            assert du == _du_fechados(base, HOJE, fer) - 1, i          # sem o hoje
            conferidas += 1
    assert conferidas >= 1


def test_RN_GER_006_ncc_saldo_bate_em_todas_as_abas_e_os_estados_somam_a_bap(real):
    """Saldo a compensar = soma do SALDO das NCC não encerradas = TOTAL das
    abas Por filial, Por vendedor, Por supervisor e Por cliente; as faixas de
    idade somam o saldo; "Acima de 90 dias" = 91-180 + +180; o cartão de cada
    estado é a soma das linhas da FILIAL da nota daquele estado."""
    _pcs, f = real
    t = _tab(f, "pl_ncc", "NCC pendentes")
    ls = [(s, sl, uf) for (s, sl), uf in zip(_linhas(t, "SALDO", "SLA NCC"), t["uf_linhas"])
          if sl != nc.SLA_ENCERRADO]
    saldo = sum(s for s, _sl, _uf in ls)
    k = f["pl_ncc"]["kpis"]
    assert _kpi(k, "Saldo a compensar")["valor"] == rn.moeda(saldo)
    for titulo in ("Por filial", "Por vendedor", "Por supervisor", "Por cliente"):
        tt = _tab(f, "pl_ncc", titulo)
        nomes = [c["nome"] for c in tt["colunas"]]
        assert math.isclose(tt["total"][nomes.index("SALDO")], saldo, abs_tol=0.01), titulo
        assert math.isclose(sum(_col(tt, "SALDO")), saldo, abs_tol=0.01), titulo
    pf = _tab(f, "pl_ncc", "Por filial")
    nomes = [c["nome"] for c in pf["colunas"]]
    tot = dict(zip(nomes, pf["total"]))
    assert tot["NCC"] == len(ls)
    faixas = ("0-30 DIAS", "31-90 DIAS", "91-180 DIAS", "+180 DIAS")
    assert math.isclose(sum(tot[x] for x in faixas), saldo, abs_tol=0.01)
    assert _kpi(k, "Acima de 90 dias")["valor"] == rn.moeda(tot["91-180 DIAS"] + tot["+180 DIAS"])
    assert _kpi(k, "Compensar já")["valor"] == rn.moeda(tot["COMPENSAR JÁ"])
    # estado = filial da nota: cada estado = as linhas dele; os estados = a BAP
    por_uf = defaultdict(float)
    for s, _sl, uf in ls:
        por_uf[uf] += s
    rec = f["pl_ncc"]["recortes"]
    assert set(rec) == {u for u in por_uf if u}
    for uf, v in por_uf.items():
        assert _kpi(rec[uf]["kpis"], "Saldo a compensar")["valor"] == rn.moeda(v), uf
    assert math.isclose(sum(por_uf.values()), saldo, abs_tol=0.01)


def test_RN_GER_006_devolucoes_do_mes_batem_nas_abas_nos_estados_e_no_painel_executivo(real):
    """Devoluções do mês = linhas de NOV/26 da aba Devoluções (contagem e
    R$) = soma do "Por motivo" do mês; o estado (FILIAL da nota) soma a BAP;
    as abas de 12 meses somam as 188 linhas; % DEVOLVIDO = VALOR ÷ FATURADO
    12M; e o cartão "Devoluções" do Painel Executivo (o do diretor) é o R$ do
    farol de origem."""
    pcs, f = real
    t = _tab(f, "pl_devolucoes", "Devoluções")
    mes = [(v, uf) for (m, v), uf in zip(_linhas(t, "MÊS", "VALOR"), t["uf_linhas"]) if m == MES]
    k = f["pl_devolucoes"]["kpis"]
    assert _kpi(k, "Devoluções")["valor"] == rn.br(len(mes))
    assert _kpi(k, "Devoluções")["detalhe"] == rn.moeda(sum(v for v, _ in mes))
    pm = [(n, v) for m, n, v in _linhas(_tab(f, "pl_devolucoes", "Por motivo"),
                                         "MÊS", "DEVOLUÇÕES", "VALOR") if m == MES]
    assert sum(n for n, _ in pm) == len(mes)
    assert math.isclose(sum(v for _, v in pm), sum(v for v, _ in mes), abs_tol=0.01)
    # estado = FILIAL da nota
    cont = Counter(uf for _v, uf in mes)
    rec = f["pl_devolucoes"]["recortes"]
    for uf, n in cont.items():
        assert _kpi(rec[uf]["kpis"], "Devoluções")["valor"] == rn.br(n), uf
    assert sum(int(_kpi(r["kpis"], "Devoluções")["valor"].replace(".", "")) for r in rec.values()) == len(mes)
    # 12 meses: as abas de resumo somam a aba Devoluções
    total12 = sum(_col(t, "VALOR"))
    for titulo in ("Por vendedor (12 meses)", "Por cliente (12 meses)"):
        tt = _tab(f, "pl_devolucoes", titulo)
        assert sum(_col(tt, "DEVOLUÇÕES")) == len(t["linhas"]), titulo
        assert math.isclose(sum(_col(tt, "VALOR")), total12, abs_tol=0.05), titulo
    assert math.isclose(sum(_col(_tab(f, "pl_devolucoes", "Por produto (12 meses)"), "VALOR")),
                        total12, abs_tol=0.05)
    for i, (v, fat, pct) in enumerate(_linhas(_tab(f, "pl_devolucoes", "Por vendedor (12 meses)"),
                                              "VALOR", "FATURADO 12M", "% DEVOLVIDO")):
        if fat:
            assert math.isclose(pct, 100 * v / fat, rel_tol=1e-9), i
    # o número do diretor: o cartão "Devoluções" do Painel Executivo (Faturamento)
    painel = rn.montar("vc_painel", RAIZ, hoje=HOJE, params={"ANO": "2026", "MÊS": "11"})
    fat = next(p for p in painel["paineis"] if p["titulo"] == "Faturamento")
    assert _kpi(fat["kpis"], "Devoluções")["valor"] == _kpi(pcs["pl_devolucoes"]["kpis"], "Devoluções")["detalhe"]


def _vnd_dev_por_mes():
    ctx = rn.Contexto(RAIZ, HOJE, None, {"ANO": "2026", "MÊS": "11"})
    vnd, dev = defaultdict(float), defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["tipo"] == "VND":
            vnd[rn.mes_de(it["dt_nf"])] += it["valor"]
        elif it["tipo"] == "DEV":
            dev[rn.mes_de(it["dt_nf"])] += abs(it["valor"])
    return vnd, dev


def test_RN_GER_002_pct_do_faturado(real):
    """Desenho 5.2: "% do faturado" = devolução ÷ faturado líquido (VND −
    DEV) pela data da NF, no cartão, em cada mês do gráfico e no detalhe do
    cartão "Devoluções" do Painel Executivo (o número do diretor). Setembro
    é o mês que separa as contas: 12,0% (líquido) contra 10,7% (bruto)."""
    pcs, _f = real
    vnd, dev = _vnd_dev_por_mes()
    g = next(x for x in pcs["pl_devolucoes"]["graficos"] if x["titulo"] == "Mês a mês: % do faturado")
    meses = rn.ultimos_meses(HOJE, 12)
    esperado = [rn.pct_de(dev[m], vnd[m] - dev[m]) or 0 for m in meses]
    assert [round(v, 6) for v in g["series"][0]["valores"]] == [round(v, 6) for v in esperado]
    set_ = meses.index("2026-09")
    assert round(g["series"][0]["valores"][set_], 1) == 12.0
    assert round(100 * dev["2026-09"] / vnd["2026-09"], 1) == 10.7         # a conta antiga, bruta
    m = rn.mes_de(HOJE)
    assert _kpi(pcs["pl_devolucoes"]["kpis"], "% do faturado")["valor"] == \
        rn.p(rn.pct_de(dev[m], vnd[m] - dev[m]))
    # o cartão do mês de setembro (filtro de período), pelas linhas da aba
    t = next(x for x in pcs["pl_devolucoes"]["tabelas"] if x["titulo"] == "Devoluções")
    nomes = [c["nome"] for c in t["colunas"]]
    i_m, i_v = nomes.index("MÊS"), nomes.index("VALOR")
    v_set = sum(ln[i_v] for ln in t["linhas"] if ln[i_m] == "SET/26")
    assert math.isclose(v_set, dev["2026-09"], abs_tol=0.01)
    assert rn.p(rn.pct_de(v_set, vnd["2026-09"] - dev["2026-09"])) == "12%"
    # Painel Executivo, aba Faturamento: o detalhe usa a mesma regra
    painel = rn.montar("vc_painel", RAIZ, hoje=HOJE, params={"ANO": "2026", "MÊS": "11"})
    fat = next(p for p in painel["paineis"] if p["titulo"] == "Faturamento")
    assert _kpi(fat["kpis"], "Devoluções")["detalhe"] == \
        f"{rn.br(rn.pct_de(dev[m], vnd[m] - dev[m]), 1)}% do faturado"


def _serie_resumo(rel, titulo):
    for b in (rel.get("painel") or {}).get("blocos") or []:
        g = b.get("grafico") or {}
        if g.get("titulo") == titulo:
            return list(g["rotulos"]), list(g["series"][0]["valores"])
    raise AssertionError(titulo)


def _pct_liquido(dev, vnd):
    """RN-GER-002: devolução ÷ (VND − DEV); sem faturado líquido, sem número."""
    liq = vnd - dev
    return dev / liq * 100.0 if liq > 0 else None


def _confere_serie(valores, esperado, nome):
    assert len(valores) == len(esperado), nome
    for i, (v, e) in enumerate(zip(valores, esperado)):
        if e is None:
            # sem faturado líquido: "—" (None) ou o vazio do dia sem evento (0)
            assert v is None or v == "—" or v == 0, (nome, i)
        else:
            assert math.isclose(v, e, abs_tol=0.005), (nome, i)          # o PC grava 2 casas


def _vnd_dev_por_dia(mes):
    ctx = rn.Contexto(RAIZ, HOJE, None, {"ANO": "2026", "MÊS": str(mes)})
    vnd, dev = defaultdict(float), defaultdict(float)
    for it in ctx.tabela["itens"]:
        if not it["dt_nf"]:
            continue
        if it["tipo"] == "VND":
            vnd[it["dt_nf"]] += it["valor"]
        elif it["tipo"] == "DEV":
            dev[it["dt_nf"]] += abs(it["valor"])
    return vnd, dev


def test_RN_GER_002_pct_devolvido_do_faturado_do_resumo(real):
    """O "% devolvido do faturado" do Resumo (dia a dia, semana a semana e
    mês a mês) = soma da devolução ÷ soma de (VND − DEV) de cada período,
    pela data da NF. A semana começa na segunda (a 1ª pega o dia 1)."""
    pcs, _f = real
    vnd, dev = _vnd_dev_por_dia(11)
    dias = [date(2026, 11, d) for d in range(1, 31)]
    rot, val = _serie_resumo(pcs["pl_devolucoes"], "% devolvido do faturado · dia a dia · NOV/26")
    assert rot == [str(d.day) for d in dias]
    _confere_serie(val, [_pct_liquido(dev[d], vnd[d]) if (dev[d] or vnd[d]) else None for d in dias],
                   "dia")
    semanas = []
    for d in dias:
        if not semanas or d.weekday() == 0:
            semanas.append((d.strftime("%d/%m"), []))
        semanas[-1][1].append(d)
    rot, val = _serie_resumo(pcs["pl_devolucoes"], "% devolvido do faturado · semana a semana · NOV/26")
    assert rot == [s for s, _ in semanas]
    _confere_serie(val, [_pct_liquido(sum(dev[d] for d in ds), sum(vnd[d] for d in ds))
                         if any(dev[d] or vnd[d] for d in ds) else None for _s, ds in semanas], "semana")
    vm, dm = _vnd_dev_por_mes()
    rot, val = _serie_resumo(pcs["pl_devolucoes"], "% devolvido do faturado · mês a mês (12 meses)")
    _confere_serie(val, [_pct_liquido(dm[m], vm[m]) for m in rn.ultimos_meses(HOJE, 12)], "mês")
    assert round(val[rot.index("SET")], 1) == 12.0


def test_RN_GER_002_faturado_12m_por_vendedor(real):
    """FATURADO 12M de cada vendedor = VND − DEV dos 12 meses, pela data da
    NF; % DEVOLVIDO = VALOR ÷ FATURADO 12M."""
    _pcs, f = real
    ctx = rn.Contexto(RAIZ, HOJE, None, {"ANO": "2026", "MÊS": "11"})
    meses = set(rn.ultimos_meses(HOJE, 12))
    fat = defaultdict(float)
    for it in ctx.tabela["itens"]:
        if it["tipo"] in ("VND", "DEV") and it["dt_nf"] and rn.mes_de(it["dt_nf"]) in meses:
            fat[ctx.vendedor(it["vend"])] += it["valor"] if it["tipo"] == "VND" else -abs(it["valor"])
    t = _tab(f, "pl_devolucoes", "Por vendedor (12 meses)")
    conferidos = 0
    for i, (vend, v, f12, pct) in enumerate(_linhas(t, "VENDEDOR", "VALOR", "FATURADO 12M", "% DEVOLVIDO")):
        assert math.isclose(f12 or 0.0, fat.get(vend, 0.0), abs_tol=0.01), i
        if f12 and f12 > 0:
            assert math.isclose(pct, 100 * v / f12, rel_tol=1e-9), i
        conferidos += 1
    assert conferidos == len(t["linhas"]) == 21


def test_RN_GER_002_faturado_liquido_zero_ou_negativo_mostra_traco():
    """06/10/2026 (real, bases congeladas): VND R$ 674,00 e DEV R$ 717,88, o
    faturado líquido do dia é negativo. O "% devolvido do faturado" do dia
    mostra "—", nunca um percentual negativo (era -1.636%)."""
    vnd, dev = _vnd_dev_por_dia(10)
    d6 = date(2026, 10, 6)
    assert vnd[d6] - dev[d6] < 0 < dev[d6]
    r = rn.montar("pl_devolucoes", RAIZ, hoje=HOJE, params={"ANO": "2026", "MÊS": "10"})
    rot, val = _serie_resumo(r, "% devolvido do faturado · dia a dia · OUT/26")
    v = val[rot.index("6")]
    assert v is None or v == "—", "06/10 com faturado líquido negativo tem de mostrar —"
    assert all(x is None or x == "—" or x >= 0 for x in val)
    # a semana de 05/10 tem faturado líquido positivo: número normal
    sem = [date(2026, 10, d) for d in range(5, 12)]
    rot_s, val_s = _serie_resumo(r, "% devolvido do faturado · semana a semana · OUT/26")
    esp = _pct_liquido(sum(dev[d] for d in sem), sum(vnd[d] for d in sem))
    assert esp is not None and math.isclose(val_s[rot_s.index("05/10")], esp, abs_tol=0.005)


def test_RN_GER_002_devolucao_do_mes_pela_data_da_nf(real):
    """O R$ devolvido do mês é o DEV pela data da NF (o mesmo do gráfico)."""
    pcs, _f = real
    _vnd, dev = _vnd_dev_por_mes()
    assert _kpi(pcs["pl_devolucoes"]["kpis"], "Devoluções")["detalhe"] == rn.moeda(dev[rn.mes_de(HOJE)])


def test_RN_GER_014_garantias_abas_de_resumo_batem_com_as_linhas(real):
    _pcs, f = real
    g = _tab(f, "pl_garantias", "Garantias")
    st = Counter(_col(g, "STATUS"))
    res = Counter(_col(g, "RESULTADO ANÁLISE"))
    sr = _tab(f, "pl_garantias", "Status x resultado")
    assert {s: tot for s, tot in _linhas(sr, "STATUS", "TOTAL")} == dict(st)
    for r_ in ("PENDENTE", "PROCEDENTE", "IMPROCEDENTE"):
        assert sum(_col(sr, r_)) == res.get(r_, 0), r_
    k = f["pl_garantias"]["kpis"]
    assert _kpi(k, "Análise pendente")["valor"] == rn.br(res.get("PENDENTE", 0))
    assert _kpi(k, "Procedentes")["valor"] == rn.br(res.get("PROCEDENTE", 0))
    assert _kpi(k, "Improcedentes")["valor"] == rn.br(res.get("IMPROCEDENTE", 0))
    pp = _tab(f, "pl_garantias", "Por produto")
    assert sum(_col(pp, "GARANTIAS")) == len(g["linhas"])
    abertas = sum(n for s, n in st.items() if s not in gm.FECHADOS)
    assert sum(_col(pp, "EM ABERTO")) == abertas
    h = _tab(f, "pl_garantias", "Histórico de compra")
    kh = h["kpis_padrao"]
    assert _kpi(kh, "Itens")["valor"] == rn.br(len(h["linhas"]))
    # o número do pedido e o da nota são por filial: (FILIAL, PEDIDO) e (FILIAL, NF)
    peds = {(fl, pd) for fl, pd in _linhas(h, "FILIAL", "PEDIDO") if pd}
    nfs = {(fl, nf) for fl, nf in _linhas(h, "FILIAL", "NF") if nf}
    assert _kpi(kh, "Pedidos")["valor"] == rn.br(len(peds))
    assert _kpi(kh, "Pedidos")["detalhe"] == f"{rn.br(len(nfs))} notas"
    nomes = [c["nome"] for c in h["colunas"]]
    assert math.isclose(h["total"][nomes.index("VALOR")], sum(_col(h, "VALOR")), abs_tol=0.05)
    assert _kpi(kh, "Valor comprado")["valor"] == rn.moeda(sum(_col(h, "VALOR")))


def test_RN_GER_006_garantias_e_por_cliente_do_ncc_sem_estado_com_aviso(real):
    _pcs, f = real
    assert not f["pl_garantias"]["recortes"]
    assert "Sem filtro por estado: os cartões mostram a BAP inteira." in f["pl_garantias"]["avisos"]
    assert "uf_linhas" not in _tab(f, "pl_ncc", "Por cliente")
    for rid, titulo in (("pl_devolucoes", "Devoluções"), ("pl_ncc", "NCC pendentes")):
        t = _tab(f, rid, titulo)
        assert t["uf_linhas"] == [ba._uf_valida_web(rn.uf_do_nome_da_filial(x)) for x in _col(t, "FILIAL")]


# ------------------------------------------------------------------ 5.3 dado pessoal
def _strings(o, caminho=""):
    """(caminho, texto) de toda string do JSON (chaves e valores)."""
    if isinstance(o, str):
        yield caminho, o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield f"{caminho}.{k}", str(k)
            yield from _strings(v, f"{caminho}.{k}")
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o):
            yield from _strings(v, f"{caminho}[{i}]")


def _numeros(o):
    if isinstance(o, bool):
        return
    if isinstance(o, (int, float)):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _numeros(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _numeros(v)


def test_RN_GER_011_padroes_pessoais_do_contrato_sao_os_do_nucleo():
    """O bloco `padroes-pessoais` (10.9.1) é a fonte única: o núcleo usa os
    mesmos padrões no texto_sem_contato."""
    assert rn._EMAIL.pattern == PADROES["EMAIL"]
    assert rn._DOC_MEIO.pattern == PADROES["DOC_MEIO"]
    assert rn._DOC_SOLTO.pattern == PADROES["DOC_SOLTO"]
    assert rn._FONE.pattern == PADROES["FONE"]
    assert rn._VALOR_RS.pattern == PADROES["VALOR_RS"]


def test_RN_GER_011_json_dos_3_farois_sem_cpf_cnpj_email_nem_telefone(real):
    """No JSON de cada farol:
    - nenhum CPF/CNPJ formatado e nenhum e-mail no texto inteiro;
    - em TODA string (célula, total, cartão, aviso, rótulo, chave): nem
      e-mail, nem documento (DOC_MEIO, DOC_SOLTO). A única exceção é o código
      de produto puro (só dígitos) nas colunas CÓD. PRODUTO e PRODUTO;
    - nos números: inteiro de 11 ou 14 dígitos (CPF/CNPJ sem máscara) reprova
      fora das colunas de código. O float com casas (97.35000000000001) é
      número, não documento: ele não passa por padrão de texto.
    O telefone (FONE) é conferido nas colunas de texto livre e de nome do
    cliente, onde a limpeza do 10.10.3 roda (em data ISO e em valor o FONE
    casaria por engano)."""
    _pcs, f = real
    livres = set(ba._COLUNAS_TEXTO_LIVRE_WEB)
    for rid in TRES:
        farol = f[rid]
        txt = ba._json_farol_web(farol).decode("utf-8")
        assert not RE_DOC_FORMATADO.search(txt), rid
        assert not PESSOAL["EMAIL"].search(txt), rid
        codigo = []                         # (tabela, coluna) das células de código
        for t in farol.get("tabelas") or []:
            nomes = [c["nome"] for c in t["colunas"]]
            limpas = set(ba._COLUNAS_LIMPAS_WEB.get((rid, t["titulo"]), {}))
            linhas = list(t["linhas"]) + ([t["total"]] if t.get("total") else [])
            for ln in linhas:
                for nome, v in zip(nomes, ln):
                    if nome in COLUNAS_CODIGO_PRODUTO:
                        if isinstance(v, str) and v:
                            assert v.isdigit() or not (PESSOAL["DOC_MEIO"].search(v)
                                                       or PESSOAL["DOC_SOLTO"].search(v)), \
                                (rid, t["titulo"], nome)
                        codigo.append((t["titulo"], nome))
                        continue
                    if isinstance(v, str):
                        for k in ("EMAIL", "DOC_MEIO", "DOC_SOLTO"):
                            assert not PESSOAL[k].search(v), (rid, t["titulo"], nome, k)
                        if nome in livres or nome in limpas:
                            assert not PESSOAL["FONE"].search(v), (rid, t["titulo"], nome, "FONE")
                    elif isinstance(v, (int, float)) and not isinstance(v, bool):
                        if float(v).is_integer():
                            assert len(str(abs(int(v)))) not in (11, 14), (rid, t["titulo"], nome)
        # o resto do farol (cartões, avisos, painel, edição, recortes)
        resto = {k: v for k, v in farol.items() if k != "tabelas"}
        resto["_tabelas"] = [{k: v for k, v in t.items() if k not in ("linhas", "total")}
                             for t in farol.get("tabelas") or []]
        for caminho, s in _strings(resto):
            for k in ("EMAIL", "DOC_MEIO", "DOC_SOLTO"):
                assert not PESSOAL[k].search(s), (rid, caminho, k)
        for v in _numeros(resto):
            if float(v).is_integer():
                assert len(str(abs(int(v)))) not in (11, 14), rid


def test_RN_GER_011_sem_cnpj_interno_nem_conta_000040_nos_clientes(real):
    """CNPJs internos (BAP AUTOPARTS / FRW / PMZ DISTRIBUIDORA) e a conta
    000040 não aparecem como cliente nos 3 faróis."""
    _pcs, f = real
    internos = ("BAP AUTOPARTS", "FRW", "PMZ DISTRIBUIDORA")
    for rid in TRES:
        for t in f[rid]["tabelas"]:
            for nome in [c["nome"] for c in t["colunas"]]:
                if not any(x in nome for x in ("CLIENTE", "NOME", "RAZÃO", "FANTASIA")) \
                        or nome in ("CLIENTES",):
                    continue
                for v in _col(t, nome):
                    s = str(v or "").upper()
                    assert not s.lstrip().startswith("000040"), (rid, t["titulo"], nome)
                    assert not any(x in s for x in internos), (rid, t["titulo"], nome)


@pytest.mark.parametrize("texto,ok", [
    ("retorno no 92999998888", False),          # 11 dígitos: celular com DDD
    ("retorno no 9233334444", False),           # 10: fixo com DDD
    ("retorno no 33334444", False),             # 8: fixo sem DDD
    ("R$ 12345678", True),                      # valor em R$ (VALOR_RS) não é telefone
])
def test_RN_GER_011_telefone_sem_mascara_e_recusado_no_robo(texto, ok):
    """Desenho 5.3: o robô recusa o texto com telefone nos 3 tamanhos do
    FONE, com a frase do 10.9.1; o valor em R$ passa."""
    reg = {"tipo": "edicao", "seq": 1, "id": "id-1", "usuario": "admin.ficticio", "rid": "pl_garantias",
           "tabela": "Garantias", "modulo": "garantias", "chave": "G-9001",
           "valores": {"observacao": texto}, "antes": {}, "status": "pendente"}
    assert (rn.texto_sem_contato(texto) == texto) is ok
    assert ba.validar_edicao_web(reg, {"_hoje": HOJE}) == ("" if ok else ba.motivo_texto_web(600))


# ------------------------------------------------------------------ 5.5 a linha nova na mesma rodada
class _SiteFalso:
    def __init__(self, linhas):
        self.linhas, self.confirmados = linhas, []

    def get(self, url, params=None, headers=None, timeout=None):
        ls = [x for x in self.linhas if x["seq"] > params["desde"]]
        return SimpleNamespace(status_code=200, json=lambda: {
            "epoca": "ep-1", "linhas": ls, "ate_seq": ls[-1]["seq"] if ls else params["desde"], "mais": False})

    def post(self, url, json=None, headers=None, timeout=None):
        self.confirmados.append(json)
        return SimpleNamespace(status_code=200)


def test_RN_GER_012_duas_garantias_novas_com_o_mesmo_padrao_ficam_com_13_e_14(tmp_path):
    """Desenho 5.5: com 12 garantias (fictícias), o padrão do formulário é
    G-0013; duas linhas novas da mesma rodada, as duas com G-0013, ficam com
    G-0013 e G-0014. O diário só ganha linhas."""
    for i in range(1, 13):
        gm.gravar(tmp_path, f"G-{i:04d}", {"status": "ABERTO", "cod_cliente": "900001"})
    assert gm.novo_ticket(tmp_path) == "G-0013"
    arq = next((tmp_path / gm.PASTA).glob("GARANTIAS_*.csv"))
    antes = arq.read_bytes()

    def nova(seq, chave):
        return {"tipo": "edicao", "seq": seq, "id": f"id-{seq}", "usuario": "admin.ficticio",
                "rid": "pl_garantias", "tabela": "Garantias", "modulo": "garantias", "chave": chave,
                "novo": True, "antes": {"ticket": "G-0013"}, "status": "pendente",
                "valores": {"ticket": "G-0013", "observacao": f"peça fictícia {seq}"}}
    opc = {"garantias.status": set(gm.STATUS), "garantias.resultado": set(gm.RESULTADOS), "_hoje": HOJE}
    site = _SiteFalso([nova(1, "NOVO-0000000A"), nova(2, "NOVO-0000000B")])
    r = ba.sincronizar_edicoes_web(tmp_path, "https://web.exemplo.test", "token-ficticio", site,
                                   lambda m: None, opcoes=opc)
    assert r["aplicadas"] == 2 and r["erros"] == 0
    d = gm.ler(tmp_path)
    assert d["G-0013"]["observacao"] == "peça fictícia 1"
    assert d["G-0014"]["observacao"] == "peça fictícia 2"
    assert len(d) == 14
    assert arq.read_bytes().startswith(antes)                               # só acrescenta (regra 7)
