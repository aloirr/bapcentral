"""T-0016 - roteirizacao por lugar (NOV/26 em diante) x regras da rota.

Decisoes do Alexandre (R-20261124, sessao BAPCentral - Cowork):
- RN-ROT-002: o sabado do excedente (deposito) nao repete cliente que ja
  tem visita na mesma semana (seg a sex) com o mesmo vendedor.
- RN-ROT-003: nos N primeiros dias uteis (dias_cidade_base) so a regiao da
  base (cidade base + ate raio_base_km), tambem na roteirizacao por lugar.
  Excecoes que continuam: agenda importada e Fayga/Rodrigo (base seg/ter).

Carteira 100% ficticia (a mesma do test_rota_maxima), com parte do
Vendedor A (todo S e A e mais um pouco) movida para uma cidade a mais de 50 km da base.
"""
import collections
import datetime as dt

import pytest

import planner_nucleo as pn
from test_rota_maxima import MESES, _cfg, _clientes

REGRA_002 = "RN-ROT-002 (T-0016)"
REGRA_003 = "RN-ROT-003 (T-0016)"
VEND_A = "000015"
LONGE = ("ITACOATIARA", -3.143, -58.444)      # ~180 km de Manaus


def _gerar(cfg, cli):
    antes = (pn.HOJE_DA_ROTA[0], pn.REESCREVER_PASSADO[0],
             pn.IGNORAR_ROTA_FIXA[0])
    pn.HOJE_DA_ROTA[0] = dt.date(2026, 10, 31)
    pn.REESCREVER_PASSADO[0] = True
    pn.IGNORAR_ROTA_FIXA[0] = True
    try:
        pn.aplicar_parametros(cfg, cli)
        return pn.gerar_rota(cfg, cli)
    finally:
        (pn.HOJE_DA_ROTA[0], pn.REESCREVER_PASSADO[0],
         pn.IGNORAR_ROTA_FIXA[0]) = antes


@pytest.fixture(scope="module")
def rota_com_interior():
    mes, fer = MESES[0]
    cfg, cli = _cfg(mes, fer), _clientes()
    cfg["parametros"]["dias_cidade_base"] = 10
    cfg["parametros"]["raio_base_km"] = 50
    cfg["areas"][f"AM|{LONGE[0]}|BAIRRO 1"] = "z1"
    for i, c in enumerate(x for x in cli if x["BAIRRO"] == "BAIRRO 1"):
        if c["CURVA_RECEITA"] in ("S", "A") or i % 4 == 1:
            c.update(CIDADE=LONGE[0], AREA=f"AM|{LONGE[0]}|BAIRRO 1",
                     LATITUDE=LONGE[1] + (i % 7) / 1000,
                     LONGITUDE=LONGE[2] + (i % 5) / 1000)
    return cfg, cli, _gerar(cfg, cli)


def _repetidos_no_sabado(rota):
    semana = collections.defaultdict(set)
    for r in rota:
        semana[(r["COD_VENDEDOR"], r["CHAVE_CLIENTE"],
                r["DATA"].isocalendar()[:2])].add(r["DATA"].weekday())
    return [k for k, ds in semana.items() if 5 in ds and ds - {5, 6}]


def test_RN_ROT_002_sabado_do_excedente_nao_repete_a_semana(
        rota_com_interior):
    cfg, _cli, rota = rota_com_interior
    assert any(r["DATA"].weekday() == 5 for r in rota), \
        f"{REGRA_002}: o cenario precisa ter sabado do excedente"
    rep = _repetidos_no_sabado(rota)
    assert not rep, f"{REGRA_002}: {len(rep)} cliente(s) no sabado e na semana"


def test_RN_ROT_003_cidade_base_vale_mais_que_o_lugar(rota_com_interior):
    cfg, _cli, rota = rota_com_interior
    dias = pn.dias_do_mes(cfg["mes"], cfg.get("feriados") or [], True)
    restr = pn.dias_da_cidade_base(dias, cfg["parametros"])
    v = next(p for p in pn.vendedores(cfg) if p["cod_protheus"] == VEND_A)
    na_base = pn.regiao_da_base(v, cfg["parametros"])
    dele = [r for r in rota if r["COD_VENDEDOR"] == VEND_A]
    longe = [r for r in dele if r["CIDADE"] == LONGE[0]]
    assert len(restr) == 10 and longe, \
        f"{REGRA_003}: o cenario precisa de visita na cidade longe"
    fora = [r for r in dele if r["DATA"] in restr and not na_base(r)]
    assert not fora, (f"{REGRA_003}: {len(fora)} visita(s) fora da regiao "
                      f"da base nos 10 primeiros dias uteis")
    assert any(r["DATA"] not in restr for r in longe), \
        f"{REGRA_003}: a cidade longe continua com visita depois da base"
