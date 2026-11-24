"""T-0017: as fotos do Farol de Inadimplência sem CNPJs internos (RN-GER-004).
Dados fictícios (sem nome real de cliente)."""
from datetime import date

import bap_dados as bd


def _t(cod, nome, saldo, venc, num="1"):
    return {"filial": "01", "cod": cod, "loja": "01", "cgc": "", "nome": nome,
            "emissao": None, "venc": venc, "prefixo": "A", "num": num,
            "parcela": "", "tipo": "NF", "valor": saldo, "saldo": saldo,
            "cond": "", "cond_desc": ""}


DIA = date(2026, 11, 20)
VENCIDO = date(2026, 11, 1)


def test_RN_GER_004_foto_tira_bap_autoparts_frw_e_pmz_distribuidora():
    titulos = [_t("100001", "CLIENTE EXTERNO A", 100.0, VENCIDO, "1"),
               _t("100002", "BAP AUTOPARTS LTDA", 50.0, VENCIDO, "2"),
               _t("100003", "FRW COMERCIO", 30.0, VENCIDO, "3"),
               _t("100004", "PMZ DISTRIBUIDORA", 20.0, VENCIDO, "4")]
    assert [t["cod"] for t in bd.titulos_sem_internos(titulos)] == ["100001"]


def test_RN_GER_004_resumo_da_foto_sem_interno_no_atraso():
    titulos = [_t("100001", "CLIENTE EXTERNO A", 100.0, VENCIDO, "1"),
               _t("100002", "BAP AUTOPARTS LTDA", 50.0, VENCIDO, "2")]
    r = bd.resumo_da_foto(bd.titulos_sem_internos(titulos), DIA)
    assert (r["atraso"], r["clientes"], r["titulos"]) == (100.0, 1, 1)


def test_RN_GER_004_titulos_sem_internos_e_pura_e_aceita_vazio():
    titulos = [_t("100002", "BAP AUTO PARTS", 50.0, VENCIDO)]
    copia = [dict(t) for t in titulos]
    assert bd.titulos_sem_internos(titulos) == []
    assert titulos == copia
    assert bd.titulos_sem_internos(None) == []


def test_RN_GER_004_marca_nova_no_cache_do_bloco_e_versao_27(tmp_path):
    _, extra = bd._fontes(tmp_path, "inadimplencia")
    assert "fi1" in extra
    assert bd.VERSAO == 27
