"""T-0035 (ADR 0003, contrato §10.8): o robô da raiz contra a web real (web/app).

A web roda num TestClient, e o robô fala com ela por um `requests` de mentira
que repassa a chamada ao TestClient. Assim o `/saude`, o farol, o `fechar` e o
formato 1 são os da web de verdade. Os faróis são as fixtures fictícias da web
(web/tests): nenhum cliente, CNPJ, telefone ou vendedor real.

- Sem fastapi (o CI da raiz não instala), os testes da web real são pulados.
  Os que só leem as constantes (AST) rodam sempre.
- A prova com as bases congeladas e o uvicorn (as 4 combinações robô × web)
  fica em docs/testes/T-0035.md. Ela é longa demais para o CI.

Regras citadas: RN-POS-003 (o diário da cobrança, com o `pacote_sha`) e
RN-GER-012 (a edição só no site, com a marca "Aguardando o PC"). O transporte
em si não tem RN: os nomes citam a ADR 0003.
"""
import ast
import base64
import copy
import hashlib
import json
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import bap_automation as ba

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
MANAUS = ZoneInfo("America/Manaus")
MB = 1024 * 1024
TOKEN = "t" * 43
ADMIN, SENHA0, SENHA1 = "admin.teste", "senha-inicial-123", "nova-senha-forte-1"
BASE = "https://testserver"


# ---------------------------------------------------------------- constantes (sem fastapi)
def _const_web(nome):
    """O valor da constante `nome` em web/app/pacotes.py, lido pela AST (sem importar a web)."""
    arv = ast.parse((WEB / "app" / "pacotes.py").read_text(encoding="utf-8"))
    for n in arv.body:
        if not isinstance(n, ast.Assign):
            continue
        for alvo in n.targets:
            if isinstance(alvo, ast.Name):
                pares = [(alvo, n.value)]
            elif isinstance(alvo, ast.Tuple) and isinstance(n.value, ast.Tuple):
                pares = list(zip(alvo.elts, n.value.elts))
            else:
                pares = []
            for a, v in pares:
                if isinstance(a, ast.Name) and a.id == nome:
                    return eval(compile(ast.Expression(v), nome, "eval"), {"MB": MB})  # noqa: S307
    raise KeyError(nome)


def test_ADR0003_tetos_dos_anexos_no_robo_sao_os_da_web():
    """§10.8.7: acima dos tetos da web o robô tira só o anexo. Para isso os
    números têm de ser os mesmos dos dois lados (senão a web recusa o farol)."""
    assert ba.MAX_PNG_B64 == _const_web("MAX_PNG_B64")
    assert ba.MAX_CSVS_WEB == _const_web("MAX_CSVS")
    assert ba.MAX_CSV_BYTES_WEB == _const_web("MAX_CSV_BYTES")
    assert ba.MAX_CSVS_TOTAL == _const_web("MAX_CSVS_TOTAL")
    # o leitor dos CSVs no PC (T-0021) já fica dentro do teto da web
    assert ba.CSV_WEB_MAX_ARQUIVOS <= ba.MAX_CSVS_WEB
    assert ba.CSV_WEB_MAX_BYTES <= ba.MAX_CSV_BYTES_WEB
    assert ba.CSV_WEB_MAX_TOTAL <= ba.MAX_CSVS_TOTAL


def test_ADR0003_teto_do_farol_no_robo_cabe_no_da_web():
    """§10.8.7 × §10.8.3: o farol cortado pelo robô (8 MB) passa no teto da web (10 MB)."""
    assert ba.WEB_FAROL_TETO_MB * MB < _const_web("FAROL_JSON_MAX")
    assert _const_web("FAROL_JSON_MAX") <= _const_web("FAROL_CORPO_MAX")


@pytest.mark.parametrize("gerado_em, lote", [
    ("2026-11-26T08:30:00-04:00", "20261126T083000"),
    ("2026-11-26T08:30:00", "20261126T083000"),         # sem fuso = já Manaus
])
def test_ADR0003_lote_do_robo_igual_ao_da_web_em_manaus(gerado_em, lote):
    assert ba._lote_web(gerado_em) == lote


@pytest.mark.xfail(strict=True, reason="achado T-0035 (modulo-robo): _lote_web não converte para "
                   "Manaus; com outro fuso, o `fechar` dá 422 (nome_arquivo da web converte)")
def test_ADR0003_lote_do_robo_converte_outro_fuso_para_manaus():
    assert ba._lote_web("2026-11-26T12:30:00+00:00") == "20261126T083000"


def test_ADR0003_farol_que_nao_montou_nao_vai_no_pacote_nem_no_manter():
    """ADR 0003, §4.4: o `erro_montagem` some (como hoje) e nunca vai no `manter`."""
    p = ba.montar_pacote_web({"pv_pedidos": {"erro_montagem": "KeyError"}}, 2026, 11, cortar=False)
    assert "pv_pedidos" not in p["relatorios"]


# ---------------------------------------------------------------- a web real
@pytest.fixture
def web_mod(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        monkeypatch.delitem(sys.modules, m)
    monkeypatch.syspath_prepend(str(WEB / "tests"))
    monkeypatch.syspath_prepend(str(WEB))
    monkeypatch.setenv("SESSION_SECRET", "segredo-de-teste-0123456789abcdef")
    monkeypatch.setenv("BAP_WEB_TOKEN", TOKEN)
    monkeypatch.setenv("BAP_ADMIN_USUARIO", ADMIN)
    monkeypatch.setenv("BAP_ADMIN_SENHA_INICIAL", SENHA0)
    monkeypatch.setenv("BAP_WEB_PACOTE_MAX_MB", "25")
    monkeypatch.setenv("TZ", "America/Manaus")
    time.tzset()
    monkeypatch.setattr(ba.time, "sleep", lambda s: None)
    monkeypatch.setattr(ba, "_base_web", lambda u: BASE)
    yield tmp_path
    monkeypatch.undo()
    time.tzset()


class _Requests:
    """O `requests` que o robô usa, repassado ao TestClient (mesmos nomes e parâmetros)."""

    def __init__(self, cli):
        self.cli = cli

    def get(self, url, timeout=None, **kw):
        return self.cli.get(url[len(BASE):], **kw)

    def post(self, url, data=None, headers=None, timeout=None):
        return self.cli.post(url[len(BASE):], content=data, headers=headers)


def _web(web_mod, nome, monkeypatch):
    """Uma web nova numa pasta própria, com o admin logado. Devolve (cli, dados, módulos da web)."""
    from fastapi.testclient import TestClient

    from app import cobranca, edicoes, main, pacotes
    dados = web_mod / nome
    monkeypatch.setenv("BAP_WEB_DADOS", str(dados))
    cli = TestClient(main.criar_app(), base_url=BASE)
    cli.__enter__()

    def tok(url):
        return re.search(r'name="csrf" value="([^"]+)"', cli.get(url).text).group(1)
    assert cli.post("/login", data={"usuario": ADMIN, "senha": SENHA0, "csrf": tok("/login")},
                    follow_redirects=False).status_code == 303
    assert cli.post("/senha", data={"atual": SENHA0, "nova": SENHA1, "confirma": SENHA1,
                                    "csrf": tok("/senha")}, follow_redirects=False).status_code == 303
    req = _Requests(cli)
    monkeypatch.setitem(sys.modules, "requests", req)     # o formato 1 faz `import requests`
    mods = {"cobranca": cobranca, "edicoes": edicoes, "pacotes": pacotes}
    return cli, dados, mods


def _png(n=200):
    return base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * n).decode()


def _pacote(gerado_em):
    """Quatro faróis fictícios da web (Pedidos com abas e parciais, Inadimplência com a fila da
    cobrança, Entregas, Visita), no topo do contrato."""
    from cobranca_fixture import farol_com_cobranca
    from farol_fixture import farol_entregas, farol_pedidos_com_abas, farol_visitas
    ped = farol_pedidos_com_abas()
    ped["parciais"] = {q: {"rotulo": q.upper(), "png": _png()} for q in ("acum", "d1", "hoje")}
    ped["csvs_protheus"] = [{"nome": "261126_1_LJ01_BAPReversaLoja.csv", "conteudo": "COD;QTD\r\n1;2\r\n"}]
    vis = farol_visitas()
    vis["parciais"] = {"acum": {"rotulo": "ACUM", "png": _png()}}
    return {"versao_contrato": 1, "gerado_em": gerado_em, "ano": 2026, "mes": 11,
            "relatorios": {"pv_pedidos": ped, "pl_inadimplencia": farol_com_cobranca(),
                           "pl_entregas": farol_entregas(), "vc_visitas": vis}}


def _agora(horas=0.0):
    return (datetime.now(MANAUS) - timedelta(hours=horas)).replace(microsecond=0).isoformat()


RE_CART = [re.compile(p, re.S) for p in (
    r'class="bc3-k[^"]*"><small>(.*?)</small><b>(.*?)</b>', r'class="kpi-valor">(.*?)</div>',
    r'class="pl-v">(.*?)(?:<small>|</div>)', r'class="rc-valor">(.*?)</div>')]


def _cartoes(html):
    out = []
    for rx in RE_CART:
        out += [" | ".join(m) if isinstance(m, tuple) else m for m in rx.findall(html)]
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip() for x in out]


def _indice(dados):
    lotes = sorted(d for d in (dados / "pacotes").iterdir() if (d / "indice.json").is_file())
    return json.loads((lotes[-1] / "indice.json").read_text(encoding="utf-8"))


def test_ADR0003_formato2_e_formato1_guardam_e_mostram_o_mesmo_farol(web_mod, monkeypatch):
    """Valor × regra: o mesmo pacote, pelo formato 2 (robô novo, web nova) e pelo formato 1
    (robô antigo, web nova divide em lote), guarda o mesmo farol e mostra os mesmos cartões."""
    p = _pacote(_agora())
    log2, log1 = [], []
    cli2, d2, m2 = _web(web_mod, "f2", monkeypatch)
    assert cli2.get("/saude").json()["pacote"]["formatos"] == [1, 2]
    assert ba.enviar_pacote(copy.deepcopy(p), url=BASE, token=TOKEN, log=log2.append) is True
    assert any("por farol" in m for m in log2), "o robô novo não usou o formato 2"
    cli1, d1, m1 = _web(web_mod, "f1", monkeypatch)
    assert ba.enviar_pacote_web(copy.deepcopy(p), url=BASE, token=TOKEN, log=log1.append) is True
    s2, s1 = cli2.get("/saude").json(), cli1.get("/saude").json()
    assert s2["pacote"]["origem"] == "por_farol" and s1["pacote"]["origem"] == "inteiro"
    assert s2["pacote"]["farois"] == s1["pacote"]["farois"] == 4
    for s in (s1, s2):
        assert set(s["memoria"]) >= {"rss_mb", "pico_mb", "limite_mb", "cache_mb", "cache_farois"}
    i2, i1 = m2["pacotes"].Indice(d2), m1["pacotes"].Indice(d1)
    for rid in p["relatorios"]:
        assert i2.farol(rid) == i1.farol(rid), f"{rid}: o farol guardado difere entre os formatos"
        assert i2.farol(rid) is not None
        h2, h1 = cli2.get(f"/farol/{rid}"), cli1.get(f"/farol/{rid}")
        assert h2.status_code == h1.status_code == 200
        c2 = _cartoes(h2.text)
        assert c2 and c2 == _cartoes(h1.text), f"{rid}: cartões diferem entre os formatos"
        txt = json.dumps(p["relatorios"][rid], ensure_ascii=False)
        assert all(c.split(" | ")[-1] in txt for c in c2), f"{rid}: cartão da tela fora do pacote"
    # os anexos: do disco nos dois formatos
    for cli in (cli1, cli2):
        x = cli.get("/farol/pv_pedidos/parcial.png?q=acum")
        assert x.status_code == 200 and x.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert i2.csvs("pv_pedidos") == i1.csvs("pv_pedidos") == p["relatorios"]["pv_pedidos"]["csvs_protheus"]
    # formato 2: o sha do índice é o sha dos bytes que o robô mandou (X-BAP-SHA256)
    ind = _indice(d2)
    for rid, f in p["relatorios"].items():
        corpo = ba._json_farol_web(ba._cortar_farol_web(rid, f))
        assert ind["farois"][rid]["sha256"] == hashlib.sha256(corpo).hexdigest()


def test_ADR0003_anexo_acima_do_teto_sai_so_ele_e_o_farol_chega(web_mod, monkeypatch):
    """§10.8.7: parcial acima de MAX_PNG_B64 e CSVs acima de MAX_CSVS_TOTAL saem no robô, com aviso;
    o farol chega (nada no `manter`), nos dois formatos."""
    p = _pacote(_agora())
    ped = p["relatorios"]["pv_pedidos"]
    ped["parciais"]["d1"]["png"] = _png(ba.MAX_PNG_B64)                          # base64 > 3 MB
    ped["csvs_protheus"] = [{"nome": f"261126_{i}_LJ01_BAPReversaLoja.csv", "conteudo": "a" * 190_000}
                            for i in range(1, 10)]                              # soma > 1,5 MB
    assert len(ped["parciais"]["d1"]["png"]) > ba.MAX_PNG_B64
    for nome, enviar in (("f2", lambda q, lg: ba.enviar_pacote(q, url=BASE, token=TOKEN, log=lg)),
                         ("f1", lambda q, lg: ba.enviar_pacote_web(ba._cortar_pacote_web(q), url=BASE,
                                                                   token=TOKEN, log=lg))):
        cli, dados, m = _web(web_mod, nome, monkeypatch)
        log = []
        assert enviar(copy.deepcopy(p), log.append) is True, nome
        assert not any("manter" in x and "0 no manter" not in x for x in log), nome
        e = _indice(dados)["farois"]["pv_pedidos"]
        assert e["herdado_de"] is None
        assert sorted((e.get("anexos") or {}).get("parciais") or {}) == ["acum", "hoje"], nome
        assert "csvs" not in (e.get("anexos") or {}), nome
        f = m["pacotes"].Indice(dados).farol("pv_pedidos")
        assert ba.AVISO_PARCIAIS_FORA in f["avisos"] and ba.AVISO_CSVS_FORA in f["avisos"], nome
        assert f.get("tabelas"), nome                                           # as abas ficam
    assert len(p["relatorios"]["pv_pedidos"]["csvs_protheus"]) == 9             # a entrada não mudou


def test_ADR0003_web_recusa_o_anexo_acima_do_teto_que_chegar_inteiro(web_mod, monkeypatch):
    """O lado da web: se o anexo grande chegasse (robô sem o corte), o farol é recusado (422)."""
    import gzip
    cli, dados, m = _web(web_mod, "w", monkeypatch)
    p = _pacote(_agora())
    lote = m["pacotes"].nome_arquivo(p["gerado_em"])
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "Content-Encoding": "gzip"}
    for estraga in (lambda f: f["parciais"]["acum"].update(png=_png(ba.MAX_PNG_B64)),
                    lambda f: f.update(csvs_protheus=[{"nome": f"261126_{i}_LJ01_BAPReversaLoja.csv",
                                                       "conteudo": "a" * 190_000} for i in range(1, 10)])):
        f = copy.deepcopy(p["relatorios"]["pv_pedidos"])
        estraga(f)
        corpo = ba._json_farol_web(f)
        r = cli.post(f"/api/pacote/{lote}/farol/pv_pedidos", content=gzip.compress(corpo),
                     headers={**h, "X-BAP-SHA256": hashlib.sha256(corpo).hexdigest()})
        assert r.status_code == 422 and r.json()["erro"] == "esquema inválido"
        q = copy.deepcopy(p)
        q["relatorios"]["pv_pedidos"] = f
        assert cli.post("/api/pacote", json=q, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 422


def test_ADR0003_farol_recusado_fica_herdado_com_a_data_dele_e_o_selo_so_passadas_26h(web_mod, monkeypatch):
    """ADR 0003, §4.4 (A, decidida) e tela-bc3 §4.1: o farol que a web recusou vai no `manter`, fica com
    a data dele (sem selo até 26 h), ganha o selo "Desatualizado" passadas 26 h e sai na rodada seguinte."""
    cli, dados, m = _web(web_mod, "h", monkeypatch)
    lote1 = _pacote(_agora(25))
    assert ba.enviar_pacote(copy.deepcopy(lote1), url=BASE, token=TOKEN, log=lambda x: None)
    rec1 = _indice(dados)["farois"]["vc_visitas"]["recebido_em"]
    threading.Event().wait(1.1)          # o recebido_em é por segundo (o time.sleep do robô está desligado)
    lote2 = _pacote(_agora())
    lote2["relatorios"]["vc_visitas"]["parciais"]["zz"] = {"rotulo": "x", "png": _png()}  # a web recusa (422)
    log = []
    assert ba.enviar_pacote(copy.deepcopy(lote2), url=BASE, token=TOKEN, log=log.append) is True
    assert any("vc_visitas recusado (422)" in x for x in log)
    ind = _indice(dados)
    e = ind["farois"]["vc_visitas"]
    assert e["herdado_de"] == m["pacotes"].nome_arquivo(lote1["gerado_em"])
    assert e["gerado_em"] == lote1["gerado_em"] and e["recebido_em"] == rec1
    assert ind["farois"]["pv_pedidos"]["herdado_de"] is None
    html = cli.get("/farol/vc_visitas").text
    data1 = datetime.fromisoformat(lote1["gerado_em"]).strftime("%d/%m/%Y %H:%M")
    assert data1 in html and "Desatualizado" not in html                          # a data dele, sem selo
    assert "/farol/vc_visitas" in cli.get("/").text
    # RN-GER-012 × §10.8.6: a edição aplicada entre as rodadas segue "Aguardando o PC" no farol herdado
    ed = m["edicoes"]
    meio = datetime.fromisoformat(rec1).strftime("%Y-%m-%d %H:%M:%S")       # aplicada depois da rodada 1
    assert meio < datetime.fromisoformat(ind["farois"]["pv_pedidos"]["recebido_em"]).strftime("%Y-%m-%d %H:%M:%S")
    sit = {"status": "aplicada", "em": meio}
    idx = m["pacotes"].Indice(dados)
    assert ed.marca(sit, idx.recebido_em("vc_visitas")) == "pendente"
    assert ed.marca(sit, idx.recebido_em("pv_pedidos")) == ""                    # o reenviado já traz
    # passadas 26 h do farol herdado: o selo aparece só nele
    real = m["cobranca"].agora
    monkeypatch.setattr(m["cobranca"], "agora", lambda: real() + timedelta(hours=2))
    assert "Desatualizado" in cli.get("/farol/vc_visitas").text
    assert "Desatualizado" not in cli.get("/farol/pv_pedidos").text
    # a rodada seguinte, 2 h depois, falha de novo: o herdado tem 27 h e sai
    reald = m["pacotes"].datetime

    class _Depois(reald):
        @classmethod
        def now(cls, tz=None):
            return reald.now(tz) + timedelta(hours=2)
    monkeypatch.setattr(m["pacotes"], "datetime", _Depois)
    lote3 = copy.deepcopy(lote2)
    lote3["gerado_em"] = (datetime.now(MANAUS) + timedelta(hours=2)).replace(microsecond=0).isoformat()
    assert ba.enviar_pacote(lote3, url=BASE, token=TOKEN, log=lambda x: None) is True
    assert "vc_visitas" not in _indice(dados)["farois"]
    assert "/farol/vc_visitas" not in cli.get("/").text


def test_RN_POS_003_diario_da_cobranca_leva_o_sha_do_farol_no_formato2(web_mod, monkeypatch):
    """§10.8.6: o `pacote_sha` do diário é o sha256 do farol pl_inadimplencia no índice, que é o dos
    bytes que o robô mandou; o robô lê o registro pela /api/cobranca."""
    cli, dados, m = _web(web_mod, "c", monkeypatch)
    p = _pacote(_agora())
    assert ba.enviar_pacote(copy.deepcopy(p), url=BASE, token=TOKEN, log=lambda x: None)
    html = cli.get("/farol/pl_inadimplencia?aba=cobrar").text
    sha = re.search(r'data-sha="([0-9a-f]{64})"', html).group(1)
    cod = re.search(r'data-cod="([^"]+)"', html).group(1)
    cs = re.search(r'data-csrf="([^"]+)"', html).group(1)
    corpo = ba._json_farol_web(ba._cortar_farol_web("pl_inadimplencia", p["relatorios"]["pl_inadimplencia"]))
    assert sha == _indice(dados)["farois"]["pl_inadimplencia"]["sha256"] == hashlib.sha256(corpo).hexdigest()
    r = cli.post("/farol/pl_inadimplencia/cobranca",
                 data={"csrf": cs, "cliente": cod, "acao": "PULADO", "pacote_sha": sha, "telefone": ""})
    assert r.status_code == 200 and r.json()["ok"]
    api = cli.get("/api/cobranca?desde=0", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert [x["pacote_sha"] for x in api["linhas"]] == [sha]
