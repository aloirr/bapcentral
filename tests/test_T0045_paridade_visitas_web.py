"""T-0045: paridade entre a regra do índice de baixas da rota
(`visitas_nucleo.juntar_baixado`, `dia_fechado_no_indice`, `dias_a_baixar`)
e o espelho da web (`web/app/visitas.py`). O Render publica só
`web/`, por isso a web tem uma cópia. Este teste prova que as duas dão a
mesma resposta.

Regra: RN-VIS-002. Para cada dia vale a maior hora de baixa entre a nuvem e o
PC; no empate fica a nuvem (contrato §3.1). Hora sem fuso conta como Manaus.
O dia fecha quando foi baixado num dia (Manaus) depois dele, e a rodada nunca
passa de hoje.
Também RN-VIS-007 (RD-0112, RD-0114): a rede de dado pessoal (`_REDE` /
`RE_PESSOAL`), os `TIPOS_ACHADO` e as colunas do Espelho que nunca saem
(`_FORA_DO_ESPELHO` / `COLUNAS_PROIBIDAS`). Um lado que muda sem o outro
reprova. Entra a comparação núcleo × web; o que olha só o núcleo
(a lista em si, as permitidas, o cabeçalho) fica em
tests/test_T0045_visitas_nucleo.py (RD-0149). No fim, a comparação robô ×
web das cópias de FASES, FECHADOS_PC_DIAS e dos códigos (RD-0174), que pula
sem o robô da T-0045 no main.

Datas fictícias, sem dado de cliente.
"""
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import visitas_nucleo as vn

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def web_app():
    """web/app (visitas): sai do sys.modules no fim (o padrão do T-0017)."""
    antes = set(sys.modules)
    sys.path.insert(0, str(RAIZ / "web"))
    try:
        from app import visitas
        yield types.SimpleNamespace(visitas=visitas)
    finally:
        sys.path.remove(str(RAIZ / "web"))
        for k in set(sys.modules) - antes:
            if k == "app" or k.startswith("app."):
                del sys.modules[k]


def _iguais(web, nuvem, pc):
    r = vn.juntar_baixado(nuvem, pc)
    assert web.visitas.juntar_baixado(nuvem, pc) == r
    return r


# ------------------------------------------------------------------ o empate
def test_RN_VIS_002_empate_fica_com_a_nuvem_nos_dois(web_app):
    """O mesmo instante escrito de 3 jeitos (UTC, Manaus e sem fuso) é empate,
    e o empate é da nuvem. Os erros_vendedor/refeito acompanham a nuvem."""
    nuvem = {"20261125": {"baixado_em": "2026-11-26T11:00:00+00:00", "erros_vendedor": 1,
                          "refeito": True},
             "20261124": "2026-11-25T07:00:00-04:00"}
    pc = {"20261125": "2026-11-26T07:00:00-04:00",
          "20261124": "2026-11-25T07:00:00"}
    r = _iguais(web_app, nuvem, pc)
    assert {k: v["origem"] for k, v in r.items()} == {"20261124": "nuvem", "20261125": "nuvem"}
    assert r["20261125"]["erros_vendedor"] == 1 and r["20261125"]["refeito"] is True
    # um segundo a mais no PC: o PC ganha, sem os campos da nuvem
    r = _iguais(web_app, nuvem, {"20261125": "2026-11-26T07:00:01-04:00"})
    assert r["20261125"] == {"baixado_em": "2026-11-26T07:00:01-04:00", "origem": "pc"}
    # o empate trocando os lados: continua sendo quem veio como nuvem
    assert _iguais(web_app, pc, nuvem)["20261124"]["origem"] == "nuvem"


# ------------------------------------------------------------------ hora sem fuso = Manaus
def test_RN_VIS_002_hora_sem_fuso_e_manaus_nos_dois(web_app):
    r = _iguais(web_app, {}, {"20261126": "2026-11-27T06:30:00"})
    assert r["20261126"] == {"baixado_em": "2026-11-27T06:30:00-04:00", "origem": "pc"}
    # 23h30 de Manaus sem fuso não fecha o dia; a mesma hora em UTC (19h30) também não
    for v in ("2026-11-26T23:30:00", "2026-11-26T23:30:00+00:00"):
        ind = {"20261126": v}
        assert vn.dia_fechado_no_indice(ind, date(2026, 11, 26)) is False
        assert web_app.visitas.dia_fechado_no_indice(ind, date(2026, 11, 26)) is False
    # 03h00 UTC do dia 27 = 23h00 do dia 26 em Manaus: ainda não fecha
    ind = {"20261126": "2026-11-27T03:00:00+00:00"}
    assert vn.dia_fechado_no_indice(ind, date(2026, 11, 26)) is False
    assert web_app.visitas.dia_fechado_no_indice(ind, date(2026, 11, 26)) is False
    # 04h00 UTC do dia 27 = 00h00 do dia 27 em Manaus: fecha
    ind = {"20261126": "2026-11-27T04:00:00+00:00"}
    assert vn.dia_fechado_no_indice(ind, date(2026, 11, 26)) is True
    assert web_app.visitas.dia_fechado_no_indice(ind, date(2026, 11, 26)) is True
    # datetime em vez de texto (o PC anota assim)
    agora = datetime(2026, 11, 27, 6, 0, tzinfo=timezone(timedelta(hours=-4)))
    _iguais(web_app, {"20261126": agora.isoformat()}, {"20261126": agora.replace(tzinfo=None).isoformat()})


# ------------------------------------------------------------------ o dia de hoje
def test_RN_VIS_002_hoje_entra_aberto_e_nada_passa_de_hoje_nos_dois(web_app):
    hoje = date(2026, 11, 27)
    ind = {"20261127": "2026-11-27T06:10:00-04:00",          # hoje, baixado hoje: aberto
           "20261126": "2026-11-27T06:00:00-04:00",          # ontem, baixado hoje: fechado
           "20261125": "2026-11-25T22:00:00"}                # baixado no próprio dia: aberto
    for refazer in (False, True):
        a = vn.dias_a_baixar(ind, date(2026, 11, 24), date(2026, 12, 3), hoje, refazer)
        assert web_app.visitas.dias_a_baixar(ind, date(2026, 11, 24), date(2026, 12, 3), hoje, refazer) == a
        assert max(a) == hoje
    a = vn.dias_a_baixar(ind, date(2026, 11, 24), date(2026, 12, 3), hoje)
    assert a == [date(2026, 11, 24), date(2026, 11, 25), hoje]
    # só hoje, e um intervalo que começa depois de hoje (vazio)
    for de, ate in ((hoje, hoje), (hoje + timedelta(days=1), hoje + timedelta(days=5))):
        assert web_app.visitas.dias_a_baixar(ind, de, ate, hoje) == vn.dias_a_baixar(ind, de, ate, hoje)
    assert vn.dias_a_baixar(ind, hoje + timedelta(days=1), hoje + timedelta(days=5), hoje) == []


# ------------------------------------------------------------------ um intervalo grande
def _indice_grande(inicio, n, lado):
    """Índice fictício e determinístico: baixas no próprio dia, no dia seguinte,
    em UTC, sem fuso e com dict; 1 dia em cada 10 sem baixa nos dois lados."""
    ind = {}
    for k in range(n):
        d = inicio + timedelta(days=k)
        chave = f"{d:%Y%m%d}"
        r = (k * 7 + (3 if lado == "pc" else 0)) % 6
        prox = d + timedelta(days=1)
        if r == 0 or k % 10 == 0:
            continue
        if r == 1:
            ind[chave] = f"{d:%Y-%m-%d}T22:00:00-04:00"
        elif r == 2:
            ind[chave] = f"{prox:%Y-%m-%d}T10:00:00+00:00"
        elif r == 3:
            ind[chave] = f"{prox:%Y-%m-%d}T06:{k % 60:02d}:00"
        elif r == 4:
            ind[chave] = {"baixado_em": f"{prox:%Y-%m-%d}T06:00:00-04:00", "erros_vendedor": k % 3,
                          "refeito": bool(k % 2)}
        else:
            ind[chave] = f"{prox:%Y-%m-%d}T03:59:59+00:00"     # 23h59 do próprio dia em Manaus
    return ind


def test_RN_VIS_002_intervalo_grande_da_o_mesmo_indice_e_os_mesmos_dias(web_app):
    inicio, hoje = date(2025, 1, 1), date(2026, 11, 27)
    n = (hoje - inicio).days                                    # baixas até ontem
    nuvem, pc = _indice_grande(inicio, n, "nuvem"), _indice_grande(inicio, n, "pc")
    ind = _iguais(web_app, nuvem, pc)
    assert len(ind) > 500
    assert {v["origem"] for v in ind.values()} == {"nuvem", "pc"}
    de, ate = inicio, inicio + timedelta(days=n + 30)          # passa de hoje de propósito
    for refazer in (False, True):
        a = vn.dias_a_baixar(ind, de, ate, hoje, refazer)
        assert web_app.visitas.dias_a_baixar(ind, de, ate, hoje, refazer) == a
        assert a and max(a) <= hoje
    todos = vn.dias_a_baixar(ind, de, ate, hoje, True)
    assert todos[0] == inicio and todos[-1] == hoje and len(todos) == (hoje - inicio).days + 1
    abertos = vn.dias_a_baixar(ind, de, ate, hoje)
    assert 0 < len(abertos) < len(todos)
    for d in todos:
        assert web_app.visitas.dia_fechado_no_indice(ind, d) == vn.dia_fechado_no_indice(ind, d), d


# ------------------------------------------------------------------ a rede de dado pessoal (RN-VIS-007; RD-0112, RD-0114)
# O cron (rota) e a web varrem o Espelho com a mesma rede (contrato §3.6). A
# web guarda uma cópia: qualquer mudança de um lado só reprova aqui.
_AMOSTRAS = (
    "fulano@exemplo.test", "x.y+z@a-b.c.d", "sem arroba",
    "12.345.678/0001-90", "12345678000190", "112345678000190", "CNPJ 12.345.678/0001-90 fim",
    "123.456.789-09", "12345678909", "123456789090", "cpf:12345678909.",
    "(92) 99123-4567", "92 99123-4567", "9299123-4567", "(92)991234567", "(92) 3233-4444",
    "99123-4567", "R$ 1.234,56", "16/10/2026", "08:30:00", "000123 FULANO", "", "[removido]",
)


def test_RN_VIS_007_rede_de_dado_pessoal_igual_na_rota_e_na_web(web_app):
    """Mesmos tipos, na mesma ordem, com o mesmo padrão e as mesmas flags, e a
    mesma resposta numa amostra fictícia (o primeiro tipo que casa)."""
    rede = tuple(vn._REDE)
    web = web_app.visitas.RE_PESSOAL
    assert [t for t, _ in rede] == list(web)
    for tipo, rx in rede:
        assert web[tipo].pattern == rx.pattern, tipo
        assert web[tipo].flags == rx.flags, tipo
    for s in _AMOSTRAS:
        r = next((t for t, rx in rede if rx.search(s)), None)
        w = next((t for t, rx in web.items() if rx.search(s)), None)
        assert r == w, s


def test_RN_VIS_007_tipos_achado_iguais_e_na_mesma_ordem(web_app):
    assert tuple(web_app.visitas.TIPOS_ACHADO) == tuple(vn.TIPOS_ACHADO)


def test_RN_VIS_007_colunas_fora_do_espelho_iguais_na_rota_e_na_web(web_app):
    """As colunas que nunca saem do Espelho são as mesmas nos dois lados
    (`_FORA_DO_ESPELHO` na rota, `COLUNAS_PROIBIDAS` na web)."""
    assert tuple(web_app.visitas.COLUNAS_PROIBIDAS) == tuple(vn._FORA_DO_ESPELHO)
    # se a web um dia tiver a lista das permitidas, ela é a mesma
    if hasattr(web_app.visitas, "ESPELHO_PERMITIDAS"):
        assert {k: tuple(v) for k, v in web_app.visitas.ESPELHO_PERMITIDAS.items()} == \
            {k: tuple(v) for k, v in vn.ESPELHO_PERMITIDAS.items()}


# ------------------------------------------------------------------ robô × web (RD-0174)
# O robô (`visitas_maxima`) e a web têm cópias de FASES, FECHADOS_PC_DIAS e dos
# códigos do contrato (§2, §3.3 e §5). Pulam enquanto o robô da T-0045 não estiver no main.
def _robo_novo():
    import visitas_maxima as vm
    if not hasattr(vm, "classificar_login"):
        pytest.skip("robô da T-0045 (modulo-robo/T-0045-nuvem-robo) ainda não está no main")
    return vm


def test_RN_VIS_005_fases_iguais_no_robo_e_na_web(web_app):
    vm = _robo_novo()
    assert tuple(vm.FASES) == tuple(web_app.visitas.FASES)


def test_RN_VIS_002_fechados_pc_dias_igual_no_robo_e_na_web(web_app):
    vm = _robo_novo()
    assert vm.FECHADOS_PC_DIAS == web_app.visitas.FECHADOS_PC_DIAS == 40


def test_RN_VIS_005_todo_codigo_do_robo_esta_na_web(web_app):
    """Todo código que o robô escreve (literal de código no `visitas_maxima.py`, fora nome de variável de
    ambiente e evento do Tk) e todo código que as funções puras devolvem existem em `web.CODIGOS`."""
    import re
    vm = _robo_novo()
    fonte = (RAIZ / "visitas_maxima.py").read_text(encoding="utf-8")
    literais = {m for m in re.findall(r"[\"']([A-Z]{2,}(?:_[A-Z0-9]{2,})+)[\"']", fonte)
                if not m.startswith(("BAP_", "WM_", "PLAYWRIGHT_", "PW"))}
    tempo = type("TimeoutError", (Exception,), {})
    devolvidos = {vm.codigo_da_excecao(e, f)[0] for e, f in (
        (vm.ErroRobo("x"), "grade"), (RuntimeError("Target closed"), "grade"), (RuntimeError("x"), "grade"),
        (tempo("t"), "login"), (tempo("t"), "grade"))}
    devolvidos |= {vm.classificar_login(u, t, c, h) for u, t, c, h in (
        ("https://x.test/login", "Usuário ou senha inválidos", False, None), ("https://x.test/login", "", True, None),
        ("https://x.test/login", "Enviamos um código por SMS", False, None),
        ("https://x.test/login", "Conta bloqueada", False, None))} - {None}
    todos = literais | devolvidos
    assert {"MAXIMA_SENHA", "MAXIMA_CAPTCHA", "MAXIMA_CONFIRMACAO", "MAXIMA_BLOQUEIO", "TELA_MUDOU",
            "NAVEGADOR_FALHOU", "MAXIMA_FORA", "ERRO_INTERNO"} <= todos
    fora = sorted(todos - set(web_app.visitas.CODIGOS))
    assert fora == [], fora
