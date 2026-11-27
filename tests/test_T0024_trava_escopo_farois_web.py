"""T-0024: a trava do escopo de FAROIS_WEB (tests/escopo_farois_web.py) vale
com e sem o lote 2 e reprova o que tem de reprovar.

Regra citada: RN-GER-006 (estado = filial da nota no faturamento e no
estoque; UF do cliente em fretes e carteira; sem a UF, aviso "Sem filtro por
estado").

O robô de verdade passa na trava; uma cópia do robô com um defeito plantado
(farol fora da lista, obrigatório faltando, farol a mais sem fonte ou sem
regra de UF, tabela de recorte sem regra) reprova. Sem dado de cliente.
"""
from types import SimpleNamespace

import pytest

ba = pytest.importorskip("bap_automation")

from escopo_farois_web import (FAROIS_LOTE2, FAROIS_OBRIGATORIOS,  # noqa: E402
                               FAROIS_PERMITIDOS, problemas_escopo)

_NOMES = ("FAROIS_WEB", "_FONTE_BAIXADO_WEB", "_TABELA_RECORTE_WEB",
          "_UF_LINHAS_WEB", "RID_META_WEB", "selecionar_farol_web")


def _robo(**troca):
    """Cópia rasa dos nomes que a trava lê, com a troca pedida."""
    d = {n: getattr(ba, n) for n in _NOMES}
    d["RIDS_KPIS_POR_UF_WEB"] = tuple(getattr(ba, "RIDS_KPIS_POR_UF_WEB", ()))
    d.update(troca)
    return SimpleNamespace(**d)


def test_RN_GER_006_trava_lista_permitida_e_os_cinco_do_lote2():
    assert FAROIS_OBRIGATORIOS == {"pl_inadimplencia", "pv_pedidos",
                                   "pl_entregas", "vc_visitas", "vc_meta"}
    assert set(FAROIS_LOTE2) == {"pv_indicadores", "vc_base", "vc_planner",
                                 "pl_giro", "pl_frw"}
    assert FAROIS_PERMITIDOS == (FAROIS_OBRIGATORIOS | set(FAROIS_LOTE2)
                                 | {"pl_fretes"})          # T-0037
    assert "pl_garantias" not in FAROIS_PERMITIDOS


def test_RN_GER_006_robo_de_verdade_passa_na_trava():
    assert problemas_escopo(ba) == []
    assert problemas_escopo(_robo()) == []


def test_RN_GER_006_trava_reprova_farol_fora_da_lista():
    p = problemas_escopo(_robo(FAROIS_WEB=tuple(ba.FAROIS_WEB)
                               + ("pl_garantias",)))
    assert "pl_garantias: fora da lista PERMITIDA" in p


def test_RN_GER_006_trava_reprova_obrigatorio_faltando_e_repetido():
    sem = tuple(r for r in ba.FAROIS_WEB if r != "vc_visitas")
    assert "vc_visitas: obrigatório e fora de FAROIS_WEB" in \
        problemas_escopo(_robo(FAROIS_WEB=sem))
    dup = tuple(ba.FAROIS_WEB) + ("pv_pedidos",)
    assert any(x.startswith("FAROIS_WEB com repetição")
               for x in problemas_escopo(_robo(FAROIS_WEB=dup)))


def test_RN_GER_006_trava_reprova_farol_do_lote2_sem_fonte_nem_regra():
    """pl_giro a mais, sem a fonte do "baixado em", sem a tabela de recorte e
    sem a regra de UF (filial do estoque): três problemas."""
    fontes = {k: v for k, v in ba._FONTE_BAIXADO_WEB.items() if k != "pl_giro"}
    tab = {k: v for k, v in ba._TABELA_RECORTE_WEB.items() if k != "pl_giro"}
    uf = {k: v for k, v in ba._UF_LINHAS_WEB.items() if k[0] != "pl_giro"}
    farois = tuple(r for r in ba.FAROIS_WEB if r != "pl_giro") + ("pl_giro",)
    p = problemas_escopo(_robo(FAROIS_WEB=farois, _FONTE_BAIXADO_WEB=fontes,
                               _TABELA_RECORTE_WEB=tab, _UF_LINHAS_WEB=uf))
    assert "pl_giro: sem a fonte do 'baixado em'" in p
    assert any(x.startswith("pl_giro: tabela de recorte None") for x in p)
    assert any(x.startswith("pl_giro: regra de UF None") for x in p)


def test_RN_GER_006_trava_reprova_regra_de_uf_trocada():
    """Estoque pela UF do cliente (e não pela filial) reprova."""
    tab = dict(ba._TABELA_RECORTE_WEB, pl_frw="Estoque FRW")
    uf = dict(ba._UF_LINHAS_WEB)
    uf[("pl_frw", "Estoque FRW")] = ("UF", "uf")
    farois = tuple(r for r in ba.FAROIS_WEB if r != "pl_frw") + ("pl_frw",)
    fontes = dict(ba._FONTE_BAIXADO_WEB,
                  pl_frw=ba._FONTE_BAIXADO_WEB["pv_pedidos"])
    p = problemas_escopo(_robo(FAROIS_WEB=farois, _FONTE_BAIXADO_WEB=fontes,
                               _TABELA_RECORTE_WEB=tab, _UF_LINHAS_WEB=uf))
    assert p == ["pl_frw: regra de UF ('UF', 'uf'), esperado "
                 "('FILIAL', 'filial')"]


def test_RN_GER_006_trava_reprova_tabela_de_recorte_sem_regra():
    tab = dict(ba._TABELA_RECORTE_WEB, pl_garantias="Garantias")
    assert "pl_garantias: tabela de recorte sem regra declarada" in \
        problemas_escopo(_robo(_TABELA_RECORTE_WEB=tab))
