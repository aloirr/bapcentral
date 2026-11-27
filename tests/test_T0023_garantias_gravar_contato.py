"""T-0023 (RD-0001): garantias.gravar_contato, o caminho do "Salvar contato"
do PC (RN-GER-012, P2 A).

RN-GER-012 · No PC só o CONTATO da garantia (contato_nome e contato_fone)
se edita. O gravar_contato grava só o contato que mudou, ignora as outras
chaves e não deduz status nem dt_fechamento (o gm.gravar deduz). Dado
digitado é intocável (regra 7): só acrescenta linha no diário.

Pula, com o motivo, enquanto o garantias.py não tiver o gravar_contato
(branch modulo-posvenda/T-0023-gravar-contato). Os testes do gravar valem
sempre (o gravar segue igual). Diários fictícios em tmp_path.
"""
from datetime import datetime

import pytest

import garantias as gm
from garantias_ficticias import (CONTATO, TICKET, diario_ficticio,
                                 linhas_novas, sha)

DEPOIS = datetime(2026, 11, 24, 10)

com_gravar_contato = pytest.mark.skipif(
    not hasattr(gm, "gravar_contato"),
    reason="o garantias.py deste código não tem o gravar_contato: ainda "
    "não entrou (branch modulo-posvenda/T-0023-gravar-contato)")


@com_gravar_contato
def test_RN_GER_012_campos_contato_e_o_par_do_pc():
    assert tuple(gm.CAMPOS_CONTATO) == CONTATO


@com_gravar_contato
@pytest.mark.parametrize("status, dt_fech", (
    ("FINALIZADA", ""), ("CANCELADA", ""), ("EM TRATATIVA", "10/11/2026"),
    ("ABERTO", "")))
def test_RN_GER_012_gravar_contato_so_contato(tmp_path, status, dt_fech):
    """Ignora as chaves fora do contato; FINALIZADA/CANCELADA sem
    dt_fechamento não ganha data; aberta com dt_fechamento não grava vazio;
    só acrescenta (o prefixo do arquivo com o mesmo sha)."""
    arq = diario_ficticio(tmp_path, status, dt_fech)
    b_antes = arq.read_bytes()
    antes = gm.ler(tmp_path)[TICKET]
    n = gm.gravar_contato(tmp_path, TICKET, {
        "contato_nome": "OUTRO CONTATO FICTICIO",
        "contato_fone": "(00) 00000-0002",
        # fora do contato: ignorado
        "status": "CANCELADA", "dt_fechamento": "01/01/2026",
        "cliente": "OUTRO CLIENTE FICTICIO", "qtd": "9",
        "observacao": "mexida", "campo_inexistente": "x"}, agora=DEPOIS)
    assert n == 2
    novas = linhas_novas(b_antes, arq.read_bytes())
    assert sorted(r["campo"] for r in novas) == sorted(CONTATO)
    assert {r["ticket"] for r in novas} == {TICKET}
    g = gm.ler(tmp_path)[TICKET]
    assert g["contato_nome"] == "OUTRO CONTATO FICTICIO"
    assert g["contato_fone"] == "(00) 00000-0002"
    assert g["status"] == status
    assert g.get("dt_fechamento", "") == dt_fech
    for c in gm.CAMPOS:
        if c not in CONTATO:
            assert g.get(c, "") == antes.get(c, ""), c


@com_gravar_contato
def test_RN_GER_012_gravar_contato_so_o_que_mudou(tmp_path):
    arq = diario_ficticio(tmp_path)
    b_antes = arq.read_bytes()
    n = gm.gravar_contato(tmp_path, TICKET, {
        "contato_nome": "CONTATO FICTICIO",              # igual
        "contato_fone": " (00) 00000-0002 "}, agora=DEPOIS)
    assert n == 1
    novas = linhas_novas(b_antes, arq.read_bytes())
    assert [(r["campo"], r["valor"]) for r in novas] == [
        ("contato_fone", "(00) 00000-0002")]


@com_gravar_contato
@pytest.mark.parametrize("campos", (
    {"contato_nome": "CONTATO FICTICIO", "contato_fone": "(00) 00000-0001"},
    {"status": "CANCELADA", "observacao": "mexida"},     # só fora do contato
    {}))
def test_RN_GER_012_gravar_contato_sem_mudanca_devolve_0_e_nao_grava(
        tmp_path, campos):
    arq = diario_ficticio(tmp_path, "FINALIZADA")
    sha_antes = sha(arq.read_bytes())
    assert gm.gravar_contato(tmp_path, TICKET, campos, agora=DEPOIS) == 0
    assert sha(arq.read_bytes()) == sha_antes
    assert [p.name for p in gm.pasta(tmp_path).iterdir()] == [arq.name]


@com_gravar_contato
def test_RN_GER_012_gravar_contato_no_arquivo_pedido(tmp_path):
    """O arquivo= escolhe o diário (como no gravar); o desta máquina fica
    igual."""
    arq = diario_ficticio(tmp_path)
    sha_antes = sha(arq.read_bytes())
    n = gm.gravar_contato(tmp_path, TICKET,
                          {"contato_fone": "(00) 00000-0003"},
                          arquivo="GARANTIAS_OUTRO_PC_FICTICIO.csv",
                          agora=DEPOIS)
    assert n == 1 and sha(arq.read_bytes()) == sha_antes
    assert gm.ler(tmp_path)[TICKET]["contato_fone"] == "(00) 00000-0003"


# ============== o gravar segue igual (RN-POS-005, fechamento da garantia)
@pytest.mark.parametrize("status, dt_fech, esperado", (
    ("FINALIZADA", "", "24/11/2026"),       # fechada sem data ganha hoje
    ("CANCELADA", "", "24/11/2026"),
    ("EM TRATATIVA", "10/11/2026", "")))    # reaberta: grava vazio
def test_RN_POS_005_gravar_segue_deduzindo_o_fechamento(
        tmp_path, status, dt_fech, esperado):
    diario_ficticio(tmp_path, status, dt_fech)
    n = gm.gravar(tmp_path, TICKET, {"contato_fone": "(00) 00000-0002"},
                  agora=DEPOIS)
    assert n == 2
    assert gm.ler(tmp_path)[TICKET]["dt_fechamento"] == esperado


def test_RN_POS_005_gravar_segue_gravando_todo_campo_e_ignorando_o_resto(
        tmp_path):
    arq = diario_ficticio(tmp_path)
    b_antes = arq.read_bytes()
    n = gm.gravar(tmp_path, TICKET, {
        "status": "EM TRATATIVA",                        # igual
        "cliente": "OUTRO CLIENTE FICTICIO", "qtd": "2",
        "campo_inexistente": "x"}, agora=DEPOIS)
    assert n == 2
    novas = linhas_novas(b_antes, arq.read_bytes())
    assert sorted(r["campo"] for r in novas) == ["cliente", "qtd"]
    assert gm.gravar(tmp_path, TICKET, {"qtd": "2"}, agora=DEPOIS) == 0
