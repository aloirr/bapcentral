"""T-0045 (ADR 0004 §8 e §9 item 6; contrato visitas-nuvem §2, §3.3, §4.4, §4.5,
§5 e §5.1): o `visitas_maxima` pronto para a nuvem.

- funções puras: `classificar_login` (RN-VIS-005), `codigo_da_excecao` (§5),
  `fechados_pc` (RN-VIS-002) e `aviso_site_baixando` (§4.5);
- `Robo` com `canal`, `foto`, `eventos`, `ao_fechar_dia` e `ao_fase`: o log em
  modo eventos sai sem nome de pessoa e sem o texto cru da Máxima (D5), sem
  print de tela; o PC continua igual sem os parâmetros novos;
- `entrar` com uma página falsa: os 4 códigos da Máxima e nenhuma segunda
  tentativa de login;
- `gravar_excel_importado` (RN-VIS-003): nunca sobrescreve nem apaga;
- `depois_de_baixar` fora do `executar`, uma vez;
- o aviso do botão do PC pelo `/saude` (com a tela Tkinter, só com display).

Os testes pulam enquanto o robô da T-0045 (modulo-robo/T-0045-nuvem-robo) não
estiver no main. Dados 100% fictícios; nada de rede nem de navegador.
"""
import os
import re
import sys
import threading
import types
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import visitas_maxima as vm
import visitas_nucleo as vn
from visitas_nuvem_fixture import NOMES_FICTICIOS, VENDEDOR, espelho_xlsx, nome_arquivo

if not hasattr(vm, "classificar_login"):
    pytest.skip("robô da T-0045 (modulo-robo/T-0045-nuvem-robo) ainda não está no main",
                allow_module_level=True)

RAIZ = Path(__file__).resolve().parent.parent
USUARIO = "usuario.ficticio.robo"
SENHA = "senha-ficticia-123"


# ------------------------------------------------------------------ RN-VIS-005: classificar_login
CASOS_LOGIN = [
    # (url, texto, tem_captcha, http_status) -> código
    ("https://app.exemplo.test/login", "Usuário ou senha inválidos", False, None, "MAXIMA_SENHA"),
    ("https://app.exemplo.test/login", "Credenciais incorretas.", False, None, "MAXIMA_SENHA"),
    ("https://app.exemplo.test/login", "Erro ao entrar", False, None, "MAXIMA_SENHA"),
    ("https://app.exemplo.test/login", "", True, None, "MAXIMA_CAPTCHA"),
    ("https://app.exemplo.test/login", "Usuário ou senha inválidos", True, None, "MAXIMA_CAPTCHA"),
    ("https://app.exemplo.test/login", "Enviamos um código para o seu e-mail", False, None, "MAXIMA_CONFIRMACAO"),
    ("https://app.exemplo.test/login", "Digite o código de verificação", False, None, "MAXIMA_CONFIRMACAO"),
    ("https://app.exemplo.test/login", "Novo dispositivo detectado", False, None, "MAXIMA_CONFIRMACAO"),
    ("https://app.exemplo.test/verificacao", "Confirme seu dispositivo", False, None, "MAXIMA_CONFIRMACAO"),
    ("https://app.exemplo.test/trocar-senha", "Sua senha expirou", False, None, "MAXIMA_CONFIRMACAO"),
    ("https://app.exemplo.test/login", "Aceite os termos de uso para continuar", False, None, "MAXIMA_CONFIRMACAO"),
    ("https://app.exemplo.test/login", "Sua senha expirou. Crie uma nova senha", False, None, "MAXIMA_CONFIRMACAO"),
    ("https://app.exemplo.test/login", "Conta bloqueada. Procure o administrador", False, None, "MAXIMA_BLOQUEIO"),
    ("https://app.exemplo.test/login", "Usuário bloqueado", False, None, "MAXIMA_BLOQUEIO"),
    ("https://app.exemplo.test/login", "Acesso negado", False, None, "MAXIMA_BLOQUEIO"),
    ("https://app.exemplo.test/login", "", False, 403, "MAXIMA_BLOQUEIO"),
    ("https://app.exemplo.test/home", "", False, 403, "MAXIMA_BLOQUEIO"),
    ("https://app.exemplo.test/home", "Bem-vindo", False, None, None),
    ("https://app.exemplo.test/home", "", True, None, None),          # saiu do /login: segue
    ("https://app.exemplo.test/login", "", False, None, None),        # ainda carregando: espera
    ("https://app.exemplo.test/login", None, False, None, None),
    (None, None, False, None, None),
]


# contrato §5.1: os 4 códigos da Máxima que o login devolve
LOGIN_DO_CONTRATO = ("MAXIMA_SENHA", "MAXIMA_CONFIRMACAO", "MAXIMA_CAPTCHA", "MAXIMA_BLOQUEIO")


@pytest.mark.parametrize("url,texto,captcha,http,esperado", CASOS_LOGIN)
def test_RN_VIS_005_classificar_login_captcha_confirmacao_bloqueio(url, texto, captcha, http, esperado):
    assert vm.classificar_login(url, texto, captcha, http) == esperado


# Contrato §5.1: "foi para uma página de verificação, com texto de código, confirmação, dispositivo, termo ou
# troca de senha → MAXIMA_CONFIRMACAO". A URL de verificação já diz o que é; o texto muda de redação.
VERIFICACAO_TEXTO_NOVO = [
    ("https://app.exemplo.test/verificacao", "Confirme o seu dispositivo"),
    ("https://app.exemplo.test/verificacao", "Insira o código"),
    ("https://app.exemplo.test/trocar-senha", "Troque a sua senha"),
    ("https://app.exemplo.test/mfa", "Este dispositivo não é reconhecido"),
    ("https://app.exemplo.test/2fa", "Passo 2 de 2"),
    ("https://app.exemplo.test/conta/otp", "Aguarde"),
    ("https://app.exemplo.test/nova-senha", "Bem-vindo"),
    ("https://app.exemplo.test/confirmar-dispositivo", ""),
]


@pytest.mark.parametrize("url,texto", VERIFICACAO_TEXTO_NOVO)
def test_RN_VIS_005_pagina_de_verificacao_pausa_com_qualquer_redacao(url, texto):
    """D1 (achado no 11b24fc e no ed640e1, corrigido no f6ae758): fora do /login, num segmento de verificação da lista fechada, o texto que não casa com o regex
    devolve None, e o `entrar` segue como "Login ok"; a rodada cai depois em TELA_MUDOU (nova tentativa),
    e a agenda entra de novo na Máxima que pediu confirmação (o §5.1 manda nunca repetir o login)."""
    assert vm.classificar_login(url, texto, False, None) == "MAXIMA_CONFIRMACAO"


def test_RN_VIS_005_entrar_na_pagina_de_verificacao_nao_segue(tmp_path):
    """A consequência do D1 (corrigido no f6ae758) no `entrar`: a página de verificação com redação nova não pode virar "Login ok"."""
    pg = _Pagina(depois_url="https://app.exemplo.test/verificacao", corpo="Confirme o seu dispositivo")
    erro, _, _ = _entrar(tmp_path, pg)
    assert erro is not None and (erro.codigo, erro.fase) == ("MAXIMA_CONFIRMACAO", "login")


def test_RN_VIS_005_verificacao_so_pelo_caminho_pede_duas_leituras(tmp_path):
    """a020b53: sem texto claro, o caminho de verificação só decide na 2ª leitura do mesmo caminho, 1 s depois
    (com texto claro, decide na 1ª). Login ainda uma vez só."""
    import time
    pg = _Pagina(depois_url="https://app.exemplo.test/mfa", corpo="Aguarde")
    t0 = time.monotonic()
    erro, _, _ = _entrar(tmp_path, pg)
    assert (erro.codigo, erro.fase) == ("MAXIMA_CONFIRMACAO", "login")
    assert time.monotonic() - t0 >= 1.0
    assert len([x for x in pg.feito if x[0] == "click"]) == 1


def test_RN_VIS_005_verificacao_de_passagem_nao_pausa(tmp_path):
    """a020b53: o caminho de verificação que aparece uma leitura só (redirecionamento) e vai para a página inicial
    é login ok, não pausa."""
    class Passagem(_Pagina):
        leituras = 0

        @property
        def url(self):
            if self._depois is None:
                return "https://app.exemplo.test/login"
            Passagem.leituras += 1
            return "https://app.exemplo.test/mfa" if Passagem.leituras == 1 else "https://app.exemplo.test/home"

        @url.setter
        def url(self, v):
            pass

        def click(self, sel, **k):
            self.feito.append(("click", sel))
            self._depois = "x"
    pg = Passagem(corpo="Aguarde")
    pg._depois = None
    erro, log, _ = _entrar(tmp_path, pg)
    assert erro is None and Passagem.leituras >= 2


@pytest.mark.parametrize("texto", ["Defina uma nova senha", "Crie uma senha nova para continuar"])
def test_RN_VIS_005_troca_de_senha_no_login_e_confirmacao_nao_senha_recusada(texto):
    """D2 (achado no 11b24fc e no ed640e1, corrigido no f6ae758), menor: no /login, o pedido de troca de senha vira MAXIMA_SENHA (o texto do
    site manda conferir a senha) em vez de MAXIMA_CONFIRMACAO. Os dois pausam; muda o que o admin lê."""
    assert vm.classificar_login("https://app.exemplo.test/login", texto, False, None) == "MAXIMA_CONFIRMACAO"


def test_RN_VIS_005_classificar_login_so_devolve_codigo_da_lista_e_da_web():
    web = _web_visitas()
    saidas = {vm.classificar_login(*c[:4]) for c in CASOS_LOGIN} - {None}
    assert saidas == set(LOGIN_DO_CONTRATO)
    assert set(LOGIN_DO_CONTRATO) <= set(web.PAUSAM)          # todos pausam no site (RN-VIS-005)


# ------------------------------------------------------------------ contrato §5: codigo_da_excecao
class TimeoutError(Exception):                                # noqa: A001  (o nome que o Playwright usa)
    pass


@pytest.mark.parametrize("exc,fase,esperado", [
    (vm.ErroRobo("Não achei o cartão."), "inicio", ("TELA_MUDOU", "inicio")),
    (vm.ErroRobo("x", "MAXIMA_SENHA", "login"), "grade", ("MAXIMA_SENHA", "login")),
    (vm.ErroRobo("x", fase="menu"), "grade", ("TELA_MUDOU", "menu")),
    (RuntimeError("Target closed"), "login", ("NAVEGADOR_FALHOU", "login")),
    (vm.ErroRobo("x", "NAVEGADOR_FALHOU"), "inicio", ("NAVEGADOR_FALHOU", "inicio")),
    (RuntimeError("Target page, context or browser has been closed"), "grade", ("NAVEGADOR_FALHOU", "grade")),
    (RuntimeError("Page crashed"), "espelho", ("NAVEGADOR_FALHOU", "espelho")),
    (MemoryError("out of memory"), "grade", ("NAVEGADOR_FALHOU", "grade")),
    (RuntimeError("qualquer"), "inicio", ("ERRO_INTERNO", "inicio")),   # a fase sozinha não decide (ed640e1)
    (TimeoutError("Timeout 60000ms exceeded"), "login", ("MAXIMA_FORA", "login")),
    (TimeoutError("Timeout 40000ms exceeded"), "filtros", ("TELA_MUDOU", "filtros")),
    (KeyError("VENDEDOR FICTICIO UM"), "grade", ("ERRO_INTERNO", "grade")),
    (ValueError(""), None, ("ERRO_INTERNO", None)),
])
def test_RN_VIS_005_codigo_da_excecao_por_fase(exc, fase, esperado):
    assert vm.codigo_da_excecao(exc, fase) == esperado


def test_RN_VIS_005_codigo_da_excecao_nao_le_a_mensagem_da_maxima():
    """A mensagem crua (que pode trazer nome ou senha) não muda o código: só a classe e as marcas do navegador."""
    for msg in ("senha inválida para VENDEDOR FICTICIO UM", "captcha", "conta bloqueada", "403"):
        assert vm.codigo_da_excecao(RuntimeError(msg), "grade") == ("ERRO_INTERNO", "grade")
        assert vm.codigo_da_excecao(vm.ErroRobo(msg), "grade") == ("TELA_MUDOU", "grade")


def test_RN_VIS_005_o_que_a_web_exige_com_fase_sai_com_fase():
    """A paridade das cópias (FASES, FECHADOS_PC_DIAS, códigos) fica em test_T0045_paridade_visitas_web.py."""
    web = _web_visitas()
    for exc in (vm.ErroRobo("x"), RuntimeError("y")):
        cod, fase = vm.codigo_da_excecao(exc, "grade")
        assert cod in web.PEDE_FASE and fase in web.FASES


# ------------------------------------------------------------------ RN-VIS-002: fechados_pc
def test_RN_VIS_002_fechados_pc_janela_de_40_dias_e_formato():
    hoje = date(2026, 11, 27)
    ind = {"20261126": "2026-11-27T07:12:03", "20261018": "2026-10-19T06:00:00",
           "20261017": "2026-10-18T06:00:00",                  # 41 dias: fora
           "20261128": "2026-11-29T06:00:00",                  # futuro: fora
           "202611": "2026-11-27T07:12:03",                    # chave de mês: fora
           "2026113": "2026-11-27T07:12:03", "20261199": "2026-11-27T07:12:03",   # tortas: fora
           "20261120": "não é data"}
    assert vm.fechados_pc(ind, hoje) == {"20261126": "2026-11-27T07:12:03-04:00",
                                         "20261018": "2026-10-19T06:00:00-04:00"}


def test_RN_VIS_002_fechados_pc_hora_com_fuso_vira_manaus_sem_trocar_o_relogio():
    """Hora sem fuso conta como Manaus (só ganha o -04:00); hora com fuso vira Manaus (a regra do núcleo)."""
    hoje = date(2026, 11, 27)
    assert vm.fechados_pc({"20261126": "2026-11-27T06:07:41-04:00"}, hoje) == {
        "20261126": "2026-11-27T06:07:41-04:00"}
    # f6ae758: o fuso pelo núcleo (`vn._quando_manaus`): UTC vira Manaus
    assert vm.fechados_pc({"20261126": "2026-11-27T10:07:41+00:00"}, hoje) == {
        "20261126": "2026-11-27T06:07:41-04:00"}
    assert vm.fechados_pc({"20261126": "2026-11-27T10:07:41+00:00"}, hoje)["20261126"] == \
        vn._quando_manaus("2026-11-27T10:07:41+00:00").isoformat(timespec="seconds")
    assert vm.fechados_pc({}, hoje) == {} and vm.fechados_pc(None, hoje) == {}
    assert vm.fechados_pc({"20261127": "2026-11-27T09:00:00"}, hoje, dias=0) == {
        "20261127": "2026-11-27T09:00:00-04:00"}


def test_RN_VIS_002_fechados_pc_o_site_aceita_e_junta_no_indice(tmp_path):
    """O que o robô manda passa no `confirmar` da web e entra no índice (`pc`), sem a nuvem baixar de novo."""
    web = _web_visitas()
    hoje = date.today()
    d = hoje - timedelta(days=3)
    fpc = vm.fechados_pc({f"{d:%Y%m%d}": f"{d + timedelta(days=1):%Y-%m-%d}T07:00:00"}, hoje)
    vis = web.Visitas(tmp_path)
    vis.confirmar({"epoca": vis.lotes(0)["epoca"], "resultados": [], "fechados_pc": fpc})
    ind = vis.trabalho()["indice"]
    assert f"{d:%Y%m%d}" in ind
    assert web.dias_a_baixar(ind, d, d, hoje) == []


# ------------------------------------------------------------------ §4.5: aviso do botão do PC
@pytest.mark.parametrize("saude,aviso", [
    ({"visitas": {"rodada_ativa": "R20261127T060012"}}, True),
    ({"visitas": {"rodada_ativa": None}}, False),
    ({"visitas": {}}, False),
    ({"ok": True}, False),                                     # web sem visitas
    ({"visitas": "torto"}, False),
    (None, False),                                             # /saude fora do ar
    ({}, False),
])
def test_RN_VIS_004_aviso_site_baixando(saude, aviso):
    assert vm.aviso_site_baixando(saude) == (vm.AVISO_SITE_BAIXANDO if aviso else None)


def test_RN_VIS_004_aviso_texto_do_contrato():
    assert vm.AVISO_SITE_BAIXANDO == ("O site está baixando agora; baixar aqui também pode derrubar a "
                                      "sessão da Máxima. Continuar?")


def test_RN_VIS_004_aviso_com_o_saude_da_web_de_verdade(tmp_path):
    """O bloco `visitas` que a web monta para o /saude liga o aviso durante a rodada e desliga no fim."""
    web = _web_visitas()
    vis = web.Visitas(tmp_path)
    assert vm.aviso_site_baixando({"visitas": vis.saude()}) is None
    con = vis.conceder({"motivo": "pedido", "dias": [f"{date.today() - timedelta(days=1):%Y%m%d}"]})
    assert vm.aviso_site_baixando({"visitas": vis.saude()}) == vm.AVISO_SITE_BAIXANDO
    vis.fim(con["id"], {"codigo": "NADA_A_FAZER"})
    assert vm.aviso_site_baixando({"visitas": vis.saude()}) is None


class _Sessao:
    def __init__(self, status=200, corpo=None, erro=None):
        self.status, self.corpo, self.erro, self.urls = status, corpo, erro, []

    def get(self, url, timeout=None):
        self.urls.append((url, timeout))
        if self.erro:
            raise self.erro
        return types.SimpleNamespace(status_code=self.status, json=lambda: self.corpo)


def test_RN_VIS_004_consultar_saude_nunca_levanta():
    s = _Sessao(corpo={"visitas": {"rodada_ativa": "R1"}})
    assert vm.consultar_saude("https://web.exemplo.test", s) == {"visitas": {"rodada_ativa": "R1"}}
    assert s.urls == [("https://web.exemplo.test/saude", 5)]
    assert vm.consultar_saude("https://web.exemplo.test", _Sessao(status=404)) is None
    assert vm.consultar_saude("https://web.exemplo.test", _Sessao(erro=ConnectionError("x"))) is None
    assert vm.consultar_saude("https://web.exemplo.test", _Sessao(corpo=None, erro=ValueError("json"))) is None


def test_RN_VIS_004_consultar_saude_sem_url_nao_chama_a_rede(monkeypatch):
    import bap_automation as ba
    monkeypatch.setattr(ba, "_segredo_web", lambda *a, **k: "")
    s = _Sessao()
    assert vm.consultar_saude(None, s) is None
    assert s.urls == []


# ------------------------------------------------------------------ Robo: eventos, foto, canal
def test_RN_VIS_005_robo_do_pc_igual_sem_os_parametros_novos(tmp_path):
    log = []
    r = vm.Robo(tmp_path, log.append)
    assert (r.eventos, r.usar_foto, r.canal, r.ao_fechar_dia) == (False, True, None, None)
    r.log("Abrindo o login da Máxima…")
    r.evento("fase", fase="login")                          # sem eventos: mudo
    assert log == ["Abrindo o login da Máxima…"]


def test_RN_VIS_007_log_em_modo_eventos_sem_nome_nem_texto_cru(tmp_path):
    log = []
    r = vm.Robo(tmp_path, log.append, eventos=True)
    r.log(f"  ✖ {VENDEDOR}: senha inválida para {USUARIO}")  # frases livres ficam mudas
    r.evento("vendedor", fase="grade", n=3, dia="20261126", codigo="OK",
             vendedor=VENDEDOR, texto="Usuário ou senha inválidos")   # chave fora da lista: não sai
    r.evento("erro", fase="login", codigo="MAXIMA_SENHA")
    r.evento("dia_fechado", dia="2026-11-26 VENDEDOR", n=None)
    assert log == ["evento=vendedor fase=grade dia=20261126 n=3 codigo=OK",
                   "evento=erro fase=login codigo=MAXIMA_SENHA",
                   "evento=dia_fechado dia=2026-11-26VENDEDOR"]
    for ln in log:
        assert re.fullmatch(r"evento=\S+( (fase|dia|n|codigo)=[A-Za-z0-9_.:-]{1,40})*", ln), ln
        assert USUARIO not in ln and SENHA not in ln and "inválid" not in ln


def test_RN_VIS_007_registrar_falha_so_codigo_e_fase(tmp_path):
    log = []
    r = vm.Robo(tmp_path, log.append, eventos=True)
    r._fase("grade", dia="20261126")
    r._registrar_falha(RuntimeError(f"Target closed while clicking {VENDEDOR} senha={SENHA}"))
    assert (r.codigo, r.fase_erro) == ("NAVEGADOR_FALHOU", "grade")
    assert log == ["evento=fase fase=grade dia=20261126", "evento=erro fase=grade codigo=NAVEGADOR_FALHOU"]


def test_RN_VIS_005_ao_fase_e_progresso(tmp_path):
    vistos = []
    r = vm.Robo(tmp_path, lambda m: None, eventos=True, ao_fase=lambda *a: vistos.append(a))
    r._fase("login")
    r._fase("login")                                           # sem mudança e sem contagem: não repete
    r._fase("filtros", dia="20261126")
    r._fase("grade", feitos=2, total=5)
    r._fase("grade", feitos=3, total=5)
    assert vistos == [("login", None, None, None), ("filtros", "20261126", None, None),
                      ("grade", "20261126", 2, 5), ("grade", "20261126", 3, 5)]
    web = _web_visitas()
    assert {v[0] for v in vistos} <= set(web.FASES)


def test_RN_VIS_005_fase_fora_do_contrato_levanta(tmp_path):
    """f6ae758: `_fase` só aceita as FASES do contrato (§3.3); a fase torta não chega ao log nem ao site."""
    log = []
    r = vm.Robo(tmp_path, log.append, eventos=True)
    for fase in vm.FASES:
        r._fase(fase)
    for torta in ("navegador", "LOGIN", "", None):
        with pytest.raises(ValueError):
            r._fase(torta)
    assert len(log) == len(vm.FASES) and all("navegador" not in m for m in log)


def test_RN_VIS_007_uma_linha_por_vendedor_no_log(tmp_path):
    """f6ae758: o vendedor pronto sai numa linha só (`evento=vendedor`), sem a linha de fase repetida."""
    log = []
    r = vm.Robo(tmp_path, log.append, eventos=True)
    r._fase("grade", dia="20261126")
    r._fase("grade", feitos=1, total=3)
    r._fase("grade", feitos=2, total=3)
    assert log == ["evento=fase fase=grade dia=20261126",
                   "evento=vendedor fase=grade dia=20261126 n=1",
                   "evento=vendedor fase=grade dia=20261126 n=2"]


@pytest.mark.parametrize("pasta,nome,dia,motivo", [
    (VENDEDOR, f"VISITA-{VENDEDOR}-26-11-2026-06-07.xlsx", None, None),
    (VENDEDOR, f"VISITA-{VENDEDOR}-26-11-2026-06-07-2.xlsx", "20261126", None),
    (VENDEDOR, f"VISITA-{VENDEDOR}-26-11-2026-06-07.xlsx", "20261125", "nome"),     # outro dia
    ("../FORA", "VISITA-../FORA-26-11-2026-06-07.xlsx", None, "pasta"),
    ("A/B", "VISITA-A/B-26-11-2026-06-07.xlsx", None, "pasta"),
    ("vendedor ficticio um", "VISITA-vendedor ficticio um-26-11-2026-06-07.xlsx", None, "pasta"),
    ("", "x", None, "pasta"),
    (None, "x", None, "pasta"),
    (VENDEDOR, f"VISITA-{VENDEDOR}..-26-11-2026-06-07.xlsx", None, "nome"),
    (VENDEDOR, f"VISITA-{VENDEDOR}-26-11-2026-06-07.xlsx/../x.xlsx", None, "nome"),
    (VENDEDOR, "VISITA-OUTRO VENDEDOR FICTICIO-26-11-2026-06-07.xlsx", None, "nome"),
    (VENDEDOR, f"VISITA-{VENDEDOR}-31-02-2026-06-07.xlsx", None, "nome"),          # data impossível
    (VENDEDOR, f"VISITA-{VENDEDOR}-26-11-2026-25-07.xlsx", None, "nome"),          # hora impossível
    (VENDEDOR, None, None, "nome"),
])
def test_RN_VIS_003_conferir_importado_regra_unica_do_nome(pasta, nome, dia, motivo):
    """f6ae758: `conferir_importado` é a regra única do Excel que vem da nuvem (função pura)."""
    m, dq = vm.conferir_importado(pasta, nome, dia)
    assert m == motivo
    if motivo is None:
        assert dq == (date(2026, 11, 26), datetime(2026, 11, 26, 6, 7))
    else:
        assert dq is None


def test_RN_VIS_003_conferir_importado_e_o_mesmo_no_robo_e_na_gravacao(tmp_path):
    """O mesmo motivo sai da importação (`_validar_lote_visitas_web`) e da última trava (`gravar_excel_importado`)."""
    for pasta, nome in (("../FORA", "VISITA-../FORA-26-11-2026-06-07.xlsx"),
                        (VENDEDOR, "VISITA-OUTRO VENDEDOR FICTICIO-26-11-2026-06-07.xlsx")):
        motivo, _ = vm.conferir_importado(pasta, nome)
        with pytest.raises(ValueError, match=motivo):
            vm.gravar_excel_importado(tmp_path, pasta, nome, b"x")


def test_RN_VIS_005_no_login_so_o_caminho():
    assert vm._no_login("https://app.exemplo.test/login?x=1") == (True, False)
    assert vm._no_login("https://app.exemplo.test/verificacao") == (False, True)
    assert vm._no_login("https://app.exemplo.test/home?voltar=/login#/verificacao") == (False, False)
    assert vm._no_login(None) == (False, False)


class _Pagina:
    """Uma página do Playwright, falsa: guarda o que o robô fez."""

    def __init__(self, depois_url="https://app.exemplo.test/home", msg="", captcha=False, status=200,
                 corpo=""):
        self.url = "https://app.exemplo.test/login"
        self._depois, self.msg, self.captcha, self.status, self.corpo = depois_url, msg, captcha, status, corpo
        self.feito, self.fotos = [], 0

    def goto(self, url, wait_until=None, timeout=None):
        self.feito.append(("goto", timeout))
        return types.SimpleNamespace(status=self.status)

    def wait_for_selector(self, sel, timeout=None):
        self.feito.append(("esperar", sel))

    def fill(self, sel, valor):
        self.feito.append(("fill", sel))

    def click(self, sel, **k):
        self.feito.append(("click", sel))
        self.url = self._depois

    def evaluate(self, js, *a):
        if js == vm.CAPTCHA_JS:
            return self.captcha
        if "innerText.trim()" in js:
            return self.msg
        return self.corpo

    def screenshot(self, **k):
        self.fotos += 1

    def set_default_timeout(self, t):
        pass


def _entrar(tmp_path, pagina, eventos=True):
    log = []
    r = vm.Robo(tmp_path, log.append, eventos=eventos, foto=not eventos)
    r.page = pagina
    try:
        r.entrar(USUARIO, SENHA)
        return None, log, r
    except vm.ErroRobo as e:
        return e, log, r


@pytest.mark.parametrize("pagina,codigo", [
    (lambda: _Pagina(depois_url="https://app.exemplo.test/login", msg="Usuário ou senha inválidos"),
     "MAXIMA_SENHA"),
    (lambda: _Pagina(depois_url="https://app.exemplo.test/login", msg="Login falhou de um jeito novo"),
     "MAXIMA_SENHA"),
    (lambda: _Pagina(depois_url="https://app.exemplo.test/login", captcha=True), "MAXIMA_CAPTCHA"),
    (lambda: _Pagina(depois_url="https://app.exemplo.test/verificacao",
                     corpo="Enviamos um código por SMS para o seu celular"), "MAXIMA_CONFIRMACAO"),
    (lambda: _Pagina(depois_url="https://app.exemplo.test/login", msg="Conta bloqueada"), "MAXIMA_BLOQUEIO"),
    (lambda: _Pagina(status=403), "MAXIMA_BLOQUEIO"),
])
def test_RN_VIS_005_senha_recusada_pausa_sem_segunda_tentativa(tmp_path, pagina, codigo):
    pg = pagina()
    erro, log, r = _entrar(tmp_path, pg)
    assert erro is not None and (erro.codigo, erro.fase) == (codigo, "login")
    assert [x for x in pg.feito if x[0] == "click"].__len__() <= 1          # um "Entrar" só, nunca repete
    assert [x for x in pg.feito if x[0] == "goto"].__len__() == 1
    assert pg.fotos == 0
    assert all(SENHA not in m and USUARIO not in m for m in log)
    assert SENHA not in str(erro) and USUARIO not in str(erro)
    assert "inválid" not in str(erro) and "jeito novo" not in str(erro)   # o texto cru não sai na nuvem
    assert vm.codigo_da_excecao(erro, r.fase) == (codigo, "login")
    web = _web_visitas()
    assert codigo in web.PAUSAM


def test_RN_VIS_005_login_ok_segue(tmp_path):
    erro, log, r = _entrar(tmp_path, _Pagina())
    assert erro is None and r.fase == "login"
    assert log == ["evento=fase fase=login"]


def test_RN_VIS_005_no_pc_a_mensagem_da_maxima_continua_na_tela(tmp_path):
    pg = _Pagina(depois_url="https://app.exemplo.test/login", msg="Usuário ou senha inválidos")
    erro, log, _ = _entrar(tmp_path, pg, eventos=False)
    assert erro.codigo == "MAXIMA_SENHA"
    assert str(erro) == "A Máxima recusou o login: Usuário ou senha inválidos"
    assert "Abrindo o login da Máxima…" in log


class _Navegador:
    def __init__(self, pagina):
        self.pagina, self.fechado = pagina, False

    def new_context(self, **k):
        nav = self

        class Ctx:
            def add_init_script(self, js):
                pass

            def new_page(self):
                return nav.pagina
        return Ctx()

    def close(self):
        self.fechado = True


class _Chromium:
    def __init__(self, pagina, falha=False):
        self.pagina, self.falha, self.launches = pagina, falha, []

    def launch(self, **kw):
        self.launches.append(kw)
        if self.falha:
            raise RuntimeError("Executable doesn't exist (fictício)")
        self.nav = _Navegador(self.pagina)
        return self.nav


@pytest.fixture
def playwright_falso(monkeypatch):
    """`playwright.sync_api.sync_playwright` falso (sem navegador)."""
    estado = types.SimpleNamespace(chromium=None)

    class _P:
        def __enter__(self):
            return types.SimpleNamespace(chromium=estado.chromium)

        def __exit__(self, *a):
            return False
    pkg = types.ModuleType("playwright")
    api = types.ModuleType("playwright.sync_api")
    api.sync_playwright = _P
    pkg.sync_api = api
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    return estado


def _robo_nuvem(tmp_path, log, playwright_falso, monkeypatch, dias_ok, erro_em=None, parar_no_primeiro=False):
    """Robo da nuvem com a Máxima falsa: cada dia grava o Espelho inventado no ANALITICO."""
    pg = _Pagina()
    playwright_falso.chromium = _Chromium(pg)
    fechados = []
    parar = threading.Event()

    def ao_fechar_dia(d, r):
        fechados.append((d, r))
        if parar_no_primeiro:
            parar.set()
    robo = vm.Robo(tmp_path, log.append, parar, canal="chromium", foto=False, eventos=True,
                   ao_fechar_dia=ao_fechar_dia)
    monkeypatch.setattr(robo, "abrir_maxgestao", lambda: robo._fase("inicio"))
    monkeypatch.setattr(robo, "abrir_auditoria", lambda: robo._fase("filtros"))
    monkeypatch.setattr(robo, "_nomes_equipe", lambda: [VENDEDOR])

    def baixar_dia(d, progresso=None):
        robo._checar()
        robo._fase("grade", dia=f"{d:%Y%m%d}")
        robo.log(f"  ✔ {VENDEDOR}")
        if erro_em == d:
            raise RuntimeError(f"Target closed ao abrir {VENDEDOR}")
        arq = vm.arquivo_analitico(tmp_path, VENDEDOR, d, datetime(d.year, d.month, d.day, 6, 7), ".xlsx")
        espelho_xlsx(arq, d)
        robo.vendedores = 1
        return {"ok": [(VENDEDOR, arq)], "erro": [], "extras": {}}
    monkeypatch.setattr(robo, "baixar_dia", baixar_dia)
    return robo, pg, fechados


def test_RN_VIS_005_robo_da_nuvem_eventos_sem_nome_e_sem_print(tmp_path, playwright_falso, monkeypatch):
    log = []
    d1, d2 = date(2026, 11, 24), date(2026, 11, 25)
    robo, pg, fechados = _robo_nuvem(tmp_path, log, playwright_falso, monkeypatch, [d1, d2])
    linhas = robo.rodar(USUARIO, SENHA, [d1, d2], [])
    assert linhas == {d1: 1, d2: 1}
    assert playwright_falso.chromium.launches == [{"headless": True, "args": ["--disable-dev-shm-usage"]}]
    assert playwright_falso.chromium.nav.fechado
    assert [d for d, _ in fechados] == [d1, d2]
    assert fechados[0][1]["linhas"] == 1 and fechados[0][1]["vendedores"] == 1
    assert len(fechados[0][1]["ok"]) == 1
    assert all(ln.startswith("evento=") for ln in log), log
    texto = "\n".join(log)
    for proibido in (*NOMES_FICTICIOS, USUARIO, SENHA, "Máxima", "✔"):
        assert proibido not in texto
    assert "evento=dia_fechado dia=20261124 n=1" in log and "evento=dia_fechado dia=20261125 n=1" in log
    assert pg.fotos == 0 and not (vn.pasta_visitas(tmp_path) / "_erros").exists()
    assert vn.dia_fechado(tmp_path, d1) or f"{d1:%Y%m%d}" in vn.indice(tmp_path)


def test_RN_VIS_005_ao_fechar_dia_pode_parar_o_proximo_dia(tmp_path, playwright_falso, monkeypatch):
    log = []
    d1, d2 = date(2026, 11, 24), date(2026, 11, 25)
    robo, _, fechados = _robo_nuvem(tmp_path, log, playwright_falso, monkeypatch, [d1, d2],
                                    parar_no_primeiro=True)
    with pytest.raises(vm.Cancelado):
        robo.rodar(USUARIO, SENHA, [d1, d2], [])
    assert [d for d, _ in fechados] == [d1]
    assert robo.codigo is None                                # cancelar não é falha
    assert playwright_falso.chromium.nav.fechado


def test_RN_VIS_005_queda_no_meio_vira_codigo_e_fase_sem_print(tmp_path, playwright_falso, monkeypatch):
    log = []
    d1, d2 = date(2026, 11, 24), date(2026, 11, 25)
    robo, pg, fechados = _robo_nuvem(tmp_path, log, playwright_falso, monkeypatch, [d1, d2], erro_em=d2)
    with pytest.raises(RuntimeError):
        robo.rodar(USUARIO, SENHA, [d1, d2], [])
    assert (robo.codigo, robo.fase_erro) == ("NAVEGADOR_FALHOU", "grade")
    assert [d for d, _ in fechados] == [d1]                   # o dia que terminou já foi entregue
    assert log[-1] == "evento=erro fase=grade codigo=NAVEGADOR_FALHOU"
    assert pg.fotos == 0 and robo.foto is None
    assert not any(n in "\n".join(log) for n in NOMES_FICTICIOS)


def test_RN_VIS_005_navegador_que_nao_abre_e_navegador_falhou(tmp_path, playwright_falso):
    playwright_falso.chromium = _Chromium(_Pagina(), falha=True)
    log = []
    robo = vm.Robo(tmp_path, log.append, canal="chromium", foto=False, eventos=True)
    with pytest.raises(vm.ErroRobo):
        robo.rodar(USUARIO, SENHA, [date(2026, 11, 24)], [])
    assert (robo.codigo, robo.fase_erro) == ("NAVEGADOR_FALHOU", "inicio")
    assert log == ["evento=fase fase=inicio", "evento=erro fase=inicio codigo=NAVEGADOR_FALHOU"]


def test_RN_VIS_005_navegador_do_pc_que_nao_abre_sai_com_fase_inicio(tmp_path, playwright_falso, monkeypatch):
    """ed640e1: sem `canal` (o PC), a falha de abrir vem sem código; enquanto abre, vira NAVEGADOR_FALHOU/inicio."""
    playwright_falso.chromium = _Chromium(_Pagina(), falha=True)
    monkeypatch.setattr(vm, "_rodar", lambda *a, **k: 1)            # sem instalar nada
    robo = vm.Robo(tmp_path, lambda m: None, eventos=True)
    with pytest.raises(vm.ErroRobo) as e:
        robo.rodar(USUARIO, SENHA, [date(2026, 11, 24)], [])
    assert e.value.codigo is None
    assert (robo.codigo, robo.fase_erro) == ("NAVEGADOR_FALHOU", "inicio")


def test_RN_VIS_005_depois_de_abrir_o_navegador_o_codigo_e_o_da_fase(tmp_path, playwright_falso, monkeypatch):
    """ed640e1: com o navegador aberto, o tempo esgotado no login é MAXIMA_FORA/login (não NAVEGADOR_FALHOU)."""
    pg = _Pagina()
    playwright_falso.chromium = _Chromium(pg)

    def goto(*a, **k):
        raise TimeoutError("Timeout 60000ms exceeded")
    pg.goto = goto
    robo = vm.Robo(tmp_path, lambda m: None, canal="chromium", foto=False, eventos=True)
    with pytest.raises(TimeoutError):
        robo.rodar(USUARIO, SENHA, [date(2026, 11, 24)], [])
    assert (robo.codigo, robo.fase_erro) == ("MAXIMA_FORA", "login")


def test_RN_VIS_005_todas_as_fases_da_rodada_sao_as_do_contrato(tmp_path, playwright_falso, monkeypatch):
    """ed640e1: a fase "navegador" saiu; cada `fase` do log e do `ao_fase` está nas FASES da web."""
    log = []
    d1 = date(2026, 11, 24)
    robo, _, _ = _robo_nuvem(tmp_path, log, playwright_falso, monkeypatch, [d1])
    vistos = []
    robo.ao_fase = lambda fase, *a: vistos.append(fase)
    robo.rodar(USUARIO, SENHA, [d1], [])
    fases = {m.split("fase=")[1].split()[0] for m in log if "fase=" in m} | set(vistos)
    assert "navegador" not in fases and fases <= set(_web_visitas().FASES)
    assert "navegador" not in vm.FASES


@pytest.mark.parametrize("url", [
    "https://app.exemplo.test/home?voltar=/login",                 # /login só na query
    "https://app.exemplo.test/home#/login",                        # só no fragmento
    "https://verificacao.exemplo.test/home",                       # "verificacao" só no host
    "https://app.exemplo.test/painel?etapa=confirmar-dispositivo",
    # 🟡 A do revisor: o caminho conta só por segmento inteiro, da lista fechada (verificacao, mfa, 2fa, otp,
    # trocar-senha, nova-senha, confirmar-dispositivo); pedaço de palavra não é verificação
    "https://app.exemplo.test/hotpage",
    "https://app.exemplo.test/devices/home",
    "https://app.exemplo.test/autenticacao/callback",
    "https://app.exemplo.test/auth/autenticar",
    "https://app.exemplo.test/sso/confirm-redirect",
])
def test_RN_VIS_005_login_conservador_olha_so_o_caminho_da_url(url):
    """ed640e1: a regra do §5.1 olha só o caminho da URL; fora do /login e da verificação, segue (None)."""
    for texto, captcha in (("Usuário ou senha inválidos", False), ("Confirme o seu dispositivo", True),
                           ("Conta bloqueada", False)):
        assert vm.classificar_login(url, texto, captcha, None) is None
    assert vm.classificar_login(url, "", False, 403) == "MAXIMA_BLOQUEIO"


def test_RN_VIS_005_captcha_so_visivel_e_fora_do_selo():
    """ed640e1: o JS do captcha só conta caixa visível de 60×40 ou mais e ignora o selo `.grecaptcha-badge`."""
    js = vm.CAPTCHA_JS
    assert ".grecaptcha-badge" in js and "r.width >= 60" in js and "r.height >= 40" in js
    for regra in ("visibility !== 'hidden'", "display !== 'none'", "opacity !== '0'"):
        assert regra in js
    assert '[class*="captcha" i]' not in js and '[id*="captcha" i]' not in js


def test_RN_VIS_005_entrar_com_query_de_login_nao_trava(tmp_path):
    """ed640e1: saiu do /login para uma URL com "/login" só na query: é login ok, sem esperar 45 s."""
    pg = _Pagina(depois_url="https://app.exemplo.test/home?voltar=/login", msg="Usuário ou senha inválidos")
    erro, log, r = _entrar(tmp_path, pg)
    assert erro is None and log == ["evento=fase fase=login"]


def test_RN_VIS_005_canal_do_pc_continua_edge_chrome_chromium():
    tentados = []

    class Ch:
        def launch(self, **kw):
            tentados.append(kw.get("channel"))
            if kw.get("channel") != "chrome":
                raise RuntimeError("não instalado")
            return "nav"
    assert vm._abrir_navegador(types.SimpleNamespace(chromium=Ch()), False, lambda m: None) == "nav"
    assert tentados == ["msedge", "chrome"]
    tentados.clear()
    assert vm._abrir_navegador(types.SimpleNamespace(chromium=Ch()), False, lambda m: None, "chrome") == "nav"
    assert tentados == ["chrome"]


def test_RN_VIS_005_nuvem_sem_screenshot_no_codigo_do_robo():
    """D5: o único print do robô é o `foto_do_erro`, e ele sai mudo com `foto=False`."""
    fonte = (RAIZ / "visitas_maxima.py").read_text(encoding="utf-8")
    chamadas = re.findall(r"\.screenshot\(", fonte)
    assert len(chamadas) == 1
    corpo = fonte.split("def foto_do_erro", 1)[1].split("def ", 1)[0]
    assert "not self.usar_foto" in corpo and ".screenshot(" in corpo
    assert not re.search(r"\.on\(\s*[\"']console", fonte)
    assert not re.search(r"tracing\.start|record_video|record_har", fonte)


# ------------------------------------------------------------------ RN-VIS-003: gravar_excel_importado
def _nome(d=date(2026, 11, 26), pasta=VENDEDOR, hhmm="06-07"):
    return nome_arquivo(pasta, d, hhmm)


def test_RN_VIS_003_importacao_nunca_sobrescreve_grava_com_sufixo(tmp_path):
    a, st = vm.gravar_excel_importado(tmp_path, VENDEDOR, _nome(), b"conteudo-ficticio-1")
    assert st == "novo" and a.name == _nome() and a.read_bytes() == b"conteudo-ficticio-1"
    b, st = vm.gravar_excel_importado(tmp_path, VENDEDOR, _nome(), b"conteudo-ficticio-2")
    assert st == "novo" and b.name == _nome().replace(".xlsx", "-2.xlsx")
    c, st = vm.gravar_excel_importado(tmp_path, VENDEDOR, _nome(), b"conteudo-ficticio-3")
    assert c.name == _nome().replace(".xlsx", "-3.xlsx")
    assert a.read_bytes() == b"conteudo-ficticio-1" and b.read_bytes() == b"conteudo-ficticio-2"
    assert sorted(p.name for p in a.parent.iterdir()) == sorted([a.name, b.name, c.name])   # sem .tmp


def test_RN_VIS_003_mesmo_sha_pula(tmp_path):
    a, _ = vm.gravar_excel_importado(tmp_path, VENDEDOR, _nome(), b"conteudo-ficticio-1")
    vm.gravar_excel_importado(tmp_path, VENDEDOR, _nome(), b"conteudo-ficticio-2")
    m1 = a.stat().st_mtime_ns
    for conteudo, nome in ((b"conteudo-ficticio-1", a.name),
                           (b"conteudo-ficticio-2", _nome().replace(".xlsx", "-2.xlsx"))):
        f, st = vm.gravar_excel_importado(tmp_path, VENDEDOR, _nome(), conteudo)
        assert (st, f.name) == ("igual", nome)
    assert len(list(a.parent.iterdir())) == 2 and a.stat().st_mtime_ns == m1


def test_RN_VIS_003_arquivo_do_pc_com_o_mesmo_nome_fica(tmp_path):
    """O Excel que o botão do PC baixou no mesmo minuto não é tocado: o da nuvem vai com sufixo."""
    d = date(2026, 11, 26)
    pc = vm.arquivo_analitico(tmp_path, VENDEDOR, d, datetime(2026, 11, 26, 6, 7), ".xlsx")
    pc.parent.mkdir(parents=True, exist_ok=True)
    pc.write_bytes(b"baixado-no-pc")
    f, st = vm.gravar_excel_importado(tmp_path, VENDEDOR, _nome(d), b"baixado-na-nuvem")
    assert st == "novo" and f != pc and pc.read_bytes() == b"baixado-no-pc"


@pytest.mark.parametrize("pasta,nome", [
    ("../FORA", "VISITA-../FORA-26-11-2026-06-07.xlsx"),
    (VENDEDOR, f"VISITA-{VENDEDOR}-26-11-2026-06-07.xlsx/../../x.xlsx"),
    (VENDEDOR, f"VISITA-{VENDEDOR}/..-26-11-2026-06-07.xlsx"),
    (VENDEDOR, f"VISITA-{VENDEDOR}\\x-26-11-2026-06-07.xlsx"),
    (VENDEDOR, "VISITA-OUTRO VENDEDOR FICTICIO-26-11-2026-06-07.xlsx"),   # pasta ≠ nome
    ("vendedor ficticio um", "VISITA-vendedor ficticio um-26-11-2026-06-07.xlsx"),   # não é o nome_limpo
    (VENDEDOR, f"VISITA-{VENDEDOR}..-26-11-2026-06-07.xlsx"),
    (VENDEDOR, "planilha.xlsx"),
    (VENDEDOR, ""),
])
def test_RN_VIS_003_nome_com_barra_ou_ponto_ponto_recusado(tmp_path, pasta, nome):
    with pytest.raises(ValueError):
        vm.gravar_excel_importado(tmp_path, pasta, nome, b"x")
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


# ------------------------------------------------------------------ depois_de_baixar fora do executar
def test_RN_VIS_003_executar_chama_depois_de_baixar_uma_vez(tmp_path, monkeypatch):
    vezes = []
    monkeypatch.setattr(vm, "plano", lambda *a, **k: ([], []))
    monkeypatch.setattr(vm, "depois_de_baixar",
                        lambda raiz, log: vezes.append(Path(raiz)) or {"excel": "x", "por_cliente": None})
    log = []
    res = vm.executar(tmp_path, date(2026, 11, 24), date(2026, 11, 25), USUARIO, SENHA, log.append)
    assert vezes == [tmp_path]
    assert res["excel"] == "x" and res["erro"] == ""
    assert log == ["Tudo já baixado nesse período (dias fechados)."]


def test_RN_VIS_003_depois_de_baixar_cada_parte_falha_sozinha(tmp_path, monkeypatch):
    def quebra(*a, **k):
        raise OSError("disco (fictício)")
    monkeypatch.setattr(vn, "atualizar_acompanhamento", quebra)
    feitos = []
    monkeypatch.setattr(vn, "atualizar_por_cliente", lambda *a, **k: feitos.append("por_cliente") or 0)
    res = vm.depois_de_baixar(tmp_path, lambda m: None)
    assert set(res) >= {"excel", "por_cliente"} and "por_cliente" in feitos


# ------------------------------------------------------------------ a tela do PC (Tkinter, só com display)
def _tk_ou_pula():
    try:
        import tkinter as tk
    except ImportError:
        pytest.skip("sem tkinter neste Python")
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        pytest.skip("sem display (rode com xvfb-run)")
    try:
        r = tk.Tk()
        r.destroy()
    except tk.TclError:
        pytest.skip("sem display")
    return tk


def _janela(monkeypatch, tmp_path, saude, resposta):
    tk = _tk_ou_pula()
    from tkinter import messagebox
    perguntas, executados = [], []
    monkeypatch.setattr(vm, "ler_config", lambda: {"usuario": USUARIO})     # nunca o visitas_config.json
    monkeypatch.setattr(vm, "gravar_usuario", lambda u: None)
    monkeypatch.setattr(vm, "tem_playwright", lambda: True)
    monkeypatch.setattr(vm, "plano", lambda raiz, de, ate, refazer=False: ([ate], []))
    monkeypatch.setattr(vm, "consultar_saude", lambda *a, **k: saude)
    monkeypatch.setattr(vm, "executar", lambda *a, **k: executados.append(a[1:3]) or {"dias": [], "erro": ""})
    monkeypatch.setattr(messagebox, "askyesno", lambda t, m, **k: perguntas.append(m) or resposta)
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: perguntas.append(a[1]))
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: None)
    w = vm.janela(raiz=tmp_path)
    try:
        w.update()

        def filhos(x):
            for c in x.winfo_children():
                yield c
                yield from filhos(c)
        todos = list(filhos(w))
        senha = next(c for c in todos if c.winfo_class() == "TEntry" and str(c.cget("show")) == "•")
        senha.insert(0, SENHA)
        baixar = next(c for c in todos if c.winfo_class() == "TButton" and c.cget("text") == "Baixar")
        baixar.invoke()
        senha_depois = senha.get()
        # a thread do download fala com o Tk: só com o mainloop rodando (como na tela de verdade)
        fim = [0]

        def vigiar():
            fim[0] += 1
            if executados or fim[0] > 60:
                w.quit()
            else:
                w.after(50, vigiar)
        w.after(50, vigiar)
        w.mainloop()
        return perguntas, executados, senha_depois
    finally:
        try:
            w.destroy()
        except tk.TclError:
            pass


def test_RN_VIS_004_botao_do_pc_pergunta_quando_o_site_esta_baixando_e_respeita_o_nao(monkeypatch, tmp_path):
    perguntas, executados, senha = _janela(monkeypatch, tmp_path,
                                           {"visitas": {"rodada_ativa": "R20261127T060012"}}, False)
    assert perguntas == [vm.AVISO_SITE_BAIXANDO]
    assert executados == []
    assert senha == SENHA                                     # nada começou: a senha fica no campo


def test_RN_VIS_004_botao_do_pc_segue_com_o_sim(monkeypatch, tmp_path):
    perguntas, executados, senha = _janela(monkeypatch, tmp_path,
                                           {"visitas": {"rodada_ativa": "R20261127T060012"}}, True)
    assert perguntas == [vm.AVISO_SITE_BAIXANDO]
    assert len(executados) == 1 and senha == ""


def test_RN_VIS_004_botao_do_pc_sem_rodada_no_site_nao_pergunta(monkeypatch, tmp_path):
    for saude in ({"visitas": {"rodada_ativa": None}}, None):
        perguntas, executados, _ = _janela(monkeypatch, tmp_path, saude, True)
        assert perguntas == [] and len(executados) == 1


# ------------------------------------------------------------------ apoio
_WEB = {}


@pytest.fixture(scope="module", autouse=True)
def _web_sai_no_fim():
    """web/app sai do sys.path e do sys.modules no fim do módulo (o padrão do T-0017)."""
    antes = set(sys.modules)
    yield
    while str(RAIZ / "web") in sys.path:
        sys.path.remove(str(RAIZ / "web"))
    for k in set(sys.modules) - antes:
        if k == "app" or k.startswith("app."):
            del sys.modules[k]
    _WEB.clear()


def _web_visitas():
    """web/app/visitas de verdade (só biblioteca padrão)."""
    if "v" not in _WEB:
        sys.path.insert(0, str(RAIZ / "web"))
        from app import visitas
        _WEB["v"] = visitas
    return _WEB["v"]
