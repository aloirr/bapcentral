"""T-0023 v2 (robo): Garantias, Devolucoes e NCC no site, edicao so do admin.

Trazido do modulo-robo e revisto pelo testes (nomes com a RN certa, fixtures
ficticias, skip sem o robo da T-0023). O teste de dado pessoal do pacote mora
em tests/test_T0023_valor_regra.py, sem a isencao larga que estava aqui.

Regras: RN-GER-006 (estado = FILIAL da nota; Garantias sem estado), RN-GER-011 (CONTATO CLIENTE e
documentos fora; "[removido]" nunca volta ao PC), RN-GER-012 (a edicao chega ao PC pela MESMA funcao
da tela, so acrescentando linha; a linha nova da garantia, contrato 10.9.2), RN-GER-014 (abas),
RN-POS-005 (DT. FECHAMENTO = solicitacao + 15 DU; o prazo igual ao padrao fica em branco).
O transporte (cortes e teto) nao e regra de negocio: os nomes citam a ADR 0003 (contrato 10.10.4).

Bases congeladas do repositorio, hoje=24/11/2026, params ANO=2026 MES=11. Nada e gravado nelas: a
gravacao vai para pastas temporarias com dados ficticios.
"""
import csv
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import bap_automation as ba

if "pl_ncc" not in getattr(ba, "FAROIS_WEB", ()) or not hasattr(ba, "CAMPOS_LUGAR_WEB"):
    pytest.skip("robô da T-0023 v2 (modulo-robo/T-0023-robo) ainda não entrou", allow_module_level=True)

import garantias as gm  # noqa: E402
import ncc_controle as nc  # noqa: E402
import pos_venda as pv  # noqa: E402
import relatorios_nucleo as rn  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent if (Path(__file__).resolve().parent.parent / "bap_automation.py").exists() \
    else Path.cwd()
HOJE = date(2026, 11, 24)
TRES = ("pl_garantias", "pl_devolucoes", "pl_ncc")
TOKEN = "token-ficticio-t23"
BASE = "https://web.exemplo.test"

# o que cada tabela tem de ter (contrato 10.10.2): (colunas no pacote, ocultas)
CONTRATO = {
    ("pl_garantias", "Garantias"): (23, 11),
    ("pl_garantias", "Histórico de compra"): (19, 0),
    ("pl_garantias", "Por produto"): (6, 0),
    ("pl_garantias", "Status x resultado"): (5, 0),
    ("pl_devolucoes", "Devoluções"): (18, 0),
    ("pl_devolucoes", "Por motivo"): (4, 0),
    ("pl_devolucoes", "Por vendedor (12 meses)"): (5, 0),
    ("pl_devolucoes", "Por cliente (12 meses)"): (3, 0),
    ("pl_devolucoes", "Por produto (12 meses)"): (4, 0),
    ("pl_ncc", "NCC pendentes"): (22, 1),
    ("pl_ncc", "Por cliente"): (14, 1),
    ("pl_ncc", "Por filial"): (9, 0),
    ("pl_ncc", "Por vendedor"): (9, 0),
    ("pl_ncc", "Por supervisor"): (9, 0),
}
@pytest.fixture(scope="module")
def farois():
    pac = ba.montar_pacote_web(
        {r: rn.montar(r, RAIZ, hoje=HOJE, params=ba.params_farol_web(r, 2026, 11)) for r in TRES},
        2026, 11, raiz=RAIZ)
    return pac["relatorios"]


@pytest.fixture(scope="module")
def pcs():
    return {r: rn.montar(r, RAIZ, hoje=HOJE, params=ba.params_farol_web(r, 2026, 11)) for r in TRES}


def _tab(farois, rid, titulo):
    return next(t for t in farois[rid]["tabelas"] if t["titulo"] == titulo)


# ------------------------------------------------------------------ os 3 faróis no pacote
def test_RN_GER_014_os_tres_farois_entram_no_FAROIS_WEB_com_as_abas_do_contrato(farois):
    assert set(TRES) <= set(ba.FAROIS_WEB)
    assert set(TRES) <= set(farois)
    for rid in TRES:
        assert [t["titulo"] for t in farois[rid]["tabelas"]] == list(ba._ABAS_TABELAS_WEB[rid])
        assert farois[rid]["forma"] == "farol"


@pytest.mark.parametrize("rid,titulo", sorted(CONTRATO))
def test_RN_GER_014_colunas_do_contrato_10_10_2(farois, rid, titulo):
    n, ocultas = CONTRATO[(rid, titulo)]
    t = _tab(farois, rid, titulo)
    assert len(t["colunas"]) == n
    assert sum(1 for c in t["colunas"] if c.get("oculta")) == ocultas
    assert all(len(ln) == n for ln in t["linhas"])


def test_RN_GER_011_contato_cliente_e_telefone_nunca_vao(farois):
    nomes = {c["nome"] for rid in TRES for t in farois[rid]["tabelas"] for c in t["colunas"]}
    assert "CONTATO CLIENTE" not in nomes and "TELEFONE" not in nomes
    for rid in TRES:
        txt = ba._json_farol_web(farois[rid]).decode("utf-8")
        for chave in ('"garantia"', '"detalhe_pedido"', '"campanha_export"', '"editar"', "CONTATO CLIENTE"):
            assert chave not in txt


def test_RN_GER_011_nome_do_cliente_sai_limpo_nas_colunas_do_contrato(pcs):
    assert ba._COLUNAS_LIMPAS_WEB[("pl_ncc", "NCC pendentes")] == {"NOME": "sem_documento"}
    assert ba._COLUNAS_LIMPAS_WEB[("pl_garantias", "Garantias")] == {"CLIENTE": "nome_sem_contato"}
    assert ba._COLUNAS_LIMPAS_WEB[("pl_devolucoes", "Devoluções")] == {"CLIENTE": "cliente_sem_documento"}
    # texto livre limpo (D6 A)
    assert {"PENDÊNCIAS", "RETORNO DO CLIENTE", "RECLAMAÇÃO", "OBSERVAÇÃO", "MOTIVO"} <= ba._COLUNAS_TEXTO_LIVRE_WEB


def test_RN_GER_011_texto_livre_da_garantia_vem_sem_contato():
    pc = {"titulo": "Garantias", "colunas": [{"nome": "TICKET", "tipo": "texto"},
                                             {"nome": "OBSERVAÇÃO", "tipo": "texto", "oculta": True}],
          "linhas": [["1", "ligar 92 99123-4567 ou x@y.com"]], "tons": [""]}
    funcs = ba._funcoes_limpeza_web()
    assert "[removido]" in funcs["texto_sem_contato"](pc["linhas"][0][1])
    assert "99123" not in funcs["texto_sem_contato"](pc["linhas"][0][1])


def test_RN_GER_006_estado_pela_FILIAL_da_nota_e_garantias_sem_estado(farois, pcs):
    for rid, titulo in (("pl_devolucoes", "Devoluções"), ("pl_ncc", "NCC pendentes")):
        t = _tab(farois, rid, titulo)
        pc = next(x for x in pcs[rid]["tabelas"] if x["titulo"] == titulo)
        ix = [c["nome"] for c in pc["colunas"]].index("FILIAL")
        esperado = [ba._uf_valida_web(rn.uf_do_nome_da_filial(ln[ix])) for ln in pc["linhas"]]
        assert t["uf_linhas"] == esperado and any(esperado)
        assert farois[rid]["recortes"]
    assert not any("uf_linhas" in t for t in farois["pl_garantias"]["tabelas"])
    assert not farois["pl_garantias"]["recortes"]
    assert any("Sem filtro por estado" in a for a in farois["pl_garantias"]["avisos"])
    assert "uf_linhas" not in _tab(farois, "pl_ncc", "Por cliente")      # sem FILIAL: sem estado


def test_RN_GER_014_ncc_sem_painel_no_pc_os_graficos_viram_barras(pcs, farois):
    assert not (pcs["pl_ncc"].get("painel") or {}).get("blocos")
    blocos = farois["pl_ncc"]["painel"]["blocos"]
    assert blocos and all(b["tipo"] == "barras" for b in blocos)
    assert len(blocos) == len([g for g in pcs["pl_ncc"]["graficos"] if g.get("rotulos")])


# ------------------------------------------------------------------ cortes (10.10.4)
def test_ADR0003_10_10_4_garantias_corta_o_historico_primeiro_e_depois_as_tabelas(farois):
    f = farois["pl_garantias"]
    hist = _tab(farois, "pl_garantias", "Histórico de compra")
    assert len(hist["linhas"]) > 4000
    bruto = len(ba._json_farol_web(f))
    sem = ba._cortar_farol_web("pl_garantias", f, teto_mb=(bruto - 1000) / 1048576)
    assert [t["titulo"] for t in sem["tabelas"]] == ["Garantias", "Por produto", "Status x resultado"]
    assert any(a.startswith(ba.AVISO_ABAS_FORA.split("{lista}")[0]) and "Histórico de compra" in a
               for a in sem["avisos"])
    nada = ba._cortar_farol_web("pl_garantias", f, teto_mb=0.001)
    assert "tabelas" not in nada and any("Garantias" in a and "Histórico de compra" in a for a in nada["avisos"])
    assert len(f["tabelas"]) == 4                                        # o de entrada nao muda


def test_ADR0003_10_10_4_devolucoes_e_ncc_seguem_a_linha_dos_outros_farois():
    assert ba._CORTES_FAROL_WEB.get("pl_devolucoes") is None and ba._CORTES_FAROL_WEB.get("pl_ncc") is None
    assert ba._CORTES_FAROL_WEB["pl_garantias"] == ("historico_fora", "tabelas")


def test_ADR0003_10_10_4_tamanho_real_dos_tres_farois_cabe_no_teto(farois):
    tam = {r: len(ba._json_farol_web(farois[r])) for r in TRES}
    assert all(v < ba.WEB_FAROL_TETO_MB * 1048576 for v in tam.values())
    assert 1_000_000 < tam["pl_garantias"] < 1_500_000                   # ~1,25 MB: o Historico
    assert tam["pl_devolucoes"] < 100_000 and tam["pl_ncc"] < 60_000


# ------------------------------------------------------------------ a especificacao `edicao`
def _ed(farois, rid, titulo):
    return _tab(farois, rid, titulo)["edicao"]


def test_RN_GER_012_edicao_da_garantia_14_campos_novo_max_multilinha_e_padroes(farois):
    ed = _ed(farois, "pl_garantias", "Garantias")
    assert ed["modulo"] == "garantias" and ed["novo"] == {"rotulo": "Nova garantia"}
    assert "novo_web" not in ed
    c = {x["campo"]: x for x in ed["campos"]}
    assert len(c) == 14 <= 16 and "contato_nome" not in c and "contato_fone" not in c
    for campo in ("reclamacao", "pendencias", "retorno_cliente", "observacao"):
        assert c[campo]["max"] == rn.max_texto_edicao("garantias", campo) == 600
        assert c[campo]["multilinha"] is True and c[campo]["caixa"] is True
    assert c["ticket"]["padrao"] == gm.novo_ticket(RAIZ)
    assert c["dt_solicitacao"]["padrao"] == "@hoje" and c["dt_solicitacao"]["opcoes"] == []
    assert (c["status"]["padrao"], c["resultado"]["padrao"]) == ("ABERTO", "PENDENTE")
    assert c["status"]["opcoes"] == list(gm.STATUS) and c["resultado"]["opcoes"] == list(gm.RESULTADOS)
    assert all("max" not in c[k] for k in ("ticket", "qtd", "cod_cliente"))   # sem max = 60
    t = _tab(farois, "pl_garantias", "Garantias")
    nomes = [x["nome"] for x in t["colunas"]]
    assert all(x["coluna"] in nomes for x in ed["campos"])                  # as 3 colunas novas do nucleo
    assert len(ed["chaves"]) == len(t["linhas"])


def test_RN_GER_012_so_a_garantia_aceita_linha_nova(farois):
    assert "novo" not in _ed(farois, "pl_ncc", "NCC pendentes")
    assert "novo" not in _ed(farois, "pl_devolucoes", "Devoluções")


def test_RN_GER_012_edicao_da_ncc_e_data_livre(farois):
    ed = _ed(farois, "pl_ncc", "NCC pendentes")
    c = {x["campo"]: x for x in ed["campos"]}
    assert ed["modulo"] == "ncc" and set(c) == {"status", "dt_mov"}
    assert c["dt_mov"]["tipo"] == "data" and c["dt_mov"]["opcoes"] == []      # data livre
    assert c["status"]["tipo"] == "lista" and "NO TÍTULO" in c["status"]["opcoes"]
    assert all(k.count("|") == 3 for k in ed["chaves"] if k)


def test_RN_GER_012_edicao_da_devolucao_so_os_campos_do_lugar(farois):
    ed = _ed(farois, "pl_devolucoes", "Devoluções")
    c = {x["campo"]: x for x in ed["campos"]}
    assert ed["modulo"] == "pos_venda"
    assert set(c) == {"etapa", "motivo", "autorizado_por", "recebida_em", "credito", "credito_em", "responsavel"}
    assert c["etapa"]["opcoes"] == list(pv.ETAPAS_DEVOLUCAO)
    assert "transportadora" not in c and "frete_real" not in c
    assert all(k.count("|") == 2 for k in ed["chaves"] if k)


def test_RN_GER_012_o_max_vem_do_nucleo_e_a_spec_diferente_nao_vai():
    ed_pc = {"arquivo": "RELATORIOS/_GARANTIAS", "aba": "", "modulo": "garantias", "chave": 0,
             "novo_web": {"rotulo": "Nova garantia"},
             "campos": [{"campo": "observacao", "rotulo": "OBSERVAÇÃO", "opcoes": [], "livre": True,
                         "col": 1, "mantem_caixa": True, "multilinha": True, "max": 599}]}
    linhas = [["G-1", ""]]
    pc = [{"nome": "TICKET"}, {"nome": "OBSERVAÇÃO"}]
    with pytest.raises(ValueError):
        ba.edicao_web("pl_garantias", "Garantias", ed_pc, linhas, pc, ["TICKET", "OBSERVAÇÃO"])
    ed_pc["campos"][0]["max"] = rn.max_texto_edicao("garantias", "observacao")
    ed = ba.edicao_web("pl_garantias", "Garantias", ed_pc, linhas, pc, ["TICKET", "OBSERVAÇÃO"])
    assert ed["campos"][0]["max"] == 600 and ed["novo"] == {"rotulo": "Nova garantia"}


# ------------------------------------------------------------------ validar_edicao_web
OPC = {"ncc.status": {"NO TÍTULO", "REEMBOLSADO"}, "devolucoes.etapa": set(pv.ETAPAS_DEVOLUCAO),
       "devolucoes.motivo": set(pv.MOTIVOS_DEVOLUCAO), "devolucoes.credito": set(pv.FORMAS_CREDITO),
       "garantias.status": set(gm.STATUS), "garantias.resultado": set(gm.RESULTADOS),
       "etapa": set(pv.ETAPAS_ENTREGA), "_hoje": HOJE}


def _g(seq, valores, chave="G-9001", novo=False, antes=None):
    r = {"tipo": "edicao", "seq": seq, "id": f"id-{seq}", "usuario": "admin.ficticio", "rid": "pl_garantias",
         "tabela": "Garantias", "modulo": "garantias", "chave": chave, "valores": valores,
         "antes": antes if antes is not None else {}, "status": "pendente"}
    if novo:
        r["novo"] = True
    return r


def _n(seq, valores, chave="FIL|PR|123|1"):
    return {"tipo": "edicao", "seq": seq, "id": f"id-{seq}", "usuario": "admin.ficticio", "rid": "pl_ncc",
            "tabela": "NCC pendentes", "modulo": "ncc", "chave": chave, "valores": valores, "antes": {},
            "status": "pendente"}


def _d(seq, valores, chave="FILIAL FICTICIA|900001|1"):
    return {"tipo": "edicao", "seq": seq, "id": f"id-{seq}", "usuario": "admin.ficticio", "rid": "pl_devolucoes",
            "tabela": "Devoluções", "modulo": "pos_venda", "chave": chave, "valores": valores, "antes": {},
            "status": "pendente"}


LONGO = "a" * 600
CASOS = [
    (_g(1, {"status": "FINALIZADA", "observacao": "Peça chegou\nsegunda linha"}), ""),
    (_g(2, {"observacao": LONGO}), ""),
    (_g(3, {"observacao": LONGO + "a"}), ba.motivo_texto_web(600)),
    (_g(4, {"cod_cliente": "a" * 61}), ba.motivo_texto_web(60)),
    (_g(5, {"observacao": "tel 92 99123-4567"}), ba.motivo_texto_web(600)),
    (_g(6, {"observacao": "cliente x@y.com"}), ba.motivo_texto_web(600)),
    (_g(7, {"observacao": "CNPJ 12.345.678/0001-90"}), ba.motivo_texto_web(600)),
    (_g(8, {"observacao": "[removido]"}), ba.MOTIVO_REMOVIDO_WEB),
    (_g(9, {"pendencias": "ligar [removido] amanhã"}), ba.MOTIVO_REMOVIDO_WEB),
    (_g(10, {"cod_produto": "a\nb"}), ba.motivo_texto_web(60)),       # quebra so no texto longo
    (_g(11, {"observacao": "a\x07b"}), ba.motivo_texto_web(600)),
    (_g(12, {"status": "OUTRO"}), ba.MOTIVO_OPCAO_WEB),
    (_g(13, {"resultado": "TALVEZ"}), ba.MOTIVO_OPCAO_WEB),
    (_g(14, {"dt_retorno": "24/11/2026"}), ""),
    (_g(15, {"dt_retorno": "31/02/2026"}), ba.MOTIVO_DATA_WEB),                # data livre: existe no calendario
    (_g(16, {"dt_retorno": "31/12/2019"}), ba.MOTIVO_DATA_WEB),               # antes de 01/01/2020
    (_g(17, {"dt_retorno": "24/11/2027"}), ""),                                # hoje + 1 ano
    (_g(18, {"dt_retorno": "25/11/2027"}), ba.MOTIVO_DATA_WEB),
    (_g(19, {"contato_fone": "1"}), ba.MOTIVO_LUGAR_WEB),                      # contato so no PC (P2 A)
    (_g(20, {"ticket": "G;1"}), ba.MOTIVO_VALOR_WEB),
    (_g(21, {"ticket": "G-0099"}), ""),
    (_g(22, {"observacao": "x"}, chave="NOVO-3F9A01C2"), ""),                # NOVO sem o `novo`: e so uma chave
    (_g(23, {"ticket": "G-0001"}, chave="NOVO-3F9A01C2", novo=True), ""),
    (_g(24, {"ticket": "G-0001"}, chave="NOVO-3f9a01c2", novo=True), ba.MOTIVO_CHAVE_WEB),
    (_g(25, {"ticket": "G-0001"}, chave="G-9001", novo=True), ba.MOTIVO_CHAVE_WEB),
    (_g(26, {"ticket": "G-0001"}, chave="NOVO-3F9A01C", novo=True), ba.MOTIVO_CHAVE_WEB),
    (_n(30, {"status": "NO TÍTULO", "dt_mov": "20/11/2026"}), ""),
    (_n(31, {"status": "FINALIZADO"}), ba.MOTIVO_OPCAO_WEB),
    (_n(32, {"dt_mov": "2026-11-20"}), ba.MOTIVO_DATA_WEB),
    (_n(33, {"dt_mov": "01/01/2026"}), ""),                                    # data livre, nao so os 30 dias
    (_n(34, {"status": "NO TÍTULO"}, chave="FIL|PR|123"), ba.MOTIVO_CHAVE_WEB),
    (_n(35, {"novo": "x"}), ba.MOTIVO_LUGAR_WEB),
    (_d(40, {"etapa": "NEGADA", "motivo": "OUTRO", "credito": "REEMBOLSO", "recebida_em": "23/11/2026",
             "autorizado_por": "FULANO FICTICIO", "responsavel": "RESPONSAVEL FICTICIO"}), ""),
    (_d(41, {"etapa": "ENTREGUE"}), ba.MOTIVO_OPCAO_WEB),                      # a lista e a da Devolucao
    (_d(42, {"transportadora": "X"}), ba.MOTIVO_LUGAR_WEB),
    (_d(43, {"autorizado_por": "FULANO 123.456.789-00"}), ba.motivo_texto_web(60)),
    (_d(44, {"etapa": "NEGADA"}, chave="SEM BARRAS"), ba.MOTIVO_CHAVE_WEB),
]


@pytest.mark.parametrize("reg,motivo", CASOS, ids=[f"{c[0]['seq']}" for c in CASOS])
def test_RN_GER_011_RN_GER_012_validar_edicao_web(reg, motivo):
    assert ba.validar_edicao_web(reg, OPC) == motivo


def test_RN_GER_012_linha_nova_so_no_lugar_que_aceita():
    r = _n(1, {"status": "NO TÍTULO"}, chave="NOVO-3F9A01C2")
    r["novo"] = True
    assert ba.validar_edicao_web(r, OPC) == ba.MOTIVO_LUGAR_WEB
    r = _d(2, {"etapa": "NEGADA"}, chave="NOVO-3F9A01C2")
    r["novo"] = True
    assert ba.validar_edicao_web(r, OPC) == ba.MOTIVO_LUGAR_WEB


def test_RN_GER_011_a_frase_do_texto_leva_o_teto_do_campo():
    assert ba.MOTIVO_TEXTO_WEB == ba.motivo_texto_web(60)
    assert ba.motivo_texto_web(600) == "texto inválido (até 600 caracteres, sem CPF, CNPJ, telefone ou e-mail)"


def test_RN_GER_012_a_comparacao_do_texto_tira_o_CRLF_e_as_pontas():
    v = ba.valores_normalizados_web(_g(1, {"observacao": "  a\r\nb\rc  ", "status": "ABERTO"}))
    assert v == {"observacao": "a\nb\nc", "status": "ABERTO"}


# ------------------------------------------------------------------ gravacao no PC (so acrescenta)
def _diario_garantias(raiz):
    saida = []
    for a in sorted((Path(raiz) / gm.PASTA).glob("GARANTIAS_*.csv")):
        with open(a, encoding="utf-8-sig", newline="") as f:
            saida += list(csv.DictReader(f, delimiter=";"))
    return saida


def test_RN_GER_012_garantia_nova_grava_pela_funcao_da_tela_e_so_acrescenta(tmp_path):
    reg = _g(1, {"ticket": "G-0001", "cod_cliente": "900001", "observacao": "Peça com defeito"},
             chave="NOVO-3F9A01C2", novo=True, antes={"ticket": "G-0001"})
    saida = {}
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC, _saida=saida) == ("aplicada", "")
    assert saida == {"chave_pc": "G-0001"}
    g = gm.ler(tmp_path)["G-0001"]
    assert (g["status"], g["resultado"], g["origem"]) == ("ABERTO", "PENDENTE", "FAROL DE GARANTIAS")
    assert g["dt_solicitacao"] == "24/11/2026" and g["cod_cliente"] == "900001"
    arq = next((tmp_path / gm.PASTA).glob("GARANTIAS_*.csv"))
    antes = arq.read_bytes()
    reg2 = _g(2, {"status": "EM TRATATIVA"}, chave="G-0001")
    assert ba.aplicar_edicao_web(tmp_path, reg2, OPC) == ("aplicada", "")
    assert arq.read_bytes().startswith(antes)                         # so acrescenta (regra 7)
    assert gm.ler(tmp_path)["G-0001"]["status"] == "EM TRATATIVA"


def test_RN_GER_012_ticket_igual_ao_padrao_que_ja_existe_usa_o_novo_ticket_da_hora(tmp_path):
    gm.gravar(tmp_path, "G-0001", {"status": "ABERTO", "cod_cliente": "1"})     # outra rodada o ocupou
    reg = _g(1, {"ticket": "G-0001", "observacao": "x"}, chave="NOVO-AAAAAAAA", novo=True,
             antes={"ticket": "G-0001"})
    saida = {}
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC, _saida=saida) == ("aplicada", "")
    assert saida["chave_pc"] == "G-0002" == gm.novo_ticket(tmp_path).replace("0003", "0002")
    assert gm.ler(tmp_path)["G-0002"]["observacao"] == "x" and len(gm.ler(tmp_path)) == 2


def test_RN_GER_012_ticket_digitado_diferente_do_padrao_que_ja_existe_e_recusado(tmp_path):
    gm.gravar(tmp_path, "G-0005", {"status": "ABERTO", "cod_cliente": "1"})
    reg = _g(1, {"ticket": "G-0005"}, chave="NOVO-AAAAAAAA", novo=True, antes={"ticket": "G-0002"})
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC) == ("erro", ba.MOTIVO_TICKET_WEB)
    assert "já existe uma garantia com esse número" == ba.MOTIVO_TICKET_WEB
    assert list(gm.ler(tmp_path)) == ["G-0005"]
    # digitado livre e que nao existe: grava com ele
    reg = _g(2, {"ticket": "T-777"}, chave="NOVO-BBBBBBBB", novo=True, antes={"ticket": "G-0002"})
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC) == ("aplicada", "")
    assert "T-777" in gm.ler(tmp_path)


def test_RN_GER_012_garantia_nova_sem_ticket_e_recusada(tmp_path):
    reg = _g(1, {"observacao": "x"}, chave="NOVO-AAAAAAAA", novo=True)
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC) == ("erro", ba.MOTIVO_VALOR_WEB)
    assert not (tmp_path / gm.PASTA).exists() or not _diario_garantias(tmp_path)


def test_RN_GER_012_garantia_que_nao_existe_e_ticket_trocado_para_outra(tmp_path):
    assert ba.aplicar_edicao_web(tmp_path, _g(1, {"status": "FINALIZADA"}, chave="NAO-EXISTE"),
                                 OPC) == ("erro", ba.MOTIVO_LINHA_WEB)
    gm.gravar(tmp_path, "G-0001", {"status": "ABERTO", "cod_cliente": "1"})
    gm.gravar(tmp_path, "G-0002", {"status": "ABERTO", "cod_cliente": "2"})
    assert ba.aplicar_edicao_web(tmp_path, _g(2, {"ticket": "G-0002"}, chave="G-0001"),
                                 OPC) == ("erro", ba.MOTIVO_TICKET_WEB)
    assert ba.aplicar_edicao_web(tmp_path, _g(3, {"ticket": "G-0009", "status": "CANCELADA"}, chave="G-0001"),
                                 OPC) == ("aplicada", "")
    d = gm.ler(tmp_path)
    assert "G-0009" in d and d["G-0009"]["status"] == "CANCELADA"      # renomear + gravar, como a tela


def test_RN_POS_005_prazo_igual_ao_padrao_fica_em_branco():
    existentes = {"G-1": {"dt_solicitacao": "03/11/2026"}}
    padrao = lambda sol: "24/11/2026" if sol == "03/11/2026" else ""       # noqa: E731
    p, mot = ba.plano_garantia_web(_g(1, {"dt_prazo": "24/11/2026"}, chave="G-1"),
                                   {"dt_prazo": "24/11/2026"}, existentes, "G-0002", HOJE, padrao)
    assert mot == "" and p["campos"] == {"dt_prazo": ""}
    p, _ = ba.plano_garantia_web(_g(2, {"dt_prazo": "30/11/2026"}, chave="G-1"),
                                 {"dt_prazo": "30/11/2026"}, existentes, "G-0002", HOJE, padrao)
    assert p["campos"] == {"dt_prazo": "30/11/2026"}


def test_RN_GER_012_plano_da_linha_nova_e_funcao_pura():
    reg = _g(1, {"ticket": "G-0003", "status": "EM TRATATIVA"}, chave="NOVO-AAAAAAAA", novo=True,
             antes={"ticket": "G-0003"})
    entrada = json.dumps(reg, sort_keys=True)
    p, mot = ba.plano_garantia_web(reg, dict(reg["valores"]), {"G-0003": {}}, "G-0004", HOJE)
    assert mot == "" and p["ticket"] == "G-0004" and p["atual"] == ""
    assert p["campos"] == {"status": "EM TRATATIVA", "resultado": "PENDENTE", "dt_solicitacao": "24/11/2026",
                           "origem": "FAROL DE GARANTIAS", "ticket": "G-0004"}
    assert json.dumps(reg, sort_keys=True) == entrada


def test_RN_GER_012_ncc_grava_no_diario_so_acrescentando(tmp_path):
    reg = _n(1, {"status": "NO TÍTULO", "dt_mov": "20/11/2026"})
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC) == ("aplicada", "")
    arq = next((tmp_path / nc.PASTA).glob("NCC_*.csv"))
    antes = arq.read_bytes()
    assert ba.aplicar_edicao_web(tmp_path, _n(2, {"dt_mov": "21/11/2026"}), OPC) == ("aplicada", "")
    assert arq.read_bytes().startswith(antes)
    d = nc.ler(tmp_path)["FIL|PR|123|1"]
    assert d["status"] == "NO TÍTULO" and d["dt_mov"] == date(2026, 11, 21)


def test_RN_GER_012_devolucao_vai_ao_diario_do_pos_venda_na_aba_DEVOLUCOES(tmp_path):
    reg = _d(1, {"etapa": "NEGADA", "credito": "REEMBOLSO", "recebida_em": "23/11/2026"})
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC) == ("aplicada", "")
    linhas = []
    for a in (tmp_path / "RELATORIOS" / pv.PASTA_DIARIO).glob("EDICOES_*.csv"):
        with open(a, encoding="utf-8-sig", newline="") as f:
            linhas += list(csv.reader(f, delimiter=";"))
    assert {(ln[3], ln[4], ln[5], ln[6]) for ln in linhas[1:]} == {
        ("DEVOLUCOES", "FILIAL FICTICIA|900001|1", "etapa", "NEGADA"),
        ("DEVOLUCOES", "FILIAL FICTICIA|900001|1", "credito", "REEMBOLSO"),
        ("DEVOLUCOES", "FILIAL FICTICIA|900001|1", "recebida_em", "2026-11-23")}


def test_RN_GER_011_texto_com_removido_nunca_volta_por_cima_do_original(tmp_path):
    gm.gravar(tmp_path, "G-0001", {"observacao": "ORIGINAL com 92 99123-4567", "cod_cliente": "1"})
    reg = _g(1, {"observacao": "ORIGINAL com [removido]"}, chave="G-0001")
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC) == ("erro", ba.MOTIVO_REMOVIDO_WEB)
    assert gm.ler(tmp_path)["G-0001"]["observacao"] == "ORIGINAL com 92 99123-4567"
    assert ba.MOTIVO_REMOVIDO_WEB == "texto com trecho removido pelo site"


def test_RN_GER_012_arquivo_aberto_da_garantia_fica_pendente(tmp_path):
    def gravar(*a):
        raise PermissionError("aberto")
    reg = _g(1, {"ticket": "G-0001"}, chave="NOVO-AAAAAAAA", novo=True)
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC, gravar)[0] == "pendente"


# ------------------------------------------------------------------ sincronizacao: o antes e a idempotencia
class SiteFalso:
    def __init__(self, linhas):
        self.linhas, self.confirmados = linhas, []

    def get(self, url, params=None, headers=None, timeout=None):
        ls = [x for x in self.linhas if x["seq"] > params["desde"]]
        return SimpleNamespace(status_code=200, json=lambda: {
            "epoca": "ep-1", "linhas": ls, "ate_seq": ls[-1]["seq"] if ls else params["desde"], "mais": False})

    def post(self, url, json=None, headers=None, timeout=None):
        self.confirmados.append(json)
        return SimpleNamespace(status_code=200)


def test_RN_GER_012_a_linha_nova_nunca_e_criada_duas_vezes_e_o_antes_fica_gravado(tmp_path):
    antes = {"ticket": "G-0001"}
    site = SiteFalso([_g(1, {"ticket": "G-0001", "observacao": "x"}, chave="NOVO-3F9A01C2", novo=True,
                         antes=antes)])
    r = ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, lambda m: None, opcoes=OPC)
    assert r["aplicadas"] == 1 and r["erros"] == 0
    # a mesma linha de novo (estado perdido): pelo `id` do APLICADAS_WEB, nao grava de novo
    (tmp_path / "RELATORIOS" / "_EDICOES_WEB" / ba.ARQ_ESTADO_EDICOES_WEB).unlink()
    r = ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, lambda m: None, opcoes=OPC)
    assert list(gm.ler(tmp_path)) == ["G-0001"]
    assert len([x for x in _diario_garantias(tmp_path) if x["campo"] == "observacao"]) == 1
    aplic = ba.aplicadas_web(tmp_path)
    assert aplic["id-1"] == ("aplicada", "")
    arq = next((tmp_path / "RELATORIOS" / "_EDICOES_WEB").glob("APLICADAS_WEB_*.jsonl"))
    linhas = [json.loads(x) for x in arq.read_text(encoding="utf-8").splitlines()]
    assert len(linhas) == 1 and linhas[0]["antes"] == antes and linhas[0]["novo"] is True
    assert linhas[0]["chave_pc"] == "G-0001"


# ------------------------------------------------------------------ o que nao pode mudar
def test_RN_GER_012_o_teto_do_texto_vem_do_nucleo_e_nao_de_uma_tabela_do_robo():
    for nome in ("MAX_TEXTO_CAMPO_WEB", "TETOS_TEXTO_WEB", "MAX_TEXTO_EDICAO_WEB"):
        assert not hasattr(ba, nome)
    assert ba.MAX_TEXTO_WEB == 60 == rn.MAX_TEXTO_PADRAO


def test_regra_3_bap_dados_VERSAO_fica_em_27():
    import bap_dados
    assert bap_dados.VERSAO == 27
