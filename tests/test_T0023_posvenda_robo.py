"""T-0023: o robô leva Garantias, Devoluções e NCC ao pacote e grava as edições da web pela função do PC."""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bap_automation as ba   # noqa: E402
import garantias as gm        # noqa: E402

OPC = {"gar_status": set(gm.STATUS), "gar_resultado": set(gm.RESULTADOS), "ncc_status": {"NO TÍTULO", "FINALIZADO"},
       "etapa_dev": {"SOLICITADA", "ENCERRADA"}, "motivo_dev": {"OUTRO"}, "credito": {"REEMBOLSO"}}


def reg(rid, tab, modulo, chave, valores, **k):
    return {"rid": rid, "tabela": tab, "modulo": modulo, "chave": chave, "valores": valores, **k}


def test_RN_POSVENDA_os_3_farois_estao_no_pacote_web():
    for rid in ("pl_garantias", "pl_devolucoes", "pl_ncc"):
        assert rid in ba.FAROIS_WEB and rid in ba.RIDS_TABELAS_WEB and rid in ba._ABAS_TABELAS_WEB
        assert set(ba._ABAS_TABELAS_WEB[rid]) == set(ba._COLUNAS_TABELAS_WEB[rid])
    assert ba._COLUNAS_FORA_TABELA_WEB[("pl_garantias", "Garantias")] == ("CONTATO CLIENTE",)


def test_validar_ncc_devolucao_e_garantia():
    v = ba.validar_edicao_web
    assert v(reg("pl_ncc", "NCC pendentes", "ncc", "01|NCC|123|A", {"status": "FINALIZADO", "dt_mov": "20/11/2026"}), OPC) == ""
    assert v(reg("pl_ncc", "NCC pendentes", "ncc", "01|NCC|123", {"status": "FINALIZADO"}), OPC) == ba.MOTIVO_CHAVE_WEB
    assert v(reg("pl_ncc", "NCC pendentes", "ncc", "01|NCC|123|A", {"status": "XX"}), OPC) == ba.MOTIVO_OPCAO_WEB
    assert v(reg("pl_devolucoes", "Devoluções", "pos_venda", "F|1|2", {"etapa": "ENCERRADA", "motivo": "OUTRO"}), OPC) == ""
    # a etapa da devolução não é a da entrega
    assert v(reg("pl_devolucoes", "Devoluções", "pos_venda", "F|1|2", {"etapa": "EM TRÂNSITO"}), OPC) == ba.MOTIVO_OPCAO_WEB
    assert v(reg("pl_garantias", "Garantias", "garantias", "G-0001", {"pendencias": "a\nb", "status": "ABERTO"}), OPC) == ""
    assert v(reg("pl_garantias", "Garantias", "garantias", "G-0001", {"pendencias": "x" * 601}), OPC) == ba.MOTIVO_TEXTO_WEB
    assert v(reg("pl_garantias", "Garantias", "garantias", "G-0001", {"observacao": "ligar 92 99999-9999"}), OPC) == ba.MOTIVO_TEXTO_WEB
    assert v(reg("pl_garantias", "Garantias", "garantias", "G-0001", {"ticket": "G;2"}), OPC) == ba.MOTIVO_TICKET_WEB
    assert v(reg("pl_garantias", "Garantias", "garantias", "G-0001", {"status": "ABERTO"}, novo=True), OPC) == ""
    assert v(reg("pl_ncc", "NCC pendentes", "ncc", "01|NCC|123|A", {"status": "FINALIZADO"}, novo=True), OPC) == ba.MOTIVO_NOVO_WEB


def test_garantia_grava_pela_funcao_do_pc_e_so_acrescenta(tmp_path):
    ba._gravar_garantia_pc(tmp_path, "G-0001", {"_novo": True, "pendencias": "faltou nota", "dt_solicitacao": "03/11/2026"})
    g = gm.ler(tmp_path)["G-0001"]
    assert g["status"] == "ABERTO" and g["resultado"] == "PENDENTE" and g["origem"] == "FAROL DE GARANTIAS"
    ba._gravar_garantia_pc(tmp_path, "G-0001", {"status": "FINALIZADA"})
    g = gm.ler(tmp_path)["G-0001"]
    assert g["status"] == "FINALIZADA" and g["dt_fechamento"]           # a mesma regra do PC
    assert g["pendencias"] == "faltou nota"
    arqs = list((tmp_path / "RELATORIOS" / "_GARANTIAS").glob("GARANTIAS_*.csv"))
    assert len(arqs) == 1 and len(arqs[0].read_text(encoding="utf-8-sig").splitlines()) > 5


def test_garantia_nova_com_numero_repetido_e_linha_inexistente(tmp_path):
    ba._gravar_garantia_pc(tmp_path, "G-0001", {"_novo": True})
    with pytest.raises(ba.ErroGravacaoWeb) as e:
        ba._gravar_garantia_pc(tmp_path, "G-0001", {"_novo": True})
    assert e.value.motivo == ba.MOTIVO_JA_EXISTE_WEB
    with pytest.raises(ba.ErroGravacaoWeb) as e:
        ba._gravar_garantia_pc(tmp_path, "G-0099", {"status": "ABERTO"})
    assert e.value.motivo == ba.MOTIVO_LINHA_WEB


def test_prazo_igual_ao_padrao_fica_em_branco_e_ticket_troca(tmp_path):
    ba._gravar_garantia_pc(tmp_path, "G-0001", {"_novo": True, "dt_solicitacao": "03/11/2026"})
    import bap_dados as bd
    padrao = gm.prazo_padrao(date(2026, 11, 3), bd.feriados(tmp_path))   # com os feriados que o robô usa
    ba._gravar_garantia_pc(tmp_path, "G-0001", {"dt_prazo": f"{padrao:%d/%m/%Y}"})
    assert not gm.ler(tmp_path)["G-0001"].get("dt_prazo")
    ba._gravar_garantia_pc(tmp_path, "G-0001", {"ticket": "G-0007", "observacao": "x"})
    d = gm.ler(tmp_path)
    assert "G-0007" in d and "G-0001" not in d and d["G-0007"]["observacao"] == "x"


def test_aplicar_edicao_garantia_nova_e_erro_do_pc(tmp_path):
    chamadas = []

    def grava(raiz, modulo, arquivo, aba, edicoes):
        chamadas.append((modulo, edicoes))
        return ba.gravar_edicoes_pc(tmp_path, modulo, arquivo, aba, edicoes)
    r = reg("pl_garantias", "Garantias", "garantias", "G-0005", {"status": "ABERTO"}, novo=True)
    assert ba.aplicar_edicao_web(tmp_path, r, OPC, grava) == ("aplicada", "")
    assert chamadas[0][1]["G-0005"]["_novo"] is True
    assert ba.aplicar_edicao_web(tmp_path, r, OPC, grava) == ("erro", ba.MOTIVO_JA_EXISTE_WEB)


def test_edicao_garantias_spec_sem_dado_pessoal():
    nomes = [n for n, *_ in ba._GARANTIAS_WEB]
    linhas = [["x"] * len(nomes) for _ in range(2)]
    i = nomes.index("TICKET")
    linhas[0][i], linhas[1][i] = "G-0001", "G-0004"
    ed = ba._edicao_garantias_web(linhas, nomes, nomes)
    assert ed["chaves"] == ["G-0001", "G-0004"] and ed["novo"] == {"chave": "G-0005"}
    campos = {c["campo"] for c in ed["campos"]}
    assert not campos & {"contato_nome", "contato_fone", "cli_telefone", "cli_endereco"}
    assert len(ed["campos"]) <= 16


# ---------------------------------------------------------------- bases congeladas (20/11)
def _web_app():
    import types
    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz / "web"))
    from app import pacotes, tabelas
    return types.SimpleNamespace(pacotes=pacotes, tabelas=tabelas)


def test_colunas_do_robo_iguais_as_da_web_e_o_pc_monta_sem_derrubar_aba():
    import relatorios_nucleo as rn
    raiz = Path(__file__).resolve().parents[1]
    web = _web_app()
    rels = {}
    for rid in ("pl_garantias", "pl_devolucoes", "pl_ncc"):
        for titulo, cols in ba._COLUNAS_TABELAS_WEB[rid].items():
            assert [c[:3] for c in cols] == [tuple(c) for c in web.tabelas.COLUNAS_RID[(rid, titulo)]], titulo
        rels[rid] = rn.montar(rid, raiz, hoje=date(2026, 11, 20), params={"ANO": "2026", "MÊS": "11"})
    pacote = ba.montar_pacote_web(rels, 2026, 11, raiz=raiz)
    for rid in rels:
        titulos = [t["titulo"] for t in pacote["relatorios"][rid]["tabelas"]]
        assert titulos == list(ba._ABAS_TABELAS_WEB[rid])          # nenhuma aba caiu
    assert web.pacotes.validar(pacote) == []                       # a web aceita o que o robô manda
    import json
    txt = json.dumps(pacote, ensure_ascii=False)
    assert "CONTATO CLIENTE" not in txt and "TELEFONE" not in txt
    gar = pacote["relatorios"]["pl_garantias"]["tabelas"][0]
    assert gar["edicao"]["modulo"] == "garantias" and gar["edicao"]["novo"]["chave"].startswith("G-")
    assert pacote["relatorios"]["pl_ncc"]["tabelas"][0]["edicao"]["modulo"] == "ncc"
    assert pacote["relatorios"]["pl_devolucoes"]["tabelas"][0]["edicao"]["campos"]
