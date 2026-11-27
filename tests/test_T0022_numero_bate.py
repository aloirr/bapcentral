"""T-0022: o número do pacote web bate com o farol de origem (relatorios_nucleo.montar), sem recalcular nada.

Usa as bases congeladas do repositório (20/11/2026). Painel Executivo (12 abas) e Farol de Metas Equipe.
Regra 8 (CLAUDE.md): desafio comercial em tudo; meta RH e RV nunca vão no pacote."""
from datetime import date
from pathlib import Path

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

# aceita os dois estados (testes entram antes do robô): sem o robô da T-0022, pula
pytestmark = pytest.mark.skipif(not hasattr(ba, "montar_por_uf_web"), reason="robô da T-0022 ainda não entrou")

RAIZ = Path(__file__).resolve().parent.parent
HOJE = date(2026, 11, 20)
PARAMS = {"ANO": "2026", "MÊS": "11"}


@pytest.fixture(scope="module")
def mundo(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setattr(ba, "_ufs_do_parametro_web", lambda r: ["AM"])          # um estado basta para conferir o recorte
    # T-0033: RELATORIOS/ é congelado; o montar do Painel do Diretor grava o
    # histórico do mês. Lê e grava numa cópia temporária (mesmos números).
    import painel_diretor as pdr                                        # noqa: PLC0415
    hist = tmp_path_factory.mktemp("hist") / pdr.ARQ_HIST
    hist.write_bytes(pdr._hist_path(RAIZ).read_bytes())
    mp.setattr(pdr, "_hist_path", lambda raiz: hist)
    rels = {"vc_painel": rn.montar("vc_painel", RAIZ, hoje=HOJE, params=PARAMS),
            "vc_meta": rn.montar("vc_meta", RAIZ, hoje=HOJE, params=PARAMS, tela=True)}
    for rid in ("vc_painel", "vc_meta"):
        rels[rid + "_uf"] = ba.montar_por_uf_web(rid, rels[rid], RAIZ, PARAMS, HOJE)
    sel = {k: v for k, v in rels.items() if k in ("vc_painel", "vc_meta")}
    pac = ba.montar_pacote_web({**rels, **{k: v for k, v in sel.items()}}, 2026, 11, raiz=RAIZ)
    yield rels, pac["relatorios"]
    mp.undo()


def _valores(kpis):
    return [(k["rotulo"], k["valor"], k.get("detalhe") or "") for k in kpis]


def test_RN_PAINEL_001_as_12_abas_do_pc_vao_no_pacote(mundo):
    rels, pac = mundo
    vp = pac["vc_painel"]
    assert set(vp["abas"]) == {"resultado", "produtividade", "por_dia_util"}
    assert [t for t, _c in ba.PAINEIS_WEB] == [p["titulo"] for p in rels["vc_painel"]["paineis"][3:]]
    assert set(vp["paineis"]) == {c for _t, c in ba.PAINEIS_WEB}


def test_RN_PAINEL_002_cartoes_do_diretor_batem_com_o_painel_do_pc(mundo):
    rels, pac = mundo
    for p in rels["vc_painel"]["paineis"][:3]:
        b = p["painel"]["blocos"][0]
        chave = ba._TITULOS_ABAS_WEB[p["titulo"]]
        web = pac["vc_painel"]["abas"][chave]["painel"]["blocos"][0]["dados"][b["visao"]]
        assert [(c["titulo"], c["valor"]) for c in web] == [(c["titulo"], c["valor"]) for c in b["dados"][b["visao"]]], chave


def test_RN_PAINEL_003_cartoes_e_placar_das_9_abas_batem(mundo):
    rels, pac = mundo
    por_titulo = {p["titulo"]: p for p in rels["vc_painel"]["paineis"]}
    for titulo, chave in ba.PAINEIS_WEB:
        assert _valores(pac["vc_painel"]["paineis"][chave]["kpis"]) == _valores(por_titulo[titulo]["kpis"]), chave
    pl_pc = next(b for b in por_titulo["Resumo gerencial"]["painel"]["blocos"] if b["tipo"] == "placar")
    pl_web = next(b for b in pac["vc_painel"]["paineis"]["resumo"]["painel"]["blocos"] if b["tipo"] == "placar")
    assert [(c["farol"], c["valor"], c["tom"]) for c in pl_web["cartoes"]] == [(c["farol"], c["valor"], c["tom"]) for c in pl_pc["cartoes"]]


def test_RN_PAINEL_004_tabelas_do_painel_batem_linha_a_linha(mundo):
    rels, pac = mundo
    pc = next(p for p in rels["vc_painel"]["paineis"] if p["titulo"] == "Faturamento")
    web = pac["vc_painel"]["paineis"]["faturamento"]["painel"]["blocos"]
    for b in (x for x in pc["painel"]["blocos"] if x["tipo"] == "tabela"):
        w = next(x for x in web if x.get("titulo") == b["titulo"])
        arred = lambda ls: [[(round(v, 4) if isinstance(v, float) else v) for v in r[:5]] for r in ls]  # noqa: E731
        assert arred(w["linhas"]) == arred(b["linhas"]), b["titulo"]


def test_RN_PAINEL_005_estado_bate_com_o_painel_montado_com_o_filtro(mundo):
    rels, pac = mundo
    am = {p["titulo"]: p for p in rels["vc_painel_uf"]["AM"]["paineis"]}
    for titulo, chave in ba.PAINEIS_WEB:
        aba = pac["vc_painel"]["paineis"][chave]
        if chave in ba._PAINEIS_UF_WEB:
            assert _valores(aba["recortes"]["AM"]["kpis"]) == _valores(am[titulo]["kpis"]), chave
        else:
            assert aba.get("so_bap") and "recortes" not in aba, chave


def test_RN_META_001_farol_de_metas_bate_com_o_pc(mundo):
    rels, pac = mundo
    pc, web = rels["vc_meta"], pac["vc_meta"]
    assert _valores(web["kpis"]) == _valores(pc["kpis"])
    assert [t["titulo"] for t in web["tabelas"]] == [t for t in ba._ABAS_META_WEB if any(x["titulo"] == t for x in pc["tabelas"])]
    for t in web["tabelas"]:
        orig = next(x for x in pc["tabelas"] if x["titulo"] == t["titulo"])
        base = orig["linhas_filtro"] if orig.get("top_n") else orig["linhas"]
        assert len(t["linhas"]) == len(base)
        assert [c["nome"] for c in t["colunas"]] == [c["nome"] for c in orig["colunas"]]
        if not orig.get("top_n") and orig.get("total"):
            assert t["total"][3] == orig["total"][3]
    am = rels["vc_meta_uf"]["AM"]
    assert _valores(web["recortes"]["AM"]["kpis"]) == _valores(am["kpis"])


def test_RN_META_002_regra_8_meta_rh_e_rv_fora_do_pacote(mundo):
    _rels, pac = mundo
    web = pac["vc_meta"]
    assert all(t["titulo"] != "Acomp. RH" for t in web["tabelas"])
    tudo = repr(pac)
    assert "META RH" not in tudo and "Acomp. RH" not in tudo and "Faturamento · meta RH" not in tudo
