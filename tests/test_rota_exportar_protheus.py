"""T-0010 - exportacao da rota para a Maxima (layout Protheus ERP_MXSROTACLI).

Decisoes R-20261120-102022 e R-20261120-104729 (20/11/2026):
- fica fora do JSON o cliente INTERNO, identificado pelo nome como no
  meta_nucleo.e_cliente_interno (BAP AUTOPARTS / FRW / PMZ DISTRIBUIDORA)
  - RN-GER-004 - e a conta 000040 (RN-GER-005);
- o cliente VISITA_SEMANAL sai com periodicidade 7;
- dtfinal = proxima visita + periodicidade - 1 dia.

Nao ha RN de rota numerada para isso em docs/produto/03-regras.md (a secao
RN-ROT so tem itens sem numero): os testes usam RN_ROTA_011 (numero livre).

Carteira 100% ficticia: codigos 999xxx, nomes inventados, sem CNPJ, telefone
nem e-mail. "BAP AUTOPARTS LTDA" e o nome da propria empresa (o caso interno).
"""
import datetime as dt
from types import SimpleNamespace

import planner_nucleo
import relatorios_nucleo

# segunda-feira de dezembro/2026 (nao e o 1o sabado, que e deposito)
SEGUNDA = dt.date(2026, 12, 7)
VENDEDOR = "999900 - VENDEDOR FICTICIO"


def _visita(cod, nome, fantasia="", semanal="", curva="C", ordem=1):
    """Uma visita no formato de ctx.base["visitas"] (o que o Farol
    Roteirizacao recebe do bap_dados)."""
    return {"cod": cod, "loja": "01", "cod_cliente": cod, "loja_cru": "01",
            "cod_vend": "999900", "vendedor": VENDEDOR, "data": SEGUNDA,
            "ordem": ordem, "chave": f"{cod}-01", "curva": curva,
            "semana": "Semana 2", "nome": nome, "fantasia": fantasia,
            "visita_semanal": semanal}


def _carteira():
    return [
        _visita("999001", "BAP AUTOPARTS LTDA", "BAP FICTICIO", ordem=1),
        _visita("999002", "AUTOPECAS FICTICIA SEMANAL LTDA",
                "FICTICIA SEMANAL", semanal="SIM", curva="C", ordem=2),
        _visita("999003", "AUTOPECAS FICTICIA NORMAL LTDA",
                "FICTICIA NORMAL", semanal="", curva="C", ordem=3),
    ]


def _ctx(visitas):
    """O ctx minimo que _exportar_protheus_da_rota usa: so ctx.base."""
    return SimpleNamespace(base={"visitas": visitas, "clientes": []})


def _por_codcli(linhas):
    return {x["codcli"]: x for x in linhas}


def test_RN_ROTA_011_repassa_nome_fantasia_e_visita_semanal(monkeypatch):
    capturado = {}

    def falso(cfg, clientes, chaves=None, compromisso=None, linhas=None):
        capturado["linhas"] = linhas
        return []

    monkeypatch.setattr(planner_nucleo, "linhas_protheus", falso)
    relatorios_nucleo._exportar_protheus_da_rota(_ctx(_carteira()))()

    rota = {r["COD_CLIENTE"]: r for r in capturado["linhas"]}
    assert set(rota) == {"999001", "999002", "999003"}
    assert rota["999001"].get("NOME_CLIENTE") == "BAP AUTOPARTS LTDA"
    assert rota["999001"].get("NOME_FANTASIA") == "BAP FICTICIO"
    assert rota["999002"].get("NOME_CLIENTE") == \
        "AUTOPECAS FICTICIA SEMANAL LTDA"
    assert rota["999002"].get("NOME_FANTASIA") == "FICTICIA SEMANAL"
    assert rota["999002"].get("VISITA_SEMANAL") == "SIM"
    assert rota["999003"].get("VISITA_SEMANAL") == ""


def test_RN_ROTA_011_interno_pelo_nome_fica_fora():
    saida = relatorios_nucleo._exportar_protheus_da_rota(_ctx(_carteira()))()
    codcli = _por_codcli(saida)
    # RN-GER-004: o interno sai pelo NOME, mesmo com clientes=[] (sem cadastro)
    assert "99900101" not in codcli
    # os outros dois seguem no arquivo
    assert set(codcli) == {"99900201", "99900301"}


def test_RN_ROTA_011_visita_semanal_sai_com_7():
    saida = relatorios_nucleo._exportar_protheus_da_rota(_ctx(_carteira()))()
    codcli = _por_codcli(saida)
    semanal, normal = codcli["99900201"], codcli["99900301"]
    # semanal: 7 dias, mesmo sendo curva C (que daria 30)
    assert semanal["periodicidade"] == "7"
    assert semanal["dtproxvisita"] == "2026-12-07T00:00:00"
    # dtfinal = proxima visita + periodicidade - 1 = 07/12 + 6
    assert semanal["dtfinal"] == "2026-12-13T00:00:00"
    # normal curva C: 30 dias, dtfinal = 07/12 + 29
    assert normal["periodicidade"] == "30"
    assert normal["dtfinal"] == "2027-01-05T00:00:00"
