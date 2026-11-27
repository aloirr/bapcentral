"""T-0023 v2, ajuste do núcleo: o % do faturado líquido (RN-GER-002), com
"—" quando o líquido fica <= 0, e o D.U. sem o hoje (RN-GER-007).

Trazido do modulo-farois (7580eb1) e revisto pelo testes: pulado, com motivo,
sem o núcleo novo. O valor x regra com o pacote real (setembro 12,0%; 06/10
com líquido negativo) mora em tests/test_T0023_valor_regra.py.
"""
from datetime import date
from pathlib import Path

import pytest

import relatorios_nucleo as rn

if not (hasattr(rn, "pct_do_liquido") and hasattr(rn, "_uteis_ate_ontem")):
    pytest.skip("núcleo da T-0023 v2 com pct_do_liquido (modulo-farois/T-0023-nucleo 7580eb1) ainda não entrou",
                allow_module_level=True)

RAIZ = Path(__file__).resolve().parent.parent


def test_RN_GER_002_pct_do_liquido_nunca_negativo():
    from painel_farol import pct_do_liquido
    assert round(pct_do_liquido(28569, 28569 / 0.12), 1) == 12.0
    assert pct_do_liquido(100, 0) is None          # liquido zero: "—"
    assert pct_do_liquido(100, -50) is None        # DEV > VND: "—"
    assert rn.pct_do_liquido is pct_do_liquido     # uma funcao so


def test_RN_GER_002_resumo_06_10_sem_percentual_negativo():
    r = rn.montar("pl_devolucoes", RAIZ, hoje=date(2026, 11, 24),
                  params={"ANO": "2026", "MÊS": "10"})
    achou = []

    def walk(o):
        if isinstance(o, dict):
            if str(o.get("titulo", "")).startswith("% devolvido do faturado"):
                achou.append(o["series"][0]["valores"])
            for x in o.values():
                walk(x)
        elif isinstance(o, (list, tuple)):
            for x in o:
                walk(x)
    walk(r)
    assert achou and all(v is None or v >= 0 for vs in achou for v in vs)


def test_RN_GER_007_ncc_ao_mudar_deixa_hoje_fora():
    import bap_dados as bd

    class C:
        hoje = date(2026, 11, 24)           # terca

        @staticmethod
        def uteis(a, b):
            return bd.dias_uteis_entre(a, b)
    f = rn._uteis_ate_ontem(C)
    assert f(date(2026, 11, 20), C.hoje) == 1      # só a segunda 23 (sem feriado na conta)
    assert bd.dias_uteis_entre(date(2026, 11, 20), C.hoje) == 2      # com o hoje seria 2
    assert f(date(2026, 11, 23), C.hoje) == 0      # movimentou ontem: 0 DU fechado
    assert f(C.hoje, C.hoje) == 0                  # movimentou hoje
