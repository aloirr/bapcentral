"""T-0053: RN-GER-019 — dados do cliente no pedido pela loja da filial.

A aba de pedidos (ftPedidos) traz so o codigo do cliente, sem a loja. No
pedido, nome, UF, cidade, limite e saldo vem da loja do codigo cuja UF e a da
filial do pedido; codigo com uma loja so usa essa loja. Sem loja unica na UF
da filial, o pedido nao herda dados de outra loja (UF da filial, sem cidade,
limite nem saldo; nome so se for igual; "Saldo Não Apurado", que entra em
"Credito a analisar"). Os cartoes e o filtro por estado nao mudam.

Sem pular condicional: relatorios_nucleo tem de importar e ter
`cadastro_do_pedido` (funcao e metodo do Contexto); se faltar, os testes
FALHAM (regressao), nao pulam. A chave "identificada" do retorno de
`cadastro_do_pedido()` e parte da RN-GER-019 (loja unica na UF da filial ou
loja unica do codigo = True; senao False).

Dados ficticios: codigos 900001+ e "CLIENTE FICTICIO".
"""
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo

HOJE = date(2026, 11, 27)
RR, AM = "0101004", "0101002"          # filiais: Boa Vista (RR), Manaus (AM)


# ---------------------------------------------------------------- modulo
@pytest.fixture(scope="module")
def rn():
    """relatorios_nucleo com cadastro_do_pedido (funcao e metodo)."""
    m = relatorios_nucleo
    assert hasattr(m, "cadastro_do_pedido"), \
        "RN-GER-019: falta relatorios_nucleo.cadastro_do_pedido"
    assert hasattr(m.Contexto, "cadastro_do_pedido"), \
        "RN-GER-019: falta Contexto.cadastro_do_pedido"
    return m


# ---------------------------------------------------------------- fixture
def _item(fil, ped, cli, valor, dias=1, tipo="VEA", nf="", dt_nf=None,
          qtd=10):
    return {"tipo": tipo, "filial": fil, "cliente": cli,
            "razao": "CLIENTE FICTICIO", "vend": "000001", "pedido": ped,
            "nf": nf, "serie": "1" if nf else "",
            "dt_pedido": date(2026, 11, 27 - dias), "dt_nf": dt_nf,
            "hora": "10:00", "cond": "001", "cod": "PROD1", "qtd": qtd,
            "qtd_at": qtd, "pct_at": 100.0, "valor": valor,
            "p_tab": valor / qtd * 1.1, "p_venda": valor / qtd, "desc": 0.0,
            "est_disp": 50.0, "est_prod": 50.0, "dem_ant": 0.0, "acres": 0.0,
            "maxima": "", "status": "", "obs": ""}


def _loja(nome, uf, cidade, limite, fantasia=""):
    return {"vend": "000001", "nome": nome, "fantasia": fantasia,
            "cidade": cidade, "uf": uf, "status": "ATIVO", "filial": "",
            "cond": "001", "limite": limite}


def _guarda(lj, loja, saldo, atraso=0.0):
    """O cadastro por codigo (tabela['clientes']): uma loja so, a de maior
    limite, com o saldo e o atraso dela."""
    return dict(nome=lj["nome"], fantasia=lj["fantasia"], cidade=lj["cidade"],
                uf=lj["uf"], limite=lj["limite"], saldo=saldo, aberto=0.0,
                atraso_valor=atraso, dias_atraso=0.0, loja=loja)


class _Vazio(dict):
    def __missing__(self, k):
        return {}


LOJAS = {
    # 900001: lojas RR e AM; o cadastro guarda a de AM (maior limite)
    ("900001", "01"): _loja("CLIENTE FICTICIO LOJA RR", "RR", "BOA VISTA",
                            20000.0, "FICTICIO RR"),
    ("900001", "02"): _loja("CLIENTE FICTICIO LOJA AM", "AM", "MANAUS",
                            80000.0, "FICTICIO AM"),
    # 900002: uma loja so, em AM
    ("900002", "01"): _loja("CLIENTE FICTICIO UNICO AM", "AM", "MANAUS",
                            5000.0, "FICTICIO UNICO"),
    # 900003: duas lojas em AM com nomes diferentes
    ("900003", "01"): _loja("CLIENTE FICTICIO A", "AM", "MANAUS", 9000.0),
    ("900003", "02"): _loja("CLIENTE FICTICIO B", "AM", "ITACOATIARA",
                            3000.0),
    # 900005: duas lojas em AM com o mesmo nome
    ("900005", "01"): _loja("CLIENTE FICTICIO IGUAL", "AM", "MANAUS",
                            7000.0),
    ("900005", "02"): _loja("CLIENTE FICTICIO IGUAL", "AM", "PARINTINS",
                            2000.0),
}
CLIENTES = {
    "900001": _guarda(LOJAS[("900001", "02")], "02", 60000.0),
    "900002": _guarda(LOJAS[("900002", "01")], "01", 4000.0),
    "900003": _guarda(LOJAS[("900003", "01")], "01", 8000.0),
    "900005": _guarda(LOJAS[("900005", "01")], "01", 6000.0),
    # 900007: so no cadastro por codigo (sem protheus_lojas)
    "900007": dict(_guarda(_loja("CLIENTE FICTICIO SO CADASTRO", "AM",
                                 "MANAUS", 3000.0), "01", 2500.0)),
}
# pedido -> (filial, codigo, valor)
PEDIDOS = {
    "000001": (RR, "900001", 1500.0),     # loja RR, sem saldo conhecido
    "000002": (AM, "900001", 52000.0),    # loja AM, saldo 60000 cobre
    "000003": (AM, "900001", 70000.0),    # loja AM, saldo 60000 nao cobre
    "000004": (RR, "900002", 900.0),      # loja unica (AM) herdada
    "000005": (AM, "900003", 700.0),      # 2 lojas AM, nomes diferentes
    "000006": (AM, "900005", 650.0),      # 2 lojas AM, nome igual
    "000007": (RR, "900003", 400.0),      # sem loja RR; 2 AM nomes dif.
    "000008": (RR, "900005", 300.0),      # sem loja RR; 2 AM nome igual
    "000009": (RR, "900004", 200.0),      # sem cadastro
    "000010": (RR, "900007", 100.0),      # so no cadastro por codigo (AM)
}


def _itens():
    its = [_item(f, p, c, v, dias=1 + n % 3)
           for n, (p, (f, c, v)) in enumerate(PEDIDOS.items())]
    # faturados do mes (os cartoes saem do caminho geral, nao so do BI)
    its.append(_item(RR, "000101", "900001", 1200.0, dias=6, tipo="VND",
                     nf="000501", dt_nf=date(2026, 11, 24)))
    its.append(_item(AM, "000102", "900001", 3400.0, dias=6, tipo="VND",
                     nf="000502", dt_nf=date(2026, 11, 24)))
    return its


# ---- extra das notas com frete (fora das capitais) e dos excluidos
LOJAS_FRETE = {
    # 900008: loja RR e loja AM, as duas fora da capital; o cadastro por
    # codigo guarda a de AM (maior limite)
    ("900008", "01"): _loja("CLIENTE FICTICIO FRETE RR", "RR", "CARACARAI",
                            1000.0),
    ("900008", "02"): _loja("CLIENTE FICTICIO FRETE AM", "AM", "PARINTINS",
                            9000.0),
    # 900009: duas lojas em AM (nomes diferentes), fora da capital
    ("900009", "01"): _loja("CLIENTE FICTICIO X", "AM", "ITACOATIARA",
                            8000.0),
    ("900009", "02"): _loja("CLIENTE FICTICIO Y", "AM", "MANACAPURU",
                            2000.0),
}
CLIENTES_FRETE = {
    "900008": _guarda(LOJAS_FRETE[("900008", "02")], "02", 7000.0),
    "900009": _guarda(LOJAS_FRETE[("900009", "01")], "01", 6000.0),
}
# nota -> (filial, codigo, valor); as 0006xx em NOV/26, as 0007xx em SET/26
# (antes do acompanhamento do pos-venda: entram nas Entregas como CONCLUIDA)
NOTAS_FRETE = {"000601": (RR, "900008", 1000.0),   # loja RR existe
               "000602": (AM, "900008", 2000.0),
               "000603": (AM, "900009", 3000.0),   # loja nao identificada
               "000604": (RR, "900009", 4000.0),   # sem loja RR
               "000701": (RR, "900008", 500.0),
               "000702": (AM, "900008", 600.0),
               "000703": (AM, "900009", 700.0),
               "000704": (RR, "900009", 800.0)}


def _itens_frete():
    its = []
    for n, (nf, (f, c, v)) in enumerate(NOTAS_FRETE.items()):
        d = date(2026, 11, 20) if nf.startswith("0006") else \
            date(2026, 9, 15)
        it = _item(f, f"0008{n:02d}", c, v, tipo="VND", nf=nf, dt_nf=d)
        it["dt_pedido"] = d
        its.append(it)
    return its


def _itens_excluidos():
    """EXC do mes: 900001 nas duas filiais (um cliente so) e 900003."""
    return [_item(RR, "000901", "900001", 100.0, tipo="EXC"),
            _item(AM, "000902", "900001", 200.0, tipo="EXC"),
            _item(AM, "000903", "900003", 300.0, tipo="EXC")]


def _ctx(rn, tmp_path, antes=False, extra=(), mes="11"):
    """extra: "frete" (LOJAS_FRETE + NOTAS_FRETE) e/ou "exc" (excluidos)."""
    ctx = rn.Contexto(Path(tmp_path), hoje=HOJE,
                      params={"ANO": "2026", "MÊS": mes})
    itens, lojas, clientes = _itens(), dict(LOJAS), dict(CLIENTES)
    if "frete" in extra:
        itens += _itens_frete()
        lojas.update(LOJAS_FRETE)
        clientes.update(CLIENTES_FRETE)
    if "exc" in extra:
        itens += _itens_excluidos()
    ctx._b["tabela"] = _Vazio({  # noqa: SLF001
        "itens": itens, "clientes": {k: dict(v) for k, v in
                                     clientes.items()},
        "protheus_lojas": {k: dict(v) for k, v in lojas.items()},
        "condpag": {"001": "A VISTA"}, "condpag_fin": {}, "autorizacoes": [],
        "filiais": {RR: "BOA VISTA", AM: "MANAUS"}})
    ctx._b["base"] = {"clientes": [], "pessoas": {}}  # noqa: SLF001
    ctx._b["posvenda"] = {"existe": True, "devolucoes": [],  # noqa: SLF001
                          "entregas": []}
    if antes:
        # o comportamento de antes da RN-GER-019: o cadastro por codigo.
        # A ficha de credito tem o mesmo formato da nova (so limite, saldo,
        # atraso_valor e credito_apurado); antes o credito era sempre
        # apurado quando havia cadastro.
        ctx.cliente_do_pedido = lambda fil, cod: ctx.cliente(cod)

        def _credito_antes(fil, cod):
            r = ctx.tabela["clientes"].get(cod)
            if not r:
                return {}
            return {"limite": r["limite"], "saldo": r["saldo"],
                    "atraso_valor": r["atraso_valor"],
                    "credito_apurado": True}
        ctx.credito_do_pedido = _credito_antes
    return ctx


def _pedidos(rn, ctx):
    rel = rn.farol_pedidos(ctx)
    t = next(x for x in rel["tabelas"] if x["titulo"] == "Pedidos")
    nomes = [c["nome"] for c in t["colunas"]]
    por_ped = {}
    for ln in t["linhas"]:
        d = dict(zip(nomes, ln))
        if d["SITUAÇÃO"] == "EM ABERTO":
            por_ped[d["PEDIDO"]] = d
    return rel, t, nomes, por_ped


# ---------------------------------------------------------------- 1
def test_RN_GER_019_pedido_da_filial_RR_usa_a_loja_RR(rn, tmp_path):
    """RN-GER-019: pedido de cada filial usa a loja daquela UF
    ("identificada")."""
    ctx = _ctx(rn, tmp_path)
    c = ctx.cadastro_do_pedido(RR, "900001")
    assert (c["uf"], c["cidade"], c["limite"]) == ("RR", "BOA VISTA",
                                                   20000.0)
    assert c["nome"] == "CLIENTE FICTICIO LOJA RR" and c["identificada"]
    c = ctx.cadastro_do_pedido(AM, "900001")
    assert (c["uf"], c["cidade"], c["limite"], c["saldo"]) == (
        "AM", "MANAUS", 80000.0, 60000.0)
    assert c["credito_apurado"] is True
    _r, _t, _n, ped = _pedidos(rn, ctx)
    rr, am = ped["000001"], ped["000002"]
    assert (rr["UF"], rr["CIDADE"], rr["LIMITE"], rr["FILIAL"]) == (
        "RR", "BOA VISTA", 20000.0, "BOA VISTA")
    assert rr["RAZÃO SOCIAL"] == "CLIENTE FICTICIO LOJA RR"
    assert rr["FANTASIA"] == "FICTICIO RR"
    assert (am["UF"], am["CIDADE"], am["LIMITE"], am["DISP."]) == (
        "AM", "MANAUS", 80000.0, 60000.0)
    assert am["RAZÃO SOCIAL"] == "CLIENTE FICTICIO LOJA AM"
    # o nome do pedido (detalhe, faltas, excluidos) e o da loja
    assert ctx.nome_cliente("900001", RR) == "900001 - FICTICIO RR"
    assert ctx.nome_cliente("900001", AM) == "900001 - FICTICIO AM"
    assert ctx.nome_cliente("900001") == "900001 - FICTICIO AM"   # sem filial


def test_RN_GER_019_saldo_da_loja_certa_decide_a_analise(rn, tmp_path):
    """valor x regra: AM com saldo 60000 cobre 52000 (Com Limite) e nao cobre
    70000 (Com Limite Parcial)."""
    _r, _t, _n, ped = _pedidos(rn, _ctx(rn, tmp_path))
    assert ped["000002"]["ANÁLISE CRÉDITO"] == rn.CREDITO_OK
    assert ped["000003"]["ANÁLISE CRÉDITO"] == rn.CREDITO_PARCIAL


# ---------------------------------------------------------------- 2
def test_RN_GER_019_loja_certa_sem_saldo_conhecido_credito_nao_apurado(
        rn, tmp_path):
    """RN-GER-019: loja certa ("identificada") sem saldo conhecido = credito
    nao apurado, sem o saldo de outra loja."""
    ctx = _ctx(rn, tmp_path)
    cr = ctx.credito_do_pedido(RR, "900001")
    # a ficha de credito do pedido: so credito, sem nome nem fantasia
    assert set(cr) == {"limite", "saldo", "atraso_valor", "credito_apurado"}
    assert cr["limite"] == 20000.0 and cr["saldo"] is None
    assert cr["atraso_valor"] is None and cr["credito_apurado"] is False
    # o rotulo diz o que falta: o saldo da loja nao foi apurado
    assert rn.CREDITO_NAO_APURADO.lower().endswith("não apurado")
    _r, _t, _n, ped = _pedidos(rn, ctx)
    p = ped["000001"]
    assert p["ANÁLISE CRÉDITO"] == rn.CREDITO_NAO_APURADO
    # nao herda o saldo (60000) nem o atraso da loja AM
    assert p["DISP."] is None and p["ATRASO"] is None
    # a funcao pura: a loja certa com saldo None
    c = rn.cadastro_do_pedido(RR, [
        {"uf": "RR", "nome": "CLIENTE FICTICIO", "limite": 1.0,
         "saldo": None},
        {"uf": "AM", "nome": "CLIENTE FICTICIO", "limite": 9.0,
         "saldo": 9.0}])
    assert c["identificada"] is True and c["credito_apurado"] is False
    assert rn.analise_credito({"credito_apurado": False, "limite": 1e9,
                               "saldo": 1e9}, 1.0) == rn.CREDITO_NAO_APURADO


# ---------------------------------------------------------------- 3
def test_RN_GER_019_sem_loja_na_UF_da_filial_nao_herda_outra(rn, tmp_path):
    """RN-GER-019: sem loja na UF da filial e com mais de uma loja, nada
    de cidade, limite ou saldo de outra loja."""
    ctx = _ctx(rn, tmp_path)
    for cod, nome in (("900003", rn.LOJA_NAO_IDENTIFICADA),
                      ("900005", "CLIENTE FICTICIO IGUAL")):
        c = ctx.cadastro_do_pedido(RR, cod)
        assert c["uf"] == "RR"                    # a UF da filial
        assert (c["cidade"], c["limite"], c["saldo"]) == ("", None, None)
        assert c["atraso_valor"] is None
        assert c["identificada"] is False and c["credito_apurado"] is False
        assert c["nome"] == nome
    _r, _t, _n, ped = _pedidos(rn, ctx)
    for p, nome in (("000007", rn.LOJA_NAO_IDENTIFICADA),
                    ("000008", "CLIENTE FICTICIO IGUAL")):
        d = ped[p]
        assert (d["UF"], d["CIDADE"], d["LIMITE"], d["DISP."],
                d["ATRASO"]) == ("RR", "", None, None, None)
        assert d["ANÁLISE CRÉDITO"] == rn.CREDITO_NAO_APURADO
        assert d["RAZÃO SOCIAL"] == nome


# ---------------------------------------------------------------- 4
def test_RN_GER_019_duas_lojas_na_mesma_UF(rn, tmp_path):
    """RN-GER-019: duas lojas na UF da filial; nome so se for igual (sem
    acento e caixa)."""
    ctx = _ctx(rn, tmp_path)
    dif = ctx.cadastro_do_pedido(AM, "900003")
    igual = ctx.cadastro_do_pedido(AM, "900005")
    assert dif["nome"] == rn.LOJA_NAO_IDENTIFICADA
    assert igual["nome"] == "CLIENTE FICTICIO IGUAL"
    for c in (dif, igual):
        assert (c["uf"], c["cidade"], c["limite"], c["saldo"]) == (
            "AM", "", None, None)
        assert c["credito_apurado"] is False
    # nome igual sem distinguir acento e caixa
    c = rn.cadastro_do_pedido(AM, [
        {"uf": "AM", "nome": "Cliente Fictício"},
        {"uf": "am", "nome": "CLIENTE FICTICIO"}])
    assert c["nome"] == "Cliente Fictício" and not c["identificada"]
    _r, _t, _n, ped = _pedidos(rn, ctx)
    assert ped["000005"]["RAZÃO SOCIAL"] == rn.LOJA_NAO_IDENTIFICADA
    assert ped["000006"]["RAZÃO SOCIAL"] == "CLIENTE FICTICIO IGUAL"
    for p in ("000005", "000006"):
        assert ped[p]["ANÁLISE CRÉDITO"] == rn.CREDITO_NAO_APURADO
        assert (ped[p]["UF"], ped[p]["CIDADE"], ped[p]["LIMITE"]) == (
            "AM", "", None)


def test_RN_GER_019_sem_loja_identificada_fantasia_igual_ao_nome(
        rn, tmp_path):
    """RN-GER-019: sem loja "identificada", a fantasia e o proprio nome
    (o igual ou LOJA_NAO_IDENTIFICADA), nunca a de outra loja."""
    ctx = _ctx(rn, tmp_path)
    for fil, cod in ((AM, "900003"), (AM, "900005"), (RR, "900003"),
                     (RR, "900005")):
        c = ctx.cadastro_do_pedido(fil, cod)
        assert c["identificada"] is False
        assert c["fantasia"] == c["nome"]
        assert ctx.cliente_do_pedido(fil, cod)["fantasia"] == c["nome"]
    assert ctx.nome_cliente("900003", RR) == \
        f"900003 - {rn.LOJA_NAO_IDENTIFICADA}"
    assert ctx.nome_cliente("900005", AM) == "900005 - CLIENTE FICTICIO IGUAL"
    # identificada: a fantasia e a da loja
    assert ctx.cadastro_do_pedido(RR, "900001")["fantasia"] == "FICTICIO RR"
    _r, _t, _n, ped = _pedidos(rn, ctx)
    for p in ("000005", "000006", "000007", "000008"):
        assert ped[p]["FANTASIA"] == ped[p]["RAZÃO SOCIAL"]


def test_RN_GER_019_pedidos_em_aberto_marca_credito_nao_apurado(
        rn, tmp_path):
    """A tela Pedidos em aberto usa o mesmo rotulo, em maiusculas."""
    r = rn.pedidos_em_aberto(_ctx(rn, tmp_path))
    t = next(x for x in r["tabelas"] if x["titulo"] == "Pedidos em aberto")
    nomes = [c["nome"] for c in t["colunas"]]
    cred = {ln[nomes.index("PEDIDO")]: ln[nomes.index("CRÉDITO")]
            for ln in t["linhas"]}
    rotulo = rn.CREDITO_NAO_APURADO.upper()
    assert {p for p, c in cred.items() if c == rotulo} == {
        "000001", "000005", "000006", "000007", "000008"}
    uf = {ln[nomes.index("PEDIDO")]: (ln[nomes.index("UF")],
                                      ln[nomes.index("LIMITE DISP.")])
          for ln in t["linhas"]}
    assert uf["000001"] == ("RR", None)        # sem o saldo da loja AM
    assert uf["000002"] == ("AM", 60000.0)
    assert uf["000007"] == ("RR", None)


# ---------------------------------------------------------------- 5
def test_RN_GER_019_loja_unica_herda_e_sem_cadastro_segue_como_antes(
        rn, tmp_path):
    """RN-GER-019: loja unica do codigo herda; sem cadastro, o caminho de
    antes."""
    ctx = _ctx(rn, tmp_path)
    c = ctx.cadastro_do_pedido(RR, "900002")
    assert (c["uf"], c["cidade"], c["limite"], c["saldo"]) == (
        "AM", "MANAUS", 5000.0, 4000.0)
    assert c["identificada"] and c["credito_apurado"]
    # so no cadastro por codigo (sem protheus_lojas): a loja dele
    c = ctx.cadastro_do_pedido(RR, "900007")
    assert (c["uf"], c["limite"], c["saldo"]) == ("AM", 3000.0, 2500.0)
    # sem cadastro: {} (o pedido segue o caminho de antes)
    assert ctx.cadastro_do_pedido(RR, "900004") == {}
    assert ctx.credito_do_pedido(RR, "900004") == {}
    _r, _t, _n, ped = _pedidos(rn, ctx)
    assert (ped["000004"]["UF"], ped["000004"]["LIMITE"],
            ped["000004"]["ANÁLISE CRÉDITO"]) == ("AM", 5000.0, rn.CREDITO_OK)
    _r, _t, _n, antes = _pedidos(rn, _ctx(rn, tmp_path / "antes", antes=True))
    assert ped["000009"] == antes["000009"]
    assert ped["000009"]["ANÁLISE CRÉDITO"] == "Sem Limite"
    assert ped["000009"]["UF"] == ""
    assert ped["000009"]["RAZÃO SOCIAL"] == "CLIENTE FICTICIO"


def test_RN_GER_019_loja_unica_de_outra_UF_herda_sempre(rn):
    """RN-GER-019: codigo com uma loja so, em qualquer UF, usa essa
    loja."""
    lojas = [{"uf": "AM", "nome": "CLIENTE FICTICIO", "fantasia": "",
              "cidade": "MANAUS", "limite": 5000.0, "saldo": 4000.0,
              "atraso_valor": 0.0}]
    for fil in (RR, AM, "0101005"):
        c = rn.cadastro_do_pedido(fil, lojas)
        assert (c["uf"], c["cidade"], c["limite"], c["saldo"]) == (
            "AM", "MANAUS", 5000.0, 4000.0)
        assert c["identificada"] is True and c["credito_apurado"] is True


# ---------------------------------------------------------------- 6
def test_RN_GER_019_cartoes_e_filtro_por_estado_nao_mudam(rn, tmp_path):
    rel, t, nomes, ped = _pedidos(rn, _ctx(rn, tmp_path))
    rel_a, t_a, _n, ped_a = _pedidos(rn, _ctx(rn, tmp_path / "a", antes=True))
    assert rel["kpis"] == rel_a["kpis"]
    # valor x regra dos cartoes: 10 em aberto + 2 notas; R$ = soma das linhas
    k = {x["rotulo"]: x for x in rel["kpis"]}
    total = sum(v for _f, _c, v in PEDIDOS.values()) + 1200.0 + 3400.0
    assert (k["Pedidos"]["valor"], k["Pedidos"]["detalhe"]) == (
        "12", rn.moeda(total))
    assert k["Faturado"]["valor"] == rn.moeda(4600.0)
    assert k["Em aberto"]["valor"] == "10"
    assert len(t["linhas"]) == len(t_a["linhas"])
    i_f, i_v = nomes.index("FILIAL"), nomes.index("R$ VENDA")

    def por_filial(ls):
        r = {}
        for ln in ls:
            n, v = r.get(ln[i_f], (0, 0.0))
            r[ln[i_f]] = (n + 1, round(v + ln[i_v], 2))
        return r
    assert por_filial(t["linhas"]) == por_filial(t_a["linhas"])
    # valor x regra: estado = filial do pedido (nao a UF da loja)
    esp = {}
    for f, _c, v in PEDIDOS.values():
        n, s = esp.get(f, (0, 0.0))
        esp[f] = (n + 1, s + v)
    nome_f = {RR: "BOA VISTA", AM: "MANAUS"}
    abertos = [ln for ln in t["linhas"]
               if ln[nomes.index("SITUAÇÃO")] == "EM ABERTO"]
    assert por_filial(abertos) == {nome_f[f]: (n, round(s, 2))
                                   for f, (n, s) in esp.items()}
    rec = ba._recortes_do_farol_web("pv_pedidos", rel)  # noqa: SLF001
    rec_a = ba._recortes_do_farol_web("pv_pedidos", rel_a)  # noqa: SLF001
    assert set(rec) == {"AM", "RR"}
    assert rec == rec_a
    # os cartoes do estado = kpis_de das linhas da filial
    for uf, fil in (("RR", "BOA VISTA"), ("AM", "MANAUS")):
        ls = [ln for ln in t["linhas"] if ln[i_f] == fil]
        assert rec[uf]["kpis"] == t["kpis_de"](ls)


# ---------------------------------------------------------------- 7
def test_RN_GER_019_credito_a_analisar_inclui_o_nao_apurado(rn, tmp_path):
    _r, t, nomes, ped = _pedidos(rn, _ctx(rn, tmp_path))
    fn = dict((r_[0], r_[1]) for r_ in t["recortes"])["Crédito a analisar"]
    i_p = nomes.index("PEDIDO")
    no_recorte = {ln[i_p] for ln in t["linhas"] if fn(ln)}
    nao_apurados = {p for p, d in ped.items()
                    if d["ANÁLISE CRÉDITO"] == rn.CREDITO_NAO_APURADO}
    assert nao_apurados == {"000001", "000005", "000006", "000007", "000008"}
    # e o recorte segue com o resto que nao e "Com Limite"
    assert no_recorte == nao_apurados | {"000003", "000009"}
    assert "000002" not in no_recorte and "000004" not in no_recorte


# ---------------------------------------------------------------- escopo
def _tab(rel, titulo):
    t = next(x for x in rel["tabelas"] if x["titulo"] == titulo)
    return t, [c["nome"] for c in t["colunas"]]


def _kpi(rel, prefixo):
    return next(x for x in rel["kpis"] if x["rotulo"].startswith(prefixo))


def test_RN_GER_019_fretes_e_entregas_iguais_ao_main(rn, tmp_path):
    """A RN-GER-019 vale so na familia do Farol de Pedidos: Fretes e Entregas
    seguem o cadastro por codigo (o main), mesmo com a loja da filial em
    outra cidade (900008) e com a loja nao identificada (900009)."""
    novo = rn.fretes(_ctx(rn, tmp_path / "n", extra=("frete",)))
    main = rn.fretes(_ctx(rn, tmp_path / "m", antes=True, extra=("frete",)))
    t, nomes = _tab(novo, "Notas com frete")
    t_m, _n = _tab(main, "Notas com frete")
    assert t["linhas"] == t_m["linhas"]
    assert novo["kpis"] == main["kpis"]
    # valor x regra: frete = cidade do cadastro por codigo fora das capitais
    i_nf, i_cid, i_uf = (nomes.index("NF"), nomes.index("CIDADE"),
                         nomes.index("UF"))
    cid = {ln[i_nf]: (ln[i_cid], ln[i_uf]) for ln in t["linhas"]}
    assert set(cid) == {nf.lstrip("0") for nf in NOTAS_FRETE}
    assert cid["601"] == ("PARINTINS", "AM")      # nao a loja RR
    assert cid["603"] == ("ITACOATIARA", "AM")    # nao "" (nao identificada)
    assert cid["604"] == ("ITACOATIARA", "AM")
    nov = sum(v for nf, (_f, _c, v) in NOTAS_FRETE.items()
              if nf.startswith("0006"))
    k = _kpi(novo, "Notas com frete")
    assert (k["valor"], k["detalhe"]) == ("4", rn.moeda(nov))

    # Entregas (SET/26: as notas de antes do acompanhamento, CONCLUIDA)
    e_n = rn.entregas(_ctx(rn, tmp_path / "en", extra=("frete",), mes="09"))
    e_m = rn.entregas(_ctx(rn, tmp_path / "em", antes=True,
                           extra=("frete",), mes="09"))
    te, ne = _tab(e_n, "Entregas")
    te_m, _n = _tab(e_m, "Entregas")
    assert te["linhas"] == te_m["linhas"]
    assert e_n["kpis"] == e_m["kpis"]
    set_ = [ln for ln in te["linhas"]
            if ln[ne.index("NF")] in {"701", "702", "703", "704"}]
    assert len(set_) == 4
    assert all(ln[ne.index("LOCAL/FRETE")] == "FRETE" for ln in set_)
    assert {ln[ne.index("CIDADE")] for ln in set_} == {"PARINTINS",
                                                       "ITACOATIARA"}
    fr = _kpi(e_n, "Frete")
    assert fr == _kpi(e_m, "Frete")
    assert fr["valor"] != rn.moeda(0.0)


def test_RN_GER_019_excluidos_usam_a_loja_e_contam_clientes_pelo_codigo(
        rn, tmp_path):
    r = rn.pedidos_excluidos(_ctx(rn, tmp_path, extra=("exc",)))
    t, nomes = _tab(r, "Pedidos excluídos")
    d = {ln[nomes.index("PEDIDO")]: dict(zip(nomes, ln))
         for ln in t["linhas"]}
    assert set(d) == {"000901", "000902", "000903"}
    assert (d["000901"]["UF"], d["000901"]["CIDADE"]) == ("RR", "BOA VISTA")
    assert (d["000902"]["UF"], d["000902"]["CIDADE"]) == ("AM", "MANAUS")
    assert d["000903"]["CLIENTE"] == f"900003 - {rn.LOJA_NAO_IDENTIFICADA}"
    # 900001 (em RR e em AM, dois nomes de loja) e 900003: 2 clientes
    assert _kpi(r, "Clientes")["valor"] == "2"
    k = _kpi(r, "Pedidos excluídos")
    assert (k["valor"], k["detalhe"]) == ("3", rn.moeda(600.0))
