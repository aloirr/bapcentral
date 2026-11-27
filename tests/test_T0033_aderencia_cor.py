"""T-0033: a cor da ADERÊNCIA ao Planner (Farol de Visita, colunas de dia).

Regra (Alexandre, T-0033): verde a partir de 80%, amarelo de 50% a 79,99%,
vermelho abaixo de 50%. `relatorios_nucleo.tom_aderencia` dá o tom da linha e
`relatorios_nucleo.faixa_aderencia` dá o chip em faixa (ate, fundo, texto) com
as cores do manual da marca (docs/marca/manual.md, 4.2).

RN-VIS-001 (docs/produto/03-regras.md): verde a partir de 80%, amarelo de 50%
a 79,99%, vermelho abaixo de 50%; a mesma regra pinta a linha e cada dia.
"""
import pytest

import relatorios_nucleo as rn
from marca_manual import tokens_do_manual

# o tom da linha -> (fundo, texto) do chip, pelos tokens do manual (4.2)
TOKENS_DO_TOM = {"alerta": ("--alerta-claro", "--alerta"),
                 "atencao": ("--atencao-claro", "--atencao-texto"),
                 "ok": ("--ok-claro", "--ok")}

CASOS = [(0, "alerta"), (10, "alerta"), (49.99, "alerta"),
         (50, "atencao"), (50.01, "atencao"), (65, "atencao"),
         (79.99, "atencao"),
         (80, "ok"), (80.01, "ok"), (100, "ok"), (125, "ok")]


def _chip(pct):
    """A cor do chip para a %: a primeira faixa com pct <= ate (None = resto)."""
    for ate, fundo, texto in rn.faixa_aderencia():
        if ate is None or pct <= ate:
            return fundo.upper(), texto.upper()
    raise AssertionError(f"nenhuma faixa para {pct}")


def test_RN_VIS_001_aderencia_limites_80_e_50():
    assert (rn.ADERENCIA_VERDE, rn.ADERENCIA_AMARELO) == (80, 50)


@pytest.mark.parametrize("pct, tom", CASOS)
def test_RN_VIS_001_aderencia_tom_por_faixa(pct, tom):
    assert rn.tom_aderencia(pct) == tom


def test_RN_VIS_001_aderencia_sem_dado_fica_sem_tom():
    assert rn.tom_aderencia(None) == ""


def test_RN_VIS_001_aderencia_faixa_em_ordem_e_fechada_no_fim():
    faixas = rn.faixa_aderencia()
    assert len(faixas) == 3
    limites = [ate for ate, _f, _t in faixas]
    assert limites[-1] is None                      # o resto (>= 80) é verde
    assert limites[0] < 50 <= limites[1] < 80       # 49,99 vermelho; 79,99 amarelo
    assert limites[0] >= 49.99 and limites[1] >= 79.99


@pytest.mark.parametrize("pct, tom", CASOS)
def test_RN_VIS_001_aderencia_chip_bate_com_o_tom_e_com_o_manual(pct, tom):
    manual = tokens_do_manual()
    fundo, texto = TOKENS_DO_TOM[rn.tom_aderencia(pct)]
    assert rn.tom_aderencia(pct) == tom
    assert _chip(pct) == (manual[fundo], manual[texto])


def test_RN_VIS_001_aderencia_tres_cores_diferentes_no_chip():
    cores = {_chip(p) for p in (0, 65, 100)}
    assert len(cores) == 3


@pytest.mark.parametrize("pct, tom", [(49.99995, "alerta"), (79.99995, "atencao")])
def test_RN_VIS_001_aderencia_borda_tom_e_chip_no_mesmo_corte(pct, tom):
    """Corte único (< 50, < 80): logo abaixo do limite, o tom e o chip são os
    da faixa de baixo (o chip não pode ir para a faixa de cima sozinho)."""
    manual = tokens_do_manual()
    fundo, texto = TOKENS_DO_TOM[tom]
    assert rn.tom_aderencia(pct) == tom
    assert _chip(pct) == (manual[fundo], manual[texto])
