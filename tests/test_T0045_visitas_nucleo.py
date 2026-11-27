"""T-0045: as funções puras do visitas_nucleo (Visitas no Render).

Trazido do modulo-rota (branch modulo-rota/T-0045-visitas-nucleo) e revisto
pelo testes. Regras: RN-VIS-002 (o dia fecha pela hora da baixa, em Manaus;
vale a baixa mais nova entre a nuvem e o PC) e RN-VIS-007 (o Espelho vai sem
dado pessoal: só as colunas permitidas; o achado leva o tipo, nunca o valor).

Pulado, com motivo, enquanto a branch da rota não estiver no main. Dados 100%
fictícios; os arquivos vão para pastas temporárias.
"""
from datetime import date, datetime

import pytest

import visitas_nucleo as vn

_FUNCOES = ("juntar_baixado", "dia_fechado_no_indice", "dias_a_baixar", "achar_dado_pessoal",
            "filtrar_espelho", "anotar_baixado", "ESPELHO_PERMITIDAS")
if not all(hasattr(vn, n) for n in _FUNCOES):
    pytest.skip("rota da T-0045 (modulo-rota/T-0045-visitas-nucleo) ainda não está no main",
                allow_module_level=True)


def test_RN_VIS_002_juntar_baixado_vale_a_maior():
    nuvem = {"20261126": "2026-11-27T06:00:00-04:00"}
    pc = {"20261126": "2026-11-27T07:12:03-04:00"}
    r = vn.juntar_baixado(nuvem, pc)
    assert r["20261126"]["origem"] == "pc"
    assert r["20261126"]["baixado_em"] == "2026-11-27T07:12:03-04:00"
    r2 = vn.juntar_baixado(pc, nuvem)  # nuvem aqui e a de 07:12
    assert r2["20261126"]["origem"] == "nuvem"


def test_RN_VIS_002_juntar_baixado_fuso_e_empate_e_um_lado_so():
    # 11:00Z = 07:00 Manaus; 07:00 sem fuso = 07:00 Manaus: empate -> nuvem
    r = vn.juntar_baixado({"20261125": "2026-11-26T11:00:00+00:00"},
                          {"20261125": "2026-11-26T07:00:00",
                           "20261124": "2026-11-25T08:00:00"})
    assert r["20261125"]["origem"] == "nuvem"
    assert r["20261124"] == {"baixado_em": "2026-11-25T08:00:00-04:00",
                             "origem": "pc"}


def test_RN_VIS_002_erros_e_refeito_so_com_origem_nuvem():
    nuvem = {"20261125": {"baixado_em": "2026-11-26T06:00:00-04:00",
                          "erros_vendedor": 2, "refeito": False}}
    r = vn.juntar_baixado(nuvem, {})
    assert r["20261125"]["erros_vendedor"] == 2
    r = vn.juntar_baixado(nuvem, {"20261125": "2026-11-26T09:00:00-04:00"})
    assert r["20261125"]["origem"] == "pc"
    assert "erros_vendedor" not in r["20261125"]


def test_RN_VIS_002_dia_fecha_pela_hora_da_baixa_nao_da_importacao():
    ind = {"20261126": {"baixado_em": "2026-11-26T23:00:00-04:00"},
           "20261125": {"baixado_em": "2026-11-26T00:10:00-04:00"}}
    assert not vn.dia_fechado_no_indice(ind, date(2026, 11, 26))
    assert vn.dia_fechado_no_indice(ind, date(2026, 11, 25))
    # 00:30 UTC do dia 27 ainda e 20:30 do dia 26 em Manaus: nao fecha o 26
    assert not vn.dia_fechado_no_indice(
        {"20261126": "2026-11-27T00:30:00+00:00"}, date(2026, 11, 26))


def test_RN_VIS_002_dias_a_baixar_pula_fechado_e_nunca_passa_de_hoje():
    ind = {"20261124": "2026-11-25T06:00:00-04:00",
           "20261125": "2026-11-25T23:00:00-04:00"}
    hoje = date(2026, 11, 27)
    r = vn.dias_a_baixar(ind, date(2026, 11, 23), date(2026, 12, 5), hoje,
                         False)
    assert date(2026, 11, 24) not in r
    assert date(2026, 11, 25) in r          # baixado no proprio dia: aberto
    assert max(r) == hoje and date(2026, 11, 23) in r


def test_RN_VIS_002_dias_a_baixar_refazer_traz_todos():
    ind = {"20261124": "2026-11-25T06:00:00-04:00"}
    r = vn.dias_a_baixar(ind, date(2026, 11, 23), date(2026, 11, 26),
                         date(2026, 11, 27), True)
    assert r == [date(2026, 11, 23 + i) for i in range(4)]
    assert vn.dias_a_baixar(None, date(2026, 11, 26), date(2026, 11, 25),
                            date(2026, 11, 27)) == []


def test_RN_VIS_002_fechados_pc_entra_no_indice_e_a_nuvem_nao_baixa_de_novo():
    ind = vn.juntar_baixado({}, {"20261124": "2026-11-25T07:00:00-04:00"})
    r = vn.dias_a_baixar(ind, date(2026, 11, 24), date(2026, 11, 26),
                         date(2026, 11, 27), False)
    assert date(2026, 11, 24) not in r and date(2026, 11, 25) in r


def test_RN_VIS_007_achar_dado_pessoal_tipos():
    f = vn.achar_dado_pessoal
    assert f("a@b.com") == "email"
    assert f("12.345.678/0001-90") == "cnpj"
    assert f("12345678000190") == "cnpj"
    assert f("123.456.789-09") == "cpf"
    assert f("12345678909") == "cpf"
    assert f("(92) 99123-4567") == "telefone"
    assert f("Cliente Fulano LTDA") is None
    assert f("[removido]") is None and f(None) is None and f("") is None


def test_RN_VIS_007_achar_dado_pessoal_formato():
    f = vn.achar_dado_pessoal
    assert f("123456", "codigo") is None
    assert f("12345", "codigo") == "formato"
    assert f("08:30:00", "hora") is None
    assert f("abc", "hora") == "formato"
    assert f("S", "sn") is None and f("X", "sn") == "formato"
    assert f("12 / 80%", "numero") is None
    assert f("1.234,56", "numero") is None
    assert f("texto livre", "numero") == "formato"
    assert f("1000", "ord") == "formato"
    assert f(12, "ord") is None
    assert f("qualquer coisa", "texto") is None


def test_RN_VIS_007_achar_nao_devolve_o_valor():
    assert vn.achar_dado_pessoal("x@y.com") in {
        "email", "cnpj", "cpf", "telefone", "formato"}


def test_RN_VIS_007_permitidas_batem_com_as_tabelas_do_ler_espelho():
    cab = set(vn.ESPELHO_PERMITIDAS["cabecalho"])
    assert cab == set(vn._ROTULOS_ESPELHO)
    col = set(vn.ESPELHO_PERMITIDAS["colunas"])
    assert col <= set(vn._COLUNAS_ESPELHO)
    assert set(vn._COLUNAS_ESPELHO) - col == {"KM DIST", "BONIF",
                                             "OBSERVACAO"}


def test_RN_VIS_007_filtrar_espelho_tira_colunas_e_ler_espelho_igual(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["RCA:", "000123 FULANO"])
    ws.append(["Periodo:", "16/10/2026 à 18/10/2026"])
    ws.append(["Telefone do vendedor:", "(92) 99123-4567"])
    ws.append(["DATA", "ORD PREV", "INICIO", "CODIGO", "CLIENTE", "KM DIST",
               "OBSERVACAO", "JUSTIFICATIVA"])
    ws.append(["10/16/2026", 1, "08:00:00", "123456", "LOJA X 11222333000144",
               "5", "obs", "ligar 92991234567"])
    org, dst = tmp_path / "o.xlsx", tmp_path / "d.xlsx"
    wb.save(org)
    rel = vn.filtrar_espelho(org, dst, limpar_cliente=lambda v: "LOJA X",
                             limpar_texto=lambda v: "[removido]")
    assert "KM DIST" in rel["colunas_fora"] and "OBSERVACAO" in rel[
        "colunas_fora"]
    assert rel["limpos"] == {"CLIENTE": 1, "JUSTIFICATIVA": 1}
    assert rel["achados"] == []
    d = vn.ler_espelho(dst)
    o = vn.ler_espelho(org)
    assert d is not None and o is not None
    assert len(d["clientes"]) == len(o["clientes"]) == 1
    assert d["clientes"][0]["codigo"] == o["clientes"][0]["codigo"]
    assert d["clientes"][0].get("obs") in (None, "")
    assert d["clientes"][0]["cliente"] == "LOJA X"
    assert "9123" not in str(d)


def test_RN_VIS_007_filtrar_espelho_acha_dado_que_sobrou(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["RCA:", "000123 FULANO"])
    ws.append(["DATA", "CODIGO", "CLIENTE", "ENDERECO"])
    ws.append(["10/16/2026", "123456", "LOJA", "tel 92991234567 e a@b.com"])
    org, dst = tmp_path / "o.xlsx", tmp_path / "d.xlsx"
    wb.save(org)
    rel = vn.filtrar_espelho(org, dst, limpar_cliente=str,
                             limpar_texto=str)
    tipos = {(a["coluna"], a["tipo"]) for a in rel["achados"]}
    assert ("ENDERECO", "email") in tipos
    assert all("valor" not in a for a in rel["achados"])


def test_RN_VIS_007_colunas_fora_so_leva_nomes_nunca_valor(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["RCA:", "000123 FULANO"])
    ws.append(["FULANO DE TAL 12345678901", "Total geral 99"])
    ws.append(["Telefone 92991234567:", "x"])
    ws.append(["DATA", "CODIGO", "CLIENTE", "KM DIST"])
    ws.append(["10/16/2026", "123456", "LOJA", "5"])
    org, dst = tmp_path / "o.xlsx", tmp_path / "d.xlsx"
    wb.save(org)
    rel = vn.filtrar_espelho(org, dst, limpar_cliente=str, limpar_texto=str)
    txt = str(rel)
    assert "FULANO DE TAL" not in txt and "12345678901" not in txt
    assert "92991234567" not in txt
    assert "KM DIST" in rel["colunas_fora"]


def test_RN_VIS_007_rodape_no_meio_da_lista_nao_gera_falso_achado(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["RCA:", "000123 FULANO"])
    ws.append(["DATA", "CODIGO", "CLIENTE"])
    ws.append(["10/16/2026", "123456", "LOJA A"])
    ws.append(["Pagina 1 de 3", None, None])
    ws.append([None, "Total: 12", None])
    ws.append(["10/16/2026", "654321", "LOJA B"])
    org, dst = tmp_path / "o.xlsx", tmp_path / "d.xlsx"
    wb.save(org)
    rel = vn.filtrar_espelho(org, dst, limpar_cliente=str, limpar_texto=str)
    assert rel["achados"] == []
    # as duas lojas, na ordem, dos dois lados do rodapé (o "or True" do
    # original não conferia nada)
    d = vn.ler_espelho(dst)
    assert [c["codigo"] for c in d["clientes"]] == ["123456", "654321"]


def test_RN_VIS_007_cpf_e_telefone_como_numero_em_coluna_de_texto():
    assert vn.achar_dado_pessoal(12345678909, "texto") == "cpf"
    assert vn.achar_dado_pessoal(92991234567, "texto") == "cpf"
    assert vn.achar_dado_pessoal(12345, "texto") is None
    assert vn.achar_dado_pessoal(12345678000190, "texto") == "cnpj"


def test_RN_VIS_002_dia_fechado_usa_a_regra_unica(tmp_path):
    arq = vn.arquivo_do_dia(tmp_path, date(2026, 11, 25))
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text("x", "utf-8")
    vn.anotar_baixado(tmp_path, "20261125",
                      datetime(2026, 11, 25, 22, 0))
    assert not vn.dia_fechado(tmp_path, date(2026, 11, 25))
    vn.anotar_baixado(tmp_path, "20261125", datetime(2026, 11, 26, 6, 0))
    assert vn.dia_fechado(tmp_path, date(2026, 11, 25))
