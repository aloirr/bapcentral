"""T-0055 (RN-GER-020): porta de leitura da web, só com token próprio. Dados 100% fictícios; token gerado na hora."""
import html
import json
import logging
import re
import secrets
from copy import deepcopy

import pytest
from conftest import postar
from farol_fixture import farol_entregas, farol_pedidos
from painel22_fixture import pacote_completo
from test_farois import _usuario

from app import VERSAO, leitura, render
from app.main import criar_app
from fastapi.testclient import TestClient

LEITURA = secrets.token_urlsafe(32)
CABECA = {"Authorization": f"Bearer {LEITURA}"}
# cartões que NUNCA podem sair (cada um por um motivo); o rótulo e o valor são inventados
INTRUSOS = [
    {"rotulo": "A pagar do mês", "valor": "R$ 9 mil", "cor": "info", "coluna": "TOTAL A PAGAR"},   # RN-GER-015 (pela coluna)
    {"rotulo": "Total a pagar", "valor": "R$ 8 mil", "cor": "info"},                              # RN-GER-015 (pelo rótulo)
    {"rotulo": "Meta RH", "valor": "R$ 7 mil", "cor": "info"},                                    # RN-GER-001
    {"rotulo": "Destaque do mês", "valor": "FULANO DE TAL", "cor": "ok"},                         # RN-GER-011 (nome no valor)
    {"rotulo": "Maior cliente", "valor": "R$ 5 mil", "cor": "ok"},                                # RN-GER-011
    {"rotulo": "Frete FOTO", "valor": "R$ 6 mil", "cor": "ok"},                                   # palavra de COLUNAS_FORA
    {"rotulo": "Observação", "valor": "ligar 92 99999-1234", "cor": "neutro"},                    # telefone
    {"rotulo": "Obs. 2", "valor": "fulano@exemplo.com", "cor": "neutro"},                         # e-mail
    {"rotulo": "Obs. 3", "valor": "12.345.678/0001-95", "cor": "neutro"},                         # CNPJ
    {"rotulo": "Obs. 4", "valor": "123.456.789-09", "cor": "neutro"},                             # CPF
]
RE_CNPJ = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
RE_CPF = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")
RE_FONE = re.compile(r"\(?\d{2}\)?[\s.\-]?9?\d{4}[\s.\-]\d{4}")
RE_MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _pacote():
    p = pacote_completo()
    ped = farol_pedidos()
    ped["kpis"] = ped["kpis"] + deepcopy(INTRUSOS)
    p["relatorios"]["pv_pedidos"] = ped
    p["relatorios"]["pl_entregas"] = farol_entregas()
    p["relatorios"]["pl_garantias"] = farol_pedidos()          # o diretor vê (só o Resumo)
    p["relatorios"]["vc_planner"] = farol_pedidos()            # idem
    return p


@pytest.fixture
def leit(admin, amb, monkeypatch):
    """Cliente do robô/consumidor com a porta ligada e o pacote fictício já enviado."""
    monkeypatch.setenv("BAP_WEB_LEITURA_TOKEN", LEITURA)
    assert postar(admin, _pacote()).status_code == 200
    with TestClient(criar_app(), base_url="https://testserver") as c:
        c.app_admin = admin
        yield c


def _acessos(amb) -> str:
    """Tudo o que a web registrou em `<dados>/acessos/`."""
    return "".join(a.read_text(encoding="utf-8") for a in (amb / "acessos").glob("ACESSO_*.jsonl"))


def _json(r):
    assert r.status_code == 200, r.text
    return r.json()


def _tudo(o):
    return json.dumps(o, ensure_ascii=False)


# ---------------------------------------------------------------- liga/desliga e token
def test_RN_GER_020_sem_variavel_desligada_404(cli, monkeypatch):
    monkeypatch.delenv("BAP_WEB_LEITURA_TOKEN", raising=False)
    with TestClient(criar_app(), base_url="https://testserver") as c:
        for m in ("get", "post", "delete"):
            r = getattr(c, m)("/api/leitura/painel", headers=CABECA)
            assert r.status_code == 404 and r.json() == {"erro": "não encontrado"}


def test_RN_GER_020_token_curto_ou_igual_ao_do_robo_desliga(cli, monkeypatch, caplog):
    from conftest import TOKEN
    monkeypatch.setenv("BAP_VISITAS_TOKEN", secrets.token_urlsafe(32))
    visitas = __import__("os").environ["BAP_VISITAS_TOKEN"]
    for ruim in ("curto", TOKEN, visitas, "segredo-de-teste-0123456789abcdef"):
        monkeypatch.setenv("BAP_WEB_LEITURA_TOKEN", ruim)
        with caplog.at_level(logging.WARNING), TestClient(criar_app(), base_url="https://testserver") as c:
            assert c.get("/api/leitura/painel", headers={"Authorization": f"Bearer {ruim}"}).status_code == 404
    assert "porta de leitura desligada" in caplog.text
    assert TOKEN not in caplog.text


def test_RN_GER_020_sem_token_401(leit):
    for url in ("/api/leitura/painel", "/api/leitura/resumo/pv_pedidos"):
        r = leit.get(url)
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_RN_GER_020_token_errado_401(leit):
    from conftest import TOKEN
    for ruim in (secrets.token_urlsafe(32), LEITURA[:-1], LEITURA + "x", TOKEN):     # inclusive o token do robô
        assert leit.get("/api/leitura/painel", headers={"Authorization": f"Bearer {ruim}"}).status_code == 401
    assert leit.get("/api/leitura/painel", headers={"Authorization": LEITURA}).status_code == 401   # sem "Bearer "


def test_RN_GER_020_post_put_patch_delete_405(leit):
    for m in ("post", "put", "patch", "delete"):
        for url in ("/api/leitura/painel", "/api/leitura/resumo/pv_pedidos"):
            r = getattr(leit, m)(url, headers=CABECA)
            assert r.status_code == 405 and r.headers["allow"] == "GET"
    assert leit.head("/api/leitura/painel", headers=CABECA).status_code == 405


def test_RN_GER_020_rid_que_o_diretor_nao_ve_404(leit):
    assert "vc_painel" not in render.FAROIS
    for rid in ("vc_painel", "nao_existe", "vc_visitas_x"):
        assert leit.get(f"/api/leitura/resumo/{rid}", headers=CABECA).status_code == 404
    perfis_sem = [r for r, (_, ps) in render.FAROIS.items() if "diretor" not in ps]
    for rid in perfis_sem[:3]:
        assert leit.get(f"/api/leitura/resumo/{rid}", headers=CABECA).status_code == 404


def test_RN_GER_020_sem_pacote_503(admin, amb, monkeypatch):
    monkeypatch.setenv("BAP_WEB_LEITURA_TOKEN", LEITURA)
    with TestClient(criar_app(), base_url="https://testserver") as c:
        assert c.get("/api/leitura/painel", headers=CABECA).status_code == 503
        assert c.get("/api/leitura/resumo/pv_pedidos", headers=CABECA).status_code == 503


# ---------------------------------------------------------------- o que sai
def test_RN_GER_020_numeros_iguais_ao_site(leit):
    """Cada valor do JSON está na tela do Painel e do farol vista pelo diretor, e vem do pacote sem recálculo."""
    adm = leit.app_admin
    d = _usuario(adm, "diretor.teste", "diretor")
    painel = _json(leit.get("/api/leitura/painel", headers=CABECA))
    assert painel["versao_web"] == VERSAO and painel["versao_leitura"] == 1
    assert [v["chave"] for v in painel["visoes"]][:3] == ["resultado", "produtividade", "por_dia_util"]
    norm = lambda t: re.sub(r"\s+", " ", html.unescape(t).replace(" ", " ")).strip()
    n_valores = 0
    for v in painel["visoes"]:
        tela = norm(d.get(f"/painel?aba={v['chave']}").text)
        assert v["cartoes"], v["chave"]
        for c in v["cartoes"]:
            n_valores += 1
            assert norm(c["valor"]) in tela, (v["chave"], c["valor"])
            for a in c.get("aneis", []):
                assert norm(a["pct"]) in tela
    assert n_valores >= 6
    # a origem: o pacote guardado (farol de origem) bate com o valor da rota
    origem = _pacote()["relatorios"]["vc_painel"]["abas"]["resultado"]["painel"]["blocos"][0]["dados"]["res"]
    res = next(v for v in painel["visoes"] if v["chave"] == "resultado")["cartoes"]
    assert [c["valor"] for c in res] == [c["valor"] for c in origem]
    assert painel["pacote"]["du"] == "13 de 19 DU" and painel["pacote"]["lote"]
    assert {"rid": "pv_pedidos", "nome": "Farol de Pedidos"} in painel["farois"]
    # o Resumo
    for rid in ("pv_pedidos", "pl_entregas"):
        r = _json(leit.get(f"/api/leitura/resumo/{rid}", headers=CABECA))
        assert r["rid"] == rid and r["nome"] == render.FAROIS[rid][0]
        tela = norm(d.get(f"/farol/{rid}").text)
        esperado = [k["valor"] for k in render.farol_para_tela(_pacote()["relatorios"][rid], None, rid)["kpis"]]
        assert r["cartoes"] and all(norm(c["valor"]) in tela for c in r["cartoes"])
        assert [c["valor"] for c in r["cartoes"]] == [v for v in esperado if v in {c["valor"] for c in r["cartoes"]}]
    ped = _json(leit.get("/api/leitura/resumo/pv_pedidos", headers=CABECA))
    assert {"320", "92,0%", "3,1 dia(s)"} <= {c["valor"] for c in ped["cartoes"]}


def test_RN_GER_020_lista_fechada_de_chaves_sem_tabela(leit):
    """RN-GER-014: o diretor não recebe tabela; só as chaves da lista fechada do desenho."""
    p = _json(leit.get("/api/leitura/painel", headers=CABECA))
    assert set(p) == {"versao_leitura", "versao_web", "pacote", "visoes", "farois"}
    assert set(p["pacote"]) == {"lote", "gerado_em", "dados_ate", "du"}
    for v in p["visoes"]:
        assert set(v) <= {"chave", "titulo", "sub", "cartoes"}
        for c in v["cartoes"]:
            assert set(c) <= {"titulo", "valor", "legenda", "aneis", "faixa", "estados", "rot", "cor"}
            for a in c.get("aneis", []):
                assert set(a) == {"rot", "pct", "sub", "tom"}
            for f in c.get("faixa", []):
                assert set(f) == {"rot", "var", "tom", "real"}
            if c.get("estados"):      # a forma de `render._barras`/`_mini`, sem reformatar
                assert set(c["estados"]) == {"barras", "legenda"}
                assert all(set(b) == {"uf", "txt", "rot", "tom"} for b in c["estados"]["barras"])
    r = _json(leit.get("/api/leitura/resumo/pl_entregas", headers=CABECA))
    assert set(r) == {"versao_leitura", "versao_web", "pacote", "rid", "nome", "cartoes"}
    assert all(set(c) == {"rot", "valor", "cor", "estados"} for c in r["cartoes"])
    txt = _tudo(p) + _tudo(r)
    for proibida in ("tabelas", "linhas", "detalhe", "insights", "blocos", "recortes", "como_ler", "ajuda", "Frete por estado"):
        assert proibida not in txt


def test_RN_GER_020_sem_pessoal_sem_meta_rh_sem_total_a_pagar(leit):
    saidas = [leit.get("/api/leitura/painel", headers=CABECA).text]
    saidas += [leit.get(f"/api/leitura/resumo/{r}", headers=CABECA).text
               for r in ("pv_pedidos", "pl_entregas", "pl_garantias", "vc_planner")]
    for t in saidas:
        for rx in (RE_CNPJ, RE_CPF, RE_FONE, RE_MAIL):
            assert not rx.search(t), rx.pattern
        assert not re.search(r"\bRH\b|TOTAL A PAGAR|FULANO|cliente\b", t, re.I)
        for dinheiro in ("R$ 9 mil", "R$ 8 mil", "R$ 7 mil", "R$ 5 mil", "R$ 6 mil"):          # os intrusos de dinheiro
            assert f'"{dinheiro}"' not in t
    ped = json.loads(saidas[1])
    assert {c["rot"] for c in ped["cartoes"]} == {"Pedidos", "Atendimento", "SLA médio"}      # os 9 intrusos saíram


def test_RN_GER_020_meta_rh_no_painel_sai(leit):
    """RN-GER-001: cartão de Painel com "meta RH" ou "RH" no texto é cortado pelo filtro final."""
    rel = deepcopy(pacote_completo()["relatorios"]["vc_painel"])
    rel["abas"]["resultado"]["painel"]["blocos"][0]["dados"]["res"][0]["legenda"] = "meta RH R$ 1 mi 2"
    montado = leitura.montar_painel(rel, {"lote": "x", "farois": {}}, "2026-11-20T08:30:00-04:00")
    assert len(next(v for v in montado["visoes"] if v["chave"] == "resultado")["cartoes"]) == 3
    res = next(v for v in leitura.limpar(montado)["visoes"] if v["chave"] == "resultado")["cartoes"]
    assert len(res) == 2     # o corte por texto é só do `limpar`: o cartão com RH sai inteiro


def test_RN_GER_020_limpar_e_funcao_pura_e_corta_o_cartao_inteiro():
    ok = {"titulo": "FATURADO", "valor": "R$ 1 mi", "legenda": "", "aneis": [], "faixa": [], "estados": None}
    com_estado = {**ok, "estados": {"legenda": "x", "barras": [{"uf": "AM", "txt": "fulano@exemplo.com", "rot": "", "tom": ""}]}}
    com_anel = {**ok, "aneis": [{"rot": "MTD", "pct": "9%", "sub": "meta RH", "tom": ""}]}
    com_faixa = {**ok, "faixa": [{"rot": "out", "var": "+1%", "tom": "", "real": "TOTAL A PAGAR"}]}
    fone = {**ok, "valor": "(92) 99999-1234"}
    entrada = {"visoes": [{"sub": "contato (92) 99999-1234", "cartoes": [ok, {**ok, "titulo": "Meta RH"}, fone, com_estado, com_anel, com_faixa]}],
               "cartoes": [ok, {**ok, "titulo": "Meta RH"}]}
    antes = deepcopy(entrada)
    saida = leitura.limpar(entrada)
    assert entrada == antes                                   # pura: não mexe na entrada
    assert saida["visoes"][0]["cartoes"] == [ok] and saida["cartoes"] == [ok] and saida["visoes"][0]["sub"] == ""
    assert leitura.limpar({"cartoes": []}) == {"cartoes": []}
    # "12345678" (8 dígitos sem separador) passa pelo `valor_so_numero`, mas o `limpar_texto` o toma por telefone: sai
    assert leitura.valor_so_numero("12345678") and leitura.limpar({"cartoes": [{**ok, "valor": "12345678"}]}) == {"cartoes": []}
    assert leitura.limpar({"cartoes": [{**ok, "valor": "1.234.567"}]})["cartoes"]       # com separador de milhar fica
    assert leitura.proibido("Total a pagar") and leitura.proibido("Vendedores") is False   # contagem por vendedor é agregado


def test_RN_GER_020_rotulo_por_vendedor_com_numero_sai_e_nome_no_valor_nao():
    k = {"rot": "VISITAS POR VENDEDOR", "valor": "12,5", "cor": "ok", "estados": None}
    assert leitura.cartao_farol(k)["valor"] == "12,5"
    assert leitura.cartao_farol({**k, "rot": "Destaque", "valor": "FULANO DE TAL"}) is None
    assert leitura.cartao_farol({**k, "valor": "R$ 1,3 mi"}) and leitura.cartao_farol({**k, "valor": "45 DU"}) and leitura.cartao_farol({**k, "valor": "—"})
    assert leitura.cartao_farol({**k, "valor": "3,1 dia(s)"}) and leitura.cartao_farol({**k, "valor": "2 h 30 min"})
    assert leitura.cartao_farol({**k, "valor": "JOÃO DA SILVA"}) is None and leitura.cartao_farol({**k, "valor": "12 semanas"}) is None


# ---------------------------------------------------------------- log e limite
def test_RN_GER_020_token_fora_do_log(leit, caplog, amb):
    with caplog.at_level(logging.DEBUG):
        leit.get("/api/leitura/painel", headers={**CABECA, "X-Forwarded-For": "203.0.113.77"})
        leit.get("/api/leitura/painel", headers={"Authorization": "Bearer errado-errado-errado"})
        leit.get("/api/leitura/resumo/pv_pedidos", headers=CABECA)
        leit.post("/api/leitura/painel", headers=CABECA)
    assert "203.0.113" not in caplog.text and LEITURA not in caplog.text and "errado-errado" not in caplog.text and "Authorization" not in caplog.text
    texto = _acessos(amb)
    assert LEITURA not in texto and "porta-leitura" in texto and '"ok"' in texto
    assert "testserver" not in texto and "127.0.0" not in texto and "203.0" not in texto


def test_T0055_limite_por_minuto():
    t = [0.0]
    lim = leitura.Limite(por_ip=3, total=5, relogio=lambda: t[0])
    assert [lim.ip_ok("a") for _ in range(4)] == [True, True, True, False]
    assert all(lim.ip_ok("b") for _ in range(3)) and not lim.ip_ok("b")
    assert [lim.total_ok() for _ in range(6)] == [True] * 5 + [False]       # o total só conta quem chamou com token válido
    t[0] = 61.0
    assert lim.ip_ok("a") and lim.total_ok()


def test_T0055_falhas_viram_uma_linha_agregada_por_janela():
    t = [0.0]
    lim = leitura.Limite(relogio=lambda: t[0])
    assert lim.agregada() is None
    for _ in range(3):
        lim.falha("negado")
    lim.falha("limite")
    assert lim.agregada() is None
    t[0] = 60.0                                  # a janela virou: a linha pendente sai em qualquer chamada, sem nova falha
    assert lim.agregada() == "falhas negado=3 limite=1"
    assert lim.agregada() is None


def test_T0055_falha_401_nao_grava_em_acessos_nem_loga_por_chamada(leit, caplog, amb):
    with caplog.at_level(logging.DEBUG, logger="bap_web"):
        for _ in range(5):
            assert leit.get("/api/leitura/painel").status_code == 401
    assert "porta de leitura: falhas" not in caplog.text                  # a linha agregada só sai quando a janela vira
    assert "porta-leitura" not in _acessos(amb)


def test_T0055_limite_429_na_rota(leit, amb):
    codigos = [leit.get("/api/leitura/painel", headers=CABECA).status_code for _ in range(leitura.POR_IP + 2)]
    assert codigos[:leitura.POR_IP] == [200] * leitura.POR_IP and codigos[-2:] == [429, 429]
    r = leit.get("/api/leitura/painel", headers=CABECA)
    assert r.headers["retry-after"] == "60" and r.json() == {"erro": "muitas chamadas"}
    assert leit.get("/api/leitura/painel").status_code == 429      # a recusa por IP vem antes do token
    linhas = _acessos(amb).splitlines()
    linhas = [x for x in linhas if "porta-leitura" in x]
    assert len(linhas) == leitura.POR_IP and all('"ok"' in x and '"api"' in x for x in linhas)    # 429 não grava linha por chamada


def test_T0055_ip_do_limite_e_o_ultimo_do_xff(leit):
    for _ in range(leitura.POR_IP):                               # esgota o IP "9.9.9.9" (o do proxy); o do cliente forjado não conta
        leit.get("/api/leitura/painel", headers={**CABECA, "X-Forwarded-For": f"1.1.1.{_}, 9.9.9.9"})
    assert leit.get("/api/leitura/painel", headers={**CABECA, "X-Forwarded-For": "2.2.2.2, 9.9.9.9"}).status_code == 429
    assert leit.get("/api/leitura/painel", headers={**CABECA, "X-Forwarded-For": "9.9.9.9, 8.8.8.8"}).status_code == 200


def test_T0055_carimbo_igual_ao_da_tela(leit, amb):
    """O `gerado_em` é o da entrada do farol no índice (a mesma função da página), com reserva no do lote."""
    from conftest import guardado
    ind = guardado(amb)["indice"]
    p = _json(leit.get("/api/leitura/painel", headers=CABECA))
    assert p["pacote"]["gerado_em"] == (ind["farois"]["vc_painel"].get("gerado_em") or ind["gerado_em"])
    assert p["pacote"]["lote"] == ind["lote"]
    r = _json(leit.get("/api/leitura/resumo/pv_pedidos", headers=CABECA))
    # a fixture tem `baixado_em` (24/11 08:10) a mais de 60 min do `gerado_em` (20/11): senão o cabeçalho esconde o texto
    assert r["pacote"]["dados_ate"] == "24/11/2026 08:10"       # `baixado_em` como a tela mostra (fmt_manaus)
    d = _usuario(leit.app_admin, "diretor.carimbo", "diretor")
    assert r["pacote"]["dados_ate"] in d.get("/farol/pv_pedidos").text         # o cabeçalho de /farol/{rid}
    assert p["pacote"]["dados_ate"] is None                     # o pacote do painel não traz `baixado_em`
    assert r["pacote"]["du"] is None                            # /farol/{rid} não mostra DU


def test_RN_GER_020_todo_valor_so_tem_numero(leit):
    """Nome de pessoa não é detectável por `limpar_texto`: todo `valor` só tem números, R$, mi, mil, %, DU, dia(s), h, min, un, x e —."""
    ok = re.compile(r"^(?:[\d.,\-+−\s%—–()]|R\$|mil?|DU|dias?|s|h|min|un|x)*$")
    p = _json(leit.get("/api/leitura/painel", headers=CABECA))
    vs = [c["valor"] for v in p["visoes"] for c in v["cartoes"]]
    vs += [a["pct"] for v in p["visoes"] for c in v["cartoes"] for a in c.get("aneis", [])]
    vs += [c["valor"] for r in ("pv_pedidos", "pl_entregas") for c in _json(leit.get(f"/api/leitura/resumo/{r}", headers=CABECA))["cartoes"]]
    assert vs and all(ok.match(v) for v in vs), [v for v in vs if not ok.match(v)]


def test_T0055_limite_guarda_no_maximo_mil_ips():
    lim = leitura.Limite(por_ip=1, total=10**9, relogio=lambda: 0.0)
    for i in range(leitura.MAX_IPS + 50):
        lim.ip_ok(f"ip{i}")
    assert len(lim._ips) <= leitura.MAX_IPS


def test_RN_GER_020_texto_proibido_palavra_a_palavra():
    assert render.texto_proibido("E-MAIL do vendedor") and render.texto_proibido("Foto") and render.texto_proibido("Endereço")
    assert not render.texto_proibido("KM/CLIENTE") and not render.texto_proibido("Clientes positivados")
