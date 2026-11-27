"""T-0023 v2, ajuste do núcleo: o % do faturado líquido (RN-GER-002), com
"—" quando o líquido fica <= 0, e o D.U. sem o hoje (RN-GER-007).

Trazido do modulo-farois (7580eb1) e revisto pelo testes. O valor x regra com o pacote real (setembro 12,0%; 06/10
com líquido negativo; nenhum % negativo em todas as séries do "% devolvido do
faturado") mora em tests/test_T0023_valor_regra.py (RD-0160).
"""
from datetime import date

import relatorios_nucleo as rn


def test_RN_GER_002_pct_do_liquido_nunca_negativo():
    from painel_farol import pct_do_liquido
    assert round(pct_do_liquido(28569, 28569 / 0.12), 1) == 12.0
    assert pct_do_liquido(100, 0) is None          # liquido zero: "—"
    assert pct_do_liquido(100, -50) is None        # DEV > VND: "—"
    assert rn.pct_do_liquido is pct_do_liquido     # uma funcao so


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
