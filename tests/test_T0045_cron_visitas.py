"""T-0045 (ADR 0004 §8 e §9, item 9): testes do cron `bap-visitas-maxima` (`nuvem/visitas/agenda.py` e
`nuvem/visitas/rodar.py`).

Contrato `.coord/contratos/visitas-nuvem.md`: §1 (segredos e configuração), §2 (constantes), §3.1 (`deve_rodar`,
os 9 passos na ordem), §3.2 (concessão), §3.3 (progresso), §3.4 (lote do dia), §3.5 (`fim`), §3.6 (o Excel
filtrado), §5 (códigos e saída do processo), §5.1 (uma tentativa só de login) e §6 (diagnóstico).

Regras: RN-VIS-002 (dias fechados), RN-VIS-004 (concessão), RN-VIS-005 (login e pausa), RN-VIS-006 (retentativa),
RN-VIS-007 (dado pessoal) e RN-VIS-008 (teto do dia).

Tudo com dublês: sem rede (o `abrir` do `Site` é um site de mentira), sem navegador (o `Robo` vem da
`fabrica_robo`), sem login real, sem esperar (a `pausa` e o relógio são injetados). Dados 100% fictícios
(`tests/visitas_nuvem_fixture.py`). O que o robô do PC e a web já cobrem fica nos outros testes da T-0045; a
paridade das constantes cron × web fica em `tests/test_T0045_paridade_visitas_web.py`.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

import visitas_maxima as vm
import visitas_nucleo as vn
from nuvem.visitas import agenda, rodar
from tests import visitas_nuvem_fixture as fx

RAIZ = Path(__file__).resolve().parent.parent
M = agenda.MANAUS
HOJE = date(2026, 11, 27)
ONTEM = HOJE - timedelta(days=1)
RID = "R20261127T060012"
USUARIO = "usuario-ficticio-cron"
SENHA = "senha-ficticia-cron-123"
HOST = "bap-central-ficticio:10000"


def _agora(h=6, m=5, s=0, us=0, dia=HOJE):
    return datetime(dia.year, dia.month, dia.day, h, m, s, us, tzinfo=M)


def _ymd(d):
    return f"{d:%Y%m%d}"


def _trab(**k):
    """Um `trabalho` (§3.1) com a agenda ligada, o diagnóstico ok e nada feito hoje."""
    t = {"versao": 1, "agora": _agora().isoformat(), "agenda": "ligada",
         "diagnostico": {"estado": "ok", "em": None, "codigo": None}, "pausado": None, "pedido": None,
         "indice": {}, "tentativas_hoje": {"dia": _ymd(HOJE), "total": 0, "por_motivo": {}},
         "falhas_seguidas": {"fase": None, "n": 0}, "fechados_pc_em": None, "rodada_ativa": None}
    t.update(k)
    return t


def _tent(total=None, **por):
    """tentativas_hoje: por motivo, (n, codigo)."""
    pm = {m: {"n": n, "ultima_em": _agora(6, 0).isoformat(), "codigo": c} for m, (n, c) in por.items()}
    return {"dia": _ymd(HOJE), "total": sum(v["n"] for v in pm.values()) if total is None else total,
            "por_motivo": pm}


def _fechado(d, origem="nuvem", erros=0, refeito=False):
    return {"baixado_em": f"{d + timedelta(days=1):%Y-%m-%d}T06:07:00-04:00", "origem": origem,
            "erros_vendedor": erros, "refeito": refeito}


# =====================================================================================================================
# agenda.deve_rodar: os 9 passos do §3.1, na ordem (RN-VIS-002, 004, 005, 006, 008)
# =====================================================================================================================
def test_RN_VIS_005_passo_1_pausado_vence_tudo():
    t = _trab(pausado={"codigo": "MAXIMA_SENHA", "desde": _agora(5).isoformat()},
              diagnostico={"estado": "pendente"}, pedido={"id": "P1", "de": _ymd(ONTEM), "ate": _ymd(ONTEM),
                                                         "rodadas": 0})
    assert agenda.deve_rodar(_agora(), t) is None


@pytest.mark.parametrize("h,m,s,us,roda", [
    (5, 59, 59, 999999, False), (6, 0, 0, 0, True), (12, 0, 0, 0, True), (21, 59, 0, 0, True),
    (21, 59, 59, 0, True), (22, 0, 0, 0, False), (23, 30, 0, 0, False), (0, 0, 0, 0, False),
])
def test_RN_VIS_008_passo_2_janela_06h00_a_21h59(h, m, s, us, roda):
    """Fora da JANELA (06h00 a 21h59 de Manaus) o cron sai, mesmo com diagnóstico pendente ou pedido."""
    for t in (_trab(), _trab(diagnostico={"estado": "pendente"}),
              _trab(pedido={"id": "P1", "de": _ymd(ONTEM), "ate": _ymd(ONTEM), "rodadas": 0})):
        r = agenda.deve_rodar(_agora(h, m, s, us), t)
        assert (r is not None) is roda, (h, m, s, us, t["diagnostico"], t["pedido"])


@pytest.mark.xfail(strict=False, reason="D5 (T-0045): transição até o #208 entrar; sai no #212")
def test_RN_VIS_008_passo_2_janela_vale_o_minuto_21h59_inteiro():
    """A JANELA vai até 21h59 (contrato §2): 21:59:59,5 ainda é 21h59."""
    assert agenda.deve_rodar(_agora(21, 59, 59, 500000), _trab()) == "agenda"


def test_RN_VIS_008_passo_2_janela_em_manaus_mesmo_com_relogio_em_utc():
    """10h00 UTC = 06h00 de Manaus (o `schedule` do Render é em UTC); 02h00 UTC = 22h00 da véspera em Manaus."""
    from datetime import timezone
    assert agenda.deve_rodar(datetime(2026, 11, 27, 10, 0, tzinfo=timezone.utc), _trab()) == "agenda"
    assert agenda.deve_rodar(datetime(2026, 11, 28, 2, 0, tzinfo=timezone.utc), _trab()) is None
    assert agenda.deve_rodar(datetime(2026, 11, 27, 9, 59, tzinfo=timezone.utc), _trab()) is None


@pytest.mark.parametrize("total,roda", [(7, True), (8, False), (9, False)])
def test_RN_VIS_008_passo_3_logins_dia_max_trava_antes_do_diagnostico(total, roda):
    t = _trab(diagnostico={"estado": "pendente"}, tentativas_hoje=_tent(total=total))
    assert (agenda.deve_rodar(_agora(), t) == "diagnostico") is roda
    t = _trab(tentativas_hoje=_tent(total=total))
    assert (agenda.deve_rodar(_agora(), t) == "agenda") is roda


def test_RN_VIS_008_passo_3_a_soma_trava_mesmo_com_cada_motivo_abaixo_do_proprio_teto():
    t = _trab(tentativas_hoje=_tent(agenda=(3, "MAXIMA_FORA"), pedido=(2, "OK"), diagnostico=(1, "OK"),
                                    retentativa=(0, None), total=8))
    assert agenda.deve_rodar(_agora(9), t) is None


def test_RN_VIS_004_passo_4_diagnostico_pendente_vem_antes_de_agenda_desligada_e_pedido():
    t = _trab(agenda="desligada", diagnostico={"estado": "pendente"},
              pedido={"id": "P1", "de": _ymd(ONTEM), "ate": _ymd(ONTEM), "rodadas": 0})
    assert agenda.deve_rodar(_agora(), t) == "diagnostico"


@pytest.mark.parametrize("n,esperado", [(0, "diagnostico"), (1, "diagnostico"), (2, None)])
def test_RN_VIS_008_passo_4_diagnostico_no_teto_cai_no_passo_5(n, esperado):
    """Diagnóstico pendente no teto (2): o passo 5 barra (diagnóstico != ok), nada de agenda nem pedido."""
    t = _trab(diagnostico={"estado": "pendente"}, tentativas_hoje=_tent(diagnostico=(n, "MAXIMA_FORA")),
              pedido={"id": "P1", "de": _ymd(ONTEM), "ate": _ymd(ONTEM), "rodadas": 0})
    assert agenda.deve_rodar(_agora(), t) == esperado


@pytest.mark.parametrize("trab", [
    _trab(agenda="desligada"),
    _trab(agenda="desligada", pedido={"id": "P1", "de": _ymd(ONTEM), "ate": _ymd(ONTEM), "rodadas": 0}),
    _trab(diagnostico={"estado": "falhou"}),
    _trab(diagnostico={"estado": "falhou"}, pedido={"id": "P1", "de": _ymd(ONTEM), "ate": _ymd(ONTEM),
                                                    "rodadas": 0}),
    _trab(diagnostico={}),
    _trab(indice={_ymd(HOJE - timedelta(days=3)): _fechado(HOJE - timedelta(days=3), erros=2)},
          agenda="desligada"),
])
def test_RN_VIS_004_passo_5_agenda_desligada_ou_diagnostico_nao_ok_nada_roda(trab):
    """O pedido do botão e a retentativa também esperam (§3.1, passo 5)."""
    assert agenda.deve_rodar(_agora(9), trab) is None


@pytest.mark.parametrize("rodadas,n,esperado", [
    (0, 0, "pedido"), (2, 2, "pedido"), (3, 0, "agenda"), (0, 3, "agenda"),
])
def test_RN_VIS_008_passo_6_pedido_ate_3_rodadas_e_abaixo_do_teto(rodadas, n, esperado):
    """Pedido vem antes da agenda; com PEDIDO_MAX_RODADAS ou o teto do pedido, cai para a agenda (ontem aberto)."""
    t = _trab(pedido={"id": "P1", "de": _ymd(ONTEM), "ate": _ymd(HOJE), "rodadas": rodadas, "refazer": False},
              tentativas_hoje=_tent(pedido=(n, "PARCIAL_TEMPO")))
    assert agenda.deve_rodar(_agora(9), t) == esperado


@pytest.mark.parametrize("hora_,n,codigo,esperado", [
    ((6, 0), 0, None, "agenda"),
    ((6, 29), 1, "MAXIMA_FORA", None), ((6, 30), 1, "MAXIMA_FORA", "agenda"),
    ((6, 59), 2, "TELA_MUDOU", None), ((7, 0), 2, "TELA_MUDOU", "agenda"),
    ((7, 29), 3, "NAVEGADOR_FALHOU", None), ((7, 30), 3, "NAVEGADOR_FALHOU", "agenda"),
    ((21, 0), 3, "ERRO_INTERNO", "agenda"),
    ((9, 0), 4, "MAXIMA_FORA", None),                      # 4 = teto da agenda
    ((9, 0), 1, "MAXIMA_SENHA", None), ((9, 0), 1, "DADO_PESSOAL", None), ((9, 0), 1, "OK", None),
    ((9, 0), 1, "DESCOMPRESSAO_TETO", None),               # fora de NOVA_TENTATIVA (§5)
    ((9, 0), 1, "PARCIAL_VENDEDOR", None), ((9, 0), 1, None, None),
])
def test_RN_VIS_008_passo_7_agenda_e_retentativas_so_com_codigo_em_nova_tentativa(hora_, n, codigo, esperado):
    t = _trab(tentativas_hoje=_tent(agenda=(n, codigo)))
    assert agenda.deve_rodar(_agora(*hora_), t) == esperado


@pytest.mark.parametrize("codigo", agenda.NOVA_TENTATIVA)
def test_RN_VIS_008_passo_7_todo_codigo_de_nova_tentativa_volta_as_06h30(codigo):
    t = _trab(tentativas_hoje=_tent(agenda=(1, codigo)))
    assert agenda.deve_rodar(_agora(6, 30), t) == "agenda"
    assert agenda.deve_rodar(_agora(6, 29, 59), t) is None


def test_RN_VIS_002_passo_7_ontem_fechado_nao_roda_a_agenda():
    """Ontem fechado no índice (pela nuvem ou pelo PC) = sem agenda."""
    for origem in ("nuvem", "pc"):
        t = _trab(indice={_ymd(ONTEM): _fechado(ONTEM, origem)})
        assert agenda.deve_rodar(_agora(6, 0), t) is None
    # baixado no próprio dia (23h00) não fecha: a agenda roda
    t = _trab(indice={_ymd(ONTEM): {"baixado_em": f"{ONTEM:%Y-%m-%d}T23:00:00-04:00", "origem": "pc"}})
    assert agenda.deve_rodar(_agora(6, 0), t) == "agenda"


def test_RN_VIS_006_passo_8_retentativa_uma_vez_nos_ultimos_7_dias():
    ind = {_ymd(ONTEM): _fechado(ONTEM)}
    d3 = HOJE - timedelta(days=3)
    t = _trab(indice={**ind, _ymd(d3): _fechado(d3, erros=2)})
    assert agenda.deve_rodar(_agora(9), t) == "retentativa"
    # já refeito, origem pc, 8 dias atrás, ou retentativa no teto (1): nada
    for item, dia in ((_fechado(d3, erros=2, refeito=True), d3), (_fechado(d3, "pc", erros=2), d3),
                      (_fechado(HOJE - timedelta(days=8), erros=2), HOJE - timedelta(days=8))):
        assert agenda.deve_rodar(_agora(9), _trab(indice={**ind, _ymd(dia): item})) is None
    t = _trab(indice={**ind, _ymd(d3): _fechado(d3, erros=2)}, tentativas_hoje=_tent(retentativa=(1, "OK")))
    assert agenda.deve_rodar(_agora(9), t) is None


def test_RN_VIS_002_passo_6_pedido_sem_dia_a_baixar_segue_para_7_e_8():
    """Pedido só com dias fechados (sem `refazer`): não trava a fila; ontem aberto = agenda; senão, retentativa."""
    d3, d2 = HOJE - timedelta(days=3), HOJE - timedelta(days=2)
    ped = {"id": "P1", "de": _ymd(d3), "ate": _ymd(d2), "refazer": False, "rodadas": 0}
    ind = {_ymd(d3): _fechado(d3), _ymd(d2): _fechado(d2)}
    assert agenda.deve_rodar(_agora(6, 10), _trab(pedido=ped, indice=ind)) == "agenda"
    ind2 = {**ind, _ymd(ONTEM): _fechado(ONTEM), _ymd(d3): _fechado(d3, erros=1)}
    assert agenda.deve_rodar(_agora(9), _trab(pedido=ped, indice=ind2)) == "retentativa"
    assert agenda.deve_rodar(_agora(9), _trab(pedido={**ped, "refazer": True}, indice=ind2)) == "pedido"


def test_RN_VIS_006_passo_7_vem_antes_do_8_e_passo_9_e_none():
    d3 = HOJE - timedelta(days=3)
    t = _trab(indice={_ymd(d3): _fechado(d3, erros=1)})          # ontem aberto e d3 pendente
    assert agenda.deve_rodar(_agora(6), t) == "agenda"
    assert agenda.deve_rodar(_agora(9), _trab(indice={_ymd(ONTEM): _fechado(ONTEM)})) is None    # passo 9


# =====================================================================================================================
# agenda.dias_da_rodada (§3.1 e §3.2; RN-VIS-002 e 006)
# =====================================================================================================================
def test_RN_VIS_002_dias_da_agenda_e_do_diagnostico_sao_ontem_e_nunca_hoje():
    assert agenda.dias_da_rodada("agenda", _trab(), HOJE) == [ONTEM]
    assert agenda.dias_da_rodada("agenda", _trab(indice={_ymd(ONTEM): _fechado(ONTEM)}), HOJE) == []
    assert agenda.dias_da_rodada("diagnostico", _trab(indice={_ymd(ONTEM): _fechado(ONTEM)}), HOJE) == [ONTEM]
    assert agenda.dias_da_rodada("outro", _trab(), HOJE) == []


def test_RN_VIS_002_hoje_so_entra_pelo_pedido_e_fica_aberto():
    ind = {_ymd(HOJE): {"baixado_em": _agora(6, 10).isoformat(), "origem": "nuvem"},
           _ymd(ONTEM): _fechado(ONTEM)}
    ped = {"id": "P1", "de": _ymd(ONTEM), "ate": _ymd(HOJE + timedelta(days=3)), "refazer": False, "rodadas": 0}
    assert agenda.dias_da_rodada("pedido", _trab(indice=ind, pedido=ped), HOJE) == [HOJE]
    assert HOJE not in agenda.dias_da_rodada("agenda", _trab(indice=ind), HOJE)


def test_RN_VIS_002_pedido_ate_pedido_max_dias_e_datas_tortas():
    de = HOJE - timedelta(days=10)
    ped = {"id": "P1", "de": _ymd(de), "ate": _ymd(HOJE), "refazer": False, "rodadas": 0}
    dias = agenda.dias_da_rodada("pedido", _trab(pedido=ped), HOJE)
    assert dias == [de + timedelta(days=k) for k in range(7)]
    for de_, ate_ in (("2026-11-20", _ymd(HOJE)), (_ymd(HOJE), _ymd(ONTEM)), (None, _ymd(HOJE)), ("x", "y")):
        ped = {"id": "P1", "de": de_, "ate": ate_, "rodadas": 0}
        assert agenda.dias_da_rodada("pedido", _trab(pedido=ped), HOJE) == [], (de_, ate_)


def test_RN_VIS_002_pedido_refazer_nao_repete_o_dia_ja_refeito_depois_do_pedido():
    d1, d2, d3 = HOJE - timedelta(days=3), HOJE - timedelta(days=2), ONTEM
    pedido_em = _agora(9, 15)
    ind = {_ymd(d1): {"baixado_em": _agora(9, 20).isoformat(), "origem": "nuvem"},      # refeito nesta leva
           _ymd(d2): {"baixado_em": _agora(9, 20).isoformat(), "origem": "pc"},         # PC: não conta
           _ymd(d3): {"baixado_em": _agora(6, 7).isoformat(), "origem": "nuvem"}}       # antes do pedido
    ped = {"id": "P1", "de": _ymd(d1), "ate": _ymd(d3), "refazer": True, "pedido_em": pedido_em.isoformat(),
           "rodadas": 1}
    assert agenda.dias_da_rodada("pedido", _trab(indice=ind, pedido=ped), HOJE) == [d2, d3]
    ped["refazer"] = False                                     # sem refazer: os fechados saem
    assert agenda.dias_da_rodada("pedido", _trab(indice=ind, pedido=ped), HOJE) == []


def test_RN_VIS_006_dias_da_retentativa_sao_os_pendentes_em_ordem():
    d5, d2 = HOJE - timedelta(days=5), HOJE - timedelta(days=2)
    ind = {_ymd(d2): _fechado(d2, erros=1), _ymd(d5): _fechado(d5, erros=3),
           _ymd(ONTEM): _fechado(ONTEM, erros=0)}
    assert agenda.dias_da_rodada("retentativa", _trab(indice=ind), HOJE) == [d5, d2]


# =====================================================================================================================
# importar não faz nada (§1; desenho §3: a trava do Dockerfile importa o rodar.py)
# =====================================================================================================================
_IMPORTA = r"""
import os, signal, socket, sys, threading
sys.path.insert(0, sys.argv[1])
lidas = []
class Espiao(dict):
    def __getitem__(self, k): lidas.append(k); return dict.__getitem__(self, k)
    def get(self, k, d=None): lidas.append(k); return dict.get(self, k, d)
    def pop(self, k, *d): lidas.append(k); return dict.pop(self, k, *d)
    def __contains__(self, k): lidas.append(k); return dict.__contains__(self, k)
os.environ = Espiao(os.environ)
def sem_rede(*a, **k): raise AssertionError("rede no import")
socket.socket.connect = sem_rede; socket.socket.connect_ex = sem_rede; socket.create_connection = sem_rede
socket.getaddrinfo = sem_rede
fios = threading.active_count()
import nuvem.visitas.rodar, nuvem.visitas.agenda
assert threading.active_count() == fios, "thread no import"
assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL, "sinal no import"
assert not [m for m in sys.modules if m == "playwright" or m.startswith("playwright.")], "playwright no import"
SEGREDOS = ("BAP_MAXIMA_USUARIO", "BAP_MAXIMA_SENHA", "BAP_VISITAS_TOKEN", "BAP_WEB_HOSTPORT")
assert not [k for k in lidas if k in SEGREDOS], ("leu", sorted(set(lidas)))
# só as URLs da Máxima (BAP_MAXIMA_LOGIN e BAP_MAXIMA_PWA, sem segredo) podem ser lidas no import do visitas_maxima
assert {k for k in lidas if str(k).startswith("BAP_")} <= {"BAP_MAXIMA_LOGIN", "BAP_MAXIMA_PWA"}, sorted(set(lidas))
assert os.environ.get("BAP_MAXIMA_SENHA") == "senha-ficticia-import"
print("ok")
"""


def test_RN_VIS_005_importar_o_rodar_nao_faz_nada(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BAP_", "PYTHON"))}
    env.update({"BAP_MAXIMA_USUARIO": "usuario-ficticio-import", "BAP_MAXIMA_SENHA": "senha-ficticia-import",
                "BAP_VISITAS_TOKEN": "t" * 40, "BAP_WEB_HOSTPORT": "x.invalid:1"})
    r = subprocess.run([sys.executable, "-I", "-B", "-c", _IMPORTA, str(RAIZ)], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr[-2000:]


# =====================================================================================================================
# dublês: o site, o Robo e o relógio
# =====================================================================================================================
class _Resp:
    def __init__(self, status, corpo):
        self.status, self._b = status, corpo

    def read(self):
        return self._b

    def close(self):
        pass


class SiteCron:
    """O `bap-central` de mentira, só com as rotas do cron (§3). `respostas[(metodo, rota)]` = (status, corpo)
    ou uma lista (uma por chamada) ou "fora" (falha de rede). Rota: trabalho, rodada, progresso, dia, fim."""

    def __init__(self, trab, **respostas):
        self.trabalho = trab
        self.resp = {"trabalho": (200, trab), "rodada": (201, {"id": RID, "vence_em": _agora(6, 15).isoformat()}),
                     "progresso": (200, {"vence_em": _agora(6, 15).isoformat()}),
                     "dia": (200, {"ok": True, "seq": 1, "arquivos": 0}), "fim": (200, {"ok": True, "pausado": False})}
        self.resp.update(respostas)
        self.chamadas = []

    @staticmethod
    def rota(caminho):
        if caminho == "/api/visitas/trabalho":
            return "trabalho"
        if caminho == "/api/visitas/rodada":
            return "rodada"
        m = re.match(r"^/api/visitas/rodada/(R\d{8}T\d{6})/(progresso|fim|dia/\d{8})$", caminho)
        assert m, caminho
        return m.group(2).split("/")[0]

    def abrir(self, req, timeout):
        u = urlparse(req.full_url)
        rota = self.rota(u.path)
        cab = {k.lower(): v for k, v in req.header_items()}
        self.chamadas.append(SimpleNamespace(metodo=req.get_method(), caminho=u.path, rota=rota, cab=cab,
                                             dados=req.data, timeout=timeout, url=req.full_url))
        r = self.resp[rota]
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if r == "fora":
            raise urllib.error.URLError("sem rede (dublê)")
        status, corpo = r
        dados = json.dumps(corpo).encode()
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "x", {}, io.BytesIO(dados))
        return _Resp(status, dados)

    def de(self, rota):
        return [c for c in self.chamadas if c.rota == rota]

    @staticmethod
    def json(c):
        d = c.dados
        if c.cab.get("content-encoding") == "gzip":
            d = gzip.decompress(d)
        return json.loads(d.decode("utf-8"))

    def fim(self):
        f = self.de("fim")
        assert len(f) == 1, [c.caminho for c in self.chamadas]
        return self.json(f[0])


class Relogio:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class RoboFalso:
    """O `visitas_maxima.Robo` de mentira: a mesma assinatura que o `rodar.py` usa. `plano[dia]` = lista de
    vendedores: "ok" (Excel limpo), "achado" (Excel com e-mail no ENDERECO) ou "erro" (vendedor perdido)."""

    def __init__(self, cfg, raiz, log, parar=None, **kw):
        self.cfg, self.raiz, self.log, self.parar, self.kw = cfg, Path(raiz), log, parar, kw
        self.ao_fase, self.ao_fechar_dia = kw["ao_fase"], kw["ao_fechar_dia"]
        self.codigo = self.fase_erro = None
        self.fase = None
        self.equipe = {"filiais": {"1": "FILIAL FICTICIA"}, "supervisores": {}, "representantes": {}}
        self.page = SimpleNamespace(context=SimpleNamespace(browser=SimpleNamespace(version="131.0.6778.33")))
        self.chamadas = []
        cfg.setdefault("robos", []).append(self)

    def entrar(self, u, s):
        self.chamadas.append(("entrar", u, s))
        self._fase("login")
        if self.cfg.get("login_erro"):
            raise vm.ErroRobo("recusado (dublê)", self.cfg["login_erro"], "login")

    def _fase(self, fase, dia=None, feitos=None, total=None):
        self.fase = fase
        self.ao_fase(fase, dia, feitos, total)
        if self.parar.is_set():
            raise vm.Cancelado()

    def rodar(self, u, s, dias, meses):
        self.chamadas.append(("rodar", list(dias), set(meses)))
        if self.cfg.get("log_segredo"):
            self.log(f"evento=teste usuario={u} senha={s} url=https://maxima.exemplo.test/x?PWE=abc123&y=1")
        self._fase("inicio")
        self.entrar(u, s)
        for f in ("maxgestao", "filtros"):
            self._fase(f)
        for d in dias:
            self._fase("grade", _ymd(d))
            ok, erro = [], []
            for i, tipo in enumerate(self.cfg.get("plano", {}).get(d, ["ok"])):
                nome = f"VENDEDOR FICTICIO {i}"
                if tipo == "erro":
                    erro.append((nome, "TimeoutError"))
                else:
                    arq = vm.arquivo_analitico(self.raiz, nome, d, datetime(2026, 11, 27, 6, 7 + i))
                    fx.espelho_xlsx(arq, d, cod=f"90000{i}", nome=nome)
                    if tipo == "achado":
                        _sujar(arq)
                    self.cfg.setdefault("originais", {})[arq.name] = arq.read_bytes()
                    ok.append((vm.nome_limpo(nome), arq))
                self.cfg.get("ao_vendedor", lambda *_: None)(d, i)
                self._fase("grade", _ymd(d), feitos=i + 1, total=len(self.cfg.get("plano", {}).get(d, ["ok"])))
            if self.cfg.get("erro_no_dia") == d:
                raise self.cfg["erro_excecao"]
            self.cfg.get("antes_de_fechar", lambda *_: None)(d)
            self.ao_fechar_dia(d, {"ok": ok, "erro": erro, "extras": {"VENDEDOR FICTICIO 0": {"gps": True,
                                                                                            "versao": "9.9"}},
                                   "vendedores": len(ok) + len(erro), "linhas": len(ok)})
            if self.parar.is_set():
                raise vm.Cancelado()
        return {}


def _sujar(arq):
    """Um e-mail fictício no ENDERECO (coluna que a limpeza do §3.6 não trata): a varredura acha."""
    from openpyxl import load_workbook
    wb = load_workbook(arq)
    ws = wb.active
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("RUA FICTICIA"):
                c.value = "RUA FICTICIA 1 contato fulano@exemplo.test"
                wb.save(arq)
                return
    raise AssertionError("fixture sem ENDERECO")


def _env(**k):
    e = {"BAP_MAXIMA_USUARIO": USUARIO, "BAP_MAXIMA_SENHA": SENHA, "BAP_VISITAS_TOKEN": fx.TOKEN_CRON,
         "BAP_WEB_HOSTPORT": HOST, "TZ": "America/Manaus", "PLAYWRIGHT_BROWSERS_PATH": "/ms-playwright"}
    e.update(k)
    return {a: b for a, b in e.items() if b is not None}


def _rodar(tmp_path, site, cfg=None, env=None, agora=None, mono=None, sair=None, ler_cgroup=None, filtrar=None):
    cfg = {} if cfg is None else cfg
    log, pausas, saidas = [], [], []
    env = _env() if env is None else env
    mono = mono or Relogio()

    def fabrica(raiz, reg, **kw):
        cfg["env_na_fabrica"] = dict(env)
        return RoboFalso(cfg, raiz, reg, **kw)

    tmp_base = tmp_path / "tmp"
    tmp_base.mkdir(exist_ok=True)
    cod = rodar.principal(ambiente=env, relogio=lambda: agora or _agora(), monotonic=mono, abrir=site.abrir,
                          pausa=pausas.append, fabrica_robo=fabrica, saida=log.append,
                          sair=sair or saidas.append, ler_cgroup=ler_cgroup or (lambda p: None), tmp_base=tmp_base,
                          instalar_sinal=False, iniciar_vigia=False, filtrar=filtrar)
    assert list(tmp_base.iterdir()) == [], "a pasta temporária da rodada ficou"
    return SimpleNamespace(cod=cod, log=log, pausas=pausas, saidas=saidas, cfg=cfg, site=site, env=env)


_RX_LINHA = re.compile(r"^evento=[A-Za-z0-9_.:-]+( (fase|dia|n|codigo|classe|variaveis)=[A-Za-z0-9_.:,-]*)*$")


def _log_no_formato(log):
    for linha in log:
        assert _RX_LINHA.match(linha) or linha.startswith("DIAGNOSTICO codigo="), linha


# =====================================================================================================================
# configuração: CONFIG_INSEGURA e CONFIG_FALTANDO saem antes do navegador (§1, §5)
# =====================================================================================================================
@pytest.mark.parametrize("extra", [
    {"DEBUG": "pw:api"}, {"DEBUG": "PW:browser*"}, {"PWDEBUG": "1"}, {"PWDEBUG": "console"},
    {"PLAYWRIGHT_TRACE": "on"}, {"PLAYWRIGHT_VIDEO_DIR": "/tmp/video"}, {"PLAYWRIGHT_HAR": "1"},
])
def test_RN_VIS_007_config_insegura_sai_antes_de_tudo(tmp_path, extra):
    site = SiteCron(_trab())
    r = _rodar(tmp_path, site, env=_env(**extra))
    assert r.cod == 1
    assert site.chamadas == [] and "robos" not in r.cfg
    assert r.log == ["evento=config codigo=CONFIG_INSEGURA"]
    assert r.env.get("BAP_MAXIMA_SENHA") == SENHA                   # nem leu o segredo


@pytest.mark.parametrize("extra", [
    {}, {"DEBUG": "app:*"}, {"PWDEBUG": "0"}, {"PWDEBUG": ""}, {"PLAYWRIGHT_TRACE": "0"},
    {"PLAYWRIGHT_VIDEO_DIR": "off"}, {"PLAYWRIGHT_BROWSERS_PATH": "/ms-playwright"},
])
def test_RN_VIS_007_config_segura_nao_trava(extra):
    assert rodar.config_insegura(_env(**extra)) is False


@pytest.mark.parametrize("falta,esperado", [
    ({"BAP_MAXIMA_USUARIO": None}, ["BAP_MAXIMA_USUARIO"]),
    ({"BAP_MAXIMA_SENHA": "  "}, ["BAP_MAXIMA_SENHA"]),
    ({"BAP_VISITAS_TOKEN": None, "BAP_WEB_HOSTPORT": None}, ["BAP_VISITAS_TOKEN", "BAP_WEB_HOSTPORT"]),
    ({"BAP_WEB_HOSTPORT": "http://host-ficticio/x?y=1"}, ["BAP_WEB_HOSTPORT"]),
])
def test_RN_VIS_005_config_faltando_so_o_nome_da_variavel(tmp_path, falta, esperado):
    site = SiteCron(_trab())
    r = _rodar(tmp_path, site, env=_env(**falta))
    assert r.cod == 1 and site.chamadas == [] and "robos" not in r.cfg
    assert r.log[0] == "evento=config codigo=CONFIG_FALTANDO"
    assert r.log[1] == f"evento=config_faltando n={len(esperado)} variaveis={','.join(esperado)}"
    texto = "\n".join(r.log)
    assert SENHA not in texto and USUARIO not in texto and "host-ficticio" not in texto


def test_RN_VIS_007_segredos_saem_do_ambiente_antes_do_robo(tmp_path):
    site = SiteCron(_trab())
    r = _rodar(tmp_path, site)
    assert r.cod == 0
    na_fabrica = r.cfg["env_na_fabrica"]
    assert "BAP_MAXIMA_USUARIO" not in na_fabrica and "BAP_MAXIMA_SENHA" not in na_fabrica
    assert "BAP_MAXIMA_USUARIO" not in r.env and "BAP_MAXIMA_SENHA" not in r.env
    assert "BAP_VISITAS_TOKEN" not in na_fabrica and "BAP_VISITAS_TOKEN" not in r.env
    # o Robo recebe usuário e senha só no rodar (e no entrar)
    robo = r.cfg["robos"][0]
    assert ("entrar", USUARIO, SENHA) in robo.chamadas
    assert all(USUARIO not in str(v) and SENHA not in str(v) for v in robo.kw.values())


def test_RN_VIS_007_segredos_saem_do_os_environ_de_verdade(tmp_path, monkeypatch):
    """Com `ambiente=None` (produção), o `pop` é no `os.environ`: o driver do Playwright (filho) não herda."""
    for k, v in _env().items():
        monkeypatch.setenv(k, v)
    visto = {}

    def fabrica(raiz, reg, **kw):
        visto["env"] = {k: os.environ.get(k) for k in ("BAP_MAXIMA_USUARIO", "BAP_MAXIMA_SENHA", "BAP_VISITAS_TOKEN")}
        return RoboFalso({}, raiz, reg, **kw)

    site = SiteCron(_trab())
    cod = rodar.principal(relogio=lambda: _agora(), monotonic=Relogio(), abrir=site.abrir, pausa=lambda s: None,
                          fabrica_robo=fabrica, saida=lambda x: None, sair=lambda c: None, ler_cgroup=lambda p: None,
                          tmp_base=tmp_path, instalar_sinal=False, iniciar_vigia=False)
    assert cod == 0
    assert visto["env"] == {"BAP_MAXIMA_USUARIO": None, "BAP_MAXIMA_SENHA": None, "BAP_VISITAS_TOKEN": None}


def test_RN_VIS_007_segredo_e_pwe_nunca_no_log_nem_no_site(tmp_path):
    site = SiteCron(_trab())
    r = _rodar(tmp_path, site, cfg={"log_segredo": True})
    texto = "\n".join(r.log)
    assert USUARIO not in texto and SENHA not in texto and "abc123" not in texto
    assert "usuario=*** senha=***" in texto and "PWE=***" in texto
    for c in site.chamadas:
        bruto = (c.url + json.dumps(c.cab) + (gzip.decompress(c.dados) if c.cab.get("content-encoding") == "gzip"
                                              else (c.dados or b"")).decode("utf-8", "replace"))
        assert USUARIO not in bruto and SENHA not in bruto
        assert c.cab["authorization"] == f"Bearer {fx.TOKEN_CRON}"
        assert c.url.startswith(f"http://{HOST}/api/visitas/")


def test_RN_VIS_007_filtro_do_log_troca_segredo_e_pwe():
    linhas = []
    reg = rodar.Registro(linhas.append)
    reg.segredos("abcdef", "abcde", None)                       # menos de 6 caracteres não entra
    reg("evento=y v=abcde")
    assert linhas.pop() == "evento=y v=abcde"
    reg("evento=x u=abcdef url=/a?PWE=zz9&b=1 PWE=")
    assert linhas == ["evento=x u=*** url=/a?PWE=***&b=1 PWE=***"]
    reg.evento("vendedor", fase="grade", dia="20261126", n=3, codigo="OK", classe="KeyError", vendedor="FULANO",
               extra="x")
    assert linhas[-1] == "evento=vendedor fase=grade dia=20261126 n=3 codigo=OK classe=KeyError"
    reg.evento("x y", fase="a b/c", codigo="")
    assert linhas[-1] == "evento=xy fase=abc"


# =====================================================================================================================
# a volta: sem trabalho, pausa, concessão (§3.1, §3.2; RN-VIS-004 e 005)
# =====================================================================================================================
def test_RN_VIS_005_pausado_nenhum_robo_e_saida_0(tmp_path):
    site = SiteCron(_trab(pausado={"codigo": "MAXIMA_CAPTCHA", "desde": _agora(5).isoformat()}))
    r = _rodar(tmp_path, site)
    assert r.cod == 0 and "robos" not in r.cfg
    assert [c.rota for c in site.chamadas] == ["trabalho"]
    assert r.log == ["evento=sem_trabalho"]
    assert site.chamadas[0].timeout == rodar.HTTP_TEMPO_TRABALHO_S == 15


def test_RN_VIS_008_fora_da_janela_nem_pede_concessao(tmp_path):
    site = SiteCron(_trab())
    r = _rodar(tmp_path, site, agora=_agora(22, 0))
    assert r.cod == 0 and [c.rota for c in site.chamadas] == ["trabalho"] and "robos" not in r.cfg


@pytest.mark.parametrize("status,corpo", [
    (409, {"erro": "rodada ativa", "id": "R20261127T055001"}), (423, {"erro": "pausado", "codigo": "MAXIMA_SENHA"}),
    (429, {"erro": "teto do dia", "motivo": "agenda"}),
])
def test_RN_VIS_004_concessao_negada_sem_robo_e_saida_0(tmp_path, status, corpo):
    site = SiteCron(_trab(), rodada=(status, corpo))
    r = _rodar(tmp_path, site)
    assert r.cod == 0 and "robos" not in r.cfg
    assert [c.rota for c in site.chamadas] == ["trabalho", "rodada"]
    assert r.log == [f"evento=rodada_negada fase=agenda n={status}"]


@pytest.mark.parametrize("resposta", [(400, {"erro": "x"}), (201, {"id": "R2026-11-27"}), (201, {}), (200, {"id": RID})])
def test_RN_VIS_004_concessao_fora_do_contrato_saida_1_sem_robo(tmp_path, resposta):
    site = SiteCron(_trab(), rodada=resposta)
    r = _rodar(tmp_path, site)
    assert r.cod == 1 and "robos" not in r.cfg and not site.de("fim")


def test_RN_VIS_004_corpo_da_concessao(tmp_path):
    ped = {"id": "P20261127T091503", "de": _ymd(ONTEM), "ate": _ymd(HOJE), "refazer": False, "rodadas": 0}
    site = SiteCron(_trab(pedido=ped))
    r = _rodar(tmp_path, site, agora=_agora(9, 20))
    c = site.de("rodada")[0]
    assert c.metodo == "POST" and c.cab["content-type"] == "application/json" and c.timeout == rodar.HTTP_TEMPO_S == 30
    assert site.json(c) == {"motivo": "pedido", "pedido": "P20261127T091503", "dias": [_ymd(ONTEM), _ymd(HOJE)],
                            "versao_robo": rodar.VERSAO_ROBO}
    assert c.dados == rodar.json_bytes(site.json(c))           # separators e ensure_ascii do §3
    assert r.cfg["robos"][0].chamadas[0] == ("rodar", [ONTEM, HOJE], set())
    # na agenda, `pedido` vai null
    site = SiteCron(_trab())
    _rodar(tmp_path, site)
    assert site.json(site.de("rodada")[0])["pedido"] is None


def test_RN_VIS_002_pedido_sem_dia_aberto_nao_trava_a_agenda(tmp_path):
    """Um pedido (sem `refazer`) só com dias já fechados: o site aceita (`validar_periodo` não olha o índice) e o
    pedido só sai da fila no `fim`. O cron não pode ficar parado nele para sempre: a agenda de ontem (aberto) roda."""
    d3, d2 = HOJE - timedelta(days=3), HOJE - timedelta(days=2)
    ped = {"id": "P20261126T180000", "de": _ymd(d3), "ate": _ymd(d2), "refazer": False, "rodadas": 0}
    site = SiteCron(_trab(pedido=ped, indice={_ymd(d3): _fechado(d3), _ymd(d2): _fechado(d2)}))
    r = _rodar(tmp_path, site, agora=_agora(6, 10))
    assert site.de("rodada"), ("a volta parou no pedido vazio, sem concessão nem fim (o pedido fica na fila e a "
                               f"agenda de ontem nunca roda): log={r.log}")
    assert site.json(site.de("rodada")[0])["dias"] == [_ymd(ONTEM)]


# =====================================================================================================================
# uma tentativa só de login (§5.1; RN-VIS-005)
# =====================================================================================================================
class _PaginaLogin:
    """Página do Playwright de mentira para o `entrar` de verdade do `visitas_maxima.Robo`."""

    def __init__(self, depois="https://app.exemplo.test/login", msg="", captcha=False, status=200, corpo=""):
        self.url = "https://app.exemplo.test/login"
        self._depois, self.msg, self.captcha, self.status, self.corpo = depois, msg, captcha, status, corpo
        self.feito = []
        self.context = SimpleNamespace(browser=SimpleNamespace(version="131.0"))

    def goto(self, url, wait_until=None, timeout=None):
        self.feito.append("goto")
        return SimpleNamespace(status=self.status)

    def wait_for_selector(self, sel, timeout=None):
        self.feito.append("esperar")

    def fill(self, sel, valor):
        self.feito.append(f"fill:{sel}")

    def click(self, sel, **k):
        self.feito.append("click")
        self.url = self._depois

    def evaluate(self, js, *a):
        if js == vm.CAPTCHA_JS:
            return self.captcha
        if "innerText.trim()" in js:
            return self.msg
        return self.corpo

    def screenshot(self, **k):
        raise AssertionError("print de tela na nuvem")


class _RoboLogin(vm.Robo):
    """O Robo de verdade, sem Playwright: o `_rodada` põe a página falsa e chama o `entrar` de verdade."""

    criados = []

    def __init__(self, *a, pagina=None, **k):
        super().__init__(*a, **k)
        self._pg, self.n_entrar, self.n_rodar = pagina, 0, 0
        _RoboLogin.criados.append(self)

    def rodar(self, *a, **k):
        self.n_rodar += 1
        return super().rodar(*a, **k)

    def entrar(self, u, s):
        self.n_entrar += 1
        return super().entrar(u, s)

    def _rodada(self, usuario, senha, dias, meses, progresso=None):
        self._abrindo = False
        self.page = self._pg
        self.entrar(usuario, senha)
        raise AssertionError("passou do login")


@pytest.mark.parametrize("pagina,codigo", [
    (lambda: _PaginaLogin(msg="Usuário ou senha inválidos"), "MAXIMA_SENHA"),
    (lambda: _PaginaLogin(captcha=True), "MAXIMA_CAPTCHA"),
    (lambda: _PaginaLogin(depois="https://app.exemplo.test/verificacao", corpo="Enviamos um código por SMS"),
     "MAXIMA_CONFIRMACAO"),
    (lambda: _PaginaLogin(msg="Conta bloqueada"), "MAXIMA_BLOQUEIO"),
    (lambda: _PaginaLogin(status=403), "MAXIMA_BLOQUEIO"),
])
def test_RN_VIS_005_uma_tentativa_so_de_login_manda_fim_e_sai_1(tmp_path, pagina, codigo):
    _RoboLogin.criados = []
    pg = pagina()
    site = SiteCron(_trab())
    log = []
    fabricas = []

    def fabrica(raiz, reg, **kw):
        fabricas.append(kw)
        return _RoboLogin(raiz, reg, pagina=pg, **kw)

    cod = rodar.principal(ambiente=_env(), relogio=lambda: _agora(), monotonic=Relogio(), abrir=site.abrir,
                          pausa=lambda s: None, fabrica_robo=fabrica, saida=log.append, sair=lambda c: None,
                          ler_cgroup=lambda p: None, tmp_base=tmp_path, instalar_sinal=False, iniciar_vigia=False)
    assert cod == 1
    assert len(fabricas) == 1 and len(_RoboLogin.criados) == 1
    robo = _RoboLogin.criados[0]
    assert robo.n_rodar == 1 and robo.n_entrar == 1
    assert pg.feito.count("goto") == 1 and pg.feito.count("fill:input[name=password]") <= 1
    assert fabricas[0]["foto"] is False and fabricas[0]["eventos"] is True and fabricas[0]["visivel"] is False
    assert fabricas[0]["canal"] == "chromium"
    fim = site.fim()
    assert fim["codigo"] == codigo and fim["fase"] == "login"
    assert fim["dias_ok"] == [] and fim["dias_faltando"] == [_ymd(ONTEM)] and fim["achados"] is None
    assert not site.de("dia")
    assert [c.rota for c in site.chamadas].count("rodada") == 1
    assert log[-1] == f"evento=fim fase=login n=0 codigo={codigo}"
    texto = "\n".join(log)
    assert SENHA not in texto and USUARIO not in texto and "inválidos" not in texto and "SMS" not in texto
    _log_no_formato(log)


# =====================================================================================================================
# o lote do dia (§3.4 e §3.6; RN-VIS-002 e 007)
# =====================================================================================================================
def test_RN_VIS_002_lote_do_dia_gzip_sha_e_excel_filtrado(tmp_path):
    d1, d2 = HOJE - timedelta(days=2), ONTEM
    ped = {"id": "P20261127T091503", "de": _ymd(d1), "ate": _ymd(d2), "refazer": False, "rodadas": 0}
    site = SiteCron(_trab(pedido=ped), dia=(200, {"ok": True, "seq": 7, "arquivos": 2}))
    r = _rodar(tmp_path, site, cfg={"plano": {d1: ["ok", "ok"], d2: ["ok"]}}, agora=_agora(9, 20))
    assert r.cod == 0
    lotes = site.de("dia")
    assert [c.caminho for c in lotes] == [f"/api/visitas/rodada/{RID}/dia/{_ymd(d1)}",
                                          f"/api/visitas/rodada/{RID}/dia/{_ymd(d2)}"]
    from openpyxl import load_workbook
    for c, d, n in zip(lotes, (d1, d2), (2, 1)):
        assert c.cab["content-encoding"] == "gzip" and c.cab["content-type"] == "application/json"
        bruto = gzip.decompress(c.dados)
        assert c.cab["x-bap-sha256"] == hashlib.sha256(bruto).hexdigest()
        corpo = json.loads(bruto)
        assert set(corpo) == {"versao", "rodada", "dia", "baixado_em", "vendedores", "erros_vendedor", "equipe",
                              "extras", "arquivos"}
        assert corpo["versao"] == 1 and corpo["rodada"] == RID and corpo["dia"] == _ymd(d)
        assert corpo["vendedores"] == n and corpo["erros_vendedor"] == 0
        assert datetime.fromisoformat(corpo["baixado_em"]).utcoffset() == timedelta(hours=-4)
        assert set(corpo["equipe"]) == {"filiais", "supervisores", "representantes"}
        assert corpo["extras"] == {"VENDEDOR FICTICIO 0": {"gps": True, "versao": "9.9"}}
        assert len(corpo["arquivos"]) == n
        for a in corpo["arquivos"]:
            dados = base64.b64decode(a["b64"])
            assert a["sha256"] == hashlib.sha256(dados).hexdigest() and a["bytes"] == len(dados)
            assert a["nome"].startswith(f"VISITA-{a['pasta']}-{d:%d-%m-%Y}-")
            assert vn._RX_ARQ_ANALITICO.match(a["nome"])
            assert dados != r.cfg["originais"][a["nome"]], "subiu o Excel da Máxima, não o filtrado"
            ws = load_workbook(io.BytesIO(dados)).active
            valores = {str(v) for row in ws.iter_rows(values_only=True) for v in row if v is not None}
            assert not {"KM DIST", "BONIF", "OBSERVACAO", "obs ficticia"} & valores
            assert "CLIENTE FICTICIO 0" in valores                    # o permitido continua
    fim = site.fim()
    assert fim["codigo"] == "OK" and fim["dias_ok"] == [_ymd(d1), _ymd(d2)] and fim["dias_faltando"] == []
    assert fim["achados"] is None and fim["medidas"] is None and fim["fase"] is None
    _log_no_formato(r.log)
    assert f"evento=dia_enviado fase=envio dia={_ymd(d1)} n=2" in r.log


def test_RN_VIS_002_dia_sem_excel_nao_sobe(tmp_path):
    d1, d2 = HOJE - timedelta(days=2), ONTEM
    ped = {"id": "P1", "de": _ymd(d1), "ate": _ymd(d2), "refazer": False, "rodadas": 0}
    site = SiteCron(_trab(pedido=ped))
    r = _rodar(tmp_path, site, cfg={"plano": {d1: [], d2: ["erro"]}}, agora=_agora(9, 20))
    assert not site.de("dia")
    fim = site.fim()
    assert fim["dias_ok"] == [] and fim["erros_vendedor"] == 1 and fim["codigo"] == "PARCIAL_VENDEDOR"
    assert r.cod == 0
    assert f"evento=dia_sem_excel dia={_ymd(d1)}" in r.log


def test_RN_VIS_006_vendedor_perdido_conta_no_lote_e_no_fim(tmp_path):
    site = SiteCron(_trab())
    r = _rodar(tmp_path, site, cfg={"plano": {ONTEM: ["ok", "erro", "ok"]}})
    corpo = site.json(site.de("dia")[0])
    assert corpo["vendedores"] == 3 and corpo["erros_vendedor"] == 1 and len(corpo["arquivos"]) == 2
    fim = site.fim()
    assert fim["codigo"] == "PARCIAL_VENDEDOR" and fim["erros_vendedor"] == 1 and fim["dias_ok"] == [_ymd(ONTEM)]
    assert r.cod == 0


def test_RN_VIS_007_achado_do_filtro_para_a_rodada_e_o_dia_nao_sobe(tmp_path):
    d1, d2, d3 = HOJE - timedelta(days=3), HOJE - timedelta(days=2), ONTEM
    ped = {"id": "P1", "de": _ymd(d1), "ate": _ymd(d3), "refazer": False, "rodadas": 0}
    site = SiteCron(_trab(pedido=ped))
    r = _rodar(tmp_path, site, cfg={"plano": {d1: ["ok"], d2: ["ok", "achado"], d3: ["ok"]}}, agora=_agora(9))
    assert r.cod == 1
    assert [c.caminho.rsplit("/", 1)[1] for c in site.de("dia")] == [_ymd(d1)]     # d2 não sobe; d3 nem baixa
    assert r.cfg["robos"][0].chamadas[0][0] == "rodar"
    fim = site.fim()
    assert fim["codigo"] == "DADO_PESSOAL" and fim["fase"] == "filtro"
    assert fim["dias_ok"] == [_ymd(d1)] and fim["dias_faltando"] == [_ymd(d2), _ymd(d3)]
    assert fim["achados"] and all(set(a) == {"coluna", "tipo", "n"} for a in fim["achados"])
    assert {"tipo": "email", "n": 1} in [{"tipo": a["tipo"], "n": a["n"]} for a in fim["achados"]]
    texto = json.dumps(fim) + "\n".join(r.log)
    assert "fulano" not in texto and "@" not in texto and "exemplo.test" not in texto
    assert f"evento=dado_pessoal fase=filtro dia={_ymd(d2)} n=1" in r.log
    _log_no_formato(r.log)


@pytest.mark.parametrize("status,corpo,codigo,saida", [
    (413, {"erro": "lote grande demais"}, "SITE_RECUSOU", 0),
    (413, {"erro": "lote grande demais", "codigo": "DESCOMPRESSAO_TETO"}, "DESCOMPRESSAO_TETO", 0),
    (422, {"erro": "sha256"}, "SITE_RECUSOU", 0),
    (422, {"erro": "esquema inválido", "detalhes": ["arquivos[0].nome"]}, "SITE_RECUSOU", 0),
    (422, {"erro": "dado pessoal", "achados": [{"coluna": "CELULA", "tipo": "telefone", "n": 2}]}, "DADO_PESSOAL", 1),
])
def test_RN_VIS_007_resposta_do_lote_vira_o_codigo_do_contrato(tmp_path, status, corpo, codigo, saida):
    site = SiteCron(_trab(), dia=(status, corpo))
    r = _rodar(tmp_path, site)
    assert len(site.de("dia")) == 1
    fim = site.fim()
    assert fim["codigo"] == codigo and r.cod == saida == rodar.codigo_e_saida(codigo)
    assert fim["dias_ok"] == [] and fim["dias_faltando"] == [_ymd(ONTEM)]
    if codigo == "DADO_PESSOAL":
        assert fim["fase"] == "envio" and fim["achados"] == [{"coluna": "CELULA", "tipo": "telefone", "n": 2}]
    else:
        assert fim["achados"] is None


@pytest.mark.parametrize("onde", ["progresso", "dia"])
@pytest.mark.parametrize("status", [404, 409])
def test_RN_VIS_004_concessao_perdida_para_sem_fim(tmp_path, onde, status):
    site = SiteCron(_trab(), **{onde: (status, {"erro": "concessão vencida"})})
    r = _rodar(tmp_path, site, cfg={"plano": {ONTEM: ["ok", "ok"]}})
    assert r.cod == 0 and not site.de("fim")
    assert len(site.de("dia")) == (0 if onde == "progresso" else 1)
    assert any(x.startswith("evento=concessao_perdida") and f"n={status}" in x for x in r.log)
    if onde == "progresso":                      # para no primeiro progresso: nem chega no vendedor
        assert len(site.de("progresso")) == 1


# =====================================================================================================================
# SITE_FORA, tempos e saída (§2, §5)
# =====================================================================================================================
def test_RN_VIS_004_site_fora_no_trabalho_3_tentativas_sem_esperar(tmp_path):
    site = SiteCron(_trab(), trabalho="fora")
    r = _rodar(tmp_path, site)
    assert r.cod == 1 and len(site.chamadas) == rodar.HTTP_TENTATIVAS == 3
    assert r.pausas == [rodar.HTTP_PAUSA_S] * 2 == [30, 30]
    assert r.log == ["evento=trabalho codigo=SITE_FORA"] and "robos" not in r.cfg


def test_RN_VIS_004_5xx_conta_como_fora_e_4xx_volta_na_hora(tmp_path):
    site = SiteCron(_trab(), trabalho=[(503, {}), (502, {}), (200, _trab(pausado={"codigo": "X"}))])
    r = _rodar(tmp_path, site)
    assert r.cod == 0 and len(site.chamadas) == 3 and r.pausas == [30, 30]
    site = SiteCron(_trab(), trabalho=(401, {"erro": "token"}))
    r = _rodar(tmp_path, site)
    assert r.cod == 1 and len(site.chamadas) == 1 and r.pausas == []
    assert r.log == ["evento=trabalho n=401 codigo=SITE_FORA"]


def test_RN_VIS_004_site_fora_no_lote_fecha_com_site_fora(tmp_path):
    site = SiteCron(_trab(), dia="fora")
    r = _rodar(tmp_path, site)
    assert len(site.de("dia")) == 3 and r.pausas == [30, 30]
    fim = site.fim()
    assert fim["codigo"] == "SITE_FORA" and r.cod == 1
    assert "evento=site_fora codigo=SITE_FORA" in r.log


def test_RN_VIS_004_site_fora_no_fim_sai_1(tmp_path):
    site = SiteCron(_trab(), fim="fora")
    r = _rodar(tmp_path, site)
    assert len(site.de("fim")) == 3 and r.cod == 1 and r.log[-1] == "evento=fim codigo=SITE_FORA"


@pytest.mark.parametrize("arquivos,esperado", [
    ({rodar.CGROUP_V2: "1073741824\n", rodar.CGROUP_V1: "1"}, (1024.0, "cgroup")),
    ({rodar.CGROUP_V2: "648019968"}, (618.0, "cgroup")),
    ({rodar.CGROUP_V2: None, rodar.CGROUP_V1: "524288000"}, (500.0, "cgroup_v1")),
    ({rodar.CGROUP_V2: "max", rodar.CGROUP_V1: "524288000"}, (500.0, "cgroup_v1")),
    ({}, (None, "indisponivel")),
])
def test_RN_VIS_008_ler_pico_mb_v2_v1_nenhum(arquivos, esperado):
    assert rodar.CGROUP_V2 == "/sys/fs/cgroup/memory.peak"
    assert rodar.CGROUP_V1 == "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"
    assert rodar.ler_pico_mb(arquivos.get) == esperado


def test_RN_VIS_008_pico_mb_vai_no_fim(tmp_path):
    site = SiteCron(_trab())
    _rodar(tmp_path, site, ler_cgroup={rodar.CGROUP_V2: "648019968"}.get)
    assert site.fim()["pico_mb"] == 618.0


# ---------------------------------------------------------------------------------------------------------- vigia
def test_RN_VIS_008_vigia_45_55_58_minutos_com_relogio_falso():
    assert (rodar.RODADA_MAX_MIN, rodar.RODADA_TETO_MIN, rodar.RODADA_MATA_MIN) == (45, 55, 58)
    rel, parar, saidas, log = Relogio(0.0), threading.Event(), [], []
    v = rodar.Vigia(parar, rel, saidas.append, rodar.Registro(log.append))
    for t in (0, 45 * 60, 55 * 60 - 1):
        rel.t = t
        v.verificar()
        assert not parar.is_set() and not v.estourou and saidas == []
    rel.t = 55 * 60
    v.verificar()
    v.verificar()
    assert parar.is_set() and v.estourou and saidas == [] and log == ["evento=vigia_teto"]
    rel.t = 58 * 60 - 1
    v.verificar()
    assert saidas == []
    rel.t = 58 * 60
    v.verificar()
    assert saidas == [1] and "evento=vigia_mata codigo=RODADA_INTERROMPIDA" in log


def test_RN_VIS_008_vigia_do_diagnostico_para_aos_15_minutos():
    rel, parar = Relogio(100.0), threading.Event()
    v = rodar.Vigia(parar, rel, lambda c: None, rodar.Registro(lambda x: None), diagnostico=True)
    rel.t = 100 + 15 * 60 - 1
    v.verificar()
    assert not parar.is_set()
    rel.t = 100 + 15 * 60
    v.verificar()
    assert parar.is_set() and v.estourou


def test_RN_VIS_008_rodada_max_45_min_no_fim_do_dia_fecha_parcial_tempo(tmp_path):
    d1, d2 = HOJE - timedelta(days=2), ONTEM
    ped = {"id": "P1", "de": _ymd(d1), "ate": _ymd(d2), "refazer": False, "rodadas": 0}
    mono = Relogio(1000.0)

    def antes(d):
        if d == d1:
            mono.t += 45 * 60

    site = SiteCron(_trab(pedido=ped))
    r = _rodar(tmp_path, site, cfg={"antes_de_fechar": antes}, mono=mono, agora=_agora(9))
    fim = site.fim()
    assert fim["codigo"] == "PARCIAL_TEMPO" and fim["dias_ok"] == [_ymd(d1)] and fim["dias_faltando"] == [_ymd(d2)]
    assert len(site.de("dia")) == 1 and r.cod == 0
    assert f"evento=rodada_max dia={_ymd(d1)} codigo=PARCIAL_TEMPO" in r.log


def test_RN_VIS_008_44_min_no_ultimo_dia_e_ok(tmp_path):
    mono = Relogio(0.0)
    site = SiteCron(_trab())
    _rodar(tmp_path, site, cfg={"antes_de_fechar": lambda d: setattr(mono, "t", 50 * 60)}, mono=mono)
    assert site.fim()["codigo"] == "OK"                 # passou de 45, mas não resta dia


# =====================================================================================================================
# diagnóstico (§6): mede, filtra e não manda lote
# =====================================================================================================================
def test_RN_VIS_004_diagnostico_manda_medidas_e_nenhum_lote(tmp_path):
    mono = Relogio(0.0)

    def ao_vendedor(d, i):
        mono.t += 40 + i

    site = SiteCron(_trab(diagnostico={"estado": "pendente"}, agenda="desligada"))
    r = _rodar(tmp_path, site, cfg={"plano": {ONTEM: ["ok", "ok", "ok"]}, "ao_vendedor": ao_vendedor}, mono=mono,
               ler_cgroup={rodar.CGROUP_V2: "648019968"}.get)
    assert site.json(site.de("rodada")[0])["motivo"] == "diagnostico"
    assert site.json(site.de("rodada")[0])["dias"] == [_ymd(ONTEM)]
    assert not site.de("dia")
    fim = site.fim()
    assert fim["codigo"] == "OK" and fim["dias_ok"] == [] and fim["dias_faltando"] == [] and fim["achados"] is None
    med = fim["medidas"]
    assert set(med) == {"tempos_s", "fonte_pico", "chromium", "espelho"}
    assert med["fonte_pico"] == "cgroup" and med["chromium"] == "131.0.6778.33"
    assert {"login", "maxgestao", "filtros", "vendedor"} <= set(med["tempos_s"])
    assert len(med["tempos_s"]["vendedor"]) == rodar.DIAGNOSTICO_VENDEDORES == 2
    assert set(med["espelho"]["colunas_fora"]) >= {"KM DIST", "BONIF", "OBSERVACAO"}
    assert set(med["espelho"]["limpos"]) == {"CLIENTE", "JUSTIFICATIVA"}
    # parou nos 2 vendedores: o 3º nem foi baixado
    assert len(r.cfg["originais"]) == 2
    linha = [x for x in r.log if x.startswith("DIAGNOSTICO ")]
    assert len(linha) == 1 and linha[0].startswith("DIAGNOSTICO codigo=OK pico_mb=618.0 login_s=")
    assert "achados=0" in linha[0] and "colunas_fora=" in linha[0]
    assert r.cod == 0
    _log_no_formato(r.log)


def test_RN_VIS_007_diagnostico_com_achado_fecha_dado_pessoal(tmp_path):
    site = SiteCron(_trab(diagnostico={"estado": "pendente"}))
    r = _rodar(tmp_path, site, cfg={"plano": {ONTEM: ["achado", "ok"]}})
    assert not site.de("dia")
    fim = site.fim()
    assert fim["codigo"] == "DADO_PESSOAL" and fim["fase"] == "filtro" and fim["achados"]
    assert fim["medidas"] is not None and r.cod == 1
    assert "@" not in json.dumps(fim)


# =====================================================================================================================
# erro do Robo e exceção não prevista (§5: ERRO_INTERNO, só o nome da classe)
# =====================================================================================================================
def test_RN_VIS_005_erro_do_robo_no_meio_guarda_o_dia_que_terminou(tmp_path):
    d1, d2 = HOJE - timedelta(days=2), ONTEM
    ped = {"id": "P1", "de": _ymd(d1), "ate": _ymd(d2), "refazer": False, "rodadas": 0}
    site = SiteCron(_trab(pedido=ped))
    r = _rodar(tmp_path, site, cfg={"erro_no_dia": d2, "erro_excecao": RuntimeError("Target closed")},
               agora=_agora(9))
    fim = site.fim()
    assert fim["codigo"] == "NAVEGADOR_FALHOU" and fim["dias_ok"] == [_ymd(d1)] and fim["dias_faltando"] == [_ymd(d2)]
    assert r.cod == 1


def test_RN_VIS_005_excecao_nao_prevista_so_a_classe_e_a_fase_do_robo(tmp_path):
    site = SiteCron(_trab())
    r = _rodar(tmp_path, site, cfg={"erro_no_dia": ONTEM,
                                    "erro_excecao": KeyError("mensagem-ficticia-com-detalhe")})
    fim = site.fim()
    assert fim["codigo"] == "ERRO_INTERNO" and fim["fase"] == "grade" and r.cod == 1
    assert "evento=excecao classe=KeyError" in r.log
    assert "mensagem-ficticia" not in "\n".join(r.log)


def test_RN_VIS_005_excecao_fora_do_robo_nao_escapa_e_manda_fim(tmp_path):
    """Exceção antes do `robo.rodar` (aqui, na construção do Robo): o §5 manda `ERRO_INTERNO` com a fase e, no log,
    só o nome da classe. O cron não pode morrer com o traceback (que leva a mensagem) e sem `fim`."""
    site = SiteCron(_trab())
    log = []

    def fabrica(raiz, reg, **kw):
        raise RuntimeError("mensagem-ficticia-que-nao-pode-sair")

    try:
        cod = rodar.principal(ambiente=_env(), relogio=lambda: _agora(), monotonic=Relogio(), abrir=site.abrir,
                              pausa=lambda s: None, fabrica_robo=fabrica, saida=log.append, sair=lambda c: None,
                              ler_cgroup=lambda p: None, tmp_base=tmp_path, instalar_sinal=False,
                              iniciar_vigia=False)
    except Exception as e:                                               # noqa: BLE001
        pytest.fail(f"a exceção escapou do principal ({type(e).__name__}): traceback com a mensagem no log do "
                    f"Render e nenhum `fim` (o site só vê RODADA_INTERROMPIDA depois de 10 min)")
    assert cod == 1
    fim = site.fim()
    assert fim["codigo"] == "ERRO_INTERNO" and fim["fase"] == "inicio"
    assert fim["dias_ok"] == [] and fim["dias_faltando"] == [_ymd(ONTEM)] and fim["achados"] is None
    assert "evento=excecao codigo=ERRO_INTERNO classe=RuntimeError" in log
    assert "mensagem-ficticia" not in "\n".join(log)


def test_RN_VIS_005_excecao_depois_de_um_dia_manda_fim_com_o_que_ja_subiu(tmp_path):
    """Exceção não prevista no `robo.rodar` depois do 1º dia (o Robo de mentira levanta SystemError já na fase
    `grade`): o `fim` ERRO_INTERNO leva a fase do Robo, os `dias_ok` e os `dias_faltando` da rodada."""
    d1, d2 = HOJE - timedelta(days=2), ONTEM
    ped = {"id": "P1", "de": _ymd(d1), "ate": _ymd(d2), "refazer": False, "rodadas": 0}
    site = SiteCron(_trab(pedido=ped))
    log = []
    cfg = {}

    def fabrica(raiz, reg, **kw):
        robo = RoboFalso(cfg, raiz, reg, **kw)
        original = robo.rodar

        def rodar_e_quebrar_depois(u, s, dias, meses):
            original(u, s, [d1], meses)
            robo.fase = "grade"
            raise SystemError("mensagem-ficticia")       # o Robo só levanta dentro do rodar: o cron trata
        robo.rodar = rodar_e_quebrar_depois
        return robo

    cod = rodar.principal(ambiente=_env(), relogio=lambda: _agora(9), monotonic=Relogio(), abrir=site.abrir,
                          pausa=lambda s: None, fabrica_robo=fabrica, saida=log.append, sair=lambda c: None,
                          ler_cgroup=lambda p: None, tmp_base=tmp_path, instalar_sinal=False, iniciar_vigia=False)
    fim = site.fim()
    assert cod == 1 and fim["codigo"] == "ERRO_INTERNO" and fim["fase"] == "grade"
    assert fim["dias_ok"] == [_ymd(d1)] and fim["dias_faltando"] == [_ymd(d2)]
    assert "mensagem-ficticia" not in "\n".join(log)


def test_RN_VIS_005_trabalho_torto_antes_da_concessao_sai_1_sem_fim(tmp_path):
    site = SiteCron(_trab(tentativas_hoje={"dia": _ymd(HOJE), "total": "muitas", "por_motivo": {}}))
    log = []
    cod = rodar.principal(ambiente=_env(), relogio=lambda: _agora(), monotonic=Relogio(), abrir=site.abrir,
                          pausa=lambda s: None, fabrica_robo=lambda *a, **k: pytest.fail("Robo sem concessão"),
                          saida=log.append, sair=lambda c: None, ler_cgroup=lambda p: None, tmp_base=tmp_path,
                          instalar_sinal=False, iniciar_vigia=False)
    assert cod == 1 and [c.rota for c in site.chamadas] == ["trabalho"]
    assert log == ["evento=excecao codigo=ERRO_INTERNO classe=ValueError"]


# =====================================================================================================================
# proibido no código (§1 e D5 da ADR 0004): trace, vídeo, HAR, console e print de tela
# =====================================================================================================================
_PROIBIDO = re.compile(r"tracing|record_video|record_har|\.on\(\s*[\"']console|screenshot")


def test_RN_VIS_007_codigo_do_cron_sem_trace_video_har_console_nem_print():
    """Contrato §1, a parte do código: nada disso em `nuvem/visitas/*.py`."""
    arqs = sorted((RAIZ / "nuvem" / "visitas").glob("*.py"))
    assert {a.name for a in arqs} >= {"rodar.py", "agenda.py"}
    for a in arqs:
        achados = [(n, l.strip()) for n, l in enumerate(a.read_text(encoding="utf-8").splitlines(), 1)
                   if _PROIBIDO.search(l)]
        assert achados == [], (a.name, achados)


def test_RN_VIS_007_robo_sem_trace_video_har_console_e_print_so_no_foto_do_erro():
    """No `visitas_maxima.py` (o caminho do Robo na nuvem): nenhuma chamada nem argumento de tracing, vídeo, HAR
    ou `on("console")`; o único `screenshot` é o do `Robo.foto_do_erro` (o do PC, com foto=True)."""
    import ast
    arvore = ast.parse((RAIZ / "visitas_maxima.py").read_text(encoding="utf-8"))
    pais = {}
    for no in ast.walk(arvore):
        for filho in ast.iter_child_nodes(no):
            pais[filho] = no

    def funcao(no):
        while no in pais:
            no = pais[no]
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return no.name
        return None

    prints, proibidos = [], []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Attribute):
            if no.attr == "screenshot":
                prints.append(funcao(no))
            elif no.attr in ("tracing", "record_video", "record_har"):
                proibidos.append((no.lineno, no.attr))
        elif isinstance(no, ast.keyword) and no.arg and no.arg.startswith(("record_video", "record_har")):
            proibidos.append((no.value.lineno, no.arg))
        elif isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr in ("on", "once") \
                and no.args and isinstance(no.args[0], ast.Constant) and no.args[0].value == "console":
            proibidos.append((no.lineno, "on(console)"))
    assert proibidos == []
    assert prints == ["foto_do_erro"]


def test_RN_VIS_007_foto_true_do_pc_tira_um_print(tmp_path):
    """O outro lado do `foto=False` da nuvem (coberto em test_T0045_robo_nuvem.py): no PC (`foto=True`, o padrão),
    o `foto_do_erro` tira 1 print. Prova que a varredura acima olha o print que existe de verdade."""
    class Pg:
        n = 0

        def screenshot(self, **k):
            Pg.n += 1

    pc = vm.Robo(tmp_path / "p", lambda *_: None)
    pc.page = Pg()
    assert pc.foto_do_erro() is not None and Pg.n == 1
