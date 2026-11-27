"""T-0060: o cache do Farol de Metas (bloco meta@) com a decisão 43.

Regras:
- RN-GER-007 (decisões 43 e 48): hoje conta no grupo A; o acompanhar do
  Metas precisa do HOJE para separar os dias restantes dos grupos A e B.
- CLAUDE.md, regras 3 e 4: regra nova de cache = marca nova na assinatura
  do bloco (VERSAO fica em 27); o dia é o de America/Manaus.

Código: bap_dados._fontes / _hoje_manaus / _bloco_meta (engenheiro-dados).
Sem dado pessoal: o acompanhar é trocado por um espião; nada é gravado.
"""
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import bap_dados as bd

RAIZ = Path(__file__).resolve().parent.parent


def _relogio(monkeypatch, instante_utc):
    """Congela o datetime.now do bap_dados num instante UTC (host em UTC)."""
    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return instante_utc.astimezone(tz) if tz else \
                instante_utc.replace(tzinfo=None)
    monkeypatch.setattr(bd, "datetime", _DT)


def test_RN_GER_007_versao_do_cache_continua_27():
    assert bd.VERSAO == 27


@pytest.mark.parametrize("instante, dia", [
    # 01/12 01h UTC = 30/11 21h em Manaus: o dia ainda não virou
    (datetime(2026, 12, 1, 1, 0, tzinfo=timezone.utc), date(2026, 11, 30)),
    # 01/12 03h59 UTC = 30/11 23h59 em Manaus
    (datetime(2026, 12, 1, 3, 59, tzinfo=timezone.utc), date(2026, 11, 30)),
    # 01/12 04h UTC = meia-noite em Manaus: virou
    (datetime(2026, 12, 1, 4, 0, tzinfo=timezone.utc), date(2026, 12, 1)),
])
def test_RN_GER_007_fontes_meta_marca_t0060_e_dia_de_manaus(
        monkeypatch, instante, dia):
    _relogio(monkeypatch, instante)
    assert bd._hoje_manaus() == dia
    _arqs, assinatura = bd._fontes(RAIZ, "meta@2026-11")
    marcas = assinatura.split("|")
    assert marcas[0] == dia.isoformat()
    assert "t0060-hoje-conta" in marcas
    assert marcas[-1] == "2026-11"


def test_RN_GER_007_bloco_meta_repassa_o_hoje_de_manaus_ao_acompanhar(
        monkeypatch):
    """_bloco_meta chama mn.acompanhar com hoje= o dia de Manaus (às 21h de
    30/11 em Manaus, com o host já em 01/12 UTC)."""
    _relogio(monkeypatch, datetime(2026, 12, 1, 1, 0, tzinfo=timezone.utc))
    chamadas = []

    class _Parou(Exception):
        pass

    def espiao(*a, **kw):
        chamadas.append(kw)
        raise _Parou
    mn = SimpleNamespace(
        achar_visitas_do_mes=lambda *a, **k: None,
        ler_visitas_realizadas=lambda *a, **k: {},
        datas_de_cadastro=lambda *a, **k: {},
        cadastros_por_vendedor=lambda *a, **k: {},
        zonas_dos_supervisores=lambda *a, **k: {},
        acompanhar=espiao)
    monkeypatch.setattr(bd, "_contexto_meta", lambda raiz, comp: (
        mn, {}, None, {"competencia": "2026-11"}))
    monkeypatch.setattr(bd, "_realizado", lambda *a, **k: {})
    with pytest.raises(_Parou):
        bd._bloco_meta(RAIZ, "2026-11")
    assert len(chamadas) == 1
    assert chamadas[0]["hoje"] == date(2026, 11, 30)
