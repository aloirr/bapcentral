"""T-0021: edição do Farol de Pedidos (autorização) e do Farol de Entregas (a linha) no site, só admin,
chegando ao PC pelo robô (bap_automation).

Regra (proposta ao gerente para docs/produto/03-regras.md, decisão do Alexandre de 25/11/2026):
RN-GER-012 · Edição só no site e só pelo admin, por enquanto; a edição chega ao PC pelo robô, gravada
pela MESMA função da tela do PC (só acrescenta linha: dado digitado é intocável, regra 7); a tela do PC
fica só leitura nessa edição ("A edição agora é só pela BAP Central web.").

Tudo numa pasta temporária, com dados fictícios; o site é um falso em memória.
"""
import csv
import json
from datetime import date
from types import SimpleNamespace

import pytest

import autorizacoes
import bap_automation as ba
import pos_venda as pv
import relatorios_nucleo as rn

TOKEN = "token-ficticio-t21"
BASE = "https://web.exemplo.test"
OPCOES = {"por": {"ALEXANDRE", "PRICE"}, "etapa": set(pv.ETAPAS_ENTREGA),
          "transportadora": {"TRANSPORTADORA FICTICIA 1", "TRANSPORTADORA FICTICIA 2"}}


def _reg(seq, rid="pv_pedidos", tabela="Pedidos", modulo="autorizacoes", chave="101002|012345",
         valores=None, status="pendente"):
    return {"tipo": "edicao", "seq": seq, "id": f"id-{seq}", "quando": "2026-11-25 09:00:00",
            "usuario": "admin.ficticio", "rid": rid, "tabela": tabela, "modulo": modulo, "chave": chave,
            "valores": valores if valores is not None else {"por": "PRICE"}, "antes": {}, "status": status}


def _ent(seq, valores, chave="FILIAL FICTICIA|900001|1", tabela="Entregas"):
    return _reg(seq, "pl_entregas", tabela, "pos_venda", chave, valores)


# ------------------------------------------------------------------ especificação que vai no pacote
def test_RN_GER_012_spec_da_autorizacao_vem_do_nucleo():
    pc = [{"nome": n} for n in ("PEDIDO", "CÓD. AUTORIZAÇÃO", "AUTORIZADO POR", "CHAVE")]
    linhas = [["000001", "", "", "101002|000001"], ["000002", "X1", "PRICE", ""]]
    ed = ba.edicao_web("pv_pedidos", "Pedidos", None, linhas, pc, [c["nome"] for c in pc])
    assert ed["modulo"] == "autorizacoes" and ed["acao"] == "Autorização"
    assert ed["chaves"] == ["101002|000001", ""]                      # sem chave: sem botão
    cod, por = ed["campos"]
    assert (cod["campo"], cod["tipo"], cod["coluna"], cod.get("caixa")) == (
        "codigo", "texto", "CÓD. AUTORIZAÇÃO", True)
    assert (por["campo"], por["tipo"], por["opcoes"]) == ("por", "lista", list(rn.QUEM_AUTORIZA))


def _ctx(tmp_path):
    return SimpleNamespace(raiz=tmp_path, hoje=date(2026, 11, 24),
                           posvenda={"entregas": [{"responsavel": "motorista ficticio"}]})


CAD = {"transportadoras": [{"nome": "TRANSPORTADORA FICTICIA 1", "ufs": ["AM"]},
                           {"nome": "TRANSPORTADORA FICTICIA 2", "ufs": ["PA"]}]}


def test_RN_GER_012_spec_das_entregas_vem_da_tabela_do_pc(tmp_path):
    nomes = ["UF", "CIDADE", "VLR NF", "LOCAL/FRETE", "VLR FRETE", "ETAPA", "TRANSPORTADORA",
             "DT. PREVISTA", "DT. REAL", "RESPONSÁVEL", "VLR REAL FRETE"]
    pc = [{"nome": n} for n in nomes]
    ix = {n: i for i, n in enumerate(nomes)}
    ed_pc = rn._entrega_editavel(_ctx(tmp_path), len(nomes), {
        "etapa": ix["ETAPA"], "transportadora": ix["TRANSPORTADORA"], "entregue_em": ix["DT. REAL"],
        "prevista_manual": ix["DT. PREVISTA"], "responsavel": ix["RESPONSÁVEL"],
        "frete_real": ix["VLR REAL FRETE"]}, CAD, uf_col=ix["UF"], cidade_col=ix["CIDADE"],
        frete=(ix["VLR NF"], ix["LOCAL/FRETE"], ix["VLR FRETE"]))
    linhas = [["AM", "MANAUS", 1000.0, "FRETE", 50.0, "EM TRÂNSITO", "", None, None, "", None, "F|900001|1"],
              ["PA", "BELÉM", 2000.0, "RETIRA", 0.0, "ENTREGUE", "", None, None, "", None, ""]]
    ed = ba.edicao_web("pl_entregas", "Entregas", ed_pc, linhas, pc, nomes)
    assert ed["modulo"] == "pos_venda" and ed["chaves"] == ["F|900001|1", ""]
    c = {x["campo"]: x for x in ed["campos"]}
    assert set(c) == {"etapa", "transportadora", "prevista_manual", "entregue_em", "responsavel", "frete_real"}
    assert c["etapa"]["opcoes"] == list(pv.ETAPAS_ENTREGA)
    tr = c["transportadora"]                                         # opções da cidade da nota
    assert [tr["grupos"][g] for g in tr["grupo_linhas"]] == [["TRANSPORTADORA FICTICIA 1"],
                                                            ["TRANSPORTADORA FICTICIA 2"]]
    assert c["prevista_manual"]["tipo"] == "data" and c["prevista_manual"]["opcoes"][0] == "24/11/2026"
    assert len(c["entregue_em"]["opcoes"]) == 30
    assert c["responsavel"]["tipo"] == "texto" and c["responsavel"]["opcoes"] == ["MOTORISTA FICTICIO"]
    assert c["frete_real"]["tipo"] == "numero" and c["frete_real"]["linhas"] == [0]   # só com FRETE
    assert c["frete_real"]["coluna"] == "VLR REAL FRETE"


def test_RN_GER_012_lugares_batem_com_o_pc(tmp_path):
    a = rn._edicao_autorizacao(0, 1, 2)
    lug = ba.EDICOES_WEB[("pv_pedidos", "Pedidos")]
    assert (a["modulo"], a["arquivo"], a["aba"]) == (lug["modulo"], lug["arquivo"], lug["aba"])
    e = rn._entrega_editavel(_ctx(tmp_path), 1, {}, CAD)
    for t in ("Entregas", "Pendências dos meses anteriores"):
        lug = ba.EDICOES_WEB[("pl_entregas", t)]
        assert (e["arquivo"], e["aba"]) == (lug["arquivo"], lug["aba"]) and e["aba"] == pv.ABA_ENT
        assert lug["modulo"] == "pos_venda"


def test_spec_que_nao_bate_com_o_pc_nao_vai():
    ed = {"arquivo": "OUTRO.xlsx", "aba": "ENTREGAS", "chave": 0, "campos": []}
    with pytest.raises(ValueError):
        ba.edicao_web("pl_entregas", "Entregas", ed, [], [], [])
    assert ba.edicao_web("vc_visitas", "Por vendedor", ed, [], [], []) is None


# ------------------------------------------------------------------ conferência no robô (função pura)
@pytest.mark.parametrize("reg, motivo", [
    (_reg(1), ""),
    (_reg(1, valores={"codigo": "Ab-12", "por": ""}), ""),
    (_ent(1, {"etapa": "ENTREGUE", "entregue_em": "23/11/2026", "frete_real": "1.234,50",
              "responsavel": "MOTORISTA X", "transportadora": "TRANSPORTADORA FICTICIA 1",
              "prevista_manual": ""}), ""),
    (_reg(1, tabela="Solicitação BAP"), ba.MOTIVO_LUGAR_WEB),
    (_reg(1, modulo="pos_venda"), ba.MOTIVO_LUGAR_WEB),
    (_reg(1, valores={"etapa": "ENTREGUE"}), ba.MOTIVO_LUGAR_WEB),
    (_reg(1, valores={}), ba.MOTIVO_LUGAR_WEB),
    (_reg(1, chave="ABC"), ba.MOTIVO_CHAVE_WEB),
    (_ent(1, {"etapa": "X"}, chave="sem barras"), ba.MOTIVO_CHAVE_WEB),
    (_reg(1, valores={"por": "OUTRO"}), ba.MOTIVO_OPCAO_WEB),
    (_ent(1, {"transportadora": "OUTRA"}), ba.MOTIVO_OPCAO_WEB),
    (_ent(1, {"entregue_em": "2026-11-23"}), ba.MOTIVO_DATA_WEB),
    (_ent(1, {"frete_real": "abc"}), ba.MOTIVO_VALOR_WEB),
    (_ent(1, {"frete_real": "-5"}), ba.MOTIVO_VALOR_WEB),
    (_ent(1, {"responsavel": "FULANO 123.456.789-00"}), ba.motivo_texto_web()),
    (_ent(1, {"responsavel": "x" * 61}), ba.motivo_texto_web()),
])
def test_RN_GER_012_validar_edicao_web(reg, motivo):
    assert ba.validar_edicao_web(reg, OPCOES) == motivo


# ------------------------------------------------------------------ gravação pela função do PC (pasta temporária)
def _linhas_csv(pasta, glob):
    out = []
    for a in sorted(pasta.glob(glob)):
        with open(a, encoding="utf-8-sig", newline="") as f:
            out += list(csv.reader(f, delimiter=";"))
    return out


def test_RN_GER_012_autorizacao_grava_pelo_autorizacoes_so_acrescentando(tmp_path):
    st, mot = ba.aplicar_edicao_web(tmp_path, _reg(1, valores={"codigo": "Ab-12", "por": "ALEXANDRE"}), OPCOES)
    assert (st, mot) == ("aplicada", "")
    arq = next((tmp_path / autorizacoes.PASTA).glob("AUTORIZACOES_*.csv"))
    antes = arq.read_bytes()
    ba.aplicar_edicao_web(tmp_path, _reg(2, valores={"por": "PRICE"}), OPCOES)
    assert arq.read_bytes().startswith(antes)                       # só acrescenta
    a = autorizacoes.ler(tmp_path)["101002|012345"]
    assert (a["codigo"], a["por"]) == ("Ab-12", "PRICE")             # o código de antes fica


def test_RN_GER_012_entrega_vai_ao_diario_do_pos_venda(tmp_path):
    st, _ = ba.aplicar_edicao_web(tmp_path, _ent(1, {"etapa": "ENTREGUE", "entregue_em": "23/11/2026"}), OPCOES)
    assert st == "aplicada"
    linhas = _linhas_csv(tmp_path / "RELATORIOS" / pv.PASTA_DIARIO, "EDICOES_*.csv")
    corpo = [ln for ln in linhas[1:]]
    assert {(ln[3], ln[4], ln[5], ln[6]) for ln in corpo} == {
        ("ENTREGAS", "FILIAL FICTICIA|900001|1", "etapa", "ENTREGUE"),
        ("ENTREGAS", "FILIAL FICTICIA|900001|1", "entregue_em", "2026-11-23")}


def test_RN_GER_012_entrega_na_planilha_quando_e_a_maquina_que_grava(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "MAQUINA_DO_POS_VENDA", "")
    arq = tmp_path / "RELATORIOS" / "ACOMPANHAMENTO_POS_VENDA.xlsx"
    arq.parent.mkdir(parents=True)
    wb = pv.criar_arquivo()
    nomes = [c[1] for c in pv.COLUNAS_DA_ABA[pv.ABA_ENT]]
    ws = wb[pv.ABA_ENT]
    ws.cell(pv.PRIMEIRA, nomes.index("chave") + 1, "FILIAL FICTICIA|900001|1")
    ws.cell(pv.PRIMEIRA, nomes.index("etapa") + 1, "EM TRÂNSITO")
    wb.save(arq)
    import os
    import time
    os.utime(arq, (time.time() - 3600, time.time() - 3600))       # a planilha é de antes da edição
    st, _ = ba.aplicar_edicao_web(tmp_path, _ent(1, {"etapa": "ENTREGUE", "responsavel": "MOTORISTA X"}), OPCOES)
    assert st == "aplicada"
    from openpyxl import load_workbook
    ws = load_workbook(arq)[pv.ABA_ENT]
    assert ws.cell(pv.PRIMEIRA, nomes.index("etapa") + 1).value == "ENTREGUE"
    assert ws.cell(pv.PRIMEIRA, nomes.index("responsavel") + 1).value == "MOTORISTA X"
    st, mot = ba.aplicar_edicao_web(tmp_path, _ent(2, {"etapa": "ENTREGUE"}, chave="F|1|1"), OPCOES)
    assert (st, mot) == ("erro", ba.MOTIVO_LINHA_WEB)               # linha que não existe no PC


def test_arquivo_aberto_fica_pendente(tmp_path):
    def gravar(*a):
        raise PermissionError("aberto")
    assert ba.aplicar_edicao_web(tmp_path, _reg(1), OPCOES, gravar)[0] == "pendente"


# ------------------------------------------------------------------ sincronização com o site (falso)
class SiteFalso:
    def __init__(self, linhas, epoca="ep-1"):
        self.linhas, self.epoca, self.confirmados, self.gets = linhas, epoca, [], []

    def get(self, url, params=None, headers=None, timeout=None):
        assert headers["Authorization"] == f"Bearer {TOKEN}" and url == f"{BASE}/api/edicoes"
        self.gets.append(params["desde"])
        ls = [x for x in self.linhas if x["seq"] > params["desde"]]
        return SimpleNamespace(status_code=200, json=lambda: {
            "epoca": self.epoca, "linhas": ls, "ate_seq": ls[-1]["seq"] if ls else params["desde"], "mais": False})

    def post(self, url, json=None, headers=None, timeout=None):
        assert url == f"{BASE}/api/edicoes/confirmar"
        self.confirmados.append(json)
        for r in json["resultados"]:
            for x in self.linhas:
                if x["seq"] == r["seq"]:
                    x["status"] = r["status"]
        return SimpleNamespace(status_code=200)


def test_RN_GER_012_sincronizar_grava_confirma_e_nao_repete(tmp_path):
    site = SiteFalso([_reg(1), _reg(2, valores={"por": "OUTRO"}),
                      _ent(3, {"etapa": "ENTREGUE"})])
    feitos, logs = [], []

    def gravar(raiz, modulo, arquivo, aba, edicoes):
        feitos.append((modulo, aba, edicoes))
        return 1
    r = ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, logs.append, gravar, OPCOES)
    assert r == {"aplicadas": 2, "erros": 1, "pendentes": 0, "confirmado": True}
    assert feitos == [("autorizacoes", "", {"101002|012345": {"por": "PRICE"}}),
                      ("pos_venda", "ENTREGAS", {"FILIAL FICTICIA|900001|1": {"etapa": "ENTREGUE"}})]
    (conf,) = site.confirmados
    assert conf["epoca"] == "ep-1"
    assert [(x["seq"], x["status"], x["motivo"]) for x in conf["resultados"]] == [
        (1, "aplicada", ""), (2, "erro", ba.MOTIVO_OPCAO_WEB), (3, "aplicada", "")]
    est = ba.ler_estado_edicoes_web(tmp_path)
    assert (est["epoca"], est["ate_seq"], est["a_confirmar"]) == ("ep-1", 3, [])
    # segunda rodada: nada novo, nada regravado
    r = ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, logs.append, gravar, OPCOES)
    assert len(feitos) == 2 and r["aplicadas"] == 0 and site.gets[-1] == 3
    assert not any(TOKEN in m for m in logs)
    assert not any("admin.ficticio" in m or "900001" in m for m in logs)   # log sem dado da linha


def test_RN_GER_012_excel_aberto_segura_a_fila(tmp_path):
    site = SiteFalso([_ent(1, {"etapa": "ENTREGUE"}), _reg(2)])
    chamadas = []

    def gravar(raiz, modulo, *a):
        chamadas.append(modulo)
        raise PermissionError("aberto")
    r = ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, lambda m: None, gravar, OPCOES)
    assert r["pendentes"] == 1 and chamadas == ["pos_venda"]        # a de trás espera (ordem do seq)
    assert ba.ler_estado_edicoes_web(tmp_path)["ate_seq"] == 0 and site.confirmados == []
    r = ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, lambda m: None,
                                   lambda *a: 1, OPCOES)
    assert r["aplicadas"] == 2 and ba.ler_estado_edicoes_web(tmp_path)["ate_seq"] == 2


def test_RN_GER_012_confirmacao_que_falhou_nao_regrava(tmp_path):
    site = SiteFalso([_reg(1)])
    site.post = lambda *a, **k: SimpleNamespace(status_code=503)
    n = []
    ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, lambda m: None, lambda *a: n.append(1) or 1, OPCOES)
    assert ba.ler_estado_edicoes_web(tmp_path)["a_confirmar"] == [{"seq": 1, "status": "aplicada", "motivo": ""}]
    # o estado se perde (pasta nova do estado) e a época muda: o id evita gravar de novo
    (tmp_path / ba.PASTA_EDICOES_WEB / ba.ARQ_ESTADO_EDICOES_WEB).unlink()
    site2 = SiteFalso([_reg(1)], epoca="ep-2")
    ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site2, lambda m: None, lambda *a: n.append(1) or 1, OPCOES)
    assert len(n) == 1 and site2.confirmados[0]["resultados"][0]["status"] == "aplicada"


def test_site_fora_do_ar_nao_derruba(tmp_path):
    class Caido:
        def get(self, *a, **k):
            raise ConnectionError("x")
    r = ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, Caido(), lambda m: None, lambda *a: 1, OPCOES)
    assert r == {"aplicadas": 0, "erros": 0, "pendentes": 0, "confirmado": False}
    site = SiteFalso([])
    site.get = lambda *a, **k: SimpleNamespace(status_code=404, json=lambda: {})
    assert ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, lambda m: None)["aplicadas"] == 0


def test_aplicadas_ficam_num_arquivo_so_de_acrescimo(tmp_path):
    site = SiteFalso([_reg(1), _reg(2)])
    ba.sincronizar_edicoes_web(tmp_path, BASE, TOKEN, site, lambda m: None, lambda *a: 1, OPCOES)
    arq = next((tmp_path / ba.PASTA_EDICOES_WEB).glob("APLICADAS_WEB_*.jsonl"))
    regs = [json.loads(x) for x in arq.read_text(encoding="utf-8").splitlines()]
    assert [(r["seq"], r["status"]) for r in regs] == [(1, "aplicada"), (2, "aplicada")]
    assert set(ba.aplicadas_web(tmp_path)) == {"id-1", "id-2"}


# ------------------------------------------------------------------ PC só leitura nessas edições
def test_RN_GER_012_pc_so_leitura_na_autorizacao_e_nas_entregas(monkeypatch):
    import bap_relatorios as br
    assert br.MSG_EDICAO_SO_WEB == "A edição agora é só pela BAP Central web."
    assert br.AUTORIZA_EM == ()                       # a janela do pedido só mostra a autorização
    avisos, abertas = [], []
    monkeypatch.setattr(br.messagebox, "showinfo", lambda titulo, msg, **k: avisos.append(msg))
    monkeypatch.setattr(br, "Edicao", lambda *a, **k: abertas.append(a))
    for rid, titulo in (("pv_pedidos", "Pedidos"), ("pl_entregas", "Entregas")):
        vista = SimpleNamespace(janela=SimpleNamespace(rel={"id": rid}),
                                t={"titulo": titulo, "edicao": {"chave": 0, "campos": []}})
        br.VistaTabela.editar(vista, ["CHAVE"])
    assert avisos == [br.MSG_EDICAO_SO_WEB] * 2 and abertas == []
    # o bloqueio vale por lugar (rid, título da aba): uma aba fora do EDICAO_SO_WEB segue abrindo a
    # Edicao. A NCC, as Devoluções e as Garantias também ficam só leitura (T-0023): o teste delas é o
    # tests/test_T0023_pc_so_leitura.py.
    fora = ("rid_ficticio", "Aba fictícia")
    assert fora not in br.EDICAO_SO_WEB
    vista = SimpleNamespace(janela=SimpleNamespace(rel={"id": fora[0]}),
                            t={"titulo": fora[1], "edicao": {"chave": 0, "campos": []}})
    br.VistaTabela.editar(vista, ["CHAVE"])
    assert len(abertas) == 1 and avisos == [br.MSG_EDICAO_SO_WEB] * 2
