"""T-0013 (passo 4f do robô): pacote da web.

Critérios:
1. o pacote só tem tipos JSON; gerado_em ISO com offset -04:00 (Manaus);
2. nenhum callable, .pkl ou caminho sobra no pacote;
   escopo (R-20261120-120939): vc_painel, abas resultado e produtividade,
   sem a aba "du" e sem o "diretor"; (T-0017, contrato §10.1) mais os faróis
   de bap_automation.FAROIS_WEB, só na forma "farol" (sem tabelas/linhas);
   sem FAROIS_WEB (main antes da T-0017) o escopo é só vc_painel;
3. sem URL/token o envio pula (False, aviso no log, nenhuma requisição);
4. envio com Bearer, corpo = pacote, timeout 30, só https:443, 3 tentativas;
5. o token nunca aparece no log.

Dados 100% fictícios. Nada de RELATORIOS/ nem SISTEMA BAP/: o montar real e
o cofre são trocados por monkeypatch. Token fictício.
"""
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
requests = pytest.importorskip("requests")
ba = pytest.importorskip("bap_automation")

TOKEN = "tok-FICTICIO-1234567890abcdef"
URL = "https://bap-web-ficticio.example.com"
MANAUS = timezone(timedelta(hours=-4))
AGORA = datetime(2026, 11, 20, 9, 30, tzinfo=MANAUS)


# ----------------------------------------------------------------- utilidades
class _KeyringNulo:
    """Cofre falso: nunca tem segredo."""
    chamadas = []

    @classmethod
    def get_password(cls, servico, usuario):
        cls.chamadas.append((servico, usuario))
        return None


@pytest.fixture(autouse=True)
def _isolar(monkeypatch):
    """Sem env real, cofre que devolve None, sem espera entre tentativas."""
    monkeypatch.delenv("BAP_WEB_URL", raising=False)
    monkeypatch.delenv("BAP_WEB_TOKEN", raising=False)
    monkeypatch.setattr(ba, "keyring", _KeyringNulo)
    monkeypatch.setattr(ba.time, "sleep", lambda *_a, **_k: None)


class _Resp:
    def __init__(self, status):
        self.status_code = status


class _ServidorFalso:
    """Substitui requests.post e guarda cada requisição."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def __call__(self, url, data=None, headers=None, timeout=None, **kw):
        self.pedidos.append({"url": url, "data": data, "headers": headers,
                             "timeout": timeout, "kw": kw})
        r = self.respostas.pop(0) if self.respostas else 500
        if isinstance(r, BaseException):
            raise r
        return _Resp(r)


def _proibido(*_a, **_k):
    raise AssertionError("nenhuma requisição deveria sair")


def _so_tipos_json(obj, caminho="$"):
    """Percorre recursivamente; só dict(str), list, str, int, float, bool, None."""
    if obj is None or isinstance(obj, (bool, str)):
        return
    if isinstance(obj, (int, float)):
        assert type(obj) in (int, float), f"{caminho}: {type(obj)}"
        if isinstance(obj, float):
            assert math.isfinite(obj), f"{caminho}: float não finito"
        return
    if isinstance(obj, dict):
        assert type(obj) is dict, f"{caminho}: {type(obj)}"
        for k, v in obj.items():
            assert type(k) is str, f"{caminho}: chave {k!r} não é str"
            _so_tipos_json(v, f"{caminho}.{k}")
        return
    if isinstance(obj, list):
        assert type(obj) is list, f"{caminho}: {type(obj)}"
        for i, v in enumerate(obj):
            _so_tipos_json(v, f"{caminho}[{i}]")
        return
    raise AssertionError(f"{caminho}: tipo não JSON {type(obj)}")


def _todas_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _todas_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _todas_strings(v)


def _valores_estranhos():
    """Valores que o montar pode devolver e que precisam virar JSON."""
    df = pd.DataFrame({
        "FILIAL": ["AM", "RR", "PA"],
        "FATURADO": [np.float64(1500.5), np.float64(float("nan")), 300.0],
        "QTD": np.array([1, 2, 3], dtype=np.int64),
        "DATA": [pd.Timestamp("2026-11-03"), pd.NaT,
                 pd.Timestamp("2026-11-05")],
    })
    return {
        "tabela": df,
        "serie": pd.Series([1, 2, np.int32(3)]),
        "total": Decimal("1234.56"),
        "total_nan": Decimal("NaN"),
        "nan": float("nan"),
        "inf": float("inf"),
        "data_base": date(2026, 11, 19),
        "momento": datetime(2026, 11, 20, 8, 0),
        "np_int": np.int64(7),
        "np_float": np.float32(2.5),
        "np_bool": np.bool_(True),
        "np_arr": np.array([[1, 2], [3, 4]]),
        "tupla": (1, "a"),
        "conjunto": {"b", "a"},
        "cores_celulas": {0: {1: "#FF0000"}, 2: {3: "#00FF00"}},
        "por_numero": {1: "um", 2.5: "dois e meio", None: "nada"},
        # o que NÃO pode ir para a web
        "detalhe_pedido": lambda linha: linha,
        "kpis_de": len,
        "_interno": {"x": 1},
        "funcao": print,
        "cache": "C:/BAP/cache_relatorio.pkl",
        "cache2": "cache.PICKLE",
        "pasta": Path("/tmp/pasta_ficticia"),
        "bruto": b"\x00\x01",
        "lista_mista": [1, print, Path("x"), "base.pkl", None],
    }


DIRETOR = {"segredo_do_diretor": "NAO-VAI-DIRETOR", "cartoes": [1, 2, 3]}


def _dados_rrm():
    """Fictício no formato de painel_rrm.calcular: as três visões juntas."""
    return {
        "comp": "2026-11", "ano": 2026, "mes": 11,
        "res": {"cartoes": [{"rotulo": "Faturamento", "real": 100.0}],
                "estranhos": _valores_estranhos()},
        "prod": {"cartoes": [{"rotulo": "Pedidos por vendedor",
                              "real": 3.5}]},
        "du": {"cartoes": [{"rotulo": "NAO-VAI-DU", "real": 1.0}]},
        "sub": {"res": "sub resultado", "prod": "sub produtividade",
                "du": "NAO-VAI-SUB-DU"},
        "como_ler": "Número grande = projeção do mês (fictício).",
        "dados_ate": "2026-11-19",
        "avisos": ["aviso fictício dos dados"],
        "diretor": DIRETOR,                  # se algum dia vier, não vai
    }


def _painel(vis, titulo, dados=None, **extra):
    return {"titulo": titulo, "kpis": [],
            "diretor": DIRETOR if vis == "res" else None,
            "kpis_export": [{"rotulo": f"kpi {vis}", "valor": 1,
                             "acao": print}],
            "painel": {"blocos": [{"tipo": "rrm",
                                   "dados": dados or _dados_rrm(),
                                   "visao": vis, "row": 0, "col": 0,
                                   "colspan": 3}],
                       "altura_min": 720},
            **extra}


def _vc_painel_ficticio(visoes=("res", "prod", "du"), outras=True):
    titulos = {"res": "Painel · resultado", "prod": "Painel · produtividade",
               "du": "Painel · por dia útil"}
    paineis = [_painel(v, titulos[v]) for v in visoes]
    if outras:
        paineis += [
            {"titulo": "Vendas por estado", "kpis": [],
             "painel": {"blocos": [{"tipo": "tabela", "dados": {"x": 1}}],
                        "altura_min": 500}},
            {"titulo": "Painel · resultado (cópia sem RRM)", "kpis": [],
             "painel": {"blocos": [{"tipo": "grafico", "visao": "res"}]}},
            "nao_e_dict",
        ]
    return {"titulo": "Visão comercial (fictício)", "paineis": paineis,
            "tabelas": [{"nome": "NAO-VAI-TABELA"}],
            "detalhe_pedido": print,
            "cache": "base.pkl"}


# Lista branca fixa (R-20261124-175008-alexandre): os 4 faróis do PC que podem
# ir para a web. Qualquer outro id em FAROIS_WEB é defeito.
LISTA_FAROIS_WEB = frozenset({"pv_pedidos", "vc_visitas", "pl_entregas",
                              "pl_inadimplencia",
                              # T-0024 (lote 2)
                              "pv_indicadores", "vc_base", "vc_planner",
                              "pl_giro", "pl_frw"})
# relatório montado no PC que nunca vai para a web (fora da lista branca)
FORA_DA_LISTA = "pl_garantias"


def _farois_web():
    """Faróis que o robô leva ao pacote (T-0017), na ordem; vazio antes dela."""
    return tuple(getattr(ba, "FAROIS_WEB", ()))


def _chaves_aninhadas(obj):
    """Todas as chaves de dict, em qualquer nível."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _chaves_aninhadas(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _chaves_aninhadas(v)


def _escopo_esperado(resultados):
    """vc_painel ∪ os faróis de FAROIS_WEB que vieram montados."""
    return {"vc_painel"} | (set(_farois_web()) & set(resultados))


def _resultados_ficticios():
    return {"vc_painel": _vc_painel_ficticio(),
            "pl_inadimplencia": {"linhas": [{"cliente": "NAO-VAI-INAD"}]},
            FORA_DA_LISTA: {"titulo": "NAO-VAI-FORA-DA-LISTA",
                            "kpis": [{"rotulo": "NAO-VAI-FORA-DA-LISTA",
                                      "valor": 1}]}}


# ------------------------------------------------------- critério 1: só JSON
def test_T0013_criterio1_pacote_so_tem_tipos_json():
    pacote = ba.montar_pacote_web(_resultados_ficticios(), 2026, 11, AGORA)
    json.dumps(pacote, allow_nan=False)          # não levanta
    _so_tipos_json(pacote)
    assert set(pacote) == {"versao_contrato", "gerado_em", "ano", "mes",
                           "relatorios"}
    assert pacote["ano"] == 2026 and pacote["mes"] == 11
    assert isinstance(pacote["versao_contrato"], int)
    assert set(pacote["relatorios"]["vc_painel"]["abas"]) == {
        "resultado", "produtividade"}


def test_T0013_criterio1_para_json_conversoes_de_valor():
    rel = ba._para_json(_valores_estranhos())
    json.dumps(rel, allow_nan=False)
    _so_tipos_json(rel)
    assert rel["total"] == pytest.approx(1234.56)
    assert rel["total_nan"] is None
    assert rel["nan"] is None and rel["inf"] is None
    assert rel["data_base"] == "2026-11-19"
    assert rel["momento"].startswith("2026-11-20T08:00")
    assert rel["np_int"] == 7 and type(rel["np_int"]) is int
    assert rel["np_float"] == pytest.approx(2.5)
    assert rel["np_bool"] is True
    assert rel["np_arr"] == [[1, 2], [3, 4]]
    assert rel["tupla"] == [1, "a"]
    assert rel["conjunto"] == ["a", "b"]
    assert rel["serie"] == [1, 2, 3]
    linhas = rel["tabela"]
    assert [l["FILIAL"] for l in linhas] == ["AM", "RR", "PA"]
    assert linhas[0]["FATURADO"] == pytest.approx(1500.5)
    assert linhas[1]["FATURADO"] is None           # NaN -> null
    assert linhas[1]["DATA"] is None               # NaT -> null
    assert linhas[0]["DATA"].startswith("2026-11-03")
    assert linhas[2]["QTD"] == 3


def test_T0013_criterio1_valores_estranhos_dentro_da_aba_viram_json():
    aba = ba.montar_pacote_web(_resultados_ficticios(), 2026, 11, AGORA)[
        "relatorios"]["vc_painel"]["abas"]["resultado"]
    est = aba["painel"]["blocos"][0]["dados"]["res"]["estranhos"]
    assert est["cores_celulas"] == {"0": {"1": "#FF0000"},
                                    "2": {"3": "#00FF00"}}
    assert est["tabela"][1]["FATURADO"] is None
    assert est["total"] == pytest.approx(1234.56)


def test_T0013_criterio1_chaves_int_viram_str_em_cores_celulas():
    rel = ba._para_json(_valores_estranhos())
    assert rel["cores_celulas"] == {"0": {"1": "#FF0000"},
                                    "2": {"3": "#00FF00"}}
    assert set(rel["por_numero"]) == {"1", "2.5", "None"}


def test_T0013_criterio1_gerado_em_iso_com_offset_manaus():
    pacote = ba.montar_pacote_web({}, 2026, 11, AGORA)
    assert pacote["gerado_em"] == "2026-11-20T09:30:00-04:00"
    # sem agora: usa o relógio de Manaus
    g = ba.montar_pacote_web({}, 2026, 11)["gerado_em"]
    assert datetime.fromisoformat(g).utcoffset() == timedelta(hours=-4)
    assert g.endswith("-04:00")
    # agora ingênuo: recebe -04:00
    g2 = ba.montar_pacote_web({}, 2026, 11,
                              datetime(2026, 12, 1, 0, 0))["gerado_em"]
    assert g2 == "2026-12-01T00:00:00-04:00"


def test_T0013_criterio1_montar_e_puro_nao_altera_entrada():
    res = _resultados_ficticios()
    antes = len(res["vc_painel"]["paineis"])
    d = res["vc_painel"]["paineis"][0]["painel"]["blocos"][0]["dados"]
    chaves = set(d)
    ba.montar_pacote_web(res, 2026, 11, AGORA)
    assert len(res["vc_painel"]["paineis"]) == antes
    assert set(d) == chaves and "du" in d and "diretor" in d
    assert 0 in d["res"]["estranhos"]["cores_celulas"]


# ------------------------------------- critério 2: sem callable/.pkl/caminho
def test_T0013_criterio2_para_json_sem_callable_pkl_nem_caminho():
    rel = ba._para_json(_valores_estranhos())
    for chave in ("detalhe_pedido", "kpis_de", "_interno", "funcao", "cache",
                  "cache2", "pasta", "bruto"):
        assert chave not in rel, chave
    assert rel["lista_mista"] == [1, None]


def test_T0013_criterio2_pacote_sem_callable_pkl_nem_caminho():
    pacote = ba.montar_pacote_web(_resultados_ficticios(), 2026, 11, AGORA)
    for s in _todas_strings(pacote):
        assert not s.lower().endswith((".pkl", ".pickle")), s
        assert "pasta_ficticia" not in s, s
        assert not s.startswith("_"), s

    def _sem_callable(o):
        assert not callable(o) and not isinstance(o, Path)
        if isinstance(o, dict):
            for v in o.values():
                _sem_callable(v)
        elif isinstance(o, list):
            for v in o:
                _sem_callable(v)
    _sem_callable(pacote)
    kpi = pacote["relatorios"]["vc_painel"]["abas"]["resultado"][
        "kpis_export"]
    assert kpi == [{"rotulo": "kpi res", "valor": 1}]   # "acao" saiu


# ------------------------- escopo novo (R-20261120-120939): só 2 abas do Painel
# (T-0017) + os faróis de FAROIS_WEB, só na forma "farol": as linhas cruas
# (cliente) nunca entram.
def test_T0013_escopo_vc_painel_e_farois_web_sem_linhas_cruas():
    pacote = ba.montar_pacote_web(_resultados_ficticios(), 2026, 11, AGORA)
    assert set(_farois_web()) <= LISTA_FAROIS_WEB      # trava do escopo
    assert set(pacote["relatorios"]) == _escopo_esperado(
        _resultados_ficticios())
    assert FORA_DA_LISTA not in pacote["relatorios"]
    for rid in set(_farois_web()) & set(pacote["relatorios"]):
        farol = pacote["relatorios"][rid]
        assert farol.get("forma") == "farol"
        # "linhas" só no 1º nível: o bloco "insights" usa "linhas" (frases)
        assert "linhas" not in farol
        assert "tabelas" not in set(_chaves_aninhadas(farol))
    texto = json.dumps(pacote, ensure_ascii=False)
    assert "NAO-VAI-FORA-DA-LISTA" not in texto
    assert "NAO-VAI-INAD" not in texto
    assert "NAO-VAI-TABELA" not in texto            # tabelas do vc_painel
    vc = pacote["relatorios"]["vc_painel"]
    assert set(vc) == {"titulo", "abas"}            # sem aviso: as 2 vieram
    assert vc["titulo"] == "Visão comercial (fictício)"


def test_T0013_escopo_selecionar_abas_resultado_e_produtividade():
    sel = ba.selecionar_abas_web(_vc_painel_ficticio())
    assert set(sel["abas"]) == {"resultado", "produtividade"}
    assert "avisos" not in sel
    for chave, vis, tit in (("resultado", "res", "Painel · resultado"),
                            ("produtividade", "prod",
                             "Painel · produtividade")):
        aba = sel["abas"][chave]
        # "recortes" (T-0014) é opcional aqui; quem confere é o test_T0014
        assert set(aba) - {"recortes"} == {"titulo", "kpis_export", "painel",
                                           "altura_min"}
        assert aba["titulo"] == tit
        assert aba["altura_min"] == 720
        assert aba["painel"]["altura_min"] == 720
        assert len(aba["painel"]["blocos"]) == 1
        b = aba["painel"]["blocos"][0]
        assert b["tipo"] == "rrm" and b["visao"] == vis
        assert (b["row"], b["col"], b["colspan"]) == (0, 0, 3)
        assert aba["kpis_export"][0]["rotulo"] == f"kpi {vis}"


def test_T0013_escopo_aba_du_e_abas_nao_rrm_ficam_fora():
    pacote = ba.montar_pacote_web(_resultados_ficticios(), 2026, 11, AGORA)
    texto = json.dumps(pacote, ensure_ascii=False)
    assert "por dia útil" not in texto
    assert "NAO-VAI-DU" not in texto and "NAO-VAI-SUB-DU" not in texto
    assert "Vendas por estado" not in texto
    assert "cópia sem RRM" not in texto
    for aba in pacote["relatorios"]["vc_painel"]["abas"].values():
        assert aba["painel"]["blocos"][0]["visao"] in ("res", "prod")


def test_T0013_escopo_dados_so_da_visao_da_aba_sem_diretor():
    sel = ba.selecionar_abas_web(_vc_painel_ficticio())
    base = {"comp", "ano", "mes", "como_ler", "dados_ate", "avisos", "sub"}
    for chave, vis, alheia in (("resultado", "res", "prod"),
                               ("produtividade", "prod", "res")):
        d = sel["abas"][chave]["painel"]["blocos"][0]["dados"]
        assert set(d) == base | {vis}
        assert alheia not in d and "du" not in d and "diretor" not in d
        assert d["sub"] == {vis: f"sub {'resultado' if vis == 'res' else 'produtividade'}"}
        assert d["como_ler"].startswith("Número grande")
        assert d["comp"] == "2026-11" and d["dados_ate"] == "2026-11-19"
    # o "diretor" do painel (p["diretor"]) também não vai
    pacote = ba.montar_pacote_web(_resultados_ficticios(), 2026, 11, AGORA)
    texto = json.dumps(pacote, ensure_ascii=False)
    assert "NAO-VAI-DIRETOR" not in texto and "diretor" not in texto


@pytest.mark.parametrize("visoes,faltando", [
    (("res", "du"), ["produtividade"]),
    (("prod", "du"), ["resultado"]),
    (("du",), ["resultado", "produtividade"]),
    ((), ["resultado", "produtividade"]),
])
def test_T0013_escopo_aviso_quando_falta_uma_das_abas(visoes, faltando):
    sel = ba.selecionar_abas_web(_vc_painel_ficticio(visoes))
    assert set(sel["abas"]) == {"resultado", "produtividade"} - set(faltando)
    assert len(sel["avisos"]) == len(faltando)
    for chave, aviso in zip(faltando, sel["avisos"]):
        assert chave in aviso
    pacote = ba.montar_pacote_web(
        {"vc_painel": _vc_painel_ficticio(visoes)}, 2026, 11, AGORA)
    assert pacote["relatorios"]["vc_painel"]["avisos"] == sel["avisos"]


def test_T0013_escopo_sem_paineis_ou_entrada_vazia_nao_levanta():
    for r in (None, {}, {"paineis": None}, {"paineis": ["x", 1, None]}):
        sel = ba.selecionar_abas_web(r)
        assert sel["abas"] == {} and len(sel["avisos"]) == 2


def test_T0013_escopo_aba_achada_pelo_titulo_sem_visao():
    p = _painel(None, "Painel · produtividade")
    del p["painel"]["blocos"][0]["visao"]
    sel = ba.selecionar_abas_web({"paineis": [p]})
    b = sel["abas"]["produtividade"]["painel"]["blocos"][0]
    assert b["visao"] == "prod"
    assert set(b["dados"]) >= {"prod", "sub"} and "res" not in b["dados"]


def test_T0013_escopo_primeira_aba_vence_duplicada():
    p1 = _painel("res", "Painel · resultado")
    p2 = _painel("res", "Painel · resultado (2)")
    sel = ba.selecionar_abas_web({"paineis": [p1, p2]})
    assert sel["abas"]["resultado"]["titulo"] == "Painel · resultado"


def test_T0013_escopo_visao_du_nao_vira_resultado_pelo_titulo():
    p = _painel("du", "Painel · resultado")
    sel = ba.selecionar_abas_web({"paineis": [p]})
    assert "resultado" not in sel["abas"]


# --------------------------------------------- critério 3: sem token, pula
def test_T0013_criterio3_sem_url_nem_token_pula(monkeypatch):
    monkeypatch.setattr(requests, "post", _proibido)
    linhas = []
    ok = ba.enviar_pacote_web({"a": 1}, log=linhas.append)
    assert ok is False
    assert linhas and "pulado" in linhas[-1]
    assert ("BAP_WEB", "url") in _KeyringNulo.chamadas or \
        ("BAP_WEB", "token") in _KeyringNulo.chamadas


@pytest.mark.parametrize("url,token", [(URL, None), (None, TOKEN),
                                       ("  ", "  ")])
def test_T0013_criterio3_falta_url_ou_token_pula(monkeypatch, url, token):
    monkeypatch.setattr(requests, "post", _proibido)
    linhas = []
    assert ba.enviar_pacote_web({"a": 1}, url=url, token=token,
                                log=linhas.append) is False
    assert any("pulado" in l for l in linhas)
    assert all(TOKEN not in l for l in linhas)


def test_T0013_criterio3_keyring_que_levanta_nao_derruba(monkeypatch):
    class _KeyringQuebrado:
        @staticmethod
        def get_password(*_a):
            raise RuntimeError("cofre indisponível")
    monkeypatch.setattr(ba, "keyring", _KeyringQuebrado)
    monkeypatch.setattr(requests, "post", _proibido)
    assert ba.enviar_pacote_web({"a": 1}, log=lambda *_: None) is False


def test_T0013_criterio3_passo_pacote_web_sem_token_nao_levanta(
        monkeypatch, caplog):
    monkeypatch.setattr(requests, "post", _proibido)
    monkeypatch.setattr(ba, "coletar_relatorios_web",
                        lambda ano, mes: _resultados_ficticios())
    with caplog.at_level(logging.INFO, logger=ba.log.name):
        r = ba.passo_pacote_web()
    assert r.get("enviado") is False and "erro" not in r
    assert "pulado" in caplog.text


def test_T0013_criterio3_passo_pacote_web_com_montar_quebrado_nao_levanta(
        monkeypatch, caplog):
    import relatorios_nucleo

    def _montar_quebra(*_a, **_k):
        raise RuntimeError("base fictícia ausente")
    monkeypatch.setattr(relatorios_nucleo, "montar", _montar_quebra)
    monkeypatch.setattr(requests, "post", _proibido)
    monkeypatch.setenv("BAP_WEB_URL", URL)
    monkeypatch.setenv("BAP_WEB_TOKEN", TOKEN)
    with caplog.at_level(logging.WARNING, logger=ba.log.name):
        r = ba.passo_pacote_web()
    assert "erro" in r


def test_T0013_criterio3_sem_url_nem_token_nem_monta(monkeypatch, caplog):
    # revisão do PR #16: sem a web configurada, a rodada do robô fica como
    # antes do 4f (o Painel não é montado à toa)
    monkeypatch.delenv("BAP_WEB_URL", raising=False)
    monkeypatch.delenv("BAP_WEB_TOKEN", raising=False)
    monkeypatch.setattr(ba, "keyring", None)
    monkeypatch.setattr(requests, "post", _proibido)

    def _nao_monta(*_a, **_k):
        raise AssertionError("montou o Painel sem a web configurada")
    monkeypatch.setattr(ba, "coletar_relatorios_web", _nao_monta)
    with caplog.at_level(logging.INFO, logger=ba.log.name):
        r = ba.passo_pacote_web()
    assert r == {"enviado": False, "pulado": True}
    assert "pulado" in caplog.text


def test_T0013_coletar_chama_montar_vc_painel_e_farois_web(monkeypatch):
    import relatorios_nucleo
    chamadas = []

    def _montar(rid, pasta, params=None):
        chamadas.append((rid, params))
        return {"id": rid}
    monkeypatch.setattr(relatorios_nucleo, "montar", _montar)
    saida = ba.coletar_relatorios_web(2026, 11)
    params = {"ANO": "2026", "MÊS": "11"}
    farois = _farois_web()
    assert set(saida) == {"vc_painel", *farois}
    assert chamadas == [("vc_painel", params)] + [
        (rid, ba.params_farol_web(rid, 2026, 11)) for rid in farois]


def test_T0013_passo_pacote_web_simulado_grava_sem_enviar(monkeypatch,
                                                          tmp_path):
    monkeypatch.setattr(requests, "post", _proibido)
    monkeypatch.setattr(ba.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(ba, "coletar_relatorios_web",
                        lambda ano, mes: _resultados_ficticios())
    monkeypatch.setenv("BAP_WEB_URL", URL)
    monkeypatch.setenv("BAP_WEB_TOKEN", TOKEN)
    r = ba.passo_pacote_web(simular_pacote=True)
    arq = Path(r["simulado"])
    assert arq.parent == tmp_path / "BAP_PACOTE_WEB"
    dado = json.loads(arq.read_text(encoding="utf-8"))
    _so_tipos_json(dado)
    assert TOKEN not in arq.read_text(encoding="utf-8")


def test_T0013_flag_pacote_web_simular_existe():
    fonte = Path(ba.__file__).read_text(encoding="utf-8")
    assert '"--pacote-web-simular"' in fonte
    assert "args.pacote_web_simular" in fonte


# ------------------------------------------------ critério 4: envio correto
def test_T0013_criterio4_envio_bearer_corpo_timeout(monkeypatch):
    srv = _ServidorFalso([200])
    monkeypatch.setattr(requests, "post", srv)
    pacote = ba.montar_pacote_web(_resultados_ficticios(), 2026, 11, AGORA)
    linhas = []
    assert ba.enviar_pacote_web(pacote, url=URL, token=TOKEN,
                                log=linhas.append) is True
    assert len(srv.pedidos) == 1
    p = srv.pedidos[0]
    assert p["url"] == "https://bap-web-ficticio.example.com/api/pacote"
    assert p["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert p["headers"]["Content-Type"].startswith("application/json")
    assert p["timeout"] == 30
    assert json.loads(p["data"].decode("utf-8")) == pacote


def test_T0013_criterio4_url_e_token_do_ambiente(monkeypatch):
    srv = _ServidorFalso([201])
    monkeypatch.setattr(requests, "post", srv)
    monkeypatch.setenv("BAP_WEB_URL", URL + "/base/")
    monkeypatch.setenv("BAP_WEB_TOKEN", "  " + TOKEN + "  ")
    assert ba.enviar_pacote_web({"a": 1}, log=lambda *_: None) is True
    p = srv.pedidos[0]
    assert p["url"] == "https://bap-web-ficticio.example.com/base/api/pacote"
    assert p["headers"]["Authorization"] == f"Bearer {TOKEN}"


def test_T0013_criterio4_url_e_token_do_cofre(monkeypatch):
    class _KeyringCheio:
        @staticmethod
        def get_password(servico, usuario):
            assert servico == "BAP_WEB"
            return {"url": URL, "token": TOKEN}[usuario]
    monkeypatch.setattr(ba, "keyring", _KeyringCheio)
    srv = _ServidorFalso([200])
    monkeypatch.setattr(requests, "post", srv)
    assert ba.enviar_pacote_web({"a": 1}, log=lambda *_: None) is True
    assert srv.pedidos[0]["headers"]["Authorization"] == f"Bearer {TOKEN}"


def test_T0013_criterio4_porta_443_explicita_aceita(monkeypatch):
    srv = _ServidorFalso([200])
    monkeypatch.setattr(requests, "post", srv)
    assert ba.enviar_pacote_web({"a": 1}, url=URL + ":443", token=TOKEN,
                                log=lambda *_: None) is True
    assert srv.pedidos[0]["url"].startswith("https://")


@pytest.mark.parametrize("url_ruim", [
    "http://bap-web-ficticio.example.com",
    "https://bap-web-ficticio.example.com:8443",
    "https://bap-web-ficticio.example.com:80",
    "ftp://bap-web-ficticio.example.com",
    "bap-web-ficticio.example.com",
    "https://bap-web-ficticio.example.com:porta",
    "https://",
])
def test_T0013_criterio4_so_https_porta_443(monkeypatch, url_ruim):
    monkeypatch.setattr(requests, "post", _proibido)
    linhas = []
    assert ba.enviar_pacote_web({"a": 1}, url=url_ruim, token=TOKEN,
                                log=linhas.append) is False
    assert linhas
    assert all(TOKEN not in l for l in linhas)


def test_T0013_criterio4_tres_tentativas_em_falha_de_rede(monkeypatch):
    erro = requests.exceptions.ConnectionError("sem rede (fictício)")
    srv = _ServidorFalso([erro, erro, erro, 200])
    monkeypatch.setattr(requests, "post", srv)
    linhas = []
    assert ba.enviar_pacote_web({"a": 1}, url=URL, token=TOKEN,
                                log=linhas.append) is False
    assert len(srv.pedidos) == 3
    assert any("3/3" in l for l in linhas)


def test_T0013_criterio4_recupera_na_segunda_tentativa(monkeypatch):
    srv = _ServidorFalso([requests.exceptions.Timeout("lento"), 200])
    monkeypatch.setattr(requests, "post", srv)
    assert ba.enviar_pacote_web({"a": 1}, url=URL, token=TOKEN,
                                log=lambda *_: None) is True
    assert len(srv.pedidos) == 2


def test_T0013_criterio4_tres_tentativas_em_erro_http(monkeypatch):
    srv = _ServidorFalso([503, 502, 500])
    monkeypatch.setattr(requests, "post", srv)
    assert ba.enviar_pacote_web({"a": 1}, url=URL, token=TOKEN,
                                log=lambda *_: None) is False
    assert len(srv.pedidos) == 3


def test_T0013_criterio4_pacote_com_nan_nao_sai(monkeypatch):
    """Pacote cru com NaN (não passado pelo montar) não é enviado."""
    monkeypatch.setattr(requests, "post", _proibido)
    linhas = []
    assert ba.enviar_pacote_web({"x": float("nan")}, url=URL, token=TOKEN,
                                log=linhas.append) is False


# -------------------------------------- critério 5: token nunca no log
def _cenarios_log():
    return {
        "sucesso": [200],
        "erro_http": [401, 403, 500],
        "rede_com_token": [
            requests.exceptions.ConnectionError(
                f"falhou Authorization: Bearer {TOKEN}"),
            RuntimeError(f"token={TOKEN}"),
            OSError(TOKEN * 3),
        ],
    }


@pytest.mark.parametrize("cenario", ["sucesso", "erro_http",
                                     "rede_com_token"])
def test_T0013_criterio5_token_nunca_no_log(monkeypatch, caplog, capsys,
                                            cenario):
    srv = _ServidorFalso(_cenarios_log()[cenario])
    monkeypatch.setattr(requests, "post", srv)
    monkeypatch.setenv("BAP_WEB_URL", URL)
    monkeypatch.setenv("BAP_WEB_TOKEN", TOKEN)
    linhas = []
    with caplog.at_level(logging.DEBUG):
        ba.enviar_pacote_web({"a": 1}, log=linhas.append)
        # também pelo log padrão (print) e pelo logger do robô
        srv.respostas = _cenarios_log()[cenario]
        ba.enviar_pacote_web({"a": 1})
        srv.respostas = _cenarios_log()[cenario]
        ba.enviar_pacote_web({"a": 1}, log=ba.log.info)
    saida = capsys.readouterr()
    assert linhas
    for texto in linhas + [caplog.text, saida.out, saida.err]:
        assert TOKEN not in texto
        assert "1234567890abcdef" not in texto
    if cenario == "rede_com_token":
        assert any("***" in l for l in linhas)


def test_T0013_criterio5_token_nunca_no_log_do_passo(monkeypatch, caplog,
                                                     capsys):
    erro = requests.exceptions.ConnectionError(f"Bearer {TOKEN}")
    srv = _ServidorFalso([erro, 500, erro])
    monkeypatch.setattr(requests, "post", srv)
    monkeypatch.setattr(ba, "coletar_relatorios_web",
                        lambda ano, mes: _resultados_ficticios())
    monkeypatch.setenv("BAP_WEB_URL", URL)
    monkeypatch.setenv("BAP_WEB_TOKEN", TOKEN)
    with caplog.at_level(logging.DEBUG):
        r = ba.passo_pacote_web()
    assert r["enviado"] is False
    saida = capsys.readouterr()
    for texto in (caplog.text, saida.out, saida.err, json.dumps(r)):
        assert TOKEN not in texto
