"""T-0034 (condição do po, R-20261127-014248-po): no Painel Executivo, cada cartão traz a comparação
(mês anterior, o anterior a ele e julho, o benchmarking) do PRÓPRIO indicador, na unidade dele.

Regra citada: "o número do Diretor bate com o farol de origem" (definição de pronto, CLAUDE.md),
mais RN-GER-002 (faturado líquido pela data da NF), RN-GER-003 (positivação = clientes com
líquido > 0) e RN-GER-007 (decisões 43 e 48: no grupo A hoje conta como DU passado; projeção = real até agora ÷
DU passados (com hoje) × DU do mês).

Dado real: as bases congeladas do repositório, com hoje = 24/11/2026, pelo caminho do robô
(`relatorios_nucleo.montar` → `bap_automation.montar_pacote_web`). O histórico do Diretor
(RELATORIOS/painel_diretor_hist.json, base congelada) vai para a cópia do `tests/conftest.py`.

- Pacote × fechamento real: a comparação "out" de cada cartão é o número do mesmo cartão no
  Painel de outubro fechado (e "set" o de setembro, "jul (bench.)" o de julho).
- Pacote × regra: a variação mostrada é a conta do PC (`painel_rrm.v_pct`, `v_pp`, `v_n`,
  `v_min`) sobre o número do cartão e o da comparação, dentro do arredondamento do texto.
- Web × pacote × PC: a web da T-0034 (no main desde o #146; cópia descartável de `web/`, ou de BAP_TESTE_WEB) mostra
  em cada cartão a comparação que o PC desenha (`painel_rrm`). Com a web da T-0052 (valor grande em todo cartão,
  sem números na faixa do topo), o teste do cartão confere o `rc-valor` de todos; a detecção é pelo HTML. Sem a web da T-0034 (sem
  `render.faixa_painel`) ou sem fastapi, esses testes são pulados com o motivo.

Nenhum dado pessoal: só os números agregados da BAP.
"""
import html
import os
import re
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import painel_rrm as prm
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 24)
ANO, MES = 2026, 11
ROTULOS = ["out", "set", "jul (bench.)"]
MESES_COMP = (10, 9, 7)
ABAS = (("resultado", "res", "Painel · resultado"), ("produtividade", "prod", "Painel · produtividade"),
        ("por_dia_util", "du", "Painel · por dia útil"))
# o cartão em que "menor é melhor" (painel_rrm: bom=False); o tom "ok" = melhorou
MENOR_E_MELHOR = {("res", "desc"), ("res", "inad"), ("prod", "fora"), ("prod", "ini"), ("prod", "alm"),
                  ("prod", "tmd")}
# a comparação desses cartões não é o número do cartão no mês fechado, por regra do PC:
# - top30: a lista de 30 é a do mês corrente (painel_cartoes._top30); a comparação conta quantos
#   DESSES 30 compraram no mês anterior. O cartão de outubro usa a lista de outubro.
# - inad: o cartão é a foto do dia (títulos vencidos hoje); os meses anteriores vêm do fechamento
#   gravado pelo Painel do Diretor. O Painel de outubro montado hoje mostra a foto de hoje.
COMP_NAO_E_O_FECHADO = {"top30", "inad"}

TOKEN = "t" * 43
ADMIN, SENHA0, SENHA1 = "admin.teste", "senha-inicial-123", "nova-senha-forte-1"


# ---------------------------------------------------------------- montagem (dado real)
def _montar(mes):
    return rn.montar("vc_painel", RAIZ, hoje=HOJE, params={"ANO": str(ANO), "MÊS": str(mes)})


def _cartoes_pc(rel):
    """{visao: [cartões]} do Painel do PC (os 3 blocos rrm que o `painel_rrm.tela` desenha)."""
    out = {}
    for p in rel["paineis"][:3]:
        b = p["painel"]["blocos"][0]
        out[b["visao"]] = b["dados"][b["visao"]]
    return out


def _painel_rrm_direto():
    """{visao: [cartões]} pelo `painel_rrm.calcular` chamado direto (a conta que o Painel do PC desenha),
    sem passar pelo `relatorios_nucleo.montar` nem pelo robô."""
    ctx = rn.Contexto(RAIZ, HOJE, None, {"ANO": str(ANO), "MÊS": str(MES)})
    dr = prm.calcular(ctx, ANO, MES)
    return {v: dr[v] for _c, v, _t in ABAS}


@pytest.fixture(scope="module")
def mundo():
    """(cartões do painel_rrm, cartões do vc_painel montado, pacote do robô, {mês fechado: cartões}), tudo das bases
    congeladas. O histórico do Diretor vai para a cópia da fixture autouse do conftest."""
    rel = _montar(MES)                                       # o mês corrente primeiro (o histórico dele)
    pac = ba.montar_pacote_web({"vc_painel": rel}, ANO, MES, raiz=RAIZ)
    fechados = {m: _cartoes_pc(_montar(m)) for m in MESES_COMP}
    pac["gerado_em"] = "2026-11-24T08:30:00-04:00"           # o pacote "de hoje" para a web não marcar desatualizado
    return _painel_rrm_direto(), _cartoes_pc(rel), pac, fechados


def _cartoes_pacote(pac):
    vp = pac["relatorios"]["vc_painel"]["abas"]
    return {v: vp[chave]["painel"]["blocos"][0]["dados"][v] for chave, v, _t in ABAS}


# ---------------------------------------------------------------- leitura dos textos do PC
def _unidade(s):
    """A unidade do texto do número: R$, %, h (hora), min, n (quantidade) ou None (sem número)."""
    s = str(s or "").strip()
    if s in ("", "—"):
        return None
    if s.startswith("R$"):
        return "R$"
    if s.endswith("%"):
        return "%"
    if re.fullmatch(r"\d+h\d\d", s):
        return "h"
    if s.endswith(" min"):
        return "min"
    if re.fullmatch(r"[\d.]+(,\d+)?( de 30)?", s):
        return "n"
    raise AssertionError(f"texto de número desconhecido: {s!r}")


def _numero(s):
    """(valor, meio passo do arredondamento do texto). Hora e min em minutos."""
    s = str(s).strip()
    m = re.fullmatch(r"(\d+)h(\d\d)", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)), 0.5
    s = s.replace("R$", "").replace(" de 30", "").replace("p.p.", "").replace("min", "").replace("%", "").strip()
    mult = 1
    if s.endswith(" mil"):
        s, mult = s[:-4], 1e3
    elif s.endswith(" mi"):
        s, mult = s[:-3], 1e6
    inteiro, _, dec = s.replace(".", "").partition(",")
    v = float(f"{inteiro}.{dec}" if dec else inteiro)
    return v * mult, 0.5 * 10 ** (-len(dec)) * mult


def _variacao(t):
    """Texto da variação do PC (+11%, −0,8 p.p., −4, +57 min, igual) → (tipo, valor, meio passo)."""
    t = t.replace("−", "-").strip()
    if t == "igual":
        return "igual", 0.0, 0.0
    tipo = "p.p." if t.endswith("p.p.") else "%" if t.endswith("%") else "min" if t.endswith("min") else "n"
    v, meio = _numero(t.lstrip("+-"))
    return tipo, (-v if t.startswith("-") else v), meio


def _base_do_cartao(c):
    """O número que o PC compara (painel_rrm.faixa): a projeção nos cartões projetados, senão o real."""
    m = re.search(r"projeção do mês ([\d.,]+)", c.get("legenda") or "")
    return _numero(m.group(1)) if m else _numero(c["valor"])


def _comparacoes(c):
    return [(f[0], f[1], f[3]) for f in c["faixa"]]


# ---------------------------------------------------------------- pacote real (sem a web)
def test_RN_PAINEL_006_pacote_leva_as_abas_e_o_pc_igual(mundo):
    """O pacote do robô leva os cartões e as comparações do `painel_rrm.calcular` (chamado direto) sem mudar nada,
    e o vc_painel montado (a tela do PC) também (número do Diretor bate)."""
    pc, rel, pac, _f = mundo
    web = _cartoes_pacote(pac)

    def chave(cs):
        return [(c["titulo"], c["valor"], c["legenda"], _comparacoes(c)) for c in cs]
    for _chave, v, _t in ABAS:
        assert chave(pc[v]), v
        assert chave(web[v]) == chave(pc[v]), v
        assert chave(rel[v]) == chave(pc[v]), v


def test_RN_PAINEL_007_cada_cartao_tem_a_comparacao_dele_e_nao_a_do_faturamento(mundo):
    """A condição do po: as 3 comparações mudam de cartão para cartão (a simulação repetia R$ 149/237/626 mil)."""
    _pc, _rel, pac, _f = mundo
    for _chave, v, _t in ABAS:
        cs = _cartoes_pacote(pac)[v]
        assert all([f[0] for f in c["faixa"]] == ROTULOS for c in cs), v
        com_numero = [tuple(x[2] for x in _comparacoes(c)) for c in cs if any(x[2] != "—" for x in _comparacoes(c))]
        assert len(com_numero) == len(set(com_numero)), (v, com_numero)
    res = {c["chave"]: c for c in _cartoes_pacote(pac)["res"]}
    assert [f[3] for f in res["fat"]["faixa"]] == ["R$ 149 mil", "R$ 237 mil", "R$ 626 mil"]
    assert all(not f[3].startswith("R$") for f in res["pos"]["faixa"] + res["ped"]["faixa"])


def test_RN_PAINEL_008_unidade_da_comparacao_e_a_do_cartao(mundo):
    """Positivação em clientes, Pedidos em quantidade, Markup em %, Jornada em hora: a comparação na unidade do cartão,
    e a variação no jeito do indicador (% nos volumes, p.p. nas taxas, minutos nos horários)."""
    _pc, _rel, pac, _f = mundo
    var_esperada = {"R$": {"%", "igual"}, "n": {"%", "igual"}, "%": {"p.p.", "igual"},
                    "h": {"min", "igual"}, "min": {"min", "igual"}}
    for _chave, v, _t in ABAS:
        for c in _cartoes_pacote(pac)[v]:
            u = _unidade(c["valor"])
            for rot, var, fech in _comparacoes(c):
                if _unidade(fech) is None:
                    continue
                assert _unidade(fech) == u, (v, c["titulo"], rot, c["valor"], fech)
                ok = {"n", "igual"} if c["chave"] == "top30" else var_esperada[u]
                assert var == "" or _variacao(var)[0] in ok, (v, c["titulo"], rot, var)


def test_RN_PAINEL_009_comparacao_e_o_fechamento_do_mesmo_cartao(mundo):
    """Valor × regra: "out" = o número do mesmo cartão no Painel de outubro fechado ("set" = setembro, "jul" = julho).
    Exceções por regra do PC: TOP 30 (lista do mês corrente) e Inadimplência (foto do dia × fechamento gravado)."""
    _pc, _rel, pac, fechados = mundo
    conferidos = 0
    for _chave, v, _t in ABAS:
        for c in _cartoes_pacote(pac)[v]:
            if c["chave"] in COMP_NAO_E_O_FECHADO:
                continue
            for (rot, _var, fech), m in zip(_comparacoes(c), MESES_COMP):
                fechado = next(x for x in fechados[m][v] if x["chave"] == c["chave"])
                assert fech == fechado["valor"], (v, c["titulo"], rot, fech, fechado["valor"])
                conferidos += fech != "—"
    assert conferidos >= 50, conferidos            # 57 nas bases congeladas, com hoje = 24/11: quase todos os cartões têm os 3 meses


def test_RN_PAINEL_010_variacao_e_a_conta_do_pc(mundo):
    """Valor × regra: a variação = (base ÷ fechamento − 1) nos volumes (base = projeção do mês, RN-GER-007, nos
    projetados), base − fechamento nas taxas (p.p.), em quantidade (TOP 30) e em minutos; o tom diz se melhorou."""
    _pc, _rel, pac, _f = mundo
    conferidas = 0
    for _chave, v, _t in ABAS:
        for c in _cartoes_pacote(pac)[v]:
            if _unidade(c["valor"]) is None:
                continue
            a, da = _base_do_cartao(c)
            for rot, var, tom, fech in c["faixa"]:
                if not var or _unidade(fech) is None:
                    continue
                b, db = _numero(fech)
                tipo, x, dx = _variacao(var)
                u = _unidade(c["valor"])
                if u in ("R$", "n") and c["chave"] != "top30":          # v_pct: "igual" = menos de 0,5%
                    lo, hi = ((a - da) / (b + db) - 1) * 100, ((a + da) / (b - db) - 1) * 100
                    dx = dx if tipo != "igual" else 0.5
                else:                                                    # v_pp (0,05), v_n e v_min (0)
                    lo, hi = (a - da) - (b + db), (a + da) - (b - db)
                    dx = dx if tipo != "igual" else (0.05 if u == "%" else 0.0)
                assert lo - dx <= x <= hi + dx, (v, c["titulo"], rot, c["valor"], fech, var, (round(lo, 2), round(hi, 2)))
                if tipo != "igual":
                    melhorou = (x > 0) != ((v, c["chave"]) in MENOR_E_MELHOR)
                    assert tom == ("ok" if melhorou else "alerta"), (v, c["titulo"], rot, var, tom)
                conferidas += 1
    assert conferidas >= 60, conferidas


# ---------------------------------------------------------------- a web da T-0034 (TestClient)
def _web_origem():
    return Path(os.environ.get("BAP_TESTE_WEB") or (RAIZ / "web"))


def _web_da_T0034(origem):
    r = origem / "app" / "render.py"
    return r.is_file() and "def faixa_painel" in r.read_text(encoding="utf-8")


@pytest.fixture
def web(mundo, tmp_path, monkeypatch):
    """A web da T-0034 numa cópia descartável, com o admin logado e o pacote real recebido."""
    for m in ("fastapi", "httpx", "jinja2"):
        pytest.importorskip(m)
    origem = _web_origem()
    if not _web_da_T0034(origem):
        pytest.skip("a web da T-0034 (render.faixa_painel, #146) não está em "
                    f"{origem}; rode com BAP_TESTE_WEB=<pasta web da branch>")
    copia = tmp_path / "web"
    shutil.copytree(origem / "app", copia / "app", ignore=shutil.ignore_patterns("__pycache__"))
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        monkeypatch.delitem(sys.modules, m)
    monkeypatch.syspath_prepend(str(copia))
    for k, val in (("SESSION_SECRET", "segredo-de-teste-0123456789abcdef"), ("BAP_WEB_DADOS", str(tmp_path / "dados")),
                   ("BAP_WEB_TOKEN", TOKEN), ("BAP_ADMIN_USUARIO", ADMIN), ("BAP_ADMIN_SENHA_INICIAL", SENHA0),
                   ("BAP_WEB_PACOTE_MAX_MB", "25"), ("TZ", "America/Manaus")):
        monkeypatch.setenv(k, val)
    time.tzset()
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.main import criar_app  # noqa: PLC0415
    cli = TestClient(criar_app(), base_url="https://testserver")
    cli.__enter__()

    def tok(url):
        return re.search(r'name="csrf" value="([^"]+)"', cli.get(url).text).group(1)
    assert cli.post("/login", data={"usuario": ADMIN, "senha": SENHA0, "csrf": tok("/login")},
                    follow_redirects=False).status_code == 303
    assert cli.post("/senha", data={"atual": SENHA0, "nova": SENHA1, "confirma": SENHA1, "csrf": tok("/senha")},
                    follow_redirects=False).status_code == 303
    r = cli.post("/api/pacote", json=mundo[2], headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200, r.text
    yield cli
    cli.__exit__(None, None, None)
    monkeypatch.undo()
    time.tzset()


def _texto(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def _cartoes_da_tela(h):
    """[(rótulo, valor no cartão ou None, [(mês, variação, fechamento)])] como a web desenha."""
    out = []
    for art in re.findall(r'<article class="rc">(.*?)</article>', h, re.S):
        rot = _texto(re.search(r'class="rc-rot">(.*?)</div>', art, re.S).group(1))
        val = re.search(r'class="rc-valor">(.*?)</div>', art, re.S)
        fx = re.findall(r'<span class="fr">(.*?)</span> <b class="t-[a-z]*">(.*?)</b><div class="fv">(.*?)</div>', art, re.S)
        out.append((rot, _texto(val.group(1)) if val else None, [tuple(_texto(x) for x in f) for f in fx]))
    return out


def _numeros_na_faixa(h):
    """O texto dos números da faixa do topo do Painel (`class="bc3-ks"`, `_faixa.numeros`) ou None quando a faixa
    não traz números (a web da T-0052, R-20261127-093750 e R-20261127-094731)."""
    if 'class="bc3-ks"' not in h:
        return None
    return _texto(h.split('class="bc3-ks"')[1].split("</header>")[0])


def test_RN_PAINEL_011_web_T0034_mostra_em_cada_cartao_a_comparacao_do_pc(web, mundo):
    """Web × pacote × PC: o rótulo, o número e as 3 comparações de cada cartão são os do Painel do PC (painel_rrm).

    Onde fica o número, condicional pelo HTML (não pela `web.app.VERSAO`, que muda de número entre os lotes):
    - web até a T-0050 (RD-0063): a faixa do topo tem os números (`bc3-ks`) e os 3 primeiros cartões levam o
      número lá, sem `rc-valor`; os demais trazem o `rc-valor`;
    - web da T-0052 (decisão do Alexandre, R-20261127-093750 e R-20261127-094731): a faixa RRM não tem `bc3-ks`
      e TODO cartão traz o seu `rc-valor`, igual ao `valor` do PC.
    Um estado misto (faixa com números e cartão repetindo o valor, ou faixa sem números e cartão sem valor)
    falha, e as 3 abas precisam estar no mesmo caso."""
    pc, _rel, _pac, _f = mundo
    casos = set()
    for chave, v, _t in ABAS:
        h = web.get(f"/painel?aba={chave}").text
        tela = _cartoes_da_tela(h)
        assert [t[0] for t in tela] == [c["titulo"].upper() for c in pc[v]], chave
        faixa_topo = _numeros_na_faixa(h)
        casos.add("faixa" if faixa_topo is not None else "T-0052")
        for i, ((rot, val, fx), c) in enumerate(zip(tela, pc[v])):
            assert fx == [(f[0], f[1], f[3] or "—") for f in c["faixa"]], (chave, rot)
            if faixa_topo is not None and i < 3:
                assert val is None and c["valor"] in faixa_topo, (chave, rot)
            else:
                assert val == c["valor"], (chave, rot, val, c["valor"])
        com_numero = [tuple(f[2] for f in fx) for _r, _v, fx in tela if any(f[2] != "—" for f in fx)]
        assert len(com_numero) == len(set(com_numero)), (chave, com_numero)   # nenhum cartão repete a comparação de outro
    assert len(casos) == 1, casos                                   # as 3 abas no mesmo caso (faixa × T-0052)
