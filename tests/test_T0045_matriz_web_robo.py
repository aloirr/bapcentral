"""T-0045 (ADR 0004 §9 item 9): a matriz web × robô, com a web de verdade.

O site é a `web/app/visitas.Visitas` do repositório (só biblioteca padrão; fixture
`web_visitas` do `tests/conftest.py`),
ligada ao robô por `visitas_nuvem_fixture.SessaoWeb` (a interface do
`requests`, sem rede). "Robô antigo" é o robô do PC sem a T-0045: só as
edições, pela régua do main d2cd695 (`tests/ref_T0045_edicoes_web_main.py`),
e nenhuma chamada a /api/visitas. "Web antiga" é o site sem as rotas de
visitas (404).

| web \\ robô | antigo                                  | novo                                             |
|------------|-----------------------------------------|--------------------------------------------------|
| antiga     | edições seguem                          | 404 mudo; edições seguem                         |
| nova       | edições seguem; lote fica esperando o PC | importa, confirma, fechados_pc; o diário = o do PC |

Regras: RN-VIS-002 (o dia fecha pela hora da baixa; o PC informa os dias
dele; o erro no confirmar tira só a parte da nuvem), RN-VIS-003 (o PC nunca
sobrescreve), RN-VIS-007 (sobe só o Espelho filtrado), RN-GER-012 (as
edições não mudam). Exige o robô da T-0045 (PR #165) no main, sem guarda.
Dados 100% fictícios.
"""
import json
from datetime import timedelta

import pytest

import bap_automation as ba
import ref_T0045_edicoes_web_main as ref
import visitas_maxima as vm
import visitas_nucleo as vn
import visitas_nuvem_fixture as fx
from visitas_nuvem_fixture import BASE, TOKEN_CRON, TOKEN_WEB, VENDEDOR, SessaoWeb


@pytest.fixture
def depois(monkeypatch):
    vezes = []
    monkeypatch.setattr(vm, "depois_de_baixar", lambda raiz, log: vezes.append(raiz) or {})
    return vezes


def _edicoes_robo_antigo(raiz, sessao):
    logs = []
    r = ref.carregar(ba).sincronizar_edicoes_web(raiz, BASE, TOKEN_WEB, sessao, logs.append,
                                                 lambda *a: 1, {"por": set(), "etapa": set(),
                                                                "transportadora": set()})
    return r, logs


def _volta_robo_novo(raiz, sessao):
    """A volta de 30 min do robô novo: edições e, depois, visitas (passo_pacote_web)."""
    logs = []
    ed = ba.sincronizar_edicoes_web(raiz, BASE, TOKEN_WEB, sessao, logs.append, lambda *a: 1,
                                    {"por": set(), "etapa": set(), "transportadora": set()})
    vis = ba.sincronizar_visitas_web(raiz, BASE, TOKEN_WEB, logs.append, sessao)
    return ed, vis, logs


def _rotas(sessao):
    return [c[1] for c in sessao.chamadas]


# ------------------------------------------------------------------ web antiga × robô antigo
def test_RN_GER_012_web_antiga_robo_antigo_edicoes_seguem(tmp_path):
    s = SessaoWeb(None)
    r, logs = _edicoes_robo_antigo(tmp_path, s)
    assert r == {"aplicadas": 0, "erros": 0, "pendentes": 0, "confirmado": False} and logs == []
    assert _rotas(s) == ["/api/edicoes"]


# ------------------------------------------------------------------ web antiga × robô novo
def test_RN_VIS_002_web_antiga_robo_novo_404_mudo_e_edicoes_seguem(tmp_path, depois):
    s = SessaoWeb(None)
    ed, vis, logs = _volta_robo_novo(tmp_path, s)
    assert ed == {"aplicadas": 0, "erros": 0, "pendentes": 0, "confirmado": False}
    assert vis == {"lotes": 0, "arquivos": 0, "dias": [], "erro": None}
    assert logs == [] and depois == []
    assert _rotas(s) == ["/api/edicoes", "/api/visitas/lotes"]             # sem POST às visitas
    assert not (tmp_path / ba.PASTA_VISITAS_WEB).exists()


# ------------------------------------------------------------------ web nova × robô antigo
def test_RN_VIS_002_web_nova_robo_antigo_lote_espera_o_pc(tmp_path, web_visitas):
    d = fx.dia_teste(2)
    vis = web_visitas.Visitas(tmp_path / "site", TOKEN_CRON)
    excel = fx.excel_da_nuvem(tmp_path / "e", d)[1]
    r = fx.lote_na_web(vis, d, excel)
    assert r["ok"] and r["seq"] == 1
    pc = tmp_path / "pc"
    d_pc = fx.dia_teste(4)
    vn.anotar_baixado(pc, fx.ymd(d_pc))
    s = SessaoWeb(vis)
    ed, logs = _edicoes_robo_antigo(pc, s)
    assert ed["aplicadas"] == 0 and logs == []
    assert _rotas(s) == ["/api/edicoes"]                                   # o robô antigo não fala de visitas
    assert not vn.pasta_analitico(pc).exists()
    sau = vis.saude()
    assert sau["lotes_a_importar"] == 1                                    # fica à espera; o site não cai
    t = vis.trabalho()
    assert t["fechados_pc_em"] is None
    assert fx.ymd(d) in t["indice"] and fx.ymd(d_pc) not in t["indice"]     # a nuvem não sabe o que o PC fechou
    assert web_visitas.dias_a_baixar(t["indice"], d_pc, d_pc, fx.hoje()) == [d_pc]  # e baixaria de novo (consequência)


# ------------------------------------------------------------------ web nova × robô novo
def test_RN_VIS_002_web_nova_robo_novo_importa_confirma_e_informa_o_pc(tmp_path, web_visitas, depois):
    d = fx.dia_teste(2)
    d_pc = fx.dia_teste(4)
    vis = web_visitas.Visitas(tmp_path / "site", TOKEN_CRON)
    original, filtrado = fx.excel_da_nuvem(tmp_path / "e", d)
    fx.lote_na_web(vis, d, filtrado)
    pc = tmp_path / "pc"
    vn.anotar_baixado(pc, fx.ymd(d_pc))
    s = SessaoWeb(vis)
    ed, r, logs = _volta_robo_novo(pc, s)
    assert r == {"lotes": 1, "arquivos": 1, "dias": [fx.ymd(d)], "erro": None}
    assert (vn.pasta_analitico(pc) / VENDEDOR / fx.nome_arquivo(VENDEDOR, d)).read_bytes() == filtrado
    assert depois == [pc]
    assert vis.saude()["lotes_a_importar"] == 0                           # o site viu o "aplicada"
    t = vis.trabalho()
    assert t["fechados_pc_em"] is not None
    assert fx.ymd(d_pc) in t["indice"]                                     # RN-VIS-002: o dia do PC entrou
    assert web_visitas.dias_a_baixar(t["indice"], d_pc, d, fx.hoje()) == [
        x for x in (d_pc + timedelta(days=1),) if x < d]                   # só o dia que ninguém baixou
    assert _rotas(s) == ["/api/edicoes", "/api/visitas/lotes", "/api/visitas/lote/1",
                         "/api/visitas/lotes/confirmar"]
    assert TOKEN_WEB not in "\n".join(logs) and VENDEDOR not in "\n".join(logs)
    # a volta seguinte: nada a importar, mas o POST do fechados_pc sai (o site aceita)
    s2 = SessaoWeb(vis)
    _, r2, _ = _volta_robo_novo(pc, s2)
    assert r2["lotes"] == 0
    assert _rotas(s2) == ["/api/edicoes", "/api/visitas/lotes", "/api/visitas/lotes/confirmar"]
    assert s2.chamadas[-1][2]["resultados"] == []


def test_RN_VIS_002_ponta_a_ponta_diario_igual_ao_do_pc(tmp_path, web_visitas, depois):
    """ADR §8: Excel de exemplo sem dado pessoal → filtro → lote → importação → diario/AAAAMMDD.csv igual ao do PC
    com o mesmo Excel sem filtro."""
    d = fx.dia_teste(2)
    vis = web_visitas.Visitas(tmp_path / "site", TOKEN_CRON)
    original, filtrado = fx.excel_da_nuvem(tmp_path / "e", d)
    fx.lote_na_web(vis, d, filtrado)
    nuvem = tmp_path / "nuvem"
    _volta_robo_novo(nuvem, SessaoWeb(vis))
    pc = tmp_path / "pc"
    arq = vn.pasta_analitico(pc) / VENDEDOR / fx.nome_arquivo(VENDEDOR, d)
    arq.parent.mkdir(parents=True)
    arq.write_bytes(original)
    assert vn.montar_dia(pc, d, {}) == 1
    a, b = vn.arquivo_do_dia(nuvem, d).read_text(encoding="utf-8"), vn.arquivo_do_dia(pc, d).read_text(encoding="utf-8")
    assert a == b and a.count("\n") == 2                                    # cabeçalho + 1 representante
    # valor × regra: o número do Farol de Visita sai do cabeçalho do Espelho (visitados da agenda + fora)
    linha = a.splitlines()[1].split(";")
    esp = vn.ler_espelho(arq)
    va, vf = (int(esp[k].split("/")[0]) for k in ("vis_agenda_txt", "vis_fora_txt"))
    assert int(linha[14]) == va + vf == 3


def test_RN_VIS_002_erro_no_confirmar_tira_so_a_parte_da_nuvem(tmp_path, web_visitas, depois):
    d = fx.dia_teste(2)
    vis = web_visitas.Visitas(tmp_path / "site", TOKEN_CRON)
    fx.lote_na_web(vis, d, fx.excel_da_nuvem(tmp_path / "e", d)[1])
    assert fx.ymd(d) in vis.trabalho()["indice"]
    gz = tmp_path / "site" / "visitas" / "lotes" / "1.json.gz"
    import gzip
    corpo = json.loads(gzip.decompress(gz.read_bytes()))
    corpo["arquivos"][0]["b64"] = corpo["arquivos"][0]["b64"][:-8] + "AAAAAAA="     # o Excel corrompido no disco
    gz.write_bytes(gzip.compress(fx.bruto(corpo)))
    pc = tmp_path / "pc"
    d_pc = fx.dia_teste(4)
    vn.anotar_baixado(pc, fx.ymd(d_pc))
    s = SessaoWeb(vis)
    _, r, _ = _volta_robo_novo(pc, s)
    assert r["lotes"] == 0 and s.chamadas[-1][2]["resultados"] == [{"seq": 1, "status": "erro", "motivo": "sha256"}]
    ind = vis.trabalho()["indice"]
    assert fx.ymd(d) not in ind and fx.ymd(d_pc) in ind                   # a nuvem baixa de novo; o PC fica
    assert not vn.pasta_analitico(pc).exists()


def test_RN_VIS_003_disco_do_site_recomeca_e_o_pc_nao_duplica(tmp_path, web_visitas, depois):
    import shutil
    d = fx.dia_teste(2)
    excel = fx.excel_da_nuvem(tmp_path / "e", d)[1]
    vis = web_visitas.Visitas(tmp_path / "site", TOKEN_CRON)
    fx.lote_na_web(vis, d, excel)
    pc = tmp_path / "pc"
    _volta_robo_novo(pc, SessaoWeb(vis))
    shutil.rmtree(tmp_path / "site")                                       # disco novo: época nova
    vis2 = web_visitas.Visitas(tmp_path / "site", TOKEN_CRON)
    fx.lote_na_web(vis2, d, excel, motivo="pedido")
    assert vis2.lotes(0)["epoca"] != json.loads((pc / ba.PASTA_VISITAS_WEB / ba.ARQ_ESTADO_VISITAS_WEB)
                                                .read_text(encoding="utf-8"))["epoca"]
    _, r, _ = _volta_robo_novo(pc, SessaoWeb(vis2))
    assert r["lotes"] == 1
    assert sorted(p.name for p in (vn.pasta_analitico(pc) / VENDEDOR).iterdir()) == [fx.nome_arquivo(VENDEDOR, d)]
    assert vis2.saude()["lotes_a_importar"] == 0


def test_RN_VIS_002_token_do_cron_nao_abre_as_rotas_do_pc(tmp_path, web_visitas, depois, monkeypatch):
    """O robô do PC só usa o BAP_WEB_TOKEN; com o token do cron, o site (SessaoWeb) responde 401 e o PC segue."""
    vis = web_visitas.Visitas(tmp_path / "site", TOKEN_CRON)
    s = SessaoWeb(vis)
    logs = []
    r = ba.sincronizar_visitas_web(tmp_path / "pc", BASE, TOKEN_CRON, logs.append, s)
    assert r["lotes"] == 0 and r["erro"] is None
    assert len(logs) == 1 and "401" in logs[0] and TOKEN_CRON not in logs[0]
