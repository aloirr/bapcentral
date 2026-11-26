"""T-0021: CSVs de importação no Protheus como o robô manda (dados fictícios, formato do PC: ';' e CRLF)."""
from copy import deepcopy

from edicao_fixture import pacote_editavel

CAB = "FILIAL ORIGEM;EMPRESA PADRAO;FORNECEDOR;PRODUTO;FILIAL DESTINO;QUANTIDADE UNIDADES\r\n"
CSVS = [
    {"nome": "261124_001_BELEM_BAPReversaLoja.csv",
     "conteudo": CAB + "010101;1;000001;PROD0001;010102;3\r\n010101;1;000001;PROD0002;010102;12\r\n"},
    {"nome": "261124_002_MANAUS_BAPSeparacaoCD.csv", "conteudo": CAB + "010103;1;000002;PROD0009;010101;5\r\n"},
    {"nome": "261120_007_BELEM_BAPReversaLoja.csv", "conteudo": CAB + "010101;1;000001;PROD0003;010102;1\r\n"},
]


def pacote_com_csvs(gerado_em="2026-11-24T08:30:00-04:00"):
    p = pacote_editavel(gerado_em)
    p["relatorios"]["pv_pedidos"]["csvs_protheus"] = deepcopy(CSVS)
    return p
