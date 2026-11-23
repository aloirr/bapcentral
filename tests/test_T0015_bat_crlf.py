"""T-0015: os .bat da raiz saem com CRLF (o padrão do Windows) no checkout.

Com o .gitattributes (`*.bat text eol=crlf`), o checkout e o zip do main
trazem os .bat com CRLF, como na pasta de produção (R-20261123-092906-alexandre).
Falha se algum .bat da raiz tiver quebra de linha LF sem o CR antes.

Atenção: num clone feito antes do .gitattributes, os .bat só mudam depois de
um checkout novo (ex.: apagar o .bat e fazer `git checkout -- <arquivo>`).
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def lf_soltos(dados: bytes) -> int:
    """Função pura: quantas quebras LF não vêm logo depois de um CR."""
    return dados.count(b"\n") - dados.count(b"\r\n")


def test_T0015_lf_soltos_conta_so_lf_sem_cr():
    assert lf_soltos(b"@echo off\r\npause\r\n") == 0
    assert lf_soltos(b"@echo off\npause\r\n") == 1
    assert lf_soltos(b"") == 0


def test_T0015_bat_da_raiz_saem_com_crlf():
    bats = sorted(RAIZ.glob("*.bat"))
    assert bats, "nenhum .bat na raiz"
    com_lf = {p.name: lf_soltos(p.read_bytes()) for p in bats}
    assert {nome: n for nome, n in com_lf.items() if n} == {}
