"""Testes da T-0056: a rotina diaria instala o commit mais novo com 2 h.

ADR 0002 §7, regra 11 do CLAUDE.md, desenho em ``docs/desenho/T-0056.md``.
Com o HEAD do ``main`` com menos de 2 h, o ``--diario`` lista os commits do
``main`` (``escolher_commit_maduro``) e instala o mais novo com 2 h ou mais,
com os limites 2, 3 (so igual, ``versoes_batem``) e 5 valendo para ele.

Sem rede (fixture ``_sem_rede`` da T-0018), tudo em ``tmp_path``, SHAs e
versoes ficticios, sem dado pessoal.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import atualizar_do_github as atu
from test_T0018_rotina_diaria import (  # noqa: F401  (fixtures da T-0018)
    AGORA, SHA, T_COMMIT, _commit, _log, _pr, _sem_rede, _sem_troca, producao, rede,
)

HEAD = "d" * 40          # HEAD novo (0,5 h)
MEIO = "c" * 40          # commit intermediario, ainda novo (1 h)
VELHO = "e" * 40         # commit mais antigo que o escolhido (30 h)


def _c(sha, horas: float):
    """Item da lista ``/commits?sha=main`` com ``horas`` de idade."""
    return _commit(sha, AGORA - timedelta(hours=horas))


# --------------------------------------------------------------------------
# Limite 1 puro: escolher_commit_maduro
# --------------------------------------------------------------------------

def test_T0056_limite_1_escolhe_o_mais_novo_com_2h():
    e = atu.escolher_commit_maduro([_c(HEAD, 0.5), _c(SHA, 2.3), _c(VELHO, 9)], AGORA)
    assert e.situacao == "maduro" and e.sha == SHA
    assert e.data == AGORA - timedelta(hours=2.3)


def test_T0056_limite_1_2h_exatas_e_maduro_1h59_nao():
    assert atu.escolher_commit_maduro([_c(SHA, 2)], AGORA) == ("maduro", SHA, AGORA - timedelta(hours=2))
    assert atu.escolher_commit_maduro([_c(SHA, 1 + 59 / 60)], AGORA).situacao == "nenhum_maduro"


@pytest.mark.parametrize("lista", [[], None])
def test_T0056_limite_1_lista_vazia_ou_none_e_nenhum_maduro(lista):
    assert atu.escolher_commit_maduro(lista, AGORA) == ("nenhum_maduro", None, None)


def test_T0056_limite_1_lixo_e_ignorado_e_acha_o_valido():
    lixo = ["texto", 42, None, {"sha": "abc1234"}, {"sha": "f" * 40},   # sem data = novo
            _c("g" * 40, 9),                                             # SHA invalido
            {"sha": "9" * 40, "commit": {"committer": {"date": "ontem"}}},
            _c(SHA, 3), _c(VELHO, 30)]
    e = atu.escolher_commit_maduro(lixo, AGORA)
    assert e.situacao == "maduro" and e.sha == SHA


def test_T0056_limite_1_relacao_com_o_instalado():
    lista = [_c(HEAD, 0.5), _c(MEIO, 1), _c(SHA, 9), _c(VELHO, 30)]
    assert atu.escolher_commit_maduro(lista, AGORA, SHA).situacao == "ja_instalado"
    assert atu.escolher_commit_maduro(lista, AGORA, SHA.upper()).situacao == "ja_instalado"
    assert atu.escolher_commit_maduro(lista, AGORA, MEIO) == ("instalado_mais_novo", None, None)
    assert atu.escolher_commit_maduro(lista, AGORA, HEAD).situacao == "instalado_mais_novo"
    antigo = atu.escolher_commit_maduro(lista, AGORA, VELHO)        # instalado antigo
    assert antigo.situacao == "maduro" and antigo.sha == SHA
    fora = atu.escolher_commit_maduro(lista, AGORA, "1" * 40)       # fora da lista
    assert fora.situacao == "maduro" and fora.sha == SHA


def test_T0056_limite_1_commit_no_futuro_nao_e_escolhido():
    e = atu.escolher_commit_maduro([_c(HEAD, -3), _c(SHA, 4)], AGORA)
    assert e.situacao == "maduro" and e.sha == SHA
    assert atu.escolher_commit_maduro([_c(HEAD, -3)], AGORA).situacao == "nenhum_maduro"


def test_T0056_horas_desde_com_virgula_para_o_log():
    assert atu.horas_desde(AGORA - timedelta(hours=2.3), AGORA) == "2,3"
    assert atu.horas_desde(AGORA - timedelta(minutes=30), AGORA) == "0,5"
    assert atu.horas_desde(AGORA - timedelta(hours=9), AGORA) == "9,0"


# --------------------------------------------------------------------------
# --diario ponta a ponta (fixtures rede/producao da T-0018 com a lista)
# --------------------------------------------------------------------------

def _head_novo(rede, lista=None):
    """HEAD ``ddddddd`` com 0,5 h; o maduro (``aaaaaaa``, 9 h) e o do zip e dos pulls."""
    rede.update(head=HEAD, data_head=AGORA - timedelta(minutes=30),
                lista=lista if lista is not None else [_c(HEAD, 0.5), _c(SHA, 9)])
    return rede


def _pagas(rede) -> list[str]:
    return [u for u in rede["chamadas"] if not u.endswith("/rate_limit")]


def test_RN_11_T0056_diario_head_novo_instala_o_maduro(rede, producao):
    _head_novo(rede)
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_OK
    assert (producao / "bap_central.py").read_bytes() == b"novo\n"
    assert (producao / "instalar_bap.bat").read_bytes() == b"velho bat\n"   # so com instale
    assert atu.sha_instalado(producao) == SHA
    linhas = _log(producao)
    assert len(linhas) == 1 and "codigo 0" in linhas[0]
    assert "HEAD ddddddd com 0,5 h; escolhido aaaaaaa (9,0 h); instalado:" in linhas[0]
    assert "main aaaaaaa" in linhas[0]
    pagas = _pagas(rede)
    assert len(pagas) == 4 < atu.REQUISICOES_MINIMAS_API
    assert any("/commits?sha=main" in u for u in pagas)
    assert [u for u in pagas if u.endswith("/pulls")] == [
        u for u in pagas if f"/commits/{SHA}/pulls" in u]


def test_T0056_diario_sem_maduro_nao_troca(rede, producao):
    _head_novo(rede, [_c(HEAD, 0.5), _c(MEIO, 1)])
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_LIMITE_IDADE
    assert _sem_troca(producao)
    assert not any(u.endswith("/pulls") for u in rede["chamadas"])
    linhas = _log(producao)
    assert len(linhas) == 1 and "codigo 10" in linhas[0] and "HEAD ddddddd" in linhas[0]


def test_T0056_diario_maduro_ja_instalado_nada_a_fazer(rede, producao):
    _head_novo(rede)
    atu.gravar_versao(producao, SHA, AGORA - timedelta(days=1), 0, "diario")
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_OK
    assert (producao / "bap_central.py").read_bytes() == b"velho\n"
    assert not any(u.endswith("/pulls") for u in rede["chamadas"])
    assert "escolhido aaaaaaa" in _log(producao)[0]


def test_T0056_diario_instalado_mais_novo_nao_volta_para_tras(rede, producao):
    _head_novo(rede, [_c(HEAD, 0.5), _c(MEIO, 1), _c(SHA, 9)])
    atu.gravar_versao(producao, MEIO, AGORA - timedelta(minutes=50), 0, "diario")
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_LIMITE_IDADE
    assert (producao / "bap_central.py").read_bytes() == b"velho\n"
    assert atu.sha_instalado(producao) == MEIO
    assert not any(u.endswith("/pulls") for u in rede["chamadas"])
    assert "codigo 10" in _log(producao)[0]


@pytest.mark.parametrize("v_commit,v_site,codigo", [
    pytest.param("0.10.0", "0.10.0", atu.CODIGO_OK, id="web_igual"),
    pytest.param("0.9.0", "0.10.0", atu.CODIGO_LIMITE_VERSAO_WEB, id="web_anterior"),
])
def test_RN_11_T0056_diario_limite_3_so_igual_no_escolhido(rede, producao, v_commit, v_site, codigo):
    _head_novo(rede).update(versao_main=v_commit, versao_site=v_site)
    assert atu.rodar_diario(producao, agora=AGORA) == codigo
    if codigo == atu.CODIGO_OK:
        assert atu.sha_instalado(producao) == SHA
    else:
        assert _sem_troca(producao)
    linhas = _log(producao)
    assert len(linhas) == 1 and f"codigo {codigo}" in linhas[0]


def test_T0056_diario_limite_2_pr_de_outro_commit(rede, producao):
    _head_novo(rede).update(pulls=[_pr(7, HEAD)])        # o PR e do HEAD, nao do escolhido
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_LIMITE_CI
    assert _sem_troca(producao)
    assert "codigo 11" in _log(producao)[0]


def test_T0056_diario_lista_de_commits_fora_do_ar(rede, producao):
    _head_novo(rede).update(lista_fora_do_ar=True)
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_API
    assert _sem_troca(producao)
    linhas = _log(producao)
    assert len(linhas) == 1 and "codigo 15" in linhas[0]


def test_T0056_diario_lista_de_commits_que_nao_e_lista(rede, producao):
    _head_novo(rede).update(lista={"message": "formato inesperado"})
    assert atu.rodar_diario(producao, agora=AGORA) == atu.CODIGO_API
    assert _sem_troca(producao)
    assert not any(u.endswith("/pulls") for u in rede["chamadas"])
    linhas = _log(producao)
    assert len(linhas) == 1 and "codigo 15" in linhas[0]
