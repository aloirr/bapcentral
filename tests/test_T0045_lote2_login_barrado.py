"""T-0045, lote 2 (contrato visitas-nuvem v1.2 §3.1 e §4.5): o `deve_rodar` do cron lendo o `trabalho` da web de
verdade. Sem 2º login no dia (RN-VIS-005) e o pedido sem dia (RN-VIS-002/004).

O site é a `web/app/visitas.Visitas` (fixture `web_visitas` do `tests/conftest.py`, pasta temporária); o cron é o
`nuvem.visitas.agenda.deve_rodar`. Relógio injetado (Manaus), sem rede, sem navegador, sem login real. O que é só da
web (429 da concessão, contadores, tela, textos, a linha NADA_A_FAZER) fica em `web/tests/test_T0045_visitas.py`; o
caminho HTTP do cron (409/423/429 = saída 0), em `tests/test_T0045_cron_visitas.py`.

Todo None é conferido contra o controle: o mesmo `trabalho` sem o `login_barrado` daria o motivo.
Dados 100% fictícios (datas e ids); nenhum nome, CNPJ, telefone ou e-mail.
"""
from datetime import date, datetime, timedelta

import pytest

import visitas_nucleo as vn
from nuvem.visitas import agenda
import visitas_nuvem_fixture as fx

M = vn.FUSO_MANAUS
ONTEM, HOJE, AMANHA = date(2026, 11, 26), date(2026, 11, 27), date(2026, 11, 28)


def _em(d, h, m=0, s=0):
    return datetime(d.year, d.month, d.day, h, m, s, tzinfo=M)


def _fim(codigo="OK", fase=None):
    return {"codigo": codigo, "fase": fase, "dias_ok": [], "dias_faltando": [], "erros_vendedor": 0,
            "duracao_s": 60, "pico_mb": 300, "achados": None, "medidas": None}


@pytest.fixture
def vis(web_visitas, tmp_path):
    """O site pronto para a agenda: diagnóstico ok e agenda ligada em 25/11 (o dia 26 fica aberto)."""
    v = web_visitas.Visitas(tmp_path, token="t" * 40)
    antes = date(2026, 11, 25)
    con = v.conceder({"motivo": "diagnostico", "dias": [fx.ymd(antes - timedelta(days=1))]}, _em(antes, 6))
    v.fim(con["id"], _fim(), _em(antes, 6, 5))
    v.confirmar({"epoca": v.lotes(0)["epoca"], "resultados": [], "fechados_pc": {}}, _em(antes, 6, 10))
    v.agenda(True, _em(antes, 6, 11))
    return v


def _cron(v, quando):
    """O que o cron faria agora: (motivo ou None, o `trabalho` lido do site)."""
    t = v.trabalho(quando)
    return agenda.deve_rodar(quando, t), t


def _concessao_agenda(v, quando):
    return v.conceder({"motivo": "agenda", "dias": [fx.ymd(quando.date() - timedelta(days=1))]}, quando)


# ------------------------------------------------------------------ login barrado: a origem × o cron
_ORIGENS = ["fim_perdido_fase_login", "fim_perdido_sem_fase",
            "MAXIMA_SENHA", "MAXIMA_CONFIRMACAO", "MAXIMA_CAPTCHA", "MAXIMA_BLOQUEIO"]


@pytest.mark.parametrize("origem", _ORIGENS)
def test_RN_VIS_005_login_barrado_com_retomar_e_diagnostico_o_cron_so_volta_amanha(vis, origem):
    """A barra vem do `fim` perdido no login (a concessão vence; sem pausa) ou do `fim` MAXIMA_* (pausa + "Retomar").
    Nos dois, o admin pede diagnóstico no mesmo dia (aceito, decisão do D9): o cron não entra na Máxima até amanhã."""
    assert _cron(vis, _em(HOJE, 6))[0] == "agenda"
    con = _concessao_agenda(vis, _em(HOJE, 6, 0, 5))
    if origem == "fim_perdido_fase_login":
        vis.progresso(con["id"], {"fase": "login"}, _em(HOJE, 6, 0, 10))
    elif origem.startswith("MAXIMA_"):
        vis.fim(con["id"], _fim(origem, "login"), _em(HOJE, 6, 1))
    motivo, t = _cron(vis, _em(HOJE, 6, 30))                          # a concessão de 10 min já venceu
    assert motivo is None
    assert t["login_barrado"]["dia"] == fx.ymd(HOJE)
    if origem.startswith("MAXIMA_"):
        assert agenda.deve_rodar(_em(HOJE, 6, 30), dict(t, login_barrado=None)) is None   # a pausa também barra
        vis.retomar("", "admin", _em(HOJE, 8))
    else:
        assert agenda.deve_rodar(_em(HOJE, 6, 30), dict(t, login_barrado=None)) == "agenda"   # 2ª tentativa
    vis.diagnostico(_em(HOJE, 8, 1))
    for h, m in ((8, 5), (12, 0), (21, 59)):
        motivo, t = _cron(vis, _em(HOJE, h, m))
        assert t["pausado"] is None and t["diagnostico"]["estado"] == "pendente"
        assert motivo is None, (origem, h, m)                            # passo 1 vence o 4
        assert agenda.deve_rodar(_em(HOJE, h, m), dict(t, login_barrado=None)) == "diagnostico"   # controle
    motivo, t = _cron(vis, _em(AMANHA, 6))                              # no dia seguinte, sem clique
    assert t["login_barrado"] is None and motivo == "diagnostico"


def test_RN_VIS_005_vencida_depois_do_login_nao_barra(vis):
    """Login confirmado (a rodada passou da fase `login`): a concessão vencida não barra; às 06h30 a agenda tenta de novo."""
    con = _concessao_agenda(vis, _em(HOJE, 6, 0, 5))
    vis.progresso(con["id"], {"fase": "login"}, _em(HOJE, 6, 0, 10))
    vis.progresso(con["id"], {"fase": "grade", "dia": fx.ymd(ONTEM), "feitos": 1, "total": 3}, _em(HOJE, 6, 2))
    motivo, t = _cron(vis, _em(HOJE, 6, 30))
    assert t["login_barrado"] is None and motivo == "agenda"


def test_RN_VIS_005_concessao_que_vence_depois_da_meia_noite_nao_barra_o_dia_seguinte(vis):
    """A barra fica no dia de Manaus do início (27/11, testado na web); às 06h00 de 28 o cron roda."""
    con = vis.conceder({"motivo": "pedido", "dias": [fx.ymd(ONTEM)]}, _em(HOJE, 21, 55))
    vis.progresso(con["id"], {"fase": "login"}, _em(HOJE, 21, 55, 10))
    motivo, t = _cron(vis, _em(AMANHA, 6))
    assert t["login_barrado"] is None and motivo == "agenda"


# ------------------------------------------------------------------ pedido sem dia: o cron não trava nem gasta login
def test_RN_VIS_002_pedido_so_com_dias_fechados_nao_chega_ao_cron(vis):
    pc = {fx.ymd(ONTEM): "2026-11-27T06:40:00-04:00", "20261125": "2026-11-26T07:00:00-04:00"}
    vis.confirmar({"epoca": vis.lotes(0)["epoca"], "resultados": [], "fechados_pc": pc}, _em(HOJE, 6, 45))
    vis.pedir("2026-11-25", "2026-11-26", False, "gerente", _em(HOJE, 9))
    motivo, t = _cron(vis, _em(HOJE, 9, 5))
    assert t["pedido"] is None and motivo is None                         # 25 e 26 fechados: nada a baixar
    # com `refazer`, os mesmos dias entram e o cron baixa os dois
    vis.pedir("2026-11-25", "2026-11-26", True, "admin", _em(HOJE, 9, 10))
    motivo, t = _cron(vis, _em(HOJE, 9, 15))
    assert motivo == "pedido" and agenda.dias_da_rodada("pedido", t, HOJE) == [date(2026, 11, 25), ONTEM]


def test_RN_VIS_002_pedido_que_o_pc_fecha_depois_sai_antes_do_cron(vis):
    vis.pedir("2026-11-25", "2026-11-26", False, "gerente", _em(HOJE, 5, 50))
    motivo, t = _cron(vis, _em(HOJE, 5, 55))
    assert t["pedido"]["de"] == "20261125" and motivo is None             # antes da JANELA
    assert agenda.deve_rodar(_em(HOJE, 6), t) == "pedido"                 # controle: às 06h00, com este trabalho
    pc = {fx.ymd(ONTEM): "2026-11-27T05:58:00-04:00", "20261125": "2026-11-26T07:00:00-04:00"}
    vis.confirmar({"epoca": vis.lotes(0)["epoca"], "resultados": [], "fechados_pc": pc}, _em(HOJE, 5, 58))
    motivo, t = _cron(vis, _em(HOJE, 6))
    assert t["pedido"] is None and motivo is None
