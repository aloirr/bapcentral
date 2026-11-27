"""T-0045 (ADR 0004 §8 e §9 item 8; contrato visitas-nuvem §4.1 a §4.4): o robô
do PC importa os lotes de visitas que a nuvem baixou, contra um site de
mentira (`visitas_nuvem_fixture.SiteFalso`).

- `sincronizar_visitas_web`: 404 da web antiga mudo; lote importado; a volta
  seguinte só com o `fechados_pc`; o mesmo conteúdo não duplica; outro
  conteúdo grava com -2; sha256 ruim, `..` e barra recusados; nunca levanta;
- RN-VIS-002: a hora do índice do PC nunca recua (`juntar_baixado`, ed640e1);
- erro inesperado ao montar o dia vira `erro`/`dia` e a fila anda (ed640e1);
- o laço `puxar_fila_web` com o `aplicar` das visitas: os cenários do laço das
  edições (página, época nova, já confirmada, pendente, 409).

Exigem o robô da T-0045 (PR #165) no main, sem guarda. Excel e nomes 100%
fictícios; tudo em pasta temporária; sem rede.
"""
import json
from datetime import datetime, timedelta

import pytest

import bap_automation as ba
import visitas_maxima as vm
import visitas_nucleo as vn
import visitas_nuvem_fixture as fx
from visitas_nuvem_fixture import BASE, NOMES_FICTICIOS, TOKEN_WEB, VENDEDOR, VENDEDOR2, SiteFalso

ZERO = {"lotes": 0, "arquivos": 0, "dias": [], "erro": None}


@pytest.fixture
def dia():
    return fx.dia_teste(2)


@pytest.fixture
def excel(tmp_path_factory, dia):
    """(original, filtrado) do Espelho fictício do VENDEDOR."""
    return fx.excel_da_nuvem(tmp_path_factory.mktemp("espelho"), dia)


@pytest.fixture
def depois(monkeypatch):
    """`visitas_maxima.depois_de_baixar` contado (sem tocar no acompanhamento)."""
    vezes = []
    monkeypatch.setattr(vm, "depois_de_baixar", lambda raiz, log: vezes.append(raiz) or {})
    return vezes


def _lote(d, dados, pasta=VENDEDOR, hhmm="06-07", **k):
    return fx.bruto(fx.corpo_lote(d, [fx.arquivo(pasta, fx.nome_arquivo(pasta, d, hhmm), dados)], **k))


def _rodar(raiz, site):
    logs = []
    r = ba.sincronizar_visitas_web(raiz, BASE, TOKEN_WEB, logs.append, site)
    return r, logs


def _analitico(raiz, pasta=VENDEDOR):
    p = vn.pasta_analitico(raiz) / pasta
    return sorted(x.name for x in p.iterdir()) if p.is_dir() else []


def _importados(raiz):
    arq = raiz / ba.PASTA_VISITAS_WEB / ba.ARQ_IMPORTADOS_VISITAS_WEB
    return [json.loads(x) for x in arq.read_text(encoding="utf-8").splitlines()] if arq.exists() else []


def _estado(raiz):
    return json.loads((raiz / ba.PASTA_VISITAS_WEB / ba.ARQ_ESTADO_VISITAS_WEB).read_text(encoding="utf-8"))


def _sem_nome_nem_token(logs):
    texto = "\n".join(logs)
    return TOKEN_WEB not in texto and not any(n in texto for n in NOMES_FICTICIOS)


# ------------------------------------------------------------------ web antiga
def test_RN_VIS_002_web_antiga_404_mudo(tmp_path, depois):
    site = SiteFalso(antigo=True)
    r, logs = _rodar(tmp_path, site)
    assert (r, logs) == (ZERO, [])
    assert [c[1] for c in site.chamadas] == ["/api/visitas/lotes"]          # um GET, nenhum POST
    assert not any(p.is_file() for p in tmp_path.rglob("*"))               # nada gravado no PC
    assert depois == []
    r2, logs2 = _rodar(tmp_path, SiteFalso(antigo=True))                   # e segue mudo nas voltas
    assert (r2, logs2) == (ZERO, [])


@pytest.mark.parametrize("status", [401, 500, 503])
def test_RN_VIS_002_outros_status_do_site_logam_sem_token(tmp_path, status, depois):
    class Site(SiteFalso):
        def get(self, url, params=None, headers=None, timeout=None):
            self.chamadas.append(("GET", url, params, headers, timeout))
            return fx.resp(status)
    r, logs = _rodar(tmp_path, Site())
    assert r == ZERO and len(logs) == 1 and str(status) in logs[0] and _sem_nome_nem_token(logs)


def test_RN_VIS_002_site_caido_nunca_levanta(tmp_path, depois):
    class Caido:
        def get(self, *a, **k):
            raise ConnectionError("rede fora (fictício)")
        post = get
    r, logs = _rodar(tmp_path, Caido())
    assert r == ZERO and _sem_nome_nem_token(logs)


# ------------------------------------------------------------------ lote importado
def test_RN_VIS_003_lote_importado(tmp_path, dia, excel, depois):
    pc_dia = fx.dia_teste(5)
    vn.anotar_baixado(tmp_path, fx.ymd(pc_dia), datetime.combine(pc_dia + timedelta(days=1),
                                                                 datetime.min.time()).replace(hour=7, minute=12))
    site = SiteFalso({1: _lote(dia, excel[1])})
    r, logs = _rodar(tmp_path, site)
    assert r == {"lotes": 1, "arquivos": 1, "dias": [fx.ymd(dia)], "erro": None}
    arq = vn.pasta_analitico(tmp_path) / VENDEDOR / fx.nome_arquivo(VENDEDOR, dia)
    assert arq.read_bytes() == excel[1]                                   # o Excel filtrado, byte a byte
    assert depois == [tmp_path]                                           # uma vez por importação
    baixado = f"{dia + timedelta(days=1):%Y-%m-%d}T06:07:41"
    assert vn.indice(tmp_path)[fx.ymd(dia)] == baixado                    # RN-VIS-002: a hora da nuvem
    assert vn.arquivo_do_dia(tmp_path, dia).exists()                       # o diario/AAAAMMDD.csv
    (_, rota, corpo, cab, _), = site.posts
    assert rota == "/api/visitas/lotes/confirmar" and cab == {"Authorization": f"Bearer {TOKEN_WEB}"}
    assert corpo["epoca"] == "ep-1"
    assert corpo["resultados"] == [{"seq": 1, "status": "aplicada", "motivo": ""}]
    assert corpo["fechados_pc"] == {fx.ymd(pc_dia): f"{pc_dia + timedelta(days=1):%Y-%m-%d}T07:12:00-04:00",
                                    fx.ymd(dia): baixado + "-04:00"}
    assert _estado(tmp_path) == {"epoca": "ep-1", "ate_seq": 1, "a_confirmar": []}
    reg, = _importados(tmp_path)
    assert set(reg) <= {"seq", "epoca", "dia", "arquivos", "status", "motivo", "em"}   # sem nome
    assert (reg["seq"], reg["epoca"], reg["dia"], reg["status"]) == (1, "ep-1", fx.ymd(dia), "aplicada")
    assert _sem_nome_nem_token(logs)
    assert [c[1] for c in site.gets] == ["/api/visitas/lotes", "/api/visitas/lote/1"]


def test_RN_VIS_003_corpo_sem_gzip_tambem_serve(tmp_path, dia, excel, depois):
    r, _ = _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}, gz=False))
    assert r["lotes"] == 1 and _analitico(tmp_path) == [fx.nome_arquivo(VENDEDOR, dia)]


def test_RN_VIS_002_segunda_volta_so_fechados_pc(tmp_path, dia, excel, depois):
    _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}))
    site = SiteFalso({1: _lote(dia, excel[1])})
    site.confirmados[1] = {"seq": 1, "status": "aplicada", "motivo": ""}
    r, logs = _rodar(tmp_path, site)
    assert r == ZERO and logs == [] and depois == [tmp_path]               # nada novo: sem depois_de_baixar
    assert [c[1] for c in site.gets] == ["/api/visitas/lotes"]             # nenhum GET de lote
    (_, rota, corpo, _, _), = site.posts
    assert rota == "/api/visitas/lotes/confirmar" and corpo["resultados"] == []
    assert fx.ymd(dia) in corpo["fechados_pc"]
    assert site.chamadas[0][2] == {"desde": 1}
    assert len(_importados(tmp_path)) == 1


def test_RN_VIS_002_primeira_volta_com_fila_vazia_ja_manda_fechados_pc(tmp_path, depois):
    d = fx.dia_teste(3)
    vn.anotar_baixado(tmp_path, fx.ymd(d), datetime(d.year, d.month, d.day, 18, 0))
    site = SiteFalso({})
    r, _ = _rodar(tmp_path, site)
    (_, _, corpo, _, _), = site.posts
    assert r == ZERO and corpo == {"epoca": "ep-1", "resultados": [],
                                   "fechados_pc": {fx.ymd(d): f"{d:%Y-%m-%d}T18:00:00-04:00"}}


def test_RN_VIS_003_mesmo_conteudo_sem_duplicar(tmp_path, dia, excel, depois):
    _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}))
    r, _ = _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}, epoca="ep-2"))   # o disco do site recomeçou
    assert r["lotes"] == 1                                                   # confirmado de novo
    assert _analitico(tmp_path) == [fx.nome_arquivo(VENDEDOR, dia)]          # sem -2
    assert [x["epoca"] for x in _importados(tmp_path)] == ["ep-1", "ep-2"]   # só acréscimo


def test_RN_VIS_003_outro_conteudo_com_sufixo_2(tmp_path, dia, excel, depois):
    _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}))
    outro = fx.excel_da_nuvem(tmp_path / "outro", dia, nome=VENDEDOR)[1]
    outro_cod = fx.excel_da_nuvem(tmp_path / "outro2", dia, cod="900002", nome=VENDEDOR)[1]
    assert outro_cod != excel[1]
    _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1]), 2: _lote(dia, outro_cod)}))
    nome = fx.nome_arquivo(VENDEDOR, dia)
    assert _analitico(tmp_path) == [nome.replace(".xlsx", "-2.xlsx"), nome]
    pasta = vn.pasta_analitico(tmp_path) / VENDEDOR
    assert (pasta / nome).read_bytes() == excel[1]                           # o primeiro intacto
    assert (pasta / nome.replace(".xlsx", "-2.xlsx")).read_bytes() == outro_cod
    assert outro is not None


@pytest.mark.parametrize("estrago", ["cabecalho", "linha", "arquivo", "bytes", "b64"])
def test_RN_VIS_003_sha256_ruim_recusado(tmp_path, dia, excel, depois, estrago):
    c = fx.corpo_lote(dia, [fx.arquivo(VENDEDOR, fx.nome_arquivo(VENDEDOR, dia), excel[1])])
    k = {}
    if estrago == "cabecalho":
        k["sha_cab"] = "0" * 64
    elif estrago == "linha":
        k["sha_linha"] = "f" * 64
    elif estrago == "arquivo":
        c["arquivos"][0]["sha256"] = "a" * 64
    elif estrago == "bytes":
        c["arquivos"][0]["bytes"] += 1
    else:
        c["arquivos"][0]["b64"] = "não é base64!"
    site = SiteFalso({1: fx.bruto(c)}, **k)
    r, logs = _rodar(tmp_path, site)
    assert r == ZERO and depois == []
    assert site.posts[0][2]["resultados"] == [{"seq": 1, "status": "erro", "motivo": "sha256"}]
    assert _analitico(tmp_path) == [] and fx.ymd(dia) not in vn.indice(tmp_path)
    assert _importados(tmp_path)[0]["status"] == "erro" and _sem_nome_nem_token(logs)


@pytest.mark.parametrize("mexer,motivo", [
    (lambda c: c["arquivos"][0].update(pasta="../FORA"), "pasta"),
    (lambda c: c["arquivos"][0].update(pasta="A/B"), "pasta"),
    (lambda c: c["arquivos"][0].update(pasta="A\\B"), "pasta"),
    (lambda c: c["arquivos"][0].update(pasta=".."), "pasta"),
    (lambda c: c["arquivos"][0].update(pasta="minusculo ficticio"), "pasta"),      # não é o nome_limpo
    (lambda c: c["arquivos"][0].update(nome=c["arquivos"][0]["nome"].replace("VISITA-", "VISITA-../")), "nome"),
    (lambda c: c["arquivos"][0].update(nome="../" + c["arquivos"][0]["nome"]), "nome"),
    (lambda c: c["arquivos"][0].update(nome=c["arquivos"][0]["nome"].replace(".xlsx", "/x.xlsx")), "nome"),
    (lambda c: c["arquivos"][0].update(nome=c["arquivos"][0]["nome"].replace(VENDEDOR, VENDEDOR2)), "nome"),
    (lambda c: c["arquivos"][0].update(nome="planilha.xlsx"), "nome"),
    (lambda c: c.update(arquivos=[]), "nome"),
    (lambda c: c.update(versao=2), "dia"),
])
def test_RN_VIS_003_nome_com_barra_ou_ponto_ponto_recusado(tmp_path, dia, excel, depois, mexer, motivo):
    c = fx.corpo_lote(dia, [fx.arquivo(VENDEDOR, fx.nome_arquivo(VENDEDOR, dia), excel[1])])
    mexer(c)
    site = SiteFalso({1: fx.bruto(c)})
    r, _ = _rodar(tmp_path, site)
    assert r == ZERO
    assert site.posts[0][2]["resultados"] == [{"seq": 1, "status": "erro", "motivo": motivo}]
    gravados = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert gravados == {f"{ba.PASTA_VISITAS_WEB.as_posix()}/{ba.ARQ_ESTADO_VISITAS_WEB}",
                        f"{ba.PASTA_VISITAS_WEB.as_posix()}/{ba.ARQ_IMPORTADOS_VISITAS_WEB}"}
    assert not any(p.is_file() for p in tmp_path.parent.glob("FORA*"))


def test_RN_VIS_003_dia_do_corpo_diferente_da_linha_ou_no_futuro(tmp_path, excel, depois):
    futuro = fx.hoje() + timedelta(days=1)
    for d, motivo in ((futuro, "dia"),):
        site = SiteFalso({1: _lote(d, excel[1])})
        _rodar(tmp_path / d.isoformat(), site)
        assert site.posts[0][2]["resultados"] == [{"seq": 1, "status": "erro", "motivo": motivo}]

    class Torto(SiteFalso):
        def _linha(self, seq, c):
            return dict(super()._linha(seq, c), dia="20000101")
    site = Torto({1: _lote(fx.dia_teste(2), excel[1])})
    _rodar(tmp_path / "torto", site)
    assert site.posts[0][2]["resultados"] == [{"seq": 1, "status": "erro", "motivo": "dia"}]


def test_RN_VIS_003_lote_com_um_arquivo_ruim_nao_grava_nenhum(tmp_path, dia, excel, depois):
    """Confere tudo antes de gravar qualquer Excel."""
    bom = fx.arquivo(VENDEDOR, fx.nome_arquivo(VENDEDOR, dia), excel[1])
    ruim = dict(fx.arquivo(VENDEDOR2, fx.nome_arquivo(VENDEDOR2, dia), b"x"), sha256="0" * 64)
    site = SiteFalso({1: fx.bruto(fx.corpo_lote(dia, [bom, ruim]))})
    _rodar(tmp_path, site)
    assert site.posts[0][2]["resultados"][0]["status"] == "erro"
    assert not vn.pasta_analitico(tmp_path).exists()


def test_RN_VIS_002_lote_que_saiu_pela_retencao_e_erro_para_a_nuvem_baixar_de_novo(tmp_path, dia, excel, depois):
    site = SiteFalso({1: _lote(dia, excel[1])}, lote_status=404)
    _rodar(tmp_path, site)
    assert site.posts[0][2]["resultados"] == [{"seq": 1, "status": "erro", "motivo": "sha256"}]


def test_RN_VIS_003_site_fora_no_lote_e_excel_aberto_ficam_pendentes(tmp_path, dia, excel, depois, monkeypatch):
    site = SiteFalso({1: _lote(dia, excel[1]), 2: _lote(dia, excel[1], hhmm="07-00")}, lote_status=503)
    r, logs = _rodar(tmp_path, site)
    assert r == ZERO and site.posts[0][2]["resultados"] == []               # o pendente não vai ao site
    assert _estado(tmp_path)["ate_seq"] == 0 and _importados(tmp_path) == []
    assert [c[1] for c in site.gets] == ["/api/visitas/lotes", "/api/visitas/lote/1"]   # parou no primeiro
    assert any("espera a proxima rodada" in m for m in logs) and _sem_nome_nem_token(logs)

    def aberto(*a, **k):
        raise PermissionError("aberto no Excel (fictício)")
    monkeypatch.setattr(vm, "gravar_excel_importado", aberto)
    r, _ = _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}))
    assert r == ZERO and _estado(tmp_path)["ate_seq"] == 0
    monkeypatch.undo()
    monkeypatch.setattr(vm, "depois_de_baixar", lambda raiz, log: {})
    r, _ = _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}))         # na volta seguinte, entra
    assert r["lotes"] == 1 and _estado(tmp_path)["ate_seq"] == 1


def test_RN_VIS_003_erro_inesperado_ao_montar_o_dia_e_erro_e_a_fila_anda(tmp_path, dia, excel, depois, monkeypatch):
    """ed640e1: o que não é disco nem Excel aberto daria o mesmo erro sempre: vira `erro`/`dia` e o próximo entra."""
    reais = vn.montar_dia
    vezes = []

    def montar(raiz, d, extras=None):
        vezes.append(d)
        if len(vezes) == 1:
            raise KeyError(f"coluna nova da Máxima com {VENDEDOR}")
        return reais(raiz, d, extras)
    monkeypatch.setattr(vn, "montar_dia", montar)
    d2 = fx.dia_teste(3)
    excel2 = fx.excel_da_nuvem(tmp_path / "e2", d2)[1]
    site = SiteFalso({1: _lote(dia, excel[1]), 2: _lote(d2, excel2)})
    r, logs = _rodar(tmp_path, site)
    assert site.posts[0][2]["resultados"] == [{"seq": 1, "status": "erro", "motivo": "dia"},
                                              {"seq": 2, "status": "aplicada", "motivo": ""}]
    assert r["lotes"] == 1 and r["dias"] == [fx.ymd(d2)]
    assert _estado(tmp_path)["ate_seq"] == 2
    assert _sem_nome_nem_token(logs) and not any("coluna nova" in m for m in logs)


@pytest.mark.parametrize("exc", [PermissionError("aberto"), OSError("disco")])
def test_RN_VIS_003_disco_e_excel_aberto_continuam_pendentes(tmp_path, dia, excel, depois, monkeypatch, exc):
    def montar(*a, **k):
        raise exc
    monkeypatch.setattr(vn, "montar_dia", montar)
    site = SiteFalso({1: _lote(dia, excel[1])})
    _rodar(tmp_path, site)
    assert site.posts[0][2]["resultados"] == [] and _estado(tmp_path)["ate_seq"] == 0


# ------------------------------------------------------------------ RN-VIS-002: a hora do índice nunca recua
def test_RN_VIS_002_hora_do_indice_do_pc_nunca_recua(tmp_path, dia, excel, depois):
    """ed640e1: o PC baixou o dia DEPOIS da nuvem: a hora do PC fica (a maior, `juntar_baixado`)."""
    depois_da_nuvem = datetime.combine(dia + timedelta(days=1), datetime.min.time()).replace(hour=9)
    vn.anotar_baixado(tmp_path, fx.ymd(dia), depois_da_nuvem)
    vn.anotar_baixado(tmp_path, f"{dia:%Y%m}", depois_da_nuvem)
    _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}))
    ind = vn.indice(tmp_path)
    assert ind[fx.ymd(dia)] == depois_da_nuvem.isoformat(timespec="seconds")
    assert ind[f"{dia:%Y%m}"] == depois_da_nuvem.isoformat(timespec="seconds")


def test_RN_VIS_002_hora_da_nuvem_mais_nova_ou_empate_entra(tmp_path, dia, excel, depois):
    baixado = datetime.combine(dia + timedelta(days=1), datetime.min.time()).replace(hour=6, minute=7, second=41)
    for raiz, pc in ((tmp_path / "antes", baixado - timedelta(hours=1)), (tmp_path / "empate", baixado)):
        vn.anotar_baixado(raiz, fx.ymd(dia), pc)
        _rodar(raiz, SiteFalso({1: _lote(dia, excel[1])}))
        assert vn.indice(raiz)[fx.ymd(dia)] == baixado.isoformat(timespec="seconds")
        assert vn.juntar_baixado({fx.ymd(dia): baixado.isoformat()},
                                 {fx.ymd(dia): pc.isoformat()})[fx.ymd(dia)]["origem"] == "nuvem"


def test_RN_VIS_002_baixado_em_com_outro_fuso_vira_manaus_no_indice(tmp_path, dia, excel, depois):
    """f6ae758: o `baixado_em` passa pelo `vn._quando_manaus`; o índice guarda Manaus sem fuso."""
    utc = f"{dia + timedelta(days=1):%Y-%m-%d}T10:07:41+00:00"
    _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1], baixado_em=utc)}))
    assert vn.indice(tmp_path)[fx.ymd(dia)] == f"{dia + timedelta(days=1):%Y-%m-%d}T06:07:41"


# ------------------------------------------------------------------ o laço `puxar_fila_web` nas visitas
def test_RN_VIS_003_laco_paginado_traz_todos_na_ordem(tmp_path, excel, depois):
    dias = [fx.dia_teste(n) for n in (4, 3, 2)]
    lotes = {i + 1: _lote(d, fx.excel_da_nuvem(tmp_path / f"e{i}", d)[1]) for i, d in enumerate(dias)}
    site = SiteFalso(lotes, pagina=1)
    r, _ = _rodar(tmp_path / "pc", site)
    assert r["lotes"] == 3 and r["dias"] == [fx.ymd(d) for d in dias]
    desdes = [c[2]["desde"] for c in site.gets if c[1] == "/api/visitas/lotes"]
    assert desdes == [0, 1, 2]
    assert [x["seq"] for x in site.posts[0][2]["resultados"]] == [1, 2, 3]
    assert depois == [tmp_path / "pc"]                                    # uma vez para os 3


def test_RN_VIS_003_laco_ja_confirmada_no_site_nao_importa(tmp_path, dia, excel, depois):
    site = SiteFalso({1: _lote(dia, excel[1])})
    site.confirmados[1] = {"seq": 1, "status": "aplicada", "motivo": ""}
    r, _ = _rodar(tmp_path, site)
    assert r == ZERO and _analitico(tmp_path) == [] and _estado(tmp_path)["ate_seq"] == 1


def test_RN_VIS_003_laco_epoca_nova_puxa_tudo_de_novo(tmp_path, dia, excel, depois):
    _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}))
    site = SiteFalso({1: _lote(dia, excel[1])}, epoca="ep-2")
    _rodar(tmp_path, site)
    desdes = [c[2]["desde"] for c in site.gets if c[1] == "/api/visitas/lotes"]
    assert desdes == [1, 0]                                               # viu a época nova e voltou ao zero
    assert _estado(tmp_path) == {"epoca": "ep-2", "ate_seq": 1, "a_confirmar": []}


def test_RN_VIS_003_laco_409_no_confirmar_volta_ao_zero(tmp_path, dia, excel, depois):
    class Epoca409(SiteFalso):
        def post(self, url, json=None, headers=None, timeout=None):
            self.chamadas.append(("POST", url.replace(BASE, ""), json, headers, timeout))
            return fx.resp(409, {"erro": "epoca"})
    _rodar(tmp_path, Epoca409({1: _lote(dia, excel[1])}))
    assert _estado(tmp_path) == {"epoca": "", "ate_seq": 0, "a_confirmar": []}


def test_RN_VIS_003_laco_confirmar_que_falha_repete_na_volta(tmp_path, dia, excel, depois):
    _rodar(tmp_path, SiteFalso({1: _lote(dia, excel[1])}, conf=503))
    assert _estado(tmp_path)["a_confirmar"] == [{"seq": 1, "status": "aplicada", "motivo": ""}]
    site = SiteFalso({1: _lote(dia, excel[1])})
    _rodar(tmp_path, site)
    assert site.posts[0][2]["resultados"] == [{"seq": 1, "status": "aplicada", "motivo": ""}]
    assert _estado(tmp_path)["a_confirmar"] == [] and len(_analitico(tmp_path)) == 1


def test_RN_VIS_003_puxar_fila_web_e_o_laco_das_duas_filas():
    """Contrato §4.4: o laço é um só; as edições e as visitas chamam o `puxar_fila_web` (o revisor pediu no CI)."""
    import inspect
    for f in (ba.sincronizar_edicoes_web, ba.sincronizar_visitas_web):
        assert "puxar_fila_web(" in inspect.getsource(f)
    fonte = inspect.getsource(ba)
    assert fonte.count("def puxar_fila_web(") == 1
    assert fonte.count("for _ in range(_PAGINAS_MAX_EDICOES_WEB)") == 1   # a paginação também é uma só


def test_RN_VIS_003_volta_de_30_min_chama_visitas_depois_das_edicoes_e_antes_do_pacote():
    import inspect
    fonte = inspect.getsource(ba.passo_pacote_web)
    i_ed, i_vis = fonte.index("sincronizar_edicoes_web("), fonte.index("sincronizar_visitas_web(")
    assert i_ed < i_vis < fonte.index("coletar_relatorios_web(")
