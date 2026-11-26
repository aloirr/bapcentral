"""T-0017 (passo 4f do robô): Farol de Inadimplência no pacote da web.

Contrato: forma "farol" (§10.1 de .coord/contratos/relatorio.md).
Regras citadas: RN-GER-006 (estado = filial da nota) nos recortes; regra 6
do CLAUDE.md (sem dado pessoal) na seleção; regra 4 (fuso America/Manaus) no
carimbo. Testes sem RN própria (encanamento do pacote) levam o prefixo T0017.

Junta a versão do testes com a do robô (test_T0017_farol_web_robo.py e
test_T0017_extra.py), sem casos repetidos.

Dados 100% fictícios (sem cliente, CNPJ, telefone ou nome de pessoa real).
"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

import bap_automation as ba

AGORA = datetime(2026, 11, 24, 10, 0, tzinfo=timezone(timedelta(hours=-4)))
UF = {"MANAUS": "AM", "BOA VISTA": "RR", "BELEM": "PA"}


def _kpis_de(linhas):
    return [{"rotulo": "Em atraso", "valor": f"R$ {sum(l[1] for l in linhas)}",
             "cor": "alerta", "detalhe": ""}]


def _farol():
    linhas = [["MANAUS", 100.0], ["MANAUS", 50.0], ["BOA VISTA", 30.0],
              ["BELEM", 20.0], ["FILIAL X", 5.0]]
    return {
        "id": "pl_inadimplencia", "titulo": "Farol de Inadimplência",
        "kpis": [{"rotulo": "Em atraso", "valor": "R$ 205", "cor": "alerta",
                  "detalhe": ""}],
        "graficos": [{"titulo": "bruto"}], "editar": {"x": 1},
        "avisos": ["aviso fictício"],
        "tabelas": [{"titulo": "Títulos",
                     "colunas": [{"nome": "FILIAL"}, {"nome": "SALDO"}],
                     "linhas": linhas, "kpis_de": _kpis_de, "edicao": None}],
        "painel": {"blocos": [
            {"tipo": "insights", "titulo": "O que o farol diz", "col": 0,
             "linhas": [("alerta", "Inadimplência: 65%."),
                        ("alerta", "Maiores devedores: CLIENTE FICTICIO "
                                  "00.000.000/0001-00 (R$ 9)."),
                        ("info", "Em atraso por vendedor (R$): maior FULANO "
                                 "(R$ 5), menor BELTRANO (R$ 1).")]},
            {"tipo": "barras", "col": 1, "abrir": lambda: 1, "_x": 1,
             "grafico": {"titulo": "Por filial", "rotulos": ["AM"],
                         "series": [{"nome": "s", "valores": [1.0]}]}},
            {"tipo": "hbarras", "titulo": "Em atraso por vendedor (R$)",
             "rotulos": ["FULANO", "BELTRANO"], "valores": [5, 1],
             "_insight": True},
            {"tipo": "hbarras", "titulo": "Por faixa", "rotulos": ["0-30"],
             "valores": [3]},
            {"tipo": "tabela", "titulo": "Frete", "linhas": [[1]]},
            {"tipo": "kpis", "cartoes": [{"rotulo": "a", "valor": "1"}]}]},
        "insights_painel": [("alerta", "Inadimplência: 65%."),
                            ("alerta", "Maiores devedores: CLIENTE FICTICIO "
                                      "00.000.000/0001-00."),
                            ("info", "Em atraso por vendedor (R$): maior "
                                     "FULANO (R$ 5).")],
    }


def _sel(**kw):
    kw.setdefault("grafico_com_nome", False)
    return ba.selecionar_farol_web("pl_inadimplencia", _farol(), AGORA, **kw)


def _chaves(obj, achadas=None):
    achadas = set() if achadas is None else achadas
    if isinstance(obj, dict):
        for k, v in obj.items():
            achadas.add(k)
            _chaves(v, achadas)
    elif isinstance(obj, list):
        for v in obj:
            _chaves(v, achadas)
    return achadas


def test_T0017_forma_do_farol_json_puro_com_fuso_manaus():
    r = _sel()
    assert set(r) == {"forma", "titulo", "kpis", "painel", "insights_painel",
                      "avisos", "recortes", "baixado_em"}
    assert r["forma"] == "farol"
    assert r["baixado_em"].endswith("-04:00")          # America/Manaus
    json.dumps(r, allow_nan=False)                     # sem callable
    # os cartões do total vão inteiros, sem mexer no valor
    assert r["kpis"] == _farol()["kpis"]


def test_T0017_agora_sem_fuso_vira_manaus():
    sem_fuso = AGORA.replace(tzinfo=None)
    r = ba.selecionar_farol_web("pl_inadimplencia", _farol(), sem_fuso,
                                grafico_com_nome=False)
    assert r["baixado_em"] == "2026-11-24T10:00:00-04:00"


def test_T0017_sem_chaves_proibidas_nem_tipos_fora():
    r = _sel()
    proibidas = {"tabelas", "juntas", "edicao", "editar", "abrir", "kpis_de",
                 "_x", "_insight"}
    assert not (_chaves(r) & proibidas)
    tipos = {b["tipo"] for b in r["painel"]["blocos"]}
    assert tipos <= {"insights", "barras", "hbarras"}
    assert "tabela" not in tipos


def test_T0017_sem_grafico_com_nome_quando_a_chave_e_false(monkeypatch):
    monkeypatch.setattr(ba, "WEB_GRAFICOS_COM_NOME", False)
    r = ba.selecionar_farol_web("pl_inadimplencia", _farol(), AGORA)
    txt = json.dumps(r, ensure_ascii=False)
    assert "FULANO" not in txt and "BELTRANO" not in txt
    # nenhuma frase do ranking por vendedor, nem no topo nem no bloco
    frases = [str(l) for l in r["insights_painel"]] + [
        str(l) for b in r["painel"]["blocos"] if b["tipo"] == "insights"
        for l in b["linhas"]]
    assert frases and all("vendedor" not in f.lower() for f in frases)
    # a frase sem nome continua (o filtro não apaga demais)
    assert any("Inadimplência: 65%." in f for f in frases)
    assert any(b.get("titulo") == "Por faixa" for b in r["painel"]["blocos"])


def test_T0017_com_a_chave_true_o_grafico_de_vendedor_volta(monkeypatch):
    monkeypatch.setattr(ba, "WEB_GRAFICOS_COM_NOME", True)
    r = ba.selecionar_farol_web("pl_inadimplencia", _farol(), AGORA)
    assert any(b.get("titulo") == "Em atraso por vendedor (R$)"
               for b in r["painel"]["blocos"])


def test_T0017_cliente_nunca_vai_nem_com_a_chave_true():
    r = _sel(grafico_com_nome=True)
    txt = json.dumps(r, ensure_ascii=False)
    assert "CLIENTE FICTICIO" not in txt
    assert "00.000.000/0001-00" not in txt              # nem CNPJ
    assert all("devedores" not in str(l) for l in r["insights_painel"])
    blocos_ins = [b for b in r["painel"]["blocos"] if b["tipo"] == "insights"]
    assert all("devedores" not in str(l) for b in blocos_ins
               for l in b["linhas"])


def test_RN_GER_006_recorte_farol_por_filial():
    rec = ba.recortes_farol_por_uf(_farol(), uf_de=lambda n: UF.get(n, ""))
    assert set(rec) == {"AM", "PA", "RR"}              # filial X fora
    assert rec["AM"]["kpis"][0]["valor"] == "R$ 150.0"
    assert rec["RR"]["kpis"][0]["valor"] == "R$ 30.0"


def test_RN_GER_006_recortes_somam_ao_total_quando_ha_so_filiais_de_estado():
    f = _farol()
    f["tabelas"][0]["linhas"].pop()                    # tira a "FILIAL X"
    rec = ba.recortes_farol_por_uf(f, uf_de=lambda n: UF.get(n, ""))
    soma = sum(float(v["kpis"][0]["valor"][3:]) for v in rec.values())
    assert soma == 200.0
    assert soma == sum(l[1] for l in f["tabelas"][0]["linhas"])


def test_RN_GER_006_recorte_usa_o_mapa_real_de_filiais():
    f = _farol()
    f["tabelas"][0]["linhas"] = [["Manaus", 10.0], ["Belém", 5.0]]
    rec = ba.recortes_farol_por_uf(f)
    assert set(rec) == {"AM", "PA"}
    assert rec["AM"]["kpis"][0]["valor"] == "R$ 10.0"
    assert rec["PA"]["kpis"][0]["valor"] == "R$ 5.0"


@pytest.mark.parametrize("filial,uf", [
    ("0101002", "AM"), ("0101004", "RR"), ("0101005", "PA"),
    ("0101007", "PA"), ("0101006", "MA"), ("0101003", "AP"),
    ("0101001", "MT")])
def test_RN_GER_006_recorte_pelo_codigo_da_filial(filial, uf):
    f = _farol()
    f["tabelas"][0]["linhas"] = [[filial, 7.0], ["0109999", 3.0]]
    rec = ba.recortes_farol_por_uf(f)
    assert rec == {uf: {"kpis": _kpis_de([[filial, 7.0]])}}


def test_T0017_recorte_sem_kpis_de_ou_sem_coluna_e_vazio():
    f = _farol()
    f["tabelas"][0]["kpis_de"] = None
    assert ba.recortes_farol_por_uf(f) == {}
    assert ba.recortes_farol_por_uf({}) == {}
    assert ba.recortes_farol_por_uf(_farol(), coluna_filial="NAO") == {}


def test_T0017_pacote_leva_o_farol_e_so_ele_dos_farois():
    assert "pl_inadimplencia" in ba.FAROIS_WEB         # 1ª entrega
    pac = ba.montar_pacote_web({"pl_inadimplencia": _farol()}, 2026, 11, AGORA)
    assert set(pac["relatorios"]) == {"pl_inadimplencia"}
    assert pac["relatorios"]["pl_inadimplencia"]["forma"] == "farol"
    json.dumps(pac)


def test_T0017_falha_de_um_farol_nao_derruba_o_pacote(monkeypatch):
    import relatorios_nucleo

    def _montar(rid, pasta, params=None, **_kw):   # T-0022: o robô passa tela= ao Farol de Metas
        if rid == "pl_inadimplencia":
            raise RuntimeError("quebrou")
        return {"id": rid}
    monkeypatch.setattr(relatorios_nucleo, "montar", _montar)
    saida = ba.coletar_relatorios_web(2026, 11)
    assert saida["pl_inadimplencia"]["erro_montagem"] == "RuntimeError"
    pac = ba.montar_pacote_web(saida, 2026, 11, AGORA)
    assert "pl_inadimplencia" not in pac["relatorios"]


def test_T0017_selecao_que_estoura_fica_fora_e_o_resto_segue(monkeypatch):
    def _quebra(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(ba, "selecionar_farol_web", _quebra)
    pac = ba.montar_pacote_web({"pl_inadimplencia": _farol()}, 2026, 11, AGORA)
    assert pac["relatorios"] == {}


def test_T0017_frase_com_contagem_de_clientes_fica():
    f = _farol()
    frase = ("alerta", "Em atraso: R$ 400 (329 títulos · 136 clientes).")
    f["insights_painel"].append(frase)
    f["painel"]["blocos"][0]["linhas"].append(frase)
    r = ba.selecionar_farol_web("pl_inadimplencia", f, AGORA,
                                grafico_com_nome=False)
    assert list(frase) in r["insights_painel"]
    assert list(frase) in r["painel"]["blocos"][0]["linhas"]
    assert all("devedores" not in str(l) for l in r["insights_painel"])


def test_T0017_kpi_leva_as_mini_barras_por_estado(monkeypatch):
    import relatorios_nucleo as rn
    barras = [("AM", 10.0, "R$ 10", "", ""), ("PA", 5.0, "R$ 5", "", "")]
    monkeypatch.setattr(rn, "estados_do_cartao", lambda rel, k: (
        {"barras": barras, "legenda": "", "conferencia": {"x": 1}}
        if k["rotulo"] == "Em atraso" else {}))
    f = _farol()
    f["kpis"].append({"rotulo": "Outro", "valor": "1", "cor": "neutro",
                      "detalhe": ""})
    r = ba.selecionar_farol_web("pl_inadimplencia", f, AGORA,
                                grafico_com_nome=False)
    assert r["kpis"][0]["estados"] == {
        "barras": [["AM", 10.0, "R$ 10", "", ""], ["PA", 5.0, "R$ 5", "", ""]],
        "legenda": ""}
    assert "estados" not in r["kpis"][1]


def test_T0017_baixado_em_e_o_da_base_nao_o_da_montagem(tmp_path):
    arq = tmp_path / "Relatorio_Titulos_em_Abertos_2026-11-24.xlsx"
    arq.write_bytes(b"x")
    os.utime(arq, (1_700_000_000, 1_700_000_000))        # 2023-11-14 UTC
    pac = ba.montar_pacote_web({"pl_inadimplencia": _farol()}, 2026, 11,
                               AGORA, arquivos_base={"pl_inadimplencia": arq})
    b = pac["relatorios"]["pl_inadimplencia"]["baixado_em"]
    assert b == "2023-11-14T18:13:20-04:00"
    assert b != pac["gerado_em"]


def test_T0017_sem_a_base_baixado_em_e_nulo(tmp_path):
    pac = ba.montar_pacote_web({"pl_inadimplencia": _farol()}, 2026, 11,
                               AGORA, arquivos_base={"pl_inadimplencia": tmp_path / "nao.xlsx"})
    assert pac["relatorios"]["pl_inadimplencia"]["baixado_em"] is None


def test_T0017_baixado_em_e_o_mtime_do_titulos_em_abertos_mais_novo_pelo_nome(
        tmp_path):
    # mtimes invertidos: o de 22/11 foi gravado depois, mas vale o nome (23/11)
    pasta = tmp_path / "SISTEMA BAP" / "BACKUP_RELATORIOS" / "BKP_RELATORIOS_BAPTOOLS"
    pasta.mkdir(parents=True)
    for dia, ts in (("2026-11-22", 1_700_003_600), ("2026-11-23", 1_700_000_000)):
        a = pasta / f"Relatorio_Titulos_em_Abertos_{dia}.xlsx"
        a.write_bytes(b"x")
        os.utime(a, (ts, ts))
    q = ba._baixado_em_da_base("pl_inadimplencia", tmp_path)
    assert q.isoformat() == "2023-11-14T18:13:20-04:00"
    assert ba._baixado_em_da_base("pl_inadimplencia", tmp_path / "vazio") is None
