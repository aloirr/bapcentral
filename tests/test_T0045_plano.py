"""T-0045 (modulo-robo): o `plano` do robô do PC (`visitas_maxima.plano`)
passou a tirar os dias da função única do núcleo (`vn.dias_a_baixar` sobre o
`indice_do_pc`), a mesma da nuvem (RN-VIS-002).

Trazido do modulo-robo (35a28dd) e revisto pelo testes. A regra de antes
(`dias_entre` sem os dias com `vn.dia_fechado`) fica escrita aqui, como
referência. Assim o "antes × depois" não depende de arquivo fora do
repositório. Compara 7 datas nas bases congeladas, com e sem `refazer`.

Pulado, com motivo, enquanto a branch modulo-robo/T-0045-plano não estiver no
main. Datas e arquivos fictícios na pasta temporária; as bases só são lidas.
"""
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import visitas_maxima as novo
import visitas_nucleo as vn

if not (hasattr(novo, "indice_do_pc") and hasattr(novo, "hoje_manaus")):
    pytest.skip("plano do robô da T-0045 (modulo-robo/T-0045-plano) ainda não está no main",
                allow_module_level=True)

RAIZ = Path(__file__).resolve().parent.parent


def _dias_antes(raiz, de, ate, refazer, hoje):
    """O plano de antes (main f3c4569): os dias até hoje, menos os fechados."""
    ate = min(ate, hoje)
    return [d for d in vn.dias_entre(de, ate) if refazer or not vn.dia_fechado(raiz, d)]


def test_RN_VIS_002_plano_igual_nas_bases_congeladas():
    ind = vn.indice(RAIZ)
    if not ind:
        pytest.skip("sem índice de baixas nas bases congeladas")
    ult = max(datetime.fromisoformat(v if isinstance(v, str) else v["baixado_em"]).date()
              for v in ind.values())
    for hoje in [ult + timedelta(days=i) for i in range(-3, 4)]:      # 7 datas
        de, ate = hoje - timedelta(days=10), hoje + timedelta(days=2)
        for refazer in (False, True):
            dias, _meses = novo.plano(RAIZ, de, ate, refazer, hoje)
            assert dias == _dias_antes(RAIZ, de, ate, refazer, hoje), (hoje, refazer)
            assert not dias or max(dias) <= hoje


def test_RN_VIS_002_dia_aberto_e_fechado_e_arquivo_a_mao():
    with tempfile.TemporaryDirectory() as t:
        r = Path(t)
        vn.pasta_diario(r).mkdir(parents=True)
        d1, d2, d3 = date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 22)
        for d in (d1, d2, d3):
            vn.arquivo_do_dia(r, d).write_text("x", "utf-8")
        vn.anotar_baixado(r, "20261120", datetime(2026, 11, 21, 8))    # fechado
        vn.anotar_baixado(r, "20261121", datetime(2026, 11, 21, 9))    # aberto (baixado no dia)
        # d3: sem índice, arquivo posto à mão (mtime = agora, depois de 22/11): fechado
        hoje = date(2026, 11, 27)
        dias, _m = novo.plano(r, d1, d3, False, hoje)
        assert dias == _dias_antes(r, d1, d3, False, hoje)
        assert d1 not in dias and d2 in dias and d3 not in dias
        assert novo.plano(r, d1, date(2026, 12, 5), False, hoje)[0][-1] == hoje
        assert novo.plano(r, d1, d3, True, hoje)[0] == [d1, d2, d3]


def test_RN_VIS_002_sem_hoje_usa_manaus():
    assert novo.hoje_manaus() == datetime.now(vn.FUSO_MANAUS).date()
