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
web das cópias de FASES, FECHADOS_PC_DIAS e dos códigos (RD-0174), que exige
o robô da T-0045 no main.

Datas fictícias, sem dado de cliente.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import visitas_nucleo as vn

RAIZ = Path(__file__).resolve().parent.parent


def _iguais(web, nuvem, pc):
    r = vn.juntar_baixado(nuvem, pc)
    assert web.juntar_baixado(nuvem, pc) == r
    return r


# ------------------------------------------------------------------ o empate
def test_RN_VIS_002_empate_fica_com_a_nuvem_nos_dois(web_visitas):
    """O mesmo instante escrito de 3 jeitos (UTC, Manaus e sem fuso) é empate,
    e o empate é da nuvem. Os erros_vendedor/refeito acompanham a nuvem."""
    nuvem = {"20261125": {"baixado_em": "2026-11-26T11:00:00+00:00", "erros_vendedor": 1,
                          "refeito": True},
             "20261124": "2026-11-25T07:00:00-04:00"}
    pc = {"20261125": "2026-11-26T07:00:00-04:00",
          "20261124": "2026-11-25T07:00:00"}
    r = _iguais(web_visitas, nuvem, pc)
    assert {k: v["origem"] for k, v in r.items()} == {"20261124": "nuvem", "20261125": "nuvem"}
    assert r["20261125"]["erros_vendedor"] == 1 and r["20261125"]["refeito"] is True
    # um segundo a mais no PC: o PC ganha, sem os campos da nuvem
    r = _iguais(web_visitas, nuvem, {"20261125": "2026-11-26T07:00:01-04:00"})
    assert r["20261125"] == {"baixado_em": "2026-11-26T07:00:01-04:00", "origem": "pc"}
    # o empate trocando os lados: continua sendo quem veio como nuvem
    assert _iguais(web_visitas, pc, nuvem)["20261124"]["origem"] == "nuvem"


# ------------------------------------------------------------------ hora sem fuso = Manaus
def test_RN_VIS_002_hora_sem_fuso_e_manaus_nos_dois(web_visitas):
    r = _iguais(web_visitas, {}, {"20261126": "2026-11-27T06:30:00"})
    assert r["20261126"] == {"baixado_em": "2026-11-27T06:30:00-04:00", "origem": "pc"}
    # 23h30 de Manaus sem fuso não fecha o dia; a mesma hora em UTC (19h30) também não
    for v in ("2026-11-26T23:30:00", "2026-11-26T23:30:00+00:00"):
        ind = {"20261126": v}
        assert vn.dia_fechado_no_indice(ind, date(2026, 11, 26)) is False
        assert web_visitas.dia_fechado_no_indice(ind, date(2026, 11, 26)) is False
    # 03h00 UTC do dia 27 = 23h00 do dia 26 em Manaus: ainda não fecha
    ind = {"20261126": "2026-11-27T03:00:00+00:00"}
    assert vn.dia_fechado_no_indice(ind, date(2026, 11, 26)) is False
    assert web_visitas.dia_fechado_no_indice(ind, date(2026, 11, 26)) is False
    # 04h00 UTC do dia 27 = 00h00 do dia 27 em Manaus: fecha
    ind = {"20261126": "2026-11-27T04:00:00+00:00"}
    assert vn.dia_fechado_no_indice(ind, date(2026, 11, 26)) is True
    assert web_visitas.dia_fechado_no_indice(ind, date(2026, 11, 26)) is True
    # datetime em vez de texto (o PC anota assim)
    agora = datetime(2026, 11, 27, 6, 0, tzinfo=timezone(timedelta(hours=-4)))
    _iguais(web_visitas, {"20261126": agora.isoformat()}, {"20261126": agora.replace(tzinfo=None).isoformat()})


# ------------------------------------------------------------------ o dia de hoje
def test_RN_VIS_002_hoje_entra_aberto_e_nada_passa_de_hoje_nos_dois(web_visitas):
    hoje = date(2026, 11, 27)
    ind = {"20261127": "2026-11-27T06:10:00-04:00",          # hoje, baixado hoje: aberto
           "20261126": "2026-11-27T06:00:00-04:00",          # ontem, baixado hoje: fechado
           "20261125": "2026-11-25T22:00:00"}                # baixado no próprio dia: aberto
    for refazer in (False, True):
        a = vn.dias_a_baixar(ind, date(2026, 11, 24), date(2026, 12, 3), hoje, refazer)
        assert web_visitas.dias_a_baixar(ind, date(2026, 11, 24), date(2026, 12, 3), hoje, refazer) == a
        assert max(a) == hoje
    a = vn.dias_a_baixar(ind, date(2026, 11, 24), date(2026, 12, 3), hoje)
    assert a == [date(2026, 11, 24), date(2026, 11, 25), hoje]
    # só hoje, e um intervalo que começa depois de hoje (vazio)
    for de, ate in ((hoje, hoje), (hoje + timedelta(days=1), hoje + timedelta(days=5))):
        assert web_visitas.dias_a_baixar(ind, de, ate, hoje) == vn.dias_a_baixar(ind, de, ate, hoje)
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


def test_RN_VIS_002_intervalo_grande_da_o_mesmo_indice_e_os_mesmos_dias(web_visitas):
    inicio, hoje = date(2025, 1, 1), date(2026, 11, 27)
    n = (hoje - inicio).days                                    # baixas até ontem
    nuvem, pc = _indice_grande(inicio, n, "nuvem"), _indice_grande(inicio, n, "pc")
    ind = _iguais(web_visitas, nuvem, pc)
    assert len(ind) > 500
    assert {v["origem"] for v in ind.values()} == {"nuvem", "pc"}
    de, ate = inicio, inicio + timedelta(days=n + 30)          # passa de hoje de propósito
    for refazer in (False, True):
        a = vn.dias_a_baixar(ind, de, ate, hoje, refazer)
        assert web_visitas.dias_a_baixar(ind, de, ate, hoje, refazer) == a
        assert a and max(a) <= hoje
    todos = vn.dias_a_baixar(ind, de, ate, hoje, True)
    assert todos[0] == inicio and todos[-1] == hoje and len(todos) == (hoje - inicio).days + 1
    abertos = vn.dias_a_baixar(ind, de, ate, hoje)
    assert 0 < len(abertos) < len(todos)
    for d in todos:
        assert web_visitas.dia_fechado_no_indice(ind, d) == vn.dia_fechado_no_indice(ind, d), d


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


def test_RN_VIS_007_rede_de_dado_pessoal_igual_na_rota_e_na_web(web_visitas):
    """Mesmos tipos, na mesma ordem, com o mesmo padrão e as mesmas flags, e a
    mesma resposta numa amostra fictícia (o primeiro tipo que casa)."""
    rede = tuple(vn._REDE)
    web = web_visitas.RE_PESSOAL
    assert [t for t, _ in rede] == list(web)
    for tipo, rx in rede:
        assert web[tipo].pattern == rx.pattern, tipo
        assert web[tipo].flags == rx.flags, tipo
    for s in _AMOSTRAS:
        r = next((t for t, rx in rede if rx.search(s)), None)
        w = next((t for t, rx in web.items() if rx.search(s)), None)
        assert r == w, s


def test_RN_VIS_007_tipos_achado_iguais_e_na_mesma_ordem(web_visitas):
    assert tuple(web_visitas.TIPOS_ACHADO) == tuple(vn.TIPOS_ACHADO)


def test_RN_VIS_007_colunas_fora_do_espelho_iguais_na_rota_e_na_web(web_visitas):
    """As colunas que nunca saem do Espelho são as mesmas nos dois lados
    (`_FORA_DO_ESPELHO` na rota, `COLUNAS_PROIBIDAS` na web)."""
    assert tuple(web_visitas.COLUNAS_PROIBIDAS) == tuple(vn._FORA_DO_ESPELHO)
    # se a web um dia tiver a lista das permitidas, ela é a mesma
    if hasattr(web_visitas, "ESPELHO_PERMITIDAS"):
        assert {k: tuple(v) for k, v in web_visitas.ESPELHO_PERMITIDAS.items()} == \
            {k: tuple(v) for k, v in vn.ESPELHO_PERMITIDAS.items()}


# ------------------------------------------------------------------ robô × web (RD-0174)
# O robô (`visitas_maxima`) e a web têm cópias de FASES, FECHADOS_PC_DIAS e dos
# códigos do contrato (§2, §3.3 e §5). Exigem o robô da T-0045 (PR #165) no main.
def _robo_novo():
    import visitas_maxima as vm
    return vm


def test_RN_VIS_005_fases_iguais_no_robo_e_na_web(web_visitas):
    vm = _robo_novo()
    assert tuple(vm.FASES) == tuple(web_visitas.FASES)


def test_RN_VIS_002_fechados_pc_dias_igual_no_robo_e_na_web(web_visitas):
    vm = _robo_novo()
    assert vm.FECHADOS_PC_DIAS == web_visitas.FECHADOS_PC_DIAS == 40


def test_RN_VIS_005_todo_codigo_do_robo_esta_na_web(web_visitas):
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
    fora = sorted(todos - set(web_visitas.CODIGOS))
    assert fora == [], fora


# ------------------------------------------------------------------ cron × web (RD-A1, padrão RD-0174)
# O cron (`nuvem/visitas/agenda.py` e `rodar.py`, modulo-robo) tem cópias das constantes da web (contrato §2, §3.1,
# §3.2, §3.5 e §5): um lado que muda sem o outro reprova. TIPOS_ACHADO e MANAUS do cron vêm do `visitas_nucleo`
# (importação, não cópia) e ficam fora daqui. Exigem o `nuvem/visitas/` (T-0045, PR do modulo-robo) no main.
def _cron():
    from nuvem.visitas import agenda, rodar
    return agenda, rodar


_CONTRATO_S2 = {"TENTATIVAS_DIA": {"agenda": 4, "pedido": 3, "retentativa": 1, "diagnostico": 2},
                "LOGINS_DIA_MAX": 8, "PEDIDO_MAX_DIAS": 7, "PEDIDO_MAX_RODADAS": 3,
                "RETENTATIVAS_AGENDA": ("06h30", "07h00", "07h30"),
                "NOVA_TENTATIVA": ("MAXIMA_FORA", "TELA_MUDOU", "NAVEGADOR_FALHOU", "SITE_RECUSOU",
                                   "RODADA_INTERROMPIDA", "PARCIAL_TEMPO", "ERRO_INTERNO")}


@pytest.mark.parametrize("nome", sorted(_CONTRATO_S2))
def test_RN_VIS_008_constantes_da_agenda_do_cron_iguais_na_web_e_no_contrato(web_visitas, nome):
    agenda, _ = _cron()
    cron, web = getattr(agenda, nome), getattr(web_visitas, nome)
    if isinstance(cron, (list, tuple)):
        assert tuple(cron) == tuple(web) == _CONTRATO_S2[nome]
    else:
        assert cron == web == _CONTRATO_S2[nome]


def test_RN_VIS_005_pede_fase_do_cron_igual_na_web(web_visitas):
    _, rodar = _cron()
    assert tuple(rodar.PEDE_FASE) == tuple(web_visitas.PEDE_FASE) == ("TELA_MUDOU", "ERRO_INTERNO")


@pytest.mark.parametrize("cron_nome,web_nome", [("RX_ID", "RE_ID_RODADA"), ("RX_ROTULO", "RE_ROTULO")])
def test_RN_VIS_004_regex_do_cron_igual_na_web(web_visitas, cron_nome, web_nome):
    """`<id>` da rodada (§3) e o rótulo dos achados (§3.6): mesmo padrão e mesmas flags."""
    _, rodar = _cron()
    c, w = getattr(rodar, cron_nome), getattr(web_visitas, web_nome)
    assert (c.pattern, c.flags) == (w.pattern, w.flags)
    for s in ("R20261127T060012", "R2026112T060012", "r20261127T060012", "R20261127T060012\n", "KM DIST",
              "% VISITAS", "CELULA", "km dist", "A" * 41, ""):
        assert bool(c.match(s)) == bool(w.match(s)), s


def test_RN_VIS_005_saida_do_cron_segue_o_status_da_web(web_visitas):
    """§5: saída 0 para `ok` e `parcial`, 1 para `erro`. Todo código que sai com 0 existe no `CODIGOS` da web."""
    _, rodar = _cron()
    status = web_visitas.STATUS_DO_CODIGO
    assert set(rodar.SAIDA_OK) <= set(status)
    for codigo, st in status.items():
        assert rodar.codigo_e_saida(codigo) == (0 if st in ("ok", "parcial") else 1), (codigo, st)
    assert rodar.codigo_e_saida("QUALQUER_OUTRO") == 1


# ------------------------------------------------------------------ pedido sem dia: cron × web (lote 2; v1.2 §4.5)
# A web decide se o pedido do botão entra (ou fica) na fila com `dias_do_pedido`, espelho de
# `agenda.dias_da_rodada("pedido", ...)`; `_refeito_depois` é o espelho do mesmo nome no cron. Um lado que muda sem o
# outro reprova: a web tiraria da fila um pedido que o cron ainda baixaria (ou o contrário, e a fila trava).
# Exigem o lote 2 da T-0045 (modulo-web e modulo-robo) no main.
_HOJE = date(2026, 11, 27)
_PEDIDO_EM = "2026-11-27T08:00:00-04:00"


def _indice_pedido():
    """Os dias 18 a 27/11, já juntados (como o `trabalho` entrega). Pedido às 08h00 de hoje (27):
    18 sem baixa (aberto) · 19 nuvem 20/11 06h00 × PC 05h00 (nuvem, antes do pedido) · 20 PC sem fuso (fechado) ·
    21 nuvem 27/11 10h00, dict (refeito depois) · 22 PC 27/11 09h30 (depois, mas pelo PC) · 23 baixado no próprio dia
    (aberto) · 24 nuvem 12h00 UTC = 08h00 Manaus (empate com o pedido) · 25 nuvem 26/11 06h07 (antes do pedido) ·
    26 nuvem 27/11 09h15 (refeito depois) · 27 hoje, sem baixa."""
    nuvem = {"20261126": "2026-11-27T09:15:00-04:00",
             "20261125": "2026-11-26T06:07:00-04:00",
             "20261124": "2026-11-27T12:00:00+00:00",
             "20261123": "2026-11-23T22:00:00-04:00",
             "20261121": {"baixado_em": "2026-11-27T10:00:00-04:00", "erros_vendedor": 1, "refeito": False},
             "20261119": "2026-11-20T06:00:00-04:00"}
    pc = {"20261122": "2026-11-27T09:30:00-04:00",
          "20261120": "2026-11-21T07:00:00",
          "20261119": "2026-11-20T05:00:00-04:00"}
    return vn.juntar_baixado(nuvem, pc)


_PEDIDOS = [
    {"de": "20261118", "ate": "20261127", "refazer": False},
    {"de": "20261118", "ate": "20261127", "refazer": True, "pedido_em": _PEDIDO_EM},
    {"de": "20261121", "ate": "20261127", "refazer": True, "pedido_em": "2026-11-27T12:00:00+00:00"},
    {"de": "20261121", "ate": "20261127", "refazer": True, "pedido_em": "2026-11-27T08:00:00"},
    {"de": "20261121", "ate": "20261127", "refazer": True, "pedido_em": "2026-11-27T10:00:01-04:00"},
    {"de": "20261121", "ate": "20261127", "refazer": True, "pedido_em": None},
    {"de": "20261121", "ate": "20261127", "refazer": True, "pedido_em": "ontem cedo"},
    {"de": "20261121", "ate": "20261127", "refazer": True},
    {"de": "20261124", "ate": "20261126", "refazer": False},
    {"de": "20261125", "ate": "20261126", "refazer": False},
    {"de": "20261119", "ate": "20261120", "refazer": False},
    {"de": "20261127", "ate": "20261210", "refazer": False},
    {"de": "20261128", "ate": "20261205", "refazer": True, "pedido_em": _PEDIDO_EM},
    {"de": "20261101", "ate": "20261127", "refazer": True, "pedido_em": _PEDIDO_EM},
    {"de": "20261101", "ate": "20261130", "refazer": False},
    {"de": 20261121, "ate": 20261127, "refazer": 1, "pedido_em": _PEDIDO_EM},
    {"de": "20261127", "ate": "20261121", "refazer": False},
    {"de": "2026-11-21", "ate": "20261127", "refazer": False},
    {"de": "20261121", "ate": "20261332", "refazer": False},
    {"de": None, "ate": "20261127", "refazer": False},
    {"ate": "20261127"},
    {},
    None,
]


@pytest.mark.parametrize("ped", _PEDIDOS, ids=lambda p: "-".join(f"{k}={v}" for k, v in (p or {}).items()) or "vazio")
@pytest.mark.parametrize("indice", ["cheio", "vazio", "nenhum"])
def test_RN_VIS_004_dias_do_pedido_da_web_igual_ao_dias_da_rodada_do_cron(web_visitas, ped, indice):
    agenda, _ = _cron()
    ind = {"cheio": _indice_pedido(), "vazio": {}, "nenhum": None}[indice]
    cron = agenda.dias_da_rodada("pedido", {"indice": ind, "pedido": ped}, _HOJE)
    assert web_visitas.dias_do_pedido(ind, ped, _HOJE) == cron
    assert len(cron) <= agenda.PEDIDO_MAX_DIAS and all(x <= _HOJE for x in cron)


def test_RN_VIS_002_dias_do_pedido_valor_x_regra():
    """Os dias esperados, contados à mão no índice de `_indice_pedido` (contrato §3.1 e §4.5). Só o cron: a web
    é igual a ele pela paridade acima."""
    agenda, _ = _cron()
    ind = _indice_pedido()

    def dias(ped):
        return [x.day for x in agenda.dias_da_rodada("pedido", {"indice": ind, "pedido": ped}, _HOJE)]

    # sem refazer: só os abertos (18 sem baixa, 23 baixado no próprio dia, 27 = hoje)
    assert dias({"de": "20261118", "ate": "20261127"}) == [18, 23, 27]
    # refazer: todos, menos os que a nuvem refez a partir do pedido (21, 24 no empate, 26); o 22 (PC) refaz
    assert dias({"de": "20261121", "ate": "20261127", "refazer": True, "pedido_em": _PEDIDO_EM}) == [22, 23, 25, 27]
    # um segundo depois do 21 (10h00): ele volta; o 24 e o 26 também
    assert dias({"de": "20261121", "ate": "20261127", "refazer": True,
                 "pedido_em": "2026-11-27T10:00:01-04:00"}) == [21, 22, 23, 24, 25, 26, 27]
    # corte em PEDIDO_MAX_DIAS: os 7 primeiros
    assert dias({"de": "20261101", "ate": "20261127", "refazer": True, "pedido_em": _PEDIDO_EM}) == \
        [1, 2, 3, 4, 5, 6, 7]
    # todos fechados = vazio = o pedido sai da fila com NADA_A_FAZER
    assert dias({"de": "20261124", "ate": "20261126"}) == []
    # período invertido, fora do formato ou só no futuro = vazio
    for ped in ({"de": "20261127", "ate": "20261121"}, {"de": "2026-11-21", "ate": "20261127"},
                {"de": "20261128", "ate": "20261205"}):
        assert dias(ped) == []


@pytest.mark.parametrize("item", [
    {"baixado_em": "2026-11-27T09:00:00-04:00", "origem": "nuvem"},
    {"baixado_em": "2026-11-27T08:00:00-04:00", "origem": "nuvem"},
    {"baixado_em": "2026-11-27T12:00:00+00:00", "origem": "nuvem"},
    {"baixado_em": "2026-11-27T07:59:59-04:00", "origem": "nuvem"},
    {"baixado_em": "2026-11-27T08:00:00", "origem": "nuvem"},
    {"baixado_em": "2026-11-27T09:00:00-04:00", "origem": "pc"},
    {"baixado_em": "2026-11-27T09:00:00-04:00"},
    {"baixado_em": "lixo", "origem": "nuvem"},
    {"baixado_em": None, "origem": "nuvem"},
    {"origem": "nuvem"},
    {},
    "2026-11-27T09:00:00-04:00",
    None,
])
def test_RN_VIS_004_refeito_depois_igual_no_cron_e_na_web(web_visitas, item):
    agenda, _ = _cron()
    em = vn._quando_manaus(_PEDIDO_EM)
    assert web_visitas._refeito_depois(item, em) == agenda._refeito_depois(item, em)
