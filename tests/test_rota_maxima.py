"""T-0010 - o JSON da rota da Maxima (layout ERP_MXSROTACLI).

Regra aprovada pelo Alexandre (R-20261120-104729), RN-ROT-001 (T-0010):
- dtfinal = dtproxvisita + periodicidade - 1 dia (periodicidade = o valor
  exportado: 7, 14, 30 ou 45); nenhuma linha com 3000-01-01;
- ficam fora do arquivo: o cliente inativo, o cliente interno (pelo
  nome/fantasia, meta_nucleo.e_cliente_interno) e a conta 000040 (vendedor
  de teste).
- (R-20261120-111303) o sabado-deposito (1o sabado do mes) VOLTA ao
  arquivo, com a data final curta (dtproxvisita + periodicidade - 1):
  nenhum cliente ativo some da Maxima.

Carteira 100% ficticia: "Cliente NN", vendedores "Vendedor A/B" e a
"Conta Teste" 000040; sem telefone, e-mail ou CNPJ real.
"""
import collections
import copy
import datetime as dt

import pytest

import planner_nucleo as pn

D = dt.date
REGRA = "RN-ROT-001 (T-0010), R-20261120-104729, R-20261120-111303"

# a regra, escrita por extenso aqui (nao lida do codigo): curva -> o valor
# exportado no campo periodicidade (60 dias da D/Z vai como 45, o maior
# aceito pela Maxima); VISITA_SEMANAL = 7
PERIODICIDADE_ESPERADA = {"S": 7, "A": 7, "B": 14, "C": 30, "D": 45, "Z": 45}

JANELA = (D(2026, 11, 23), D(2026, 12, 31))
HOJE = D(2026, 11, 20)
MESES = (("2026-11", ["2026-11-02", "2026-11-20"]),
         ("2026-12", ["2026-12-25"]))


def _d(iso: str) -> dt.date:
    return D.fromisoformat(iso[:10])


# --------------------------------------------------------------------------
# carteira ficticia
# --------------------------------------------------------------------------
def _pessoa(cod, nome, cargo, responde_a=""):
    return {"cod_protheus": cod, "cod_maxima": "", "nome": nome,
            "cargo": cargo, "uf_base": "AM", "cidade_base": "MANAUS",
            "responde_a": responde_a, "ativo": True, "email": "",
            "interior": False, "provisorio": False,
            "conta_supervisor": False}


VENDEDORES = {1: "000015", 2: "000016", 3: pn.CONTA_TESTE_MAXIMA}
# zona -> {curva: quantos}; a zona 1 e pesada (sobra para o deposito)
PLANO = {1: {"S": 35, "A": 30, "B": 25, "C": 40, "Z": 40},
         2: {"S": 10, "A": 10, "B": 20, "C": 40, "Z": 60},
         3: {"A": 3, "C": 5, "Z": 4}}
RECEITA_3M = {"S": 90000.0, "A": 40000.0, "B": 20000.0, "C": 300.0, "Z": 0.0}
NOMES_INTERNOS = {7: ("Cliente 07 FRW", ""),
                  77: ("Cliente 77", "BAP AUTOPARTS LOJA"),
                  177: ("PMZ DISTRIBUIDORA Cliente 177", "")}
INATIVOS_PROTHEUS = {11, 52, 120, 201, 260, 300}
INATIVOS_PLANNER = {13, 99, 150, 222}


def _cfg(mes, feriados):
    c = pn.config_nova(mes)
    c["feriados"] = list(feriados)
    c["pessoas"] = [_pessoa("000901", "Supervisor Teste", "SUPERVISOR"),
                    _pessoa("000015", "Vendedor A", "VENDEDOR", "000901"),
                    _pessoa("000016", "Vendedor B", "VENDEDOR", "000901"),
                    _pessoa(pn.CONTA_TESTE_MAXIMA, "Conta Teste", "VENDEDOR",
                            "000901")]
    c["zonas"] = [{"id": f"z{i}", "nome": f"ZONA {i}", "uf": "AM",
                   "vendedor": v, "visitas_por_dia": 0,
                   "atendimento": [{"vendedor": v, "segmentos": []}]}
                  for i, v in VENDEDORES.items()]
    c["areas"] = {f"AM|MANAUS|BAIRRO {i}": f"z{i}" for i in VENDEDORES}
    c["parametros"]["excedentes_no_sabado"] = True   # para ter deposito
    c["parametros"]["dias_cidade_base"] = 0
    c["clientes_inativos"] = {f"{n:06d}-01": {"em": "2026-11-01"}
                              for n in INATIVOS_PLANNER}
    return pn._com_codigos(c)


def _clientes():
    out, n = [], 0
    for z, plano in PLANO.items():
        for curva, qtd in plano.items():
            for _ in range(qtd):
                n += 1
                nome, fant = NOMES_INTERNOS.get(n, (f"Cliente {n:02d}",
                                                    f"Cliente {n:02d}"))
                rec = RECEITA_3M[curva]
                out.append({
                    "CHAVE_CLIENTE": f"{n:06d}-01", "COD_CLIENTE": f"{n:06d}",
                    "LOJA": "01", "NOME_CLIENTE": nome, "NOME_FANTASIA": fant,
                    "UF": "AM", "CIDADE": "MANAUS", "BAIRRO": f"BAIRRO {z}",
                    "ENDERECO": f"RUA {n % 9}", "NUMERO": str(n),
                    "CONTATO": "", "TELEFONE": "",
                    "LATITUDE": -3.10 + ((n * 37) % 100 - 50) / 1000,
                    "LONGITUDE": -60.02 + ((n * 53) % 100 - 50) / 1000,
                    "LIMITE_DISPONIVEL": 0.0, "LIMITE_APROVADO": 0.0,
                    "VALOR_EM_ATRASO": 0.0, "DIAS_ATRASO": 0.0,
                    "CURVA_RECEITA": curva, "RECEITA_PERIODO": rec,
                    "RECEITA_6M": rec * 2, "MEDIA_MENSAL": 0.0,
                    "MEDIA_MENSAL_6M": 0.0, "RECEITA_PERIODO_ANTERIOR": 0.0,
                    "MEDIA_MENSAL_ANTERIOR": 0.0, "RECEITA_ACUMULADA": 0.0,
                    "STATUS_CLIENTE": "ATIVO",
                    "STATUS_PROTHEUS": ("INATIVO" if n in INATIVOS_PROTHEUS
                                        else "ATIVO"),
                    "SEGMENTO": "AUTOPEÇAS", "SUBSEGMENTO": "",
                    "DIAS_SEM_COMPRA": 10 if rec else 200,
                    "ULTIMA_COMPRA": None, "COD_ULTIMO_VENDEDOR": "",
                    "AREA": f"AM|MANAUS|BAIRRO {z}", "AREA_ROTULO": "",
                    "COMPRA_BATERIA": ""})
    return out


@pytest.fixture(scope="module")
def rotas():
    """{mes: (cfg, clientes, rota de gerar_rota, linhas do JSON)} para
    nov e dez/2026, hoje = 20/11, com o deposito ligado."""
    antes = (pn.HOJE_DA_ROTA[0], pn.REESCREVER_PASSADO[0],
             pn.IGNORAR_ROTA_FIXA[0])
    pn.HOJE_DA_ROTA[0] = HOJE
    pn.REESCREVER_PASSADO[0] = True
    pn.IGNORAR_ROTA_FIXA[0] = True
    try:
        saida = {}
        for mes, fer in MESES:
            cfg, cli = _cfg(mes, fer), _clientes()
            pn.aplicar_parametros(cfg, cli)
            rota = pn.gerar_rota(cfg, cli)
            json_ = pn.linhas_protheus(cfg, cli, linhas=rota,
                                       compromisso="20261120080000")
            saida[mes] = (cfg, cli, rota, json_)
        return saida
    finally:
        (pn.HOJE_DA_ROTA[0], pn.REESCREVER_PASSADO[0],
         pn.IGNORAR_ROTA_FIXA[0]) = antes


def _deposito(mes):
    ano, m = int(mes[:4]), int(mes[5:7])
    return next(D(ano, m, d) for d in range(1, 8) if D(ano, m, d).weekday() == 5)


def _codcli(r):
    return f"{r['COD_CLIENTE'].zfill(6)}{str(r['LOJA']).zfill(2)}"


def _periodicidade_esperada(cliente_ou_linha):
    if cliente_ou_linha.get("VISITA_SEMANAL") == "SIM":
        return 7
    return PERIODICIDADE_ESPERADA[(cliente_ou_linha.get("CURVA_RECEITA")
                                   or "Z")[:1]]


def _linha_rota(chave, data, vendedor="000015", curva="C", ordem=1,
                nome="Cliente 01", fantasia="Cliente 01", semanal=""):
    cod, loja = chave.split("-")
    return {"CHAVE_CLIENTE": chave, "COD_CLIENTE": cod, "LOJA": loja,
            "COD_VENDEDOR": vendedor, "DATA": data, "ORDEM_DE_VISITA": ordem,
            "CURVA_RECEITA": curva, "NOME_CLIENTE": nome,
            "NOME_FANTASIA": fantasia, "VISITA_SEMANAL": semanal}


# --------------------------------------------------------------------------
# 1. dtfinal = dtproxvisita + periodicidade - 1
# --------------------------------------------------------------------------
@pytest.mark.parametrize("periodicidade,esperado", [
    (7, "2026-11-29T00:00:00"), (14, "2026-12-06T00:00:00"),
    (30, "2026-12-22T00:00:00"), (45, "2027-01-06T00:00:00")])
def test_RN_ROT_001_dtfinal_funcao_pura(periodicidade, esperado):
    """RN-ROT-001 (T-0010), R-20261120-104729: dtfinal = dtproxvisita +
    periodicidade - 1 dia (visita 23/11/2026)."""
    assert pn.dtfinal_protheus(D(2026, 11, 23), periodicidade) == esperado


def test_RN_ROT_001_dtfinal_virada_de_ano_e_bissexto():
    """RN-ROT-001 (T-0010), R-20261120-104729: a conta e de calendario (vira
    mes e ano; 2028 e bissexto)."""
    assert pn.dtfinal_protheus(D(2026, 12, 31), 7) == "2027-01-06T00:00:00"
    assert pn.dtfinal_protheus(D(2028, 2, 20), 14) == "2028-03-04T00:00:00"
    assert pn.dtfinal_protheus(D(2026, 11, 23), 1) == "2026-11-23T00:00:00"


@pytest.mark.parametrize("curva,semanal,per", [
    ("S", "", 7), ("A", "", 7), ("B", "", 14), ("C", "", 30),
    ("D", "", 45), ("Z", "", 45), ("C", "SIM", 7), ("Z", "SIM", 7)])
def test_RN_ROT_001_dtfinal_via_linhas_protheus(curva, semanal, per):
    """RN-ROT-001 (T-0010), R-20261120-104729: pela linhas_protheus, a curva
    S/A=7, B=14, C=30, D/Z=45 (60 levado ao maior aceito) e VISITA_SEMANAL=7;
    dtfinal = dtproxvisita + essa periodicidade - 1."""
    visita = D(2026, 11, 24)                          # terca, dia util
    cli = {"CHAVE_CLIENTE": "000001-01", "CURVA_RECEITA": curva,
           "STATUS_PROTHEUS": "ATIVO", "NOME_CLIENTE": "Cliente 01",
           "NOME_FANTASIA": "Cliente 01"}
    rota = [_linha_rota("000001-01", visita, curva=curva, semanal=semanal)]
    out = pn.linhas_protheus({"mes": "2026-11"}, [cli], linhas=rota,
                             compromisso="20261120080000")
    assert len(out) == 1
    x = out[0]
    assert x["periodicidade"] == str(per)
    assert x["dtproxvisita"] == "2026-11-24T00:00:00"
    assert _d(x["dtfinal"]) - _d(x["dtproxvisita"]) == dt.timedelta(per - 1)
    assert x["dtinicio"] == "2000-01-01T00:00:00"
    assert x["numsemana"] == 1 and x["diasemana"] == "TERCA"


# --------------------------------------------------------------------------
# 2. nenhuma linha com 3000-01-01
# --------------------------------------------------------------------------
def test_RN_ROT_001_nenhuma_linha_com_3000(rotas):
    """RN-ROT-001 (T-0010), R-20261120-104729: nenhuma linha sai com dtfinal
    3000-01-01 (a vigencia termina em dtproxvisita + periodicidade - 1)."""
    todas = [x for _c, _k, _r, js in rotas.values() for x in js]
    assert todas
    assert not [x for x in todas if x["dtfinal"].startswith("3000")]
    assert max(_d(x["dtfinal"]) for x in todas) <= D(2027, 2, 14)


# --------------------------------------------------------------------------
# 3. sabado-deposito DENTRO (R-20261120-111303); interno e 000040 fora
# --------------------------------------------------------------------------
def test_RN_ROT_001_sabado_deposito_entra_com_cfg_vazio():
    """RN-ROT-001 (T-0010), R-20261120-111303: a visita do 1o sabado do mes
    (deposito) VAI para a Maxima, como o ultimo sabado e os do meio, com o
    dtfinal curto (dtproxvisita + periodicidade - 1). Com cfg vazio e sem
    clientes (chamada do Farol de Roteirizacao, relatorios_nucleo:
    linhas_protheus({}, [], linhas=rota)) nao quebra."""
    rota = [_linha_rota("000001-01", D(2026, 11, 7), ordem=1),     # 1o sab
            _linha_rota("000002-01", D(2026, 11, 14), ordem=1),
            _linha_rota("000003-01", D(2026, 11, 28), ordem=1),    # ultimo
            _linha_rota("000004-01", D(2026, 12, 5), ordem=1),      # 1o sab
            _linha_rota("000005-01", D(2026, 12, 7), ordem=1)]
    for r in rota:                       # o Farol nao manda nome
        r.pop("NOME_CLIENTE")
        r.pop("NOME_FANTASIA")
    out = pn.linhas_protheus({}, [], linhas=copy.deepcopy(rota))
    assert sorted(x["codcli"] for x in out) == [
        "00000101", "00000201", "00000301", "00000401", "00000501"]
    assert pn.motivo_fora_da_maxima({}, rota[0]) == ""
    assert pn.motivo_fora_da_maxima({}, rota[3]) == ""
    dep = {x["codcli"]: x for x in out}
    # curva C = 30: 7/11 -> 6/12; 5/12 -> 3/1/2027
    assert (dep["00000101"]["dtproxvisita"], dep["00000101"]["dtfinal"]) == (
        "2026-11-07T00:00:00", "2026-12-06T00:00:00")
    assert (dep["00000401"]["dtproxvisita"], dep["00000401"]["dtfinal"]) == (
        "2026-12-05T00:00:00", "2027-01-03T00:00:00")
    # DATA como datetime (a linha pode vir assim de fora) tambem entra
    r_dt = _linha_rota("000006-01", dt.datetime(2026, 12, 5))
    assert pn.motivo_fora_da_maxima({}, r_dt) == ""
    out_dt = pn.linhas_protheus({}, [], linhas=[r_dt])
    assert [(x["codcli"], x["dtproxvisita"], x["dtfinal"]) for x in out_dt] \
        == [("00000601", "2026-12-05T00:00:00", "2027-01-03T00:00:00")]


def test_RN_ROT_001_sabado_deposito_entra_pelo_mes_do_cfg():
    """RN-ROT-001 (T-0010), R-20261120-111303: com cfg["mes"], o 1o sabado do
    mes do cfg (5/12 para dez/2026) nao e motivo de fora; vai com o
    dtfinal curto, uma linha so."""
    r = _linha_rota("000001-01", D(2026, 12, 5), curva="S")
    cfg = {"mes": "2026-12"}
    assert pn.motivo_fora_da_maxima(cfg, r) == ""
    assert pn.motivo_fora_da_maxima(
        cfg, _linha_rota("000001-01", D(2026, 12, 12))) == ""
    out = pn.linhas_protheus(cfg, [], linhas=[r])
    assert [(x["dtproxvisita"], x["periodicidade"], x["dtfinal"])
            for x in out] == [("2026-12-05T00:00:00", "7",
                               "2026-12-11T00:00:00")]


@pytest.mark.parametrize("curva,per", [("S", 7), ("B", 14), ("C", 30),
                                       ("Z", 45)])
def test_RN_ROT_001_sabado_deposito_dtfinal_curto(curva, per):
    """RN-ROT-001 (T-0010), R-20261120-111303: a linha do sabado-deposito tem
    dtfinal = dtproxvisita + periodicidade - 1 (nunca 3000-01-01) e a
    Maxima gera uma so ocorrencia."""
    cli = {"CHAVE_CLIENTE": "000001-01", "CURVA_RECEITA": curva,
           "STATUS_PROTHEUS": "ATIVO", "NOME_CLIENTE": "Cliente 01",
           "NOME_FANTASIA": "Cliente 01"}
    r = _linha_rota("000001-01", D(2026, 11, 7), curva=curva)
    out = pn.linhas_protheus({"mes": "2026-11"}, [cli], linhas=[r],
                             compromisso="20261120080000")
    assert len(out) == 1
    x = out[0]
    assert x["periodicidade"] == str(per)
    assert x["dtfinal"] == pn.dtfinal_protheus(D(2026, 11, 7), per)
    assert (_d(x["dtfinal"]) - _d(x["dtproxvisita"])).days == per - 1
    assert x["diasemana"] == "SABADO"


def test_RN_ROT_001_sabado_deposito_nao_duplica():
    """RN-ROT-001 (T-0010), R-20261120-111303: o sabado-deposito entra uma vez
    por visita; nenhuma chave codcli+codusur+dtproxvisita repete, nem com
    o cliente tambem visitado em dia util do mesmo mes."""
    rota = [_linha_rota("000001-01", D(2026, 11, 7), ordem=1),      # dep
            _linha_rota("000002-01", D(2026, 11, 7), ordem=2),      # dep
            _linha_rota("000001-01", D(2026, 11, 24), ordem=1),
            _linha_rota("000003-01", D(2026, 11, 28), ordem=1)]
    out = pn.linhas_protheus({"mes": "2026-11"}, [], linhas=rota,
                             compromisso="20261120080000")
    chaves = collections.Counter((x["codcli"], x["codusur"],
                                  x["dtproxvisita"]) for x in out)
    assert len(out) == len(rota) == len(chaves)
    assert max(chaves.values()) == 1
    assert sum(1 for x in out
               if x["dtproxvisita"] == "2026-11-07T00:00:00") == 2


@pytest.mark.parametrize("nome,fantasia", [
    ("FRW COMERCIO", ""), ("Cliente 01", "FRW"),
    ("BAP AUTOPARTS LTDA", ""), ("Cliente 01", "Bap Autoparts Loja 2"),
    ("BAP AUTO PARTS", ""), ("PMZ DISTRIBUIDORA", ""),
    ("Cliente 01", "PMZ Distribuidora")])
def test_RN_ROT_001_interno_fora(nome, fantasia):
    """RN-ROT-001 (T-0010), R-20261120-104729: CNPJ interno (FRW, BAP AUTOPARTS,
    PMZ DISTRIBUIDORA no nome ou na fantasia) nao vai para a Maxima."""
    r = _linha_rota("000001-01", D(2026, 11, 24), nome=nome,
                    fantasia=fantasia)
    assert pn.motivo_fora_da_maxima({"mes": "2026-11"}, r) == "INTERNO"
    assert pn.linhas_protheus({"mes": "2026-11"}, [], linhas=[r]) == []


def test_RN_ROT_001_interno_pelo_cadastro_do_cliente():
    """RN-ROT-001 (T-0010), R-20261120-104729: sem nome na linha da rota, vale
    o nome do cadastro do cliente."""
    r = _linha_rota("000001-01", D(2026, 11, 24), nome="", fantasia="")
    cli = {"CHAVE_CLIENTE": "000001-01", "NOME_CLIENTE": "",
           "NOME_FANTASIA": "BAP AUTOPARTS", "STATUS_PROTHEUS": "ATIVO"}
    assert pn.motivo_fora_da_maxima({}, r, cli) == "INTERNO"
    # "FRWX" nao e FRW (palavra inteira)
    r2 = _linha_rota("000002-01", D(2026, 11, 24), nome="FRWX PECAS")
    assert pn.motivo_fora_da_maxima({}, r2) == ""


@pytest.mark.parametrize("vendedor", ["000040", "40", 40])
def test_RN_ROT_001_conta_000040_fora(vendedor):
    """RN-ROT-001 (T-0010), R-20261120-104729: a conta 000040 (vendedor de
    teste) nao vai, com ou sem zeros a esquerda."""
    r = _linha_rota("000001-01", D(2026, 11, 24), vendedor=vendedor)
    assert pn.motivo_fora_da_maxima({}, r) == "CONTA_000040"
    assert pn.linhas_protheus({}, [], linhas=[r]) == []
    assert pn.motivo_fora_da_maxima(
        {}, _linha_rota("000001-01", D(2026, 11, 24),
                        vendedor="000400")) == ""


def test_RN_ROT_001_precedencia_dos_motivos():
    """RN-ROT-001 (T-0010), R-20261120-104729 e R-20261120-111303: precedencia
    INATIVO, INTERNO, CONTA_000040; o sabado-deposito nao e motivo."""
    r = _linha_rota("000001-01", D(2026, 11, 7), vendedor="000040",
                    nome="FRW")
    cli = {"CHAVE_CLIENTE": "000001-01", "STATUS_PROTHEUS": "INATIVO"}
    assert pn.motivo_fora_da_maxima({}, r, cli) == "INATIVO"
    assert pn.motivo_fora_da_maxima({}, r) == "INTERNO"
    r["NOME_CLIENTE"] = "Cliente 01"
    assert pn.motivo_fora_da_maxima({}, r) == "CONTA_000040"
    r["COD_VENDEDOR"] = "000015"
    assert pn.motivo_fora_da_maxima({}, r) == ""        # 1o sabado: entra


def test_RN_ROT_001_motivos_fora_sem_sabado_deposito():
    """RN-ROT-001 (T-0010), R-20261120-111303: MOTIVOS_FORA_DA_MAXIMA ==
    ("INATIVO", "INTERNO", "CONTA_000040"), nessa precedencia; o
    sabado-deposito saiu da lista."""
    assert pn.MOTIVOS_FORA_DA_MAXIMA == ("INATIVO", "INTERNO", "CONTA_000040")
    assert "SABADO_DEPOSITO" not in pn.MOTIVOS_FORA_DA_MAXIMA


# --------------------------------------------------------------------------
# 4. inativo fora
# --------------------------------------------------------------------------
def test_RN_ROT_001_inativo_fora():
    """RN-ROT-001 (T-0010), R-20261120-104729: inativo (no Protheus ou inativado
    no Planner) nao vai, mesmo que a linha da rota exista."""
    r1 = _linha_rota("000001-01", D(2026, 11, 24))
    r2 = _linha_rota("000002-01", D(2026, 11, 24), ordem=2)
    r3 = _linha_rota("000003-01", D(2026, 11, 24), ordem=3)
    clis = [{"CHAVE_CLIENTE": "000001-01", "STATUS_PROTHEUS": "INATIVO"},
            {"CHAVE_CLIENTE": "000002-01", "STATUS_PROTHEUS": "ATIVO"},
            {"CHAVE_CLIENTE": "000003-01", "STATUS_PROTHEUS": "ATIVO"}]
    cfg = {"mes": "2026-11", "clientes_inativos": {"000002-01": {}}}
    out = pn.linhas_protheus(cfg, clis, linhas=[r1, r2, r3])
    assert [x["codcli"] for x in out] == ["00000301"]


def test_RN_ROT_001_inativo_fora_da_rota_real(rotas):
    """RN-ROT-001 (T-0010), R-20261120-104729: na carteira ficticia, nenhum
    inativo tem linha no JSON de nov nem de dez."""
    inativos = {f"{n:06d}01" for n in INATIVOS_PROTHEUS | INATIVOS_PLANNER}
    for _c, _k, _r, js in rotas.values():
        assert not inativos & {x["codcli"] for x in js}


# --------------------------------------------------------------------------
# 5. nenhum cliente perdido pelo gerador (gerar_rota real)
# --------------------------------------------------------------------------
def test_RN_ROT_001_toda_visita_exportavel_vira_linha(rotas):
    """RN-ROT-001 (T-0010), R-20261120-104729 e R-20261120-111303: com a
    gerar_rota real (nov e dez/2026, feriado 25/12, deposito ligado), TODA
    visita de cliente ativo e exportavel, INCLUSIVE a do sabado-deposito,
    vira exatamente uma linha; nenhuma linha sobra; nenhuma chave
    codcli+codusur+dtproxvisita repete; cada linha cobre exatamente a sua periodicidade
    (dtfinal - dtproxvisita = p - 1) e gera uma so ocorrencia; nenhuma
    (cliente, data) repete entre as remessas de nov e dez."""
    internos = {f"{n:06d}01" for n in NOMES_INTERNOS}
    vistos = collections.Counter()
    for mes, (cfg, cli, rota, js) in rotas.items():
        por_chave = {c["CHAVE_CLIENTE"]: c for c in cli}
        dep = _deposito(mes)
        assert any(r["DATA"] == dep for r in rota), \
            f"{mes}: a carteira tem de encher o deposito"
        esperadas = collections.Counter()
        for r in rota:
            c = por_chave[r["CHAVE_CLIENTE"]]
            if (pn.cliente_inativo(cfg, c) or _codcli(r) in internos
                    or r["COD_VENDEDOR"].zfill(6) == "000040"):
                continue
            esperadas[(_codcli(r), r["COD_VENDEDOR"].zfill(6),
                       f"{r['DATA']:%Y-%m-%d}T00:00:00",
                       int(r["ORDEM_DE_VISITA"]),
                       str(_periodicidade_esperada(r)))] += 1
        obtidas = collections.Counter(
            (x["codcli"], x["codusur"], x["dtproxvisita"], x["sequencia"],
             x["periodicidade"]) for x in js)
        faltam = esperadas - obtidas
        sobram = obtidas - esperadas
        assert not faltam, f"{mes}: {sum(faltam.values())} visita(s) perdida(s)"
        assert not sobram, f"{mes}: {sum(sobram.values())} linha(s) a mais"
        dep_iso = f"{dep:%Y-%m-%d}T00:00:00"
        assert any(x["dtproxvisita"] == dep_iso for x in js), \
            f"{mes}: o sabado-deposito tem de ir ao JSON"
        chaves = collections.Counter(
            (x["codcli"], x["codusur"], x["dtproxvisita"]) for x in js)
        assert max(chaves.values()) == 1, f"{mes}: chave repetida no JSON"
        for x in js:
            p = int(x["periodicidade"])
            ini, fim = _d(x["dtproxvisita"]), _d(x["dtfinal"])
            assert (fim - ini).days == p - 1
            # a Maxima repete a cada p dias ate o dtfinal: uma ocorrencia
            assert len(range(0, (fim - ini).days + 1, p)) == 1
            assert _d(x["dtproxvisita"]).strftime("%Y-%m") == mes
            vistos[(x["codcli"], x["dtproxvisita"])] += 1
    assert not [k for k, n in vistos.items() if n > 1]


# --------------------------------------------------------------------------
# 6. quem fica sem compromisso entre 23/11 e 31/12/2026 (so contagens)
# --------------------------------------------------------------------------
MOTIVOS_JANELA = ("INATIVO", "INTERNO", "CONTA_000040",
                  "SO_NO_SABADO_DEPOSITO", "SEM_VISITA_NA_ROTA_DO_MES",
                  "VISITADO_ANTES_DE_23_11_E_PROXIMA_EM_JANEIRO",
                  "PERDIDO_PELO_GERADOR")


def _classificar(rotas):
    """{chave: motivo ou "COM_COMPROMISSO"} e {chave: periodicidade}."""
    cfg_n, cli_n, rota_n, js_n = rotas["2026-11"]
    cfg_d, cli_d, rota_d, js_d = rotas["2026-12"]
    js_janela = (pn.rota_a_partir_de(js_n, JANELA[0])
                 + [x for x in js_d if _d(x["dtproxvisita"]) <= JANELA[1]])
    com = {x["codcli"] for x in js_janela}
    antes = collections.defaultdict(list)          # nov, antes de 23/11
    for x in js_n:
        if _d(x["dtproxvisita"]) < JANELA[0]:
            antes[x["codcli"]].append(x)
    rota_janela = collections.defaultdict(list)
    for mes, rota in (("2026-11", rota_n), ("2026-12", rota_d)):
        for r in rota:
            if JANELA[0] <= r["DATA"] <= JANELA[1]:
                rota_janela[r["CHAVE_CLIENTE"]].append((mes, r))
    por_d = {c["CHAVE_CLIENTE"]: c for c in cli_d}
    motivo, period = {}, {}
    for c in cli_n:
        ch = c["CHAVE_CLIENTE"]
        cod = f"{c['COD_CLIENTE']}{c['LOJA'].zfill(2)}"
        period[ch] = _periodicidade_esperada(por_d.get(ch, c))
        if cod in com:
            motivo[ch] = "COM_COMPROMISSO"
        elif pn.cliente_inativo(cfg_d, c) or pn.cliente_inativo(cfg_n, c):
            motivo[ch] = "INATIVO"
        elif _interno(c):
            motivo[ch] = "INTERNO"
        elif pn.vendedor_do_cliente(cfg_d, c).zfill(6) == "000040":
            motivo[ch] = "CONTA_000040"
        elif rota_janela.get(ch):
            if all(r["DATA"] == _deposito(m) for m, r in rota_janela[ch]):
                motivo[ch] = "SO_NO_SABADO_DEPOSITO"
            else:
                motivo[ch] = "PERDIDO_PELO_GERADOR"
        elif antes.get(cod) and max(
                _d(x["dtproxvisita"]) + dt.timedelta(int(x["periodicidade"]))
                for x in antes[cod]) > JANELA[1]:
            motivo[ch] = "VISITADO_ANTES_DE_23_11_E_PROXIMA_EM_JANEIRO"
        else:
            motivo[ch] = "SEM_VISITA_NA_ROTA_DO_MES"
    return motivo, period


def _interno(c):
    import meta_nucleo as mn
    return mn.e_cliente_interno(c.get("NOME_CLIENTE"), c.get("NOME_FANTASIA"))


def test_RN_ROT_001_sem_compromisso_na_janela_sem_perdido(rotas):
    """RN-ROT-001 (T-0010), R-20261120-104729 e R-20261120-111303: de 23/11 a
    31/12/2026 (JSON de nov a partir de 23/11 + JSON de dez), todo cliente
    sem compromisso tem motivo de regra; PERDIDO_PELO_GERADOR = 0 e
    SO_NO_SABADO_DEPOSITO = 0 (o sabado-deposito vai ao JSON: nenhum
    cliente ativo some da Maxima por causa dele). Imprime so contagens."""
    motivo, period = _classificar(rotas)
    cont = collections.Counter(motivo.values())
    ativos = [ch for ch, m in motivo.items() if m != "INATIVO"]
    sem = [ch for ch in ativos if motivo[ch] != "COM_COMPROMISSO"]
    por_p = collections.defaultdict(collections.Counter)
    for ch in sem:
        por_p[motivo[ch]][period[ch]] += 1
    linhas = [f"Carteira ficticia: {len(motivo)} clientes; ativos "
              f"{len(ativos)}; com compromisso "
              f"{cont['COM_COMPROMISSO']}; ativos sem compromisso "
              f"{len(sem)} ({100 * len(sem) / max(1, len(ativos)):.1f}%)",
              f"{'MOTIVO':46} {'QTD':>4}  p7 p14 p30 p45"]
    for m in MOTIVOS_JANELA:
        q = por_p.get(m, collections.Counter())
        n = cont[m] if m == "INATIVO" else sum(q.values())
        linhas.append(f"{m:46} {n:>4} {q[7]:>3} {q[14]:>3} {q[30]:>3} "
                      f"{q[45]:>3}")
    tot = collections.Counter(period[ch] for ch in sem)
    linhas.append(f"{'TOTAL ativos sem compromisso':46} {len(sem):>4} "
                  f"{tot[7]:>3} {tot[14]:>3} {tot[30]:>3} {tot[45]:>3}")
    print("\n" + "\n".join(linhas))
    assert cont["PERDIDO_PELO_GERADOR"] == 0, "\n".join(linhas)
    assert cont["SO_NO_SABADO_DEPOSITO"] == 0, "\n".join(linhas)
    # o teste so prova algo se o deposito da janela (5/12) tiver visita
    _cd, _kd, rota_d, js_d = rotas["2026-12"]
    dep = _deposito("2026-12")
    assert any(r["DATA"] == dep for r in rota_d)
    assert any(_d(x["dtproxvisita"]) == dep for x in js_d)
    assert set(cont) <= set(MOTIVOS_JANELA) | {"COM_COMPROMISSO"}


def test_RN_ROT_001_rota_a_partir_de_23_11():
    """RN-ROT-001 (T-0010), R-20261120-104729: o JSON 'a partir de 23/11' leva
    so as visitas de 23/11 em diante, com o mesmo dtfinal."""
    rota = [_linha_rota("000001-01", D(2026, 11, 20)),
            _linha_rota("000001-01", D(2026, 11, 23), curva="S"),
            _linha_rota("000001-01", D(2026, 11, 30), curva="S")]
    out = pn.rota_a_partir_de(
        pn.linhas_protheus({"mes": "2026-11"}, [], linhas=copy.deepcopy(rota)),
        D(2026, 11, 23))
    assert [(x["dtproxvisita"][:10], x["dtfinal"][:10]) for x in out] == [
        ("2026-11-23", "2026-11-29"), ("2026-11-30", "2026-12-06")]


# --------------------------------------------------------------------------
# 6b. todo cliente ativo com compromisso no mes e o espacamento da rota
# --------------------------------------------------------------------------
MOTIVO_ESPACAMENTO = "espaçamento da rota do Planner (anterior à T-0010)"


def _exportavel(cfg, c):
    return not (pn.cliente_inativo(cfg, c) or _interno(c)
                or pn.vendedor_do_cliente(cfg, c).zfill(6) == "000040")


def test_RN_ROT_001_todo_ativo_tem_linha_no_json_do_mes(rotas):
    """RN-ROT-001 (T-0010), R-20261120-104729 e R-20261120-111303: (1) todo
    cliente ativo, fora interno e 000040, que a rota do mes visita tem ao
    menos uma linha no JSON do mes; (2) nenhum cliente com linha na rota
    some do JSON (fora os de motivo de regra). So contagens."""
    rel = []
    for mes, (cfg, cli, rota, js) in rotas.items():
        no_json = {x["codcli"] for x in js}
        na_rota = {_codcli(r) for r in rota}
        ativos = {f"{c['COD_CLIENTE']}{c['LOJA'].zfill(2)}" for c in cli
                  if _exportavel(cfg, c)}
        por_chave = {c["CHAVE_CLIENTE"]: c for c in cli}
        rota_export = {_codcli(r) for r in rota
                       if _exportavel(cfg, por_chave[r["CHAVE_CLIENTE"]])
                       and r["COD_VENDEDOR"].zfill(6) != "000040"}
        sumidos = rota_export - no_json
        sem_rota = ativos - na_rota
        rel.append(f"{mes}: ativos exportaveis {len(ativos)}; com linha no "
                   f"JSON {len(ativos & no_json)}; sem visita na rota do mes "
                   f"{len(sem_rota)}; sumidos do JSON {len(sumidos)}")
        assert not sumidos, "\n".join(rel)
        assert not sem_rota, "\n".join(rel)
        assert not (no_json - ativos), f"{mes}: linha de nao exportavel"
    print("\n" + "\n".join(rel))


def test_RN_ROT_001_espacamento_maior_que_a_periodicidade(rotas):
    """RN-ROT-001 (T-0010), R-20261120-104729: relatorio (so contagens, sem
    nome) de quem, de 23/11 a 31/12/2026, tem intervalo maior que a
    periodicidade: a 1a visita da janela depois de p dias (sem visita entre
    23/11 e 23/11 + p - 1) ou duas visitas seguidas a mais de p dias.
    Motivo: espacamento da rota do Planner (anterior a T-0010). Nao
    reprova: o gerador da rota nao mudou na T-0010; o teste prende o
    limite de hoje (ninguem ativo fica sem visita na janela)."""
    datas = collections.defaultdict(set)
    per = {}
    for mes, (cfg, cli, rota, js) in rotas.items():
        por_cod = {f"{c['COD_CLIENTE']}{c['LOJA'].zfill(2)}": c for c in cli}
        for x in js:
            d = _d(x["dtproxvisita"])
            if JANELA[0] <= d <= JANELA[1]:
                datas[x["codcli"]].add(d)
            per[x["codcli"]] = int(x["periodicidade"])
        for cod, c in por_cod.items():
            if _exportavel(cfg, c):
                per.setdefault(cod, _periodicidade_esperada(c))
    tot, inicio, meio = (collections.Counter() for _ in range(3))
    sem_visita = collections.Counter()
    for cod, p in per.items():
        tot[p] += 1
        ds = sorted(datas.get(cod, ()))
        if not ds:
            sem_visita[p] += 1
            continue
        if (ds[0] - JANELA[0]).days >= p:
            inicio[p] += 1
        if any((b - a).days > p for a, b in zip(ds, ds[1:])):
            meio[p] += 1
    linhas = [f"Espacamento > periodicidade, 23/11 a 31/12/2026 "
              f"(motivo: {MOTIVO_ESPACAMENTO})",
              f"{'p':>3} {'clientes':>8} {'1a visita > p':>13} "
              f"{'intervalo > p':>13} {'sem visita':>10}"]
    for p in sorted(tot):
        linhas.append(f"{p:>3} {tot[p]:>8} {inicio[p]:>13} {meio[p]:>13} "
                      f"{sem_visita[p]:>10}")
    print("\n" + "\n".join(linhas))
    # p=45 (D/Z, bimestral levado a 45) pode cair so em janeiro; os outros
    # tem de ter visita na janela de 39 dias
    assert not [p for p, n in sem_visita.items() if n and p < 45], \
        "\n".join(linhas)


# --------------------------------------------------------------------------
# 7. remessas antigas (dtfinal 3000) e o pedido de exclusao a Maxima
# --------------------------------------------------------------------------
CNPJ_RE = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"   # CNPJ formatado
ARQUIVO_FICTICIO = "ROTA_PROTHEUS_2026-11_A_PARTIR_09-11_.json"


def _remessa(compromisso, vendedores, dtfinal):
    """Linhas de uma remessa ficticia, com campos a mais que NAO podem
    vazar (nome, fantasia, CNPJ e o nome do arquivo)."""
    out = []
    for i, vend in enumerate(vendedores, 1):
        out.append({
            "codcli": f"{i:06d}01", "codusur": vend,
            "codcompromisso": compromisso,
            "dtproxvisita": "2026-11-10T00:00:00", "periodicidade": "7",
            "sequencia": i, "diasemana": "TERCA", "numsemana": 1,
            "dtinicio": "2000-01-01T00:00:00", "dtfinal": dtfinal,
            "ARQUIVO": ARQUIVO_FICTICIO,
            "NOME_CLIENTE": f"Cliente {i:02d} Razao Ficticia",
            "NOME_FANTASIA": f"Fantasia Ficticia {i:02d}",
            "CNPJ": f"00.000.000/{i:04d}-01",
            "A1_CGC": f"00000000{i:04d}01"})
    return out


def test_RN_ROT_001_remessas_3000_vazio_sem_linha_3000():
    """RN-ROT-001 (T-0010), R-20261120-111303: sem linha com dtfinal
    3000-01-01, remessas_dtfinal_3000 devolve [] (o aviso de exclusao nao
    abre); lista vazia e remessa vazia tambem."""
    curta = _remessa("20261120080000", ["000015", "000016"],
                     "2026-11-16T00:00:00")
    assert pn.remessas_dtfinal_3000([curta, curta]) == []
    assert pn.remessas_dtfinal_3000([]) == []
    assert pn.remessas_dtfinal_3000([[]]) == []


def test_RN_ROT_001_remessas_3000_da_mais_antiga_a_mais_nova():
    """RN-ROT-001 (T-0010), R-20261120-111303: so as remessas com alguma
    linha 3000-01-01, da mais antiga a mais nova, com a data (do
    codcompromisso, dd/mm/aaaa hh:mm) e os codusur distintos e ordenados."""
    nova = _remessa("20261115090000", ["000016", "000015"],
                    "3000-01-01T00:00:00")
    curta = _remessa("20261120080000", ["000015"], "2026-11-26T00:00:00")
    velha = _remessa("20261109143705", ["000016", "000040", "000016"],
                     "3000-01-01T00:00:00")
    velha[0]["dtfinal"] = "2026-11-16T00:00:00"     # basta uma linha 3000
    out = pn.remessas_dtfinal_3000([nova, curta, velha])
    assert out == [
        {"quando": "09/11/2026 14:37", "vendedores": ["000016", "000040"]},
        {"quando": "15/11/2026 09:00", "vendedores": ["000015", "000016"]}]


def test_RN_ROT_001_pedido_exclusao_maxima_periodo_e_vendedores():
    """RN-ROT-001 (T-0010), R-20261120-111303: o pedido cita o periodo
    (1a a ultima remessa 3000) e os codusur distintos, em ordem, uma vez
    cada, e pede a exclusao de TODAS as anteriores com 3000-01-01."""
    import re
    rem = pn.remessas_dtfinal_3000([
        _remessa("20261109143705", ["000016", "000015", "000040"],
                 "3000-01-01T00:00:00"),
        _remessa("20261115090000", ["000015", "000015"],
                 "3000-01-01T00:00:00")])
    texto = pn.pedido_exclusao_maxima(rem)
    assert "Remessas enviadas em: 09/11/2026 14:37 a 15/11/2026 09:00" \
        in texto
    achados = re.findall(r"\b0000(?:15|16|40)\b", texto)
    assert achados == ["000015", "000016", "000040"]
    assert "TODAS" in texto and "3000-01-01" in texto
    um = pn.pedido_exclusao_maxima(rem[:1])
    assert "Remessas enviadas em: 09/11/2026 14:37\n" in um
    assert " a " not in um.splitlines()[1]


def test_RN_ROT_001_pedido_exclusao_maxima_sem_dado_pessoal():
    """RN-ROT-001 (T-0010), R-20261120-111303, regra 6: o pedido nao traz
    nome de arquivo, nome de cliente, fantasia, CNPJ (com ou sem mascara)
    nem codigo de cliente, mesmo que as linhas tragam esses campos."""
    import re
    linhas = _remessa("20261109143705", ["000016", "000015"],
                      "3000-01-01T00:00:00")
    texto = pn.pedido_exclusao_maxima(pn.remessas_dtfinal_3000([linhas]))
    assert isinstance(texto, str) and texto.strip()
    assert ARQUIVO_FICTICIO not in texto and ".json" not in texto
    assert "ROTA_PROTHEUS" not in texto
    assert "Cliente" not in texto and "Ficticia" not in texto
    assert not re.search(CNPJ_RE, texto)
    assert not [x["A1_CGC"] for x in linhas if x["A1_CGC"] in texto]
    assert not [x["codcli"] for x in linhas if x["codcli"] in texto]


def test_RN_ROT_001_aviso_some_depois_da_primeira_remessa_curta():
    """RN-ROT-001 (T-0010), R-20261120-111303: o aviso aparece uma vez so.
    Remessas 3000 de 09/11 e 15/11 e uma curta de 20/11: remessas_a_excluir
    devolve [] (o aviso nao volta depois do 1o envio curto). Sem
    codcompromisso na curta, vale a data do par (mtime do arquivo)."""
    v3000a = _remessa("20261109143705", ["000015", "000016"],
                      "3000-01-01T00:00:00")
    v3000b = _remessa("20261115090000", ["000016"], "3000-01-01T00:00:00")
    curta = _remessa("20261120080000", ["000015", "000016"],
                     "2026-11-26T00:00:00")
    assert pn.remessas_a_excluir(
        [(None, v3000a), (None, v3000b), (None, curta)]) == []
    # curta sem codcompromisso: a data do par (20/11 08:00) faz o corte
    sem_comp = _remessa("", ["000015"], "2026-11-26T00:00:00")
    assert pn.remessas_a_excluir([
        (dt.datetime(2026, 11, 9, 15, 0), v3000a),
        (dt.datetime(2026, 11, 15, 10, 0), v3000b),
        (dt.datetime(2026, 11, 20, 8, 0), sem_comp)]) == []


def test_RN_ROT_001_aviso_aparece_com_remessa_3000_mais_nova():
    """RN-ROT-001 (T-0010), R-20261120-111303: o aviso aparece uma vez so,
    mas volta se surgir remessa 3000 MAIS NOVA que a ultima curta: com
    [3000 de 09/11, curta de 20/11, 3000 de 21/11] so a de 21/11 entra.
    Sem curta nenhuma ([3000 de 09/11]) ela entra: o 1o envio mostra o
    aviso."""
    velha = _remessa("20261109143705", ["000015", "000016"],
                     "3000-01-01T00:00:00")
    curta = _remessa("20261120080000", ["000015"], "2026-11-26T00:00:00")
    nova = _remessa("20261121100000", ["000016", "000015", "000016"],
                    "3000-01-01T00:00:00")
    out = pn.remessas_a_excluir([(None, velha), (None, curta), (None, nova)])
    assert out == [
        {"quando": "21/11/2026 10:00", "vendedores": ["000015", "000016"]}]
    so_velha = pn.remessas_a_excluir([(None, velha)])
    assert so_velha == [
        {"quando": "09/11/2026 14:37", "vendedores": ["000015", "000016"]}]
