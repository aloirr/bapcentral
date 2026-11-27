"""T-0037 — Farol de Fretes na web (robô + faróis), dados FICTÍCIOS.

Valor × regra em todo número (desenho docs/desenho/T-0037.md, contrato
§10.11). Regras: RN-POS-007 a 010 (propostas), RN-GER-006 (fretes = UF do
cliente), RN-GER-011 (cliente sem documento), RN-GER-012 (edição só no site).

Os testes entram antes do robô e dos faróis: sem eles, pulam.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

import bap_automation as ba
import relatorios_nucleo as rn

if not hasattr(rn, "kpis_fretes") or "pl_fretes" not in getattr(
        ba, "FAROIS_WEB", ()):
    pytest.skip("robô/faróis da T-0037 ainda não entraram",
                allow_module_level=True)

RAIZ = Path(__file__).resolve().parent.parent
NOV, OUT = rn.rotulo_mes("2026-11"), rn.rotulo_mes("2026-10")
D = __import__("datetime").date
CAD = {"transportadoras": [
    {"nome": "TRANSPORTADORA FICTICIA 1", "ufs": ["PA"]},
    {"nome": "TRANSPORTADORA FICTICIA 2", "ufs": ["RR"]}]}


def _l(mes, cliente, cidade, uf, vlr, frete, etapa, transp, ate, entregue,
       chave):
    """Linha de "Notas com frete" como o rn.fretes monta (16 colunas + a
    CHAVE na 17ª célula)."""
    return [mes, D(2026, 11, 1), D(2026, 11, 2), "900001", "FILIAL FICTICIA",
            cliente, cidade, uf, vlr, frete, etapa, transp, ate, entregue,
            3 if entregue else None, "", chave]


# NOV: 4 notas (PA, PA, RR, AM); OUT: 1 nota (PA)
L_NOV = [
    _l(NOV, "000101 - CLIENTE TESTE 01 12.345.678/0001-90", "CIDADE FICT A",
       "PA", 1000.0, 50.0, "ENTREGUE", "TRANSPORTADORA FICTICIA 1",
       D(2026, 11, 10), D(2026, 11, 9), "FILIAL FICTICIA|900001|1"),
    _l(NOV, "000102 - CLIENTE TESTE 02", "CIDADE FICT B", "PA", 3000.0,
       150.0, "EM TRÂNSITO", "", D(2026, 11, 12), None,
       "FILIAL FICTICIA|900002|1"),
    _l(NOV, "000103 - CLIENTE TESTE 03", "CIDADE FICT C", "RR", 2000.0,
       100.0, "ENTREGUE", "TRANSPORTADORA FICTICIA 2", D(2026, 11, 5),
       D(2026, 11, 7), "FILIAL FICTICIA|900003|1"),
    _l(NOV, "000104 - CLIENTE TESTE 04", "CIDADE FICT D", "AM", 4000.0,
       None, rn.CONCLUIDA, "", None, None, ""),            # sem acompanhamento
]
L_OUT = [_l(OUT, "000105 - CLIENTE TESTE 05", "CIDADE FICT A", "PA", 500.0,
            25.0, "ENTREGUE", "TRANSPORTADORA FICTICIA 1", D(2026, 10, 10),
            D(2026, 10, 8), "FILIAL FICTICIA|900005|1")]
# faturado LÍQUIDO de devolução (P3 B) por (mês, UF do cliente), com os
# clientes de Manaus no AM; o líquido montado do zero: test_T0037_fretes_nucleo
FAT = {(NOV, "AM"): 40000.0, (NOV, "PA"): 8000.0, (NOV, "RR"): 5000.0,
       (OUT, "AM"): 20000.0, (OUT, "PA"): 9500.0}


def _k(kpis):
    return {k["rotulo"]: (k["valor"], k["detalhe"]) for k in kpis}


# ------------------------------------------------------------- cartões (PC)
def test_RN_POS_009_kpis_bap_inteira_valor_x_regra():
    k = _k(rn.kpis_fretes(L_NOV, FAT))
    # notas = 4 linhas do mês; valor = 1000+3000+2000+4000
    assert k["Notas com frete"] == ("4", "R$ 10.000")
    # 10.000 ÷ (40.000+8.000+5.000) = 18,87% → 19%
    assert k["% do faturado"][0] == "19%"
    # frete = 50+150+100+0 = 300; 300 ÷ 10.000 = 3%
    assert k["Frete estimado"] == ("R$ 300", "3% do valor")
    assert k["Cidades atendidas"][0] == "4"
    # entregues = com data (2) + CONCLUÍDA (1); no prazo = 1 de 2 com data
    assert k["Entregues"] == ("3", "50% no prazo")
    # sem transportadora: só a linha com CHAVE (a sem acompanhamento fica fora)
    assert k["Sem transportadora"][0] == "1"


def test_RN_POS_009_pct_faturado_no_recorte_usa_uf():
    pa = [l for l in L_NOV if l[7] == "PA"]
    k = _k(rn.kpis_fretes(pa, FAT, uf="PA"))         # o recorte informa a UF
    assert k["Notas com frete"] == ("2", "R$ 4.000")
    # 4.000 ÷ faturado do PA em NOV (8.000) = 50% (antes: 4.000 ÷ 53.000 = 8%)
    assert k["% do faturado"][0] == "50%"
    assert k["Frete estimado"] == ("R$ 200", "5% do valor")
    assert k["Entregues"] == ("1", "100% no prazo")
    assert k["Sem transportadora"][0] == "1"


def test_RN_POS_009_meses_visiveis_somam_o_faturado_dos_dois():
    ls = L_NOV + L_OUT
    # 10.500 ÷ (53.000 + 29.500) = 12,7% → 13%
    assert _k(rn.kpis_fretes(ls, FAT))["% do faturado"][0] == "13%"


def test_RN_GER_006_fretes_na_uf_do_cliente_sem_linhas():
    k = _k(rn.kpis_fretes([], FAT))
    assert k["Notas com frete"][0] == "0" and k["% do faturado"][0] == "—"


def test_RN_POS_009_bap_inteira_com_notas_de_uma_uf_so_igual_ao_antigo():
    # OUT: a única nota com frete é do PA; a BAP faturou 29.500 no mês
    # BAP inteira: 500 ÷ 29.500 = 1,7% → 2% (a UF não é adivinhada)
    assert _k(rn.kpis_fretes(L_OUT, FAT))["% do faturado"][0] == "2%"
    # recorte PA informado: 500 ÷ 9.500 = 5,3% → 5%
    assert _k(rn.kpis_fretes(L_OUT, FAT, uf="PA"))["% do faturado"][0] == "5%"


def _cartoes(ls, filtro=None):
    """O cartoes(ls, filtro) do rn.fretes: a UF vem do filtro (índice 7 ou
    "UF"); sem filtro, BAP inteira."""
    f = filtro or {}
    return rn.kpis_fretes(ls, FAT, f.get(7) or f.get("UF") or None)



# ------------------------------------------------------------- pacote (robô)
COLS = [("MÊS", "texto", True), ("DATA PED.", "dia"), ("DATA NF", "dia"),
        ("NF", "texto"), ("FILIAL", "texto"), ("CLIENTE", "texto"),
        ("CIDADE", "texto"), ("UF", "texto"), ("VLR NF", "moeda"),
        ("VLR FRETE", "moeda"), ("ETAPA", "texto"),
        ("TRANSPORTADORA", "texto"), ("ENTREGAR ATÉ", "dia"),
        ("ENTREGUE", "dia"), ("SLA ENTREGA", "int"), ("RESPONSÁVEL", "texto")]


def _ctx(tmp_path):
    return SimpleNamespace(raiz=tmp_path, hoje=D(2026, 11, 24),
                           posvenda={"entregas": []})


def _farol(tmp_path):
    """O farol como o rn.fretes devolve, com as 4 tabelas (12 meses)."""
    linhas = L_NOV + L_OUT
    cols = [rn.col(c[0], c[1], 60, oculta=len(c) > 2) for c in COLS]
    filtro_mes = {"coluna": "MÊS", "padrao": NOV}
    tabs = [rn.tabela(
        "Notas com frete", cols, [list(x) for x in linhas],
        ["ok"] * len(linhas),
        filtros=(filtro_mes, "UF", "FILIAL", "ETAPA", "TRANSPORTADORA"),
        kpis_de=_cartoes,
        edicao=rn._entrega_editavel(
            _ctx(tmp_path), len(cols), {
                "etapa": 10, "transportadora": 11, "entregue_em": 13,
                "prevista_manual": 12, "responsavel": 15}, CAD, uf_col=7,
            cidade_col=6, frete=(8, None, 9)))]
    for titulo, i in (("Por UF", 7), ("Por cidade", 6),
                      ("Por transportadora", 11)):
        g = {}
        for x in linhas:
            k = (x[0], x[i] or "(sem)")
            a = g.setdefault(k, [0, 0.0, 0.0])
            a[0] += 1
            a[1] += x[8]
            a[2] += x[9] or 0
        tabs.append(rn.tabela(
            titulo, [rn.col("MÊS", "texto", 60),
                     rn.col(titulo[4:].upper(), "texto", 60),
                     rn.col("NOTAS", "int"), rn.col("VLR NF", "moeda"),
                     rn.col("VLR FRETE", "moeda")],
            [[k[0], k[1]] + v for k, v in g.items()], filtros=(filtro_mes,)))
    return {"id": "pl_fretes", "titulo": "Fretes", "kpis": [],
            "tabelas": tabs}


def test_RN_GER_011_pacote_quatro_abas_colunas_so_o_mes(tmp_path):
    tabs, avisos = ba.tabelas_farol_web("pl_fretes", _farol(tmp_path))
    assert avisos == []
    assert [t["titulo"] for t in tabs] == [
        "Notas com frete", "Por UF", "Por cidade", "Por transportadora"]
    notas = tabs[0]
    # contrato §10.11.3: as 16 colunas, sem a CHAVE
    assert [c["nome"] for c in notas["colunas"]] == [c[0] for c in COLS]
    assert [(c["nome"], c["tipo"]) for c in notas["colunas"]] == [
        c[:2] for c in COLS]
    # P1 A: só o mês (4 de NOV; a de OUT fica fora) e o filtro MÊS oculto
    assert len(notas["linhas"]) == 4
    assert {ln[0] for ln in notas["linhas"]} == {NOV}
    assert all(len(ln) == 16 for ln in notas["linhas"])
    assert any(f.get("coluna") == "MÊS" and f.get("oculto")
               for f in notas["filtros"] if isinstance(f, dict))
    # RN-GER-011: o CNPJ fictício sai, o código do cliente fica
    cli = notas["linhas"][0][5]
    assert cli.startswith("000101") and "12.345.678" not in cli
    assert "0001-90" not in cli
    # as outras 3 abas: só o mês, com NOTAS = linhas do mês por grupo
    for t, n_nov in zip(tabs[1:], (3, 4, 3)):
        assert {ln[0] for ln in t["linhas"]} == {NOV}
        assert len(t["linhas"]) == n_nov
        assert [c["nome"] for c in t["colunas"]][2:] == [
            "NOTAS", "VLR NF", "VLR FRETE"]
    por_uf = {ln[1]: ln[2:] for ln in tabs[1]["linhas"]}
    # PA em NOV: 2 notas, 1.000+3.000, 50+150 (a de OUT fica fora)
    assert por_uf["PA"] == [2, 4000.0, 200.0]


def test_RN_POS_009_kpis_padrao_do_pacote_batem_com_o_pc(tmp_path):
    notas = ba.tabelas_farol_web("pl_fretes", _farol(tmp_path))[0][0]
    assert notas["kpis_padrao"] == rn.kpis_fretes(L_NOV, FAT)


def test_RN_GER_006_recorte_do_estado_usa_a_uf_do_cliente(tmp_path):
    rec = ba._recortes_do_farol_web("pl_fretes", _farol(tmp_path))
    assert set(rec) == {"PA", "RR", "AM"}
    pa = _k(rec["PA"]["kpis"])
    # o cartão do PA = o do PC com o filtro UF = PA (só NOV): 4.000 ÷ 8.000
    assert pa["Notas com frete"] == ("2", "R$ 4.000")
    assert pa["% do faturado"][0] == "50%"
    # o recorte AM leva o faturado do AM (40.000), não o da BAP
    assert _k(rec["AM"]["kpis"])["% do faturado"][0] == "10%"
    rr = _k(rec["RR"]["kpis"])
    # RR: 2.000 ÷ 5.000 = 40%
    assert rr["% do faturado"][0] == "40%"
    assert rr["Entregues"] == ("1", "0% no prazo")


def test_RN_POS_010_edicao_web_cinco_campos_sem_frete_real(tmp_path):
    notas = ba.tabelas_farol_web("pl_fretes", _farol(tmp_path))[0][0]
    ed = notas["edicao"]
    assert (ed["modulo"], ed["acao"]) == ("pos_venda", "Editar")
    assert [c["campo"] for c in ed["campos"]] == [
        "etapa", "transportadora", "prevista_manual", "entregue_em",
        "responsavel"]
    assert "frete_real" not in {c["campo"] for c in ed["campos"]}
    # a chave das 4 linhas do mês; a sem acompanhamento vai vazia
    assert ed["chaves"] == ["FILIAL FICTICIA|900001|1",
                            "FILIAL FICTICIA|900002|1",
                            "FILIAL FICTICIA|900003|1", ""]


def test_RN_POS_010_lugar_e_o_mesmo_das_entregas():
    lug = ba.EDICOES_WEB[("pl_fretes", "Notas com frete")]
    assert lug == ba.EDICOES_WEB[("pl_entregas", "Entregas")]
    assert (lug["modulo"], lug["aba"], lug["arquivo"]) == (
        "pos_venda", "ENTREGAS", "RELATORIOS/ACOMPANHAMENTO_POS_VENDA.xlsx")


OPCOES = {"etapa": {"ENTREGUE", "EM TRÂNSITO"},
          "transportadora": {"TRANSPORTADORA FICTICIA 1"}}


def _reg(seq, valores, chave="FILIAL FICTICIA|900001|1"):
    return {"tipo": "edicao", "seq": seq, "id": f"id-{seq}",
            "quando": "2026-11-27 09:00:00", "usuario": "admin.ficticio",
            "rid": "pl_fretes", "tabela": "Notas com frete",
            "modulo": "pos_venda", "chave": chave, "valores": valores,
            "antes": {}, "status": "pendente"}


@pytest.mark.parametrize("reg, motivo", [
    (_reg(1, {"etapa": "ENTREGUE", "entregue_em": "26/11/2026"}), ""),
    (_reg(1, {"transportadora": "OUTRA"}), "opcao"),
    (_reg(1, {"etapa": "ENTREGUE"}, chave="sem barras"), "chave"),
    (_reg(1, {"entregue_em": "2026-11-26"}), "data"),
    (_reg(1, {"responsavel": "FULANO 123.456.789-00"}), "texto"),
])
def test_RN_POS_010_validar_edicao_do_fretes(reg, motivo):
    esperado = {"": "", "opcao": ba.MOTIVO_OPCAO_WEB,
                "chave": ba.MOTIVO_CHAVE_WEB, "data": ba.MOTIVO_DATA_WEB,
                "texto": ba.MOTIVO_TEXTO_WEB}[motivo]
    assert ba.validar_edicao_web(reg, OPCOES) == esperado


def test_RN_POS_010_edicao_grava_so_acrescentando(tmp_path):
    import csv

    import pos_venda as pv

    def linhas():
        out = []
        for a in sorted((tmp_path / "RELATORIOS" / pv.PASTA_DIARIO).glob(
                "EDICOES_*.csv")):
            out.append(a.read_bytes())
        return b"".join(out)
    st, _ = ba.aplicar_edicao_web(
        tmp_path, _reg(1, {"etapa": "ENTREGUE"}), OPCOES)
    assert st == "aplicada"
    antes = linhas()
    st, _ = ba.aplicar_edicao_web(
        tmp_path, _reg(2, {"entregue_em": "26/11/2026",
                           "transportadora": "TRANSPORTADORA FICTICIA 1"}),
        OPCOES)
    assert st == "aplicada"
    depois = linhas()
    assert depois.startswith(antes)                     # só acrescenta
    novas = list(csv.reader(depois[len(antes):].decode("utf-8-sig")
                            .splitlines(), delimiter=";"))
    # 1 linha por campo, na aba ENTREGAS (a mesma do Farol de Entregas)
    assert sorted((n[3], n[5]) for n in novas if n) == [
        ("ENTREGAS", "entregue_em"), ("ENTREGAS", "transportadora")]


# ------------------------------------------------------------- PC só leitura
def test_RN_GER_012_pc_so_leitura_no_fretes():
    """bap_relatorios importa tkinter: lê o EDICAO_SO_WEB pelo código."""
    arv = ast.parse((RAIZ / "bap_relatorios.py").read_text(encoding="utf-8"))
    valor = next(ast.literal_eval(n.value) for n in ast.walk(arv)
                 if isinstance(n, ast.Assign) and any(
                     getattr(t, "id", "") == "EDICAO_SO_WEB"
                     for t in n.targets))
    assert ("pl_fretes", "Notas com frete") in valor
    assert {("pv_pedidos", "Pedidos"), ("pl_entregas", "Entregas")} <= valor


def test_RN_POS_010_frete_real_recusado_no_fretes_aceito_no_entregas():
    """P2 A: o VLR FRETE (REAL) só se edita no Farol de Entregas."""
    fr = _reg(1, {"frete_real": "120,00"})
    assert ba.validar_edicao_web(fr, OPCOES) == ba.MOTIVO_LUGAR_WEB
    ent = dict(fr, rid="pl_entregas", tabela="Entregas")
    assert ba.validar_edicao_web(ent, OPCOES) == ""
    # junto com um campo válido, a edição do Fretes também cai inteira
    mix = _reg(2, {"etapa": "ENTREGUE", "frete_real": "120,00"})
    assert ba.validar_edicao_web(mix, OPCOES) == ba.MOTIVO_LUGAR_WEB


def test_RN_POS_010_campos_lugar_web_do_fretes_sem_frete_real():
    """Contrato §10.11.4: os 5 campos do lugar, pela tabela por lugar
    (CAMPOS_LUGAR_WEB); o Entregas segue com os do módulo (com frete_real)."""
    if not hasattr(ba, "CAMPOS_LUGAR_WEB"):
        pytest.skip("CAMPOS_LUGAR_WEB ainda não entrou")
    esperado = {"etapa": "lista", "transportadora": "lista",
                "prevista_manual": "data", "entregue_em": "data",
                "responsavel": "livre"}
    assert ba.CAMPOS_LUGAR_WEB[("pl_fretes", "Notas com frete")] == esperado
    assert ba.campos_do_lugar_web("pl_fretes", "Notas com frete") == esperado
    ent = ba.campos_do_lugar_web("pl_entregas", "Entregas")
    assert ent == ba.CAMPOS_EDICAO_WEB["pos_venda"]
    assert ent["frete_real"] == "valor"
