"""T-0004 - o smoke_processos vira bloqueante com a lista de falhas
conhecidas do agente testes (tests/conferir_smoke.py)."""
from conferir_smoke import conferir

RESUMO = "\n" + "=" * 62 + "\n"


def test_smoke_ok_passa():
    assert conferir("...\n" + RESUMO + "OK - Farol, pos-venda, TABELA_BAP, "
                    "BAP Central\n") == (True, [])


def test_so_falha_conhecida_passa():
    txt = (RESUMO + "1 FALHA(S):\n  - 281336 celulas conferidas contra o "
           "Excel: 66 diferenca(s)\n")
    assert conferir(txt) == (True, [])


def test_falha_nova_bloqueia():
    txt = (RESUMO + "2 FALHA(S):\n  - 281336 celulas conferidas contra o "
           "Excel: 66 diferenca(s)\n  - Com as regras novas: nunca 2x na "
           "semana e o teto do dia vale\n")
    ok, novas = conferir(txt)
    assert not ok and novas == ["Com as regras novas: nunca 2x na semana e "
                                "o teto do dia vale"]


def test_smoke_quebrado_bloqueia():
    ok, novas = conferir("Traceback (most recent call last):\n  ...\n")
    assert not ok and "parou antes do resumo" in novas[0]
