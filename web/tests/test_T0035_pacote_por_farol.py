"""T-0035 (ADR 0003, contrato §10.8): pacote por farol, índice e leitura sob demanda. Fixtures fictícias."""
import gzip
import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import ADMIN, SENHA0, TOKEN, entrar, guardado, pacote_ficticio, por_farol, postar, token_form
from csv_fixture import pacote_com_csvs
from farol_fixture import farol_inadimplencia, pacote_farol

from app import cobranca, pacotes

MANAUS = ZoneInfo("America/Manaus")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _agora(horas=0):
    return (datetime.now(MANAUS) - timedelta(hours=horas)).replace(microsecond=0).isoformat()


def _dois(gerado_em):
    p = pacote_farol(pl_inadimplencia=farol_inadimplencia(), **{})
    p["relatorios"]["vc_painel"] = pacote_ficticio()["relatorios"]["vc_painel"]
    p["gerado_em"] = gerado_em
    return p


def _post_farol(cli, rid, corpo: bytes, lote="20261126T083000", sha=None, gz=True, **cab):
    sha = sha or hashlib.sha256(corpo).hexdigest()
    h = {**H, "X-BAP-SHA256": sha, **({"Content-Encoding": "gzip"} if gz else {}), **cab}
    return cli.post(f"/api/pacote/{lote}/farol/{rid}", content=gzip.compress(corpo) if gz else corpo, headers=h)


# ------------------------------------------------------------------ as 4 combinações robô × web
def test_formato1_na_web_nova_vira_lote_inteiro(cli, amb):
    assert postar(cli, pacote_farol()).status_code == 200            # robô antigo, web nova
    s = cli.get("/saude").json()
    assert s["pacote"]["formatos"] == [1, 2] and s["pacote"]["origem"] == "inteiro"
    assert s["pacote"]["farois"] == 1 and s["versao"] == "0.6.0"


def test_formato2_com_e_sem_gzip_guarda_o_mesmo(cli, amb):
    p = pacote_farol()
    assert postar(cli, p).status_code == 200
    f1 = guardado(amb)["relatorios"]
    por_farol(cli, {**p, "gerado_em": "2026-11-25T08:30:00-04:00"}, gz=False)
    por_farol(cli, {**p, "gerado_em": "2026-11-26T08:30:00-04:00"}, gz=True)
    f2 = guardado(amb)
    assert f2["relatorios"] == f1 and f2["indice"]["origem"] == "por_farol"
    assert cli.get("/saude").json()["pacote"]["origem"] == "por_farol"


def test_robo_novo_web_antiga_cai_no_formato1(cli):
    # a web antiga não traz `pacote.formatos`; o robô novo então manda o formato 1, que a web nova segue aceitando
    assert postar(cli, pacote_ficticio()).status_code == 200


def test_farol_so_pelo_site_novo_aparece_na_tela(admin):
    r, _ = por_farol(admin, _dois(_agora()))
    assert r.status_code == 200 and r.json()["farois"] == 2
    assert admin.get("/farol/pl_inadimplencia").status_code == 200
    assert admin.get("/painel").status_code == 200


# ------------------------------------------------------------------ recusas e teto
def test_recusas_do_recebimento(cli):
    corpo = pacotes.json_compacto(farol_inadimplencia())
    assert cli.post("/api/pacote/20261126T083000/farol/pl_inadimplencia", content=corpo).status_code == 401
    assert _post_farol(cli, "pl_inadimplencia", corpo, lote="../x").status_code in (400, 404)
    assert _post_farol(cli, "pl_inadimplencia", corpo, lote="2026").status_code == 400
    assert _post_farol(cli, "nao_existe", corpo).status_code == 404
    assert _post_farol(cli, "pl_inadimplencia", corpo, sha="zz").status_code == 400
    assert _post_farol(cli, "pl_inadimplencia", corpo, sha="0" * 64).status_code == 422
    assert _post_farol(cli, "pl_inadimplencia", corpo, **{"Content-Type": "text/plain"}).status_code == 415
    assert _post_farol(cli, "pl_inadimplencia", corpo, **{"Content-Encoding": "br"}).status_code == 415
    r = _post_farol(cli, "pl_inadimplencia", b'{"forma":"farol"}')
    assert r.status_code == 422 and r.json()["erro"] == "esquema inválido"


def test_teto_do_farol_e_bomba_de_gzip(cli, amb, monkeypatch):
    monkeypatch.setattr(pacotes, "FAROL_CORPO_MAX", 20_000)
    bomba = json.dumps({"x": "a" * 5_000_000}).encode()              # comprime a quase nada
    assert len(gzip.compress(bomba)) < 20_000
    assert _post_farol(cli, "pl_inadimplencia", bomba).status_code == 413
    monkeypatch.setattr(pacotes, "FAROL_CORPO_MAX", 24 * 1024 * 1024)
    pequeno = pacotes.json_compacto(farol_inadimplencia())
    monkeypatch.setattr(pacotes, "FAROL_JSON_MAX", 100)              # teto do farol sem anexos
    r = cli.post("/api/pacote/20261126T083000/farol/pl_inadimplencia", content=gzip.compress(pequeno),
                 headers={**H, "Content-Encoding": "gzip", "X-BAP-SHA256": hashlib.sha256(pequeno).hexdigest()})
    assert r.status_code == 200                                      # o teto da config vale, não a constante
    assert pacotes.FAROL_JSON_MAX == 100


def test_teto_por_farol_da_config(amb, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import criar_app
    monkeypatch.setenv("BAP_WEB_FAROL_MAX_MB", "0.0001")
    with TestClient(criar_app(), base_url="https://testserver") as c:
        r = _post_farol(c, "pl_inadimplencia", pacotes.json_compacto(farol_inadimplencia()))
        assert r.status_code == 413 and r.json()["erro"] == "farol grande demais"
        # o teto não atinge os anexos: o PNG da parcial segue por fora do JSON do farol (testado abaixo)


# ------------------------------------------------------------------ fechar
def test_fechar_repetido_409_e_nao_vigente(cli, amb):
    p = pacote_farol()
    r, lote = por_farol(cli, p)
    topo = {k: p[k] for k in ("versao_contrato", "gerado_em", "ano", "mes")}
    r2 = cli.post(f"/api/pacote/{lote}/fechar", json={**topo, "farois": {"pl_inadimplencia": "0" * 64}}, headers=H)
    assert r2.status_code == 200 and r2.json() == r.json()           # repetido: mesma resposta
    novo = {**topo, "gerado_em": "2026-11-27T08:30:00-04:00"}
    lote2 = pacotes.nome_arquivo(novo["gerado_em"])
    r3 = cli.post(f"/api/pacote/{lote2}/fechar", json={**novo, "farois": {"pl_inadimplencia": "a" * 64}}, headers=H)
    assert r3.status_code == 409 and r3.json() == {"erro": "faltam", "farois": ["pl_inadimplencia"]}
    r4 = cli.post(f"/api/pacote/{lote2}/fechar", json={**novo, "gerado_em": "2026-11-28T08:30:00-04:00",
                                                      "farois": {"pl_inadimplencia": "a" * 64}}, headers=H)
    assert r4.status_code == 422                                     # o lote não bate com o gerado_em
    antigo, _ = por_farol(cli, {**p, "gerado_em": "2026-11-10T08:30:00-04:00"})
    assert antigo.json()["vigente"] is False                         # guardado, mas não vira o vigente


def test_retencao_dos_7_lotes_contando_formato1(cli, amb):
    for i in range(1, 10):
        por_farol(cli, {**pacote_farol(), "gerado_em": f"2026-11-{i:02d}T08:30:00-04:00"})
    lotes = sorted(d.name for d in (amb / "pacotes").iterdir())
    assert len(lotes) == 7 and lotes[-1] == "20261109T083000" and "_recebendo" not in lotes


def test_disco_do_formato1_e_convertido_na_partida(amb):
    (amb / "pacotes").mkdir()
    p = pacote_farol()
    p["recebido_em"] = "2026-11-24T08:31:00-04:00"
    (amb / "pacotes" / "20261124T083000.json").write_text(json.dumps(p), encoding="utf-8")
    assert pacotes.converter_legado(amb) is True and pacotes.converter_legado(amb) is False
    ind = pacotes.Indice(amb)
    assert ind.indice()["origem"] == "convertido" and ind.recebido_em("pl_inadimplencia") == p["recebido_em"]


# ------------------------------------------------------------------ anexos no disco
def test_parciais_e_csvs_ficam_no_disco_fora_do_farol(admin, amb):
    p = pacote_com_csvs(_agora())
    assert por_farol(admin, p)[0].status_code == 200
    pasta = next(d for d in (amb / "pacotes").iterdir() if d.is_dir())
    assert list(pasta.glob("pv_pedidos.csvs.json.gz"))
    g = guardado(amb)["relatorios"]["pv_pedidos"]
    assert "csvs_protheus" not in g and "parciais" not in g
    nome = "261124_002_MANAUS_BAPSeparacaoCD.csv"
    r = admin.get(f"/farol/pv_pedidos/csv/{nome}")
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]


# ------------------------------------------------------------------ farol que falhou: herdado e selo
def test_farol_que_falhou_herda_e_leva_o_selo(admin, amb, monkeypatch):
    por_farol(admin, _dois(_agora(20)))
    r, _ = por_farol(admin, _dois(_agora()), omitir=("pl_inadimplencia",), manter=("pl_inadimplencia",))
    assert r.status_code == 200 and r.json()["herdados"] == ["pl_inadimplencia"]
    ind = guardado(amb)["indice"]["farois"]
    assert ind["pl_inadimplencia"]["herdado_de"] and ind["vc_painel"]["herdado_de"] is None
    assert ind["pl_inadimplencia"]["gerado_em"] != ind["vc_painel"]["gerado_em"]
    assert "Desatualizado" not in admin.get("/farol/pl_inadimplencia").text          # ainda dentro das 26 h
    hoje = cobranca.agora()
    monkeypatch.setattr(cobranca, "agora", lambda: hoje + timedelta(hours=10))        # passou de 26 h
    assert "Desatualizado" in admin.get("/farol/pl_inadimplencia").text
    assert "Desatualizado" not in admin.get("/painel").text                          # o Painel é do lote novo


def test_farol_com_mais_de_26h_nao_e_herdado(cli, amb):
    por_farol(cli, _dois(_agora(30)))
    r, _ = por_farol(cli, _dois(_agora()), omitir=("pl_inadimplencia",), manter=("pl_inadimplencia",))
    assert r.json()["herdados"] == [] and "pl_inadimplencia" not in guardado(amb)["relatorios"]


def test_farol_que_nao_montou_sem_manter_some(cli, amb):
    por_farol(cli, _dois(_agora(2)))
    por_farol(cli, _dois(_agora()), omitir=("pl_inadimplencia",))
    assert list(guardado(amb)["relatorios"]) == ["vc_painel"]


# ------------------------------------------------------------------ cache LRU e memória
def test_cache_lru_respeita_o_orcamento(amb):
    p = _dois(_agora())
    shas = {}
    for rid, f in p["relatorios"].items():
        corpo = pacotes.json_compacto(f)
        shas[rid] = hashlib.sha256(corpo).hexdigest()
        pacotes.receber_farol(amb, pacotes.nome_arquivo(p["gerado_em"]), rid, corpo, shas[rid])
    topo = {k: p[k] for k in ("versao_contrato", "gerado_em", "ano", "mes")}
    pacotes.fechar(amb, pacotes.nome_arquivo(p["gerado_em"]), topo, shas, None, _agora())
    grande = pacotes.Indice(amb, cache_mb=96)
    assert grande.farol("pl_inadimplencia") is grande.farol("pl_inadimplencia")        # 2ª leitura vem do cache
    grande.farol("vc_painel")
    assert grande.cache()[1] == 2 and grande.cache()[0] > 0
    custo_a = grande.entrada("pl_inadimplencia")["bytes_json"] * pacotes.CUSTO_POR_BYTE
    custo_b = grande.entrada("vc_painel")["bytes_json"] * pacotes.CUSTO_POR_BYTE
    justo = pacotes.Indice(amb, cache_mb=(max(custo_a, custo_b) + 1) / pacotes.MB)     # só cabe um
    justo.farol("pl_inadimplencia")
    justo.farol("vc_painel")
    assert justo.cache()[1] == 1                                                        # o mais antigo saiu
    zero = pacotes.Indice(amb, cache_mb=0)
    assert zero.farol("vc_painel") and zero.cache()[1] == 0                             # maior que o orçamento: lido, não guardado
    grande.esvaziar()
    assert grande.cache() == (0.0, 0)


def test_saude_traz_a_memoria_medida(admin):
    por_farol(admin, _dois(_agora()))
    admin.get("/farol/pl_inadimplencia")
    m = admin.get("/saude").json()["memoria"]
    assert set(m) == {"rss_mb", "pico_mb", "limite_mb", "cache_mb", "cache_farois"}
    assert m["rss_mb"] > 1 and m["pico_mb"] >= m["rss_mb"] * 0.5 and m["cache_farois"] >= 1
    assert "memoria_alerta" not in admin.get("/saude").json() or m["pico_mb"] > 400


def test_memoria_do_lote_grande_fica_abaixo_do_orcamento(cli, amb):
    """Um farol de ~3 MB (JSON) lido sob demanda: o pico medido (tracemalloc) cabe no teto da ADR (§4.9)."""
    import tracemalloc
    f = farol_inadimplencia()
    f["avisos"] = ["linha fictícia de aviso " + str(i) for i in range(100_000)]
    p = pacote_farol(pl_inadimplencia=f)
    por_farol(cli, p)
    ind = pacotes.Indice(amb, cache_mb=96)
    tracemalloc.start()
    ind.farol("pl_inadimplencia")
    atual, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    bj = ind.entrada("pl_inadimplencia")["bytes_json"]
    assert bj > 2_000_000 and pico < bj * 12 and ind.cache()[0] <= 96


def test_por_sha_acha_so_o_farol_e_sha_antigo_nao_acha(cli, amb):
    p = pacote_farol()
    por_farol(cli, {**p, "gerado_em": "2026-11-24T08:30:00-04:00"})
    sha_velho = pacotes.Indice(amb).sha("pl_inadimplencia")
    por_farol(cli, {**p, "gerado_em": "2026-11-25T08:30:00-04:00", "relatorios": {
        "pl_inadimplencia": {**farol_inadimplencia(), "titulo": "Outro título"}}})
    assert pacotes.por_sha(amb, "pl_inadimplencia", sha_velho)["titulo"] != "Outro título"
    assert pacotes.por_sha(amb, "pl_inadimplencia", "f" * 64) is None
    assert pacotes.por_sha(amb, "pl_inadimplencia", "lixo") is None


def test_pico_vem_do_vmhwm_do_proprio_processo(amb, monkeypatch):
    """O ru_maxrss herda o pico do lançador (fork+exec); o pico do /saude é o VmHWM de /proc/self/status."""
    from pathlib import Path
    real = Path.read_text
    falso = "Name:\tx\nVmHWM:\t   64512 kB\nVmRSS:\t   51200 kB\n"
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: falso if str(self) == "/proc/self/status" else real(self, *a, **k))
    import resource
    monkeypatch.setattr(resource, "getrusage", lambda *_: (_ for _ in ()).throw(AssertionError("não deve usar o ru_maxrss")))
    m = pacotes.memoria(pacotes.Indice(amb))
    assert m["pico_mb"] == 63.0 and m["rss_mb"] == 50.0


def test_lote_e_sha_com_quebra_de_linha_no_fim_sao_recusados(cli):
    corpo = pacotes.json_compacto(farol_inadimplencia())
    assert _post_farol(cli, "pl_inadimplencia", corpo, lote="20261126T083000%0A").status_code == 400
    assert not pacotes.RE_LOTE.fullmatch("20261126T083000\n") and not pacotes.RE_SHA.fullmatch("a" * 64 + "\n")
    assert pacotes.por_sha(pacotes.Path("/nao/existe"), "pl_inadimplencia", "a" * 64 + "\n") is None


def test_pacote_antigo_estragado_nao_derruba_a_web(amb):
    from fastapi.testclient import TestClient
    from app.main import criar_app
    (amb / "pacotes").mkdir()
    (amb / "pacotes" / "20261124T083000.json").write_text("{lixo", encoding="utf-8")
    with TestClient(criar_app(), base_url="https://testserver") as c:
        s = c.get("/saude")
        assert s.status_code == 200 and "convertido" in s.json()["aviso_pacote"]
        assert s.json()["pacote"]["lote"] is None
