"""T-0023 v2 (PR 1, nucleo): a edicao da Garantia, as colunas ocultas e o teto
do texto. Trazido do modulo-farois e revisto pelo testes.

Regras: RN-GER-012 (a edicao e so pelo site; a linha nova da garantia, contrato
10.9.2), RN-POS-005 (DT. FECHAMENTO = solicitacao + 15 dias uteis), RN-GER-011
(o contato do cliente nunca vai; as 3 colunas novas vao ocultas).
Dados 100% ficticios. Nada de RELATORIOS/ real alterado (o montar so le)."""
from datetime import date
from pathlib import Path

import pytest

import garantias as gm
import relatorios_nucleo as rn

if not (hasattr(rn, "edicao_garantia") and hasattr(rn, "MAX_TEXTO_EDICAO")):
    pytest.skip("núcleo da T-0023 v2 (modulo-farois/T-0023-nucleo) ainda não entrou",
                allow_module_level=True)

RAIZ = Path(__file__).resolve().parent.parent

COLS = ["STATUS", "RESULTADO ANÁLISE", "TICKET", "DT. SOLICITAÇÃO",
        "DT. FECHAMENTO", "CÓD. CLIENTE", "CÓD. PRODUTO",
        "DESCRIÇÃO PRODUTO", "QTD", "PENDÊNCIAS", "RETORNO DO CLIENTE",
        "RECLAMAÇÃO", "OBSERVAÇÃO", "DT. RETORNO"]
I = {c: i for i, c in enumerate(COLS)}


def _ed(ticket="G-0013"):
    return rn.edicao_garantia(I, gm.STATUS, gm.RESULTADOS, ticket)


def test_RN_GER_012_garantia_tem_14_campos_sem_contato():
    campos = [c["campo"] for c in _ed()["campos"]]
    assert len(campos) == 14 and len(set(campos)) == 14
    assert not any(c.startswith("contato") for c in campos)   # P2 A
    assert _ed()["modulo"] == "garantias"


def test_RN_GER_012_teto_do_texto_vem_do_nucleo():
    por = {c["campo"]: c for c in _ed()["campos"]}
    for k in ("reclamacao", "pendencias", "retorno_cliente", "observacao"):
        assert por[k]["max"] == rn.MAX_TEXTO_EDICAO[("garantias", k)] == 600
        assert por[k]["multilinha"] and por[k]["mantem_caixa"]
    assert "max" not in por["descricao"]
    assert rn.max_texto_edicao("garantias", "descricao") == 60


def test_RN_GER_012_linha_nova_com_padroes():
    por = {c["campo"]: c for c in _ed("G-0013")["campos"]}
    assert por["ticket"]["padrao"] == "G-0013"          # garantias.novo_ticket
    assert por["dt_solicitacao"]["padrao"] == "@hoje"
    assert (por["status"]["padrao"], por["resultado"]["padrao"]) == (
        "ABERTO", "PENDENTE")
    assert por["status"]["opcoes"] == list(gm.STATUS)
    assert por["resultado"]["opcoes"] == list(gm.RESULTADOS)
    assert por["dt_prazo"]["opcoes"] == [] and por["dt_prazo"]["data"]
    assert _ed()["novo_web"] == {"rotulo": "Nova garantia"}


def test_RN_POS_005_cada_campo_aponta_a_coluna():
    ed = _ed()
    assert ed["chave"] == I["TICKET"]
    por = {c["campo"]: c["col"] for c in ed["campos"]}
    assert por["dt_prazo"] == I["DT. FECHAMENTO"]       # prazo = 15 DU
    assert por["dt_retorno"] == I["DT. RETORNO"]
    assert gm.PRAZO_UTEIS == 15


def test_RN_GER_011_montar_garantias_tres_colunas_novas_ocultas():
    r = rn.montar("pl_garantias", RAIZ, hoje=date(2026, 11, 24),
                  params={"ANO": "2026", "MÊS": "11"})
    t = next(x for x in r["tabelas"] if x["titulo"] == "Garantias")
    nomes = [c["nome"] for c in t["colunas"]]
    for n in ("RECLAMAÇÃO", "OBSERVAÇÃO", "DT. RETORNO"):
        assert t["colunas"][nomes.index(n)]["oculta"]
    assert all(len(l) == len(nomes) for l in t["linhas"])
    ed = t["edicao"]
    assert all(0 <= c["col"] < len(nomes) for c in ed["campos"])
    assert nomes[ed["chave"]] == "TICKET"
