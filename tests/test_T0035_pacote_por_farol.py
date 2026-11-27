"""T-0035 (ADR 0003, contrato 10.8): o robo manda farol a farol.

Trazido do modulo-robo (R-20261126-181930) e revisto pelo testes: o corte
do Pedidos passava vazio (`if sa:`); os nomes citam a ADR 0003, porque o
transporte nao e regra de negocio (nao ha RN para ele).

Servidor de teste local que segue o 10.8 (so o necessario ao robo). Nao toca
a rede da empresa; sem dado pessoal (farois sinteticos)."""
import gzip
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import bap_automation as ba

GERADO = "2026-11-26T08:30:00-04:00"


def _pacote(extra=None):
    rel = {"titulo": "x", "avisos": [], "cartoes": []}
    p = {"versao_contrato": 1, "gerado_em": GERADO, "ano": 2026, "mes": 11,
         "relatorios": {"vc_painel": dict(rel), "pv_pedidos": dict(rel),
                        "vc_visitas": dict(rel)}}
    p["relatorios"].update(extra or {})
    return p


class Web:
    def __init__(self, formatos=(1, 2), recusa=None, faltam_uma_vez=None):
        self.formatos, self.recusa = formatos, recusa or {}
        self.recebidos, self.fechar, self.rotas = {}, [], []
        self.faltam = faltam_uma_vez
        web = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _r(self, cod, obj):
                b = json.dumps(obj).encode()
                self.send_response(cod)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                web.rotas.append(("GET", self.path))
                if self.path == "/saude":
                    corpo = {"status": "ok"}
                    if web.formatos:
                        corpo["pacote"] = {"formatos": list(web.formatos)}
                    return self._r(200, corpo)
                self._r(404, {})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                dados = self.rfile.read(n)
                web.rotas.append(("POST", self.path))
                partes = self.path.strip("/").split("/")
                if partes[:2] != ["api", "pacote"]:
                    return self._r(404, {})
                if len(partes) == 2:
                    return self._r(200, {"ok": True})
                if partes[3] == "farol":
                    rid = partes[4]
                    if rid in web.recusa:
                        return self._r(web.recusa[rid], {"detalhes": ["x"]})
                    if self.headers.get("Content-Encoding") == "gzip":
                        dados = gzip.decompress(dados)
                    if hashlib.sha256(dados).hexdigest() != self.headers.get(
                            "X-BAP-SHA256"):
                        return self._r(422, {"erro": "sha256"})
                    web.recebidos[rid] = (hashlib.sha256(dados).hexdigest(),
                                          json.loads(dados))
                    return self._r(200, {"ok": True})
                if partes[3] == "fechar":
                    c = json.loads(dados)
                    web.fechar.append(c)
                    if web.faltam:
                        rid, web.faltam = web.faltam, None
                        web.recebidos.pop(rid, None)
                        return self._r(409, {"erro": "faltam",
                                             "farois": [rid]})
                    ruins = [r for r, s in c["farois"].items()
                             if web.recebidos.get(r, ("",))[0] != s]
                    if ruins:
                        return self._r(409, {"erro": "faltam",
                                             "farois": ruins})
                    return self._r(200, {"ok": True})
                self._r(404, {})
        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def fim(self):
        self.srv.shutdown()


@pytest.fixture
def web(monkeypatch):
    criados = []

    def novo(**kw):
        w = Web(**kw)
        criados.append(w)
        monkeypatch.setattr(ba, "_base_web", lambda u: w.url)
        monkeypatch.setattr(ba.time, "sleep", lambda s: None)
        return w
    yield novo
    for w in criados:
        w.fim()


def _env(w):
    return {"url": "https://x.exemplo", "token": "tk", "log": lambda m: None}


def test_ADR0003_formato2_manda_farol_a_farol_e_fecha(web):
    w = web()
    p = _pacote()
    assert ba.enviar_pacote(p, **_env(w)) is True
    assert set(w.recebidos) == set(p["relatorios"])
    fe = w.fechar[0]
    assert fe["gerado_em"] == GERADO and "manter" not in fe
    assert fe["farois"] == {r: s for r, (s, _) in w.recebidos.items()}
    assert ("POST", "/api/pacote") not in w.rotas
    assert w.recebidos["vc_painel"][1] == p["relatorios"]["vc_painel"]


def test_ADR0003_web_antiga_cai_no_formato1(web):
    w = web(formatos=())
    assert ba.enviar_pacote(_pacote(), **_env(w)) is True
    assert ("POST", "/api/pacote") in w.rotas
    assert not [r for r in w.rotas if "/farol/" in r[1]]


def test_ADR0003_saude_fora_cai_no_formato1(web, monkeypatch):
    w = web()
    monkeypatch.setattr(ba, "_formatos_web", lambda b, r: [1])
    assert ba.enviar_pacote(_pacote(), **_env(w)) is True
    assert ("POST", "/api/pacote") in w.rotas


def test_ADR0003_farol_recusado_vai_no_manter_e_nao_derruba_outros(web):
    w = web(recusa={"pv_pedidos": 413})
    assert ba.enviar_pacote(_pacote(), **_env(w)) is True
    assert w.fechar[0]["manter"] == ["pv_pedidos"]
    assert "pv_pedidos" not in w.fechar[0]["farois"]
    assert {"vc_painel", "vc_visitas"} <= set(w.fechar[0]["farois"])


def test_ADR0003_404_deixa_o_farol_fora_sem_manter(web):
    w = web(recusa={"vc_visitas": 404})
    assert ba.enviar_pacote(_pacote(), **_env(w)) is True
    assert "manter" not in w.fechar[0]
    assert "vc_visitas" not in w.fechar[0]["farois"]


def test_ADR0003_fechar_409_reenvia_os_faltantes(web):
    w = web(faltam_uma_vez="vc_painel")
    assert ba.enviar_pacote(_pacote(), **_env(w)) is True
    assert len(w.fechar) == 2 and "vc_painel" in w.fechar[1]["farois"]


def test_ADR0003_nenhum_farol_aceito_nao_fecha(web):
    w = web(recusa={r: 422 for r in ("vc_painel", "pv_pedidos",
                                     "vc_visitas")})
    assert ba.enviar_pacote(_pacote(), **_env(w)) is False
    assert not w.fechar


def test_ADR0003_lote_e_o_gerado_em_de_manaus():
    assert ba._lote_web(GERADO) == "20261126T083000"


def _grande(rid):
    linhas = [[f"v{i}" * 20, "EM ABERTO" if i % 2 else "FATURADO"]
              for i in range(60000)]
    sa = {"titulo": "Pedidos", "colunas": [{"nome": "X"},
                                           {"nome": "SITUACAO_PEDIDO"}],
          "linhas": linhas, "tons": [""] * len(linhas)}
    return {"titulo": "x", "avisos": [], "parciais": {"acum": "AAA"},
            "tabelas": [{"titulo": ba.TITULO_SOLICITACAO_WEB,
                         "subabas": [sa]}]}


def _mb(f):
    return len(ba._json_farol_web({k: v for k, v in f.items()
                                   if k not in ("parciais", "csvs_protheus")})) / (1024 * 1024)


def test_ADR0003_corte_1_do_pedidos_basta_fica_so_em_aberto_e_preserva_anexos():
    """(testes) Antes o teto de 1 MB tirava a aba inteira e o `if sa:` passava
    vazio. Agora o teto fica entre o farol só com EM ABERTO e o farol inteiro:
    o corte 1 tem de bastar, e a aba fica."""
    f = _grande("pv_pedidos")
    antes = json.dumps(f)
    so_aberto = json.loads(antes)
    sa0 = so_aberto["tabelas"][0]["subabas"][0]
    sa0["linhas"] = [l for l in sa0["linhas"] if l[1] == "EM ABERTO"]
    sa0["tons"] = [""] * len(sa0["linhas"])
    teto = (_mb(so_aberto) + _mb(f)) / 2
    assert _mb(so_aberto) < teto < _mb(f)
    out = ba._cortar_farol_web("pv_pedidos", f, teto_mb=teto)
    assert json.dumps(f) == antes                 # funcao pura
    assert out["parciais"] == {"acum": "AAA"}     # anexo nao e tocado
    assert out.get("tabelas"), "o corte 1 bastava: a aba nao pode sair"
    sa = out["tabelas"][0]["subabas"][0]
    assert len(sa["linhas"]) == 30000 and len(sa["tons"]) == 30000
    assert all(l[1] == "EM ABERTO" for l in sa["linhas"])
    assert ba.AVISO_SOLICITACAO_ABERTO in out["avisos"]
    assert not any(a.startswith("Abas fora") for a in out["avisos"])
    assert _mb(out) <= teto


def test_ADR0003_corte_do_pedidos_que_nao_basta_tira_a_aba_com_aviso():
    f = _grande("pv_pedidos")
    out = ba._cortar_farol_web("pv_pedidos", f, teto_mb=1)
    assert "tabelas" not in out and out["parciais"] == {"acum": "AAA"}
    assert ba.AVISO_ABAS_FORA.format(lista=ba.TITULO_SOLICITACAO_WEB) in out["avisos"]
    assert ba.AVISO_SOLICITACAO_ABERTO in out["avisos"]       # o corte 1 veio antes


def test_ADR0003_abaixo_do_teto_devolve_o_mesmo_farol():
    f = {"titulo": "x", "avisos": []}
    assert ba._cortar_farol_web("vc_painel", f) is f


def test_ADR0003_farol_fora_da_lista_perde_todas_as_tabelas():
    f = {"titulo": "x", "avisos": [],
         "tabelas": [{"titulo": "Grande", "linhas": ["y" * 100] * 50000}]}
    out = ba._cortar_farol_web("pl_inadimplencia", f, teto_mb=1)
    assert "tabelas" not in out and out["avisos"][0].startswith("Abas fora")


def test_ADR0003_montar_pacote_sem_cortar_nao_aplica_o_teto_global(
        monkeypatch):
    chamado = []
    monkeypatch.setattr(ba, "_cortar_pacote_web",
                        lambda p, *a: chamado.append(1) or p)
    ba.montar_pacote_web({}, 2026, 11, cortar=False)
    assert not chamado
    ba.montar_pacote_web({}, 2026, 11)
    assert chamado
