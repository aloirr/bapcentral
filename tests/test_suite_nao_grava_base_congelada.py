"""A suíte não grava em RELATORIOS/ (base congelada): o histórico do Painel do
Diretor vai para a cópia temporária do conftest."""
import hashlib
from datetime import date
from pathlib import Path

import painel_diretor as pdr
import relatorios_nucleo as rn

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "RELATORIOS" / pdr.ARQ_HIST


def _hash(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def test_historico_do_diretor_na_suite_vai_para_a_copia_temporaria():
    destino = pdr._hist_path(RAIZ)
    assert destino.resolve() != ARQ.resolve()
    assert RAIZ.resolve() not in destino.resolve().parents
    # outra raiz segue o caminho normal (testes com pasta fictícia)
    assert pdr._hist_path(Path("/x")) == Path("/x") / "RELATORIOS" / pdr.ARQ_HIST


def test_montar_o_painel_nao_muda_o_historico_do_repositorio():
    antes = _hash(ARQ)
    rn.montar("vc_painel", RAIZ, hoje=date(2026, 11, 24),
              params={"ANO": "2026", "MÊS": "11"})
    assert _hash(ARQ) == antes
