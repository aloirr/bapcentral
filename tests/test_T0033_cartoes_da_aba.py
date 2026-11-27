"""T-0033 (web 94b3440 e f188d73): os cartões da aba (`kpis_padrao`) só no padrão.

Contrato `.coord/contratos/relatorio.md`:
- §10.7.2 (`kpis_padrao`): a web mostra os cartões da aba só com os filtros no
  padrão, sem recorte e sem estado. Com outro filtro, recorte ou estado, eles
  saem e fica o `AVISO_CARTOES`.
- §10.7.6: o texto do `AVISO_CARTOES`.
- D5: com estado, a web filtra as linhas pelas `uf_linhas` (RN-GER-006), mas
  os `kpis_padrao` não seguem o estado: saem.
- Sem `kpis_padrao`, a aba mostra os `kpis` de cima (não há aviso).

O pacote é o do robô, montado com as BASES CONGELADAS do repositório
(NOV/2026, hoje = 24/11/2026, terça, em Manaus), e vai à web real (web/app)
pelo robô (`enviar_pacote`, formato 2) num TestClient. Valor × regra: no
padrão, o cartão da tela é o `kpis_padrao` do farol guardado; fora do padrão,
nenhum número da aba aparece na faixa, e a contagem de linhas com estado é a
das `uf_linhas` (RN-GER-006).

Sem fastapi (o CI da raiz), o módulo é pulado; roda no venv com a web.
Depende da web f188d73 (`modulo-web/T-0033-revisao-geral`): com a web do
main a32b610, os casos do aviso, do Visita e da Solicitação com `uf` falham.

Nenhum valor de célula é impresso: as mensagens só têm rótulos de cartão,
contagens e nomes de aba.
"""
import copy
import html
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

# a web real precisa do fastapi (o CI da raiz não instala): sem ele, o módulo inteiro é pulado
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
HOJE = date(2026, 11, 24)
PARAMS = {"ANO": "2026", "MÊS": "11"}
MES_ROT = "NOV/26"
RIDS = ("pv_pedidos", "pl_entregas", "vc_visitas")
TOKEN = "t" * 43
ADMIN, SENHA0, SENHA1 = "admin.teste", "senha-inicial-123", "nova-senha-forte-1"
BASE = "https://testserver"
# §10.7.6, escrito aqui à mão (fonte: o contrato)
AVISO_CARTOES = "Cartões sem filtro. Com filtro, veja as linhas na tabela."
RE_CARTAO = re.compile(r'class="bc3-k[^"]*"><small>(.*?)</small><b>(.*?)</b>', re.S)
RE_TOTAL_ABA = re.compile(r'aria-current="page">[^<]*<span>· (\d+)</span>')


class _Requests:
    """O `requests` que o robô usa, repassado ao TestClient."""

    def __init__(self, cli):
        self.cli = cli

    def get(self, url, timeout=None, **kw):
        return self.cli.get(url[len(BASE):], **kw)

    def post(self, url, data=None, headers=None, timeout=None):
        return self.cli.post(url[len(BASE):], content=data, headers=headers)


class _Web(tuple):
    """(cli, render, farol guardado por rid). O repr é curto: na falha, o pytest não mostra o pacote."""

    def __new__(cls, *itens):
        return super().__new__(cls, itens)

    def __repr__(self):
        return "<web do teste>"


@pytest.fixture(scope="module")
def pacote():
    rels = {rid: rn.montar(rid, RAIZ, hoje=HOJE, params=dict(PARAMS))
            for rid in RIDS}
    return ba.montar_pacote_web(rels, 2026, 11, raiz=RAIZ)


@pytest.fixture(scope="module")
def web(pacote, tmp_path_factory):
    """A web real com o pacote do robô (formato 2) e o admin logado.
    Devolve (cli, render, farol guardado por rid)."""
    mp = pytest.MonkeyPatch()
    antes = set(sys.modules)
    try:
        for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
            mp.delitem(sys.modules, m)
        mp.syspath_prepend(str(WEB))
        mp.setenv("SESSION_SECRET", "segredo-de-teste-0123456789abcdef")
        mp.setenv("BAP_WEB_TOKEN", TOKEN)
        mp.setenv("BAP_ADMIN_USUARIO", ADMIN)
        mp.setenv("BAP_ADMIN_SENHA_INICIAL", SENHA0)
        mp.setenv("BAP_WEB_PACOTE_MAX_MB", "25")
        dados = tmp_path_factory.mktemp("web")
        mp.setenv("BAP_WEB_DADOS", str(dados))
        mp.setenv("TZ", "America/Manaus")
        time.tzset()
        mp.setattr(ba.time, "sleep", lambda s: None)
        mp.setattr(ba, "_base_web", lambda u: BASE)
        from fastapi.testclient import TestClient

        from app import main, pacotes, render
        cli = TestClient(main.criar_app(), base_url=BASE)
        cli.__enter__()

        def tok(url):
            return re.search(r'name="csrf" value="([^"]+)"', cli.get(url).text).group(1)
        assert cli.post("/login", data={"usuario": ADMIN, "senha": SENHA0, "csrf": tok("/login")},
                        follow_redirects=False).status_code == 303
        assert cli.post("/senha", data={"atual": SENHA0, "nova": SENHA1, "confirma": SENHA1,
                                        "csrf": tok("/senha")}, follow_redirects=False).status_code == 303
        mp.setitem(sys.modules, "requests", _Requests(cli))
        log = []
        assert ba.enviar_pacote(copy.deepcopy(pacote), url=BASE, token=TOKEN, log=log.append) is True
        ind = pacotes.Indice(dados)
        guardado = {rid: ind.farol(rid) for rid in RIDS}
        assert all(guardado.values()), "a web não guardou os três faróis"
        yield _Web(cli, render, guardado)
        cli.__exit__(None, None, None)
    finally:
        mp.undo()
        time.tzset()
        for k in set(sys.modules) - antes:
            if k == "app" or k.startswith("app."):
                del sys.modules[k]


def _tab(farol, titulo):
    return next(t for t in farol.get("tabelas") or [] if t["titulo"] == titulo)


def _cartoes(h):
    return [(html.unescape(re.sub(r"<[^>]+>", "", r)).strip(),
             html.unescape(re.sub(r"<[^>]+>", "", v)).strip()) for r, v in RE_CARTAO.findall(h)]


def _esperados(render, kpis):
    """(rótulo, valor) de cada cartão da aba: `kpis_para_tela` (o cartão sem dado sai, T-0020).
    §10.7.2: "cartão inteiro, como os do Resumo", com ou sem `linhas`."""
    return [(k["rot"], k["valor"]) for k in render.kpis_para_tela(kpis)]


def _pagina(cli, rid, q):
    r = cli.get(f"/farol/{rid}?{q}")
    assert r.status_code == 200, (rid, q, r.status_code)
    return r.text


def _i(t, nome):
    return [c["nome"] for c in t["colunas"]].index(nome)


def _outro_valor(t, nome, padrao):
    """Um valor da coluna diferente do padrão (sem imprimir o valor)."""
    i = _i(t, nome)
    vals = sorted({str(ln[i]) for ln in t["linhas"] if ln[i] not in (None, "") and str(ln[i]) != padrao})
    assert vals, f"{t['titulo']}: a coluna {nome} só tem o padrão"
    return i, vals[0]


# Visita: no pacote real os 10 cartões têm `linhas`; a faixa mostra o cartão inteiro (§10.7.2),
# com as `linhas` ou sem elas (defeito achado no combinado e corrigido na web f188d73).
ABAS_COM_KPIS = (("pv_pedidos", "pedidos", "Pedidos"),
                 ("pl_entregas", "entregas", "Entregas"),
                 ("vc_visitas", "dia", "Dia a dia"))


# ============================================================== no padrão: os cartões da aba
@pytest.mark.parametrize("rid, aba, titulo", ABAS_COM_KPIS)
def test_T0033_padrao_mostra_os_kpis_padrao_da_aba(web, rid, aba, titulo):
    """§10.7.2, valor × regra: sem filtro, recorte nem estado, a faixa da aba
    mostra os `kpis_padrao` do farol guardado, na ordem, e sem o aviso."""
    cli, render, guardado = web
    t = _tab(guardado[rid], titulo)
    assert t.get("kpis_padrao"), f"{rid}/{titulo}: o pacote real não trouxe kpis_padrao"
    esperado = _esperados(render, t["kpis_padrao"])
    h = _pagina(cli, rid, f"aba={aba}")
    tela = _cartoes(h)
    assert esperado, f"{rid}/{titulo}: nenhum cartão com número"
    rot_t, rot_e = [r for r, _ in tela], [r for r, _ in esperado]
    assert rot_t == rot_e, f"{rid}/{titulo}: rótulos {rot_t} × {rot_e}"
    difere = [r for (r, v), (_, ve) in zip(tela, esperado) if v != ve]
    assert not difere, f"{rid}/{titulo}: valor diferente do kpis_padrao em {difere}"
    assert AVISO_CARTOES not in h


@pytest.mark.parametrize("rid, aba, titulo", ABAS_COM_KPIS[:2])
def test_T0033_estado_desconhecido_e_ignorado_e_os_cartoes_ficam(web, rid, aba, titulo):
    """Estado fora da lista do farol não conta como estado: segue o padrão."""
    cli, render, guardado = web
    esperado = _esperados(render, _tab(guardado[rid], titulo)["kpis_padrao"])
    h = _pagina(cli, rid, f"aba={aba}&uf=ZZ")
    assert _cartoes(h) == esperado and AVISO_CARTOES not in h


def test_T0033_visita_nao_tem_estado_e_os_cartoes_ficam_com_uf(web):
    """D5: o Visita não tem estado; `uf=AM` na URL não tira os cartões."""
    cli, render, guardado = web
    esperado = _esperados(render, _tab(guardado["vc_visitas"], "Dia a dia")["kpis_padrao"])
    h = _pagina(cli, "vc_visitas", "aba=dia&uf=AM")
    assert _cartoes(h) == esperado and AVISO_CARTOES not in h


# ============================================================== fora do padrão: saem e entra o aviso
def _sem_cartoes_com_aviso(h, esperado_padrao, rotulo):
    assert 'class="bc3-ks"' not in h, f"{rotulo}: a faixa ainda tem cartões"
    assert not _cartoes(h), f"{rotulo}: cartão na faixa fora do padrão"
    assert h.count(AVISO_CARTOES) == 1, f"{rotulo}: o AVISO_CARTOES tem de aparecer uma vez"
    assert "<b>—</b>" not in h and "BAP inteira</em>" not in h and "sem o filtro</em>" not in h, rotulo
    # nenhum número da aba (o da BAP inteira ou o do padrão) sobra na faixa
    faixa = h[h.index('class="bc3-faixa"'):h.index("</header>")]
    sobra = [r for r, v in esperado_padrao if f"<b>{html.escape(v)}</b>" in faixa]
    assert not sobra, f"{rotulo}: número do padrão na faixa: {sobra}"


@pytest.mark.parametrize("rid, aba, titulo", ABAS_COM_KPIS[:2])
def test_T0033_RN_GER_006_estado_tira_os_cartoes_da_aba_e_poe_o_aviso(web, rid, aba, titulo):
    """§10.7.2 e D5: com estado, os `kpis_padrao` saem e entra o
    `AVISO_CARTOES`, em cada estado do farol."""
    cli, render, guardado = web
    t = _tab(guardado[rid], titulo)
    esperado = _esperados(render, t["kpis_padrao"])
    ufs = sorted(set(t["uf_linhas"]))
    assert ufs, f"{rid}/{titulo}: sem uf_linhas"
    for uf in ufs:
        _sem_cartoes_com_aviso(_pagina(cli, rid, f"aba={aba}&uf={uf}"), esperado, f"{rid}/{titulo} uf={uf}")


def test_T0033_RN_GER_006_entregas_com_estado_conta_as_linhas_pela_uf_do_cliente(web):
    """Valor × regra: com estado, sai o cartão e fica a contagem de linhas,
    que é a das `uf_linhas` (UF do cliente, RN-GER-006) no mês do filtro oculto."""
    cli, _, guardado = web
    t = _tab(guardado["pl_entregas"], "Entregas")
    i_mes = _i(t, "MÊS")
    for uf in sorted(set(t["uf_linhas"])):
        n = sum(1 for k, ln in enumerate(t["linhas"])
                if str(ln[i_mes]) == MES_ROT and t["uf_linhas"][k] == uf)
        h = _pagina(cli, "pl_entregas", f"aba=entregas&uf={uf}")
        m = RE_TOTAL_ABA.search(h)
        tela = int(m.group(1)) if m else 0
        assert tela == n, f"Entregas uf={uf}: {tela} linhas na tela × {n} pelas uf_linhas"
        assert AVISO_CARTOES in h


def test_T0033_filtro_fora_do_padrao_tira_os_cartoes_da_aba(web):
    """§10.7.2: SITUAÇÃO diferente do padrão (EM ABERTO) no Pedidos, um
    VENDEDOR escolhido, a SITUAÇÃO das Entregas e a busca livre: os cartões
    da aba saem e fica o aviso."""
    cli, render, guardado = web
    ped = _tab(guardado["pv_pedidos"], "Pedidos")
    ent = _tab(guardado["pl_entregas"], "Entregas")
    e_ped = _esperados(render, ped["kpis_padrao"])
    e_ent = _esperados(render, ent["kpis_padrao"])
    i, v = _outro_valor(ped, "SITUAÇÃO", "EM ABERTO")
    _sem_cartoes_com_aviso(_pagina(cli, "pv_pedidos", f"aba=pedidos&f{i}={quote(v)}"), e_ped,
                           "Pedidos SITUAÇÃO fora do padrão")
    i, v = _outro_valor(ped, "VENDEDOR", "")
    _sem_cartoes_com_aviso(_pagina(cli, "pv_pedidos", f"aba=pedidos&f{i}={quote(v)}"), e_ped,
                           "Pedidos com VENDEDOR")
    i, v = _outro_valor(ent, "SITUAÇÃO", "")
    _sem_cartoes_com_aviso(_pagina(cli, "pl_entregas", f"aba=entregas&f{i}={quote(v)}"), e_ent,
                           "Entregas com SITUAÇÃO")
    _sem_cartoes_com_aviso(_pagina(cli, "pv_pedidos", "aba=pedidos&busca=ZZZZQ"), e_ped,
                           "Pedidos com busca")


def test_T0033_recorte_tira_os_cartoes_da_aba(web):
    """§10.7.2 e §11.4: com um recorte do PC ativo (Visita, Dia a dia),
    os cartões da aba saem e fica o aviso, em cada recorte."""
    cli, render, guardado = web
    t = _tab(guardado["vc_visitas"], "Dia a dia")
    esperado = _esperados(render, t["kpis_padrao"])
    assert t.get("recortes_linhas"), "Dia a dia sem recortes no pacote real"
    for n in range(len(t["recortes_linhas"])):
        _sem_cartoes_com_aviso(_pagina(cli, "vc_visitas", f"aba=dia&rec={n}"), esperado,
                               f"Dia a dia rec={n}")


def _topo_bap(render, farol):
    """Os `kpis` de cima da BAP inteira, como a faixa mostra (os com barras ficam no corpo do Resumo)."""
    return [(k["rot"], k["valor"]) for k in render.kpis_para_tela(farol["kpis"])
            if not k.get("estados") and not k.get("linhas")]


def test_T0033_solicitacao_sem_kpis_padrao_mostra_os_kpis_de_cima_sem_aviso(web):
    """§10.7.2 e D5, valor × regra: a Solicitação BAP não tem `kpis_padrao`:
    a aba mostra os `kpis` de cima do Pedidos, os mesmos do Resumo da BAP, e
    sem o aviso."""
    cli, render, guardado = web
    assert _tab(guardado["pv_pedidos"], "Solicitação BAP").get("kpis_padrao") is None
    esperado = _topo_bap(render, guardado["pv_pedidos"])
    assert esperado, "Pedidos sem os cartões de cima"
    resumo = _cartoes(_pagina(cli, "pv_pedidos", ""))
    h = _pagina(cli, "pv_pedidos", "aba=solicitacao")
    assert _cartoes(h) == esperado == resumo
    assert AVISO_CARTOES not in h


def test_T0033_solicitacao_sem_estado_ignora_o_uf_da_url(web):
    """D5 e §10.1: a Solicitação BAP não tem estado (o seletor fica fora), então
    os cartões de cima são os da BAP inteira mesmo com `uf` na URL. O link da
    aba leva o `&uf=` da aba Pedidos, então o caso é o da navegação normal."""
    cli, render, guardado = web
    esperado = _topo_bap(render, guardado["pv_pedidos"])
    for uf in sorted(set(_tab(guardado["pv_pedidos"], "Pedidos")["uf_linhas"])):
        tela = _cartoes(_pagina(cli, "pv_pedidos", f"aba=solicitacao&uf={uf}"))
        difere = [r for (r, v), (_, ve) in zip(tela, esperado) if v != ve]
        assert not difere, f"Solicitação uf={uf}: cartões do estado em {difere}"


def test_T0033_aba_sem_kpis_padrao_mostra_os_kpis_de_cima_mesmo_com_filtro(web):
    """§10.7.2: sem `kpis_padrao` (Aderência dia a dia), a aba mostra os
    `kpis` de cima, com ou sem filtro, e sem o aviso."""
    cli, render, guardado = web
    t = _tab(guardado["vc_visitas"], "Aderência dia a dia")
    assert t.get("kpis_padrao") is None
    esperado = _esperados(render, guardado["vc_visitas"]["kpis"])
    h0 = _pagina(cli, "vc_visitas", "aba=aderencia")
    assert _cartoes(h0) == esperado and esperado, "Aderência sem os cartões de cima"
    i, v = _outro_valor(t, "SUPERVISOR", "")
    h1 = _pagina(cli, "vc_visitas", f"aba=aderencia&f{i}={quote(v)}")
    assert _cartoes(h1) == esperado
    assert AVISO_CARTOES not in h0 and AVISO_CARTOES not in h1


def test_T0033_aviso_cartoes_da_web_e_o_do_contrato(web):
    """§10.7.6: o texto que a web põe é o do contrato (a T-0017 confere a
    constante; aqui, o que sai na página)."""
    txt = (RAIZ / ".coord" / "contratos" / "relatorio.md").read_text(encoding="utf-8")
    assert f"`{AVISO_CARTOES}`" in txt
    cli, _, _ = web
    assert AVISO_CARTOES in _pagina(cli, "pv_pedidos", "aba=pedidos&uf=AM")
