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
                               FAROIS_PERMITIDOS, FAROIS_T0036,
                               FONTE_PENDENTE, problemas_escopo)

_NOMES = ("FAROIS_WEB", "_FONTE_BAIXADO_WEB", "_TABELA_RECORTE_WEB",
          "_UF_LINHAS_WEB", "RID_META_WEB", "selecionar_farol_web",
          "RIDS_RECORTE_CONFERIDO_WEB")


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
    # T-0036: + os 4 do Analista Comercial (contrato §10.11.1)
    assert set(FAROIS_T0036) == {"vc_saldo", "vc_markup", "vc_preco",
                                 "an_divergencias"}
    assert FAROIS_PERMITIDOS == (FAROIS_OBRIGATORIOS | set(FAROIS_LOTE2)
                                 | set(FAROIS_T0036))
    assert "pl_garantias" not in FAROIS_PERMITIDOS
    # a folga da fonte do "baixado em" vale só para os 4 do Analista
    assert FONTE_PENDENTE <= set(FAROIS_T0036)


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


# ------------------------------------------------------------------ T-0036
def test_RN_GER_006_trava_reprova_saldo_sem_conferencia_do_kpis_de():
    """Saldo com cartão por estado sem a conferência do kpis_de (§10.11.1):
    o número do estado pode sair errado; a trava reprova."""
    p = problemas_escopo(_robo(RIDS_RECORTE_CONFERIDO_WEB=("vc_markup",)))
    assert p == ["vc_saldo: fora de RIDS_RECORTE_CONFERIDO_WEB"]


def test_RN_GER_006_trava_reprova_pesquisa_pela_filial():
    """Pesquisa de mercado é da UF do cliente (§10.11.3), não da filial."""
    uf = dict(ba._UF_LINHAS_WEB)
    uf[("vc_preco", "Pesquisa de mercado")] = ("FILIAL", "filial")
    assert problemas_escopo(_robo(_UF_LINHAS_WEB=uf)) == [
        "vc_preco: regra de UF das linhas de 'Pesquisa de mercado' "
        "('FILIAL', 'filial'), esperado ('UF', 'uf')"]


def test_RN_GER_006_trava_reprova_recorte_no_preco():
    """Preço sem cartões por estado (§10.11.1): tabela de recorte reprova."""
    tab = dict(ba._TABELA_RECORTE_WEB, vc_preco="Reajustes por produto")
    p = problemas_escopo(_robo(_TABELA_RECORTE_WEB=tab))
    assert "vc_preco: sem_estado não leva recorte" in p


def test_RN_GER_006_trava_cobra_fonte_fora_da_folga():
    """A folga FONTE_PENDENTE não vale para os outros faróis."""
    fontes = {k: v for k, v in ba._FONTE_BAIXADO_WEB.items()
              if k != "vc_meta"}
    assert "vc_meta: sem a fonte do 'baixado em'" in problemas_escopo(
        _robo(_FONTE_BAIXADO_WEB=fontes))


def test_T0036_farois_do_analista_tem_fonte_do_baixado_em():
    """RN-GER-006 + §10.11.1: os 4 do Analista com a fonte do "baixado em"
    (o defeito do modulo-robo foi corrigido em 9d886fa)."""
    assert problemas_escopo(ba, fonte_pendente=frozenset()) == []
