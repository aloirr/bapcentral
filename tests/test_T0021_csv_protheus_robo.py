"""T-0021: o robô leva para a web os CSVs de importação no Protheus (reversa de loja e separação de CD).

Pasta temporária, dados fictícios. Os testes entram antes do robô (ordem testes -> robô): sem a
função do robô, pulam.
"""
from datetime import date

import bap_automation as ba

HOJE = date(2026, 11, 24)
CAB = "FILIAL ORIGEM;EMPRESA PADRAO;FORNECEDOR;PRODUTO;FILIAL DESTINO;QUANTIDADE UNIDADES\r\n"


def _pasta(tmp_path):
    p = tmp_path / ba.SUBPASTA_IMPORTAR
    p.mkdir(parents=True)
    return p


def test_ultimos_30_dias_nome_no_padrao_e_texto_exato(tmp_path):
    p = _pasta(tmp_path)
    ok = CAB + "010101;1;000001;PROD0001;010102;3\r\n"
    (p / "261124_001_BELEM_BAPReversaLoja.csv").write_bytes(ok.encode("utf-8"))
    (p / "261124_001_MANAUS_BAPSeparacaoCD.csv").write_bytes(ok.encode("utf-8"))
    (p / "261001_001_BELEM_BAPReversaLoja.csv").write_bytes(ok.encode("utf-8"))      # velho (> 30 dias)
    (p / "261124_001_BELEM_Outro.csv").write_bytes(b"x")                              # nome fora do padrão
    (p / "anotacao.txt").write_bytes(b"x")
    (p / "SIMULACAO").mkdir()
    (p / "261124_002_BELEM_BAPReversaLoja.csv").write_bytes(b"\xff\xfe\x00")          # não é UTF-8
    r = ba.csvs_importar_web(tmp_path, HOJE)
    assert {c["nome"] for c in r} == {"261124_001_BELEM_BAPReversaLoja.csv", "261124_001_MANAUS_BAPSeparacaoCD.csv"}
    assert all(c["conteudo"] == ok and "\r\n" in c["conteudo"] for c in r)           # CRLF preservado


def test_tetos(tmp_path, monkeypatch):
    p = _pasta(tmp_path)
    monkeypatch.setattr(ba, "CSV_WEB_MAX_ARQUIVOS", 2)
    for n in range(1, 5):
        (p / f"2611{20 + n:02d}_001_BELEM_BAPReversaLoja.csv").write_text(CAB, encoding="utf-8", newline="")
    assert [c["nome"][:6] for c in ba.csvs_importar_web(tmp_path, HOJE)] == ["261124", "261123"]
    monkeypatch.setattr(ba, "CSV_WEB_MAX_BYTES", 10)
    assert ba.csvs_importar_web(tmp_path, HOJE) == []


def test_sem_pasta_nao_levanta(tmp_path):
    assert ba.csvs_importar_web(tmp_path / "nao_existe", HOJE) == []


def test_so_o_pedidos_leva_o_csv():
    csvs = [{"nome": "261124_001_BELEM_BAPReversaLoja.csv", "conteudo": CAB}]
    f = {"forma": "farol", "titulo": "t", "kpis": [], "painel": {"blocos": []}}
    pacote = ba.montar_pacote_web({"pv_pedidos": dict(f), "pl_entregas": dict(f)}, 2026, 11, csvs=csvs)
    rels = pacote["relatorios"]
    assert rels["pv_pedidos"]["csvs_protheus"] == csvs
    assert "csvs_protheus" not in rels["pl_entregas"]
