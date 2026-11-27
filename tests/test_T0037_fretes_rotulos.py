"""T-0037 — rótulos de agrupamento do Farol de Fretes no PC (faróis 48c6577).

`relatorios_nucleo.rotulo_agrupa_fretes(coluna, linha)` dá o rótulo das abas
"Por UF", "Por cidade" e "Por transportadora": "Sem UF", "Sem cidade / UF",
"<CIDADE> / Sem UF", "Sem transportadora" (nota com acompanhamento e sem
transportadora) e "Sem acompanhamento" (nota sem a CHAVE da entrega). Valor
× regra: a linha "Sem transportadora" conta o mesmo que o cartão "Sem
transportadora" (RN-POS-009, cartões do Fretes). A UF é a do cliente
(RN-POS-007). Linhas FICTÍCIAS (17 células, a CHAVE na 17ª).

Teste trazido do modulo-farois.
"""
import pytest

import relatorios_nucleo as rn

COL_CIDADE, COL_UF, COL_TRANSP, COL_CHAVE = 6, 7, 11, 16


def _l(cidade="", uf="", transp="", chave="X"):
    ln = [""] * 17
    ln[8] = ln[9] = 0.0                  # VLR NF e VLR FRETE: o kpis_fretes soma
    ln[COL_CIDADE], ln[COL_UF], ln[COL_TRANSP], ln[COL_CHAVE] = (
        cidade, uf, transp, chave)
    return ln


def test_T0037_rotulo_uf_vazia_vira_sem_uf():
    assert rn.rotulo_agrupa_fretes(COL_UF, _l(uf="")) == "Sem UF"
    assert rn.rotulo_agrupa_fretes(COL_UF, _l(uf="PA")) == "PA"


def test_T0037_rotulo_cidade_com_e_sem_uf():
    f = rn.rotulo_agrupa_fretes
    assert f(COL_CIDADE, _l("CIDADE FICT A", "PA")) == "CIDADE FICT A / PA"
    assert f(COL_CIDADE, _l("CIDADE FICT A", "")) == "CIDADE FICT A / Sem UF"
    assert f(COL_CIDADE, _l("", "MA")) == "Sem cidade / MA"
    assert f(COL_CIDADE, _l("", "")) == "Sem cidade / Sem UF"


def test_T0037_rotulo_transportadora_e_sem_acompanhamento():
    f = rn.rotulo_agrupa_fretes
    assert f(COL_TRANSP, _l(transp="TRANSPORTADORA FICTICIA")) == \
        "TRANSPORTADORA FICTICIA"
    assert f(COL_TRANSP, _l(transp="", chave="123")) == "Sem transportadora"
    assert f(COL_TRANSP, _l(transp="", chave="")) == "Sem acompanhamento"


def test_RN_POS_009_sem_transportadora_bate_com_o_cartao():
    """Cartão "Sem transportadora" de verdade (rn.kpis_fretes) = a linha
    "Sem transportadora" da aba (a sem CHAVE vai a "Sem acompanhamento")."""
    ls = [_l(chave="1"), _l(chave=""),
          _l(transp="TRANSPORTADORA FICTICIA", chave="2")]
    cartao = int(next(k["valor"] for k in rn.kpis_fretes(ls, {})
                      if k["rotulo"] == "Sem transportadora"))
    tab = sum(1 for ln in ls
              if rn.rotulo_agrupa_fretes(COL_TRANSP, ln) == "Sem transportadora")
    sem_acomp = sum(1 for ln in ls if rn.rotulo_agrupa_fretes(
        COL_TRANSP, ln) == "Sem acompanhamento")
    assert cartao == tab == 1
    assert sem_acomp == 1
