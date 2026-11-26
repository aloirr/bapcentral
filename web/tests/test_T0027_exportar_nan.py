"""T-0027: NaN, inf e número gigante não viram `<v>nan</v>` (planilha inválida) no Excel das tabelas (T-0026)."""
import pytest

from app import exportar


@pytest.mark.parametrize("v", [float("nan"), float("inf"), float("-inf"), 10 ** 400])
def test_num_recusa_o_que_nao_e_numero_do_excel(v):
    assert exportar._num(v) is None


@pytest.mark.parametrize("v", [0, 1, -3.5, 12345678.9])
def test_num_aceita_numero_finito(v):
    assert exportar._num(v) == v


@pytest.mark.parametrize("v", [float("nan"), float("inf"), float("-inf")])
def test_celula_com_nan_ou_inf_vira_texto(v):
    xml = exportar._celula_xlsx("A2", v, "num")
    assert "<v>" not in xml and 't="inlineStr"' in xml
    assert f"<v>{v!r}</v>" not in xml


def test_celula_com_numero_finito_continua_numerica():
    assert "<v>1234.5</v>" in exportar._celula_xlsx("A2", 1234.5, "moeda")
    assert 't="inlineStr"' not in exportar._celula_xlsx("A2", 7, "int")


def test_planilha_inteira_com_nan_gera_zip_valido():
    import io, zipfile
    t = {"titulo": "T", "cols": [("A", "num"), ("B", "moeda")], "linhas": [[float("nan"), 1.5], [float("inf"), 2]],
         "total": None}
    z = zipfile.ZipFile(io.BytesIO(exportar.xlsx([t])))
    folha = z.read("xl/worksheets/sheet1.xml").decode()
    assert "<v>nan</v>" not in folha and "<v>inf</v>" not in folha
