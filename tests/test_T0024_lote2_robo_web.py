"""T-0024 (lote 2) × T-0035 (ADR 0003, contrato §10.8): o robô da raiz manda os
5 faróis do lote 2 à web real (web/app) pelo formato 2 (um POST por farol e o
`fechar`), e a web os abre.

1. Farol do lote 2 acima do teto do farol (WEB_FAROL_TETO_MB = 8): pela regra
   do §10.8.7 (ADR 0003), o lote 2 não tem cortes próprios em
   _CORTES_FAROL_WEB, então o único corte é o último: TODAS as abas
   (`tabelas`) saem de uma vez, com o AVISO_ABAS_FORA (as abas na ordem do
   PC); os cartões, o painel e os recortes ficam; o resto do pacote segue
   inteiro; e a web aceita o farol assim, sem as abas (abre o Resumo em 200).
   O farol é FICTÍCIO (web/tests/lote2_fixture.py; sem ela, o mínimo daqui).
2. Pacote REAL das bases congeladas (NOV/2026, hoje = 24/11/2026): os 5 faróis
   passam pelo POST por farol, abrem em 200 (o Resumo e cada aba) para quem
   vê, e em 403 para quem não vê. Não há RN de perfil para o lote 2 (a única
   é a RN-POS-004, da Inadimplência): a matriz esperada é a do quadrado do PC
   (decisão D1 A da T-0017, estendida ao lote 2 na T-0024: o diretor vê só o
   Resumo) e está escrita aqui, à mão, para que mudar o perfil na web exija
   mudar o teste. Valor × regra: todo cartão da tela está no farol que o robô
   mandou (a web não recalcula).

- Sem fastapi (o CI da raiz não instala), a parte da web é pulada; o corte do
  robô (função pura) roda sempre.
- Sem o lote 2 no robô (#91) ou na web (#89), a parte que depende dele é
  pulada, com o motivo: o teste vale em qualquer ordem de merge.
- Nenhum valor de célula é impresso: as mensagens de falha só têm id, título,
  perfil e números agregados (regra 6 do CLAUDE.md).
"""
import copy
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
WEB_TESTS = RAIZ / "web" / "tests"
MANAUS = ZoneInfo("America/Manaus")
MB = 1024 * 1024
HOJE = date(2026, 11, 24)
LOTE2 = ("pv_indicadores", "vc_base", "vc_planner", "pl_giro", "pl_frw")
AVISO_ABAS_FORA = "Abas fora desta atualização: {lista}. Veja no PC."
PERFIS = ("admin", "diretor", "gerente", "pos_venda", "pre_venda", "vendas")
# quem abre o farol (o quadrado do PC) e quem vê as abas (D1 A: o diretor só o Resumo)
VE_FAROL = {
    "pv_indicadores": {"admin", "diretor", "gerente", "pre_venda"},
    "vc_base": {"admin", "diretor", "gerente", "vendas"},
    "vc_planner": {"admin", "diretor", "gerente", "vendas"},
    "pl_giro": {"admin", "diretor", "gerente", "vendas"},
    "pl_frw": {"admin", "diretor", "gerente", "pre_venda", "pos_venda"},
}
VE_ABAS = {rid: p - {"diretor"} for rid, p in VE_FAROL.items()}

# o harness da web real (TestClient + o `requests` de mentira) é o da T-0035
from test_T0035_robo_web import BASE, TOKEN, _cartoes, _indice, _web, web_mod  # noqa: E402,F401


def _tam_sem_anexos(f):
    return len(ba._json_farol_web({k: v for k, v in f.items()
                                   if k not in ba._ANEXOS_FAROL_WEB}))


def _agora():
    return datetime.now(MANAUS).replace(microsecond=0).isoformat()


def _farol_minimo(rid):
    """Farol fictício mínimo do lote 2 (3 abas, cartão, painel e recorte), sem a fixture da web."""
    col = [{"nome": "FILIAL", "tipo": "texto"}, {"nome": "ITEM", "tipo": "texto"},
           {"nome": "QTD", "tipo": "int"}]
    return {"forma": "farol", "titulo": f"Farol fictício {rid}",
            "kpis": [{"rotulo": "Itens", "valor": "3", "cor": "ok", "detalhe": ""}],
            "painel": {"blocos": []}, "insights_painel": [], "avisos": [],
            "recortes": {"AM": {"kpis": [{"rotulo": "Itens", "valor": "1", "cor": "ok", "detalhe": ""}]}},
            "baixado_em": "2026-11-24T08:10:00-04:00",
            "tabelas": [{"titulo": f"Aba fictícia {i}", "colunas": col,
                         "linhas": [["FILIAL FICTICIA AM", f"ITEM {j:03d}", j] for j in range(20)],
                         "tons": [""] * 20, "total": None, "filtros": []} for i in (1, 2, 3)]}


def _fixture_lote2(so_web=False):
    """O pacote fictício do lote 2 da web (abas, colunas e cartões reais; valores inventados). Sem a
    fixture da web (PR #89 fora do main): o farol mínimo daqui, ou skip se `so_web`."""
    if str(WEB_TESTS) not in sys.path:
        sys.path.insert(0, str(WEB_TESTS))
    try:
        from lote2_fixture import pacote_lote2                # noqa: PLC0415
    except ImportError:
        if so_web:
            pytest.skip("sem web/tests/lote2_fixture.py (lote 2 da web, PR #89)")
        return {"versao_contrato": 1, "gerado_em": "2026-11-24T08:30:00-04:00", "ano": 2026, "mes": 11,
                "relatorios": {rid: _farol_minimo(rid) for rid in LOTE2}}
    return pacote_lote2()


def _inflar(farol, mb):
    """Cópia do farol com a 1ª aba repetida até o JSON sem anexos passar de `mb` MB."""
    f = copy.deepcopy(farol)
    t = f["tabelas"][0]
    base_l, base_t = list(t["linhas"]), list(t.get("tons") or [""] * len(t["linhas"]))
    while _tam_sem_anexos(f) <= mb * MB:
        t["linhas"] += [list(ln) for ln in base_l] * 50
        t["tons"] = (t.get("tons") or []) + base_t * 50
    return f


def _web_tem_lote2():
    from app import render                                    # noqa: PLC0415
    if not set(LOTE2) <= set(render.FAROIS):
        pytest.skip("a web não tem o lote 2 (PR #89)")


def _usuario(admin, perfil):
    """Um cliente logado com o perfil (criado pelo admin, como na tela /usuarios)."""
    from fastapi.testclient import TestClient                 # noqa: PLC0415

    def tok(cli, url):
        return re.search(r'name="csrf" value="([^"]+)"', cli.get(url).text).group(1)
    if perfil == "admin":
        return admin
    login, senha, nova = "t24." + perfil.replace("_", ""), "senha-de-teste-12", "senha-nova-teste-9"
    r = admin.post("/usuarios", data={"acao": "criar", "login": login, "perfil": perfil,
                                      "senha": senha, "csrf": tok(admin, "/usuarios")})
    assert r.status_code == 200, perfil
    c = TestClient(admin.app, base_url=BASE)
    assert c.post("/login", data={"usuario": login, "senha": senha, "csrf": tok(c, "/login")},
                  follow_redirects=False).status_code == 303, perfil
    c.post("/senha", data={"atual": senha, "nova": nova, "confirma": nova, "csrf": tok(c, "/senha")})
    return c


# ------------------------------------------------ 1. farol do lote 2 acima do teto (§10.8.7)
@pytest.mark.parametrize("rid", LOTE2)
def test_ADR0003_10_8_7_lote2_acima_do_teto_perde_todas_as_abas_com_aviso(rid):
    """§10.8.7 (ADR 0003): sem corte próprio, o farol do lote 2 acima de 8 MB perde TODAS as abas de
    uma vez, com um aviso só (as abas na ordem do PC, em 1º); cartões, painel e recortes ficam; cabe
    no teto; a entrada não muda."""
    assert rid not in ba._CORTES_FAROL_WEB               # o único corte é o das `tabelas`
    p = _fixture_lote2()
    grande = _inflar(p["relatorios"][rid], ba.WEB_FAROL_TETO_MB)
    antes = json.dumps(grande, ensure_ascii=False, sort_keys=True)
    assert _tam_sem_anexos(grande) > ba.WEB_FAROL_TETO_MB * MB
    out = ba._cortar_farol_web(rid, grande)
    assert "tabelas" not in out
    assert _tam_sem_anexos(out) <= ba.WEB_FAROL_TETO_MB * MB
    fora = [a for a in out["avisos"] if a.startswith(AVISO_ABAS_FORA.split("{")[0])]
    assert fora == [AVISO_ABAS_FORA.format(lista=", ".join(t["titulo"] for t in grande["tabelas"]))]
    assert out["avisos"][0] == fora[0]                   # abas fora em 1º (§10.7.6)
    for chave in ("kpis", "painel", "recortes", "insights_painel", "titulo", "baixado_em"):
        assert out.get(chave) == grande.get(chave), (rid, chave)
    assert json.dumps(grande, ensure_ascii=False, sort_keys=True) == antes


def test_ADR0003_10_8_7_lote2_abaixo_do_teto_nao_muda():
    """O corte só age acima do teto: o farol do lote 2 que cabe volta o mesmo (sem aviso novo)."""
    p = _fixture_lote2()
    for rid in LOTE2:
        f = p["relatorios"][rid]
        assert _tam_sem_anexos(f) <= ba.WEB_FAROL_TETO_MB * MB, rid
        assert ba._cortar_farol_web(rid, f) is f, rid


def test_ADR0003_10_8_7_lote2_acima_do_teto_o_resto_segue_e_a_web_aceita_sem_abas(web_mod, monkeypatch):
    """§10.8.7 de ponta a ponta: no pacote do lote 2 com o Giro acima de 8 MB, o robô (formato 2) manda
    os 5 faróis; a web guarda os 5 (nada no `manter`); o Giro chega sem abas, com o aviso, e abre o
    Resumo em 200 com os cartões; os outros 4 chegam inteiros, com as abas."""
    cli, dados, m = _web(web_mod, "teto", monkeypatch)
    _web_tem_lote2()
    p = _fixture_lote2(so_web=True)
    p["gerado_em"] = _agora()
    p["relatorios"]["pl_giro"] = _inflar(p["relatorios"]["pl_giro"], ba.WEB_FAROL_TETO_MB)
    log = []
    assert ba.enviar_pacote(copy.deepcopy(p), url=BASE, token=TOKEN, log=log.append) is True
    assert any("por farol" in x for x in log), "o robô não usou o formato 2"
    assert not any("manter" in x and "0 no manter" not in x for x in log)
    ind = _indice(dados)
    assert set(ind["farois"]) == set(LOTE2)
    idx = m["pacotes"].Indice(dados)
    giro = idx.farol("pl_giro")
    assert giro is not None and "tabelas" not in giro
    assert ind["farois"]["pl_giro"]["herdado_de"] is None
    lista = ", ".join(t["titulo"] for t in p["relatorios"]["pl_giro"]["tabelas"])
    assert AVISO_ABAS_FORA.format(lista=lista) in giro["avisos"]
    assert giro["kpis"] == p["relatorios"]["pl_giro"]["kpis"]
    h = cli.get("/farol/pl_giro")
    assert h.status_code == 200
    assert _cartoes(h.text), "a tela do Giro sem cartões"
    assert "aba=todos-os-produtos" not in h.text                      # sem abas na tela
    for rid in LOTE2:
        if rid == "pl_giro":
            continue
        f = idx.farol(rid)
        assert [t["titulo"] for t in f.get("tabelas") or []] == [
            t["titulo"] for t in p["relatorios"][rid]["tabelas"]], rid
        assert not [a for a in f.get("avisos") or [] if a.startswith(AVISO_ABAS_FORA.split("{")[0])], rid
        assert cli.get(f"/farol/{rid}").status_code == 200, rid


# ------------------------------------------------ 2. pacote real: POST por farol, 200 e 403 por perfil
@pytest.fixture(scope="module")
def pacote_real():
    """Os 5 faróis do lote 2 como o coletar_relatorios_web monta, com as bases congeladas."""
    if not set(LOTE2) <= set(ba.FAROIS_WEB):
        pytest.skip("o robô não tem o lote 2 (PR #91)")
    rels = {}
    for rid in LOTE2:
        params = ba.params_farol_web(rid, 2026, 11)
        rels[rid] = rn.montar(rid, RAIZ, hoje=HOJE, params=params)
        if rid in ba.RIDS_KPIS_POR_UF_WEB:
            rels[rid + "_uf"] = ba.montar_por_uf_web(rid, rels[rid], RAIZ, params, HOJE)
    p = ba.montar_pacote_web(rels, 2026, 11, raiz=RAIZ)
    assert set(p["relatorios"]) == set(LOTE2)
    return p


def test_T0024_pacote_real_do_lote2_pelo_formato2_abre_em_200_e_403_por_perfil(web_mod, monkeypatch,
                                                                                pacote_real):
    """Os 5 faróis reais pelo POST por farol (§10.8): guardados sem herança, cada um com o sha dos bytes
    que o robô mandou; o Resumo e cada aba abrem em 200 para quem vê e em 403 para quem não vê
    (VE_FAROL e VE_ABAS, o quadrado do PC); todo cartão da tela está no farol do robô."""
    import hashlib                                                    # noqa: PLC0415
    cli, dados, m = _web(web_mod, "real", monkeypatch)
    _web_tem_lote2()
    from app import render, tabelas                                   # noqa: PLC0415
    # a matriz da web é a escrita aqui (mudar o perfil exige mudar o teste)
    for rid in LOTE2:
        assert set(render.FAROIS[rid][1]) == VE_FAROL[rid], rid
        assert set(tabelas.VE_TABELAS[rid]) == VE_ABAS[rid], rid
    p = copy.deepcopy(pacote_real)
    p["gerado_em"] = _agora()
    log = []
    assert ba.enviar_pacote(copy.deepcopy(p), url=BASE, token=TOKEN, log=log.append) is True
    assert any("por farol" in x for x in log), "o robô não usou o formato 2"
    assert not any("manter" in x and "0 no manter" not in x for x in log)
    ind = _indice(dados)
    assert set(ind["farois"]) == set(LOTE2)
    idx = m["pacotes"].Indice(dados)
    clis = {pf: _usuario(cli, pf) for pf in PERFIS}
    for rid in LOTE2:
        e = ind["farois"][rid]
        corpo = ba._json_farol_web(ba._cortar_farol_web(rid, p["relatorios"][rid]))
        assert e["herdado_de"] is None and e["sha256"] == hashlib.sha256(corpo).hexdigest(), rid
        rel = idx.farol(rid)
        assert rel is not None, rid
        abas = tabelas.abas_do_farol(rid, rel)
        assert [tit for _c, tit in abas] == [t["titulo"] for t in p["relatorios"][rid].get("tabelas") or []], rid
        txt = json.dumps(p["relatorios"][rid], ensure_ascii=False)
        for pf, c in clis.items():
            h = c.get(f"/farol/{rid}")
            esperado = 200 if pf in VE_FAROL[rid] else 403
            assert h.status_code == esperado, (rid, pf, h.status_code)
            if esperado == 200:
                cart = _cartoes(h.text)
                assert cart, (rid, pf)
                assert all(x.split(" | ")[-1] in txt for x in cart), (rid, pf, "cartão fora do pacote")
            for chave, _tit in abas:
                r = c.get(f"/farol/{rid}?aba={chave}")
                esp = 200 if pf in VE_ABAS[rid] else 403
                assert r.status_code == esp, (rid, pf, chave, r.status_code)
