"""T-0024: a trava do escopo de FAROIS_WEB (tests/escopo_farois_web.py) tem o
lote 2 como obrigatório (o #91 está no main) e reprova o que tem de reprovar.

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
                               FAROIS_PERMITIDOS, FAROIS_T0023, FAROIS_T0036,
                               problemas_escopo)
from escopo_farois_web import FAROIS_FRETES_TRANSICAO  # noqa: E402  transição T-0037: até o #169 (testes/T-0037-fretes)

# rid inventado, que nunca entra na lista (o pl_garantias entrou na T-0023 v2
# e o vc_markup na T-0036; um rid real pode entrar amanhã)
FORA = "zz_fora"

_NOMES = ("FAROIS_WEB", "_FONTE_BAIXADO_WEB", "_TABELA_RECORTE_WEB",
          "_UF_LINHAS_WEB", "RID_META_WEB", "selecionar_farol_web")


def _robo(**troca):
    """Cópia rasa dos nomes que a trava lê, com a troca pedida."""
    d = {n: getattr(ba, n) for n in _NOMES}
    d["RIDS_KPIS_POR_UF_WEB"] = tuple(getattr(ba, "RIDS_KPIS_POR_UF_WEB", ()))
    d["RIDS_RECORTE_CONFERIDO_WEB"] = tuple(
        getattr(ba, "RIDS_RECORTE_CONFERIDO_WEB", ()))           # T-0036
    d.update(troca)
    return SimpleNamespace(**d)


def test_RN_GER_006_trava_lista_permitida_os_cinco_do_lote2_e_os_da_T0023_e_T0036():
    """Depois do #91, os 5 do lote 2 são obrigatórios; depois do robô da
    T-0023 v2 (#171), os 3 do pós-venda (FAROIS_T0023), e depois do robô da
    T-0036 (#159), os 4 do Analista. A lista permitida é a dos obrigatórios."""
    assert set(FAROIS_LOTE2) == {"pv_indicadores", "vc_base", "vc_planner",
                                 "pl_giro", "pl_frw"}
    assert FAROIS_OBRIGATORIOS == ({"pl_inadimplencia", "pv_pedidos",
                                    "pl_entregas", "vc_visitas", "vc_meta"}
                                   | set(FAROIS_LOTE2) | set(FAROIS_T0023)
                                   | set(FAROIS_T0036))
    assert FAROIS_T0023 == {
        "pl_garantias": ("sem_estado",),
        "pl_devolucoes": ("tabela", "Devoluções", "FILIAL", "filial"),
        "pl_ncc": ("tabela", "NCC pendentes", "FILIAL", "filial")}
    # T-0036: + os 4 do Analista Comercial (contrato §10.11.1)
    assert set(FAROIS_T0036) == {"vc_saldo", "vc_markup", "vc_preco",
                                 "an_divergencias"}
    # transição T-0037: até o #169 (testes/T-0037-fretes): + o pl_fretes, opcional
    assert FAROIS_FRETES_TRANSICAO == {
        "pl_fretes": ("tabela", "Notas com frete", "UF", "uf")}
    assert FAROIS_PERMITIDOS == FAROIS_OBRIGATORIOS | set(FAROIS_FRETES_TRANSICAO)
    assert FORA not in FAROIS_PERMITIDOS


@pytest.mark.parametrize("rid", sorted(FAROIS_OBRIGATORIOS))
def test_RN_GER_006_trava_reprova_obrigatorio_faltando(rid):
    """Qualquer farol obrigatório (T-0017, T-0022, lote 2 da T-0024, T-0023 v2,
    T-0036) que sai de FAROIS_WEB reprova."""
    sem = tuple(r for r in ba.FAROIS_WEB if r != rid)
    assert f"{rid}: obrigatório e fora de FAROIS_WEB" in \
        problemas_escopo(_robo(FAROIS_WEB=sem))


def test_RN_GER_006_robo_de_verdade_passa_na_trava():
    assert problemas_escopo(ba) == []
    assert problemas_escopo(_robo()) == []


def test_RN_GER_006_trava_reprova_farol_fora_da_lista():
    p = problemas_escopo(_robo(FAROIS_WEB=tuple(ba.FAROIS_WEB) + (FORA,)))
    assert f"{FORA}: fora da lista PERMITIDA" in p


def test_RN_GER_006_trava_reprova_farol_repetido():
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


# transição T-0037: até o #169 (testes/T-0037-fretes): opcional, mas com a regra
def test_RN_GER_006_trava_reprova_fretes_pela_filial():
    """Fretes é da UF do cliente (RN-GER-006), não da filial: com o pl_fretes
    em FAROIS_WEB, a regra trocada reprova (com ou sem o robô da T-0037)."""
    farois = tuple(r for r in ba.FAROIS_WEB if r != "pl_fretes") + ("pl_fretes",)
    fontes = dict(ba._FONTE_BAIXADO_WEB,
                  pl_fretes=ba._FONTE_BAIXADO_WEB["pv_pedidos"])
    tab = dict(ba._TABELA_RECORTE_WEB, pl_fretes="Notas com frete")
    uf = dict(ba._UF_LINHAS_WEB)
    uf[("pl_fretes", "Notas com frete")] = ("FILIAL", "filial")
    p = problemas_escopo(_robo(FAROIS_WEB=farois, _FONTE_BAIXADO_WEB=fontes,
                               _TABELA_RECORTE_WEB=tab, _UF_LINHAS_WEB=uf))
    assert p == ["pl_fretes: regra de UF ('FILIAL', 'filial'), esperado "
                 "('UF', 'uf')"]
    uf[("pl_fretes", "Notas com frete")] = ("UF", "uf")
    assert problemas_escopo(_robo(FAROIS_WEB=farois, _FONTE_BAIXADO_WEB=fontes,
                                  _TABELA_RECORTE_WEB=tab,
                                  _UF_LINHAS_WEB=uf)) == []

def test_RN_GER_006_trava_reprova_tabela_de_recorte_sem_regra():
    tab = dict(ba._TABELA_RECORTE_WEB, **{FORA: "Tabela inventada"})
    assert f"{FORA}: tabela de recorte sem regra declarada" in \
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
