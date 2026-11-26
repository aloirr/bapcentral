"""T-0025: edição na web do Farol DDR (STATUS e MOTIVO) e do Farol de Expositores (editar e linha nova), só admin,
chegando ao PC pelo robô; PC só leitura nelas. Tudo em pasta temporária, dados fictícios.

RN-GER-012 (decisão do Alexandre, 25/11/2026): edição só na web e só pelo admin; o robô grava pela MESMA função da
tela do PC (farol_ddr.gravar_marcacoes, expositores.gravar_edicoes); a tela do PC fica só leitura.
"""
from types import SimpleNamespace

import pytest

import bap_automation as ba
import expositores as ex
import farol_ddr as fd

OPC = {"farol.status": set(fd.STATUS), "farol.motivo": set(fd.MOTIVOS), "expositores.status": set(ex.STATUS),
       "expositores.categoria": set(ex.CATEGORIAS), "expositores.uf": set(ex.UFS),
       "expositores.qtd": {str(n) for n in range(1, 21)}}
ARQ_FAROL = "RELATORIOS/FAROL_DDR_BAP_2026-11.xlsx"


def _reg(rid, tabela, modulo, chave, valores):
    return {"rid": rid, "tabela": tabela, "modulo": modulo, "chave": chave, "valores": valores}


# ------------------------------------------------------------------ especificação no pacote
def test_RN_GER_012_spec_ddr_leva_mes_aba_e_linha_na_chave():
    pc = [{"nome": n} for n in ("HORÁRIO", "ATIVIDADE", "PONTOS", "STATUS", "MOTIVO")]
    linhas = [["08:00", "A", 5, "", "", "PESSOA FICTICIA|12"], ["09:00", "B", 5, "", "", "PESSOA FICTICIA|13"]]
    pc_ed = {"arquivo": ARQ_FAROL, "aba": "PESSOA FICTICIA", "modulo": "farol", "chave": 5, "campos": [
        {"campo": "status", "rotulo": "STATUS", "opcoes": list(fd.STATUS), "col": 3, "data": False},
        {"campo": "motivo", "rotulo": "MOTIVO", "opcoes": list(fd.MOTIVOS), "col": 4, "data": False}]}
    ed = ba.edicao_web("farol_pv", "Hoje", pc_ed, linhas, pc, [c["nome"] for c in pc])
    assert ed["modulo"] == "farol" and ed["chaves"] == ["2026-11|PESSOA FICTICIA|12", "2026-11|PESSOA FICTICIA|13"]
    assert [c["campo"] for c in ed["campos"]] == ["status", "motivo"] and "novo" not in ed
    # arquivo que não é o Farol do mês: recusa a especificação
    with pytest.raises(ValueError):
        ba.edicao_web("farol_pv", "Hoje", {**pc_ed, "arquivo": "RELATORIOS/OUTRO.xlsx"}, linhas, pc,
                      [c["nome"] for c in pc])


def test_RN_GER_012_spec_expositores_tem_novo_max_e_chaves():
    nomes = ["STATUS", "SOLICITAÇÃO", "CLIENTE", "OBSERVAÇÕES"]
    pc = [{"nome": n} for n in nomes]
    linhas = [["Solicitado", None, "C", "", "EXP0001"]]
    pc_ed = {"arquivo": "RELATORIOS/" + ex.ARQUIVO, "aba": ex.ABA, "modulo": "expositores", "chave": 4,
             "novo": True, "padroes_novo": {"status": "Solicitado", "qtd": "1", "data": "05/11/2026"},
             "campos": [{"campo": "status", "rotulo": "STATUS", "opcoes": ex.STATUS, "col": 0},
                        {"campo": "data", "rotulo": "DATA", "opcoes": ["05/11/2026"], "data": True, "col": 1},
                        {"campo": "observacoes", "rotulo": "OBS", "opcoes": [], "livre": True, "col": 3,
                         "mantem_caixa": True}]}
    ed = ba.edicao_web("tm_expositores", "Expositores", pc_ed, linhas, pc, nomes)
    assert ed["chaves"] == ["EXP0001"]
    assert ed["novo"] == {"padroes": {"status": "Solicitado", "data": "hoje"}}      # qtd sem campo: fora
    obs = ed["campos"][2]
    assert obs["tipo"] == "texto" and obs["max"] == 200 and obs["caixa"] is True


# ------------------------------------------------------------------ validação no robô
def test_RN_GER_012_validar_farol():
    ok = _reg("farol_pv", "Hoje", "farol", "2026-11|PESSOA FICTICIA|12",
              {"status": "ENTREGUE PARCIAL", "motivo": fd.MOTIVOS[0]})
    assert ba.validar_edicao_web(ok, OPC) == ""
    assert ba.validar_edicao_web({**ok, "valores": {"status": ""}}, OPC) == ""            # limpar a marcação
    assert ba.validar_edicao_web({**ok, "chave": "2026-11|PESSOA FICTICIA|4"}, OPC) == ba.MOTIVO_CHAVE_WEB
    assert ba.validar_edicao_web({**ok, "chave": "PESSOA FICTICIA|12"}, OPC) == ba.MOTIVO_CHAVE_WEB
    assert ba.validar_edicao_web({**ok, "chave": "../2026|X|12"}, OPC) == ba.MOTIVO_CHAVE_WEB
    assert ba.validar_edicao_web({**ok, "valores": {"status": "Solicitado"}}, OPC) == ba.MOTIVO_OPCAO_WEB
    assert ba.validar_edicao_web({**ok, "valores": {"data": "01/11/2026"}}, OPC) == ba.MOTIVO_LUGAR_WEB
    assert ba.validar_edicao_web({**ok, "tabela": "Outra"}, OPC) == ba.MOTIVO_LUGAR_WEB


def test_RN_GER_012_validar_expositores():
    base = _reg("tm_expositores", "Expositores", "expositores", "NOVO1A2B3C4D",
                {"status": "Solicitado", "qtd": "2", "uf": "AM", "categoria": "BATERIAS",
                 "data": "05/11/2026", "cliente": "900001 - CLIENTE FICTICIO", "observacoes": "x" * 200})
    assert ba.validar_edicao_web(base, OPC) == ""
    assert ba.validar_edicao_web({**base, "chave": "EXP0007"}, OPC) == ""
    assert ba.validar_edicao_web({**base, "chave": "LINHA9"}, OPC) == ba.MOTIVO_CHAVE_WEB
    # "status" do DDR não vale nos Expositores e vice-versa (listas por módulo)
    assert ba.validar_edicao_web({**base, "valores": {"status": "ENTREGUE"}}, OPC) == ba.MOTIVO_OPCAO_WEB
    assert ba.validar_edicao_web({**base, "valores": {"uf": "SP"}}, OPC) == ba.MOTIVO_OPCAO_WEB
    assert ba.validar_edicao_web({**base, "valores": {"observacoes": "x" * 201}}, OPC) == ba.MOTIVO_TEXTO_WEB
    assert ba.validar_edicao_web({**base, "valores": {"descricao": "y" * 61}}, OPC) == ""   # até 80
    assert ba.validar_edicao_web({**base, "valores": {"cidade": "z" * 61}}, OPC) == ba.MOTIVO_TEXTO_WEB
    assert ba.validar_edicao_web({**base, "valores": {"observacoes": "a@b.com"}}, OPC) == ba.MOTIVO_TEXTO_WEB
    assert ba.validar_edicao_web({**base, "valores": {"data": "31/02/2026"}}, OPC) == ba.MOTIVO_DATA_WEB


# ------------------------------------------------------------------ grava no PC pela mesma função da tela
def test_RN_GER_012_robo_grava_marcacao_do_farol_ddr(tmp_path):
    from openpyxl import Workbook, load_workbook
    (tmp_path / "RELATORIOS").mkdir()
    wb = Workbook()
    ws = wb.active
    ws.title = "PESSOA FICTICIA"
    ws.cell(12, 4, "Atividade fictícia")
    wb.save(tmp_path / ARQ_FAROL)
    reg = _reg("farol_pv", "Hoje", "farol", "2026-11|PESSOA FICTICIA|12",
               {"status": "NÃO ENTREGUE", "motivo": fd.MOTIVOS[1]})
    assert ba.aplicar_edicao_web(tmp_path, reg, OPC) == ("aplicada", "")
    ws = load_workbook(tmp_path / ARQ_FAROL)["PESSOA FICTICIA"]
    assert (ws.cell(12, 7).value, ws.cell(12, 9).value) == ("NÃO ENTREGUE", fd.MOTIVOS[1])
    # linha que não é atividade, ou aba que não existe: recusa com frase fixa (sem dado pessoal)
    assert ba.aplicar_edicao_web(tmp_path, {**reg, "chave": "2026-11|PESSOA FICTICIA|20"}, OPC) == (
        "erro", ba.MOTIVO_LINHA_WEB)
    assert ba.aplicar_edicao_web(tmp_path, {**reg, "chave": "2026-11|OUTRA ABA|12"}, OPC) == (
        "erro", ba.MOTIVO_LINHA_WEB)


def test_RN_GER_012_robo_grava_expositor_novo_e_existente(tmp_path):
    from openpyxl import load_workbook
    novo = _reg("tm_expositores", "Expositores", "expositores", "NOVO1A2B3C4D",
                {"status": "Solicitado", "qtd": "2", "cliente": "900001 - CLIENTE FICTICIO",
                 "descricao": "EXPOSITOR FICTICIO", "uf": "AM", "observacoes": "o" * 150})
    assert ba.aplicar_edicao_web(tmp_path, novo, OPC) == ("aplicada", "")
    ws = load_workbook(ex.caminho(tmp_path))[ex.ABA]
    textos = [str(c.value) for row in ws.iter_rows(min_row=2) for c in row if c.value is not None]
    assert "EXP0001" in textos and "CLIENTE FICTICIO" in textos and "o" * 150 in textos
    alterar = _reg("tm_expositores", "Expositores", "expositores", "EXP0001", {"status": "Entregue"})
    assert ba.aplicar_edicao_web(tmp_path, alterar, OPC) == ("aplicada", "")
    inexistente = {**alterar, "chave": "EXP0099"}
    assert ba.aplicar_edicao_web(tmp_path, inexistente, OPC) == ("erro", ba.MOTIVO_LINHA_WEB)


# ------------------------------------------------------------------ PC só leitura
def test_RN_GER_012_pc_so_leitura_no_farol_ddr_e_nos_expositores(monkeypatch):
    import bap_relatorios as br
    avisos, abertas = [], []
    monkeypatch.setattr(br.messagebox, "showinfo", lambda titulo, msg, **k: avisos.append(msg))
    monkeypatch.setattr(br, "Edicao", lambda *a, **k: abertas.append(a))
    casos = [(r, t) for r in ("farol_pv", "farol_vc", "farol_pl")
             for t in ("Hoje", "Pendentes de marcação", "Até hoje")] + [("tm_expositores", "Expositores")]
    assert set(casos) <= br.EDICAO_SO_WEB
    for rid, titulo in casos:
        vista = SimpleNamespace(janela=SimpleNamespace(rel={"id": rid}),
                                t={"titulo": titulo, "edicao": {"chave": 0, "campos": []}})
        br.VistaTabela.editar(vista, ["CHAVE"])
    assert avisos == [br.MSG_EDICAO_SO_WEB] * len(casos) and abertas == []


def test_RN_GER_012_robo_leva_os_cinco_farois_ao_site():
    for rid in ("farol_pv", "farol_vc", "farol_pl", "vc_champions", "tm_expositores"):
        assert rid in ba.FAROIS_WEB and rid in ba.RIDS_TABELAS_WEB
    # Campanhas não edita na web (champions_config.json é dado digitado): nenhum lugar de edição
    assert not [k for k in ba.EDICOES_WEB if k[0] == "vc_champions"]
